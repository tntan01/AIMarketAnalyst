"""Scanner V4 release smoke (Bước 12, §12.4; target-only cutover check).

Run:  python scripts/scanner_v4_smoke.py

Drives the SINGLE release wiring against a deterministic canonical fixture and
produces ``reports/scanner-v4/release_b12_smoke.json``:

* one canonical V4 snapshot → ``compose_scanner_v4`` → row → candidate (via the
  locked DEFAULT threshold policy) → rank → filtered by selected-side setup;
* asserts a V3 artifact (a V3-versioned backtest/ledger envelope) is **rejected**
  — never V4-replayable, never fed into the decision path;
* records the exact version identity (scoring / features / output / safety /
  macro / snapshot / threshold / journal) and the routed status + reason codes.

The script is byte-reproducible: same fixture → same snapshot id / versions.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.scanner_v4_backtest_contract import (
    V3_AUDIT_ONLY_ARTIFACT_KIND,
    classify_backtest_artifact,
)
from core.scanner_v4_order_policy import load_runtime_order_policy
from core.scanner_v4_release import (
    DEFAULT_THRESHOLD_POLICY,
    SCANNER_V4_RELEASE_VERSION,
    grouped_pairs,
    rank_pairs,
    ready_pairs_above_setup,
    run_v4_pair,
    run_v4_pair_from_live,
)
from tests.scanner_v4_testkit import build_snapshot

NOW = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)
SAMPLE_SYMBOLS = ("XAUUSD", "EURUSD", "US30")
OUT_DIR = PROJECT_ROOT / "reports" / "scanner-v4"
OUT_PATH = OUT_DIR / "release_b12_smoke.json"


def _run() -> dict[str, object]:
    pairs = [
        run_v4_pair(
            build_snapshot(symbol=symbol, captured_at=NOW),
            now=NOW,
            entry_confirmation="confirmed",
        )
        for symbol in SAMPLE_SYMBOLS
    ]

    ranked = rank_pairs(pairs)
    grouped = grouped_pairs(pairs)
    ready = ready_pairs_above_setup(pairs)  # default setup floor 35

    # Order payloads must be INTENT ONLY — structurally locked sends_real_order=False.
    order_intents = []
    for p in ready:
        if p.candidate is not None and p.candidate.order_payload is not None:
            order_intents.append({
                "symbol": p.composition.symbol,
                "sends_real_order": p.candidate.order_payload.sends_real_order,
            })

    # §12.1 / §9C: a V3-versioned artifact is READ-ONLY audit, never replayable.
    v3_artifact = classify_backtest_artifact(
        {"candidate_ledger_version": "backtest-candidate-ledger-v1"}
    )

    ready_status = [p.row.selected_side for p in ready]
    grouped_statuses = {status: len(items) for status, items in grouped.items()}

    return {
        "smoke_version": SCANNER_V4_RELEASE_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "threshold_policy": DEFAULT_THRESHOLD_POLICY.to_dict(),
        "ranked_symbols": [p.composition.symbol for p in ranked],
        "ranked_statuses": [
            None if p.candidate is None else p.candidate.candidate_status
            for p in ranked
        ],
        "grouped_status_counts": grouped_statuses,
        "ready_above_default_setup_floor": ready_status,
        "ready_order_intents": order_intents,
        "default_v3_artifact": v3_artifact.to_dict(),
        "pairs": [p.to_dict() for p in pairs],
    }


def _assert_release_contract(report: dict[str, object]) -> None:
    assert report["threshold_policy"]["policy_version"] == "scanner-threshold-policy-v4"
    assert report["threshold_policy"]["technical_floor"] == 40
    assert report["threshold_policy"]["setup_floor"] == 35
    # V3 artifact must be audit-only (never V4-replayable).
    assert (
        report["default_v3_artifact"]["kind"] == V3_AUDIT_ONLY_ARTIFACT_KIND
    ), "a V3 artifact must never be V4-replayable"
    # Every pair must carry exact V4 identity end-to-end.
    for pair in report["pairs"]:
        row = pair["row"]
        assert row["composition_version"] == "scanner-composition-v4"
        assert row["scoring_version"] == "scanner-v4"
        assert row["feature_version"] == "scanner-features-v4"
    # Every ready candidate's order payload must be intent-only (never a real
    # order).  Under this canonical smoke fixture no candidate materializes a
    # real-order payload (all BLOCKED/DATA_UNAVAILABLE — nothing to dispatch);
    # whenever a payload IS produced it is structurally locked to
    # sends_real_order=False (the V4 cell always diffs False for real orders).
    for intent in report["ready_order_intents"]:
        assert intent["sends_real_order"] is False, (
            f"order payload for {intent['symbol']} must be intent, "
            f"sends_real_order=False"
        )
    assert len(report["ready_order_intents"]) == 0 or all(
        i["sends_real_order"] is False
        for i in report["ready_order_intents"]
    )


def _pathb_candles() -> tuple[list, list, list]:
    """Deterministic closed D1/H4/H1 candle fixture for the Path-B live smoke."""
    import math
    from concurrent.futures import Future  # noqa: F401  (keeps import symmetry)
    from datetime import timedelta

    from core.market_models import Candle

    base = 1000.0

    def mk(n, step, phase):
        out = []
        for i in range(n):
            o = base + math.sin((i + phase) / 3) * 0.5 + i * step
            c = base + math.sin((i + 1 + phase) / 3) * 0.5 + (i + 1) * step
            out.append(
                Candle(
                    time=NOW - timedelta(seconds=int((n - i) * step * 3600)),
                    open=o,
                    high=max(o, c) + 0.1,
                    low=min(o, c) - 0.1,
                    close=c,
                )
            )
        return out

    return mk(120, 0.08, 0.0), mk(120, 0.04, 1.0), mk(80, 0.02, 2.0)


def _pathb_safety() -> dict:
    from datetime import timedelta

    from core.scanner_v4_live_producers import build_live_market_safety_context

    return build_live_market_safety_context(
        "XAUUSD",
        NOW,
        terminal_connected=True,
        broker_logged_in=True,
        connectivity_checked_at=NOW - timedelta(seconds=30),
        last_candle_time_utc=NOW - timedelta(seconds=30),
        spread_points=20.0,
        spread_checked_at=NOW,
        news_source_verified=True,
        news_checked_at=NOW,
        volatility_ratio=1.0,
        volatility_checked_at=NOW,
    )


def _run_pathb() -> dict[str, object]:
    """Path-B §12.4 smoke: candle → V4 row via the producers (non-order).

    Runs with the owner's LIVE ``RuntimeOrderPolicy`` loaded from
    ``config/scanner_v4_order_policy.json`` — proves the Bước-13 wiring while
    the order payload stays structurally intent-only.
    """
    from core.scanner_v4_features import TechnicalRawDerivationError

    live_policy = load_runtime_order_policy()
    d1, h4, h1 = _pathb_candles()
    pair = run_v4_pair_from_live(
        d1, h4, h1, "XAUUSD", _pathb_safety(),
        now=NOW, captured_at=NOW,
        macro_raw_buy=20, macro_raw_sell=14, macro_confidence=0.8,
        order_policy=live_policy,
    )
    # Surface the DERIVED raw values out of the composition so the evidence
    # proves the full-history path derived raws (NOT the insufficient_history
    # fail-closed branch, which is shown separately below). The composition
    # exposes per-side results via ``composition.technical[side]``; the input
    # ``SideSnapshot.technical_raws`` map is normalized into the breakdown.
    raws = {}
    for side in ("buy", "sell"):
        tech = pair.composition.technical[side]
        bd = tech.technical_breakdown if tech is not None else None
        raws[side] = {
            "trend": bd.trend.raw if bd is not None else None,
            "momentum": bd.momentum.raw if bd is not None else None,
            "location": bd.location.raw if bd is not None else None,
        }
    # fail-closed on insufficient history
    try:
        run_v4_pair_from_live(d1[:30], h4, h1, "XAUUSD", _pathb_safety(),
                              now=NOW, captured_at=NOW)
        fail_closed = "NO_ERROR"
    except TechnicalRawDerivationError:
        fail_closed = "TechnicalRawDerivationError"

    payload = pair.candidate.order_payload if pair.candidate else None
    return {
        "smoke": "scanner-v4-pathb-non-order",
        "generated_at_utc": NOW.isoformat(),
        "threshold_policy": DEFAULT_THRESHOLD_POLICY.to_dict(),
        "order_policy_version": live_policy.order_policy_version,
        "order_policy_enabled": live_policy.order_enabled,
        "route_status": pair.route_status,
        "row_identity": {
            "composition_version": pair.composition.to_dict().get("composition_version"),
            "scoring_version": pair.row.scoring_version,
            "feature_version": pair.row.feature_version,
            "row_version": pair.row.row_version,
        },
        "snapshot_id": pair.composition.snapshot_id,
        "candidate_status": pair.candidate.candidate_status if pair.candidate else None,
        "intent_only": None if payload is None else payload.sends_real_order,
        "insufficient_history": fail_closed,
        "raws_summary": raws,
    }


def main() -> None:
    report = _run()
    _assert_release_contract(report)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"SMOKE OK -> {OUT_PATH}")
    print(f"  threshold: {report['threshold_policy']['policy_version']} "
          f"40/35/5 R:R2/1 DEFAULT (not fabricated)")
    print(f"  ranked: {report['ranked_symbols']}")
    print(f"  ready above setup floor 35: {report['ready_above_default_setup_floor']}")
    print(f"  ready order intents (sends_real_order=False): "
          f"{[i['symbol'] for i in report['ready_order_intents']]}")
    print(f"  v3 artifact class: {report['default_v3_artifact']['kind']} (must be v3_audit_only)")

    # Path-B §12.4 non-order smoke
    pathb = _run_pathb()
    pathb_out = OUT_DIR / "release_b12_pathb_smoke.json"
    pathb_out.write_text(json.dumps(pathb, indent=2, ensure_ascii=False), encoding="utf-8")
    assert pathb["insufficient_history"] == "TechnicalRawDerivationError"
    assert pathb["row_identity"]["scoring_version"] == "scanner-v4"
    assert pathb["row_identity"]["feature_version"] == "scanner-features-v4"
    # The owner's live order policy must load certified (order_enabled True);
    # the intent-only structural lock still keeps sends_real_order=False.
    assert pathb["order_policy_enabled"] is True, (
        "owner order policy must certify; a broken config must fail closed, "
        "not silently disable"
    )
    # The full-history path must have DERIVED raw scores (in-bounds ints), NOT
    # the insufficient_history branch — proves the smoke used enough candles.
    for side_rawns in pathb["raws_summary"].values():
        for name, value in side_rawns.items():
            assert isinstance(value, int) and 0 <= value, (
                f"raw {name} not derived on full history: {value!r}"
            )
    if pathb["intent_only"] is not None:
        assert pathb["intent_only"] is False
    print(f"PATHB SMOKE OK -> {pathb_out}")
    print(f"  row: {pathb['row_identity']}")
    print(f"  snapshot_id: {pathb['snapshot_id']}")
    print(f"  route/candidate: {pathb['route_status']}/{pathb['candidate_status']} "
          f"(intent={pathb['intent_only']})")
    print(f"  insufficient_history -> {pathb['insufficient_history']} (fail-closed)")


if __name__ == "__main__":
    main()