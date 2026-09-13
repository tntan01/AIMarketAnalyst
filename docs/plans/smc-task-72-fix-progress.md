# Gate72 fix progress — F00/F01

**HIỆN HÀNH: TASK72 APPROVED — D PASS, TL 2026-09-12 (§A3.157).** R72-01…09 CLOSED trong phạm vi gate; A/B/C PASS giữ nguyên, F11 hoàn tất. Task73 chưa thực hiện; không rollout production. Các trạng thái trước bên dưới là lịch sử.

### A3.157 — Quyết định cuối task72: APPROVED

Tech Lead ngày2026-09-12 nghiệm thu bản trình F11 §A3.156. **D PASS; gate72 APPROVED; R72-01…09 CLOSED** theo bảng quyết định tại `smc-task-72-response.md` mục0. Hai chuỗi: actual swing→pool→sweep→caller→assignment→repeat/restore được node F11 kiểm liền mạch; confirmed zone→lifecycle→typed→D1 positive/invalid/expiry được các node actual-producer A3-057…062 kiểm, không lấy H1 smoke thay chuỗi này.

Reviewer chạy full §5 **983 passed**, probes **16 passed**, task57–71 **108 passed**. Acceptance129 + retained854 =983; manifest5 core + acceptance **6/6 khớp**, protected probe/golden/4 R56 **6/6 khớp**. SHA256 acceptance: `978AA7ECD044B9D41FF7AEBCDE650D2D5191DB5BAD8869D5C709A73A317E8E11`. Không code/test changes trong lượt TL; git diff --check kiểm sau đồng bộ.

Giới hạn và G1/G2 giữ theo response mục0/7 và quyết định trước; canonical production rollout không thuộc phê duyệt. Không mở lại task72 vì deferred cleanup/formatting hoặc yêu cầu tương lai ngoài scope. Task73 hết bị gate72 chặn, **chưa thực hiện và không tự khởi chạy**. Người dùng quyết định việc tiếp tục kế hoạch144 bước.

**Quyết định hiện hành — checkpoint C PASS, TL 2026-09-12 (§A3.155).** C-R1/C-R2 đã đạt trong phạm vi review, G1/G2 theo §A3.153. A/B giữ PASS. Chuyển F11 để nghiệm thu end-to-end và trình D; gate72 chưa APPROVED, chưa task73. Các kết luận C trước bên dưới giữ làm lịch sử.

### A3.155 — Tech Lead duyệt checkpoint C: PASS

**Ngày:** 2026-09-12. Duyệt cụm F06–F10 sau bản sửa §A3.154. C-R1: caller giữ canonical lineage/time; thiếu reclaimed_at không lấy open time thay, không cấp owner/consumption/contribution mới; control đủ mốc và legacy vẫn đạt. C-R2: history cùng lineage khác owner/assignment fail closed, không chọn theo insertion order. Giữ replay same-pool, pool mới độc lập và history-only controls đã đạt.

**Reviewer kiểm chứng:** ba regression caller same-pool/history-conflict/missing-reclaim **3 passed**; probes **16 passed**; task57–71 **108 passed**; full §5 **982 passed, 0 failed**. Acceptance128 + retained854 =982. T hash `24F4243E289769D314EEA82398AB00FC85022F2080CE857C69DD6DB4E3A1BFFC`. Probe + canonical golden +4 R56 hashes **6/6 khớp baseline**. Reviewer không sửa core/tests hoặc commit; chỉ đồng bộ quyết định.

**Ghi chú đã xử lý:** G1 min instant hợp lệ theo setup và G2 completeness/claim-time trước class theo §A3.153; provisional usable_at=None theo §A3.143; source_ids là lineage equal pool, không bịa source_swing_id đại diện; pool cap và caller legacy theo §A3.146. Không bổ sung invariant assignment-flag↔tổng-claim. used_owners/định dạng lịch sử không chặn C, không mở cleanup riêng.

**NEXT F11**, đúng §3 fix-plan: nghiệm thu hai chuỗi actual-producer end-to-end, đối chiếu baseline node inventory và hoàn thiện `smc-task-72-response.md` để trình **WAITING_REVIEW D**. Reuse evidence/tests đã có; không làm lại A/B/C, không rollout Analyze/Scanner canonical, không mở framework/tính năng/scoring mới. Nếu nghĩa vụ F11 chưa có evidence thì bổ sung đúng ca cần thiết, không suy end-to-end từ tổng số PASS. Các kết quả hiện tại là baseline kiểm chứng, không thay lệnh chạy mới ở snapshot trình D.

**Giới hạn quyết định:** C PASS không CLOSED9 findings hoặc APPROVED gate72. F11 chưa thực hiện; chỉ D do TL duyệt mới bỏ chặn task73. `git diff --check` kiểm sau cập nhật hồ sơ.

**Hiện hành — C lần2 CHANGES_REQUESTED (§A3.153, 2026-09-12):** C-R2 và same-pool replay C-R1 đạt; chỉ sửa tiếp fallback time→reclaimed_at ở caller canonical. Full981P chưa bao phủ ca thiếu mốc này. G1/G2 được chốt/đính chính tại §A3.153, chưa F11/task73.

**Hiện hành — C CHANGES_REQUESTED, TL 2026-09-12 (§A3.151):** full979P nhưng hai diagnostic F10 thất bại: caller mất canonical lineage/time khi dựng claim; helper chọn history đầu tiên thay fail closed khi cùng pool có assignment mâu thuẫn. Giữ A/B PASS; sửa C-R1/C-R2, chưa F11/task73.

**NEXT hiện hành: F07/r1 — sửa compatibility boundary của caller production (§A3.146).** Giữ A/B PASS và sweep canonical F07 đã triển khai; không tự chuyển producer legacy sang canonical, chưa F08/task73.

**Điều phối hiện hành — §A3.143:** A/B giữ PASS. F06 đã có implementation pool nhưng còn nối producer→pool: làm F06/r1 phát usable_at tường minh trên swing producer theo quyết định dưới đây, rồi báo trước F07. Chưa C/task73.

**Quyết định hiện hành — checkpoint B lần4 PASS (2026-09-11), §A3.141.** B-R1/B-R2 đạt trong phạm vi review; F02–F05 qua checkpoint B. Giữ A PASS, chuyển F06 theo fix-plan; gate72 vẫn CHANGES_REQUESTED, R72-01…09 OPEN, chưa task73. Các quyết định B trước và WAITING_REVIEW bên dưới giữ làm lịch sử.

**Quyết định B lần3 — CHANGES_REQUESTED, §A3.139 (2026-09-11):** B-R1 và hai ca bảo toàn terminal/timestamp đã đạt. Chỉ còn phần history của B-R2: enrich thiếu metadata ghi đè visit terminal bằng reaction sau invalidation. Giữ các phần đạt; chưa F06.

**Quyết định B lần2 — CHANGES_REQUESTED (2026-09-11), §A3.137:** B-R1 đạt; B-R2 chưa bảo toàn terminal khi derivation chạy vào nhánh expiry. Chỉ sửa tiếp B-R2, đồng bộ mapping ba regression trong cùng lượt; chưa F06. Quyết định này thay trạng thái bản trình §A3.136, giữ A PASS.

**Quyết định mới nhất — checkpoint B: CHANGES_REQUESTED**, Tech Lead 2026-09-11, §A3.135. Giữ checkpoint A PASS; chỉ sửa B-R1/B-R2 dưới đây, chưa F06. Bản trình §A3.134 và các trạng thái IMPLEMENTED/WAITING_REVIEW giữ làm lịch sử coder, không thay kết luận này.

**Status: checkpoint A lần4 `PASS` — Tech Lead 2026-09-11; Gate72 vẫn `CHANGES_REQUESTED`**

Quyết định hiện hành: **§A3.129 — PASS checkpoint A lần4**. Chấp nhận 5/5 nhóm A3R3 và bản trình §A3.128; A3-090 IMPLEMENTED. Coder làm F02 → F03 → F04 → F05 rồi dừng trình B. Không làm lại90 mã; chưa F06/task73, chưa CLOSED R72 findings hoặc APPROVED gate72. Các trạng thái A lần3/WAITING_REVIEW và kết quả cũ bên dưới giữ lịch sử.

**Checklist A3-001…090:** Coder đã hoàn tất bản trình đủ90 mã ở §A3.93; không còn trạng thái “cả90 TODO”. Reviewer đã chạy lại: acceptance65 failed/51 passed (116 node), full65 failed/905 passed, retained854 passed, task57–71:108 passed, probes13 failed/3 passed. Số pass không loại trừ lỗi oracle/coverage. Các dòng WAITING_REVIEW và kết quả từng lượt cũ bên dưới giữ làm lịch sử; chỉ các mục được review mở lại mới cần sửa.

**Mốc lịch sử:** A3 ledger mở 2026-09-11 11:11 +07:00, A3-001 IMPLEMENTED. Reviewer lượt này không sửa core/tests, chỉ báo cáo và đồng bộ hồ sơ.

Tech Lead đã review lần1: F00 PASS, phần sửa OHLC của F01 PASS; yêu cầu
bổ sung coverage case-level, sửa thứ tự terminal/reaction và interface
proposal. Bản lần2 áp dụng các quyết định A-D01…A-D07, chưa F02 và chưa đóng
toàn bộ R72-09. Đoạn này và ledger F00/F01 ngay dưới là lịch sử trước A lần3.
**Date:** 2026-09-11 (Asia/Saigon)  
**Scope:** F00 baseline + F01 fixture/oracle audit only. No F02, no task73.

## Ledger

| Subtask | Status | Files changed | RED before / GREEN after | Previous tests retained | Remaining RED / decision |
|---|---|---|---|---|---|
| F00 | IMPLEMENTED | This ledger | reviewer probes 14 failed, 2 passed | task57–71: 108 passed; SMC/scanner: 854 passed | R72-01…09 reproduced |
| F01 | WAITING_CHECKPOINT | five fixture files, expanded acceptance test, matrix | R72-09 fixture validity GREEN; 49 acceptance cases collect, 30 RED/19 GREEN | task57–71: 108 passed; retained SMC/scanner: 854 passed | R72-01…08 behavior RED where implementation is missing; TL approval needed |

## F00 baseline

Baseline was captured against the existing dirty worktree. No reset, stash,
cleanup, or unrelated change was performed.

```text
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=short
14 failed, 2 passed in 0.34s

$gate72Tests = @(rg --files tests -g '*task5[7-9].py' -g '*task6[0-9].py' -g '*task7[01].py')
python -m pytest @gate72Tests -q --tb=short
15 files; 108 passed in 1.27s

$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q --tb=short
66 files before F01; 854 passed in 9.08s

git diff --check
Exit 0; only existing LF/CRLF conversion warnings.
```

Initial reviewer RED node mapping:

```text
R72-01 [buy], [sell]; R72-02; R72-03; R72-04;
R72-05 [buy], [sell]; R72-06 [buy], [sell];
R72-07 [buy], [sell]; R72-08 [buy], [sell]; R72-09.
```

Initial dirty state included tracked edits in `core/market_models.py`,
`core/smc_confluence.py`, `core/smc_context.py`, `core/smc_lifecycle.py`,
`core/smc_models.py`, `core/smc_sweep_linking.py`, and
`tests/test_smc_context.py`, plus pre-existing untracked SMC modules, plans,
fixtures, and tests from earlier tasks. These were preserved; the complete
machine-readable state is the F00 `git status --short` capture in the session.

## F01 result

Only fixture/test/docs scope changed. No `core/` file, reviewer probe, R56
contract, or R56 golden fixture changed.

| File/case | Old OHLC | New OHLC | Expected semantic retained |
|---|---|---|---|
| task59 exit | `(112,114,111.2,110.2)` | `(112,114,110.2,110.2)` | close remains outside `high+0.1`; no displacement |
| task60 BUY exit/reaction rows | lows `111.2,110.5,111.5` with closes `110.2,110.3,110.5` | lows `110.2,110.3,110.5` | same exit and 3-candle reaction window |
| task60 SELL reaction rows | `(98,99,98.8,99.8)`, `(99,99.5,98,99.7)`, `(98,98.5,97,99.5)` | `(98,99.8,97.5,99.8)`, `(99,99.7,98,99.7)`, `(98,99.5,97,99.5)` | below-zone exit and `99.5` reaction preserved |
| task62/task65 BUY formation | `(102,112,105,110)` | `(102,112,102,110)` | valid formation; post-formation fill unchanged |
| task63 shared exit | invalid task60 row | valid task60 row | buffered invalidation unchanged |
| task63 SELL wick-only | `(105,111,109,109.5)` | `(105,111,104.5,109.5)` | close-not-wick invalidation unchanged |

The positive factories in task59, task60, task62, task63, and task65 now call
`validate_smc_candles`; intentional invalid-data cases remain separate and the
validator was not relaxed.

Actual F01 checks:

```text
python -m pytest tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py tests/test_smc_fvg_fill_task62.py tests/test_smc_zone_lifecycle_task63.py tests/test_smc_lifecycle_task65.py -q --tb=short
32 passed in 0.48s

python -m pytest docs/plans/probes/test_smc_gate72_review.py::test_r72_09_existing_task60_positive_fixture_must_have_valid_ohlc -q --tb=short
1 passed in 0.08s

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
14 tests collected

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=short
13 failed, 1 passed in 0.40s

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=short
13 failed, 3 passed in 0.33s

python -m pytest @gate72Tests -q --tb=short
108 passed in 1.26s

SMC/scanner retained baseline, excluding the new acceptance file:
854 passed in 8.98s
```

The 13 acceptance RED nodes are the expected implementation obligations
R72-01…R72-08 (BUY/SELL where applicable), not hidden with skip/xfail. The
corrected R72-09 probe is GREEN.

## Hash ledger

The reviewed core/protected hashes are unchanged:

```text
core/smc_context.py       D7550D1A0A9A3FDB6CAF17B520359F5BEC00D064FF242F11DBAF21AF6D62A3E7
core/smc_models.py        AE630F7B24160D794675602A08B3C05F9A9A52410AFD7FBBBEDA066E1C93AA20
core/smc_lifecycle.py     AAB6B803417070588B90EB4F9EAC73563565C8B48C76875EC2808FDFB6ECD019
core/smc_sweep_linking.py 38B0276FB065D6EF7FBB454D8C6929D533D8ECA22FFC4EDB5BF6C352E57EFFB3
core/smc_confluence.py    386008C758FC23CE3ED2E8F66F65AF8F2A38090DA039B9E3FF2A71CDFDACCDEF
docs/plans/probes/test_smc_gate72_review.py 5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6
tests/fixtures/smc_canonical/golden_cases.json 45437A90E540BF772E1E3F2899C06D328293181F19F9B36AA5E26C3170C79999
docs/plans/smc-r56-01-session-contract.md F04A0E6451801E04EA90E288543FD03B96CB82C715657992962A2FDB433D50BB
docs/plans/smc-r56-01-coder-handoff.md AA682DA161E49E807CC0AB2CD7E6BC3A581E9E8AD14456F6FB53BDE41F28D301
tests/fixtures/smc_r56_01_session_acceptance.json 698CF8A2557FFD829CEBF7316AE30D854C84BED605B17F5FF1C6220254D2BDD5
tests/test_smc_r56_01_session_acceptance.py F1975050751F61A44CFE3B0936C19179A85DEECA08735D942986CFD8A253A5CA
```

## Checkpoint A

See [`smc-task-72-acceptance-matrix.md`](smc-task-72-acceptance-matrix.md) for
the nine finding obligations, acceptance node IDs, old→new→expected ledger,
and proposed caller→owner→data interfaces/boundaries.

**Checkpoint A lần 2 — `WAITING_REVIEW`.** Giữ F00/fixture fixes đã đạt; F01
supplement áp dụng A-01…03 và decisions A-D01…07. Không sửa core hoặc làm F02
trước khi TL PASS.

## Checkpoint A lần 2 supplement

Applied the review requirements in
[`smc-task-72-checkpoint-a-review.md`](smc-task-72-checkpoint-a-review.md):

- Added case-level positive, boundary, missing-metadata, permutation,
  JSON-restore, typed round-trip, terminal-cutoff, and real detector-chain
  cases to the acceptance test file. Expected values are contract-written;
  no production output generated an oracle.
- Corrected event order to
  `availability/cutoff → invalidation/expiry → exit → reaction`. Reaction at
  age20 remains history; reaction at the inclusive terminal candle or after
  it is blocked. Invalidation has priority.
- Recorded A-D01…A-D07 in the matrix, including inclusive
  `pool_usable_at <= reclaimed_at`, both canonical claim timestamps,
  historical-owner contribution zero, inclusive terminal cutoff, stable pool
  identity, tick-source parity/conflict, and canonical/legacy boundaries.
- Added concrete proposed signatures/fields and caller propagation for pool
  source lineage, assignment history/completeness, metadata unknown, typed
  terminal projection, and pool identity. No API or core implementation was
  changed.

Latest acceptance collection/run:

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
49 tests collected

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=short
30 failed, 19 passed in 0.81s
```

The 30 RED cases are explicit implementation obligations for later F02–F10 or
missing canonical representation. The 19 GREEN cases cover fixture validity,
controls, permutations, restore and valid boundary behavior; none claims a
finding closed. Existing reviewer probes and retained baseline remain
unchanged, and all F01 edits stay outside `core/`.

Latest F01 supplement hashes:

```text
tests/test_smc_gate72_fix_acceptance.py  DEF12B99850D7C6E0B248DAFB83939F5B746510E2D63F761019E5F560248FF63
docs/plans/smc-task-72-acceptance-matrix.md  45E8DD27839321BEAD7E999ACF5A0103D79C0EEC5567A15160544EA31ED3CD8F
```

**Checkpoint A lần 2 — `WAITING_REVIEW`; F01 supplement complete. Stop until
Tech Lead records PASS.**

---

## A3 — checklist checkpoint A lần3

Chỉ ghi kết quả; không thay số liệu lịch sử ở trên. Quy tắc và định nghĩa trạng thái theo
[fix-plan §8.1][§8]. Lượt này làm đúng dải mã được giao, không tự chuyển F02.

### Bảng ledger

Theo template [fix-plan §8.7][§8]:

```text
Mã | Trạng thái | Vị trí | Việc + bằng chứng | Giữ nguyên / đã làm | Còn lại
```

| Mã | Trạng thái | Vị trí | Việc + bằng chứng | Giữ nguyên / đã làm | Còn lại |
|---|---|---|---|---|---|
| A3-001 | IMPLEMENTED | `L` / Git | Ghi mốc nhận việc: revision, trạng thái Git, fingerprint core/probe/R56 theo danh sách F00 (11 file) + fingerprint phạm vi F01 để so cuối lượt. Không chạy lại F00. | Giữ nguyên mọi thay đổi có trước; không reset/stash/cleanup/commit. | Phát hiện 1 điểm lệch hash cần A3-003 đối chiếu (xem §A3.3). |
| A3-002 | IMPLEMENTED | `T` / `L` | Lập danh sách node acceptance đang collect được trước khi sửa. Command ở §A3.5 → **49 tests collected in 0.17s**, **0 lỗi collection**. Inventory đầy đủ ở §A3.5. | Không sửa file nào; chỉ collect/đọc. | Tên node chưa đối chiếu với matrix/review A lần2 — thuộc A3-003. |
| A3-003 | IMPLEMENTED | `M` (bảng đối chiếu mới) / `L` | Đối chiếu 17 điểm F01.1…4 với code hiện tại + 1 điểm CHƯA RÕ; nhận diện fixture đã sửa để không ghi đè. Chi tiết ở [§Đối chiếu F01.1…4 trong matrix](smc-task-72-acceptance-matrix.md#đối-chiếu-f011f014-với-code-hiện-tại--a3-003); tóm tắt §A3.6. | Chỉ đọc test/matrix/probe và ghi tài liệu; thêm 1 mục vào **cuối** matrix, phần lịch sử A lần2 giữ nguyên. | 13 điểm CÒN THIẾU + 3 MỘT PHẦN còn phải làm ở A3-005…062; 1 điểm cần A3-080 xác minh. |
| A3-004 | IMPLEMENTED | `M` (bảng theo dõi mới) / `L` | Chuẩn hóa cột theo dõi ca nghiệm thu: `Full node ID / Rule ref / Input-TF-cutoff / Precond / Expected / Actual / Loại RED`; một hàng cho mỗi node chạy được (không dùng `[buy/sell]`), `Actual` để trống theo yêu cầu. Đối chiếu tự động: 49 hàng, 49 ID duy nhất, khớp 100% danh sách collect §A3.5 (không thừa/thiếu/trùng). | Chỉ thêm mục mới vào cuối matrix; phần lịch sử và bảng A3-003 giữ nguyên. | `Actual`/`Loại RED` sẽ điền ở A3-083/084; hoàn thiện case-level ở A3-081. |
| A3-005 | IMPLEMENTED | `M` (mục interface pool mới) / `L` | Ghi schema pool theo review A lần2: numeric keys giữ `list[float]` làm legacy projection; `records` canonical có `pool_id/kind/level/source_ids/sources/usable_at`; mỗi source giữ `swing_id/confirmed_at/usable_at/provisional`. Kèm 6 luật bắt buộc (không key nào vừa float vừa dict; thiếu records ⇒ fail closed). | Chỉ thêm mục mới; mục "Interface proposal" của A lần2 giữ nguyên làm lịch sử và được ghi rõ là bị thay thế. Không sửa `core/`. | 3 câu hỏi mở trình TL: tên enum `kind`, swing pool một source, `level` của equal pool. |
| A3-006 | IMPLEMENTED | `M` (mục interface history mới) / `L` / `smc-task-72-fix-plan.md` | Đính chính đề xuất `history_complete`: đề xuất cũ ghi default `False` là sai; default hiện hữu trong code là `True` (`core/smc_sweep_linking.py:279`, wrapper `:444`). Ghi ngữ nghĩa 3 nhánh + nghĩa vụ canonical caller truyền True/False tường minh. Kiểm chứng: `test_r72_04_incomplete_history_returns_explicit_reason` + `test_r72_04_assignment_survives_json_restore_with_late_only_window` → **2 passed in 0.15s**; 8 file bảo vệ **0 changed**. | Không sửa `core/` — code đã đúng default, chỉ tài liệu sai. Thêm con trỏ "đã bị thay thế" ở mục proposal cũ; nội dung lịch sử giữ nguyên. | Không còn blocker; A3-011/A3-012 dùng ràng buộc này để viết test tường minh. |
| A3-007 | IMPLEMENTED | `M` (mục interface metadata mới) / `L` | Ghi contract biểu diễn thiếu metadata: `metadata_state="unknown"` + `metadata_reason` không rỗng, `usable=False`, threshold không tính được `None` (không `0`/`NaN`), `lifecycle_status` giữ nguyên; kèm bảng 7 ca (thiếu ATR / thiếu tick / nonfinite / conflict / parity / one-source / terminal + thiếu) và ranh giới terminal. Kiểm chứng đọc code: `SmcZone(lifecycle_status="unknown")` → `ValueError`; enum đóng `core/smc_models.py:38-45`; `SmcZone` chưa có field `usable`; `metadata_state` = 0 hit toàn repo. Chạy 4 node R72-07 liên quan → **4 failed in 0.17s**, RED đúng loại `implementation` (buffer `0.0` khi thiếu tick/ATR; nonfinite `ValueError`; argument tick không forward; conflict chọn item `.2` âm thầm). 8 file bảo vệ **0 changed**. | Không sửa `core/`, test, probe hay R56 — chỉ thêm mục mới vào cuối `M` + con trỏ "đã bị thay thế" ở mục proposal cũ; nội dung lịch sử giữ nguyên. | 1 câu hỏi mở không chặn: tên chuỗi reason code cụ thể. A3-015…018/020/021 viết assertion theo contract này. |
| A3-008 | IMPLEMENTED | `M` (mục interface claim→assignment mới) / `L` | Ghi chuỗi caller→owner→output với field thật: sweep record (`core/smc_context.py:4488-4515`) → link (`core/smc_sweep_linking.py:234-236`) → claim (caller `core/smc_context.py:4647-4653`) → owner (`:275`) → projection (`:439`, `core/smc_context.py:4662-4671`). Chốt 8 luật từ A-D02/A-D03/A-D06 (không thêm thuật toán ownership): claim cần **cả** `reclaimed_at` + `setup_available_at`, thiếu một ⇒ `SWEEP_CLAIM_TIME_MISSING` không assignment, không fallback; `pool_id`/`source_ids` phải theo claim vào **history record**; history-only owner giữ owner với contribution 0; cùng pool identity không tạo owner mới. Kiểm chứng bằng probe `python -c` trên `core`: claim chỉ có `reclaimed_at` **hoặc** chỉ `setup_available_at` **hoặc** alias `sweep_time` đều được cấp assignment; record `SweepAssignment` **không** chứa `pool_id`/`source_ids`; history-only → `{}`. Chạy 5 node liên quan → **4 failed, 1 passed in 0.21s** (RED đúng loại `implementation`, xem §A3.11). 8 file bảo vệ **0 changed**. | Không sửa `core/`, test, probe, R56 — chỉ thêm mục mới cuối `M` + con trỏ thay thế ở mục proposal cũ. Không đề xuất thuật toán ownership mới. | 1 câu hỏi mở không chặn: claim thiếu hẳn lineage thì fail closed hay nhận kèm reason. A3-013/014/045–048/069 viết assertion theo contract này. |
| A3-009 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Chuyển `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy/sell]` từ assertion `isinstance(equal_lows[0], dict)` (schema sai bị review cấm) sang canonical `records`: numeric projection vẫn `list[float]` = trung bình cặp (`100.025`/`109.975`), **đúng một** record theo `source_ids=["source-a","source-b"]`, `pool_id`/`kind` không rỗng, `usable_at = max(stamp(1),stamp(2))` tính từ fixture, `sources` giữ `confirmed_at`/`usable_at`/`provisional=False` từng source. Thêm helper cục bộ `_pool_records` (chấp nhận cả list và mapping, không khoá shape chưa chốt). Fixture: bổ sung `usable_at` tường minh cho 2 source để expected không phụ thuộc quy tắc fallback chưa chốt. Command + kết quả ở §A3.12; file hash mới `3A51064295B545783A180D9F7CA3E1751B6A00F1148E7518FC64743261016208`. | Giữ nguyên mọi thay đổi có trước; không sửa `core/`, probe, R56/golden. Không khoá 3 câu hỏi mở của A3-005 (tên enum `kind`, swing pool một source, `level` của equal record) — chọn record theo lineage và chỉ đòi `kind`/`pool_id` là chuỗi không rỗng. | RED còn lại đúng loại `interface` (`records` chưa có — thuộc F06), 2 node; inventory giữ **49 node**, tổng file **30 failed / 19 passed** không đổi. Còn tồn: `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` vẫn assert numeric-as-dict → thuộc A3-039/A3-022. |
| A3-010 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Viết mới `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[buy/sell]`: payload pool numeric-only (`swing_lows=[100.0]` / `swing_highs=[110.0]`, **không** có `records`) + `tick=.1`/`ATR=1`; assert fail closed `swept_lows == []` **và** `swept_highs == []`. Precondition assert độc lập: numeric level còn tồn tại, `"records" not in pools`, và geometry fixture thật (`low 99.5 < 100-0.2` + `close 100.1 > 100`; SELL mirror `110.5 > 110.2` + `close 109.9 < 110`). Control: cùng nến/swings trên nhánh legacy không truyền pool → sweep idx2 được nhận ⇒ kết quả rỗng của canonical là do thiếu provenance, không do fixture không có excursion. Command/kết quả ở §A3.13. | Chỉ thêm test + 2 hàng `M`; không sửa `core/`, probe, R56/golden. Pytest cũ không đổi. Fixture viết tay (không lấy output production). | RED hiện tại đúng loại `implementation` (numeric level vẫn cấp sweep — F07 phải fail closed), 2 node; inventory **49 → 51 node**, tổng file **30 → 32 failed, 19 passed**. Phụ thuộc: ca positive `records`→sweep chưa viết được vì container/`kind` của A3-005 còn câu hỏi mở 1–2 (thuộc A3-040/044). |
| A3-011 | IMPLEMENTED | `T` / `L` / `M` | Truyền `history_complete` **tường minh** ở mọi canonical-path call trong file acceptance: 4 ca "còn dựa default" (`test_r72_03_acceptance_contribution_is_selected_within_owner_children`, `test_r72_02_same_time_tie_is_stable_under_claim_permutation`, `test_r72_02_missing_canonical_claim_time_fails_closed`, `test_r72_03_duplicate_owner_children_keep_one_contribution_under_permutation`) + 3 call site dựng history ban đầu (`test_r72_03_historical_owner_without_current_child_gets_zero_contribution`, `test_r72_04_assignment_survives_json_restore_with_late_only_window`, `test_r72_04_same_pool_observation_cannot_bypass_consumption`) → `True`. Tổng: **11/11 call site** `assign_sweep_ownership` trong file nay truyền cờ (10 `True`, 1 `False` — ca incomplete của A3-012). Không đổi assertion nào. Command/kết quả ở §A3.14; file hash mới `AEAF61777105E005C150A2AC135E5002EC9C32C40E5707D7A3ACCCC22CF74416`. | Chỉ sửa test; không sửa `core/`, probe, R56/golden. Cập nhật 1 hàng verdict trong bảng đối chiếu A3-003 của `M` (thêm ghi chú ngày, giữ bằng chứng lịch sử). | Thay đổi **trung tính hành vi** (default của helper là `True`, đã xác minh ở A3-006) — tổng file giữ **32 failed / 19 passed**, inventory **51 node** không đổi. Còn tồn: caller context `_probe.attach` không truyền được completeness vì `_attach_zone_sweep_links` chưa có tham số đó (probe là file read-only) → thuộc F08/F10, đã ghi nhận. |
| A3-012 | IMPLEMENTED | `T` / `L` / `M` | `test_r72_04_incomplete_history_returns_explicit_reason`: giữ `history_complete=False` **tường minh**, làm claim đầy đủ canonical (`pool_id="pool-1"`, `source_ids=["swing-1"]` thêm vào `reclaimed_at`/`setup_available_at` vốn có) và assert precondition 4 field để kết quả rỗng không thể quy cho field khác thiếu (A-D02/A-D06). Siết `reason_codes == ["SWEEP_OWNER_HISTORY_INCOMPLETE"]` (đúng một reason, theo contract A3-006 và tiền lệ `test_smc_sweep_consumed_task69.py:113`). Command/kết quả ở §A3.15; file hash mới `0D3B9E8A75A454507CC60AA5EE8BF3B3107A88326E1014FB23763B476902C9AB`. | Chỉ sửa test + 1 hàng `M`; không sửa `core/`, probe, R56/golden. Không thêm node/không đổi inventory. | Node giữ **GREEN** (`1 passed`), tổng file **32 failed / 19 passed** không đổi. Control `history_complete=True` cùng claim ⇒ có owner `late` ⇒ assertion thực sự phụ thuộc cờ, không vacuous. Không còn blocker; A3-048 dùng lại ca này cho history conflict. |
| A3-013 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Parameterize `test_r72_02_missing_canonical_claim_time_fails_closed` theo `missing_field ∈ {reclaimed_at, setup_available_at}` (A3-014 cho phép parameterize chung). Claim giữ **field còn lại hợp lệ** (assert `== stamp(13)` / `== stamp(11)`) **và lineage** (`pool_id="pool-1"`, `source_ids=["swing-1"]`), `history_complete=True` tường minh; assert field thiếu vắng mặt; expected `assignments == {}` + `SWEEP_CLAIM_TIME_MISSING` trong `reason_codes`. Command/kết quả ở §A3.16; file hash mới `899440F84507A11C2EFEE0804C3B52D10AD77B5C57AFEE7FBE71CC71DBB2D028`. | Chỉ sửa test + `M` (2 hàng tracking theo node ID tham số hoá, inventory, hàng đối chiếu A3-003); không sửa `core/`, probe, R56/golden. Giữ `in` cho reason theo đúng câu chữ hàng A3-013 (khác A3-012 dùng `==` vì contract A3-006 nói "đúng một reason"); phần chống fail-vì-lý-do-khác do precondition đảm nhiệm. | RED cả 2 param đúng loại `implementation` (F08 fallback sang timestamp còn lại: `[reclaimed_at]` → eligible `13:00`, `[setup_available_at]` → eligible `11:00`). Inventory **51 → 52 node**, tổng file **32 → 33 failed, 19 passed**. **A3-014**: ca `setup_available_at` đã nằm trong cùng node ⇒ mã sau chỉ cần verify + reuse, không viết lại. |
| A3-014 | IMPLEMENTED | `T` / `L` / `M` | Xác minh ca `[setup_available_at]` của node A3-013 khớp hàng A3-014 (reclaimed time hợp lệ, không fallback) và **thêm positive control** dùng chung cho cả 2 param: cùng claim đủ 2 mốc (`reclaimed_at=stamp(11)`, `setup_available_at=stamp(13)`, lineage `pool-1`/`swing-1`, `history_complete=True`) ⇒ owner `setup` và `claim_eligible_at == max(stamp(11),stamp(13)) = stamp(13)` (A-D02). Control chặn trường hợp `assignments == {}` pass rỗng nếu claim bị loại vì lý do khác. Command/kết quả ở §A3.17; file hash mới `28F1D7924F8CB0FACE46C8AE2B3F79D3DE1938DC122043A7A3464273CA0008FA`. | Không tạo bản sao test, không viết lại assertion của A3-013; chỉ thêm khối control + 2 hàng `M`. Không sửa `core/`, probe, R56/golden. | Control **PASS** (kiểm độc lập bằng probe: `owner=setup`, `eligible=13:00` = `max(stamp(11),stamp(13))`), nhưng chưa được thực thi trong lượt chạy RED vì assert âm phía trên fail trước — đã ghi rõ. Tổng file giữ **33 failed / 19 passed**, inventory **52 node**. Không blocker; A3-016/A3-017 dùng tiếp cùng fixture canonical. |
| A3-015 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Viết mới `test_r72_07_missing_canonical_atr_is_unknown_and_unusable`: item tick `0.1` hợp lệ + `atr_current=None`, H1 2 nến với close `102.5` trong zone `[100,110]` ⇒ **vùng chưa terminal**. Assert đúng contract A3-007 (không dùng dạng `status in {unknown,candidate,invalid}` hay `buffer != 0` bị review cấm): `metadata_state=="unknown"`, `metadata_reason` chuỗi không rỗng, `usable is False`, `invalidation_buffer is None`, giữ `lifecycle_status=="confirmed"` + `broken is False` (assert `lifecycle_expired is False` làm precondition). Kèm **positive control** cùng fixture với `atr_current=1` ⇒ `invalidation_buffer ≈ 0.1`, `confirmed`, `broken=False`. Command/kết quả ở §A3.18; file hash mới `6BE3417ACD419172597BD78930874B153AE882306EE2EB8A711546DC5791EDE8`. | Chỉ thêm test + 2 hàng `M`; không sửa `core/`, probe, R56/golden. Không đụng node bundled `missing_or_nonfinite` (thuộc A3-016/A3-017) và không khoá quy tắc fallback `confirmed_at → usable_at` (chưa có quyết định). | RED đúng loại `interface`: dừng ở `KeyError: 'metadata_state'` (field chưa có — contract A3-007/F02). Probe xác nhận 2 gap implementation phía sau: `usable` hiện `True`, `invalidation_buffer` hiện `0.0`. Inventory **52 → 53 node**, tổng file **33 → 34 failed, 19 passed**. Control verified bằng probe, chưa được thực thi trong lượt RED (assert trước fail) — đã ghi rõ. |
| A3-016 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Viết mới `test_r72_07_missing_canonical_tick_is_unknown_and_unusable` (mirror A3-015): item `atr_current=1` **hợp lệ**, không khai nguồn tick nào (`tick_size`/`digits`/`point` đều vắng), close `102.5` trong zone ⇒ chưa terminal. Cùng bộ assertion contract: `metadata_state=="unknown"`, `metadata_reason` không rỗng, `usable is False`, `invalidation_buffer is None` (không tự suy từ `digits`, không điền `0`), giữ `confirmed`/`broken is False`; precondition assert ATR `== 1` và vắng cả 3 key nguồn tick. Control cùng fixture với `tick_size=0.1` ⇒ `invalidation_buffer ≈ 0.1`. Command/kết quả ở §A3.19; file hash mới `9BC772D90CF315B90C0F7875A78828B3EB469994576038C23C8891F200A6AE14`. | Chỉ thêm test + 2 hàng `M`; không sửa `core/`, probe, R56/golden. Không sửa node bundled `missing_or_nonfinite` (phần nonfinite thuộc A3-017). | RED đúng loại `interface` (`KeyError: 'metadata_state'`); probe cho thấy gap implementation phía sau: `usable True`, `buffer 0.0`. Inventory **53 → 54 node**, tổng file **34 → 35 failed, 19 passed**. Control verified bằng probe, chưa chạy tới trong lượt RED — đã ghi rõ. |
| A3-017 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | **Đổi tên + parameterize** node bundled `test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero` → `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current\|tick_size]`: chỉ giữ ca **nonfinite** (NaN theo từng field), bỏ phần missing (đã do A3-015/A3-016 khóa riêng), field còn lại hợp lệ (assert), vùng chưa terminal; assert `metadata_state=="unknown"`, `metadata_reason` không rỗng, `usable is False`, `invalidation_buffer is None` — bỏ hẳn dạng bị review cấm (`status in {unknown,candidate,invalid}`, `buffer != 0`). Thêm `import math`. Command/kết quả ở §A3.20; file hash mới `978F4106BA23B2C9574F706A2D49AE7E5DAA5330B8DED9376A1D94A32FE28BF5`. | Chỉ sửa test + `M` (thay 1 hàng cũ bằng 2 hàng mới, ghi rõ rename cho A3-082); không sửa `core/`, probe, R56/golden. | RED cả 2 param đúng loại `implementation`, dạng **raise** `ValueError: Invalid zone boundary: nan` tại `_finite_float` (`core/smc_lifecycle.py:674`) — nonfinite phải thành `unknown`, không được ném lỗi. Inventory **54 → 55 node**, tổng file **35 → 36 failed, 19 passed**. Ghi nhận quan sát: `inf`/`-inf` cũng đi cùng nhánh `isfinite` và hiện cũng raise; **chưa** khóa bằng node riêng (để A3-063 quyết định theo coverage). |
| A3-018 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Sửa `test_r72_07_conflicting_same_scope_tick_sources_fail_closed`: bỏ assert sai nhánh `lifecycle_status == "unknown"`, thay bằng contract A3-007 — `metadata_state=="unknown"`, `metadata_reason` không rỗng, `usable is False`, `invalidation_buffer is None` (không dùng cả `0.1` lẫn `0.2`), giữ `confirmed`/`broken is False`; dùng fixture chưa terminal (`close 102.5` trong zone) thay vì nến mặc định làm zone bị invalidate bởi buffer `0`. Thêm precondition: hai nguồn tick cùng scope **mâu thuẫn** (`0.2 != 0.1`), `atr_current == 1` hợp lệ, chưa terminal ⇒ `unknown` chỉ có thể do conflict. Command/kết quả ở §A3.21; file hash mới `F9E6B2B0F74E94512E5C06A54E863A37BDDD3E01BC763D8119D4193E191BC5DA`. | Chỉ sửa test + 3 hàng `M`; không sửa `core/`, probe, R56/golden. Không thêm control parity (thuộc A3-019) và không khoá chuỗi reason cụ thể (câu hỏi mở A3-007). | RED đúng loại `interface` (`KeyError: 'metadata_state'`); probe cho thấy gap implementation phía sau: item tick `0.2` **thắng âm thầm** (`buffer 0.2`), `usable True`. Inventory giữ **55 node**, tổng file giữ **36 failed / 19 passed** (node vốn đã RED, nay RED đúng lý do). |
| A3-019 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Siết `test_r72_07_item_and_argument_tick_sources_have_parity[buy/sell]` sang expected **tuyệt đối** cho **từng** biến thể thay vì chỉ so ba kết quả với nhau: mỗi biến thể phải có `invalidation_buffer ≈ 0.1` (= `max(tick,0.05*ATR)` tính từ fixture), `lifecycle_broken is False`, `lifecycle_status == "confirmed"`; thêm assert ba khai báo thực sự khác nhau (item-only có `tick_size`, argument-only không có key). Fixture giữ nguyên nến `[(112,114,111,113),(100,101,99.95,99.98)]`. Command/kết quả ở §A3.22; file hash mới `06B98D133C0580CA531DD62FCB11BD7588FD4DDB233EEE9F2EC5C600FADF520F`. | Chỉ sửa test + 3 hàng `M`; không sửa `core/`, probe, R56/golden. Giữ assertion cũ về buffer cho item-only/equal-both (nay tuyệt đối hoá) — không nới assertion. | RED cả BUY/SELL tại đúng biến thể `argument_only` (message assert nêu tên biến thể): buffer `0.0` thay vì `0.1`, kèm `broken True`. Probe xác nhận `item_only`/`equal_both` đều `0.1`/`False`/`confirmed` — gap nằm ở argument tick chưa được forward (`core/smc_context.py:4912-4926`), thuộc F02. Tổng file giữ **36 failed / 19 passed**, inventory **55 node**. |
| A3-020 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Viết mới `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[expired_by_age\|already_invalid]`: (a) H1 **52 nến** trong zone ⇒ expiry theo age (độc lập metadata), (b) item đã mang terminal evidence (`lifecycle_status="invalid"`, `broken=True`, `usable=False`). Cả hai thiếu **toàn bộ** nguồn tick (`tick_size`/`digits`/`point` vắng) + ATR hợp lệ. Assert: `lifecycle_status` giữ `expired`/`invalid` (≠ `confirmed`), `lifecycle_expired` đúng theo nhánh, `usable is False`, `visits` còn nguyên (`open` / `closed_by_invalidation`), `metadata_state=="unknown"`, `metadata_reason` không rỗng, `invalidation_buffer is None`; kèm control cùng nến **có** `tick_size=0.1` ⇒ cùng trạng thái terminal. Command/kết quả ở §A3.23; file hash mới `5B4B167D4D94541E287E1D40656196FFA97F0473E14BC27D242BA03F2C3BE83F`. | Chỉ thêm test + 3 hàng `M`; không sửa `core/`, probe, R56/golden. Không assert `broken` ở nhánh `already_invalid` (thuộc projection R72-08/F03) để không khoá quá phạm vi. | RED cả 2 param đúng loại `interface` (`KeyError: 'metadata_state'` tại dòng 828 — mọi assert trước đó PASS, gồm giữ trạng thái terminal + history). Probe xác nhận gap implementation phía sau: buffer `0.0`. Control verified bằng probe (`expired`/`invalid` + `usable False`), chưa chạy tới trong lượt RED. Inventory **55 → 57 node**, tổng file **36 → 38 failed, 19 passed**. |
| A3-021 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Viết mới `test_r72_07_metadata_survives_context_to_typed_round_trip`: fixture thiếu ATR (tick `0.1` hợp lệ, vùng chưa terminal) → assert **lifecycle→context** có `metadata_state=="unknown"`, `metadata_reason` không rỗng, `usable is False`, `invalidation_buffer is None`; rồi **context→typed→JSON** `SmcZone.from_dict(json.loads(json.dumps(context))).to_dict()` vẫn giữ `metadata_state`/`metadata_reason`/`usable`. Expected lấy từ contract A3-007, không lấy từ payload production. Command/kết quả ở §A3.24; file hash mới `3BE3EE62829C4CDAABA9F1280FC7A127FF4EB26742B93A61D0E5376E3CED6EDE`. | Chỉ thêm test + 3 hàng `M`; không sửa `core/`, probe, R56/golden. Không assert threshold trên payload typed (contract đề xuất typed chỉ gồm `usable`/`terminal_at`/`terminal_reason`/`lifecycle_status`) để không vượt phạm vi A3-007. | RED đúng loại `interface`: dừng ở `context["metadata_state"]` (stage lifecycle→context); probe xác nhận **stage typed cũng thiếu**: payload `to_dict()` 73 key không có `metadata_state`/`metadata_reason`/`usable`/`invalidation_buffer` (F02/F03 phải thêm). Control round-trip (identity/bounds/status/visits) PASS. Inventory **57 → 58 node**, tổng file **38 → 39 failed, 19 passed**. |
| A3-022 | IMPLEMENTED | `M` / `T` / `L` | Rà mô tả schema cũ còn mâu thuẫn theo 3 nhóm: (1) **numeric-as-dict** — sửa `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` (assertion numeric-as-dict **cuối cùng** trong file acceptance) sang interface: numeric `equal_lows` giữ `float` + trung bình cặp, provenance đọc từ `records` bằng helper `_pool_records`, `usable_at = max(usable_at các source)` tính từ fixture (fixture thêm `usable_at` tường minh); (2) **default `False` mới** — hàng đối chiếu `M` thêm đính chính "đã đính chính ở A3-006, default hiện hữu là `True`"; (3) **unknown lifecycle** — không còn mô tả nào coi `unknown` là lifecycle status (chỉ còn ghi chú lịch sử/đúng contract). `M` cập nhật thêm hàng tracking của node và con trỏ A3-039/A3-022 ở hàng đối chiếu A3-003. Command/kết quả ở §A3.25; file hash mới `0D1E96D5EF3E96B682D58F88B8CFC93A32E9410539737CA0663D11762D84746E`. | Chỉ sửa test + `M`; **không sửa `core/`**, probe, R56/golden, không đổi ngưỡng/quy tắc. Giữ nguyên fixture/timeline của node đó (phần sweep detector thật thuộc A3-039, không làm thay). Lịch sử review/A lần2 giữ nguyên (chỉ có con trỏ đã bị thay thế). | RED của node vừa chuyển đổi nay đúng loại `interface` (`assert len(records) == 1 → 0 == 1`, do `records` chưa có — F06), không còn RED do test/document sai schema. Inventory giữ **58 node**; tổng file giữ **39 failed / 19 passed** (node vốn đã RED, nay RED đúng lý do). Không blocker; A3-023 mở cụm F01.2 (fixture/timeline). |
| A3-023 | IMPLEMENTED | `M` (mục kiểm kê mới) / `L` | Kiểm kê **10 đường dựng nến** trong file acceptance + helper probe với 6 cột (factory, caller/node, timeframe, bước timestamp, nơi validate, positive/negative) tại [Danh sách candle factory/caller](smc-task-72-acceptance-matrix.md#danh-sách-candle-factorycaller--a3-023); cập nhật hàng đối chiếu A3-003 trỏ tới mục này. Kết luận: (a) **mọi** đường đều validate đúng timeframe (trực tiếp hoặc qua `_probe.candles`) — không thấy đường thiếu validator; (b) **một** đường sai cadence: local `run()` của `test_r72_07_equal_and_outside_buffer_buy_sell` (H1 + `timedelta(days=i)`) ⇒ A3-028; (c) **không** có fixture invalid-data cố ý trong file acceptance (không có ca kỳ vọng validator thất bại). Command/kết quả ở §A3.26. | Chỉ ghi tài liệu vào `M` + `L`; **không sửa test, `core/`, probe, R56/golden** nên hash file acceptance không đổi (`0D1E96D5…`). Không kết luận thay A3-027/A3-028 — chỉ cung cấp đầu vào. | Không có RED mới (docs-only). Inventory **58 node**, tổng file **39 failed / 19 passed** không đổi. Không blocker; A3-024 dùng danh sách này để xác minh `_terminal_candles`. |
| A3-024 | IMPLEMENTED | `T` / `L` / `M` | Xác minh **BUY exit candle** bằng số học độc lập trên chính `rows` (không gọi hàm production để tự sinh expected): zone `[100,110]`, `tick=0.1`, `ATR=1` ⇒ tolerance `max(1*tick, 0.05*ATR)=0.1`, ngưỡng reaction `0.25*ATR=0.25`; exit `(110.2,110.22,110.15,110.2)` có `low 110.15 > 110.1` (ngoài vùng mở rộng) và `close−110 = 0.2 < 0.25` (chưa đạt reaction); OHLC hợp lệ (validator trong factory). Fixture **đã đúng theo review ⇒ không ghi đè**; chỉ thêm 2 assert bất biến vào nhánh BUY của `_terminal_candles` (kèm comment A3-024) để chặn hồi quy về mẫu `110.5`/giá trị sai. Command/kết quả ở §A3.27; file hash mới `5CFF65276588EFAEEE5C4633205597E5E93C2AFC8DA6D08089E64EACB3EA9D84`. | Chỉ sửa test (nhánh BUY của factory) + `L`/`M`; **không** sửa `core/`, probe, R56/golden, không đổi nhánh SELL (A3-026) hay reaction candle (A3-025). Không đổi bước timestamp (D1 + `timedelta(days=…)` vốn đúng cho D1). | Không tạo RED/GREEN mới: consumer duy nhất `_terminal_lifecycle` → `test_r72_06_terminal_order_before_reaction_is_explicit` (10 node: 6 RED đã ghi — `[21]/[22]` và `reaction_cannot_cross_expiry_boundary`, 4 GREEN — `[20]` và `invalidation_precedes_expiry_and_reaction`); tổng file giữ **39 failed / 19 passed**, inventory **58 node**. `invalidation_precedes_expiry_and_reaction` GREEN nhưng expected còn yếu ⇒ A3-037 siết. |
| A3-025 | IMPLEMENTED | `T` / `L` / `M` | Xác minh **BUY reaction candle** `(112,114,111,113)` bằng số học độc lập (không qua hàm production): envelope OHLC hợp lệ (`high ≥ max(open,close)`, `low ≤ min(open,close)`); điều kiện follow-through của BUY theo code `close >= zone_high + 0.25*ATR` ⇒ `113 >= 110.25` đạt, **biên 2.75**; nến **không** phải invalidation (`close >= zone_low − buffer`). Fixture **đã đúng ⇒ giữ nguyên**; thêm 3 assert bất biến (envelope + ngưỡng reaction) vào nhánh BUY của `_terminal_candles` để "không chỉ validator pass". Command/kết quả ở §A3.28; file hash mới `4C241173B8C8E1BCB845BD0CED9158EE1300BBDCD531DB2D44F258D75EBA3A0C`. | Chỉ sửa test (nhánh BUY của factory) + `L`/`M`; không sửa `core/`, probe, R56/golden. Không đổi nhánh SELL (A3-026), không đổi vị trí `reaction_index` hay timeline (A3-030…A3-032). | Không tạo RED/GREEN mới: nhóm `test_r72_06_terminal_order_before_reaction_is_explicit` giữ nguyên 2 GREEN (`[20-buy/sell]`) / 4 RED (`[21]/[22]` — F04); tổng file **39 failed / 19 passed**, inventory **58 node**. Ghi chú: window follow-through của code là `exit_index … exit_index+3`, nên nến reaction đặt ở `reaction_index ∈ {20,21,22}` nằm trong cửa sổ khi exit ở idx20 — đây là lý do fixture sinh được reaction "trước terminal". |
| A3-026 | IMPLEMENTED | `T` / `L` / `M` | Xác minh **SELL mirror** của exit/reaction bằng số học độc lập: `exit (99.8,99.85,99.78,99.8) == mirror(110.2,110.22,110.15,110.2)` và `reaction (98,99,96,97) == mirror(112,114,111,113)` với `mirror(o,h,l,c) = (210−o, 210−l, 210−h, 210−c)` ⇒ **khớp tuyệt đối**; nghĩa đối xứng cũng đạt: exit ngoài vùng mở rộng phía dưới (`99.85 < 99.9`), `100 − close = 0.2 < 0.25` (chưa reaction), reaction `close 97 ≤ 99.75` và envelope hợp lệ. Fixture **giữ nguyên**; thêm vào nhánh SELL: 2 assert mirror + 5 assert nghĩa (envelope/ngưỡng) để việc kiểm không chỉ dựa validator. Command/kết quả ở §A3.29; file hash mới `819ED76914E1F6BAB0280533D53846C30FC9D706FE77115D6BD94DD19A5A65A2`. | Chỉ sửa test (nhánh SELL) + `L`/`M`; không sửa `core/`, probe, R56/golden. **Không** đổi candle touch `rows[19]` dù phát hiện không phải mirror tuyệt đối — ngoài phạm vi hàng (chỉ exit/reaction) và sửa sẽ đổi fixture của nhóm R72-06; đã ghi vào `M` §CHƯA RÕ cho A3-080/A3-063 quyết định. | **Phát hiện mới (không phải RED):** candle touch SELL `(101,105,99,102)` lệch mirror tuyệt đối `(101,105,100,101)` ở `low`/`close` 1 đơn vị — **tương đương về nghĩa** (cả hai overlap zone và không invalidate) nên không đổi. Không tạo RED/GREEN mới: nhóm R72-06 giữ 2 GREEN / 4 RED; tổng file **39 failed / 19 passed**, inventory **58 node**. |
| A3-027 | IMPLEMENTED | `M` / `L` (không cần sửa `T`) | Rà lại theo tiêu chí "validate **đúng timeframe** và **trước evaluator**" bằng script phân tích thứ tự trong file acceptance + đọc probe: **6** call site validator tường minh trong file acceptance (dòng 131 `"D1"` `_terminal_candles`; 333 `"H1"` 5 fixture task59/60/62/63/65; 678 `"D1"`; 722 `"D1"`; 1000 `"H1"` local `run()`; 1074 `"H1"` gate56) và **2** trong probe (dòng 39 `"D1" if hours == 24 else "H1"`, dòng 187 `"H1"`); các đường còn lại đi qua `_probe.candles`/`_terminal_candles` ⇒ validate xong mới tới evaluator (`analyze_zone_lifecycle`/`enrich_zones`/`detect_order_block_candidates`/`detect_liquidity_pools`/`detect_liquidity_sweeps`/`_attach_zone_sweep_links`). Command/kết quả ở §A3.30. | **Không sửa gì** (đúng ⇒ xác minh): không thêm validator, không nới call nào, không đổi timeframe. Không sửa `core/`, probe, R56/golden. | **Không tìm thấy đường thiếu validator** ⇒ không cần bổ sung. Cũng xác nhận lại: không call nào gọi `validate_smc_candles` thiếu timeframe, và **không** có fixture invalid-data cố ý bị validate như positive. Hash file acceptance **không đổi** (`819ED769…`); tổng file **39 failed / 19 passed**, inventory **58 node**. |
| A3-028 | IMPLEMENTED | `T` / `L` / `M` | Sửa cadence của fixture H1: local `run()` trong `test_r72_07_equal_and_outside_buffer_buy_sell` đổi `start + timedelta(days=i)` → **`timedelta(hours=i)`** (H1 = bước giờ) + comment A3-028; thêm assert bất biến `values[1].time - values[0].time == timedelta(hours=1)` để chặn hồi quy. Kiểm 3 đường D1 còn lại (`_terminal_candles` dòng 126, R72-05 dòng 676, R72-06 dòng 720) — đã dùng bước **ngày** đúng timeframe ⇒ **giữ nguyên**. Command/kết quả ở §A3.31; file hash mới `58D6F6377391231F76E6F492EAC42239E6621D04E552DB2A7BA4DA1ED0099940`. | Chỉ sửa test (timestamps + 1 assert) + `M`/`L`; không sửa `core/`, probe, R56/golden. Không đổi giá trị OHLC, ngưỡng, `tick`/`ATR` hay assertion nghiệp vụ. | Thay đổi **trung tính hành vi** cho fixture này (assertion chỉ phụ thuộc buffer `0.1`/`broken`; `_age_anchor_index` với `available_at=None` trả `safe_origin` nên không phụ thuộc timestamp): node giữ **2 PASSED** (buy/sell) và tổng file giữ **39 failed / 19 passed**, inventory **58 node**. Không còn đường sai cadence trong file acceptance. |
| A3-029 | IMPLEMENTED | `M` (mục timeline mới) / `L` | Ghi [Timeline D1 terminal — A3-029](smc-task-72-acceptance-matrix.md#timeline-d1-terminal--a3-029) vào `M`: fixture `_terminal_candles` 23 nến D1 (`time = 2026-09-01T00:00Z + index ngày`), consumer `_terminal_lifecycle` (`origin_index=0`, không `available_at`); quy tắc anchor `_age_anchor_index` (`available_at=None` ⇒ anchor = origin ⇒ `age(i)=i`, và cảnh báo không mặc định index=age khi có `available_at`); lifetime `_STALE_AFTER_BARS["D1"]=20` ⇒ `age>20`; bảng **index / age / open / close D1 / vai trò** cho index 19–22 (age20 index20 chưa terminal; **terminal index21**, `expired_at = 2026-09-23T00:00Z`; index22 sau terminal); thêm con trỏ tới mục này ở 2 hàng đối chiếu A3-003 (invalidation age21 → A3-037; reaction trước/đúng/sau terminal → A3-030…036). Command/kết quả ở §A3.32. | Chỉ ghi tài liệu vào `M` + `L`; **không sửa `core/`, probe, test, R56/golden** (hash file acceptance không đổi `58D6F637…`). Expected tính từ quy tắc (lifetime/anchor/close) chứ không lấy output production. | Không tạo RED/GREEN mới. Kiểm chứng (chỉ để xác nhận): `_terminal_lifecycle` cho `reaction_index` 20/21/22 đều trả `expiry_index=21`, `expired_at=2026-09-23T00:00+00:00`, `age_bars=22` — khớp bảng; khác biệt duy nhất là `reacted_at` hiện **có** giá trị ở index 21/22 ⇒ đúng gap **F04** (không phải lỗi fixture). Tổng file giữ **39 failed / 19 passed**, inventory **58 node**. |
| A3-030 | IMPLEMENTED | `T` / `L` / `M` | Khóa D1 reaction **trước** terminal trong nhánh `reaction_index == 20` của `test_r72_06_terminal_order_before_reaction_is_explicit`: mở rộng helper test-local `_terminal_lifecycle(side, reaction_index, candles=None)` để chạy được **prefix 21 nến** (kết thúc đúng candle reaction idx20); assert `reacted_at == "2026-09-22T00:00:00+00:00"` (tính độc lập: `2026-09-01 + 21 ngày` = close của nến idx20) cho **cả prefix và full**, `completed_reacted` cho cả hai, và `prefix.lifecycle_expired is False` ⇒ append candle terminal **không đổi thời điểm/lịch sử**. Command/kết quả ở §A3.33; file hash mới `B2390C267C5D2FF29FAD53D9819DFD0961712750810DBD935B1E320799A732B9`. | Chỉ sửa test (thêm tham số `candles` cho helper + siết nhánh [20]) + `M`/`L`; không sửa `core/`, probe, R56/golden. Không đụng nhánh `[21]/[22]` (A3-031/A3-032). | Không tạo RED/GREEN mới: `[20-buy]`/`[20-sell]` vẫn **PASSED** (nay siết chặt hơn), `[21]/[22]` vẫn RED (F04) — tổng file **39 failed / 19 passed**, inventory **58 node**. Probe xác nhận prefix(21) và full(23) đều `reacted_at=2026-09-22T00:00:00+00:00`, `completed_reacted`. |
| A3-031 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Khóa nhánh `else` (reaction tại/sau terminal, phủ `[21]` và `[22]`): thêm bằng chứng **vùng thật sự được vào/rời trước terminal** (`visit.entered_at == 2026-09-21T00:00Z` = close idx19; `visit.exited_at == 2026-09-22T00:00Z` = close idx20; `bars_spent_inside >= 1`) ⇒ "không reaction" không thể pass vì chưa từng vào vùng; và khóa **terminal timestamp/index** (`state.expiry_index == 21`, `state.expired_at == 2026-09-23T00:00Z` = close idx21) thay vì chỉ `lifecycle_expired is True`. Expected tính độc lập (`start + N ngày` + D1 close = open + 1 ngày), khớp bảng §A3-029. Command/kết quả ở §A3.34; file hash mới `EA9DFE2BBA94F29451A494FC3BD075E7F0050CCE98E3C5C991736816D8E132A9`. | Chỉ sửa test (nhánh `else`) + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi nhánh `[20]`. Vì `[21]` và `[22]` dùng chung nhánh nên phần "visit/history trước terminal còn nguyên" của **A3-032** đã được phủ một phần (entered/exited/state) — A3-032 xác minh lại và chỉ thêm nếu còn thiếu. | RED vẫn đúng loại `implementation` (F04) và **chỉ còn ở 2 assert cuối** (`reacted_at is None`, `completed_unreacted`): mọi assert mới (entry/exit/bars, `expiry_index==21`, `expired_at`) **PASS** ⇒ fixture + terminal timestamp đã đúng, gap là reaction được ghi tại/sau terminal (`reacted_at=2026-09-23` cho [21], `2026-09-24` cho [22]). 4 node `[21]/[22]` RED; tổng file giữ **39 failed / 19 passed**, inventory **58 node**. |
| A3-032 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Thêm vào nhánh `else` phép so **bỏ candle sau terminal**: `trimmed = _terminal_lifecycle(side, ri, candles=_terminal_candles(side, ri)[:22])` và `assert trimmed.visits[0] == visit` ⇒ candle sau terminal **không** được đổi visit/history (khóa trực tiếp "visit/history trước terminal còn nguyên"). Command/kết quả ở §A3.35; file hash mới `6A66F7090D0D64938F88E564693C81216636AD15C611C0FB2F6CA97203F6CFE6`. | Chỉ sửa test (1 khối assert trong nhánh `else`, dùng lại tham số `candles` thêm ở A3-030) + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi nhánh `[20]`. | Probe: `ri=21` hai bên **bằng nhau** (assert này PASS hôm nay); `ri=22` hiện **khác** đúng 2 field `reacted_at`/`visit_state` (`2026-09-24`/`completed_reacted` so với `None`/`completed_unreacted`) ⇒ chính là gap **F04** được phơi ra ở assert mới. Trong lượt RED, assert mới chưa chạy tới (assert `reacted_at is None` phía trên fail trước) — đã kiểm độc lập bằng probe; tổng file giữ **39 failed / 19 passed**, inventory **58 node**. |
| A3-033 | IMPLEMENTED | `M` (mục timeline H4 mới) / `L` | Ghi [Timeline H4 terminal — A3-033](smc-task-72-acceptance-matrix.md#timeline-h4-terminal--a3-033): hằng số `_STALE_AFTER_BARS["H4"]=30` + `SMC_TIMEFRAME_INTERVALS["H4"]=14400s (4h)`; suy ra từ quy tắc D1 (touch `L−1`, exit `L`, terminal `L+1`, sau `L+2`, tổng `L+3` nến) ⇒ **age30 = index 30 chưa terminal, terminal = index 31**, sau terminal = index 32, cần **33 nến** bước 4h; bảng index/age/open/close/role (close = open + 4h); nêu **close cutoff** (đánh giá tại candle close; cutoff bằng mốc terminal là terminal — A-D04) và **follow-through window** `exit_index … exit_index+3` với ngưỡng `0.25*ATR` + invalidation ưu tiên; đối chiếu chéo D1 (`L=20` ⇒ 23 nến) khớp đúng fixture thật. Thêm con trỏ ở hàng đối chiếu A3-003. | Chỉ ghi tài liệu vào `M` + `L`; **không sửa `core/`, probe, test, R56/golden** (hash file acceptance không đổi `6A66F709…`). Không thêm quy tắc/ngưỡng mới — chỉ áp hằng số + quy tắc A-D04/A-D05 đã duyệt cho H4. Fixture H4 là **đề xuất** cho A3-034…036 (các mã đó viết node). | Không có RED/GREEN mới (docs-only). Tổng file giữ **39 failed / 19 passed**, inventory **58 node**. Ghi chú cho A3-034…036: `H4: không có node nào` (theo hàng đối chiếu A3-003) nên ba mã này phải **viết mới** node H4 theo timeline này. |
| A3-034 | IMPLEMENTED | `T` / `L` / `M` | Viết **H4 fixture** `_h4_terminal_candles(side, reaction_index)` + `_h4_terminal_lifecycle`: 33 nến bước **4h** (start `2026-09-01T00:00Z`), touch idx29, exit idx30, terminal idx31, sau idx32; assert bất biến geometry BUY/SELL + cadence 4h + `validate_smc_candles(values, "H4")`. Node mới `test_r72_06_h4_reaction_before_terminal_is_retained[buy/sell]`: `entered_at == 2026-09-06T00:00Z` (close idx29), `exited_at == reacted_at == 2026-09-06T04:00Z` (close idx30 — exit + reaction cùng close, chưa terminal), `completed_reacted`, `bars_spent_inside ≥ 1`, `lifecycle_expired is True`, `expiry_index == 31`, `expired_at == 2026-09-06T08:00Z` (close idx31). Expected tính từ quy ước fixture (`start + (4h·i) + 4h`). Command/kết quả ở §A3.37; file hash mới `885E87960999556326EC770AFA26D1C17C606E65D220C62FEB9D09AF3BDB5C9A`. | Thêm factory + node mới vào test, cập nhật `M` (2 hàng tracking mới, R72-06 10→12 node, inventory 58→60, hàng đối chiếu A3-003 "H4 đã có node") + `L`; không sửa `core/`, probe, R56/golden. | **GREEN cả 2 side** (hành vi H4 "reaction trước terminal" đã đúng — đối ứng D1 `[20]`); inventory **58 → 60 node**, passed **19 → 21**, failed giữ **39**. Factory này sẽ được A3-035/A3-036 dùng lại cho "đúng terminal"/"sau terminal". |
| A3-035 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Node mới `test_r72_06_h4_reaction_at_terminal_is_blocked[buy/sell]` dùng lại `_h4_terminal_candles(side, 31)` (reaction đặt đúng candle terminal): precondition `expiry_index == 31`; entry/exit/bars để chứng minh vùng thật sự được vào; `lifecycle_expired is True`, `expired_at == 2026-09-06T08:00Z` (terminal evidence rõ); contract `reacted_at is None` + `completed_unreacted`. Command/kết quả ở §A3.38; file hash mới `8EB33A305EEA34002ADB7A5F99F8439DAC89B22B46EE89DF4C3C955954557FC4`. | Chỉ thêm node mới + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi fixture (chỉ truyền `reaction_index = 31`). | RED cả 2 side đúng loại `implementation` (F04): fail **chỉ ở assert `reacted_at is None`** — mọi assert trước đó (entry/exit/bars, `expiry_index == 31`, `expired_at`) **PASS** ⇒ terminal evidence đúng, gap là reaction được tạo tại chính candle terminal (`reacted_at = 2026-09-06T08:00Z`). Inventory **60 → 62 node**, failed **39 → 41**, passed giữ **21**. |
| A3-036 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Node mới `test_r72_06_h4_reaction_after_terminal_is_blocked[buy/sell]` dùng `_h4_terminal_candles(side, 32)` (reaction **sau** terminal): precondition `expiry_index == 31`; entry/exit/bars; `lifecycle_expired is True`, `expired_at == 2026-09-06T08:00Z`; contract `reacted_at is None` + `completed_unreacted`; thêm so **bỏ candle sau terminal** (`[:32]`): `trimmed.visits[0] == visit` ⇒ không mất lịch sử trước đó. Mở rộng helper `_h4_terminal_lifecycle(side, reaction_index, candles=None)` (additive). Command/kết quả ở §A3.39; file hash mới `5E330EE7B6BD8FF99817D13E7BB4BA3BB93EBB790070ECD1C1F8FA7D4D15628B`. | Chỉ thêm node mới + tham số `candles` cho helper H4 + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi fixture. | RED cả 2 side đúng loại `implementation` (F04): fail ở assert `reacted_at is None` (`reacted_at = 2026-09-06T12:00Z` = close idx32 — candle sau terminal tạo reaction); mọi assert trước đó **PASS**. Probe thêm: `trimmed` (bỏ idx32) cho `reacted=None`/`completed_unreacted`, **khác** full ở 2 field ⇒ assert so-sánh sẽ chặn hồi quy sau khi F04 sửa. Inventory **62 → 64 node**, failed **41 → 43**, passed giữ **21**. |
| A3-037 | IMPLEMENTED | `T` / `L` / `M` | Sửa `test_r72_06_invalidation_precedes_expiry_and_reaction`: chuyển invalidation từ **row20 (age20)** sang **row21 (age21 = candle hết lifetime D1)**, thêm exit row ở idx20 để mở follow-through window `20…23`; assert `invalidation_index == 21`, `invalidated_at == 2026-09-23T00:00Z`, `lifecycle_broken is True`, **`expiry_index is None`**, **`lifecycle_expired is False`** (invalidation thắng expiry cùng candle), visit `entered_at == 2026-09-21T00:00Z`/`exited_at == 2026-09-22T00:00Z`/`completed_unreacted`/`reacted_at is None`. Không dựng close vừa phá distal vừa phản ứng ngược hướng. Command/kết quả ở §A3.40; file hash mới `7D6D92D42F57710FB736B2A06467E85F50DF2D15E15250A1634A205F8E1903F1`. | Chỉ sửa test (fixture + assertion của node đó) + `M`/`L`; không sửa `core/`, probe, R56/golden. Không đổi số node/inventory. | Node **PASSED cả 2 side** sau khi sửa (hành vi invalidation-ưu-tiên đã đúng; trước đây node cũng GREEN nhưng *expected yếu* — nay đã khóa timestamp/index/priority). Tổng file giữ **43 failed / 21 passed**, inventory **64 node**. Probe trước khi sửa cho: `invalidation_index=21`, `invalidated_at=2026-09-23T00:00Z`, `broken=True`, `expiry_index=None`, `lifecycle_expired=False`, visit `entered 09-21/ exited 09-22/ reacted None`. |
| A3-038 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED` cho nhánh `invalid`) | `T` / `L` / `M` | Node mới `test_r72_06_terminal_state_survives_enrich_restore_enrich[terminal_kind-side]` (4 node): chuỗi `enrich_zones` → `json.dumps/loads` → `enrich_zones` lại trên **cùng fixture D1**, parameterize `terminal_kind ∈ {expired, invalid}` × `side`. `expired` dùng `_terminal_candles(side, 20)`; `invalid` dựng chuỗi touch idx19 → reaction idx20 → **invalidation idx21** (thay expiry). Assert: `zone_id` không đổi; `lifecycle_status` giữ `expired`/`invalid` ở **cả hai** lượt; `usable is False`; terminal time `2026-09-23T00:00Z` (`expired_at`+`expiry_index==21` hoặc `invalidated_at`+`invalidation_index==21`, kèm `lifecycle_expired is False` cho nhánh invalid); reaction trước terminal `2026-09-22T00:00Z` được giữ và `visits` lượt 2 **giống** lượt 1 (không reaction mới); D1 `valid is False`/`score == 0` tại cutoff `2026-09-23T00:00Z`. Command/kết quả ở §A3.41; file hash mới `21CDAB4CE068BE01DA4216213C371547DBBAFCB7E209E78CDE59BC2720F62352`. | Chỉ thêm node mới + `M`/`L`; không sửa `core/`, probe, R56/golden, không sửa fixture hiện có (chỉ tái sử dụng `_terminal_candles` + dựng chuỗi invalid inline). | **expired**: 2 PASSED (trạng thái terminal đi qua round-trip nguyên vẹn). **invalid**: 2 FAILED đúng loại `implementation` (R72-08/F03) — `assert context["lifecycle_status"] == "invalid"` nhưng nhận `'confirmed'` ⇒ projection context chưa đánh dấu vùng bị canonical lifecycle invalidate là `invalid`/unusable; mọi assert khác (zone_id, terminal time, visits giữ nguyên, D1 invalid/0) **PASS**. Inventory **64 → 68 node**, passed **21 → 23**, failed **43 → 45**. |
| A3-039 | **IMPLEMENTED** (A3R3-05; kèm `EXPECTED_IMPLEMENTATION_RED` **F06** — `records` chưa có, temporal seam PASS) | `T` / `L` / `M` | Dựng lại `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible`: đổi nến **idx1** thành `(100.3,100.5,99.5,100.3)` (excursion + reclaim thật), giữ fixture 2 source equal `100`/`100.05` với `usable_at=stamp(2)`; thêm precondition hình học (`low 99.5 < 100.025 − excursion 0.2`, `close 100.3 > 100.025`) và **gọi `detect_liquidity_sweeps`** (`lookback_bars=8`, `causal_only=True`, `tick=.1`, `ATR=1`) assert `swept_lows` đúng **idx1**, `level == 100.025`, `reclaimed_at == stamp(2) == pool_usable_at`, `swept_highs == []`. Giữ nguyên assertion pool (numeric `float` + `records` provenance). Command/kết quả ở §A3.42; file hash mới `D7CA26D339FDC45799F9D561D4C910DE0C2436B52AE2D40E240727E6DC1DED67`. | Chỉ sửa test (fixture + gọi detector) + `M`/`L`; không sửa `core/`, probe, R56/golden. Không parameterize trước/bằng/sau (thuộc A3-040/041/042) và không assert `source_swing_id` (lineage thuộc F06). | RED còn lại đúng loại `interface`: dừng ở `assert len(records) == 1 → 0 == 1` (`records` chưa có — F06); các phần mới (geometry + detector) **verified độc lập bằng probe**: `swept_lows indices [1]`, `level == 100.025`, `reclaimed_at = 2026-09-01T02:00:00+00:00 == usable_at`, `swept_highs []` — chưa chạy tới trong lượt RED (fail-fast), đã ghi rõ. Tổng file giữ **45 failed / 23 passed**, inventory **68 node**. → **A3-039 (2026-09-11)** — bỏ khóa toàn bộ `swept_lows` và phần tử `[0]`; nay **lọc target event theo level equal pool + candle `index 1`**, đòi **tồn tại** target event và có `reclaimed_at == pool_usable_at == stamp(2)`. Không dùng vị trí list, không assert tổng số `swept_lows`, không pool priority/dedupe. Block canonical `records` chuyển xuống **sau** temporal seam để A3-039/041 thực sự chạy; node cuối cùng RED **F06** (thiếu `records`), không phải lỗi temporal. Bằng chứng: §A3.112. |
| A3-040 | **IMPLEMENTED** (A3R3-05; **GREEN** — oracle không còn khóa priority/cardinality) | `T` / `L` / `M` | Node mới `test_r72_01_equal_pool_usable_before_sweep_close_is_accepted`: cùng fixture equal pool như A3-039 nhưng nến được xét ở **idx2** (`(100.3,100.5,99.5,100.3)`) ⇒ `pool_usable_at = stamp(2)` **<** event close `stamp(3)` (usable **trước** sweep close). Assert precondition (2 source confirmed/usable/non-provisional, `pool_usable_at == stamp(2) < stamp(3)`, geometry excursion/reclaim) và **nhận sweep** với đủ **source time + event time**: `swept_lows` đúng **idx2**, `kind == "swept_low"`, `side == "buy"`, `level == 100.025`, `time == stamp(2)` (open), `reclaimed_at == stamp(3)` (close), `excursion_buffer ≈ 0.2`, `swept_highs == []`. Command/kết quả ở §A3.43; file hash mới `DD1FEC36513BC503DDEB3A2A20A2CE3F95A71AB491940554FD6A620A8205F7DB`. | Chỉ thêm node mới + `M`/`L`; không sửa `core/`, probe, R56/golden, fixture của A3-039 giữ nguyên. Không assert `records` ở node này (để giữ vai trò **positive control** xanh cho cặp reject của A3-042). | Node **PASSED** (positive side của gate A-D01 hiện đã đúng và nay được khóa bằng source/event time). Inventory **68 → 69 node**, passed **23 → 24**, failed giữ **45**. Ghi chú: gate `usable_at <= reclaimed_at` **chưa** được implement (F07) nên positive này pass độc lập với gate — A3-042 sẽ là cặp reject RED tương ứng. → **A3-040 (2026-09-11):** bỏ khóa toàn list/`[0]`, lọc **target event theo level + `index 2`** và đòi khớp `kind`/`side`/`time stamp(2)`/`reclaimed_at stamp(3)`/`excursion_buffer`; thêm precondition equal pool tồn tại + level khác hai source level. Không assert tổng số `swept_lows`/pool priority/dedupe; không thêm `records`. **GREEN.** Bằng chứng: §A3.113. |
| A3-041 | **IMPLEMENTED** (A3R3-05; kèm `EXPECTED_IMPLEMENTATION_RED` **F06** — `records` chưa có, temporal seam PASS) | `T` / `L` / `M` | **Xác minh + ghi rõ** ca biên "equal" (không sửa hành vi): node `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` đã khóa `pool_usable_at == reclaimed_at == stamp(2)` và sweep vẫn **được chấp nhận** (`swept_lows` idx1, `reclaimed_at == pool_usable_at`) theo A-D01 inclusive; thêm vào **docstring** và comment tại chỗ assertion equality ghi rõ đây là **temporal seam synthetic** (`usable_at` do fixture khai, ca này chứng minh contract cửa sổ bao gồm chứ không chứng minh pivot producer — ca end-to-end là **A3-044**). Cập nhật `M` (hàng tracking + hàng đối chiếu A3-003). Command/kết quả ở §A3.44; file hash mới `F4C0AFACF3A678DD3F7CAB103FDF8903B1C92E6D935F191B4CCF2D4386DED118`. | Chỉ sửa **comment/docstring** + `M`/`L`; không đổi assertion, không sửa `core/`, probe, R56/golden. | Không đổi RED/GREEN: node vẫn RED đúng loại `interface` (`records` chưa có — F06), node "trước close" (A3-040) vẫn PASSED; tổng file giữ **45 failed / 24 passed**, inventory **69 node**. → **A3-041 (2026-09-11)** — equality `usable_at == reclaimed_at` được chấp nhận, nay khóa bằng **target event** (lọc theo level + candle `index 1`) chứ không qua toàn list/`[0]`; `pool_usable_at` tính **từ fixture** và có precondition `pool_usable_at == usable_at == stamp(2)`. Vẫn ghi rõ đây là **temporal seam synthetic**. Bằng chứng: §A3.112. |
| A3-042 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Node mới `test_r72_01_source_usable_after_sweep_close_is_rejected[buy/sell]` (2 node): **cùng geometry excursion/reclaim như control A3-040** (BUY nến idx2 `(100.3,100.5,99.5,100.3)`; SELL dùng rows buy-shaped `_probe.candles(..., "sell")` mirror quanh 210 ⇒ nến `(109.7,110.5,109.5,109.7)`, pool `equal_highs` `110`/`109.95` = `109.975`) nhưng 2 source chỉ usable/confirmed tại **`stamp(4)`**; precondition assert `pool_usable_at == stamp(4) > event_close == stamp(3)` + geometry đúng phía; contract: `swept_*` phải `[]` (nguồn tương lai không được dùng). Command/kết quả ở §A3.45; file hash mới `F725A989B19748C70A7D82458B98FD7A4CD0C25CF9CF3F79BC87271FF3C677F9`. | Chỉ thêm node mới + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi fixture của A3-039/040/041. | RED cả 2 side đúng loại `implementation` (**F07** — gate A-D01 `usable_at <= reclaimed_at` chưa được implement): fail ở `assert sweeps[tested] == []` nhưng detector trả sweep tại idx2 ⇒ nguồn tương lai **đang** được dùng; mọi assert precondition (source hợp lệ, usable sau close, geometry) **PASS** ⇒ không phải fixture defect. Kèm sanity `sweep_candle.time == stamp(2)`. Inventory **69 → 71 node**, failed **45 → 47**, passed giữ **24**. |
| A3-043 | **IMPLEMENTED** (A3R3-05; lượt A3-043/a + /b — /a `EXPECTED_IMPLEMENTATION_RED` **F07**, /b **GREEN**) | `T` / `L` / `M` | 2 node mới: (a) `test_r72_01_equal_pool_usable_time_is_max_of_both_sources` — 2 source equal cùng pool nhưng usable/confirmed **khác nhau** (`source-a = stamp(1)`, `source-b = stamp(3)`), nến idx1 (close `stamp(2)`) nằm **giữa** hai mốc ⇒ assert `pool_usable_at == max == stamp(3) > event close` và `swept_* == []` (luật max, không chỉ source đầu); (b) `test_r72_01_equal_pool_without_usable_source_does_not_exist` — `source-b.usable = False` ⇒ assert `equal_lows == []` và `swing_lows == [100.0]` (chỉ còn level của source hợp lệ). Command/kết quả ở §A3.46; file hash mới `0784F871D2719A734231F328A2BE49673AFFEC987D6F8580126170052B9FA82D`. | Chỉ thêm 2 node + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi fixture các mã trước. Không assert `kind` của sweep hay `records` ở ca (b) để tránh khoá tên enum/câu hỏi mở A3-005. | (a) **RED** đúng loại `implementation` (F07): `assert [{'depth': …, 'index': 1, …}] == []` ⇒ chỉ dùng mốc source-a (`stamp(1)`) là đủ để detector nhận, tức luật **max** chưa được áp. (b) **PASSED** (source không usable bị loại khỏi projection nên không có equal pool). Inventory **71 → 73 node**, failed **47 → 48**, passed **24 → 25**. → **A3-043/a (2026-09-11):** bỏ `assert sweeps["swept_lows"] == []` (quá rộng — cấm oan single-source sweep hợp lệ), thay bằng lọc theo **đúng level equal pool** rồi assert rỗng; thêm precondition `expected_level not in {source_a.level, source_b.level}`. **Không** thêm `records` canonical (F06 che RED F07), **không** thêm single-source control (A3-043/b), không assert tổng số sweep/pool priority/dedupe. Node vẫn **RED đúng F07**, lỗi ở assertion target equal pool. Bằng chứng: §A3.110. → **A3-043/b (2026-09-11):** node mới `test_r72_01_single_source_pool_usable_before_sweep_close_is_accepted` — **cùng geometry /a**, chỉ khai một low source `source-a` (level `100.0`, usable/confirmed `stamp(1)`); `equal_lows == []`, `swing_lows == [100.0]`; lọc event theo **level** rồi đòi event khớp `index 1`/`reclaimed_at stamp(2)`/`source_swing_id "source-a"`. **GREEN** ⇒ single-source sweep hợp lệ, negative /a không được cấm toàn bộ `swept_lows`. Không assert tổng số `swept_lows`/pool priority/dedupe; không dùng `records`. Bằng chứng: §A3.111. |
| A3-044 | IMPLEMENTED | `T` / `L` / `M` | Node mới `test_r72_01_actual_swing_producer_feeds_pool_and_sweep` (end-to-end, **tách** khỏi fixture synthetic 039–043): 12 nến H1 OHLC thật → `external_swing_points(symbol="EURUSD", timeframe="H1", lookback=2, equal_tolerance=0.0)` phát **một** swing low idx4 (`level 99.5`, `pivot_time = stamp(4)`, `confirmed_at = stamp(7)` = close idx4+lookback, `confirmed/usable True`, non-provisional, có `swing_id`) → `detect_liquidity_pools` cho `swing_lows == [99.5]` → nến idx10 `(100,100.6,99.0,100.2)` sweep; assert sweep đúng **idx10**, `level == 99.5`, `reclaimed_at == stamp(11)`, **`source_swing_id == swing["swing_id"]`** (lineage về swing thật) và `confirmed_at (stamp 7) < reclaimed_at (stamp 11)`. Command/kết quả ở §A3.47; file hash mới `01F7EEB3E180084F597B724AFD8661813C9A9AB56420606939B6D0C899531655`. | Thêm node + **1 import mới** `external_swing_points` vào khối `from core.smc_context import (...)` + `M`/`L`; không sửa `core/`, probe, R56/golden. Expected tính từ `rows` + contract causal của producer (`pivot_time` = open nến pivot, `confirmed_at` = close nến pivot+lookback), không lấy từ output pool/sweep. | Node **PASSED** — chuỗi producer→pool→sweep chạy đúng đầu-cuối, gồm cả lineage `source_swing_id` (điểm mà fixture equal-pool synthetic **không** có, vì level là trung bình). Inventory **73 → 74 node**, passed **25 → 26**, failed giữ **48**. |
| A3-045 | IMPLEMENTED | `T` / `L` / `M` | Lượt 1 của `test_r72_04_same_pool_observation_cannot_bypass_consumption` được **xác minh tường minh**: assert lineage trên claim (`pool_id == "pool-1"`, `source_ids == ["swing-1"]`, `reclaimed_at == stamp(11)`, `setup_available_at == stamp(13)`); sau `assign_sweep_ownership(..., history_complete=True)`: `reason_codes == []` (history đầy đủ, không fail-closed), `owner_setup_id == "original"` (early owner), `assignment_id` không rỗng, `claim_eligible_at == max(stamp(11), stamp(13)) == stamp(13)` và `assigned_at == claim_eligible_at` (A-D02), và history qua **JSON round-trip** (`json.loads(json.dumps(...))`) nguyên vẹn. Lượt 2 (observation mới) **giữ nguyên**, thuộc A3-046. Command/kết quả ở §A3.48; file hash mới `BACFE1E7C7F3F16C6D1B75A114AA62DAE0CAFC50C888618118D4EA21FDF4FC99`. | Chỉ sửa lượt 1 của test + `M`/`L`; không sửa `core/`, probe, R56/golden. Không đụng lượt 2 (A3-046), không thêm node nên inventory không đổi. | Node **PASSED** (các assert mới đều đúng với hành vi hiện tại). Không đổi RED/GREEN: tổng file giữ **48 failed / 26 passed**, inventory **74 node**. Ghi chú: lượt 2 hiện vẫn "pass trivial" (hai claim cùng `sweep_id`/`reclaimed_at`) ⇒ **A3-046** phải đổi observation sweep ID/time/rolling index. |
| A3-046 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Lượt 2 nay là **observation MỚI thật**: `sweep_id="sweep-later"`, `reclaimed_at=stamp(17)`, `index=99` (rolling index), **giữ** `pool_id="pool-1"`/`source_ids=["swing-1"]`; lượt 1 thêm `index=7` để precondition so được. Assert precondition (cùng pool/source identity, khác sweep ID/time/index) và contract: `assignments["sweep-later"]["owner_setup_id"] == "original"` **và** `assignment_id == initial["assignment_id"]`, claim late `contribution_applied is False`. Command/kết quả ở §A3.49; file hash mới `25348D5D7A58199541040B0CC07CD5CD339C4C1E01C2F9F53239F86B0866AEA1`. | Chỉ sửa lượt 2 của test (+ `index` ở lượt 1) + `M`/`L`; không sửa `core/`, probe, R56/golden. Không thêm node. | Node chuyển từ **"pass trivial"** sang **RED** đúng loại `implementation` (**F10**): `assert result["assignments"]["sweep-later"]["owner_setup_id"] == "original"` → nhận `'later'` ⇒ hiện history khớp theo **sweep ID**, nên observation mới của cùng causal pool né được consumed. Inventory giữ **74 node**, failed **48 → 49**, passed **26 → 25**. |
| A3-047 | IMPLEMENTED | `T` / `L` / `M` | Thêm **control pool mới thật** vào cùng node (sau lượt A3-046): claim `new-setup/new-child` với `sweep_id="sweep-new"`, `reclaimed_at=stamp(21)`, `index=199`, `pool_id="pool-2"`, `source_ids=["swing-2"]`, dùng cùng `restored_history`; precondition assert `pool_id`/`source_ids`/`sweep_id` **khác** lượt 1 và hai mốc claim hợp lệ (`stamp(21)`/`stamp(19)`); contract: `reason_codes == []`, `assignments["sweep-new"]["owner_setup_id"] == "new-setup"`, `contribution_applied is True` (không bị khóa nhầm bởi pool cũ). Command/kết quả ở §A3.50; file hash mới `BB0D1F07749BCE693F11AABC8511DB8AFEF5918709DB5E77E8EE7E0E685D8704`. | Chỉ thêm khối control vào test + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi lượt 1/2. Không thêm node. | Phần control **PASS** khi chạy riêng (probe: owner `new-setup`, `contribution_applied True`, `reason_codes []`) nhưng **chưa chạy tới** trong lượt RED hiện tại vì assert A3-046 phía trên fail trước — đã ghi rõ. Node vẫn RED ở lượt A3-046; tổng file giữ **49 failed / 25 passed**, inventory **74 node**. |
| A3-048 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Node mới `test_r72_04_conflicting_assignment_history_fails_closed`: claim `late/child` **đầy đủ canonical** (`reclaimed_at=stamp(11)`, `setup_available_at=stamp(15)`, `pool_id="pool-1"`, `source_ids=["swing-1"]`, `index=3`) + history mâu thuẫn `{"sweep": {"sweep_id": "sweep", "owner_setup_id": "original"}}` (thiếu `assignment_id`/timestamps); assert **fail closed**: `assignments == {}` và `reason_codes` không rỗng (không khoá chuỗi reason vì chưa được review chốt). Command/kết quả ở §A3.51; file hash mới `5C372D0A5DF646FC6A322E670DB220ECD3D3051A21D49959BBF5E953BDD3A087`. | Chỉ thêm node mới + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi các node khác. | RED đúng loại `implementation` (**F10**): `assert result["assignments"] == {}` → nhận `{'sweep': {owner 'late', assignment_id mới 'smca-30bb697d…', contribution_applied True}}` ⇒ history mâu thuẫn bị **bỏ qua âm thầm** và sweep được cấp lại owner, `reason_codes == []`. Precondition (claim đủ mốc + lineage) **PASS** ⇒ không fail vì thiếu fixture timestamp. Inventory **74 → 75 node**, failed **49 → 50**, passed giữ **25**. |
| A3-049 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Đổi fixture `test_r72_05_cutoff_equal_invalidated_at_is_terminal` từ **3 nến** (outside → touch → invalidation, **không** có reaction) sang **4 nến**: outside → touch `(105,111,105,108)`/`(101,105,99,102)` → **exit+reaction** `(112,114,111,113)`/`(98,99,96,97)` → invalidation `(99,100,98,99)`/`(111,112,109,111)`; thêm **phase prefix positive (A3-049)**: `analyze_zone_lifecycle(values[:3])` → visit `completed_reacted`, `reacted_at == 2026-09-04T00:00Z` (close nến idx2), rồi `build_d1_reaction_evidence(..., as_of=<close idx2>)` ⇒ `valid is True`, `score > 0`, `zone_id == "equal-terminal"`, `source_visit_id == prefix_visit.visit_id`. Phase terminal (cutoff bằng `invalidated_at`) **giữ nguyên** cho A3-050. Command/kết quả ở §A3.52; file hash mới `D899C9AB178350880F1DAD7650471B4F2ED9D10E90BFC78549B8119C518AB4F9`. | Chỉ sửa test (fixture + phase prefix) + `M`/`L`; không sửa `core/`, probe, R56/golden. Không thêm node nên inventory **không đổi**; đã xoá 1 hàng `[sell]` **trùng** do thao tác chèn (bảng R72-05 còn đúng 6 hàng, header giữ "6 node"). | **Node chuyển GREEN-nhưng-yếu → RED đúng nghĩa:** prefix positive **PASS** (reaction thật), nhưng tại `as_of == invalidated_at` consumer trả `valid=True/score=1.0` (reason `D1_REACTION_COMPLETED_REACTED`) ⇒ RED loại `implementation` (**F05**, A-D04). Tổng file **50 → 52 failed, 25 → 23 passed** (2 param của node), inventory giữ **75 node**. |
| A3-050 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Siết **phase terminal** của cùng node theo hàng A3-050: assert `state.invalidated_at == start + 4 ngày` (`2026-09-05T00:00Z`, close nến idx3), `state.visits[0].reacted_at == prefix_cutoff` (`2026-09-04T00:00Z` — reaction trước terminal **giữ nguyên**), `evidence["valid"] is False`, `evidence["score"] == 0`, và reject **không** vì thiếu reaction (`"D1_REACTION_NOT_COMPLETED_REACTED" not in evidence["reason_codes"]`). Command/kết quả ở §A3.53; file hash mới `B0667E722F28FB997DCABC49FC7F2C7A88DFD5EDB84D230078C985BA6C646040`. | Chỉ thêm assert vào phase terminal của test + `M`/`L`; không sửa `core/`, probe, R56/golden. Không thêm node. | RED vẫn đúng loại `implementation` (**F05**) và **chỉ ở assert `valid is False`**: hai assert mới phía trên (`invalidated_at == start+4d`, `reacted_at` giữ nguyên) **PASS** ⇒ terminal timestamp đúng và history không bị xoá; consumer vẫn trả `valid=True/score=1.0` tại cutoff terminal. Tổng file giữ **52 failed / 23 passed**, inventory **75 node**. |
| A3-051 | IMPLEMENTED | `T` / `L` / `M` | Node mới `test_r72_05_cutoff_equal_expired_at_is_terminal[buy/sell]` (đối ứng **expiry** của A3-049/050) trên `_terminal_candles(side, 20)` (D1 23 nến: touch idx19, **reaction idx20**, hết lifetime idx21 **không** invalidation): prefix 21 nến → visit `completed_reacted`, `reacted_at == 2026-09-22T00:00Z` (close idx20) và `build_d1_reaction_evidence(as_of=close idx20)` ⇒ `valid True`/`score > 0`; full 23 nến → `expiry_index == 21`, `expired_at == 2026-09-23T00:00Z` (close idx21), `visits[0].reacted_at` **giữ nguyên**, evidence tại `expired_at` ⇒ `valid is False`/`score == 0`, reject không vì thiếu reaction. Command/kết quả ở §A3.54; file hash mới `1F612B0DF65EF2BB3E0FDC4B0B383D8EF04DB83D1EC6841B6D7074E51FA6BC48`. | Chỉ thêm node mới + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi các node khác. Tái sử dụng `_terminal_candles` (không tạo fixture trùng). | **GREEN cả 2 side** — nhánh expiry cutoff **đã đúng** (reason `D1_REACTION_STALE`, `score 0`), tức không có gap implementation ở đường expiry; đối chiếu: nhánh **invalidation** cutoff (A3-049/050) vẫn RED (F05). Inventory **75 → 77 node**, passed **23 → 25**, failed giữ **52**. |
| A3-052 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Chuẩn hóa `test_r72_08_typed_terminal_projection_reaches_d1_consumer`: bỏ `restored = dict(terminal_zone)` và dict `zone_id="terminal-zone"`; payload nay dựng bằng **`SmcZone.from_dict({... "timeframe": "D1", "zone_id": visit.zone_id, "lifecycle_status": "invalid", "broken": True, "low": 100, "high": 110 ...}).to_dict()`** (round-trip typed thật), cutoff `stamp(96)` = **sau** reaction `stamp(72)` (assert `visit.reacted_at < cutoff`), kèm 2 assert loại trừ sai nhánh: không `D1_REACTION_NOT_COMPLETED_REACTED` (ID lệch) và không `D1_REACTION_AFTER_CUTOFF` (cutoff trước reaction). Command/kết quả ở §A3.55; file hash mới `1464470133B5644BA62EAD0696843C612DCAEF1A8BE2CAB9C3E441649587FAAD`. | Chỉ sửa test (payload/assertion của node) + `M`/`L`; không sửa `core/`, probe, R56/golden. Không thêm node. | **Node chuyển GREEN-nhưng-sai-nhánh → RED đúng loại `implementation` (F05):** trước đây pass vì ID lệch ⇒ mọi visit bị bỏ (`D1_REACTION_NOT_COMPLETED_REACTED`); nay round-trip typed khớp ID nhưng vùng canonical terminal vẫn trả `valid=True/score=1.0` tại cutoff sau reaction. Tổng file **52 → 54 failed, 25 → 23 passed** (2 param), inventory giữ **77 node**. |
| A3-053 | IMPLEMENTED | `T` / `L` / `M` | Node mới `test_r72_08_typed_d1_projection_keeps_valid_reaction[buy/sell]` (positive control cho đường typed D1): payload **không terminal** dựng bằng `SmcZone.from_dict({zone_id: visit.zone_id, direction, timeframe "D1", low 100/high 110, available_at stamp(24), lifecycle_status "confirmed", broken False, visits [visit.to_dict()]}).to_dict()`, cutoff `stamp(96)` sau reaction `stamp(72)`; assert round-trip giữ `zone_id`/`low`/`high`/`available_at`/`lifecycle_status` và **1 visit** (`visit_id`, `reacted_at`, `visit_state` khớp); evidence ⇒ `valid is True`, `score > 0`, `zone_id == visit.zone_id`, `source_visit_id == visit.visit_id`. Command/kết quả ở §A3.56; file hash mới `21538A945EAA9A8739D81B607548CEA702B710FFD79DCF2B6878E80A8621940F`. | Chỉ thêm node mới + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node A3-052. | **GREEN cả 2 side** — control chứng minh payload typed **hoạt động** cho vùng không terminal ⇒ ca terminal (A3-052/A3-054) không thể "xanh vì mọi payload typed đều fail". Inventory **77 → 79 node**, passed **23 → 25**, failed giữ **54**. |
| A3-054 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `L` / `M` | Node mới `test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[buy/sell]` (**cùng nguồn A3-053**): payload typed có `lifecycle_status "invalid"`, `broken True`, `invalidated_at stamp(96)`, `visits [visit.to_dict()]` **và** legacy `d1_reaction True`/`proximity True`; lifecycle payload = `state.to_dict()` + `{lifecycle_status "invalid", lifecycle_broken False, broken False, d1_reaction True, proximity True}` (legacy trái canonical); precondition assert canonical giữ nguyên sau round-trip và legacy keys **không** thuộc payload typed (`"d1_reaction" not in payload`, `"proximity" not in payload`); contract: `valid is False`, `score == 0`. Command/kết quả ở §A3.57; file hash mới `BF0473E1313B65B4650A1B25A76A12D8DFD0D27508ED7135C0285574F22EDD37`. | Chỉ thêm node mới + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi các node khác. | RED cả 2 side đúng loại `implementation` (**F05/F03**) và **chỉ ở `valid is False`**: mọi precondition **PASS** (typed round-trip giữ `invalid`/`broken True`/`invalidated_at`; legacy keys bị loại khỏi payload typed) nhưng consumer vẫn trả `valid=True/score=1.0` (reason `D1_REACTION_COMPLETED_REACTED`) ⇒ canonical invalid **chưa** thắng để chặn evidence hoạt động. Inventory **79 → 81 node**, failed **54 → 56**, passed giữ **25**. |
| A3-055 | IMPLEMENTED | `T` / `L` / `M` | Node mới `test_r72_08_typed_expired_projection_blocks_d1_and_keeps_history[buy/sell]`: dùng `_terminal_lifecycle(side, 20)` (reaction idx20, expiry idx21) ⇒ precondition `lifecycle_expired is True`, `expiry_index == 21`, `visit.reacted_at == stamp(21*24)`, `expired_at == stamp(22*24)`; payload typed `SmcZone.from_dict({..., lifecycle_status "expired", broken False, expired_at, visits [visit.to_dict()]}).to_dict()`; assert payload giữ **cùng `zone_id`** với visit, `lifecycle_status == "expired"`, `expired_at` khớp, 1 visit với `reacted_at` còn nguyên; evidence tại `expired_at` ⇒ `valid is False`, `score == 0`, `zone_id == visit.zone_id`. Command/kết quả ở §A3.58; file hash mới `22F9F4586AA8AD441DBDB770D6E4D0E832DC0A95179ADE140291A655ABB275B5`. | Chỉ thêm node mới + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi các node khác. Tái sử dụng `_terminal_lifecycle`/`_terminal_candles` (không tạo fixture trùng). | **GREEN cả 2 side** — đường expiry typed **đã đúng** (reason `D1_REACTION_STALE`, `score 0`) và reaction trước expiry còn trong payload; guard chống "pass bằng mismatched ID" bằng assert `payload["zone_id"] == visit.zone_id` + `evidence["zone_id"] == visit.zone_id`. Inventory **81 → 83 node**, passed **25 → 27**, failed giữ **56**. |
| A3-056 | IMPLEMENTED | `T` / `M` / `L` | Đổi tên `test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture` → **`test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke`** (không đổi hành vi/không thêm node); docstring ghi rõ phạm vi **H1 candidate smoke** và nêu bằng chứng confirmed D1 end-to-end thuộc A3-057…A3-062; thêm `assert candidate["lifecycle_status"] == "candidate"` + `assert candidate.get("confirmed") is not True` (khẳng định fixture gate56 **không** phải vùng confirmed); gỡ assertion tautology `lifecycle.to_dict()["visits"] == [visit.to_dict() for visit in lifecycle.visits]` (không thể fail — so chính serialization của nó), thay bằng comment; ghi chú `tick_size=0.1, atr_current=5.0` là do ca smoke **tự gán** (không lấy làm bằng chứng). Command/kết quả ở §A3.59; file hash mới `FD04499EA9C0764093A3FFF4B3F67CA959A287486506C29227699F90AD1C4424`. | Chỉ sửa test (tên/docstring/assertion của một node) + `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node khác. Tên cũ giữ lại trong `M` như ghi chú đổi tên (lịch sử), **không** viết lại bảng lịch sử. | **Node PASSED** (giữ nguyên trạng thái GREEN trước đó — đây là ca plumbing, không kỳ vọng RED) và 2 assert mới **PASS**, xác nhận fixture gate56 chỉ ra **candidate**. Tổng file giữ **83 node / 56 failed / 27 passed** (không đổi số so với A3-055). Không tạo gap implementation mới; phần "nguồn confirmed D1" vẫn **CÒN THIẾU** và thuộc A3-057…A3-062. |
| A3-057 | IMPLEMENTED | `T` / `M` / `L` | Fixture D1 mới `_D1_SOURCE_ROWS` (37 nến) + helper `_d1_source_candles()`/`_d1_confirmed_source()` và node `test_r72_09_d1_source_is_confirmed_by_fixture_break`: 0..32 là warm-up zigzag để `replay_smc_structure` tự bootstrap bullish từ chính swing của nó (HH bar 14 = 102.0, bar 26 = 103.0; HL bar 8 = 96.4, bar 20 = 97.8), bar 32 = base bearish (O 100.0/H 100.2/L 99.2/C 99.4), bar 33 = departure bullish (O 99.4/H 101.4/L 99.3/C 101.2 > base high), bar 34 = nến đóng 103.8 phá đỉnh swing 103.0, bar 35..36 đuôi. Precondition assert trên fixture (validator D1 sạch; departure index 33 ≥ 15 cho ATR causal; đúng 1 buy candidate tại base 32; candidate **chưa** confirmed với `available_at`/`confirmed_at`/`confirmation_event_id` = None; `departure_measurement.status == "ok"`); BOS dùng để confirm là event thật của replay: `status == "confirmed"`, `broken_level_id ==` swing high ID của fixture, `candles[34].close > 103.0`. Contract sau `confirm_order_block_candidate`: `confirmed`, `candidate is False`, `entry_eligible is False`, `available_at == confirmed_at ==` close nến 34 (`candles[34].time + timedelta(days=1)` — tính độc lập từ fixture, không đọc output), `confirmation_event_id == related_structure_event_id == event_id`, `broken_level_id ==` swing high ID, bounds `{low: 99.2, high: 100.2}` từ nến base, `original_bounds` khớp, và 12 field identity (`zone_id`/`setup_id`/`type`/`family`/`symbol`/`timeframe`/`direction`/`origin_index`/`origin_time`/`departure_end_index`/`departure_end`/`departure_source_id`) giữ nguyên; cuối cùng assert candidate đầu vào **không bị mutate**. Import thêm `confirm_order_block_candidate` (core.smc_context) và `replay_smc_structure` (core.smc_structure_replay). Command/kết quả ở §A3.60; file hash mới `5DE28DAAB5558CBFC8E555DF0CA19962FEF75D00248EA57CB8D343DBF3B51F31`. | Chỉ thêm fixture/helper/node + import vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node khác, không đổi ngưỡng. Không tự gán `confirmed` — promotion do `confirm_order_block_candidate` thực hiện. | **GREEN** (chuẩn bị, không kỳ vọng RED): đường confirmation đã đúng nên node này là **positive control** cho nguồn confirmed D1 dùng ở A3-058…A3-062. Inventory **83 → 84 node**, passed **27 → 28**, failed giữ **56**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **882 passed / 56 failed** (56 đều nằm trong file acceptance). |
| A3-058 | IMPLEMENTED | `T` / `M` / `L` | Fixture retest `_D1_RETEST_ROWS` = `_D1_SOURCE_ROWS` + 5 nến (bar 37 hạ về `(105.0,105.2,101.5,102.0)`; bar 38 vào vùng `(102.0,102.2,99.0,100.0)`; bar 39 trong vùng `(100.0,100.2,99.3,99.8)`; bar 40 thoát lên `(100.4,100.7,100.35,100.35)`; bar 41 follow-through `(100.4,101.8,100.35,101.6)`) + helper `_d1_retest_candles()` assert hình học theo metadata fixture (tolerance `max(1 tick, 0.05×ATR)`, buffer `max(2 tick, 0.10×ATR)`, threshold `0.25×ATR`: nến 34..37 không chạm vùng; bar 38 overlap đầu tiên; bar 40 thoát nhưng close < threshold; bar 41 close ≥ threshold; không nến nào đóng qua buffer) + node `test_r72_09_d1_confirmed_zone_timeline_comes_from_fixture_retest` đưa **chính** vùng confirmed của A3-057 (`_d1_confirmed_source(_D1_RETEST_ROWS)`; `tick_size=_D1_TICK_SIZE`, `atr_current=_D1_ATR_CURRENT` là metadata fixture) qua `enrich_zones(..., tf_minutes=1440, symbol/timeframe D1, tick_size=0.1)`. Expected tính từ fixture: `available_at` = close nến phá đỉnh; `entered_at`/`exited_at`/`reacted_at` = close nến 38/40/41 (mỗi close = `time + 1 ngày`). Assert: `first_retest_index == 38`, `first_retest_time == entered`, `independent_retest_count == 1`, `bars_spent_inside == 2`, `lifecycle_mitigated True`, `lifecycle_broken/stale False`, `invalidation_index`/`invalidated_at`/`expiry_index`/`expired_at` None, 1 visit `completed_reacted` với `zone_id`/`start_index 38`/`end_index 39` và 3 mốc thời gian; identity zone_id/bounds/`origin_index`/`departure_end_index`/`available_at`/`tick_size`/`atr_current` giữ nguyên. Helper `_d1_source_candles(rows=None)`/`_d1_confirmed_source(rows=None)` được **parameterize** (mặc định = `_D1_SOURCE_ROWS`) và swing nay đọc **causal** trên `candles[:_D1_BREAK_INDEX+1]` để nến retest về sau không làm đổi swing xác nhận. Command/kết quả ở §A3.61; file hash mới `F1555E4912D7F0BA7BFAE69304C685F9DD839982C04FFFBC684FD35879640A74`. | Chỉ thêm fixture/helper/node + parameterize helper sẵn có trong test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node A3-057, không đổi ngưỡng. **Không** gọi `analyze_zone_lifecycle` lần hai với ATR tự gán để thay output cần kiểm — output kiểm là của `enrich_zones`. | **GREEN** (chuẩn bị, không kỳ vọng RED): lifecycle canonical tính đúng timeline retest của fixture ⇒ `enrich_zones` là đường đúng cho A3-060…A3-062. Node A3-057 chạy lại **vẫn PASS** sau khi đổi helper sang swing causal. Inventory **84 → 85 node**, passed **28 → 29**, failed giữ **56**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **883 passed / 56 failed**. |
| A3-059 | IMPLEMENTED | `T` / `M` / `L` | Helper mới `_d1_close_at(candles, index)` (close D1 = `time + 1 ngày`, tính từ fixture) và `_d1_enriched_source()` (entry point cho A3-059…A3-062: trả `candles, break_index, bos, enriched`) + node `test_r72_09_d1_enriched_zone_survives_typed_restore`: vùng enriched của A3-058 → `SmcZone.from_dict(enriched, symbol="EUR/USD", timeframe="D1")` (typed) → `SmcZone.from_dict(typed.to_dict())` (restored). Assert cho **cả hai** model, mỗi giá trị so với expected **tính từ fixture** (không so `typed.to_dict()` với `restored.to_dict()`): `zone_id == enriched["zone_id"]`; `symbol == "EURUSD"` (dạng chuẩn hoá của `_D1_SYMBOL.replace("/", "")`); `timeframe "D1"`, `family "ob"`, `direction "buy"`; `low/high/original_low/original_high == 99.2/100.2` (nến base 32); `origin_index 32`, `departure_end_index 33`; `confirmation_event_id == bos["event_id"]`; `confirmed_at == available_at ==` close nến 34; `lifecycle_status "confirmed"`; `first_retest_index 38` + `first_retest_time` = close nến 38; `independent_retest_count 1`, `bars_spent_inside 2`, `lifecycle_mitigated True`, `broken False`, `invalidation_index`/`invalidated_at`/`expired_at` None; đúng 1 visit `completed_reacted` với `zone_id` khớp, `start_index 38`, `end_index 39`, `bars_spent_inside 2` và `entered_at`/`exited_at`/`reacted_at` = close nến 38/40/41. Command/kết quả ở §A3.62; file hash mới `42078DFA1CBE500A9251D08D8BA0F2978F2448BD3DCE27B17C254B3859D96D95`. | Chỉ thêm helper/node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node A3-057/A3-058, không đổi ngưỡng. Không so hai serialization của cùng object — mỗi field đối chiếu với giá trị dẫn xuất từ fixture. | **GREEN** (chuẩn bị, không kỳ vọng RED): typed restore **không mất** identity/biên/timeline cho vùng này (kể cả `visits` qua cả hai vòng). Giá trị bảo vệ: nếu `SmcZone.from_dict`/`to_dict` rơi mất `visits`, `available_at`, `original_low/high` hay đổi `lifecycle_status` thì node đỏ. Inventory **85 → 86 node**, passed **29 → 30**, failed giữ **56**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **884 passed / 56 failed**. |
| A3-060 | IMPLEMENTED | `T` / `M` / `L` | Node `test_r72_09_d1_reaction_positive_reads_canonical_lifecycle`: payload = **typed đã restore** của A3-059 (`SmcZone.from_dict(enriched).to_dict()`), lifecycle = **chính** dict do `enrich_zones` sinh (A3-058) — **không** gọi `analyze_zone_lifecycle` lần hai; cutoff `as_of = _d1_close_at(candles, len(candles)-1)` = close nến 41 = `2026-02-12T00:00Z`. Precondition: payload **không** có `d1_reaction`/`proximity`; canonical lifecycle có đúng 1 visit `completed_reacted` (`entered_at` = close nến 38, `reacted_at` = close nến 41); `available_at` = close nến 34 (`2026-02-05`) < cutoff; không có `invalidation_index`/`invalidated_at`/`expiry_index`/`expired_at` ⇒ **chưa terminal**. Contract: `valid is True`, `score > 0`, `zone_id == enriched["zone_id"]`, `source_visit_id == typed.visits[0].visit_id`, `reacted_at` = close nến 41 (tính từ fixture), `reason_codes == ["D1_REACTION_COMPLETED_REACTED"]`. **Control loại legacy flag:** `dict(payload, visits=[], d1_reaction=True, proximity=True)` + `dict(enriched, visits=[])` ⇒ `valid is False`/`score == 0`/`["D1_REACTION_NOT_COMPLETED_REACTED"]`. Command/kết quả ở §A3.63; file hash mới `3366321C28615BCA8D81619570BEA9C2C42727EB19FD493AAAF4007CD1643225`. | Chỉ thêm node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node A3-057…A3-059, không đổi ngưỡng. Tái dùng `_d1_enriched_source()`/`_d1_close_at()` (không tạo fixture trùng, không gọi lifecycle thứ hai). | **GREEN** (không kỳ vọng RED): consumer D1 đọc đúng visit canonical của fixture cho kết quả dương. Đây là **ca dương thật** cho R72-09 end-to-end (detector → confirm → enrich → typed → D1) sau khi A3-056 thu hẹp ca H1 smoke. Inventory **86 → 87 node**, passed **30 → 31**, failed giữ **56**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **885 passed / 56 failed**. |
| A3-061 | IMPLEMENTED (A3R3-03; lượt A3-061/a + A3-061/b) | `T` / `M` / `L` | **A3R3-03 đã sửa (§A3.101):** bỏ positive control “rewind `as_of` trên payload đã terminal”; control nay là **prefix thật** `_D1_RETEST_ROWS` enrich **riêng** qua `_d1_enriched_source()`, `as_of` = close cuối của chính prefix (= close nến 41, `2026-02-12`) — assert prefix **chưa terminal** và **identity/history khớp bản append** (`zone_id`/`low`/`high`/`available_at`/`visits[0]`) trước khi gọi consumer. **A3-061/b (§A3.102):** khóa vế “bản append tại invalidation close” — `_D1_INVALIDATION_INDEX == len(candles) − 1` và `terminal_at` = close cuối của **chính snapshot** (không rewind); giữ nguyên contract invalid/unusable + D1 false/0 + reaction history. Fixture `_D1_INVALIDATION_ROWS` = `_D1_RETEST_ROWS` + 2 nến (bar 42 `(101.6,101.7,100.35,100.4)` vẫn ngoài vùng; bar 43 `(100.4,100.5,98.5,98.6)` đóng `98.6 < zone_low − buffer = 99.0` ⇒ terminal) + helper `_d1_invalidated_candles()` assert hình học (không nến 38..42 nào đóng qua buffer; bar 43 đóng qua buffer; reaction nến 41 vẫn trước breakdown). Node `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer`: payload typed từ `_d1_enriched_source(_D1_INVALIDATION_ROWS)`, cutoff terminal = `_d1_close_at(candles, 43)`; control trước terminal `as_of = expected_reacted_at`. Precondition **PASS**: `invalidation_index 43`, `invalidated_at == terminal_at`, `lifecycle_broken`/`broken` **True**, `expiry_index`/`expired_at` None, `available_at` giữ nguyên (close nến 34); history **2 visit** — visit-1 `completed_reacted` (entered/exited/reacted = close nến 38/40/41) và visit-2 `closed_by_invalidation` (`start=end=43`, `reacted_at` None); control trước terminal trả `valid True` với `source_visit_id == visits[0]["visit_id"]` ⇒ việc cắt tại terminal **không** thể đổ cho thiếu reaction. Command/kết quả ở §A3.64 (lượt đầu), **§A3.101** (A3-061/a) và **§A3.102** (A3-061/b); file hash mới `B1B2A6DFA86F68A9C9BAEBBF6E3346D92A4E0E6172235CF6E9A4468CD6A9DDB3`. | Chỉ thêm fixture/helper/node + parameterize `_d1_enriched_source(rows=None)` trong test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node A3-057…A3-060, không đổi ngưỡng. | RED đúng loại `implementation` (**F03/R72-08** + **F05/A-D04**) và **dừng ở assert contract đầu tiên** `lifecycle_status == "invalid"` (thực tế `"confirmed"`). **Sau A3-061/a** điểm dừng **không đổi**, nhưng positive control nay là **prefix thật** (không còn rewind `as_of` trên payload terminal) và **PASS** trước khi tới assert terminal — nên RED không thể đổ cho "control không hợp lệ" hay "payload terminal bị cắt ngược". Probe cùng chuỗi (trước khi viết node) cho thấy hai gap còn lại cũng đỏ: **`usable` thiếu key** (kỳ vọng `False`) và D1 tại terminal trả `valid True`/`score 1.0` (reason `D1_REACTION_COMPLETED_REACTED`). Đối chiếu: nhánh **expiry** cùng họ (A3-051/A3-055) đã GREEN ⇒ gap còn lại đúng là nhánh **invalidation**. Inventory **87 → 88 node**, passed giữ **31**, failed **56 → 57**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **885 passed / 57 failed** (57 đều thuộc file acceptance). |
| A3-062 | IMPLEMENTED | `T` / `M` / `L` | Fixture `_D1_EXPIRY_ROWS` = `_D1_RETEST_ROWS` + 14 nến (index 42..55) đều **ngoài** vùng (`low > zone_high + tolerance = 100.3`) và không đóng qua buffer ⇒ không mở visit mới; vùng đạt tuổi lifetime D1 (20 nến, tính từ anchor = nến xác nhận 34) tại nến 55. Helper `_d1_expired_candles()` assert hình học + `_D1_EXPIRY_INDEX == _D1_BREAK_INDEX + 21` và `== len(values) - 1`. Node `test_r72_09_d1_expired_source_is_terminal_for_the_consumer`: payload typed từ `_d1_enriched_source(_D1_EXPIRY_ROWS)`, cutoff = `_d1_close_at(candles, 55)`. Precondition PASS: metadata fixture còn (`tick_size`/`atr_current`), `available_at` nguyên (close nến 34), `expiry_index 55`, `expired_at` = close nến 55 (`2026-02-26T00:00Z`), `lifecycle_expired`/`lifecycle_stale` True, `lifecycle_broken`/`broken` False, `invalidation_index`/`invalidated_at` None, `age_bars == 21`; history 1 visit `completed_reacted` giữ nguyên (`entered/exited/reacted` = close nến 38/40/41). Contract **GREEN**: `lifecycle_status "expired"`, `usable is False`, `ZONE_EXPIRED` trong reason_codes, D1 tại expiry `valid False`/`score 0` với `reason_codes == ["D1_REACTION_STALE"]` (kèm assert loại trừ `D1_REACTION_NOT_COMPLETED_REACTED`). Command/kết quả ở §A3.65; file hash mới `34624536E34806C67398F47D7B385401AF60A92C06E14BB3AC3C557E5C738A67`. | Chỉ thêm fixture/helper/node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node A3-057…A3-061, không đổi ngưỡng. Dùng lại `_d1_enriched_source(rows=None)` (không tạo đường enrich thứ hai, không gọi lifecycle lần hai). | **GREEN** (chuẩn bị, không kỳ vọng RED): nhánh **expiry** đúng end-to-end — `enrich_zones` đã set `lifecycle_status "expired"`/`usable False`/`ZONE_EXPIRED` và consumer D1 cắt bằng `D1_REACTION_STALE`. Đối chiếu trong cùng chuỗi: **A3-060** là positive control trên chính vùng này trước expiry (valid/score>0) ⇒ kết quả ở đây không thể do "consumer luôn từ chối". Điểm cần lưu ý khi chạy control sớm: nếu truyền lifecycle **cuối chuỗi** (đã expired) với `as_of` cũ thì consumer vẫn từ chối vì gate staleness đọc trạng thái lifecycle hiện tại, **không** theo cutoff — nên node không dùng kiểu control đó mà dựa vào A3-060. Inventory **88 → 89 node**, passed **31 → 32**, failed giữ **57**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **886 passed / 57 failed** (57 đều thuộc file acceptance). |
| A3-063 | IMPLEMENTED | `M` / `L` | Mapping coverage §4 (docs-only, **không** sửa test/core): thêm mục **"Mapping coverage §4 — bảy cụm (A3-063)"** vào `smc-task-72-acceptance-matrix.md`, mỗi cụm 3 ô (positive/negative/integration) → node acceptance thật hoặc ghi thiếu. Kết quả kiểm kê **21 ô**: **13 ĐỦ** (3 ô có phần REFERENCED: fill bounds `tests/test_smc_fvg_fill_task62.py`, no-break/full-fill, R56 invariant `tests/test_smc_r56_01_session_acceptance.py` + `test_r56_02_ob_requires_atr_ids_validity_and_causal_close_provenance`), **6 MỘT PHẦN** (Metadata integration → thiếu A3-068; Pool negative → thiếu A3-065; Pool integration → thiếu A3-066; Owner negative → thiếu A3-070/071/072; Owner integration → thiếu A3-069; Consumed integration → thiếu A3-078), **2 THIẾU** (Contribution integration → A3-074; Fixtures negative phần invalid-data cố ý → A3-080). Command dùng để chốt danh sách node: `python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q` → **89 tests collected**. Không có file code/test nào đổi; file acceptance hash giữ `34624536E34806C67398F47D7B385401AF60A92C06E14BB3AC3C557E5C738A67`. | Chỉ sửa tài liệu `M`/`L`; không sửa `core/`, probe, R56/golden, không sửa test, không đổi ngưỡng. Không tạo node mới và **không** tự làm các mã A3-065/066/068/069/070/071/072/074/078/079/080 trong bước này. | **IMPLEMENTED (không phải RED/GREEN test)** — đây là bước kiểm kê coverage. Inventory giữ **89 node**, failed **57**, passed **32** (không đổi). Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration giữ **886 passed / 57 failed**. |
| A3-064 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `M` / `L` | Audit provisional + missing source/provenance theo luật 3 interface pool (A3-005). **Reuse** (không tạo bản sao): `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[buy/sell]` = pool thiếu hẳn `records`; `test_r72_01_provisional_source_cannot_create_a_sweep` = source `provisional=True`; `test_r72_01_equal_pool_without_usable_source_does_not_exist` = source `usable=False`; `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy/sell]` = lineage hợp lệ. **Bù phần thiếu:** helper `_pool_record_fixture(**overrides)` + node `test_r72_01_missing_pool_provenance_fails_closed[5 param]` phủ **5 ca thiếu riêng**: (1) `record_for_other_level` — `records` có nhưng không mang level bị sweep; (2) `no_sources` — record không có `source_ids`/`sources`; (3) `dangling_source_id` — `source_ids` trỏ nguồn vắng mặt trong `sources`; (4) `source_without_provenance_id` — source thiếu `swing_id`; (5) `source_without_usable_at` — source thiếu `usable_at`. Mỗi ca: precondition khẳng định **đúng khuyết điểm** đó + hình học nến thật sweep (`low 99.5 < 100 − 0.2`, `close 100.1 > 100`), contract `swept_lows == []` và `swept_highs == []`, control đường legacy (không `liquidity_pools`) vẫn sweep ở `index 2`. Command/kết quả ở §A3.67; file hash mới `906780EF5A7D9D0622833DEC8B6463E1B2A81E12AA43396CBA897D730C655BA3`. | Chỉ thêm helper/node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node cũ, không đổi ngưỡng. Axis BUY/SELL không nhân đôi ở node mới vì trục kiểm là **loại khuyết điểm provenance**; mirror SELL của cùng hình học đã có ở A3-010[sell]/A3-042[sell]. | RED **5/5** đúng loại `implementation` (**F06** — interface `records` chưa được `core/` đọc, `detect_liquidity_sweeps` vẫn fallback numeric): probe xác nhận cùng fixture vẫn cho `swept_lows` ở `index 2` với `source_swing_id="pool-source"` dù record khuyết provenance; precondition + control legacy **PASS** nên RED không do fixture/test sai. Inventory **89 → 94 node**, failed **57 → 62** (R72-01: 10 → 15 RED, 4 GREEN giữ nguyên), passed giữ **32**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **886 passed / 62 failed**. |
| A3-065 | IMPLEMENTED | `T` / `M` / `L` | Audit strict excursion threshold. Node mới `test_r72_01_excursion_threshold_is_strict[distance × side]` (6 param: `below`/`equal`/`beyond` × `buy`/`sell`): fixture H1 8 nến buy-shape `rows[2] = (110, 111, 100 − depth, 100.1)` với `depth = max(2×tick, 0.10×ATR) + slack`, `slack ∈ {−0.05, 0, +0.05}`; SELL dùng **đúng** fixture đó qua mirror của probe (nhắc lại: truyền rows buy-shape, không tự mirror — bài học A3-042); source `confirmed/usable/non-provisional`. Precondition: `level − candle.low == depth` (buy) / `candle.high − level == depth` (sell) và nến **reclaim trong cùng nến** ở cả 3 mức ⇒ không ca nào đổ cho thiếu reclaim. Contract: `below`/`equal` ⇒ `swept_* == []` (**đúng biên chưa đủ**); `beyond` ⇒ đúng 1 sweep `index 2`, `level` khớp, `depth == excursion + 0.05`, `excursion_buffer == max(2×tick, 0.10×ATR)`, `source_swing_id == "pool-source"`; side còn lại luôn rỗng. Command/kết quả ở §A3.68; file hash mới `33A0FB40A730DAE96C0186EFD720488160C4519B5937377468BDF08E9C213498`. | Chỉ thêm node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node A3-064, không đổi ngưỡng (dùng đúng `max(2*tick, 0.10*ATR)` đã duyệt). | **GREEN 6/6** — audit xác nhận rule strict **đã đúng** trong `core/` (`candle.low < level - excursion` / `candle.high > level + excursion`, không dùng `>=`): đúng biên không sweep, vượt biên sweep. Giá trị bảo vệ: nếu rule bị nới thành `>=`, 2 param `equal` sẽ đỏ ngay. Inventory **94 → 100 node**, passed **32 → 38**, failed giữ **62** (R72-01: 15 RED giữ nguyên, 4 → 10 GREEN). Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **892 passed / 62 failed**. |
| A3-066 | IMPLEMENTED (A3R3-04; lượt A3-066/a + /b + /c + /d + /e + /e-r1, kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `M` / `L` | Audit causal qua prefix/batch + rolling index trên **chuỗi thật**: fixture `_POOL_CAUSAL_ROWS` = 16 nến (12 nến A3-044 + 4 nến đuôi tạo swing high idx13 và swept high idx14), helper `_pool_causal_candles(rows, offset)` (build H1 y như probe, `offset` cho phép bỏ nến đầu mà **giữ nguyên timestamp**), `_pool_causal_run(values)` (producer → `detect_liquidity_pools` → `detect_liquidity_sweeps` với `lookback_bars = len(series)`), `_pool_causal_evidence(sweep)` (12 field causal, **trừ** `index`). **Node 1** `test_r72_01_pool_sweep_evidence_survives_future_bars`: prefix 12 nến vs batch 16 nến, cutoff = close nến 11; precondition chống rỗng (batch có 2 low swing vs 1, nhiều hơn 1 high swing; pivot idx4 giữ nguyên `swing_id`/`level`/`pivot_time`/`confirmed_at`/`confirmed`/`usable`; pool `swing_lows == [99.5]`); contract: evidence sweep `time <= cutoff` **giống hệt** và batch có thêm `swept_highs == [14]`. **Node 2** `test_r72_01_pool_sweep_identity_survives_rolling_index`: rolled = bỏ nến cũ nhất, offset 1 (giữ timestamp, không thêm nến mới); precondition `rolled[0].time == batch[1].time` + pool levels giống nhau; contract: pivot giữ nguyên `swing_id`/`level`/`confirmed_at` (index 4 → 3) và sweep giữ nguyên identity (`sweep_id`, `reclaimed_at`, level, depth, source IDs) chỉ `index` 10 → 9. Command/kết quả ở §A3.69; file hash mới `DF673830D4A25CBF18D941C670011AB0E59E183474FE1DD4A54E137150E091A7`. → **Sửa A3R3-04 (2026-09-11, lượt A3-066/a…/e):** **(a)** lọc evidence trước cutoff theo **`reclaimed_at`** (close) qua helper `_reclaimed_by`, không dùng `time` (open nến), kèm assert mọi event đã biết có close ≤ cutoff + assert toán tử bao gồm tại đúng cutoff; **(b)** thêm `_pool_record_for` (chọn record theo **kind + lineage**, không theo vị trí list/level) và `_assert_pool_record_matches_source` (`pool_id` chuỗi không rỗng, `sources` khớp `swing_id`/`confirmed_at`/`provisional` của swing fixture, luật max `usable_at`, bound `usable_at ≥ confirmed_at`) — **không** khoá quy tắc fallback `confirmed_at → usable_at` vì chưa có quyết định; **(c)** nối `sweep["source_pool_id"] == record["pool_id"]` cho **cả** prefix và batch + pool thứ hai cùng kind (`swing_low` idx10 level 99.0) phân biệt được bằng lineage; **(d)** rolling index 4 → 3 giữ nguyên `pool_id`/`source_ids`/`usable_at`/`kind`/`level` và nối sweep↔record ở cả hai lượt; **(e)** **node mới** `test_r72_01_pool_identity_survives_source_permutation` — đảo thứ tự 2 nguồn (precondition khẳng định thứ tự thật sự đổi) giữ `pool_id`/`usable_at` (**`source_ids` khóa theo danh sách ĐÃ SORT ổn định** sau finding A3-066/e-r1, không theo causal order). Bằng chứng: §A3.103, §A3.104, §A3.105, §A3.106, §A3.107, §A3.109. File hash mới (**hash cuối**) `67E47D6E5CFEDE9236BA684230AC44D80A76A2245AD2A30D792C331FA93BC2F2`; hash **trước /e-r1** là `21768F9473486CBABCC74DD0BD23D5F67E7C4071AB27A539098E727CF25DEBD0`. | Chỉ thêm fixture/helper/2 node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node cũ, không đổi ngưỡng. Không tạo interface mới: `usable_at`/`records.pool_id` canonical chưa có trong `core/` nên phần đó vẫn thuộc F06 (đã ghi ở A3-064/A3-010), không tự bịa. | **GREEN 2/2** — audit xác nhận tính causal **đã đúng** cho các seam đã implement: thêm nến tương lai không đổi evidence trước cutoff; rolling index không đổi causal identity và không backdate confirmation. Giá trị bảo vệ: nếu producer backdate `confirmed_at`, đổi `swing_id` theo vị trí, hoặc sweep lấy identity theo index thì 2 node này đỏ. Inventory **100 → 102 node**, passed **38 → 40**, failed giữ **62** (R72-01: 15 RED giữ nguyên, 10 → 12 GREEN). Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **894 passed / 62 failed**. → **Sau A3-066/a…/e:** hai node A3-066 chuyển **GREEN → RED chủ ý** (F06 — `records` canonical chưa có, chữ ký `assert 0 == 1`), thêm **1 node** permutation; file acceptance **116 → 117 node**, **66 failed / 50 passed → 69 failed / 48 passed** (đầu lô → cuối lô). RED còn lại của A3-066 đúng loại `implementation` **F06/R72-01**. |
| A3-067 | IMPLEMENTED (A3R3-02; lượt A3-067/a + A3-067/b + A3-067/c) | `T` / `M` / `L` | **A3R3-02 đã sửa (§A3.98):** node lifecycle override nay khóa **canonical** cho rule thiếu nguồn — `metadata_state == "unknown"`, `metadata_reason` không rỗng, `invalidation_buffer is None` (**không** còn `0.0`), `lifecycle_broken is False` cho cả nến chạm lẫn nến đóng `99.93`; bỏ hẳn oracle “fail-closed `0.0`”. **A3-067/b (§A3.99):** bổ sung **2 cross-control** chứng minh mỗi override chỉ đổi rule của nó — `break_buffer=0.05` trên fixture chạm (buffer `0.05`, `visits == ()`), `zone_tolerance=0.5` trên fixture phá (buffer vẫn `0.1`, `broken False`); nhóm controls được đặt **trước** khối thiếu-metadata để chạy thật dưới RED hiện tại. Không thêm override mới. **A3-067/c (§A3.100):** quét đồng bộ mô tả/docstring còn gọi thiếu metadata là “fail-closed” — sửa docstring A3-021 sang `unknown ⇒ unusable, threshold None`; giữ nguyên lịch sử (interface proposal M dòng172 đã bị thay, §A3.70 đã có đính chính). Audit **explicit override**. Bảng "Override audit — A3-067" vào `M` liệt kê đúng các override đang hỗ trợ (đọc chữ ký hàm, không thêm mới): `excursion_buffer` (`detect_liquidity_sweeps`), `equal_tolerance` (`detect_liquidity_pools`), `zone_tolerance` + `break_buffer` (`analyze_zone_lifecycle`; `enrich_zones` chỉ **forward** `item["break_buffer"]`, **không** có tham số `zone_tolerance`), và `tick_size` đối số (A-D07). 3 node mới + helper `_override_source(level=100.0, **overrides)`: (1) `test_r72_07_excursion_override_only_replaces_its_own_rule` — penetration `0.10` dưới ngưỡng tính toán `0.2` nhưng trên override `0.05` ⇒ control không override `swept_lows == []`, override hợp lệ ⇒ 1 sweep `index 2` với `excursion_buffer == 0.05`, còn 3 source ineligible (`provisional`/`usable=False`/`confirmed=False`) ⇒ `[]`; (2) `test_r72_07_equal_tolerance_override_only_replaces_its_own_rule` — 2 swing low `100.0`/`100.05`; mặc định tolerance `0.2` ⇒ `equal_lows == [100.025]`, override `0.01` ⇒ `equal_lows == []` nhưng `swing_lows` vẫn `[100.0, 100.05]`, override `1.0` + 1 source `usable=False` ⇒ `equal_lows == []`; (3) `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule` — `zone_tolerance=0.5` cho 1 visit (mặc định 0) nhưng buffer vẫn `0.1`, `zone_tolerance=0.5` **không** tick/ATR vẫn 1 visit và buffer **phải là `None` + `metadata_state unknown`** (không còn `0.0` — A3R3-02), `break_buffer=0.05` ⇒ buffer `0.05` và `lifecycle_broken True` (mặc định `False`). Phần A-D07 **reuse** `test_r72_07_conflicting_same_scope_tick_sources_fail_closed` + `test_r72_07_item_and_argument_tick_sources_have_parity[buy/sell]` (tick argument không tự thắng tick item mâu thuẫn). Command/kết quả ở §A3.70 (lượt đầu), **§A3.98** (A3-067/a), **§A3.99** (A3-067/b) và **§A3.100** (A3-067/c); file hash mới `31B728A440D9C272F1FFDEA1A1D0CB0499079C6E63FA980314CDF8C5C1018931`. | Chỉ thêm helper/3 node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node cũ, không đổi ngưỡng, **không thêm override mới**. | **GREEN 3/3** — audit xác nhận mỗi override chỉ thay đúng rule của nó: (a) đổi được ngưỡng của chính rule (control chứng minh override là nguyên nhân), (b) **không** cứu source/provenance thiếu (provisional/unusable/unconfirmed), (c) **không** tạo metadata còn thiếu. **Sau A3-067/a** vế (c) khóa theo contract A3-007: thiếu tick/ATR ⇒ `metadata_state unknown` + reason + threshold `None` + `lifecycle_broken False` (không còn `0.0`) ⇒ 3 controls đủ metadata vẫn **PASS**, phần thiếu-metadata chuyển **RED F02** (§A3.98). Giá trị bảo vệ: node đỏ nếu override bị nối sang rule khác, bị dùng để miễn điều kiện eligibility, hoặc core lại coi threshold thiếu nguồn là `0`. Inventory **102 → 105 node**, passed **40 → 43**, failed giữ **62** (R72-07: 12 RED giữ nguyên, 5 → 8 GREEN). Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **897 passed / 62 failed**. |
| A3-068 | IMPLEMENTED | `T` / `M` / `L` | Audit nguồn ATR/tick tại thời điểm đánh giá. Fixture `_atr_source_candles(extra_rows=())` (16 nến calm + base bearish idx16 + departure idx17 + 2 nến đuôi; `extra_rows` để nối nến tương lai) + 2 node: (1) `test_r72_07_formation_atr_is_causal_and_never_latest_fallback` — `atr_reference_before_event` cho `reference_time == stamp(17)` (close **trước** nến sự kiện) và `event_time == stamp(18)`, `period 14`, `timeframe H1`; nối **5 nến biến động** (`(90,120,80,110)`) ⇒ giá trị tại cùng event **không đổi**; chuỗi warm-up ngắn (prefix 11 < 15) ⇒ reference `None`, `measure_departure(status="unavailable", reason_codes=["DEPARTURE_ATR_UNAVAILABLE"])`, candidate `unavailable`, và **BOS hợp lệ vẫn không promote** (`lifecycle_status == "candidate"`, `available_at is None`, có `OB_DEPARTURE_MEASUREMENT_UNAVAILABLE`) — kèm **control** cùng event shape promote được candidate có ATR (`confirmed`, `available_at == stamp(19)`) nên việc từ chối đúng là do thiếu nguồn; (2) `test_r72_07_formation_and_current_atr_keep_their_own_source` — thêm **4 nến biến động** ⇒ ATR formation `2.0357142857142856` ≠ ATR current `9.666099150826065`; `candidate["departure_measurement"]["atr_before_event"] == formation`; `invalidation_buffer` = `max(1×tick, 0.05×current)` khi truyền current và `max(1×tick, 0.05×formation)` khi truyền formation (**hai giá trị khác nhau**), tức mỗi rule đọc đúng nguồn của mình; `timeframe="M1"` ⇒ `ValueError`, `event_time` không khớp candle close ⇒ `ValueError` (không default). Import thêm `atr_reference_before_event`, `atr_value_before_event`, `measure_departure`. Command/kết quả ở §A3.71; file hash mới `3A325063FABB9AFC6C5775DC746DBE9EDE0FD4CF30247F0FF54F56C5153C0AC4`. | Chỉ thêm fixture/helper/2 node + import vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node cũ, không đổi ngưỡng. Không có override mới; chỉ kiểm nguồn ở đúng thời điểm đánh giá. | **GREEN 2/2** — audit xác nhận: (a) ATR formation đọc **causal** tại close trước nến sự kiện, nến tương lai không ảnh hưởng, thiếu warm-up ⇒ **không** có latest fallback mà fail closed tới cả bước confirmation; (b) ATR formation và ATR current **không** bị hoán nguồn (detector dùng formation, lifecycle dùng current); (c) timeframe/cutoff sai ⇒ lỗi rõ, không default. Giá trị bảo vệ: node đỏ nếu ai thêm fallback "latest ATR" khi thiếu nguồn, lấy reference ở cuối chuỗi, hoặc cho lifecycle dùng formation ATR thay current. Inventory **105 → 107 node**, passed **43 → 45**, failed giữ **62** (R72-07: 12 RED giữ nguyên, 8 → 10 GREEN). Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **899 passed / 62 failed**. |
| A3-069 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `M` / `L` | Audit owner theo claim time ở **tầng context** với thứ tự đảo. Node `test_r72_02_context_owner_follows_claim_time_under_input_permutation`: 2 zone claim cùng sweep — `early` (available hour 13, bounds `[105.2,106]`, **xa**) và `late` (hour 15, bounds `[100,110]`, **gần**) — chạy `_probe.attach` (⇒ `_attach_zone_sweep_links`) với **cả hai thứ tự** và đọc **payload sweep được chiếu**, nên kiểm đúng chuỗi enumerate→assign→project của caller (không chỉ helper). Precondition **PASS**: cả hai thứ tự đều có `owner_setup_id`/`assignment_id` (khác rỗng), `consumed is True`, `contribution_applied is True`; **invariance PASS**: đảo thứ tự không đổi `owner_setup_id`/`assignment_id`/`linked_zone_id`/`claim_eligible_at`. Contract RED: owner là `"late"` cùng `linked_zone_id "late-child"`, `claim_eligible_at == stamp(15)` thay vì claim sớm nhất `"early"`/`"early-child"`/`stamp(13)`. Command/kết quả ở §A3.72; file hash mới `C147EEF5B0DBF6E2A3CA5A1D559EE280A14A3BF9203A1AEF7F5B87C26F016684`. | Chỉ thêm node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node A3-004/A3-045…A3-048, không đổi ngưỡng. **Reuse** `test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time` (một thứ tự) làm ca gốc; ca mới chỉ thêm trục permutation + đọc projection. | RED đúng loại `implementation` (**F08** — caller đang rank theo **distance** thay vì claim time theo A-D02) và **chỉ ở assert contract đầu** `owner_setup_id == "early"`; precondition + invariance đều PASS nên RED không do fixture/test sai. Đối chiếu: helper độc lập đã GREEN (`test_r72_02_same_time_tie_is_stable_under_claim_permutation`) ⇒ gap nằm ở **caller**, đúng như hàng A3-069 yêu cầu. Inventory **107 → 108 node**, passed giữ **45**, failed **62 → 63** (R72-02: 3 RED → 4). Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **899 passed / 63 failed** (63 đều thuộc file acceptance). |
| A3-070 | IMPLEMENTED | `T` / `M` / `L` | Audit claim sai chiều. Node `test_r72_02_opposite_side_claim_cannot_own_a_sweep`: zone sai chiều `supply_zone`/`sell` bounds `[104.95,105.05]` (khe giá `0.05` tới level sweep `105` — **gần hơn**) + zone hợp lệ `demand_zone`/`buy` bounds `[105.2,106]` (khe `0.2`); sweep `swept_low` level `105`, `atr_value=1.0`. Precondition từ fixture: `sweep_side == "buy"`, zone sai chiều khác chiều sweep và **gần hơn về giá** (`0.05 < 0.2`) ⇒ chỉ rule chiều mới loại được nó. Contract: tầng link `associate_sweeps_to_zones` chỉ trả link cho zone hợp lệ với `distance_atr == 0.2`; caller context (`_probe.attach` ⇒ `_attach_zone_sweep_links`) chiếu `owner_setup_id "right-side"` + `linked_zone_id "right-side-child"`, zone sai chiều `liquidity_sweep_linked False`/`linked_sweep_id None`, và **giống nhau ở cả hai thứ tự**. Import thêm `associate_sweeps_to_zones`. Command/kết quả ở §A3.73; file hash mới `357D8CE299EE25BC9FC5BE634B94A6391FF0171F5A38B92C6394335964E98683`. | Chỉ thêm node + import vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node cũ, không đổi ngưỡng. | **GREEN 1/1** — audit xác nhận rule chiều **đã đúng ở cả hai tầng**: `associate_sweeps_to_zones` so `zone_side != sweep_side` trước mọi kiểm giá/thời gian, nên zone sai chiều bị loại **dù gần hơn**; zone đúng chiều vẫn được chọn (positive control trong cùng node). **Ghi nhận phạm vi (không tạo RED giả):** `assign_sweep_ownership` chỉ kiểm `side ∈ {buy, sell}` (không so với chiều sweep) — nhưng theo caller chuẩn thì claim chỉ được sinh ra từ cặp zone–sweep **đã qua tầng link side-aware**, nên claim sai chiều không tới được assignment; node này kiểm đúng đường đi thật thay vì dựng input không tồn tại. Inventory **108 → 109 node**, passed **45 → 46**, failed giữ **63**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **900 passed / 63 failed**. |
| A3-071 | IMPLEMENTED (A3R3-01; lượt A3-071/a + A3-071/b + A3-071/c) | `T` / `M` / `L` | **A3R3-01 đã sửa (§A3.95):** tầng context nay truyền **candle input local** `(120,120.5,119.5,120) × 20` ⇒ `TR = 1.0` mọi nến ⇒ ATR caller **1.0** (không còn ATR `2.0` của `_probe.attach`), và **từng zone được chạy một mình qua chính caller** để assert eligibility/`linked_sweep_distance_atr` trước khi ghép cặp; zone "ngoài" **không** link kể cả đứng một mình. **A3-071/b (§A3.96):** khẳng định **event-level** cho từng zone đứng riêng — trong/đúng biên có `linked_zone_id`/`owner_setup_id`/`consumed True` của chính zone đó, ngoài biên giữ `linked_zone_id None`/`consumed False`/không `owner_setup_id`. **A3-071/c (§A3.97):** vế **hai thứ tự** — mỗi thứ tự dựng **pair mới** (không dùng lại dict đã bị caller ghi link payload), outside-early `hour 13` **sớm hơn** vẫn **không** lấy owner/assignment (`sweep_owner_setup_id`/`sweep_assignment_id` vắng), owner/`assignment_id`/`linked_zone_id`/`claim_eligible_at` **không đổi** khi đảo input. Audit claim ngoài khoảng cách. Node `test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep`: sweep level `105`, `atr_value=1.0`, tolerance đã chốt `0.25` ⇒ 3 mức band — **trong** `[104,106]` (level nằm trong vùng), **đúng biên** `[105.25,106]` (khe `0.25`), **ngoài** `[105.26,106]` (khe `0.26`). Contract tầng link: trong ⇒ link với `distance_atr == 0.0`; đúng biên ⇒ **vẫn link** với `distance_atr == 0.25` (biên bao gồm vì code chỉ loại khi `>`); ngoài ⇒ `None` (không claim). Tầng context: zone ngoài khoảng nhưng `available_at` **sớm hơn** (`hour 13` < `hour 15`) **không** thắng — owner là `"inside-late"`, `linked_zone_id "inside-late-child"`, zone ngoài `liquidity_sweep_linked False`/`linked_sweep_id None`, giống nhau ở **cả hai thứ tự**. Command/kết quả ở §A3.74 (lượt đầu), **§A3.95** (A3-071/a), **§A3.96** (A3-071/b) và **§A3.97** (A3-071/c); file hash mới `23AE09AD38A960BD178076001047916FF3B6297D1917A3576D247D6AB1ACC9EE`. | Chỉ thêm node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node cũ, **không đổi ngưỡng** (`tolerance_atr = 0.25` là rule đã chốt, chỉ kiểm đúng biên). | **GREEN 1/1** — audit xác nhận rule khoảng cách **đã đúng**: `distance_atr = price_distance / atr`, loại khi `distance_atr > tolerance` ⇒ **biên bao gồm** (`0.25` vẫn nhận, `0.26` loại) và ngoài khoảng thì **fail closed** (không sinh claim). Điểm "claim không đủ không thắng bằng timestamp sớm" được kiểm ở tầng context: zone ngoài khoảng available sớm hơn vẫn không thành owner. Giá trị bảo vệ: node đỏ nếu ai nới biên thành `>=`, bỏ hẳn kiểm khoảng cách, hoặc để claim ngoài khoảng tham gia xếp hạng. **Sau A3-071/a** node còn đỏ nếu fixture context quay lại ATR sai nguồn (`2.0` ⇒ zone "ngoài" chỉ cách `0.13` ATR ⇒ link) — đúng lỗi A3R3-01. **Sau A3-071/b** node còn đỏ nếu caller link zone nhưng không sở hữu sweep ở event, hoặc nếu zone đúng biên bị loại (`0.25` phải nhận). Inventory **109 → 110 node**, passed **46 → 47**, failed giữ **63**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **901 passed / 63 failed**. |
| A3-072 | IMPLEMENTED | `T` / `M` / `L` | Audit claim ngoài cửa sổ thời gian. Node `test_r72_02_claim_outside_time_window_cannot_own_a_sweep`: sweep idx `10`, `max_time_bars = 3` (**đúng tham số đã có**, không chỉnh window) ⇒ delta `sweep_index − formation_start_index`: `8 → 2` (**trong**) ⇒ link; `7 → 3` (**đúng biên** `== max_time_bars`) ⇒ **vẫn** link; `6 → 4` (**ngoài**) ⇒ **không** link; cửa sổ formation/departure kết thúc trước sweep (`formation_start 0`, `departure_end_index 9 < 10`) ⇒ **không** link. Tầng context (window mặc định `20`): zone hết cửa sổ available `hour 13` (sớm hơn) **không** thắng; owner `"in-window"`/`linked_zone_id "in-window-child"`, zone hết cửa sổ `liquidity_sweep_linked False`, giống nhau ở **cả hai thứ tự**. Command/kết quả ở §A3.75; file hash mới `B34FC1A03047878D32F970EC7AB64824F6048DB76DE9582173DCD2A43E024F36`. | Chỉ thêm node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node cũ, **không đổi time window** (`max_time_bars=3` chỉ là tham số truyền vào cho fixture nhỏ, rule giữ nguyên). | **GREEN 1/1** — audit xác nhận rule cửa sổ thời gian **đã đúng**: điều kiện `sweep_index - formation_start > time_window` ⇒ **biên bao gồm** (delta `3` nhận, delta `4` loại), đồng thời `formation_start ≤ sweep_index ≤ departure_end_index` loại sweep nằm ngoài cửa sổ formation/departure; tầng context zone ngoài cửa sổ **không** thắng dù `available_at` sớm hơn. Giá trị bảo vệ: node đỏ nếu ai nới window để test đạt, bỏ vế `sweep_index − formation_start`, hoặc để zone ngoài cửa sổ tham gia xếp hạng. Inventory **110 → 111 node**, passed **47 → 48**, failed giữ **63**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **902 passed / 63 failed**. |
| A3-073 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `M` / `L` | Audit tie-break khi claim time bằng nhau. **Reuse (đã đủ, không viết lại):** `test_r72_02_same_time_tie_is_stable_under_claim_permutation` — helper `assign_sweep_ownership` với 2 claim cùng `setup_available_at`/`reclaimed_at`, owner `"early"` (setup ID nhỏ) ở **cả hai thứ tự**; chạy lại xác nhận PASS. **Bù phần context (chưa có node cho tie):** node `test_r72_02_context_same_time_tie_follows_stable_setup_id` — 2 zone cùng `available_at == stamp(13)` (`alpha-setup`/`z-winner-child` có setup ID nhỏ, `beta-setup`/`a-loser-child` có zone ID nhỏ ⇒ phân biệt được rule), mỗi zone link được khi chạy riêng (tie thật), link one-to-one nên đúng 1 zone mang link/lượt, chạy cả hai thứ tự. Precondition + invariance **PASS** (đảo thứ tự không đổi owner/assignment/linked zone; `claim_eligible_at == stamp(13)`). RED tại contract: owner `"beta-setup"`/`"a-loser-child"` (theo **zone ID**) thay vì `"alpha-setup"`/`"z-winner-child"` (setup ID ổn định theo A-D02). Command/kết quả ở §A3.76; file hash mới `47E92C983C76A60176BDB59A2DB02CC51EBFB222C83FEAFDF1F8B9DBB4ED7CCB`. | Chỉ thêm 1 node vào test và `M`/`L`; không sửa `test_r72_02_same_time_tie_is_stable_under_claim_permutation` (chỉ chạy lại), không sửa `core/`, probe, R56/golden, không đổi ngưỡng. | RED đúng loại `implementation` (**F08**, chiều tie-break — cùng họ với A3-069 nhưng ở trục *cùng claim time*) và **chỉ ở assert contract đầu** `owner_setup_id == "alpha-setup"`; precondition + invariance PASS nên RED không do fixture sai. Ghi nhận phạm vi: hàng A3-073 nói "ghi riêng coverage context từ 069" — 069 phủ trường hợp context **khác claim time**; tie ở context trước đây **chưa** có node nên lượt này bù đúng ô "same-time owner tie" đó (thêm 1 node, không nhân bản 069). Inventory **111 → 112 node**, passed giữ **48**, failed **63 → 64** (R72-02: 4 RED → 5). Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **902 passed / 64 failed** (64 đều thuộc file acceptance). |
| A3-074 | IMPLEMENTED | `T` / `M` / `L` | Audit contribution theo **từng sweep** khi owner có nhiều child. Node `test_r72_03_contribution_is_counted_per_sweep_not_per_list`: 5 claim của cùng owner `owner-1` trên **2 sweep độc lập** — `sweep-a` ← `child-b`, `child-a` (`family="fvg"`), `child-c` (`family="ob"` + `note` metadata); `sweep-b` ← `child-d`, `child-e` (`family="fvg"`); cùng claim time. Precondition/contract: `assignments` mỗi sweep owner `owner-1`; `per_sweep == {"sweep-a": 1, "sweep-b": 1}` ⇒ **tổng danh sách `2`** (chứng minh **không** cap tổng toàn danh sách về 1); con được credit là con đầu tiên theo zone ID (`child-a`, `child-d`) ⇒ duplicate/multi-family/metadata **không** tăng hoặc làm mất contribution; đảo thứ tự input ⇒ per-sweep count và con credit **không đổi**. Command/kết quả ở §A3.77; file hash mới `73F027D724F16FED221273CA8748D1025BAEE6B4BF16C71D3A4CD15A3AEDBF75`. | Chỉ thêm node vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node cũ, không đổi ngưỡng. | **GREEN 1/1** — audit xác nhận rule contribution **theo sweep** đã đúng: logic gom theo `sweep_id` và chỉ một claim (con đầu tiên của owner) được credit, nên nhiều child/multi-family/metadata không làm tăng; và vì khoá là `sweep_id` nên hai sweep độc lập cho tổng `2`. Giá trị bảo vệ: node đỏ nếu ai cap contribution theo **danh sách** về 1, bỏ dedupe theo child, hoặc để metadata/family ảnh hưởng kết quả. Inventory **112 → 113 node**, passed **48 → 49**, failed giữ **64**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **903 passed / 64 failed**. |
| A3-075 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `M` / `L` | Audit child **non-owner có ID nhỏ hơn**. **Reuse** node sẵn có `test_r72_03_acceptance_contribution_is_selected_within_owner_children` (fixture `early/z-owner` 13:00 + `late/a-nonowner` 15:00 — non-owner có zone ID nhỏ hơn) và **bổ sung tối thiểu** đúng hai vế của hàng (không tạo node trùng, không đổi fixture): precondition `assert "a-nonowner" < "z-owner"`, `non_owner_claim["contribution_applied"] is False` (**PASS**), `owner_claim["contribution_applied"] is True` (**RED**); các assert cũ (`owner_setup_id == "early"`, `tổng == 1`, claim được cấp là `early`) giữ nguyên. Probe cùng fixture: assignment owner `"early"` ✓, nhưng **cả hai** claim đều `contribution_applied False` ⇒ tổng `0`, trong khi `assignments[...]["contribution_applied"] is True` ⇒ slot contribution đang được chọn trên **toàn bộ** children nên non-owner ID nhỏ chiếm khoá và con của owner không được credit (F09). Command/kết quả ở §A3.78; file hash mới `0FE5D324DD0A302C92868FCDF8EE81980A98B83A425B8E2D280AFEF9B068E1C9`. | Chỉ sửa **một node** trong test (thêm precondition + 2 assert đúng hai vế của hàng) và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi fixture/ngưỡng, không thêm node. | RED đúng loại `implementation` (**F09**) — node vốn đã RED từ trước, lượt này chỉ làm rõ **điểm dừng** và bổ sung vế non-owner: giờ dừng ở `owner_claim … is True` sau khi vế `non_owner … is False` **PASS** ⇒ chứng minh non-owner **không** được credit nhưng owner **cũng không**, tức slot bị chọn sai tập children. Inventory giữ **113 node**, failed giữ **64**, passed giữ **49** (node đã RED trước đó). Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **903 passed / 64 failed**. |
| A3-076 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `M` / `L` | Audit **owner chỉ còn trong history**. **Reuse** hai node sẵn có + **bổ sung tối thiểu** một vế: node `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` nay assert thêm `restored["assignments"]["sweep"] == first["assignments"]["sweep"]` (giữ owner **và** `assignment_id`/`claim_eligible_at`/`assigned_at`), đưa `restored["claims"] == []` lên trước làm precondition; vế "không chuyển cho late child" **đã đủ** ở node reused `test_r72_04_assignment_survives_json_restore_with_late_only_window` (GREEN: owner `"original"` giữ, claim late `contribution_applied False`, vẫn project owner `"original"`). Probe cùng fixture: lần 1 `assignments["sweep"]` có owner `"owner"` + `assignment_id smca-371aca1fa03ccf132f88`; lần 2 (`claims=[]`) → `assignments == {}` ⇒ assignment bị **mất**. Command/kết quả ở §A3.79; file hash mới `87030B68B3BD9628CFAA0BE90E1D2B6F843D2B4FF5C41284E35446C1ACD37296`. | Chỉ sửa **một node** trong test (thêm 1 assert + đổi thứ tự assert) và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi fixture/ngưỡng, không thêm node. Không đụng golden R56. | RED đúng loại `implementation` (**F10**) và **chỉ ở assert assignment** (`restored["assignments"] == {}`, KeyError `'sweep'`) sau khi precondition `claims == []` PASS: owner history-only giữ không nổi assignment ⇒ đúng ô "owner absent" của F10. Node đã RED từ trước (điểm dừng cũ cùng chỗ), lượt này chỉ làm rõ vế "assignment giữ". Inventory giữ **113 node**, failed giữ **64**, passed giữ **49**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **903 passed / 64 failed**. |
| A3-077 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `M` / `L` | Audit **hai nhóm riêng biệt** của history bằng hai node sẵn có + **bổ sung tối thiểu 1 assert** phân nhóm. Nhóm (a) **thiếu coverage**: `test_r72_04_incomplete_history_returns_explicit_reason` — `history_complete=False` ⇒ `assignments == {}`, `claims == []`, reason **riêng** `["SWEEP_OWNER_HISTORY_INCOMPLETE"]` (**GREEN**, PASS). Nhóm (b) **mâu thuẫn history**: `test_r72_04_conflicting_assignment_history_fails_closed` — thêm `assert "SWEEP_OWNER_HISTORY_INCOMPLETE" not in result["reason_codes"]` (fixture khai `history_complete=True` + có record ⇒ không được báo nhầm nhóm thiếu), giữ `assignments == {}` và `reason_codes` không rỗng. Kết quả (b): **RED** — `assignments` chứa `sweep` với `owner_setup_id "late"` (setup của claim hiện tại), `assignment_id` mới, `contribution_applied True`, `reason_codes == []` ⇒ helper **reset history và cấp owner mới**, đúng điều hàng A3-077 cấm. Command/kết quả ở §A3.80; file hash mới `98C9D4498AA5890B1FBECA48EB591E5A1D2DFCC38066355C1F905589E3D7925D`. | Chỉ sửa **một node** trong test (thêm 1 assert + mở rộng comment) và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi fixture/ngưỡng, không thêm node, không đổi node nhóm (a). | RED đúng loại `implementation` (**F10**) và **chỉ ở nhóm (b)** sau khi assert phân nhóm PASS: nhóm (a) fail closed kèm reason riêng, nhóm (b) fail **open** (cấp lại owner, không reason) ⇒ đúng điểm hàng A3-077 yêu cầu ("có reason đúng từng nhóm, không reset history rồi cấp owner mới"). Node (b) đã RED từ trước; lượt này chỉ thêm vế phân nhóm nên inventory giữ **113 node**, failed giữ **64**, passed giữ **49**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **903 passed / 64 failed**. |
| A3-078 | IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`) | `T` / `M` / `L` | Audit **first run → JSON restore → repeat trên context**. Node mới `test_r72_04_context_repeat_after_json_restore_keeps_assignment`: lượt 1 `_probe.attach` (⇒ `_attach_zone_sweep_links`) với `old-child/original-owner` 13:00 ⇒ `owner "original-owner"`, `assignment_id smca-81d0ce9b964b17bb3702`, `consumed True`; **JSON restore** payload (`restored = json.loads(json.dumps(sweeps))`, assert `restored is not sweeps` và giá trị owner/assignment/consumed giữ nguyên **trước** lượt 2 — khác ca in-RAM của A3-004/A3-046); lượt 2 attach `new-child/later-owner` 15:00 trên payload restore ⇒ **RED**: `owner_setup_id` đổi thành `"later-owner"`, `assignment_id` mới `smca-eb0c85c44b303a18195c`, `linked_zone_id` mới, `claim_eligible_at` mới (`15:00`). Command/kết quả ở §A3.81; file hash mới `DA350504FA4F9568696C2F8C98CC61ADECD3A859A033D408CA50B7B048E0AE41`. | Chỉ thêm **một node** vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node A3-004/A3-046/A3-077, không đổi fixture/ngưỡng. Không đụng golden R56. | RED đúng loại `implementation` (**F10**) và **chỉ ở assert contract đầu** `repeated["owner_setup_id"] == first["owner_setup_id"]`; precondition (lượt 1 có owner/consumed; restore độc lập và giữ nguyên giá trị) **PASS** ⇒ RED không do fixture/test sai. Đây là ca **JSON restore** cùng họ với A3-004 (in-RAM) nên hai node không trùng nhau. Inventory **113 → 114 node**, passed giữ **49**, failed **64 → 65** (R72-04: 4 RED → 5). Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **903 passed / 65 failed** (65 đều thuộc file acceptance). |
| A3-079 | IMPLEMENTED | `T` / `M` / `L` | Audit fill + invariant R56. **Reuse (không viết lại):** `tests/test_smc_fvg_fill_task62.py` (partial bullish/bearish, full fill có/không tolerance, `original_bounds`/`zone_id` giữ, tích hợp `enrich_zones`, typed round-trip zero-width) + `tests/test_smc_r56_01_session_acceptance.py` — chạy chung **121 passed** (`python -m pytest tests/test_smc_fvg_fill_task62.py tests/test_smc_r56_01_session_acceptance.py -q`). **Bù vế còn thiếu** ("full fill không tự là break" — chưa node nào assert): node mới `test_r72_09_full_fvg_fill_is_not_a_break` dùng **đúng rows của fixture task62** (H1 4 nến, gap tạo ở bar 2, bị quét ở bar 3) + `update_fvg_fill` (import thêm từ `core.smc_lifecycle`): assert `fill_status "filled"`, `fill_ratio 1.0`, `remaining_bounds {low:100, high:100}`; `zone_id`/`setup_id`/`original_bounds`/`low`/`high` **không đổi**; **`broken is False`** và **`lifecycle_status "confirmed"`** ⇒ fill không nâng terminal state. Command/kết quả ở §A3.82; file hash mới `19CE5468214032D53B7CC8BE8AA0AFCB1785BB9CD46E45F24F1BF878BE59B4A2`. | Chỉ thêm **một node** + import vào test và `M`/`L`; không sửa `core/`, probe, **không sửa** `tests/test_smc_fvg_fill_task62.py`/R56/golden (chỉ chạy), không đổi ngưỡng. | **GREEN 1/1** — audit xác nhận fill **đã đúng**: `update_fvg_fill` không đụng `broken`/`lifecycle_status` (chỉ set `remaining_bounds`/`fill_ratio`/`fill_status`) nên full fill là **trạng thái riêng**, không phải invalidation; identity/`original_bounds` giữ nguyên. Giá trị bảo vệ: node đỏ nếu sau này ai cho fill đánh dấu `broken`/`invalid` hoặc ghi đè `low`/`high`/`original_bounds`. Inventory **114 → 115 node**, passed **49 → 50**, failed giữ **65**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **904 passed / 65 failed**. |
| A3-080 | IMPLEMENTED | `T` / `M` / `L` | Audit positive vs negative invalid-data. **Reuse:** `test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid` (năm fixture fixes F01-T59/T60-BUY/T60-SELL/T62-BUY/T63-SELL) chạy lại **PASS**. **Bù vế negative** (A3-023 ghi "chưa có fixture invalid-data cố ý"): node mới `test_r72_09_intentional_invalid_data_reports_its_own_reason` — 5 nến H1, bar 4 dùng **đúng ví dụ R72-09** `(112,113,111.2,110.2)` (close **dưới** low) ⇒ `validate_smc_candles` trả **đúng một** issue `code "SMC_OHLC_INVALID"`, `index 4`, `field "ohlc"`; control **cùng bar đã sửa theo F01-T60-BUY** `(112,113,110.2,110.2)` (close == low) ⇒ validator trả `()`; kèm assert 4 nến đầu (close/low) giống nhau giữa hai series ⇒ reason do **dữ liệu** chứ không do họ fixture. Command/kết quả ở §A3.83; file hash mới `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD`. | Chỉ thêm **một node** vào test và `M`/`L`; không sửa `core/`, probe, R56/golden, không đổi node positives, không đổi ngưỡng. | **GREEN 1/1** — positive và negative tách nhau **bằng cùng một validator**: positives qua validator sạch, invalid-data cố ý mang **reason riêng** `SMC_OHLC_INVALID` kèm đúng bar vi phạm. Giá trị bảo vệ: node đỏ nếu validator ngừng bắt OHLC sai, hoặc nếu ai "sửa" negative thành positive để test xanh. Inventory **115 → 116 node**, passed **50 → 51**, failed giữ **65**. Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration **905 passed / 65 failed**. |
| A3-084 | IMPLEMENTED | `T` / `L` | Chạy **full acceptance** và phân loại **từng** failure: `python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no` ⇒ **65 failed, 51 passed**; `-v --tb=no -rf` ⇒ đúng 65 dòng `FAILED`; `--tb=line` ⇒ 63 frame trỏ file acceptance + 2 frame trỏ `core/smc_lifecycle.py:674` (ValueError nan) = 65. **Bảng 65 dòng** (node \| expected \| actual đọc từ output \| gap) ở §A3.87, mỗi dòng ghi gap F02…F10 + precondition PASS kèm §A3.NN. **Không có test-defect/fixture-defect**: 0 lỗi collection; mọi RED dừng ở assert contract (không phải assert precondition). **GREEN 51 node KHÔNG tự là finding CLOSED** — ghi rõ trong §A3.87 (việc đóng finding thuộc Tech Lead ở A3-090/checkpoint). | Chỉ chạy và ghi `L`; không sửa test/core/probe/R56, không đổi ngưỡng. | **IMPLEMENTED** — không sinh RED/GREEN mới. Inventory **116 node**, failed **65**, passed **51**; probe **13 failed / 3 passed**; 15 file task57–71 **108 passed**; suite SMC+integration **905 passed / 65 failed**. → **Refresh r1a (2026-09-11):** full acceptance `-v --tb=short -ra` ⇒ **118 collected / 49 passed / 69 failed / 0 skip / 0 xfail / 0 error**, **khớp snapshot 69/49**, không node đổi trạng thái; bảng nhóm + 69 dòng FAILED ở **§A3.117**. **r1a xong phần chạy/inventory; r1b phân loại còn chờ.** → **r1b-01 (2026-09-11):** phân loại **18/18 RED thuộc R72-01** ⇒ **F06 ×13** (canonical `records` chưa có + fallback numeric) và **F07 ×5** (cổng A-D01 `usable_at <= reclaimed_at` chưa áp); **18/18 là `implementation`**, không có lỗi test/fixture. Bảng đầy đủ (rule, precondition đã chạy, assertion đầu fail, expected, assertion sau chưa chạy) ở **§A3.118** — kèm **giới hạn** hai node `acceptance_source_must_be_usable_at_sweep_close[buy/sell]`: fixture thiếu `usable_at` nên **chưa cô lập** được reject-do-thiếu-provenance **(F06)** với reject-thời-gian **(F07)**; ghi **F06/F07**, không chốt fallback `confirmed_at → usable_at`, và **không** tính hai node này là bằng chứng độc lập rằng temporal gate đã được kiểm. → **r1b-02 (2026-09-11):** phân loại **5/5 RED thuộc R72-02** ⇒ **F08 ×5**, 5/5 `implementation` (caller xếp hạng theo distance/zone ID thay vì claim time + setup ID; một mốc claim time thay được mốc kia) — bảng đầy đủ ở **§A3.119**. → **r1b-03 (2026-09-11):** phân loại **2/2 RED thuộc R72-03** ⇒ **F09 ×1** (`acceptance_contribution_is_selected_within_owner_children`: owner đúng, non-owner 0, nhưng **owner-present tổng 0 ≠ 1** — contribution không chiếu xuống dòng claim của owner) và **F10 ×1** (`historical_owner_without_current_child_gets_zero_contribution`: `restored["assignments"] == {}` — assignment của owner history-only bị xoá), cả hai `implementation`, ở **§A3.120** (cách diễn giải **F09** đã **đính chính** theo `core/smc_sweep_linking.py:394-424` — xem §A3.120). → **r1b-04 (2026-09-11):** phân loại **4/4 RED thuộc R72-04** ⇒ **F10 ×4**, 4/4 `implementation` (caller bỏ qua consumption qua replay/restore; helper khớp history theo `sweep_id` thay vì lineage, và không fail closed khi history mâu thuẫn) — bảng ở **§A3.121**. → **r1b-05 (2026-09-11):** phân loại **6/6 RED thuộc R72-05** ⇒ **F05 ×6** (mục 3–4 kèm **dependency F03**), 6/6 `implementation` — `build_d1_reaction_evidence` vẫn phát evidence `valid True`/`score 1.0` cho vùng terminal (`invalidated_at`), trong khi nhánh `expired_at` đã được chặn (2 node expired PASS) — bảng ở **§A3.122**. → **r1b-06 (2026-09-11):** phân loại **12/12 RED thuộc R72-06** ⇒ **F04 ×10** (lifecycle vẫn tạo reaction ở nến đúng-biên/sau-biên dù đã phát hiện terminal — A-D05) và **F03 ×2** (`enrich_zones` giữ `lifecycle_status="confirmed"` + `usable=True` dù `broken=True`) — 12/12 `implementation`, bảng ở **§A3.123**. → **r1b-07…09 (2026-09-11):** phân loại nốt **22/22 RED thuộc R72-07…09** ⇒ **F02 ×13** (hợp đồng metadata A3-007 chưa tồn tại: thiếu `metadata_state`/`metadata_reason`, tick argument không chuyển tiếp, non-finite lọt tới biên zone), **F03 ×5** (canonical `invalid` không áp ra projection) và **F05 ×4** (D1 consumer chưa đọc canonical payload) — bảng + nguyên nhân nhóm ở **§A3.124**. **A3-084 HOÀN TẤT: 69/69 RED đã phân loại**, tất cả `implementation`; không phát hiện test/fixture defect. |
| A3-083 | IMPLEMENTED | `T` / `L` | Chạy targeted cho factory/test vừa chỉnh + consumer: (1) **năm file fixture đã sửa** `tests/test_smc_zone_lifecycle_task{59,60,63}.py`, `tests/test_smc_fvg_fill_task62.py`, `tests/test_smc_lifecycle_task65.py` ⇒ **32 passed in 0.46s** (fixture hợp lệ, không regression); (2) **consumer** của các factory đó: quét import cho thấy chỉ `tests/test_smc_gate72_fix_acceptance.py` dùng chúng (qua `_load_module`) ⇒ chạy toàn file: **116 collected, 0 lỗi collection**, `65 failed, 51 passed in 0.41s`; (3) 15 file task57–71 ⇒ **108 passed**; probe reviewer ⇒ **13 failed / 3 passed** (không đổi baseline đang ghi). **Phân loại 65 RED theo finding:** R72-01 **15**, R72-02 **5**, R72-03 **2**, R72-04 **4**, R72-05 **6**, R72-06 **12**, R72-07 **12**, R72-08 **8**, R72-09 **1**. **Không có fixture/collection/test-defect:** 0 lỗi collection; mọi RED là `AssertionError` trừ hai dạng có chủ đích — `KeyError` trên field canonical **đã duyệt nhưng chưa có** (`metadata_state`/`metadata_reason`/`usable`, xem M §Interface metadata + R72-08) và `ValueError: Invalid zone boundary: nan` phát từ `core/smc_lifecycle.py:674` khi metadata non-finite (đúng gap A3-017). Không có test nào chết vì import/fixture/interface sai. Command/kết quả ở §A3.86. → **Refresh r1a (2026-09-11, lượt trình A lần4):** đã chạy lại **targeted factory (5 file ⇒ 32 passed)** và **consumer** (118 collected / 69 failed / 49 passed) trên snapshot hiện hành; bổ sung: ngoài file acceptance, `docs/plans/probes/test_smc_gate72_review.py` **cũng** tham chiếu năm factory đã sửa. Bảng đầy đủ ở **§A3.125**. | Chỉ chạy test và ghi `L` (không sửa test/core/probe/R56); không đổi ngưỡng. | **IMPLEMENTED** — không sinh RED/GREEN mới. Inventory giữ **116 node**, failed **65**, passed **51**; probe **13 failed / 3 passed**; 15 file task57–71 **108 passed**; suite SMC+integration **905 passed / 65 failed**. → **Targeted evidence r1a (2026-09-11, A3-083/r1a)** — chạy **một** lệnh pytest gồm **14 node** đã mở lại ở A lần4: **9 failed / 5 passed**, khớp **toàn bộ** expected hiện hành. RED theo F-code: **F02 ×3** (`missing_canonical_atr`, `missing_canonical_tick`, `lifecycle_threshold_overrides` — cả ba fail ở `metadata_state`, riêng node lifecycle fail **sau** khi 3 override control đủ-metadata đã PASS nên vẫn đúng "controls GREEN, thiếu-metadata RED F02"), **F03 ×1** (`d1_invalidated_source`: `'confirmed' == 'invalid'`), **F06 ×4** (`pool_sweep_evidence`, `pool_sweep_identity`, `pool_identity_permutation` — `_pool_record_for` `assert 0 == 1`; `equal_usable_at_reclaimed` — `len(records) == 1`), **F07 ×1** (`equal_pool_usable_time_is_max`: `equal_pool_events == []`). GREEN 5: A3-071, hai override control r72_07, A3-040, A3-043/b. Đây là **targeted evidence**, **chưa** phải full classification A3-084/r1; snapshot full acceptance **69 failed / 49 passed** giữ nguyên. Bằng chứng: §A3.116. |
| A3-082 | IMPLEMENTED | `T` / `L` | Collect bản cuối + so inventory A3-002: `python -m pytest -q --collect-only tests/test_smc_gate72_fix_acceptance.py` ⇒ **116 tests collected in 0.14s** (74 hàm `def test_`). So **49 node** baseline: **46 giữ nguyên ID**; **1 đổi tên** (`…actual_detector_lifecycle_d1_context_chain…` → `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke`, A3-056); **1 tách node** (`test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero` → 4 ID tại A3-016/017); **1 thêm param** (`test_r72_02_missing_canonical_claim_time_fails_closed` → `[reclaimed_at]`, `[setup_available_at]`, A3-013/014); **68 node mới** thuộc 45 họ hàm, phân bố R72-01 +21, R72-02 +6, R72-03 +1, R72-04 +1, R72-05 +2, R72-06 +11, R72-07 +9, R72-08 +5, R72-09 +8 — tất cả thuộc các mã A3 đã IMPLEMENTED. Kết luận: **không mất coverage cũ**, collection 0 lỗi. Bảng đầy đủ ở §A3.85. | Chỉ chạy collect và ghi `L`/`M` (không đổi dòng plan nào khác); không sửa `core/`, probe, R56/golden, không sửa test. | **IMPLEMENTED (docs-only)** — không sinh RED/GREEN. Inventory giữ **116 node**, failed **65**, passed **51**; probe **13 failed / 3 passed**; 15 file task57–71 **108 passed**; suite SMC+integration **905 passed / 65 failed**. → **Refresh r1 (2026-09-11, A3-082/r1)** — chạy lại **đúng một lệnh** `python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q` sau các thay đổi A3-066/e và A3-043/b: **actual 118 node / 76 test functions** (snapshot **116 / 74** giữ làm lịch sử). Hai node mới chính là phần tăng: `test_r72_01_pool_identity_survives_source_permutation` (**A3-066/e**) và `test_r72_01_single_source_pool_usable_before_sweep_close_is_accepted` (**A3-043/b**) — mỗi node +1 node và +1 function, khớp đúng Δ+2/+2. Mọi node cũ **vẫn collect được** (kể cả các họ parametrized: `excursion_threshold_is_strict` 6, `missing_pool_provenance_fails_closed` 5, `source_usable_after_sweep_close_is_rejected` 2); không tên rỗng, không trùng. SHA256 `T` **không đổi**. Bằng chứng: §A3.114. |
| A3-085 | IMPLEMENTED | `P` / `L` | Chạy **toàn bộ reviewer probes nguyên bản**: `python -m pytest docs/plans/probes/test_smc_gate72_review.py -v --tb=no` ⇒ **13 failed, 3 passed in 0.10s** (16 node). FAILED: R72-01 2 (`sweep_must_not_precede_source_confirmation[buy\|sell]`), R72-02 1 (`context_must_consider_earliest_eligible_setup…`), R72-03 1 (`nonowner_child_cannot_take_contribution_slot`), R72-04 1 (`context_must_not_reassign_already_consumed_sweep`), R72-05 2 (`broken_d1_lifecycle_cannot_supply_active_reaction[buy\|sell]`), R72-06 2 (`expiry_candle_cannot_create_reaction_for_earlier_exit[buy\|sell]`), R72-07 2 (`enrich_must_forward_explicit_tick_to_lifecycle[buy\|sell]`), R72-08 2 (`invalidated_zone_must_not_keep_confirmed_usable_flags[buy\|sell]`). PASSED 3: `test_r72_09_existing_task60_positive_fixture_must_have_valid_ohlc` + **2 control** (`test_control_live_d1_reaction_still_accepted`, `test_control_owner_children_share_exactly_one_contribution`). Probe **không sửa** (hash khớp F00 `5B040D6A…`); đúng hàng A3-085: **không** buộc tất cả GREEN trước B/C — mỗi RED gắn cụm F02…F10 (bảng ở §A3.88), 16/16 phải xanh trước checkpoint C. | Chỉ chạy probe và ghi `L`; không sửa probe/core/R56/golden, không skip/xfail. | **IMPLEMENTED** — không sinh RED/GREEN mới; giữ baseline probe **13 failed / 3 passed** như đã ghi từ đầu. Inventory **116 node** acceptance, failed **65**, passed **51**; 15 file task57–71 **108 passed**; suite SMC+integration **905 passed / 65 failed**. → **Chạy mới trên snapshot trình A lần4 (2026-09-11):** xem bảng ở **§A3.125** (số đo mới, không dẫn lại số cũ). |
| A3-086 | IMPLEMENTED | `tests task57–71` / `L` | Chạy nhóm task theo đúng §5 (`$gate72Tests = @(rg --files tests -g '*task5[7-9].py' -g '*task6[0-9].py' -g '*task7[01].py')`): **15 file**, `python -m pytest @gate72Tests -q --tb=short` ⇒ **108 passed in 1.26s**; `--collect-only -q` ⇒ **108 tests collected in 1.18s** ⇒ **0 skip/xfail/collection error**. Số node mỗi file ghi ở §A3.89 (tổng 108). So baseline: F00 **15 file / 108 passed (1.27s)**, reviewer **15 / 108 (1.26s)**, lượt này **15 / 108 (1.26s)** ⇒ **không đổi** (F01 không mất/thêm node trong nhóm này; node mới nằm ở file acceptance riêng). Đây là kết quả **chạy thật lượt này**, không chép số 108 từ tài liệu. | Chỉ chạy và ghi `L`; không sửa test/core/probe/R56/golden. | **IMPLEMENTED** — không sinh RED/GREEN mới; giữ 108 passed. Inventory acceptance **116 node** (65 failed / 51 passed); probe **13 failed / 3 passed**; suite SMC+integration **905 passed / 65 failed**. → **Chạy mới trên snapshot trình A lần4 (2026-09-11):** xem bảng ở **§A3.125** (số đo mới, không dẫn lại số cũ). |
| A3-088 | IMPLEMENTED | `full SMC/scanner` / `L` | Chạy lệnh **full §5 có cả acceptance**: `$smcTests` = `rg --files tests -g 'test_smc*.py'` (67 file, gồm acceptance) + 6 file integration = 73 file ⇒ `python -m pytest <73 file> -q --tb=no` = **65 failed, 905 passed in 9.48s**; `--collect-only -q` = **970 tests collected**. **Tách RED khỏi regression (máy móc):** `-rf \| grep '^FAILED' \| sed 's/::.*//' \| sort \| uniq -c` ⇒ **65 tests/test_smc_gate72_fix_acceptance.py** ⇒ **0 failure ở 72 file còn lại**. Đối chiếu số: retained 854 (0 fail) + acceptance 116 (51 pass / 65 fail) = **970 node / 905 pass / 65 fail** (khớp collect) — không test nào mất/chạy trùng. Phát biểu trạng thái: retained xanh hoàn toàn, **không** regression trong lệnh full; 65 RED là implementation gap F02…F10 (đã phân loại §A3.87) — **không** gọi toàn hệ thống xanh. | Chỉ chạy và ghi `L`; không sửa test/core/probe/R56/golden. | **IMPLEMENTED** — không sinh RED/GREEN mới; giữ nguyên các con số trên. → **Chạy mới trên snapshot trình A lần4 (2026-09-11):** xem bảng ở **§A3.125** (số đo mới, không dẫn lại số cũ). |
| A3-089 | IMPLEMENTED | `Git` / `L` | Kiểm phạm vi diff + fingerprints trước trình: `git diff --check` ⇒ **exit=0**, chỉ còn cảnh báo LF→CRLF **có trước** cho 7 file tracked (không có lỗi whitespace mới). `git status --short` ⇒ **135 entry** = **7 M + 5 D** (đều **có trước**, trùng khít §A3.2) + **123 ??** (62 `tests/`, 58 `docs/`, 3 module `core/smc_{history,snapshot_cache,structure_replay}.py`). Fingerprint **11/11 khớp A3-001** (5 core + probe `5B040D6A…` + R56 contract/handoff/golden/fixture/test) ⇒ core/probe/R56 không bị chạm. Phạm vi sửa của lượt này: **chỉ 4 file untracked** (acceptance + fix-plan + fix-progress + matrix), **không** thêm/xoá file ⇒ status giữ 135 suốt lượt. Thay đổi của người khác **ghi rõ, không reset/ghi đè**; 3 module core untracked chỉ **đọc**. | Chỉ chạy kiểm và ghi `L`; không commit/add/reset/xoá, không sửa core/probe/R56/golden. | **IMPLEMENTED** — không sinh RED/GREEN mới. Inventory acceptance **116 node** (65 failed / 51 passed); probe **13 failed / 3 passed**; retained **854 passed**; full §5 **970 node / 905 passed / 65 failed**. → **Chạy mới trên snapshot trình A lần4 (2026-09-11):** `git status` **136 entry** (khớp baseline ~135 có trước), `git diff --stat` 12 file tracked, `git diff --check` **exit=0** (chỉ cảnh báo LF→CRLF có trước); **11/11 fingerprint KHỚP**; SHA256 `T` **không đổi** `766EC04E…`; `L`/`P` **0** hàng lệch cột, `M` **3** hàng cũ (DEFERRED_OBSERVATION); **0** section trùng số ở cả ba file. Chi tiết: **§A3.127**. |
| A3-090 | **IMPLEMENTED** (TL: checkpoint A lần4 PASS, §A3.129) | `M` / `L` / `progress tổng` | Ghép bản trình A lần3 **trong hồ sơ hiện có** (không tạo file mới): §A3.93 gồm (1) mapping F01.1→A3-005…022, F01.2→A3-023…038, F01.3→A3-039…062, F01.4→A3-063…090 (kèm sản phẩm/kết quả từng cụm; **90/90 mã IMPLEMENTED**, 0 TODO/DOING/BLOCKED); (2) **manifest**: 4 file Coder sửa + hash (acceptance `E84A3093…`, matrix `AD6B0081…`, progress `8BDECC64…`, plan `AF1DF63D…`), fingerprint **11/11 khớp A3-001**, git `diff --check` exit=0 / status 135, acceptance 116 node (65/51), retained 854, full §5 970/905/65, probe 13/3; (3) **known RED**: 65 acceptance (§A3.87) + 13 probe (§A3.88) + lưu ý GREEN không tự CLOSED; (4) **6 quyết định còn mở** cho TL (kind enum, swing pool one-source trong `records`, `level` equal pool, tên reason code metadata, claim thiếu lineage fail-closed?, 2 điểm CHƯA RÕ của M); (5) ghi rõ **WAITING_REVIEW cho A3**, **không** tự APPROVED/đóng finding/sang F02. | Chỉ ghi `M`/`L`; không sửa core/probe/R56/test, không commit/reset/xoá. | **IMPLEMENTED** — hồ sơ đã đủ để TL review; các con số giữ nguyên như A3-088/A3-089. → **Bản trình A lần4 ghép tại §A3.128 (2026-09-11) — trạng thái `WAITING_REVIEW`.** Gồm: mapping 5 finding A3R3 → sửa đổi → evidence; manifest + hash; bảng kết quả 6 nhóm kiểm chứng (acceptance 118/69/49 · probes 13/3 · task57–71 108 · retained 854 · full 69/903); phân loại **69/69 RED** (F02×13, F03×7, F04×10, F05×10, F06×13, F06/F07×2, F07×3, F08×5, F09×1, F10×5 — tất cả `implementation`, **không** regression); 5 giới hạn còn lại; bảng trạng thái refresh A3-081…090. **Quyết định A lần3 giữ lịch sử**; không tự PASS/CLOSED/APPROVED, chưa F02/task73. |
| A3-087 | IMPLEMENTED | `retained SMC/scanner` / `L` | Chạy **retained baseline** đúng §8.7 (`$retainedSmcTests` = `rg --files tests -g 'test_smc*.py'` trừ file acceptance mới, + 6 file integration): **66 file** ⇒ `python -m pytest @retainedSmcTests <6 file integration> -q --tb=short` = **854 passed in 8.96s**; `--collect-only -q` = **854 tests collected** ⇒ 0 skip/xfail/collection error. Kiểm inventory: `test_smc*.py` = 67 file, trừ đúng 1 file acceptance ⇒ 66 (không loại nhầm file khác). So baseline F00 **66 file / 854 passed (9.08s)** ⇒ **trùng khít**, không test nào mất/thêm, không failure. Con số 854 dùng để **đối chiếu inventory**, không phải mục tiêu; acceptance mới (116 node / 65 RED) **không** nằm trong nhóm này nên không bù tổng. | Chỉ chạy và ghi `L`; không sửa test/core/probe/R56/golden. | **IMPLEMENTED** — không sinh RED/GREEN mới; giữ 854 passed cho retained. Inventory acceptance **116 node** (65 failed / 51 passed); probe **13 failed / 3 passed**. → **Chạy mới trên snapshot trình A lần4 (2026-09-11):** xem bảng ở **§A3.125** (số đo mới, không dẫn lại số cũ). |
| A3-081 | IMPLEMENTED | `M` / `L` | Hoàn thiện mapping case-level (docs-only, không sửa test): thay **toàn bộ** dạng gộp param bằng **parameter ID thật** lấy từ `--collect-only` — `[buy/sell]` (35 lần xuất hiện), `[20/21/22-buy/sell]`, `[20-buy/sell]`, `[21/22-buy/sell]`, `[20-*]`, `[expired\|invalid-buy/sell]`, `[20\|21\|22-buy/sell]`, `[False/True]`, `[atr_current\|tick_size]`, `[reclaimed_at\|setup_available_at]`, `[expired_by_age\|already_invalid]`, `[record_for_other_level\|…]`, `[below\|equal\|beyond × buy\|sell]` ⇒ mỗi ô nay liệt kê từng ID chạy được (ví dụ `…[below-buy]`, `…[below-sell]`, …, `…[beyond-sell]`). Mở rộng **2 tên bị cắt bằng dấu ba chấm** trong bảng factory A3-023 (`test_r72_05_acceptance_terminal_d1…`, `test_r72_05_serialized_terminal_mapping…`) và viết lại danh sách call-site ở hàng 1 (trước đó là shorthand `positive_pool_keeps_source_lineage`, `provisional_source…`) thành ID đầy đủ. Thêm **quy ước ghi node (A3-081)** ở đầu mục mapping (ô nêu node chạy được phải kèm param thật; tên không ngoặc = tên **họ node**, param thật ở bảng theo dõi R72-0X; tên lịch sử/probe ghi chú tại ô). **Ghi chú 3 tên còn lại:** `test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero` (tên lịch sử, đã tách tại A3-016/A3-017), `test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture` (đổi tên tại A3-056), `test_r72_09_existing_task60_positive_fixture_must_have_valid_ohlc` (reviewer probe, không thuộc file acceptance). Đồng thời sửa **dòng trạng thái đầu plan** còn ghi `A3-001…A3-055` (mâu thuẫn) thành `A3-001…A3-081`. Kiểm chứng: `python - <<script>>` đối chiếu mọi mention `test_r72_…[...]` trong M với `--collect-only` ⇒ **0** mention dạng ngoặc không tồn tại; `grep -c '[buy/sell]'` = **0**; `grep -c '\|\|'` = 0; file acceptance hash **không đổi** `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD`. | Chỉ sửa tài liệu `M`/`L` (+ một dòng trạng thái đầu plan); không sửa `core/`, probe, R56/golden, không sửa test, không đổi ngưỡng. Ca thiếu **vẫn ghi thiếu** (không đổi kết luận 21 ô §4 của A3-063). | **IMPLEMENTED (docs-only)** — không sinh RED/GREEN test. Inventory giữ **116 node**, failed **65**, passed **51** (không đổi). Probe giữ **13 failed / 3 passed**, 15 file task57–71 giữ **108 passed**, suite SMC+integration giữ **905 passed / 65 failed**. → **Refresh r1a (2026-09-11):** bằng chứng **§A3.115** — đối chiếu collection **118 node / 76 hàm `def test_`** với bảng R72-01 trong `M`: **29/29 node khớp**, không node matrix nào không collect được, không node collect bị thiếu, không ID trùng. Tham chiếu lịch sử **§A3.84** (ở `P` hàng A3-081) giữ nguyên. → **Khép A3-081 (2026-09-11, lượt trình A lần4):** đối chiếu mapping với collection thật ⇒ **118/118 node khớp** (không thiếu/thừa/trùng); một tên trong `M` là **ghi chú đổi tên lịch sử** (`test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture` → A3-056 đổi tên thành `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke`), **không** phải node thừa. Đã điền **77 ô `Actual`/`Loại RED` còn trống** trên **9 bảng tracking** (109 hàng) từ evidence đã xác minh ⇒ **0 ô trống, 0 hàng lệch cột**; đồng bộ header `M` và kết luận A3-063 (§4) để phân biệt **ảnh chụp lịch sử** với **bản trình A lần4**. Bằng chứng: §A3.126. |

### A3.1 — Mốc nhận việc

| Mục | Giá trị |
|---|---|
| Thời điểm nhận việc | 2026-09-11 11:11:59 +07:00 (Asia/Saigon) |
| Branch | `main` |
| Revision `HEAD` | `fb9ea527ee7ff0eb48c53875e24796260008e92c` |
| Revision `origin/main` | `fb9ea527ee7ff0eb48c53875e24796260008e92c` (trùng `HEAD`) |
| Giao việc | `A3-001` trong [fix-plan §8.2][§8]; chỉ documentation/inspection, không sửa `core/`, probe, R56, tests |
| Command đã chạy | `git rev-parse HEAD`, `git rev-parse origin/main`, `git status --short`, `Get-FileHash -Algorithm SHA256`, đọc file (không chạy pytest) |

### A3.2 — Trạng thái Git tại mốc nhận việc

Toàn bộ là thay đổi **có trước**, giữ nguyên; không thuộc lượt A3 này.

- Tracked đã sửa (7): `core/market_models.py`, `core/smc_confluence.py`, `core/smc_context.py`,
  `core/smc_lifecycle.py`, `core/smc_models.py`, `core/smc_sweep_linking.py`, `tests/test_smc_context.py`.
- Tracked đã xóa (5), ngoài phạm vi SMC: `docs/plans/dashboard-flat-icons-plan.md`,
  `flat-icons-gates-plan.md`, `flat-icons-phase2-plan.md`, `flat-icons-score-breakdown-plan.md`,
  `location-scoring-upgrade-plan.md`.
- Untracked: `docs/plans/probes/`, các spec/review/response/task-72 plan trong `docs/plans/`,
  các module `core/smc_history.py`, `core/smc_snapshot_cache.py`, `core/smc_structure_replay.py`,
  và các fixture/test SMC của task 17–72.

Đối chiếu `HEAD` với baseline task 1 trong
[progress tổng](smc-implementation-progress.md): **không đổi** (`fb9ea52`), tức chưa có commit mới
trong khoảng giữa.

### A3.3 — Fingerprint F00 (bắt buộc đối chiếu cuối lượt)

11 file theo danh sách F00 / hash ledger đã review. **Cả 11 khớp tuyệt đối** → `core/`, reviewer
probe và hồ sơ R56 chưa bị chạm kể từ lúc review.

| File | SHA256 hiện tại | So với ledger |
|---|---|---|
| `core/smc_context.py` | `D7550D1A0A9A3FDB6CAF17B520359F5BEC00D064FF242F11DBAF21AF6D62A3E7` | khớp |
| `core/smc_models.py` | `AE630F7B24160D794675602A08B3C05F9A9A52410AFD7FBBBEDA066E1C93AA20` | khớp |
| `core/smc_lifecycle.py` | `AAB6B803417070588B90EB4F9EAC73563565C8B48C76875EC2808FDFB6ECD019` | khớp |
| `core/smc_sweep_linking.py` | `38B0276FB065D6EF7FBB454D8C6929D533D8ECA22FFC4EDB5BF6C352E57EFFB3` | khớp |
| `core/smc_confluence.py` | `386008C758FC23CE3ED2E8F66F65AF8F2A38090DA039B9E3FF2A71CDFDACCDEF` | khớp |
| `docs/plans/probes/test_smc_gate72_review.py` | `5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6` | khớp |
| `tests/fixtures/smc_canonical/golden_cases.json` | `45437A90E540BF772E1E3F2899C06D328293181F19F9B36AA5E26C3170C79999` | khớp |
| `docs/plans/smc-r56-01-session-contract.md` | `F04A0E6451801E04EA90E288543FD03B96CB82C715657992962A2FDB433D50BB` | khớp |
| `docs/plans/smc-r56-01-coder-handoff.md` | `AA682DA161E49E807CC0AB2CD7E6BC3A581E9E8AD14456F6FB53BDE41F28D301` | khớp |
| `tests/fixtures/smc_r56_01_session_acceptance.json` | `698CF8A2557FFD829CEBF7316AE30D854C84BED605B17F5FF1C6220254D2BDD5` | khớp |
| `tests/test_smc_r56_01_session_acceptance.py` | `F1975050751F61A44CFE3B0936C19179A85DEECA08735D942986CFD8A253A5CA` | khớp |

**Fingerprint phạm vi F01** (mốc để so cuối lượt; chưa sửa trong lượt này):

| File | SHA256 tại mốc nhận việc |
|---|---|
| `tests/test_smc_zone_lifecycle_task59.py` | `213766685D91637067E85E7DFC80CD5EFA641464A556770D61B1D17FB60CEAAB` |
| `tests/test_smc_zone_lifecycle_task60.py` | `DD4A07AA41598510C0236830DB8533C085A2DDC14DBD022618576E3CF1013A29` |
| `tests/test_smc_fvg_fill_task62.py` | `8A2CAB7CDCCE4A69082C5B50567907BEC95F9D76A7E4A5EF6BB6BD101A357E90` |
| `tests/test_smc_zone_lifecycle_task63.py` | `C52772C93797B83032FB2DE4B7E9EE41A1697CD3B68C08186BB1CB3FC5EC73EF` |
| `tests/test_smc_lifecycle_task65.py` | `7639B01DE97876F499A5D41464A4BCB3F788496B64805C3048E00693BB048DAF` |
| `tests/test_smc_gate72_fix_acceptance.py` | `687F030C2A9F7E3D00141D9B40A3CB8260D677611AAA8971E18E084B386DE0A5` |
| `docs/plans/smc-task-72-acceptance-matrix.md` | `A8966538E9073DADD766172650C3DAC74B8E394AB1C9742BD8CF68786A131FD3` |
| `docs/plans/smc-task-72-fix-progress.md` | `0F46C6B6856810863E5A0ECE0F80705964D66DB4DBB7098E55E006DA75055534` (trước lượt A3 này) |

### A3.4 — Điểm lệch cần A3-003 đối chiếu (không tự xử lý ở A3-001)

`tests/test_smc_gate72_fix_acceptance.py` và `docs/plans/smc-task-72-acceptance-matrix.md` hiện
**không khớp** hash mà ledger §"Checkpoint A lần 2 supplement" đã ghi lúc trình A lần2
(`DEF12B99850D…` và `45E8DD27…`).

- Không phải khác biệt phương pháp băm: ba cách tính (raw bytes, CRLF→LF, text-mode UTF-8) cho
  **cùng một** kết quả trên cả hai file.
- Dấu vết thời gian: matrix `10:17:12` (trùng khít mtime của
  [review A lần2](smc-task-72-checkpoint-a-review-round2.md)), acceptance test `10:18:32`,
  trong khi ledger được ghi sau đó (`11:04:24`) và fix-plan §8 (`11:06:02`).
- Một phần nội dung đã ở trạng thái **đã sửa một phần** so với dòng code mà review A lần2 trích:
  `_terminal_candles` dùng đúng exit `(110.2,110.22,110.15,110.2)` và reaction `(112,114,111,113)`
  như review yêu cầu ở F01.2; dòng 501 cũ `(112,114,111,110.5)` không còn. Ngược lại, item A3-037
  vẫn còn nguyên trạng: `test_r72_06_invalidation_precedes_expiry_and_reaction` còn đặt invalidation
  ở `rows[20]` thay vì candle age21 của D1 lifetime20.
- File hiện có **31 hàm `def test_`** và 15 decorator `parametrize` (chỉ đếm tĩnh, chưa collect).
- Chưa xác định được ai/ lượt nào tạo thay đổi này. **Không ghi đè, không khôi phục**: A3-003 phải
  đối chiếu theo tên hàm/hành vi (đúng như [fix-plan §8.1][§8] lưu ý) và ghi rõ phần đã đúng để
  không viết lại. Nếu cần, nêu câu hỏi cho TL thay vì tự chốt.

### A3.5 — Inventory node acceptance tại mốc nhận việc (A3-002)

Command đã chạy (PowerShell từ repo root):

```powershell
python -X utf8 -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
# 49 tests collected in 0.17s
```

Kết quả đo mới tại lượt này (không dùng lại con số 49 trong ledger lịch sử làm kết quả):

- **49 node / 31 hàm test**, **0 lỗi collection**, không warning import.
- Số node trùng với con số ghi lúc trình A lần2, nhưng **bytes file vẫn khác hash đã ghi**
  (§A3.4). Nghĩa là inventory không đổi trong khi nội dung trong thân hàm đã đổi — khớp với
  quan sát "sửa một phần F01.2" ở §A3.4. **Chưa kết luận** điều này đúng/sai; A3-003 sẽ đối chiếu
  theo tên hàm/hành vi.

Inventory đầy đủ theo nhóm finding (full node ID để dùng cho các mã sau):

```text
# R72-01 — 6 node
test_r72_01_acceptance_source_must_be_usable_at_sweep_close[buy]
test_r72_01_acceptance_source_must_be_usable_at_sweep_close[sell]
test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy]
test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[sell]
test_r72_01_provisional_source_cannot_create_a_sweep
test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible

# R72-02 — 3 node
test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time
test_r72_02_same_time_tie_is_stable_under_claim_permutation
test_r72_02_missing_canonical_claim_time_fails_closed

# R72-03 — 3 node
test_r72_03_acceptance_contribution_is_selected_within_owner_children
test_r72_03_historical_owner_without_current_child_gets_zero_contribution
test_r72_03_duplicate_owner_children_keep_one_contribution_under_permutation

# R72-04 — 4 node
test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay
test_r72_04_assignment_survives_json_restore_with_late_only_window
test_r72_04_incomplete_history_returns_explicit_reason
test_r72_04_same_pool_observation_cannot_bypass_consumption

# R72-05 — 6 node
test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[buy]
test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[sell]
test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[buy]
test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[sell]
test_r72_05_cutoff_equal_invalidated_at_is_terminal[buy]
test_r72_05_cutoff_equal_invalidated_at_is_terminal[sell]

# R72-06 — 10 node
test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[buy]
test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[sell]
test_r72_06_terminal_order_before_reaction_is_explicit[20-buy]
test_r72_06_terminal_order_before_reaction_is_explicit[20-sell]
test_r72_06_terminal_order_before_reaction_is_explicit[21-buy]
test_r72_06_terminal_order_before_reaction_is_explicit[21-sell]
test_r72_06_terminal_order_before_reaction_is_explicit[22-buy]
test_r72_06_terminal_order_before_reaction_is_explicit[22-sell]
test_r72_06_invalidation_precedes_expiry_and_reaction[buy]
test_r72_06_invalidation_precedes_expiry_and_reaction[sell]

# R72-07 — 8 node
test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[buy]
test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[sell]
test_r72_07_item_and_argument_tick_sources_have_parity[buy]
test_r72_07_item_and_argument_tick_sources_have_parity[sell]
test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero
test_r72_07_conflicting_same_scope_tick_sources_fail_closed
test_r72_07_equal_and_outside_buffer_buy_sell[buy]
test_r72_07_equal_and_outside_buffer_buy_sell[sell]

# R72-08 — 7 node
test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[buy]
test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[sell]
test_r72_08_invalid_canonical_zone_survives_typed_round_trip_consistently
test_r72_08_canonical_invalid_status_wins_legacy_boolean[False]
test_r72_08_canonical_invalid_status_wins_legacy_boolean[True]
test_r72_08_typed_terminal_projection_reaches_d1_consumer[buy]
test_r72_08_typed_terminal_projection_reaches_d1_consumer[sell]

# R72-09 — 2 node
test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid
test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture
```

Ghi chú phạm vi: inventory này **chưa phân loại GREEN/RED** — theo §8.1, đánh giá pass/fail và phân
loại RED thuộc A3-084; A3-002 chỉ chốt danh sách collect được trước khi sửa. Không node nào bị
skip/xfail và không có lỗi collection để ghi.

### A3.6 — Đối chiếu F01.1…4 với code hiện tại (A3-003)

Bảng đầy đủ nằm ở cuối [acceptance matrix](smc-task-72-acceptance-matrix.md#đối-chiếu-f011f014-với-code-hiện-tại--a3-003).
Tóm tắt theo trạng thái (17 điểm đối chiếu + 1 điểm để ngỏ):

| Trạng thái | Số điểm | Gồm |
|---|---|---|
| ĐÚNG RỒI (giữ nguyên) | 1 | Exit/reaction OHLC của `_terminal_candles` + dòng `rows` mở đầu của `test_r72_06_invalidation_precedes_expiry_and_reaction` (F01.2). Không ghi đè. |
| MỘT PHẦN | 3 | (a) `history_complete` còn dựa default ở 4 node positive; (b) validator đã có trên các factory nhưng chưa ghi danh sách vào M; (c) reaction trước/đúng/sau terminal có D1, **thiếu toàn bộ H4**. |
| CÒN THIẾU | 13 | F01.1: 3 (pool `records`, parameterize thiếu từng claim time, unknown metadata). F01.2: 4 (invalidation age21, timeline vào M, cadence H1/D1, terminal repeat). F01.3: 5 hàng. F01.4: 1. |
| CHƯA RÕ | 1 | `test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid` validate bản rows hard-code trong chính file, không phải rows module thật dùng → để A3-080 xác minh. |

Hai điểm đáng lưu ý cho các mã sau:

- **F01.1 chưa đạt ở cả ba nhánh** và đây là interface cho F02/F06/F10. Test lineage vẫn đọc
  `pools["equal_lows"][0]` như dict — đúng dạng mà review A lần2 yêu cầu bỏ (A3-009).
- **F01.3 gần như chưa đạt**: cả 5 hàng review nêu vẫn ở trạng thái cũ. Riêng hàng "same-pool
  observation" còn nguyên `sweep_id="sweep"` / `reclaimed_at=stamp(11)` cho cả hai claim (đã xác
  minh trong `claim` của probe, dòng 53–54).

Đối chiếu này cũng giải thích điểm lệch hash ở §A3.4: phần OHLC của F01.2 **đã** được áp dụng vào
file, nên bytes đổi trong khi inventory node không đổi (§A3.5). Không có bằng chứng thay đổi nào
ngoài phạm vi F01.2.

### A3.7 — Cột theo dõi ca nghiệm thu (A3-004)

Đã thêm mục [Bảng theo dõi ca nghiệm thu — A3-004](smc-task-72-acceptance-matrix.md#bảng-theo-dõi-ca-nghiệm-thu--a3-004)
ở cuối matrix, gồm 9 bảng con theo finding.

**Schema cột đã chốt** (dùng cho A3-081…084):

```text
Full node ID | Rule ref | Input / timeframe / cutoff | Precond | Expected | Actual | Loại RED
```

- `Full node ID`: node chạy được, ghi đủ giá trị tham số (không dùng `[buy/sell]`).
- `Rule ref`: contract/spec/decision sở hữu kỳ vọng (R72-xx, A-Dxx, P7/P8, lifecycle spec).
- `Input / timeframe / cutoff`: dữ liệu vào, timeframe và mốc cắt; ghi cadence nếu là nguồn lỗi đã biết.
- `Precond`: điều kiện phải đúng để phép assert có nghĩa, tách khỏi input.
- `Expected`: kỳ vọng viết theo contract, không lấy từ output production.
- `Actual`: **để trống** — số của A lần2 là lịch sử, không tái sử dụng; điền ở A3-083/084.
- `Loại RED`: `implementation` / `interface` / `assertion` / `fixture` / `collection` / `green`; điền sau khi chạy.

**Kiểm tra tính đầy đủ** (đã chạy): 49 hàng, 49 ID duy nhất; so với danh sách collect của A3-002
(§A3.5) — không thừa, không thiếu, không trùng. Cột `Expected` có ghi chú `⇒ cần sửa` ở những ca mà
A3-003 đã xác định chưa khớp contract, để A3-039…062 biết chỗ phải sửa.

### A3.8 — Schema pool (A3-005)

Đã ghi [Interface pool — chốt theo review A lần2](smc-task-72-acceptance-matrix.md#interface-pool--chốt-theo-review-a-lần2-a3-005)
vào cuối matrix; mục "Interface proposal for TL approval" của A lần2 giữ nguyên và được ghi rõ là bị
thay thế. **Không sửa `core/`.**

Hiện trạng đọc từ `core/smc_context.py:detect_liquidity_pools` (dùng cho phần legacy projection):

- Bốn key numeric đều là `list[float]`. `swing_highs/swing_lows` = level swing hợp lệ;
  `equal_highs/equal_lows` = **trung bình cặp** `(value+other)/2.0` — nên không thể tra ngược source
  từ level, đúng như R72-01 mô tả.
- Tolerance: `max(2*tick, 0.10*ATR)`; có override `equal_tolerance`; nhánh legacy không typed metadata
  dùng `max(avg_range*0.15, 0.0001)`. Thiếu tolerance ở nhánh typed ⇒ `status="unknown"` +
  `SMC_EQUAL_LEVEL_TOLERANCE_UNAVAILABLE`.
- Chưa có `pool_id`, `source_ids`, `sources`, `usable_at` — đây là phần canonical phải bổ sung ở F06.

Schema canonical `records` và 6 luật bắt buộc đã ghi tại M; điểm cốt lõi: không key nào vừa `float`
vừa `dict`, lineage đọc từ `records`, canonical thiếu records ⇒ fail closed (không fallback numeric).

Ba điểm phải TL chốt tại A (không tự quyết): tên enum `kind`; swing pool một source có vào `records`
không; `level` của equal pool giữ trung bình hay lấy level source sớm nhất.

### A3.9 — Đính chính `history_complete` (A3-006)

Đã ghi [Interface history — chốt theo review A lần2](smc-task-72-acceptance-matrix.md#interface-history--chốt-theo-review-a-lần2-a3-006)
vào cuối matrix, và thêm con trỏ "đã bị thay thế" ở đầu mục "Interface proposal for TL approval".

**Sai ở tài liệu, không sai ở code.** Đề xuất cũ ghi `history_complete=False` làm mặc định; kiểm tra
code cho thấy default hiện hữu là `True`:

```text
core/smc_sweep_linking.py:279   history_complete: bool = True   (assign_sweep_ownership)
core/smc_sweep_linking.py:444   history_complete: bool = True   (wrapper cùng file)
```

Ngữ nghĩa đã ghi lại theo code: history có record ⇒ authority, trả nguyên owner/assignment bất kể cờ;
không có record + `False` ⇒ `SWEEP_OWNER_HISTORY_INCOMPLETE`, không cấp owner mới; không có record +
`True` ⇒ xếp hạng claims hiện tại theo `(claim_eligible_at, setup_id, zone_id)`. Nghĩa vụ canonical
caller: truyền tường minh, đủ history ⇒ `True`, thiếu/không xác định ⇒ `False`.

**Kiểm chứng** (chỉ đọc, không sửa code):

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py::test_r72_04_incomplete_history_returns_explicit_reason \
  tests/test_smc_gate72_fix_acceptance.py::test_r72_04_assignment_survives_json_restore_with_late_only_window -q
2 passed in 0.15s
```

8 file bảo vệ (core/probe/R56/golden/acceptance): **0 changed** — không có thay đổi code hay test nào
trong lượt này.

### A3.10 — Interface metadata: biểu diễn thiếu dữ liệu (A3-007)

Đã ghi [Interface metadata — chốt theo review A lần2](smc-task-72-acceptance-matrix.md#interface-metadata--chốt-theo-review-a-lần2-a3-007)
vào cuối matrix, và thêm con trỏ "đã bị thay thế" cho dòng `enrich_zones → lifecycle → context` ở đầu
mục "Interface proposal for TL approval".

Contract đã ghi: `metadata_state="available" | "unknown"` + `metadata_reason` không rỗng khi unknown,
`usable=False`, threshold không tính được là `None` (không `0`/`NaN`, vì `0` là ngưỡng hợp lệ thật),
`lifecycle_status` giữ nguyên theo bằng chứng terminal; kèm bảng 7 ca (thiếu riêng ATR, thiếu riêng tick,
nonfinite, conflict item/argument, parity, một nguồn hợp lệ, terminal + thiếu) và ranh giới terminal.
**Không sửa `core/`.**

**Kiểm chứng 1 — ranh giới enum (chỉ đọc):** `unknown` không được thêm vào lifecycle enum.

```text
python -c "... SmcZone(**base, lifecycle_status='unknown') ..."
SmcZone unknown -> ValueError: Invalid SMC zone lifecycle status: unknown
SmcZone has usable field: False
```

Enum đóng tại `core/smc_models.py:38-45` (`candidate, confirmed, usable, watch, invalid, expired`),
validate tại `core/smc_models.py:1012-1014`. `SmcZone` **chưa** có field `usable` — round-trip typed là
việc của A3-021/F03, không phải mục này.

**Kiểm chứng 2 — hiện trạng metadata (chỉ đọc, `python -c` gọi thẳng `core`):**

```text
missing_atr {'usable': True, 'lifecycle_status': 'confirmed', 'broken': True, 'invalidation_buffer': 0.0}
missing_tick {'usable': True, 'lifecycle_status': 'confirmed', 'broken': True, 'invalidation_buffer': 0.0}
conflict {'usable': True, 'lifecycle_status': 'confirmed', 'broken': False, 'invalidation_buffer': 0.2}
arg_only {'usable': True, 'lifecycle_status': 'confirmed', 'broken': True, 'invalidation_buffer': 0.0}
enum: ['candidate', 'confirmed', 'expired', 'invalid', 'usable', 'watch'] | metadata_state present: False
```

Thiếu tick hoặc ATR ⇒ buffer `0.0` và vẫn `usable=True`/`broken` suy từ ngưỡng 0; conflict chọn item `.2`
âm thầm; argument tick không được forward (`arg_only` vẫn `0.0`); chưa có field `metadata_state` nào.
Đúng như đã ghi ở mục 6 của `M`.

**Kiểm chứng 3 — 4 node R72-07 hiện có (RED đúng loại `implementation`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero" \
  "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_conflicting_same_scope_tick_sources_fail_closed" \
  "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle" -q --tb=line
4 failed in 0.17s
```

Nguyên nhân RED (đọc trace): nonfinite tick ⇒ `ValueError: Invalid zone boundary: nan`
(`core/smc_lifecycle.py:674`); conflict ⇒ `usable` vẫn `True` (test dòng 548); forward tick ⇒ buffer
`0.0` thay vì `0.1` (test dòng 237). Đây là RED do core chưa sửa, **không phải** test/fixture defect —
assertion hiện tại của 2 node còn theo dạng cũ (`lifecycle_status in {unknown,candidate,invalid}`,
`buffer != 0`) và thuộc A3-015…018 để chỉnh.

8 file bảo vệ (core/probe/R56/golden/acceptance): **0 changed** trong lượt này — chỉ sửa 2 file docs
(`M` và `L`) + `smc-task-72-fix-plan.md` (trạng thái mã).

### A3.11 — Interface claim → assignment: nguồn pool và thời gian claim (A3-008)

Đã ghi [Interface claim → assignment — chốt theo review A lần2](smc-task-72-acceptance-matrix.md#interface-claim--assignment--chốt-theo-review-a-lần2-a3-008)
vào cuối matrix, và mở rộng con trỏ "đã bị thay thế" ở mục "Interface proposal for TL approval" cho hai
dòng `_attach_zone_sweep_links → assign_sweep_ownership` (phần còn lại) và
`assignment → contribution projection`.

Contract đã ghi (chỉ đọc code, **không sửa `core/`**, không thêm thuật toán ownership): chuỗi
caller→owner→output với field thật; claim cần **cả** `reclaimed_at` + `setup_available_at`, thiếu một ⇒
`SWEEP_CLAIM_TIME_MISSING` và không assignment (không fallback); `pool_id`/`source_ids` phải theo claim
vào **history record**; history-only owner giữ owner với contribution `0`; observation cùng causal pool
không tạo owner mới.

**Kiểm chứng 1 — probe `python -c` gọi thẳng `core` (chỉ đọc):**

```text
A reclaimed only : {'sweep': {'sweep_id': 'sweep', 'owner_setup_id': 'setup', 'assignment_id': 'smca-07fd7cbe4d0af4f0fef1', 'claim_eligible_at': '2026-09-01T11:00:00+00:00', 'assigned_at': '2026-09-01T11:00:00+00:00', 'contribution_applied': True}}
B available only : {'sweep': {..., 'assignment_id': 'smca-881815359e8b591a82d6', 'claim_eligible_at': '2026-09-01T13:00:00+00:00', ...}}
C alias sweep_time: {'sweep': {..., 'assignment_id': 'smca-07fd7cbe4d0af4f0fef1', 'claim_eligible_at': '2026-09-01T11:00:00+00:00', ...}}
D neither        : {'assignments': {}, 'claims': [], 'reason_codes': []}
E lineage in     : assignment keys = ['sweep_id', 'owner_setup_id', 'assignment_id', 'claim_eligible_at', 'assigned_at', 'contribution_applied']  (không có pool_id/source_ids; claim projection vẫn giữ pool_id/source_ids/claim_source)
F history-only   : {}
G consumed proj  : sweep nhận consumed/pool_consumed/owner_setup_id/assignment_id/assigned_at/claim_eligible_at/contribution_applied (không lineage)
```

Diễn giải: thiếu **một** trong hai thời điểm vẫn được cấp assignment (A, B); alias `sweep_time` cũng được
chấp nhận (C) nên caller dùng alias vẫn "chạy"; claim thiếu **cả hai** bị bỏ im lặng, `reason_codes` rỗng
(D); `SweepAssignment` **không** giữ lineage của pool (E) nên history không chứng minh được pool identity;
history-only không được phát lại (F). Đúng như mục 4 của `M`.

**Kiểm chứng 2 — 5 node liên quan:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_missing_canonical_claim_time_fails_closed" \
  "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time" \
  "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_same_pool_observation_cannot_bypass_consumption" \
  "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay" \
  "tests/test_smc_gate72_fix_acceptance.py::test_r72_03_historical_owner_without_current_child_gets_zero_contribution" -q --tb=line
4 failed, 1 passed in 0.21s
```

Nguyên nhân RED (đọc trace, đều loại `implementation`):

- `test_r72_02_missing_canonical_claim_time_fails_closed`: `assignments` vẫn có `{'sweep': ... owner
  'setup' ...}` ⇒ thiếu `setup_available_at` vẫn cấp owner bằng fallback, chưa có `SWEEP_CLAIM_TIME_MISSING`.
- `test_r72_03_historical_owner_without_current_child_gets_zero_contribution`: `KeyError: 'sweep'` ⇒
  history-only không được phát lại.
- `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay`: `'later-owner' !=
  'original-owner'` ⇒ `_attach_zone_sweep_links` gọi `mark_sweeps_consumed` không truyền history.
- `test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time`: owner sai do claim từ link
  chỉ có `sweep_time` thay vì `reclaimed_at`.
- `test_r72_04_same_pool_observation_cannot_bypass_consumption`: **pass nhưng trivial** — hai claim dùng
  cùng `sweep_id="sweep"` nên history khớp ID, chưa chứng minh lineage (A3-046 phải đổi observation).

8 file bảo vệ (core/probe/R56/golden/acceptance): **0 changed** trong lượt này — chỉ sửa 3 file docs
(`M`, `L`, `smc-task-72-fix-plan.md`).

### A3.12 — Chuyển assertion lineage pool sang canonical `records` (A3-009)

Sửa **chỉ test**: `tests/test_smc_gate72_fix_acceptance.py::test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy/sell]`
(local helper mới `_pool_records`). Không sửa `core/`, probe, R56/golden. Giữ mọi thay đổi có trước.

**Trước → sau.** Assertion cũ đòi `equal_lows[0]` **vừa float vừa dict** (`isinstance(levels[0], dict)`,
`levels[0]["source_ids"]`, `levels[0]["usable_at"]`) — đúng dạng schema bị review cấm ở F01.1. Assertion
mới: numeric projection vẫn `list[float]` = trung bình cặp; provenance đọc từ `records`, chọn record theo
`source_ids` của fixture, `usable_at` = max thời điểm usable **tính từ fixture**, `sources` giữ từng source.

Fixture: hai source thêm `usable_at` tường minh (`stamp(1)`/`stamp(2)`) để expected không phụ thuộc quy tắc
fallback `confirmed_at → usable_at` (chưa có quyết định). Không khoá 3 câu hỏi mở của A3-005: tên enum
`kind`, swing pool một source có `records`, `level` của equal record — test chỉ đòi `kind`/`pool_id` là chuỗi
không rỗng và không assert `record["level"]`.

**Command và kết quả thật:**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
49 tests collected                              (inventory không đổi; 0.13–0.14s)

python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_positive_pool_keeps_source_lineage_and_usable_time" -q --tb=short
2 failed                                         (0.14–0.28s tuỳ lần chạy)
  [buy]  : tests\...:360: in test_r72_01_positive_pool_keeps_source_lineage_and_usable_time
           assert len(matches) == 1  →  assert 0 == 1  (records vắng)
  [sell] : như trên

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
30 failed, 19 passed in 0.22s                    (bằng đúng số của A lần2)
```

**Phân loại RED:** `interface` — hai assertion numeric projection ở đầu test **đã pass** (positive control
chứng minh fixture thật sự vào equal pool: `equal_lows == [100.025]`, `equal_highs == [109.975]`), RED chỉ
xảy ra tại assert `records` vì container canonical `records` chưa được implement (F06, A3-005). Không còn
RED do test/fixture sai; không skip/xfail.

**Consumer/liên quan đã chạy:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_provisional_source_cannot_create_a_sweep" \
  "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible" \
  tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py -q --tb=line
1 failed, 15 passed in 0.32s
```

Failure duy nhất là `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` (RED cũ, numeric-as-dict,
xem "Còn tồn"); node provisional PASS, task66+task67 không hồi quy. Helper `_pool_records` mới chỉ dùng cục
bộ trong file acceptance nên không có consumer khác.

**Hash mới của file acceptance:** `3A51064295B545783A180D9F7CA3E1751B6A00F1148E7518FC64743261016208`
(trước lượt này: `687F030C…`, ghi ở §A3.3 — bảng cũ giữ nguyên làm lịch sử). 5 file core, probe, golden và
R56 giữ nguyên hash.

**Còn tồn (ngoài phạm vi mã này):** `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` vẫn giữ
assertion numeric-as-dict và đang RED — thuộc A3-039 (dựng lại fixture temporal + gọi sweep detector) và
A3-022 (rà schema cũ còn mâu thuẫn).

### A3.13 — Canonical sweep phải fail closed khi thiếu `records` (A3-010)

Thêm **node mới** `tests/test_smc_gate72_fix_acceptance.py::test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[buy/sell]`
(A3-005 luật 3: "canonical sweep thiếu `records` hoặc thiếu provenance ⇒ fail closed, không fallback sang
level numeric"). Không sửa `core/`, probe, R56/golden; chỉ thêm test + 2 hàng vào `M`.

**Thiết kế để RED không bị nhiễu:**

- Fixture viết tay (không lấy output production): payload pool numeric-only `swing_lows=[100.0]` (SELL:
  `swing_highs=[110.0]`), **không** có key `records`; swings có source `confirmed=True/usable=True/
  provisional=False`; `tick=.1`, `ATR=1` ⇒ `excursion = max(2*tick, 0.10*ATR) = 0.2`.
- Precondition assert rõ: `pools[numeric_key] == [level]`, `"records" not in pools`, và geometry thật của
  nến sweep idx2 — BUY `low 99.5 < 100 - 0.2` và `close 100.1 > 100`; SELL `high 110.5 > 110 + 0.2` và
  `close 109.9 < 110`. Vì vậy kết quả rỗng **không thể** bị giải thích là "fixture không có excursion".
- Control: cùng nến/swings gọi **không** truyền `liquidity_pools` (nhánh legacy adapter, đang được giữ bởi
  test task68 legacy/canonical parity) → nhận sweep tại `index == 2`. Control này chứng minh fixture thật sự
  sweepable và guard chống test pass rỗng nếu sau này detector trả rỗng cho mọi input.
- Ca positive `records` → sweep **chưa** viết được ở mã này: container `records` và tên enum `kind` còn là
  câu hỏi mở 1–2 của A3-005, viết payload canonical lúc này là đoán shape. Phần positive do A3-040/041/042
  và A3-044 (actual swing→pool→sweep) khóa bằng fixture thật.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels" -q --tb=short
2 failed                                         (RED tại dòng assert canonical)
  [buy]  : tests\...:442: assert canonical[swept_key] == []
           assert [{'depth': 0.5, 'depth_atr': 0.5, 'excursion_buffer': 0.2, 'index': 2, ...}] == []
  [sell] : như trên  → numeric level vẫn cấp sweep canonical

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
51 tests collected                               (49 + 2 node mới; inventory thay đổi có chủ đích)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
32 failed, 19 passed in 0.23s                    (30+2 failed, 19 passed)
```

Kiểm chứng riêng control (chạy trước khi ghi tài liệu, không sửa test để né RED):

```text
buy  control indices: [2] | {'swept_highs': 0, 'swept_lows': 1}
sell control indices: [2] | {'swept_highs': 1, 'swept_lows': 0}
```

**Phân loại RED:** `implementation` — precondition và control đều PASS, chỉ assert fail-closed của canonical
là fail; nguyên nhân là `detect_liquidity_sweeps` đang lấy level từ numeric keys mà không kiểm `records`
(thuộc F07). Không có RED do fixture/assertion sai, không skip/xfail.

**Consumer đã chạy (không hồi quy vì không đụng core):**

```text
python -m pytest tests/test_smc_liquidity_sweeps_task67.py tests/test_smc_liquidity_context_task71.py tests/test_smc_sweep_linking.py tests/test_smc_context.py -q --tb=line
39 passed in 0.39s
```

**Hash mới file acceptance:** `1744092182E384927BB3909E582AB6AD6843DFBFF4735BA6318C6DFF7DC2EDA0`
(§A3.12 ghi `3A510642…`, §A3.3 giữ `687F030C…` làm lịch sử). Core/probe/golden/R56 giữ nguyên hash.

### A3.14 — Completeness tường minh cho fixture ownership/history (A3-011)

Chỉ sửa `tests/test_smc_gate72_fix_acceptance.py`, **không đổi assertion nào**: mọi call site canonical
`assign_sweep_ownership(...)` nay truyền `history_complete` tường minh, không dựa default (nghĩa vụ
canonical caller đã chốt ở [Interface history (A3-006)](smc-task-72-acceptance-matrix.md#interface-history--chốt-theo-review-a-lần2-a3-006)).

| Call site | Trước | Sau |
|---|---|---|
| `test_r72_03_acceptance_contribution_is_selected_within_owner_children` | default | `True` |
| `test_r72_02_same_time_tie_is_stable_under_claim_permutation` (2 call) | default | `True` |
| `test_r72_02_missing_canonical_claim_time_fails_closed` | default | `True` (history rỗng nhưng đủ) |
| `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` (call 1) | default | `True` |
| `test_r72_03_duplicate_owner_children_keep_one_contribution_under_permutation` | default | `True` |
| `test_r72_04_assignment_survives_json_restore_with_late_only_window` (call 1) | default | `True` |
| `test_r72_04_same_pool_observation_cannot_bypass_consumption` (call 1) | default | `True` |
| `test_r72_04_incomplete_history_returns_explicit_reason` | đã `False` | giữ `False` (ca A3-012) |

Còn lại 3 call site đã tường minh từ trước (`True`): hai call dựng/khôi phục history ở
`test_r72_03_historical_owner_without_current_child_gets_zero_contribution` (call 2),
`test_r72_04_assignment_survives_json_restore_with_late_only_window` (call 2),
`test_r72_04_same_pool_observation_cannot_bypass_consumption` (call 2) ⇒ tổng **11/11 call site** có cờ.

**Command và kết quả thật:**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
32 failed, 19 passed in 0.28s        (y hệt trước khi sửa: 32/19)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
51 tests collected in 0.13s          (inventory không đổi)

python -m pytest <8 node ownership/history của R72-02/03/04> -q --tb=line
3 failed, 5 passed in 0.26s
  FAILED test_r72_02_missing_canonical_claim_time_fails_closed      → :505 assert {...owner 'setup'...} == {}
  FAILED test_r72_03_acceptance_contribution_is_selected_within_owner_children → :168 assert 0 == 1
  FAILED test_r72_03_historical_owner_without_current_child_gets_zero_contribution → :514 KeyError: 'sweep'
```

**Phân loại:** cả 3 RED là `implementation`, đúng các finding đã biết (F08 fallback claim time, F09
contribution chọn ngoài owner children, F10 history-only không phát lại) — không phải do cờ mới thêm. Việc
thêm cờ là **trung tính hành vi** vì default của helper là `True` (đã xác minh ở
[§A3.9](#a39--đính-chính-history_complete-a3-006), `core/smc_sweep_linking.py:279`), và tổng số
failed/passed giữ nguyên 32/19; 5 node ownership còn lại vẫn GREEN.

**Consumer đã chạy:** `tests/test_smc_sweep_consumed_task69.py`, `tests/test_smc_sweep_linking_task68.py`,
`tests/test_smc_setup_children_task51.py` → **15 passed** (không hồi quy).

**Còn tồn (ngoài phạm vi mã này):** caller context (`docs/plans/probes/test_smc_gate72_review.py::attach`,
read-only) vẫn để `_attach_zone_sweep_links` tự mặc định `history_complete` vì hàm này chưa có tham số
truyền xuống — thuộc F08/F10 (R72-04), không sửa được ở checkpoint A.

**Hash mới file acceptance:** `AEAF61777105E005C150A2AC135E5002EC9C32C40E5707D7A3ACCCC22CF74416`
(§A3.13 ghi `1744092182…`, §A3.12 ghi `3A510642…`, §A3.3 giữ `687F030C…` làm lịch sử).

### A3.15 — Ca history thiếu/unknown dùng claim canonical đầy đủ (A3-012)

Sửa **chỉ test** `test_r72_04_incomplete_history_returns_explicit_reason`: `history_complete=False` vốn đã
tường minh từ trước (A3-006), nên phần việc của mã này là **loại trừ mọi nguyên nhân fail khác** và siết
đúng reason của contract.

- Claim nay đầy đủ canonical: giữ `reclaimed_at`/`setup_available_at` (vốn có trong `_probe.claim`) và thêm
  `pool_id="pool-1"`, `source_ids=["swing-1"]` (giá trị fixture đã dùng ở
  `test_r72_04_same_pool_observation_cannot_bypass_consumption`), nên kết quả rỗng không thể quy cho thiếu
  claim time (A-D02) hay thiếu lineage (A-D06).
- Assert precondition 4 field trước khi gọi, để test không "fail vì field khác thiếu".
- Assertion reason siết từ `in` thành `== ["SWEEP_OWNER_HISTORY_INCOMPLETE"]` (đúng một reason), theo ngữ
  nghĩa đã chốt ở [Interface history (A3-006)](smc-task-72-acceptance-matrix.md#interface-history--chốt-theo-review-a-lần2-a3-006)
  và cùng dạng với tiền lệ `tests/test_smc_sweep_consumed_task69.py:113`.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_incomplete_history_returns_explicit_reason" -q --tb=short
1 passed in 0.19s                     (node giữ GREEN)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
32 failed, 19 passed in 0.22s         (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
51 tests collected in 0.12s           (không thêm node)
```

**Kiểm chứng assertion không vacuous** (probe `python -c`, không sửa test để né/né RED):

```text
history_complete=False -> {} ['SWEEP_OWNER_HISTORY_INCOMPLETE']
history_complete=True  -> {'sweep': {..., 'owner_setup_id': 'late', ...}} []
```

Cùng một claim canonical: chỉ khác cờ ⇒ `False` không cấp owner và trả đúng một reason, `True` cấp owner
`late`. Nên assertion thực sự phụ thuộc nhánh fail-closed của history, không phải kết quả rỗng sẵn có.

**Consumer đã chạy:** `tests/test_smc_sweep_consumed_task69.py` + `tests/test_smc_sweep_linking_task68.py`
→ **13 passed** (không hồi quy).

**Hash mới file acceptance:** `0D3B9E8A75A454507CC60AA5EE8BF3B3107A88326E1014FB23763B476902C9AB`
(§A3.14 ghi `AEAF6177…`; các hash trước giữ nguyên làm lịch sử).

### A3.16 — Khóa thiếu **từng** claim time canonical (A3-013)

Parameterize `test_r72_02_missing_canonical_claim_time_fails_closed` theo `missing_field`, thay vì viết test
mới: cùng một quy tắc A-D02 ("thiếu **một trong hai** claim time ⇒ fail closed"), §8.1 cho phép
parameterization khi cùng quy tắc. Ca `setup_available_at` cũ được **giữ nguyên hành vi** (nay là một param),
ca `reclaimed_at` là phần việc mới của A3-013.

Fixture giữ mọi thứ khác hợp lệ để RED không thể quy cho field khác:

- field còn lại hợp lệ và được assert: `[reclaimed_at]` ⇒ `setup_available_at == stamp(13)`;
  `[setup_available_at]` ⇒ `reclaimed_at == stamp(11)`;
- lineage hợp lệ: `pool_id="pool-1"`, `source_ids=["swing-1"]` (A-D06);
- `history_complete=True` **tường minh** (giữ nghĩa vụ A3-011);
- assert field thiếu thực sự vắng mặt.

Expected theo hàng A3-013: `assignments == {}` + `SWEEP_CLAIM_TIME_MISSING` trong `reason_codes`; không
fallback sang timestamp còn lại. Assertion reason giữ dạng `in` đúng theo câu chữ hàng A3-013 (khác A3-012
dùng `==` vì ở đó contract A3-006 ghi rõ "đúng một reason"); việc chống "fail vì lý do khác" do các
precondition assert đảm nhiệm.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_missing_canonical_claim_time_fails_closed" -q --tb=short
2 failed
  [reclaimed_at]      : tests\...:522: assert result["assignments"] == {}
                        → {'sweep': {..., 'claim_eligible_at': '2026-09-01T13:00:00+00:00', ...}} == {}
  [setup_available_at]: tests\...:522: assert result["assignments"] == {}
                        → {'sweep': {..., 'claim_eligible_at': '2026-09-01T11:00:00+00:00', ...}} == {}

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
52 tests collected                    (51 + 1 param mới)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
33 failed, 19 passed in 0.22s         (32 → 33 failed; +1 node RED mới)
```

**Phân loại RED:** `implementation` — precondition (field còn lại + lineage) đều PASS; chỉ assert fail-closed
là fail, và fail đúng cơ chế fallback: claim thiếu `reclaimed_at` được cấp owner bằng `setup_available_at`
(`13:00`), thiếu `setup_available_at` được cấp bằng `reclaimed_at` (`11:00`). Thuộc F08
(`core/smc_sweep_linking.py:312-326`), không sửa ở checkpoint A.

**Consumer đã chạy:** `tests/test_smc_sweep_consumed_task69.py` + `tests/test_smc_sweep_linking_task68.py`
→ **13 passed** (không hồi quy).

**Hash mới file acceptance:** `899440F84507A11C2EFEE0804C3B52D10AD77B5C57AFEE7FBE71CC71DBB2D028`
(§A3.15 ghi `0D3B9E8A…`; các hash trước giữ nguyên làm lịch sử).

**Cho A3-014:** ca thiếu riêng `setup_available_at` giờ nằm trong cùng node (`[setup_available_at]`) với đầy
đủ precondition + expected của hàng A3-014 ("reclaimed time còn hợp lệ; không fallback sang timestamp còn
lại") ⇒ mã sau chỉ cần verify + map/reuse, không viết lại.

### A3.17 — Positive control cho ca thiếu claim time (A3-014)

Ca `[setup_available_at]` đã tồn tại từ A3-013 (parameterize chung), nên mã này **không viết lại**; phần việc
còn lại là xác minh khớp hàng A3-014 và bịt lỗ hổng "pass rỗng":

- **Vấn đề:** `assignments == {}` cũng sẽ pass nếu claim bị loại vì một lý do khác (thiếu lineage, lỗi
  tương lai không liên quan), nên cần một control chứng minh chính claim đó **thắng** owner khi đủ dữ liệu.
- **Đã thêm** (dùng chung cho cả 2 param, đặt sau assert âm): claim đủ 2 mốc + lineage, `history_complete=True`
  ⇒ `owner_setup_id == "setup"` và `claim_eligible_at == max(stamp(11), stamp(13)) == stamp(13)` (A-D02).
  `max()` tính từ giá trị fixture; hai stamp cùng offset UTC nên thứ tự chuỗi trùng thứ tự thời gian.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_missing_canonical_claim_time_fails_closed" -q --tb=short
2 failed      (vẫn fail tại assert âm — control chưa được chạy tới trong lượt RED này)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
33 failed, 19 passed in 0.22s        (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
52 tests collected                   (không đổi)
```

**Kiểm chứng control độc lập** (probe `python -c` trên đúng fixture, vì lượt chạy RED dừng ở assert âm):

```text
owner: setup | eligible: 2026-09-01T13:00:00+00:00
expected max: 2026-09-01T13:00:00+00:00
control owner ok: True
control eligible ok: True
```

⇒ Khi F08 sửa xong assert âm, control phải PASS; nếu claim bị loại vì lý do khác thì control fail và test
không thể xanh giả.

**Phân loại RED hiện tại:** `implementation` (F08 chưa fail closed với claim thiếu `reclaimed_at` /
`setup_available_at`) — không phải test defect. Không skip/xfail.

**Consumer đã chạy:** `tests/test_smc_sweep_consumed_task69.py` + `tests/test_smc_sweep_linking_task68.py`
→ **13 passed** (không hồi quy).

**Hash mới file acceptance:** `28F1D7924F8CB0FACE46C8AE2B3F79D3DE1938DC122043A7A3464273CA0008FA`
(§A3.16 ghi `899440F8…`; các hash trước giữ nguyên làm lịch sử).

### A3.18 — Ca thiếu riêng ATR: unknown, unusable, threshold `None` (A3-015)

Thêm node `tests/test_smc_gate72_fix_acceptance.py::test_r72_07_missing_canonical_atr_is_unknown_and_unusable`
theo contract [Interface metadata (A3-007)](smc-task-72-acceptance-matrix.md#interface-metadata--chốt-theo-review-a-lần2-a3-007).
Không sửa `core/`, probe, R56/golden.

**Fixture và precondition (độc lập, viết tay):**

- H1 2 nến `[(112,114,111,113), (102,103,101,102.5)]`, zone `[100,110]`, `available_at=stamp(1)`,
  `origin_index=0`; item có `tick_size=0.1` **hợp lệ** và `atr_current=None`.
- Assert precondition: tick `== 0.1`, ATR là `None`, `low < close(102.5) < high` (giá còn trong zone);
  `lifecycle_expired is False` ⇒ vùng **chưa terminal** (H1 stale = 50 bars, fixture chỉ 2 nến).
- Assert giữ nguyên trạng thái: `lifecycle_status == "confirmed"`, `broken is False`.

**Assertion contract (không dùng dạng bị review cấm):** `metadata_state == "unknown"`,
`metadata_reason` là chuỗi không rỗng, `usable is False`, `invalidation_buffer is None`. Không assert
`lifecycle_status in {unknown, candidate, invalid}` và không assert `buffer != 0`.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_missing_canonical_atr_is_unknown_and_unusable" -q --tb=short
1 failed
  tests\...:724: assert result["metadata_state"] == "unknown"  →  KeyError: 'metadata_state'

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
53 tests collected                   (52 + 1 node mới)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
34 failed, 19 passed in 0.23s        (33 → 34 failed)
```

**Phân loại RED:** `interface` — field `metadata_state`/`metadata_reason` chưa tồn tại (contract đã duyệt ở
A3-007, implement ở F02). Probe trên đúng fixture cho thấy 2 gap implementation nằm sau assert này:
`usable` hiện `True` (phải `False`) và `invalidation_buffer` hiện `0.0` (phải `None`) — tức assertion đúng
nhánh, chỉ chưa chạy tới.

**Positive control** (cùng fixture, `atr_current=1`): `invalidation_buffer ≈ 0.1` (= `max(tick, 0.05*ATR)`),
`lifecycle_status == "confirmed"`, `broken is False`. Kiểm độc lập bằng probe:

```text
control buffer: 0.1 | status: confirmed | broken: False | approx0.1: True
```

⇒ `None` ở ca thiếu ATR là đặc thù của metadata thiếu, không phải artifact của fixture. Control chưa được
thực thi trong lượt RED (assert `metadata_state` fail trước) — ghi rõ, không nhận là đã chạy qua test.

**Consumer đã chạy:** `tests/test_smc_confluence_task70.py` + `tests/test_smc_zone_visit_task57.py` →
**23 passed** (không hồi quy).

**Hash mới file acceptance:** `6BE3417ACD419172597BD78930874B153AE882306EE2EB8A711546DC5791EDE8`
(§A3.17 ghi `28F1D792…`; các hash trước giữ nguyên làm lịch sử).

**Còn tồn:** ca thiếu riêng tick (A3-016), nonfinite tách khỏi missing (A3-017), conflict (A3-018),
terminal + metadata thiếu (A3-020), round-trip (A3-021). Node bundled
`test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero` vẫn giữ assertion dạng cũ và
thuộc các mã đó — không sửa ở lượt này.

### A3.19 — Ca thiếu riêng tick: unknown, unusable, threshold `None` (A3-016)

Thêm node `tests/test_smc_gate72_fix_acceptance.py::test_r72_07_missing_canonical_tick_is_unknown_and_unusable`
(mirror của A3-015, cùng contract [Interface metadata (A3-007)](smc-task-72-acceptance-matrix.md#interface-metadata--chốt-theo-review-a-lần2-a3-007)).
Không sửa `core/`, probe, R56/golden.

**Fixture và precondition:** H1 2 nến `[(112,114,111,113), (102,103,101,102.5)]`, zone `[100,110]`,
`available_at=stamp(1)`; item **ATR hợp lệ** (`atr_current=1`) và **không khai nguồn tick nào** —
assert `tick_size`/`digits`/`point` đều vắng, nên không có đường fallback `digits` để lách. Assert
`low < close(102.5) < high` và `lifecycle_expired is False` ⇒ chưa terminal; giữ `confirmed`/`broken False`.

**Assertion contract:** `metadata_state == "unknown"`, `metadata_reason` chuỗi không rỗng, `usable is False`,
`invalidation_buffer is None` (không `digits`-derived, không `0`). Không assert dạng bị review cấm.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_missing_canonical_tick_is_unknown_and_unusable" -q --tb=short
1 failed
  tests\...:763: assert result["metadata_state"] == "unknown"  →  KeyError: 'metadata_state'

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
54 tests collected                   (53 + 1 node mới)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
35 failed, 19 passed in 0.23s        (34 → 35 failed)
```

**Phân loại RED:** `interface` — `metadata_state`/`metadata_reason` chưa tồn tại. Probe trên đúng fixture:

```text
missing tick: {'usable': True, 'lifecycle_status': 'confirmed', 'broken': False, 'invalidation_buffer': 0.0, 'lifecycle_expired': False}
metadata fields present: False False
control: {'lifecycle_status': 'confirmed', 'broken': False, 'invalidation_buffer': 0.1} | approx0.1: True
```

⇒ hai gap implementation phía sau assert (`usable` phải `False`, buffer phải `None`) và control
(`tick_size=0.1` cùng fixture) cho threshold tính được ⇒ `None` là đặc thù của thiếu tick. Control chưa được
thực thi trong lượt RED (assert `metadata_state` fail trước) — ghi rõ, không nhận là đã chạy qua test.

**Consumer đã chạy:** `tests/test_smc_confluence_task70.py`, `tests/test_smc_zone_visit_task57.py`,
`tests/test_smc_domain_models.py` → **31 passed** (không hồi quy).

**Hash mới file acceptance:** `9BC772D90CF315B90C0F7875A78828B3EB469994576038C23C8891F200A6AE14`
(§A3.18 ghi `6BE3417A…`; các hash trước giữ nguyên làm lịch sử).

**Còn tồn:** nonfinite tách khỏi missing (A3-017), conflict (A3-018), terminal + metadata thiếu (A3-020),
round-trip (A3-021). Node bundled `test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero`
vẫn giữ assertion dạng cũ và thuộc các mã đó.

### A3.20 — Tách ca nonfinite khỏi missing (A3-017)

Node bundled `test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero` được **đổi tên +
parameterize** thành `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current|tick_size]`.
Phần "missing" được bỏ khỏi node này vì đã được khóa riêng ở A3-015 (thiếu ATR) và A3-016 (thiếu tick);
node còn lại chỉ xử lý **nonfinite**, đúng yêu cầu "tách ca metadata nonfinite khỏi missing".

**Thay đổi assertion:** bỏ hẳn hai dạng bị review cấm — `lifecycle_status in {"unknown","candidate","invalid"}`
và `invalidation_buffer != 0.0` — thay bằng `metadata_state == "unknown"`, `metadata_reason` chuỗi không rỗng,
`usable is False`, `invalidation_buffer is None`; giữ `confirmed`/`broken is False` và `lifecycle_expired is False`
làm precondition. Mỗi param assert **field còn lại hợp lệ** (`tick_size == 0.1` / `atr_current == 1`) và
`math.isnan(...)` trên field đang xét (thêm `import math`). Fixture chưa terminal (close `102.5` trong zone).

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable" -q --tb=short
2 failed
  [atr_current]: tests\...:797: result = _metadata_result(item, values=values)
                 core\smc_lifecycle.py:674: ValueError: Invalid zone boundary: nan
  [tick_size]  : như trên (cùng site _finite_float)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
55 tests collected                   (54 - 1 node bundled + 2 param)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
36 failed, 19 passed in 0.23s        (35 → 36 failed)
```

**Phân loại RED:** `implementation` — precondition PASS, RED là **raise** `ValueError` tại
`_finite_float` (`core/smc_lifecycle.py:668-675`): nonfinite phải trở thành `unknown` + threshold `None`,
không được ném lỗi. Đây là gap đã ghi ở A3-007 §6 ("Nonfinite tick/ATR ⇒ ValueError"), thuộc F02; không
phải test defect, không skip/xfail.

**Quan sát bổ sung (probe, chỉ đọc):**

```text
atr nan  -> ('raise', 'Invalid zone boundary: nan')
tick nan -> ('raise', 'Invalid zone boundary: nan')
atr inf  -> ('raise', 'Invalid zone boundary: inf')
tick -inf -> ('raise', 'Invalid zone boundary: -inf')
```

`inf`/`-inf` đi cùng nhánh `isfinite` và hiện cũng raise; **chưa** khóa bằng node riêng ở mã này (hàng
A3-017 chỉ yêu cầu parameterize ATR/tick) — để A3-063 quyết định theo audit coverage.

**Consumer đã chạy:** `tests/test_smc_confluence_task70.py`, `tests/test_smc_zone_visit_task57.py`,
`tests/test_smc_domain_models.py` → **31 passed** (không hồi quy).

**Hash mới file acceptance:** `978F4106BA23B2C9574F706A2D49AE7E5DAA5330B8DED9376A1D94A32FE28BF5`
(§A3.19 ghi `9BC772D9…`; các hash trước giữ nguyên làm lịch sử).

**Còn tồn:** conflict hai nguồn tick (A3-018), terminal + metadata thiếu (A3-020), round-trip (A3-021);
node `test_r72_07_conflicting_same_scope_tick_sources_fail_closed` vẫn giữ assert `lifecycle_status == "unknown"`
và thuộc A3-018.

### A3.21 — Conflict hai nguồn tick cùng scope: unknown là data-quality (A3-018)

Sửa `test_r72_07_conflicting_same_scope_tick_sources_fail_closed`. Assertion cũ sai nhánh:
`assert result["lifecycle_status"] == "unknown"` — `unknown` là **data-quality state**, không phải lifecycle
status (`SmcZone` còn từ chối `unknown` ở enum đóng), nên assertion đó vừa sai contract vừa không thể đúng
sau F02.

**Sửa:**

- Expected theo contract A3-007/A-D07: `metadata_state == "unknown"`, `metadata_reason` chuỗi không rỗng,
  `usable is False`, `invalidation_buffer is None` (không dùng cả `0.1` lẫn `0.2`) — tức không tự chọn bên
  thuận lợi; giữ `lifecycle_status == "confirmed"` và `broken is False`.
- Fixture đổi sang nến **chưa terminal** `[(112,114,111,113), (102,103,101,102.5)]` (close `102.5` trong
  zone) thay cho nến mặc định của `_metadata_result` — nến mặc định đóng `99.98` nên bị coi là invalidate
  bởi buffer `0`, làm trạng thái terminal lấn át đối tượng đang kiểm.
- Precondition assert: hai nguồn tick cùng scope **mâu thuẫn** (`item.tick_size == 0.2 != 0.1`),
  `atr_current == 1` hợp lệ, `low < close < high` ⇒ `unknown` chỉ có thể đến từ conflict (không phải do
  thiếu ATR/tick hay do terminal).
- Không thêm control parity (`item-only`/`argument-only`/`equal-both`) vì thuộc A3-019; không khoá chuỗi
  reason cụ thể vì đó là câu hỏi mở của A3-007.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_conflicting_same_scope_tick_sources_fail_closed" -q --tb=short
1 failed
  tests\...:837: assert result["metadata_state"] == "unknown"  →  KeyError: 'metadata_state'

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
55 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
36 failed, 19 passed in 0.23s        (không đổi số: node vốn đã RED, nay RED đúng lý do)
```

**Phân loại RED:** `interface` — field `metadata_state`/`metadata_reason` chưa tồn tại. Probe trên đúng
fixture conflict cho thấy 2 gap implementation phía sau assert:

```text
conflict: {'usable': True, 'lifecycle_status': 'confirmed', 'broken': False, 'invalidation_buffer': 0.2, 'lifecycle_expired': False}
metadata fields: False False
```

⇒ hiện item tick `0.2` **thắng âm thầm** (buffer `0.2` thay vì `None`) và zone vẫn `usable True`; đúng như
A3-007 §4 ghi. Không phải test defect, không skip/xfail.

**Consumer đã chạy:** `tests/test_smc_confluence_task70.py`, `tests/test_smc_zone_visit_task57.py`,
`tests/test_smc_domain_models.py` → **31 passed** (không hồi quy).

**Hash mới file acceptance:** `F9E6B2B0F74E94512E5C06A54E863A37BDDD3E01BC763D8119D4193E191BC5DA`
(§A3.20 ghi `978F4106…`; các hash trước giữ nguyên làm lịch sử).

**Còn tồn:** terminal + metadata thiếu (A3-020), round-trip metadata (A3-021), và parity ba cách cấp tick
(A3-019).

### A3.22 — Parity ba cách cấp tick: expected tuyệt đối (A3-019)

Siết `test_r72_07_item_and_argument_tick_sources_have_parity[buy/sell]`. Test cũ **đã** so buffer tuyệt đối
cho cả ba biến thể, nhưng phần "state" chỉ là so **tương đối** giữa ba kết quả
(`item_only["lifecycle_broken"] is argument_only[...] is both[...]`) — dạng so sánh này vẫn pass nếu cả ba
cùng sai. Đúng cảnh báo của hàng A3-019 ("không chỉ so hai kết quả cùng sai").

**Sửa:**

- Mỗi biến thể assert **tuyệt đối**: `invalidation_buffer == pytest.approx(0.1)` (giá trị suy từ fixture:
  `tick=0.1`, `ATR=1` ⇒ `max(tick, 0.05*ATR) = 0.1`), `lifecycle_broken is False`, `lifecycle_status == "confirmed"`;
  mỗi assert mang message là tên biến thể để biết ngay biến thể nào lệch.
- Thêm precondition chứng minh ba cách cấp tick **thực sự khác nhau**: `item_with_tick["tick_size"] == 0.1`
  và `"tick_size" not in item_without_tick`.
- Giữ nguyên fixture `[(112,114,111,113), (100,101,99.95,99.98)]` (close nằm trong buffer `0.1` nên zone
  còn live) và không nới assertion nào.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_item_and_argument_tick_sources_have_parity" -q --tb=short
2 failed
  [buy] : tests\...:713: assert result["invalidation_buffer"] == pytest.approx(0.1), name
          → AssertionError: argument_only | assert 0.0 == 0.1
  [sell]: như trên (cùng biến thể argument_only)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
55 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
36 failed, 19 passed in 0.23s        (không đổi số)
```

**Phân loại RED:** `implementation` — RED rơi đúng biến thể `argument_only` (không phải cả ba), nguyên nhân
là `enrich_zones` chỉ đọc `item.get("tick_size")` và **bỏ qua** tham số `tick_size`
(`core/smc_context.py:4912-4926`), thuộc F02/A-D07. Probe hai side:

```text
buy  item_only   : {'invalidation_buffer': 0.1, 'lifecycle_broken': False, 'lifecycle_status': 'confirmed'}
buy  argument_only: {'invalidation_buffer': 0.0, 'lifecycle_broken': True,  'lifecycle_status': 'confirmed'}
buy  equal_both  : {'invalidation_buffer': 0.1, 'lifecycle_broken': False, 'lifecycle_status': 'confirmed'}
sell item_only   : {'invalidation_buffer': 0.1, 'lifecycle_broken': False, 'lifecycle_status': 'confirmed'}
sell argument_only: {'invalidation_buffer': 0.0, 'lifecycle_broken': True,  'lifecycle_status': 'confirmed'}
sell equal_both  : {'invalidation_buffer': 0.1, 'lifecycle_broken': False, 'lifecycle_status': 'confirmed'}
```

⇒ hai biến thể hợp lệ khớp đúng expected tuyệt đối, nên assertion không phải test defect; không skip/xfail.

**Consumer đã chạy:** `tests/test_smc_confluence_task70.py`, `tests/test_smc_zone_visit_task57.py`,
`tests/test_smc_domain_models.py` → **31 passed** (không hồi quy).

**Hash mới file acceptance:** `06B98D133C0580CA531DD62FCB11BD7588FD4DDB233EEE9F2EC5C600FADF520F`
(§A3.21 ghi `F9E6B2B0…`; các hash trước giữ nguyên làm lịch sử).

**Còn tồn:** terminal + metadata thiếu (A3-020), round-trip metadata (A3-021).

### A3.23 — Terminal evidence + metadata thiếu: không hồi sinh zone (A3-020)

Thêm node `tests/test_smc_gate72_fix_acceptance.py::test_r72_07_unknown_metadata_does_not_revive_terminal_zone[expired_by_age|already_invalid]`
theo contract [Interface metadata (A3-007)](smc-task-72-acceptance-matrix.md#interface-metadata--chốt-theo-review-a-lần2-a3-007) §4
("bằng chứng terminal đã biết thắng"). Không sửa `core/`, probe, R56/golden.

**Hai nhánh:**

| Nhánh | Fixture | Terminal evidence | Assert chính |
|---|---|---|---|
| `expired_by_age` | H1 52 nến đều trong zone `[(105,106,104,105.5)]×52`; lifetime H1 = 50 bars | expiry theo **age** (không phụ thuộc metadata) | `lifecycle_status == "expired"` (≠ `confirmed`), `lifecycle_expired is True`, `usable is False`, `visits[0].visit_state == "open"` |
| `already_invalid` | H1 `[(112,114,111,113),(99,100,98,99)]`; item đã mang `lifecycle_status="invalid"`, `broken=True`, `usable=False` | terminal evidence **đã có trong input** | `lifecycle_status == "invalid"` (≠ `confirmed`), `lifecycle_expired is False`, `usable is False`, `visits[0].visit_state == "closed_by_invalidation"` |

Cả hai nhánh: precondition ATR hợp lệ và **không** khai nguồn tick nào (`tick_size`/`digits`/`point` vắng);
assert `metadata_state == "unknown"`, `metadata_reason` không rỗng, `invalidation_buffer is None`.
Không assert `broken` ở nhánh `already_invalid` (thuộc projection R72-08/F03) để giữ đúng phạm vi hàng A3-020.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_unknown_metadata_does_not_revive_terminal_zone" -q --tb=short
2 failed
  [expired_by_age] : tests\...:828: assert result["metadata_state"] == "unknown"  →  KeyError: 'metadata_state'
  [already_invalid]: như trên (cùng dòng)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
57 tests collected                   (55 + 2 param mới)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
38 failed, 19 passed in 0.24s        (36 → 38 failed)
```

**Phân loại RED:** `interface` — mọi assert **trước** dòng 828 PASS, gồm giữ `expired`/`invalid`, `usable
False` và `visits` còn nguyên; RED chỉ ở field `metadata_state` chưa tồn tại. Probe xác nhận gap
implementation phía sau: `invalidation_buffer` hiện `0.0` (phải `None`) ở cả hai nhánh.

**Control** (cùng nến, thêm `tick_size=0.1`) kiểm độc lập bằng probe:

```text
expired_by_age  control -> expired | usable: False | visits: 1
already_invalid control -> invalid | usable: False | visits: 1
```

⇒ trạng thái terminal đến từ fixture, không từ metadata thiếu; control chưa được thực thi trong lượt RED
(assert `metadata_state` fail trước) — ghi rõ, không nhận là đã chạy qua test.

**Sự cố trong lượt (đã khắc phục, ghi để truy vết):** một thao tác Edit đã vô tình thay mất dòng `def` của
node A3-017 và một hàng bảng `M` (`equal_and_outside_buffer_buy_sell[buy]`). Đã phát hiện ngay, khôi phục
lại đủ, và xác nhận bằng: `ast.parse` OK, `--collect-only` = 57 (khớp 55 + 2), 8/8 `def test_r72_07_*` còn
đủ, node A3-017 chạy lại đúng RED như trước, bảng R72-07 có đúng 13 hàng không trùng, `grep '||'` = 0.

**Consumer đã chạy:** `tests/test_smc_confluence_task70.py`, `tests/test_smc_zone_visit_task57.py`,
`tests/test_smc_domain_models.py` → **31 passed** (không hồi quy).

**Hash mới file acceptance:** `5B4B167D4D94541E287E1D40656196FFA97F0473E14BC27D242BA03F2C3BE83F`
(§A3.22 ghi `06B98D13…`; các hash trước giữ nguyên làm lịch sử).

**Còn tồn:** round-trip metadata qua lifecycle → context → typed (A3-021) — node cuối của cụm F01.1.

### A3.24 — Metadata qua lifecycle→context→typed round-trip (A3-021)

Thêm node `tests/test_smc_gate72_fix_acceptance.py::test_r72_07_metadata_survives_context_to_typed_round_trip`
theo hàng A3-021. Không sửa `core/`, probe, R56/golden.

**Hai stage được kiểm trong cùng node:**

1. **lifecycle → context** (`_metadata_result`): `metadata_state == "unknown"`, `metadata_reason` chuỗi không
   rỗng, `usable is False`, `invalidation_buffer is None`.
2. **context → typed → JSON** (`SmcZone.from_dict(json.loads(json.dumps(context))).to_dict()`): vẫn giữ
   `metadata_state == "unknown"`, `metadata_reason` không rỗng, `usable is False`.

Expected lấy từ contract A3-007 (unknown/fail-closed), **không** lấy từ payload production. Không assert
threshold trên payload typed vì contract đề xuất cho typed chỉ gồm `usable`/`terminal_at`/`terminal_reason`/
`lifecycle_status` — giữ đúng phạm vi A3-021.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_metadata_survives_context_to_typed_round_trip" -q --tb=short
1 failed
  tests\...:858: assert context["metadata_state"] == "unknown"  →  KeyError: 'metadata_state'

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected                   (57 + 1 node mới)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.24s        (38 → 39 failed)
```

**Phân loại RED:** `interface` — dừng ở stage lifecycle→context (field chưa có). Probe xác nhận stage **typed
cũng thiếu**: `SmcZone.from_dict(context).to_dict()` cho 73 key nhưng **không** có
`metadata_state`/`metadata_reason`/`usable`/`invalidation_buffer` ⇒ phần typed thuộc F02/F03. Không skip/xfail.

**Control (round-trip không hỏng)** — probe trên cùng fixture:

```text
identity: zone 100.0 110.0 confirmed visits: 1
metadata keys: []
```

⇒ round-trip giữ `zone_id`/bounds/`lifecycle_status`/`visits` (assert control PASS trong test), nên field
metadata thiếu là gap thật, không phải round-trip hỏng.

**Sự cố trong lượt (đã khắc phục, ghi để truy vết):** hai thao tác Edit đã **thay mất** một hàng bảng `M`
(`equal_and_outside_buffer_buy_sell[buy]`) và hàng ledger A3-020 thay vì chèn thêm. Đã phát hiện ngay, khôi
phục đủ, và xác nhận lại: bảng R72-07 có **14 hàng** không trùng (đủ cả `[buy]`/`[sell]`), ledger có **21
hàng** A3-001…A3-021, `grep '||'` = 0, `ast.parse` OK, `--collect-only` = 58.

**Consumer đã chạy:** `tests/test_smc_confluence_task70.py`, `tests/test_smc_zone_visit_task57.py`,
`tests/test_smc_domain_models.py`, `tests/test_smc_zone_models_task41.py` → **35 passed** (không hồi quy).

**Hash mới file acceptance:** `3BE3EE62829C4CDAABA9F1280FC7A127FF4EB26742B93A61D0E5376E3CED6EDE`
(§A3.23 ghi `5B4B167D…`; các hash trước giữ nguyên làm lịch sử).

**Còn lại của F01.1:** A3-022 — rà hết mô tả schema cũ còn mâu thuẫn (numeric-as-dict, default `False` mới,
unknown lifecycle) cho docs/tests cùng interface; không đổi core.

### A3.25 — Rà mô tả schema cũ còn mâu thuẫn (A3-022)

Cụm F01.1 khép lại bằng một lượt rà 3 nhóm mâu thuẫn trên `M` + file acceptance. Không sửa `core/`, probe,
R56/golden, không đổi ngưỡng/quy tắc; lịch sử review A lần2 giữ nguyên (chỉ con trỏ "đã bị thay thế").

**Nhóm 1 — numeric-as-dict.** Còn đúng **một** assertion dạng cũ trong file acceptance:
`test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` (dòng 488 bản trước: `assert isinstance(level, dict)`
rồi `level["usable_at"]`/`level["source_ids"]`). Đã chuyển sang interface A3-005:

- numeric `equal_lows` giữ `float` + trung bình cặp: `== [(100 + 100.05)/2]` và `not isinstance(level, dict)`;
- provenance đọc từ `records` bằng helper `_pool_records` (đã có từ A3-009): đúng một record
  `source_ids == ["source-a","source-b"]`, `usable_at == max(usable_at các source)` = `stamp(2)`;
- fixture thêm `usable_at` **tường minh** cho 2 source để expected không phụ thuộc quy tắc fallback
  `confirmed_at → usable_at` (chưa có quyết định) — cùng cách xử lý ở A3-009.

Giữ nguyên phần fixture/timeline của node đó: "test gọi sweep detector" là việc của **A3-039**, không làm thay.

**Nhóm 2 — default `False` mới.** Không còn mô tả nào *đang hiệu lực* đề xuất `history_complete=False`:
đề xuất cũ nằm ở bảng "Interface proposal" (đã có con trỏ thay thế bởi A3-006) và trong bảng đối chiếu A3-003
(nay thêm đính chính ngay trong hàng: default hiện hữu là `True`). Các chỗ khác dùng `history_complete=False`
chỉ với nghĩa **input của ca** (A3-012) hoặc ngữ nghĩa helper (A3-006) — đúng contract.

**Nhóm 3 — unknown lifecycle.** Kiểm bằng grep: không còn mô tả nào coi `unknown` là lifecycle status. Các
chỗ còn chữ `unknown` chỉ là (a) ghi chú lịch sử về dạng assert bị review cấm, (b) `metadata_state == "unknown"`
đúng contract, (c) câu khẳng định "unknown là data-quality, **không** phải lifecycle status".

**Command và kết quả thật:**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected in 0.13s                  (inventory không đổi)

python -m pytest <4 node đích: equal_usable_at_reclaimed, acceptance_source_must_be_usable_at_sweep_close, provisional_source_cannot_create_a_sweep, metadata_survives_context_to_typed_round_trip> -q --tb=line
4 failed, 1 passed in 0.19s                  (chỉ provisional_source… PASS; 3 RED còn lại đúng loại đã ghi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.24s                (không đổi số so với A3-021)

python -m pytest tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py tests/test_smc_domain_models.py tests/test_smc_zone_models_task41.py -q --tb=line
49 passed in 0.57s                           (không hồi quy)
```

**Phân loại RED sau khi chuyển đổi:** node vừa sửa nay RED đúng loại `interface` —
`tests\...:499: assert len(records) == 1 → 0 == 1` (canonical `records` chưa có, thuộc F06); hai assert numeric
projection phía trên **đã PASS**, nên RED không còn do test/document sai schema. Không skip/xfail.

**Hash mới file acceptance:** `0D1E96D5EF3E96B682D58F88B8CFC93A32E9410539737CA0663D11762D84746E`
(§A3.24 ghi `3BE3EE62…`; các hash trước giữ nguyên làm lịch sử).

**Trạng thái cụm F01.1 (A3-005…A3-022):** đủ mã, docs/tests đã cùng interface. RED còn lại của cụm đều là
**implementation/interface** chờ F02/F06 (metadata `metadata_state`/`metadata_reason`/`usable`/`None`,
canonical pool `records`, argument tick forwarding) — không còn RED do test/fixture/schema sai.

### A3.26 — Kiểm kê candle factory/caller (A3-023)

Mục kiểm kê mới trong `M`: [Danh sách candle factory/caller — A3-023](smc-task-72-acceptance-matrix.md#danh-sách-candle-factorycaller--a3-023),
10 đường dựng nến với 6 cột (factory, caller/node, timeframe, bước timestamp, nơi validate, positive/negative).
Hàng đối chiếu A3-003 (mục "Mọi positive factory … gọi validator") đã được nối tới mục này thay cho câu
"Chưa ghi danh sách factory/caller vào M". **Không sửa test/code** ở lượt này.

**Nguồn dữ liệu kiểm kê** (đọc code, không chạy production để sinh kết luận):
`grep -n "def run(\|Candle(\|validate_smc_candles(\|_probe.candles(\|_terminal_candles("` trên file acceptance
+ đọc helper `candles`/`lifecycle` của probe.

**Ba kết luận:**

1. **Validator:** cả 10 đường đều validate với **đúng timeframe** — trực tiếp (`_terminal_candles` D1; hai
   builder D1 inline; local `run()` H1; `test_r72_09_acceptance_corrected_task57_71…` H1;
   `test_r72_09_actual_detector_lifecycle_d1_context_chain…` H1) hoặc gián tiếp qua `_probe.candles`
   (`assert not validate_smc_candles(values, "D1" if hours == 24 else "H1")`). Không thấy đường nào thiếu
   validator ⇒ A3-027 xác nhận lại khi bổ sung.
2. **Cadence:** đúng **một** đường sai — local `run()` trong `test_r72_07_equal_and_outside_buffer_buy_sell`
   (dòng 965): `timeframe="H1"`, `tf_minutes=60` nhưng bước `timedelta(days=i)`. Đúng dạng lỗi đã ghi ở hàng
   A3-003 ⇒ **A3-028**; mã này không sửa.
3. **Negative invalid-data:** **không** có fixture invalid-data cố ý trong file acceptance — không có
   `pytest.raises(...)`/`assert validate_smc_candles(...)` nào kỳ vọng validator *thất bại*. Các ca negative ở
   đây là negative về **hành vi** (không sweep, không assignment, metadata unknown, terminal giữ nguyên). Vì
   vậy không có ca "validate negative cố ý như positive" trong file này.

**Command và kết quả thật** (docs-only, chạy để xác nhận lượt không đổi hành vi):

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected in 0.13s          (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.24s        (không đổi)
```

**Hash file acceptance:** không đổi — `0D1E96D5EF3E96B682D58F88B8CFC93A32E9410539737CA0663D11762D84746E`
(ghi ở §A3.25). Core/probe/R56/golden cũng không đổi.

### A3.27 — BUY exit candle của `_terminal_candles` (A3-024)

Xác minh fixture **đã đúng theo review ⇒ không ghi đè** (khớp ghi chú A3-003 "ĐÚNG RỒI — KHÔNG GHI ĐÈ"), rồi
làm việc xác minh **bền vững** bằng 2 assert bất biến trong nhánh BUY của chính factory.

**Số học độc lập trên `rows` (không gọi hàm production để sinh expected):** zone của consumer
`_terminal_lifecycle` là `[100, 110]`, `tick_size=0.1`, `atr_current=1`, timeframe D1 ⇒
`tolerance = max(1*tick, 0.05*ATR) = 0.1`, ngưỡng reaction `= 0.25*ATR = 0.25`.

| Điều kiện (theo review A3-024) | Giá trị từ fixture | Đạt? |
|---|---|---|
| OHLC hợp lệ | `(110.2, 110.22, 110.15, 110.2)`: `high ≥ max(open, close)`, `low ≤ min(open, close)` | ✔ (và `validate_smc_candles(values, "D1")` sẵn có trong factory) |
| Ngoài tolerance `.1` | `low 110.15 > 110 + 0.1 = 110.1` | ✔ |
| **Chưa** đạt reaction `.25` | `close − 110 = 0.2 < 0.25` | ✔ |
| Mirror SELL tương ứng | `(99.8, 99.85, 99.78, 99.8)`: `high 99.85 < 100 − 0.1`, `100 − close = 0.2 < 0.25` | ✔ (A3-026 khóa chính thức) |

**Thay đổi duy nhất:** trong `_terminal_candles` nhánh BUY, đặt tên `exit_row` và thêm 2 assert bất biến
(`exit_row[2] > zone_high + max(1*tick, 0.05*atr)`, `exit_row[3] - zone_high < 0.25*atr`) với
`zone_high, tick, atr = 110.0, 0.1, 1.0` + comment A3-024. Nhánh SELL để nguyên (A3-026); reaction candle để
nguyên (A3-025).

**Command và kết quả thật:**

```text
python -m pytest <10 node R72-06: terminal_order_before_reaction × 6, reaction_cannot_cross_expiry_boundary × 2, invalidation_precedes_expiry × 2> -v --tb=no
6 failed, 4 passed
  PASSED: [20-buy], [20-sell], invalidation_precedes_expiry_and_reaction[buy], [sell]
  FAILED: [21-buy], [21-sell], [22-buy], [22-sell], reaction_cannot_cross_expiry_boundary[buy], [sell]

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.24s        (không đổi — assert mới đều PASS)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_zone_lifecycle_task58.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py tests/test_smc_zone_lifecycle_task63.py tests/test_smc_lifecycle_task65.py -q --tb=line
42 passed in 0.55s                   (không hồi quy)
```

Consumer của helper: `_terminal_candles` chỉ được gọi bởi `_terminal_lifecycle`, và `_terminal_lifecycle` chỉ
bởi `test_r72_06_terminal_order_before_reaction_is_explicit` ⇒ đã chạy hết nhóm node đó (bảng trên).

**Phân loại:** không có RED mới; 6 RED của nhóm là các finding đã biết (F04 — reaction tại/sau terminal bị
chặn, expiry chặn reaction). `invalidation_precedes_expiry_and_reaction` **GREEN nhưng expected còn yếu**
(invalidation chưa đặt đúng candle age21) ⇒ **A3-037** siết. Không skip/xfail.

**Hash mới file acceptance:** `5CFF65276588EFAEEE5C4633205597E5E93C2AFC8DA6D08089E64EACB3EA9D84`
(§A3.26 ghi hash không đổi `0D1E96D5…`; các hash trước giữ nguyên làm lịch sử).

### A3.28 — BUY reaction candle của `_terminal_candles` (A3-025)

Fixture **đã đúng ⇒ giữ nguyên giá trị**, chỉ thêm assert bất biến để việc xác minh là bền vững và **không chỉ
dựa vào validator**.

**Điều kiện lấy từ code (đọc, không sửa):** `_follow_through_reaction_at` (`core/smc_lifecycle.py:583-634`)
dùng `threshold = 0.25 * ATR`, cửa sổ `exit_index … exit_index + 3`, và với BUY yêu cầu
`candle.close >= zone_high + threshold`; nến trong cửa sổ phải **không** invalidate, nếu invalidate thì trả
`None` (terminal ưu tiên).

**Số học độc lập trên `rows`** (zone `[100,110]`, `tick=0.1`, `ATR=1` ⇒ threshold `0.25`):

| Điều kiện (theo hàng A3-025) | Giá trị từ fixture `(112,114,111,113)` | Đạt? |
|---|---|---|
| Envelope OHLC hợp lệ | `high 114 ≥ max(112,113)`, `low 111 ≤ min(112,113)` | ✔ |
| Đủ reaction (BUY) | `close 113 ≥ 110 + 0.25 = 110.25` — biên `2.75` | ✔ |
| Không phải invalidation | `close 113 ≥ zone_low − buffer = 99.9` | ✔ |

**Thay đổi duy nhất:** nhánh BUY của `_terminal_candles` đặt tên `reaction_row` và thêm 3 assert
(envelope 2 dòng + ngưỡng reaction 1 dòng) với comment A3-025, rồi `rows[reaction_index] = reaction_row`.
Nhánh SELL để nguyên (A3-026); timeline/vị trí `reaction_index` không đổi (A3-030…A3-032).

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_terminal_order_before_reaction_is_explicit" -v --tb=no
2 passed, 4 failed
  PASSED: [20-buy], [20-sell]
  FAILED: [21-buy], [21-sell], [22-buy], [22-sell]     (RED đã biết — F04, không mới)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.24s        (không đổi — assert mới đều PASS)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_zone_lifecycle_task58.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py tests/test_smc_zone_lifecycle_task63.py tests/test_smc_lifecycle_task65.py -q --tb=line
42 passed in 0.54s                   (không hồi quy)
```

**Phân loại:** không có RED mới; 4 RED của node là finding F04 đã ghi (reaction tại/sau terminal phải bị chặn).
Không skip/xfail.

**Hash mới file acceptance:** `4C241173B8C8E1BCB845BD0CED9158EE1300BBDCD531DB2D44F258D75EBA3A0C`
(§A3.27 ghi `5CFF6527…`; các hash trước giữ nguyên làm lịch sử).

### A3.29 — SELL mirror của `_terminal_candles` (A3-026)

Xác minh mirror **exit/reaction** của nhánh SELL; fixture **giữ nguyên giá trị**, chỉ thêm assert để việc kiểm
là bền vững (mirror + nghĩa), đúng yêu cầu "high/low đảo đúng; cùng ý nghĩa exit và reaction đối xứng BUY".

**Số học độc lập** với phép mirror quanh 210 `(o, h, l, c) → (210−o, 210−l, 210−h, 210−c)`:

| Row | BUY | mirror(BUY) | SELL fixture | Khớp |
|---|---|---|---|---|
| base | `(112,114,111,113)` | `(98,99,96,97)` | `(98,99,96,97)` | ✔ |
| **exit** | `(110.2,110.22,110.15,110.2)` | `(99.8,99.85,99.78,99.8)` | `(99.8,99.85,99.78,99.8)` | ✔ |
| **reaction** | `(112,114,111,113)` | `(98,99,96,97)` | `(98,99,96,97)` | ✔ |
| touch | `(109,110,105,109)` | `(101,105,100,101)` | `(101,105,99,102)` | ✖ lệch |

Nghĩa đối xứng (zone `[100,110]`, `tick=0.1`, `ATR=1` ⇒ tolerance `0.1`, reaction `0.25`):

- exit dưới vùng mở rộng: `high 99.85 < 100 − 0.1 = 99.9` ✔
- chưa đạt reaction: `100 − close 99.8 = 0.2 < 0.25` ✔
- reaction đạt ngưỡng SELL: `close 97 ≤ 100 − 0.25 = 99.75` ✔ (biên 2.75, đối xứng BUY)

**Phát hiện ngoài phạm vi (đã ghi vào `M` §CHƯA RÕ):** candle **touch** `rows[19]` của SELL **không** phải
mirror tuyệt đối (`low` 99 vs 100, `close` 102 vs 101). Tương đương về nghĩa — cả hai đều overlap zone
(`high 105 ≥ 99.9`, `low 99 ≤ 110.1`) và đều **không** invalidate (`close 102 ≤ 110.1`) — nên A3-026 không đổi
(nhánh chỉ được yêu cầu khóa exit/reaction, và sửa sẽ đổi fixture dùng bởi nhóm R72-06). Đề xuất
A3-080/A3-063 quyết định chuẩn hoá.

**Thay đổi:** nhánh SELL của `_terminal_candles` thêm `mirror()` cục bộ, đặt tên `exit_row`/`reaction_row`,
2 assert mirror (`== mirror(<BUY literal>)`) và 5 assert nghĩa (envelope ×2, exit tolerance, below-reaction,
reaction threshold) + comment A3-026.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_terminal_order_before_reaction_is_explicit" -v --tb=no
2 passed, 4 failed
  PASSED: [20-buy], [20-sell]           FAILED: [21-buy], [21-sell], [22-buy], [22-sell]   (RED đã biết — F04)

python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary" -q --tb=no
2 failed                                 (RED đã biết)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected                       (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.24s            (không đổi — assert mới đều PASS)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_zone_lifecycle_task58.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py tests/test_smc_zone_lifecycle_task63.py tests/test_smc_lifecycle_task65.py -q --tb=line
42 passed in 0.55s                       (không hồi quy)
```

**Hash mới file acceptance:** `819ED76914E1F6BAB0280533D53846C30FC9D706FE77115D6BD94DD19A5A65A2`
(§A3.28 ghi `4C241173…`; các hash trước giữ nguyên làm lịch sử).

### A3.30 — Validator trên mọi đường tạo nến (A3-027)

Rà lại theo đúng tiêu chí hàng A3-027: **đúng timeframe** và **trước evaluator**. Phương pháp: script quét
thứ tự trong file acceptance (gom theo hàm bao: builder → validator → evaluator) + đọc trực tiếp
`_probe.candles`/`_probe.attach` (read-only).

**Kết quả (không phát hiện đường thiếu validator ⇒ không cần bổ sung):**

| Call site validator | Timeframe | Builder đứng trước | Evaluator phía sau |
|---|---|---|---|
| file acceptance dòng 131 (`_terminal_candles`) | `"D1"` | `Candle(...)` trong chính hàm | — (factory trả về cho consumer) |
| dòng 333 (`test_r72_09_acceptance_corrected_task57_71…`) | `"H1"` (+ tên nhóm trong message) | `module._candles(rows)` của task59/60/62/63/65 | — |
| dòng 678 (`test_r72_05_cutoff_equal_invalidated_at_is_terminal`) | `"D1"` | `Candle(...)` inline | `analyze_zone_lifecycle` (679) + `build_d1_reaction_evidence` (685) |
| dòng 722 (`test_r72_06_invalidation_precedes_expiry_and_reaction`) | `"D1"` | `Candle(...)` inline (720) | `analyze_zone_lifecycle` (723) |
| dòng 1000 (local `run()` trong `test_r72_07_equal_and_outside_buffer_buy_sell`) | `"H1"` | `Candle(...)` inline (998) | `analyze_zone_lifecycle` (1001) |
| dòng 1074 (`test_r72_09_actual_detector_lifecycle_d1_context_chain…`) | `"H1"` | `module._candles(module._fixture_rows())` (1073) | detector (1075) → `enrich_zones` (1078) → typed/`analyze_zone_lifecycle`/D1 (1084, 1091) |
| probe dòng 39 (`_probe.candles` — dùng chung) | `"D1" if hours == 24 else "H1"` | `Candle(...)` trong probe | mọi evaluator của consumer (lifecycle/enrich/detector/attach) |
| probe dòng 187 (golden check nội bộ probe) | `"H1"` | nến task60 trong probe | — |

Mọi đường **không** có validator tường minh đều nhận nến từ `_probe.candles` hoặc `_terminal_candles` — cả hai
validate **trước khi trả về**, nên validator luôn chạy trước evaluator. `_probe.attach` (đường context) cũng
đi qua `candles([(120,121,119,120)]*20)` của probe.

**Kiểm hai điều kiện phủ định của hàng A3-027:**

1. **Không nới validator:** cả 8 call site đều truyền timeframe tường minh; không có call dạng
   `validate_smc_candles(values)` thiếu tham số.
2. **Không validate negative cố ý như positive:** không có `pytest.raises`/`assert validate_smc_candles(...)`
   nào kỳ vọng validator *thất bại*; các ca negative trong file là negative về hành vi (không sweep/không
   assignment/metadata unknown/terminal giữ nguyên).

**Command và kết quả thật** (không sửa gì nên chỉ chạy xác nhận):

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected in 0.13s          (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.24s        (không đổi)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py tests/test_smc_fvg_fill_task62.py -q --tb=line
25 passed in 0.30s                   (không hồi quy)
```

**Hash file acceptance: không đổi** — `819ED76914E1F6BAB0280533D53846C30FC9D706FE77115D6BD94DD19A5A65A2`
(ghi ở §A3.29). Core/probe/R56/golden cũng không đổi.

### A3.31 — Đồng bộ cadence timestamp với timeframe (A3-028)

Sửa **một** đường duy nhất còn sai cadence (đường #7 ở bảng kiểm kê §A3.26): local `run()` trong
`test_r72_07_equal_and_outside_buffer_buy_sell` — fixture H1 (`timeframe="H1"`, `tf_minutes=60`) nhưng dựng
nến bằng `start + timedelta(days=i)`.

**Sửa:** `timedelta(days=i)` → `timedelta(hours=i)` + comment A3-028; thêm assert bất biến
`values[1].time - values[0].time == timedelta(hours=1)` để lần sau không âm thầm quay lại bước ngày.

**Vì sao trung tính hành vi với fixture này:**

- Assertion của node chỉ phụ thuộc `invalidation_buffer` (`max(tick, 0.05*ATR) = max(0.1, 0.1) = 0.1`) và
  `lifecycle_broken` (exact close `99.9` không vượt buffer; beyond close `99.89` vượt) — không phụ thuộc
  timestamp.
- `_age_anchor_index` (`core/smc_lifecycle.py:522-537`) khi `available_at=None` trả `safe_origin` (fixture
  truyền `origin_index=0`) ⇒ không dùng timestamp để tính age; 2 nến vẫn `age = 1` ≪ H1 stale 50.
- `_candle_close` vẫn cho mốc đúng giờ (start `00:00Z`, bước 1 giờ) nên không phát sinh nhánh gap khác.

**Ba đường D1 còn lại** (`_terminal_candles` dòng 126, R72-05 dòng 676, R72-06 dòng 720) đã dùng bước
**ngày** đúng timeframe ⇒ **giữ nguyên**, không đụng.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_equal_and_outside_buffer_buy_sell" -v --tb=short
2 passed                             ([buy] PASSED, [sell] PASSED — giữ GREEN sau khi đổi cadence)

python -m pytest <3 node R72-07 nhóm buffer/parity/missing-ATR> -q --tb=line
3 failed, 2 passed                   (2 passed = đúng node buffer cả 2 side; 3 failed là RED đã biết: parity ×2, missing ATR)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.24s        (không đổi)

python -m pytest tests/test_smc_lifecycle_task65.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py tests/test_smc_zone_visit_task57.py -q --tb=line
31 passed in 0.36s                   (không hồi quy)
```

**Phân loại:** không có RED mới; thay đổi là **sửa fixture defect** (cadence) đã được review nêu ở hàng A3-003,
không nới assertion nào.

**Hash mới file acceptance:** `58D6F6377391231F76E6F492EAC42239E6621D04E552DB2A7BA4DA1ED0099940`
(§A3.30 ghi hash không đổi `819ED769…`; các hash trước giữ nguyên làm lịch sử).

### A3.32 — Timeline D1 terminal (A3-029)

Mục `M`: [Timeline D1 terminal — A3-029](smc-task-72-acceptance-matrix.md#timeline-d1-terminal--a3-029). Docs-only,
**không sửa test/core**. Expected tính từ quy tắc: fixture (`_terminal_candles`: 23 nến D1, `time = 2026-09-01T00:00Z
+ index ngày`) + anchor (`_age_anchor_index`: `available_at=None` ⇒ anchor = `origin_index = 0`) + lifetime
(`_STALE_AFTER_BARS["D1"] = 20`) + close (`candle_close_at` = open + 1 ngày).

**Bảng đã ghi vào `M` (index 19–22):**

| Index | Age | Open | Close D1 | Vai trò |
|---|---|---|---|---|
| 19 | 19 | `2026-09-20T00:00Z` | `2026-09-21T00:00Z` | touch — mở visit |
| 20 | 20 | `2026-09-21T00:00Z` | `2026-09-22T00:00Z` | **chưa terminal** (`20 > 20` sai) — exit; reaction tại đây hợp lệ |
| 21 | 21 | `2026-09-22T00:00Z` | `2026-09-23T00:00Z` | **terminal** — `expiry_index=21`, `expired_at=2026-09-23T00:00Z`; không tạo reaction |
| 22 | 22 | `2026-09-23T00:00Z` | `2026-09-24T00:00Z` | sau terminal — không reaction mới |

Kèm cảnh báo quy tắc: `age(i) = i − anchor` với `anchor = origin_index` **chỉ khi** `available_at is None`; có
`available_at` thì anchor là nến đầu có close ≥ mốc ⇒ không được suy age từ index.

**Command và kết quả thật** (xác nhận mốc, không dùng làm expected):

```text
python - <<'PY'  (gọi _terminal_lifecycle cho reaction_index 20/21/22)
reaction_index=20: age_bars=22 expiry_index=21 expired_at=2026-09-23T00:00:00+00:00 reacted=2026-09-22T00:00:00+00:00 state=completed_reacted
reaction_index=21: age_bars=22 expiry_index=21 expired_at=2026-09-23T00:00:00+00:00 reacted=2026-09-23T00:00:00+00:00 state=completed_reacted
reaction_index=22: age_bars=22 expiry_index=21 expired_at=2026-09-23T00:00:00+00:00 reacted=2026-09-24T00:00:00+00:00 state=completed_reacted
closes idx19..22: ['2026-09-21T00:00:00+00:00', '2026-09-22T00:00:00+00:00', '2026-09-23T00:00:00+00:00', '2026-09-24T00:00:00+00:00']
PY

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.24s        (không đổi)
```

⇒ `expiry_index`/`expired_at`/`age_bars` khớp bảng; khác biệt là `reacted_at` **có** giá trị ở index 21/22 —
đúng gap **F04** mà các node `[21-*]`/`[22-*]`/`reaction_cannot_cross_expiry_boundary` đang RED, không phải lỗi
fixture. Không skip/xfail, không đổi test.

**Hash file acceptance: không đổi** — `58D6F6377391231F76E6F492EAC42239E6621D04E552DB2A7BA4DA1ED0099940`
(§A3.31). Core/probe/R56/golden cũng không đổi.

### A3.33 — D1 reaction trước terminal: đúng thời điểm và giữ qua append (A3-030)

Siết nhánh `reaction_index == 20` của `test_r72_06_terminal_order_before_reaction_is_explicit`. Trước đây chỉ
assert `reacted_at is not None` ⇒ không khóa được "**đúng** `reacted_at`" và không chứng minh được việc
**append candle terminal không đổi thời điểm**.

**Thay đổi:**

1. Helper test-local `_terminal_lifecycle(side, reaction_index, candles=None)` — thêm tham số `candles` để
   chạy được **prefix 21 nến** (`_terminal_candles(side, 20)[:21]`, kết thúc đúng candle reaction). Consumer
   duy nhất của helper là node này nên thay đổi additive, không ảnh hưởng node khác.
2. Expected tính **độc lập**: `datetime(2026, 9, 1, tzinfo=utc) + timedelta(days=21)` =
   `2026-09-22T00:00:00+00:00` — close của nến idx20 (open idx20 = start + 20 ngày, D1 close = open + 1 ngày),
   khớp bảng timeline §A3-029.
3. Assert cho **cả prefix và full**: `visits[0].reacted_at == expected`, `visit_state == "completed_reacted"`,
   và `prefix.lifecycle_expired is False` (prefix chưa tới terminal) ⇒ khi append candle terminal (index 21)
   thời điểm reaction **không đổi** và lịch sử được giữ.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_terminal_order_before_reaction_is_explicit" -v --tb=short
2 passed, 4 failed
  PASSED: [20-buy], [20-sell]          (nay siết chặt hơn, vẫn xanh)
  FAILED: [21-buy], [21-sell], [22-buy], [22-sell]   (RED đã biết — F04)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.25s        (không đổi)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py -q --tb=line
31 passed in 0.37s                   (không hồi quy)
```

**Phân loại:** nhánh [20] không có RED; 4 RED của node là finding **F04** đã ghi. Probe độc lập xác nhận
`prefix(21)` và `full(23)` cùng cho `reacted_at=2026-09-22T00:00:00+00:00`, `visit_state=completed_reacted` —
tức hành vi hiện tại đã đúng cho nhánh "trước terminal" và nay đã được khóa bằng assertion chặt.

**Hash mới file acceptance:** `B2390C267C5D2FF29FAD53D9819DFD0961712750810DBD935B1E320799A732B9`
(§A3.32 ghi hash không đổi `58D6F637…`; các hash trước giữ nguyên làm lịch sử).

### A3.34 — D1 reaction tại candle terminal: terminal index/close + bằng chứng đã vào vùng (A3-031)

Siết nhánh `else` của `test_r72_06_terminal_order_before_reaction_is_explicit` (phủ `reaction_index` 21 và 22).
Trước đây chỉ có `lifecycle_expired is True` + `reacted_at is None` + `completed_unreacted` ⇒ (a) chưa khóa
**timestamp/index** của terminal, (b) chưa chứng minh zone **từng được vào** nên "không reaction" có thể pass
một cách vô nghĩa.

**Thêm vào nhánh `else`** (expected tính độc lập: `start + N ngày`, D1 close = open + 1 ngày; khớp bảng
§A3-029):

```text
assert visit.entered_at == (start + timedelta(days=20)).isoformat()   # close idx19
assert visit.exited_at  == (start + timedelta(days=21)).isoformat()   # close idx20
assert visit.bars_spent_inside >= 1
assert state.lifecycle_expired is True
assert state.expiry_index == 21
assert state.expired_at == (start + timedelta(days=22)).isoformat()   # close idx21
assert visit.reacted_at is None
assert visit.visit_state == "completed_unreacted"
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_terminal_order_before_reaction_is_explicit" -v --tb=line
2 passed, 4 failed
  PASSED: [20-buy], [20-sell]
  FAILED: [21-buy]=reacted_at '2026-09-23T00:00:00+00:00' is None
          [21-sell]=như trên
          [22-buy]=reacted_at '2026-09-24T00:00:00+00:00' is None
          [22-sell]=như trên

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.24s        (không đổi)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py -q --tb=line
31 passed in 0.36s                   (không hồi quy)
```

**Phân loại RED:** `implementation` (F04) và **chỉ còn ở 2 assert cuối** — mọi assert mới (entry/exit/bars,
`expiry_index == 21`, `expired_at`) đều **PASS** ⇒ fixture và terminal timestamp đã đúng; gap duy nhất là
reaction vẫn được ghi tại candle terminal (`reacted_at` = close idx21 cho `[21]`) và sau terminal
(`reacted_at` = close idx22 cho `[22]`). Probe độc lập xác nhận `entered_at=2026-09-21T00:00Z`,
`exited_at=2026-09-22T00:00Z`, `bars=1`, `expiry_index=21`, `expired_at=2026-09-23T00:00Z` cho cả 3
`reaction_index`.

**Ghi chú cho A3-032:** `[21]` và `[22]` dùng **chung** nhánh `else`, nên phần "visit/history trước terminal còn
nguyên" (entered/exited/state) đã được phủ; A3-032 xác minh lại và chỉ bổ sung nếu còn thiếu (ví dụ so trực
tiếp với prefix).

**Hash mới file acceptance:** `EA9DFE2BBA94F29451A494FC3BD075E7F0050CCE98E3C5C991736816D8E132A9`
(§A3.33 ghi `B2390C26…`; các hash trước giữ nguyên làm lịch sử).

### A3.35 — Candle sau terminal không đổi visit/history (A3-032)

Bổ sung **một** khối assert vào nhánh `else` của `test_r72_06_terminal_order_before_reaction_is_explicit`
(dùng lại tham số `candles` đã thêm ở A3-030): chạy lại cùng fixture **bỏ candle cuối** (22 nến, tức chuỗi kết
thúc đúng ở candle terminal index 21) và so visit với bản đầy đủ 23 nến.

```python
trimmed = _terminal_lifecycle(side, reaction_index, candles=_terminal_candles(side, reaction_index)[:22])
assert trimmed.visits[0] == visit
```

Ý nghĩa: khóa trực tiếp "**visit/history trước terminal còn nguyên**" khi có thêm candle **sau** terminal — nếu
candle sau terminal làm đổi visit (như hiện tại), assert này fail.

**Kiểm chứng độc lập (probe, vì lượt RED dừng ở assert phía trên):**

```text
ri=21: full.reacted=2026-09-23T00:00:00+00:00 trimmed.reacted=2026-09-23T00:00:00+00:00 | equal visits: True
ri=22: full.reacted=2026-09-24T00:00:00+00:00 trimmed.reacted=None | equal visits: False
   fields differing: ['reacted_at', 'visit_state']
```

⇒ Với `ri=21` assert **PASS** ngay hôm nay (candle thừa nằm sau mốc break nên không được xử lý). Với `ri=22`
hiện **khác đúng 2 field** `reacted_at`/`visit_state` — chính là gap **F04** (candle sau terminal đang tạo
reaction `2026-09-24`); sau khi F04 sửa, cả hai phía đều `reacted_at=None`/`completed_unreacted` nên assert
satisfiable, không phải ràng buộc bất khả thi.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_terminal_order_before_reaction_is_explicit" -v --tb=line
2 passed, 4 failed
  PASSED: [20-buy], [20-sell]
  FAILED: [21-buy]/[21-sell] (reacted_at '2026-09-23T00:00:00+00:00' is None)
          [22-buy]/[22-sell] (reacted_at '2026-09-24T00:00:00+00:00' is None)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.25s        (không đổi)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py -q --tb=line
31 passed in 0.37s                   (không hồi quy)
```

**Phân loại:** RED của node vẫn là `implementation` (F04); assert mới **chưa được thực thi** trong lượt RED
(fail-fast ở `reacted_at is None`) — đã kiểm độc lập bằng probe và ghi rõ, không nhận là đã chạy qua test.

**Hash mới file acceptance:** `6A66F7090D0D64938F88E564693C81216636AD15C611C0FB2F6CA97203F6CFE6`
(§A3.34 ghi `EA9DFE2B…`; các hash trước giữ nguyên làm lịch sử).

### A3.36 — Timeline H4 terminal (A3-033)

Mục `M`: [Timeline H4 terminal — A3-033](smc-task-72-acceptance-matrix.md#timeline-h4-terminal--a3-033).
Docs-only, **không sửa test/core**; mọi số lấy từ hằng số đã duyệt + quy tắc A-D04/A-D05, không thêm
quy tắc/ngưỡng mới. Fixture H4 là **đề xuất** cho A3-034…A3-036 (ba mã đó viết node — hàng đối chiếu A3-003
ghi rõ hiện `H4: không có node nào`).

**Nguồn số (đọc code, không lấy output production làm expected):**

```text
H4 interval seconds: 14400 = 4.0h          (SMC_TIMEFRAME_INTERVALS["H4"])
H4 lifetime (stale_after_bars): 30         (_STALE_AFTER_BARS["H4"])
terminal age = lifetime + 1 = 31
idx29: age=29 open=2026-09-05T20:00:00+00:00 close=2026-09-06T00:00:00+00:00
idx30: age=30 open=2026-09-06T00:00:00+00:00 close=2026-09-06T04:00:00+00:00
idx31: age=31 open=2026-09-06T04:00:00+00:00 close=2026-09-06T08:00:00+00:00
idx32: age=32 open=2026-09-06T08:00:00+00:00 close=2026-09-06T12:00:00+00:00
candles needed = lifetime + 3 = 33
D1 cross-check: lifetime 20 -> terminal index 21 | candles 23   (khớp fixture _terminal_candles thật)
```

**Quy tắc đã ghi:** lifetime `L` ⇒ touch `L−1`, exit `L`, terminal `L+1`, sau terminal `L+2`, tổng `L+3` nến;
với H4 (`L=30`) ⇒ touch idx29, exit idx30, **terminal idx31** (`expired_at = 2026-09-06T08:00Z`), sau terminal
idx32; anchor `age(i) = i` khi `origin_index = 0` và không `available_at`; đánh giá tại **candle close**
(cutoff bằng mốc terminal là terminal — A-D04); thứ tự availability/cutoff → invalidation/expiry → exit →
reaction (A-D05); follow-through window `exit_index … exit_index+3`, ngưỡng `0.25*ATR`, invalidation ưu tiên.

**Command và kết quả thật** (docs-only, chạy xác nhận lượt không đổi hành vi):

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
58 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 19 passed in 0.25s        (không đổi)
```

**Hash file acceptance: không đổi** — `6A66F7090D0D64938F88E564693C81216636AD15C611C0FB2F6CA97203F6CFE6`
(§A3.35). Core/probe/R56/golden cũng không đổi.

### A3.37 — H4 reaction trước terminal (A3-034)

H4 chưa có node nào (hàng đối chiếu A3-003), nên mã này **viết mới** fixture + node theo timeline §A3-033.

**Fixture mới trong file acceptance:**

- `_h4_terminal_candles(side, reaction_index)`: **33 nến bước 4h**, `start = 2026-09-01T00:00Z`, cấu trúc đối ứng
  D1 (touch idx29, exit idx30, terminal idx31, sau terminal idx32) với `rows[30:33]` là exit row và
  `rows[reaction_index]` là reaction row; assert bất biến geometry cho **cả BUY và SELL** (exit ngoài vùng mở
  rộng, chưa đủ reaction; reaction đạt ngưỡng), assert cadence `values[1].time - values[0].time == timedelta(hours=4)`,
  và `validate_smc_candles(values, "H4")`.
- `_h4_terminal_lifecycle(side, reaction_index)`: `analyze_zone_lifecycle(..., timeframe="H4", tf_minutes=240, tick_size=0.1, atr_current=1)`.

**Node mới:** `test_r72_06_h4_reaction_before_terminal_is_retained[buy/sell]` — H4 lifetime 30 ⇒ reaction ở age30
(idx30) vẫn **trước** terminal (idx31). Expected tính từ quy ước fixture (`start + 4h·i + 4h`), không lấy output
production:

```text
entered_at  == 2026-09-06T00:00:00+00:00   (close idx29)
exited_at   == 2026-09-06T04:00:00+00:00   (close idx30)
reacted_at  == 2026-09-06T04:00:00+00:00   (exit + reaction cùng close, chưa terminal)
bars_spent_inside >= 1; visit_state == "completed_reacted"
lifecycle_expired is True; expiry_index == 31; expired_at == 2026-09-06T08:00:00+00:00 (close idx31)
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_h4_reaction_before_terminal_is_retained" -v --tb=short
2 passed                             ([buy] PASSED, [sell] PASSED)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
60 tests collected                   (58 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
39 failed, 21 passed in 0.25s        (passed 19 → 21; failed không đổi)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py -q --tb=line
31 passed in 0.36s                   (không hồi quy)
```

**Phân loại:** node **GREEN** cả 2 side — hành vi H4 "reaction trước terminal" hiện đã đúng (đối ứng D1 `[20]`),
không có RED mới. Probe trước khi viết test cũng cho cùng kết quả (`entered 00:00Z / exited 04:00Z / reacted
04:00Z / expired 08:00Z`, expiry_index 31) nên fixture + expected độc lập khớp nhau.

**Hash mới file acceptance:** `885E87960999556326EC770AFA26D1C17C606E65D220C62FEB9D09AF3BDB5C9A`
(§A3.36 ghi hash không đổi `6A66F709…`; các hash trước giữ nguyên làm lịch sử).

### A3.38 — H4 reaction đúng terminal (A3-035)

Node mới `test_r72_06_h4_reaction_at_terminal_is_blocked[buy/sell]`, dùng lại fixture H4 của A3-034 với
`reaction_index = 31` (đúng candle terminal). Không đổi fixture, không sửa `core/`.

**Assert (expected từ quy ước fixture + bảng §A3-033):**

```text
precondition: expiry_index == 31                 # reaction candle = terminal candle
entered_at  == 2026-09-06T00:00:00+00:00         # close idx29 (vùng thật sự được vào)
exited_at   == 2026-09-06T04:00:00+00:00         # close idx30
bars_spent_inside >= 1
lifecycle_expired is True
expired_at  == 2026-09-06T08:00:00+00:00         # close idx31 — terminal evidence rõ
reacted_at is None                               # contract A-D05
visit_state == "completed_unreacted"
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_h4_reaction_at_terminal_is_blocked" -q --tb=line
2 failed
  tests\...:801: assert '2026-09-06T08:00:00+00:00' is None   (cả [buy] và [sell])

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
62 tests collected                   (60 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
41 failed, 21 passed in 0.25s        (failed 39 → 41, passed giữ 21)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py -q --tb=line
31 passed in 0.38s                   (không hồi quy)
```

**Phân loại RED:** `implementation` (F04) và fail **chỉ ở assert `reacted_at is None`** — mọi assert trước đó
(entry/exit/bars, `expiry_index == 31`, `expired_at`) **PASS**, nên terminal evidence của fixture đúng; gap là
reaction vẫn được tạo tại chính candle terminal (`reacted_at = 2026-09-06T08:00Z`). Probe trước khi viết test
cho cùng kết quả (`expiry_index=31`, `expired_at=2026-09-06T08:00Z`, `reacted=2026-09-06T08:00Z`).

**Sự cố trong lượt (đã khắc phục, ghi để truy vết):** một thao tác Edit đã **thay mất dòng decorator
`@pytest.mark.parametrize("reaction_index", [20, 21, 22])`** của node D1 `test_r72_06_terminal_order_...`
(và làm node mới chèn đè phần đầu), cùng lúc một Edit khác **thay mất hàng bảng `M`** của
`test_r72_06_invalidation_precedes_expiry_and_reaction[buy]`. Đã khôi phục cả hai ngay và xác nhận lại:
`ast.parse` OK, node D1 trở lại **6 param** với đúng trạng thái cũ (2 PASSED `[20]`, 4 FAILED `[21]/[22]`),
bảng R72-06 có **14 hàng không trùng** (đủ 2 hàng invalidation + 4 hàng H4), `grep '||'` = 0.

**Hash mới file acceptance:** `8EB33A305EEA34002ADB7A5F99F8439DAC89B22B46EE89DF4C3C955954557FC4`
(§A3.37 ghi `885E8796…`; các hash trước giữ nguyên làm lịch sử).

### A3.39 — H4 reaction sau terminal (A3-036)

Node mới `test_r72_06_h4_reaction_after_terminal_is_blocked[buy/sell]`, dùng fixture H4 của A3-034 với
`reaction_index = 32` (sau candle terminal idx31). Không đổi fixture, không sửa `core/`.

**Assert (expected từ quy ước fixture + bảng §A3-033):**

```text
precondition: expiry_index == 31                  # terminal vẫn ở idx31
entered_at  == 2026-09-06T00:00:00+00:00          # close idx29
exited_at   == 2026-09-06T04:00:00+00:00          # close idx30
bars_spent_inside >= 1
lifecycle_expired is True; expired_at == 2026-09-06T08:00:00+00:00   # close idx31
reacted_at is None; visit_state == "completed_unreacted"
trimmed = run bỏ idx32 ([:32]) ⇒ trimmed.visits[0] == visit           # không mất lịch sử trước đó
```

Helper `_h4_terminal_lifecycle(side, reaction_index, candles=None)` được mở rộng (additive, giống A3-030 làm
cho helper D1) để chạy được bản "bỏ candle sau terminal".

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_h4_reaction_after_terminal_is_blocked" -q --tb=line
2 failed
  tests\...:829: assert '2026-09-06T12:00:00+00:00' is None   (cả [buy] và [sell])

python -m pytest <4 node H4 + node D1 terminal_order> -v --tb=line
  h4_reaction_before_terminal_is_retained: 2 PASSED
  h4_reaction_at_terminal_is_blocked:      2 FAILED (RED đã biết — F04)
  h4_reaction_after_terminal_is_blocked:   2 FAILED (RED mới — F04)
  terminal_order_before_reaction_is_explicit: 2 PASSED [20], 4 FAILED [21]/[22] (đúng như trước)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
64 tests collected                   (62 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
43 failed, 21 passed in 0.24s        (failed 41 → 43, passed giữ 21)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py -q --tb=line
31 passed in 0.37s                   (không hồi quy)
```

**Phân loại RED:** `implementation` (F04) — fail ở `reacted_at is None` với `reacted_at = 2026-09-06T12:00Z`
(= close idx32): candle **sau** terminal vẫn tạo reaction. Probe độc lập trước khi viết test: bản `trimmed`
(bỏ idx32) cho `reacted=None`/`completed_unreacted`, tức **khác** bản full ở 2 field `reacted_at`/`visit_state`
⇒ assert so-sánh là hợp lệ và sẽ chặn hồi quy sau khi F04 sửa; mọi assert trước đó (entry/exit/bars,
`expiry_index == 31`, `expired_at`) đều **PASS**.

**Sự cố trong lượt (đã khắc phục, ghi để truy vết):** một thao tác Edit lại **thay mất** (a) dòng decorator
`@pytest.mark.parametrize("reaction_index", [20, 21, 22])` và (b) dòng đầu thân hàm
`state = _terminal_lifecycle(side, reaction_index)` của node D1. Đã khôi phục ngay và xác nhận **bằng hành vi**:
node D1 trở lại **6 param** đúng trạng thái cũ (2 PASSED `[20]`, 4 FAILED `[21]/[22]`), `ast.parse` OK,
`--collect-only` = 64 (khớp 62 + 2), bảng `M` R72-06 đúng **16 hàng không trùng** (đủ 6 hàng H4 + 2 hàng
invalidation), `grep '||'` = 0. Lượt này tôi đã chuyển sang kỹ thuật chèn-sau-dòng-neo cho `M`; lỗi còn lại
nằm ở thao tác Edit trên file test.

**Hash mới file acceptance:** `5E330EE7B6BD8FF99817D13E7BB4BA3BB93EBB790070ECD1C1F8FA7D4D15628B`
(§A3.38 ghi `8EB33A30…`; các hash trước giữ nguyên làm lịch sử).

### A3.40 — Invalidation tại candle hết lifetime (A3-037)

Sửa `test_r72_06_invalidation_precedes_expiry_and_reaction[buy/sell]`. Fixture cũ đặt invalidation ở
**row20 (age20)** nên **không** chạm mốc expiry (age21) ⇒ chưa kiểm được "invalidation ưu tiên expiry", và chỉ
assert `lifecycle_broken is True` + `reacted_at is None` (đúng như hàng đối chiếu A3-003 ghi "⇒ cần sửa").

**Fixture mới (22 nến D1, cùng quy ước `start = 2026-09-01T00:00Z`):**

| Index | BUY | SELL | Vai trò |
|---|---|---|---|
| 19 | `(109,110,105,109)` | `(101,105,99,102)` | touch — mở visit (overlap zone `[100,110]`) |
| 20 | `(110.2,110.22,110.15,110.2)` | `(99.8,99.85,99.78,99.8)` | exit ngoài vùng mở rộng, **chưa** đủ reaction (0.2 < 0.25) ⇒ mở follow-through window `20…23` |
| **21** | `(99,100,98,99)` | `(111,112,109,111)` | **invalidation đúng candle hết lifetime** (age21 > lifetime 20) và nằm trong window ⇒ chặn reaction |

Không dựng close vừa phá distal vừa phản ứng ngược hướng (bất khả thi trong 1 candle) — đúng yêu cầu hàng A3-037.

**Assert thêm (expected tính từ fixture + bảng §A3-029):**

```text
lifecycle_broken is True; invalidation_index == 21; invalidated_at == 2026-09-23T00:00:00+00:00
expiry_index is None; lifecycle_expired is False        # invalidation thắng expiry cùng candle
visit: entered_at == 2026-09-21T00:00:00+00:00 (close idx19)
       exited_at  == 2026-09-22T00:00:00+00:00 (close idx20)
       visit_state == "completed_unreacted"; reacted_at is None
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_invalidation_precedes_expiry_and_reaction" -v --tb=short
2 passed                             ([buy] PASSED, [sell] PASSED)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
64 tests collected                   (không đổi — không thêm node)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
43 failed, 21 passed in 0.25s        (không đổi)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py -q --tb=line
31 passed in 0.37s                   (không hồi quy)
```

**Phân loại:** không có RED mới — hành vi "invalidation ưu tiên expiry" của implementation đã đúng; việc của
A3-037 là **sửa fixture + khóa expected** (trước đây node GREEN nhưng expected yếu). Probe độc lập trước khi sửa
cho đúng các giá trị đã khóa (`invalidation_index=21`, `invalidated_at=2026-09-23T00:00Z`, `broken=True`,
`expiry_index=None`, `lifecycle_expired=False`, visit `entered 09-21 / exited 09-22 / reacted None`).

**Hash mới file acceptance:** `7D6D92D42F57710FB736B2A06467E85F50DF2D15E15250A1634A205F8E1903F1`
(§A3.39 ghi `5E330EE7…`; các hash trước giữ nguyên làm lịch sử).

### A3.41 — Terminal state qua enrich→restore→enrich (A3-038)

Node mới `test_r72_06_terminal_state_survives_enrich_restore_enrich[expired|invalid-buy/sell]` (4 node) — node
cuối của cụm F01.2. Chuỗi được kiểm: `enrich_zones(item, candles, ...)` → `json.dumps/loads` → `enrich_zones`
**lại** trên dict đã restore, cùng fixture D1 và cùng item.

**Hai nhánh fixture (expected tính từ fixture + bảng §A3-029, không lấy output lượt 1 làm chuẩn):**

| Nhánh | Fixture | Terminal evidence | Reaction trước terminal |
|---|---|---|---|
| `expired` | `_terminal_candles(side, 20)` (touch idx19, reaction idx20, idx21/22 ngoài **không** invalidation) | `expired_at == 2026-09-23T00:00Z`, `expiry_index == 21`, `lifecycle_broken is False` | `reacted_at == 2026-09-22T00:00Z` |
| `invalid` | dựng inline: touch idx19, reaction idx20, **invalidation idx21** (BUY `(99,100,98,99)`, SELL `(111,112,109,111)`) | `invalidated_at == 2026-09-23T00:00Z`, `invalidation_index == 21`, `lifecycle_expired is False` | như trên |

Assert chung: `zone_id` không đổi; `lifecycle_status` giữ đúng giá trị kỳ vọng ở **cả hai** lượt; `usable is
False`; `visits` lượt 2 **giống** lượt 1 (không reaction mới); D1 `build_d1_reaction_evidence(..., as_of=2026-09-23T00:00Z)`
cho `valid is False` / `score == 0`.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_06_terminal_state_survives_enrich_restore_enrich" -v --tb=line
2 passed, 2 failed
  [expired-buy]  PASSED      [expired-sell] PASSED
  [invalid-buy]  FAILED      [invalid-sell] FAILED
    E   AssertionError: assert 'confirmed' == 'invalid'

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
68 tests collected                   (64 + 4)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
45 failed, 23 passed in 0.26s        (passed 21 → 23, failed 43 → 45)

python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py -q --tb=line
31 passed in 0.37s                   (không hồi quy)
```

**Phân loại RED:** nhánh `invalid` là `implementation` (**R72-08/F03**): projection ở context **không** đánh dấu
vùng bị canonical lifecycle invalidate là `invalid`/unusable (`lifecycle_status` vẫn `"confirmed"`,
`usable` vẫn `True`), trong khi nhánh `expired` đã được code xử lý đúng và đi qua round-trip nguyên vẹn. Probe
trước khi viết test cho cùng kết luận cho cả 2 side: `expired` ⇒ `status expired→expired`, `usable False`,
`visits` giữ `reacted_at=2026-09-22T00:00Z`, D1 `valid=False/score=0`; `invalid` ⇒ `invalidated_at=2026-09-23T00:00Z`
nhưng `status confirmed`, `usable True`. Không skip/xfail.

**Hash mới file acceptance:** `21CDAB4CE068BE01DA4216213C371547DBBAFCB7E209E78CDE59BC2720F62352`
(§A3.40 ghi `7D6D92D4…`; các hash trước giữ nguyên làm lịch sử).

**Kết cụm F01.2 (A3-023…A3-038):** đủ mã — 5 fixture fixes giữ nguyên, timeline D1/H4 ghi ở `M`, `_terminal_candles`
và `_h4_terminal_candles` có bất biến, validator/cadence đã chuẩn, các ca terminal trước/đúng/sau và round-trip
đã khóa. RED còn lại của cụm là implementation (chủ yếu **F04** — reaction vượt terminal — và **F03** — projection
`invalid`).

### A3.42 — Fixture excursion/reclaim thật + gọi sweep detector (A3-039)

Mở cụm F01.3. Sửa `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible`: fixture trước đây toàn nến ở
`(112,114,111,113)` (không có excursion) và chỉ gọi `detect_liquidity_pools` — đúng như hàng đối chiếu A3-003
ghi "chỉ tạo pool, không gọi sweep detector".

**Fixture mới (H1 8 nến, `tick=0.1`, `ATR=1` ⇒ `excursion = max(2*tick, 0.10*ATR) = 0.2`):**

```text
rows[1] = (100.3, 100.5, 99.5, 100.3)      # nến được xét: xuyên + reclaim thật
equal pool = trung bình 2 source = 100.025 (source-a 100, source-b 100.05)
cả hai source usable_at = confirmed_at = stamp(2)  ⇒  pool_usable_at = stamp(2)
nến idx1 đóng tại START + 2h = stamp(2)  ⇒  reclaimed_at == pool_usable_at  (biên "equal")
```

**Assert mới:** precondition hình học (`low 99.5 < 100.025 − 0.2 = 99.825`, `close 100.3 > 100.025`) và **gọi
`detect_liquidity_sweeps`** với `timeframe="H1"`, `tick_size=.1`, `atr_value=1`, `causal_only=True`,
`lookback_bars=8`, `liquidity_pools=pools`.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible" -q --tb=short
1 failed
  tests\...:590: assert len(records) == 1  →  assert 0 == 1   (records chưa có — interface, F06)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
68 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
45 failed, 23 passed in 0.26s        (không đổi)

python -m pytest tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py -q --tb=line
37 passed in 0.38s                   (không hồi quy)
```

**Kiểm chứng độc lập phần mới** (probe, vì lượt RED dừng ở assert `records` phía trên):

```text
geometry: low < level-excursion: True (99.5 < 99.825)
geometry: close > level: True (100.3 > 100.025)
swept_lows indices: [1] | swept_highs: []
sweep level == expected: True | reclaimed_at: 2026-09-01T02:00:00+00:00 | == usable_at: True
```

⇒ `lookback_bars=8` là bắt buộc (với `6` thì idx1 nằm ngoài cửa sổ và không có sweep) — đã cố định trong test.
Không assert `source_swing_id`: hiện `None` vì pool numeric là **trung bình** nên không tra ngược được source
(đúng gap A3-005/F06), không thuộc phạm vi mã này.

**Phân loại RED:** `interface` (`records` chưa có) — phần fixture/detector của mã này đã đúng và được kiểm độc
lập; không phải test defect. Không skip/xfail.

**Ghi chú cho A3-040/041/042:** fixture này là ca **biên "equal"**; A3-040 cần nến sweep **sau** mốc usable
(ví dụ idx2, close = stamp(3)) và A3-042 cần mốc usable **sau** close sweep (ví dụ `usable_at = stamp(3)` với
sweep ở idx1) — cả hai dùng lại đúng fixture/geometry này, chỉ dịch thời điểm.

**Hash mới file acceptance:** `D7CA26D339FDC45799F9D561D4C910DE0C2436B52AE2D40E240727E6DC1DED67`
(§A3.41 ghi `21CDAB4C…`; các hash trước giữ nguyên làm lịch sử).

### A3.43 — Equal pool usable trước sweep close: nhận sweep (A3-040)

Node mới `test_r72_01_equal_pool_usable_before_sweep_close_is_accepted` — cùng fixture equal pool với A3-039
nhưng **dịch nến được xét sang idx2** để nguồn usable **trước** close của sweep (ca dương của gate A-D01).

**Fixture và precondition (H1 8 nến, `tick=0.1`, `ATR=1` ⇒ `excursion = 0.2`):**

```text
rows[2] = (100.3, 100.5, 99.5, 100.3)       # excursion + reclaim
equal pool = 100.025 (source-a 100, source-b 100.05), cả hai usable/confirmed tại stamp(2)
pool_usable_at = stamp(2)  <  event close = stamp(3)      # usable TRƯỚC sweep close
geometry: low 99.5 < 99.825 ; close 100.3 > 100.025
```

**Assert (source time + event time, không chỉ "list nonempty"):**

```text
2 source: confirmed True / usable True / provisional False
swept_lows index == 2 ; swept_highs == []
kind == "swept_low" ; side == "buy" ; level == 100.025
time == stamp(2) (open) ; reclaimed_at == stamp(3) (close) ; excursion_buffer ≈ 0.2
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_equal_pool_usable_before_sweep_close_is_accepted" -v --tb=short
1 passed

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
69 tests collected                   (68 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
45 failed, 24 passed in 0.26s        (passed 23 → 24, failed không đổi)

python -m pytest tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py -q --tb=line
37 passed in 0.38s                   (không hồi quy)
```

**Phân loại:** **GREEN** — ca dương của gate hiện đã đúng và nay được khóa bằng cả source time lẫn event time.
Ghi rõ một điều quan trọng cho người đọc sau: gate `pool_usable_at <= reclaimed_at` **chưa** được implement
trong detector (F07), nên node này pass *độc lập* với gate — cặp chứng minh gate thật sự có tác dụng là các node
reject (A3-042, hiện RED). Vì vậy node này đóng vai trò **positive control** xanh cho cặp đó, và tôi **không**
assert `records` ở đây để không biến nó thành RED interface.

**Hash mới file acceptance:** `DD1FEC36513BC503DDEB3A2A20A2CE3F95A71AB491940554FD6A620A8205F7DB`
(§A3.42 ghi `D7CA26D3…`; các hash trước giữ nguyên làm lịch sử).

### A3.44 — Ca biên "equal" + ghi rõ temporal seam synthetic (A3-041)

**Xác minh, không viết lại** (theo §8.1): node `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible`
sau A3-039 đã khóa đúng ca biên:

```text
pool_usable_at = max(usable_at 2 source) = stamp(2)
sweep["reclaimed_at"] == usable_at == pool_usable_at        # equality
swept_lows index == [1]                                     # equality VẪN được nhận (A-D01 inclusive)
```

**Thay đổi duy nhất:** ghi rõ trạng thái **synthetic temporal seam** — thêm 2 dòng vào docstring và 1 comment
ngay tại chỗ assertion equality: `usable_at` do **fixture khai**, nên ca này chứng minh *contract cửa sổ bao gồm*
chứ **không** chứng minh pivot producer phát ra mốc đó; ca end-to-end (producer thật) là **A3-044**. Không đổi
assertion nào. `M` cập nhật hàng tracking của node + hàng đối chiếu A3-003 với cùng ghi chú.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible" "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_equal_pool_usable_before_sweep_close_is_accepted" -q --tb=line
1 failed, 1 passed
  failed: equal_usable_at_reclaimed (RED đã biết — `records` chưa có, F06)
  passed: equal_pool_usable_before_sweep_close (A3-040)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
69 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
45 failed, 24 passed in 0.27s        (không đổi)
```

**Hash mới file acceptance:** `F4C0AFACF3A678DD3F7CAB103FDF8903B1C92E6D935F191B4CCF2D4386DED118`
(§A3.43 ghi `DD1FEC36…`; các hash trước giữ nguyên làm lịch sử).

### A3.45 — Nguồn usable sau sweep close: reject (A3-042)

Node mới `test_r72_01_source_usable_after_sweep_close_is_rejected[buy/sell]` — cặp **reject** của gate A-D01,
dùng **đúng geometry excursion/reclaim** của control A3-040, chỉ khác mốc usable của nguồn.

| Side | Pool | Nến được xét (idx2) | Mốc thời gian |
|---|---|---|---|
| `buy` | `equal_lows` `100`/`100.05` = `100.025` | `(100.3,100.5,99.5,100.3)` | `pool_usable_at = stamp(4)` **>** close `stamp(3)` |
| `sell` | `equal_highs` `110`/`109.95` = `109.975` | `(109.7,110.5,109.5,109.7)` (rows buy-shaped qua `_probe.candles(..., "sell")`) | như trên |

Contract: `swept_lows == []` (buy) / `swept_highs == []` (sell) **và** list phía đối diện cũng rỗng ⇒ nguồn tương
lai không được dùng. Kèm sanity `sweep_candle.time == stamp(2)` (đúng candle đang xét).

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_source_usable_after_sweep_close_is_rejected" -v --tb=line
2 failed
  [buy] : assert [{'depth': 0.5, 'index': 2, ...}] == []      (detector VẪN trả sweep)
  [sell]: như trên

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
71 tests collected                   (69 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
47 failed, 24 passed in 0.26s        (failed 45 → 47, passed giữ 24)

python -m pytest tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py -q --tb=line
37 passed in 0.38s                   (không hồi quy)
```

**Phân loại RED:** `implementation` — **F07** (gate `usable_at <= reclaimed_at` chưa có trong detector): với
nguồn chỉ usable ở `stamp(4)` detector vẫn cấp sweep ở idx2. Mọi assert precondition (source confirmed/usable/
non-provisional, `stamp(4) > stamp(3)`, geometry đúng phía) **PASS** ⇒ đây là reject-gap thật, không phải test
hay fixture sai; cặp xanh tương ứng là A3-040 (trước close) và A3-041 (đúng biên).

**Lưu ý kỹ thuật đã kiểm:** `_probe.candles(rows, side="sell")` **tự mirror** rows quanh 210, nên fixture SELL
phải truyền rows buy-shaped (lần probe đầu tôi truyền rows đã mirror ⇒ ra `swept_highs == []` một cách **giả**
do không có excursion; đã phát hiện và sửa lại đúng trước khi viết test).

**Hash mới file acceptance:** `F725A989B19748C70A7D82458B98FD7A4CD0C25CF9CF3F79BC87271FF3C677F9`
(§A3.44 ghi `F4C0AFAC...`; các hash trước giữ nguyên làm lịch sử).

### A3.46 — Usable time của equal pool = max cả hai source (A3-043)

Hai node mới, cùng fixture family của A3-039…042:

**(a) `test_r72_01_equal_pool_usable_time_is_max_of_both_sources`** — 2 source equal `100`/`100.05` nhưng
usable/confirmed **khác nhau** (`source-a = stamp(1)`, `source-b = stamp(3)`); nến được xét ở idx1 đóng tại
`stamp(2)`, tức **nằm giữa** hai mốc.

```text
precondition: equal pool tồn tại; source_a.usable_at != source_b.usable_at
              pool_usable_at == max == stamp(3);  stamp(1) < event_close stamp(2) < stamp(3)
              geometry excursion/reclaim hợp lệ
contract:     swept_lows == [] và swept_highs == []
```

Ca này phân biệt "max cả hai source" với "chỉ source đầu": nếu chỉ so `source-a` (`stamp(1)`) thì close
`stamp(2)` sẽ được nhận ⇒ chính là RED hiện tại.

**(b) `test_r72_01_equal_pool_without_usable_source_does_not_exist`** — `source-b.usable = False`:

```text
equal_lows == []            # nguồn không usable bị loại ⇒ không có equal pool để sweep
swing_lows == [100.0]       # chỉ còn level của source hợp lệ
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_equal_pool_usable_time_is_max_of_both_sources" "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_equal_pool_without_usable_source_does_not_exist" -v --tb=line
1 failed, 1 passed
  (a) FAILED: assert [{'depth': 0.5, 'index': 1, ...}] == []      # luật max chưa áp (F07)
  (b) PASSED: equal_lows == [] ; swing_lows == [100.0]

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
73 tests collected                   (71 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
48 failed, 25 passed in 0.27s        (failed 47 → 48, passed 24 → 25)

python -m pytest tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py -q --tb=line
37 passed in 0.39s                   (không hồi quy)
```

**Phân loại:** (a) RED `implementation` — **F07** (detector chưa áp luật `max(source usable_at) <= reclaimed_at`;
hiện chỉ cần một source đủ sớm là nhận). Mọi precondition **PASS** ⇒ không phải fixture defect. (b) GREEN —
hành vi loại source không usable đã đúng ở projection, và node này ghi lại điều đó. Không skip/xfail.

**Hash mới file acceptance:** `0784F871D2719A734231F328A2BE49673AFFEC987D6F8580126170052B9FA82D`
(§A3.45 ghi `F725A989…`; các hash trước giữ nguyên làm lịch sử).

### A3.47 — End-to-end swing producer → pool → sweep (A3-044)

Node mới `test_r72_01_actual_swing_producer_feeds_pool_and_sweep` — positive **đầu-cuối** với **producer thật**
(`external_swing_points`, `core/smc_context.py:1037`), tách hẳn khỏi fixture temporal synthetic của A3-039…043
(ở đó `usable_at` do tay khai).

**Fixture 12 nến H1 OHLC thật** (đã qual qua `_probe.candles`, tức `validate_smc_candles(..., "H1")`):

```text
idx4 low 99.5  là đáy duy nhất trong cửa sổ [2..6]  ⇒ producer phát 1 swing low
idx10 = (100, 100.6, 99.0, 100.2)  ⇒ candle sweep: low 99.0 < 99.5 − excursion(0.2), close 100.2 > 99.5
```

**Chuỗi được assert (expected tính độc lập từ `rows` + contract causal của producer):**

```text
producer:  index == 4 ; level == 99.5 ; pivot_time == stamp(4) (open nến pivot)
           confirmed_at == stamp(7) (close nến idx4 + lookback 2)
           confirmed True / usable True / provisional False ; swing_id không rỗng
pool:      detect_liquidity_pools(...)["swing_lows"] == [99.5]
sweep:     index == 10 ; level == 99.5 ; reclaimed_at == stamp(11) ; source_swing_id == swing["swing_id"]
ordering:  confirmed_at (stamp 7) < reclaimed_at (stamp 11)      # sweep SAU usable
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_actual_swing_producer_feeds_pool_and_sweep" -v --tb=short
1 passed

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
74 tests collected                   (73 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
48 failed, 26 passed in 0.27s        (passed 25 → 26, failed không đổi)

python -m pytest tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py tests/test_smc_external_pivots.py tests/test_smc_internal_pivots.py -q --tb=line
48 passed in 0.55s                   (không hồi quy)
```

**Điểm đáng ghi:** sweep trả về **`source_swing_id` trỏ đúng `swing_id` của swing mà producer phát** ⇒ đây là ca
positive **có lineage thật**, bổ sung cho hạn chế đã ghi ở §A3.42 của fixture equal pool (level là **trung bình**
nên không tra ngược được source ⇒ `source_swing_id` là `None`). Thay đổi kèm theo: **1 import mới**
`external_swing_points` trong khối `from core.smc_context import (...)`.

**Hash mới file acceptance:** `01F7EEB3E180084F597B724AFD8661813C9A9AB56420606939B6D0C899531655`
(§A3.46 ghi `0784F871…`; các hash trước giữ nguyên làm lịch sử).

### A3.48 — Xác minh assignment ban đầu của same-pool observation (A3-045)

Lượt 1 của `test_r72_04_same_pool_observation_cannot_bypass_consumption` nay được xác minh **tường minh** thay vì
chỉ dựng rồi dùng. Lượt 2 (observation mới) **giữ nguyên** — thuộc **A3-046**.

**Assert mới cho lượt 1 (expected tính từ fixture/probe + A-D02, không lấy từ output để tự sinh expected):**

```text
claim:  pool_id == "pool-1" ; source_ids == ["swing-1"]
        reclaimed_at == stamp(11) ; setup_available_at == stamp(13)
assign: reason_codes == []                                  # history đầy đủ ⇒ không fail-closed
        owner_setup_id == "original"                        # early owner
        assignment_id không rỗng
        claim_eligible_at == max(stamp(11), stamp(13)) == stamp(13)     # A-D02
        assigned_at == claim_eligible_at
JSON:   json.loads(json.dumps(assignments)) == assignments   # history serialize/restore nguyên vẹn
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_same_pool_observation_cannot_bypass_consumption" -v --tb=short
1 passed

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
74 tests collected                   (không đổi — chỉ siết assert)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
48 failed, 26 passed in 0.30s        (không đổi)

python -m pytest tests/test_smc_sweep_consumed_task69.py tests/test_smc_sweep_linking_task68.py tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py -q --tb=line
27 passed in 0.39s                   (không hồi quy)
```

**Phân loại:** không có RED mới — các assert mới khớp hành vi hiện tại (probe trước khi sửa cho
`reason_codes == []`, owner `original`, `assignment_id = smca-2c5edcc5…`, `claim_eligible_at == stamp(13)`,
JSON round-trip bằng nhau). **Còn tồn (A3-046):** lượt 2 vẫn "pass trivial" vì hai claim dùng cùng
`sweep_id="sweep"` và `reclaimed_at=stamp(11)` ⇒ history khớp theo **ID** chứ chưa chứng minh pool identity.

**Hash mới file acceptance:** `BACFE1E7C7F3F16C6D1B75A114AA62DAE0CAFC50C888618118D4EA21FDF4FC99`
(§A3.47 ghi `01F7EEB3…`; các hash trước giữ nguyên làm lịch sử).

### A3.49 — Observation mới của cùng causal pool (A3-046)

Lượt 2 của `test_r72_04_same_pool_observation_cannot_bypass_consumption` được viết lại thành **observation mới
thật** thay cho "replay cùng sweep ID/time" (đúng cảnh báo của review).

**Thay đổi:**

```text
lượt 1:  thêm "index": 7 vào claim (observation/rolling index) — để precondition so được
lượt 2:  _probe.claim("later", "late-child", 15) + {
             "sweep_id": "sweep-later",          # sweep ID mới
             "reclaimed_at": stamp(17),          # observation time mới
             "index": 99,                        # rolling index mới
             "pool_id": "pool-1",                # GIỮ nguyên causal pool identity
             "source_ids": ["swing-1"],          # GIỮ nguyên nguồn pool
         }
precondition: cùng pool/source identity; khác sweep ID / reclaimed_at / index
contract:     assignments["sweep-later"]["owner_setup_id"] == "original"
              assignments["sweep-later"]["assignment_id"]  == initial["assignment_id"]
              claims[0]["contribution_applied"] is False
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_same_pool_observation_cannot_bypass_consumption" -v --tb=short
1 failed
  E   AssertionError: assert 'later' == 'original'
      - original
      + later

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
74 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
49 failed, 25 passed in 0.28s        (failed 48 → 49, passed 26 → 25 — đúng vì node chuyển từ pass-trivial sang RED)

python -m pytest tests/test_smc_sweep_consumed_task69.py tests/test_smc_sweep_linking_task68.py tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py -q --tb=line
27 passed in 0.37s                   (không hồi quy)
```

**Phân loại RED:** `implementation` — **F10**: `assign_sweep_ownership` khớp history theo **`sweep_id`**
(`grouped` + `history.get(sweep_id)`), nên một observation mới của **cùng causal pool** (giữ `pool_id`/`source_ids`,
đổi sweep ID) không thấy history và **cấp owner mới cho setup muộn** (`'later'`) với contribution `True` ⇒
bypass consumption. Probe trước khi sửa xác nhận đúng hành vi này (`assignments = {'sweep-later': {owner 'later',
assignment_id mới, contribution_applied True}})`, trong khi lượt 1 (A3-045) đã đúng.

**Hash mới file acceptance:** `25348D5D7A58199541040B0CC07CD5CD339C4C1E01C2F9F53239F86B0866AEA1`
(§A3.48 ghi `BACFE1E7…`; các hash trước giữ nguyên làm lịch sử).

### A3.50 — Control pool mới thật (không bị khóa nhầm) (A3-047)

Thêm **khối control** vào cuối `test_r72_04_same_pool_observation_cannot_bypass_consumption` (sau lượt A3-046):

```text
claim:  new-setup/new-child, sweep_id="sweep-new", reclaimed_at=stamp(21), index=199
        pool_id="pool-2", source_ids=["swing-2"]          # pool MỚI thật
history: dùng lại restored_history của lượt 1 (pool-1 đã bị consumed)
precos: pool_id/source_ids/sweep_id đều KHÁC lượt 1; hai mốc claim hợp lệ (stamp(21)/stamp(19))
expect: reason_codes == [] ; assignments["sweep-new"]["owner_setup_id"] == "new-setup"
        claims[0]["contribution_applied"] is True          # KHÔNG bị khóa nhầm bởi pool cũ
```

Mục đích: chặn khả năng bản sửa F10 **over-block** (khoá mọi claim mới theo pool cũ).

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_same_pool_observation_cannot_bypass_consumption" -v --tb=short
1 failed
  E   AssertionError: assert 'later' == 'original'        # assert của lượt A3-046 fail trước
  (khối control A3-047 nằm SAU đó nên chưa được chạy tới trong lượt này)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
74 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
49 failed, 25 passed in 0.27s        (không đổi — node vốn đã RED ở lượt A3-046)

python -m pytest tests/test_smc_sweep_consumed_task69.py tests/test_smc_sweep_linking_task68.py tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py -q --tb=line
27 passed in 0.37s                   (không hồi quy)
```

**Kiểm chứng control độc lập** (probe, vì lượt RED fail-fast trước khối này):

```text
new-pool control: {'sweep-new': {'owner_setup_id': 'new-setup', 'assignment_id': 'smca-21dde681ac97338d5b6c',
                                 'claim_eligible_at': '2026-09-01T21:00:00+00:00', 'contribution_applied': True}}
reason_codes: []
claims: [{'sweep_id': 'sweep-new', 'setup_id': 'new-setup', 'owner_setup_id': 'new-setup',
          'contribution_applied': True, 'pool_id': 'pool-2', 'source_ids': ['swing-2']}]
```

⇒ control **PASS** (đúng như mong đợi); đã ghi rõ là *chưa chạy qua test* trong lượt RED này, không nhận là đã chạy.

**Hash mới file acceptance:** `BB0D1F07749BCE693F11AABC8511DB8AFEF5918709DB5E77E8EE7E0E685D8704`
(§A3.49 ghi `25348D5D…`; các hash trước giữ nguyên làm lịch sử).

### A3.51 — Assignment history mâu thuẫn ⇒ fail closed (A3-048)

Node mới `test_r72_04_conflicting_assignment_history_fails_closed` — khép cụm F01.3.

**Fixture:** claim `late/child` **đầy đủ canonical** (`reclaimed_at=stamp(11)`, `setup_available_at=stamp(15)`,
`pool_id="pool-1"`, `source_ids=["swing-1"]`, `index=3`) + history **mâu thuẫn**:
`{"sweep": {"sweep_id": "sweep", "owner_setup_id": "original"}}` — record **khai owner** nhưng thiếu
`assignment_id`/`claim_eligible_at`/`assigned_at` nên không thể được tôn trọng.

```text
precondition: claim không thiếu field nào (cả hai mốc + lineage) ⇒ không thể fail vì thiếu fixture timestamp
contract:     assignments == {}            # không tự cấp lại owner cho sweep
              reason_codes != []           # phải có reason tường minh
```

Không khoá **chuỗi** reason cụ thể: contract/interface chưa chốt tên cho ca conflict (ghi nhận ở mục câu hỏi mở
của A3-008), nên chỉ assert "không rỗng" — cùng cách xử lý như reason của metadata.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_conflicting_assignment_history_fails_closed" -v --tb=short
1 failed
  E   AssertionError: assert {'sweep': {'a...': True, ...}} == {}
      Left contains 1 more item: {'sweep': {'assigned_at': '2026-09-01T15:00:00+00:00',
                                            'assignment_id': 'smca-30bb697d628ee9c39480', ...}}

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
75 tests collected                   (74 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
50 failed, 25 passed in 0.28s        (failed 49 → 50, passed giữ 25)

python -m pytest tests/test_smc_sweep_consumed_task69.py tests/test_smc_sweep_linking_task68.py tests/test_smc_liquidity_pools_task66.py tests/test_smc_liquidity_sweeps_task67.py -q --tb=line
27 passed in 0.37s                   (không hồi quy)
```

**Phân loại RED:** `implementation` (**F10**). Probe trước khi viết cho thấy **cả ba** dạng record không tôn trọng
được đều bị **bỏ qua âm thầm** và sweep bị cấp lại cho setup hiện tại, `reason_codes == []`:

```text
partial record (owner only)          : assignments={'sweep': {owner 'late', assignment_id mới, contribution True}} reason_codes=[]
empty record                         : như trên
owner+assignment without times       : như trên
```

Precondition của node (claim đủ mốc + lineage) **PASS** ⇒ RED không đến từ thiếu fixture timestamp.

**Dặn lại cho F10:** cần phân biệt ba trạng thái — history **đầy đủ** (authority, giữ nguyên),
**thiếu hẳn** (đã có `SWEEP_OWNER_HISTORY_INCOMPLETE` theo A3-006) và **mâu thuẫn/không tôn trọng được**
(node này) ⇒ phải fail closed kèm reason riêng, không cấp owner mới. Biến thể "conflict theo pool lineage"
chưa kiểm được ở A vì `SweepAssignment` hiện **chưa có** `pool_id`/`source_ids` (đúng gap đã ghi ở A3-008/F10).

**Hash mới file acceptance:** `5C372D0A5DF646FC6A322E670DB220ECD3D3051A21D49959BBF5E953BDD3A087`
(§A3.50 ghi `BB0D1F07…`; các hash trước giữ nguyên làm lịch sử).

**Kết cụm F01.3 (A3-039…A3-048):** đủ mã — fixture temporal synthetic (039–043) và end-to-end producer (044) đã
khóa ở A3-010…, các ca consumption/history (045–048) đã có node với phần control xanh và phần RED đúng loại
`implementation` (F10). Bước tiếp theo của dải mã là **A3-049** (mở cụm test `cutoff_equal_invalidated_at`).

### A3.52 — Positive D1 trước invalidation (A3-049)

Mở cụm R72-05. Fixture của `test_r72_05_cutoff_equal_invalidated_at_is_terminal` trước đây chỉ có
outside → touch → **invalidation** (không có reaction), nên phần "tại terminal ⇒ invalid/0" **pass vì chưa
từng có reaction** — đúng điểm review nêu ("actual reject reason `D1_REACTION_NOT_COMPLETED_REACTED`").

**Fixture mới (D1, zone `[100,110]`, 4 nến):**

| Index | BUY | SELL | Vai trò |
|---|---|---|---|
| 0 | `(112,114,111,113)` | `(98,99,96,97)` | outside |
| 1 | `(105,111,105,108)` | `(101,105,99,102)` | touch — mở visit |
| 2 | `(112,114,111,113)` | `(98,99,96,97)` | **exit + reaction** (BUY `close 113 ≥ 110.25`; SELL `close 97 ≤ 99.75`) |
| 3 | `(99,100,98,99)` | `(111,112,109,111)` | invalidation (cutoff terminal) |

**Phase prefix positive (A3-049)** — chain **bỏ** nến invalidation:

```text
prefix = analyze_zone_lifecycle(values[:3], ...)   → visit completed_reacted
         entered 2026-09-03T00:00Z (close idx1) ; exited/ reacted 2026-09-04T00:00Z (close idx2)
evidence = build_d1_reaction_evidence(zone, prefix, as_of=2026-09-04T00:00Z)
         → valid True ; score > 0 ; zone_id "equal-terminal" ; source_visit_id == prefix_visit.visit_id
```

Phase terminal (cutoff bằng `invalidated_at`) giữ nguyên assertion cũ — **A3-050** sẽ siết tiếp (giữ `reacted_at`
cũ + reject đúng terminal).

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_05_cutoff_equal_invalidated_at_is_terminal" -v --tb=short
2 failed
  [buy] / [sell]: E   assert True is False        # tại terminal, evidence vẫn valid=True

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
75 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
52 failed, 23 passed in 0.27s        (failed 50 → 52, passed 25 → 23 — 2 param của node chuyển RED)

python -m pytest tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py -q --tb=line
30 passed in 0.29s                   (không hồi quy)
```

**Phân loại:** RED loại `implementation` (**F05**, A-D04): với reaction thật trong prefix, consumer tại
`as_of == state.invalidated_at` vẫn trả `valid True`/`score 1.0` (reason `D1_REACTION_COMPLETED_REACTED`) ⇒
cutoff bằng mốc invalidation **chưa** bị coi là terminal. Phase prefix (mới) **PASS** cả 2 side ⇒ node nay
chứng minh được điều nó tuyên bố, thay vì pass nhờ "chưa từng có reaction".

**Sự cố nhỏ trong lượt (đã sửa):** thao tác chèn hàng `M` tạo **hàng `[sell]` trùng** cho node này (bảng vốn đã
có hàng `[sell]`); đã xoá hàng trùng, bảng R72-05 còn đúng **6 hàng unique**, header giữ "6 node", `grep '||'` = 0.

**Hash mới file acceptance:** `D899C9AB178350880F1DAD7650471B4F2ED9D10E90BFC78549B8119C518AB4F9`
(§A3.51 ghi `5C372D0A…`; các hash trước giữ nguyên làm lịch sử).

### A3.53 — Cutoff đúng invalidation: invalid/0 nhưng giữ reaction history (A3-050)

Siết **phase terminal** của `test_r72_05_cutoff_equal_invalidated_at_is_terminal` (cùng chuỗi 4 nến của A3-049):

```text
state.invalidated_at == start + 4 ngày == 2026-09-05T00:00Z      (close nến idx3)
state.visits[0].reacted_at == prefix_cutoff == 2026-09-04T00:00Z  # reaction TRƯỚC terminal giữ nguyên
evidence["valid"] is False ; evidence["score"] == 0               # cutoff bằng mốc terminal
"D1_REACTION_NOT_COMPLETED_REACTED" not in evidence["reason_codes"]  # reject KHÔNG vì thiếu reaction
```

Assert cuối cố ý **không** khoá tên reason của ca terminal (chưa được review chốt) mà chỉ loại trừ khả năng
"bị từ chối vì chưa từng có reaction" — điều mà prefix positive ở A3-049 đã bác bỏ.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_05_cutoff_equal_invalidated_at_is_terminal" -v --tb=short
2 failed
  [buy] / [sell]: E   assert True is False     # dừng ở `evidence["valid"] is False`

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
75 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
52 failed, 23 passed in 0.28s        (không đổi — chỉ siết assert)

python -m pytest tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py -q --tb=line
30 passed in 0.30s                   (không hồi quy)
```

**Phân loại RED:** `implementation` (**F05**, A-D04) và **chỉ còn ở assert `valid is False`** — hai assert mới phía
trên đều **PASS** (probe: `invalidated_at = 2026-09-05T00:00Z`, `visit reacted_at = 2026-09-04T00:00Z`,
`visit_state = completed_reacted`), tức terminal timestamp đúng và lịch sử reaction **không** bị xoá; gap là
consumer vẫn phục vụ evidence hoạt động tại cutoff terminal (`valid=True/score=1.0`,
reason `['D1_REACTION_COMPLETED_REACTED']`).

**Hash mới file acceptance:** `B0667E722F28FB997DCABC49FC7F2C7A88DFD5EDB84D230078C985BA6C646040`
(§A3.52 ghi `D899C9AB…`; các hash trước giữ nguyên làm lịch sử).

### A3.54 — Cutoff đúng expiry: invalid/0 và giữ lịch sử (A3-051)

Node mới `test_r72_05_cutoff_equal_expired_at_is_terminal[buy/sell]` — bản **đối ứng expiry** của chuỗi A3-049/050,
dùng lại fixture D1 `_terminal_candles(side, 20)` (23 nến: touch idx19, **reaction idx20**, hết lifetime idx21
**không** invalidation; bảng §A3-029).

```text
prefix (21 nến, dừng ở candle reaction):
    visited completed_reacted ; reacted_at == 2026-09-22T00:00Z (close idx20)
    evidence(as_of = 2026-09-22T00:00Z)  → valid True ; score > 0        # positive thật, cutoff SAU reaction
full (23 nến):
    expiry_index == 21 ; expired_at == 2026-09-23T00:00Z (close idx21)
    visits[0].reacted_at == 2026-09-22T00:00Z                            # history giữ nguyên
    evidence(as_of = expired_at) → valid False ; score == 0
    "D1_REACTION_NOT_COMPLETED_REACTED" not in reason_codes              # không phải vì thiếu reaction
```

Ba điều kiện "không pass vì stale/no-reaction/cutoff-trước-reaction" đều được chặn: prefix là **positive thật**
tại chính close của reaction, và fixture có reaction thật (`completed_reacted`) chứ không rỗng.

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_05_cutoff_equal_expired_at_is_terminal" -v --tb=short
2 passed                             ([buy] PASSED, [sell] PASSED)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
77 tests collected                   (75 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
52 failed, 25 passed in 0.28s        (passed 23 → 25, failed giữ 52)

python -m pytest tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py tests/test_smc_lifecycle_task65.py -q --tb=line
30 passed in 0.31s                   (không hồi quy)
```

**Phân loại:** **GREEN cả 2 side** — đường **expiry** của D1 consumer **đã đúng**: tại `expired_at` evidence trả
`valid False`/`score 0.0` với reason `D1_REACTION_STALE`, và reaction trước expiry vẫn nằm trong visit history.
Đối chiếu đáng chú ý cho F05: cùng cơ chế cutoff nhưng nhánh **invalidation** (`invalidated_at`) **chưa** bị chặn
(A3-049/050 vẫn RED) — tức gap nằm ở mốc invalidation, không phải expiry.

**Hash mới file acceptance:** `1F612B0DF65EF2BB3E0FDC4B0B383D8EF04DB83D1EC6841B6D7074E51FA6BC48`
(§A3.53 ghi `B0667E72…`; các hash trước giữ nguyên làm lịch sử).

### A3.55 — Chuẩn hóa payload typed cho D1 consumer (A3-052)

Node `test_r72_08_typed_terminal_projection_reaches_d1_consumer` trước đây **pass sai nhánh**: payload là
`restored = dict(terminal_zone)` (không typed) với `zone_id="terminal-zone"` **khác** zone `"zone"` của
`_probe.lifecycle` ⇒ `build_d1_reaction_evidence` bỏ **mọi** visit (`visit_zone_id != zone_id`) và trả
`D1_REACTION_NOT_COMPLETED_REACTED`/`score 0` — tức xanh vì ID lệch, không vì terminal. Cutoff `stamp(3)` cũng
**trước** reaction `stamp(72)`.

**Chuẩn hóa:**

```text
state = _probe.lifecycle([...3 nến D1...], side)  → visit zone_id "zone", reacted_at stamp(72), completed_reacted
payload = SmcZone.from_dict({
              "zone_id": visit.zone_id, "direction": side, "timeframe": "D1", "family": "ob",
              "zone_type": bullish_ob/bearish_ob, "low": 100.0, "high": 110.0,
              "origin_index": 0, "origin_time": stamp(0),
              "lifecycle_status": "invalid", "broken": True, "invalidated_at": stamp(96),
          }).to_dict()
assert payload["zone_id"] == visit.zone_id ; payload["timeframe"] == "D1" ; status == "invalid"
cutoff = stamp(96)  (D1 close kế tiếp) ; assert visit.reacted_at (stamp 72) < cutoff
evidence = build_d1_reaction_evidence(payload, state, as_of=cutoff)
assert "D1_REACTION_NOT_COMPLETED_REACTED" not in reason_codes     # không do ID lệch
assert "D1_REACTION_AFTER_CUTOFF" not in reason_codes              # không do cutoff trước reaction
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_08_typed_terminal_projection_reaches_d1_consumer" -v --tb=short
2 failed
  [buy] / [sell]: E   assert True is False     # dừng ở `evidence["valid"] is False`

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
77 tests collected                   (không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
54 failed, 23 passed in 0.28s        (failed 52 → 54, passed 25 → 23 — 2 param của node chuyển RED)

python -m pytest tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py tests/test_smc_zone_models_task41.py -q --tb=line
27 passed in 0.29s                   (không hồi quy)
```

**Phân loại:** RED loại `implementation` (**F05**) và **đúng nhánh**: round-trip typed khớp `zone_id`/`timeframe`,
cutoff **sau** reaction, và kết luận hiện tại là `valid=True/score=1.0` với reason `D1_REACTION_COMPLETED_REACTED`
(probe trước khi sửa xác nhận cùng kết quả) ⇒ vùng canonical terminal **vẫn** cấp evidence hoạt động, không phải
do ID lệch hay cutoff. A3-053/054/055 sẽ bổ sung control positive / invalid / expired.

**Hash mới file acceptance:** `1464470133B5644BA62EAD0696843C612DCAEF1A8BE2CAB9C3E441649587FAAD`
(§A3.54 ghi `1F612B0D…`; các hash trước giữ nguyên làm lịch sử).

### A3.56 — Typed D1 positive control (A3-053)

Node mới `test_r72_08_typed_d1_projection_keeps_valid_reaction[buy/sell]` — **control** cho đường typed D1: chứng
minh payload typed **hoạt động** với vùng **không terminal**, để ca terminal (A3-052/A3-054) không thể xanh nhờ
"mọi payload typed đều fail".

```text
state  = _probe.lifecycle([...3 nến D1...], side)  → visit zone_id "zone", visit_id "zone:visit-1",
                                                       reacted_at stamp(72), completed_reacted
payload = SmcZone.from_dict({
              "zone_id": visit.zone_id, "direction": side, "timeframe": "D1", "family": "ob",
              "zone_type": bullish_ob/bearish_ob, "low": 100.0, "high": 110.0,
              "origin_index": 0, "origin_time": stamp(0), "available_at": stamp(24),
              "lifecycle_status": "confirmed", "broken": False, "visits": [visit.to_dict()],
          }).to_dict()
round-trip: zone_id == visit.zone_id ; (low, high) == (100.0, 110.0) ; available_at == stamp(24)
            lifecycle_status == "confirmed" ; 1 visit với visit_id/reacted_at/visit_state khớp
evidence(payload, state, as_of=stamp(96)) → valid True ; score > 0 ;
            zone_id == visit.zone_id ; source_visit_id == visit.visit_id
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_08_typed_d1_projection_keeps_valid_reaction" -v --tb=short
2 passed                             ([buy] PASSED, [sell] PASSED)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
79 tests collected                   (77 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
54 failed, 25 passed in 0.28s        (passed 23 → 25, failed giữ 54)

python -m pytest tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py tests/test_smc_zone_models_task41.py -q --tb=line
27 passed in 0.29s                   (không hồi quy)
```

**Phân loại:** **GREEN cả 2 side** (probe trước khi viết cho cùng kết quả: `valid=True/score=1.0`,
`zone_id="zone"`, `source_visit_id="zone:visit-1"`, `lifecycle_status="confirmed"`). Đây là control cần thiết cho
chuỗi typed: nó chứng minh `SmcZone.from_dict(...).to_dict()` + D1 consumer chạy đúng khi vùng **chưa** terminal,
nên RED của A3-052/A3-054 là do trạng thái terminal chưa thắng, không do payload typed hỏng.

**Hash mới file acceptance:** `21538A945EAA9A8739D81B607548CEA702B710FFD79DCF2B6878E80A8621940F`
(§A3.55 ghi `14644701…`; các hash trước giữ nguyên làm lịch sử).

### A3.57 — Typed invalid thắng legacy flags trái canonical (A3-054)

Node mới `test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[buy/sell]` — cùng **nguồn** với
control A3-053, nhưng vùng ở trạng thái **canonical invalid** trong khi legacy flags khai có reaction hoạt động.

```text
state = _probe.lifecycle([...3 nến D1...], side)   → visit completed_reacted, reacted_at stamp(72), zone_id "zone"
payload = SmcZone.from_dict({
              ..., "lifecycle_status": "invalid", "broken": True, "invalidated_at": stamp(96),
              "visits": [visit.to_dict()], "d1_reaction": True, "proximity": True,
          }).to_dict()
precondition: payload giữ "invalid"/broken True/invalidated_at ; "d1_reaction" & "proximity" NOT in payload (typed
              không mang legacy flags)
lifecycle_payload = state.to_dict() + {lifecycle_status "invalid", lifecycle_broken False, broken False,
              d1_reaction True, proximity True}      # legacy TRÁI canonical
evidence(payload, lifecycle_payload, as_of=stamp(96)) → contract: valid False ; score == 0
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags" -v --tb=short
2 failed
  [buy] / [sell]: E   assert True is False     # dừng ở `evidence["valid"] is False`

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
81 tests collected                   (79 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
56 failed, 25 passed in 0.29s        (failed 54 → 56, passed giữ 25)

python -m pytest tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py tests/test_smc_zone_models_task41.py -q --tb=line
27 passed in 0.28s                   (không hồi quy)
```

**Phân loại:** RED loại `implementation` (**F05/F03**) và **chỉ ở assert `valid is False`** — mọi precondition
**PASS** (probe trước khi viết: typed round-trip giữ `lifecycle_status="invalid"`, `broken=True`,
`invalidated_at=2026-09-05T00:00Z`; `d1_reaction`/`proximity` bị loại khỏi payload typed; lifecycle payload mang
legacy trái canonical), nhưng consumer vẫn trả `valid=True/score=1.0` (reason `D1_REACTION_COMPLETED_REACTED`) ⇒
trạng thái canonical invalid **chưa** thắng để chặn evidence hoạt động.

**Hash mới file acceptance:** `BF0473E1313B65B4650A1B25A76A12D8DFD0D27508ED7135C0285574F22EDD37`
(§A3.56 ghi `21538A94…`; các hash trước giữ nguyên làm lịch sử).

### A3.58 — Typed expired chặn D1 nhưng giữ history (A3-055)

Node mới `test_r72_08_typed_expired_projection_blocks_d1_and_keeps_history[buy/sell]` — nhánh **expired** của
đường typed D1, dùng lại `_terminal_lifecycle(side, 20)` (D1 23 nến: reaction idx20, expiry idx21).

```text
state:   lifecycle_expired True ; expiry_index == 21 ; visit.zone_id "terminal-zone"
         visit.reacted_at == stamp(504) (close idx20 = 2026-09-22) ; expired_at == stamp(528) = 2026-09-23
payload: SmcZone.from_dict({ ..., "lifecycle_status": "expired", "broken": False, "expired_at": expired_at,
                             "visits": [visit.to_dict()] }).to_dict()
precondition: payload["zone_id"] == visit.zone_id   (guard chống pass bằng mismatched ID)
              payload["lifecycle_status"] == "expired" ; payload["expired_at"] == expired_at
              1 visit với reacted_at == stamp(504)  (KHÔNG mất reacted history)
evidence(payload, state, as_of=expired_at) → valid False ; score == 0 ; zone_id == visit.zone_id
```

**Command và kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_08_typed_expired_projection_blocks_d1_and_keeps_history" -v --tb=short
2 passed                             ([buy] PASSED, [sell] PASSED)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
83 tests collected                   (81 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
56 failed, 27 passed in 0.30s        (passed 25 → 27, failed giữ 56)

python -m pytest tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py tests/test_smc_zone_models_task41.py -q --tb=line
27 passed in 0.28s                   (không hồi quy)
```

**Phân loại:** **GREEN cả 2 side** — đường expiry typed **đã đúng**: evidence tại `expired_at` trả
`valid False`/`score 0.0` (reason `D1_REACTION_STALE`) và reaction trước expiry vẫn nằm trong payload.
Đối chiếu chuỗi typed vừa hoàn tất: **positive** (A3-053, GREEN) → **invalid** (A3-052/A3-054, RED vì canonical
invalid chưa chặn) → **expired** (A3-055, GREEN vì expiry đã được xử lý) — tức gap còn lại đúng là nhánh
**invalidation**, không phải expiry.

**Hash mới file acceptance:** `22F9F4586AA8AD441DBDB770D6E4D0E832DC0A95179ADE140291A655ABB275B5`
(§A3.57 ghi `BF0473E1…`; các hash trước giữ nguyên làm lịch sử).

### A3.59 — Ghi đúng phạm vi ca H1 candidate hiện có (A3-056)

**Bối cảnh (từ `M`, hàng A3-003):** node R72-09 đang có tên
`test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture` nhưng thực chất chạy fixture
gate56 **H1** qua `detect_order_block_candidates` (chỉ ra **candidate**, không confirmed) và tự gán
`atr_current=5.0` — tức tên ghi "d1_context_chain" còn nội dung là H1 candidate. Node này còn một assertion
tautology: `lifecycle.to_dict()["visits"] == [visit.to_dict() for visit in lifecycle.visits]` (so chính
serialization của nó ⇒ không thể fail).

**Thay đổi (chỉ trong phạm vi test + `M`/`L`, không sửa `core/`, probe, R56/golden):**

1. Đổi tên node → `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke` (không đổi hành vi, **không** thêm node).
2. Docstring ghi rõ đây là ca **H1 candidate smoke** kiểm plumbing (ids/bounds sống qua các tầng và consumer D1 trả lời), và nêu bằng chứng **confirmed D1 end-to-end** thuộc A3-057…A3-062.
3. Thêm 2 assert khẳng định đúng bản chất fixture: `candidate["lifecycle_status"] == "candidate"` và `candidate.get("confirmed") is not True`.
4. Gỡ assertion tautology ở (1), thay bằng comment giải thích lý do gỡ.
5. Comment tại chỗ gọi lifecycle ghi rõ `tick_size=0.1, atr_current=5.0` là do ca smoke tự gán.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke" -q --tb=short
1 passed in 0.14s                    # ca plumbing, GREEN như trước; 2 assert mới PASS

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
83 tests collected in 0.13s          # không thêm node (83 giữ nguyên)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
56 failed, 27 passed in 0.28s        # không đổi so với A3-055

python -m pytest tests/test_smc_confluence_task70.py tests/test_smc_zone_visit_task57.py tests/test_smc_zone_models_task41.py -q --tb=line
27 passed in 0.28s                   # không hồi quy
```

**Phân loại:** **không có RED mới** — ca này là plumbing smoke, đã GREEN trước và vẫn GREEN; đây **không** phải
bằng chứng cho quy tắc confirmed-D1 end-to-end (nguồn confirmed còn **CÒN THIẾU**, thuộc A3-057…A3-062). Việc
sửa lượt này chỉ để tên/mapping khớp bản chất ca và loại bỏ assertion rỗng, đúng hàng A3-056 của fix-plan.

**Hash mới file acceptance:** `FD04499EA9C0764093A3FFF4B3F67CA959A287486506C29227699F90AD1C4424`
(§A3.58 ghi `22F9F458…`; các hash trước giữ nguyên làm lịch sử).

**Ghi chú `M` (đổi tên, giữ lịch sử):** trong `smc-task-72-acceptance-matrix.md`, 4 vị trí còn tên cũ đều là
chú thích lịch sử/đổi tên (bảng ledger R72-09 dòng 48, danh sách call-site validator A3-027 dòng 197, hàng
audit A3-003 dòng 213, hàng inventory A3-023 dòng 695) và đều đi kèm tên mới ⇒ **không** viết lại bảng lịch sử.

### A3.60 — Fixture nguồn D1 confirmed qua detector + structure replay (A3-057)

**Mục tiêu (hàng A3-057):** có một vùng **D1 confirmed** mà cả biên vùng lẫn nguồn xác nhận đều do
fixture sinh ra — không tự gán `confirmed`, không lấy output production làm expected.

**Cách dựng fixture:** `_D1_SOURCE_ROWS` gồm 37 nến D1 (mở tại `2026-01-01T00:00Z`, mỗi nến cách
nhau 1 ngày):

| Dải nến | Vai trò |
|---|---|
| 0..31 | warm-up + zigzag để `replay_smc_structure` **tự** bootstrap trạng thái bullish từ swing của chính nó: HH bar 14 = `102.0`, bar 26 = `103.0`; HL bar 8 = `96.4`, bar 20 = `97.8` (mỗi bar cách bar liền trước ≥ 0.2×ATR nên không bị lọc) |
| 32 | base bearish của order block: `O 100.0 / H 100.2 / L 99.2 / C 99.4` |
| 33 | departure bullish: `O 99.4 / H 101.4 / L 99.3 / C 101.2` (đóng trên base high, dưới đỉnh swing `103.0`) |
| 34 | nến phá đỉnh swing: đóng `103.8 > 103.0` ⇒ BOS bullish của replay |
| 35..36 | đuôi lịch sử đã đóng |

**Chuỗi thật:** `detect_order_block_candidates` (candidate) → `replay_smc_structure` (BOS bullish thật,
`event_id = smc-bos-f6ef…`, `broken_level_id =` swing high bar 26) → `confirm_order_block_candidate`.
`available_at` mong đợi được tính **độc lập** từ fixture: close của nến 34 = `candles[34].time + 1 ngày`.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_d1_source_is_confirmed_by_fixture_break" -q --tb=short
1 passed in 0.35s

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
84 tests collected in 0.13s          (83 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
56 failed, 28 passed in 0.28s        (passed 27 → 28, failed giữ 56)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                  (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.27s                  (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
56 failed, 882 passed in 11.70s      (56 failed đều thuộc file acceptance)
```

**Phân loại:** **GREEN** — đây là bước chuẩn bị, không kỳ vọng RED: đường `confirm_order_block_candidate`
đã đúng, nên node đóng vai **positive control** cho nguồn confirmed D1 sẽ dùng ở A3-058…A3-062 (nếu core
hồi quy phần confirmation, node này đỏ ở assert `lifecycle_status == "confirmed"`/`available_at`).
Fixture **không** dùng output production làm expected: `available_at` tính từ nến phá đỉnh của fixture,
biên vùng lấy từ nến base, `broken_level_id` phải khớp swing high ID của fixture.

**Hash mới file acceptance:** `5DE28DAAB5558CBFC8E555DF0CA19962FEF75D00248EA57CB8D343DBF3B51F31`
(§A3.59 ghi `FD04499E…`; các hash trước giữ nguyên làm lịch sử).

Việc tiếp theo: **A3-058** — cho vùng A3-057 đi qua canonical lifecycle từ `enrich_zones` (expected
entered/exited/reacted lấy từ fixture, không gọi lifecycle thứ hai với ATR tự gán).

### A3.61 — Vùng D1 confirmed đi qua lifecycle canonical của `enrich_zones` (A3-058)

**Cách dựng fixture retest:** `_D1_RETEST_ROWS = _D1_SOURCE_ROWS + 5 nến`, giữ nguyên toàn bộ chuỗi
A3-057 (nên `_D1_BASE_INDEX=32`, `_D1_DEPARTURE_INDEX=33`, `_D1_BREAK_INDEX=34` vẫn đúng) và thêm dải
retest vào vùng demand `[99.2, 100.2]`:

| Nến | OHLC | Vai trò |
|---|---|---|
| 37 | `(105.0, 105.2, 101.5, 102.0)` | hạ về nhưng chưa chạm vùng (low `101.5 > 100.2 + 0.1`) |
| 38 | `(102.0, 102.2, 99.0, 100.0)` | **nến vào vùng** (overlap đầu tiên) |
| 39 | `(100.0, 100.2, 99.3, 99.8)` | còn trong vùng |
| 40 | `(100.4, 100.7, 100.35, 100.35)` | **thoát lên** (low `100.35 > 100.3`) nhưng close `100.35 < 100.2 + 0.25` ⇒ chưa phản ứng |
| 41 | `(100.4, 101.8, 100.35, 101.6)` | **follow-through**: close `101.6 ≥ 100.2 + 0.25` |

`_d1_retest_candles()` assert chính hình học đó trên nến (tolerance `max(1 tick, 0.05×ATR) = 0.1`, buffer
`max(2 tick, 0.10×ATR) = 0.2`, threshold `0.25×ATR = 0.25`) trước khi trả về — nên mốc thời gian mong đợi
là hệ quả của fixture, không phải của code production.

**Chuỗi kiểm:** `_d1_confirmed_source(_D1_RETEST_ROWS)` (detector + BOS thật của replay + confirmation) →
thêm metadata fixture `tick_size=0.1`, `atr_current=1.0` → `enrich_zones([...], candles, "ob", {}, {"status":
"unknown"}, tf_minutes=1440, symbol="EUR/USD", timeframe="D1", tick_size=0.1)`. **Không** gọi
`analyze_zone_lifecycle` lần hai: output được kiểm chính là output của `enrich_zones`.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_d1_confirmed_zone_timeline_comes_from_fixture_retest" -q --tb=short
1 passed in 0.38s

python -m pytest ...::test_r72_09_d1_source_is_confirmed_by_fixture_break ...::test_r72_09_d1_confirmed_zone_timeline_comes_from_fixture_retest -q
2 passed in 0.39s                    (A3-057 chạy lại vẫn PASS sau khi helper đổi sang swing causal)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
85 tests collected in 0.13s          (84 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
56 failed, 29 passed in 0.30s        (passed 28 → 29, failed giữ 56)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                  (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.28s                  (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
56 failed, 883 passed in 12.21s      (56 failed đều thuộc file acceptance)
```

**Phân loại:** **GREEN** — bước chuẩn bị, không kỳ vọng RED: lifecycle canonical đã tính đúng timeline
retest của fixture (`first_retest_index 38`, 1 visit `completed_reacted`, `entered_at/exited_at/reacted_at`
= close nến 38/40/41, không broken/stale/expiry). Giá trị bảo vệ: nếu lifecycle hồi quy (mất reaction, sai
mốc, tự invalidate), node đỏ ở đúng assert tương ứng. Ghi chú phạm vi: node **chỉ** chứng minh timeline
lifecycle; consumer D1 (`build_d1_reaction_evidence`) trên chính nguồn này là A3-060…A3-062.

**Thay đổi helper dùng chung (giữ A3-057 xanh):** `_d1_source_candles(rows=None)` và
`_d1_confirmed_source(rows=None)` nay nhận danh sách rows (mặc định `_D1_SOURCE_ROWS`), và swing xác nhận
được đọc **causal** trên `candles[:_D1_BREAK_INDEX + 1]` thay vì toàn chuỗi — vì 5 nến retest tạo thêm swing
high bar 36 (`105.2`) khiến "swing cao nhất của toàn chuỗi" đổi nghĩa. Node A3-057 đã chạy lại: **PASS**.

**Hash mới file acceptance:** `F1555E4912D7F0BA7BFAE69304C685F9DD839982C04FFFBC684FD35879640A74`
(§A3.60 ghi `5DE28DAA…`; các hash trước giữ nguyên làm lịch sử).

### A3.62 — Vùng D1 enriched qua typed restore (A3-059)

**Chuỗi kiểm:** `_d1_enriched_source()` (vùng confirmed A3-057 → `enrich_zones` của A3-058, kèm metadata
fixture `tick_size=0.1`/`atr_current=1.0`) → `SmcZone.from_dict(enriched, symbol=_D1_SYMBOL, timeframe="D1")`
(`typed`) → `SmcZone.from_dict(typed.to_dict())` (`restored`). Cả hai model được kiểm bằng **cùng một bộ
expected tính từ fixture**, không so `typed.to_dict()` với `restored.to_dict()`.

| Nhóm | Assert (mỗi giá trị dẫn xuất từ fixture) |
|---|---|
| Identity | `zone_id == enriched["zone_id"]`; `symbol == "EURUSD"` (dạng model chuẩn hoá của `_D1_SYMBOL`); `timeframe "D1"`, `family "ob"`, `direction "buy"` |
| Biên vùng | `low/high/original_low/original_high == 99.2/100.2` (nến base 32 của fixture) |
| Mốc nguồn | `origin_index 32`, `departure_end_index 33`, `confirmation_event_id == bos["event_id"]`, `confirmed_at == available_at ==` close nến 34, `lifecycle_status "confirmed"` |
| Timeline | `first_retest_index 38`, `first_retest_time` = close nến 38, `independent_retest_count 1`, `bars_spent_inside 2`, `lifecycle_mitigated True`, `broken False`, `invalidation_index`/`invalidated_at`/`expired_at` None |
| Visit | đúng 1 visit `completed_reacted`: `zone_id` khớp, `start_index 38`, `end_index 39`, `bars_spent_inside 2`, `entered_at`/`exited_at`/`reacted_at` = close nến 38/40/41 |

Helper mới: `_d1_close_at(candles, index)` = `candles[index].time + timedelta(days=1)` (close D1 suy từ
fixture) và `_d1_enriched_source()` (entry point dùng lại cho A3-060…A3-062).

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_d1_enriched_zone_survives_typed_restore" -q --tb=short
1 passed in 0.37s

python -m pytest <3 node R72-09 D1: confirmed_source + timeline + typed restore> -q
3 passed in 0.20s                    (A3-057, A3-058 chạy lại vẫn PASS)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
86 tests collected in 0.13s          (85 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
56 failed, 30 passed in 0.31s        (passed 29 → 30, failed giữ 56)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                  (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.27s                  (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
56 failed, 884 passed in 11.76s      (56 failed đều thuộc file acceptance)
```

**Phân loại:** **GREEN** — bước chuẩn bị, không kỳ vọng RED: typed restore **không mất** identity, biên vùng,
mốc nguồn hay timeline (kể cả `visits` qua cả hai vòng `from_dict`/`to_dict`). Giá trị bảo vệ: node sẽ đỏ nếu
`SmcZone.from_dict`/`to_dict` rơi `visits`, `available_at`, `original_low/high` hoặc đổi `lifecycle_status`.
Ghi chú: `symbol` ở model là dạng chuẩn hoá `EURUSD` (không phải `EUR/USD`) — đã assert đúng dạng đó thay vì
nới điều kiện.

**Hash mới file acceptance:** `42078DFA1CBE500A9251D08D8BA0F2978F2448BD3DCE27B17C254B3859D96D95`
(§A3.61 ghi `F1555E49…`; các hash trước giữ nguyên làm lịch sử).

Việc tiếp theo: **A3-060** — D1 integration positive: dùng chính vùng confirmed này, kiểm reaction trước
terminal bằng lifecycle canonical (valid/score>0 sau availability, trước terminal; loại khả năng pass từ
legacy flag).

### A3.63 — D1 reaction dương từ lifecycle canonical (A3-060)

**Chuỗi kiểm:** `_d1_enriched_source()` (A3-058) → payload = `SmcZone.from_dict(enriched).to_dict()`
(typed đã restore của A3-059) → `build_d1_reaction_evidence(payload, enriched, as_of=cutoff)` với lifecycle
là **chính** dict `enrich_zones` sinh ra. Không gọi `analyze_zone_lifecycle` lần hai.

**Cutoff:** `_d1_close_at(candles, len(candles) - 1)` = close nến 41 = `2026-02-12T00:00Z`. Đây là **sau**
`available_at` (`2026-02-05` = close nến 34) và **chưa terminal**: fixture không có invalidation/expiry cho
vùng này (assert `invalidation_index`/`invalidated_at`/`expiry_index`/`expired_at` đều `None`).

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_d1_reaction_positive_reads_canonical_lifecycle" -q --tb=short
1 passed in 0.39s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_09" --tb=short
6 passed, 81 deselected in 0.18s     (toàn bộ node R72-09 xanh)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
87 tests collected in 0.13s          (86 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
56 failed, 31 passed in 0.33s        (passed 30 → 31, failed giữ 56)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                  (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.29s                  (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
56 failed, 885 passed in 12.00s      (56 failed đều thuộc file acceptance)
```

**Kết quả evidence (dương) — giá trị đọc thật:**

```text
{'valid': True, 'score': 1.0, 'zone_id': 'smcz-39145ea0596368fd6556',
 'source_visit_id': 'smcz-39145ea0596368fd6556:visit-1', 'source_event_id': None,
 'reacted_at': '2026-02-12T00:00:00+00:00', 'age_bars': 7,
 'reason_codes': ['D1_REACTION_COMPLETED_REACTED']}
```

**Control loại legacy flag (âm):** cùng payload/lifecycle nhưng `visits=[]` **và** bật
`d1_reaction=True`, `proximity=True` ⇒ `{'valid': False, 'score': 0.0, 'reacted_at': None,
'reason_codes': ['D1_REACTION_NOT_COMPLETED_REACTED']}` — chứng minh đường pass là visit canonical, **không**
phải cờ legacy. Thêm precondition `"d1_reaction" not in payload` / `"proximity" not in payload` để payload
kiểm đúng là dạng canonical (typed).

**Phân loại:** **GREEN** — không kỳ vọng RED: consumer D1 đọc đúng visit `completed_reacted` của canonical
lifecycle. Đây là **ca dương end-to-end thật** cho R72-09 (detector → confirm → `enrich_zones` → typed
restore → D1), bổ sung cho ca H1 candidate smoke đã thu hẹp ở A3-056. Hai nhánh âm còn lại của chuỗi
(invalidated / expired) thuộc A3-061 và A3-062 nên R72-09 **chưa** đóng.

**Hash mới file acceptance:** `3366321C28615BCA8D81619570BEA9C2C42727EB19FD493AAAF4007CD1643225`
(§A3.62 ghi `42078DFA…`; các hash trước giữ nguyên làm lịch sử).

Việc tiếp theo: **A3-061** — D1 integration invalid: chuỗi A3-060 khi vùng bị invalidated (tại close
terminal: canonical status invalid/unusable, D1 invalid/0; lịch sử reaction trước đó còn).

### A3.64 — D1 tại terminal invalidation (A3-061)

**Fixture:** `_D1_INVALIDATION_ROWS` = chuỗi retest của A3-058 + 2 nến:

| Nến | OHLC | Vai trò |
|---|---|---|
| 42 | `(101.6, 101.7, 100.35, 100.4)` | vẫn **ngoài** vùng (low `100.35 > 100.3`) |
| 43 | `(100.4, 100.5, 98.5, 98.6)` | **breakdown**: đóng `98.6 < zone_low − buffer = 99.0` ⇒ invalidation + terminal |

`_d1_invalidated_candles()` assert: không nến nào 38..42 đóng qua buffer; bar 43 đóng qua buffer; reaction
của visit-1 (nến 41) vẫn **trước** breakdown.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer" -q --tb=long
1 failed in 0.50s
  E   assert 'confirmed' == 'invalid'          # dòng 2589 — assert contract ĐẦU TIÊN

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_09" --tb=no
1 failed, 6 passed, 81 deselected in 0.19s     (6 node còn lại của R72-09 vẫn xanh)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
88 tests collected in 0.14s                    (87 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
57 failed, 31 passed in 0.34s                  (failed 56 → 57, passed giữ 31)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                            (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.30s                            (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
57 failed, 885 passed in 9.26s                 (57 failed đều thuộc file acceptance)
```

**Phân loại RED — `implementation` (F03/R72-08 + F05/A-D04), test đúng:**

- **PASS trước khi tới contract:** terminal của lifecycle khớp fixture (`invalidation_index 43`,
  `invalidated_at` = close nến 43), `lifecycle_broken`/`broken` True, không expiry, `available_at` giữ
  nguyên; **lịch sử còn** — 2 visit với visit-1 `completed_reacted` nguyên `reacted_at` (close nến 41) và
  visit-2 `closed_by_invalidation` (`start=end=43`).
- **Control dương trước terminal:** cùng payload/lifecycle ở `as_of = 2026-02-12` trả `valid True`,
  `source_visit_id == visits[0]["visit_id"]`, `reacted_at` khớp ⇒ kết quả ở terminal **không** thể đổ cho
  "thiếu reaction".
- **RED tại contract** (dừng ở assert đầu): `lifecycle_status` vẫn `"confirmed"` thay vì `"invalid"`
  (R72-08). Probe cùng chuỗi trước khi viết node cho thấy hai gap còn lại cũng đỏ: key `usable` **thiếu**
  (kỳ vọng `False`) và D1 consumer tại terminal trả `valid True`/`score 1.0`
  (reason `D1_REACTION_COMPLETED_REACTED`) thay vì `valid False`/`0` theo A-D04 (cutoff == terminal).
- Đối chiếu họ terminal: nhánh **expiry** (A3-051, A3-055) đã GREEN ⇒ gap còn lại đúng là nhánh
  **invalidation**, khớp với ghi nhận từ A3-050/A3-052/A3-054.

**Hash mới file acceptance:** `D5A2CEA05CD7E36D0948788588E0F5B836C84979A78E2ED9270DA6618DAF6F1D`
(§A3.63 ghi `3366321C…`; các hash trước giữ nguyên làm lịch sử).

### A3.65 — D1 tại expiry theo tuổi (A3-062)

**Fixture:** `_D1_EXPIRY_ROWS` = chuỗi retest của A3-058 + **14 nến** (index 42..55) đều ở **ngoài** vùng
(`low > zone_high + tolerance = 100.3`) và không đóng qua buffer invalidation (`0.2`) ⇒ không mở visit mới.
Tuổi vùng tính từ anchor (nến xác nhận 34, `close >= available_at`) nên `age_at_index = index − 34`; lifetime
D1 đã duyệt là **20 nến** ⇒ nến đầu tiên có `age > 20` là index **55**, cũng là nến cuối fixture.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_d1_expired_source_is_terminal_for_the_consumer" -q --tb=long
1 passed in 0.41s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_09" --tb=no
1 failed, 7 passed, 81 deselected in 0.22s     (1 failed = A3-061 RED đã ghi; 7 node còn lại xanh)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
89 tests collected in 0.13s                    (88 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
57 failed, 32 passed in 0.37s                  (passed 31 → 32, failed giữ 57)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                            (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.32s                            (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
57 failed, 886 passed in 11.90s                (57 failed đều thuộc file acceptance)
```

**Giá trị đọc thật tại expiry:** `expiry_index 55`, `expired_at 2026-02-26T00:00:00+00:00` (= close nến 55,
tính từ fixture), `lifecycle_expired`/`lifecycle_stale` True, `lifecycle_broken`/`broken` False,
`invalidation_index`/`invalidated_at` None, `age_bars 21`, `lifecycle_status "expired"`, `usable False`,
`reason_codes` có `ZONE_EXPIRED`; evidence: `{'valid': False, 'score': 0.0, 'reacted_at': None, 'age_bars': 21,
'reason_codes': ['D1_REACTION_STALE']}` và 1 visit `completed_reacted` vẫn còn (`reacted_at` = close nến 41).

**Phân loại:** **GREEN** — bước chuẩn bị, không kỳ vọng RED: nhánh **expiry** đã đúng end-to-end (canonical
set `lifecycle_status "expired"`/`usable False`/`ZONE_EXPIRED`, consumer cắt bằng `D1_REACTION_STALE`). Việc
từ chối **không** do thiếu reaction (visit `completed_reacted` còn nguyên) và **không** do thiếu metadata
(`tick_size`/`atr_current` còn nguyên) — đúng yêu cầu hàng A3-062. Positive control của cùng vùng trước expiry
là **A3-060** (GREEN, valid/score>0), nên không cần gọi lifecycle lần hai với ATR tự gán.

**Ghi chú kỹ thuật (để không lặp lại):** nếu truyền lifecycle **cuối chuỗi** (đã expired) nhưng `as_of` đặt ở
mốc cũ, consumer **vẫn** từ chối vì gate `lifecycle_expired/stale/lifecycle_status` đọc trạng thái lifecycle
hiện tại, không theo cutoff — nên "control trước terminal" phải dùng lifecycle của **prefix** hoặc (như ở đây)
một node riêng trên chuỗi ngắn hơn (A3-060). Đã bỏ kiểu control đó khỏi node này.

**Hash mới file acceptance:** `34624536E34806C67398F47D7B385401AF60A92C06E14BB3AC3C557E5C738A67`
(§A3.64 ghi `D5A2CEA0…`; các hash trước giữ nguyên làm lịch sử).

Việc tiếp theo: **A3-063** — bù coverage và bàn giao theo §8.6 (bắt đầu từ mã chưa hoàn tất đầu tiên trong
dải A3-063…A3-090; đọc dòng task tương ứng trước khi làm).

### A3.66 — Mapping coverage §4 (A3-063)

**Việc đã làm (docs-only):** thêm mục `## Mapping coverage §4 — bảy cụm (A3-063)` vào
`smc-task-72-acceptance-matrix.md`: 7 bảng con (Metadata, Terminal/reaction, Pool/sweep, Owner, Contribution,
Consumed, Fixtures/fill), mỗi bảng 3 ô §4 → node acceptance thật hoặc ghi rõ phần thiếu + mã A3 sẽ bù.
Nguồn node: `python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q` (**89 tests
collected**) ngày 2026-09-11.

**Kiểm kê 21 ô §4 — trạng thái:**

| Cụm | Positive/control | Negative/boundary | Integration/parity |
|---|---|---|---|
| Metadata | ĐỦ | ĐỦ | MỘT PHẦN (thiếu A3-068: nguồn causal/không latest fallback) |
| Terminal/reaction | ĐỦ | ĐỦ | ĐỦ (1 node RED do core — A3-061) |
| Pool/sweep | ĐỦ | MỘT PHẦN (thiếu A3-065: threshold equality) | MỘT PHẦN (thiếu A3-066: prefix/batch provenance) |
| Owner | ĐỦ | MỘT PHẦN (thiếu A3-070/071/072: side/distance/time) | MỘT PHẦN (thiếu A3-069: enumerate→assign→project) |
| Contribution | ĐỦ | ĐỦ | **THIẾU — A3-074** (thêm metadata/child + control hai sweep độc lập) |
| Consumed | ĐỦ | ĐỦ | MỘT PHẦN (thiếu A3-078: run→restore→repeat trên caller) |
| Fixtures/fill | ĐỦ (fill REFERENCED task62) | **THIẾU** phần invalid-data cố ý — A3-080 (no-break/full-fill: REFERENCED) | ĐỦ (R56 REFERENCED) |

Tổng: **13 ĐỦ** (3 ô có phần REFERENCED) + **6 MỘT PHẦN** + **2 THIẾU**.

**Command/kết quả thật:**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
89 tests collected in 0.14s          # danh sách node dùng cho mapping; không đổi so với A3-062

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
57 failed, 32 passed in 0.36s        # không đổi (A3-063 không sửa test)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                  # không đổi baseline đang ghi

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.30s                  # không hồi quy

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
57 failed, 886 passed                # không đổi; 57 failed đều thuộc file acceptance
```

**Phân loại:** bước **kiểm kê coverage**, không sinh RED/GREEN test mới. Giá trị sử dụng: chốt danh sách ô
còn thiếu kèm mã phụ trách, để A3-064…A3-080 chỉ bù đúng chỗ và A3-081 giữ nguyên quy ước (không dùng
`[buy/sell]` như node chạy được). Không tự làm các mã bù trong bước này.

**Hash file acceptance:** giữ `34624536E34806C67398F47D7B385401AF60A92C06E14BB3AC3C557E5C738A67` (không đổi —
A3-063 chỉ sửa tài liệu).

Việc tiếp theo: **A3-064** — audit provisional và missing source/provenance ở đường pool (reuse A3-010/043 và
ca provisional; đủ từng nguồn thiếu riêng, không lấy tên finding làm coverage).

### A3.67 — Audit provisional và missing source/provenance (A3-064)

**Nguồn luật:** interface pool A3-005 (mục `## Interface pool — chốt theo review A lần2` trong M), **luật 3**:
*"Canonical sweep thiếu `records` hoặc thiếu provenance ⇒ fail closed, không fallback sang level numeric"*.

**Kết quả audit — nguồn/provenance trên đường pool→sweep:**

| Ca | Đã có node? | Kết luận |
|---|---|---|
| Pool numeric-only, **không** có `records` | Có — `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[buy/sell]` | **reuse** |
| Source `provisional=True` | Có — `test_r72_01_provisional_source_cannot_create_a_sweep` | **reuse** |
| Source `usable=False` | Có — `test_r72_01_equal_pool_without_usable_source_does_not_exist` | **reuse** |
| Lineage hợp lệ (positive) | Có — `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy/sell]` | **reuse** |
| `records` có nhưng **không mang level bị sweep** | **Chưa** | **thêm mới** (`record_for_other_level`) |
| Record **không có** `source_ids`/`sources` | **Chưa** | **thêm mới** (`no_sources`) |
| `source_ids` **trỏ nguồn vắng mặt** trong `sources` | **Chưa** | **thêm mới** (`dangling_source_id`) |
| Source thiếu **ID provenance** (`swing_id`) | **Chưa** | **thêm mới** (`source_without_provenance_id`) |
| Source thiếu **`usable_at`** (mốc causal) | **Chưa** | **thêm mới** (`source_without_usable_at`) |

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_missing_pool_provenance_fails_closed" -q --tb=line
5 failed, 89 deselected in 0.41s
  E  AssertionError: assert [{'index': 2, ...}] == []      # dòng 660 — canonical vẫn cấp sweep

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_01" --tb=no
15 failed, 4 passed, 75 deselected in 0.18s     # R72-01: RED 10 → 15, GREEN giữ 4

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
94 tests collected in 0.13s                     (89 + 5)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
62 failed, 32 passed in 0.38s                   (failed 57 → 62, passed giữ 32)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                             (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.27s                             (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
62 failed, 886 passed in 12.12s                 (62 failed đều thuộc file acceptance)
```

**Kiểm chứng độc lập trước khi kết luận RED (probe read-only, cùng fixture):**

```text
legacy (không liquidity_pools)      → swept_lows index [2]                    # fixture thật sự sweep được
canonical, record sai level         → swept_lows index [2], source_swing_id "pool-source"
canonical, record không sources     → swept_lows index [2], source_swing_id "pool-source"
```

⇒ Kết quả hiện tại **không** đến từ fixture thiếu excursion; `core/` chưa đọc `records` nên vẫn cấp sweep từ
level numeric. Đó là **implementation gap (F06)**, không phải test/fixture sai.

**Phân loại:** RED **5/5** loại `implementation` (F06). Precondition của từng ca (**đúng** một khuyết điểm
provenance + hình học excursion/reclaim) và **control legacy** đều PASS. Node mới không nhân đôi BUY/SELL vì
trục kiểm là loại khuyết điểm; mirror SELL của cùng hình học đã có ở A3-010[sell] và A3-042[sell].

**Ghi chú sự cố (đã khắc phục ngay):** một lệnh Edit của tôi (old/new chỉ khác dấu xuống dòng) đã ghép nhầm
dòng `def test_r72_01_provisional_source_cannot_create_a_sweep():` với dòng thân đầu tiên; đã sửa lại ngay và
kiểm chứng bằng `ast.parse` + `--collect-only` (89 node, 57 failed/32 passed — đúng như trước khi thao tác)
trước khi thêm node mới.

**Hash mới file acceptance:** `906780EF5A7D9D0622833DEC8B6463E1B2A81E12AA43396CBA897D730C655BA3`
(§A3.66 ghi `34624536…`; các hash trước giữ nguyên làm lịch sử).

Việc tiếp theo: **A3-065** — audit equality và vượt excursion threshold (đúng biên chưa đủ, vượt mới có thể
nhận khi reclaim/source hợp lệ; BUY/SELL).

### A3.68 — Audit strict excursion threshold (A3-065)

**Rule đang áp dụng (đã duyệt):** excursion `= max(2*tick, 0.10*ATR)`; sweep chỉ khi penetration **vượt** biên
(`candle.low < level − excursion` cho BUY, `candle.high > level + excursion` cho SELL) **và** reclaim trong cùng
nến (`close > level` / `close < level`). Code hiện tại dùng bất đẳng thức **strict** (`<`/`>`), không `>=`.

**Fixture:** H1 8 nến buy-shape, nến sweep `rows[2] = (110, 111, 100 − depth, 100.1)` với
`depth = excursion + slack`, `slack ∈ {−0.05 (below), 0 (equal), +0.05 (beyond)}`; tick `0.1`, ATR `1.0`
⇒ `excursion = 0.2`, `depth ∈ {0.15, 0.2, 0.25}`. SELL dùng **đúng** rows đó qua mirror của `_probe.candles`
(mirror quanh 210: level `100 ↔ 110`), không tự mirror thủ công.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_excursion_threshold_is_strict" -q --tb=short
6 passed, 94 deselected in 0.41s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_01" --tb=no
15 failed, 10 passed, 75 deselected in 0.19s     (R72-01: GREEN 4 → 10)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
100 tests collected in 0.13s                     (94 + 6)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
62 failed, 38 passed in 0.39s                    (passed 32 → 38, failed giữ 62)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.26s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
62 failed, 892 passed in 12.29s                  (62 failed đều thuộc file acceptance)
```

**Kết quả theo từng mức (giá trị đọc thật):**

| Mức | `slack` | `depth` | BUY | SELL |
|---|---|---|---|---|
| `below` | −0.05 | 0.15 | `swept_lows == []` | `swept_highs == []` |
| `equal` | 0 | 0.20 | `swept_lows == []` (**đúng biên chưa đủ**) | `swept_highs == []` |
| `beyond` | +0.05 | 0.25 | 1 sweep `index 2`, `depth 0.25`, `source_swing_id "pool-source"` | như trên, `level 110` |

**Phân loại:** **GREEN 6/6** — audit cho thấy rule strict **đã đúng** trong `core/`, không cần sửa
implementation. Giá trị bảo vệ: nếu ai đó nới thành `>=`, hai param `equal` đỏ ngay; nếu bỏ reclaim trong
cùng nến, precondition đỏ. Không đổi ngưỡng, chỉ dùng đúng `max(2*tick, 0.10*ATR)` đã duyệt.

**Hash mới file acceptance:** `33A0FB40A730DAE96C0186EFD720488160C4519B5937377468BDF08E9C213498`
(§A3.67 ghi `906780EF…`; các hash trước giữ nguyên làm lịch sử).

### A3.69 — Audit causal prefix/batch và rolling index (A3-066)

**Fixture dùng chung:** `_POOL_CAUSAL_ROWS` = 12 nến của A3-044 (pivot low idx4 = `99.5`, sweep idx10)
**+ 4 nến đuôi** tạo thêm swing high idx13 (`106.5`) và một swept high idx14. Helper:
`_pool_causal_candles(rows, offset)` (build H1 y như probe; `offset` cho phép bỏ nến đầu mà giữ nguyên
timestamp), `_pool_causal_run(values)` (producer → `detect_liquidity_pools` → `detect_liquidity_sweeps` với
`lookback_bars = len(series)`), `_pool_causal_evidence(sweep)` (12 field causal, **trừ** `index` vì index là
vị trí, không phải identity).

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_pool_sweep_evidence_survives_future_bars" \
                 "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_pool_sweep_identity_survives_rolling_index" -q --tb=short
2 passed, 100 deselected in 0.43s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_01" --tb=no
15 failed, 12 passed, 75 deselected in 0.19s     (R72-01: GREEN 10 → 12)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
102 tests collected in 0.15s                     (100 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
62 failed, 40 passed in 0.39s                    (passed 38 → 40, failed giữ 62)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.32s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
62 failed, 894 passed in 12.22s                  (62 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe cùng fixture trước khi viết node):**

```text
prefix(12)  swing low idx4  swing_id smcs-a3eedff40ca702ee7827  confirmed_at 2026-09-01T07:00
batch(16)   swing low idx4  swing_id smcs-a3eedff40ca702ee7827  confirmed_at 2026-09-01T07:00   # y nguyên
            swept_lows      idx10 sweep_id smcs-cf78c21551731fca9a77  reclaimed_at 2026-09-01T11:00
batch(16)   swept_lows      idx10 sweep_id smcs-cf78c21551731fca9a77  reclaimed_at 2026-09-01T11:00   # y nguyên
            swept_highs     idx14 (chỉ batch có)
rolled(15, offset 1)  low idx3  swing_id smcs-a3eedff40ca702ee7827   # identity không đổi, index dịch 1
                      swept_lows idx9  sweep_id smcs-cf78c21551731fca9a77  reclaimed_at 2026-09-01T11:00
```

**Phân loại:** **GREEN 2/2** — audit xác nhận tính causal **đã đúng** trong các seam đã implement:
thêm nến tương lai không đổi evidence đã biết trước cutoff, và rolling index không đổi causal identity
(`swing_id`/`sweep_id` bám thời điểm + level, không bám vị trí) cũng không backdate `confirmed_at`.
Giá trị bảo vệ: node đỏ nếu producer backdate confirmation, đổi `swing_id` theo vị trí, hoặc sweep lấy
identity theo index.

**Giới hạn phạm vi (đã ghi rõ, không tự bịa):** phần "pool ID/source/usable time" ở dạng **canonical
`records`** (A3-005) — `records.pool_id`, mỗi source có `usable_at` — **chưa** tồn tại trong `core/`, nên
audit chỉ kiểm được `source_pool_id`/`source_swing_id` của projection numeric và `confirmed_at` của swing.
Phần canonical đó vẫn thuộc **F06** (đã ghi ở A3-064 và A3-010), không tính là đã phủ.

**Hash mới file acceptance:** `DF673830D4A25CBF18D941C670011AB0E59E183474FE1DD4A54E137150E091A7`
(§A3.68 ghi `33A0FB40…`; các hash trước giữ nguyên làm lịch sử).

Việc tiếp theo: **A3-067** — audit override hợp lệ của rule metadata (ghi đúng parameter/rule đang hỗ trợ
override; chỉ thay requirement của rule đó, không cứu thiếu nguồn/metadata khác; tick argument không được tự
thắng tick item mâu thuẫn — A-D07; không thêm override mới).

### A3.70 — Audit explicit override (A3-067)

**Override đang hỗ trợ (đọc chữ ký hàm, không thêm mới):** `excursion_buffer` (`detect_liquidity_sweeps`),
`equal_tolerance` (`detect_liquidity_pools`), `zone_tolerance` + `break_buffer` (`analyze_zone_lifecycle`),
và `tick_size` đối số ở các seam lifecycle/context (A-D07). `enrich_zones` **không** có `zone_tolerance`; nó
chỉ forward `available_at`, `tick_size`, `atr_current`, `break_buffer` từ item. `structure_break_buffer`
không có override (cần cả tick và ATR — A3-015/016/017). Bảng đầy đủ ở M, mục
[Override audit — A3-067](smc-task-72-acceptance-matrix.md#override-audit--a3-067).

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_excursion_override_only_replaces_its_own_rule" \
                 "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_equal_tolerance_override_only_replaces_its_own_rule" \
                 "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule" -q --tb=short
3 passed, 102 deselected in 0.49s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_07" --tb=no
12 failed, 5 passed, 88 deselected in 0.17s      (R72-07: GREEN 5 → 8, RED giữ 12)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
105 tests collected in 0.14s                     (102 + 3)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
62 failed, 43 passed in 0.39s                    (passed 40 → 43, failed giữ 62)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.27s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
62 failed, 897 passed in 11.99s                  (62 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe cùng fixture trước khi viết node):**

```text
excursion:  không override (tick .1/ATR 1) → swept_lows []          # penetration 0.10 < 0.2
            override 0.05 + source hợp lệ  → swept_lows [2]          # override là nguyên nhân
            override 0.05 + provisional    → []
            override 0.05 + usable=False   → []
equal tol:  mặc định                     → equal_lows [100.025], equal_tolerance 0.2
            override 0.01                → equal_lows [], tolerance 0.01, swing_lows giữ 2 level
            override 1.0 + 1 source unusable → equal_lows []
lifecycle:  mặc định                     → visits 0,  buffer 0.1
            zone_tolerance=0.5           → visits 1,  buffer 0.1 (rule khác không đổi)
            zone_tolerance=0.5, no tick/ATR → visits 1, buffer 0.0 (không tạo metadata)
            break_buffer=0.05            → buffer 0.05, lifecycle_broken True (mặc định False)
```

**Phân loại:** **GREEN 3/3** — audit xác nhận mỗi override **chỉ** thay đúng rule của nó: (a) đổi được ngưỡng
của chính rule (control chứng minh override là nguyên nhân chứ không phải fixture), (b) **không** cứu
source/provenance thiếu (`provisional`/`usable=False`/`confirmed=False` vẫn không sweep; source unusable vẫn
không thành cặp equal), (c) **không** tạo metadata còn thiếu (thiếu tick/ATR ⇒ buffer fail-closed `0.0`).
Không đổi ngưỡng nào; phần A-D07 chỉ **reuse** node đã có, không viết lại.

> **Đính chính (2026-09-11, §A3.98 — A3R3-02):** vế (c) như ghi ở trên **sai contract** — `0.0` không phải
> nghĩa “không biết”. Ca thiếu tick/ATR nay khóa `metadata_state unknown` + reason + `invalidation_buffer
> None` + `lifecycle_broken False`; phần mô tả cũ giữ nguyên làm lịch sử.

**Hash mới file acceptance:** `A8B47C0BE433D28529484A626D2D11AD4442D87086560616E6344A59768C50DB`
(§A3.69 ghi `DF673830…`; các hash trước giữ nguyên làm lịch sử).

Việc tiếp theo: **A3-068** — audit nguồn metadata tại thời điểm đánh giá (timeframe/cutoff đúng; không dùng
nến tương lai/latest fallback khi thiếu nguồn; phân biệt ATR formation với ATR current theo đúng rule được
kiểm).

### A3.71 — Audit nguồn ATR/tick tại thời điểm đánh giá (A3-068)

**Fixture:** `_atr_source_candles(extra_rows=())` = 16 nến H1 calm `(100,101,99,100.5)` + base bearish idx16
(`(101,101.5,99.0,99.5)`) + departure idx17 (`(99.6,104.0,99.5,103.5)`) + 2 nến đuôi; `extra_rows` để nối nến
tương lai. Chuỗi warm-up ngắn = 10 calm + base + departure (departure idx11, prefix 11 < ngưỡng 15).

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_formation_atr_is_causal_and_never_latest_fallback" \
                 "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_formation_and_current_atr_keep_their_own_source" -q --tb=short
2 passed, 105 deselected in 0.46s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_07" --tb=no
12 failed, 7 passed, 88 deselected in 0.18s      (R72-07: GREEN 8 → 10)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
107 tests collected in 0.14s                     (105 + 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
62 failed, 45 passed in 0.40s                    (passed 43 → 45, failed giữ 62)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.27s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
62 failed, 899 passed in 11.66s                  (62 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe cùng fixture trước khi viết node):**

```text
reference @idx17  value 2.0357142857142856, period 14, timeframe H1
                  reference_time 2026-09-01T17:00  (= close nến trước sự kiện)
                  event_time     2026-09-01T18:00  (= close nến sự kiện)
nối 5 nến biến động (90,120,80,110)  → giá trị tại idx17 KHÔNG đổi
prefix 11 (< 15)  → atr_reference_before_event = None
                    measure_departure status "unavailable", reason ["DEPARTURE_ATR_UNAVAILABLE"]
                    candidate departure_measurement.status "unavailable"
                    confirm với BOS hợp lệ → "candidate", available_at None,
                      reason có OB_DEPARTURE_MEASUREMENT_UNAVAILABLE
                    control: cùng event shape + candidate có ATR → "confirmed", available_at stamp(19)
formation (idx17) = 2.0357142857142856   current (nến cuối, +4 nến biến động) = 9.666099150826065
detector departure_measurement.atr_before_event = 2.0357… (formation)
invalidation_buffer(current)   = 0.4833049575413033 = max(1×0.1, 0.05×current)
invalidation_buffer(formation) = 0.10178571428571428 = max(1×0.1, 0.05×formation)
timeframe="M1"                    → ValueError "Unsupported SMC timeframe: M1"
event_time không khớp candle close → ValueError "event_time must match exactly one candle close"
```

**Phân loại:** **GREEN 2/2** — audit xác nhận nguồn metadata đọc đúng **thời điểm đánh giá**: (a) ATR
formation là **causal** (reference ở close trước nến sự kiện, `period 14`), nến tương lai **không** đổi được
giá trị, thiếu warm-up ⇒ `None` và **không** có latest fallback — fail closed tới cả bước confirmation;
(b) ATR formation và ATR current **không** hoán nguồn cho nhau (detector dùng formation, lifecycle dùng
`atr_current`), buffer mỗi bên theo nguồn của mình; (c) timeframe/cutoff sai ⇒ lỗi rõ, không default.
Giá trị bảo vệ: node đỏ nếu ai thêm fallback "latest ATR", lấy reference ở cuối chuỗi, hoặc cho lifecycle
dùng formation thay current.

**Hash mới file acceptance:** `3A325063FABB9AFC6C5775DC746DBE9EDE0FD4CF30247F0FF54F56C5153C0AC4`
(§A3.70 ghi `A8B47C0B…`; các hash trước giữ nguyên làm lịch sử).

Việc tiếp theo: **A3-069** — audit early-far thắng late-near qua context với thứ tự đảo
(`_attach_zone_sweep_links` thực sự enumerate→assign→project; owner theo claim time, không chỉ helper độc lập
pass).

### A3.72 — Audit owner theo claim time ở tầng context (A3-069)

**Fixture:** 2 zone claim cùng một sweep (dùng helper của probe, không tự dựng lại):
`early` = `zone("early-child", "early", 13, 105.2, 106)` (available hour 13, **xa** sweep) và
`late` = `zone("late-child", "late", 15, 100, 110)` (hour 15, **gần** hơn). Chạy `_probe.attach(zones, sweeps)`
⇒ `_attach_zone_sweep_links((("demand", zones),), sweeps, candles=..., symbol="EURUSD", timeframe="H1", tf_minutes=60)`.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_context_owner_follows_claim_time_under_input_permutation" -q --tb=short
1 failed in 0.57s
  E   assert 'late' == 'early'          # dòng 291 — assert contract ĐẦU TIÊN

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_02" --tb=no
4 failed, 1 passed, 103 deselected in 0.16s      (R72-02: RED 3 → 4)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
108 tests collected in 0.15s                     (107 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
63 failed, 45 passed in 0.41s                    (failed 62 → 63, passed giữ 45)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.28s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
63 failed, 899 passed in 11.95s                  (63 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe cùng fixture trước khi viết node):**

```text
[early, late]  owner_setup_id "late"  assignment_id smca-30bb697d628ee9c39480
               linked_zone_id "late-child"  claim_eligible_at stamp(15)  consumed True  contribution_applied True
[late, early]  owner_setup_id "late"  assignment_id smca-30bb697d628ee9c39480   # y nguyên
⇒ đảo thứ tự KHÔNG đổi kết quả (invariance đúng) nhưng owner vẫn là zone GẦN, không phải claim sớm nhất
```

**Phân loại RED — `implementation` (F08), test đúng:**

- **PASS trước contract:** cả hai thứ tự đều được caller chiếu (`owner_setup_id`, `assignment_id`,
  `consumed True`, `contribution_applied True`) và bất biến dưới permutation (owner/assignment/linked zone/
  claim time không đổi) ⇒ chứng minh caller thực hiện enumerate→assign→project, không phải chỉ helper pass.
- **RED tại contract:** owner là `"late"` (distance rank) thay vì `"early"` (claim sớm nhất theo A-D02), kèm
  `linked_zone_id`/`claim_eligible_at` lệch theo (`late-child`/`stamp(15)`). Dừng ở assert đầu nên hai assert
  sau (`linked_zone_id`, `claim_eligible_at`) cũng cùng nguyên nhân.
- **Đối chiếu phạm vi:** helper độc lập đã GREEN (`test_r72_02_same_time_tie_is_stable_under_claim_permutation`)
  ⇒ gap nằm ở **caller context**, đúng yêu cầu hàng A3-069 ("không chỉ helper độc lập pass").

**Hash mới file acceptance:** `C147EEF5B0DBF6E2A3CA5A1D559EE280A14A3BF9203A1AEF7F5B87C26F016684`
(§A3.71 ghi `3A325063…`; các hash trước giữ nguyên làm lịch sử).

### A3.73 — Audit claim sai chiều (A3-070)

**Fixture:** zone sai chiều `supply_zone`/`sell` bounds `[104.95, 105.05]` (khe giá `0.05` tới level sweep `105`
— **gần hơn**) và zone hợp lệ `demand_zone`/`buy` bounds `[105.2, 106]` (khe `0.2`); sweep của probe
(`swept_low`, level `105`, `time stamp(10)`, `reclaimed_at stamp(11)`, `side "buy"`); `atr_value = 1.0`.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_opposite_side_claim_cannot_own_a_sweep" -q --tb=short
1 passed, 108 deselected in 0.45s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_02" --tb=no
4 failed, 2 passed, 103 deselected in 0.16s      (R72-02: GREEN 1 → 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
109 tests collected in 0.14s                     (108 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
63 failed, 46 passed in 0.42s                    (passed 45 → 46, failed giữ 63)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.26s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
63 failed, 900 passed in 11.51s                  (63 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe cùng fixture trước khi viết node):**

```text
associate_sweeps_to_zones([wrong, right], sweep, atr_value=1.0)
  → links chỉ có 'right-side-child' với distance_atr 0.2, time_delta 2      # wrong-side bị loại dù gần hơn
associate_sweeps_to_zones([right, wrong], ...)  → y nguyên
context (attach) [wrong, right] và [right, wrong]
  → owner_setup_id "right-side"; wrong-side: liquidity_sweep_linked False, linked_sweep_id None
```

**Phân loại:** **GREEN 1/1** — audit xác nhận rule chiều **đã đúng ở cả hai tầng**: `associate_sweeps_to_zones`
so `zone_side != sweep_side` **trước** mọi kiểm giá/thời gian, nên zone sai chiều bị loại **dù gần hơn**; zone
đúng chiều vẫn được chọn (positive control nằm trong cùng node). Giá trị bảo vệ: node đỏ nếu ai bỏ kiểm chiều
ở tầng link hoặc để distance/time quyết định trước chiều.

**Ghi nhận phạm vi (không tạo RED giả):** `assign_sweep_ownership` chỉ kiểm `side ∈ {buy, sell}`, **không** so
với chiều của sweep — nhưng ở caller chuẩn, claim chỉ được sinh từ cặp zone–sweep **đã qua tầng link
side-aware** (`_attach_zone_sweep_links` lấy claim từ `links`), nên claim sai chiều không tới được assignment.
Node kiểm đúng đường đi thật (link → claim → project), không dựng input mà production không tạo ra. Phần
"ngoài khoảng cách" (A3-071) và "ngoài cửa sổ thời gian" (A3-072) vẫn chưa có node.

**Hash mới file acceptance:** `357D8CE299EE25BC9FC5BE634B94A6391FF0171F5A38B92C6394335964E98683`
(§A3.72 ghi `C147EEF5…`; các hash trước giữ nguyên làm lịch sử).

### A3.74 — Audit claim ngoài khoảng cách (A3-071)

**Rule đang áp dụng:** `associate_sweeps_to_zones(..., tolerance_atr = SWEEP_ZONE_TOLERANCE_ATR = 0.25)`;
`price_distance = _distance_to_zone(sweep_level, zone_low, zone_high)`, `distance_atr = price_distance / ATR`
(bằng `0.0` khi level nằm trong band), và loại khi **`distance_atr > tolerance`** ⇒ **biên bao gồm**.

**Fixture:** sweep level `105`, `atr_value = 1.0` ⇒ tolerance `0.25` = khe giá `0.25`.

```text
[104,106]      trong      → link, distance_atr 0.0
[105.25,106]   đúng biên  → link, distance_atr 0.25     (0.25 KHÔNG bị loại)
[105.26,106]   ngoài      → KHÔNG link (không sinh claim)
```

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep" -q --tb=short
1 passed, 109 deselected in 0.45s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_02" --tb=no
4 failed, 3 passed, 103 deselected in 0.17s      (R72-02: GREEN 2 → 3)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
110 tests collected in 0.14s                     (109 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
63 failed, 47 passed in 0.40s                    (passed 46 → 47, failed giữ 63)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.27s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
63 failed, 901 passed in 12.25s                  (63 failed đều thuộc file acceptance)
```

**Giá trị đọc thật ở tầng context (probe read-only, cùng fixture):**

```text
zone ngoài khoảng [105.26,106] available hour 13 (SỚM hơn)  → liquidity_sweep_linked False
zone trong khoảng [104,106]    available hour 15            → liquidity_sweep_linked True
owner (cả hai thứ tự [outside,inside] và [inside,outside])  → "inside-late"
```

**Phân loại:** **GREEN 1/1** — audit xác nhận rule khoảng cách **đã đúng**: biên bao gồm (`0.25` nhận, `0.26`
loại), ngoài khoảng **fail closed** (không sinh claim), và ở tầng context zone ngoài khoảng **không** thắng
dù có `available_at` sớm hơn ⇒ đúng vế "claim không đủ không thắng bằng timestamp sớm". Giá trị bảo vệ: node
đỏ nếu ai nới biên thành `>=`, bỏ kiểm khoảng cách, hoặc để claim ngoài khoảng tham gia xếp hạng.

**Hash mới file acceptance:** `3D65FC5FF39E5FAD36A15718CE5CC44B1DC34EF690A30948130A013EF3F4BAD9`
(§A3.73 ghi `357D8CE2…`; các hash trước giữ nguyên làm lịch sử).

### A3.75 — Audit claim ngoài cửa sổ thời gian (A3-072)

**Rule đang áp dụng:** trong `candidate_link`, một link hợp lệ cần `formation_start ≤ sweep_index ≤
departure_end_index` **và** `sweep_index - formation_start <= time_window`, với `time_window = max_time_bars`
(mặc định `20`; ở đây truyền `3` để fixture nhỏ mà **không** đổi rule).

**Fixture:** sweep idx `10`; `formation_start_index` lần lượt `8` / `7` / `6` (giữ `departure_end_index 12`),
và một biến thể cửa sổ kết thúc trước sweep (`formation_start 0`, `departure_end_index 9`).

```text
start 8  delta 2  (≤ window 3)  → link, distance_atr 0.0
start 7  delta 3  (== window)   → link            (biên BAO GỒM)
start 6  delta 4  (> window)    → KHÔNG link
start 0, departure 9 (< sweep 10) → KHÔNG link     (ngoài cửa sổ formation/departure)
```

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_claim_outside_time_window_cannot_own_a_sweep" -q --tb=short
1 passed, 110 deselected in 0.48s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_02" --tb=no
4 failed, 4 passed, 103 deselected in 0.16s      (R72-02: GREEN 3 → 4)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
111 tests collected in 0.14s                     (110 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
63 failed, 48 passed in 0.40s                    (passed 47 → 48, failed giữ 63)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.28s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
63 failed, 902 passed in 11.87s                  (63 failed đều thuộc file acceptance)
```

**Giá trị đọc thật ở tầng context (probe read-only, cùng fixture, window mặc định):**

```text
zone hết cửa sổ (departure 9 < sweep 10) available hour 13 (SỚM hơn) → liquidity_sweep_linked False
zone trong cửa sổ (8..12)                available hour 15           → liquidity_sweep_linked True
owner (cả hai thứ tự)                                                → "in-window"
```

**Phân loại:** **GREEN 1/1** — audit xác nhận rule cửa sổ thời gian **đã đúng**: biên **bao gồm**
(delta `3` nhận, `4` loại), vế `formation_start ≤ sweep_index ≤ departure_end_index` loại sweep nằm ngoài cửa
sổ formation/departure, và tầng context zone ngoài cửa sổ **không** thắng dù `available_at` sớm hơn. Không
nới window để test đạt. Giá trị bảo vệ: node đỏ nếu ai nới window, bỏ vế `sweep_index − formation_start`,
hoặc để zone ngoài cửa sổ tham gia xếp hạng.

**Hash mới file acceptance:** `B34FC1A03047878D32F970EC7AB64824F6048DB76DE9582173DCD2A43E024F36`
(§A3.74 ghi `3D65FC5F…`; các hash trước giữ nguyên làm lịch sử).

### A3.76 — Audit tie-break khi claim time bằng nhau (A3-073)

**Reuse (helper đã đủ — chỉ chạy lại, không viết lại):** `test_r72_02_same_time_tie_is_stable_under_claim_permutation`
dùng 2 claim cùng `setup_available_at`/`reclaimed_at`, owner là setup ID nhỏ (`"early"`) ở **cả hai thứ tự**;
fixture của nó còn phân biệt được setup-ID-first với zone-ID-first (claim thua có zone ID nhỏ hơn). Kết quả
chạy lại: **PASS**.

**Phần context:** trước lượt này **chưa** có node cho trường hợp *cùng claim time* ở tầng caller (A3-069 phủ
trường hợp khác claim time). Node mới `test_r72_02_context_same_time_tie_follows_stable_setup_id`:

```text
2 zone cùng available_at stamp(13), cùng ăn sweep (level 105):
  alpha-setup  / z-winner-child   (setup ID NHỎ hơn, zone ID lớn hơn)
  beta-setup   / a-loser-child    (setup ID lớn hơn, zone ID NHỎ hơn)
⇒ nếu caller tie-break theo zone ID thì chọn beta; theo setup ID (rule A-D02) thì chọn alpha
```

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_context_same_time_tie_follows_stable_setup_id" -q --tb=short
1 failed in 0.59s
  E   assert 'beta-setup' == 'alpha-setup'      # dòng 496 — assert contract ĐẦU TIÊN

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_02" --tb=no
5 failed, 4 passed, 103 deselected in 0.16s      (R72-02: RED 4 → 5)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
112 tests collected in 0.14s                     (111 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
64 failed, 48 passed in 0.41s                    (failed 63 → 64, passed giữ 48)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.32s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
64 failed, 902 passed in 12.04s                  (64 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe cùng fixture trước khi viết node):**

```text
[alpha-setup/z-winner-child, beta-setup/a-loser-child] và thứ tự đảo
  → owner "beta-setup", linked_zone_id "a-loser-child", claim_eligible_at stamp(13)   (giống nhau cả hai lượt)
  → per-zone: a-loser-child liquidity_sweep_linked True; z-winner-child False          (link one-to-one)
```

**Phân loại RED — `implementation` (F08), test đúng:**

- **PASS trước contract:** hai zone cùng `available_at`; mỗi zone link được khi chạy riêng (tie thật, không
  phải do một zone không đủ điều kiện); link one-to-one nên mỗi lượt đúng 1 zone mang link; đảo thứ tự
  **không** đổi owner/assignment/linked zone; `claim_eligible_at` = availability chung.
- **RED tại contract:** caller chọn `"beta-setup"`/`"a-loser-child"` (theo **zone ID**) thay vì `"alpha-setup"`
  (setup ID ổn định theo A-D02). Cùng họ F08 với A3-069 nhưng ở **trục tie-break** (A3-069 là trục claim time).
- **Ghi nhận phạm vi:** hàng A3-073 chỉ đạo "nếu helper đã đủ thì reuse, ghi riêng coverage context từ 069";
  helper đã đủ (reuse, không viết lại) và 069 phủ trường hợp context *khác claim time* — còn ô "same-time
  owner tie ở context" **chưa** có node nên lượt này bù đúng ô đó bằng **một** node mới (không nhân bản 069).

**Hash mới file acceptance:** `47E92C983C76A60176BDB59A2DB02CC51EBFB222C83FEAFDF1F8B9DBB4ED7CCB`
(§A3.75 ghi `B34FC1A0…`; các hash trước giữ nguyên làm lịch sử).

### A3.77 — Audit contribution theo từng sweep (A3-074)

**Fixture:** 5 claim của **cùng owner** `owner-1` trên **2 sweep độc lập** (`sweep-a`, `sweep-b`), cùng claim
time (`setup_available_at = stamp(13)`, `reclaimed_at = stamp(11)`):

| Sweep | Claim | Ghi chú |
|---|---|---|
| `sweep-a` | `child-b` | thường |
| `sweep-a` | `child-a` | `family="fvg"` (multi-family) |
| `sweep-a` | `child-c` | `family="ob"` + `note="metadata"` |
| `sweep-b` | `child-d` | thường |
| `sweep-b` | `child-e` | `family="fvg"` |

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_03_contribution_is_counted_per_sweep_not_per_list" -q --tb=short
1 passed, 112 deselected in 0.49s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_03" --tb=no
2 failed, 2 passed, 109 deselected in 0.15s      (R72-03: GREEN 1 → 2)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
113 tests collected in 0.14s                     (112 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
64 failed, 49 passed in 0.40s                    (passed 48 → 49, failed giữ 64)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.28s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
64 failed, 903 passed in 12.32s                  (64 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe cùng fixture trước khi viết node):**

```text
tổng contribution toàn danh sách: 2                      # KHÔNG cap về 1
per sweep: {"sweep-a": 1, "sweep-b": 1}
con được credit: {"sweep-a": "child-a", "sweep-b": "child-d"}   # con đầu tiên theo zone ID
owner mỗi sweep: {"sweep-a": "owner-1", "sweep-b": "owner-1"}
đảo thứ tự input → per sweep và con credit KHÔNG đổi
```

**Phân loại:** **GREEN 1/1** — audit xác nhận rule contribution **theo sweep** đã đúng: logic gom nhóm theo
`sweep_id` (`contribution_winner` keyed by sweep) và chỉ credit **một** claim là con đầu tiên của owner, nên
duplicate/multi-family/metadata không làm tăng, và hai sweep độc lập cho tổng `2` ⇒ không có cap toàn danh
sách. Giá trị bảo vệ: node đỏ nếu ai cap contribution theo **danh sách** về 1, bỏ dedupe theo child, hoặc để
`family`/metadata ảnh hưởng kết quả.

**Ghi chú sự cố nhỏ (đã khắc phục ngay):** khi chèn node tôi gõ nhầm một hàm placeholder
(`test_r72_03_histo_placeholder_anchor_marker`) — đã thay bằng node thật trong cùng lượt, kiểm chứng
`grep -c` = 0 và `ast.parse` + `--collect-only` (113 node) trước khi chạy.

**Hash mới file acceptance:** `73F027D724F16FED221273CA8748D1025BAEE6B4BF16C71D3A4CD15A3AEDBF75`
(§A3.76 ghi `47E92C98…`; các hash trước giữ nguyên làm lịch sử).

### A3.78 — Audit child non-owner có ID nhỏ hơn (A3-075)

**Reuse (không tạo node trùng):** `test_r72_03_acceptance_contribution_is_selected_within_owner_children` —
fixture `claim("early", "z-owner", 13)` + `claim("late", "a-nonowner", 15)`; non-owner mang zone ID **nhỏ hơn**
(`"a-nonowner" < "z-owner"`). Lượt này **chỉ bổ sung** đúng hai vế của hàng A3-075 vào node đó: precondition
`"a-nonowner" < "z-owner"`, `non_owner_claim["contribution_applied"] is False`, `owner_claim[...] is True`;
các assert cũ giữ nguyên.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_03_acceptance_contribution_is_selected_within_owner_children" -q --tb=short
1 failed in 0.64s
  E   assert False is True      # dòng 515 — owner_claim["contribution_applied"] is True

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_03" --tb=no
2 failed, 2 passed, 109 deselected in 0.16s

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
113 tests collected in 0.14s                     (không thêm node)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
64 failed, 49 passed in 0.40s                    (không đổi — node đã RED từ trước)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.28s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
64 failed, 903 passed in 12.20s                  (64 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe read-only cùng fixture):**

```text
assignment: owner_setup_id "early", contribution_applied True (trên record assignment)
claim early / z-owner     contribution_applied False
claim late  / a-nonowner  contribution_applied False
tổng contribution: 0
```

**Phân loại RED — `implementation` (F09), test đúng:**

- **PASS trước điểm dừng:** `owner_setup_id == "early"` (claim sớm nhất được owner ✓) và
  `non_owner_claim["contribution_applied"] is False` ⇒ **non-owner có ID nhỏ KHÔNG được credit**.
- **RED:** `owner_claim["contribution_applied"] is True` — con của **owner** cũng không được credit; probe cho
  thấy tổng `0` dù assignment ghi `contribution_applied True`. Nguyên nhân: khoá chọn slot
  (`contribution_winner`) tính trên **toàn bộ** children theo `(zone_id, visit_id, order)`, nên child non-owner
  có zone ID nhỏ hơn **chiếm khoá**, rồi cả hai vế điều kiện (`setup_id == owner` và khớp khoá) đều không đúng
  với bất kỳ claim nào ⇒ mất contribution của owner. Đúng ô "non-owner ID nhỏ hơn" của F09.
- **Ghi nhận:** node đã RED từ trước lượt này (điểm dừng cũ ở assert `tổng == 1`); lượt A3-075 chỉ làm rõ
  nguyên nhân bằng hai vế tường minh + precondition ID nhỏ hơn, **không** đổi số RED và không tạo node trùng.

**Hash mới file acceptance:** `0FE5D324DD0A302C92868FCDF8EE81980A98B83A425B8E2D280AFEF9B068E1C9`
(§A3.77 ghi `73F027D7…`; các hash trước giữ nguyên làm lịch sử).

### A3.79 — Audit owner chỉ còn trong history (A3-076)

**Reuse + bổ sung tối thiểu (không tạo node trùng):**

- Node `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` (history-only, `claims=[]`)
  được thêm **một** assert: `restored["assignments"]["sweep"] == first["assignments"]["sweep"]` — giữ owner
  **và** `assignment_id`/`claim_eligible_at`/`assigned_at`; đồng thời đưa `restored["claims"] == []`
  (current contribution 0) lên trước làm precondition.
- Node `test_r72_04_assignment_survives_json_restore_with_late_only_window` (GREEN) đã phủ vế **"không chuyển
  cho late child"**: sau JSON restore, cửa sổ hiện tại chỉ có `later/late-child` 15:00 ⇒ owner vẫn
  `"original"`, claim late `contribution_applied False` và vẫn project owner `"original"`. **Không viết lại.**

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_03_historical_owner_without_current_child_gets_zero_contribution" \
                 "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_assignment_survives_json_restore_with_late_only_window" -q --tb=short
1 failed, 1 passed, 111 deselected in 0.62s
  E   KeyError: 'sweep'      # dòng 1613 — restored["assignments"] không có 'sweep'

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_03" --tb=no
2 failed, 2 passed, 109 deselected in 0.16s

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
113 tests collected in 0.14s                     (không thêm node)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
64 failed, 49 passed in 0.41s                    (không đổi — node đã RED từ trước)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.27s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
64 failed, 903 passed in 12.19s                  (64 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe read-only cùng fixture):**

```text
lần 1  assignments["sweep"] = {sweep_id "sweep", owner_setup_id "owner",
                               assignment_id "smca-371aca1fa03ccf132f88",
                               claim_eligible_at/assigned_at "…T13:00", contribution_applied True}
lần 2  (claims=[]) → assignments = {}   claims = []      # assignment history-only BỊ MẤT
late-window (reuse) → owner "owner"; claim late contribution_applied False; claim owner "owner"
```

**Phân loại RED — `implementation` (F10), test đúng:** precondition `restored["claims"] == []` **PASS** (đúng:
cửa sổ hiện tại không có con nào để cộng contribution) và vế late-child **PASS** ở node reused; RED **chỉ ở**
assert assignment: `restored["assignments"] == {}` ⇒ owner/assignment của history-only không được giữ. Đúng ô
"owner absent" của F10 (helper chỉ xử lý các sweep **có claim hiện tại**, nên sweep chỉ-còn-history bị bỏ).
Node đã RED từ trước lượt này; A3-075/A3-076 chỉ làm rõ vế và không đổi số RED.

**Hash mới file acceptance:** `87030B68B3BD9628CFAA0BE90E1D2B6F843D2B4FF5C41284E35446C1ACD37296`
(§A3.78 ghi `0FE5D324…`; các hash trước giữ nguyên làm lịch sử).

### A3.80 — Audit coverage thiếu vs mâu thuẫn history (A3-077)

**Hai nhóm, hai node (reuse, không viết lại):**

| Nhóm | Node | Hành vi hiện tại |
|---|---|---|
| **Thiếu coverage** | `test_r72_04_incomplete_history_returns_explicit_reason` (`history_complete=False`, không history) | `assignments == {}`, `claims == []`, `reason_codes == ["SWEEP_OWNER_HISTORY_INCOMPLETE"]` ⇒ fail closed kèm **reason riêng** — **GREEN** |
| **Mâu thuẫn history** | `test_r72_04_conflicting_assignment_history_fails_closed` (history `{"sweep": {owner_setup_id "original"}}` thiếu `assignment_id`/timestamps, `history_complete=True`) | `assignments == {"sweep": {owner_setup_id "late", assignment_id mới, contribution_applied True}}`, `reason_codes == []` ⇒ **cấp lại owner mới** cho setup hiện tại — **RED** |

**Bổ sung tối thiểu (1 assert) vào nhóm mâu thuẫn** để thể hiện "reason đúng từng nhóm":
`assert "SWEEP_OWNER_HISTORY_INCOMPLETE" not in result["reason_codes"]` — fixture khai history **đầy đủ** và có
record, nên báo nhóm-thiếu sẽ là **nhầm nhóm**; assert này PASS hôm nay (reason rỗng) và vẫn đúng sau fix nếu
nhóm (b) có reason riêng.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_conflicting_assignment_history_fails_closed" \
                 "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_incomplete_history_returns_explicit_reason" -q --tb=short
1 failed, 1 passed, 111 deselected in 0.63s
  E   assert {'sweep': {'owner_setup_id': 'late', ...}} == {}      # dòng 1758

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
113 tests collected in 0.14s                     (không thêm node)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
64 failed, 49 passed in 0.40s                    (không đổi)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.26s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
64 failed, 903 passed in 10.76s                  (64 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe read-only, cùng fixture):**

```text
mâu thuẫn history → assignments {'sweep': {owner 'late', assignment_id 'smca-30bb697d628ee9c39480',
                            claim_eligible_at/assigned_at '…T15:00', contribution_applied True}}
                    reason_codes []            claims [('late', owner 'late', contribution True)]
thiếu coverage    → assignments {}             reason_codes ['SWEEP_OWNER_HISTORY_INCOMPLETE']   claims []
```

**Phân loại:** nhóm (a) **GREEN**; nhóm (b) **RED — implementation (F10)**: precondition (claim đầy đủ
canonical, không thiếu field) và assert phân nhóm đều PASS, nhưng helper **không** fail closed — nó cấp lại
owner cho setup hiện tại với assignment ID mới và không trả reason, tức "reset history rồi cấp owner mới" đúng
như hàng A3-077 cấm. Node (b) đã RED từ trước lượt này; A3-077 chỉ thêm vế phân nhóm nên không đổi số RED.

**Hash mới file acceptance:** `98C9D4498AA5890B1FBECA48EB591E5A1D2DFCC38066355C1F905589E3D7925D`
(§A3.79 ghi `87030B68…`; các hash trước giữ nguyên làm lịch sử).

### A3.81 — Audit first run → JSON restore → repeat trên context (A3-078)

**Ca in-RAM đã có (không viết lại):** `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay`
(A3-004) — attach lần 2 trên **cùng dict** sweeps trong RAM; RED (owner đổi thành `later-owner`).
**Ca JSON restore của hàng A3-078 là node mới** dưới đây, khác ở chỗ payload được serialize/deserialize
trước lượt 2.

**Fixture:** `sweeps = _probe.sweep()`; lượt 1 attach `zone("old-child", "original-owner", 13, 100, 110)`;
`restored = json.loads(json.dumps(sweeps))`; lượt 2 attach `zone("new-child", "later-owner", 15, 100, 110)`
trên `restored`.

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_04_context_repeat_after_json_restore_keeps_assignment" -q --tb=short
1 failed in 0.66s
  E   assert 'later-owner' == 'original-owner'      # dòng 1655 — assert contract ĐẦU TIÊN

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_04" --tb=no
4 failed, 2 passed, 108 deselected in 0.16s       (R72-04: RED 4 → 5)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
114 tests collected in 0.14s                      (113 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
65 failed, 49 passed in 0.49s                     (failed 64 → 65, passed giữ 49)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                               (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.41s                               (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
65 failed, 903 passed in 9.80s                    (65 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe read-only cùng fixture):**

```text
lượt 1  owner "original-owner"  assignment_id "smca-81d0ce9b964b17bb3702"  consumed True  linked_zone_id "old-child"
json    payload có keys ['swept_highs','swept_lows'] — restore giữ nguyên owner/assignment/consumed
lượt 2  owner "later-owner"  assignment_id "smca-eb0c85c44b303a18195c"  consumed True  linked_zone_id "new-child"
        claim_eligible_at 15:00      ⇒ owner + assignment của lượt 1 bị THAY
```

**Phân loại RED — `implementation` (F10), test đúng:**

- **PASS trước contract:** lượt 1 ghi owner/assignment/`consumed True`; JSON restore tạo **bản độc lập**
  (`restored is not sweeps`) và bảo toàn owner/assignment/consumed **trước** lượt 2 ⇒ chứng minh ca này kiểm
  đúng đường serialize→restore chứ không phải cùng dict trong RAM.
- **RED tại contract:** lượt 2 (setup muộn hơn) **lấy lại** owner và sinh `assignment_id` mới ⇒ caller không
  tôn trọng assignment đã ghi sau restore; hai assert sau (`linked_zone_id`, `claim_eligible_at`) cùng nguyên
  nhân.
- **Đối chiếu phạm vi:** A3-004 kiểm in-RAM (cùng dict), A3-078 kiểm sau JSON restore — hai ca khác nhau,
  cùng một gap F10 ở caller.

**Hash mới file acceptance:** `DA350504FA4F9568696C2F8C98CC61ADECD3A859A033D408CA50B7B048E0AE41`
(§A3.80 ghi `98C9D449…`; các hash trước giữ nguyên làm lịch sử).

### A3.82 — Audit fill và invariant R56 (A3-079)

**Reuse (không viết lại):** `tests/test_smc_fvg_fill_task62.py` phủ partial bullish/bearish, full fill (kể cả
trong tolerance), `original_bounds`/`zone_id` giữ, tích hợp `enrich_zones` không thay bounds zone, và typed
round-trip zero-width; `tests/test_smc_r56_01_session_acceptance.py` giữ invariant R56. Chạy chung:

```text
python -m pytest tests/test_smc_fvg_fill_task62.py tests/test_smc_r56_01_session_acceptance.py -q
121 passed in 0.36s
```

**Vế còn thiếu — "full fill không tự là break":** chưa node nào assert điều này (task62 chỉ assert
`fill_status`/`remaining_bounds`/identity). Node mới `test_r72_09_full_fvg_fill_is_not_a_break` dùng **đúng rows
task62** (không tạo fixture mới):

```text
rows = [(100,101,99,100), (100,102,99,101), (102,112,102,110), (110,111,99,100)]   # H1, gap @bar2 quét @bar3
zone: low 100 / high 110, origin_index 2 / formation_end_index 2, lifecycle_status "confirmed", broken False
```

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_full_fvg_fill_is_not_a_break" -q --tb=short
1 passed, 114 deselected in 0.50s

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
115 tests collected in 0.14s                     (114 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
65 failed, 50 passed in 0.40s                    (passed 49 → 50, failed giữ 65)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.25s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
65 failed, 904 passed in 9.29s                   (65 failed đều thuộc file acceptance)
```

**Phân loại:** **GREEN 1/1** — audit xác nhận fill **đã đúng**: `update_fvg_fill` chỉ set
`remaining_bounds`/`fill_ratio`/`fill_status` và **không** đụng `broken`/`lifecycle_status`, nên full fill là
**trạng thái riêng**, không tự thành invalidation; identity (`zone_id`/`setup_id`) và `original_bounds`/`low`/
`high` giữ nguyên. Giá trị bảo vệ: node đỏ nếu sau này ai cho fill đánh dấu `broken`/`invalid` hoặc ghi đè
bounds gốc. Golden R56 **không** bị sửa (chỉ chạy).

**Hash mới file acceptance:** `19CE5468214032D53B7CC8BE8AA0AFCB1785BB9CD46E45F24F1BF878BE59B4A2`
(§A3.81 ghi `DA350504…`; các hash trước giữ nguyên làm lịch sử).

### A3.83 — Audit positive vs negative invalid-data (A3-080)

**Reuse (không viết lại):** `test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid` — năm
fixture fixes F01-T59/T60-BUY/T60-SELL/T62-BUY/T63-SELL, mỗi bộ rows nạp qua module rồi **re-validate** trong
file acceptance; chạy lại **PASS**.

**Vế negative (A3-023 từng ghi "chưa có fixture invalid-data cố ý"):** node mới
`test_r72_09_intentional_invalid_data_reports_its_own_reason` dựng đúng **ví dụ invalid của R72-09**:

```text
bar 4 = (112, 113, 111.2, 110.2)      # close 110.2 < low 111.2  → invalid có chủ đích
control bar 4 = (112, 113, 110.2, 110.2)   # đúng bản sửa F01-T60-BUY (low 111.2 → 110.2), close == low
4 nến đầu giống hệt nhau ở cả hai series
```

**Command/kết quả (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_intentional_invalid_data_reports_its_own_reason" -q --tb=short
1 passed, 115 deselected in 0.55s

python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid" -q --tb=line
1 passed, 115 deselected in 0.15s

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
116 tests collected in 0.14s                     (115 + 1)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
65 failed, 51 passed in 0.41s                    (passed 50 → 51, failed giữ 65)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi baseline đang ghi)

python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.28s                              (không hồi quy)

python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no
65 failed, 905 passed in 9.61s                   (65 failed đều thuộc file acceptance)
```

**Giá trị đọc thật (probe read-only):**

```text
invalid bar  → validate_smc_candles trả (SmcCandleValidationIssue(code='SMC_OHLC_INVALID', index=4, field='ohlc',
              detail='OHLC must be finite and satisfy high >= max(open, close), low <= min(open, close), high >= low'),)
control bar  → ()
```

**Phân loại:** **GREEN 1/1** — positive và negative tách nhau **bằng cùng một validator**: positives (năm fixture
fixes) qua validator sạch; invalid-data cố ý mang **reason riêng** `SMC_OHLC_INVALID` kèm đúng bar vi phạm
(`index 4`) và control chứng minh reason do **dữ liệu**, không do họ fixture. Giá trị bảo vệ: node đỏ nếu
validator ngừng bắt OHLC sai, hoặc nếu ai "sửa" negative thành positive cho test xanh. Golden R56 không bị sửa.

**Ghi chú phạm vi:** audit **không** thêm yêu cầu rằng detector/consumer phải raise khi nhận nến invalid —
probe cho thấy `detect_order_block_candidates` vẫn trả 1 candidate vì ATR prefix của nó (các nến trước) hợp lệ;
hàng A3-080 chỉ đòi "invalid-data intentional kiểm reason riêng", và điều đó được kiểm ở **validator** — không
tự nâng thành quy tắc mới.

**Hash mới file acceptance:** `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD`
(§A3.82 ghi `19CE5468…`; các hash trước giữ nguyên làm lịch sử).

### A3.84 — Hoàn thiện mapping case-level (A3-081)

**Việc đã làm (docs-only, mục M):**

1. **Thay toàn bộ dạng gộp param bằng parameter ID thật** (lấy từ `--collect-only`): **35** lần xuất hiện `[buy/sell]`
   cùng các dạng gộp khác — `[20/21/22-buy/sell]`, `[20-buy/sell]`, `[21/22-buy/sell]`, `[20-*]`,
   `[expired\|invalid-buy/sell]`, `[20\|21\|22-buy/sell]`, `[False/True]`, `[atr_current\|tick_size]`,
   `[reclaimed_at\|setup_available_at]`, `[expired_by_age\|already_invalid]`, `[record_for_other_level\|…]`,
   `[below\|equal\|beyond × buy\|sell]`.
2. **Mở rộng hai tên bị cắt** trong bảng factory A3-023 (`test_r72_05_acceptance_terminal_d1…`,
   `test_r72_05_serialized_terminal_mapping…`) và viết lại danh sách call-site hàng 1 (shorthand cũ
   `positive_pool_keeps_source_lineage`, `canonical_sweep_requires_pool_records`, `provisional_source…`,
   `equal_usable_at_reclaimed`) thành ID đầy đủ.
3. **Quy ước ghi node (A3-081)** thêm ở đầu mục mapping §A3-063: ô nêu node chạy được phải kèm param thật; tên
   không ngoặc vuông = **tên họ node** (param thật ở bảng theo dõi R72-0X); tên lịch sử/đổi tên/probe ghi chú tại ô.
4. **Ghi chú 3 tên không chạy được còn lại:** `test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero`
   (tên lịch sử, đã tách tại A3-016/A3-017), `test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture`
   (đổi tên tại A3-056), `test_r72_09_existing_task60_positive_fixture_must_have_valid_ohlc` (reviewer probe).
5. **Sửa dòng trạng thái đầu plan** còn ghi `A3-001…A3-055` (mâu thuẫn §8.1) ⇒ `A3-001…A3-081`.

**Command/kết quả (thật):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q     # 116 node
<script đối chiếu mention test_r72_…[...] trong M với collection>            # 0 mention ngoặc không tồn tại
grep -c "\[buy/sell\]" docs/plans/smc-task-72-acceptance-matrix.md           # 0
grep -cF "||" docs/plans/smc-task-72-acceptance-matrix.md                      # 0
sha256sum tests/test_smc_gate72_fix_acceptance.py                              # E84A3093… (không đổi)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no            # 65 failed, 51 passed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no        # 13 failed, 3 passed
python -m pytest <15 file task57..71> -q --tb=no                               # 108 passed
python -m pytest <tests/test_smc*.py + 6 file integration> -q --tb=no          # 65 failed, 905 passed
```

**Phân loại:** bước **hoàn thiện hồ sơ mapping**, không sinh RED/GREEN test; kết luận 21 ô §4 của A3-063 **không
đổi** (ca thiếu vẫn ghi thiếu). Giá trị bảo vệ: từ nay mọi ô nêu node đều là ID chạy được, hoặc được đánh dấu họ
node/lịch sử/probe — A3-082 và A3-084 có thể đối chiếu máy móc.

**Hash file acceptance:** giữ `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD` (không đổi).

### A3.85 — Collect bản cuối và so inventory A3-002 (A3-082)

**Command/kết quả (thật):**

```text
python -m pytest -q --collect-only tests/test_smc_gate72_fix_acceptance.py
116 tests collected in 0.14s            # 74 hàm test (74 `def test_`), 116 node

$retainedSmcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
65 failed, 51 passed in 0.41s
```

**Đối chiếu inventory A3-002 (49 node) → bản cuối (116 node):**

| Nhóm | Số lượng | Ghi chú |
|---|---|---|
| Có mặt ở cả hai | **46** | giữ nguyên ID (một số nay có thêm param, ví dụ `[20-buy]`…`[22-sell]`) |
| Đổi tên | **1** | `test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture` → `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke` (**A3-056**; cùng hành vi, thu hẹp tên/phạm vi) |
| Tách node | **1** | `test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero` → `…missing_canonical_atr…`, `…missing_canonical_tick…`, `…nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]`, `[tick_size]` (**A3-016/A3-017**) |
| Thêm param | **1** | `test_r72_02_missing_canonical_claim_time_fails_closed` → `[reclaimed_at]`, `[setup_available_at]` (**A3-013/A3-014**) |
| Node mới | **68** (45 họ) | thêm bởi A3-010…A3-081 theo từng finding (bảng dưới) |

**Node mới theo finding (số node / số họ hàm):**

| Finding | Node cuối | Họ hàm | Node mới thêm trong F01 |
|---|---|---|---|
| R72-01 pool/source-time | 27 | 14 | 21 node mới (canonical `records`, provenance thiếu riêng, temporal gate, threshold strict, prefix/batch…) |
| R72-02 owner | 9 | 8 | 6 node mới (context permutation, tie, sai chiều, khoảng cách, cửa sổ thời gian) |
| R72-03 contribution | 4 | 4 | 1 node mới (per-sweep, không cap danh sách) |
| R72-04 consumed | 6 | 6 | 1 node mới (JSON restore → repeat) |
| R72-05 terminal D1 | 8 | 4 | 2 node mới (cutoff = expired/invalidated) |
| R72-06 terminal/reaction | 20 | 7 | 11 node mới (H4 timeline, thứ tự terminal, enrich↔restore) |
| R72-07 metadata | 19 | 14 | 9 node mới (missing/nonfinite/parity/unknown-terminal/formation ATR/override) |
| R72-08 typed projection | 13 | 7 | 5 node mới (typed D1 positive/invalid/expired) |
| R72-09 fixture + chuỗi thật | 10 | 10 | 8 node mới (confirmed D1 source, retest, typed restore, D1 positive/invalid/expired, fill, invalid-data) |

**Kết luận:** **không mất coverage cũ** — 46 ID giữ nguyên, 3 mục còn lại đều có node thay thế tương ứng và mở
rộng (tách/param/đổi tên), 68 node mới đều thuộc các mã A3 đã IMPLEMENTED. Collection **0 lỗi**, không warning
import; 116 node / 74 hàm test.

**Hash file acceptance:** giữ `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD` (không đổi —
A3-082 chỉ chạy và ghi kết quả).

### A3.86 — Targeted cho factory/test vừa chỉnh và consumer (A3-083)

**Command/kết quả (thật):**

```text
# (1) năm file fixture đã sửa ở F01
python -m pytest tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py                  tests/test_smc_fvg_fill_task62.py tests/test_smc_zone_lifecycle_task63.py                  tests/test_smc_lifecycle_task65.py -q --tb=short
32 passed in 0.46s

# (2) consumer: quét import ⇒ chỉ file acceptance dùng các factory đó (qua _load_module)
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
116 tests collected in 0.14s          # grep -ci "error" ⇒ 0
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
65 failed, 51 passed in 0.41s

# (3) nhóm task57–71 và probe reviewer
python -m pytest <15 file task57..71> -q --tb=no
108 passed in 1.25s
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed
```

**Phân loại 65 RED theo finding (đếm máy móc từ `-v --tb=no | grep FAILED`):**

| Finding | RED | Chủ sở hữu implementation |
|---|---|---|
| R72-01 pool/source-time | 15 | F06/F07 (canonical `records`, provenance, temporal gate, threshold) |
| R72-02 owner | 5 | F08 (claim time/tie/eligibility ở caller) |
| R72-03 contribution | 2 | F09 (chọn con trong owner; history-only) |
| R72-04 consumed | 4 | F10 (assignment/history qua replay + JSON restore) |
| R72-05 terminal D1 | 6 | F05 (A-D04 cutoff = terminal) |
| R72-06 terminal/reaction | 12 | F04/F05 (thứ tự terminal, expiry biên) |
| R72-07 metadata | 12 | F02/F03 (`metadata_state`/`usable`, non-finite) |
| R72-08 typed projection | 8 | F03/F05 (canonical invalid/expired thắng legacy) |
| R72-09 chuỗi D1 | 1 | F03/F05 (terminal invalidation) |

**Đối chiếu "cần sửa trước bàn giao":**

- **0 lỗi collection** trên toàn bộ file acceptance (116 node collect được).
- **0 fixture defect**: năm factory đã sửa chạy sạch (32 passed) và fixture acceptance tự validate
  (`validate_smc_candles` trong mọi factory, xem §A3.23/§A3.77…§A3.83).
- **0 test defect**: mọi RED là `AssertionError` **trừ hai dạng có chủ đích**:
  1. `KeyError` trên field canonical **đã duyệt nhưng core chưa có** — `metadata_state`, `metadata_reason`,
     `usable` (M §Interface metadata; R72-08). Đây là "thiếu interface tương lai" theo §8.1, và chính tên field
     trong KeyError là mô tả thiếu interface; contract đã ghi ở M và ở ledger các mã A3-007/A3-015/A3-016/A3-017/A3-021.
  2. `ValueError: Invalid zone boundary: nan` phát từ `core/smc_lifecycle.py:674` khi metadata non-finite
     (`test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current|tick_size]`) — đúng gap đã ghi
     ở A3-017 (core phải biểu diễn unknown/unusable thay vì ném).
- Không có test nào chết vì import/interface sai; không skip/xfail.

**Kết luận:** không có defect fixture/collection/test cần sửa trước bàn giao; toàn bộ 65 RED là
implementation gap có expected rõ, thuộc F02…F10 (ngoài phạm vi F01/checkpoint A).

**Hash file acceptance:** giữ `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD` (không đổi —
A3-083 chỉ chạy và ghi kết quả).

### A3.87 — Full acceptance và phân loại từng failure (A3-084)

**Command/kết quả (thật):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
65 failed, 51 passed in 0.44s
python -m pytest tests/test_smc_gate72_fix_acceptance.py -v --tb=no -rf -q
# 65 dòng FAILED (đếm theo finding: R72-01 15, 02 5, 03 2, 04 4, 05 6, 06 12, 07 12, 08 8, 09 1)
python -m pytest tests/test_smc_gate72_fix_acceptance.py --tb=line -q
# 63 frame trỏ vào file acceptance + 2 frame trỏ `core/smc_lifecycle.py:674` (ValueError nan) = 65
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
116 tests collected (0 lỗi collection)
```

**Phân loại từng failure (65 RED — mỗi dòng: node, expected, actual đọc từ output, gap):**

| # | Node (RED) | Expected (ngắn) | Actual (từ output) | Gap / test-defect |
|---|---|---|---|---|
| 1 | `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[buy]` | swept_* == [] (source chưa usable tại close sweep) | `AssertionError: assert not [{'depth': 0.5, 'depth_atr': 0.5, 'excursion_buffer': 0.2, 'index': 2, ...}]` | **F06/F07** — precondition PASS (§A3.22/§A3.42) |
| 2 | `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[sell]` | swept_* == [] (source chưa usable tại close sweep) | `AssertionError: assert not [{'depth': 0.5, 'depth_atr': 0.5, 'excursion_buffer': 0.2, 'index': 2, ...}]` | **F06/F07** — precondition PASS (§A3.22/§A3.42) |
| 3 | `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[buy]` | swept_* == [] khi pool thiếu records | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` | **F06** — precondition PASS (§A3.10) |
| 4 | `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[sell]` | swept_* == [] khi pool thiếu records | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` | **F06** — precondition PASS (§A3.10) |
| 5 | `test_r72_01_equal_pool_usable_time_is_max_of_both_sources` | usable_at = max(2 source) | `AssertionError: assert [{'depth': 0....dex': 1, ...}] == []` | **F06** — precondition PASS (§A3.43) |
| 6 | `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` | sweep hợp lệ (usable_at == reclaimed_at, inclusive) | `assert 0 == 1` | **F06/F07** — precondition PASS (§A3.41) |
| 7 | `test_r72_01_missing_pool_provenance_fails_closed[dangling_source_id]` | swept_* == [] cho TỪNG khuyết điểm provenance | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` | **F06** — precondition PASS (§A3.67) |
| 8 | `test_r72_01_missing_pool_provenance_fails_closed[no_sources]` | swept_* == [] cho TỪNG khuyết điểm provenance | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` | **F06** — precondition PASS (§A3.67) |
| 9 | `test_r72_01_missing_pool_provenance_fails_closed[record_for_other_level]` | swept_* == [] cho TỪNG khuyết điểm provenance | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` | **F06** — precondition PASS (§A3.67) |
| 10 | `test_r72_01_missing_pool_provenance_fails_closed[source_without_provenance_id]` | swept_* == [] cho TỪNG khuyết điểm provenance | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` | **F06** — precondition PASS (§A3.67) |
| 11 | `test_r72_01_missing_pool_provenance_fails_closed[source_without_usable_at]` | swept_* == [] cho TỪNG khuyết điểm provenance | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` | **F06** — precondition PASS (§A3.67) |
| 12 | `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy]` | records giữ pool_id/source_ids/usable_at | `assert 0 == 1` | **F06** — precondition PASS (§A3.9) |
| 13 | `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[sell]` | records giữ pool_id/source_ids/usable_at | `assert 0 == 1` | **F06** — precondition PASS (§A3.9) |
| 14 | `test_r72_01_source_usable_after_sweep_close_is_rejected[buy]` | swept_* == [] (source usable sau close) | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` | **F06/F07** — precondition PASS (§A3.42) |
| 15 | `test_r72_01_source_usable_after_sweep_close_is_rejected[sell]` | swept_* == [] (source usable sau close) | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` | **F06/F07** — precondition PASS (§A3.42) |
| 16 | `test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time` | owner "early" (claim time) | `AssertionError: assert 'late' == 'early'` | **F08** — precondition PASS (§A3.69) |
| 17 | `test_r72_02_context_owner_follows_claim_time_under_input_permutation` | owner "early" + linked_zone_id/claim_eligible_at theo claim sớm | `AssertionError: assert 'late' == 'early'` | **F08** — precondition PASS (§A3.72) |
| 18 | `test_r72_02_context_same_time_tie_follows_stable_setup_id` | owner "alpha-setup" (setup ID ổn định) | `AssertionError: assert 'beta-setup' == 'alpha-setup'` | **F08** — precondition PASS (§A3.76) |
| 19 | `test_r72_02_missing_canonical_claim_time_fails_closed[reclaimed_at]` | assignments == {} + reason thiếu claim time | `AssertionError: assert {'sweep': {'a...': True, ...}} == {}` | **F08/A-D02** — precondition PASS (§A3.13/§A3.14) |
| 20 | `test_r72_02_missing_canonical_claim_time_fails_closed[setup_available_at]` | assignments == {} + reason thiếu claim time | `AssertionError: assert {'sweep': {'a...': True, ...}} == {}` | **F08/A-D02** — precondition PASS (§A3.13/§A3.14) |
| 21 | `test_r72_03_acceptance_contribution_is_selected_within_owner_children` | con của owner được credit, tổng 1, non-owner 0 | `assert False is True` | **F09** — precondition PASS (§A3.78) |
| 22 | `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | assignment history-only giữ nguyên | `KeyError: 'sweep'` | **F10** — precondition PASS (§A3.79) |
| 23 | `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` | owner/assignment giữ qua replay trên context | `AssertionError: assert 'later-owner' == 'original-owner'` | **F10** — precondition PASS (§A3.4) |
| 24 | `test_r72_04_conflicting_assignment_history_fails_closed` | fail closed + reason riêng nhóm mâu thuẫn | `AssertionError: assert {'sweep': {'a...': True, ...}} == {}` | **F10** — precondition PASS (§A3.80) |
| 25 | `test_r72_04_context_repeat_after_json_restore_keeps_assignment` | owner/assignment giữ sau JSON restore + repeat | `AssertionError: assert 'later-owner' == 'original-owner'` | **F10** — precondition PASS (§A3.81) |
| 26 | `test_r72_04_same_pool_observation_cannot_bypass_consumption` | owner gốc + không cộng thêm contribution | `AssertionError: assert 'later' == 'original'` | **F10/A-D06** — precondition PASS (§A3.46) |
| 27 | `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[buy]` | D1 valid False/score 0 tại terminal | `assert True is False` | **F05/A-D04** — precondition PASS (§A3.49) |
| 28 | `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[sell]` | D1 valid False/score 0 tại terminal | `assert True is False` | **F05/A-D04** — precondition PASS (§A3.49) |
| 29 | `test_r72_05_cutoff_equal_invalidated_at_is_terminal[buy]` | cutoff == invalidated_at ⇒ terminal | `assert True is False` | **F05/A-D04** — precondition PASS (§A3.50) |
| 30 | `test_r72_05_cutoff_equal_invalidated_at_is_terminal[sell]` | cutoff == invalidated_at ⇒ terminal | `assert True is False` | **F05/A-D04** — precondition PASS (§A3.50) |
| 31 | `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[buy]` | canonical invalid thắng legacy flag | `assert True is False` | **F03/F05** — precondition PASS (§A3.50) |
| 32 | `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[sell]` | canonical invalid thắng legacy flag | `assert True is False` | **F03/F05** — precondition PASS (§A3.50) |
| 33 | `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[buy]` | reaction không vượt expiry | `AssertionError: assert '2026-09-23T00:00:00+00:00' is None` | **F04** — precondition PASS (§A3.29) |
| 34 | `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[sell]` | reaction không vượt expiry | `AssertionError: assert '2026-09-23T00:00:00+00:00' is None` | **F04** — precondition PASS (§A3.29) |
| 35 | `test_r72_06_h4_reaction_after_terminal_is_blocked[buy]` | reaction sau terminal bị chặn | `AssertionError: assert '2026-09-06T12:00:00+00:00' is None` | **F04** — precondition PASS (§A3.36) |
| 36 | `test_r72_06_h4_reaction_after_terminal_is_blocked[sell]` | reaction sau terminal bị chặn | `AssertionError: assert '2026-09-06T12:00:00+00:00' is None` | **F04** — precondition PASS (§A3.36) |
| 37 | `test_r72_06_h4_reaction_at_terminal_is_blocked[buy]` | reaction tại terminal bị chặn | `AssertionError: assert '2026-09-06T08:00:00+00:00' is None` | **F04** — precondition PASS (§A3.35) |
| 38 | `test_r72_06_h4_reaction_at_terminal_is_blocked[sell]` | reaction tại terminal bị chặn | `AssertionError: assert '2026-09-06T08:00:00+00:00' is None` | **F04** — precondition PASS (§A3.35) |
| 39 | `test_r72_06_terminal_order_before_reaction_is_explicit[21-buy]` | thứ tự terminal quyết định reaction | `AssertionError: assert '2026-09-23T00:00:00+00:00' is None` | **F04** — precondition PASS (§A3.32) |
| 40 | `test_r72_06_terminal_order_before_reaction_is_explicit[21-sell]` | thứ tự terminal quyết định reaction | `AssertionError: assert '2026-09-23T00:00:00+00:00' is None` | **F04** — precondition PASS (§A3.32) |
| 41 | `test_r72_06_terminal_order_before_reaction_is_explicit[22-buy]` | thứ tự terminal quyết định reaction | `AssertionError: assert '2026-09-24T00:00:00+00:00' is None` | **F04** — precondition PASS (§A3.32) |
| 42 | `test_r72_06_terminal_order_before_reaction_is_explicit[22-sell]` | thứ tự terminal quyết định reaction | `AssertionError: assert '2026-09-24T00:00:00+00:00' is None` | **F04** — precondition PASS (§A3.32) |
| 43 | `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-buy]` | terminal giữ qua enrich↔restore | `AssertionError: assert 'confirmed' == 'invalid'` | **F03** — precondition PASS (§A3.38) |
| 44 | `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-sell]` | terminal giữ qua enrich↔restore | `AssertionError: assert 'confirmed' == 'invalid'` | **F03** — precondition PASS (§A3.38) |
| 45 | `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[buy]` | invalidation_buffer == 0.1 khi tick truyền từ đối số | `assert 0.0 == 0.1 ± 1.0e-07` | **F02** — precondition PASS (§A3.11) |
| 46 | `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[sell]` | invalidation_buffer == 0.1 khi tick truyền từ đối số | `assert 0.0 == 0.1 ± 1.0e-07` | **F02** — precondition PASS (§A3.11) |
| 47 | `test_r72_07_conflicting_same_scope_tick_sources_fail_closed` | tick mâu thuẫn cùng scope ⇒ fail closed | `KeyError: 'metadata_state'` | **F02** — precondition PASS (§A3.18) |
| 48 | `test_r72_07_item_and_argument_tick_sources_have_parity[buy]` | buffer 0.1 ở cả 3 biến thể nguồn tick | `AssertionError: argument_only` | **F02/A-D07** — precondition PASS (§A3.19) |
| 49 | `test_r72_07_item_and_argument_tick_sources_have_parity[sell]` | buffer 0.1 ở cả 3 biến thể nguồn tick | `AssertionError: argument_only` | **F02/A-D07** — precondition PASS (§A3.19) |
| 50 | `test_r72_07_metadata_survives_context_to_typed_round_trip` | metadata_state unknown sống qua context→typed→JSON | `KeyError: 'metadata_state'` | **F02/F03** — precondition PASS (§A3.21) |
| 51 | `test_r72_07_missing_canonical_atr_is_unknown_and_unusable` | metadata_state unknown + usable False | `KeyError: 'metadata_state'` | **F02/F03** — precondition PASS (§A3.15) |
| 52 | `test_r72_07_missing_canonical_tick_is_unknown_and_unusable` | metadata_state unknown + usable False | `KeyError: 'metadata_state'` | **F02/F03** — precondition PASS (§A3.16) |
| 53 | `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]` | nonfinite ⇒ unknown/unusable (không ném) | `ValueError: Invalid zone boundary: nan` | **F02/F03** — precondition PASS (§A3.17) |
| 54 | `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[tick_size]` | nonfinite ⇒ unknown/unusable (không ném) | `ValueError: Invalid zone boundary: nan` | **F02/F03** — precondition PASS (§A3.17) |
| 55 | `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[already_invalid]` | unknown metadata không hồi sinh vùng terminal | `KeyError: 'metadata_state'` | **F02/F03** — precondition PASS (§A3.20) |
| 56 | `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[expired_by_age]` | unknown metadata không hồi sinh vùng terminal | `KeyError: 'metadata_state'` | **F02/F03** — precondition PASS (§A3.20) |
| 57 | `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[buy]` | invalidated ⇒ invalid + usable False | `assert True is False` | **F03** — precondition PASS (§A3.24) |
| 58 | `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[sell]` | invalidated ⇒ invalid + usable False | `assert True is False` | **F03** — precondition PASS (§A3.24) |
| 59 | `test_r72_08_canonical_invalid_status_wins_legacy_boolean[False]` | canonical invalid thắng legacy boolean | `AssertionError: assert False is True` | **F03** — precondition PASS (§A3.54) |
| 60 | `test_r72_08_invalid_canonical_zone_survives_typed_round_trip_consistently` | invalid/broken/usable giữ qua round-trip typed | `KeyError: 'usable'` | **F03** — precondition PASS (§A3.24/§A3.53) |
| 61 | `test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[buy]` | typed invalid thắng legacy ⇒ D1 invalid/0 | `assert True is False` | **F05/F03** — precondition PASS (§A3.57) |
| 62 | `test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[sell]` | typed invalid thắng legacy ⇒ D1 invalid/0 | `assert True is False` | **F05/F03** — precondition PASS (§A3.57) |
| 63 | `test_r72_08_typed_terminal_projection_reaches_d1_consumer[buy]` | typed terminal ⇒ D1 invalid/0 | `assert True is False` | **F05** — precondition PASS (§A3.52) |
| 64 | `test_r72_08_typed_terminal_projection_reaches_d1_consumer[sell]` | typed terminal ⇒ D1 invalid/0 | `assert True is False` | **F05** — precondition PASS (§A3.52) |
| 65 | `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` | terminal ⇒ invalid/unusable + D1 invalid/0 | `AssertionError: assert 'confirmed' == 'invalid'` | **F03/F05** — precondition PASS (§A3.64) |

**Kết luận phân loại:**

- **Không có test-defect / fixture-defect**: 0 lỗi collection; mọi dòng RED dừng ở **assert contract** (không phải
  assert precondition — precondition nằm trước và đã qua, xem §A3.NN của từng mã); 63/65 RED là `AssertionError`
  đọc thẳng actual; 2/65 là `ValueError: Invalid zone boundary: nan` phát từ `core/smc_lifecycle.py:674` — đúng gap
  đã ghi ở **A3-017** (core phải biểu diễn unknown/unusable thay vì ném khi metadata non-finite).
- **Toàn bộ 65 RED thuộc implementation gap F02…F10** (không mã nào nằm trong phạm vi F01/checkpoint A); một số RED
  có thêm dạng "thiếu interface canonical đã duyệt" (`metadata_state`/`metadata_reason`/`usable`) với tên field nằm
  ngay trong `KeyError`, contract ghi ở M §Interface metadata và R72-08.
- **GREEN (51 node) KHÔNG tự là finding CLOSED**: 51 node xanh chỉ nghĩa các contract đó đã đúng ở thời điểm A;
  việc đóng finding R72-01…09 thuộc **Tech Lead** sau checkpoint A lần3 (A3-090 mới ghép bản trình), Coder không tự chuyển.

**Hash file acceptance:** giữ `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD` (không đổi —
A3-084 chỉ chạy và ghi kết quả).

### A3.88 — Reviewer probes nguyên bản (A3-085)

**Command/kết quả (thật):**

```text
python -m pytest docs/plans/probes/test_smc_gate72_review.py -v --tb=no
13 failed, 3 passed in 0.10s          # 16 node
sha256sum docs/plans/probes/test_smc_gate72_review.py
5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6   # khớp F00 ⇒ probe KHÔNG bị sửa
```

**Pass/fail theo node (16):**

| Node | Kết quả | Cụm sửa dự kiến |
|---|---|---|
| `test_r72_01_sweep_must_not_precede_source_confirmation[buy]` | **FAILED** | F06/F07 |
| `test_r72_01_sweep_must_not_precede_source_confirmation[sell]` | **FAILED** | F06/F07 |
| `test_r72_02_context_must_consider_earliest_eligible_setup_before_distance_rank` | **FAILED** | F08 |
| `test_r72_03_nonowner_child_cannot_take_contribution_slot` | **FAILED** | F09 |
| `test_r72_04_context_must_not_reassign_already_consumed_sweep` | **FAILED** | F10 |
| `test_r72_05_broken_d1_lifecycle_cannot_supply_active_reaction[buy]` | **FAILED** | F05 |
| `test_r72_05_broken_d1_lifecycle_cannot_supply_active_reaction[sell]` | **FAILED** | F05 |
| `test_r72_06_expiry_candle_cannot_create_reaction_for_earlier_exit[buy]` | **FAILED** | F04 |
| `test_r72_06_expiry_candle_cannot_create_reaction_for_earlier_exit[sell]` | **FAILED** | F04 |
| `test_r72_07_enrich_must_forward_explicit_tick_to_lifecycle[buy]` | **FAILED** | F02 |
| `test_r72_07_enrich_must_forward_explicit_tick_to_lifecycle[sell]` | **FAILED** | F02 |
| `test_r72_08_invalidated_zone_must_not_keep_confirmed_usable_flags[buy]` | **FAILED** | F03 |
| `test_r72_08_invalidated_zone_must_not_keep_confirmed_usable_flags[sell]` | **FAILED** | F03 |
| `test_r72_09_existing_task60_positive_fixture_must_have_valid_ohlc` | **PASSED** | F01 (đã đạt) |
| `test_control_live_d1_reaction_still_accepted` | **PASSED** | control — phải giữ xanh |
| `test_control_owner_children_share_exactly_one_contribution` | **PASSED** | control — phải giữ xanh |

**Ghi nhận theo hàng A3-085:**

- **Probe nguyên bản, không sửa** — hash khớp F00 (`5B040D6A…`); lệnh trên là chạy read-only.
- **13 RED là trạng thái trước B/C, không phải việc của checkpoint A**: theo review §4, mỗi probe thuộc một cụm
  F02…F10 (bảng trên). Hàng A3-085 **không** buộc tất cả GREEN ở bước này — chỉ ghi actual; các probe phải xanh
  dần khi F02…F10 được sửa (checkpoint B/C), và **16/16** phải xanh trước checkpoint C.
- **3 PASSED gồm 2 control** (`test_control_live_d1_reaction_still_accepted`,
  `test_control_owner_children_share_exactly_one_contribution`) — đây là chốt "không được sửa quá tay": khi fix
  F05/F09 phải giữ hai control này xanh.
- Không có probe nào bị skip/xfail; không có lỗi collection.

**Hash probe:** giữ `5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6` (không đổi).
**Hash file acceptance:** giữ `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD` (không đổi).

### A3.89 — Nhóm task tests task57–71 theo §5 (A3-086)

**Command (đúng §5, enumerate bằng `rg`):**

```powershell
$gate72Tests = @(rg --files tests -g '*task5[7-9].py' -g '*task6[0-9].py' -g '*task7[01].py')
python -m pytest @gate72Tests -q --tb=short
# 108 passed in 1.26s

python -m pytest @gate72Tests --collect-only -q
# 108 tests collected in 1.18s
```

**File (15) và số node mỗi file (thật):**

| File | Node |
|---|---|
| `tests/test_smc_zone_visit_task57.py` | 11 |
| `tests/test_smc_zone_lifecycle_task58.py` | 6 |
| `tests/test_smc_zone_lifecycle_task59.py` | 5 |
| `tests/test_smc_zone_lifecycle_task60.py` | 8 |
| `tests/test_smc_zone_lifecycle_task61.py` | 8 |
| `tests/test_smc_fvg_fill_task62.py` | 7 |
| `tests/test_smc_zone_lifecycle_task63.py` | 5 |
| `tests/test_smc_zone_lifecycle_task64.py` | 6 |
| `tests/test_smc_lifecycle_task65.py` | 7 |
| `tests/test_smc_liquidity_pools_task66.py` | 6 |
| `tests/test_smc_liquidity_sweeps_task67.py` | 8 |
| `tests/test_smc_sweep_linking_task68.py` | 5 |
| `tests/test_smc_sweep_consumed_task69.py` | 8 |
| `tests/test_smc_confluence_task70.py` | 12 |
| `tests/test_smc_liquidity_context_task71.py` | 6 |
| **Tổng** | **108** |

**So baseline liên quan:**

| Mốc | File | Node | Kết quả |
|---|---|---|---|
| F00 baseline (§A3.5/§A3.7 ghi) | 15 | 108 | 108 passed (1.27s) |
| Reviewer (review gate72 §3) | 15 | 108 | 108 passed (1.26s) |
| **Lượt này (A3-086)** | **15** | **108** | **108 passed (1.26s)** |

**Ghi nhận:** `--collect-only` = **108** = số test chạy ⇒ **0 skip / 0 xfail / 0 lỗi collection**; số file và số node
**không đổi** so với baseline F00 và reviewer ⇒ F01 (sửa fixture + thêm acceptance) **không** làm mất hay thêm node
trong nhóm này (node mới của F01 nằm ở file acceptance riêng). Kết quả này là **chạy thật lượt này**, không chép
lại con số 108 từ tài liệu.

**Hash file acceptance:** giữ `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD` (không đổi).

### A3.90 — Retained baseline (loại acceptance mới) — A3-087

**Command (đúng §8.7):**

```powershell
$retainedSmcTests = @(rg --files tests -g 'test_smc*.py' | Where-Object { ($_ -replace '\','/') -ne 'tests/test_smc_gate72_fix_acceptance.py' })
python -m pytest @retainedSmcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q --tb=short
```

**Kết quả thật:**

```text
$retainedSmcTests  → 66 file
python -m pytest <66 file SMC + 6 file integration> -q --tb=short
854 passed in 8.96s
... --collect-only -q
854 tests collected in 5.52s
```

**Kiểm inventory (không dùng tổng count để che test mất):**

| Kiểm tra | Kết quả |
|---|---|
| `rg --files tests -g 'test_smc*.py'` | **67** file |
| trong đó file acceptance mới | **1** (`test_smc_gate72_fix_acceptance.py`) |
| retained SMC = 67 − 1 | **66** file — đúng bằng bộ `$retainedSmcTests` (không loại nhầm file nào khác) |
| file integration ngoài SMC | **6** (technical_signal_scorer, scanner_features, scanner_live_producers, analysis_pipeline_integration, scanner_scenario_producers, scanner_replay) |
| node collect được | **854** |
| test chạy/pass | **854 passed** ⇒ node = passed ⇒ **0 skip / 0 xfail / 0 lỗi collection** |
| baseline F00 đã ghi | 66 file / **854 passed** (9.08s) |
| lượt này (A3-087) | 66 file / **854 passed** (8.96s) |

**Ghi nhận:** số **file** và số **node/pass** đều **trùng khít** baseline F00 đã ghi ⇒ không có test nào bị mất,
không có test nào được thêm vào nhóm này, không có failure nào. Con số **854** ở đây dùng để **đối chiếu inventory**
(khớp ⇒ không mất test), **không** phải mục tiêu cần đạt; file acceptance mới (116 node, 65 RED) **không** nằm
trong nhóm retained này nên không bị dùng để "bù" tổng count.

**Hash file acceptance:** giữ `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD` (không đổi).

### A3.91 — Full §5 có acceptance, tách RED khỏi regression (A3-088)

**Command (đúng §5):**

```powershell
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
```

**Kết quả thật:**

```text
$smcTests  → 67 file (gồm file acceptance) + 6 file integration = 73 file
python -m pytest <73 file> -q --tb=no
65 failed, 905 passed in 9.48s
... --collect-only -q
970 tests collected in 6.02s
```

**Tách known acceptance RED khỏi regression khác (kiểm máy móc):**

```text
python -m pytest <73 file> -q --tb=no -rf | grep '^FAILED' | sed 's/^FAILED //; s/::.*//' | sort | uniq -c
     65 tests/test_smc_gate72_fix_acceptance.py
```

⇒ **toàn bộ 65 failure nằm trong file acceptance; 0 failure ở 72 file còn lại** ⇒ **không có regression ngoài
known acceptance RED**.

**Đối chiếu số (khớp tuyệt đối, không có test mất):**

| Nhóm | Node | Passed | Failed |
|---|---|---|---|
| Retained (66 SMC + 6 integration) — A3-087 | 854 | **854** | 0 |
| Acceptance mới — A3-084 | 116 | 51 | **65** |
| **Tổng §5** | **970** | **905** | **65** |

Kiểm: 854 + 116 = 970 ✓ (collect 970); 854 + 51 = 905 ✓ (passed); 0 + 65 = 65 ✓ (failed). Không file nào bị chạy
hai lần hay bị bỏ sót.

**Phát biểu trạng thái (không gọi toàn hệ thống xanh):** retained baseline **xanh hoàn toàn** (854/854) và trong
lệnh full **không có regression**; 51/116 node acceptance xanh; **65 RED còn lại là implementation gap F02…F10**
(tách bạch, đã phân loại ở §A3.87), **không** phải lỗi môi trường hay test.

**Hash file acceptance:** giữ `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD` (không đổi).

### A3.92 — Kiểm phạm vi diff và fingerprints trước trình (A3-089)

**Command/kết quả (thật):**

```text
git diff --check
# exit=0; chỉ có cảnh báo LF→CRLF đã tồn tại từ trước cho 7 file tracked (market_models, smc_confluence,
# smc_context, smc_lifecycle, smc_models, smc_sweep_linking, tests/test_smc_context) — KHÔNG có lỗi whitespace mới.

git status --short | awk '{print $1}' | sort | uniq -c
   123 ??
     5 D
     7 M
# tổng 135 entry — trùng khít con số ghi ở mọi mã A3-003…A3-088 của lượt này.

git status --short | grep -E "^ ?[MD]"
# M core/market_models.py, core/smc_confluence.py, core/smc_context.py, core/smc_lifecycle.py,
#   core/smc_models.py, core/smc_sweep_linking.py, tests/test_smc_context.py        (7 file — CÓ TRƯỚC)
# D docs/plans/dashboard-flat-icons-plan.md, flat-icons-gates-plan.md, flat-icons-phase2-plan.md,
#   flat-icons-score-breakdown-plan.md, location-scoring-upgrade-plan.md            (5 file — CÓ TRƯỚC)
```

**Đối chiếu fingerprint với A3-001 (F00):**

| Nhóm | Kết quả |
|---|---|
| 5 file `core/` (`smc_context`, `smc_models`, `smc_lifecycle`, `smc_sweep_linking`, `smc_confluence`) | **khớp A3-001** |
| reviewer probe `docs/plans/probes/test_smc_gate72_review.py` | **khớp** (`5B040D6A…`) |
| R56: contract, handoff, fixture golden `smc_canonical/golden_cases.json`, fixture + test session | **khớp** |
| **Tổng** | **11/11 khớp** ⇒ `core/`, probe, R56 **không** bị chạm trong toàn bộ lượt A3-007…A3-089 |

**Phạm vi thay đổi của lượt này (chỉ 4 file, đều untracked):**

| File | Loại sửa |
|---|---|
| `tests/test_smc_gate72_fix_acceptance.py` | thêm/sửa node + helper/import; hash cuối `E84A3093…` |
| `docs/plans/smc-task-72-fix-plan.md` | hàng A3-xxx + dòng tổng quan/đầu plan |
| `docs/plans/smc-task-72-fix-progress.md` | hàng ledger + §A3.10…§A3.92 |
| `docs/plans/smc-task-72-acceptance-matrix.md` | bảng theo dõi + mapping + quy ước node |

Không thêm/xoá file nào trong repo ⇒ `git status` giữ **135 entry** suốt lượt (đã ghi ở từng mã).

**Thay đổi của người khác (ghi rõ, KHÔNG reset/ghi đè):** 7 file tracked sửa + 5 file tracked xoá ở bảng trên là
**có trước** (trùng khít danh sách §A3.2 ghi tại mốc nhận việc), cùng 123 file untracked có trước (62 `tests/`,
58 `docs/`, 3 module `core/smc_{history,snapshot_cache,structure_replay}.py`). Lượt này chỉ **đọc** 3 module core
đó; không sửa, không xoá, không `git add`/`commit`/`reset`.

**Hash file acceptance:** `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD` (không đổi).

### A3.93 — Bản trình A lần3 ghép trong hồ sơ hiện có (A3-090)

> Ghi trong **hồ sơ hiện có** (không tạo file báo cáo mới, theo §8.7). Trạng thái A3: **WAITING_REVIEW** —
> Tech Lead quyết PASS/CHANGES_REQUESTED và việc đóng finding; Coder **không** tự PASS/CLOSED, **chưa** sang F02.

#### 1. Mapping F01.1…F01.4 → mã A3 → file/node/kết quả

| Cụm | Mã A3 | Sản phẩm | Kết quả |
|---|---|---|---|
| **F01.1** Representation & interface | A3-005…022 | M §Interface pool/history/metadata/claim→assignment; node interface trong file acceptance (provenance, claim time, metadata unknown/parity/nonfinite, buffer) | 18/18 mã IMPLEMENTED; node trong cụm: một phần GREEN (interface đã có), phần lớn RED thuộc F02/F03/F06/F08 (gap impl.) |
| **F01.2** Fixture & timeline | A3-023…038 | M §Danh sách candle factory/caller (A3-023), §Timeline D1 (A3-029), §Timeline H4 (A3-033); 5 fixture fixes T59/T60-BUY/T60-SELL/T62-BUY/T63-SELL; node timeline H4/D1, enrich↔restore, cadence | 16/16 IMPLEMENTED; **5 fixture fixes PASS**; node timeline chủ yếu RED (F04/F05) trừ các ca GREEN đã ghi |
| **F01.3** Test chưa chứng minh đúng nhánh | A3-039…062 | Node canonical: temporal gate `usable_at`/`reclaimed_at`, pool `records`/provenance, terminal cutoff = invalidated/expired, thứ tự terminal, typed round-trip, D1 consumer | 24/24 IMPLEMENTED; nhiều node RED thuộc F03/F05/F06/F08/F09/F10 (đã phân loại §A3.87) |
| **F01.4** Bù coverage & bàn giao | A3-063…090 | M mapping §4 (A3-063), fix-plan, per-sweep contribution (A3-074), JSON restore (A3-078), fill (A3-079), invalid-data (A3-080), mapping case-level (A3-081), collect/so inventory (A3-082), targeted (A3-083), full phân loại (A3-084), probes (A3-085), task57–71 (A3-086), retained (A3-087), full §5 (A3-088), diff/fingerprint (A3-089) | 28/28 IMPLEMENTED; **không** còn mã TODO/DOING/BLOCKED |

#### 2. Manifest (trạng thái trình)

| Hạng mục | Giá trị |
|---|---|
| File Coder sửa trong lượt (4, đều untracked) | `tests/test_smc_gate72_fix_acceptance.py` `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD` (**cuối, không đổi sau A3-081**) và `docs/plans/smc-task-72-acceptance-matrix.md` `AD6B0081EEB3C1A9EFCA14EED3649B97E93AA5040C35E476C490AB2311FC7828` (**cuối**). Hai file hồ sơ còn lại mang bản trình nên hash đổi theo mỗi lần ghi: `docs/plans/smc-task-72-fix-plan.md` `67A0431C91FD939401B5C86CB977F91BE9BF3809EE2DDF98C90D3C03C94C40C1`, `docs/plans/smc-task-72-fix-progress.md` `901F01F17850E532F7259B4176BA9BACCB333307FB8E64F4D927127CC7CA362C` — ghi ở đây là **hash ngay trước lần ghi cuối**; bản trình nằm trong chính hai file này nên chúng **không thể** tự khớp hash sau khi ghi (self-referential) — TL đối chiếu bằng cách mở file, không bằng hash tự thân. |
| Fingerprint F00 | **11/11 khớp A3-001** (5 core + probe `5B040D6A…` + R56 contract/handoff/golden/fixture/test) ⇒ `core/`, probe, R56 **không** bị chạm |
| Git | `git diff --check` **exit=0**; status **135** = 7 M + 5 D (có trước) + 123 ?? (có trước); **không** thêm/xoá file |
| Acceptance | **116 node** (74 hàm), `65 failed / 51 passed`, 0 lỗi collection |
| Retained baseline | **854 passed** (66 SMC + 6 integration), `--collect-only` = 854 |
| Full §5 | **970 node** / **905 passed** / **65 failed**; **cả 65 RED đều thuộc file acceptance** (0 regression ngoài) |
| Reviewer probes | **13 failed / 3 passed**, hash khớp F00 (không sửa) |

#### 3. Known RED (trước B/C — đúng dự kiến ở checkpoint A)

- **Acceptance 65 RED**: phân loại từng node ở **§A3.87** (mỗi dòng có expected/actual/gap F02…F10). Toàn bộ là
  implementation gap, không có fixture/test defect; 2 ca nonfinite surface dưới dạng `ValueError` từ core
  (`smc_lifecycle.py:674`, gap A3-017) và một số ca dùng `KeyError` nêu đúng field canonical đã duyệt nhưng core
  chưa có (`metadata_state`/`metadata_reason`/`usable`).
- **Probe 13 RED**: danh sách node→cụm ở **§A3.88** (R72-01×2, 02×1, 03×1, 04×1, 05×2, 06×2, 07×2, 08×2); hai
  `test_control_*` **PASSED** phải giữ xanh khi fix; 16/16 phải xanh trước checkpoint C.
- **GREEN 51 node** không tự là finding CLOSED (đóng thuộc TL).

#### 4. Quyết định còn mở (chỉ TL chốt)

1. **`kind` enum của pool record** — đề xuất `swing_low`/`swing_high`/`equal_low`/`equal_high` (M §Interface pool).
2. **Swing pool một source có nằm trong `records`** — đề xuất có (M §Interface pool).
3. **`level` của equal pool** — giữ trung bình + `source_ids` làm authority (M §Interface pool).
4. **Tên reason code metadata** — đề xuất `SMC_METADATA_*`; chưa chốt thì assertion chỉ đòi reason không rỗng
   (M §Interface metadata).
5. **Claim thiếu hẳn `pool_id`/`source_ids`** — fail closed kèm reason riêng hay nhận? Ảnh hưởng A3-045/A3-047
   (M §Interface claim→assignment).
6. **Hai điểm "CHƯA RÕ" của M vẫn mở**: (a) node positives của R72-09 validate **bản sao rows hard-code** trong file
   acceptance thay vì rows của module; (b) candle touch nhánh **SELL không phải mirror tuyệt đối** của BUY
   (A3-026) — chưa có node nào xác minh riêng.

#### 5. Trạng thái & giới hạn

- Checklist A3 **A3-001…A3-090 đã hoàn tất** về docs/test/verification ⇒ ghi **WAITING_REVIEW cho A3** (chờ TL).
- **Không** tự APPROVED, **không** đóng R72-01…09, **không** chuyển F02; PASS/CLOSED là quyết định của Tech Lead.
- Giới hạn đã biết: 65 RED acceptance + 13 RED probe là dữ liệu **trước** B/C (F01 cố ý không sửa `core/`); các
  quyết định ở mục 4 chưa chốt nên một số assertion hiện chỉ đòi "reason không rỗng" thay vì mã cụ thể.


**Hết dải A3-001…A3-090.** Trạng thái A3 = **WAITING_REVIEW** (Tech Lead quyết PASS/CHANGES_REQUESTED, việc đóng R72-01…09 và mọi bước F02+ thuộc TL).
Bản trình ghép ở §A3.93; known RED ở §A3.87 (acceptance) và §A3.88 (probe); quyết định còn mở ở §A3.93 mục 4.

[§8]: smc-task-72-fix-plan.md#8-checklist-rất-nhỏ-cho-checkpoint-a-lần-3

### A3.94 — Tech Lead review A lần3: CHANGES_REQUESTED

**Ngày:** 2026-09-11 (Asia/Saigon). **Quyết định hiện hành:** [review A lần3](smc-task-72-checkpoint-a-review-round3.md). Mục này thay trạng thái WAITING_REVIEW của §A3.93, không sửa/xóa lịch sử báo cáo Coder. Reviewer không triển khai core/tests.

| Finding review | Mã cần sửa | Kết luận |
|---|---|---|
| A3R3-01 | A3-071 | Context dùng ATR2 nên zone “outside” chỉ cách0.13ATR, vẫn eligible; test GREEN nhờ nearest-rank sai. Sửa fixture/precondition theo ATR thật, không sửa protected helper. |
| A3R3-02 | A3-067 | Không chấp nhận expected missing-metadata buffer0.0 là canonical fail-closed; rule thiếu nguồn phải None/unknown. Giữ các controls override đúng. |
| A3R3-03 | A3-061 | Positive control phải dùng prefix thật/reuse A3-060, không chỉ lùi cutoff trên snapshot đã invalidated. |
| A3R3-04 | A3-066 | Bổ sung canonical pool record/source/time→sweep parity và source permutation; cutoff dùng reclaim close. GREEN hiện tại mới chứng minh phần swing/legacy. |
| A3R3-05 | A3-043 + A3-039/040/041 | Cô lập/lọc đúng equal-pool lineage; không reject pool đơn hợp lệ hoặc ngầm khóa priority/cardinality detector. |

Reviewer đã đối chiếu bản acceptance hash `E84A30933CF7C99F22DB08451366A7B9D849376371F5FAE334820CB96D7FDBBD`; matrix bản trình hash `AD6B0081EEB3C1A9EFCA14EED3649B97E93AA5040C35E476C490AB2311FC7828` (hash này trước khi ghi review, không dùng so matrix sau cập nhật). 11 fingerprint F00 khớp §A3.3.

**Kết quả chạy reviewer:** collection116; acceptance65 failed/51 passed; task57–71:108 passed; retained854 passed; full65 failed/905 passed (970 total, mọi failure ở acceptance); probe13 failed/3 passed. Targeted A3-071/067/066×2/061:4 passed/1 failed. Không có regression ngoài acceptance; không dùng điều đó để khẳng định “không có test defect” như bản trình cũ. Hai node A3-061/A3-043 có thể vừa dừng ở gap implementation hiện tại vừa cần sửa oracle; các GREEN nêu trong review cũng chưa được duyệt.

**Các câu hỏi mở §A3.93 mục4:** đã chốt tại review §3 (kind enum, single-source records, equal mean, metadata reason names, canonical/legacy lineage boundary). Bản sao fixture được bù bởi actual factory validation+108 task tests; SELL touch khác số nhưng đúng semantics: cả hai không blocking, không thêm node trùng. Giữ đánh giá A3-076 IMPLEMENTED/EXPECTED_IMPLEMENTATION_RED-F10; không hồi tố helper legacy control thành canonical-provenance defect.

**Giao tiếp:** chỉ sửa8 mã test trong bảng; các mã khác giữ IMPLEMENTED. A3-081…089 refresh matrix/actual/classification/tests/hashes sau sửa; A3-090 CHANGES_REQUESTED, trình A lần4 trong file này. Không cần dải90 task mới hoặc TL review từng mã. Các ô Actual còn trống và mapping summary cũ trong matrix được đồng bộ bằng kết quả mới, không phải yêu cầu80 test mới. F00/fixture fixes giữ PASS, chưa F02/task73, R72-01…09 OPEN.

### A3.95 — Sửa fixture context theo ATR thật (A3-071/a; finding A3R3-01)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-01](smc-task-72-checkpoint-a-review-round3.md) — “[P1] A3-071: fixture context không thực sự ngoài khoảng cách”.

**Vấn đề tái lập:** tầng **link trực tiếp** đã đúng vì truyền `atr_value=1.0`, nhưng tầng **context** gọi `_probe.attach` → `_attach_zone_sweep_links(..., candles=candles([(120,121,119,120)]*20))`, mà caller tự tính `atr_value = _latest_atr(candles)` ⇒ **ATR thực = 2.0**. Zone được gọi là “ngoài” `[105.26,106]` chỉ cách `0.26 / 2.0 = 0.13` ATR ⇒ **vẫn eligible**. Test ghép vì thế xanh nhờ core ưu tiên khoảng cách gần — chính hành vi F08 phải sửa.

**Falsification check (chạy trước khi sửa, read-only trên probe, không sửa probe):**

```text
zone ngoài [105.26,106] qua _probe.attach (ATR 2.0)  → linked True, distance_atr 0.13
```

**Sửa (chỉ trong `T`; `_probe.attach` và ba boundary controls giữ nguyên):**

1. **Candle input local cho caller**: `context_rows = [(120.0, 120.5, 119.5, 120.0)] * 20` — `TR = max(1.0, 0.5, 0.5) = 1.0` mọi nến ⇒ trung bình Wilder **bằng chính hằng số đó** ⇒ ATR caller `1.0`, dẫn xuất độc lập (assert từng hàng `TR == 1.0`, không đọc giá trị production).
2. **Giữ ba boundary controls ở helper** (`associate_sweeps_to_zones(..., atr_value=fixture_atr)`) : trong `[104,106]` ⇒ `distance_atr 0.0`; đúng biên `[105.25,106]` ⇒ `distance_atr 0.25`; ngoài `[105.26,106]` ⇒ `None`.
3. **Eligibility từng zone riêng qua chính caller** (`context_attach` gọi `_attach_zone_sweep_links` với candle input local) **trước khi ghép hai thứ tự**:
   `inside` ⇒ `liquidity_sweep_linked True` + `linked_sweep_distance_atr == 0.0` + owner `"inside"`;
   `exact` ⇒ `True` + `linked_sweep_distance_atr == 0.25` + owner `"exact"`;
   `outside` ⇒ `liquidity_sweep_linked False`, `linked_sweep_id None`, event `consumed False`/`linked_zone_id None`/không có `owner_setup_id`.
4. **Sau đó** mới ghép cặp (outside available `hour 13` sớm hơn vs inside `hour 15`) ⇒ owner `"inside-late"`, cả hai thứ tự.

**Command/kết quả thật (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
116 tests collected in 0.52s                     (không đổi inventory; 0 lỗi collection)

python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep" -q --tb=short
1 passed in 0.15s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_02" --tb=no -rf
5 failed, 4 passed, 107 deselected in 0.16s      (node A3-071 PASSED; 5 RED là F08 đã ghi ở §A3.87 dòng16–20)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
65 failed, 51 passed in 0.40s                    (khớp baseline review: 65 failed / 51 passed)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi; probe không sửa, hash `5B040D6A…` khớp F00)
```

**Positive control bị ảnh hưởng (chạy kèm):** 4 node `r72_02` còn lại **PASS** — `test_r72_02_opposite_side_claim_cannot_own_a_sweep` (A3-070), `test_r72_02_claim_outside_time_window_cannot_own_a_sweep` (A3-072), `test_r72_02_same_time_tie_is_stable_under_claim_permutation` (helper), `test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep` (A3-071). 5 node RED giữ nguyên là **implementation gap F08 đã ghi**: `…acceptance_context_ranks_all_eligible_claims_by_causal_time`, `…context_owner_follows_claim_time_under_input_permutation`, `…context_same_time_tie_follows_stable_setup_id`, `…missing_canonical_claim_time_fails_closed[reclaimed_at]`, `…[setup_available_at]` — assert đầu tiên fail và F-code nằm ở §A3.87 dòng16–20; **không** node nào đổi trạng thái do lượt này.

**Phân loại:** **GREEN 1/1** cho node A3-071 **sau khi sửa oracle** — fixture context nay phản ánh ATR thật, và cả ba mức trong/đúng/ngoài được khẳng định **qua chính caller** ở trạng thái từng zone đứng một mình, nên cặp zone không còn dựa vào lỗi nearest-rank. RED của node này (nếu có) sẽ phải là lỗi `implementation`, không phải do fixture.

**Hash mới file acceptance:** `93DFBA7DC1A017355E1D0AB2793AC24D68D324C4CA0B65441C9012611EA38B8A`
(§A3.80 ghi `E84A3093…` — hash đã review; các hash trước giữ nguyên làm lịch sử).

**Phạm vi:** chỉ `T` (một hàm test) + `M` (dòng R72-02/A3-071) + `L` (dòng checklist A3-071 và mục này) + `smc-task-72-fix-plan.md` (dòng A3-071 §8.5). **Không** sửa `core/`, protected probe, R56/golden; **không** skip/xfail; **không** commit.

**Việc còn lại của checkpoint A (thuộc lượt khác, không làm ở đây):** A3-067 (A3R3-02), A3-061 (A3R3-03), A3-066 (A3R3-04), A3-043 + A3-039/040/041 (A3R3-05), rồi refresh A3-081…089 và trình A lần4 (A3-090). A3-071 giữ **IMPLEMENTED** ở phần test/oracle; checkpoint A vẫn **CHANGES_REQUESTED**, R72-01…09 vẫn **OPEN** — PASS/CLOSED thuộc Tech Lead.

### A3.96 — Từng zone đứng riêng qua context: event-level (A3-071/b; finding A3R3-01)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-01](smc-task-72-checkpoint-a-review-round3.md) — vế “Assert ATR/khoảng cách và eligibility của từng zone riêng qua chính caller trước khi ghép hai thứ tự. Zone ngoài phải không link khi đứng một mình; zone trong/đúng biên phải đạt theo cùng nguồn ATR.”

**Trạng thái vào lượt:** lượt A3-071/a (§A3.95) đã dựng `context_attach` (candle input local ⇒ ATR caller `1.0`) và `sole_event` (chạy **một** zone qua caller), nhưng vế “được link” mới khẳng định trên **zone payload** (`liquidity_sweep_linked`) + owner; chưa khẳng định **event** của sweep có thuộc chính zone đó. Phần đó là nội dung A3-071/b.

**Sửa (chỉ trong `T`, cùng node `test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep`; `_probe.attach` và `_probe` giữ nguyên):** bổ sung 6 assert **event-level** cho hai case đứng riêng `inside`/`exact` — `event["linked_zone_id"] == "<zone>-child"`, `event["owner_setup_id"] == "<setup>"`, `event["consumed"] is True` — và giữ vế âm `outside` (`linked_zone_id None`, `consumed False`, không `owner_setup_id`). Không thêm node mới, không đổi fixture, không đổi expected (assert suy từ contract: zone eligible ⇒ có claim ⇒ `mark_sweeps_consumed` gắn `consumed True`/owner lên sweep đã chiếu).

**Giá trị đọc thật (đứng riêng qua chính caller, ATR caller `1.0`, read-only):**

```text
inside-child   linked=True  dist_atr=0.0   event.linked_zone_id=inside-child  owner=inside   consumed=True
exact-child    linked=True  dist_atr=0.25  event.linked_zone_id=exact-child   owner=exact    consumed=True
outside-child  linked=False dist_atr=None  event.linked_zone_id=None          owner=None     consumed=False
```

**Command/kết quả thật (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
116 tests collected in 0.56s                     (không đổi inventory; 0 lỗi collection)

python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep" -q --tb=short
1 passed in 0.15s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_02" --tb=no -rf
5 failed, 4 passed, 107 deselected in 0.16s      (node A3-071 PASSED; 5 RED vẫn đúng tập F08 ở §A3.87 dòng16–20)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
65 failed, 51 passed in 0.42s                    (khớp baseline review: 65 failed / 51 passed)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi; probe không sửa)
```

**Phân loại:** **GREEN 1/1** — ba case đứng riêng đã được khẳng định ở cả hai tầng (payload zone và event sweep): trong/đúng biên **được link và sở hữu sweep**, ngoài biên **không** link; cùng một nguồn ATR fixture `1.0`. Không phát sinh RED mới, không node nào đổi trạng thái.

**Hash mới file acceptance:** `47FE1C2F29599476404712401C8030454C954182113855A328F80F6EA8F31CC4`
(§A3.95 ghi `93DFBA7D…`; các hash trước giữ nguyên làm lịch sử).

**Phạm vi:** chỉ `T` (một hàm test) + `M` (dòng R72-02/A3-071) + `L` (dòng checklist A3-071 và mục này) + `smc-task-72-fix-plan.md` (dòng A3-071 §8.5). **Không** sửa `core/`, protected probe, R56/golden; **không** skip/xfail; **không** commit; không thêm/xoá file.

**Kết luận mã A3-071:** hai phần **/a** (fixture theo ATR thật) và **/b** (event-level từng zone đứng riêng) đều xong và có bằng chứng ⇒ hàng A3-071 giữ **IMPLEMENTED**. Checkpoint A vẫn **CHANGES_REQUESTED**; R72-01…09 vẫn **OPEN**; mã kế tiếp theo review §4 là **A3-067**.

### A3.97 — Hai thứ tự zone: outside available sớm hơn vẫn không lấy owner (A3-071/c; finding A3R3-01)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-01](smc-task-72-checkpoint-a-review-round3.md) — vế “Sau đó mới assert outside không lấy ownership dù available sớm hơn” và “pair/permutation không dựa lỗi nearest-rank”.

**Trạng thái vào lượt:** vế cặp zone đã có từ lượt A3-071/a, nhưng vòng lặp dùng **cùng hai dict zone** cho cả hai thứ tự — lượt thứ hai chạy trên dict **đã bị caller ghi link payload** ở lượt đầu, nên tính độc lập của phép hoán vị không được chứng minh; chưa assert zone ngoài **không** nhận owner/assignment, và chưa so trực tiếp hai thứ tự.

**Sửa (chỉ trong `T`, cùng node `test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep`; fixture/probe giữ nguyên):**

1. `build_pair()` dựng **pair mới** mỗi thứ tự (`build_pair()` và `build_pair()[::-1]`) ⇒ lượt đảo không kế thừa payload của lượt trước; precondition `outside_early["available_at"] < inside_late["available_at"]` (hour 13 < 15) chứng minh **chỉ rule khoảng cách** mới loại được zone ngoài — xếp hạng theo thời gian sẽ chọn nó.
2. Trong mỗi thứ tự: inside-late `liquidity_sweep_linked True` + `sweep_owner_setup_id "inside-late"`, event `consumed True`/`owner_setup_id "inside-late"`/`linked_zone_id "inside-late-child"`; outside-early `liquidity_sweep_linked False`, `linked_sweep_id None`, **không có** `sweep_owner_setup_id`/`sweep_assignment_id` (đúng nghĩa “không lấy owner/assignment”).
3. Sau vòng lặp: `owner_setup_id`/`assignment_id`/`linked_zone_id`/`claim_eligible_at` **giống nhau** giữa hai thứ tự (cùng cách A3-069).

**Giá trị đọc thật (read-only, hai thứ tự, ATR caller `1.0`):**

```text
[outside,inside] owner=inside-late assignment=smca-cf4c5d5cb.. linked_zone=inside-late-child claim_at=2026-09-01T15:00:00+00:00
    outside: linked=False linked_sweep_id=None has_owner_key=False has_assignment_key=False
    inside : linked=True  sweep_owner=inside-late
[inside,outside] owner=inside-late assignment=smca-cf4c5d5cb.. linked_zone=inside-late-child claim_at=2026-09-01T15:00:00+00:00
    outside: linked=False linked_sweep_id=None has_owner_key=False has_assignment_key=False
    inside : linked=True  sweep_owner=inside-late
```

**Command/kết quả thật (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
116 tests collected in 0.51s                     (không đổi inventory; 0 lỗi collection)

python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep" -q --tb=short
1 passed in 0.14s

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_02" --tb=no -rf
5 failed, 4 passed, 107 deselected in 0.17s      (node A3-071 PASSED; 5 RED vẫn đúng tập F08 ở §A3.87 dòng16–20)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
65 failed, 51 passed in 0.41s                    (khớp baseline review: 65 failed / 51 passed)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi; probe không sửa)
```

**Phân loại:** **GREEN 1/1** — hai thứ tự cho **cùng** owner/assignment/linked zone/claim time, và zone ngoài khoảng dù `available_at` **sớm hơn** vẫn không có link, không owner, không assignment. Không phát sinh RED mới, không node nào đổi trạng thái.

**Hash mới file acceptance:** `23AE09AD38A960BD178076001047916FF3B6297D1917A3576D247D6AB1ACC9EE`
(§A3.96 ghi `47FE1C2F…`; các hash trước giữ nguyên làm lịch sử).

**Phạm vi:** chỉ `T` (một hàm test) + `M` (dòng R72-02/A3-071) + `L` (dòng checklist A3-071 và mục này) + `smc-task-72-fix-plan.md` (dòng A3-071 §8.5). **Không** sửa `core/`, protected probe, R56/golden; **không** skip/xfail; **không** commit; không thêm/xoá file.

**Kết luận mã A3-071:** ba phần **/a** (fixture theo ATR thật), **/b** (event-level từng zone đứng riêng) và **/c** (hai thứ tự, outside sớm hơn không lấy owner) đều xong và có bằng chứng ⇒ hàng A3-071 giữ **IMPLEMENTED**. Checkpoint A vẫn **CHANGES_REQUESTED**; R72-01…09 vẫn **OPEN**; mã kế tiếp theo review §4 là **A3-067**.

### A3.98 — Sửa oracle thiếu metadata cho rule override (A3-067/a; finding A3R3-02)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-02](smc-task-72-checkpoint-a-review-round3.md) — “[P1] A3-067: ngưỡng thiếu metadata bị khóa thành 0”; interface metadata [A3-007](smc-task-72-acceptance-matrix.md#interface-metadata--chốt-theo-review-a-lần2-a3-007).

**Vấn đề tái lập:** node `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule` gọi `touch_lifecycle(zone_tolerance=0.5)` **không** tick/ATR rồi assert `invalidation_buffer == pytest.approx(0.0)` và gọi đó là fail-closed. Trái contract A3-007: rule không tính được phải **`None` + `metadata_state unknown` + reason**, không phải `0` (`0` là ngưỡng thật hợp lệ nên không mang nghĩa “không biết”). Biến thể reviewer nêu — nến đóng `99.93` cùng thiếu metadata — cho thấy hệ quả:

```text
break fixture [(112,114,111,113),(105,106,99.90,99.93)], không tick/ATR:
  invalidation_buffer = 0.0      lifecycle_broken = True     (core hiện tại)
ZoneLifecycle fields = [age_bars, …, invalidation_buffer, …]  → KHÔNG có metadata_state/metadata_reason (F02)
```

**Sửa (chỉ trong `T`, cùng node; fixture/probe giữ nguyên):**

1. Giữ nguyên **3 controls đủ metadata** (default `buffer 0.1`/`visits == ()`; `zone_tolerance=0.5` ⇒ 1 visit nhưng buffer vẫn `0.1`, `broken False`; `break_buffer=0.05` ⇒ buffer `0.05`, `broken True`) — chứng minh mỗi override chỉ đổi đúng rule của nó.
2. Ca thiếu metadata (nến chạm) khóa theo canonical: `len(visits) == 1` (override overlap không cần metadata) + `metadata_state == "unknown"` + `metadata_reason` không rỗng + `invalidation_buffer is None` + `lifecycle_broken is False`.
3. Thêm ca **thiếu metadata cho nến đóng `99.93`** (đúng biến thể reviewer kiểm): `metadata_state == "unknown"`, `invalidation_buffer is None`, `lifecycle_broken is False` ⇒ **không** coi `0` là fail-closed, unknown không tự tạo invalidation.
4. Bỏ hẳn oracle cũ `invalidation_buffer == 0.0`; **không** giữ legacy control cho hành vi sai này; docstring đổi từ “fail-closed 0.0” sang “not computable ⇒ `None` + unknown + reason”. Không thêm tham số override mới.

**Command/kết quả thật (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule" -q --tb=long
1 failed in 0.65s
  → assert đầu fail: `without_metadata.metadata_state == "unknown"`
    AttributeError: 'ZoneLifecycle' object has no attribute 'metadata_state'   (RED — F02)
  → precondition TRƯỚC đó đều PASS: default.visits == () ; default.invalidation_buffer ≈ 0.1 ;
    len(overridden.visits) == 1 ; overridden.invalidation_buffer ≈ 0.1 ; overridden.lifecycle_broken is False ;
    len(without_metadata.visits) == 1
  → các assert SAU chưa chạy: metadata_reason, invalidation_buffer is None, lifecycle_broken is False,
    và toàn bộ block thiếu-metadata của nến 99.93 (KHÔNG báo PASS)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_07" -q --tb=no
13 failed, 6 passed                               (R72-07 RED 12 → 13; 6 GREEN giữ nguyên = 2 node override
                                                   excursion/equal_tolerance + 2 node buffer boundary + 2 node A3-068)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
66 failed, 50 passed                              (trước lượt: 65 failed / 51 passed — đúng 1 node đổi trạng thái)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                               (không đổi; probe không sửa)
```

**Positive control bị ảnh hưởng (giữ xanh):** `test_r72_07_excursion_override_only_replaces_its_own_rule`, `test_r72_07_equal_tolerance_override_only_replaces_its_own_rule` (hai node override cùng mã A3-067) và hai node buffer boundary `test_r72_07_equal_and_outside_buffer_buy_sell[buy|sell]` đều **PASSED** sau sửa ⇒ RED mới **chỉ** nằm ở vế thiếu-metadata, không phải do đổi fixture hay đổi rule.

**Phân loại:** **EXPECTED_IMPLEMENTATION_RED (F02)** cho phần thiếu metadata — đúng như review cho phép (“RED do F02 được phép giữ”). Đây là **sửa oracle**, không phải regression: node trước đây xanh nhờ khóa một giá trị sai (`0.0`) làm chuẩn. Vế `usable is False` của cùng điều kiện đã được assert trên **canonical path** bởi `test_r72_07_missing_canonical_atr_is_unknown_and_unusable` / `…missing_canonical_tick…` (A3-015/A3-016, RED F02) — không lặp lại ở đây vì `zone_tolerance` không đi qua `enrich_zones`.

**Hash mới file acceptance:** `7C4B251A569F5A207A902B816A6A8E174107274DF75DDFFCADA871259C963D78`
(§A3.97 ghi `23AE09AD…`; các hash trước giữ nguyên làm lịch sử).

**Phạm vi:** chỉ `T` (một hàm test) + `M` (dòng theo dõi R72-07 và bảng "Override audit — A3-067") + `L` (dòng checklist A3-067 và mục này) + `smc-task-72-fix-plan.md` (dòng A3-067 §8.5). **Không** sửa `core/`, protected probe, R56/golden; **không** skip/xfail; **không** thêm override mới; **không** commit; không thêm/xoá file.

**Kết luận mã A3-067:** phần **/a** (oracle thiếu metadata ⇒ `None`/`unknown`/reason, bỏ `0.0`; đồng bộ mô tả matrix/plan) xong và có bằng chứng ⇒ hàng A3-067 ghi **IMPLEMENTED**. Checkpoint A vẫn **CHANGES_REQUESTED**; R72-01…09 vẫn **OPEN**; mã kế tiếp theo review §4 là **A3-061**.

### A3.99 — Cross-control: mỗi override chỉ đổi đúng rule của nó (A3-067/b; finding A3R3-02)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-02](smc-task-72-checkpoint-a-review-round3.md) — “giữ controls đủ metadata chứng minh từng override chỉ đổi đúng rule”; “Không thêm tham số override mới”.

**Trạng thái vào lượt:** sau A3-067/a node đã giữ 3 controls (`default`, `zone_tolerance=0.5` trên fixture chạm, `break_buffer=0.05` trên fixture phá) nhưng mỗi override **chưa** được chạy trên fixture của rule kia, nên vế “chỉ đổi đúng rule của nó” mới được chứng minh một chiều; và khối thiếu-metadata (RED F02) nằm **trước** phần controls phá, khiến các assert đó không chạy.

**Sửa (chỉ trong `T`, cùng node; fixture/probe giữ nguyên, không thêm override mới):**

1. **Cross-control cho `break_buffer`:** `touch_lifecycle(tick_size=0.1, atr_current=1.0, break_buffer=0.05)` ⇒ `invalidation_buffer == 0.05` (override vào đúng rule của nó) và `visits == ()` — **giống hệt** default, tức rule overlap không hề nới; `lifecycle_broken is False`.
2. **Cross-control cho `zone_tolerance`:** `break_lifecycle(tick_size=0.1, atr_current=1.0, zone_tolerance=0.5)` ⇒ `invalidation_buffer == 0.1` (**không** phải `0.5` — nếu override rò sang rule buffer thì giá trị sẽ là `0.5`) và `lifecycle_broken is False` — giống hệt khi không override.
3. **Thứ tự:** nhóm controls đủ metadata (gồm 2 cross-control) đặt **trước** khối thiếu-metadata, nên chúng thực sự chạy dưới RED F02 hiện tại thay vì bị bỏ qua sau assert fail.
4. Docstring ghi rõ vế cross-control.

**Giá trị đọc thật (read-only, trước khi khóa assertion):**

```text
touch  default            : buffer 0.1   visits 0
touch  break_buffer=0.05  : buffer 0.05  visits 0   broken False
touch  zone_tolerance=0.5 : buffer 0.1   visits 1   broken False
break  default            : buffer 0.1                 broken False   visits 1
break  zone_tolerance=0.5 : buffer 0.1   (≠0.5)        broken False   visits 1
break  break_buffer=0.05  : buffer 0.05                broken True    visits 1
```

**Command/kết quả thật (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
116 tests collected in 0.52s                     (không đổi inventory; 0 lỗi collection)

python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule" -q --tb=long
1 failed in 0.28s
  → assert fail duy nhất vẫn là `without_metadata.metadata_state == "unknown"`
    AttributeError: 'ZoneLifecycle' object has no attribute 'metadata_state'   (RED — F02, KHÔNG đổi)
  → đạt tới dòng fail nghĩa là MỌI assert trước đó đã PASS, gồm 2 cross-control mới
    (`invalidation_leak`, `overlap_leak`) và 3 controls cũ
  → các assert SAU vẫn chưa chạy (metadata_reason, invalidation_buffer is None,
    lifecycle_broken is False, block thiếu-metadata của nến 99.93) — KHÔNG báo PASS

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_07" --tb=no
13 failed, 6 passed                              (không đổi so với A3-067/a: RED 13, GREEN 6)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
66 failed, 50 passed                             (không đổi — lượt này không đổi trạng thái node nào)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi; probe không sửa)
```

**Phân loại:** **không sinh RED mới** — 2 cross-control **PASS** và node vẫn dừng ở đúng assert F02 cũ. RED hiện tại giữ nguyên là **EXPECTED_IMPLEMENTATION_RED (F02)** như đã ghi ở §A3.98.

**Hash mới file acceptance:** `7AF299C484CC79D0D044FA9F279423ED928F441A4D30569200CC71457786311D`
(§A3.98 ghi `7C4B251A…`; các hash trước giữ nguyên làm lịch sử).

**Phạm vi:** chỉ `T` (một hàm test) + `M` (dòng theo dõi R72-07) + `L` (dòng checklist A3-067 và mục này) + `smc-task-72-fix-plan.md` (dòng A3-067 §8.5). **Không** sửa `core/`, protected probe, R56/golden; **không** skip/xfail; **không** thêm override mới; **không** commit; không thêm/xoá file.

**Kết luận mã A3-067:** hai phần **/a** (oracle thiếu metadata ⇒ `None`/`unknown`/reason) và **/b** (cross-control mỗi override chỉ đổi đúng rule) đều xong và có bằng chứng ⇒ hàng A3-067 giữ **IMPLEMENTED**. Checkpoint A vẫn **CHANGES_REQUESTED**; R72-01…09 vẫn **OPEN**; mã kế tiếp theo review §4 là **A3-061**.

### A3.100 — Đồng bộ mô tả “fail-closed” cho thiếu metadata (A3-067/c; finding A3R3-02)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-02](smc-task-72-checkpoint-a-review-round3.md) — “Sửa mô tả ‘fail-closed `0.0`’ trong matrix/plan”; interface [A3-007](smc-task-72-acceptance-matrix.md#interface-metadata--chốt-theo-review-a-lần2-a3-007) (threshold không tính được ⇒ `None`, **không** `0`).

**Việc của lượt:** quét toàn bộ docstring/mô tả trong `T`, `M`, `L`, plan còn gọi trạng thái **thiếu metadata** là “fail-closed `0.0`” (hoặc đồng nhất nó với một ngưỡng số), rồi đồng bộ; **không** sửa báo cáo review (`smc-task-72-checkpoint-a-review-round1/2/3.md`) và không viết lại lịch sử.

**Kết quả quét (4 file trong phạm vi):**

| Vị trí | Nội dung cũ | Xử lý |
|---|---|---|
| `T` docstring node A3-067 (dòng 3571) | “with tick/ATR absent the buffer stays the **fail-closed 0.0**” | **Đã sửa ở §A3.98** (A3-067/a) → “not computable ⇒ `None` + `unknown` + reason” |
| `T` docstring node A3-021 (dòng 2402) | “Expected values come from the A3-007 contract (**unknown/fail-closed**)” | **Sửa lượt này** → “(`unknown ⇒ unusable`, threshold `None`)” — bỏ cách gọi tắt dễ bị đọc thành ngưỡng số; assertion của node **không** đổi |
| `M` dòng theo dõi R72-07 (406) | “buffer fail-closed `0.0`” | **Đã sửa ở §A3.98** |
| `M` bảng override (924/925) | “buffer fail-closed `0.0`” | **Đã sửa ở §A3.98** |
| `M` §4 (589) + §6 (607) | “hiện tại buffer `0.0` làm close sát biên bị coi là invalidation” / “Sai: phải `unknown` + threshold `None`” | **Giữ nguyên** — đang mô tả **lỗi hiện trạng** và đã ghi rõ là `Sai` đối chiếu contract, không cổ suý `0.0` |
| `M` interface proposal dòng 172 | “unknown/fail-closed” | **Giữ nguyên** — mục đã bị §A3-007 **thay thế** và được ghi rõ “dòng cũ giữ làm lịch sử” |
| `L` §A3.70 (3687) | “(c) **không** tạo metadata còn thiếu (thiếu tick/ATR ⇒ buffer fail-closed `0.0`)” | **Giữ nguyên + đính chính** đã thêm ở §A3.98 (blockquote ngay dưới) |
| plan dòng A3-067 §8.5 | “không tick/ATR ⇒ buffer fail-closed 0.0” | **Đã sửa ở §A3.98** |

Không còn mô tả nào đang hiệu lực gọi thiếu metadata là “fail-closed `0.0`”.

**Command/kết quả thật (`node` = `tests/test_smc_gate72_fix_acceptance.py`; sửa docstring nên có chạy lại):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
116 tests collected in 0.54s                     (không đổi inventory; 0 lỗi collection)

python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_metadata_survives_context_to_typed_round_trip" \
                "tests/test_smc_gate72_fix_acceptance.py::test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule" -q --tb=short
2 failed in 0.17s
  → A3-021: assert đầu fail `context["metadata_state"] == "unknown"` → `KeyError: 'metadata_state'`  (F02)
  → A3-067: assert đầu fail `without_metadata.metadata_state == "unknown"` → `AttributeError`      (F02)
  → cả hai đã RED từ trước lượt này; docstring không đổi hành vi, và assert sau vẫn CHƯA chạy

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
66 failed, 50 passed                             (không đổi — chỉ sửa docstring)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi; probe không sửa)
```

**Phân loại:** **không sinh RED/GREEN mới** — 2 node RED giữ nguyên đúng assert F02 như §A3.87; lượt này chỉ đồng bộ văn bản.

**Hash mới file acceptance:** `31B728A440D9C272F1FFDEA1A1D0CB0499079C6E63FA980314CDF8C5C1018931`
(§A3.99 ghi `7AF299C4…`; các hash trước giữ nguyên làm lịch sử).

**Phạm vi:** chỉ `T` (một docstring) + `L` (dòng checklist A3-067 và mục này) + `smc-task-72-fix-plan.md` (dòng A3-067 §8.5). `M` **không** phải sửa vì expected/node/result không đổi. **Không** sửa `core/`, protected probe, R56/golden, **báo cáo review**; **không** skip/xfail; **không** commit; không thêm/xoá file.

**Kết luận mã A3-067:** ba phần **/a** (oracle ⇒ `None`/`unknown`), **/b** (cross-control) và **/c** (đồng bộ mô tả) đều xong, có bằng chứng ⇒ hàng A3-067 giữ **IMPLEMENTED**. Checkpoint A vẫn **CHANGES_REQUESTED**; R72-01…09 vẫn **OPEN**; mã kế tiếp theo review §4 là **A3-061**.

### A3.101 — Positive control bằng prefix thật (A3-061/a; finding A3R3-03)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-03](smc-task-72-checkpoint-a-review-round3.md) — “[P2] A3-061: positive control dùng snapshot tương lai”.

**Vấn đề tái lập:** node `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` enrich **toàn chuỗi đã invalidated** (`_D1_INVALIDATION_ROWS`, nến cuối 43) rồi chỉ lùi `as_of` về close nến 41 trên **cùng payload terminal** để đòi `valid=True`. Theo data spec §1 đó **không phải** prefix snapshot: snapshot có close cuối `2026-02-14` nhưng cutoff là `2026-02-12`. A3-062 đã loại đúng cách làm này (§A3.65) và dùng A3-060 làm control.

**Falsification check (read-only):**

```text
prefix  (_D1_RETEST_ROWS, enrich riêng) : status=confirmed broken=False invalidation_index=None expiry_index=None visits=1
                                          last close = 2026-02-12   ← chính là cutoff
terminal(_D1_INVALIDATION_ROWS)         : status=confirmed broken=True  invalidation_index=43          visits=2
                                          last close = 2026-02-14   ← snapshot bị cắt ngược ở control cũ
identity parity (prefix vs terminal)    : zone_id True · low/high True · available_at True · visits[0] True
```

**Sửa (chỉ trong `T`, cùng node; fixture/probe giữ nguyên):** control cũ thay bằng **prefix thật** — `_d1_enriched_source()` (chuỗi `_D1_RETEST_ROWS` = `_D1_INVALIDATION_ROWS` bỏ 2 nến terminal) enrich **riêng**, typed round-trip riêng, `as_of = _d1_close_at(prefix_candles, len-1)` = close nến 41. Trước khi gọi consumer, assert:
- prefix **chưa terminal**: `lifecycle_status == "confirmed"`, `broken is False`, `invalidation_index`/`invalidated_at`/`expiry_index`/`expired_at` đều `None`;
- **identity/history khớp bản append**: `zone_id`, `low`/`high`, `available_at`, `visits[0]` bằng nhau; `prefix_cutoff == expected_reacted_at`;
- consumer trên prefix: `valid True`, `score > 0`, `source_visit_id` = visit-1 **của chính prefix**, `reacted_at` = close nến 41.

Bản terminal giữ nguyên: `lifecycle_status == "invalid"`, `usable is False`, D1 `valid False`/`score 0`, và reject **không** vì thiếu reaction. **Không** còn yêu cầu consumer hồi dựng snapshot quá khứ từ payload terminal. Không đổi comment trong core; không sửa fixture.

**Command/kết quả thật (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
116 tests collected in 0.56s                     (không đổi inventory; 0 lỗi collection)

python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer" -q --tb=long
1 failed in 0.30s
  → toàn bộ precondition + **positive control prefix** PASS (đạt tới dòng fail nghĩa là mọi assert trước đã chạy)
  → assert đầu fail KHÔNG đổi: `enriched["lifecycle_status"] == "invalid"` → `AssertionError: assert 'confirmed' == 'invalid'`  (F03/R72-08)
  → các assert sau CHƯA chạy: `usable is False`, D1 `valid False`/`score 0`, loại trừ `D1_REACTION_NOT_COMPLETED_REACTED`

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_09" --tb=no
1 failed, 9 passed                               (A3-060 positive vẫn GREEN; 9 node còn lại của nhóm không đổi)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
66 failed, 50 passed                             (không đổi — cục bộ trong node A3-061)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi; probe không sửa)
```

**Phân loại:** **RED giữ nguyên** — cùng node, cùng assert dừng, đúng gap **F03/R72-08** (và F05/A-D04 phía sau); lượt này chỉ làm control **hợp lệ** nên RED không còn bị nghi do fixture/control sai. Không sinh RED/GREEN mới.

**Hash mới file acceptance:** `AD95E1F083F82CE4120044F3D82EC0E2F25E3169D943B7E92C715163E554285C`
(§A3.100 ghi `31B728A4…`; các hash trước giữ nguyên làm lịch sử).

**Phạm vi:** chỉ `T` (một hàm test) + `M` (dòng theo dõi R72-09/A3-061) + `L` (dòng checklist A3-061 và mục này) + `smc-task-72-fix-plan.md` (dòng A3-061 §8.5). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit; không thêm/xoá file.

**Kết luận mã A3-061:** phần **/a** (thay positive control bằng prefix thật; kiểm identity/reaction/chưa-terminal) xong và có bằng chứng ⇒ hàng A3-061 ghi **IMPLEMENTED**. Checkpoint A vẫn **CHANGES_REQUESTED**; R72-01…09 vẫn **OPEN**; mã kế tiếp theo review §4 là **A3-066**.

### A3.102 — Bản append tại invalidation close, không rewind (A3-061/b; finding A3R3-03)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-03](smc-task-72-checkpoint-a-review-round3.md) — “Bản terminal tiếp tục kiểm invalid/unusable và D1 false/0 ở đúng close. Không yêu cầu consumer hồi dựng snapshot quá khứ từ terminal payload.”

**Trạng thái vào lượt:** các assert contract tại terminal (`lifecycle_status == "invalid"`, `usable is False`, D1 `valid False`/`score 0`, loại trừ `D1_REACTION_NOT_COMPLETED_REACTED`) và history (`independent_retest_count == 2`, visit-1 `completed_reacted` giữ nguyên 3 mốc thời gian, visit-2 `closed_by_invalidation`) **đã có**; vế “**không rewind terminal snapshot**” mới chỉ đúng trên thực tế chứ **chưa được khóa** bằng assertion.

**Sửa (chỉ trong `T`, cùng node; fixture/probe giữ nguyên):** thêm hai precondition suy từ fixture, đặt ngay sau khi tính `terminal_at`:
- `_D1_INVALIDATION_INDEX == len(candles) - 1` ⇒ bản append **kết thúc đúng** tại bar breakdown, không có nến nào sau terminal;
- `terminal_at == _d1_close_at(candles, len(candles) - 1)` ⇒ cutoff terminal là **close cuối của chính snapshot**, tức không hồi dựng snapshot quá khứ từ terminal payload (đối lập trực tiếp với lỗi A3R3-03 đã sửa ở §A3.101).

Docstring nói rõ vế append-kết-thúc-tại-close và control là prefix thật. Không đổi assert contract, không đổi fixture, không thêm node.

**Giá trị đọc thật (read-only):**

```text
len(candles) - 1 = 43   invalidation_index = 43   → bằng nhau
terminal_at == close cuối của snapshot: True
prefix (control) vẫn: confirmed / broken False / invalidation_index None / visits 1 / close cuối 2026-02-12
```

**Command/kết quả thật (`node` = `tests/test_smc_gate72_fix_acceptance.py`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
116 tests collected in 0.58s                     (không đổi inventory; 0 lỗi collection)

python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer" -q --tb=long
1 failed in 0.29s
  → precondition mới + toàn bộ precondition cũ + **positive control prefix** đều PASS
    (đạt tới dòng fail nghĩa là mọi assert trước đã chạy)
  → assert đầu fail KHÔNG đổi: `enriched["lifecycle_status"] == "invalid"` → `assert 'confirmed' == 'invalid'`  (F03/R72-08)
  → các assert sau CHƯA chạy: `usable is False`, D1 `valid False`/`score 0`,
    loại trừ `D1_REACTION_NOT_COMPLETED_REACTED`

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k "r72_09" --tb=no
1 failed, 9 passed                               (A3-060 positive vẫn GREEN)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
66 failed, 50 passed                             (không đổi)

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
13 failed, 3 passed                              (không đổi; probe không sửa)
```

**Phân loại:** **RED giữ nguyên** đúng gap **F03/R72-08** (F05/A-D04 phía sau); lượt này chỉ khóa thêm vế “append kết thúc tại invalidation close, không rewind”, không sinh RED/GREEN mới.

**Hash mới file acceptance:** `B1B2A6DFA86F68A9C9BAEBBF6E3346D92A4E0E6172235CF6E9A4468CD6A9DDB3`
(§A3.101 ghi `AD95E1F0…`; các hash trước giữ nguyên làm lịch sử).

**Phạm vi:** chỉ `T` (một hàm test) + `M` (dòng theo dõi R72-09/A3-061) + `L` (dòng checklist A3-061 và mục này) + `smc-task-72-fix-plan.md` (dòng A3-061 §8.5). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit; không thêm/xoá file.

**Kết luận mã A3-061:** hai phần **/a** (positive control bằng prefix thật) và **/b** (khóa bản append tại invalidation close, không rewind) đều xong và có bằng chứng ⇒ hàng A3-061 giữ **IMPLEMENTED**. Checkpoint A vẫn **CHANGES_REQUESTED**; R72-01…09 vẫn **OPEN**; mã kế tiếp theo review §4 là **A3-066**.

### A3.103 — Cutoff theo reclaim close, không theo open nến (A3-066/a; finding A3R3-04)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-04](smc-task-72-checkpoint-a-review-round3.md) — “lọc ở dòng1101/1106 dùng `sweep["time"]` (open) thay vì `reclaimed_at` (close); không được tính event chỉ mới mở ở cutoff là evidence đã biết”.

**Trạng thái vào lượt:** hai node A3-066 lọc evidence trước cutoff bằng `s["time"] <= cutoff`, tức **thời điểm mở** nến sweep. Nến mới chỉ mở tại cutoff chưa reclaim nên chưa phải bằng chứng mà lượt chạy có thể dùng.

**Sửa (chỉ trong `T`):** thêm helper `_reclaimed_by(sweep, cutoff)` trả `sweep["reclaimed_at"] <= cutoff` — cổng **bao gồm** tại đúng cutoff; thay cả hai bộ lọc (prefix và batch) sang helper này; thêm assert mọi event được tính là đã biết đều có `reclaimed_at <= cutoff`; thêm một assert khóa chính toán tử bao gồm (`reclaimed_at == cutoff` vẫn tính là đã biết) vì fixture không có event nằm đúng biên.

**Giá trị đọc thật (read-only):**

```text
cutoff = stamp(12) = 2026-09-01T12:00:00+00:00
prefix sweep idx10  time 10:00  reclaimed_at 11:00  → time<=cut True , reclaim<=cut True
batch  sweep idx10  time 10:00  reclaimed_at 11:00  → time<=cut True , reclaim<=cut True
=> fixture hiện không có event mở đúng cutoff, nên hai bộ lọc cho cùng kết quả;
   lượt này sửa tính đúng của oracle, không sinh RED/GREEN mới.
```

**Command/kết quả thật:**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=short -k "r72_01"
15 failed, 12 passed, 89 deselected

Đối chiếu trước/sau (bản tạm tests/_a3066_baseline_tmp.py hoàn nguyên đúng sửa đổi này):
trước 15 failed / 12 passed ; sau 15 failed / 12 passed
diff tập node FAILED: IDENTICAL (15 = 15) ⇒ không regression, không đổi hàng A3-066.
```

**Phân loại:** không đổi; 15 RED của nhóm `r72_01` giữ nguyên đúng loại `implementation` (F06 cho phần canonical `records`, F02/F01.1 cho phần metadata) đã ghi ở §A3.93.

**Hash T sau bước này:** `A969A7BB269FF662420EC2BC25E59E1994E33F8C07DE16BCA9BB7EF721559086`
(§A3.102 ghi `B1B2A6DF…`; các hash trước giữ nguyên làm lịch sử).

**Phạm vi:** chỉ `T` (một helper + một hàm test) + `L` (mục này). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit.

**NEXT_TASK:** A3-066/b — canonical record có bằng chứng thật.

### A3.104 — Canonical pool record có bằng chứng thật (A3-066/b; finding A3R3-04)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** review A lần3 §2/A3R3-04 — “hai node chỉ kiểm numeric pool levels, swing ID và `source_pool_id` của sweep; **không** đọc/đối chiếu `records.pool_id/source_ids/sources/usable_at`” và “bổ sung vào các node hiện có assertions record tồn tại/không rỗng, đúng source/time từ fixture”.

**Trạng thái vào lượt:** node `test_r72_01_pool_sweep_evidence_survives_future_bars` chỉ kiểm `prefix_pools["swing_lows"] == [99.5]` (numeric projection) và `swing_id`; payload thật **không có `records`** (diagnostic: `has records: False` cho cả prefix và batch).

**Sửa (chỉ trong `T`):** hai helper mới dùng chung cho /b…/e —
- `_pool_record_for(pools, kind, source_ids)` — chọn **đúng một** record theo `kind` + **lineage** `source_ids`, **không** theo vị trí list và **không** theo level numeric; khi thiếu `records` nó báo cáo tập `(kind, source_ids)` thực có thay vì so rỗng;
- `_assert_pool_record_matches_source(record, swing)` — `pool_id` là chuỗi không rỗng, `sources` mang đúng `swing_id`/`confirmed_at`/`provisional=False` của swing fixture, `usable_at` là chuỗi không rỗng, **`record["usable_at"] == max(usable_at các source của chính record)`** (luật max của A3-005), và `usable_at >= confirmed_at`.

`_batch_pools` đổi tên thành `batch_pools` (không đổi hành vi) để đối chiếu record hai lượt. Khối canonical đặt **cuối** node để toàn bộ assert causal phía trước vẫn thực thi.

**Không khoá quy tắc chưa chốt:** quy tắc fallback `confirmed_at → usable_at` cho swing thật vẫn **chưa có quyết định** (§A3.9, §A3.12) nên oracle CỐ Ý không assert `usable_at == confirmed_at`; chỉ khoá luật max nội tại của contract và bound không thể sai (`usable >= confirmed_at`).

**Bằng chứng fixture/precondition độc lập (read-only):** batch có 2 swing low — idx4 level `99.5` `swing_id smcs-a3eedff40ca702ee7827` `confirmed_at 2026-09-01T07:00Z`, idx10 level `99.0` `swing_id smcs-58ee51f5deef9d5dfa93`. Chọn theo lineage nên không thể lẫn record của idx10 (đó là lý do dùng selector chứ không dùng `records[0]`).

**Command/kết quả thật:**

```text
python -m pytest "tests/test_smc_gate72_fix_acceptance.py::test_r72_01_pool_sweep_evidence_survives_future_bars" -q --tb=long
1 failed in 0.66s
  assert đầu fail: AssertionError: ('swing_low', ['smcs-a3eedff40ca702ee7827'], [])
                   assert 0 == 1   (trong `_pool_record_for`, dòng 1164)
  → toàn bộ precondition + causal parity phía trước PASS (fail nằm ở khối cuối)
  → các assert sau CHƯA CHẠY: `_assert_pool_record_matches_source`,
    `batch_record["pool_id"] == prefix_record["pool_id"]`, kind/source_ids/usable_at/level parity

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_01"
16 failed, 11 passed, 89 deselected        (trước: 15 failed / 12 passed)

diff tập node FAILED so với baseline: chỉ thêm đúng 1 dòng
  > test_r72_01_pool_sweep_evidence_survives_future_bars      (GREEN → RED)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
67 failed, 49 passed                       (trước LÔ 1: 66 failed / 50 passed)
```

**Phân loại:** RED **mới** đúng loại `implementation` — **F06/R72-01** (`records` canonical chưa được `core/` phát ra), cùng chữ ký `assert 0 == 1` như hai node tiền lệ `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy/sell]` đã ghi ở §A3.93 dòng 12–13. **Không** phải BLOCKED, **không** sửa core để làm xanh. Node đã GREEN trước đó nay RED là **chủ ý**: equality cũ chỉ có nghĩa cho swing/legacy evidence, chưa chứng minh canonical pool→sweep.

**Hash T sau bước này:** `99905D6D3393131543ADC7142FC78288827BF14CFB68BAF7D6955D76F0B666AA`
**Hash T trước bước này:** `A969A7BB269FF662420EC2BC25E59E1994E33F8C07DE16BCA9BB7EF721559086` (§A3.103)

**Phạm vi:** chỉ `T` (2 helper + 1 hàm test) + `L` (mục này). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit.

**NEXT_TASK:** A3-066/c — prefix/batch parity nối `source_pool_id`/provenance của sweep với canonical pool record.

### A3.105 — Nối `source_pool_id` của sweep với canonical pool record (A3-066/c; finding A3R3-04)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** review A lần3 §2/A3R3-04 — “nối ID/lineage sang sweep; so cùng causal pool qua prefix/batch/rolling” và “So các record liên quan, **không** đòi toàn bộ batch giống prefix khi thực sự có nguồn mới”.

**Trạng thái vào lượt:** sau /b, `source_pool_id` của sweep vẫn **chưa** được đối chiếu với `records.pool_id`; `_pool_causal_evidence` chỉ so sweep-vs-sweep (hai output có thể cùng sai).

**Sửa (chỉ trong `T`, cùng node):** thêm khối cuối node `test_r72_01_pool_sweep_evidence_survives_future_bars`:
- với **cả hai** lượt (prefix và batch): `sweep["source_swing_id"] == swing["swing_id"]`, `record["source_ids"] == [swing["swing_id"]]`, **`sweep["source_pool_id"] == record["pool_id"]`**, `record["level"] == swing["level"] == expected_level` — expected lấy từ **fixture**, không chỉ so hai output;
- chọn pool **khác cùng kind** trong batch (swing low idx10 level `99.0`) theo lineage ⇒ `other_record["level"] == other_swing["level"] != expected_level`, `other_record["pool_id"] != batch_record["pool_id"]`, và `batch_at_cutoff[0]["source_pool_id"] != other_record["pool_id"]` — chứng minh chọn theo lineage **không** lẫn pool mới, và sweep vẫn gắn pool của pivot chứ không phải pool cuối/gần nhất.

**Không khoá field ngoài contract:** `source_pool_kind` **không** xuất hiện trong bất kỳ tài liệu interface nào (chỉ có trong `core/smc_context.py:4506` và đang bằng `kind` của **sweep**, không phải kind của pool) nên oracle **không** assert field này. Cũng không assert `usable_at <= reclaimed_at` (đó là gate A-D01/F07 thuộc A3-042/043, ngoài phạm vi A3-066).

**Bằng chứng gốc RED (read-only, `core/smc_context.py:4408-4415`):** `pool_id(kind, level, source)` fallback `source.get("pool_id", source.get("swing_id"))` ⇒ `source_pool_id` hiện **bằng `source_swing_id`**; nhánh cuối còn sinh ID từ **`level`** (`f"{kind}:{level:.15g}"`) — đúng thứ A-D06 (“không sinh ID theo level”) cấm. Đây là gap **F06**.

**Fixture/precondition kiểm độc lập (read-only):**

```text
prefix sweep.source_swing_id == pivot.swing_id : True
batch  sweep.source_swing_id == pivot.swing_id : True
pivot level == expected 99.5                  : True
other batch low: index 10 level 99.0 (≠ 99.5) ; swing_id khác pivot : True
core hiện tại: sweep.source_pool_id == sweep.source_swing_id : True
```

**Command/kết quả thật:**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=line -k "r72_01"
16 failed, 11 passed, 89 deselected        (không đổi so với sau /b)
  assert đầu fail giữ nguyên: `assert 0 == 1` tại `_pool_record_for` (dòng 1388)
  → khối /c CHƯA CHẠY (fail-fast): `sweep["source_pool_id"] == record["pool_id"]`,
    selector pool thứ hai theo lineage, và 2 parity check `other_record`
```

**Phân loại:** giữ nguyên RED **F06/R72-01** đã sinh ở /b; lượt này **không** sinh RED/GREEN mới (node đã RED từ trước, khối mới nằm sau điểm fail). Đã kiểm độc lập mọi precondition của khối mới nên khi F06 được implement, các assert này chạy được thật.

**Hash T sau bước này:** `64728EAD1779D41D726CCC5FD1D9973E5BCC492234272EAA76AE4E9561CD1D39`
**Hash T trước bước này:** `99905D6D3393131543ADC7142FC78288827BF14CFB68BAF7D6955D76F0B666AA` (§A3.104)

**Phạm vi:** chỉ `T` (một hàm test) + `L` (mục này). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit.

**NEXT_TASK:** A3-066/d — rolling-index parity giữ identity/source/usable time.

### A3.106 — Rolling-index parity giữ canonical pool (A3-066/d; finding A3R3-04)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** review A lần3 §2/A3R3-04 — “so cùng causal pool qua prefix/batch/rolling” và §4 hàng A3-066 — “permutation/rolling index đúng”.

**Trạng thái vào lượt:** node `test_r72_01_pool_sweep_identity_survives_rolling_index` chỉ kiểm `swing_id`/`level`/`confirmed_at` của **swing** và `_pool_causal_evidence` của **sweep**; chưa đọc canonical `records`, chưa nối `source_pool_id` → `pool_id`.

**Sửa (chỉ trong `T`, cùng node):** thêm khối cuối node (sau parity causal, để parity cũ vẫn chạy):
- lấy record theo **lineage** cho pivot ở **cả** batch (idx4) và rolled (idx3) bằng `_pool_record_for`, rồi `_assert_pool_record_matches_source` cho từng bên;
- **`rolled_record["pool_id"] == batch_record["pool_id"]`**, `source_ids` bằng nhau và bằng `[batch_swing["swing_id"]]`, `kind == "swing_low"`, `level` bằng nhau và bằng level fixture, **`usable_at` bằng nhau** ⇒ index dịch nhưng identity/source/usable time **không** đổi;
- nối sweep ↔ record ở cả hai lượt: `batch_sweep["source_pool_id"] == batch_record["pool_id"]`, `rolled_sweep["source_pool_id"] == rolled_record["pool_id"]`, và hai `source_pool_id` bằng nhau.

**Bằng chứng fixture/precondition độc lập (read-only):**

```text
pivot index batch/rolled     : 4 / 3          (index dịch đúng 1)
same swing_id                : True
same confirmed_at            : True
same level 99.5              : True
rolled pools swing_lows      : [99.5, 99.0]
records present batch/rolled : False / False   ← gốc RED F06
```

**Command/kết quả thật:**

```text
python -m pytest "tests/...::test_r72_01_pool_sweep_identity_survives_rolling_index" -q --tb=short
1 failed in 0.69s
  assert đầu fail: AssertionError: ('swing_low', ['smcs-a3eedff40ca702ee7827'], [])
                   assert 0 == 1   (tại `_pool_record_for`, dòng 1164)
  → toàn bộ precondition (timestamp rolled == batch[1], pivot identity, sweep index dịch 1,
    `_pool_causal_evidence` parity) PASS; fail nằm ở khối canonical cuối
  → các assert sau CHƯA CHẠY: `_assert_pool_record_matches_source` hai bên, pool_id/source_ids/
    kind/level/usable_at parity, ba assert nối `source_pool_id` ↔ `pool_id`

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_01"
17 failed, 10 passed, 89 deselected        (sau /c: 16 failed / 11 passed)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
68 failed, 48 passed                       (sau /c: 67 failed / 49 passed)
```

**Phân loại:** RED **mới** trên node thứ hai, cùng loại `implementation` **F06/R72-01** (thiếu `records` canonical), chữ ký `assert 0 == 1` tại cùng helper. Node này trước đó GREEN; chuyển RED là **chủ ý** theo đúng review (equality cũ chỉ chứng minh swing/legacy evidence). Không BLOCKED, không sửa core.

**Hash T sau bước này:** `3CC6DBED34A0950D3F59BED35AB4A7892C0970395D47114DEAA4C8C1ECCC9305`
**Hash T trước bước này:** `64728EAD1779D41D726CCC5FD1D9973E5BCC492234272EAA76AE4E9561CD1D39` (§A3.105)

**Phạm vi:** chỉ `T` (một hàm test) + `L` (mục này). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit.

**NEXT_TASK:** A3-066/e — source permutation (đảo thứ tự cùng tập nguồn không đổi canonical identity/source/usable time).

### A3.107 — Permutation nguồn pool không đổi canonical identity (A3-066/e; finding A3R3-04)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** review A lần3 §2/A3R3-04 — “Chưa có biến thể permutation nguồn pool” và “permutation cùng nguồn giữ identity/usable time”. §4 hàng A3-066 xác nhận điều kiện xong: “permutation/rolling/cutoff đúng”.

**Trạng thái vào lượt:** chưa có node nào đảo thứ tự **nguồn pool**; các node A3-044 đều truyền nguồn theo một thứ tự cố định.

**Sửa (`T`):** **1 node mới** `test_r72_01_pool_identity_survives_source_permutation` (không parameterize theo side — trục kiểm là *thứ tự input*, không phải chiều), **reuse** fixture equal-pool và helper sẵn có (`_probe.candles`, `detect_liquidity_pools`, `_pool_record_for`):
- fixture 2 nguồn equal `source-a` (idx0, `pivot_time` stamp(0), usable stamp(1)) và `source-b` (idx1, level 100.05, `pivot_time` stamp(1), usable stamp(2));
- **precondition thật**: hai thứ tự có danh sách `swing_id` **khác nhau** (permutation không rỗng) và `pivot_time(a) < pivot_time(b)` (thứ tự causal xác định). ⚠️ **ĐÍNH CHÍNH (A3-066/e-r1, §A3.109):** mô tả “`source_ids` giữ **thứ tự causal**” trong mục này **SAI** so với M dòng pool identity (`kind + sorted source_ids + source causal records`). Quy tắc đúng là **`source_ids` sort ổn định**; node đã được sửa lại theo §A3.109.
- chạy `detect_liquidity_pools` cho **cả hai** thứ tự; chọn record theo **kind + lineage causal** `["source-a","source-b"]` (không theo vị trí list);
- mỗi lượt: `source_ids == ["source-a","source-b"]`, `usable_at == max(usable) == stamp(2)` (tính **từ fixture**), numeric projection `equal_lows == [100.025]` giữ nguyên;
- đối chiếu hai lượt: **`pool_id` bằng nhau**, `source_ids` bằng nhau, `usable_at` bằng nhau, `kind == "equal_low"`, `level` bằng nhau và bằng trung bình fixture; `usable_at == max(usable_at các source của chính record)`.
- **Không** thêm quy tắc ưu tiên pool, **không** assert số lượng sweep hay dedupe (đúng giới hạn review).

**Bằng chứng fixture/precondition độc lập (read-only):**

```text
causal   | equal_lows = [100.025] | swing_lows = [100.0, 100.05]
reversed | equal_lows = [100.025] | swing_lows = [100.0, 100.05]   ← projection numeric không đổi
expected level = 100.025 ; expected usable_at = 2026-09-01T02:00:00+00:00 ; pivot_time a<b : True
fixture phát cả swing pool (100.0/100.05) lẫn equal pool ⇒ chọn theo `kind` là bắt buộc,
không thể chọn nhầm bằng vị trí hay level.
```

**Command/kết quả thật:**

```text
python -m pytest "tests/...::test_r72_01_pool_identity_survives_source_permutation" -q --tb=short
1 failed in 0.72s
  assert đầu fail: AssertionError: ('equal_low', ['source-a', 'source-b'], [])
                   assert 0 == 1   (tại `_pool_record_for`, dòng 1164, lượt "causal")
  → precondition (permutation khác nhau, thứ tự causal) PASS
  → các assert sau CHƯA CHẠY: pool_id/source_ids/usable_at/kind/level parity giữa hai thứ tự
    và luật max usable_at

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
117 tests collected in 0.14s              (trước: 116 node — thêm đúng 1 node, 0 lỗi collection)

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_01"
18 failed, 10 passed, 89 deselected       (sau /d: 17 failed / 10 passed)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
69 failed, 48 passed                      (sau /d: 68 failed / 48 passed; tổng 117 = 69 + 48)
```

**Phân loại:** RED **mới** trên node mới, đúng loại `implementation` **F06/R72-01** (`records` canonical chưa có), chữ ký `assert 0 == 1`. Không BLOCKED, không sửa core.

**Hash T sau bước này (hash "trước /e-r1" — đã bị §A3.109 thay):** `21768F9473486CBABCC74DD0BD23D5F67E7C4071AB27A539098E727CF25DEBD0`
**Hash T trước bước này:** `3CC6DBED34A0950D3F59BED35AB4A7892C0970395D47114DEAA4C8C1ECCC9305` (§A3.106)

**Phạm vi:** chỉ `T` (1 node mới) + `L` (mục này). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit.

**Kết luận cụm A3-066:** đủ **năm** phần /a…/e (§A3.103…§A3.107).

### A3.108 — Tổng kết LÔ 1: A3-066/a…/e (finding A3R3-04)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** review A lần3 §2/A3R3-04 + §4 hàng “Bổ sung canonical pool parity”.

**Phạm vi đã sửa:** chỉ `tests/test_smc_gate72_fix_acceptance.py` (`T`) + ba tài liệu `L`/`M`/`P`. **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit. Đã xác minh lại 7 fingerprint bảo vệ (5 core + probe + golden) **khớp nguyên** hash ledger.

| Phần | Trạng thái | Node/helper | Thay đổi chính | Bằng chứng |
|---|---|---|---|---|
| **/a** | XONG | `_reclaimed_by` + `test_r72_01_pool_sweep_evidence_survives_future_bars` | Lọc evidence trước cutoff theo **`reclaimed_at`** (close), bỏ `time` (open); assert mọi event đã biết có close ≤ cutoff; assert toán tử **bao gồm** tại đúng cutoff | §A3.103 |
| **/b** | XONG | `_pool_record_for`, `_assert_pool_record_matches_source`, node prefix/batch | Record tồn tại + `pool_id` không rỗng + `sources`/`confirmed_at`/`provisional` khớp swing fixture + luật max `usable_at` + bound `≥ confirmed_at`; chọn theo **kind + lineage** | §A3.104 |
| **/c** | XONG | cùng node prefix/batch | Nối `sweep["source_pool_id"] == record["pool_id"]` cho **cả** prefix và batch; pool thứ hai cùng kind phân biệt bằng lineage | §A3.105 |
| **/d** | XONG | `test_r72_01_pool_sweep_identity_survives_rolling_index` | Rolling idx 4→3 giữ **cùng** `pool_id`/`source_ids`/`usable_at`/`kind`/`level`; nối sweep↔record cả hai lượt | §A3.106 |
| **/e** | XONG | **node mới** `test_r72_01_pool_identity_survives_source_permutation` | Đảo thứ tự 2 nguồn (precondition khẳng định thứ tự **thật sự** đổi) giữ `pool_id`/`usable_at`; **`source_ids` khóa theo danh sách ĐÃ SORT ổn định** (đính chính A3-066/e-r1 — xem §A3.109), provenance từng source tra theo `swing_id`; không assert số sweep/pool priority/dedupe | §A3.107, §A3.109 |

**Thay đổi so với đầu lô:**

```text
nhóm r72_01        : 15 failed / 12 passed  →  18 failed / 10 passed
file acceptance    : 116 node, 66 failed / 50 passed  →  117 node, 69 failed / 48 passed
hai node A3-066    : GREEN → RED **chủ ý** (trước đây xanh nhờ equality swing/legacy, chưa chứng minh canonical pool→sweep)
node mới /e        : +1 node
collect-only       : 117 collected, 0 lỗi collection
```

**RED còn lại của cụm:** cả ba node (`...future_bars`, `...rolling_index`, `...source_permutation`) **RED đúng loại `implementation` — F06/R72-01**, chữ ký `assert 0 == 1` tại `_pool_record_for` do `core/` chưa phát `records`; `source_pool_id` hiện bằng `source_swing_id` (fallback `core/smc_context.py:4408-4415`, nhánh cuối còn sinh ID từ `level` — điều A-D06 cấm). Đây là **EXPECTED_IMPLEMENTATION_RED**, không phải BLOCKED; **không** sửa core để làm xanh. Các assert phía sau điểm fail ghi rõ **CHƯA CHẠY** ở từng mục.

**Tài liệu đã cập nhật:** `L` (mục §A3.103…§A3.108 + hàng checklist A3-066), `M` (hai hàng tracking A3-066 + hàng mới cho node /e + ô §4 “Pool/sweep → Integration/parity”), `P` (hàng A3-066 §8.6). **Hash T cuối (trước /e-r1):** `21768F9473486CBABCC74DD0BD23D5F67E7C4071AB27A539098E727CF25DEBD0`. **Sau A3-066/e-r1:** `67E47D6E5CFEDE9236BA684230AC44D80A76A2245AD2A30D792C331FA93BC2F2` — xem §A3.109.

**Trạng thái mã A3-066:** đủ cả năm phần /a…/e, đối chiếu đúng R và có bằng chứng ⇒ chuyển **CHANGES_REQUESTED → IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`)**.
**Checkpoint A** vẫn **CHANGES_REQUESTED**; R72-01…09 vẫn **OPEN**; **không** tự PASS checkpoint, **không** CLOSED finding nào.

**Blocker:** không có.

**NEXT_TASK = A3-043/a** (finding A3R3-05, cô lập canonical equal-pool temporal seam; đồng bộ A3-039/040/041) — **chưa thực hiện** trong lô này.

### A3.109 — Đính chính A3-066/e: `source_ids` sort ổn định, không phải thứ tự causal (A3-066/e-r1)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** review finding **A3-066/e-r1** — node /e khóa `source_ids` theo “thứ tự causal”, nhưng M dòng **pool identity** quy định `pool_id` dựa trên `kind + sorted source_ids + source causal records`. Hai quy tắc này **mâu thuẫn**, và fixture cũ (`source-a` pivot sớm, `source-b` pivot muộn) có **causal order TRÙNG sorted order** ⇒ node **không phân biệt được** hai quy tắc, không chứng minh được điều nó tuyên bố.

**Trạng thái vào lượt:** node /e (A3-066/e) khẳng định `source_ids == ["source-a","source-b"]` với fixture mà causal order = sorted order = `["source-a","source-b"]`. Một implementation theo **hoặc** quy tắc nào cũng cho cùng kết quả ⇒ oracle **yếu**.

**Sửa (chỉ trong `T`, cùng node; không đổi `core/`):**
1. Đổi fixture để **hai quy tắc cho kết quả khác nhau**: `source-z` (idx0, `pivot_time stamp(0)`, usable `stamp(1)`) pivot **sớm nhất** nhưng sort **cuối**; `source-a` (idx1, level `100.05`, `pivot_time stamp(1)`, usable `stamp(2)`) pivot **muộn hơn** nhưng sort **đầu**.
2. Giữ nguyên việc **đảo input order** ở hai lượt; đổi tên lượt thành `as_given` / `reversed`.
3. Khóa **`source_ids == sorted(...) == ["source-a","source-z"]`** bất kể input order (chọn record và assert đều dùng danh sách sort).
4. Bổ sung precondition **phân biệt được**: `causal_ids == ["source-z","source-a"]`, `sorted_ids == ["source-a","source-z"]`, và `causal_ids != sorted_ids`.
5. Kiểm **từng source** giữ đúng `confirmed_at`/`usable_at`/`provisional` **tra theo `swing_id`** (`by_id`), không theo vị trí list `sources`; kèm `len(record["sources"]) == len(source_ids)` để bản ghi trùng không lọt qua dict.
6. Giữ `pool_id`/`kind`/`level`/`usable_at` giống nhau ở hai lượt và luật max `usable_at`. **Không** assert pool priority, số sweep, dedupe (đúng giới hạn review).
7. Đổi docstring helper `_pool_record_for` từ “causal source lineage” → “**sorted source-ID lineage**”.

**Bằng chứng độc lập — logic assertion THẬT SỰ phân biệt hai quy tắc** (bắt buộc, vì assertion canonical không chạy được khi `records` vắng):

```text
causal order      : ['source-z', 'source-a']
sorted id order   : ['source-a', 'source-z']
two rules differ  : True

numeric projection (order-independent):
  as_given  equal_lows=[100.025] swing_lows=[100.0, 100.05]
  reversed  equal_lows=[100.025] swing_lows=[100.0, 100.05]

chạy `_pool_record_for` trên record synthetic ĐÚNG contract:
  source_ids sort  (đúng) -> ACCEPTED
  source_ids causal (sai)  -> REJECTED
  tra source theo swing_id khi list `sources` bị đảo: source-z usable stamp(1) True ; source-a usable stamp(2) True
```

**Command/kết quả thật:**

```text
python -m pytest "tests/...::test_r72_01_pool_identity_survives_source_permutation" -q --tb=long
1 failed in 0.69s
  assert đầu fail: AssertionError: ('equal_low', ['source-a', 'source-z'], [])
                   assert 0 == 1   (tại `_pool_record_for`, dòng 1165)
  → precondition permutation PASS (2 thứ tự khác nhau, causal ≠ sorted, hai quy tắc khác nhau)
  → các assert sau CHƯA CHẠY: `record["source_ids"] == expected_source_ids`,
    `record["usable_at"] == max == stamp(2)`, `equal_lows == [100.025]`,
    parity hai lượt (`pool_id`/`source_ids`/`usable_at`/`kind`/`level`),
    vòng lặp từng-source tra theo `swing_id` + luật max `usable_at`

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
117 tests collected in 0.14s           (không đổi inventory; 0 lỗi collection)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_01"
18 failed, 10 passed, 89 deselected    (không đổi)
git diff --check -> clean
```

**Phân loại:** RED giữ nguyên **F06/R72-01**; `records` chưa có ⇒ **EXPECTED_IMPLEMENTATION_RED**. Lượt này không sinh RED/GREEN mới, chỉ làm oracle **đúng và phân biệt được**.

**Phạm vi:** chỉ `T` (một hàm test + một docstring helper) + `M` (hàng tracking /e, dòng interface `source_ids`, ô §4 Pool/sweep) + `L` (mục này + đính chính §A3.107/§A3.108 + hàng checklist A3-066) + `P` (hàng A3-066 §8.6). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit.

**Hash T sau bước này:** `67E47D6E5CFEDE9236BA684230AC44D80A76A2245AD2A30D792C331FA93BC2F2`
**Hash T trước bước này (tức hash "trước /e-r1", đã bị thay bởi hash cuối ở trên):** `21768F9473486CBABCC74DD0BD23D5F67E7C4071AB27A539098E727CF25DEBD0` (§A3.107/§A3.108)

**Trạng thái mã A3-066:** giữ **IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED`)** — /e-r1 đã có bằng chứng đạt yêu cầu (fixture phân biệt hai quy tắc + assertion khóa sort order + provenance từng source theo `swing_id`).

**NEXT_TASK = A3-043/a** — **chưa thực hiện** trong lượt này.

### A3.110 — Cô lập negative equal-pool temporal, bỏ assert toàn bộ `swept_lows` (A3-043/a; finding A3R3-05)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-05](smc-task-72-checkpoint-a-review-round3.md) — “A3-043 muốn reject **equal pool** chưa đủ hai source, nhưng assert toàn bộ `swept_lows == []`” và “Negative chỉ chặn equal pool chưa usable; giữ control riêng cho single-source hợp lệ. Positive khóa equal record/time/mean tương ứng, không phụ thuộc list position. **Không** thêm quy tắc phát nhiều event, dedupe hay pool priority ở lượt này.”

**Trạng thái vào lượt:** node `test_r72_01_equal_pool_usable_time_is_max_of_both_sources` kết thúc bằng `assert sweeps["swept_lows"] == []`. Assertion này **quá rộng**: fixture còn có pool **single-source** của `source-a` (level `100`, usable `stamp(1)`) — nguồn này usable **trước** close `stamp(2)` nên sweep của nó là **hợp lệ**; oracle cũ vô tình khóa luôn số lượng event / pool priority.

**Sửa (chỉ trong `T`, cùng node; fixture/geometry/precondition giữ nguyên):**
1. Bỏ `assert sweeps["swept_lows"] == []`.
2. Lọc danh sách chỉ lấy event **của target equal pool** bằng **đúng level** đã tính độc lập từ hai source:
   `equal_pool_events = [sweep for sweep in sweeps["swept_lows"] if sweep["level"] == expected_level]` — **không** dùng vị trí list, **không** assert tổng số sweep, **không** pool priority/dedupe.
3. Negative chỉ assert `equal_pool_events == []`.
4. Thêm precondition chống khớp nhầm: `assert expected_level not in {source_a["level"], source_b["level"]}` ⇒ bộ lọc theo level **không thể** bắt nhầm event single-source.
5. Giữ `assert sweeps["swept_highs"] == []` (fixture khai `highs: []` nên không thể có pool SELL — không phải over-lock).
6. **Không** thêm `records` canonical vào node này (F06 còn thiếu sẽ che mất RED temporal F07 cần thấy) và **không** thêm single-source control — đó là **A3-043/b** riêng.

**Giá trị đọc thật (read-only, trước sửa):**

```text
equal_lows = [100.025] ; swing_lows = [100.0, 100.05]
expected_level = 100.025 ; khác cả 100.0 lẫn 100.05 ⇒ lọc theo level là phân biệt được
swept_lows hiện có ĐÚNG 1 event: idx 1 | level 100.025 | time 01:00 | reclaimed_at 02:00
event_close = 02:00 ; pool_usable_at(max) = 03:00  ⇒ equal pool CHƯA usable khi nến đóng
```

**Command/kết quả thật:**

```text
python -m pytest "tests/...::test_r72_01_equal_pool_usable_time_is_max_of_both_sources" -q --tb=long
1 failed in 0.66s
  assert đầu fail: `assert equal_pool_events == []`
                   AssertionError: assert [{'depth': 0.525…, 'index': 1, …}] == []
                   (dòng 1694)
  → mọi precondition PASS (equal pool tồn tại; hai usable_at khác nhau; `early < event_close < pool_usable_at`;
    geometry excursion/reclaim; precondition phân biệt level)
  → LỖI KHÔNG CÒN ở assertion toàn bộ `swept_lows`; nay nằm đúng ở assertion target equal pool

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
117 tests collected in 0.14s          (không đổi inventory; 0 lỗi collection)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_01"
18 failed, 10 passed, 89 deselected   (không đổi)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
69 failed, 48 passed                  (không đổi — node vốn đã RED, nay RED đúng lý do)
git diff --check -> clean
```

**Phân loại:** **RED giữ nguyên đúng loại `implementation` — F07** (gate A-D01 `usable_at <= reclaimed_at` chưa được implement: equal pool usable `stamp(3)` nhưng core vẫn emit event tại reclaim `stamp(2)`). Lượt này chỉ **đúng hóa oracle**, không sinh RED/GREEN mới.

**Oracle không còn cấm single-source sweep hợp lệ:** sau lượt này, một implementation F07 đúng có thể vừa chặn event của equal pool (usable `stamp(3) > close stamp(2)`) vừa **hợp lệ** phát event cho pool single-source của `source-a` (usable `stamp(1) <= close stamp(2)`) mà node này **vẫn xanh** — điều oracle cũ không cho phép. Control riêng cho vế đó được để **A3-043/b**.

**Hash T sau bước này:** `CCD01CA91690AFBBD0CD686B8CC48F4DA4E2919FB7C4C96D9AB8D53530A47708`
**Hash T trước bước này:** `67E47D6E5CFEDE9236BA684230AC44D80A76A2245AD2A30D792C331FA93BC2F2` (§A3.109)

**Phạm vi:** chỉ `T` (một hàm test) + `P` (hàng A3-043 §8.5) + `M` (hàng tracking node + ô §4 Pool/sweep) + `L` (mục này + hàng checklist A3-043). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit.

**Trạng thái mã A3-043:** **/a IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED` F07)**; mã tổng thể vẫn **CHANGES_REQUESTED**, phần **/b vẫn OPEN** (single-source control + đồng bộ A3-039/040/041 chưa làm).

**NEXT_TASK = A3-043/b** — **chưa thực hiện** trong lượt này.

### A3.111 — Single-source control: sweep hợp lệ mà negative /a không được cấm (A3-043/b; finding A3R3-05)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-05](smc-task-72-checkpoint-a-review-round3.md) — “Thiếu source cho equal pool không làm pool đơn hợp lệ mất eligibility” và “Negative chỉ chặn equal pool chưa usable; **giữ control riêng cho single-source hợp lệ**”.

**Trạng thái vào lượt:** sau A3-043/a, negative đã được thu hẹp về đúng target equal pool, nhưng **chưa có node nào chứng minh** rằng sweep single-source là hợp lệ — tức vế “được phép” mới chỉ được suy luận, chưa được khóa.

**Sửa (`T`):** **1 node mới** `test_r72_01_single_source_pool_usable_before_sweep_close_is_accepted`, dùng **đúng geometry H1 của A3-043/a** (nến idx1 `(100.3,100.5,99.5,100.3)`) nhưng **chỉ khai một low source** `source-a` — level `100.0`, `confirmed_at = usable_at = stamp(1)`, non-provisional; `tick=0.1`, `atr=1.0`; gọi `detect_liquidity_pools` rồi `detect_liquidity_sweeps`.

**Assertions (đúng danh sách yêu cầu, không thêm):**
1. Nguồn `confirmed`/`usable`/non-provisional và `stamp(1) < stamp(2)` (usable **trước** close nến sweep).
2. Geometry thật: `low 99.5 < 100 − excursion 0.2` và `close 100.3 > 100`.
3. `equal_lows == []` và `swing_lows == [100.0]` — một nguồn không thể tạo equal pool.
4. Lọc event theo **level `100.0`**, không theo vị trí list.
5. Có **ít nhất một** event target, và tồn tại event khớp `index 1`, `reclaimed_at stamp(2)`, `source_swing_id "source-a"`.
6. **Không** assert tổng số `swept_lows`, pool priority hay dedupe; **không** dùng/đòi canonical `records`.

**Bằng chứng fixture/precondition độc lập (read-only):**

```text
equal_lows = []            swing_lows = [100.0]        records present: False
excursion 0.2 : low 99.5 < 100 − 0.2 = True ; close 100.3 > 100 = True
stamp(1) < stamp(2) = True
swept_lows count = 1 → idx 1 | level 100.0 | time 01:00 | reclaimed_at 02:00 |
                       source_swing_id "source-a" | kind swept_low | side buy | excursion_buffer 0.2
```

**Command/kết quả thật:**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
118 tests collected in 0.55s          (trước: 117 → thêm đúng 1 node, 0 lỗi collection)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --tb=no -v -k "equal_pool_usable_time_is_max_of_both_sources or single_source_pool_usable_before_sweep_close_is_accepted"
  test_r72_01_equal_pool_usable_time_is_max_of_both_sources            FAILED   (RED — F07, /a)
  test_r72_01_single_source_pool_usable_before_sweep_close_is_accepted PASSED   (GREEN, /b)
  1 failed, 1 passed, 116 deselected

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_01"
18 failed, 11 passed, 89 deselected   (trước: 18 failed / 10 passed — +1 GREEN)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
69 failed, 49 passed                  (trước: 69 failed / 48 passed; tổng 118 = 69 + 49)
git diff --check -> clean
```

**Phân loại:** **GREEN** — không sinh RED. Không sửa `core/`.

**Vì sao control này quan trọng:** negative A3-043/a **không** được cấm toàn bộ `swept_lows`, vì implementation F07 đúng có thể vừa chặn event của equal pool (usable `stamp(3) > close stamp(2)`) **vừa hợp lệ** phát event cho pool single-source của `source-a` (usable `stamp(1) <= close stamp(2)`). Node /b chạy **đúng phần được phép đó** và xác nhận nó vẫn được nhận ⇒ hai node /a và /b cùng tồn tại mà không mâu thuẫn, và oracle /a không còn khóa cardinality/pool priority.

**Hash T sau bước này:** `AC623CC3BDC4C6A20709880AD6C9C92785E5E1BECA2752CB38A641F6B42AAD74`
**Hash T trước bước này:** `CCD01CA91690AFBBD0CD686B8CC48F4DA4E2919FB7C4C96D9AB8D53530A47708` (§A3.110)

**Phạm vi:** chỉ `T` (1 node mới) + `P` (hàng A3-043 §8.5) + `M` (hàng tracking node mới + hai ô §4 Pool/sweep) + `L` (mục này + hàng checklist A3-043). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit.

**Trạng thái mã A3-043:** **/a IMPLEMENTED (kèm `EXPECTED_IMPLEMENTATION_RED` F07)** + **/b IMPLEMENTED (GREEN)** ⇒ mã tổng thể chuyển **CHANGES_REQUESTED → IMPLEMENTED**. **A3-039/040/041 vẫn CHANGES_REQUESTED** — phần đồng bộ của chúng thuộc A3R3-05 nhưng **chưa làm** ở lượt này, **không** tự đóng.

**NEXT_TASK = A3-039/040/041** (đồng bộ cụm equal-pool temporal theo A3R3-05) — **chưa thực hiện**.

### A3.112 — Positive equal-pool temporal: bỏ khóa toàn list, đưa temporal seam lên trước canonical (A3-039 + A3-041; finding A3R3-05)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-05](smc-task-72-checkpoint-a-review-round3.md) — “Hai positive controls cũng bắt toàn bộ list có đúng một event và event đầu là equal mean… chưa có quyết định buộc 'equal luôn thắng/chỉ một event'” và “Positive khóa equal record/time/mean tương ứng, **không phụ thuộc list position**”.

**Trạng thái vào lượt:** node `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` khóa **toàn bộ** `swept_lows` bằng `assert [sweep["index"] for sweep in sweeps["swept_lows"]] == [1]` rồi lấy `sweeps["swept_lows"][0]` — tức khóa **số lượng event** và **thứ tự/priority** của detector, trong khi A3-039/A3-041 chỉ cần chứng minh **target equal pool** được sweep tại biên `usable_at == reclaimed_at`. Thêm nữa, block canonical `records` nằm **trước** phần temporal nên khi `records` còn thiếu (F06) **mọi assertion temporal không bao giờ chạy**: RED F06 che mất tín hiệu temporal.

**Sửa (chỉ trong `T`, cùng node; fixture/geometry/`expected_level` giữ nguyên):**
1. Bỏ `assert [...swept_lows...] == [1]` và `sweep = sweeps["swept_lows"][0]`.
2. Thay bằng lọc theo **target equal level + candle `index 1`**:
   `target_events = [s for s in sweeps["swept_lows"] if s["level"] == expected_level and s["index"] == 1]`;
   `assert target_events` (tồn tại ít nhất một) và `assert any(s["reclaimed_at"] == pool_usable_at for s in target_events)`.
   **Không** dùng vị trí list, **không** assert tổng số `swept_lows`, **không** pool priority/dedupe.
3. `pool_usable_at` chuyển lên tính **từ fixture** ở khối precondition, kèm `assert pool_usable_at == usable_at == _probe.stamp(2)` ⇒ seam bằng nhau được khóa tường minh.
4. Chuyển **toàn bộ** block canonical `records` xuống **cuối** node (sau temporal + `swept_highs`), giữ nguyên nội dung (`len(records) == 1`, `records[0]["usable_at"] == pool_usable_at`) — **không** xóa assertion canonical.
5. Giữ `assert sweeps["swept_highs"] == []` (fixture khai `highs: []`, không phải over-lock). Không thêm `source_pool_id` fallback, không sửa `core/`.

**Bằng chứng giá trị temporal đọc độc lập (read-only):**

```text
expected_level                 : 100.025
pool_usable_at (max 2 source)  : 2026-09-01T02:00:00+00:00 == stamp(2) : True
target_events count            : 1
   idx 1 | level 100.025 | reclaimed_at 2026-09-01T02:00:00+00:00 | reclaimed_at == pool_usable_at : True
any(reclaimed_at == pool_usable_at) : True
swept_lows total = 1 ; swept_highs = []
```

**Command/kết quả thật:**

```text
python -m pytest "tests/...::test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible" -q --tb=long
1 failed in 0.68s
  ĐÃ CHẠY tới hết phần temporal (fail nằm SAU, tại dòng 1521):
    numeric projection `equal_lows == [100.025]`            PASS
    `pool_usable_at == usable_at == stamp(2)`               PASS
    geometry excursion/reclaim trên nến idx1                PASS
    `assert target_events`                                  PASS  (1 target event)
    `assert any(reclaimed_at == pool_usable_at …)`          PASS
    `assert sweeps["swept_highs"] == []`                    PASS
  assert đầu fail: `assert len(records) == 1` → `assert 0 == 1`  (F06, `records` chưa có)
  ⇒ node RED vì **canonical records thiếu**, KHÔNG phải lỗi temporal

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
118 tests collected in 0.14s          (không đổi inventory; 0 lỗi collection)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_01"
18 failed, 11 passed, 89 deselected   (không đổi)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
69 failed, 49 passed                  (không đổi — node vốn đã RED, nay RED đúng lý do)
git diff --check -> clean
```

**Phân loại:** RED **giữ nguyên, nay thuộc đúng loại `implementation` F06** (thiếu `records` canonical) — **không** phát sinh RED/GREEN mới và **không** còn bị che bởi lỗi temporal. Oracle **không còn khóa priority/cardinality**: một implementation F07 đúng vẫn xanh dù phát thêm event hợp lệ khác.

**Hash T sau bước này:** `4A6F9F23C8A0C7F3A6DE7E1F86E7FA13E6C7F45C134C4F4D484A1B89E3FB386D`
**Hash T trước bước này:** `AC623CC3BDC4C6A20709880AD6C9C92785E5E1BECA2752CB38A641F6B42AAD74` (§A3.111)

**Phạm vi:** chỉ `T` (một hàm test) + `P` (hàng A3-039 và A3-041 §8.5) + `M` (hàng tracking node + ô §4 Pool/sweep → Positive/control) + `L` (mục này + hàng checklist A3-039/A3-041). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit.

**Trạng thái mã:** **A3-039 IMPLEMENTED** và **A3-041 IMPLEMENTED** (cả hai kèm `EXPECTED_IMPLEMENTATION_RED` F06 do `records` thiếu — không phải lỗi temporal). **A3-040 vẫn CHANGES_REQUESTED/OPEN**: node `test_r72_01_equal_pool_usable_before_sweep_close_is_accepted` **vẫn** còn `assert [sweep["index"] for …] == [2]` và `sweeps["swept_lows"][0]` (đúng lỗi A3R3-05) — **chưa** xử lý ở lượt này theo đúng giới hạn giao việc. **A3-042, A3-043 không đụng tới.**

**NEXT_TASK = A3-040** (cùng cách sửa: lọc target event theo level + candle index, bỏ khóa số lượng/`[0]`) — **chưa thực hiện**.

### A3.113 — Positive "usable before close": bỏ khóa toàn list (A3-040; đóng finding A3R3-05)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn quyết định:** [review A lần3 §2/A3R3-05](smc-task-72-checkpoint-a-review-round3.md) — “Hai positive controls cũng bắt toàn bộ list có đúng một event và event đầu là equal mean… **Không** thêm quy tắc phát nhiều event, dedupe hay pool priority ở lượt này” và §4 hàng “Cô lập equal-pool temporal seam”.

**Trạng thái vào lượt:** node `test_r72_01_equal_pool_usable_before_sweep_close_is_accepted` khóa **toàn bộ** `swept_lows` bằng `assert [sweep["index"] for sweep in sweeps["swept_lows"]] == [2]` rồi lấy `sweeps["swept_lows"][0]` — khóa **số lượng event** và **priority** của detector, ngoài phạm vi một positive temporal.

**Sửa (chỉ trong `T`, cùng node; fixture/geometry/tick/atr/thời gian giữ nguyên):**
1. Bỏ `assert [...swept_lows...] == [2]` và `sweep = sweeps["swept_lows"][0]`.
2. Thay bằng lọc theo **level `100.025` + candle `index 2`**; `assert target_events`; rồi đòi tồn tại event khớp
   `kind == "swept_low"`, `side == "buy"`, `time == stamp(2)` (open), `reclaimed_at == stamp(3)` (close),
   `excursion_buffer == pytest.approx(excursion)` — assert cả **source time** lẫn **event time**.
3. Thêm precondition: `pools["equal_lows"] == [expected_level]` (equal pool thật sự tồn tại) và
   `expected_level not in {source_a["level"], source_b["level"]}` ⇒ lọc theo level **không** bắt nhầm pool single-source.
4. **Không** dùng vị trí list; **không** assert tổng số `swept_lows`, pool priority hay dedupe.
5. Giữ `assert sweeps["swept_highs"] == []` (fixture khai `highs: []`). **Không** thêm `records`/`source_pool_id` fallback vào node này.

**Bằng chứng fixture/precondition độc lập (read-only):**

```text
equal_lows == [expected_level] : True   | expected_level = 100.025
expected_level khác 2 source level : True
pool_usable_at stamp(2) < event close stamp(3) : True
target_events = 1  (tổng swept_lows = 1)
   kind swept_low | side buy | time 2026-09-01T02:00:00+00:00 | reclaimed_at 2026-09-01T03:00:00+00:00 | excursion_buffer 0.2
matched (kind/side/time/close/buffer) : True
swept_highs : []
```

**Command/kết quả thật:**

```text
python -m pytest "tests/...::test_r72_01_equal_pool_usable_before_sweep_close_is_accepted" -q --tb=short
1 passed in 0.53s                      (GREEN — không còn assertion nào khóa toàn list/`[0]`)

python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
118 tests collected in 0.14s           (không đổi inventory; 0 lỗi collection)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_01"
18 failed, 11 passed, 89 deselected    (không đổi)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
69 failed, 49 passed                   (không đổi)
git diff --check -> clean
```

**Phân loại:** **GREEN** — không phát sinh RED; không sửa `core/`.

**Hash T sau bước này:** `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C`
**Hash T trước bước này:** `4A6F9F23C8A0C7F3A6DE7E1F86E7FA13E6C7F45C134C4F4D484A1B89E3FB386D` (§A3.112)

**Phạm vi:** chỉ `T` (một hàm test) + `P` (hàng A3-040 §8.5) + `M` (hàng tracking node + ô §4 Pool/sweep → Positive/control) + `L` (mục này + hàng checklist A3-040). **Không** sửa `core/`, protected probe, R56/golden, báo cáo review; **không** skip/xfail; **không** commit.

#### Kết luận finding A3R3-05 — đã xử lý xong (chưa tự PASS checkpoint)

| Mã | Trạng thái | Kết quả | Bằng chứng |
|---|---|---|---|
| **A3-039** | IMPLEMENTED | RED `EXPECTED_IMPLEMENTATION_RED` **F06** tại canonical `records`, **sau khi** temporal seam đã chạy thật | §A3.112 |
| **A3-041** | IMPLEMENTED | như trên — equality `usable_at == reclaimed_at` khóa bằng target event, không qua toàn list/`[0]` | §A3.112 |
| **A3-043/a** | IMPLEMENTED | RED `EXPECTED_IMPLEMENTATION_RED` **F07** (gate A-D01 chưa áp); negative chỉ khóa event **của đúng target equal pool** | §A3.110 |
| **A3-043/b** | IMPLEMENTED | **GREEN** — control chứng minh single-source sweep hợp lệ **không** bị negative /a cấm | §A3.111 |
| **A3-040** | IMPLEMENTED | **GREEN** — positive "usable before close" nay lọc theo level + candle index | §A3.113 |

**Hệ quả:** oracle cụm equal-pool temporal **không còn khóa** số lượng event, priority hay dedupe ở cả ba positive/negative; **A3-042** (reject nguồn usable sau close) vốn dùng hình học mirror và **không** bị finding này nêu, giữ nguyên **không đụng tới**.

**Checkpoint A vẫn CHANGES_REQUESTED** — lượt này **không** tự PASS checkpoint, **không** refresh A3-081…090, **không** CLOSED finding nào ở tầng hồ sơ. Các nhóm A3R3-01/02/03/04/05 nay đều đã có sửa đổi + bằng chứng; việc trình A lần4 và chạy nhóm lệnh bắt buộc thuộc lượt sau.

**NEXT_TASK = trình A lần4 (refresh A3-081…090 + chạy nhóm lệnh §4 của review)** — **chưa thực hiện**.

### A3.114 — Refresh inventory acceptance sau A3-066/e + A3-043/b (A3-082/r1)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** lượt refresh inventory của mã **A3-082** (đang IMPLEMENTED). **Giới hạn:** chỉ mã A3-082; **không** làm A3-081 hay A3-083…090.

**Command duy nhất đã chạy:**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
118 tests collected in 0.14s        (0 lỗi collection)
```

**Actual inventory hiện tại:**

```text
node (collected tests)        : 118
distinct collected functions  : 76
`def test_*` trong file       : 76
tên rỗng / trùng trong list   : 0 / 0
phân bố theo nhóm             : r72_01=29, r72_02=9, r72_03=4, r72_04=6,
                                r72_05=8, r72_06=20, r72_07=19, r72_08=13, r72_09=10
```

**So với snapshot cũ của A3-082:** **116 node / 74 functions** → nay **118 / 76** (Δ **+2 / +2**).

**Hai node mới kể từ snapshot — chính là toàn bộ phần tăng:**

| Node | Mã | nodes | funcs |
|---|---|---|---|
| `test_r72_01_pool_identity_survives_source_permutation` | A3-066/e | 1 | 1 |
| `test_r72_01_single_source_pool_usable_before_sweep_close_is_accepted` | A3-043/b | 1 | 1 |

**Node cũ vẫn collect được — kiểm độc lập, không suy từ tổng số:**

```text
test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible          nodes=1
test_r72_01_equal_pool_usable_before_sweep_close_is_accepted          nodes=1
test_r72_01_equal_pool_usable_time_is_max_of_both_sources             nodes=1
test_r72_01_pool_sweep_evidence_survives_future_bars                  nodes=1
test_r72_01_pool_sweep_identity_survives_rolling_index                nodes=1
test_r72_09_intentional_invalid_data_reports_its_own_reason           nodes=1
họ parametrized:
  test_r72_01_excursion_threshold_is_strict                           funcs=6
  test_r72_01_missing_pool_provenance_fails_closed                    funcs=5
  test_r72_01_source_usable_after_sweep_close_is_rejected             funcs=2
```

`distinct collected functions (76) == số `def test_*` trong file (76)` ⇒ **mọi** test function khai báo đều collect được, không function nào rơi rụng và không có function thừa. Tổng node tăng **không** được dùng thay cho việc kiểm sự hiện diện của node cũ.

**An toàn:**

```text
SHA256 tests/test_smc_gate72_fix_acceptance.py
  766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C   (KHÔNG ĐỔI so với §A3.113)
git diff --check -> clean
```

**Không chạy ở lượt này:** full acceptance, probes, task57–71, retained suite (đúng giới hạn giao việc). **Không** sửa code/test, `core/`, probe, R56/golden; **không** commit.

**Phạm vi:** chỉ `P` (hàng A3-082 §8.6) + `L` (hàng checklist A3-082 + mục này). **Không** cập nhật mapping A3-081, **không** đụng A3-083…090.

**Trạng thái A3-082:** giữ **IMPLEMENTED**; snapshot **116 / 74** là **lịch sử**, actual hiện hành là **118 / 76**.

**NEXT_TASK = A3-081** (refresh mapping §4 theo inventory mới) — **chưa thực hiện**.

### A3.115 — Refresh mapping R72-01 theo collection hiện hành (A3-081/r1a)

**Giới hạn:** docs-only, chỉ R72-01. Không sửa test/core/probe/R56/golden; không sửa mapping R72-02…09; không chạy full acceptance.

**Command:** `python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q` ⇒ **118 tests collected**, 0 lỗi collection; `T` có **76** hàm `def test_`.

**Đối chiếu:** lọc collection theo `test_r72_01` được **29 ID**. Bảng R72-01 trong `M` có đúng 29 node: 2 usable-at control, 2 positive-lineage param, provisional, equal usable-at, equal-before, 2 after-close param, equal-max, single-source, equal-without-usable, actual producer, 2 canonical-record param, 5 missing-provenance param, 6 strict-excursion param, prefix/batch, rolling, permutation. Kết quả **29/29 khớp**, không node matrix không collect được, không node collect bị thiếu, không ID trùng; param đều là ID thật.

**Kiểm riêng các node A lần4:** A3-039/041 giữ temporal assertion trước F06; A3-040 GREEN; A3-043/a RED F07 và /b GREEN; A3-066 prefix/batch, rolling, permutation giữ RED F06 cùng Expected/Actual hiện hành. Header M R72-01 đã đổi **18 → 29**.

**Không refresh ngoài phạm vi:** `69 failed / 49 passed` là snapshot full acceptance lịch sử; actual mới chỉ là collection **118 / 76**. Phân loại full mới thuộc A3-084/r1.

**Hash T:** `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C` (không đổi). `git diff --check` sạch.

**Trạng thái A3-081:** giữ **IMPLEMENTED**; đây là refresh r1a giới hạn R72-01.

### A3.116 — Targeted evidence 14 node đã mở lại ở A lần4 (A3-083/r1a)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** lượt refresh evidence của mã **A3-083**. **Giới hạn:** chỉ A3-083/r1a; **không** làm A3-081, A3-084…090, **không** chạy full acceptance / probes / task57–71 / retained suite / F02–F05.

**Command duy nhất (14 node, một lệnh pytest):** các node A3-071, hai node thiếu-metadata r72_07, ba override control r72_07, A3-061, ba node A3-066, hai node A3-039/041 + A3-040, và hai node A3-043 — `-q --tb=short`.

**Actual: `9 failed, 5 passed in 1.04s`** (14 node).

| # | Node | Mã | Expected | Actual | Assertion/frame đầu tiên khi RED | F |
|---|---|---|---|---|---|---|
| 1 | `test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep` | A3-071 | GREEN | **PASS** | — | — |
| 2 | `test_r72_07_missing_canonical_atr_is_unknown_and_unusable` | A3-067 | RED F02 | **RED** | `:2610` `assert result["metadata_state"] == "unknown"` → `KeyError: 'metadata_state'` | **F02** |
| 3 | `test_r72_07_missing_canonical_tick_is_unknown_and_unusable` | A3-067 | RED F02 | **RED** | `:2649` `assert result["metadata_state"] == "unknown"` → `KeyError: 'metadata_state'` | **F02** |
| 4 | `test_r72_07_excursion_override_only_replaces_its_own_rule` | A3-067 | GREEN | **PASS** | — | — |
| 5 | `test_r72_07_equal_tolerance_override_only_replaces_its_own_rule` | A3-067 | GREEN | **PASS** | — | — |
| 6 | `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule` | A3-067 | controls GREEN; thiếu-metadata RED F02 | **RED** | `:3980` `assert without_metadata.metadata_state == "unknown"` → `AttributeError` — nằm trong **khối thiếu-metadata** (comment `:3976`), **sau** hai cross-control `:3972-3974` đã PASS | **F02** |
| 7 | `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` | A3-061 | implementation RED đã ghi | **RED** | `:3708` `assert enriched["lifecycle_status"] == "invalid"` → `assert 'confirmed' == 'invalid'` | **F03** |
| 8 | `test_r72_01_pool_sweep_evidence_survives_future_bars` | A3-066 | RED F06 | **RED** | `:1248` → `_pool_record_for` `:1165` `assert 0 == 1` với `('swing_low', ['smcs-a3eedf…'], [])` | **F06** |
| 9 | `test_r72_01_pool_sweep_identity_survives_rolling_index` | A3-066 | RED F06 | **RED** | `:1330` → `_pool_record_for` `:1165` `assert 0 == 1` | **F06** |
| 10 | `test_r72_01_pool_identity_survives_source_permutation` | A3-066/e | RED F06 | **RED** | `:1401` → `_pool_record_for` `:1165` `assert 0 == 1` với `('equal_low', ['source-a','source-z'], [])` | **F06** |
| 11 | `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` | A3-039/041 | RED F06 sau temporal seam | **RED** | `:1521` `assert len(records) == 1` → `assert 0 == 1` (temporal seam phía trên đã PASS) | **F06** |
| 12 | `test_r72_01_equal_pool_usable_before_sweep_close_is_accepted` | A3-040 | GREEN | **PASS** | — | — |
| 13 | `test_r72_01_equal_pool_usable_time_is_max_of_both_sources` | A3-043/a | RED F07 | **RED** | `:1721` `assert equal_pool_events == []` → `assert [{'depth': 0.525…, 'index': 1, …}] == []` | **F07** |
| 14 | `test_r72_01_single_source_pool_usable_before_sweep_close_is_accepted` | A3-043/b | GREEN | **PASS** | — | — |

**Tổng hợp F-code của RED:** **F02 ×3**, **F03 ×1**, **F06 ×4**, **F07 ×1** = **9 RED**. **GREEN 5**: A3-071, hai override control r72_07, A3-040, A3-043/b.

**Đối chiếu expected ⇒ KHỚP toàn bộ, không có `UNEXPECTED`.** Lưu ý diễn giải: expected “3 override controls: GREEN” đúng ở tầng **control** — ba control đủ metadata đều chạy và PASS; node `lifecycle_threshold_overrides` vẫn RED vì khối **thiếu-metadata** ở cuối node, chính là vế “RED F02” mà cùng dòng expected đã nêu riêng.

**An toàn:**

```text
SHA256 tests/test_smc_gate72_fix_acceptance.py
  766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C   (KHÔNG ĐỔI)
git diff --check -> clean
7 fingerprint bảo vệ (5 core + probe + golden) : ALL UNCHANGED
```

**Không sửa:** code, test, `core/`, probe, golden, R56, ngưỡng. **Không** đổi snapshot full acceptance **69 failed / 49 passed**; **không** sửa `M`.

**Phạm vi:** chỉ `P` (hàng A3-083 §8.6) + `L` (hàng checklist A3-083 + mục này).

**Trạng thái A3-083:** giữ **IMPLEMENTED**; đây là **targeted evidence**, **chưa** phải full classification **A3-084/r1**.

**NEXT_TASK = A3-084/r1** (phân loại đầy đủ theo full acceptance) — **chưa thực hiện**.

### A3.117 — Full acceptance: inventory PASS/FAIL (A3-084/r1a)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** lượt chạy full acceptance của mã **A3-084**. **Giới hạn:** chỉ phần **chạy + ghi inventory**; phân loại RED chi tiết (implementation vs test-defect) thuộc **A3-084/r1b** — mục này **không** kết luận mọi RED là implementation.

**Command (đúng một lệnh, chỉ file acceptance):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -v --tb=short -ra
```

**Tổng thực:**

```text
collected = 118   passed = 49   failed = 69   skipped = 0   xfail = 0   xpass = 0   error = 0
(không có skip/xfail nào được thêm; tổng 118 = 49 + 69)
```

**Đối chiếu snapshot cũ (A3-083 §A3.86): 69 failed / 49 passed.** Actual hôm nay **69 / 49 — KHỚP hoàn toàn**. Mọi node có status tường minh từ `-v` đều rơi vào hai nhóm PASSED/FAILED (118/118), **không node nào đổi trạng thái**.

**Tổng PASS/FAIL theo nhóm:**

| Nhóm | PASS | FAIL | Tổng |
|---|---|---|---|
| R72-01 | 11 | 18 | 29 |
| R72-02 | 4 | 5 | 9 |
| R72-03 | 2 | 2 | 4 |
| R72-04 | 2 | 4 | 6 |
| R72-05 | 2 | 6 | 8 |
| R72-06 | 8 | 12 | 20 |
| R72-07 | 6 | 13 | 19 |
| R72-08 | 5 | 8 | 13 |
| R72-09 | 9 | 1 | 10 |
| **Tổng** | **49** | **69** | **118** |

**Danh sách 69 node FAILED — full node ID, file/dòng, exception/assertion đầu tiên** (`T` = `tests/test_smc_gate72_fix_acceptance.py`; cột lỗi là dòng `E` đầu tiên của block `--tb=short`):

| # | Full node ID | Frame | Exception/assertion đầu tiên |
|---|---|---|---|
| 1 | `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[buy]` | `T:245` | `AssertionError: assert not [{'depth': 0.5, 'depth_atr': 0.5, 'excursion_buffer': 0.2, 'index': 2, ...}]` |
| 2 | `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[sell]` | `T:245` | `AssertionError: assert not [{'depth': 0.5, 'depth_atr': 0.5, 'excursion_buffer': 0.2, 'index': 2, ...}]` |
| 3 | `test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time` | `T:253` | `AssertionError: assert 'late' == 'early'` |
| 4 | `test_r72_02_context_owner_follows_claim_time_under_input_permutation` | `T:291` | `AssertionError: assert 'late' == 'early'` |
| 5 | `test_r72_02_context_same_time_tie_follows_stable_setup_id` | `T:569` | `AssertionError: assert 'beta-setup' == 'alpha-setup'` |
| 6 | `test_r72_03_acceptance_contribution_is_selected_within_owner_children` | `T:588` | `assert False is True` |
| 7 | `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` | `T:600` | `AssertionError: assert 'later-owner' == 'original-owner'` |
| 8 | `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[buy]` | `T:618` | `assert True is False` |
| 9 | `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[sell]` | `T:618` | `assert True is False` |
| 10 | `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[buy]` | `T:632` | `AssertionError: assert '2026-09-23T00:00:00+00:00' is None` |
| 11 | `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[sell]` | `T:632` | `AssertionError: assert '2026-09-23T00:00:00+00:00' is None` |
| 12 | `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[buy]` | `T:660` | `assert 0.0 == 0.1 � 1.0e-07` |
| 13 | `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[sell]` | `T:660` | `assert 0.0 == 0.1 � 1.0e-07` |
| 14 | `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[buy]` | `T:686` | `assert True is False` |
| 15 | `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[sell]` | `T:686` | `assert True is False` |
| 16 | `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy]` | `T:783` | `assert 0 == 1` |
| 17 | `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[sell]` | `T:783` | `assert 0 == 1` |
| 18 | `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[buy]` | `T:865` | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` |
| 19 | `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[sell]` | `T:865` | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` |
| 20 | `test_r72_01_missing_pool_provenance_fails_closed[record_for_other_level]` | `T:988` | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` |
| 21 | `test_r72_01_missing_pool_provenance_fails_closed[no_sources]` | `T:988` | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` |
| 22 | `test_r72_01_missing_pool_provenance_fails_closed[dangling_source_id]` | `T:988` | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` |
| 23 | `test_r72_01_missing_pool_provenance_fails_closed[source_without_provenance_id]` | `T:988` | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` |
| 24 | `test_r72_01_missing_pool_provenance_fails_closed[source_without_usable_at]` | `T:988` | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` |
| 25 | `test_r72_01_pool_sweep_evidence_survives_future_bars` | `T:1248` | `AssertionError: ('swing_low', ['smcs-a3eedff40ca702ee7827'], [])` |
| 26 | `test_r72_01_pool_sweep_identity_survives_rolling_index` | `T:1330` | `AssertionError: ('swing_low', ['smcs-a3eedff40ca702ee7827'], [])` |
| 27 | `test_r72_01_pool_identity_survives_source_permutation` | `T:1401` | `AssertionError: ('equal_low', ['source-a', 'source-z'], [])` |
| 28 | `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` | `T:1521` | `assert 0 == 1` |
| 29 | `test_r72_01_source_usable_after_sweep_close_is_rejected[buy]` | `T:1657` | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` |
| 30 | `test_r72_01_source_usable_after_sweep_close_is_rejected[sell]` | `T:1657` | `AssertionError: assert [{'depth': 0....dex': 2, ...}] == []` |
| 31 | `test_r72_01_equal_pool_usable_time_is_max_of_both_sources` | `T:1721` | `AssertionError: assert [{'depth': 0....dex': 1, ...}] == []` |
| 32 | `test_r72_02_missing_canonical_claim_time_fails_closed[reclaimed_at]` | `T:1914` | `AssertionError: assert {'sweep': {'a...': True, ...}} == {}` |
| 33 | `test_r72_02_missing_canonical_claim_time_fails_closed[setup_available_at]` | `T:1914` | `AssertionError: assert {'sweep': {'a...': True, ...}} == {}` |
| 34 | `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | `T:1993` | `KeyError: 'sweep'` |
| 35 | `test_r72_04_context_repeat_after_json_restore_keeps_assignment` | `T:2035` | `AssertionError: assert 'later-owner' == 'original-owner'` |
| 36 | `test_r72_04_same_pool_observation_cannot_bypass_consumption` | `T:2117` | `AssertionError: assert 'later' == 'original'` |
| 37 | `test_r72_04_conflicting_assignment_history_fails_closed` | `T:2177` | `AssertionError: assert {'sweep': {'a...': True, ...}} == {}` |
| 38 | `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[buy]` | `T:2199` | `assert True is False` |
| 39 | `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[sell]` | `T:2199` | `assert True is False` |
| 40 | `test_r72_05_cutoff_equal_invalidated_at_is_terminal[buy]` | `T:2253` | `assert True is False` |
| 41 | `test_r72_05_cutoff_equal_invalidated_at_is_terminal[sell]` | `T:2253` | `assert True is False` |
| 42 | `test_r72_06_h4_reaction_at_terminal_is_blocked[buy]` | `T:2358` | `AssertionError: assert '2026-09-06T08:00:00+00:00' is None` |
| 43 | `test_r72_06_h4_reaction_at_terminal_is_blocked[sell]` | `T:2358` | `AssertionError: assert '2026-09-06T08:00:00+00:00' is None` |
| 44 | `test_r72_06_h4_reaction_after_terminal_is_blocked[buy]` | `T:2386` | `AssertionError: assert '2026-09-06T12:00:00+00:00' is None` |
| 45 | `test_r72_06_h4_reaction_after_terminal_is_blocked[sell]` | `T:2386` | `AssertionError: assert '2026-09-06T12:00:00+00:00' is None` |
| 46 | `test_r72_06_terminal_order_before_reaction_is_explicit[21-buy]` | `T:2428` | `AssertionError: assert '2026-09-23T00:00:00+00:00' is None` |
| 47 | `test_r72_06_terminal_order_before_reaction_is_explicit[21-sell]` | `T:2428` | `AssertionError: assert '2026-09-23T00:00:00+00:00' is None` |
| 48 | `test_r72_06_terminal_order_before_reaction_is_explicit[22-buy]` | `T:2428` | `AssertionError: assert '2026-09-24T00:00:00+00:00' is None` |
| 49 | `test_r72_06_terminal_order_before_reaction_is_explicit[22-sell]` | `T:2428` | `AssertionError: assert '2026-09-24T00:00:00+00:00' is None` |
| 50 | `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-buy]` | `T:2529` | `AssertionError: assert 'confirmed' == 'invalid'` |
| 51 | `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-sell]` | `T:2529` | `AssertionError: assert 'confirmed' == 'invalid'` |
| 52 | `test_r72_07_item_and_argument_tick_sources_have_parity[buy]` | `T:2582` | `AssertionError: argument_only` |
| 53 | `test_r72_07_item_and_argument_tick_sources_have_parity[sell]` | `T:2582` | `AssertionError: argument_only` |
| 54 | `test_r72_07_missing_canonical_atr_is_unknown_and_unusable` | `T:2610` | `KeyError: 'metadata_state'` |
| 55 | `test_r72_07_missing_canonical_tick_is_unknown_and_unusable` | `T:2649` | `KeyError: 'metadata_state'` |
| 56 | `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[expired_by_age]` | `T:2697` | `KeyError: 'metadata_state'` |
| 57 | `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[already_invalid]` | `T:2697` | `KeyError: 'metadata_state'` |
| 58 | `test_r72_07_metadata_survives_context_to_typed_round_trip` | `T:2727` | `KeyError: 'metadata_state'` |
| 59 | `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]` | `T:2765` | `ValueError: Invalid zone boundary: nan` |
| 60 | `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[tick_size]` | `T:2765` | `ValueError: Invalid zone boundary: nan` |
| 61 | `test_r72_07_conflicting_same_scope_tick_sources_fail_closed` | `T:2805` | `KeyError: 'metadata_state'` |
| 62 | `test_r72_08_invalid_canonical_zone_survives_typed_round_trip_consistently` | `T:2858` | `KeyError: 'usable'` |
| 63 | `test_r72_08_canonical_invalid_status_wins_legacy_boolean[False]` | `T:2874` | `AssertionError: assert False is True` |
| 64 | `test_r72_08_typed_terminal_projection_reaches_d1_consumer[buy]` | `T:2912` | `assert True is False` |
| 65 | `test_r72_08_typed_terminal_projection_reaches_d1_consumer[sell]` | `T:2912` | `assert True is False` |
| 66 | `test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[buy]` | `T:3022` | `assert True is False` |
| 67 | `test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[sell]` | `T:3022` | `assert True is False` |
| 68 | `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` | `T:3708` | `AssertionError: assert 'confirmed' == 'invalid'` |
| 69 | `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule` | `T:3980` | `AttributeError: 'ZoneLifecycle' object has no attribute 'metadata_state'` |

**Chưa phân loại:** bảng trên chỉ là **inventory thực tế**. Việc gán từng RED vào nhóm `implementation` / `test-defect` / `EXPECTED_IMPLEMENTATION_RED` theo F-code **chưa** được làm ở lượt này — thuộc **A3-084/r1b**.

**An toàn:**

```text
SHA256 tests/test_smc_gate72_fix_acceptance.py
  766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C   (KHÔNG ĐỔI trước/sau lượt)
git diff --check -> clean
```

Không sửa test/core/probe/golden/R56/matrix, không skip/xfail, không commit; không chạy suite ngoài file acceptance.

**Phạm vi:** `L` (mục này + hàng A3-084) và `P` (hàng A3-084). Kèm một sửa **định dạng** ở hàng A3-081 trong `L`: escape hai pipe trong `` `grep -c '\|\|'` `` để hàng trở lại **6 ô** đúng header (nội dung giữ nguyên).

**Trạng thái A3-084:** giữ **IMPLEMENTED**; **r1a hoàn tất phần chạy/inventory**, **r1b (phân loại) còn chờ**. **Checkpoint A vẫn CHANGES_REQUESTED** — lượt này không tự PASS checkpoint và không làm F02.

### A3.118 — Phân loại 18 RED thuộc R72-01 (A3-084/r1b-01)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** inventory §A3.117 + contract/mapping R72-01 trong `M` + đọc trực tiếp node/helper trong `T` và `core/` (chỉ đọc). **Giới hạn:** chỉ **R72-01**; **51 RED thuộc R72-02…09 chưa phân loại**.

**Nguyên tắc áp dụng:** precondition chỉ được tính là “đã chạy” khi assert của nó nằm **trước** điểm fail (pytest fail-fast); assertion nằm **sau** điểm fail ghi là **chưa chạy**. Không suy diễn “mọi precondition PASS”. RED không mặc nhiên đúng chỉ vì từng được gắn nhãn — mỗi dòng dưới đây đối chiếu lại **nguyên nhân tại điểm fail**.

**Bảng phân loại 18/18 ID (khớp tập R72-01 FAILED ở §A3.117, không thiếu/trùng):**

| # | Full node ID | Rule/nguồn contract | Precondition đã chạy | Assertion đầu fail + actual | Expected | Loại lỗi | F-code | Assertion phía sau chưa chạy |
|---|---|---|---|---|---|---|---|---|
| 1 | `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[buy]` | A-D01: source phải usable tại sweep close (R72-01) | **0** — đoạn 216–244 chỉ là setup, **không có assert nào** trước điểm fail | ``assert not events` → `[{… 'index': 2, …}]` (1 event, depth 0.5)` | `[]` — nguồn chỉ `confirmed_at = stamp(6)`, **sau** close nến sweep `stamp(3)` | implementation — **chưa cô lập nguyên nhân** | **F06/F07** (chưa cô lập) | **0** — T:245 là câu lệnh cuối node |
| 2 | `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[sell]` | nt. | nt. | nt. (nhánh `swept_highs`, cùng `index 2`) | nt. | implementation — **chưa cô lập nguyên nhân** | **F06/F07** (chưa cô lập) | **0** |
| 3 | `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy]` | A3-005/A3-009: `records` canonical có `pool_id/kind/source_ids/sources/usable_at` | **2** — numeric projection `equal_lows == [expected_level]` và không-dict đều PASS | ``assert len(matches) == 1` → `assert 0 == 1` (0 record khớp lineage)` | đúng **1** record `source_ids == ["source-a","source-b"]` | implementation | **F06** | **7** — T:785/786/788 (`kind`/`pool_id` không rỗng, `usable_at == max`), T:794–799 (`sources` từng nguồn) |
| 4 | `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[sell]` | nt. | nt. (nhánh `equal_highs`) | `nt.` | nt. | implementation | **F06** | nt. (7) |
| 5 | `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[buy]` | A3-005 luật 3 / A3-010: thiếu `records` ⇒ fail closed, **không** fallback numeric | **6** — numeric level có, `"records" not in pools`, geometry excursion/reclaim — đều PASS | ``assert canonical[swept_key] == []` → `[{… 'index': 2, …}]`` | `[]` — core **cấp sweep từ level numeric** dù thiếu provenance | implementation | **F06** | **2** — T:866 (mặt đối diện rỗng), T:871 (control legacy vẫn sweep `index 2`) |
| 6 | `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[sell]` | nt. | nt. | `nt. (nhánh `swept_highs`)` | nt. | implementation | **F06** | nt. (2) |
| 7 | `test_r72_01_missing_pool_provenance_fails_closed[record_for_other_level]` | A3-064 / A3-005 luật 3: mỗi dạng thiếu provenance **riêng** phải fail closed | **8** — record mang đúng khuyết điểm đã nêu, numeric level còn, geometry sweep được — PASS | ``assert canonical["swept_lows"] == []` → `[{… 'index': 2, …}]`` | `[]` — core bỏ qua provenance và fallback sang level numeric | implementation | **F06** | **2** — T:989 (`swept_highs` rỗng), T:994 (control legacy `index 2`) |
| 8 | `test_r72_01_missing_pool_provenance_fails_closed[no_sources]` | nt. | nt. | `nt.` | nt. | implementation | **F06** | nt. (2) |
| 9 | `test_r72_01_missing_pool_provenance_fails_closed[dangling_source_id]` | nt. | nt. | `nt.` | nt. | implementation | **F06** | nt. (2) |
| 10 | `test_r72_01_missing_pool_provenance_fails_closed[source_without_provenance_id]` | nt. | nt. | `nt.` | nt. | implementation | **F06** | nt. (2) |
| 11 | `test_r72_01_missing_pool_provenance_fails_closed[source_without_usable_at]` | nt. | nt. | `nt.` | nt. | implementation | **F06** | nt. (2) |
| 12 | `test_r72_01_pool_sweep_evidence_survives_future_bars` | A3-066/a…/c + A-D06: record canonical giữ nguyên qua prefix/batch | **15** — gồm lọc cutoff theo `reclaimed_at`, parity 12 field causal, hình học, `prefix_pools["swing_lows"]` — đều PASS | ``_pool_record_for(...)` → `assert 0 == 1` với `('swing_low', ['smcs-a3eedff40ca702ee7827'], [])`` | đúng 1 record theo **kind + lineage** của swing pivot | implementation | **F06** | **16** — T:1249–1271 (record↔source, `pool_id` prefix==batch, nối `source_pool_id`, pool cùng kind thứ hai) |
| 13 | `test_r72_01_pool_sweep_identity_survives_rolling_index` | A3-066/d + A-D06: index dịch nhưng identity/nguồn/usable time không đổi | **12** — timestamp rolled == batch[1], pivot giữ `swing_id`/`confirmed_at`, sweep `index` dịch 1, `_pool_causal_evidence` parity — PASS | ``_pool_record_for(...)` → `assert 0 == 1` (`('swing_low', ['smcs-a3eedff40ca702ee7827'], [])`)` | cùng một record canonical cho pivot ở cả hai lượt | implementation | **F06** | **11** — T:1331–1344 (`pool_id`/`source_ids`/`kind`/`level`/`usable_at` bằng nhau giữa batch và rolled, nối `source_pool_id`) |
| 14 | `test_r72_01_pool_identity_survives_source_permutation` | A3-066/e + A-D06: đảo thứ tự nguồn không đổi canonical pool | **4** — hai thứ tự input khác nhau, `causal_ids != sorted_ids`, equal pool tồn tại ở `expected_level` — PASS | ``_pool_record_for(...)` → `assert 0 == 1` (`('equal_low', ['source-a', 'source-z'], [])`)` | 1 record `equal_low` với `source_ids` **sort ổn định** `["source-a","source-z"]` | implementation | **F06** | **14** — T:1402–1425 (parity hai lượt, từng source tra theo `swing_id`, luật max `usable_at`) |
| 15 | `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` | A-D01 inclusive + A3-039/041: `usable_at == reclaimed_at` phải được nhận | **8** — numeric projection, `pool_usable_at == usable_at == stamp(2)`, geometry, **target event tồn tại**, **`reclaimed_at == pool_usable_at`**, `swept_highs == []` — **temporal seam PASS hết** | ``assert len(records) == 1` → `assert 0 == 1`` | 1 record `source_ids == ["source-a","source-b"]` | implementation | **F06** | **1** — T:1522 (`records[0]["usable_at"] == pool_usable_at`) |
| 16 | `test_r72_01_source_usable_after_sweep_close_is_rejected[buy]` | A-D01: nguồn usable **sau** sweep close không được dùng (A3-042) | **9** — nguồn hợp lệ, `pool_usable_at == future_usable_at`, `pool_usable_at > event_close`, geometry — PASS | ``assert sweeps[tested] == []` → `[{… 'index': 2, …}]`` | `[]` — `usable_at = stamp(4)` **sau** close `stamp(3)` nhưng core vẫn dùng | implementation | **F07** | **2** — T:1658 (mặt đối diện rỗng), T:1660 (`sweep_candle.time == open_time`) |
| 17 | `test_r72_01_source_usable_after_sweep_close_is_rejected[sell]` | nt. | nt. | `nt. (nhánh `swept_highs`)` | nt. | implementation | **F07** | nt. (2) |
| 18 | `test_r72_01_equal_pool_usable_time_is_max_of_both_sources` | A-D01 luật **max cả hai nguồn** (A3-043/a) | **7** — equal pool tồn tại, hai `usable_at` khác nhau, `early < event_close < pool_usable_at`, geometry, `expected_level` khác hai level single-source — PASS | ``assert equal_pool_events == []` → `[{… 'index': 1, …}]`` | target equal pool **không** có event — usable `stamp(3)` muộn hơn close `stamp(2)` | implementation | **F07** | **1** — T:1723 (`swept_highs == []`) |

**Tổng hợp theo F-code:** **F06 ×13** (mục 3–15), **F06/F07 ×2 — chưa cô lập** (mục 1–2), **F07 ×3** (mục 16, 17, 18). **18/18 là `implementation`** — không phát hiện lỗi test hay fixture ở cụm R72-01.

**Nguyên nhân gốc tại điểm fail (đọc `core/`, chỉ đọc):**

- **F06 (13 node):** `detect_liquidity_pools` **không phát** container `records`, và `detect_liquidity_sweeps` **fallback sang level numeric** khi thiếu `records` ⇒ mọi assertion đọc/đối chiếu canonical record fail ngay ở bước chọn record (`assert 0 == 1`) hoặc ở `canonical[...] == []`. Đây là interface canonical A3-005 chưa được `core/` hiện thực.
- **F07 (5 node):** `detect_liquidity_sweeps` **không** áp cổng thời gian A-D01 (`usable_at <= reclaimed_at`) — nguồn usable **sau** close vẫn được dùng, và luật **max hai nguồn** chưa được áp. Check causal hiện tại dựa trên **index** (`source["index"] >= candle_index`), không dựa trên thời điểm usable.

**Hai điểm cần TL làm rõ (ghi nhận, KHÔNG sửa):**

1. **GIỚI HẠN của mục 1–2 (đính chính 2026-09-11, A3-084/r1b-02):** expected **reject là hợp lệ** (nguồn `confirmed_at = stamp(6)` nằm sau close `stamp(3)` ⇒ không được cấp sweep), nhưng **fixture không có `usable_at`** nên node **chưa phân biệt được** hai nguyên nhân reject: **(F06)** thiếu provenance `usable_at` ⇒ fail closed theo A3-005 luật 3 / A3-064 (`source_without_usable_at`), và **(F07)** nguồn chưa usable tại close ⇒ cổng A-D01 chặn. Vì chưa cô lập, mục 1–2 ghi **F06/F07** thay vì chốt F07.
   - **Không chốt** quy tắc fallback `confirmed_at → usable_at` — quy tắc này vẫn **chưa có quyết định** (§A3.9/§A3.12).
   - **Hai node này KHÔNG được tính là bằng chứng độc lập rằng temporal gate đã được kiểm.** Muốn cô lập cần fixture **có `usable_at` tường minh** đặt sau close để loại hẳn nhánh thiếu-provenance — thuộc lượt sửa test riêng, **không** làm ở đây.
2. **Mục 1–2 không có precondition nào** trước điểm fail (dòng 216–244 là setup thuần). Khác các node còn lại, ở đây **không** có bằng chứng “precondition PASS” để dựa vào — đã ghi `0` thay vì suy diễn.

**Hai control chưa chạy trong lượt này** (nằm sau điểm fail, sẽ chạy khi F06 được hiện thực): `T:871` và `T:994` — control đường legacy vẫn phải sweep ở `index 2`. Lượt full acceptance này **không** sản sinh bằng chứng trực tiếp cho chúng.

**Giữ nguyên số liệu lịch sử:** full acceptance vẫn **69 failed / 49 passed** (§A3.117); inventory **118 node / 76 hàm** (§A3.114); các snapshot 116/74 và 69/49 là lịch sử.

**An toàn:** SHA256 `T` = `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C` (không đổi). Không sửa test/core/probe/golden/R56/matrix; **không chạy lại node nào** (traceback §A3.117 đã đủ); không commit.

**Phạm vi:** chỉ `L` (mục này + hàng A3-084).

**Trạng thái A3-084:** giữ **IMPLEMENTED**; **r1b-01 hoàn tất R72-01 (18/18)**; **r1b phần R72-02…09 (51 RED) còn chờ**. **Checkpoint A vẫn CHANGES_REQUESTED** — không tự PASS, không đóng finding nào.

### A3.119 — Phân loại 5 RED thuộc R72-02 (A3-084/r1b-02)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** inventory §A3.117 + mapping R72-02 trong `M` + đọc trực tiếp node trong `T` và `core/smc_sweep_linking.py`/`core/smc_context.py` (chỉ đọc). **Giới hạn:** chỉ **R72-02**; **46 RED thuộc R72-03…09 chưa phân loại**. Lượt này **không** sửa test/core và **không** chốt contract nào.

**Nguyên tắc:** precondition chỉ tính là “đã chạy” khi assert của nó nằm **trước** điểm fail. Loại lỗi và F-code được suy từ **giá trị actual tại điểm fail**, không từ tên nhóm hay nhãn cũ.

**Bảng phân loại 5/5 ID (khớp tập R72-02 FAILED ở §A3.117, không thiếu/thừa/trùng):**

| # | Full node ID | Rule | Precondition đã chạy | Assertion đầu fail + actual | Expected | Loại lỗi | F-code | Assertions phía sau chưa chạy |
|---|---|---|---|---|---|---|---|---|
| 1 | `test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time` | A-D02: owner là claim **sớm nhất**, không phải zone **gần nhất** (R72-02) | **0** — T:249–252 là setup thuần (`zone`/`sweep`/`attach`), **không có assert nào** trước điểm fail | `assert sweeps["swept_lows"][0]["owner_setup_id"] == "early"` → `'late' == 'early'` | `"early"` (available hour 13); zone `late` (hour 15) **gần hơn** nhưng không được thắng | implementation | **F08** | **0** — T:253 là câu lệnh cuối node |
| 2 | `test_r72_02_context_owner_follows_claim_time_under_input_permutation` | A3-069 / A-D02: caller enumerate → assign → project, owner theo claim time | **9** — T:277–287: caller thật sự chiếu assignment lên **cả hai** thứ tự (`owner_setup_id`/`assignment_id`/`consumed`/`contribution_applied` có mặt) và bất biến khi đảo input — đều PASS | `assert forward["owner_setup_id"] == "early"` → `'late' == 'early'` | `"early"` — claim sớm nhất, không phải zone gần nhất | implementation | **F08** | **2** — T:292 `forward["linked_zone_id"] == "early-child"`, T:293 `forward["claim_eligible_at"] == stamp(13)` |
| 3 | `test_r72_02_context_same_time_tie_follows_stable_setup_id` | A3-073 / A-D02: khi claim time **bằng nhau**, tie-break bằng **setup ID ổn định** | **10** — T:546–566: fixture có hai `available_at` bằng nhau, `setup_id` và `zone_id` chỉ về hai zone **khác nhau**, mỗi zone tự đủ điều kiện link, link one-to-one ở cả hai thứ tự, và bất biến owner/link/assignment — đều PASS | `assert forward["owner_setup_id"] == "alpha-setup"` → `'beta-setup' == 'alpha-setup'` | `"alpha-setup"` (setup ID nhỏ hơn); `a-loser-child` có **zone ID nhỏ hơn** nên phân biệt được quy tắc | implementation | **F08** | **1** — T:570 `forward["linked_zone_id"] == "z-winner-child"` |
| 4 | `test_r72_02_missing_canonical_claim_time_fails_closed[reclaimed_at]` | A-D02: claim canonical cần **cả hai** mốc thời gian; **không** mốc nào được thay cho mốc kia | **4** — T:1908–1911: field bị bỏ **thật sự vắng**, mốc còn lại đúng giá trị fixture, `pool_id`/`source_ids` vẫn hợp lệ — đều PASS | `assert result["assignments"] == {}` → **có** assignment cho `sweep`: `owner_setup_id 'setup'`, `claim_eligible_at '2026-09-01T13:00:00+00:00'`, `assigned_at` cùng mốc, `contribution_applied True` | `{}` — không được cấp owner khi thiếu một mốc claim time | implementation | **F08** | **3** — T:1915 `"SWEEP_CLAIM_TIME_MISSING" in reason_codes`, T:1923 và T:1925–1927 (positive control: claim đủ hai mốc vẫn thắng) |
| 5 | `test_r72_02_missing_canonical_claim_time_fails_closed[setup_available_at]` | nt. (thiếu mốc còn lại) | **4** — nt. | `assert result["assignments"] == {}` → assignment cho `sweep` với `claim_eligible_at '2026-09-01T11:00:00+00:00'` (= `reclaimed_at` còn lại), `contribution_applied True` | `{}` | implementation | **F08** | **3** — nt. |

**Tổng hợp:** **F08 ×5** (5/5). Tất cả là **`implementation`** — không phát hiện lỗi test hay fixture ở cụm R72-02.

**Nguyên nhân gốc tại điểm fail (đọc `core/`, chỉ đọc):**

- **Mục 1–3 — caller xếp hạng/tie-break sai khóa.** Ở cả ba node, tầng caller **đã** enumerate → assign → project thật (điều đó được chứng minh bằng chính các precondition PASS), nhưng **khóa chọn owner** là khoảng cách/zone ID thay vì **claim time** rồi **setup ID ổn định**: mục 1 và 2 chọn `late` (zone gần hơn) thay vì `early` (claim sớm hơn); mục 3 chọn `beta-setup`/`a-loser-child` (zone ID nhỏ hơn) thay vì `alpha-setup` (setup ID nhỏ hơn). Đúng mô tả **F08** — “Xét mọi claim trước chọn owner / context owner theo claim time, không theo distance rank”.
- **Mục 4–5 — một mốc claim time thay được mốc kia.** `assign_sweep_ownership` **không** fail closed khi claim thiếu một trong hai mốc; nó **lấy mốc còn lại** làm `claim_eligible_at` rồi cấp owner: thiếu `reclaimed_at` ⇒ dùng `setup_available_at = stamp(13)`; thiếu `setup_available_at` ⇒ dùng `reclaimed_at = stamp(11)`. Đây là cùng nhóm ownership/canonical claim time ⇒ **F08**.

**Điểm cần lưu ý (ghi nhận, KHÔNG sửa):**

1. **Mục 1 dùng `swept_lows[0]` (vị trí list) để chọn event** thay vì lọc theo lineage/level. Fixture chỉ có một sweep nên RED vẫn đúng (`owner_setup_id` quả thật là `'late'`), nhưng oracle **yếu**: nếu sau này phát sinh event thứ hai, node có thể chọn nhầm. Cùng loại phê bình mà review A lần3 đã nêu cho các cụm khác — **chưa** xử lý ở lượt này.
2. **Mục 4–5: assignment được cấp thiếu lineage.** Payload thực tế **không** có `pool_id`/`source_ids` (khớp ghi chú `M` mục “Projection … không có lineage” — F10). Node này **không** assert lineage trên assignment nên đó **không** phải nguyên nhân fail; ghi ở đây như **dependency** cho F10, không tính vào phân loại 5 RED.
3. **Mục 2 và 3 đã có nhãn F08 từ trước trong `M`** (`A3-069`, `A3-073`) — lượt này **tái lập độc lập** từ actual, không sao chép nhãn. **Mục 1, 4, 5 trước đây ô `Actual`/`Loại RED` trong `M` đang trống** — F08 của ba mục này là **kết quả mới** của lượt này.

**Giữ nguyên số liệu lịch sử:** full acceptance vẫn **69 failed / 49 passed** (§A3.117); inventory **118 node / 76 hàm** (§A3.114); các snapshot 116/74 và 69/49 là lịch sử.

**An toàn:** SHA256 `T` = `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C` (không đổi). Không sửa test/core/probe/golden/R56/matrix/plan; các node R72-02 được **chạy lại** chỉ để lấy actual đầy đủ (5 node, không đổi trạng thái); không commit.

**Phạm vi:** chỉ `L` (mục này + hàng A3-084 + đính chính giới hạn hai node trong §A3.118).

**Trạng thái A3-084:** giữ **IMPLEMENTED**; **r1b-01 xong R72-01 (18/18, có giới hạn nêu tại §A3.118 mục 1)**, **r1b-02 xong R72-02 (5/5)**; **46 RED thuộc R72-03…09 còn chờ**. **Checkpoint A vẫn CHANGES_REQUESTED** — không tự PASS, không đóng finding nào.

### A3.120 — Phân loại 2 RED thuộc R72-03 (A3-084/r1b-03)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** inventory §A3.117 + contract/mapping R72-03 trong `M` + đọc trực tiếp node/helper trong `T` và probe `core/smc_sweep_linking.py` (**chỉ đọc**). **Giới hạn:** chỉ **R72-03**; sau lượt này **44 RED thuộc R72-04…09 chưa phân loại**. Không sửa test/core.

**Nguyên tắc:** precondition ghi theo **điều đã được xác minh**, không suy từ số dòng assert. Loại lỗi và F-code suy từ **giá trị actual đo được**, không từ tên nhóm hay nhãn cũ. Hai node này **không** đọc phần tử `[0]` của danh sách (dùng `next(...)` theo `setup_id` và tra key `"sweep"`), nên **không** có vấn đề “vị trí list”. Claim của fixture đi qua **helper compatibility** (`_probe.claim`) và node **không** đòi canonical lineage — đúng như contract hiện hành, **không** tính là thiếu sót.

**Bảng phân loại 2/2 ID (khớp tập R72-03 FAILED ở §A3.117, không thiếu/thừa/trùng):**

| # | Full node ID | Rule | Precondition đã chạy (điều đã xác minh) | Assertion đầu fail + actual | Expected | Loại lỗi | F-code | Assertions phía sau chưa chạy |
|---|---|---|---|---|---|---|---|---|
| 1 | `test_r72_03_acceptance_contribution_is_selected_within_owner_children` | F09: contribution chỉ được chọn **trong owner children** — owner-present tổng **1**, non-owner **0** | **Đã xác minh (3 điều, không phải đếm dòng):** (a) `"a-nonowner" < "z-owner"` — fixture thật sự để non-owner có zone ID nhỏ hơn (T:582); (b) `assignments["sweep"]["owner_setup_id"] == "early"` — **owner đúng** (T:586); (c) `non_owner_claim["contribution_applied"] is False` — non-owner **không** được credit (T:587) | `assert owner_claim["contribution_applied"] is True` → `assert False is True` | owner `"early"`/`z-owner` **được** credit ⇒ tổng contribution trên claims = **1** | implementation | **F09** | **2** — T:589 `sum(contribution_applied) == 1`, T:590 claim được credit là `"early"` |
| 2 | `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | F10: owner chỉ còn trong **history** giữ nguyên owner **và** assignment record; cửa sổ hiện tại không còn child ⇒ current contribution **0** | **Đã xác minh (1 điều):** `restored["claims"] == []` (T:1992) — cửa sổ hiện tại thật sự không còn child, nên vế “current contribution 0” **đúng** | `assert restored["assignments"]["sweep"] == first["assignments"]["sweep"]` → `KeyError: 'sweep'` (⇒ `restored["assignments"] == {}`) | assignment `"sweep"` của owner history-only **sống sót** qua lượt restore, bằng đúng bản `first` | implementation | **F10** | **1** — T:1994 `restored["assignments"]["sweep"]["owner_setup_id"] == "owner"` |

**Tổng hợp:** **F09 ×1**, **F10 ×1** — cả hai là **`implementation`**.

**Nguyên nhân gốc tại điểm fail (đo trực tiếp, read-only):**

- **Mục 1 — F09 (đính chính theo `core/smc_sweep_linking.py:394-424`):** `assign_sweep_ownership` chọn `contribution_winner[sweep_id]` trên **toàn bộ `normalized_claims`** — **không** giới hạn trong owner children — bằng khoá nhỏ nhất `candidate_key = (zone_id, visit_id, _claim_order)`. Ở fixture này `a-nonowner` thắng khoá. Khi chiếu xuống claim, điều kiện là **hội** của hai vế: `claim.setup_id == assignment.owner_setup_id` **và** `contribution_winner[sweep_id] == candidate_key của claim`. Hệ quả đúng như đo được: non-owner **thắng candidate_key nhưng bị vế owner chặn** ⇒ `False`; owner **không trùng winner** ⇒ `False`; nên **cả hai claim đều `contribution_applied == False`** (tổng trên claims = **0**) trong khi `assignments["sweep"]["contribution_applied"]` là `True`.
  - Đây **không** phải “non-owner được credit”. Mô tả cũ ở §A3.78 (“non-owner có ID nhỏ **chiếm** contribution slot”) **không bị bác bỏ** — non-owner **đúng là** thắng candidate_key. Điều mô tả cũ còn thiếu là **vế owner phía sau cũng chặn luôn owner**, nên **không ai** được credit.
  - Phân loại giữ **F09**: contract đã yêu cầu **owner-present tổng claim contribution = 1**, actual là **0** ⇒ vi phạm tiêu chí F09. Nguyên nhân là winner được chọn **ngoài phạm vi owner children**.
- **Mục 2 — F10:** `restored["assignments"] == {}` trong khi `first["assignments"]` có `"sweep"` ⇒ assignment của owner history-only **bị xoá** khi cửa sổ hiện tại không còn child. Vế “current contribution 0” **đúng** (`restored["claims"] == []` PASS), nên lỗi nằm ở việc **giữ assignment qua restore** ⇒ **F10**, không phải F09 dù node thuộc R72-03.

**Điểm chưa rõ / cần lưu ý (ghi nhận, KHÔNG sửa):**

1. **Cách đáp ứng contract khi sửa F09 (đính chính 2026-09-11, A3-084/r1b-04).** Contract đã yêu cầu **owner-present tổng claim contribution = 1**; vì vậy **hạ cờ `assignment.contribution_applied` xuống `False`** đơn thuần **không phải** cách đáp ứng contract — nó để tổng vẫn **0** và còn làm assignment mâu thuẫn thêm với claims. Lượt này **không** đề xuất và **không** khoá bất biến `assignment.contribution_applied ↔ tổng claim` vì bất biến đó **chưa được chốt**. Cách sửa thực chất là **giới hạn phạm vi chọn `contribution_winner` trong owner children** — thuộc **F09**, không làm ở đây.
2. **Không có defect test/fixture** được phát hiện ở cụm R72-03: mọi precondition đã chạy đều PASS và đúng kỳ vọng.

**Giữ nguyên số liệu lịch sử:** full acceptance vẫn **69 failed / 49 passed** (§A3.117); inventory **118 node / 76 hàm** (§A3.114).

**An toàn:** SHA256 `T` = `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C` (không đổi). Không sửa test/core/probe/golden/R56/matrix/plan; probe đọc trạng thái chỉ để lấy actual (không tạo/xoá file, không đổi test); không commit.

**Phạm vi:** chỉ `L` (mục này + hàng A3-084).

**Trạng thái A3-084:** giữ **IMPLEMENTED**; **r1b-01 R72-01 (18/18)**, **r1b-02 R72-02 (5/5)**, **r1b-03 R72-03 (2/2)** đã xong; **44 RED thuộc R72-04…09 còn chờ**. **Checkpoint A vẫn CHANGES_REQUESTED** — không tự PASS, không đóng finding nào.

### A3.121 — Phân loại 4 RED thuộc R72-04 (A3-084/r1b-04)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** inventory §A3.117 + contract/mapping R72-04 trong `M` + đọc trực tiếp node trong `T` và `core/smc_sweep_linking.py` (**chỉ đọc**). **Giới hạn:** chỉ **R72-04**; sau lượt này **40 RED thuộc R72-05…09 chưa phân loại**. Không sửa test/core.

**Nguyên tắc:** điều kiện ghi theo **điều đã xác minh bằng giá trị đo được**, không suy từ số dòng assert hay từ tên test. **Phân biệt tầng:** mục 1–2 chạy qua **caller thật** (`_probe.attach` = `_attach_zone_sweep_links`); mục 3–4 chạy trực tiếp **helper** `assign_sweep_ownership`. Cả 4 node đều **không** dùng `[0]` để chọn đối tượng (mục 1–2 đọc `swept_lows[0]` trên payload chỉ có **một** sweep do `_probe.sweep()` tạo — fixture bảo đảm một đối tượng, nên **không** tính là defect).

**Bảng phân loại 4/4 ID (khớp tập R72-04 FAILED ở §A3.117, không thiếu/thừa/trùng):**

| # | Full node ID | Rule | Điều kiện đã xác minh | Assertion đầu fail + actual | Expected | Loại lỗi | F-code | Assertions phía sau chưa chạy |
|---|---|---|---|---|---|---|---|---|
| 1 | `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` | A3-004 / A3-046: assignment + consumption đã ghi phải sống qua **replay** trên cùng payload | **1 điều (đo trực tiếp):** `prior["consumed"] is True` (T:597) — lượt 1 **thật sự** đã consumed; đo được `prior` owner `original-owner`, assignment `smca-81d0ce9b964b17bb3702` | `assert event["owner_setup_id"] == prior["owner_setup_id"]` → `'later-owner' == 'original-owner'` | giữ `original-owner` và cùng `assignment_id` sau lượt attach thứ hai | implementation — **caller** (`_probe.attach` = `_attach_zone_sweep_links`) | **F10** | **1** — T:601 `event["assignment_id"] == prior["assignment_id"]` |
| 2 | `test_r72_04_context_repeat_after_json_restore_keeps_assignment` | A3-078 / A3-046: vòng run → **JSON restore** → repeat trên caller thật; payload restore là bản độc lập | **2 điều (đo trực tiếp):** (a) T:2025 `restored is not sweeps`; (b) T:2027–2029 — payload **đã restore** vẫn giữ `original-owner` / `smca-81d0ce9b964b17bb3702` / `consumed True` **trước** lượt 2 | `assert repeated["owner_setup_id"] == first["owner_setup_id"]` → `'later-owner' == 'original-owner'` | giữ `original-owner`, cùng `assignment_id`/`linked_zone_id`/`claim_eligible_at`, `consumed` vẫn `True` | implementation — **caller** (`_probe.attach`) | **F10** | **4** — T:2036 `assignment_id`, T:2037 `linked_zone_id`, T:2038 `claim_eligible_at`, T:2039 `consumed is True` |
| 3 | `test_r72_04_same_pool_observation_cannot_bypass_consumption` | A-D06 / A3-045–047: observation **MỚI của cùng causal pool** không được né consumption; control pool **mới thật** không bị chặn nhầm | **7 điều (đo trực tiếp):** claim có `pool_id`/`source_ids` + hai mốc time (T:2077–2080); `reason_codes == []` (T:2083); owner `original`, `assignment_id` không rỗng, `claim_eligible_at == max(stamp(11),stamp(13))`, `assigned_at == claim_eligible_at` (T:2085–2089); history **JSON round-trip nguyên vẹn** (T:2090–2091); cùng `pool_id`/`source_ids`, khác `sweep_id`/`reclaimed_at`/`index` (T:2105–2109) | `assert result["assignments"]["sweep-later"]["owner_setup_id"] == "original"` → `'later' == 'original'` | giữ `original` và **cùng** `assignment_id`; claim muộn `contribution_applied is False` | implementation — **helper** (`assign_sweep_ownership`); history khớp theo `sweep_id`, `pool_id`/`source_ids` trên claim **không** được dùng | **F10** | **10** — T:2118 `assignment_id`, T:2119 `contribution_applied is False`, và **control pool mới** T:2133–2137 + T:2143–2145 |
| 4 | `test_r72_04_conflicting_assignment_history_fails_closed` | A-D06 fail-closed / A3-048: history **mâu thuẫn** ⇒ không cấp lại owner, không reset history, phải có reason **riêng của nhóm conflict** | **2 điều (đo trực tiếp):** (a) T:2161–2164 — claim canonical đủ hai mốc + `pool_id`/`source_ids`; (b) T:2173 `"SWEEP_OWNER_HISTORY_INCOMPLETE" not in reason_codes` **PASS** với `reason_codes == []` ⇒ vế phân nhóm đúng | `assert result["assignments"] == {}` → **có** assignment cho `sweep`: owner `late` (setup hiện tại), `assignment_id` `smca-30bb697d628ee9c39480`, `claim_eligible_at` `stamp(15)`, `contribution_applied True` | `{}` — không cấp owner mới cho sweep, history không bị reset | implementation — **helper** (`assign_sweep_ownership`) | **F10** | **1** — T:2178 `assert result["reason_codes"]` (reason riêng của nhóm conflict) |

**Tổng hợp: F10 ×4 — 4/4 là `implementation`.** Không phát hiện defect test/fixture. Cả 4 cùng một nhóm: **assignment/consumption không được giữ** — hoặc qua replay/restore ở **caller** (mục 1–2), hoặc qua **observation mới của cùng causal pool** và **history mâu thuẫn** ở **helper** (mục 3–4).

**Nguyên nhân gốc tại điểm fail (đo trực tiếp, read-only):**

- **Mục 1–2 — caller bỏ qua consumption đã ghi.** `_attach_zone_sweep_links` chạy lại trên payload đã có owner/assignment liền **cấp owner mới** cho setup đến sau (`later-owner`) kèm `assignment_id` **mới** (`smca-eb0c85c4…` thay `smca-81d0ce9b…`). Ở mục 2 điều này xảy ra **sau** JSON round-trip, tức payload restore **không** được coi là authoritative cho lượt kế tiếp.
- **Mục 3 — helper khớp history theo `sweep_id`, không theo lineage.** Claim mới mang đúng `pool_id="pool-1"`/`source_ids=["swing-1"]` nhưng mang `sweep_id` mới (`sweep-later`); helper không tìm thấy trong history nên **cấp assignment mới** (`owner_setup_id "later"`, `assignment_id` mới, claim `contribution_applied True`). Đúng luật A-D06 bị vi phạm: observation mới của cùng causal pool **không** được né consumption.
- **Mục 4 — helper bỏ qua history mâu thuẫn.** Với `assignment_history={"sweep": {...owner "original"}}` thiếu field để tôn trọng, helper **không** fail closed mà **cấp lại** sweep cho setup hiện tại (`late`) và trả `reason_codes == []` ⇒ vừa reset history vừa không báo reason riêng.

**Điểm chưa rõ / cần lưu ý (ghi nhận, KHÔNG sửa):**

1. **Mục 3 nêu căng thẳng với một node đang GREEN.** `test_r72_04_assignment_survives_json_restore_with_late_only_window` (xanh) cũng dựa vào history để giữ owner cũ khi cửa sổ chỉ còn claim muộn. Hai node vẽ ra hai đường khác nhau cho cùng bài toán “history phải sống qua observation mới” ⇒ khi sửa F10 cần làm hài hoà, **không** đánh đổi node này để làm xanh node kia.
2. **Mục 4: contract chưa nói rõ reason nào.** Node chỉ đòi `reason_codes` **không rỗng** và **khác** `SWEEP_OWNER_HISTORY_INCOMPLETE`; tên reason của nhóm conflict **chưa được chốt** trong `M`. Không khoá tên ở lượt này.
3. **Không** yêu cầu canonical lineage cho helper compatibility: mục 1–2 đi qua `_probe` (compatibility path) và node **không** đòi `pool_id`/`source_ids` ở đó — đúng contract hiện hành, không tính là thiếu sót.

**Giữ nguyên số liệu lịch sử:** full acceptance vẫn **69 failed / 49 passed** (§A3.117); inventory **118 node / 76 hàm** (§A3.114).

**An toàn:** SHA256 `T` = `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C` (không đổi). Không sửa test/core/probe/golden/R56/matrix/plan; probe chỉ đọc trạng thái để lấy actual; không commit.

**Phạm vi:** chỉ `L` (mục này + hàng A3-084 + đính chính cách diễn giải F09 trong §A3.120).

**Trạng thái A3-084:** giữ **IMPLEMENTED**; **r1b-01 R72-01 (18/18)**, **r1b-02 R72-02 (5/5)**, **r1b-03 R72-03 (2/2)**, **r1b-04 R72-04 (4/4)** đã xong; **40 RED thuộc R72-05…09 còn chờ**. **Checkpoint A vẫn CHANGES_REQUESTED** — không tự PASS, không đóng finding nào.

### A3.122 — Phân loại 6 RED thuộc R72-05 (A3-084/r1b-05)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** inventory §A3.117 + contract/mapping R72-05 trong `M` + đọc trực tiếp node trong `T` và `core/smc_confluence.py` (**chỉ đọc**). **Giới hạn:** chỉ **R72-05**; sau lượt này **34 RED thuộc R72-06…09 chưa phân loại**. Không sửa test/core.

**Nguyên tắc:** điều kiện ghi theo **giá trị đo được**, không suy từ tên test. **Phân biệt tầng lỗi:** `F03` = đồng bộ `invalid` state/usability (context → typed round-trip), `F05` = **D1 consumer** loại evidence của vùng terminal. Cái sai nằm ở **consumer** trả `valid=True` cho vùng terminal ⇒ **F05**, không phải F03. **Mức độ đã kiểm khác nhau theo mục (đính chính r1b-06):** mục 1–2 — node chỉ assert `lifecycle_broken` + `visit_state` (`invalidated_at` là số đo phụ của tôi, **không** được node kiểm); mục 5–6 — node assert được `state.invalidated_at` và `visits[0].reacted_at` (T:2247–2248) **cộng** prefix positive đã PASS; mục 3–4 — `lifecycle_status`/cờ là **payload khai tay trong fixture**, **không** phải output lifecycle đã được kiểm, nên mục 3–4 ghi thêm **dependency F03** (đồng bộ cờ `invalid`).

**Bảng phân loại 6/6 ID (khớp tập R72-05 FAILED ở §A3.117, không thiếu/thừa/trùng):**

| # | Full node ID | Rule | Điều kiện đã xác minh | Assertion đầu fail + actual | Expected | Loại lỗi | F-code | Assertions phía sau chưa chạy |
|---|---|---|---|---|---|---|---|---|
| 1 | `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[buy]` | F05: **D1 consumer** phải loại evidence của vùng terminal (A3-050/A-D04) | **2 assert của node đã chạy trước điểm fail:** T:611 `assert state.lifecycle_broken` và T:612 `assert state.visits[0].visit_state == "completed_reacted"` — node chỉ xác minh **vùng đã broken** và **visit đã reaction**, **không** assert `invalidated_at`/`expired_at`/status nào khác. (Ngoài node, tôi **đo riêng** `invalidated_at = 2026-09-05T00:00:00+00:00`, `expired_at = None` — đây là **số đo phụ**, **không** phải điều node đã kiểm.) | `assert evidence["valid"] is False` → `assert True is False` | `valid False`, `score 0` — terminal ⇒ không còn evidence hoạt động | implementation — **D1 consumer** (`build_d1_reaction_evidence`) | **F05** | **1** — T:619 `evidence["score"] == 0` |
| 2 | `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[sell]` | nt. (mirror SELL) | nt. — cùng **2 assert** (T:611 `lifecycle_broken`, T:612 `visit_state == "completed_reacted"`); số đo phụ `invalidated_at` như trên | `assert evidence["valid"] is False` → `assert True is False` | `valid False`, `score 0` | implementation — **D1 consumer** | **F05** | **1** — nt. |
| 3 | `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[buy]` | F05 (chính) + F03 (dependency): payload typed/serialized khai canonical `lifecycle_status="invalid"` lẫn cờ legacy `d1_reaction`/`proximity` = `True` ⇒ **canonical thắng**, consumer phải loại evidence | **Không có assert trước điểm fail** (T:2183–2198 là dựng payload + gọi consumer). Điều đã xác minh bằng cách đọc fixture: payload **cố ý** đặt `lifecycle_status="invalid"` cùng `lifecycle_broken=False`/`broken=False`/`d1_reaction=True`/`proximity=True` | `assert evidence["valid"] is False` → `assert True is False` | `valid False`, `score 0` — canonical terminal thắng cờ legacy | implementation — **D1 consumer**; dependency **F03** (đồng bộ `invalid` state/usability: payload còn cờ mâu thuẫn là phạm vi F03) | **F05** (dep **F03**) | **1** — T:2200 `evidence["score"] == 0` |
| 4 | `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[sell]` | nt. (mirror SELL) | nt. — cùng payload/cùng kết quả | `assert evidence["valid"] is False` → `assert True is False` | `valid False`, `score 0` | implementation — **D1 consumer**; dependency **F03** | **F05** (dep **F03**) | **1** — nt. |
| 5 | `test_r72_05_cutoff_equal_invalidated_at_is_terminal[buy]` | F05: **cutoff bằng đúng `invalidated_at`** vẫn là terminal (A3-050/A-D04; biên bao gồm) | **4 điều (đo trực tiếp):** candles hợp lệ (T:2217); **prefix positive** — `prefix_visit.visit_state == "completed_reacted"` + `reacted_at == prefix_cutoff` (T:2228–2229) và evidence prefix **`valid True`/`score > 0`/đúng `zone_id`/`source_visit_id`** (T:2234–2237); `state.invalidated_at == start+4d` (T:2247); `state.visits[0].reacted_at == prefix_cutoff` — history reaction **được giữ** (T:2248) | `assert evidence["valid"] is False` → `assert True is False` | `valid False`, `score 0`, và reason **không** phải `D1_REACTION_NOT_COMPLETED_REACTED` (tức bị chặn vì **terminal**, không phải vì thiếu reaction) | implementation — **D1 consumer** (`build_d1_reaction_evidence`) | **F05** | **2** — T:2254 `evidence["score"] == 0`, T:2255 `"D1_REACTION_NOT_COMPLETED_REACTED" not in reason_codes` |
| 6 | `test_r72_05_cutoff_equal_invalidated_at_is_terminal[sell]` | nt. (mirror SELL) | nt. — cùng kết quả: `invalidated_at` đúng, `broken True`, visit `completed_reacted` với `reacted_at == stamp(4d)` | `assert evidence["valid"] is False` → `assert True is False` | `valid False`, `score 0` | implementation — **D1 consumer** | **F05** | **2** — nt. |

**Tổng hợp: F05 ×6** (mục 3–4 kèm **dependency F03**) — **6/6 là `implementation`**. Không phát hiện defect test/fixture.

**Giá trị đo được (read-only, cùng nhau):**

```text
mục 1–2  (typed `_probe.lifecycle`): broken=True ; visit0=completed_reacted ;
         invalidated_at=2026-09-05T00:00:00+00:00 ; expired_at=None
         evidence → valid=True , score=1.0 , reason_codes=['D1_REACTION_COMPLETED_REACTED']
mục 3–4  (payload serialized, canonical invalid + cờ legacy True):
         evidence → valid=True , score=1.0 , reason_codes=['D1_REACTION_COMPLETED_REACTED']
mục 5–6  (D1, cutoff == invalidated_at):
         invalidated_at=2026-09-05T00:00:00+00:00 ; broken=True ;
         visit0=completed_reacted ; reacted_at=2026-09-04T00:00:00+00:00
         evidence → valid=True , score=1.0 , reason_codes=['D1_REACTION_COMPLETED_REACTED']
```

**Nguyên nhân gốc tại điểm fail:** `build_d1_reaction_evidence` **không** coi trạng thái terminal (`invalidated_at`/`lifecycle_status="invalid"`) là chặn — nó vẫn phát evidence từ visit `completed_reacted` với `score 1.0` và reason `D1_REACTION_COMPLETED_REACTED`. Cả 6 node dừng ở **đúng cùng một assertion** `evidence["valid"] is False`.

**Điểm chưa rõ / cần lưu ý (ghi nhận, KHÔNG sửa):**

1. **Không mâu thuẫn với node anh em đang GREEN.** `test_r72_05_cutoff_equal_expired_at_is_terminal[buy/sell]` **PASS** (nhóm R72-05: 2 PASS / 6 FAIL). Đó là **đường terminal khác** (`expired_at`) và fixture khác (`_terminal_candles`, cutoff tại `expired_at`) — core hiện **có** chặn nhánh expiry nhưng **không** chặn nhánh invalidation. Ghi nhận như **bất đối xứng giữa hai loại terminal**, không phải test defect.
2. **Mục 3–4: hợp đồng “canonical thắng cờ legacy” chưa được `M` gán F-code.** `M` L121 mô tả expected “serialized canonical `lifecycle_status=invalid` plus legacy reaction/proximity true ⇒ invalid/0” nhưng cột Loại RED chỉ ghi `RED`. Lượt này gán **F05** tại điểm fail + **dependency F03**; nếu TL muốn coi phần cờ mâu thuẫn là **F03 primary**, cần chốt lại — **chưa** làm ở đây.
3. **Đính chính (A3-084/r1b-06): mục 1–2 CÓ 2 assert chạy trước điểm fail** — T:611 `assert state.lifecycle_broken` và T:612 `assert state.visits[0].visit_state == "completed_reacted"` (đọc lại node T:605–619). Câu cũ trong mục này nói “không có assert nào trước điểm fail” là **sai** và đã được thay. **Đồng thời không suy toàn bộ trạng thái lifecycle là đúng chỉ từ `broken`**: node **chỉ** kiểm `lifecycle_broken` + `visit_state`; `invalidated_at` là **số đo phụ** của tôi, **không** được node kiểm. Riêng mục 3–4, `lifecycle_status`/cờ là **payload khai tay trong fixture**, **không** phải output lifecycle đã được kiểm — nên câu “trạng thái lifecycle đã đúng” ở phần tổng hợp **không** áp dụng cho mục 3–4.
4. **Prefix positive ở mục 5–6 nằm TRƯỚC điểm fail và đã PASS** (evidence prefix `valid True`, `score > 0`, đúng `zone_id`/`source_visit_id`) — nên RED **không** đến từ fixture thiếu reaction. Ở mục 5–6 **không** có positive control nào nằm sau điểm fail.

**Giữ nguyên số liệu lịch sử:** full acceptance vẫn **69 failed / 49 passed** (§A3.117); inventory **118 node / 76 hàm** (§A3.114).

**An toàn:** SHA256 `T` = `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C` (không đổi). Không sửa test/core/probe/golden/R56/matrix/plan; probe chỉ đọc để lấy actual; không commit.

**Phạm vi:** chỉ `L` (mục này + hàng A3-084).

**Trạng thái A3-084:** giữ **IMPLEMENTED**; **r1b-01 R72-01 (18/18)**, **r1b-02 R72-02 (5/5)**, **r1b-03 R72-03 (2/2)**, **r1b-04 R72-04 (4/4)**, **r1b-05 R72-05 (6/6)** đã xong; **34 RED thuộc R72-06…09 còn chờ**. **Checkpoint A vẫn CHANGES_REQUESTED** — không tự PASS, không đóng finding nào.

### A3.123 — Phân loại 12 RED thuộc R72-06 (A3-084/r1b-06)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** inventory §A3.117 + contract/mapping R72-06 trong `M` + đọc trực tiếp node/helper trong `T` và `core/` (**chỉ đọc**). **Giới hạn:** chỉ **R72-06**; sau lượt này **22 RED thuộc R72-07…09 chưa phân loại**. Không sửa test/core.

**Nguyên tắc:** nguyên nhân suy từ **giá trị đo được**, không từ tên nhóm hay nhãn cũ. Phân biệt ba tầng: **F04** = lifecycle chặn reaction tại/sau terminal, **F03** = đồng bộ `invalid` state/usability, **F05** = D1 consumer. Mỗi param BUY/SELL, D1/H4 được đo riêng.

**Bảng phân loại 12/12 ID (khớp tập R72-06 FAILED ở §A3.117, không thiếu/thừa/trùng):**

| # | Full node ID | Rule | Điều kiện đã xác minh | Assertion đầu fail + actual | Expected | Loại lỗi | F-code | Assertions/control phía sau chưa chạy |
|---|---|---|---|---|---|---|---|---|
| 1 | `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[buy]` | F04: reaction **không được vượt biên expiry** (A3-033/A-D05) — D1, cutoff tính theo **close** | **2 assert đã chạy:** T:629 `prefix.visits[0].visit_state == "completed_unreacted"` (prefix **thật sự chưa reaction**) và T:631 `state.lifecycle_expired` + `state.expiry_index == 21` — đo được `expired=True`, `expiry_index=21` | `assert state.visits[0].reacted_at is None` → `'2026-09-23T00:00:00+00:00' is None` | `reacted_at is None` và `visit_state == "completed_unreacted"` — nến reaction nằm **sau** biên expiry nên không tạo được reaction | implementation — **lifecycle** (`analyze_zone_lifecycle`) | **F04** | **1** — T:633 `visit_state == "completed_unreacted"` |
| 2 | `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[sell]` | nt. (mirror SELL) | nt. — đo được cùng kết quả: `expired=True`, `expiry_index=21`, `reacted_at=2026-09-23T00:00:00+00:00`, `visit_state=completed_reacted` | `assert state.visits[0].reacted_at is None` → `'2026-09-23T00:00:00+00:00' is None` | `reacted_at is None`, `completed_unreacted` | implementation — **lifecycle** | **F04** | **1** — nt. |
| 3 | `test_r72_06_h4_reaction_at_terminal_is_blocked[buy]` | F04: reaction đặt **đúng nến terminal** không được tạo — cổng terminal chạy **trước** reaction cùng nến (A3-035/A-D05); timeframe **H4** | **6 assert đã chạy:** T:2351 `expiry_index == 31`; T:2353–2355 `entered_at`/`exited_at`/`bars_spent_inside >= 1` (vùng **thật sự** được vào rồi ra); T:2356–2357 `lifecycle_expired is True` + `expired_at == terminal_close` | `assert visit.reacted_at is None` → `'2026-09-06T08:00:00+00:00' is None` | `reacted_at is None`, `visit_state == "completed_unreacted"` | implementation — **lifecycle** | **F04** | **1** — T:2359 `visit_state == "completed_unreacted"` |
| 4 | `test_r72_06_h4_reaction_at_terminal_is_blocked[sell]` | nt. (mirror SELL) | nt. — cùng 6 assert PASS; đo được `reacted_at=2026-09-06T08:00:00+00:00`, `visit_state=completed_reacted` | `assert visit.reacted_at is None` → `'2026-09-06T08:00:00+00:00' is None` | `reacted_at is None`, `completed_unreacted` | implementation — **lifecycle** | **F04** | **1** — nt. |
| 5 | `test_r72_06_h4_reaction_after_terminal_is_blocked[buy]` | F04: reaction đặt **sau nến terminal** không được tạo, và history trước terminal phải **được giữ** (A3-036/A-D05); timeframe **H4** | **6 assert đã chạy:** T:2379 `expiry_index == 31`; T:2381–2383 `entered_at`/`exited_at`/`bars_spent_inside`; T:2384–2385 `lifecycle_expired is True` + `expired_at == terminal_close` | `assert visit.reacted_at is None` → `'2026-09-06T12:00:00+00:00' is None` | `reacted_at is None`, `completed_unreacted`; nến sau terminal không đổi history | implementation — **lifecycle** | **F04** | **2** — T:2387 `visit_state == "completed_unreacted"`, T:2393 control `trimmed.visits[0] == visit` (bỏ nến sau terminal ⇒ history y hệt) |
| 6 | `test_r72_06_h4_reaction_after_terminal_is_blocked[sell]` | nt. (mirror SELL) | nt. — cùng 6 assert PASS; đo được `reacted_at=2026-09-06T12:00:00+00:00` | `assert visit.reacted_at is None` → `'2026-09-06T12:00:00+00:00' is None` | `reacted_at is None`, `completed_unreacted` | implementation — **lifecycle** | **F04** | **2** — nt. |
| 7 | `test_r72_06_terminal_order_before_reaction_is_explicit[21-buy]` | F04: thứ tự terminal-trước-reaction phải tường minh; reaction ở index **21** = **đúng biên lifetime** (A3-031/A3-032) — D1 | **6 assert đã chạy:** T:2422–2423 `entered_at`/`exited_at`; T:2424 `bars_spent_inside >= 1`; T:2425–2427 `lifecycle_expired is True`, `expiry_index == 21`, `expired_at == start+22d` | `assert visit.reacted_at is None` → `'2026-09-23T00:00:00+00:00' is None` | `reacted_at is None`, `completed_unreacted` | implementation — **lifecycle** | **F04** | **2** — T:2429 `visit_state == "completed_unreacted"`, T:2435 control `trimmed.visits[0] == visit` |
| 8 | `test_r72_06_terminal_order_before_reaction_is_explicit[21-sell]` | nt. (mirror SELL) | nt. — cùng 6 assert PASS; đo được `reacted_at=2026-09-23T00:00:00+00:00` | `assert visit.reacted_at is None` → `'2026-09-23T00:00:00+00:00' is None` | `reacted_at is None`, `completed_unreacted` | implementation — **lifecycle** | **F04** | **2** — nt. |
| 9 | `test_r72_06_terminal_order_before_reaction_is_explicit[22-buy]` | nt. — reaction ở index **22**, **sau** biên lifetime | **6 assert đã chạy:** nt. (cùng nhánh `else`) — `expiry_index == 21`, `expired_at == start+22d` | `assert visit.reacted_at is None` → `'2026-09-24T00:00:00+00:00' is None` | `reacted_at is None`, `completed_unreacted` | implementation — **lifecycle** | **F04** | **2** — nt. |
| 10 | `test_r72_06_terminal_order_before_reaction_is_explicit[22-sell]` | nt. (mirror SELL) | nt. — đo được `reacted_at=2026-09-24T00:00:00+00:00` | `assert visit.reacted_at is None` → `'2026-09-24T00:00:00+00:00' is None` | `reacted_at is None`, `completed_unreacted` | implementation — **lifecycle** | **F04** | **2** — nt. |
| 11 | `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-buy]` | F03: zone terminal giữ **status + usability** qua enrich → JSON → restore → enrich (A3-038/A-D04) | **2 assert đã chạy:** T:2510 `not validate_smc_candles(values, "D1")`; T:2528 `restored["zone_id"] == context["zone_id"]`. **Số đo phụ:** `lifecycle_broken=True`, `invalidated_at=2026-09-23T00:00:00+00:00`, `lifecycle_expired=False` — lifecycle **đã phát hiện** invalidation | `assert context["lifecycle_status"] == expected_status` → `'confirmed' == 'invalid'` | `lifecycle_status == "invalid"` (và `usable is False`) — canonical invalid thắng | implementation — **trạng thái/projection** (`enrich_zones` giữ `lifecycle_status='confirmed'` và `usable=True` dù đã `broken`) | **F03** | **12** — T:2530 `restored[...]`, T:2531 `usable is False`, T:2536–2537 history reaction, T:2540–2542 (`invalidated_at`/`invalidation_index`/`expired is False`), T:2553–2554 (D1 consumer `valid False`/`score 0`); T:2544–2546 thuộc nhánh `expired` |
| 12 | `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-sell]` | nt. (mirror SELL) | nt. — cùng 2 assert PASS; đo được `lifecycle_status='confirmed'`, `broken=True`, `invalidated_at=2026-09-23T00:00:00+00:00`, `usable=True` | `assert context["lifecycle_status"] == expected_status` → `'confirmed' == 'invalid'` | `lifecycle_status == "invalid"`, `usable is False` | implementation — **trạng thái/projection** | **F03** | **12** — nt. |

**Tổng hợp: F04 ×10** (mục 1–10), **F03 ×2** (mục 11–12) — **12/12 là `implementation`**. Không phát hiện defect test/fixture.

**Giá trị đo được (read-only, từng param):**

```text
mục 1–2   D1 expiry  : expired=True expiry_index=21
                       reacted_at=2026-09-23T00:00:00+00:00  visit_state=completed_reacted
mục 3–4   H4 idx31   : expiry_index=31 expired=True reacted_at=2026-09-06T08:00:00+00:00  completed_reacted
mục 5–6   H4 idx32   : expiry_index=31 expired=True reacted_at=2026-09-06T12:00:00+00:00  completed_reacted
mục 7–10  D1 idx21/22: expiry_index=21 expired=True
                       idx21 → reacted_at=2026-09-23T00:00:00+00:00 ; idx22 → 2026-09-24T00:00:00+00:00
mục 11–12 enrich D1  : lifecycle_status='confirmed' (phải 'invalid') ; usable=True (phải False)
                       broken=True ; invalidated_at=2026-09-23T00:00:00+00:00 ; lifecycle_expired=False
```

**Nguyên nhân gốc tại điểm fail:**

- **Mục 1–10 — F04 (lifecycle).** Ở cả 10 node, engine **đã** phát hiện terminal đúng (`lifecycle_expired`/`expiry_index`/`expired_at` đều khớp fixture, và vùng được vào/rồi ra thật), nhưng **vẫn tạo reaction** ở nến đúng-biên hoặc sau-biên: `visits[0].reacted_at` có giá trị và `visit_state = "completed_reacted"`. Cổng terminal **không** chạy trước reaction của cùng nến / nến sau đó ⇒ vi phạm A-D05 ⇒ **F04**.
- **Mục 11–12 — F03 (trạng thái/projection).** Lifecycle **đã** phát hiện invalidation (`broken=True`, `invalidated_at` đúng) nhưng `enrich_zones` giữ **`lifecycle_status='confirmed'`** và **`usable=True`** ⇒ trạng thái canonical `invalid` chưa được đồng bộ ra projection ⇒ **F03**. Lỗi **không** nằm ở consumer.

**Điểm chưa rõ / cần lưu ý (ghi nhận, KHÔNG sửa):**

1. **Bất đối xứng expiry ↔ invalidation được đo thấy, không suy đoán.** Cùng node, param **`expired` PASS** còn **`invalid` FAIL** (mục 11–12); và ở mục 7–10 param **index 20 PASS** còn **21/22 FAIL**. Điều này khớp với §A3.122 (nhánh `expired_at` đã được chặn, nhánh invalidation thì chưa) ⇒ **cùng một họ lỗi** chứ không mâu thuẫn.
2. **History reaction hợp lệ trước terminal ĐÃ được giữ** — đo được ở param `[20-*]` (PASS: `prefix.visits[0].reacted_at == expected` và `visit.reacted_at` giữ nguyên) và ở nhánh `expired` của mục 11–12. Vế này **không** phải nguyên nhân RED.
3. **Mục 3–10 dùng timeframe H4/D1 khác nhau** nhưng cho **cùng dạng actual** (reaction vẫn được tạo); đã đối chiếu riêng từng param, không gộp theo tên hàm.
4. **Control `trimmed.visits[0] == visit`** (mục 5–10) nằm **sau** điểm fail nên **chưa chạy** — vế “nến sau terminal không đổi history” chưa có bằng chứng từ lượt này.
5. **Không** kết luận gì về F05 ở cụm này: mục 11–12 có assert D1 consumer ở cuối nhưng nằm **sau** điểm fail, nên F05 của R72-06 **không** được xác nhận lẫn phủ nhận ở đây.

**Giữ nguyên số liệu lịch sử:** full acceptance vẫn **69 failed / 49 passed** (§A3.117); inventory **118 node / 76 hàm** (§A3.114).

**An toàn:** SHA256 `T` = `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C` (không đổi). Không sửa test/core/probe/golden/R56/matrix/plan; probe chỉ đọc để lấy actual; không commit.

**Phạm vi:** chỉ `L` (mục này + hàng A3-084 + đính chính precondition mục 1–2 trong §A3.122).

**Trạng thái A3-084:** giữ **IMPLEMENTED**; **r1b-01…r1b-05** đã xong (R72-01…05), **r1b-06 R72-06 (12/12)** đã xong; **22 RED thuộc R72-07…09 còn chờ**. **Checkpoint A vẫn CHANGES_REQUESTED** — không tự PASS, không đóng finding nào.

### A3.124 — Khép A3-084: phân loại 22 RED còn lại, R72-07…09 (A3-084/r1b-07…09)

**Ngày:** 2026-09-11 (Asia/Saigon). **Nguồn:** inventory §A3.117 + contract `M` + đọc trực tiếp node trong `T` và `core/` (**chỉ đọc**). **Giới hạn:** lượt này **khép A3-084** — 22 RED còn lại thuộc R72-07…09. Không sửa test/core.

**Bảng 22/22 ID (khớp tập R72-07…09 FAILED ở §A3.117, không thiếu/thừa/trùng):**

| # | Full node ID | Frame | Expected | Actual / điểm fail | Loại lỗi | F-code / giới hạn | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[buy]` | T:660 | `invalidation_buffer ≈ 0.1` | biến thể `argument_only` (item không khai tick, `tick_size=0.1` truyền qua argument) trả **0.0**; `item_only` trả đúng 0.1 | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle | §A3.117 mục 1 |
| 2 | `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[sell]` | T:660 | nt. | nt. (mirror SELL) | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle | §A3.117 mục 2 |
| 3 | `test_r72_07_item_and_argument_tick_sources_have_parity[buy]` | T:2582 | cả ba biến thể đạt cùng ngưỡng `0.1` (`item_only`/`argument_only`/`equal_both`) | `AssertionError: argument_only` — biến thể chỉ-có-argument không đạt; hai biến thể còn lại đạt | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle (A-D07) | §A3.117 mục 5 |
| 4 | `test_r72_07_item_and_argument_tick_sources_have_parity[sell]` | T:2582 | nt. | nt. (mirror SELL) | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle (A-D07) | §A3.117 mục 6 |
| 5 | `test_r72_07_missing_canonical_atr_is_unknown_and_unusable` | T:2610 | `metadata_state == "unknown"`, `metadata_reason` không rỗng, `usable is False`, `invalidation_buffer is None` | `KeyError: 'metadata_state'` — trường chưa tồn tại (precondition T:2598–2600 và `lifecycle_*`/`broken` T:2605–2607 đã PASS) | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle | §A3.117 mục 7 |
| 6 | `test_r72_07_missing_canonical_tick_is_unknown_and_unusable` | T:2649 | nt. (thiếu tick thay vì ATR) | `KeyError: 'metadata_state'`; precondition T:2637–2639 + T:2644–2646 PASS | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle | §A3.117 mục 8 |
| 7 | `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[expired_by_age]` | T:2697 | `metadata_state == "unknown"`, reason không rỗng, `invalidation_buffer is None` | `KeyError: 'metadata_state'`; precondition T:2683–2684 + terminal/history T:2689–2694 PASS | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle | §A3.117 mục 9 |
| 8 | `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[already_invalid]` | T:2697 | nt. | nt. | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle | §A3.117 mục 10 |
| 9 | `test_r72_07_metadata_survives_context_to_typed_round_trip` | T:2727 | context + typed/JSON đều giữ `unknown`/reason/`usable False` | `KeyError: 'metadata_state'`; precondition T:2720–2722 PASS | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle | §A3.117 mục 11 |
| 10 | `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]` | T:2765 | non-finite ⇒ `unknown`, `usable False`, `invalidation_buffer is None` | `ValueError: Invalid zone boundary: nan` — giá trị non-finite lọt tới biên zone thay vì bị chặn (precondition T:2761–2763 PASS) | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle | §A3.117 mục 12 |
| 11 | `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[tick_size]` | T:2765 | nt. | nt. | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle | §A3.117 mục 13 |
| 12 | `test_r72_07_conflicting_same_scope_tick_sources_fail_closed` | T:2805 | hai tick cùng scope mâu thuẫn ⇒ `unknown`, không giá trị nào thắng | `KeyError: 'metadata_state'`; precondition T:2792–2795 + T:2800–2802 PASS | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle (A-D07) | §A3.117 mục 14 |
| 13 | `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule` | T:3980 | ba override control đủ metadata PASS; khối thiếu-metadata khóa `unknown`/`None` | `AttributeError: 'ZoneLifecycle' object has no attribute 'metadata_state'` — nằm trong **khối thiếu-metadata** (sau hai cross-control đã PASS) | implementation | **F02** — metadata lifecycle đúng nguồn: `metadata_state`/`metadata_reason` chưa tồn tại trong payload `enrich_zones`; tick khai qua **argument** không được chuyển tiếp xuống lifecycle | §A3.117 mục 22; M L410 |
| 14 | `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[buy]` | T:686 | `lifecycle_broken is True`, `usable is False`, `lifecycle_status == "invalid"` | `assert result["usable"] is False` → `True is False`; T:685 `lifecycle_broken is True` **đã PASS** ⇒ phát hiện invalidation đúng nhưng `usable` không hạ | implementation | **F03** — đồng bộ `invalid` state/usability: canonical `invalid` chưa áp ra projection (status/`usable`/`broken`) | §A3.117 mục 3 |
| 15 | `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[sell]` | T:686 | nt. | nt. (mirror SELL) | implementation | **F03** — đồng bộ `invalid` state/usability: canonical `invalid` chưa áp ra projection (status/`usable`/`broken`) | §A3.117 mục 4 |
| 16 | `test_r72_08_invalid_canonical_zone_survives_typed_round_trip_consistently` | T:2858 | typed round-trip giữ `lifecycle_status="invalid"`, `broken True`, `usable False` | `KeyError: 'usable'` — khoá `usable` **biến mất** sau `SmcZone.from_dict(...).to_dict()`; T:2855–2857 PASS | implementation | **F03** — đồng bộ `invalid` state/usability: canonical `invalid` chưa áp ra projection (status/`usable`/`broken`) | §A3.117 mục 15 |
| 17 | `test_r72_08_canonical_invalid_status_wins_legacy_boolean[False]` | T:2874 | `restored.broken is True` — canonical `invalid` thắng cờ legacy `broken=False` | `assert False is True` — đo được `restored.lifecycle_status='invalid'` nhưng `restored.broken=False` (cờ legacy thắng). Param `[True]` **PASS** | implementation | **F03** — đồng bộ `invalid` state/usability: canonical `invalid` chưa áp ra projection (status/`usable`/`broken`) | §A3.117 mục 16 |
| 18 | `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` | T:3708 | `enriched["lifecycle_status"] == "invalid"` (và `usable is False`) | `assert 'confirmed' == 'invalid'` tại **tầng enrich**; prefix positive T:3701–3704 đã PASS ⇒ chuỗi D1 thật sự có reaction trước terminal | implementation | **F03** — đồng bộ `invalid` state/usability: canonical `invalid` chưa áp ra projection (status/`usable`/`broken`) (dep **F05**) | §A3.117 mục 21; M L442 |
| 19 | `test_r72_08_typed_terminal_projection_reaches_d1_consumer[buy]` | T:2912 | `evidence["valid"] is False`, `score == 0`, và reason không phải `NOT_COMPLETED_REACTED`/`AFTER_CUTOFF` | `assert evidence["valid"] is False` → `True is False`; đo được payload canonical `lifecycle_status='invalid'`/`broken=True` nhưng consumer trả `valid=True`, `score=1.0`, reason `D1_REACTION_COMPLETED_REACTED`; T:2907–2909 PASS | implementation | **F05** — D1 consumer chưa loại evidence của vùng terminal theo canonical payload | §A3.117 mục 17 |
| 20 | `test_r72_08_typed_terminal_projection_reaches_d1_consumer[sell]` | T:2912 | nt. | nt. (mirror SELL) | implementation | **F05** — D1 consumer chưa loại evidence của vùng terminal theo canonical payload | §A3.117 mục 18 |
| 21 | `test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[buy]` | T:3022 | canonical `invalid` thắng cờ legacy ⇒ consumer `valid False`/`score 0` | `assert evidence["valid"] is False` → `True is False`; precondition T:3005–3009 PASS | implementation | **F05** — D1 consumer chưa loại evidence của vùng terminal theo canonical payload | §A3.117 mục 19 |
| 22 | `test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[sell]` | T:3022 | nt. | nt. (mirror SELL) | implementation | **F05** — D1 consumer chưa loại evidence của vùng terminal theo canonical payload | §A3.117 mục 20 |

**Tổng hợp: F02 ×13, F03 ×5, F05 ×4 — 22/22 là `implementation`.** Không phát hiện defect test/fixture ở cụm này.

**Nguyên nhân chung theo nhóm (không lặp lại từng dòng):**

1. **F02 (13 node, R72-07) — hợp đồng metadata A3-007 chưa tồn tại.** `enrich_zones` **không** phát `metadata_state`/`metadata_reason` (mọi node dừng ở `KeyError: 'metadata_state'` hoặc `AttributeError` tương ứng trên `ZoneLifecycle`), **không** chuyển tiếp tick khai qua **argument** xuống lifecycle (`argument_only` ⇒ `invalidation_buffer = 0.0` trong khi `item_only` ⇒ `0.1`), và **không** chặn giá trị non-finite (lọt tới `ValueError: Invalid zone boundary: nan`). Ba biểu hiện này là **cùng một gap** — metadata lifecycle chưa được nối nguồn.
2. **F03 (5 node, R72-08 + R72-09) — canonical `invalid` chưa áp ra projection.** `enrich_zones` **đã phát hiện** invalidation (`lifecycle_broken=True` trong node `acceptance_invalidated_projection…`, `invalidated_at` trong §A3.123) nhưng vẫn để `usable=True`; `SmcZone.from_dict(...).to_dict()` **rơi mất khoá `usable`** và **để cờ legacy `broken=False` thắng** canonical `lifecycle_status="invalid"`; ở tầng enrich của chuỗi D1 (R72-09) `lifecycle_status` vẫn là `confirmed`.
3. **F05 (4 node, R72-08) — D1 consumer chưa đọc canonical payload.** Payload typed khai `lifecycle_status="invalid"`/`broken=True` (thậm chí kèm `invalidated_at`) nhưng `build_d1_reaction_evidence` vẫn trả `valid=True`, `score=1.0`, reason `D1_REACTION_COMPLETED_REACTED`.

**Phụ thuộc giữa các nhóm (ghi riêng, không gộp vào F-code):** F05 ở node 17–20 chỉ quan sát được **sau** khi F03 đồng bộ xong canonical `invalid` ra projection — nhưng **điểm fail** của chúng nằm ở consumer, nên phân loại theo F05. Ở node 21 (R72-09) điểm fail nằm ở **tầng enrich** ⇒ F03, với **dependency F05** cho vế consumer phía sau.

**Điều chỉnh so với nhãn cũ (theo evidence, không theo tên nhóm):**

- `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule` **giữ F02** (khớp `M` L410), và nay được xác nhận lại độc lập rằng fail nằm trong **khối thiếu-metadata** sau hai cross-control — **không** phải lỗi của các override control.
- `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` giữ **F03/F05** như `M` L442, nay ghi rõ **F03 là điểm fail**, F05 là dependency.

**Giữ nguyên giới hạn đã công bố:** hai node R72-01 `acceptance_source_must_be_usable_at_sweep_close[buy/sell]` **vẫn** ở trạng thái **F06/F07 chưa cô lập** (§A3.118, đính chính §A3.122) — **không** nâng thành kết luận trong lượt này.

**Đính chính §A3.122:** câu mâu thuẫn về precondition mục 1–2 đã được sửa ở lượt **r1b-06** bằng code thực tế (T:611–612 là **2 assert chạy trước điểm fail**; `invalidated_at` là số đo phụ, **không** phải điều node kiểm) — xác nhận lại trong lượt này, **không** sửa thêm.

**Giữ nguyên số liệu lịch sử:** full acceptance vẫn **69 failed / 49 passed** (§A3.117).

**An toàn:** SHA256 `T` = `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C`. Không sửa test/core/probe/golden/R56/matrix/plan; probe chỉ đọc để lấy actual.

**Trạng thái A3-084: HOÀN TẤT** — đủ **69/69 RED** đã phân loại (R72-01→05 §A3.118–§A3.122, R72-06 §A3.123, R72-07→09 §A3.124). **Checkpoint A vẫn CHANGES_REQUESTED** — không tự PASS, không đóng finding nào.

### A3.125 — Refresh A3-083 và A3-085…088 trên snapshot hiện hành

**Ngày:** 2026-09-11 (Asia/Saigon). **Interpreter:** `Python 3.11.9` (`/c/Users/tntan/AppData/Local/Programs/Python/Python311/python`), shell **Git Bash**; đều chạy từ `D:/Projects/AIMarketAnalyst`. **Snapshot:** đúng phiên bản test/core của §A3.117…§A3.124 — SHA256 `T` = `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C`.

**Đây là các lệnh chạy MỚI trong cùng lượt trình A lần4** trên cùng snapshot nói trên; không dẫn lại số cũ ở §A3.86/§A3.87 và **không** gọi là “không đổi” khi chưa đo.

| Mã | Nhóm | Command (rút gọn) | Actual |
|---|---|---|---|
| **A3-083** | Targeted factory + consumer | `pytest tests/test_smc_zone_lifecycle_task{59,60,63}.py tests/test_smc_fvg_fill_task62.py tests/test_smc_lifecycle_task65.py` | **32 passed** (5 file fixture đã sửa, không regression) |
| **A3-083** | Consumer của các factory | `pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q` rồi chạy cả file | **118 collected / 0 lỗi collection**; **69 failed, 49 passed** |
| **A3-085** | Reviewer probes nguyên bản | `pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=short` | **13 failed, 3 passed** |
| **A3-086** | Nhóm task57–71 (§5) | `pytest` 15 file `*task5[7-9]/task6[0-9]/task7[01]*` | **108 passed** |
| **A3-087** | Retained (loại acceptance) | `pytest` 66 file `test_smc*.py` trừ acceptance + 6 file integration | **854 passed** |
| **A3-088** | Full (có acceptance) | `pytest` 67 file `test_smc*.py` + 6 file integration | **69 failed, 903 passed** |

**Đối chiếu inventory — không dùng tổng count tăng để kết luận:**

```text
retained 854 + acceptance 118 = 972 = full (69 failed + 903 passed)   ✔ khớp
903 passed (full) − 854 passed (retained) = 49 = acceptance passed    ✔ khớp
69 failure trong full: 100% nằm trong test_smc_gate72_fix_acceptance.py
  (lọc `grep '^FAILED' | grep -v acceptance` ⇒ 0 dòng)                ✔ không mất test ngoài acceptance
số file: 66 + 6 = 72 (retained) và 67 + 6 = 73 (full); 118 node / 76 hàm (§A3.114)
```

**13 ID FAILED của reviewer probes (nguyên bản, không sửa probe):**

| # | Node |
|---|---|
| 1 | `test_r72_01_sweep_must_not_precede_source_confirmation[buy]` |
| 2 | `test_r72_01_sweep_must_not_precede_source_confirmation[sell]` |
| 3 | `test_r72_02_context_must_consider_earliest_eligible_setup_before_distance_rank` |
| 4 | `test_r72_03_nonowner_child_cannot_take_contribution_slot` |
| 5 | `test_r72_04_context_must_not_reassign_already_consumed_sweep` |
| 6 | `test_r72_05_broken_d1_lifecycle_cannot_supply_active_reaction[buy]` |
| 7 | `test_r72_05_broken_d1_lifecycle_cannot_supply_active_reaction[sell]` |
| 8 | `test_r72_06_expiry_candle_cannot_create_reaction_for_earlier_exit[buy]` |
| 9 | `test_r72_06_expiry_candle_cannot_create_reaction_for_earlier_exit[sell]` |
| 10 | `test_r72_07_enrich_must_forward_explicit_tick_to_lifecycle[buy]` |
| 11 | `test_r72_07_enrich_must_forward_explicit_tick_to_lifecycle[sell]` |
| 12 | `test_r72_08_invalidated_zone_must_not_keep_confirmed_usable_flags[buy]` |
| 13 | `test_r72_08_invalidated_zone_must_not_keep_confirmed_usable_flags[sell]` |

**Bổ sung / đính chính nhỏ so với hàng A3-083 cũ:** hàng cũ ghi consumer của năm factory là “**chỉ** `tests/test_smc_gate72_fix_acceptance.py`”. Quét lại trên snapshot này cho thấy **còn `docs/plans/probes/test_smc_gate72_review.py`** cũng tham chiếu các factory đó — probe là **artifact bảo vệ** và lượt chạy của nó là **A3-085** ở bảng trên. Ghi nhận để không hiểu nhầm rằng probe không dùng fixture đã sửa.

**Đối chiếu với review A lần3 §1:** probes **13 failed / 3 passed** trùng khớp. Retained và full **khác** số cũ vì **acceptance đã tăng 116 → 118 node** (thêm hai node A3-066/e và A3-043/b ở F01) — phần **retained không đổi 854**, `task57–71` **không đổi 108**, probe **không đổi 13/3**; đây là kỳ vọng, không phải regression.

**An toàn:** không sửa test/core/probe/golden/R56/matrix/plan; không skip/xfail; không commit.

**Trạng thái:** **A3-083, A3-085, A3-086, A3-087, A3-088 đều đã có bằng chứng chạy mới trên snapshot trình A lần4.**

### A3.126 — Khép A3-081: mapping case-level và đồng bộ matrix (A3-081/r1b)

**Ngày:** 2026-09-11 (Asia/Saigon). **Phạm vi:** `M` (điền `Actual`/`Loại RED`, header, kết luận §4) + `L`/`P` (hàng A3-081). **Không** sửa test/core/probe/golden/R56.

**Đối chiếu mapping với collection thật (118 node / 76 hàm):**

```text
ID trong 9 bảng tracking của M : 118 (sau khi loại 1 ghi chú đổi tên lịch sử) | duy nhất 118
collected thật                 : 118
M thiếu                        : không      M thừa (không collect được) : không
==> KHỚP 118/118
```

Ghi chú: tên `test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture` xuất hiện trong `M` chỉ là **ghi chú đổi tên** (A3-056 → `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke`), **không** phải node thừa.

**Điền ô trống:** **9 bảng tracking / 109 hàng** trước đó có **77 hàng** thiếu `Actual` **và** `Loại RED`. Nay điền từ evidence đã xác minh (§A3.118…§A3.124): **51 hàng RED** (kèm F-code + trỏ section) và **26 hàng GREEN** (`Actual = GREEN`, `Loại RED = —`) ⇒ **0 ô trống**, **0 hàng lệch cột**, **0 hàng trộn** (không hàng nào vừa RED vừa GREEN).

**Đồng bộ khác trong `M`:** header cập nhật trạng thái (A lần3 là lịch sử · bản trình A lần4 đang chờ TL) và số hiện hành **118 node / 76 hàm**; kết luận A3-063 (§4) được chú thích rõ **13 ĐỦ / 6 MỘT PHẦN / 2 THIẾU là ảnh chụp lịch sử** và các mã được giao (A3-064…A3-080) nay **đã IMPLEMENTED**.

**Sửa lỗi định dạng trong cùng lượt (đã kiểm):**

| File | Sửa | Còn lại |
|---|---|---|
| `L` | nối lại **2 hàng** mất `\|` cuối (A3-039, A3-041 — do lượt trước của tôi); escape pipe nằm trong văn bản ở **3 hàng** (A3-084/A3-085/A3-088) | **0** hàng lệch cột |
| `P` | nối lại **4 hàng** mất `\|` cuối (A3-039/040/041/082); gộp **ô trùng** ở **7 hàng** (A3-084…A3-090) | **0** hàng lệch cột |
| `M` | — | **3** hàng cũ (L73, L74, L172) — xem DEFERRED_OBSERVATION |

**DEFERRED_OBSERVATION:** `M` còn **3 hàng** (L73, L74, L172) có **một ô thừa** so với header bảng của chúng. **Có trước**, nằm trong các bảng tường thuật lịch sử (không thuộc 9 bảng tracking vừa điền) và **không** do lượt này tạo; nội dung hai ô khác nhau nên **không** sửa để tránh mất thông tin. Cùng loại: `smc-implementation-progress.md` **L87** (ô thừa, có trước — lượt này chỉ sửa L5/L9 của file đó). Không điều tra mở rộng.

**Trạng thái A3-081: HOÀN TẤT** (mapping khớp 118/118, ô trống đã điền, header/§4 đồng bộ).

### A3.127 — A3-089: kiểm phạm vi diff, hash và fingerprint trước trình

**Ngày:** 2026-09-11 (Asia/Saigon). **Không** reset/ghi đè bất kỳ thay đổi có trước nào.

**Phạm vi diff:**

```text
git status --porcelain      : 136 entry (12 tracked + 124 untracked) — khớp baseline "~135 entry dirty có trước" của review A lần3
git diff --stat (tracked)   : 12 file, 6807 insertions(+), 2730 deletions(-)
                              (6 core, 5 plan file bị xoá có trước, 1 tests/test_smc_context.py)
git diff --check            : exit=0 — không lỗi whitespace/conflict; chỉ còn cảnh báo LF→CRLF CÓ TRƯỚC
                              cho 7 file tracked (core/*.py + tests/test_smc_context.py)
untracked                   : không có file rác do lượt này tạo (đã xoá temp; `__pycache__` là bình thường)
```

**11 fingerprint bảo vệ (baseline F00/A3-001) — KHỚP 11/11:**

| # | Artifact | Kết quả |
|---|---|---|
| 1 | `core/smc_context.py` | OK |
| 2 | `core/smc_models.py` | OK |
| 3 | `core/smc_lifecycle.py` | OK |
| 4 | `core/smc_sweep_linking.py` | OK |
| 5 | `core/smc_confluence.py` | OK |
| 6 | `docs/plans/probes/test_smc_gate72_review.py` | OK |
| 7 | `tests/fixtures/smc_canonical/golden_cases.json` | OK |
| 8 | `docs/plans/smc-r56-01-session-contract.md` | OK |
| 9 | `docs/plans/smc-r56-01-coder-handoff.md` | OK |
| 10 | `tests/fixtures/smc_r56_01_session_acceptance.json` | OK |
| 11 | `tests/test_smc_r56_01_session_acceptance.py` | OK |

**Hash test trước/sau lượt:**

```text
tests/test_smc_gate72_fix_acceptance.py
  766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C   == giá trị dự kiến  ⇒ KHÔNG ĐỔI
```

**Toàn vẹn hồ sơ (sau khi sửa định dạng ở §A3.126):** `L` **0** hàng lệch cột / **0** section trùng; `P` **0** / **0**; `M` **3** hàng cũ (DEFERRED_OBSERVATION) / **0** section trùng. Không section `### A3.NNN` nào bị trùng số ở cả ba file.

**Trạng thái A3-089: HOÀN TẤT.**

### A3.128 — A3-090: bản trình checkpoint A lần4

**Ngày:** 2026-09-11 (Asia/Saigon). **Trạng thái trình:** `WAITING_REVIEW`. **Quyết định hiện hành vẫn là review A lần3** cho tới khi Tech Lead phản hồi; bản trình này **không** tự PASS checkpoint, **không** CLOSED finding, **không** APPROVED gate72, **chưa** làm F02/task73.

#### 1. Mapping năm finding A3R3 → sửa đổi → evidence

| Finding | Sửa đổi | Trạng thái | Evidence |
|---|---|---|---|
| **A3R3-01** A3-071 fixture context không thật sự ngoài khoảng cách | Context dùng candle input local ⇒ ATR caller **1.0**; từng zone assert eligibility **một mình qua chính caller**; thêm vế event-level và vế hai thứ tự | XONG (GREEN) | §A3.95, §A3.96, §A3.97 |
| **A3R3-02** A3-067 ngưỡng thiếu metadata bị khóa thành 0 | Bỏ oracle “thiếu metadata ⇒ fail-closed `0.0`”; khóa `metadata_state="unknown"` / `metadata_reason` / `invalidation_buffer is None`; thêm 2 cross-control; quét đồng bộ mô tả | XONG (control GREEN, phần thiếu-metadata RED **F02**) | §A3.98, §A3.99, §A3.100 |
| **A3R3-03** A3-061 positive control dùng snapshot tương lai | Thay bằng **prefix thật** (A3-060) và khóa “bản append kết thúc tại invalidation close, không rewind” | XONG (RED implementation **F03** giữ nguyên) | §A3.101, §A3.102 |
| **A3R3-04** A3-066 GREEN chưa chứng minh canonical pool identity | (a) cutoff theo `reclaimed_at`; (b) helper `_pool_record_for` + `_assert_pool_record_matches_source`; (c) nối `source_pool_id ↔ pool_id` cho prefix/batch; (d) rolling giữ `pool_id`/`source_ids`/`usable_at`; (e) thêm node permutation | XONG (ba node RED **F06**, phân loại đầy đủ) | §A3.103…§A3.107, §A3.109 |
| **A3R3-05** A3-043 + temporal controls reject nhầm phạm vi pool | (a) negative lọc theo **đúng level equal pool** + precondition phân biệt level; (b) thêm **single-source control**; (c) hai positive/negative temporal bỏ khóa toàn list, lọc theo level + candle index; (d) đưa temporal seam lên trước block canonical | XONG (/a RED **F07**, /b GREEN, A3-039/041 RED **F06** sau seam, A3-040 GREEN) | §A3.110, §A3.111, §A3.112, §A3.113 |

#### 2. Manifest và hash

```text
T = tests/test_smc_gate72_fix_acceptance.py
    766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C
inventory T (collect-only) : 118 node / 76 hàm def test_      (§A3.114, §A3.115)
L = docs/plans/smc-task-72-fix-progress.md   (mục §A3.103…§A3.128 + 2 hàng checklist + bản trình này)
M = docs/plans/smc-task-72-acceptance-matrix.md  (9 bảng tracking đã điền; header + §4 đồng bộ)
P = docs/plans/smc-task-72-fix-plan.md       (hàng A3-066/067/061/043/039/040/041/071/082/083/084/089/090)
11 fingerprint bảo vệ : KHỚP 11/11            (§A3.127)
```

#### 3. Bảng kết quả các nhóm kiểm chứng (chạy mới trên snapshot này — §A3.125)

| Nhóm | Command | Actual |
|---|---|---|
| Acceptance (collect) | `pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q` | **118 collected**, 0 lỗi collection |
| Acceptance (run) | `pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=short` | **69 failed / 49 passed** |
| Reviewer probes | `pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=short` | **13 failed / 3 passed** |
| Task57–71 (§5) | `pytest` 15 file | **108 passed** |
| Retained (loại acceptance) | `pytest` 66 + 6 file | **854 passed** |
| Full (có acceptance) | `pytest` 67 + 6 file | **69 failed / 903 passed** |
| Đối chiếu inventory | `854 + 118 = 972 = 69 + 903`; `903 − 854 = 49`; 0 failure ngoài acceptance | ✔ khớp |

`task57–71` và `retained` **không đổi** so với A lần3; `full` tăng tổng vì acceptance **116 → 118 node** (hai node thêm ở F01) — kỳ vọng, không regression.

#### 4. Phân loại toàn bộ RED (69/69 — A3-084 đã khép)

| F-code | Số RED | Nhóm | Evidence |
|---|---|---|---|
| **F02** | **13** | R72-07 — hợp đồng metadata A3-007 chưa tồn tại | §A3.124 |
| **F03** | **7** | R72-06 ×2 + R72-08 ×4 + R72-09 ×1 — canonical `invalid` chưa áp ra projection | §A3.123, §A3.124 |
| **F04** | **10** | R72-06 — reaction không bị chặn tại/sau terminal | §A3.123 |
| **F05** | **10** | R72-05 ×6 + R72-08 ×4 — D1 consumer chưa đọc canonical terminal | §A3.122, §A3.124 |
| **F06** | **13** | R72-01 — thiếu canonical `records` + fallback numeric | §A3.118, §A3.120 |
| **F06/F07 (chưa cô lập)** | **2** | R72-01 — hai node `acceptance_source_must_be_usable_at_sweep_close` | §A3.118 + đính chính §A3.122 |
| **F07** | **3** | R72-01 — cổng A-D01 `usable_at <= reclaimed_at` chưa áp | §A3.120 |
| **F08** | **5** | R72-02 — caller xếp hạng/tie-break sai khóa | §A3.119 |
| **F09** | **1** | R72-03 — contribution chọn winner ngoài owner children | §A3.120 |
| **F10** | **5** | R72-03 ×1 + R72-04 ×4 — assignment/consumption không được giữ | §A3.120, §A3.121 |
| **Tổng** | **69** | tất cả là **`implementation`** — **không** có test/fixture defect | §A3.118…§A3.124 |

**Regression:** **không có**. `task57–71` 108/108, retained 854/854, probe 13/3 — bằng đúng A lần3.

#### 5. Giới hạn còn lại (ghi để TL quyết, KHÔNG tự chốt)

1. **Hai node R72-01 chưa cô lập `F06/F07`.** Fixture source **không có `usable_at`**, nên chưa phân biệt được reject-do-thiếu-provenance với reject-thời-gian; **không** chốt quy tắc fallback `confirmed_at → usable_at`; hai node này **không** được tính là bằng chứng temporal gate đã được kiểm (§A3.118, §A3.122).
2. **Bất đối xứng `expired` ↔ `invalid`** đã đo thấy và ghi lại (nhiều node: param `expired` GREEN, param `invalid` RED) — là **cùng một họ lỗi**, không mâu thuẫn (§A3.122, §A3.123).
3. **Contract chưa chốt:** (a) tên reason của nhóm history-conflict (§A3.121); (b) tầng authority giữa `assignment.contribution_applied` và tổng claim (§A3.120 — **không** đề xuất bất biến mới); (c) `source_pool_kind` không nằm trong contract nào nên oracle **không** khóa (§A3.105).
4. **Assertion/control chưa chạy** ở một số node vì fail-fast — đã ghi riêng từng mục ở §A3.118…§A3.124.
5. **`M` còn 3 hàng lệch cột có trước** (L73/L74/L172) — DEFERRED_OBSERVATION ở §A3.126.

#### 6. Trạng thái các mục refresh

| Mã | Nội dung refresh | Trạng thái |
|---|---|---|
| A3-081 | Mapping case-level + đồng bộ `M` (118/118, điền 77 ô) | **HOÀN TẤT** (§A3.126) |
| A3-082 | Inventory acceptance 118 / 76 | HOÀN TẤT (§A3.114) |
| A3-083 | Targeted factory (32 passed) + consumer (118/69/49) | HOÀN TẤT (§A3.125) |
| A3-084 | Phân loại **69/69 RED** | **HOÀN TẤT** (§A3.118…§A3.124) |
| A3-085 | Reviewer probes 13 failed / 3 passed | HOÀN TẤT (§A3.125) |
| A3-086 | task57–71: 108 passed | HOÀN TẤT (§A3.125) |
| A3-087 | Retained: 854 passed | HOÀN TẤT (§A3.125) |
| A3-088 | Full: 69 failed / 903 passed | HOÀN TẤT (§A3.125) |
| A3-089 | Diff/hash/fingerprint | HOÀN TẤT (§A3.127) → **Chạy mới trên snapshot trình A lần4 (2026-09-11):** `git status` **136 entry** (khớp baseline ~135 có trước), `git diff --stat` 12 file tracked, `git diff --check` **exit=0** (chỉ cảnh báo LF→CRLF có trước); **11/11 fingerprint KHỚP**; SHA256 `T` **không đổi** `766EC04E…`; `L`/`P` **0** hàng lệch cột, `M` **3** hàng cũ (DEFERRED_OBSERVATION); **0** section trùng số ở cả ba file. Chi tiết: **§A3.127**. |
| A3-090 | Bản trình A lần4 | **WAITING_REVIEW** (mục này) → **Bản trình A lần4 ghép tại §A3.128 (2026-09-11) — trạng thái `WAITING_REVIEW`.** Gồm: mapping 5 finding A3R3 → sửa đổi → evidence; manifest + hash; bảng kết quả 6 nhóm kiểm chứng (acceptance 118/69/49 · probes 13/3 · task57–71 108 · retained 854 · full 69/903); phân loại **69/69 RED** (F02×13, F03×7, F04×10, F05×10, F06×13, F06/F07×2, F07×3, F08×5, F09×1, F10×5 — tất cả `implementation`, **không** regression); 5 giới hạn còn lại; bảng trạng thái refresh A3-081…090. **Quyết định A lần3 giữ lịch sử**; không tự PASS/CLOSED/APPROVED, chưa F02/task73. |

**Kết luận:** checkpoint A lần4 **đã đủ điều kiện trình** — 5/5 nhóm A3R3 có sửa đổi + bằng chứng, 69/69 RED đã phân loại, các nhóm kiểm chứng chạy mới trên cùng snapshot, 11/11 fingerprint nguyên vẹn, không regression. **Chờ Tech Lead review.** Không tự PASS/CLOSED/APPROVED; chưa F02/task73.

### A3.129 — Tech Lead review checkpoint A lần4: PASS

**Ngày:** 2026-09-11. **Quyết định:** PASS checkpoint A (F01 oracle/coverage/phạm vi), thay CHANGES_REQUESTED của A lần3. A3-090 IMPLEMENTED. Gate72 vẫn CHANGES_REQUESTED; R72-01…09 OPEN; chưa task73.

| Finding | Kết luận reviewer |
|---|---|
| A3R3-01 | Đạt: ATR caller thật, eligibility từng zone/event và permutation; outside-distance control GREEN. |
| A3R3-02 | Đạt: giữ controls override đủ nguồn; canonical thiếu metadata khóa unknown/None, không khóa zero. RED F02 được phép ở A. |
| A3R3-03 | Đạt: positive prefix thật, append tới invalidation; không rewind terminal snapshot. RED F03 được phép ở A. |
| A3R3-04 | Đạt: canonical record/source/time và liên kết pool→sweep được assert; reclaim-close cutoff, prefix/rolling/permutation kiểm identity. Fixture phân biệt sorted source IDs với causal order. RED F06 được phép ở A. |
| A3R3-05 | Đạt: temporal kiểm target equal pool, không khóa toàn bộ cardinality/priority; single-source control riêng; temporal seam trước assertion canonical. |

**Reviewer kiểm chứng trên snapshot trình:** full §5 **903 passed / 69 failed** (972; mọi failure trong acceptance); task57–71 **108 passed**; probes **13 failed / 3 passed**. Collection **118 node / 76 hàm**; mapping **118/118**, không thiếu/thừa/trùng (loại tên cũ trong ghi chú đổi tên H1 smoke). Acceptance **49 passed / 69 failed**; retained **854 passed** (903−49), không regression ngoài acceptance.

SHA256 T: `766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C`; **11/11** core/probe/golden/R56 fingerprint khớp ledger. Reviewer chỉ ghi quyết định trong bốn tài liệu hiện có, không sửa code/tests, không commit. Worktree trước ghi quyết định có **136 entry**, không coi136 bằng135 hoặc lấy số lượng file thay hash/diff. `git diff --check` exit0; cảnh báo LF/CRLF không phải lỗi whitespace.

**Giới hạn không blocking:** giữ hai node F06/F07 chưa cô lập, không tính là bằng chứng temporal độc lập; không chốt fallback confirmed_at→usable_at. Không thêm source_pool_kind hoặc invariant assignment-flag↔tổng-claim. F09 vẫn phải chọn winner trong owner children để owner-present tổng contribution1; history-conflict fail closed và reason phân biệt incomplete theo contract hiện hành. Assertions sau điểm fail chưa chạy không được báo PASS. Các lệch bảng lịch sử là DEFERRED_OBSERVATION. Evidence F06/F07 đọc §A3.118; tham chiếu §A3.120 trong bảng tóm tắt §A3.128 không phải evidence pool (§A3.120 là contribution/history).

**NEXT: F02 → F03 → F04 → F05 → trình checkpoint B**, theo §3 fix-plan và matrix đã duyệt. Coder tự chia bước nhỏ nội bộ, một root cause mỗi thay đổi; sau mỗi F cập nhật ledger ngắn (file, tests, actual, RED còn lại), rồi tiếp tục nếu không có blocker. Không làm lại90 mã hoặc mở task riêng cho từng chỉnh định dạng.

Trước trình B chạy targeted/cumulative, probes, task57–71 và full §5; không mất GREEN đã có. RED F06…F10 đã biết được giữ cho cụm C, không yêu cầu toàn69 RED xanh tại B. Fail mới lộ sau sửa phải phân loại theo contract/scope trước khi gọi regression. Chỉ dừng giữa cụm khi thiếu quyết định contract ảnh hưởng cách sửa hoặc regression không xử lý được trong scope; phát hiện khác ghi DEFERRED_OBSERVATION, không tự mở rộng.

Không sửa reviewer probes/R56/golden để làm xanh, không đổi scoring/công thức hoặc thêm tính năng/framework. **Dừng ở WAITING_REVIEW B; chưa F06/task73.** PASS A không phải APPROVED gate72.

### A3.130 — F02: metadata lifecycle đúng nguồn (R72-07)

**Ngày:** 2026-09-11 (Asia/Saigon). **Trạng thái F02:** **IMPLEMENTED** — kèm **BLOCKER** regression legacy (mục 5). **Chưa** PASS checkpoint B / CLOSED finding / APPROVED gate72.

**Baseline trước khi sửa:** acceptance **118 node**, **69 failed / 49 passed**; `r72_07` **13 failed / 6 passed**. Hash `core/smc_lifecycle.py` `AAB6B803…`, `core/smc_context.py` `D7550D1A…`, `core/smc_models.py` `AE630F7B…`; `T` `766EC04E…`.

#### 1. Thay đổi (chỉ code/model/adapter của F02)

| File | Thay đổi |
|---|---|
| `core/smc_lifecycle.py` | Thêm reason constants (`SMC_METADATA_ATR_UNAVAILABLE`/`_TICK_UNAVAILABLE`/`_NONFINITE`/`_SOURCE_CONFLICT`) + `METADATA_AVAILABLE`/`METADATA_UNKNOWN`; `_finite_metadata` (không raise, trả reason); `_resolve_threshold` dùng chung cho `_resolve_zone_tolerance`/`_resolve_break_buffer`, **trả `(value\|None, reason\|None)`** — explicit override thắng trước, conflict ⇒ unknown, thiếu/nonfinite ⇒ `None` + reason; `ZoneLifecycle` thêm `metadata_state`/`metadata_reason`/`tick_size_source`/`atr_source` và đổi `invalidation_buffer: float \| None = None`; `analyze_zone_lifecycle` nhận `tick_conflict`/`tick_size_source`/`atr_source`/`declared_terminal`; `_invalidates` nhận `buffer: float \| None` (None ⇒ **không** bao giờ invalidate); `_follow_through_reaction_at` nhận cùng kiểu. |
| `core/smc_context.py` | `enrich_zones` giải quyết **item tick vs argument tick** cùng scope (bằng ⇒ parity, một nguồn ⇒ dùng nguồn đó, khác ⇒ `tick_conflict=True` + không bên nào thắng) rồi forward xuống lifecycle; truyền `tick_size_source`/`atr_source` xuyên qua nếu caller khai; `declared_terminal` suy từ payload khai `broken`/`lifecycle_status ∈ {invalid, expired}`; projection đặt `usable = False` khi `metadata_state == "unknown"`. |
| `core/smc_models.py` | `SmcZone` thêm `metadata_state`/`metadata_reason`/`tick_size_source`/`atr_source` (default `"available"`/`None`) và đọc lại trong `from_dict` ⇒ sống qua typed round-trip. |

**Quy tắc đã áp đúng contract A3-007:**

1. Threshold không tính được ⇒ **`None`**, **không** `0`, **không** `NaN`; không dùng `digits`/`point`, không lấy ATR tương lai/latest.
2. `metadata_state="unknown"` + `metadata_reason` không rỗng; **unknown không phải lifecycle status** (`lifecycle_status` giữ nguyên).
3. Chưa có bằng chứng terminal ⇒ unknown **chỉ hạ `usable`**, **không** tự tạo `broken`.
4. Payload **đã khai** terminal (`broken`/`invalid`/`expired`) ⇒ bằng chứng đó **thắng**: dùng biên vùng **không buffer** để tái dựng history mà khai báo hàm ý; `invalidation_buffer` báo cáo vẫn là `None`.
5. Explicit override chỉ miễn metadata **của rule tương ứng** (override `zone_tolerance` không cứu requirement của break buffer ⇒ vẫn `unknown`).
6. `metadata_state`/`metadata_reason` đi xuyên lifecycle → context → typed (`SmcZone`) → JSON.

#### 2. Kết quả trước → sau

```text
r72_07              : 13 failed /  6 passed  →   1 failed / 18 passed
full acceptance     : 69 failed / 49 passed  →  57 failed / 61 passed
  GREEN mới         : 12 node (0 RED mới)
  12 node           : explicit_tick[buy/sell], item_and_argument_tick_sources_have_parity[buy/sell],
                      lifecycle_threshold_overrides_only_replace_their_own_rule, missing_canonical_atr,
                      missing_canonical_tick, nonfinite[atr_current], nonfinite[tick_size],
                      unknown_metadata_does_not_revive_terminal_zone[already_invalid], [expired_by_age]
reviewer probes     : 13 failed /  3 passed  →  11 failed /  5 passed   (2 probe GREEN thêm)
task57–71           : 108 passed             →   4 failed / 104 passed   (XEM MỤC 5 — regression)
retained            : 854 passed             → 849 passed / 5 failed    (regression)
full §5 (72+6 file) : 69 failed / 903 passed →  62 failed / 910 passed
```

**RED còn lại của r72_07 (1 node):** `test_r72_07_metadata_survives_context_to_typed_round_trip` — dừng ở `restored["usable"]` với `KeyError: 'usable'`. Phần **F02** của node (metadata_state/metadata_reason qua context → typed → JSON) **đã đạt**; khoá `usable` **chưa tồn tại trên `SmcZone`** và `M` §5 ghi rõ việc bổ sung thuộc **F03/R72-08**, không thuộc metadata ⇒ đây là **dependency F03**, không phải F02 còn thiếu.

#### 3. Command/kết quả thật

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_07"      → 1 failed, 18 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no                 → 57 failed, 61 passed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no             → 11 failed, 5 passed
python -m pytest <15 file task57–71> -q --tb=no                                     → 4 failed, 104 passed
python -m pytest <66+6 file retained> -q --tb=no                                    → 5 failed, 849 passed
python -m pytest <67+6 file full §5> -q --tb=no                                     → 62 failed, 910 passed
```

#### 4. Hash sau sửa

```text
tests/test_smc_gate72_fix_acceptance.py  766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C  (KHÔNG ĐỔI)
core/smc_lifecycle.py                    74D570CADEFAC0E6CAD41B4288CC63F88C450064745A0041592C6EF399DD56C5
core/smc_context.py                      E1EDD03B14376B3E455E33E4BB0BC9445420EA4707B84D5EBDDE466FA0FC77D3
core/smc_models.py                       B31D4A930B50908C85D474694BB22C58CCCD93F136C098C7F3BCD9E3312A5808
```

(Các fingerprint còn lại của F00 — probe/golden/R56 — **không** bị sửa; 3 file trên là core của F02 nên ledger F00 phải cập nhật khi trình checkpoint B.)

#### 5. **BLOCKER** — regression legacy không giải quyết được trong scope

**5 node Green trước đây nay FAILED**, tất cả cùng một nguyên nhân:

| Node | File |
|---|---|
| `test_first_invalidation_is_terminal_for_the_lifecycle` | `tests/test_smc_zone_lifecycle.py` |
| `test_invalidation_before_reaction_has_priority` | `tests/test_smc_zone_lifecycle_task60.py` |
| `test_invalidation_while_visit_open_closes_visit_without_reaction` | `tests/test_smc_zone_lifecycle_task60.py` |
| `test_invalidation_wins_over_expiry_on_same_candle` | `tests/test_smc_zone_lifecycle_task64.py` |
| `test_invalidation_before_lifetime_does_not_become_later_expiry` | `tests/test_smc_zone_lifecycle_task64.py` |

**Nguyên nhân (đo trực tiếp):** cả 5 gọi `analyze_zone_lifecycle` **trực tiếp, không khai `tick_size`** (task60 chỉ truyền `atr_current=2.0`; task64 không truyền cả hai) rồi khẳng định `lifecycle_broken is True` / `invalidation_index == 31`. Đo được `metadata_state='unknown'`, `metadata_reason='SMC_METADATA_TICK_UNAVAILABLE'`, `invalidation_buffer=None` ⇒ theo contract **sửa** ở §2 mục 1/3, buffer `None` **không** được suy ra invalidation ⇒ `broken` giữ `False`. Đây **không** phải RED F03…F10 đã biết, mà là test cũ mã hoá **hành vi tiền-F02** (“thiếu tick ⇒ buffer `0.0`”) — đúng thứ `M` §6 đánh dấu là **Sai**.

**Vì sao không tự xử lý:** hai đường duy nhất đều ngoài phạm vi được giao —
(a) sửa fixture test cũ để khai `tick_size` (là **sửa test**, lượt này bị cấm); hoặc
(b) nới contract cho trường hợp thiếu tick (sẽ phá `test_r72_07_missing_canonical_tick_is_unknown_and_unusable` và `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule` vừa GREEN, tức đảo ngược chính F02).
Giữ nguyên bản sửa **đúng contract** và **dừng** theo đúng luật “regression không giải quyết được trong scope”.

**Ảnh hưởng:** không có RED mới trong acceptance (12 GREEN, 0 RED mới); regression **chỉ** ở 5 node legacy gọi lifecycle thiếu tick. `T` **không đổi** nên oracle đã duyệt không bị đụng.

#### 6. DEFERRED_OBSERVATION

- `smc-implementation-progress.md` L87 và `M` L73/L74/L172 vẫn còn ô thừa **có trước** (đã ghi ở §A3.126) — không điều tra thêm.

#### 7. Phạm vi

Chỉ `core/smc_lifecycle.py`, `core/smc_context.py`, `core/smc_models.py` (code F02) + `fix-plan.md`, `fix-progress.md`, `acceptance-matrix.md` (hồ sơ). Giữ nguyên dirty changes có trước; **không** commit/reset/xoá; **không** sửa probe/R56/golden/`T`; không skip/xfail.

**F02: IMPLEMENTED** (kèm blocker ở mục 5). **NEXT_TASK = F03**, chưa thực hiện.

### A3.131 — F02/r1: khép 5 regression fixture bằng metadata synthetic tường minh

**Ngày:** 2026-09-11 (Asia/Saigon). **Quyết định TL:** cho phép bổ sung metadata synthetic **đúng 5 fixture** đã nêu, giữ nguyên OHLC/timeline/assertion. **Trạng thái blocker §A3.130:** **ĐÃ HẾT** — không còn regression.

**Phạm vi:** chỉ 3 file test. **Không** sửa core/acceptance/probe/golden/R56.

#### 1. Bảng old → new → expected (chứng minh bằng số từ fixture)

Buffer sau khi cấp metadata: `max(1 × tick, 0.05 × ATR) = max(0.1, 0.05 × 2.0) = max(0.1, 0.1) = **0.1**`.
Ngưỡng invalidation BUY = `zone_low − 0.1 = 99.9`; các nến invalidation đều đóng **98** hoặc **99**, tức **vượt ngưỡng** ⇒ index/precedence/history giữ nguyên.

| # | File | Fixture (nến invalidation) | Old | New | Expected |
|---|---|---|---|---|---|
| 1 | `test_smc_zone_lifecycle.py::test_first_invalidation_is_terminal_for_the_lifecycle` | idx3 `(99, 99, 97, 98)` close **98** < 99.9 | `_lifecycle(_candles([...]))` (helper không khai metadata) | `_lifecycle(_candles([...]), tick_size=0.1, atr_current=2.0)` | `broken True`, `invalidation_index == 3`, `independent_retest_count == 1`, `bars_spent_inside == 1` |
| 2 | `task60.py::test_invalidation_before_reaction_has_priority` | `(99, 100, 98, 99)` close **99** < 99.9 | `_lifecycle(candles)` (helper đã có `atr_current=2.0`) | `_lifecycle(candles, tick_size=0.1)` | `broken True`, visit `completed_unreacted`, `reacted_at is None` |
| 3 | `task60.py::test_invalidation_while_visit_open_closes_visit_without_reaction` | `(99, 100, 98, 99)` close **99** < 99.9 | nt. | nt. | `broken True`, visit `closed_by_invalidation`, `reacted_at is None` |
| 4 | `task64.py::test_invalidation_wins_over_expiry_on_same_candle` | idx31 `(99, 100, 98, 99)` close **99** < 99.9 | `_lifecycle(candles)` (helper không khai metadata) | `_lifecycle(candles, tick_size=0.1, atr_current=2.0)` | `invalidation_index == 31`, `broken True`, `lifecycle_expired is False`, `expiry_index is None`, `expired_at is None` |
| 5 | `task64.py::test_invalidation_before_lifetime_does_not_become_later_expiry` | idx5 `(99, 100, 98, 99)` close **99** < 99.9 | nt. | nt. | `broken True`, `invalidation_index == 5`, `lifecycle_expired is False`, `expiry_index is None` |

**Không lấy output core làm expected:** mọi giá trị trên suy từ fixture (`close` và vùng `[100, 110]`) cộng công thức buffer đã duyệt; expected là các con số **có sẵn trong assertion gốc**, không đổi.

**Thay đổi ở helper:** chỉ `tests/test_smc_zone_lifecycle.py` cần thêm hai keyword optional (`tick_size`/`atr_current`, mặc định `None`) để forward — **mặc định giữ nguyên hành vi các test khác**. Hai file `task60`/`task64` đã có `**kwargs` nên **không** đụng helper; metadata chỉ đặt tại đúng call site.

#### 2. Command/kết quả thật

```text
5 node đích (chạy riêng)                        → 5 passed
3 file test (test_smc_zone_lifecycle + task60 + task64)  → 22 passed
r72_07                                          → 1 failed, 18 passed
acceptance (§5)                                 → 57 failed, 61 passed
probes                                          → 11 failed, 5 passed
task57–71                                       → 108 passed          ← regression ĐÃ HẾT
retained (loại acceptance)                      → 854 passed          ← regression ĐÃ HẾT
full §5                                         → 57 failed, 915 passed
```

**Đối chiếu baseline và sau F02:** full §5 đi `69 failed / 903 passed` (A lần4) → `57 failed / 915 passed`; `task57–71` và `retained` trở về **đúng** số cũ; acceptance **12 GREEN mới, 0 RED mới**. Không phát sinh regression khác.

#### 3. RED còn lại và assertion chưa chạy

- **F03 dependency (giữ nguyên, không sửa):** `test_r72_07_metadata_survives_context_to_typed_round_trip` dừng ở `assert restored["usable"] is False` → `KeyError: 'usable'` (T:2736). Phần **F02** của node **đã đạt** (`assert restored["metadata_state"] == "unknown"` và `metadata_reason` không rỗng đều PASS trước điểm fail).
  **Assertion phía sau CHƯA CHẠY:** T:2740 `restored["zone_id"] == "zone"`, T:2741 `(restored["low"], restored["high"]) == (100.0, 110.0)`, T:2742 `restored["lifecycle_status"] == "confirmed"`, T:2743 `len(restored["visits"]) == 1`.
- Các test canonical thiếu metadata **không bị sửa** và vẫn kiểm `unknown` + threshold `None`: `missing_canonical_atr_is_unknown_and_unusable`, `missing_canonical_tick_is_unknown_and_unusable`, `nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current|tick_size]`, `conflicting_same_scope_tick_sources_fail_closed`, `lifecycle_threshold_overrides_only_replace_their_own_rule` — tất cả **GREEN**.

#### 4. Hash sau F02/r1

```text
tests/test_smc_gate72_fix_acceptance.py   766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C  (KHÔNG ĐỔI)
docs/plans/probes/...review.py            5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6  (KHÔNG ĐỔI)
core/smc_lifecycle.py                     74D570CADEFAC0E6CAD41B4288CC63F88C450064745A0041592C6EF399DD56C5  (= F02)
core/smc_context.py                       E1EDD03B14376B3E455E33E4BB0BC9445420EA4707B84D5EBDDE466FA0FC77D3  (= F02)
core/smc_models.py                        B31D4A930B50908C85D474694BB22C58CCCD93F136C098C7F3BCD9E3312A5808  (= F02)
tests/test_smc_zone_lifecycle.py          2EEBA2CBB0023E650DD715A7AF4C9845937C2C793A4485178788A3DC1D2F01DF
tests/test_smc_zone_lifecycle_task60.py   03152CCB4A9554BE7BB66B7E52F8BB0D41E7BABA9EE8F98D8FCAEBD8D95AECA8
tests/test_smc_zone_lifecycle_task64.py   BDD8B29DA164B8FFEDE21842A4D9571B0CE0A074BBDD64E729AF87645CD174E5
```

#### 5. Blocker

**Không còn blocker.** Blocker ở §A3.130 (5 regression legacy) đã được khép đúng theo quyết định TL.

**Ghi nhận trung thực:** khi chèn metadata vào `task60`/`task64` tôi đã chèn tuần tự theo số dòng khiến lần chèn thứ hai rơi vào giữa lời gọi `_base_visit(...)`/`Candle(...)`, làm mất một dòng OHLC (`(99, 100, 98, 99),` và `volume=100,`). Đã phát hiện và **khôi phục nguyên trạng** hai dòng đó ngay trong lượt; vùng sửa đã được kiểm lại từng dòng và cả 3 file đều xanh (22 passed).

#### 6. Phạm vi

Chỉ 3 file test + `fix-plan.md`, `fix-progress.md`, `acceptance-matrix.md`. Giữ nguyên dirty changes có trước; **không** commit/reset/xoá; **không** skip/xfail; **không** chạm `T`/probe/golden/R56. Không mở rộng audit, không tạo tài liệu mới.

**F02: IMPLEMENTED** (blocker đã hết). **Chưa** PASS checkpoint B / CLOSED finding / APPROVED gate72. **NEXT_TASK = F03**, chưa thực hiện.

### A3.132 — F03: đồng bộ canonical terminal state/usability và typed round-trip (R72-08)

**Ngày:** 2026-09-11 (Asia/Saigon). **Trạng thái F03:** **IMPLEMENTED** — không phát sinh regression, không blocker. **Chưa** PASS checkpoint B / CLOSED finding / APPROVED gate72.

**Baseline vào lượt (sau F02/r1):** acceptance **57 failed / 61 passed**; cluster F03 targeted **12 failed / 7 passed**; probes **11F/5P**; task57–71 **108P**; retained **854P**; full §5 **57F/915P**.

#### 1. Thay đổi (chỉ code/model/adapter của F03)

| File | Thay đổi |
|---|---|
| `core/smc_context.py` | `enrich_zones` thêm **nhánh canonical terminal**: khi `lifecycle.lifecycle_broken` ⇒ `lifecycle_status="invalid"`, `usable=False`, `broken=True`, `lifecycle_broken=True`, giữ `invalidated_at`/`invalidation_index` từ lifecycle, thêm reason `ZONE_INVALIDATED`; nhánh `expired` chuyển thành `elif` ⇒ **invalidation thắng expiry** trên cùng một lần suy diễn. Các trường khác (`zone_id`, `origin_*`, bounds, `visits`, `setup_id`) vẫn đi qua `item.update(lifecycle.to_dict())` nên **history và identity được giữ**. Nhánh `metadata_state == "unknown"` giữ nguyên: hạ `usable` nhưng **không** đổi `lifecycle_status`. |
| `core/smc_models.py` | `SmcZone` thêm field `usable: bool = True` (đi cùng `to_dict` qua `asdict` và được `from_dict` đọc lại ⇒ **sống qua typed → dict → restore**); `__post_init__` áp **canonical thắng legacy**: `lifecycle_status == "invalid"` ⇒ ép `broken=True` + `usable=False` bất kể cờ legacy vào; `broken` ⇒ `usable=False` (không payload nào vừa `broken` vừa `usable`). |

**Đối chiếu contract F03 (fix-plan §F03 + `M` dòng 170–171):** status invalid + `usable False` + `broken` nhất quán; giữ timestamp/reason invalidation và visit history + original bounds/zone ID/setup; typed→dict→restore giữ `usable` và metadata; legacy flags **không** ghi đè canonical terminal; thiếu metadata ⇒ unknown/unusable, **không** tự thành invalid; control chưa invalid vẫn giữ trạng thái hợp lệ.

#### 2. Kết quả trước → sau

```text
cluster F03 targeted : 12 failed /  7 passed  →   5 failed / 14 passed
acceptance           : 57 failed / 61 passed  →  50 failed / 68 passed   (7 GREEN mới, 0 RED mới)
r72_07               :  1 failed / 18 passed  →  19 passed  ← F02 nay XANH HOÀN TOÀN
probes               : 11 failed /  5 passed  →   9 failed /  7 passed   (2 probe GREEN thêm)
task57–71            : 108 passed             → 108 passed              (không regression)
retained             : 854 passed             → 854 passed              (không regression)
full §5              : 57 failed / 915 passed →  50 failed / 922 passed (0 failure ngoài acceptance)
```

**7 node F03 vừa chuyển GREEN:**

| # | Node | Assertion nay chạy được |
|---|---|---|
| 1–2 | `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[buy/sell]` | `result["usable"] is False`, `result["lifecycle_status"] == "invalid"` |
| 3 | `test_r72_08_invalid_canonical_zone_survives_typed_round_trip_consistently` | `round_trip["usable"] is False` (trước: `KeyError: 'usable'`) |
| 4 | `test_r72_08_canonical_invalid_status_wins_legacy_boolean[False]` | `restored.broken is True` với `legacy_broken=False` |
| 5–6 | `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-buy/sell]` | `context["lifecycle_status"] == "invalid"` + toàn bộ control round-trip |
| 7 | `test_r72_07_metadata_survives_context_to_typed_round_trip` | `restored["usable"] is False` (F02→F03 dependency, nay đóng) |

**Assertion trước đây bị fail-fast che, nay chạy được** — ở node 3–7, các assert phía sau điểm fail cũ đã thực thi thật: `restored["lifecycle_status"] == "expected_status"`, `restored["usable"] is False`, `first_visits[0][0] == expected_reacted_at`, `second_visits == first_visits`, `restored["invalidated_at"]/["invalidation_index"]/["lifecycle_expired"]`, `restored["zone_id"]`, `(restored["low"], restored["high"])`, `len(restored["visits"]) == 1`. **Repeated enrichment/serialization** được kiểm ở cả node 5–6 (enrich → JSON → restore → enrich) và node 3–4/chỉ typed round-trip — tất cả PASS.

#### 3. Command/kết quả thật

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "<F03 cluster>"  → 5 failed, 14 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no                     → 50 failed, 68 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_07"         → 19 passed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no                 → 9 failed, 7 passed
python -m pytest <15 file task57–71> -q --tb=no                                         → 108 passed
python -m pytest <66+6 file retained> -q --tb=no                                        → 854 passed
python -m pytest <67+6 file full §5> -q --tb=no                                         → 50 failed, 922 passed
```

#### 4. RED còn lại (giữ nguyên, đúng scope)

- **F05 — D1 consumer (không đụng ở F03):** `typed_terminal_projection_reaches_d1_consumer[buy/sell]` (T:2912), `typed_invalid_projection_beats_conflicting_legacy_flags[buy/sell]` (T:3022), và **vế consumer** của `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` (nay dừng ở T:3711 `evidence["valid"] is False`, tức **phần F03** của node — `enriched["lifecycle_status"] == "invalid"` và `usable is False` tại T:3708–3709 — **đã PASS**).
- Không còn RED nào thuộc F03.

#### 5. Hash sau F03

```text
tests/test_smc_gate72_fix_acceptance.py   766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C  (KHÔNG ĐỔI)
docs/plans/probes/...review.py            5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6  (KHÔNG ĐỔI)
tests/fixtures/.../golden_cases.json      45437A90E540BF772E1E3F2899C06D328293181F19F9B36AA5E26C3170C79999  (KHÔNG ĐỔI)
core/smc_lifecycle.py                     74D570CADEFAC0E6CAD41B4288CC63F88C450064745A0041592C6EF399DD56C5  (= F02)
core/smc_context.py                       BBC1B829BB09235D29956FCB39BD7DDE61113857E59E456AE4AF5B0F0F5DBF80
core/smc_models.py                        AEE437971AE15BF4A0B6995A30A3ED3C9F903550FF20C394670E7D3D1C47794B
```

#### 6. DEFERRED_OBSERVATION

- `M` L71/L72/L170 và `smc-implementation-progress.md` L87 vẫn còn ô thừa **có trước** (§A3.126) — không điều tra thêm.

#### 7. Phạm vi

Chỉ 2 file core + `fix-plan.md`, `fix-progress.md`, `acceptance-matrix.md`. Không sửa D1 consumer (F05), reaction/expiry (F04), liquidity/ownership; không chạm `T`/probe/golden/R56; không skip/xfail; giữ dirty changes; không commit/reset/xoá.

**F03: IMPLEMENTED.** **NEXT_TASK = F04**, chưa thực hiện.

### A3.133 — F04: reaction không được cấp tại/sau terminal expiry (R72-06)

**Ngày:** 2026-09-11 (Asia/Saigon). **Trạng thái F04:** **IMPLEMENTED** — không blocker, không regression. **Chưa** PASS checkpoint B / CLOSED finding / APPROVED gate72.

**Baseline vào lượt (sau F03):** acceptance **50 failed / 68 passed**; `r72_06` **10 failed / 10 passed**; probe `r72_06` **2 failed**; probes tổng **9F/7P**; task57–71 **108P**; retained **854P**; full §5 **50F/922P**.

#### 1. Nguyên nhân đo được trước sửa

Cả 10 node và 2 probe dừng ở **cùng một dạng**: `reacted_at` có giá trị trong khi hợp đồng đòi `None`.

```text
terminal_order_before_reaction_is_explicit[21-*] : reacted_at = 2026-09-23T00:00:00+00:00  (phải None)
terminal_order_before_reaction_is_explicit[22-*] : reacted_at = 2026-09-24T00:00:00+00:00  (phải None)
acceptance_reaction_cannot_cross_expiry_boundary : reacted_at = 2026-09-23T00:00:00+00:00  (phải None)
h4_reaction_at_terminal_is_blocked               : reacted_at = 2026-09-06T08:00:00+00:00  (phải None)
h4_reaction_after_terminal_is_blocked            : reacted_at = 2026-09-06T12:00:00+00:00  (phải None)
probe expiry_candle_cannot_create_reaction_for_earlier_exit[buy|sell] : cùng dạng
```

**Gốc:** `_follow_through_reaction_at` quét `exit_index … exit_index + 3` **không** biết biên lifetime, nên một exit ở age 20 lấy được nến **terminal 21** (age 21 > lifetime 20) hoặc nến 22 làm nguồn reaction — reaction “prospective” vượt mốc expiry. Vòng lặp chính **đã** dừng đúng tại terminal, nhưng cửa sổ follow-through thì chưa.

#### 2. Thay đổi (chỉ `core/smc_lifecycle.py`)

| Thay đổi | Nội dung |
|---|---|
| `_expiry_boundary_index(...)` (**mới**) | Trả index **đầu tiên** có `age > stale_after_bars(timeframe, tf_minutes)`, tính bằng **đúng** `age_anchor_index` + `available_boundary` + `first_eligible` mà vòng lặp chính dùng ⇒ biên follow-through và biên lifecycle không thể lệch nhau. |
| `analyze_zone_lifecycle` | Tính `lifetime_boundary` một lần trước vòng lặp và truyền xuống `_follow_through_reaction_at(terminal_index=...)`. |
| `_follow_through_reaction_at(..., terminal_index=None)` | `last_index = min(len-1, exit_index+3, terminal_index - 1)` ⇒ **nến terminal và mọi nến sau đó không bao giờ là nguồn reaction** (A-D05: expiry xét trước reaction cùng nến). |

**Không** thêm guard riêng cho D1: cắt cửa sổ dựa trên **lifetime của timeframe đang chạy** (`_STALE_AFTER_BARS`), nên D1 (20) và H4 (30) dùng cùng một luật; BUY/SELL không phân nhánh. Invalidation trong window vẫn có ưu thế terminal như trước (`_invalidates` ⇒ `None`).

#### 3. Timeline trước → sau (đối chiếu §Timeline D1/H4 terminal trong `M`)

```text
D1 (lifetime 20, anchor = origin ⇒ age(i)=i):
  index 20 (exit, age 20)   window cũ 20…23 → reaction lấy từ 21 ✗
                            window mới 20…20 → chỉ xét chính nến exit ✓
  index 21 (terminal, age 21)  không còn là nguồn reaction ✓
  index 22 (sau terminal)      không còn là nguồn reaction ✓
H4 (lifetime 30): exit 30 ⇒ window cũ 30…33, mới 30…30; terminal 31 và sau-terminal 32 bị loại ✓
Giữ nguyên: exit ở age < lifetime vẫn lấy reaction trong window còn trước terminal (same-candle exit→reaction) ✓
```

#### 4. Kết quả trước → sau

```text
r72_06 (acceptance) : 10 failed / 10 passed  →  20 passed   (10 node GREEN, 0 RED mới)
probe r72_06        :  2 failed              →   2 passed
acceptance          : 50 failed / 68 passed  →  40 failed / 78 passed
probes (tổng)       :  9 failed /  7 passed  →   7 failed /  9 passed
task57–71           : 108 passed             → 108 passed   (không regression)
retained            : 854 passed             → 854 passed   (không regression)
full §5             : 50 failed / 922 passed →  40 failed / 932 passed   (0 failure ngoài acceptance)
```

**10 node F04 chuyển GREEN (khớp đúng tập FAILED trước sửa; kiểm bằng diff tập FAILED ⇒ 0 RED mới):**

| # | Node | Assertion nay chạy được |
|---|---|---|
| 1–2 | `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[buy/sell]` | T:632 `reacted_at is None`, T:633 `visit_state == "completed_unreacted"` |
| 3–4 | `test_r72_06_h4_reaction_at_terminal_is_blocked[buy/sell]` | T:2358 `reacted_at is None`, T:2359 `completed_unreacted` |
| 5–6 | `test_r72_06_h4_reaction_after_terminal_is_blocked[buy/sell]` | T:2386, T:2387, **control** T:2393 `trimmed.visits[0] == visit` |
| 7–10 | `test_r72_06_terminal_order_before_reaction_is_explicit[21-buy/21-sell/22-buy/22-sell]` | T:2428, T:2429, **control** T:2435 `trimmed.visits[0] == visit` |

**Assertion trước đây bị fail-fast che, nay chạy thật:** `visit_state == "completed_unreacted"` ở cả 4 họ node, và **hai control cold-run** `trimmed.visits[0] == visit` (bỏ nến sau terminal ⇒ history y hệt) ở `h4_reaction_after_terminal_is_blocked` và `terminal_order_before_reaction_is_explicit[21/22-*]`. **Prefix/parity giữ nguyên:** `terminal_order_before_reaction_is_explicit[20-*]` (reaction ở age 20 < terminal) và `h4_reaction_before_terminal_is_retained[*]` **vẫn GREEN**, tức reaction hợp lệ trước terminal **không** bị xóa.

**Số node GREEN ≠ số hàng tài liệu:** 10 node chuyển GREEN; `M` cập nhật **10 hàng** (mỗi hàng một node; 12 hàng ban đầu bị gắn nhầm gồm cả `[20-*]` vốn đã GREEN, đã hoàn nguyên ngay trong lượt). Các node `[20-*]` và `terminal_state_survives_enrich_restore_enrich[invalid-*]` **không** được ghi lại là GREEN do F04 — chúng đã xanh từ trước (F03).

#### 5. RED còn lại (đúng scope, không phải F04)

**F05 — D1 consumer:** `typed_terminal_projection_reaches_d1_consumer[buy/sell]`, `typed_invalid_projection_beats_conflicting_legacy_flags[buy/sell]`, và **vế consumer** của `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer`. Không còn RED nào thuộc F04.

#### 6. Command/kết quả thật

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_06"          → 20 passed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no -k "r72_06"      → 2 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no                      → 40 failed, 78 passed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no                  → 7 failed, 9 passed
python -m pytest <15 file task57–71> -q --tb=no                                          → 108 passed
python -m pytest <66+6 file retained> -q --tb=no                                         → 854 passed
python -m pytest <67+6 file full §5> -q --tb=no                                          → 40 failed, 932 passed
```

#### 7. Hash sau F04

```text
tests/test_smc_gate72_fix_acceptance.py   766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C  (KHÔNG ĐỔI)
docs/plans/probes/...review.py            5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6  (KHÔNG ĐỔI)
tests/fixtures/.../golden_cases.json      45437A90E540BF772E1E3F2899C06D328293181F19F9B36AA5E26C3170C79999  (KHÔNG ĐỔI)
core/smc_lifecycle.py                     2109E93970270FBFFCE44D665EC28599C3031956873F20354A128D0BD6B1ED8D
core/smc_context.py                       BBC1B829BB09235D29956FCB39BD7DDE61113857E59E456AE4AF5B0F0F5DBF80  (= F03)
core/smc_models.py                        AEE437971AE15BF4A0B6995A30A3ED3C9F903550FF20C394670E7D3D1C47794B  (= F03)
```

#### 8. DEFERRED_OBSERVATION

- `M` L71/L72/L170 và `smc-implementation-progress.md` L87 vẫn còn ô thừa **có trước** (§A3.126) — không điều tra thêm.

#### 9. Phạm vi

Chỉ `core/smc_lifecycle.py` + `fix-plan.md`, `fix-progress.md`, `acceptance-matrix.md`. Không sửa D1 consumer (F05), scoring, liquidity/ownership; không chạm `T`/probe/golden/R56; không skip/xfail; giữ dirty changes; không commit/reset/xoá.

**F04: IMPLEMENTED.** **NEXT_TASK = F05**, chưa thực hiện.

### A3.134 — F05 (D1 consumer terminal) và bản trình checkpoint B

**Ngày:** 2026-09-11 (Asia/Saigon). **Trạng thái F05:** **IMPLEMENTED**. **Checkpoint B:** **WAITING_REVIEW**. Không tự PASS B / CLOSED finding / APPROVED gate72; chưa F06/task73.

**Baseline vào lượt (sau F04):** acceptance **40 failed / 78 passed**; cluster F05 targeted **11 node + 2 probe FAILED**; probes tổng **7F/9P**; task57–71 **108P**; retained **854P**; full §5 **40F/932P**.

#### 1. Nguyên nhân đo được trước sửa

`build_d1_reaction_evidence` chỉ chặn khi `lifecycle_expired`/`lifecycle_stale`/status ∈ {`expired`,`stale`}/`age > lifetime`, đọc **duy nhất** từ tham số `lifecycle`. Nó **không** đọc canonical terminal từ typed/serialized zone, **không** xét `lifecycle_broken`/`broken`/status `invalid`, và **không** so mốc `invalidated_at`/`expired_at` với cutoff. Vì vậy vùng đã terminal vẫn được cấp reaction `valid=True`, `score=1.0`, reason `D1_REACTION_COMPLETED_REACTED`.

#### 2. Thay đổi (chỉ `core/smc_confluence.py`)

| Thay đổi | Nội dung |
|---|---|
| `_canonical(key, default)` (cục bộ trong hàm) | Đọc giá trị canonical từ **typed/serialized zone trước**, rồi tới `lifecycle` (actual `ZoneLifecycle` hoặc dict) — đúng yêu cầu “dùng actual lifecycle **và** serialized mapping”. |
| Cổng terminal mở rộng | `lifecycle_broken` **hoặc** `broken` **hoặc** status ∈ {`invalid`,`expired`,`stale`} **hoặc** `lifecycle_expired`/`lifecycle_stale` **hoặc** `invalidated_at`/`expired_at` **≤ cutoff** (bao gồm) **hoặc** `age > lifetime` ⇒ `valid=False`, `score=0`, reason **`D1_REACTION_STALE`**. |
| Mốc thời gian bao gồm tại cutoff | Vùng terminal **đúng** tại cutoff ⇒ terminal (A-D04); cutoff **trước** mốc terminal ⇒ vẫn là positive hợp lệ, **không** hồi dựng snapshot quá khứ từ payload terminal tương lai. |

**Không** đổi công thức scoring, **không** reintroduce proximity bonus, **không** sửa liquidity/ownership. Reason dùng **`D1_REACTION_STALE`** (tên đã duyệt, cùng họ “lifecycle không còn sống”) — **không** bịa chuỗi mới. Visit/reaction history vẫn nằm trong payload để audit; consumer chỉ từ chối cấp **active** evidence.

#### 3. Kết quả trước → sau

```text
r72_05 (acceptance)   :  6 failed /  2 passed  →   8 passed
F05 cluster targeted  : 11 node + 2 probe FAILED → 13 passed (11 node) ; probe r72_05 2 passed
probes (tổng)         :  7 failed /  9 passed  →   5 failed / 11 passed
acceptance            : 40 failed / 78 passed  →  29 failed / 89 passed   (11 GREEN, 0 RED mới)
task57–71             : 108 passed             → 108 passed   (không regression)
retained              : 854 passed             → 854 passed   (không regression)
full §5               : 40 failed / 932 passed →  29 failed / 943 passed  (0 failure ngoài acceptance)
```

**11 node F05 chuyển GREEN (khớp đúng tập FAILED trước sửa):**

| # | Node | Assertion nay chạy được |
|---|---|---|
| 1–2 | `r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[buy/sell]` | `evidence["valid"] is False`, `score == 0` |
| 3–4 | `r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[buy/sell]` | `valid is False`, `score == 0` với canonical invalid + cờ legacy `d1_reaction/proximity=True` |
| 5–6 | `r72_05_cutoff_equal_invalidated_at_is_terminal[buy/sell]` | `valid is False`, `score == 0`, `"D1_REACTION_NOT_COMPLETED_REACTED" not in reason_codes` |
| 7–8 | `r72_08_typed_terminal_projection_reaches_d1_consumer[buy/sell]` | `valid is False`, `score == 0`, loại trừ cả `NOT_COMPLETED_REACTED` **và** `AFTER_CUTOFF` |
| 9–10 | `r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[buy/sell]` | `valid is False`, `score == 0` (canonical thắng cờ legacy mâu thuẫn) |
| 11 | `r72_09_d1_invalidated_source_is_terminal_for_the_consumer` | `evidence["valid"] is False`, `score == 0`, loại trừ `NOT_COMPLETED_REACTED` |

**Assertion trước bị fail-fast che, nay chạy thật:** toàn bộ các assert **sau** `valid`/`score` — `"D1_REACTION_NOT_COMPLETED_REACTED" not in reason_codes`, `"D1_REACTION_AFTER_CUTOFF" not in reason_codes`, và positive control `pre_terminal["valid"] is True` / `score > 0` / `source_visit_id` / `reacted_at` trong `d1_invalidated_source_is_terminal_for_the_consumer`. **Positive trước terminal vẫn đạt:** `typed_d1_projection_keeps_valid_reaction[*]`, `typed_expired_projection_blocks_d1_and_keeps_history[*]`, `cutoff_equal_expired_at_is_terminal[*]`, `h1_candidate_chain_reaches_d1_consumer_smoke` — giữ GREEN.

**Số node GREEN (11) = số hàng `M` cập nhật (11)** — kiểm bằng khớp **node ID đầy đủ** (không khớp theo tên họ), và **0 hàng MỘT PHẦN**: không hàng nào vừa chứa node nay GREEN vừa chứa node còn RED.

#### 4. Command/kết quả thật

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_05"          → 8 passed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no                 → 5 failed, 11 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no                     → 29 failed, 89 passed
python -m pytest <15 file task57–71> -q --tb=no                                         → 108 passed
python -m pytest <66+6 file retained> -q --tb=no                                        → 854 passed
python -m pytest <67+6 file full §5> -q --tb=no                                         → 29 failed, 943 passed
```

---

## BẢN TRÌNH CHECKPOINT B (lần 1) — `WAITING_REVIEW`

#### B.1. F02 → F05: obligation → thay đổi → node/bằng chứng

| F | Obligation (fix-plan) | Thay đổi | Node/evidence |
|---|---|---|---|
| **F02** | Metadata lifecycle đúng nguồn | `smc_lifecycle.py` (`_finite_metadata`, `_resolve_threshold`, `metadata_state/reason`, `invalidation_buffer: float\|None`, `_invalidates(buffer=None)⇒False`), `smc_context.py` (tick item-vs-argument, `usable=False` khi unknown), `smc_models.py` (`metadata_*` trên `SmcZone`) | r72_07 **19/19 GREEN**; §A3.130, §A3.131 |
| **F03** | Một trạng thái terminal canonical | `smc_context.py` (nhánh `lifecycle_broken` ⇒ `invalid`+`usable=False`+`broken`+`invalidated_at`+reason; invalidation thắng expiry), `smc_models.py` (`usable` trên `SmcZone`; canonical `invalid` thắng cờ legacy) | 7 node GREEN; §A3.132 |
| **F04** | Reaction không vượt expiry | `smc_lifecycle.py` (`_expiry_boundary_index`; `_follow_through_reaction_at(terminal_index=…)` cắt cửa sổ tại biên lifetime) | r72_06 **20/20 GREEN** + probe r72_06 2/2; §A3.133 |
| **F05** | D1 consumer loại evidence terminal | `smc_confluence.py` (`build_d1_reaction_evidence` cổng canonical terminal đọc cả typed zone **và** lifecycle, gồm broken/invalid + mốc ≤ cutoff) | 11 node GREEN + probe r72_05 2/2; §A3.134 |

#### B.2. Kết quả cumulative/full trên cùng snapshot

```text
acceptance (118 node)  : 29 failed / 89 passed   (baseline A lần4: 69 failed / 49 passed)
                         GREEN thêm: F02 12 + F03 7 + F04 10 + F05 11 = 40 node ; RED mới: 0
probes (nguyên bản)    :  5 failed / 11 passed   (A lần4: 13 failed / 3 passed)
task57–71              : 108 passed              (không đổi)
retained (loại accept) : 854 passed              (không đổi)
full §5 (67+6 file)    : 29 failed / 943 passed  (0 failure ngoài acceptance)
```

#### B.3. RED còn lại — theo F-code, toàn bộ thuộc cụm sau

| Nhóm | Số node | F-code | Ghi chú |
|---|---|---|---|
| r72_01 | 18 | F06 ×13, F06/F07 ×2 (chưa cô lập), F07 ×3 | Pool/sweep canonical — checkpoint C |
| r72_02 | 5 | F08 ×5 | Ownership claim time — checkpoint C |
| r72_03 | 2 | F09 ×1, F10 ×1 | Contribution/history — checkpoint C |
| r72_04 | 4 | F10 ×4 | Assignment/consumption — checkpoint C |
| **Tổng** | **29** | **F06…F10** | **không còn RED nào thuộc F02–F05** |

Đối chiếu: **0 RED mới** so với baseline A lần4 (diff tập FAILED), nên 29 = 69 − 40 node đã xanh.

#### B.4. Regression

**Không có.** `task57–71` **108 passed** và `retained` **854 passed** — bằng đúng con số trước khi bắt đầu F02. `full §5` chỉ có failure trong file acceptance.

#### B.5. Hash và artifact bảo vệ

```text
artifact bảo vệ — KHÔNG ĐỔI (6/6 kiểm lại sau F05):
  docs/plans/probes/test_smc_gate72_review.py      5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6
  tests/fixtures/smc_canonical/golden_cases.json   45437A90E540BF772E1E3F2899C06D328293181F19F9B36AA5E26C3170C79999
  docs/plans/smc-r56-01-session-contract.md        F04A0E6451801E04EA90E288543FD03B96CB82C715657992962A2FDB433D50BB
  docs/plans/smc-r56-01-coder-handoff.md           AA682DA161E49E807CC0AB2CD7E6BC3A581E9E8AD14456F6FB53BDE41F28D301
  tests/fixtures/smc_r56_01_session_acceptance.json 698CF8A2557FFD829CEBF7316AE30D854C84BED605B17F5FF1C6220254D2BDD5
  tests/test_smc_r56_01_session_acceptance.py      F1975050751F61A44CFE3B0936C19179A85DEECA08735D942986CFD8A253A5CA

tests/test_smc_gate72_fix_acceptance.py  766EC04E57F4086C4EEF2CBF39E65DCD93B8804413FCF67E79A78BD903E6688C  (KHÔNG ĐỔI)

hash core hiện hành:
  core/smc_lifecycle.py      2109E93970270FBFFCE44D665EC28599C3031956873F20354A128D0BD6B1ED8D
  core/smc_context.py        BBC1B829BB09235D29956FCB39BD7DDE61113857E59E456AE4AF5B0F0F5DBF80
  core/smc_models.py         AEE437971AE15BF4A0B6995A30A3ED3C9F903550FF20C394670E7D3D1C47794B
  core/smc_confluence.py     F91F2A88BF167EE7A2A1D62290FBA934F84A57BDCD765E1927FBD9191C5CE78B
  core/smc_sweep_linking.py  38B0276FB065D6EF7FBB454D8C6929D533D8ECA22FFC4EDB5BF6C352E57EFFB3  (chưa sửa)
git diff --check -> exit=0
```

#### B.6. Giới hạn chưa kiểm (không blocking B)

1. **Hai node r72_01 `acceptance_source_must_be_usable_at_sweep_close[buy/sell]` vẫn `F06/F07` chưa cô lập** — fixture thiếu `usable_at`; không chốt fallback `confirmed_at → usable_at`; hai node này **không** được tính là bằng chứng temporal độc lập (§A3.118, §A3.122).
2. **Reason `D1_REACTION_STALE` dùng chung cho cả terminal-invalid** — chưa có quyết định TL về việc tách một reason riêng cho `invalid`; lượt này **không** thêm chuỗi mới ngoài tập đã duyệt.
3. **`source_pool_kind`** vẫn không nằm trong contract nào nên oracle không khóa (§A3.105).
4. Assertions phía sau điểm fail ở các node còn RED **chưa chạy** — đã ghi riêng ở §A3.118…§A3.124.

#### B.7. DEFERRED_OBSERVATION

- `M` L71/L72/L170 và `smc-implementation-progress.md` L87 vẫn còn ô thừa **có trước** (§A3.126) — không mở task riêng.

#### B.8. Phạm vi

Chỉ `core/smc_confluence.py` (code F05) + `fix-plan.md`, `fix-progress.md`, `acceptance-matrix.md`. Không sửa scoring/proximity bonus/liquidity/ownership; không chạm `T`/probe/golden/R56; không skip/xfail; giữ dirty changes; không commit/reset/xoá.

**F05: IMPLEMENTED. Checkpoint B: WAITING_REVIEW. NEXT_TASK = F06 (chờ B PASS), chưa thực hiện.**

### A3.135 — Tech Lead review checkpoint B: CHANGES_REQUESTED

**Ngày:** 2026-09-11. Reviewer chạy full §5: **29 failed / 943 passed**, 972 tests, mọi failure trong acceptance. Kết quả suite khớp bản trình nhưng hai diagnostic trực tiếp dưới đây cho thấy nghĩa vụ terminal của F02/F03/F05 chưa đạt. Không mở lại A hoặc mở rộng sang F06…F10.

#### B-R1 [P1] — Zone có cờ False che terminal trên actual lifecycle (F05)

`core/smc_confluence.py:166–204`: `_canonical` chọn giá trị zone trước lifecycle, kể cả False/0/status confirmed. Vì thế terminal thực ở nguồn lifecycle bị che. Repro read-only dùng `_probe.lifecycle` với D1 BUY rows `(112,114,111,113), (109,110,105,109), (112,114,111,113), (99,100,98,99)`: lifecycle có completed_reacted rồi broken=True. Gọi consumer với zone chỉ có đúng zone_id ⇒ valid=False; thêm zone `lifecycle_status=confirmed`, `broken=False`, `lifecycle_broken=False`, `lifecycle_expired=False`, `lifecycle_stale=False`, `age_bars=0` ⇒ **valid=True** với as_of mặc định (API cho phép). Serialized lifecycle giữ broken=True nhưng không có invalidated_at cũng bị cấp valid=True dù truyền cutoff cuối chuỗi. Không sửa input hoặc production state trên đĩa khi probe.

**Yêu cầu sửa giới hạn:** bằng chứng terminal hợp lệ từ một trong hai nguồn không được bị cờ non-terminal/default của nguồn kia che. Không dùng quy tắc “zone thắng” cho mọi field một cách máy móc. Giữ positive khi cả hai nguồn chưa terminal; giữ cutoff contract và không rewind snapshot. Thêm regression test chứng minh actual lifecycle terminal + zone non-terminal/default vẫn reject, và vế serialized phù hợp; không sửa probe.

#### B-R2 [P1] — Dựng invalidation bằng zero khi metadata thiếu, phá terminal đã biết (F02/F03)

`core/smc_lifecycle.py:142–150` đặt invalidation_threshold=0.0 nếu declared_terminal dù buffer=None; `core/smc_context.py:4946` truyền cả status expired vào nhánh này rồi `item.update(lifecycle.to_dict())` ghi đè evidence cũ. Trái matrix interface metadata §4: metadata thiếu không đổi invalid/expired sang trạng thái khác hoặc suy ra invalidation từ threshold None.

Repro read-only: H1 BUY zone[100,110], origin0/departure1, status expired, usable=False, expired_at=stamp(2), ATR1, thiếu tick; rows `(112,114,111,113), (112,114,111,113), (100,101,99.9,99.98)` qua `_probe.candles`; enrich với liquidity_sweeps={}, premium_discount_range={}. Actual: **status invalid, invalidated_at=stamp(3), expired_at=None, broken=True, metadata_state=unknown, invalidation_buffer=None**. Payload expired đã biết bị biến thành invalid nhờ buffer0 không có nguồn, đồng thời mất timestamp expiry.

**Yêu cầu sửa giới hạn:** bảo toàn loại terminal/timestamp/reason/history đã biết khi không đủ dữ liệu tái tính; không suy ra invalidation mới bằng zero giả. Thêm regression cho expired và invalid đã biết + thiếu metadata; không thay lifecycle contract, không yêu cầu hồi dựng history không có trong payload. Giữ behavior tính mới khi đủ metadata và các controls F02–F04.

**Điểm dừng:** sửa B-R1/B-R2 và tests hồi quy tối thiểu, cập nhật matrix/ledger cùng lượt, chạy targeted + cumulative F02–F05 + full §5 và probes; trình B lại một lần. Không làm lại90 mã, không mở task cho lỗi bảng lịch sử, chưa F06/task73. Hash acceptance sẽ được phép đổi chỉ vì regression tests mới này; ghi before/after và collection delta. Probe/golden/R56 giữ nguyên. Reviewer không sửa code/tests, không commit.

### A3.136 — Sửa B-R1/B-R2 và trình checkpoint B lần2

**Ngày:** 2026-09-11 (Asia/Saigon). **Trạng thái:** B-R1 **đã sửa**, B-R2 **đã sửa**; **Checkpoint B: WAITING_REVIEW (lần2)**. Không tự PASS/CLOSED/APPROVED; chưa F06/task73. Không mở lại A.

**Baseline vào lượt:** acceptance **29 failed / 89 passed** (118 node); probes **5F/11P**; task57–71 **108P**; retained **854P**; full §5 **29F/943P**.

#### 1. B-R1 [P1] — zone có cờ False che terminal trên actual lifecycle (F05)

**Tái lập (read-only, trước sửa — theo §A3.135):** `_probe.lifecycle` D1 BUY rows `(112,114,111,113),(109,110,105,109),(112,114,111,113),(99,100,98,99)` cho `lifecycle_broken=True`, `visits[0]=completed_reacted`. Zone tối giản `{zone_id, direction}` ⇒ `valid=False`; nhưng thêm zone `lifecycle_status="confirmed"`, `broken=False`, `lifecycle_broken=False`, `lifecycle_expired=False`, `lifecycle_stale=False`, `age_bars=0` ⇒ **`valid=True`** — terminal thật trên lifecycle bị cờ non-terminal của zone che.

**Gốc:** `_canonical` chọn **zone trước** cho **mọi** field, kể cả `False`/`0`/`"confirmed"`.

**Sửa (`core/smc_confluence.py`):** bỏ “zone thắng” theo field; terminal hợp nhất bằng **OR theo nguồn**:
- `_terminal_flag(key)` ⇒ True nếu **một trong hai** nguồn có cờ truthy (`lifecycle_broken`, `broken`, `lifecycle_expired`, `lifecycle_stale`);
- `_terminal_status()` ⇒ True nếu **một trong hai** nguồn có status ∈ {`invalid`,`expired`,`stale`};
- `_earliest_terminal_at()` ⇒ mốc terminal **sớm nhất** trong hai nguồn (`invalidated_at`/`expired_at`) — vẫn so **bao gồm** với cutoff;
- `_largest_age()` ⇒ tuổi **lớn nhất**, để `age_bars=0` mặc định không che tuổi thật.

Positive giữ nguyên: cả hai nguồn chưa terminal ⇒ vẫn cấp reaction; cutoff contract và “không rewind snapshot” không đổi.

#### 2. B-R2 [P1] — dựng invalidation bằng zero khi metadata thiếu (F02/F03)

**Tái lập (read-only, TRƯỚC sửa — đo lại trong lượt):** H1 BUY zone[100,110], origin0/departure1, `lifecycle_status="expired"`, `usable=False`, `expired_at=stamp(2)`, `atr_current=1`, **thiếu tick**; rows `(112,114,111,113),(112,114,111,113),(100,101,99.9,99.98)`. Kết quả đo được:

```text
lifecycle_status='invalid'  invalidated_at='2026-09-01T03:00:00+00:00'  expired_at=None
broken=True  lifecycle_broken=True  lifecycle_expired=False
metadata_state='unknown'  invalidation_buffer=None
```

Payload `expired` đã biết bị **biến thành `invalid`** nhờ buffer `0.0` không có nguồn, đồng thời **mất timestamp expiry**.

**Sửa:**
- `core/smc_lifecycle.py`: **bỏ** hoàn toàn `invalidation_threshold = 0.0` khi `declared_terminal` — buffer `None` ⇒ luật buffered **không** bao giờ tự kích hoạt. Thay `declared_terminal: bool` bằng `declared_terminal_status: str | None` + `declared_invalidated_at: str | None`; nếu payload khai `invalid` **và** metadata không tính được, visit còn mở được đóng bằng **chính khai báo đó** (`closed_by_invalidation`, dùng timestamp khai nếu có) — không suy ra từ ngưỡng giả.
- `core/smc_context.py`: chụp terminal đã khai **trước** khi `item.update(lifecycle.to_dict())`; nếu derivation **không** tạo ra terminal nào và metadata là `unknown`, **bảo toàn verbatim** loại terminal + `invalidated_at`/`expiration_index`/`expired_at`/`expiry_index` + reason (`ZONE_INVALIDATED`/`ZONE_EXPIRED`) ⇒ không biến `expired` thành `invalid`, không xóa evidence.

#### 3. Regression tests mới (thêm vào acceptance — collection delta)

| # | Node | RED trước / GREEN sau |
|---|---|---|
| 1 | `test_r72_05_zone_nonterminal_defaults_cannot_mask_active_lifecycle_terminal` | **RED trước** (repro §A3.135) / **GREEN sau** — control “cả hai nguồn chưa terminal ⇒ `valid=True`, `score>0`” cũng PASS |
| 2 | `test_r72_07_known_expired_is_preserved_when_metadata_is_missing` | **RED trước** (`assert 'invalid' == 'expired'`) / **GREEN sau** |
| 3 | `test_r72_07_known_invalid_is_preserved_when_metadata_is_missing` | **RED trước** (`assert None == stamp(2)`) / **GREEN sau** |

**Ghi nhận trung thực về #1:** bản sửa B-R1 được áp **trước** khi tôi viết test #1, nên trạng thái RED của nó **không** được đo lại trong lượt này — bằng chứng RED là **repro read-only của reviewer tại §A3.135** (cùng input, cùng kết quả `valid=True`), còn lượt này đo được kết quả **sau sửa** `valid=False`, `score=0`, reason `D1_REACTION_STALE`. Hai test #2/#3 thì **đo được RED ngay trước khi sửa B-R2** (`2 failed` cho đúng 2 assertion nêu trên).

**Collection delta:** **118 → 121 node** (+3). Hash `T`: `766EC04E…` → `3B1412CC9C21B828499BA19AEF4C61DD91C36F103B08C791B6763573AF531403`. Probe/golden/R56 **không đổi**.

#### 4. Kết quả trước → sau

```text
acceptance            : 29 failed / 89 passed  → 29 failed / 92 passed   (+3 test mới; 0 RED mới)
r72_05                :  8 passed              →  9 passed
r72_07                : 19 passed              → 21 passed
r72_06 / r72_08       : 20 / 13 passed         → 20 / 13 passed          (không đổi)
probes (tổng)         :  5 failed / 11 passed  →  5 failed / 11 passed
task57–71             : 108 passed             → 108 passed              (không regression)
retained              : 854 passed             → 854 passed              (không regression)
full §5               : 29 failed / 943 passed → 29 failed / 946 passed  (0 failure ngoài acceptance)
```

**RED còn lại:** **29 node, 0 RED mới** (diff tập FAILED vs baseline A lần4) — r72_01 ×18, r72_02 ×5, r72_03 ×2, r72_04 ×4 ⇒ **toàn bộ thuộc F06…F10**; không còn RED nào thuộc F02–F05. Ba test mới **không** nằm trong tập RED.

#### 5. Command/kết quả thật

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q              → 121 tests collected
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "<3 test mới>"   → 3 passed  (trước sửa B-R2: 2 failed, 1 passed)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_07"         → 21 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_05"         → 9 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no                     → 29 failed, 92 passed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no                 → 5 failed, 11 passed
python -m pytest <15 file task57–71> -q --tb=no                                         → 108 passed
python -m pytest <66+6 file retained> -q --tb=no                                        → 854 passed
python -m pytest <67+6 file full §5> -q --tb=no                                         → 29 failed, 946 passed
git diff --check                                                                        → exit=0
```

#### 6. Hash

```text
tests/test_smc_gate72_fix_acceptance.py   3B1412CC9C21B828499BA19AEF4C61DD91C36F103B08C791B6763573AF531403   (ĐỔI: +3 regression test)
docs/plans/probes/...review.py            5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6   (KHÔNG ĐỔI)
tests/fixtures/.../golden_cases.json      45437A90E540BF772E1E3F2899C06D328293181F19F9B36AA5E26C3170C79999   (KHÔNG ĐỔI)
4 artifact R56                            KHÔNG ĐỔI (đã kiểm lại ở §A3.134 B.5)
core/smc_lifecycle.py                     A99A338B4F9040242A0D00840150AA50E8269F20834DD58BA610E79167DEA45C
core/smc_context.py                       D980208E920CCF948EBE33A7A5AF9DBD7C9B114302CF0E49C18161BB1CC7E2EF
core/smc_models.py                        AEE437971AE15BF4A0B6995A30A3ED3C9F903550FF20C394670E7D3D1C47794B   (= F03)
core/smc_confluence.py                    EA5C4A52D4C4806F2E37AC1DCE6B18A2A07BE49F5D981317633A1D58C38D7051
core/smc_sweep_linking.py                 38B0276FB065D6EF7FBB454D8C6929D533D8ECA22FFC4EDB5BF6C352E57EFFB3   (chưa sửa)
```

`M` (acceptance-matrix) **không** đổi Actual/Loại RED trong lượt này: 3 test mới là **node hồi quy ngoài mapping R72**, không thuộc bảng tracking nào; các hàng R72-05/R72-07 đã ở trạng thái GREEN từ §A3.134 và **vẫn** GREEN (r72_05 9/9, r72_07 21/21) nên không có hàng nào bị ghi lại sai.

#### 7. Bản trình checkpoint B (lần 2) — các số hiệu lực

```text
acceptance (121 node)  : 29 failed / 92 passed    (baseline A lần4: 118 node, 69 failed / 49 passed)
probes (nguyên bản)    :  5 failed / 11 passed    (A lần4: 13 failed / 3 passed)
task57–71              : 108 passed               (không đổi)
retained (loại accept) : 854 passed               (không đổi)
full §5 (67+6 file)    : 29 failed / 946 passed   (0 failure ngoài acceptance)
RED còn lại            : 29 — F06…F10 (r72_01 ×18, r72_02 ×5, r72_03 ×2, r72_04 ×4) ; 0 RED mới
```

Điều kiện trình B: obligations **F02–F05 đạt**, **không regression** retained/task57–71, **mọi RED còn lại thuộc cụm sau**, hash probe/golden/R56 **không đổi**, `git diff --check` **exit=0**.

#### 8. DEFERRED_OBSERVATION

- `M` L71/L72/L170 và `smc-implementation-progress.md` L87 vẫn còn ô thừa **có trước** (§A3.126) — không mở task riêng.
- Reason `D1_REACTION_STALE` vẫn dùng chung cho cả terminal-invalid; chưa có quyết định TL tách reason riêng.

#### 9. Phạm vi

Chỉ `core/smc_confluence.py`, `core/smc_lifecycle.py`, `core/smc_context.py` (code B-R) + `tests/test_smc_gate72_fix_acceptance.py` (3 regression test) + `fix-plan.md`, `fix-progress.md`. Không sửa probe/golden/R56/`smc_sweep_linking.py`/`smc_models.py`; không nới contract, không giảm assertion, không skip/xfail; giữ dirty changes; không commit/reset/xoá.

**F05 và F02/F03 (phần bị B-R nêu): IMPLEMENTED. Checkpoint B: WAITING_REVIEW (lần2). NEXT_TASK = F06 (chờ B PASS), chưa thực hiện.**

### A3.137 — Tech Lead review B lần2: B-R1 đạt, B-R2 còn CHANGES_REQUESTED

**Ngày:** 2026-09-11. Reviewer đọc sửa đổi và ba regression, chạy lại full §5: **29 failed / 946 passed**, 975 tests. Hash T khớp bản trình: `3B1412CC9C21B828499BA19AEF4C61DD91C36F103B08C791B6763573AF531403`. Không sửa code/tests trong lượt reviewer.

**B-R1: đạt trong phạm vi finding.** Flags/status terminal đọc cả hai nguồn, không còn zone False che lifecycle terminal; earliest timestamp và age không bị default của zone che. Regression actual lifecycle + positive control đã xanh trong full suite. Việc chưa chạy test #1 RED trước sửa được công bố đúng; diagnostic reviewer §A3.135 là bằng chứng RED trước, không cần đảo core để diễn lại lịch sử. Giữ phần đã đạt, không mở lại B-R1.

**B-R2: chưa đạt — cùng lỗi bảo toàn evidence terminal, không phải finding mới.** `core/smc_context.py` chỉ bảo toàn declared terminal trong nhánh `elif declared_status and metadata_state == unknown`, đứng SAU `lifecycle_broken`/`lifecycle_expired`. Khi derivation hết tuổi, nhánh expiry chạy trước và vẫn ghi đè terminal đã biết. Hai regression mới chỉ chạy cửa sổ ngắn nên chưa đi qua nhánh này.

Diagnostic read-only: `_probe.candles([(112,114,111,113)]*25, hours=24)`; item BUY ob, zone_id=zone, bounds100/110, origin_index0, departure_end_index1, available_at=stamp(24), atr_current1, thiếu tick, usable=False. Lần1 khai status invalid/broken=True/invalidated_at=stamp(48); lần2 khai status expired/expired_at=stamp(48). Gọi `enrich_zones([item], values, 'ob', {}, {'status':'unknown'}, timeframe='D1', tf_minutes=1440)`.

| Payload đã biết | Actual sau enrich | Expected theo B-R2/interface metadata §4 |
|---|---|---|
| invalid, invalidated_at=2026-09-03T00:00Z | expired, broken=False, invalidated_at=None, expired_at=2026-09-23T00:00Z, metadata unknown | Giữ invalid/broken và timestamp invalidation đã biết, không chuyển thành expiry muộn hơn |
| expired, expired_at=2026-09-03T00:00Z | expired nhưng expired_at bị thay thành 2026-09-23T00:00Z, metadata unknown | Giữ timestamp expiry gốc |

**Lượt sửa giới hạn:** xử lý precedence bảo toàn terminal khi metadata không đủ tái tính, không chỉ sửa nhánh cuối. Không dựng timestamp/index/history giả để làm khớp output. Mở rộng hai regression B-R2 hiện có với cửa sổ vượt lifetime (giữ vế cửa sổ ngắn, kiểm timestamp/index/reason/history đã khai nếu có). Giữ controls metadata đầy đủ và B-R1; không mở rộng audit.

**Đồng bộ cùng lượt, không tách task:** ba node mới thực sự có prefix r72_05/r72_07, nằm trong collection acceptance, không phải “ngoài mapping R72”. Thêm ba hàng mapping tương ứng và cập nhật inventory theo collection thật (bản hiện tại121 node; R72-05=9, R72-07=21). Không viết lại bảng lịch sử. Đây là sửa hồ sơ ngay trong lượt B-R2, không blocker implementation riêng.

Chạy targeted/cumulative + full §5/probes và trình lại B một lần. Giữ RED F06…F10 đã biết; chưa F06/task73, chưa PASS B/CLOSED R72 findings. Không commit/reset; không đổi probe/golden/R56. `git diff --check` kiểm sau ghi quyết định.

### A3.138 — B-R2/r1: precedence bảo toàn terminal khi metadata không đủ tái tính; trình B lần3

**Ngày:** 2026-09-11 (Asia/Saigon). **Trạng thái:** B-R2 **đã sửa**; **Checkpoint B: WAITING_REVIEW (lần3)**. B-R1 **giữ nguyên** (đã đạt theo §A3.137), không mở lại. Không tự PASS/CLOSED/APPROVED; chưa F06/task73.

**Baseline vào lượt (sau B lần2):** acceptance **29 failed / 92 passed** (121 node); probes **5F/11P**; task57–71 **108P**; retained **854P**; full §5 **29F/946P**; hash `T` `3B1412CC…`.

#### 1. Tái lập hai diagnostic cửa sổ vượt lifetime (§A3.137)

Fixture chung: `_probe.candles([(112,114,111,113)] * 25, hours=24)`; item BUY ob, `zone_id=zone`, bounds `100/110`, `origin_index=0`, `departure_end_index=1`, `available_at=stamp(24)`, `atr_current=1`, **thiếu tick**, `usable=False`; gọi `enrich_zones([item], values, 'ob', {}, {'status':'unknown'}, timeframe='D1', tf_minutes=1440)`.

| Payload đã biết | Actual **trước** sửa | Expected (B-R2 + interface metadata §4) |
|---|---|---|
| `invalid`, `broken=True`, `invalidated_at=stamp(48)` (= 2026-09-03) | `expired`, `broken=False`, `invalidated_at=None`, `expired_at=stamp(528)` (2026-09-23), `metadata unknown` | Giữ **invalid**/`broken` và timestamp invalidation đã biết |
| `expired`, `expired_at=stamp(48)` (= 2026-09-03) | `expired` nhưng `expired_at` bị thay thành `stamp(528)` (2026-09-23) | Giữ timestamp expiry gốc |

**Gốc:** nhánh bảo toàn declared terminal mà tôi thêm ở §A3.136 nằm ở `elif` **sau** `lifecycle_broken`/`lifecycle_expired`. Khi series dài tới mức derivation tự hết tuổi, nhánh expiry chạy **trước** và ghi đè terminal đã khai. Hai regression cũ chỉ dùng cửa sổ ngắn nên không đi qua nhánh này.

#### 2. Sửa (`core/smc_context.py`) — precedence, không chỉ nhánh cuối

Nhánh bảo toàn được **dời lên đầu** chuỗi quyết định:

```text
if declared_status and lifecycle.metadata_state == "unknown":   ← bảo toàn terminal đã khai (ưu tiên)
elif lifecycle.lifecycle_broken:                                ← derivation
elif lifecycle.lifecycle_expired:                               ← derivation
```

Khi metadata **không đủ tái tính** và payload **đã khai** terminal, khai báo đó thắng mọi expiry/broken mà derivation sinh ra. Giữ **verbatim**: `lifecycle_status`, `invalidated_at`/`invalidation_index`/`expired_at`/`expiry_index`, `broken`/`lifecycle_broken`/`lifecycle_expired`, `usable=False`, và reason (`ZONE_INVALIDATED` cho invalid, `ZONE_EXPIRED` cho expired). Bốn khoá terminal luôn được **gán lại** từ payload (kể cả `None`) để shape ổn định và không giữ giá trị do derivation chèn.

**Không** dựng timestamp/index/history giả; **không** dùng buffer `0`; với payload khai `invalid` mà metadata thiếu, visit còn mở vẫn được đóng bằng **chính khai báo** đó (`closed_by_invalidation`, §A3.136) chứ không bằng ngưỡng giả.

**Kết quả đo lại sau sửa:**

```text
[invalid] status=invalid broken=True  invalidated_at=2026-09-03T00:00:00+00:00 expired_at=None           buffer=None meta=unknown
[expired] status=expired broken=False invalidated_at=None                          expired_at=2026-09-03T00:00:00+00:00 buffer=None meta=unknown
```

#### 3. Mở rộng hai regression B-R2 (giữ vế cửa sổ ngắn)

| Node | Vế cửa sổ ngắn (giữ) | Vế **vượt lifetime** (thêm) |
|---|---|---|
| `test_r72_07_known_expired_is_preserved_when_metadata_is_missing` | H1 3 nến, `expired_at=stamp(2)` ⇒ giữ đúng mốc, `lifecycle_expired=True`, `lifecycle_broken=False` | D1 25 nến, `expired_at=stamp(48)` ⇒ giữ đúng `stamp(48)` và **khác** mốc expiry suy ra `stamp(24*22)` (tính từ fixture: lifetime D1 20 ⇒ index vượt tuổi đầu tiên 21, close = open + 1 ngày) |
| `test_r72_07_known_invalid_is_preserved_when_metadata_is_missing` | H1 2 nến, `invalidated_at=stamp(2)` | D1 25 nến, `invalidated_at=stamp(48)` ⇒ giữ **invalid** + `invalidated_at=stamp(48)`, `lifecycle_expired=False`, `expired_at=None`, reason có `ZONE_INVALIDATED` và **không** có `ZONE_EXPIRED` |

Node ID **không đổi** (mở rộng tại chỗ) ⇒ collection vẫn **121 node / 79 hàm**.

**RED trước / GREEN sau:** hai vế vượt lifetime này chính là hai diagnostic ở §1 — **đo được RED trước khi sửa precedence** (`assert 'expired' == 'invalid'` và `assert stamp(528) == stamp(48)`) và **GREEN sau**. Vế cửa sổ ngắn giữ nguyên như đã có từ §A3.136 (khi đó đã đo RED trước khi sửa B-R2). Controls đủ metadata và B-R1 vẫn GREEN.

#### 4. Kết quả trước → sau

```text
acceptance            : 29 failed / 92 passed  → 29 failed / 92 passed   (không đổi số; chỉ đổi nội dung 2 test)
F02–F05 targeted      : r72_05 9 · r72_06 20 · r72_07 21 · r72_08 13 · r72_09 … → 73 passed
probes (tổng)         :  5 failed / 11 passed  →  5 failed / 11 passed
task57–71             : 108 passed             → 108 passed   (không regression)
retained              : 854 passed             → 854 passed   (không regression)
full §5               : 29 failed / 946 passed → 29 failed / 946 passed   (0 failure ngoài acceptance)
```

**RED còn lại:** **29, 0 RED mới** (diff tập FAILED vs baseline A lần4) — r72_01 ×18, r72_02 ×5, r72_03 ×2, r72_04 ×4 ⇒ **toàn bộ F06…F10**; không còn RED nào thuộc F02–F05.

#### 5. Command/kết quả thật

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q                    → 121 tests collected
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "<3 regression>"       → 3 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_05 or r72_06 or r72_07 or r72_08 or r72_09" → 73 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no                           → 29 failed, 92 passed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no                       → 5 failed, 11 passed
python -m pytest <15 file task57–71> -q --tb=no                                               → 108 passed
python -m pytest <66+6 file retained> -q --tb=no                                              → 854 passed
python -m pytest <67+6 file full §5> -q --tb=no                                               → 29 failed, 946 passed
git diff --check                                                                              → exit=0
```

#### 6. Hash

```text
tests/test_smc_gate72_fix_acceptance.py   3D4C4519B8F3BF4520BBE7A7DAD53387D8BC447F62605A7FE69756686F67518C   (ĐỔI: mở rộng 2 regression)
docs/plans/probes/...review.py            5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6   (KHÔNG ĐỔI)
tests/fixtures/.../golden_cases.json      45437A90E540BF772E1E3F2899C06D328293181F19F9B36AA5E26C3170C79999   (KHÔNG ĐỔI)
4 artifact R56                            KHÔNG ĐỔI
core/smc_context.py                       580DF0A13B714858A761ACCB8979A139D7B540F23B4C2E9D4538D119A99518F0
core/smc_lifecycle.py                     A99A338B4F9040242A0D00840150AA50E8269F20834DD58BA610E79167DEA45C   (= B-R2 lần2)
core/smc_confluence.py                    EA5C4A52D4C4806F2E37AC1DCE6B18A2A07BE49F5D981317633A1D58C38D7051   (= B-R1)
core/smc_models.py                        AEE437971AE15BF4A0B6995A30A3ED3C9F903550FF20C394670E7D3D1C47794B   (= F03)
core/smc_sweep_linking.py                 38B0276FB065D6EF7FBB454D8C6929D533D8ECA22FFC4EDB5BF6C352E57EFFB3   (chưa sửa)
```

#### 7. Đồng bộ inventory/mapping trong cùng lượt

`M`: thêm **3 hàng mapping** — `test_r72_05_zone_nonterminal_defaults_cannot_mask_active_lifecycle_terminal` vào bảng **R72-05** (header **8 → 9 node**) và hai node B-R2 vào bảng **R72-07** (header **19 → 21 node**); thêm ghi chú collection **121 node / 79 hàm** ngay sau dòng review B lần2, nêu rõ **118 node / 76 hàm** và `69 failed / 49 passed` là **snapshot A lần4** giữ làm lịch sử. Bảng lịch sử không bị viết lại.

#### 8. Bản trình checkpoint B (lần 3) — số hiệu lực

```text
acceptance (121 node / 79 hàm) : 29 failed / 92 passed
probes (nguyên bản)            :  5 failed / 11 passed
task57–71                      : 108 passed
retained (loại acceptance)     : 854 passed
full §5 (67+6 file)            : 29 failed / 946 passed   (0 failure ngoài acceptance)
RED còn lại                    : 29 — F06…F10 (r72_01 ×18, r72_02 ×5, r72_03 ×2, r72_04 ×4) ; 0 RED mới
B-R1 : đạt (giữ nguyên)        B-R2 : đã sửa (precedence + 2 regression mở rộng)
```

#### 9. Giới hạn chưa kiểm

- Reason `D1_REACTION_STALE` vẫn dùng chung cho terminal-invalid; chưa có quyết định TL tách reason riêng.
- Hai node r72_01 `acceptance_source_must_be_usable_at_sweep_close[buy/sell]` vẫn **F06/F07 chưa cô lập** (thiếu `usable_at`) — thuộc cụm sau.

#### 10. DEFERRED_OBSERVATION

- `M` L73/L74/L172 và `smc-implementation-progress.md` L87 vẫn còn ô thừa **có trước** (§A3.126).

#### 11. Phạm vi

Chỉ `core/smc_context.py` + `tests/test_smc_gate72_fix_acceptance.py` (mở rộng 2 regression) + `fix-plan.md`, `fix-progress.md`, `acceptance-matrix.md`. Không sửa probe/golden/R56/`smc_lifecycle.py`/`smc_confluence.py`/`smc_models.py`/`smc_sweep_linking.py`; không giảm assertion, không skip/xfail; giữ dirty changes; không commit/reset.

**Checkpoint B: WAITING_REVIEW (lần3). NEXT_TASK = F06 (chờ B PASS), chưa thực hiện.**

### A3.139 — Tech Lead review B lần3: còn phần history của B-R2

**Ngày:** 2026-09-11. Reviewer đọc precedence mới và chạy acceptance nhóm r72_05…09: **73 passed, 48 deselected**. SHA256 T khớp `3D4C4519B8F3BF4520BBE7A7DAD53387D8BC447F62605A7FE69756686F67518C`. Hai ca cửa sổ dài trong §A3.137 đã được regression khóa và PASS; không yêu cầu sửa lại các field terminal đã đạt. Full29F/946P ở §A3.138 là kết quả coder, reviewer không chạy lại full ở lượt này.

**B-R2 còn thiếu đúng nghĩa vụ history đã giao:** `item.update(lifecycle.to_dict())` vẫn ghi đè visits cũ; nhánh bảo toàn mới chỉ khôi phục loại/flags/bốn field thời gian-index. Khi thiếu tick, derivation không chặn tại invalidation đã khai và có thể viết reaction mới sau terminal. Đây không phải yêu cầu mới hoặc mở lại A.

**Diagnostic read-only từ actual lifecycle:** dùng `_probe.lifecycle(rows,'buy')` với D1 rows:

```text
[(112,114,111,113), (109,110,105,109), (112,114,111,113),
 (99,100,98,99), (109,110,105,109), (112,114,111,113)]
```

State nguồn có invalidated_at=2026-09-05T00:00Z. Tạo item zone_id=zone, type=bullish_ob, family=ob, direction=buy, origin_index=0, departure_end_index=0, bounds100/110, atr_current1, status invalid/broken=True/usable=False; copy invalidated_at/invalidation_index và visits từ state.to_dict(), không cấp tick. Gọi enrich cùng rows D1 (`_probe.candles(rows,hours=24)`), family ob, liquidity_sweeps={}, premium_discount_range={status:unknown}, timeframe D1/tf_minutes1440.

| Visit | History đầu vào từ lifecycle thật | Sau enrich thiếu tick |
|---|---|---|
| 1, entered 2026-09-03 | completed_reacted, reacted_at=2026-09-04 | Giữ nguyên |
| 2, entered 2026-09-05 | closed_by_invalidation, reacted_at=None | **completed_reacted, reacted_at=2026-09-07** |

Metadata đầu ra unknown; reaction mới muộn hơn invalidated_at đã biết hai ngày. Bảo toàn status invalid không đủ khi history bị tái viết như trên. Cụm B vẫn CHANGES_REQUESTED.

**Lượt sửa cuối phạm vi B-R2/history:** thêm vế regression này vào node known_invalid hiện có (hoặc một node nhỏ nếu cần), dùng history do lifecycle thật sinh; assert history đầu vào không bị mutate, terminal history không bị ghi đè và không xuất hiện reaction sau terminal. Bảo toàn history/evidence đã có khi không đủ metadata tái tính; không dựng history/timestamp/index giả. Nếu vẫn replay, phải tôn trọng terminal boundary đã biết. Giữ controls đủ metadata, hai ca timestamp ngắn/dài và B-R1 đã đạt.

Cập nhật test/matrix/plan/ledger cùng lượt; targeted+cumulative và full §5/probes trước trình lại. Không mở audit ngoài B-R2, không làm lại90 mã hoặc task định dạng. Reviewer không sửa code/tests, không commit. Chưa F06/task73, chưa PASS B/CLOSED gate findings.

### A3.140 — B-R2/history: bảo toàn history khi thiếu metadata tái tính; trình B lần4

**Ngày:** 2026-09-11 (Asia/Saigon). **Trạng thái:** B-R2 **khép nốt nghĩa vụ history**; **Checkpoint B: WAITING_REVIEW (lần4)**. B-R1 và các ca terminal/timestamp ngắn/dài **giữ nguyên**, không mở lại. Không tự PASS/CLOSED/APPROVED; chưa F06/task73.

**Baseline vào lượt (sau B lần3):** acceptance **29 failed / 92 passed** (121 node); probes **5F/11P**; task57–71 **108P**; retained **854P**; full §5 **29F/946P**; hash `T` `3D4C4519…`.

#### 1. Tái lập diagnostic history (§A3.139)

Input: `visits` lấy từ **actual lifecycle** `_probe.lifecycle(rows,'buy')` với D1 rows

```text
[(112,114,111,113), (109,110,105,109), (112,114,111,113), (99,100,98,99), (109,110,105,109), (112,114,111,113)]
```

⇒ `invalidated_at=2026-09-05T00:00:00+00:00` (= `stamp(96)`, close của index 3), `invalidation_index=3`; history nguồn: visit-1 `completed_reacted`/`reacted_at=stamp(72)`, visit-2 `closed_by_invalidation`/`reacted_at=None`. Item zone khai `status invalid`/`broken=True`/`usable=False`, copy `invalidated_at`/`invalidation_index`/`visits`, **không cấp tick**; enrich cùng rows D1 (`_probe.candles(rows, hours=24)`, `timeframe="D1"`, `tf_minutes=1440`).

| Visit | History đầu vào (lifecycle thật) | Actual **trước** sửa | Sau sửa |
|---|---|---|---|
| 1, entered `2026-09-03` | `completed_reacted`, `reacted_at=2026-09-04` | giữ nguyên | giữ nguyên |
| 2, entered `2026-09-05` | `closed_by_invalidation`, `reacted_at=None` | **`completed_reacted`, `reacted_at=2026-09-07`** | **`closed_by_invalidation`, `reacted_at=None`** |

Reaction mới muộn hơn `invalidated_at` đã biết **hai ngày**. `metadata_state` đầu ra vẫn `unknown`.

**Gốc:** `item.update(lifecycle.to_dict())` ghi đè `visits` bằng bản replay; nhánh bảo toàn trước đó chỉ khôi phục loại/flags/bốn field thời gian-index, **không** khôi phục history.

#### 2. Sửa (`core/smc_context.py`)

`enrich_zones` nay chụp thêm **history đã khai** trước khi gọi lifecycle — `visits` cùng các field sinh ra từ history (`independent_retest_count`, `bars_spent_inside`, `first_retest_index`, `first_retest_time`, `mitigation_ratio`, `lifecycle_mitigated`, `departure_end_index`) — và trong nhánh bảo toàn (`declared_status` + `metadata_state == "unknown"`) **khôi phục verbatim** các field đó cùng terminal fields.

- **Không** dựng history/index/timestamp giả: chỉ trả lại đúng giá trị payload đã mang.
- Field payload **không** khai thì **không** bị đụng ⇒ hai ca cửa sổ ngắn/dài (payload không có `visits`) giữ nguyên hành vi.
- Caller payload **không** bị mutate (assert trong regression).

#### 3. Regression (mở rộng node `known_invalid`, ID không đổi)

Vế thêm vào `test_r72_07_known_invalid_is_preserved_when_metadata_is_missing`:
- **RED trước**: `assert 'completed_reacted' == 'closed_by_invalidation'` (T:2926).
- **GREEN sau**, với ba vế reviewer yêu cầu: (a) `input bị mutate: False` — payload caller nguyên vẹn; (b) visit-2 vẫn `closed_by_invalidation` / `reacted_at is None`; (c) **không** có reaction tại/sau terminal đã biết (`mọi reacted_at` đều `None` hoặc `<= stamp(96)`).
- Precondition dựng từ fixture: `invalidated_at == stamp(96)` và history nguồn đúng hai visit với trạng thái/thời điểm nêu trên — **không** lấy output core làm expected.

**Không** tạo node mới ⇒ collection vẫn **121 node / 79 hàm**.

#### 4. Kết quả trước → sau

```text
acceptance            : 29 failed / 92 passed  → 29 failed / 92 passed   (không đổi số; đổi nội dung 1 node)
F02–F05 targeted      : 73 passed              → 73 passed
probes (tổng)         :  5 failed / 11 passed  →  5 failed / 11 passed
task57–71             : 108 passed             → 108 passed   (không regression)
retained              : 854 passed             → 854 passed   (không regression)
full §5               : 29 failed / 946 passed → 29 failed / 946 passed   (0 failure ngoài acceptance)
```

**RED còn lại:** **29, 0 RED mới** (diff tập FAILED vs baseline A lần4) — r72_01 ×18, r72_02 ×5, r72_03 ×2, r72_04 ×4 ⇒ **toàn bộ F06…F10**; không còn RED nào thuộc F02–F05.

#### 5. Command/kết quả thật

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q                     → 121 tests collected
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "<3 regression>"        → 3 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no -k "r72_05 or r72_06 or r72_07 or r72_08 or r72_09" → 73 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no                            → 29 failed, 92 passed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no                        → 5 failed, 11 passed
python -m pytest <15 file task57–71> -q --tb=no                                                → 108 passed
python -m pytest <66+6 file retained> -q --tb=no                                               → 854 passed
python -m pytest <67+6 file full §5> -q --tb=no                                                → 29 failed, 946 passed
git diff --check                                                                               → exit=0
```

#### 6. Hash

```text
tests/test_smc_gate72_fix_acceptance.py   F16A5702CAFCCB415EB05A278EA4D5AAF871DDDC573C73A5509E0B418A17957A   (ĐỔI: mở rộng known_invalid)
docs/plans/probes/...review.py            5B040D6AAD6DD1F8EA81CED1D809E89AEABC227147DFAC84D593B8FCB618B1C6   (KHÔNG ĐỔI)
tests/fixtures/.../golden_cases.json      45437A90E540BF772E1E3F2899C06D328293181F19F9B36AA5E26C3170C79999   (KHÔNG ĐỔI)
4 artifact R56                            KHÔNG ĐỔI
core/smc_context.py                       49BC2F7245678262C3EB49439B75CC27916878D1932352B5D06EAED9F21068D1
core/smc_lifecycle.py                     A99A338B4F9040242A0D00840150AA50E8269F20834DD58BA610E79167DEA45C   (= B-R2 lần2)
core/smc_confluence.py                    EA5C4A52D4C4806F2E37AC1DCE6B18A2A07BE49F5D981317633A1D58C38D7051   (= B-R1)
core/smc_models.py                        AEE437971AE15BF4A0B6995A30A3ED3C9F903550FF20C394670E7D3D1C47794B   (= F03)
core/smc_sweep_linking.py                 38B0276FB065D6EF7FBB454D8C6929D533D8ECA22FFC4EDB5BF6C352E57EFFB3   (chưa sửa)
```

`M`: hàng mapping `known_invalid` (bảng R72-07) cập nhật Actual để nêu vế history; **không** thêm hàng mới ⇒ inventory **121 node / 79 hàm** và mapping **121/121** giữ nguyên.

#### 7. Bản trình checkpoint B (lần 4) — số hiệu lực

```text
acceptance (121 node / 79 hàm) : 29 failed / 92 passed
probes (nguyên bản)            :  5 failed / 11 passed
task57–71                      : 108 passed
retained (loại acceptance)     : 854 passed
full §5 (67+6 file)            : 29 failed / 946 passed   (0 failure ngoài acceptance)
RED còn lại                    : 29 — F06…F10 (r72_01 ×18, r72_02 ×5, r72_03 ×2, r72_04 ×4) ; 0 RED mới
B-R1 : đạt (giữ nguyên)   B-R2 : đạt — terminal/timestamp (ngắn + dài) và history
```

#### 8. Giới hạn chưa kiểm

- Reason `D1_REACTION_STALE` vẫn dùng chung cho terminal-invalid; chưa có quyết định TL tách reason riêng.
- Hai node r72_01 `acceptance_source_must_be_usable_at_sweep_close[buy/sell]` vẫn **F06/F07 chưa cô lập** — thuộc cụm sau.

#### 9. DEFERRED_OBSERVATION

- `M` L77/L78/L176 và `smc-implementation-progress.md` L87 vẫn còn ô thừa **có trước** (§A3.126).

#### 10. Phạm vi

Chỉ `core/smc_context.py` + `tests/test_smc_gate72_fix_acceptance.py` (mở rộng 1 regression) + `fix-plan.md`, `fix-progress.md`, `acceptance-matrix.md`. Không sửa probe/golden/R56/`smc_lifecycle.py`/`smc_confluence.py`/`smc_models.py`/`smc_sweep_linking.py`; không mở rộng audit, không giảm assertion, không skip/xfail; giữ dirty changes; không commit/reset.

**Checkpoint B: WAITING_REVIEW (lần4). NEXT_TASK = F06 (chờ B PASS), chưa thực hiện.**

### A3.141 — Tech Lead review B lần4: PASS

**Ngày:** 2026-09-11. **Quyết định:** PASS checkpoint B trong phạm vi lifecycle → typed projection → D1 (F02–F05). Thay kết luận B CHANGES_REQUESTED tại §A3.135/137/139. Không phải APPROVED gate72; không đóng R72 findings ở tầng gate.

**B-R1 đạt:** terminal từ actual/serialized lifecycle không bị zone False/default che; giữ positive control khi cả hai nguồn chưa terminal. **B-R2 đạt đối với các ca review đã nêu:** precedence bảo toàn terminal/timestamp qua cửa sổ ngắn/dài và history đã có khi metadata thiếu. Nhánh mới chụp history trước derivation, khôi phục sau update; regression dùng actual lifecycle giữ visit closed_by_invalidation/không reaction sau terminal, giữ reaction trước terminal và xác nhận input không bị mutate. Không yêu cầu đảo code để chạy lại lịch sử RED đã có bằng chứng.

**Kiểm chứng reviewer trên snapshot lần4:** full §5 **29 failed / 946 passed**, 975 tests; toàn bộ29 failure là R72-01×18, R72-02×5, R72-03×2, R72-04×4 (F06…F10). Các nhóm R72-05…09 và ba regression B đều GREEN trong full run. Task57–71 **108 passed**; probes **5 failed / 11 passed** (chỉ R72-01…04 còn RED). Acceptance **121 node:29F/92P**, retained **854P** (946−92); mapping so collection **121/121**, không thiếu/thừa. Không failure ngoài acceptance.

SHA256 T: `F16A5702CAFCCB415EB05A278EA4D5AAF871DDDC573C73A5509E0B418A17957A`. Reviewer tính lại probe/golden/4 R56: **6/6 khớp baseline**. Không sửa core/tests trong lượt TL; chỉ cập nhật quyết định vào hồ sơ hiện có. `git diff --check` kiểm sau cập nhật. Các lỗi bảng lịch sử đã ghi vẫn DEFERRED_OBSERVATION, không chặn B.

**NEXT_TASK = F06:** chỉ pool identity/provenance/usable time theo fix-plan và interface A. Sau F06 báo kết quả rồi dừng để giao F07; không làm một lượt F06…F10. Giữ cumulative F02–F05 GREEN. Những node end-to-end có phần sweep chưa sửa phải báo rõ assertion pool đã chạy/điểm fail kế tiếp, không báo toàn node GREEN hoặc ép F07 vào F06. Hai ca thiếu usable_at vẫn chưa cô lập F06/F07; không tự chốt fallback confirmed_at→usable_at. Checkpoint C chỉ trình sau F10; chưa task73.

### A3.142 — F06: canonical pool identity/provenance/usable time (R72-01)

**Ngày:** 2026-09-11. **Trạng thái:** F06 **IMPLEMENTED** (theo fix-plan §F06); checkpoint C **chưa** trình, chưa CLOSED/APPROVED gate72, chưa task73.

**Phạm vi đã làm (chỉ pool detector):** `core/smc_context.py::detect_liquidity_pools` phát thêm container canonical `records` (A3-005):

| Field | Nội dung |
|---|---|
| `pool_id` | `kind` + `source_ids` **đã sort** + causal record (`confirmed_at`) của từng source. **Không** dùng level, thứ tự input, rolling index hay observation time (A-D06). |
| `kind` | `swing_low` / `swing_high` / `equal_low` / `equal_high` (đã chốt tại review A lần3 §3). |
| `level` | Level canonical; equal pool giữ **mean** đúng như projection, lineage lấy từ `source_ids`. |
| `source_ids` | Danh sách **sort ổn định**, không theo input order và không theo causal order. |
| `sources` | Mỗi phần tử `{swing_id, confirmed_at, usable_at, provisional}`, tra theo `swing_id`, không theo vị trí list. |
| `usable_at` | `max(source.usable_at)` (so sánh theo instant, không theo chuỗi thô). |

**Giữ nguyên:** bốn key numeric vẫn `list[float]` (legacy projection), `equal_tolerance`/`status`/`reason_codes` không đổi, `detect_liquidity_sweeps` **không sửa** (canonical/legacy + cổng temporal thuộc F07).

**Fail closed, không tự tạo nguồn:** source thiếu `swing_id` non-empty hoặc thiếu `usable_at` ⇒ pool đó **không** có record canonical (projection numeric vẫn giữ). **Không** suy `usable_at` từ `confirmed_at`, **không** coi payload thiếu provenance là legacy.

**RED trước sửa → GREEN sau sửa (node `T`):** `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy]`/`[sell]`, `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible`, `test_r72_01_pool_identity_survives_source_permutation`. RED đầu tiên ghi trước khi sửa: `assert len(matches) == 1` / `assert len(records) == 1` → `assert 0 == 1` (`records` chưa tồn tại); permutation báo `('equal_low', ['source-a', 'source-z'], [])`.

**Kiểm chứng đã chạy (PowerShell, `D:/Projects/AIMarketAnalyst`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k r72_01 --tb=line
  trước: 18 failed / 11 passed   →   sau: 14 failed / 15 passed   (0 RED mới)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
  25 failed / 96 passed      (baseline §A3.141: 29 failed / 92 passed; 121 node)
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
  5 failed / 11 passed       (không đổi; chỉ R72-01…04)
task57–71 (rg --files tests -g '*task5[7-9].py' -g '*task6[0-9].py' -g '*task7[01].py')
  108 passed                 (không đổi)
retained SMC + 6 file integration (loại file acceptance)
  854 passed                 (không đổi)
full §5 (test_smc* + 6 file integration, gồm acceptance)
  25 failed / 950 passed     (baseline: 29 failed / 946 passed)
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
  121 node                   (không thiếu/thừa)
git diff --check             sạch (chỉ warning LF→CRLF có trước)
```

**RED còn lại: 25, 0 RED mới** — R72-01×14, R72-02×5, R72-03×2, R72-04×4 (F07…F10). Phân loại điểm fail kế tiếp của 14 node R72-01:

1. **Assertion pool đã PASS, việc còn lại là F07 (sweep)** — 7 node: `canonical_sweep_requires_pool_records_not_numeric_levels[buy]`/`[sell]`, `missing_pool_provenance_fails_closed[record_for_other_level|no_sources|dangling_source_id|source_without_provenance_id|source_without_usable_at]`. `detect_liquidity_sweeps` vẫn dựng candidate từ key numeric; “canonical vs legacy tường minh” là nội dung F07 theo fix-plan. Lưu ý hồ sơ: cột **Loại RED** của bảng matrix R72-01 đang gán 7 node này cho **F06**; fix-plan F07 gán cho F07 — **lệch phân loại cần TL xác nhận**, không tự sửa bảng lịch sử.
2. **RED do cổng temporal — F07** — 5 node: `acceptance_source_must_be_usable_at_sweep_close[buy]`/`[sell]`, `source_usable_after_sweep_close_is_rejected[buy]`/`[sell]`, `equal_pool_usable_time_is_max_of_both_sources`. Cần `usable_at <= reclaimed_at` (A-D01) tại sweep; F06 không đụng cổng thời gian.
3. **RED do producer thiếu `usable_at` — điểm cần TL quyết định** — 2 node: `pool_sweep_evidence_survives_future_bars`, `pool_sweep_identity_survives_rolling_index`. Khối causal parity **PASS** (prefix/batch cùng evidence trên 12 field causal, lọc theo `reclaimed_at <= cutoff`, rolling giữ identity, sweep đuôi chỉ batch có); fail tại `_pool_record_for` → `assert 0 == 1` (`('swing_low', ['smcs-a3eedff40ca702ee7827'], [])`).

**ĐIỂM CẦN QUYẾT ĐỊNH (chỉ rõ nguồn/contract, không tự chốt):** swing producer **không phát** `usable_at`.

- Nguồn/contract: `core/smc_context.py::_confirmed_swing_points` — dict `common` (≈ dòng 1119–1130) chỉ có `index/pivot_time/confirmed_at/confirmation_delay/confirmed/usable/provisional/pivot_width/timeframe/scope`; `external_swing_points` chỉ bọc lại hàm này. `usable = not provisional`, **không** có mốc usable riêng. Không có tài liệu SMC nào định nghĩa `usable_at` cho swing (đã rà `core/` và `docs/plans/smc-*.md`: 0 kết quả).
- Hệ quả nếu giữ nguyên: pool dựng từ producer thật **không có** `records` ⇒ F07 (khi chuyển sweep sang chỉ dùng `records`) sẽ fail closed cho mọi sweep production. Vì vậy điểm này cần chốt **trước** F07.
- Hai phương án để TL chọn (F06 **không** tự chọn):
  1. **Producer phát `usable_at`**: `_confirmed_swing_points` set `usable_at = confirmed_at` cho swing `usable=True` (documented là “usable kể từ khi confirmed”). Đụng producer nên cần TL duyệt phạm vi.
  2. **Contract riêng cho usability**: định nghĩa mốc usable khác `confirmed_at` (ví dụ một `lookback`/`confirmation_delay` khác), producer phát theo contract mới.
- Trong cả hai phương án, `detect_liquidity_pools` **không** cần sửa thêm: record tự lấy `usable_at` từ source khi producer bắt đầu phát.

**Hash/fingerprint lượt này:** `SHA256 core/smc_context.py = 0C3B5C9091BE26EB4D9EC05A40AEF119DB9860A99A0A2E1BD60587CF5C809273`; `SHA256 T = F16A5702CAFCCB415EB05A278EA4D5AAF871DDDC573C73A5509E0B418A17957A` (không đổi — **không** sửa acceptance test/probe/R56/golden lượt này). Giữ nguyên mọi dirty changes có trước; không commit/reset/xóa.

**DEFERRED_OBSERVATION:** (1) cột **Loại RED** R72-01 trong matrix gán 7 node sweep-consumption cho F06 trong khi fix-plan F07 gán cho F07 — lệch hồ sơ, chờ TL; (2) `records` của pool bị cắt theo `_MAX_LIQUIDITY_LEVELS` để khớp 1:1 với projection numeric — nếu F07 cần record cho **mọi** pool eligible thì phải chốt lại cùng lúc với việc bỏ fallback numeric.

**NEXT_TASK = F07** — chưa thực hiện; F06 dừng ở đây, không trình checkpoint C.

### A3.143 — TL chốt usable_at tại swing producer; F06/r1 trước F07

**Ngày:** 2026-09-11. Đọc `_confirmed_swing_points`: confirmed_at là `candle_close_at(candles[index+lookback].time, timeframe)`; producer chỉ phát pivot khi đủ cửa sổ bên phải, confirmed=True, usable=not provisional. Task21/25 trong implementation-plan và tiến độ task25 xác lập swing chưa confirmed chưa usable; không có thêm điều kiện trì hoãn usability cho confirmed non-provisional swing trong seam này.

**Quyết định interface cho producer này:** confirmed=True, usable=True, provisional=False ⇒ phát **usable_at=confirmed_at**, là instant UTC close nến xác nhận bên phải, không phải pivot/open/observation time. Áp tại shared producer internal/external. Provisional/unusable không cấp mốc usability có hiệu lực (dùng None hoặc không khai); vẫn bị canonical pool loại. Không đổi pivot detection/confirmation delay/ID.

Đây là **producer khai mốc từ semantics do chính nó sở hữu**, không phải fallback của pool/sweep cho record bất kỳ thiếu field. Pool/sweep vẫn fail closed khi payload canonical thiếu usable_at; hai node synthetic F06/F07 thiếu field giữ giới hạn, không được đổi fixture để che ca missing provenance. Không mặc định usable_at=confirmed_at cho mọi model/adapter hoặc loại source.

**NEXT: F06/r1**, nối shared swing producer và kiểm actual producer→pool với prefix/batch/rolling. Reuse tests, thêm assert producer/record có usable_at đúng fixture; không sửa sweep để ép các node end-to-end xanh. Báo riêng điểm fail sau pool (nếu F07 link/temporal chưa đạt). Giữ cumulative B GREEN và chạy full §5 trước báo. Không coi hai node actual-producer thiếu records hiện tại là F07 thuần; đó là phần nối F06 còn thiếu.

**Phân loại hồ sơ:** bảy node kiểm sweep từ numeric-only/missing provenance hiện fail ở consumer sweep ⇒ chủ sửa tiếp là F07 theo fix-plan; F06 cũ trong matrix là phân loại baseline lịch sử. Đồng bộ Actual/owner F07 cùng lượt F06/r1, không tạo task riêng và không gọi assertion pool đã PASS ở node không chạy producer. Hai node actual producer→pool đang dừng ở records rỗng, chưa PASS canonical pool.

**Giới hạn pool:** chưa có quyết định bỏ giới hạn `_MAX_LIQUIDITY_LEVELS` hoặc buộc phát mọi pool/event. Giữ chính sách pool-selection đã có; không dùng numeric projection làm authority lineage. Nếu test contract cụ thể cho thấy selection làm mất pool bắt buộc thì đưa đúng diagnostic, không tự thay thuật toán trong F06/r1.

Reviewer lượt này chỉ chốt điểm interface/điều phối dựa trên code và tài liệu; chưa xác nhận độc lập toàn bộ kết quả F06 hoặc PASS C. Coder cập nhật fix-plan/matrix/ledger cùng lượt, hash trước/sau, command/results, regression/blocker; không commit/probe/golden/R56 changes. Xong F06/r1 dừng, chưa tự F07/task73.

### A3.144 — F06/r1: producer khai `usable_at`; nối producer→pool→records

**Ngày:** 2026-09-11. **Trạng thái:** F06/r1 **IMPLEMENTED** theo quyết định TL [§A3.143](#a3143--tl-chốt-usable_at-tại-swing-producer-f06r1-trước-f07). Chưa F07, chưa checkpoint C, chưa CLOSED/APPROVED gate72, chưa task73.

**Producer contract đã chốt và thực thi** (`core/smc_context.py::_confirmed_swing_points`, dict `common`):

| Điều kiện pivot | `usable_at` phát ra |
|---|---|
| `confirmed=True`, `usable=True`, `provisional=False` | `= confirmed_at` — instant UTC **close nến xác nhận bên phải** (`candle_close_at(candles[index+lookback].time, timeframe)`), **không** phải `pivot_time`/open/observation time. |
| `provisional=True` (`usable=False`) | `None` — **không** cấp mốc usability có hiệu lực. |

Áp cho shared producer nên cả `external_swing_points` lẫn `internal_swing_points` cùng contract. **Không** đổi pivot detection, `confirmation_delay`, `pivot_width`, `swing_id`, `confirmed`/`usable`/`provisional`.

Đây là **producer khai mốc từ semantics chính nó sở hữu**, không phải fallback chung của pool/sweep: pool vẫn **fail closed** khi payload canonical thiếu `usable_at`; `detect_liquidity_pools` và `detect_liquidity_sweeps` **không** được nới thêm (giữ nguyên `_MAX_LIQUIDITY_LEVELS` và chính sách pool-selection). Các fixture cố ý thiếu provenance **không** bị sửa.

**Tests (reuse, không thay expected cũ, không bớt assertion):**

- `test_r72_01_actual_swing_producer_feeds_pool_and_sweep` — **thêm** assert producer: `usable_at == confirmed_at == stamp(pivot+lookback+1)`, `usable_at != pivot_time`; **thêm** assert record: `_pool_record_for(pools,"swing_low",[swing_id])` có `level`/`sources[0].confirmed_at`/`sources[0].usable_at`/`usable_at` khớp fixture. Node vẫn **GREEN**.
- `test_r72_01_pool_sweep_evidence_survives_future_bars` — thêm `usable_at` vào tuple parity prefix↔batch; assert `usable_at == confirmed_at == stamp(pivot+3)` và `!= pivot_time`.
- `test_r72_01_pool_sweep_identity_survives_rolling_index` — assert `usable_at` batch == rolled == `confirmed_at` (index shift không đổi usable time).
- **Node mới (+2, collection 121 → 123):** `test_r72_01_internal_producer_declares_usable_at_at_confirmation_close` (seam internal: `usable_at == confirmed_at == candle_close_at(pivot+2)`; record `swing_high` mang đúng mốc); `test_r72_01_provisional_producer_declares_no_usable_at_and_no_canonical_record` (provisional vẫn được producer phát nhưng `usable=False`, không `usable_at`; pool **không** cấp record, `swing_*`/`records` rỗng ⇒ fail closed, không hạ xuống legacy).

**Kiểm chứng (PowerShell, `D:/Projects/AIMarketAnalyst`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k r72_01 --tb=line
  F06:   14 failed / 15 passed   →   F06/r1: 14 failed / 17 passed   (0 RED mới, +2 node mới)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
  25 failed / 98 passed      (collection 123 node; trước F06/r1: 25/96 ở 121 node)
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
  5 failed / 11 passed       (không đổi; chỉ R72-01…04)
task57–71        108 passed  (không đổi)
retained SMC + 6 file integration (loại acceptance)        854 passed  (không đổi)
full §5          25 failed / 952 passed   (trước F06/r1: 25/950)
--collect-only   123 node
git diff --check  sạch
```

**RED còn lại: 25 (0 RED mới)** — R72-01×14, R72-02×5, R72-03×2, R72-04×4. **Toàn bộ 14 node R72-01 nay thuộc F07:**

1. **7 node numeric-only / thiếu provenance** (`canonical_sweep_requires_pool_records_not_numeric_levels[buy]`/`[sell]`, `missing_pool_provenance_fails_closed[...]`×5): assertion **pool** PASS; fail tại consumer sweep vì `detect_liquidity_sweeps` vẫn dựng candidate từ key numeric. Owner **F07**; phân loại **F06** trong matrix giữ làm **lịch sử**.
2. **2 node actual producer→pool** (`..._survives_future_bars`, `..._survives_rolling_index`): trước F06/r1 dừng ở `records` rỗng — đó là **phần nối F06**, **không** phải F07 thuần. Nay chạy tới và PASS toàn bộ assertion pool, rồi fail ở **dòng nối sweep**: `assert sweep["source_pool_id"] == record["pool_id"]` → `'smcs-a3eedff40ca702ee7827'` vs `'swing_low:smcs-a3eedff40ca702ee7827@2026-09-01T07:00:00+00:00'`. Owner **F07** (link `source_pool_id` → `records.pool_id`). **Không** sửa sweep ở lượt này để ép xanh; assertion pool chỉ được coi là PASS vì phép chạy đã **thực sự đi qua** nó.
3. **5 node temporal** (`acceptance_source_must_be_usable_at_sweep_close`×2, `source_usable_after_sweep_close_is_rejected`×2, `equal_pool_usable_time_is_max_of_both_sources`): cần cổng `usable_at <= reclaimed_at` (A-D01) tại sweep. Owner **F07**.

**Giới hạn giữ nguyên:** `_MAX_LIQUIDITY_LEVELS` và pool-selection hiện hành chưa đổi; numeric projection **không** là authority lineage; chưa buộc phát mọi pool/event.

**Hash:** `core/smc_context.py` `D8DF4996CA55B7449259DB64827DA4C6508141B6E3E0D1C3477B5F7BFE976B62` (trước F06/r1: `0C3B5C9091BE26EB4D9EC05A40AEF119DB9860A99A0A2E1BD60587CF5C809273`); `tests/test_smc_gate72_fix_acceptance.py` `973D247AA0D68D320858A6B0ABD93CFC13DB97C89E0905B6A787A31F52192839` (trước: `F16A5702CAFCCB415EB05A278EA4D5AAF871DDDC573C73A5509E0B418A17957A`). Không sửa probe/golden/R56; giữ nguyên dirty changes; không commit/reset/xóa.

**DEFERRED_OBSERVATION:** (1) `provisional` producer phát `"usable_at": None` — field xuất hiện trong payload swing ở nhánh provisional; TL đã cho phép “None hoặc không khai”, chọn None để schema ổn định, ghi lại để review đối chiếu; (2) `records` vẫn bị cắt theo `_MAX_LIQUIDITY_LEVELS` để khớp 1:1 projection numeric — nếu F07 cần record cho mọi pool eligible thì chốt cùng lúc với việc bỏ fallback numeric.

**NEXT_TASK = F07** — chưa thực hiện; dừng sau F06/r1.

### A3.145 — F07: sweep canonical dùng `records` + cổng `usable_at <= reclaimed_at` (R72-01)

**Ngày:** 2026-09-11. **Trạng thái:** F07 **IMPLEMENTED** theo fix-plan §F07. R72-01 xanh toàn bộ. Chưa F08, chưa checkpoint C, chưa CLOSED/APPROVED gate72, chưa task73.

**Sửa `core/smc_context.py::detect_liquidity_sweeps` (chỉ sweep detector/adapter):**

1. **Candidate canonical dựng từ `records`** (`canonical_candidates`): mỗi record phải có `kind` đúng phía, `level` hữu hạn, `pool_id` non-empty, `source_ids` non-empty **và** mọi ID có entry tương ứng trong `sources`, mỗi source có `swing_id` non-empty và `usable_at` parse được thành instant UTC. Thiếu bất kỳ phần nào ⇒ record không cấp candidate. **Không** fallback numeric level, **không** match level để tìm swing, **không** dùng `swing_id` làm pool identity.
2. **`source_pool_id` = `records.pool_id`**; evidence mang thêm `source_ids` và `source_pool_usable_at`; `source_swing_id`/`source_swing_index`/`source_swing_time` lấy từ record, chỉ đặt khi pool có **đúng một** source (equal pool nhiều source ⇒ `source_swing_id = None`, không bịa nguồn đại diện).
3. **Cổng A-D01** tại từng nến sweep: `usable_at <= reclaimed_at` (close nến theo timeframe), so theo **instant** không theo chuỗi; **equality được phép**; `usable_at` = **max** usable của mọi source; nguồn tương lai bị loại. `usable_at` thiếu/không parse được ⇒ không thành nguồn usable.
4. **Boundary canonical/legacy tường minh** (quyết định triển khai, ghi để TL review): payload **có** key `records` ⇒ canonical, chỉ `records` có quyền (numeric key bị bỏ hoàn toàn, kể cả khi `records` rỗng). Payload **không** có `records` ⇒ route numeric legacy do caller cấp, chỉ giữ **equal** level (contract task67 `test_pool_levels_are_used_when_explicitly_supplied` — giữ `source_pool_id` dạng `equal_high:110`); numeric **swing** level **không** cấp sweep vì không thể truy lineage từ level (A3-005 luật 3). Không có pool payload ⇒ legacy adapter path giữ nguyên.
5. **Giữ nguyên:** excursion/reclaim P8 (`max(2*tick, 0.10*ATR)`), BUY/SELL, numeric projection, pool-selection/`_MAX_LIQUIDITY_LEVELS`. **Không** thêm policy priority/dedupe/cardinality; dedupe duy nhất là theo `pool_id` trùng lặp (lỗi danh tính payload, không phải ưu tiên pool) và giữ `break` một event/nến/phía như cũ. Thứ tự candidate giữ đúng precedence cũ của projection: **equal trước swing**.

**RED trước sửa (assertion đầu fail, ghi trước khi sửa):** `r72_01` 14 failed / 17 passed; `canonical_sweep_requires_pool_records…` fail tại `assert canonical[swept_key] == []` (còn `index 2`); `missing_pool_provenance_fails_closed` 5/5 fail tại `assert canonical["swept_lows"] == []`; `acceptance_source_must_be_usable_at_sweep_close` fail tại `assert not events`; `source_usable_after_sweep_close_is_rejected` fail tại `assert swept_* == []`; `equal_pool_usable_time_is_max_of_both_sources` fail tại `assert equal_pool_events == []`; hai node producer fail tại `assert sweep["source_pool_id"] == record["pool_id"]`.

**Kiểm chứng (PowerShell, `D:/Projects/AIMarketAnalyst`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k r72_01 --tb=line
  14 failed / 17 passed   →   31 passed / 0 failed        (R72-01 XANH TOÀN BỘ)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
  25 failed / 98 passed   →   11 failed / 112 passed      (123 node, không đổi collection)
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=line
  5 failed / 11 passed    →   3 failed / 13 passed        (hai probe R72-01 nay xanh)
task57–71        108 passed   (không đổi)
retained SMC + 6 file integration (loại acceptance)       854 passed   (không đổi)
full §5          25 failed / 952 passed  →  11 failed / 966 passed
--collect-only   123 node
git diff --check  sạch
```

**RED còn lại: 11 (0 RED mới)** — đúng **R72-02×5, R72-03×2, R72-04×4** = F08…F10, không đụng ở lượt này. Probe còn lại 3: `test_r72_02_context_must_consider_earliest_eligible_setup_before_distance_rank`, `test_r72_03_nonowner_child_cannot_take_contribution_slot`, `test_r72_04_context_must_not_reassign_already_consumed_sweep` — cùng owner F08…F10.

**Assertion đã PASS ≠ toàn node PASS:** các node R72-01 nay PASS **toàn node** (không còn assertion treo). Hai fixture cố ý thiếu `usable_at` (`acceptance_source_must_be_usable_at_sweep_close[buy]`/`[sell]`) PASS với tư cách **ca thiếu provenance** — nguồn không khai `usable_at` ⇒ pool không có record ⇒ sweep rỗng vì thiếu provenance, **không** phải bằng chứng temporal độc lập; bằng chứng temporal thật là A3-040/041/042/043 + các node producer. Bảy node numeric-only/missing-provenance PASS nhờ consumer sweep fail closed, không phải nhờ pool.

**BLOCKER — cần TL quyết định (ngoài scope F07, đã đo cụ thể):** route production `core/smc_context.py::_smc_for_timeframe` gọi `detect_liquidity_sweeps(..., liquidity_pools=liquidity)` với `liquidity` dựng từ producer **legacy** `swing_points` (không có `confirmed`/`usable`/`usable_at`) ⇒ `records` rỗng ⇒ **sweep pool-driven của route này nay fail closed** (trước F07 lấy level từ numeric projection). Đo thực tế trên fixture 12 nến H1: `swing_lows` numeric `[99.5]`, `records` **0**, `liquidity_sweeps` và `zone_link_sweeps` đều **0** event. Đây là hệ quả trực tiếp của A3-005 luật 3 (“thiếu provenance không thành nguồn hợp lệ”), cùng loại khoảng trống TL đã chốt cho `_confirmed_swing_points` ở §A3.143 — nhưng `swing_points` là producer khác, không thuộc “sweep detector/caller/adapter” nên **không tự mở rộng scope**. Hai phương án cho TL: (a) đồng bộ producer legacy `swing_points`/`_filter_swings_by_atr` theo contract `confirmed`/`usable`/`usable_at`; (b) cho caller khai route legacy tường minh (không truyền `liquidity_pools`) — phương án (b) làm mất cả sweep của equal pool khỏi route đó. Không test nào trong 854 retained phủ hành vi này (đã đo: chỉ `test_pool_levels_are_used_when_explicitly_supplied` phụ thuộc pool path, và node đó **vẫn xanh** nhờ nhánh equal legacy).

**Hash:** `core/smc_context.py` `4E976A4D0A855F1B686AD173E96B910BD18A08061CEF0F6A1EB76F9CE76DBFF0` (trước F07: `D8DF4996CA55B7449259DB64827DA4C6508141B6E3E0D1C3477B5F7BFE976B62`); `tests/test_smc_gate72_fix_acceptance.py` `973D247AA0D68D320858A6B0ABD93CFC13DB97C89E0905B6A787A31F52192839` (**không đổi** — F07 không sửa test). Không sửa probe/golden/R56; giữ nguyên dirty changes; không commit/reset/xóa.

**DEFERRED_OBSERVATION:** (1) `source_swing_id = None` cho equal pool nhiều source — chưa có contract nào buộc một ID đại diện, để TL xác nhận khi làm F08/F10 (claim lineage dùng `source_ids`); (2) `records` vẫn cắt theo `_MAX_LIQUIDITY_LEVELS` để khớp 1:1 projection numeric — nếu cần record cho mọi pool eligible thì chốt cùng lúc; (3) evidence canonical thêm field `source_ids`/`source_pool_usable_at` mà legacy không có — khác biệt schema có chủ ý.

**NEXT_TASK = F08** — chưa thực hiện; dừng sau F07, chưa tự PASS C.

### A3.146 — TL chốt phạm vi production compatibility trước F08

**Ngày:** 2026-09-11. Đọc `_smc_for_timeframe`: producer vẫn là legacy swing_points (có lookback fallback và ATR filter), rồi pool/sweep dùng chung API với canonical. Gate40 review round3 §R40-03 giữ external payload/Analyze-Scanner legacy; mục4 cuối review cấm tự nối detector mới vào production. Gate72 review cũng loại production rollout khỏi scope.

**Quyết định:** không chọn nâng cấp/migrate `swing_points` hoặc thay nó bằng external_swing_points ở public route trong lượt này. Làm **F07/r1 — compatibility boundary tường minh**, caller đã biết legacy phải chọn adapter/nhánh legacy rõ ràng. Canonical records rỗng hoặc thiếu provenance vẫn fail closed; không được suy rằng record lỗi/rỗng là legacy. Không chỉ xóa key records ở mọi payload để né kiểm tra.

**Điều kiện tương thích:** khôi phục hành vi liquidity_sweeps và zone_link_sweeps của route legacy trước tác động canonical F06/F07, có regression qua `_smc_for_timeframe` thật. Không chấp nhận phương án “route legacy nhưng mất sweep/equal sweep hợp lệ” là hoàn thành. Giữ producer shape, swing selection/fallback/ATR filter, structure/leg count và các schema cam kết; không dùng ID/usable_at giả để tuyên bố legacy evidence là canonical. Đây là sửa regression của shared API, không rollout canonical trading logic.

Coder xác định baseline từ nguồn thực có sẵn và contract/fixture trước sửa; ghi rõ nguồn, không tự gọi HEAD là snapshot trước F07 khi các thay đổi còn uncommitted. Reuse fixture diagnostic12 nến và thêm equal-pool control phù hợp; expected event/time/level phải tính từ fixture hoặc đối chiếu baseline xác minh được, không lấy output vừa sửa làm oracle. Nếu không có baseline đủ kết luận semantics cần giữ, báo đúng thiếu gì trước khi thiết kế lại behavior.

**Scope F07/r1:** caller/adapter/sweep branch legacy tối thiểu + regression tests route public. Giữ canonical R72-01 xanh và missing records/provenance controls fail closed; không thay F08 ownership/F09/F10/scoring. Chạy targeted, cumulative A/B/F06/F07, acceptance, probes, task57–71 và full §5; cập nhật plan/matrix/ledger cùng lượt rồi dừng trước F08. Không sửa probe/golden/R56, không commit/reset, không mở tài liệu/task phụ.

**Phân biệt trạng thái:** báo cáo11 acceptance RED còn lại F08…F10 không chứng minh public route đã tương thích; blocker caller phải khép trước chuyển F08. Reviewer lượt này kiểm code/contract để chốt phạm vi, chưa chạy độc lập full F07 hoặc PASS checkpoint C. Equal-pool nhiều source không cần bịa source_swing_id đại diện; source_ids giữ lineage. Giới hạn pool-selection hiện hành không được tự bỏ ở F07/r1.

### A3.147 — F07/r1: compatibility boundary tường minh cho route public; khép blocker caller

**Ngày:** 2026-09-11. **Trạng thái:** F07/r1 **IMPLEMENTED** theo [§A3.146](#a3146--tl-chốt-phạm-vi-production-compatibility-trước-f08). **Blocker caller của F07 đã khép**: `liquidity_sweeps`/`zone_link_sweeps` của route legacy được khôi phục và có regression qua `_smc_for_timeframe` thật. Chưa F08/task73; chưa PASS checkpoint C.

#### 1. Baseline đã xác minh (nguồn thật, không mặc định HEAD)

| Nguồn | Nội dung | Vì sao dùng được |
|---|---|---|
| **B1** contract tests retained (đang xanh) | `test_smc_liquidity_sweeps_task67.py::test_pool_levels_are_used_when_explicitly_supplied` (payload numeric ⇒ `source_pool_id == "equal_high:110"`); `test_smc_liquidity_context_task71.py` (`source_pool_id` = swing id ở route không payload); `test_smc_context.py::TestDetectLiquiditySweeps`; `test_smc_sweep_linking.py` | Khóa semantics legacy bằng assertion, không phải suy đoán |
| **B2** bản ghi có ngày, viết **trước** thay đổi | fix-progress bảng A3.118 (dòng 6274): `assert canonical[swept_key] == []` → `[{… 'index': 2, …}]`, “core **cấp sweep từ level numeric**”; §A3.142 (F06) mô tả cùng hành vi | Chứng minh trước F06/F07 numeric **swing** level của payload vẫn cấp sweep ở `index 2` |
| **B3** contract payload | `docs/plans/smc-task-67-response.md`: “Explicit pool levels là source; legacy swing-only route vẫn tương thích”; evidence giữ `source_pool_id`/`source_pool` + source swing provenance | Chốt hình dạng evidence legacy |
| **B4** code legacy khôi phục | Khối `candidates()` tiền-canonical (đọc 4 key numeric, `source` = swing cùng level, `pool_id` fallback) | Khôi phục **nguyên văn**, không thiết kế lại |

**HEAD (fb9ea52) bị loại làm baseline — có bằng chứng:** `git show HEAD:core/smc_context.py` chỉ **1223 dòng** (bản hiện tại ~4700; diff uncommitted `+4378/-144`), và `detect_liquidity_sweeps` ở HEAD **không có** tham số `liquidity_pools` (`grep -c liquidity_pools` = 4, đều là key pool trong payload context). Vậy HEAD cũ hơn cả chuỗi task72, **không** phải snapshot “ngay trước F07”.

#### 2. Thay đổi

1. `core/smc_context.py::detect_liquidity_sweeps` thêm tham số caller-facing **`pool_provenance: "canonical" | "legacy"`** (mặc định `canonical`; giá trị khác ⇒ `ValueError("pool_provenance must be 'canonical' or 'legacy'")`).
2. Nhánh `"legacy"` khôi phục **nguyên văn** quy tắc tiền-canonical: mọi level numeric của phía là candidate, `source` = swing cùng level, `pool_id` fallback `kind:level`/swing id, **không** cổng `usable_at` (candidate legacy không mang `usable_at`).
3. `_smc_for_timeframe` (route Analyze/Scanner công khai) khai báo **tường minh** `pool_provenance="legacy"` cho cả `liquidity_sweeps` và `zone_link_sweeps`, kèm comment lý do (producer legacy `swing_points`, Gate40 §R40-03 giữ route này legacy).
4. **Không** migrate `swing_points`, **không** thay bằng `external_swing_points`, **không** xóa key `records` để né kiểm tra, **không** tạo `swing_id`/`usable_at` giả cho legacy. Detector **không** tự suy legacy từ `records` rỗng/lỗi — canonical vẫn fail closed (node mới có control xác nhận cùng payload đọc mặc định vẫn ra rỗng).

#### 3. Tests route public (mới, +2 node; collection 123 → 125)

| Node | Fixture | Expected tính từ fixture |
|---|---|---|
| `test_r72_01_public_route_keeps_legacy_pool_sweeps` | diagnostic 12 nến H1; pivot low idx4 level `99.5`; bar10 `(100,100.6,99.0,100.2)` | `liquidity_sweeps` **và** `zone_link_sweeps` `swept_lows == [(idx10, 99.5)]`, `reclaimed_at = stamp(11)`; `source_pool_id == "swing_low:99.5"`; `source_swing_id` rỗng; **không** có `source_ids`/`source_pool_usable_at`; `records == []` và swing không khai `usable_at` (precondition); control: cùng payload đọc canonical mặc định ⇒ **rỗng** |
| `test_r72_01_public_route_keeps_legacy_equal_pool_sweep` | control equal: pivot low `99.5`/`99.55` tại idx4/idx7 ⇒ mean `99.525`; bar10 crossing mean | `pools["equal_lows"] == [99.525]`; `liquidity_sweeps == [(idx10, 99.525)]`; `zone_link_sweeps == [(idx4, 99.525), (idx10, 99.525)]` (route này quét từ bar 0; bar pivot đầu có low `99.5 < 99.525` và close `101.5 > 99.525`); `reclaimed_at` `stamp(5)`/`stamp(11)`; `source_pool_id == "equal_low:99.525"`, `source_swing_id is None` |

Lưu ý đã đo: route public gọi detector **không truyền** `tick_size`/`atr_value` ⇒ `excursion = 0.0` (hành vi có trước, không đổi ở F07/r1) — nên điều kiện sweep trên route này là `low < level` / `high > level` nghiêm ngặt. `_filter_swings_by_atr` không chạy vì fixture 12 nến < `_ATR_FILTER_MIN_CANDLES = 15`.

#### 4. Kiểm chứng (PowerShell, `D:/Projects/AIMarketAnalyst`)

```text
python -m pytest … -k r72_01 --tb=short        33 passed / 0 failed   (R72-01 xanh, +2 node mới)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
  F07: 11 failed / 112 passed (123 node)  →  F07/r1: 11 failed / 114 passed (125 node)
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
  3 failed / 13 passed   (không đổi)
task57–71        108 passed   (không đổi)
retained SMC + 6 file integration (loại acceptance)       854 passed   (không đổi)
full §5          11 failed / 968 passed   (F07: 11 / 966)
--collect-only   125 node
git diff --check  sạch
```

**RED còn lại: 11 (0 RED mới)** — đúng R72-02×5, R72-03×2, R72-04×4 = F08…F10; probe còn lại 3 cùng owner. Canonical R72-01 giữ xanh; missing records/provenance vẫn fail closed; không giảm assertion, không skip/xfail.

#### 5. Blocker

**Không còn blocker caller.** Điều kiện TL đặt (“route legacy nhưng mất sweep/equal sweep hợp lệ” không được coi là hoàn thành) đã đạt: cả sweep swing **và** equal-pool đều được khôi phục, có regression qua `_smc_for_timeframe` thật và có control chứng minh canonical vẫn fail closed. Việc **không** migrate `swing_points` là quyết định phạm vi của TL (§A3.146), không phải blocker mở.

**Hash:** `core/smc_context.py` `12F7EA15999AFD8CD146A366006B1778412CC9A5FA5A5303553C38AB6AD81F80` (trước F07/r1: `4E976A4D0A855F1B686AD173E96B910BD18A08061CEF0F6A1EB76F9CE76DBFF0`); `tests/test_smc_gate72_fix_acceptance.py` `E16C5A3E0A78AC0CD6F3938F5C0FA106A3EE4CE17A3F7ADE8DD90F732F701B3B` (trước: `973D247A…192839`). Không sửa probe/golden/R56; giữ dirty changes; không commit/reset/xóa.

**DEFERRED_OBSERVATION:** (1) route public hiện khai `pool_provenance="legacy"` ở caller — nếu sau này `swing_points` được nâng theo contract usable thì phải chốt lại cờ này cùng lúc; (2) `source_swing_id` rỗng trên route public vì `swing_points` không phát `swing_id` — nay được test khóa để chứng minh không bịa ID; (3) `zone_link_sweeps` trên route public quét từ bar 0 với `excursion = 0` nên có thể phát event ở chính bar pivot (đã khóa bằng fixture equal-pool) — hành vi có trước, ghi lại để review.

**NEXT_TASK = F08** — chưa thực hiện; dừng sau F07/r1, chưa tự PASS C.

### A3.148 — F08: owner chọn từ mọi eligible claim theo causal claim time (R72-02)

**Ngày:** 2026-09-11. **Trạng thái:** F08 **IMPLEMENTED** theo fix-plan §F08. **R72-02 xanh toàn bộ** + probe R72-02 xanh. Chưa F09/task73; chưa PASS checkpoint C.

**RED ghi trước khi sửa.** Probe: `test_r72_02_context_must_consider_earliest_eligible_setup_before_distance_rank` → `assert sweeps["swept_lows"][0]["owner_setup_id"] == "early"` nhận `'late'` (zone **gần** thắng). Acceptance `-k r72_02`: **5 failed / 4 passed** — `..._acceptance_context_ranks_all_eligible_claims_by_causal_time`, `..._context_owner_follows_claim_time_under_input_permutation` (cả hai thứ tự chiếu `"late"`), `..._context_same_time_tie_follows_stable_setup_id` (`"beta-setup"` theo **zone ID**), và `..._missing_canonical_claim_time_fails_closed[reclaimed_at]`/`[setup_available_at]` (cấp owner từ mốc còn lại).

**Root cause:** `associate_sweeps_to_zones` xếp hạng candidate theo `(distance_atr, departure_gap, |time_delta|, zone_id, sweep_id)` — **distance quyết định owner** và khoá độc quyền setup ngay ở bước enumerate; `assign_sweep_ownership::claim_time` cho mốc còn lại/alias thay thế mốc thiếu; caller lấy `setup_available_at` từ **child** được chiếu (`zone.get("available_at")`).

**Thay đổi (chỉ linker + caller, không sửa test — T hash không đổi):**

| File/hàm | Nội dung |
|---|---|
| `core/smc_sweep_linking.py::associate_sweeps_to_zones` | Rank owner = claim time `max(reclaimed_at, setup_available_at)` sớm nhất → **setup ID ổn định**; distance/departure/`time_delta` **vẫn được tính cho eligibility và giữ trong link payload** nhưng **không** còn quyết định owner. Candidate thiếu mốc canonical xếp **sau** candidate đủ mốc, không lấy mốc còn lại làm thay thế. |
| `core/smc_sweep_linking.py::setup_availability_by_owner` + `setup_owner_key` (mới) | Availability của **setup** chốt **một lần** cho cả owner, order-independent (child khai sớm nhất) ⇒ child tình cờ đứng đầu không đổi nghĩa setup. |
| `core/smc_sweep_linking.py::assign_sweep_ownership::claim_time` | Claim **canonical** (khai `pool_id` hoặc `source_ids`): **buộc đủ** `reclaimed_at` **và** `setup_available_at`; thiếu mốc ⇒ không vào ownership + reason `SWEEP_CLAIM_TIME_MISSING`. **Không** alias, **không** fallback mốc còn lại. Claim **legacy** (không lineage) giữ nguyên compatibility default (alias + fallback một mốc) — boundary tường minh, không tự chuyển canonical thiếu field thành legacy. |
| `core/smc_context.py::_attach_zone_sweep_links` | `setup_available_at` của claim lấy từ map theo **setup** thay vì `zone.get("available_at")` của child. |

**Boundary giữ GREEN retained (quan trọng):** claim **gắn setup** đi theo claim time; zone **không có setup metadata** giữ nguyên thứ hạng legacy một-một. Lý do không thể suy đoán: retained `tests/test_smc_sweep_linking.py::test_one_sweep_is_assigned_to_only_one_best_zone` khóa `links == ["zone-departure-near"]` (tie-break theo `departure_gap` khi hai zone **không** có `setup_id`). Hai nhánh được tách bằng một vị trí **class** riêng trong tuple rank nên không bao giờ so chéo kiểu dữ liệu. Đây là **quyết định triển khai trong scope F08** (fix-plan F08: policy claim time không đổi), ghi rõ để TL xác nhận: class **setup-scoped** xếp trước class **zone-only** khi cùng tranh một sweep.

**Kiểm chứng (PowerShell, `D:/Projects/AIMarketAnalyst`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k r72_02 --tb=line
  5 failed / 4 passed  →  9 passed / 0 failed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q -k r72_02 --tb=line
  1 failed  →  1 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
  11 failed / 114 passed  →  6 failed / 119 passed      (125 node, collection không đổi)
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
  3 failed / 13 passed    →  2 failed / 14 passed
task57–71        108 passed   (không đổi)
retained SMC + 6 file integration (loại acceptance)       854 passed   (không đổi)
full §5          11 failed / 968 passed  →  6 failed / 973 passed
--collect-only   125 node
git diff --check  sạch
```

**RED còn lại: 6 (0 RED mới, không mất GREEN)** — `R72-03×2` (F09: `test_r72_03_acceptance_contribution_is_selected_within_owner_children` vẫn dừng ở `owner_claim["contribution_applied"] is True`; `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` dừng ở assignment history-only — **F10**) và `R72-04×4` (F10: replay/restore giữ `'later-owner'` thay vì `'original-owner'`, history mâu thuẫn được cấp lại owner). Probe còn 2: `r72_03` (F09), `r72_04` (F10). **Không node nào đổi điểm fail sang nhóm khác**; không kéo F09/F10 vào lượt này.

**Assertions nay chạy được:** các assertion **sau** điểm fail cũ trong 5 node R72-02 nay thực sự thực thi và PASS — vế bất biến qua permutation (`assignment_id`/`linked_zone_id`/`claim_eligible_at`), vế event-level của node tie (`alpha-setup`/`z-winner-child`), và **control dương** của hai node missing-time (claim đủ hai mốc vẫn thắng owner `setup`, `claim_eligible_at == max(stamp(11), stamp(13))`). Không cần thêm node: obligations đã có đủ từ checkpoint A.

**Hash:** `core/smc_sweep_linking.py` `DB5666904053D4E8C44DE866136A60BBFD16CA5C82185B58CEF95B5B06118FAC`; `core/smc_context.py` `8190C1871FEAD042D90EFBAF21CEC7A0D3C6A8A5FA184447F4AB03E084574FCA` (trước F08: `12F7EA15999AFD8CD146A366006B1778412CC9A5FA5A5303553C38AB6AD81F80`); `tests/test_smc_gate72_fix_acceptance.py` `E16C5A3E0A78AC0CD6F3938F5C0FA106A3EE4CE17A3F7ADE8DD90F732F701B3B` (**không đổi** — F08 không sửa test). Không sửa probe/golden/R56; giữ dirty changes; không commit/reset/xóa.

**DEFERRED_OBSERVATION:** (1) khi nhiều child cùng setup khai `available_at` khác nhau, map chọn **mốc sớm nhất** — fixture hiện có 1 child/setup nên chưa được kiểm; TL có thể muốn fail-closed thay vì lấy min; (2) class **setup-scoped trước zone-only** khi cùng tranh sweep chưa có fixture khóa — ghi để review; (3) `used_owners` trong `associate_sweeps_to_zones` vẫn là biến ghi-mà-không-đọc (có trước F08), không sửa để tránh mở rộng scope.

**NEXT_TASK = F09** — chưa thực hiện; dừng sau F08, chưa tự PASS C.

### A3.149 — F09: contribution chỉ được chọn trong owner children (R72-03)

**Ngày:** 2026-09-11. **Trạng thái:** F09 **IMPLEMENTED** theo fix-plan §F09. **R72-03 xanh phần F09** (3 passed / 1 failed — node còn lại thuộc **F10**) + probe R72-03 xanh. Chưa F10/task73; chưa PASS checkpoint C.

**RED ghi trước khi sửa.** Probe `test_r72_03_nonowner_child_cannot_take_contribution_slot` → `assert sum(c["contribution_applied"] for c in result["claims"]) == 1` nhận `0`. Acceptance `-k r72_03`: **2 failed / 2 passed** — `test_r72_03_acceptance_contribution_is_selected_within_owner_children` dừng ở `owner_claim["contribution_applied"] is True` → `assert False is True` (T:590); `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` dừng ở `restored["assignments"]["sweep"]` → `KeyError: 'sweep'` (T:2229).

**Root cause (khớp phân tích [§A3.120](#a3120--phân-loại-2-red-thuộc-r72-03-a3-084r1b-03)):** `assign_sweep_ownership` chọn `contribution_winner[sweep_id]` bằng khoá nhỏ nhất `(zone_id, visit_id, _claim_order)` trên **toàn bộ `normalized_claims`**, rồi mới kiểm owner khi chiếu xuống claim. Fixture để `"a-nonowner" < "z-owner"` nên non-owner thắng khoá; vế owner chặn non-owner, và vế khoá chặn luôn owner ⇒ **cả hai claim** `contribution_applied == False` (tổng **0**) trong khi assignment báo `True`.

**Thay đổi (chỉ `core/smc_sweep_linking.py::assign_sweep_ownership`, không sửa test — hash `T` không đổi):**

```python
    for claim in normalized_claims:
        sweep_id = str(claim["sweep_id"])
        assignment = assignments.get(sweep_id)
        if assignment is None or str(claim["setup_id"]) != assignment.owner_setup_id:
            continue           # F09: slot chỉ chọn trong owner children
        candidate_key = (zone_id, visit_id, _claim_order)   # tie-break đã duyệt, giữ nguyên
```

Giữ nguyên: owner selection (F08), lineage F06/F07, tie-break giữa owner children `(zone_id, visit_id, input order)` — **không** thêm priority mới; **không** hạ cờ `assignment.contribution_applied` để che tổng 0; **không** thêm bất biến assignment-flag ↔ tổng claim (chưa được chốt, đúng lưu ý §A3.120 mục 1). Không đụng history/replay (F10).

**Kiểm chứng (PowerShell, `D:/Projects/AIMarketAnalyst`):**

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q -k r72_03 --tb=line
  2 failed / 2 passed  →  1 failed / 3 passed        (node còn lại là F10)
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q -k r72_03 --tb=line
  1 failed  →  1 passed
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=no
  6 failed / 119 passed  →  5 failed / 120 passed    (125 node, collection không đổi)
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=no
  2 failed / 14 passed   →  1 failed / 15 passed
task57–71        108 passed   (không đổi)
retained SMC + 6 file integration (loại acceptance)       854 passed   (không đổi)
full §5          6 failed / 973 passed  →  5 failed / 974 passed
--collect-only   125 node
git diff --check  sạch
```

**Controls đã chạy:** `test_r72_03_duplicate_owner_children_keep_one_contribution_under_permutation` (duplicate + permutation, tổng `1`) **GREEN**; `test_r72_03_contribution_is_counted_per_sweep_not_per_list` (nhiều sweep độc lập, `{"sweep-a": 1, "sweep-b": 1}`) **GREEN**; probe `r72_03` (non-owner có zone ID nhỏ hơn) **GREEN**.

**Assertions nay chạy được:** hai assertion từng bị fail-fast che ở T:589/T:590 nay thực thi và PASS — tổng `contribution_applied` trên claims `== 1` và claim được credit có `setup_id == "early"`. Không cần thêm node: obligations đã có đủ từ checkpoint A.

**RED còn lại: 5 (0 RED mới, không mất GREEN)** — **toàn bộ thuộc F10**, giữ nguyên điểm fail như baseline §A3.148:

| Node | Assertion đầu fail | Nguyên nhân |
|---|---|---|
| `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | `restored["assignments"]["sweep"]` → `KeyError: 'sweep'` (T:2229) | assignment của owner history-only bị xoá khi cửa sổ hiện tại không còn child |
| `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` | `'later-owner' == 'original-owner'` (T:602) | caller cấp lại owner sau replay |
| `test_r72_04_context_repeat_after_json_restore_keeps_assignment` | `'later-owner' == 'original-owner'` (T:2271) | như trên, qua JSON restore |
| `test_r72_04_same_pool_observation_cannot_bypass_consumption` | `'later' == 'original'` (T:2353) | observation mới của cùng pool né consumption |
| `test_r72_04_conflicting_assignment_history_fails_closed` | `{'sweep': {...}} == {}` (T:2413) | history mâu thuẫn vẫn được cấp owner |

Probe còn **1**: `test_r72_04_context_must_not_reassign_already_consumed_sweep` (F10).

**Hash:** `core/smc_sweep_linking.py` `697AD4C3F0CCD6BCD3AF045416D047D65F8416CE987EF12ECF49338237D00736` (trước F09: `DB5666904053D4E8C44DE866136A60BBFD16CA5C82185B58CEF95B5B06118FAC`); `core/smc_context.py` `8190C1871FEAD042D90EFBAF21CEC7A0D3C6A8A5FA184447F4AB03E084574FCA` (**không đổi** — F09 không đụng caller); `tests/test_smc_gate72_fix_acceptance.py` `E16C5A3E0A78AC0CD6F3938F5C0FA106A3EE4CE17A3F7ADE8DD90F732F701B3B` (**không đổi**). Không sửa probe/golden/R56; giữ dirty changes; không commit/reset/xóa.

**DEFERRED_OBSERVATION:** ba mục F08 tại §A3.148 **giữ nguyên** cho review C (không mở rộng xử lý ở lượt này): (1) nhiều child cùng setup khai `available_at` khác nhau ⇒ chọn mốc sớm nhất; (2) class setup-scoped trước zone-only khi cùng tranh sweep; (3) `used_owners` ghi-mà-không-đọc. Thêm 1 mục mới: `assignment.contribution_applied` (`SweepAssignment`) và tổng `contribution_applied` trên claims **chưa** được ràng buộc bởi bất biến nào — F09 chỉ bảo đảm tổng trên claims đúng theo A-D03, không chốt quan hệ với cờ của assignment.

**NEXT_TASK = F10** — chưa thực hiện; dừng sau F09, chưa tự PASS C.

### A3.150 — F10 (history/consumption tại caller) + BẢN TRÌNH CHECKPOINT C

**Ngày:** 2026-09-11. **Trạng thái:** F10 **IMPLEMENTED**; **CHECKPOINT C = `WAITING_REVIEW`**. Chưa F11/task73; **không** tự PASS C/CLOSED/APPROVED gate72.

#### 1. F10 — RED ghi trước khi sửa

| Node | Assertion đầu fail (trước F10) |
|---|---|
| `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` | `later-owner == original-owner` (T:602) |
| `test_r72_04_context_repeat_after_json_restore_keeps_assignment` | `later-owner == original-owner` (T:2271) |
| `test_r72_04_same_pool_observation_cannot_bypass_consumption` | `later == original` (T:2353) |
| `test_r72_04_conflicting_assignment_history_fails_closed` | dict assignment có `sweep` trong khi expected rỗng (T:2413) |
| `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | `KeyError: sweep` (T:2229) |
| probe `test_r72_04_context_must_not_reassign_already_consumed_sweep` | `later-owner == original-owner` (P:120) |

**Nguyên nhân gốc:** caller gọi `mark_sweeps_consumed(liquidity_sweeps, ownership_claims)` **không truyền history**, nên lần attach sau tính lại owner từ cửa sổ mới; history chỉ tra theo `sweep_id` nên observation mới của cùng pool (khác `sweep_id`) không khớp; record history không tôn trọng được thì **rơi xuống nhánh xếp hạng thường** và cấp owner mới; sweep chỉ còn trong history không có claim hiện tại nên assignment **không được phát**; sweep đã consumed vẫn được link cho setup khác nên `linked_zone_id` bị đổi.

#### 2. Thay đổi (chỉ `core/`, **không** sửa test — hash `T` không đổi)

| File | Nội dung |
|---|---|
| `core/smc_sweep_linking.py::SweepAssignment` | Thêm `pool_id`/`source_ids` (**list**, JSON-native) = causal pool lineage của lần cấp owner (đúng interface A3-008/ma trận). |
| `core/smc_sweep_linking.py::assign_sweep_ownership` | Tra consumption theo **sweep ID trước, rồi theo causal pool lineage** (không theo sweep/index/thời điểm/level) ⇒ cùng pool không né consumption, pool mới (`pool-2`/`source_ids` khác) vẫn độc lập. Record **không thể tôn trọng** ⇒ **fail closed** + reason `SWEEP_OWNER_HISTORY_CONFLICT`, **không** reset history rồi cấp owner mới, **không** báo nhầm `SWEEP_OWNER_HISTORY_INCOMPLETE`. Owner chỉ còn trong **history** vẫn phát assignment đã biết (verbatim). |
| `core/smc_sweep_linking.py::associate_sweeps_to_zones` | Sweep **đã consumed** chỉ được link lại bởi **chính setup sở hữu** (owner key so với `owner_setup_id` đã ghi) ⇒ “sweep đã consumed không thành claim mới cho setup khác”. |
| `core/smc_sweep_linking.py::mark_sweeps_consumed` | `contribution_applied` của sweep = “có claim hiện tại nào được credit”; sweep chỉ còn owner trong history (không child hiện tại) ⇒ **False** (current contribution 0). |
| `core/smc_context.py::_attach_zone_sweep_links` | Dựng `assignment_history` từ chính payload sweep đã consumed và truyền `history_complete=True` **tường minh**; `pool_id` chỉ đưa vào history khi sweep có canonical `source_ids` (legacy numeric pool id **không** là identity); giữ `linked_zone_id` đã biết khi cửa sổ hiện tại không còn child (A3-078). |

Giữ nguyên: owner selection F08, contribution selection F09, lineage pool/sweep F06/F07, boundary legacy §A3.146, scoring/pool-selection/rollout. **Không** thêm bất biến assignment-flag ↔ tổng-claim (chưa chốt).

#### 3. Mapping F06…F10 → obligation → node/results (cùng snapshot)

| F | Obligation (matrix §4) | Node tiêu biểu | Kết quả |
|---|---|---|---|
| **F06** | Pool identity/provenance/usable time (R72-01) | `positive_pool_keeps_source_lineage_and_usable_time[buy,sell]`, `pool_identity_survives_source_permutation`, `equal_usable_at_reclaimed_is_temporally_eligible` | GREEN |
| **F06/r1** | Producer khai `usable_at` (TL §A3.143) | `actual_swing_producer_feeds_pool_and_sweep`, `internal_producer_declares_usable_at_at_confirmation_close`, `provisional_producer_declares_no_usable_at_and_no_canonical_record` | GREEN |
| **F07** | Sweep chỉ dùng records + cổng `usable_at <= reclaimed_at` (A-D01) | `canonical_sweep_requires_pool_records_not_numeric_levels[buy,sell]`, `missing_pool_provenance_fails_closed[5]`, `source_usable_after_sweep_close_is_rejected[buy,sell]`, `equal_pool_usable_time_is_max_of_both_sources`, `pool_sweep_evidence_survives_future_bars`, `pool_sweep_identity_survives_rolling_index` | GREEN |
| **F07/r1** | Caller legacy tường minh + khôi phục sweep route công khai (TL §A3.146) | `public_route_keeps_legacy_pool_sweeps`, `public_route_keeps_legacy_equal_pool_sweep` | GREEN |
| **F08** | Owner theo causal claim time (A-D02) | `acceptance_context_ranks_all_eligible_claims_by_causal_time`, `context_owner_follows_claim_time_under_input_permutation`, `context_same_time_tie_follows_stable_setup_id`, `missing_canonical_claim_time_fails_closed[reclaimed_at,setup_available_at]` + probe R72-02 | GREEN |
| **F09** | Contribution chỉ trong owner children (A-D03) | `acceptance_contribution_is_selected_within_owner_children`, `duplicate_owner_children_keep_one_contribution_under_permutation`, `contribution_is_counted_per_sweep_not_per_list` + probe R72-03 | GREEN |
| **F10** | History/consumption có hiệu lực tại caller (A-D06) | `acceptance_context_preserves_consumed_assignment_on_replay`, `context_repeat_after_json_restore_keeps_assignment`, `same_pool_observation_cannot_bypass_consumption` (+ control pool mới), `conflicting_assignment_history_fails_closed`, `assignment_survives_json_restore_with_late_only_window`, `incomplete_history_returns_explicit_reason`, `historical_owner_without_current_child_gets_zero_contribution` + probe R72-04 | GREEN |

#### 4. Caller/legacy compatibility regression

- **Route công khai `_smc_for_timeframe`** khai `pool_provenance="legacy"` (F07/r1) ⇒ `liquidity_sweeps`/`zone_link_sweeps` giữ event như trước canonical: `test_r72_01_public_route_keeps_legacy_pool_sweeps` (diagnostic 12 nến) + control equal-pool — **GREEN**, có control chứng minh cùng payload đọc mặc định canonical vẫn fail closed.
- **Pool payload numeric không có `records`** (contract task67): `tests/test_smc_liquidity_sweeps_task67.py::test_pool_levels_are_used_when_explicitly_supplied` giữ `source_pool_id == equal_high:110` — **GREEN** trong retained 854.
- **Zone không có setup metadata** giữ thứ hạng legacy một-một: `tests/test_smc_sweep_linking.py::test_one_sweep_is_assigned_to_only_one_best_zone` (`zone-departure-near`) — **GREEN**.
- **Claim không lineage** giữ compatibility default của helper (alias + fallback một mốc) — boundary tường minh, không tự chuyển canonical thiếu field thành legacy.

#### 5. Commands/counts trên cùng một snapshot (2026-09-11)

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=line
  125 passed / 0 failed          (125 node collect được; baseline F00: 65/51)
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=line
  16 passed / 0 failed           (16 node; baseline: 13 failed / 3 passed)
task57–71 (15 file)              108 passed
retained SMC + 6 file integration (loại acceptance)      854 passed
full §5 (test_smc* + 6 file integration, gồm acceptance)  979 passed / 0 failed
--collect-only acceptance        125 node
--collect-only probes            16 node
git diff --check                 sạch (exit=0)
```

#### 6. Hash code/tests + fingerprint bảo vệ

| Artifact | SHA256 |
|---|---|
| `core/smc_context.py` | `D2BD3E07F540F63D43EEA6F25971C56B5437A5E50F5E3754A54EF79D36E11A44` |
| `core/smc_sweep_linking.py` | `D0B07222A7930579CBB5989AB9C0EC7828B85FF52C1C2F1808D846D2C28C803E` |
| `core/smc_models.py` | `AEE437971AE15BF4A0B6995A30A3ED3C9F903550FF20C394670E7D3D1C47794B` |
| `core/smc_lifecycle.py` | `A99A338B4F9040242A0D00840150AA50E8269F20834DD58BA610E79167DEA45C` |
| `core/smc_confluence.py` | `EA5C4A52D4C4806F2E37AC1DCE6B18A2A07BE49F5D981317633A1D58C38D7051` |
| `tests/test_smc_gate72_fix_acceptance.py` (`T`) | `E16C5A3E0A78AC0CD6F3938F5C0FA106A3EE4CE17A3F7ADE8DD90F732F701B3B` |

**Fingerprint bảo vệ — 6/6 KHỚP ledger F00** ⇒ probe và hồ sơ R56 **không** bị chạm: probe `5B040D6A…B618B1C6`, golden `45437A90…70C79999`, session-contract `F04A0E64…433D50BB`, coder-handoff `AA682DA1…F28D301`, fixture `698CF8A2…54D2BDD5`, test R56 `F1975050…A253A5CA`. **5 file `core/` KHÁC ledger F00 là thay đổi có chủ đích của chuỗi F02→F10** (F02 `smc_lifecycle`/`smc_context`/`smc_models`, F03 `smc_context`/`smc_models`, F04 `smc_lifecycle`, F05 `smc_confluence`, F06–F07 `smc_context`, F08–F10 `smc_sweep_linking`/`smc_context`) — **không** phải chạm ngoài phạm vi. `T` **không đổi** trong F09/F10.

**Phạm vi file sửa cả chuỗi F06→F10:** `core/smc_context.py`, `core/smc_sweep_linking.py` (+ `core/smc_models.py`, `core/smc_lifecycle.py`, `core/smc_confluence.py` từ F02–F05). **Không** thêm/xoá file; giữ dirty changes; không commit/reset/xóa.

#### 7. Blocker và quyết định còn cần TL

**Không còn blocker kỹ thuật.** Các điểm cần TL xác nhận khi duyệt C (đều đã ghi DEFERRED_OBSERVATION, **không** tự chốt):

| # | Nội dung | Nguồn |
|---|---|---|
| 1 | Nhiều child cùng setup khai `available_at` khác nhau ⇒ map lấy **mốc sớm nhất** (fixture hiện 1 child/setup; có thể muốn fail-closed) | §A3.148 |
| 2 | Class **setup-scoped xếp trước zone-only** khi cùng tranh một sweep — chưa có fixture khóa | §A3.148 |
| 3 | `used_owners` trong `associate_sweeps_to_zones` là biến ghi-mà-không-đọc (có trước F08) | §A3.148 |
| 4 | `SweepAssignment.contribution_applied` và tổng `contribution_applied` trên claims **chưa** ràng buộc bởi bất biến nào | §A3.149 |
| 5 | `records` của pool vẫn cắt theo `_MAX_LIQUIDITY_LEVELS` để khớp 1:1 projection numeric | §A3.142 |
| 6 | `provisional` producer phát `usable_at: None` (TL cho phép “None hoặc không khai”; chọn None) | §A3.144 |
| 7 | `source_swing_id = None` cho equal pool nhiều source; evidence canonical thêm `source_ids`/`source_pool_usable_at` | §A3.145 |
| 8 | Route public khai `pool_provenance="legacy"` ở caller — nếu sau này `swing_points` được nâng theo contract usable thì phải chốt lại cờ này | §A3.147 |

**Điều kiện trình C đã đạt:** toàn acceptance **125/125** và **16/16** reviewer probes GREEN; không regression (retained 854, task57–71 108, full §5 979/0); `git diff --check` sạch.

#### 8. Bản trình C — mẫu gửi TL

```text
Checkpoint C — WAITING_REVIEW
Đã làm F06, F06/r1, F07, F07/r1, F08, F09, F10; chưa làm F11/task73.
Files + root causes + contract/test mapping: §A3.150 mục 2 và 3.
Expected đã giữ nguyên; 8 điểm cần TL xác nhận: §A3.150 mục 7.
Targeted: acceptance 125/125, probes 16/16; cumulative: task57–71 108, retained 854,
full §5 979 passed / 0 failed. Known RED còn lại: 0.
Manifest + diff + fingerprints: §A3.150 mục 6 (6/6 artifact bảo vệ khớp ledger F00);
git diff --check sạch.
Không task73, không production rollout; chờ TL duyệt checkpoint C.
```

**NEXT_TASK = (chờ TL duyệt C)** — F11 **chưa** thực hiện; dừng ở `WAITING_REVIEW C`, không tự PASS C/CLOSED/APPROVED gate72.

### A3.153 — TL review C lần2: còn canonical reclaim-time fallback của C-R1

**Ngày:** 2026-09-12. Reviewer chạy full §5 **981 passed**, hai regression C-R1/C-R2 **2 passed**, probes **16 passed**. T hash `1FD52BC4C4CA0151010A125B167AF3C166C93A4C4A1B0C89EE333D161C3595A1`. Giữ phần same-pool owner/assignment và history conflict đã đạt; không mở lại C-R2.

**C-R1 còn lỗi đã thuộc yêu cầu truyền mốc thật:** `_attach_zone_sweep_links` vẫn dựng `reclaimed_at` bằng `linked_sweep.get('reclaimed_at', linked_sweep.get('time',''))`. Canonical thiếu reclaim close bị thay bằng open time; helper nhìn thấy field đã được caller điền nên không thể fail closed theo A-D02/A3-008.

Diagnostic read-only: `_probe.sweep()` + source_pool_id=pool-A/source_ids=[source-A], xóa reclaimed_at (giữ time=stamp(10)); `_probe.attach([_probe.zone('child','owner',13,100,110)], sweeps)`. Actual sau call: **consumed=True, owner_setup_id=owner, assignment_id=smca-371aca1fa03ccf132f88, claim_eligible_at=stamp(13)** dù sweep không có reclaimed_at. Expected canonical không cấp assignment/contribution; không lấy time/sweep_time thay mốc thiếu.

**Sửa giới hạn:** caller canonical chỉ truyền reclaimed_at thật, giữ missing là missing; alias nếu cần chỉ ở nhánh legacy tường minh đã duyệt. Mở rộng regression caller C-R1 bằng ca canonical thiếu reclaimed_at nhưng còn time; kiểm không cấp owner/consumption/contribution mới, giữ control đủ mốc và legacy compatibility. Ghi reason thiếu mốc theo contract nơi output có hỗ trợ, không phát minh API logging mới. Không giảm assertion, không sửa probe/golden/R56. Chạy targeted+cumulative/full/probes, cập nhật hồ sơ cùng lượt và trình C lại; chưa F11/task73.

#### Chốt G1/G2 trong phạm vi adapter hiện tại

**G1 — quyết định TL:** chấp nhận min instant hợp lệ của các child cùng setup như mốc availability tổng hợp của setup trong adapter này (setup được biết khi child đầu tiên available). Child ra đời muộn không dời mốc của setup; không yêu cầu mọi child cùng available_at. Đây là quyết định semantics tường minh, không suy luật từ số PASS. Không đồng nghĩa được lấy reclaimed_at thay setup availability khi không có nguồn hợp lệ; canonical thiếu mốc vẫn fail closed. Diagnostic helper với cùng setup, child stamp13/stamp15: cả hai thứ tự cho stamp13. Không mở service/model availability mới ở task72.

**G2 — đính chính báo cáo và quyết định TL:** rank thực tế là completeness/claim time rồi mới class. Đã chạy direct associate: setup stamp15 đấu zone-only stamp12 ⇒ zone-only thắng; đấu stamp15 ⇒ setup thắng; đấu stamp17 ⇒ setup thắng. Chấp nhận thứ tự này ở mixed compatibility boundary: causal time trước, setup-scoped ưu tiên khi đồng hạng với zone-only; pure setup tie vẫn stable setup ID, legacy giữ phần tie-break đã cam kết. Không đúng khi mô tả “setup thắng bất kể claim time”. Không cần đổi thuật toán class trong lượt sửa C-R1; ghi lại đúng semantics trong bản trình.

Reviewer chỉ ghi hồ sơ, không sửa code/tests, không commit. A/B vẫn PASS; C CHANGES_REQUESTED vì diagnostic canonical missing-time ở trên, không vì các DEFERRED_OBSERVATION đã chốt.

### A3.151 — Tech Lead review checkpoint C: CHANGES_REQUESTED

**Ngày:** 2026-09-12. Reviewer đọc caller/linker/ownership/history và chạy full §5: **979 passed**. Kết quả khớp coder nhưng không bao phủ hai trường hợp vi phạm contract dưới đây. Không mở lại A/B hoặc mở scope ngoài F08…F10.

#### C-R1 [P1] — Canonical lineage/time bị mất tại caller; cùng pool cấp owner mới

`_attach_zone_sweep_links` dựng claim từ `link.to_dict()` + zone/side/setup availability, không truyền `pool_id`, `source_ids`, `reclaimed_at` tường minh. Helper coi claim không lineage là legacy; lookup same-pool không chạy dù history đã có lineage. Trái interface A3-008 luật3 và A-D06.

Diagnostic read-only dùng helpers của reviewer probe: tạo `sweep()` và thêm `source_pool_id='pool-A', source_ids=['source-A']`; `attach([zone('old','original',13,100,110)], sweeps)` cấp original. Giữ nguyên sweep consumed này trong payload, thêm observation từ `sweep()` với `sweep_id='sweep-later'`, cùng pool/source, reclaimed_at=stamp(12); attach zone('new','later',15,100,110). Actual: sweep cũ owner original/assignment smca-2c5edcc5aad86fd41d5a, sweep-later owner later/assignment smca-31db2bd735ee7bdacf49. History không thiếu: nằm ngay trong cùng payload.

**Sửa:** caller chuyển canonical provenance và hai mốc thật tới helper, boundary legacy tường minh; không để thiếu field tự downgrade canonical. Observation mới cùng pool phải giữ owner/assignment/consumption gốc, late child contribution0. Thêm regression qua caller thật (không chỉ helper), JSON round-trip, control pool khác. Giữ legacy route đã duyệt §A3.146. Không tự coi mọi cửa sổ là complete chỉ vì caller truyền True; không mở framework history mới.

#### C-R2 [P1] — History mâu thuẫn cùng pool phụ thuộc insertion order

`history_record` trả ngay history theo sweep_id hoặc candidate cùng pool đầu tiên; không kiểm toàn bộ record cùng lineage có mâu thuẫn. Diagnostic: hai history keys old1/old2, cùng pool-A/source-A, assigned_at=claim_eligible_at=stamp(13), nhưng owner first/second và assignment_id id-first/id-second. Claim mới setup later, zone child, sweep_id new-observation, side buy, reclaimed_at=stamp(11), setup_available_at=stamp(15), pool-A/source-A. Đảo thứ tự dict history: actual owner lần lượt first/second, reason_codes=[] cả hai. Expected fail closed + history-conflict reason, không cấp assignment mới hoặc chọn bản đầu.

**Sửa:** kiểm consistency tất cả history liên quan cùng canonical lineage trước restore/assign, kể cả khi có exact sweep_id match. Mâu thuẫn owner/assignment identity không được chọn theo thứ tự. Giữ incomplete khác conflict; không reset history. Thêm regression đảo history order và control nhiều observation cùng một assignment nhất quán. Chỉ đối chiếu fields authority đã có contract, không invent invariant contribution flag.

#### Xử lý tám ghi chú bản trình

- used_owners không đọc: cleanup deferred, không blocker, không cần task.
- Không bổ sung invariant assignment.contribution_applied ↔ tổng claims; nghĩa vụ F09 giữ theo A-D03.
- Cap pool-selection: giữ chính sách hiện hành, không mở rộng số pool.
- Provisional usable_at=None đã chốt §A3.143; equal source_swing_id=None được giữ vì source_ids mang nhiều nguồn, không bịa đại diện.
- Caller pool_provenance=legacy đã chốt §A3.146, không migrate production.
- setup availability nhiều child khác nhau và mixed setup/zone-only class chưa được xác nhận chỉ từ test xanh. Không đổi hai policy này trong lượt C-R1/C-R2; đưa bằng chứng contract và ảnh hưởng vào cùng bản trình lại để TL kết luận, không tự tạo task/audit riêng.

**Lượt tiếp:** sửa đúng C-R1/C-R2, regression RED→GREEN, targeted+cumulative/full §5/probes; đồng bộ plan/matrix/ledger và trình C lại một lần. Giữ A/B PASS, chưa F11/task73; không tự CLOSED/APPROVED gate72. Reviewer chỉ ghi tài liệu, không sửa code/tests hoặc commit.

### A3.152 — Sửa C-R1/C-R2 (review C §A3.151) + BẢN TRÌNH LẠI CHECKPOINT C

**Ngày:** 2026-09-12. **Trạng thái:** C-R1 + C-R2 **đã sửa**; **CHECKPOINT C trình lại = `WAITING_REVIEW`**. Chưa F11/task73; **không** tự PASS/CLOSED/APPROVED gate72.

#### 1. RED ghi trước khi sửa (tái lập diagnostic read-only của §A3.151)

**C-R1** — `attach([zone old/original 13])` trên sweep có `source_pool_id='pool-A'`/`source_ids=['source-A']`, rồi thêm observation `sweep-later` (cùng pool/source, `reclaimed_at=stamp(12)`) và `attach([zone new/later 15])`:

```text
C-R1 old  : original smca-2c5edcc5aad86fd41d5a
C-R1 later: later    smca-31db2bd735ee7bdacf49     ← trước sửa: KHÁC owner + KHÁC assignment
```

**C-R2** — hai history `old-1`/`old-2` cùng `pool-A`/`source-A`, owner `first`/`second`, assignment `id-first`/`id-second`:

```text
C-R2 as-given : {'new-observation': ('first','id-first'), 'old1': ('first',…), 'old2': ('second',…)}  reasons []
C-R2 reversed : {'new-observation': ('second','id-second'), 'old2': ('second',…), 'old1': ('first',…)} reasons []
```

**Nguyên nhân gốc:** (C-R1) `_attach_zone_sweep_links` dựng claim từ `link.to_dict()` + zone/side/availability, **không** truyền `pool_id`/`source_ids`/`reclaimed_at` ⇒ `is_canonical_claim` False ⇒ helper đọc claim là legacy, lookup same-pool không chạy dù history có lineage. (C-R2) `history_record` trả ngay record theo `sweep_id` hoặc candidate cùng pool **đầu tiên**, không kiểm các record cùng lineage có mâu thuẫn.

#### 2. Sửa (chỉ `core/`; `T` **có đổi** vì thêm regression)

| File | Nội dung |
|---|---|
| `core/smc_context.py::_attach_zone_sweep_links` | Dựng `sweeps_by_id` **trước** vòng claim; claim mang thêm `reclaimed_at` (thật, từ sweep) và **chỉ khi** sweep có canonical `source_ids` mới mang `pool_id`/`source_ids` ⇒ canonical không bị downgrade thành legacy tại boundary, legacy §A3.146 giữ nguyên. `pool_provenance="legacy"` của route public **không** đổi. |
| `core/smc_sweep_linking.py::assign_sweep_ownership` | Thêm `history_lineage`/`history_identity`/`conflicting_history`: trước khi restore/assign, **mọi** record liên quan (cùng `sweep_id` **hoặc** cùng canonical lineage) phải nhất quán về `(owner_setup_id, assignment_id)` — kể cả khi có exact `sweep_id` match; mâu thuẫn ⇒ `SWEEP_OWNER_HISTORY_CONFLICT` + không cấp assignment. Áp cả ở vòng echo owner-history-only. |

**Không** invent invariant contribution flag; **không** reset history; **không** đổi policy claim time/owner selection/contribution selection; **không** mở framework history mới.

#### 3. Regression đã thêm (collection **125 → 127**)

| Node | Bao phủ |
|---|---|
| `test_r72_04_caller_same_pool_observation_keeps_consumption` | C-R1 qua **caller thật** (`_attach_zone_sweep_links`): sweep cũ giữ `original`/`smca-2c5edcc5aad86fd41d5a`; `sweep-later` **giữ cùng owner + cùng `assignment_id`**; `late_zone["sweep_contribution_applied"] is False`; **JSON restore** giữa hai lượt; **control `pool-B`** vẫn cấp owner riêng (`other-setup`, assignment khác) |
| `test_r72_04_conflicting_history_is_order_independent_and_fails_closed` | C-R2: hai thứ tự history ⇒ `assignments == {}` + `SWEEP_OWNER_HISTORY_CONFLICT`, **không** báo nhầm `SWEEP_OWNER_HISTORY_INCOMPLETE`; **control nhất quán** (nhiều observation cùng owner+assignment) ⇒ vẫn cấp assignment, `reason_codes == []` |

#### 4. Commands/results trên cùng snapshot (2026-09-12)

```text
targeted C-R1            : old original/smca-2c5edcc5…  later later/smca-31db2bd7…   →  later original/smca-2c5edcc5…
targeted C-R2 (2 order)  : owner first / owner second, reasons []                   →  {} + SWEEP_OWNER_HISTORY_CONFLICT (cả hai)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=line       127 passed / 0 failed   (127 node)
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=line   16 passed / 0 failed    (16 node)
task57–71 (15 file)                                                          108 passed
retained SMC + 6 file integration (loại acceptance)                          854 passed
full §5 (test_smc* + 6 file integration, gồm acceptance)                      981 passed / 0 failed
git diff --check                                                             sạch
```

#### 5. Hash + fingerprint bảo vệ

| Artifact | Trước (trình C lần 1) | Sau C-R1/C-R2 |
|---|---|---|
| `core/smc_context.py` | `D2BD3E07…36E11A44` | `756BB8D35A5C0D169AD9F2F7B2528C3C2470B0E17F442E96D103812FFDBD2EB2` |
| `core/smc_sweep_linking.py` | `D0B07222…C28C803E` | `5B3C2DA85C910E432FA6C087486DD3AB2231D144AA6BD4732D2897D769658495` |
| `tests/test_smc_gate72_fix_acceptance.py` (`T`) | `E16C5A3E…2F701B3B` | `1FD52BC4C4CA0151010A125B167AF3C166C93A4C4A1B0C89EE333D161C3595A1` |

**6/6 artifact bảo vệ vẫn KHỚP ledger F00** — probe `5B040D6A…B618B1C6` (xác minh lại sau lượt này) + golden `45437A90…70C79999`, session-contract `F04A0E64…433D50BB`, coder-handoff `AA682DA1…F28D301`, fixture `698CF8A2…54D2BDD5`, test R56 `F1975050…A253A5CA`. 5 file `core/` khác ledger F00 vẫn là thay đổi có chủ đích của chuỗi F02→F10 + C-R1/C-R2. Không sửa probe/golden/R56; không commit/reset/xóa.

#### 6. Hai ghi chú TL yêu cầu đưa nguồn contract + ảnh hưởng vào bản trình (không đổi policy)

**G1 — setup availability khi nhiều child cùng setup khai khác nhau.** *Nguồn contract:* fix-plan §F08 (“Ghi rõ field source/caller nào cung cấp setup availability. Không dùng availability của child tình cờ đứng đầu để thay meaning setup đã thống nhất”) và matrix interface A3-008 (boundary canonical/legacy tường minh ở caller/adapter). *Đang làm:* `setup_availability_by_owner` chốt **một** mốc cho mỗi owner = **mốc sớm nhất** các child khai, order-independent; claim nào của setup đó cũng dùng mốc ấy. *Ảnh hưởng:* nếu sibling khai khác nhau, setup được coi là available sớm hơn child khai muộn ⇒ có thể thắng sweep bằng claim sớm hơn; **không** fixture nào khóa (mọi fixture hiện có 1 child/setup), và chưa có quyết định TL giữa “lấy min” và “fail closed/conflict reason”. *Không đổi ở lượt này.*

**G2 — class setup-scoped vs zone-only khi cùng tranh một sweep.** *Nguồn contract:* `associate_sweeps_to_zones` docstring (“A sweep may be assigned once to a setup… Zones without setup metadata retain the legacy one-to-one behavior”) + retained `tests/test_smc_sweep_linking.py::test_one_sweep_is_assigned_to_only_one_best_zone` (khóa `zone-departure-near` cho nhánh zone-only). *Đang làm:* tuple rank tách hai nhánh bằng một vị trí class riêng: claim **gắn setup** xếp trước claim **zone-only**, nên hai nhánh không bao giờ so chéo kiểu; trong từng nhánh thứ tự đã duyệt được giữ nguyên. *Ảnh hưởng:* khi một zone có setup và một zone không có setup cùng claim một sweep, zone có setup thắng **bất kể** claim time/khoảng cách; **không** fixture nào khóa thứ tự liên class này. *Không đổi ở lượt này.*

**Các ghi chú còn lại xử lý theo §A3.151:** `used_owners` = deferred cleanup (không blocker, không task); **không** thêm invariant `assignment.contribution_applied` ↔ tổng claims (nghĩa vụ F09 giữ theo A-D03); giữ cap pool-selection hiện hành; `provisional usable_at=None` đã chốt §A3.143; `equal source_swing_id=None` giữ (source_ids mang nhiều nguồn); caller `pool_provenance="legacy"` đã chốt §A3.146.

#### 7. Bản trình lại C — mẫu gửi TL

```text
Checkpoint C (trình lại) — WAITING_REVIEW
Đã sửa C-R1 và C-R2 theo §A3.151; chưa F11/task73.
C-R1: caller truyền canonical pool_id/source_ids + reclaimed_at thật; sweep-later giữ owner
      original + cùng assignment_id; late child contribution 0; JSON restore + control pool khác.
C-R2: kiểm consistency mọi history liên quan cùng lineage (kể cả exact sweep_id match);
      mâu thuẫn ⇒ fail closed + SWEEP_OWNER_HISTORY_CONFLICT, order-independent; control nhất quán.
Regression: 2 node mới (collection 125 → 127); targeted RED→GREEN ở mục 1 và 4.
Targeted: acceptance 127/127, probes 16/16; cumulative: task57–71 108, retained 854,
full §5 981 passed / 0 failed. Known RED còn lại: 0.
Hash: smc_context 756BB8D3…, smc_sweep_linking 5B3C2DA8…, T 1FD52BC4…;
6/6 artifact bảo vệ khớp ledger F00; git diff --check sạch.
Hai ghi chú setup availability (G1) và mixed owner classes (G2): nguồn contract + ảnh hưởng ở §6,
chưa đổi policy, chờ TL kết luận.
Không task73, không production rollout; chờ TL duyệt checkpoint C.
```

**NEXT_TASK = (chờ TL duyệt C)** — F11 **chưa** thực hiện; dừng ở `WAITING_REVIEW C`, không tự PASS/CLOSED/APPROVED gate72.

### A3.154 — Sửa nốt C-R1 (canonical reclaim-time fallback) + BẢN TRÌNH LẠI CHECKPOINT C (lần 3)

**Ngày:** 2026-09-12. **Trạng thái:** phần còn lại của C-R1 **đã sửa**; **CHECKPOINT C trình lại = `WAITING_REVIEW`**. Chưa F11/task73; **không** tự PASS/CLOSED/APPROVED gate72.

#### 1. RED ghi trước khi sửa (tái lập diagnostic §A3.153)

`_probe.sweep()` + `source_pool_id='pool-A'`/`source_ids=['source-A']`, xóa `reclaimed_at` (giữ `time=stamp(10)`), `attach([zone child/owner 13])`:

```text
RED: consumed=True  owner_setup_id=owner  assignment_id=smca-371aca1fa03ccf132f88  claim_eligible_at=stamp(13)  time=stamp(10)
zone: liquidity_sweep_linked=True  sweep_owner_setup_id=owner  sweep_contribution_applied=True
```

**Nguyên nhân gốc:** `_attach_zone_sweep_links` dựng `reclaimed_at` bằng `linked_sweep.get('reclaimed_at', linked_sweep.get('time',''))` ⇒ canonical thiếu reclaim close bị **thay bằng open time**; helper nhìn thấy field đã được caller điền nên không thể fail closed theo A-D02/A3-008.

#### 2. Sửa (chỉ `core/smc_context.py::_attach_zone_sweep_links`)

Claim canonical **chỉ** mang `reclaimed_at` khi sweep thật sự khai mốc đó:

```python
            claim = {**link.to_dict(), "zone_id": ..., "side": ..., "setup_available_at": ...,
                     "pool_id": ..., "source_ids": ...}
            # Chỉ reclaim close thật của sweep; thiếu thì GIỮ THIẾU — open time / `sweep_time` /
            # mốc còn lại không được thay thế. Alias legacy thuộc nhánh legacy của helper.
            if isinstance(linked_sweep, dict) and linked_sweep.get("reclaimed_at"):
                claim["reclaimed_at"] = linked_sweep["reclaimed_at"]
```

Cố ý **không** set key với giá trị `None`: `claim.get("reclaimed_at", <alias>)` của nhánh legacy sẽ bị `None` chặn mất alias, nên chỉ **bỏ key** mới giữ được legacy compatibility. Không đổi policy nào khác; không thêm API logging (reason `SWEEP_CLAIM_TIME_MISSING` đã có sẵn trong helper trả về, caller không phơi ra).

Kết quả đo sau sửa:

```text
canonical thiếu reclaimed_at (còn time) : consumed=False  owner=None  assignment=None  → không owner/consumption/contribution
canonical đủ hai mốc                    : consumed=True   owner=owner assignment=smca-371aca1fa03ccf132f88
legacy thiếu reclaimed_at (chỉ còn time): consumed=True   owner=owner (alias legacy giữ nguyên)
```

#### 3. Regression mở rộng (collection **127 → 128**)

`test_r72_04_caller_canonical_claim_without_reclaim_time_gets_no_owner`:
- **Ca chính:** canonical (có lineage) thiếu `reclaimed_at` nhưng còn `time` ⇒ sweep **không** `consumed`, không `owner_setup_id`, không `assignment_id`; zone **không** owner, **không** contribution. (Precondition: sweep vẫn link — `liquidity_sweep_linked is True` — nên kết quả rỗng là do **ownership** fail closed, không phải do mất link.)
- **Control đủ mốc:** cùng sweep với `reclaimed_at` thật ⇒ owner + `sweep_contribution_applied is True`.
- **Control legacy:** sweep **không** lineage, chỉ còn `time` ⇒ vẫn cấp owner (alias chỉ sống ở nhánh legacy tường minh).

#### 4. Commands/results trên cùng snapshot (2026-09-12)

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=line       128 passed / 0 failed   (128 node)
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=line   16 passed / 0 failed    (16 node)
task57–71 (15 file)                                                          108 passed
retained SMC + 6 file integration (loại acceptance)                          854 passed
full §5 (test_smc* + 6 file integration, gồm acceptance)                      982 passed / 0 failed
git diff --check                                                             sạch
```

Không regression, không giảm assertion, không skip/xfail, không sửa probe/golden/R56.

#### 5. Hash + fingerprint bảo vệ

| Artifact | Trình C lần 2 | Sau C-R1 (phần còn lại) |
|---|---|---|
| `core/smc_context.py` | `756BB8D3…DBD2EB2` | `0B87C6349DBAA072F1D0F04D50C84CBB1AA9DDEF5ACFDC97EA8BD12887A571FD` |
| `core/smc_sweep_linking.py` | `5B3C2DA8…69658495` | `5B3C2DA85C910E432FA6C087486DD3AB2231D144AA6BD4732D2897D769658495` (**không đổi**) |
| `tests/test_smc_gate72_fix_acceptance.py` (`T`) | `1FD52BC4…1C3595A1` | `24F4243E289769D314EEA82398AB00FC85022F2080CE857C69DD6DB4E3A1BFFC` |

**6/6 artifact bảo vệ vẫn KHỚP ledger F00** — probe `5B040D6A…B618B1C6` (xác minh lại), golden `45437A90…70C79999`, session-contract `F04A0E64…433D50BB`, coder-handoff `AA682DA1…F28D301`, fixture `698CF8A2…54D2BDD5`, test R56 `F1975050…A253A5CA`. Không sửa probe/golden/R56; không commit/reset/xóa.

#### 6. G1/G2 — ghi đúng quyết định §A3.153 (không đổi policy thêm)

| # | Quyết định TL | Ảnh hưởng đã ghi |
|---|---|---|
| **G1** | Availability tổng hợp của setup = **min instant hợp lệ** trong các child cùng setup (setup được biết khi child đầu tiên available); child ra đời muộn **không** dời mốc; không yêu cầu mọi child cùng `available_at`. **Không** đồng nghĩa được lấy `reclaimed_at` thay setup availability — canonical thiếu mốc vẫn fail closed. Không mở service/model availability mới ở task72. | Khớp `setup_availability_by_owner` hiện có (order-independent, min). Không đổi code ở lượt này. |
| **G2** | Thứ hạng thực tế = **completeness/claim time trước, class sau**; setup-scoped chỉ ưu tiên khi **đồng hạng** claim instant với zone-only; pure setup tie vẫn stable setup ID; legacy giữ tie-break đã cam kết. **Đính chính:** mô tả cũ ở §A3.152 mục 6 (“setup thắng bất kể claim time/khoảng cách”) là **sai**. | Đo trực tiếp: setup stamp15 đấu zone-only stamp12 ⇒ zone-only thắng; stamp15 ⇒ setup thắng; stamp17 ⇒ setup thắng. Không đổi thuật toán class ở lượt này; matrix đã ghi lại đúng semantics. |

Các ghi chú còn lại xử lý theo §A3.151 (không đổi ở lượt này): `used_owners` deferred cleanup; không thêm invariant contribution-flag; giữ cap pool-selection; `provisional usable_at=None` §A3.143; `equal source_swing_id=None` giữ; `pool_provenance="legacy"` §A3.146.

#### 7. Bản trình lại C — mẫu gửi TL

```text
Checkpoint C (trình lại lần 3) — WAITING_REVIEW
Đã sửa nốt C-R1 (canonical reclaim-time) theo §A3.153; C-R2/same-pool giữ nguyên; chưa F11/task73.
RED trước: canonical thiếu reclaimed_at (còn time) vẫn được cấp owner original/smca-371aca1fa03ccf132f88.
GREEN sau: không owner/consumption/contribution; control đủ mốc vẫn đạt; control legacy (chỉ còn time) vẫn đạt.
Regression: 1 node mới (collection 127 → 128).
Targeted: acceptance 128/128, probes 16/16; cumulative: task57–71 108, retained 854,
full §5 982 passed / 0 failed. Known RED còn lại: 0.
Hash: smc_context 0B87C634…, smc_sweep_linking 5B3C2DA8… (không đổi), T 24F4243E…;
6/6 artifact bảo vệ khớp ledger F00; git diff --check sạch.
G1/G2: đã ghi đúng quyết định §A3.153, không đổi policy thêm.
Không task73, không production rollout; chờ TL duyệt checkpoint C.
```

**NEXT_TASK = (chờ TL duyệt C)** — F11 **chưa** thực hiện; dừng ở `WAITING_REVIEW C`, không tự PASS/CLOSED/APPROVED gate72.

### A3.156 — F11: nghiệm thu end-to-end + BẢN TRÌNH CHECKPOINT D

**Ngày:** 2026-09-12. **Trạng thái:** F11 **IMPLEMENTED**; **CHECKPOINT D = `WAITING_REVIEW`**. Bản trình cuối duy nhất: [smc-task-72-response.md](smc-task-72-response.md). Chưa task73; **không** tự CLOSED 9 finding hoặc APPROVED gate72.

#### 1. Hai chuỗi end-to-end — mức bằng chứng

**Chuỗi (a) actual swing → pool → sweep → linked setup children → assignment → repeat/JSON restore.** Trước F11 bằng chứng **rời**: producer→pool→sweep ở A3-044/A3-066 (node `actual_swing_producer_feeds_pool_and_sweep`, `pool_sweep_evidence_survives_future_bars`, `pool_sweep_identity_survives_rolling_index`) và link→assignment→restore dùng **sweep tổng hợp của probe** (`_probe.sweep()`). Không node nào ghép actual producer vào caller thật ⇒ **bổ sung tối thiểu 1 node**:

`test_r72_chain_actual_producer_pool_sweep_reaches_owner_and_survives_restore` (collection **128 → 129**)

| Mắt xích | Nguồn thật | Giá trị khẳng định (suy từ fixture) |
|---|---|---|
| swing producer | `external_swing_points(values, "EURUSD", "H1", lookback=2)` trên 16 bar `_POOL_CAUSAL_ROWS` | pivot low `idx 4`, level `99.5`, `pivot_time stamp(4)`, `confirmed_at = usable_at = stamp(7)` |
| pool | `detect_liquidity_pools(..., tick_size=0.1, atr_value=1.0)` | record `swing_low` level `99.5`, `source_ids=[<swing_id>]`, `usable_at stamp(7)` |
| sweep | `detect_liquidity_sweeps(..., causal_only=True, lookback_bars=len(values), liquidity_pools=pools)` | event `idx 10`, level `99.5`, `reclaimed_at stamp(11)`; **lineage:** `source_pool_id == record["pool_id"]` |
| link + assignment | `_attach_zone_sweep_links((("demand", zones),), sweeps, candles=values, symbol="EURUSD", timeframe="H1", tf_minutes=60)`; setup `producer-setup` avail `stamp(13)` bounds `[99.0,100.0]`; setup `later-setup` avail `stamp(15)` | owner `producer-setup`; `claim_eligible_at = max(stamp(11), stamp(13)) = stamp(13)`; `linked_zone_id "producer-child"`; contribution owner `True`, `later-setup` không link/không owner/không contribution |
| repeat | attach lại cùng payload | owner + `assignment_id` giữ nguyên |
| JSON restore | `json.loads(json.dumps(sweeps))` rồi attach cửa sổ **late-only** | owner/`assignment_id`/`linked_zone_id`/`claim_eligible_at` giữ nguyên |

**Chuỗi (b) actual confirmed zone → visit → exit/reaction → invalidation/expiry → D1 evidence.** **Đã đủ bằng chứng, không thêm node:** A3-057 `d1_source_is_confirmed_by_fixture_break` (detector candidate + `replay_smc_structure` thật ⇒ confirmed) → A3-058 `d1_confirmed_zone_timeline_comes_from_fixture_retest` (`enrich_zones`, enter/exit/reaction = close bar 38/40/41) → A3-059 `d1_enriched_zone_survives_typed_restore` → A3-060 `d1_reaction_positive_reads_canonical_lifecycle` (`valid=True`, `score=1.0`) → A3-061 `d1_invalidated_source_is_terminal_for_the_consumer` / A3-062 `d1_expired_source_is_terminal_for_the_consumer` (`valid=False`, `score=0`, `D1_REACTION_STALE`, history giữ). Node A3-056 tự khai là **smoke**, không dùng làm bằng chứng chuỗi này.

#### 2. Kiểm BUY/SELL, cutoff, bounds/ID, fill, lifetime, dữ liệu lỗi, R56 (tests hiện có)

- **BUY/SELL:** mọi quy tắc có hướng đều chạy cả hai chiều (`[buy]`/`[sell]` ở usable-at, terminal, D1, cutoff, H4 reaction…).
- **cutoff:** `cutoff_equal_invalidated_at_is_terminal[buy,sell]`, `cutoff_equal_expired_at_is_terminal[buy,sell]` (biên **bao gồm**); `pool_sweep_evidence_survives_future_bars` lọc theo `reclaimed_at <= cutoff`.
- **original bounds/ID + full/partial fill:** `test_r72_09_full_fvg_fill_is_not_a_break` (fill `filled`/`fill_ratio 1.0`, `remaining_bounds {low:100,high:100}`, `zone_id`/`setup_id`/`original_bounds`/`low`/`high` **không đổi**, `broken is False`), `test_r72_08_invalid_canonical_zone_survives_typed_round_trip_consistently`.
- **lifetime/age:** `acceptance_reaction_cannot_cross_expiry_boundary[buy,sell]`, `h4_reaction_before/at/after_terminal_*`, `terminal_state_survives_enrich_restore_enrich[expired|invalid-buy|sell]`.
- **dữ liệu lỗi:** `intentional_invalid_data_reports_its_own_reason` (validator trả đúng một issue `SMC_OHLC_INVALID` ở `index 4`), `acceptance_corrected_task57_71_positive_fixtures_are_valid`; pool/sweep canonical thiếu provenance **fail closed**.
- **R56 acceptance:** 5 artifact R56 + probe **6/6 hash khớp ledger F00** (không đụng); `tests/test_smc_r56_01_session_acceptance.py` nằm trong retained **854 passed**.

#### 3. Commands/results — chạy mới trên cùng snapshot (2026-09-12)

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q            129 collected
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q -k "not chain_actual_producer"
                                                                                     128/129 (1 deselected)
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=line                 129 passed / 0 failed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=line              16 passed / 0 failed
task57–71 (15 file)                                                                   108 passed
retained SMC + 6 file integration (loại acceptance)                                    854 passed
full §5 (test_smc* + 6 file integration, gồm acceptance)                               983 passed / 0 failed
git diff --check                                                                      sạch
```

**Đối chiếu inventory node (không chỉ so tổng count):** `-k "not chain_actual_producer"` ⇒ đúng **128 node cũ** còn nguyên ⇒ Δ = **+1**, không node nào bị xoá/đổi tên ở F11; retained **854 không đổi** suốt chuỗi. Lịch sử tăng: 116 (A) → 118 (A3-066/e, A3-043/b) → 121 (3 regression B) → 123 (F06/r1 ×2) → 125 (F07/r1 ×2) → 127 (C-R1/C-R2 ×2) → 128 (C-R1 reclaim-time ×1) → **129 (F11 ×1)**.

#### 4. Manifest

| Artifact | SHA256 |
|---|---|
| `core/smc_context.py` | `0B87C6349DBAA072F1D0F04D50C84CBB1AA9DDEF5ACFDC97EA8BD12887A571FD` |
| `core/smc_sweep_linking.py` | `5B3C2DA85C910E432FA6C087486DD3AB2231D144AA6BD4732D2897D769658495` |
| `core/smc_models.py` | `AEE437971AE15BF4A0B6995A30A3ED3C9F903550FF20C394670E7D3D1C47794B` |
| `core/smc_lifecycle.py` | `A99A338B4F9040242A0D00840150AA50E8269F20834DD58BA610E79167DEA45C` |
| `core/smc_confluence.py` | `EA5C4A52D4C4806F2E37AC1DCE6B18A2A07BE49F5D981317633A1D58C38D7051` |
| `tests/test_smc_gate72_fix_acceptance.py` | `978AA7ECD044B9D41FF7AEBCDE650D2D5191DB5BAD8869D5C709A73A317E8E11` |

**6/6 artifact bảo vệ KHỚP ledger F00** (probe `5B040D6A…`, golden `45437A90…`, session-contract `F04A0E64…`, coder-handoff `AA682DA1…`, fixture `698CF8A2…`, test R56 `F1975050…`) ⇒ **không** sửa probe/golden/R56. 5 file `core/` khác ledger F00 là thay đổi có chủ đích của F02→F11. Tạo mới **1 file tài liệu**: `docs/plans/smc-task-72-response.md` (bản trình cuối, không phải báo cáo phụ). Giữ dirty changes; không commit/reset/xoá.

#### 5. Giới hạn chưa kiểm (chi tiết ở response mục 7)

(1) **Legacy production route chưa nâng cấp** — `_smc_for_timeframe` vẫn dùng producer legacy `swing_points` + khai `pool_provenance="legacy"` tường minh (§A3.146), nên route này không dùng canonical lineage/usable-time; muốn chuyển phải đồng bộ producer legacy rồi chốt lại cờ — **ngoài scope F11**. (2) Chưa production rollout canonical. (3) `records` pool bị cắt theo `_MAX_LIQUIDITY_LEVELS`. (4) G1/G2 chưa có fixture khóa ca biên nhiều-child/mixed-class. (5) `used_owners` ghi-mà-không-đọc (deferred). (6) Không có bất biến `assignment.contribution_applied` ↔ tổng claims. (7) `source_swing_id=None` cho equal pool nhiều source; evidence canonical thêm `source_ids`/`source_pool_usable_at`. (8) Reviewer chưa chạy độc lập F11 trong lượt review này.

**Không phát hiện lỗi vi phạm nghĩa vụ hiện có** trong lượt F11: không node nào đỏ, không regression, không cần mở rộng audit.

#### 6. Bản trình D — mẫu gửi TL

```text
Checkpoint D — WAITING_REVIEW
Đã làm F00…F11; A/B/C PASS (§A3.129/§A3.141/§A3.155). Chưa task73, chưa APPROVED gate72.
Bản trình cuối: docs/plans/smc-task-72-response.md (mapping9 finding; hai chuỗi e2e; commands/counts;
manifest/hash; giới hạn).
Snapshot trình D: acceptance 129P/0F (baseline 65F/51P, 116 node) · probes 16P/0F (baseline 13F/3P)
· task57–71 108P · retained 854P (không đổi) · full §5 983P/0F. Δcollection +1 (node chuỗi (a)),
không mất/đổi tên node cũ. Fingerprint bảo vệ 6/6 khớp ledger F00; git diff --check sạch.
Blocker: không. Giới hạn: legacy production route chưa nâng cấp + 7 điểm khác (response mục 7).
Không task73, không production rollout; chờ TL quyết định checkpoint D.
```

**NEXT_TASK = (chờ TL duyệt D)** — task73 **chưa** thực hiện; dừng ở `WAITING_REVIEW D`, không tự CLOSED/APPROVED gate72.
