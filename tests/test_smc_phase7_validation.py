"""Phase-7 SMC replay, statistical validation and release-gate tests."""

from __future__ import annotations

from copy import deepcopy
import json

from core.scanner_observability import stable_hash
from core.smc_validation import (
    SMC_VALIDATION_CONTRACT_VERSION,
    build_smc_validation_report,
    replay_sample_from_analysis_document,
    replay_smc_cases,
)
from scripts.run_smc_validation import main as run_validation


def _zone(side: str) -> dict:
    is_buy = side == "buy"
    return {
        "zone_id": f"zone-{side}",
        "type": "demand_zone" if is_buy else "supply_zone",
        "family": "demand" if is_buy else "supply",
        "direction": side,
        "low": 90 if is_buy else 105,
        "high": 95 if is_buy else 110,
        "origin_index": 10,
        "origin_time": "2026-07-01T00:00:00+00:00",
        "departure_end_index": 11,
        "freshness_bars": 4,
        "age_bars": 4,
        "age_minutes": 960,
        "independent_retest_count": 0,
        "bars_spent_inside": 0,
        "mitigation_ratio": 0,
        "displacement_multiple": 2.0,
        "zone_location": "discount" if is_buy else "premium",
        "zone_quality_score": 75,
        "zone_setup_score": 75,
        "zone_score": 75,
    }


def _case(side: str, *, sample_id: str, split: str = "oos") -> dict:
    is_buy = side == "buy"
    structure = "HH/HL" if is_buy else "LH/LL"
    displacement = "bullish" if is_buy else "bearish"
    zone = _zone(side)
    return {
        "sample_id": sample_id,
        "dataset_split": split,
        "observed_at": "2026-07-01T00:00:00+00:00",
        "symbol": "EUR/USD",
        "asset_class": "forex",
        "side": side,
        "status": "WATCH_ZONE",
        "result_r": 0.5,
        "technical": {
            "price": 100,
            "atr_h4": 10,
            "support_zones": [{"level": 92.5}],
            "resistance_zones": [{"level": 107.5}],
        },
        "market_regime": {
            "primary": "trend_up" if is_buy else "trend_down",
        },
        "smc": {
            "symbol": "EUR/USD",
            "H4": {
                "structure": structure,
                "bos": True,
                "choch": False,
                "choch_confirmed": False,
                "displacement": displacement,
                "demand_zones": [zone] if is_buy else [],
                "supply_zones": [zone] if not is_buy else [],
                "order_blocks": [],
                "fvg": [],
            },
            "H1": {
                "structure": structure,
                "bos": True,
                "choch": False,
                "choch_confirmed": False,
                "displacement": displacement,
                "demand_zones": [],
                "supply_zones": [],
                "order_blocks": [],
                "fvg": [],
            },
            "confluence": {
                "buy_score": 5 if is_buy else 0,
                "sell_score": 0 if is_buy else 5,
            },
        },
    }


def _sample(
    sample_id: str,
    *,
    score: int,
    result_r: float,
    side: str = "buy",
    status: str = "READY_NOW",
    choch: bool = False,
    split: str = "oos",
    walk_forward_window: str = "wf-1",
) -> dict:
    opposite = "sell" if side == "buy" else "buy"
    return {
        "sample_id": sample_id,
        "dataset_split": split,
        "observed_at": "2026-07-01T00:00:00+00:00",
        "walk_forward_window": walk_forward_window,
        "symbol": "EUR/USD",
        "asset_class": "forex",
        "side": side,
        "market_regime": "trend_up" if side == "buy" else "trend_down",
        "zone_family": "demand" if side == "buy" else "supply",
        "zone_quality_score": score * 6,
        "zone_relevance_score": score * 6,
        "lifecycle_state": "fresh",
        "linked_sweep": score >= 10,
        "h4_confirmed_choch_against": choch,
        "scores": {side: score, opposite: 2},
        "selected_zone_id": f"zone-{sample_id}",
        "status": status,
        "result_r": result_r,
        "scoring_version": "smc-v2",
    }


def test_replay_runs_canonical_scorer_deterministically_without_mutating_inputs():
    cases = [_case("buy", sample_id="buy-1"), _case("sell", sample_id="sell-1")]
    before = stable_hash(cases)

    first = replay_smc_cases(cases)
    second = replay_smc_cases(deepcopy(cases))

    assert stable_hash(cases) == before
    assert stable_hash(first) == stable_hash(second)
    assert all(sample["valid"] for sample in first)
    assert all(
        0 <= score <= 15
        for sample in first
        for score in sample["scores"].values()
    )
    assert first[0]["scoring_version"] == "smc-v2"


def test_live_and_backtest_replay_use_identical_scorer_features():
    live = _case("buy", sample_id="same-input", split="live")
    backtest = deepcopy(live)
    backtest["sample_id"] = "same-input-oos"
    backtest["dataset_split"] = "oos"

    live_sample, backtest_sample = replay_smc_cases([live, backtest])

    assert live_sample["scores"] == backtest_sample["scores"]
    assert (
        live_sample["selected_zone_id"]
        == backtest_sample["selected_zone_id"]
    )
    assert live_sample["zone_quality_score"] == backtest_sample[
        "zone_quality_score"
    ]
    assert live_sample["zone_relevance_score"] == backtest_sample[
        "zone_relevance_score"
    ]


def test_validation_report_covers_replay_oos_calibration_and_strata():
    samples = [
        _sample(
            "low-1",
            score=5,
            result_r=-1,
            walk_forward_window="wf-1",
        ),
        _sample(
            "low-2",
            score=6,
            result_r=0,
            walk_forward_window="wf-2",
        ),
        _sample(
            "high-1",
            score=12,
            result_r=1,
            walk_forward_window="wf-1",
        ),
        _sample(
            "high-2",
            score=14,
            result_r=2,
            walk_forward_window="wf-2",
        ),
    ]

    report = build_smc_validation_report(
        samples,
        min_oos_samples=4,
        min_calibration_bucket_samples=2,
        min_walk_forward_windows=2,
        min_walk_forward_samples=2,
    )

    assert report["contract_version"] == SMC_VALIDATION_CONTRACT_VERSION
    assert report["scoring_version"] == "smc-v2"
    assert report["sample_count"] == 4
    assert report["release_gate"]["ready"] is True
    assert report["calibration"]["sample_guard_passed"] is True
    assert report["calibration"]["reasonable_relationship"] is True
    assert report["walk_forward"]["verdict"] == "ROBUST"
    assert report["oos"]["ready_sample_size"] == 4
    assert report["replay"]["score_distribution"]["0-3"] == 4
    assert report["replay"]["score_distribution"]["12-15"] == 2
    for field in (
        "symbol",
        "asset_class",
        "side",
        "market_regime",
        "zone_family",
        "quality_bucket",
        "relevance_bucket",
        "lifecycle_state",
        "linked_sweep",
        "h4_confirmed_choch_against",
        "scoring_version",
    ):
        assert field in report["stratification"]
    assert len(report["report_hash"]) == 64


def test_confirmed_h4_choch_can_never_pass_release_gate_as_ready():
    samples = [
        _sample(
            "safe-1",
            score=5,
            result_r=-1,
            walk_forward_window="wf-1",
        ),
        _sample(
            "safe-2",
            score=6,
            result_r=0,
            walk_forward_window="wf-2",
        ),
        _sample(
            "unsafe-1",
            score=12,
            result_r=1,
            choch=True,
            walk_forward_window="wf-1",
        ),
        _sample(
            "safe-3",
            score=14,
            result_r=2,
            walk_forward_window="wf-2",
        ),
    ]

    report = build_smc_validation_report(
        samples,
        min_oos_samples=4,
        min_calibration_bucket_samples=2,
        min_walk_forward_windows=2,
        min_walk_forward_samples=2,
    )

    assert report["replay"]["choch_against_ready_count"] == 1
    assert report["release_gate"]["ready"] is False
    assert "CHOCH_AGAINST_READY" in report["release_gate"][
        "block_reason_codes"
    ]


def test_losing_ready_samples_are_counted():
    losing = _sample(
        "losing-ready",
        score=8,
        result_r=-1,
        status="READY_NOW",
    )

    report = build_smc_validation_report(
        [losing],
        min_oos_samples=1,
        min_calibration_bucket_samples=1,
        min_walk_forward_windows=1,
        min_walk_forward_samples=1,
    )
    replay = report["replay"]

    assert replay["losing_ready_count"] == 1


def test_invalid_or_out_of_bounds_samples_fail_closed():
    invalid = _sample("bad-score", score=5, result_r=1)
    invalid["scores"]["buy"] = 99

    report = build_smc_validation_report(
        [invalid],
        min_oos_samples=1,
        min_calibration_bucket_samples=1,
    )

    assert report["sample_count"] == 0
    assert report["invalid_sample_count"] == 1
    assert "BUY_SCORE_INVALID" in report["invalid_samples"][0][
        "reason_codes"
    ]
    assert "INVALID_REPLAY_SAMPLE" in report["release_gate"][
        "block_reason_codes"
    ]


