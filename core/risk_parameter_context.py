"""Execution-local risk parameters used by isolated research workloads.

Scanner/live analysis always sees the configured defaults.  Backtests may
temporarily bind an immutable set of overrides to the current execution
context without mutating ``core.risk_engine`` module globals.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterator, Mapping


@dataclass(frozen=True, slots=True)
class RiskParameterOverrides:
    values: tuple[tuple[str, float], ...] = ()

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, object] | None,
    ) -> "RiskParameterOverrides":
        normalized: list[tuple[str, float]] = []
        for key, value in (values or {}).items():
            normalized.append((str(key), float(value)))
        return cls(tuple(sorted(normalized)))

    def as_mapping(self) -> Mapping[str, float]:
        return MappingProxyType(dict(self.values))


_ACTIVE_OVERRIDES: ContextVar[RiskParameterOverrides] = ContextVar(
    "backtest_risk_parameter_overrides",
    default=RiskParameterOverrides(),
)


def risk_parameter(name: str, default: float) -> float:
    return float(dict(_ACTIVE_OVERRIDES.get().values).get(name, default))


@contextmanager
def risk_parameter_scope(
    overrides: RiskParameterOverrides | None,
) -> Iterator[None]:
    token = _ACTIVE_OVERRIDES.set(overrides or RiskParameterOverrides())
    try:
        yield
    finally:
        _ACTIVE_OVERRIDES.reset(token)

