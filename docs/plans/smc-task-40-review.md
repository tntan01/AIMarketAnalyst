# Tech Lead review — gate 40

**Quyết định: CHANGES_REQUESTED. Chưa được bắt đầu task 41.**

- Reviewer: Codex, Tech Lead do người dùng chỉ định.
- Ngày: 2026-09-10, Asia/Saigon.
- Phạm vi: chặng B task 17–39 theo kế hoạch; dữ liệu, typed models, pivots, BOS/CHoCH, history và snapshot/cache seams. Gate 16 vẫn APPROVED; findings dưới đây là implementation chưa đạt contract, không mở lại thiết kế đã duyệt.
- HEAD: `fb9ea527ee7ff0eb48c53875e24796260008e92c`; branch thực tế `main`.
- Có 4 tracked files thay đổi và các module/test/fixture mới chưa tracked. Review dựa trên working tree, không chỉ HEAD. Manifest đầu vào 37 file ở cuối báo cáo; digest `6D9F464F307064F3090067CE2A8C585A041FE0835271627FBD687DBB9C92029E`.
- Không sửa code, test, fixture, progress hay báo cáo cũ trong lượt review này.

## Kết quả kiểm thử

Command PowerShell đã chạy:

```powershell
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
```

**558 passed in 4.76s.** Đây là kết quả mới của lượt review. Lệnh ban đầu dùng wildcard trực tiếp `tests/test_smc*` không được pytest expand trên Windows nên không chạy test; đã sửa cách liệt kê như trên. `git diff --check` đạt, chỉ có cảnh báo LF/CRLF.

Test xanh nhưng **7 finding còn mở: 4 P1, 3 P2**. Các probe bổ sung dưới đây đã chạy trên code hiện tại và tái hiện lỗi. Chưa chạy toàn bộ repository test suite, UI, live broker hoặc dispatch giao dịch.

## R40-01 — [P1] Chưa có evaluator tái dựng structure theo thứ tự thời gian

**Vị trí:** `core/smc_context.py:2053`, `:2255`; đường ghép tại `:300`. **Task:** 28–31, 36–39.

BOS chỉ xét `eligible_candles[-1]`; initialization lấy hai high/low cuối ở cutoff. Không có owner replay toàn bộ lịch sử để giữ bootstrap đầu tiên, BOS/protected history và cập nhật continuation khi swing mới confirmed. State sau BOS chỉ cập nhật anchor/history, không chuyển tracked continuation sang swing mới.

Probe dùng helper `bullish_swings/candle` trong `tests/test_smc_bos.py`:

- BOS phá H1 tại close **08/01 12:00**; sau đó close 09/01 12:00 vẫn trên H1.
- Warm state giữ BOS 08/01. Cold call cùng hai candle, cutoff 09/01, không truyền state/history, phát BOS mới tại **09/01 12:00**, ID khác.
- Giữ state sau first BOS, cho H2=116 và L2=103 confirmed sau anchor, close 118: vẫn tracked H1, trả `SMC_BOS_ALREADY_EMITTED`, không phát continuation BOS H2.

Test `test_different_broken_level_remains_eligible_after_prior_bos` tại dòng 246 tự gán `tracked_continuation_id=H2`, che phần update chưa có. Task-37 test cũng chạy cả “batch” lẫn “prefix” qua cùng các phase với state truyền từ phase trước; chưa phải cold batch rebuild tại từng cutoff. Task-39 dùng stand-in chỉ trả hash/coverage/count, không kiểm state/event/protected thực.

**Yêu cầu sửa:** tạo một pure evaluator chặng B xử lý candle/pivot theo thời gian, bootstrap một lần, tự update continuation, phát event đúng close đầu tiên, giữ protected qua các swing không tạo BOS. Cold rebuild và incremental/restart phải dùng cùng semantics. Không cần production integration hoặc cache store ở gate này.

