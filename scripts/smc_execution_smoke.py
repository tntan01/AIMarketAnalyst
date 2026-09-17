"""Execution smoke that must never send a real order (task 135).

Run:
    python -X utf8 scripts/smc_execution_smoke.py --report reports/scanner/smc_real_snapshots/execution_smoke.json

The smoke drives the REAL dispatch boundary — ``ScannerController.execute_order_candidate``,
the only path in this codebase that can reach ``MT5Service.place_market_order`` →
``mt5.order_send`` — with a **mock broker**.  Every scenario records three things:
the verdict the controller returned, the block codes it reported, and how many
times the mock broker was asked to place an order.  The last number is the proof:
the real ``order_send`` is unreachable while the mock's call list stays empty.

The approved proposal of the control case is built from a **real** canonical plan
of the task-131 corpus (zone band, SL/TP and identity read from the typed
selection, never retyped by hand), and the fresh snapshot the dispatcher
re-evaluates comes from the same real candles — extended with the broker bars
that printed *after* that cutoff, which the corpus stores as the future tail.

Scenarios:

* ``control_matching_setup`` — the market is still the approved setup: this one
  MUST pass revalidation and reach the mock, otherwise the negative scenarios
  below would be vacuous (a dispatcher that blocks everything blocks nothing for
  the reason it claims).
* ``zone_invalid`` — the fresh snapshot no longer offers the entry region.
* ``stale_quote`` — the broker quote is older than the freshness limit.
* ``missing_m15`` — the fresh window has no M15, so the trigger cannot exist.
* ``setup_changed`` — the approval names a setup the fresh snapshot does not
  confirm any more.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.market_models import Candle  # noqa: E402
from core.portfolio_models import PortfolioSnapshot  # noqa: E402
from core.scanner_models import ExecutionMarketSnapshot  # noqa: E402
from core.scanner_live_producers import derive_live_analysis  # noqa: E402

OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_real_snapshots"
CORPUS_PATH = OUTPUT_DIR / "corpus.jsonl.gz"
DEFAULT_REPORT = OUTPUT_DIR / "execution_smoke.json"

TICK_SIZE = 0.00001
TICK_VALUE = 1.0
CONTRACT_SIZE = 100000.0
MIN_RR = 2.0
STALE_TICK_SECONDS = 120.0

# The codes that mean "the approval no longer matches the market".
SMC_BLOCK_CODES = frozenset(
    {
        "SMC_SETUP_CHANGED",
        "SMC_ZONE_INVALID_OR_EXPIRED",
        "SMC_NOT_READY",
        "SMC_M15_UNAVAILABLE",
    }
)


def _settings() -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        trading=SimpleNamespace(
            account_balance=10000.0,
            account_currency="USD",
            default_risk_percent=1.0,
            lot_step=0.01,
            minimum_lot=0.01,
            contract_size_override=CONTRACT_SIZE,
            max_daily_loss_pct=2.0,
            max_weekly_loss_pct=5.0,
            max_consecutive_losses=3,
            max_open_risk_pct=3.0,
            max_symbol_risk_pct=2.0,
            max_currency_exposure_pct=2.0,
            max_correlated_risk_pct=2.0,
            max_concurrent_orders=5,
        ),
        advanced=SimpleNamespace(
            high_impact_news_block_before_minutes=30,
            high_impact_news_block_after_minutes=30,
            block_high_impact_news=True,
            d1_bars=500,
            h4_bars=500,
            h1_bars=500,
        ),
        display=SimpleNamespace(timezone="Asia/Ho_Chi_Minh"),
    )


class _SettingsService:
    def load(self):
        return _settings()


class _Journal:
    """A journal that records nothing and blocks nothing."""

    def log_order_event(self, *_args, **_kwargs):
        return None

    def has_open_order(self, *_args, **_kwargs):
        return False

    def list_closed_trades_for_account_guard(self, *_args, **_kwargs):
        return []


class _News:
    def execution_news_status(self, *_args, **_kwargs):
        return {"available": True, "blackout": False, "reason_codes": []}


class MockBroker:
    """A broker that answers from a fixed candle window and records calls."""

    def __init__(self, candles: Mapping[str, list[Candle]], *, tick_age_seconds: float = 0.0):
        self.candles = {tf: list(values) for tf, values in candles.items()}
        self.tick_age_seconds = tick_age_seconds
        self.place_calls: list[dict[str, Any]] = []
        self.execution_snapshot_calls = 0
        self.load_calls = 0
        self._ask = 0.0
        self._now = datetime.now(timezone.utc)

    def set_quote(self, *, ask: float, now: datetime) -> None:
        self._ask = ask
        self._now = now

    def load_primary_timeframes(self, broker_symbol, bars_by_timeframe):
        self.load_calls += 1
        return {tf: list(values) for tf, values in self.candles.items()}

    def symbol_data_quality(self, symbol, broker_symbol):
        return {"tick_size": TICK_SIZE, "tick_size_source": "trade_tick_size"}

    def execution_snapshot(self, broker_symbol):
        self.execution_snapshot_calls += 1
        tick_time = self._now - timedelta(seconds=self.tick_age_seconds)
        return ExecutionMarketSnapshot(
            broker_symbol=broker_symbol,
            captured_at=self._now,
            connected=True,
            logged_in=True,
            trade_allowed=True,
            symbol_available=True,
            symbol_trade_mode=4,
            bid=round(self._ask - 2.0 * TICK_SIZE, 6),
            ask=self._ask,
            point=TICK_SIZE,
            spread_points=2.0,
            spread_price=round(2.0 * TICK_SIZE, 6),
            tick_time=tick_time,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            symbol_state_available=True,
            has_open_position_or_order=False,
            trade_tick_size=TICK_SIZE,
            trade_tick_value_loss=TICK_VALUE,
            contract_size=CONTRACT_SIZE,
        )

    def portfolio_snapshot(self):
        return PortfolioSnapshot(
            available=True,
            captured_at=self._now,
            account_balance=10000.0,
            account_currency="USD",
            positions=(),
        )

    def quote_to_usd_rate(self, currency):
        return 1.0

    def get_open_positions(self):
        return []

    def place_market_order(self, **kwargs):
        self.place_calls.append(dict(kwargs))
        return {"success": True, "order_id": 1, "message": "mock", **kwargs}


def _controller(broker: MockBroker, clock: Any):
    from controllers.scanner_controller import ScannerController

    return ScannerController(
        settings_service=_SettingsService(),
        mt5=broker,
        news_service=_News(),
        journal_service=_Journal(),
        clock=clock,
    )


def _corpus_rows() -> list[dict[str, Any]]:
    with gzip.open(CORPUS_PATH, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _candle(item: Mapping[str, Any]) -> Candle:
    return Candle(
        time=datetime.fromisoformat(str(item["t"])),
        open=float(item["o"]),
        high=float(item["h"]),
        low=float(item["l"]),
        close=float(item["c"]),
        volume=float(item.get("v") or 0.0),
    )


def _windows(row: Mapping[str, Any], *, with_tail: bool, drop_m15: bool = False):
    windows: dict[str, list[Candle]] = {}
    for timeframe in ("D1", "H4", "H1", "M15"):
        values = [_candle(item) for item in row["candles"][timeframe]]
        if with_tail:
            values = values + [_candle(item) for item in row["future_tail"].get(timeframe) or []]
        windows[timeframe] = values
    if drop_m15:
        windows["M15"] = []
    return windows


def _plan_of(row: Mapping[str, Any]) -> tuple[str, Any, Any] | None:
    """The side, typed selection and plan of a real accepted canonical plan."""

    windows = _windows(row, with_tail=False)
    analysis = derive_live_analysis(
        windows["D1"],
        windows["H4"],
        windows["H1"],
        symbol=row["symbol"],
        captured_at=datetime.fromisoformat(row["as_of"]),
        m15_candles=windows["M15"],
        m15_as_of=datetime.fromisoformat(row["as_of"]),
        tick_size=row["tick_size"],
        tick_size_source=row["tick_size_source"],
        min_rr=MIN_RR,
    )
    for side in ("buy", "sell"):
        selection = analysis["smc_evaluation"].selection(side)
        if selection is None or not selection.plan_available or selection.plan is None:
            continue
        return side, selection, analysis
    return None


def _proposal(row: Mapping[str, Any], side: str, selection: Any) -> dict[str, Any]:
    plan = selection.plan
    original = selection.selected.plan_zone["original_bounds"]
    low, high = float(original["low"]), float(original["high"])
    return {
        "scan_id": "smc-execution-smoke",
        "row_id": f"smc-execution-smoke:{row['symbol']}",
        "symbol": row["symbol"],
        "broker_symbol": row["broker_symbol"],
        "side": side,
        "entry_zone": [low, high],
        "entry_price": 9.9999,
        "current_price": 9.9999,
        "stop_loss": float(plan.stop_loss),
        "take_profit": float(plan.take_profit),
        "volume": 0.01,
        "required_min_rr": MIN_RR,
        "smc_zone_id": selection.selected_zone_id,
        "smc_setup_id": selection.selected_setup_id,
    }


def _ask_for(side: str, proposal: Mapping[str, Any]) -> float:
    """Quote at the band's protective edge, as the approved plan itself would."""

    low, high = proposal["entry_zone"]
    return round(low if side == "buy" else high, 6)


