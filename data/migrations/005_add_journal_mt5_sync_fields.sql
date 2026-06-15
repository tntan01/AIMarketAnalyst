-- MT5 history sync identity fields.
ALTER TABLE journal_entries ADD COLUMN mt5_deal_id INTEGER;
ALTER TABLE journal_entries ADD COLUMN mt5_order_id INTEGER;
ALTER TABLE journal_entries ADD COLUMN mt5_position_id INTEGER;
ALTER TABLE journal_entries ADD COLUMN synced_from TEXT;
ALTER TABLE journal_entries ADD COLUMN synced_at_utc TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_mt5_deal_id
ON journal_entries(mt5_deal_id)
WHERE mt5_deal_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_journal_mt5_position_id
ON journal_entries(mt5_position_id);
