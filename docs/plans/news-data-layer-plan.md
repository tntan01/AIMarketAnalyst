# Plan triển khai — Tầng dữ liệu Tin tức

> **Trạng thái: DRAFT rev 2 — chờ Owner duyệt** (lập 21/09/2026, vai trò Product Owner;
> rev 2: phân lô chi tiết trên căn cứ khảo sát code thật).
> Vòng đời theo D3 (`docs/README.md`): hoàn tất ca → **xóa file này** (lịch sử trong Git);
> điều khoản còn hiệu lực đã nằm trong tài liệu chính đích danh.
> Nguồn thẩm quyền: [`../news/news-architecture.md`](../news/news-architecture.md)
> (contract BAN HÀNH 20/09/2026) + [`../architecture/architecture-rules.md`](../architecture/architecture-rules.md).
> Plan này **không lặp lại đặc tả** — chỉ xếp thứ tự, tiêu chí hoàn thành và
> quyết định triển khai (D5: trỏ về nguồn, không chép).
>
> **Cách dùng cho Tech Lead:** mỗi lô (L*) = một đơn vị giao cho coder =
> **một commit D2** (code + test + tài liệu cùng commit). Chỉ tăng lô kế tiếp
> khi lô trước đạt Trạng thái IMPLEMENTED + DoD (kỷ luật relay A3). Cột
> "Điểm review" là trọng tâm khi chấm commit của coder.

---

## 1. Mục tiêu và giá trị người dùng

Thay thế lớp tin tức cũ (`news_service.py` — sổ nợ kiến trúc #1, 4 lý do thay
đổi) bằng miền Tin tức sạch: `news.db` là nguồn chân lý duy nhất, producer
chỉ ghi, consumer chỉ đọc qua `NewsRepository`. Giá trị người dùng trực tiếp
của ca này (trước đấu nối):

1. **Màn Quản lý tin:** toàn bộ tin/sự kiện một chỗ — xem, lọc, nhập tay tin
   nguồn tự động bỏ sót, loại trừ tin rác, xuất/nhập file bù ngày app không chạy.
2. **AI nhận định xu hướng** 3 chân trời cho một cặp tiền/đồng tiền — **chỉ
   tham khảo** (ranh giới cứng contract §9.2).
3. Nền dữ liệu sẵn sàng cho Dashboard và chấm điểm vĩ mô đọc từ một nguồn
   duy nhất (hai ca đấu nối, lập plan riêng — ngoài phạm vi plan này).

## 2. Phạm vi

**Trong phạm vi:** 20 lô trong 4 bước ở mục 4 — chính sách, schema, mô hình
miền, hàm thuần `core/`, repository, 3 bộ sản xuất + nhập tay,
controller/worker, màn Quản lý tin + dialog AI, cổng cưỡng chế E2, nghiệm thu
tổng.

**Ngoài phạm vi (cấm mở rộng trong ca này):**
- Đấu nối (a) Dashboard và (b) vĩ mô/MacroGate — đặc tả + plan riêng, chỉ bắt
  đầu sau khi Bước 4 đạt (contract §3.1 khoản 3).
- Mọi sửa đổi vào `news_service.py`, `forex_factory_client.py`,
  `interest_rate_service.py` (QĐ-1 phương án A đã chốt — cả ba untouched tới
  ca đấu nối), `dashboard_screen.py` (NewsWorker/mục tin cũ), mục tin
  Dashboard, chấm điểm vĩ mô, guard thực thi, Telegram alert.
- Xóa code cũ — chỉ xảy ra ở các ca đấu nối, cùng commit (D2).

## 3. Ràng buộc nền (mọi lô phải tuân thủ)

| # | Ràng buộc | Nguồn |
|---|---|---|
| R1 | Chỉ tạo file mới; code cũ giữ nguyên hành vi runtime 100%; hai hệ không đọc/ghi đường dữ liệu của nhau. Ngoại lệ duy nhất: **sổ điểm chạm additive** bên dưới | B7, contract §3.1 |
| R2 | Mỗi lô hoàn thành = code + kiểm thử + tài liệu trong **cùng một commit**; thông điệp commit nêu tên mục tài liệu đã sửa | D2 |
| R3 | Trước khi code mỗi lô: điều khoản tài liệu tương ứng phải tồn tại (contract/screen_design/plan này); lô nào phát hiện thiếu điều khoản → **dừng, báo Owner**, không tự bịa hành vi | D1, V2 |
| R4 | Mọi con số vận hành đọc từ `config/news_policy.json` qua loader; cấm hard-code trong logic; giá trị kế thừa code cũ phải mang nhãn bằng chứng "kế thừa runtime hiện hành" | S4, D5, B5, contract §7 |
| R5 | Mỗi lô trả lời 4 câu hỏi E1 trong thông điệp commit; cập nhật bảng trạng thái mục 8 | E1 |
| R6 | Không tên phiên bản trong mọi định danh mới; enum/chuỗi persist đóng băng | V3 |
| R7 | Singleton mới chỉ đăng ký DI trong `AppController` theo khuôn property lazy hiện có | architecture.md "Ghi chú" |
| R8 | Dữ liệu thô (JSON feed/HTML/XML RSS) không tồn tại ngoài bộ chuyển đổi của producer — ra khỏi biên chỉ có dataclass `core/news_models.py` | C2, C3, contract §5 |

**Sổ điểm chạm additive (file cũ duy nhất được phép sửa, và chỉ theo cách nêu):**

| File cũ | Thay đổi cho phép | Lô |
|---|---|---|
| `config/paths.py` | **append-only**: thêm `news_db_path()` theo khuôn `journal_db_path()` (d.29) | L1.2 |
| `packaging/pyinstaller.spec` | thêm dòng `datas` cho `data/migrations/news/*.sql` (glob `config/*.json` d.9 **đã tự phủ** `news_policy.json` — không cần sửa) | L1.2 |
| `controllers/app_controller.py` | thêm `self._news_controller` + property lazy theo khuôn `journal_controller` (d.141-148); không đụng property `news_service` cũ (d.71-75) | L2.7 |
| `ui/navigation.py` | thêm `("news", "Tin tức")` vào `NAV_ITEMS` + glyph vào `NAV_ICONS` | L3.2 |
| `ui/main_window.py` | import `NewsScreen` + thêm `"news"` vào `screen_factories` (d.229-247) + ánh xạ `nav_route` (d.324-331) | L3.2 |
| `tests/test_backtest_removal_step3_ui.py`, `tests/test_main_window_startup_policy.py` | **chỉ cập nhật ghim inventory điều hướng 5→6** — hệ quả tất yếu của điểm chạm đã đăng ký (`ui/navigation.py` + mục `"news"`); Owner duyệt phương án A 22/09/2026, đúng 4 dòng | L3.2 |

