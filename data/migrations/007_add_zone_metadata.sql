-- Zone quality metadata, wired from build_trade_plan() output.
ALTER TABLE journal_entries ADD COLUMN entry_zone_score INTEGER;
ALTER TABLE journal_entries ADD COLUMN entry_zone_source TEXT;
ALTER TABLE journal_entries ADD COLUMN sub_zone TEXT;
