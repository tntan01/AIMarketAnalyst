CREATE TABLE IF NOT EXISTS journal_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp_utc TEXT NOT NULL,
  saved_at_utc TEXT NOT NULL,
  symbol TEXT NOT NULL,
  broker_symbol TEXT,
  mode TEXT NOT NULL,
  data_source TEXT NOT NULL DEFAULT 'MT5',
  market_regime TEXT,
  decision TEXT,
  direction_bias TEXT,
  trade_permission TEXT,
  buy_score INTEGER DEFAULT 0,
  sell_score INTEGER DEFAULT 0,
  selected_scenario TEXT,
  entry_zone TEXT,
  stop_loss TEXT,
  take_profit TEXT,
  risk_reward TEXT,
  suggested_lot REAL,
  ai_commentary TEXT,
  analysis_json TEXT NOT NULL,
  user_action TEXT DEFAULT '',
  result TEXT DEFAULT '',
  note TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON journal_entries(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_journal_symbol ON journal_entries(symbol);
CREATE INDEX IF NOT EXISTS idx_journal_decision ON journal_entries(decision);
CREATE INDEX IF NOT EXISTS idx_journal_permission ON journal_entries(trade_permission);
