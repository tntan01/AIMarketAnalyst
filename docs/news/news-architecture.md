# Kiến trúc Tin tức — Contract tầng dữ liệu

> **Trạng thái: BAN HÀNH — Owner duyệt ngày 20/09/2026 (V1). Sửa đổi đợt 3 —
> Owner duyệt 24/09/2026:** ForexFactory chuyển sang kênh **dán mã nguồn trang
> (page source) do người dùng cung cấp** — bỏ mọi đường thu tự động của FF;
> **bỏ xuất/nhập file CSV-JSON**; RSS và FRED giữ tự động định kỳ (§6.1, §10,
> §13 đợt 3). Tài liệu này
> là đặc tả thẩm quyền **duy nhất** của miền Tin tức (V2): code phải đúng từng
> hành vi mô tả ở đây; lệch tài liệu ↔ code = defect phải đóng. Toàn bộ giá
> trị chính sách đã được Owner chốt (mục 7, 13) — không còn điểm `OPEN`.
> Phạm vi: **tầng dữ liệu tin tức** — database, bộ sản xuất (producer), kho
> truy cập (repository), mô hình miền, chính sách, contract nhận định xu hướng
> của AI. **Không** đặc tả hiển thị Dashboard, công thức chấm điểm vĩ mô hay
> bố cục màn hình — các nội dung đó thuộc tài liệu của miền tương ứng, viết
> sau khi phần Tin tức hoàn thành (mục 12).
>
> Căn cứ: quyết định Owner ngày 20/09/2026 — (1) "đập đi – xây mới" lớp tin
> tức, không giữ tương thích code cũ, không tên phiên bản (V3); ngoại lệ của
> B6 **đã ghi vào Phụ lục B** `architecture-rules.md` (E3, 20/09/2026);
> (2) database là nguồn chân lý duy nhất; (3) AI nhận định xu hướng **chỉ để
> người dùng tham khảo, không tham gia bất cứ quy trình nào**; (4) ForexFactory
> — **từ 24/09/2026 (đợt 3): không thu tự động dưới mọi hình thức**, lịch kinh
> tế + actual đến từ mã nguồn trang người dùng dán; RSS và FRED giữ tự động
> định kỳ (các quyết định bổ sung: mục 6.1 và 13).

---

## 1. Ý định Owner (nguồn gốc đặc tả)

1. Database tin tức (SQLite) là **nguồn chân lý duy nhất**: bộ sản xuất chỉ
   GHI, bên tiêu thụ chỉ ĐỌC; không bên tiêu thụ nào gọi thẳng ra nguồn ngoài.
2. Tin văn bản thu tự động từ RSS (headline/phát biểu); lãi suất thu tự động
   từ FRED; **lịch kinh tế + actual ForexFactory đến từ mã nguồn trang người
   dùng dán** (không tự động — đợt 3, 24/09/2026); người dùng có thể nhập tay
   tin bổ sung; dữ liệu được cập nhật vào database theo từng ngày.
3. Database phục vụ hai bên tiêu thụ chính: **tin tức trên Dashboard** và
   **chấm điểm vĩ mô/macro gate** (đặc tả từng bên nằm ở tài liệu miền tương
   ứng — mục 12), cộng với màn **Quản lý tin** (xem/nhập tay/dán mã nguồn
   trang).
4. Màn Quản lý tin có cửa sổ nhỏ gọi **AI nhận định xu hướng ngắn hạn/trung
   hạn/dài hạn** của cặp tiền — kết quả **chỉ tư vấn cho người dùng**, không
   là đầu vào của scoring, gate, guard thực thi hay alert (quyết định chốt
   20/09/2026).
5. Riêng ForexFactory: **không thu tự động dưới bất kỳ hình thức nào** —
   không lượt khởi động, không nút fetch, không thăm dò (poll), không lookup;
   hệ thống **không phát request mạng nào tới ForexFactory**. Lịch kinh tế và
   actual được bóc tách từ **mã nguồn trang (page source) người dùng dán** qua
   màn Quản lý tin (Owner quyết 24/09/2026, đợt 3 — chi tiết mục 6.1, 13).
   RSS và FRED **giữ tự động định kỳ** như thiết kế.

## 2. Từ vựng miền (S5 — định nghĩa một lần, dùng nhất quán)

| Thuật ngữ | Định nghĩa |
|---|---|
| Sự kiện lịch kinh tế (calendar event) | Một tin có lịch công bố trước từ ForexFactory: giờ, đồng tiền, tên, mức tác động, dự báo/kỳ trước/thực tế |
| Tin văn bản (news item) | Headline, phát biểu chính thức hoặc ghi chú nhập tay — có giờ đăng, tiêu đề, nội dung/tóm tắt, đồng tiền liên quan |
| Quan sát lãi suất (rate observation) | Một lần ghi nhận lãi suất điều hành của một đồng tiền, kèm nguồn và ngày quan sát |
| Nhận định xu hướng (trend verdict) | Kết quả AI đánh giá xu hướng một cặp tiền/đồng tiền theo một chân trời thời gian (horizon) |
| Bộ sản xuất (producer) | Mô-đun duy nhất được phép GHI một loại tín hiệu vào database (S6) |
| Bên tiêu thụ (consumer) | Mô-đun chỉ ĐỌC database qua giao diện kho truy cập |
| Kho tin tức (`NewsRepository`) | Điểm truy cập database duy nhất (đọc + ghi) của miền |
| Trạng thái sự kiện | `scheduled` (chưa tới giờ) — `released` (đã có số liệu thực tế) — `stale` (đã qua giờ công bố + ân hạn mà chưa có số liệu thực tế) |
| Loại trừ (`excluded`) | Cờ do người dùng đặt để tin tự động không được tính trong dữ liệu phục vụ vĩ mô; không xóa vật lý |
| Mã nguồn trang (page source) | Toàn bộ văn bản HTML của một trang lịch ForexFactory do người dùng sao chép/lưu từ trình duyệt của chính mình — đầu vào duy nhất của kênh cập nhật lịch kinh tế + actual (§6.1) |
| Lượt ingest (ingest run) | Một lần chạy của một bộ sản xuất hoặc một lượt dán mã nguồn (ghi `producer=user`), có kết quả và số bản ghi đã ghi |
| Ân hạn (grace) | Khoảng chờ sau giờ sự kiện trước khi đánh dấu `stale` |

Nhãn trạng thái/loại/nguồn là **enum máy đọc** — chuỗi đóng băng, không đổi
giá trị đã persist (V3(a)). Từ điển hiển thị tiếng Việt thuộc tầng trình bày,
đăng ký trong tài liệu UI tương ứng.

## 3. Kiến trúc tổng thể và phân lớp (L1)

```text
BÊN GHI (chỉ GHI)                             DATABASE                      BÊN TIÊU THỤ (chỉ ĐỌC)
───────────────                               ────────                      ─────────────────────
Người dùng dán mã nguồn trang FF        ───►  news_events              ───►  Dashboard (đặc tả: screen_design.md — viết sau)
 (qua NewsController                          news_items               ───►  Chấm điểm vĩ mô/gate (đặc tả: macro_score_architecture.md — viết sau)
  + services/ff_source_parser.py)       ───►  interest_rates           ───►  Màn Quản lý tin (xem/nhập tay/dán mã nguồn)
rss_producer (Google News, FXStreet,          ai_trend_verdicts        ───►  Cửa sổ AI nhận định xu hướng (đọc lịch sử verdict)
 Investing)                             ───►  ingest_runs
fred_rate_producer (FRED API + config fallback)
Người dùng nhập tay (form, qua NewsController)

Mọi đọc/ghi đi qua NewsRepository — điểm truy cập database duy nhất (S1).
App KHÔNG phát request mạng nào tới ForexFactory (§6.1 — Owner quyết đợt 3).
```

Chiều phụ thuộc bắt buộc:

```text
ui → controllers → core ← services (repository, producer, parser)
```