**Test để đóng:** BUY/SELL first BOS → candle tiếp diễn → swing mới → BOS thứ hai → CHoCH; cold batch từ đầu tại mỗi cutoff phải bằng incremental/restart về event ID/time, direction và protected/source IDs. Không gán cursor bằng tay trong acceptance test.

## R40-02 — [P1] CHoCH confirmation không được chặn đúng bởi reclaim/expiry

**Vị trí:** `core/smc_context.py:1659–1660`, `:1848–1868`, `:1931–1941`; wiring `:325–343`. **Task:** 32–37.

`confirm_choch_candidate` chỉ kiểm trạng thái expired đã được caller gán trước; không kiểm break close với `event.expires_at`, không xử lý reclaim trước reversal. `_smc_for_timeframe` gọi confirmation trước expiry và không gọi reclaim evaluator.

Các probe đã tái hiện từ fixture/helper hiện có:

1. Candidate bearish phá L1=100 ngày 10/01; close **101 ngày 11/01** đạt reclaim inclusive với buffer=1; sau đó close 95.9 phá L3 ngày 13/01. Truyền cả history cho confirm vẫn trả **true**, dù candidate phải bị invalidated trước đó.
2. Candidate expires **17/01 04:00**; chưa gọi expiry helper, đưa reversal close **18/01 12:00**: vẫn `choch_confirmed=True`, payload có confirmed_at sau expires_at.
3. Nếu đã ghi active candidate vào history bằng expiry pass trước confirmation, sau khi confirmed ngày 13/01, chạy expiry tại deadline candidate cũ đổi `candidate_status=confirmed → expired`, `choch_confirmed=True → False`, trong khi direction vẫn bearish và candidate_event là CHOCH_CONFIRMED. Candidate ID cũ chưa được đánh dấu terminal confirmed, nên expiry làm hỏng projection của reversal đã hoàn tất.

**Yêu cầu sửa:** khóa thứ tự transition trong evaluator: reclaim/timeout trước confirmation theo từng close; không phụ thuộc caller nhớ gọi helper. Candidate terminal confirmed phải giữ lịch sử xác nhận; expiry của trigger không được biến thành candidate chưa từng confirmed. Chặn confirm ngoài lifetime ngay tại seam có thể được gọi riêng, hoặc đóng seam bằng contract/evaluator bắt buộc.

**Test để đóng:** cả BUY/SELL reclaim rồi reversal; reversal tại/sau expiry; confirmed trước expiry rồi restart/tick vượt deadline; compare cold/incremental history và flags. Không chỉ test state đã được set expired sẵn.

## R40-03 — [P1] Đã thay đường SMC production trước mốc được phép

**Vị trí:** `core/smc_context.py:282–300`, `:301–344`. **Task:** giới hạn chặng B và gate 40.

`build_smc_context` vẫn được gọi ở `core/analysis_pipeline.py:542` và `core/scanner_live_producers.py:307`. Bản sửa thay swings bên trong `_smc_for_timeframe` bằng detector mới rồi truyền trực tiếp sang legacy BOS, liquidity, zone enrichment và confluence. Đây không chỉ là thêm pure seam.

Detector mới không giữ key legacy `time`; liquidity sweep hiện đọc `swing.get("time")` ở dòng 2699/2728. Probe so code HEAD với working tree trên cùng input qua `build_smc_context`: swing trước có time `2026-01-01T20:00:00+00:00`, bản mới trả `None`. Trong khi đó public builder không truyền buffer/ATR/tick cho structure mới, nên `structure_bos` trả `SMC_BREAK_BUFFER_UNAVAILABLE`. Output hiện bị trộn legacy và structure mới chưa hoàn chỉnh.

**Yêu cầu sửa:** giữ nguyên đường production/legacy trong chặng B; expose evaluator mới tách biệt để test. Nếu có shared refactor thì phải giữ schema/provenance và behavior tương đương của đường đang chạy, không bật detector mới vào producer. Không giải quyết bằng cách nối tiếp scorer/entry ở gate này. Làm trên nhánh làm việc như kế hoạch; không reset/ghi đè thay đổi người dùng.

