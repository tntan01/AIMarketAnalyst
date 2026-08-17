"""Scanner V4 runtime order policy — single owner config seam (Bước 12/13).

A personal single-owner application: the numbers that decide whether the live
order workflow may open a real order are the owner's, never fabricated by code.
This module is the ONE place the runtime binds the three policy layers the
composition consumes (``SafetyPolicy`` + ``MacroPolicy`` + ``ComposeOptions``)
so that, once the owner fills the values, the live path unlocks — and while
anything is left unset it fails closed to a blocked order.

Governance (unchanged from the target modules):
* ``None`` means "policy open / uncalibrated" and fails closed (order stays
  blocked; never an optimistic PASS).
* The default ``RuntimeOrderPolicy`` binds the owner-approved
  ``DEFAULT_THRESHOLD_POLICY`` (technical 40 / setup 35 / gap 5 / R:R 2/1) into
  the composition floors, and keeps every safety/macro/portfolio/journal value
  open -> ``certified()`` is False -> order workflow stays disabled.
* ``from_dict`` is a strict-identity loader: it only overrides the keys the
  owner supplies and keeps the rest unset; it rejects unknown/mixed versions.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from core.macro_gate import DEFAULT_MACRO_POLICY, MacroPolicy
from core.market_safety_gate import (
    SafetyPolicy,
    SCANNER_V4_SAFETY_POLICY_VERSION,
)
from core.scanner_v4_composition import ComposeOptions
from core.scanner_v4_threshold_policy import (
    SCANNER_V4_THRESHOLD_POLICY_VERSION,
    ThresholdPolicy,
    make_default_threshold_policy,
)

ORDER_POLICY_VERSION = "scanner-order-policy-v1"


class OrderPolicyError(ValueError):
    """Typed misuse: an order policy is not shaped/versioned correctly."""

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"ORDER_POLICY_INVALID at {path}: {detail}")


def _require_text(value: object, path: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise OrderPolicyError(path, "expected a non-empty string")
    return value


def _require_optional_rr(value: object, path: str) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise OrderPolicyError(path, "expected a ratio string/int or null")
    if isinstance(value, int):
        number = Fraction(value)
    elif isinstance(value, str):
        try:
            number = Fraction(value)
        except (ValueError, ZeroDivisionError):
            raise OrderPolicyError(path, f"unparsable ratio {value!r}") from None
    else:
        raise OrderPolicyError(path, "expected a ratio string/int or null")
    if number <= 0:
        raise OrderPolicyError(path, "must be positive")
    return number


def _safety_configured(policy: SafetyPolicy) -> bool:
    """Safety is only certifying order eligibility when every mandatory dim is set."""
    if policy.connectivity_max_age_minutes is None:
        return False
    if policy.max_candle_age_minutes is None:
        return False
    if not policy.spread_threshold_by_symbol:
        return False
    if not policy.volatility_calibrated or policy.volatility_upper_ratio is None:
        return False
    return True


def _macro_configured(policy: MacroPolicy) -> bool:
    """Macro is certifying only when deadband/confidence/conflict/cap are set."""
    if policy.deadband_points is None:
        return False
    if policy.confidence_threshold is None:
        return False
    if policy.conflict_cap is None:
        return False
    return True


@dataclass(frozen=True, slots=True)
class RuntimeOrderPolicy:
    """The single owner-facing bundle the live order workflow reads.

    Every value defaults to open (``None``/empty) so the default policy can
    never silently enable a real order: ``certified()`` (and therefore
    ``order_enabled``) is False until THRESHOLD + SAFETY + MACRO + PORTFOLIO +
    JOURNAL are all explicitly configured.  Only ``threshold`` carries the
    owner-approved default floors (40/35/5/2:1) so composition and routing agree.
    """

    order_policy_version: str = ORDER_POLICY_VERSION
    threshold: ThresholdPolicy = field(default_factory=make_default_threshold_policy)
    safety: SafetyPolicy = field(default_factory=lambda: SafetyPolicy(
        policy_version=SCANNER_V4_SAFETY_POLICY_VERSION
    ))
    macro: MacroPolicy = field(default_factory=lambda: DEFAULT_MACRO_POLICY)
    portfolio_position_limit: int | None = None
    portfolio_exposure_limit: float | None = None
    journal_max_consecutive_losses: int | None = None
    journal_drawdown_caution_ratio: float | None = None

    def __post_init__(self) -> None:
        if self.order_policy_version != ORDER_POLICY_VERSION:
            raise OrderPolicyError(
                "order_policy_version",
                f"expected the locked {ORDER_POLICY_VERSION!r}",
            )
        if type(self.threshold) is not ThresholdPolicy:
            raise OrderPolicyError("threshold", "expected a ThresholdPolicy")
        if type(self.safety) is not SafetyPolicy:
            raise OrderPolicyError("safety", "expected a SafetyPolicy")
        if type(self.macro) is not MacroPolicy:
            raise OrderPolicyError("macro", "expected a MacroPolicy")
        if self.portfolio_position_limit is not None and (
            type(self.portfolio_position_limit) is not int
            or self.portfolio_position_limit < 1
        ):
            raise OrderPolicyError(
                "portfolio_position_limit", "expected a positive integer or null"
            )
        if self.portfolio_exposure_limit is not None:
            number = float(self.portfolio_exposure_limit)
            if not 0 <= number <= 1:
                raise OrderPolicyError(
                    "portfolio_exposure_limit", "expected a ratio in 0..1 or null"
                )
        if self.journal_max_consecutive_losses is not None and (
            type(self.journal_max_consecutive_losses) is not int
            or self.journal_max_consecutive_losses < 1
        ):
            raise OrderPolicyError(
                "journal_max_consecutive_losses",
                "expected a positive integer or null",
            )
        if self.journal_drawdown_caution_ratio is not None:
            number = float(self.journal_drawdown_caution_ratio)
            if not 0 <= number <= 1:
                raise OrderPolicyError(
                    "journal_drawdown_caution_ratio",
                    "expected a ratio in 0..1 or null",
                )

    # --- composition mapping ------------------------------------------------

    def to_compose_options(self) -> ComposeOptions:
        """Carry the threshold floors + portfolio/journal limits into composition.

        The floors come from the owner-approved threshold policy so the
        composition's own decision guard and the router read the SAME values.
        """
        return ComposeOptions(
            min_risk_reward=self.threshold.min_risk_reward,
            technical_floor=self.threshold.technical_floor,
            setup_floor=self.threshold.setup_floor,
            portfolio_position_limit=self.portfolio_position_limit,
            portfolio_exposure_limit=self.portfolio_exposure_limit,
            journal_max_consecutive_losses=self.journal_max_consecutive_losses,
            journal_drawdown_caution_ratio=self.journal_drawdown_caution_ratio,
        )

    # --- certification -------------------------------------------------------

    def certified(self) -> bool:
        """True only when EVERY required layer can actually gate order eligibility."""
        return bool(
            self.threshold.certified()
            and _safety_configured(self.safety)
            and _macro_configured(self.macro)
            and self.portfolio_position_limit is not None
            and self.portfolio_exposure_limit is not None
            and self.journal_max_consecutive_losses is not None
            and self.journal_drawdown_caution_ratio is not None
        )

    @property
    def order_enabled(self) -> bool:
        """The single knob the runtime reads before it may dispatch a real order."""
        return self.certified()

    # --- serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_policy_version": self.order_policy_version,
            "threshold": self.threshold.to_dict(),
            "safety": {
                "policy_version": self.safety.policy_version,
                "connectivity_max_age_minutes": self.safety.connectivity_max_age_minutes,
                "max_candle_age_minutes": self.safety.max_candle_age_minutes,
                "spread_threshold_by_symbol": dict(self.safety.spread_threshold_by_symbol),
                "volatility_calibrated": self.safety.volatility_calibrated,
                "volatility_upper_ratio": self.safety.volatility_upper_ratio,
            },
            "macro": {
                "policy_version": self.macro.policy_version,
                "deadband_points": self.macro.deadband_points,
                "confidence_threshold": self.macro.confidence_threshold,
                "conflict_cap": self.macro.conflict_cap,
                "unknown_cap": self.macro.unknown_cap,
            },
            "portfolio_position_limit": self.portfolio_position_limit,
            "portfolio_exposure_limit": self.portfolio_exposure_limit,
            "journal_max_consecutive_losses": self.journal_max_consecutive_losses,
            "journal_drawdown_caution_ratio": self.journal_drawdown_caution_ratio,
        }

    @classmethod
    def from_dict(cls, value: object) -> "RuntimeOrderPolicy":
        """Strict-but-lenient loader: only overrides the keys the owner supplies.

        Identity is exact (reject unknown version); every numeric value is
        co-validated.  A key that is absent or explicit ``null`` stays open
        (fail-closed) and the order workflow remains blocked until filled.
        """
        if type(value) is not dict:
            raise OrderPolicyError("order_policy", "expected an object")
        version = _require_text(value.get("order_policy_version"), "order_policy.order_policy_version")
        if version != ORDER_POLICY_VERSION:
            raise OrderPolicyError(
                "order_policy.order_policy_version",
                f"expected the locked {ORDER_POLICY_VERSION!r}, got {version!r}",
            )

        # --- threshold (overrides only provided floors; else owner default) -
        raw_threshold = value.get("threshold")
        threshold = make_default_threshold_policy()
        if raw_threshold is not None:
            if type(raw_threshold) is not dict:
                raise OrderPolicyError("threshold", "expected an object")
            tv = _require_text(
                raw_threshold.get("policy_version"), "threshold.policy_version"
            )
            if tv != SCANNER_V4_THRESHOLD_POLICY_VERSION:
                raise OrderPolicyError(
                    "threshold.policy_version", f"expected {SCANNER_V4_THRESHOLD_POLICY_VERSION!r}"
                )
            min_rr_raw = raw_threshold.get("min_risk_reward")
            min_rr = (
                threshold.min_risk_reward
                if min_rr_raw is None
                else _require_optional_rr(min_rr_raw, "threshold.min_risk_reward")
            )
            threshold = ThresholdPolicy(
                policy_version=SCANNER_V4_THRESHOLD_POLICY_VERSION,
                technical_floor=_optional_over(
                    raw_threshold.get("technical_floor"), threshold.technical_floor
                ),
                setup_floor=_optional_over(
                    raw_threshold.get("setup_floor"), threshold.setup_floor
                ),
                min_score_gap=_optional_over(
                    raw_threshold.get("min_score_gap"), threshold.min_score_gap
                ),
                min_risk_reward=min_rr,
            )

        # --- safety (all-open default; owner fills) -------------------------
        raw_safety = value.get("safety")
        safety = SafetyPolicy(policy_version=SCANNER_V4_SAFETY_POLICY_VERSION)
        if raw_safety is not None:
            if type(raw_safety) is not dict:
                raise OrderPolicyError("safety", "expected an object")
            sv = _require_text(raw_safety.get("policy_version"), "safety.policy_version")
            if sv != SCANNER_V4_SAFETY_POLICY_VERSION:
                raise OrderPolicyError(
                    "safety.policy_version", f"expected {SCANNER_V4_SAFETY_POLICY_VERSION!r}"
                )
            spread = raw_safety.get("spread_threshold_by_symbol")
            if spread is None:
                spread = {}
            if type(spread) is not dict:
                raise OrderPolicyError("safety.spread_threshold_by_symbol", "expected an object")
            spread = {str(k): v for k, v in spread.items()}
            safety = SafetyPolicy(
                policy_version=SCANNER_V4_SAFETY_POLICY_VERSION,
                connectivity_max_age_minutes=_optional_over(
                    raw_safety.get("connectivity_max_age_minutes"), None
                ),
                max_candle_age_minutes=_optional_over(
                    raw_safety.get("max_candle_age_minutes"), None
                ),
                spread_threshold_by_symbol=spread,
                volatility_calibrated=bool(
                    _optional_over(raw_safety.get("volatility_calibrated"), True)
                    and raw_safety.get("volatility_upper_ratio") is not None
                ),
                volatility_upper_ratio=_optional_over(
                    raw_safety.get("volatility_upper_ratio"), None
                ),
            )

        # --- macro (all-open default; owner fills) --------------------------
        raw_macro = value.get("macro")
        macro = DEFAULT_MACRO_POLICY
        if raw_macro is not None:
            if type(raw_macro) is not dict:
                raise OrderPolicyError("macro", "expected an object")
            from core.macro_gate import MacroPolicy as _MacroPolicy
            macro = _MacroPolicy(
                policy_version=macro.policy_version,
                deadband_points=_optional_over(
                    raw_macro.get("deadband_points"), macro.deadband_points
                ),
                confidence_threshold=_optional_over(
                    raw_macro.get("confidence_threshold"), macro.confidence_threshold
                ),
                conflict_cap=_optional_over(
                    raw_macro.get("conflict_cap"), macro.conflict_cap
                ),
                unknown_cap=_optional_over(
                    raw_macro.get("unknown_cap"), macro.unknown_cap
                ),
            )

        return cls(
            order_policy_version=ORDER_POLICY_VERSION,
            threshold=threshold,
            safety=safety,
            macro=macro,
            portfolio_position_limit=_optional_over(
                value.get("portfolio_position_limit"), None
            ),
            portfolio_exposure_limit=_optional_over(
                value.get("portfolio_exposure_limit"), None
            ),
            journal_max_consecutive_losses=_optional_over(
                value.get("journal_max_consecutive_losses"), None
            ),
            journal_drawdown_caution_ratio=_optional_over(
                value.get("journal_drawdown_caution_ratio"), None
            ),
        )


# The default policy every runtime build shares: threshold floors owner-approved,
# everything else open -> ORDER BLOCKED until the owner fills the values.
DEFAULT_RUNTIME_ORDER_POLICY = RuntimeOrderPolicy()


DEFAULT_ORDER_POLICY_FILENAME = "scanner_v4_order_policy.json"


class OrderPolicyLoadError(OrderPolicyError):
    """Typed fault: the owner's policy file could not be read/parsed as a policy."""


