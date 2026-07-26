# Rà Soát Và Kế Hoạch Nâng Cấp Backtest

> Trạng thái: **Đã hoàn thành kỹ thuật Giai đoạn 0 đến 7; Phase 7 chờ bằng
> chứng forward-demo thực tế để đóng vận hành**
>
> Ngày rà soát: **25/07/2026**
>
> Phạm vi: màn hình Backtest, controller/worker, engine replay, mô phỏng
> khớp lệnh, IS/OOS, Walk-Forward, Monte Carlo, parameter sweep và luồng
> áp dụng cấu hình Backtest vào Scanner.

## 1. Kết Luận

Backtest hiện tại đã đáp ứng tương đối đầy đủ nhu cầu **nghiên cứu và phân
tích chiến lược**:

- lấy dữ liệu lịch sử D1/H4/H1/M15 từ MT5;
- replay pipeline phân tích thật và SMC v2;
- mô phỏng entry, SL/TP và tính kết quả theo R;
- có equity curve, breakdown, diagnostics và funnel;
- có Monte Carlo, Walk-Forward và parameter sensitivity;
- lưu snapshot riêng, không ghi vào journal giao dịch thật;
- có lifecycle `DRAFT`/`VALIDATED`, version, fingerprint, expiry và cơ chế
  fail-closed khi Strategy Router nhận config không hợp lệ.

Engine validation hiện đã có point-in-time data, event ordering, execution
parity, frozen OOS replay, thống kê, portfolio và release gate. Kết quả
`RESEARCH` vẫn chỉ dùng phân tích. Kết quả `VALIDATION` chỉ được phát hành
thành config `VALIDATED` sau khi báo cáo Phase 7 chứng minh golden replay,
shadow và forward-demo đều đạt ngưỡng, đồng thời có người review phê duyệt.
Config cũ hoặc config thiếu release report bị hạ trạng thái fail-closed.

### Đánh giá theo mục đích

| Mục đích | Mức đáp ứng | Kết luận |
|---|---|---|
| Nghiên cứu tín hiệu và xem funnel | Tốt | Có purpose `RESEARCH`, diagnostics và provenance rõ ràng |
| So sánh tương đối tham số | Tốt | Sweep chạy process-isolated, tham số risk bất biến |
| Ước lượng hiệu quả giao dịch thực | Khá | Có execution parity; vẫn phải đối soát demo theo broker |
| Xác thực OOS/Walk-Forward | Tốt | Config được đóng băng và replay trên OOS theo thời gian |
| Tạo config Scanner production | Có kiểm soát | Chỉ mở khi release report Phase 7 `ready=true` |
| Backtest portfolio nhiều mã | Đã hỗ trợ | Có batch, portfolio clock và account guard dùng chung |

## 2. Những Điểm Đã Làm Tốt

### 2.1. Tái sử dụng pipeline thật

`core/system_backtest_engine.py` gọi `analyze_symbol()` thay vì viết một
scoring engine riêng. Đây là nền tảng đúng để giảm sai khác giữa backtest và
Scanner.

### 2.2. Quản lý lifecycle config theo hướng fail-closed

Config chỉ được Strategy Router dùng khi:

- đúng symbol, schema, scorer và feature version;
- đúng SMC scorer/mode;
- có khoảng IS/OOS hợp lệ;
- đủ sample và metrics;
- có confidence interval và Walk-Forward;
- fingerprint hợp lệ;
- chưa hết hạn.

Config `DRAFT`, hết hạn hoặc sai version vẫn có thể được giữ để xem lại nhưng
không đủ điều kiện auto trade.

### 2.3. Diagnostics và khả năng giải thích

Backtest lưu:

- gate funnel;
- số snapshot/setup/lệnh;
- pipeline pass/fail/warning;
- gate fail counts;
- skipped setup và debug context;
- breakdown theo side, regime, score, R:R và SMC.

Đây là dữ liệu tốt để tìm nguyên nhân không có lệnh hoặc một gate lọc quá
nhiều.

## 3. Những Vấn Đề Cần Sửa

### P0 — Ảnh hưởng trực tiếp đến tính đúng

#### BT-P0-01 — Có nguy cơ nhìn trước dữ liệu đa khung

Trạng thái: **Đã xử lý ở Giai đoạn 1**.

Trước Giai đoạn 1, MT5 gắn timestamp theo **thời điểm mở nến** trong khi
snapshot lấy mọi nến có `candle.time <= moment`. Runtime hiện đã chuyển sang
`close_time <= decision_time`, UTC và `[start, end)`.

Kết quả: score, regime, SMC zone và entry plan không còn nhận nến đa khung
đang hình thành; regression test khóa hành vi này cho cả bốn timeframe.

#### BT-P0-02 — Sai thứ tự sự kiện trên nến khớp entry

Trạng thái: **Đã xử lý ở Giai đoạn 2**.

Trước Giai đoạn 2, entry được xác nhận và khớp tại close nhưng cùng nến đó
được dùng để xét SL/TP. Runtime hiện chỉ bắt đầu đánh giá exit từ nến
execution kế tiếp và lưu event sequence có thứ tự.

Kết quả: high/low có trước fill không còn tạo win/loss.

#### BT-P0-03 — Scenario backtest không bảo đảm giống Scanner

Trạng thái: **Đã xử lý ở Giai đoạn 2**.

Trước Giai đoạn 2, nếu không tìm được scenario đúng `best_side`, engine có
thể:

- lấy scenario buy/sell đầu tiên còn lại; hoặc
- dựng synthetic scenario từ giá và ATR.

Runtime hiện bắt buộc exact-side. Synthetic fallback được gắn
`research_only=true`, chỉ sinh trong `RESEARCH` và bị validator loại khỏi
dataset/config validation.

#### BT-P0-04 — OOS đang lọc lại kết quả thay vì replay

Trạng thái: **Đã xử lý ở Giai đoạn 4**.

Config được chọn trên IS rồi OOS được đánh giá bằng cách lọc danh sách trade
đã chạy sẵn. Cách này không tương đương với chạy lại engine:

- trade bị loại trước đó có thể đã chiếm thời gian và chặn setup sau;
- balance và compounding thay đổi;
- account guard và chuỗi thua thay đổi;
- thứ tự candidate được chấp nhận thay đổi.

#### BT-P0-05 — Walk-Forward chưa tối ưu IS rồi khóa config

Trạng thái: **Đã xử lý đầy đủ qua Giai đoạn 4–5**. Giai đoạn 4 hoàn tất
optimize/freeze/replay; Giai đoạn 5 chuyển sang calendar window và khử trùng
lặp OOS aggregate.

Mỗi window hiện chỉ chạy cùng một `BacktestRequest` cho IS và OOS. Không có
bước lấy IS để tạo strategy config, đóng băng config rồi replay OOS.

Tác động: kết quả là rolling performance check, chưa phải Walk-Forward
validation theo đúng nghĩa.

#### BT-P0-06 — Research sample đang được dùng cho live validation

Trạng thái: **Đã xử lý ở Giai đoạn 4**. Candidate nghiên cứu vẫn được ghi vào
ledger để phân tích nhưng frozen validation loại `research_only` và chỉ tính
OOS metric từ trade execution-parity đã thực thi.

Backtest chấp nhận cả `WATCH_ONLY`, `WAITING_CONFIRMATION`,
`AGGRESSIVE_SETUP`, permission `caution` và entry `watch_zone`. Đây là tập mẫu
nghiên cứu rộng hơn tập lệnh mà live execution thực sự gửi.

Tác động: threshold được tối ưu trên phân phối khác với production.

### P1 — Ảnh hưởng lớn đến độ thực tế

#### BT-P1-01 — Chi phí và execution model còn đơn giản

Trạng thái: **Đã xử lý phần execution cost ở Giai đoạn 3**.

- spread theo symbol/phiên, slippage vào/ra, commission và swap đã được mô phỏng;
- lot được làm tròn theo step và chặn theo minimum/maximum volume;
- báo cáo tách `gross_r`, `cost_r`, `net_r` và chi phí theo tiền tài khoản;
- chỉ xử lý TP1, chưa mô phỏng partial TP, breakeven hoặc trailing.

#### BT-P1-02 — Account guard không theo Settings

Trạng thái: **Đã xử lý ở Giai đoạn 3**.

Controller bật account guard cho execution-parity và ánh xạ trực tiếp giới hạn
ngày/tuần, chuỗi thua và open-risk từ `TradingSettings`. Guard dùng kết quả
ròng sau chi phí để cập nhật lịch sử đóng lệnh.

#### BT-P1-03 — Đơn vị “bar” thay đổi theo dữ liệu sẵn có

Trạng thái: **Đã xử lý ở Giai đoạn 2**.

Runtime dùng `setup_expiry_minutes` và `max_holding_minutes`; execution
timeframe được ghi rõ trong contract. Hai field `*_bars` chỉ còn để tương
thích API cũ, không chi phối luồng runtime mới.

#### BT-P1-04 — Feature parity chưa đầy đủ

- macro lịch sử chưa được replay;
- correlation mặc định bị tắt;
- tỷ giá quote/account đã dùng candle H1 đóng tại thời điểm quyết định/fill/exit;
- scorer/feature contract vẫn có thể mang cùng version với Scanner live.

Tác động: điểm và execution quality của backtest có thể không cùng phân phối
với live, đặc biệt với JPY và các cặp chéo.

#### BT-P1-05 — Monte Carlo đang trộn hai mục đích thống kê

Trạng thái: **Đã xử lý ở Giai đoạn 5**.

Monte Carlo hiện xáo thứ tự cùng một danh sách R. Cách này phù hợp để khảo sát
drawdown và chuỗi thua do thứ tự, nhưng:

- expectancy không đổi;
- win rate không đổi;
- profit factor không đổi;
- xác suất expectancy âm chỉ có thể gần 0% hoặc 100%.

Các phân phối đó không phải uncertainty estimate.

#### BT-P1-06 — Validation evidence chưa gắn chặt với dữ liệu nguồn

Trạng thái: **Đã xử lý ở Giai đoạn 5**. Provenance hiện khóa dataset, code
revision, request/risk config, scoring, frozen strategy và execution contract;
recency của `validated_to` được kiểm tra tại lúc phát hành và khi Router dùng.

Fingerprint bảo vệ các field của config nhưng chưa chứng minh config được tạo
từ đúng:

- file OHLC và phạm vi dữ liệu;
- broker/timezone;
- code commit;
- risk parameters;
- execution model;
- macro mode.

Ngoài ra, dữ liệu rất cũ vẫn có thể được cấp `validated_at=now` và hiệu lực
thêm 90 ngày.

### P2 — Kiến trúc, vận hành và UX

