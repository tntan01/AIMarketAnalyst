"""Contract tests for the News domain models (contract §5, plan lô L1.3).

``core/news_models.py`` is the single owner of the six domain models
(registered at contract §11b).  Its contract, verified here:

* every frozen string enum of §2/§4.2-§4.6 pins the EXACT persisted string —
  renaming a member value is red;
* every enum set of the models matches the CHECK constraints of the L1.2
  migration ``data/migrations/news/001_create_news_db.sql`` in BOTH
  directions (no value the model allows can be rejected, no value SQL
  allows may be missing from the model) — the SQL text is read as the
  machine source of truth;
* for the 5 table-mapped models the dataclass field set matches the column
  set (PRAGMA table_info on a temp DB that applied the migration) one-to-one,
  with exactly the three deliberate domain renames for the JSON columns
  (``currencies_json``→``currencies``, ``evidence_item_ids_json``→
  ``evidence_item_ids``, ``input_snapshot_json``→``input_snapshot``);
* every model constructs from pure domain values without any mock or I/O
  (L2); models are frozen; Optional fields accept/keep None where the SQL
  column is nullable, and NOT NULL columns map to mandatory dataclass fields;
* ``StoreState`` reports state + last successful ingest time per signal with
  two explicit typed components — never a bare dict across the boundary
  (C3, contract §8);
* core layer boundary: no services/ui/controllers/Qt import and no display
  strings (Vietnamese) in the module source (L2, L3).
"""

from __future__ import annotations

import dataclasses
import re
import sqlite3
import typing
from pathlib import Path

import pytest

from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    ImpactHint,
    IngestProducer,
    IngestRun,
    IngestRunStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    RateObservation,
    RateSource,
    StoreState,
    StoreStatus,
    TrendVerdict,
    VerdictConfidence,
    VerdictDirection,
    VerdictHorizon,
    VerdictScopeType,
)

MIGRATION_SQL = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "migrations"
    / "news"
    / "001_create_news_db.sql"
)
NEWS_MODELS_PY = (
    Path(__file__).resolve().parents[1] / "core" / "news_models.py"
)


# ---- enums: every name -> the exact string §4 persists -------------------


