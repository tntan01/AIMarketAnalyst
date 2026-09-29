"""Cổng E2 của miền Tin tức (lô L4.1) — bốn phần (a)(b)(c)(d) của contract §9.2 + §14.

Cổng này là **cơ chế cưỡng chế tự động** cho ranh giới cứng §9.2 ("AI chỉ là
nhận định cho người dùng tham khảo — không tham gia vào BẤT KỲ quy trình nào")
và cho chiều phụ thuộc L1 (`ui → controllers → core ← services`). Luật không có
cơ chế tự động chỉ là khuyến cáo (architecture-rules E2), nên mỗi phần đều có
hai loại test: (1) khẳng định cổng **XANH** trên cây code hiện hành, và (2) dựng
một vi phạm **giả** (trên chuỗi nguồn / gói tạm trong `tmp_path` — KHÔNG đụng
file thật) để khẳng định cổng **BẮT ĐƯỢC** vi phạm. Nhóm thứ hai là bằng chứng
máy-đọc rằng cổng có hiệu lực, không phải test rỗng.

Bốn phần:

* **(a) Cách ly verdict AI** — mọi mô-đun `.py` trong `core/`, `services/`,
  `controllers/`, `workers/`, `ui/` **trừ** danh sách cho phép
  (`news_controller`, `news_screen`, `news_repository`) không được import
  `trend_verdict_parser`, không được gọi `verdicts_for`, không được truy vấn SQL
  tới `ai_trend_verdicts`. Theo "Làm rõ thực thi" của lô: việc
  `core/news_models.py` **khai báo mô hình** `TrendVerdict` là hợp lệ, và nhắc
  tên bảng/mô hình trong docstring/comment **không** tính vi phạm — cổng chỉ
  tính import, lời gọi và chuỗi SQL thật ở vị trí code.
* **(b) Chiều phụ thuộc** — chạy cổng THẬT `lint-imports` trên `.importlinter`
  (phạm vi tối thiểu 8 mô-đun `core/` của miền, B6). Thiếu công cụ là **ĐỎ kèm
  hướng dẫn cài**, tuyệt đối không skip im lặng (B4 fail-closed, QĐ-6).
* **(c) Chuỗi hiển thị** — các mô-đun `core/` của miền không có **string literal
  tiếng Việt ở vị trí code** (L3: phép tính trả giá trị + nhãn enum, tầng trình
  bày mới sinh chuỗi cho người đọc). Docstring/comment tiếng Việt là hợp lệ.
* **(d) Cách ly tín hiệu lợi suất trái phiếu (đợt 5)** — mọi mô-đun `.py` trong
  5 thư mục sản xuất **trừ** chủ sở hữu (`bond_yield_producer`, `news_controller`,
  `news_repository`) không được import `bond_yield_producer` hay truy vấn SQL
  tới bảng `bond_yields` (§9.2 + §13 đợt 5 — tín hiệu dữ liệu, đọc qua hợp đồng
  repository). Docstring/comment nhắc tên bảng/mô hình không tính vi phạm.
"""

from __future__ import annotations

import ast
import configparser
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- (a) cách ly verdict ----------------------------------------------------------

# Danh sách cho phép của contract §9.2: màn Quản lý tin là bên tiêu thụ DUY NHẤT
# của lịch sử verdict (`verdicts_for`), đi qua controller + repository của miền.
VERDICT_ALLOWED_MODULE_STEMS = frozenset({"news_controller", "news_screen", "news_repository"})

SCAN_DIRECTORIES = ("core", "services", "controllers", "workers", "ui")

FORBIDDEN_PARSER_MODULE = "trend_verdict_parser"
FORBIDDEN_VERDICT_CALL = "verdicts_for"
FORBIDDEN_VERDICT_TABLE = "ai_trend_verdicts"

# --- (d) cách ly tín hiệu lợi suất trái phiếu (đợt 5) ------------------------------

