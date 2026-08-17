"""Scanner V4 runtime order policy tests (Bước 12/13 config seam).

Proves the single owner-facing ``RuntimeOrderPolicy`` and its release wiring:

* default policy stays OPEN for safety/macro/portfolio/journal and therefore
  ``order_enabled is False`` (no real order can ever materialize while unset);
* the owner-approved DEFAULT threshold (40/35/5/2:1) is carried into the
  composition floors so the composition decision and the router agree;
* ``run_v4_pair`` consumes the policy and, with the default policy, still fails
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

from core.scanner_v4_order_policy import (
    DEFAULT_RUNTIME_ORDER_POLICY,
    ORDER_POLICY_VERSION,
    OrderPolicyError,
    RuntimeOrderPolicy,
)
from core.scanner_v4_release import DEFAULT_THRESHOLD_POLICY, run_v4_pair

from tests.test_scanner_v4_composition import NOW, _snapshot


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
        pair = run_v4_pair(_snapshot(), now=NOW)
        assert pair.candidate is not None
        assert pair.candidate.candidate_status == "BLOCKED"
        assert pair.composition.decision.candidate_status == "BLOCKED"

    def test_accepts_explicit_order_policy_without_changing_shape(self):
        full = RuntimeOrderPolicy.from_dict(_full_dict())
        pair = run_v4_pair(_snapshot(), now=NOW, order_policy=full)
        # The wiring consumed the policy (safety/macro/portfolio now configured);
        # it must NOT raise and still returns the exact-identity release pair.
        assert pair.row.to_dict().get("composition_version") == "scanner-composition-v4"


class TestCertification:
    def test_full_policy_enables_order(self):
        full = RuntimeOrderPolicy.from_dict(_full_dict())
        assert full.order_enabled is True
        assert full.certified() is True

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
    """The repo's order-policy config (config/scanner_v4_order_policy.json).

    Owner-accepted LIVE values (promoted 2026-08-15 from the 2026-08-14 trial;
    rollout removed — docs/scanner/scanner-v4-architecture.md §13.1).  The config
    must stay loadable and certified so the live path can gate on it; removing a
    mandatory layer must drop it back to blocked (fail-closed).
    """

    _CONFIG = Path(__file__).resolve().parents[1] / "config" / "scanner_v4_order_policy.json"

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
        assert policy.threshold.min_risk_reward == Fraction(2, 1)

    def test_config_fails_closed_if_any_mandatory_value_is_removed(self):
        # Guard the fail-closed invariant on the persisted config: pulling out one
        # mandatory layer must drop the config back to BLOCKED (never silently open).
        data = json.loads(self._CONFIG.read_text(encoding="utf-8"))
        del data["macro"]
        policy = RuntimeOrderPolicy.from_dict(data)
        assert policy.order_enabled is False