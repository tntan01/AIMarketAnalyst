"""Controller integration tests for the shared Phase-3 order gate."""

from __future__ import annotations

import ast
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.market_models import Candle

from controllers.scanner_controller import ScannerController
from core.portfolio_models import PortfolioRiskItem, PortfolioSnapshot
from core.scanner_models import ExecutionMarketSnapshot


def _settings():
    return SimpleNamespace(
        trading=SimpleNamespace(
            account_balance=10000.0,
            account_currency="USD",
            default_risk_percent=1.0,
            lot_step=0.01,
            minimum_lot=0.01,
            contract_size_override=100000.0,
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
            d1_bars=120,
            h4_bars=120,
            h1_bars=120,
        ),
        display=SimpleNamespace(timezone="Asia/Ho_Chi_Minh"),
    )


def _snapshot():
    now = datetime.now(timezone.utc)
    return ExecutionMarketSnapshot(
        broker_symbol="EURUSD",
        captured_at=now,
        connected=True,
        logged_in=True,
        trade_allowed=True,
        symbol_available=True,
        symbol_trade_mode=4,
        bid=round(_stub_ask() - 2.0 * _TICK_SIZE, 6),
        ask=_stub_ask(),
        point=_TICK_SIZE,
        spread_points=2.0,
        spread_price=round(2.0 * _TICK_SIZE, 6),
        tick_time=now,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        symbol_state_available=True,
        has_open_position_or_order=False,
        trade_tick_size=_TICK_SIZE,
        trade_tick_value_loss=_TICK_VALUE,
        contract_size=_CONTRACT_SIZE,
    )


def _proposal():
    """The approved order intent.

    ``entry_price``/``current_price`` stay at the 9.9999 sentinel: the live
    execution price must come from the fresh broker quote, never from the
    scanner proposal.  The zone/SL/TP and the R:R floor come from the fixture's
    canonical plan so the proposal approves exactly the setup the dispatcher
    re-evaluates.
    """

    payload = {
        "scan_id": "scan-test",
        "row_id": "scan-test:EURUSD",
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "side": "buy",
        "entry_zone": [1.0990, 1.1015],
        "entry_price": 9.9999,
        "current_price": 9.9999,
        "stop_loss": 1.0950,
        "take_profit": 1.1120,
        "volume": 0.1,
        "required_min_rr": _MIN_RR,
    }
    payload.update(_approved_identity())
    return payload


# The closed set of reasons the Task-111 comparison can block with.  A
# ``SMC_REVALIDATION_UNAVAILABLE`` is deliberately NOT in it: that code means
# the comparison never ran, which would make the negative controls vacuous.
_SMC_BLOCK_CODES = frozenset(
    {
        "SMC_SETUP_CHANGED",
        "SMC_ZONE_INVALID_OR_EXPIRED",
        "SMC_NOT_READY",
        "SMC_M15_UNAVAILABLE",
    }
)


class _SettingsService:
    def load(self):
        return _settings()


class _Journal:
    def list_closed_trades_for_account_guard(self):
        return []


# ---------------------------------------------------------------------------
# Task 111 fixture: a GENUINELY dispatchable canonical snapshot.
#
# The retired fixture only reached WATCH_ZONE, so revalidation blocked with
# SMC_NOT_READY / SMC_M15_UNAVAILABLE.  M15 confirmation legitimately changes
# the candidate ranking (task 73-100), so attaching a window to the pre-window
# winner makes ANOTHER candidate win.  The fixture therefore resolves the
# winner by FIXED POINT: evaluate, build the window for the current winner,
# re-evaluate, repeat until the identity stops moving (max 3 rounds, asserted).
# No zone, setup, plan or confirmation is ever injected — every id comes from
# the canonical chain; the only thing the test pins is the dispatch clock (see
# ``_OBSERVED_AT``), which the controller now takes as an explicit dependency.
# ---------------------------------------------------------------------------
_PRICE_SCALE = 0.001096
_TICK_SIZE = 0.01 * _PRICE_SCALE
_CONTRACT_SIZE = 100000.0
# Broker tick metadata must stay SELF-CONSISTENT: one tick on one lot is worth
# ``tick_size * contract_size``.  ``recalc_execution_lot`` sizes with the
# contract value while the portfolio guard re-values the same lots with the
# tick value, so a tick value left at the unscaled 10.0 would make the guard
# read ~9x the intended 1% risk.  The original fixture satisfied this identity
# exactly (0.0001 * 100000 == 10.0); rescaling the prices means rescaling it.
_TICK_VALUE = _TICK_SIZE * _CONTRACT_SIZE
_APPROVED_SIDE = "buy"
_MIN_RR = 2.0
_MAX_FIXPOINT_ROUNDS = 3