# contract §9.2 + §13 đợt 5: `bond_yields` là TÍN HIỆU dữ liệu (không phải verdict).
# Mô-đun sản xuất duy nhất là `bond_yield_producer`; bên tiêu thụ đọc qua hợp đồng
# `NewsRepository` (S1/S6).  Không mô-đun scoring/gate/alert/producer nào khác được
# import producer hay tự truy vấn SQL bảng `bond_yields`.
FORBIDDEN_BOND_PRODUCER = "bond_yield_producer"
FORBIDDEN_BOND_TABLE = "bond_yields"
# Nơi hợp lệ để IMPORT producer: chính nó + controller (dựng producer theo DI).
BOND_IMPORT_ALLOWED_STEMS = frozenset({"bond_yield_producer", "news_controller"})
# Nơi hợp lệ để chứa SQL bảng `bond_yields`: repository — điểm truy cập duy nhất (§8).
BOND_SQL_ALLOWED_STEMS = frozenset({"news_repository"})

# --- (b) chiều phụ thuộc ----------------------------------------------------------

IMPORTLINTER_CONFIG = REPO_ROOT / ".importlinter"
IMPORTLINTER_CONTRACT_ID = "news-core-independence"
INSTALL_HINT = "pip install -r requirements.txt   # import-linter>=2.0"

# --- (c) chuỗi hiển thị -----------------------------------------------------------

# Các mô-đun `core/` của miền Tin tức (news_*, rate_trend, trend_*, yield_context,
# pair_bias) — đối tượng bị cổng (b)(c) soi. Trùng khớp `source_modules` của
# `.importlinter`.
NEWS_CORE_MODULES = (
    "core/news_policy.py",
    "core/news_models.py",
    "core/news_freshness.py",
    "core/rate_trend.py",
    "core/trend_prompt_builder.py",
    "core/trend_verdict_parser.py",
    "core/yield_context.py",
    "core/pair_bias.py",
)


# ---- helpers (thuần: nhận chuỗi nguồn ⇒ chạy được cả trên cây thật lẫn fixture) ---