Ngoài 5 file này: **mọi thay đổi là file mới**. `git diff` trên
`news_service.py` / `forex_factory_client.py` / `interest_rate_service.py` /
`dashboard_screen.py` phải rỗng ở mọi lô (bằng chứng máy đọc của R1).

## 4. Lộ trình 4 bước — phân lô chi tiết

Quy ước cỡ lô: **S** ≤ nửa phiên coder · **M** ≈ một phiên · **L** > một phiên
( Tech Lead được tách thêm nhưng không gộp qua bước). Test mới đặt trong
`tests/test_news_*.py`.

### Bước 1 — Nền tảng miền (không mạng, không UI, không Qt)

#### L1.1 — Chính sách miền + loader (S)
- **File mới:** `config/news_policy.json`, `core/news_policy.py`, `tests/test_news_policy.py`.
- **Neo đặc tả:** contract §7 (9 khóa + `policy_version`); án lệ loader
  `core/scanner_order_policy.py` `load_runtime_order_policy` (d.411-443):
  đọc `CONFIG_DIR`, fail-closed raise lỗi có kiểu khi thiếu file/sai JSON/sai
  version, dataclass validate `__post_init__`.
- **Nội dung:** dataclass `NewsPolicy` (9 trường đúng tên khóa §7) +
  `load_news_policy(path=None)`; không giá trị mặc định ngầm — thiếu khóa = lỗi (B4).
- **Test:** ghim đúng cặp khóa↔giá trị bảng §7; JSON hỏng/thiếu khóa → raise;
  không có hành vi lạc quan.
- **Tài liệu cùng commit (D2):** contract §3 (bảng lớp `core/`) + §11b thêm
  dòng chủ sở hữu "Nạp và validate chính sách miền Tin tức → `core/news_policy.py`"
  (hiện contract chưa đăng ký chủ sở hữu loader — xem QĐ-3).
- **Phụ thuộc:** — · **Điểm review:** không số ma thuật ngoài JSON; lỗi có kiểu; §11b đã thêm dòng.
- **Trạng thái:** IMPLEMENTED

#### L1.2 — Đường dẫn + migration schema `news.db` (S)
- **File mới:** `data/migrations/news/001_create_news_db.sql`, `tests/test_news_migration.py`.
- **Điểm chạm additive:** `config/paths.py` (+`news_db_path()`), `packaging/pyinstaller.spec` (+datas).
- **Neo đặc tả:** contract §4.1-§4.6 (5 bảng + cột + index, `dedupe_key` UNIQUE).
- **Nội dung:** SQL thuần tạo 5 bảng theo §4; **đặt trong thư mục con
  `data/migrations/news/`** vì runner journal `JournalService.migrate()` glob
  `*.sql` không đệ quy (d.44-59) — để chung thư mục gốc sẽ bị runner journal
  áp nhầm vào `journal.db` (QĐ-2). Runner của news viết ở L2.1, lô này chỉ
  test bằng `sqlite3` trực tiếp trên DB tạm.
- **Test:** áp SQL lên DB trống → đủ 5 bảng, đúng cột/kiểu, đủ index,
  `dedupe_key` UNIQUE có hiệu lực; chạy lại có bảng `schema_migrations` kiểm soát (test mô phỏng version).
- **Phụ thuộc:** — · **Điểm review:** đối chiếu từng cột với §4; spec bundle đủ; không đụng `journal.db`.
- **Trạng thái:** IMPLEMENTED

#### L1.3 — Mô hình miền `core/news_models.py` (S)
- **File mới:** `core/news_models.py`, `tests/test_news_models.py`.
- **Neo đặc tả:** contract §5 (6 dataclass: `CalendarEvent`, `NewsItem`, `RateObservation`, `TrendVerdict`, `IngestRun`, `StoreState`); enum chuỗi đóng băng (V3(a), §2).
- **Nội dung:** dataclass tường minh + hằng enum (giá trị chuỗi đúng §4);
  không logic nghiệp vụ, không I/O, không chuỗi hiển thị (L2/L3).
- **Test:** ghim giá trị enum (đổi chuỗi = đỏ); khởi tạo không cần mock (L2); ánh xạ trường ↔ cột.
- **Phụ thuộc:** L1.2 (thống nhất tên) · **Điểm review:** đúng đủ 6 mô hình; không dict trần.
- **Trạng thái:** IMPLEMENTED

#### L1.4 — Phân loại trạng thái `core/news_freshness.py` (M)
- **File mới:** `core/news_freshness.py`, `tests/test_news_freshness.py`.
- **Neo đặc tả:** contract §6.5 — `classify_event_status(event, now, grace)`
  và `classify_store_state(last_success_by_producer, now, max_age)`; án lệ
  `MacroMarketCache` (B4 — không im lặng lạc quan).
- **Nội dung:** hàm thuần, grace/max_age là **tham số** (caller đọc từ
  policy — giữ tính thuần L2); trả enum, không sinh chuỗi.
- **Test:** bảng biên thời gian (trước/sau `event_time_utc + grace`, actual
  NULL/có, `impact=non`); store_state đủ 3 trạng thái + chưa-từng-có → `unavailable`.
- **Phụ thuộc:** L1.3 · **Điểm review:** không import policy/Qt/services trong hàm thuần.
- **Trạng thái:** IMPLEMENTED

#### L1.5 — Dẫn xuất trend lãi suất `core/rate_trend.py` (S)
- **File mới:** `core/rate_trend.py`, `tests/test_rate_trend.py`.
- **Neo đặc tả:** contract §4.4 — `derive_rate_trend` từ hai quan sát gần nhất; danh tính M5 đã đăng ký.
- **Nội dung:** hấp thụ logic trend **inline hiện hành** của
  `interest_rate_service.py` (ngưỡng FRED `>0.1` d.182-187, ngưỡng FF `>0.01`
  d.123) thành hàm thuần tham số hóa theo nguồn; **giữ nguyên ngưỡng kế thừa,
  nhãn B5 "kế thừa runtime hiện hành (bằng chứng: đang chạy)" — không bịa
  ngưỡng mới, không hợp nhất hai ngưỡng khi chưa có bằng chứng**.
