# ARCHITECTURE.md

## Kiến trúc tổng thể

Dự án dùng PyQt6 làm giao diện desktop. Biểu đồ tương tác được nhúng bằng `QWebEngineView`, còn core Python xử lý MT5, AI, indicator, scoring và quản trị rủi ro.

Không viết ứng dụng theo kiểu một file lớn. Phải chia module rõ ràng để dễ mở rộng, dễ bảo trì và dễ chuyển đổi sau này.

Mục tiêu kiến trúc:

* UI có độ hoàn thiện cao như một phần mềm desktop thật.
* Logic nghiệp vụ có thể test độc lập, không phụ thuộc PyQt6.
* Dễ thêm màn hình, thêm loại phân tích, thêm AI provider và thêm loại tài sản sau này.
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
    backtest_candidate_ledger.py
    backtest_contract.py
    backtest_execution.py
    backtest_execution_parity.py
    backtest_feedback.py
    backtest_market_data.py
    backtest_provenance.py
    backtest_migration.py
    backtest_golden_replay.py
    backtest_release.py
    backtest_statistics.py
    backtest_validation_replay.py
    system_backtest_engine.py
    walk_forward_engine.py
    monte_carlo.py
    smc_context.py
    risk_engine.py
    technical_context.py
    final_score_engine.py
    decision_engine.py
    trade_gate_engine.py
    correlation_check.py
    vix_pair_backtest.py
    account_guard.py
    journal_feedback_engine.py
    statistical_edge_engine.py
    execution_quality_engine.py
    reason_codes.py

  controllers/
    app_controller.py
    backtest_controller.py
    scanner_controller.py
    journal_controller.py
    settings_controller.py

  workers/
    base_worker.py
    scanner_worker.py
    backtest_worker.py

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

  ui/
    theme.py
    styles/
      base.qss
      dark.qss
      light.qss
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

  data/
    vix_pair_sensitivity.json
    migrations/
    seed/

  reports/
    vix_pair_sensitivity_2026-08-09.json

  scripts/
    run_vix_pair_backtest.py

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
* Replay/backtest trade plan bằng `backtest_engine.py`.
* Quản lý risk/reward.
* Chuẩn hóa dữ liệu thị trường.

`core/` không được import PyQt6, services hoặc widget UI.

Core không render chart và không sinh widget. Core chỉ trả dữ liệu sạch cho UI hoặc `QWebEngineView`.

`core/prompt_builder.py` chỉ ghép template + dữ liệu đã chuẩn hóa, không gọi API AI trực tiếp.

`core/entry_engine.py` là lớp xác nhận điểm vào lệnh thuần Python. Module này nhận `technical`, `smc`, nến H1 và `entry_zone`, sau đó trả về `entry_status`, `trigger_type`, `confirmation_score`, `invalid_reason`, `price_in_entry_zone`, `h1_confirmation` và `ready_to_trade`. UI, controller và AI không được tự đặt trạng thái này.

`core/backtest_engine.py` là lớp replay/backtest trade plan thuần Python. Module này mô phỏng các lần giá chạm `entry_zone` trên dữ liệu H1, sau đó đo `win_rate`, `expectancy_r`, `average_r`, `average_mfe_r`, `average_mae_r`, `max_drawdown_r`, hiệu quả theo symbol và theo session. Module này không gọi MT5, không gọi AI và không phụ thuộc PyQt6.

`core/backtest_feedback.py` đánh giá độ tin cậy của pattern nến (trigger_type) bằng cách quét lịch sử H1 tìm pattern tương tự. Dùng ATR để forward-test mỗi tín hiệu (3 nến tiếp theo), trả về `win_rate` và `confidence_adjustment` (+0.10 nếu win_rate >= 65%, -0.10 nếu < 40%).

`core/backtest_market_data.py` là lớp dữ liệu point-in-time của system
backtest. Module định nghĩa duration/close time D1/H4/H1/M15, chuẩn hóa UTC,
sort/deduplicate, lọc nến đã đóng theo `[start, end)`, kiểm tra coverage,
gap/OHLC và tạo `DataManifest` v2 có dataset hash cùng session-policy
fingerprint.

`core/trading_session_calendar.py` phân loại slot thiếu thành thời gian đóng
phiên, ngày lễ, broker maintenance hoặc gap thật. Policy theo Forex, kim loại
và crypto dùng timezone New York để tự xử lý DST; chỉ gap thật trong quality
scope mới làm validation không đủ điều kiện.

