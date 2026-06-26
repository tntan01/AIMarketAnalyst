"""Journal service — persistence and lifecycle management for trade journal entries."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT, journal_db_path
from services.journal_models import JournalEntry, JournalFilter, SQLITE_BUSY_TIMEOUT_MS, SQLITE_TIMEOUT_SECONDS
from services.journal_converters import (
    _parse_utc,
    _safe_float,
    _safe_int,
    build_performance_summary,
    calculate_trade_outcome,
    entry_from_row,
    entry_to_record,
    journal_entry_from_analysis,
    journal_entry_from_mt5_trade,
    journal_entry_from_scanner_row,
    normalize_trade_status,
    tags_from_json,
    tags_to_json,
    utc_now,
)


# ---------------------------------------------------------------------------
# Re-export for backward compatibility
# ---------------------------------------------------------------------------
__all__ = [
    "JournalEntry",
    "JournalFilter",
    "JournalService",
    "SQLITE_TIMEOUT_SECONDS",
    "SQLITE_BUSY_TIMEOUT_MS",
    "journal_entry_from_analysis",
    "journal_entry_from_scanner_row",
    "journal_entry_from_mt5_trade",
    "entry_to_record",
    "entry_from_row",
    "normalize_tag_list",
    "tags_to_json",
    "tags_from_json",
    "normalize_trade_status",
    "calculate_trade_outcome",
    "build_performance_summary",
    "group_performance",
    "recent_trade_rows",
    "utc_now",
    "normalize_utc_timestamp",
    "max_drawdown_r",
]

# Re-import for external consumers that import from this module
from services.journal_converters import (  # noqa: E402
    group_performance,
    max_drawdown_r,
    normalize_tag_list,
    normalize_utc_timestamp,
    recent_trade_rows,
)


class JournalService:
    def __init__(self, db_path: Path | None = None, migrations_dir: Path | None = None) -> None:
        self.db_path = db_path or journal_db_path()
        self.migrations_dir = migrations_dir or PROJECT_ROOT / "data" / "migrations"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def migrate(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
            )
            applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
            for migration in sorted(self.migrations_dir.glob("*.sql")):
                version = migration.stem
                if version in applied:
                    continue
                self._safe_execute_migration(conn, migration.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at_utc) VALUES (?, ?)",
                    (version, utc_now()),
                )
            conn.commit()

    def _safe_execute_migration(self, conn: sqlite3.Connection, sql: str) -> None:
        """Execute migration SQL, skipping ALTER TABLE ADD COLUMN for columns that already exist.

        SQLite does not support IF NOT EXISTS for ADD COLUMN.  If a migration
        is re-run on a database that already has the column (e.g. after a
        backup restore or partial migration), the ALTER TABLE would fail with
        a "duplicate column" error.  We guard against that by inspecting
        PRAGMA table_info before each ADD COLUMN statement.
        """
        # Strip -- style comments so they don't interfere with statement
        # splitting (comments have no trailing ; and would otherwise merge
        # with the following ALTER TABLE, defeating the regex).
        lines = [line for line in sql.split("\n") if not line.strip().startswith("--")]
        clean_sql = "\n".join(lines)

        existing_columns: set[str] = set()
        _table_info_fetched = False

        statements = [s.strip() for s in clean_sql.split(";") if s.strip()]

        for stmt in statements:
            match = re.match(
                r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)",
                stmt,
                re.IGNORECASE,
            )
            if match:
                table_name = match.group(1)
                column_name = match.group(2)

                if not _table_info_fetched:
                    rows = conn.execute(
                        f"PRAGMA table_info({table_name})"
                    ).fetchall()
                    existing_columns = {row[1] for row in rows}
                    _table_info_fetched = True

                if column_name in existing_columns:
                    continue  # already present — skip safely
                existing_columns.add(column_name)  # track for later statements in same script

            conn.execute(stmt)

    def create_from_analysis(self, analysis: dict[str, Any], *, mode: str = "scanner_detail", note: str = "") -> int:
        entry = journal_entry_from_analysis(analysis, mode=mode, note=note)
        return self.create(entry)

    def create_from_scanner_row(self, row: dict[str, Any], *, note: str = "") -> int:
        analysis = row.get("analysis_result")
        if isinstance(analysis, dict):
            return self.create_from_analysis(analysis, mode="scanner_detail", note=note)
        entry = journal_entry_from_scanner_row(row, note=note)
        return self.create(entry)

    def create(self, entry: JournalEntry) -> int:
        data = entry_to_record(entry)
        columns = ", ".join(data)
        placeholders = ", ".join("?" for _ in data)
        with self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO journal_entries ({columns}) VALUES ({placeholders})",
                tuple(data.values()),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def list_entries(self, filters: JournalFilter | None = None) -> list[JournalEntry]:
        filters = filters or JournalFilter()
        query = "SELECT * FROM journal_entries WHERE 1=1"
        params: list[object] = []
        if filters.date_from:
            query += " AND substr(timestamp_utc, 1, 10) >= ?"
            params.append(filters.date_from)
        if filters.date_to:
            query += " AND substr(timestamp_utc, 1, 10) <= ?"
            params.append(filters.date_to)
        if filters.symbol:
            query += " AND symbol = ?"
            params.append(filters.symbol)
        if filters.decision:
            query += " AND decision = ?"
            params.append(filters.decision)
        if filters.permission:
            query += " AND trade_permission = ?"
            params.append(filters.permission)
        if filters.min_score > 0:
            query += " AND max(buy_score, sell_score) >= ?"
            params.append(filters.min_score)
        query += " ORDER BY timestamp_utc DESC, id DESC"
        with self._connect() as conn:
            return [entry_from_row(row) for row in conn.execute(query, params).fetchall()]

    def get_entry(self, entry_id: int) -> JournalEntry | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
            return entry_from_row(row) if row else None

    def update_note(self, entry_id: int, note: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE journal_entries SET note = ? WHERE id = ?", (note, entry_id))
            conn.commit()

    def delete_entry(self, entry_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
            conn.commit()

    # Phase 17 field whitelist for update_trade_outcome
    _UPDATE_WHITELIST = frozenset({
        "result", "result_r", "result_pct", "closed_at", "exit_reason",
        "actual_lot", "planned_lot", "trade_status", "opened_at", "result_amount",
        "planned_entry", "actual_entry", "planned_sl", "actual_sl", "planned_tp", "actual_tp", "actual_exit",
        "realized_effective_rr",
        "manual_mistake_tags", "auto_mistake_tags",
        "execution_quality_score",
        "mt5_deal_id", "mt5_order_id", "mt5_position_id", "synced_from", "synced_at_utc",
        "note",
    })

    def update_trade_outcome(self, entry_id: int, updates: dict[str, object]) -> None:
        """Safely update trade-outcome fields for a journal entry.

        Only whitelisted fields are accepted.  Tags are normalised via
        :func:`tags_to_json`.  Unknown / unsafe keys are silently dropped.
        Empty or all-rejected updates are a no-op.
        """
        if not isinstance(updates, dict) or not updates:
            return

        safe: dict[str, object] = {}
        for key, value in updates.items():
            if key not in self._UPDATE_WHITELIST:
                continue
            if key in ("manual_mistake_tags", "auto_mistake_tags"):
                safe[key] = tags_to_json(value)
            elif key in ("result_r", "result_pct", "actual_lot", "planned_lot",
                         "planned_entry", "actual_entry", "planned_sl", "actual_sl", "planned_tp", "actual_tp", "actual_exit",
                         "realized_effective_rr", "execution_quality_score", "result_amount"):
                try:
                    safe[key] = float(value) if value is not None else None
                except (TypeError, ValueError):
                    safe[key] = None
            elif key in {"closed_at", "opened_at"}:
                safe[key] = str(value or "")
            elif key == "trade_status":
                safe[key] = normalize_trade_status(value)
            elif key in {"mt5_deal_id", "mt5_order_id", "mt5_position_id"}:
                try:
                    safe[key] = int(value) if value not in (None, "") else None
                except (TypeError, ValueError):
                    safe[key] = None
            else:
                safe[key] = str(value or "") if not isinstance(value, (int, float)) else value

        if not safe:
            return

        columns = ", ".join(f"{col} = ?" for col in safe)
        values = list(safe.values())
        values.append(entry_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE journal_entries SET {columns} WHERE id = ?",
                values,
            )
            conn.commit()

    def update_lifecycle(self, entry_id: int, updates: dict[str, object], *, auto_analyze: bool = True) -> dict[str, object] | None:
        """Update planned/actual trade fields and derive outcome metrics.

        The UI sends loosely typed values. This method normalises lifecycle
        state, computes result_r/result_pct/realized_effective_rr when enough
        price data exists, persists the row, and optionally refreshes mistake
        detection/execution quality for closed trades.
        """
        entry = self.get_entry(entry_id)
        if entry is None:
            return None

        merged = asdict(entry)
        merged.update(updates or {})
        status = normalize_trade_status(merged.get("trade_status"))
        if merged.get("closed_at"):
            status = "closed"
        elif merged.get("opened_at") or merged.get("actual_entry") is not None:
            status = "opened" if status == "planned" else status
        merged["trade_status"] = status

        outcome = calculate_trade_outcome(merged)
        if outcome:
            merged.update(outcome)
            if "realized_effective_rr" not in updates:
                merged["realized_effective_rr"] = outcome.get("result_r")
        elif any(key in updates for key in ("actual_entry", "planned_entry", "actual_sl", "planned_sl", "actual_exit")):
            merged["result_r"] = None
            merged["result_pct"] = None
            merged["realized_effective_rr"] = None

        payload = {key: merged.get(key) for key in self._UPDATE_WHITELIST if key in merged}
        self.update_trade_outcome(entry_id, payload)

        analysis: dict[str, object] | None = None
        if auto_analyze and status == "closed":
            analysis = self.apply_execution_analysis_to_entry(entry_id)

        updated = self.get_entry(entry_id)
        return {
            "entry": asdict(updated) if updated else None,
            "outcome": outcome,
            "execution_analysis": analysis,
        }

    def sync_mt5_closed_trades(self, trades: list[dict[str, object]]) -> dict[str, object]:
        """Import MT5 closed trades into journal, updating existing rows when possible."""
        summary = {"received": len(trades), "created": 0, "updated": 0, "skipped": 0, "errors": []}
        synced_ids: list[int] = []
        for trade in trades:
            try:
                entry_id = self._find_mt5_sync_entry(trade)
                payload = self._mt5_trade_update_payload(trade)
                if entry_id is None:
                    entry_id = self.create(journal_entry_from_mt5_trade(trade))
                    summary["created"] = int(summary["created"]) + 1
                else:
                    self.update_lifecycle(entry_id, payload)
                    summary["updated"] = int(summary["updated"]) + 1
                synced_ids.append(int(entry_id))
            except sqlite3.IntegrityError:
                summary["skipped"] = int(summary["skipped"]) + 1
            except Exception as exc:  # pragma: no cover - defensive sync boundary.
                summary["errors"].append(str(exc))
        summary["synced_entry_ids"] = synced_ids
        return summary

    def _find_mt5_sync_entry(self, trade: dict[str, object]) -> int | None:
        deal_id = _safe_int(trade.get("mt5_deal_id"))
        position_id = _safe_int(trade.get("mt5_position_id"))
        with self._connect() as conn:
            if deal_id is not None:
                row = conn.execute("SELECT id FROM journal_entries WHERE mt5_deal_id = ?", (deal_id,)).fetchone()
                if row:
                    return int(row["id"])
            if position_id is not None:
                row = conn.execute("SELECT id FROM journal_entries WHERE mt5_position_id = ?", (position_id,)).fetchone()
                if row:
                    return int(row["id"])

            symbol = str(trade.get("symbol") or "")
            broker_symbol = str(trade.get("broker_symbol") or "")
            side = str(trade.get("side") or "")
            closed_at = str(trade.get("closed_at") or "")
            rows = conn.execute(
                "SELECT id, closed_at, timestamp_utc FROM journal_entries "
                "WHERE (symbol = ? OR broker_symbol = ?) AND selected_scenario = ? "
                "AND (mt5_deal_id IS NULL AND mt5_position_id IS NULL) "
                "AND (closed_at IS NULL OR closed_at = '') "
                "AND (trade_status IS NULL OR trade_status IN ('planned', 'opened')) "
                "ORDER BY id DESC LIMIT 20",
                (symbol, broker_symbol, side),
            ).fetchall()
        close_time = _parse_utc(closed_at)
        for row in rows:
            candidate_time = _parse_utc(row["closed_at"] or row["timestamp_utc"])
            if close_time and candidate_time and abs((close_time - candidate_time).total_seconds()) <= 86400:
                return int(row["id"])
        return None

    def _mt5_trade_update_payload(self, trade: dict[str, object]) -> dict[str, object]:
        amount = _safe_float(trade.get("result_amount"))
        result = "win" if amount and amount > 0 else "loss" if amount and amount < 0 else "breakeven"
        return {
            "trade_status": "closed",
            "opened_at": trade.get("opened_at") or "",
            "closed_at": trade.get("closed_at") or "",
            "actual_entry": trade.get("actual_entry"),
            "actual_exit": trade.get("actual_exit"),
            "actual_lot": trade.get("actual_lot"),
            "result_amount": trade.get("result_amount"),
            "result": result,
            "exit_reason": trade.get("exit_reason") or "mt5_history",
            "mt5_deal_id": trade.get("mt5_deal_id"),
            "mt5_order_id": trade.get("mt5_order_id"),
            "mt5_position_id": trade.get("mt5_position_id"),
            "synced_from": "mt5_history",
            "synced_at_utc": utc_now(),
        }

    def apply_execution_analysis_to_entry(
        self, entry_id: int, *, previous_limit: int = 50
    ) -> dict | None:
        """Run mistake detector and execution quality analysis on a closed entry.

        Retrieves the entry, converts to dict, runs
        :func:`core.trade_mistake_detector.detect_trade_mistakes` and
        :func:`core.execution_quality_engine.calculate_execution_quality`,
        then saves the results via :meth:`update_trade_outcome`.

        Does **not** affect live trade decisions, scoring, or gates.
        Returns ``None`` if the entry does not exist.
        """
        entry = self.get_entry(entry_id)
        if entry is None:
            return None

        from core.trade_mistake_detector import detect_trade_mistakes
        from core.execution_quality_engine import calculate_execution_quality

        trade_dict: dict[str, object] = asdict(entry)
        # Use timestamp_utc as opened_at if not present
        if not trade_dict.get("opened_at"):
            trade_dict["opened_at"] = trade_dict.get("timestamp_utc")

        previous = self.list_closed_trades_for_account_guard(limit=previous_limit)

        # Detect mistakes
        detection = detect_trade_mistakes(trade_dict, previous_trades=previous)

        # Merge auto tags into trade dict for execution_quality
        if isinstance(detection, dict):
            trade_dict["auto_mistake_tags"] = detection.get("auto_mistake_tags")

        # Calculate execution quality (don't reuse existing — recompute fresh)
        quality = calculate_execution_quality(trade_dict, use_existing_score=False)

        # Build update payload
        updates: dict[str, object] = {}
        if isinstance(detection, dict):
            updates["auto_mistake_tags"] = detection.get("auto_mistake_tags")
        if isinstance(quality, dict) and "execution_quality_score" in quality:
            updates["execution_quality_score"] = quality["execution_quality_score"]

        if updates:
            self.update_trade_outcome(entry_id, updates)

        return {
            "detection": detection,
            "execution_quality": quality,
            "updated_entry_id": entry_id,
        }

    def symbols(self) -> list[str]:
        with self._connect() as conn:
            return [row[0] for row in conn.execute("SELECT DISTINCT symbol FROM journal_entries ORDER BY symbol").fetchall()]

    def stats(self) -> dict[str, object]:
        entries = self.list_entries()
        counts = {"ready": 0, "watch": 0, "wait": 0, "stand_aside": 0}
        symbol_counts: dict[str, int] = {}
        for entry in entries:
            if entry.decision in {"ready", "watch"}:
                counts[entry.decision] += 1
            elif entry.decision in {"wait", "wait_for_confirmation"}:
                counts["wait"] += 1
            else:
                counts["stand_aside"] += 1
            symbol_counts[entry.symbol] = symbol_counts.get(entry.symbol, 0) + 1
        top_symbol = max(symbol_counts.items(), key=lambda item: item[1])[0] if symbol_counts else "--"
        return {"total": len(entries), **counts, "top_symbol": top_symbol}

    def performance_summary(self, limit: int = 1000) -> dict[str, object]:
        """Summarise closed-trade performance from journal outcome fields."""
        trades = self.list_closed_trades_for_account_guard(limit=limit)
        return build_performance_summary(trades)

    def list_closed_trades_for_account_guard(self, limit: int = 500) -> list[dict[str, object]]:
        """Trả về danh sách closed trades phục vụ Account Guard và Phase 17 engines.

        Returns list of dict with keys:
            result_r, result_pct, closed_at, exit_reason, actual_lot, planned_lot,
            symbol, direction (selected_scenario)
        Phase 17 additions:
            planned_entry, actual_entry, planned_sl, actual_sl, planned_tp, actual_tp,
            actual_exit, setup_type, regime, session, m15_quality, spread_at_entry,
            expected_effective_rr, realized_effective_rr,
            manual_mistake_tags (list), auto_mistake_tags (list),
            execution_quality_score
        Only includes entries where closed_at is not null.
        """
        select_cols = (
            "result_r", "result_pct", "closed_at", "exit_reason",
            "actual_lot", "planned_lot", "symbol", "selected_scenario",
            "trade_status", "opened_at", "result_amount",
            "planned_entry", "actual_entry", "planned_sl", "actual_sl",
            "planned_tp", "actual_tp", "actual_exit",
            "setup_type", "regime", "session", "m15_quality",
            "spread_at_entry", "expected_effective_rr", "realized_effective_rr",
            "manual_mistake_tags", "auto_mistake_tags", "execution_quality_score",
        )
        cols_str = ", ".join(select_cols)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {cols_str} FROM journal_entries "
                "WHERE closed_at IS NOT NULL AND closed_at != '' "
                "ORDER BY closed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        trades: list[dict[str, object]] = []
        for row in rows:
            trade: dict[str, object] = {}
            for key in (
                "result_r", "result_pct", "closed_at", "exit_reason",
                "actual_lot", "planned_lot", "symbol", "trade_status", "opened_at", "result_amount",
                "planned_entry", "actual_entry", "planned_sl", "actual_sl",
                "planned_tp", "actual_tp", "actual_exit",
                "setup_type", "regime", "session", "m15_quality",
                "spread_at_entry", "expected_effective_rr", "realized_effective_rr",
                "execution_quality_score",
            ):
                try:
                    trade[key] = row[key]
                except (KeyError, IndexError):
                    trade[key] = None
            try:
                trade["direction"] = row["selected_scenario"]
            except (KeyError, IndexError):
                trade["direction"] = None

            # Parse tag JSON strings
            trade["manual_mistake_tags"] = tags_from_json(
                row["manual_mistake_tags"] if "manual_mistake_tags" in row.keys() else None
            )
            trade["auto_mistake_tags"] = tags_from_json(
                row["auto_mistake_tags"] if "auto_mistake_tags" in row.keys() else None
            )

            trades.append(trade)
        return trades

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn
