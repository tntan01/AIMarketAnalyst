# Tech Lead review — gate 56, lần 3

**Quyết định: CHANGES_REQUESTED. Chưa được làm task 57.**

- Reviewer: Codex, Tech Lead theo yêu cầu người dùng.
- Thời điểm: 2026-09-11, khoảng 04:06 Asia/Saigon.
- Phạm vi: ba finding còn mở sau lần 2, regression chống tái phát và hồ sơ fixture. Không sửa implementation, tests, specs, progress hoặc báo cáo cũ; chỉ thêm báo cáo này.
- Bản trình lại: `docs/plans/smc-task-56-response-round2.md`, trạng thái FIXES_READY. Manifest mới **6/6 file khớp SHA256**. Manifest response cũ là lịch sử, không dùng để xác minh bản hiện tại.

## 1. Kết luận

**6 finding CLOSED, 2 finding còn PARTIAL/OPEN: R56-01 và R56-02.** R56-05 được đóng trong lượt này. Không mở lại các lỗi đã giải quyết chỉ vì acceptance tổng thể chưa đạt.

| Finding | Kết luận lần 3 |
|---|---|
| R56-01 | **PARTIAL / P1:** pending/cold/idempotent đã đúng; guard mới bỏ sót trạng thái canonical `invalid`, có thể xác nhận lại vùng hỏng. Session policy còn điều kiện exact open equality không có trong P5 |
| R56-02 | **PARTIAL / P1:** BOS canonical và quality gate đã sửa; association timestamp-only vẫn đếm thời gian nghỉ phiên thành bar, từ chối BOS thật trong cửa sổ ba nến |
| R56-03 | Giữ CLOSED — S/D close-location |
| R56-04 | Giữ CLOSED — canonical base/dedup S/D |
| R56-05 | **CLOSED** — departure lineage giữ qua typed round-trip/regroup; BUY/SELL, permutation giữ setup ID/count và child IDs |
| R56-06 | Giữ CLOSED — closed history tại cutoff |
| R56-07 | Giữ CLOSED — measurement evidence adapter |
| R56-08 | Giữ CLOSED trong phạm vi detector retention; test M15 đã sửa đúng interval/count/cutoff, không suy ra lifecycle expiry đã hoàn tất |

## 2. R56-01 — Hai phần chưa đúng

### A. Guard terminal không nhận trạng thái `invalid` của model

**Vị trí:** `core/smc_context.py:639`; đối chiếu `VALID_ZONE_LIFECYCLE_STATUSES` trong `core/smc_models.py`.

Guard kiểm tra `{"invalidated", "expired", "broken"}`, trong khi canonical zone dùng **`invalid`**, không phải `invalidated`. Với FVG đã confirmed, đổi trạng thái thành canonical `invalid`, giữ `invalidated_at`, rồi gọi lại confirmation: hàm bỏ reason `ZONE_CONFIRMED` và promote vùng thành confirmed mới.

Probe dùng actual FVG `formation_end_index=17` từ fixture gate56, full H1 history; trạng thái `invalid` đã kiểm tra là được `SmcZone.from_dict` chấp nhận. Giữ detector measurements gốc để cô lập guard, không trộn lỗi adapter:

```python
confirmed = confirm_fvg_candidate(raw, candles, timeframe='H1')
invalid = {
    **confirmed,
    'lifecycle_status': 'invalid',
    'invalidated_at': candle_close_at(candles[18].time, 'H1').isoformat(),
}
result = confirm_fvg_candidate(invalid, candles, timeframe='H1')
```

```text
input lifecycle_status:  invalid
output lifecycle_status: confirmed
output invalidated_at:   2026-09-07T19:00:00+00:00 (vẫn tồn tại)
control status expired:  vẫn expired
```

Không thể dựa vào reason `ZONE_INVALIDATED` luôn có mặt để thay validation trạng thái; typed model không yêu cầu reason này và guard mới chủ động hứa giữ terminal state. Zone spec không cho phép phục hồi vùng hỏng bằng cách gọi confirmation lại. Đây là lỗi guard của phần sửa, không yêu cầu triển khai thuật toán invalidation task 63 trước gate này.

**Đóng khi:** guard theo enum canonical và trạng thái/timestamp terminal hợp lệ; kiểm thử confirmed → invalid → reevaluate không trở lại confirmed, cùng expired và BUY/SELL. Giữ pending/cold parity đã sửa; không xóa invalidated_at hoặc audit history để làm output có vẻ nhất quán.

### B. Session displacement bị buộc open phải bằng close tuyệt đối

**Vị trí:** `core/smc_context.py:539–546`.

P5 yêu cầu phân biệt session-only gap với displacement hợp lệ. Code mới chỉ nhận khi cả `middle.open == first.close` **và** `third.open == middle.close`. Điều kiện thứ hai còn áp vào hai candle trong cùng phiên, không phải tại chỗ nghỉ phiên. Thay open nến thứ ba một tick có thể loại vùng dù gap bounds, middle quality và nguồn displacement hoàn toàn không đổi.

