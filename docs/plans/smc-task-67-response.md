# Task 67 — Implementation response

Trạng thái: **DONE / WAITING_REVIEW tại gate 72**. Đã dừng sau Task 67; không triển khai Task 68.

## Phạm vi

Task 67 khóa detector liquidity sweep theo contract P8. Sweep chỉ được phát khi wick vượt source pool bằng excursion strict và cùng candle đóng reclaim trở lại phía trong pool. Wick-only, close tiếp diễn xuyên level và excursion đúng boundary không tạo evidence.

## Mapping contract → code → tests

| Contract | Code | Tests |
|---|---|---|
| `excursion = max(2*tick, 0.10*ATR)`; hỗ trợ explicit buffer và ATR alias | `core/smc_context.py:detect_liquidity_sweeps` | `test_high_sweep_requires_strict_excursion_and_records_reclaim_provenance`, `test_exact_excursion_boundary_is_not_a_sweep` |
| High/low mirror; wick phải vượt pool và close reclaim strict cùng candle | `core/smc_context.py:detect_liquidity_sweeps` | `test_low_sweep_is_mirrored`, `test_wick_only_or_reclaim_close_controls_high_sweep` |
| Lưu depth, reclaim time/count và source pool | evidence payload của `detect_liquidity_sweeps`: `depth`, `depth_atr`, `reclaimed_at`, `reclaim_bars`, `source_pool_id`, `source_pool` và source swing provenance | `test_high_sweep_requires_strict_excursion_and_records_reclaim_provenance`, `test_pool_levels_are_used_when_explicitly_supplied` |
| Explicit pool levels là source; legacy swing-only route vẫn tương thích | tham số `liquidity_pools`; `_smc_for_timeframe` truyền pool output vào detector | `test_pool_levels_are_used_when_explicitly_supplied`; regression context/liquidity |
| Typed thiếu threshold fail-closed; buffer invalid bị reject | guard metadata và validation `excursion_buffer` | `test_typed_sweep_without_causal_excursion_metadata_fails_closed`, `test_invalid_excursion_buffer_is_rejected` |

## Verification

- Task 67 + context/liquidity/linking: **39 passed**.
- Bộ SMC/scanner chuẩn (mọi `test_smc*.py` + technical/scanner/integration/replay): **823 passed in 8.75s**.
- `python -m py_compile core/smc_context.py`: **passed**.
- `git diff --check`: **passed**.
- Không sửa/skip/xfail golden fixture hoặc acceptance test.

## Gate

Đã hoàn thành đúng phạm vi Task 67, chuyển trạng thái **WAITING_REVIEW**, dừng tại gate 72 và chờ Admin/Tech Lead review. Không làm Task 68.
