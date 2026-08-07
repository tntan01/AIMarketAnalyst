"""Test Bước 7 — VIX Pair Sensitivity (core/vix_pair_backtest.py + core/correlation_check.py).

Bao phủ:
- Nhóm A: compute_vix_pair_sensitivity() — backtest engine
- Nhóm B: _vix_score() pair-aware — scoring logic
- Nhóm C: _load_vix_sensitivity() — map loading + fallback
- Nhóm D: is_sensitivity_map_stale() — re-validation
- Nhóm E: compute_correlation_adjustment() — integration
- Nhóm F: generate_seed_sensitivity_map() — seed data

KHÔNG hardcode "if JPY: bỏ phạt" — tất cả test dùng sensitivity_map fixture.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from core.market_models import Candle
from core.vix_pair_backtest import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_TTL_DAYS,
    MIN_LOOKBACK_DAYS,
    compute_vix_pair_sensitivity,
    generate_seed_sensitivity_map,
    get_vix_sensitivity_map,
    is_sensitivity_map_stale,
    load_sensitivity_map,
    lookup_pair_sensitivity,
    save_sensitivity_map,
)
from core.correlation_check import (
    _load_vix_sensitivity,
    _reset_vix_sensitivity_cache,
    _vix_score,
    compute_correlation_adjustment,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candles(closes: list[float], start_date: datetime | None = None) -> list[Candle]:
    """Tạo list Candle từ list close prices, mỗi candle cách nhau 1 ngày làm việc."""
    base = start_date or datetime(2026, 1, 5, tzinfo=UTC)  # Monday
    candles = []
    day_offset = 0
    for close in closes:
        t = base + timedelta(days=day_offset)
        day_offset += 1
        while t.weekday() >= 5:
            t = base + timedelta(days=day_offset)
            day_offset += 1
        candles.append(Candle(time=t, open=close, high=close, low=close, close=close, volume=0))
    return candles


def _vix_high() -> list[Candle]:
    """VIX > 25 (risk-off)."""
    return [Candle(time=datetime(2026, 8, 7, tzinfo=UTC), open=26, high=27, low=25, close=26.5)]


def _vix_medium() -> list[Candle]:
    """VIX 20-25 (căng thẳng)."""
    return [Candle(time=datetime(2026, 8, 7, tzinfo=UTC), open=22, high=23, low=21, close=22.0)]


def _vix_low() -> list[Candle]:
    """VIX < 15 (bình tĩnh)."""
    return [Candle(time=datetime(2026, 8, 7, tzinfo=UTC), open=13, high=14, low=12, close=13.0)]


def _vix_normal() -> list[Candle]:
    """VIX 15-20 (bình thường)."""
    return [Candle(time=datetime(2026, 8, 7, tzinfo=UTC), open=18, high=19, low=17, close=18.0)]


def _sample_sensitivity_map() -> dict:
    """Tạo sensitivity map mẫu (mini) cho testing."""
    return {
        "pairs": {
            "USD/JPY": {
                "correlation": -0.35,
                "sensitivity_factor": 0.3,
                "vix_direction": "falls_on_vix_up",
                "interpretation": "safe_haven",
                "note": "JPY safe haven — SELL benefits from risk-off.",
            },
            "AUD/USD": {
                "correlation": -0.45,
                "sensitivity_factor": 0.1,
                "vix_direction": "falls_on_vix_up",
                "interpretation": "safe_haven",
                "note": "AUD risk-on — SELL benefits from risk-off.",
            },
            "EUR/AUD": {
                "correlation": 0.35,
                "sensitivity_factor": 0.3,
                "vix_direction": "rises_on_vix_up",
                "interpretation": "risk_sensitive",
                "note": "AUD ở mẫu — BUY benefits from risk-off.",
            },
            "EUR/USD": {
                "correlation": -0.10,
                "sensitivity_factor": 0.8,
                "vix_direction": "indeterminate",
                "interpretation": "neutral",
                "note": "No clear VIX correlation.",
            },
            "AUD/JPY": {
                "correlation": -0.80,
                "sensitivity_factor": 0.0,
                "vix_direction": "falls_on_vix_up",
                "interpretation": "safe_haven",
                "note": "Both effects reinforce — SELL benefits strongly.",
            },
        }
    }


def _inject_sensitivity_map(monkeypatch, sensitivity_map: dict | None = None):
    """Inject sensitivity map vào module-level cache, bypass file I/O."""
    import core.correlation_check as cc

    cc._VIX_SENSITIVITY_LOADED = True
    if sensitivity_map is None:
        cc._VIX_SENSITIVITY_CACHE = {}
    else:
        cc._VIX_SENSITIVITY_CACHE = sensitivity_map.get("pairs", sensitivity_map)

    # Also patch _load_vix_sensitivity to return our injected data
    def _mock_load():
        if sensitivity_map is None:
            return {}
        return sensitivity_map.get("pairs", sensitivity_map)

    monkeypatch.setattr(cc, "_load_vix_sensitivity", _mock_load)


# ---------------------------------------------------------------------------
# Nhóm A: Backtest Engine
# ---------------------------------------------------------------------------


class TestComputeVixPairSensitivity:
    """Nhóm A: compute_vix_pair_sensitivity() — tính correlation từ data."""

    def test_correlation_safe_haven(self):
        """VIX↑ → USD/JPY↓ → correlation âm (safe haven)."""
        import random
        random.seed(123)
        # Generate 300 candles with random walk
        vix_close = 20.0
        pair_close = 150.0
        vix_candles = []
        pair_candles = []
        base = datetime(2026, 1, 5, tzinfo=UTC)
        day_offset = 0
        for _ in range(300):
            t = base + timedelta(days=day_offset)
            day_offset += 1
            while t.weekday() >= 5:
                t = base + timedelta(days=day_offset)
                day_offset += 1
            vix_change = random.gauss(0, 0.02)  # ~2% daily std
            vix_close = max(10, vix_close * (1 + vix_change))
            # Anti-correlated: VIX up → pair down
            pair_change = -0.5 * vix_change + random.gauss(0, 0.005)
            pair_close = max(50, pair_close * (1 + pair_change))
            vix_candles.append(Candle(time=t, open=vix_close, high=vix_close, low=vix_close, close=vix_close, volume=0))
            pair_candles.append(Candle(time=t, open=pair_close, high=pair_close, low=pair_close, close=pair_close, volume=0))

        result = compute_vix_pair_sensitivity(vix_candles, {"USD/JPY": pair_candles})
        pairs = result["pairs"]
        assert "USD/JPY" in pairs
        assert pairs["USD/JPY"]["correlation"] < -0.3  # strong negative
        assert pairs["USD/JPY"]["vix_direction"] == "falls_on_vix_up"
        assert pairs["USD/JPY"]["interpretation"] == "safe_haven"

    def test_correlation_risk_sensitive(self):
        """VIX↑ → AUD/USD↓ → correlation âm (risk-on currency yếu)."""
        import random
        random.seed(456)
        vix_close = 20.0
        pair_close = 0.70
        vix_candles = []
        pair_candles = []
        base = datetime(2026, 1, 5, tzinfo=UTC)
        day_offset = 0
        for _ in range(300):
            t = base + timedelta(days=day_offset)
            day_offset += 1
            while t.weekday() >= 5:
                t = base + timedelta(days=day_offset)
                day_offset += 1
            vix_change = random.gauss(0, 0.02)
            vix_close = max(10, vix_close * (1 + vix_change))
            # AUD/USD: risk-on, VIX↑ → AUD↓ → pair↓
            pair_change = -0.4 * vix_change + random.gauss(0, 0.005)
            pair_close = max(0.10, pair_close * (1 + pair_change))
            vix_candles.append(Candle(time=t, open=vix_close, high=vix_close, low=vix_close, close=vix_close, volume=0))
            pair_candles.append(Candle(time=t, open=pair_close, high=pair_close, low=pair_close, close=pair_close, volume=0))

        result = compute_vix_pair_sensitivity(vix_candles, {"AUD/USD": pair_candles})
        pairs = result["pairs"]
        assert pairs["AUD/USD"]["correlation"] < -0.25
        assert pairs["AUD/USD"]["vix_direction"] == "falls_on_vix_up"

    def test_correlation_neutral(self):
        """EUR/USD không tương quan với VIX."""
        vix = _make_candles([20 + i * 0.05 for i in range(300)])
        # EUR/USD: đi ngang (nhiễu)
        import random
        random.seed(42)
        eurusd = _make_candles([1.10 + random.gauss(0, 0.001) for _ in range(300)])

        result = compute_vix_pair_sensitivity(vix, {"EUR/USD": eurusd})
        pairs = result["pairs"]
        assert abs(pairs["EUR/USD"]["correlation"]) < 0.25
        assert pairs["EUR/USD"]["interpretation"] in ("neutral", "mild_safe_haven", "mild_risk_sensitive")

    def test_insufficient_vix_data(self):
        """Không đủ VIX data → warning."""
        vix = _make_candles([20.0] * 10)  # only 10 candles, < MIN_LOOKBACK_DAYS
        pair = _make_candles([1.10] * 10)

        result = compute_vix_pair_sensitivity(vix, {"EUR/USD": pair})
        assert result["meta"]["status"] == "insufficient_data"
        assert len(result["pairs"]) == 0
        assert len(result["warnings"]) > 0

    def test_insufficient_pair_data(self):
        """Cặp không đủ data → bỏ qua với note."""
        vix = _make_candles([20.0] * 300)
        pair = _make_candles([1.10] * 10)  # only 10 candles

        result = compute_vix_pair_sensitivity(vix, {"XXX/YYY": pair})
        assert "XXX/YYY" in result["pairs"]
        assert result["pairs"]["XXX/YYY"]["interpretation"] == "unknown"

    def test_multiple_pairs(self):
        """Nhiều cặp cùng lúc."""
        import random
        random.seed(789)
        vix_close = 20.0
        usdjpy_close = 150.0
        eurusd_close = 1.10
        audusd_close = 0.70
        vix_candles = []
        usdjpy_candles = []
        eurusd_candles = []
        audusd_candles = []
        base = datetime(2026, 1, 5, tzinfo=UTC)
        day_offset = 0
        for _ in range(300):
            t = base + timedelta(days=day_offset)
            day_offset += 1
            while t.weekday() >= 5:
                t = base + timedelta(days=day_offset)
                day_offset += 1
            vix_change = random.gauss(0, 0.02)
            vix_close = max(10, vix_close * (1 + vix_change))
            # JPY safe haven: VIX↑ → pair↓
            jpy_change = -0.5 * vix_change + random.gauss(0, 0.003)
            usdjpy_close = max(50, usdjpy_close * (1 + jpy_change))
            # EUR/USD: near-zero correlation
            eu_change = 0.05 * vix_change + random.gauss(0, 0.005)
            eurusd_close = max(0.50, eurusd_close * (1 + eu_change))
            # AUD risk-on: VIX↑ → pair↓
            au_change = -0.4 * vix_change + random.gauss(0, 0.005)
            audusd_close = max(0.10, audusd_close * (1 + au_change))
            vix_candles.append(Candle(time=t, open=vix_close, high=vix_close, low=vix_close, close=vix_close, volume=0))
            usdjpy_candles.append(Candle(time=t, open=usdjpy_close, high=usdjpy_close, low=usdjpy_close, close=usdjpy_close, volume=0))
            eurusd_candles.append(Candle(time=t, open=eurusd_close, high=eurusd_close, low=eurusd_close, close=eurusd_close, volume=0))
            audusd_candles.append(Candle(time=t, open=audusd_close, high=audusd_close, low=audusd_close, close=audusd_close, volume=0))

        result = compute_vix_pair_sensitivity(vix_candles, {
            "USD/JPY": usdjpy_candles,
            "EUR/USD": eurusd_candles,
            "AUD/USD": audusd_candles,
        })
        assert len(result["pairs"]) == 3
        corr_usdjpy = result["pairs"]["USD/JPY"]["correlation"]
        corr_audusd = result["pairs"]["AUD/USD"]["correlation"]
        assert corr_usdjpy < -0.2
        assert corr_audusd < -0.2

    def test_sensitivity_factor_range(self):
        """sensitivity_factor luôn trong [0, 1]."""
        vix = _make_candles([20 + i * 0.02 for i in range(300)])
        pairs_map = {
            "USD/JPY": _make_candles([150 - i * 0.03 for i in range(300)]),
        }
        result = compute_vix_pair_sensitivity(vix, pairs_map)
        factor = result["pairs"]["USD/JPY"]["sensitivity_factor"]
        assert 0.0 <= factor <= 1.0

    def test_meta_fields_present(self):
        """Meta có đủ các trường bắt buộc."""
        vix = _make_candles([20.0] * 300)
        pair = _make_candles([1.10] * 300)
        result = compute_vix_pair_sensitivity(vix, {"EUR/USD": pair})
        meta = result["meta"]
        assert "generated_at_utc" in meta
        assert "lookback_days" in meta
        assert "version" in meta
        assert "ttl_days" in meta


# ---------------------------------------------------------------------------
# Nhóm B: Pair-Aware VIX Scoring
# ---------------------------------------------------------------------------


class TestVixScorePairAware:
    """Nhóm B: _vix_score() với sensitivity map — điều chỉnh theo cặp + hướng."""

    def test_jpy_sell_reduced_penalty_high_vix(self, monkeypatch):
        """VIX>25, SELL USD/JPY → penalty giảm mạnh (safe haven flow)."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        result = _vix_score("USD/JPY", "sell", _vix_high())
        # USD/JPY: factor=0.3, SELL aligned → 0.3*0.3=0.09 → -5*0.09=-0.45→-0.5
        assert result > -1.0  # Much better than -5.0
        assert result < 0.0   # Still negative (penalty), but reduced

    def test_jpy_buy_still_penalized_high_vix(self, monkeypatch):
        """VIX>25, BUY USD/JPY → penalty vẫn còn (đi ngược safe haven flow)."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        result = _vix_score("USD/JPY", "buy", _vix_high())
        # BUY: not aligned → 0.3*0.8+0.2=0.44 → -5*0.44=-2.2
        assert result < -1.5  # Still penalized
        assert result > -3.0  # But less than full -5

    def test_aud_sell_reduced_penalty_high_vix(self, monkeypatch):
        """VIX>25, SELL AUD/USD → penalty giảm (risk-on, sell benefits)."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        result = _vix_score("AUD/USD", "sell", _vix_high())
        # AUD/USD: factor=0.1, SELL aligned → 0.1*0.3=0.03 → -5*0.03=-0.15→-0.2
        assert result > -1.0
        assert result <= 0.0

    def test_eur_aud_buy_reduced_penalty_high_vix(self, monkeypatch):
        """VIX>25, BUY EUR/AUD → penalty giảm (AUD yếu → EUR/AUD↑)."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        result = _vix_score("EUR/AUD", "buy", _vix_high())
        # EUR/AUD: factor=0.3, rises_on_vix_up, BUY aligned → 0.09 → -0.5
        assert result > -1.0
        assert result < 0.0

    def test_eur_aud_sell_still_penalized(self, monkeypatch):
        """VIX>25, SELL EUR/AUD → penalty gần như nguyên (đi ngược flow)."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        result = _vix_score("EUR/AUD", "sell", _vix_high())
        # SELL: not aligned → 0.3*0.8+0.2=0.44 → -5*0.44=-2.2
        assert result < -1.5

    def test_neutral_pair_near_flat_penalty(self, monkeypatch):
        """EUR/USD (indeterminate) → penalty gần như flat cũ."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        result_buy = _vix_score("EUR/USD", "buy", _vix_high())
        result_sell = _vix_score("EUR/USD", "sell", _vix_high())
        # EUR/USD: factor=0.8, indeterminate → 0.8*0.8+0.2=0.84 → -5*0.84=-4.2
        assert result_buy < -3.5  # Close to original -5
        assert result_sell < -3.5
        # Both sides should get same penalty for indeterminate pairs
        assert result_buy == result_sell

    def test_fallback_without_sensitivity_map(self, monkeypatch):
        """Không có sensitivity map → flat scoring cũ."""
        _inject_sensitivity_map(monkeypatch, None)
        result = _vix_score("USD/JPY", "sell", _vix_high())
        assert result == -5.0  # Original flat behavior
        result = _vix_score("EUR/USD", "buy", _vix_high())
        assert result == -5.0

    def test_unknown_pair_fallback(self, monkeypatch):
        """Cặp không có trong map → flat scoring."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        result = _vix_score("XXX/YYY", "buy", _vix_high())
        assert result == -5.0  # Unknown → flat

    def test_low_vix_bonus_not_modulated(self, monkeypatch):
        """VIX < 15 bonus không bị điều chỉnh (áp dụng cho mọi cặp)."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        # Bonus should be +2.0 for all pairs regardless of sensitivity
        assert _vix_score("USD/JPY", "sell", _vix_low()) == 2.0
        assert _vix_score("USD/JPY", "buy", _vix_low()) == 2.0
        assert _vix_score("AUD/USD", "sell", _vix_low()) == 2.0
        assert _vix_score("EUR/USD", "buy", _vix_low()) == 2.0

    def test_normal_vix_no_penalty(self, monkeypatch):
        """VIX 15-20 → không penalty."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        assert _vix_score("USD/JPY", "sell", _vix_normal()) == 0.0
        assert _vix_score("EUR/USD", "buy", _vix_normal()) == 0.0

    def test_medium_vix_reduced_penalty(self, monkeypatch):
        """VIX 20-25: base=-2, được giảm theo sensitivity."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        # USD/JPY SELL: factor=0.3, aligned → 0.09 → -2*0.09=-0.18→-0.2
        result = _vix_score("USD/JPY", "sell", _vix_medium())
        assert result > -0.5

    def test_empty_candles_returns_zero(self):
        """Không có candles → 0."""
        assert _vix_score("EUR/USD", "buy", []) == 0.0
        assert _vix_score("EUR/USD", "sell", None) == 0.0

    def test_zero_close_returns_zero(self):
        """Close = 0 → 0."""
        bad = [Candle(time=datetime(2026, 8, 7, tzinfo=UTC), open=0, high=0, low=0, close=0)]
        assert _vix_score("EUR/USD", "buy", bad) == 0.0

    def test_aud_jpy_fully_explained(self, monkeypatch):
        """AUD/JPY: factor=0.0 → SELL penalty triệt tiêu hoàn toàn."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        result = _vix_score("AUD/JPY", "sell", _vix_high())
        # factor=0.0, SELL aligned → 0.0*0.3=0.0 → -5*0.0=0.0
        assert result == 0.0

    def test_sell_vs_buy_asymmetry(self, monkeypatch):
        """Cùng cặp, SELL luôn ≤ BUY về penalty (falls_on_vix_up) hoặc ngược lại."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        # USD/JPY: falls_on_vix_up → SELL should be LESS penalized than BUY
        sell_penalty = _vix_score("USD/JPY", "sell", _vix_high())
        buy_penalty = _vix_score("USD/JPY", "buy", _vix_high())
        assert sell_penalty > buy_penalty  # SELL better (less negative)

        # EUR/AUD: rises_on_vix_up → BUY should be LESS penalized than SELL
        sell_penalty2 = _vix_score("EUR/AUD", "sell", _vix_high())
        buy_penalty2 = _vix_score("EUR/AUD", "buy", _vix_high())
        assert buy_penalty2 > sell_penalty2  # BUY better (less negative)


# ---------------------------------------------------------------------------
# Nhóm C: Sensitivity Map Loading
# ---------------------------------------------------------------------------


class TestSensitivityMapLoading:
    """Nhóm C: _load_vix_sensitivity() + file I/O."""

    def test_load_from_file(self, monkeypatch, tmp_path: Path):
        """Load sensitivity map từ file JSON."""
        import core.correlation_check as cc

        # Write test file
        test_data = {
            "meta": {"generated_at_utc": "2026-08-07T00:00:00Z", "ttl_days": 90},
            "pairs": {
                "EUR/USD": {"correlation": 0.0, "sensitivity_factor": 1.0,
                            "vix_direction": "indeterminate", "interpretation": "neutral",
                            "note": "test"},
            }
        }
        test_file = tmp_path / "vix_pair_sensitivity.json"
        test_file.write_text(json.dumps(test_data), "utf-8")

        # Patch the path resolution
        def _mock_paths():
            return [test_file]
        monkeypatch.setattr(cc.Path, "__init__", lambda self, *args: None)
        # Reset cache
        _reset_vix_sensitivity_cache()

        # Direct file loading test
        result = load_sensitivity_map(test_file, warn_stale=False)
        assert result is not None
        assert "EUR/USD" in result.get("pairs", {})

    def test_load_missing_file(self):
        """File không tồn tại → None."""
        result = load_sensitivity_map(Path("/nonexistent/path.json"), warn_stale=False)
        assert result is None

    def test_load_invalid_json(self, tmp_path: Path):
        """File JSON không hợp lệ → None."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json", "utf-8")
        result = load_sensitivity_map(bad_file, warn_stale=False)
        assert result is None

    def test_load_missing_pairs_key(self, tmp_path: Path):
        """JSON thiếu key 'pairs' → None."""
        bad_file = tmp_path / "no_pairs.json"
        bad_file.write_text('{"meta": {}}', "utf-8")
        result = load_sensitivity_map(bad_file, warn_stale=False)
        assert result is None

    def test_get_vix_sensitivity_map_auto_seed(self, tmp_path: Path):
        """get_vix_sensitivity_map() tự động tạo seed nếu file không tồn tại."""
        seed_path = tmp_path / "vix_pair_sensitivity.json"
        result = get_vix_sensitivity_map(seed_path, warn_stale=False, auto_generate_seed=True)
        assert result is not None
        assert "pairs" in result
        assert len(result["pairs"]) > 0
        # Seed file should have been created
        assert seed_path.exists()

    def test_lookup_pair_sensitivity_found(self):
        """Tra cứu cặp có trong map."""
        result = lookup_pair_sensitivity("USD/JPY", _sample_sensitivity_map())
        assert result["correlation"] == -0.35
        assert result["sensitivity_factor"] == 0.3
        assert result["vix_direction"] == "falls_on_vix_up"

    def test_lookup_pair_sensitivity_not_found(self):
        """Tra cứu cặp không có → default neutral (sensitivity_factor=1.0: full penalty)."""
        result = lookup_pair_sensitivity("XXX/YYY", _sample_sensitivity_map())
        assert result["correlation"] == 0.0
        # Default for unknown pairs: factor=1.0 (VIX is noise → keep full penalty)
        assert result["sensitivity_factor"] == 1.0
        assert result["vix_direction"] == "indeterminate"
        assert result["interpretation"] == "neutral"

    def test_lookup_pair_sensitivity_none_map(self):
        """Map=None → default neutral."""
        result = lookup_pair_sensitivity("EUR/USD", None)
        assert result["correlation"] == 0.0


