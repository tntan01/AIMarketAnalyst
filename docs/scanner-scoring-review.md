# Rà soát Scanner và hệ thống chấm điểm

> Cập nhật trạng thái 24/07/2026: đây là tài liệu review và nhật ký triển khai.
> Các phát hiện ở đầu file mô tả kiến trúc cũ tại thời điểm rà soát. Chín giai
> đoạn 0–8 đã hoàn tất về code/tooling; runtime contract sau nâng cấp nằm tại
> `docs/scanner-flow.md` và `docs/technical-scoring-architecture.md`. Mã nguồn
> vẫn mặc định `SHADOW`. Runtime trên máy hiện tại đã chọn `PRODUCTION`, nhưng
> release readiness còn `false`; vì vậy chưa được xem là production-ready và
> rollout guard vẫn chặn lệnh. Xem `docs/runtime-status.md`.
>
> Cập nhật SMC ngày 24/07/2026: decision path mặc định đã chuyển sang
> `smc-v2`, làm contract Scanner tăng thành
> `scanner-v3/scanner-features-v3`. Các đoạn `scanner-v2` bên dưới là nhật ký
> lịch sử; config đó hiện fail closed và phải được backtest/validation lại.
> 31 config `DRAFT` đã được tắt khỏi routing nhưng giữ nguyên metadata; Scanner
> hiện chạy `DEFAULT_RULES` với SMC v2, còn backtest/OOS sẽ thực hiện sau.

## Kết luận

Scanner có kiến trúc khá đầy đủ: đa khung thời gian, kỹ thuật/SMC, macro, gate rủi ro, journal feedback, backtest config, auto-scan, Telegram và AI Market Brief. Tuy nhiên:

- Chất lượng phân tích thủ công: khá.
- Độ tin cậy của điểm/xếp hạng: trung bình, chưa được hiệu chuẩn thống kê.
- Auto-trade: chưa nên dùng thực chiến trước khi xử lý các lỗi P0 trong tài liệu này.

Vấn đề lớn nhất không nằm ở một trọng số cụ thể, mà ở việc `signal_score`, `final_score`, `opportunity_score`, gate và backtest config đang dùng những ý nghĩa khác nhau nhưng chồng lấn hoặc so sánh lẫn nhau.

## Luồng điểm hiện tại

| Tầng | Vai trò | Công thức chính |
|---|---|---|
| `signal_score` | Chất lượng setup BUY/SELL | Kỹ thuật + SMC + rủi ro + macro |
| `final_score` | Tổng hợp setup với lịch sử | Signal 65% + Evidence 20% + Execution 15% |
| `opportunity_score` | Xếp hạng scanner | Final + proximity + readiness + RR + zone - spread/news |
| Gate/Decision | Cho phép hành động | MT5, tin, spread, M15, RR, score gap, zone, account guard |

Cách phân tầng hợp lý về mặt ý tưởng, nhưng triển khai hiện tại gây tính trùng và sai lệch ý nghĩa.

## Phát hiện nghiêm trọng

### P0 - Nhánh backtest có thể auto-trade setup đang `WATCH` hoặc `STAND_ASIDE`

Trong `controllers/scanner_controller.py`, nhánh có cấu hình backtest cố ý bỏ qua `scanner_action` và chỉ kiểm tra regime, điểm, RR và sự tồn tại của scenario.

Các test hiện tại khóa hành vi này như một yêu cầu: `stand_aside`, `watch`, `wait` đều được phép qua nhánh B trong `tests/test_symbol_override.py`.

Hậu quả:

- Bỏ qua kết luận của Decision Engine.
- Không bắt buộc `confirmed_entry`.
- Không bắt buộc `ready_to_trade=True`.
- `trade_permission="caution"` vẫn có thể vào lệnh.
- Gate `WATCH_ONLY` do RR/M15/zone không nhất thiết ngăn nhánh B.

Đây là rủi ro cao nhất của toàn bộ scanner.

### P0 - Có thể kiểm tra một hướng nhưng đặt lệnh hướng khác

Khi cấu hình ép BUY nhưng không có BUY scenario, `_best_scenario()` tự fallback sang scenario của `best_side`. Tuy nhiên `_execute_auto_trades()` vẫn giữ `trade_side` từ cấu hình để đặt lệnh.

Trường hợp xấu:

1. Config yêu cầu BUY.
2. Chỉ có SELL scenario.
3. Hàm trả SELL scenario.
4. Hệ thống gửi lệnh BUY với SL/TP được xây cho SELL.

Ngoài ra:

- `best_score` dùng để lọc là điểm của hướng tốt nhất, không phải hướng bị ép.
- `expected_effective_rr` trên row cũng có thể thuộc hướng tốt nhất, không phải hướng sắp giao dịch.
- Test hiện coi việc fallback sai hướng này là hành vi hợp lệ.

### P0 - Kiểm tra giá entry bằng giá snapshot cũ

Trước khi đặt market order, scanner dùng `analysis["technical"]["price"]` thay vì lấy tick mới. Sau một lượt quét nhiều mã và AI Market Brief, giá có thể đã rời vùng entry nhưng lệnh vẫn được gửi.

Lot cũng được tính theo trung điểm vùng, không phải giá khớp dự kiến hiện tại.

### P0 - Portfolio guard không nhận vị thế đang mở

Scanner gọi pipeline với `open_trades=[]`. Vì vậy `max_open_risk_pct` không thực sự phản ánh danh mục MT5 hiện tại.

Khi mở nhiều lệnh trong cùng lượt quét, guard cũng không được chạy lại sau mỗi lệnh. Hệ thống có thể vượt giới hạn rủi ro tổng hoặc tích lũy nhiều vị thế cùng exposure USD.

## Nhược điểm của tính năng chấm điểm

### 1. Tính trùng cùng một thông tin

Một số yếu tố được tính nhiều lần:

- Vị trí/zone: `location_quality`, `smc_quality`, gate zone và opportunity zone bonus.
- Spread/news: `risk_condition`, gate, sau đó tiếp tục bị trừ trong opportunity.
- Entry readiness: entry engine -> decision -> scanner group -> readiness bonus.
- Journal: evidence trong final score, sau đó lại decision cap và opportunity penalty.
- VIX/yield: macro tier và correlation adjustment cùng sử dụng.

Điều này làm điểm trông mạnh hơn nhưng không tăng lượng thông tin độc lập. Một tín hiệu sai có thể bị khuếch đại qua nhiều tầng.

### 2. Penalty spread/news của opportunity hiện gần như không hoạt động

Ranking đọc `spread_status`, `news_in_3h` và `high_impact_event_within_30m`.

Nhưng row tạo bởi `core/scanner.py` không đưa các trường này lên top-level, và ranking enrichment cũng không lấy chúng từ `analysis_result`.

Các unit test truyền thủ công những trường này nên vẫn pass về mặt logic, nhưng integration thực tế không áp dụng penalty như mô tả.

### 3. Xử lý dữ liệu lịch sử thiếu không nhất quán

`final_score` dùng trọng số cố định 65/20/15.

Trong pipeline:

- Evidence thiếu thường trở thành 50.
- Execution thiếu được thay bằng chính `signal_score`.
- Trong API độc lập, execution thiếu lại mặc định 100.

Vì vậy “không có dữ liệu” có ba cách diễn giải khác nhau. Evidence bằng 50 cũng kéo setup mạnh xuống và đẩy setup yếu lên, dù về lý thuyết phải là “không có ý kiến”.

Nên chuẩn hóa lại trọng số trên các thành phần thật sự có dữ liệu, đồng thời xuất riêng `coverage/confidence`.

### 4. `execution_quality` không phải thuộc tính của setup hiện tại

Execution quality đo lỗi hành vi lịch sử như chase giá, oversize, dời SL. Trộn nó trực tiếp vào chất lượng setup khiến cùng một thị trường có điểm khác chỉ vì hành vi cũ của trader.

Hợp lý hơn:

- Setup score đánh giá cơ hội thị trường.
- Execution quality điều chỉnh khối lượng/risk multiplier hoặc cảnh báo.
- Không dùng execution để thay đổi hướng BUY/SELL.

### 5. Điểm chưa phải xác suất và chưa được calibration

Các ngưỡng 50/65/80 là rule thủ công. Không có bằng chứng rằng:

- Điểm 80 tương ứng xác suất thắng khoảng 80%.
- Setup 70 trên XAU có chất lượng tương đương 70 trên EUR/USD.
- Khoảng cách 65 -> 70 có ý nghĩa tương đương 75 -> 80.

EMA, structure, RSI, MACD và SMC cũng có tương quan cao, nên tổng điểm không tương đương tổng bằng chứng độc lập.

### 6. Macro confidence vận hành ngược mô tả

Khi macro confidence thấp, trọng số macro bị giảm nhưng phần trọng số dư được phân phối lại cho kỹ thuật/risk trong `core/signal_engine.py`. Vì vậy thiếu macro không làm trần điểm thấp hơn; setup kỹ thuật vẫn có thể đạt gần 100.

Trong khi comment trong code lại nói dữ liệu macro yếu khiến tổng điểm tự nhiên thấp hơn. Code và thiết kế không thống nhất.

Ngoài ra pattern feedback thay đổi `macro_confidence` sau bước scoring nhưng không tính lại score, nên thay đổi này không tác động đến final score.

### 7. Phân rã điểm trên UI không cộng được về tổng

Signal score dùng trọng số động theo regime, nhưng màn chi tiết hiển thị component raw với max cố định. Trong volatile/range regime, các số hiển thị không phản ánh trọng số thực dùng tính tổng.

Màn Final Score còn đọc:

```python
final_detail.get("signal_score")
```

trong khi engine lưu chúng dưới `final_detail["score_inputs"]`. Với payload thật, ba thành phần có thể hiện `?`. Test không bắt được vì mock dùng cấu trúc phẳng không giống output thật.