from tests.test_scanner_release import NOW as _FIXTURE_ANCHOR

# The dispatcher's clock is INJECTED, so the scenario does not have to sit at
# the wall clock: a FIXED observation instant makes it reproducible.  Tracking
# ``datetime.now()`` was not merely cosmetic — the canonical verdict depends on
# the hour the candle grid lands on, so the fixture picked a different winner
# from one run to the next and sometimes found no candidate at all.  The offset
# is a whole number of hours so the D1/H4/H1 candles keep the grid they were
# built on.
_M15_CANDLES = 23
_OBSERVATION_OFFSET = timedelta(hours=6)
_OBSERVED_AT: datetime = _FIXTURE_ANCHOR + _OBSERVATION_OFFSET
_SHIFT: timedelta = _OBSERVATION_OFFSET
_M15_START: datetime = _OBSERVED_AT - timedelta(
    minutes=15 * (_M15_CANDLES - 1)
)


def _scale(candles):
    """Rescale onto the quoted FX band and place at the observation instant."""

    assert _SHIFT is not None, "the fixture shift must be resolved first"
    return [
        replace(
            candle,
            time=candle.time + _SHIFT,
            open=round(candle.open * _PRICE_SCALE, 6),
            high=round(candle.high * _PRICE_SCALE, 6),
            low=round(candle.low * _PRICE_SCALE, 6),
            close=round(candle.close * _PRICE_SCALE, 6),
        )
        for candle in candles
    ]


def _confirming_m15(zone_low: float, zone_high: float, *, supply: bool = False) -> list:
    """M15 window whose rejection at the zone confirms the entry (task 74-77).

    Every offset is expressed in units of the zone's own width, so the window
    keeps its shape whatever price scale the fixture is placed on.

    The default shape approaches a DEMAND zone from above, sweeps its low and
    closes back above it.  A SUPPLY zone is confirmed the mirrored way — rally
    up into it, sweep its high, close back below — so ``supply=True`` reflects
    the whole window through the zone's midpoint.
    """

    unit = max(zone_high - zone_low, 1e-9)
    rows: list[tuple[float, float, float, float]] = []
    price = zone_high + 1.8 * unit
    for index in range(20):
        swing = (0.32 if index % 2 == 0 else -0.27) * unit
        close = price + swing
        rows.append(
            (price, max(price, close) + 0.23 * unit, min(price, close) - 0.23 * unit, close)
        )
        price = close
    rows.append((price, price + 0.09 * unit, zone_low + 0.55 * unit, zone_low + 0.73 * unit))
    rows.append(
        (zone_low + 0.73 * unit, zone_high + 0.23 * unit, zone_low - 0.09 * unit, zone_high + 0.14 * unit)
    )
    rows.append(
        (zone_high + 0.14 * unit, zone_high + 0.46 * unit, zone_low + 0.18 * unit, zone_high + 0.41 * unit)
    )
    if supply:
        # Reflecting through the midpoint swaps high/low with it.
        mirror = lambda price: zone_low + zone_high - price  # noqa: E731
        rows = [
            (mirror(open_), mirror(low), mirror(high), mirror(close))
            for open_, high, low, close in rows
        ]
    return [
        Candle(
            time=_M15_START + timedelta(minutes=15 * index),
            open=row[0],
            high=row[1],
            low=row[2],
            close=row[3],
        )
        for index, row in enumerate(rows)
    ]


