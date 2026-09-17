"""Lô A — publish the canonical ``protected_swing`` to consumer and Chart.

The canonical structure state has always carried a protected swing
(``protected_swing_id``/``_level``/``_kind`` plus ``protected_provenance`` with
the pivot and confirmation times).  Nothing carried it past the evaluator, so
every consumer reported ``SMC_PROTECTED_SWING_UNAVAILABLE`` on every snapshot.

This suite locks the two halves of the new behaviour with real callers:

* **positive** — when the canonical evidence really has a protected swing, the
  exact record (identity, level, kind, source event and times) reaches the
  selection and the chart overlay unchanged;
* **negative** — when it does not, or when the payload is historical, corrupted
  or forged, nothing is drawn and no level is substituted from a stop-loss, a
  technical level or a legacy zone.

The fixtures are the repo's own canonical cases; no synthetic structure state is
injected into the producer path.
"""

from __future__ import annotations

import gzip
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from core.chart_payload import SMC_PROTECTED_SWING_UNAVAILABLE, build_smc_overlay
from core.smc_consumer_contract import canonical_selection_of
from core.smc_models import protected_swing_record
from core.smc_scoring_result import SmcSideSelection, validate_smc_side_selection

_il = importlib

_T113 = importlib.import_module("tests.test_smc_consumer_contract_task113")
_R114 = importlib.import_module("tests.test_smc_analyze_scenario_r114")
_T117 = importlib.import_module("tests.test_smc_persistence_task117_120")

# The record fields the consumer publishes, in the order the canonical owner
# emits them.  Identity/provenance must survive verbatim.
_RECORD_FIELDS = (
    "protected_swing_id",
    "protected_swing_kind",
    "protected_swing_level",
    "protected_swing_pivot_time",
    "protected_swing_confirmed_at",
    "source_bos_id",
)


def _structure_state(pipeline: Any, timeframe: str) -> dict[str, Any]:
    """The canonical structure state the snapshot itself evaluated.

    Read from the frozen snapshot the evaluation ran on, so the "expected"
    record comes from the canonical owner rather than from the published copy
    the assertion is checking.
    """

    snapshot = pipeline._smc_evaluation.snapshot
    return snapshot.smc[timeframe]["structure_state"]


def _selection(result: dict[str, Any], side: str) -> dict[str, Any]:
    selection = canonical_selection_of(result, side)
    assert selection is not None, f"{side} has no canonical selection"
    return selection


def _layer(result: dict[str, Any], timeframe: str) -> dict[str, Any]:
    overlay = build_smc_overlay(result)
    assert overlay["available"], "overlay is not available for a current payload"
    return overlay["timeframes"][timeframe]


# ---------------------------------------------------------------------------
# The owner of the published shape
# ---------------------------------------------------------------------------


def test_the_record_keeps_identity_kind_level_and_provenance() -> None:
    state = {
        "protected_swing_id": "L1",
        "protected_swing_kind": "low",
        "protected_swing_level": 100.0,
        "protected_provenance": {
            "protected_swing_id": "L1",
            "source_bos_id": "BOS-1",
            "protected_swing_pivot_time": "2026-01-02T15:00:00+00:00",
            "protected_swing_confirmed_at": "2026-01-02T21:00:00+00:00",
        },
    }

    assert protected_swing_record(state) == {
        "protected_swing_id": "L1",
        "protected_swing_kind": "low",
        "protected_swing_level": 100.0,
        "protected_swing_pivot_time": "2026-01-02T15:00:00+00:00",
        "protected_swing_confirmed_at": "2026-01-02T21:00:00+00:00",
        "source_bos_id": "BOS-1",
    }


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"protected_swing_id": None, "protected_swing_level": 100.0},
        {"protected_swing_id": "L1", "protected_swing_kind": "low"},
        {"protected_swing_id": "L1", "protected_swing_kind": "low", "protected_swing_level": None},
        {"protected_swing_id": "L1", "protected_swing_kind": "sideways", "protected_swing_level": 1.0},
        {"protected_swing_id": "L1", "protected_swing_kind": "low", "protected_swing_level": 0.0},
        {"protected_swing_id": "L1", "protected_swing_kind": "low", "protected_swing_level": -5.0},
        {"protected_swing_id": "L1", "protected_swing_kind": "low", "protected_swing_level": float("nan")},
        {"protected_swing_id": "L1", "protected_swing_kind": "low", "protected_swing_level": "abc"},
        {"protected_swing_id": "   ", "protected_swing_kind": "low", "protected_swing_level": 1.0},
    ],
)
def test_a_state_without_a_usable_swing_stays_unavailable(state: dict[str, Any]) -> None:
    """No id, no level, an unknown kind or a non-finite level is NOT a record."""

    assert protected_swing_record(state) is None


