"""Scanner PIT dataset collector/validator (Bước 09; target-only).

Mục 9B/9D — nền: khóa **schema** của một historical point-in-time (PIT) dataset
mà corpus của Bước 09 phải thoả, + bộ **loader/validator/collector** để loại
data thu về thành các contract đã khóa (``SafetyDataSource`` → ``audit_safety_data``,
``CalibrationInput`` → ``run_calibration``).

Đây KHÔNG phải module runtime: không nối vào live scanner, không tạo dual path,
không phát order. Đây là công cụ target-only cho phía owner/infra thu PIT data về
cho lần calibration sau, và để "báo chính xác schema/dữ liệu còn thiếu".

Discipline fail-closed (khớp DoR-9 / Mục 16):

* mọi snapshot phải có UTC aware timestamp + provenance + canonical
  input/output (symbol/side/regime/technical/setup/selected_side/candidate_status);
* mỗi category connectivity/data_freshness/spread/news/volatility phải khai
  availability ∈ {``valid``, ``missing``, ``unknown``}; ``valid`` phải kèm
  per-observation timestamp (`observed_at`) để chứng minh điểm-trong-thời-gian;
  ``missing``/``unknown`` → category bị xử lý `UNKNOWN`, **không bao giờ** giả thành
  normal/no-news/PASS;
* validator phát hiện duplicate (captured_at, symbol), timestamp tương lai,
  look-ahead leakage (outcome_observed_at < captured_at), provenance rỗng,
  naïvetime (thiếu tz);
* dataset manifest có version + SHA-256 digest cho phép tái hiện byte-reproducible;
* collector KHÔNG tự đặt threshold production và KHÔNG tự hạ minimum sample để
  chạy calibration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.scanner_calibration import (
    SCANNER_CALIBRATION_MANIFEST_VERSION,
    CalibrationInput,
    CalibrationManifest,
    CalibrationReport,
    run_calibration,
)
from core.scanner_safety_audit import (
    SAFETY_AUDIT_CATEGORIES,
    SafetyDataAuditReport,
    SafetyDataSource,
    audit_safety_data,
)

PIT_DATASET_VERSION = "scanner-pit-dataset"
PIT_DATASET_LEGACY_VERSION = "scanner-v4-pit-dataset-v1"
UTC = timezone.utc

VALID_AVAILABILITY = frozenset({"valid", "missing", "unknown"})
VALID_SIDES = frozenset({"buy", "sell"})

# The set of production values a calibration *would* target (declared, frozen).
# The collector never computes them; it only records the declared target list.
PIT_TARGET_THRESHOLDS_DECLARED = (
    "technical_floor",
    "setup_floor",
    "min_score_gap",
    "min_risk_reward",
    "spread_threshold_by_symbol",
    "candle_freshness_sla_minutes",
    "safety_volatility_upper_ratio",
    "macro_deadband_points",
    "macro_confidence_threshold",
    "macro_conflict_cap",
    "macro_unknown_cap",
    "ranking_weights_within_group",
)


# ---------------------------------------------------------------------------
# Normalized row model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CategoryObservation:
    """Per-category PIT observation inside one snapshot.

    ``availability == "valid"`` requires an ``observed_at`` timestamp so the
    observation is provably point-in-time.  ``missing``/``unknown`` are carried
    as-is and consumed downstream as ``UNKNOWN`` (fail-closed), never PASS.
    """

    availability: str
    source: str
    observed_at: datetime | None = None
    value: Any = None

    @property
    def is_pit_valid(self) -> bool:
        return self.availability == "valid" and self.observed_at is not None


@dataclass(frozen=True, slots=True)
class PitSnapshotRow:
    """One immutable PIT decision snapshot as gathered for calibration."""

    captured_at: datetime
    symbol: str
    regime: str
    side: str
    provenance: str
    categories: Mapping[str, CategoryObservation]
    technical_signal_score: int | None = None
    setup_score: int | None = None
    selected_side: str | None = None
    candidate_status: str | None = None
    outcome_r: float | None = None
    outcome_observed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PitDatasetValidation:
    version: str
    row_count: int
    issues: tuple[str, ...]
    categories_seen: Mapping[str, int]

    @property
    def clean(self) -> bool:
        return not self.issues


@dataclass(frozen=True, slots=True)
class PitDatasetEvidence:
    """Combined evidence for one gathered PIT corpus (audit + calibration + digest)."""

    dataset_version: str
    dataset_id: str
    validation: PitDatasetValidation
    audit: SafetyDataAuditReport
    calibration: CalibrationReport
    sha256: str

    def single_payload_dict(self) -> dict[str, object]:
        return {
            "dataset_version": self.dataset_version,
            "dataset_id": self.dataset_id,
            "validation": {
                "clean": self.validation.clean,
                "row_count": self.validation.row_count,
                "issues": list(self.validation.issues),
            },
            "audit": self.audit.to_dict(),
            "calibration": self.calibration.to_dict(),
            "sha256": self.sha256,
        }

    def to_dict(self) -> dict[str, object]:
        return self.single_payload_dict()


def _utc_aware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.utcoffset() is not None


def _coerce_category(raw: Any, *, category: str) -> CategoryObservation | None:
    """Coerce the raw category payload; ``None`` → the category is UNKNOWN."""
    if not isinstance(raw, dict):
        return CategoryObservation(availability="unknown", source=category)
    availability = raw.get("availability")
    if availability not in VALID_AVAILABILITY:
        availability = "unknown"
    source = raw.get("source") or category
    observed_raw = raw.get("observed_at")
    observed_at = None
    if observed_raw:
        try:
            dt = datetime.fromisoformat(str(observed_raw))
            if _utc_aware(dt):
                observed_at = dt.astimezone(UTC)
        except ValueError:
            observed_at = None
    return CategoryObservation(
        availability=availability,
        source=source,
        observed_at=observed_at,
        value=raw.get("value"),
    )


def _coerce_row(raw: Mapping[str, Any]) -> PitSnapshotRow:
    captured = datetime.fromisoformat(str(raw["captured_at_utc"]))
    outcome_raw = raw.get("outcome_r")
    outcome_observed_raw = raw.get("outcome_observed_at_utc")
    categories = {
        category: _coerce_category(raw.get(category), category=category)
        for category in SAFETY_AUDIT_CATEGORIES
    }
    return PitSnapshotRow(
        captured_at=captured,
        symbol=str(raw.get("symbol") or ""),
        regime=str(raw.get("regime") or ""),
        side=str(raw.get("side") or ""),
        provenance=str(raw.get("provenance") or ""),
        categories=categories,
        technical_signal_score=raw.get("technical_signal_score"),
        setup_score=raw.get("setup_score"),
        selected_side=raw.get("selected_side"),
        candidate_status=raw.get("candidate_status"),
        outcome_r=float(outcome_raw) if outcome_raw is not None else None,
        outcome_observed_at=(
            datetime.fromisoformat(str(outcome_observed_raw))
            if outcome_observed_raw
            else None
        ),
    )


def load_pit_dataset_jsonl(path: Path | str) -> tuple[PitSnapshotRow, ...]:
    """Load a JSONL corpus (one snapshot per line) into normalized rows."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    rows: list[PitSnapshotRow] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        rows.append(_coerce_row(json.loads(line)))
    return tuple(rows)