| Lớp | Mô-đun của miền này | Vai trò |
|---|---|---|
| `services/` | `news_repository.py`; `ff_source_parser.py`; `news_producers/rss_producer.py`; `news_producers/fred_rate_producer.py` | Vào/ra + tầng chống ăn mòn (C2): biên dịch dữ liệu thô nguồn ngoài (XML RSS, JSON feed FRED, **mã nguồn trang FF người dùng dán**) → mô hình miền có tên ngay tại biên; dữ liệu thô không tồn tại ngoài bộ chuyển đổi |
| `core/` | `news_policy.py`; `news_models.py`; `news_freshness.py`; `rate_trend.py`; `trend_prompt_builder.py`; `trend_verdict_parser.py` | Logic thuần: nạp và xác thực chính sách miền, mô hình miền, phân loại trạng thái dữ liệu, dẫn xuất trend lãi suất, dựng prompt, parse verdict. Không vào/ra, không chuỗi hiển thị (L2, L3). Mô hình miền **bắt buộc đặt trong `core/`** vì L1 cấm `Core → Services` (hàm thuần `core/` nhận mô hình làm tham số) |
| `controllers/` | `news_controller.py` | Điều phối: lên lịch producer, phục vụ truy vấn cho bên tiêu thụ, tiếp nhận nhập tay **và mã nguồn trang FF dán** (giao parser, ghi qua repository), điều phối gọi AI trong worker |
| `workers/` | worker nền cho producer poll + lời gọi AI | Bao bọc concurrency, không logic nghiệp vụ |
| `ui/` | màn Quản lý tin, mục tin Dashboard | Chỉ hiển thị dữ liệu miền đã định dạng (đặc tả ở tài liệu UI — ngoài phạm vi tài liệu này) |

**Cấm:** bên tiêu thụ tự suy diễn lại tín hiệu từ dữ liệu thô (S2); công thức
chấm điểm nằm trong `services/` ; hai nơi cùng sản xuất một loại tín hiệu (S6).

### 3.1. Nguyên tắc triển khai ca — xây song song, đấu nối sau (B7)

Áp dụng quy tắc B7 của `architecture-rules.md` (Owner ban hành 20/09/2026)
cho ca Tin tức:

1. **Chỉ tạo file mới.** Toàn bộ module mục 3 là file mới độc lập. Trong suốt
   quá trình phát triển: **không sửa** `services/news_service.py`,
   `services/forex_factory_client.py`, `services/interest_rate_service.py`
   (QĐ-1 phương án A — Owner duyệt 21/09/2026), mục tin tức trên Dashboard,
   chấm điểm vĩ mô/MacroGate và mọi code tiêu thụ tin hiện hành — các đường
   này giữ nguyên hành vi runtime 100%.
2. **Không dùng chung đường dữ liệu khi song song:** hệ mới chỉ ghi
   `news.db`; hệ cũ giữ cache đĩa của nó. Không bên nào đọc/ghi đường của bên
   kia.
3. **Hoàn thiện mới đấu nối.** Tính năng Tin tức (database + producer RSS/FRED
   + kênh dán mã nguồn trang FF + nhập tay + màn Quản lý tin + cửa sổ AI nhận
   định) phải hoàn
   thiện và nghiệm thu đạt theo tài liệu này, khi đó mới đấu nối lần lượt:
   **(a) Dashboard** chuyển mục tin sang đọc `news.db` (đặc tả trong
   `screen_design.md`, viết ở ca đấu nối); **(b) vĩ mô** chuyển sang đọc qua
   `NewsRepository` (đặc tả trong `macro_score_architecture.md` + tài liệu
   Scanner, viết ở ca đấu nối).