def _parse(source: str) -> ast.AST:
    """Parse một chuỗi nguồn cho cổng này.

    Vài mô-đun di sản chứa escape sequence không hợp lệ trong literal (ví dụ
    ``core/final_score.py``) — CPython chỉ *cảnh báo* khi biên dịch, không phải
    lỗi cú pháp, và không liên quan tới phép soi ở đây, nên cảnh báo đó được
    tắt cho gọn output battery (lỗi cú pháp THẬT vẫn ném ra nguyên vẹn).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        warnings.simplefilter("ignore", DeprecationWarning)
        return ast.parse(source)


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """Id của các ``Constant`` là docstring (câu lệnh đầu của module/class/hàm)."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _called_name(node: ast.Call) -> str | None:
    """Tên hàm/method của một lời gọi (``repo.verdicts_for(...)`` ⇒ ``verdicts_for``)."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _verdict_isolation_findings(source: str, where: str = "<source>") -> list[str]:
    """Phát hiện của MỘT mô-đun theo §9.2(a); danh sách rỗng = đạt cổng.

    Chỉ tính code thật: import mô-đun thẩm quyền của verdict, lời gọi
    ``verdicts_for`` và chuỗi SQL chạm bảng ``ai_trend_verdicts``. Docstring/comment
    nhắc tên bảng/mô hình không tính (plan L4.1 "Làm rõ thực thi").
    """
    tree = _parse(source)
    docstrings = _docstring_constant_ids(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and FORBIDDEN_PARSER_MODULE in node.module.split("."):
                findings.append(f"{where}:{node.lineno}: import {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if FORBIDDEN_PARSER_MODULE in alias.name.split("."):
                    findings.append(f"{where}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.Call):
            if _called_name(node) == FORBIDDEN_VERDICT_CALL:
                findings.append(f"{where}:{node.lineno}: call {FORBIDDEN_VERDICT_CALL}()")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            if FORBIDDEN_VERDICT_TABLE in node.value:
                findings.append(f"{where}:{node.lineno}: SQL chạm {FORBIDDEN_VERDICT_TABLE}")
    return findings


def _bond_signal_findings(
    source: str,
    where: str = "<source>",
    *,
    allow_import: bool = False,
    allow_sql: bool = False,
) -> list[str]:
    """Phát hiện của MỘT mô-đun theo §9.2(d) (đợt 5); rỗng = đạt cổng.

    Chỉ tính code thật: import mô-đun thẩm quyền ``bond_yield_producer`` và chuỗi SQL
    chạm bảng ``bond_yields``.  Docstring/comment nhắc tên bảng/mô hình không tính.
    ``allow_import``/``allow_sql`` bật cho đúng chủ sở hữu (producer/controller,
    repository)."""
    tree = _parse(source)
    docstrings = _docstring_constant_ids(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and FORBIDDEN_BOND_PRODUCER in node.module.split("."):
                if not allow_import:
                    findings.append(f"{where}:{node.lineno}: import {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if FORBIDDEN_BOND_PRODUCER in alias.name.split("."):
                    if not allow_import:
                        findings.append(f"{where}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            if FORBIDDEN_BOND_TABLE in node.value and not allow_sql:
                findings.append(f"{where}:{node.lineno}: SQL chạm {FORBIDDEN_BOND_TABLE}")
    return findings


def _vietnamese_code_literal_findings(source: str, where: str = "<source>") -> list[str]:
    """String literal tiếng Việt ở VỊ TRÍ CODE của một mô-đun; rỗng = đạt cổng.

    Docstring không tính (docstring tiếng Việt trong ``core/`` là hợp lệ — plan
    L4.1 "Làm rõ thực thi"); comment không phải node AST nên tự nhiên không tính.
    """
    tree = _parse(source)
    docstrings = _docstring_constant_ids(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            if any(ord(character) > 127 for character in node.value):
                findings.append(f"{where}:{node.lineno}: {node.value[:40]!r}")
    return findings


def _production_modules() -> list[Path]:
    """Mọi mô-đun `.py` trong 5 thư mục sản xuất của contract §9.2(a)."""
    modules: list[Path] = []
    for directory in SCAN_DIRECTORIES:
        modules.extend(sorted((REPO_ROOT / directory).rglob("*.py")))
    return modules


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


class ImportLinterMissingError(RuntimeError):
    """Cổng (b) không chạy được vì thiếu công cụ — fail-closed (B4, QĐ-6)."""


def _lint_imports_command() -> list[str]:
    """Lệnh chạy cổng (b) thật; thiếu công cụ ⇒ raise kèm hướng dẫn cài (B4)."""
    executable = shutil.which("lint-imports")
    if executable:
        return [executable]
    scripts_dir = Path(sys.executable).parent / ("Scripts" if os.name == "nt" else "bin")
    for candidate_name in ("lint-imports.exe", "lint-imports"):
        candidate = scripts_dir / candidate_name
        if candidate.exists():
            return [str(candidate)]
    raise ImportLinterMissingError(
        f"Thiếu import-linter để chạy cổng E2 phần (b). Cài bằng: {INSTALL_HINT}"
    )


def _run_lint_imports(config_name: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Chạy `lint-imports` THẬT trên một config; `--no-cache` để không sinh rác."""
    return subprocess.run(
        [*_lint_imports_command(), "--config", config_name, "--no-cache", "--no-logo"],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )


def _configured_source_modules(path: Path) -> set[str]:
    """`source_modules` khai trong hợp đồng của `.importlinter`."""
    parser = configparser.ConfigParser()
    parser.read_string(path.read_text(encoding="utf-8"))
    raw = parser[f"importlinter:contract:{IMPORTLINTER_CONTRACT_ID}"]["source_modules"]
    return {line.strip() for line in raw.splitlines() if line.strip()}


# --- nguồn giả dùng cho các test chứng minh cổng bắt được vi phạm -------------------