def validate_pit_rows(
    rows: tuple[PitSnapshotRow, ...],
    *,
    now: datetime | None = None,
) -> PitDatasetValidation:
    """Fail-closed validation: duplicates, future, look-ahead, identity gaps."""
    now = now if now is not None else datetime.now(UTC)
    issues: list[str] = []
    seen: set[tuple[datetime, str]] = set()

    for idx, row in enumerate(rows):
        anchor = f"row#{idx} {row.symbol}@{row.captured_at.isoformat()}"
        # Future / naive timestamp.
        if not _utc_aware(row.captured_at):
            issues.append(f"{anchor}: NAIVE_TIMESTAMP (captured_at must be tz-aware)")
        if _utc_aware(row.captured_at) and row.captured_at > now:
            issues.append(f"{anchor}: FUTURE_TIMESTAMP")
        # Duplicate.
        key = (row.captured_at, row.symbol)
        if key in seen:
            issues.append(f"{anchor}: DUPLICATE_SNAPSHOT (same captured_at+symbol)")
        seen.add(key)
        # Identity.
        if not row.symbol:
            issues.append(f"{anchor}: MISSING_SYMBOL")
        if row.side not in VALID_SIDES:
            issues.append(f"{anchor}: INVALID_SIDE (row.side={row.side!r})")
        if not row.regime:
            issues.append(f"{anchor}: MISSING_REGIME")
        if not row.provenance:
            issues.append(f"{anchor}: MISSING_PROVENANCE")
        # Look-ahead leakage (only comparable when both sides are tz-aware).
        if (
            row.outcome_observed_at is not None
            and _utc_aware(row.outcome_observed_at)
            and _utc_aware(row.captured_at)
            and row.outcome_observed_at.astimezone(UTC) < row.captured_at.astimezone(UTC)
        ):
            issues.append(f"{anchor}: LOOK_AHEAD_LEAK (outcome observed before decision)")
        # Per-category PIT integrity.
        for category in SAFETY_AUDIT_CATEGORIES:
            obs = row.categories.get(category)
            if obs is not None and obs.is_pit_valid is False:
                # A "valid" category without an observed_at is non-PIT.
                if obs.availability == "valid":
                    issues.append(f"{anchor}: {category} CATEGORY_NON_PIT (valid but no observed_at)")

    counts: dict[str, int] = {}
    for row in rows:
        for category in SAFETY_AUDIT_CATEGORIES:
            obs = row.categories.get(category)
            counts[f"{category}:{obs.availability if obs else 'unknown'}"] = (
                counts.get(f"{category}:{obs.availability if obs else 'unknown'}", 0) + 1
            )
    return PitDatasetValidation(
        version=PIT_DATASET_VERSION,
        row_count=len(rows),
        issues=tuple(issues),
        categories_seen=counts,
    )


