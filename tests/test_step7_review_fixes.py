"""Regression tests for the Step 7 VIX pair-sensitivity review fixes.

These tests deliberately exercise the production loader instead of injecting its
module cache everywhere.  The synthetic market data is deterministic and does
not require network access.
"""

from __future__ import annotations

import json
import math
import os
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import core.correlation_check as correlation_check
from config.constants import APP_ID
from config.settings import AdvancedSettings
from core.market_models import Candle
from core.vix_pair_backtest import (
    MIN_LOOKBACK_DAYS,
    SENSITIVITY_SCHEMA_VERSION,
    compute_vix_pair_sensitivity,
)
from services.settings_service import SettingsService


@pytest.fixture(autouse=True)
def _isolate_vix_sensitivity_cache():
    """No Step 7 test may leak the module-level loader cache to another test."""
    correlation_check._reset_vix_sensitivity_cache()
    yield
    correlation_check._reset_vix_sensitivity_cache()


def _candles(
    closes: list[float],
    *,
    start: datetime | None = None,
    dates: list[datetime] | None = None,
) -> list[Candle]:
    start = start or datetime(2025, 1, 1, tzinfo=UTC)
    if dates is None:
        dates = [start + timedelta(days=index) for index in range(len(closes))]
    return [
        Candle(
            time=when,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=0.0,
        )
        for when, close in zip(dates, closes, strict=True)
    ]


def _closes_from_returns(
    returns: list[float],
    *,
    initial: float = 100.0,
) -> list[float]:
    closes = [initial]
    for change in returns:
        closes.append(closes[-1] * (1.0 + change))
    return closes


def _pct_changes(closes: list[float]) -> list[float]:
    return [
        (current - previous) / previous * 100.0
        for previous, current in zip(closes, closes[1:])
    ]


def _pearson(left: list[float], right: list[float]) -> float:
    assert len(left) == len(right)
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    numerator = sum(
        (x - mean_left) * (y - mean_right)
        for x, y in zip(left, right, strict=True)
    )
    denominator = math.sqrt(
        sum((x - mean_left) ** 2 for x in left)
        * sum((y - mean_right) ** 2 for y in right)
    )
    return numerator / denominator


def _fresh_map(
    *,
    factor: float = 0.2,
    correlation: float = -0.7,
    direction: str = "falls_on_vix_up",
    significant: bool = True,
    p_value: float = 0.001,
) -> dict:
    now = datetime.now(UTC)
    points = max(MIN_LOOKBACK_DAYS + 10, 130)
    actionable = significant and abs(correlation) > 0.15
    effective_factor = factor if actionable else 1.0
    effective_direction = direction if actionable else "indeterminate"
    return {
        "meta": {
            "generated_at_utc": now.isoformat(),
            "data_start": (now - timedelta(days=points + 30)).date().isoformat(),
            "data_end": now.date().isoformat(),
            "lookback_days": max(252, points + 1),
            "ttl_days": 90,
            "vix_data_points": points,
            "pair_count": 1,
            "validated_pair_count": 1,
            "actionable_pair_count": 1 if actionable else 0,
            "is_seed": False,
            "version": "2.0.0",
            "schema_version": SENSITIVITY_SCHEMA_VERSION,
            "status": "validated",
            "minimum_overlap_days": MIN_LOOKBACK_DAYS,
            "significance_alpha": 0.05,
            "alignment_method": "intersect_close_dates_before_returns",
            "methodology": "pearson_delta_vix_pct_vs_pair_return",
        },
        "pairs": {
            "USD/JPY": {
                "correlation": correlation,
                "p_value": p_value,
                "statistically_significant": significant,
                "actionable": actionable,
                "sensitivity_score": (
                    (-3.0 if correlation < 0 else 3.0) if actionable else 0.0
                ),
                "sensitivity_factor": effective_factor,
                "vix_direction": effective_direction,
                "interpretation": "directional" if actionable else "neutral",
                "note": "synthetic validated map",
                "data_points": points,
            }
        },
    }