# The dispatcher derives the symbol from the PROPOSAL, and zone identity
# embeds it, so the fixture must measure with the same symbol.
_PROPOSAL_SYMBOL = "EUR/USD"


def _selection_for(side: str, candles: dict):
    """The fixture's own canonical verdict for ``side`` — the only source of identity."""

    from core.scanner_live_producers import derive_live_analysis

    analysis = derive_live_analysis(
        candles["D1"],
        candles["H4"],
        candles["H1"],
        symbol=_PROPOSAL_SYMBOL,
        captured_at=_OBSERVED_AT,
        m15_candles=candles.get("M15") or None,
        m15_as_of=_OBSERVED_AT,
        tick_size=_TICK_SIZE,
        min_rr=_MIN_RR,
    )
    return analysis["smc_evaluation"].selection(side)


def _canonical_selection(candles: dict):
    return _selection_for(_APPROVED_SIDE, candles)


def _resolve_fixture() -> tuple[dict, object]:
    """Winner + the M15 window that confirms THAT winner (fixed point)."""

    from tests.test_scanner_release import _zoned_candles

    d1, h4, h1 = _zoned_candles()
    candles = {"D1": _scale(d1), "H4": _scale(h4), "H1": _scale(h1), "M15": ()}
    previous = None
    trace: list[tuple[str | None, str | None]] = []
    for _round in range(_MAX_FIXPOINT_ROUNDS):
        selection = _canonical_selection(candles)
        trace.append((selection.selected_zone_id, selection.selected_setup_id))
        if selection.selected is None:
            raise AssertionError(
                f"dispatch fixture: no canonical candidate at round {_round}; "
                f"trace={trace}"
            )
        if previous is not None and previous == (
            selection.selected_zone_id,
            selection.selected_setup_id,
        ):
            return candles, selection
        previous = (selection.selected_zone_id, selection.selected_setup_id)
        zone = selection.selected.plan_zone["original_bounds"]
        candles = dict(candles)
        candles["M15"] = _confirming_m15(
            float(zone["low"]), float(zone["high"])
        )
    raise AssertionError(
        "dispatch fixture did not converge: the M15 window keeps changing the "
        f"winner. trace={trace}"
    )


_DISPATCH: tuple[dict, object] | None = None


def _dispatch_fixture() -> tuple[dict, object]:
    """Resolve the fixed point once, on first use, and reuse it verbatim."""

    global _DISPATCH
    if _DISPATCH is None:
        _DISPATCH = _resolve_fixture()
    return _DISPATCH


def _fresh_candles() -> dict:
    """The converged fixture; the loader returns exactly these candles."""

    return _dispatch_fixture()[0]


def _approved_identity(side: str = _APPROVED_SIDE) -> dict:
    """Zone/setup/plan of the fixture's dispatchable canonical setup."""

    selection = _dispatch_fixture()[1]
    band = selection.selected.plan_zone["original_bounds"]
    return {
        "smc_zone_id": selection.selected_zone_id,
        "smc_setup_id": selection.selected_setup_id,
        "side": side,
        "entry_zone": [float(band["low"]), float(band["high"])],
        "stop_loss": selection.plan.stop_loss,
        "take_profit": selection.plan.take_profit,
    }


def _entry_band() -> tuple[float, float]:
    return tuple(_approved_identity()["entry_zone"])  # type: ignore[return-value]


def _stub_ask() -> float:
    """Live ask the stub quotes: the plan's own entry edge, tick-quantized.

    Buying at the band's protective edge is exactly what the approved plan
    does, so the effective R:R the dispatcher recomputes is the plan's own.
    """

    return round(_entry_band()[0], 6)