`core/backtest_execution.py` sở hữu execution policy có version của backtest:
confirmation-close fill, exit từ nến kế tiếp, gap fill tại open,
same-bar ambiguity policy, duration expiry/holding và event sequence. Module
không cho dùng high/low của nến fill để kết luận SL/TP.

`core/backtest_execution_parity.py` sở hữu mô hình chi phí MT5 xác định:
spread theo symbol/phiên, bid/ask, slippage entry/exit, commission, swap,
point-in-time quote conversion và volume step/min/max. Module xuất cost
manifest/fingerprint và tách gross/cost/net cho từng trade.

`core/backtest_candidate_ledger.py` sở hữu Candidate Ledger và
`FrozenStrategyConfig`. Ledger được tạo trước strategy filter, lưu
`setup_score` đúng side, rejection reasons và trade mô phỏng. Optimizer chỉ
nhận IS ledger và tạo config bất biến có ID xác định.

`core/backtest_validation_replay.py` điều phối validation theo đúng thứ tự:
chạy IS → tối ưu frozen config → khởi tạo lại trạng thái tài khoản → replay
OOS từ đầu. Output lưu fingerprint riêng cho IS/OOS ledger và chỉ expose
execution-parity OOS trades cho validator.

`core/backtest_statistics.py` tách bootstrap with replacement cho uncertainty
khỏi permutation without replacement cho sequence risk. Module trả CI,
probability of positive edge, one-sided p-value và sample-size guard.

`core/backtest_provenance.py` tạo manifest SHA-256 liên kết dataset, code
revision, request/risk config, scoring contract, frozen config và execution
contract; validator kiểm tra lại từng thành phần trước khi phát hành config.

`core/backtest_migration.py` tạo runtime view fail-closed cho snapshot đã lưu:
snapshot sai contract/engine được giữ để audit nhưng gắn `LEGACY_RESEARCH` và
không thể phát hành config.

`core/backtest_advanced.py` sở hữu policy cho workload nâng cao: mọi output là
`RESEARCH_ONLY`, portfolio không thể áp config đơn mã và Monte Carlo chỉ chạy
khi có tối thiểu 30 trade hoặc được yêu cầu rõ ràng.

`core/backtest_history.py` là data loader dùng chung cho Backtest và parameter
sweep, thống nhất warm-up, cache giới hạn và fallback chia đoạn M15.

`core/backtest_golden_replay.py` là replay nhỏ, broker-free trên fixture cố
định. `core/backtest_release.py` ghép ba bằng chứng phát hành: golden replay,
shadow engine cũ/mới và đối soát forward demo. Release report được ràng buộc
với dataset/provenance và nằm trong validation fingerprint.

Snapshot validation dùng để khóa config/dataset/provenance; snapshot forward
là một artifact riêng chạy frozen config trên cùng kỳ với tài khoản demo và
shadow legacy. Lệnh Scanner mang comment `AMA-FWD:*`; exporter chỉ nhận lịch
sử demo có correlation này để tránh ghép nhầm lệnh tay.

`core/system_backtest_engine.py` là engine backtest cấp hệ thống — replay toàn
bộ pipeline `analyze_symbol()` trên dữ liệu lịch sử. Mỗi quyết định chạy tại
thời điểm đóng nến step; snapshot chỉ nhận nến đa khung đã đóng và macro
context cũng được cắt point-in-time. Runtime hiện dùng một entry filter
thống nhất, rồi giả lập khớp lệnh qua M15 hoặc H1. Kết quả trả về
`BacktestResult` gồm summary, danh sách trade, equity curve, breakdowns,
diagnostics funnel, scoring/backtest contract và `DataManifest`. Engine còn
thu thập **pipeline diagnostics** từ mỗi snapshot qua
`_aggregate_pipeline_diag()` — gom thống kê pass/fail/warning từng bước
pipeline (validate, correlation, score, scenarios, direction, gate,
final_score) và đếm số lần mỗi gate chặn/cảnh báo.

`core/monte_carlo.py` tách bootstrap có hoàn lại để đo uncertainty của
expectancy/profit factor/win rate khỏi permutation không hoàn lại để đo
sequence drawdown/loss streak. Controller dùng 2.000 simulation và chỉ tự chạy
khi có ít nhất 30 trade; mẫu nhỏ được ghi `SKIPPED`, trừ khi người dùng yêu cầu
chạy rõ ràng trong khu vực nâng cao.

