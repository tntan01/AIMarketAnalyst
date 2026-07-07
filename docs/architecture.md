# ARCHITECTURE.md

## Kiến trúc tổng thể

Dự án dùng PyQt6 làm giao diện desktop. Biểu đồ tương tác được nhúng bằng `QWebEngineView`, còn core Python xử lý MT5, AI, indicator, scoring và quản trị rủi ro.

Không viết ứng dụng theo kiểu một file lớn. Phải chia module rõ ràng để dễ mở rộng, dễ bảo trì và dễ chuyển đổi sau này.

Mục tiêu kiến trúc:

* UI có độ hoàn thiện cao như một phần mềm desktop thật.
* Logic nghiệp vụ có thể test độc lập, không phụ thuộc PyQt6.
* Dễ thêm màn hình, thêm data provider, thêm AI provider và thêm loại tài sản sau này.
* Dễ đóng gói thành bản cài đặt Windows và chuyển sang máy khác.

## Phạm vi symbol được hỗ trợ

Danh sách symbol chuẩn nằm trong `config/constants.py` tại `SUPPORTED_SYMBOLS`. Ứng dụng hiện hỗ trợ 31 mã:

* 28 cặp Forex chính/phụ.
* XAU/USD (vàng giao ngay so với USD).
* XAG/USD (bạc giao ngay so với USD).
* BTC/USD (Bitcoin so với USD).

Mapping từ symbol hiển thị của ứng dụng sang symbol thật của broker MT5 nằm trong `config/symbol_profiles.json`. Mapping phải hỗ trợ alias không hậu tố và alias có hậu tố phổ biến như `m`, `c`; ví dụ `XAGUSD`, `XAGUSDm`, `BTCUSD`, `BTCUSDm`. Nếu broker dùng hậu tố khác như `.r`, service MT5 phải dò theo tiền tố symbol đã chuẩn hóa trong Market Watch.

Các symbol đặc biệt không được dùng mặc định contract size Forex `100000`. Risk engine phải ưu tiên `trade_contract_size` từ MT5 cho XAU/USD, XAG/USD và BTC/USD; nếu broker không trả về giá trị hợp lệ thì dùng fallback theo cấu hình nội bộ.

## Cấu trúc thư mục đề xuất

```text
ai-market-analyst/
  main.py
  requirements.txt
  README.md

  config/
    constants.py
    paths.py
    settings.py
    currency_drivers.json
    symbol_profiles.json
    ai_providers.json
    interest_rates.json

  core/
    market_models.py
    indicators.py
    chart_payload.py
    prompt_builder.py
    analysis_engine.py
    analysis_pipeline.py
    signal_engine.py
    entry_engine.py
    backtest_engine.py
    backtest_feedback.py
    system_backtest_engine.py
    smc_context.py
    risk_engine.py
    technical_context.py
    final_score_engine.py
    decision_engine.py
    trade_gate_engine.py
    correlation_check.py
    account_guard.py
    journal_feedback_engine.py
    statistical_edge_engine.py
    execution_quality_engine.py
    reason_codes.py

  controllers/
    backtest_controller.py
    scanner_controller.py

  workers/
    base_worker.py
    scanner_worker.py
    backtest_worker.py
    analyze_worker.py

  services/
    mt5_service.py
    ai_service.py
    news_service.py
    market_data_service.py
    interest_rate_service.py
    storage_service.py
    settings_service.py
    logging_service.py
    scanner_worker.py

  controllers/
    app_controller.py
    analysis_controller.py
    settings_controller.py

  ui/
    theme.py
    styles.qss
    main_window.py
    navigation.py
    chart_bridge.py

    components/
      app_button.py
      icon_button.py
      card.py
      stat_card.py
      toolbar.py
      section_header.py
      loading_state.py
      empty_state.py

    screens/
      dashboard_screen.py
      scanner_screen.py
      scanner_detail_screen.py
      backtest_screen.py
      journal_screen.py
      journal_detail_screen.py
      settings_screen.py

  assets/
    icons/
    fonts/
    chart/

  prompts/
    full_analysis_prompt.md
    sections/
      macro_flow.md
      behavior_model.md
      technical_smc.md
      output_schema.md

  data/
    migrations/
    seed/

  packaging/
    pyinstaller.spec
    build_windows.ps1
    installer_notes.md

  tests/
    test_indicators.py
    test_signal_engine.py
    test_risk_engine.py
    test_settings_service.py
```

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
* User data: `%APPDATA%/AI Market Analyst/` cho settings, database, log và export.

