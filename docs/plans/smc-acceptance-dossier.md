# Hồ sơ nghiệm thu SMC — task 15 và hồ sơ bàn giao Task143

> **Trạng thái:** `IMPLEMENTED — WAITING_REVIEW Task144`. Task129–138 đã `REVIEW PASS` (2026-09-17). Lô Task139–143 đã thực hiện xong và **dừng tại đây**; **Task144 chưa bắt đầu** và **không** được tự ghi REVIEW PASS/APPROVED. Đây không phải phê duyệt thay build đang dùng, rollout production hay auto-entry.
> **Mục đích:** nối phát hiện → task sửa → test/evidence, chọn command tái chạy được và xác định nguồn snapshot. §1–§7 là hồ sơ Task15 (giữ nguyên giá trị lịch sử); §8–§16 là **hồ sơ bàn giao Task143**.
> **Hồ sơ này không tuyên bố hiệu quả giao dịch, win rate hay lợi nhuận.** Xem §15.

## 1. Phạm vi và nguyên tắc nghiệm thu

- Mỗi finding phải có owner, task sửa, test/command và expected behavior.
- Synthetic fixture chỉ chứng minh logic cục bộ/tái hiện bug; không thay cho dữ liệu MT5 thật.
- Dữ liệu thật phải có symbol, source, `as_of`/`captured_at`, timeframe, tick size/provenance, cutoff và digest.
- Test xanh không thay cho Tech Lead approval ở task 16.
- Không yêu cầu backtest lớn, ML, order-flow thật hoặc đặt lệnh tiền thật.
- Execution smoke chỉ dry-run/mock dispatch; auto-entry phải giữ tắt.

## 2. Mapping phát hiện → task sửa → test/evidence

| Phát hiện/risks | Bằng chứng baseline | Task sửa dự kiến | Test/evidence bắt buộc | Expected sau sửa |
|---|---|---|---|---|
| Cutoff dùng nến forming/look-ahead | `smc-data-spec.md`; caller live có `capture_cutoff` nhưng detector target chưa đồng bộ | 17–20, 38–39 | Prefix replay cùng `as_of`; candle chưa đóng thêm vào không đổi kết quả | Không score nến chưa đóng; cùng cutoff live/replay parity |
| Swing/structure và protected swing sai | `smc_protected_swing_differs_from_latest.json` tái hiện `choch=False` khi latest khác protected | 21–37 | BUY/SELL mirror, first-BOS bootstrap anchor, source interval có pullback sau tracked pivot nhưng trước break, pivot/confirmed_at, wick-only, break/reclaim, same-candle, prefix/batch | Source/protected cursor deterministic; candidate-local LH/HL → reversal BOS mới xác nhận CHoCH |
| D1 proximity bị gọi là reaction | `smc_d1_proximity_only.json` trả bonus 2 hiện tại | 70–71 | D1 proximity-only, valid visit/reaction, stale reaction, legacy/canonical conflict | Proximity chỉ metadata; chỉ lifecycle reaction còn hiệu lực mới C/evidence |
| M15 rejection cũ xác nhận lại | `smc_m15_stale_rejection.json`: 1 rejection + 47 nến phẳng vẫn `confirmed=True` hiện tại | 73–79 | Visit hiện tại, rejection stale, trigger timeout, reclaim, M15 missing, xa entry, BUY lower-wick/SELL upper-wick, equal/under/doji/range-zero boundaries | Stale → `M15_NO_CONFIRMATION`, penalty `0`, B/Q/L/C và quality không đổi; chỉ readiness đổi |
| OB candidate dùng trước structure break | Zone spec và current detector nhận candle đối màu + impulse | 41–44, 54–55 | OB no-break, wick-only, break đúng/sai hướng, `available_at` | Chưa break là candidate/watch; confirmed chỉ sau close BOS liên quan |
| FVG tiny/weak/session gap | Current `detect_fvg` mới kiểm gap dương | 45–47, 54–55, 62 | Tiny gap, middle body/close-location yếu, session gap, partial/full fill | Gap không đạt bị loại; remaining bounds riêng; full fill không xóa original ID |
| S/D base/departure quá dễ | Current detector thử 3/5/7/10 và impulse 1.5 avg range | 48–49, 54–55 | Base quá rộng, departure râu dài, close trong base, BUY/SELL mirror | Chỉ base nén và departure đủ body/efficiency mới confirmed |
| Lifecycle visit/dwell/expiry không thống nhất | `smc_lifecycle.py` hiện overlap theo candle và stale threshold 20/30/50/80 | 57–65, 71 | H4/H1 parent vs M15 entry visit/nullable ID, first touch before H4 close, post-close link, exit/re-entry, delta 12/13 expiry, dwell, age, reclaim, invalidation | Parent TF sở hữu quality; M15 visit riêng; `dwell/age/reclaim` theo boundary chung; trigger expiry không xóa plan đã tính |
| Sweep/link bị cộng trùng hoặc unrelated | `smc_sweep_linking.py` có one-to-one/link version | 66–72 | Pool source, `claim_eligible_at`, exclusive owner theo thời điểm, setup đến muộn, same-time tie, child duplicate, restart/rebuild/prefix | Một sweep có một owner setup độc quyền; child owner chỉ một contribution; late setup không rút assignment; unrelated không xác nhận |
| B/Q/L/C và score cũ/cap/AI penalty | Current `smc_scorer.py` còn component/cap legacy | 80–90, 88 | Zero/max/boundary/null, age/dwell/reclaim/consumed, round-half-up, no-sweep, duplicate evidence, D1 no-reaction, OB/FVG/S-D raw geometry feature, weak/good/boundary, missing core | `S=4B+7Q+2L+2C`; raw 0..15; M15 penalty 0; bounds chỉ validation; D1 unreacted C=0 |
| Scorer chọn zone trước planner | `select_smc_zone` hiện ưu tiên H4 tuyệt đối; producer plan sau đó có thể trả None | 91–94, 97–99 | Shared planner mapping từ risk_engine/Scanner, exact entry/SL/TP/ATR, `RR=abs(TP-entry)/abs(entry-SL)`, min-RR pass/reject, candidate confirmation trace, cache/fallback | Analyze/Scanner/replay cùng semantic input dùng cùng plan policy; route chỉ adapter; valid watch giữ selected IDs, plan null |
| Readiness/consumer bypass hoặc null/no-zone lẫn nhau | `scanner_composition.py` có status/gate fail-closed; SMC target cần contract mới | 90, 95–96, 101–116 | M15 missing, valid watch/no-plan, invalid zone, countertrend, no-zone, core unavailable, gate block | Không READY khi thiếu/hỏng; valid watch giữ selected IDs/quality/lifecycle với plan null; `0` no-zone khác `null` unavailable |
| Persistence/UI đọc sai công thức/phiên bản | Current payload có legacy compatibility fields và version nội bộ | 117–128 | Round-trip, cache miss/corrupt, history, UI status, chart bounds, restart | Lịch sử giữ semantics cũ; UI không hiện engine/version; không sửa lệnh mở |