#### BT-P2-01 — Chưa hỗ trợ nhiều mã/portfolio thật

Controller nhận `list[BacktestRequest]` nhưng chỉ chạy request đầu tiên.
Portfolio risk, correlation exposure và concurrent positions chưa được replay.

#### BT-P2-02 — Lưu DRAFT có thể làm mã biến mất khỏi Scanner

Khi lưu config chưa đạt validation, `backtest=False` có thể kéo theo việc xóa
symbol khỏi `enabled_symbols`. Việc lưu bằng chứng nghiên cứu không nên tự đổi
danh sách mã đang quét.

#### BT-P2-03 — Parameter sweep sửa global state

Sensitivity scan dùng `setattr()` trực tiếp lên module `risk_engine` trong
background thread. Nếu Scanner chạy đồng thời, nó có thể đọc tham số thử
nghiệm. Việc restore cũng chưa nằm trong `finally` bao phủ toàn bộ sweep.

#### BT-P2-04 — Data quality validation còn yếu

Engine mới kiểm tra D1/H4/H1 có dữ liệu. Chưa kiểm tra:

- dữ liệu được sort;
- duplicate;
- timezone;
- OHLC hợp lệ;
- gap bất thường;
- coverage đầu/cuối;
- số lượng warmup theo feature;
- tỷ lệ thiếu M15.

Chunk M15 lỗi có thể bị bỏ qua mà không làm backtest fail.

#### BT-P2-05 — Test và tài liệu chưa đồng bộ

Tại thời điểm rà soát:

- 115 test liên quan đạt;
- 7 test UI backtest lỗi do fixture cũ không theo kịp widget/style mới;
- tài liệu vận hành ghi đồng thời backtest schema v3 và schema v4;
- tài liệu nói người dùng chọn riêng train/OOS nhưng UI chỉ có một khoảng
  `Từ/Đến`, còn code tự chia theo trade.

## 4. Kiến Trúc Đích

```text
Historical Data + Data Manifest
               |
               v
      Point-in-Time Snapshot
      (chỉ nến đã đóng)
               |
               v
         Candidate Ledger
  (lưu mọi candidate trước strategy filter)
               |
       +-------+--------+
       |                |
       v                v
 RESEARCH mode    EXECUTION_PARITY mode
 không cấp config  mô phỏng đúng live
                        |
                        v
            IS Strategy Optimization
                        |
                 Frozen Strategy
                        |
                        v
                 OOS Full Replay
                        |
                        v
              Walk-Forward Windows
                        |
                        v
        Statistical + Robustness Validation
                        |
                        v
           DRAFT hoặc VALIDATED config
                        |
                        v
               Scanner Strategy Router
```

### Nguyên tắc bắt buộc

1. Mọi quyết định phải có `decision_time`.
2. Mọi input phải có `available_at <= decision_time`.
3. Scenario dùng để vào lệnh phải đúng side và tồn tại trong output pipeline.
4. Synthetic/fallback candidate chỉ dùng cho nghiên cứu.
5. IS không được nhìn OOS.
6. OOS phải replay config đóng băng, không được lọc hậu nghiệm.
7. Chỉ `EXECUTION_PARITY` được phát hành `VALIDATED`.
8. Evidence phải truy ngược được đến data, code và parameter manifest.

## 5. Kế Hoạch Thực Hiện

Tổng cộng **8 giai đoạn**, đánh số từ 0 đến 7.

### Giai đoạn 0 — Khóa an toàn và chốt contract

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Mục tiêu: ngăn engine cũ tiếp tục tạo bằng chứng production trong khi thay đổi
kiến trúc.

Công việc:

- thêm `backtest_purpose = RESEARCH | VALIDATION`;
- kết quả hiện hành mặc định `RESEARCH`;
- chỉ `VALIDATION` + engine contract mới được phép tạo `VALIDATED`;
- định nghĩa `BACKTEST_ENGINE_VERSION` và schema config kế tiếp;
- ghi rõ current config schema bị invalid khi engine version đổi;
- chốt glossary: signal score, setup score, final score alias, strategy score;
- sửa tài liệu v3/v4 mâu thuẫn;
- bổ sung feature flag để rollout engine mới mà không ảnh hưởng Scanner.

Tiêu chí đóng:

- engine cũ không thể phát hành config mới đủ điều kiện live;
- config cũ được giữ lại nhưng hiển thị `DRAFT/VERSION_MISMATCH`;
- test chứng minh fail-closed;
- không thay đổi hành vi quét và đặt lệnh live hiện tại.

Độ phức tạp: **Trung bình**.

Kết quả thực hiện:

- thêm `core/backtest_contract.py` với purpose `RESEARCH/VALIDATION`;
- engine nghiên cứu tại thời điểm Giai đoạn 0 phát hành
  `system-backtest-v1-research`, `execution_parity=false` và
  `validation_eligible=false`;
- nâng config lên schema v5,
  `backtest-v5-execution-parity-v1` (sau đó được Giai đoạn 3 nâng tiếp lên
  schema v6/`backtest-v6-cost-parity-v1`);
- Router chỉ chấp nhận validation engine
  `system-backtest-v2-execution-parity`;
- config schema/engine cũ fail-closed và được giữ làm DRAFT/evidence;
- từng thêm feature flag dự phòng `backtest_engine_v2=false`; flag này đã hết
  vai trò và được migration loại khỏi runtime ở Giai đoạn 5 của kế hoạch tinh
  gọn Backtest;
