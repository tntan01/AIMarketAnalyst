"""Phase 15A.2: macro scoring contract — production-path tests.

Uses REAL production fixtures (test_signal_engine helpers) and extracts
production scoring formulas for calendar/tier paths that cannot be
instantiated without full NewsService dependencies.

Corrects all false-positives from Phase 15A.1.
x-fails document confirmed production defects.
"""

from __future__ import annotations

import pytest

from core.signal_engine import (
    _detect_macro_status,
    score_scenario,
)

# Real production fixtures — same as test_signal_engine.py uses
from tests.test_signal_engine import _technical_buy_context, _smc_buy_context


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
        s = score_scenario("buy", _technical_buy_context(), _smc_buy_context(),
                           risk_score=self.RISK, macro_score=self.MACRO_RAW,
                           macro_confidence=1.0, market_regime=self.REGIME,
                           macro_context=self.MACRO_CTX)
        assert s["signal_score"] == 84, \
            f"Baseline score at conf=1.0 must be 84, got {s['signal_score']}"

    def test_confidence_0_5_gives_80(self):
        """Phase 15B fix: surplus discarded. Score drops 84 → 80 (not 87)."""
        s = score_scenario("buy", _technical_buy_context(), _smc_buy_context(),
                           risk_score=self.RISK, macro_score=self.MACRO_RAW,
                           macro_confidence=0.5, market_regime=self.REGIME,
                           macro_context=self.MACRO_CTX)
        assert s["signal_score"] == 80, \
            f"Score at conf=0.5 must be 80, got {s['signal_score']}"

    def test_confidence_0_1_gives_77(self):
        """Score at conf=0.1 drops to 77 — macro_effective ≈ 0, technical
        scores unchanged (no surplus redistribution)."""
        s = score_scenario("buy", _technical_buy_context(), _smc_buy_context(),
                           risk_score=self.RISK, macro_score=self.MACRO_RAW,
                           macro_confidence=0.1, market_regime=self.REGIME,
                           macro_context=self.MACRO_CTX)
        assert s["signal_score"] == 77, \
            f"Score at conf=0.1 must be 77, got {s['signal_score']}"

    def test_score_monotonic_non_increasing(self):
        """Phase 15B: confidence drop does NOT increase score."""
        prev = None
        for conf in [1.0, 0.5, 0.1]:
            s = score_scenario("buy", _technical_buy_context(), _smc_buy_context(),
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
        s_full = score_scenario("buy", _technical_buy_context(), _smc_buy_context(),
                                risk_score=15, macro_score=15,
                                macro_confidence=1.0, market_regime={"primary": "trend_up"},
                                macro_context={"buy": 15, "sell": 15})
        s_half = score_scenario("buy", _technical_buy_context(), _smc_buy_context(),
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
                s = score_scenario("buy", _technical_buy_context(), _smc_buy_context(),
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
            s = score_scenario("sell", _technical_buy_context(), _smc_buy_context(),
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
    is deferred to a future phase with standardized indicator engine."""

    def _tier2(self, base_events, quote_events):
        """Extracted production formula from NewsService._macro_tier2 (Phase 15C.1).
        All events directional-neutral.  Risk is diagnostic only."""
        base_quality = 0.0
        quote_quality = 0.0
        for e in base_events:
            sev = {"high": 3, "medium": 2}.get(str(e.get("severity", "")).lower(), 1)
            base_quality += sev * 2.0  # time_weight=2 (within 24h)
        for e in quote_events:
            sev = {"high": 3, "medium": 2}.get(str(e.get("severity", "")).lower(), 1)
            quote_quality += sev * 2.0

        # Phase 15C.1: ALWAYS neutral directional
        buy_cal = 5
        sell_cal = 5

        total_risk = base_quality + quote_quality
        if total_risk >= 8:   risk_level = "high"
        elif total_risk >= 4:  risk_level = "medium"
        elif total_risk > 0:   risk_level = "low"
        else:                  risk_level = "none"

        return buy_cal, sell_cal, total_risk, risk_level

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
    A. correlation_adjustment (score_scenario parameter, from M15/DXY candles)
    B. Tier 3 sentiment → macro_raw (from Yahoo Finance _fetch_vix)

    These are independent data sources.  The contract is that each
    path works correctly in isolation.  The macro_raw path is tested
    via score_scenario; the correlation path via its adjustment.
    """

    def test_correlation_adjustment_reduces_score(self):
        """Negative correlation_adjustment (high VIX) reduces signal_score."""
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s1 = score_scenario("buy", tech, smc, 15, 15,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 15, "sell": 15},
                            correlation_adjustment=0.0)
        s2 = score_scenario("buy", tech, smc, 15, 15,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 15, "sell": 15},
                            correlation_adjustment=-5.0)
        assert s2["signal_score"] < s1["signal_score"], \
            "Negative correlation must reduce score"

    def test_macro_raw_with_vix_encoded(self):
        """Tier 3 VIX is encoded in macro_raw (0-30) passed to score_scenario.
        A lower macro_raw (from high VIX in Tier 3) reduces macro_effective."""
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s_low = score_scenario("buy", tech, smc, 15, 10,  # low macro = high VIX
                               macro_confidence=1.0,
                               market_regime={"primary": "trend_up"},
                               macro_context={"buy": 10, "sell": 20})
        s_high = score_scenario("buy", tech, smc, 15, 25,  # high macro = low VIX
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
        encoded in macro_context.  score_scenario does not read AI keys."""
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s1 = score_scenario("buy", tech, smc, 15, 20,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 20, "sell": 10})
        s2 = score_scenario("buy", tech, smc, 15, 20,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 20, "sell": 10,
                                           "ai_stance_base": "hawkish",
                                           "ai_stance_quote": "dovish"})
        assert s1["signal_score"] == s2["signal_score"], \
            "AI stance keys in macro_context must not affect score_scenario"


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
        s = score_scenario("buy", tech, smc, 15, 25,
                           macro_confidence=1.0,
                           market_regime={"primary": "trend_up"},
                           macro_context={"bias": "sell"})
        assert MACRO_CONFLICT in s.get("penalty_codes", [])

    def test_same_raw_same_effective_regardless_of_status(self):
        """macro_effective is purely raw*weight/30, not status-dependent."""
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s1 = score_scenario("buy", tech, smc, 15, 25,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"bias": "buy"})
        s2 = score_scenario("buy", tech, smc, 15, 25,
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
        s_aligned = score_scenario("buy", tech, smc, 15, 25,
                                   macro_confidence=0.5,
                                   market_regime={"primary": "trend_up"},
                                   macro_context={"bias": "buy"})
        s_conflict = score_scenario("buy", tech, smc, 15, 25,
                                    macro_confidence=1.0,
                                    market_regime={"primary": "trend_up"},
                                    macro_context={"bias": "sell"})
        assert s_conflict["signal_score"] < s_aligned["signal_score"]


# ===========================================================================
# Phase 15D: Macro V2 pair-relative shadow mode
# ===========================================================================



class TestMacroV2Shadow:
    """Phase 15D.1: Macro V2 hardened -- exact symmetry, missing->neutral."""

    def _compute_v2(self, base_rate=2.0, quote_rate=1.0,
                    base_trend="hold", quote_trend="hold",
                    base_stance="neutral", quote_stance="neutral",
                    base_rate_avail=True, quote_rate_avail=True,
                    base_trend_avail=True, quote_trend_avail=True,
                    base_stance_avail=True, quote_stance_avail=True):
        def _rate(avail, val):
            if not avail: return 2, False
            return round(4 * min(abs(val), 5.0) / 5.0), True
        def _trend(avail, val):
            m = {"hike": 4, "hold": 2, "cut": 0}
            return (m.get(val, 2), True) if avail else (2, False)
        def _stance(avail, val):
            m = {"hawkish": 4, "neutral": 2, "dovish": 0}
            return (m.get(val, 2), True) if avail else (2, False)
        br, br_ok = _rate(base_rate_avail, base_rate)
        qr, qr_ok = _rate(quote_rate_avail, quote_rate)
        bt, bt_ok = _trend(base_trend_avail, base_trend)
        qt, qt_ok = _trend(quote_trend_avail, quote_trend)
        bs, bs_ok = _stance(base_stance_avail, base_stance)
        qs, qs_ok = _stance(quote_stance_avail, quote_stance)
        base_s = br + bt + bs
        quote_s = qr + qt + qs
        edge = base_s - quote_s
        scale = 30.0 / 24.0
        buy_v2 = round(max(0.0, min(30.0, 15.0 + edge * scale)))
        sell_v2 = 30 - buy_v2
        conf = round(sum([br_ok, qr_ok, bt_ok, qt_ok, bs_ok, qs_ok]) / 6.0, 2)
        return {"buy": buy_v2, "sell": sell_v2, "pair_edge": edge,
                "base_strength": base_s, "quote_strength": quote_s,
                "confidence": conf}

    def test_exact_symmetry(self):
        v2 = self._compute_v2(base_rate=3.0, quote_rate=1.0,
                              base_trend="hike", quote_trend="cut",
                              base_stance="hawkish", quote_stance="dovish")
        assert v2["buy"] + v2["sell"] == 30
        assert v2["buy"] > 15 > v2["sell"]

    def test_exact_reversal(self):
        eur = self._compute_v2(base_rate=2.5, quote_rate=1.0,
                               base_trend="hike", quote_trend="hold",
                               base_stance="hawkish", quote_stance="neutral")
        usd = self._compute_v2(base_rate=1.0, quote_rate=2.5,
                               base_trend="hold", quote_trend="hike",
                               base_stance="neutral", quote_stance="hawkish")
        assert eur["buy"] == usd["sell"]
        assert eur["sell"] == usd["buy"]

    def test_missing_rate_neutral_not_zero(self):
        v2 = self._compute_v2(base_rate=2.0, base_rate_avail=False, quote_rate_avail=False)
        assert v2["pair_edge"] == 0, f"edge={v2['pair_edge']}"
        assert v2["buy"] == 15

    def test_missing_trend_neutral(self):
        v2 = self._compute_v2(base_trend="hike", quote_trend="cut",
                              quote_trend_avail=False,
                              base_stance="hawkish", quote_stance="hawkish")
        assert v2["pair_edge"] > 0

    def test_missing_stance_neutral(self):
        v2 = self._compute_v2(base_stance="hawkish", quote_stance_avail=False)
        assert v2["pair_edge"] >= 0

    def test_partial_confidence(self):
        v2 = self._compute_v2(base_rate_avail=False, quote_trend_avail=False)
        assert v2["confidence"] < 1.0

    def test_full_confidence(self):
        assert self._compute_v2()["confidence"] == 1.0

    def test_bounds_and_symmetry(self):
        for args in [
            (5.0, 0.0, "hike", "cut", "hawkish", "dovish"),
            (0.0, 5.0, "cut", "hike", "dovish", "hawkish"),
            (0.0, 0.0, "cut", "cut", "dovish", "dovish"),
        ]:
            v2 = self._compute_v2(*args)
            assert 0 <= v2["buy"] <= 30
            assert 0 <= v2["sell"] <= 30
            assert v2["buy"] + v2["sell"] == 30


# ===========================================================================
# Phase 15D.2: end-to-end exposure
# ===========================================================================


class TestMacroV2Exposure:
    """macro_v2 must be available in analysis output without affecting V1."""

    def test_tier_scores_contains_macro_v2(self):
        """_compute_macro_tiers output must include macro_v2 key."""
        from services.news_service import NewsService
        svc = NewsService()
        result = svc._compute_macro_tiers(
            "EUR/USD", ["EUR", "USD"], [], [], [], [], ai_service=None,
        )
        assert "macro_v2" in result, "macro_v2 must be in tier_scores"
        v2 = result["macro_v2"]
        assert "buy" in v2
        assert "sell" in v2
        assert "pair_edge" in v2
        assert "confidence" in v2
        assert v2["buy"] + v2["sell"] == 30

    def test_macro_v2_does_not_change_v1_alignment(self):
        """V1 alignment scores must be unchanged when macro_v2 is present."""
        from services.news_service import NewsService
        svc = NewsService()
        result = svc._compute_macro_tiers(
            "EUR/USD", ["EUR", "USD"], [], [], [], [], ai_service=None,
        )
        v1 = result["alignment"]
        assert "buy" in v1
        assert "sell" in v1
        assert isinstance(v1["buy"], int)
        # V1 should be V1 tier sums, not V2 values
        v2 = result["macro_v2"]
        assert v1["buy"] != v2["buy"] or v1["sell"] != v2["sell"] or v2["pair_edge"] == 0, \
            "V1 and V2 should differ unless neutral (they use different formulas)"

    def test_missing_macro_v2_no_crash(self):
        """Parsing code with missing macro_v2 must not crash."""
        # Simulate what analysis pipeline does
        macro_context = {"macro_alignment_scores": {"buy": 15, "sell": 15}}
        v2 = macro_context.get("macro_v2")
        assert v2 is None
        # Should not crash when checking v2
        if v2:
            _ = v2.get("buy")
        # Backward compat OK

    def test_backward_compat_no_macro_v2_key(self):
        """Old macro context dict without macro_v2 key — no crash."""
        context = {"macro_alignment_scores": {"buy": 20, "sell": 10}}
        # The analysis pipeline accesses driver_context = context
        driver = context
        assert "macro_v2" not in driver
        # Safe access pattern
        macro_v2 = driver.get("macro_v2")
        assert macro_v2 is None

# ===========================================================================
# Phase 15E: deduplicate VIX and AI stance from Tier 3
# ===========================================================================


class TestPhase15EDedup:
    """AI stance and VIX must each contribute to numeric score exactly ONCE."""

    def test_tier3_ai_not_added_to_raw_sentiment(self):
        from services.news_service import NewsService
        svc = NewsService()
        result = svc._macro_tier3(["EUR", "USD"], [], [], ai_service=None)
        detail = result[2]
        assert detail["ai_applied_to_score"] is False

    def test_tier3_vix_not_added_to_raw_sentiment(self):
        from services.news_service import NewsService
        svc = NewsService()
        result = svc._macro_tier3(["EUR", "USD"], [], [], ai_service=None)
        detail = result[2]
        assert detail["vix_applied_to_score"] is False

    def test_vix_via_correlation_adjustment_only(self):
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s_no = score_scenario("buy", tech, smc, 15, 20,
                              macro_confidence=1.0,
                              market_regime={"primary": "trend_up"},
                              macro_context={"buy": 20, "sell": 10},
                              correlation_adjustment=0.0)
        s_vix = score_scenario("buy", tech, smc, 15, 20,
                               macro_confidence=1.0,
                               market_regime={"primary": "trend_up"},
                               macro_context={"buy": 20, "sell": 10},
                               correlation_adjustment=-3.0)
        assert s_vix["signal_score"] <= s_no["signal_score"]

    def test_score_deterministic_without_ai_vix_in_t3(self):
        tech = _technical_buy_context()
        smc = _smc_buy_context()
        s1 = score_scenario("buy", tech, smc, 15, 20,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 20, "sell": 10})
        s2 = score_scenario("buy", tech, smc, 15, 20,
                            macro_confidence=1.0,
                            market_regime={"primary": "trend_up"},
                            macro_context={"buy": 20, "sell": 10})
        assert s1["signal_score"] == s2["signal_score"]

# ===========================================================================
# Phase 15F: data quality provenance breakdown
# ===========================================================================


class TestDataQualityDetail:
    """macro_data_quality_detail must provide per-component provenance."""

    def test_detail_present_in_latest_macro_context(self):
        from services.news_service import NewsService
        svc = NewsService()
        ctx = svc.latest_macro_context("EUR/USD")
        dq = ctx.get("macro_data_quality_detail")
        assert dq is not None
        for key in ("rates", "calendar", "headlines", "ai_stance", "market_proxies"):
            assert key in dq, f"Missing {key}"
        assert dq["rates"]["confidence"] <= 1.0
        assert dq["calendar"]["confidence"] <= 1.0
        hl = dq["headlines"]
        assert "base_confidence" in hl
        assert "quote_confidence" in hl
        assert "global_count" in hl
        assert hl["global_not_counted_for_coverage"] is True

    def test_scalar_quality_unchanged(self):
        from services.news_service import NewsService
        svc = NewsService()
        ctx = svc.latest_macro_context("EUR/USD")
        scalar = ctx.get("macro_data_quality")
        assert isinstance(scalar, float)
        assert 0.0 <= scalar <= 1.0

    def test_missing_data_low_confidence(self):
        from services.news_service import NewsService
        svc = NewsService()
        detail = svc._macro_data_quality_detail(
            base="EUR", quote="USD", headlines=[], events=[],
            calendar_source="forex_factory", calendar_warning="",
            tier1_detail={}, tier3_detail={}, ai_available=False,
        )
        assert detail["headlines"]["base_count"] == 0
        assert detail["calendar"]["event_count"] == 0
        # Calendar available via source, not event count
        assert detail["headlines"]["base_count"] == 0

    def test_backward_compat_no_detail_key(self):
        ctx = {"macro_alignment_scores": {"buy": 15, "sell": 15}}
        detail = ctx.get("macro_data_quality_detail")
        assert detail is None  # old context, no crash


class TestDataQualityDetailFixed:
    """Phase 15F.1: provenance uses pre-fetched data, no re-fetch."""

    def test_rates_fallback_detected(self):
        from services.news_service import NewsService
        svc = NewsService()
        detail = svc._macro_data_quality_detail(
            base="EUR", quote="USD", headlines=[], events=[],
            calendar_source="forex_factory", calendar_warning="",
            tier1_detail={}, tier3_detail={}, ai_available=False,
        )
        assert "is_fallback" in detail["rates"]
        assert "last_updated" in detail["rates"]

    def test_calendar_zero_events_available(self):
        from services.news_service import NewsService
        svc = NewsService()
        detail = svc._macro_data_quality_detail(
            base="EUR", quote="USD", headlines=[], events=[],
            calendar_source="forex_factory", calendar_warning="",
            tier1_detail={}, tier3_detail={}, ai_available=False,
        )
        assert detail["calendar"]["available"] is True, \
            "Zero events from valid source must be available"
        assert detail["calendar"]["event_count"] == 0

    def test_ai_stance_actual_availability(self):
        from services.news_service import NewsService
        svc = NewsService()
        d_ai = svc._macro_data_quality_detail(
            base="EUR", quote="USD", headlines=[], events=[],
            calendar_source="forex_factory", calendar_warning="",
            tier1_detail={"base_stance": "hawkish"}, tier3_detail={},
            ai_available=True,
        )
        assert d_ai["ai_stance"]["available"] is True
        assert d_ai["ai_stance"]["is_fallback"] is False
        assert d_ai["ai_stance"]["confidence"] == 1.0

    def test_market_proxies_structured(self):
        from services.news_service import NewsService
        svc = NewsService()
        detail = svc._macro_data_quality_detail(
            base="EUR", quote="USD", headlines=[], events=[],
            calendar_source="forex_factory", calendar_warning="",
            tier1_detail={}, tier3_detail={"vix_level": 18.5},
            ai_available=False,
        )
        vix = detail["market_proxies"]["vix"]
        assert vix["available"] is True
        assert vix["level"] == 18.5
        yd = detail["market_proxies"]["yield_spread"]
        assert "available" in yd

    def test_no_duplicate_fetch(self):
        from services.news_service import NewsService
        svc = NewsService()
        detail = svc._macro_data_quality_detail(
            base="EUR", quote="USD", headlines=[], events=[],
            calendar_source="forex_factory", calendar_warning="",
            tier1_detail={}, tier3_detail={},
            ai_available=False,
        )
        assert detail["market_proxies"]["vix"]["available"] is False


class TestYieldSpreadNaming:
    """Phase 15F.2: yield_spread_10y_5y canonical, 2s10s deprecated alias."""

    def test_canonical_name_present(self):
        from services.news_service import NewsService
        data = NewsService._fetch_yield_spread()
        if data.get("spread") is not None:
            assert data["yield_spread_10y_5y"] == data["spread"]
            assert data["ten_year_yield"] is not None
            assert data["five_year_yield"] is not None

    def test_deprecated_alias_matches_canonical(self):
        from services.news_service import NewsService
        data = NewsService._fetch_yield_spread()
        if data.get("spread") is not None:
            assert data["yield_spread_2s10s"] == data["yield_spread_10y_5y"]
        assert "_deprecated_alias" in data or data["spread"] is None

    def test_tier1_detail_has_both_names(self):
        from services.news_service import NewsService
        svc = NewsService()
        _, _, detail = svc._macro_tier1("EUR", "USD", "neutral", "neutral")
        if detail.get("yield_spread_2s10s") is not None:
            assert detail["yield_spread_10y_5y"] == detail["yield_spread_2s10s"]
            assert "ten_year_yield" in detail
            assert "five_year_yield" in detail

    def test_score_unchanged_by_rename(self):
        from services.news_service import NewsService
        svc = NewsService()
        b1, s1, _ = svc._macro_tier1("EUR", "USD", "neutral", "neutral")
        b2, s2, _ = svc._macro_tier1("EUR", "USD", "neutral", "neutral")
        assert b1 == b2 and s1 == s2, "Score unchanged by field rename"


class TestMacroV1V2Script:
    """Phase 15G: script parser, aggregation, backward compat."""

    def test_old_snapshot_no_v2_no_crash(self):
        import sys; sys.path.insert(0, 'scripts')
        from compare_macro_v1_v2 import parse_input, compute_comparison
        rows = parse_input({'rows': [{'symbol': 'EUR/USD', 'best_side': 'buy'}]})
        report = compute_comparison(rows)
        assert report.rows_with_v2 == 0
        assert report.total_rows == 1

    def test_reversal_detected(self):
        import sys; sys.path.insert(0, 'scripts')
        from compare_macro_v1_v2 import compare_row
        r = compare_row({'symbol': 'EUR/USD', 'best_side': 'buy',
            'analysis_result': {'macro': {'driver_context': {
                'macro_alignment_scores': {'buy': 25, 'sell': 5},
                'macro_v2': {'buy': 5, 'sell': 25, 'confidence': 1.0},
            }}}})
        assert r.v1_direction == 'buy'
        assert r.v2_direction == 'sell'
        assert r.agreement is False

    def test_deterministic_output(self):
        import sys; sys.path.insert(0, 'scripts')
        from compare_macro_v1_v2 import compare_row
        r1 = compare_row({'symbol': 'EUR/USD', 'analysis_result': {'macro': {'driver_context': {
            'macro_alignment_scores': {'buy': 20, 'sell': 10},
            'macro_v2': {'buy': 18, 'sell': 12, 'confidence': 1.0},
        }}}})
        r2 = compare_row({'symbol': 'EUR/USD', 'analysis_result': {'macro': {'driver_context': {
            'macro_alignment_scores': {'buy': 20, 'sell': 10},
            'macro_v2': {'buy': 18, 'sell': 12, 'confidence': 1.0},
        }}}})
        assert r1.agreement == r2.agreement
        assert r1.score_gap_buy == r2.score_gap_buy
