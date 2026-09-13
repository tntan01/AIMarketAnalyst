# Task 16 — Tech Lead review response

Ngày lập: 2026-09-10  
Trạng thái: **APPROVED** theo [Tech Lead review lần 5](D:/Projects/AIMarketAnalyst/docs/plans/smc-task-16-review-round5.md), ngày 2026-09-10 18:29 Asia/Saigon; R16-01 đến R16-09 đều CLOSED ở mức đặc tả.  
Quyền tiếp tục: task **17–39** trên nhánh làm việc; **dừng review tại task 40**, không làm task 41 trước khi gate 40 được APPROVED. Chưa phê duyệt runtime/production/auto-entry.  
Phạm vi cập nhật hiện tại: đồng bộ trạng thái trong response và progress; không sửa báo cáo review, runtime hoặc fixture, không triển khai task 17 và không gửi lệnh giao dịch.

## 1. Nguyên tắc xử lý

- `expected_current_behavior` trong fixture và bằng chứng baseline được giữ nguyên để chứng minh lỗi nền; chỉ `expected_after_fix` và contract tài liệu được sửa.
- M15 là entry visit/confirmation. M15 không phải quality input và không được tạo penalty/quality downgrade trong contract mới.
- Các mục đổi owner hoặc đổi semantics planner đã được chấp nhận ở mức đặc tả qua gate 16; chưa được xem là runtime behavior đã triển khai hoặc nghiệm thu.
- Các kiểm tra trong response này chỉ là kiểm tra tài liệu/fixture và probe đã có từ baseline. Runtime regression, PIT thật, parity Analyze/Scanner, UI, restart/cache và execution dry-run vẫn là kiểm tra tương lai sau khi được duyệt và triển khai đúng task.

Review lần 4 giữ 8 finding CLOSED và yêu cầu sửa phần partial cuối của R16-08. Sau khi sửa, review lần 5 xác nhận bốn case OHLC BUY/SELL đạt expected và manifest 14/14 file khớp, đóng R16-08 và ghi **APPROVED** cho gate 16. Đây là cập nhật theo quyết định Tech Lead, không phải coder tự phê duyệt.

## 2. Lịch sử response từng finding trước phê duyệt

Các đoạn “Chờ Tech Lead duyệt” dưới đây được giữ làm lịch sử nội dung đã trình, không biểu thị yêu cầu duyệt còn mở. Review lần 5 cùng các quyết định thành phần trước đó đã đóng R16-01 đến R16-09 ở mức đặc tả; trạng thái hiện tại nằm ở đầu tài liệu và §6.

### R16-01 — continuation/protected swing và CHoCH causal

**Thay đổi.** `smc-structure-spec.md` tách `bootstrap_ready_at` khỏi `source_history_anchor_at`. Bootstrap phải có H0/L0/H1/L1 confirmed và quan hệ HH/HL hoặc LH/LL; `bootstrap_ready_at=max(confirmed_at(H1),confirmed_at(L1))` chỉ mở gate đánh giá first BOS, không phải điểm bắt đầu source interval và không backdate event. Với bullish BOS, source interval dùng `pivot_time > source_history_anchor_at/anchor_start_at`, `< break_candle_close`, `confirmed_at <= break_candle_close`; vì vậy pullback L1 có pivot trước ready nhưng confirmed trước break vẫn được chọn. Sau BOS, anchor chuyển về break close. Cursor lưu tracked continuation, protected swing, source BOS và candidate IDs. Reversal candidate có state cục bộ: break protected → LH/HL confirmed sau break → continuation pivot → reversal BOS mới; reclaim/expiry hủy candidate, trend cũ giữ nguyên. Boundary break/reclaim đã thống nhất và timeline BUY/SELL có timestamp/pivot/confirmed_at/source IDs.

**File/vị trí.** `docs/plans/smc-structure-spec.md` §10; `docs/plans/smc-parameter-table.md` P2; `tests/fixtures/smc_protected_swing_differs_from_latest.json` giữ baseline và expected candidate.