ENUM_EXPECTED_VALUES: dict[type, dict[str, str]] = {
    EventImpact: {"HIGH": "high", "MEDIUM": "medium", "LOW": "low", "NON": "non"},
    EventStatus: {
        "SCHEDULED": "scheduled",
        "RELEASED": "released",
        "STALE": "stale",
    },
    EventSource: {
        "FF_JSON": "ff_json",
        "FF_HTML": "ff_html",
        "USER": "user",
        "IMPORT": "import",
    },
    NewsItemKind: {
        "HEADLINE": "headline",
        "STATEMENT": "statement",
        "USER_NOTE": "user_note",
    },
    NewsItemSource: {
        "GOOGLE_NEWS_RSS": "google_news_rss",
        "FXSTREET_RSS": "fxstreet_rss",
        "INVESTING_RSS": "investing_rss",
        "USER": "user",
        "IMPORT": "import",
    },
    ImpactHint: {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"},
    RateSource: {
        "FRED": "fred",
        "FF_HTML": "ff_html",
        "CONFIG_FALLBACK": "config_fallback",
    },
    IngestProducer: {
        "FF_CRAWLER": "ff_crawler",
        "RSS": "rss",
        "FRED": "fred",
        "USER": "user",
        "ON_DEMAND_LOOKUP": "on_demand_lookup",
    },
    IngestRunStatus: {"OK": "ok", "PARTIAL": "partial", "FAILED": "failed"},
    VerdictScopeType: {"PAIR": "pair", "CURRENCY": "currency"},
    VerdictHorizon: {"SHORT": "short", "MID": "mid", "LONG": "long"},
    VerdictDirection: {
        "BULLISH": "bullish",
        "BEARISH": "bearish",
        "NEUTRAL": "neutral",
        "INSUFFICIENT_DATA": "insufficient_data",
    },
    VerdictConfidence: {
        "HIGH": "high",
        "MEDIUM": "medium",
        "LOW": "low",
        "NONE": "none",
    },
    StoreStatus: {
        "FRESH": "fresh",
        "DEGRADED": "degraded",
        "UNAVAILABLE": "unavailable",
    },
}

# enum -> the table.column whose CHECK constraint pins the same set (§4.2-4.6)
ENUM_SQL_COLUMNS: dict[type, str] = {
    EventImpact: "news_events.impact",
    EventStatus: "news_events.status",
    EventSource: "news_events.source",
    NewsItemKind: "news_items.kind",
    NewsItemSource: "news_items.source",
    ImpactHint: "news_items.impact_hint",
    RateSource: "interest_rates.source",
    VerdictScopeType: "ai_trend_verdicts.scope_type",
    VerdictHorizon: "ai_trend_verdicts.horizon",
    VerdictDirection: "ai_trend_verdicts.direction",
    VerdictConfidence: "ai_trend_verdicts.confidence",
    IngestProducer: "ingest_runs.producer",
    IngestRunStatus: "ingest_runs.status",
}


# ---- table-mapped models ------------------------------------------------


TABLE_MODELS: dict[str, type] = {
    "news_events": CalendarEvent,
    "news_items": NewsItem,
    "interest_rates": RateObservation,
    "ai_trend_verdicts": TrendVerdict,
    "ingest_runs": IngestRun,
}

# The only (model, field) -> storage column renames. JSON encoding/decoding
# belongs to the repository (L2.1); the model carries the typed domain value
# under its domain name (C2/C3, contract §5).
DOMAIN_RENAMES: dict[tuple[str, str], str] = {
    ("NewsItem", "currencies"): "currencies_json",
    ("TrendVerdict", "evidence_item_ids"): "evidence_item_ids_json",
    ("TrendVerdict", "input_snapshot"): "input_snapshot_json",
}

# Fields whose model annotation is Optional (accepts/keeps None) exactly where
# the L1.2 column is nullable (PRAGMA notnull=0) — plus ``id``, the
# AUTOINCREMENT primary key that is absent at insert time / present on read.
OPTIONAL_FIELDS: dict[type, set[str]] = {
    CalendarEvent: {
        "id",
        "forecast",
        "previous",
        "actual",
        "actual_updated_at",
        "raw_json",
    },
    NewsItem: {"id", "content", "url", "impact_hint", "speaker_role"},
    RateObservation: {"id"},
    TrendVerdict: {"id"},
    IngestRun: {"id", "error_type", "error_detail"},
    StoreState: {
        "events_last_success_at",
        "items_last_success_at",
        "rates_last_success_at",
    },
}


# ---- valid pure-domain fixture per model (no mock, no IO — L2) -----------


MODEL_KWARGS: dict[type, dict[str, object]] = {
    CalendarEvent: {
        "day_key": "2026-09-21",
        "event_time_utc": "2026-09-21T08:00:00Z",
        "currency": "USD",
        "title": "CPI press conference",
        "impact": EventImpact.HIGH,
        "status": EventStatus.SCHEDULED,
        "source": EventSource.FF_JSON,
        "dedupe_key": "evt-1",
        "fetched_at": "2026-09-21T01:00:00Z",
        "raw_json": None,
    },
    NewsItem: {
        "kind": NewsItemKind.HEADLINE,
        "source": NewsItemSource.GOOGLE_NEWS_RSS,
        "title": "Fed holds rates steady",
        "published_utc": "2026-09-21T07:00:00Z",
        "currencies": ["USD"],
        "dedupe_key": "item-1",
        "fetched_at": "2026-09-21T01:00:00Z",
        "url": "https://example.com/x",
    },
    RateObservation: {
        "currency": "USD",
        "rate": 5.5,
        "observed_at": "2026-09-20",
        "source": RateSource.FRED,
        "fetched_at": "2026-09-21T01:00:00Z",
    },
    TrendVerdict: {
        "created_at": "2026-09-21T09:00:00Z",
        "scope_type": VerdictScopeType.PAIR,
        "scope_value": "EUR/USD",
        "horizon": VerdictHorizon.SHORT,
        "direction": VerdictDirection.BULLISH,
        "confidence": VerdictConfidence.HIGH,
        "rationale": "Momentum follows the rate path.",
        "evidence_item_ids": [10, 12],
        "input_snapshot": {"window_days": 7, "events": 4, "items": 6},
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "prompt_hash": "abcdef123456",
    },
    IngestRun: {
        "producer": IngestProducer.FF_CRAWLER,
        "started_at": "2026-09-21T01:00:00Z",
        "finished_at": "2026-09-21T01:00:30Z",
        "status": IngestRunStatus.OK,
        "items_written": 12,
    },
    StoreState: {
        "events_state": StoreStatus.FRESH,
        "items_state": StoreStatus.DEGRADED,
        "rates_state": StoreStatus.UNAVAILABLE,
        "events_last_success_at": "2026-09-21T00:50:00Z",
        "items_last_success_at": "2026-09-20T12:00:00Z",
        "rates_last_success_at": None,
    },
}

MODEL_CLASSES: list[type] = [
    CalendarEvent,
    NewsItem,
    RateObservation,
    TrendVerdict,
    IngestRun,
    StoreState,
]


# ---- helpers -------------------------------------------------------------


def _fresh_conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "news_models_test.db")
    conn.row_factory = sqlite3.Row
    return conn