- **Test:** hike/cut/hold theo biên từng nguồn; <2 quan sát → `hold`/không xác định theo hành vi cũ (đặc trưng hóa B3 mức hàm).
- **Phụ thuộc:** L1.3 · **Điểm review:** so diff logic với `interest_rate_service` gốc — tương đương hành vi, không "cải tiến".
- **Trạng thái:** IMPLEMENTED

### Bước 2 — Tầng truy cập + bộ sản xuất (dữ liệu chảy vào DB, chưa UI)

#### L2.1 — `NewsRepository` phần GHI + runner migration (L)
- **File mới:** `services/news_repository.py`, `tests/test_news_repository_write.py`.
- **Neo đặc tả:** contract §8 (7 phương thức ghi), §6.1 (3 quy tắc merge), §4.1 (WAL, connection).
- **Nội dung:** khuôn connection theo `JournalService._connect()` (d.584-590:
  WAL, `busy_timeout=15s`, `row_factory=Row`, per-call context manager);
  runner migration riêng cho `data/migrations/news/` + bảng `schema_migrations`
  (copy khuôn `JournalService.migrate()` d.44-59, chạy trong `__init__`);
  7 method ghi: `upsert_events`, `upsert_items`, `add_rate_observations`,
  `add_verdicts`, `record_run`, `set_excluded`, `delete_user_note`,
  `purge_expired_runs` — trả số bản ghi/lỗi **có kiểu** (C3); 3 quy tắc merge
  nằm trong `upsert_events/upsert_items`: không NULL đè `actual`, không đè
  `source=user`, xung đột actual → ưu tiên user + trả thông tin xung đột để
  producer ghi `ingest_runs`; stamp `status` sự kiện qua `core/news_freshness`.
- **Cấm trong lô:** công thức chấm điểm, quyết định gate, chuỗi hiển thị (§8).
- **Test:** upsert/dedupe theo `dedupe_key`; từng quy tắc merge một test; user_note protect; purge theo retention (giá trị truyền vào, không hard-code).
- **Phụ thuộc:** L1.1, L1.2, L1.3, L1.4 · **Điểm review:** 3 quy tắc merge đủ 3 test riêng; không logic nghiệp vụ ngoài upsert.
- **Trạng thái:** IMPLEMENTED

#### L2.2 — `NewsRepository` phần ĐỌC + `store_state` + kiểm thử hợp đồng C4 (M)
- **File mới:** mở rộng `services/news_repository.py` (file mới của ca — được sửa trong ca), `tests/test_news_repository_contract.py`.
- **Neo đặc tả:** contract §8 bảng 7 phương thức đọc (`events_in_range`, `events_pending_actual`, `event_actual_or_lookup`, `items_in_range`, `latest_rates`, `store_state`, `verdicts_for`); §14 "kiểm thử hợp đồng ghim chữ ký + ngữ nghĩa".
- **Nội dung:** query có index + giới hạn dòng (§4.1); `latest_rates` gọi
  `core/rate_trend.derive_rate_trend` (không tự tính — §4.4);
  `store_state()` dựng `StoreState` qua `core/news_freshness.classify_store_state`
  từ `ingest_runs`; `event_actual_or_lookup` **chưa kích hoạt fetch** ở lô này
  (chỉ đánh dấu điểm nối on-demand — callback/dependency injection để L2.4/L2.7 cắm lookup, tránh repo tự gọi mạng: services không tự phong quyết định điều phối).
- **Test C4:** ghim chữ ký + ngữ nghĩa từng method (đây là test hai ca đấu nối sẽ dùng lại — xanh nguyên trạng khi nội bộ đổi).
- **Phụ thuộc:** L2.1, L1.4, L1.5 · **Điểm review:** test hợp đồng không ghim giá trị trung gian nội bộ (C4); repo không import network.
- **Trạng thái:** IMPLEMENTED

#### L2.3 — `ff_calendar_producer` kênh JSON (lịch) (M)
- **File mới:** `services/news_producers/__init__.py`, `services/news_producers/ff_calendar_producer.py`, `tests/test_news_ff_producer_json.py`.
- **Neo đặc tả:** contract §6.1 (phân công kênh: JSON = lịch; 4 lượt thu; không retry vòng lặp), §6 sổ đăng ký.
- **Nội dung:** hấp thụ từ `forex_factory_client.py` — `_fetch_json_events`
  (d.236) + `_fetch_json_events_nextweek` (d.282), retry 3 + backoff 429
  (d.251-253), URL hằng (d.55-58); **bộ chuyển đổi dict thô → `CalendarEvent`
  ngay tại biên** (R8 — dict keys `source/currency/event/impact/time_utc/...`
  không thoát khỏi producer); ghi qua `repo.upsert_events` + `record_run`
  (producer `ff_crawler`); **không port cache đĩa cũ** (`_store_calendar_cache`
  d.729 — DB thay thế, B7 khoản 2: không ghi đường cũ).
- **Test:** HTTP giả lập JSON ok / 429 / URLError; converter đủ trường; luôn upsert đè (không "tồn tại thì bỏ qua"); `ingest_runs` ghi đúng status.
- **Phụ thuộc:** L2.1 · **Điểm review:** grep producer không lộ dict thô ra API công khai; không retry vô hạn.
- **Trạng thái:** IMPLEMENTED

#### L2.4 — `ff_calendar_producer` kênh HTML (actual targeted) + on-demand lookup (L)
- **File mới:** mở rộng `ff_calendar_producer.py`, `tests/test_news_ff_producer_html.py` + fixture HTML.
- **Neo đặc tả:** contract §6.1 (HTML chỉ targeted, không poll; on-demand lookup; 3 quy tắc merge; lỗi → không retry, ghi run).
- **Nội dung:** hấp thụ `_fetch_html_events`/`_fetch_html_events_nextweek`
  (d.262/308), `_parse_html` + `_RowContext` rowspan (d.402/366),
  `_merge_actual_from_html` + `_normalize_event_name` (d.588/580),
  `_detect_html_timezone`/`_parse_html_time`; đường vào: (1) phần HTML của
  lượt khởi động, (2) nút "Cập nhật actual" — cả hai qua
  `repo.events_pending_actual(now)`; (3) lookup một sự kiện theo id
  (on-demand, ghi `ingest_runs` producer `on_demand_lookup`).
- **Test:** parse HTML fixture (rowspan, timezone); targeted đúng ngày/tuần; merge không NULL-đè actual; xung đột actual → ưu tiên user + run log; 429/lỗi → run `failed`/`partial`, không retry lặp.
- **Phụ thuộc:** L2.3, L2.2 (`events_pending_actual`) · **Điểm review:** đối chiếu `_parse_html` cũ ↔ mới trên cùng fixture (B3 mức hàm); xác nhận không có đường poll.
- **Trạng thái:** IMPLEMENTED

