-- 002_add_bond_yields.sql — tín hiệu lợi suất trái phiếu (§4.7) + giá trị
-- producer bond_yield của ingest_runs (§4.6) — đợt 5, Owner duyệt 28/09/2026.
CREATE TABLE IF NOT EXISTS bond_yields (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  currency TEXT NOT NULL,
  maturity TEXT NOT NULL CHECK (maturity IN ('2y', '10y', 'be10y')),
  value REAL NOT NULL,
  observed_at TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('fred', 'yahoo')),
  fetched_at TEXT NOT NULL,
  UNIQUE (currency, maturity, observed_at, source)
);
CREATE INDEX IF NOT EXISTS idx_bond_yields_currency_maturity_observed_at
  ON bond_yields(currency, maturity, observed_at);

-- ingest_runs: SQLite không ALTER được CHECK constraint → rebuild bảng
-- (runner news_repository.migrate tách statement theo ';' nên chuỗi 4 lệnh
-- dưới chạy tuần tự an toàn trong 1 migration).
CREATE TABLE IF NOT EXISTS ingest_runs_v2 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  producer TEXT NOT NULL CHECK (producer IN (
    'ff_crawler', 'rss', 'fred', 'user', 'on_demand_lookup', 'bond_yield'
  )),
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok', 'partial', 'failed')),
  items_written INTEGER NOT NULL,
  error_type TEXT,
  error_detail TEXT
);
INSERT INTO ingest_runs_v2 SELECT * FROM ingest_runs;
DROP TABLE ingest_runs;
ALTER TABLE ingest_runs_v2 RENAME TO ingest_runs;