def test_provenance_of_another_swing_is_never_republished() -> None:
    """A provenance naming a different swing lends the record nothing.

    The level alone is not evidence: the source event and the times belong to
    the swing they name, so a mismatch makes the whole record unpublished rather
    than a level with invented or borrowed history.
    """

    assert (
        protected_swing_record(
            {
                "protected_swing_id": "L1",
                "protected_swing_kind": "low",
                "protected_swing_level": 100.0,
                "protected_provenance": {
                    "protected_swing_id": "H9",
                    "source_bos_id": "BOS-9",
                    "protected_swing_pivot_time": "2026-01-02T15:00:00+00:00",
                    "protected_swing_confirmed_at": "2026-01-02T21:00:00+00:00",
                },
            }
        )
        is None
    )


@pytest.mark.parametrize(
    "provenance",
    [
        {},  # no provenance at all
        {"protected_swing_id": "L1"},  # names the swing but no source event
        {
            "protected_swing_id": "L1",
            "source_bos_id": "BOS-1",
            "protected_swing_pivot_time": "2026-01-02T15:00:00+00:00",
        },  # no confirmation time
        {
            "protected_swing_id": "L1",
            "source_bos_id": "BOS-1",
            "protected_swing_confirmed_at": "2026-01-02T21:00:00+00:00",
        },  # no pivot time
        {"protected_swing_id": "L1", "source_bos_id": "  ", "protected_swing_pivot_time": "t", "protected_swing_confirmed_at": "t"},
    ],
)
def test_an_incomplete_provenance_keeps_the_record_unavailable(
    provenance: dict[str, Any],
) -> None:
    """No source event or no times means no line: the level is not published."""

    assert (
        protected_swing_record(
            {
                "protected_swing_id": "L1",
                "protected_swing_kind": "low",
                "protected_swing_level": 100.0,
                "protected_provenance": provenance,
                # Present but deliberately NOT usable as a substitute source.
                "protected_updated_at": "2026-01-02T22:00:00+00:00",
            }
        )
        is None
    )


# ---------------------------------------------------------------------------
# Positive: the real callers publish the record unchanged
# ---------------------------------------------------------------------------


def test_the_analyze_caller_publishes_the_canonical_protected_swing() -> None:
    """Every published field equals what the canonical state itself recorded."""

    result, pipeline = _R114._analyze()
    selection = _selection(result, "buy")
    published = selection["protected_swing"]
    expected = protected_swing_record(
        _structure_state(pipeline, selection["timeframe"])
    )

    assert expected is not None, "the fixture must really carry a protected swing"
    assert published == expected
    assert set(published) == set(_RECORD_FIELDS)
    # Identity is the canonical swing, not a fresh one built for display.
    assert published["protected_swing_id"].startswith("smcs-")
    assert published["source_bos_id"].startswith("smc-bos-")


