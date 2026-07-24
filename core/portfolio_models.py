"""Immutable domain models for Phase-4 portfolio risk evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


PORTFOLIO_ENGINE_VERSION = "phase4-portfolio-v1"


@dataclass(frozen=True, slots=True)
class PortfolioRiskItem:
    """One live position or pending order with broker valuation metadata."""

    source: str
    ticket: int
    symbol: str
    broker_symbol: str
    side: str
    entry_price: float | None
    current_price: float | None
    stop_loss: float | None
    volume: float | None
    tick_size: float | None
    tick_value_loss: float | None
    contract_size: float | None
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ticket": self.ticket,
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "stop_loss": self.stop_loss,
            "volume": self.volume,
            "tick_size": self.tick_size,
            "tick_value_loss": self.tick_value_loss,
            "contract_size": self.contract_size,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """Atomic view of all MT5 positions and pending orders."""

    available: bool
    captured_at: datetime
    account_balance: float | None
    account_currency: str
    positions: tuple[PortfolioRiskItem, ...] = ()
    pending_orders: tuple[PortfolioRiskItem, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_engine_version": PORTFOLIO_ENGINE_VERSION,
            "available": self.available,
            "captured_at": self.captured_at.isoformat(),
            "account_balance": self.account_balance,
            "account_currency": self.account_currency,
            "positions": [item.to_dict() for item in self.positions],
            "pending_orders": [
                item.to_dict() for item in self.pending_orders
            ],
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class PortfolioEvaluation:
    """Structured result for current and projected portfolio risk."""

    allowed: bool
    portfolio_allowed: bool
    account_allowed: bool
    snapshot_available: bool
    current_open_risk_pct: float | None
    proposed_risk_pct: float | None
    projected_open_risk_pct: float | None
    max_open_risk_pct: float
    current_order_count: int
    projected_order_count: int
    max_concurrent_orders: int
    symbol_risk_pct: dict[str, float]
    currency_exposure_pct: dict[str, dict[str, float]]
    correlation_clusters: tuple[dict[str, Any], ...]
    account_guard: dict[str, Any]
    checked_at: datetime
    reason_codes: tuple[str, ...] = ()
    block_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_engine_version": PORTFOLIO_ENGINE_VERSION,
            "allowed": self.allowed,
            "portfolio_allowed": self.portfolio_allowed,
            "account_allowed": self.account_allowed,
            "snapshot_available": self.snapshot_available,
            "current_open_risk_pct": self.current_open_risk_pct,
            "proposed_risk_pct": self.proposed_risk_pct,
            "projected_open_risk_pct": self.projected_open_risk_pct,
            "max_open_risk_pct": self.max_open_risk_pct,
            "current_order_count": self.current_order_count,
            "projected_order_count": self.projected_order_count,
            "max_concurrent_orders": self.max_concurrent_orders,
            "symbol_risk_pct": dict(self.symbol_risk_pct),
            "currency_exposure_pct": {
                currency: dict(values)
                for currency, values in self.currency_exposure_pct.items()
            },
            "correlation_clusters": [
                dict(cluster) for cluster in self.correlation_clusters
            ],
            "account_guard": dict(self.account_guard),
            "checked_at": self.checked_at.isoformat(),
            "reason_codes": list(self.reason_codes),
            "block_codes": list(self.block_codes),
            "warning_codes": list(self.warning_codes),
        }
