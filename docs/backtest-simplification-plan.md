# Kế Hoạch Tinh Gọn Chức Năng Backtest

> Trạng thái: **Toàn bộ Giai đoạn 0–6 đã hoàn thành**
>
> Ngày lập: **25/07/2026**
>
> Phạm vi: màn hình Backtest, controller/worker, kiểm tra chất lượng dữ liệu,
> Research/Validation, IS/OOS, Walk-Forward, Monte Carlo, portfolio, điều chỉnh
> tham số, áp dụng cấu hình Scanner và migration Settings cũ.

## 1. Mục Đích

Thay đổi này nhằm làm cho Backtest dễ hiểu và an toàn hơn mà không làm mất các
lớp kiểm chứng cần thiết. Người dùng thông thường chỉ cần chọn mã, thời gian,
mục đích và chạy; hệ thống phải tự chọn đúng quy trình kỹ thuật phía sau.

Các mục tiêu cụ thể:

- khắc phục lỗi nhận diện khoảng trống dữ liệu khiến `VALIDATION` bị chặn sai;
- loại bỏ control trùng nghĩa và các tổ hợp cấu hình không hợp lệ;
- tách rõ luồng nghiên cứu với luồng kiểm chứng để phát hành config Scanner;
- giảm thông tin lặp lại trên màn hình kết quả;
- chỉ hiển thị hành động phù hợp với lifecycle của snapshot;
- chuyển các công cụ chuyên sâu ra khỏi luồng Backtest thông thường;
- xóa code chết và feature flag đã hết vai trò;
- giữ nguyên các bằng chứng cần thiết cho tính đúng, audit và release gate.

Đây là thay đổi tinh gọn kiến trúc và trải nghiệm, không phải hạ tiêu chuẩn để
config Backtest dễ đạt `VALIDATED` hơn.

## 2. Kết Luận Rà Soát

Không có module lõi lớn nào của Backtest nên bị xóa hoàn toàn. Point-in-time
data, execution parity, frozen OOS, Walk-Forward, thống kê, portfolio và release
gate đều có consumer trong runtime và phục vụ một mục đích khác nhau.

Phần dư thừa tập trung ở ba nhóm:

1. Giao diện có nhiều lựa chọn nhưng một số lựa chọn thực hiện cùng một hành vi.
2. Công cụ nghiên cứu nâng cao đang đặt ngang hàng với luồng Backtest chính.
3. Code giao diện, script vá tạm và feature flag cũ không còn tác dụng.

## 3. Thành Phần Phải Giữ

Các thành phần sau là bắt buộc đối với kiến trúc Backtest hoàn chỉnh:

- Point-in-time candle snapshot và khoảng thời gian `[start, end)`;
- `DataManifest`, dataset hash, coverage, timezone, duplicate và chất lượng OHLC;
- execution parity với spread, slippage, commission và swap;
- mô hình entry/exit có thứ tự sự kiện và xử lý gap tại giá mở cửa;
- Candidate Ledger, frozen strategy và provenance;
- frozen IS/OOS replay với trạng thái tài khoản được reset;
- Walk-Forward theo thời gian;
- bootstrap uncertainty và permutation sequence risk;
- portfolio clock và account guard cho backtest nhiều mã;
- snapshot migration và khả năng xem lại kết quả cũ;
- golden replay, shadow, forward-demo và release report;
- đường cong vốn, danh sách lệnh và dữ liệu chẩn đoán pipeline.

`core/backtest_engine.py` không được xóa chỉ vì có tên giống engine cũ. Module
này vẫn được Analysis Pipeline dùng cho plan replay; nếu cần làm rõ có thể đổi
tên trong một thay đổi riêng có migration import đầy đủ.

## 4. Thành Phần Cần Gộp Hoặc Loại Bỏ

### 4.1. Gộp `Walk-Forward` và `IS/OOS`

Trước Giai đoạn 2, hai checkbox cùng tạo một giá trị
`walk_forward_enabled`. Khi một trong hai được chọn, controller đều chạy frozen
validation replay và Walk-Forward. Hai control trùng nghĩa này đã được loại bỏ.

Runtime hiện hành:

- không còn checkbox `IS/OOS` và `Walk-Forward` trên form chính;
- khi mục đích là `VALIDATION`, hệ thống tự động chạy cả frozen IS/OOS và
  Walk-Forward;
- với `RESEARCH`, cho phép chạy kiểm chứng bổ sung trong khu vực nâng cao nếu
  người dùng thật sự cần.

### 4.2. Xóa code giao diện không còn được gọi

Các thành phần cần xác minh lại bằng test rồi loại bỏ:

- `_on_tab_changed()` đang chỉ chứa `pass`;
- `_build_equity_curve_html()` của biểu đồ HTML cũ;
- `_do_apply_config()` của dialog nhiều checkbox cũ;
- `_section_box()`, `_field_cell()` và `_symbol_cell()` không có caller;
- `BacktestInputHelpDialog` không có đường mở và mô tả nhiều field đã bị xóa;
- `_show_input_help()` không có caller;
- `set_equity_chart_visible()` được gọi nhưng chỉ chứa `pass`;
- import chỉ phục vụ các đoạn code chết phía trên;
- `scratch/fix_backtest_screen.py`, là script vá tạm của giao diện cũ.

