# Phân tích tính năng Nhật ký giao dịch

## Phạm vi

Báo cáo này được lập bằng cách đọc `ARCHITECTURE.md` ở thư mục gốc và lần theo code liên quan đến phần Nhật ký giao dịch. Phạm vi tập trung vào tính năng hiện có, luồng dữ liệu và những hạn chế có thể ảnh hưởng trực tiếp đến người dùng hoặc độ chính xác của kết quả.

Các thành phần chính đã được xem xét:

- `services/journal_service.py`, `journal_models.py`, `journal_converters.py`
- `core/journal_feedback_engine.py`, `core/statistical_edge_engine.py`
- `controllers/journal_controller.py`
- `ui/screens/journal_screen.py`, `ui/screens/journal_detail_screen.py`
- Các migration SQLite trong `data/migrations/`
- Luồng đồng bộ lịch sử tại `services/mt5_service.py`
- Tích hợp journal feedback vào scanner và analysis pipeline

## Định vị kiến trúc

Theo `ARCHITECTURE.md`, phần Nhật ký giao dịch nằm trên bốn lớp chính:

```text
Journal UI
    ↓
JournalController
    ↓
JournalService / JournalConverters / JournalModels
    ↓
SQLite journal database
```

Ngoài luồng hiển thị và lưu trữ, dữ liệu lệnh đã đóng còn được đưa ngược vào hệ thống phân tích:

```text
Closed journal entries
    ↓
Journal feedback / Statistical edge
    ↓
Analysis pipeline / Scanner gates / Ranking
```

Như vậy Journal không chỉ là nơi lưu lịch sử. Nó còn có thể tác động đến điểm số, cảnh báo và quyền thực thi của các cơ hội giao dịch mới.

## Nhược điểm chức năng

### 1. Đánh dấu “Đã đóng” nhưng lệnh có thể không được tính vào thống kê

Màn hình chi tiết ghi rằng thời gian đóng sẽ được tự điền khi trạng thái là “Đã đóng lệnh”. Tuy nhiên, nếu người dùng không bật checkbox thời gian đóng, UI gửi `closed_at` dưới dạng chuỗi rỗng.

Service vẫn có thể lưu `trade_status="closed"`, nhưng truy vấn hiệu suất và journal feedback chỉ lấy các bản ghi có `closed_at` khác rỗng. Kết quả là một lệnh nhìn trên giao diện như đã đóng nhưng lại không xuất hiện trong thống kê và không đóng góp vào phản hồi lịch sử.

Tệp liên quan:

- `ui/screens/journal_detail_screen.py`, khu vực `_save_lifecycle()`
- `services/journal_service.py`, các hàm `update_lifecycle()` và `list_closed_trades_for_account_guard()`

### 2. KPI tách rõ hai tập mẫu (đã sửa 2026-08-18)

`build_performance_summary()` thu thập riêng và **không trộn** hai tập mẫu:

- **Mẫu "tiền" (amount-sample)** — lệnh có `result_amount`. Đây là dân số chính:
  `win_rate`, `win_count`/`loss_count`/`breakeven_count`, `net_amount`, `profit_factor`
  **chia sẻ cùng một mẫu số** với `net_amount`, nên các KPI hiển thị cạnh nhau luôn
  cùng dân số (không còn tình trạng win rate tính trên 2 lệnh có R mà Net P/L tính trên 82 lệnh).
- **Mẫu "R" (r-sample)** — lệnh có `result_r` (cần SL): `expectancy_r`, `total_r`,
  `average_win_r`/`average_loss_r`, `r_win_rate`, `r_win_count`/`r_loss_count`.
  Khi số mẫu R khác số mẫu tiền (ví dụ lệnh MT5-sync có P/L nhưng không có SL —
  broker không lưu order history hoặc chưa re-sync sau nâng cấp SL), hai tỷ lệ
  thắng **được phép khác nhau** và được báo cáo tách bạch.

Từ 2026-08-18, lệnh MT5-sync có SL trong **order history** (`history_orders_get`)
sẽ được gán `actual_sl` và tính `result_r` khi re-sync — giảm áp lực "đói R".

UI minh bạch mẫu số: KPI "Tỷ lệ thắng" hiển thị headline theo dân số tiền và nêu rõ
`r_win_rate` + `r_trades/closed_trades` khi mẫu R nhỏ hơn mẫu tiền; KPI "Đã đóng" và
banner cảnh báo vẫn hiển thị số lệnh còn thiếu Result R.

