# Hướng dẫn code MVP

## Mục tiêu MVP

MVP phải là bản app desktop dùng thật được, không phải demo rời rạc.

MVP đạt yêu cầu khi:

* Có giao diện PyQt6 hoàn chỉnh với Dashboard, Single Analysis, Scanner, Journal và Settings.
* Có chart tương tác nhúng bằng `QWebEngineView`.
* Tách rõ UI, controller, worker, service và core.
* Chạy được khi thiếu MT5 hoặc AI bằng fallback rõ ràng.
* Có SQLite journal và settings local.
* Có test cho core logic quan trọng.
* Có script đóng gói Windows cơ bản.

## Giai đoạn 1: Skeleton và nền tảng

Tạo:

* `main.py`.
* `config/constants.py`.
* `config/paths.py`.
* `services/logging_service.py`.
* `services/settings_service.py`.
* `ui/main_window.py`.
* `ui/chart_bridge.py`.
* `ui/styles.qss`.

Tiêu chí đạt:

* App mở được cửa sổ chính.
* Có log file.
* Có user data dir.
* Không phụ thuộc current working directory.

## Giai đoạn 2: Theme và component

Tạo component dùng chung:

* `AppButton`.
* `IconButton`.
* `Card`.
* `StatCard`.
* `SectionHeader`.
* `Toolbar`.
* `LoadingState`.
* `EmptyState`.

Tiêu chí đạt:

* Không hard-code style rải rác.
* Các nút, card, spacing đồng nhất.
* UI chạy tốt ở 1366x768 và 1920x1080.

## Giai đoạn 3: Navigation và màn hình nền

Tạo:

* Dashboard.
* Single Analysis.
* Scanner.
* Journal.
* Settings.

Tiêu chí đạt:

* Chuyển màn hình bằng `QStackedWidget` hoặc router.
* Mỗi màn hình nằm trong file riêng.
* Có trạng thái empty/loading/error.

## Giai đoạn 4: Database và settings

Tạo:

* SQLite schema.
* Migration runner.
* Journal service.
* Settings service.

Tiêu chí đạt:

* Database tự tạo lần đầu.
* Có bảng schema version.
* Settings lưu ở user data dir.
* Không mất dữ liệu khi nâng schema.

## Giai đoạn 5: Core analysis

Tạo core thuần Python:

* Indicator.
* Chart payload.
* Market regime.
* Direction bias.
* Buy/sell scoring.
* Trade plan.
* Position sizing.

Tiêu chí đạt:

* Có unit test.
* Không import PyQt6.
* Không import `QWebEngineView`.
* Input/output dùng dataclass hoặc dict có schema rõ ràng.

## Giai đoạn 5.5: Chart web nhúng

Tạo:

* `assets/chart/index.html`.
* JavaScript chart tối giản hoặc thư viện chart được chọn.
* `core/chart_payload.py`.
* `core/entry_engine.py`.
* `core/backtest_engine.py`.
* `ui/chart_bridge.py`.
* Vùng chart `QWebEngineView` trong `single_analysis_result_screen.py` và `scanner_detail_screen.py`.

Tiêu chí đạt:

* Chart được nhúng trong PyQt6 bằng `QWebEngineView`.
* Chart nhận dữ liệu OHLCV/indicator từ core Python qua JSON.
* JavaScript chỉ render chart, không tính indicator, scoring, entry, SL, TP hoặc lot.
* Chart vẫn load được sau khi đóng gói `.exe`.

## Entry, news và SMC quality