#### L2.5 — `rss_producer` (M)
- **File mới:** `services/news_producers/rss_producer.py`, `tests/test_news_rss_producer.py` + fixture XML.
- **Neo đặc tả:** contract §6.2; khóa `rss_poll_interval_minutes`/`rss_window_hours` (§7 — đọc qua `core/news_policy`, không hard-code 24h).
- **Nội dung:** hấp thụ từ `news_service.py` — 3 query Google News broad
  (d.1207-1211), 6 query phát biểu Trump/Fed/Nhật/Anh/EU (d.2621-2628, kind
  `statement` + `speaker_role`), `EXTRA_RSS_FEEDS` FXStreet/Investing
  (d.521-524), parser `ElementTree` `_rss_items` (d.2696, mỗi feed [:8]),
  `parse_rss_time` (d.3042), giới hạn 10 statement (d.2675); converter →
  `NewsItem` (dedupe theo title lowercased → `dedupe_key`); `ThreadPoolExecutor`
  giữ khuôn cũ (max 3/6); `record_run` producer `rss` với `error_type` phân loại.
- **Test:** fixture XML từng feed; dedupe trùng title; cửa sổ thời gian theo policy; feed chết → run `partial`, các feed khác vẫn ghi.
- **Phụ thuộc:** L2.1, L1.1 · **Điểm review:** query/URL lấy đúng danh sách cũ (không bịa nguồn mới); window từ policy.
- **Trạng thái:** IMPLEMENTED

#### L2.6 — `fred_rate_producer` (S)
- **File mới:** `services/news_producers/fred_rate_producer.py`, `tests/test_news_fred_producer.py`.
- **Neo đặc tả:** contract §6.3 (QĐ-1 phương án A); §4.4 (trend không nằm trong producer).
- **Nội dung:** hấp thụ `interest_rate_service.py` — `FRED_SERIES` 8 tiền tệ
  (d.17-26), `_fetch_from_fred` (d.155, endpoint observations, lấy ≥2 obs),
  đường FF HTML lãi suất `_update_from_forexfactory` + `_FOREX_RATE_EVENTS`
  (d.76/29-38, `source=ff_html`), fallback `_load_fallback` đọc
  `config/interest_rates.json` (`source=config_fallback`); chu kỳ theo khóa
  `fred_refresh_hours`; ghi `repo.add_rate_observations` (UNIQUE
  `(currency, observed_at, source)`); **không tính trend** (consumer gọi
  `latest_rates` ở L2.2); **không đụng cache 6h in-memory cũ** (file cũ untouched).
- **Test:** FRED mock ok/lỗi → fallback chain đúng thứ tự; source ghi đúng enum; obs trùng → upsert không nhân bản.
- **Phụ thuộc:** L2.1, L1.5 · **Điểm review:** diff logic với file gốc — chỉ đổi đích ghi; `interest_rate_service.py` không bị sửa.
- **Trạng thái:** IMPLEMENTED

#### L2.7 — `NewsController` + worker + đăng ký DI (M)
- **File mới:** `controllers/news_controller.py`, `workers/news_worker.py`, `tests/test_news_controller.py`.
- **Điểm chạm additive:** `controllers/app_controller.py` (property lazy theo khuôn d.141-148).
- **Neo đặc tả:** contract §3 (bảng lớp), §6.1 (4 lượt thu), §6.4 (nhập tay), §8.
- **Nội dung:** controller ủy quyền mỏng khuôn `journal_controller` (không tự
  tính): điều phối lịch producer theo policy (RSS poll, FRED refresh — timer
  do worker/app sở hữu, chưa bật lượt khởi động, đó là L3.6); đường nhập tay
  validate §6.4 (bắt buộc: giờ đăng, loại, nội dung, đồng tiền) →
  `upsert_items(kind=user_note, source=user)`; `set_excluded`/`delete_user_note`
  (chỉ user_note); on-demand lookup cắm vào `event_actual_or_lookup`; worker
  `QObject + pyqtSlot + signals` theo khuôn `ai_test_worker.py` (không QThread
  subclass mới); **chưa có đường AI** (thêm ở L3.5).
- **Test:** orchestration với repo/producer giả (fake có kiểu, không mock sâu); validate nhập tay đủ nhánh; DI: battery cũ xanh nguyên trạng + property mới lazy.
- **Phụ thuộc:** L2.2-L2.6 · **Điểm review:** controller không moi ruột dict (C3/S2); không logic trong worker.
- **Trạng thái:** IMPLEMENTED

### Bước 3 — Màn Quản lý tin + AI nhận định

#### L3.1 — `trend_prompt_builder` + `trend_verdict_parser` (M)
- **File mới:** `core/trend_prompt_builder.py`, `core/trend_verdict_parser.py`, `tests/test_news_trend_prompt.py`, `tests/test_news_trend_parser.py`.
- **Neo đặc tả:** contract §9.1 bước 3+5; khóa `ai_window_days`/`ai_min_items`/`ai_horizons` truyền qua tham số (hàm thuần).
- **Nội dung:** builder dựng prompt từ tập `CalendarEvent`/`NewsItem` đã chuẩn
  hóa (AI chỉ nhận định trên dữ liệu trong prompt — cấm bịa; doctrine kế thừa);
  `prompt_hash` ổn định (hash khuôn, không hash dữ liệu — đổi khuôn mới đổi
  hash); parser JSON 3 horizon đúng enum §4.5, `rationale` tiếng Việt,
  `evidence_item_ids`; JSON hỏng → tín hiệu "retry một lần" (parser thuần trả
  kết quả/lỗi, **việc retry là của controller L3.5**); thiếu horizon → từ chối
  toàn bộ, không lưu rác.
- **Test:** prompt ổn định + hash đổi khi khuôn đổi; parser: hợp lệ/lỗi/thiếu horizon/thừa horizon; không chuỗi hiển thị trong core (L3).
- **Phụ thuộc:** L1.1, L1.3 · **Điểm review:** builder/parser không import services/Qt; hash không chứa dữ liệu tin.
- **Trạng thái:** IMPLEMENTED

#### L3.2 — Khung màn Quản lý tin: bảng + bộ lọc + chi tiết dòng (L)
- **File mới:** `ui/screens/news_screen.py`, `tests/test_news_screen_smoke.py`.
- **Điểm chạm additive:** `ui/navigation.py`, `ui/main_window.py` (sổ R1).
- **Neo đặc tả:** `screen_design.md` mục News Screen — bố cục, **từ điển hiển
  thị 8 nhóm enum** (nhãn đúng từng chuỗi đã đăng ký), badge semantic, chi
  tiết dòng (provenance + `raw_json` + link ngoài), trạng thái tải/rỗng.
