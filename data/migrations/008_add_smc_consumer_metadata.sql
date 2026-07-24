ALTER TABLE journal_entries ADD COLUMN selected_zone_id TEXT;
ALTER TABLE journal_entries ADD COLUMN entry_zone_quality_score INTEGER;
ALTER TABLE journal_entries ADD COLUMN entry_zone_relevance_score INTEGER;
ALTER TABLE journal_entries ADD COLUMN entry_zone_setup_score INTEGER;
ALTER TABLE journal_entries ADD COLUMN entry_zone_scoring_version TEXT;
ALTER TABLE journal_entries ADD COLUMN smc_score_breakdown_json TEXT;