### 8. `opportunity_score` vừa thiếu dữ liệu vừa tính lặp

Opportunity score có thang 0-120 nhưng bảng chỉ ghi “Điểm”, dễ bị hiểu là điểm chất lượng 0-100.

Ngoài ra:

```python
row.get("final_score") or row.get("best_score")
```

Khi `final_score=0`, biểu thức sẽ fallback sang `best_score`, có thể vô hiệu hóa final score hợp lệ bằng 0.

### 9. Bộ lọc làm trạng thái ranking bị stale

Sau khi opportunity đã được tính, `_apply_scanner_filters()` có thể đổi row thành `scanner_group="blocked"` nhưng không tính lại opportunity hoặc breakdown.

Kết quả có thể là:

- Nhóm: blocked.
- Opportunity score: vẫn rất cao.
- Breakdown: vẫn ghi readiness bonus.
- Reason code: vẫn mô tả nhóm cũ.

Sau đó UI lại sắp xếp theo “có plan/SMC” thay vì thứ tự engine. Một row blocked có plan có thể đứng trên row an toàn hơn.

### 10. Backtest config dễ overfit và dùng sai loại điểm

Bộ đề xuất:

- Chọn regime, side, min score và min RR trên cùng một mẫu.
- Chỉ cần 8 lệnh sau lọc.
- Không dùng out-of-sample để xác nhận cấu hình được chọn.
- Trade thiếu RR vẫn được xem là đạt mọi ngưỡng RR.

Nghiêm trọng hơn:

- Backtest tối ưu threshold bằng `final_score`.
- Scanner live kiểm tra threshold bằng `best_score`, tức signal score.

Đây là hai đại lượng khác nhau.

Cấu hình truyền sang `symbol_auto_trade` còn bỏ mất `min_rr`.

## Các vấn đề chức năng khác

- Snapshot loại bỏ toàn bộ `analysis_result`, khiến khó tái hiện hoặc audit điểm về sau.
- Snapshot không lưu scorer version, config hash, trọng số và dữ liệu đầu vào đầy đủ.
- Nút dừng auto-scan chỉ dừng lượt kế tiếp, không hủy lượt đang chạy.
- Market Brief chỉ lấy gate statistics từ row đầu tiên, không phải toàn thị trường.
- Ready/Watch/Wait được kiểm tra trong khoảng 0-100 nhưng không bắt buộc `Ready >= Watch >= Wait`.
- Exception tải từng symbol bị chuyển thành blocked row nhưng thiếu logging kỹ thuật phục vụ điều tra.

## Hướng nâng cấp đề xuất

### P0 - Khóa an toàn trước

1. Tạm vô hiệu hóa auto-trade nhánh B hoặc bắt buộc:

   - `decision == READY_TO_TRADE`
   - `entry_status == confirmed_entry`
   - `ready_to_trade is True`
   - `gate.allowed is True`
   - Không có decision cap
   - M15 strict
   - RR và score đạt trên đúng hướng giao dịch

2. Không bao giờ fallback sang hướng khác khi `force_side` được cấu hình.

3. Trước khi gửi lệnh:

   - Lấy tick/spread/news mới.
   - Chạy lại zone, RR, SL/TP và portfolio guard.
   - Tính lot bằng giá hiện tại.
   - Kiểm tra SL/TP đúng phía của lệnh.

4. Truyền `min_rr` đầy đủ và thống nhất dùng `signal_score` hoặc `final_score` từ backtest đến live.

5. Đưa bộ lọc vào trước ranking, sau đó chỉ có một lần enrich/sort. UI sử dụng nguyên thứ tự backend.

### P1 - Thiết kế lại hợp đồng điểm

Nên tách rõ:

- `setup_quality`: chất lượng kỹ thuật/macro, 0-100.
- `edge_confidence`: bằng chứng lịch sử và cỡ mẫu.
- `execution_readiness`: entry/M15/zone hiện tại.
- `eligibility`: gate boolean/cap.
- `opportunity_rank`: chỉ dùng sắp xếp, không dùng quyết định vào lệnh.

Không trộn execution history vào setup quality. Không cộng lại yếu tố đã được gate hoặc signal sử dụng.

Một mô hình mục tiêu hợp lý:

```text
calibrated_win_probability = calibrate(raw_setup_score, symbol_class, regime)
expected_value = p * effective_RR - (1 - p) - transaction_cost
opportunity_rank = percentile(expected_value * readiness * freshness)
```

Nếu chưa đủ dữ liệu để calibration, nên gọi là “điểm quy tắc” thay vì hàm ý xác suất.

### P2 - Calibration và backtest đúng chuẩn

- Dùng walk-forward/time-series split.
- Chọn threshold trên in-sample, báo cáo trên out-of-sample.
- Bootstrap confidence interval cho expectancy/PF.
- Tăng mẫu tối thiểu; không đưa cấu hình 8 lệnh vào auto-trade.
- Đánh giá calibration bằng Brier score, reliability curve và kết quả theo score bucket.
- Theo dõi riêng từng asset class/regime, sau đó shrink về global prior khi thiếu mẫu.
- Missing RR phải bị loại khỏi tối ưu RR, không được tự động pass.

### P3 - Minh bạch và kiểm thử

- Lưu immutable scan snapshot gồm input candles, freshness, config, scorer version và toàn bộ breakdown.
- UI hiển thị ba loại điểm với tên/thang đo rõ ràng.
- Breakdown phải dùng weighted component thực và cộng chính xác về tổng.
- Thêm invariant tests:

  - Blocked không bao giờ auto-trade.
  - Forced BUY không bao giờ dùng SELL scenario.
  - Thiếu dữ liệu không được làm điểm tăng.
  - RR thấp hơn không được làm rank tăng.
  - UI rank phải giống backend rank.
  - Payload thật phải hiển thị đủ final score components.
  - Stale tick hoặc spread mới bất thường phải chặn order.

## Đánh giá tại thời điểm rà soát ban đầu

Ở thời điểm rà soát ban đầu, scanner phù hợp làm công cụ hỗ trợ phân tích nếu
người dùng đọc cả gate, entry status và breakdown; chưa nên dựa vào riêng cột
“Điểm”. Các lỗi P0 của auto-trade nhánh backtest được mô tả ở trên đã được xử
lý trong Giai đoạn 0; các giới hạn còn lại được theo dõi trong bảng tiến độ.

Ghi chú lịch sử: ở thời điểm rà soát ban đầu chưa có thay đổi mã nguồn. Sau đó
Giai đoạn 0 đã được triển khai như ghi nhận trong phần theo dõi tiến độ bên
dưới. Full pytest đã được thử chạy ngày 24/07/2026 nhưng dừng ở collection:
`tests/test_be_trailing_integration.py` chạy kiểm tra ngay khi import rồi gọi
`sys.exit(1)` do 10/53 kiểm tra trailing legacy không đạt. Khi bỏ qua file đó,
collection tiếp tục vướng ba script-test legacy
(`test_orders_upgrade.py`, `test_redesign_overview.py`,
`test_upgrade_dialog.py`). Đây là blocker của test suite có sẵn, không thuộc
phạm vi Scanner Giai đoạn 7.

---

# Kế hoạch triển khai kiến trúc Scanner hoàn chỉnh

## Theo dõi tiến độ

Cập nhật lần cuối: **24/07/2026**.

| Giai đoạn | Trạng thái | Kết quả hiện tại |
|---|---|---|
| 0. Khóa an toàn và chốt đặc tả | **Đã hoàn tất code** | Contract `phase0-safety-v1` đã được tích hợp; unit/smoke test chuyên biệt đã đạt. Full pytest hiện bị chặn khi collection bởi các script-test legacy. |
| 1. Domain model chuẩn | **Đã hoàn tất code** | Đã có bốn domain model, điểm `setup_score` độc lập cho BUY/SELL và adapter payload lệnh dùng chung; 105 test mục tiêu đã đạt. Full pytest hiện bị chặn khi collection bởi các script-test legacy. |
| 2. Strategy Router hai nhánh | **Đã hoàn tất code** | Router chính thức trả đúng một trong `BACKTEST_VALIDATED`, `DEFAULT_RULES`, `BACKTEST_INVALID`; config legacy/expired/sai scorer fail-closed và 21 test Giai đoạn 2 đã đạt. |
| 3. Execution Readiness dùng chung | **Đã đóng phần code** | Auto-trade và lệnh manual chỉ còn một đường thực thi qua cổng `phase3-revalidation-v1`; kiểm thử kiến trúc chặn mọi đường gọi MT5 bỏ qua revalidation. |
| 4. Portfolio Risk Engine | **Đã hoàn tất code** | Engine `phase4-portfolio-v1` định giá position/pending/proposal bằng tick-value broker, kiểm soát projected risk, symbol/currency/correlation/order count và chạy lại sau mỗi lệnh. |
| 5. Backtest config lifecycle/validation | **Đã hoàn tất code** | Schema v4 và validator `phase8-smc-v2-oos-v1` đã tách IS/OOS theo thời gian, bắt buộc OOS/bootstrap CI/walk-forward, khóa rõ SMC v2, kiểm tra fingerprint và migrate config cũ về DRAFT. |
| 6. Ranking/UI một nguồn chuẩn | **Đã hoàn tất code** | Contract `phase6-ranking-v1` xếp hạng sau filters; backend, UI, preview lệnh, Telegram và Market Brief giữ cùng thứ tự/candidate payload. |
| 7. Observability và tái hiện | **Đã hoàn tất code** | Contract `phase7-observability-v1` đã gắn provenance cho scan/row/order, tự động lưu summary + full analysis, ghi structured events và hỗ trợ replay quyết định. |
| 8. Test, shadow mode và rollout | **Đã hoàn tất tooling/code** | Có V1/V2 shadow engine, rollout guard fail-closed, kill switch, canary risk cap, persistent metrics và release gate; demo soak/canary thật vẫn phải chạy trước production. |