**Bằng chứng kiểm tra.** Đã đọc detector structure hiện tại và chạy probe baseline trong task 5: fixture trả `structure=mixed`, `bos=false`, `choch=false`, `choch_confirmed=false`; đây là lỗi nền, không được biến thành assertion chuẩn. Fixture mới ghi rõ H0/L0/H1/L1 với pivot/confirmed, `source_history_anchor_at=H0.pivot_time`, `bootstrap_ready_at=2026-01-05T00:00:00Z`, và break thực tại 12:00; source filter có `L0,L1`, chọn L1 theo pivot muộn nhất. Timeline tiếp diễn có pullback sau tracked high và SELL mirror. JSON fixture parse hợp lệ trong command ở §3.

**Chờ Tech Lead duyệt.** Duyệt việc tách ready gate khỏi source-history anchor, chọn source muộn nhất theo `pivot_time` (tie theo extreme price rồi stable ID), break strict/reclaim inclusive, fallback width-2 chỉ ở `unknown/watch`, và precedence khi một candle đồng thời phá continuation/protected. Đây là thay đổi semantics, chưa runtime.

### R16-02 — lifecycle H4/H1 và M15 entry visit

**Thay đổi.** `smc-lifecycle-spec.md` §11 và readiness §10 tách parent lifecycle H4/H1 khỏi M15 entry visit. Parent owns formation/exit/reaction/invalidation/expiry và B/Q/L/C; M15 có `entry_visit_id`, `parent_zone_id`, nullable `parent_lifecycle_visit_id`, anchor M15 đầu tiên overlap sau `available_at`, follow-through `delta=1..3`, trigger sống tới `delta=12` và hết hạn ở `delta=13`. Confirmation ID không chứa parent ID, nên M15 touch 08:15/confirm 08:45 khi H4 08:00–12:00 chưa đóng vẫn hợp lệ; parent link bổ sung sau không đổi trigger ID. Invariant được sửa theo từng canonical candidate: thay chuỗi M15 không đổi B/Q/L/C, quality hoặc parent lifecycle của candidate; selected ID/final raw có thể đổi nếu confirmation rank đổi. Matrix phân biệt parent open, M15 expiry và plan đã tính.

**File/vị trí.** `docs/plans/smc-lifecycle-spec.md` §11; `docs/plans/smc-readiness-spec.md` §10; `docs/plans/smc-compatibility-spec.md` §4; `docs/plans/smc-implementation-progress.md` task 10/12.

**Bằng chứng kiểm tra.** Đối chiếu với lifecycle hiện tại: zone stale D1/H4/H1/M15 là `20/30/50/80`, trigger M15 là 12; tài liệu đã ghi riêng hai lifetime và ID lineage. Chưa chạy runtime test cho contract mới.

**Chờ Tech Lead duyệt.** Xác nhận nullable parent link/projection sau H4 close và precedence nếu parent exit cùng lúc M15 confirmation. Invariant độc lập M15 áp dụng cho quality/lifecycle của cùng candidate; selected ID có thể đổi nếu confirmation rank đổi.

### R16-03 — loại M15 penalty/quality downgrade

**Thay đổi.** Bỏ penalty khỏi parameter P10 và expected-after-fix của stale fixture; `penalty=0`, `quality_unchanged=true`, `smc_quality_delta=0`, readiness `WAITING_CONFIRMATION`, reason `M15_NO_CONFIRMATION`. Readiness/compatibility/BQLC/acceptance/progress đều ghi rõ M15 chỉ đổi confirmation/readiness, không đổi B/Q/L/C hoặc quality. Legacy penalty chỉ được đọc để audit lịch sử.

**File/vị trí.** `docs/plans/smc-parameter-table.md` P1/P10; `tests/fixtures/smc_m15_stale_rejection.json` `expected_after_fix` và `rejection_contract`; `docs/plans/smc-bqlc-spec.md` §7/§9; `docs/plans/smc-readiness-spec.md` §10; `docs/plans/smc-compatibility-spec.md` §4; `docs/plans/smc-acceptance-dossier.md` §2; `docs/plans/smc-implementation-progress.md` task 4/12/16.

