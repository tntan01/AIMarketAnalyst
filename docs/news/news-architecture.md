# Kiến trúc Tin tức — Contract tầng dữ liệu

> **Trạng thái: BAN HÀNH — Owner duyệt ngày 20/09/2026 (V1).** Tài liệu này
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
> thu theo chế độ **khởi động + nút bấm, không thăm dò định kỳ (poll)**; RSS
> và FRED giữ tự động định kỳ (quyết định bổ sung cùng ngày, mục 6.1 và 13).

---

## 1. Ý định Owner (nguồn gốc đặc tả)

1. Database tin tức (SQLite) là **nguồn chân lý duy nhất**: bộ sản xuất chỉ
   GHI, bên tiêu thụ chỉ ĐỌC; không bên tiêu thụ nào gọi thẳng ra nguồn ngoài.
2. Tin tức tự động thu từ ForexFactory (lịch kinh tế), RSS (headline/phát
   biểu), FRED (lãi suất); người dùng có thể nhập tay tin bổ sung; dữ liệu
   được cập nhật vào database theo từng ngày.
3. Database phục vụ hai bên tiêu thụ chính: **tin tức trên Dashboard** và
   **chấm điểm vĩ mô/macro gate** (đặc tả từng bên nằm ở tài liệu miền tương
   ứng — mục 12), cộng với màn **Quản lý tin** (xem/nhập/sửa/xuất).
4. Màn Quản lý tin có cửa sổ nhỏ gọi **AI nhận định xu hướng ngắn hạn/trung
   hạn/dài hạn** của cặp tiền — kết quả **chỉ tư vấn cho người dùng**, không
   là đầu vào của scoring, gate, guard thực thi hay alert (quyết định chốt
   20/09/2026).
5. Riêng ForexFactory: **không thăm dò định kỳ (poll)** — dữ liệu lịch lấy
   theo lượt tự động khi khởi động app và theo nút bấm của người dùng; actual
   chỉ lấy đúng đối tượng cần (targeted) bằng HTML khi cần. RSS và FRED **giữ
   tự động định kỳ** như thiết kế (Owner quyết 20/09/2026, đợt 2 — chi tiết
   mục 6.1, 13).

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
| Lượt ingest (ingest run) | Một lần chạy của một bộ sản xuất, có kết quả và số bản ghi đã ghi |
| Ân hạn (grace) | Khoảng chờ sau giờ sự kiện trước khi đánh dấu `stale` |

Nhãn trạng thái/loại/nguồn là **enum máy đọc** — chuỗi đóng băng, không đổi
giá trị đã persist (V3(a)). Từ điển hiển thị tiếng Việt thuộc tầng trình bày,
đăng ký trong tài liệu UI tương ứng.

## 3. Kiến trúc tổng thể và phân lớp (L1)

```text
BỘ SẢN XUẤT (chỉ GHI)                       DATABASE                      BÊN TIÊU THỤ (chỉ ĐỌC)
─────────────────────                       ────────                      ─────────────────────
ff_calendar_producer  (ForexFactory)  ───►  news_events              ───►  Dashboard (đặc tả: screen_design.md — viết sau)
rss_producer          (Google News,   ───►  news_items               ───►  Chấm điểm vĩ mô/gate (đặc tả: macro_score_architecture.md — viết sau)
                       FXStreet,            interest_rates           ───►  Màn Quản lý tin (xem/nhập/sửa/xuất)
                       Investing)           ai_trend_verdicts        ───►  Cửa sổ AI nhận định xu hướng (đọc lịch sử verdict)
fred_rate_producer    (FRED)          ───►  ingest_runs
Người dùng (form nhập tay, qua NewsController)

Mọi đọc/ghi đi qua NewsRepository — điểm truy cập database duy nhất (S1).
```

Chiều phụ thuộc bắt buộc:

```text
ui → controllers → core ← services (repository, producer)
```