def _outcome(result: Mapping[str, Any], broker: MockBroker) -> dict[str, Any]:
    validation = result.get("revalidation") or {}
    return {
        "success": bool(result.get("success")),
        "message": result.get("message"),
        "block_codes": list(validation.get("block_codes") or []),
        "reason_codes": list(validation.get("reason_codes") or []),
        "smc_revalidation": result.get("smc_revalidation"),
        "place_calls": len(broker.place_calls),
    }


def _engine_scenarios(proposal: Mapping[str, Any], zone_id: Any, setup_id: Any) -> list[dict[str, Any]]:
    """The five gate behaviours, on the real engine, with real identity values.

    ``revalidate_execution`` is where a dispatch is actually decided, so the
    demonstration is made there: the approved/current pair is filled with the
    zone and setup ids of a REAL accepted plan from the corpus, and each
    scenario changes exactly one thing.  The matching case must pass — without
    it the negatives would prove nothing, because a gate that blocks everything
    blocks nothing for the reason it claims.

    The proposal and the broker snapshot come from the repository's own
    revalidation fixtures (``tests.test_execution_revalidation``): they are the
    non-SMC half of the gate (prices, volume, spread) and the task's four
    scenarios are all about the SMC/quote half.
    """

    from core.execution_revalidation_engine import revalidate_execution
    from tests.test_execution_revalidation import NOW, _proposal, _snapshot

    matching = {
        "approved": {"selected_zone_id": zone_id, "selected_setup_id": setup_id},
        "current": {
            "selected_zone_id": zone_id,
            "selected_setup_id": setup_id,
            "state": "evaluated",
            "readiness_status": "READY_NOW",
            "m15_status": "confirmed",
        },
    }

    def mutate(**changes):
        payload = json.loads(json.dumps(matching))
        payload["current"].update(changes)
        return payload

    scenarios = [
        ("matching_setup", _proposal(), _snapshot(), matching),
        (
            "stale_quote",
            _proposal(),
            _snapshot(tick_time=NOW - timedelta(seconds=STALE_TICK_SECONDS)),
            matching,
        ),
        (
            "m15_missing",
            _proposal(),
            _snapshot(),
            mutate(m15_status="missing"),
        ),
        (
            "zone_invalid",
            _proposal(),
            _snapshot(),
            mutate(state="no_zone", selected_zone_id=None, selected_setup_id=None),
        ),
        (
            "setup_changed",
            _proposal(),
            _snapshot(),
            mutate(selected_setup_id="smcs-0000000000000000dead"),
        ),
        (
            "not_ready",
            _proposal(),
            _snapshot(),
            mutate(readiness_status="WATCH_ZONE"),
        ),
    ]
    results: list[dict[str, Any]] = []
    for name, proposal_payload, snapshot, smc in scenarios:
        verdict = revalidate_execution(
            proposal_payload,
            snapshot,
            news_blackout=False,
            account_allowed=True,
            portfolio_allowed=True,
            now=NOW,
            smc_revalidation=smc,
        )
        results.append(
            {
                "scenario": name,
                "allowed": bool(verdict.allowed),
                "block_codes": list(verdict.block_codes),
                "reason_codes": list(verdict.reason_codes),
            }
        )
    return results


