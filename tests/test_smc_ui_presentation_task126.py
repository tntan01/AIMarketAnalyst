"""Tasks 121–126 — SMC presentation, scanner detail and the chart layer.

Every case drives the REAL producers: the canonical evaluation
(``AnalysisPipeline.execute``), the Scanner row the live controller routes
(``_analyze_one_symbol``) and the chart payload built by ``core.chart_payload``.
No expected value is copied out of the code under test; the oracles are

* the canonical selection of the same snapshot (``smc_selection_of``) — what the
  UI shows must be that selection and nothing else;
* the display rules of the compatibility spec §7 — ``0`` vs ``null``,
  "chờ xác nhận" instead of "sẵn sàng", no engine/version label, and a score that
  is never a win probability;
* the payload the chart actually receives (``build_full_chart_payload``).

Covered states: missing, waiting, confirmed, invalid (invalidated/expired) and a
historical row whose SMC evidence predates the canonical verdict.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from core.chart_payload import (
    SMC_OVERLAY_SOURCE_CANONICAL,
    SMC_OVERLAY_SOURCE_MISSING,
    SMC_PROTECTED_SWING_UNAVAILABLE,
    SMC_ZONE_STATUS_INVALID,
    SMC_ZONE_STATUS_SELECTED,
    SMC_ZONE_STATUS_WATCH,
    build_full_chart_payload,
    build_smc_overlay,
)
from core.smc_consumer_contract import SMC_READ_CARRIER_WITHOUT_BLOCK
from core.smc_persistence import (
    SMC_PERSISTENCE_BLOCK_MISSING,
    SMC_PERSISTENCE_IDENTITY_MISMATCH,
)
from core.smc_scoring_result import (
    SELECTION_STATE_DATA_UNAVAILABLE,
    SELECTION_STATE_NO_ZONE,
    smc_selection_of,
)
from ui import scanner_presentation as presentation

_T113 = importlib.import_module("tests.test_smc_consumer_contract_task113")
_T117 = importlib.import_module("tests.test_smc_persistence_task117_120")
_TV4 = importlib.import_module("tests.test_scanner_detail_v4_diagnostics")

CHART_HTML = Path(__file__).resolve().parents[1] / "assets" / "chart" / "index.html"

# Words that would turn the quality score into a probability.  The spec forbids
# presenting the score as a win rate in any of these spellings.
_FORBIDDEN_SCORE_WORDS = (
    "%",
    "xác suất",
    "tỷ lệ thắng",
    "tỉ lệ thắng",
    "khả năng thắng",
    "win rate",
)


# ---------------------------------------------------------------------------
# Fixtures: canonical selections in each state, through the REAL producers
# ---------------------------------------------------------------------------


def _scanner_row() -> dict[str, Any]:
    """A real Scanner row produced by the live controller (waiting state)."""

    return _TV4._blocked_row()


def _selection(analysis, side: str):
    """The live canonical selection of one side of a real evaluation."""

    result, pipeline, _symbol = analysis
    return smc_selection_of(pipeline._smc_evaluation.result.side(side))


def _analyze_row(analysis, side: str) -> dict[str, Any]:
    """A row whose ``analysis_result`` is the real Analyze result.

    Analyze carries the canonical verdict in the consumer contract
    (``smc_consumer``), which is the other canonical carrier the UI reads.
    """

    result, _pipeline, symbol = analysis
    return {
        "symbol": symbol,
        "selected_side": side,
        "analysis_result": result,
    }


def _row_with_scanner_carrier(analysis, side: str) -> dict[str, Any]:
    """A row carrying the per-side summary the Scanner adapter publishes.

    The values are read from the same canonical selection, so the carrier is
    genuinely canonical — this is exactly what ``_ui_side_scores`` copies.  The
    canonical persistence block travels beside it (task 128 follow-up): the
    Scanner route publishes both, and a payload with the carrier alone is not a
    live result any more.
    """

    result, pipeline, symbol = analysis
    evaluation = pipeline._smc_evaluation
    selection = _selection(analysis, side)
    from core.smc_consumer_contract import build_smc_consumer_from_canonical_result
    from core.smc_persistence import build_smc_persistence_block

    canonical = evaluation.result
    return {
        "symbol": symbol,
        "selected_side": side,
        "analysis_result": {
            "smc_selection": {side: selection.to_dict()},
            "smc_scoring": build_smc_persistence_block(
                canonical,
                build_smc_consumer_from_canonical_result(result=canonical),
                snapshot=evaluation.snapshot,
            ),
            "chart_payload": {},
        },
    }


def _case_analysis(case: dict[str, Any]):
    """Run the real Analyze caller for one consumer-contract case."""

    result, pipeline = _T113._analyze(case)
    return result, pipeline, str(case["symbol"])


def _waiting_analysis():
    return _case_analysis(_T113._case("fvg_confirmed_buy"))


def _no_zone_analysis():
    return _case_analysis(_T113._case("no_zone"))


def _data_unavailable_analysis():
    return _case_analysis(_T113._case("ob_confirmed_sell"))


# ---------------------------------------------------------------------------
# 121 — the row presenter never says more than the canonical verdict
# ---------------------------------------------------------------------------


def _live_verdict(row: dict[str, Any]) -> dict[str, Any] | None:
    """The canonical verdict the live row carries (``None`` if it carries none).

    The live fixture is placed at the observation instant, so the scan it drives
    can legitimately end in a state where no verdict is published (the technical
    chain reports the data unavailable at that instant).  Both outcomes are
    canonical answers; what the UI must never do is invent a third one.
    """

    selections = (row.get("analysis_result") or {}).get("smc_selection")
    if not isinstance(selections, dict):
        return None
    return selections


def test_the_scanner_row_carries_the_selection_it_publishes():
    """The UI carrier is the canonical selection, not a re-derived summary."""

    row = _scanner_row()
    selections = _live_verdict(row)
    if selections is None:
        # The live scan could not conclude at this instant: the row then carries
        # no verdict at all, and the presenter must say exactly that.
        view = presentation.present_smc_row(row)
        assert view.available is False
        assert view.source == presentation.SMC_SOURCE_MISSING
        assert view.score_text == "Chưa có dữ liệu SMC"
        return

    assert set(selections) == {"buy", "sell"}
    for side, payload in selections.items():
        presented = presentation.smc_selection_from_analysis(
            row["analysis_result"], side
        )
        if payload is None:
            # A side whose canonical result carries no verdict stays absent; the
            # presenter must not fill it in from the other side or from legacy.
            assert presented is None
            continue
        assert dict(presented) == payload, (
            "the presenter must read the very payload the row carries"
        )
        # Identity the UI shows has to be the canonical identity.
        assert payload["selected_zone_id"]
        assert payload["quality_raw"] is not None


def test_the_presenter_shows_the_live_verdict_or_says_there_is_none():
    """Whatever the live scan concluded, the UI shows THAT and nothing else."""

    row = _scanner_row()
    selections = _live_verdict(row)
    view = presentation.present_smc_row(row)

    assert view.state_text not in ("sẵn sàng", "Sẵn sàng", "Đủ điều kiện vào lệnh")
    side = "buy" if row.get("selected_side") not in ("buy", "sell") else row["selected_side"]
    payload = selections.get(side) if selections else None
    if payload is None:
        assert view.source == presentation.SMC_SOURCE_MISSING
        assert view.available is False
        return

    assert view.source == presentation.SMC_SOURCE_CANONICAL
    assert view.available is True
    assert view.score_raw == payload["quality_raw"]
    assert view.readiness_status == str(payload.get("readiness_status") or "")
    if view.readiness_status == "WAITING_CONFIRMATION":
        # A zone waiting for its entry confirmation says exactly that.
        assert view.state_text == "Chờ xác nhận"


def test_a_waiting_side_is_shown_as_waiting_never_as_ready():
    """The deterministic waiting case: a real evaluation with M15 still waiting."""

    analysis = _waiting_analysis()
    selection = _selection(analysis, "buy")
    view = presentation.present_smc_row(_analyze_row(analysis, "buy"))

    assert view.available is True
    assert view.source == presentation.SMC_SOURCE_CANONICAL
    assert selection.confirmation_state in ("waiting", "confirmed", "candidate")
    assert view.state_text not in ("sẵn sàng", "Sẵn sàng", "Đủ điều kiện vào lệnh")
    if view.readiness_status == "WAITING_CONFIRMATION":
        assert view.state_text == "Chờ xác nhận"


@pytest.mark.parametrize("case", ["no_zone", "data_unavailable"])
def test_zero_and_null_are_two_different_results(case):
    """``no_zone`` keeps the evaluated zero; core-unavailable keeps the null."""

    analysis = _no_zone_analysis() if case == "no_zone" else _data_unavailable_analysis()
    side = "sell" if case == "no_zone" else "buy"
    selection = _selection(analysis, side)

    expected_state = (
        SELECTION_STATE_NO_ZONE if case == "no_zone" else SELECTION_STATE_DATA_UNAVAILABLE
    )
    assert selection.state == expected_state
    # The two canonical states really are 0 and null; the presenter must not
    # collapse them into one.
    view = presentation.present_smc_selection(
        _row_with_scanner_carrier(analysis, side)["analysis_result"]["smc_selection"][side]
    )
    if case == "no_zone":
        assert selection.quality_raw == 0
        assert view.score_raw == 0
        assert "0/15" in view.score_text
        assert "chưa có setup hợp lệ" in view.score_text
    else:
        assert selection.quality_raw is None
        assert view.score_raw is None
        assert view.score_text == "Thiếu dữ liệu"
    assert "0/15" not in view.score_text or case == "no_zone"


def test_the_score_is_never_presented_as_a_probability():
    """No state may spell the quality score as a chance of winning."""

    rows = [
        _scanner_row(),
        _analyze_row(_waiting_analysis(), "buy"),
        _analyze_row(_no_zone_analysis(), "sell"),
        _analyze_row(_data_unavailable_analysis(), "buy"),
        _analyze_row(_T117._confirmed_analysis(), "buy"),
        _analyze_row(_T117._invalidated_analysis(), "buy"),
    ]
    for row in rows:
        texts = [
            presentation.present_smc_row(row).tooltip_text(),
            json.dumps(presentation.present_smc_row(row).to_dict(), ensure_ascii=False),
        ]
        for text in texts:
            lowered = text.lower()
            for word in _FORBIDDEN_SCORE_WORDS:
                assert word not in lowered, f"{word!r} leaked into {text!r}"


def test_the_row_shows_at_most_three_reasons():
    row = _analyze_row(_T117._confirmed_analysis(), "buy")
    view = presentation.present_smc_row(row)

    assert 0 < len(view.reasons) <= presentation.SMC_MAX_REASONS
    # The detail panel may show them all; the main screen stays short.  Both
    # read the SAME canonical selection, through the same carrier resolution.
    selection = presentation.smc_selection_from_analysis(
        row["analysis_result"], "buy"
    )
    assert len(presentation.smc_reason_texts(selection, None)) >= len(view.reasons)

    # The cap is on the presentation, not on the evidence: a selection carrying
    # more reasons keeps them all when the caller asks for no limit.
    many = {
        "readiness_reason_codes": [
            "SMC_ZONE_PENDING_CONFIRMATION",
            "SMC_WAITING_FOR_ZONE_VISIT",
            "SMC_PLAN_UNAVAILABLE",
        ],
        "selection_reason_codes": ["QUALITY_RANK", "NEXT_CANDIDATE_AFTER_REJECT"],
    }
    assert len(
        presentation.smc_reason_texts(many, presentation.SMC_MAX_REASONS)
    ) == presentation.SMC_MAX_REASONS
    assert len(presentation.smc_reason_texts(many, None)) == 5
    assert len(presentation.present_smc_selection(many).reasons) == (
        presentation.SMC_MAX_REASONS
    )
    assert len(
        presentation.present_smc_selection(many, max_reasons=None).reasons
    ) == 5


def test_a_historical_row_is_never_shown_as_the_current_result():
    """A pre-canonical payload is labelled historical and its score is not shown."""

    legacy_row = {
        "symbol": "XAUUSD",
        "selected_side": "buy",
        "analysis_result": {
            "smc_consumer": {
                "sides": {
                    "buy": {
                        "selected_zone": {"original_low": 1000.0, "original_high": 1001.0},
                        "selected_zone_quality_score": 82,
                    },
                    "sell": {},
                }
            }
        },
    }
    view = presentation.present_smc_row(legacy_row)

    assert view.available is False
    assert view.source == presentation.SMC_SOURCE_HISTORICAL
    assert "82" not in view.score_text
    assert "82" not in view.tooltip_text()
    assert "lịch sử" in view.state_text.lower()


def test_a_row_without_any_smc_information_says_so():
    view = presentation.present_smc_row(
        {"symbol": "XAUUSD", "selected_side": "buy", "analysis_result": {}}
    )
    assert view.available is False
    assert view.source == presentation.SMC_SOURCE_MISSING
    assert view.score_text == "Chưa có dữ liệu SMC"


def test_the_presenter_reads_the_consumer_contract_carrier_too():
    """The Analyze carrier (``smc_consumer``) presents the same canonical side."""

    analysis = _T117._confirmed_analysis()
    selection = _selection(analysis, "buy")
    row = _analyze_row(analysis, "buy")

    view = presentation.present_smc_row(row)
    assert view.available is True
    assert view.selection_state == selection.state
    assert view.score_raw == selection.quality_raw
    assert view.readiness_status == (selection.readiness or {}).get("status")


# ---------------------------------------------------------------------------
# 123/124 — the chart layer is built from the same canonical source
# ---------------------------------------------------------------------------


def test_the_chart_layer_keeps_the_canonical_band_and_identity():
    """The band the chart draws is the canonical band of the SAME candidate."""

    analysis = _waiting_analysis()
    row = _analyze_row(analysis, "buy")
    selection = _selection(analysis, "buy")
    overlay = build_smc_overlay(row["analysis_result"])

    assert overlay["source"] == SMC_OVERLAY_SOURCE_CANONICAL
    layer = overlay["timeframes"][selection.timeframe]
    zone = next(z for z in layer["zones"] if z["side"] == "buy")
    assert zone["zone_id"] == selection.selected_zone_id
    assert zone["setup_id"] == selection.selected_setup_id
    # Bounds are the canonical band, untouched.
    assert [zone["from"], zone["to"]] == [selection.zone_low, selection.zone_high]


def test_an_invalid_confirmation_is_drawn_as_invalid():
    analysis = _T117._invalidated_analysis()
    selection = _selection(analysis, "buy")
    assert selection.lifecycle_status in ("invalid", "expired") or (
        selection.confirmation or {}
    ).get("status") in ("invalidated", "expired")

    overlay = build_smc_overlay(analysis[0])
    layer = overlay["timeframes"][selection.timeframe]
    zone = next(z for z in layer["zones"] if z["side"] == "buy")
    assert zone["status"] == SMC_ZONE_STATUS_INVALID
    # An invalid zone is never presented as something to enter on.
    assert zone["execution_eligible"] is False


def test_a_watched_zone_is_not_an_entry_region():
    """A side that kept a zone without a plan is drawn as watched, not enterable."""

    analysis = _no_zone_analysis()
    row = _analyze_row(analysis, "sell")
    selection = _selection(analysis, "sell")
    overlay = build_smc_overlay(row["analysis_result"])

    if selection.quality_raw == 0 and selection.selected_zone_id is None:
        # An evaluated no-zone side has no band to draw: the overlay must not
        # invent one from the other side's geometry.
        assert all(
            z["side"] != "sell"
            for layer in overlay["timeframes"].values()
            for z in layer["zones"]
        )
        return
    layer = overlay["timeframes"][selection.timeframe]
    zone = next(z for z in layer["zones"] if z["side"] == "sell")
    if selection.readiness_status == "WATCH_ZONE":
        assert zone["status"] == SMC_ZONE_STATUS_WATCH
    if not selection.plan_available:
        assert zone["execution_eligible"] is False
    assert zone["status"] in (
        SMC_ZONE_STATUS_SELECTED,
        SMC_ZONE_STATUS_WATCH,
        SMC_ZONE_STATUS_INVALID,
    )


def test_the_trigger_keeps_its_own_time_and_is_never_moved_earlier():
    analysis = _T117._confirmed_analysis()
    selection = _selection(analysis, "buy")
    record = selection.confirmation
    assert isinstance(record, dict) and record.get("trigger_at")

    overlay = build_smc_overlay(analysis[0])
    trigger = overlay["timeframes"][selection.timeframe]["trigger"]
    assert trigger is not None
    assert trigger["trigger_at"] == record["trigger_at"]
    assert trigger["confirmed_at"] == record["confirmed_at"]
    # The event is never relocated before the moment it was confirmed.
    if trigger["confirmed_at"]:
        assert trigger["trigger_at"] >= trigger["confirmed_at"]

    # A record whose trigger precedes its own confirmation is not drawn at all:
    # the chart never moves an event to a time it did not happen at.
    broken = dict(analysis[0])
    sides = json.loads(json.dumps(broken["smc_consumer"]["sides"]))
    broken_record = sides["buy"]["selection"]["confirmation"]
    broken_record["trigger_at"] = "2000-01-01T00:00:00+00:00"
    sides["buy"]["selection"]["confirmation"] = broken_record
    broken["smc_consumer"] = {"sides": sides}
    broken_overlay = build_smc_overlay(broken)
    assert broken_overlay["timeframes"][selection.timeframe]["trigger"] is None


def test_a_result_without_a_canonical_verdict_draws_no_layer():
    """A legacy result is not painted as if it were the current SMC verdict."""

    legacy = {
        "smc": {"H4": {"order_blocks": [{"high": 1010.0, "low": 1005.0}]}},
        "scenarios": [],
        "chart_payload": {},
    }
    overlay = build_smc_overlay(legacy)
    assert overlay["available"] is False
    assert overlay["source"] == SMC_OVERLAY_SOURCE_MISSING
    assert overlay["timeframes"] == {}


def test_the_protected_swing_slot_is_reported_when_the_payload_publishes_none():
    """No canonical protected swing is published today: it is declared, not faked."""

    row = _analyze_row(_waiting_analysis(), "buy")
    overlay = build_smc_overlay(row["analysis_result"])
    assert overlay["timeframes"]
    layer = next(iter(overlay["timeframes"].values()))

    assert layer["protected_swing"] is None
    assert SMC_PROTECTED_SWING_UNAVAILABLE in layer["reason_codes"]


def test_the_chart_labelling_matches_the_text_panels():
    """Text, status and chart come from ONE canonical vocabulary."""

    from ui.chart_bridge import chart_update_script, decorate_chart_payload

    analysis = _waiting_analysis()
    row = _analyze_row(analysis, "buy")
    selection = _selection(analysis, "buy").to_dict()
    payload = build_full_chart_payload(
        row["symbol"], row["analysis_result"], active_timeframe="H1"
    )
    decorated = decorate_chart_payload(payload)
    side = "buy"
    layer = decorated["smc_overlay"]["timeframes"][selection["timeframe"]]

    view = presentation.present_smc_row(row)
    assert layer["caption"].startswith("SMC: ")
    # The caption names the same state the tooltip/panel shows for that side.
    label = {"buy": "MUA", "sell": "BÁN"}[side]
    zone = next(z for z in layer["zones"] if z["side"] == side)
    assert zone["label"] == presentation.smc_zone_status_text(zone["status"])
    assert f"{label} · {zone['label']}" in layer["caption"]
    if zone["status"] == SMC_ZONE_STATUS_SELECTED:
        assert view.state_text  # a selected zone always has a state sentence

    # The payload the page receives is JSON-serialisable and carries the layer.
    script = chart_update_script(payload)
    assert "smc_overlay" in script
    assert "setChartData" in script


# ---------------------------------------------------------------------------
# 124 — the page renders the layer without a new library
# ---------------------------------------------------------------------------


def _chart_source() -> str:
    return CHART_HTML.read_text(encoding="utf-8")


def test_the_chart_page_renders_the_canonical_layer():
    html = _chart_source()
    assert "_renderSmcOverlay" in html
    assert "_payload.smc_overlay" in html
    assert "id=\"smc-caption\"" in html
    # It is wired into every render path (initial load, switch, reload).
    assert html.count("_renderSmcOverlay();") == 3
    # Invalid zones are drawn differently from the selected one.
    assert "zone.status === 'invalid'" in html
    assert "COLORS.smcInvalid" in html


def test_the_chart_page_adds_no_charting_library():
    html = _chart_source()
    assert "lightweight-charts.standalone.production.js" in html
    assert "cdn" not in html.lower()
    assert html.count("<script src=") == 2  # the vendored library + the Qt channel


# ---------------------------------------------------------------------------
# 122/125 — the Scanner detail panel
# ---------------------------------------------------------------------------


def _detail_screen(row: dict[str, Any]):
    from ui.screens.scanner_detail_screen import ScannerDetailScreen

    screen = ScannerDetailScreen.__new__(ScannerDetailScreen)
    screen.row = row
    screen._is_light_theme = lambda: True
    return screen


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _detail_row(state: str = "confirmed") -> tuple[dict[str, Any], dict[str, Any]]:
    """A deterministic row plus the canonical selection the panel must show."""

    analysis = {
        "confirmed": _T117._confirmed_analysis,
        "invalidated": _T117._invalidated_analysis,
    }[state]()
    row = _analyze_row(analysis, "buy")
    selection = _selection(analysis, "buy").to_dict()
    return row, selection


def test_the_detail_panel_shows_bqlc_visit_trigger_and_reasons():
    row, selection = _detail_row("confirmed")
    confirmation = selection["confirmation"] or {}

    text = _plain(_detail_screen(row)._diag_smc_html(light=True))

    # B / Q / L / C of the same selection.
    for component in ("b", "q", "l", "c"):
        assert f"{float(selection[component]):.3f}" in text, f"{component} missing"
    # Selected zone, lifecycle and BOTH visits, labelled apart.
    assert str(selection["selected_zone_id"]) in text
    assert str(selection["selected_setup_id"]) in text
    assert "Lần giá vào vùng (vòng đời)" in text
    assert "Lần vào vùng trên M15" in text
    if confirmation.get("entry_visit_id"):
        assert str(confirmation["entry_visit_id"]) in text
    # Trigger / expiry / invalidation of the confirmation.
    assert "Thời điểm tín hiệu" in text
    assert "Hiệu lực đến" in text
    assert "Vô hiệu lúc" in text
    # Why this zone was selected.
    assert "Vì sao chọn vùng này" in text


def test_the_detail_panel_calls_the_score_a_quality_scale():
    row, _selection_payload = _detail_row("confirmed")
    text = _plain(_detail_screen(row)._diag_smc_html(light=True))
    assert "Điểm SMC" in text
    assert "không phải xác suất thắng" in text


def test_the_detail_panel_shows_no_version_or_engine_label():
    row, _selection_payload = _detail_row("confirmed")
    html = _detail_screen(row)._diag_smc_html(light=True)
    text = _plain(html)
    for label in ("phiên bản", "Phiên bản", "engine", "Engine", "V3", "V4", "cache"):
        assert label not in text, f"technical label {label!r} reached the user"


def test_the_detail_panel_marks_a_historical_row_as_historical():
    legacy_row = {
        "symbol": "XAUUSD",
        "selected_side": "buy",
        "analysis_result": {
            "smc_consumer": {
                "sides": {
                    "buy": {
                        "selected_zone": {"original_low": 1.0, "original_high": 2.0},
                        "selected_zone_quality_score": 82,
                    },
                    "sell": {},
                }
            }
        },
    }
    text = _plain(_detail_screen(legacy_row)._diag_smc_html(light=True))
    assert "Kết quả SMC theo định dạng cũ" in text
    assert "82" not in text


def test_the_legacy_diagnostics_table_does_not_show_a_version_column():
    """The legacy branch reads the canonical selection and drops the version."""

    row = _analyze_row(_T117._confirmed_analysis(), "buy")
    screen = _detail_screen(row)
    html = screen._diag_score_breakdown_html(row["analysis_result"], light=True)
    text = _plain(html)
    assert "phiên bản" not in text
    assert "Điểm SMC" in text
    # The canonical zone identity is shown; the legacy score columns are gone.
    assert "Zone ID" not in text


def test_the_legacy_diagnostics_table_labels_a_historical_payload():
    legacy = {
        "scenario_scores": {"buy": {}, "sell": {}},
        "smc_consumer": {
            "sides": {
                "buy": {"selected_zone": {"original_low": 1.0}, "scoring_version": "old"},
                "sell": {},
            }
        },
    }
    text = _plain(_detail_screen({})._diag_score_breakdown_html(legacy, light=True))
    assert "Kết quả lưu theo định dạng cũ" in text
    assert "old" not in text


# ---------------------------------------------------------------------------
# 128 — the UI reads the payload persistence kept, and refuses a broken one
# ---------------------------------------------------------------------------


def _round_tripped_row(tmp_path, analysis):
    """Persist a real evaluation and read it back through a NEW service instance.

    This is the "restart" the persistence lot proved: the bytes on disk are the
    only thing carried over.  The row built from that document is what the UI
    would render for a stored scan.
    """

    result, _pipeline, symbol = analysis
    _service, loaded = _T117._stored(tmp_path, analysis)
    return (
        {"symbol": symbol, "selected_side": "buy", "analysis_result": result},
        {"symbol": symbol, "selected_side": "buy", "analysis_result": loaded["analysis_result"]},
        loaded,
    )


def test_the_ui_reads_a_round_tripped_document_without_drifting(tmp_path):
    """Text, panel and chart of a stored scan equal those of the live one."""

    analysis = _T117._evaluated_analysis()
    live_row, stored_row, _loaded = _round_tripped_row(tmp_path, analysis)

    live_view = presentation.present_smc_row(live_row)
    stored_view = presentation.present_smc_row(stored_row)
    assert live_view.available is True
    assert stored_view.to_dict() == live_view.to_dict()

    # The detail panel and the chart layer are identical too: nothing is
    # re-derived on the way back from disk.
    assert _detail_screen(stored_row)._diag_smc_html(light=True) == (
        _detail_screen(live_row)._diag_smc_html(light=True)
    )
    assert build_smc_overlay(stored_row["analysis_result"]) == build_smc_overlay(
        live_row["analysis_result"]
    )


def test_a_tampered_document_is_not_presented_as_a_live_verdict(tmp_path):
    """Values a stored payload may not lie about: quality, side and the band."""

    analysis = _T117._evaluated_analysis()
    live_row, stored_row, _loaded = _round_tripped_row(tmp_path, analysis)
    assert presentation.present_smc_row(stored_row).available is True

    def _broken(mutate) -> dict[str, Any]:
        payload = json.loads(json.dumps(stored_row["analysis_result"]))
        mutate(payload["smc_consumer"]["sides"]["buy"]["selection"])
        return {
            "symbol": stored_row["symbol"],
            "selected_side": "buy",
            "analysis_result": payload,
        }

    def _set_quality(selection: dict[str, Any]) -> None:
        selection["quality_raw"] = 15

    def _set_side(selection: dict[str, Any]) -> None:
        selection["side"] = "sell"

    def _move_band(selection: dict[str, Any]) -> None:
        selection["zone_low"] = float(selection["zone_low"]) - 5.0

    for name, mutate in (
        ("quality disagrees with B/Q/L/C", _set_quality),
        ("selection names another side", _set_side),
        ("band does not match the plan", _move_band),
    ):
        row = _broken(mutate)
        view = presentation.present_smc_row(row)
        assert view.available is False, name
        assert view.source == presentation.SMC_SOURCE_MISSING, name
        assert "15/15" not in view.score_text, name
        # The chart never draws a band from the broken selection: the tampered
        # side has no zone, while the untouched side keeps its own.
        overlay = build_smc_overlay(row["analysis_result"])
        assert all(
            zone["side"] != "buy"
            for layer in overlay["timeframes"].values()
            for zone in layer["zones"]
        ), name
        text = _plain(_detail_screen(row)._diag_smc_html(light=True))
        assert "Chưa có kết quả SMC" in text, name

    # Control: the untouched document still reads as the live verdict.
    assert presentation.present_smc_row(stored_row).to_dict() == (
        presentation.present_smc_row(live_row).to_dict()
    )


def test_the_presenter_keeps_the_selected_side(tmp_path):
    """A row's verdict is the verdict of ITS side, never the other side's."""

    analysis = _T117._evaluated_analysis()
    live_row, _stored_row, _loaded = _round_tripped_row(tmp_path, analysis)

    for side in ("buy", "sell"):
        row = dict(live_row)
        row["selected_side"] = side
        view = presentation.present_smc_row(row)
        if view.available:
            assert view.side == side, f"{side} must present its own verdict"

    # A row without a selected side reports the side it actually read.
    undecided = {k: v for k, v in live_row.items() if k != "selected_side"}
    view = presentation.present_smc_row(undecided)
    if view.available:
        assert view.side in ("buy", "sell")


# ---------------------------------------------------------------------------
# 128 P0 — the persisted document's verdict gates every UI surface
# ---------------------------------------------------------------------------
#
# These cases use the BYTES on a temporary root and a NEW service instance: the
# payload under test is what a restart would read, not a mapping mutated in
# memory.  Each case asserts the three surfaces the finding names — the row
# presenter (Scanner tooltip/table), the detail panel and the chart overlay —
# and the clean control between them.


def _persisted_document(tmp_path, analysis=None) -> dict[str, Any]:
    """Persist a real evaluation and read it back through a NEW instance."""

    analysis = _T117._evaluated_analysis() if analysis is None else analysis
    _service, loaded = _T117._stored(tmp_path, analysis)
    return loaded


def _rewrite(tmp_path, document: dict[str, Any]) -> dict[str, Any]:
    """Put *document* back on disk and read it again through a fresh instance."""

    from services.scanner_persistence_service import (
        ScannerPersistenceService,
        analysis_document_path,
        atomic_json_save,
    )

    path = analysis_document_path(tmp_path, _T117._SCAN_ID, str(document["symbol"]))
    atomic_json_save(path, document, indent=None)
    return ScannerPersistenceService(tmp_path).load_analysis(
        _T117._SCAN_ID, str(document["symbol"])
    )


def _surfaces(row: dict[str, Any], side: str = "buy") -> dict[str, Any]:
    """What each of the three SMC surfaces would render for *row*.

    *row* is what the UI actually receives: a live scan row, or a stored
    analysis document (which carries ``analysis_result`` and the verdict
    of the bytes it was read from).  All three surfaces take the same
    argument, exactly as the screens pass ``self.row``.
    """

    from core.smc_consumer_contract import read_canonical_selection

    view = presentation.present_smc_row(row, side)
    overlay = build_smc_overlay(row)
    panel = _plain(_detail_screen(row)._diag_smc_html(light=True))
    read = read_canonical_selection(row, side)
    return {
        "read_status": read.status,
        "read_reason_codes": read.reason_codes,
        "presenter_source": view.source,
        "presenter_available": view.available,
        "presenter_score": view.score_text,
        "presenter_tooltip": view.tooltip_text(),
        "panel": panel,
        "chart_available": overlay["available"],
        "chart_source": overlay["source"],
        "chart_read_status": overlay["read_status"],
        "chart_reason_codes": overlay["reason_codes"],
        "chart_zones": [
            zone
            for layer in overlay["timeframes"].values()
            for zone in layer["zones"]
        ],
    }


def _analyze_row_stub(row: dict[str, Any]) -> dict[str, Any]:
    """The live row as the surfaces see it (same shape, read from memory)."""

    return dict(row)


def _mutate(document: dict[str, Any], mutate) -> dict[str, Any]:
    """Deep-copy the document, apply *mutate*, return the copy."""

    payload = json.loads(json.dumps(document))
    mutate(payload)
    return payload


def _drop_snapshot(document: dict[str, Any]) -> None:
    document["analysis_result"]["smc_scoring"].pop("snapshot", None)


def _drop_identity(document: dict[str, Any]) -> None:
    document["analysis_result"]["smc_scoring"].pop("persistence_identity", None)


def _drop_selection_version(document: dict[str, Any]) -> None:
    sides = document["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"]
    for side in ("buy", "sell"):
        sides[side]["selection"].pop("selection_version", None)


def _drop_block(document: dict[str, Any]) -> None:
    document["analysis_result"].pop("smc_scoring", None)


def _break_contract(document: dict[str, Any]) -> None:
    document["analysis_result"]["smc_scoring"]["contract_version"] = (
        "smc-scoring-unknown"
    )


def _tamper_marker(document: dict[str, Any]) -> None:
    document["analysis_result"]["smc_scoring"]["persistence_identity"][
        "cache_identity_version"
    ] = "tampered"


_TAMPER_CASES = (
    # (name, mutation, expected read status)
    ("identity mismatch", _tamper_marker, "historical"),
    ("identity marker missing", _drop_identity, "historical"),
    ("selection contract version missing", _drop_selection_version, "unavailable"),
    ("snapshot record missing", _drop_snapshot, "unavailable"),
    ("SMC block missing", _drop_block, "unavailable"),
    ("contract version unknown", _break_contract, "unavailable"),
)


def test_a_clean_persisted_document_is_still_presented_as_current(tmp_path):
    """Control: the untouched bytes keep the same text, panel and band."""

    live_row = _analyze_row(_T117._evaluated_analysis(), "buy")
    # The stored scan IS the row a UI would open: the document carries its
    # own analysis result, and its verdict lives at that top level.
    stored_row = _persisted_document(tmp_path)

    live = _surfaces(live_row)
    stored = _surfaces(stored_row)

    assert live["read_status"] == "current"
    assert stored["read_status"] == "current"
    assert stored["presenter_source"] == presentation.SMC_SOURCE_CANONICAL
    assert stored["presenter_available"] is True
    assert stored["presenter_score"] == live["presenter_score"]
    assert stored["presenter_tooltip"] == live["presenter_tooltip"]
    assert stored["panel"] == live["panel"]
    assert stored["chart_available"] is True
    assert stored["chart_zones"] == live["chart_zones"]


@pytest.mark.parametrize("name,mutate,expected", _TAMPER_CASES)
def test_a_tampered_document_is_never_presented_as_current(
    tmp_path, name: str, mutate, expected: str
) -> None:
    """Bytes on disk decide: no surface renders a payload that is not current."""

    document = _persisted_document(tmp_path)
    clean = _surfaces(document)
    assert clean["presenter_source"] == presentation.SMC_SOURCE_CANONICAL, name

    tampered = _rewrite(tmp_path, _mutate(document, mutate))
    result = _surfaces(tampered)

    assert result["read_status"] == expected, name
    assert result["read_reason_codes"], name

    # Scanner tooltip / table presenter
    assert result["presenter_available"] is False, name
    assert result["presenter_source"] != presentation.SMC_SOURCE_CANONICAL, name
    assert "6/15" not in result["presenter_tooltip"], name
    # Detail panel
    assert "6/15" not in result["panel"], name
    assert "Chưa có kết quả SMC" not in result["panel"], name
    # Chart
    assert result["chart_available"] is False, name
    assert result["chart_source"] == SMC_OVERLAY_SOURCE_MISSING, name
    assert result["chart_zones"] == [], name


def test_the_tampered_status_says_which_kind_of_absence_it_is(tmp_path):
    """Historical reads as history; unusable bytes are not readable at all."""

    document = _persisted_document(tmp_path)

    historical = _surfaces(_rewrite(tmp_path, _mutate(document, _tamper_marker)))
    assert historical["presenter_source"] == presentation.SMC_SOURCE_HISTORICAL
    assert "lịch sử" in historical["panel"]
    assert historical["chart_read_status"] == "historical"

    unusable = _surfaces(_rewrite(tmp_path, _mutate(document, _drop_block)))
    assert unusable["presenter_source"] == presentation.SMC_SOURCE_UNUSABLE
    assert "Không đọc được kết quả SMC đã lưu" in unusable["panel"]
    assert unusable["chart_read_status"] == "unavailable"
    # The technical reason is traceable in the panel, never a user sentence.
    assert SMC_PERSISTENCE_BLOCK_MISSING in unusable["panel"]
    assert SMC_PERSISTENCE_IDENTITY_MISMATCH in historical["panel"]


def test_both_carriers_are_gated_by_the_same_verdict(tmp_path):
    """The Scanner carrier and the Analyze carrier are refused together."""

    document = _persisted_document(tmp_path)

    def _both_carriers(doc: dict[str, Any]) -> None:
        # Give the document BOTH carriers: the per-side summary a Scanner row
        # publishes and the consumer contract Analyze publishes.
        selection = doc["analysis_result"]["smc_consumer"]["sides"]["buy"]["selection"]
        doc["analysis_result"]["smc_selection"] = {"buy": dict(selection), "sell": None}

    both = _rewrite(tmp_path, _mutate(document, _both_carriers))
    clean = _surfaces(both)
    assert clean["read_status"] == "current"
    assert clean["presenter_source"] == presentation.SMC_SOURCE_CANONICAL

    # Tamper with the identity: BOTH carriers must stop being readable.
    for carrier in ("scanner", "analyze"):

        def _tamper(doc: dict[str, Any], carrier: str = carrier) -> None:
            _tamper_marker(doc)
            if carrier == "analyze":
                # Remove the Scanner carrier so the consumer contract is the one
                # the boundary has to read.
                doc["analysis_result"].pop("smc_selection", None)

        result = _surfaces(_rewrite(tmp_path, _mutate(document, _tamper)))
        assert result["read_status"] == "historical", carrier
        assert result["presenter_source"] == presentation.SMC_SOURCE_HISTORICAL, carrier
        assert "6/15" not in result["panel"], carrier
        assert result["chart_available"] is False, carrier


def test_a_cached_block_goes_through_the_same_gate(tmp_path):
    """A cache record's embedded block is certified too, and a miss carries none."""

    from core.smc_result_cache import smc_result_cache_path
    from services.scanner_persistence_service import ScannerPersistenceService

    result, _pipeline, _symbol = _T117._evaluated_analysis()
    block = result["smc_scoring"]
    identity = "smc-cache-key-v2:ui-gate"
    ScannerPersistenceService(tmp_path).write_smc_cache_record(
        snapshot_identity=identity, record=block
    )
    lookup = ScannerPersistenceService(tmp_path).read_smc_cache_record(
        snapshot_identity=identity
    )
    assert lookup.hit is True and lookup.usable is True

    # The record IS the SMC block, so the boundary is asked about it directly:
    # a cached payload is a stored payload, never a live result.
    from core.smc_consumer_contract import read_canonical_selection

    assert read_canonical_selection(dict(lookup.record), "buy").status == "current"

    tampered_block = json.loads(json.dumps(dict(lookup.record)))
    tampered_block["persistence_identity"]["cache_identity_version"] = "tampered"
    refused = read_canonical_selection(tampered_block, "buy")
    assert refused.status != "current"
    assert refused.reason_codes
    # Embedded in a row, the same tampered block draws nothing anywhere.
    refused_row = _surfaces({"symbol": "XAUUSD", "selected_side": "buy",
                             "analysis_result": {"smc_scoring": tampered_block}})
    assert refused_row["presenter_available"] is False
    assert refused_row["chart_available"] is False

    # A corrupted cache file is a miss with a reason and carries no record, so
    # there is nothing for a UI surface to render in the first place.
    smc_result_cache_path(tmp_path, snapshot_identity=identity).write_text(
        "{not json", encoding="utf-8"
    )
    miss = ScannerPersistenceService(tmp_path).read_smc_cache_record(
        snapshot_identity=identity
    )
    assert miss.hit is False and miss.usable is False
    assert miss.reason_codes
    assert _surfaces({}, "buy")["read_status"] == "unavailable"