| Lớp | Mô-đun của miền này | Vai trò |
|---|---|---|
| `services/` | `news_repository.py`; `news_producers/ff_calendar_producer.py`; `news_producers/rss_producer.py`; `news_producers/fred_rate_producer.py` | Vào/ra + tầng chống ăn mòn (C2): biên dịch dữ liệu thô nguồn ngoài → mô hình miền có tên ngay tại biên; dữ liệu thô không tồn tại ngoài bộ chuyển đổi |
| `core/` | `news_policy.py`; `news_models.py`; `news_freshness.py`; `rate_trend.py`; `trend_prompt_builder.py`; `trend_verdict_parser.py` | Logic thuần: nạp và xác thực chính sách miền, mô hình miền, phân loại trạng thái dữ liệu, dẫn xuất trend lãi suất, dựng prompt, parse verdict. Không vào/ra, không chuỗi hiển thị (L2, L3). Mô hình miền **bắt buộc đặt trong `core/`** vì L1 cấm `Core → Services` (hàm thuần `core/` nhận mô hình làm tham số) |
| `controllers/` | `news_controller.py` | Điều phối: lên lịch producer, phục vụ truy vấn cho bên tiêu thụ, tiếp nhận nhập tay, điều phối gọi AI trong worker |
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
3. **Hoàn thiện mới đấu nối.** Tính năng Tin tức (database + đủ bộ sản xuất
   FF/RSS/FRED/nhập tay + màn Quản lý tin + cửa sổ AI nhận định) phải hoàn
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
| `source` | TEXT enum | `ff_json` \| `ff_html` \| `user` \| `import` |
| `dedupe_key` | TEXT UNIQUE | hash(`event_time_utc` + `currency` + `title`) — upsert (ghi đè nếu đã tồn tại, chèn nếu chưa) không trùng |
| `raw_json` | TEXT NULL | payload gốc, chỉ cho provenance/self-heal |
| `fetched_at` | TEXT | lượt lấy dữ liệu (fetch) gần nhất chạm bản ghi |

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
| `source` | TEXT enum | `fred` \| `ff_html` \| `config_fallback` |
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
| `producer` | TEXT enum | `ff_crawler` \| `rss` \| `fred` \| `user` \| `on_demand_lookup` |
| `started_at` / `finished_at` | TEXT | |
| `status` | TEXT enum | `ok` \| `partial` \| `failed` |
| `items_written` | INTEGER | số bản ghi upsert |
| `error_type` / `error_detail` | TEXT NULL | phân loại lỗi kế thừa transport hiện hành (vd `Http429`, `InvalidRSSStructure`) |

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

Bộ chuyển đổi nguồn (trong từng producer) là nơi **duy nhất** nhìn thấy dữ
liệu thô (JSON feed, HTML, XML RSS); ra khỏi biên chỉ có mô hình miền. Đổi
nhà cung cấp = thay bộ chuyển đổi, giữ nguyên mô hình (C2).

## 6. Bộ sản xuất — sổ đăng ký tín hiệu (S6: mỗi tín hiệu một chủ sở hữu)

| Tín hiệu | Bộ sản xuất duy nhất | Danh tính mô-đun (M5 — một câu không "và") |
|---|---|---|
| Sự kiện lịch kinh tế + actual | `ff_calendar_producer` | Sở hữu tri thức lấy và chuẩn hóa lịch kinh tế ForexFactory thành `CalendarEvent` |
| Headline + phát biểu chính thức | `rss_producer` | Sở hữu tri thức thu thập tin văn bản công khai thành `NewsItem` |
| Quan sát lãi suất | `fred_rate_producer` (FRED) | Sở hữu tri thức thu thập lãi suất điều hành 8 đồng tiền thành `RateObservation` |
| Ghi chú nhập tay | `news_controller` (đường nhập tay) | Sở hữu tri thức tiếp nhận và xác thực tin người dùng nhập |
| Nhận định xu hướng AI | `news_controller` (đường AI, ghi qua repository) | Sở hữu điều phối lời gọi AI; thẩm quyền nội dung verdict thuộc parser (mục 9) |

### 6.1. `ff_calendar_producer` — chế độ khởi động + nút bấm (không poll)

Kế thừa transport của `forex_factory_client.py` hiện hành (JSON feed
`nfs.faireconomy.media/ff_calendar_thisweek.json` + `nextweek.json`; HTML
`forexfactory.com/calendar`; xử lý 429; hòa trộn (merge) actual từ HTML) —
hấp thụ thành bộ chuyển đổi nội bộ, mô hình ra là `CalendarEvent`.

**Phân công hai kênh (Owner quyết 20/09/2026):** JSON đảm nhận **lịch** (giờ,
đồng tiền, tên, impact, forecast/previous — dữ liệu gần như tĩnh, FF chốt
trước theo tuần); HTML đảm nhận **actual** — JSON feed không có actual, và
HTML chỉ được fetch **targeted** (đúng ngày/tuần chứa sự kiện đến hạn), không
bao giờ poll định kỳ.

Các lượt thu — request mạng tới ForexFactory chỉ phát sinh trong 4 trường hợp:

1. **Lượt tự động khi khởi động app** (một lần mỗi phiên, không timer): fetch
   JSON tuần này + tuần sau, upsert lịch; sau đó fetch HTML targeted cho các
   sự kiện đã đến hạn công bố (theo `events_pending_actual`) mà `actual` còn
   NULL.