### `core/`

Chứa logic nghiệp vụ độc lập với UI:

* Tính indicator.
* Chuẩn bị dữ liệu chart dạng JSON/payload thuần Python.
* Build prompt AI từ template, symbol profile và context đã tính.
* Phân tích tín hiệu.
* Tính vùng hỗ trợ/kháng cự.
* Tính supply/demand.
* Xác nhận trạng thái entry bằng `entry_engine.py`.
* Replay/backtest trade plan bằng `backtest_engine.py`.
* Quản lý risk/reward.
* Chuẩn hóa dữ liệu thị trường.

`core/` không được import PyQt6, services hoặc widget UI.

Core không render chart và không sinh widget. Core chỉ trả dữ liệu sạch cho UI hoặc `QWebEngineView`.

`core/prompt_builder.py` chỉ ghép template + dữ liệu đã chuẩn hóa, không gọi API AI trực tiếp.

`core/entry_engine.py` là lớp xác nhận điểm vào lệnh thuần Python. Module này nhận `technical`, `smc`, nến H1 và `entry_zone`, sau đó trả về `entry_status`, `trigger_type`, `confirmation_score`, `invalid_reason`, `price_in_entry_zone`, `h1_confirmation` và `ready_to_trade`. UI, controller và AI không được tự đặt trạng thái này.

`core/backtest_engine.py` là lớp replay/backtest trade plan thuần Python. Module này mô phỏng các lần giá chạm `entry_zone` trên dữ liệu H1, sau đó đo `win_rate`, `expectancy_r`, `average_r`, `average_mfe_r`, `average_mae_r`, `max_drawdown_r`, hiệu quả theo symbol và theo session. Module này không gọi MT5, không gọi AI và không phụ thuộc PyQt6.

`core/backtest_feedback.py` đánh giá độ tin cậy của pattern nến (trigger_type) bằng cách quét lịch sử H1 tìm pattern tương tự. Dùng ATR để forward-test mỗi tín hiệu (3 nến tiếp theo), trả về `win_rate` và `confidence_adjustment` (+0.10 nếu win_rate >= 65%, -0.10 nếu < 40%).

`core/system_backtest_engine.py` là engine backtest cấp hệ thống — replay toàn bộ pipeline `analyze_symbol()` trên dữ liệu lịch sử. Module này cắt dữ liệu thành từng snapshot không có future leak, gọi `analyze_symbol()` với snapshot đó, rồi giả lập khớp lệnh qua M15. Hỗ trợ 5 chế độ vào lệnh: Strict, Balanced, Legacy, Research, Backtest. Kết quả trả về `BacktestResult` gồm summary, danh sách trade, equity curve, breakdowns theo 12 chiều (symbol, side, decision, score bucket, M15 quality, market regime, SMC zone score, liquidity sweep, displacement, CHOCH, RR bucket) và diagnostics funnel. Từ Phase 2, engine còn thu thập **pipeline diagnostics** từ mỗi snapshot qua `_aggregate_pipeline_diag()` — gom thống kê pass/fail/warning từng bước pipeline (validate, correlation, score, scenarios, direction, gate, final_score) và đếm số lần mỗi gate chặn/cảnh báo.

`core/technical_context.py` chứa `detect_market_regime()` — hàm phát hiện chế độ thị trường dùng hệ thống chấm điểm 3 thành phần (EMA alignment 0-40, structure 0-30, price position 0-30, tổng 0-100). Khắc phục vấn đề 80% lệnh rơi vào "unknown" của code cũ bằng cách chấp nhận mixed structure khi EMA đã rõ hướng, và nới lỏng ngưỡng phát hiện range.