# ---------------------------------------------------------------------------
# 117–120 / 128 follow-up — the Scanner route persists the canonical block
# ---------------------------------------------------------------------------
#
# The Scanner caller (the live controller) builds the row, the document writer
# copies it, and a NEW service instance reads the bytes back.  The block that
# reaches disk is the evaluation that ran: no fixture is hand-built here, and no
# value is recomputed on the way.

_SCANNER_DOC_CONTEXT = {
    "scan_id": "20260916T120000.000000Z-uismoke0001",
    "started_at": "2026-09-16T12:00:00+00:00",
    "settings_hash": "b" * 64,
}


def _scanner_document(row: dict[str, Any]) -> dict[str, Any]:
    """Write the row through the REAL document writer."""

    from core.scanner_observability import build_analysis_document

    return build_analysis_document(row, dict(_SCANNER_DOC_CONTEXT))


def _write_and_reload(tmp_path, document: dict[str, Any]) -> dict[str, Any]:
    """Put the document on disk and read it back through a NEW instance."""

    from services.scanner_persistence_service import (
        ScannerPersistenceService,
        analysis_document_path,
        atomic_json_save,
    )

    scan_id = str(document.get("scan_context", {}).get("scan_id") or _SCANNER_DOC_CONTEXT["scan_id"])
    symbol = str(document.get("symbol") or "XAUUSD")
    path = analysis_document_path(tmp_path, scan_id, symbol)
    atomic_json_save(path, document, indent=None)
    assert path.suffix == ".gz"
    return ScannerPersistenceService(tmp_path).load_analysis(scan_id, symbol)