### Bổ sung theo round 3 (chưa phải runtime test)

- R16-01: first BOS phải có `H0/L0/H1/L1` với `pivot_time` và `confirmed_at`; `bootstrap_ready_at=max(confirmed_at(H1),confirmed_at(L1))` chỉ mở gate đánh giá break. `source_history_anchor_at` độc lập (H0 pivot trong fixture), nên `L1` vẫn eligible khi pivot trước ready nhưng confirmed trước break; break chỉ ghi ở candle close thực tế.
- R16-02: M15 replacement giữ nguyên B/Q/L/C, quality và parent lifecycle của từng canonical candidate; chỉ selection ID/final raw được phép đổi khi confirmation rank đổi.
- R16-05: execution ATR dùng chung `first_finite_positive(H4,D1)`. Với H1 formation ATR `.80`, width `.60`, H4 execution ATR `2.00`, distance `4.00`, expected width/distance đều pass (`4 <= 6`). Đây là owner proposal chờ duyệt, không phải parity runtime.
- R16-08: ordered/finite bounds chỉ là validation gate. OB examples dùng `base_width=zone_width`: weak `geometry=0`, `Q=.540`, `S=7.980`; good `.35 ATR` có `geometry=.8775`, `Q=.84550`, `S=10.11850`. FVG dùng `inverse(.70,.35,1)=.4615385`. Hai S/D examples dùng OHLC hợp lệ với `avg_range=1`, `formation_atr=2`, width/ATR `.33`: detector minimum cho `formation=.460`, `geometry=.825`, `Q=.635`, `S=8.645`; ratio `2.25` cho `formation=.710`, `geometry=.825`, `Q=.760`, `S=9.520`. Endpoint `[1.50,3.00]` giữ nguyên; detector minimum không tự nhận bonus.

## 3. Command kiểm tra đã chọn

### 3.1 Baseline/regression logic

Command baseline đã chạy ở task 3, dùng lại làm mốc trước/sau runtime change:

```text
python -m pytest tests/test_smc_canonical_golden.py tests/test_smc_composition.py tests/test_smc_consumer_phase6.py tests/test_smc_context.py tests/test_smc_directional_confluence.py tests/test_smc_domain_models.py tests/test_smc_m15_confirmation.py tests/test_smc_phase7_validation.py tests/test_smc_prefilter.py tests/test_smc_scorer.py tests/test_smc_scoring_phase0.py tests/test_smc_scoring_result.py tests/test_smc_sweep_linking.py tests/test_smc_zone_ai_review.py tests/test_smc_zone_audit_cache.py tests/test_smc_zone_lifecycle.py tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
```

Expected baseline hiện tại: `418 passed in 3.63s` trên Python 3.11.9/pytest 9.0.3. Sau mỗi task runtime chỉ chạy test bị ảnh hưởng trước, sau đó chạy lại command đầy đủ; không xóa test để làm xanh suite.

Target test groups sau khi code được triển khai:

```text
python -m pytest tests/test_smc_*.py tests/test_entry_engine.py tests/test_execution_revalidation.py tests/test_scanner_scenario_producers.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_replay.py -q
```

Các module chưa tồn tại khi task 15 được viết phải được thêm đúng task sửa tương ứng; không coi glob không match là bằng chứng đầy đủ.

### 3.2 Fixture/probe semantics

Các fixture tổng hợp hiện có:

```text
tests/fixtures/smc_m15_stale_rejection.json
tests/fixtures/smc_d1_proximity_only.json
tests/fixtures/smc_protected_swing_differs_from_latest.json
```

Command kiểm tra fixture JSON và expected contract:

```text
python -c "import json; from pathlib import Path; paths=['tests/fixtures/smc_m15_stale_rejection.json','tests/fixtures/smc_d1_proximity_only.json','tests/fixtures/smc_protected_swing_differs_from_latest.json']; [json.load(Path(p).open(encoding='utf-8')) for p in paths]; print('fixtures: valid=', len(paths))"
```

M15 stale probe đã tái hiện hiện tại: 48 candle, `confirmed=True`, `reaction=True`; expected sau sửa là not confirmed. D1/protected-swing probes được lưu trong progress log task 5. Các expected này là behavior contract để khóa sau review, không phải assertion cho behavior sai hiện tại.

### 3.3 Replay và snapshot validation

Command kiểm tra interface replay:

```text
python -X utf8 scripts/run_smc_validation.py --help
python scripts/scanner_pit_collector.py --schema
```

Khi có dataset PIT hợp lệ, command validation:

```text
python scripts/scanner_pit_collector.py --dataset <PIT_DATASET.jsonl> --out reports/smc/pit-evidence.json --pit-boundary 2026-08-13T00:00:00Z --minimum-rows 20
python -X utf8 scripts/run_smc_validation.py --input <REPLAY_INPUT.json> --output reports/smc/replay-report.json
```

Replay ngắn phải:

- chạy cùng prefix/cutoff với batch;
- so `zone_id`, `setup_id`, original bounds, event/visit times, selected ID, quality raw, readiness và reasons;
- kiểm tra snapshot liền kề không tạo cơ hội mới chỉ vì cùng visit;
- ghi rõ input digest/rule identity và không đọc nến tương lai.

### 3.4 Scanner/Analyze/UI/restart smoke

Command smoke target-only đang có:

```text
python scripts/scanner_smoke.py
python scripts/scanner_b11_validation.py
```

`scanner_smoke.py` và `scanner_b11_validation.py` là smoke/validation của Scanner contract hiện có; phải ghi rõ lỗi nền nếu script chưa tương thích với thay đổi SMC, không gọi đó là SMC pass. Smoke/help probe tại task 15 cho thấy `run_smc_validation.py --help` cần `python -X utf8` trên console Windows CP1258; `scanner_pit_collector.py --schema` thoát thành công. Sau khi nối canonical SMC:

- chạy Analyze và Scanner live trên cùng snapshot/cutoff;
- so selected setup/zone, quality, plan, readiness và reasons;
- mở Scanner → Detail → Chart, kiểm tra active/invalid zone, original/refined bounds, visit, trigger, expiry và missing-data text;
- restart ứng dụng, mở lịch sử/cache và xác nhận payload không đổi khi input/rule identity giống nhau;
- execution smoke dùng mock/dry-run, xác nhận `sends_real_order=false` và không có dispatch thật.

### 3.5 Performance

Target task 8 đã chốt: p50 `<=2s`, p95 `<=5s` cho một symbol/snapshot trên máy cá nhân, đo cold-cache và warm-cache riêng. Evidence cần ghi:

```text
Measure-Command { python scripts/scanner_smoke.py }
```

và benchmark harness task 136 với cùng dataset/máy:

```text
python scripts/smc_performance.py --dataset <PIT_DATASET.jsonl> --repeats 10 --report reports/smc/performance.json
```

`smc_performance.py` là artifact cần tạo ở task 136; command được ghi trước để khóa cách đo, không tuyên bố đã chạy. Report phải có p50/p95, cold/warm, số lần scorer/evaluator, số candidate, snapshot size và commit/environment. Không dùng performance để thay đổi score hoặc bỏ gate.

## 4. Nguồn snapshot và ma trận dữ liệu thật

### Nguồn được chấp nhận

| Nguồn | Cách lấy | Mục đích | Giới hạn |
|---|---|---|---|
| MT5 live history | `services/mt5_service.py` qua `controllers/scanner_controller.py`; freeze `capture_cutoff` trước fetch | 20–30 snapshot PIT cho task 131, cùng D1/H4/H1/M15 và symbol metadata | Cần terminal/broker; không tự tạo hoặc dùng forming candle |
| Stored scanner envelopes | `app_data/scanner_snapshots/`, `data/scanner_snapshots/` nếu tồn tại; validate bằng PIT collector | Replay/round-trip/restart và parity | Phải kiểm tra schema, cutoff, provenance; payload cũ chỉ historical |
| PIT JSONL corpus | `scripts/scanner_pit_collector.py` với digest và boundary | Audit source/coverage và lưu artifact | Không được gọi synthetic fixture là PIT thật |
| Synthetic SMC fixtures | `tests/fixtures/` task 4/5 và fixture mới sau review | Logic regression có expected rõ | Không dùng để kết luận market behavior/performance |