### 4.3. Loại bỏ feature flag đã hết vai trò

- `backtest_engine_v2` được lưu nhưng không điều khiển engine đang chạy.
- `backtest_config_v2` chủ yếu còn xuất hiện trong observability, không quyết
  định Strategy Router.

Migration phải cho phép đọc Settings cũ nhưng ngừng sử dụng và ngừng ghi lại
hai flag này. Không được làm mất cấu hình symbol hoặc evidence Backtest đã lưu.

## 5. Thành Phần Chuyển Sang Nghiên Cứu Nâng Cao

### 5.1. Điều chỉnh tham số

Engine điều chỉnh tham số vẫn hữu ích để đo sensitivity và phát hiện overfit,
nhưng không cần thiết trong luồng Backtest thông thường.

Hạn chế hiện tại:

- dùng các giai đoạn cố định 2023–2025 thay vì khoảng người dùng vừa chọn;
- chỉ dùng symbol đầu tiên khi người dùng đã chọn nhiều mã;
- tạo request `RESEARCH` chưa đồng nhất toàn bộ cost/execution context của
  Backtest chính;
- kết quả chỉ tạo báo cáo và không phải bằng chứng `VALIDATED`;
- việc chọn giá trị tốt nhất trên dữ liệu cũ có thể gây overfit.

Hướng xử lý:

- chuyển tab này sang khu vực “Nghiên cứu nâng cao”;
- dùng chung request factory, cost model và data loader với Backtest chính;
- cho phép chọn đúng khoảng thời gian và symbol;
- ghi rõ mọi kết quả sweep là `RESEARCH_ONLY`;
- không tự động áp dụng giá trị được xếp hạng cao nhất;
- sau khi chọn tham số phải chạy lại frozen IS/OOS, Walk-Forward và
  forward-demo.

### 5.2. AI phân tích

AI phân tích là tiện ích diễn giải, không phải bằng chứng validation. Chức năng
này phụ thuộc API bên ngoài và có thể đưa ra nhận định không ổn định.

Hướng xử lý:

- chuyển vào phần nâng cao;
- ghi rõ nội dung AI chỉ tham khảo;
- không cho AI thay đổi lifecycle hoặc release report;
- giữ các kết luận định lượng do engine tính làm nguồn sự thật.

### 5.3. Nghiên cứu nhanh

Chế độ này có thể cho kết quả khác execution parity và không đủ điều kiện phát
hành. Chuyển khỏi form chính, mặc định mọi lần chạy dùng “Mô phỏng MT5”.

### 5.4. Portfolio nhiều mã

Portfolio có giá trị khi đánh giá risk/exposure nhưng kết quả luôn
`RESEARCH_ONLY` và không thể áp trực tiếp thành config của một symbol.

Hướng xử lý:

- giữ engine và UI trong phần nâng cao;
- thông báo rõ trước khi chạy nhiều mã;
- không hiển thị hành động áp dụng config trên kết quả portfolio.

### 5.5. Monte Carlo

Monte Carlo cần giữ nhưng không nhất thiết luôn chạy 2.000 lần cho mọi kết quả.
Chỉ chạy khi đủ số lệnh hoặc khi người dùng yêu cầu phân tích thống kê nâng cao.
Validation vẫn phải chạy đúng thống kê bắt buộc trong frozen replay.

## 6. Tinh Gọn Kết Quả Và Hành Động

### 6.1. Thanh kết quả nhanh

Chỉ giữ năm chỉ số phục vụ quyết định nhanh:

- số lệnh;
- kỳ vọng;
- hệ số lợi nhuận;
- drawdown tối đa;
- Net R.

Win rate, Gross R, chi phí, trung bình thắng/thua và chuỗi thua vẫn được lưu và
hiển thị trong bảng chi tiết, không bị xóa khỏi snapshot.

### 6.2. Nút áp dụng cấu hình

Hành động phải phụ thuộc lifecycle:

| Lifecycle | Hành động |
|---|---|
| `RESEARCH_ONLY` | Không hiển thị nút áp dụng |
| `DRAFT` | Hiển thị “Lưu đề xuất nháp” |
| `VALIDATED` | Hiển thị “Áp dụng cấu hình” |
| `LEGACY_RESEARCH` | Chỉ xem/phân tích |
| Portfolio | Không cho áp thành config đơn mã |

Khi tải snapshot, màn hình phải lấy symbol từ snapshot. Không dùng symbol đang
chọn trên form để áp một file thuộc symbol khác.

## 7. Sửa Lỗi Nhận Diện Khoảng Trống Dữ Liệu

Lỗi `UNEXPECTED_DATA_GAP` báo sai cho thời gian Forex đóng cửa tối thứ Sáu đã
được khắc phục ở Giai đoạn 1. Runtime không còn suy luận bằng weekday UTC đơn
thuần mà phân loại từng slot thiếu theo lịch phiên của nhóm tài sản.