def _apply_migration(conn: sqlite3.Connection) -> None:
    conn.executescript(MIGRATION_SQL.read_text(encoding="utf-8"))


def _sql_enum_sets(sql: str) -> dict[str, set[str]]:
    """``table.column`` -> the string set pinned by its CHECK constraint.

    Parses the L1.2 migration text — the machine source of the schema.  The
    integer CHECK ``excluded IN (0, 1)`` is intentionally absent (a bool flag,
    not an enum).
    """
    sets: dict[str, set[str]] = {}
    for table_match in re.finditer(
        r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(\w+)\s*\((.*?)\)\s*;",
        sql,
        re.DOTALL,
    ):
        table, body = table_match.group(1), table_match.group(2)
        for check in re.finditer(
            r"CHECK\s*\(\s*(\w+)\s+IN\s*\((.*?)\)\s*\)", body, re.DOTALL
        ):
            column = check.group(1)
            values = set(re.findall(r"'([^']*)'", check.group(2)))
            if values:
                sets[f"{table}.{column}"] = values
    return sets


def _temp_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _insert_probe_row(
    conn: sqlite3.Connection, table: str, column: str, value: str
) -> None:
    """Insert a minimal valid row of ``table`` with ``column`` set to ``value``."""
    base_rows: dict[str, dict[str, object]] = {
        "news_events": {
            "day_key": "2026-09-21",
            "event_time_utc": "2026-09-21T08:00:00Z",
            "currency": "USD",
            "title": "CPI press conference",
            "impact": "high",
            "status": "scheduled",
            "source": "ff_json",
            "dedupe_key": f"probe-{value}",
            "fetched_at": "2026-09-21T01:00:00Z",
        },
        "news_items": {
            "kind": "headline",
            "source": "google_news_rss",
            "title": "Fed holds rates steady",
            "published_utc": "2026-09-21T07:00:00Z",
            "currencies_json": '["USD"]',
            "excluded": 0,
            "dedupe_key": f"probe-{value}",
            "fetched_at": "2026-09-21T01:00:00Z",
        },
        "interest_rates": {
            "currency": "USD",
            "rate": 5.5,
            "observed_at": "2026-09-20",
            "source": "fred",
            "fetched_at": "2026-09-21T01:00:00Z",
        },
        "ai_trend_verdicts": {
            "created_at": "2026-09-21T09:00:00Z",
            "scope_type": "pair",
            "scope_value": "EUR/USD",
            "horizon": "short",
            "direction": "bullish",
            "confidence": "high",
            "rationale": "momentum",
            "evidence_item_ids_json": "[]",
            "input_snapshot_json": "{}",
            "provider": "anthropic",
            "model": "claude-sonnet-5",
            "prompt_hash": "abcdef123456",
        },
        "ingest_runs": {
            "producer": "rss",
            "started_at": "2026-09-21T01:00:00Z",
            "finished_at": "2026-09-21T01:00:30Z",
            "status": "ok",
            "items_written": 1,
        },
    }
    row = dict(base_rows[table])
    row[column] = value
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        list(row.values()),
    )


class TestEnumPinning:
    """Every closed value set pins the exact §4 string (V3(a) — V3(a))."""

    @pytest.mark.parametrize(
        "enum_cls",
        list(ENUM_EXPECTED_VALUES),
        ids=lambda enum_cls: enum_cls.__name__,
    )
    def test_all_members_pin_the_exact_contract_string(self, enum_cls):
        expected = ENUM_EXPECTED_VALUES[enum_cls]
        members = {
            name: member.value for name, member in enum_cls.__members__.items()
        }
        assert members == expected

    @pytest.mark.parametrize(
        "enum_cls",
        list(ENUM_EXPECTED_VALUES),
        ids=lambda enum_cls: enum_cls.__name__,
    )
    def test_enums_are_string_enums(self, enum_cls):
        assert issubclass(enum_cls, str)


