from __future__ import annotations

from pathlib import Path

from core.chart_payload import build_full_chart_payload


CHART_HTML = (
    Path(__file__).resolve().parents[1] / "assets" / "chart" / "index.html"
)


def _chart_source() -> str:
    return CHART_HTML.read_text(encoding="utf-8")


def test_chart_payload_keeps_source_zone_for_optional_display() -> None:
    result = {
        "decision_summary": {"best_side": "buy"},
        "scenarios": [{
            "type": "buy",
            "entry_zone": [1.0980, 1.0990],
            "entry_zone_source": "smc",
            "source_zone": {
                "original_low": 1.0950,
                "original_high": 1.1000,
            },
        }],
        "chart_payload": {},
    }

    payload = build_full_chart_payload("EURUSD", result)

    source = next(zone for zone in payload["zones"] if zone["type"] == "source_zone")
    assert source["execution_eligible"] is False
    assert [source["from"], source["to"]] == [1.095, 1.1]


def test_chart_defaults_to_daily_and_falls_back_when_daily_is_missing() -> None:
    daily = build_full_chart_payload(
        "EURUSD",
        {"chart_payload": {"D1": [{"time": "2026-01-01", "close": 1.1}]}},
    )
    fallback = build_full_chart_payload(
        "EURUSD",
        {"chart_payload": {"H1": [{"time": "2026-01-01", "close": 1.1}]}},
    )

    assert daily["active_timeframe"] == "D1"
    assert fallback["active_timeframe"] == "H1"


def test_source_zone_is_hidden_by_default_and_has_explicit_toggle() -> None:
    html = _chart_source()

    assert "var _showSourceZone = false;" in html
    assert 'id="source-zone-checkbox"' in html
    assert "Vùng cấu trúc tham khảo, không dùng để vào lệnh" in html
    assert "sourceToggle.style.display = hasSource ? 'inline-flex' : 'none';" in html
    assert "if (isSource && !_showSourceZone) continue;" in html


def test_hidden_source_zone_does_not_affect_chart_price_scale() -> None:
    html = _chart_source()

    assert (
        "if (zones[j].type === 'source_zone' && !_showSourceZone) continue;"
        in html
    )


def test_optional_source_display_uses_single_reference_label() -> None:
    html = _chart_source()

    assert "var upperTitle = isSource ? 'Source zone' : 'Entry+';" in html
    assert "var lowerTitle = isSource ? '' : 'Entry-';" in html
    assert "Source+" not in html
    assert "Source-" not in html


def test_chart_uses_medium_default_candle_density() -> None:
    html = _chart_source()

    assert "var _activeTF = 'D1';" in html
    assert "var visibleBars = 100;" in html
    assert "barSpacing: 7," in html
    assert "minBarSpacing: 3," in html