Luồng phân tích phải lấy lịch tin kinh tế, headline vĩ mô mới nhất, macro theme theo đồng tiền và điểm nóng thế giới trong controller trước khi gọi `core.analysis_engine.analyze_symbol()`. Controller đưa `news_in_3h`, `high_impact_event_within_30m`, `next_high_impact_event` và `resume_after` vào `data_quality`; đồng thời đưa `macro_alignment_scores` vào `analysis_engine` để macro thật sự tham gia `scenario_scores`.

`services/news_service.py` chịu trách nhiệm gom:

* Lịch kinh tế theo chuỗi fallback: Forex Factory JSON, Forex Factory HTML scrape nhẹ, file cache gần nhất, cuối cùng là `Calendar unavailable` kèm warning.
* Headline macro mới nhất từ RSS/search feed công khai.
* Phát biểu đáng chú ý trong 24h qua từ RSS/search feed công khai: Truth Social/Trump, quan chức Mỹ/Fed, thủ tướng Nhật, thủ tướng Anh và quan chức EU.
* Macro theme theo từng đồng tiền: hawkish, dovish hoặc neutral — xác định qua AI (có fallback keyword matching) hoặc keyword matching thuần nếu không có AI service.
* Macro theme cho XAU, XAG và BTC dựa trên real yields, DXY, risk sentiment, ETF/flow và catalyst liên quan từng tài sản.
* Điểm nóng thế giới liên quan risk-off, dầu, chiến sự, trừng phạt, tariff.
* **Macro alignment score 3 tầng (0-30):** T1 lãi suất & chính sách tiền tệ (0-12) — lãi suất tự động cập nhật từ FRED API (fallback về `config/interest_rates.json` nếu không có API key) + stance từ AI hoặc keyword; T2 lịch kinh tế (0-10) dùng calendar events 72h; T3 tâm lý rủi ro & địa chính trị (0-8) dùng sentiment + hotspot count. Score được điều chỉnh theo `macro_confidence` (0.10-1.0) dựa trên chất lượng dữ liệu.
* AI chỉ được dịch, tóm tắt và nhận định tác động dựa trên dữ liệu app đã lấy, không tự bịa headline, phát biểu hoặc sự kiện.

Nếu lịch kinh tế bị rate limit, ví dụ HTTP 429 từ Forex Factory, app không được làm mất toàn bộ macro context. `news_service.py` phải thử HTML calendar, sau đó dùng cache lịch kinh tế gần nhất nếu có, và ghi warning rõ ràng. Khi không có cache, `events` để rỗng nhưng `latest_headlines`, `latest_statements`, `macro_themes`, `geopolitical_hotspots` và `macro_alignment_scores` vẫn được trả về nếu nguồn headline còn hoạt động.

`services/market_data_service.py` chịu trách nhiệm cung cấp dữ liệu thị trường Mỹ cho correlation checking:

* Fetch DXY (`DX-Y.NYB`), VIX (`^VIX`), US10Y (`^TNX`), US2Y (`2YY=F`) qua cơ chế 2 tầng: `yfinance` → nếu lỗi/rỗng → gọi thẳng Yahoo Finance chart API bằng `requests`.
* Cache 30 phút để giảm số lần gọi mạng.
* Parse response thành `list[Candle]` chuẩn hóa cho `core/correlation_check.py`.

`services/interest_rate_service.py` chịu trách nhiệm cập nhật lãi suất ngân hàng trung ương:

* Tự động fetch từ FRED API (miễn phí, cần API key) cho 8 loại tiền tệ: USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF.
* Fallback về `config/interest_rates.json` nếu không có API key hoặc FRED lỗi.
* Cache 6 giờ để giới hạn 4 lần gọi/ngày.
* Tính trend (hike/cut/hold) từ 2 observation gần nhất.

Mọi lịch kinh tế hiển thị cho người dùng phải ưu tiên mẫu: `ngày-tháng-năm thời gian: nội dung tiếng Việt -> ảnh hưởng tới đồng tiền đang xét`. Mục Tin mới nhất chỉ giữ headline/phát biểu trong 24h trước và dùng mẫu `ngày-tháng-năm thời gian: nội dung tiếng Việt`; chỉ thêm phần `-> ảnh hưởng...` khi có nhận định tác động cụ thể từ AI hoặc rule heuristic. Nếu không xác định được tác động, không thêm câu chung chung.