class _MT5:
    def __init__(self):
        self.place_calls = []
        self.portfolio_items = []
        self.portfolio_snapshot_calls = 0

    def load_primary_timeframes(self, broker_symbol, bars_by_timeframe):
        return _fresh_candles()

    def symbol_data_quality(self, symbol, broker_symbol):
        return {"tick_size": _TICK_SIZE, "tick_size_source": "trade_tick_size"}

    def execution_snapshot(self, broker_symbol):
        return replace(_snapshot(), broker_symbol=broker_symbol)

    def portfolio_snapshot(self):
        self.portfolio_snapshot_calls += 1
        return PortfolioSnapshot(
            available=True,
            captured_at=datetime.now(timezone.utc),
            account_balance=10000.0,
            account_currency="USD",
            positions=tuple(self.portfolio_items),
        )

    def quote_to_usd_rate(self, currency):
        return 1.0

    def get_open_positions(self):
        return []

    def place_market_order(self, **kwargs):
        self.place_calls.append(kwargs)
        self.portfolio_items.append(
            PortfolioRiskItem(
                source="position",
                ticket=len(self.place_calls),
                symbol=str(kwargs["symbol"]),
                broker_symbol=str(kwargs["broker_symbol"]),
                side=str(kwargs["side"]),
                entry_price=_stub_ask(),
                current_price=_stub_ask(),
                stop_loss=float(kwargs["stop_loss"]),
                volume=float(kwargs["volume"]),
                tick_size=_TICK_SIZE,
                tick_value_loss=_TICK_VALUE,
                contract_size=_CONTRACT_SIZE,
            )
        )
        return {
            "success": True,
            "order_id": 123,
            "message": "ok",
            **kwargs,
        }


class _News:
    def __init__(self, available=True, blackout=False):
        self.available = available
        self.blackout = blackout

    def execution_news_status(self, *args, **kwargs):
        return {
            "available": self.available,
            "blackout": self.blackout if self.available else None,
            "reason_codes": [],
        }


def _controller(mt5, news, *, clock=None):
    """The real controller; only the dispatch clock is pinned.

    ``clock`` returns the fixture's own observation instant so the approved
    proposal and the fresh SMC re-evaluation describe the SAME cutoff.  Every
    other dependency (loader, tick metadata, evaluator, coordinator, planner,
    M15 evaluator, revalidate_execution) stays the real one.
    """

    return ScannerController(
        settings_service=_SettingsService(),
        mt5=mt5,
        news_service=news,
        journal_service=_Journal(),
        clock=clock if clock is not None else (lambda: _OBSERVED_AT),
    )


def test_controller_revalidates_then_places_with_live_price_sizing():
    mt5 = _MT5()
    result = _controller(mt5, _News()).execute_order_candidate(_proposal())

    assert result["success"] is True
    assert result["revalidation"]["allowed"] is True
    # The execution price is the stub's FRESH ask, never the proposal sentinel.
    assert result["revalidation"]["execution_price"] == _stub_ask()
    assert len(mt5.place_calls) == 1
    assert result["portfolio_guard"]["allowed"] is True
    assert "post_trade_portfolio" in result
    assert mt5.portfolio_snapshot_calls == 2
    assert mt5.place_calls[0]["comment"].startswith("AMA-FWD:")
    assert result["forward_correlation_id"]


