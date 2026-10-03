"""Sao lưu & phục hồi dữ liệu người dùng — chủ sở hữu duy nhất của mối quan
tâm "gói dữ liệu di chuyển được giữa các máy".

Contract: ``docs/plans/backup-restore-plan.md`` (3 quyết định Owner 03/10/2026).
Hoạt động ở tầng tệp: mở connection SQLite riêng chỉ để snapshot DB qua
``VACUUM INTO`` (an toàn WAL kể cả khi producer news đang ghi), thu thập các
tệp trạng thái theo danh sách bao gồm/loại trừ của plan, đóng gói một file zip
kèm manifest SHA-256. Phục hồi trải qua hai bước: stage trong thư mục chờ +
marker, rồi áp dụng lúc khởi động — TRƯỚC khi bất kỳ service nào mở DB
(``main.py`` là điểm gọi duy nhất của ``apply_pending_restore``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config.paths import app_data_dir

__all__ = [
    "ApplyResult",
    "BackupResult",
    "BackupService",
    "StageResult",
    "ValidationResult",
]

logger = logging.getLogger(__name__)

# --- Phạm vi theo plan §3 (Q1: "đầy đủ trừ rác") -----------------------------
DATABASES = ("journal.db", "news.db")
ROOT_FILES = (
    "settings.json",
    "ai-market-analyst.ini",
    "be_trailing_state.json",
    "vix_pair_sensitivity.json",
)
DATA_DIRS = (
    "scan_health",
    "scanner_snapshots",
    "scanner_analysis",
    "scanner_jobs",
)

MANIFEST_NAME = "manifest.json"
BACKUP_PREFIX = "backup-"
BACKUPS_DIR = "backups"
# OPEN (B5): số thế hệ giữ lại chưa có bằng chứng hiệu chỉnh — 5 là mặc định
# vận hành, đổi tại đây khi có dữ liệu sử dụng thật.
RETENTION_KEEP = 5

PENDING_DIR = "restore-pending"
REQUEST_NAME = "restore-request.json"

SQLITE_TIMEOUT_SECONDS = 30.0
SQLITE_BUSY_TIMEOUT_MS = 15000
_HASH_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class BackupResult:
    zip_path: Path
    manifest: dict
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()
    manifest: dict | None = None


@dataclass(frozen=True)
class StageResult:
    ok: bool
    errors: tuple[str, ...] = ()
    staging_dir: Path | None = None
    safety_backup: Path | None = None
    message: str = ""


@dataclass(frozen=True)
class ApplyResult:
    applied: bool
    safety_backup: Path | None = None
    applied_files: int = 0
    errors: tuple[str, ...] = ()


def _sha256_of(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _max_migration(snapshot_path: Path) -> str | None:
    """Mức migration cao nhất trong bảng schema_migrations của snapshot."""

    try:
        conn = sqlite3.connect(snapshot_path, timeout=SQLITE_TIMEOUT_SECONDS)
    except sqlite3.Error:
        return None
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if table is None:
            return None
        versions = [
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        ]
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not versions:
        return None
    return max(versions, key=lambda v: int(str(v).split("_", 1)[0] or 0))


class BackupService:
    """Sao lưu/phục hồi toàn bộ dữ liệu người dùng tại ``app_data_dir()``.

    Chấp nhận ``app_data_root`` tường minh để kiểm thử — mọi đường dẫn nội
    bộ suy ra từ gốc này, không tự suy lại đường dẫn ở chỗ khác (một nguồn
    duy nhất: ``config/paths.py``).
    """

    def __init__(self, app_data_root: Path | None = None) -> None:
        self.root = Path(app_data_root) if app_data_root else app_data_dir()

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------

    def create_backup(self, dest_dir: Path | None = None) -> BackupResult:
        """Tạo một file zip hoàn chỉnh; trả về đường dẫn + manifest."""

        dest = Path(dest_dir) if dest_dir else self.root / BACKUPS_DIR
        dest.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="backup-build-", dir=dest))
        warnings: list[str] = []
        try:
            # (tệp nguồn, đường dẫn trong zip): DB lấy từ snapshot VACUUM,
            # phần còn lại lấy trực tiếp từ gốc.
            items: list[tuple[Path, str]] = []
            database_migrations: dict[str, str] = {}
            for name in DATABASES:
                source = self.root / name
                if not source.exists():
                    warnings.append(f"Không có {name} để sao lưu — bỏ qua.")
                    logger.warning("Backup: %s không tồn tại, bỏ qua", source)
                    continue
                snapshot = staging / name
                self._snapshot_database(source, snapshot)
                migration = _max_migration(snapshot)
                if migration is not None:
                    database_migrations[name] = migration
                items.append((snapshot, name))

            for name in ROOT_FILES:
                source = self.root / name
                if source.is_file():
                    items.append((source, name))

            for dir_name in DATA_DIRS:
                source_dir = self.root / dir_name
                if not source_dir.is_dir():
                    continue
                for file_path in sorted(source_dir.rglob("*")):
                    if file_path.is_file():
                        items.append(
                            (
                                file_path,
                                file_path.relative_to(self.root).as_posix(),
                            )
                        )

            # Băm đúng luồng byte ghi vào zip: tệp state (vd
            # be_trailing_state.json) có thể được app đang chạy ghi lại giữa
            # lúc băm và lúc nén nếu băm trước ghi sau.
            entries: list[dict] = []
            zip_path = self._unique_zip_path(dest)
            tmp_zip = zip_path.with_name(f"{zip_path.name}.tmp")
            try:
                with zipfile.ZipFile(
                    tmp_zip, "w", zipfile.ZIP_DEFLATED
                ) as archive:
                    for source, relative in items:
                        sha256, size = self._write_entry(archive, source, relative)
                        entries.append(
                            {
                                "path": relative,
                                "sha256": sha256,
                                "size_bytes": size,
                            }
                        )
                    manifest = {
                        "created_at": _utc_now_iso(),
                        "database_migrations": database_migrations,
                        "entries": entries,
                    }
                    archive.writestr(
                        MANIFEST_NAME,
                        json.dumps(manifest, ensure_ascii=False, indent=2),
                    )
                tmp_zip.replace(zip_path)
            finally:
                if tmp_zip.exists():
                    tmp_zip.unlink()
            logger.info(
                "Backup: đã tạo %s (%d tệp, %d cảnh báo)",
                zip_path,
                len(entries),
                len(warnings),
            )
            self._apply_retention(dest)
            return BackupResult(
                zip_path=zip_path,
                manifest=manifest,
                warnings=tuple(warnings),
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _snapshot_database(self, source: Path, target: Path) -> None:
        """Snapshot nhất quán qua SQLite — an toàn WAL khi DB đang được ghi."""

        conn = sqlite3.connect(source, timeout=SQLITE_TIMEOUT_SECONDS)
        try:
            conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            conn.execute("VACUUM INTO ?", (str(target),))
        finally:
            conn.close()

    def _write_entry(self, archive: zipfile.ZipFile, source: Path,
                     relative: str) -> tuple[str, int]:
        """Gói tệp vào zip đồng thời băm chính xác byte đã ghi."""

        digest = hashlib.sha256()
        size = 0
        with archive.open(relative, "w", force_zip64=True) as target:
            with source.open("rb") as handle:
                while True:
                    chunk = handle.read(_HASH_CHUNK)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                    target.write(chunk)
        return digest.hexdigest(), size

    def _unique_zip_path(self, dest: Path) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        candidate = dest / f"{BACKUP_PREFIX}{stamp}.zip"
        counter = 2
        while candidate.exists():
            candidate = dest / f"{BACKUP_PREFIX}{stamp}-{counter}.zip"
            counter += 1
        return candidate

    def _apply_retention(self, dest: Path) -> None:
        # Sắp theo mtime, không theo tên: hậu tố cùng phút (-2, -3…) làm
        # thứ tự tên lệch thứ tự thời gian.
        backups = sorted(
            dest.glob(f"{BACKUP_PREFIX}*.zip"),
            key=lambda path: path.stat().st_mtime_ns,
        )
        for stale in backups[: max(0, len(backups) - RETENTION_KEEP)]:
            try:
                stale.unlink()
                logger.info("Backup: dọn thế hệ cũ %s", stale)
            except OSError:
                logger.warning("Backup: không dọn được %s", stale)

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def validate_backup(self, zip_path: Path) -> ValidationResult:
        """Kiểm tra manifest + SHA-256 từng tệp; sai → từ chối kèm lý do."""

        zip_path = Path(zip_path)
        if not zip_path.is_file():
            return ValidationResult(ok=False, errors=(f"Không tìm thấy {zip_path}.",))
        errors: list[str] = []
        manifest: dict | None = None
        try:
            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
                if MANIFEST_NAME not in names:
                    return ValidationResult(
                        ok=False,
                        errors=("Gói thiếu manifest.json — không phải bản sao lưu của app.",),
                    )
                manifest = json.loads(archive.read(MANIFEST_NAME))
                entries = manifest.get("entries", [])
                if not entries:
                    return ValidationResult(
                        ok=False, errors=("Gói rỗng — không có dữ liệu nào.",)
                    )
                for entry in entries:
                    rel = str(entry.get("path", ""))
                    if not rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
                        errors.append(f"Đường dẫn lạ trong gói: {rel!r}")
                        continue
                    if rel not in names:
                        errors.append(f"Thiếu tệp trong gói: {rel}")
                        continue
                    data = archive.read(rel)
                    if len(data) != entry.get("size_bytes", -1):
                        errors.append(f"Sai kích thước: {rel}")
                    if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                        errors.append(f"Sai SHA-256 (tệp hỏng): {rel}")
        except (zipfile.BadZipFile, json.JSONDecodeError) as exc:
            return ValidationResult(ok=False, errors=(f"Gói không đọc được: {exc}",))
        if errors:
            return ValidationResult(ok=False, errors=tuple(errors), manifest=manifest)
        return ValidationResult(ok=True, manifest=manifest)

    # ------------------------------------------------------------------
    # Restore — stage (trong app) + apply (lúc khởi động)
    # ------------------------------------------------------------------

    def stage_restore(self, zip_path: Path) -> StageResult:
        """Validate, sao lưu an toàn bản hiện tại, giải nén vào thư mục chờ.

        Sau bước này app phải khởi động lại; ``apply_pending_restore`` (điểm
        gọi duy nhất: khởi động trong ``main.py``) mới thay dữ liệu thật.
        """

        validation = self.validate_backup(zip_path)
        if not validation.ok:
            return StageResult(
                ok=False,
                errors=validation.errors,
                message="Gói sao lưu không hợp lệ — chưa thay đổi gì.",
            )

        safety_backup: Path | None = None
        if self._has_user_data():
            safety_backup = self.create_backup().zip_path
            logger.info("Restore: bản an toàn trước phục hồi — %s", safety_backup)

        pending = self.root / PENDING_DIR
        if pending.exists():
            shutil.rmtree(pending)
        pending.mkdir(parents=True)
        with zipfile.ZipFile(Path(zip_path)) as archive:
            archive.extractall(pending)
        atomic_request = {
            "source_zip": str(Path(zip_path)),
            "safety_backup": str(safety_backup) if safety_backup else None,
            "created_at": _utc_now_iso(),
        }
        request_file = pending / REQUEST_NAME
        temporary = request_file.with_name(f"{request_file.name}.tmp")
        temporary.write_text(
            json.dumps(atomic_request, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(request_file)
        return StageResult(
            ok=True,
            staging_dir=pending,
            safety_backup=safety_backup,
            message=(
                "Đã chuẩn bị phục hồi. Khởi động lại app để áp dụng "
                "(dữ liệu hiện tại đã được sao lưu an toàn)."
            ),
        )

    def _has_user_data(self) -> bool:
        return any(
            (self.root / name).exists()
            for name in (*DATABASES, *ROOT_FILES, *DATA_DIRS)
        )

    def apply_pending_restore(self) -> ApplyResult:
        """Áp dụng thư mục chờ nếu marker tồn tại; không marker → không làm gì.

        Điểm gọi duy nhất: khởi động app, trước khi bất kỳ service nào mở DB.
        Dữ liệu staged được kiểm tra SHA-256 lại theo manifest trước khi áp
        (chống hỏng giữa stage và apply — fail-closed: sai thì không áp, giữ
        nguyên thư mục chờ để truy vết).
        """

        pending = self.root / PENDING_DIR
        request_file = pending / REQUEST_NAME
        if not request_file.is_file():
            return ApplyResult(applied=False)

        try:
            request = json.loads(request_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Restore: marker không đọc được (%s)", exc)
            return ApplyResult(applied=False, errors=(str(exc),))

        manifest_path = pending / MANIFEST_NAME
        if not manifest_path.is_file():
            logger.error("Restore: thiếu manifest trong thư mục chờ")
            return ApplyResult(applied=False, errors=("missing-manifest",))
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return ApplyResult(applied=False, errors=(f"manifest: {exc}",))

        errors: list[str] = []
        entries = manifest.get("entries", [])
        for entry in entries:
            staged = pending / str(entry.get("path", ""))
            if not staged.is_file():
                errors.append(f"Thiếu tệp đã staged: {entry.get('path')}")
                continue
            sha256, _ = _sha256_of(staged)
            if sha256 != entry.get("sha256"):
                errors.append(f"Tệp staged hỏng: {entry.get('path')}")
        if errors:
            logger.error(
                "Restore: staged không nguyên vẹn, KHÔNG áp — %s", "; ".join(errors)
            )
            return ApplyResult(
                applied=False,
                safety_backup=self._request_safety_backup(request),
                errors=tuple(errors),
            )

        # Thư mục dữ liệu được thay nguyên thư mục (bằng chứng scan là một
        # tập gắn với nhau); tệp ở gốc được thay từng tệp.
        applied_dirs: set[str] = set()
        applied_files = 0
        for entry in entries:
            rel = Path(str(entry.get("path", "")))
            top = rel.parts[0] if rel.parts else ""
            staged = pending / rel
            if top in DATA_DIRS:
                if top in applied_dirs:
                    continue
                applied_dirs.add(top)
                target_dir = self.root / top
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.move(str(pending / top), str(target_dir))
                applied_files += 1
                continue
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(target)
            # DB thay bằng file mới → sidecar WAL/SHM của bản cũ phải đi cùng,
            # nếu không SQLite sẽ replay WAL cũ lên DB mới.
            if top in DATABASES:
                for suffix in ("-wal", "-shm"):
                    sidecar = self.root / f"{top}{suffix}"
                    if sidecar.exists():
                        sidecar.unlink()
            applied_files += 1

        shutil.rmtree(pending, ignore_errors=True)
        safety_backup = self._request_safety_backup(request)
        logger.info(
            "Restore: đã áp dụng %d mục từ %s (bản an toàn: %s)",
            applied_files,
            request.get("source_zip"),
            safety_backup,
        )
        return ApplyResult(
            applied=True,
            safety_backup=safety_backup,
            applied_files=applied_files,
        )

    def _request_safety_backup(self, request: dict) -> Path | None:
        raw = request.get("safety_backup")
        return Path(raw) if raw else None