### `services/`

Chứa kết nối bên ngoài:

* Nguồn dữ liệu thị trường (MT5 & cTrader qua BaseDataProvider).
* AI API.
* Tin tức.
* Telegram alert.
* File/database.
* Cache.
* Logging.
* Settings persistence.

### Auto-scan và Telegram Alert

Scanner hỗ trợ chạy một lần hoặc chạy theo khoảng thời gian do người dùng chọn: 1 phút, 5 phút, 15 phút, 30 phút, 1 giờ, 4 giờ, 1 ngày. Interval mặc định lưu trong `settings.notifications.auto_scan_interval_minutes`; màn hình Scanner có thể override cho phiên quét hiện tại.

`services/telegram_alert_service.py` chỉ gửi alert khi row scanner có `scanner_action = ready`, `trade_permission = allowed` và còn `analysis_result` với trade plan tương ứng. Nội dung alert phải gồm mã giao dịch, broker symbol, hướng BUY/SELL, Entry, Stop loss, Take profit, lot gợi ý, R:R, điểm setup, lý do và vốn MT5 nếu có trong `position_sizing`.

Services không được phụ thuộc trực tiếp vào widget UI.

### `workers/`

Chứa các tác vụ chạy nền để không làm đơ giao diện:

* Lấy dữ liệu.
* Phân tích AI.
* Refresh chart.
* Load news.
* Backtest.
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

5 màn hình chính trong ứng dụng:

* `dashboard_screen.py`: Bảng điều khiển, trạng thái MT5/AI.
* `scanner_screen.py`: Quét thị trường, bảng xếp hạng, auto-trade.
* `backtest_screen.py`: Backtest hệ thống trên dữ liệu lịch sử. Sử dụng QTabWidget 3 tab: (1) "📊 Kết quả" — HTML thống kê tổng hợp + pipeline diagnostics, (2) "📈 Đường cong vốn" — QWebEngineView + Lightweight Charts hiển thị cumulative R (line xanh) và drawdown R (vùng đỏ), (3) "📋 Danh sách lệnh" — bảng trade với màu sắc (xanh=thắng, đỏ=thua, xám=hòa). Có banner kết luận nhanh (có edge/không), KPI 9 ô, dialog phân tích với bảng thống kê mở rộng, pipeline diagnostics, và AI nhận xét.
* `journal_screen.py`: Nhật ký giao dịch.
* `settings_screen.py`: Cài đặt AI, MT5, giao dịch, auto-trade theo cặp.

Nếu cần màn hình hoặc widget chart riêng, đặt dưới dạng component/view phụ và dùng `QWebEngineView`; không thay thế màn hình kết quả phân tích.

### `data/migrations/`

Chứa migration SQLite có version rõ ràng.

Không sửa trực tiếp schema bằng code rải rác. Khi thay đổi database phải thêm migration mới để app cũ có thể nâng cấp dữ liệu an toàn.

### `packaging/`

Chứa script đóng gói và ghi chú release.

Mọi asset cần dùng khi đóng gói như icon, font, QSS, sample config và migration phải được liệt kê trong spec/script.

### `prompts/`

Chứa prompt template dạng markdown.

Prompt không nên hard-code riêng cho từng cặp. Cách đúng:

```text
Base Prompt Template
+ Currency Drivers
+ Symbol Profile
+ Macro Snapshot
+ Technical/SMC Context do Python tính
+ Output Schema
= Prompt cuối gửi AI
```

AI service chỉ nhận prompt cuối từ `core/prompt_builder.py`.

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
* Backtest.
* Phân tích nhiều symbol cùng lúc.

UI phải luôn có trạng thái loading, progress, cancel hoặc retry phù hợp cho tác vụ dài.

## Nguyên tắc dữ liệu runtime

Phân biệt rõ:

* App assets: icon, font, QSS, sample data; readonly sau khi đóng gói.
* User data: settings, API key metadata, journal database, exports, logs; nằm trong `%APPDATA%/AI Market Analyst/`.
* Cache: dữ liệu tạm có thể xóa được.