def test_unsupported_scorer_version_fails_closed():
    unsupported = _sample("v1-sample", score=12, result_r=1)
    unsupported["scoring_version"] = "smc-v1"

    report = build_smc_validation_report(
        [unsupported],
        min_oos_samples=1,
        min_calibration_bucket_samples=1,
    )

    assert report["sample_count"] == 0
    assert "SCORING_VERSION_UNSUPPORTED" in report["invalid_samples"][0][
        "reason_codes"
    ]
    assert "INVALID_REPLAY_SAMPLE" in report["release_gate"][
        "block_reason_codes"
    ]


def test_duplicate_sample_with_different_results_is_non_deterministic():
    first = _sample("duplicate", score=12, result_r=1)
    second = _sample("duplicate", score=12, result_r=-1)

    report = build_smc_validation_report(
        [first, second],
        min_oos_samples=1,
        min_calibration_bucket_samples=1,
    )

    assert report["duplicate_conflicts"] == ["duplicate"]
    assert "NON_DETERMINISTIC_DUPLICATE_SAMPLE" in report["release_gate"][
        "block_reason_codes"
    ]


def test_analysis_document_adapter_reads_canonical_sides():
    document = {
        "symbol": "EUR/USD",
        "scan_context": {
            "started_at": "2026-07-01T00:00:00+00:00",
        },
        "row_summary": {
            "row_id": "scan-1:EURUSD",
            "selected_side": "buy",
            "candidate_status": "WATCH_ZONE",
        },
        "candidate_decision": {
            "selected_side": "buy",
            "status": "WATCH_ZONE",
        },
        "analysis_result": {
            "market_regime": {"primary": "trend_up"},
            "smc": {"H4": {}, "H1": {}},
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
                    "sell": {
                        "score": 1,
                        "selected_zone_id": None,
                        "scoring_version": "smc-v2",
                    },
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

    sample = replay_sample_from_analysis_document(
        document,
        result_r=1.2,
        dataset_split="oos",
        asset_class="forex",
    )

    assert sample["valid"] is True
    assert sample["sample_id"] == "scan-1:EURUSD"
    assert sample["scores"] == {"buy": 12, "sell": 1}
    assert sample["selected_zone_id"] == "v2-zone"
    assert sample["linked_sweep"] is True
    assert sample["scoring_version"] == "smc-v2"


def test_calibration_and_stratification_use_only_oos_samples():
    samples = [
        _sample(
            "oos-low",
            score=5,
            result_r=-1,
            walk_forward_window="wf-1",
        ),
        _sample(
            "oos-high",
            score=12,
            result_r=2,
            walk_forward_window="wf-1",
        ),
        _sample(
            "train-high-loss",
            score=14,
            result_r=-10,
            split="train",
        ),
    ]

    report = build_smc_validation_report(
        samples,
        min_oos_samples=2,
        min_calibration_bucket_samples=1,
        min_walk_forward_windows=1,
        min_walk_forward_samples=2,
    )

    assert report["statistical_dataset_split"] == "oos"
    assert sum(
        bucket["sample_size"]
        for bucket in report["calibration"]["buckets"]
    ) == 2
    assert report["stratification"]["symbol"]["eur/usd"][
        "sample_size"
    ] == 2


def test_validation_cli_writes_deterministic_json_report(tmp_path):
    input_path = tmp_path / "samples.json"
    output_path = tmp_path / "report.json"
    input_path.write_text(
        json.dumps([
            _sample(
                "low-1",
                score=5,
                result_r=-1,
                walk_forward_window="wf-1",
            ),
            _sample(
                "low-2",
                score=6,
                result_r=0,
                walk_forward_window="wf-2",
            ),
            _sample(
                "high-1",
                score=12,
                result_r=1,
                walk_forward_window="wf-1",
            ),
            _sample(
                "high-2",
                score=14,
                result_r=2,
                walk_forward_window="wf-2",
            ),
        ]),
        encoding="utf-8",
    )

    exit_code = run_validation([
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--min-oos-samples",
        "4",
        "--min-bucket-samples",
        "2",
        "--min-walk-forward-windows",
        "2",
        "--min-walk-forward-samples",
        "2",
        "--fail-on-block",
    ])
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["release_gate"]["ready"] is True
    assert report["sample_count"] == 4
    assert len(report["report_hash"]) == 64
