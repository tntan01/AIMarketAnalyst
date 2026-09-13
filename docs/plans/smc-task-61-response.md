# Task 61 — Implementation response

Trạng thái: **DONE / WAITING_REVIEW tại gate 72**. Đã dừng sau task 61; chưa triển khai task 62.

## Phạm vi

Task 61 khóa penetration và dwell theo candle đóng trong canonical lifecycle. Penetration của từng candle vẫn được clamp trong `[0, 1]`; dwell của một visit là chuỗi overlap liên tiếp, tách khỏi tổng số candle overlap của toàn zone.

## Mapping contract → code → tests

| Contract | Code | Tests |
|---|---|---|
| Penetration nằm trong `[0,1]`, BUY/SELL đối xứng | `_penetration_ratio` giữ công thức theo wick và clamp; kết quả lớn nhất của visit tiếp tục lưu ở `max_penetration_ratio` | `test_visit_stores_continuous_dwell_and_total_is_separate`, regression lifecycle BUY/SELL |
| Dwell là số candle đóng overlap liên tiếp của từng visit | `active_bars_spent_inside` tăng đúng một lần cho mỗi candle overlap và được lưu vào `ZoneVisit.bars_spent_inside` | `test_visit_stores_continuous_dwell_and_total_is_separate`, `test_open_visit_dwell_counts_closed_overlapping_candles_only` |
| Tổng dwell/overlap của zone khác dwell visit hiện tại | `ZoneLifecycle.bars_spent_inside` giữ tổng; `dwell_bars` và `current_dwell_bars` đọc visit cuối cùng/current | `test_reentry_resets_current_dwell_but_keeps_total_overlap_count` |
| Re-entry bắt đầu dwell mới | Khi visit đóng, bộ đếm active được reset; visit kế tiếp có bộ đếm riêng, không gộp với visit trước | `test_reentry_resets_current_dwell_but_keeps_total_overlap_count` |
| Không phụ thuộc số lần scanner/polling | Lifecycle chỉ đếm candle trong history sau availability/departure, không có increment theo polling | `test_scan_frequency_does_not_change_dwell_result` |
| Dwell count phải là số nguyên không âm | `ZoneVisit.__post_init__` validate `bars_spent_inside`; serialization round-trip giữ field | `test_visit_dwell_count_is_non_negative_integer`, domain/lifecycle regression |

## Verification

- Task 61 + Task 57–60/lifecycle/domain regression: **54 passed**.
- Full SMC/scanner integration command: **784 passed** (`8.19s`).
- `py_compile` cho lifecycle/model/test và `git diff --check`: **passed**.

## Gate

Đã hoàn thành phạm vi Task 61 và chuyển trạng thái **WAITING_REVIEW**. Dừng tại gate 72, không làm Task 62.