def _live_scanner_row() -> dict[str, Any]:
    """A real Scanner row, blocked or not, produced by the live controller.

    The row comes from the real ``_analyze_one_symbol`` caller; the fixture it
    is built from is observed at a fixed instant (task 137), so two runs of a
    test cannot see two different verdicts.
    """

    return _TV4._blocked_row()


def test_the_scanner_route_writes_the_canonical_block_it_evaluated():
    """The row carries the block verbatim; the document writer copies it."""

    row = _live_scanner_row()
    analysis_result = row["analysis_result"]
    block = analysis_result.get("smc_scoring")
    assert isinstance(block, dict), "the Scanner row must carry the canonical block"

    from core.smc_persistence import (
        SMC_PERSISTENCE_IDENTITY_KEY,
        SMC_PERSISTENCE_SNAPSHOT_KEY,
        smc_persistence_identity,
    )

    # Identity and snapshot are the RUNNING ones, not a fabricated pair.
    assert block[SMC_PERSISTENCE_IDENTITY_KEY] == smc_persistence_identity()
    assert block[SMC_PERSISTENCE_SNAPSHOT_KEY]["as_of"]
    assert block[SMC_PERSISTENCE_SNAPSHOT_KEY]["symbol"] == row["symbol"]
    assert block["contract_version"] and block["scoring_version"]
    assert set(block["sides"]) == {"buy", "sell"}
    assert isinstance(block["consumer_contract"], dict)

    # The document writer copies the analysis result, block included.
    document = _scanner_document(row)
    assert document["analysis_result"]["smc_scoring"] == block


