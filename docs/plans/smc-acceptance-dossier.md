# Hồ sơ nghiệm thu SMC — task 15

> **Trạng thái:** READY FOR TECH LEAD REVIEW — không tự chuyển qua task 16.  
> **Mục đích:** nối phát hiện → task sửa → test/evidence, chọn command tái chạy được và xác định nguồn snapshot. Hồ sơ này không tuyên bố hiệu quả giao dịch, win rate hay lợi nhuận.

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

Hiện tại repo chưa có corpus MT5 20–30 snapshot được xác nhận cho SMC. Đây là trạng thái `PENDING_DATA` của checklist nghiệm thu, không được đánh dấu đạt bằng fixture tổng hợp.

## 5. Checklist nghiệm thu

| Hạng mục | Artifact/command | Trạng thái khi lập hồ sơ |
|---|---|---|
| Logic regression | Baseline 418 test + target groups ở §3.1 | Baseline đã chạy; target sau runtime pending |
| Fixture semantics | Ba fixture task 4/5 + JSON validation/probes | Đã có fixture và tái hiện bug; assertion sau sửa pending |
| Dữ liệu thật | 24 PIT snapshots theo §4, MT5 provenance/digest | `PENDING_DATA` — chưa có corpus thật trong repo |
| Replay ngắn | `run_smc_validation.py`, prefix parity | Command đã chọn; chạy sau canonical runtime |
| Analyze/Scanner parity | Cùng snapshot/cutoff, selected/quality/plan/status | Pending integration tasks 101–116 |
| UI/chart | Scanner → Detail → Chart, missing/invalid/waiting/confirmed | Pending tasks 121–127 |
| Restart/history/cache | Round-trip, cache miss/correction, legacy read | Pending tasks 117–120 |
| Execution dry-run | Mock revalidation/dispatch, không order thật | Pending task 135 |
| Performance | `smc_performance.py`, p50/p95 cold/warm | Target đã khóa; harness task 136 pending |
| Backtest lớn | Không yêu cầu | Intentionally out of scope |

Task 15 hoàn tất việc chọn nguồn/command và ghi checklist; các mục pending là công việc thực thi ở task sau, không phải lý do để tự tuyên bố APPROVED.

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
