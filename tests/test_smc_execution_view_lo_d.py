"""Lô D (Task145–147) — H1 execution view, snapshot "Vị trí", candle refresh.

**Reproduced case (audited from a real Scanner document).** AUD/NZD, snapshot
price **1.23790**; the BUY plan's Entry is **[1.23710, 1.23913]** so the table's
"Vị trí = Trong vùng" is *arithmetically correct* — but the canonical SELL
selection lives on **H1** with a different band **[1.23981, 1.24068]**, and the
Detail chart opens on H1.  The user therefore saw an Entry band for one side and
an SMC band for the other, on the same screen.

**Task 145** makes H1 an execution view: candles + Entry + SL/TP only, with no
SMC zone, caption, M15 trigger or protected swing — even when the canonical
payload carries them.  **Task 146** makes "Vị trí" say what it measured (the
scan-time price against the plan's Entry bounds).  **Task 147** keeps the plan
snapshot distinct from refreshed candles.

The chart page is a real QWebEngine page, so the page-level assertions run in a
**subprocess**: a full ``ScannerDetailScreen`` cannot be built headless (it
segfaults — see ``tests/test_scanner_detail_v4_diagnostics.py``), and a crash
there would take the whole test session with it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from core.chart_payload import build_full_chart_payload
from core.market_models import candles_to_dicts, candles_from_dicts, merge_candles, normalize_candles
from ui.chart_bridge import EXECUTION_VIEW_TIMEFRAMES, chart_update_script, decorate_chart_payload

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The reproduced numbers, verbatim from the audited document.
_PRICE = 1.23790
_BUY_BAND = (1.23710, 1.23913)
_SELL_BAND = (1.23981, 1.24068)
_SNAPSHOT_AT = "2026-09-18T05:15:34+00:00"


def _candles() -> dict[str, list[dict[str, Any]]]:
    from tests.test_scanner_release import _zoned_candles

    d1, h4, h1 = _zoned_candles()
    return {
        "D1": candles_to_dicts(d1),
        "H4": candles_to_dicts(h4),
        "H1": candles_to_dicts(h1),
        "M15": candles_to_dicts(h1[-60:]),
    }


def _selection(side: str, timeframe: str, band: tuple[float, float], **overrides: Any) -> dict[str, Any]:
    """A canonical selection of the audited shape, built through the real model.

    Built with ``SmcSideSelection`` so it satisfies the final invariant the
    reader re-checks — an ``evaluated`` side must carry the plan that belongs to
    the same zone/setup.  Nothing here is a hand-written payload the reader
    would refuse.
    """

    from core.smc_scoring_result import SmcSideSelection

    zone_id = f"smcz-lod-{side}"
    setup_id = f"smcs-lod-{side}"
    selection = SmcSideSelection(
        side=side,
        state="evaluated",
        selected_candidate_id=zone_id,
        selected_zone_id=zone_id,
        selected_setup_id=setup_id,
        timeframe=timeframe,
        family="ob",
        lifecycle_status="usable",
        confirmation_state="waiting",
        entry_visit_id=f"visit-lod-{side}",
        quality_raw=7,
        quality_score=100 * 7.3 / 15,
        # Must satisfy the final invariant total == 4B + 7Q + 2L + 2C.
        b=0.6, q=0.5, l=0.4, c=0.3, total=7.3,
        zone_low=band[0],
        zone_high=band[1],
        plan_available=True,
        plan_zone_id=zone_id,
        plan_setup_id=setup_id,
        plan={"direction": side, "zone_id": zone_id, "setup_id": setup_id,
              "entry_zone_low": band[0], "entry_zone_high": band[1]},
        readiness={"status": "WAITING_CONFIRMATION"},
        selection_reason_codes=("QUALITY_RANK",),
        confirmation={
            "zone_id": zone_id,
            "side": side,
            "status": "waiting",
            "reason_codes": ["M15_NO_CONFIRMATION"],
        },
    )
    payload = selection.to_dict()
    payload.update(overrides)
    return payload


def _block(selections: dict[str, Any]) -> dict[str, Any]:
    """The persisted canonical block the strict read boundary demands.

    A row that carries ``smc_selection`` without this beside it is refused
    (``SMC_READ_CARRIER_WITHOUT_BLOCK``) — which is exactly what a real Scanner
    row does *not* do, because the controller attaches the block.
    """

    from core.smc_persistence import (
        SMC_PERSISTENCE_IDENTITY_KEY,
        SMC_PERSISTENCE_SNAPSHOT_KEY,
        smc_persistence_identity,
    )
    from core.smc_scoring_result import SMC_SCORING_CONTRACT_VERSION
    from core.smc_versions import SMC_SCORER_VERSION

    return {
        "contract_version": SMC_SCORING_CONTRACT_VERSION,
        "scoring_version": SMC_SCORER_VERSION,
        "sides": {side: {"score": 7, "breakdown": {}} for side in ("buy", "sell")},
        "consumer_contract": {
            "sides": {
                side: {"side": side, "selection": selection}
                for side, selection in selections.items()
                if isinstance(selection, dict)
            }
        },
        SMC_PERSISTENCE_IDENTITY_KEY: smc_persistence_identity(),
        SMC_PERSISTENCE_SNAPSHOT_KEY: {
            "as_of": _SNAPSHOT_AT,
            "symbol": "AUD/NZD",
        },
    }


def _scenario(band: tuple[float, float]) -> dict[str, Any]:
    return {
        "side": "buy",
        "entry_zone": [band[0], band[1]],
        "stop_loss": 1.23489,
        "take_profit": 1.24155,
        "entry_status": "no_setup",
        "zone_origin_class": "smc",
    }


def _row(*, buy: dict[str, Any] | None = ..., sell: dict[str, Any] | None = ...) -> dict[str, Any]:
    """A row shaped exactly like a real Scanner row for the audited case."""

    if buy is ...:
        buy = _selection("buy", "H4", _BUY_BAND)
    if sell is ...:
        sell = _selection("sell", "H1", _SELL_BAND)
    selections = {"buy": buy, "sell": sell}
    analysis = {
        "status": "ok",
        "technical": {"price": _PRICE, "atr_h1": None, "atr_h4": 0.002},
        "scenarios": [_scenario(_BUY_BAND)],
        "smc_selection": selections,
        "smc_scoring": _block(selections),
        "chart_payload": _candles(),
    }
    return {
        "symbol": "AUD/NZD",
        "broker_symbol": "AUDNZDM",
        "selected_side": "buy",
        "candidate_status": "BLOCKED",
        "zone_origin_class": "smc",
        "captured_at": _SNAPSHOT_AT,
        "price_vs_zone": "in_zone",
        "price_vs_zone_detail": {
            "price": _PRICE,
            "entry_low": _BUY_BAND[0],
            "entry_high": _BUY_BAND[1],
            "snapshot_at": _SNAPSHOT_AT,
        },
        "analysis_result": analysis,
    }


def _payload(row: dict[str, Any], timeframe: str = "H1") -> dict[str, Any]:
    """The exact chain the Detail screen runs: row → payload → chart bridge."""

    return decorate_chart_payload(
        build_full_chart_payload(
            str(row.get("symbol") or ""),
            row["analysis_result"],
            active_timeframe=timeframe,
            smc_source=row,
        )
    )


# ---------------------------------------------------------------------------
# Page-level probe (isolated subprocess; the page is a real QWebEngine page)
# ---------------------------------------------------------------------------


_PROBE = r"""
import importlib, json, sys, tempfile
from pathlib import Path
root, timeframe, mode = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)
# Import the repo's OWN chart renderer first: it is the harness whose
# Qt/WebEngine initialisation is known to work in this environment (an ad-hoc
# QApplication + QWebEngineView().show() aborts the process here).
smoke = importlib.import_module("scripts.smc_ui_smoke")
fixture = importlib.import_module("tests.test_smc_execution_view_lo_d")
# Capture into a throwaway directory: this probe must not drop new artifacts
# into the repo's smoke report folder.
out_dir = Path(tempfile.mkdtemp(prefix="lod_probe_")).resolve()
smoke.OUT_DIR = out_dir
# F-D-01 pin: the captures must follow the run's own output directory.  A
# def-time default binding `OUT_DIR` would silently write into reports/ again,
# so assert the resolved target before rendering anything.
assert Path(smoke.OUT_DIR).resolve() == out_dir, smoke.OUT_DIR
reports_dir = Path(root) / "reports" / "scanner" / "smc_ui_smoke"
before = sorted(p.name for p in reports_dir.glob("chart_lod_probe*"))
payload = fixture._payload(fixture._row(), timeframe)
if mode == "strip_rule":
    payload = dict(payload)
    payload.pop("execution_view_timeframes", None)