### Phân bổ 20–30 snapshot thật

Mục tiêu đề xuất là `24` snapshot, tối thiểu:

| Nhóm | Số tối thiểu | Nội dung cần có |
|---|---:|---|
| Trend tăng | 4 | BUY structure/zone, cả có và không M15 confirmation |
| Trend giảm | 4 | SELL mirror, cả có và không M15 confirmation |
| Range/neutral | 4 | Mixed/unknown structure, không default direction |
| Zone tốt/hỏng | 4 | Confirmed active đối chiếu invalid/expired/full-filled |
| Countertrend | 3 | Chưa CHoCH, CHoCH candidate, CHoCH confirmed |
| Data quality | 3 | M15 missing/insufficient, core coverage gap, metadata issue |
| Parity duplicates | 2 | Cùng input qua Analyze/Scanner/replay hoặc cold/warm cache |

Mỗi row phải có:

```text
symbol, source, captured_at, as_of, timeframe coverage,
candle digest, broker symbol, tick_size + source,
data-quality reasons, rule identity, input digest,
SMC state/selected ID/readiness observed output
```

Corpus thật cho SMC **đã có** (task 131, 2026-09-16): `reports/scanner/smc_real_snapshots/corpus.jsonl.gz` — 58 snapshot từ MT5 history, có cutoff/`as_of`, provenance terminal, tick size + nguồn, digest đầu vào canonical và verdict quan sát; ma trận phủ đủ nhóm tăng/giảm/range, vùng tốt/hỏng, thiếu/đủ M15 và data-quality. Ba row data-quality lấy theo broker symbol (`BWPUSDm`, `SOLUSDm`) vì đó là nơi broker này thật sự phát feed thiếu; chúng được ghi nhãn `symbol_group=broker_symbol_only`. Fixture tổng hợp **không** được dùng để thay dữ liệu thật ở bất kỳ mục nào dưới đây.

## 5. Checklist nghiệm thu

| Hạng mục | Artifact/command | Trạng thái khi lập hồ sơ |
|---|---|---|
| Logic regression | Baseline 418 test + target groups ở §3.1 | Baseline đã chạy; target sau runtime pending |
| Fixture semantics | Ba fixture task 4/5 + JSON validation/probes | Đã có fixture và tái hiện bug; assertion sau sửa pending |
| Dữ liệu thật | 24 PIT snapshots theo §4, MT5 provenance/digest | **ĐÃ CÓ (task 131):** 58 snapshot thật trong `reports/scanner/smc_real_snapshots/corpus.jsonl.gz`, đủ nhóm theo ma trận (`shortfalls = {}`); `scanner_pit_collector.py --schema` vẫn chạy được làm interface |
| Replay ngắn | `run_smc_validation.py`, prefix parity | **ĐÃ CHẠY (task 133):** 4 snapshot × 2 đoạn nến đã đóng, cùng cutoff; parity đường chạy live↔replay, prefix == prefix+future tail, xác định, không mốc thời gian sự kiện nào sau cutoff (`replay_parity.json`) |
| Analyze/Scanner parity | Cùng snapshot/cutoff, selected/quality/plan/status | **ĐÃ CHẠY:** parity 3 route ở task 114/116 và parity live↔replay trên dữ liệu thật ở task 133 |
| UI/chart | Scanner → Detail → Chart, missing/invalid/waiting/confirmed | **ĐÃ CHẠY (task 127 + 132):** smoke 7 trạng thái × 2 theme; QA chart expected/observed trên 58 snapshot thật, kèm ảnh render |
| Restart/history/cache | Round-trip, cache miss/correction, legacy read | **ĐÃ CHẠY (task 134):** 4 ca trên runtime root tạm, instance mới đọc lại khớp verdict; 6 biến thể hỏng đều fail-closed; cache hit/miss đúng; journal/open-order không đổi |
| Execution dry-run | Mock revalidation/dispatch, không order thật | **ĐÃ CHẠY (task 135):** control pass ở tầng engine, 4 ca âm + quote cũ chặn đúng mã, `place_calls = 0`; `sends_real_order` khoá cứng; inventory call site `order_send` |
| Performance | `smc_performance.py`, p50/p95 cold/warm | **ĐÃ CHẠY (task 136), ĐÃ SỬA (task 137–138):** lượt đo Task136 **không đạt** target Task8/Task15 (warm p50 6,9264 s / p95 7,2316 s; target 2 s / 5 s) và đã thành BLOCKING F129-136-01. Gói sửa Task137–138 sửa trọn root cause (tái dùng validation/pivot/ATR trong một cửa sổ đóng băng) và đo lại **đạt**: warm **p50 1,4344 s · p95 1,7951 s**, evaluator **1,0/snapshot**. Chi tiết ở §10 và nhật ký tiến độ |
| Backtest lớn | Không yêu cầu | Intentionally out of scope |