**Test để đóng:** production public-builder regression so với baseline cho swings/source time và downstream payload; test evaluator mới độc lập. Cập nhật progress cho đúng phạm vi thực tế, không ghi “chưa runtime” khi public route đã dùng code mới.

## R40-04 — [P1] Filter swing dùng ATR cuối input nên dữ liệu tương lai đổi structure tại cutoff cũ

**Vị trí:** `core/smc_context.py:298–300`, `:2274–2286`. **Task:** 18, 23–28, 37.

Đường structure mới gọi `_filter_swings_by_atr(candles, swings)` trước khi lọc swings bằng as_of. Helper dùng ATR của **candle cuối toàn input**, không ATR causal của swing/event. Dù initialize loại swing confirmed sau cutoff, volatility sau cutoff vẫn có thể xóa swing cũ trước khi initialization.

Probe độc lập: 30 H4 candle O/C=100, H=101, L=99; hai high level 100 và 101 được giữ. Thêm một candle tương lai H=1000, L=1, O/C=100: cùng hai high cũ chỉ còn **1** sau filter. ATR-reference helper mới đúng hướng nhưng chưa được dùng trong đường cấu trúc này.

Đây là legacy helper có sẵn được tái dùng sai trong evaluator mới; không yêu cầu mở rộng sửa toàn bộ legacy quality.

**Yêu cầu sửa/test:** cutoff trước mọi detector/filter và dùng reference causal tại thời điểm đánh giá swing/event. Appending volatility hoặc malformed future record không được đổi kết quả tại cutoff cũ; chạy trên actual OHLC → pivot/filter → structure, không chỉ supplied swing dictionaries.

## R40-05 — [P2] Typed swing payload không được structure evaluator nhận

**Vị trí:** `core/smc_models.py:469–472`; `core/smc_context.py:666`, `:969`, `:1667`, `:2173`. **Task:** 21, 25–31.

`SmcSwing.to_dict()` xuất confirmed_at và usable, nhưng không xuất `confirmed`. Các evaluator lại yêu cầu `item.get("confirmed") is True`. Detector riêng trả một schema khác có field này.

Probe chuyển cùng H0/H1/L0/L1 confirmed thành `SmcSwing(...).to_dict()`, truyền vào initialize tại cutoff 08/01: **unknown**, thay vì bullish như dictionaries thủ công. Typed model/serializer không dùng được với consumer vừa triển khai, dù mỗi nhóm test riêng đều xanh.

**Yêu cầu sửa/test:** một canonical swing contract hoặc adapter tường minh giữa model và detector; suy ra usable theo confirmed_at/cutoff và provisional policy đúng thiết kế. Test detector → model/serialize/deserialize → initialize/BOS/protected phải giữ nguyên kết quả; không chèn flag bằng tay ở test.

## R40-06 — [P2] Snapshot validated vẫn chấp nhận ATR tương lai và interval sai timeframe

**Vị trí:** `core/smc_models.py:75–76`, `:118–121`, `:278–287`. **Task:** 17, 23–24.

Snapshot chỉ so last eligible close với as_of; atr_reference_time chỉ được kiểm format UTC. Frame interval chỉ kiểm dương, không kiểm mapping D1/H4/H1/M15.

Probe tạo snapshot as_of **01/01/2026 04:00** với ATR reference **01/01/2027**, bốn frame đều interval=14400: model nhận và giữ `data_quality.status=complete`. Các frame D1/H1/M15 vì vậy có interval sai mà vẫn được coi validated. Test complete-snapshot hiện cũng dùng helper mặc định 14400 cho mọi TF.

**Yêu cầu sửa/test:** chặn reference sau as_of/eligible causal bound, validate interval theo canonical timeframe; khi có event context phải giữ reference trước event candle như contract. Test reject future ATR và sai interval, cùng round-trip hợp lệ cho từng TF. Không tự đổi metadata đầu vào để “sửa” payload.

## R40-07 — [P2] Cache metadata collision giữa số và chuỗi

