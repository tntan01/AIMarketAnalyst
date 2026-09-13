# Tech Lead review — gate72, lần 1

**Quyết định: CHANGES_REQUESTED. Chưa được làm task73.**

- Reviewer: Codex, Tech Lead theo yêu cầu người dùng.
- Ngày: 2026-09-11, khoảng 09:28 Asia/Saigon.
- Phạm vi: task57–71, lifecycle/visit/fill/expiry, liquidity pools/sweeps, setup ownership/contribution và D1 reaction. Chặng D/scorer mới/M15 entry/production rollout không thuộc lượt này.
- Chuẩn: `smc-implementation-plan.md` task57–72, `smc-lifecycle-spec.md`, P7/P8/P9 trong parameter table, BQLC §L/§C và exclusive ownership đã duyệt. Không bổ sung threshold hoặc đổi contract trong review.
- Hồ sơ trình gồm response task57–71 và progress; chưa có dossier gate72 riêng. HEAD `fb9ea527ee7ff0eb48c53875e24796260008e92c`; worktree dirty qua nhiều chặng. Quyết định gắn với content hashes ở cuối báo cáo, không xem mọi git diff từ HEAD là thay đổi riêng chặng này.
- Reviewer chỉ thêm báo cáo/probes và đồng bộ progress/response hiện hành; không sửa production hoặc tests của Coder. Gate56 APPROVED giữ nguyên.

## 1. Kết luận và phạm vi đã đạt

**9 finding OPEN: 6 P1, 3 P2.** Các seam đã được triển khai nhưng chưa đủ nghiệm thu chặng lifecycle/liquidity.

Reviewer chạy được 108 tests task57–71 và toàn bộ baseline SMC/scanner 854 tests. Các ca thường về visit IDs/round-trip, departure exclusion, tolerance, fill direction/original bounds, expiry boundary, same-owner child dedupe và D1 proximity-only đạt trong bộ hiện có. Tuy nhiên tests xanh chưa chứng minh source-time, multi-owner/persisted consumption hay terminal-state consistency; một số candle fixtures còn sai OHLC.

Bộ tái hiện độc lập: [probes/test_smc_gate72_review.py](probes/test_smc_gate72_review.py), **14 failed, 2 passed**. Đây là 16 probes bổ sung chạy explicit, không nằm trong con số baseline 854; không skip/xfail, không thay expected tests đã có. Ngoại trừ probe kiểm tra fixture sai của Coder, mọi chuỗi OHLC do reviewer tạo đều qua `validate_smc_candles` trước khi dùng.

| Finding | Priority | Task chịu trách nhiệm | Vấn đề |
|---|---|---|---|
| R72-01 | P1 | 66, 67, 71 | Sweep được phát trước source confirmation; pool mất provenance thời gian |
| R72-02 | P1 | 68, 69, 71 | Linker chọn setup theo khoảng cách trước ownership, loại mất claim sớm nhất |
| R72-03 | P2 | 69, 71 | Child của non-owner chiếm slot contribution, owner nhận 0 |
| R72-04 | P1 | 69, 71 | Context gán lại owner/assignment của sweep đã consumed |
| R72-05 | P1 | 70, 71 | D1 canonical lifecycle đã broken vẫn cấp reaction evidence |
| R72-06 | P2 | 60, 64, 65 | Look-ahead follow-through gắn reaction tại candle đã expiry |
| R72-07 | P1 | 59, 63, 65 | Enrichment bỏ tick được truyền; thiếu metadata silently dùng buffer/tolerance=0 |
| R72-08 | P1 | 63, 65 | Zone bị invalidated vẫn giữ canonical confirmed/usable=true |
| R72-09 | P2 | 60, 62, 65, 71 | Acceptance fixtures dùng OHLC không hợp lệ, chưa đủ bằng chứng end-to-end |

## 2. Findings và tiêu chí sửa đã khóa

### R72-01 — Không kiểm tra source confirmation tại sweep candle

**Code:** `core/smc_context.py:4240`, `:4290`, `:4443`, `:4527–4532`, `:4553–4558`.

Pool eligibility chỉ đọc các boolean hiện tại; output pool là các level float, không giữ source IDs/usable_at. Sweep `causal_only=True` chỉ so pivot index với sweep index, không kiểm tra `confirmed_at`. Equal-pool average thường không bằng level của source nào nên lookup source trả None, bỏ luôn index guard.

**Tái hiện:** source record typed có pivot index0, `confirmed_at=06:00`, confirmed/usable=true tại snapshot; sweep index2 đóng03:00. Qua pool → detector với `causal_only=True` vẫn nhận một sweep BUY và SELL. Đây là probe kiểm tra input source-time, không giả vờ source record được tạo từ pivot detector của chuỗi probe.