Task 15 hoàn tất việc chọn nguồn/command và ghi checklist; các mục pending là công việc thực thi ở task sau, không phải lý do để tự tuyên bố APPROVED.

---

# Hồ sơ bàn giao Task143 (2026-09-17)

## 8. Snapshot, baseline và diff boundary

| Hạng mục | Giá trị |
|---|---|
| Nhánh | `main`, `HEAD = c42770e` |
| Worktree | 39 file đã sửa / 16 mục chưa được git theo dõi (chuỗi SMC 73–143 **chưa commit**) |
| Baseline đối chiếu bắt buộc | `6 failed / 4555 passed / 7 skipped / 16 xfailed`; sáu failure **chỉ** là sáu node trong `tests/test_step3_fred.py` |
| Quy tắc đối chiếu failure | Bất kỳ failure khác tên/file/nguyên nhân là **finding mới** — không được gắn nhãn "FRED nền" |
| `git diff --check` | exit 0 (chỉ cảnh báo LF→CRLF) |
| Môi trường | Windows 11, Python 3.11.9, pytest 9.0.3, PyQt6/Qt 6.11.0, PyInstaller 6.20.0 |
| Build Sep 9 (`packaging/dist/`) | Bản **trước** toàn bộ chuỗi SMC — chỉ dùng để kiểm chéo, **không** phải bản đang nghiệm thu |
| `AGENTS.md` | Không tồn tại trong repository |

**Ranh giới diff của lô Task139–143:** chỉ 5 file, **không có file code sản phẩm nào**: `docs/guides/USER_GUIDE.md`, `docs/README.md`, `docs/plans/smc-acceptance-dossier.md`, `docs/plans/smc-implementation-progress.md`, `docs/plans/smc-implementation-plan.md`.

## 9. Mapping caller canonical — Scanner / Analyze / replay / persistence / UI

| Đường chạy | Điểm vào | Chuỗi canonical | Trạng thái |
|---|---|---|---|
| **Scanner (live)** | `core/scanner_live_producers.py:321` | `build_smc_snapshot` → `evaluate_smc_snapshot` (`:330`) → `canonical_smc` | production |
| **Analyze** | `core/analysis_pipeline.py:602` | `build_smc_snapshot` → `evaluate_smc_snapshot` (`:805`, `_step_score_scenarios`); prefilter `core/smc_prefilter.py:86` | production |
| **Replay** | `core/smc_validation.py:236` (`replay_canonical_snapshot`) | `evaluate_smc_snapshot` trên snapshot đóng băng | tool/script |
| **Persistence (ghi)** | `core/analysis_pipeline.py:208`, `controllers/scanner_controller.py:3318` | `build_smc_persistence_block` | production |
| **Persistence (đọc lại)** | `services/scanner_persistence_service.py:195,200,222` | `classify_persisted_smc`, `smc_block_of`, `read_smc_result_record` | production |
| **Cache kết quả** | `services/scanner_persistence_service.py:202–224` | `write_smc_result_record` / `read_smc_result_record` | **chưa nối live** — docstring: *"Nothing on the live route calls it."*; `cache/smc_results/` **chưa tồn tại trên đĩa** |
| **Adapter reader-only** | `core/smc_consumer_contract.py:202,414,462,481` | `read_canonical_selection`, `canonical_selection_of`, `selected_zone_for_side`, `scenario_preferred_zone_for_side` | **giữ nguyên, không tự gỡ** |
| **UI / Chart** | `ui/scanner_presentation.py:234,245`; `core/chart_payload.py:60,66,68,494` | đọc `canonical_selection_of` → `present_smc_row` / `build_smc_overlay` | production, chỉ đọc |

**Façade canonical (D101-01):** `core/smc_canonical_context.build_canonical_smc_context` là builder mặc định của `build_smc_snapshot` (`core/smc_snapshot.py:405–415`, chọn ở `:227–228`). Đường legacy `build_smc_context` / `_smc_for_timeframe` **không** có caller production; xem §12 để biết vì sao vẫn giữ.

## 10. Kết quả Task129–138 (đã `REVIEW PASS` 2026-09-17)

