# Task 56 — response mapping sau review round 2

Trạng thái: **FIXES_READY / chờ Tech Lead review lại**. Review round 1 và round 2 không bị sửa; không đánh dấu APPROVED và không triển khai task 57 hoặc production rollout.

## Mapping finding → thay đổi → bằng chứng

| Finding | Thay đổi lần trình lại | Regression / evidence |
|---|---|---|
| R56-01 | `core/smc_context.py`: confirmation FVG loại các waiting/audit reason cũ trước khi reevaluate, giữ terminal invalidated/expired fail-closed; session gap chỉ được giữ khi mở phiên đúng close trước và middle displacement đạt quality, còn session-only/unknown/unexpected bị loại. | `tests/test_smc_gate56_review_regressions.py::test_r56_01_fvg_confirmed_available_at_third_close_buy_and_sell` kiểm cold/incremental parity, cutoff, BUY/SELL và weak-middle; `tests/test_smc_fvg_session_task47.py::test_session_gap_with_continuous_open_and_valid_displacement_is_candidate` kiểm positive displacement qua closure, còn session-only negative giữ nguyên. |
| R56-02 | `core/smc_context.py`: chấp nhận canonical `SmcStructureEvent.to_dict()` với `status=confirmed` dù không có boolean `confirmed`; vẫn yêu cầu event/broken-level IDs, timestamp/index/source timeframe causal, lifecycle active và measurement finite. Bổ sung body/range `>=.50`, body/ATR `>=.30`, directional close-location `>=.70`. | `tests/test_smc_gate56_review_regressions.py::test_r56_02_genuine_canonical_bos_from_gate40_replay_promotes_ob` dùng event thật từ `replay_smc_structure`, không gắn boolean; cùng test kiểm thiếu ATR/ID, invalidated, mismatch/late và BUY/SELL; quality probe độc lập chặn departure yếu. |
| R56-05 | `core/smc_models.py`: thêm và serialize/deserialize `departure_source_id`/`departure_source_time` trên `SmcZone`; grouping sau typed round-trip dùng lại canonical source thay vì fallback third candle. | `tests/test_smc_gate56_review_regressions.py::test_r56_05_actual_ob_fvg_sd_lineage_groups_one_setup_for_buy_and_sell` chạy detector → confirmation → availability → typed Zone → regroup cho BUY/SELL, giữ một setup và child identity. |

Các finding R56-03, R56-04, R56-06, R56-07, R56-08 được giữ nguyên implementation đã CLOSED ở lần trình trước và được chạy lại trong bộ regression.

## Fixture / timeline cập nhật

Fixture [smc_gate56_zone_pipeline.json](D:/Projects/AIMarketAnalyst/tests/fixtures/smc_gate56_zone_pipeline.json) hiện có 70 OHLC rows H1 để cutoff index 69 đủ history budget H1=69, pattern source `formation_start=15 → displacement/departure_source=16 → FVG completion=17`, và expected BUY/SELL mirror. `structure_provenance` trỏ tới event canonical thật từ [smc_gate40_structure_replay.json](D:/Projects/AIMarketAnalyst/tests/fixtures/smc_gate40_structure_replay.json); regression replay lại fixture gate40, đối chiếu `event_id`, `broken_level_id`, `status`, `occurred_at`, `confirmed_at` rồi mới promote OB.

M15 retention regression dùng timestamp cách nhau đúng 15 phút, 104 candles và cutoff lần lượt ở index 101/102/103 (L-1/L/L+1 theo confirmation index 22), thay vì step 1 giờ và cutoff cố định.

## Verification

```powershell
$gateTests = @(rg --files tests -g '*task4[1-9].py' -g '*task5[0-5].py')
python -m pytest @gateTests tests/test_smc_gate56_review_regressions.py -q
56 passed

$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
629 passed

python -m py_compile core/smc_context.py core/smc_models.py tests/test_smc_gate56_review_regressions.py
git diff --check
```

## Manifest / SHA256

| File | SHA256 |
|---|---|
| `core/smc_context.py` | `1659008D1C0EA563E8787221AAFAACC31DB6659B28FE75E0F4CD967F88FAF9D5` |
| `core/smc_models.py` | `C8FBBD90AA10E7F99B61DE8DAEBB30B5019B9D3A9E98987EE27144C2D29045E5` |
| `tests/test_smc_gate56_review_regressions.py` | `D746835C34071B04C568D1161DC0ACD6512781E9706059A160FE4109ADBCB1BC` |
| `tests/test_smc_fvg_session_task47.py` | `6323EC5ECABBAF8F97756EE9CD1D48E62E0A1C492AEE2912D6DEFA1DD95E380B` |
| `tests/fixtures/smc_gate56_zone_pipeline.json` | `AA4B400C2F7DFD01442D816DB13B70171136D30C09B9CEAB9790082A415720D3` |
| `docs/plans/smc-implementation-progress.md` | `1671A67076EF8E8E5D2BEB770C1FB9F49D9E9B37D80076CB8A8992A4D45A2118` |
