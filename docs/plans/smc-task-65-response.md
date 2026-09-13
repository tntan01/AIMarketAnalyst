# Task 65 — Implementation response

Trạng thái: **DONE / WAITING_REVIEW tại gate 72**. Đã dừng sau task 65; chưa triển khai task 66.

## Phạm vi

Task 65 bổ sung acceptance matrix cho lifecycle tasks 57–64. Các test khóa hành vi causal theo candle đóng, không phụ thuộc số lần scanner/polling và không thay đổi golden fixture.

## Mapping contract → tests

| Contract | Test coverage |
|---|---|
| Departure không tính retest, overlap đầu tiên sau departure mở visit | `test_departure_is_excluded_and_first_overlap_is_an_open_visit` |
| Dwell dài đếm từng candle overlap một lần, tách tổng zone và dwell visit | `test_long_dwell_counts_each_closed_overlap_candle_once` |
| Boundary jitter trong exit tolerance không tạo visit giả; outside hợp lệ mới cho re-entry | `test_boundary_jitter_inside_tolerance_does_not_create_extra_visit` |
| FVG partial/full fill giữ original bounds và identity riêng | `test_fvg_partial_and_full_fill_remain_separate_from_zone_identity` |
| Invalidation chỉ theo close vượt buffered boundary | `test_invalidation_uses_close_buffer_and_preserves_penetration_visit` |
| Zone expiry theo lifetime, age score và giữ prior visit history | `test_age_expiry_is_terminal_but_keeps_prior_visit_history` |
| Dwell/age/retest không phụ thuộc tần suất polling và state round-trip ổn định | `test_visit_and_lifecycle_round_trip_are_deterministic` |

Không chỉnh sửa, skip hoặc xfail golden fixture/acceptance artifacts.

## Verification

- Task 65 + Task 57–64/lifecycle regression: **71 passed**.
- Full SMC/scanner integration command: **809 passed** (`8.48s`).
- `py_compile` và `git diff --check`: **passed**.

## Gate

Đã hoàn thành phạm vi Task 65 và chuyển trạng thái **WAITING_REVIEW**. Dừng tại gate 72, không làm Task 66.