FAKE_PARSER_IMPORT_SOURCE = '''\
from core.trend_verdict_parser import parse_trend_verdict


def route(answer):
    return parse_trend_verdict(answer)
'''

FAKE_VERDICTS_FOR_CALL_SOURCE = '''\
def history(repo, scope_value):
    return repo.verdicts_for("pair", scope_value, 5)
'''

FAKE_VERDICT_SQL_SOURCE = '''\
QUERY = "SELECT * FROM ai_trend_verdicts ORDER BY created_at DESC"
'''

FAKE_DOCSTRING_MENTION_SOURCE = '''\
"""Mo dun chi nhac ten ai_trend_verdicts va verdicts_for trong van xuoi."""


def noop():
    """Docstring nhac ai_trend_verdicts: hop le, khong tinh vi pham."""
    return None
'''

FAKE_VIETNAMESE_CODE_STRING_SOURCE = '''\
def label():
    return "Chưa cấu hình AI Provider hoặc API key trong Settings."
'''

FAKE_VIETNAMESE_DOCSTRING_SOURCE = '''\
"""Mô-đun thuần: trả nhãn enum, không sinh chuỗi cho người đọc."""


def value():
    """Docstring tiếng Việt hợp lệ — chuỗi hiển thị mới là vi phạm (L3)."""
    return "scheduled"
'''

FAKE_BOND_IMPORT_SOURCE = '''\
from services.news_producers.bond_yield_producer import BondYieldProducer


def route(producer):
    return producer.fetch_round()
'''

FAKE_BOND_SQL_SOURCE = '''\
QUERY = "SELECT * FROM bond_yields ORDER BY observed_at DESC"
'''

FAKE_BOND_DOCSTRING_SOURCE = '''\
"""Mô dun chi nhac ten bond_yields trong van xuoi - hop le, khong tinh vi pham."""


def noop():
    """Docstring nhac bond_yields: hop le."""
    return None
'''


# ---- (a) cách ly verdict AI -------------------------------------------------------


class TestVerdictIsolationGate:
    def test_current_tree_isolates_the_ai_verdict(self):
        findings: list[str] = []
        for path in _production_modules():
            if path.stem in VERDICT_ALLOWED_MODULE_STEMS:
                continue
            findings.extend(
                _verdict_isolation_findings(path.read_text(encoding="utf-8"), _relative(path))
            )
        assert findings == [], findings

    def test_scan_covers_the_review_modules(self):
        """Điểm review của lô: cổng không bỏ sót `dashboard_screen`/`scanner_*`/`telegram_*`."""
        scanned = {_relative(path) for path in _production_modules()}
        for expected in (
            "ui/screens/dashboard_screen.py",
            "ui/screens/scanner_screen.py",
            "ui/screens/scanner_detail_screen.py",
            "services/telegram_alert_service.py",
        ):
            assert expected in scanned, expected

    def test_allowlist_is_exactly_the_verdict_consumers(self):
        """Allowlist không được rộng hơn thực tế — rộng hơn là cổng bị vô hiệu."""
        touching = {
            path.stem
            for path in _production_modules()
            if _verdict_isolation_findings(path.read_text(encoding="utf-8"), _relative(path))
        }
        assert touching == set(VERDICT_ALLOWED_MODULE_STEMS)

    def test_gate_flags_a_parser_import(self):
        findings = _verdict_isolation_findings(FAKE_PARSER_IMPORT_SOURCE, "fake/dashboard.py")
        assert findings and "trend_verdict_parser" in findings[0]

    def test_gate_flags_a_verdicts_for_call(self):
        findings = _verdict_isolation_findings(FAKE_VERDICTS_FOR_CALL_SOURCE, "fake/gate.py")
        assert findings and "verdicts_for" in findings[0]

    def test_gate_flags_a_query_on_the_verdict_table(self):
        findings = _verdict_isolation_findings(FAKE_VERDICT_SQL_SOURCE, "fake/alert.py")
        assert findings and FORBIDDEN_VERDICT_TABLE in findings[0]

    def test_prose_mentions_are_not_violations(self):
        """Khai báo mô hình + docstring nhắc tên bảng là hợp lệ (Làm rõ thực thi)."""
        assert _verdict_isolation_findings(FAKE_DOCSTRING_MENTION_SOURCE) == []
        for module in NEWS_CORE_MODULES:
            source = (REPO_ROOT / module).read_text(encoding="utf-8")
            assert _verdict_isolation_findings(source, module) == [], module