`core/walk_forward_engine.py` kiểm tra tính ổn định qua thời gian bằng
Walk-Forward Analysis. Mỗi cửa sổ tối ưu từ Candidate Ledger IS, khóa
`FrozenStrategyConfig`, rồi replay OOS bằng trạng thái tài khoản sạch. Báo
cáo lưu config của từng window, số candidate và lý do bị frozen strategy
loại; window dùng tháng lịch và `[start,end)`, còn aggregate khử trùng lặp
OOS theo trade identity trước khi tính `oos_is_expectancy_ratio` và
`robustness_score`.

`core/technical_context.py` chứa `detect_market_regime()` — hàm phát hiện chế độ thị trường dùng hệ thống chấm điểm 3 thành phần (EMA alignment 0-40, structure 0-30, price position 0-30, tổng 0-100). Khắc phục vấn đề 80% lệnh rơi vào "unknown" của code cũ bằng cách chấp nhận mixed structure khi EMA đã rõ hướng, và nới lỏng ngưỡng phát hiện range.

Luồng phân tích phải lấy lịch tin kinh tế, headline vĩ mô mới nhất, macro theme theo đồng tiền và điểm nóng thế giới trong controller trước khi gọi `core.analysis_engine.analyze_symbol()`. Controller đưa `news_in_3h`, `high_impact_event_within_30m`, `next_high_impact_event` và `resume_after` vào `data_quality`; đồng thời đưa `macro_alignment_scores` vào `analysis_engine` để macro thật sự tham gia `scenario_scores`.

> **Runtime và kiến trúc đã chốt (11/08/2026):** Đoạn trên mô tả code
> hiện hành của Scanner. Kiến trúc Scanner đã được phê duyệt:
> `TechnicalSignalScore` chỉ gồm Trend, Momentum, Location và SMC; Macro và Risk
> trở thành gate/assessment độc lập, không cộng hoặc trừ điểm. Scanner sẽ cutover
> trực tiếp, không chạy dual scoring/shadow. Đây vẫn là thiết kế non-runtime cho
> tới khi code và version được đổi. Xem
> [`scanner-architecture.md`](../scanner/scanner-architecture.md).

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

* Fetch DXY (`DX-Y.NYB`), VIX (`^VIX`), US10Y (`^TNX`), US2Y (`^IRX`) qua cơ chế 2 tầng: `yfinance` → nếu lỗi/rỗng → gọi thẳng Yahoo Finance chart API bằng `requests`.
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

### Auto-scan và Telegram Alert

Scanner hỗ trợ chạy một lần hoặc chạy theo khoảng thời gian do người dùng chọn: M5, M15, H1, H4. Interval mặc định lưu trong `settings.notifications.auto_scan_interval_minutes`; màn hình Scanner có thể override cho phiên quét hiện tại.

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

* `dashboard_screen.py`: Bảng điều khiển, trạng thái MT5, AI, Broker dạng card.
* `scanner_screen.py`: Quét thị trường và bảng xếp hạng. Tự động chạy quét lần đầu khi mở tab (tất cả mã, M5); nút auto-trade khả dụng trong auto-scan, mặc định unchecked và chỉ đặt `auto_trade_enabled=true` khi người dùng chủ động bật.
* `backtest_screen.py`: Backtest hệ thống trên dữ liệu lịch sử. Sử dụng
  QTabWidget 4 tab: Kết quả, Đường cong vốn, Danh sách lệnh và Nghiên cứu nâng
  cao. Form chính chọn Research/Validation, không còn checkbox IS/OOS hoặc
  Walk-Forward trùng nghĩa. Validation tự chạy execution parity, frozen IS/OOS
  và Walk-Forward theo `backtest-run-policy-v1`; research-fast chỉ có ở tab
  nâng cao và luôn `RESEARCH_ONLY`. Thanh nhanh chỉ hiển thị 5 KPI; policy
  `backtest-presentation-v1` đồng bộ symbol từ snapshot và khóa nút lưu/áp dụng
  theo lifecycle. Portfolio mặc định tắt và chỉ nhận toàn bộ mã khi người dùng
  bật chủ động; AI, Monte Carlo theo yêu cầu và sweep cũng chỉ nằm trong tab
  nâng cao.
* `journal_screen.py`: Nhật ký giao dịch.
* `settings_screen.py`: Cài đặt AI, dữ liệu MT5, giao dịch, hiển thị và nâng cao;
  gồm kill-switch VIX pair-aware mặc định OFF với cảnh báo chỉ bật sau backtest.

Nếu cần màn hình hoặc widget chart riêng, đặt dưới dạng component/view phụ và dùng `QWebEngineView`; không thay thế màn hình kết quả phân tích.

### `data/migrations/`

Chứa migration SQLite có version rõ ràng.

