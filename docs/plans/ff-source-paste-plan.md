# Plan triển khai — Ca "Nguồn dán FF" (dán mã nguồn trang ForexFactory)

> **Trạng thái: DUYỆT — Owner duyệt 24/09/2026** (lập 24/09/2026, vai trò Tech Lead).
> Vòng đời theo D3 (`docs/README.md`): hoàn tất ca → **xóa file này** (lịch sử
> trong Git); điều khoản còn hiệu lực đã nằm trong tài liệu chính đích danh.
> Nguồn thẩm quyền: [`../news/news-architecture.md`](../news/news-architecture.md)
> **sửa đổi đợt 3 (Owner duyệt 24/09/2026 — §6.1, §10, §13 đợt 3)** +
> [`../ui/screen_design.md`](../ui/screen_design.md) mục News Screen (phần đợt 3
> PLANNED) + [`../architecture/architecture-rules.md`](../architecture/architecture-rules.md).
> Plan này **không lặp lại đặc tả** — chỉ xếp thứ tự, tiêu chí hoàn thành và
> quyết định triển khai (D5: trỏ về nguồn, không chép).
>
> **Cách dùng cho Tech Lead:** mỗi lô (F*) = một đơn vị giao cho coder =
> **một commit D2** (code + test + tài liệu cùng commit). Chỉ giao lô kế khi lô
> trước đạt Trạng thái IMPLEMENTED + DoD (kỷ luật A3 — PO tự chuyển prompt).
> Cột "Điểm review" là trọng tâm khi chấm commit của coder.

---

## 1. Mục tiêu và giá trị người dùng

Thực thi quyết định Owner đợt 3+4 (24/09/2026, contract §13): **bỏ hoàn toàn
mọi đường thu tự động từ ForexFactory và xuất/nhập file CSV-JSON**; thay bằng
kênh duy nhất, **xác nhận trước khi ghi (đợt 4)**: **người dùng dán mã nguồn
trang FF → hệ thống bóc tách (`calendarComponentStates` JSON) → hiển thị bảng
xem trước → người dùng kiểm tra, bấm "Cập nhật" → mới ghi `news.db`** với
chống trùng tuyệt
đối (`dedupe_key` + 3 quy tắc merge giữ nguyên văn). Căn cứ: cả ba kênh FF tự
động đều bất khả thi với app (nextweek 404 vĩnh viễn; thisweek 429 tái diễn;
HTML + wss bị Cloudflare chặn client không-phải-browser — bằng chứng trong
memory dự án + lịch sử Git), trong khi browser người dùng luôn qua được và
việc bóc tách đã được chứng minh bằng code chạy thật trên source Owner dán
24/09/2026.

Giá trị người dùng trực tiếp: lịch kinh tế + actual + lãi suất `ff_html` vào
`news.db` ổn định (không 404/429/SSL), chất lượng dữ liệu cao hơn scrape cũ
(`dateline` UTC epoch, có `revision`/`notice`), bù được cả ngày quá khứ.

## 2. Phạm vi

**Trong phạm vi:** 5 lô (F1–F5) — (1) **XÓA HOÀN TOÀN** các đường FF tự động
+ xuất/nhập file (lệnh Owner: việc đầu tiên); (2) parser mã nguồn trang;
(3) đường nhập qua controller/repository; (4) UI dialog dán + panel thiếu số
liệu; (5) nghiệm thu tổng + đồng bộ tài liệu + đóng plan.

**Ngoài phạm vi (cấm mở rộng trong ca này):**
- Hai ca đấu nối (a) Dashboard / (b) vĩ mô (contract §3.1) — giữ nguyên lộ
  trình, không đụng.
- Code legacy: `news_service.py`, `forex_factory_client.py`,
  `interest_rate_service.py`, `dashboard_screen.py` — untouched 100% tới đấu
  nối (QĐ-1A/B7 kế thừa từ ca Tin tức).
- RSS/FRED tự động định kỳ (giữ nguyên hành vi L2.5/L2.6/L3.7 — chỉ gỡ kênh
  FF-HTML qua mạng trong `fred_rate_producer` theo §6.3 đợt 3); dialog AI,
  nhập tay `user_note`, cổng E2, timer L3.7, retention purge L3.6 — giữ.
- Kênh wss `calendar-feed`, QtWebEngine, transport giả lập fingerprint — đã
  bị loại theo quyết định đợt 3, cấm xuất hiện lại dưới mọi dạng.
- `main.py`, `controllers/app_controller.py`, `ui/main_window.py`,
  `ui/navigation.py` — **không đụng** (ca này KHÔNG có điểm chạm additive
  nào: hook QĐ-5 giữ nguyên vì `run_startup_turn` vẫn tồn tại, chỉ đổi phần
  thân theo §6.1 đợt 3).

**Khoảng trống tạm thời có chủ đích:** giữa F1 và F4, `news.db` chưa có
đường vào cho dữ liệu FF. Chấp nhận được vì **chưa có bên tiêu thụ
production nào của `news.db`** (Dashboard/vĩ mô vẫn đọc hệ legacy tới đấu
nối); hệ legacy untouched nên runtime tổng không đổi (B7 khoản 1).

## 3. Ràng buộc nền (mọi lô phải tuân thủ)

