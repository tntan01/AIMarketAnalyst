"""Scanner feature derivation (Path B — candle → technical raws).

This module is the candle→raw producer that the technical scorer consumes
(``core.technical_signal_scorer.score_technical_signal`` expects pre-computed
``trend`` ≤25 / ``momentum`` ≤20 / ``location`` ≤25 raws plus a canonical SMC).
It is a **documented port** of the legacy formulas from ``core/signal_engine.py``
(which is on the Bước 12 deletion list); formulas are copied verbatim so the
path stays live after legacy scoring is removed.

Governance (spec: ``docs/scanner/scanner-features-spec.md``):
* **deterministic** — identical candles ⇒ identical raws (asserted via
  ``deterministic_fingerprint``);
* **fail-closed** — insufficient D1/H4/H1 candles raise
  ``TechnicalRawDerivationError`` (never fabricated numbers);
* **no legacy score dependency** — imports ``technical_context``, ``indicators`` and
  the retained canonical-SMC producer (``smc_scorer``/``smc_scoring_result``),
  NOT ``signal_engine``/``analysis_engine``/``analysis_pipeline``;
* raw ceilings are the legacy maxima, exactly matching the component maxes
  (the spec's parity contract).

The ``smc`` raw (≤15) is not derived from candles here: per owner decision
(§4-a) it comes from the RETURED canonical ``SmcScoringResult`` via
``project_smc_technical_raw``.  If no ``canonical_smc`` is supplied, ``smc`` is
``None`` (fail-closed), never fabricated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from core.smc_scoring_result import SmcScoringResult
from core.technical_context import (
    build_technical_snapshot,
    distance_to_zone,
    nearest_zone,
    price_in_zone,
)
from core.technical_signal_scorer import project_smc_technical_raw

# Version identity of this feature layer (locked; contract §7.3).
FEATURES_VERSION = "scanner-features"
FEATURES_LEGACY_VERSION = "scanner-v4-features-v1"

# Raw ceilings — the legacy per-raw maxima, matching the component maxes
# (TECHNICAL_COMPONENT_RAW_MAX) that ScoreTechnicalSignal enforces.
TREND_RAW_MAX = 25
MOMENTUM_RAW_MAX = 20
LOCATION_RAW_MAX = 25
SMC_RAW_MAX = 15

# Minimum history the derivation requires (identical to
# ``technical_context.build_technical_snapshot``'s own guard).
MIN_D1 = 60
MIN_H4 = 60
MIN_H1 = 30

# Retained canonical-SMC provenance marker (owner decision §4-a).
SMC_SOURCE = "smc-v2"

REASON_INSUFFICIENT_DATA = "features_insufficient_data"
SOURCE_TECHNICAL = "technical"


class TechnicalRawDerivationError(ValueError):
    """Fail-closed: candles or inputs are insufficient — never fabricate."""


def _clamp(value: float, min_value: float, max_value: float) -> int:
    return int(max(min_value, min(max_value, value)))


def _choose_one(candidates: list[tuple[bool, int]]) -> int:
    """First TRUE candidate in list order (order is part of the legacy contract)."""
    for condition, score in candidates:
        if condition:
            return score
    return 0


# ---------------------------------------------------------------------------
# Ported raw formulas (verbatim from core/signal_engine.py).  These are pure
# functions of the technical context dict ``t`` built by
# ``build_technical_snapshot``, and are what Bước-4 parity tests compare against
# the legacy functions until legacy scoring is deleted.
# ---------------------------------------------------------------------------

def trend_alignment_score_v4(side: str, t: Mapping[str, Any]) -> int:
    price = t["price"]
    if side == "buy":
        return _clamp(
            sum(
                [
                    8 if t["ema50_d1"] > t["ema200_d1"] else 0,
                    5 if price > t["ema200_d1"] else 0,
                    5 if price > t["ema50_d1"] or price > t["ema50_h4"] else 0,
                    5 if t["structure_h4"] == "HH/HL" else 0,
                    2 if t["structure_d1"] == "HH/HL" and t["structure_h4"] == "HH/HL" else 0,
                ]
            ),
            0,
            TREND_RAW_MAX,
        )
    return _clamp(
        sum(
            [
                8 if t["ema50_d1"] < t["ema200_d1"] else 0,
                5 if price < t["ema200_d1"] else 0,
                5 if price < t["ema50_d1"] or price < t["ema50_h4"] else 0,
                5 if t["structure_h4"] == "LH/LL" else 0,
                2 if t["structure_d1"] == "LH/LL" and t["structure_h4"] == "LH/LL" else 0,
            ]
        ),
        0,
        TREND_RAW_MAX,
    )


def momentum_alignment_score_v4(side: str, t: Mapping[str, Any]) -> int:
    value = t["rsi_h4"] or 50.0
    previous_value = t.get("rsi_h4_previous")
    prev_value = value if previous_value is None else previous_value
    rsi_rising = value > prev_value
    rsi_falling = value < prev_value
    hist = t["macd_histogram_h4"]
    now = hist["value"]
    prev = hist["previous_value"]
    prev2 = hist["previous2_value"]
    if side == "buy":
        rsi_score = _choose_one(
            [
                (30 <= value <= 50 and rsi_rising, 8),
                (40 <= value <= 60 and not rsi_falling, 6),
                (60 < value <= 70 and not rsi_falling, 3),
                (value > 75, 0),
            ]
        )
        macd_score = _choose_one(
            [
                (now > 0 and now > prev > prev2, 10),
                (now < 0 and now > prev > prev2, 6),
                (now > prev, 3),
                (now > 0 and now < prev, 5),
            ]
        )
    else:
        rsi_score = _choose_one(
            [
                (50 <= value <= 70 and rsi_falling, 8),
                (40 <= value <= 60 and not rsi_rising, 6),
                (30 <= value < 40 and not rsi_rising, 3),
                (value < 25, 0),
            ]
        )
        macd_score = _choose_one(
            [
                (now < 0 and now < prev < prev2, 10),
                (now > 0 and now < prev < prev2, 6),
                (now < prev, 3),
                (now < 0 and now > prev, 5),
            ]
        )
    macd_accel = hist.get("direction", "flat") == "increasing"
    accel_bonus = 0
    if side == "buy":
        if rsi_rising and macd_accel:
            accel_bonus = 2
        elif not rsi_rising and not macd_accel:
            accel_bonus = -2
    else:
        if rsi_falling and not macd_accel:
            accel_bonus = 2
        elif not rsi_falling and macd_accel:
            accel_bonus = -2
    return _clamp(rsi_score + macd_score + accel_bonus, 0, MOMENTUM_RAW_MAX)


def location_quality_score_v4(side: str, t: Mapping[str, Any]) -> int:
    price = t["price"]
    atr_value = t["atr_h4"] or t["atr_d1"] or 0.0
    supports = t["support_zones"]
    resistances = t["resistance_zones"]
    nearest_support = nearest_zone(price, supports)
    nearest_resistance = nearest_zone(price, resistances)

    if side == "buy":
        if nearest_support and price_in_zone(price, nearest_support):
            base = 15
        elif nearest_support and distance_to_zone(price, nearest_support) <= atr_value * 0.5:
            base = 10
        elif nearest_resistance and price_in_zone(price, nearest_resistance):
            base = 0
        else:
            base = 3
        bonus_zone = nearest_support
    else:
        if nearest_resistance and price_in_zone(price, nearest_resistance):
            base = 15
        elif nearest_resistance and distance_to_zone(price, nearest_resistance) <= atr_value * 0.5:
            base = 10
        elif nearest_support and price_in_zone(price, nearest_support):
            base = 0
        else:
            base = 3
        bonus_zone = nearest_resistance

    bonus = 0
    if bonus_zone:
        test_count = bonus_zone.get("test_count", 0)
        if test_count >= 3:
            bonus -= 5
        if test_count >= 5:
            bonus -= 3
        if bonus_zone.get("confluence_count", 0) >= 3:
            bonus += 5
        if bonus_zone.get("is_round_number"):
            bonus += 3
    return _clamp(base + bonus, 0, LOCATION_RAW_MAX)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SideFeatureRaws:
    """One side's four technical raws + their provenance."""

    side: str
    trend: int
    momentum: int
    location: int
    smc: int | None
    smc_source: str | None
    trend_source: str = SOURCE_TECHNICAL
    momentum_source: str = SOURCE_TECHNICAL
    location_source: str = SOURCE_TECHNICAL
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "trend": self.trend,
            "momentum": self.momentum,
            "location": self.location,
            "smc": self.smc,
            "smc_source": self.smc_source,
            "trend_source": self.trend_source,
            "momentum_source": self.momentum_source,
            "location_source": self.location_source,
            "reason_codes": list(self.reason_codes),
        }


