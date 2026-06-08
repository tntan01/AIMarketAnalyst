-- Phase 17 Đợt 2: journal fields nâng cao phục vụ execution quality,
-- mistake detector, statistical edge và phân tích journal.
--
-- Tất cả cột mới đều nullable để không phá dữ liệu journal cũ.
ALTER TABLE journal_entries ADD COLUMN planned_entry REAL;
ALTER TABLE journal_entries ADD COLUMN actual_entry REAL;
ALTER TABLE journal_entries ADD COLUMN planned_sl REAL;
ALTER TABLE journal_entries ADD COLUMN actual_sl REAL;
ALTER TABLE journal_entries ADD COLUMN planned_tp REAL;
ALTER TABLE journal_entries ADD COLUMN actual_tp REAL;
ALTER TABLE journal_entries ADD COLUMN actual_exit REAL;
ALTER TABLE journal_entries ADD COLUMN setup_type TEXT;
ALTER TABLE journal_entries ADD COLUMN regime TEXT;
ALTER TABLE journal_entries ADD COLUMN session TEXT;
ALTER TABLE journal_entries ADD COLUMN m15_quality TEXT;
ALTER TABLE journal_entries ADD COLUMN spread_at_entry REAL;
ALTER TABLE journal_entries ADD COLUMN expected_effective_rr REAL;
ALTER TABLE journal_entries ADD COLUMN realized_effective_rr REAL;
ALTER TABLE journal_entries ADD COLUMN manual_mistake_tags TEXT;
ALTER TABLE journal_entries ADD COLUMN auto_mistake_tags TEXT;
ALTER TABLE journal_entries ADD COLUMN execution_quality_score INTEGER;
