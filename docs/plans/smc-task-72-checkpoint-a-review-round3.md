# Gate72 — Checkpoint A, review lần 3

**CHANGES_REQUESTED. Chỉ sửa các mục F01 dưới đây; chưa F02, chưa task73.**

Tech Lead, 2026-09-11 (Asia/Saigon). Review bản trình A3-090 tại [fix-progress §A3.93](smc-task-72-fix-progress.md#a393--bản-trình-a-lần3-ghép-trong-hồ-sơ-hiện-có-a3-090). Đây là quyết định hiện hành; review A lần1/lần2 và báo cáo Coder giữ làm lịch sử. A-D01…07 và interface đã chốt ở lần2 tiếp tục áp dụng, với các làm rõ tại §3 bên dưới.

90/90 mã đã được Coder báo IMPLEMENTED, nhưng chưa đồng nghĩa checkpoint A PASS. Review xác nhận tiến bộ và kết quả chạy; còn **5 nhóm lỗi oracle/coverage**, không yêu cầu làm lại 90 mã. Các lỗi core chưa sửa được phép RED tại A. Không đóng R72-01…09 và không phê duyệt runtime/auto-entry.

## 1. Evidence và phần giữ nguyên

| Kiểm tra reviewer | Kết quả |
|---|---|
| Acceptance collection | 116 node, không lỗi collection |
| Acceptance execution | 65 failed, 51 passed |
| Task57–71 | 108 passed |
| Retained SMC + 6 integration files, loại đúng file acceptance | 854 passed in 9.01s |
| Full SMC + 6 integration files, gồm acceptance | 65 failed, 905 passed in 10.06s; tổng 970 node |
| Protected reviewer probes | 13 failed, 3 passed |
| Targeted 5 node cho A3-071/067/066/061 | 1 failed, 4 passed; A3-061 dừng tại status `confirmed != invalid` |
| 11 fingerprint F00 (5 core + probe + 5 R56 artifacts) | Khớp toàn bộ bảng §A3.3 trong fix-progress |

Toàn bộ 65 failure trong full suite thuộc file acceptance; không có failure ngoài file đó. **Không suy ra mọi oracle đều đúng từ kết quả này**: A3-061/A3-043 có cả gap core lẫn vấn đề test; bốn node targeted đang GREEN cũng có lỗi oracle/thiếu assertions như §2.

Snapshot đã review:

```text
HEAD fb9ea527ee7ff0eb48c53875e24796260008e92c
tests/test_smc_gate72_fix_acceptance.py
  E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD
docs/plans/smc-task-72-acceptance-matrix.md (bản trình, trước reviewer ghi đính chính)
  AD6B0081EEB3C1A9EFCA14EED3649B97E93AA5040C35E476C490AB2311FC7828
docs/plans/probes/test_smc_gate72_review.py
  5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6
```

Giữ F00 PASS, năm fixture fixes đã đạt, actual factory validation, chuỗi confirmed D1 detector→enrich→typed→D1 và các coverage không bị nêu dưới đây. A3-076 history-only vẫn là test hợp lệ với EXPECTED_IMPLEMENTATION_RED/F10; không hồi tố thành lỗi vì helper control không mang pool lineage.

Reviewer không sửa core/tests/probe/golden, không stage/reset/commit. Worktree đầu review có 135 entry dirty có trước; thay đổi lượt review chỉ là báo cáo này và trạng thái trong bốn tài liệu fix-plan/fix-progress/matrix/progress tổng.

## 2. Các mục phải sửa trước khi trình lại A

Số dòng dưới đây thuộc hash acceptance ở §1; tìm theo tên hàm khi file thay đổi. Mọi finding đều thuộc yêu cầu F01 đã có, không thêm tính năng.

### A3R3-01 [P1] — A3-071: fixture context không thực sự ngoài khoảng cách

**Vị trí:** [test:376](../../tests/test_smc_gate72_fix_acceptance.py#L376), `test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep`; helper bảo vệ `probes/test_smc_gate72_review.py:70`.

Vế link trực tiếp dùng ATR=1 nên gap `105.26 - 105 = 0.26` ngoài tolerance `0.25 ATR`. Nhưng `_probe.attach` cấp 20 candle `(120,121,119,120)` và context dùng `_latest_atr`: ATR thực là **2**. Zone được gọi là outside chỉ cách **0.13 ATR**, vẫn eligible. Diagnostic reviewer cho zone này chạy riêng qua cùng caller trả `liquidity_sweep_linked=True`, owner `outside-early`. Test ghép hiện GREEN nhờ core ưu tiên khoảng cách gần, chính là hành vi F08 phải sửa; expected này sẽ cản implementation đúng chọn owner sớm nhất trong các claim hợp lệ.

**Sửa nhỏ:** giữ ba boundary controls ở helper; dùng fixture context có ATR xác định đúng (đổi geometry hoặc local candle input, không sửa protected probe). Assert ATR/khoảng cách và eligibility của từng zone riêng qua chính caller trước khi ghép hai thứ tự. Zone ngoài phải không link khi đứng một mình; zone trong/đúng biên phải đạt theo cùng nguồn ATR. Sau đó mới assert outside không lấy ownership dù available sớm hơn. Đồng bộ dòng A3-071 trong matrix/ledger.

### A3R3-02 [P1] — A3-067: ngưỡng thiếu metadata bị khóa thành 0

**Vị trí:** [test:3526](../../tests/test_smc_gate72_fix_acceptance.py#L3526), `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule`; docstring3502 và matrix dòng405/923 bản trình.

Test chỉ truyền `zone_tolerance=0.5`, không tick/ATR, rồi assert `invalidation_buffer == 0.0` và gọi đây là fail-closed. Trái F02, review lần2 F01.1 và chính matrix interface metadata: rule không tính được phải **None + metadata unknown/reason**, không phải0. Reviewer kiểm biến thể close99.93: cùng thiếu metadata, buffer0 khiến core đánh dấu broken=True; đây là lỗi đã biết, không phải oracle được duyệt.

**Sửa nhỏ:** giữ controls đủ metadata chứng minh từng override chỉ đổi đúng rule. Với rule còn thiếu nguồn, khóa None/unknown/unusable qua canonical path theo interface đã có. Không thêm tham số override mới. Nếu giữ một helper case làm legacy compatibility control thì ghi rõ phạm vi legacy và không tính nó là coverage canonical; canonical control vẫn phải khóa unknown/None. Sửa mô tả “fail-closed0.0” trong matrix/plan; RED do F02 được phép giữ.

### A3R3-03 [P2] — A3-061: positive control dùng snapshot tương lai

**Vị trí:** [test:3286](../../tests/test_smc_gate72_fix_acceptance.py#L3286), `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer`.

Test enrich toàn chuỗi đã invalidated, sau đó chỉ lùi `as_of` trên **cùng terminal payload** để đòi D1 valid=True. Diagnostic: snapshot invalidated/last close là **2026-02-14**, `lifecycle_broken=True`, nhưng cutoff control là **2026-02-12**. Đây không phải prefix snapshot hợp lệ theo data spec §1. A3-062 đã loại cùng cách làm ở fix-progress §A3.65 và dùng A3-060 làm control. Việc control hiện GREEN không chứng minh nó hợp lệ sau khi F03/F05 tôn trọng terminal canonical.

**Sửa nhỏ:** reuse positive A3-060 cùng source/zone, hoặc enrich riêng prefix chỉ tới reaction close rồi typed round-trip và gọi consumer. Assert prefix chưa terminal, identity/history khớp với bản append. Bản terminal tiếp tục kiểm invalid/unusable và D1 false/0 ở đúng close. Không yêu cầu consumer hồi dựng snapshot quá khứ từ terminal payload. Giữ core RED F03/F05 nếu còn.

### A3R3-04 [P2] — A3-066: GREEN chưa chứng minh canonical pool identity

**Vị trí:** [test:1067](../../tests/test_smc_gate72_fix_acceptance.py#L1067) và1112, `test_r72_01_pool_sweep_evidence_survives_future_bars` / `test_r72_01_pool_sweep_identity_survives_rolling_index`; matrix dòng876 bản trình.

Hai node chỉ kiểm numeric pool levels, swing ID và `source_pool_id` của sweep; không đọc/đối chiếu `records.pool_id/source_ids/sources/usable_at`. Diagnostic chạy actual producer cho thấy **không có `records`** và `source_pool_id` chỉ bằng swing ID. Vì vậy equality hiện tại có ý nghĩa cho swing/legacy evidence nhưng chưa chứng minh canonical pool→sweep như A3-066/F01.4 yêu cầu. Chưa có biến thể permutation nguồn pool. Matrix còn hoãn assertions canonical tới F06 dù A phải chuẩn bị expected trước core fix.

Ngoài ra, lọc ở dòng1101/1106 dùng `sweep["time"]` (open) thay vì `reclaimed_at` (close); không được tính event chỉ mới mở ở cutoff là evidence đã biết.

**Sửa nhỏ:** bổ sung vào các node hiện có assertions record tồn tại/không rỗng, đúng source/time từ fixture, nối ID/lineage sang sweep, so cùng causal pool qua prefix/batch/rolling; permutation cùng nguồn giữ identity/usable time. So các record liên quan, không đòi toàn bộ batch giống prefix khi thực sự có nguồn mới. Lọc theo reclaim close và assert close<=cutoff. Reuse helper/actual producer A3-044; thiếu records có thể RED F06, không cần sửa core để làm xanh.

### A3R3-05 [P2] — A3-043 và temporal controls: reject nhầm phạm vi pool

**Vị trí:** [test:1362](../../tests/test_smc_gate72_fix_acceptance.py#L1362), `test_r72_01_equal_pool_usable_time_is_max_of_both_sources`; hai controls `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` (1233–1236, A3-039/041) và `test_r72_01_equal_pool_usable_before_sweep_close_is_accepted` (1286–1291, A3-040).

A3-043 muốn reject **equal pool** chưa đủ hai source, nhưng assert toàn bộ `swept_lows == []`. Fixture còn có single-source pool của source-a: usable01:00, sweep close02:00, level100, low99.5, close100.3 — hoàn toàn đạt temporal/excursion/reclaim; source-b/equal pool chỉ usable03:00. Diagnostic riêng source-a xác nhận event index1, level100, reclaim02:00. Thiếu source cho equal pool không làm pool đơn hợp lệ mất eligibility.

Hai positive controls cũng bắt toàn bộ list có đúng một event và event đầu là equal mean dù geometry cho phép sweep pool đơn. Điều này vô tình khóa priority/cardinality hiện tại của detector trong test chỉ nhằm kiểm thời gian; chưa có quyết định buộc “equal luôn thắng/chỉ một event”.

**Sửa nhỏ:** cô lập canonical equal record đang kiểm trong synthetic temporal seam, hoặc lọc/assert theo đúng pool lineage. Negative chỉ chặn equal pool chưa usable; giữ control riêng cho single-source hợp lệ. Positive khóa equal record/time/mean tương ứng, không phụ thuộc list position. **Không** thêm quy tắc phát nhiều event, dedupe hay pool priority ở lượt này. Reuse ba node, đồng bộ A3-039/040/041/043 cùng một lần sửa.

## 3. Chốt các câu hỏi mở của bản trình

Các lựa chọn này hoàn thiện interface đã đề xuất; không tạo service, mode giao dịch hoặc business formula mới.

| Câu hỏi §A3.93 | Quyết định TL |
|---|---|
| Pool record kind | Chấp nhận `swing_low`, `swing_high`, `equal_low`, `equal_high`. |
| Single-source record | Có canonical record cho swing pool một source; dùng cùng quy tắc causal/provenance. Không đồng nghĩa mọi pool cùng candle bắt buộc phát event. |
| Equal level | Giữ trung bình cặp nguồn như numeric projection; source IDs/records xác định lineage, không truy ngược nguồn bằng mean price. Không thay thuật toán gom nhóm ở A. |
| Metadata reason names | Chấp nhận `SMC_METADATA_ATR_UNAVAILABLE`, `SMC_METADATA_TICK_UNAVAILABLE`, `SMC_METADATA_NONFINITE`, `SMC_METADATA_SOURCE_CONFLICT` cho bốn nhóm tương ứng. Assertions “reason không rỗng” đã được cho phép ở A được giữ; khi sửa F02 dùng tên đã chốt. Không mở thêm task chỉ để thay chuỗi ở mọi test. |
| Claim không có pool/source lineage | Canonical pool→sweep→ownership không được coi thiếu lineage là legacy, tự tạo nguồn hay cấp lại owner. Giữ fail-closed với reason rõ cho nhóm provenance; không đổi helper compatibility default. Boundary canonical/legacy phải tường minh ở caller/adapter như A3-008. Các helper controls cũ không tuyên bố canonical provenance (ví dụ A3-076) được giữ; không yêu cầu đổi hàng loạt chỉ để thêm fields. Không khóa thêm chuỗi reason mới trong review này. |
| Validator chạy bản sao rows | Node `...corrected_task57_71_positive_fixtures_are_valid` kiểm samples được copy, không tự chứng minh toàn bộ rows thật. Tuy nhiên actual factories task59/60/62/63/65 đều gọi validator và 108 task tests đã chạy trực tiếp chúng: chấp nhận evidence này, chỉ sửa mô tả/mapping. Không duplicate node/refactor factories. |
| SELL touch không mirror tuyệt đối | Không blocking: exit/reaction đã mirror đúng yêu cầu A3-026; touch vẫn overlap/chưa invalid và timeline BUY/SELL được kiểm. Không ép đổi touch chỉ vì khác số học BUY. |

## 4. Đồng bộ hồ sơ và lượt giao tiếp theo

Matrix bản trình có đầy đủ tên 116 node nhưng khoảng80 hàng tracking còn trống Actual/Loại RED; phần mở đầu tracking ghi83 node và chờ A3-083/084, summary §4 vẫn13 đủ/6 một phần/2 thiếu, dù tasks tương ứng đã thực hiện. Fix-progress §A3.87 chứa ledger chi tiết hơn. Đây là **lệch đồng bộ A3-081/A3-090**, không phải80 yêu cầu test mới. Header các tài liệu đã được reviewer sửa; Coder cập nhật nội dung hàng còn stale sau khi sửa tests, không tạo một progress file khác.

Lượt sửa được giới hạn theo thứ tự sau (mỗi hàng có thể giao riêng):

| Việc | Mã đã có | Điều kiện xong |
|---|---|---|
| Sửa context distance preconditions | A3-071 | Từng zone đúng eligibility với ATR thật; pair/permutation không dựa lỗi nearest-rank. |
| Sửa missing-metadata override oracle | A3-067 | Không còn gọi zero thiếu nguồn là canonical fail-closed; controls override hợp lệ được giữ. |
| Thay positive control terminal | A3-061 | Prefix thật/reuse A3-060, không rewind terminal snapshot. |
| Bổ sung canonical pool parity | A3-066 | Record/source/time→sweep được assert; permutation/rolling/cutoff đúng. |
| Cô lập equal-pool temporal seam | A3-043; đồng bộ A3-039/040/041 | Không reject pool đơn hợp lệ; không khóa priority/cardinality ngoài scope. |
| Đồng bộ và trình lại một lần | A3-081…090 | Case mapping/actual/classification, commands/hashes đúng bản mới; bản trình A lần4 trong fix-progress. |

Chỉ **8 mã test** nêu trên mở lại; các mã khác giữ lịch sử IMPLEMENTED. A3-081…089 refresh evidence theo bản mới, không làm lại các sửa đổi đã đạt; A3-090 hiện CHANGES_REQUESTED. Không lập dải90 task mới, không review riêng từng mã. Những điểm mới được TL làm rõ ở §3 không tự biến mọi test helper cũ thành defect.

Khi trình lại, chạy đúng nhóm bắt buộc bên dưới; ghi actual thay vì giữ mục tiêu số pass. Ghi riêng **implementation RED** và **test defect đã sửa/còn mở**. Không skip/xfail/xóa test, không sửa protected artifacts hoặc core. **Chỉ khi A được TL PASS mới giao F02.**

```powershell
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=short
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=short
$gate72Tests = @(rg --files tests -g '*task5[7-9].py' -g '*task6[0-9].py' -g '*task7[01].py')
python -m pytest @gate72Tests -q --tb=short
$retainedSmcTests = @(rg --files tests -g 'test_smc*.py' | Where-Object { $_ -notmatch 'test_smc_gate72_fix_acceptance.py$' })
python -m pytest @retainedSmcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q --tb=short
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q --tb=short
git diff --check
```

**Kết luận:** F01 tiến bộ rõ, nhưng expected/coverage chưa đủ chắc để làm chuẩn sửa core. Đóng đúng5 nhóm trên và cập nhật hồ sơ là bước tiếp theo; không mở rộng kế hoạch144 bước.
