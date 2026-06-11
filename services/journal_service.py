from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.paths import PROJECT_ROOT, journal_db_path


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
        "actual_lot", "planned_lot",
        "actual_entry", "actual_sl", "actual_tp", "actual_exit",
        "realized_effective_rr",
        "manual_mistake_tags", "auto_mistake_tags",
        "execution_quality_score",
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
                         "actual_entry", "actual_sl", "actual_tp", "actual_exit",
                         "realized_effective_rr", "execution_quality_score"):
                try:
                    safe[key] = float(value) if value is not None else None
                except (TypeError, ValueError):
                    safe[key] = None
            elif key == "closed_at":
                safe[key] = str(value or "")
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
                "actual_lot", "planned_lot", "symbol",
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
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


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