**Bằng chứng kiểm tra.** Baseline fixture vẫn giữ nguyên: 48 candle, current evaluator `confirmed=true`, `reaction=true`, `penalty=0`; expected-after-fix nay không xác nhận và không phạt quality. Không chạy runtime regression sau khi sửa hồ sơ.

**Chờ Tech Lead duyệt.** Xác nhận schema current có giữ field penalty legacy ở dạng audit-only hay loại khỏi current payload hoàn toàn; cả hai lựa chọn đều không được phép tác động S hoặc quality.

### R16-04 — age, dwell, reclaim và consumed

**Thay đổi.** Đồng bộ bảng tham số và B/Q/L/C về một công thức; sweep consumed dùng exclusive owner theo thời điểm:

```text
dwell_score(d) = clamp(1 - d/5, 0, 1)
age_score(a,L) = max(0.25, 1 - 0.75*a/L) nếu 0 <= a <= L, ngược lại 0 sau expiry
reclaim_quality(r) = 1.00 nếu r=1, 0 nếu r>=2 hoặc không reclaim
claim_eligible_at = max(sweep_reclaim_at, setup_available_at)
owner(S) = claim sớm nhất; stable_setup_id chỉ tie khi cùng claim_eligible_at
```

Expected biên đã ghi: dwell `0/1/5/6 = 1/.8/0/0`; H4 age `3/4/8/9/30/31 = .925/.900/.800/.775/.250/0`; D1 age `3/4/8/9/20/21 = .8875/.850/.700/.6625/.250/0`; reclaim `1/2/3/4 = 1/0/0/0`. Assignment có `owner_setup_id`, `assignment_id`, `assigned_at`; child cùng owner không nhân L, setup khác không tái dùng, setup đến muộn không rút owner. Prefix thiếu owner history trả `SWEEP_OWNER_HISTORY_INCOMPLETE`.

**File/vị trí.** `docs/plans/smc-parameter-table.md` P7/P8 và §R16; `docs/plans/smc-bqlc-spec.md` §5/§9; `docs/plans/smc-lifecycle-spec.md` §5/§8; `docs/plans/smc-implementation-progress.md` task 8/10.

**Bằng chứng kiểm tra.** Đã tính tay lại các giá trị trên và ví dụ geometry trong BQLC; chưa chạy scorer runtime vì user giới hạn task này ở hồ sơ/fixture.

**Chờ Tech Lead duyệt.** Xác nhận age bắt đầu tại `available_at`, reclaim tính từ candle sweep đầu tiên và exclusive owner theo claim time thay cho linker one-to-one hiện tại. Đây là contract chờ duyệt.

### R16-05 — parity Analyze/Scanner planner

**Thay đổi.** `smc-selection-spec.md` §12 đối chiếu thực tế và ghi rõ policy đề xuất: shared planner nhận canonical zone/refinement; dùng cùng entry refinement; dùng đúng thứ tự SL swing → distal original zone → risk ATR fallback của `risk_engine`, cùng min-stop/SL-floor; dùng cùng TP cascade equal-level → nearest target zone → Fib khi không range → swing; execution ATR là `first_finite_positive(technical.atr_h4, technical.atr_d1)` từ frozen snapshot và ghi reason nếu fallback; shared SMC width/distance gate là width `<=1*formation_atr`, distance `<=3*execution_atr`; RR pre-spread là `abs(TP-entry)/abs(entry-SL)`. Ví dụ H1 zone formation ATR `.80`, width `.60`, H4 execution ATR `2.00`, distance `4.00` phải pass (`4<=6`) ở cả hai route; current H1 ATR không được thay execution ATR. Analyze `core/risk_engine.py:build_trade_plan` là implementation source được adapter hóa; Scanner `core/scanner_scenario_producers.py:produce_scenario_plans` bỏ công thức SL 1 ATR riêng khi policy được duyệt. Cache evaluation và plan tách; plan key không dùng route identity.