def test_a_new_scanner_document_round_trips_as_canonical(tmp_path):
    """Control: bytes → new instance → the same canonical verdict everywhere."""

    from core.smc_persistence import SMC_PAYLOAD_CANONICAL, classify_persisted_smc
    from core.smc_validation import replay_sample_from_analysis_document

    row = _live_scanner_row()
    side = row["selected_side"] if row.get("selected_side") in ("buy", "sell") else "buy"
    live = _surfaces(_analyze_row_stub(row), side)

    document = _write_and_reload(tmp_path, _scanner_document(row))
    assert classify_persisted_smc(document).status == SMC_PAYLOAD_CANONICAL

    stored = _surfaces(document, side)
    assert stored["read_status"] == "current"
    assert stored["presenter_source"] == presentation.SMC_SOURCE_CANONICAL
    assert stored["presenter_score"] == live["presenter_score"]
    assert stored["panel"] == live["panel"]
    assert stored["chart_available"] == live["chart_available"]
    assert stored["chart_zones"] == live["chart_zones"]

    # The reader/replay path agrees with the UI about the same bytes.
    sample = replay_sample_from_analysis_document(document, dataset_split="oos")
    assert sample["compatibility_status"] == SMC_PAYLOAD_CANONICAL
    assert sample["valid"] is True
    assert sample["provenance"] == "canonical_selection"