Tiến độ tổng thể: **9/9 giai đoạn đã hoàn tất phần code**. Toàn bộ hệ thống chưa
được coi là xác nhận production cho đến khi full regression suite và kiểm tra
tích hợp trong môi trường có MT5/PyQt, shadow sample, demo soak và canary thật
hoàn tất.

Tài liệu đã được đồng bộ lại ngày **24/07/2026**:

- `scanner-flow.md`, `technical-scoring-architecture.md`, `product_spec.md` và
  `workflow_guide.md` là contract hiện hành của Scanner V2;
- `architecture.md`, `screen_design.md`, `installation_guide.md` và
  `system_backtest_design.md` đã bổ sung contract V2/rollout;
- nội dung Scanner V1 và kế hoạch MVP cũ được gắn nhãn lịch sử, không còn được
  dùng làm đặc tả runtime.

## Kiến trúc mục tiêu

```text
Market Analysis
      |
      v
Side Evaluation
 BUY và SELL độc lập
      |
      v
Strategy Router
 +-- BACKTEST_VALIDATED
 +-- DEFAULT_RULES
 +-- BACKTEST_INVALID
      |
      v
Execution Readiness
 Entry, M15, tick, spread, news
      |
      v
Portfolio Guard
 Open risk, exposure, correlation
      |
      v
Scanner Decision
 READY / WAITING / WATCH /
 OUT_OF_STRATEGY / BLOCKED
      |
      v
Ranking / Alert / Auto-trade
```

Controller chỉ điều phối. Các engine thuần chịu trách nhiệm đánh giá và trả kết quả có cấu trúc.

## Giai đoạn 0 - Khóa an toàn và chốt đặc tả

### Mục tiêu

Ngăn hành vi nguy hiểm trong khi kiến trúc mới đang được xây dựng.

### Công việc

- Thêm feature flags:

```text
scanner_architecture_v2
auto_trade_v2
backtest_config_v2
```

- Khi `auto_trade_v2=false`, giữ scan nhưng không cho nhánh backtest tự động đặt lệnh nếu Decision Engine không READY.
- Loại bỏ forced-side fallback trong auto-trade.
- Viết tài liệu chính thức về ý nghĩa:

  - `signal_score`
  - `final_score`
  - `opportunity_score`
  - `strategy_eligible`
  - `execution_ready`
  - `trade_allowed`
  - `auto_trade_candidate`

- Chốt metric dùng cho backtest và live. Khuyến nghị dùng một tên rõ ràng như `setup_score`, không dùng lẫn `best_score` và `final_score`.

### Hợp đồng chính thức của Giai đoạn 0

- `signal_score`: điểm tín hiệu thô theo từng hướng BUY/SELL; không trực tiếp cho phép đặt lệnh.
- `final_score`: điểm setup tổng hợp mà backtest hiện tại sử dụng để tối ưu ngưỡng.
- `setup_score`: tên chuẩn dùng khi so ngưỡng backtest với live; trong giai đoạn chuyển tiếp là alias tường minh của `final_score`.
- `opportunity_score`: điểm xếp hạng hiển thị trong scanner; không phải gate đặt lệnh.
- `strategy_eligible`: setup thỏa quy tắc chiến lược của nhánh
  `BACKTEST_VALIDATED` hoặc `DEFAULT_RULES`; `BACKTEST_INVALID` luôn false.
- `execution_ready`: Decision Engine trả `READY_TO_TRADE`, entry đã `confirmed_entry`, scenario có `ready_to_trade=true` và đủ entry/SL/TP.
- `trade_allowed`: scanner group, trade permission, journal cap và trade gate đều cho phép.
- `auto_trade_candidate`: chỉ đúng khi đồng thời `strategy_eligible`, `execution_ready` và `trade_allowed`.

Các bất biến an toàn luôn bật, không phụ thuộc feature flag. Ba cờ
`scanner_architecture_v2`, `auto_trade_v2` và `backtest_config_v2` chỉ là
ranh giới rollout cho các giai đoạn sau; rollback không được khôi phục hành vi
WATCH/WAIT đặt lệnh hoặc fallback sang hướng đối diện.

### Trạng thái triển khai

Giai đoạn 0 đã được triển khai ngày 24/07/2026 với contract
`phase0-safety-v1`:

- Dùng chung một evaluator fail-closed cho auto-trade, preview lệnh và Telegram.
- Giữ nguyên trạng thái scanner để WATCH/WAIT vẫn hiển thị nhưng không thể thành lệnh.
- Nhánh backtest bắt buộc READY như nhánh mặc định.
- Cấu hình hướng chỉ được dùng khi trùng hướng tốt nhất và có đúng scenario của hướng đó.
- Live dùng `setup_score` thay cho `best_score`; `min_rr` được truyền đầy đủ từ Settings.
- Kết quả scanner lưu feature flags, contract version và reason codes để audit.

Checklist triển khai:

- [x] Tạo safety evaluator fail-closed độc lập tại `core/scanner_safety.py`.
- [x] Bắt buộc `READY_TO_TRADE` cho cả nhánh mặc định và nhánh có backtest.
- [x] Chặn WATCH, WAIT, STAND_ASIDE và trade gate không cho phép.
- [x] Loại bỏ fallback từ hướng cấu hình sang scenario hướng đối diện.
- [x] Chốt `setup_score = final_score` trong giai đoạn chuyển tiếp.
- [x] Truyền `min_rr` và `score_metric` từ Settings sang request.
- [x] Dùng chung quyết định candidate cho auto-trade, preview lệnh và Telegram.
- [x] Giữ nguyên trạng thái scanner; không đổi WATCH/WAIT thành BLOCKED chỉ vì chưa thể đặt lệnh.
- [x] Thêm feature flags, contract version và reason codes phục vụ rollout/audit.
- [x] Cập nhật màn hình chi tiết để mô tả đúng vai trò của backtest config.
- [x] 15 test invariant an toàn chuyên biệt đã PASS.
- [x] Smoke test hai nhánh và kiểm tra cú pháp các file thay đổi đã PASS.
- [ ] Chạy trọn bộ pytest regression suite; hiện collection bị chặn bởi các
  script-test trailing/UI legacy nêu ở phần theo dõi tiến độ.
- [ ] Chạy kiểm tra tích hợp với PyQt/MT5 trong môi trường ứng dụng đầy đủ.

### Tiêu chí hoàn thành

- `WATCH`, `WAIT`, `STAND_ASIDE` không thể đặt lệnh.
- Forced BUY không thể sử dụng SELL scenario.
- Thiếu dữ liệu phải fail-closed.
- Có đặc tả trạng thái được thống nhất trước khi refactor.

## Giai đoạn 1 - Xây dựng domain model chuẩn

### Mục tiêu

Tạo một nguồn dữ liệu chuẩn thay cho các dictionary rời rạc.

### Trạng thái triển khai

Giai đoạn 1 đã hoàn tất phần code ngày 24/07/2026:

- `core/scanner_models.py` định nghĩa các model bất biến và sáu trạng thái chuẩn.
- `core/scanner_strategy_engine.py` dựng BUY/SELL độc lập và chọn đúng một hướng.
- `core/execution_readiness_engine.py` tách entry readiness khỏi trade permission.
- `core/scanner_candidate_engine.py` hợp nhất strategy và execution thành một quyết định.
- `core/scanner_safety.py` trở thành compatibility facade, nên contract an toàn Giai đoạn 0 không bị gián đoạn.
- Analysis pipeline xuất `side_scores.buy` và `side_scores.sell`; mỗi phía có
  `signal_score`, `evidence_score`, `execution_quality_score` và `setup_score`
  riêng. `final_score` cấp cao chỉ còn là alias tương thích của phía được chọn.
- Controller gắn `candidate_status`, `selected_side` và `scanner_candidate_decision` có cấu trúc vào mỗi row.
- Auto-trade, preview lệnh và Telegram dùng chung
  `build_candidate_order_payload()`, không tự chọn lại side hoặc parse
  scenario/entry/SL/TP riêng.
- Đã loại bỏ fallback scenario hướng đối diện ở scanner row, primary scenario và gate scenario của analysis pipeline.

Checklist triển khai:

- [x] Tạo `SideEvaluation` cho BUY và SELL độc lập.
- [x] Tạo `StrategyEvaluation`.
- [x] Tạo `ExecutionEvaluation`.
- [x] Tạo `ScannerCandidateDecision`.
- [x] Chuẩn hóa `READY_NOW`, `WAITING_CONFIRMATION`, `WATCH_ZONE`, `OUT_OF_STRATEGY`, `BLOCKED`, `DATA_UNAVAILABLE`.
- [x] Mỗi candidate có thể hành động có đúng một `selected_side`; row đứng ngoài hoặc thiếu dữ liệu để `selected_side=None`.
- [x] Tính `setup_score` riêng cho cả BUY và SELL từ evidence/execution feedback cùng phía.
- [x] `setup_score`, R:R, scenario, entry zone, SL và TP thuộc cùng hướng.
- [x] Không dùng gate result của hướng tốt nhất cho hướng đối diện.
- [x] Auto-trade, preview và Telegram dùng cùng một adapter tạo payload lệnh.
- [x] Duy trì API tương thích `evaluate_auto_trade_safety()`.
- [x] 17 test domain model Giai đoạn 1 đã PASS.
- [x] 8 test tích hợp analysis pipeline, bao gồm contract `side_scores`, đã PASS.
- [x] 15 test safety Giai đoạn 0 và smoke test hai nhánh vẫn PASS.
- [x] 57 test hồi quy tập trung liên quan Settings, Decision Engine, ranking và backtest đã PASS.
- [x] 8 test pipeline diagnostics đã PASS.
- [x] Chạy bằng pytest trên tập Scanner/pipeline/backtest liên quan: **105 passed**.
- [x] Kiểm tra cú pháp toàn bộ file thay đổi và `git diff --check` đã PASS.
- [ ] Chạy trọn full pytest; collection hiện bị chặn bởi bốn script-test
  legacy nêu ở phần theo dõi, không liên quan thay đổi Scanner Giai đoạn 1.