def derive_technical_raws(
    d1: list[Any],
    h4: list[Any],
    h1: list[Any],
    *,
    symbol: str = "",
    captured_at: datetime | None = None,
    canonical_smc: SmcScoringResult | None = None,
) -> "TechnicalRaws":
    """Derive per-side technical raws from closed D1/H4/H1 candles.

    Raises ``TechnicalRawDerivationError`` (fail-closed) when history is below
    the minimums, mirroring ``build_technical_snapshot``.  Raw formulas are the
    verbatim legacy ports.  ``smc`` is ``None`` unless ``canonical_smc`` (a retained
    ``smc-v2`` ``SmcScoringResult``) is supplied — never fabricated.
    """
    if len(d1) < MIN_D1 or len(h4) < MIN_H4 or len(h1) < MIN_H1:
        raise TechnicalRawDerivationError(
            f"{REASON_INSUFFICIENT_DATA}: need D1>={MIN_D1} H4>={MIN_H4} H1>={MIN_H1} "
            f"(got D1={len(d1)} H4={len(h4)} H1={len(h1)})"
        )

    technical = build_technical_snapshot(d1, h4, h1)

    per_side: dict[str, SideFeatureRaws] = {}
    for side in ("buy", "sell"):
        smc: int | None = None
        smc_source: str | None = None
        if canonical_smc is not None:
            projection = project_smc_technical_raw(canonical_smc, side)
            smc = projection.raw
            smc_source = SMC_SOURCE
        per_side[side] = SideFeatureRaws(
            side=side,
            trend=trend_alignment_score_v4(side, technical),
            momentum=momentum_alignment_score_v4(side, technical),
            location=location_quality_score_v4(side, technical),
            smc=smc,
            smc_source=smc_source,
        )

    captured = captured_at if captured_at is not None else datetime.now(timezone.utc)
    return TechnicalRaws(
        features_version=FEATURES_VERSION,
        symbol=symbol,
        captured_at=captured,
        per_side=per_side,
        requirements={"d1_min": MIN_D1, "h4_min": MIN_H4, "h1_min": MIN_H1},
        derivation="port:trend_alignment_score_v4/momentum_alignment_score_v4"
        "/location_quality_score_v4@sig_engine; smc=@smc-v2",
    )