**Vị trí:** `core/smc_snapshot_cache.py:171–177`; test `tests/test_smc_snapshot_cache_task38.py:68–70`. **Task:** 38–39.

Numeric metadata được serialize thành string, còn string giữ nguyên. Vì vậy `metadata={"tick_size":0.0001}` và `metadata={"tick_size":"0.0001"}` có **cùng key** (probe trả True), trái fixture “metadata type changed → different”. Điều này có thể reuse result của input typed hợp lệ cho metadata sai kiểu.

Test hiện thay số thành string **"0.0001000"** đồng thời sửa point; nó pass nhờ spelling khác, không chứng minh phân biệt kiểu.

**Yêu cầu sửa/test:** canonical metadata bảo toàn type (hoặc validate/reject kiểu không hợp lệ trước hashing, không silently coerce). Kiểm 0.0001 vs "0.0001", 5 vs "5", nested metadata và order-only invariant; sửa đúng một field mỗi mutation.

## Điều kiện trình lại gate 40

- Sửa R40-01…07 trong chặng B; bổ sung regression chứng minh các probe lỗi thành PASS trên actual evaluator.
- Acceptance task 37/39 phải kiểm result structure thật, không chỉ phase-filter equivalence hoặc stand-in hash/count. Không yêu cầu cache store/producer integration trước lịch.
- Chạy lại command 558-test ở trên cùng tests mới, ghi command/count/failure thực tế; cập nhật progress, response gate 40 và manifest. Không đổi expected để hợp thức hóa behavior sai.
- Giữ gate 16 APPROVED và báo cáo cũ bất biến. Gate 40 hiện CHANGES_REQUESTED; không task 41, production rollout hoặc auto-entry.

## Manifest đầu vào review

SHA256 file uppercase + hai khoảng trắng + repo-relative slash path; sort path, join LF không newline cuối; SHA256 UTF-8 cho aggregate `6D9F464F307064F3090067CE2A8C585A041FE0835271627FBD687DBB9C92029E`. Bao gồm changed tracked files, untracked core/tests trong scope và sáu tài liệu đối chiếu. Các dependency tracked khác neo theo HEAD. Không bao gồm chính báo cáo này.