def _write_map(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _high_vix() -> list[Candle]:
    return _candles([30.0])


# ---------------------------------------------------------------------------
# Backtest methodology: common-date alignment and statistical evidence
# ---------------------------------------------------------------------------


def test_minimum_lookback_is_long_enough_for_market_inference():
    assert MIN_LOOKBACK_DAYS >= 120


def test_backtest_aligns_by_date_instead_of_tail_position():
    count = max(MIN_LOOKBACK_DAYS + 30, 180)
    rng = random.Random(7301)
    returns = [rng.uniform(-0.025, 0.025) for _ in range(count - 1)]
    closes = _closes_from_returns(returns)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    vix_dates = [base + timedelta(days=index) for index in range(count)]
    pair_dates = [base + timedelta(days=index + 1) for index in range(count)]

    result = compute_vix_pair_sensitivity(
        _candles(closes, dates=vix_dates),
        {"TEST/PAIR": _candles(closes, dates=pair_dates)},
        lookback_days=count + 5,
    )
    pair = result["pairs"]["TEST/PAIR"]

    # The common dates contain VIX closes[1:] and pair closes[:-1].  Positional
    # tail alignment incorrectly compares the identical full return sequences
    # and reports r=1.0.
    expected = _pearson(
        _pct_changes(closes[1:]),
        _pct_changes(closes[:-1]),
    )
    assert pair["data_points"] == count - 2
    assert pair["correlation"] == pytest.approx(round(expected, 4), abs=1e-4)
    assert pair["correlation"] != pytest.approx(1.0)


def test_backtest_computes_both_returns_over_the_same_common_interval():
    count = max(MIN_LOOKBACK_DAYS + 30, 180)
    rng = random.Random(7302)
    closes = _closes_from_returns(
        [rng.uniform(-0.02, 0.02) for _ in range(count - 1)]
    )
    dates = [
        datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index)
        for index in range(count)
    ]
    missing_index = count // 2
    pair_closes = closes[:missing_index] + closes[missing_index + 1 :]
    pair_dates = dates[:missing_index] + dates[missing_index + 1 :]

    result = compute_vix_pair_sensitivity(
        _candles(closes, dates=dates),
        {"TEST/PAIR": _candles(pair_closes, dates=pair_dates)},
        lookback_days=count + 5,
    )
    pair = result["pairs"]["TEST/PAIR"]

    # Removing one date must make both assets use the same two-day interval
    # across that gap.  Joining independently calculated returns by endpoint
    # would compare a two-day pair return with a one-day VIX return.
    assert pair["data_points"] == count - 2
    assert pair["correlation"] == pytest.approx(1.0, abs=1e-4)


def test_backtest_emits_significance_evidence_for_strong_signal():
    count = max(MIN_LOOKBACK_DAYS + 30, 180)
    rng = random.Random(7303)
    vix_returns = [rng.gauss(0.0, 0.018) for _ in range(count - 1)]
    pair_returns = [
        -0.65 * change + rng.gauss(0.0, 0.001)
        for change in vix_returns
    ]

    result = compute_vix_pair_sensitivity(
        _candles(_closes_from_returns(vix_returns, initial=20.0)),
        {"USD/JPY": _candles(_closes_from_returns(pair_returns, initial=150.0))},
        lookback_days=count,
    )
    pair = result["pairs"]["USD/JPY"]

    assert pair["correlation"] < -0.8
    assert 0.0 <= pair["p_value"] <= 1.0
    assert pair["p_value"] < 0.05
    assert pair["statistically_significant"] is True
    assert pair["actionable"] is True


def test_non_significant_noise_is_neutral_not_a_live_directional_mapping():
    count = max(MIN_LOOKBACK_DAYS + 30, 180)
    vix_rng = random.Random(7304)
    pair_rng = random.Random(8304)
    vix_returns = [vix_rng.gauss(0.0, 0.018) for _ in range(count - 1)]
    pair_returns = [pair_rng.gauss(0.0, 0.006) for _ in range(count - 1)]

    result = compute_vix_pair_sensitivity(
        _candles(_closes_from_returns(vix_returns, initial=20.0)),
        {"EUR/USD": _candles(_closes_from_returns(pair_returns, initial=1.1))},
        lookback_days=count,
    )
    pair = result["pairs"]["EUR/USD"]

    assert pair["p_value"] > 0.05
    assert pair["statistically_significant"] is False
    assert pair["actionable"] is False
    assert pair["sensitivity_factor"] == 1.0
    assert pair["vix_direction"] == "indeterminate"


# ---------------------------------------------------------------------------
# Runtime loading: one canonical precedence, validation, and cache refresh
# ---------------------------------------------------------------------------


