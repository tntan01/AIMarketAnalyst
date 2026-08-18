"""Step-02 tests for the non-runtime Scanner domain contract."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone

import pytest

from core.reason_codes import (
    SCANNER_FORBIDDEN_SCORED_FIELD,
    SCANNER_LEGACY_V3_AUDIT_ONLY,
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISMATCH,
    SCANNER_VERSION_MISSING,
)
from core.scanner_models import (
    CanonicalPairSnapshot,
    DecisionResult,
    GateCheck,
    MacroAssessment,
    MacroGateResult,
    MarketSafetyResult,
    PAYLOAD_INVALID,
    PAYLOAD_LEGACY_V3,
    PAYLOAD,
    SCANNER_FEATURE_VERSION,
    SCANNER_SCORER_VERSION,
    SCANNER_V4_FEATURE_VERSION,
    SCANNER_MACRO_POLICY_VERSION,
    SCANNER_OUTPUT_SCHEMA_VERSION,
    SCANNER_V4_RANKING_VERSION,
    SCANNER_SAFETY_POLICY_VERSION,
    SCANNER_SCORING_VERSION,
    SCANNER_SNAPSHOT_VERSION,
    SCANNER_VERSION_FIELDS,
    ScannerContractError,
    SideScore,
    TechnicalBreakdown,
    TechnicalComponent,
    classify_scanner_payload,
    classify_scanner_payload_json,
    deserialize_canonical_pair_snapshot,
    serialize_canonical_pair_snapshot,
    validate_canonical_pair_snapshot,
)


NOW = datetime(2026, 8, 13, 9, 30, tzinfo=timezone.utc)


def _breakdown(
    *,
    side: str = "buy",
    unavailable: bool = False,
) -> TechnicalBreakdown:
    valid_raw = (20, 15, 20, 10) if side == "buy" else (10, 10, 15, 12)
    raw = (None, None, None, None) if unavailable else valid_raw
    contribution = (
        (None, None, None, None)
        if unavailable
        else tuple(
            (value * weight) / maximum
            for value, maximum, weight in zip(
                raw,
                (25, 20, 25, 15),
                (40, 20, 20, 20),
            )
        )
    )
    return TechnicalBreakdown(
        trend=TechnicalComponent(raw[0], 25, 40, contribution[0]),
        momentum=TechnicalComponent(raw[1], 20, 20, contribution[1]),
        location=TechnicalComponent(raw[2], 25, 20, contribution[2]),
        smc=TechnicalComponent(raw[3], 15, 20, contribution[3]),
    )


def _side(side: str, *, unavailable: bool = False) -> SideScore:
    if unavailable:
        return SideScore(
            side=side,
            technical_signal_score=None,
            technical_breakdown=_breakdown(unavailable=True),
            evidence_score=None,
            evidence_source="unavailable",
            execution_quality_score=None,
            execution_quality_source="unavailable",
            setup_score=None,
            final_score=None,
            reason_codes=("TECHNICAL_DATA_UNAVAILABLE",),
        )
    technical = 76 if side == "buy" else 54
    setup = 70 if side == "buy" else 55
    return SideScore(
        side=side,
        technical_signal_score=technical,
        technical_breakdown=_breakdown(side=side),
        evidence_score=70 if side == "buy" else 50,
        evidence_source="journal-v4",
        execution_quality_score=60,
        execution_quality_source="execution-v4",
        setup_score=setup,
        final_score=setup,
        reason_codes=(),
    )


def _check(name: str) -> GateCheck:
    return GateCheck(
        name=name,
        status="PASS",
        reason_codes=(),
        observed_value={"available": True, "samples": [1, 2]},
        threshold={"required": True},
        policy_version=SCANNER_SAFETY_POLICY_VERSION,
        checked_at=NOW,
        source=f"{name}-provider",
        provenance={"provider": {"name": name, "version": "v1"}},
    )


def _snapshot() -> CanonicalPairSnapshot:
    checks = tuple(
        _check(name)
        for name in ("connectivity", "data", "spread", "news", "volatility")
    )
    safety = MarketSafetyResult(
        status="PASS",
        checks=checks,
        reason_codes=(),
        policy_version=SCANNER_SAFETY_POLICY_VERSION,
    )
    assessment = MacroAssessment(
        raw_buy=8,
        raw_sell=4,
        confidence=0.8,
        status="aligned",
        correlation_context={"usd_index": {"direction": "down"}},
        provenance={
            "macro": {"source": "calendar-v4"},
            "event": {"source": "event-v4"},
        },
    )
    macro_gate = MacroGateResult(
        assessed_side="buy",
        status="PASS",
        decision_cap=None,
        reason_codes=(),
        policy_version=SCANNER_MACRO_POLICY_VERSION,
        checked_at=NOW,
        provenance={"assessment_id": "macro-1"},
    )
    decision = DecisionResult(
        selected_side="buy",
        score_gap=22,
        candidate_status="READY_NOW",
        decision_cap=None,
        gate_codes=("ALL_GATES_PASS",),
        reason_codes=("DECISION_READY_TO_TRADE",),
        block_codes=(),
    )
    return CanonicalPairSnapshot.create(
        snapshot_id="EURUSD-20260813T093000Z",
        symbol="EUR/USD",
        captured_at=NOW,
        side_scores=[_side("sell"), _side("buy")],
        market_safety=safety,
        macro_assessment=assessment,
        macro_gate=macro_gate,
        decision=decision,
        provenance={
            "capture": {"source": "pair-snapshot", "timestamps": [NOW.isoformat()]}
        },
    )


def _walk_keys(value: object) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            result.add(key)
            result.update(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_walk_keys(item))
    return result


def _assert_dict_and_json_invalid(
    payload: object,
    expected_code: str = SCANNER_SCHEMA_INVALID,
) -> None:
    encoded = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    dict_classification = classify_scanner_payload(payload)
    json_classification = classify_scanner_payload_json(encoded)
    assert dict_classification.kind == PAYLOAD_INVALID
    assert json_classification.kind == PAYLOAD_INVALID
    assert dict_classification.replayable is False
    assert json_classification.replayable is False
    assert dict_classification.reason_codes == (expected_code,)
    assert json_classification.reason_codes == (expected_code,)
    with pytest.raises(ScannerContractError) as dict_error:
        deserialize_canonical_pair_snapshot(payload)
    with pytest.raises(ScannerContractError) as model_dict_error:
        CanonicalPairSnapshot.from_dict(payload)
    with pytest.raises(ScannerContractError) as json_error:
        CanonicalPairSnapshot.from_json(encoded)
    assert dict_error.value.code == expected_code
    assert model_dict_error.value.code == expected_code
    assert json_error.value.code == expected_code


def test_target_versions_are_locked_without_activating_runtime_v3():
    assert SCANNER_SCORER_VERSION == "scanner-v3"
    assert SCANNER_FEATURE_VERSION == "scanner-features-v3"
    assert dict(SCANNER_VERSION_FIELDS) == {
        "scoring_version": "scanner",
        "feature_version": "scanner-features",
        "output_schema_version": "scanner-output",
        "safety_policy_version": "scanner-safety-policy",
        "macro_policy_version": "scanner-macro-policy",
        "ranking_version": "scanner-ranking",
        "snapshot_version": "scanner-pair-snapshot",
    }


def test_all_models_round_trip_without_data_loss():
    snapshot = _snapshot()
    component = snapshot.side_score("buy").technical_breakdown.trend
    breakdown = snapshot.side_score("buy").technical_breakdown
    side = snapshot.side_score("buy")
    check = snapshot.market_safety.checks[0]
    safety = snapshot.market_safety
    assessment = snapshot.macro_assessment
    macro_gate = snapshot.macro_gate
    decision = snapshot.decision

    assert TechnicalComponent.from_dict(component.to_dict()) == component
    assert TechnicalBreakdown.from_dict(breakdown.to_dict()) == breakdown
    assert SideScore.from_dict(side.to_dict()) == side
    assert GateCheck.from_dict(check.to_dict()) == check
    assert MarketSafetyResult.from_dict(safety.to_dict()) == safety
    assert MacroAssessment.from_dict(assessment.to_dict()) == assessment
    assert MacroGateResult.from_dict(macro_gate.to_dict()) == macro_gate
    assert DecisionResult.from_dict(decision.to_dict()) == decision
    assert validate_canonical_pair_snapshot(snapshot.to_dict()) == snapshot
    assert CanonicalPairSnapshot.from_json(snapshot.to_json()) == snapshot


def test_models_are_deeply_immutable_and_detached_from_creator_inputs():
    observed = {"available": True, "samples": [1, 2]}
    provenance = {"provider": {"name": "mt5"}}
    check = GateCheck(
        name="connectivity",
        status="PASS",
        reason_codes=(),
        observed_value=observed,
        threshold=None,
        policy_version=SCANNER_SAFETY_POLICY_VERSION,
        checked_at=NOW,
        source="mt5",
        provenance=provenance,
    )
    observed["available"] = False
    observed["samples"].append(3)
    provenance["provider"]["name"] = "mutated"

    assert check.observed_value["available"] is True
    assert check.observed_value["samples"] == (1, 2)
    assert check.provenance["provider"]["name"] == "mt5"
    with pytest.raises(FrozenInstanceError):
        check.status = "BLOCK"  # type: ignore[misc]
    with pytest.raises(TypeError):
        check.provenance["provider"]["name"] = "other"  # type: ignore[index]


def test_creator_stamps_exact_versions_and_payload_has_exact_canonical_blocks():
    snapshot = _snapshot()
    payload = serialize_canonical_pair_snapshot(snapshot)

    for field, expected in SCANNER_VERSION_FIELDS.items():
        assert payload[field] == expected
    assert set(payload) == set(SCANNER_VERSION_FIELDS) | {
        "snapshot_id",
        "symbol",
        "captured_at",
        "side_scores",
        "market_safety",
        "macro_assessment",
        "macro_gate",
        "decision",
        "provenance",
    }
    assert set(payload["side_scores"]) == {"buy", "sell"}
    assert set(payload["market_safety"]["checks"]) == {
        "connectivity",
        "data",
        "spread",
        "news",
        "volatility",
    }
    assert payload["side_scores"]["buy"]["final_score"] == payload[
        "side_scores"
    ]["buy"]["setup_score"]
    assert {"risk_condition", "macro_alignment"}.isdisjoint(_walk_keys(payload))
    assert classify_scanner_payload(payload).kind == PAYLOAD


@pytest.mark.parametrize("field", tuple(SCANNER_VERSION_FIELDS))
def test_missing_version_or_schema_fails_closed(field: str):
    payload = _snapshot().to_dict()
    del payload[field]

    classification = classify_scanner_payload(payload)
    assert classification.kind == PAYLOAD_INVALID
    assert classification.replayable is False
    assert classification.reason_codes == (SCANNER_VERSION_MISSING,)
    with pytest.raises(ScannerContractError) as exc_info:
        deserialize_canonical_pair_snapshot(payload)
    assert exc_info.value.code == SCANNER_VERSION_MISSING


@pytest.mark.parametrize("field", tuple(SCANNER_VERSION_FIELDS))
def test_mismatched_version_or_schema_fails_closed(field: str):
    payload = _snapshot().to_dict()
    payload[field] = f"{payload[field]}-mismatch"

    classification = classify_scanner_payload(payload)
    assert classification.kind == PAYLOAD_INVALID
    assert classification.replayable is False
    assert classification.reason_codes == (SCANNER_VERSION_MISMATCH,)
    with pytest.raises(ScannerContractError) as exc_info:
        deserialize_canonical_pair_snapshot(payload)
    assert exc_info.value.code == SCANNER_VERSION_MISMATCH


def test_blank_wrong_type_and_unknown_fields_fail_closed_without_coercion():
    blank = _snapshot().to_dict()
    blank["scoring_version"] = ""
    assert classify_scanner_payload(blank).reason_codes == (
        SCANNER_VERSION_MISSING,
    )

    wrong_type = _snapshot().to_dict()
    wrong_type["feature_version"] = ["scanner-features-v4"]
    classification = classify_scanner_payload(wrong_type)
    assert classification.kind == PAYLOAD_INVALID
    assert classification.reason_codes == (SCANNER_VERSION_MISMATCH,)

    unknown = _snapshot().to_dict()
    unknown["side_scores"]["buy"]["bonus"] = 3
    with pytest.raises(ScannerContractError) as exc_info:
        validate_canonical_pair_snapshot(unknown)
    assert exc_info.value.code == SCANNER_SCHEMA_INVALID


@pytest.mark.parametrize("forbidden", ["risk_condition", "macro_alignment"])
def test_forbidden_scored_fields_are_rejected_at_any_depth(forbidden: str):
    payload = _snapshot().to_dict()
    payload["side_scores"]["buy"]["technical_breakdown"][forbidden] = {
        "raw": 15
    }

    classification = classify_scanner_payload(payload)
    assert classification.kind == PAYLOAD_INVALID
    assert classification.audit_only is False
    assert classification.replayable is False
    assert classification.reason_codes == (SCANNER_FORBIDDEN_SCORED_FIELD,)
    with pytest.raises(ScannerContractError) as exc_info:
        deserialize_canonical_pair_snapshot(payload)
    assert exc_info.value.code == SCANNER_FORBIDDEN_SCORED_FIELD
    with pytest.raises(ScannerContractError) as json_error:
        CanonicalPairSnapshot.from_json(json.dumps(payload))
    assert json_error.value.code == SCANNER_FORBIDDEN_SCORED_FIELD


def test_explicit_v3_is_legacy_audit_only_non_replayable_and_not_relabelled():
    artifact = {
        "scorer_version": "scanner-v3",
        "feature_version": "scanner-features-v3",
        "scenario_scores": {
            "buy": {
                "signal_score": 80,
                "risk_condition": 12,
                "macro_alignment": 15,
            }
        },
    }
    before = deepcopy(artifact)

    classification = classify_scanner_payload(artifact)

    assert artifact == before
    assert classification.kind == PAYLOAD_LEGACY_V3
    assert classification.audit_only is True
    assert classification.replayable is False
    assert SCANNER_LEGACY_V3_AUDIT_ONLY in classification.reason_codes
    serialized_classification = classification.to_dict()
    assert serialized_classification["observed_versions"]["scoring_version"] == (
        "scanner-v3"
    )
    observed = serialized_classification["observed_versions"]
    assert SCANNER_SCORING_VERSION not in observed.values()
    assert SCANNER_V4_FEATURE_VERSION not in observed.values()
    with pytest.raises(ScannerContractError) as exc_info:
        deserialize_canonical_pair_snapshot(artifact)
    assert exc_info.value.code == SCANNER_LEGACY_V3_AUDIT_ONLY


def test_unversioned_payload_is_invalid_and_never_gets_defaults():
    payload = {"snapshot_id": "missing-versions", "side_scores": {}}
    before = deepcopy(payload)

    classification = classify_scanner_payload(payload)

    assert payload == before
    assert classification.kind == PAYLOAD_INVALID
    assert classification.audit_only is False
    assert classification.replayable is False
    assert classification.reason_codes == (SCANNER_VERSION_MISSING,)
    assert SCANNER_SCORING_VERSION not in str(classification.to_dict())
    assert SCANNER_V4_FEATURE_VERSION not in str(classification.to_dict())


def test_technical_unavailable_remains_none_in_canonical_payload():
    snapshot = _snapshot()
    payload = snapshot.to_dict()
    payload["side_scores"]["sell"] = _side("sell", unavailable=True).to_dict()
    payload["decision"].update({
        "selected_side": None,
        "score_gap": None,
        "candidate_status": "DATA_UNAVAILABLE",
    })
    payload["macro_gate"]["assessed_side"] = None
    payload["macro_gate"].update({
        "status": "UNKNOWN",
        "reason_codes": ["TECHNICAL_DATA_UNAVAILABLE"],
    })

    restored = validate_canonical_pair_snapshot(payload)

    sell = restored.side_score("sell")
    assert sell.technical_signal_score is None
    assert sell.setup_score is None
    assert sell.final_score is None
    assert sell.technical_breakdown.trend.raw is None


def test_score_types_and_final_alias_are_strict():
    boolean_score = _snapshot().to_dict()
    boolean_score["side_scores"]["buy"]["technical_signal_score"] = True
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(boolean_score)

    alias_mismatch = _snapshot().to_dict()
    alias_mismatch["side_scores"]["buy"]["final_score"] = 71
    with pytest.raises(ScannerContractError) as exc_info:
        validate_canonical_pair_snapshot(alias_mismatch)
    assert exc_info.value.code == SCANNER_SCHEMA_INVALID


def test_side_key_and_required_safety_checks_are_strict():
    wrong_side = _snapshot().to_dict()
    wrong_side["side_scores"]["buy"]["side"] = "sell"
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(wrong_side)

    missing_check = _snapshot().to_dict()
    del missing_check["market_safety"]["checks"]["news"]
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(missing_check)


def test_strict_json_rejects_duplicate_keys_and_non_finite_numbers():
    snapshot = _snapshot()
    duplicate = snapshot.to_json().replace(
        '"snapshot_id":"EURUSD-20260813T093000Z"',
        '"snapshot_id":"one","snapshot_id":"two"',
    )
    with pytest.raises(ScannerContractError) as duplicate_error:
        CanonicalPairSnapshot.from_json(duplicate)
    assert duplicate_error.value.code == SCANNER_SCHEMA_INVALID

    non_finite = snapshot.to_json().replace('"confidence":0.8', '"confidence":NaN')
    with pytest.raises(ScannerContractError) as finite_error:
        CanonicalPairSnapshot.from_json(non_finite)
    assert finite_error.value.code == SCANNER_SCHEMA_INVALID


def test_auxiliary_target_constants_match_payload_fields():
    payload = _snapshot().to_dict()
    assert payload["output_schema_version"] == SCANNER_OUTPUT_SCHEMA_VERSION
    assert payload["safety_policy_version"] == SCANNER_SAFETY_POLICY_VERSION
    assert payload["macro_policy_version"] == SCANNER_MACRO_POLICY_VERSION
    assert payload["ranking_version"] == SCANNER_V4_RANKING_VERSION
    assert payload["snapshot_version"] == SCANNER_SNAPSHOT_VERSION


def test_safety_aggregate_cannot_pass_or_caution_over_a_block_check():
    payload = _snapshot().to_dict()
    payload["market_safety"]["checks"]["spread"].update({
        "status": "BLOCK",
        "reason_codes": ["SPREAD_ABNORMAL"],
    })

    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(payload)

    payload["market_safety"]["status"] = "CAUTION"
    payload["market_safety"]["reason_codes"] = ["MARKET_SAFETY_CAUTION"]
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(payload)

    payload["market_safety"]["status"] = "BLOCK"
    payload["market_safety"]["reason_codes"] = ["SPREAD_ABNORMAL"]
    payload["decision"]["candidate_status"] = "BLOCKED"
    assert validate_canonical_pair_snapshot(payload).market_safety.status == "BLOCK"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("raw_buy", -1),
        ("raw_sell", 31),
        ("confidence", -0.01),
        ("confidence", 1.01),
    ],
)
def test_macro_ranges_are_strict(field: str, value: int | float):
    payload = _snapshot().to_dict()
    payload["macro_assessment"][field] = value
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(payload)


def test_snapshot_rejects_inconsistent_gap_macro_side_and_ready_without_side():
    gap = _snapshot().to_dict()
    gap["decision"]["score_gap"] = 99
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(gap)

    macro_side = _snapshot().to_dict()
    macro_side["macro_gate"]["assessed_side"] = "sell"
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(macro_side)

    no_side = _snapshot().to_dict()
    no_side["decision"]["selected_side"] = None
    no_side["macro_gate"]["assessed_side"] = None
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(no_side)

    lower_technical_side = _snapshot().to_dict()
    lower_technical_side["decision"]["selected_side"] = "sell"
    lower_technical_side["macro_gate"]["assessed_side"] = "sell"
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(lower_technical_side)


def test_external_python_only_containers_are_not_coerced_to_json():
    tuple_metadata = _snapshot().to_dict()
    tuple_metadata["provenance"] = {"values": (1, 2)}
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(tuple_metadata)

    proxy_payload = _snapshot().to_dict()
    proxy_payload["market_safety"]["checks"]["news"]["observed_value"] = (
        "no_event",
    )
    assert classify_scanner_payload(proxy_payload).kind == PAYLOAD_INVALID

    mixed_keys = _snapshot().to_dict()
    mixed_keys[1] = "not-json"
    mixed_keys["zzz"] = "unknown"
    assert classify_scanner_payload(mixed_keys).kind == PAYLOAD_INVALID
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(mixed_keys)

    surrogate_key = _snapshot().to_dict()
    surrogate_key["provenance"] = {"\ud800": 1}
    assert classify_scanner_payload(surrogate_key).kind == PAYLOAD_INVALID
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(surrogate_key)


def test_overflow_malformed_versions_and_parser_limits_fail_closed_typed():
    overflow = _snapshot().to_dict()
    overflow["macro_assessment"]["confidence"] = 10**10000
    classification = classify_scanner_payload(overflow)
    assert classification.kind == PAYLOAD_INVALID
    assert classification.replayable is False
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(overflow)

    malformed_version = _snapshot().to_dict()
    malformed_version["scoring_version"] = object()
    assert classify_scanner_payload(malformed_version).kind == PAYLOAD_INVALID

    with pytest.raises(ScannerContractError):
        CanonicalPairSnapshot.from_json("[" * 2000 + "0" + "]" * 2000)
    with pytest.raises(ScannerContractError):
        CanonicalPairSnapshot.from_json("{" + '"n":' + "9" * 5001 + "}")


def test_serializer_rejects_model_subclasses_and_revalidates_output():
    snapshot = _snapshot()

    class EvilSnapshot(CanonicalPairSnapshot):
        def to_dict(self) -> dict[str, object]:
            return {"scoring_version": "scanner-v3", "risk_condition": 100}

    evil = EvilSnapshot(
        *(getattr(snapshot, field.name) for field in fields(CanonicalPairSnapshot))
    )
    with pytest.raises(ScannerContractError):
        serialize_canonical_pair_snapshot(evil)


def test_creator_canonicalizes_all_timestamps_to_utc_for_stable_round_trip():
    local_time = NOW.astimezone(timezone(timedelta(hours=7)))
    snapshot = _snapshot()
    recreated = CanonicalPairSnapshot.create(
        snapshot_id=snapshot.snapshot_id,
        symbol=snapshot.symbol,
        captured_at=local_time,
        side_scores=list(snapshot.side_scores),
        market_safety=snapshot.market_safety,
        macro_assessment=snapshot.macro_assessment,
        macro_gate=snapshot.macro_gate,
        decision=snapshot.decision,
        provenance=snapshot.provenance,
    )

    assert recreated.captured_at.tzinfo is timezone.utc
    assert CanonicalPairSnapshot.from_json(recreated.to_json()) == recreated


def test_unavailable_technical_cannot_carry_valid_looking_raw_breakdown():
    payload = _snapshot().to_dict()
    payload["side_scores"]["sell"]["technical_signal_score"] = None
    payload["side_scores"]["sell"]["setup_score"] = None
    payload["side_scores"]["sell"]["final_score"] = None
    payload["decision"].update({
        "selected_side": None,
        "score_gap": None,
        "candidate_status": "DATA_UNAVAILABLE",
    })
    payload["macro_gate"]["assessed_side"] = None
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(payload)


def test_technical_weights_must_match_a_locked_regime_profile():
    payload = _snapshot().to_dict()
    weights = (1, 2, 3, 94)
    for name, weight in zip(("trend", "momentum", "location", "smc"), weights):
        payload["side_scores"]["buy"]["technical_breakdown"][name]["weight"] = weight
        payload["side_scores"]["buy"]["technical_breakdown"][name][
            "contribution"
        ] = 0.0
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(payload)


def test_technical_contribution_rejects_component_rounding():
    payload = _snapshot().to_dict()
    contribution = payload["side_scores"]["buy"]["technical_breakdown"]["smc"][
        "contribution"
    ]
    payload["side_scores"]["buy"]["technical_breakdown"]["smc"][
        "contribution"
    ] = round(contribution, 12)

    with pytest.raises(ScannerContractError) as exc_info:
        validate_canonical_pair_snapshot(payload)

    assert exc_info.value.path == "snapshot"


def test_technical_score_must_match_round_once_breakdown_sum():
    payload = _snapshot().to_dict()
    payload["side_scores"]["buy"]["technical_signal_score"] += 1
    payload["decision"]["score_gap"] += 1

    with pytest.raises(ScannerContractError) as exc_info:
        validate_canonical_pair_snapshot(payload)

    assert exc_info.value.path == "snapshot"


@pytest.mark.parametrize("assessment_status", ["conflict", "unknown"])
def test_macro_conflict_or_unknown_cannot_be_serialized_with_pass_gate(
    assessment_status: str,
):
    payload = _snapshot().to_dict()
    payload["macro_assessment"]["status"] = assessment_status
    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(payload)


@pytest.mark.parametrize("gate", ["market_safety", "macro_gate"])
@pytest.mark.parametrize("status", ["CAUTION", "BLOCK", "UNKNOWN"])
def test_nonpass_gate_cannot_be_overridden_by_ready_now(gate: str, status: str):
    payload = _snapshot().to_dict()
    payload[gate]["status"] = status
    payload[gate]["reason_codes"] = [f"{gate.upper()}_{status}"]
    if gate == "market_safety" and status == "BLOCK":
        payload["market_safety"]["checks"]["spread"].update({
            "status": "BLOCK",
            "reason_codes": ["SPREAD_ABNORMAL"],
        })

    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(payload)


@pytest.mark.parametrize("gate", ["market_safety", "macro_gate"])
def test_block_gate_requires_blocked_or_data_unavailable_decision(gate: str):
    payload = _snapshot().to_dict()
    payload[gate]["status"] = "BLOCK"
    payload[gate]["reason_codes"] = [f"{gate.upper()}_BLOCK"]
    if gate == "market_safety":
        payload["market_safety"]["checks"]["spread"].update({
            "status": "BLOCK",
            "reason_codes": ["SPREAD_ABNORMAL"],
        })
    payload["decision"]["candidate_status"] = "WATCH_ZONE"

    with pytest.raises(ScannerContractError):
        validate_canonical_pair_snapshot(payload)

    payload["decision"]["candidate_status"] = "BLOCKED"
    assert validate_canonical_pair_snapshot(payload).decision.candidate_status == (
        "BLOCKED"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("observed_value", None),
        ("provenance", {}),
    ],
)
def test_safety_check_missing_evidence_cannot_pass_or_reach_ready(
    field: str,
    value: object,
):
    payload = _snapshot().to_dict()
    payload["market_safety"]["checks"]["news"][field] = value

    _assert_dict_and_json_invalid(payload)


def test_missing_safety_evidence_is_representable_only_as_nonpass_nonready():
    payload = _snapshot().to_dict()
    payload["market_safety"]["checks"]["news"].update({
        "status": "UNKNOWN",
        "reason_codes": ["NEWS_DATA_UNAVAILABLE"],
        "observed_value": None,
        "provenance": {},
    })
    payload["market_safety"].update({
        "status": "UNKNOWN",
        "reason_codes": ["NEWS_DATA_UNAVAILABLE"],
    })
    payload["decision"]["candidate_status"] = "WATCH_ZONE"

    restored = validate_canonical_pair_snapshot(payload)
    assert restored.market_safety.status == "UNKNOWN"
    assert restored.decision.candidate_status != "READY_NOW"


@pytest.mark.parametrize("field", ["raw_buy", "raw_sell", "confidence"])
def test_missing_macro_values_cannot_be_aligned_pass_or_ready(field: str):
    payload = _snapshot().to_dict()
    payload["macro_assessment"][field] = None

    _assert_dict_and_json_invalid(payload)


def test_missing_macro_provenance_cannot_be_aligned_pass_or_ready():
    payload = _snapshot().to_dict()
    payload["macro_assessment"]["provenance"] = {}

    _assert_dict_and_json_invalid(payload)


def test_missing_macro_data_is_representable_only_as_unknown_nonready():
    payload = _snapshot().to_dict()
    payload["macro_assessment"].update({
        "raw_buy": None,
        "raw_sell": None,
        "confidence": None,
        "status": "unknown",
        "provenance": {},
    })
    payload["macro_gate"].update({
        "status": "UNKNOWN",
        "decision_cap": "WATCH_ZONE",
        "reason_codes": ["MACRO_DATA_UNAVAILABLE"],
    })
    payload["decision"].update({
        "candidate_status": "WATCH_ZONE",
        "decision_cap": "WATCH_ZONE",
    })

    restored = validate_canonical_pair_snapshot(payload)
    assert restored.macro_assessment.status == "unknown"
    assert restored.macro_gate.status == "UNKNOWN"
    assert restored.decision.candidate_status != "READY_NOW"


def test_macro_gate_side_is_required_and_must_exactly_match_selected_side():
    missing_side = _snapshot().to_dict()
    missing_side["macro_gate"]["assessed_side"] = None
    _assert_dict_and_json_invalid(missing_side)

    unselected = _snapshot().to_dict()
    unselected["decision"].update({
        "selected_side": None,
        "candidate_status": "WATCH_ZONE",
    })
    _assert_dict_and_json_invalid(unselected)


@pytest.mark.parametrize(
    "mutation",
    [
        "macro_gate_cap",
        "decision_cap",
        "decision_block_code",
    ],
)
def test_cap_or_block_code_cannot_coexist_with_ready_now(mutation: str):
    payload = _snapshot().to_dict()
    if mutation == "macro_gate_cap":
        payload["macro_gate"]["decision_cap"] = "WATCH_ZONE"
    elif mutation == "decision_cap":
        payload["decision"]["decision_cap"] = "WATCH_ZONE"
    else:
        payload["decision"]["block_codes"] = ["MACRO_BLOCK"]

    _assert_dict_and_json_invalid(payload)


@pytest.mark.parametrize(
    ("aggregate_status", "aggregate_reasons", "child_status", "child_reasons"),
    [
        ("UNKNOWN", ["SAFETY_UNKNOWN"], "PASS", []),
        ("BLOCK", ["SAFETY_BLOCK"], "PASS", []),
        ("CAUTION", ["SAFETY_CAUTION"], "UNKNOWN", ["NEWS_DATA_UNAVAILABLE"]),
    ],
)
def test_safety_aggregate_must_reflect_its_subchecks(
    aggregate_status: str,
    aggregate_reasons: list[str],
    child_status: str,
    child_reasons: list[str],
):
    payload = _snapshot().to_dict()
    payload["market_safety"].update({
        "status": aggregate_status,
        "reason_codes": aggregate_reasons,
    })
    payload["market_safety"]["checks"]["news"].update({
        "status": child_status,
        "reason_codes": child_reasons,
        "observed_value": None if child_status == "UNKNOWN" else {"events": []},
    })
    payload["decision"]["candidate_status"] = (
        "BLOCKED" if aggregate_status == "BLOCK" else "WATCH_ZONE"
    )

    _assert_dict_and_json_invalid(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        "scoring_v3",
        "feature_v3",
        "legacy_alias",
        "legacy_scoring_provenance",
        "legacy_snapshot_provenance",
    ],
)
def test_mixed_v3_identity_is_invalid_for_dict_and_json(mutate: str):
    payload = _snapshot().to_dict()
    if mutate == "scoring_v3":
        payload["scoring_version"] = "scanner-v3"
    elif mutate == "feature_v3":
        payload["feature_version"] = "scanner-features-v3"
    elif mutate == "legacy_alias":
        payload["scorer_version"] = "scanner-v3"
    elif mutate == "legacy_scoring_provenance":
        payload["scoring_provenance"] = {
            "scanner_scorer_version": "scanner-v3",
            "scanner_feature_version": "scanner-features-v3",
        }
    else:
        payload["provenance"]["scoring_version"] = "scanner-v3"

    _assert_dict_and_json_invalid(payload, SCANNER_VERSION_MISMATCH)


def test_malformed_scoring_marker_with_v3_shape_is_invalid_not_legacy():
    payload = {
        "scoring_version": "scanner-v4-malformed",
        "feature_version": "scanner-features-v4-malformed",
        "side_scores": {"buy": {"risk_condition": 10}},
        "decision": {},
    }

    _assert_dict_and_json_invalid(payload, SCANNER_VERSION_MISSING)


def test_snapshot_provenance_cannot_duplicate_contract_identity_even_when_equal():
    payload = _snapshot().to_dict()
    payload["provenance"]["scoring_version"] = SCANNER_SCORING_VERSION

    _assert_dict_and_json_invalid(payload)


@pytest.mark.parametrize(
    ("provenance_path", "identity_field", "identity_value"),
    [
        ("safety", "scoring_version", "scanner-v3"),
        ("macro_assessment", "scanner_scorer_version", "scanner-v3"),
        ("macro_gate", "output_schema_version", "bogus"),
        ("macro_gate", "scoring_provenance", {"source": "nested"}),
        ("safety", "scanner_contract_version", "phase0-safety-v1"),
    ],
)
def test_all_provenance_blocks_reject_duplicate_or_conflicting_identity(
    provenance_path: str,
    identity_field: str,
    identity_value: object,
):
    payload = _snapshot().to_dict()
    if provenance_path == "safety":
        provenance = payload["market_safety"]["checks"]["news"]["provenance"]
    else:
        provenance = payload[provenance_path]["provenance"]
    provenance["nested"] = {identity_field: identity_value}

    _assert_dict_and_json_invalid(payload)


def test_pure_v3_classification_and_reader_error_are_consistent_for_dict_and_json():
    artifact = {
        "scorer_version": "scanner-v3",
        "feature_version": "scanner-features-v3",
        "scenario_scores": {
            "buy": {"risk_condition": 10, "macro_alignment": 15},
        },
    }
    encoded = json.dumps(artifact)

    assert classify_scanner_payload(artifact).kind == PAYLOAD_LEGACY_V3
    assert classify_scanner_payload_json(encoded).kind == PAYLOAD_LEGACY_V3
    with pytest.raises(ScannerContractError) as dict_error:
        deserialize_canonical_pair_snapshot(artifact)
    with pytest.raises(ScannerContractError) as model_dict_error:
        CanonicalPairSnapshot.from_dict(artifact)
    with pytest.raises(ScannerContractError) as json_error:
        CanonicalPairSnapshot.from_json(encoded)
    assert dict_error.value.code == SCANNER_LEGACY_V3_AUDIT_ONLY
    assert model_dict_error.value.code == SCANNER_LEGACY_V3_AUDIT_ONLY
    assert json_error.value.code == SCANNER_LEGACY_V3_AUDIT_ONLY


def test_runtime_v3_side_scores_and_ranking_keys_remain_legacy_not_intent():
    artifact = {
        "scorer_version": "scanner-v3",
        "feature_version": "scanner-features-v3",
        "ranking_version": "phase6-ranking-v1",
        "side_scores": {"buy": {"signal_score": 72}},
    }

    assert classify_scanner_payload(artifact).kind == PAYLOAD_LEGACY_V3
    assert classify_scanner_payload_json(json.dumps(artifact)).kind == PAYLOAD_LEGACY_V3

    scoring_version_artifact = dict(artifact)
    scoring_version_artifact.pop("scorer_version")
    scoring_version_artifact["scoring_version"] = "scanner-v3"
    assert classify_scanner_payload(scoring_version_artifact).kind == PAYLOAD_LEGACY_V3


def test_non_object_legacy_signature_is_invalid_not_legacy():
    encoded = '[{"risk_condition":1}]'
    classification = classify_scanner_payload_json(encoded)
    assert classification.kind == PAYLOAD_INVALID
    assert classification.reason_codes == (SCANNER_SCHEMA_INVALID,)
    with pytest.raises(ScannerContractError) as exc_info:
        CanonicalPairSnapshot.from_json(encoded)
    assert exc_info.value.code == SCANNER_SCHEMA_INVALID


@pytest.mark.parametrize(
    "timestamp_path",
    ["captured_at", "safety_checked_at", "macro_checked_at"],
)
def test_timestamp_normalization_overflow_is_typed_and_fail_closed(
    timestamp_path: str,
):
    payload = _snapshot().to_dict()
    invalid_timestamp = "0001-01-01T00:00:00+14:00"
    if timestamp_path == "captured_at":
        payload["captured_at"] = invalid_timestamp
    elif timestamp_path == "safety_checked_at":
        payload["market_safety"]["checks"]["news"]["checked_at"] = invalid_timestamp
    else:
        payload["macro_gate"]["checked_at"] = invalid_timestamp

    _assert_dict_and_json_invalid(payload)
