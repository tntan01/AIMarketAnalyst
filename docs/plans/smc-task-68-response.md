# Task 68 — Implementation response

Trạng thái: **DONE / WAITING_REVIEW tại gate 72**. Đã dừng sau Task 68; không triển khai Task 69.

## Phạm vi

Task 68 hoàn thiện linker sweep với zone/setup/visit provenance. Link hợp lệ phải cùng side, nằm trong zone hoặc cách boundary không quá `0.25 ATR`, và nằm trong formation/departure window không quá 20 bar hoặc visit window tương ứng. Một sweep chỉ độc quyền giữa các setup khác nhau; các child cùng setup được tham chiếu cùng evidence.

## Mapping contract → code → tests

| Contract | Code | Tests |
|---|---|---|
| Cùng side, distance `<=0.25 ATR`, thiếu ATR khi sweep ở ngoài zone thì fail-closed | `core/smc_sweep_linking.py:associate_sweeps_to_zones` | `test_link_distance_gate_is_inclusive_at_quarter_atr`, existing distance/symmetry/wrong-side tests |
| Formation/departure window, tối đa 20 bar, boundary inclusive | `associate_sweeps_to_zones` với `max_time_bars=20` | `test_link_time_window_is_inclusive_at_twenty_bars`, existing out-of-window test |
| Sweep nằm trong visit window được link và lưu visit ID | `associate_sweeps_to_zones(..., visits=...)` và visit records trong zone payload | `test_visit_window_can_link_a_sweep_after_departure` |
| Nhiều child cùng setup tham chiếu cùng sweep; setup khác không tái sử dụng sweep | owner key `(setup_id, sweep_id)` và broadcast trong cùng setup; zone không có setup giữ legacy one-to-one | `test_same_setup_children_reference_the_same_sweep`, `test_one_sweep_is_not_reused_by_another_setup`, existing family dedupe test |
| Link payload có setup/visit provenance và sweep time ưu tiên `reclaimed_at` | `SweepZoneLink.setup_id`, `visit_id`, `to_zone_payload`; context cập nhật `linked_zone_ids` khi broadcast | Task 68 tests + context/linking regression |

## Verification

- `python -m pytest tests/test_smc_sweep_linking_task68.py tests/test_smc_sweep_linking.py -q` → **15 passed**.
- Bộ SMC/scanner chuẩn (mọi `test_smc*.py` + technical/scanner/integration/replay) → **828 passed in 9.01s**.
- `python -m py_compile core/smc_sweep_linking.py core/smc_context.py` → **passed**.
- `git diff --check` → **passed**.
- Không sửa/skip/xfail golden fixture hoặc acceptance test.

## Gate

Đã hoàn thành đúng phạm vi Task 68, chuyển trạng thái **WAITING_REVIEW**, dừng tại gate 72 và chờ Admin/Tech Lead review. Không làm Task 69.