# ---- (d) cách ly tín hiệu lợi suất trái phiếu (đợt 5) ------------------------------


class TestBondYieldSignalGate:
    def test_current_tree_isolates_the_bond_yield_signal(self):
        findings: list[str] = []
        for path in _production_modules():
            findings.extend(
                _bond_signal_findings(
                    path.read_text(encoding="utf-8"),
                    _relative(path),
                    allow_import=path.stem in BOND_IMPORT_ALLOWED_STEMS,
                    allow_sql=path.stem in BOND_SQL_ALLOWED_STEMS,
                )
            )
        assert findings == [], findings

    def test_allowlist_is_exactly_the_bond_signal_owners(self):
        """Chỉ producer/controller import producer và chỉ repository chạm SQL bảng."""
        touching = {
            path.stem
            for path in _production_modules()
            if _bond_signal_findings(path.read_text(encoding="utf-8"), _relative(path))
        }
        assert touching <= (BOND_IMPORT_ALLOWED_STEMS | BOND_SQL_ALLOWED_STEMS), touching

    def test_gate_flags_a_producer_import(self):
        findings = _bond_signal_findings(FAKE_BOND_IMPORT_SOURCE, "fake/gate.py")
        assert findings and FORBIDDEN_BOND_PRODUCER in findings[0]

    def test_gate_flags_a_query_on_the_bond_table(self):
        findings = _bond_signal_findings(FAKE_BOND_SQL_SOURCE, "fake/alert.py")
        assert findings and FORBIDDEN_BOND_TABLE in findings[0]

    def test_prose_mentions_are_not_violations(self):
        """Producer/repository (chủ sở hữu) + docstring nhắc tên bảng là hợp lệ."""
        assert _bond_signal_findings(FAKE_BOND_DOCSTRING_SOURCE) == []
        for module in (
            "core/news_models.py",
            "services/news_producers/bond_yield_producer.py",
            "services/news_repository.py",
        ):
            source = (REPO_ROOT / module).read_text(encoding="utf-8")
            stem = Path(module).stem
            assert _bond_signal_findings(
                source,
                module,
                allow_import=stem in BOND_IMPORT_ALLOWED_STEMS,
                allow_sql=stem in BOND_SQL_ALLOWED_STEMS,
            ) == [], module


# ---- (b) chiều phụ thuộc (import-linter thật) -------------------------------------


FAKE_PROBE_CONTRACT = """\
[importlinter]
root_packages =
{root_packages}

[importlinter:contract:{contract_id}]
name = probe contract
type = forbidden
source_modules =
{fake_source_modules}
forbidden_modules =
{fake_forbidden_modules}
"""


def _write_probe_package(root: Path, *, violating: bool) -> Path:
    """Gói giả trong tmp_path: `fakecore.thing` tuỳ chọn import lớp ngoài."""
    (root / "fakecore").mkdir()
    (root / "fakeservices").mkdir()
    (root / "fakecore" / "__init__.py").write_text("", encoding="utf-8")
    (root / "fakeservices" / "__init__.py").write_text("", encoding="utf-8")
    (root / "fakeservices" / "helper.py").write_text(
        "def helper():\n    return 1\n", encoding="utf-8"
    )
    body = (
        "from fakeservices import helper\n\n\ndef use():\n    return helper()\n"
        if violating
        else "def use():\n    return 1\n"
    )
    (root / "fakecore" / "thing.py").write_text(body, encoding="utf-8")
    config = FAKE_PROBE_CONTRACT.format(
        root_packages="    fakecore\n    fakeservices",
        contract_id=IMPORTLINTER_CONTRACT_ID,
        fake_source_modules="    fakecore.thing",
        fake_forbidden_modules="    fakeservices",
    )
    path = root / ".importlinter"
    path.write_text(config, encoding="utf-8")
    return path


class TestDependencyDirectionGate:
    def test_real_gate_keeps_the_news_core_independent(self):
        """Cổng THẬT trên cây code hiện hành: hợp đồng phải được KEPT (không rỗng)."""
        result = _run_lint_imports(IMPORTLINTER_CONFIG.name, REPO_ROOT)
        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert "1 kept, 0 broken" in output, output
        assert "News core must not depend on outer layers or PyQt6" in output, output

    def test_gate_flags_a_core_module_importing_an_outer_layer(self, tmp_path):
        """Vi phạm giả (gói tạm, không đụng file thật): core → services phải ĐỎ."""
        config = _write_probe_package(tmp_path, violating=True)

        result = _run_lint_imports(config.name, tmp_path)

        output = result.stdout + result.stderr
        assert result.returncode != 0, output
        assert "fakecore.thing is not allowed to import fakeservices" in output, output

    def test_gate_stays_green_on_the_same_fixture_without_the_import(self, tmp_path):
        """Đối chứng: cùng gói, bỏ import vi phạm ⇒ cổng xanh (đỏ ở trên là do vi phạm)."""
        config = _write_probe_package(tmp_path, violating=False)

        result = _run_lint_imports(config.name, tmp_path)

        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert "1 kept, 0 broken" in output, output

    def test_config_covers_every_news_core_module(self):
        """Phạm vi hợp đồng phủ hết mô-đun `core/` thuộc họ miền Tin tức."""
        listed = _configured_source_modules(IMPORTLINTER_CONFIG)
        assert listed == {f"core.{Path(module).stem}" for module in NEWS_CORE_MODULES}
        on_disk = {
            f"core.{path.stem}"
            for path in (REPO_ROOT / "core").glob("*.py")
            if path.stem.startswith(("news_", "trend_"))
            or path.stem in {"rate_trend", "yield_context", "pair_bias"}
        }
        assert listed == on_disk, on_disk

    def test_missing_gate_tool_fails_closed_with_install_hint(self, monkeypatch, tmp_path):
        """Thiếu công cụ ⇒ ĐỎ kèm hướng dẫn cài — không skip im lặng (B4, QĐ-6)."""
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))

        with pytest.raises(ImportLinterMissingError) as excinfo:
            _lint_imports_command()

        assert "requirements.txt" in str(excinfo.value)


# ---- (c) chuỗi hiển thị trong core/ ------------------------------------------------


class TestCoreDisplayStringGate:
    def test_news_core_modules_have_no_vietnamese_code_literals(self):
        findings: list[str] = []
        for module in NEWS_CORE_MODULES:
            source = (REPO_ROOT / module).read_text(encoding="utf-8")
            findings.extend(_vietnamese_code_literal_findings(source, module))
        assert findings == [], findings

    def test_gate_flags_a_vietnamese_code_literal(self):
        findings = _vietnamese_code_literal_findings(
            FAKE_VIETNAMESE_CODE_STRING_SOURCE, "core/rate_trend.py"
        )
        assert findings and "Chưa cấu hình" in findings[0]

    def test_vietnamese_docstrings_and_comments_are_legal(self):
        assert _vietnamese_code_literal_findings(FAKE_VIETNAMESE_DOCSTRING_SOURCE) == []
        # core/news_policy.py có docstring/comment tiếng Việt — vẫn phải xanh.
        policy_source = (REPO_ROOT / "core/news_policy.py").read_text(encoding="utf-8")
        assert not policy_source.isascii()  # có tiếng Việt trong docstring/comment
        assert _vietnamese_code_literal_findings(policy_source, "core/news_policy.py") == []