# ---------------------------------------------------------------------------
# Nhóm D: Re-validation
# ---------------------------------------------------------------------------


class TestStalenessCheck:
    """Nhóm D: is_sensitivity_map_stale() — TTL check."""

    def test_fresh_map(self):
        """Map vừa tạo → không stale."""
        smap = {
            "meta": {
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "ttl_days": 90,
            },
            "pairs": {},
        }
        assert is_sensitivity_map_stale(smap) is False

    def test_stale_map(self):
        """Map quá hạn → stale."""
        smap = {
            "meta": {
                "generated_at_utc": "2025-01-01T00:00:00Z",
                "ttl_days": 90,
            },
            "pairs": {},
        }
        assert is_sensitivity_map_stale(smap) is True

    def test_seed_data_always_stale(self):
        """Seed data luôn được coi là stale."""
        smap = {
            "meta": {
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "ttl_days": 90,
                "is_seed": True,
            },
            "pairs": {},
        }
        assert is_sensitivity_map_stale(smap) is True

    def test_missing_meta_stale(self):
        """Thiếu meta → stale (fail-safe)."""
        assert is_sensitivity_map_stale({"pairs": {}}) is True

    def test_invalid_date_stale(self):
        """Ngày không parse được → stale."""
        smap = {
            "meta": {
                "generated_at_utc": "not-a-date",
                "ttl_days": 90,
            },
            "pairs": {},
        }
        assert is_sensitivity_map_stale(smap) is True

    def test_custom_now(self):
        """Dùng now tùy chỉnh để kiểm tra TTL."""
        now = datetime(2026, 8, 7, tzinfo=UTC)
        # Map generated 89 days ago, TTL=90 → still fresh
        fresh_date = (now - timedelta(days=89)).isoformat()
        smap = {"meta": {"generated_at_utc": fresh_date, "ttl_days": 90}, "pairs": {}}
        assert is_sensitivity_map_stale(smap, now=now) is False

        # Map generated 91 days ago, TTL=90 → stale
        stale_date = (now - timedelta(days=91)).isoformat()
        smap2 = {"meta": {"generated_at_utc": stale_date, "ttl_days": 90}, "pairs": {}}
        assert is_sensitivity_map_stale(smap2, now=now) is True