**Expected:** không có sweep usable tại03:00 từ source chỉ confirmed06:00; không thể backdate evidence bằng boolean ở cutoff mới. Giữ pool identity, sources và thời điểm usable đủ để kiểm tra cả swing pool và equal pool. Source/metadata không đủ trên canonical path phải fail closed; không dùng numeric level làm bằng chứng source-time. Bổ sung positive sau source usable và case equal pool có hai source confirmed khác thời điểm; prefix/batch phải nhất quán. Không bỏ mọi sweep để vượt negative.

**Probe:** `test_r72_01_sweep_must_not_precede_source_confirmation[buy/sell]`.

### R72-02 — Ownership theo claim time bị linker vô hiệu trước khi xét

**Code:** `core/smc_sweep_linking.py:243–273`, `core/smc_context.py:4634–4655`.

Linker sort distance/departure-gap rồi loại mọi setup khác khi một setup đã nhận sweep. Context chỉ chuyển những link còn lại thành claims. Vì vậy `assign_sweep_ownership` không thấy toàn bộ claim đủ điều kiện, dù helper độc lập sort claim time đúng.

**Tái hiện:** sweep level105 reclaim11:00; ATR2. Setup early available13:00, bounds[105.2,106], distance=.10ATR; setup late available15:00, bounds[100,110], distance=0. Cả hai cùng BUY, formation windows hợp lệ, distance đều <=.25ATR. Context chọn **late**, trong khi contract max(reclaim, available) yêu cầu **early**.

**Expected:** lọc validity/geometry/time trước, xét ownership trên tất cả eligible claims, rồi project link cho children của owner. Distance là gate, không được thay causal owner ranking. Khóa list permutation, same-time tie và multi-family cùng owner qua context, không chỉ test assignment helper độc lập.

**Probe:** `test_r72_02_context_must_consider_earliest_eligible_setup_before_distance_rank`.

### R72-03 — Contribution winner được chọn từ cả non-owner

**Code:** `core/smc_sweep_linking.py:394–424`.

`contribution_winner` chọn zone ID nhỏ nhất trong tất cả normalized claims, rồi flag lại đòi setup==owner. Nếu ID nhỏ nhất thuộc non-owner, không claim nào đạt cả hai điều kiện.

**Tái hiện:** owner early/child `z-owner` available13:00; late/child `a-nonowner` available15:00. Assignment đúng early nhưng tổng contribution bằng **0**, không phải1. Việc thêm unrelated late claim đã làm mất contribution của owner.

**Expected:** chọn slot contribution trong các child claims của assignment owner, giữ đúng một contribution khi owner hiện diện, non-owner luôn0. Rename/permutation/duplicate child không làm contribution biến mất. Nếu owner chỉ còn trong history và không có child hiện tại, không trao điểm cho setup khác.

**Probe:** `test_r72_03_nonowner_child_cannot_take_contribution_slot`.

### R72-04 — Consumed record không bảo vệ owner ở context replay

**Code:** `core/smc_context.py:4634–4655`; linker không chặn consumed source, context không truyền assignment history/history completeness vào ownership.

**Tái hiện:** attach sweep cho original-owner available13:00, record đã có `consumed=true`, owner và assignment ID. Chạy lại chính record sweep đó với later-owner available15:00 trong danh sách zone: owner và assignment bị thay. Đây không phải yêu cầu xây persistence service mới; chính audit record đang có đã bị bỏ qua.

**Expected:** đã có assignment hợp lệ thì giữ nguyên owner/assignment qua context/rebuild. Nếu owner không có trong window hiện tại, không tự cấp sweep cho setup muộn; propagate `SWEEP_OWNER_HISTORY_INCOMPLETE` khi cần. Pool consumption phải có source identity xuyên observation; đánh `pool_consumed` trên một sweep không tự đảm bảo pool mới không phát lại contribution vô hạn. Kiểm tra same snapshot, owner rơi khỏi window, record/history được restore và observation khác của cùng pool. Không chỉ sửa helper có optional history trong khi caller luôn dùng mặc định history_complete=true.

**Probe:** `test_r72_04_context_must_not_reassign_already_consumed_sweep`.

### R72-05 — D1 reaction bỏ qua canonical invalidation

**Code:** `core/smc_confluence.py:165–176`.

Guard chỉ xét stale/expired/age, không đọc `lifecycle_broken`, invalidation time hay canonical invalid state.

