#!/usr/bin/env python
"""README-ONLY probe: propose ``safety.spread_threshold_by_symbol`` from REAL MT5 spreads.

Discipline (never fabricate): this script does NOT write any config. It connects
to the live MT5 terminal, reads each supported symbol's REAL current spread in
points (``MT5.symbol_info().spread``), and prints a proposed
``spread_threshold_by_symbol`` map. The owner reviews the proposed numbers and
(only if they approve) pastes them into ``config/scanner_order_policy.json``.

Why a threshold = observed spread:
  ``safety.spread_threshold_by_symbol`` is the per-symbol *cap* the market-safety
  gate compares against (actual spread > threshold -> SAFETY_SPREAD_ABNORMAL).
  The therefore most honest first proposal is the currently-observed spread
  itself; the owner may widen it (a *multiple*) to tolerate normal intraday
  widening. Use ``--multiple`` to scale the proposal upward.

Run:
  python scripts/propose_spread_thresholds.py [--multiple 1.5] [--json-only]

No real orders, no config writes. ``sends_real_order`` is untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_existing_thresholds() -> dict[str, int]:
    """Return the owner's current ``spread_threshold_by_symbol`` (may be empty)."""
    from config.paths import CONFIG_DIR

    path = CONFIG_DIR / "scanner_order_policy.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    safety = data.get("safety") or {}
    return dict(safety.get("spread_threshold_by_symbol") or {})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--multiple",
        type=float,
        default=1.0,
        help="proposed threshold = observed spread points * MULTIPLE (default 1.0).",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="print only the proposed JSON map (no human table).",
    )
    args = parser.parse_args()

    from config.constants import SUPPORTED_SYMBOLS
    from services.mt5_service import MT5Service

    existing = _load_existing_thresholds()

    svc = MT5Service()
    # Must initialize the MT5 IPC session first; mt5_connection_status() reads
    # terminal_info() directly and reports disconnected without initialize().
    connected = svc.connect()
    status = svc.mt5_connection_status()
    if not (connected and status.terminal_connected and status.logged_in):
        print(
            "MT5 not connected (connect=%r, terminal_connected=%r, broker_logged_in=%r). "
            "Cannot read real spreads — nothing proposed. Connect the terminal "
            "and log in, then re-run." % (connected, status.terminal_connected, status.logged_in),
            file=sys.stderr,
        )
        return 2

    available = svc.available_symbols(market_watch_only=True)
    rows: list[tuple[str, str, int, bool]] = []  # (app, broker, spread, already_configured)

    for app in SUPPORTED_SYMBOLS:
        broker = svc.resolve_symbol(app, available)
        if broker is None:
            print("  ! %-9s no broker symbol in market watch" % app, file=sys.stderr)
            continue
        q = svc.symbol_data_quality(app, broker)
        spread = q.get("spread_points")
        if spread is None:
            print("  ! %-9s real spread unavailable (broker=%s)" % (app, broker), file=sys.stderr)
            continue
        already = existing.get(_key(app)) is not None or existing.get(_key(broker)) is not None
        rows.append((app, broker, int(spread), already))

    if not rows:
        print("No real spread data available.", file=sys.stderr)
        return 2

    proposed: dict[str, int] = {}
    for app, broker, spread, _ in rows:
        proposed[_key(app)] = max(1, round(spread * args.multiple))

    if args.json_only:
        print(json.dumps(proposed, indent=2, sort_keys=True))
        return 0

    print("\nExisting thresholds in config (%d symbol(s)):" % len(existing))
    print("  " + json.dumps(existing, sort_keys=True))
    print("\nReal MT5 spread probe (points) + proposed threshold:\n")
    print(f"{'APP':9} {'BROKER':11} {'spread_pt':>9} {'proposed':>9}  status")
    for app, broker, spread, already in rows:
        marker = "covered" if already else "MISSING"
        print(f"{app:9} {broker:11} {spread:>9} {proposed[_key(app)]:>9}  {marker}")
    print("\nProposed spread_threshold_by_symbol (owner review — READ ONLY, not written):")
    print(json.dumps({"spread_threshold_by_symbol": proposed}, indent=2, sort_keys=True))
    print(
        "\nTo apply, copy the block above into config/scanner_order_policy.json "
        "safety.spread_threshold_by_symbol. This script never writes config."
    )
    return 0


def _key(symbol: str) -> str:
    """Normalize an app (EUR/USD) or broker (EURUSDc) key to the config form (EURUSD)."""
    return "".join(ch for ch in symbol if ch.isalnum()).upper().rstrip("C")


if __name__ == "__main__":
    raise SystemExit(main())