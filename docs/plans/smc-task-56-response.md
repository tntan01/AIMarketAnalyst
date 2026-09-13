# Task 56 — response mapping sau CHANGES_REQUESTED

Trạng thái: **FIXES_READY / chờ Tech Lead review lại**. Không đánh dấu APPROVED và không triển khai task 57 hoặc production rollout.

## Mapping finding → thay đổi → bằng chứng

| Finding | Thay đổi | Regression / evidence |
|---|---|---|
| R56-01 | `core/smc_context.py`: thêm `confirm_fvg_candidate(s)`, xác nhận tại close nến thứ ba, kiểm tra cutoff, gap, middle quality và session continuity. | `tests/test_smc_gate56_review_regressions.py::test_r56_01_fvg_confirmed_available_at_third_close_buy_and_sell`; BUY/SELL positive và cutoff sớm, weak middle fail-closed. |
| R56-02 | `core/smc_context.py`: OB chỉ promote khi measurement ATR hợp lệ, event có `event_id`/`broken_level_id`, BOS confirmed, chưa invalidated/reclaimed/expired, đúng timeframe và timestamp/index close causal trong tối đa 3 bar. | `::test_r56_02_ob_requires_atr_ids_validity_and_causal_close_provenance`; BUY/SELL genuine event, thiếu ATR/ID, invalidated, mismatch và timestamp-only late. |
| R56-03 | `core/smc_context.py`: S/D confirmation bắt buộc `directional_close_location >= 0.70`, đối xứng cho BUY/SELL. | `::test_r56_03_sd_directional_close_location_is_required`; raw OHLC giữ các gate khác đạt nhưng close-location `.60/.40` bị giữ candidate. |
| R56-04 | `core/smc_context.py`: canonicalize một base hẹp nhất cho mỗi `(departure_index, direction)`, tie-break deterministic; giữ child ID riêng và không tạo duplicate typed child. | `::test_r56_04_sd_selects_one_canonical_base_per_impulse_and_typed_setup_is_safe`; nested base qua detector → confirmation → `SmcSetup`. |
| R56-05 | `core/smc_context.py`: FVG `departure_source_id` dùng middle displacement candle; OB/S-D dùng departure source; grouping không merge theo overlap. | `::test_r56_05_actual_ob_fvg_sd_lineage_groups_one_setup_for_buy_and_sell`; actual detector BUY/SELL có một setup chung. |
| R56-06 | `core/smc_context.py`: `apply_zone_availability` lọc nến đã đóng `<= as_of` trước khi gọi history assessment. | `::test_r56_06_availability_is_invariant_to_future_valid_or_invalid_candles`; prefix, future-valid và future-invalid cho cùng coverage/usability. |
| R56-07 | `core/smc_models.py`: adapter gom measurement top-level của detector vào canonical `evidence` tại `SmcZone.from_dict` và `SmcSetup.from_zones`. | `::test_r56_07_actual_detector_evidence_survives_zone_and_setup_round_trip`; actual OB measurement giữ qua Zone/Setup serialization. |
| R56-08 | `core/smc_context.py`: detector start index dùng `required_history_for_lifetime(timeframe)`, tách retention khỏi output Top-K. | `::test_r56_08_m15_cold_rebuild_keeps_zone_at_l_minus_one_l_and_l_plus_one`; M15 budget `147`, cold rebuild giữ candidate và promote được ở các mốc L-1/L/L+1. |

## Fixture / timeline

Fixture [smc_gate56_zone_pipeline.json](D:/Projects/AIMarketAnalyst/tests/fixtures/smc_gate56_zone_pipeline.json) có OHLC hợp lệ cho BUY và SELL mirror, event provenance (`event_id`, `broken_level_id`, `occurred_index`, `occurred_at`, `confirmed_at`, `timeframe`) và timeline:

`formation_start=15 → displacement/departure_source=16 → FVG completion=17 → structure confirmation=17 → cutoff=17`.

FVG available tại close index 17; OB event dùng cùng departure source index 16; S/D canonical base dùng impulse index 16; history budget H1 là 69 bar. Test `test_r56_05...` chạy ba family qua detector thực và grouping; test `test_r56_07...` chạy detector thực qua typed round-trip.

## Verification

```text
python -m pytest <task41–55 files> tests/test_smc_gate56_review_regressions.py -q
54 passed in 1.23s

$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
627 passed in 7.72s

python -m py_compile core/smc_context.py core/smc_models.py
git diff --check
```

## Manifest / SHA256

Các digest dưới đây được tính sau khi hoàn tất chỉnh sửa implementation, fixture, regression và progress:

| File | SHA256 |
|---|---|
| `core/smc_context.py` | `2CE72588C47C10ED426343CAB2985A26B46DA4D0C1900587622F2D80D256399E` |
| `core/smc_models.py` | `B220981EE74D12809B1DFFD82C09979E4BBA74900EC0DD6E96A4B7881520BC4A` |
| `tests/test_smc_gate56_review_regressions.py` | `C2BB8288A0ED5ABEB19913AD6F977122039D1C65FBA19129DBC3A015F351F22C` |
| `tests/fixtures/smc_gate56_zone_pipeline.json` | `901CB4DF70C58C4533D6840AF0D4901CC3B7F6886D75875BBC44751DED1756F3` |
| `tests/test_smc_order_block_confirmation_task44.py` | `3A90FA5BA6BBE02F5F1824FBC770B63F5F87A513B29423A17398FF0812E18590` |
| `tests/test_smc_zone_identity_task55.py` | `607EE3FAC1F175C73B719B5C6585742B2C9C5AB40E846B5B67CB76DC68AB9948` |
| `docs/plans/smc-implementation-progress.md` | `19986C4CD4ADB5F84A2E4F54CEB6E1E08668C92E25D65B004B98EE3E9BB1A727` |