# ---------------------------------------------------------------------------
# Manifest + evidence
# ---------------------------------------------------------------------------


def _payload_canonical(rows: tuple[PitSnapshotRow, ...]) -> str:
    entries: list[dict[str, Any]] = []
    for row in rows:
        entries.append(
            {
                "captured_at_utc": row.captured_at.astimezone(UTC).isoformat(),
                "symbol": row.symbol,
                "regime": row.regime,
                "side": row.side,
                "provenance": row.provenance,
                "categories": {
                    category: {
                        "availability": obs.availability,
                        "source": obs.source,
                        "observed_at": obs.observed_at.astimezone(UTC).isoformat()
                        if obs.observed_at is not None
                        else None,
                        "value": obs.value,
                    }
                    for category, obs in sorted(row.categories.items())
                },
                "technical_signal_score": row.technical_signal_score,
                "setup_score": row.setup_score,
                "selected_side": row.selected_side,
                "candidate_status": row.candidate_status,
                "outcome_r": row.outcome_r,
                "outcome_observed_at_utc": (
                    row.outcome_observed_at.astimezone(UTC).isoformat()
                    if row.outcome_observed_at is not None
                    else None
                ),
            }
        )
    # Deterministic order independent of input row order.
    entries.sort(
        key=lambda e: (str(e["captured_at_utc"]), str(e["symbol"]))
    )
    return json.dumps(entries, sort_keys=True, separators=(",", ":"))


def dataset_sha256(rows: tuple[PitSnapshotRow, ...]) -> str:
    return hashlib.sha256(_payload_canonical(rows).encode()).hexdigest()


def collect_safety_sources(
    rows: tuple[PitSnapshotRow, ...],
) -> tuple[SafetyDataSource, ...]:
    """Derive the five per-category PIT data sources as declared to the audit.

    A category source is emitted only when at least one row is PIT-valid for it;
    otherwise the category stays undeclared → audit reports ``MISSING``.
    ``point_in_time`` is True only when that category's observed timestamps are
    present on the eligible rows.
    """
    sources: list[SafetyDataSource] = []
    for category in SAFETY_AUDIT_CATEGORIES:
        eligible = [
            row
            for row in rows
            if (obs := row.categories.get(category)) is not None and obs.is_pit_valid
        ]
        if not eligible:
            continue
        times = sorted(row.captured_at for row in eligible if _utc_aware(row.captured_at))
        if not times:
            continue
        sources.append(
            SafetyDataSource(
                category=category,
                source=f"{category}:{PIT_DATASET_VERSION}",
                observed_from=times[0].astimezone(UTC),
                observed_to=times[-1].astimezone(UTC),
                point_in_time=True,
                provenance=f"collector:{PIT_DATASET_VERSION}",
                checked_at=datetime.now(UTC),
                sample_count=len(eligible),
            )
        )
    return tuple(sources)


def to_calibration_inputs(
    rows: tuple[PitSnapshotRow, ...],
) -> tuple[CalibrationInput, ...]:
    return tuple(
        CalibrationInput(
            observed_at=row.captured_at,
            symbol=row.symbol,
            regime=row.regime,
            side=row.side,
            candidate_status=row.candidate_status or "",
            outcome_r=row.outcome_r,
            technical_signal_score=row.technical_signal_score,
            setup_score=row.setup_score,
            risk_reward_ratio=None,
            seeded=False,
        )
        for row in rows
    )


