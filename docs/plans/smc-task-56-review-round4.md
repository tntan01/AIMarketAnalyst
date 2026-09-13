# Tech Lead review — gate 56, lần 4

**Quyết định: CHANGES_REQUESTED. Chưa được làm task 57.**

- Reviewer: Codex, Tech Lead theo yêu cầu người dùng.
- Thời điểm: 2026-09-11, khoảng 04:23 Asia/Saigon.
- Phạm vi: R56-01/R56-02 còn mở sau lần 3, fixture tích hợp mới và regression. Chỉ thêm báo cáo này; không sửa implementation/tests/specs/progress hoặc các báo cáo cũ.
- Bản trình lại: `docs/plans/smc-task-56-response-round3.md`; manifest mới **6/6 file khớp SHA256**.

## 1. Kết luận

**7/8 finding CLOSED. Chỉ còn phần session-gap của R56-01, mức P2.** Phần terminal invalid của R56-01 đã sửa; R56-02 và yêu cầu fixture tích hợp đã được xác minh đạt trong lượt này. Không còn giữ các vấn đề P1 cũ làm blocker.

| Finding | Kết luận lần 4 |
|---|---|
| R56-01 | **PARTIAL / P2:** terminal invalid/expired và in-session open mismatch đã sửa; vẫn reject mọi open jump tại closure, kể cả displacement hợp lệ không phải session-only |
| R56-02 | **CLOSED:** canonical timestamp-only BOS được resolve vào candle thật; closure không bị tính thành bar; biên 3/4 actual bars đúng |
| R56-03 | Giữ CLOSED — S/D close-location |
| R56-04 | Giữ CLOSED — canonical base/dedup S/D |
| R56-05 | Giữ CLOSED — typed departure lineage/regroup; fixture tích hợp dùng event thật cùng nguồn đã đạt |
| R56-06 | Giữ CLOSED — closed history/cutoff |
| R56-07 | Giữ CLOSED — measurement evidence |
| R56-08 | Giữ CLOSED — detector history retention, không suy ra lifecycle expiry đã triển khai |

## 2. R56-01 còn mở — Một tick tại reopen vẫn loại displacement thật

**Vị trí:** `core/smc_context.py:545–554`.

Code đã bỏ exact equality giữa hai candle liên tục trong phiên. Tuy nhiên nhánh `session_open_jumps` vẫn coi **bất kỳ** `current.open != previous.close` tại cặp qua closure là lý do loại toàn bộ FVG, không phân biệt session-only gap với formation có displacement độc lập.

P5 trong `docs/plans/smc-parameter-table.md` quy định:

> Reject gap chỉ do session boundary; giữ gap có candle displacement hợp lệ.

“Có open jump” không tương đương “gap chỉ do session boundary”. Đây vẫn là phần exact-equality policy đã yêu cầu sửa ở lần 3, không phải threshold mới hoặc yêu cầu thêm family.

### Probe BUY/SELL có OHLC hợp lệ

H1 EUR/USD; tick=.1; ATR before event=5. Timestamps dùng closure đã được calendar helper phân loại:

| Open time UTC | O/H/L/C |
|---|---|
| 2026-09-11 21:00 | 101 / 102 / 99 / 100 |
| 2026-09-13 21:00 | **100 hoặc 100.1** / 106 / 99.8 / 105.5 |
| 2026-09-13 22:00 | 105.4 / 107 / 103 / 106 |

Chỉ thay open nến giữa một tick; low/high/close giữ nguyên. Giá reopen vẫn nằm trong range [99,102] của candle đầu. Gap FVG [102,103] hình thành sau middle displacement, không phải một price jump từ dưới 102 lên trên 103 khi mở phiên.

```text
middle.open=100.0:
  body/range=.887097; gap_width=1; middle accepted=True; 1 candidate
middle.open=100.1:
  body/range=.870968; gap_width=1; middle accepted=True; 0 candidate
```

Directional close-location vẫn khoảng .919; minimum gap là max(.2,.5)=.5, nhỏ hơn gap 1. SELL mirror `(200-O,200-L,200-H,200-C)` cho cùng kết quả: open tương ứng 100.0 nhận, 99.9 bị loại. Giảm open jump về 0 không thay gap geometry hay làm mất displacement — bằng chứng gap không chỉ do closure.

**Ảnh hưởng:** bỏ vùng đạt P5 chỉ vì giá mở phiên lệch một tick. Không còn lỗi phục hồi vùng invalid; vì vậy mức còn lại là P2, không phải P1 như các vòng trước.

### Điều kiện đóng, giới hạn rõ cho lượt sửa tiếp theo

1. Phân biệt session-only contribution với displacement hợp lệ; bỏ blanket veto chỉ dựa vào open khác close. Không sửa P5 thành “cấm mọi open jump” để khớp implementation.
2. Khóa positive BUY/SELL của probe trên: gap [102,103] và middle quality vẫn đạt khi reopen nằm trong range cũ và có displacement thực. Test phải đi qua candidate → confirmation tại third close.
3. Giữ negative session-only thực sự, weak/wrong-direction middle, unknown/unexpected gap; không chuyển sang nhận mọi session gap.
4. Nếu muốn một policy bảo thủ khác P5, trình đề xuất riêng để được quyết định; không tự thêm threshold mới. Review hiện tại yêu cầu thực hiện policy đã duyệt, không ép một thuật toán phân rã cụ thể chưa có trong spec.

