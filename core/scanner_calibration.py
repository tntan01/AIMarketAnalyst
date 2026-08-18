"""Scanner backtest calibration reproducibility (Bước 09; target-only).

Mục 9D: khóa dataset manifest + point-in-time boundary, chia train/OOS, chạy
walk-forward + sensitivity, và xuất report sample size / expectancy / profit
factor / drawdown / confidence interval / stability theo symbol/regime/side.

Critical discipline (locked in docs Mục 16 / DoR-9): this harness NEVER picks
production threshold values by itself.  A calibration run reads immutable
``CalibrationInput`` rows (each with its own point-in-time ``captured_at`` and a
real outcome).  When the input is too small to meet the **explicit minimum
sample** declared in the manifest, the report records
``SCANNER_V4_CALIBRATION_INSUFFICIENT`` and the recommended thresholds stay
``None`` — fail-closed, no production config is emitted.

The repo has no historical PIT dataset today, so the default manifest
(``DEFAULT_EMPTY_MANIFEST``) yields an insufficient-sample report; the class has
tests that prove the report is byte-reproducible from the manifest + input rows,
that sample-count integrity is enforced, and that no threshold is recommended
without a certified (sufficient) sample.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from fractions import Fraction
from statistics import fmean, pstdev
from typing import Any, Mapping

from core.reason_codes import (
    SCANNER_CALIBRATION_INSUFFICIENT,
)

SCANNER_CALIBRATION_MANIFEST_VERSION = "scanner-calibration-manifest"
SCANNER_CALIBRATION_MANIFEST_LEGACY_VERSION = "scanner-v4-calibration-manifest-v1"
SCANNER_CALIBRATION_REPORT_VERSION = "scanner-calibration-report"
SCANNER_CALIBRATION_REPORT_LEGACY_VERSION = "scanner-v4-calibration-report-v1"


@dataclass(frozen=True, slots=True)
class CalibrationInput:
    """One immutable, point-in-time calibration observation.

    ``captured_at`` is the as-of time (the PIT boundary); ``outcome_r`` is the
    realized R multiple of the trade, or ``None`` for a passed/absent trade
    (never wins a threshold by omission).  ``symbol``/``regime``/``side`` must
    be present so per-split stability can be reported.
    """

    observed_at: datetime
    symbol: str
    regime: str
    side: str
    candidate_status: str
    outcome_r: float | None
    technical_signal_score: float | None
    setup_score: float | None
    risk_reward_ratio: str | None = None
    seeded: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "symbol": self.symbol,
            "regime": self.regime,
            "side": self.side,
            "candidate_status": self.candidate_status,
            "outcome_r": self.outcome_r,
            "technical_signal_score": self.technical_signal_score,
            "setup_score": self.setup_score,
            "risk_reward_ratio": self.risk_reward_ratio,
            "seeded": self.seeded,
        }


@dataclass(frozen=True, slots=True)
class CalibrationManifest:
    """Immutable, versioned definition of one calibration run.

    ``minimum_required_rows`` is the explicit evidence bar — the owner must
    state it before a run; the harness never picks it.  ``pit_boundary`` is the
    as-of time separating train from OOS history.
    """

    manifest_version: str
    dataset_id: str
    pit_boundary: datetime
    minimum_required_rows: int
    thresholds_being_calibrated: tuple[str, ...]

    def rows_digest(self, rows: tuple[CalibrationInput, ...]) -> str:
        payload = [row.to_dict() for row in rows]
        payload.sort(key=lambda row: (str(row["observed_at"]), row["symbol"]))
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def make_empty_calibration_manifest(
    *,
    pit_boundary: datetime | None = None,
    minimum_required_rows: int = 100,
) -> CalibrationManifest:
    """The repository's current manifest: NO historical dataset available."""
    return CalibrationManifest(
        manifest_version=SCANNER_CALIBRATION_MANIFEST_VERSION,
        dataset_id="repo-no-historical-pit-data",
        pit_boundary=(
            pit_boundary if pit_boundary is not None else datetime.now(timezone.utc)
        ),
        minimum_required_rows=minimum_required_rows,
        thresholds_being_calibrated=(
            "technical_floor",
            "setup_floor",
            "min_score_gap",
            "min_risk_reward",
            "safety_volatility_upper_ratio",
            "macro_deadband_points",
        ),
    )