Probe H1 EUR/USD, tick=.1, ATR=5:

| Open time UTC | O/H/L/C |
|---|---|
| 2026-09-11 21:00 | 101 / 102 / 99 / 100 |
| 2026-09-13 21:00 | 100 / 106 / 99.8 / 105.5 |
| 2026-09-13 22:00 | **105.5 hoặc 105.4** / 107 / 103 / 106 |

Cả hai chuỗi đều 0 OHLC validation error; reopen tại middle vẫn đúng close trước, middle body/range khoảng .887, directional close-location khoảng .919, FVG [102,103] đạt minimum. Hai candle cuối liên tục trong phiên:

```text
third.open=105.5 -> 1 candidate
third.open=105.4 -> 0 candidate
```

Đây là thêm một hard gate exact equality chưa được duyệt, không phải chứng minh gap chỉ do session jump. Negative test đang đặt tên session-only cũng không cô lập nguyên nhân này với middle displacement.

**Đóng khi:** phân loại phần gap do boundary và phần displacement dựa trên candle/session evidence; không reject chỉ vì open/close lệch một tick ở cặp không qua closure. Thêm BUY/SELL positive với small open mismatch, negative gap thực sự chỉ do session boundary và unknown/unexpected gap. Nếu muốn thay chính sách P5, trình đề xuất riêng thay vì khóa điều kiện mới bằng fixture khớp số tuyệt đối.

## 3. R56-02 — BOS qua phiên bị đếm sai association window

**Vị trí:** `core/smc_context.py:3350–3357`.

Event canonical có timestamp nhưng không có `occurred_index`. Nhánh này tính:

```text
bars_after = (occurred_at - departure_close) / timeframe_interval
```

Dù caller đã truyền `candles`, hàm không resolve timestamp về candle tương ứng mà đếm cả thời gian thị trường nghỉ. Một BOS ở candle kế tiếp sau weekend bị coi cách departure hàng chục bar. Nhánh có index của cùng event lại nhận đúng.

### Probe từ evaluator thật, không tự tạo BOS

Dùng BUY rows của fixture gate40, lấy prefix tới index 25, sửa hai candle như probe lần 2:

```text
index 23: (105.5,106,104,105)  # base
index 24: (105,108,104.5,107)  # departure
index 25: (105,115,105,113)   # genuine continuation BOS
```

Đặt H1 candle index 0 tại `2026-09-10 20:00 UTC`, do đó index 24 là thứ Sáu `2026-09-11 20:00 UTC`. So hai chuỗi cùng OHLC:

- Control: index 25 tại thứ Sáu 21:00, liên tục.
- Weekend: index 25 tại Chủ nhật `2026-09-13 21:00 UTC`, candle kế tiếp trong lịch sử có closure hợp lệ; calendar helper phân loại `session_gap`.

Chạy `replay_smc_structure(..., timeframe='H1', tick_size=.01, as_of=close(index 25))`, default external width 5; lấy BOS thật đúng cutoff. Không thêm cờ confirmed:

| Input | Actual OB |
|---|---|
| Control liên tục + canonical BOS | confirmed |
| Weekend + canonical BOS | **candidate** |
| Weekend + cùng BOS, chỉ thêm `occurred_index=25` làm control | confirmed |

Sau weekend chỉ có **một candle** từ departure đến break, nhưng nhánh timestamp-only tính khoảng **49 giờ/bar H1** và reject. Cửa sổ tối đa ba bar phải dựa trên candles/session coverage, không dựa vào thời gian nghỉ. Yêu cầu này đã nằm trong R56-02 lần 1/2, không phải thay threshold mới.

**Đóng khi:** resolve event/departure timestamp về closed candle lineage khi có candles, validate mismatch và đếm actual bars. Không có đủ context/session metadata thì trả unavailable có reason, không tự coi downtime thành candles. Test genuine canonical BOS BUY/SELL: continuous và valid closure cho cùng association; negative vượt ba actual bars vẫn bị loại; không thêm index thủ công vào input chuẩn để che lỗi consumer.

## 4. Phần đã xác minh đúng trong lượt này