* Controller phải lấy lịch tin kinh tế trước khi gọi `analyze_symbol()` và đưa `news_in_3h`, `high_impact_event_within_30m`, `next_high_impact_event`, `resume_after` vào `data_quality`.
* Controller cũng phải lấy headline vĩ mô mới nhất, macro theme theo đồng tiền, điểm nóng thế giới và `macro_alignment_scores`; sau đó truyền `macro_alignment_scores` vào `analyze_symbol()` để điểm buy/sell phản ánh bối cảnh vĩ mô.
* Macro headline phải có nguồn, tiêu đề, URL nếu có, thời gian UTC và tags. Nếu không lấy được nguồn, app phải ghi rõ không có dữ liệu thay vì tự bịa.
* Macro scoring chỉ được dựa trên dữ liệu app đã lấy: central bank stance, inflation/labor/yield/intervention/geopolitical tags. AI không được tự tạo Reuters poll, BOJ/Fed stance, intervention zone hoặc tin điểm nóng nếu không có trong payload.
* Khi lịch kinh tế bị HTTP 429/rate limit, app vẫn phải tiếp tục lấy headline macro và điểm nóng; thử Forex Factory HTML, dùng cache lịch kinh tế gần nhất nếu có, đồng thời hiển thị warning rõ. Không dùng cụm “dữ liệu AI nội bộ”.
* Calendar cache phải là lịch tổng hợp tuần này, lưu ra file trong thư mục cache runtime để phân tích nhiều mã không gọi lại Forex Factory liên tục.
* Tin mới nhất chỉ lấy các headline/phát biểu có thời gian công bố trong 24h trước. Dòng tin dùng mẫu `ngày-tháng-năm thời gian: nội dung tiếng Việt`; chỉ thêm `-> ảnh hưởng tới đồng tiền đang xét` khi AI hoặc rule heuristic có nhận định tác động cụ thể. Không hiển thị câu chung chung kiểu “Tác động cần được xác nhận thêm”.
* Lịch kinh tế hiển thị theo mẫu `ngày-tháng-năm thời gian: nội dung tiếng Việt -> ảnh hưởng tới đồng tiền đang xét`. AI chỉ được dịch/nhận định tác động từ dữ liệu app đã fetch, không tự tạo tin hoặc giờ công bố.
* `resume_after` do code tính, mặc định bằng thời điểm tin tác động cao cộng 30 phút. AI không được tự đặt hoặc tự sửa thời điểm này.
* `core/entry_engine.py` là nơi duy nhất xác nhận trạng thái entry. Module này trả về `entry_status`, `trigger_type`, `confirmation_score`, `invalid_reason`, `price_in_entry_zone`, `h1_confirmation`, `ready_to_trade`.
* `risk_engine.build_trade_plan()` chỉ coi lệnh là ready khi `ready_to_trade = true`. Nếu chưa xác nhận, vẫn có thể hiển thị `entry_zone` dưới dạng vùng theo dõi, nhưng không được trình bày như lệnh sẵn sàng.
* `smc_context.py` phải gắn metadata chất lượng cho supply/demand, order block và FVG: `zone_score`, `freshness_bars`, `mitigated`, `broken`, `test_count`, `displacement_multiple`, `liquidity_sweep`, `zone_location`.
* Rule Engine ưu tiên vùng chưa broken, còn fresh, ít bị test, có displacement rõ, có liquidity sweep và đúng premium/discount theo hướng lệnh.
* `core/backtest_engine.py` phải replay trade plan trên H1 và trả về `win_rate`, `expectancy_r`, `average_r`, `average_mfe_r`, `average_mae_r`, `max_drawdown_r`, `by_symbol`, `by_session`.
* Dashboard Market Overview dùng `yfinance` lấy DXY (`DX-Y.NYB`), VIX (`^VIX`), US10Y (`^TNX`) — không phụ thuộc MT5. Cập nhật bằng `QTimer` hoặc `refresh_status`.
* Màn hình kết quả phải hiển thị checklist entry gồm: Xu hướng, Vùng POI, Xác nhận H1, Tin tức, Spread, R:R, Lot. Mỗi mục phải có trạng thái đạt/chờ và ghi chú ngắn.
* Auto-scan trong Scanner phải dùng `QTimer` để hẹn lần quét tiếp theo sau khi worker hiện tại kết thúc; không chạy song song hai worker scan. Nút `Dừng quét tự động` phải dừng timer và không hủy ngang worker đang chạy.
* Telegram alert chỉ gửi cho setup thật sự sẵn sàng (`ready` + `allowed`). Tin nhắn phải dùng lot tính theo vốn MT5 hiện tại, không dùng vốn nhập tay nếu MT5 có balance hợp lệ.

## Giai đoạn 6: MT5 service và worker

Tạo:

* `mt5_service.py`.
* `mt5_worker.py`.
* Data quality model.

Tiêu chí đạt:

* Không làm đơ UI khi lấy dữ liệu.
* Báo rõ lỗi khi MT5 chưa mở, chưa login hoặc thiếu symbol.
* Không dùng dữ liệu fallback để tạo tín hiệu thực chiến.

## Giai đoạn 7: AI service và fallback

Tạo:

* AI provider adapter.
* Prompt builder.
* `config/currency_drivers.json`.
* `config/symbol_profiles.json`.
* `prompts/full_analysis_prompt.md`.
* `prompts/sections/macro_flow.md`.
* `prompts/sections/behavior_model.md`.
* `prompts/sections/technical_smc.md`.
* `prompts/sections/output_schema.md`.
* Response validator.
* Fallback template.

Tiêu chí đạt:

* AI không tự bịa giá, entry, SL, TP, lot.
* AI không tự bịa supply/demand zone, order block, FVG, BOS/CHOCH nếu technical/SMC context không cung cấp.
* Prompt cho từng symbol được sinh từ template chung + symbol profile, không hard-code số lượng prompt riêng cho từng mã.
* Output AI ngắn gọn nhưng sâu, có chất bank trader / macro trader / SMC trader.
* Output ưu tiên mức giá, vùng vào lệnh, SL, TP và invalidation.
* Nếu không có setup sạch, AI phải trả rõ: `No clean setup / đứng ngoài tốt hơn`.
* Lỗi AI không làm dừng app.
* Có test với mock AI response.

**Format nhận định AI (đã cập nhật 2026-06-02):**