Không lưu database, log hoặc settings vào thư mục cài đặt ứng dụng khi đã đóng gói.

## Nguyên tắc logging và lỗi

Ứng dụng phải có logging thống nhất:

* Log file xoay vòng theo dung lượng hoặc theo ngày.
* Không ghi API key hoặc dữ liệu nhạy cảm vào log.
* Lỗi kỹ thuật đầy đủ nằm trong log.
* UI chỉ hiển thị thông báo ngắn, rõ nguyên nhân và có hành động tiếp theo.

## Nguyên tắc đóng gói

Ngay từ MVP phải giữ code tương thích đóng gói Windows:

* Không phụ thuộc current working directory.
* Không đọc asset bằng relative path trực tiếp.
* Không yêu cầu user tự chạy command phức tạp sau khi cài.
* Có kiểm tra MT5 terminal, Python package MetaTrader5, Visual C++ runtime nếu cần.
* Có bản build chạy được bằng double click.
* Có checklist test trên máy sạch hoặc Windows user profile mới.

## Nguyên tắc phát triển từng bước

Ưu tiên thứ tự:

1. Tạo skeleton project.
2. Tạo config paths, logging và settings service.
3. Tạo theme, QSS và component chung.
4. Tạo MainWindow, Sidebar, TopBar và router.
5. Tạo Dashboard skeleton có trạng thái thật.
6. Tạo Settings screen và lưu cấu hình.
7. Tạo SQLite schema, migration và journal service.
8. Tích hợp MT5 qua service và worker.
9. Tích hợp indicator, scoring, risk engine.
10. Tạo currency drivers, symbol profiles và prompt builder.
11. Tích hợp AI provider và fallback.
12. Tạo Scanner, Journal, export JSON.
13. Viết test core/service.
14. Tạo script packaging và test build.
15. Tối ưu UI/UX.

Không code tất cả trong một lần.

## Logic Updates