- [ ] Chạy kiểm tra tích hợp với PyQt/MT5 trong môi trường ứng dụng đầy đủ.

### Module đã triển khai

```text
core/scanner_models.py
core/scanner_strategy_engine.py
core/execution_readiness_engine.py
core/scanner_candidate_engine.py
```

### Các model chính

```python
@dataclass
class SideEvaluation:
    side: str
    signal_score: float | None
    final_score: float | None
    expected_effective_rr: float | None
    scenario: dict | None
    entry_status: str
    m15_quality: str
    gate_result: dict
    reason_codes: tuple[str, ...]
```

```python
@dataclass
class StrategyEvaluation:
    branch: str
    config_status: str
    selected_side: str | None
    score_metric: str
    score_value: float | None
    min_score: float | None
    expected_effective_rr: float | None
    min_rr: float | None
    eligible: bool
    reason_codes: tuple[str, ...]
```

```python
@dataclass
class ExecutionEvaluation:
    entry_ready: bool
    trade_allowed: bool
    live_price_valid: bool | None
    portfolio_allowed: bool | None
    reason_codes: tuple[str, ...]
    block_codes: tuple[str, ...]
```

```python
@dataclass
class ScannerCandidateDecision:
    status: str
    side_evaluation: SideEvaluation | None
    side_evaluations: tuple[SideEvaluation, ...]
    strategy: StrategyEvaluation
    execution: ExecutionEvaluation
    auto_trade_candidate: bool
    reason_codes: tuple[str, ...]
```

`selected_side`, `strategy_eligible`, `execution_ready`, `trade_allowed`,
`setup_score` và `scenario` được cung cấp dưới dạng property dẫn xuất từ các
model lồng nhau, tránh lưu hai bản dữ liệu có thể lệch nhau. Hai trường
`live_price_valid` và `portfolio_allowed` để `None` cho tới khi Giai đoạn 3-4
thực sự đánh giá; `None` không được hiểu là cho phép.

### Trạng thái chuẩn

```text
READY_NOW
WAITING_CONFIRMATION
WATCH_ZONE
OUT_OF_STRATEGY
BLOCKED
DATA_UNAVAILABLE
```

### Tiêu chí hoàn thành

- Controller và UI không tự suy luận lại candidate hoặc payload lệnh trong
  các đường auto-trade, preview và cảnh báo.
- Mỗi row có tối đa một `selected_side`; candidate có thể hành động bắt buộc
  có đúng một phía, còn row đứng ngoài/thiếu dữ liệu dùng `None`.
- Score, RR, scenario, SL và TP luôn thuộc cùng hướng.

## Giai đoạn 2 - Tách Strategy Router thành hai nhánh đúng nghĩa

### Trạng thái triển khai

Giai đoạn 2 đã hoàn tất phần code ngày 24/07/2026:

- `core/scanner_strategy_router.py` là nơi duy nhất chọn và đánh giá ba nhánh
  `BACKTEST_VALIDATED`, `DEFAULT_RULES`, `BACKTEST_INVALID`.
- Scanner output và decision snapshot ghi
  `strategy_router_version=phase2-router-v1`.
- Cấu hình backtest chỉ hợp lệ khi có `status=VALIDATED`,
  `scorer_version=scanner-v2`, đúng symbol và có đủ side/regime/min score/min
  RR/score metric.
- Cấu hình legacy thiếu metadata, DRAFT, expired, sai scorer hoặc sai schema
  được đưa vào `BACKTEST_INVALID`. Router vẫn lấy hướng theo default rules để
  hiển thị phân tích nhưng luôn đặt `strategy_eligible=false`, nên không thể
  tạo auto-trade candidate.
- `side=best` khóa hướng tốt nhất tại thời điểm route; cấu hình BUY/SELL cố
  định không được mượn scenario phía đối diện.
- Nhánh `DEFAULT_RULES` kiểm tra rõ best side, score gap, `setup_score` theo
  decision threshold và expected RR theo ngưỡng mặc định.
- Backtest config không còn ghi đè `READY/WATCH/WAIT` của Decision Engine;
  nó chỉ quyết định strategy eligibility.
- `core/backtest_config.py` tập trung việc đóng dấu config được áp dụng từ
  Backtest, serialize payload và làm config thành DRAFT khi người dùng sửa tay.
- Settings đã lưu được `config_id`, `status`, `scorer_version`,
  `validated_at`, `expires_at`. Đây là lifecycle tối thiểu cho router; kiểm
  định OOS/walk-forward đầy đủ vẫn thuộc Giai đoạn 5.
- Màn hình chi tiết hiển thị rõ `BACKTEST_CONFIG_INVALID` cùng reason codes.

Checklist triển khai:

- [x] Tạo Strategy Router chính thức và xóa logic chọn nhánh khỏi evaluator cũ.
- [x] Cài ba kết quả route loại trừ nhau.
- [x] Cài validation status, scorer version, expiry, symbol và schema.
- [x] Cài `side=best` và khóa selected side xuyên suốt quyết định.
- [x] Cài đầy đủ điều kiện cho `DEFAULT_RULES`.
- [x] Config invalid fallback phân tích mặc định nhưng chặn auto-trade.
- [x] Backtest config không còn thay đổi Decision Engine thresholds.
- [x] Gom serialize/stamp/invalidate config vào module lifecycle dùng chung.
- [x] Xóa kiểm tra regime/side/RR backtest lặp lại khỏi UI đặt lệnh.
- [x] Controller xuất `strategy_config_status` và
  `backtest_config_status=BACKTEST_CONFIG_INVALID` cho UI/audit.
- [x] 21 test chuyên biệt Giai đoạn 2 đã PASS.
- [x] 165 test mục tiêu Scanner/pipeline/backtest/UI liên quan đã PASS.
- [ ] Full pytest vẫn bị chặn khi collection bởi các script-test legacy đã
  ghi nhận ở phần theo dõi tiến độ.
- [ ] Chưa xác nhận tích hợp với MT5 thật; thuộc checklist production chung.

### Nhánh 1: `BACKTEST_VALIDATED`

Điều kiện:

```text
config.status == VALIDATED
AND config.scorer_version == live.scorer_version
AND regime phù hợp
AND side phù hợp
AND side_score >= config.min_score
AND side_rr >= config.min_rr
```

Quy tắc:

- Config BUY chỉ đánh giá BUY.
- Không có BUY scenario thì `eligible=false`.
- Không fallback sang SELL.
- Nếu `side=best`, chọn hướng tốt nhất rồi khóa hướng đó cho toàn bộ quá trình.
- Backtest config chỉ quyết định `strategy_eligible`; không quyết định entry đã sẵn sàng.

### Nhánh 2: `DEFAULT_RULES`

Điều kiện:

```text
best_side rõ ràng
AND score_gap >= min_score_gap
AND final_score >= decision threshold
AND expected_rr >= default min_rr
```

### Config không hợp lệ

Nếu config tồn tại nhưng expired/invalid:

- Scanner vẫn có thể phân tích bằng nhánh mặc định.
- `auto_trade_candidate=false`.
- UI hiển thị `BACKTEST_CONFIG_INVALID`.
- Không tự động coi config đó là nhánh 1.

### Tiêu chí hoàn thành

- Cả hai nhánh trả cùng một schema `StrategyEvaluation`.
- Không có logic backtest rải rác trong UI/controller.
- Một symbol chỉ thuộc một nhánh trong một lượt scan.

## Giai đoạn 3 - Execution Readiness dùng chung

### Trạng thái triển khai

**Trạng thái đóng: ĐÃ ĐÓNG PHẦN CODE ngày 24/07/2026.**

Việc xác nhận production bằng MT5 demo/news thật được chuyển sang gate rollout
ở Giai đoạn 8 và không còn chặn việc bắt đầu Giai đoạn 4.

- `core/execution_revalidation_engine.py` là cổng fail-closed duy nhất ngay
  trước khi gửi lệnh, có contract version `phase3-revalidation-v1`.
- `ExecutionMarketSnapshot` đóng băng một lần đọc MT5 gồm kết nối, quyền trade,
  bid/ask, tick time, spread, trade mode, quy tắc volume và trạng thái
  position/order của symbol.
- `ExecutionRevalidation` trả kết quả có cấu trúc gồm `allowed`,
  `execution_price`, effective RR mới, các guard và `block_codes`.
- `MT5Service.execution_snapshot()` phân biệt rõ “không có position/order” với
  “không đọc được trạng thái”; trường hợp thứ hai luôn chặn.
- `NewsService.execution_news_status()` kiểm tra cả khoảng trước và sau tin tác
  động cao theo cấu hình. Nguồn calendar không khả dụng sẽ chặn nếu news guard
  đang bật.
- `ScannerController.execute_order_candidate()` là đường thực thi dùng chung
  cho auto-trade và nút vào lệnh manual.
- Đã xóa toàn bộ auto-trade legacy và dead code manual-order cũ; Scanner chỉ
  còn đúng một điểm gọi `place_market_order()`, nằm sau kết quả
  `validation.allowed`.
- Lot được tính lại theo ask hiện tại cho BUY hoặc bid hiện tại cho SELL. Giá
  trong scan snapshot và midpoint của entry zone không tham gia quyết định cuối.
- Scan-time readiness đã được siết thêm: M15 phải `strict`, RR phải đạt đúng
  ngưỡng của Strategy Router, zone chưa broken, dữ liệu chưa stale và mọi
  `decision_cap` khác `None` đều chặn candidate.
