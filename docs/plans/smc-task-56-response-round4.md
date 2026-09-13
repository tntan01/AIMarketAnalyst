# Task 56 — response mapping sau review round 4

Trạng thái: **FIXES_READY / chờ Tech Lead review lại**. Review và response các vòng trước được giữ nguyên; không đánh dấu APPROVED, không triển khai task 57 hoặc production rollout.

## R56-01 — session-gap displacement

Đã sửa `core/smc_context.py` để không veto blanket mọi open jump tại session boundary. Với cặp candle qua closure:

- Nếu reopen nằm bên trong range của candle trước, open jump không bị coi là session-only; middle candle vẫn được đánh giá bằng displacement/quality gates đã có.
- Nếu reopen nằm ngoài hoặc đúng biên range candle trước, formation session-only vẫn bị loại.
- Các cặp candle liên tục trong phiên vẫn không bị ràng buộc exact open/close equality.

Không thêm threshold mới hoặc thay đổi gap geometry/quality policy trong P5.

Regression đã bổ sung/khóa lại trong `tests/test_smc_fvg_session_task47.py`:

- Probe H1 BUY/SELL với middle open lần lượt `100.0`/`100.1`, reopen nằm trong range candle trước, và third open lệch một tick; cả hai side đều đi qua candidate → confirmation tại third close.
- Session-only negative BUY/SELL vẫn không tạo candidate.
- Weak/wrong-direction middle cùng unknown/unexpected gap tiếp tục fail-closed qua các test hiện hữu.

## Các finding đã CLOSED được giữ nguyên

R56-01 terminal `invalid`/`expired`, R56-02 timestamp-only BOS qua closure, R56-03/R56-04, R56-05 fixture tích hợp + typed lineage, R56-06, R56-07 và R56-08 không thay đổi. Fixture tích hợp và event canonical thật từ round 3 được giữ nguyên.

## Verification

```powershell
$gateTests = @(rg --files tests -g '*task4[1-9].py' -g '*task5[0-5].py')
python -m pytest @gateTests tests/test_smc_gate56_review_regressions.py -q
# 59 passed in 1.31s

$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
# 632 passed in 7.70s

python -m py_compile core/smc_context.py core/smc_models.py tests/test_smc_gate56_review_regressions.py tests/test_smc_fvg_session_task47.py
git diff --check
# Exit 0; chỉ warning LF/CRLF từ Git.
```

## Manifest / SHA256

| File | SHA256 |
|---|---|
| `core/smc_context.py` | `4C8BA93AA51A50C897B479EBEF491C24F1FC2A9007B914EEDA42586899453972` |
| `core/smc_models.py` | `C8FBBD90AA10E7F99B61DE8DAEBB30B5019B9D3A9E98987EE27144C2D29045E5` |
| `tests/test_smc_gate56_review_regressions.py` | `0B9C3ACB4868F4FE155A319444FC716A75ED96237C8D9768CCEF47CDABE51145` |
| `tests/test_smc_fvg_session_task47.py` | `D0CFEA37E3DBE972C97DD8B7DD743A380AB2FAE43E2DC62BB179336A522F3991` |
| `tests/fixtures/smc_gate56_zone_pipeline.json` | `DFA9269D2071F30CED72869C5DD8FFCF0C018C3DF43863C0E58103C75E3F8207` |
| `docs/plans/smc-implementation-progress.md` | `A4CDD004CD3176D587A1AD6740BD73AFF83AFC79AE163A4E15A01AA66BAD1775` |