Nhận định AI output theo chuẩn 4 section bullet. Mỗi dòng 1 bullet "- ", không markdown, không dấu *. Section 2 được sinh từ `economic_events` đã fetch, không qua AI. Giới hạn bullet mỗi section: 3/5/5/3. Pipeline post-processing: `_normalize_ai_commentary()` → `_compact_ai_commentary()` (regex parser) → `_annotate_common_english_terms()`. Fallback khi không có AI vẫn giữ đúng 4 section.

## Giai đoạn 8: Scanner và Journal

Tạo:

* Scanner worker.
* Scanner table model.
* Journal list/detail.
* Export JSON.

Tiêu chí đạt:

* Quét nhiều symbol không đơ UI.
* Bảng dùng model/view, không dựng thủ công từng label.
* Lưu được snapshot scanner và phân tích chi tiết.

## Giai đoạn 9: Packaging

Tạo:

* `packaging/pyinstaller.spec`.
* `packaging/build_windows.ps1`.
* `packaging/installer_notes.md`.

Tiêu chí đạt:

* Build ra `.exe`.
* `.exe` chạy bằng double click.
* Asset, QSS, migration được include.
* App tạo dữ liệu trong `%APPDATA%`.

## Definition of Done

Một task chỉ được coi là xong khi:

* Code đúng kiến trúc.
* Có xử lý lỗi người dùng thấy được.
* Có log kỹ thuật.
* Có test hoặc checklist thủ công phù hợp.
* UI không lệch/tràn ở viewport tối thiểu.
* Không làm khó việc đóng gói sau này.

## Logic Updates

- `risk_engine.build_trade_plan()` phai tach `watch_zone` rong va `entry_zone` hep. Chi `entry_zone` duoc dung de xac nhan `price_in_entry_zone` va `ready_to_trade`; `watch_zone` chi la vung theo doi.
- `core/backtest_engine.py` phai ap dung `cooldown_bars` sau khi thoat lenh de tranh dem trung cung mot setup khi gia sideways trong entry zone.
- AI commentary prompt phai co `entry_context`, gom entry/SL/TP/trang thai entry va `price_vs_zone`, de AI khong viet nhan dinh chung chung.
- Scanner table phai hien thi `price_vs_zone` bang text ngan: `Trong vung`, `Gan vung`, `Con xa`, de trader khong can mo Detail moi biet gia dang o dau so voi entry.
- `build_entry_checklist()` phai danh gia muc `Xu huong` theo side cua scenario; range chi pass khi co POI/edge setup va `location_quality` du manh.
- `score_scenario()` phai tinh tong diem theo trong so: trend 18, momentum 15, location 17, SMC quality 15, risk 15, macro 30. SMC quality phai dung BOS/CHOCH/displacement, premium/discount, liquidity sweep va metadata zone_score/broken/mitigated/test_count.
- `confidence_reason` phai giai thich breakdown diem trend/momentum/location/SMC/risk/macro, SMC reason, macro confidence thap, va event gan nhat neu dang caution.

## Auto Trade Implementation Rules

- Auto trade chi duoc kich hoat khi Scanner dang o che do auto-scan va nguoi dung da tick `Tu dong vao lenh MT5`. Quet 1 lan/manual scan khong duoc dat lenh.
- UI phai co nut toggle chon cho phep auto-entry. Khi nut dang bat va dang o auto-scan, control nay phai duoc lam noi bat de nguoi dung nhin thay.
- Khong hien thi them o checkbox nho ben trong nut toggle auto-entry; toan bo nut la chi bao trang thai bat/tat.
- UI phai truyen `ScannerRequest.auto_trade_enabled=True` chi khi scan mode la auto va nut auto-entry dang bat.
- Controller phai cap `risk_percent` theo `settings.trading.max_risk_percent` truoc khi goi analysis va truoc khi dat lenh.
- Chi auto trade row `ready` + `allowed` + co `analysis_result` + co scenario khop `best_side`.
- Lot dat lenh phai lay tu `position_sizing.suggested_lot`. Khong tinh lot rieng trong UI, khong tang lot len minimum neu viec do co the vuot risk.
- Moi broker symbol chi duoc co mot lenh dang ton tai. Phai kiem tra ca `positions_get(symbol=...)` va `orders_get(symbol=...)` truoc khi goi `order_send`.
- Neu da co position/order cho symbol, ghi ket qua skipped va khong dat lenh moi.
- Market order:
  - BUY dung gia `ask`.
  - SELL dung gia `bid`.
  - SL dung `scenario.stop_loss`.
  - TP dung TP dau tien trong `scenario.take_profit`.
- Ket qua auto trade phai tra ve trong `output["auto_trade_results"]` de UI/log co the hien thi va debug.

## Telegram Alert Implementation Rules

- Telegram detail alert chi gui setup that su ready.
- Summary alert chi hien thi tong so ma da quet va danh sach ma san sang vao lenh kem Entry/SL/TP. Khong hien thi danh sach theo doi.
- Thoi gian summary phai dung dinh dang `dd-mm-yyyy HH:MM:SS`.