- Account guard được chạy lại với journal và trạng thái MT5 hiện tại. Phase 3
  ban đầu chỉ áp dụng portfolio guard tối thiểu theo symbol. Từ Giai đoạn 4,
  cổng này nhận kết quả đầy đủ từ `Portfolio Risk Engine`.

Checklist triển khai:

- [x] Tạo immutable realtime market snapshot.
- [x] Tạo structured execution revalidation result và version contract.
- [x] Kiểm tra kết nối/account trade permission/symbol trade mode.
- [x] Kiểm tra tick tồn tại, tick age, bid/ask và spread hiện tại.
- [x] Dùng ask cho BUY, bid cho SELL và kiểm tra lại entry zone.
- [x] Kiểm tra news blackout cả trước và sau sự kiện.
- [x] Kiểm tra SL/TP đúng phía và tính lại effective RR sau spread.
- [x] Tính lại lot bằng execution price và kiểm tra min/max/step của broker.
- [x] Chặn khi không đọc được position/order hoặc symbol đã có exposure.
- [x] Chạy lại account guard ngay trước order.
- [x] Dùng chung một controller path cho auto-trade và manual order.
- [x] Xóa đường auto-trade legacy và dead code manual-order.
- [x] Thêm architecture guard xác nhận không có đường đặt lệnh bypass
  `execute_order_candidate()`.
- [x] Trả block reason có cấu trúc trong kết quả auto/manual.
- [x] 26 test Phase 3 mới/mở rộng đã đạt.
- [x] Regression tập trung Scanner/pipeline/backtest liên quan:
  **235 passed, 7 skipped**.
- [ ] Xác nhận bằng tài khoản MT5 demo thật và news calendar thật tại
  Giai đoạn 8 trước production rollout.
- [ ] Full pytest vẫn bị chặn bởi các script-test legacy đã ghi trong phần theo
  dõi chung; một nhóm test UI Backtest cũ cũng đang lệch fake widget contract,
  không phát sinh từ Execution Revalidation.

### Mục tiêu

Cả hai nhánh phải qua cùng một cổng thực thi.

### Điều kiện tối thiểu

```text
trade_gate.allowed is True
AND decision_cap is None
AND entry_status == confirmed_entry
AND ready_to_trade is True
AND m15_quality == strict
AND expected_effective_rr >= required_min_rr
AND zone chưa bị phá
AND dữ liệu chưa stale
```

Ngay trước khi đặt lệnh phải kiểm tra lại:

- Tick hiện tại.
- Bid/ask và spread hiện tại.
- Giá còn trong entry zone.
- News blackout.
- SL/TP đúng phía.
- RR sau spread vẫn đạt.
- Volume hợp lệ.
- Symbol chưa có position/order.
- Account và portfolio guard vẫn cho phép.

Không sử dụng giá trong snapshot để quyết định order cuối cùng.

### Tiêu chí hoàn thành

- Scan result chỉ là đề xuất; execution engine luôn revalidate.
- Bất kỳ dữ liệu realtime nào thiếu đều chặn order.
- Lý do chặn được trả về có cấu trúc, không chỉ là chuỗi lỗi.

## Giai đoạn 4 - Portfolio Risk Engine

### Trạng thái triển khai

Giai đoạn 4 đã hoàn tất phần code ngày **24/07/2026**:

- `core/portfolio_models.py` định nghĩa immutable `PortfolioRiskItem`,
  `PortfolioSnapshot` và structured `PortfolioEvaluation`.
- `core/portfolio_risk_engine.py` là engine thuần, contract version
  `phase4-portfolio-v1`.
- `MT5Service.portfolio_snapshot()` đọc đồng thời toàn bộ position và pending
  order, phân biệt portfolio rỗng với trạng thái không đọc được.
- Mỗi item được enrich bằng `trade_tick_size`, `trade_tick_value_loss` và
  contract size từ broker. Risk amount được quy đổi trực tiếp về deposit
  currency; không dùng contract-size approximation khi broker valuation thiếu.
- Position thiếu SL, item thiếu tick-value/tick-size, balance thiếu hoặc MT5
  không trả được portfolio đều fail-closed.
- Current open risk dùng khoảng cách từ current mark tới SL; position đã khóa
  lợi nhuận chỉ giữ phần downside risk còn lại.
- Proposed risk dùng ask hiện tại cho BUY hoặc bid hiện tại cho SELL và volume
  đã tính lại ở Giai đoạn 3.
- Engine tính cả current/projected total risk, risk theo symbol, directional
  exposure theo currency và correlation cluster giữa các symbol cùng exposure.
- Ví dụ BUY EUR/USD và BUY GBP/USD được gom vào cluster `USD short`, thay vì
  coi là hai rủi ro độc lập.
- Daily loss, weekly loss và consecutive losses được hợp nhất vào cùng một
  `PortfolioEvaluation`.
- Controller dùng live MT5 balance thay vì balance snapshot trong Settings để
  tính lot và projected risk.
- Guard được chạy trước order, snapshot/evaluate lại sau order thành công và
  chạy lại với trạng thái mới trước order kế tiếp.
- Auto/manual execution được bảo vệ bằng `RLock`; hai request đồng thời không
  thể cùng đọc portfolio cũ rồi đồng thời gửi lệnh.
- Scanner output ghi `portfolio_engine_version=phase4-portfolio-v1`.
- Settings legacy tự nhận các giới hạn an toàn mới; giá trị không hợp lệ được
  clamp khi load.

Checklist triển khai:

- [x] Đọc position và pending order thật từ MT5.
- [x] Tính current open risk theo current mark, SL và broker tick value.
- [x] Tính proposed/projected open risk trước khi gửi lệnh.
- [x] Kiểm soát max total open risk.
- [x] Kiểm soát max risk theo symbol.
- [x] Kiểm soát directional exposure theo currency.
- [x] Phát hiện correlated positions theo shared currency leg/direction.
- [x] Kiểm soát số position/pending order đồng thời.
- [x] Hợp nhất daily/weekly loss và consecutive-loss guard.
- [x] Fail-closed khi balance, SL hoặc broker valuation thiếu.
- [x] Chạy lại portfolio guard sau mỗi order thành công.
- [x] Order kế tiếp bắt buộc dùng trạng thái sau order trước.
- [x] Tuần tự hóa request auto/manual để chống race condition.
- [x] Trả snapshot, evaluation, limits và block codes có cấu trúc.
- [x] 20 test Giai đoạn 4 mới/mở rộng đã đạt.
- [x] Regression tập trung Scanner/pipeline/backtest liên quan:
  **255 passed, 7 skipped**.
- [ ] Chưa xác nhận end-to-end bằng tài khoản MT5 demo có nhiều position và
  pending order thật; chuyển sang production gate ở Giai đoạn 8.

### Mục tiêu

Bảo vệ tài khoản khi scanner mở nhiều mã.

### Công việc

- Đọc position và pending order thật từ MT5.
- Tính current open risk theo SL.
- Chạy lại guard sau mỗi order thành công.
- Kiểm soát:

  - Tổng open risk.
  - Rủi ro theo symbol.
  - Exposure theo currency.
  - Vị thế tương quan.
  - Số lệnh mở đồng thời.
  - Daily/weekly loss.
  - Consecutive losses.

Ví dụ:

```text
BUY EUR/USD + BUY GBP/USD
-> cùng short USD
-> không được xem là hai rủi ro độc lập
```

Kết quả nên trả:

```python
{
    "allowed": False,
    "current_open_risk_pct": 2.4,
    "proposed_risk_pct": 1.0,
    "projected_open_risk_pct": 3.4,
    "max_open_risk_pct": 3.0,
    "block_codes": ["PORTFOLIO_RISK_EXCEEDED"]
}
```

### Tiêu chí hoàn thành

- Không thể vượt max open risk qua nhiều order liên tiếp.
- Order thứ hai sử dụng trạng thái tài khoản sau order thứ nhất.
- Có test exposure theo currency và correlated positions.

## Giai đoạn 5 - Backtest config có vòng đời và validation

### Trạng thái triển khai

Giai đoạn 5 đã hoàn tất phần code ngày **24/07/2026**:

- `core/backtest_config_validation.py` là nguồn chuẩn cho schema
  `backtest config schema v4` và validation contract
  `phase8-smc-v2-oos-v1`.
- Optimizer chỉ nhìn thấy 70% lệnh đầu theo thời gian để chọn
  `regime/side/min_score/min_rr`. 30% lệnh sau được giữ riêng làm OOS; config
  đã chọn được áp nguyên trạng lên OOS và không được tối ưu lại.
- Mốc `trained_to` bắt buộc nhỏ hơn `validated_from`. Timestamp thiếu, khoảng
  IS/OOS chồng lấn hoặc sample không đủ đều không thể tạo config
  `VALIDATED`.
- Ngưỡng tối thiểu hiện tại là 10 lệnh IS, 8 lệnh OOS và ít nhất 2 cửa sổ
  walk-forward hợp lệ.
- OOS phải đạt expectancy tối thiểu `+0.10R`, profit factor tối thiểu `1.20`
  và max drawdown không vượt `8R`.
- Bootstrap 1.000 lần tạo confidence interval 95% cho expectancy. Cận dưới
  phải lớn hơn 0.
- Walk-forward phải có ít nhất 2 cửa sổ có ranh giới IS/OOS hợp lệ, verdict
  `ROBUST`, aggregate OOS đủ sample và đạt cùng ngưỡng expectancy/PF.
- Trade thiếu `expected_effective_rr` bị loại khỏi mọi bộ lọc RR trong cả
  optimizer lẫn validator; không còn được mặc nhiên pass.
- `BacktestResult` ghi rõ `score_metric`, `scorer_version` và
  `feature_version`. Snapshot cũ thiếu scoring contract chỉ tạo được DRAFT.
