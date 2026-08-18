"""Scanner detail R:R display fallback tests.

Locks the detail-screen behavior where a scanner row may have entry data at
top level but R:R fields only inside ``analysis_result.scenarios``.
"""

from __future__ import annotations

from ui.screens.scanner_detail_screen import ScannerDetailScreen


def _screen(row: dict[str, object]) -> ScannerDetailScreen:
    screen = ScannerDetailScreen.__new__(ScannerDetailScreen)
    screen.row = row
    return screen


def test_detail_rr_falls_back_to_best_scenario_when_row_rr_missing():
    screen = _screen({
        "best_side": "buy",
        "entry_zone": [1.0950, 1.0970],
        "analysis_result": {
            "scenarios": [
                {
                    "type": "buy",
                    "entry_zone": [1.0950, 1.0970],
                    "risk_reward": "1:2.5",
                    "risk_reward_range": {"best": 2.5, "base": 1.8, "worst": 1.2},
                    "risk_reward_effective_range": {"best": 2.3, "base": 1.6, "worst": 1.0},
                    "expected_effective_rr": 2.3,
                    "expected_effective_rr_base": 1.6,
                }
            ],
        },
    })

    assert screen._rr_main_text() == "1:1.8"
    value, detail, _ = screen._dialog_card_rr()
    assert value == "1:1.8"
    assert "dải 1.2–2.5" in detail
    assert "base sau spread ~1.6" in detail
    assert screen._rr_field("risk_reward_range") == {"best": 2.5, "base": 1.8, "worst": 1.2}


def test_detail_rr_uses_matching_scenario_side():
    screen = _screen({
        "best_side": "sell",
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "risk_reward": "1:1.4"},
                {"type": "sell", "risk_reward": "1:2.2"},
            ],
        },
    })

    assert screen._rr_main_text() == "1:2.2"


def test_detail_rr_can_build_from_range_when_string_missing():
    screen = _screen({
        "entry_zone": [1.0950, 1.0970],
        "risk_reward_range": {"best": 2.4, "base": 1.7, "worst": 1.1},
    })

    # Base is the primary anchor now (best 2.4 is secondary).
    assert screen._rr_main_text() == "1:1.7"


def test_detail_rr_shows_na_when_entry_exists_but_no_tp_rr():
    screen = _screen({
        "entry_zone": [1.0950, 1.0970],
        "analysis_result": {"scenarios": [{"type": "buy", "entry_zone": [1.0950, 1.0970]}]},
    })

    assert screen._rr_main_text() == "N/A"
    value, detail, _ = screen._dialog_card_rr()
    assert value == "N/A"
    assert "Chưa có TP hợp lệ" in detail


def test_detail_checklist_rr_uses_scenario_rr_for_pass_fail():
    screen = _screen({
        "best_side": "buy",
        "best_score": 75,
        "score_gap": 20,
        "buy_score": 75,
        "sell_score": 55,
        "trade_permission": "allowed",
        "entry_status": "confirmed_entry",
        "m15_quality": "strict",
        "price_vs_zone": "in_zone",
        "min_rr": 1.3,
        "analysis_result": {
            "trade_gate": {"allowed": True, "reasons": []},
            "scenarios": [
                {
                    "type": "buy",
                    "entry_zone": [1.0950, 1.0970],
                    "risk_reward": "1:2.5",
                    "risk_reward_range": {"best": 2.5, "base": 1.8, "worst": 1.2},
                    "expected_effective_rr_base": 1.6,
                }
            ],
        },
    })

    items = screen._build_entry_checklist()
    rr_item = next(item for item in items if "R:R" in item["label"])
    assert rr_item["pass"] is True
    # Label shows the base anchor now (1.8), not the best case (2.5).
    assert "1:1.8" in rr_item["label"]
    assert "1:2.5" not in rr_item["label"]


def test_detail_rr_label_follows_actual_anchor():
    """When base is unavailable and the display falls back to the best-case
    string, the label must NOT claim '(base)'."""
    # No base anywhere -> best-case fallback, unlabeled
    screen = _screen({
        "best_side": "buy",
        "entry_zone": [1.0950, 1.0970],
        "analysis_result": {
            "scenarios": [
                {
                    "type": "buy",
                    "entry_zone": [1.0950, 1.0970],
                    "risk_reward": "1:2.5",
                }
            ],
        },
    })
    assert screen._rr_main_text() == "1:2.5"
    _, detail, _ = screen._dialog_card_rr()
    assert "(base)" not in detail
    assert "danh nghĩa 1:2.5" in detail

    # Base present -> labeled (base)
    screen_base = _screen({
        "best_side": "buy",
        "entry_zone": [1.0950, 1.0970],
        "analysis_result": {
            "scenarios": [
                {
                    "type": "buy",
                    "entry_zone": [1.0950, 1.0970],
                    "risk_reward": "1:2.5",
                    "risk_reward_range": {"best": 2.5, "base": 1.8, "worst": 1.2},
                }
            ],
        },
    })
    _, detail_base, _ = screen_base._dialog_card_rr()
    assert "danh nghĩa (base) 1:1.8" in detail_base


def test_detail_rr_candidate_label_follows_actual_anchor():
    """Candidate branch: best-case fallback must not be labeled '(base)'."""
    screen = _screen({
        "scanner_candidate_decision": {"selected_side": "buy", "strategy": {}},
        "analysis_result": {
            "scenarios": [
                {"type": "buy", "risk_reward": "1:2.5"},
            ],
        },
    })
    _, detail, _ = screen._dialog_card_rr()
    assert "(base)" not in detail
    assert "danh nghĩa 1:2.5" in detail


def test_number_rejects_non_finite():
    assert ScannerDetailScreen._number(float("nan")) is None
    assert ScannerDetailScreen._number(float("inf")) is None
    assert ScannerDetailScreen._number(float("-inf")) is None
    assert ScannerDetailScreen._number(1.5) == 1.5
    assert ScannerDetailScreen._number(None) is None


def test_rr_main_text_ignores_non_finite_range_values():
    screen = _screen({
        "entry_zone": [1.0950, 1.0970],
        "risk_reward_range": {"best": float("nan"), "base": None, "worst": 1.1},
        "risk_reward": "1:2.0",
    })
    # NaN best must not render as "1:nan"; falls back to the string.
    assert screen._rr_main_text() == "1:2.0"
