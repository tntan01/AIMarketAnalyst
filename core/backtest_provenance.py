"""Deterministic provenance manifest for validation evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


BACKTEST_PROVENANCE_VERSION = "backtest-provenance-v1"


def build_backtest_provenance(
    *,
    code_revision: str,
    request: dict[str, Any],
    data_manifest: dict[str, Any],
    execution_contract: dict[str, Any],
    scoring_contract: dict[str, Any],
    frozen_strategy_config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Bind source data, code, request/config, scoring and execution."""

    request_payload = dict(request)
    request_payload.pop("code_revision", None)
    components = {
        "version": BACKTEST_PROVENANCE_VERSION,
        "code_revision": str(code_revision or "").strip().lower(),
        "dataset_hash": str(data_manifest.get("dataset_hash") or "").lower(),
        "request_fingerprint": canonical_fingerprint(request_payload),
        "execution_fingerprint": canonical_fingerprint(execution_contract),
        "scoring_fingerprint": canonical_fingerprint(scoring_contract),
        "frozen_config_fingerprint": canonical_fingerprint(
            frozen_strategy_config or {}
        ),
    }
    components["provenance_fingerprint"] = canonical_fingerprint(components)
    return components


def validate_backtest_provenance(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["BACKTEST_PROVENANCE_MISSING"]
    reasons: list[str] = []
    if str(value.get("version") or "") != BACKTEST_PROVENANCE_VERSION:
        reasons.append("BACKTEST_PROVENANCE_VERSION_MISMATCH")
    revision = str(value.get("code_revision") or "").lower()
    if not 7 <= len(revision) <= 64 or any(
        character not in "0123456789abcdef" for character in revision
    ):
        reasons.append("BACKTEST_CODE_REVISION_INVALID")
    for field in (
        "dataset_hash",
        "request_fingerprint",
        "execution_fingerprint",
        "scoring_fingerprint",
        "frozen_config_fingerprint",
    ):
        if not _sha256(value.get(field)):
            reasons.append(f"BACKTEST_{field.upper()}_INVALID")
    supplied = str(value.get("provenance_fingerprint") or "").lower()
    payload = dict(value)
    payload.pop("provenance_fingerprint", None)
    if not _sha256(supplied) or supplied != canonical_fingerprint(payload):
        reasons.append("BACKTEST_PROVENANCE_FINGERPRINT_INVALID")
    return reasons


def canonical_fingerprint(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sha256(value: object) -> bool:
    text = str(value or "").lower()
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text
    )