**Tái hiện bằng lifecycle thật:** BUY D1 zone[100,110], tick=.1, ATR1. Candle0 outside, candle1 visit, candle2 exit và reaction, candle3 close99 invalidates. `ZoneLifecycle.lifecycle_broken=True` nhưng `build_d1_reaction_evidence` trả **valid=true, score=1**. SELL mirror lỗi tương tự; không dựa trên legacy flag giả.

**Expected:** tại cutoff sau invalidation, giữ visit/history cho audit nhưng không cấp active D1 reaction score. Positive cùng chuỗi trước invalidation vẫn hợp lệ; canonical terminal state thắng flags legacy và visit historical. Kiểm cả typed object lẫn serialized mapping.

**Probe:** `test_r72_05_broken_d1_lifecycle_cannot_supply_active_reaction[buy/sell]`; positive control `test_control_live_d1_reaction_still_accepted`.

### R72-06 — Follow-through vượt ranh giới expiry

**Code:** `core/smc_lifecycle.py:187–202`, `:613–631`; expiry chính tại `:149` không được áp dụng bên trong future reaction search.

**Timeline D1, lifetime20, age anchor0:**

| Candle index | Giá BUY | Expected |
|---|---|---|
| 19 | O109 H110 L105 C109 | Open visit |
| 20 | O110.2 H110.22 L110.15 C110.2 | Exit ngoài tolerance .1, chưa đạt reaction110.25 |
| 21 | O112 H114 L111 C113 | Age21: expired, không phát reaction |

**Actual:** prefix qua20 là completed_unreacted; append21 tạo `reacted_at` đúng bằng `expired_at` và đổi visit thành completed_reacted. SELL mirror cùng lỗi. Contract yêu cầu invalidation/expiry trước reaction, không tạo event reaction sau terminal.

**Expected:** không tìm reaction vượt terminal boundary. Cùng candle exit/reaction trước expiry vẫn được phép; reaction xảy ra hợp lệ trước terminal vẫn giữ lịch sử. Khóa expiry trước/đúng/sau prospective reaction với OHLC hợp lệ, không chỉ invalidation guard.

**Probe:** `test_r72_06_expiry_candle_cannot_create_reaction_for_earlier_exit[buy/sell]`.

### R72-07 — Tick metadata bị mất và missing data biến thành zero threshold

**Code:** `core/smc_context.py:4923–4925`; `core/smc_lifecycle.py:477–478`, `:497–498`.

`enrich_zones(..., tick_size=.1)` forward tick cho FVG fill nhưng lifecycle chỉ đọc `item.tick_size`. Zone không lặp lại tick trong payload sẽ mất metadata; resolver thiếu tick hoặc ATR trả0.0 không reason unknown.

**Tái hiện:** BUY confirmed zone[100,110], payload atr_current1, tick=.1 ở argument. Close99.98 còn trong break buffer hợp lệ .1 phải không invalid; actual buffer0, broken=true. SELL mirror cùng lỗi.

**Expected:** forward metadata đúng scope, không làm cùng input thay kết quả chỉ vì tick nằm trong argument thay vì item. Canonical metadata thiếu phải unknown/fail closed theo P7/lifecycle §4, không silently dùng0. Có thể giữ legacy compatibility nếu phân biệt rõ; không dùng latest/future ATR để sửa missing causal source cho sự kiện quá khứ. Khóa đủ metadata, thiếu tick/ATR, explicit override và boundary BUY/SELL.

**Probe:** `test_r72_07_enrich_must_forward_explicit_tick_to_lifecycle[buy/sell]`.

### R72-08 — Invalidation không đồng bộ canonical status/usability

**Code:** `core/smc_context.py:4943–4957` chỉ project expired, thiếu nhánh invalidated.

**Tái hiện độc lập R72-07:** payload đủ tick=.1/ATR1, `lifecycle_status=confirmed`, `usable=true`; candle BUY close99 phá vùng. Result `lifecycle_broken=true`, `broken=true`, nhưng vẫn **lifecycle_status=confirmed, usable=true**. SELL mirror tương tự.

**Expected:** mọi projection canonical thống nhất terminal invalid/unusable; giữ original ID/bounds/visit history và invalidation reason/time. Không để consumer tự chọn một trong các cờ mâu thuẫn, không chuyển sang breaker. Test context → typed round-trip → consumer evidence chứ không chỉ bool lifecycle_broken.

**Probe:** `test_r72_08_invalidated_zone_must_not_keep_confirmed_usable_flags[buy/sell]`.

### R72-09 — Fixture lifecycle/fill không hợp lệ