Baseline 86 slot H1 đã được khóa thành 43 cuối tuần nhân hai slot báo sai. Test
hồi quy chạy qua 43 tuần, bao gồm cả thời điểm đổi DST, xác nhận các slot này
không còn tạo gap bất thường.

Kiến trúc hiện hành:

- `TradingSessionCalendar` được tách khỏi hàm chuẩn hóa candle;
- policy có version theo Forex, kim loại và crypto;
- giờ đóng/mở dùng `America/New_York`, tự đổi theo DST; kim loại có daily
  maintenance, lịch đóng sớm và ngày nghỉ có version;
- phân loại `EXPECTED_SESSION_CLOSE`, `MARKET_HOLIDAY` và
  `UNEXPECTED_DATA_GAP`;
- coverage đầu/cuối được kiểm tra riêng với gap bên trong;
- `DataManifest` v2 lưu symbol, khoảng yêu cầu, policy version/fingerprint,
  expected closure và gap nằm ngoài quality scope để audit;
- chỉ gap thật trong quality scope của timeframe mới chặn `VALIDATION`.

Không được đơn giản hóa bằng cách đổi mọi gap thành warning được bỏ qua hoặc hạ
`validation_eligible` gate.

## 8. Luồng Sử Dụng Đích

### Research thông thường

1. Chọn symbol, thời gian, vốn và rủi ro.
2. Chọn `RESEARCH`.
3. Hệ thống mặc định dùng execution parity.
4. Chạy replay và hiển thị kết quả nghiên cứu.
5. Không xuất hiện nút áp dụng config production.

### Validation

1. Chọn symbol, thời gian, vốn và rủi ro.
2. Chọn `VALIDATION`.
3. Hệ thống tự khóa execution parity và cost model.
4. Kiểm tra Trading Session/DataManifest.
5. Chạy Candidate Ledger IS, frozen OOS và Walk-Forward.
6. Kết quả chỉ là `DRAFT` cho tới khi release evidence hợp lệ.
7. Chỉ snapshot có release report `ready=true` mới đạt `VALIDATED`.

### Nghiên cứu nâng cao

Người dùng chủ động mở khu vực riêng để chạy parameter sweep, AI analysis,
research-fast hoặc portfolio. Mọi kết quả phải ghi rõ phạm vi sử dụng và không
được tự động phát hành.

## 9. Kế Hoạch Thực Hiện

Tổng cộng **7 giai đoạn, đánh số từ 0 đến 6**.

### Giai đoạn 0 — Khóa đặc tả và baseline

Mục tiêu: bảo vệ hành vi đúng đang có trước khi thay đổi.

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Công việc:

- lập ma trận `RESEARCH`/`VALIDATION`, đơn mã/portfolio;
- lưu baseline snapshot và kết quả đại diện;
- bổ sung characterization test cho UI, controller, lifecycle và Settings;
- chốt danh sách code chết và dữ liệu cần migration;
- xác định rollback boundary cho từng giai đoạn.

Tiêu chí đóng:

- test baseline xanh;
- ma trận hành vi được khóa;
- chưa thay đổi runtime production.

Độ phức tạp: **Thấp**.

#### Kết quả thực hiện Giai đoạn 0

Giai đoạn này không thay đổi runtime. Baseline có version được lưu tại
`tests/fixtures/backtest_simplification_phase0_baseline.json`; characterization
test nằm tại `tests/test_backtest_simplification_phase0.py`.

Ma trận hành vi hiện tại đã được khóa:

| Phạm vi | Purpose | Yêu cầu evidence | Kết quả hiện tại | Có thể phát hành |
|---|---|---:|---|---:|
| Đơn mã | `RESEARCH` | Không | `RESEARCH_ONLY` | Không |
| Đơn mã | `RESEARCH` | Có | Chạy frozen replay + Walk-Forward nhưng vẫn `RESEARCH_ONLY` | Không |
| Đơn mã | `VALIDATION` | Không | Thiếu validation replay, bị giữ ở `RESEARCH_ONLY` | Không |
| Đơn mã | `VALIDATION` | Có | Validation replay hoàn tất thì tạo `DRAFT` | Không, còn release gate |
| Portfolio | Bất kỳ | Bất kỳ | `portfolio_backtest` / `RESEARCH_ONLY` | Không áp thành config đơn mã |

Baseline UI ghi nhận hai checkbox `Walk-Forward` và `IS/OOS` cùng được gộp bằng
phép `OR` thành một `walk_forward_enabled`. Đây là hành vi được mô tả để Phase 2
thay đổi có kiểm soát, không phải contract đích cần giữ vĩnh viễn.

Baseline lỗi dữ liệu cũng đã tái hiện: một nến H1 mở thứ Sáu 21:00 UTC và nến
tiếp theo mở Chủ nhật 22:00 UTC bị thuật toán hiện tại báo thiếu hai interval.
Đây là `KNOWN_FALSE_POSITIVE_TO_FIX_IN_PHASE_1`; Giai đoạn 0 chỉ khóa bằng
chứng, không sửa hoặc bỏ qua warning.