Không sửa trực tiếp schema bằng code rải rác. Khi thay đổi database phải thêm migration mới để app cũ có thể nâng cấp dữ liệu an toàn.

### `packaging/`

Chứa script đóng gói và ghi chú release.

Mọi asset cần dùng khi đóng gói như icon, font, QSS, sample config và migration phải được liệt kê trong spec/script.

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
* User data: settings, API key metadata, journal database, exports, logs; nằm trong `%APPDATA%/ai-market-analyst/`.
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

Ngay từ MVP phải giữ code tương thích đóng gói Windows:

* Không phụ thuộc current working directory.
* Không đọc asset bằng relative path trực tiếp.
* Không yêu cầu user tự chạy command phức tạp sau khi cài.
* Có kiểm tra MT5 terminal, Python package MetaTrader5, Visual C++ runtime nếu cần.
* Có bản build chạy được bằng double click.
* Có checklist test trên máy sạch hoặc Windows user profile mới.
* Bundle validated `data/vix_pair_sensitivity.json`; calibration runner hiện
  chưa được bundle nên packaged UI chưa tự revalidate được.

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

## Logic Updates (historical notes)

> Các bullet dưới đây ghi lại thay đổi tại thời điểm triển khai trước Scanner
> V2. Với Scanner, mọi giá trị threshold, branch, alert và execution phải theo
> mục “Scanner V2 — kiến trúc hiện hành” bên dưới.

- `risk_engine.build_trade_plan()` returns a wider `watch_zone` for monitoring and a narrower `entry_zone` for confirmation. Only the narrow `entry_zone` is passed to `core/entry_engine.py`; UI, controller and AI must not use `watch_zone` to set `ready_to_trade`.
- `core/backtest_engine.py` applies `cooldown_bars` after a trade exits before replaying another touch of the same setup zone, reducing duplicate trades during sideways price action.
- `core.analysis_pipeline.AnalysisPipeline` passes `entry_context` into the technical prompt payload so AI commentary can reference current price versus entry zone, stop loss, take profit and entry status.
- `core.scanner.scanner_row_from_analysis()` computes `price_vs_zone` for Scanner UI table visibility; Detail still keeps full `entry_status`.
- `core.analysis_engine.build_entry_checklist()` evaluates trend compatibility by scenario side and allows range setups only when the POI/location quality is strong enough.
- `core.smc_context._smc_for_timeframe()` uses `lookback=5` for swing detection. If no swings are found (common in strongly trending markets), it automatically falls back to `lookback=2` and sets `swing_source = "fallback"` in the output. Normal markets use `swing_source = "standard"`.
- `core.risk_engine._find_nearest_swing_for_sl()` and `_find_nearest_swing_for_tp()` collect all swing candidates from both H4 and H1 before selecting the one closest to price. Previously they returned the first H4 candidate without checking H1.
- `core.smc_context` defines 30 module-level constants (e.g. `_LOOKBACK_WINDOW = 80`, `_ZONE_SCORE_STRONG = 75`, `_PD_THRESHOLD = 0.05`) replacing 51 hardcoded magic numbers. Duplicated values (`80`×3, `0.05`×2, `3`×10) are now unified under single constants. Downstream modules (`signal_engine.py`, `risk_engine.py`) can import these constants instead of re-hardcoding the same thresholds.
- `core.risk_engine` defines 10 module-level constants (including `_TP_SELECTION_AGGRESSIVENESS = 0.5` for conservative TP selection and `_ENTRY_AGGRESSIVENESS = 0.0` for display) for Entry/SL/TP parameters (e.g. `_MIN_STOP_DISTANCE_ATR_MULT = 0.20`, `_WATCH_ZONE_OFFSET_ATR = 0.10`, `_SL_FLOOR_BUFFER_ATR = 0.20`). The previously ambiguous `atr * 0.10` (used for 3 different purposes) is now split into 3 distinct constants: `_ZONE_SL_BUFFER_ATR`, `_WATCH_ZONE_OFFSET_ATR`, `_SL_FLOOR_BUFFER_ATR`.
- `core.risk_engine.build_trade_plan()` SL priority: **swing structural → preferred zone boundary → ATR/zone-based**. Swing search (`_find_nearest_swing_for_sl`) runs unconditionally first regardless of whether an SMC preferred zone exists; falling back to zone boundary only when no suitable swing is found. Two guards enforce min distance: floor guard (SL ≥ entry_zone_edge ± 0.20×ATR) and min-distance guard (entry_for_rr→SL ≥ 0.20×ATR for SMC, 0.50×ATR for technical).
- `core.entry_engine` defines 8 module-level constants (e.g. `_NEAR_ZONE_ATR_MULT = 0.5`, `_ZONE_BROKEN_ATR_MULT = 0.25`, `_M15_DISPLACEMENT_THRESHOLD = 0.3`). An `UnboundLocalError` bug in `evaluate_entry()` (variable `internal_structure` used before assignment in early-return paths) and a missing kwarg bug (parameter accidentally embedded in a string) were fixed.
- `core.analysis_engine.confidence_reason()` includes component score breakdowns, SMC reason and macro/news context so score confidence is explainable from rule-engine data.
- `core.decision_engine.make_final_decision()` accepts per-symbol `thresholds`
  with `ready`, `watch`, `wait`, `min_score_gap` and `min_rr`. Scanner builds
  these qua `analysis_thresholds_for_symbol()` để giữ Decision Engine độc lập
  với strategy config backtest.
