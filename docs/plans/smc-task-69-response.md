# Task 69 — Implementation response

Trạng thái: **DONE / WAITING_REVIEW tại gate 72**. Đã dừng sau Task 69; không triển khai Task 70.

## Phạm vi

Task 69 bổ sung consumed/ownership cho sweep linking. Mỗi `sweep_id` có tối đa một `owner_setup_id`; owner được chọn theo `claim_eligible_at = max(sweep_reclaim_at, setup_available_at)`, stable `setup_id` chỉ dùng khi cùng timestamp. Assignment ổn định, late setup không thu hồi owner lịch sử, child cùng setup chỉ áp dụng contribution một lần.

## Mapping contract → code → tests

| Contract | Code | Tests |
|---|---|---|
| Một sweep chỉ có một owner setup theo thời gian claim | `core/smc_sweep_linking.py:assign_sweep_ownership` | `test_owner_is_earliest_claim_time_not_smallest_setup_id`, `test_same_claim_time_uses_stable_setup_id_tie_break` |
| `assignment_id`, `owner_setup_id`, `assigned_at`, `claim_eligible_at` là audit fields ổn định | `SweepAssignment`, `_build_assignment_id` | `test_assignment_id_is_stable_when_duplicate_claims_are_replayed`, existing linker identity tests |
| Late setup không rút owner đã gắn | `assign_sweep_ownership(..., assignment_history=...)` | `test_existing_owner_history_is_not_revoked_by_late_setup` |
| Child cùng owner dùng cùng assignment nhưng contribution chỉ một lần | deterministic contribution winner trong `assign_sweep_ownership` | `test_same_setup_children_have_one_assignment_and_one_contribution` |
| Mark pool/sweep consumed và giữ audit output | `mark_sweeps_consumed`; context `_attach_zone_sweep_links` tích hợp assignment metadata | `test_mark_sweeps_consumed_preserves_one_assignment_and_marks_source` |
| Thiếu owner history không tự gán lại | `history_complete=False` trả `SWEEP_OWNER_HISTORY_INCOMPLETE` | `test_missing_owner_history_fails_closed` |

## Verification

- `python -m pytest tests/test_smc_sweep_consumed_task69.py tests/test_smc_sweep_linking_task68.py tests/test_smc_sweep_linking.py -q` → **23 passed**.
- Bộ SMC/scanner chuẩn (mọi `test_smc*.py` + technical/scanner/integration/replay) → **836 passed in 8.81s**.
- `python -m py_compile core/smc_sweep_linking.py core/smc_context.py` → **passed**.
- `git diff --check` → **passed**.
- Không sửa/skip/xfail golden fixture hoặc acceptance test.

## Gate

Đã hoàn thành đúng phạm vi Task 69, chuyển trạng thái **WAITING_REVIEW**, dừng tại gate 72 và chờ Admin/Tech Lead review. Không làm Task 70.
