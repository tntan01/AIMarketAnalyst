from __future__ import annotations

from core.decision_engine import (
    normalize_decision_cap,
)
from core.normalization import (
    normalize_choice,
    normalize_entry_status as normalize_decision_entry_status,
    normalize_scanner_entry_status,
)
from core.scanner_ranking_engine import normalize_decision


def test_normalize_choice_handles_valid_values_aliases_and_defaults():
    assert normalize_choice(" ready ", frozenset({"READY"}), case="upper") == "READY"
    assert normalize_choice("r", frozenset({"READY"}), aliases={"r": "READY"}, case="upper") == "READY"
    assert normalize_choice("none", frozenset({"READY"}), default=None, null_values=frozenset({"none"})) is None
    assert normalize_choice("", frozenset({"ready"}), default="unknown") == "unknown"
    assert normalize_choice(123, frozenset({"ready"}), default="unknown") == "unknown"


def test_decision_engine_decision_cap_preserves_existing_behavior():
    assert normalize_decision_cap("TRADE_BLOCKED") == "TRADE_BLOCKED"
    assert normalize_decision_cap("blocked") == "TRADE_BLOCKED"
    assert normalize_decision_cap("watch") == "WATCH_ONLY"
    assert normalize_decision_cap("wait") == "WAITING_CONFIRMATION"
    assert normalize_decision_cap("ready") == "READY_TO_TRADE"
    assert normalize_decision_cap("stand_aside") == "STAND_ASIDE"
    assert normalize_decision_cap("none") is None
    assert normalize_decision_cap("null") is None
    assert normalize_decision_cap("n/a") is None
    assert normalize_decision_cap("unknown") is None
    assert normalize_decision_cap(None) is None


def test_decision_engine_entry_status_excludes_scanner_only_values():
    assert normalize_decision_entry_status("confirmed_entry") == "confirmed_entry"
    assert normalize_decision_entry_status(" WAITING_CONFIRMATION ") == "waiting_confirmation"
    assert normalize_decision_entry_status("data_unavailable") == "unknown"
    assert normalize_decision_entry_status("bad") == "unknown"
    assert normalize_decision_entry_status(None) == "unknown"


def test_scanner_entry_status_includes_data_unavailable():
    assert normalize_scanner_entry_status("confirmed_entry") == "confirmed_entry"
    assert normalize_scanner_entry_status(" DATA_UNAVAILABLE ") == "data_unavailable"
    assert normalize_scanner_entry_status("bad") == "unknown"
    assert normalize_scanner_entry_status(None) == "unknown"


def test_scanner_decision_accepts_constants_and_legacy_aliases():
    assert normalize_decision("READY_TO_TRADE") == "READY_TO_TRADE"
    assert normalize_decision("ready") == "READY_TO_TRADE"
    assert normalize_decision("wait_for_confirmation") == "WAITING_CONFIRMATION"
    assert normalize_decision("skip") == "TRADE_BLOCKED"
    assert normalize_decision("blocked") == "TRADE_BLOCKED"
    assert normalize_decision("stand_aside") == "STAND_ASIDE"
    assert normalize_decision("bad") == ""
    assert normalize_decision(None) == ""