**Code:** `tests/test_smc_zone_lifecycle_task60.py:69–73` và các ca dùng cùng OHLC; `tests/test_smc_fvg_fill_task62.py` nhiều BUY formation rows.

Ví dụ task60 positive dùng O112 H113 **L111.2 C110.2**, rồi O111 H112 **L110.5 C110.3**, tức close dưới low. Shared data validator trả `SMC_OHLC_INVALID` cho cả ba tail candles của positive; lifecycle vẫn chạy nên tests xanh. Task62 dùng O102 H112 **L105** C110 (open dưới low). Các trường hợp này không thể tồn tại trên thị trường và không chứng minh valid pipeline.

**Expected:** sửa fixture OHLC, giữ nguyên mục đích semantic; bổ sung validation ngay trong fixture factory/matrix. Không chỉ nới validator, skip/xfail hoặc xóa assertion. Khi sửa low/high làm thay overlap/exit thì dựng lại chuỗi đúng thay vì đổi expected theo output code. Giữ valid positive, negative và boundaries BUY/SELL; tối thiểu có chuỗi detector → lifecycle → D1/context với nguồn thật. Không yêu cầu sửa golden R56 đã duyệt.

**Probe:** `test_r72_09_existing_task60_positive_fixture_must_have_valid_ohlc` gắn shared validation vào factory của positive task60; không sửa module hoặc file Coder trong lúc review.

## 3. Lệnh tái lập / kết quả thực chạy

Chạy từ repo root bằng PowerShell:

```powershell
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=short
# 14 failed, 2 passed in 0.36s

$gate72Tests = @(rg --files tests -g '*task5[7-9].py' -g '*task6[0-9].py' -g '*task7[01].py')
python -m pytest @gate72Tests -q
# Reviewer đã chạy explicit cùng 15 test files: 108 passed in 1.26s

$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
# 854 passed in 9.11s

git diff --check
# Exit0, chỉ LF/CRLF warnings.
```

Golden contract/fixture/suite R56-01 khớp nguyên hash đã duyệt. Không phát hiện regression gate56 trong baseline đã chạy. Chưa chạy toàn bộ repository, UI/live trading, build/production hoặc chứng nhận execution.

## 4. Bàn giao sửa và điều kiện trình lại

1. Sửa theo cụm owner rõ ràng: pool/source-time (01); claim/link/history/contribution (02–04); lifecycle terminal/metadata/projection (06–08); D1 consumer (05); fixture validation/end-to-end (09).
2. Đọc các expected ở §2 trước implementation. Nếu phát hiện mâu thuẫn với contract, báo input/điều khoản cụ thể để Tech Lead quyết định; không tự thêm heuristic hoặc đổi ngưỡng.
3. 16 reviewer probes phải pass không skip/xfail; baseline 854 không tái phát. Coder được thêm tests cho các acceptance extensions ghi rõ trong từng finding. Tests R56/golden contract không đổi.
4. Trình `docs/plans/smc-task-72-response.md`: mapping R72-01…09 → root cause → code → tests, actual commands/count, SHA256 code/tests mới và một timeline source→sweep→assignment→visit→terminal/D1 hợp lệ. Tách isolated-helper test khỏi integration/prefix/restore proof.
5. Sau fix trạng thái là WAITING_REVIEW, không tự APPROVED. Tech Lead sẽ chạy lại và đồng bộ quyết định. Không task73, không production rollout/auto-entry, không sửa review lịch sử.

## 5. Manifest nội dung được review

| File | SHA256 |
|---|---|
| `core/smc_context.py` | `D7550D1A0A9A3FDB6CAF17B520359F5BEC00D064FF242F11DBAF21AF6D62A3E7` |
| `core/smc_models.py` | `AE630F7B24160D794675602A08B3C05F9A9A52410AFD7FBBBEDA066E1C93AA20` |
| `core/smc_lifecycle.py` | `AAB6B803417070588B90EB4F9EAC73563565C8B48C76875EC2808FDFB6ECD019` |
| `core/smc_sweep_linking.py` | `38B0276FB065D6EF7FBB454D8C6929D533D8ECA22FFC4EDB5BF6C352E57EFFB3` |
| `core/smc_confluence.py` | `386008C758FC23CE3ED2E8F66F65AF8F2A38090DA039B9E3FF2A71CDFDACCDEF` |
| `tests/test_smc_zone_lifecycle_task60.py` | `3E10EC367DF219079E95CCE23490FF305BFE999763F0FAFC9F828C8CE3843357` |
| `docs/plans/probes/test_smc_gate72_review.py` | `5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6` |