**File/vị trí.** `docs/plans/smc-selection-spec.md` §5/§12; `docs/plans/smc-acceptance-dossier.md` §2/§3; `docs/plans/smc-implementation-progress.md` task 13/16.

**Bằng chứng kiểm tra.** Đã đọc các nhánh thực tế trong `core/risk_engine.py` và `core/scanner_scenario_producers.py`; đây là bằng chứng tài liệu/source inspection, không phải runtime parity. Không sửa hai file runtime.

**Chờ Tech Lead duyệt.** Duyệt mapping trên và tác động Analyze/Scanner: Scanner bỏ SL 1 ATR riêng, Analyze chia sẻ cùng planner nhưng giữ risk policy hiện hữu qua adapter; xác nhận `atr_h4→atr_d1` fallback, TP cascade, shared width/distance gate và technical fallback chỉ khi `NO_ZONE` + core đủ + caller explicit allow. Không tự đổi runtime/risk policy.

### R16-06 — rejection M15

**Thay đổi.** Parameter và fixture ghi phương trình chính xác, theo directional wick đã được Tech Lead xác nhận:

```text
range = high - low
body = abs(close - open)
BUY wick = min(open, close) - low
SELL wick = high - max(open, close)
directional_wick >= max(0.80*body, 0.25*range)
```

Phải thêm `range>0`, close đúng màu và rejection/follow-through thuộc current entry visit/window 3 bar. Equal threshold đạt, dưới threshold không đạt, doji/range zero reject; BUY/SELL mirror. Không gọi `body/range >= .80` là contract. Bảng OHLC trong parameter có BUY/SELL bằng ngưỡng và dưới ngưỡng, cùng expected stale ngoài visit.

**File/vị trí.** `docs/plans/smc-parameter-table.md` P10 và §R16; `tests/fixtures/smc_m15_stale_rejection.json` `rejection_contract`; `docs/plans/smc-acceptance-dossier.md` §2.

**Bằng chứng kiểm tra.** Source inspection đã đối chiếu `core/smc_m15_confirmation.py` hiện dùng lower wick cho BUY, upper wick cho SELL, `max(.80*body,.25*range)` và close color. Probe baseline O=100, C=100.4, H=100.5, L=99.4 có BUY lower wick `.6`, threshold `.32`, nên runtime `rejection=true`; công thức cũ upper wick `.1` cho kết quả false. SELL mirror O=100, C=99.6, H=100.6, L=99.5 có upper wick `.6`, threshold `.32`, runtime true; công thức cũ lower wick `.1` false. Hai case này được tính độc lập từ OHLC.

**Quyết định đã áp dụng.** Giữ directional wick đúng runtime hiện tại; không proposal đảo wick. Chỉ còn runtime regression của detector/visit sau khi được phép triển khai, còn hồ sơ không sửa runtime.

### R16-07 — D1 proximity không cấp reaction C

**Thay đổi.** BQLC đổi `independent_htf_reaction_score`: D1 proximity-only, visit open, `completed_unreacted` và stale đều `0`; chỉ visit exited có reaction follow-through còn hiệu lực mới `1`. Fixture D1 giữ `expected_current_behavior` bonus 2 và expected-after-fix bonus 0. Acceptance/progress đồng bộ.

**File/vị trí.** `docs/plans/smc-bqlc-spec.md` §6/§7; `tests/fixtures/smc_d1_proximity_only.json`; `docs/plans/smc-lifecycle-spec.md` §6; `docs/plans/smc-acceptance-dossier.md` §2.

**Bằng chứng kiểm tra.** Probe baseline đã gọi `_d1_zone_reaction_bonus` trên fixture và trả `(2,["D1_ZONE_REACTION_BONUS"])`; đây là lỗi nền được giữ riêng. Fixture expected-after-fix là proximity metadata/bonus 0.

**Quyết định đã áp dụng.** Không thêm partial-reaction event trong phạm vi này; `completed_unreacted`/proximity/open đều C reaction feature bằng 0. Runtime test sau này phải kiểm tra đủ các trạng thái này.

### R16-08 — bounds validation không tự sinh Q

**Thay đổi.** BQLC bỏ `bounds_integrity=1` chỉ vì ordered/finite. Ordered/finite/positive/tick-aligned là hard validation gate. Geometry dùng `0.65*width_score + 0.35*family_geometry_score`, với công thức: OB `clamp(1-base_width/(1*formation_atr),0,1)`; FVG `clamp(remaining_width/original_width,0,1)`; S/D `clamp(1-base_width/(avg_range*compression_limit(n)),0,1)`. Formation không tái sử dụng các metric geometry này. Hai ví dụ S/D nay dùng raw OHLC hợp lệ và history statistics tường minh: base/zone width `.66`, `avg_range=1`, `formation_atr=2`, compression `.50`, width/ATR `.33` nên width score `1`. Minimum: BUY `100.09/101.50/100/101.29`, SELL mirror `99.91/100/98.50/98.71`, body/ATR score `3/7`, body/range score `.60`, close score `.80`, family `0`, formation `.460`, geometry `.825`, Q `.635`, S `8.645`. Trên minimum: BUY `100.135/102.25/100/101.935`, SELL mirror `99.865/100/97.75/98.065`, body/ATR score `6/7`, body/range `.60`, close `.80`, family `.50`, formation `.710`, geometry `.825`, Q `.760`, S `9.520`. OB/FVG vẫn giữ subtotal formation/integrity giả định được ghi rõ; endpoint S/D `[1.50,3.00]` không đổi.

**File/vị trí.** `docs/plans/smc-bqlc-spec.md` §4/§9; `docs/plans/smc-parameter-table.md` P11/§R16; `docs/plans/smc-acceptance-dossier.md` §2.

**Bằng chứng kiểm tra.** Đã tính bằng Decimal chuỗi BUY OHLC → normalized feature → formation → geometry → Q → S cho cả hai S/D cases; SELL là mirror kiểm tra cùng tỷ lệ. Đã kiểm tra inverse-vs-linear, endpoints/clamp/missing policy và tách validation gate. Đây là kiểm tra tài liệu/toán học; chưa chạy Q scorer runtime.

**Chờ Tech Lead duyệt.** Duyệt family feature cụ thể, endpoints và trọng số `0.65/0.35`; các phương trình đã đủ để review raw→normalized→geometry→Q→S nhưng chưa được triển khai vào scorer. Tài liệu không còn coi validation là chất lượng.

### R16-09 — watch-no-plan và no-zone

**Thay đổi.** Readiness, selection và compatibility thống nhất: zone confirmed/usable hợp lệ nhưng planner không tạo plan giữ `selected_setup_id`, `selected_zone_id`, quality và lifecycle; đặt `plan=null`, `plan_reference=null`, `plan_available=false`, status `WATCH_ZONE`. Chỉ no-zone sau core đủ, core unavailable hoặc không có candidate hợp lệ mới selected IDs null. Có bảng ba payload và timeline BUY/SELL.

**File/vị trí.** `docs/plans/smc-selection-spec.md` §8/§12; `docs/plans/smc-readiness-spec.md` §7/§10; `docs/plans/smc-compatibility-spec.md` §3/§4; `docs/plans/smc-acceptance-dossier.md` §2; `docs/plans/smc-implementation-progress.md` task 12/13/16.

**Bằng chứng kiểm tra.** Đã đối chiếu selection loop/finalizer, readiness output table và compatibility null policy; đã sửa các điểm từng nói selected IDs null khi no-plan. Đã bổ sung `selected_visit_id=entry_visit_id` khi visit đã mở và cho phép plan còn tồn tại sau trigger expiry. Chưa chạy serializer/UI runtime.