Các bằng chứng hiện hành khác được tái sử dụng thay vì nhân bản fixture:

- golden deterministic snapshot tại `tests/fixtures/backtest_phase7_golden.json`;
- legacy migration/fail-closed trong `tests/test_backtest_phase7_release.py`;
- Settings feature-flag round-trip trong `tests/test_scanner_phase0_settings.py`;
- portfolio clock/account guard trong `tests/test_backtest_phase6_portfolio.py`;
- point-in-time/DataManifest trong `tests/test_backtest_point_in_time.py`.

#### Danh sách migration đã chốt

- `backtest_config_v2` và `backtest_engine_v2`: deprecated, chỉ loại bỏ ở
  Giai đoạn 5 sau khi có migration đọc-cũ/ghi-mới;
- snapshot engine cũ: giữ evidence, migrate thành `LEGACY_RESEARCH`, không phát
  hành;
- snapshot hiện hành: không sửa tay lifecycle hoặc fingerprint;
- Settings symbol/backtest evidence: không được xóa khi bỏ feature flag;
- parameter-sweep checkpoint: giữ tương thích cho đến khi khu vực nâng cao mới
  có migration riêng.

#### Rollback boundary

Mỗi giai đoạn sau phải có phạm vi rollback độc lập:

| Giai đoạn | Boundary bắt buộc |
|---|---|
| 1 | Chỉ session calendar, DataManifest và thông báo gap; không đổi scoring/execution |
| 2 | Chỉ mode orchestration và control UI; không đổi kết quả replay của cùng request |
| 3 | Chỉ presentation/lifecycle action; không sửa snapshot evidence |
| 4 | Công cụ nâng cao, worker và shared request factory; không mở quyền phát hành |
| 5 | Chỉ xóa sau reference audit; migration phải đọc được Settings/snapshot cũ |
| 6 | Test, tài liệu và nghiệm thu; không thêm behavior ngoài đặc tả đã khóa |

Nếu một giai đoạn làm sai baseline ngoài boundary của nó, rollback riêng giai
đoạn đó thay vì sửa tiếp trên contract chưa ổn định.

Kiểm chứng khi đóng Giai đoạn 0:

- characterization mới: **11 passed**;
- nhóm Backtest/lifecycle/Settings liên quan: **70 passed**;
- full test suite: **1561 passed, 12 skipped, 17 xfailed, 0 failed**;
- không có file runtime nào được sửa riêng bởi Giai đoạn 0.

### Giai đoạn 1 — Sửa lịch phiên và nhận diện data gap

Mục tiêu: khôi phục tính đúng và khả năng sử dụng của `VALIDATION`.

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Công việc:

- triển khai Trading Session Calendar có version;
- phân loại cuối tuần, DST, ngày lễ, broker break và gap thật;
- kiểm tra coverage;
- cải thiện thông báo lỗi, kèm timestamp và số nến thiếu;
- bổ sung test cho Forex, XAU và JPY.

Tiêu chí đóng:

- thời gian đóng cửa hợp lệ không chặn Validation;
- gap thật trong phiên vẫn bị chặn;
- case 86 gap H1 được tái hiện và giải quyết đúng nguyên nhân.

Độ phức tạp: **Cao**.

#### Kết quả thực hiện Giai đoạn 1

- Thêm `core/trading_session_calendar.py` với policy
  `trading-session-calendar-v1` và holiday calendar
  `backtest-market-holidays-v1`.
- Forex dùng phiên Chủ nhật 17:00 đến thứ Sáu 17:00 theo New York; kim loại
  dùng Chủ nhật 18:00 đến thứ Sáu 17:00, có khoảng bảo trì 17:00–18:00,
  grace 15 phút khi mở lại, Good Friday và các lịch đóng sớm chính; crypto
  được coi là 24/7.
- Nâng manifest lên `backtest-data-manifest-v2-session-aware`. Dataset hash
  bao gồm session-policy fingerprint và khoảng thời gian người dùng yêu cầu;
  manifest cũ không được âm thầm coi là evidence tương đương.
- Tách `EXPECTED_SESSION_CLOSE`, `BROKER_MAINTENANCE`, `MARKET_HOLIDAY` khỏi
  `UNEXPECTED_DATA_GAP`; các khoảng đóng hợp lệ vẫn được lưu để audit nhưng
  không tạo quality issue.
- Kiểm tra riêng `DATA_COVERAGE_START_MISSING` và
  `DATA_COVERAGE_END_MISSING`. Gap lịch sử ngoài vùng có thể ảnh hưởng replay
  được lưu ở `out_of_scope_gaps`, không chặn một validation window về sau.
- Quality lookback hiện hành: D1 365 ngày, H4 90 ngày, H1 30 ngày và M15 7
  ngày trước `requested_start`; mọi gap trong khoảng này hoặc trong khoảng
  backtest vẫn fail-closed.
- Thông báo gap thật nêu timeframe, số đoạn, tổng số nến thiếu và timestamp
  thiếu đầu tiên.