def build_calibration_manifest(
    rows: tuple[PitSnapshotRow, ...],
    *,
    pit_boundary: datetime,
    minimum_required_rows: int,
) -> CalibrationManifest:
    """Versioned manifest keyed to the corpus digest (owner fixes the bars)."""
    digest = dataset_sha256(rows)
    return CalibrationManifest(
        manifest_version=SCANNER_CALIBRATION_MANIFEST_VERSION,
        dataset_id=f"pit-{digest[:12]}",
        pit_boundary=pit_boundary,
        minimum_required_rows=minimum_required_rows,
        thresholds_being_calibrated=_canonical_threshold_targets(),
    )


def _canonical_threshold_targets() -> tuple[str, ...]:
    # The manifest lives under the calibration harness; map the declared targets
    # to the subset that CalibrationManifest.thresholds_being_calibrated accepts.
    return (
        "technical_floor",
        "setup_floor",
        "min_score_gap",
        "min_risk_reward",
        "safety_volatility_upper_ratio",
        "macro_deadband_points",
    )


def run_pit_evidence(
    rows: tuple[PitSnapshotRow, ...],
    *,
    pit_boundary: datetime,
    minimum_required_rows: int,
    minimum_coverage_days: Mapping[str, int] | None = None,
    now: datetime | None = None,
) -> PitDatasetEvidence:
    """Full fail-closed evidence chain for one gathered corpus.

    Runs validation, maps to the safety audit and the calibration harness, and
    produces a digest.  It NEVER recommends production thresholds on its own —
    that is gated by ``minimum_required_rows`` + realized outcomes inside
    ``run_calibration`` (insufficient ⇒ every threshold is ``None``).
    """
    validation = validate_pit_rows(rows, now=now)
    sources = collect_safety_sources(rows)
    audit = audit_safety_data(
        sources,
        pit_boundary=pit_boundary,
        minimum_required=minimum_coverage_days,
    )
    manifest = build_calibration_manifest(
        rows,
        pit_boundary=pit_boundary,
        minimum_required_rows=minimum_required_rows,
    )
    calibration = run_calibration(manifest, to_calibration_inputs(rows))
    digest = dataset_sha256(rows)
    return PitDatasetEvidence(
        dataset_version=PIT_DATASET_VERSION,
        dataset_id=manifest.dataset_id,
        validation=validation,
        audit=audit,
        calibration=calibration,
        sha256=digest,
    )


def requested_schema() -> dict[str, object]:
    """The exact row schema a gathered PIT corpus must satisfy (for reporting
    "schema/data còn thiếu")."""
    return {
        "dataset_version": PIT_DATASET_VERSION,
        "file_format": "jsonl — one snapshot per line",
        "required_top_level_fields": [
            "captured_at_utc",
            "symbol",
            "regime",
            "side",
            "selected_side",
            "technical_signal_score",
            "setup_score",
            "candidate_status",
            "outcome_r",
            "outcome_observed_at_utc",
            "provenance",
        ],
        "required_per_category_fields": [
            f"{category}.{{availability, source, observed_at, value}}"
            for category in SAFETY_AUDIT_CATEGORIES
        ],
        "availability_values": ["valid", "missing", "unknown"],
        "UTC": f"{PIT_DATASET_VERSION} requires aware UTC timestamps; every "
        "category availability==valid must carry observed_at to be provably PIT.",
        "identity": "symbol / side(buy|sell) / regime / provenance non-empty",
        "integrity": "no duplicate (captured_at_utc, symbol); no future "
        "timestamps; outcome_observed_at_utc >= captured_at_utc (no look-ahead)",
    }