**Chờ Tech Lead duyệt.** Xác nhận serializer current có giữ selected visit ID khi plan null và phân biệt candidate pending với confirmed watch. Không cho UI/consumer suy luận no-zone chỉ từ `plan=null`.

## 3. Commands đã chạy và kết quả

Các command dưới đây đã thực sự chạy; không ghi command runtime mới như thể đã chạy sau patch hồ sơ:

| Command | Kết quả | Phân loại |
|---|---|---|
| `python -m pytest tests/test_smc_canonical_golden.py tests/test_smc_composition.py tests/test_smc_consumer_phase6.py tests/test_smc_context.py tests/test_smc_directional_confluence.py tests/test_smc_domain_models.py tests/test_smc_m15_confirmation.py tests/test_smc_phase7_validation.py tests/test_smc_prefilter.py tests/test_smc_scorer.py tests/test_smc_scoring_phase0.py tests/test_smc_scoring_result.py tests/test_smc_sweep_linking.py tests/test_smc_zone_ai_review.py tests/test_smc_zone_audit_cache.py tests/test_smc_zone_lifecycle.py tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q` | `418 passed in 3.63s` baseline, Python 3.11.9/pytest 9.0.3 | Runtime baseline trước response; không phải test expected-after-fix |
| Cùng command trên khi Tech Lead review rerun | `418 passed in 3.41s` | Runtime baseline xác nhận lại; không phải test contract mới |
| `python -X utf8 scripts/run_smc_validation.py --help` | exit `0` | Interface/help probe đã chạy |
| `python scripts/scanner_pit_collector.py --schema` | exit `0` | Interface/schema probe đã chạy |
| `python scripts/run_smc_validation.py --help` không có `-X utf8` | lỗi encode CP1258 của Windows console | Known console encoding issue, không phải lỗi logic CLI |
| M15 stale evaluator probe | 48 candle; current `confirmed=True`, `reaction=True`, `penalty=0` | Baseline bug reproduction |
| D1 proximity bonus probe | `(2, ["D1_ZONE_REACTION_BONUS"])` | Baseline bug reproduction |
| Protected swing probe | `structure=mixed`, `bos=false`, `choch=false`, `choch_confirmed=false` | Baseline bug reproduction |

Sau khi chỉnh hồ sơ, command kiểm tra fixture/docs được chạy ở §4. Không chạy pytest/runtime regression, PIT thật, UI/restart/cache hoặc execution smoke trong turn này vì phạm vi yêu cầu chỉ là hồ sơ/fixture và chưa được phép triển khai runtime.

## 4. Kiểm tra hồ sơ/fixture sau chỉnh sửa

Đây là các kiểm tra tĩnh đã chạy sau patch:

| Command | Kết quả |
|---|---|
| `python -X utf8 -c "import json; from pathlib import Path; paths=['tests/fixtures/smc_m15_stale_rejection.json','tests/fixtures/smc_d1_proximity_only.json','tests/fixtures/smc_protected_swing_differs_from_latest.json']; [json.load(Path(p).open(encoding='utf-8')) for p in paths]; print('fixtures: valid=', len(paths))"` | `fixtures: valid= 3` |
| PowerShell `rg` kiểm tra các marker/R16 contract trong spec/dossier/progress/fixture | pass; marker và expected contract có mặt |
| PowerShell `Get-FileHash -Algorithm SHA256 docs/plans/smc-task-16-rereview.md` | `39C885656A4038798E4083CAC69FE19BA8B4EC1AEA67F837EDC892F5891F4A20`; re-review được giữ nguyên, chỉ đọc |
| PowerShell `Get-FileHash -Algorithm SHA256 docs/plans/smc-task-16-review-round3.md` | `72E9D38CA57E8C97C65810E1525A27CDC3B90F9FD5294253A1E7A9F9B628AFA3`; round 3 được giữ nguyên, chỉ đọc |
| PowerShell `Get-FileHash -Algorithm SHA256 docs/plans/smc-task-16-review-round4.md` | `81676D65CC616237C2E9A58B5EC8D1608C67864810EC36643DBF03E639B7467C`; round 4 được giữ nguyên, chỉ đọc |
| PowerShell tính SHA256 từng file scope | pass; manifest ở §5 |
| PowerShell `Get-Content ... | ConvertFrom-Json` trên 3 fixture | `fixture_parse=PASS count=3` |
| PowerShell decimal boundary probe cho BUY/SELL wick và RR | wick vector `True,False,True,False,False,False`; RR `5.5,2.75,5.5`; `formula_boundary_checks=PASS` |
| PowerShell contradiction scan trên changed scope | `changed_scope_contradiction_scan=PASS` |
| PowerShell `git status --short -- core services controllers models` | không có runtime status entry |

