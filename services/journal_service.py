from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT, journal_db_path
from core.safe_types import optional_float


@dataclass(frozen=True, slots=True)
class JournalEntry:
    id: int | None
    timestamp_utc: str
    saved_at_utc: str
    symbol: str
    broker_symbol: str
    mode: str
    data_source: str
    market_regime: str
    decision: str
    direction_bias: str
    trade_permission: str
    buy_score: int
    sell_score: int
    selected_scenario: str
    entry_zone: str
    stop_loss: str
    take_profit: str
    risk_reward: str
    suggested_lot: float | None
    ai_commentary: str
    analysis_json: str
    user_action: str = ""
    result: str = ""
    note: str = ""
    # Phase 7 — account guard fields (đợt 1)
    result_r: float | None = None
    result_pct: float | None = None
    closed_at: str | None = None
    exit_reason: str | None = None
    actual_lot: float | None = None
    planned_lot: float | None = None
    # Phase 17 — journal execution fields (đợt 2)
    planned_entry: float | None = None
    actual_entry: float | None = None
    planned_sl: float | None = None
    actual_sl: float | None = None
    planned_tp: float | None = None
    actual_tp: float | None = None
    actual_exit: float | None = None
    setup_type: str | None = None
    regime: str | None = None
    session: str | None = None
    m15_quality: str | None = None
    spread_at_entry: float | None = None
    expected_effective_rr: float | None = None
    realized_effective_rr: float | None = None
    manual_mistake_tags: str | None = None
    auto_mistake_tags: str | None = None
    execution_quality_score: int | None = None
    # Trade lifecycle fields
    trade_status: str | None = "planned"
    opened_at: str | None = None
    result_amount: float | None = None
    mt5_deal_id: int | None = None
    mt5_order_id: int | None = None
    mt5_position_id: int | None = None
    synced_from: str | None = None
    synced_at_utc: str | None = None


@dataclass(frozen=True, slots=True)
class JournalFilter:
    date_from: str | None = None
    date_to: str | None = None
    symbol: str | None = None
    decision: str | None = None
    permission: str | None = None
    min_score: int = 0


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
                conn.executescript(migration.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at_utc) VALUES (?, ?)",
                    (version, utc_now()),
                )
            conn.commit()

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

        from dataclasses import asdict
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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _safe_float(value: object) -> float | None:
    """Parse float safely, returning None for bad input."""
    return optional_float(value)


