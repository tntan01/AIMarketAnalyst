"""Phase 15.2 — test import and basic behaviour of scanner_ranking_engine."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner_ranking_engine import (
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    BLOCKED,
    VALID_SCANNER_GROUPS,
    DEFAULT_OPPORTUNITY_WEIGHTS,
    SCANNER_GROUP_LABELS,
    default_opportunity_result,
    map_decision_to_scanner_group,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_valid_scanner_groups():
    assert READY_NOW in VALID_SCANNER_GROUPS
    assert BLOCKED in VALID_SCANNER_GROUPS
    assert len(VALID_SCANNER_GROUPS) == 4


def test_weights_has_final_score():
    assert "final_score" in DEFAULT_OPPORTUNITY_WEIGHTS
    assert DEFAULT_OPPORTUNITY_WEIGHTS["final_score"] == 1.0


def test_group_labels():
    assert SCANNER_GROUP_LABELS[READY_NOW] == "Sẵn sàng ngay"
    assert SCANNER_GROUP_LABELS[BLOCKED] == "Bị chặn"


# ---------------------------------------------------------------------------
# default_opportunity_result
# ---------------------------------------------------------------------------


def test_default_result():
    result = default_opportunity_result()
    assert result["opportunity_score"] == 0
    assert result["scanner_group"] == WATCH_ZONE
    assert isinstance(result["warning_codes"], list)
    assert isinstance(result["score_breakdown"], dict)


# ---------------------------------------------------------------------------
# map_decision_to_scanner_group
# ---------------------------------------------------------------------------


def test_map_ready():
    assert map_decision_to_scanner_group("READY_TO_TRADE") == READY_NOW


def test_map_waiting():
    assert map_decision_to_scanner_group("WAITING_CONFIRMATION") == WAITING_CONFIRMATION


def test_map_aggressive():
    assert map_decision_to_scanner_group("AGGRESSIVE_SETUP") == WAITING_CONFIRMATION


def test_map_watch():
    assert map_decision_to_scanner_group("WATCH_ONLY") == WATCH_ZONE


def test_map_stand_aside():
    assert map_decision_to_scanner_group("STAND_ASIDE") == WATCH_ZONE


def test_map_blocked():
    assert map_decision_to_scanner_group("TRADE_BLOCKED") == BLOCKED


def test_map_unknown():
    assert map_decision_to_scanner_group(None) == WATCH_ZONE
    assert map_decision_to_scanner_group("bogus") == WATCH_ZONE