class TestEnumVsSqlCheckConstraint:
    """Two-way cross-check with the L1.2 CHECK constraints (§4, V3(a))."""

    SQL_SETS = _sql_enum_sets(MIGRATION_SQL.read_text(encoding="utf-8"))

    @pytest.mark.parametrize(
        "enum_cls",
        list(ENUM_SQL_COLUMNS),
        ids=lambda enum_cls: enum_cls.__name__,
    )
    def test_enum_value_set_matches_the_sql_check_set(self, enum_cls):
        # == is both directions at once: every model value must be accepted by
        # SQL and no SQL-allowed value may be missing from the model — either
        # drift makes this red.
        sql_values = self.SQL_SETS[ENUM_SQL_COLUMNS[enum_cls]]
        model_values = {member.value for member in enum_cls}
        assert model_values == sql_values

    @pytest.mark.parametrize(
        "enum_cls",
        list(ENUM_SQL_COLUMNS),
        ids=lambda enum_cls: enum_cls.__name__,
    )
    def test_every_model_value_is_accepted_by_the_applied_schema(
        self, tmp_path, enum_cls
    ):
        table, column = ENUM_SQL_COLUMNS[enum_cls].split(".")
        conn = _fresh_conn(tmp_path)
        _apply_migration(conn)
        for member in enum_cls:
            _insert_probe_row(conn, table, column, member.value)
        conn.close()

    def test_excluded_flag_column_is_a_bool_not_an_enum(self):
        # ``excluded INTEGER NOT NULL DEFAULT 0 CHECK (excluded IN (0, 1))`` —
        # an integer flag (SQL column -> model ``bool``), so it must NOT be
        # counted among the string enums nor appear in the enum sets.
        assert "news_items.excluded" not in self.SQL_SETS

    def test_every_text_enum_column_is_cross_checked(self):
        # Pin that the cross-check table covers exactly the 13 string sets the
        # migration declares — adding a new enum column without registering it
        # (or dropping one) is red.
        assert set(self.SQL_SETS) == set(ENUM_SQL_COLUMNS.values())


class TestFieldColumnMapping:
    """Dataclass fields <-> L1.2 columns, one-to-one except the JSON renames."""

    def test_field_sets_match_column_sets_one_to_one(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_migration(conn)
        for table, model_cls in TABLE_MODELS.items():
            columns = _temp_columns(conn, table)
            fields = {field.name for field in dataclasses.fields(model_cls)}
            prefix = model_cls.__name__
            storage_names = {DOMAIN_RENAMES[key] for key in DOMAIN_RENAMES if key[0] == prefix}
            domain_names = {key[1] for key in DOMAIN_RENAMES if key[0] == prefix}
            mapped = (fields - domain_names) | storage_names
            assert mapped == columns, f"{table}: field/column set drift"
            assert len(fields) == len(columns), f"{table}: cardinality drift"
        conn.close()

    def test_only_the_three_json_columns_are_renamed(self, tmp_path):
        # The deliberate domain renames are exactly the three multi-valued JSON
        # columns; every other column shares its model field name 1:1.
        conn = _fresh_conn(tmp_path)
        _apply_migration(conn)
        assert len(DOMAIN_RENAMES) == 3
        assert {value for value in DOMAIN_RENAMES.values()} == {
            "currencies_json",
            "evidence_item_ids_json",
            "input_snapshot_json",
        }
        renamed_fields = {value for key, value in DOMAIN_RENAMES.items()}
        for table, model_cls in TABLE_MODELS.items():
            columns = _temp_columns(conn, table)
            fields = {field.name for field in dataclasses.fields(model_cls)}
            prefix = model_cls.__name__
            local_renames = {key[1] for key in DOMAIN_RENAMES if key[0] == prefix}
            for field_name in fields:
                if field_name in local_renames:
                    continue
                assert field_name in columns  # 1:1 name sharing
        conn.close()

    def test_optional_fields_match_sql_nullable_columns(self, tmp_path):
        # ``Optional``/``None`` fields (minus ``id``, the AUTOINCREMENT PK that
        # PRAGMA reports notnull=0) are exactly the columns the schema leaves
        # nullable — nothing more, nothing less.
        conn = _fresh_conn(tmp_path)
        _apply_migration(conn)
        for table, model_cls in TABLE_MODELS.items():
            nullable = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})")
                if not row["notnull"] and row["name"] != "id"
            }
            optional = OPTIONAL_FIELDS[model_cls] - {"id"}
            assert optional == nullable, f"{table}: optional/Nullable drift"
        conn.close()


