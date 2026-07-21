-- Rename Phase 17 regime field to execution_regime to avoid confusion
-- with market_regime (AI analysis field from migration 001).
ALTER TABLE journal_entries RENAME COLUMN regime TO execution_regime;