- **Nội dung:** table model khuôn `JournalTableModel` (DisplayRole/ForegroundRole
  qua `semantic_qcolor` theme_manager d.124); `configure_table` (layout_system
  d.217-231), `page_header`/`card`/`action_button` (`ui/screens/shared.py`),
  `ResponsiveRow`, empty state `empty_state_html` (`ui/rich_text.py`); đọc qua
  `NewsController` trong worker (không query ở GUI thread); bộ lọc đúng enum
  contract (S5) — nhãn từ từ điển, không phát minh nhãn mới.
- **Test:** smoke offscreen (khuôn `tests/test_dashboard_status_cards.py`) +
  render non-offscreen `QT_QPA_PLATFORM=windows` (yêu cầu plan Bước 3); bảng
  có dữ liệu giả → đúng nhãn từ điển; empty state hiện khi lọc rỗng.
- **Phụ thuộc:** L2.7 · **Điểm review:** đối chiếu từng bullet bố cục screen_design; sidebar thêm mục "Tin tức" không vỡ layout 800px.
- **Trạng thái:** IMPLEMENTED

#### L3.3 — Hành vi tương tác: nhập/sửa tin + 2 nút ForexFactory (M)
- **File mới:** mở rộng `news_screen.py`, `tests/test_news_screen_actions.py`.
- **Neo đặc tả:** screen_design "Hành vi lấy dữ liệu ForexFactory (2 nút)" + "Hành vi nhập/sửa tin"; contract §6.1/§6.4.
- **Nội dung:** form nhập `user_note` (validate hiện lỗi trên form, không ghi
  DB khi thiếu); sửa/xóa chỉ `source=user`; toggle Loại trừ (không nút xóa tin
  tự động); nút "Lấy lịch kinh tế" → controller → producer JSON (disable +
  progress + tóm tắt mới/cập nhật; lỗi → thông báo nguyên nhân, không retry);
  nút "Cập nhật actual" → HTML targeted (lỗi → gợi ý "Nhập actual bằng tay"
  mở form điền sẵn sự kiện liên quan).
- **Test:** offscreen với controller giả: trạng thái nút khi chạy, nhánh lỗi hiện đúng thông báo, form thiếu trường không ghi.
- **Phụ thuộc:** L3.2 · **Điểm review:** không có đường mạng nào từ UI ngoài 2 nút → controller (nguyên tắc screen_design).
- **Trạng thái:** IMPLEMENTED

#### L3.4 — Xuất/nhập file CSV-JSON (S)
- **File mới:** mở rộng `news_screen.py` + `services/news_file_transfer.py` (logic đọc/ghi file thuần qua repo — UI không tự parse), `tests/test_news_file_transfer.py`.
- **Điều kiện kèm theo — QĐ-4 (Owner duyệt 22/09/2026, §5):** lô này BẮT
  BUỘC gom công thức `dedupe_key` §4.3 về một hàm thuần duy nhất trong
  `core/news_models.py`; sửa `rss_producer.py` + `news_controller.py` xóa hai
  bản sao; import của `news_file_transfer.py` gọi cùng hàm đó (cấm bản sao thứ
  ba); contract §11b thêm dòng chủ sở hữu cùng commit (D2). Chi tiết 5 khoản
  tại QĐ-4 mục 5. File của ca được sửa trong ca: `core/news_models.py`,
  `services/news_producers/rss_producer.py`, `controllers/news_controller.py`,
  `docs/news/news-architecture.md` (chỉ §11b).
- **Neo đặc tả:** contract §10; screen_design "Hành vi xuất file"/"Hành vi nhập file"; QĐ-4 (§5).
- **Nội dung:** export theo khoảng ngày đang lọc → `%APPDATA%/ai-market-analyst/exports/`
  (thư mục qua helper paths); import upsert theo `dedupe_key`, `source=import`,
  không ghi đè `actual` chính thống trừ khi bản ghi `stale`; chạy nền +
  progress + tóm tắt mới/cập nhật/bỏ-qua-trùng.
- **Test:** round-trip CSV/JSON; import đè đúng quy tắc `stale`; file hỏng → lỗi thân thiện, DB nguyên vẹn; QĐ-4 khoản 5 — test `dedupe_key` hiện có của L2.5/L2.7 xanh nguyên trạng + test thuần cho hàm mới.
- **Phụ thuộc:** L3.2 · **Điểm review:** parse/serialize không nằm trong UI; đường dẫn export qua `paths.py`; QĐ-4 — grep toàn miền Tin tức chỉ còn ĐÚNG MỘT định nghĩa công thức §4.3 (trong `core/news_models.py`).
- **Trạng thái:** IMPLEMENTED

#### L3.5 — Dialog AI nhận định xu hướng (L)
- **File mới:** mở rộng `news_screen.py` (dialog) + `controllers/news_controller.py` (đường AI: đọc dữ liệu → đếm → builder → `AIService.analyze` trong worker → parser → retry một lần → `add_verdicts`), `tests/test_news_ai_dialog.py`.
- **Neo đặc tả:** contract §9.1-§9.2; screen_design "Cửa sổ AI nhận định xu hướng".
- **Nội dung:** QDialog 520×640 không modal toàn app — khuôn trộn
  `_show_headline_detail` (dashboard_screen d.1072: QDialog size cố định) +
  `AuditWorker(QThread)` (scanner_detail_screen d.2835: gọi AI ngoài GUI
  thread) — **không gọi `analyze()` đồng bộ trong callback như dialog cũ**;
  chọn phạm vi cặp/tiền; đếm tin trong `ai_window_days` hiển thị trước, dưới
  `ai_min_items` → "Không đủ dữ liệu nhận định", **không gọi AI** (B4); 3 thẻ
  chân trời theo `ai_horizons`; lịch sử `verdicts_for`; dẫn chứng bấm → đóng
  dialog nhảy dòng bảng; cảnh báo advisory **thường trực**; lỗi provider →
  `friendly_error()`; parser hỏng → retry một lần → thất bại không lưu verdict rác.
- **Test:** insufficient_data không phát lời gọi AI (fake service đếm call); verdict lưu đủ `input_snapshot_json` + `prompt_hash`; advisory label tồn tại; dialog smoke offscreen.
- **Phụ thuộc:** L3.1, L3.2, L2.7 · **Điểm review:** ranh giới §9.2 — không screen/worker nào khác đọc verdict; AI chạy worker thật (không processEvents đồng bộ).
- **Trạng thái:** PLANNED