## 3. Bằng chứng đóng các phần còn lại

### R56-01 terminal và in-session mismatch

- Guard mới nhận canonical `invalid` cùng `expired` và legacy terminal aliases. Regression confirmed → invalid/expired BUY/SELL giữ trạng thái, timestamp và payload; không promote lại.
- Trường hợp third.open lệch một tick nhưng hai candle cuối liên tục trong phiên đã được nhận. Pending/cold parity và confirmation trước/sau cutoff tiếp tục pass.

### R56-02 association theo candle thật

- Đọc nhánh mới: khi canonical event không có index và caller có candles, resolve `occurred_at` về đúng candle close; không tìm thấy thì reject. Sau đó áp association bằng index và validate timestamp như nhánh có index.
- Regression lấy nguyên BOS từ `replay_smc_structure`, default pivot width 5, BUY/SELL, continuous và weekend closure: đều confirmed, không cần boolean confirmed hoặc tự gắn index.
- Probe reviewer độc lập giữ cùng OB đạt quality ở departure index24, thêm 2 hoặc 3 candle phẳng trước genuine BOS: **3 actual bars → confirmed; 4 actual bars → candidate/OB_STRUCTURE_BREAK_MISSING**, cho cả BUY/SELL. Như vậy negative thực sự đi qua association gate, không chỉ fail quality trước đó.

### Fixture tích hợp cùng nguồn thật

Đã chạy `integrated_rows + integrated_history_tail_rows`: **70 H1 candles, 0 OHLC validation error**, BUY/SELL mirror. Mỗi side có một BOS thật từ chính timeline:

| Side | BOS event ID | occurred/confirmed UTC |
|---|---|---|
| BUY | `smc-bos-52a8958e48b4d9d7880b` | 2026-09-11 22:00 |
| SELL | `smc-bos-dc9e88ec4c3dfe9c6d17` | 2026-09-11 22:00 |

Actual pipeline mỗi side:

- OB và FVG available_at=22:00; S/D available_at=21:00 cùng ngày.
- Cả ba family confirmed; availability/history seam báo usable tại cutoff cuối.
- Qua typed zone serialization rồi regroup: một setup, đúng direction.
- Test tích hợp không còn dùng `_event()` cho positive này. H4 gate40 provenance đã tách riêng, không dùng xác nhận H1 zone khác nguồn.

Đây là acceptance synthetic của detector/availability/grouping, không phải dữ liệu thị trường thực hoặc phê duyệt lifecycle/geometry/planner/production. Không lấy nhãn usable của seam hiện tại để tuyên bố đã hoàn thành các task sau gate56.

## 4. Verification mới

```powershell
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
# 632 passed in 7.71s

$gateTests = @(rg --files tests -g '*task4[1-9].py' -g '*task5[0-5].py')
python -m pytest @gateTests tests/test_smc_gate56_review_regressions.py -q
# 59 passed in 1.30s

python -m py_compile core/smc_context.py core/smc_models.py tests/test_smc_gate56_review_regressions.py tests/test_smc_fvg_session_task47.py
git diff --check
# Exit 0; chỉ warning LF/CRLF từ Git.
```

Đã chạy thêm probe integration/association/session read-only được mô tả ở trên. Chưa chạy toàn repository, UI/live trading hoặc production acceptance.

## 5. Bàn giao

Chỉ cần xử lý phần session-gap R56-01 còn mở và regression liên quan; giữ CLOSED của bảy finding khác. Không yêu cầu dựng lại fixture tích hợp vừa đạt. Trình response/manifest mới, giữ nguyên báo cáo cũ, progress FIXES_READY chờ review. **Không tự APPROVED; chưa task57 hoặc rollout production.**

## 6. SHA256 bản đã kiểm tra

| File | SHA256 |
|---|---|
| `core/smc_context.py` | `CA8F421F32D4E43994AC59D0BC7611918C8FB69BC17D2F33505BD97F7DCC9DA1` |
| `core/smc_models.py` | `C8FBBD90AA10E7F99B61DE8DAEBB30B5019B9D3A9E98987EE27144C2D29045E5` |
| `tests/test_smc_gate56_review_regressions.py` | `0B9C3ACB4868F4FE155A319444FC716A75ED96237C8D9768CCEF47CDABE51145` |
| `tests/test_smc_fvg_session_task47.py` | `E82B1A96991DE4DF51B6A1961858275049393341EDCC76888867687E25B8E05F` |
| `tests/fixtures/smc_gate56_zone_pipeline.json` | `DFA9269D2071F30CED72869C5DD8FFCF0C018C3DF43863C0E58103C75E3F8207` |
| `docs/plans/smc-task-56-response-round3.md` | `65F00F8ED68ED292F4EA545A7CB8CFA1732E0D5DCA5E699E507100154BFA3E56` |
| `docs/plans/smc-task-56-review-round3.md` | `B5CBCC0897BADE3950C043EDC03821F9B611F8F790A5F282802DC8C822F6E00C` |