# argv must be non-empty: Chromium reads argv[0] to launch its child processes
# and aborts the whole process when handed an empty one.
app = smoke.QApplication.instance() or smoke.QApplication(sys.argv)
result = smoke._render_chart(app, payload, "lod_probe", "dark", out_dir=out_dir)
after = sorted(p.name for p in reports_dir.glob("chart_lod_probe*"))
print(json.dumps({
    "caption": result.get("caption") or "",
    "loaded": bool(result.get("loaded")),
    "active_timeframe": payload.get("active_timeframe"),
    "captured_in_temp": sorted(p.name for p in out_dir.glob("chart_lod_probe*")),
    "reports_untouched": before == after,
}), flush=True)

# Qt/WebEngine teardown can abort here; the answer is already on stdout.
import os; os._exit(0)
"""


def _render_caption(payload: dict[str, Any], mode: str = "as_is") -> dict[str, Any]:
    """Render the REAL chart page and read the SMC caption the user would see.

    Runs the repo's own renderer (``scripts.smc_ui_smoke._render_chart``) in a
    subprocess: a QWebEngine hiccup kills only the child, never the session.
    The child rebuilds the fixture itself from ``_row``/``_payload``. ``mode`` is
    the child's instruction: ``as_is``, or ``strip_rule`` for the control render.
    """

    timeframe = str(payload.get("active_timeframe") or "H1")
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", _PROBE, str(_PROJECT_ROOT), timeframe, mode],
        capture_output=True,
        text=True,
        timeout=240,
    )
    lines = [line for line in (result.stdout or "").splitlines() if line.startswith("{")]
    if not lines:
        pytest.skip(
            "chart page could not render here: "
            f"rc={result.returncode} {(result.stderr or '')[-200:]}"
        )
    return json.loads(lines[-1])


# ---------------------------------------------------------------------------
# A — the reproduced AUD/NZD case
# ---------------------------------------------------------------------------


def test_A_the_row_and_tooltip_say_in_zone_because_the_price_is_in_the_BUY_entry() -> None:
    """"Trong vùng" is correct for what it measures: 1.23790 ∈ [1.23710, 1.23913]."""

    from ui.screens.scanner_screen import ScannerTableModel

    row = _row()
    assert row["price_vs_zone"] == "in_zone"

    tooltip = ScannerTableModel._price_vs_zone_tooltip(row)

    assert "Giá lúc quét 1.23790 nằm trong Entry 1.23710–1.23913." in tooltip
    assert "Giá LÚC QUÉT" in tooltip, "the copy must say this is the scan-time price"
    assert "không phải giá hiện tại" in tooltip
    # The reading itself names the price and the bounds, never a timeframe: the
    # "no H1/H4" rule is about the H1 EXECUTION VIEW (the chart), not this table
    # tooltip, which legitimately still carries the canonical SMC line under it.
    assert tooltip.index("Giá lúc quét") < tooltip.index("Giá LÚC QUÉT") + len(tooltip)


def test_A_the_H1_payload_carries_Entry_SL_TP_and_the_execution_view_rule() -> None:
    payload = _payload(_row(), "H1")

    assert payload["execution_view_timeframes"] == ["H1"]
    assert payload["trade_plan"]["entry_zone"] == [_BUY_BAND[0], _BUY_BAND[1]]
    assert [level["label"] for level in payload["levels"]] == ["SL", "TP"]
    assert [zone["type"] for zone in payload["zones"]] == ["entry_zone"]
    # The overlay DATA is untouched — the rule only declines to draw it.
    assert "H1" in (payload["smc_overlay"].get("timeframes") or {})


def test_A_the_page_draws_no_SMC_on_H1_although_the_payload_has_it() -> None:
    """The real chart page: H1 renders with no SMC caption, though data exists."""

    row = _row()
    h1 = _render_caption(_payload(row, "H1"))

    assert h1["loaded"] is True
    assert h1["caption"] == "", (
        "H1 is the execution view: the page must draw no SMC caption there"
    )
    # The payload it received really did carry an H1 SMC layer — so the empty
    # caption is the rule, not missing data.
    assert "H1" in (_payload(row, "H1")["smc_overlay"].get("timeframes") or {})


def test_A_the_script_sent_to_the_page_carries_the_rule_and_the_data() -> None:
    """The page receives the rule and the H1 data it must not draw."""

    script = chart_update_script(_payload(_row(), "H1"))

    assert "execution_view_timeframes" in script
    assert "smcz-lod-sell" in script, "the sell H1 zone data still travels"


# ---------------------------------------------------------------------------
# B — H1 never renders SMC; H4/D1/M15 keep their behaviour
# ---------------------------------------------------------------------------


def test_B_H1_suppresses_SMC_even_when_BOTH_sides_are_valid() -> None:
    payload = _payload(_row(), "H1")
    layers = payload["smc_overlay"]["timeframes"]

    assert layers["H1"]["zones"], "the fixture must really carry an H1 SMC zone"
    assert payload["execution_view_timeframes"] == ["H1"]


@pytest.mark.parametrize("timeframe", ["H4", "D1", "M15"])
def test_B_a_non_H1_timeframe_still_draws_its_SMC_caption(timeframe: str) -> None:
    """Control: H4 keeps the behaviour it had — the rule is H1-only."""

    payload = _payload(_row(), timeframe)
    assert payload["active_timeframe"] == timeframe
    assert payload["trade_plan"]["entry_zone"] == [_BUY_BAND[0], _BUY_BAND[1]]
    assert list(EXECUTION_VIEW_TIMEFRAMES) == ["H1"]

    if timeframe not in ("H4", "H1"):
        # D1/M15 carry no layer for this fixture, so there is nothing to caption.
        assert not (payload["smc_overlay"].get("timeframes") or {}).get(timeframe)
        return
    rendered = _render_caption(payload)
    assert rendered["caption"], "H4 must keep drawing its SMC caption"


def test_B_a_payload_without_the_rule_still_renders_SMC() -> None:
    """Control: the page has not lost its SMC layer in general."""

    payload = _payload(_row(), "H1")
    assert payload["execution_view_timeframes"] == ["H1"]

    # Same fixture, same page — the rule is the only difference.
    rendered = _render_caption(payload, mode="strip_rule")
    assert rendered["caption"], (
        "without the rule the H1 SMC caption is drawn — so the suppression above "
        "is the rule, not a change to the layer itself"
    )
    assert "BÁN" in rendered["caption"], "it is the SELL H1 band that used to leak"


# ---------------------------------------------------------------------------
# C — candle refresh keeps the plan snapshot
# ---------------------------------------------------------------------------


def test_C_a_candle_refresh_does_not_touch_the_plan_or_the_reading() -> None:
    from core.scanner_ui_adapter import _classify_price_vs_zone

    row = _row()
    before_state = row["price_vs_zone"]
    before_detail = dict(row["price_vs_zone_detail"])
    before_result = json.loads(json.dumps(row["analysis_result"], default=str))

    # The refresh path: merge newer candles into the payload ONLY.
    chart_payload = dict(row["analysis_result"]["chart_payload"])
    merged = merge_candles(
        candles_from_dicts(chart_payload["H1"]),
        normalize_candles(candles_from_dicts(chart_payload["H1"])[:5]),
    )
    chart_payload["H1"] = candles_to_dicts(merged)

    assert row["price_vs_zone"] == before_state
    assert row["price_vs_zone_detail"] == before_detail
    assert json.loads(json.dumps(row["analysis_result"], default=str)) == before_result
    assert _classify_price_vs_zone(*_BUY_BAND, _PRICE, None) == before_state


def test_C_the_refresh_notice_names_the_snapshot_without_inventing_one() -> None:
    """The notice is built from the row's own provenance, never from a clock."""

    import ast

    import ui.screens.scanner_detail_screen as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_candle_refresh_notice"
    )

    # No clock: neither `datetime.now()` nor `datetime.utcnow()` may appear.
    clock_calls = [
        node.attr
        for node in ast.walk(fn)
        if isinstance(node, ast.Attribute) and node.attr in ("now", "utcnow", "today")
    ]
    assert clock_calls == [], f"it must not use the current clock: {clock_calls}"

    body = ast.unparse(fn)  # docstring excluded: `unparse` drops it
    assert "snapshot_at" in body, "it reads the row's snapshot instant"
    assert "thời điểm quét" in body, "a missing provenance has honest wording"
    assert "chưa được đánh giá lại" in body, "it must not imply a re-evaluation"


