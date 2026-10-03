"""Unit test cho `core/macro_tiers.py` — công thức 3-tier vĩ mô đã tách thuần (WI-2).

Ba nhóm:

* **Đơn vị** — fixture thuần, `now` ghim: từng tier, data quality, shape tổng hợp.
* **Pin B** — bộ số liệu ghim giá trị tuyệt đối (tier1 9/0, tier2 5/5, tier3 6/4,
  raw_total 20/9) + detail số học, chạy THUẦN trên `core.macro_tiers`. Bộ hằng số
  `_PIN_B_*` được chuyển về đây ở WI-7 cùng lúc gỡ path cũ; hai cụm đối chiếu
  path cũ (`TestPinBEquivalence`, `TestPortEquivalenceSweep`) đã hoàn thành sứ
  mệnh oracle trước cutover và được gỡ theo.
* **Độ thuần** — `core/macro_tiers` không import `services`/`ui`/`controllers`/PyQt6,
  không đọc đồng hồ (quét AST trên mã nguồn module).
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import core.macro_tiers as macro_tiers
from core.macro_tiers import (
    compute_macro_tiers,
    currency_stance,
    geopolitical_hotspots,
    macro_data_quality,
    macro_score_from_delta,
    macro_themes,
    macro_tier1,
    macro_tier2,
    macro_tier3,
    matches_currency,
    stance_value,
)
# ===========================================================================
# Fixture Pin B — bộ số liệu ghim giá trị công thức.
#
# WI-7: chuyển từ `tests/test_macro_cutover_b3_pin.py` về đây (bản gốc ghim
# trên path cũ `NewsService` đã xóa); nay chạy thẳng trên `core.macro_tiers`.
# ===========================================================================

_PIN_B_CURRENCIES = ["EUR", "USD"]

# Rate cố định: EUR hike 3.5% / USD hold 5.0%.
# rate_diff = -1.5 → diff 0/1; trend hike(4) - hold(2) = 2 → 3/1;
# stance hawkish(1) - dovish(-1) = 2 → 4/0; yield spread -0.35 < 0 và cặp có USD,
# base không phải USD → ±2. Tier 1 = 9 / 0.
_PIN_B_RATES = {
    "EUR": {"rate": 3.5, "trend": "hike", "rate_label": "3.50%"},
    "USD": {"rate": 5.0, "trend": "hold", "rate_label": "5.00%"},
}

# Headline cố định: EUR hawkish, USD dovish (keyword stance).
# Lexicon Tier 3 trên toàn bộ title: "rate cut" +2, "optimism" +2, "slowdown" -1,
# "hawkish" -2, "rally" +1 → raw_sentiment +2 → sentiment 5/8 → risk_on.
_PIN_B_HEADLINES = [
    {
        "title": "ECB signals hawkish stance as inflation above target",
        "published_utc": "2026-08-13T10:00:00+00:00",
        "currencies": ["EUR"],
    },
    {
        "title": "Fed officials signal rate cut as slowdown deepens",
        "published_utc": "2026-08-13T09:00:00+00:00",
        "currencies": ["USD"],
    },
    {
        "title": "Global markets rally as optimism returns",
        "published_utc": "2026-08-13T11:00:00+00:00",
        "currencies": [],
    },
]

# Event đặt lệch hẳn khỏi biên bucket time_weight (6/24/48h) để pin không phụ
# thuộc thời điểm chạy: +20h → weight 2.0; +50h → weight 1.0 (và < cutoff 72h).
_PIN_B_EVENT_OFFSETS_HOURS = (20, 50)

# Đường cong USD cố định (thay fetch ^TNX/^FVX): spread 2y-10y = -0.35.
_PIN_B_YIELD_PAYLOAD = {
    "spread": -0.35,
    "steepening": False,
    "ten_year_yield": 4.25,
    "five_year_yield": None,
    "tnx": 4.25,
    "fvx": 4.60,
}

# Giá trị ghim (đo trên path cũ tại HEAD 02/10/2026 — WI-1; phải khớp tuyệt đối
# sau khi port sang `core.macro_tiers`).
_PIN_B_TIER1 = {"buy": 9, "sell": 0}
_PIN_B_TIER2 = {"buy": 5, "sell": 5}  # Phase 15C: calendar luôn trung lập
_PIN_B_TIER3 = {"buy": 6, "sell": 4}
_PIN_B_RAW_TOTAL = {"buy": 20, "sell": 9}


def _pin_b_events(now: datetime) -> list[dict]:
    return [
        {
            "currency": "EUR",
            "event": "ECB Interest Rate Decision",
            "impact": "high",
            "time_utc": (
                now + timedelta(hours=_PIN_B_EVENT_OFFSETS_HOURS[0])
            ).isoformat(),
        },
        {
            "currency": "USD",
            "event": "US CPI",
            "impact": "high",
            "time_utc": (
                now + timedelta(hours=_PIN_B_EVENT_OFFSETS_HOURS[1])
            ).isoformat(),
        },
    ]

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def _headline(title: str, *, published: datetime | None = None) -> dict:
    return {
        "title": title,
        "published_utc": (published or NOW).isoformat(),
        "currencies": [],
    }


def _event(
    currency: str,
    title: str,
    *,
    hours_until: float,
    actual=None,
    forecast=None,
) -> dict:
    return {
        "currency": currency,
        "event": title,
        "impact": "high",
        "time_utc": (NOW + timedelta(hours=hours_until)).isoformat(),
        "actual": actual,
        "forecast": forecast,
    }


# ===========================================================================
# Helper thuần
# ===========================================================================


class TestHelpers:
    def test_matches_currency_by_code_and_keyword(self):
        assert matches_currency({"title": "EURUSD breaks higher"}, "EUR")
        assert matches_currency({"title": "ECB holds rates"}, "EUR")
        assert not matches_currency({"title": "Bank of Canada speaks"}, "EUR")

    def test_currency_stance_counts_keywords(self):
        assert currency_stance(["Fed signals hike"], macro_tiers.HAWKISH_TERMS, macro_tiers.DOVISH_TERMS) == "hawkish"
        assert currency_stance(["Fed signals cut"], macro_tiers.HAWKISH_TERMS, macro_tiers.DOVISH_TERMS) == "dovish"
        assert currency_stance(["Fed holds"], macro_tiers.HAWKISH_TERMS, macro_tiers.DOVISH_TERMS) == "neutral"

    def test_stance_value_and_macro_score_from_delta(self):
        assert (stance_value("hawkish"), stance_value("neutral"), stance_value("dovish")) == (1, 0, -1)
        assert macro_score_from_delta(2) == 15
        assert macro_score_from_delta(1) == 11
        assert macro_score_from_delta(0) == macro_tiers.BASELINE_MACRO_SCORE
        assert macro_score_from_delta(-1) == 4
        assert macro_score_from_delta(-2) == 0

    def test_macro_themes_per_currency(self):
        headlines = [
            _headline("ECB signals hike"),
            _headline("Fed signals cut"),
            _headline("Gold rallies"),
        ]

        themes = macro_themes(["EUR", "USD"], headlines)

        assert [theme["currency"] for theme in themes] == ["EUR", "USD"]
        assert themes[0]["stance"] == "hawkish" and themes[0]["headline_count"] == 1
        assert themes[1]["stance"] == "dovish" and themes[1]["headline_count"] == 1

    def test_geopolitical_hotspots_caps_at_six(self):
        headlines = [_headline(f"War escalates part {i}") for i in range(8)]

        hotspots = geopolitical_hotspots(headlines)

        assert len(hotspots) == 6
        assert geopolitical_hotspots([_headline("Markets steady")]) == []


# ===========================================================================
# Tier 1 — lãi suất (0-12)
# ===========================================================================


_BASE_RATES = {
    "EUR": {"rate": 2.0, "trend": "hold", "rate_label": "2.00%"},
    "USD": {"rate": 5.0, "trend": "hold", "rate_label": "5.00%"},
}


def _tier1(base="EUR", quote="USD", base_stance="neutral", quote_stance="neutral", *, rates=None, yield_payload=None):
    return macro_tier1(
        base, quote, base_stance, quote_stance,
        rates=rates if rates is not None else _BASE_RATES,
        yield_payload=yield_payload,
    )


class TestTier1:
    def test_rate_differential_favours_the_higher_rate(self):
        buy, sell, detail = _tier1()

        # |2.0 - 5.0| = 3.0 → round(4 × 3 / 5) = 2 điểm về phía USD (quote).
        assert detail["rate_differential"] == pytest.approx(-3.0)
        assert detail["components"]["rate_diff"] == {"buy": 0, "sell": 2}
        assert detail["base_rate"] == "2.00%" and detail["quote_rate"] == "5.00%"

    def test_rate_differential_saturates_at_five_points(self):
        rates = {
            "EUR": {"rate": 0.0, "trend": "hold", "rate_label": "0.00%"},
            "USD": {"rate": 9.0, "trend": "hold", "rate_label": "9.00%"},
        }

        _, _, detail = _tier1(rates=rates)

        assert detail["components"]["rate_diff"] == {"buy": 0, "sell": 4}

    def test_rate_trend_maps_hike_hold_cut(self):
        rates = {
            "EUR": {"rate": 3.0, "trend": "hike", "rate_label": "3.00%"},
            "USD": {"rate": 3.0, "trend": "cut", "rate_label": "3.00%"},
        }

        _, _, detail = _tier1(rates=rates)

        # trend_diff = 4 - 0 = 4 ≥ 3 → 4/0.
        assert detail["components"]["rate_trend"] == {"buy": 4, "sell": 0}

    def test_stance_delta_maps_to_four_zero(self):
        _, _, detail = _tier1(base_stance="hawkish", quote_stance="dovish")

        assert detail["components"]["stance"] == {"buy": 4, "sell": 0}
        assert detail["base_stance"] == "hawkish" and detail["quote_stance"] == "dovish"

    def test_inverted_yield_curve_adjusts_only_usd_pairs(self):
        inverted = {"spread": -0.4, "steepening": False, "tnx": 4.1, "fvx": 4.5,
                    "ten_year_yield": 4.1, "five_year_yield": 4.5}

        _, _, usd_pair = _tier1(yield_payload=inverted)
        _, _, cross = _tier1(base="AUD", quote="NZD", yield_payload=inverted)

        assert usd_pair["yield_spread_adj"] == {"buy": 2, "sell": -2}
        assert cross["yield_spread_adj"] == {"buy": 0, "sell": 0}

    def test_inverted_curve_flips_sign_when_usd_is_base(self):
        inverted = {"spread": -0.4, "steepening": False}

        _, _, detail = _tier1(base="USD", quote="JPY", yield_payload=inverted)

        assert detail["yield_spread_adj"] == {"buy": -2, "sell": 2}

    def test_steepening_adds_one_point(self):
        steep = {"spread": 0.8, "steepening": True}

        _, _, detail = _tier1(yield_payload=steep)

        assert detail["yield_spread_adj"] == {"buy": -1, "sell": 1}

    def test_flat_curve_inside_threshold_is_neutral(self):
        flat = {"spread": 0.25, "steepening": True}

        _, _, detail = _tier1(yield_payload=flat)

        assert detail["yield_spread_adj"] == {"buy": 0, "sell": 0}

    def test_sides_are_clamped_to_zero_twelve(self):
        rates = {
            "EUR": {"rate": 9.0, "trend": "hike", "rate_label": "9.00%"},
            "USD": {"rate": 0.0, "trend": "cut", "rate_label": "0.00%"},
        }

        buy, sell, _ = _tier1(rates=rates, base_stance="hawkish", quote_stance="dovish")

        assert buy == 12  # 4 + 4 + 4 = 12, không vượt trần
        assert sell == 0


# ===========================================================================
# Tier 2 — lịch kinh tế (luôn 5/5)
# ===========================================================================


class TestTier2:
    def test_directional_score_is_always_neutral(self):
        empty = macro_tier2("EUR", "USD", [], now=NOW)
        heavy = macro_tier2(
            "EUR", "USD", [_event("EUR", "ECB Interest Rate Decision", hours_until=2.0)], now=NOW
        )

        assert empty[:2] == (5, 5)
        assert heavy[:2] == (5, 5)

    def test_time_weight_buckets(self):
        events = [
            _event("EUR", "ECB speaks", hours_until=3.0),
            _event("EUR", "ECB speaks", hours_until=12.0),
            _event("EUR", "ECB speaks", hours_until=30.0),
            _event("EUR", "ECB speaks", hours_until=60.0),
        ]

        _, _, detail = macro_tier2("EUR", "USD", events, now=NOW)

        assert [item["time_weight"] for item in detail["base_events"]] == [3.0, 2.0, 1.5, 1.0]

    def test_severity_comes_from_title_keywords(self):
        events = [
            _event("EUR", "US CPI", hours_until=10.0),
            _event("EUR", "Retail Sales", hours_until=10.0),
            _event("EUR", "Some Minor Release", hours_until=10.0),
        ]

        _, _, detail = macro_tier2("EUR", "USD", events, now=NOW)

        assert [item["severity"] for item in detail["base_events"]] == [3, 2, 1]

    def test_quality_rounds_up(self):
        # severity 3 × weight 1.5 = 4.5 → 5 (làm tròn lên).
        events = [_event("EUR", "US CPI", hours_until=30.0)]

        _, _, detail = macro_tier2("EUR", "USD", events, now=NOW)

        assert detail["base_quality"] == 5
        assert detail["base_events"][0]["quality"] == 5

    def test_events_outside_72h_window_are_skipped(self):
        events = [_event("EUR", "US CPI", hours_until=80.0)]

        _, _, detail = macro_tier2("EUR", "USD", events, now=NOW)

        assert detail["base_event_count"] == 0
        assert detail["base_quality"] == 0
        # `next_72h_events` vẫn đếm đầu vào thô (giữ nguyên hành vi bản cũ).
        assert detail["next_72h_events"] == 1

    def test_event_risk_level_thresholds(self):
        def risk(events):
            return macro_tier2("EUR", "USD", events, now=NOW)[2]["event_risk_level"]

        assert risk([_event("EUR", "US CPI", hours_until=2.0)]) == "high"  # 3 × 3 = 9
        assert risk([_event("EUR", "US CPI", hours_until=10.0)]) == "medium"  # 3 × 2 = 6
        assert risk([_event("EUR", "Minor Release", hours_until=10.0)]) == "low"  # 1 × 2 = 2
        assert risk([]) == "none"

    def test_surprise_data_is_diagnostic_only(self):
        events = [_event("EUR", "US CPI", hours_until=10.0, actual="3.1%", forecast="3.0%")]

        buy, sell, detail = macro_tier2("EUR", "USD", events, now=NOW)

        assert (buy, sell) == (5, 5)  # surprise KHÔNG đổi hướng điểm
        assert detail["has_surprise_data"] is True
        assert detail["base_events"][0]["has_surprise"] is True

    def test_currency_is_split_between_base_and_quote(self):
        events = [
            _event("EUR", "US CPI", hours_until=10.0),
            _event("USD", "US CPI", hours_until=10.0),
            _event("JPY", "US CPI", hours_until=10.0),  # không thuộc cặp → bỏ qua
        ]

        _, _, detail = macro_tier2("EUR", "USD", events, now=NOW)

        assert detail["base_event_count"] == 1
        assert detail["quote_event_count"] == 1


# ===========================================================================
# Tier 3 — tâm lý & địa chính trị (0-12)
# ===========================================================================


class TestTier3:
    def test_risk_on_sentiment_split(self):
        headlines = [_headline("Global markets rally as optimism returns")]

        buy, sell, detail = macro_tier3(["EUR", "USD"], headlines, [], vix_level=None)

        assert detail["raw_sentiment"] == 3
        assert detail["risk_sentiment"] == "risk_on"
        assert detail["components"]["risk_sentiment"] == {"buy": 4, "sell": 2}
        assert (buy, sell) == (6, 4)  # + geo 2/2

    def test_negation_flips_the_term(self):
        headlines = [_headline("Fed says no rate cut on the table")]

        _, _, detail = macro_tier3(["EUR", "USD"], headlines, [], vix_level=None)

        assert detail["raw_sentiment"] == -2
        assert detail["matched_terms"][0]["negated"] is True
        assert detail["matched_terms"][0]["effective"] == -2
        assert detail["risk_sentiment"] == "risk_off"

    def test_sentiment_is_clamped_to_zero_eight(self):
        headlines = [_headline("crash contagion default financial crisis recession")]

        _, _, detail = macro_tier3(["EUR", "USD"], headlines, [], vix_level=None)

        assert detail["sentiment_score_0_8"] == 0
        assert detail["raw_sentiment"] <= -12

    def test_hotspots_move_geopolitical_score(self):
        hotspots = [{"title": "War escalates in the region"}]

        _, _, detail = macro_tier3(["EUR", "USD"], [], hotspots, vix_level=None)

        # severity 2 → quote USD là safe haven → 1/3.
        assert detail["hotspot_severity"] == 2
        assert detail["components"]["geopolitical"] == {"buy": 1, "sell": 3}

    def test_vix_is_diagnostic_only(self):
        headlines = [_headline("Global markets rally as optimism returns")]

        without = macro_tier3(["EUR", "USD"], headlines, [], vix_level=None)
        stressed = macro_tier3(["EUR", "USD"], headlines, [], vix_level=27.0)

        assert stressed[0] == without[0] and stressed[1] == without[1]
        assert stressed[2]["vix_level"] == 27.0
        assert stressed[2]["vix_adjustment"] == -2
        assert stressed[2]["vix_applied_to_score"] is False

    def test_ai_fields_are_frozen_at_ai_off(self):
        _, _, detail = macro_tier3(["EUR", "USD"], [], [], vix_level=None)

        assert detail["ai_sentiment_used"] is False
        assert detail["ai_sentiment_score"] is None
        assert detail["ai_applied_to_score"] is False


# ===========================================================================
# Macro data quality (0.0-1.0)
# ===========================================================================


class TestMacroDataQuality:
    def test_fresh_coverage_scores_one(self):
        headlines = [_headline(f"Headline {i}", published=NOW - timedelta(hours=1)) for i in range(3)]
        events = [_event("EUR", "US CPI", hours_until=10.0)]

        assert macro_data_quality(headlines, events, now=NOW) == pytest.approx(1.0)

    def test_stale_headlines_lose_fifteen_points(self):
        headlines = [_headline(f"Headline {i}", published=NOW - timedelta(hours=20)) for i in range(3)]
        events = [_event("EUR", "US CPI", hours_until=10.0)]

        assert macro_data_quality(headlines, events, now=NOW) == pytest.approx(0.85)

    def test_thin_coverage_and_missing_events_penalise(self):
        headlines = [_headline("Only one", published=NOW - timedelta(hours=5))]

        # 1.0 − 0.05 (tuổi 5h) − 0.10 (<3 headline) − 0.10 (không event) = 0.75.
        assert macro_data_quality(headlines, [], now=NOW) == pytest.approx(0.75)

    def test_no_data_at_all_scores_point_four(self):
        assert macro_data_quality([], [], now=NOW) == pytest.approx(0.40)


# ===========================================================================
# Tổng hợp `compute_macro_tiers`
# ===========================================================================


def _compute_pin_b(now: datetime, *, vix_level: float = 18.0) -> dict:
    return compute_macro_tiers(
        _PIN_B_CURRENCIES,
        _PIN_B_HEADLINES,
        _pin_b_events(now),
        [],
        rates=_PIN_B_RATES,
        yield_payload=_PIN_B_YIELD_PAYLOAD,
        now=now,
        vix_level=vix_level,
    )


class TestComputeMacroTiers:
    def test_shape_matches_the_old_contract(self):
        result = _compute_pin_b(NOW)

        assert set(result) == {
            "tier1", "tier2", "tier3", "raw_total", "alignment", "reasons", "stance_detail",
        }
        assert result["raw_total"] == {
            "buy": result["tier1"]["buy"] + result["tier2"]["buy"] + result["tier3"]["buy"],
            "sell": result["tier1"]["sell"] + result["tier2"]["sell"] + result["tier3"]["sell"],
        }
        assert result["alignment"] == result["raw_total"]

    def test_stance_detail_is_keyword_sourced(self):
        result = _compute_pin_b(NOW)

        assert result["stance_detail"]["base"]["currency"] == "EUR"
        assert result["stance_detail"]["base"]["stance"] == "hawkish"
        assert result["stance_detail"]["base"]["source"] == "keyword"
        assert result["stance_detail"]["base"]["strength"] is None
        assert result["stance_detail"]["quote"]["currency"] == "USD"
        assert result["stance_detail"]["quote"]["stance"] == "dovish"
        assert result["stance_detail"]["quote"]["source"] == "keyword"

    def test_reasons_render_the_three_tiers(self):
        result = _compute_pin_b(NOW)

        assert result["reasons"]["buy"] == (
            "[T1] EUR=3.50%(Thắt chặt) so với USD=5.00%(Nới lỏng) | "
            "[T2] Sự kiện lịch KT: base=0, quote=0 | "
            "[T3] Tâm lý TT=Chấp nhận rủi ro, điểm nóng=0"
        )
        assert "[T1]" in result["reasons"]["sell"]

    def test_empty_context_fails_closed_without_crashing(self):
        """Đường lỗi đọc DB của provider: context rỗng → không crash, shape nguyên."""
        result = compute_macro_tiers(
            [], [], [], [],
            rates={},
            yield_payload=None,
            now=NOW,
            vix_level=None,
        )

        assert (result["tier2"]["buy"], result["tier2"]["sell"]) == (5, 5)
        assert result["raw_total"] == {
            "buy": result["tier1"]["buy"] + 5 + result["tier3"]["buy"],
            "sell": result["tier1"]["sell"] + 5 + result["tier3"]["sell"],
        }
        assert result["tier3"]["detail"]["vix_applied_to_score"] is False


# ===========================================================================
# Pin B — giá trị công thức đã ghim (WI-1), nay chạy THUẦN trên `core.macro_tiers`
# ===========================================================================


class TestPinBPinnedValues:
    """Bộ số liệu ghim của Pin B phải giữ nguyên giá trị tuyệt đối.

    Đây là bản kế thừa của cụm `TestPinBFormula` trong `tests/test_macro_cutover_b3_pin.py`
    (đo trên path cũ `NewsService` trước cutover, đã gỡ cùng `news_service.py` ở
    WI-7). Cùng input, cùng hằng số — nay tính bằng module thuần.
    """

    def test_tier_values_match_the_pinned_constants(self):
        result = _compute_pin_b(NOW)

        for tier_name, expected in (
            ("tier1", _PIN_B_TIER1),
            ("tier2", _PIN_B_TIER2),
            ("tier3", _PIN_B_TIER3),
        ):
            assert result[tier_name]["buy"] == expected["buy"], tier_name
            assert result[tier_name]["sell"] == expected["sell"], tier_name

        assert dict(result["raw_total"]) == _PIN_B_RAW_TOTAL == {"buy": 20, "sell": 9}

    def test_pinned_numbers_are_literal(self):
        """Ghim thẳng số, không chỉ so với hằng số (bắt lỗi sửa hằng số theo code)."""
        result = _compute_pin_b(NOW)

        assert (result["tier1"]["buy"], result["tier1"]["sell"]) == (9, 0)
        assert (result["tier2"]["buy"], result["tier2"]["sell"]) == (5, 5)
        assert (result["tier3"]["buy"], result["tier3"]["sell"]) == (6, 4)
        assert result["raw_total"] == {"buy": 20, "sell": 9}

    def test_detail_numbers_match_the_pinned_paths(self):
        """Chi tiết đủ để chứng minh fixture chạm đúng các nhánh công thức."""
        result = _compute_pin_b(NOW)

        tier1 = result["tier1"]["detail"]
        assert tier1["rate_differential"] == pytest.approx(-1.5)
        assert tier1["base_stance"] == "hawkish"
        assert tier1["quote_stance"] == "dovish"
        assert tier1["yield_spread_adj"] == {"buy": 2, "sell": -2}
        assert tier1["components"]["rate_diff"] == {"buy": 0, "sell": 1}
        assert tier1["components"]["rate_trend"] == {"buy": 3, "sell": 1}
        assert tier1["components"]["stance"] == {"buy": 4, "sell": 0}

        tier2 = result["tier2"]["detail"]
        assert tier2["base_event_count"] == 1
        assert tier2["quote_event_count"] == 1
        assert tier2["event_risk_score"] == 9
        assert tier2["event_risk_level"] == "high"
        assert [event["time_weight"] for event in tier2["base_events"]] == [2.0]
        assert [event["time_weight"] for event in tier2["quote_events"]] == [1.0]

        tier3 = result["tier3"]["detail"]
        assert tier3["raw_sentiment"] == 2
        assert tier3["sentiment_score_0_8"] == 5
        assert tier3["risk_sentiment"] == "risk_on"
        assert tier3["components"]["risk_sentiment"] == {"buy": 4, "sell": 2}
        assert tier3["components"]["geopolitical"] == {"buy": 2, "sell": 2}

    def test_ai_off_is_the_pinned_behaviour(self):
        """Đường AI-off: stance keyword, không verdict AI nào vào điểm."""
        result = _compute_pin_b(NOW)

        assert result["tier3"]["detail"]["ai_sentiment_used"] is False
        assert result["tier3"]["detail"]["ai_applied_to_score"] is False
        assert result["tier3"]["detail"]["ai_sentiment_score"] is None
        assert result["stance_detail"]["base"]["source"] == "keyword"
        assert result["stance_detail"]["base"]["stance"] == "hawkish"
        assert result["stance_detail"]["quote"]["stance"] == "dovish"
        assert result["stance_detail"]["base"]["strength"] is None


# ===========================================================================
# Độ thuần
# ===========================================================================

_MODULE_SOURCE = Path(macro_tiers.__file__).read_text(encoding="utf-8")
_FORBIDDEN_ROOTS = {
    "services", "ui", "controllers", "workers",
    "PyQt6", "PyQt5", "yfinance", "requests", "urllib", "httplib", "sqlite3",
}


def _imported_roots(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


class TestPurity:
    def test_module_does_not_import_outer_layers(self):
        assert _imported_roots(_MODULE_SOURCE) & _FORBIDDEN_ROOTS == set()

    def test_module_has_no_clock(self):
        assert "datetime.now(" not in _MODULE_SOURCE
        assert "time.time(" not in _MODULE_SOURCE

    def test_no_io_on_the_macro_path(self, monkeypatch):
        """Gọi công thức với socket bị chặn — không được có I/O mạng."""
        import socket

        def _no_socket(*args, **kwargs):
            raise AssertionError("I/O mạng trên đường vĩ mô")

        monkeypatch.setattr(socket, "socket", _no_socket)
        monkeypatch.setattr(socket, "create_connection", _no_socket)

        assert _compute_pin_b(NOW)["raw_total"] == _PIN_B_RAW_TOTAL