Tệp liên quan:

- `services/journal_converters.py`, hàm `build_performance_summary()`
- `services/journal_converters.py`, hàm `group_performance()`
- `ui/screens/journal_screen.py`, hàm `_refresh_performance()`
- Regression: `tests/test_journal_performance_universes.py`

### 3. Đường cong P/L lũy kế mặc định chỉ dùng 12 lệnh gần nhất

Service tạo danh sách `recent` với giới hạn 12 lệnh. Khi không có cross-filter theo symbol, UI dùng chính danh sách này để vẽ đường cong P/L lũy kế.

Nhãn biểu đồ không nói rõ đây chỉ là 12 lệnh gần nhất, nên người dùng có thể hiểu nhầm đường cong này đại diện cho toàn bộ lịch sử giao dịch.

Tệp liên quan:

- `services/journal_converters.py`, `recent_trade_rows(..., limit=12)`
- `ui/screens/journal_screen.py`, `PerformanceChartWidget.update_charts()` và `_apply_recent_table_filters()`

### 4. Trạng thái cảnh báo Max Drawdown không hoạt động đúng

Hàm `max_drawdown_r()` trả về độ lớn drawdown dưới dạng số không âm. Tuy nhiên UI chỉ chuyển card sang trạng thái cảnh báo hoặc nguy hiểm khi drawdown nhỏ hơn `0` hoặc `-5`.

Vì điều kiện đó không thể xảy ra với giá trị hiện tại, một drawdown lớn vẫn được hiển thị ở trạng thái trung tính.

Tệp liên quan:

- `services/journal_converters.py`, hàm `max_drawdown_r()`
- `ui/screens/journal_screen.py`, phần cập nhật KPI Max Drawdown

### 5. Journal feedback theo vùng/setup tương tự không nhận đủ metadata

Schema và model có lưu các trường như:

- `entry_zone_score`
- `entry_zone_scoring_version`
- Điểm quality, relevance và setup của vùng
- Scoring provenance

Tuy nhiên `list_closed_trades_for_account_guard()` không đưa các trường zone metadata và scoring version vào dictionary trả về. Trong khi đó `statistical_edge_engine` cần chính các trường này để chọn cohort `symbol_direction_zone`.

Hệ quả là nhánh phản hồi thống kê theo vùng/setup tương tự gần như không thể hoạt động qua luồng runtime thông thường, dù metadata đã được lưu trong database và UI mô tả đây là bằng chứng từ các setup tương tự.

Tệp liên quan:

- `services/journal_models.py`
- `services/journal_service.py`, hàm `list_closed_trades_for_account_guard()`
- `core/journal_feedback_engine.py`
- `core/statistical_edge_engine.py`

### 6. Đồng bộ lịch sử MT5 chạy trực tiếp trên UI thread

Nút “Đồng bộ MT5” gọi controller đồng bộ, sau đó controller gọi trực tiếp `MT5Service.closed_trade_history()`. Không có worker hoặc background thread cho luồng này.

Khi MT5 phản hồi chậm hoặc lịch sử lớn, giao diện có thể bị đứng. Tính năng cũng không có tiến độ chi tiết hoặc khả năng hủy tác vụ. Khoảng đồng bộ trên UI bị cố định ở 90 ngày.

Điều này không phù hợp với yêu cầu kiến trúc rằng các tác vụ MT5 phải chạy ngoài UI thread.

Tệp liên quan:

- `ui/screens/journal_screen.py`, hàm `_sync_mt5_history()`
- `controllers/journal_controller.py`, hàm `sync_mt5_history()`
- `services/mt5_service.py`, hàm `closed_trade_history()`

### 7. Ghép lịch sử MT5 với kế hoạch journal có nguy cơ sai bản ghi

MT5 parser đã lấy `candidate_id` từ comment của lệnh, nhưng journal sync không dùng ID này để ghép với kế hoạch đã lưu.

Với bản ghi chưa có deal ID hoặc position ID, service thực hiện ghép gần đúng theo:

- Symbol hoặc broker symbol
- Hướng giao dịch
- Trạng thái planned/opened
- Khoảng thời gian tối đa 24 giờ

Sau đó service lấy bản ghi phù hợp gần nhất. Nếu có nhiều kế hoạch cùng symbol và cùng hướng trong một ngày, outcome từ MT5 có thể bị gắn vào sai kế hoạch.

Tệp liên quan:

- `services/mt5_service.py`, hàm `_closed_trades_from_deals()`
- `services/journal_service.py`, hàm `_find_mt5_sync_entry()`

### 8. Scale-in và partial close — R đã dùng giá bình quân, SL cuối cần order history

MT5 sync nhóm các deal theo position và cộng tổng profit, commission, swap.

- Giá vào/giá thoát thực tế là **bình quân theo volume** (`_volume_weighted_average`) — đúng với scale-in/đóng từng phần (không còn dùng deal đầu/cuối đơn lẻ).
- **SL** cho `result_r` từ 2026-08-18 được lấy từ **order history** (`history_orders_get`): lấy SL **cuối** (theo time) của position (bắt cả SL bị MODIFY). Broker không lưu order history → không có SL → `result_r=None` (fail-closed).

Với lệnh scale-in hoặc đóng từng phần, P/L tiền có thể đúng và R dùng chung SL cuối; nếu SL cuối không khớp ý định ban đầu (dời SL), R có thể khác kỳ vọng — cần đối soát khi dùng feedback R-based.

Tệp liên quan:

- `services/mt5_service.py`, hàm `_closed_trades_from_deals()`
- `services/journal_converters.py`, hàm `calculate_trade_outcome()`

### 9. Một số bộ lọc nhanh không làm mới bảng ngay

Các bộ lọc nhanh như:

- Lệnh thắng/thua
- Điểm AI tối thiểu
- Chất lượng thực thi tối thiểu

thay đổi giá trị widget trong lúc signal bị chặn nhưng không gọi lại `_apply_filters()` trước khi thoát. Vì vậy người dùng có thể bấm bộ lọc nhưng bảng chưa thay đổi cho tới khi có một thao tác lọc khác.

Ngoài ra, nút “Độ tin cậy AI ≥ 90” thực chất dùng cùng trường `min_score` với “Điểm AI ≥ 85”. Nó lọc `max(buy_score, sell_score)`, không lọc một trường AI confidence riêng.

Tệp liên quan:

- `ui/screens/journal_screen.py`, `_QUICK_FILTER_DEFS` và `_apply_quick_filter_value()`
- `services/journal_service.py`, phần xử lý `min_score`

### 10. Bộ lọc danh sách không áp dụng cho dashboard hiệu suất

Tab danh sách dùng đầy đủ `JournalFilter`, nhưng tab “Thống kê Hiệu suất” luôn gọi `performance_summary()` toàn cục mà không truyền các bộ lọc hiện tại.

KPI, phân nhóm và biểu đồ do đó không phản ánh khoảng ngày, symbol, kết quả, setup hoặc regime đang được chọn ở tab danh sách. Summary còn bị giới hạn tối đa 1.000 lệnh.

Tệp liên quan:

- `ui/screens/journal_screen.py`, các hàm `_apply_filters()` và `_refresh_performance()`
- `services/journal_service.py`, hàm `performance_summary()`

### 11. Cấu hình đường dẫn SQLite không có tác dụng với Journal runtime

`AppController` luôn tạo `JournalService()` không truyền đường dẫn từ settings. `JournalService` mặc định luôn dùng `config.paths.journal_db_path()`, tức database dưới thư mục app-data. Ô nhập `sqlite_database_path` đã bị xóa khỏi Settings ngày 16/08/2026 vì không code nào đọc nó (key cũ còn sót trên disk bị loader bỏ qua).

Người dùng có thể thay đổi và lưu đường dẫn trên UI nhưng Journal vẫn mở database mặc định.

Tệp liên quan:

- `config/settings.py`
- `ui/screens/settings_screen.py`
- `controllers/app_controller.py`
- `config/paths.py`
- `services/journal_service.py`

### 12. Workflow quản lý dữ liệu còn hạn chế

Các hạn chế đáng chú ý:

- Không có chức năng tạo một giao dịch thủ công ngay trong màn hình Journal.
- Luồng lưu journal được nối chủ yếu từ Scanner Detail hoặc đồng bộ MT5.
- Không thấy luồng lưu trực tiếp cho một phân tích đơn lẻ dù controller có `save_analysis()`.
- Chỉ xuất JSON từng bản ghi.
- Không có xuất CSV theo bộ lọc, import, backup hoặc restore database từ UI.
- Không có thao tác hàng loạt.
- Không có trường riêng cho ảnh chụp biểu đồ, attachment, trạng thái tâm lý hoặc review trước/sau giao dịch.

Tệp liên quan:

- `ui/screens/journal_screen.py`
- `ui/screens/journal_detail_screen.py`
- `ui/screens/scanner_detail_screen.py`
- `controllers/journal_controller.py`

### 13. Xóa bản ghi không có bước xác nhận hoặc khả năng khôi phục

Nút “Xóa bản ghi” gọi trực tiếp `delete_entry()` rồi quay về Journal. Không có hộp thoại xác nhận, undo hoặc thùng rác mềm.

Một lần bấm nhầm có thể xóa vĩnh viễn analysis payload, ghi chú và dữ liệu lifecycle của giao dịch.

Tệp liên quan:

- `ui/screens/journal_detail_screen.py`, hàm `_delete_entry()`
- `services/journal_service.py`, hàm `delete_entry()`

### 14. Đơn vị tiền tệ bị giả định là USD

P/L lấy từ MT5 là giá trị theo tiền tệ tài khoản giao dịch. Tuy nhiên màn hình và biểu đồ luôn hiển thị ký hiệu `$`.

Nếu tài khoản MT5 dùng EUR, GBP, JPY hoặc tiền tệ khác, các con số vẫn bị trình bày như USD. Journal hiện không lưu account currency để hiển thị đúng đơn vị.

Tệp liên quan:

- `services/mt5_service.py`, trường `result_amount`
- `services/journal_models.py`
- `ui/screens/journal_screen.py`, các KPI, bảng lịch sử và biểu đồ P/L
- `ui/screens/journal_detail_screen.py`, hero summary

### 15. Audit provenance chưa đầy đủ

Journal có lưu một phần scoring provenance và analysis payload, nhưng màn hình chi tiết không trình bày rõ:

- Phiên bản scorer đã tạo quyết định
- Zone scoring version và breakdown
- VIX pair-aware map version
- Sensitivity factor và hướng tác động
- Số điểm được cộng/trừ do VIX modulation

Tài liệu sản phẩm cũng xác nhận giới hạn VIX attribution này. Do đó Journal chưa đủ mạnh để giải thích vì sao cùng một setup lại nhận điểm hoặc quyết định khác nhau giữa các phiên bản hệ thống.

Tệp liên quan:

- `docs/product/product_spec.md`
- `services/journal_models.py`
- `services/journal_converters.py`
- `ui/screens/journal_detail_screen.py`

## Kết luận

Phần Journal đã có nền tảng tương đối đầy đủ: SQLite migration, lưu kế hoạch và outcome, đồng bộ MT5, Result R, mistake tags, execution quality, bộ lọc và dashboard hiệu suất. Điểm yếu lớn nhất nằm ở tính nhất quán giữa dữ liệu được lưu, dữ liệu được đưa vào thống kê và dữ liệu được dùng làm feedback cho scanner.

Các vấn đề nên được ưu tiên cao nhất nếu triển khai cải tiến sau này là:

1. Bảo đảm lệnh “đã đóng” luôn có lifecycle hợp lệ và được thống kê đúng.
2. Thống nhất tập mẫu cho các KPI và biểu đồ.
3. Sửa đường cong hiệu suất và trạng thái Max Drawdown.
4. Đưa đầy đủ zone/scoring metadata vào journal feedback.
5. Chuyển đồng bộ MT5 sang background worker và ghép lệnh bằng định danh ổn định.
6. Làm cho bộ lọc, cấu hình database và đơn vị tiền tệ phản ánh đúng hành vi thực tế.

## Đề xuất 3 nâng cấp tích hợp AI

Ba nâng cấp có giá trị nhất nên tạo thành vòng lặp:

```text
Tự động ghi nhận → Hỗ trợ trước lệnh → Huấn luyện sau lệnh
```

### 1. AI Auto-Journal và tái dựng giao dịch

Đây nên là ưu tiên đầu tiên vì chất lượng mọi thống kê và AI sau này phụ thuộc vào dữ liệu Journal đầy đủ.

Sau khi lệnh đóng hoặc đồng bộ MT5, AI có thể tổng hợp:

- Kế hoạch ban đầu so với thực thi thực tế.
- Setup, regime, session và bối cảnh tin tức.
- Entry/SL/TP dự kiến so với thực tế.
- Các trường còn thiếu hoặc có dấu hiệu bất thường.
- Tóm tắt điều gì đã xảy ra, đúng ở đâu và sai ở đâu.
- Phân tích ảnh chart trước/sau lệnh nếu trader đính kèm.

Nên có một “Hộp thư cần xác nhận” để trader duyệt nhanh các trường AI suy luận thay vì nhập lại toàn bộ.

R, P/L, drawdown và giá phải tiếp tục do code xác định. AI chỉ nên phân loại, giải thích và đề xuất; các trường AI suy luận phải có confidence và nguồn dữ liệu. Không được ghi đè note hoặc tag thủ công nếu chưa được trader xác nhận.

Nền hiện tại đã có plan/actual/tags/execution quality trong `services/journal_models.py` và phân tích thực thi trong `services/journal_service.py`.

### 2. AI Similar-Trade Copilot trước khi vào lệnh

Khi trader mở Scanner Detail, hệ thống truy hồi những giao dịch lịch sử giống setup hiện tại nhất.

Nên kết hợp hai tầng:

1. Lọc cứng theo symbol, hướng, regime, session và zone score.
2. Dùng embedding để xếp hạng độ giống nhau dựa trên analysis, lý do vào lệnh và ghi chú.

Copilot nên hiển thị:

- 3–5 lệnh tương tự kèm Journal ID.
- Sample size, win rate và expectancy do statistical engine tính.
- Điểm giống và khác so với cơ hội hiện tại.
- Các lỗi thường lặp lại như FOMO, vào sớm, dời SL hoặc revenge trade.
- Checklist cá nhân hóa trước khi trader đặt lệnh.
- Cảnh báo dạng: “5/7 lệnh tương tự thua khi bỏ qua M15”.

AI chỉ giải thích bằng chứng; không được tự thay đổi score, gate hoặc quyết định đặt lệnh. Khi mẫu ít, phải hiển thị rõ “chưa đủ dữ liệu”.

Nâng cấp này mở rộng trực tiếp `core/journal_feedback_engine.py`. Catalog AI hiện đã khai báo khả năng Embedding và JSON mode trong `services/ai/provider_catalog.py`.

### 3. AI Performance Coach và Playbook cá nhân

AI tạo review sau từng lệnh và báo cáo tuần/tháng, biến Journal thành hệ thống huấn luyện thay vì chỉ là kho dữ liệu.

Báo cáo nên trả lời:

- Trader đang kiếm tiền từ setup nào?
- Đang mất tiền vì chiến lược hay vì thực thi?
- Hiệu suất suy giảm ở symbol, regime hoặc session nào?
- Sai lầm nào lặp lại nhiều nhất và gây mất bao nhiêu R?
- Kỷ luật có cải thiện sau khuyến nghị trước không?
- Tuần tới nên tập trung thay đổi 1–3 hành vi nào?

AI có thể xây “Playbook cá nhân” được version hóa, gồm setup ưu tiên, điều kiện bắt buộc trước khi vào, điều kiện nên đứng ngoài, mức risk khuyến nghị và checklist riêng cho từng lỗi hành vi.

Mọi đề xuất ảnh hưởng scanner hoặc risk phải được trader chấp thuận và kiểm chứng bằng backtest hoặc đủ mẫu Journal. AI không được tự sửa rule giao dịch.

### Guardrail bắt buộc cho cả 3 nâng cấp

- Mỗi kết luận phải dẫn tới Journal ID hoặc số liệu nguồn.
- Lưu model, prompt version, thời điểm và confidence của AI.
- Không dùng AI để tự tính số liệu tài chính.
- Không cho AI tự đặt lệnh hoặc tự thay đổi risk.
- Không kết luận khi mẫu dưới ngưỡng tối thiểu.
- Dữ liệu gửi lên cloud phải có opt-in và loại bỏ thông tin tài khoản nhạy cảm.

Nếu chỉ triển khai một nâng cấp trước, nên chọn **AI Auto-Journal**. Nó giải quyết nút thắt dữ liệu và tạo nền móng để hai nâng cấp còn lại hoạt động đáng tin cậy.