- UI ghi rõ kết quả nghiên cứu không phát hành live;
- 159 kiểm thử Backtest/Router/Settings/SMC liên quan đạt; smoke contract
  `verify_two_branch.py` cũng đạt.

### Giai đoạn 1 — Point-in-time data engine

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Mục tiêu: loại bỏ future leak.

Công việc:

- định nghĩa duration và `close_time` chuẩn cho D1/H4/H1/M15;
- snapshot chỉ nhận nến có `close_time <= decision_time`;
- dùng interval `[start, end)` cho replay và IS/OOS;
- không dùng current forming candle;
- normalize UTC và sort/deduplicate dữ liệu;
- bổ sung `DataManifest` gồm coverage, gap, duplicate, timezone và hash;
- fail validation khi dữ liệu bắt buộc không đạt chất lượng.

Tiêu chí đóng:

- test đóng băng cho từng timeframe chứng minh không nhìn nến chưa đóng;
- boundary IS/OOS không có candle/trade trùng;
- kết quả không phụ thuộc thứ tự input candle;
- gap/duplicate/timezone lỗi được báo rõ.

Độ phức tạp: **Cao**.

Kết quả thực hiện:

- thêm `core/backtest_market_data.py`, định nghĩa duration và `close_time`
  chuẩn cho D1/H4/H1/M15;
- bump research engine thành
  `system-backtest-v1.1-point-in-time-research` để snapshot cũ/mới truy
  nguyên được;
- mọi snapshot chỉ chứa nến đã đóng:
  `close_time <= decision_time`, không còn dùng nến đang hình thành;
- replay và execution window dùng khoảng nửa mở `[start, end)`;
- nến execution phải bắt đầu sau khi quyết định tồn tại và đóng trước biên
  cuối kỳ, nên IS/OOS không dùng chung nến tại boundary;
- toàn bộ timestamp được chuẩn hóa UTC, dữ liệu được sort và deduplicate theo
  quy tắc xác định nên không phụ thuộc thứ tự provider trả về;
- macro correlation context, khi được bật, cũng được cắt point-in-time theo
  nến D1 đã đóng;
- kết quả có `DataManifest` gồm coverage, duration, gap, duplicate,
  timezone, OHLC quality và SHA-256 hash theo từng timeframe/toàn dataset;
- manifest version, point-in-time flag, quality status và dataset hash được
  đưa vào config fingerprint, persistence và Strategy Router; payload thiếu
  hoặc bị sửa sẽ fail-closed;
- `RESEARCH` được phép tiếp tục với cảnh báo có ghi trong manifest;
  `VALIDATION` fail-closed nếu manifest có lỗi hoặc cảnh báo chất lượng;
- ngày kết thúc người dùng chọn trên UI được chuyển thành 00:00 UTC của ngày
  kế tiếp để đúng contract `[start, end)`;
- bổ sung 14 kiểm thử point-in-time, bao phủ bốn timeframe, IS/OOS boundary,
  execution boundary, UTC, duplicate, gap, hash ổn định và fail-closed.
- bộ hồi quy Backtest/Router/Settings/SMC liên quan đạt **181 kiểm thử**;
  smoke `verify_two_branch.py` tiếp tục đạt.

### Giai đoạn 2 — Mô hình entry/exit đúng thứ tự

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Mục tiêu: bảo đảm fill, SL và TP chỉ dùng dữ liệu sau thời điểm lệnh tồn tại.

Công việc:

- chuẩn hóa event sequence: signal → setup active → entry confirmation → fill
  → exit;
- nếu fill tại close, bắt đầu xét SL/TP từ nến kế tiếp;
- nếu cần same-bar exit, phải có lower-timeframe/tick path hợp lệ;
- xử lý gap qua entry/SL/TP;
- định nghĩa rõ same-bar ambiguity policy;
- thay số bar bằng duration hoặc cố định execution timeframe;
- không fallback scenario khác side;
- đánh dấu synthetic scenario `research_only` và loại khỏi validation.

Tiêu chí đóng:

- không còn dùng high/low trước fill để xác định kết quả;
- exact-side invariant được test;
- validation dataset không chứa fallback trade;
- các case gap/same-bar có expected result rõ ràng.

Độ phức tạp: **Cao**.

Kết quả thực hiện:

- thêm `core/backtest_execution.py` với policy version
  `backtest-execution-sequence-v1`;
- chuẩn hóa event sequence
  `SIGNAL_DETECTED → SETUP_ACTIVATED → ENTRY_CONFIRMED → ENTRY_FILLED →
  EXIT_FILLED/POSITION_OPEN` và lưu trên từng trade;
- fill tại close xác nhận, SL/TP chỉ được xét từ nến execution kế tiếp;
- gap xuyên SL/TP khớp tại giá open; gap xuyên entry zone nhưng không có giao
  dịch trong zone không được fill;
- nếu một nến sau fill chạm cả SL/TP, policy được ghi rõ:
  `STOP_FIRST` mặc định, `TARGET_FIRST` chỉ dành cho nghiên cứu;
- runtime dùng duration `setup_expiry_minutes`/`max_holding_minutes` và ghi
  execution timeframe; validation bắt buộc M15;
- scenario phải khớp chính xác best side, không dùng scenario đối diện;
- synthetic fallback có `synthetic=true`, `research_only=true`, chỉ được tạo
  trong `RESEARCH`; engine/config validator cùng chặn nó trong validation;
