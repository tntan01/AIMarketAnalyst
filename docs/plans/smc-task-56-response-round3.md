# Task 56 — response mapping sau review round 3

Trạng thái: **FIXES_READY / chờ Tech Lead review lại**. Giữ nguyên review và response các vòng trước; không đánh dấu APPROVED, không triển khai task 57 hoặc production rollout.

## Mapping finding → thay đổi → bằng chứng

| Finding | Thay đổi lần trình lại | Regression / evidence |
|---|---|---|
| R56-01 | `core/smc_context.py`: confirmation FVG nhận đủ lifecycle terminal canonical (`invalid`, `expired`, `broken`, cùng trạng thái legacy nếu có) và trả nguyên candidate, không reevaluate/promote lại. Session-gap policy chỉ loại open jump tại cặp qua closure; không yêu cầu exact open/close equality giữa các candle liên tục trong phiên. | `test_r56_01_fvg_terminal_invalid_and_expired_are_idempotent_buy_and_sell` kiểm confirmed → `invalid`/`expired` cho BUY/SELL. `test_session_gap_allows_in_session_third_open_tick_mismatch_buy_and_sell` kiểm lệch một tick vẫn là displacement BUY/SELL; negative session-only và unknown/unexpected gap vẫn fail-closed. |
| R56-02 | `core/smc_context.py`: khi event canonical chỉ có timestamp, nếu đã có `candles` thì resolve timestamp về đúng candle close và đếm chênh lệch index thực tế; không tính thời gian nghỉ phiên thành bar. BOS canonical dùng `status=confirmed`, IDs, timestamp và quality gates finite/causal. | `test_r56_02_timestamp_only_canonical_bos_uses_closed_candle_lineage_across_weekend` lấy BOS BUY/SELL thật từ `replay_smc_structure`, bỏ `occurred_index`, kiểm continuous và closure hợp lệ qua weekend đều confirm. `test_r56_02_genuine_canonical_bos_from_gate40_replay_promotes_ob` tiếp tục đối chiếu event canonical không có boolean `confirmed`. |
| R56-05 | Fixture/test tích hợp dùng một timeline H1 chung: 70 rows gồm pattern tạo OB/FVG/S-D, BOS canonical BUY/SELL và history tới cutoff. Event positive lấy nguyên bản từ evaluator; sau đó mới confirmation → availability → `SmcZone` typed round-trip → regroup. | `test_r56_05_actual_ob_fvg_sd_lineage_groups_one_setup_for_buy_and_sell` không dùng `_event()`; đối chiếu event/broken-level ID với provenance BUY/SELL trong fixture và giữ một setup cùng child lineage sau round-trip. |

Các finding R56-03, R56-04, R56-06, R56-07, R56-08 được giữ nguyên implementation đã CLOSED và chạy lại trong bộ gate/full review.

## Fixture / provenance

Fixture [smc_gate56_zone_pipeline.json](D:/Projects/AIMarketAnalyst/tests/fixtures/smc_gate56_zone_pipeline.json) tách rõ hai nguồn provenance:

- `canonical_gate40_provenance`: event H4 dùng cho regression schema/OB canonical riêng.
- `integrated_structure_provenance`: event H1 BUY/SELL sinh từ chính `integrated_rows` của fixture bằng `replay_smc_structure`, cùng symbol/timeframe/cutoff với integration test.

Timeline tích hợp có 27 rows tạo pattern và 43 rows history tail, tổng cộng 70 H1 candles; confirmation diễn ra trước cutoff index 69. Không sửa các báo cáo review round 1/2.

## Verification

```powershell
$gateTests = @(rg --files tests -g '*task4[1-9].py' -g '*task5[0-5].py')
python -m pytest @gateTests tests/test_smc_gate56_review_regressions.py -q
# 59 passed in 1.32s

$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
# 632 passed in 7.69s

python -m py_compile core/smc_context.py core/smc_models.py tests/test_smc_gate56_review_regressions.py tests/test_smc_fvg_session_task47.py
git diff --check
# Exit 0; chỉ warning LF/CRLF từ Git.
```

## Manifest / SHA256

| File | SHA256 |
|---|---|
| `core/smc_context.py` | `CA8F421F32D4E43994AC59D0BC7611918C8FB69BC17D2F33505BD97F7DCC9DA1` |
| `core/smc_models.py` | `C8FBBD90AA10E7F99B61DE8DAEBB30B5019B9D3A9E98987EE27144C2D29045E5` |
| `tests/test_smc_gate56_review_regressions.py` | `0B9C3ACB4868F4FE155A319444FC716A75ED96237C8D9768CCEF47CDABE51145` |
| `tests/test_smc_fvg_session_task47.py` | `E82B1A96991DE4DF51B6A1961858275049393341EDCC76888867687E25B8E05F` |
| `tests/fixtures/smc_gate56_zone_pipeline.json` | `DFA9269D2071F30CED72869C5DD8FFCF0C018C3DF43863C0E58103C75E3F8207` |
| `docs/plans/smc-implementation-progress.md` | `BAD318C4BE0DD31ED722150681A5E0A11275FE371A44363CF1ED8C0FCB89E9AF` |