def test_the_scanner_caller_publishes_the_same_record_as_analyze() -> None:
    """Both live routes read the SAME canonical record for the same snapshot."""

    from core.smc_scoring_result import smc_selection_of

    case = _T113._case("ob_confirmed_sell")
    scanner = _T113._scanner_analysis(case)
    _analyze_result, pipeline = _T113._analyze(case)

    seen = 0
    for side in ("buy", "sell"):
        left = smc_selection_of(scanner["canonical_smc"].side(side))
        right = smc_selection_of(pipeline._smc_evaluation.result.side(side))
        assert left is not None and right is not None
        assert left.protected_swing == right.protected_swing
        seen += 1 if left.protected_swing is not None else 0

    assert seen, "the fixture must publish a record on at least one route/side"


def test_the_chart_overlay_draws_the_canonical_level_for_its_timeframe() -> None:
    result, _pipeline = _R114._analyze()
    selection = _selection(result, "buy")
    layer = _layer(result, selection["timeframe"])

    assert layer["protected_swing"] is not None
    assert layer["protected_swing"]["level"] == selection["protected_swing"][
        "protected_swing_level"
    ]
    assert layer["protected_swing"]["id"] == selection["protected_swing"][
        "protected_swing_id"
    ]
    assert SMC_PROTECTED_SWING_UNAVAILABLE not in layer["reason_codes"]


def test_the_drawn_level_is_not_the_plan_stop_loss() -> None:
    """The chart must never gain a level by substituting the plan's risk."""

    result, _pipeline = _R114._analyze()
    selection = _selection(result, "buy")
    plan = selection["plan"]
    assert plan is not None and plan.get("stop_loss") is not None

    drawn = _layer(result, selection["timeframe"])["protected_swing"]["level"]

    assert drawn == selection["protected_swing"]["protected_swing_level"]
    assert drawn != plan["stop_loss"]
    assert drawn != selection["zone_low"]
    assert drawn != selection["zone_high"]


def test_the_decorated_chart_payload_labels_the_swing() -> None:
    """The UI label is attached by the presentation layer, not by the producer."""

    from ui.chart_bridge import decorate_chart_payload
    from core.chart_payload import build_full_chart_payload

    result, _pipeline = _R114._analyze()
    selection = _selection(result, "buy")
    payload = build_full_chart_payload(
        "XAUUSD", result, active_timeframe=selection["timeframe"]
    )
    decorated = decorate_chart_payload(payload)
    layer = decorated["smc_overlay"]["timeframes"][selection["timeframe"]]

    assert layer["protected_swing"]["label"] == "Đỉnh/đáy bảo vệ"
    assert layer["protected_swing"]["level"] == selection["protected_swing"][
        "protected_swing_level"
    ]


def test_replay_of_the_same_cutoff_publishes_the_same_record() -> None:
    """A second evaluation of the same frozen snapshot yields the same record."""

    result, _pipeline = _R114._analyze()
    again, _pipeline2 = _R114._analyze()

    for side in ("buy", "sell"):
        assert (
            _selection(result, side).get("protected_swing")
            == _selection(again, side).get("protected_swing")
        )


# ---------------------------------------------------------------------------
# Negative: nothing is drawn, and nothing stands in for the missing level
# ---------------------------------------------------------------------------


def test_a_side_without_canonical_evidence_publishes_no_swing() -> None:
    """``ob_confirmed_sell`` BUY has no core evidence — so no level either."""

    result, _pipeline = _T113._analyze(_T113._case("ob_confirmed_sell"))
    selection = _selection(result, "buy")

    assert selection["state"] == "data_unavailable"
    assert selection["protected_swing"] is None


@pytest.mark.parametrize("name", ["fvg_confirmed_buy", "sell_setup", "no_zone", "broken_invalid"])
def test_a_case_without_a_canonical_swing_reports_the_unavailable_code(name: str) -> None:
    """Where a zone IS drawn but no swing exists, the absence is stated."""

    result, _pipeline = _T113._analyze(_T113._case(name))
    overlay = build_smc_overlay(result)
    drawn = [layer for layer in (overlay.get("timeframes") or {}).values() if layer.get("zones")]

    for layer in drawn:
        assert layer["protected_swing"] is None
        assert SMC_PROTECTED_SWING_UNAVAILABLE in layer["reason_codes"]


