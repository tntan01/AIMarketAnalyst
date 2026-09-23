# Kiến trúc hệ thống

> Tài liệu kiến trúc đầy đủ **duy nhất** của dự án (bản `ARCHITECTURE.md` ở thư
> mục gốc đã được gộp vào đây ngày 20/09/2026). Mọi thiết kế/sửa chữa phải tuân
> thủ [Quy tắc kiến trúc](architecture-rules.md). Trạng thái cấu hình/thực thi
> thực tế trên máy: [`runtime-status.md`](runtime-status.md).

## Bản đồ định vị nhanh

Đọc mục này trước khi mò vào code.

App desktop **AI Market Analyst** (PyQt6) phân tích trading MT5. Runtime Scanner
sử dụng luồng: lấy dữ liệu thị trường → phân tích kỹ thuật (SMC) → chấm điểm
setup; macro, market safety và AI policy chạy ở lớp assessment/gate → xếp hạng →
hiển thị bảng scanner → (tùy chọn) tự vào lệnh MT5.

> **Kiến trúc đã chốt:** Scanner tách Macro và Risk khỏi điểm số,
> direct cutover không shadow/dual scoring. Contract runtime tại
> [`scanner/scanner-architecture.md`](../scanner/scanner-architecture.md).

**Luồng dữ liệu chính:**
```
MT5 / Yahoo / ForexFactory ──► services (data) ──► core (phân tích) ──► workers (nền) ──► controllers ──► ui (PyQt6)
                                                                                              │
                                                              AI prompts (services/ai) ◄──────┘
```

### Các lớp (layer)

| Thư mục | Vai trò |
|---------|---------|
| `main.py` | Entry point: khởi tạo runtime, QApplication, AppController, MainWindow |
| `controllers/` | **DI container + điều phối.** `AppController` giữ singleton mọi service/controller. Mỗi màn hình nhận cùng 1 instance |
| `core/` | **Logic nghiệp vụ thuần** (không phụ thuộc UI). Phân tích, SMC, scoring, risk, scanner engine |
| `services/` | **Truy cập bên ngoài + hạ tầng**: MT5, AI providers, news, journal (SQLite), telegram, storage, logging |
| `workers/` | **Thread nền** (QThread/QObject) chạy tác vụ nặng: scan, analyze |
| `ui/` | **Giao diện PyQt6**: screens, components, theme, chart bridge |
| `config/` | Cấu hình: constants, paths, settings, risk params, AI providers, symbol profiles |
| `data/` | SQL migrations + seed data (journal DB) |
| `tools/`, `scripts/` | Tiện ích dev/audit/validation (chạy thủ công, không phải runtime) |
| `packaging/` | Build Windows (PyInstaller) |
| `tests/` | Pytest |

### Module then chốt (đọc khi cần)

**Luồng phân tích 1 symbol**
- `core/analysis_pipeline.py` — **orchestrator** chính: gọi tuần tự các engine, trả dict kết quả
- `core/analysis_engine.py` — engine phân tích tổng
- `core/indicators.py` — tính chỉ báo kỹ thuật
- `core/smc_*.py` — Smart Money Concepts: context, zones, confluence, scorer, validation
- `core/signal_engine.py` — scorer composite hiện hành; target tách TechnicalScore khỏi safety/macro gate
- `core/risk_engine.py` — scenarios, trade permission, contract size, RR
- `core/final_score_engine.py` — điểm tổng
- `core/decision_engine.py` — quyết định cuối (entry/stand aside...)
- `core/correlation_check.py` — điều chỉnh tương quan

**Scanner (bảng quét thị trường)**
- `core/scanner.py` — models + build scanner output
- `core/scanner_candidate_engine.py` — build candidate order payload
- `core/scanner_ranking_engine.py` — xếp hạng (READY_NOW / WAITING / WATCH / BLOCKED)
- `core/scanner_strategy_engine.py` + `scanner_strategy_router.py` — chọn chiến lược
- `core/scanner_ai_auditor.py` — AI audit setup
- `core/scanner_observability.py` / `scanner_performance.py` — theo dõi + hiệu năng
- `controllers/scanner_controller.py` — điều phối scan (thread pool)
- `workers/scanner_worker.py` — chạy scan nền
- `docs/scanner/technical-scoring-architecture.md` — scoring contract runtime hiện hành
- `docs/scanner/scanner-architecture.md` — **kiến trúc đích đã chốt**:
  TechnicalScore 4 thành phần, MarketSafetyGate, MacroGate và direct cutover