| # | Ràng buộc | Nguồn |
|---|---|---|
| R1 | Chỉ đụng **file của miền Tin tức** (liệt kê tường minh từng lô) + file mới; legacy và file hệ thống khác diff rỗng ở mọi lô (bằng chứng máy đọc: `git diff` trên danh sách cấm §2) | B7, QĐ-1A |
| R2 | Mỗi lô = code + test + tài liệu trong **một commit**; message nêu tên mục tài liệu sửa | D2 |
| R3 | Điều khoản phải tồn tại trước khi code — contract đợt 3 + screen_design đợt 3 **đã ban hành**; lô nào thấy thiếu/mâu thuẫn điều khoản → DỪNG báo Owner, không tự bịa hành vi | D1, V2 |
| R4 | Không con số vận hành mới; danh mục sự kiện lãi suất **kế thừa `_FOREX_RATE_EVENTS`** của `interest_rate_service.py` d.29-38 (chỉ ĐỌC file legacy để copy — nhãn B5 "kế thừa runtime hiện hành"); công thức `dedupe_key` gọi từ `core/news_models.py` (QĐ-4 — cấm bản sao) | S4, B5 |
| R5 | Mỗi lô trả lời 4 câu E1 trong commit message; cập nhật **KÉP** trạng thái (trường "Trạng thái" trong mục lô + dòng bảng §8) trong chính commit đó (bài học L3.6/L4.1 ca trước) | E1 |
| R6 | Không tên phiên bản trong định danh mới (`ff_source_parser`, `parse_pasted_source`, `commit_pasted_source`… mô tả nội dung — V3(b)); enum `source`/`producer` GIỮ chuỗi đóng băng, chỉ dùng theo ngữ nghĩa đợt 3 (`ff_html` = dán source; `user` = lượt dán; `ff_json`/`import`/`ff_crawler`/`on_demand_lookup` không phát sinh) | V3(a) |
| R7 | Không singleton/DI mới; parser là module hàm thuần trong `services/` | architecture.md |
| R8 | Mã nguồn trang thô (HTML text) không tồn tại ngoài `ff_source_parser` — controller/UI nhận source, giao thẳng parser, ra khỏi biên chỉ có `CalendarEvent`/`RateObservation`/kết quả có kiểu | C2, C3, §6.1 bước 2-3 |
| R9 | Nghiệm thu battery đối chiếu ngoại lệ **theo DANH TÍNH**, không đếm cứng: họ `tests/test_step3_fred.py` (4-6 failed tùy mạng/cache) + collection error `tests/test_smc_gate72_fix_acceptance.py` — ngoài danh tính này = ĐỎ, dừng | bài học L3.7/L4.2 |

**Sổ điểm chạm additive: RỖNG** — ca này không sửa file cũ nào ngoài miền
Tin tức. `git diff` trên `main.py`, `controllers/app_controller.py`,
`ui/main_window.py`, `ui/navigation.py`, `services/news_service.py`,
`services/forex_factory_client.py`, `services/interest_rate_service.py`,
`ui/screens/dashboard_screen.py` phải rỗng ở mọi lô.

## 4. Lộ trình 5 lô — phân lô chi tiết

Quy ước cỡ lô: **S** ≤ nửa phiên · **M** ≈ một phiên · **L** > một phiên.
Test mới/sửa trong `tests/test_news_*.py`. Thứ tự giao mặc định: tuần tự
F1→F2→F3→F4→F5 (lệnh Owner: xóa trước; F2 thuần file mới có thể giao song
song F1 nếu Tech Lead muốn, nhưng nghiệm thu vẫn theo thứ tự).

### F1 — XÓA HOÀN TOÀN đường FF tự động + xuất/nhập file (L)

- **Xóa file:** `services/news_producers/ff_calendar_producer.py`;
  `services/news_file_transfer.py`; `tests/test_news_ff_producer_json.py`;
  `tests/test_news_ff_producer_html.py`; `tests/test_news_file_transfer.py`;
  `tests/fixtures/ff_calendar_week.html` (GIỮ các fixture `rss_*.xml`).