```text
9142B298173BF209B150421D2A38FA03CC58F9CF5A0DFC3C08ED3F0299507F54  core/market_models.py
65BFB8586609A22BAB79EF8035EEC1D068749D348EE8659C4BF1DF30806BE615  core/smc_context.py
5B3FD1F9665C339CE0F809AFA2DA9C707B80FF9D4C542CAB10C7D783A1436639  core/smc_history.py
2F87BB5E44545290CFE7D350FFDAD3325914DDF991D6C230FB66F12C4DD46053  core/smc_models.py
37BC53A84698323183EBFCDEF1D14F9AF0F5F86EA7010D60EF4D74EB40C57FC9  core/smc_snapshot_cache.py
C966D8307A28C8E61A20A1E93830E2778CABB5BBC01A4DBE42D47E56A0398682  docs/plans/smc-data-spec.md
088A567411443FB121D6D99C35D2CDDA91AEDF2FD10F3AC5006AC836A6782125  docs/plans/smc-implementation-plan.md
AF2F2FD957DC097A4B3A2FB79F8E04B5DAFC5FDF940EA0BB772F47374F9A2F39  docs/plans/smc-implementation-progress.md
C4A3C1C7785010E3DD6E82D3312C61689D0D3A0D3B9218415EA53E1826A11FC1  docs/plans/smc-parameter-table.md
FCFED4E61B0D4C1C831469953179D7363BA285D77C62028EF7B17A7731D7EBA2  docs/plans/smc-scoring-upgrade-plan.md
20C66269A3D4C1D827E070DA4FEB8D87A631D0729189EF5E98ACCB6DF99AA27C  docs/plans/smc-structure-spec.md
6D9BF9B5E36228EF13985C29CF6885A447C700E927A2D62728763B4B38F07261  tests/fixtures/smc_d1_proximity_only.json
7F334CF3BFB9EC39A4114A8AD18CBD522F54A6B53898786A70B26BA1951A477D  tests/fixtures/smc_data_boundaries.json
1253E04657D1A90E0DC6447202B5B3B87D41988755E7E66DBE39ABC18F3B23ED  tests/fixtures/smc_m15_stale_rejection.json
1C556136F1B1AEF48230233654CB119B6C9F7870D6626289A839DFA94955DA17  tests/fixtures/smc_protected_swing_differs_from_latest.json
EC4B8B8D7AB8C4E83869B24D5955ABA9E724D1AB287BFE132EAC5B4B9FA9894B  tests/fixtures/smc_snapshot_cache_task38.json
BDD0E9B66B638C5F30EEF0C4BF8CECFCBCB4CEA16D6B9C54F0E818B6FB136367  tests/fixtures/smc_snapshot_cache_task39.json
03C10FEF6E4C3C873FC6F265292C92BC457269CFD04EE9A3801A5ADAE1A846C3  tests/fixtures/smc_structure_task36.json
AADEA22AA43568DDC0EFE0F431747C6955CF5A405DD5012656C2A52696D2BACD  tests/fixtures/smc_structure_task37.json
2EDB5EB07804B5B746F644152A1EE51026518DDA182C7D4000BAEE03058C249A  tests/test_smc_atr_reference.py
3C7BDDAAEFD63398B720FFDD17AF41B7E2DA3F727372ED7F8F307A8D67C493DD  tests/test_smc_bos.py
188AEF98E3D9F13F24F4E1487D90E34D1ADBEF68231C642940A85491FB7496D9  tests/test_smc_context.py
0D0A294E0B4A67CFD91C64FEEF00EE1AED372475E412E4CDE6875F8F17FBCA91  tests/test_smc_data_boundaries.py
E5A9BA0CE7D393FCB673D298B079278A0C87E2637DC4617DD4E17C5B17AA02BB  tests/test_smc_data_cutoff.py
F1F5F635C97F49C60C35C5064D60BC20BEA362A9ECCAF051D0290ED045B21DB5  tests/test_smc_data_validation.py
6A61596B9B5FB3FFD1C782F248FE12DF056FA4F81995CB27770405652C7C7C1E  tests/test_smc_external_pivots.py
F2348231F6D256123A8D535E3958EDD1B00EB0983E36EB2283E14A2792081F73  tests/test_smc_history.py
92222F251A088E29B731E28F1DADF00FC3C519FCE8FB4E7CA55595C1BC3312E2  tests/test_smc_internal_pivots.py
39C0275D349C21B45AE998464832CF090D91C41131A3E6412911F11A3A86B5CC  tests/test_smc_snapshot_cache_task38.py
0B1B469D1143E0531DF1A5291A02DE95721527ADF4C0F88714CF72852F0CA0AD  tests/test_smc_snapshot_cache_task39.py
9F6D4DBFB4B0979115822B5B50E18D466CF7AECD6DE18C5AC04ED6F1F06B9443  tests/test_smc_snapshot_models.py
B963F576C453D271BAEB9A0303AEE63D8FE7DC3B6C54DF6BE96E4EFA506F6E18  tests/test_smc_structure_event_models.py
B846D9EDEDEC9B003EF5E0DF46D033F5429E489C5C31493493290B100F0DBBCF  tests/test_smc_structure_state.py
1D6FC0B3CF8446EDD1D789E790A0229ED4DF95AFD903B5BEF9A3AA936BEA9B8D  tests/test_smc_structure_task36.py
6A9CDBB27A8E942C26E1F27A516F47329D0FDAAF7A009301A4F52A77F0E74469  tests/test_smc_structure_task37.py
1FDA6F3B8D53AE418E80BDA2753F0940B33B1C76389123282092A61E6CF15A8D  tests/test_smc_swing_models.py
0A85E9F770CB453C8D46D5A7B55C503ACBECD957694EC70A5B84307A79589A70  tests/test_smc_swing_ordering.py
```