- `config.settings.SymbolScanSettings` stores per-symbol decision thresholds:
  `decision_ready` (default 65), `decision_watch` (default 60),
  `decision_wait` (default 55), cùng `min_expected_rr` (default 1.3).
- `core.risk_engine.build_trade_plan()` includes a **TP1 zone guard** after the 4-tier cascade: TP1 must be strictly outside the entry zone (`> entry_high` for BUY, `< entry_low` for SELL). Without this guard, a resistance/support zone inside the entry zone could be selected as TP1 when `entry_aggressiveness < ~0.32` — producing a take-profit target that hasn't left the entry zone. The guard rejects TP1 and allows the cascade to fall through; if no valid TP is found, the plan is cancelled rather than created with a bogus target.
- `core.risk_engine.build_trade_plan()` includes a **TP2 minimum gap guard**: TP2 must be at least `_TP2_MIN_GAP_ATR` (0.15 × ATR) away from TP1. `next_target()` finds the nearest S/R zone but previously had no distance floor, so a resistance/support zone just 0.4 pips from TP1 could be selected as TP2 — producing two take-profit targets that are effectively identical. The guard runs after both `next_target` and the Fib 0.618 fallback; if the gap is too small, TP2 is set to None (plan proceeds with TP1 only).
- `ui.main_window.MainWindow` có nút "🔄 Khởi động lại" trong sidebar footer (dưới dòng "Dữ liệu: MT5..."). Khi bấm: hiện QMessageBox xác nhận Yes/No; nếu Yes → shutdown MT5, khởi chạy process mới bằng `subprocess.Popen` (hỗ trợ cả PyInstaller `sys.executable` và `python main.py`), `QApplication.quit()`. Logic nằm trong `_restart_app()`. Tham khảo `docs/ui/screen_design.md` phần Sidebar để biết vị trí UI.

## Scanner V2 — kiến trúc hiện hành (24/07/2026)

```text
UI / ScannerRequest
  → ScannerController
      → Analysis Pipeline
      → Candidate Engine
          → Side Evaluation
          → Strategy Router
          → Scan-time Execution Readiness
      → Canonical Ranking
      → Observability + Shadow V1/V2
      → Rollout Policy
      → Shared Execution Revalidation
      → MT5Service.place_market_order()
```

Các boundary bắt buộc:

- `core/scanner_models.py` định nghĩa domain model và version contract.
- `core/scanner_strategy_router.py` là nơi duy nhất chọn
  `BACKTEST_VALIDATED`, `DEFAULT_RULES` hoặc `BACKTEST_INVALID`.
- Decision thresholds 65/60/55 độc lập với min score/RR của backtest.
- Config backtest chỉ được thực thi khi `VALIDATED`, đúng schema/scorer/feature,
  còn hạn và đủ bằng chứng OOS/walk-forward/fingerprint.
- `core/scanner_candidate_engine.py` tạo canonical candidate decision với sáu
  status; UI không suy luận lại từ `scanner_action`.
- `core/scanner_ranking_engine.py` xếp hạng sau filter bằng thang 0–100.
  `opportunity_score` chỉ là compatibility alias.
- `controllers/scanner_controller.ScannerController.execute_order_candidate()`
  là shared execution boundary cho cả auto và manual Scanner order.
- Execution lấy snapshot MT5 mới, tính lại lot, kiểm tra news, giá/zone/SL/TP/RR,
  account và portfolio trước khi gọi `place_market_order`.
- RuntimeOrderPolicy (`config/scanner_order_policy.json`, loader fail-closed,
  event `ORDER_POLICY_FAULT`) quyết định `order_enabled` trước khi candidate có
  thể thực thi.