| Task | Nội dung | Kết quả đo được | Artifact |
|---|---|---|---|
| 129 | Golden fixtures | **Không sửa expected nào**; golden chạy xanh 76 passed; mọi diff golden đã có thuộc `c42770e` được ghi mapping kèm lý do | nhật ký |
| 130 | Regression suite | Bộ test phạm vi Task15 | nhật ký |
| 131 | Snapshot thực tế | **58 snapshot thật từ MT5** (55 symbol cấu hình + 3 row data-quality theo broker symbol `BWPUSDm`/`SOLUSDm`), cutoff + provenance + digest, ma trận đủ nhóm (`shortfalls = {}`) | `reports/scanner/smc_real_snapshots/corpus.jsonl.gz`, `report.json` |
| 132 | QA chart thực tế | Expected/observed trên 58 snapshot thật, kèm ảnh render 3 ca; **`protected_swing` giữ `SMC_PROTECTED_SWING_UNAVAILABLE`** — không thay bằng SL hay level legacy | `chart_qa.json`, 3 PNG |
| 133 | Replay ngắn | Cùng cutoff; `route_parity`, `prefix == wide`, xác định, `after_cutoff = 0`; **không mốc thời gian sự kiện nào sau cutoff** | `replay_parity.json` |
| 134 | Smoke restart / history | 4/4 ca, `failures = 0`; instance mới đọc lại khớp verdict; 6 biến thể payload hỏng đều fail-closed; cache hit/miss đúng; **journal/open-order không đổi** | `restart_smoke.json` |
| 135 | Execution smoke **không gửi lệnh** | Control pass ở tầng engine; 4 ca âm + quote cũ chặn đúng mã; **`place_calls = 0`**; `sends_real_order` khoá cứng | `execution_smoke.json` |
| 136 | Performance cục bộ | Sau gói sửa Task137–138: warm **p50 1,4344 s · p95 1,7951 s** (target ≤ 2 s / ≤ 5 s — **đạt**); evaluator/context builder **1,0/snapshot** | `performance.json` |
| 137 | Sửa lỗi nghiệm thu | Ba finding F129-136-01/02/03 xử lý theo root cause (xem §11) | `core/smc_structure_window.py`, `tests/test_smc_structure_reuse_task137.py` (13 node) |
| 138 | Kiểm tra lại sau sửa | Targeted + equivalence + replay/persistence parity + `scanner_smoke` + benchmark + full suite | nhật ký |

**Equivalence trước/sau tối ưu (Task137) — bằng chứng rời:** `scripts/smc_equivalence.py --limit 8`, hai nhánh `--no-reuse` và mặc định, cùng digest `sha256:8515f796084ef0f0053430179e82dce325a10e9ebba975de669eba4c49d339b6`.

## 11. Các review đã qua và finding đã đóng

| Review | Kết luận | Finding | Trạng thái |
|---|---|---|---|
| Gói sửa Task137–138 (F129-136-01/02/03) | `CHANGES_REQUESTED` → sửa → `REVIEW PASS` | **F129-136-01** performance vượt target → tái dùng validation/pivot/ATR trong **một** cửa sổ đóng băng | **CLOSED** — p50/p95 đạt target |
| | | **F129-136-02** Path-B composition che raw technical đã derive → provenance `ScannerCompositionResult.technical_raws` | **CLOSED** — `scanner_smoke.py` exit 0, không nới assertion |
| | | **F129-136-03** fixture UI Scanner phụ thuộc thời điểm → mốc cố định + seam `now=` (production truyền `None`) | **CLOSED** — 10/10 lượt xanh |
| Tái review F137-138-01 | `CHANGES_REQUESTED` → sửa → **đóng** | **F137-138-01** `StructureWindowReuse.owns` chỉ so hai endpoint ⇒ cửa sổ bị thay nến ở giữa vẫn được trả lời bằng cache cũ | **CLOSED** — `owns()` nay xác thực **mọi** Candle bằng object identity (không dùng equality theo giá trị); +6 node tái lập, reproducer đỏ 4/13 khi khôi phục kiểm cũ |
| **Task129–138** | **`REVIEW PASS` (2026-09-17)** | Không còn finding mở | **đủ điều kiện thực hiện Task139–143** |

Một lỗi trong chính code mới đã bị chính phép kiểm equivalence bắt và sửa: nhánh fallback của `filter_swings_by_atr` lúc đầu trả danh sách swing **chưa lọc** khi dãy không thuộc sở hữu. Đây là lỗi của bản sửa, không phải của sản phẩm.

## 12. Danh sách chính xác `DEFERRED` và `BLOCKED`

**`DEFERRED` (không đụng trong lô này):**

| Hạng mục | Lý do |
|---|---|
| `protected_swing` producer | Vẫn `SMC_PROTECTED_SWING_UNAVAILABLE` trên **cả 58** snapshot thật; muốn có lớp này trên chart phải mở việc publish `protected_swing_*` từ chain cấu trúc canonical ra carrier |
| Source-age / P10 | Quyết định policy riêng, chưa chốt |
| Cache production wiring | Cố ý chưa nối; `cache/smc_results/` chưa tồn tại trên đĩa |
| Adapter `selection → preferred_zone` | Adapter reader-only đang được giữ; **không tự gỡ** |
| Dispatch-clock injection | `revalidate_execution` đo tuổi tick bằng đồng hồ thật; khác với `now=` của đường đọc dòng Scanner (đã dùng cho fixture test) |
| Dọn đường chạy Task140 | **Không xóa gì.** Mọi ứng viên đều còn đường chạy, hoặc là seam/adapter/historical reader phải giữ — xem bảng dưới |
| Artifact commit/revert | `reports/scanner/smc_real_snapshots/` và `reports/scanner/smc_ui_smoke/` **chưa được git theo dõi**; ba artifact báo cáo smoke lại đổi nội dung khi chạy lệnh Task15 §3.4 |
| Rollout / auto-entry | Ngoài phạm vi; `sends_real_order` vẫn `False` |