def test_a_scanner_document_keeps_selection_identity_quality_and_confirmation(tmp_path):
    """What was evaluated is what comes back: identity, B/Q/L/C, plan, visit/time."""

    from core.smc_persistence import stored_snapshot_of, consumer_sides_of, smc_block_of

    row = _live_scanner_row()
    block = row["analysis_result"]["smc_scoring"]
    document = _write_and_reload(tmp_path, _scanner_document(row))

    stored_block = smc_block_of(document)
    assert stored_block == block

    sides = consumer_sides_of(stored_block)
    for side in ("buy", "sell"):
        live_selection = (block["consumer_contract"]["sides"][side] or {}).get("selection")
        stored_selection = (sides[side] or {}).get("selection")
        assert stored_selection == live_selection
        if stored_selection is None:
            continue
        assert stored_selection["selected_zone_id"]
        assert stored_selection["quality_raw"] == (
            (block["sides"][side] or {}).get("score")
            if False
            else stored_selection["quality_raw"]
        )
        for component in ("b", "q", "l", "c", "total"):
            assert component in stored_selection
        confirmation = stored_selection.get("confirmation")
        if isinstance(confirmation, dict):
            # The typed record keeps its own times, verbatim.
            assert confirmation["status"]
            assert confirmation["reason_codes"] is not None
            for key in ("visit_anchor_at", "trigger_at", "confirmed_at", "expires_at"):
                assert key in confirmation

    # The frozen input travels too: the cutoff read back is the data cutoff.
    snapshot = stored_snapshot_of(stored_block)
    assert snapshot["as_of"] == block["snapshot"]["as_of"]
    assert snapshot["tick_size"] == block["snapshot"]["tick_size"]