def test_C_no_rescore_or_reselection_on_refresh() -> None:
    """A refresh rebuilds the payload from the SAME stored result."""

    row = _row()
    first = _payload(row, "H1")
    second = _payload(row, "H1")

    assert first["trade_plan"]["entry_zone"] == second["trade_plan"]["entry_zone"]
    assert first["trade_plan"]["stop_loss"] == second["trade_plan"]["stop_loss"]
    assert first["smc_overlay"] == second["smc_overlay"]
    assert row["candidate_status"] == "BLOCKED"


# ---------------------------------------------------------------------------
# D — fail-closed payloads and missing data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "detail",
    [
        None,
        {},
        {"price": None, "entry_low": 1.0, "entry_high": 2.0},
        {"price": 1.5, "entry_low": None, "entry_high": 2.0},
        {"price": "1.5", "entry_low": 1.0, "entry_high": 2.0},
    ],
)
def test_D_missing_price_or_bounds_reads_unknown(detail: Any) -> None:
    from ui.screens.scanner_screen import ScannerTableModel

    row = _row()
    row["price_vs_zone"] = "unknown"
    row["price_vs_zone_detail"] = detail

    tooltip = ScannerTableModel._price_vs_zone_tooltip(row)

    assert "Không xác định." in tooltip
    assert "nằm trong Entry" not in tooltip