def test_runtime_candidates_prefer_mutable_appdata(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    candidates = correlation_check._vix_sensitivity_candidates()

    assert candidates
    assert candidates[0] == (
        tmp_path / "appdata" / APP_ID / "vix_pair_sensitivity.json"
    )


def test_production_loader_uses_first_valid_candidate(monkeypatch, tmp_path: Path):
    appdata_map = tmp_path / "appdata" / "vix_pair_sensitivity.json"
    repo_map = tmp_path / "repo" / "vix_pair_sensitivity.json"
    first = _fresh_map(factor=0.2)
    second = _fresh_map(factor=0.8)
    _write_map(appdata_map, first)
    _write_map(repo_map, second)
    monkeypatch.setattr(
        correlation_check,
        "_vix_sensitivity_candidates",
        lambda: [appdata_map, repo_map],
    )

    loaded = correlation_check._load_vix_sensitivity()

    assert loaded["USD/JPY"]["sensitivity_factor"] == 0.2


@pytest.mark.parametrize("invalid_kind", ["seed", "stale", "too_few_points"])
def test_production_loader_rejects_unvalidated_maps(
    monkeypatch,
    tmp_path: Path,
    invalid_kind: str,
):
    path = tmp_path / "vix_pair_sensitivity.json"
    payload = _fresh_map()
    if invalid_kind == "seed":
        payload["meta"]["is_seed"] = True
    elif invalid_kind == "stale":
        payload["meta"]["generated_at_utc"] = "2020-01-01T00:00:00+00:00"
    else:
        payload["meta"]["vix_data_points"] = MIN_LOOKBACK_DAYS - 1
        payload["pairs"]["USD/JPY"]["data_points"] = MIN_LOOKBACK_DAYS - 1
    _write_map(path, payload)
    monkeypatch.setattr(
        correlation_check,
        "_vix_sensitivity_candidates",
        lambda: [path],
    )

    assert correlation_check._load_vix_sensitivity() == {}


def test_non_significant_only_map_is_rejected_and_cannot_change_score(
    monkeypatch,
    tmp_path: Path,
):
    path = tmp_path / "vix_pair_sensitivity.json"
    _write_map(path, _fresh_map(significant=False, p_value=0.4))
    monkeypatch.setattr(
        correlation_check,
        "_vix_sensitivity_candidates",
        lambda: [path],
    )

    assert correlation_check._load_vix_sensitivity() == {}
    assert correlation_check._vix_score(
        "USD/JPY",
        "sell",
        _high_vix(),
        pair_aware_enabled=True,
    ) == -5.0


@pytest.mark.parametrize(
    "raw_content",
    [
        "not json",
        json.dumps({"meta": {}, "pairs": []}),
        json.dumps({"meta": {}, "pairs": {"USD/JPY": ["bad"]}}),
    ],
)
def test_production_loader_malformed_file_fails_open(
    monkeypatch,
    tmp_path: Path,
    raw_content: str,
):
    path = tmp_path / "vix_pair_sensitivity.json"
    path.write_text(raw_content, encoding="utf-8")
    monkeypatch.setattr(
        correlation_check,
        "_vix_sensitivity_candidates",
        lambda: [path],
    )

    assert correlation_check._load_vix_sensitivity() == {}


def test_production_loader_reloads_when_file_mtime_changes(
    monkeypatch,
    tmp_path: Path,
):
    path = tmp_path / "vix_pair_sensitivity.json"
    _write_map(path, _fresh_map(factor=0.2))
    monkeypatch.setattr(
        correlation_check,
        "_vix_sensitivity_candidates",
        lambda: [path],
    )
    first = correlation_check._load_vix_sensitivity()
    first_mtime_ns = path.stat().st_mtime_ns

    _write_map(path, _fresh_map(factor=0.7))
    changed_mtime_ns = first_mtime_ns + 2_000_000_000
    os.utime(path, ns=(changed_mtime_ns, changed_mtime_ns))
    second = correlation_check._load_vix_sensitivity()

    assert first["USD/JPY"]["sensitivity_factor"] == 0.2
    assert second["USD/JPY"]["sensitivity_factor"] == 0.7


# ---------------------------------------------------------------------------
# Live scoring: kill switch and monotonic side-aware penalty
# ---------------------------------------------------------------------------


def _inject_pair(monkeypatch, pair: dict) -> None:
    monkeypatch.setattr(
        correlation_check,
        "_load_vix_sensitivity",
        lambda: {"USD/JPY": pair},
    )


def _directional_pair(
    *,
    factor: float = 0.0,
    direction: str = "falls_on_vix_up",
) -> dict:
    return {
        "correlation": -0.8 if direction == "falls_on_vix_up" else 0.8,
        "p_value": 0.001,
        "statistically_significant": True,
        "actionable": True,
        "sensitivity_factor": factor,
        "vix_direction": direction,
        "data_points": max(MIN_LOOKBACK_DAYS + 10, 130),
    }


def test_pair_aware_flag_off_preserves_flat_penalty_without_loading(monkeypatch):
    def unexpected_load():
        raise AssertionError("disabled pair-aware scoring must not load a map")

    monkeypatch.setattr(
        correlation_check,
        "_load_vix_sensitivity",
        unexpected_load,
    )

    assert correlation_check._vix_score(
        "USD/JPY",
        "sell",
        _high_vix(),
        pair_aware_enabled=False,
    ) == -5.0


def test_aligned_trade_gets_reduced_penalty(monkeypatch):
    _inject_pair(monkeypatch, _directional_pair(factor=0.0))

    score = correlation_check._vix_score(
        "USD/JPY",
        "sell",
        _high_vix(),
        pair_aware_enabled=True,
    )

    assert -5.0 < score <= 0.0


def test_opposite_flow_is_never_penalized_less_than_flat_base(monkeypatch):
    _inject_pair(monkeypatch, _directional_pair(factor=0.0))

    score = correlation_check._vix_score(
        "USD/JPY",
        "buy",
        _high_vix(),
        pair_aware_enabled=True,
    )

    assert score <= -5.0


def test_indeterminate_pair_keeps_full_base_penalty(monkeypatch):
    _inject_pair(
        monkeypatch,
        {
            **_directional_pair(factor=0.0),
            "correlation": 0.0,
            "vix_direction": "indeterminate",
        },
    )

    buy = correlation_check._vix_score(
        "USD/JPY",
        "buy",
        _high_vix(),
        pair_aware_enabled=True,
    )
    sell = correlation_check._vix_score(
        "USD/JPY",
        "sell",
        _high_vix(),
        pair_aware_enabled=True,
    )

    assert buy == -5.0
    assert sell == -5.0


@pytest.mark.parametrize(
    "malformed_pair",
    [
        ["not", "a", "dict"],
        {"sensitivity_factor": "not-a-number", "vix_direction": "falls_on_vix_up"},
        {"sensitivity_factor": float("nan"), "vix_direction": "falls_on_vix_up"},
    ],
)
def test_malformed_pair_data_falls_back_to_flat_penalty(
    monkeypatch,
    malformed_pair,
):
    monkeypatch.setattr(
        correlation_check,
        "_load_vix_sensitivity",
        lambda: {"USD/JPY": malformed_pair},
    )

    assert correlation_check._vix_score(
        "USD/JPY",
        "sell",
        _high_vix(),
        pair_aware_enabled=True,
    ) == -5.0


def test_compute_adjustment_propagates_pair_aware_flag(monkeypatch):
    _inject_pair(monkeypatch, _directional_pair(factor=0.0))

    disabled = correlation_check.compute_correlation_adjustment(
        "USD/JPY",
        "sell",
        vix_candles=_high_vix(),
        vix_pair_aware_enabled=False,
    )
    enabled = correlation_check.compute_correlation_adjustment(
        "USD/JPY",
        "sell",
        vix_candles=_high_vix(),
        vix_pair_aware_enabled=True,
    )

    assert disabled == -5.0
    assert -5.0 < enabled <= 0.0


# ---------------------------------------------------------------------------
# Settings kill switch
# ---------------------------------------------------------------------------


def test_pair_aware_setting_defaults_off():
    assert AdvancedSettings().vix_pair_aware_enabled is False


def test_pair_aware_setting_roundtrips_through_settings_service(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    service = SettingsService(settings_path)
    settings = service.load()
    assert settings.advanced.vix_pair_aware_enabled is False

    settings.advanced.vix_pair_aware_enabled = True
    service.save(settings)

    assert SettingsService(settings_path).load().advanced.vix_pair_aware_enabled is True


def test_reset_vix_sensitivity_cache_clears_all_cached_state():
    correlation_check._VIX_SENSITIVITY_CACHE = {"USD/JPY": _directional_pair()}
    correlation_check._VIX_SENSITIVITY_LOADED = True

    correlation_check._reset_vix_sensitivity_cache()

    assert correlation_check._VIX_SENSITIVITY_CACHE is None
    assert correlation_check._VIX_SENSITIVITY_LOADED is False