- Snapshot, full analysis, event JSONL và scan health được lưu trong
  app-data để replay/audit.

Rollout machinery cũ (stage ladder
`DISABLED → SHADOW → DEMO_LIMITED → DEMO_FULL → CANARY → PRODUCTION`, kill
switch, release/canary readiness) đã bị gỡ bỏ hoàn toàn khỏi codebase ngày
15/08/2026 theo quyết định của owner (phần mềm cá nhân, chạy thật trực tiếp).
Không còn kill switch phần mềm; dừng khẩn cấp = tắt feature flag, đóng lệnh ở
terminal broker hoặc ngắt kết nối MT5. Không một feature flag hoặc nút UI nào
được bỏ qua các guard thực thi còn lại.

Runtime hiện tại: order policy owner-accepted (live), feature flag V2 bật, tài
khoản real được phép. Lệnh chỉ đi qua khi policy `certified()` và toàn bộ
execution guard chain đạt. Xem `docs/architecture/runtime-status.md`.

`ScannerScreen.AUTO_TRADE_UI_ENABLED=true` cho phép bật auto-entry ở chế độ
quét định kỳ. Nút mặc định unchecked và bị reset khi chuyển sang quét một lần.
Auto order và manual order đều đi qua shared execution boundary, cùng một
guard chain, không có override riêng.

Xem chi tiết tại `docs/scanner/scanner-flow.md` và
`docs/scanner/technical-scoring-architecture.md`.

Kiến trúc Scanner là runtime hiện hành, chạy live từ 15/08/2026:
[`scanner-architecture.md`](../scanner/scanner-architecture.md). Mọi bước
phân tích/triển khai tiếp theo phải được cập nhật vào tài liệu này trước khi sửa
code.

## Implementation Addendum trước Scanner V2 (tham chiếu lịch sử)

> Hai mục Telegram/Auto-entry ngay dưới đây mô tả contract cũ. Chúng đã được
> thay thế bởi candidate status canonical và shared execution path ở mục trên
> (rollout policy cũ cũng đã bị gỡ bỏ ngày 15/08/2026).

### Telegram alert format

- `services/telegram_alert_service.py` sends detailed trade alerts only for scanner rows with `scanner_action == "ready"`, `trade_permission == "allowed"` and a matching trade plan in `analysis_result`.
- The detailed trade alert is Vietnamese with accents and bullet icons. It includes symbol, broker symbol, side, Entry, Stop loss, Take profit, suggested lot, R:R, setup score, reason, MT5 balance if present, and source.
- Detailed R:R uses base effective RR as the primary value when available, falls back to best effective RR, and keeps best nominal RR as a secondary reference. Current execution RR is not substituted into the alert.
- The scanner summary alert no longer lists watch symbols. It shows only scan time, number of scanned symbols, number of ready symbols, and ready symbols with Entry/SL/TP.
- Summary time is formatted as `dd-mm-yyyy HH:MM:SS`, for example `09-06-2026 10:30:07`.

### Auto-entry on MT5

- Auto-entry is enabled only when the Scanner is running in auto-scan mode and the user has turned on the `Tự động vào lệnh MT5` toggle button. One-shot scans never place orders automatically; a valid candidate can still be placed manually from its dialog.
- `ui.screens.scanner_screen.ScannerScreen` exposes a visible auto-entry toggle button. The button is disabled in one-shot mode, enabled in auto-scan mode, and highlighted when active.
- `ScannerScreen` sets `ScannerRequest.auto_trade_enabled=True` only when scan mode is auto and the auto-entry toggle button is on.
- `controllers.scanner_controller.ScannerController` executes auto trades after all rows are scanned, sorted and enriched.
- A row can be auto-traded only when canonical
  `scanner_candidate_decision.auto_trade_candidate=true`. Setup score,
  scenario, Gate, entry, R:R và payload phải cùng `selected_side`; không dùng
  lại `scanner_action`, `trade_permission` hoặc `best_side` legacy để tự suy
  luận quyền đặt lệnh.
- Risk is still controlled by the normal sizing path. The controller caps `request.risk_percent` to `settings.trading.max_risk_percent` before analysis and before auto-entry.
- Auto-entry recalculates volume from the latest MT5 balance, risk percent, entry/SL and quote-to-USD rate; `scenario.position_sizing.suggested_lot` is the fallback when execution-time conversion is unavailable.
- For each broker symbol, `MT5Service.has_open_position_or_order()` checks both open positions and pending orders. If any existing position/order exists for that symbol, the system skips auto-entry for that symbol.
- Immediately before execution, the controller retrieves live ask/bid with
  `MT5Service.get_live_price()`, re-checks the final `entry_zone` from the
  strict same-side scenario and calculates spread-adjusted current RR. Price
  outside that zone or current RR below `min_rr` causes an explicit skip.
  Manual order placement applies the same protection and blocks with a
  warning. `source_zone`, `watch_zone`, and opposite-side scenarios are never
  execution fallbacks.