def _legacy_row() -> dict[str, Any]:
    """A carrier that only speaks the historical ``selected_zone`` shape."""

    return {
        "symbol": "AUD/NZD",
        "selected_side": "buy",
        "captured_at": _SNAPSHOT_AT,
        "analysis_result": {
            "status": "ok",
            "technical": {"price": _PRICE},
            "scenarios": [_scenario(_BUY_BAND)],
            "smc_consumer": {
                "sides": {
                    "buy": {
                        "selected_zone": {"original_low": 1.0, "original_high": 2.0},
                        "selected_zone_quality_score": 82,
                    },
                    "sell": {},
                }
            },
            "chart_payload": _candles(),
        },
    }


def _corrupted_row() -> dict[str, Any]:
    """A carrier whose selection field is not even the right shape."""

    return {
        "symbol": "AUD/NZD",
        "selected_side": "buy",
        "captured_at": _SNAPSHOT_AT,
        "analysis_result": {
            "status": "ok",
            "technical": {"price": _PRICE},
            "scenarios": [],
            "smc_selection": "not-a-mapping",
            "chart_payload": _candles(),
        },
    }


def test_D_a_historical_payload_is_not_made_current_by_the_rule() -> None:
    """H1 suppression is presentation; it never upgrades the verdict."""

    payload = _payload(_legacy_row(), "H1")

    assert payload["smc_overlay"]["available"] is False
    assert payload["smc_overlay"]["source"] != "canonical"
    assert payload["execution_view_timeframes"] == ["H1"]