def test_injected_clock_must_be_a_timezone_aware_datetime():
    """A broken clock fails closed instead of silently dropping the cutoff.

    ``SMC_REVALIDATION_UNAVAILABLE`` would also stop the order, but it would
    hide a wiring bug as a market verdict; an invalid clock is a programming
    error and must say so.  Only ``None`` means "not injected" — an injected
    dependency that cannot be used is never quietly replaced by the real clock.
    """

    # 1. ``clock=None`` is the production default and DOES read the real UTC
    #    clock.  Built directly: ``_controller`` substitutes the fixture clock
    #    for None.
    production = ScannerController(
        settings_service=_SettingsService(),
        mt5=_MT5(),
        news_service=_News(),
        journal_service=_Journal(),
        clock=None,
    )
    stamp = production._utc_now()
    assert stamp.tzinfo is not None and stamp.utcoffset() == timedelta(0)
    assert abs((datetime.now(timezone.utc) - stamp).total_seconds()) < 5

    mt5 = _MT5()

    # 2. A non-callable injection is a WIRING bug, not "no clock".
    invalid = _controller(mt5, _News(), clock="invalid")
    with pytest.raises(ValueError):
        invalid._utc_now()
    with pytest.raises(ValueError):
        invalid.execute_order_candidate(_proposal())
    assert mt5.place_calls == []

    # 3. A callable that returns junk or a cutoff with no usable offset.
    class _UnknownOffset(tzinfo):
        """A tzinfo that is present but refuses to name its offset."""

        def utcoffset(self, dt):
            return None

        def dst(self, dt):
            return None

        def tzname(self, dt):
            return None

    for broken in (
        lambda: "2026-08-13T18:00:00Z",
        lambda: 1755100000.0,
        lambda: None,
        lambda: datetime(2026, 8, 13, 18, 0),
        lambda: datetime(2026, 8, 13, 18, 0, tzinfo=_UnknownOffset(timedelta(0))),
    ):
        broken_clock = _controller(mt5, _News(), clock=broken)
        with pytest.raises(ValueError):
            broken_clock._utc_now()
        with pytest.raises(ValueError):
            broken_clock.execute_order_candidate(_proposal())
    assert mt5.place_calls == []

    # 4. A clock in another timezone is ACCEPTED and normalized to UTC, so the
    #    cutoff the chain sees is always the same instant.
    local = timezone(timedelta(hours=7))
    shifted = _controller(
        mt5, _News(), clock=lambda: _OBSERVED_AT.astimezone(local)
    )
    assert shifted._utc_now() == _OBSERVED_AT
    result = shifted.execute_order_candidate(_proposal())

    assert result["smc_revalidation"]["cutoff"] == _OBSERVED_AT.isoformat()
    assert len(mt5.place_calls) == 1

    # 5. A legacy instance/test double that predates the dependency has no
    #    ``_clock`` attribute at all: that is "not injected", not an
    #    AttributeError.
    legacy = object.__new__(ScannerController)
    assert not hasattr(legacy, "_clock")
    legacy_stamp = legacy._utc_now()
    assert legacy_stamp.tzinfo is not None
    assert legacy_stamp.utcoffset() == timedelta(0)
    assert abs((datetime.now(timezone.utc) - legacy_stamp).total_seconds()) < 5


def test_manual_order_no_longer_carries_any_rollout_gate():
    # The Phase-8 rollout stage ladder was removed (2026-08-15, fully live):
    # a manual order reaches the remaining guard chain directly — no rollout
    # decision, no release gate, no override knob.
    mt5 = _MT5()
    controller = _controller(mt5, _News())

    result = controller.execute_order_candidate(_proposal())

    assert result["success"] is True
    assert "rollout" not in result
    assert len(mt5.place_calls) == 1


def test_controller_does_not_place_when_realtime_news_is_unavailable():
    mt5 = _MT5()
    result = _controller(
        mt5,
        _News(available=False),
    ).execute_order_candidate(_proposal())

    assert result["success"] is False
    assert "NEWS_STATUS_UNAVAILABLE" in result["revalidation"]["block_codes"]
    assert mt5.place_calls == []


def test_second_order_uses_portfolio_state_after_first_order():
    mt5 = _MT5()
    controller = _controller(mt5, _News())
    settings = controller.settings_service.load()
    settings.trading.max_open_risk_pct = 1.5
    controller.settings_service.load = lambda: settings

    first = controller.execute_order_candidate(_proposal())
    second_proposal = {
        **_proposal(),
        "symbol": "GBP/USD",
        "broker_symbol": "GBPUSD",
    }
    second = controller.execute_order_candidate(second_proposal)

    assert first["success"] is True
    assert second["success"] is False
    assert second["portfolio_guard"]["current_open_risk_pct"] > 0
    assert "PORTFOLIO_RISK_EXCEEDED" in second["portfolio_guard"]["block_codes"]
    assert "PORTFOLIO_RISK_EXCEEDED" in second["message"]
    assert len(mt5.place_calls) == 1