- Mỗi config VALIDATED có fingerprint SHA-256 trên toàn bộ strategy fields,
  version và bằng chứng validation. Sửa threshold/evidence sau validation làm
  fingerprint sai và Strategy Router fail-closed.
- Config VALIDATED hết hạn sau 90 ngày. Router kiểm tra schema, validation
  version, scorer version, feature version, metric, thời gian, sample, OOS,
  CI, walk-forward, fingerprint và expiry trước khi cho vào nhánh
  `BACKTEST_VALIDATED`.
- `apply_validated_backtest_config()` không còn tự đóng dấu VALIDATED cho một
  recommendation thường. Payload thiếu bằng chứng validator được lưu dưới
  trạng thái DRAFT.
- Settings lưu đầy đủ metadata IS/OOS/walk-forward. Settings legacy có
  `backtest=true`, hoặc config cũ tự nhận là VALIDATED nhưng thiếu bằng chứng
  v3, được migrate an toàn về DRAFT và không được auto-trade.
- Lưu thủ công trong Settings chỉ giữ validation khi toàn bộ strategy fields
  không đổi; thay đổi regime/side/min score/min RR làm mất validation.
- Màn hình Backtest dùng validator thay vì recommendation toàn mẫu, hiển thị
  trạng thái VALIDATED/DRAFT, số lệnh OOS, số cửa sổ walk-forward và reason
  codes. DRAFT vẫn lưu được để nghiên cứu nhưng UI nói rõ không được
  auto-trade.

Checklist triển khai:

- [x] Có schema version, validation version và feature version.
- [x] Chọn config chỉ trên IS và xác nhận trên OOS muộn hơn.
- [x] Không dùng cùng một tập lệnh để vừa chọn vừa chứng minh config.
- [x] Có sample gate cho IS, OOS và walk-forward.
- [x] Có bootstrap confidence interval cho OOS expectancy.
- [x] Trade thiếu RR không pass RR filter.
- [x] Bắt buộc walk-forward nhiều cửa sổ và verdict ROBUST.
- [x] Config hết hạn hoặc sai scorer/feature/schema/version fail-closed.
- [x] Fingerprint phát hiện strategy/evidence bị sửa sau validation.
- [x] Config legacy được migrate về DRAFT, không tự nâng thành VALIDATED.
- [x] Backtest và live cùng contract `setup_score/scanner-v2/scanner-features-v2`.
- [x] UI lưu và hiển thị validation health/reason codes.
- [x] 7 test validation mới đã đạt.
- [x] Regression tập trung backtest/router/domain/safety/walk-forward:
  **126 passed**; smoke test hai nhánh đã đạt.
- [ ] Full regression vẫn bị chặn khi collection bởi các script-test legacy
  đã ghi ở phần theo dõi chung; lần chạy mở rộng sau khi loại blocker vượt
  timeout 120 giây nên chưa được dùng làm production sign-off.
- [ ] Chưa xác nhận end-to-end với dữ liệu MT5 demo dài hạn; chuyển sang
  production gate ở Giai đoạn 8.

### Schema đề xuất

```json
{
  "schema_version": 4,
  "validation_version": "phase8-smc-v2-oos-v1",
  "config_id": "EURUSD-trend-buy-v3",
  "status": "VALIDATED",
  "symbol": "EUR/USD",
  "allowed_regimes": ["trend_up"],
  "side": "buy",
  "score_metric": "setup_score",
  "min_score": 68,
  "min_rr": 1.5,
  "scorer_version": "scanner-v2",
  "feature_version": "scanner-features-v2",
  "trained_from": "2024-01-01",
  "trained_to": "2025-06-30",
  "validated_from": "2025-07-01",
  "validated_to": "2025-12-31",
  "in_sample_trades": 120,
  "out_of_sample_trades": 46,
  "oos_expectancy_r": 0.24,
  "oos_profit_factor": 1.42,
  "oos_max_drawdown_r": 5.8,
  "expectancy_ci_low": 0.05,
  "expectancy_ci_high": 0.43,
  "walk_forward_windows": 3,
  "walk_forward_verdict": "ROBUST",
  "validation_fingerprint": "...",
  "validated_at": "...",
  "expires_at": "..."
}
```

### Trạng thái

```text
DRAFT
VALIDATED
EXPIRED
INVALID
DISABLED
```

### Validation

- Chọn cấu hình trên in-sample.
- Xác nhận trên out-of-sample.
- Chạy walk-forward nhiều cửa sổ.
- Yêu cầu sample tối thiểu.
- Bootstrap confidence interval cho expectancy.
- Không cho trade thiếu RR pass filter RR.
- Không dùng cùng tập dữ liệu để vừa chọn vừa chứng minh cấu hình.
- Config hết hiệu lực khi scorer version thay đổi.

### Migration

- Settings cũ có `backtest=true` được chuyển thành `DRAFT`, không tự động thành `VALIDATED`.
- Người dùng phải chạy validation hoặc chủ động xác nhận chuyển đổi.
- Auto-trade không dùng config `DRAFT`.

### Tiêu chí hoàn thành

- Backtest và live dùng cùng score metric, scorer version và feature definition.
- Mọi config auto-trade đều có kết quả OOS.
- Config cũ không gây lỗi khi tải settings.

## Giai đoạn 6 - Ranking và UI dùng một nguồn chuẩn

### Trạng thái triển khai

Giai đoạn 6 đã hoàn tất phần code ngày **24/07/2026**:

- Thêm immutable domain model `ScannerRankingEvaluation` và contract
  `phase6-ranking-v1`.
- Ranking canonical chỉ chạy sau khi Strategy Router và Execution Readiness
  đã gắn `candidate_status`; không còn xếp hạng trước rồi giữ breakdown cũ.
- Mỗi lần ranking tính lại toàn bộ status priority, opportunity rank,
  evidence confidence, strategy confidence, execution readiness, effective
  RR, expected value và breakdown.
- Thứ tự chuẩn:

  1. `candidate_status`
  2. `opportunity_rank`
  3. `strategy_confidence`
  4. `execution_readiness`
  5. `expected_effective_rr`
  6. `symbol`

- Status priority đúng theo contract:
  `READY_NOW`, `WAITING_CONFIRMATION`, `WATCH_ZONE`, `OUT_OF_STRATEGY`,
  `BLOCKED`, `DATA_UNAVAILABLE`.
- `opportunity_rank` được chuẩn hóa 0-100 từ setup score, effective RR, vị trí
  so với entry zone, evidence confidence, execution readiness và penalty
  spread/news. Trường `opportunity_score` chỉ còn là compatibility alias cùng
  giá trị 0-100 ở output cuối.
- Evidence confidence được tính riêng với setup score. Config backtest
  VALIDATED dùng OOS sample, OOS expectancy, profit factor và CI lower bound;
  nhánh default chỉ dùng journal evidence khi có tối thiểu 8 mẫu.
- `BLOCKED`, `OUT_OF_STRATEGY` và `DATA_UNAVAILABLE` có execution readiness
  bằng 0. Breakdown ghi rõ `readiness_bonus_applied=false`, nên không còn
  trường hợp hàng bị chặn nhưng breakdown mô tả READY.
- Backend gán `rank` một lần. Màn hình Scanner đã bỏ toàn bộ logic tự sắp xếp
  theo “có plan/SMC” và không tự đánh lại số thứ tự.
- Bảng Scanner hiển thị riêng status, hướng, setup score, opportunity rank,
  evidence confidence, execution readiness, effective RR, strategy branch và
  config health.
- Nút `Giải thích` giữ dialog mô tả chung khi chưa chọn dòng. Khi đã chọn một
  candidate, nút mở dialog ba cột theo style `EconTable`. Phần mặc định chỉ
  hiển thị 11 thông tin hữu ích cho quyết định theo thứ tự: kết luận, hướng,
  việc nên làm, lý do, chất lượng thiết lập, tỷ lệ lời/lỗ, mức sẵn sàng, bối
  cảnh thị trường, độ tin cậy dữ liệu lịch sử, điểm ưu tiên và nguồn quy tắc.
- Nội dung chính dùng thuật ngữ tiếng Việt, giải thích rõ điểm không phải xác
  suất thắng và so sánh trực tiếp với ngưỡng. Mã lý do được đổi thành câu dễ
  hiểu nếu có bản dịch.
- Broker symbol, rank, ranking breakdown, selected-zone ID/quality/relevance,
  scoring version và reason code nội bộ nằm trong phần kỹ thuật ẩn mặc định;
  dialog không tự tính lại decision hoặc score.
- Màn hình chi tiết đọc `candidate_status` canonical, đồng thời vẫn tương
  thích snapshot cũ có `scanner_group`.
- Màn hình chi tiết dùng toàn bộ canonical selected-side contract cho hero,
  setup/ngưỡng, entry, M15, SL/TP và effective R:R. `best_score`,
  `direction_bias`, R:R danh nghĩa và `trade_permission` legacy không còn được
  dùng để tạo kết luận hành động.
- Checklist Tổng quan không còn fail-open khi thiếu Gate. Trạng thái thiếu dữ
  liệu là `unknown`, scenario fallback được chọn theo `selected_side`, và
  rollout `SHADOW` được ghi rõ là không gửi lệnh thật.
- Chẩn đoán Gate không dùng `pipeline_diagnostics` của legacy best-side khi đã
  có canonical decision. Nếu selected-side chưa có Gate result, UI hiển thị
  "chưa kiểm tra"; các Gate vùng giá/CHOCH mới cũng được hiển thị.
- Vị trí giá và R:R danh nghĩa/dải R:R được lấy theo selected-side scenario,
  tránh ghép setup score của một hướng với vùng giá hoặc R:R của hướng kia.
- Khối vĩ mô hiển thị `macro_raw/30`, confidence và macro status của
  selected-side; không còn gắn nhãn `/30` cho `macro_alignment` đã co giãn.