- **Sửa file miền (được sửa trong ca):**
  - `controllers/news_controller.py`: gỡ `fetch_calendar_json`/`fetch_actual_html`
    (d.493/501), gỡ phần FF trong `run_startup_turn` (d.507 — **GIỮ** purge
    retention + khởi động lịch RSS/FRED L3.7 + cờ phiên; `StartupTurnResult`
    bỏ 2 trường json/html), gỡ seam on-demand lookup (`self._repo.on_demand_lookup = …`
    d.434 + `event_actual_or_lookup` delegate d.795), gỡ
    `export_news_range`/`import_news_file` (d.760/768), gỡ `_ff_producer`
    (d.428) + import liên quan; **docstring module viết lại theo thực tại đợt 3**
    (V2 — không mô tả luồng đã bỏ). GIỮ nguyên: nhập tay §6.4, AI §9, poll/refresh
    RSS-FRED, lịch producer L3.7, purge L3.6.
  - `services/news_repository.py`: gỡ `event_actual_or_lookup` (d.657) + seam
    `on_demand_lookup` (d.132/147-150); **GIỮ** `events_pending_actual` (ngữ
    nghĩa mới §8 đợt 3: nuôi panel hướng dẫn); docstring sửa tương ứng.
  - `services/news_producers/fred_rate_producer.py`: gỡ kênh FF-HTML
    (`_update_from_forexfactory` + `_FOREX_RATE_EVENTS` + import
    `forex_factory_client` — chuỗi nguồn còn **`fred` → `config_fallback`**
    theo §6.3 đợt 3); `RateFetchResult` bỏ đếm `ff_html_observations`; docstring sửa.
  - `ui/screens/news_screen.py`: gỡ 2 nút "Lấy lịch kinh tế"/"Cập nhật actual"
    + 2 nút "Xuất file"/"Nhập file" (TOOLBAR_LABELS d.265-269, hằng
    FETCH_JSON/HTML d.320-325) + dialog/worker riêng của 2 nút FF (slot thread
    D10) + luồng xuất/nhập file + gợi ý "Nhập actual bằng tay"; toolbar còn
    **[ Nhập tin | AI nhận định xu hướng ]**; từ điển hiển thị: nhãn `source`
    đổi theo screen_design đợt 3 (`ff_html` = "ForexFactory (mã nguồn trang)",
    `ff_json` = "ForexFactory (lịch — dữ liệu cũ)", `import` = "Nhập file (dữ
    liệu cũ)"); empty state gợi ý đổi "Lấy lịch kinh tế" → "Dán mã nguồn trang"
    (nút sẽ có ở F4 — lô này chỉ đổi chuỗi gợi ý).
  - **Test sửa cùng commit (D2 — đổi điều khoản = đổi test):**
    `tests/test_news_controller.py` (viết lại nhóm startup-turn: purge + schedule
    đúng 1 lần/phiên, KHÔNG json/html; gỡ nhóm nút FF/xuất-nhập/lookup seam);
    `tests/test_news_repository_contract.py` (gỡ ghim C4 `event_actual_or_lookup`
    — các ghim đọc khác XANH NGUYÊN TRẠNG); `tests/test_news_repository_write.py`
    (gỡ nhánh lookup nếu có); `tests/test_news_screen_actions.py` (gỡ test 2 nút
    FF + xuất/nhập; GIỮ test form nhập tay); `tests/test_news_screen_smoke.py`
    (inventory toolbar mới); `tests/test_news_fred_producer.py` (gỡ nhánh FF-HTML,
    ghim chuỗi nguồn mới fred→config_fallback).
- **CẤM đụng:** `main.py` (hook QĐ-5 giữ nguyên — `run_startup_turn` vẫn tồn
  tại), `workers/news_worker.py` (NewsWorker timer + NewsReadWorker giữ), mọi
  file legacy/hệ thống (§2).
- **Test phải đạt:** battery (R9) + 3 smoke (`scanner_smoke`, `smc_ui_smoke`
  offscreen + non-offscreen `QT_QPA_PLATFORM=windows`) EXIT=0; ghim lazy DI
  d.884, `test_main_py_has_exactly_one_startup_policy_owner`, cổng E2
  (`test_news_e2_gates.py`) xanh nguyên trạng.
- **Tài liệu cùng commit:** §8 + mục lô này (cập nhật KÉP — R5). Contract/
  screen_design đã ban hành trước (f546957) — không sửa nữa.
- **Phụ thuộc:** — · **Điểm review:** `git diff` danh sách cấm = rỗng; grep
  toàn miền Tin tức (controllers/services mới, workers, ui/screens/news_screen.py)
  KHÔNG còn `faireconomy|forexfactory.com|fetch_calendar|fetch_actual|on_demand_lookup|
  event_actual_or_lookup|news_file_transfer|ff_calendar_producer`; `run_startup_turn`
  còn đúng purge + schedule (test ghim); toolbar đúng 2 nút; nhãn từ điển đúng
  TỪNG CHUỖI screen_design đợt 3.
- **Trạng thái:** PLANNED

### F2 — Parser mã nguồn trang FF: `services/ff_source_parser.py` (M)

- **File mới:** `services/ff_source_parser.py`, `tests/test_news_ff_source_parser.py`,
  fixture source thật `tests/fixtures/ff_homepage_source.html`.
- **Fixture (điều kiện giao lô):** PO đính kèm **mã nguồn thật trang chủ FF
  Owner dán 24/09/2026** (bản đầy đủ hoặc cắt còn khối `calendarComponentStates`
  + `<head>` tối thiểu) khi giao lô. Coder KHÔNG bịa fixture "thật" (B5);
  fixture biến thể ngày/tuần (`ff_day_source.html`, `ff_week_source.html`) được
  phép **dựng theo cấu trúc** từ fixture thật (đa ngày trong `days[]`, có sự
  kiện `holiday`, có actual rỗng) và phải ghi nhãn "constructed" trong test.
  Thiếu fixture thật khi giao lô → DỪNG báo BLOCKED.
- **Neo đặc tả:** contract §6.1 bước 3-4 (ánh xạ trường + bóc lãi suất), §5
  (mô hình có kiểu), §11b (chủ sở hữu bóc tách), §14 (kiểm thử parser).
