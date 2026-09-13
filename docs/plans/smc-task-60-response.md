# Task 60 — Implementation response

Trạng thái: **DONE / WAITING_REVIEW tại gate 72**. Đã dừng sau task 60; chưa triển khai task 61.

## Phạm vi

Task 60 bổ sung đánh giá reaction/follow-through cho visit lifecycle trong `core/smc_lifecycle.py`. Visit chỉ được đánh dấu reacted sau khi đã exited; open visit và touch-only không được gắn reaction.

## Mapping contract → code → tests

| Contract | Code | Tests |
|---|---|---|
| BUY reaction cần close ra trên zone ít nhất `0.25*ATR_current`; SELL là mirror phía dưới zone | `_follow_through_reaction_at` dùng ngưỡng `0.25 * atr_current` và bounds gốc `zone_low/zone_high` | `test_buy_reaction_is_allowed_within_three_candles`, `test_sell_reaction_is_symmetric` |
| Follow-through hợp lệ ở candle exit hoặc tối đa 3 candle kế tiếp | Helper quét từ `exit_index` đến `exit_index + 3`; cùng candle ghi `exited_at == reacted_at` | `test_same_exit_candle_can_emit_exit_then_reaction`, `test_follow_through_after_three_candles_does_not_react` |
| Open visit/touch-only không phải reaction | Chỉ gọi helper khi `active_start` kết thúc; visit chưa exit đi qua nhánh open | `test_open_visit_is_not_reacted`, `test_exit_without_follow_through_is_completed_unreacted` |
| Invalidation có ưu tiên trước reaction | Helper dừng và trả no reaction khi gặp `_invalidates`; invalidation trong visit giữ `closed_by_invalidation` | `test_invalidation_before_reaction_has_priority`, `test_invalidation_while_visit_open_closes_visit_without_reaction` |
| Reaction phải lưu canonical evidence | `_visit` truyền `reacted_at`; `ZoneVisit.__post_init__` tự giữ state `completed_reacted` khi có timestamp | Các assertion `visit_state`/`reacted_at` trong toàn bộ file Task 60 |

## Verification

- Task 60 + lifecycle regression: **27 passed**.
- Full SMC/scanner integration command: **776 passed** (`8.11s`). Command:

  `$smcTests = @(rg --files tests -g 'test_smc*.py'); python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q`
- `git diff --check`: **passed**.
- Không sửa, skip hoặc xfail golden fixture/acceptance test; một case regression của Task 59 được điều chỉnh dữ liệu close để vẫn kiểm tra exit tolerance mà không đồng thời thỏa ngưỡng reaction mới của Task 60.

## Gate

Đã hoàn thành phạm vi Task 60 và chuyển trạng thái **WAITING_REVIEW**. Dừng tại gate 72, không làm Task 61.