#### L3.6 — Bật lượt fetch khởi động + retention purge (S)
- **File mới:** mở rộng `controllers/news_controller.py` (+ cờ phiên), test bổ sung.
- **Điểm chạm additive:** không file cũ mới nào ngoài những gì L2.7 đã đăng ký (hook khởi động qua AppController/main theo đường controller có sẵn — nếu phải sửa `main.py` thì **dừng, báo Owner** vì ngoài sổ R1).
- **Neo đặc tả:** contract §6.1 lượt 1 (một lần mỗi phiên, không timer), §4.6 (purge khi khởi động).
- **Nội dung:** khi app khởi động: `purge_expired_runs()` (retention từ policy) + lượt JSON tuần này/tuần sau + HTML targeted cho `events_pending_actual`; cờ `_fetched_this_session` đảm bảo đúng 1 lần (khuôn `_auto_scanned_this_session` của Scanner).
- **Test:** gọi 2 lần chỉ fetch 1; purge xóa đúng run quá hạn, không đụng tin/verdict.
- **Phụ thuộc:** L3.3 (nút dùng chung đường), L2.7 · **Điểm review:** không timer/poll FF nào được tạo; hành vi boot cũ không đổi khi tính năng chưa bật.
- **Trạng thái:** PLANNED

### Bước 4 — Nghiệm thu tổng + cổng cưỡng chế E2

#### L4.1 — Cổng E2: cách ly verdict + import-linter + quét chuỗi hiển thị (M)
- **File mới:** `.importlinter` (config **chưa tồn tại trong repo** — tạo mới, phạm vi tối thiểu miền Tin tức để không kéo vi phạm legacy vào cổng, B6), `tests/test_news_e2_gates.py`.
- **Neo đặc tả:** contract §9.2 (cơ chế cưỡng chế a/b/c), §14 "Cổng E2".
- **Nội dung:** (a) test quét AST/import mọi module `core/`, `services/`,
  `controllers/`, `workers/`, `ui/` ngoài danh sách cho phép (`news_controller`,
  `news_screen`, `news_repository`) → cấm import/query `verdicts_for`,
  `ai_trend_verdicts`, `trend_verdict_parser`; (b) import-linter contract:
  `core.news_*`/`core.rate_trend`/`core.trend_*` không import
  services/ui/controllers/PyQt6; (c) quét chuỗi hiển thị tiếng Việt trong các
  module `core/` mới (L3).
- **DoD đặc biệt:** **tự chứng minh cổng đỏ** — thêm vi phạm giả vào nhánh tạm, chạy đỏ, hoàn nguyên (ghi evidence vào commit message).
- **Phụ thuộc:** L3.5 (đủ module để quét) · **Điểm review:** cổng không bỏ sót `dashboard_screen`/`scanner_*`/`telegram_*`.
- **Trạng thái:** PLANNED

#### L4.2 — Nghiệm thu tổng + đồng bộ tài liệu + đóng plan (M)
- **File:** không code mới; sửa tài liệu + chạy nghiệm thu.
- **Nội dung:** (1) full battery `python -m pytest -q` xanh; (2) smoke hiện có
  (`scripts/scanner_smoke.py`, `scripts/smc_ui_smoke.py` kể cả non-offscreen)
  xanh; (3) build PyInstaller `.exe` đạt, boot bản đóng gói: `news.db` tạo ở
  %APPDATA% (không ghi thư mục cài đặt), migration + `news_policy.json` bundle
  đủ; (4) tài liệu: contract §16 + screen_design + architecture.md đổi PLANNED
  → IMPLEMENTED đúng các mục đã làm; `docs/README.md` bỏ dòng plan này;
  (5) **xóa plan file này trong commit nghiệm thu** (D3); (6) tuyên bố
  READY-FOR-CONNECT — sổ nợ #1 **chưa đóng** (chỉ đóng tại đấu nối b).
- **Phụ thuộc:** tất cả · **Điểm review:** bảng trạng thái mục 8 — 20/20 IMPLEMENTED trước khi chạy lô này.
- **Trạng thái:** PLANNED

## 5. Quyết định đã chốt

**QĐ-1 — Bộ sản xuất lãi suất FRED trong giai đoạn song song: PHƯƠNG ÁN A —
Owner duyệt 21/09/2026.** Tạo mới `services/news_producers/fred_rate_producer.py`
hấp thụ logic FRED của `interest_rate_service.py` (copy logic, không sửa file
cũ — đối xứng đúng khuôn FF: `forex_factory_client` → `ff_calendar_producer`);
`interest_rate_service.py` untouched, tiếp tục nuôi cache lãi suất cho vĩ mô
di sản, bị xóa tại đấu nối (b). Lý do: "đổi đích ghi" trong giai đoạn song
song sẽ cắt nguồn cache của macro cũ — vi phạm §3.1 khoản 1 (giữ nguyên hành
vi runtime 100%). Hai hệ fetch FRED độc lập song song là chấp nhận có chủ
đích theo B7 (tần suất thấp). Contract đã sửa cùng đợt: §3 (sơ đồ + bảng
lớp), §3.1 khoản 1 (thêm `interest_rate_service.py` vào danh sách cấm sửa),
§6 (sổ đăng ký producer), §6.3 (viết lại theo `fred_rate_producer`), §11b,
§12 (danh sách code cũ bị thay thế).

**QĐ-2 — Migration của `news.db` đặt tại thư mục con `data/migrations/news/`
(quyết định kỹ thuật từ khảo sát code, 21/09/2026).** Runner journal
`JournalService.migrate()` glob `*.sql` **không đệ quy** trên
`data/migrations/` và áp mọi file tìm thấy vào `journal.db` — nếu để SQL của
news cùng thư mục gốc, bảng tin tức sẽ bị tạo nhầm vào journal DB và ngược
lại runner news sẽ áp migration journal. Thư mục con tách hai DB sạch, không
cần sửa code journal (R1). Contract §4.1 ("migration trong `data/migrations/`")
vẫn đúng nguyên văn — thư mục con nằm trong `data/migrations/`. Đóng gói:
thêm 1 dòng `datas` trong spec (L1.2).