def test_a_historical_payload_draws_no_level() -> None:
    """A stored pre-canonical document is never presented as a current verdict."""

    historical = {
        "smc_consumer": {
            "sides": {
                "buy": {
                    "selected_zone": {"original_low": 1.0, "original_high": 2.0},
                    "selected_zone_quality_score": 82,
                },
                "sell": {},
            }
        }
    }
    overlay = build_smc_overlay({"analysis_result": historical})

    assert overlay["available"] is False
    assert overlay["timeframes"] == {}
    assert all(
        layer.get("protected_swing") is None
        for layer in (overlay.get("timeframes") or {}).values()
    )


def test_a_forged_selection_cannot_publish_a_swing_on_a_no_zone_side() -> None:
    """A side that certified no zone has no zone whose timeframe it could name."""

    with pytest.raises(ValueError, match="cannot publish a protected swing"):
        SmcSideSelection(
            side="buy",
            state="no_zone",
            quality_raw=0,
            protected_swing={
                "protected_swing_id": "L1",
                "protected_swing_kind": "low",
                "protected_swing_level": 100.0,
            },
        )


def _real_selection_payload() -> dict[str, Any]:
    """A genuine evaluated selection, used to store a tampered record in."""

    result, _pipeline = _R114._analyze()
    payload = dict(_selection(result, "buy"))
    assert payload["protected_swing"] is not None
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        {},  # no id
        {"protected_swing_id": "L1"},  # no kind
        {"protected_swing_id": "L1", "protected_swing_kind": "up", "protected_swing_level": 1.0},
        {"protected_swing_id": "L1", "protected_swing_kind": "low", "protected_swing_level": 0.0},
        {"protected_swing_id": "L1", "protected_swing_kind": "low", "protected_swing_level": float("inf")},
        {"protected_swing_id": "L1", "protected_swing_kind": "low", "protected_swing_level": float("nan")},
        {
            "protected_swing_id": "L1",
            "protected_swing_kind": "low",
            "protected_swing_level": 1.0,
            "source_bos_id": 17,
        },
        # A level with no source event or no times is not a publishable record.
        {"protected_swing_id": "L1", "protected_swing_kind": "low", "protected_swing_level": 1.0},
        {
            "protected_swing_id": "L1",
            "protected_swing_kind": "low",
            "protected_swing_level": 1.0,
            "source_bos_id": "BOS-1",
        },
    ],
)
def test_a_stored_record_the_owner_could_not_have_published_is_refused(
    payload: dict[str, Any],
) -> None:
    """A present-but-invalid record is refused, not republished as usable."""

    stored = _real_selection_payload()
    stored["protected_swing"] = payload

    with pytest.raises(ValueError):
        SmcSideSelection.from_dict(stored)


def test_a_non_mapping_stored_record_is_treated_as_absent() -> None:
    """A mistyped field is absence, exactly as the confirmation contract treats it.

    The canonical owner publishes a mapping or nothing, so bytes that carry
    something else are read as "no record" and the overlay states the absence
    rather than raising a level out of a malformed field.
    """

    stored = _real_selection_payload()
    stored["protected_swing"] = "not-a-mapping"
    restored = SmcSideSelection.from_dict(stored)

    assert restored.protected_swing is None
    assert validate_smc_side_selection(restored) is True


def test_a_well_formed_record_survives_the_round_trip() -> None:
    """A well-formed record passes the same re-check a reader applies."""

    stored = _real_selection_payload()
    restored = SmcSideSelection.from_dict(stored)

    assert restored.protected_swing == stored["protected_swing"]
    assert validate_smc_side_selection(restored) is True
    assert restored.to_dict()["protected_swing"] == stored["protected_swing"]