**Vào lệnh MT5 (auto-entry)**
- `core/entry_engine.py` — logic vào lệnh
- `core/execution_*_engine.py` — readiness, quality, revalidation
- `core/account_guard.py` — bảo vệ tài khoản
- `core/portfolio_risk_engine.py` — rủi ro danh mục

**Quản lý lệnh (order management — BE/trailing stop)**
- `core/order_management_state_machine.py` — **state machine thuần** (không biết MT5/Qt/persistence): nhận snapshot broker → trả `DesiredAction` (modify SL)
- `services/order_management_service.py` — **cầu nối duy nhất** giữa state machine và MT5: thread-safe, mọi broker call chạy trên 1 serial executor, Qt timer chỉ lên lịch
- `services/order_management_models.py` — contract broker: phân biệt rõ snapshot rỗng vs query lỗi (`SnapshotStatus`, `OperationStatus`, `AccountTradeMode`)
- `services/order_management_state_store.py` — persist trạng thái quản lý lệnh
- `ui/screens/orders_screen.py` — hiển thị lệnh (render snapshot cache, không block GUI)

**Journal (nhật ký giao dịch)**
- `services/journal_service.py` + `journal_models.py` + `journal_converters.py`
- `core/journal_feedback_engine.py` — phản hồi từ journal
- `controllers/journal_controller.py` + `ui/screens/journal_*.py`

**AI**
- `services/ai_service.py` — facade AI
- `services/ai/provider_adapter.py` + `providers/*.py` — adapter từng provider (openai, anthropic, gemini, deepseek, openai_compatible)
- `services/ai_provider_catalog_service.py` — catalog provider

**Dữ liệu thị trường**
- `services/mt5_service.py` — MT5
- `services/market_data_service.py` + `data_provider.py` + `candle_history_cache.py`
- `services/yahoo_chart_fetcher.py` — Yahoo fallback
- `services/forex_factory_client.py` + `macro_*` — tin tức/vĩ mô

**Tin tức (tầng dữ liệu) — IMPLEMENTED, READY-FOR-CONNECT (nghiệm thu 23/09/2026; contract [`news/news-architecture.md`](../news/news-architecture.md))**
- `services/news_repository.py` — điểm truy cập duy nhất (đọc + ghi) vào `news.db`
- `services/news_producers/ff_calendar_producer.py` — bộ sản xuất sự kiện lịch kinh tế ForexFactory (lượt tự động khi khởi động / nút "Lấy lịch kinh tế" + "Cập nhật actual" / lookup actual theo yêu cầu — không poll)
- `services/news_producers/rss_producer.py` — bộ sản xuất tin văn bản (headline, phát biểu chính thức)
- `services/news_producers/fred_rate_producer.py` — bộ sản xuất quan sát lãi suất FRED (hấp thụ `interest_rate_service.py` — file cũ bị xóa tại đấu nối vĩ mô)
- `controllers/news_controller.py` — điều phối lịch producer, nhập tay, lời gọi AI nhận định
- `core/news_models.py` — mô hình miền có kiểu của miền Tin tức (`CalendarEvent`, `NewsItem`, `RateObservation`, `TrendVerdict`, `IngestRun`, `StoreState`)
- `core/news_freshness.py` — phân loại trạng thái dữ liệu (`scheduled/released/stale`, `fresh/degraded/unavailable`)
- `core/rate_trend.py` — dẫn xuất trend lãi suất (hike/cut/hold) từ hai quan sát gần nhất
- `core/trend_prompt_builder.py` + `core/trend_verdict_parser.py` — contract AI nhận định xu hướng (chỉ tư vấn, không tham gia bất cứ quy trình nào)
- `ui/screens/news_screen.py` — màn Quản lý tin
- Chính sách vận hành: `config/news_policy.json` — nguồn duy nhất của mọi con số vận hành miền này (tài liệu trỏ về khóa, không chép giá trị — D5)

Nhóm module Tin tức thay thế dần `services/news_service.py` và
`services/forex_factory_client.py`; hai file cũ bị xóa khi di trú xong (ngoại lệ
E3 đã ghi trong Phụ lục B của [Quy tắc kiến trúc](architecture-rules.md)).

### Ghi chú

- **DI container:** mọi service/controller là singleton lazy trong `AppController` — thêm dependency mới thì đăng ký ở đó.
- **UI không gọi service trực tiếp** — đi qua controller/worker để giữ UI thread không bị block.
- **Truy vết thay đổi logic:** nhiều engine có hằng `*_VERSION` (SMC_DOMAIN_VERSION, PORTFOLIO_ENGINE_VERSION...) — khóa provenance máy đọc, thuộc ngoại lệ V3(a) của [Quy tắc kiến trúc](architecture-rules.md); không dùng làm tên tính năng.