- **FVG pending/cold/idempotent:** actual detector BUY/SELL, early cutoff → late cutoff có toàn bộ dict bằng cold confirmation; gọi lại confirmed trả cùng dict. Không còn blocker stale `FVG_THIRD_CANDLE_NOT_CLOSED`.
- **Canonical BOS / P3:** replay genuine gate40-derived BUY và SELL mirror, không có boolean confirmed, đều promote đúng trên dữ liệu liên tục; đọc guard body/range .50, body/ATR .30, directional close-location .70 và finite checks. Regression weak departure bị loại.
- **R56-05:** raw OB/FVG/S-D → SmcZone → dict → SmcZone → dict, đảo thứ tự, group lại: cả BUY/SELL đều một setup, cùng setup ID, cùng child IDs. Hai field departure source được bảo toàn. R56-05 CLOSED.
- **M15:** regression mới có step 15 phút, 104 candles, độ dài 102/103/104 và cutoff cuối prefix, tương ứng age79/80/81 từ confirmation index22. Không còn hai slice giống nhau hoặc cutoff cố định.
- Không yêu cầu Coder sửa lại các finding CLOSED nếu không có regression mới. Chưa duyệt lifecycle/expiry hoặc rollout production.

## 5. Hồ sơ integration vẫn chưa nối thành cùng một timeline thật

Fixture H1 đã thêm đủ 70 rows cho history, nhưng `structure_provenance` trỏ sang **event H4 tháng 01 từ fixture khác**. Đây là provenance cho test canonical schema riêng, không phải nguồn BOS của H1 pattern tháng 09.

Trong `tests/test_smc_gate56_review_regressions.py:248`, integration confirmation → availability → typed regroup vẫn gọi `_event(candles,17)` tự tạo ID/BOS. Chạy chính 70 H1 rows bằng `replay_smc_structure(..., symbol='EUR/USD', timeframe='H1', tick_size=.1)` cho **0 event**.

Test canonical riêng là tiến bộ đúng và đã giúp đóng lỗi schema, nhưng không thay thế fixture tích hợp từ cùng symbol/timeframe/cutoff/price history. Cần một timeline có BOS thật của chính chuỗi nến tạo OB, đồng thời kiểm các family, availability và typed grouping theo yêu cầu gate56. Đừng chỉ thêm metadata trỏ sang event không liên quan hoặc dùng event ấy để xác nhận H1 zone.

Response/progress vẫn chờ review, không tự APPROVED; manifest mới khớp. Báo cáo review cũ không bị sửa.

## 6. Verification reviewer đã chạy

```powershell
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
# 629 passed in 7.73s

$gateTests = @(rg --files tests -g '*task4[1-9].py' -g '*task5[0-5].py')
python -m pytest @gateTests tests/test_smc_gate56_review_regressions.py -q
# 56 passed in 1.25s

python -m py_compile core/smc_context.py core/smc_models.py tests/test_smc_gate56_review_regressions.py
git diff --check
# Exit 0; chỉ warning LF/CRLF từ Git.
```

Đã chạy thêm các probe read-only mô tả ở trên. Không sửa tests để assert hành vi sai; không tuyên bố chạy toàn bộ repository, UI/live trading hay production acceptance.

## 7. Yêu cầu trình lại

1. Sửa ba nhánh còn lỗi: FVG canonical terminal guard, session displacement policy, OB association qua closure. Mapping giữ R56-01/R56-02; không mở task57.
2. Regression mỗi nhánh cùng BUY/SELL và negative đối chứng; giữ các test đã pass, typed identity và prefix parity.
3. Bổ sung fixture/timeline tích hợp cùng nguồn thật; dùng event nguyên bản từ evaluator thay `_event()` trong acceptance positive. Mock vẫn có thể dùng ở unit negative để cô lập guard.
4. Response mới ghi actual commands/counts, hash manifest; đồng bộ progress FIXES_READY chờ review. Giữ nguyên báo cáo các vòng trước; không tự APPROVED hoặc rollout.

## 8. SHA256 của bản review

| File | SHA256 |
|---|---|
| `core/smc_context.py` | `1659008D1C0EA563E8787221AAFAACC31DB6659B28FE75E0F4CD967F88FAF9D5` |
| `core/smc_models.py` | `C8FBBD90AA10E7F99B61DE8DAEBB30B5019B9D3A9E98987EE27144C2D29045E5` |
| `tests/test_smc_gate56_review_regressions.py` | `D746835C34071B04C568D1161DC0ACD6512781E9706059A160FE4109ADBCB1BC` |
| `tests/test_smc_fvg_session_task47.py` | `6323EC5ECABBAF8F97756EE9CD1D48E62E0A1C492AEE2912D6DEFA1DD95E380B` |
| `tests/fixtures/smc_gate56_zone_pipeline.json` | `AA4B400C2F7DFD01442D816DB13B70171136D30C09B9CEAB9790082A415720D3` |
| `docs/plans/smc-task-56-response-round2.md` | `3E580EDD6E3510DFCB185862956E6C64B373EC77742052EB131B5B4A4982FD6C` |
| Review lần 1 | `A718DB310BECC4FFEC058A498621B2A86EDFE722EB3B5E51BE67CC8FB9184059` |
| Review lần 2 | `CF4F6BFC1F5ECC2E2CAA3BF39AA635FB23C56278188AD660E4FF76B5C45CE644` |