def test_the_record_is_read_only_but_copied_not_aliased() -> None:
    """Serialising never mutates the record the canonical owner produced."""

    result, _pipeline = _R114._analyze()
    selection = _selection(result, "buy")
    before = dict(selection["protected_swing"])

    SmcSideSelection.from_dict(selection).to_dict()

    assert selection["protected_swing"] == before


def test_the_carrier_the_chart_reads_carries_the_record() -> None:
    """The composition summary IS the carrier — the record must survive into it.

    The chart and the UI panels do not read the consumer contract directly: they
    read ``analysis_result.smc_selection``, the per-side summary
    ``core.scanner_composition._smc_selection_summary`` projects.  A record that
    reached only the consumer contract would therefore still be invisible on the
    chart, so this locks the projection too.
    """

    from core.scanner_composition import _smc_selection_summary
    from core.smc_consumer_contract import build_smc_consumer_from_canonical_result
    from core.smc_persistence import build_smc_persistence_block
    from core.smc_scoring_result import smc_selection_of

    _analyze_result, pipeline = _R114._analyze()
    canonical = pipeline._smc_evaluation.result

    for side in ("buy", "sell"):
        selection = smc_selection_of(canonical.side(side))
        summary = _smc_selection_summary(canonical, side)
        assert selection is not None and summary is not None
        assert summary["protected_swing"] == selection.protected_swing

    # ... and the chart really draws it from that carrier.  The read boundary
    # refuses a carrier that carries the summary without the canonical block
    # beside it, so the carrier is built through the production producers.
    carrier = {
        "analysis_result": {
            "smc_selection": {
                side: _smc_selection_summary(canonical, side) for side in ("buy", "sell")
            },
            "smc_scoring": build_smc_persistence_block(
                canonical,
                build_smc_consumer_from_canonical_result(result=canonical),
                snapshot=pipeline._smc_snapshot,
            ),
        }
    }
    selection = _selection(carrier, "buy")
    layer = _layer(carrier, selection["timeframe"])
    assert layer["protected_swing"]["id"] == selection["protected_swing"][
        "protected_swing_id"
    ]
    assert SMC_PROTECTED_SWING_UNAVAILABLE not in layer["reason_codes"]


def test_the_scanner_composition_publishes_the_record_on_the_live_route() -> None:
    """A real Scanner caller reaches the carrier with the record intact."""

    from core.scanner_composition import _smc_selection_summary

    case = _T113._case("ob_confirmed_sell")
    scanner = _T113._scanner_analysis(case)
    canonical = scanner["canonical_smc"]

    published = [
        _smc_selection_summary(canonical, side)["protected_swing"]
        for side in ("buy", "sell")
        if _smc_selection_summary(canonical, side) is not None
    ]
    assert any(record is not None for record in published), (
        "the live Scanner route must publish the record for at least one side"
    )


# ---------------------------------------------------------------------------
# Persistence and restart
# ---------------------------------------------------------------------------


def test_a_stored_document_republishes_the_same_record_after_a_restart(
    tmp_path: Path,
) -> None:
    """A NEW service instance reads the same protected swing off the disk bytes."""

    from services.scanner_persistence_service import ScannerPersistenceService

    result, _pipeline = _R114._analyze()
    live = _selection(result, "buy")["protected_swing"]
    assert live is not None

    _T117._persist(tmp_path, "XAUUSD", result, selected_side="buy")
    restarted = ScannerPersistenceService(tmp_path)
    loaded = restarted.load_analysis(_T117._SCAN_ID, "XAUUSD")

    stored = _selection(loaded, "buy")["protected_swing"]
    assert stored == live
    assert _layer(loaded, _selection(loaded, "buy")["timeframe"])["protected_swing"][
        "level"
    ] == live["protected_swing_level"]