- `run_system_backtest()` truyền symbol và khoảng `[start, end)` vào bước tạo
  manifest; không thay đổi scoring, execution, lifecycle hoặc quyền phát hành.

Kiểm chứng khi đóng Giai đoạn 1:

- test 43 cuối tuần/86 slot, DST mùa đông và mùa hè, Forex, JPY, XAU, crypto,
  holiday, broker maintenance, coverage, hash và gap thật đều xanh;
- smoke trực tiếp MT5 cho `EUR/USD`, `USD/JPY`, `XAU/USD` trong khoảng
  25/01/2026–25/07/2026 đều có `quality_status=OK`,
  `validation_eligible=true` và 0 gap bất thường;
- gap H1 thật trong ngày giao dịch vẫn tạo `UNEXPECTED_DATA_GAP` và chặn
  validation;
- nhóm hồi quy Backtest/Router/contract: **256 passed**;
- full test suite: **1582 passed, 12 skipped, 17 xfailed, 0 failed**;
- `compileall` và `git diff --check` đạt; cảnh báo line-ending của worktree
  Windows không phải lỗi nội dung.

### Giai đoạn 2 — Hợp nhất Research, IS/OOS và Validation

Mục tiêu: loại bỏ tổ hợp lựa chọn không hợp lệ và giảm kiến thức kỹ thuật người
dùng phải tự nhớ.

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Công việc:

- bỏ checkbox trùng nghĩa;
- Validation tự chạy frozen IS/OOS và Walk-Forward;
- Validation tự ép execution parity;
- Research mặc định dùng mô phỏng MT5;
- research-fast chuyển vào phần nâng cao;
- bổ sung UI state và test cho toàn bộ ma trận mode.

Tiêu chí đóng:

- không còn hai control điều khiển cùng một biến;
- không thể chạy Validation bằng execution model không hợp lệ;
- Validation luôn tạo đủ evidence bắt buộc ở cấp backtest.

Độ phức tạp: **Trung bình–cao**.

#### Kết quả thực hiện Giai đoạn 2

- Thêm policy trung tâm `backtest-run-policy-v1` trong
  `core/backtest_contract.py`. Policy là nguồn quyết định duy nhất cho purpose,
  execution mode, frozen IS/OOS và Walk-Forward.
- `VALIDATION` luôn bị ép sang `EXECUTION_PARITY`; caller truyền
  `execution_mode=RESEARCH` cũng không thể tạo Validation nhanh.
- Validation luôn chạy frozen validation replay và Walk-Forward, không còn phụ
  thuộc checkbox hoặc cờ thủ công từ UI.
- Replay mô tả ban đầu của Validation chạy dưới purpose `RESEARCH`, vì lúc đó
  chưa có frozen strategy. Chỉ OOS replay sau khi tối ưu IS mới mang contract
  `VALIDATION`; cách này tránh tạo bằng chứng Validation giả.
- `RESEARCH` mặc định dùng Mô phỏng MT5. Người dùng chỉ có thể chọn Nghiên cứu
  nhanh trong tab **Nghiên cứu nâng cao** và kết quả luôn `RESEARCH_ONLY`.
- Tùy chọn chạy thêm IS/OOS + Walk-Forward cho Research chỉ khả dụng với
  execution parity. Chọn Nghiên cứu nhanh sẽ tự tắt tùy chọn này để loại bỏ tổ
  hợp không hợp lệ.
- Form chính đã bỏ cả checkbox `IS/OOS`, checkbox `Walk-Forward` và combobox
  execution. Nhãn mode giải thích trực tiếp quy trình sẽ chạy.
- Controller dùng tên rõ nghĩa `research_validation_enabled`; batch/portfolio
  cũng áp cùng policy cho từng symbol nhưng kết quả portfolio vẫn
  `RESEARCH_ONLY`.
- Mỗi snapshot mới lưu `run_policy` để audit version và quyết định orchestration.

Kiểm chứng khi đóng Giai đoạn 2:

- test ma trận Research/Validation, execution coercion, UI state, single và
  portfolio đều xanh;
- nhóm hồi quy Backtest/Walk-Forward/Router/contract: **302 passed**;
- full test suite: **1590 passed, 12 skipped, 17 xfailed, 0 failed**;
- `compileall` và `git diff --check` đạt; 5 warning hiện hữu của pytest/thư viện
  không phải failure của Phase 2.

### Giai đoạn 3 — Tinh gọn kết quả và hành động

Mục tiêu: giúp người dùng hiểu đúng kết quả và không áp nhầm config.

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Công việc:

- rút thanh kết quả nhanh xuống năm chỉ số;
- chuyển số liệu phụ vào chi tiết;
- điều khiển nút theo lifecycle;
- đồng bộ symbol khi tải snapshot;
- Việt hóa lý do `DRAFT`/không phát hành;
- giữ đầy đủ dữ liệu audit trong JSON.

Tiêu chí đóng:

- Research không còn nút áp dụng production;
- không thể áp snapshot cho sai symbol;
- lifecycle và hành động có ý nghĩa nhất quán.

Độ phức tạp: **Trung bình**.

#### Kết quả thực hiện Giai đoạn 3

