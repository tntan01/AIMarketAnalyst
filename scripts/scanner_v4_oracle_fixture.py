"""Scanner V4 Bước 11 oracle fixture generator (reproducible; target-only).

Run:  python scripts/scanner_v4_oracle_fixture.py

Writes ``reports/scanner-v4/oracle_fixture_v4.json`` — a frozen, versioned V4
oracle for the locked Bước 07 canonical geometry (buy 76 / sell 32 / gap 44).
It is produced by the *real* modules and cross-checked against hand-written
``Fraction``/ROUND_HALF_UP reference functions, so the fixture doubles as a
byte-reproducible artifact for Bước 11 acceptance.

The report is deterministic: the only field that changes between runs is
``generated_at_utc``; a SHA-256 digest over the stable payload is stable.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.final_score_v4 import score_final_score
from core.scanner_v4_composition import COMPOSITION_POLICY_VERSION
from core.scanner_v4_models import SCANNER_V4_SCORING_VERSION
from core.scanner_v4_row import SCANNER_V4_ROW_VERSION
from core.scanner_v4_snapshot import SCANNER_V4_SNAPSHOT_ENVELOPE_VERSION
from core.scanner_v4_threshold_policy import SCANNER_V4_THRESHOLD_POLICY_VERSION
from core.technical_signal_scorer import TECHNICAL_COMPONENT_RAW_MAX
from tests.scanner_v4_testkit import (
    SELL,
    DEFAULT_THRESHOLD_POLICY,
    build_snapshot,
    canonical_smc,
    compose,
)

OUTPUT = PROJECT_ROOT / "reports" / "scanner-v4" / "oracle_fixture_v4.json"


def _round_half_up(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + int(remainder * 2 >= value.denominator)


def _ref_final(technical: int, evidence: int, execution: int) -> int:
    total = Fraction(65 * technical + 20 * evidence + 15 * execution, 100)
    return _round_half_up(min(Fraction(100, 1), max(Fraction(0, 1), total)))


def _ref_technical(side: str, raws: dict[str, int], *, smc_raw: int, regime: str) -> int:
    weights = {
        "trending_up": {"trend": 40, "momentum": 20, "location": 20, "smc": 20},
    }[regime]
    total = Fraction(0, 1)
    for component, raw in [("trend", raws["trend"]), ("momentum", raws["momentum"]), ("location", raws["location"])]:
        total += Fraction(raw * weights[component], TECHNICAL_COMPONENT_RAW_MAX[component])
    total += Fraction(smc_raw * weights["smc"], TECHNICAL_COMPONENT_RAW_MAX["smc"])
    return _round_half_up(min(Fraction(100, 1), max(Fraction(0, 1), total)))


def _build_report() -> dict[str, object]:
    smc = canonical_smc(buy_subtotal=12, sell_subtotal=7)
    snapshot = build_snapshot(source="live")  # buy 20/14/18 + 12, sell 8/5/6 + 7
    composition = compose(snapshot)

    buy = composition.canonical.side_scores[0]
    sell = composition.canonical.side_scores[1]

    # Independent reference oracle (never a copy of the module).
    ref_buy_tech = _ref_technical("buy", {"trend": 20, "momentum": 14, "location": 18}, smc_raw=12, regime="trending_up")
    ref_sell_tech = _ref_technical("sell", {"trend": 8, "momentum": 5, "location": 6}, smc_raw=7, regime="trending_up")
    ref_buy_setup = _ref_final(76, 60, 70)
    ref_sell_setup = _ref_final(32, 60, 70)

    stable = {
        "fixture": "scanner-v4-oracle-v1",
        "target_only": True,
        "scoring_version": SCANNER_V4_SCORING_VERSION,
        "composition_version": COMPOSITION_POLICY_VERSION,
        "row_version": SCANNER_V4_ROW_VERSION,
        "envelope_version": SCANNER_V4_SNAPSHOT_ENVELOPE_VERSION,
        "threshold_policy_version": SCANNER_V4_THRESHOLD_POLICY_VERSION,
        "threshold_policy_notes": DEFAULT_THRESHOLD_POLICY.certified(),
        "input": {
            "regime": "trending_up",
            "smc": {"buy_subtotal": 12, "sell_subtotal": 7},
            "buy": {"trend": 20, "momentum": 14, "location": 18, "evidence": 60, "execution": 70},
            "sell": {"trend": 8, "momentum": 5, "location": 6, "evidence": 60, "execution": 70},
        },
        "oracle_reference": {
            "buy_technical": ref_buy_tech,
            "sell_technical": ref_sell_tech,
            "buy_setup": ref_buy_setup,
            "sell_setup": ref_sell_setup,
            "gap": 44,
        },
        "module_output": {
            "buy_technical": buy.technical_signal_score,
            "sell_technical": sell.technical_signal_score,
            "buy_setup": buy.setup_score,
            "sell_setup": sell.setup_score,
            "selected_side": composition.decision.selected_side,
            "candidate_status": composition.decision.candidate_status,
            "score_gap": composition.decision.score_gap,
            "snapshot_id": composition.snapshot_id,
            "symbol": composition.symbol,
        },
    }

    stable_json = json.dumps(stable, indent=2, sort_keys=True)
    digest = hashlib.sha256(stable_json.encode("utf-8")).hexdigest()

    return {
        "schema": "scanner-v4-oracle-fixture",
        "generated_by": "scripts/scanner_v4_oracle_fixture.py",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "digest_sha256": digest,
        "oracle_matches_module": (
            ref_buy_tech == buy.technical_signal_score
            and ref_sell_tech == sell.technical_signal_score
            and ref_buy_setup == buy.setup_score
            and ref_sell_setup == sell.setup_score
            and composition.decision.score_gap == 44
        ),
        **stable,
    }


def main() -> None:
    report = _build_report()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT}")
    print(f"oracle_matches_module={report['oracle_matches_module']}")
    print(f"digest={report['digest_sha256']}")


if __name__ == "__main__":
    main()