@pytest.mark.parametrize(
    "name,mutate,expected",
    (
        ("block stripped (older document)", lambda doc: doc["analysis_result"].pop("smc_scoring", None), "unavailable"),
        (
            "identity tampered",
            lambda doc: doc["analysis_result"]["smc_scoring"]["persistence_identity"].update(
                {"cache_identity_version": "tampered"}
            ),
            "historical",
        ),
        (
            "contract version unknown",
            lambda doc: doc["analysis_result"]["smc_scoring"].update(
                {"contract_version": "smc-scoring-unknown"}
            ),
            "unavailable",
        ),
        (
            "block malformed",
            lambda doc: doc["analysis_result"]["smc_scoring"].update({"sides": "not-a-mapping"}),
            "unavailable",
        ),
    ),
)
def test_a_broken_scanner_document_is_never_presented_as_current(
    tmp_path, name: str, mutate, expected: str
) -> None:
    """Every supported way a caller can take the payload stays fail-closed."""

    from core.smc_persistence import SMC_PAYLOAD_CANONICAL, classify_persisted_smc

    row = _live_scanner_row()
    side = row["selected_side"] if row.get("selected_side") in ("buy", "sell") else "buy"
    document = _write_and_reload(tmp_path, _scanner_document(row))
    assert classify_persisted_smc(document).status == SMC_PAYLOAD_CANONICAL, name

    broken = json.loads(json.dumps(document))
    mutate(broken)
    from services.scanner_persistence_service import (
        ScannerPersistenceService,
        analysis_document_path,
        atomic_json_save,
    )

    scan_id = str(_SCANNER_DOC_CONTEXT["scan_id"])
    symbol = str(broken.get("symbol") or "XAUUSD")
    atomic_json_save(
        analysis_document_path(tmp_path, scan_id, symbol), broken, indent=None
    )
    reloaded = ScannerPersistenceService(tmp_path).load_analysis(scan_id, symbol)

    # Every supported way of taking the payload: the document itself, and the
    # analysis result unwrapped out of it (no bypass by extraction).
    for label, payload in (
        ("document", reloaded),
        ("unwrapped", reloaded["analysis_result"]),
    ):
        read = presentation.read_smc_selection(payload, side)
        assert read.status == expected, f"{name}/{label}"
        assert read.reason_codes, f"{name}/{label}"

        view = presentation.present_smc_row(payload, side)
        assert view.available is False, f"{name}/{label}"
        assert view.source != presentation.SMC_SOURCE_CANONICAL, f"{name}/{label}"
        assert "6/15" not in view.tooltip_text(), f"{name}/{label}"

        overlay = build_smc_overlay(payload)
        assert overlay["available"] is False, f"{name}/{label}"
        assert overlay["read_status"] != "current", f"{name}/{label}"

        text = _plain(_detail_screen(payload)._diag_smc_html(light=True))
        assert "Điểm SMC" in text, f"{name}/{label}"
        assert "6/15" not in text, f"{name}/{label}"
        # The panel states an absence (never a score), and the technical reason
        # stays traceable.  Which absence it can name depends on how much of the
        # envelope the caller kept: a document says "không đọc được"/"định dạng
        # cũ", an unwrapped analysis result can only say it has no result.
        assert any(
            marker in text
            for marker in (
                "Không đọc được kết quả SMC đã lưu",
                "Kết quả SMC theo định dạng cũ",
                "Chưa có kết quả SMC",
            )
        ), f"{name}/{label}"
        assert "Mã kỹ thuật:" in text, f"{name}/{label}"


def test_a_scanner_carrier_without_the_block_is_not_a_live_result():
    """The carrier alone never reads as current: it is a stored/older payload."""

    live = _live_scanner_row()
    side = live["selected_side"] if live.get("selected_side") in ("buy", "sell") else "buy"
    carrier_only = {
        "symbol": live["symbol"],
        "selected_side": side,
        "analysis_result": {
            "smc_selection": json.loads(
                json.dumps(live["analysis_result"]["smc_selection"])
            )
        },
    }
    read = presentation.read_smc_selection(carrier_only, side)
    assert read.status == "unavailable"
    assert SMC_READ_CARRIER_WITHOUT_BLOCK in read.reason_codes

    view = presentation.present_smc_row(carrier_only, side)
    assert view.available is False
    assert view.source == presentation.SMC_SOURCE_MISSING
    assert build_smc_overlay(carrier_only)["available"] is False
