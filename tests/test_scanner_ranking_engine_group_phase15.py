"""Phase 15.4 — test classify_scanner_group()."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner_ranking_engine import (
    classify_scanner_group,
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    BLOCKED,
)


# ---- A. Gate block ----


def test_decision_blocked():
    assert classify_scanner_group(decision="TRADE_BLOCKED") == BLOCKED


def test_scanner_action_skip():
    assert classify_scanner_group(scanner_action="skip") == BLOCKED


def test_trade_permission_blocked():
    assert classify_scanner_group(
        trade_permission={"status": "blocked"},
        decision="READY_TO_TRADE",
    ) == BLOCKED


def test_trade_permission_blocked_str():
    assert classify_scanner_group(trade_permission="blocked") == BLOCKED


# ---- B/C. READY ----


def test_decision_ready():
    assert classify_scanner_group(decision="READY_TO_TRADE") == READY_NOW


def test_scanner_action_ready_with_ready_to_trade():
    assert classify_scanner_group(
        scanner_action="ready",
        ready_to_trade=True,
    ) == READY_NOW


def test_scanner_action_ready_without_ready():
    assert classify_scanner_group(
        scanner_action="ready",
        ready_to_trade=False,
    ) == WATCH_ZONE  # falls through to fallback


# ---- D/E. WAITING ----


def test_decision_waiting():
    assert classify_scanner_group(decision="WAITING_CONFIRMATION") == WAITING_CONFIRMATION


def test_scanner_action_wait():
    assert classify_scanner_group(scanner_action="wait") == WAITING_CONFIRMATION


def test_entry_waiting():
    assert classify_scanner_group(entry_status="waiting_confirmation") == WAITING_CONFIRMATION


# ---- F/G. WATCH ----


def test_decision_watch():
    assert classify_scanner_group(decision="WATCH_ONLY") == WATCH_ZONE


def test_scanner_action_watch():
    assert classify_scanner_group(scanner_action="watch") == WATCH_ZONE


def test_entry_watch_zone():
    assert classify_scanner_group(entry_status="watch_zone") == WATCH_ZONE


# ---- H. No trade ----


def test_entry_invalidated():
    assert classify_scanner_group(entry_status="invalidated") == BLOCKED


def test_entry_no_setup():
    assert classify_scanner_group(entry_status="no_setup") == BLOCKED


def test_entry_data_unavailable():
    assert classify_scanner_group(entry_status="data_unavailable") == BLOCKED


# ---- I. Fallback ----


def test_fallback_watch():
    assert classify_scanner_group() == WATCH_ZONE


def test_legacy_mapping():
    """Legacy action strings are mapped correctly."""
    assert classify_scanner_group(decision="ready") == READY_NOW
    assert classify_scanner_group(decision="blocked") == BLOCKED