- **Nội dung:** hàm thuần (không I/O, không Qt — L2): nhận văn bản source →
  trích khối `window.calendarComponentStates[...]` (mọi component id, mọi ngày
  trong `days[]`) → `list[CalendarEvent]` theo đúng ánh xạ §6.1 bước 3
  (`dateline` epoch→`event_time_utc`+`day_key` UTC; `prefixedName`→`title`;
  `impactName`→`impact`, `holiday`→`non`; `forecast/previous/actual` rỗng→NULL;
  `revision`/`notice`/`ebaseId`/`soloUrl`→`raw_json` từng sự kiện; stamp
  `source=ff_html`; `dedupe_key` gọi hàm `core/news_models.py` — R4) +
  `list[RateObservation]` cho sự kiện lãi suất khớp danh mục
  `_FOREX_RATE_EVENTS` kế thừa (R4, nhãn B5; `rate` parse từ `actual` dạng
  "0.00%"→0.0; `observed_at` = `day_key`) → kết quả có kiểu
  `SourceParseOutcome(events, rates, error)`: source không chứa JSON lịch →
  error có kiểu "không tìm thấy dữ liệu lịch"; JSON hỏng/cắt cụt → error
  (all-or-nothing — không trả nửa vời); **không chuỗi hiển thị** (L3 — error
  là mã/phân loại có kiểu, câu chữ thân thiện thuộc UI). Module đồng thời
  xuất **hàm thuần phân loại dòng của lô dán** so với bản ghi hiện hữu
  (`mới` / `sẽ_cập_nhật` / `xung_đột_giữ_nhập_tay` — contract §6.1 bước 5 đợt
  4, đăng ký §11b; nhận danh sách event đã bóc + danh sách event hiện hữu,
  khớp theo `dedupe_key`, không I/O) và **hàm thuần chung thiện lô đã chỉnh
  sửa** (dòng có sửa `actual` → stamp `source=user` + giá trị actual FF gốc
  vào `raw_json`; dòng không sửa giữ `ff_html`; giá trị quan sát lãi suất
  trong danh mục đồng bộ theo actual đã sửa; `dedupe_key` BẤT BIẾN — Owner
  chốt chỉ actual được sửa, đợt 4; §6.1 bước 6, §11b).
- **Test:** ánh xạ đủ từng trường trên fixture thật (25 sự kiện 24/09/2026 —
  đối chiếu sổ tay: JPY PMI actual 54.1 revision 54.9; AU Employment 39.5K
  high impact; SNB Policy Rate 0.00% → 1 `RateObservation` CHF; sự kiện
  `holiday`→`non` nếu có trong fixture biến thể); đa ngày; actual rỗng→NULL;
  không JSON→error; JSON cắt cụt→error không ghi gì; `dedupe_key` trùng công
  thức §4.2 (so với hàm core); bóc lãi suất đúng danh mục kế thừa; **phân
  loại dòng đúng 3 nhánh** (DB rỗng→mới toàn bộ; trùng khóa→sẽ_cập_nhật; hiện
  hữu `source=user` khác actual→xung_đột_giữ_nhập_tay); **chung thiện lô đã
  sửa đúng** (dòng sửa actual→`source=user`+actual gốc trong `raw_json`;
  dòng không sửa→`ff_html`; sửa actual sự kiện lãi suất→giá trị quan sát
  theo actual đã sửa; `dedupe_key` bất biến); parser
  không import Qt/network/DB (AST ghim như khuôn `test_worker_carries_no_domain_logic`).
- **Phụ thuộc:** — (file mới thuần; giao sau F1 theo thứ tự mặc định) ·
  **Điểm review:** R8 — source thô không thoát khỏi parser (API công khai chỉ
  nhận text, chỉ trả mô hình); không bản sao `dedupe_key` (grep); danh mục
  lãi suất diff từng dòng với `interest_rate_service.py` d.29-38 (B3 mức dữ
  liệu, không "cải tiến"); cổng E2 xanh (parser không chạm verdict).
- **Trạng thái:** PLANNED

### F3 — Đường nhập 2 pha qua controller: `parse_pasted_source` + `commit_pasted_source` (M)

- **File sửa:** `controllers/news_controller.py` (+ docstring mục §6.1 đợt
  3+4), `tests/test_news_controller.py`.
- **Neo đặc tả:** contract §6.1 luồng 2 pha (đợt 4 — bước 2/5/6), §4.6
  (`producer=user`), §8 (ghi qua repository; đọc `events_in_range` cho phân
  loại dòng — **không thêm method hợp đồng mới**), §11b (`news_controller`
  tiếp nhận; phân loại dòng = hàm thuần `ff_source_parser`).
- **Nội dung:** HAI method (C3 — kết quả có kiểu, không dict trần; không
  mạng, không Qt trong controller):
  - `parse_pasted_source(source_text) -> SourcePreview`: gọi parser bóc tách
    (không tự bóc — S2); đọc sự kiện hiện hữu qua `events_in_range` (cửa sổ =
    min→max `event_time_utc` của lô dán) → gọi **hàm thuần phân loại dòng**
    của parser (mới/sẽ_cập_nhật/xung_đột_giữ_nhập_tay); trả preview có kiểu
    (events, rates, dispositions, error). **PHA 1 KHÔNG GHI DỮ LIỆU**; parse
    error → `record_run(status=failed, error_type/error_detail có kiểu)` + lỗi
    trong preview (không bảng).
  - `commit_pasted_source(preview) -> SourceIngestResult`: nhận preview **đã
    áp chỉnh sửa actual của người dùng** (typed, cờ đã-sửa từng dòng — chỉ
    actual được khác giá trị bóc, quyết định đợt 4); gọi **hàm thuần chung
    thiện lô** của parser (dòng có sửa actual → stamp `source=user` + giá trị
    actual FF gốc vào `raw_json`; dòng không sửa giữ `ff_html`; giá trị lãi
    suất trong danh mục đồng bộ theo actual đã sửa; `dedupe_key` BẤT BIẾN —
    contract §6.1 bước 6 đợt 4, §11b); sau đó `repo.upsert_events`
    + `repo.add_rate_observations` (3 quy tắc merge trong repository GIỮ
    nguyên trạng từ L2.1 — không nhân bản) + `record_run(IngestRun(producer=
    user, status=ok, items_written=tổng sự kiện + lãi suất))`; trả tóm tắt số
    **mới / cập nhật / xung đột** THẬT (từ `UpsertEventsResult` của lần ghi —
    không dùng số dự đoán của preview) + số lãi suất.
  - **Hủy = UI không gọi `commit_pasted_source`** → không ghi, không run,
    mọi chỉnh sửa bị loại bỏ (contract §6.1 bước 6 đợt 4).
