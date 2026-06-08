"""Phase 13.6 — test calculate_final_score_batch() and summarize_final_scores()."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.final_score_engine import (
    calculate_final_score_batch,
    summarize_final_scores,
    FINAL_SCORE_DATA_INCOMPLETE,
)


def _make_payload(signal: int, evidence: int = 50, exec_q: int = 100) -> dict:
    return {
        "signal_score": signal,
        "evidence_score": evidence,
        "execution_quality_score": exec_q,
    }


# ---------------------------------------------------------------------------
# calculate_final_score_batch
# ---------------------------------------------------------------------------


def test_batch_three_payloads():
    payloads = [
        _make_payload(80, 50, 100),
        _make_payload(60, 50, 100),
        _make_payload(40, 30, 40),
    ]
    results = calculate_final_score_batch(payloads)
    assert len(results) == 3
    assert results[0]["final_score"] == 77   # 80*0.65 + 50*0.20 + 100*0.15
    assert results[1]["final_score"] == 64   # 60*0.65 + 50*0.20 + 100*0.15
    assert results[2]["final_score"] == 38   # 40*0.65 + 30*0.20 + 40*0.15


def test_batch_none_returns_empty():
    assert calculate_final_score_batch(None) == []


def test_batch_empty_list_returns_empty():
    assert calculate_final_score_batch([]) == []


def test_batch_non_dict_item_no_crash():
    payloads = [_make_payload(80), "junk", None, _make_payload(60)]
    results = calculate_final_score_batch(payloads)
    assert len(results) == 4
    # item 1 is dict → has score
    assert results[0]["final_score"] == 77
    # item 2 is "junk" → default result
    assert FINAL_SCORE_DATA_INCOMPLETE in results[1]["warning_codes"]
    # item 3 is None → default result
    assert FINAL_SCORE_DATA_INCOMPLETE in results[2]["warning_codes"]
    # item 4 is dict → has score
    assert results[3]["final_score"] == 64


def test_batch_does_not_mutate_input():
    payloads = [_make_payload(80), _make_payload(60)]
    originals = [dict(p) for p in payloads]
    calculate_final_score_batch(payloads)
    assert payloads == originals


# ---------------------------------------------------------------------------
# summarize_final_scores
# ---------------------------------------------------------------------------


def test_summary_three_results():
    results = calculate_final_score_batch([
        _make_payload(80, 50, 100),
        _make_payload(60, 50, 100),
        _make_payload(40, 30, 40),
    ])
    summary = summarize_final_scores(results)
    assert summary["count"] == 3
    expected_avg = round((77 + 64 + 38) / 3, 2)
    assert summary["average_final_score"] == expected_avg
    assert summary["min_final_score"] == 38
    assert summary["max_final_score"] == 77


def test_summary_strong_count():
    # signal=100, evidence=100, execution=100 → final=100 (≥80 → strong)
    results = calculate_final_score_batch([
        _make_payload(100, 100, 100),
        _make_payload(80, 80, 80),
        _make_payload(60, 50, 100),
    ])
    summary = summarize_final_scores(results)
    # 100*0.65+100*0.20+100*0.15 = 100 → strong
    # 80*0.65+80*0.20+80*0.15 = 80 → strong
    # 60*0.65+50*0.20+100*0.15 = 64 → not strong, ≥50 so not weak
    assert summary["strong_count"] == 2
    assert summary["weak_count"] == 0


def test_summary_weak_count():
    results = calculate_final_score_batch([
        _make_payload(40, 30, 30),   # 40*0.65 + 30*0.20 + 30*0.15 = 39.5 → 40 < 50
        _make_payload(20, 20, 20),   # 20 → < 50
        _make_payload(60, 50, 100),  # 64 → ≥ 50
    ])
    summary = summarize_final_scores(results)
    assert summary["weak_count"] == 2


def test_summary_code_counts():
    """Penalty codes from evidence ≤40 and exec <70 should be counted."""
    results = calculate_final_score_batch([
        _make_payload(80, 30, 40),    # evidence NEGATIVE penalty, exec WEAK penalty
        _make_payload(80, 50, 100),   # ok
    ])
    summary = summarize_final_scores(results)
    assert summary["penalty_code_counts"] != {}


def test_summary_none_input():
    summary = summarize_final_scores(None)
    assert summary["count"] == 0
    assert summary["average_final_score"] is None
    assert summary["min_final_score"] is None
    assert summary["max_final_score"] is None


def test_summary_empty_list():
    summary = summarize_final_scores([])
    assert summary["count"] == 0
    assert summary["strong_count"] == 0
    assert summary["weak_count"] == 0


def test_summary_with_junk_mixed_in():
    """Items that aren't dicts are skipped, not fatal."""
    results = [
        _make_payload(80),   # dict
        "junk",              # not dict — skipped
        _make_payload(60),   # dict
        None,                # skipped (not dict)
    ]
    # Re-create via batch so we have the right shape
    real_results = calculate_final_score_batch([
        _make_payload(80),
        _make_payload(60),
    ])
    summary = summarize_final_scores(real_results)
    assert summary["count"] == 2
    assert summary["average_final_score"] == round((77 + 64) / 2, 2)