## Kiến trúc tổng thể

Dự án dùng PyQt6 làm giao diện desktop. Biểu đồ tương tác được nhúng bằng `QWebEngineView`, còn core Python xử lý MT5, AI, indicator, scoring và quản trị rủi ro.

Không viết ứng dụng theo kiểu một file lớn. Phải chia module rõ ràng để dễ mở rộng, dễ bảo trì và dễ chuyển đổi sau này.

Mục tiêu kiến trúc:

* UI có độ hoàn thiện cao như một phần mềm desktop thật.
* Logic nghiệp vụ có thể test độc lập, không phụ thuộc PyQt6.
* Dễ thêm màn hình, thêm loại phân tích, thêm AI provider và thêm loại tài sản sau này.
* Dễ đóng gói thành bản cài đặt Windows và chuyển sang máy khác.

## Location runtime — đã nối, R5 đã duyệt (10/09/2026)

Phạm vi này theo [kiến trúc Scanner canonical](../scanner/scanner-architecture.md)
(nâng cấp Location đã hoàn tất — lịch sử trong Git), ưu tiên ứng dụng cá nhân
gọn. Các mô tả legacy bên dưới không thay thế contract canonical hoặc tạo thêm
yêu cầu backtest cho Location.

- Module thuần `core/location_engine.py` chứa model/config, dựng vùng H4,
  lifecycle, chọn vùng và tính raw/detail. Không phụ thuộc Qt, broker, mạng
  hoặc database.
- Adapter trong luồng Scanner chịu trách nhiệm chuẩn hóa dữ liệu, cutoff và
  truyền kết quả qua schema/snapshot hiện có. UI chỉ đọc kết quả, không tính lại.
- Vùng Location tách khỏi vùng technical/SMC dùng chung; không thay đổi logic
  Trend, Momentum, SMC, scenario, trọng số hoặc gate hiện có.
- Dùng nơi lưu snapshot/journal hiện tại cho detail nhỏ và version/config;
  không tạo database, service, replay engine hoặc cache Location riêng.
- Giới hạn cửa sổ nến; chỉ tối ưu thêm khi có số đo cho thấy chậm, không thêm
  hạ tầng dự phòng theo giả định.

Cutoff được đóng băng trước khi lấy history và đi xuyên packet → analysis →
snapshot. UI đọc detail versioned bằng template/semantic palette chung. Chưa có
nghiệm thu production smoke; broker không gửi lệnh trong smoke hiện tại.
Checkpoint rollback/config: `reports/scanner/location-r5-checkpoint.json`.

## Phạm vi symbol được hỗ trợ

Danh sách symbol chuẩn nằm trong `config/constants.py` tại `SUPPORTED_SYMBOLS`. Ứng dụng hiện hỗ trợ 31 mã:

* 28 cặp Forex chính/phụ.
* XAU/USD (vàng giao ngay so với USD).
* XAG/USD (bạc giao ngay so với USD).
* BTC/USD (Bitcoin so với USD).

Mapping từ symbol hiển thị của ứng dụng sang symbol thật của broker MT5 nằm trong `config/symbol_profiles.json`. Mapping phải hỗ trợ alias không hậu tố và alias có hậu tố phổ biến như `m`, `c`; ví dụ `XAGUSD`, `XAGUSDm`, `BTCUSD`, `BTCUSDm`. Nếu broker dùng hậu tố khác như `.r`, service MT5 phải dò theo tiền tố symbol đã chuẩn hóa trong Market Watch.

Các symbol đặc biệt không được dùng mặc định contract size Forex `100000`. Risk engine phải ưu tiên `trade_contract_size` từ MT5 cho XAU/USD, XAG/USD và BTC/USD; nếu broker không trả về giá trị hợp lệ thì dùng fallback theo cấu hình nội bộ.

## Vai trò từng phần

### `main.py`

Điểm khởi chạy ứng dụng.

Chỉ làm nhiệm vụ:

* Khởi tạo `QApplication`.
* Bật High DPI nếu cần.
* Khởi tạo logging và runtime paths.
* Load theme.
* Mở `MainWindow` bằng `showMaximized()` để app chiếm toàn bộ vùng làm việc của màn hình ở mọi kích thước và Windows scaling.

Không chứa logic nghiệp vụ.

### `config/`

Chứa cấu hình hệ thống:

* App name.
* Version.
* Default symbols.
* Timeframes.
* API config.
* MT5 config.
* UI constants.
* Đường dẫn dữ liệu theo môi trường qua `paths.py`.
* Currency drivers và symbol profiles dùng để sinh prompt phân tích cho từng cặp.

Không hard-code đường dẫn tuyệt đối trong code. Mọi đường dẫn runtime phải đi qua helper chung:

* Development: thư mục project.
* Packaged app: thư mục cài đặt cho asset readonly.
* User data: `%APPDATA%/ai-market-analyst/` cho settings, database, log và export.

### `core/`

Chứa logic nghiệp vụ độc lập với UI:

* Tính indicator.
* Chuẩn bị dữ liệu chart dạng JSON/payload thuần Python.
* Build prompt AI từ template, symbol profile và context đã tính.
* Phân tích tín hiệu.
* Tính vùng hỗ trợ/kháng cự.
* Tính supply/demand.
* Xác nhận trạng thái entry bằng `entry_engine.py`.
* Quản lý risk/reward.
* Chuẩn hóa dữ liệu thị trường.

`core/` không được import PyQt6, services hoặc widget UI.

Core không render chart và không sinh widget. Core chỉ trả dữ liệu sạch cho UI hoặc `QWebEngineView`.

`core/prompt_builder.py` chỉ ghép template + dữ liệu đã chuẩn hóa, không gọi API AI trực tiếp.

`core/entry_engine.py` là lớp xác nhận điểm vào lệnh thuần Python. Module này nhận `technical`, `smc`, nến H1 và `entry_zone`, sau đó trả về `entry_status`, `trigger_type`, `confirmation_score`, `invalid_reason`, `price_in_entry_zone`, `h1_confirmation` và `ready_to_trade`. UI, controller và AI không được tự đặt trạng thái này.

`core/trading_session_calendar.py` phân loại slot thiếu thành thời gian đóng
phiên, ngày lễ, broker maintenance hoặc gap thật. Policy theo Forex, kim loại
và crypto dùng timezone New York để tự xử lý DST; chỉ gap thật trong quality
scope mới làm validation không đủ điều kiện.

> **Backtest đã gỡ (2026-09-09):** Toàn bộ engine Backtest
> (`backtest_*`, `system_backtest_engine`, `monte_carlo`,
> `walk_forward_engine`) đã bị loại bỏ khỏi sản phẩm cùng tính năng Backtest.
> Chỉ còn vestigial `scanner_backtest_contract` (hạ tầng Scanner) và `vix_pair_*`
> (producer data VIX). Chi tiết: `product_spec.md` §3.2.

`core/technical_context.py` chứa `detect_market_regime()` — hàm phát hiện chế độ thị trường dùng hệ thống chấm điểm 3 thành phần (EMA alignment 0-40, structure 0-30, price position 0-30, tổng 0-100). Khắc phục vấn đề 80% lệnh rơi vào "unknown" của code cũ bằng cách chấp nhận mixed structure khi EMA đã rõ hướng, và nới lỏng ngưỡng phát hiện range.

Luồng phân tích phải lấy lịch tin kinh tế, headline vĩ mô mới nhất, macro theme theo đồng tiền và điểm nóng thế giới trong controller trước khi gọi `core.analysis_engine.analyze_symbol()`. Controller đưa `news_in_3h`, `high_impact_event_within_30m`, `next_high_impact_event` và `resume_after` vào `data_quality`; đồng thời đưa `macro_alignment_scores` vào `analysis_engine` để macro thật sự tham gia `scenario_scores`.

> **Runtime và kiến trúc đã chốt (11/08/2026):** Đoạn trên mô tả code
> hiện hành của Scanner. Kiến trúc Scanner đã được phê duyệt:
> `TechnicalSignalScore` chỉ gồm Trend, Momentum, Location và SMC; Macro và Risk
> trở thành gate/assessment độc lập, không cộng hoặc trừ điểm. Scanner đã cutover
> trực tiếp, không chạy dual scoring/shadow.
> Xem [`scanner-architecture.md`](../scanner/scanner-architecture.md).

> **Đang thay thế (E3, Owner duyệt 20/09/2026):** phần thu thập tin tức của
> `news_service.py` (lịch kinh tế, headline, phát biểu, cache đĩa) được thay
> bằng tầng dữ liệu Tin tức — database `news.db` là nguồn chân lý duy nhất,
> bộ sản xuất chỉ ghi, bên tiêu thụ chỉ đọc qua repository — theo
> [`news/news-architecture.md`](../news/news-architecture.md). Đoạn mô tả dưới
> đây còn hiệu lực với code đang chạy cho tới khi di trú xong và bị xóa cùng
> commit xóa code (D2); phần chấm điểm vĩ mô di trú ở ca sau, chưa đụng trong
> ca Tin tức.