**Kết luận Task140 — không xóa gì, kèm lý do từng ứng viên:**

| Ứng viên | Vì sao **không** xóa |
|---|---|
| `build_smc_context` (`core/smc_context.py:834`) | Là **seam monkeypatch có chủ đích**: `scripts/tier2_feasibility_gate.py:227` đọc `pipeline_module.build_smc_context`, `:243` gán lại, `:257` khôi phục. Xóa sẽ làm script đó `AttributeError` |
| `_smc_for_timeframe` (`core/smc_context.py:890`) | Chỉ tới được qua `build_smc_context`; thuộc đường legacy đã được Task72 nghiệm thu |
| `score_smc` (`core/smc_scorer.py:238`) | Là engine của `core/smc_validation.py:79`; `scripts/run_smc_validation.py` là lệnh nghiệm thu Task15 §3.3 |
| `project_smc_technical_raw` | Reader lịch sử cho ca linked-sweep |
| `smc_snapshot_identity`, `smc_result_cache_path`, `selection_payload_for_side`, `legacy_zone_for_side` | Utility/exported, còn dùng ở script/test |
| Import `build_smc_context` ở `core/analysis_pipeline.py:49` | Tưởng là import chết (không có lời gọi nào trong module) nhưng chính là **đích monkeypatch** ở trên ⇒ xóa là phá đường chạy |

**`BLOCKED`:**

| Hạng mục | Trạng thái | Phần đã làm được |
|---|---|---|
| Backup destination (Task141) | **`BLOCKED: backup destination not authorized`** | Checklist recovery hoàn thành; dry-run read-only trên temp storage đã chạy (`smc_restart_smoke.py --limit 4` → 4/4 ca) |
| Quét thật từ UI (Task142) | **BLOCKED** | Không có MT5 terminal/broker phục vụ trong môi trường này; phần tương đương đã kiểm bằng fixture canonical thật qua ba lớp UI và bằng corpus 58 snapshot thật |
| Nội dung Settings/Journal với dữ liệu thật (Task142) | **BLOCKED** | Route mở được, không raise; nội dung nạp từ nguồn ngoài nên chưa xác minh |

## 13. Recovery checklist (Task141) — xem nhật ký tiến độ

Inventory đầy đủ (7 nhóm: mã/build, config, persistence documents, journal/lệnh đang mở, corpus & artifact bằng chứng, cache tái tạo được, cache **không** phải nguồn sự thật) và quy trình 8 bước theo đúng thứ tự bắt buộc nằm ở [nhật ký tiến độ](smc-implementation-progress.md), mục *Task141*. Hai điểm phải nhớ khi khôi phục:

* **Persistence documents không phải archive.** `scanner_analysis/<scan_id>/` bị retention xóa sau **24 h**, `scanner_snapshots/scanner_*.json` sau **7 ngày** (`services/runtime_retention_service.py:207–225`).
* **`cache/smc_results/` không phải nguồn sự thật** và hiện chưa tồn tại; xóa/làm mới nhóm cache tái tạo là an toàn, nhưng **không** được đụng journal, lệnh đang mở, persistence documents hay artifact bằng chứng.

## 14. Command build/run (Task142) và kết quả

Xem bảng đầy đủ 10 mục ở [nhật ký tiến độ](smc-implementation-progress.md), mục *Task142*. Tóm tắt:

| Kiểm | Command | Kết quả |
|---|---|---|
| Compile | `python -m compileall -q main.py config core controllers services ui workers tools` | exit 0 |
| Import entry point + module SMC | 15 module | 15/15 OK |
| Màn hình chính, cả hai theme | boot `MainWindow` offscreen, mở mọi route | 7/7 route, không raise |
| Scanner → Detail → Chart | `QT_QPA_PLATFORM=windows python -X utf8 scripts/smc_ui_smoke.py` | exit 0 — 7 trạng thái × 2 theme |
| Scanner smoke (Task15 §3.4) | `python -X utf8 scripts/scanner_smoke.py` | exit 0 (`SMOKE OK` + `PATHB SMOKE OK`) |
| Restart / lịch sử / cache | `python -X utf8 scripts/smc_restart_smoke.py --limit 4` | exit 0 — 4/4 ca |
| Replay parity | `python -X utf8 scripts/smc_replay_parity.py` | exit 0 — 116 ca, `no_future_leak = True` |
| Build | `python -m PyInstaller ./pyinstaller.spec --clean --noconfirm` | exit 0 — `.exe` 22.650.649 B |
| Boot artifact | chạy `.exe` với `QT_QPA_PLATFORM=offscreen` | sống 25 s, RSS ~217 MB, không traceback |
| Corpus bằng chứng | `python -X utf8 scripts/smc_real_snapshots.py verify` | exit 0 — `rows: 58`, `problems: []` |
| Full suite (chạy một mình) | `python -m pytest tests -q` | **6 failed / 4555 passed / 7 skipped / 16 xfailed** (324,98 s) — **trùng baseline tuyệt đối**; đúng 6 failure, toàn bộ ở `tests/test_step3_fred.py`, cùng tên với baseline; không failure nào khác |
| Whitespace | `git diff --check` | exit 0 (chỉ warning LF→CRLF) |

