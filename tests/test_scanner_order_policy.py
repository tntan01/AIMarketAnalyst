"""Scanner runtime order policy tests (Bước 12/13 config seam).

Proves the single owner-facing ``RuntimeOrderPolicy`` and its release wiring:

* default policy stays OPEN for safety/macro/portfolio/journal and therefore
  ``order_enabled is False`` (no real order can ever materialize while unset);
* the owner-approved DEFAULT threshold (40/35/5/2:1) is carried into the
  composition floors so the composition decision and the router agree;
* ``run_pair`` consumes the policy and, with the default policy, still fails
  closed to a BLOCKED candidate (behavior-identical to before the wire);
* filling every required layer via ``from_dict`` makes ``order_enabled`` True —
  derived only from owner-supplied input, never fabricated;
* ``to_dict``/``from_dict`` roundtrip with strict identity (rejects unknown/mixed
  version), and ``from_dict`` overrides only supplied keys (unset stays None).
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from core.scanner_order_policy import (
    DEFAULT_RUNTIME_ORDER_POLICY,
    ORDER_POLICY_VERSION,
    OrderPolicyError,
    RuntimeOrderPolicy,
    load_runtime_order_policy,
    update_threshold_policy_file,
)
from core.scanner_release import DEFAULT_THRESHOLD_POLICY, run_pair
from core.scanner_threshold_policy import (
    SCANNER_THRESHOLD_POLICY_VERSION,
    ThresholdPolicy,
)

from tests.test_scanner_composition import NOW, _snapshot


def _full_dict() -> dict:
    return {
        "order_policy_version": ORDER_POLICY_VERSION,
        "safety": {
            "policy_version": "scanner-safety-policy-v4",
            "connectivity_max_age_minutes": 2,
            "max_candle_age_minutes": 15,
            "spread_threshold_by_symbol": {"EURUSD": 25, "XAUUSD": 40},
            "volatility_upper_ratio": 2.0,
        },
        "macro": {
            "policy_version": "scanner-macro-policy-v4",
            "deadband_points": 3,
            "confidence_threshold": 0.7,
            "conflict_cap": "WATCH_ZONE",
            "unknown_cap": "DATA_UNAVAILABLE",
        },
        "portfolio_position_limit": 5,
        "portfolio_exposure_limit": 0.3,
        "journal_max_consecutive_losses": 3,
        "journal_drawdown_caution_ratio": 0.2,
    }


class TestDefaultPolicy:
    def test_default_order_disabled_fail_closed(self):
        assert DEFAULT_RUNTIME_ORDER_POLICY.order_enabled is False
        assert not DEFAULT_RUNTIME_ORDER_POLICY.certified()

    def test_default_threshold_is_owner_approved_default(self):
        p = DEFAULT_RUNTIME_ORDER_POLICY
        assert p.threshold.certified()
        assert p.threshold.technical_floor == 40
        assert p.threshold.setup_floor == 35
        assert p.threshold.min_score_gap == 5
        assert p.threshold.min_risk_reward == Fraction(2, 1)

    def test_default_safety_macro_portfolio_all_open(self):
        p = DEFAULT_RUNTIME_ORDER_POLICY
        assert p.safety.max_candle_age_minutes is None
        assert p.safety.spread_threshold_by_symbol == {}
        assert p.safety.volatility_calibrated is False
        assert p.macro.deadband_points is None
        assert p.macro.confidence_threshold is None
        assert p.portfolio_position_limit is None
        assert p.journal_max_consecutive_losses is None


class TestComposeOptionsMapping:
    def test_carries_dflt_threshold_floors_into_composition(self):
        opts = DEFAULT_RUNTIME_ORDER_POLICY.to_compose_options()
        assert opts.technical_floor == 40
        assert opts.setup_floor == 35
        assert opts.min_risk_reward == Fraction(2, 1)
        # portfolio/journal stay open in the default bundle.
        assert opts.portfolio_position_limit is None
        assert opts.journal_max_consecutive_losses is None


class TestReleaseWiring:
    def test_default_policy_still_fails_closed_to_blocked(self):
        # Behavior-identical: with the default (open) order policy the release
        # candidate stays BLOCKED — no real order path is unlocked.
        pair = run_pair(_snapshot(), now=NOW)
        assert pair.candidate is not None
        assert pair.candidate.candidate_status == "BLOCKED"
        assert pair.composition.decision.candidate_status == "BLOCKED"

    def test_accepts_explicit_order_policy_without_changing_shape(self):
        full = RuntimeOrderPolicy.from_dict(_full_dict())
        pair = run_pair(_snapshot(), now=NOW, order_policy=full)
        # The wiring consumed the policy (safety/macro/portfolio now configured);
        # it must NOT raise and still returns the exact-identity release pair.
        assert pair.row.to_dict().get("composition_version") == "scanner-composition"


class TestCertification:
    def test_full_policy_enables_order(self):
        full = RuntimeOrderPolicy.from_dict(_full_dict())
        assert full.order_enabled is True
        assert full.certified() is True


def _with_threshold_dict() -> dict:
    data = _full_dict()
    data["_accepted_by_owner"] = "owner note must survive"
    data["threshold"] = {
        "policy_version": SCANNER_THRESHOLD_POLICY_VERSION,
        "technical_floor": 40,
        "setup_floor": 35,
        "min_score_gap": 5,
        "min_risk_reward": "2/1",
    }
    return data


class TestUpdateThresholdPolicyFile:
    def test_writes_threshold_preserving_other_blocks(self, tmp_path):
        src = tmp_path / "policy.json"
        src.write_text(json.dumps(_with_threshold_dict()), encoding="utf-8")

        update_threshold_policy_file(
            technical_floor=45,
            setup_floor=40,
            min_score_gap=3,
            min_risk_reward=2.5,
            path=src,
        )
        data = json.loads(src.read_text(encoding="utf-8"))
        assert data["threshold"]["technical_floor"] == 45
        assert data["threshold"]["setup_floor"] == 40
        assert data["threshold"]["min_score_gap"] == 3
        assert data["threshold"]["min_risk_reward"] == "5/2"
        # Every other block + the owner note survive byte intact.
        assert data["_accepted_by_owner"] == "owner note must survive"
        assert data["safety"]["spread_threshold_by_symbol"]["XAUUSD"] == 40
        assert data["macro"]["confidence_threshold"] == 0.7
        assert data["portfolio_position_limit"] == 5
        # Reloads through the real loader with the new floors.
        policy = load_runtime_order_policy(path=src)
        assert policy.threshold.min_risk_reward == Fraction(5, 2)
        assert policy.threshold.setup_floor == 40
        assert policy.threshold.technical_floor == 45
        assert policy.threshold.certified()

    def test_partial_update_keeps_unsupplied_floors(self, tmp_path):
        src = tmp_path / "policy.json"
        src.write_text(json.dumps(_with_threshold_dict()), encoding="utf-8")

        update_threshold_policy_file(min_risk_reward=3, path=src)
        data = json.loads(src.read_text(encoding="utf-8"))
        assert data["threshold"]["min_risk_reward"] == "3"
        assert data["threshold"]["technical_floor"] == 40
        assert data["threshold"]["setup_floor"] == 35
        assert data["threshold"]["min_score_gap"] == 5

    def test_invalid_rr_raises_and_leaves_file_unchanged(self, tmp_path):
        src = tmp_path / "policy.json"
        original = json.dumps(_with_threshold_dict(), indent=2)
        src.write_text(original, encoding="utf-8")

        with pytest.raises(OrderPolicyError):
            update_threshold_policy_file(min_risk_reward=0, path=src)
        assert src.read_text(encoding="utf-8") == original

    def test_uncertified_policy_is_rejected(self, tmp_path):
        src = tmp_path / "policy.json"
        src.write_text(json.dumps(_with_threshold_dict()), encoding="utf-8")

        with pytest.raises(OrderPolicyError):
            update_threshold_policy_file(setup_floor=None, path=src)
        # Nothing written by the rejected save.
        data = json.loads(src.read_text(encoding="utf-8"))
        assert data["threshold"]["setup_floor"] == 35

    def test_rejects_garbage_threshold_block(self, tmp_path):
        src = tmp_path / "policy.json"
        src.write_text(json.dumps(_with_threshold_dict()), encoding="utf-8")

        with pytest.raises(OrderPolicyError):
            update_threshold_policy_file(technical_floor=999, path=src)
        assert json.loads(src.read_text(encoding="utf-8"))["threshold"]["technical_floor"] == 40

    def test_partial_safety_keeps_order_disabled(self):
        data = _full_dict()
        del data["macro"]
        partial = RuntimeOrderPolicy.from_dict(data)
        assert partial.order_enabled is False

    def test_missing_volatility_band_keeps_order_disabled(self):
        data = _full_dict()
        data["safety"].pop("volatility_upper_ratio")
        partial = RuntimeOrderPolicy.from_dict(data)
        assert partial.order_enabled is False
        assert partial.safety.volatility_calibrated is False


class TestSerialization:
    def test_roundtrip_default(self):
        policy = DEFAULT_RUNTIME_ORDER_POLICY
        rebuilt = RuntimeOrderPolicy.from_dict(policy.to_dict())
        assert rebuilt.to_dict() == policy.to_dict()
        assert rebuilt.order_enabled is False

    def test_roundtrip_full(self):
        full = RuntimeOrderPolicy.from_dict(_full_dict())
        rebuilt = RuntimeOrderPolicy.from_dict(full.to_dict())
        assert rebuilt.to_dict() == full.to_dict()
        assert rebuilt.order_enabled is True

    def test_to_dict_deterministic(self):
        full = RuntimeOrderPolicy.from_dict(_full_dict())
        assert full.to_dict() == full.to_dict()

    def test_rejects_unknown_version(self):
        with pytest.raises(OrderPolicyError):
            RuntimeOrderPolicy.from_dict(
                {"order_policy_version": "scanner-order-policy-v9"}
            )

    def test_rejects_malformed_policy_values(self):
        data = _full_dict()
        data["safety"]["spread_threshold_by_symbol"] = "bad"
        with pytest.raises(OrderPolicyError):
            RuntimeOrderPolicy.from_dict(data)

    def test_from_dict_only_overrides_supplied_keys(self):
        # Only safety given; macro/portfolio/journal must stay open (None).
        data = {
            "order_policy_version": ORDER_POLICY_VERSION,
            "safety": {
                "policy_version": "scanner-safety-policy-v4",
                "connectivity_max_age_minutes": 2,
                "max_candle_age_minutes": 15,
                "spread_threshold_by_symbol": {"EURUSD": 25},
                "volatility_upper_ratio": 2.0,
            },
        }
        partial = RuntimeOrderPolicy.from_dict(data)
        assert partial.safety.max_candle_age_minutes == 15
        assert partial.macro.deadband_points is None
        assert partial.portfolio_position_limit is None
        assert partial.order_enabled is False

    def test_threshold_rr_string_parsed(self):
        # A threshold-only policy keeps its owner default floors and parses the
        # R:R override; everything else stays open -> order remains disabled.
        data = {
            "order_policy_version": ORDER_POLICY_VERSION,
            "threshold": {
                "policy_version": "scanner-threshold-policy-v4",
                "min_risk_reward": "3/2",
            },
        }
        policy = RuntimeOrderPolicy.from_dict(data)
        assert policy.threshold.min_risk_reward == Fraction(3, 2)
        # Unset floors keep the owner default; safety/macro unset -> disabled.
        assert policy.threshold.technical_floor == 40
        assert policy.order_enabled is False


class TestTrialConfig:
    """The repo's order-policy config (config/scanner_order_policy.json).

    Owner-accepted LIVE values (promoted 2026-08-15 from the 2026-08-14 trial;
    rollout removed — docs/scanner/scanner-architecture.md §13.1).  The config
    must stay loadable and certified so the live path can gate on it; removing a
    mandatory layer must drop it back to blocked (fail-closed).
    """

    _CONFIG = Path(__file__).resolve().parents[1] / "config" / "scanner_order_policy.json"

    def test_config_file_is_present_and_loads(self):
        assert self._CONFIG.is_file(), "trial config file must exist"
        data = json.loads(self._CONFIG.read_text(encoding="utf-8"))
        policy = RuntimeOrderPolicy.from_dict(data)
        assert policy.order_enabled is True
        assert policy.certified() is True

    def test_config_keeps_owner_approved_threshold_floors(self):
        data = json.loads(self._CONFIG.read_text(encoding="utf-8"))
        policy = RuntimeOrderPolicy.from_dict(data)
        assert policy.threshold.technical_floor == 40
        assert policy.threshold.setup_floor == 35
        assert policy.threshold.min_risk_reward == Fraction(1, 1)

    def test_config_fails_closed_if_any_mandatory_value_is_removed(self):
        # Guard the fail-closed invariant on the persisted config: pulling out one
        # mandatory layer must drop the config back to BLOCKED (never silently open).
        data = json.loads(self._CONFIG.read_text(encoding="utf-8"))
        del data["macro"]
        policy = RuntimeOrderPolicy.from_dict(data)
        assert policy.order_enabled is False