`services/news_service.py` chịu trách nhiệm gom:

* Lịch kinh tế theo chuỗi fallback: Forex Factory JSON, Forex Factory HTML scrape nhẹ, file cache gần nhất, cuối cùng là `Calendar unavailable` kèm warning.
* Headline macro mới nhất từ RSS/search feed công khai.
* Phát biểu đáng chú ý trong 24h qua từ RSS/search feed công khai: Truth Social/Trump, quan chức Mỹ/Fed, thủ tướng Nhật, thủ tướng Anh và quan chức EU.
* Macro theme theo từng đồng tiền: hawkish, dovish hoặc neutral — xác định qua AI (có fallback keyword matching) hoặc keyword matching thuần nếu không có AI service.
* Macro theme cho XAU, XAG và BTC dựa trên real yields, DXY, risk sentiment, ETF/flow và catalyst liên quan từng tài sản.
* Điểm nóng thế giới liên quan risk-off, dầu, chiến sự, trừng phạt, tariff.
* **Macro alignment score 3 tầng (raw được clamp 0-30 khi compose):** T1 lãi suất & chính sách tiền tệ (0-12) — lãi suất tự động cập nhật từ FRED API (fallback về `config/interest_rates.json` nếu không có API key) + stance từ AI hoặc keyword; T2 giữ contract 0-10 nhưng runtime hiện luôn 5/5 directional-neutral và đưa event severity vào diagnostic/gate; T3 tâm lý rủi ro (0-8) + địa chính trị (0-4). Contribution vào signal còn được co theo `macro_confidence` dựa trên chất lượng/freshness dữ liệu.
* AI chỉ được dịch, tóm tắt và nhận định tác động dựa trên dữ liệu app đã lấy, không tự bịa headline, phát biểu hoặc sự kiện.

Nếu lịch kinh tế bị rate limit, ví dụ HTTP 429 từ Forex Factory, app không được làm mất toàn bộ macro context. `news_service.py` phải thử HTML calendar, sau đó dùng cache lịch kinh tế gần nhất nếu có, và ghi warning rõ ràng. Khi không có cache, `events` để rỗng nhưng `latest_headlines`, `latest_statements`, `macro_themes`, `geopolitical_hotspots` và `macro_alignment_scores` vẫn được trả về nếu nguồn headline còn hoạt động.

`services/market_data_service.py` chịu trách nhiệm cung cấp dữ liệu thị trường Mỹ cho correlation checking:

* Fetch DXY (`DX-Y.NYB`), VIX (`^VIX`), US10Y (`^TNX`), US2Y (`2YY=F`) qua cơ chế 2 tầng: `yfinance` → nếu lỗi/rỗng → gọi thẳng Yahoo Finance chart API bằng `requests`.
* Cache 30 phút để giảm số lần gọi mạng.
* Parse response thành `list[Candle]` chuẩn hóa cho `core/correlation_check.py`.

VIX có hai horizon tách biệt:

* live correlation context dùng số nến ngắn để chấm setup hiện tại;
* `scripts/run_vix_pair_backtest.py` là calibration runner riêng, tải daily
  `2y` cho `^VIX` và 31 symbol rồi dùng 252 common-date returns để tạo schema-2
  map. Runner không phải System Backtest và không tự bật scoring.

Đường Bước 7 là
`AdvancedSettings.vix_pair_aware_enabled → SettingsService → NewsService.data_quality_flags → AnalysisPipeline → correlation_check`.
Loader chỉ dùng data-backed map còn TTL, ưu tiên APPDATA rồi repo/bundled
fallback. Candidate seed/stale/legacy/malformed bị bỏ qua; chỉ flag OFF, không
còn candidate eligible hoặc pair non-actionable mới giữ VIX penalty phẳng.
Chi tiết và evidence hiện hành xem mục **Bước 7 — VIX Pair Sensitivity** trong
[`macro_score_architecture.md`](../macro/macro_score_architecture.md).

`services/interest_rate_service.py` chịu trách nhiệm cập nhật lãi suất ngân hàng trung ương:

* Tự động fetch từ FRED API (miễn phí, cần API key) cho 8 loại tiền tệ: USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF.
* Fallback về `config/interest_rates.json` nếu không có API key hoặc FRED lỗi.
* Cache 6 giờ để giới hạn 4 lần gọi/ngày.
* Tính trend (hike/cut/hold) từ 2 observation gần nhất.