- Thanh kết quả nhanh chỉ còn năm chỉ số phục vụ quyết định: số lệnh, kỳ vọng,
  hệ số lợi nhuận, drawdown tối đa và Net R.
- Win rate, Gross R, chi phí, trung bình thắng/thua, chuỗi thua cùng toàn bộ
  breakdown vẫn nằm trong kết quả chi tiết và snapshot JSON; Phase 3 không xóa
  hoặc sửa evidence.
- Thêm policy trình bày `backtest-presentation-v1` làm nguồn duy nhất cho
  lifecycle label, lý do tiếng Việt, symbol của snapshot và hành động được phép.
- `RESEARCH_ONLY`, `LEGACY_RESEARCH`, `REVIEW_REQUIRED` và portfolio không
  hiển thị hành động lưu/áp dụng cấu hình.
- `DRAFT` chỉ hiển thị **Lưu đề xuất nháp**; nhãn và tooltip nói rõ bản nháp
  không được Strategy Router dùng để giao dịch.
- Chỉ `VALIDATED`, `RELEASE_READY` hoặc lifecycle có
  `can_publish_config=true` mới hiển thị **Áp dụng cấu hình**.
- Khi tải hoặc nhận kết quả, symbol trên form được đồng bộ từ `request`, frozen
  validation replay, child portfolio hoặc trade legacy. Mọi thao tác ghi
  Settings kiểm tra lại snapshot là đơn mã và symbol phải khớp ngay trước khi
  lưu.
- Dialog cấu hình kiểm tra lifecycle của snapshot phải tương ứng với status
  config (`DRAFT` hoặc `VALIDATED`); trạng thái không nhất quán sẽ fail-closed.
- Lý do DRAFT, thiếu mẫu OOS, Walk-Forward, thống kê và release gate phổ biến
  đã được giải thích bằng tiếng Việt; mã kỹ thuật vẫn được giữ trong fallback
  để audit.

Kiểm chứng khi đóng Giai đoạn 3:

- test action theo lifecycle, symbol mismatch, portfolio, snapshot legacy,
  Việt hóa, KPI và guard khi gọi trực tiếp đều xanh;
- nhóm hồi quy Backtest/UI/Router: **344 passed**;
- full test suite: **1602 passed, 12 skipped, 17 xfailed, 0 failed**;
- `compileall` và `git diff --check` đạt; 5 warning hiện hữu của pytest/thư viện
  không phải failure của Phase 3.

### Giai đoạn 4 — Tách công cụ nghiên cứu nâng cao

Mục tiêu: tinh gọn Backtest chính mà không mất năng lực nghiên cứu.

Công việc:

- tạo khu vực nâng cao cho sweep, AI, research-fast và portfolio;
- nâng sweep dùng chung request/cost/data context;
- cho sweep dùng khoảng thời gian và symbol được chọn;
- đánh dấu mọi kết quả nâng cao đúng lifecycle;
- chạy Monte Carlo theo điều kiện mẫu hoặc theo yêu cầu;
- giữ cancel, timeout và checkpoint/resume.

Tiêu chí đóng:

- Backtest chính không còn công cụ chuyên sâu gây nhiễu;
- sweep không thể tự động áp tham số;
- portfolio không thể áp config đơn mã;
- kết quả nâng cao vẫn truy vết được.

Độ phức tạp: **Cao**.

#### Kết quả thực hiện Giai đoạn 4

Trạng thái: **Hoàn thành ngày 25/07/2026**.

- Tab **Nghiên cứu nâng cao** hiện chứa tập trung research-fast, IS/OOS bổ sung,
  portfolio, Monte Carlo theo yêu cầu, AI và parameter sweep; nút AI đã được
  bỏ khỏi vùng xem kết quả chính.
- Portfolio chuyển thành tùy chọn chủ động, mặc định tắt. Nếu không bật, việc
  chọn nhiều mã vẫn chỉ chạy mã chính. Portfolio bị vô hiệu hóa trong
  Validation, luôn mang lifecycle `RESEARCH_ONLY`, không có action áp cấu hình
  đơn mã và có manifest `backtest-advanced-research-v1` để truy vết.
- Monte Carlo tự chạy khi kết quả có ít nhất 30 lệnh hoặc chạy khi người dùng
  yêu cầu rõ ràng. Trường hợp thiếu mẫu được lưu thành `SKIPPED` cùng số lệnh,
  ngưỡng và lý do, thay vì tốn 2.000 lượt mô phỏng không cần thiết.
- Sweep mặc định dùng đúng khoảng ngày trên form Backtest và mã chính; người
  dùng có thể chủ động chọn các giai đoạn mẫu hoặc toàn bộ mã đã chọn.
- Sweep nhận `BacktestRequest` do controller tạo nên dùng chung broker symbol,
  balance/risk, spread, slippage, commission, swap, lot/contract và account
  guard với Backtest chính. Backtest và sweep cũng dùng chung loader lịch sử
  `backtest-history-loader-v1` với cùng warm-up, cache và chunk M15.