class TestConstruction:
    """Every model builds from pure domain values; frozen; nullability real."""

    @pytest.mark.parametrize(
        "model_cls", MODEL_CLASSES, ids=lambda cls: cls.__name__
    )
    def test_constructs_from_domain_values_without_mock(self, model_cls):
        instance = model_cls(**MODEL_KWARGS[model_cls])
        assert dataclasses.replace(instance) == instance

    @pytest.mark.parametrize(
        "model_cls", MODEL_CLASSES, ids=lambda cls: cls.__name__
    )
    def test_models_are_frozen(self, model_cls):
        kwargs = MODEL_KWARGS[model_cls]
        instance = model_cls(**kwargs)
        first_field = next(
            field for field in dataclasses.fields(model_cls)
            if field.name in kwargs
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, first_field.name, object())

    @pytest.mark.parametrize(
        ("model_cls", "field"),
        [
            (model_cls, field_name)
            for model_cls, fields in OPTIONAL_FIELDS.items()
            for field_name in sorted(fields)
        ],
        ids=lambda value: value if isinstance(value, str) else value.__name__,
    )
    def test_optional_fields_accept_none(self, model_cls, field):
        kwargs = {
            key: value
            for key, value in MODEL_KWARGS[model_cls].items()
            if key != field
        }
        instance = model_cls(**kwargs, **{field: None})
        assert getattr(instance, field) is None

    @pytest.mark.parametrize(
        ("model_cls", "required_field"),
        [
            (
                model_cls,
                field.name,
            )
            for model_cls, fields in MODEL_KWARGS.items()
            for field in dataclasses.fields(model_cls)
            if field.name != "id"
            and field.default is dataclasses.MISSING
            and field.default_factory is dataclasses.MISSING
        ],
        ids=lambda value: value if isinstance(value, str) else value.__name__,
    )
    def test_not_null_fields_are_required(self, model_cls, required_field):
        kwargs = dict(MODEL_KWARGS[model_cls])
        del kwargs[required_field]
        with pytest.raises(TypeError):
            model_cls(**kwargs)

    def test_news_item_excluded_mirrors_the_sql_default(self):
        # column ``excluded INTEGER NOT NULL DEFAULT 0`` -> a fresh item is not
        # flagged unless explicitly built so (structural default, not a policy
        # default — B4 does not apply to model fields).
        item = NewsItem(**MODEL_KWARGS[NewsItem])
        assert item.excluded is False
        assert NewsItem(**MODEL_KWARGS[NewsItem], excluded=True).excluded is True


class TestStoreState:
    """StoreState: typed per-signal freshness — no bare dict (C3, §8)."""

    def test_constructs_with_all_three_signals_and_last_ingest_times(self):
        state = StoreState(**MODEL_KWARGS[StoreState])
        assert state.events_state is StoreStatus.FRESH
        assert state.items_state is StoreStatus.DEGRADED
        assert state.rates_state is StoreStatus.UNAVAILABLE
        assert state.events_last_success_at == "2026-09-21T00:50:00Z"
        assert state.items_last_success_at == "2026-09-20T12:00:00Z"
        assert state.rates_last_success_at is None

    def test_never_ingested_signal_has_none_last_success(self):
        state = StoreState(
            events_state=StoreStatus.UNAVAILABLE,
            items_state=StoreStatus.UNAVAILABLE,
            rates_state=StoreStatus.UNAVAILABLE,
        )
        assert state.events_last_success_at is None
        assert state.items_last_success_at is None
        assert state.rates_last_success_at is None

    def test_components_are_explicit_typed_fields_not_dicts(self):
        # Contract §8: store_state() returns a typed model, never a bare dict
        # across the boundary — pinned at the type-annotation level, too.
        hints = typing.get_type_hints(StoreState)
        assert set(hints) == {
            "events_state",
            "items_state",
            "rates_state",
            "events_last_success_at",
            "items_last_success_at",
            "rates_last_success_at",
        }
        for signal in ("events", "items", "rates"):
            assert hints[f"{signal}_state"] is StoreStatus
            assert hints[f"{signal}_last_success_at"] == typing.Optional[str]
        assert all("dict" not in str(hint) for hint in hints.values())


class TestCoreLayerBoundary:
    """core/news_models.py: no upstream imports, no display strings (L2/L3)."""

    @classmethod
    def _source(cls) -> str:
        return NEWS_MODELS_PY.read_text(encoding="utf-8")

    def test_module_imports_nothing_from_services_ui_controllers_or_qt(self):
        source = self._source()
        for forbidden in (
            "import services",
            "from services",
            "import ui",
            "from ui",
            "import controllers",
            "from controllers",
            "PyQt6",
            "tkinter",
        ):
            assert forbidden not in source, f"{forbidden!r} must not appear"

    def test_module_source_is_ascii_no_vietnamese_display_strings(self):
        # A core module carries no display strings (L2/L3): the whole source
        # stays ASCII, so a Vietnamese label or any non-ASCII glyph cannot hide.
        source = self._source()
        assert source.isascii(), (
            "core/news_models.py must stay pure ASCII - display strings "
            "(Vietnamese labels) belong to the presentation tier"
        )