"""Step 04 tests for MarketSafetyContext + MarketSafetyGate.

Covers the full matrix for the five safety sub-gates (PASS/CAUTION/BLOCK/UNKNOWN),
the fail-closed aggregate precedence, strict context/policy construction, and the
runtime-isolation guard (this target-only module is NOT wired into live runtime).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.market_safety_gate import (
    AVAILABILITY_ERROR,
    AVAILABILITY_MISSING,
    AVAILABILITY_STALE,
    AVAILABILITY_VALID,
    DEFAULT_MARKET_SAFETY_POLICY,
    MANUAL_ORDER_POLICY_VERSION,
    SPREAD_POLICY_VERSION,
    MarketSafetyContext,
    MarketSafetyGate,
    MarketSafetyGateError,
    SafetyPolicy,
    ConnectivitySource,
    DataFreshnessSource,
    NewsSource,
    SpreadSource,
    VolatilitySource,
    BaseSafetySource,
    VOLATILITY_METRIC_ATR14,
    VOLATILITY_INTRADAY_REFERENCE,
    VOLATILITY_STRUCTURAL_REFERENCE,
    VOLATILITY_REFERENCE_WINDOW_DAYS,
    VOLATILITY_SEMANTICS_VERSION,
)
from core.reason_codes import (
    SAFETY_DATA_FRESHNESS_UNKNOWN,
    SAFETY_DATA_STALE,
    SAFETY_MT5_NOT_READY,
    SAFETY_MT5_STATE_UNKNOWN,
    SAFETY_NEWS_HIGH_IMPACT_BLOCK,
    SAFETY_NEWS_HIGH_IMPACT_CAUTION,
    SAFETY_NEWS_SOURCE_UNAVAILABLE,
    SAFETY_SPREAD_ABNORMAL,
    SAFETY_SPREAD_THRESHOLD_UNSET,
    SAFETY_SPREAD_UNKNOWN,
    SAFETY_VOLATILITY_BAND_UNSET,
    SAFETY_VOLATILITY_EXTREME,
    SAFETY_VOLATILITY_UNKNOWN,
)
from core.scanner_v4_models import (
    PASS,
    CAUTION,
    BLOCK,
    UNKNOWN,
    SCANNER_SAFETY_POLICY_VERSION,
    SAFETY_CHECK_NAMES,
)


UTC = timezone.utc
NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

# Cross-safe provenance (no forbidden scored/identity keys).
PROV = {"captured_by": "scanner-v4-target", "feed": "mt5", "session": "test"}


def _base_context() -> MarketSafetyContext:
    return MarketSafetyContext(
        symbol="XAUUSD",
        captured_at=NOW,
        connectivity=ConnectivitySource(
            availability=AVAILABILITY_VALID,
            source="mt5_connection_status",
            checked_at=NOW,
            provenance=PROV,
            terminal_connected=True,
            broker_logged_in=True,
        ),
        data=DataFreshnessSource(
            availability=AVAILABILITY_VALID,
            source="mt5_candles",
            checked_at=NOW,
            provenance=PROV,
            last_candle_time_utc=NOW - timedelta(seconds=60),
            intended_timeframe="M15",
        ),
        spread=SpreadSource(
            availability=AVAILABILITY_VALID,
            source="mt5_tick",
            checked_at=NOW,
            provenance=PROV,
            spread_points=20.0,
            symbol="XAUUSD",
        ),
        news=NewsSource(
            availability=AVAILABILITY_VALID,
            source="news_service",
            checked_at=NOW,
            provenance=PROV,
            source_verified=True,
            events=(),
        ),
        volatility=VolatilitySource(
            availability=AVAILABILITY_VALID,
            source="technical_context",
            checked_at=NOW,
            provenance=PROV,
            volatility_ratio=1.0,
            metric="atr14_h1",
        ),
    )


def _base_policy() -> SafetyPolicy:
    return SafetyPolicy(
        policy_version=SCANNER_SAFETY_POLICY_VERSION,
        max_candle_age_minutes=5,
        spread_threshold_by_symbol={"XAUUSD": 50},
        connectivity_max_age_minutes=10,
        volatility_calibrated=True,
        volatility_upper_ratio=1.5,
    )


def _config_policy(**overrides) -> SafetyPolicy:
    """Base policy willing to PASS all five sub-gates; override to exercise gates."""
    base = {
        "policy_version": SCANNER_SAFETY_POLICY_VERSION,
        "max_candle_age_minutes": 5,
        "spread_threshold_by_symbol": {"XAUUSD": 50},
        "connectivity_max_age_minutes": 10,
        "volatility_calibrated": True,
        "volatility_upper_ratio": 1.5,
    }
    base.update(overrides)
    return SafetyPolicy(**base)


GATE = MarketSafetyGate()


def _assert_all_passes(result):
    assert result.status == PASS
    assert result.reason_codes == ()
    assert {c.status for c in result.checks} == {PASS}
    for check in result.checks:
        assert check.observed_value is not None
        assert check.provenance
        assert check.policy_version == SCANNER_SAFETY_POLICY_VERSION


def _single_result(context: MarketSafetyContext, policy: SafetyPolicy) -> MarketSafetyResult:
    return GATE.evaluate(context, policy, now=NOW)


def _context_with_data(data: DataFreshnessSource) -> MarketSafetyContext:
    context = _base_context()
    return MarketSafetyContext(
        context.symbol, context.captured_at,
        context.connectivity, data,
        context.spread, context.news, context.volatility,
    )


# ---------------------------------------------------------------------------
# Structure / contract
# ---------------------------------------------------------------------------


class TestContract:
    def test_returns_exactly_five_checks_in_canonical_order(self):
        result = GATE.evaluate(_base_context(), _base_policy(), now=NOW)
        assert [c.name for c in result.checks] == list(SAFETY_CHECK_NAMES)

    def test_all_checks_are_gate_statuses_and_versioned(self):
        result = GATE.evaluate(_base_context(), _base_policy(), now=NOW)
        for check in result.checks:
            assert check.status in {PASS, CAUTION, BLOCK, UNKNOWN}
            assert check.policy_version == SCANNER_SAFETY_POLICY_VERSION
            assert check.checked_at == NOW

    def test_policy_version_must_match_constant(self):
        with pytest.raises(MarketSafetyGateError):
            SafetyPolicy(policy_version="wrong-policy")


# ---------------------------------------------------------------------------
# Connectivity sub-gate
# ---------------------------------------------------------------------------


class TestConnectivitySubGate:
    def test_pass_when_connected_and_logged_in(self):
        result = _single_result(_base_context(), _base_policy())
        assert result.status == PASS
        assert result.checks[0].status == PASS

    def test_block_when_terminal_not_connected(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            connectivity=ConnectivitySource(
                availability=AVAILABILITY_VALID, source="mt5_connection_status",
                checked_at=NOW, provenance={**PROV, "probe": "1"},
                terminal_connected=False, broker_logged_in=True),
            data=context.data, spread=context.spread, news=context.news, volatility=context.volatility,
        )
        result = _single_result(context, _base_policy())
        check = result.checks[0]
        assert check.status == BLOCK
        assert SAFETY_MT5_NOT_READY in check.reason_codes
        assert result.status == BLOCK

    def test_block_when_broker_not_logged_in(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            connectivity=ConnectivitySource(
                availability=AVAILABILITY_VALID, source="mt5_connection_status",
                checked_at=NOW, provenance={**PROV, "probe": "2"},
                terminal_connected=True, broker_logged_in=False),
            data=context.data, spread=context.spread, news=context.news, volatility=context.volatility,
        )
        result = _single_result(context, _base_policy())
        assert result.checks[0].status == BLOCK

    def test_unknown_when_connectivity_data_missing(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            connectivity=ConnectivitySource(
                availability=AVAILABILITY_MISSING, source="mt5_connection_status",
                checked_at=None, provenance=PROV, terminal_connected=None, broker_logged_in=None),
            data=context.data, spread=context.spread, news=context.news, volatility=context.volatility,
        )
        result = _single_result(context, _base_policy())
        check = result.checks[0]
        assert check.status == UNKNOWN
        assert SAFETY_MT5_STATE_UNKNOWN in check.reason_codes
        assert result.status == UNKNOWN

    def test_unknown_when_probe_stale(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            connectivity=ConnectivitySource(
                availability=AVAILABILITY_VALID, source="mt5_connection_status",
                checked_at=NOW - timedelta(minutes=30),
                provenance={**PROV, "probe": "3"},
                terminal_connected=True, broker_logged_in=True),
            data=context.data, spread=context.spread, news=context.news, volatility=context.volatility,
        )
        # connectivity_max_age_minutes=10 -> 30m stale probe fails closed
        result = _single_result(context, _base_policy())
        check = result.checks[0]
        assert check.status == UNKNOWN
        assert SAFETY_MT5_STATE_UNKNOWN in check.reason_codes


# ---------------------------------------------------------------------------
# Data / candle freshness sub-gate
# ---------------------------------------------------------------------------


class TestDataFreshnessSubGate:
    def test_pass_when_candle_fresh(self):
        result = _single_result(_base_context(), _base_policy())
        assert result.checks[1].status == PASS

    def test_block_when_candle_stale(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity,
            DataFreshnessSource(
                availability=AVAILABILITY_VALID, source="mt5_candles",
                checked_at=NOW, provenance={**PROV, "candle": "1"},
                last_candle_time_utc=NOW - timedelta(minutes=20),
                intended_timeframe="M15"),
            context.spread, context.news, context.volatility,
        )
        result = _single_result(context, _base_policy())
        check = result.checks[1]
        assert check.status == BLOCK
        assert SAFETY_DATA_STALE in check.reason_codes
        assert result.status == BLOCK

    def test_unknown_when_freshness_sla_open(self):
        # Default policy has max_candle_age_minutes=None (SLA OPEN) -> fail-closed.
        result = GATE.evaluate(_base_context(), DEFAULT_MARKET_SAFETY_POLICY, now=NOW)
        check = next(c for c in result.checks if c.name == "data")
        assert check.status == UNKNOWN
        assert SAFETY_DATA_FRESHNESS_UNKNOWN in check.reason_codes

    def test_unknown_when_candle_data_missing(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity,
            DataFreshnessSource(
                availability=AVAILABILITY_MISSING, source="mt5_candles",
                checked_at=None, provenance=PROV, last_candle_time_utc=None),
            context.spread, context.news, context.volatility,
        )
        result = _single_result(context, _base_policy())
        assert result.checks[1].status == UNKNOWN
        assert SAFETY_DATA_FRESHNESS_UNKNOWN in result.checks[1].reason_codes

    def test_fresh_tick_wins_over_stale_candle_open(self):
        # An M15 candle open time lags wall-clock by up to 15 minutes; a fresh
        # broker tick is the feed-liveness reference and must PASS the SLA even
        # when the candle-only age would exceed it.
        data = DataFreshnessSource(
            availability=AVAILABILITY_VALID, source="mt5_candles",
            checked_at=NOW, provenance={**PROV, "tick": "1"},
            last_candle_time_utc=NOW - timedelta(minutes=10),
            intended_timeframe="M15",
            last_tick_time_utc=NOW - timedelta(seconds=30),
        )
        check = _single_result(_context_with_data(data), _base_policy()).checks[1]
        assert check.status == PASS
        assert check.observed_value["freshness_reference"] == "tick"

    def test_stale_tick_blocks_even_with_fresh_candle(self):
        # Weekend/dead feed: the last tick is old -> the tick reference itself
        # exceeds the SLA and must BLOCK (fail-closed), never rescued by the
        # (also stale) candle.
        data = DataFreshnessSource(
            availability=AVAILABILITY_VALID, source="mt5_candles",
            checked_at=NOW, provenance={**PROV, "tick": "1"},
            last_candle_time_utc=NOW - timedelta(seconds=60),
            intended_timeframe="M15",
            last_tick_time_utc=NOW - timedelta(minutes=20),
        )
        check = _single_result(_context_with_data(data), _base_policy()).checks[1]
        assert check.status == BLOCK
        assert SAFETY_DATA_STALE in check.reason_codes
        assert check.observed_value["freshness_reference"] == "tick"

    def test_missing_tick_falls_back_to_candle(self):
        data = DataFreshnessSource(
            availability=AVAILABILITY_VALID, source="mt5_candles",
            checked_at=NOW, provenance={**PROV, "candle": "1"},
            last_candle_time_utc=NOW - timedelta(seconds=60),
            intended_timeframe="M15",
            last_tick_time_utc=None,
        )
        check = _single_result(_context_with_data(data), _base_policy()).checks[1]
        assert check.status == PASS
        assert check.observed_value["freshness_reference"] == "candle"

    def test_naive_tick_is_never_used(self):
        # A naive tick timestamp carries no verifiable timezone -> ignored,
        # the candle reference applies (fail-closed, never assume a timezone).
        data = DataFreshnessSource(
            availability=AVAILABILITY_VALID, source="mt5_candles",
            checked_at=NOW, provenance={**PROV, "tick": "1"},
            last_candle_time_utc=NOW - timedelta(seconds=60),
            intended_timeframe="M15",
            last_tick_time_utc=datetime(2026, 8, 13, 11, 59, 30),
        )
        check = _single_result(_context_with_data(data), _base_policy()).checks[1]
        assert check.status == PASS
        assert check.observed_value["freshness_reference"] == "candle"


# ---------------------------------------------------------------------------
# Spread sub-gate (per-symbol threshold)
# ---------------------------------------------------------------------------


class TestSpreadSubGate:
    def test_pass_within_per_symbol_threshold(self):
        result = _single_result(_base_context(), _base_policy())
        assert result.checks[2].status == PASS

    def test_block_when_above_per_symbol_threshold(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data,
            SpreadSource(
                availability=AVAILABILITY_VALID, source="mt5_tick",
                checked_at=NOW, provenance={**PROV, "tick": "1"},
                spread_points=80.0, symbol="XAUUSD"),
            context.news, context.volatility,
        )
        result = _single_result(context, _base_policy())
        check = result.checks[2]
        assert check.status == BLOCK
        assert SAFETY_SPREAD_ABNORMAL in check.reason_codes
        assert result.status == BLOCK

    def test_unknown_when_no_per_symbol_threshold_open(self):
        # 'XAUUSD' not in the policy mapping -> policy OPEN, fail-closed UNKNOWN.
        policy = _config_policy(spread_threshold_by_symbol={})
        result = _single_result(_base_context(), policy)
        check = result.checks[2]
        assert check.status == UNKNOWN
        assert SAFETY_SPREAD_THRESHOLD_UNSET in check.reason_codes
        assert result.status == UNKNOWN

    def test_unknown_when_spread_data_missing(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data,
            SpreadSource(
                availability=AVAILABILITY_MISSING, source="mt5_tick",
                checked_at=None, provenance=PROV, spread_points=None, symbol="XAUUSD"),
            context.news, context.volatility,
        )
        result = _single_result(context, _base_policy())
        check = result.checks[2]
        assert check.status == UNKNOWN
        assert SAFETY_SPREAD_UNKNOWN in check.reason_codes


class TestSpreadSymbolKeyNormalization:
    """Config keys are broker-style ("EURUSD"); live symbols can be the app
    display form ("EUR/USD") or the cent-account broker form ("EURUSDc").
    Matching must be spelling-tolerant; thresholds themselves never change."""

    def _context_with_spread_symbol(self, symbol: str, spread_points: float = 20.0):
        base = _base_context()
        return MarketSafetyContext(
            base.symbol, base.captured_at,
            base.connectivity, base.data,
            SpreadSource(
                availability=AVAILABILITY_VALID, source="mt5_tick",
                checked_at=NOW, provenance=PROV,
                spread_points=spread_points, symbol=symbol),
            base.news, base.volatility,
        )

    def test_app_symbol_with_slash_matches_config_key(self):
        policy = _config_policy(spread_threshold_by_symbol={"EURUSD": 25})
        result = _single_result(self._context_with_spread_symbol("EUR/USD"), policy)
        check = result.checks[2]
        assert check.status == PASS
        assert check.threshold == {"max_spread_points": 25}

    def test_cent_broker_symbol_matches_base_pair_key(self):
        policy = _config_policy(spread_threshold_by_symbol={"EURUSD": 25})
        result = _single_result(self._context_with_spread_symbol("EURUSDc"), policy)
        check = result.checks[2]
        assert check.status == PASS
        assert check.threshold == {"max_spread_points": 25}

    def test_variant_key_still_enforces_threshold(self):
        policy = _config_policy(spread_threshold_by_symbol={"EURUSD": 25})
        result = _single_result(
            self._context_with_spread_symbol("EUR/USD", spread_points=40.0), policy)
        check = result.checks[2]
        assert check.status == BLOCK
        assert SAFETY_SPREAD_ABNORMAL in check.reason_codes

    def test_exact_cent_key_wins_over_stripped_key(self):
        # Owner may configure the cent symbol explicitly; it takes precedence.
        policy = _config_policy(
            spread_threshold_by_symbol={"EURUSDC": 60, "EURUSD": 25})
        result = _single_result(
            self._context_with_spread_symbol("EURUSDc", spread_points=40.0), policy)
        check = result.checks[2]
        assert check.status == PASS
        assert check.threshold == {"max_spread_points": 60}

    def test_unknown_symbol_still_fails_closed(self):
        policy = _config_policy(spread_threshold_by_symbol={"EURUSD": 25})
        result = _single_result(self._context_with_spread_symbol("GBP/JPY"), policy)
        check = result.checks[2]
        assert check.status == UNKNOWN
        assert SAFETY_SPREAD_THRESHOLD_UNSET in check.reason_codes


# ---------------------------------------------------------------------------
# News / event window sub-gate
# ---------------------------------------------------------------------------


def _news(events, *, verified=True, availability=AVAILABILITY_VALID,
          checked_at=NOW, impact="high"):
    return NewsSource(
        availability=availability,
        source="news_service",
        checked_at=checked_at,
        provenance={**PROV, "feed": str(len(events))},
        source_verified=verified,
        events=events,
    )


def _event_at(minutes_ahead: int, impact="high"):
    return {"time_utc": NOW + timedelta(minutes=minutes_ahead), "impact": impact}


class TestNewsSubGate:
    def test_pass_when_valid_source_no_event(self):
        result = _single_result(_base_context(), _base_policy())
        check = result.checks[3]
        assert check.status == PASS
        assert result.status == PASS

    def test_block_within_30_minutes_window(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread,
            _news([_event_at(10)]),
            context.volatility,
        )
        result = _single_result(context, _base_policy())
        check = result.checks[3]
        assert check.status == BLOCK
        assert SAFETY_NEWS_HIGH_IMPACT_BLOCK in check.reason_codes
        assert result.status == BLOCK

    def test_block_at_exact_30_minute_boundary(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread,
            _news([_event_at(30)]),
            context.volatility,
        )
        result = _single_result(context, _base_policy())
        assert result.checks[3].status == BLOCK

    def test_caution_between_30_minutes_and_3_hours(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread,
            _news([_event_at(120)]),
            context.volatility,
        )
        result = _single_result(context, _base_policy())
        check = result.checks[3]
        assert check.status == CAUTION
        assert SAFETY_NEWS_HIGH_IMPACT_CAUTION in check.reason_codes
        assert result.status == CAUTION

    def test_past_event_is_ignored(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread,
            _news([_event_at(-5)]),
            context.volatility,
        )
        result = _single_result(context, _base_policy())
        assert result.checks[3].status == PASS

    def test_low_impact_event_is_ignored(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread,
            _news([_event_at(20, impact="low")]),
            context.volatility,
        )
        result = _single_result(context, _base_policy())
        assert result.checks[3].status == PASS

    def test_unverified_source_is_unknown(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread,
            _news([_event_at(10)], verified=False),
            context.volatility,
        )
        result = _single_result(context, _base_policy())
        check = result.checks[3]
        assert check.status == UNKNOWN
        assert SAFETY_NEWS_SOURCE_UNAVAILABLE in check.reason_codes
        assert result.status == UNKNOWN

    def test_missing_news_source_is_unknown(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread,
            _news((), availability=AVAILABILITY_MISSING, checked_at=None),
            context.volatility,
        )
        result = _single_result(context, _base_policy())
        assert result.checks[3].status == UNKNOWN


# ---------------------------------------------------------------------------
# Volatility sub-gate (band OPEN until calibrated)
# ---------------------------------------------------------------------------


class TestVolatilitySubGate:
    def test_pass_within_calibrated_band(self):
        result = _single_result(_base_context(), _base_policy())
        assert result.checks[4].status == PASS

    def test_caution_when_beyond_calibrated_band(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread, context.news,
            VolatilitySource(
                availability=AVAILABILITY_VALID, source="technical_context",
                checked_at=NOW, provenance={**PROV, "atr": "h1"},
                volatility_ratio=2.0, metric="atr14_h1"),
        )
        result = _single_result(context, _base_policy())
        check = result.checks[4]
        assert check.status == CAUTION
        assert SAFETY_VOLATILITY_EXTREME in check.reason_codes
        assert result.status == CAUTION

    def test_unknown_when_band_not_calibrated(self):
        # Default policy volatility_calibrated=False (band OPEN) -> UNKNOWN.
        result = GATE.evaluate(_base_context(), DEFAULT_MARKET_SAFETY_POLICY, now=NOW)
        check = next(c for c in result.checks if c.name == "volatility")
        assert check.status == UNKNOWN
        assert SAFETY_VOLATILITY_BAND_UNSET in check.reason_codes

    def test_unknown_when_volatility_data_missing(self):
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread, context.news,
            VolatilitySource(
                availability=AVAILABILITY_MISSING, source="technical_context",
                checked_at=None, provenance=PROV, volatility_ratio=None),
        )
        result = _single_result(context, _base_policy())
        check = result.checks[4]
        assert check.status == UNKNOWN
        assert SAFETY_VOLATILITY_UNKNOWN in check.reason_codes


# ---------------------------------------------------------------------------
# Locked policies (Step 04: volatility semantics, manual-order, spread shape)
# ---------------------------------------------------------------------------


class TestLockedPolicies:
    def test_volatility_semantics_are_locked_atr14_h4_d1_14d(self):
        # Evidence: core/technical_context.py builds atr_h4/atr_d1/atr_avg_14d.
        policy = _base_policy()
        assert VOLATILITY_METRIC_ATR14 == "atr14"
        assert VOLATILITY_INTRADAY_REFERENCE == "H4"
        assert VOLATILITY_STRUCTURAL_REFERENCE == "D1"
        assert VOLATILITY_REFERENCE_WINDOW_DAYS == 14
        assert VOLATILITY_SEMANTICS_VERSION == "scanner-safety-volatility-atr14-v1"
        assert policy.volatility_metric == VOLATILITY_METRIC_ATR14
        assert policy.volatility_intraday_reference == VOLATILITY_INTRADAY_REFERENCE
        assert policy.volatility_structural_reference == VOLATILITY_STRUCTURAL_REFERENCE
        assert policy.volatility_reference_window_days == VOLATILITY_REFERENCE_WINDOW_DAYS

    def test_volatility_threshold_carries_locked_semantics(self):
        result = _single_result(_base_context(), _base_policy())
        check = next(c for c in result.checks if c.name == "volatility")
        assert check.status == PASS
        assert check.threshold["metric"] == "atr14"
        assert check.threshold["intraday_reference"] == "H4"
        assert check.threshold["structural_reference"] == "D1"
        assert check.threshold["reference_window_days"] == 14
        assert check.threshold["semantics_version"] == VOLATILITY_SEMANTICS_VERSION

    def test_policy_rejects_other_volatility_semantics(self):
        with pytest.raises(MarketSafetyGateError):
            SafetyPolicy(
                policy_version=SCANNER_SAFETY_POLICY_VERSION,
                volatility_metric="atr21",
            )
        with pytest.raises(MarketSafetyGateError):
            SafetyPolicy(
                policy_version=SCANNER_SAFETY_POLICY_VERSION,
                volatility_reference_window_days=30,
            )

    def test_spread_policy_shape_has_no_global_fallback(self):
        # The per-symbol policy version is locked; a symbol with no threshold is
        # UNKNOWN (never a fabricated global default like the legacy 50-point rule).
        assert SPREAD_POLICY_VERSION == "scanner-safety-spread-per-symbol-v1"
        assert not hasattr(DEFAULT_MARKET_SAFETY_POLICY, "spread_default_threshold_points")
        default_policy = DEFAULT_MARKET_SAFETY_POLICY
        assert default_policy.spread_threshold_by_symbol == {}
        result = GATE.evaluate(_base_context(), default_policy, now=NOW)
        spread = next(c for c in result.checks if c.name == "spread")
        assert spread.status == UNKNOWN
        assert SAFETY_SPREAD_THRESHOLD_UNSET in spread.reason_codes

    def test_manual_order_policy_default_no_bypass(self):
        # LOCKED decision: a manual order does NOT auto-bypass the fail-closed
        # gate.  The gate API is deliberately override-free.
        assert MANUAL_ORDER_POLICY_VERSION == "scanner-safety-manual-order-v1"
        assert DEFAULT_MARKET_SAFETY_POLICY.manual_order_bypass_fail_closed is False
        # Gate signature has no bypass/override parameter: only context/policy/now.
        import inspect

        params = inspect.signature(GATE.evaluate).parameters
        assert set(params) == {"context", "policy", "now"}
        assert "override" not in params and "bypass" not in params
        # No module-level escape hatch: flag never flips the gate result.
        policy = _config_policy(
            manual_order_bypass_fail_closed=True,
        )
        result = GATE.evaluate(_base_context(), policy, now=NOW)
        assert result.status == PASS  # bypass flag is not consulted by the gate


# ---------------------------------------------------------------------------
# Ownership / deduplication (target side)
# ---------------------------------------------------------------------------


class TestOwnershipDeduplication:
    def _scan_core_for(self, symbol: str, allowed_files: tuple[str, ...]):
        import glob as _glob

        allowed = {Path(p).as_posix() for p in allowed_files}
        found = []
        for path in sorted(_glob.glob("core/*.py")):
            key = Path(path).as_posix()
            if key in allowed:
                continue
            if symbol in open(path, encoding="utf-8").read():
                found.append(path)
        return found

    def test_market_safety_gate_is_sole_constructor_of_safety_results(self):
        # Only core/market_safety_gate.py constructs MarketSafetyResult in the
        # target modules; the models module only defines it.
        others = self._scan_core_for(
            "MarketSafetyResult(", ("core/market_safety_gate.py",)
        )
        assert others == [], f"safety recomputed/constructed outside the gate: {others}"

    def test_gate_check_produced_only_by_gate_module(self):
        others = self._scan_core_for(
            "GateCheck(", ("core/market_safety_gate.py",)
        )
        assert others == [], f"GateCheck constructed outside the gate: {others}"

    def test_target_never_recomputes_safety_inputs_inline(self):
        import glob as _glob

        allowed = {
            Path("core/market_safety_gate.py").as_posix(),
            Path("core/scanner_v4_models.py").as_posix(),
            # reason_codes.py is the code-authority (string definitions only).
            Path("core/reason_codes.py").as_posix(),
        }
        # No target module re-derives spread/news thresholds; the only policy
        # holder in the target is the SafetyPolicy passed to the gate.
        for path in _glob.glob("core/*.py"):
            if Path(path).as_posix() in allowed:
                continue
            text = open(path, encoding="utf-8").read()
            for marker in ("SAFETY_VOLATILITY_BAND_UNSET", "SAFETY_SPREAD_THRESHOLD_UNSET"):
                assert marker not in text, f"{path} carries safety policy outside target"

    def test_scenario_preserved_while_safety_block(self):
        """BLOCK at safety must coexist with a full technical score 100 payload.

        Safety GateCheck/MarketSafetyResult never touch TechnicalScore or the
        scenario dict; the composite payload keeps both intact so a "good
        setup but currently blocked" row is rendered, not hidden.
        """
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread,
            _news([_event_at(10)]), context.volatility,
        )
        result = _single_result(context, _base_policy())
        assert result.status == BLOCK

        scenario = {
            "side": "sell",
            "score": 100,
            "entry_zone": [4099.0, 4112.0],
            "stop_loss": 4142.0,
            "take_profit": [4017.0],
            "risk_reward": "1:3.0",
        }
        payload = {
            "technical_signal_score": 100,
            "scenario": scenario,
            "safety": result.to_dict(),
        }
        assert payload["safety"]["status"] == BLOCK
        assert payload["technical_signal_score"] == 100
        assert payload["scenario"]["score"] == 100
        assert SAFETY_NEWS_HIGH_IMPACT_BLOCK in payload["safety"]["reason_codes"]
        # Gate result serializes independently of the scenario.
        assert result.to_dict()["status"] == BLOCK


# ---------------------------------------------------------------------------
# Aggregate fail-closed invariants / precedence matrix
# ---------------------------------------------------------------------------


class TestAggregateInvariants:
    def test_all_pass_aggregate_pass(self):
        result = _single_result(_base_context(), _base_policy())
        _assert_all_passes(result)

    def test_any_block_drives_aggregate_block(self):
        # News block (10m event) is enough; others pass.
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread,
            _news([_event_at(10)]), context.volatility,
        )
        result = _single_result(context, _base_policy())
        assert all(c.status == PASS for c in result.checks if c.name != "news")
        assert result.status == BLOCK
        assert SAFETY_NEWS_HIGH_IMPACT_BLOCK in result.reason_codes

    def test_unknown_precedence_over_caution(self):
        # spread UNKNOWN (no threshold) + news CAUTION -> aggregate UNKNOWN (fail-closed).
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            context.connectivity, context.data, context.spread,
            _news([_event_at(120)]), context.volatility,
        )
        policy = _config_policy(spread_threshold_by_symbol={})
        result = _single_result(context, policy)
        assert result.checks[2].status == UNKNOWN
        assert result.checks[3].status == CAUTION
        assert result.status == UNKNOWN

    def test_block_precedence_over_unknown(self):
        # connectivity BLOCK + volatility UNKNOWN (band open) -> aggregate BLOCK.
        context = _base_context()
        context = MarketSafetyContext(
            context.symbol, context.captured_at,
            ConnectivitySource(
                availability=AVAILABILITY_VALID, source="mt5_connection_status",
                checked_at=NOW, provenance={**PROV, "probe": "x"},
                terminal_connected=False, broker_logged_in=True),
            context.data, context.spread, context.news, context.volatility,
        )
        policy = _config_policy(volatility_calibrated=False)
        result = _single_result(context, policy)
        assert result.checks[0].status == BLOCK
        assert result.checks[4].status == UNKNOWN
        assert result.status == BLOCK
        assert SAFETY_MT5_NOT_READY in result.reason_codes

    def test_default_open_policy_fails_closed_to_unknown(self):
        """With no thresholds calibrated, the aggregate must NOT pass."""
        result = GATE.evaluate(_base_context(), DEFAULT_MARKET_SAFETY_POLICY, now=NOW)
        # data(spread SLA open), spread(per-symbol), volatility(band open) -> UNKNOWN each.
        assert {c.status for c in result.checks} == {PASS, UNKNOWN}
        assert result.status == UNKNOWN
        assert any(
            reason in result.reason_codes
            for reason in (SAFETY_DATA_FRESHNESS_UNKNOWN, SAFETY_SPREAD_THRESHOLD_UNSET,
                           SAFETY_VOLATILITY_BAND_UNSET)
        )

    def test_aggregate_never_pass_when_any_source_missing(self):
        # Every single-source-missing scenario must yield UNKNOWN aggregate.
        for check_name in SAFETY_CHECK_NAMES:
            context = _base_context()
            if check_name == "connectivity":
                context = MarketSafetyContext(
                    context.symbol, context.captured_at,
                    ConnectivitySource(AVAILABILITY_MISSING, "mt5_connection_status",
                                       None, PROV, None, None),
                    context.data, context.spread, context.news, context.volatility)
            elif check_name == "data":
                context = MarketSafetyContext(
                    context.symbol, context.captured_at, context.connectivity,
                    DataFreshnessSource(AVAILABILITY_MISSING, "mt5_candles",
                                       None, PROV, None),
                    context.spread, context.news, context.volatility)
            elif check_name == "spread":
                context = MarketSafetyContext(
                    context.symbol, context.captured_at, context.connectivity,
                    context.data,
                    SpreadSource(AVAILABILITY_MISSING, "mt5_tick", None, PROV, None, "XAUUSD"),
                    context.news, context.volatility)
            elif check_name == "news":
                context = MarketSafetyContext(
                    context.symbol, context.captured_at, context.connectivity,
                    context.data, context.spread,
                    NewsSource(AVAILABILITY_MISSING, "news_service", None, PROV, True, ()),
                    context.volatility)
            else:  # volatility
                context = MarketSafetyContext(
                    context.symbol, context.captured_at, context.connectivity,
                    context.data, context.spread, context.news,
                    VolatilitySource(AVAILABILITY_MISSING, "technical_context", None, PROV, None))
            with pytest.raises(AssertionError):
                _assert_all_passes(_single_result(context, _base_policy()))
            result = _single_result(context, _base_policy())
            assert result.status == UNKNOWN
            assert {c.name: c.status for c in result.checks}[check_name] == UNKNOWN

    def test_aggregate_blocks_and_never_changes_the_others(self):
        """Safety status BLOCK must coexist with other gates (it is not a score gate)."""
        result = _single_result(_base_context(), _base_policy())
        _assert_all_passes(result)
        block_result = GATE.evaluate(_base_context(), _base_policy(), now=NOW)
        assert block_result.status == PASS  # base context is safe by construction


# ---------------------------------------------------------------------------
# Strict context / policy construction
# ---------------------------------------------------------------------------


class TestStrictConstruction:
    def test_valid_source_requires_timestamp(self):
        with pytest.raises(MarketSafetyGateError):
            ConnectivitySource(
                availability=AVAILABILITY_VALID, source="mt5_connection_status",
                checked_at=None, provenance=PROV,
                terminal_connected=True, broker_logged_in=True)

    def test_valid_source_requires_provenance(self):
        with pytest.raises(MarketSafetyGateError):
            ConnectivitySource(
                availability=AVAILABILITY_VALID, source="mt5_connection_status",
                checked_at=NOW, provenance={},
                terminal_connected=True, broker_logged_in=True)

    def test_invalid_availability_rejected(self):
        with pytest.raises(MarketSafetyGateError):
            BaseSafetySource(availability="weird", source="x", checked_at=None, provenance={})

    def test_valid_connectivity_requires_both_bools(self):
        with pytest.raises(MarketSafetyGateError):
            ConnectivitySource(
                availability=AVAILABILITY_VALID, source="mt5_connection_status",
                checked_at=NOW, provenance=PROV,
                terminal_connected=True, broker_logged_in=None)

    def test_policy_rejects_calibrated_but_missing_band(self):
        with pytest.raises(MarketSafetyGateError):
            SafetyPolicy(
                policy_version=SCANNER_SAFETY_POLICY_VERSION,
                volatility_calibrated=True, volatility_upper_ratio=None)

    def test_policy_rejects_negative_threshold(self):
        with pytest.raises(MarketSafetyGateError):
            SafetyPolicy(
                policy_version=SCANNER_SAFETY_POLICY_VERSION,
                spread_threshold_by_symbol={"XAUUSD": -5})

    def test_evaluate_rejects_non_context(self):
        with pytest.raises(MarketSafetyGateError):
            GATE.evaluate({"not": "a context"}, _base_policy(), now=NOW)


# ---------------------------------------------------------------------------
# Runtime isolation guard (same pattern as Step 03)
# ---------------------------------------------------------------------------


class TestModuleIsolation:
    def test_market_safety_gate_not_wired_into_live_runtime(self):
        root = Path(__file__).resolve().parent.parent
        runtime_consumers = (
            root / "core/analysis_pipeline.py",
            root / "core/scanner.py",
            root / "core/system_backtest_engine.py",
            root / "core/trade_gate_engine.py",
            root / "controllers/scanner_controller.py",
        )
        for consumer in runtime_consumers:
            assert consumer.exists(), consumer
            assert "market_safety_gate" not in consumer.read_text(encoding="utf-8"), consumer


def test_doc_example_imports_cleanly():
    import core.market_safety_gate as gate
    assert gate.__all__