@dataclass(frozen=True, slots=True)
class TechnicalRaws:
    """The versioned feature layer output for one symbol."""

    features_version: str
    symbol: str
    captured_at: datetime
    per_side: dict[str, SideFeatureRaws]
    requirements: dict[str, int]
    derivation: str

    def __post_init__(self) -> None:
        if type(self.features_version) is not str or self.features_version not in (
            FEATURES_VERSION,
            FEATURES_LEGACY_VERSION,
        ):
            raise TechnicalRawDerivationError(
                f"features_version must equal {FEATURES_VERSION!r}"
            )
        if set(self.per_side) != {"buy", "sell"}:
            raise TechnicalRawDerivationError("per_side must contain exactly buy and sell")

    @property
    def deterministic_fingerprint(self) -> str:
        """sha256 over the ordered raw triples — byte-reproducible per candle set.

        ``captured_at``/``symbol`` are metadata and excluded so identical candles
        always yield an identical fingerprint regardless of when they were read.
        """
        ordered: dict[str, Any] = {}
        for side in ("buy", "sell"):
            s = self.per_side[side]
            ordered[side] = {
                "trend": s.trend,
                "momentum": s.momentum,
                "location": s.location,
                "smc": s.smc,
            }
        payload = json.dumps(ordered, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "features_version": self.features_version,
            "symbol": self.symbol,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "features": {side: s.to_dict() for side, s in self.per_side.items()},
            "requirements": dict(self.requirements),
            "derivation": self.derivation,
            "deterministic_fingerprint": self.deterministic_fingerprint,
        }


__all__ = [
    "FEATURES_VERSION",
    "SMC_SOURCE",
    "SOURCE_TECHNICAL",
    "TREND_RAW_MAX",
    "MOMENTUM_RAW_MAX",
    "LOCATION_RAW_MAX",
    "SMC_RAW_MAX",
    "MIN_D1",
    "MIN_H4",
    "MIN_H1",
    "TechnicalRawDerivationError",
    "SideFeatureRaws",
    "TechnicalRaws",
    "derive_technical_raws",
]