def test_a_restart_never_invents_a_record_for_a_side_that_had_none(tmp_path: Path) -> None:
    """The zero/null distinction survives: no evidence stays no record."""

    from services.scanner_persistence_service import ScannerPersistenceService

    result, _pipeline = _T113._analyze(_T113._case("ob_confirmed_sell"))
    _T117._persist(tmp_path, "EUR/USD", result, selected_side="buy")
    restarted = ScannerPersistenceService(tmp_path)
    loaded = restarted.load_analysis(_T117._SCAN_ID, "EUR/USD")

    assert _selection(loaded, "buy")["protected_swing"] is None
    assert _selection(loaded, "sell")["protected_swing"] is not None


# ---------------------------------------------------------------------------
# F-LA-01 — the carrier cannot replace what the block certified
#
# These go through the bytes on disk and a NEW service instance, so what is
# checked is the payload the application actually reads back, not a fixture
# assembled in memory.
# ---------------------------------------------------------------------------


# ``ob_confirmed_sell`` carries its canonical protected swing on the SELL side
# (the BUY side has no core evidence at all, so it publishes no record either).
_CARRIER_SIDE = "sell"


def _stored_carrier(tmp_path: Path) -> dict[str, Any]:
    """Persist a real SCANNER payload and read it back through a new instance.

    A Scanner document carries BOTH carriers under ``analysis_result`` — the
    per-side summary the UI adapter writes into ``smc_selection`` and the block
    the controller attaches at ``smc_scoring`` — which is exactly the pair of
    sources F-LA-01 is about.  The tampering below edits only the summary bytes.
    """



    from core.scanner_ui_adapter import pair_to_ui_row
    from core.smc_consumer_contract import build_smc_consumer_from_canonical_result
    from core.smc_persistence import build_smc_persistence_block
    from services.scanner_persistence_service import (
        ScannerPersistenceService,
        analysis_document_path,
        atomic_json_save,
    )

    case = _T113._case("ob_confirmed_sell")
    symbol = str(case["symbol"])
    pair = _T113._scanner(case)
    analysis = _T113._scanner_analysis(case)

    ui_row = pair_to_ui_row(
        pair,
        broker_symbol=symbol,
        scan_id=_T117._SCAN_ID,
        row_id=f"{_T117._SCAN_ID}:{symbol}",
        settings_hash="a" * 64,
        technical=analysis["technical"],
    )

    # The same canonical evaluation the Scanner block is built from on the live
    # route (``controllers/scanner_controller.py``), attached beside the summary
    # the UI adapter wrote.
    canonical = analysis["canonical_smc"]
    analysis_result = ui_row["analysis_result"]
    analysis_result["smc_scoring"] = build_smc_persistence_block(
        canonical,
        build_smc_consumer_from_canonical_result(result=canonical),
        snapshot=analysis["smc_snapshot"],
    )
    assert isinstance(analysis_result.get("smc_selection"), dict), (
        "the real Scanner carrier must carry the per-side summary"
    )

    document = _T117._document(symbol, analysis_result, selected_side=_CARRIER_SIDE)
    # Written through the production writer to the production path, so the bytes
    # on disk are the ones the application really reads back.
    atomic_json_save(
        analysis_document_path(tmp_path, _T117._SCAN_ID, symbol),
        document,
        indent=None,
    )

    restarted = ScannerPersistenceService(tmp_path)
    return restarted.load_analysis(_T117._SCAN_ID, symbol)


def _edit(loaded: dict[str, Any], mutate) -> None:
    """Rewrite ONE field of the stored summary inside the loaded document."""

    carrier = loaded["analysis_result"]["smc_selection"][_CARRIER_SIDE]
    mutate(carrier["protected_swing"])


def _certified(loaded: dict[str, Any]) -> dict[str, Any] | None:
    return (
        loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
            _CARRIER_SIDE
        ]["selection"]["protected_swing"]
    )