Mọi lịch kinh tế hiển thị cho người dùng phải ưu tiên mẫu: `ngày-tháng-năm thời gian: nội dung tiếng Việt -> ảnh hưởng tới đồng tiền đang xét`. Mục Tin mới nhất chỉ giữ headline/phát biểu trong 24h trước và dùng mẫu `ngày-tháng-năm thời gian: nội dung tiếng Việt`; chỉ thêm phần `-> ảnh hưởng...` khi có nhận định tác động cụ thể từ AI hoặc rule heuristic. Nếu không xác định được tác động, không thêm câu chung chung.

### `services/`

Chứa kết nối bên ngoài:

* Nguồn dữ liệu thị trường (MT5 qua DataProvider).
* AI API.
* Tin tức.
* Telegram alert.
* File/database.
* Cache.
* Logging.
* Settings persistence.

### Hệ con AI (provider) và quản lý API key

* Hệ con AI tổ chức theo provider: `services/ai/provider_catalog.py` là registry
  tĩnh (`ProviderInfo`: tên, capability, model mặc định/khóa, adapter class);
  `services/ai/provider_adapter.py` định nghĩa `BaseProviderAdapter`
  (`generate()`, `generate_stream()`, `discover_models()`, `friendly_error()`,
  `validate_model()`); adapter cụ thể nằm trong `services/ai/providers/`
  (DeepSeek, OpenAI, Anthropic, Gemini, OpenAI-compatible) và tự đăng ký khi
  import.
* `services/ai_service.py` là dispatcher mỏng — nhận `AIProviderConfig`, tra
  adapter từ catalog, chuyển tiếp mọi lời gọi; không còn chuỗi if/elif theo
  provider. **Thêm provider mới = đăng ký `ProviderInfo` + import adapter**,
  không phải sửa `AIService` hay bất kỳ file nào khác.
* Provider có capability model discovery tự fetch danh sách model từ API
  (Gemini: `GET /v1beta/models`, OpenAI: `GET /v1/models`), cache 30 phút trong
  memory + disk (`cache/provider_runtime/{provider}.json`); khi API lỗi dùng
  disk cache (fallback offline).
* Mỗi adapter tự dịch lỗi REST thành thông báo tiếng Việt rõ ràng
  (`friendly_error()`): model deprecated, API key sai, quota...
* API key **không lưu plaintext** trong `settings.json`:
  `services/credential_service.py` bọc keyring hệ điều hành (Windows Credential
  Manager); `SettingsService` đọc/ghi key qua store này trong suốt, settings cũ
  chứa plaintext tự động migrate ở lần save đầu tiên.

### Auto-scan và Telegram Alert

Scanner hỗ trợ chạy một lần hoặc chạy theo chu kỳ do người dùng chọn: M5, M15, H1, H4. Interval mặc định lưu trong `settings.notifications.auto_scan_interval_minutes`; màn hình Scanner có thể override cho phiên quét hiện tại.

Khi mở tab Scanner lần đầu trong phiên, hệ thống tự động chọn tất cả mã (`SUPPORTED_SYMBOLS`), đặt chế độ quét tự động với interval M5, và chạy quét đầu tiên sau 1.5 giây. Auto-trade (tự động vào lệnh MT5) luôn mặc định OFF. Cờ `_auto_scanned_this_session` đảm bảo chỉ auto-scan đúng 1 lần mỗi phiên.

`services/telegram_alert_service.py` lọc detailed alert theo canonical
`candidate_status == READY_NOW` và trade plan hợp lệ. Alert chỉ là kênh thông
báo, không cấp quyền execution. Nội dung gồm mã giao dịch, broker symbol, hướng,
Entry, Stop loss, Take profit, lot gợi ý, R:R, setup score, lý do và vốn MT5
nếu có.

Services không được phụ thuộc trực tiếp vào widget UI.

### `workers/`

Chứa các tác vụ chạy nền để không làm đơ giao diện:

* Lấy dữ liệu.
* Phân tích AI.
* Refresh chart.
* Load news.
* Phân tích nhiều symbol cùng lúc.

Dùng `QThread`, `QRunnable` hoặc `QThreadPool` phù hợp.

Worker phải giao tiếp với UI bằng signal/slot, không cập nhật widget trực tiếp từ thread nền.

### `controllers/`

Chứa lớp điều phối giữa UI, workers và services.

Controller được phép:

* Nhận action từ màn hình.
* Validate input UI ở mức nhẹ.
* Gọi worker/service phù hợp.
* Chuyển kết quả thành view model cho UI.

Controller không được:

* Tính chỉ báo kỹ thuật.
* Tính điểm giao dịch.
* Chứa query SQL phức tạp.
* Import widget cụ thể nếu không cần thiết.

### `ui/`

Chỉ chứa giao diện.

UI được phép gọi controller/worker, nhưng không được tự xử lý logic phân tích phức tạp.

Chart tương tác trong UI dùng `QWebEngineView` để nhúng HTML/JavaScript chart. `QWebEngineView` chỉ nhận dữ liệu đã được core/service chuẩn bị, không tự tính indicator hoặc tín hiệu giao dịch.

### `ui/chart_bridge.py`

Chứa logic nối PyQt6 với chart web:

* Load HTML chart từ asset.
* Truyền dữ liệu chart vào JavaScript bằng JSON.
* Nhận event từ chart nếu cần, ví dụ chọn nến hoặc zoom range.
* Không gọi MT5, AI hoặc database trực tiếp.

### `ui/components/`

Chứa widget tái sử dụng.

Mọi button, card, toolbar, header, loading state và empty state nên dùng component chung.

### `ui/screens/`

Mỗi màn hình nằm trong một file riêng.

Mỗi screen chỉ quản lý layout và interaction của màn hình đó.

Các màn hình chính trong ứng dụng:

* `dashboard_screen.py`: Bảng điều khiển, trạng thái MT5, AI, Broker dạng card.
* `scanner_screen.py`: Quét thị trường và bảng xếp hạng. Tự động chạy quét lần đầu khi mở tab (tất cả mã, M5); nút auto-trade khả dụng trong auto-scan, mặc định unchecked và chỉ đặt `auto_trade_enabled=true` khi người dùng chủ động bật.
* `scanner_detail_screen.py`: Chi tiết một setup/analysis của symbol được quét — reason codes, cổng chặn, phân rã điểm số và vùng entry.
* `journal_screen.py`: Nhật ký giao dịch; tổng quan, thống kê và bộ lọc.
* `journal_detail_screen.py`: Chi tiết một giao dịch trong nhật ký.
* `orders_screen.py`: Quản lý lệnh/vị thế đang mở và trạng thái Order Management (SL/BE/trailing).
* `news_screen.py`: Quản lý tin — **IMPLEMENTED** (ca Tin tức, Bước 3): xem/lọc tin từ `news.db`, nhập/sửa tin tay, xuất/nhập file CSV-JSON, cửa sổ AI nhận định xu hướng (chỉ tham khảo). Contract dữ liệu: [`news/news-architecture.md`](../news/news-architecture.md); thiết kế màn hình: `ui/screen_design.md`.
* `settings_screen.py`: Cài đặt AI, dữ liệu MT5, giao dịch, hiển thị và nâng cao; gồm kill-switch VIX pair-aware mặc định OFF.

Nếu cần màn hình hoặc widget chart riêng, đặt dưới dạng component/view phụ và dùng `QWebEngineView`; không thay thế màn hình kết quả phân tích.

### `data/migrations/`

Chứa migration SQLite có version rõ ràng.

Không sửa trực tiếp schema bằng code rải rác. Khi thay đổi database phải thêm migration mới để app cũ có thể nâng cấp dữ liệu an toàn.

### `packaging/`

Chứa script đóng gói và ghi chú release.

Mọi asset cần dùng khi đóng gói như icon, font, QSS, sample config và migration phải được liệt kê trong spec/script.

## Scanner runtime hiện hành

Tài liệu kiến trúc Scanner **duy nhất**:
[`scanner/scanner-architecture.md`](../scanner/scanner-architecture.md) —
contract runtime live từ 15/08/2026. Luồng chi tiết:
[`scanner/scanner-flow.md`](../scanner/scanner-flow.md); chấm điểm:
[`scanner/technical-scoring-architecture.md`](../scanner/technical-scoring-architecture.md).

Các sự kiện vận hành then chốt:

* Mọi bước phân tích/triển khai Scanner phải được cập nhật vào
  `scanner-architecture.md` **trước khi** sửa code (D1).
* Rollout machinery cũ (stage ladder, kill switch, canary/readiness) đã bị gỡ
  hoàn toàn ngày 15/08/2026 theo quyết định của Owner (phần mềm cá nhân, chạy
  thật trực tiếp). **Không còn kill switch phần mềm**; dừng khẩn cấp = tắt
  feature flag, đóng lệnh ở terminal broker hoặc ngắt kết nối MT5. Không một
  feature flag hay nút UI nào được bỏ qua guard chain thực thi còn lại.
