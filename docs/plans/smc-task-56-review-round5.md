# Tech Lead review — gate 56, lần 5

**Quyết định: CHANGES_REQUESTED. Chưa được làm task 57.**

- Reviewer: Codex, Tech Lead theo yêu cầu người dùng; tiếp tục cùng lượt review sau yêu cầu “tiếp tục review”.
- Thời điểm: 2026-09-11, khoảng 04:33 Asia/Saigon.
- Phạm vi: phần session-gap R56-01 còn mở, regression và tính toàn vẹn bản trình lại. Chỉ thêm báo cáo này; không sửa implementation, tests, specs, progress hoặc báo cáo cũ.
- HEAD `fb9ea527ee7ff0eb48c53875e24796260008e92c`, branch `main`; quyết định gắn với working-tree content, không chỉ HEAD.
- Response hiện tại: `docs/plans/smc-task-56-response-round4.md`; manifest **6/6 khớp SHA256**.

## 1. Kết luận

**Giữ 7/8 finding CLOSED. R56-01 còn PARTIAL / P2.** Probe reopen lệch một tick *bên trong* range từ lần 4 đã được sửa. Tuy nhiên rule mới vẫn đồng nhất reopen tại/ngoài biên range với session-only gap, nên loại displacement hợp lệ. Không còn các blocker P1 của vòng trước.

R56-02…R56-08 giữ CLOSED trong phạm vi gate56. Không yêu cầu làm lại fixture tích hợp đã đạt hoặc mở rộng sang lifecycle/production.

## 2. Finding còn lại: phân loại sai ngay tại biên range

**Vị trí:** `core/smc_context.py:545–555`, đặc biệt `:549`:

```python
and current.open != previous.close
and not (previous.low < current.open < previous.high)
```

Điều kiện này chỉ cho phép reopen khác close nếu nằm *strictly inside* range trước. Tại biên hoặc ngoài biên, code loại cả formation mà không xét gap cụ thể có thật sự chỉ do closure hay không. Việc nằm ngoài range không đủ để kết luận mọi displacement sau đó là session-only, nhất là khi middle candle đã giao dịch trở lại range cũ.

P5 tại `docs/plans/smc-parameter-table.md:65` vẫn quy định reject gap **chỉ do session boundary**, giữ gap có displacement hợp lệ. Không có rule “reopen tại biên là session-only”.

### Positive matrix tái hiện bằng OHLC

H1 EUR/USD; tick=.1; ATR trước sự kiện=5. Timestamp qua closure được helper hiện tại phân loại `session_gap`:

| Candle open UTC | O/H/L/C |
|---|---|
| 2026-09-11 21:00 | 100 / 100 / 99 / 99.5 |
| 2026-09-13 21:00 | **99.9, 100.0 hoặc 100.1** / 103 / 99.5 / 102.5 |
| 2026-09-13 22:00 | 102 / 104 / 101 / 103 |

Middle low=99.5 quay vào range [99,100] trước đó; middle close=102.5 thể hiện displacement vượt range. Original FVG gap [100,101] vẫn đúng 1.0, minimum .5; không có bất kỳ gap dương nào phía trên first.high=100 do *reopen bằng 100* tự tạo. Ở biến thể open100.1, middle vẫn giao dịch lại tới 99.5 trước khi đóng phía trên; không thể kết luận chỉ từ open rằng toàn bộ gap là do kỳ nghỉ.

| BUY middle.open | Body/range | Directional close-location | Actual | Expected theo P5 |
|---:|---:|---:|---|---|
| 99.9 | .742857 | .857143 | confirmed | confirmed |
| 100.0, đúng first.high | .714286 | .857143 | **không có candidate** | confirmed |
| 100.1, đã re-enter range qua low99.5 | .685714 | .857143 | **không có candidate** | confirmed |

SELL mirror `(200-O,200-L,200-H,200-C)` tái hiện cùng kết quả. OHLC hợp lệ, gap/middle helper đều accepted. Không phải vấn đề thiếu ATR, gap nhỏ, wrong direction hay wick-only.

### Đính chính negative fixture và chỉ dẫn các vòng trước

`tests/test_smc_fvg_session_task47.py:46`, test `test_weekend_gap_with_session_only_jump_is_not_fvg_displacement`, dùng chính hàng **middle.open=100.0** ở trên và assert `[]`. Expected này **sai với P5**: mở tại first.high không tự tạo gap [100,101]; middle có displacement đạt chuẩn và low quay vào range cũ.

Các báo cáo trước yêu cầu giữ negative session-only nhưng chưa chỉ rõ fixture này không phải đối chứng session-only hợp lệ; cách diễn đạt đó có thể khiến Coder cố giữ assertion cũ bằng cách đặt strict range boundary. Reviewer đính chính tại đây: **không cần và không được giữ expected sai này**. Đổi nó thành positive hoặc thay bằng negative có nguồn gap đúng. Giữ nguyên các báo cáo cũ để bảo toàn lịch sử; dùng đính chính này làm chỉ dẫn hiện tại.

Đây không phải yêu cầu thêm một threshold hay family; là sửa phân loại nguồn của cùng R56-01. Không chỉ đổi `<` thành `<=` để vượt một hàng test rồi tiếp tục bỏ ca reopen ngoài range nhưng middle đã re-enter và displacement hợp lệ.