- Auto-trade results include a `diagnostics` list; manual order data includes an `execution_guard` dict with price source, live/fallback price, entry-zone state, current RR and decision reason.
- `MT5Service.place_market_order()` sends a market order through the MetaTrader5 Python API:
  - BUY uses current `ask`.
  - SELL uses current `bid`.
  - SL comes from the trade plan.
  - TP uses the first item in `take_profit`.
  - The order comment is prefixed with `AMA`.
- Volume is normalized down to broker `volume_step`; if the normalized value is below broker `volume_min`, the order is skipped instead of increasing risk.
- Auto-entry results are returned in `output["auto_trade_results"]` with `enabled`, `attempted`, `opened`, `skipped`, `errors`, `orders`, `risk_percent`, and `diagnostics`.

### Order Management V2 — đã triển khai, chờ release validation (09/08/2026)

Order Management V2 tách broker DTO, state machine thuần và persistence
account-scoped khỏi widget. Snapshot typed phân biệt `AVAILABLE` với
`UNAVAILABLE`; SL/TP và close chỉ thành công sau postcondition broker; state
machine giữ invariant BUY/Bid, SELL/Ask, BE trước trailing, TP không đổi và SL
không dời lùi.

`AppController` hiện sở hữu `OrderManagementService` ở application scope. MT5
I/O chạy qua single-executor/serialization boundary; Scanner reconcile rồi
register position broker; Orders UI đọc cache và nhận Qt signal; shutdown
persist/flush state trước khi disconnect MT5. Pending/manual/bulk action cũng
dùng service với broker postcondition.

Targeted suite và full suite tích hợp đều xanh: targeted đạt **191 passed in
3.15s** trên 17 file; full suite đạt **2740 passed, 8 skipped, 17 xfailed,
5 warnings in 178.62s (179.5s wall)**.
Forward-demo/reconnect evidence vẫn chưa có, nên implementation chưa được coi là
live-safe hoặc GA. Kế hoạch và review triển khai đã được hợp nhất vào
[`order-management-contract.md`](../trading/order-management-contract.md); trạng
thái vận hành xem [`runtime-status.md`](runtime-status.md). Chi tiết lịch sử vẫn
có trong Git.

### Gemini API Migration (2026-07-17)

- **Lý do:** Google đã chuyển đổi model Gemini. `gemini-2.5-flash` và `gemini-2.5-pro` không còn khả dụng cho API Key mới (scheduled shutdown: October 16, 2026). Google khuyến nghị dùng `gemini-3.5-flash` (Stable) và `gemini-3.1-pro-preview`.
- **Model Discovery:** Mỗi provider tự implement `discover_models()` trong adapter. Gemini gọi `GET /v1beta/models`, OpenAI gọi `GET /v1/models`. Chỉ lọc model có `generateContent` (Gemini) hoặc `gpt-*/o*` prefix (OpenAI). Cache 30 phút trong memory + disk (`cache/provider_runtime/{provider}.json`).
- **Error Messages:** Mỗi adapter tự implement `friendly_error()` — parse lỗi REST API và hiển thị thông báo tiếng Việt rõ ràng cho HTTP 404 (model deprecated), 403 (API Key sai), 401, 429 (quota).
- **systemInstruction:** Gemini API call dùng `systemInstruction` field thay vì ghép system prompt vào user content.
- **Backward Compatible:** API Key cũ vẫn hoạt động. Cấu hình cũ (model 2.5) vẫn được chấp nhận trong settings (chỉ lỗi khi gọi API).

### Credential Service (2026-07-17)

- **API Key Storage:** API Key không còn lưu plaintext trong `settings.json`. Thay vào đó dùng `services/credential_service.py` — wrapper quanh `keyring` (Windows Credential Manager / WinVaultKeyring).
- **Transparent:** `SettingsService._load_ai_settings()` tự động populate `api_key` từ credential store khi load. `SettingsService.save()` tự động lưu key vào credential store và serialize bản sao không có plaintext ra disk.
- **Migration:** Settings cũ chứa `api_key` plaintext được tự động migrate sang credential store ở lần save đầu tiên sau khi nâng cấp. Không cần user can thiệp.
- **In-memory preserved:** `SettingsService.save()` tạo bản sao settings để serialize, không xóa `api_key` khỏi memory — runtime consumer không bị ảnh hưởng.