* Order policy owner-accepted (live), tài khoản real được phép; lệnh chỉ đi qua
  khi policy `certified()` và toàn bộ execution guard chain đạt. Trạng thái thực
  tế trên máy: [`runtime-status.md`](runtime-status.md).
* Auto order và manual order đều đi qua **shared execution boundary**
  (`ScannerController.execute_order_candidate()`) với cùng một guard chain,
  không có override riêng. `ScannerScreen.AUTO_TRADE_UI_ENABLED=true` cho phép
  bật auto-entry ở chế độ quét định kỳ; nút mặc định unchecked và bị reset khi
  chuyển sang quét một lần.

## Quản lý lệnh (BE/trailing stop)

Contract và thiết kế đầy đủ:
[`trading/order-management-contract.md`](../trading/order-management-contract.md).

Tinh thần kiến trúc: broker DTO, state machine thuần và persistence
account-scoped tách khỏi widget. Snapshot typed phân biệt `AVAILABLE` với
`UNAVAILABLE`; SL/TP và close chỉ thành công sau postcondition broker; state
machine giữ invariant BUY/Bid, SELL/Ask, BE trước trailing, TP không đổi và SL
không dời lùi.

`AppController` sở hữu `OrderManagementService` ở application scope. MT5 I/O
chạy qua single-executor/serialization boundary; Scanner reconcile rồi register
position broker; Orders UI đọc cache và nhận Qt signal; shutdown persist/flush
state trước khi disconnect MT5. Pending/manual/bulk action cũng dùng service với
broker postcondition.

## Nguyên tắc dependency

Luồng phụ thuộc đúng:

```text
UI -> Controllers -> Workers -> Services -> Core
```

Không cho phép:

```text
Core -> UI
Services -> UI
Core -> Services
Core -> PyQt6
Core -> QWebEngineView
```

`core/` chỉ được dùng Python thuần và thư viện tính toán cần thiết như pandas/numpy.

`QWebEngineView` thuộc UI layer. Nếu chart cần indicator, dữ liệu indicator phải được tính trước trong `core/indicators.py` rồi truyền sang chart bằng payload.

## Nguyên tắc xử lý tác vụ nặng

Không chạy tác vụ nặng trực tiếp trong main UI thread.

Các việc sau phải đưa vào worker:

* Gọi AI API.
* Lấy dữ liệu MT5.
* Tính toán dữ liệu lớn.
* Load tin tức.
* Phân tích nhiều symbol cùng lúc.

UI phải luôn có trạng thái loading, progress, cancel hoặc retry phù hợp cho tác vụ dài.

## Nguyên tắc dữ liệu runtime

Phân biệt rõ:

* App assets: icon, font, QSS, sample data; readonly sau khi đóng gói.
* User data: settings, API key metadata, journal database, news database (`news.db` — tầng dữ liệu Tin tức, READY-FOR-CONNECT 23/09/2026), exports (gồm kết xuất tin tức), logs; nằm trong `%APPDATA%/ai-market-analyst/`.
* Cache: dữ liệu tạm có thể xóa được.
* VIX sensitivity: mutable map nằm trong app-data và được ưu tiên; validated
  `data/vix_pair_sensitivity.json` trong package là readonly fallback. Map hết
  TTL hoặc không eligible không được tác động scoring.

Không lưu database, log hoặc settings vào thư mục cài đặt ứng dụng khi đã đóng gói.

## Nguyên tắc logging và lỗi

Ứng dụng phải có logging thống nhất:

* Log file xoay vòng theo dung lượng hoặc theo ngày.
* Không ghi API key hoặc dữ liệu nhạy cảm vào log.
* Lỗi kỹ thuật đầy đủ nằm trong log.
* UI chỉ hiển thị thông báo ngắn, rõ nguyên nhân và có hành động tiếp theo.

## Nguyên tắc đóng gói

Giữ code tương thích đóng gói Windows:

* Không phụ thuộc current working directory.
* Không đọc asset bằng relative path trực tiếp.
* Không yêu cầu user tự chạy command phức tạp sau khi cài.
* Có kiểm tra MT5 terminal, Python package MetaTrader5, Visual C++ runtime nếu cần.
* Có bản build chạy được bằng double click.
* Có checklist test trên máy sạch hoặc Windows user profile mới.
* Bundle validated `data/vix_pair_sensitivity.json`; calibration runner hiện
  chưa được bundle nên packaged UI chưa tự revalidate được.