- execution policy, fill/exit model, same-bar policy, timeframe và quyền dùng
  synthetic được đưa vào fingerprint, Settings và Strategy Router;
- bump research engine thành
  `system-backtest-v1.2-event-sequence-research`.
- bổ sung 16 kiểm thử execution sequence cho pre-fill high/low, BUY/SELL gap,
  same-bar policy, duration, invalid geometry, exact-side và synthetic
  validation guard, đồng thời khóa execution timeframe và ambiguity policy
  của chế độ validation.
- bộ hồi quy Backtest/Router/Settings/SMC liên quan đạt **199 kiểm thử**;
  smoke hai nhánh tiếp tục đạt.

### Giai đoạn 3 — Execution parity và chi phí thực tế

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Mục tiêu: mô phỏng gần với đường thực thi MT5.

Công việc:

- tách rõ `RESEARCH` và `EXECUTION_PARITY`;
- ánh xạ account guard từ Settings;
- thêm spread model theo symbol/session;
- thêm entry/exit slippage, commission và swap;
- dùng quote conversion đúng tại thời điểm giao dịch;
- mô phỏng lot step, minimum/maximum volume và contract size;
- ghi `cost_r`, `gross_r`, `net_r`;
- khóa execution model/version vào scoring provenance.

Tiêu chí đóng:

- cùng candidate và snapshot tạo cùng quyết định strategy/gate với Scanner;
- net result phản ánh đầy đủ chi phí cấu hình;
- account guard backtest cho kết quả tương thích test live;
- có báo cáo chênh lệch gross/net.

Độ phức tạp: **Rất cao**.

Kết quả thực hiện:

- thêm `core/backtest_execution_parity.py` với execution model
  `backtest-execution-parity-v1`, cost model `backtest-cost-model-v1` và quote
  conversion `point-in-time-close-v1`;
- tách `execution_mode=RESEARCH` và `EXECUTION_PARITY`; màn hình Backtest tạo
  request execution-parity nhưng vẫn giữ purpose `RESEARCH` cho tới khi có đủ
  OOS/Walk-Forward evidence;
- mô hình OHLC theo giá Bid: BUY trả spread khi vào, SELL trả spread khi thoát;
  spread nền lấy theo symbol và nhân hệ số phiên UTC;
- áp dụng adverse slippage riêng cho entry/exit, commission khứ hồi và swap
  theo số lần rollover, gồm Wednesday triple swap;
- position sizing dùng balance tại thời điểm lệnh, tỷ lệ rủi ro, contract size,
  quote/account rate tại thời điểm fill; lot được floor theo step và chặn
  min/max volume của broker;
- Controller lấy spread, volume step/min/max và contract size từ MT5, đồng thời
  ánh xạ toàn bộ account guard và cost settings;
- tỷ giá quote/account dùng candle H1 đã đóng tại decision/fill/exit; validation
  fail-closed nếu symbol cần quy đổi nhưng thiếu dữ liệu point-in-time;
- trade và summary ghi `gross_r`, `cost_r`, `net_r`, gross/net PnL, lot,
  commission, swap và spread/slippage cost; equity và account guard dùng net;
- cost manifest/fingerprint và quote-conversion fingerprint cùng
  execution/cost/conversion version được khóa
  vào contract, scoring provenance, Settings và Strategy Router; schema nâng
  lên `v6`, validation version `backtest-v6-cost-parity-v1`;
- màn hình kết quả Backtest hiển thị rõ Gross R, chi phí execution và Net R;
- bổ sung 10 kiểm thử Phase 3; bộ hồi quy Backtest/Router/Settings/SMC liên quan
  đạt **212 kiểm thử**, smoke hai nhánh tiếp tục đạt.

### Giai đoạn 4 — Candidate ledger và OOS replay

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Mục tiêu: thay hậu lọc trade bằng replay cấu hình đóng băng.

Công việc:

- lưu mọi candidate trước strategy filter vào `CandidateLedger`;
- lưu side-specific `setup_score` tường minh, không dựa vào alias;
- optimizer chỉ đọc IS candidate;
- tạo `FrozenStrategyConfig`;
- replay OOS từ đầu với frozen config;
- cập nhật balance, open-position state và account guard theo OOS path;
- lưu rejection reasons của frozen strategy;
- metrics OOS chỉ lấy từ execution-parity trades.

Tiêu chí đóng:

- thay đổi IS không làm optimizer nhìn OOS;
- OOS result là output của replay, không phải list filtering;
- min score được hiệu chỉnh và áp dụng trên cùng metric `setup_score`;
- cùng frozen config cho kết quả deterministic.

Độ phức tạp: **Rất cao**.

Kết quả thực hiện:

- thêm `CandidateLedgerEntry` trước strategy filter, có ID ổn định, nguồn
  `setup_score`, trạng thái base/frozen, lý do loại và trade mô phỏng;
- `side_setup_score()` chỉ đọc `side_scores[side].setup_score` hoặc
  `scenario_scores[side].setup_score`, tuyệt đối không dùng `final_score` làm
  alias;
- optimizer chỉ nhận IS ledger và sinh `FrozenStrategyConfig` bất biến, có
  `config_id` xác định từ symbol/regime/side/score/R:R;
- OOS được gọi lại qua `run_system_backtest()` với request mới, balance ban
  đầu sạch, không có closed trade/open position kế thừa và dùng cùng frozen
  config trong toàn bộ khoảng `[start,end)`;