2. **Nút "Lấy lịch kinh tế"** (màn Quản lý tin): lặp lại phần JSON của lượt
   khởi động — **luôn fetch, không kiểm tra "đã tồn tại thì bỏ qua"** để hiệu
   đính của FF (đổi giờ/impact/forecast) luôn được cập nhật.
3. **Nút "Cập nhật actual"** (màn Quản lý tin): fetch HTML targeted cho các
   sự kiện `events_pending_actual()` trả về, merge actual.
4. **On-demand lookup:** bên tiêu thụ yêu cầu (qua `NewsController`) một sự
   kiện đã qua giờ công bố mà `actual` còn NULL → fetch ngay sự kiện đó,
   upsert rồi trả `CalendarEvent` mới; ghi `ingest_runs` với producer
   `on_demand_lookup`.

**Tuần trước: KHÔNG thu** (Owner quyết) — JSON feed không có tuần trước; app
tắt trọn tuần thì chấp nhận mất dữ liệu tuần đó. Đường bù duy nhất là nhập
file thủ công (mục 10).

**Quy tắc merge khi upsert (3 quy tắc an toàn):**

1. **Không ghi đè giá trị thật bằng NULL** — `actual` chỉ được ghi khi dữ liệu
   mới có giá trị; lịch từ JSON không được xóa `actual` đã có.
2. **Bảo vệ dữ liệu nhập tay** — bản ghi `source=user` không bị merge tự động
   đè; chỉ người dùng được sửa.
3. **Xung đột actual** (giá trị nhập tay khác giá trị tự động) → ưu tiên nhập
   tay, ghi nhận xung đột vào `ingest_runs`.

**Chống lạm dụng nguồn:** lỗi/429 → thông báo rõ nguyên nhân cho người dùng
(nút bấm) hoặc ghi `ingest_runs` (lượt khởi động/on-demand); **không tự retry
theo vòng lặp**. Tần suất chạm HTML thực tế vài lượt/ngày — rủi ro bị chặn
nguồn gần bằng 0. Khi HTML lỗi, người dùng có thể nhập actual bằng tay qua
màn Quản lý tin.

### 6.2. `rss_producer`

Kế thừa tập query Google News RSS hiện hành (headline rộng + phát biểu:
Trump/Fed/PM Nhật/PM Anh/EU) và feed phụ FXStreet/Investing. Thăm dò (poll)
theo khóa `rss_poll_interval_minutes`; cửa sổ thu theo khóa `rss_window_hours`
(kế thừa giá trị đang chạy — bằng chứng: runtime hiện hành); dedupe theo
`dedupe_key`.

### 6.3. `fred_rate_producer` (QĐ-1 phương án A — Owner duyệt 21/09/2026)

File mới `services/news_producers/fred_rate_producer.py`, hấp thụ logic FRED
hiện hành của `interest_rate_service.py` theo cùng khuôn FF (§6.1): copy
logic sang file mới, **không sửa file cũ**. Giữ tần suất hiện hành (khóa
`fred_refresh_hours`); đích ghi là bảng `interest_rates`. Fallback
`config/interest_rates.json` ghi `source=config_fallback`. Dẫn xuất trend
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

**ForexFactory không có khóa chu kỳ** — chế độ thu là 4 trường hợp của mục
6.1 (lượt khởi động, 2 nút bấm, on-demand lookup), không poll (Owner quyết
20/09/2026 đợt 2).

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
| `events_pending_actual(now)` | sự kiện đã đến hạn công bố (`impact != non`, qua `event_time_utc + grace`) mà `actual` còn NULL — phục vụ lượt khởi động, nút "Cập nhật actual" và on-demand lookup |
| `event_actual_or_lookup(event_id)` | trả `CalendarEvent`; nếu `stale` → kích hoạt on-demand lookup (6.1) trước khi trả |
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

## 10. Provenance, nhập/xuất file

- Mọi bản ghi có `source` + `fetched_at`; `news_events.raw_json` giữ payload
  gốc để self-heal; mọi lượt producer có `ingest_runs`.
- **Export:** CSV/JSON theo khoảng ngày, ra `%APPDATA%/ai-market-analyst/exports/`
  (dữ liệu người dùng, không ghi vào thư mục cài đặt).
- **Import:** upsert theo `dedupe_key`, `source=import` — để bù ngày app không
  chạy. Import không được ghi đè `actual` đã có từ nguồn chính thống
  (FF) trừ khi bản ghi đích đang `stale`.

