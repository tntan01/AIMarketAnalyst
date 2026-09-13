# Task 59 — implementation response

Trạng thái: **DONE / chờ review gate 72**. Đã triển khai riêng điều kiện kết thúc visit theo exit tolerance; chưa làm task 60 hoặc các task tiếp theo.

## Mapping yêu cầu → code → tests

| Yêu cầu | Implementation | Bằng chứng |
|---|---|---|
| Rời vùng theo tolerance đã duyệt | `analyze_zone_lifecycle` nhận `tick_size` và `atr_current`, tính `zone_tolerance = max(1*tick, 0.05*ATR_current)`; hỗ trợ explicit `zone_tolerance` cho caller đã resolve metadata. | `test_inside_tolerance_does_not_close_visit`; `test_invalid_tolerance_metadata_is_rejected`. |
| Rung sát biên không tạo exit giả | Overlap dùng vùng mở rộng `[low - tolerance, high + tolerance]`; candle vẫn trong vùng này tiếp tục visit hiện tại. | `test_inside_tolerance_does_not_close_visit`; `test_tolerance_is_symmetric_for_sell`. |
| Outside vượt tolerance mới đóng visit | Khi candle không còn overlap vùng mở rộng, visit được đóng với `completed_unreacted`; `end_index` vẫn là candle overlap cuối. | `test_outside_beyond_tolerance_closes_visit_and_reentry_starts_next_visit`; `test_exit_timestamp_is_close_of_last_inside_boundary`. |
| Re-entry phải qua outside hợp lệ | Visit chỉ reset sau candle outside vượt tolerance; overlap tiếp theo tạo visit ID ordinal mới, không gộp nhầm hoặc tạo lại do rung biên. | `test_outside_beyond_tolerance_closes_visit_and_reentry_starts_next_visit`. |
| Không nới protective geometry | Tolerance chỉ được dùng cho overlap/exit; original zone bounds và invalidation check hiện hữu không bị thay đổi. | Existing lifecycle regression vẫn pass cùng Task 59 tests. |

## Files thay đổi

- `core/smc_lifecycle.py`: thêm resolve tolerance, áp dụng cho overlap/exit và giữ availability/close boundary.
- `core/smc_context.py`: truyền metadata `tick_size`/`atr_current` nếu zone enrichment có sẵn.
- `tests/test_smc_zone_lifecycle_task59.py`: regression BUY/SELL, jitter, exit, re-entry và invalid metadata.
- `docs/plans/smc-implementation-progress.md`: ghi Task 59 DONE, chờ review gate 72.
- `docs/plans/smc-task-59-response.md`: báo cáo này.

Không triển khai reaction/follow-through của task 60, penetration/dwell mới của task 61 hoặc fill/invalidation/expiry các task sau.

## Verification

Targeted Task 59 + lifecycle:

```text
python -m pytest tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task58.py tests/test_smc_zone_lifecycle.py -q
19 passed in 0.32s
```

Toàn bộ SMC và integration suite:

```text
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
768 passed in 8.14s
```

`py_compile` cho lifecycle/context/models và test Task 59 đạt. `git diff --check` đạt; chỉ có warning LF/CRLF chuẩn của Git trên Windows.

## SHA256

| File | SHA256 |
|---|---|
| `core/smc_lifecycle.py` | `0840FD449E8C7EA9B4C4A8851FC6C125E5D58596619B805468BE7418FCF92202` |
| `core/smc_context.py` | `4C9161CCD5E0FF930809C84551B280C73E5940E211234261D16FA02F6411BEA8` |
| `core/smc_models.py` | `66453868D9B0B39368B4C24CEC5F274CDB1A104D3703C75F1D5C22234E05C519` |
| `tests/test_smc_zone_lifecycle_task59.py` | `1B702FC778827C084E303B5FF978A81CB7964F525D013741BA6FF8C1590E9137` |
| `docs/plans/smc-implementation-progress.md` | `FF77069BE4FBC9FC4BA651A62D3EBFCDBFD1C8E10C51B4619EDB7A309B70FA6A` |

## Handoff

Task 59 đã hoàn thành trong phạm vi exit tolerance, sẵn sàng cho Tech Lead review tại gate 72. Dừng tại đây; không làm task 60 trở đi.
