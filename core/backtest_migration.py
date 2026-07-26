"""Fail-closed migration views for persisted backtest snapshots."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.backtest_contract import (
    BACKTEST_CONTRACT_VERSION,
    CURRENT_BACKTEST_ENGINE_VERSION,
    VALIDATION_BACKTEST_ENGINE_VERSION,
)


BACKTEST_SNAPSHOT_MIGRATION_VERSION = "backtest-phase7-snapshot-migration-v1"
LEGACY_RESEARCH = "LEGACY_RESEARCH"


def migrate_snapshot_payload(
    payload: object,
    *,
    source_path: str = "",
) -> dict[str, Any]:
    """Return an audit-preserving runtime view of a persisted snapshot."""

    if not isinstance(payload, dict):
        raise ValueError("Snapshot backtest phải là JSON object.")
    migrated = deepcopy(payload)
    current = _is_current_snapshot(migrated)
    migration = {
        "version": BACKTEST_SNAPSHOT_MIGRATION_VERSION,
        "source_path": str(source_path or ""),
        "legacy_engine": not current,
        "original_mode": str(payload.get("mode") or ""),
        "original_engine_version": _engine_version(payload),
        "evidence_preserved": True,
    }
    migrated["migration"] = migration
    if not current:
        migrated["lifecycle"] = {
            "status": LEGACY_RESEARCH,
            "can_publish_config": False,
            "reasons": [
                "LEGACY_BACKTEST_ENGINE",
                "REVALIDATION_WITH_CURRENT_ENGINE_REQUIRED",
            ],
        }
        contract = migrated.get("backtest_contract")
        if isinstance(contract, dict):
            contract["validation_eligible"] = False
            contract["legacy_engine"] = True
    else:
        lifecycle = migrated.get("lifecycle")
        if not isinstance(lifecycle, dict):
            migrated["lifecycle"] = {
                "status": "RESEARCH_ONLY",
                "can_publish_config": False,
                "reasons": ["RELEASE_REPORT_REQUIRED"],
            }
        else:
            lifecycle.setdefault("can_publish_config", False)
    return migrated


def _is_current_snapshot(payload: dict[str, Any]) -> bool:
    if payload.get("mode") == "portfolio_backtest":
        rows = payload.get("symbols")
        return bool(rows) and all(
            isinstance(row, dict) and _is_current_contract(row.get("backtest_contract"))
            for row in rows
        )
    if _is_current_contract(payload.get("backtest_contract")):
        return True
    replay = payload.get("validation_replay")
    return isinstance(replay, dict) and _is_current_contract(
        replay.get("backtest_contract")
    )


def _is_current_contract(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        str(value.get("contract_version") or "") == BACKTEST_CONTRACT_VERSION
        and str(value.get("engine_version") or "")
        in {CURRENT_BACKTEST_ENGINE_VERSION, VALIDATION_BACKTEST_ENGINE_VERSION}
    )


def _engine_version(payload: dict[str, Any]) -> str:
    contract = payload.get("backtest_contract")
    return str(contract.get("engine_version") or "") if isinstance(contract, dict) else ""