## 11. Danh mục thay đổi bắt buộc (D4)

### 11a. Yêu cầu thay đổi → điểm chạm duy nhất → cơ chế bảo vệ

| Yêu cầu thay đổi | Điểm chạm duy nhất | Cơ chế bảo vệ |
|---|---|---|
| Đổi khuôn dạng/nguồn lịch kinh tế (JSON feed, cách scrape) | bộ chuyển đổi trong `ff_calendar_producer` | mô hình `CalendarEvent` bất biến (C2) + kiểm thử hợp đồng producer |
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
| Sản xuất tín hiệu sự kiện lịch kinh tế (kể cả actual) | `ff_calendar_producer` |
| Sản xuất tín hiệu tin văn bản tự động | `rss_producer` |
| Sản xuất quan sát lãi suất | `fred_rate_producer` |
| Khai báo mô hình miền tin tức (`CalendarEvent`, `NewsItem`, `RateObservation`, `TrendVerdict`, `IngestRun`, `StoreState`) | `core/news_models.py` |
| Nạp và validate chính sách miền Tin tức | `core/news_policy.py` |
| Dẫn xuất trend lãi suất (hike/cut/hold) | `core/rate_trend.py` (`derive_rate_trend`) |
| Ghi tin nhập tay | `news_controller` |
| Đọc/ghi database tin tức | `news_repository` |
| Phân loại trạng thái dữ liệu (`scheduled/released/stale`, `fresh/degraded/unavailable`) | `core/news_freshness.py` |
| Dựng prompt nhận định xu hướng | `core/trend_prompt_builder.py` |
| Thẩm quyền nội dung verdict (parse/chấp nhận/từ chối) | `core/trend_verdict_parser.py` |
| Điều phối lịch producer + lời gọi AI | `news_controller` |
| Quyết định dùng verdict AI trong quy trình tự động | **không mô-đun nào** — bị cấm (mục 9.2); thay đổi = quyết định mới của Owner |

## 12. Tài liệu liên quan (trỏ, không chép — D5)

Viết **sau** khi phần Tin tức được duyệt và triển khai (theo quyết định Owner
20/09/2026 — làm phần news trước):

| Tài liệu | Nội dung tiếp nhận từ miền này |
|---|---|
| `docs/ui/screen_design.md` | **ĐÃ GHI 20/09/2026:** màn Quản lý tin + layout cửa sổ AI (mục News Screen, trạng thái PLANNED). **Viết sau (ca đấu nối a):** đặc tả hiển thị mục tin Dashboard (cột/tab/dialog/empty state) — tiêu thụ hợp đồng repository mục 8 |
| `docs/macro/macro_score_architecture.md` | Mapping 3 tier + gate sang đọc DB; hệ quả fail-closed từ `store_state`/`stale`; công thức và ngưỡng vĩ mô giữ nguyên |
| `docs/scanner/scanner-architecture.md` + `scanner-flow.md` | MacroGate/news gate dùng `event_actual_or_lookup`; khẳng định verdict AI ngoài guard chain |
| `docs/architecture/architecture.md` | Bản đồ module/luồng dữ liệu mới; xóa mô tả `news_service.py` cũ |
| `docs/architecture/architecture-rules.md` (Phụ lục B) | **ĐÃ GHI 20/09/2026:** ngoại lệ E3 cho ca "đập đi – xây mới"; cập nhật mốc xử lý sổ nợ #1 |
| `docs/README.md` | **ĐÃ ĐĂNG KÝ 20/09/2026** vào danh sách tài liệu chính (D3) |
| `docs/product/product_spec.md`, `docs/guides/USER_GUIDE.md` | Tính năng + hướng dẫn sử dụng |

Code cũ bị thay thế (thời điểm xóa theo lộ trình tiêu thụ, tránh khoảng trống
runtime): `services/news_service.py`, `services/forex_factory_client.py` (hấp
thụ vào `ff_calendar_producer`), `services/interest_rate_service.py` (hấp thụ
vào `fred_rate_producer` — QĐ-1 phương án A, xóa tại đấu nối b), cache JSON
tin tức trên đĩa, `NewsWorker`/`fetch_news_window` phía Dashboard.

## 13. Quyết định đã chốt của Owner (B5 — không còn điểm OPEN)

Chốt ngày 20/09/2026 (đợt duyệt tài liệu này):

