"""Export correlated Scanner trades from a connected MT5 demo account."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.mt5_service import MT5Service, is_demo_server
from services.storage_service import JsonStorage


EXPORT_VERSION = "backtest-phase7-mt5-demo-export-v1"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export closed Scanner-correlated trades from the currently "
            "connected MT5 demo account. Real accounts are rejected."
        )
    )
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    service = MT5Service()
    status = service.mt5_connection_status()
    if not status.logged_in:
        parser.error("MT5 is not connected to a logged-in account.")
    if not is_demo_server(status.server):
        print(json.dumps({
            "exported": False,
            "reason": "MT5_DEMO_ACCOUNT_REQUIRED",
            "server": status.server,
        }, ensure_ascii=True, indent=2))
        return 2

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(1, int(args.days)))
    rows = service.closed_trade_history(start=start, end=end)
    correlated = [
        dict(row) for row in rows
        if isinstance(row, dict) and str(row.get("candidate_id") or "")
    ]
    payload = {
        "version": EXPORT_VERSION,
        "account_is_demo": True,
        "server": status.server,
        "start": start.isoformat(timespec="seconds"),
        "end": end.isoformat(timespec="seconds"),
        "total_closed_trades": len(rows),
        "uncorrelated_trades": len(rows) - len(correlated),
        "trades": correlated,
    }
    JsonStorage(args.output).save(payload)
    print(json.dumps({
        "output": str(args.output.resolve()),
        "correlated_trades": len(correlated),
        "uncorrelated_trades": len(rows) - len(correlated),
    }, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