def _drawn(loaded: dict[str, Any]) -> Any:
    """The level the chart would draw for the carrier side, if any."""

    selection = canonical_selection_of(loaded, _CARRIER_SIDE)
    if selection is None:
        return None
    timeframe = selection.get("timeframe")
    layer = (build_smc_overlay(loaded).get("timeframes") or {}).get(timeframe)
    swing = (layer or {}).get("protected_swing")
    return swing["level"] if swing else None


def test_the_untouched_stored_carrier_still_draws_the_certified_level(
    tmp_path: Path,
) -> None:
    """Control: reading the bytes back changes nothing."""

    loaded = _stored_carrier(tmp_path)
    certified = _certified(loaded)
    assert certified is not None

    assert _drawn(loaded) == certified["protected_swing_level"]
    assert canonical_selection_of(loaded, _CARRIER_SIDE)["protected_swing"] == certified


def test_a_stored_carrier_cannot_raise_the_level(tmp_path: Path) -> None:
    """F-LA-01 reproducer: a mutated level is never drawn, and never current."""

    from core.smc_consumer_contract import SMC_READ_PROTECTED_SWING_MISMATCH

    loaded = _stored_carrier(tmp_path)
    certified = _certified(loaded)
    assert certified is not None and certified["protected_swing_level"] != 999.0

    _edit(loaded, lambda swing: swing.__setitem__("protected_swing_level", 999.0))

    assert _drawn(loaded) is None
    selection = canonical_selection_of(loaded, _CARRIER_SIDE)
    assert selection is not None, "the rest of the selection stays readable"
    assert selection["protected_swing"] is None
    assert SMC_READ_PROTECTED_SWING_MISMATCH in _read(loaded).reason_codes


def test_a_stored_carrier_cannot_substitute_identity_source_or_time(
    tmp_path: Path,
) -> None:
    """A record pointing at another swing is withheld, not drawn."""

    loaded = _stored_carrier(tmp_path)
    certified = _certified(loaded)
    assert certified is not None

    def forge(swing: dict[str, Any]) -> None:
        swing["protected_swing_id"] = "smcs-FORGED"
        swing["source_bos_id"] = "smc-bos-FORGED"
        swing["protected_swing_pivot_time"] = "1999-01-01T00:00:00+00:00"
        swing["protected_swing_confirmed_at"] = "1999-01-01T04:00:00+00:00"

    _edit(loaded, forge)

    assert _drawn(loaded) is None
    assert canonical_selection_of(loaded, _CARRIER_SIDE)["protected_swing"] is None


def test_a_stored_carrier_cannot_swap_the_level_for_a_valid_looking_other_one(
    tmp_path: Path,
) -> None:
    """A DIFFERENT but individually well-formed level is still not the certified one."""

    loaded = _stored_carrier(tmp_path)
    certified = _certified(loaded)
    assert certified is not None
    other = round(float(certified["protected_swing_level"]) + 1.0, 6)

    _edit(loaded, lambda swing: swing.__setitem__("protected_swing_level", other))

    assert _drawn(loaded) is None
    assert _drawn(loaded) != other


def test_a_stored_carrier_cannot_inject_a_record_the_block_never_certified(
    tmp_path: Path,
) -> None:
    """The block certified NO swing: an injected one is withheld."""

    loaded = _stored_carrier(tmp_path)
    assert _certified(loaded) is not None

    # Take the certification away, then inject a record into the summary.
    loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        _CARRIER_SIDE
    ]["selection"]["protected_swing"] = None
    carrier = loaded["analysis_result"]["smc_selection"][_CARRIER_SIDE]
    carrier["protected_swing"] = {
        "protected_swing_id": "smcs-INJECTED",
        "protected_swing_kind": "high",
        "protected_swing_level": 4242.0,
        "protected_swing_pivot_time": "1999-01-01T00:00:00+00:00",
        "protected_swing_confirmed_at": "1999-01-01T04:00:00+00:00",
        "source_bos_id": "smc-bos-INJECTED",
    }

    assert _drawn(loaded) is None
    assert canonical_selection_of(loaded, _CARRIER_SIDE)["protected_swing"] is None


