# Task 58 — implementation response

Trạng thái: **DONE / chờ review gate 72**. Đã triển khai riêng entry boundary của lifecycle; chưa làm task 59–60 hoặc các task tiếp theo.

## Mapping yêu cầu → code → tests

| Yêu cầu | Implementation | Bằng chứng |
|---|---|---|
| Mở visit ở overlap đầu tiên sau departure | `analyze_zone_lifecycle` bắt đầu quét từ `departure_end_index + 1`; candle departure không thể tạo visit. | `test_departure_overlap_is_excluded_and_first_later_overlap_opens_visit`. |
| Chỉ tính zone sau khi available | Thêm `available_at` tùy chọn cho lifecycle; candle chỉ được xét khi `close_at >= available_at`. `enrich_zones` truyền `item["available_at"]` xuống lifecycle. | `test_available_at_blocks_overlap_until_zone_is_usable`; `test_enrich_zones_passes_available_at_to_canonical_lifecycle`. |
| Chạm biên là overlap hợp lệ | Giữ overlap inclusive: `candle.low <= zone_high` và `candle.high >= zone_low`; không thêm exit tolerance của task 59. | `test_overlap_at_either_zone_boundary_opens_visit`. |
| Mốc entry dùng candle close | `entered_at` và `first_retest_time` dùng canonical UTC close boundary theo timeframe; các lifecycle close mốc tương ứng cũng dùng close boundary. | `test_departure_overlap_is_excluded_and_first_later_overlap_opens_visit`. |
| Input availability phải rõ ràng | `available_at` yêu cầu timestamp timezone-aware UTC; không tự sửa timestamp thiếu timezone. | `test_available_at_must_be_timezone_aware`. |

## Files thay đổi

- `core/smc_lifecycle.py`: thêm availability boundary, timeframe/close helper và entry selection sau departure.
- `core/smc_context.py`: truyền `available_at` từ zone enrichment vào lifecycle.
- `tests/test_smc_zone_lifecycle_task58.py`: regression cho departure, availability, boundary và validation.
- `docs/plans/smc-implementation-progress.md`: ghi Task 58 DONE, chờ gate 72.
- `docs/plans/smc-task-58-response.md`: báo cáo này.

Không triển khai exit/rung biên/tolerance của task 59 hoặc reaction của task 60.

## Verification

Targeted Task 58 + domain/lifecycle:

```text
python -m pytest tests/test_smc_zone_lifecycle_task58.py tests/test_smc_zone_lifecycle.py tests/test_smc_domain_models.py -q
22 passed in 0.34s
```

Toàn bộ SMC và integration suite:

```text
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
763 passed in 8.00s
```

`py_compile` cho `core/smc_lifecycle.py`, `core/smc_models.py`, `core/smc_context.py` và test Task 58 đạt. `git diff --check` đạt; chỉ có warning LF/CRLF chuẩn của Git trên Windows.

Full repository smoke run trước đó có 3842 passed, 8 skipped, 16 xfailed và 7 failure ngoài phạm vi Task 57/58 (1 UI navigation, 6 FRED fallback); không sửa các lỗi ngoài phạm vi.

## SHA256

| File | SHA256 |
|---|---|
| `core/smc_lifecycle.py` | `1442970F66437C458DF4F0AE76D4E4BE4901A3EF4ED9EA88D19A50490634FE25` |
| `core/smc_context.py` | `91B7618F86DBD921EA93FD980B6F519CD51C0138D1F2171C8197069AB03DEBFA` |
| `core/smc_models.py` | `66453868D9B0B39368B4C24CEC5F274CDB1A104D3703C75F1D5C22234E05C519` |
| `tests/test_smc_zone_lifecycle_task58.py` | `8BBEA31C327731F46D8D100D1659EE66C9B0EF227E0AE2FDDC1BF560B9DF7878` |
| `docs/plans/smc-implementation-progress.md` | `81B5E95AEE7C54781631A3B56E16A0BC5757C0EA1C8D2145FDBD03C560C6A608` |

## Handoff

Task 58 đã hoàn thành trong phạm vi entry boundary, sẵn sàng cho Tech Lead review tại gate 72. Dừng tại đây; không làm task 59 trở đi.
