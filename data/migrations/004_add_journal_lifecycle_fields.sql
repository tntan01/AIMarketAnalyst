-- Journal lifecycle fields for planned/opened/closed trade review.
ALTER TABLE journal_entries ADD COLUMN trade_status TEXT DEFAULT 'planned';
ALTER TABLE journal_entries ADD COLUMN opened_at TEXT;
ALTER TABLE journal_entries ADD COLUMN result_amount REAL;