- Walk-Forward đã theo chuỗi optimize IS → freeze → replay OOS; mỗi window lưu
  frozen config, candidate count và thống kê lý do loại;
- validator không còn cấp `VALIDATED` từ cách chia/lọc danh sách trade cũ;
  bắt buộc `validation_replay`, fingerprint của cả IS/OOS ledger và đối chiếu
  tập candidate đã thực thi với tập OOS trade;
- schema nâng lên `v7`, validation version
  `backtest-v7-frozen-oos-replay-v1`; Router fail-closed nếu thiếu version
  ledger/replay/frozen config hoặc không xác nhận `oos_replay=true`;
- bổ sung 10 kiểm thử Phase 4; bộ hồi quy Backtest/Router/Settings/SMC liên quan
  đạt **246 kiểm thử**.

### Giai đoạn 5 — Walk-Forward, Monte Carlo và validation

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Mục tiêu: tạo bằng chứng robustness đúng nghĩa.

Công việc:

- mỗi Walk-Forward window: optimize IS → freeze → replay OOS;
- dùng calendar period và half-open boundary;
- loại duplicate OOS trades giữa các window;
- tách:
  - permutation Monte Carlo cho sequence/drawdown;
  - bootstrap with replacement cho uncertainty/CI;
- bổ sung p-value hoặc probability-of-positive-edge phù hợp;
- tăng sample threshold hoặc dùng threshold theo statistical power;
- kiểm tra recency của `validated_to`;
- fingerprint gồm data/code/config/execution manifest;
- chỉ phát hành `VALIDATED` khi toàn bộ evidence đạt.

Tiêu chí đóng:

- Walk-Forward report chứa config riêng của từng IS window;
- OOS chưa bao giờ tham gia chọn config của chính window đó;
- expectancy/PF/WR bootstrap có phân phối thực, không còn bất biến;
- config bị từ chối khi dữ liệu quá cũ hoặc provenance thiếu.

Độ phức tạp: **Cao**.

Kết quả thực hiện:

- Walk-Forward dùng phép cộng tháng lịch thay cho `31 ngày`, giữ boundary
  `[start,end)` và `is_end == oos_start`;
- mỗi window lưu frozen config, nguồn tối ưu IS, trạng thái replay OOS, trade
  ID và lý do loại; aggregate OOS khử trùng lặp theo candidate/trade identity;
- báo cáo khóa version `walk-forward-calendar-v2`, số window thành công, số
  trade OOS duy nhất, số duplicate đã loại và fingerprint tập OOS;
- Monte Carlo được tách thành bootstrap có hoàn lại cho phân phối expectancy,
  profit factor, win rate và permutation không hoàn lại chỉ cho drawdown/chuỗi
  thua;
- bổ sung probability of positive edge, one-sided p-value và ngưỡng sample
  động theo effect/dispersion; validation fail-closed khi statistical power
  không đủ;
- từ chối phát hành config khi `validated_to` cũ quá 365 ngày hoặc nằm trong
  tương lai;
- thêm provenance manifest khóa dataset hash, code revision, request/risk,
  scoring, frozen config và execution contract bằng SHA-256;
- schema nâng lên `v8`, validation version
  `backtest-v8-statistical-validation-v1`; config v7 tự động version mismatch;
- bổ sung 7 kiểm thử Phase 5; bộ hồi quy mở rộng liên quan đạt **263 kiểm thử**.

### Giai đoạn 6 — Portfolio, parameter sweep và UI

Trạng thái: **Hoàn thành ngày 25/07/2026**.

Mục tiêu: hoàn thiện khả năng sử dụng và cô lập workload nghiên cứu.

Công việc:

- hỗ trợ batch nhiều symbol thật;
- thêm portfolio clock và concurrent positions;
- replay max open risk, symbol/currency/correlation exposure;
- chạy parameter sweep trong process riêng;
- truyền params qua immutable config thay vì monkey-patch global;
- có cancel, timeout, resume và cache dữ liệu;
- UI cho chọn purpose, execution model, IS/OOS và Walk-Forward;
- hiển thị rõ `RESEARCH_ONLY`, `DRAFT`, `VALIDATED` và lý do;
- lưu DRAFT không tự xóa symbol khỏi `enabled_symbols`.

Tiêu chí đóng:

- Scanner không thể đọc parameter đang sweep;
- batch result tổng hợp đúng theo symbol và portfolio;
- người dùng hủy được tác vụ dài mà không làm hỏng snapshot;
- lưu config không gây side effect ngoài lựa chọn được xác nhận.

Độ phức tạp: **Rất cao**.

Kết quả triển khai:

- `build_requests()` giữ toàn bộ danh sách mã duy nhất thay vì chỉ lấy mã đầu;
- batch replay riêng từng mã rồi ghép entry/exit trên một portfolio clock;
- portfolio kiểm soát tổng open risk, risk theo symbol, exposure tiền tệ,
  risk tương quan và số vị thế đồng thời; kết quả có tổng hợp theo mã và các
  lệnh bị từ chối kèm reason code;
- dữ liệu lịch sử được cache theo broker symbol/khoảng thời gian;
- parameter sweep chạy trong process `spawn` riêng, có timeout, cancel,
  checkpoint nguyên tử và resume theo tham số đã hoàn tất;
