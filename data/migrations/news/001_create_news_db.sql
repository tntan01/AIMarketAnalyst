-- 001_create_news_db.sql — schema miền Tin tức (news.db)
-- Đặc tả thẩm quyền: docs/news/news-architecture.md §4.1-§4.6 (BAN HÀNH 20/09/2026).
-- Schema chỉ thay đổi bằng migration versioned trong data/migrations/ (§4.1);
-- file này đặt trong thư mục con news/ vì runner journal glob *.sql không đệ
-- quy (QĐ-2 — plan news-data-layer-plan §5): đặt chung thư mục gốc sẽ bị áp
-- nhầm vào journal.db.
-- Giá trị enum là chuỗi persist đóng băng (V3(a)) — CHECK constraint ghim
-- đúng tập giá trị của đặc tả, không hơn không kém.

-- news_events (§4.2) — sự kiện lịch kinh tế
CREATE TABLE IF NOT EXISTS news_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day_key TEXT NOT NULL,
  event_time_utc TEXT NOT NULL,
  currency TEXT NOT NULL,
  title TEXT NOT NULL,
  impact TEXT NOT NULL CHECK (impact IN ('high', 'medium', 'low', 'non')),
  forecast TEXT,
  previous TEXT,
  actual TEXT,
  actual_updated_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('scheduled', 'released', 'stale')),
  source TEXT NOT NULL CHECK (source IN ('ff_json', 'ff_html', 'user', 'import')),
  dedupe_key TEXT NOT NULL UNIQUE,
  raw_json TEXT,
  fetched_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_events_day_key ON news_events(day_key);
CREATE INDEX IF NOT EXISTS idx_news_events_event_time_utc ON news_events(event_time_utc);
CREATE INDEX IF NOT EXISTS idx_news_events_currency_event_time_utc
  ON news_events(currency, event_time_utc);
CREATE INDEX IF NOT EXISTS idx_news_events_status_stale
  ON news_events(status) WHERE status = 'stale';

-- news_items (§4.3) — tin văn bản
CREATE TABLE IF NOT EXISTS news_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK (kind IN ('headline', 'statement', 'user_note')),
  source TEXT NOT NULL CHECK (source IN (
    'google_news_rss', 'fxstreet_rss', 'investing_rss', 'user', 'import'
  )),
  title TEXT NOT NULL,
  content TEXT,
  url TEXT,
  published_utc TEXT NOT NULL,
  currencies_json TEXT NOT NULL,
  impact_hint TEXT CHECK (impact_hint IN ('high', 'medium', 'low')),
  speaker_role TEXT,
  excluded INTEGER NOT NULL DEFAULT 0 CHECK (excluded IN (0, 1)),
  dedupe_key TEXT NOT NULL UNIQUE,
  fetched_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_items_kind_published_utc
  ON news_items(kind, published_utc);
CREATE INDEX IF NOT EXISTS idx_news_items_published_utc
  ON news_items(published_utc);

-- interest_rates (§4.4) — quan sát lãi suất
CREATE TABLE IF NOT EXISTS interest_rates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  currency TEXT NOT NULL,
  rate REAL NOT NULL,
  observed_at TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('fred', 'ff_html', 'config_fallback')),
  fetched_at TEXT NOT NULL,
  UNIQUE (currency, observed_at, source)
);

-- ai_trend_verdicts (§4.5) — nhận định xu hướng của AI
CREATE TABLE IF NOT EXISTS ai_trend_verdicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  scope_type TEXT NOT NULL CHECK (scope_type IN ('pair', 'currency')),
  scope_value TEXT NOT NULL,
  horizon TEXT NOT NULL CHECK (horizon IN ('short', 'mid', 'long')),
  direction TEXT NOT NULL CHECK (direction IN (
    'bullish', 'bearish', 'neutral', 'insufficient_data'
  )),
  confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low', 'none')),
  rationale TEXT NOT NULL,
  evidence_item_ids_json TEXT NOT NULL,
  input_snapshot_json TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_hash TEXT NOT NULL
);

-- ingest_runs (§4.6) — log vận hành bộ sản xuất
CREATE TABLE IF NOT EXISTS ingest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  producer TEXT NOT NULL CHECK (producer IN (
    'ff_crawler', 'rss', 'fred', 'user', 'on_demand_lookup'
  )),
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok', 'partial', 'failed')),
  items_written INTEGER NOT NULL,
  error_type TEXT,
  error_detail TEXT
);