- Payload lệnh dùng cho preview và Telegram được chụp ngay từ
  `ScannerCandidateDecision`, sau đó chỉ bổ sung rank metadata. UI/Telegram
  không reload Settings và không tự chạy lại branch selection.
- Market Brief lọc top setup nhưng giữ nguyên thứ tự backend; không gom lại
  theo logic riêng làm thay đổi ranking.
- Telegram hiển thị rank, setup score, opportunity rank, evidence confidence,
  execution readiness, branch và config health từ cùng payload.
- Scanner summary có count riêng cho `OUT_OF_STRATEGY` và
  `DATA_UNAVAILABLE`, đồng thời bổ sung `top/average_opportunity_rank`.

Checklist triển khai:

- [x] Có một ranking domain model và contract version duy nhất.
- [x] Filters/Strategy Router/Execution Readiness chạy trước ranking.
- [x] Ranking breakdown được tính lại hoàn toàn sau filters.
- [x] Opportunity rank được chuẩn hóa 0-100.
- [x] Blocked không nhận readiness bonus.
- [x] Backend là nơi duy nhất sắp xếp và gán rank.
- [x] UI không còn sort theo plan/SMC.
- [x] UI hiển thị riêng các chiều setup/evidence/execution/RR/status/branch/config.
- [x] Preview lệnh và Telegram dùng candidate payload đã chụp từ backend.
- [x] Market Brief và Telegram bảo toàn thứ tự candidate backend.
- [x] Có compatibility alias cho snapshot/consumer cũ.
- [x] 12 test Giai đoạn 6 mới đã đạt.
- [x] Regression Scanner/pipeline/execution/portfolio liên quan:
  **165 passed**.
- [ ] Chưa chạy UI interaction test thật trên màn hình desktop và Telegram
  sandbox; chuyển sang production gate ở Giai đoạn 8.

### Mục tiêu

Backend, UI, Telegram và Market Brief cùng nhìn một thứ tự.

### Thứ tự đề xuất

```text
1. Status priority
2. Expected value hoặc opportunity rank
3. Strategy confidence
4. Execution readiness
5. Effective RR
6. Symbol
```

Status priority:

```text
READY_NOW
WAITING_CONFIRMATION
WATCH_ZONE
OUT_OF_STRATEGY
BLOCKED
DATA_UNAVAILABLE
```

### Quy tắc

- UI không tự sắp xếp lại theo “có plan/SMC”.
- Filter chạy trước ranking.
- Sau filter phải tính lại toàn bộ ranking breakdown.
- Blocked không bao giờ có readiness bonus.
- Opportunity score chuẩn hóa 0-100 hoặc đổi tên rõ ràng thành `opportunity_rank`.

UI cần hiển thị riêng:

| Trường | Ý nghĩa |
|---|---|
| Setup score | Chất lượng setup |
| Evidence confidence | Độ tin cậy từ lịch sử |
| Execution readiness | Mức sẵn sàng vào lệnh |
| Effective RR | RR sau spread |
| Status | READY/WAIT/WATCH/... |
| Branch | Backtest validated/default |
| Config health | Valid/expired/invalid |

### Tiêu chí hoàn thành

- Thứ tự UI giống chính xác backend.
- Telegram và Market Brief dùng cùng candidate list.
- Không còn trường hợp blocked nhưng điểm/breakdown vẫn mô tả READY.

## Giai đoạn 7 - Observability và khả năng tái hiện

### Trạng thái triển khai

Giai đoạn 7 đã hoàn tất phần code ngày **24/07/2026**:

- Thêm contract `phase7-observability-v1` và `ScannerScanContext`. Mỗi lần
  quét có `scan_id` duy nhất, thời điểm bắt đầu, version của scanner/scorer/
  feature/router/ranking/revalidation/portfolio, `settings_hash`,
  `request_hash` và feature flags.
- Hash được tạo từ JSON canonical đã che các trường nhạy cảm. API key, token,
  password, secret và credential không được ghi vào hash input, snapshot hay
  structured log.
- Mỗi row có `row_id` ổn định trong scan và một trace `observability` chứa:
  input timestamps theo timeframe, data freshness, config ID, branch/side,
  score inputs, weighted components, strategy/execution/trade gates,
  portfolio state và quyết định candidate cuối.
- Candidate order payload mang xuyên suốt `scan_id`, `row_id`,
  `settings_hash`, `backtest_config_id`, `scorer_version` và
  `ranking_version`. Kết quả revalidation và order response giữ lại cùng
  provenance, nên có thể xác định đúng scorer/config tạo ra một yêu cầu lệnh.
- Scanner tự lưu snapshot sau mỗi scan. Summary nhẹ nằm tại
  `scanner_snapshots/scanner_{scan_id}.json`; full analysis từng mã nằm tại
  `scanner_analysis/{scan_id}/{symbol}.json`. Summary có `analysis_manifest`
  và từng row có `analysis_ref`, không còn mất `analysis_result`.
- Full analysis document lưu row summary, analysis result, config đã dùng,
  candidate decision, ranking contract, scan context và observability trace.
- `replay_candidate_decision()` dựng lại row tại đúng `started_at`, chạy lại
  Candidate Engine và Ranking Engine, rồi so sánh status, branch, side,
  reason codes và opportunity rank với snapshot. Sai khác trả
  `REPLAY_DECISION_MISMATCH`.
- Structured events được append dạng JSONL vào
  `logs/scanner-events.jsonl` trong app data. Observability là fail-safe:
  lỗi ghi log không được thay đổi quyết định giao dịch hoặc làm hỏng scan.
- Các lỗi từ connection, balance, macro correlation/news preload, tải giá,
  analysis pipeline, execution snapshot và gửi lệnh đều được ghi lại cùng
  stage/reason. Exception nghiệp vụ vẫn giữ hành vi fail-closed hiện có.
- Ở thời điểm đóng Giai đoạn 7, so sánh V1/V2 mới ghi
  `DECISION_DISAGREEMENT` giữa scanner group legacy và candidate status
  canonical. Phần shadow comparison đầy đủ, disagreement metrics và rollout
  sau đó đã được triển khai tại Giai đoạn 8; việc thu bằng chứng vận hành thực
  tế vẫn là production gate.

Các structured event hiện có:

```text
SCAN_STARTED
DATA_FETCH_FAILURE
STRATEGY_REJECTION
GATE_REJECTION
DECISION_DISAGREEMENT
ORDER_REQUEST
EXECUTION_REVALIDATION_FAILURE
ORDER_SEND_REQUEST
ORDER_RESPONSE
SNAPSHOT_WRITE_FAILURE
SCAN_COMPLETED
```

Checklist triển khai:

- [x] Có scan context/version/hash không làm lộ secret.
- [x] Có provenance từ scan row tới order request/response.
- [x] Lưu input timestamps, freshness, score, gates và portfolio state.
- [x] Snapshot summary không chứa analysis nặng nhưng có reference đầy đủ.
- [x] Full `analysis_result` được lưu riêng theo scan/symbol.
- [x] Có deterministic decision replay và phát hiện snapshot bị thay đổi.
- [x] Có structured JSONL events cho data/strategy/gate/order/disagreement.
- [x] Structured logging fail-safe, không can thiệp trading decision.
- [x] 10 test Giai đoạn 7 mới đã đạt, gồm replay cho cả
  `DEFAULT_RULES` và `BACKTEST_VALIDATED`.
- [x] Regression Scanner/pipeline/backtest/execution/portfolio liên quan:
  **169 passed**.
- [ ] Chưa xác nhận replay bằng snapshot từ MT5 demo thật, UI interaction và
  shadow V1/V2 dài hạn; đây là production gate của Giai đoạn 8.

Mỗi scan cần lưu:

```text
scan_id
scanner_version
scorer_version
settings_hash
backtest_config_id
input timestamps
data freshness
selected branch
selected side
score inputs
weighted components
gate results
portfolio state
final candidate decision
```

Snapshot không được loại bỏ toàn bộ `analysis_result`. Nếu dung lượng lớn, tách:

```text
scanner_summary.json
scanner_analysis/{scan_id}/{symbol}.json
```

Thêm structured logging cho:

- Data fetch failure.
- Strategy rejection.
- Gate rejection.
- Order revalidation failure.
- Order request/response.
- V1/V2 decision disagreement.

### Tiêu chí hoàn thành

- Có thể tái hiện lý do một symbol được READY tại một thời điểm.
- Có thể xác định scorer/config nào tạo ra order.
- Có thể so sánh kết quả V1 và V2.

## Giai đoạn 8 - Test, shadow mode và rollout

### Trạng thái triển khai

Tooling và phần code của Giai đoạn 8 đã hoàn tất ngày **24/07/2026**:

- Thêm contract `phase8-rollout-v1` với sáu stage:
  `DISABLED`, `SHADOW`, `DEMO_LIMITED`, `DEMO_FULL`, `CANARY`,
  `PRODUCTION`.
- Settings mới hoặc settings cũ sau migration đều mặc định ở `SHADOW`.
  Trong stage này Scanner V2 vẫn phân tích/xếp hạng nhưng mọi order bị chặn
  trước khi đọc execution snapshot hoặc gọi MT5.
- `kill_switch` luôn thắng mọi stage và phê duyệt. Rollback analysis có thể
  chọn `legacy` để dùng SMC v1, nhưng không bao giờ khôi phục đường auto-trade
  V1 thiếu safety gate.
- `DEMO_LIMITED` bắt buộc server có dấu hiệu demo và chỉ cho phép symbol trong
  allowlist. `DEMO_FULL` bắt buộc demo nhưng cho phép toàn bộ symbol.