| Hạng mục | Quyết định |
|---|---|
| Toàn bộ giá trị chính sách số (chu kỳ poll RSS, cửa sổ thu RSS, chu kỳ FRED, ân hạn stale, ngưỡng degraded, retention log vận hành, cửa sổ AI, định nghĩa 3 chân trời) | Chốt tại bảng mục 7 — `config/news_policy.json` là nguồn runtime duy nhất (D5: mục này không nhân bản giá trị; riêng retention dọn tự động khi khởi động app theo mục 4.6) |
| Ranh giới verdict AI | **Advisory-only — không tham gia bất cứ quy trình nào** (scoring, gate, guard thực thi, alert, producer); đổi = quyết định mới của Owner (đặc tả hành vi: mục 9.2) |

Chốt ngày 20/09/2026, đợt 2 (điều chỉnh chế độ thu ForexFactory):

| Hạng mục | Quyết định |
|---|---|
| Chế độ thu ForexFactory | **Không poll** — thay khóa `ff_poll_interval_minutes` bằng 4 lượt thu: tự động 1 lượt khi khởi động app + nút "Lấy lịch kinh tế" + nút "Cập nhật actual" + on-demand lookup (mục 6.1) |
| Phân công kênh | JSON chỉ lấy lịch; HTML chỉ fetch targeted để lấy actual, không poll định kỳ |
| Quy tắc fetch khi bấm nút | Luôn fetch + **upsert đè** (không "đã tồn tại thì bỏ qua") để hiệu đính của FF được cập nhật; kèm 3 quy tắc merge an toàn (không NULL đè actual; bảo vệ `source=user`; xung đột actual → ưu tiên nhập tay + log) |
| Tuần trước | Không thu — chấp nhận mất dữ liệu khi app tắt trọn tuần; bù bằng nhập file thủ công |
| RSS + FRED | Giữ tự động định kỳ như đã ban hành (giá trị theo khóa `rss_poll_interval_minutes` / `fred_refresh_hours`, bảng mục 7) |
| Lỗi fetch HTML | Thông báo rõ nguyên nhân cho người dùng, không tự retry vòng lặp; người dùng có thể nhập actual bằng tay |

Nơi lưu giá trị chính thức lúc runtime: `config/news_policy.json` (mục 7).

## 14. Kiểm thử (C4, B3, E2)

- **Hàm thuần (`core/`):** `news_freshness` (bảng trạng thái theo biên thời
  gian), `trend_prompt_builder` (prompt ổn định, hash), `trend_verdict_parser`
  (JSON hợp lệ/lỗi/thiếu horizon → từ chối, không lưu rác).
- **Repository:** CRUD/upsert/dedupe/`excluded`/retention purge; `store_state`
  đúng theo `ingest_runs`.
- **Producer:** HTTP giả lập — JSON ok / 429 / HTML targeted / merge actual;
  lượt khởi động; hành vi 2 nút bấm; on-demand lookup; 3 quy tắc merge (không
  NULL đè actual, bảo vệ `source=user`, xung đột actual → ưu tiên nhập tay +
  log `ingest_runs`).
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

## 16. Lộ trình triển khai (đăng ký 21/09/2026)

Bốn bước, đúng thứ tự; chi tiết thực thi (sản phẩm, Definition of Done, ràng
buộc, rủi ro, quyết định mở) tại plan đang mở
[`../plans/news-data-layer-plan.md`](../plans/news-data-layer-plan.md) (vòng
đời D3 — xóa khi hoàn tất ca):

| Bước | Nội dung | Điều khoản neo |
|---|---|---|
| 1 | Nền tảng miền: `config/news_policy.json`, migration `news.db` (5 bảng + index), `core/news_models.py`, `core/news_freshness.py`, `core/rate_trend.py`, đăng ký asset đóng gói | §4, §5, §6.5, §7 |
| 2 | Tầng dữ liệu: `NewsRepository`, `ff_calendar_producer`, `rss_producer`, bộ sản xuất lãi suất FRED (QĐ-1 của plan), `NewsController` + worker; chưa bật fetch khởi động | §6, §8, §14 |
| 3 | Màn Quản lý tin + cửa sổ AI nhận định xu hướng; bật lượt fetch tự động khi khởi động + retention purge | `screen_design.md` mục News Screen; §9, §10 |
| 4 | Nghiệm thu tổng: cổng E2 (cách ly verdict AI, import-linter, quét chuỗi hiển thị trong `core/`), battery + smoke + build `.exe`, đồng bộ tài liệu, tuyên bố READY-FOR-CONNECT | §9.2, §14 |

Hai ca đấu nối **(a) Dashboard** và **(b) vĩ mô** (§3.1 khoản 3–4) nằm ngoài
lộ trình này, lập plan riêng sau khi Bước 4 đạt.
