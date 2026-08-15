"""Scanner V4 threshold policy (Bước 08; target-only, not live-wired yet).

A single versioned threshold contract owns, at the decision layer, exactly the
four confirmation criteria defined by the architecture (Mục 9 / Bước 08):

* ``technical_floor`` — minimum TechnicalSignalScore on the selected side,
* ``setup_floor`` — minimum SetupScore on the selected side,
* ``min_score_gap`` — minimum |buy - sell| technical gap,
* ``min_risk_reward`` — minimum scenario R:R of the selected side.

The composition (Bước 07) never certifies these criteria: its own floor check is
a fail-closed guard.  This contract is the single authority the candidate
decision layer reads; a strong score can never loosen it.

This is a personal single-owner application.  The values below are the **default
policy** chosen by the developer, not a PIT/OOS calibration.  They are honest
but un-calibrated defaults; the optional PIT calibration (Bước 09 infra) may
revisit them later, but that is never a blocker.  ``None`` means "policy open /
uncalibrated" and fails closed (never certifies a confirmation state).
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

SCANNER_V4_THRESHOLD_POLICY_VERSION = "scanner-threshold-policy-v4"


class ThresholdPolicyError(ValueError):
    """Typed misuse: a threshold policy is not shaped/versioned correctly."""

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"THRESHOLD_POLICY_INVALID at {path}: {detail}")


def _require_policy_version(value: object) -> str:
    if type(value) is not str or value != SCANNER_V4_THRESHOLD_POLICY_VERSION:
        raise ThresholdPolicyError(
            "policy_version",
            f"expected the locked Scanner V4 threshold policy version "
            f"{SCANNER_V4_THRESHOLD_POLICY_VERSION!r}",
        )
    return value


def _require_floor_or_none(value: object, path: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or isinstance(value, bool) or not 0 <= value <= 100:
        raise ThresholdPolicyError(path, "expected an integer in 0..100 or None")
    return value


def _require_gap_or_none(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or isinstance(value, bool) or not 0 <= value <= 100:
        raise ThresholdPolicyError(
            "min_score_gap", "expected an integer in 0..100 or None"
        )
    return value


def _require_rr_or_none(value: object) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        rr = Fraction(value)
    elif isinstance(value, Fraction):
        rr = value
    else:
        raise ThresholdPolicyError(
            "min_risk_reward", "expected a Fraction or int or None"
        )
    if rr <= 0:
        raise ThresholdPolicyError("min_risk_reward", "must be positive")
    return rr


@dataclass(frozen=True, slots=True)
class ThresholdPolicy:
    """Versioned decision-layer threshold contract (default policy).

    Every criterion is optional so the policy can stay "open" before
    calibration; ``None`` fails closed at the decision layer.
    """

    policy_version: str
    technical_floor: int | None
    setup_floor: int | None
    min_score_gap: int | None
    min_risk_reward: Fraction | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_version", _require_policy_version(self.policy_version))
        object.__setattr__(
            self, "technical_floor", _require_floor_or_none(self.technical_floor, "technical_floor")
        )
        object.__setattr__(
            self, "setup_floor", _require_floor_or_none(self.setup_floor, "setup_floor")
        )
        object.__setattr__(self, "min_score_gap", _require_gap_or_none(self.min_score_gap))
        object.__setattr__(self, "min_risk_reward", _require_rr_or_none(self.min_risk_reward))

    def certified(self) -> bool:
        """True only when every criterion has an explicit value.

        An uncertified contract can never promote a candidate: the decision
        layer must fail closed to ``WATCH_ZONE`` with ``V4_THRESHOLD_POLICY_OPEN``.
        """
        return (
            self.technical_floor is not None
            and self.setup_floor is not None
            and self.min_score_gap is not None
            and self.min_risk_reward is not None
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "technical_floor": self.technical_floor,
            "setup_floor": self.setup_floor,
            "min_score_gap": self.min_score_gap,
            "min_risk_reward": (
                None if self.min_risk_reward is None else str(self.min_risk_reward)
            ),
        }


def make_default_threshold_policy() -> ThresholdPolicy:
    """Explicit versioned default policy used by Bước 08 tests and docs.

    Values are the single-owner default (40/35/5/2-1) — honest, but NOT a PIT
    calibration.  The optional calibration harness may revisit them later
    without blocking completion of Bước 09/11.
    """
    return ThresholdPolicy(
        policy_version=SCANNER_V4_THRESHOLD_POLICY_VERSION,
        technical_floor=40,
        setup_floor=35,
        min_score_gap=5,
        min_risk_reward=Fraction(2, 1),
    )