- Kết quả/checkpoint sweep được nâng lên
  `parameter-sweep-v2-shared-context`, luôn `RESEARCH_ONLY`,
  `can_apply_config=false`, và lưu dataset hash, request fingerprint,
  provenance fingerprint, execution mode, symbol cùng khoảng thời gian.
- Cơ chế process riêng, cancel, timeout, checkpoint/resume vẫn được giữ nguyên;
  version cache được tăng để không tái sử dụng nhầm checkpoint từ contract cũ.
- Kiểm thử mới bao phủ điều kiện Monte Carlo, shared request context, lifecycle
  và provenance của sweep/checkpoint, portfolio opt-in và guard Validation.
  Nhóm hồi quy Phase 0–4/portfolio/Monte Carlo: **60 passed, 0 failed**;
  full test suite: **1607 passed, 12 skipped, 17 xfailed, 0 failed**;
  `compileall` và `git diff --check` đạt. Năm warning pytest/thư viện là warning
  hiện hữu, không phải failure của Giai đoạn 4.

### Giai đoạn 5 — Xóa code chết và migration flag cũ

Mục tiêu: giảm chi phí bảo trì sau khi luồng mới đã ổn định.

Công việc:

- xóa method, dialog, import và scratch script đã xác nhận không dùng;
- bỏ kết nối signal vào method no-op;
- deprecate/migrate feature flag cũ;
- giữ khả năng đọc Settings và snapshot cũ;
- chạy tìm kiếm reference và test import.

Tiêu chí đóng:

- không còn caller/reference chết;
- Settings cũ tải không lỗi;
- Router không phụ thuộc flag cũ;
- không làm mất evidence lịch sử.

Độ phức tạp: **Trung bình**.

#### Kết quả thực hiện Giai đoạn 5

Trạng thái: **Hoàn thành ngày 25/07/2026**.

- Xóa signal và `_on_tab_changed()` no-op; xóa các method không có caller
  `_section_box()`, `_field_cell()`, `_symbol_cell()`,
  `_build_equity_curve_html()`, `_do_apply_config()`, `_show_input_help()`;
  xóa `BacktestInputHelpDialog` đã lỗi thời.
- Xóa các hook style/visibility no-op gồm `set_equity_chart_visible()`,
  `_refresh_progress_bar_style()` và `_refresh_tab_styles()` cùng caller tương
  ứng. Biểu đồ Matplotlib hiện hành và action áp cấu hình đơn mã vẫn được giữ.
- Xóa script vá tạm đã được baseline xác nhận không dùng:
  `scratch/fix_backtest_screen.py`.
- Loại `backtest_config_v2` và `backtest_engine_v2` khỏi
  `FeatureFlagSettings`, Settings loader và Scanner observability. Settings cũ
  có hai key này vẫn tải bình thường; lần lưu tiếp theo không ghi lại chúng.
- Giữ nguyên `scanner_architecture_v2`, `auto_trade_v2` và
  `smc_scoring_mode` vì vẫn thuộc contract Scanner hiện hành.
- Strategy Router không đọc hai flag Backtest cũ. Quyền dùng cấu hình vẫn chỉ
  dựa trên lifecycle/schema/provenance của cấu hình Backtest.
- Khi cấu hình lịch sử không còn đạt schema hiện hành, loader vẫn fail-closed
  (`VERSION_MISMATCH`, `backtest=false`) nhưng giữ fingerprint/evidence cũ để
  audit và migration; snapshot cũ tiếp tục được chuyển thành
  `LEGACY_RESEARCH`, không thể phát hành.
- Test Phase 5 khóa reference cleanup, đọc-cũ/ghi-mới Settings, bảo toàn cấu
  hình symbol/evidence, độc lập của Router và snapshot migration. Nhóm hồi quy
  Backtest/Settings/Router liên quan: **98 passed, 0 failed**; full test suite:
  **1612 passed, 12 skipped, 17 xfailed, 0 failed**; `compileall`, reference
  audit và `git diff --check` đạt. Năm warning pytest/thư viện là warning hiện
  hữu, không phải failure của Giai đoạn 5.

### Giai đoạn 6 — Kiểm thử, tài liệu và nghiệm thu

Mục tiêu: chứng minh thay đổi không làm sai Backtest hoặc Scanner.

Công việc:

- unit test Trading Session/DataManifest;
- UI test cho mode và lifecycle;
- integration test Backtest → config → Strategy Router;
- migration test Settings/snapshot;
- smoke test dữ liệu MT5 Forex, XAU và JPY;
- full test suite, compileall và diff check;
- cập nhật product spec, architecture, workflow và tài liệu Backtest.

Tiêu chí đóng:

- full suite không có failure;
- false-positive cuối tuần được xử lý;
- gap thật vẫn bị chặn;
- Research không phát hành config;
- Validation tạo đúng evidence;
- tài liệu khớp chương trình.

Độ phức tạp: **Trung bình–cao**.

#### Kết quả thực hiện Giai đoạn 6

Trạng thái: **Hoàn thành và nghiệm thu ngày 25/07/2026**.

