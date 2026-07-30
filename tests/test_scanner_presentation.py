"""Unit tests for ui/scanner_presentation.py — presentation ordering."""

from __future__ import annotations

import copy

import pytest

from core.scanner_models import SCANNER_RANKING_VERSION
from ui.scanner_presentation import (
    PRESENTATION_ZONE_ORIGIN_PRIORITY,
    sort_scanner_rows_for_display,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(symbol, entry_zone_source, rank=1, **extra):
    return {"symbol": symbol, "entry_zone_source": entry_zone_source, "rank": rank, **extra}


# ---------------------------------------------------------------------------
# Baseline: function exists and returns list
# ---------------------------------------------------------------------------

def test_returns_empty_for_none():
    assert sort_scanner_rows_for_display(None) == []


def test_returns_empty_for_non_list():
    assert sort_scanner_rows_for_display("not_a_list") == []  # type: ignore[arg-type]
    assert sort_scanner_rows_for_display(42) == []  # type: ignore[arg-type]


def test_returns_empty_for_empty_list():
    assert sort_scanner_rows_for_display([]) == []


# ---------------------------------------------------------------------------
# Non-dict filtering
# ---------------------------------------------------------------------------

def test_filters_non_dict_items():
    rows = [
        _row("AAPL", "smc", rank=1),
        "not_a_dict",
        None,
        123,
        _row("MSFT", "fallback", rank=3),
    ]
    result = sort_scanner_rows_for_display(rows)  # type: ignore[list[dict]]
    assert len(result) == 2
    assert all(isinstance(r, dict) for r in result)


# ---------------------------------------------------------------------------
# Presentation order: smc → technical → fallback → none
# ---------------------------------------------------------------------------

def test_smc_before_technical_before_fallback_before_none():
    rows = [
        _row("F1", "fallback", rank=1),
        _row("T1", "technical", rank=2),
        _row("N1", None, rank=3),
        _row("S1", "smc_v2_selected", rank=4),
        _row("T2", "technical", rank=5),
        _row("S2", "smc", rank=6),
    ]
    result = sort_scanner_rows_for_display(rows)
    classes = [
        r["entry_zone_source"] if r["entry_zone_source"] else None
        for r in result
    ]
    # smc sources first
    assert classes[0] == "smc_v2_selected"
    assert classes[1] == "smc"
    # then technical
    assert classes[2] == "technical"
    assert classes[3] == "technical"
    # then fallback
    assert classes[4] == "fallback"
    # then none
    assert classes[5] is None


# ---------------------------------------------------------------------------
# Stable sort: relative order preserved within same class
# ---------------------------------------------------------------------------

def test_stable_sort_preserves_relative_order():
    rows = [
        _row("A", "smc", rank=5),
        _row("B", "technical", rank=1),
        _row("C", "smc", rank=30),
        _row("D", "technical", rank=7),
        _row("E", "fallback", rank=2),
        _row("F", "technical", rank=10),
        _row("G", "smc", rank=3),
        _row("H", "fallback", rank=8),
    ]
    result = sort_scanner_rows_for_display(rows)

    # smc group: A(5), C(30), G(3) — in input order
    smc_symbols = [r["symbol"] for r in result if r["entry_zone_source"] in ("smc",)]
    assert smc_symbols == ["A", "C", "G"]

    # technical group: B(1), D(7), F(10) — in input order
    tech_symbols = [r["symbol"] for r in result if r["entry_zone_source"] == "technical"]
    assert tech_symbols == ["B", "D", "F"]

    # fallback group: E(2), H(8) — in input order
    fb_symbols = [r["symbol"] for r in result if r["entry_zone_source"] == "fallback"]
    assert fb_symbols == ["E", "H"]


def test_raw_rank_preserved_across_presentation_reorder():
    """Technical rank=1 should appear after SMC rank=3, but both keep raw rank."""
    rows = [
        _row("TECH", "technical", rank=1),
        _row("SMC", "smc_v2_selected", rank=3),
    ]
    result = sort_scanner_rows_for_display(rows)
    assert result[0]["symbol"] == "SMC"
    assert result[0]["rank"] == 3
    assert result[1]["symbol"] == "TECH"
    assert result[1]["rank"] == 1


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

def test_input_list_not_mutated():
    rows = [
        _row("A", "fallback", rank=1),
        _row("B", "smc", rank=2),
    ]
    original = copy.deepcopy(rows)
    sort_scanner_rows_for_display(rows)
    assert rows == original


def test_input_dicts_not_mutated():
    rows = [
        _row("A", "fallback", rank=1),
        _row("B", "smc", rank=2),
    ]
    original_row = copy.deepcopy(rows[0])
    sort_scanner_rows_for_display(rows)
    assert rows[0] == original_row


def test_nested_payload_not_mutated():
    nested = {"key": "value", "list": [1, 2, 3]}
    rows = [
        {"symbol": "A", "entry_zone_source": "smc", "rank": 1, "nested": nested},
    ]
    original_nested = copy.deepcopy(nested)
    sort_scanner_rows_for_display(rows)
    assert rows[0]["nested"] == original_nested


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_missing_source_treated_as_none():
    rows = [
        _row("SMC", "smc", rank=1),
        _row("UNK", None, rank=2),
        _row("FALL", "fallback", rank=3),
    ]
    result = sort_scanner_rows_for_display(rows)
    sources = [r.get("entry_zone_source") for r in result]
    assert sources == ["smc", "fallback", None]


def test_unknown_source_treated_as_none():
    rows = [
        _row("SMC", "smc", rank=1),
        _row("WEIRD", "bogus_future_source_xyz", rank=2),
    ]
    result = sort_scanner_rows_for_display(rows)
    assert result[0]["symbol"] == "SMC"
    assert result[1]["symbol"] == "WEIRD"


def test_single_row():
    result = sort_scanner_rows_for_display([_row("ONLY", "fallback", rank=7)])
    assert len(result) == 1
    assert result[0]["symbol"] == "ONLY"


def test_all_same_class_preserves_order():
    rows = [
        _row("C", "smc", rank=50),
        _row("A", "smc_selected", rank=10),
        _row("B", "smc_distant", rank=30),
    ]
    result = sort_scanner_rows_for_display(rows)
    assert [r["symbol"] for r in result] == ["C", "A", "B"]


# ---------------------------------------------------------------------------
# Contract: SCANNER_RANKING_VERSION unchanged
# ---------------------------------------------------------------------------

def test_ranking_version_unchanged():
    assert SCANNER_RANKING_VERSION == "phase6-ranking-v1"


# ---------------------------------------------------------------------------
# Contract: priority dict has all four classes
# ---------------------------------------------------------------------------

def test_presentation_priority_covers_all_classes():
    assert set(PRESENTATION_ZONE_ORIGIN_PRIORITY.keys()) == {"smc", "technical", "fallback", "none"}
    assert PRESENTATION_ZONE_ORIGIN_PRIORITY["smc"] == 0
    assert PRESENTATION_ZONE_ORIGIN_PRIORITY["technical"] == 1
    assert PRESENTATION_ZONE_ORIGIN_PRIORITY["fallback"] == 2
    assert PRESENTATION_ZONE_ORIGIN_PRIORITY["none"] == 3


# ---------------------------------------------------------------------------
# Does NOT depend on PyQt
# ---------------------------------------------------------------------------

def test_module_has_no_pyqt_imports():
    import ui.scanner_presentation as mod
    with open(mod.__file__, encoding="utf-8") as fh:  # type: ignore[arg-type]
        content = fh.read()
    assert "import PyQt" not in content
    assert "from PyQt" not in content
    assert "import PySide" not in content
    assert "from PySide" not in content


# ---------------------------------------------------------------------------
# ScannerTableModel.set_rows() — presentation_rank contract
# ---------------------------------------------------------------------------


class TestSetRowsPresentationRank:
    """Verify set_rows() recalculates presentation_rank, preserves raw rank,
    and does not mutate source rows."""

    @staticmethod
    def _make_model():
        from ui.screens.scanner_screen import ScannerTableModel
        return ScannerTableModel()

    def test_presentation_rank_is_sequential_from_one(self):
        model = self._make_model()
        rows = [
            {"symbol": "C", "rank": 50},
            {"symbol": "A", "rank": 10},
            {"symbol": "B", "rank": 30},
        ]
        model.set_rows(rows)
        ranks = [r["presentation_rank"] for r in model.rows]
        assert ranks == [1, 2, 3]

    def test_raw_rank_preserved_after_set_rows(self):
        model = self._make_model()
        rows = [
            {"symbol": "C", "rank": 50},
            {"symbol": "A", "rank": 10},
        ]
        model.set_rows(rows)
        raw_ranks = [r["rank"] for r in model.rows]
        assert raw_ranks == [50, 10]

    def test_presentation_rank_stripped_from_caller(self):
        """Caller-injected presentation_rank must be ignored and recalculated."""
        model = self._make_model()
        rows = [
            {"symbol": "X", "rank": 5, "presentation_rank": 999},
            {"symbol": "Y", "rank": 3, "presentation_rank": 888},
        ]
        model.set_rows(rows)
        ranks = [r["presentation_rank"] for r in model.rows]
        assert ranks == [1, 2]

    def test_set_rows_recalculates_on_second_call(self):
        model = self._make_model()
        model.set_rows([{"symbol": "A", "rank": 1}])
        assert model.rows[0]["presentation_rank"] == 1

        model.set_rows([{"symbol": "B", "rank": 2}, {"symbol": "C", "rank": 3}])
        ranks = [r["presentation_rank"] for r in model.rows]
        assert ranks == [1, 2]

    def test_source_rows_not_mutated(self):
        model = self._make_model()
        source = {"symbol": "SRC", "rank": 7}
        model.set_rows([source])
        assert "presentation_rank" not in source

    def test_source_list_not_mutated(self):
        import copy
        model = self._make_model()
        source_rows = [
            {"symbol": "A", "rank": 1},
            {"symbol": "B", "rank": 2},
        ]
        original = copy.deepcopy(source_rows)
        model.set_rows(source_rows)
        assert source_rows == original

    def test_non_dict_filtered_before_numbering(self):
        model = self._make_model()
        rows = [
            {"symbol": "A", "rank": 1},
            "not_a_dict",
            {"symbol": "B", "rank": 2},
        ]
        model.set_rows(rows)  # type: ignore[arg-type]
        assert len(model.rows) == 2
        assert [r["presentation_rank"] for r in model.rows] == [1, 2]
        assert [r["symbol"] for r in model.rows] == ["A", "B"]
