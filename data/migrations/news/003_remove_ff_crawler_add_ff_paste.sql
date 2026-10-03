-- 003_remove_ff_crawler_add_ff_paste.sql — bỏ di sản `ff_crawler`, công nhận
-- kênh dán lịch `ff_paste` (§4.6, fix 03/10/2026).
--
-- Gốc rễ: `ff_crawler` là kênh tải lịch qua mạng, đã bị gỡ đợt 3 (24/09/2026)
-- và CHƯA TỪNG chạy lượt nào → mọi run thật của kênh dán ghi dưới `user`
-- (nhập tay) nên registry không thấy `events` → `events_state` vĩnh viễn
-- `unavailable` dù DB có dữ liệu. Kênh dán nay ghi `ff_paste`; `user` chỉ còn
-- là nhập tay tin (add_user_note) và KHÔNG nuôi tín hiệu registry nào.
--
-- An toàn: giá trị 'ff_crawler' chưa từng persist (§4 + các vòng nghiệm thu
-- build `.exe` ghi 0 lượt ff_crawler), nên không có dòng nào cần di trú; các
-- lượt `user` cũ (76+) được giữ NGUYÊN qua rebuild.
--
-- ingest_runs: SQLite không ALTER được CHECK constraint → rebuild bảng (khuôn y
-- migration 002; runner news_repository.migrate tách statement theo ';' nên
-- chuỗi 4 lệnh dưới chạy tuần tự an toàn trong 1 migration).
CREATE TABLE IF NOT EXISTS ingest_runs_v3 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  producer TEXT NOT NULL CHECK (producer IN (
    'ff_paste', 'rss', 'fred', 'user', 'on_demand_lookup', 'bond_yield'
  )),
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok', 'partial', 'failed')),
  items_written INTEGER NOT NULL,
  error_type TEXT,
  error_detail TEXT
);
INSERT INTO ingest_runs_v3 SELECT * FROM ingest_runs;
DROP TABLE ingest_runs;
ALTER TABLE ingest_runs_v3 RENAME TO ingest_runs;