### Provider Runtime Architecture (2026-07-17)

Toàn bộ subsystem AI đã được refactor từ Model-Centric sang Provider-Centric:

- **Provider Catalog (`services/ai/provider_catalog.py`):** Static registry của tất cả provider. Mỗi provider có `ProviderInfo` (name, display_name, capabilities, default_models, locked_models, adapter_class). `ProviderCapability` IntFlag định nghĩa capability: CHAT, STREAM, MODEL_DISCOVERY, VISION, TOOL_CALLING, SYSTEM_PROMPT, REASONING, JSON_MODE, EMBEDDING, IMAGE_GEN. `capability_labels()` trả về nhãn tiếng Việt.
- **Provider Adapter (`services/ai/provider_adapter.py`):** `BaseProviderAdapter` ABC — mỗi provider implement: `generate()`, `generate_stream()`, `discover_models()`, `friendly_error()`, `validate_model()`. Shared HTTP helpers: `_post_json()`, `_chat_completion_payload()`, `_extract_chat_completion_text()`.
- **Concrete Adapters (`services/ai/providers/`):** `DeepSeekAdapter`, `OpenAIAdapter`, `AnthropicAdapter`, `GeminiAdapter`. Mỗi adapter tự đăng ký vào `provider_catalog` khi import.
- **AIService (`services/ai_service.py`):** Thin dispatcher — nhận `AIProviderConfig`, lookup adapter từ `provider_catalog`, delegate mọi call. Không còn if/elif chain.
- **Runtime Model Discovery:** Model không còn hard-code trong `ai_providers.json`. Mỗi provider có `MODEL_DISCOVERY` capability tự động fetch model từ API (Gemini: `GET /v1beta/models`, OpenAI: `GET /v1/models`). Cache 30 phút trong memory + disk (`cache/provider_runtime/{provider}.json`). Offline fallback: dùng disk cache khi API lỗi.
- **Settings UI:** Panel trái — danh sách provider (QListWidget). Panel phải — tên provider, capabilities, API key, model (editable combobox + icon ↻ refresh), test/save buttons. Tự động discovery sau khi test API key thành công.
- **Thêm provider mới:** Đăng ký `ProviderInfo` + import adapter → tự động xuất hiện trong UI. Không cần sửa `AIService`, `AIProviderCatalogService`, hay bất kỳ file nào khác.

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
- **Hero bar mở rộng**: thêm 5 chỉ số inline (Điểm, R:R kèm dải worst–best, Buy/Sell, Gap, Vĩ mô) ngay trên hero bar. R:R hiển thị dạng `1:5.6 (2.9–5.6)` — best case + khoảng dao động.
- **Panel "Số liệu giao dịch"** (`_refresh_trade_panel()`): QFrame cố định ở cột phải, hiển thị Entry zone, SL, TP, R:R (kèm dải worst–best từ `risk_reward_range`), Vĩ mô, Chế độ TT — tái sử dụng `_dialog_card_*()`.
- Scanner Detail resolves RR from the flat row first and falls back to the scenario matching `best_side`. Entry without a real TP1 is displayed as `N/A` with an explanatory note, not a fabricated RR.
- **Panel "Điểm phân tích"** (`_refresh_score_panel()`): QFrame cố định ở cột phải, hiển thị Điểm tốt nhất, Điểm cuối, Buy/Sell, Gap, M15, Quyền GD.
- Cả 2 panel đều có guard `if not self.row` → hiển thị `"—"`, không crash.

### 9. Dialog "Xem đầy đủ" upgrade — bỏ trùng lặp, thêm tooltip
- Bỏ 10 ô trùng lặp với tab Tổng quan (Điểm, Mua/Bán, Gap, R:R, SL, TP, Entry, Chế độ TT, Quyền GD, Vĩ mô).
- Giữ 6 ô còn lại, nhóm thành 2 khu vực có tiêu đề: "🔎 Ngữ cảnh mở rộng" (Vị trí giá, Nhóm scanner, M15, Vĩ mô) và "📔 Thống kê nhật ký" (Mẫu NK, Kỳ vọng NK).
- Thêm `setToolTip()` giải thích thuật ngữ cho từng ô.
- Cảnh báo `⚠️ Mẫu quá ít, kỳ vọng chưa đáng tin` khi sample_size < 20.
