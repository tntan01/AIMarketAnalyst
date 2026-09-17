"""Tasks 117–120 — canonical persistence, cache/config compatibility, readers.

Every case below runs the REAL producers and the REAL persistence service on a
temporary runtime root; no evaluator, coordinator, planner or reader is mocked
and no expected value is copied out of the code under test.

The oracles are independent of the persistence path:

* the live canonical result of the same snapshot
  (``pipeline._smc_evaluation.result``) — the stored payload must agree with it;
* the contract's own validator (``SmcSideSelection.from_dict``) — a stored
  selection is re-checked against the invariant the finalizer enforces;
* the published version constants (``SMC_SELECTION_VERSION`` …) — the identity
  the payload carries must be built from those, not from a literal.

Covered here (compatibility spec §3, §4.1 and §5):

* 117 — a canonical result survives save/load byte for byte, keeping raw vs
  null, reasons, source and identity;
* 118 — the cache/config identity now covers the selection policy, so an
  artifact certified before it is not self-valid;
* 119 — a historical document is read with its own meaning and never rewritten
  into the canonical contract, and no canonical provenance is fabricated;
* 120 — old/new payloads, cache hit/miss/incompatible/corrupted and restart.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from core.market_models import Candle
from core.smc_models import M15Confirmation
from core.scanner_observability import (
    build_analysis_document,
    create_scan_context,
)
from core.scoring_provenance import (
    build_scoring_provenance,
    normalize_scoring_provenance,
)
from core.smc_persistence import (
    SMC_PAYLOAD_CANONICAL,
    SMC_PAYLOAD_CORRUPTED,
    SMC_PAYLOAD_HISTORICAL,
    SMC_PAYLOAD_INCOMPATIBLE,
    SMC_PERSISTENCE_BLOCK_MALFORMED,
    SMC_PERSISTENCE_BLOCK_MISSING,
    SMC_PERSISTENCE_CONFIRMATION_IDENTITY_MISMATCH,
    SMC_PERSISTENCE_CONTRACT_MISSING,
    SMC_PERSISTENCE_CONTRACT_UNSUPPORTED,
    SMC_PERSISTENCE_IDENTITY_KEY,
    SMC_PERSISTENCE_IDENTITY_DIGEST_MISMATCH,
    SMC_PERSISTENCE_IDENTITY_MISMATCH,
    SMC_PERSISTENCE_IDENTITY_MISSING,
    SMC_PERSISTENCE_SELECTION_MALFORMED,
    SMC_PERSISTENCE_SELECTION_MISSING,
    SMC_PERSISTENCE_SNAPSHOT_KEY,
    SMC_SOURCE_CANONICAL_SELECTION,
    SMC_SOURCE_LEGACY_SELECTED_ZONE,
    classify_persisted_smc,
    smc_persistence_identity,
)
from core.smc_scoring_result import SmcSideSelection, smc_selection_of
from core.smc_snapshot_cache import (
    SMC_CACHE_IDENTITY_VERSION,
    SMC_RULE_IDENTITY,
    smc_rule_identity,
    smc_rule_identity_digest,
    smc_rule_versions,
)
from core.smc_result_cache import (
    SMC_CACHE_MISS_ABSENT,
    SMC_CACHE_MISS_IDENTITY_MISMATCH,
    SMC_CACHE_MISS_RECORD_CORRUPTED,
    SMC_CACHE_MISS_RECORD_INVALID,
    SMC_CACHE_MISS_SNAPSHOT_MISMATCH,
    SMC_RESULT_CACHE_IDENTITY_KEY,
)
from core.smc_validation import replay_sample_from_analysis_document
from core.smc_versions import SMC_SELECTION_VERSION
from services.scanner_persistence_service import (
    ScannerPersistenceService,
    analysis_document_path,
    atomic_json_save,
    load_json_document,
)

_T113 = importlib.import_module("tests.test_smc_consumer_contract_task113")
_R114 = importlib.import_module("tests.test_smc_analyze_scenario_r114")

_SIDES = ("buy", "sell")
_SCAN_ID = "20260916T120000.000000Z-persist00001"


# ---------------------------------------------------------------------------
# Real producers on a temporary runtime root
# ---------------------------------------------------------------------------


def _evaluated_analysis() -> tuple[dict[str, Any], Any, str]:
    """A real canonical evaluation whose BUY side is ``evaluated`` with a plan.

    ``min_rr`` is a certified owner policy here; without it the coordinator
    accepts no plan and every side stays ``watch_zone``.
    """

    result, pipeline = _R114._analyze()
    return result, pipeline, "XAUUSD"


def _case_analysis(case: dict[str, Any]) -> tuple[dict[str, Any], Any, str]:
    """Run the real Analyze caller for one consumer-contract case."""

    result, pipeline = _T113._analyze(case)
    return result, pipeline, str(case["symbol"])


def _no_zone_analysis() -> tuple[dict[str, Any], Any, str]:
    return _case_analysis(_T113._case("no_zone"))


def _data_unavailable_analysis() -> tuple[dict[str, Any], Any, str]:
    """``ob_confirmed_sell``: the BUY side has no core evidence at all."""

    return _case_analysis(_T113._case("ob_confirmed_sell"))


def _persist(
    root: Path,
    symbol: str,
    result: dict[str, Any],
    *,
    selected_side: str | None = None,
) -> Path:
    """Write one analysis document the way the scan call site writes it."""

    path = analysis_document_path(root, _SCAN_ID, symbol)
    atomic_json_save(path, _document(symbol, result, selected_side=selected_side), indent=None)
    return path


def _document(
    symbol: str,
    result: dict[str, Any],
    *,
    selected_side: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "symbol": symbol,
        "row_id": f"{_SCAN_ID}:{symbol}",
        "analysis_result": result,
    }
    if selected_side is not None:
        # A real Scanner row records the side the candidate engine chose; without
        # it a reader can only fall back to comparing scores, which is a tie.
        row["selected_side"] = selected_side
    return build_analysis_document(
        row,
        {
            "scan_id": _SCAN_ID,
            "started_at": "2026-09-16T12:00:00+00:00",
            "settings_hash": "a" * 64,
        },
    )


def _stored(
    tmp_path: Path,
    analysis: tuple[dict[str, Any], Any, str],
    *,
    selected_side: str | None = None,
) -> tuple[ScannerPersistenceService, dict[str, Any]]:
    """Persist and re-open one analysis through a NEW service instance.

    The second instance is the "restart": nothing from the writing process is
    carried over except the bytes on disk.
    """

    result, _pipeline, symbol = analysis
    _persist(tmp_path, symbol, result, selected_side=selected_side)
    service = ScannerPersistenceService(tmp_path)
    return service, service.load_analysis(_SCAN_ID, symbol)


def _selection_of(pipeline, side: str) -> SmcSideSelection:
    return smc_selection_of(pipeline._smc_evaluation.result.side(side))


# The M15 window decides the typed confirmation, so the two cases below differ
# only in the candles that follow the entry trigger: holding near the band keeps
# the trigger alive, running away from it invalidates the entry.  Everything
# else — candles, cutoff, policy — is the shared positive fixture.
_M15_AS_OF = datetime(2026, 8, 13, 11, 0, tzinfo=timezone.utc)
_M15_CALM = [(1008.0, 1008.3, 1007.8, 1008.1)] * 20
_M15_ENTRY = [
    (1008.0, 1008.2, 1006.0, 1006.4),
    (1006.3, 1006.5, 1004.0, 1004.2),
    (1004.1, 1004.3, 1002.9, 1005.6),
]


def _m15_window(tail: list[tuple[float, float, float, float]]) -> tuple[Candle, ...]:
    rows = _M15_CALM + _M15_ENTRY + tail
    start = _M15_AS_OF - timedelta(minutes=15 * (len(rows) - 1))
    return tuple(
        Candle(
            time=start + timedelta(minutes=15 * index),
            open=row[0],
            high=row[1],
            low=row[2],
            close=row[3],
        )
        for index, row in enumerate(rows)
    )


def _m15_analysis(tail) -> tuple[dict[str, Any], Any, str]:
    """Run the REAL Analyze caller with an M15 window that confirms or invalidates."""

    result, pipeline = _R114._analyze(
        m15_candles=_m15_window(tail), m15_as_of=_M15_AS_OF
    )
    return result, pipeline, "XAUUSD"


def _confirmed_analysis():
    return _m15_analysis([(1005.0, 1005.4, 1004.3, 1004.9)] * 8)


def _invalidated_analysis():
    return _m15_analysis([(1005.6, 1006.6, 1005.4, 1006.4)] * 8)


_CONFIRMATION_FIELDS = (
    "zone_id",
    "side",
    "status",
    "entry_visit_id",
    "visit_ordinal",
    "visit_anchor_at",
    "bars_since_anchor",
    "trigger_event_id",
    "trigger_kind",
    "trigger_at",
    "confirmation_id",
    "confirmed_at",
    "expires_at",
    "invalidated_at",
    "invalidation_reason",
    "parent_lifecycle_visit_id",
    "zone_low",
    "zone_high",
    "reason_codes",
)


# ---------------------------------------------------------------------------
# 117 — persistence round trip
# ---------------------------------------------------------------------------


def test_a_real_evaluation_round_trips_through_the_persistence_service(tmp_path):
    """What the scan call site wrote is exactly what a restart reads back."""

    result, _pipeline, symbol = _evaluated_analysis()
    path = _persist(tmp_path, symbol, result)

    service = ScannerPersistenceService(tmp_path)
    assert service.analysis_path(_SCAN_ID, symbol) == path
    loaded = service.load_analysis(_SCAN_ID, symbol)

    assert loaded == _document(symbol, result)
    # The document really is the gzip JSON artifact on disk, not a shortcut.
    assert path.suffix == ".gz"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert json.load(handle) == loaded


def test_round_trip_keeps_selection_identity_quality_and_reasons(tmp_path):
    """Zone/setup/plan identity, B/Q/L/C, visit/confirmation and reasons survive."""

    analysis = _evaluated_analysis()
    result, pipeline, symbol = analysis
    service, loaded = _stored(tmp_path, analysis)

    compat = service.classify_analysis(_SCAN_ID, symbol)
    assert compat.status == SMC_PAYLOAD_CANONICAL
    assert compat.identity is not None

    stored = loaded["analysis_result"]["smc_scoring"]
    for side in _SIDES:
        live = _selection_of(pipeline, side)
        recorded = stored["consumer_contract"]["sides"][side]["selection"]
        # The stored selection satisfies the SAME invariant the finalizer owns.
        rebuilt = SmcSideSelection.from_dict(recorded)
        assert rebuilt.to_dict() == live.to_dict(), side
        for field_name in (
            "state",
            "selected_zone_id",
            "selected_setup_id",
            "selected_candidate_id",
            "timeframe",
            "family",
            "lifecycle_status",
            "confirmation_state",
            "confirmation_rank",
            "entry_visit_id",
            "confirmation_event_id",
            "quality_raw",
            "quality_score",
            "b",
            "q",
            "l",
            "c",
            "total",
            "zone_low",
            "zone_high",
            "plan",
            "plan_available",
            "plan_zone_id",
            "plan_setup_id",
        ):
            assert recorded[field_name] == live.to_dict()[field_name], (
                f"{side}.{field_name}"
            )
        assert list(recorded["selection_reason_codes"]) == list(
            live.selection_reason_codes
        )


def test_the_reader_reproduces_the_live_verdict_from_the_stored_payload(tmp_path):
    """The stored payload drives the reader to the SAME side/zone/quality as live."""

    _result, pipeline, _symbol = _evaluated_analysis()
    _service, loaded = _stored(tmp_path, _evaluated_analysis())

    buy = _selection_of(pipeline, "buy")
    assert buy.state == "evaluated" and buy.plan_available is True

    sample = replay_sample_from_analysis_document(loaded, dataset_split="oos")
    assert sample["side"] == "buy"
    assert sample["selected_zone_id"] == buy.selected_zone_id
    assert sample["scores"]["buy"] == float(buy.quality_raw)
    assert sample["canonical_lifecycle_status"] == buy.lifecycle_status
    assert sample["canonical_confirmation_state"] == buy.confirmation_state
    assert sample["compatibility_status"] == SMC_PAYLOAD_CANONICAL
    assert sample["provenance"] == SMC_SOURCE_CANONICAL_SELECTION
    assert sample["valid"] is True
    assert sample["validation_reason_codes"] == []


def test_zero_and_null_keep_their_meaning_across_a_restart(tmp_path):
    """``no_zone`` stays an evaluated 0 and ``data_unavailable`` stays null."""

    service, loaded = _stored(tmp_path, _no_zone_analysis())
    assert service.classify_analysis(
        _SCAN_ID, str(_T113._case("no_zone")["symbol"])
    ).status == SMC_PAYLOAD_CANONICAL
    for side in _SIDES:
        recorded = loaded["analysis_result"]["smc_scoring"]["consumer_contract"][
            "sides"
        ][side]["selection"]
        assert recorded["state"] == "no_zone"
        assert recorded["quality_raw"] == 0
        assert recorded["quality_raw"] is not None
        assert recorded["quality_score"] == 0.0
        assert recorded["selected_zone_id"] is None

    service, loaded = _stored(tmp_path, _data_unavailable_analysis())
    recorded = loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        "buy"
    ]["selection"]
    assert recorded["state"] == "data_unavailable"
    assert recorded["quality_raw"] is None
    assert recorded["quality_score"] is None
    assert recorded["selected_zone_id"] is None


def test_the_recorded_cutoff_is_the_data_cutoff_not_the_run_clock(tmp_path):
    """The decision cutoff survives, and is never confused with wall-clock time.

    The analysis document's own timestamp is when the run happened; the stored
    snapshot record is the cutoff the data was read at.  A reader must get the
    latter, and must get ``None`` — not a re-derived value — when a payload
    never recorded one.
    """

    result, pipeline, symbol = _evaluated_analysis()
    service, loaded = _stored(tmp_path, (result, pipeline, symbol))

    block = loaded["analysis_result"]["smc_scoring"]
    record = block[SMC_PERSISTENCE_SNAPSHOT_KEY]
    snapshot = pipeline._smc_snapshot
    assert record["as_of"] == snapshot.as_of.astimezone(timezone.utc).isoformat()
    assert record["m15_as_of"] == snapshot.m15_as_of.astimezone(
        timezone.utc
    ).isoformat()
    assert record["symbol"] == symbol
    assert record["tick_size"] == snapshot.tick_size
    assert record["tick_size_source"] == snapshot.tick_size_source
    assert record["core_reason_codes"] == list(snapshot.core_reason_codes)

    sample = replay_sample_from_analysis_document(loaded, dataset_split="oos")
    assert sample["snapshot_as_of"] == record["as_of"]
    assert sample["snapshot_m15_as_of"] == record["m15_as_of"]
    # The scan wall clock is a different instant from the data cutoff.
    assert sample["snapshot_as_of"] != sample["observed_at"]

    # A historical payload recorded no cutoff, so the reader reports none.
    legacy = replay_sample_from_analysis_document(
        _legacy_document(), dataset_split="oos"
    )
    assert legacy["snapshot_as_of"] is None
    assert legacy["snapshot_m15_as_of"] is None


def test_the_writer_stamps_the_running_identity_into_the_payload(tmp_path):
    """The stored payload carries the identity, built from the version constants."""

    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    block = loaded["analysis_result"]["smc_scoring"]
    stamp = block[SMC_PERSISTENCE_IDENTITY_KEY]

    assert stamp == smc_persistence_identity()
    assert stamp["rule_identity"]["rule_identity"] == SMC_RULE_IDENTITY
    assert stamp["rule_identity"]["rule_versions"] == smc_rule_versions()
    assert stamp["rule_identity"]["rule_versions"]["selection"] == SMC_SELECTION_VERSION
    assert stamp["cache_identity_version"] == SMC_CACHE_IDENTITY_VERSION
    assert stamp["rule_identity_digest"] == smc_rule_identity_digest()
    # The identity is internal metadata, never a display generation label.
    assert set(stamp).isdisjoint({"generation", "engine", "v1", "v2", "legacy"})


# ---------------------------------------------------------------------------
# 118 — cache and config compatibility markers
# ---------------------------------------------------------------------------


def test_the_cache_identity_covers_the_selection_policy():
    """A cached key must depend on HOW the final candidate is chosen."""

    versions = smc_rule_versions()
    assert versions["selection"] == SMC_SELECTION_VERSION
    identity = smc_rule_identity()
    assert identity["cache_identity_version"] == "smc-cache-key-v2"
    assert identity["rule_versions"] == versions

    # The digest is a function of the whole record, including the selection.
    other = smc_rule_identity(rule_identity="smc-rules-other")
    assert smc_rule_identity_digest(rule_identity="smc-rules-other") != (
        smc_rule_identity_digest()
    )
    assert other["rule_versions"] == versions


def test_a_payload_certified_before_the_selection_policy_is_not_current(tmp_path):
    """Dropping the selection policy from the stamp makes the payload historical."""

    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    stamp = loaded["analysis_result"]["smc_scoring"][SMC_PERSISTENCE_IDENTITY_KEY]
    del stamp["rule_identity"]["rule_versions"]["selection"]

    compat = classify_persisted_smc(loaded)
    assert compat.status == SMC_PAYLOAD_HISTORICAL
    # Editing the stamped record also invalidates the digest that describes it,
    # so both reasons are reported instead of one being silently satisfied.
    assert compat.reason_codes == (
        SMC_PERSISTENCE_IDENTITY_MISMATCH,
        SMC_PERSISTENCE_IDENTITY_DIGEST_MISMATCH,
    )
    assert compat.usable_as_current is False


def test_the_config_attestation_now_carries_the_selection_policy():
    """An attestation that cannot name the selection policy is not self-valid."""

    provenance = build_scoring_provenance()
    assert provenance["smc_selection_version"] == SMC_SELECTION_VERSION
    assert normalize_scoring_provenance(provenance) == provenance

    legacy = dict(provenance)
    del legacy["smc_selection_version"]
    assert set(normalize_scoring_provenance(legacy).values()) == {""}

    context = create_scan_context({"a": 1}, {"b": 2})
    assert context.smc_selection_version == SMC_SELECTION_VERSION
    assert context.to_dict()["smc_selection_version"] == SMC_SELECTION_VERSION


def test_a_scanner_row_document_keeps_the_attestation_and_the_stamp(tmp_path):
    """The Scanner row route persists the same stamp and a certified attestation.

    ``scanner_row_from_analysis`` re-validates the attestation through
    ``normalize_scoring_provenance``, so a row that lost the selection policy
    would be blanked here — this is the "config attestation is affected" half of
    task 118 observed on the real Scanner row adapter.
    """

    from core.scanner import scanner_row_from_analysis

    result, _pipeline, symbol = _evaluated_analysis()
    row = scanner_row_from_analysis(result)
    assert row["scoring_provenance"]["smc_selection_version"] == SMC_SELECTION_VERSION
    assert row["scoring_provenance"] == build_scoring_provenance()
    assert SMC_PERSISTENCE_IDENTITY_KEY in row["analysis_result"]["smc_scoring"]

    path = analysis_document_path(tmp_path, _SCAN_ID, symbol)
    atomic_json_save(path, build_analysis_document(row, {"scan_id": _SCAN_ID}), indent=None)
    loaded = ScannerPersistenceService(tmp_path).load_analysis(_SCAN_ID, symbol)

    assert loaded["analysis_result"]["smc_scoring"] == row["analysis_result"]["smc_scoring"]
    assert loaded["row_summary"]["scoring_provenance"] == build_scoring_provenance()
    assert classify_persisted_smc(loaded).status == SMC_PAYLOAD_CANONICAL


# ---------------------------------------------------------------------------
# 117 — the typed M15 confirmation survives storage and restart
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("build", "expected_status"),
    [(_confirmed_analysis, "confirmed"), (_invalidated_analysis, "invalidated")],
    ids=["confirmed", "invalidated"],
)
def test_the_typed_m15_confirmation_round_trips_field_by_field(
    tmp_path, build, expected_status
):
    """Every visit/trigger/time/identity/reason field survives save and reload.

    The fixture is produced by the REAL M15 window of the REAL Analyze caller, so
    the record under test is the one the evaluator actually built — not a dict
    written by the test.
    """

    analysis = build()
    result, pipeline, symbol = analysis
    live = _selection_of(pipeline, "buy")
    assert live.state == "evaluated", "the fixture must reach an evaluated side"
    assert live.confirmation is not None
    assert live.confirmation["status"] == expected_status

    service, loaded = _stored(tmp_path, analysis, selected_side="buy")
    assert service.classify_analysis(_SCAN_ID, symbol).status == SMC_PAYLOAD_CANONICAL

    recorded = loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        "buy"
    ]["selection"]["confirmation"]

    # Field by field against the LIVE typed record, including the fields the flat
    # readiness projection never carried.
    for field_name in _CONFIRMATION_FIELDS:
        expected = live.confirmation[field_name]
        if isinstance(expected, tuple):
            expected = list(expected)
        assert recorded[field_name] == expected, field_name
    assert recorded["entry_visit_id"]
    assert recorded["visit_anchor_at"]
    assert recorded["trigger_event_id"]
    assert recorded["trigger_at"]
    assert recorded["confirmation_id"]
    assert recorded["confirmed_at"]
    assert recorded["expires_at"]
    if expected_status == "invalidated":
        assert recorded["invalidated_at"]
        assert recorded["invalidation_reason"]
        assert recorded["reason_codes"]

    # The reader exposes the SAME record for whichever side it reports, verbatim.
    sample = replay_sample_from_analysis_document(loaded, dataset_split="oos")
    reported = loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        sample["side"]
    ]["selection"]["confirmation"]
    assert sample["confirmation"] == reported
    if sample["side"] == "buy":
        assert sample["confirmation"]["status"] == expected_status

    # Reloading twice is stable: nothing is recomputed on read.
    again = service.load_analysis(_SCAN_ID, symbol)
    assert again["analysis_result"]["smc_scoring"] == loaded["analysis_result"]["smc_scoring"]


def test_the_stored_confirmation_keeps_zero_distinct_from_null(tmp_path):
    """An integer 0 must not arrive as ``null`` (or the reverse)."""

    _service, loaded = _stored(tmp_path, _confirmed_analysis(), selected_side="buy")
    recorded = loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        "buy"
    ]["selection"]["confirmation"]

    assert isinstance(recorded["bars_since_anchor"], int)
    assert recorded["bars_since_anchor"] > 0
    # A field the record genuinely never had stays null — never defaulted to 0
    # or to an empty string.
    assert recorded["invalidated_at"] is None
    assert recorded["invalidation_reason"] is None
    assert recorded["parent_lifecycle_visit_id"] is None
    # ``trigger_kind`` is a string field: its "absent" value is the empty string
    # the typed record owns, not a null invented by the reader.
    assert isinstance(recorded["trigger_kind"], str)
    assert recorded["trigger_kind"] != ""
    # The reason codes are carried as data, not rebuilt from the status.
    assert recorded["reason_codes"] == list(
        M15Confirmation.from_dict(recorded).reason_codes
    )


def test_loading_never_rebuilds_a_confirmation_the_payload_did_not_have(tmp_path):
    """A side without a recorded confirmation stays empty — never back-filled."""

    service, loaded = _stored(tmp_path, _no_zone_analysis())
    block = loaded["analysis_result"]["smc_scoring"]
    for side in _SIDES:
        assert block["consumer_contract"]["sides"][side]["selection"][
            "confirmation"
        ] is None

    sample = replay_sample_from_analysis_document(loaded, dataset_split="oos")
    assert sample["confirmation"] is None

    # A historical payload never gains one either, even though it has a zone.
    historical = replay_sample_from_analysis_document(
        _legacy_document(), dataset_split="oos"
    )
    assert historical["confirmation"] is None


def test_a_tampered_stored_confirmation_is_refused(tmp_path):
    """The record is re-checked against its own invariant, so edits are caught."""

    service, loaded = _stored(tmp_path, _confirmed_analysis())
    recorded = loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        "buy"
    ]["selection"]["confirmation"]
    recorded["reason_codes"] = []

    compat = classify_persisted_smc(loaded)
    assert compat.status == SMC_PAYLOAD_INCOMPATIBLE
    assert "SMC_PERSISTENCE_SELECTION_INVALID_BUY" in compat.reason_codes
    sample = replay_sample_from_analysis_document(loaded)
    assert sample["valid"] is False


def _confirmation_identity_mutations() -> list[tuple[str, Any, str]]:
    """Edits that leave the confirmation SELF-valid but mis-paired."""

    def set_field(field_name, value):
        def mutate(selection):
            # The record stays internally well formed where it can; the point is
            # that it now describes a different setup than the selection.
            selection["confirmation"][field_name] = value

        return mutate

    return [
        ("side flipped to sell", set_field("side", "sell"), "side"),
        ("side re-cased", set_field("side", "SELL"), "side"),
        ("zone_id is another zone", set_field("zone_id", "smcz-another-zone"), "zone_id"),
        ("zone_id emptied", set_field("zone_id", ""), "zone_id"),
    ]


@pytest.mark.parametrize(
    ("label", "mutate", "mismatched_field"),
    _confirmation_identity_mutations(),
    ids=[case[0] for case in _confirmation_identity_mutations()],
)
def test_a_confirmation_of_another_setup_is_incompatible(
    tmp_path, label, mutate, mismatched_field
):
    """A self-valid confirmation that belongs to another side/zone is forged.

    The mutation is applied to the artifact on disk and read back through a NEW
    service instance, so the verdict comes from the stored bytes alone.  The
    record is refused — never repaired, never downgraded to historical, never
    served as current.
    """

    service, loaded = _stored(tmp_path, _confirmed_analysis(), selected_side="buy")
    selection = loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        "buy"
    ]["selection"]
    assert selection["confirmation"]["status"] == "confirmed"
    mutate(selection)

    path = service.analysis_path(_SCAN_ID, "XAUUSD")
    atomic_json_save(path, loaded, indent=None)

    restarted = ScannerPersistenceService(tmp_path)
    compat = restarted.classify_analysis(_SCAN_ID, "XAUUSD")
    assert compat.status == SMC_PAYLOAD_INCOMPATIBLE, label
    assert compat.usable_as_current is False, label
    reason = (
        f"{SMC_PERSISTENCE_CONFIRMATION_IDENTITY_MISMATCH}:BUY:{mismatched_field}"
    )
    assert reason in compat.reason_codes, label

    stored = restarted.load_analysis(_SCAN_ID, "XAUUSD")
    # The record is refused, not rewritten: what is on disk is what was written.
    assert stored["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        "buy"
    ]["selection"]["confirmation"] == selection["confirmation"]

    sample = replay_sample_from_analysis_document(stored, dataset_split="oos")
    assert sample["valid"] is False, label
    assert sample["compatibility_status"] == SMC_PAYLOAD_INCOMPATIBLE, label
    assert reason in " ".join(sample["validation_reason_codes"]), label


def test_a_matching_confirmation_stays_canonical(tmp_path):
    """Control: the untouched artifact is canonical through the same path."""

    service, loaded = _stored(tmp_path, _confirmed_analysis(), selected_side="buy")
    selection = loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        "buy"
    ]["selection"]
    confirmation = selection["confirmation"]

    # The links the contract actually requires all hold on real data.
    assert confirmation["side"] == selection["side"] == "buy"
    assert confirmation["zone_id"] == selection["selected_zone_id"]

    compat = service.classify_analysis(_SCAN_ID, "XAUUSD")
    assert compat.status == SMC_PAYLOAD_CANONICAL
    assert compat.reason_codes == ()
    sample = replay_sample_from_analysis_document(loaded, dataset_split="oos")
    assert sample["compatibility_status"] == SMC_PAYLOAD_CANONICAL
    assert sample["confirmation"] == confirmation


def test_the_confirmation_visit_ids_are_not_the_selection_visit_id(tmp_path):
    """Why no equality rule is asserted for ``entry_visit_id``.

    The selection's ``entry_visit_id`` is a LIFECYCLE zone visit, while the
    confirmation owns the M15 ENTRY visit it was raised on.  They are built in
    different namespaces and are never equal, so requiring them to match would
    reject every real canonical payload.  What does hold — and is checked — is
    that the confirmation's ids are scoped to the SAME zone as the selection.
    """

    _service, loaded = _stored(tmp_path, _confirmed_analysis(), selected_side="buy")
    selection = loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        "buy"
    ]["selection"]
    confirmation = selection["confirmation"]

    assert selection["entry_visit_id"]
    assert confirmation["entry_visit_id"]
    assert confirmation["entry_visit_id"] != selection["entry_visit_id"]
    zone = selection["selected_zone_id"]
    # Same zone, different visit namespaces.
    assert confirmation["entry_visit_id"].startswith(f"{zone}:m15-visit-")
    assert selection["entry_visit_id"].startswith(f"{zone}:")
    assert not selection["entry_visit_id"].startswith(f"{zone}:m15-visit-")


def test_a_restored_confirmation_cannot_certify_a_dispatch(tmp_path):
    """A stored confirmation is evidence; it never clears the revalidation gate."""

    from core.execution_revalidation_engine import _smc_revalidation_blocks

    _service, loaded = _stored(tmp_path, _confirmed_analysis(), selected_side="buy")
    selection = loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        "buy"
    ]["selection"]
    confirmation = selection["confirmation"]
    assert confirmation["status"] == "confirmed"
    assert confirmation["confirmed_at"] is not None

    # Even handing the gate the recorded confirmation verbatim is not enough: the
    # gate reads the NEW snapshot verdict, which a stored record can never be.
    approved = {
        "side": "buy",
        "selected_zone_id": selection["selected_zone_id"],
        "selected_setup_id": selection["selected_setup_id"],
        "confirmation": confirmation,
    }
    blocks = _smc_revalidation_blocks({"approved": approved, "current": confirmation})
    assert blocks, "a stored confirmation must never clear the gate"
    assert "SMC_M15_UNAVAILABLE" in blocks or "SMC_NOT_READY" in blocks
    assert _smc_revalidation_blocks({"approved": approved}) == [
        "SMC_REVALIDATION_UNAVAILABLE"
    ]

    sample = replay_sample_from_analysis_document(loaded, dataset_split="oos")
    for gate_field in ("state", "readiness_status", "m15_status", "selected_setup_id"):
        assert gate_field not in sample


# ---------------------------------------------------------------------------
# 118 — every stamped marker is verified, not just the convenient ones
# ---------------------------------------------------------------------------

_IDENTITY = "analysis_result.smc_scoring.persistence_identity"


def _marker_mutations() -> list[tuple[str, Any, str, str]]:
    """(label, mutate, expected status, expected reason substring) per marker."""

    def set_stamp(key):
        def mutate(document):
            block = document["analysis_result"]["smc_scoring"]
            block[SMC_PERSISTENCE_IDENTITY_KEY][key] = "tampered"

        return mutate

    def drop(path):
        def mutate(document):
            block = document["analysis_result"]["smc_scoring"]
            if path == "snapshot":
                block.pop(SMC_PERSISTENCE_SNAPSHOT_KEY)
            else:
                for side in _SIDES:
                    block["consumer_contract"]["sides"][side]["selection"].pop(path)

        return mutate

    def set_selection(key):
        def mutate(document):
            block = document["analysis_result"]["smc_scoring"]
            for side in _SIDES:
                block["consumer_contract"]["sides"][side]["selection"][key] = "old-v0"

        return mutate

    return [
        ("cache_identity_version", set_stamp("cache_identity_version"),
         SMC_PAYLOAD_HISTORICAL, SMC_PERSISTENCE_IDENTITY_MISMATCH),
        ("rule_identity_digest", set_stamp("rule_identity_digest"),
         SMC_PAYLOAD_HISTORICAL, SMC_PERSISTENCE_IDENTITY_DIGEST_MISMATCH),
        ("scoring_contract_version", set_stamp("scoring_contract_version"),
         SMC_PAYLOAD_HISTORICAL, SMC_PERSISTENCE_IDENTITY_MISMATCH),
        ("selection_contract_version", set_stamp("selection_contract_version"),
         SMC_PAYLOAD_HISTORICAL, SMC_PERSISTENCE_IDENTITY_MISMATCH),
        ("selection_version", set_stamp("selection_version"),
         SMC_PAYLOAD_HISTORICAL, SMC_PERSISTENCE_IDENTITY_MISMATCH),
        ("persistence_contract_version", set_stamp("persistence_contract_version"),
         SMC_PAYLOAD_HISTORICAL, SMC_PERSISTENCE_IDENTITY_MISMATCH),
        ("nested cache_identity_version",
         lambda d: d["analysis_result"]["smc_scoring"][
             SMC_PERSISTENCE_IDENTITY_KEY
         ]["rule_identity"].__setitem__("cache_identity_version", "tampered"),
         SMC_PAYLOAD_HISTORICAL, SMC_PERSISTENCE_IDENTITY_MISMATCH),
        ("snapshot record dropped", drop("snapshot"),
         SMC_PAYLOAD_INCOMPATIBLE, "SMC_PERSISTENCE_SNAPSHOT_MISSING"),
        ("selection contract_version dropped", drop("contract_version"),
         SMC_PAYLOAD_INCOMPATIBLE,
         "SMC_PERSISTENCE_SELECTION_CONTRACT_MISSING"),
        ("selection selection_version dropped", drop("selection_version"),
         SMC_PAYLOAD_INCOMPATIBLE,
         "SMC_PERSISTENCE_SELECTION_CONTRACT_MISSING"),
        ("selection contract_version moved", set_selection("contract_version"),
         SMC_PAYLOAD_INCOMPATIBLE,
         "SMC_PERSISTENCE_SELECTION_CONTRACT_MISMATCH"),
        ("selection selection_version moved", set_selection("selection_version"),
         SMC_PAYLOAD_INCOMPATIBLE,
         "SMC_PERSISTENCE_SELECTION_CONTRACT_MISMATCH"),
    ]


@pytest.mark.parametrize(
    ("label", "mutate", "expected_status", "expected_reason"),
    _marker_mutations(),
    ids=[case[0] for case in _marker_mutations()],
)
def test_a_tampered_marker_is_never_read_as_current(
    tmp_path, label, mutate, expected_status, expected_reason
):
    """Each stamped marker is independently verified — no marker is decorative.

    The mutation is applied to the artifact on disk and re-read through a NEW
    service instance, so the verdict comes from the stored bytes alone.  A
    payload that lost or contradicts a mandatory marker is never
    ``canonical_compatible`` and is never readable as a current result.
    """

    service, _loaded = _stored(tmp_path, _evaluated_analysis())
    path = service.analysis_path(_SCAN_ID, "XAUUSD")
    document = service.load_analysis(_SCAN_ID, "XAUUSD")
    mutate(document)
    atomic_json_save(path, document, indent=None)

    restarted = ScannerPersistenceService(tmp_path)
    compat = restarted.classify_analysis(_SCAN_ID, "XAUUSD")
    assert compat.status == expected_status, label
    assert expected_reason in " ".join(compat.reason_codes), label
    assert compat.usable_as_current is False, label

    sample = replay_sample_from_analysis_document(
        restarted.load_analysis(_SCAN_ID, "XAUUSD"), dataset_split="oos"
    )
    assert sample["compatibility_status"] == expected_status, label
    # ``provenance`` reports WHERE the evidence was read from, ``status`` reports
    # whether it may be trusted as current — they are independent on purpose, so
    # the assertion is on the trust level, never on the source.
    assert sample["compatibility_status"] != SMC_PAYLOAD_CANONICAL, label
    if expected_status != SMC_PAYLOAD_HISTORICAL:
        assert sample["valid"] is False, label
        assert expected_reason.split(":")[0] in " ".join(
            sample["validation_reason_codes"]
        ), label


def test_the_clean_artifact_passes_every_marker_check(tmp_path):
    """Control: with no mutation the same path classifies canonical."""

    service, _loaded = _stored(tmp_path, _evaluated_analysis())
    compat = service.classify_analysis(_SCAN_ID, "XAUUSD")
    assert compat.status == SMC_PAYLOAD_CANONICAL
    assert compat.reason_codes == ()
    assert compat.usable_as_current is True


def test_a_cached_key_hits_on_the_same_rules_and_misses_when_a_policy_moves(tmp_path):
    """Cache hit for identical input; a moved policy must invalidate the key."""

    import core.smc_snapshot_cache as cache

    fixture_path = (
        Path(__file__).parent / "fixtures" / "smc_snapshot_cache_task38.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    kwargs = {
        "symbol": fixture["symbol"],
        "as_of": fixture["as_of"],
        "candles_by_timeframe": {
            timeframe: tuple(
                Candle(
                    time=datetime.fromisoformat(
                        item["time"].replace("Z", "+00:00")
                    ).astimezone(timezone.utc),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item["volume"]),
                )
                for item in candles
            )
            for timeframe, candles in fixture["candles"].items()
        },
        "metadata": dict(fixture["metadata"]),
        "rule_identity": fixture["rule_identity"],
    }

    first = cache.smc_snapshot_identity(**kwargs)
    assert first == cache.smc_snapshot_identity(**kwargs), "identical input must hit"
    assert first == cache.smc_snapshot_identity(**dict(kwargs))

    # The selection policy is the only thing that moves: the key must miss.
    moved = dict(cache.smc_rule_versions(), selection="smc-selection-moved")
    original = cache.smc_rule_versions
    try:
        cache.smc_rule_versions = lambda: moved
        assert cache.smc_snapshot_identity(**kwargs) != first
    finally:
        cache.smc_rule_versions = original
    assert cache.smc_snapshot_identity(**kwargs) == first

    # A payload certified under that moved policy is historical, not current.
    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    stamp = loaded["analysis_result"]["smc_scoring"][SMC_PERSISTENCE_IDENTITY_KEY]
    stamp["rule_identity"]["rule_versions"]["selection"] = "smc-selection-moved"
    compat = classify_persisted_smc(loaded)
    assert compat.status == SMC_PAYLOAD_HISTORICAL
    assert compat.usable_as_current is False


# ---------------------------------------------------------------------------
# 119 / 120 — historical, incompatible and corrupted payloads
# ---------------------------------------------------------------------------


def _legacy_document() -> dict[str, Any]:
    """The stored shape written before the canonical contract existed."""

    return {
        "symbol": "EURUSD",
        "scan_context": {"started_at": "2026-07-01T00:00:00+00:00"},
        "row_summary": {
            "row_id": "scan-1:EURUSD",
            "selected_side": "buy",
            "candidate_status": "WATCH_ZONE",
        },
        "candidate_decision": {"selected_side": "buy", "status": "WATCH_ZONE"},
        "analysis_result": {
            "market_regime": {"primary": "trend_up"},
            "smc_scoring": {
                "contract_version": "smc-scoring-canonical-2026-08",
                "scoring_version": "smc-v2",
                "sides": {
                    "buy": {
                        "score": 12,
                        "selected_zone_id": "v2-zone",
                        "selected_zone_quality_score": 82,
                        "selected_zone_relevance_score": 76,
                        "scoring_version": "smc-v2",
                    },
                    "sell": {"score": 1, "selected_zone_id": None, "scoring_version": "smc-v2"},
                },
                "consumer_contract": {
                    "contract_version": "smc-consumer-v2",
                    "sides": {
                        "buy": {
                            "selected_zone_id": "v2-zone",
                            "selected_zone": {
                                "zone_id": "v2-zone",
                                "family": "demand",
                                "independent_retest_count": 0,
                                "liquidity_sweep_linked": True,
                            },
                        },
                        "sell": {},
                    },
                },
            },
        },
    }


def test_a_historical_document_is_read_with_its_own_meaning():
    """No identity stamp ⇒ historical: legacy fields read, nothing invented."""

    document = _legacy_document()
    compat = classify_persisted_smc(document)
    assert compat.status == SMC_PAYLOAD_HISTORICAL
    assert compat.reason_codes == (SMC_PERSISTENCE_IDENTITY_MISSING,)
    assert compat.source == SMC_SOURCE_LEGACY_SELECTED_ZONE

    sample = replay_sample_from_analysis_document(document, dataset_split="oos")
    assert sample["valid"] is True
    assert sample["compatibility_status"] == SMC_PAYLOAD_HISTORICAL
    assert sample["provenance"] == SMC_SOURCE_LEGACY_SELECTED_ZONE
    # Read as recorded …
    assert sample["selected_zone_id"] == "v2-zone"
    assert sample["zone_family"] == "demand"
    assert sample["linked_sweep"] is True
    assert sample["zone_quality_score"] == 82
    # … and the canonical vocabulary stays empty instead of being back-filled.
    assert sample["canonical_lifecycle_status"] is None
    assert sample["canonical_confirmation_state"] is None


def test_a_payload_with_another_rule_identity_is_historical_not_current(tmp_path):
    """Same schema, different scorer/selection identity ⇒ historical."""

    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    stamp = loaded["analysis_result"]["smc_scoring"][SMC_PERSISTENCE_IDENTITY_KEY]
    stamp["rule_identity"]["rule_identity"] = "smc-rules-other"

    compat = classify_persisted_smc(loaded)
    assert compat.status == SMC_PAYLOAD_HISTORICAL
    # Editing the stamped record also invalidates the digest that describes it,
    # so both reasons are reported instead of one being silently satisfied.
    assert compat.reason_codes == (
        SMC_PERSISTENCE_IDENTITY_MISMATCH,
        SMC_PERSISTENCE_IDENTITY_DIGEST_MISMATCH,
    )
    assert compat.usable_as_current is False
    # The recorded selection is still readable, but only as what it recorded.
    assert compat.source == SMC_SOURCE_CANONICAL_SELECTION

    sample = replay_sample_from_analysis_document(loaded)
    assert sample["compatibility_status"] == SMC_PAYLOAD_HISTORICAL


def test_reading_a_stored_document_never_rewrites_it(tmp_path):
    """A historical payload is opened, classified and left byte-identical."""

    document = _legacy_document()
    path = analysis_document_path(tmp_path, _SCAN_ID, "EURUSD")
    atomic_json_save(path, document, indent=None)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    service = ScannerPersistenceService(tmp_path)
    loaded = service.load_analysis(_SCAN_ID, "EURUSD")
    assert service.classify_analysis(_SCAN_ID, "EURUSD").status == SMC_PAYLOAD_HISTORICAL
    replay_sample_from_analysis_document(loaded, dataset_split="oos")

    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert loaded == document
    # Nothing was promoted into the current contract.
    assert SMC_PERSISTENCE_IDENTITY_KEY not in loaded["analysis_result"]["smc_scoring"]


def test_an_unknown_contract_version_is_incompatible_and_never_a_valid_sample(tmp_path):
    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    loaded["analysis_result"]["smc_scoring"]["contract_version"] = (
        "smc-scoring-canonical-2099-01"
    )

    compat = classify_persisted_smc(loaded)
    assert compat.status == SMC_PAYLOAD_INCOMPATIBLE
    assert compat.reason_codes == (SMC_PERSISTENCE_CONTRACT_UNSUPPORTED,)
    assert compat.readable is False

    sample = replay_sample_from_analysis_document(loaded, dataset_split="oos")
    assert sample["valid"] is False
    assert SMC_PERSISTENCE_CONTRACT_UNSUPPORTED in sample["validation_reason_codes"]
    assert sample["compatibility_status"] == SMC_PAYLOAD_INCOMPATIBLE


def test_a_recorded_selection_that_breaks_its_own_invariant_is_incompatible(tmp_path):
    """A selected setup with an available plan must name the zone it belongs to."""

    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    recorded = loaded["analysis_result"]["smc_scoring"]["consumer_contract"]["sides"][
        "buy"
    ]["selection"]
    recorded["selected_zone_id"] = None

    compat = classify_persisted_smc(loaded)
    assert compat.status == SMC_PAYLOAD_INCOMPATIBLE
    assert SMC_PERSISTENCE_SELECTION_MALFORMED in compat.reason_codes

    sample = replay_sample_from_analysis_document(loaded, dataset_split="oos")
    assert sample["valid"] is False
    assert SMC_PERSISTENCE_SELECTION_MALFORMED in sample["validation_reason_codes"]


def test_a_stamped_payload_without_a_selection_is_incomplete_not_current(tmp_path):
    """A current stamp promises one selection per side; a torn write is not trusted."""

    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    block = loaded["analysis_result"]["smc_scoring"]
    for side in _SIDES:
        block["consumer_contract"]["sides"][side]["selection"] = None

    compat = classify_persisted_smc(loaded)
    assert compat.status == SMC_PAYLOAD_INCOMPATIBLE
    assert compat.reason_codes == (
        SMC_PERSISTENCE_SELECTION_MISSING,
        "SMC_PERSISTENCE_SELECTION_MISSING_BUY",
        "SMC_PERSISTENCE_SELECTION_MISSING_SELL",
    )
    assert replay_sample_from_analysis_document(loaded)["valid"] is False


def test_a_stamped_payload_missing_one_side_is_not_read_partly_canonical(tmp_path):
    """One absent side must not be read through the historical field instead."""

    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    block = loaded["analysis_result"]["smc_scoring"]
    block["consumer_contract"]["sides"]["sell"]["selection"] = None
    # The legacy field is still populated, so a lenient reader would report it.
    block["consumer_contract"]["sides"]["sell"]["selected_zone"] = {
        "zone_id": "legacy-zone",
        "family": "supply_demand",
        "liquidity_sweep_linked": True,
    }

    compat = classify_persisted_smc(loaded)
    assert compat.status == SMC_PAYLOAD_INCOMPATIBLE
    assert compat.reason_codes == (
        SMC_PERSISTENCE_SELECTION_MISSING,
        "SMC_PERSISTENCE_SELECTION_MISSING_SELL",
    )

    sample = replay_sample_from_analysis_document(loaded)
    assert sample["valid"] is False
    assert sample["side"] == "buy"
    assert SMC_PERSISTENCE_SELECTION_MISSING in sample["validation_reason_codes"]


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        ("block", SMC_PERSISTENCE_BLOCK_MISSING),
        ("sides", SMC_PERSISTENCE_BLOCK_MALFORMED),
        ("contract", SMC_PERSISTENCE_CONTRACT_MISSING),
    ],
)
def test_a_corrupted_block_never_normalizes_into_a_valid_sample(
    tmp_path, mutate: str, reason: str
):
    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    block = loaded["analysis_result"]["smc_scoring"]
    if mutate == "block":
        del loaded["analysis_result"]["smc_scoring"]
    elif mutate == "sides":
        block["sides"] = ["not", "a", "mapping"]
    else:
        block["contract_version"] = None

    compat = classify_persisted_smc(loaded)
    assert compat.status == SMC_PAYLOAD_CORRUPTED
    assert reason in compat.reason_codes

    sample = replay_sample_from_analysis_document(loaded)
    assert sample["valid"] is False
    assert reason in sample["validation_reason_codes"]


def test_an_unreadable_artifact_is_refused_instead_of_read_as_empty(tmp_path):
    """A truncated/foreign file raises; it is never read as "no data"."""

    path = analysis_document_path(tmp_path, _SCAN_ID, "EURUSD")
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("[1, 2, 3]")
    # Valid gzip, valid JSON, wrong shape: refused, never read as "no data".
    with pytest.raises(ValueError):
        load_json_document(path)
    with pytest.raises(ValueError):
        ScannerPersistenceService(tmp_path).classify_analysis(_SCAN_ID, "EURUSD")

    # Unreadable bytes are an error either way; they never read as an empty doc.
    plain = analysis_document_path(tmp_path, _SCAN_ID, "GBPUSD").with_suffix(".json")
    plain.write_text("not json at all", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_json_document(plain)

    path.write_bytes(b"not a gzip stream")
    with pytest.raises(OSError):
        load_json_document(path)


def test_persisting_and_reading_never_touches_journal_or_open_orders(tmp_path):
    """The persistence cycle writes only under its runtime root.

    A journal entry and an open managed position are laid down first (real
    stores, temporary paths — never operational storage).  Writing, reading,
    classifying and replaying a stored SMC document must leave both artifacts
    byte-identical and the position still open.
    """

    from services.journal_models import JournalEntry
    from services.journal_service import JournalService
    from services.order_management_state_store import (
        ManagedPositionState,
        OrderManagementStateStore,
    )

    journal_path = tmp_path / "journal" / "journal.sqlite3"
    order_path = tmp_path / "order_management_state.json"

    journal = JournalService(db_path=journal_path)
    journal.migrate()
    entry_id = journal.create(
        JournalEntry(
            id=None,
            timestamp_utc="2026-09-16T10:00:00+00:00",
            saved_at_utc="2026-09-16T10:00:01+00:00",
            symbol="XAUUSD",
            broker_symbol="XAUUSD",
            mode="scanner_detail",
            data_source="live",
            market_regime="trend_up",
            decision="ready",
            direction_bias="buy",
            trade_permission="allowed",
            buy_score=70,
            sell_score=10,
            selected_scenario="buy",
            entry_zone="1000-1002",
            stop_loss="995",
            take_profit="1020",
            risk_reward="4.0",
            suggested_lot=0.1,
            ai_commentary="",
            analysis_json="{}",
        )
    )
    account = {"broker": "TmpBroker", "server": "TmpServer", "login": "12345678"}
    store = OrderManagementStateStore(path=order_path)
    saved = store.save(
        account=account,
        positions=[
            ManagedPositionState(
                ticket=4242,
                symbol="XAUUSD",
                side="buy",
                original_sl=995.0,
                trailing={"enabled": False},
            )
        ],
    )

    assert saved.status.value == "saved"

    # The order-state artifact is plain deterministic JSON, so byte identity is
    # the right check.  The journal is SQLite in WAL mode, where the file bytes
    # legitimately change on checkpoint without any row changing — so the check
    # there is SQLite's own "did another connection write this database" signal,
    # read on ONE held connection, plus the rows themselves.
    order_before = hashlib.sha256(order_path.read_bytes()).hexdigest()
    probe = sqlite3.connect(journal_path)
    try:
        version_before = probe.execute("PRAGMA data_version").fetchone()[0]
        rows_before = probe.execute(
            "SELECT id, symbol, entry_zone, stop_loss, take_profit FROM journal_entries"
        ).fetchall()

        # The full cycle, including the failure paths.
        _service, loaded = _stored(tmp_path, _evaluated_analysis())
        replay_sample_from_analysis_document(loaded, dataset_split="oos")
        broken = json.loads(json.dumps(loaded))
        broken["analysis_result"]["smc_scoring"]["contract_version"] = "unknown-2099"
        assert classify_persisted_smc(broken).status == SMC_PAYLOAD_INCOMPATIBLE
        replay_sample_from_analysis_document(broken)

        assert probe.execute("PRAGMA data_version").fetchone()[0] == version_before
        assert probe.execute(
            "SELECT id, symbol, entry_zone, stop_loss, take_profit FROM journal_entries"
        ).fetchall() == rows_before
    finally:
        probe.close()
    assert hashlib.sha256(order_path.read_bytes()).hexdigest() == order_before

    # And the artifacts still read back with their original meaning.
    entries = journal.list_entries()
    assert [item.id for item in entries] == [entry_id]
    assert entries[0].entry_zone == "1000-1002"
    assert entries[0].stop_loss == "995"
    reloaded = OrderManagementStateStore(path=order_path).load(account=account)
    assert reloaded.status.value == "loaded"
    position = reloaded.snapshot.by_ticket()[4242]
    assert position.symbol == "XAUUSD"
    assert position.original_sl == 995.0


# ---------------------------------------------------------------------------
# 118 / 120 — the result-cache seam: a real hit, and every way it must miss
# ---------------------------------------------------------------------------

_CACHE_IDENTITY = "smc-cache-key-v2:snapshot-under-test"


def _cached(tmp_path: Path):
    """Evaluate for real, store the result, and read it back on a NEW instance."""

    result, _pipeline, _symbol = _evaluated_analysis()
    block = result["smc_scoring"]
    writer = ScannerPersistenceService(tmp_path)
    path = writer.write_smc_cache_record(
        snapshot_identity=_CACHE_IDENTITY, record=block
    )
    reader = ScannerPersistenceService(tmp_path)
    return path, reader, block


def test_a_cached_canonical_result_is_a_real_positive_lookup(tmp_path):
    """Hit through the stored record, read by a different service instance."""

    path, reader, block = _cached(tmp_path)
    assert path.is_file()

    lookup = reader.read_smc_cache_record(snapshot_identity=_CACHE_IDENTITY)
    assert lookup.hit is True
    assert lookup.usable is True
    assert lookup.reason_codes == ()
    # The served record is the one that was evaluated, not a reconstruction.
    assert lookup.record == block
    assert lookup.record["consumer_contract"]["sides"]["buy"]["selection"][
        "confirmation"
    ] is not None


def test_a_cache_lookup_for_an_input_never_stored_is_a_plain_miss(tmp_path):
    _path, reader, _block = _cached(tmp_path)
    lookup = reader.read_smc_cache_record(snapshot_identity="another-input")
    assert lookup.hit is False
    assert lookup.usable is False
    assert lookup.record is None
    assert lookup.reason_codes == (SMC_CACHE_MISS_ABSENT,)


def test_moving_only_the_selection_policy_invalidates_the_cached_record(tmp_path):
    """The cache depends on HOW the candidate was chosen, not just the scorer."""

    path, reader, _block = _cached(tmp_path)
    assert reader.read_smc_cache_record(snapshot_identity=_CACHE_IDENTITY).hit is True

    # The same scorer/domain, a moved selection policy: every other marker is
    # left alone so only the selection identity can explain the miss.
    moved = dict(smc_rule_versions(), selection="smc-selection-moved")
    envelope = json.loads(gzip.open(path, "rt", encoding="utf-8").read())
    changed = dict(envelope[SMC_RESULT_CACHE_IDENTITY_KEY])
    changed["selection_version"] = "smc-selection-moved"
    changed["rule_identity"] = dict(changed["rule_identity"])
    changed["rule_identity"]["rule_versions"] = moved
    envelope[SMC_RESULT_CACHE_IDENTITY_KEY] = changed
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(envelope, handle)

    restarted = ScannerPersistenceService(tmp_path)
    lookup = restarted.read_smc_cache_record(snapshot_identity=_CACHE_IDENTITY)
    assert lookup.hit is False
    assert lookup.usable is False
    assert lookup.record is None
    assert lookup.reason_codes == (SMC_CACHE_MISS_IDENTITY_MISMATCH,)
    assert SMC_PERSISTENCE_IDENTITY_MISMATCH in lookup.identity_mismatch_codes


@pytest.mark.parametrize(
    ("label", "mutate", "expected_reason"),
    [
        (
            "digest tampered",
            lambda e: e[SMC_RESULT_CACHE_IDENTITY_KEY].__setitem__(
                "rule_identity_digest", "tampered"
            ),
            SMC_CACHE_MISS_IDENTITY_MISMATCH,
        ),
        (
            "identity removed",
            lambda e: e.pop(SMC_RESULT_CACHE_IDENTITY_KEY),
            SMC_CACHE_MISS_IDENTITY_MISMATCH,
        ),
        (
            "cache contract unknown",
            lambda e: e.__setitem__("cache_contract_version", "smc-result-cache-2099"),
            SMC_CACHE_MISS_RECORD_INVALID,
        ),
        (
            "record missing",
            lambda e: e.pop("record"),
            SMC_CACHE_MISS_RECORD_CORRUPTED,
        ),
        (
            "record is not a canonical block",
            lambda e: e.__setitem__("record", {"contract_version": "zzz", "sides": {}}),
            SMC_CACHE_MISS_RECORD_INVALID,
        ),
        (
            "snapshot identity rewritten",
            lambda e: e.__setitem__("snapshot_identity", "some-other-input"),
            SMC_CACHE_MISS_SNAPSHOT_MISMATCH,
        ),
    ],
)
def test_a_cache_record_that_lost_its_marker_or_shape_misses(
    tmp_path, label, mutate, expected_reason
):
    """No fallback path: every broken artifact misses and returns no result."""

    path, _reader, _block = _cached(tmp_path)
    envelope = json.loads(gzip.open(path, "rt", encoding="utf-8").read())
    mutate(envelope)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(envelope, handle)

    lookup = ScannerPersistenceService(tmp_path).read_smc_cache_record(
        snapshot_identity=_CACHE_IDENTITY
    )
    assert lookup.hit is False, label
    assert lookup.usable is False, label
    assert lookup.record is None, label
    assert expected_reason in lookup.reason_codes, label


def test_an_unreadable_cache_artifact_misses_without_raising(tmp_path):
    path, reader, _block = _cached(tmp_path)
    path.write_bytes(b"not a gzip stream")

    lookup = reader.read_smc_cache_record(snapshot_identity=_CACHE_IDENTITY)
    assert lookup.hit is False
    assert lookup.record is None
    assert lookup.reason_codes == (SMC_CACHE_MISS_RECORD_CORRUPTED,)

    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("[1, 2, 3]")
    assert reader.read_smc_cache_record(
        snapshot_identity=_CACHE_IDENTITY
    ).reason_codes == (SMC_CACHE_MISS_RECORD_CORRUPTED,)


def test_a_cache_hit_is_stable_across_a_restart_and_never_touches_the_journal(tmp_path):
    """The seam is read-only towards everything outside its own cache directory."""

    import sqlite3

    from services.order_management_state_store import (
        ManagedPositionState as ManagedPositionStateState,
        OrderManagementStateStore,
    )

    order_path = tmp_path / "order_management_state.json"
    account = {"broker": "TmpBroker", "server": "TmpServer", "login": "12345678"}
    assert OrderManagementStateStore(path=order_path).save(
        account=account,
        positions=[
            ManagedPositionStateState(
                ticket=7, symbol="XAUUSD", side="buy", original_sl=990.0
            )
        ],
    ).status.value == "saved"
    before = hashlib.sha256(order_path.read_bytes()).hexdigest()

    path, _reader, block = _cached(tmp_path)
    first = ScannerPersistenceService(tmp_path).read_smc_cache_record(
        snapshot_identity=_CACHE_IDENTITY
    )
    second = ScannerPersistenceService(tmp_path).read_smc_cache_record(
        snapshot_identity=_CACHE_IDENTITY
    )
    assert first.hit is True and second.hit is True
    assert first.record == second.record == block
    assert hashlib.sha256(order_path.read_bytes()).hexdigest() == before
    # The seam writes only inside its own cache directory.
    assert path.parent.name == "smc_results"
    assert path.parent.parent.name == "cache"


# ---------------------------------------------------------------------------
# 120 — restart: nothing historical becomes a live result
# ---------------------------------------------------------------------------


def test_a_restart_reader_cannot_feed_the_execution_revalidation_gate(tmp_path):
    """A stored payload is evidence, not the "current" verdict the gate needs.

    Execution revalidation compares the approved setup against the verdict of a
    NEW snapshot.  The persisted reader exposes the recorded decision only; it
    must not hand over the fields that gate reads (``state``,
    ``readiness_status``, ``m15_status``, ``selected_setup_id``), so a restart
    can never skip revalidation or revive an expired confirmation.
    """

    from core.execution_revalidation_engine import (
        SMC_REVALIDATION_UNAVAILABLE,
        _smc_revalidation_blocks,
    )

    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    sample = replay_sample_from_analysis_document(loaded, dataset_split="oos")

    for gate_field in ("state", "readiness_status", "m15_status", "selected_setup_id"):
        assert gate_field not in sample, gate_field

    # Feeding the recorded sample where a fresh verdict is required fails closed.
    approved = {
        "side": sample["side"],
        "selected_zone_id": sample["selected_zone_id"],
        "selected_setup_id": None,
        "plan": None,
    }
    blocks = _smc_revalidation_blocks({"approved": approved, "current": sample})
    assert blocks, "a stored payload must never clear the revalidation gate"
    # The recorded payload cannot certify readiness or a live M15 confirmation.
    assert "SMC_NOT_READY" in blocks
    assert "SMC_M15_UNAVAILABLE" in blocks

    # Supplying nothing at all is the documented fail-closed case.
    assert _smc_revalidation_blocks({"approved": approved}) == [
        SMC_REVALIDATION_UNAVAILABLE
    ]
    assert _smc_revalidation_blocks(None) == [SMC_REVALIDATION_UNAVAILABLE]


def test_only_a_canonical_compatible_payload_may_be_read_as_current(tmp_path):
    """The four states never collapse into each other."""

    _service, loaded = _stored(tmp_path, _evaluated_analysis())
    canonical = classify_persisted_smc(loaded)
    assert canonical.status == SMC_PAYLOAD_CANONICAL
    assert canonical.usable_as_current is True

    historical = classify_persisted_smc(_legacy_document())
    assert historical.status == SMC_PAYLOAD_HISTORICAL
    assert historical.readable is True
    assert historical.usable_as_current is False

    for document, expected in (
        ({}, SMC_PAYLOAD_CORRUPTED),
        ({"analysis_result": {"smc_scoring": {"contract_version": "x", "sides": []}}},
         SMC_PAYLOAD_CORRUPTED),
    ):
        compat = classify_persisted_smc(document)
        assert compat.status == expected
        assert compat.readable is False
        assert compat.usable_as_current is False


def test_restart_keeps_the_recorded_scan_time_and_does_not_advance_it(tmp_path):
    """Reading a stored payload never re-dates (or refreshes) the decision."""

    result, pipeline, symbol = _evaluated_analysis()
    _persist(tmp_path, symbol, result)

    service = ScannerPersistenceService(tmp_path)
    first = service.load_analysis(_SCAN_ID, symbol)
    second = service.load_analysis(_SCAN_ID, symbol)
    assert first == second

    block = first["analysis_result"]["smc_scoring"]
    as_of = _R114.CUTOFF
    assert isinstance(as_of, datetime)
    # The stored selection is the one evaluated at the snapshot cutoff, unchanged.
    buy = _selection_of(pipeline, "buy")
    assert block["consumer_contract"]["sides"]["buy"]["selection"][
        "selected_zone_id"
    ] == buy.selected_zone_id
    assert block["consumer_contract"]["sides"]["buy"]["selection"][
        "confirmation_state"
    ] == buy.confirmation_state
    assert datetime.now(timezone.utc) > as_of