- `CANARY` áp hard cap `canary_risk_percent` trước shared execution path.
  Mặc định vẫn bắt buộc tài khoản demo; chỉ có thể bỏ yêu cầu này bằng cấu
  hình rõ ràng. Canary chỉ mở khi shadow/demo/OOS/rollback gate đã đạt.
- `PRODUCTION` bắt buộc đồng thời `production_approved=true` và release
  readiness đang `ready=true`, bao gồm đủ sample canary. Thiếu metrics hoặc
  đọc metrics lỗi đều fail-closed bằng `RELEASE_GATE_NOT_READY`.
- Màn hình Settings có tab **Rollout** để chọn stage, bật kill switch,
  shadow comparison, allowlist, canary risk, demo requirement, production
  approval, SMC mode `legacy | shadow | v2` và các ngưỡng release gate.
- Scoring provenance `phase8-scoring-provenance-v1` được lưu đồng nhất trên
  analysis, scanner row/output, observability/order, journal và backtest.
- Backtest config schema v4 bắt buộc khớp `scanner-v3`,
  `scanner-features-v3`, `smc-v2` và mode `v2`; config cũ không được tự nâng
  `min_score`.
- Rollback drill `phase8-rollback-drill-v1` đã chạy đạt mà không gọi broker:
  kill switch chặn order và analysis có thể quay rõ về `smc-v1`.
- Shadow engine tái hiện đúng hành vi V1 cũ: nhánh không config dùng
  `scanner_action=ready`; nhánh có config dùng regime, `best_score`, RR và
  side override, kể cả fallback scenario phía đối diện của logic cũ. Vì vậy
  báo cáo có thể phát hiện trực tiếp lỗi `V1_SIDE_SCENARIO_MISMATCH` thay vì
  chỉ so sánh hai status đã có.
- Mỗi symbol có bản ghi `SHADOW_DECISION_COMPARISON` gồm V1/V2 status, side,
  trade decision, score gate, reason codes và các loại disagreement:
  trade/wait, side, status, score gate, side/scenario mismatch.
- Metrics được tích lũy tại
  `rollout/scanner-rollout-metrics.json` trong app data: số scan/shadow
  sample/disagreement/side mismatch, demo order, revalidation attempt/failure,
  premature order, portfolio violation, score delta SMC, đổi hướng/zone,
  false-ready, no-zone/data-unavailable, latency/error, hiệu suất theo scorer
  và kết quả thử rollback.
- Metrics contract `phase8-smc-rollout-metrics-v2` không trộn counter cũ;
  evidence cũ được lưu dưới `legacy_metrics`. Release threshold dùng
  `unsafe_disagreement`, còn false-ready được v2 loại bỏ được đếm riêng.
- Release gate kiểm tra tối thiểu shadow sample/demo order, unsafe disagreement rate,
  canary order, side mismatch, premature order, portfolio violation,
  revalidation failure rate, OOS/demo performance degradation và xác nhận đã
  thử rollback.
- OOS/demo degradation được cập nhật qua
  `ScannerRolloutMetricsService.update_release_evidence()`. Không có bằng
  chứng được hiểu là chưa đủ điều kiện production.
- Controller ghi rollout policy, shadow report, pre-scan readiness, metrics
  sau scan và release readiness vào output/snapshot. Policy được kiểm tra lại
  ngay trong `execute_order_candidate()`, nên UI/manual/auto không thể bỏ qua
  rollout guard.
- Runtime ngày 24/07/2026 đã được lưu ở stage `PRODUCTION`, kill switch tắt,
  production approval bật, real account được phép, ba feature flag V2 bật và
  SMC mode là `v2`. Đây là cấu hình đã chọn, không phải bằng chứng release.
- Nút auto-entry trên Scanner hiện bị disable và request từ UI luôn đặt
  `auto_trade_enabled=false`. Lệnh thủ công vẫn bị policy trả
  `RELEASE_GATE_NOT_READY` do `0/20` demo orders, `0/5` canary orders và thiếu
  OOS/demo evidence.

Checklist triển khai:

- [x] V1 và V2 được đánh giá song song bằng hai logic độc lập.
- [x] V2 tuyệt đối không gọi execution trong `SHADOW`.
- [x] Có structured disagreement theo trade/side/status/score/scenario.
- [x] Có stage guard cho demo limited, demo full, canary và production.
- [x] Có kill switch fail-closed và kiểm tra rollback.
- [x] Canary có hard risk cap trước shared execution.
- [x] Production bắt buộc approval và release evidence đạt chuẩn.
- [x] Metrics/revalidation failure rate được lưu bền vững.
- [x] Settings cũ migrate an toàn về `SHADOW`.
- [x] Có UI cấu hình rollout.
- [x] Test mục tiêu SMC/Scanner Phase 8: **143 passed**.
- [x] Regression SMC/Scanner/Settings/Backtest/Journal liên quan:
  **322 passed**; 7 lỗi fixture Qt cũ nằm ngoài đường Phase 8.
- [x] Đã đạt tối thiểu 100 shadow samples (`364/100` tại snapshot
  24/07/2026 22:31, Asia/Ho_Chi_Minh).
- [ ] Chưa đạt 20 demo orders (`0/20`) và 5 canary orders (`0/5`).
- [ ] Chưa ghi OOS evidence và demo evidence.
- [ ] Chưa chạy soak test MT5 demo, Telegram sandbox, UI interaction dài hạn
  và canary bằng tài khoản được phê duyệt.
- [x] Full test collection hiện không lỗi.

Kết luận trạng thái: **đã hoàn tất code/tooling nhưng chưa được phép gắn nhãn
production-ready**. Runtime đã chọn `PRODUCTION`, tuy nhiên stage này chưa có
hiệu lực gửi lệnh cho tới khi checklist thực nghiệm phía trên đạt và release
gate trả `ready=true`. Giá trị mặc định cho settings mới vẫn là `SHADOW`.

### Unit tests

Ma trận tối thiểu:

```text
branch x config status x side x score x RR
x entry status x M15 x gate x freshness
```

Invariant bắt buộc:

- Blocked không bao giờ auto-trade.
- Invalid config không bao giờ auto-trade.
- Forced BUY không bao giờ dùng SELL scenario.
- Score và RR phải thuộc selected side.
- Thiếu dữ liệu không được làm tăng độ sẵn sàng.
- RR giảm không được làm candidate tốt hơn.
- Stale tick chặn order.
- Spread mới bất thường chặn order.
- Portfolio risk vượt ngưỡng chặn order.
- UI rank bằng backend rank.

### Integration tests

- Analysis result thật -> scanner row.
- Scanner row -> strategy router.
- Candidate -> Telegram/UI.
- Candidate -> MT5 mocked execution.
- Settings cũ -> schema mới.
- Backtest config -> live evaluation cùng metric.

### Shadow mode

Chạy V1 và V2 song song nhưng:

- Chỉ V1 hiển thị hoặc hiển thị cả hai để so sánh.
- V2 tuyệt đối không đặt lệnh.
- Ghi lại disagreement:

```text
V1=TRADE, V2=WAIT
V1=BUY, V2=SELL
V1 score passed, V2 side score failed
```

### Rollout

1. Shadow mode.
2. Demo account, một vài symbol.
3. Demo account, toàn bộ symbol.
4. Auto-trade canary với risk rất thấp.
5. Mở rộng dần sau khi đạt tiêu chí.

### Tiêu chí phát hành

- Không có side mismatch.
- Không có order khi entry chưa confirmed.
- Không có order vượt portfolio risk.
- Tỷ lệ lỗi order revalidation được theo dõi.
- Kết quả OOS và demo không suy giảm vượt ngưỡng đã định.
- Có cơ chế rollback bằng feature flag.

## Thứ tự triển khai khuyến nghị

| Milestone | Nội dung | Phụ thuộc | Trạng thái |
|---|---|---|---|
| M0 | Safety freeze và đặc tả | Không | **Đã hoàn tất code; chờ full regression/integration** |
| M1 | Domain models và Strategy Router | M0 | **Đã hoàn tất code; 165 test mục tiêu đạt** |
| M2 | Execution Readiness | M1 | **Đã đóng phần code; 235 test regression mục tiêu đạt, 7 skipped** |
| M3 | Portfolio Guard | M2 | **Đã hoàn tất code; 255 test regression mục tiêu đạt, 7 skipped** |
| M4 | Config schema và migration | M1 | **Đã hoàn tất code trong Giai đoạn 5** |
| M5 | Backtest OOS validation | M4 | **Đã hoàn tất code trong Giai đoạn 5; 126 test mục tiêu đạt** |
| M6 | Ranking/UI/Telegram đồng bộ | M1-M5 | **Đã hoàn tất code; 165 test regression mục tiêu đạt** |
| M7 | Observability và snapshots | M1-M6 | **Đã hoàn tất code; 169 test regression mục tiêu đạt** |
| M8 | Shadow/demo/canary rollout | Tất cả | **Đã hoàn tất code/tooling; 192 test regression mục tiêu đạt, chờ shadow/demo/canary thật** |

Các milestone M0-M8 đã hoàn tất phần code. Production validation bằng dữ liệu
shadow/demo/canary thật vẫn là điều kiện vận hành bắt buộc, không thể thay thế
bằng unit test.

## Ước lượng nguồn lực

| Hạng mục | Ngày công |
|---|---:|
| Safety và đặc tả | 1-2 |
| Domain model/strategy router | 3-5 |
| Execution revalidation | 3-5 |
| Portfolio guard | 3-4 |
| Config schema/migration | 2-3 |
| Backtest OOS/walk-forward | 5-8 |
| Ranking/UI/downstream | 3-5 |
| Observability/snapshot | 2-3 |
| Test và rollout tooling | 4-6 |

Tổng: khoảng 25-35 ngày công. Có thể rút ngắn thời gian lịch nếu tách song song phần portfolio và backtest validation, nhưng không nên song song hóa phần domain contract vì tất cả module phía sau phụ thuộc vào nó.