### Negative session-only độc lập, không phụ thuộc middle yếu

Reviewer đã chạy đối chứng sau, BUY/SELL mirror, tick=.1, ATR=5:

| Candle open UTC | BUY O/H/L/C |
|---|---|
| 2026-09-11 20:00 | 100 / 102 / 99 / 100 |
| 2026-09-11 21:00 | 100 / 101 / 99 / 101 |
| 2026-09-13 21:00 | 105 / 106 / 104 / 105.5 |

Hai candle đầu liên tục; closure nằm giữa middle và third. Middle body/range=.50 và close-location=1, nên quality accepted, nhưng high middle=101 chưa vượt first.high=102. Gap [102,104] xuất hiện do third reopen lên105 sau closure, không do displacement middle. Expected **không confirmed**; actual hiện tại 0 candidate cho cả BUY/SELL, 0 OHLC validation error. Giữ negative như ca này thay vì fixture gắn nhãn sai phía trên.

## 3. Điều kiện đóng cuối cùng cho R56-01

1. Dựa trên phần gap và candle displacement thực tế để phân biệt session-only với gap có formation độc lập; không dùng chỉ vị trí open như một veto toàn bộ formation.
2. Khóa đủ ba positive rows bên trong/tại biên/ngoài biên nhưng có re-entry ở matrix trên, cả BUY/SELL, đi qua detector → confirmation tại third close. Giữ original bounds và ID theo formation, không thay gap để hợp classifier.
3. Thay negative fixture sai, giữ negative session-only độc lập như đối chứng trên; giữ weak/wrong-direction, unknown/unexpected gap, tiny gap fail-closed. Không giải quyết bằng nhận tất cả session gaps.
4. Bổ sung assertion cho chính probe round4 `middle.open=100.1` nằm trong range [99,102]. Response hiện nói đã khóa 100.0/100.1, nhưng test đọc được vẫn dùng open100; reviewer đã chạy độc lập xác nhận fix hoạt động, còn regression cần thực sự lưu cả hai.
5. Nếu Coder muốn một policy bảo thủ khác P5, phải trình thay đổi policy rõ ràng để người có thẩm quyền duyệt, không gọi rule mới là semantics đã có. Không tự chỉnh spec trong lượt fix.

Phạm vi sửa tiếp theo chỉ là classifier session-gap và tests/evidence liên quan. Bảy finding CLOSED và fixture tích hợp cùng BOS thật không cần dựng lại.

## 4. Kiểm tra bản hiện tại

- Probe round4 với first range[99,102], middle.open100/100.1, third.open105.4 đều trả một candidate rồi confirmed tại third close: phần sửa đã có hiệu quả.
- Manifest mới 6/6 khớp. Hash model, gate56 regression và fixture tích hợp không đổi so với bản đã review lần 4; không có bằng chứng tái phát các finding CLOSED trong regression.
- Progress ghi FIXES_READY chờ review, không tự APPROVED hoặc làm task57. Giữ nguyên quyền dừng gate56 theo kế hoạch.

```powershell
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
# 632 passed in 7.60s

$gateTests = @(rg --files tests -g '*task4[1-9].py' -g '*task5[0-5].py')
python -m pytest @gateTests tests/test_smc_gate56_review_regressions.py -q
# 59 passed in 1.31s

python -m py_compile core/smc_context.py core/smc_models.py tests/test_smc_gate56_review_regressions.py tests/test_smc_fvg_session_task47.py
git diff --check
# Exit 0; chỉ warning LF/CRLF từ Git.
```

Các positive/negative probe trên được chạy read-only ngoài pytest. Chưa chạy toàn bộ repository, UI/live trading hoặc production acceptance. Test xanh hiện tại có chứa một expected sai được chỉ rõ ở §2, nên không đủ để APPROVED.

## 5. Bàn giao và dấu vân tay

Trình response/manifest mới sau khi sửa R56-01; ghi rõ negative fixture được đính chính, command/count actual và kết quả matrix. Giữ nguyên báo cáo cũ. **Chưa task57, chưa rollout production; chờ Tech Lead duyệt lại.**

| File | SHA256 |
|---|---|
| `core/smc_context.py` | `4C8BA93AA51A50C897B479EBEF491C24F1FC2A9007B914EEDA42586899453972` |
| `core/smc_models.py` | `C8FBBD90AA10E7F99B61DE8DAEBB30B5019B9D3A9E98987EE27144C2D29045E5` |
| `tests/test_smc_gate56_review_regressions.py` | `0B9C3ACB4868F4FE155A319444FC716A75ED96237C8D9768CCEF47CDABE51145` |
| `tests/test_smc_fvg_session_task47.py` | `D0CFEA37E3DBE972C97DD8B7DD743A380AB2FAE43E2DC62BB179336A522F3991` |
| `tests/fixtures/smc_gate56_zone_pipeline.json` | `DFA9269D2071F30CED72869C5DD8FFCF0C018C3DF43863C0E58103C75E3F8207` |
| `docs/plans/smc-task-56-response-round4.md` | `948DB4164C6D1AF0EB39845A602817A71D10DEF8EB10F58CED7812221E6C4CD2` |
| `docs/plans/smc-task-56-review-round4.md` | `1C2099839471742D40B0C18B5BAEE7B559C49D6C99E276FE357EE0F9B80CE4EB` |