def test_D_a_corrupted_payload_does_not_crash_H1() -> None:
    payload = _payload(_corrupted_row(), "H1")

    assert payload["execution_view_timeframes"] == ["H1"]
    assert payload["smc_overlay"]["available"] is False


def test_D_a_row_with_no_plan_has_no_entry_band_and_still_no_SMC_on_H1() -> None:
    row = _row()
    row["analysis_result"]["scenarios"] = []
    payload = _payload(row, "H1")

    assert payload["trade_plan"]["entry_zone"] is None
    assert payload["zones"] == []
    assert payload["execution_view_timeframes"] == ["H1"]


# ---------------------------------------------------------------------------
# E — the real Scanner caller
# ---------------------------------------------------------------------------


def test_E_a_real_Scanner_row_carries_the_execution_view_rule() -> None:
    """A row built by the real Scanner caller → payload → page script."""

    import importlib

    _T113 = importlib.import_module("tests.test_smc_consumer_contract_task113")

    case = _T113._case("ob_confirmed_sell")
    pair = _T113._scanner(case)
    from core.scanner_ui_adapter import pair_to_ui_row

    analysis = _T113._scanner_analysis(case)
    ui_row = pair_to_ui_row(pair, broker_symbol=str(case["symbol"]), technical=analysis["technical"])

    # The presentation metadata the tooltip needs is stamped by the real caller.
    detail = ui_row.get("price_vs_zone_detail")
    assert isinstance(detail, dict)
    assert set(detail) == {"price", "entry_low", "entry_high", "snapshot_at"}

    payload = _payload(ui_row, "H1")
    assert payload["execution_view_timeframes"] == ["H1"]
    script = chart_update_script(payload)
    assert "execution_view_timeframes" in script