def load_runtime_order_policy(
    path: str | Path | None = None,
) -> RuntimeOrderPolicy:
    """Load the owner's RuntimeOrderPolicy from config (fail-closed).

    Reads ``config/scanner_v4_order_policy.json`` by default. Any failure
    (missing file, unreadable JSON, invalid policy identity/values) raises
    ``OrderPolicyLoadError``; the caller falls back to
    ``DEFAULT_RUNTIME_ORDER_POLICY`` whose ``order_enabled`` is False, so a
    broken config can never open the live order workflow.
    """
    if path is None:
        from config.paths import CONFIG_DIR

        resolved = CONFIG_DIR / DEFAULT_ORDER_POLICY_FILENAME
    else:
        resolved = Path(path)
    try:
        raw = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise OrderPolicyLoadError(
            str(resolved), f"cannot read file: {exc}"
        ) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OrderPolicyLoadError(
            str(resolved), f"invalid JSON: {exc}"
        ) from exc
    try:
        return RuntimeOrderPolicy.from_dict(data)
    except OrderPolicyError as exc:
        raise OrderPolicyLoadError(str(resolved), exc.detail) from exc


def _optional_over(value: object, fallback: Any) -> Any:
    """Return ``fallback`` when the key is absent or explicit ``null``."""
    return fallback if value is None else value


__all__ = [
    "DEFAULT_ORDER_POLICY_FILENAME",
    "DEFAULT_RUNTIME_ORDER_POLICY",
    "ORDER_POLICY_VERSION",
    "OrderPolicyError",
    "OrderPolicyLoadError",
    "RuntimeOrderPolicy",
    "load_runtime_order_policy",
]