- `risk_engine.build_trade_plan()` returns a wider `watch_zone` for monitoring and a narrower `entry_zone` for confirmation. Only the narrow `entry_zone` is passed to `core/entry_engine.py`; UI, controller and AI must not use `watch_zone` to set `ready_to_trade`.
- `core/backtest_engine.py` applies `cooldown_bars` after a trade exits before replaying another touch of the same setup zone, reducing duplicate trades during sideways price action.
- `controllers.analysis_controller.AnalysisController` passes `entry_context` into the technical prompt payload so AI commentary can reference current price versus entry zone, stop loss, take profit and entry status.
- `core.scanner.scanner_row_from_analysis()` computes `price_vs_zone` for Scanner UI table visibility; Detail still keeps full `entry_status`.
- `core.analysis_engine.build_entry_checklist()` evaluates trend compatibility by scenario side and allows range setups only when the POI/location quality is strong enough.
- `core.smc_context._smc_for_timeframe()` uses `lookback=5` for swing detection. If no swings are found (common in strongly trending markets), it automatically falls back to `lookback=2` and sets `swing_source = "fallback"` in the output. Normal markets use `swing_source = "standard"`.
- `core.risk_engine._find_nearest_swing_for_sl()` and `_find_nearest_swing_for_tp()` collect all swing candidates from both H4 and H1 before selecting the one closest to price. Previously they returned the first H4 candidate without checking H1.
- `core.smc_context` defines 30 module-level constants (e.g. `_LOOKBACK_WINDOW = 80`, `_ZONE_SCORE_STRONG = 75`, `_PD_THRESHOLD = 0.05`) replacing 51 hardcoded magic numbers. Duplicated values (`80`×3, `0.05`×2, `3`×10) are now unified under single constants. Downstream modules (`signal_engine.py`, `risk_engine.py`) can import these constants instead of re-hardcoding the same thresholds.
- `core.risk_engine` defines 8 module-level constants for Entry/SL/TP parameters (e.g. `_MIN_STOP_DISTANCE_ATR_MULT = 0.20`, `_WATCH_ZONE_OFFSET_ATR = 0.10`, `_SL_FLOOR_BUFFER_ATR = 0.10`). The previously ambiguous `atr * 0.10` (used for 3 different purposes) is now split into 3 distinct constants: `_ZONE_SL_BUFFER_ATR`, `_WATCH_ZONE_OFFSET_ATR`, `_SL_FLOOR_BUFFER_ATR`.
- `core.entry_engine` defines 8 module-level constants (e.g. `_NEAR_ZONE_ATR_MULT = 0.5`, `_ZONE_BROKEN_ATR_MULT = 0.25`, `_M15_DISPLACEMENT_THRESHOLD = 0.3`). An `UnboundLocalError` bug in `evaluate_entry()` (variable `internal_structure` used before assignment in early-return paths) and a missing kwarg bug (parameter accidentally embedded in a string) were fixed.
- `core.analysis_engine.confidence_reason()` includes component score breakdowns, SMC reason and macro/news context so score confidence is explainable from rule-engine data.
- `core.decision_engine.make_final_decision()` accepts per-symbol `thresholds` (dict with keys `ready`, `watch`, `wait`, `min_score_gap`) that override `DEFAULT_DECISION_THRESHOLDS` (80/65/50/10). Custom thresholds flow from `config.settings.SymbolScanSettings.decision_ready/watch/wait` → `ui.screens.scanner_screen` builds per-symbol dict → `ScannerRequest.thresholds` → `scanner_controller` passes to `analyze_symbol(thresholds=...)` → `AnalysisPipeline.execute()` → `make_final_decision(thresholds=...)`.
- `config.settings.SymbolScanSettings` stores per-symbol decision thresholds: `decision_ready` (default 80), `decision_watch` (default 65), `decision_wait` (default 50). These are loaded from JSON by `services.settings_service.SettingsService` with backward-compatible fallback to defaults when fields are missing.
- `core.risk_engine.build_trade_plan()` includes a **TP1 zone guard** after the 4-tier cascade: TP1 must be strictly outside the entry zone (`> entry_high` for BUY, `< entry_low` for SELL). Without this guard, a resistance/support zone inside the entry zone could be selected as TP1 when `entry_aggressiveness < ~0.32` — producing a take-profit target that hasn't left the entry zone. The guard rejects TP1 and allows the cascade to fall through; if no valid TP is found, the plan is cancelled rather than created with a bogus target.
- `core.risk_engine.build_trade_plan()` includes a **TP2 minimum gap guard**: TP2 must be at least `_TP2_MIN_GAP_ATR` (0.15 × ATR) away from TP1. `next_target()` finds the nearest S/R zone but previously had no distance floor, so a resistance/support zone just 0.4 pips from TP1 could be selected as TP2 — producing two take-profit targets that are effectively identical. The guard runs after both `next_target` and the Fib 0.618 fallback; if the gap is too small, TP2 is set to None (plan proceeds with TP1 only).
- `ui.main_window.MainWindow` có nút "🔄 Khởi động lại" trong sidebar footer (dưới dòng "Dữ liệu: MT5..."). Khi bấm: hiện QMessageBox xác nhận Yes/No; nếu Yes → shutdown MT5, khởi chạy process mới bằng `subprocess.Popen` (hỗ trợ cả PyInstaller `sys.executable` và `python main.py`), `QApplication.quit()`. Logic nằm trong `_restart_app()`. Tham khảo `docs/screen_design.md` phần Sidebar để biết vị trí UI.

## Current Implementation Addendum

### Telegram alert format

- `services/telegram_alert_service.py` sends detailed trade alerts only for scanner rows with `scanner_action == "ready"`, `trade_permission == "allowed"` and a matching trade plan in `analysis_result`.
- The detailed trade alert is Vietnamese with accents and bullet icons. It includes symbol, broker symbol, side, Entry, Stop loss, Take profit, suggested lot, R:R, setup score, reason, MT5 balance if present, and source.
- The scanner summary alert no longer lists watch symbols. It shows only scan time, number of scanned symbols, number of ready symbols, and ready symbols with Entry/SL/TP.
- Summary time is formatted as `dd-mm-yyyy HH:MM:SS`, for example `09-06-2026 10:30:07`.

### Auto-entry on MT5