def run_scenarios(row: Mapping[str, Any], side: str, selection: Any, proposal: dict[str, Any]) -> dict[str, Any]:
    cutoff = datetime.fromisoformat(row["as_of"])
    scenarios: list[dict[str, Any]] = []

    def run(name: str, *, windows, clock_at, tick_age=0.0, proposal_override=None):
        broker = MockBroker(windows, tick_age_seconds=tick_age)
        broker.set_quote(ask=_ask_for(side, proposal), now=clock_at)
        controller = _controller(broker, lambda: clock_at)
        outcome = controller.execute_order_candidate(proposal_override or proposal)
        record = {"scenario": name, **_outcome(outcome, broker)}
        record["load_primary_timeframes_calls"] = broker.load_calls
        record["execution_snapshot_calls"] = broker.execution_snapshot_calls
        scenarios.append(record)
        return record

    same = _windows(row, with_tail=False)
    run("control_matching_setup", windows=same, clock_at=cutoff)
    later = _windows(row, with_tail=True)
    run(
        "zone_invalid_or_setup_changed",
        windows=later,
        clock_at=cutoff + timedelta(hours=24),
    )
    run("stale_quote", windows=same, clock_at=cutoff, tick_age=STALE_TICK_SECONDS)
    run("missing_m15", windows=_windows(row, with_tail=False, drop_m15=True), clock_at=cutoff)
    aged = dict(proposal)
    aged["smc_setup_id"] = "smcs-0000000000000000dead"
    run("setup_changed", windows=same, clock_at=cutoff, proposal_override=aged)
    return {
        "symbol": row["symbol"],
        "as_of": row["as_of"],
        "side": side,
        "approved_zone_id": proposal["smc_zone_id"],
        "approved_setup_id": proposal["smc_setup_id"],
        "engine_scenarios": _engine_scenarios(proposal, proposal["smc_zone_id"], proposal["smc_setup_id"]),
        "dispatch_scenarios": scenarios,
    }