**Lô Task139–143 không sửa một dòng code sản phẩm nào** (chỉ 5 file `.md`). Full suite được chạy để chứng minh điều đó, không phải để chứng minh một thay đổi hành vi — nên số `passed`/`skipped`/`xfailed` không đổi là kết quả đúng.

## 15. Đã xác minh kỹ thuật **so với** chưa chứng minh hiệu quả giao dịch

**Đã xác minh kỹ thuật (có bằng chứng tái lập được):** tính đúng của chuỗi canonical (identity, reason, lifecycle, readiness) qua parity ba đường và parity live↔replay trên dữ liệu thật; không đọc tương lai (`no_future_leak`, `after_cutoff = 0`); fail-closed khi dữ liệu thiếu/hỏng/lịch sử; restart/history/cache giữ nguyên verdict; revalidation chặn đúng và **không gửi lệnh** (`place_calls = 0`); hiệu năng trong target; UI/chart/Detail đọc cùng một kết quả canonical; build và boot artifact.

**Chưa chứng minh — và hồ sơ này không tuyên bố:** lợi nhuận, win rate, kỳ vọng dương, hay rằng điểm SMC cao thì lệnh dễ thắng hơn. **Không có backtest quy mô lớn, không tối ưu tham số, không order-flow thật, không giao dịch tiền thật.** Mọi con số trong hồ sơ này là số đo kỹ thuật. QA kỹ thuật **không** thay cho các điều kiện chứng nhận giao dịch mà chương trình đang yêu cầu.

## 16. Điều kiện còn lại để Tech Lead đánh giá Task144

1. Đối chiếu full suite lượt này với baseline `6F / 4555P / 7skip / 16xfail` — **từng failure**, không gắn nhãn "FRED nền" cho node khác.
2. Quyết định **`protected_swing`** tiếp tục `SMC_PROTECTED_SWING_UNAVAILABLE` (đúng như đã nghiệm thu) hay mở việc publish producer canonical.
3. Quyết định về **cache production wiring** (hiện deferred, chưa có bản ghi nào trên đĩa).
4. Quyết định về **artifact commit**: `reports/scanner/smc_real_snapshots/` và `reports/scanner/smc_ui_smoke/` chưa được git theo dõi, cùng ba artifact báo cáo smoke đã đổi nội dung.
5. Quyết định **`BLOCKED: backup destination not authorized`** của Task141.
6. Quyết định về việc build loại `core.analysis_pipeline`/`core.analysis_engine` (tiền tồn tại) có cần xử lý trước khi bàn giao `.exe` hay không.
7. Quyết định mở hay đóng các việc `DEFERRED`: dispatch-clock injection, adapter cleanup, source-age/P10.
8. Nếu cho phép thay bản đang dùng: các điều kiện chứng nhận execution hiện có **vẫn giữ nguyên**; **không** tự bật auto-trade.

## 6. Tài liệu trình Tech Lead tại task 16

Gói review gồm:

1. [smc-data-spec.md](smc-data-spec.md)
2. [smc-structure-spec.md](smc-structure-spec.md)
3. [smc-parameter-table.md](smc-parameter-table.md)
4. [smc-zone-spec.md](smc-zone-spec.md)
5. [smc-lifecycle-spec.md](smc-lifecycle-spec.md)
6. [smc-bqlc-spec.md](smc-bqlc-spec.md)
7. [smc-readiness-spec.md](smc-readiness-spec.md)
8. [smc-selection-spec.md](smc-selection-spec.md)
9. [smc-compatibility-spec.md](smc-compatibility-spec.md)
10. Hồ sơ này và [smc-implementation-progress.md](smc-implementation-progress.md)

Tech Lead cần ghi rõ `APPROVED`, hoặc chỉ ra finding/ngoại lệ và task/spec phải sửa. Khi chưa có approval, không triển khai task 17.

## 7. Tiêu chí hoàn thành task 15

- Có mapping phát hiện → task sửa → test/evidence và expected behavior.
- Có command baseline, fixture, replay, PIT, smoke/UI/restart và performance; command không được hiểu là đã chạy nếu hồ sơ ghi pending.
- Có nguồn snapshot thật, provenance/digest/cutoff và ma trận 20–30 snapshot; không lẫn synthetic với real.
- Checklist bao gồm logic, dữ liệu thật, replay ngắn, UI/scan/restart, execution dry-run và performance; không yêu cầu backtest lớn.
- Đã đánh dấu rõ phần baseline đã có và phần pending cần task sau; không tự báo APPROVED.
- Sau task này phải dừng ở `WAITING_REVIEW` cho Tech Lead task 16.