- Auto-entry is enabled only when the Scanner is running in auto-scan mode and the user has turned on the `Tự động vào lệnh MT5` toggle button. Manual one-shot scans do not place orders.
- `ui.screens.scanner_screen.ScannerScreen` exposes a visible auto-entry toggle button. The button is disabled in one-shot mode, enabled in auto-scan mode, and highlighted when active.
- `ScannerScreen` sets `ScannerRequest.auto_trade_enabled=True` only when scan mode is auto and the auto-entry toggle button is on.
- `controllers.scanner_controller.ScannerController` executes auto trades after all rows are scanned, sorted and enriched.
- A row can be auto-traded only when it is a true ready setup: `scanner_action == "ready"`, `trade_permission == "allowed"`, `analysis_result` exists, and a scenario matching `best_side` exists.
- Risk is still controlled by the normal sizing path. The controller caps `request.risk_percent` to `settings.trading.max_risk_percent` before analysis and before auto-entry.
- Auto-entry uses `scenario.position_sizing.suggested_lot`, which is calculated from the MT5 account balance and configured risk percent.
- For each broker symbol, `MT5Service.has_open_position_or_order()` checks both open positions and pending orders. If any existing position/order exists for that symbol, the system skips auto-entry for that symbol.
- `MT5Service.place_market_order()` sends a market order through the MetaTrader5 Python API:
  - BUY uses current `ask`.
  - SELL uses current `bid`.
  - SL comes from the trade plan.
  - TP uses the first item in `take_profit`.
  - The order comment is prefixed with `AMA`.
- Volume is normalized down to broker `volume_step`; if the normalized value is below broker `volume_min`, the order is skipped instead of increasing risk.
- Auto-entry results are returned in `output["auto_trade_results"]` with `enabled`, `attempted`, `opened`, `skipped`, `errors`, `orders`, and `risk_percent`.

## Macro Upgrade (2026-07-05)

### 1. yfinance fallback — market data resilience
- `services/market_data_service.py` sử dụng cơ chế 2 tầng: `yfinance.download()` → nếu lỗi hoặc trả về empty → gọi thẳng Yahoo Finance chart API qua `requests`.
- `_fetch_via_requests()` parse JSON response từ `query1.finance.yahoo.com/v8/finance/chart/{ticker}` → `list[Candle]`.
- Cache TTL tăng từ 15 phút lên 30 phút để giảm tần suất gọi mạng.
- Log `logger.warning` rõ ràng mỗi khi dùng fallback.

### 2. Correlation expansion — XXX/USD pairs
- `core/correlation_check.py`: `_us10y_score()` và `_us2y_score()` mở rộng từ XAU/XAG/JPY sang tất cả cặp `XXX/USD` (EUR, GBP, AUD, NZD, CAD).
- Logic: US10Y/US2Y tăng → USD mạnh → SELL XXX/USD được thưởng (+1.5 với US10Y, +1.0 với US2Y); BUY bị phạt (-1.5 / -1.0).
- Chỉ áp dụng Tier 1 Directional, bỏ qua Tier 2 (absolute level) và Tier 3 (momentum) cho XXX/USD pairs.
- XAU/XAG/JPY giữ nguyên logic 3 tầng.

### 3. FRED API — auto-update interest rates
- `services/interest_rate_service.py` (file mới): tự động fetch lãi suất từ FRED API cho 8 loại tiền tệ.
- `news_service.py._load_interest_rates()` chuyển từ đọc file JSON tĩnh → gọi `get_latest_rates()`.
- `config.settings.AdvancedSettings` thêm `fred_api_key: str = ""` — để trống để dùng fallback JSON.
- Cache 6 giờ, tính trend (hike/cut/hold) từ chênh lệch 2 kỳ gần nhất.

### 4. AI stance analysis — hawkish/dovish
- `news_service.py._ai_currency_stance()`: dùng AI đọc headline và trả về "hawkish" / "dovish" / "neutral".
- Fallback về keyword matching (`currency_stance()` cũ) nếu không có AI service hoặc AI lỗi.
- Cache stance 30 phút theo `currency + hash(5 headlines đầu)` để tránh gọi AI lặp.
- `_compute_macro_tiers()` truyền `ai_service` xuống `_ai_currency_stance()`.
- `scanner_controller.run_market_scan()` tạo `AIService` từ settings và truyền qua `_fetch_one_symbol_mt5()` → `data_quality_flags()` → `latest_macro_context()`.