def test_a_carrier_that_omits_the_field_is_bound_to_the_certified_record(
    tmp_path: Path,
) -> None:
    """A foreshortened summary is filled from the certification, not left blank."""

    loaded = _stored_carrier(tmp_path)
    certified = _certified(loaded)
    assert certified is not None

    del loaded["analysis_result"]["smc_selection"][_CARRIER_SIDE]["protected_swing"]

    assert canonical_selection_of(loaded, _CARRIER_SIDE)["protected_swing"] == certified
    assert _drawn(loaded) == certified["protected_swing_level"]


def test_a_withheld_field_says_so_on_every_surface(tmp_path: Path) -> None:
    """Tooltip, detail panel and chart all state the same absence."""

    from ui.scanner_presentation import present_smc_row, smc_reason_text

    loaded = _stored_carrier(tmp_path)
    _edit(loaded, lambda swing: swing.__setitem__("protected_swing_level", 999.0))

    overlay = build_smc_overlay(loaded)
    selection = canonical_selection_of(loaded, _CARRIER_SIDE)
    layer = overlay["timeframes"][selection["timeframe"]]

    assert layer["protected_swing"] is None
    assert SMC_PROTECTED_SWING_UNAVAILABLE in layer["reason_codes"]

    read = _read(loaded)
    assert "SMC_READ_PROTECTED_SWING_MISMATCH" in read.reason_codes
    # The raw code never reaches the user.
    assert (
        smc_reason_text("SMC_READ_PROTECTED_SWING_MISMATCH")
        != "SMC_READ_PROTECTED_SWING_MISMATCH"
    )
    # The UI row presents the canonical selection, without a protected level.
    view = present_smc_row(loaded)
    assert view.available
    assert build_smc_overlay(loaded)["reason_codes"].count(
        "SMC_READ_PROTECTED_SWING_MISMATCH"
    ) == 1


def test_the_certified_record_is_the_one_published_on_the_whole_corpus() -> None:
    """Control on real data: every layer still publishes the certified record.

    This is the anti-regression for the bind itself — binding must be a no-op
    when the summary and the block agree, which is what the live route produces.
    """

    import gzip


    qa = _il.import_module("scripts.smc_chart_qa")
    corpus = (
        Path(__file__).resolve().parents[1]
        / "reports"
        / "scanner"
        / "smc_real_snapshots"
        / "corpus.jsonl.gz"
    )
    if not corpus.exists():  # pragma: no cover - artifact is not tracked by git
        pytest.skip("real-snapshot corpus is not present in this checkout")

    with gzip.open(corpus, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]

    published = 0
    for row in rows:
        analysis = qa._analysis(row)
        canonical = analysis["canonical_smc"]
        carrier = qa._carrier(canonical, analysis["smc_snapshot"])

        records = {}
        for side in ("buy", "sell"):
            selection = canonical_selection_of(carrier, side)
            if selection is None:
                continue
            record = selection.get("protected_swing")
            if record is not None:
                records[selection.get("timeframe")] = record

        for timeframe, layer in (build_smc_overlay(carrier).get("timeframes") or {}).items():
            swing = layer.get("protected_swing")
            if swing is None:
                continue
            published += 1
            record = records.get(timeframe)
            assert record is not None, "a drawn layer must have a certified record"
            assert swing["level"] == record["protected_swing_level"]
            assert swing["id"] == record["protected_swing_id"]
            assert swing["source_bos_id"] == record["source_bos_id"]

    assert published == 77, f"the corpus control must keep all 77 layers, got {published}"


def _read(loaded: dict[str, Any]):
    from core.smc_consumer_contract import read_canonical_selection

    return read_canonical_selection(loaded, _CARRIER_SIDE)