Các acceptance test tương lai chưa chạy gồm structure causal replay, H4/H1–M15 lifecycle, M15 boundary detector, B/Q/L/C boundary scorer, Analyze/Scanner parity, serializer/UI và PIT corpus. Chúng được ghi là pending, không dùng tài liệu/fixture để tuyên bố runtime pass.

Round 3 static check bổ sung: ba fixture parse được; marker `bootstrap_ready_at`, `source_history_anchor_at`, execution ATR fallback, inverse geometry và `WATCH_ZONE/plan_available=false` đều có mặt; contradiction scan không còn marker cũ. Decimal probe cho wick/close-color là `True,False,True,False,False,False`, RR là `5.5,2.75,5.5`, OB good geometry `.8775`, FVG geometry `.475`, và trả `formula_boundary_checks=PASS`. Đây vẫn là kiểm tra tài liệu/fixture/toán học, không phải runtime test.

Round 4 static check: Decimal probe trên hai chuỗi BUY OHLC S/D và SELL mirror trả `sd_cases` minimum `formation=.460, geometry=.825, Q=.635, S=8.645`, trên minimum `formation=.710, geometry=.825, Q=.760, S=9.520`, `mirror_ok=True`, `sd_raw_boundary_checks=PASS`. Đây là kiểm tra raw OHLC→feature→score trong tài liệu, chưa chạy scorer runtime.

## 5. Revision và manifest bàn giao sau phê duyệt

Manifest hồ sơ đã được review lần 5 phê duyệt là `F6C56A33AEC121E0F393B9CE3DB79B18BA70DEDC8879D51ABE82DD121B2A050B`; response tại thời điểm duyệt có SHA256 `E802AAE6F7EAC83FA1B90AF8D77D668F5A00A97DC1114D740E0D029F52B3469D`. Đây là dấu vết lịch sử bất biến trong báo cáo lần 5. Manifest bên dưới được cập nhật cho trạng thái bàn giao hiện tại: chỉ progress đổi trong tập 14 file, response vẫn hash riêng ngoài aggregate. Không đổi đặc tả, fixture hoặc quyết định phê duyệt.

- Git revision nền/review: `fb9ea527ee7ff0eb48c53875e24796260008e92c` (`main`); không có commit mới.
- Canonical digest method: lấy các file scope bên dưới, sort theo repo-relative path dùng `/`; mỗi dòng `SHA256_UPPERCASE + two spaces + relative_path`; join bằng LF, không thêm LF cuối; SHA256 chuỗi manifest cho ra `SUBMISSION_MANIFEST_DIGEST`.
- `smc-task-16-review.md` bị loại khỏi manifest vì là review gốc bất biến. Response file này cũng bị loại khỏi aggregate để tránh tự tham chiếu; SHA256 của nó được ghi riêng khi kết thúc.

Danh sách file scope và digest được điền sau command manifest cuối cùng:

```text
SUBMISSION_MANIFEST_DIGEST=F4871CA6CF3CDE8039C795996B32DD3D53B36A1F46A556F41D16143D31C5F2B6
RESPONSE_FILE_SHA256=reported in final handoff (not embedded to avoid self-reference)
```