4. **Xóa code cũ theo từng đấu nối, cùng commit (D2):** đấu nối (a) xóa
   đường fetch headline/dashboard cũ; đấu nối (b) xóa `news_service.py` +
   `forex_factory_client.py` (đóng sổ nợ #1, hết hiệu lực ngoại lệ E3) và
   cache đĩa tin tức. Kiểm thử đặc trưng B3 ghim đầu ra vĩ mô **trước** khi
   xóa, đối chiếu tương đương sau đấu nối.

## 4. Database

### 4.1. Vị trí và hạ tầng

- File riêng: `%APPDATA%/ai-market-analyst/news.db`, đường dẫn qua helper
  `config/paths.py` (bản đóng gói không ghi vào thư mục cài đặt).
- Schema thay đổi **chỉ bằng migration versioned** trong `data/migrations/`.
- WAL; mỗi thread một connection; truy vấn đọc từ GUI thread phải có index và
  giới hạn số dòng (không block).

### 4.2. Bảng `news_events` — sự kiện lịch kinh tế

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | INTEGER PK | |
| `day_key` | TEXT | `YYYY-MM-DD` (UTC) của sự kiện — khóa truy cập theo ngày |
| `event_time_utc` | TEXT ISO-8601 | |
| `currency` | TEXT | |
| `title` | TEXT | tên sự kiện đã chuẩn hóa |
| `impact` | TEXT enum | `high` \| `medium` \| `low` \| `non` |
| `forecast` / `previous` / `actual` | TEXT NULL | `actual` NULL khi chưa công bố |
| `actual_updated_at` | TEXT NULL | thời điểm actual được ghi |
| `status` | TEXT enum | `scheduled` \| `released` \| `stale` |
| `source` | TEXT enum | `ff_json` \| `ff_html` \| `user` \| `import` — chuỗi đóng băng (V3(a)). **Ngữ nghĩa từ đợt 3-4 (24/09/2026):** `ff_html` = bóc từ mã nguồn trang FF người dùng dán (kênh FF chính thức duy nhất); `user` = nhập tay, **gồm cả dòng sự kiện người dùng đã chỉnh sửa trong luồng dán (đợt 4 — giá trị FF gốc giữ trong `raw_json`)**; `ff_json`, `import` = giá trị lịch sử của dữ liệu cũ, không phát sinh thêm |
| `dedupe_key` | TEXT UNIQUE | hash(`event_time_utc` + `currency` + `title`) — upsert (ghi đè nếu đã tồn tại, chèn nếu chưa) không trùng |
| `raw_json` | TEXT NULL | JSON sự kiện đã trích (provenance/self-heal) — đường dán mã nguồn lưu phần trích từng sự kiện (kèm `revision`/`notice`), không lưu cả trang |
| `fetched_at` | TEXT | lượt gần nhất (fetch tự động cũ hoặc dán mã nguồn) chạm bản ghi |

Index: `(day_key)`, `(event_time_utc)`, `(currency, event_time_utc)`, index
một phần `(status='stale')`.

### 4.3. Bảng `news_items` — tin văn bản

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | INTEGER PK | |
| `kind` | TEXT enum | `headline` \| `statement` \| `user_note` |
| `source` | TEXT enum | `google_news_rss` \| `fxstreet_rss` \| `investing_rss` \| `user` \| `import` |
| `title` | TEXT | |
| `content` | TEXT NULL | bắt buộc với `user_note` |
| `url` | TEXT NULL | |
| `published_utc` | TEXT | tin nhập tay bắt buộc có giờ đăng (để tính cửa sổ thời gian) |
| `currencies_json` | TEXT | vd `["USD","JPY"]` |
| `impact_hint` | TEXT NULL | `high`\|`medium`\|`low` — chỉ `user_note` |
| `speaker_role` | TEXT NULL | chỉ `statement` (vd `Fed official`, `JP PM`) |
| `excluded` | INTEGER 0/1 | người dùng loại khỏi dữ liệu phục vụ vĩ mô |
| `dedupe_key` | TEXT UNIQUE | hash(url hoặc title + published_utc) |
| `fetched_at` | TEXT | |

Index: `(kind, published_utc)`, `(published_utc)`.

### 4.4. Bảng `interest_rates` — quan sát lãi suất

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | INTEGER PK | |
| `currency` | TEXT | 8 tiền tệ theo phạm vi `interest_rate_service` hiện hành |
| `rate` | REAL | %/năm |
| `observed_at` | TEXT | ngày quan sát của số liệu |
| `source` | TEXT enum | `fred` \| `ff_html` \| `config_fallback` — từ đợt 3 (24/09/2026): `ff_html` phát sinh **duy nhất** từ đường dán mã nguồn trang (§6.1 bước 4; kênh mạng FF-HTML cũ trong producer bị gỡ) |
| `fetched_at` | TEXT | |
| UNIQUE | | `(currency, observed_at, source)` |

Trend (hike/cut/hold) **không lưu** — dẫn xuất lúc đọc từ hai quan sát gần
nhất. Chủ sở hữu phép dẫn xuất là **`core/rate_trend.py`** (hàm thuần
`derive_rate_trend`; danh tính M5: "Sở hữu tri thức dẫn xuất trend lãi suất
hike/cut/hold từ hai quan sát gần nhất" — logic hiện hành của
`interest_rate_service` chuyển về core); `interest_rate_service`
và `NewsRepository` chỉ gọi hàm này, không tự tính (L1 — tính toán thuộc
`core/`, `services/` cấm chứa công thức).

### 4.5. Bảng `ai_trend_verdicts` — nhận định xu hướng của AI

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | INTEGER PK | |
| `created_at` | TEXT | |
| `scope_type` | TEXT enum | `pair` \| `currency` |
| `scope_value` | TEXT | vd `EUR/USD` hoặc `JPY` |
| `horizon` | TEXT enum | `short` \| `mid` \| `long` — mỗi chân trời một dòng |
| `direction` | TEXT enum | `bullish` \| `bearish` \| `neutral` \| `insufficient_data` |
| `confidence` | TEXT enum | `high` \| `medium` \| `low` \| `none` |
| `rationale` | TEXT | lập luận tiếng Việt |
| `evidence_item_ids_json` | TEXT | id sự kiện/tin được dẫn chứng |
| `input_snapshot_json` | TEXT | cửa sổ thời gian + số tin/sự kiện đưa vào prompt |
| `provider` / `model` | TEXT | provenance nhà cung cấp AI |
| `prompt_hash` | TEXT | hash khuôn prompt — hằng truy vết provenance, ngoại lệ V3(a) |

### 4.6. Bảng `ingest_runs` — log vận hành bộ sản xuất

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | INTEGER PK | |
| `producer` | TEXT enum | `ff_crawler` \| `rss` \| `fred` \| `user` \| `on_demand_lookup` — chuỗi đóng băng (V3(a)); từ đợt 3 (24/09/2026): `ff_crawler`, `on_demand_lookup` là giá trị lịch sử, không phát sinh thêm; **lượt dán mã nguồn trang ghi `user`** |
| `started_at` / `finished_at` | TEXT | |
| `status` | TEXT enum | `ok` \| `partial` \| `failed` |
| `items_written` | INTEGER | số bản ghi upsert |
| `error_type` / `error_detail` | TEXT NULL | phân loại lỗi có kiểu (vd `InvalidRSSStructure` của RSS; đường dán mã nguồn: lỗi không tìm thấy JSON lịch trong source — tên mã cụ thể đăng ký tại lô triển khai) |

**Retention (Owner chốt 20/09/2026):** giá trị vận hành nằm ở khóa
`ingest_runs_retention_days` của tệp chính sách (mục 7); dọn tự động khi
khởi động app. Chỉ áp cho log vận hành; tin tức và verdict không bị xóa.

## 5. Mô hình miền có kiểu (C2, C3)

Toàn bộ mô hình miền của miền Tin tức khai báo tại **`core/news_models.py`**
(chủ sở hữu duy nhất, đăng ký tại mục 11b). Dữ liệu qua ranh giới mô-đun là
dataclass tường minh, **không dùng dict không kiểu**:

| Mô hình | Ánh xạ bảng | Trường chính |
|---|---|---|
| `CalendarEvent` | `news_events` | thời gian, currency, title, impact, forecast/previous/actual, status, source, dedupe_key |
| `NewsItem` | `news_items` | kind, source, title, content, url, published_utc, currencies, impact_hint, speaker_role, excluded |
| `RateObservation` | `interest_rates` | currency, rate, observed_at, source |
| `TrendVerdict` | `ai_trend_verdicts` | scope, horizon, direction, confidence, rationale, evidence ids, snapshot, provider/model, prompt_hash |
| `IngestRun` | `ingest_runs` | producer, mốc thời gian, status, items_written, lỗi |
| `StoreState` | — (dẫn xuất từ `ingest_runs` + `news_freshness`) | trạng thái `fresh`/`degraded`/`unavailable` từng tín hiệu (`events`, `items`, `rates`) + giờ ingest thành công cuối |

Bộ chuyển đổi nguồn (trong từng producer và trong `ff_source_parser.py`) là
nơi **duy nhất** nhìn thấy dữ liệu thô (JSON feed FRED, XML RSS, **mã nguồn
trang FF người dùng dán**); ra khỏi biên chỉ có mô hình miền. Đổi nhà cung
cấp/khuôn dạng nguồn = thay bộ chuyển đổi, giữ nguyên mô hình (C2).

## 6. Bộ sản xuất — sổ đăng ký tín hiệu (S6: mỗi tín hiệu một chủ sở hữu)

| Tín hiệu | Bộ sản xuất duy nhất | Danh tính mô-đun (M5 — một câu không "và") |
|---|---|---|
| Sự kiện lịch kinh tế + actual (ForexFactory) | đường dán mã nguồn: `news_controller` (tiếp nhận) + `services/ff_source_parser.py` (bóc tách) | Parser: Sở hữu tri thức chuyển mã nguồn trang ForexFactory thành mô hình miền có kiểu |
| Headline + phát biểu chính thức | `rss_producer` | Sở hữu tri thức thu thập tin văn bản công khai thành `NewsItem` |
| Quan sát lãi suất | `fred_rate_producer` (FRED) | Sở hữu tri thức thu thập lãi suất điều hành 8 đồng tiền thành `RateObservation` |
| Ghi chú nhập tay | `news_controller` (đường nhập tay) | Sở hữu tri thức tiếp nhận và xác thực tin người dùng nhập |
| Nhận định xu hướng AI | `news_controller` (đường AI, ghi qua repository) | Sở hữu điều phối lời gọi AI; thẩm quyền nội dung verdict thuộc parser (mục 9) |

### 6.1. ForexFactory — kênh dán mã nguồn trang (không mạng)

**Quyết định Owner đợt 3 (24/09/2026):** BỎ toàn bộ thu tự động từ
ForexFactory (4 lượt thu cũ: lượt khởi động, nút "Lấy lịch kinh tế", nút
"Cập nhật actual", on-demand lookup) và BỎ xuất/nhập file CSV-JSON (mục 10).
Kênh **duy nhất** của lịch kinh tế + actual là **mã nguồn trang (page source)
người dùng dán** — hệ thống **không phát bất kỳ request mạng nào tới
ForexFactory**.

Căn cứ (điều tra 24/09/2026 — bằng chứng trong lịch sử Git/memory dự án): cả
ba kênh tự động đều chết hoặc bất ổn với client không-phải-browser —
(1) JSON feed `nfs.faireconomy.media`: `ff_calendar_nextweek.json` bị gỡ khỏi
CDN (404 vĩnh viễn), `thisweek` bị giới hạn tần suất theo IP rất hẹp (429 tái
diễn, retry khuếch đại); (2) HTML `forexfactory.com`: Cloudflare chặn theo
TLS fingerprint — Python/curl không bắt tay được (handshake timeout);
(3) WebSocket feed nội bộ (`calendar-feed.forexfactory.com:2087`): Cloudflare
managed challenge từ chối client không-phải-browser (403 `cf-mitigated:
challenge`). Trình duyệt người dùng luôn qua được (fingerprint thật + tự giải
challenge) — người dùng trở thành kênh vận chuyển, hệ thống giữ phần bóc tách.

**Luồng 2 pha (hành vi đặc tả — Owner duyệt đợt 4, 24/09/2026: người dùng
xác nhận trước khi ghi):**

*Pha 1 — bóc tách và xem trước (không ghi dữ liệu):*

1. Người dùng mở một trang lịch ForexFactory bất kỳ bằng trình duyệt của mình
   (trang chủ hôm nay, `/calendar?day=...`, `/calendar?week=this|next`), sao
   chép toàn bộ mã nguồn trang, dán vào dialog "Dán mã nguồn" của màn Quản lý
   tin (hoặc chọn file `.html` đã lưu) → bấm **"Bóc tách"**.
2. `NewsController` tiếp nhận văn bản source (không tự bóc tách — S2), gọi
   chủ sở hữu duy nhất: `services/ff_source_parser.py`.
3. Parser trích khối JSON nhúng `window.calendarComponentStates[...]` trong
   source (cấu trúc dữ liệu chính frontend FF dùng để render lịch) → chuẩn
   hóa thành `CalendarEvent`:
   - `dateline` (Unix epoch, chuẩn UTC) → `event_time_utc` + `day_key` — không
     suy đoán timezone;
   - `prefixedName` → `title`; `currency` giữ nguyên;
   - `impactName` (`high`/`medium`/`low`/`holiday`) → enum `impact` của §4.2
     (`holiday` → `non`);
   - `forecast`/`previous`/`actual`: chuỗi rỗng → NULL;
   - các trường bổ sung (`revision`, `notice`, `ebaseId`, `soloUrl`) đưa vào
     `raw_json` của sự kiện (provenance từng sự kiện — không lưu cả trang);
   - stamp `source=ff_html` (giá trị enum đóng băng §4.2 — ngữ nghĩa "từ mã
     nguồn trang FF"); `dedupe_key` theo công thức §4.2 (chủ sở hữu duy nhất
     `core/news_models.py` — cấm bản sao công thức).
4. Parser đồng thời bóc **sự kiện lãi suất** có trong source (tên sự kiện
   khớp danh mục lãi suất điều hành của 8 tiền tệ) thành `RateObservation`
   (`source=ff_html`, `observed_at` = ngày sự kiện, `rate` parse từ `actual`) —
   kênh lãi suất `ff_html` (§4.4) sống lại qua đường dán. Danh mục sự kiện bóc
   **kế thừa `_FOREX_RATE_EVENTS` hiện hành** của `interest_rate_service.py`
   (bằng chứng: runtime hiện hành — không bịa danh mục mới, B5).
5. **Bảng xem trước (preview):** màn hình hiển thị dữ liệu đã bóc tách dạng
   bảng — thời gian (UTC), đồng tiền, sự kiện, tác động, dự báo, kỳ trước,
   **thực tế (actual lấy từ chính source)** — kèm **trạng thái từng dòng**
   đối chiếu database theo `dedupe_key` (chỉ đọc): `Mới` / `Sẽ cập nhật` /
   `Xung đột — giữ nhập tay` (bản ghi hiện hữu `source=user` khác actual).
   **Người dùng chỉ được chỉnh sửa cột `actual` khi phát hiện sai sót** (đợt
   4 — quyết định Owner: các cột còn lại thời gian/đồng tiền/sự kiện/tác
   động/dự báo/kỳ trước **read-only**; không bỏ chọn/xóa dòng); dòng đã sửa
   hiển thị trạng thái `Đã sửa`, phân loại dòng được tính lại sau khi sửa.
   **Chưa ghi gì vào database ở pha này.**

*Pha 2 — xác nhận ghi:*

6. Người dùng bấm **"Cập nhật"** → controller ghi qua repository **giá trị
   sau chỉnh sửa actual**: `upsert_events` + `add_rate_observations`
   (chống trùng tuyệt đối nhờ `dedupe_key` UNIQUE — **bất biến** vì chỉ
   `actual` được sửa — + **3 quy tắc merge an toàn** bên dưới) và
   `record_run` (`producer=user`; `items_written` = tổng bản ghi sự kiện +
   lãi suất đã ghi) → màn hình hiện tóm tắt số bản ghi **mới / cập nhật /
   xung đột**. Bấm **"Hủy"** → **không ghi gì, không sinh lượt ingest**
   (preview là dữ liệu có kiểu, hủy = loại bỏ cùng mọi chỉnh sửa).
   "Cập nhật" ghi toàn bộ lô (all-or-nothing). **Provenance của chỉnh sửa
   (đợt 4):** dòng sự kiện có `actual` người dùng đã sửa → ghi `source=user`
   (được quy tắc merge 2 bảo vệ bất khả xâm phạm trước các lượt dán sau; quy
   tắc 3 coi là phía nhập tay khi xung đột), **giá trị actual FF gốc trước
   sửa được giữ trong `raw_json`**; dòng không sửa giữ `source=ff_html`.
   Quan sát lãi suất bóc từ source dán giữ `source=ff_html` (§4.4 enum không
   có giá trị `user` — đóng băng, không thêm), **giá trị đồng bộ theo actual
   đã sửa** nếu sự kiện gốc thuộc danh mục lãi suất và bị sửa actual.

**Trang parser đọc được:** mọi source có chứa `calendarComponentStates` —
parser đọc **toàn bộ các ngày** trong `days[]`, không giới hạn loại trang;
dán được trang ngày quá khứ để bù dữ liệu (thay thế điều khoản "Tuần trước:
KHÔNG thu" cũ — điều khoản đó bãi bỏ cùng kênh JSON feed).

**Quy tắc merge khi upsert (3 quy tắc an toàn — giữ nguyên văn 20/09/2026):**

1. **Không ghi đè giá trị thật bằng NULL** — `actual` chỉ được ghi khi dữ liệu
   mới có giá trị; source chưa có actual thì actual đã có được giữ nguyên.
2. **Bảo vệ dữ liệu nhập tay** — bản ghi `source=user` không bị lượt dán đè;
   chỉ người dùng được sửa.
3. **Xung đột actual** (giá trị nhập tay khác giá trị trong source dán) → ưu
   tiên nhập tay, ghi nhận xung đột vào `ingest_runs`.

**Dán trùng (source đã có trong DB):** `dedupe_key` không tạo row trùng —
bảng xem trước hiển thị các dòng trạng thái `Sẽ cập nhật`; khi xác nhận, bản
ghi khớp khóa được **cập nhật** theo 3 quy tắc merge; tóm tắt phản ánh đúng
số mới/cập nhật/xung đột để người dùng biết điều gì đã xảy ra.

**Lỗi (fail-closed, B4):** source không chứa JSON lịch → lỗi có kiểu "không
tìm thấy dữ liệu lịch kinh tế trong mã nguồn" hiển thị ngay ở pha 1, **không
ghi dữ liệu**, ghi run `failed`; source cắt cụt/JSON hỏng → báo lỗi rõ nguyên
nhân, không ghi nửa vời (một lô bóc tách là all-or-nothing). Không có mạng
⇒ không retry, không 429, không điều khoản chống lạm dụng nguồn.

### 6.2. `rss_producer`

Kế thừa tập query Google News RSS hiện hành (headline rộng + phát biểu:
Trump/Fed/PM Nhật/PM Anh/EU) và feed phụ FXStreet/Investing. Thăm dò (poll)
theo khóa `rss_poll_interval_minutes`; cửa sổ thu theo khóa `rss_window_hours`
(kế thừa giá trị đang chạy — bằng chứng: runtime hiện hành); dedupe theo
`dedupe_key`.

### 6.3. `fred_rate_producer` (QĐ-1 phương án A — Owner duyệt 21/09/2026)

File mới `services/news_producers/fred_rate_producer.py`, hấp thụ logic FRED
hiện hành của `interest_rate_service.py`: copy logic sang file mới, **không
sửa file cũ**. Giữ tần suất hiện hành (khóa `fred_refresh_hours`); đích ghi là
bảng `interest_rates`. Chuỗi nguồn: FRED API → fallback
`config/interest_rates.json` ghi `source=config_fallback`. **Từ đợt 3
(24/09/2026):** kênh FF-HTML lãi suất qua mạng trong producer (khuôn
`_update_from_forexfactory` kế thừa) bị **gỡ** — kênh đó chết vì Cloudflare
chặn client không-phải-browser (§6.1 căn cứ); quan sát `source=ff_html` từ nay
phát sinh duy nhất qua đường dán mã nguồn (§6.1 bước 4). Dẫn xuất trend
(hike/cut/hold) không nằm trong producer — gọi `core/rate_trend.py` (§4.4).
Trong thời gian song song, hai hệ fetch FRED độc lập (B7 — đường cache cũ
nuôi vĩ mô di sản giữ nguyên 100%); `interest_rate_service.py` bị xóa tại
đấu nối (b) vĩ mô (mục 12).

### 6.4. Nhập tay

Qua form màn Quản lý tin → `NewsController` xác thực (bắt buộc: giờ đăng,
loại tin, nội dung, đồng tiền) → repository ghi `NewsItem(kind=user_note,
source=user)`. Quyền sửa/xóa: chỉ `user_note`; tin tự động chỉ được đặt
`excluded=1` (giữ provenance).

### 6.5. Quy tắc trạng thái dữ liệu — `core/news_freshness.py` (thuần)

Chủ sở hữu **duy nhất** của phép phân loại trạng thái (S1, L3 — trả enum,
không sinh chuỗi hiển thị):

- `classify_event_status(event, now, grace)` → `scheduled` \| `released` \|
  `stale`: sự kiện `impact != non` đã qua `event_time_utc + grace`
  (`event_stale_grace_minutes`) mà `actual NULL` → `stale`; có actual →
  `released`.
- `classify_store_state(last_success_by_producer, now, max_age)` →
  `fresh` \| `degraded` \| `unavailable` cho từng loại tín hiệu: không có lượt
  ingest `ok`/`partial` trong `ingest_freshness_hours` → `degraded`; chưa từng
  có → `unavailable`. Án lệ: `MacroMarketCache` (Phụ lục C — không im lặng lạc
  quan, B4).
- Producer ghi `status` lúc upsert; `NewsRepository` trả kèm `store_state` khi
  bên tiêu thụ truy vấn. **Hệ quả chấm điểm/gate từ các trạng thái này do tài
  liệu miền vĩ mô quy định** (mục 12) — tài liệu này chỉ sở hữu việc phân
  loại và công bố trạng thái.

## 7. Chính sách có phiên bản (S4, B5, D5)

Mọi con số vận hành của miền nằm trong **một** tệp chính sách
`config/news_policy.json` (object có khóa `policy_version` — chuỗi provenance
máy đọc, V3(a)). Tài liệu này trỏ về khóa, **không chép giá trị** (D5):

| Khóa | Ý nghĩa | Giá trị Owner chốt (20/09/2026) |
|---|---|---|
| `rss_poll_interval_minutes` | chu kỳ thăm dò (poll) tin văn bản | **15** |
| `rss_window_hours` | cửa sổ thu tin văn bản mỗi lượt | **24** (kế thừa runtime hiện hành — bằng chứng: đang chạy) |
| `fred_refresh_hours` | chu kỳ fetch lãi suất | giữ giá trị hiện hành của `interest_rate_service` (bằng chứng: đang chạy) |
| `event_stale_grace_minutes` | ân hạn trước khi `stale` | **15** |
| `ingest_freshness_hours` | tuổi tối đa lượt ingest thành công trước khi `degraded` | **2** |
| `ingest_runs_retention_days` | retention log vận hành | **30** |
| `ai_window_days` | cửa sổ tin đưa vào prompt AI | **7** |
| `ai_min_items` | số tin tối thiểu để được gọi AI | **3** |
| `ai_horizons` | định nghĩa 3 chân trời (short/mid/long) | **ngắn: trong ngày–3 ngày; trung: 1–4 tuần; dài: 1–6 tháng** |

**ForexFactory không có khóa chính sách nào** — từ đợt 3 (24/09/2026): không
thu tự động dưới mọi hình thức, không lượt thu, không nút fetch; kênh duy
nhất của lịch kinh tế + actual là mã nguồn trang người dùng dán (mục 6.1).

Bảng trên là **quyết định của Owner** (B5 — không còn giá trị `OPEN`). Nơi
lưu chính thức lúc runtime là tệp chính sách `config/news_policy.json` tạo khi
triển khai Bước 1 (S4); từ thời điểm tệp tồn tại, tài liệu trỏ về khóa của
tệp, không chép lại giá trị (D5). **Bảng này giữ vai trò bản ghi quyết định
của Owner, không phải bản sao giá trị runtime** — giá trị runtime đọc từ tệp
chính sách, mục 13 không nhân bản giá trị. Đổi bất kỳ giá trị nào = quyết
định mới của Owner, sửa tệp chính sách + ghi lý do, không sửa code.

## 8. `NewsRepository` — hợp đồng truy cập duy nhất (C1, S1)

Hợp đồng theo ý định, không phơi bày cách thực thi: chữ ký + ngữ nghĩa đầu
ra ổn định; đổi cách lưu trữ bên trong không buộc bên tiêu thụ sửa.

**Ghi (chỉ producer/controller gọi):** `upsert_events(list[CalendarEvent])`,
`upsert_items(list[NewsItem])`, `add_rate_observations(...)`,
`add_verdicts(list[TrendVerdict])`, `record_run(IngestRun)`,
`set_excluded(item_id, bool)`, `delete_user_note(item_id)`,
`purge_expired_runs()` — tất cả trả số bản ghi đã ghi/lỗi có kiểu.

**Đọc (mọi bên tiêu thụ):**

| Phương thức | Ngữ nghĩa |
|---|---|
| `events_in_range(from_utc, to_utc, currencies=None, include_non_impact=True)` | sự kiện theo cửa sổ, đã phân loại `status` |
| `events_pending_actual(now)` | sự kiện đã đến hạn công bố (`impact != non`, qua `event_time_utc + grace`) mà `actual` còn NULL — từ đợt 3 (24/09/2026) phục vụ **panel hướng dẫn "sự kiện đang thiếu actual"** của màn Quản lý tin (cho người dùng biết cần mở trang FF nào để dán mã nguồn); KHÔNG phục vụ lượt fetch tự động nào (không còn — §6.1) |
| `items_in_range(from_utc, to_utc=None, kinds=None, currencies=None, exclude_flagged=True)` | tin văn bản; mặc định bỏ tin `excluded=1` |
| `latest_rates(currencies)` | quan sát gần nhất mỗi đồng tiền + trend dẫn xuất |
| `store_state()` | trả `StoreState` — mô hình có kiểu (C3, cấm dict trần qua ranh giới): trạng thái `fresh`/`degraded`/`unavailable` cho từng tín hiệu (`events`, `items`, `rates`) + giờ ingest thành công cuối mỗi tín hiệu (từ `ingest_runs`) |
| `verdicts_for(scope_type, scope_value, limit)` | lịch sử nhận định AI, mới nhất trước |

**Cấm trong repository:** công thức chấm điểm, quyết định nghiệp vụ (gate),
chuỗi hiển thị — vi phạm lớp `services/` (mục 3).

## 9. Nhận định xu hướng của AI — contract dữ liệu

### 9.1. Luồng

1. Người dùng chọn phạm vi (cặp tiền hoặc đồng tiền) trong cửa sổ AI của màn
   Quản lý tin (UI đặc tả sau — mục 12).
2. `NewsController` đọc qua repository: sự kiện + tin văn bản (`excluded=0`)
   liên quan base/quote trong cửa sổ `ai_window_days`; nếu tổng < `ai_min_items`
   → trả trạng thái `insufficient_data`, **không gọi AI** (B4).
3. `core/trend_prompt_builder.py` (thuần) dựng prompt từ tập dữ liệu đã chuẩn
   hóa: AI **chỉ nhận định trên dữ liệu được đưa vào prompt**, cấm bịa sự
   kiện/số liệu (kế thừa doctrine tin tức hiện hành). Khuôn prompt thay đổi →
   `prompt_hash` thay đổi (provenance).
4. Gọi `AIService.analyze()` trong worker nền (không block GUI).
5. `core/trend_verdict_parser.py` (thuần) parse JSON 3 horizon
   (`short`/`mid`/`long` theo định nghĩa `ai_horizons`), mỗi horizon:
   `direction`, `confidence`, `rationale` tiếng Việt, `evidence_item_ids`.
   JSON không hợp lệ → retry một lần → thất bại trả lỗi thân thiện qua
   `friendly_error()` của provider adapter; **không lưu verdict rác**.
6. Repository lưu 3 dòng `ai_trend_verdicts` kèm `input_snapshot_json` +
   `prompt_hash`; cửa sổ hiển thị kết quả + lịch sử.

### 9.2. Ranh giới cứng (Owner chốt 20/09/2026)

> **AI chỉ là nhận định cho người dùng tham khảo — không tham gia vào BẤT KỲ
> quy trình nào:** không chấm điểm vĩ mô, không MacroGate/news gate, không
> guard thực thi lệnh, không Telegram alert, không producer nào khác đọc lại
> verdict làm đầu vào.

Bên tiêu thụ duy nhất của `ai_trend_verdicts` là màn Quản lý tin (qua
`NewsRepository.verdicts_for`). Cơ chế cưỡng chế tự động (E2): battery có
kiểm thử ghim — (a) không mô-đun scoring/gate/alert/producer nào import hoặc
query `verdicts_for`/bảng verdict; (b) import-linter chặn phụ thuộc ngược vào
`core/`; (c) parser/prompt builder được kiểm thử như hàm thuần (L2).

## 10. Provenance và nhập mã nguồn trang FF

- Mọi bản ghi có `source` + `fetched_at`; `news_events.raw_json` giữ JSON sự
  kiện đã trích để self-heal (không lưu cả trang); mọi lượt ghi có
  `ingest_runs`.
- **Kênh cập nhật duy nhất của lịch kinh tế + actual:** dán mã nguồn trang
  ForexFactory (mục 6.1) — chống trùng bằng `dedupe_key` UNIQUE, 3 quy tắc
  merge an toàn giữ nguyên văn, tóm tắt mới/cập nhật/xung đột mỗi lượt.
- **Xuất/nhập file CSV-JSON: BÃI BỎ** (Owner quyết 24/09/2026, đợt 3). Nhu
  cầu sao lưu (nếu có) thuộc về chính tệp database (`news.db` trong
  `%APPDATA%` — dữ liệu người dùng); bù ngày app không chạy thực hiện bằng
  dán mã nguồn trang của ngày quá khứ (mục 6.1).

## 11. Danh mục thay đổi bắt buộc (D4)

### 11a. Yêu cầu thay đổi → điểm chạm duy nhất → cơ chế bảo vệ

| Yêu cầu thay đổi | Điểm chạm duy nhất | Cơ chế bảo vệ |
|---|---|---|
| Đổi cấu trúc mã nguồn trang FF (khuôn JSON `calendarComponentStates`) | bộ chuyển đổi trong `services/ff_source_parser.py` | mô hình `CalendarEvent` bất biến (C2) + kiểm thử hợp đồng parser trên fixture source thật |
| Thêm/đổi nguồn tin văn bản (bỏ FXStreet, thêm feed mới) | bộ chuyển đổi trong `rss_producer` | mô hình `NewsItem` bất biến (C2) |
| Đổi chu kỳ poll/ân hạn/retention/cửa sổ AI | `config/news_policy.json` | chính sách có phiên bản; không sửa code (S4); giá trị mới cần bằng chứng hoặc `OPEN` |
| Đổi schema DB tin tức | migration mới + `NewsRepository` | bên tiêu thụ chỉ đọc qua hợp đồng repository (C1/C4) — kiểm thử consumer xanh nguyên trạng |
| Đổi quy tắc phân loại `stale`/`fresh` | `core/news_freshness.py` | thẩm quyền duy nhất (S1) + kiểm thử hàm thuần |
| Đổi khuôn prompt AI | `core/trend_prompt_builder.py` | `prompt_hash` provenance + kiểm thử parser không đổi (C4) |
| Đổi trường nhập tay | `NewsController` + form (tài liệu UI) | repository là điểm ghi duy nhất |
| Đổi cách Dashboard hiển thị sự kiện | tài liệu UI + mô-đun trình bày | hợp đồng `events_in_range` bất biến (ngoài phạm vi tài liệu này) |
| Đổi cách vĩ mô đọc tin | tài liệu vĩ mô + `macro_context_builder` (miền vĩ mô) | hợp đồng repository bất biến (ngoài phạm vi tài liệu này) |

### 11b. Sổ đăng ký sở hữu

| Phép tính/quyết định | Chủ sở hữu duy nhất |
|---|---|
| Sản xuất tín hiệu sự kiện lịch kinh tế (kể cả actual) | đường dán mã nguồn: `news_controller` (tiếp nhận) + `services/ff_source_parser.py` (bóc tách) |
| Bóc tách mã nguồn trang ForexFactory (JSON `calendarComponentStates` → `CalendarEvent` + `RateObservation` lãi suất `ff_html`) | `services/ff_source_parser.py` |
| Phân loại dòng của lô dán so với database (`Mới`/`Sẽ cập nhật`/`Xung đột — giữ nhập tay`) + **chung thiện lô đã chỉnh sửa** (stamp `source=user` cho dòng có sửa, giữ giá trị gốc vào `raw_json`) — hàm thuần, không I/O | `services/ff_source_parser.py` |
| Sản xuất tín hiệu tin văn bản tự động | `rss_producer` |
| Sản xuất quan sát lãi suất (FRED API + config fallback) | `fred_rate_producer` |
| Khai báo mô hình miền tin tức (`CalendarEvent`, `NewsItem`, `RateObservation`, `TrendVerdict`, `IngestRun`, `StoreState`) | `core/news_models.py` |
| Công thức `dedupe_key` của `news_events` (§4.2) | `core/news_models.py` |
| Công thức `dedupe_key` của `news_items` (§4.3) | `core/news_models.py` |
| Nạp và validate chính sách miền Tin tức | `core/news_policy.py` |
| Dẫn xuất trend lãi suất (hike/cut/hold) | `core/rate_trend.py` (`derive_rate_trend`) |
| Ghi tin nhập tay | `news_controller` |
| Đọc/ghi database tin tức | `news_repository` |
| Phân loại trạng thái dữ liệu (`scheduled/released/stale`, `fresh/degraded/unavailable`) | `core/news_freshness.py` |
| Dựng prompt nhận định xu hướng | `core/trend_prompt_builder.py` |
| Thẩm quyền nội dung verdict (parse/chấp nhận/từ chối) | `core/trend_verdict_parser.py` |
| Điều phối lịch producer + tiếp nhận dán mã nguồn/nhập tay + lời gọi AI | `news_controller` |
| Quyết định dùng verdict AI trong quy trình tự động | **không mô-đun nào** — bị cấm (mục 9.2); thay đổi = quyết định mới của Owner |

## 12. Tài liệu liên quan (trỏ, không chép — D5)

Viết **sau** khi phần Tin tức được duyệt và triển khai (theo quyết định Owner
20/09/2026 — làm phần news trước):

| Tài liệu | Nội dung tiếp nhận từ miền này |
|---|---|
| `docs/ui/screen_design.md` | **ĐÃ GHI 20/09/2026 + IMPLEMENTED 23/09/2026:** màn Quản lý tin + layout cửa sổ AI (mục News Screen — ca Tin tức đã nghiệm thu). **Viết sau (ca đấu nối a):** đặc tả hiển thị mục tin Dashboard (cột/tab/dialog/empty state) — tiêu thụ hợp đồng repository mục 8 |
| `docs/macro/macro_score_architecture.md` | Mapping 3 tier + gate sang đọc DB; hệ quả fail-closed từ `store_state`/`stale`; công thức và ngưỡng vĩ mô giữ nguyên |
| `docs/scanner/scanner-architecture.md` + `scanner-flow.md` | MacroGate/news gate đọc `events_in_range` + trạng thái `stale` — fail-closed: độ tươi dữ kiện FF phụ thuộc kỷ luật dán mã nguồn của người dùng (đợt 3, 24/09/2026 — không còn đường tự chữa `event_actual_or_lookup`); khẳng định verdict AI ngoài guard chain |
| `docs/architecture/architecture.md` | Bản đồ module/luồng dữ liệu mới; xóa mô tả `news_service.py` cũ |
| `docs/architecture/architecture-rules.md` (Phụ lục B) | **ĐÃ GHI 20/09/2026:** ngoại lệ E3 cho ca "đập đi – xây mới"; cập nhật mốc xử lý sổ nợ #1 |
| `docs/README.md` | **ĐÃ ĐĂNG KÝ 20/09/2026** vào danh sách tài liệu chính (D3) |
| `docs/product/product_spec.md`, `docs/guides/USER_GUIDE.md` | Tính năng + hướng dẫn sử dụng |

Code cũ bị thay thế (thời điểm xóa theo lộ trình tiêu thụ, tránh khoảng trống
runtime): `services/news_service.py`, `services/forex_factory_client.py`
(**không hấp thụ vào hệ mới** — đợt 3 chuyển FF sang kênh dán mã nguồn;
xóa tại đấu nối b), `services/interest_rate_service.py` (hấp thụ
vào `fred_rate_producer` — QĐ-1 phương án A, xóa tại đấu nối b), cache JSON
tin tức trên đĩa, `NewsWorker`/`fetch_news_window` phía Dashboard.

## 13. Quyết định đã chốt của Owner (B5 — không còn điểm OPEN)

Chốt ngày 20/09/2026 (đợt duyệt tài liệu này):

| Hạng mục | Quyết định |
|---|---|
| Toàn bộ giá trị chính sách số (chu kỳ poll RSS, cửa sổ thu RSS, chu kỳ FRED, ân hạn stale, ngưỡng degraded, retention log vận hành, cửa sổ AI, định nghĩa 3 chân trời) | Chốt tại bảng mục 7 — `config/news_policy.json` là nguồn runtime duy nhất (D5: mục này không nhân bản giá trị; riêng retention dọn tự động khi khởi động app theo mục 4.6) |
| Ranh giới verdict AI | **Advisory-only — không tham gia bất cứ quy trình nào** (scoring, gate, guard thực thi, alert, producer); đổi = quyết định mới của Owner (đặc tả hành vi: mục 9.2) |

Chốt ngày 20/09/2026, đợt 2 (điều chỉnh chế độ thu ForexFactory) — **đã bị
đợt 3 (24/09/2026) thay thế toàn bộ phần ForexFactory; bảng giữ làm ghi nhận
lịch sử quyết định, riêng dòng "RSS + FRED" còn hiệu lực**:

| Hạng mục | Quyết định |
|---|---|
| Chế độ thu ForexFactory | **Không poll** — thay khóa `ff_poll_interval_minutes` bằng 4 lượt thu: tự động 1 lượt khi khởi động app + nút "Lấy lịch kinh tế" + nút "Cập nhật actual" + on-demand lookup (mục 6.1) |
| Phân công kênh | JSON chỉ lấy lịch; HTML chỉ fetch targeted để lấy actual, không poll định kỳ |
| Quy tắc fetch khi bấm nút | Luôn fetch + **upsert đè** (không "đã tồn tại thì bỏ qua") để hiệu đính của FF được cập nhật; kèm 3 quy tắc merge an toàn (không NULL đè actual; bảo vệ `source=user`; xung đột actual → ưu tiên nhập tay + log) |
| Tuần trước | Không thu — chấp nhận mất dữ liệu khi app tắt trọn tuần; bù bằng nhập file thủ công |
| RSS + FRED | Giữ tự động định kỳ như đã ban hành (giá trị theo khóa `rss_poll_interval_minutes` / `fred_refresh_hours`, bảng mục 7) |
| Lỗi fetch HTML | Thông báo rõ nguyên nhân cho người dùng, không tự retry vòng lặp; người dùng có thể nhập actual bằng tay |

Nơi lưu giá trị chính thức lúc runtime: `config/news_policy.json` (mục 7).

Chốt ngày 24/09/2026, đợt 3 (kênh ForexFactory — dán mã nguồn trang; bãi bỏ
xuất/nhập file):

| Hạng mục | Quyết định |
|---|---|
| Bỏ thu tự động FF | Xóa cả 4 lượt thu (lượt khởi động JSON+HTML, nút "Lấy lịch kinh tế", nút "Cập nhật actual", on-demand lookup) — app **không phát request mạng nào tới ForexFactory** |
| Bãi bỏ xuất/nhập file | Export CSV/JSON và Import CSV/JSON (mục 10 cũ) bị bỏ; sao lưu = tệp `news.db`; bù ngày app không chạy = dán mã nguồn trang ngày quá khứ |
| Kênh duy nhất | Người dùng dán mã nguồn trang FF (dialog dán hoặc file `.html`) → `services/ff_source_parser.py` bóc JSON `calendarComponentStates` → upsert qua repository (chống trùng `dedupe_key` + 3 quy tắc merge giữ nguyên văn) → tóm tắt mới/cập nhật/xung đột (đặc tả hành vi: mục 6.1) |
| Stamp `source` | Sự kiện/actual/lãi suất bóc từ source dán = `ff_html` (enum đóng băng, đúng provenance); `ff_json`, `import` = giá trị lịch sử, không phát sinh; lượt dán ghi `ingest_runs` `producer=user` |
| Lãi suất từ source dán | CÓ — parser bóc sự kiện lãi suất theo danh mục kế thừa `_FOREX_RATE_EVENTS` (B5) → `interest_rates` `source=ff_html`; kênh FF-HTML qua mạng trong `fred_rate_producer` bị gỡ |
| `event_actual_or_lookup` | XÓA khỏi hợp đồng §8 — bên tiêu thụ đọc `events_in_range` + trạng thái `stale` (fail-closed; độ tươi là trách nhiệm người dùng dán source) |
| `events_pending_actual` | GIỮ, đổi công dụng: nuôi panel hướng dẫn "sự kiện đang thiếu actual" của màn Quản lý tin |
| Nhập tay | Form tin `user_note` (§6.4) GIỮ nguyên; đường "nhập actual bằng tay cho sự kiện khi HTML lỗi" BỎ — dán source là kênh actual duy nhất |
| RSS + FRED | KHÔNG đổi — giữ tự động định kỳ (`rss_poll_interval_minutes`, `fred_refresh_hours`) |
| Căn cứ | Điều tra 24/09/2026: nextweek JSON 404 vĩnh viễn (upstream gỡ), thisweek 429 tái diễn (budget IP hẹp + retry khuếch đại), HTML `forexfactory.com` chặn theo TLS fingerprint (handshake timeout với Python/curl, browser qua được), wss `calendar-feed:2087` bị managed challenge (403 `cf-mitigated: challenge`) — cả ba kênh tự động bất khả thi với app |

Chốt ngày 24/09/2026, đợt 4 (đường dán mã nguồn — **xác nhận của người dùng
trước khi ghi**; bổ sung hạng mục "Kênh duy nhất" của đợt 3, các hạng mục
khác của đợt 3 giữ nguyên hiệu lực):

| Hạng mục | Quyết định |
|---|---|
| Luồng 2 pha | **Pha 1:** dán source → "Bóc tách" → hệ thống hiển thị **bảng xem trước** dữ liệu kinh tế đã bóc (thời gian UTC, đồng tiền, sự kiện, tác động, dự báo, kỳ trước, **actual từ chính source**) kèm trạng thái từng dòng (`Mới`/`Sẽ cập nhật`/`Xung đột — giữ nhập tay`, đối chiếu `dedupe_key` chỉ-đọc) — **không ghi gì**. **Pha 2:** người dùng kiểm tra, bấm **"Cập nhật"** → hệ thống mới ghi CSDL (+ `ingest_runs` `producer=user` + tóm tắt); bấm **"Hủy"** → không ghi, không sinh lượt ingest (đặc tả hành vi: §6.1) |
| Quyền trên bảng xem trước | **Chỉ được sửa cột `actual` khi phát hiện sai sót** (Owner quyết 24/09/2026); mọi cột còn lại (thời gian, đồng tiền, sự kiện, tác động, dự báo, kỳ trước) **read-only**; không bỏ chọn/xóa dòng — "Cập nhật" ghi toàn bộ lô bóc được (all-or-nothing); dòng đã sửa mang trạng thái `Đã sửa`, phân loại tính lại |
| Provenance của chỉnh sửa | Dòng sự kiện có actual đã sửa → `source=user` (quy tắc merge 2+3 bảo vệ trước các lượt dán sau), **giá trị actual FF gốc giữ trong `raw_json`**; dòng không sửa → `source=ff_html`; quan sát lãi suất giữ `ff_html` (enum §4.4 không có `user` — đóng băng), giá trị đồng bộ theo actual đã sửa; `dedupe_key` **bất biến** (chỉ actual được sửa) |
| Phân loại dòng preview | Hàm thuần trong `services/ff_source_parser.py` (đăng ký §11b) — controller không tự tính (S2), UI không tự tính (L1) |
| Căn cứ | Người dùng là chốt chặn cuối trước khi số liệu vào nguồn chân lý duy nhất (nuôi vĩ mô/gate tại đấu nối b); parser lệch do FF đổi cấu trúc → thấy ngay trên bảng preview và hủy, thay vì nhiễm DB âm thầm (B4) |

## 14. Kiểm thử (C4, B3, E2)

- **Hàm thuần (`core/`):** `news_freshness` (bảng trạng thái theo biên thời
  gian), `trend_prompt_builder` (prompt ổn định, hash), `trend_verdict_parser`
  (JSON hợp lệ/lỗi/thiếu horizon → từ chối, không lưu rác).
- **Repository:** CRUD/upsert/dedupe/`excluded`/retention purge; `store_state`
  đúng theo `ingest_runs`.
- **Parser source FF (`services/ff_source_parser.py`):** bóc trên **fixture
  mã nguồn thật** (trang chủ/ngày/tuần — fixture lấy từ source người dùng dán
  24/09/2026): đủ trường ánh xạ §6.1 bước 3 (dateline UTC, impact, rỗng→NULL,
  revision/notice vào `raw_json`); nhiều ngày trong `days[]`; bóc sự kiện lãi
  suất theo danh mục kế thừa; source không có JSON lịch → lỗi có kiểu, không
  ghi gì; JSON hỏng/cắt cụt → all-or-nothing.
- **Lượt dán 2 pha (controller + repository):** pha 1 không ghi — bóc tách +
  preview xong, database nguyên trạng, không run mới; phân loại dòng đúng
  (mới/sẽ cập nhật/xung đột-giữ-nhập-tay); **chung thiện lô đã sửa đúng**
  (dòng có sửa actual → `source=user` + actual gốc trong `raw_json`; dòng
  không sửa → `ff_html`; lãi suất theo actual đã sửa; `dedupe_key` bất
  biến); hủy = không ghi không run; pha 2
  xác nhận → chống trùng (dán 2 lần cùng source không tạo row trùng — khớp
  `dedupe_key` → cập nhật); 3 quy tắc merge mỗi quy tắc một test riêng (không
  NULL đè actual, bảo vệ `source=user`, xung đột actual → ưu tiên user +
  log); đếm mới/cập nhật/xung đột đúng; `ingest_runs` ghi `producer=user`.
- **Producer RSS/FRED:** HTTP giả lập — RSS: fixture XML từng feed, dedupe,
  feed chết → `partial`; FRED: chuỗi nguồn API → config fallback đúng thứ tự,
  không còn kênh FF-HTML qua mạng.
- **Kiểm thử hợp đồng (C4):** ghim chữ ký + ngữ nghĩa phương thức đọc mục 8 —
  bên tiêu thụ (Dashboard, vĩ mô) viết kiểm thử theo hợp đồng này, xanh nguyên
  trạng khi nội bộ repository thay đổi.
- **Kiểm thử đặc trưng (B3):** trước khi xóa `news_service.py`, ghim đầu ra
  macro tiers/coverage trên fixture dữ liệu cũ; sau khi miền vĩ mô chuyển sang
  đọc DB, đối chiếu tương đương trên cùng fixture (thực hiện ở ca vĩ mô).
- **Cổng E2:** kiểm thử cấm mô-đun scoring/gate/alert/producer đọc
  `ai_trend_verdicts`; import-linter chiều phụ thuộc.

## 15. Tự rà soát E1 (bốn câu hỏi bắt buộc)

1. **Chủ sở hữu:** mọi phép tính của miền đăng ký tại mục 11b; bên tiêu thụ
   chỉ dùng hợp đồng repository — không nhân bản.
2. **Một lý do thay đổi:** mỗi mô-đun mục 3/6 có danh tính M5 một câu không
   "và"; `NewsService` cũ 4 vai trò bị thay thế (đóng sổ nợ #1 khi hoàn tất).
3. **Điều khoản tài liệu:** hành vi mới đều có mục ở trên; tài liệu đã BAN
   HÀNH (Owner duyệt 20/09/2026) và đã đăng ký vào `docs/README.md` (D3).
4. **Định danh phiên bản:** không tên phiên bản trong mô-đun/tính năng mới;
   chỉ `policy_version`/`prompt_hash` là khóa provenance máy đọc — ngoại lệ
   V3(a), đóng băng, không xuất hiện trên UI.

## 16. Lộ trình triển khai (đăng ký 21/09/2026 — HOÀN TẤT 23/09/2026)

**Trạng thái hoàn tất (23/09/2026):** toàn bộ 4 bước + 21 lô của tầng dữ liệu
Tin tức đã IMPLEMENTED và nghiệm thu (battery + smoke + build `.exe` + boot
bản đóng gói xanh; cổng E2 hoạt động). Tuyên bố **READY-FOR-CONNECT** cho hai
ca đấu nối: (a) Dashboard và (b) vĩ mô — đặc tả riêng, lập plan riêng theo
§3.1 khoản 3–4. Sổ nợ kiến trúc **#1 chưa đóng** — chỉ đóng tại đấu nối (b)
khi xóa `news_service.py` + `forex_factory_client.py` (§3.1 khoản 4, B7).

Bốn bước, đúng thứ tự; chi tiết thực thi (sản phẩm, Definition of Done, ràng
buộc, rủi ro, quyết định mở) nằm trong plan triển khai của ca — **đã đóng và
xóa theo vòng đời D3 sau khi hoàn tất ca**; lịch sử còn trong Git.

| Bước | Nội dung | Điều khoản neo |
|---|---|---|
| 1 | Nền tảng miền: `config/news_policy.json`, migration `news.db` (5 bảng + index), `core/news_models.py`, `core/news_freshness.py`, `core/rate_trend.py`, đăng ký asset đóng gói | §4, §5, §6.5, §7 |
| 2 | Tầng dữ liệu: `NewsRepository`, `ff_calendar_producer`, `rss_producer`, bộ sản xuất lãi suất FRED (QĐ-1 của plan), `NewsController` + worker; chưa bật fetch khởi động | §6, §8, §14 |
| 3 | Màn Quản lý tin + cửa sổ AI nhận định xu hướng; bật lượt fetch tự động khi khởi động + retention purge | `screen_design.md` mục News Screen; §9, §10 |
| 4 | Nghiệm thu tổng: cổng E2 (cách ly verdict AI, import-linter, quét chuỗi hiển thị trong `core/`), battery + smoke + build `.exe`, đồng bộ tài liệu, tuyên bố READY-FOR-CONNECT | §9.2, §14 |

Hai ca đấu nối **(a) Dashboard** và **(b) vĩ mô** (§3.1 khoản 3–4) nằm ngoài
lộ trình này, lập plan riêng sau khi Bước 4 đạt.

**Sửa đổi đợt 3 (24/09/2026):** ca "Nguồn dán FF" — thay kênh thu
ForexFactory bằng dán mã nguồn trang + bãi bỏ xuất/nhập file (mục 6.1, 10,
13); triển khai theo plan riêng (vòng đời D3). Lộ trình 4 bước ở trên giữ
nguyên làm ghi nhận lịch sử của ca tầng dữ liệu.

**Ghi chú hoàn tất ca "Nguồn dán FF" (25/09/2026):** 5 lô F1–F5 đều
**IMPLEMENTED**; nghiệm thu tổng xanh (battery đối chiếu ngoại lệ danh tính R9 —
họ `test_step3_fred.py` + collection error `test_smc_gate72_fix_acceptance.py`;
3 smoke EXIT=0; build `.exe` + boot bản đóng gói không sinh lượt `ff_crawler`;
luồng dán 2 pha đầu-cuối đúng điều khoản §6.1 đợt 4). Tuyên bố: miền Tin tức giữ
READY-FOR-CONNECT — hai ca đấu nối (a) Dashboard / (b) vĩ mô không đổi lộ trình
(§3.1 khoản 3-4); sổ nợ #1 **chưa đóng** — chỉ đóng tại đấu nối (b) khi xóa
`news_service.py` + `forex_factory_client.py`.