**QĐ-3 — Chủ sở hữu loader chính sách: `core/news_policy.py` (quyết định kỹ
thuật từ khảo sát code, 21/09/2026).** Contract §7 quy định tệp
`config/news_policy.json` nhưng §11b **chưa đăng ký chủ sở hữu phép nạp/validate**
— thiếu dòng này là khuyết D4. Chọn `core/` theo án lệ
`core/scanner_order_policy.py` (Phụ lục C — chính sách có phiên bản, fail-closed).
Điều khoản §3 + §11b được bổ sung **trong commit của L1.1** (D2); nếu Owner
không đồng ý vị trí `core/` thì sửa trước khi L1.1 chạy.

**QĐ-4 — Chủ sở hữu duy nhất của công thức `dedupe_key` (§4.3):
`core/news_models.py` (Owner duyệt 22/09/2026, khi nghiệm thu L2.7).** Hiện
trạng được ghi nhận tại biên bản nghiệm thu L2.7 (commit 6eaa0bd): công thức
§4.3 (hash của url, else hash của `title + published_utc`) đang bị **nhân bản
hai nơi** — `rss_producer._dedupe_key` và `news_controller._user_note_dedupe_key`
(hai bản giống hệt nhau, khai báo V2 điểm lệch 4 của lô) — trái nguyên tắc
"một điểm thay đổi duy nhất". Lô **L3.4** (xuất/nhập file — nơi sẽ cần đúng
công thức này cho đường import theo `dedupe_key`, nguy cơ bản sao thứ ba)
**BẮT BUỘC** thực hiện trong phạm vi lô:

1. Chuyển công thức thành **một hàm thuần duy nhất** trong `core/news_models.py`
   (hàm trên mô hình miền, không I/O — L2).
2. Sửa `services/news_producers/rss_producer.py` + `controllers/news_controller.py`
   gọi hàm đó, xóa hai bản sao (đây là các file mới của ca — được sửa trong ca,
   án lệ L2.2 "mở rộng file mới của ca").
3. Đường import của `news_file_transfer.py` gọi **cùng hàm đó** — cấm tạo bản
   sao thứ ba.
4. Contract §11b thêm dòng chủ sở hữu "Công thức `dedupe_key` của `news_items`
   (§4.3) → `core/news_models.py`" **trong cùng commit** (D2). Phạm vi QĐ-4
   chỉ là công thức `news_items` — `dedupe_key` của `news_events` (§4.2) đang
   có một chủ sở hữu duy nhất trong `ff_calendar_producer`, không đụng tới.
5. Giá trị khóa không đổi (hành vi tương đương B3): test hiện có của L2.5/L2.7
   ghim `dedupe_key` phải xanh nguyên trạng; thêm test thuần cho hàm mới.

Nợ đóng khi L3.4 đạt; nếu việc gom này đụng vấn đề ngoài phạm vi → DỪNG, báo
BLOCKED theo kỷ luật, không tự mở rộng.

## 6. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| ForexFactory chặn/429 khi scrape HTML | Chế độ không poll (4 lượt duy nhất); lỗi → thông báo rõ + nhập tay; không retry vòng lặp (§6.1); L2.4 có test 429 |
| Trùng lặp fetch RSS/FRED hai hệ song song | Chấp nhận có chủ đích (B7) — tần suất thấp; kết thúc tại đấu nối (b) khi code cũ bị xóa |
| Migration news bị runner journal áp nhầm | QĐ-2 — thư mục con `data/migrations/news/`; L1.2 có test khẳng định `journal.db` không đổi |
| SQLite đa thread nghẽn GUI | WAL + busy_timeout theo khuôn journal; truy vấn GUI có index + giới hạn dòng (§4.1); đọc qua worker (L3.2) |
| Trượt phạm vi sang Dashboard/vĩ mô | Sổ điểm chạm additive đóng (mục 3); cổng E2 L4.1; E1 mỗi lô |
| Hành vi UI phát sinh ngoài đặc tả | V2 "cấm hành vi không khai báo" — mọi thay đổi screen_design phải Owner duyệt trước, cùng commit (D2) |
| import-linter chưa có trong repo | L4.1 tạo config phạm vi tối thiểu miền Tin tức; không mở rộng toàn repo trong ca này (tránh chặn bởi vi phạm legacy — B6) |
| Coder "cải tiến" logic hấp thụ (FF/RSS/FRED) | DoD các lô hấp thụ yêu cầu đối chiếu fixture/logic gốc (B3 mức hàm); cấm đổi ngưỡng không bằng chứng (B5, L1.5) |

## 7. Tiêu chí nghiệm thu tổng (Definition of Done toàn ca)

1. 20/20 lô IMPLEMENTED; battery + smoke + build `.exe` xanh (L4.2).
2. Bằng chứng R1: `git diff` rỗng trên `news_service.py`,
   `forex_factory_client.py`, `interest_rate_service.py`, `dashboard_screen.py`;
   5 file additive chỉ đúng thay đổi đã đăng ký; test cũ xanh nguyên trạng.
3. Cổng E2 hoạt động và đã tự chứng minh đỏ-khi-vi-phạm (L4.1).
4. Tài liệu chính đồng bộ trạng thái; plan file đã xóa (D3).
5. Tuyên bố READY-FOR-CONNECT; sổ nợ #1 **chưa đóng** (chỉ đóng tại đấu nối b).

## 8. Bảng trạng thái lô (Tech Lead cập nhật mỗi lô — R5)

Thứ tự giao = thứ tự phụ thuộc dưới đây; lô cùng tầng không phụ thuộc nhau
có thể giao song song cho 2 coder (ví dụ L1.4 ∥ L1.5; L2.3 ∥ L2.5 ∥ L2.6).