- sweep truyền `RiskParameterOverrides` bất biến theo execution context,
  không còn `setattr()` lên global của `risk_engine`, nên Scanner không thể
  đọc tham số nghiên cứu đang thử;
- Backtest worker cancel tại progress boundary và chỉ ghi snapshot khi hoàn tất;
- UI hỗ trợ nhiều mã, purpose, execution model, IS/OOS, Walk-Forward và nút
  hủy cho cả backtest lẫn sweep;
- lifecycle `RESEARCH_ONLY`/`DRAFT` cùng lý do được hiển thị; portfolio không
  cho áp nhầm thành config một mã;
- lưu DRAFT/expired/version-mismatch không còn tự gỡ symbol khỏi
  `enabled_symbols`; chỉ lựa chọn tắt đã xác nhận trên config `VALIDATED` mới gỡ.

Kiểm chứng Phase 6:

- 8 unit/integration test mới cho portfolio, batch, immutable sweep params,
  cancel và DRAFT membership;
- bộ hồi quy Backtest/Scanner/UI liên quan đạt **180 kiểm thử**;
- smoke UI Qt offscreen và `compileall` đạt;
- full suite toàn repository vượt giới hạn 120 giây của phiên kiểm tra nên chưa
  có kết luận xanh toàn bộ;
- ba test SL guard cũ trong `test_risk_engine.py` còn dùng giả định zone width
  trước execution sub-zone; đây là fixture/đặc tả cũ ngoài phạm vi Phase 6,
  không thay đổi ngưỡng production chỉ để ép các test này.

### Giai đoạn 7 — Migration, đối soát và rollout

Mục tiêu: đưa engine mới vào vận hành có kiểm soát.

Trạng thái kỹ thuật: **Đã hoàn thành ngày 25/07/2026**. Việc đóng vận hành còn
phụ thuộc dữ liệu forward-demo thực tế và báo cáo được duyệt `ready=true`.

Công việc:

- migrate snapshot cũ sang `LEGACY_RESEARCH`;
- hạ config contract cũ về `DRAFT/VERSION_MISMATCH`;
- golden replay trên fixture cố định;
- đối soát backtest với forward demo;
- đo slippage, fill rate, rejection rate và performance degradation;
- chạy shadow song song engine cũ/mới;
- cập nhật toàn bộ docs và hướng dẫn vận hành;
- chỉ mở phát hành config sau review report.

Đã triển khai:

- `core/backtest_migration.py` gắn snapshot cũ là `LEGACY_RESEARCH`, giữ
  nguyên evidence nhưng cấm phát hành config;
- `core/backtest_golden_replay.py` chạy fixture cố định, không cần MT5 và khóa
  fingerprint kết quả để chạy nhất quán trên Windows/CI;
- `core/backtest_release.py` đối soát candidate với lệnh demo, đo fill rate,
  rejection rate, adverse slippage và performance degradation; đồng thời so
  sánh shadow output engine cũ/mới;
- `scripts/backtest_release_report.py` tách snapshot validation khỏi snapshot
  forward cùng kỳ demo, tạo snapshot đã review và gắn release report có
  fingerprint;
- `scripts/export_mt5_forward_demo.py` chỉ xuất lệnh Scanner có correlation ID
  từ tài khoản demo; tài khoản thật bị từ chối fail-closed;
- release report trở thành một phần của validation fingerprint, Settings và
  Router. Config v8 cũ thiếu report bị hạ `VERSION_MISMATCH`; DRAFT chưa có
  report không thể kích hoạt;
- màn hình Backtest chỉ cho xem/phân tích snapshot legacy và ẩn thao tác áp
  dụng cấu hình;
- test chuyên biệt Phase 7 bao phủ migration, golden replay, reconciliation,
  shadow, tamper detection và fail-closed Router.

Runbook vận hành: `docs/backtest-release-runbook.md`.

Kiểm chứng tại thời điểm triển khai:

- full suite đã xanh ngày 25/07/2026: **1550 passed, 12 skipped, 17 xfailed,
  0 failed**; compileall và `git diff --check` đạt;
- 31 lỗi full-suite ban đầu đã được xử lý: 4 fixture Scanner được bổ sung release
  evidence; 27 test còn lại được đồng bộ với trailing state bắt buộc, UI
  compact, provider-adapter, chính sách không lộ reasoning, ticker `^IRX` và
  execution sub-zone. Test UI lỗi đầu vào cũng không còn mở modal thật trong
  test runner; cache market-data được khóa theo period, interval và downloader;
- MT5 hiện kết nối tài khoản thật `Exness-MT5Real36`, 74 lệnh đóng không có
  correlation ID; hai snapshot đang lưu đều là legacy. Exporter đã xác nhận
  từ chối tạo demo evidence từ trạng thái này;
- vì chưa có tài khoản demo cùng ít nhất 20 lệnh Scanner correlated và bộ
  snapshot validation/forward hiện hành, **Phase 7 chưa đủ điều kiện đóng vận
  hành**, dù phần lập trình đã hoàn tất.

Tiêu chí đóng:

- [x] test chuyên biệt và full test suite đều xanh;
- [x] không còn config legacy được Router chấp nhận;
- [x] replay deterministic trên Windows/CI;
- [ ] sai lệch backtest–demo nằm trong ngưỡng đã chốt;
- [ ] release report xác nhận `ready=true`.

Độ phức tạp: **Cao**.

## 6. Chiến Lược Kiểm Thử

### Unit test bắt buộc