## Brave Search & Calendar Cache Fixes (2026-07-06)

### 5. Persistent calendar cache — tích lũy event quá khứ
- **Vấn đề:** `forex_factory_client._store_calendar_cache()` chỉ merge khi cùng ngày, ngày mới → overwrite toàn bộ cache. FF API `thisweek.json` chỉ trả event tương lai → `lookup_actuals_batch()` không bao giờ có event quá khứ để lookup actual.
- **Fix:** `_store_calendar_cache()` luôn merge với cache cũ (bỏ điều kiện `date == today_key`), thêm cleanup tự động event > 7 ngày. `CALENDAR_CACHE_MAX_AGE` tăng 12h → 24h.
- **Kết quả:** Event quá khứ được tích lũy qua các lần chạy → `lookup_actuals_batch()` có dữ liệu đầu vào → Brave Search tự động tra cứu actual values.

### 6. AI parse fallback — chống reasoning text lọt vào actual
- **Vấn đề:** `news_service._parse_with_ai()` trả về toàn bộ AI reasoning text (~500 ký tự) thay vì con số actual. DeepSeek model output thinking tokens trước answer → `_parse_fallback_regex()` không được gọi.
- **Fix:** Nếu `len(result) > 20` → AI đang trả về reasoning → fallback về `_parse_fallback_regex()` trích xuất số từ raw search text.
- **Kết quả:** Actual values được parse sạch (`-0.4%`, `-1.0%`, `-0.2%`) thay vì nguyên đoạn văn bản.

### 7. Scanner Detail cleanup — xóa dead code tab Tổng quan
- `ui/screens/scanner_detail_screen.py`: xóa `_cards_container` + 14 `InfoCard` ẩn (108 dòng) — widget được tạo từ `_build_ui()` nhưng không bao giờ hiển thị.
- Xóa `_refresh_cards()` method — populate card ẩn vô ích. Dialog `_show_scan_detail_dialog()` tạo card riêng bằng `_dialog_card_*()`.
- Chuyển `_refresh_entry_checklist()` thành lời gọi trực tiếp từ `_render()`, không qua `_refresh_cards()` trung gian.

### 8. Tab Tổng quan redesign — hiển thị trực tiếp không cần mở dialog
- **Hero bar mở rộng**: thêm 5 chỉ số inline (Điểm, R:R, Buy/Sell, Gap, Vĩ mô) ngay trên hero bar.
- **Panel "Số liệu giao dịch"** (`_refresh_trade_panel()`): QFrame cố định ở cột phải, hiển thị Entry zone, SL, TP, R:R, Vĩ mô, Chế độ TT — tái sử dụng `_dialog_card_*()`.
- **Panel "Điểm phân tích"** (`_refresh_score_panel()`): QFrame cố định ở cột phải, hiển thị Điểm tốt nhất, Điểm cuối, Buy/Sell, Gap, M15, Quyền GD.
- Cả 2 panel đều có guard `if not self.row` → hiển thị `"—"`, không crash.

### 9. Dialog "Xem đầy đủ" upgrade — bỏ trùng lặp, thêm tooltip
- Bỏ 10 ô trùng lặp với tab Tổng quan (Điểm, Mua/Bán, Gap, R:R, SL, TP, Entry, Chế độ TT, Quyền GD, Vĩ mô).
- Giữ 6 ô còn lại, nhóm thành 2 khu vực có tiêu đề: "🔎 Ngữ cảnh mở rộng" (Vị trí giá, Nhóm scanner, M15, Vĩ mô) và "📔 Thống kê nhật ký" (Mẫu NK, Kỳ vọng NK).
- Thêm `setToolTip()` giải thích thuật ngữ cho từng ô.
- Cảnh báo `⚠️ Mẫu quá ít, kỳ vọng chưa đáng tin` khi sample_size < 20.