| Lô | Nội dung | Bước | Phụ thuộc | Cỡ | Trạng thái |
|---|---|---|---|---|---|
| L1.1 | Chính sách + loader `core/news_policy.py` | 1 | — | S | IMPLEMENTED |
| L1.2 | `news_db_path()` + migration `data/migrations/news/001` + spec | 1 | — | S | IMPLEMENTED |
| L1.3 | `core/news_models.py` (6 dataclass + enum) | 1 | L1.2 | S | IMPLEMENTED |
| L1.4 | `core/news_freshness.py` | 1 | L1.3 | M | IMPLEMENTED |
| L1.5 | `core/rate_trend.py` | 1 | L1.3 | S | IMPLEMENTED |
| L2.1 | Repository GHI + runner migration + 3 quy tắc merge | 2 | L1.1-1.4 | L | IMPLEMENTED |
| L2.2 | Repository ĐỌC + `store_state` + test hợp đồng C4 | 2 | L2.1, L1.4, L1.5 | M | IMPLEMENTED |
| L2.3 | `ff_calendar_producer` kênh JSON | 2 | L2.1 | M | IMPLEMENTED |
| L2.4 | `ff_calendar_producer` kênh HTML + on-demand lookup | 2 | L2.3, L2.2 | L | IMPLEMENTED |
| L2.5 | `rss_producer` | 2 | L2.1, L1.1 | M | IMPLEMENTED |
| L2.6 | `fred_rate_producer` (QĐ-1A) | 2 | L2.1, L1.5 | S | IMPLEMENTED |
| L2.7 | `NewsController` + worker + DI | 2 | L2.2-L2.6 | M | IMPLEMENTED |
| L3.1 | `trend_prompt_builder` + `trend_verdict_parser` | 3 | L1.1, L1.3 | M | IMPLEMENTED |
| L3.2 | Khung màn Quản lý tin (bảng/lọc/từ điển/chi tiết) | 3 | L2.7 | L | IMPLEMENTED |
| L3.3 | Nhập/sửa tin + 2 nút ForexFactory | 3 | L3.2 | M | IMPLEMENTED |
| L3.4 | Xuất/nhập CSV-JSON | 3 | L3.2 | S | IMPLEMENTED |
| L3.5 | Dialog AI nhận định xu hướng | 3 | L3.1, L3.2 | L | PLANNED |
| L3.6 | Bật fetch khởi động + retention purge | 3 | L3.3, L2.7 | S | PLANNED |
| L4.1 | Cổng E2 (verdict isolation + import-linter + quét chuỗi) | 4 | L3.5 | M | PLANNED |
| L4.2 | Nghiệm thu tổng + đồng bộ tài liệu + xóa plan | 4 | tất cả | M | PLANNED |

## Phụ lục — Khuôn prompt giao lô chuẩn (Tech Lead dùng cho mọi lô)

Nguyên tắc: prompt **tự chứa** (phiên coder không chia sẻ context phiên điều
phối), **trỏ điều khoản thay vì chép đặc tả** (D5), **đóng phạm vi bằng danh
sách file**, **đòi bằng chứng máy-đọc** cho DoD. Điền 6 chỗ `<...>`:

```text
[CA TIN TỨC — LÔ <Lx.y>: <tên lô>]

Bạn là coder của dự án AIMarketAnalyst (thư mục gốc d:\Projects\AIMarketAnalyst).
Thực hiện ĐÚNG MỘT lô dưới đây. Không mở rộng phạm vi, không "tiện tay" sửa
gì ngoài lô.

## 1. Đọc trước khi viết code (theo thứ tự, bắt buộc)
1. docs/plans/news-data-layer-plan.md — mục lô <Lx.y> + §3 ràng buộc R1-R8
   + sổ điểm chạm additive.
2. docs/news/news-architecture.md — §<các mục neo của lô> (đặc tả thẩm quyền
   duy nhất — code phải đúng từng hành vi).
3. <tài liệu bổ sung của lô: screen_design.md mục News Screen / architecture-rules.md chương...>
4. Code khuôn mẫu (CHỈ ĐỌC để copy đúng tiền lệ, không sửa):
   <file + số dòng, lấy từ mục "Nội dung" của lô>.

## 2. Sản phẩm bàn giao
- File mới: <đúng danh sách trong lô>.
- File cũ được sửa (nếu lô có, đúng giới hạn đã ghi): <danh sách hoặc "không">.
- CẤM đụng: services/news_service.py, services/forex_factory_client.py,
  services/interest_rate_service.py, ui/screens/dashboard_screen.py, và mọi
  file không liệt kê ở trên.

## 3. Hành vi phải hiện thực
Đối chiếu từng gạch đầu dòng mục "Nội dung" của lô <Lx.y> trong plan — đó là
danh sách kiểm tra của bạn; chi tiết ngữ nghĩa đọc tại contract §<...>.
Cấm hành vi không có điều khoản (V2); cấm bịa con số/ngưỡng (B5) — mọi giá
trị vận hành đọc từ policy qua loader.

## 4. Test phải viết
<danh sách file test + các nhánh bắt buộc, chép từ mục "Test" của lô>.
Khuôn test theo tiền lệ repo: <contract test mẫu / smoke offscreen mẫu...>.

## 5. Definition of Done — báo cáo kèm bằng chứng, không báo cáo miệng
1. `python -m pytest -q` toàn battery: xanh, không regressed test cũ.
2. Dán `git diff --stat HEAD~1` của commit lô — chứng minh chỉ chạm file được phép.
3. Một commit duy nhất (D2): code + test + tài liệu (nếu lô có mục "Tài liệu
   cùng commit"). Thông điệp commit: tên lô + trả lời 4 câu hỏi E1 + dòng cuối
   `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
4. Sửa cột Trạng thái lô <Lx.y> ở plan §8 thành IMPLEMENTED trong CHÍNH commit đó.
5. Thư mục audit/output tạm (nếu test sinh file) đặt trong temp, không commit rác.

## 6. Kỷ luật dừng
- Thiếu điều khoản / đặc tả mâu thuẫn / buộc phải sửa file ngoài danh sách →
  DỪNG, báo BLOCKED kèm vị trí cụ thể. Không tự quyết, không suy diễn ý Owner.
- Lô hấp thụ logic cũ: hành vi phải TƯƠNG ĐƯƠNG bản gốc trên cùng fixture
  (B3) — không cải tiến, không đổi ngưỡng, không đổi danh sách nguồn.
- Không làm trước việc của lô sau (kể cả khi "thấy tiện").
```

Ba biến thể theo tính chất lô (bổ sung vào khung trên):
- **Lô hấp thụ (L1.5, L2.3-L2.6):** dán thêm vào §1 chỉ dẫn "đọc file gốc
  `<tên>` các hàm `<tên hàm + dòng>` — danh mục hàm phải port nằm trong lô;
  port xong đối chiếu từng hàm bằng test trên fixture lấy từ hành vi cũ".
- **Lô UI (L3.2-L3.5):** thêm "chạy smoke non-offscreen
  `QT_QPA_PLATFORM=windows python -X utf8 scripts/smc_ui_smoke.py` và test
  smoke của màn; nhãn hiển thị phải đúng TỪNG CHUỖI trong từ điển của
  screen_design — không tự đặt nhãn".
- **Lô cổng E2 (L4.1):** thêm "chứng minh cổng ĐỎ trước khi xanh: tạo vi
  phạm giả trên nhánh tạm, chạy test đỏ, dán output, hoàn nguyên — evidence
  đỏ nằm trong commit message".