- close-time filtering cho từng timeframe;
- timezone, duplicate, gap và coverage;
- exact-side scenario;
- không synthetic trade trong validation;
- entry-at-close không exit bằng high/low cũ;
- gap SL/TP;
- commission/spread/slippage/swap;
- half-open IS/OOS boundary;
- setup score contract;
- bootstrap/permutation;
- config fingerprint và expiry/recency.

### Integration test bắt buộc

- MT5 history → manifest → replay → snapshot;
- IS optimization → frozen config → OOS replay;
- Walk-Forward nhiều window;
- config result → Settings → Strategy Router;
- account guard parity;
- multi-symbol portfolio;
- cancel/retry worker;
- parameter sweep không ảnh hưởng Scanner.

### Golden test

Mỗi fixture cần cố định:

- OHLC và timezone;
- engine/scorer/feature version;
- execution costs;
- expected candidates;
- expected trades;
- expected metrics;
- expected validation status/reasons.

Golden fixture phải nhỏ để review được bằng tay và không phụ thuộc MT5 đang
online.

## 7. Migration Và Tương Thích

### Snapshot cũ

- không xóa;
- thêm nhãn `legacy_engine=true` khi tải;
- chỉ cho xem/phân tích;
- không cho phát hành config mới.

### Config cũ

- giữ nguyên evidence để audit;
- đổi trạng thái runtime thành `VERSION_MISMATCH` hoặc `DRAFT`;
- không tự chuyển sang schema mới;
- người dùng phải chạy lại validation bằng engine mới.

### Scanner

- branch chuẩn vẫn là `DEFAULT_RULES`, `BACKTEST_VALIDATED`,
  `BACKTEST_INVALID`;
- trong thời gian nâng cấp, symbol không có config mới tiếp tục dùng
  `DEFAULT_RULES`;
- không thay đổi execution/portfolio/rollout gate.

## 8. Rủi Ro Triển Khai

| Rủi ro | Cách kiểm soát |
|---|---|
| Kết quả mới xấu hơn đáng kể | Xem đây là sửa bias, không giữ compatibility số liệu sai |
| Backtest chạy chậm | Cache immutable data/snapshot, process pool và incremental replay |
| Snapshot lớn | Candidate ledger dạng compact, tách manifest và optional full analysis |
| Schema migration làm mất config | Chỉ hạ trạng thái, không xóa evidence |
| Khó đối soát với live | Gắn correlation ID và cùng candidate/execution contract |
| Sweep ảnh hưởng Scanner | Process isolation, immutable params |
| Thiếu dữ liệu macro lịch sử | Ghi rõ macro mode; không giả vờ feature parity |

## 9. Thứ Tự Ưu Tiên

Không nên làm UI hoặc portfolio trước khi sửa tính đúng cốt lõi.

Thứ tự bắt buộc:

1. Giai đoạn 0 — khóa an toàn.
2. Giai đoạn 1 — point-in-time data.
3. Giai đoạn 2 — entry/exit ordering.
4. Giai đoạn 3 — execution parity.
5. Giai đoạn 4 — OOS replay.
6. Giai đoạn 5 — validation/statistics.
7. Giai đoạn 6 — portfolio và UX.
8. Giai đoạn 7 — migration và rollout.

Các giai đoạn 1 và 2 có thể thiết kế song song nhưng chỉ merge khi dùng chung
time/event contract. Giai đoạn 4 phụ thuộc hoàn toàn vào 1–3. Giai đoạn 7 chỉ
bắt đầu sau khi 4–6 có test ổn định.

## 10. Ước Lượng Độ Phức Tạp

Đây là thay đổi kiến trúc **rất phức tạp** vì ảnh hưởng đồng thời data contract,
simulation, validation, Settings, Scanner Router, UI và dữ liệu đã lưu.

Ước lượng tương đối cho một kỹ sư làm tuần tự:

| Nhóm | Ước lượng |
|---|---:|
| Giai đoạn 0 | 2–3 ngày |
| Giai đoạn 1 | 5–8 ngày |
| Giai đoạn 2 | 5–8 ngày |
| Giai đoạn 3 | 7–12 ngày |
| Giai đoạn 4 | 7–12 ngày |
| Giai đoạn 5 | 5–8 ngày |
| Giai đoạn 6 | 8–14 ngày |
| Giai đoạn 7 | 5–8 ngày |
| Tổng có buffer kiểm thử | Khoảng 8–12 tuần |

Ước lượng không bao gồm thời gian chờ thu thập forward-demo evidence. Nếu chỉ
sửa P0 và phát hành một engine single-symbol, fixed-cost, chưa portfolio thì
có thể thu gọn xuống khoảng 3–5 tuần, nhưng vẫn phải chạy lại toàn bộ OOS trước
khi cấp config mới.

## 11. Điều Kiện Hoàn Thành Toàn Bộ

Task chỉ được xem là hoàn thành khi:

- không có future leak đã biết;
- entry/exit event ordering đúng;
- validation không chứa synthetic/opposite-side trade;
- OOS và Walk-Forward là replay config đóng băng;
- score metric giống hệt Scanner Router;
- chi phí và account guard có version rõ ràng;
- provenance truy được về data/code/config;
- config cũ fail-closed;
- full test suite xanh;
- tài liệu khớp chương trình;
- có report đối soát với forward demo;
- release report của backtest engine mới xác nhận đủ điều kiện phát hành
  `VALIDATED`.