Aggregate manifest không bao gồm review gốc và response file để tránh self-reference; SHA256 cuối của response được báo ở handoff và có thể tái tạo bằng `Get-FileHash -Algorithm SHA256 docs/plans/smc-task-16-review-response.md`. Manifest command ghi ở §4.

Scope gồm các file đã sửa trong hồ sơ: `docs/plans/smc-implementation-progress.md`, `docs/plans/smc-data-spec.md`, `docs/plans/smc-structure-spec.md`, `docs/plans/smc-parameter-table.md`, `docs/plans/smc-zone-spec.md`, `docs/plans/smc-lifecycle-spec.md`, `docs/plans/smc-bqlc-spec.md`, `docs/plans/smc-readiness-spec.md`, `docs/plans/smc-selection-spec.md`, `docs/plans/smc-compatibility-spec.md`, `docs/plans/smc-acceptance-dossier.md`, `tests/fixtures/smc_m15_stale_rejection.json`, `tests/fixtures/smc_d1_proximity_only.json`, `tests/fixtures/smc_protected_swing_differs_from_latest.json`.

Digest từng file tại lần chốt manifest:

```text
F014F27974E8F11F8FF53E1D118E4A65A925EC04ED0D56208840F01B087AB2A6  docs/plans/smc-acceptance-dossier.md
B9A9BCC84BE32340098B76DF9F0B9BE70AD6E117844262C05787D25013970E34  docs/plans/smc-bqlc-spec.md
DB8ED34FF48B5479481B33F6E24A9AA0682E378C2BBF7308FFF73277422C165E  docs/plans/smc-compatibility-spec.md
C966D8307A28C8E61A20A1E93830E2778CABB5BBC01A4DBE42D47E56A0398682  docs/plans/smc-data-spec.md
0B3A06C3B8CB2A2630D4CF6E4F80D70253FC6B969BC7CD04C49C9B380C41EABD  docs/plans/smc-implementation-progress.md
9541AF6EF055A0CB1C5962CA2A8B81D6FE2740486B59D4653D91564E427434B0  docs/plans/smc-lifecycle-spec.md
C4A3C1C7785010E3DD6E82D3312C61689D0D3A0D3B9218415EA53E1826A11FC1  docs/plans/smc-parameter-table.md
559F2AD64994F6BBCD6B55323E402A98E4E708CD57E1A86C9043D6A274146E2D  docs/plans/smc-readiness-spec.md
2EE712D1596BF0145FB1F67AADD691457B6D367F04DB5F60BDD6212AA3A85111  docs/plans/smc-selection-spec.md
20C66269A3D4C1D827E070DA4FEB8D87A631D0729189EF5E98ACCB6DF99AA27C  docs/plans/smc-structure-spec.md
C609A6E50A7B3FB865F5FE0AF0BF6137F2EA424EA4D060CB7F07EB0B6C34D766  docs/plans/smc-zone-spec.md
6D9BF9B5E36228EF13985C29CF6885A447C700E927A2D62728763B4B38F07261  tests/fixtures/smc_d1_proximity_only.json
1253E04657D1A90E0DC6447202B5B3B87D41988755E7E66DBE39ABC18F3B23ED  tests/fixtures/smc_m15_stale_rejection.json
1C556136F1B1AEF48230233654CB119B6C9F7870D6626289A839DFA94955DA17  tests/fixtures/smc_protected_swing_differs_from_latest.json
```

## 6. Quyết định bàn giao

Task 16 **APPROVED** theo [Tech Lead review lần 5](D:/Projects/AIMarketAnalyst/docs/plans/smc-task-16-review-round5.md); R16-01 đến R16-09 đều CLOSED ở mức đặc tả. Response và progress đã đồng bộ quyết định này. Coder được tiếp tục task 17–39 trên nhánh làm việc và phải dừng review tại task 40; không bắt đầu task 41 trước khi gate 40 được APPROVED. Phê duyệt hồ sơ không cho phép bỏ gate, thay producer production hoặc bật auto-entry. Lượt cập nhật này không triển khai task 17, không sửa runtime và không gửi lệnh giao dịch.
