# Task 71 — Implementation response

Trạng thái bàn giao hiện tại: **Gate72 CHANGES_REQUESTED**, theo [Tech Lead review gate72](D:/Projects/AIMarketAnalyst/docs/plans/smc-task-72-review.md), ngày 2026-09-11. Task71 đã có implementation/tests nhưng chặng57–71 còn **9 finding OPEN (R72-01…R72-09)**; chưa được làm task73.

Tech Lead đồng bộ trạng thái sau review. Nội dung và kết quả test dưới đây giữ nguyên như hồ sơ Coder trình WAITING_REVIEW, không phải kết luận nghiệm thu. Reviewer chạy baseline 854 passed và probes bổ sung 14 failed, 2 passed; xem báo cáo để biết từng input/expected và tiêu chí sửa.

## Phạm vi

Task 71 bổ sung acceptance matrix cho liquidity/context, khóa provenance nguồn, consumed ownership, family-child dedupe, D1 proximity và precedence của canonical lifecycle so với legacy flags.

## Mapping contract → code → tests

| Contract | Tests |
|---|---|
| Sweep giữ source pool và `reclaimed_at` theo close boundary | `test_sweep_source_time_and_pool_provenance_are_preserved` |
| Một sweep chỉ tạo một assignment/contribution dù nhiều child cùng setup | `test_consumed_evidence_has_one_assignment_and_one_contribution` |
| Family children cùng setup dùng cùng linked sweep, không nhân source | `test_duplicate_family_children_share_linked_sweep_without_duplicate_source` |
| Proximity-only không tạo D1 reaction | `test_d1_proximity_only_has_no_reaction_evidence` |
| Canonical D1 lifecycle là nguồn duy nhất; legacy metadata không tăng evidence | `test_d1_canonical_reaction_is_the_single_source_of_truth`, `test_legacy_conflicting_reaction_flags_cannot_override_open_visit` |

## Verification

- Task 71 + Task 69/70/linking/context suites → **36 passed**.
- Bộ SMC/scanner chuẩn (mọi `test_smc*.py` + technical/scanner/integration/replay) → **854 passed in 8.97s**.
- `python -m py_compile core/smc_confluence.py core/smc_context.py core/smc_sweep_linking.py` → **passed**.
- `git diff --check` → **passed**.
- Không sửa/skip/xfail golden fixture hoặc acceptance test.

## Gate

Tech Lead đã thực hiện gate72 và quyết định **CHANGES_REQUESTED**. Chỉ sửa các finding trong báo cáo, trình `docs/plans/smc-task-72-response.md` cùng mapping/tests/manifest để review lại; không tự APPROVED hoặc làm task73. Gate56 vẫn APPROVED; chưa phê duyệt production rollout/auto-entry.