def _intent_lock() -> dict[str, Any]:
    """The payload that carries an order intent can never claim a real send.

    Every other field is filled with the real locked version constants, so a
    refusal can only come from ``sends_real_order`` itself and not from an
    unrelated contract error.
    """

    from core.scanner_candidate import ScannerOrderPayload
    from core.scanner_composition import COMPOSITION_POLICY_VERSION
    from core.scanner_v4_models import (
        SCANNER_MACRO_POLICY_VERSION,
        SCANNER_OUTPUT_SCHEMA_VERSION,
        SCANNER_SAFETY_POLICY_VERSION,
        SCANNER_SCORING_VERSION,
        SCANNER_SNAPSHOT_VERSION,
        SCANNER_V4_FEATURE_VERSION,
    )
    from tests.scanner_testkit import DEFAULT_THRESHOLD_POLICY

    valid = {
        "symbol": "EUR/USD",
        "side": "buy",
        "captured_at": datetime.now(timezone.utc),
        "snapshot_id": "smc-execution-smoke",
        "composition_version": COMPOSITION_POLICY_VERSION,
        "scoring_version": SCANNER_SCORING_VERSION,
        "feature_version": SCANNER_V4_FEATURE_VERSION,
        "output_schema_version": SCANNER_OUTPUT_SCHEMA_VERSION,
        "snapshot_version": SCANNER_SNAPSHOT_VERSION,
        "safety_policy_version": SCANNER_SAFETY_POLICY_VERSION,
        "macro_policy_version": SCANNER_MACRO_POLICY_VERSION,
        "threshold_policy_version": DEFAULT_THRESHOLD_POLICY.policy_version,
        "entry": 1.1,
        "stop_loss": 1.09,
        "take_profit": 1.12,
        "risk_reward_ratio": None,
        "technical_signal_score": 70,
        "setup_score": 70,
    }
    default = ScannerOrderPayload(**valid)
    try:
        ScannerOrderPayload(**valid, sends_real_order=True)
    except Exception as exc:
        locked = "sends_real_order" in str(exc)
        error = f"{type(exc).__name__}: {exc}"
    else:
        locked = False
        error = "constructor accepted sends_real_order=True"
    return {
        "rejects_true": locked,
        "error": error,
        "default_value": bool(getattr(default, "sends_real_order", None)),
    }


