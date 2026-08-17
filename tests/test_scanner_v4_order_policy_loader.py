"""Runtime loader for the owner's live order policy (Bước 13 "bước nối").

``load_runtime_order_policy`` is the ONLY runtime seam that reads
``config/scanner_v4_order_policy.json``. Its contract:

* the default path resolves to the committed config (repo-root anchored, never
  CWD-dependent);
* the owner's live config loads certified (``order_enabled is True``) with the
  exact accepted values;
* ANY load failure (missing file, bad JSON, invalid identity/values) raises
  ``OrderPolicyLoadError`` so the controller falls back to
  ``DEFAULT_RUNTIME_ORDER_POLICY`` whose ``order_enabled`` is False — a broken
  config can never open the live order workflow (fail-closed).
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from core.scanner_v4_order_policy import (
    DEFAULT_ORDER_POLICY_FILENAME,
    DEFAULT_RUNTIME_ORDER_POLICY,
    OrderPolicyError,
    OrderPolicyLoadError,
    load_runtime_order_policy,
)

CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "scanner_v4_order_policy.json"
)


class TestLiveConfigLoad:
    def test_default_path_resolves_to_committed_config(self):
        policy = load_runtime_order_policy()
        assert policy.order_enabled is True
        assert policy.certified() is True

    def test_default_path_is_repo_root_anchored(self):
        assert DEFAULT_ORDER_POLICY_FILENAME == "scanner_v4_order_policy.json"
        resolved = load_runtime_order_policy(CONFIG_PATH)
        assert resolved.to_dict() == load_runtime_order_policy().to_dict()

    def test_live_values_match_owner_accepted_config(self):
        policy = load_runtime_order_policy()
        # threshold (owner-approved floors, unchanged since Bước 07)
        assert policy.threshold.technical_floor == 40
        assert policy.threshold.setup_floor == 35
        assert policy.threshold.min_score_gap == 5
        assert policy.threshold.min_risk_reward == Fraction(2, 1)
        # safety
        assert policy.safety.connectivity_max_age_minutes == 5
        assert policy.safety.max_candle_age_minutes == 3
        # spread_threshold_by_symbol: owner accepted the FULL real-MT5 1.5x map
        # on 17/08/2026 (proposed by scripts/propose_spread_thresholds.py;
        # covers all 28 symbols present in Market Watch). Previously only
        # XAUUSD/EURUSD were configured; MISSING keys fail-closed BLOCK.
        assert dict(policy.safety.spread_threshold_by_symbol) == {
            "AUDCAD": 27,
            "AUDCHF": 14,
            "AUDJPY": 16,
            "AUDNZD": 27,
            "AUDUSD": 14,
            "BTCUSD": 1500,
            "CADJPY": 16,
            "CHFJPY": 32,
            "EURAUD": 26,
            "EURCAD": 22,
            "EURCHF": 24,
            "EURGBP": 20,
            "EURJPY": 24,
            "EURNZD": 33,
            "EURUSD": 12,
            "GBPAUD": 32,
            "GBPCAD": 27,
            "GBPCHF": 22,
            "GBPJPY": 33,
            "GBPNZD": 36,
            "GBPUSD": 15,
            "NZDJPY": 21,
            "NZDUSD": 21,
            "USDCAD": 21,
            "USDCHF": 20,
            "USDJPY": 15,
            "XAGUSD": 45,
            "XAUUSD": 390,
        }
        assert policy.safety.volatility_upper_ratio == 2.0
        assert policy.safety.volatility_calibrated is True
        # macro
        assert policy.macro.deadband_points == 3
        assert policy.macro.confidence_threshold == 0.6
        assert policy.macro.conflict_cap == "WATCH_ZONE"
        assert policy.macro.unknown_cap == "DATA_UNAVAILABLE"
        # portfolio / journal
        assert policy.portfolio_position_limit == 1
        assert policy.portfolio_exposure_limit == 0.3
        assert policy.journal_max_consecutive_losses == 3
        assert policy.journal_drawdown_caution_ratio == 0.1

    def test_unknown_marker_keys_are_ignored(self):
        # The governance markers (_accepted_by_owner / legacy _trial) must never
        # affect certification in either direction.
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        data["_accepted_by_owner"] = "ignored"
        data["_trial"] = "ignored"
        path = CONFIG_PATH.with_name("_loader_marker_probe.json")
        try:
            path.write_text(json.dumps(data), encoding="utf-8")
            assert load_runtime_order_policy(path).order_enabled is True
        finally:
            path.unlink(missing_ok=True)


class TestFailClosedLoad:
    def test_missing_file_raises_load_error(self, tmp_path):
        missing = tmp_path / "does-not-exist.json"
        with pytest.raises(OrderPolicyLoadError) as excinfo:
            load_runtime_order_policy(missing)
        assert str(missing) in excinfo.value.path

    def test_invalid_json_raises_load_error(self, tmp_path):
        broken = tmp_path / "broken.json"
        broken.write_text("{ not json", encoding="utf-8")
        with pytest.raises(OrderPolicyLoadError):
            load_runtime_order_policy(broken)

    def test_unknown_version_raises_load_error(self, tmp_path):
        bad_version = tmp_path / "bad-version.json"
        bad_version.write_text(
            json.dumps({"order_policy_version": "scanner-order-policy-v9"}),
            encoding="utf-8",
        )
        with pytest.raises(OrderPolicyLoadError):
            load_runtime_order_policy(bad_version)

    def test_load_error_is_an_order_policy_error(self):
        assert issubclass(OrderPolicyLoadError, OrderPolicyError)

    def test_fallback_default_policy_keeps_orders_blocked(self, tmp_path):
        # The controller contract: on OrderPolicyLoadError fall back to the
        # default policy -> order_enabled False -> every order stays blocked.
        with pytest.raises(OrderPolicyLoadError):
            load_runtime_order_policy(tmp_path / "missing.json")
        assert DEFAULT_RUNTIME_ORDER_POLICY.order_enabled is False


class TestConfigRegression:
    def test_removing_a_mandatory_layer_stays_loadable_but_blocked(self, tmp_path):
        # A reduced-but-valid config is NOT a load error: it loads and fails
        # closed via certified() == False.
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        del data["macro"]
        path = tmp_path / "reduced.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        policy = load_runtime_order_policy(path)
        assert policy.order_enabled is False