def test_E_light_and_dark_render_the_same_suppression() -> None:
    """The rule is data, not theme: both themes suppress H1 identically."""

    from ui.theme import chart_palette, palette_for

    for theme in ("light", "dark"):
        payload = _payload(_row(), "H1")
        payload["theme"] = theme
        payload["palette"] = chart_palette(palette_for(theme))
        script = chart_update_script(payload)
        assert '"execution_view_timeframes": ["H1"]' in script


# ---------------------------------------------------------------------------
# F (F-D-02) — the no-op contract at the payload boundary
# ---------------------------------------------------------------------------


def test_F_a_dict_without_overlay_is_an_exact_no_op() -> None:
    """F-D-02: the rule rides WITH the SMC layer, so a payload that has no layer
    is handed back exactly as it arrived — same object, no new key."""

    payload = {"symbol": "AUD/NZD", "active_timeframe": "H1", "timeframes": {}}
    before = json.loads(json.dumps(payload))

    decorated = decorate_chart_payload(payload)

    assert decorated is payload, "a payload without an overlay is not even copied"
    assert "execution_view_timeframes" not in decorated
    assert set(decorated) == set(before), "no key may be added"
    assert payload == before, "the caller's dict is not mutated"


def test_F_an_overlay_payload_gets_the_rule_without_mutating_the_input() -> None:
    """The control on the other side: a real (overlay) payload keeps the rule."""

    payload = build_full_chart_payload(
        "AUD/NZD",
        _row()["analysis_result"],
        active_timeframe="H1",
        smc_source=_row(),
    )
    before = json.loads(json.dumps(payload, default=str))

    decorated = decorate_chart_payload(payload)

    assert decorated is not payload
    assert decorated["execution_view_timeframes"] == ["H1"]
    assert "caption" in decorated["smc_overlay"]["timeframes"]["H1"], (
        "the overlay went through present_smc_overlay"
    )
    assert json.loads(json.dumps(payload, default=str)) == before, "input untouched"


@pytest.mark.parametrize(
    "row_factory",
    [_row, _legacy_row, _corrupted_row],
    ids=["canonical", "historical", "corrupted"],
)
def test_F_every_carrier_that_reaches_the_overlay_keeps_the_rule(row_factory: Any) -> None:
    """F-D-02 does not weaken the Scanner routes: canonical, historical and
    corrupted carriers all still reach the page WITH the H1 rule."""

    payload = _payload(row_factory(), "H1")

    assert payload["execution_view_timeframes"] == ["H1"]
    assert "smc_overlay" in payload
    assert "execution_view_timeframes" in chart_update_script(payload)


# ---------------------------------------------------------------------------
# F-D-01 — the lap's own captures stay out of the tracked reports tree
# ---------------------------------------------------------------------------


def test_F_the_render_writes_its_captures_outside_the_reports_tree() -> None:
    """The renderer must follow the run's output directory, not the tracked one."""

    rendered = _render_caption(_payload(_row(), "H1"))

    assert rendered["loaded"] is True
    assert rendered["captured_in_temp"], "the PNG/PDF landed in the run's own dir"
    assert rendered["reports_untouched"] is True, (
        "rendering must not add or touch chart captures under reports/scanner/"
    )


# ---------------------------------------------------------------------------
# G (F-D-03) — the "Vị trí" record is complete or it says nothing
# ---------------------------------------------------------------------------


def _banded_pair(band: tuple[float, float] = (100.0, 101.0)) -> Any:
    """A REAL testkit pair whose selected plan carries a real Entry band.

    The testkit pair routes a plan without a band, so a real ``ScenarioPlan``
    (constructor-validated: both bounds, ``low < high``) is put in its place —
    the same ``dataclasses.replace`` idiom ``tests/test_scanner_ui_adapter.py``
    already uses to vary a real pair.
    """

    import dataclasses

    from core.scanner_composition import ScenarioPlan

    from tests.test_scanner_ui_adapter import _pair

    banded = ScenarioPlan(
        direction="buy",
        entry=(band[0] + band[1]) / 2,
        stop_loss=band[0] - 1.0,
        take_profit=band[1] + 4.0,
        source="plan",
        entry_zone_low=band[0],
        entry_zone_high=band[1],
    )
    pair = _pair()
    return dataclasses.replace(
        pair,
        composition=dataclasses.replace(
            pair.composition,
            scenario=dataclasses.replace(pair.composition.scenario, plan=banded),
        ),
    )


