ALTER TABLE journal_entries ADD COLUMN result_r REAL;
ALTER TABLE journal_entries ADD COLUMN result_pct REAL;
ALTER TABLE journal_entries ADD COLUMN closed_at TEXT;
ALTER TABLE journal_entries ADD COLUMN exit_reason TEXT;
ALTER TABLE journal_entries ADD COLUMN actual_lot REAL;
ALTER TABLE journal_entries ADD COLUMN planned_lot REAL;