- Bổ sung acceptance test cuối cho: false-positive cuối tuần và gap thật trong
  phiên; Validation ép execution parity + IS/OOS + Walk-Forward; Research và
  workload nâng cao không phát hành; config `VALIDATED` đi xuyên suốt tới
  `BACKTEST_VALIDATED`; Settings/snapshot cũ vẫn fail-closed và giữ evidence.
- Nhóm hồi quy Phase 6 gồm Trading Session/DataManifest, UI/lifecycle,
  advanced research, migration và Backtest → Strategy Router:
  **84 passed, 0 failed**.
- Ngày 26/07/2026, toàn bộ UI Backtest được chuẩn hóa tiếp bằng
  `ui/layout_system.py`: form chính dùng grid ba hàng/cột label thẳng; hai card
  nghiên cứu cân bằng; input/button/checkbox cao 32 px; progress/help lần lượt
  20/24 px; icon 16 px; table header/row 32/36 px; chart tối thiểu 240 px.
  Ba dialog dùng chung margin 16 px, spacing 12 px và button metrics. Phần chi
  phí Backtest trong Settings dùng cùng form token. 14 UI test bảo vệ sáu vùng
  làm việc từ `1110x700` tới `3200x1800`, dữ liệu lớn nhất, bảng/chart và toàn
  bộ dialog.
- Smoke trực tiếp MT5 trên khoảng `[25/01/2026,25/07/2026)` đạt cho ba nhóm:
  - `EUR/USD → EURUSDc`: D1 600, H4 3.085, H1 11.921, M15 18.515 nến;
  - `USD/JPY → USDJPYc`: D1 601, H4 3.086, H1 11.922, M15 18.515 nến;
  - `XAU/USD → XAUUSDc`: D1 598, H4 3.066, H1 11.332, M15 17.557 nến.
  Cả ba đều `quality_status=OK`, `validation_eligible=true`, không issue và
  không có `UNEXPECTED_DATA_GAP` trên D1/H4/H1/M15.
- Đồng bộ `product_spec.md`, `architecture.md`, `workflow_guide.md`,
  `system_backtest_design.md`, `README.md` và `runtime-status.md` với runtime:
  portfolio opt-in, Monte Carlo có điều kiện, sweep dùng context chung và hai
  feature flag Backtest cũ đã được migration khỏi runtime.
- Full test suite cuối: **1631 passed, 12 skipped, 17 xfailed, 0 failed**;
  `compileall`, reference audit và `git diff --check` đạt. Năm warning
  pytest/thư viện là warning hiện hữu, không phải failure.
- Không hạ hoặc bỏ qua release gate, forward-demo, execution gate, news,
  account hay portfolio guard. Việc nghiệm thu Backtest không đồng nghĩa tự
  cấp quyền đặt lệnh production.

## 10. Thứ Tự, Phụ Thuộc Và Ước Lượng

Thứ tự bắt buộc:

`Giai đoạn 0 → 1 → 2 → 3 → 4 → 5 → 6`

Không dọn UI hoặc xóa code trước khi hoàn thành baseline. Không coi Validation
đã hoạt động chỉ bằng cách bỏ qua warning data gap. Giai đoạn 4 chỉ bắt đầu khi
contract Research/Validation ở Giai đoạn 2 đã ổn định.

Ước lượng tổng: **9–14 ngày làm việc**, chưa bao gồm thời gian thu thập
forward-demo. Độ phức tạp tổng thể: **Cao**.

## 11. Rủi Ro Và Biện Pháp Kiểm Soát

| Rủi ro | Biện pháp |
|---|---|
| Bỏ qua gap thật khi sửa lịch phiên | Policy có version, test gap trong phiên và fail-closed |
| DST/ngày lễ khác giữa broker | Tách session policy, lưu fingerprint và cho phép cấu hình broker |
| UI gọn làm mất dữ liệu audit | Chỉ giảm hiển thị nhanh; giữ đầy đủ JSON và tab chi tiết |
| Settings cũ không tương thích | Migration đọc-cũ/ghi-mới và fixture Settings cũ |
| Sweep tiếp tục dùng contract khác | Dùng chung request factory và đánh dấu `RESEARCH_ONLY` |
| Người dùng hiểu DRAFT là đã kích hoạt | Đổi nhãn hành động và không enable Router khi chưa `VALIDATED` |
| Xóa nhầm code có caller gián tiếp | Tìm reference, characterization test và xóa theo từng commit nhỏ |

## 12. Điều Kiện Hoàn Thành Toàn Bộ

Task chỉ được đóng khi:

- Trading Session Calendar xử lý đúng cuối tuần, DST và gap trong phiên;
- Research/Validation có một contract rõ ràng, không còn control trùng nghĩa;
- Validation tự chạy toàn bộ IS/OOS và Walk-Forward bắt buộc;
- hành động trên UI khớp lifecycle;
- công cụ nghiên cứu nâng cao không can thiệp phát hành config;
- code chết và flag cũ được migration an toàn;
- full test suite xanh;
- smoke test MT5 đạt;
- tài liệu hiện hành được cập nhật;
- release gate và yêu cầu forward-demo không bị hạ hoặc bỏ qua.