def test_concurrent_order_requests_are_serialized_against_portfolio_state():
    class SlowMT5(_MT5):
        def place_market_order(self, **kwargs):
            time.sleep(0.05)
            return super().place_market_order(**kwargs)

    mt5 = SlowMT5()
    controller = _controller(mt5, _News())
    settings = controller.settings_service.load()
    settings.trading.max_open_risk_pct = 1.5
    controller.settings_service.load = lambda: settings
    eur = _proposal()
    gbp = {
        **_proposal(),
        "symbol": "GBP/USD",
        "broker_symbol": "GBPUSD",
    }

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(controller.execute_order_candidate, (eur, gbp)))

    assert sum(bool(result["success"]) for result in results) == 1
    assert len(mt5.place_calls) == 1
    blocked = next(result for result in results if not result["success"])
    assert "PORTFOLIO_RISK_EXCEEDED" in blocked["portfolio_guard"]["block_codes"]


def test_success_path_proves_the_fresh_snapshot_that_was_compared():
    """The dispatch evidence names the ONE cutoff and the identity it matched.

    Task 111 can only be trusted if the order that was sent is the order whose
    approved setup the FRESH snapshot still confirms — so the result must show
    that fresh comparison, not merely that the order went out.
    """

    mt5 = _MT5()
    result = _controller(mt5, _News()).execute_order_candidate(_proposal())

    assert result["success"] is True
    fresh = result["smc_revalidation"]
    assert fresh["source"] == "fresh_canonical_snapshot"
    # The injected dispatch clock is the ONLY cutoff the fresh chain saw, so the
    # evidence must name exactly that instant.
    assert fresh["cutoff"] == _OBSERVED_AT.isoformat()
    approved = _approved_identity()
    assert fresh["approved"]["selected_zone_id"] == approved["smc_zone_id"]
    assert fresh["approved"]["selected_setup_id"] == approved["smc_setup_id"]
    # ... and the current verdict matched it, dispatchably.
    assert fresh["current"]["selected_zone_id"] == approved["smc_zone_id"]
    assert fresh["current"]["selected_setup_id"] == approved["smc_setup_id"]
    assert fresh["current"]["state"] == "evaluated"
    assert fresh["current"]["readiness_status"] == "READY_NOW"
    assert fresh["current"]["m15_status"] == "confirmed"
    assert result["revalidation"]["block_codes"] == []
    assert len(mt5.place_calls) == 1


def test_production_default_reads_the_utc_clock_exactly_once():
    """Without an injected clock the boundary reads UTC itself, once.

    Production passes no ``clock``; the dispatch must still derive the fresh
    snapshot from a single UTC read that it then hands to the revalidation —
    never a second, later instant, and never a value taken from the proposal.
    """

    reads: list[datetime] = []

    class _Spy(ScannerController):
        def _utc_now(self) -> datetime:
            value = super()._utc_now()
            reads.append(value)
            return value

    mt5 = _MT5()
    controller = _Spy(
        settings_service=_SettingsService(),
        mt5=mt5,
        news_service=_News(),
        journal_service=_Journal(),
    )
    assert controller._clock is None, "production default must not inject a clock"

    before = datetime.now(timezone.utc)
    result = controller.execute_order_candidate(_proposal())
    after = datetime.now(timezone.utc)

    assert len(reads) == 1, "the dispatch boundary must read the clock exactly once"
    cutoff = reads[0]
    assert cutoff.tzinfo is not None and cutoff.utcoffset() == timedelta(0)
    assert before - timedelta(seconds=1) <= cutoff <= after + timedelta(seconds=1)
    # The value that single read produced is the cutoff the snapshot used.
    assert result["smc_revalidation"]["cutoff"] == cutoff.isoformat()
    assert result["success"] is True
    assert len(mt5.place_calls) == 1