- **Test:** pha 1 không ghi — DB nguyên trạng, không run `ok` mới (repo thật
  temp DB); disposition đúng 3 nhánh (DB rỗng / trùng khóa / `source=user`
  khác actual); parse error → run `failed` + preview lỗi, 0 bản ghi; pha 2 →
  ghi + run `producer=user` + `items_written` + tóm tắt đúng số; dán 2 lần
  cùng source: preview lần 2 toàn `sẽ_cập_nhật`, commit → mới=0, không row
  trùng; **commit ghi đúng actual đã sửa; dòng sửa actual → `source=user` +
  actual gốc trong `raw_json`; dòng không sửa → `ff_html`; `dedupe_key` bất
  biến; sửa actual sự kiện lãi suất → quan sát lãi suất theo giá trị đã
  sửa**; 3 quy tắc merge qua đường commit (quy tắc 2: `source=user` không bị
  đè; quy tắc 3: xung đột → ưu tiên user + log); preview/result có kiểu
  (không dict trần).
- **Phụ thuộc:** F1, F2 · **Điểm review:** grep method `parse_pasted_source`
  không có lời gọi `upsert|add_rate|record_run(status=ok)` nào (pha 1 không
  ghi — ngoại lệ duy nhất: run `failed` khi parse lỗi); disposition + chung
  thiện lô không tính trong controller (S2 — gọi hàm thuần parser); không
  method mới trong `news_repository.py` (diff file này = 0).
- **Trạng thái:** PLANNED

### F4 — UI: dialog dán mã nguồn 2 pha + panel "Sự kiện đang thiếu số liệu" (M)

- **File sửa:** `ui/screens/news_screen.py`, `tests/test_news_screen_actions.py`
  (+ smoke nếu inventory đổi).
- **Neo đặc tả:** screen_design mục "Hành vi dán mã nguồn trang ForexFactory"
  (đợt 3+4 — dialog 2 pha, bảng xem trước, nhãn trạng thái dòng, tóm tắt,
  lỗi, panel, nút mở link) + "Bố cục" (toolbar 3 nút, panel) + "Từ điển hiển
  thị" (gồm dòng nhãn preview đợt 4) + "Nguyên tắc" (không đường mạng FF từ màn).