def _safe_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_utc(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_entry_from_zone(zone: object) -> float | None:
    """Extract the mid-point of an entry zone like [1.0840, 1.0860]."""
    if not isinstance(zone, list) or len(zone) < 2:
        return None
    lo = _safe_float(zone[0])
    hi = _safe_float(zone[1])
    if lo is not None and hi is not None:
        return round((lo + hi) / 2, 6)
    return None


def _parse_take_profit_first(tp: object) -> float | None:
    """Extract the first take-profit value from a list or numeric."""
    if tp is None:
        return None
    if isinstance(tp, list):
        return _safe_float(tp[0]) if tp else None
    return _safe_float(tp)


def journal_entry_from_analysis(analysis: dict[str, Any], *, mode: str, note: str = "") -> JournalEntry:
    scores = analysis.get("scenario_scores", {}) if isinstance(analysis.get("scenario_scores"), dict) else {}
    buy_score = int(scores.get("buy", {}).get("total", 0))
    sell_score = int(scores.get("sell", {}).get("total", 0))
    scenarios = analysis.get("scenarios", []) if isinstance(analysis.get("scenarios"), list) else []
    scenario = next((item for item in scenarios if isinstance(item, dict) and item.get("type") in {"buy", "sell"}), scenarios[0] if scenarios else {})
    scenario = scenario if isinstance(scenario, dict) else {}
    decision = analysis.get("decision_summary", {}) if isinstance(analysis.get("decision_summary"), dict) else {}
    permission = analysis.get("trade_permission", {}) if isinstance(analysis.get("trade_permission"), dict) else {}
    data_quality = analysis.get("data_quality", {}) if isinstance(analysis.get("data_quality"), dict) else {}
    market_regime = analysis.get("market_regime", {}) if isinstance(analysis.get("market_regime"), dict) else {}
    macro = analysis.get("macro", {}) if isinstance(analysis.get("macro"), dict) else {}
    sizing = scenario.get("position_sizing", {}) if isinstance(scenario.get("position_sizing"), dict) else {}

    # Phase 17 Đợt 2 — extract from analysis_result
    planned_entry = _parse_entry_from_zone(scenario.get("entry_zone"))
    planned_sl = _safe_float(scenario.get("stop_loss"))
    planned_tp = _parse_take_profit_first(scenario.get("take_profit"))
    setup_type = str(scenario.get("trigger_type") or scenario.get("type") or decision.get("best_scenario", ""))
    regime_val = str(market_regime.get("primary", ""))
    m15_qual = str(scenario.get("m15_quality") or "")
    spread_at_entry = _safe_float(data_quality.get("spread_points") or data_quality.get("spread_price"))
    expected_rr = _safe_float(scenario.get("expected_effective_rr"))

    eq = analysis.get("execution_quality")
    if not isinstance(eq, dict):
        eq = {}
    exec_qual_score = int(eq.get("execution_quality_score")) if eq.get("execution_quality_score") is not None else (
        int(analysis.get("execution_quality_score")) if analysis.get("execution_quality_score") is not None else None
    )

    manual_tags = tags_to_json(analysis.get("manual_mistake_tags"))
    auto_tags = tags_to_json(analysis.get("auto_mistake_tags") or scenario.get("auto_mistake_tags"))

    return JournalEntry(
        id=None,
        timestamp_utc=normalize_utc_timestamp(str(analysis.get("timestamp") or utc_now())),
        saved_at_utc=utc_now(),
        symbol=str(analysis.get("symbol", "")),
        broker_symbol=str(data_quality.get("broker_symbol") or analysis.get("broker_symbol") or ""),
        mode=mode,
        data_source=str(data_quality.get("price_source", "MT5")),
        market_regime=str(market_regime.get("primary", "")),
        decision=str(decision.get("action", "")),
        direction_bias=str(analysis.get("direction_bias", "")),
        trade_permission=str(permission.get("status", "")),
        buy_score=buy_score,
        sell_score=sell_score,
        selected_scenario=str(scenario.get("type", decision.get("best_scenario", ""))),
        entry_zone=json.dumps(scenario.get("entry_zone", ""), ensure_ascii=False),
        stop_loss=str(scenario.get("stop_loss", "")),
        take_profit=json.dumps(scenario.get("take_profit", ""), ensure_ascii=False),
        risk_reward=str(scenario.get("risk_reward", "")),
        suggested_lot=float(sizing["suggested_lot"]) if sizing.get("suggested_lot") not in (None, "") else None,
        ai_commentary=str(macro.get("ai_summary", "")),
        analysis_json=json.dumps(analysis, ensure_ascii=False),
        note=note,
        # Phase 17 Đợt 2
        planned_entry=planned_entry,
        actual_entry=None,
        planned_sl=planned_sl,
        actual_sl=None,
        planned_tp=planned_tp,
        actual_tp=None,
        actual_exit=None,
        setup_type=setup_type,
        regime=regime_val,
        session=None,
        m15_quality=m15_qual if m15_qual else None,
        spread_at_entry=spread_at_entry,
        expected_effective_rr=expected_rr,
        realized_effective_rr=None,
        manual_mistake_tags=manual_tags if manual_tags != "[]" else None,
        auto_mistake_tags=auto_tags if auto_tags != "[]" else None,
        execution_quality_score=exec_qual_score,
        trade_status="planned",
        opened_at=None,
        result_amount=None,
    )


def journal_entry_from_scanner_row(row: dict[str, Any], *, note: str = "") -> JournalEntry:
    now = utc_now()
    payload = {key: value for key, value in row.items() if key != "analysis_result"}

    # Phase 17 Đợt 2 — extract from scanner row
    row_regime = str(row.get("market_regime", ""))
    row_m15 = str(row.get("m15_quality") or "")
    row_expected_rr = _safe_float(row.get("expected_effective_rr"))
    row_setup_type = str(row.get("entry_status") or row.get("scanner_group") or "")
    row_exec_qual = int(row.get("execution_quality_score")) if row.get("execution_quality_score") is not None else None
    row_manual_tags = tags_to_json(row.get("manual_mistake_tags"))
    row_auto_tags = tags_to_json(row.get("auto_mistake_tags"))
    row_planned_entry = _parse_entry_from_zone(row.get("entry_zone"))
    row_planned_sl = _safe_float(row.get("stop_loss"))
    row_planned_tp = _parse_take_profit_first(row.get("take_profit"))
    row_planned_lot = _safe_float(row.get("planned_lot"))
    row_actual_lot = _safe_float(row.get("actual_lot"))
    row_spread = _safe_float(row.get("spread_at_entry") or row.get("spread_points"))
    row_session = str(row.get("session") or "")

    return JournalEntry(
        id=None,
        timestamp_utc=now,
        saved_at_utc=now,
        symbol=str(row.get("symbol", "")),
        broker_symbol=str(row.get("broker_symbol", "")),
        mode="scanner_detail",
        data_source="MT5",
        market_regime=str(row.get("market_regime", "")),
        decision=str(row.get("scanner_action", "")),
        direction_bias=str(row.get("direction_bias", "")),
        trade_permission=str(row.get("trade_permission", "")),
        buy_score=int(row.get("buy_score", 0)),
        sell_score=int(row.get("sell_score", 0)),
        selected_scenario=str(row.get("best_side", "")),
        entry_zone="",
        stop_loss="",
        take_profit="",
        risk_reward=str(row.get("risk_reward") or ""),
        suggested_lot=None,
        ai_commentary=str(row.get("short_reason", "")),
        analysis_json=json.dumps(payload, ensure_ascii=False),
        note=note,
        # Phase 17 Đợt 2
        planned_lot=row_planned_lot,
        actual_lot=row_actual_lot,
        planned_entry=row_planned_entry,
        actual_entry=None,
        planned_sl=row_planned_sl,
        actual_sl=None,
        planned_tp=row_planned_tp,
        actual_tp=None,
        actual_exit=None,
        setup_type=row_setup_type if row_setup_type else None,
        regime=row_regime if row_regime else None,
        session=row_session if row_session else None,
        m15_quality=row_m15 if row_m15 else None,
        spread_at_entry=row_spread,
        expected_effective_rr=row_expected_rr,
        realized_effective_rr=None,
        manual_mistake_tags=row_manual_tags if row_manual_tags != "[]" else None,
        auto_mistake_tags=row_auto_tags if row_auto_tags != "[]" else None,
        execution_quality_score=row_exec_qual,
        trade_status="planned",
        opened_at=None,
        result_amount=None,
    )


def journal_entry_from_mt5_trade(trade: dict[str, object]) -> JournalEntry:
    now = utc_now()
    amount = _safe_float(trade.get("result_amount"))
    result = "win" if amount and amount > 0 else "loss" if amount and amount < 0 else "breakeven"
    payload = {"source": "mt5_history", "trade": trade}
    return JournalEntry(
        id=None,
        timestamp_utc=normalize_utc_timestamp(str(trade.get("opened_at") or trade.get("closed_at") or now)),
        saved_at_utc=now,
        symbol=str(trade.get("symbol") or trade.get("broker_symbol") or ""),
        broker_symbol=str(trade.get("broker_symbol") or ""),
        mode="mt5_sync",
        data_source="MT5",
        market_regime="",
        decision="closed",
        direction_bias=str(trade.get("side") or ""),
        trade_permission="",
        buy_score=0,
        sell_score=0,
        selected_scenario=str(trade.get("side") or ""),
        entry_zone="",
        stop_loss="",
        take_profit="",
        risk_reward="",
        suggested_lot=None,
        ai_commentary="Imported from MT5 history.",
        analysis_json=json.dumps(payload, ensure_ascii=False),
        user_action="",
        result=result,
        note="",
        result_r=None,
        result_pct=None,
        closed_at=str(trade.get("closed_at") or ""),
        exit_reason=str(trade.get("exit_reason") or "mt5_history"),
        actual_lot=_safe_float(trade.get("actual_lot")),
        planned_lot=None,
        planned_entry=None,
        actual_entry=_safe_float(trade.get("actual_entry")),
        planned_sl=None,
        actual_sl=None,
        planned_tp=None,
        actual_tp=None,
        actual_exit=_safe_float(trade.get("actual_exit")),
        setup_type="mt5_history",
        regime=None,
        session=None,
        m15_quality=None,
        spread_at_entry=None,
        expected_effective_rr=None,
        realized_effective_rr=None,
        manual_mistake_tags=None,
        auto_mistake_tags=None,
        execution_quality_score=None,
        trade_status="closed",
        opened_at=str(trade.get("opened_at") or ""),
        result_amount=amount,
        mt5_deal_id=_safe_int(trade.get("mt5_deal_id")),
        mt5_order_id=_safe_int(trade.get("mt5_order_id")),
        mt5_position_id=_safe_int(trade.get("mt5_position_id")),
        synced_from="mt5_history",
        synced_at_utc=now,
    )


def entry_to_record(entry: JournalEntry) -> dict[str, object]:
    data = asdict(entry)
    data.pop("id", None)
    return data


def entry_from_row(row: sqlite3.Row) -> JournalEntry:
    fields = {}
    for field_name in JournalEntry.__dataclass_fields__:
        try:
            fields[field_name] = row[field_name]
        except KeyError:
            fields[field_name] = None
    return JournalEntry(**fields)


# ---------------------------------------------------------------------------
# Tag normalisation helpers
# ---------------------------------------------------------------------------


def normalize_tag_list(value: object) -> list[str]:
    """Normalise flexible tag input into a deduplicated list of lowercase strings.

    Handles:
    - list/tuple/set → lowercase, strip, drop empty, dedup
    - JSON string like ``'["a","b"]'`` → parse
    - comma-separated string → split
    - None / non-string → ``[]``
    Never raises.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                s = item.strip().lower()
                if s and s not in seen:
                    seen.add(s)
                    result.append(s)
        return result
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return normalize_tag_list(parsed)
            except (json.JSONDecodeError, ValueError):
                pass
        # Comma-separated
        parts = [p.strip().lower() for p in stripped.split(",")]
        seen: set[str] = set()
        result: list[str] = []
        for p in parts:
            if p and p not in seen:
                seen.add(p)
                result.append(p)
        return result
    return []


def tags_to_json(value: object) -> str:
    """Convert any tag input to a compact JSON string (always an array)."""
    tags = normalize_tag_list(value)
    return json.dumps(tags, ensure_ascii=False)


def tags_from_json(value: object) -> list[str]:
    """Parse a tag JSON string back to a list; delegates to :func:`normalize_tag_list`."""
    return normalize_tag_list(value)


def normalize_trade_status(value: object) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "plan": "planned",
        "planned": "planned",
        "open": "opened",
        "opened": "opened",
        "close": "closed",
        "closed": "closed",
        "cancel": "cancelled",
        "cancelled": "cancelled",
        "miss": "missed",
        "missed": "missed",
    }
    return aliases.get(raw, "planned")


def calculate_trade_outcome(trade: dict[str, object]) -> dict[str, float | str]:
    """Calculate R-multiple and percent result from journal trade data.

    Uses actual values first, falling back to planned values. Result R is
    positive when price moves in the selected scenario direction.
    """
    side = str(trade.get("selected_scenario") or trade.get("direction") or "").strip().lower()
    if side not in {"buy", "sell"}:
        return {}

    entry = _safe_float(trade.get("actual_entry"))
    if entry is None:
        entry = _safe_float(trade.get("planned_entry"))
    stop = _safe_float(trade.get("actual_sl"))
    if stop is None:
        stop = _safe_float(trade.get("planned_sl"))
    exit_price = _safe_float(trade.get("actual_exit"))
    if entry is None or stop is None or exit_price is None:
        return {}

    risk = abs(entry - stop)
    if risk <= 0:
        return {}

    signed_move = exit_price - entry if side == "buy" else entry - exit_price
    result_r = signed_move / risk
    result_pct = (signed_move / entry * 100) if entry else 0.0
    label = "win" if result_r > 0 else "loss" if result_r < 0 else "breakeven"
    return {
        "result_r": round(result_r, 3),
        "result_pct": round(result_pct, 3),
        "realized_effective_rr": round(result_r, 3),
        "result": label,
    }


def build_performance_summary(trades: list[dict[str, object]]) -> dict[str, object]:
    valid = [trade for trade in trades if _safe_float(trade.get("result_r")) is not None]
    valid_for_curve = sorted(valid, key=lambda item: str(item.get("closed_at") or ""))
    results = [float(_safe_float(trade.get("result_r")) or 0.0) for trade in valid_for_curve]
    amounts = [float(value) for value in (_safe_float(trade.get("result_amount")) for trade in trades) if value is not None]
    outcome_values = results if results else amounts
    wins = [value for value in outcome_values if value > 0]
    losses = [value for value in outcome_values if value < 0]
    breakeven = [value for value in outcome_values if value == 0]
    r_wins = [value for value in results if value > 0]
    r_losses = [value for value in results if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    avg_quality_values = [
        float(score)
        for score in (_safe_float(trade.get("execution_quality_score")) for trade in valid)
        if score is not None
    ]
    summary = {
        "closed_trades": len(trades),
        "r_trades": len(valid),
        "amount_trades": len(amounts),
        "win_count": len(wins),
        "loss_count": len(losses),
        "breakeven_count": len(breakeven),
        "win_rate": round(len(wins) / len(outcome_values) * 100, 2) if outcome_values else 0.0,
        "expectancy_r": round(sum(results) / len(results), 3) if results else 0.0,
        "total_r": round(sum(results), 3) if results else 0.0,
        "average_win_r": round(sum(r_wins) / len(r_wins), 3) if r_wins else 0.0,
        "average_loss_r": round(sum(r_losses) / len(r_losses), 3) if r_losses else 0.0,
        "net_amount": round(sum(amounts), 2) if amounts else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else (round(gross_profit, 3) if gross_profit > 0 else 0.0),
        "max_drawdown_r": round(max_drawdown_r(results), 3),
        "average_execution_quality": round(sum(avg_quality_values) / len(avg_quality_values), 1) if avg_quality_values else 0.0,
    }
    return {
        "summary": summary,
        "by_symbol": group_performance(trades, "symbol"),
        "by_setup": group_performance(trades, "setup_type"),
        "by_regime": group_performance(trades, "regime"),
        "by_session": group_performance(trades, "session"),
        "by_direction": group_performance(trades, "direction"),
        "recent": recent_trade_rows(trades, limit=12),
    }


def group_performance(trades: list[dict[str, object]], key: str, *, limit: int = 8) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, float | None]]] = {}
    for trade in trades:
        label = str(trade.get(key) or "--").strip() or "--"
        result = _safe_float(trade.get("result_r"))
        amount = _safe_float(trade.get("result_amount"))
        if result is None and amount is None:
            continue
        groups.setdefault(label, []).append({"result_r": result, "amount": amount})
    rows: list[dict[str, object]] = []
    for label, items in groups.items():
        results = [float(item["result_r"]) for item in items if item["result_r"] is not None]
        amounts = [float(item["amount"]) for item in items if item["amount"] is not None]
        outcome_values = results if results else amounts
        wins = [value for value in outcome_values if value > 0]
        losses = [value for value in outcome_values if value < 0]
        rows.append({
            "label": label,
            "trades": len(items),
            "win_rate": round(len(wins) / len(outcome_values) * 100, 2) if outcome_values else 0.0,
            "expectancy_r": round(sum(results) / len(results), 3) if results else 0.0,
            "total_r": round(sum(results), 3),
            "net_amount": round(sum(amounts), 2) if amounts else 0.0,
            "profit_factor": _profit_factor(wins, losses),
        })
    rows.sort(key=lambda item: (int(item["trades"]), float(item["total_r"])), reverse=True)
    return rows[:limit]


def recent_trade_rows(trades: list[dict[str, object]], *, limit: int = 12) -> list[dict[str, object]]:
    rows = sorted(trades, key=lambda item: str(item.get("closed_at") or ""), reverse=True)
    return [
        {
            "closed_at": trade.get("closed_at") or "--",
            "symbol": trade.get("symbol") or "--",
            "direction": trade.get("direction") or "--",
            "result_r": round(float(_safe_float(trade.get("result_r"))), 3) if _safe_float(trade.get("result_r")) is not None else None,
            "result_amount": _safe_float(trade.get("result_amount")),
            "exit_reason": trade.get("exit_reason") or "--",
            "execution_quality_score": trade.get("execution_quality_score"),
        }
        for trade in rows[:limit]
    ]


def _profit_factor(wins: list[float], losses: list[float]) -> float:
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss > 0:
        return round(gross_profit / gross_loss, 3)
    return round(gross_profit, 3) if gross_profit > 0 else 0.0


def max_drawdown_r(results: list[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for value in results:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_utc_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return utc_now()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
