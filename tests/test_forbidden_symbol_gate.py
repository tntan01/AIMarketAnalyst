"""Static forbidden-symbol gates for the SMC single-runtime migration.

Bước 29: no production/runtime module may reintroduce a legacy/shadow SMC
scorer, mode selector or version literal. The Phase-8 rollout shadow symbols
are equally forbidden: the rollout stage ladder was removed on 2026-08-15
(fully live) and must never be reintroduced.
"""

from __future__ import annotations

import re
from pathlib import Path


_REPO = Path(__file__).resolve().parent.parent
_SCANNED_DIRS = (
    "core",
    "controllers",
    "services",
    "config",
    "ui",
    "workers",
    "scripts",
)

_FORBIDDEN_PATTERN = re.compile(
    r"SMC_MODE_LEGACY"
    r"|SMC_MODE_SHADOW"
    r"|SMC_SHADOW_BASELINE_VERSION"
    r"|SMC_V2_SHADOW_ONLY"
    r"|SMC_SHADOW_COMPARISON"
    r"|smc_quality_score"
    r"|score_smc_v2"
    r"|smc_scorer_v2"
    r"|smc_scoring_mode"
    r"|smc-v1"
)

_REMOVED_ROLLOUT_SYMBOLS = (
    "ROLLOUT_SHADOW",
    "SHADOW_MODE_ORDER_SUPPRESSED",
)


def _runtime_files() -> list[Path]:
    files: list[Path] = []
    for directory in _SCANNED_DIRS:
        root = _REPO / directory
        if not root.is_dir():
            continue
        files.extend(path for path in root.rglob("*.py") if path.is_file())
    return files


def test_forbidden_smc_legacy_shadow_symbols_are_absent() -> None:
    offenders: list[str] = []
    for path in _runtime_files():
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if _FORBIDDEN_PATTERN.search(line):
                offenders.append(f"{path.relative_to(_REPO)}:{line_number}")
    assert not offenders, (
        "SMC legacy/shadow scorer symbols must not exist in runtime code: "
        + ", ".join(offenders)
    )


def test_generic_scanner_rollout_shadow_symbols_are_removed() -> None:
    # The Phase-8 rollout stage ladder was removed on 2026-08-15 (fully live):
    # its shadow order-suppression symbols must not reappear in runtime code.
    offenders: list[str] = []
    for path in _runtime_files():
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            for symbol in _REMOVED_ROLLOUT_SYMBOLS:
                if symbol in line:
                    offenders.append(
                        f"{path.relative_to(_REPO)}:{line_number}:{symbol}"
                    )
    assert not offenders, (
        "removed rollout shadow symbols must not reappear in runtime code: "
        + ", ".join(offenders)
    )