def test_m15_confirming_a_different_zone_blocks_the_approved_setup():
    """Negative control: a fresh window that confirms ANOTHER zone.

    The approved setup is unchanged and still the current winner, but the
    market's entry confirmation has moved to a different zone — the dispatcher
    must block on the canonical comparison and send nothing.
    """

    approved_zone = _approved_identity()["smc_zone_id"]
    other = _selection_for("sell", _fresh_candles())
    assert other.selected is not None
    band = other.selected.plan_zone["original_bounds"]
    candles = {
        **_fresh_candles(),
        "M15": _confirming_m15(
            float(band["low"]), float(band["high"]), supply=True
        ),
    }

    # The window genuinely confirms the OTHER zone, so this control is about
    # confirmation moving away — not about a window that confirms nothing.
    confirmed_other = _selection_for("sell", candles)
    assert confirmed_other.selected_zone_id != approved_zone
    assert confirmed_other.readiness.m15_status == "confirmed"
    # ... while the approved zone is still current but no longer confirmed.
    approved_now = _selection_for(_APPROVED_SIDE, candles)
    assert approved_now.selected_zone_id == approved_zone
    assert approved_now.readiness.m15_status != "confirmed"

    class _OtherZoneMT5(_MT5):
        def load_primary_timeframes(self, broker_symbol, bars_by_timeframe):
            return candles

    mt5 = _OtherZoneMT5()
    result = _controller(mt5, _News()).execute_order_candidate(_proposal())

    assert result["success"] is False
    assert mt5.place_calls == []
    # The comparison really ran (it was not skipped) and saw the other zone.
    fresh = result["smc_revalidation"]
    assert fresh is not None
    assert fresh["approved"]["selected_zone_id"] == approved_zone
    assert fresh["current"]["m15_status"] != "confirmed"
    assert "SMC_M15_UNAVAILABLE" in result["revalidation"]["block_codes"]
    assert _SMC_BLOCK_CODES & set(result["revalidation"]["block_codes"])


def test_stale_proposal_identity_blocks_and_sends_nothing():
    """Negative control: an approval carried over from an earlier snapshot."""

    mt5 = _MT5()
    stale = {
        **_proposal(),
        "smc_zone_id": _stale_identity(_approved_identity()["smc_zone_id"]),
    }
    result = _controller(mt5, _News()).execute_order_candidate(stale)

    assert result["success"] is False
    assert "SMC_SETUP_CHANGED" in result["revalidation"]["block_codes"]
    assert mt5.place_calls == []


def _stale_identity(identity: str) -> str:
    """A same-shaped but no-longer-current ``smcz-`` id."""

    head, _, digest = identity.partition("-")
    flipped = ("0" if digest[:1] != "0" else "1") + digest[1:]
    return f"{head}-{flipped}"


def test_scanner_has_no_order_path_bypassing_shared_revalidation():
    """Architecture guard: scanner order_send has exactly one owner."""

    project_root = Path(__file__).resolve().parent.parent
    controller_path = project_root / "controllers" / "scanner_controller.py"
    screen_path = project_root / "ui" / "screens" / "scanner_screen.py"

    controller_tree = ast.parse(controller_path.read_text(encoding="utf-8"))
    screen_tree = ast.parse(screen_path.read_text(encoding="utf-8"))

    controller_calls = _attribute_call_owners(
        controller_tree,
        "place_market_order",
    )
    screen_calls = _attribute_call_owners(screen_tree, "place_market_order")
    shared_gate_calls = _attribute_call_owners(
        controller_tree,
        "execute_order_candidate",
    )
    manual_gate_calls = _attribute_call_owners(
        screen_tree,
        "execute_order_candidate",
    )

    assert controller_calls == ["execute_order_candidate"]
    assert screen_calls == []
    assert "_execute_auto_trades" in shared_gate_calls
    assert "execute_manual_order" in manual_gate_calls


def test_revalidation_occurs_before_the_only_mt5_order_call():
    project_root = Path(__file__).resolve().parent.parent
    source = (
        project_root / "controllers" / "scanner_controller.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "execute_order_candidate"
    )
    revalidation_line = next(
        node.lineno
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "revalidate_execution"
    )
    order_line = next(
        node.lineno
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "place_market_order"
    )

    assert revalidation_line < order_line
    assert "if not validation.allowed:" in source


def _attribute_call_owners(tree: ast.AST, attribute: str) -> list[str]:
    owners: list[str] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.functions: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        def visit_Call(self, node: ast.Call) -> None:
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == attribute
            ):
                owners.append(self.functions[-1] if self.functions else "<module>")
            self.generic_visit(node)

    Visitor().visit(tree)
    return owners