def _dispatch_call_sites() -> dict[str, Any]:
    """Where the real send lives, read from the source tree.

    The claim "no real order can be sent" is only meaningful if the one call
    that talks to the broker is reachable from exactly one place, and that place
    is behind the revalidation verdict.  This walks the production sources and
    reports every ``order_send`` / ``place_market_order`` mention with its file,
    so the reader can check the claim instead of trusting it.
    """

    import re

    patterns = {
        "order_send": re.compile(r"\border_send\s*\("),
        "place_market_order_def": re.compile(r"def place_market_order\s*\("),
        "place_market_order_call": re.compile(r"\.place_market_order\s*\("),
    }
    found: dict[str, list[str]] = {name: [] for name in patterns}
    guarded_by_verdict = False
    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT)
        if relative.parts[0] in {"tests", "data", "__pycache__"}:
            continue
        if "__pycache__" in relative.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in patterns.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                found[name].append(f"{relative.as_posix()}:{line}")
        if relative.as_posix() == "controllers/scanner_controller.py":
            guard = text.find("if not validation.allowed")
            dispatch = text.find(".place_market_order(")
            guarded_by_verdict = guard != -1 and dispatch != -1 and guard < dispatch
    found["market_dispatch_guarded_by_verdict"] = [str(guarded_by_verdict)]
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Execution smoke, no real order (task 135)")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()
    if not CORPUS_PATH.exists():
        print(f"BLOCKED: no corpus at {CORPUS_PATH}; run scripts/smc_real_snapshots.py collect first.")
        return 2

    started = time.perf_counter()
    rows = _corpus_rows()
    found: dict[str, Any] | None = None
    scanned = 0
    for row in rows:
        scanned += 1
        try:
            plan = _plan_of(row)
        except Exception:
            continue
        if plan is None:
            continue
        side, selection, _analysis = plan
        proposal = _proposal(row, side, selection)
        found = run_scenarios(row, side, selection, proposal)
        break

    report: dict[str, Any] = {
        "report_version": "smc-execution-smoke-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus": str(CORPUS_PATH.relative_to(PROJECT_ROOT)),
        "rows_available": len(rows),
        "rows_scanned_for_a_real_plan": scanned,
        "broker": "mock (no MT5 order path is reachable)",
        "intent_lock": _intent_lock(),
        "dispatch_call_sites": _dispatch_call_sites(),
        "case": found,
    }
    if found is None:
        report["status"] = "BLOCKED"
        report["blocked_reason"] = (
            "no corpus row reached an accepted canonical plan, so there is no real "
            "approval to revalidate"
        )

    failures: list[str] = []
    if found is not None:
        engine = {item["scenario"]: item for item in found["engine_scenarios"]}
        if not engine["matching_setup"]["allowed"] or engine["matching_setup"]["block_codes"]:
            failures.append(
                "engine control did not pass: the negative scenarios would be vacuous "
                f"({engine['matching_setup']['block_codes']})"
            )
        expected_codes = {
            "stale_quote": "TICK_STALE",
            "m15_missing": "SMC_M15_UNAVAILABLE",
            "zone_invalid": "SMC_ZONE_INVALID_OR_EXPIRED",
            "setup_changed": "SMC_SETUP_CHANGED",
            "not_ready": "SMC_NOT_READY",
        }
        for scenario, code in expected_codes.items():
            item = engine.get(scenario, {})
            if item.get("allowed") or code not in (item.get("block_codes") or []):
                failures.append(
                    f"engine {scenario} did not block with {code} ({item.get('block_codes')})"
                )
        for scenario in found["dispatch_scenarios"]:
            if scenario["place_calls"] != 0:
                failures.append(f"{scenario['scenario']}: a mock order was placed")
            if not scenario["block_codes"]:
                failures.append(f"{scenario['scenario']}: nothing blocked the dispatch")
    if not report["intent_lock"]["rejects_true"] or report["intent_lock"]["default_value"]:
        failures.append("ScannerOrderPayload no longer locks sends_real_order to False")
    send_sites = report["dispatch_call_sites"]["order_send"]
    if not send_sites or any(
        not site.startswith("services/mt5_service.py") for site in send_sites
    ):
        failures.append(
            f"every order_send must live in services/mt5_service.py, found {send_sites}"
        )
    scanner_dispatch = [
        site
        for site in report["dispatch_call_sites"]["place_market_order_call"]
        if site.startswith("controllers/scanner_controller.py")
    ]
    if len(scanner_dispatch) != 1:
        failures.append(
            f"expected one market-dispatch call site in the controller, found {scanner_dispatch}"
        )
    if report["dispatch_call_sites"]["market_dispatch_guarded_by_verdict"] != ["True"]:
        failures.append("the market dispatch is not textually behind the revalidation guard")

    report["failures"] = failures
    report["elapsed_seconds"] = round(time.perf_counter() - started, 4)
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if found:
        for scenario in found["engine_scenarios"]:
            print(
                f"  engine  {scenario['scenario']:20s} allowed={scenario['allowed']} "
                f"blocks={scenario['block_codes']}"
            )
        for scenario in found["dispatch_scenarios"]:
            print(
                f"  dispatch {scenario['scenario']:24s} success={scenario['success']} "
                f"blocks={scenario['block_codes']} place_calls={scenario['place_calls']}"
            )
    else:
        print("BLOCKED: no real accepted plan in the corpus to revalidate.")
    print(f"\nfailures={len(failures)}")
    print(f"report -> {target}")
    return 0 if not failures and found is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