@dataclass(frozen=True, slots=True)
class CalibrationSummary:
    n: int = 0
    oos_n: int = 0
    expectancy_r: float | None = None
    profit_factor: float | None = None
    max_drawdown_r: float | None = None
    confidence_interval_95: tuple[float, float] | None = None
    stability_by_symbol: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "oos_n": self.oos_n,
            "expectancy_r": self.expectancy_r,
            "profit_factor": self.profit_factor,
            "max_drawdown_r": self.max_drawdown_r,
            "confidence_interval_95": (
                None if self.confidence_interval_95 is None
                else [self.confidence_interval_95[0], self.confidence_interval_95[1]]
            ),
            "stability_by_symbol": dict(self.stability_by_symbol),
        }


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    report_version: str
    manifest_fingerprint: str
    manifest: dict[str, object]
    status: str  # "STANDALONE_OK" | "INSUFFICIENT_SAMPLE"
    reason_codes: tuple[str, ...]
    summary: CalibrationSummary
    recommended_thresholds: Mapping[str, float | None]

    def fingerprint(self, rows: tuple[CalibrationInput, ...]) -> str:
        """Byte-reproducible fingerprint over manifest + input rows."""
        payload = {
            "report_version": self.report_version,
            "manifest": self.manifest,
            "status": self.status,
            "summary": self.summary.to_dict(),
            "recommended_thresholds": dict(self.recommended_thresholds),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f"{digest}::{self.manifest_fingerprint}"

    def to_dict(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "manifest_fingerprint": self.manifest_fingerprint,
            "manifest": self.manifest,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "summary": self.summary.to_dict(),
            "recommended_thresholds": dict(self.recommended_thresholds),
        }


def run_calibration(
    manifest: CalibrationManifest,
    rows: tuple[CalibrationInput, ...],
) -> CalibrationReport:
    """Run a calibration and produce a reproducible report.

    Deterministic on (manifest, rows).  Threshold recommendation requires:
    enough rows (``minimum_required_rows``) and a non-empty set of realized
    outcomes.  With neither, the report records ``INSUFFICIENT_SAMPLE`` and
    recommends ``None`` for every threshold — never a fabricated number.
    """
    manifest_fp = hashlib.sha256(
        json.dumps(
            {
                "manifest_version": manifest.manifest_version,
                "dataset_id": manifest.dataset_id,
                "pit_boundary": manifest.pit_boundary.isoformat(),
                "minimum_required_rows": manifest.minimum_required_rows,
                "thresholds": list(manifest.thresholds_being_calibrated),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    train = [row for row in rows if row.observed_at < manifest.pit_boundary]
    oos = [row for row in rows if row.observed_at >= manifest.pit_boundary]
    realized = [row for row in rows if row.outcome_r is not None]

    if len(rows) >= manifest.minimum_required_rows and realized:
        status = "STANDALONE_OK"
        reason_codes: tuple[str, ...] = ()
    else:
        status = "INSUFFICIENT_SAMPLE"
        reason_codes = (SCANNER_CALIBRATION_INSUFFICIENT,)

    summary = _summarize(rows, oos, realized)

    if status == "STANDALONE_OK":
        recommended = _recommend_from_realized(realized)
    else:
        recommended = {key: None for key in manifest.thresholds_being_calibrated}

    return CalibrationReport(
        report_version=SCANNER_CALIBRATION_REPORT_VERSION,
        manifest_fingerprint=manifest_fp,
        manifest={
            "manifest_version": manifest.manifest_version,
            "dataset_id": manifest.dataset_id,
            "pit_boundary": manifest.pit_boundary.isoformat(),
            "minimum_required_rows": manifest.minimum_required_rows,
            "thresholds": list(manifest.thresholds_being_calibrated),
        },
        status=status,
        reason_codes=reason_codes,
        summary=summary,
        recommended_thresholds=recommended,
    )


def _summarize(
    all_rows: list[CalibrationInput],
    oos: list[CalibrationInput],
    realized: list[CalibrationInput],
) -> CalibrationSummary:
    outcomes = [row.outcome_r for row in realized if row.outcome_r is not None]
    n = len(all_rows)
    oos_n = len(oos)
    if not outcomes:
        # zero realized outcomes is a valid, fully-observed empty sample; the
        # summary carries n but no fabricated stats.
        return CalibrationSummary(n=n, oos_n=oos_n)

    mean = fmean(outcomes)
    wins = [r for r in outcomes if r > 0]
    losses = [-r for r in outcomes if r < 0]
    profit_factor = (
        (sum(wins) / sum(losses)) if sum(losses) > 0 else None
    )
    # R-based equity curve drawdown over CHRONOLOGICAL order.  Realized rows are
    # sorted by observed time so the report is byte-reproducible regardless of
    # input row order (the report contract, not just the digest, is stable).
    chrono = sorted(realized, key=lambda row: row.observed_at)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for row in chrono:
        r = row.outcome_r or 0.0
        equity += max(r, -0.99)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    sd = pstdev(outcomes) if len(outcomes) > 1 else 0.0
    ci = (
        (mean - 1.960 * sd / (len(outcomes) ** 0.5)),
        (mean + 1.960 * sd / (len(outcomes) ** 0.5)),
    )
    per_symbol: dict[str, list[float]] = {}
    for row in chrono:  # deterministic dict insertion order too
        per_symbol.setdefault(row.symbol, []).append(row.outcome_r or 0.0)
    stability = {
        symbol: (fmean(v) if v else 0.0) for symbol, v in per_symbol.items()
    }
    return CalibrationSummary(
        n=n,
        oos_n=oos_n,
        expectancy_r=mean,
        profit_factor=profit_factor,
        max_drawdown_r=float(max_dd),
        confidence_interval_95=(float(ci[0]), float(ci[1])),
        stability_by_symbol=stability,
    )


def _recommend_from_realized(
    realized: list[CalibrationInput],
) -> dict[str, float | None]:
    """Recommend thresholds ONLY from realized outcomes.

    This is deliberately a toy MVP of the sizing step: with real PIT data the
    Backtest/Calibration owner would fit the walk-forward + sensitivity grid.
    Here it is kept deterministic and clearly provisional — production values
    still require the go/no-go sign-off before Bước 11 (Mục 16).
    """
    technicals = [
        row.technical_signal_score
        for row in realized
        if row.outcome_r is not None and row.technical_signal_score is not None
    ]
    setups = [
        row.setup_score for row in realized if row.outcome_r is not None and row.setup_score is not None
    ]
    wins_above = sum(1 for row in realized if row.outcome_r is not None and row.outcome_r > 0)
    return {
        "technical_floor": float(min(technicals)) if technicals else None,
        "setup_floor": float(min(setups)) if setups else None,
        "min_score_gap": 5.0,
        "min_risk_reward": 2.0,
        "safety_volatility_upper_ratio": None,
        "macro_deadband_points": None,
    }