# ---------------------------------------------------------------------------
# Forward collector: append-only PIT corpus for the NEXT calibration.
#
# This is observation infrastructure, NOT runtime — it never calls
# ``compose_scanner`` and never touches the live decision path.  A human /
# infra supplies each snapshot's raw fields via a configured provider; the
# collector FAIL-CLOSES on append (rejects duplicate / future / non-PIT /
# malformed), so a growing forward corpus always stays schema-clean.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ForwardCollectorConfig:
    """Owner-declared collection bars (the collector never picks them)."""

    corpus_path: str
    minimum_required_rows: int
    target_coverage_days: int
    pit_boundary: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "corpus_path": self.corpus_path,
            "minimum_required_rows": self.minimum_required_rows,
            "target_coverage_days": self.target_coverage_days,
            "pit_boundary": self.pit_boundary.astimezone(UTC).isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ForwardCollectorReport:
    """Current state of a growing forward PIT corpus vs the owner-set bars."""

    dataset_version: str
    config: dict[str, object]
    collected_rows: int
    missing_rows: int
    coverage_days: int
    missing_coverage_days: int
    corpus_digest_sha256: str
    validated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_version": self.dataset_version,
            "config": self.config,
            "collected_rows": self.collected_rows,
            "missing_rows": self.missing_rows,
            "coverage_days": self.coverage_days,
            "missing_coverage_days": self.missing_coverage_days,
            "corpus_digest_sha256": self.corpus_digest_sha256,
            "validated": self.validated,
        }


def _load_existing(corpus_path: str) -> tuple[PitSnapshotRow, ...]:
    path = Path(corpus_path)
    if not path.exists() or path.stat().st_size == 0:
        return ()
    return load_pit_dataset_jsonl(path)


def _row_to_raw(row: PitSnapshotRow) -> dict[str, Any]:
    """Serialize a normalized row back to the JSONL input shape (digest-stable)."""
    base: dict[str, Any] = {
        "captured_at_utc": row.captured_at.astimezone(UTC).isoformat(),
        "symbol": row.symbol,
        "regime": row.regime,
        "side": row.side,
        "provenance": row.provenance,
        "technical_signal_score": row.technical_signal_score,
        "setup_score": row.setup_score,
        "selected_side": row.selected_side,
        "candidate_status": row.candidate_status,
        "outcome_r": row.outcome_r,
        "outcome_observed_at_utc": (
            row.outcome_observed_at.astimezone(UTC).isoformat()
            if row.outcome_observed_at is not None
            else None
        ),
    }
    for category, obs in sorted(row.categories.items()):
        base[category] = {
            "availability": obs.availability,
            "source": obs.source,
            "observed_at": (
                obs.observed_at.astimezone(UTC).isoformat()
                if obs.observed_at is not None
                else None
            ),
            "value": obs.value,
        }
    return base


def init_forward_collector(cfg: ForwardCollectorConfig) -> str:
    """Ensure the forward corpus path exists (creates empty + parent dirs)."""
    path = Path(cfg.corpus_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    return str(path)


def forward_status(cfg: ForwardCollectorConfig, *, now: datetime | None = None) -> ForwardCollectorReport:
    return _forward_status(cfg, _load_existing(cfg.corpus_path), now)


def append_forward_snapshot(
    cfg: ForwardCollectorConfig,
    raw: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, tuple[str, ...], ForwardCollectorReport]:
    """Validate + append one snapshot.  Never records a row that has any issue."""
    now = now if now is not None else datetime.now(UTC)
    existing = _load_existing(cfg.corpus_path)
    try:
        new_row = _coerce_row(raw)
    except Exception:
        return (False, ("MALFORMED_SNAPSHOT",), _forward_status(cfg, existing, now))

    combined = tuple(existing) + (new_row,)
    validation = validate_pit_rows(combined, now=now)
    if not validation.clean:
        # Fail-closed: reject the row and leave the corpus byte-identical.
        return (False, validation.issues, _forward_status(cfg, existing, now))

    path = Path(cfg.corpus_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_row_to_raw(new_row), sort_keys=True) + "\n")
    return (True, (), _forward_status(cfg, combined, now))


def _forward_status(
    cfg: ForwardCollectorConfig,
    rows: tuple[PitSnapshotRow, ...],
    now: datetime | None = None,
) -> ForwardCollectorReport:
    validation = validate_pit_rows(rows, now=now)
    collected = len(rows)
    coverage = 0
    times = [r.captured_at for r in rows if _utc_aware(r.captured_at)]
    if times:
        coverage = max(0, (max(times) - min(times)).days)
    return ForwardCollectorReport(
        dataset_version=PIT_DATASET_VERSION,
        config=cfg.to_dict(),
        collected_rows=collected,
        missing_rows=max(0, cfg.minimum_required_rows - collected),
        coverage_days=coverage,
        missing_coverage_days=max(0, cfg.target_coverage_days - coverage),
        corpus_digest_sha256=dataset_sha256(rows),
        validated=validation.clean,
    )