- **Nội dung:**
  - Toolbar: **[ Dán mã nguồn trang | Nhập tin | AI nhận định xu hướng ]**.
  - **Dialog 2 pha** (khuôn dialog hiện có của màn):
    - *Pha 1:* ô text lớn dán source + nút chọn file `.html` (file dialog;
      đọc file qua worker) + hướng dẫn 3 bước đúng câu chữ screen_design +
      nút **"Bóc tách"** → chạy `controller.parse_pasted_source` trong
      **`NewsReadWorker` có sẵn** (task = callable — khuôn L3.2, không block
      GUI) + progress. Lỗi parse → thông báo nguyên nhân (chuỗi thân thiện từ
      mã lỗi có kiểu — từ điển nhãn đặt tại screen, không trong services),
      dialog giữ pha 1 để dán lại.
    - *Pha 2:* **bảng xem trước** đúng cột screen_design (Thời gian UTC |
      Đồng tiền | Sự kiện | Tác động | Dự báo | Kỳ trước | Thực tế | Trạng
      thái dòng — badge semantic, nhãn ĐÚNG TỪNG CHUỖI từ điển: "Mới" / "Sẽ
      cập nhật" / "Xung đột — giữ nhập tay" / "Đã sửa") + dòng đếm quan sát
      lãi suất. **CHỈ cột "Thực tế" (actual) sửa được** (quyết định Owner đợt
      4 — sửa khi phát hiện sai sót); mọi cột còn lại read-only (ghim bằng
      test); không checkbox/không xóa dòng. Dòng sửa actual → badge "Đã sửa"
      + phân loại lại (gọi lại hàm thuần qua controller — UI không tự phân
      loại, S2). Nút **"Cập nhật"** → `controller.commit_pasted_source
      (preview đã sửa actual)` (worker + progress) → tóm tắt
      mới/cập nhật/xung đột, đóng dialog, làm mới bảng tin + panel; nút
      **"Hủy"** → đóng dialog, KHÔNG gọi commit (loại bỏ cả chỉnh sửa, không
      ghi, không run).
  - Panel "Sự kiện đang thiếu số liệu": đọc `events_pending_actual` qua
    controller/worker (khuôn đọc bảng hiện có); mỗi dòng: sự kiện + nút "Mở
    trang ForexFactory" → `QDesktopServices.openUrl` trang lịch ngày tương ứng
    (chỉ mở link bằng trình duyệt ngoài — app không fetch, đúng §6.1); panel
    tự làm mới sau lượt dán thành công.
  - Bố cục tuân thủ style-guide (24/20px, không setStyleSheet cục bộ) +
    contract responsive 800×500 (panel không phá layout — ResponsiveRow/Grid).
- **Test (offscreen, controller giả có kiểu):** dialog mở/đóng; bấm "Bóc
  tách" → gọi đúng `parse_pasted_source`, bảng preview hiện đủ số dòng +
  đúng nhãn badge từng trạng thái; **bảng khóa mọi cột trừ "Thực tế" (assert
  read-only từng cột); sửa actual → badge dòng thành "Đã sửa" + yêu cầu phân
  loại lại qua controller giả (UI không tự phân loại)**; bấm "Cập nhật" →
  gọi đúng `commit_pasted_source` với preview **mang actual đã sửa**, hiện
  tóm tắt, panel + bảng tin được làm mới; bấm "Hủy" → KHÔNG gọi
  commit (fake đếm call = 0), chỉnh sửa bị loại bỏ; lỗi parse → thông báo đúng
  chuỗi từ điển, dialog ở pha 1; chọn file `.html` → đọc + đưa vào luồng bóc;
  panel liệt kê đúng sự kiện stale từ fake; nút mở link gọi `openUrl` đúng
  URL ngày (mock); smoke màn + `QT_QPA_PLATFORM=windows` non-offscreen xanh.
- **Phụ thuộc:** F3 · **Điểm review:** không `urlopen`/`requests`/mạng nào
  trong `news_screen.py` (grep — chỉ `openUrl`); parse + phân loại không nằm
  trong UI (R8/S2 — UI chỉ hiển thị preview có kiểu); nhãn đúng TỪNG CHUỖI
  từ điển (kể cả 3 nhãn preview đợt 4); đường "Hủy" không chạm controller
  (test đếm call); worker thật (không processEvents đồng bộ); layout 800px
  không vỡ (smoke non-offscreen).
- **Trạng thái:** PLANNED

### F5 — Nghiệm thu tổng + đồng bộ tài liệu + đóng plan (M)

- **Không code mới**; chạy nghiệm thu + sửa tài liệu + xóa plan.
- **Nội dung tuần tự (bước nào đỏ ngoài danh tính R9 → DỪNG báo BLOCKED):**
  1. Battery `python -m pytest -q --continue-on-collection-errors` — đối chiếu
     R9 (baseline tham chiếu: 5484 passed +7 skipped +16 xfailed của ca trước,
     ± số test do F1 gỡ/F2-F4 thêm — ghi rõ số liệu vào commit).
  2. Smoke: `scripts/scanner_smoke.py`, `scripts/smc_ui_smoke.py` offscreen +
     non-offscreen (`QT_QPA_PLATFORM=windows python -X utf8 …`) — EXIT=0;
     artifact trỏ temp.
  3. Build: `packaging/build_windows.ps1` (PyInstaller) exit 0, `.exe` tồn tại;
     bundle đủ migration + `news_policy.json` (không asset nào của đường FF đã
     xóa còn được spec tham chiếu — nếu spec lỗi do file bị xóa, đó là defect
     của F1, quay lại sửa đúng lô).
  4. Boot bản đóng gói (offscreen, bounded): ALIVE; `news.db` ở `%APPDATA%` đủ
     5 bảng; **không lượt `ff_crawler` mới trong `ingest_runs` sau boot** (bằng
     chứng máy đọc: app không phát request FF); thư mục cài đặt sạch.
  5. Bằng chứng grep toàn miền Tin tức: không còn `faireconomy|forexfactory.com`
     trong code sản xuất mới (ngoại lệ DUY NHẤT: URL mở trình duyệt của panel
     F4 + fixture/test của parser); không `urlopen|requests` nhắm host FF.
  6. Luồng dán source 2 pha đầu-cuối trên fixture THẬT (offscreen, script
     kiểm chứng tạm trong temp): pha 1 bóc → preview đủ 25 sự kiện + phân
     loại dòng đúng; **sửa actual 1 dòng** → dòng badge/phân loại cập nhật;
     **hủy** → DB nguyên trạng, không run mới, sửa bị loại bỏ; bóc lại + sửa
     lại → **xác nhận** → `news_events`/`interest_rates` có bản ghi (dòng
     không sửa `source=ff_html`; **dòng đã sửa `source=user` + `raw_json` giữ
     giá trị FF gốc**) + run `producer=user` + tóm tắt đúng số; dán lại lần 2
     → mới=0. Dán kết quả vào commit message.
  7. Đồng bộ tài liệu: `architecture.md` (module Tin tức: bỏ nhãn "PLANNED đợt
     3" → IMPLEMENTED; dòng `news_screen.py` cập nhật); `screen_design.md`
     (trạng thái mục News Screen đợt 3+4 PLANNED → IMPLEMENTED, ghi ngày
     nghiệm thu); `product_spec.md` §3.5 (đợt 3 PLANNED → IMPLEMENTED + câu
     quy trình 2 pha nếu Owner đã duyệt sửa — xem ghi chú Tech Lead);
     contract §16 (ghi chú ca "Nguồn dán FF" → hoàn tất + ngày);
     `docs/README.md` (bỏ dòng đăng ký plan này).
  8. **Xóa plan file này** trong chính commit nghiệm thu (D3); chụp bảng §8
     (5/5 IMPLEMENTED) vào commit message làm bằng chứng cuối.
- **Tuyên bố:** ca "Nguồn dán FF" HOÀN TẤT; trạng thái READY-FOR-CONNECT của
  miền Tin tức giữ nguyên (đấu nối a/b không đổi lộ trình); sổ nợ #1 CHƯA đóng.
- **Phụ thuộc:** tất cả · **Điểm review:** bảng §8 5/5 trước khi chạy; 7 mục
  trên đủ bằng chứng dán trong commit message; tài liệu không còn nhãn PLANNED
  đợt 3 sót (grep).
- **Trạng thái:** PLANNED

## 5. Quyết định triển khai (Tech Lead, trong khuôn contract đợt 3)

- **QĐ-F1 — Thứ tự xóa-trước-xây-sau** theo lệnh Owner 24/09/2026 ("việc đầu
  tiên phải xóa hoàn toàn"): F1 xóa trọn, F2-F4 xây kênh mới. Khoảng trống
  FF tạm thời giữa ca được chấp nhận có căn cứ (§2 — chưa có consumer
  production của `news.db`).
- **QĐ-F2 — `run_startup_turn` GIỮ, đổi phần thân:** purge + khởi động lịch
  RSS/FRED (L3.6/L3.7) không liên quan FF — giữ nguyên; chỉ gỡ phần fetch FF.
  Hook `main.py` 1 dòng QĐ-5 nhờ đó không đụng tới (không điểm chạm mới).
- **QĐ-F3 — Parser đặt tại `services/ff_source_parser.py`** (hàm thuần, không
  I/O): đúng vai "bộ chuyển đổi tại biên" của lớp `services/` (C2 — source thô
  là dữ liệu ngoài; §3 đợt 3 đã đăng ký module này trong bảng lớp).
- **QĐ-F4 — Panel thiếu số liệu dùng `QDesktopServices.openUrl`** (mở trình
  duyệt ngoài): không phải request mạng của app — nhất quán §1 ý 5 đợt 3
  ("app không phát request mạng nào tới ForexFactory") và screen_design
  ("chỉ mở link").
- **QĐ-F5 — Fixture thật do PO cấp khi giao F2** (source Owner dán 24/09/2026);
  fixture biến thể được dựng theo cấu trúc nhưng phải nhãn "constructed";
  thiếu fixture thật = BLOCKED (B5 — không bịa dữ liệu gốc).
- **QĐ-F6 — Luồng 2 pha, preview CHỈNH SỬA ĐƯỢC, xác nhận trước khi ghi
  (Owner duyệt 24/09/2026 — đợt 4, bổ sung cùng ngày: người dùng được sửa
  dữ liệu bóc tách trước khi cập nhật; contract §13 đợt 4):** pha 1 "Bóc
  tách" trả preview có kiểu + phân loại dòng (hàm THUẦN trong
  `ff_source_parser`, §11b; controller đọc hiện hữu qua `events_in_range` có
  sẵn — **không thêm method hợp đồng §8 mới**), KHÔNG ghi; người dùng **chỉ
  được sửa cột `actual` khi phát hiện sai sót** (Owner chốt 24/09/2026 — mọi
  cột còn lại read-only; dòng sửa → badge "Đã sửa", phân loại lại); pha 2
  "Cập nhật" → hàm thuần **chung thiện lô** (dòng có sửa actual →
  `source=user` + actual gốc FF vào `raw_json`; dòng không sửa → `ff_html`;
  lãi suất trong danh mục đồng bộ theo actual đã sửa, stamp giữ `ff_html` —
  enum §4.4 không có `user`; `dedupe_key` BẤT BIẾN) → ghi + run
  `producer=user` + tóm tắt số THẬT; "Hủy" = không gọi controller → không
  ghi, không run, loại bỏ chỉnh sửa. Không bỏ chọn/xóa dòng — all-or-nothing.
  Căn cứ: người dùng là chốt chặn cuối + người hiệu đính số liệu trước khi
  vào nguồn chân lý (nuôi vĩ mô/gate tại đấu nối b) — B4; giá trị sửa được
  bảo vệ vĩnh viễn bởi quy tắc merge 2-3 như nhập tay.

## 6. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| F1 là lô đại phẫu (xóa 2 file + sửa 5 file + ~6 file test) → sót tham chiếu, battery đỏ | Inventory tường minh trong lô + điểm review grep từng symbol; coder sót = review bắt được bằng lệnh grep trong §4-F1 |
| FF đổi cấu trúc `calendarComponentStates` | Một điểm chạm duy nhất (`ff_source_parser` — §11a đợt 3) + kiểm thử hợp đồng trên fixture thật (C4); fail-closed lỗi có kiểu, không ghi gì (B4). **Quy trình bảo trì (Owner duyệt 24/09/2026):** dùng AI hỗ trợ viết lại converter ở THỜI ĐIỂM SỬA (dev-time) trong một lô sửa nhỏ, kiểm chứng bằng fixture thật mới + test trước khi vào production — AI là công cụ bảo trì, **không** nằm trong luồng dữ liệu lúc chạy (§9.2: AI không tham gia bất kỳ quy trình nào) |
| Source dán rất lớn (cả tuần, hàng trăm KB) | Parser thuần xử lý trong worker nền (F4) — không block GUI; test với fixture tuần |
| Người dùng quên dán → dữ liệu `stale`, gate fail-closed chặn quét sau đấu nối | Panel hướng dẫn (F4) + `store_state` công bố degraded/unavailable (contract §6.5 — không im lặng lạc quan, B4); đã ghi chú trong contract §12 dòng Scanner |
| Xóa nhầm hành vi được giữ (AI/nhập tay/timer/purge) | Test ghim từng khối giữ-nguyên liệt kê trong F1 (lazy DI, startup-policy owner, E2, TestStartupTurn viết lại chứ không xóa bừa) |
| Fixture thật không đến tay coder | QĐ-F5: điều kiện giao lô — PO đính kèm; thiếu = BLOCKED, coder không tự bịa |

## 7. Tiêu chí nghiệm thu tổng (DoD toàn ca)

1. 5/5 lô IMPLEMENTED; battery + 3 smoke + build `.exe` + boot đóng gói xanh
   (F5), ngoại lệ theo danh tính R9.
2. Bằng chứng R1: `git diff` rỗng trên `main.py`, `app_controller.py`,
   `main_window.py`, `navigation.py` + 4 file legacy; sổ điểm chạm rỗng.
3. Không còn đường mạng FF nào trong app (grep F5 mục 5 + boot đóng gói không
   sinh lượt `ff_crawler`).
4. Kênh dán source hoạt động đầu-cuối: dán source thật → sự kiện + lãi suất
   vào `news.db` đúng `source=ff_html`, chống trùng + 3 quy tắc merge có test
   ghim; panel thiếu số liệu + dialog đúng screen_design đợt 3.
5. Tài liệu chính đồng bộ IMPLEMENTED; plan file đã xóa (D3); tuyên bố ca
   HOÀN TẤT; sổ nợ #1 chưa đóng; READY-FOR-CONNECT giữ nguyên.

## 8. Bảng trạng thái lô (Tech Lead cập nhật KÉP mỗi lô — R5)

| Lô | Nội dung | Cỡ | Phụ thuộc | Trạng thái |
|---|---|---|---|---|
| F1 | Xóa hoàn toàn đường FF tự động + xuất/nhập file (producer, file_transfer, 2 nút FF, 2 nút file, lookup seam, kênh ff_html trong fred producer) + test theo D2 | L | — | PLANNED |
| F2 | Parser `services/ff_source_parser.py` (bóc tách + hàm thuần phân loại dòng) + fixture source thật + test | M | — (giao sau F1) | PLANNED |
| F3 | Đường nhập 2 pha: `parse_pasted_source` (preview — không ghi) + `commit_pasted_source` (chung thiện lô: dòng sửa actual→`source=user`+`raw_json` actual gốc, `dedupe_key` bất biến; ghi DB + run `producer=user` + tóm tắt) | M | F1, F2 | PLANNED |
| F4 | UI: dialog dán mã nguồn 2 pha (bảng xem trước — **chỉ cột actual sửa được** + Cập nhật/Hủy) + panel "Sự kiện đang thiếu số liệu" + toolbar 3 nút | M | F3 | PLANNED |
| F5 | Nghiệm thu tổng (battery/smoke/build/boot + bằng chứng không-mạng-FF) + đồng bộ tài liệu + xóa plan | M | tất cả | PLANNED |

## Phụ lục — Kỷ luật giao lô (A3) và khuôn prompt

- **PO tự chuyển prompt sang phiên coder** — Tech Lead không relay, không làm
  thay; Tech Lead chỉ: báo cáo trạng thái, soạn prompt, nghiệm thu khi được
  yêu cầu. Chỉ coi lô xong khi Trạng thái = IMPLEMENTED + DoD đạt; BLOCKED →
  báo Owner, không tự quyết.
- Khuôn prompt 6 mục như ca trước (plan `news-data-layer-plan.md` — Phụ lục,
  lịch sử trong Git tại commit cha của 212fc41): [1] Đọc trước khi viết (mục
  lô + §3 + contract/screen_design mục neo + code khuôn CHỈ ĐỌC); [2] Sản phẩm
  bàn giao (đúng danh sách file lô + danh sách CẤM); [3] Hành vi đối chiếu
  từng gạch "Nội dung" (cấm hành vi không điều khoản V2, cấm bịa số B5);
  [4] Test phải viết; [5] DoD — bằng chứng máy đọc: battery theo danh tính
  R9, `git diff --stat HEAD~1`, một commit D2 + E1 4 câu + `Co-Authored-By:
  Claude Code <noreply@anthropic.com>`, cập nhật KÉP §8 + mục lô, temp không
  rác; [6] Kỷ luật dừng (thiếu điều khoản/buộc sửa file ngoài danh sách →
  DỪNG báo BLOCKED kèm vị trí; không làm trước việc lô sau).
- Biến thể lô F1 (lô xóa): thêm "sau khi xóa, chạy grep điểm review của lô và
  dán kết quả rỗng vào báo cáo; test của hành vi BỊ XÓA được gỡ cùng commit
  (D2), test của hành vi GIỮ phải xanh nguyên trạng — liệt kê từng nhóm".
- Biến thể lô F4 (lô UI): thêm "chạy smoke non-offscreen
  `QT_QPA_PLATFORM=windows python -X utf8 scripts/smc_ui_smoke.py`; nhãn hiển
  thị đúng TỪNG CHUỖI từ điển screen_design — không tự đặt nhãn".