# ---------------------------------------------------------------------------
# Nhóm E: Integration — compute_correlation_adjustment
# ---------------------------------------------------------------------------


class TestCorrelationAdjustmentIntegration:
    """Nhóm E: compute_correlation_adjustment() với VIX pair-aware."""

    def test_adjustment_includes_pair_aware_vix(self, monkeypatch):
        """compute_correlation_adjustment truyền symbol+side vào _vix_score."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())

        # USD/JPY SELL: VIX>25 → penalty reduced
        result = compute_correlation_adjustment("USD/JPY", "sell", vix_candles=_vix_high())
        assert result > -5.0  # Reduced from -5
        assert result < 0.0

    def test_adjustment_no_vix_returns_zero(self):
        """Không có VIX candles → VIX không đóng góp."""
        result = compute_correlation_adjustment("EUR/USD", "buy")
        assert result == 0.0

    def test_adjustment_with_all_sources(self, monkeypatch):
        """Kết hợp DXY + US10Y + US2Y + VIX pair-aware."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())

        # Tạo mock DXY candles
        from core.market_models import Candle
        dxy = [Candle(time=datetime(2026, 8, 6, tzinfo=UTC), open=104, high=105, low=103, close=104),
               Candle(time=datetime(2026, 8, 7, tzinfo=UTC), open=104, high=106, low=103, close=105.5)]

        result = compute_correlation_adjustment(
            "EUR/USD", "buy",
            dxy_candles=dxy,
            vix_candles=_vix_high(),
        )
        # DXY contribution + VIX contribution
        # EUR/USD BUY với DXY up → SELL USD → BUY EUR/USD = against DXY → penalty
        assert result < 0.0  # Combined penalty

    def test_vix_outside_usd_clamp(self, monkeypatch):
        """VIX vẫn nằm ngoài USD cap [-6, +5]."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())

        # VIX only → pair-aware adjustment applied
        result = compute_correlation_adjustment("USD/JPY", "sell", vix_candles=_vix_high())
        # USD/JPY SELL: ~-0.4
        assert result > -1.0
        assert result <= 0.0

    def test_unknown_pair_no_sensitivity_effect(self, monkeypatch):
        """Cặp không có → flat VIX scoring trong adjustment."""
        _inject_sensitivity_map(monkeypatch, _sample_sensitivity_map())
        result = compute_correlation_adjustment("XXX/YYY", "buy", vix_candles=_vix_high())
        assert result == -5.0  # Flat


# ---------------------------------------------------------------------------
# Nhóm F: Seed Sensitivity Map
# ---------------------------------------------------------------------------


class TestSeedSensitivityMap:
    """Nhóm F: generate_seed_sensitivity_map() — seed data quality."""

    def test_generates_all_supported_pairs(self):
        """Seed map phủ tất cả các cặp trong SUPPORTED_SYMBOLS."""
        from config.constants import SUPPORTED_SYMBOLS
        seed = generate_seed_sensitivity_map()
        pairs = seed["pairs"]
        for sym in SUPPORTED_SYMBOLS:
            assert sym in pairs, f"Missing {sym} in seed map"

    def test_jpy_pairs_are_safe_haven(self):
        """Tất cả cặp JPY (quote) → falls_on_vix_up."""
        seed = generate_seed_sensitivity_map()
        pairs = seed["pairs"]
        for sym, data in pairs.items():
            if sym.endswith("/JPY") or sym.startswith("JPY/"):
                if sym == "CHF/JPY":
                    continue  # both safe havens → indeterminate
                # JPY ở quote (XXX/JPY): VIX↑ → JPY↑ → pair↓ → negative corr
                if sym.endswith("/JPY"):
                    assert data["correlation"] < -0.15, \
                        f"{sym}: expected negative corr, got {data['correlation']}"
                    assert data["vix_direction"] == "falls_on_vix_up", \
                        f"{sym}: expected falls_on_vix_up, got {data['vix_direction']}"

    def test_aud_nzd_pairs_risk_sensitive(self):
        """AUD/NZD base pairs → falls_on_vix_up (risk-on base weakens)."""
        seed = generate_seed_sensitivity_map()
        pairs = seed["pairs"]
        for sym, data in pairs.items():
            if sym.startswith("AUD/") and sym != "AUD/NZD":
                if sym.endswith("/JPY") or sym.endswith("/CHF"):
                    continue  # đã test ở trên
                # AUD as base: VIX↑ → AUD↓ → pair↓
                assert data["correlation"] <= -0.1, \
                    f"{sym}: AUD base should have negative corr, got {data['correlation']}"

    def test_seed_meta_has_is_seed(self):
        """Seed map có flag is_seed=True."""
        seed = generate_seed_sensitivity_map()
        assert seed["meta"]["is_seed"] is True

    def test_seed_sensitivity_factors_in_range(self):
        """Tất cả sensitivity_factor trong [0, 1]."""
        seed = generate_seed_sensitivity_map()
        for sym, data in seed["pairs"].items():
            factor = data["sensitivity_factor"]
            assert 0.0 <= factor <= 1.0, \
                f"{sym}: factor={factor} out of range [0, 1]"

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        """Ghi seed map ra file rồi đọc lại — dữ liệu nguyên vẹn."""
        seed = generate_seed_sensitivity_map()
        dest = tmp_path / "test_seed.json"
        saved = save_sensitivity_map(seed, dest)
        assert saved == dest
        assert dest.exists()

        loaded = load_sensitivity_map(dest, warn_stale=False)
        assert loaded is not None
        assert loaded["meta"]["is_seed"] is True
        assert len(loaded["pairs"]) == len(seed["pairs"])
        # Verify one key pair
        assert loaded["pairs"]["USD/JPY"]["correlation"] == seed["pairs"]["USD/JPY"]["correlation"]