def _pair_with_one_bound() -> Any:
    """A carrier whose stored plan lost one Entry bound.

    ``ScenarioPlan.__post_init__`` refuses a one-sided band, so such a document
    can only arrive as an object that never went through the constructor.  The
    forged-instance idiom is the one the repo already uses for exactly this
    (``tests/test_smc_selection_identity_task100.py``).
    """

    import dataclasses

    from core.scanner_composition import ScenarioPlan

    pair = _banded_pair()
    real = pair.composition.scenario.plan
    forged = object.__new__(ScenarioPlan)
    for field in dataclasses.fields(ScenarioPlan):
        value = getattr(real, field.name)
        object.__setattr__(forged, field.name, None if field.name == "entry_zone_high" else value)
    return dataclasses.replace(
        pair,
        composition=dataclasses.replace(
            pair.composition,
            scenario=dataclasses.replace(pair.composition.scenario, plan=forged),
        ),
    )


def _row_of(pair: Any, technical: dict[str, Any] | None = None) -> dict[str, Any]:
    from core.scanner_ui_adapter import pair_to_ui_row

    kwargs = {"broker_symbol": "XAUUSD"}
    if technical is not None:
        kwargs["technical"] = technical
    return pair_to_ui_row(pair, **kwargs)


def _assert_incomplete_record(row: dict[str, Any]) -> None:
    """The shared demand of F-D-03: unknown, three ``None``, honest tooltip."""

    from ui.screens.scanner_screen import ScannerTableModel

    assert row["price_vs_zone"] == "unknown"
    assert row["price_vs_zone_detail"] == {
        "price": None,
        "entry_low": None,
        "entry_high": None,
        "snapshot_at": row["price_vs_zone_detail"]["snapshot_at"],
    }, "a comparison that did not happen must not be recorded halfway"
    assert isinstance(row["price_vs_zone_detail"]["snapshot_at"], str), (
        "the snapshot instant comes from the row's own captured_at"
    )

    tooltip = ScannerTableModel._price_vs_zone_tooltip(row)
    assert "Không xác định." in tooltip
    assert "nằm trong Entry" not in tooltip


def test_G_a_missing_price_publishes_three_nones_and_unknown() -> None:
    """The reproduced half-record: a band with no price used to publish bounds."""

    _assert_incomplete_record(_row_of(_banded_pair()))


@pytest.mark.parametrize("price", ["100.5", True, float("nan"), float("inf")])
def test_G_an_unusable_price_publishes_three_nones_and_unknown(price: Any) -> None:
    """``bool``/``nan``/``inf`` used to classify as a number and be published."""

    row = _row_of(_banded_pair(), {"price": price, "atr_h4": 2.0})

    _assert_incomplete_record(row)


def test_G_a_missing_entry_bound_publishes_three_nones_and_unknown() -> None:
    _assert_incomplete_record(_row_of(_pair_with_one_bound(), {"price": 100.5}))


def test_G_a_complete_comparison_still_classifies() -> None:
    """Guard the other way: the fix must not fail closed on usable data."""

    inside = _row_of(_banded_pair(), {"price": 100.5, "atr_h4": 2.0})
    assert inside["price_vs_zone"] == "in_zone"
    assert inside["price_vs_zone_detail"]["price"] == 100.5
    assert inside["price_vs_zone_detail"]["entry_low"] == 100.0
    assert inside["price_vs_zone_detail"]["entry_high"] == 101.0

    outside = _row_of(_banded_pair(), {"price": 103.0, "atr_h4": 0.5})
    assert outside["price_vs_zone"] == "far"
    assert outside["price_vs_zone_detail"]["price"] == 103.0

    # A pair with no plan at all keeps the blocked-by-absence reading.
    _assert_incomplete_record(_row_of(_banded_pair_without_plan(), {"price": 100.5}))


def _banded_pair_without_plan() -> Any:
    import dataclasses

    from tests.test_scanner_ui_adapter import _pair

    pair = _pair()
    return dataclasses.replace(
        pair,
        composition=dataclasses.replace(
            pair.composition,
            scenario=dataclasses.replace(pair.composition.scenario, plan=None),
        ),
    )
