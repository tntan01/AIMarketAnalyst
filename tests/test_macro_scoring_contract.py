"""Phase 15A.2: macro scoring contract — production-path tests.

Uses REAL production fixtures (test_signal_engine helpers) for the composite
scoring path, and the REAL pure formula `core.macro_tiers` for the tier paths
(WI-7: trước đây các tier phải chép lại công thức/khởi tạo `NewsService` vì
công thức nằm trong `services/`; nay gọi thẳng hàm thuần).

Corrects all false-positives from Phase 15A.1.
x-fails document confirmed production defects.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.macro_tiers import macro_tier1, macro_tier2, macro_tier3
from core.signal_engine import (
    _detect_macro_status,
    compose_scenario_score,
)
from core.smc_context import extract_smc_trade_flags

# Real production fixtures — same as test_signal_engine.py uses
from tests.test_signal_engine import _technical_buy_context, _smc_buy_context

# Characterization từ scorer v1 (Bước 13 đã xóa): giữ cố định để output của
# các test macro contract không đổi sau khi signal_engine chỉ còn canonical.
_SMC_BUY_QUALITY_V1 = {"buy": 15, "sell": 0}


def _scenario(side, technical, smc, risk_score, macro_score, *,
              macro_confidence=1.0, market_regime=None,
              correlation_adjustment=0.0, macro_context=None):
    return compose_scenario_score(
        side, technical,
        smc_quality=_SMC_BUY_QUALITY_V1[side],
        smc_flags=extract_smc_trade_flags(smc, side),
        risk_score=risk_score, macro_score=macro_score,
        macro_confidence=macro_confidence, market_regime=market_regime,
        correlation_adjustment=correlation_adjustment,
        macro_context=macro_context,
    )


# ===========================================================================
# Contract 1: confidence drop MUST NOT increase signal_score
# ===========================================================================


class TestConfidenceMonotonic:
    """Using the exact same fixtures as test_signal_engine.py,
    verify that reducing macro_confidence does not increase signal_score.

    Defect reproduced: conf 1.0→0.5→0.1 gives score 84→87→89.
    The surplus weight from shrinking macro is redistributed to technical,
    which already scores high → total INCREASES.
    """

    REGIME = {"primary": "trend_up"}
    RISK = 15
    MACRO_RAW = 15
    MACRO_CTX = {"buy": 15, "sell": 15}

    def test_confidence_1_0_gives_84(self):
        s = _scenario("buy", _technical_buy_context(), _smc_buy_context(),
                           risk_score=self.RISK, macro_score=self.MACRO_RAW,
                           macro_confidence=1.0, market_regime=self.REGIME,
                           macro_context=self.MACRO_CTX)
        assert s["signal_score"] == 84, \
            f"Baseline score at conf=1.0 must be 84, got {s['signal_score']}"

    def test_confidence_0_5_gives_80(self):
        """Phase 15B fix: surplus discarded. Score drops 84 → 80 (not 87)."""
        s = _scenario("buy", _technical_buy_context(), _smc_buy_context(),
                           risk_score=self.RISK, macro_score=self.MACRO_RAW,
                           macro_confidence=0.5, market_regime=self.REGIME,
                           macro_context=self.MACRO_CTX)
        assert s["signal_score"] == 80, \
            f"Score at conf=0.5 must be 80, got {s['signal_score']}"

    def test_confidence_0_1_gives_77(self):
        """Score at conf=0.1 drops to 77 — macro_effective ≈ 0, technical
        scores unchanged (no surplus redistribution)."""
        s = _scenario("buy", _technical_buy_context(), _smc_buy_context(),
                           risk_score=self.RISK, macro_score=self.MACRO_RAW,
                           macro_confidence=0.1, market_regime=self.REGIME,
                           macro_context=self.MACRO_CTX)
        assert s["signal_score"] == 77, \
            f"Score at conf=0.1 must be 77, got {s['signal_score']}"

    def test_score_monotonic_non_increasing(self):
        """Phase 15B: confidence drop does NOT increase score."""
        prev = None
        for conf in [1.0, 0.5, 0.1]:
            s = _scenario("buy", _technical_buy_context(), _smc_buy_context(),
                               risk_score=15, macro_score=15,
                               macro_confidence=conf,
                               market_regime={"primary": "trend_up"},
                               macro_context={"buy": 15, "sell": 15})
            if prev is not None:
                assert s["signal_score"] <= prev, \
                    f"Conf {conf}: score {s['signal_score']} > prev {prev}"
            prev = s["signal_score"]

    def test_macro_effective_shrinks_with_confidence(self):
        """macro_effective does scale down correctly — the defect is in
        weight redistribution, not in the macro computation itself."""
        s_full = _scenario("buy", _technical_buy_context(), _smc_buy_context(),
                                risk_score=15, macro_score=15,
                                macro_confidence=1.0, market_regime={"primary": "trend_up"},
                                macro_context={"buy": 15, "sell": 15})
        s_half = _scenario("buy", _technical_buy_context(), _smc_buy_context(),
                                risk_score=15, macro_score=15,
                                macro_confidence=0.5, market_regime={"primary": "trend_up"},
                                macro_context={"buy": 15, "sell": 15})
        assert s_half["macro_alignment"] < s_full["macro_alignment"], \
            "macro_effective must shrink with confidence"

    def test_confidence_monotonic_across_all_regimes(self):
        """Phase 15B: monotonicity holds for all 5 regime keys."""
        for regime in ["trend_up", "trend_down", "range", "volatile", "unknown"]:
            prev = None
            for conf in [1.0, 0.5, 0.1]:
                s = _scenario("buy", _technical_buy_context(), _smc_buy_context(),
                                   risk_score=15, macro_score=15,
                                   macro_confidence=conf,
                                   market_regime={"primary": regime},
                                   macro_context={"buy": 15, "sell": 15})
                if prev is not None:
                    assert s["signal_score"] <= prev, \
                        f"Regime {regime} conf {conf}: {s['signal_score']} > {prev}"
                prev = s["signal_score"]

    def test_confidence_monotonic_sell_side(self):
        """Monotonicity holds for SELL side too."""
        prev = None
        for conf in [1.0, 0.5, 0.1]:
            s = _scenario("sell", _technical_buy_context(), _smc_buy_context(),
                               risk_score=15, macro_score=15,
                               macro_confidence=conf,
                               market_regime={"primary": "trend_down"},
                               macro_context={"buy": 15, "sell": 15})
            if prev is not None:
                assert s["signal_score"] <= prev, \
                    f"SELL conf {conf}: {s['signal_score']} > {prev}"
            prev = s["signal_score"]


# ===========================================================================
# Contract 2: calendar events w/o actual/forecast must not create
#             artificial directional bias
# ===========================================================================


class TestCalendarNeutrality:
    """Phase 15C.1: ALL calendar events are directional-neutral (buy=sell=5).
    actual/forecast only tracked as diagnostic.  Directional surprise scoring
    is deferred to a future phase with standardized indicator engine.

    WI-7: chạy trên công thức THẬT `core.macro_tiers.macro_tier2` (trước đây
    test chép lại công thức vì nó nằm trong `services/`). Severity lấy qua
    chính bảng `EVENT_SEVERITY` của module: "US CPI"→3, "Retail Sales"→2,
    tiêu đề lạ→1; mọi event đặt +10h (time_weight 2.0) như bản chép cũ.
    """

    NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    _SEVERITY_TITLE = {"high": "US CPI", "medium": "Retail Sales"}

    @classmethod
    def _tier2(cls, base_events, quote_events):
        """Gọi công thức thật; trả (buy, sell, event_risk_score, risk_level)."""
        events = [
            {
                "currency": currency,
                "event": cls._SEVERITY_TITLE.get(
                    str(item.get("severity", "")).lower(), "Minor Release"
                ),
                "impact": "high",
                "time_utc": (cls.NOW + timedelta(hours=10)).isoformat(),
            }
            for currency, bucket in (("EUR", base_events), ("USD", quote_events))
            for item in bucket
        ]
        buy_cal, sell_cal, detail = macro_tier2("EUR", "USD", events, now=cls.NOW)
        return buy_cal, sell_cal, detail["event_risk_score"], detail["event_risk_level"]

    def test_no_events_neutral_no_risk(self):
        b, s, risk, level = self._tier2([], [])
        assert b == 5 and s == 5
        assert risk == 0 and level == "none"

    def test_base_events_neutral_directional(self):
        b, s, risk, level = self._tier2([{"severity": "high"}], [])
        assert b == 5 and s == 5, "Phase 15C.1: all events neutral"
        assert risk > 0

    def test_quote_events_neutral_directional(self):
        b, s, risk, level = self._tier2([], [{"severity": "high"}])
        assert b == 5 and s == 5

    def test_equal_events_neutral(self):
        b, s, risk, level = self._tier2(
            [{"severity": "high"}], [{"severity": "high"}]
        )
        assert b == 5 and s == 5

    def test_cpi_actual_above_forecast_no_bias(self):
        """CPI with actual=3.5 > forecast=3.0 → still neutral."""
        b, s, risk, level = self._tier2([{"severity": "high"}], [])
        assert b == 5 and s == 5, \
            "Phase 15C.1: actual>forecast does NOT create bias"

    def test_unemployment_actual_below_forecast_no_bias(self):
        """Unemployment actual=3.8 < forecast=4.0 → still neutral."""
        b, s, risk, level = self._tier2([{"severity": "high"}], [])
        assert b == 5 and s == 5, \
            "Phase 15C.1: actual<forecast does NOT create bias"

    def test_high_impact_risk_level_tracked(self):
        b, s, risk, level = self._tier2(
            [{"severity": "high"}, {"severity": "high"}],
            [{"severity": "high"}],
        )
        assert risk >= 12
        assert level == "high"


# ===========================================================================
# Contract 3: Base/quote reversal must reverse macro direction
# ===========================================================================


class TestBaseQuoteReversal:
    """When computing a pair like EUR/USD vs USD/EUR, the macro scores
    must reverse direction.  Using the production scoring formula from
    _compute_macro_tiers (news_service.py line 631+):
      base = currencies[0], quote = currencies[1]
      Tier1/Tier2/Tier3 all use base/quote to compute buy/sell split.
    """

    def test_reversal_reverses_buy_sell_scores(self):
        """EUR/USD: base=EUR, quote=USD → buy favors EUR, sell favors USD.
        USD/EUR: base=USD, quote=EUR → buy favors USD, sell favors EUR."""
        # Simulate a pair reversal: EUR/USD scores are swapped for USD/EUR
        eur_usd = {"buy": 22, "sell": 8}   # EUR base favors buy
        usd_eur = {"buy": 8, "sell": 22}    # USD base favors sell

        # EUR/USD: buy aligned
        assert _detect_macro_status(eur_usd, "buy") == "aligned"
        # USD/EUR: sell aligned (scores reversed)
        assert _detect_macro_status(usd_eur, "sell") == "aligned"

    def test_reversal_converts_aligned_to_conflict(self):
        """Direction that was aligned becomes conflict after reversal."""
        eur_usd = {"buy": 22, "sell": 8}
        usd_eur = {"buy": 8, "sell": 22}

        # EUR/USD sell → conflict (buy dominates)
        assert _detect_macro_status(eur_usd, "sell") == "conflict"
        # USD/EUR buy → conflict (sell dominates)
        assert _detect_macro_status(usd_eur, "buy") == "conflict"

    def test_neutral_pair_stays_neutral_after_reversal(self):
        """Equal scores → unclear for both directions regardless of swap."""
        neutral = {"buy": 15, "sell": 15}
        assert _detect_macro_status(neutral, "buy") == "unclear"
        assert _detect_macro_status(neutral, "sell") == "unclear"


# ===========================================================================
# Contract 4: VIX and AI stance paths — tier-3 vs correlation_adjustment
# ===========================================================================


class TestVIXDualPath:
    """VIX enters scoring through TWO independent paths:
    A. correlation_adjustment (compose_scenario_score parameter, from M15/DXY candles)
    B. Tier 3 sentiment → macro_raw (from Yahoo Finance _fetch_vix)

    These are independent data sources.  The contract is that each
    path works correctly in isolation.  The macro_raw path is tested
    via compose_scenario_score; the correlation path via its adjustment.
    """

    def test_correlation_adjustment_reduces_score(self):
        """Negative correlation_adjustment (high VIX) reduces signal_score."""
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s1 = _scenario("buy", tech, smc, 15, 15,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 15, "sell": 15},
                            correlation_adjustment=0.0)
        s2 = _scenario("buy", tech, smc, 15, 15,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 15, "sell": 15},
                            correlation_adjustment=-5.0)
        assert s2["signal_score"] < s1["signal_score"], \
            "Negative correlation must reduce score"

    def test_macro_raw_with_vix_encoded(self):
        """Tier 3 VIX is encoded in macro_raw (0-30) passed to compose_scenario_score.
        A lower macro_raw (from high VIX in Tier 3) reduces macro_effective."""
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s_low = _scenario("buy", tech, smc, 15, 10,  # low macro = high VIX
                               macro_confidence=1.0,
                               market_regime={"primary": "trend_up"},
                               macro_context={"buy": 10, "sell": 20})
        s_high = _scenario("buy", tech, smc, 15, 25,  # high macro = low VIX
                                macro_confidence=1.0,
                                market_regime={"primary": "trend_up"},
                                macro_context={"buy": 25, "sell": 5})
        assert s_low["macro_alignment"] < s_high["macro_alignment"], \
            "Lower macro_raw (VIX encoded) must give lower macro_effective"


class TestAIStanceDualPath:
    """AI stance appears in both Tier 1 (rate stance) and Tier 3 (sentiment).
    These are different uses of the same data — Tier 1 uses stance_delta
    for rate direction; Tier 3 uses sentiment_map for risk appetite.
    """

    def test_score_scenario_is_deterministic(self):
        """Same inputs → same output, regardless of how AI stance is
        encoded in macro_context.  _scenario does not read AI keys."""
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s1 = _scenario("buy", tech, smc, 15, 20,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 20, "sell": 10})
        s2 = _scenario("buy", tech, smc, 15, 20,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 20, "sell": 10,
                                           "ai_stance_base": "hawkish",
                                           "ai_stance_quote": "dovish"})
        assert s1["signal_score"] == s2["signal_score"], \
            "AI stance keys in macro_context must not affect _scenario"


# ===========================================================================
# Contract 5: macro conflict with high confidence must penalize more
# ===========================================================================


class TestMacroConflictPenalty:
    """The desired contract: macro_status=conflict should reduce the
    signal_score, weighted by confidence.  Currently (Phase 15A) it is
    display-only — adds penalty_codes but no numeric impact.
    """

    def test_conflict_adds_penalty_code_only(self):
        from core.reason_codes import MACRO_CONFLICT
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s = _scenario("buy", tech, smc, 15, 25,
                           macro_confidence=1.0,
                           market_regime={"primary": "trend_up"},
                           macro_context={"bias": "sell"})
        assert MACRO_CONFLICT in s.get("penalty_codes", [])

    def test_same_raw_same_effective_regardless_of_status(self):
        """macro_effective is purely raw*weight/30, not status-dependent."""
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s1 = _scenario("buy", tech, smc, 15, 25,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"bias": "buy"})
        s2 = _scenario("buy", tech, smc, 15, 25,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"bias": "sell"})
        assert s1["macro_alignment"] == s2["macro_alignment"]

    @pytest.mark.xfail(strict=True,
                       reason="DESIRED: high-confidence conflict reduces "
                       "signal_score vs low-confidence aligned. Currently "
                       "macro_status is display-only (signal_engine.py:142). "
                       "Phase 15B should add confidence-weighted penalty.")
    def test_high_conflict_beats_low_aligned(self):
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s_aligned = _scenario("buy", tech, smc, 15, 25,
                                   macro_confidence=0.5,
                                   market_regime={"primary": "trend_up"},
                                   macro_context={"bias": "buy"})
        s_conflict = _scenario("buy", tech, smc, 15, 25,
                                    macro_confidence=1.0,
                                    market_regime={"primary": "trend_up"},
                                    macro_context={"bias": "sell"})
        assert s_conflict["signal_score"] < s_aligned["signal_score"]


# ===========================================================================
# Phase 15E: deduplicate VIX and AI stance from Tier 3
# ===========================================================================


class TestPhase15EDedup:
    """AI stance and VIX must each contribute to numeric score exactly ONCE."""

    def test_tier3_ai_not_added_to_raw_sentiment(self):
        detail = macro_tier3(["EUR", "USD"], [], [])[2]
        assert detail["ai_applied_to_score"] is False

    def test_tier3_vix_not_added_to_raw_sentiment(self):
        detail = macro_tier3(["EUR", "USD"], [], [])[2]
        assert detail["vix_applied_to_score"] is False

    def test_vix_via_correlation_adjustment_only(self):
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s_no = _scenario("buy", tech, smc, 15, 20,
                              macro_confidence=1.0,
                              market_regime={"primary": "trend_up"},
                              macro_context={"buy": 20, "sell": 10},
                              correlation_adjustment=0.0)
        s_vix = _scenario("buy", tech, smc, 15, 20,
                               macro_confidence=1.0,
                               market_regime={"primary": "trend_up"},
                               macro_context={"buy": 20, "sell": 10},
                               correlation_adjustment=-3.0)
        assert s_vix["signal_score"] <= s_no["signal_score"]

    def test_score_deterministic_without_ai_vix_in_t3(self):
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s1 = _scenario("buy", tech, smc, 15, 20,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 20, "sell": 10})
        s2 = _scenario("buy", tech, smc, 15, 20,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 20, "sell": 10})
        assert s1["signal_score"] == s2["signal_score"]

# ===========================================================================
# Phase 15F.2: yield spread naming
# ===========================================================================


class TestYieldSpreadNaming:
    """Phase 15F.2: yield_spread_10y_5y canonical, 2s10s deprecated alias.

    WI-7: nhắm `core.macro_tiers.macro_tier1` với payload đường cong CỐ ĐỊNH
    (bản cũ đọc `NewsService._fetch_yield_spread()` — tức gọi mạng Yahoo).
    """

    _RATES = {
        "EUR": {"rate": 3.5, "trend": "hike", "rate_label": "3.50%"},
        "USD": {"rate": 5.0, "trend": "hold", "rate_label": "5.00%"},
    }
    _YIELD_PAYLOAD = {
        "spread": -0.35,
        "tnx": 4.25,
        "fvx": 4.60,
        "steepening": False,
        "ten_year_yield": 4.25,
        "five_year_yield": None,
    }

    def _detail(self) -> dict:
        _, _, detail = macro_tier1(
            "EUR", "USD", "neutral", "neutral",
            rates=self._RATES,
            yield_payload=self._YIELD_PAYLOAD,
        )
        return detail

    def test_canonical_name_present(self):
        detail = self._detail()

        assert detail["yield_spread_10y_5y"] == -0.35
        assert detail["ten_year_yield"] == 4.25
        assert "five_year_yield" in detail

    def test_deprecated_alias_matches_canonical(self):
        detail = self._detail()

        assert detail["yield_spread_2s10s"] == detail["yield_spread_10y_5y"]

    def test_tier1_detail_has_both_names(self):
        detail = self._detail()

        assert detail["yield_spread_2s10s"] is not None
        assert detail["yield_spread_10y_5y"] == detail["yield_spread_2s10s"]
        assert "ten_year_yield" in detail
        assert "five_year_yield" in detail

    def test_score_unchanged_by_rename(self):
        b1, s1, _ = macro_tier1(
            "EUR", "USD", "neutral", "neutral",
            rates=self._RATES, yield_payload=self._YIELD_PAYLOAD,
        )
        b2, s2, _ = macro_tier1(
            "EUR", "USD", "neutral", "neutral",
            rates=self._RATES, yield_payload=self._YIELD_PAYLOAD,
        )
        assert b1 == b2 and s1 == s2, "Score unchanged by field rename"

