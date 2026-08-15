# Scanner V4 — Kiến trúc cho phần mềm cá nhân

> - **Bối cảnh:** ứng dụng cá nhân, chạy cục bộ.
> - **Mục tiêu tài liệu:** mô tả chức năng, cấu hình, kiểm thử và cách chuyển runtime.
> - **Runtime hiện tại:** `scanner-v3` / `scanner-features-v3`.
> - **Target:** `scanner-v4` / `scanner-features-v4`.
> - **Tiến độ:** Bước 00–12 `DONE` (code cutover xong, full suite 3727 xanh); Bước 13 `TODO`.
> - **Migration:** cutover trực tiếp sang V4, không duy trì hai scorer trong runtime.
> - **Cập nhật tài liệu:** 14/08/2026.

Tài liệu này là nguồn chuẩn cho Scanner V4. Nó cố ý chỉ giữ những nội dung ảnh
hưởng trực tiếp tới chương trình:

- công thức score;
- gate và quyết định;
- cấu hình mặc định;
- schema/version;
- backtest, persistence và replay;
- kiểm thử;
- cutover và rollback.

`DONE` nghĩa là code, test và tài liệu trong phạm vi của bước đã hoàn tất. Nó
không có nghĩa V4 đã chạy live. Runtime V3 được thay bằng V4 ở Bước 12 (đã xong ở
mức code cutover + full suite xanh); việc mở order workflow thật thuộc Bước 13.

## 1. Mục tiêu và phạm vi

Scanner V4 tách ba câu hỏi độc lập:

1. **TechnicalScore:** setup kỹ thuật mạnh tới đâu?
2. **Gate:** dữ liệu và điều kiện thị trường có cho phép tiếp tục không?
3. **Decision:** với score và toàn bộ gate, trạng thái tối đa là gì?

Các quyết định nền:

- `TechnicalSignalScore` chỉ gồm **Trend, Momentum, Location, SMC**.
- Risk legacy không còn là scored component.
- Macro không cộng/trừ score; Macro chỉ tác động qua gate/cap.
- News, spread, connectivity, freshness và volatility chỉ nằm trong
  `MarketSafetyGate`.
- Gate không được sửa score. Score cao không thể vượt `BLOCK` hoặc dữ liệu thiếu.
- Evidence và Execution độc lập với Technical.
- Ranking ưu tiên trạng thái trước, score sau.
- Artifact V3 chỉ đọc để audit, không replay hoặc gắn nhãn thành V4.
- Rollback dùng nguyên release trước đó, không bật lại scorer V3 bên trong release V4.

“Risk legacy” ở đây là `risk_condition` đang trộn ATR, news và spread vào điểm.
SL/TP, position sizing, account guard, portfolio guard và execution guard vẫn là
chức năng bắt buộc.

## 2. Luồng xử lý một pair

```text
Immutable pair snapshot
  ├─ Technical Context + SMC
  │    ├─ TechnicalSignalScore BUY
  │    └─ TechnicalSignalScore SELL
  ├─ MarketSafetyGate
  │    ├─ Connectivity
  │    ├─ Candle freshness
  │    ├─ Spread
  │    ├─ News/Event
  │    └─ Volatility
  ├─ Chọn side từ TechnicalScore + score gap
  ├─ Scenario/Entry/SL/TP/R:R
  ├─ EvidenceScore + ExecutionQualityScore + SetupScore cho BUY/SELL
  ├─ MacroAssessment → MacroGate cho side được chọn
  ├─ Account/Portfolio/Journal/Execution gates
  └─ Decision → Candidate → Ranking
```

Thứ tự canonical:

1. Capture một snapshot immutable có timestamp và provenance.
2. Validate version và dữ liệu technical bắt buộc.
3. Tính TechnicalScore độc lập cho BUY và SELL.
4. Chạy MarketSafetyGate.
5. Tính BUY/SELL gap và chọn side chỉ từ TechnicalScore.
6. Dựng scenario cho side được chọn. Nếu TechnicalScore hòa, chọn BUY để deterministic.
7. Tính Evidence, Execution và SetupScore riêng cho cả BUY và SELL.
8. Dựng MacroAssessment và chạy MacroGate một lần cho side được chọn.
9. Chạy các gate còn lại.
10. Tạo decision và candidate bằng một đường duy nhất.
11. Ranking theo trạng thái rồi mới theo chất lượng setup.
12. Nếu candidate đạt `READY_NOW`, revalidate dữ liệu thực thi trước khi gửi lệnh thật.

Gate có thể chặn hành động nhưng không được làm mất score/scenario đã tính hợp lệ.
UI phải hiển thị được “setup tốt nhưng đang bị chặn”.

## 3. TechnicalSignalScore

### 3.1 Bốn thành phần

| Component | Raw range | Vai trò |
|---|---:|---|
| Trend | 0–25 | Hướng và cấu trúc xu hướng |
| Momentum | 0–20 | Xác nhận động lượng |
| Location | 0–25 | Chất lượng vị trí |
| SMC | 0–15 | Cấu trúc/vùng SMC canonical |

Risk, Macro, correlation, AI verdict và CHOCH không được sửa TechnicalScore.

### 3.2 Trọng số theo regime

| Regime | Trend | Momentum | Location | SMC | Tổng |
|---|---:|---:|---:|---:|---:|
| `trending_up` / `trending_down` | 40 | 20 | 20 | 20 | 100 |
| `ranging` | 10 | 10 | 40 | 40 | 100 |
| `volatile` | 20 | 10 | 40 | 30 | 100 |
| `unknown` | 25 | 25 | 25 | 25 | 100 |

### 3.3 Công thức

```text
contribution_i =
    clamp(raw_i, 0, raw_max_i) / raw_max_i × regime_weight_i

technical_signal_score =
    ROUND_HALF_UP(clamp(sum(contribution_i), 0, 100))
```

Quy tắc:

- dùng precision đầy đủ cho từng contribution;
- không `int()` từng thành phần;
- chỉ `ROUND_HALF_UP` một lần ở tổng;
- lưu raw và scaled contribution theo đúng side;
- BUY/SELL gap chỉ tính từ TechnicalScore BUY/SELL.

Module canonical: `core/technical_signal_scorer.py`.

## 4. SetupScore và FinalScore

```text
setup_score = technical_signal_score × 0.65
            + evidence_score × 0.20
            + execution_quality_score × 0.15

final_score = setup_score
```

`final_score` chỉ là compatibility alias của `setup_score`.

| Input | Khi thiếu/invalid |
|---|---|
| Technical | `DATA_UNAVAILABLE`; không sinh candidate số |
| Evidence | Dùng đúng 50 neutral, có warning và source |
| Execution | Dùng đúng 50 neutral, có warning và source |

Không được:

- copy Technical sang Evidence hoặc Execution;
- dynamic-renormalize trọng số;
- thay đổi trọng số theo recent trades;
- override trọng số từ caller;
- làm tròn từng contribution.

Module canonical: `core/final_score_v4.py`.

## 5. Gate và hành vi fail-closed

### 5.1 Trạng thái chung

Ba loại gate dùng cùng bốn trạng thái nhưng có payload khác nhau:

| Loại | Field chính |
|---|---|
| Safety check | `status`, `reason_codes`, `observed_value`, `threshold`, `policy_version`, `checked_at`, `source`, `provenance` |
| Macro gate | `assessed_side`, `status`, `decision_cap`, `reason_codes`, `policy_version`, `checked_at`, `provenance` |
| Composition gate | `name`, `status`, `reason_codes`, `observed`, `threshold`, `checked_at`, `source`, `provenance` |

Thứ tự ưu tiên duy nhất:

```text
BLOCK > UNKNOWN > CAUTION > PASS
```

- `BLOCK`: không thể được score/rank vượt qua.
- `UNKNOWN` critical: dữ liệu không đủ tin cậy, candidate là `BLOCKED`.
- `CAUTION`: candidate tối đa là `WATCH_ZONE` trong composition hiện tại.
- `PASS`: chỉ có khi các field chứng minh bắt buộc của đúng loại gate hợp lệ.

Không có đường mặc định biến missing/error/stale thành `PASS`.

### 5.2 MarketSafetyGate

`MarketSafetyGate` là nguồn canonical duy nhất cho năm kiểm tra:

| Check | PASS | CAUTION | BLOCK | UNKNOWN |
|---|---|---|---|---|
| Connectivity | Terminal và broker sẵn sàng | — | Mất kết nối/không đăng nhập | Không đọc được trạng thái |
| `data` (candle freshness) | Candle còn trong SLA | — | Candle quá cũ | Thiếu timestamp hoặc SLA |
| Spread | Có ngưỡng symbol và spread hợp lệ | — | Spread vượt ngưỡng | Thiếu spread/ngưỡng symbol |
| News | Nguồn hợp lệ, không có event gần | Event high-impact `(30, 180]` phút | Event high-impact `[0, 30]` phút | Không lấy/verify được nguồn |
| Volatility | Ratio không vượt upper threshold | Vượt upper threshold | — | Thiếu metric hoặc upper threshold |

Cấu hình mặc định hiện tại:

- News: block 30 phút, caution 180 phút.
- Volatility semantics: ATR(14), H4/D1, reference window 14 ngày.
- Connectivity probe max age: `None`; source vẫn phải có timestamp hợp lệ nhưng chưa bị giới hạn tuổi.
- Spread threshold map: rỗng.
- Candle freshness SLA: `None`.
- Volatility upper ratio: chưa cấu hình.
- Manual order không bypass `UNKNOWN`.

Vì các giá trị chưa cấu hình trả `UNKNOWN`, cấu hình mặc định phù hợp cho
scan/hiển thị/paper. Nó không đảm bảo sinh `READY_NOW` hoặc gửi lệnh. Muốn bật
order workflow ở Bước 12 phải cấu hình đủ dữ liệu safety bắt buộc; missing
provider vẫn luôn fail-closed.

Module canonical: `core/market_safety_gate.py`.

### 5.3 MacroGate

`MacroAssessment` giữ:

```text
raw_buy / raw_sell
confidence
status: aligned | neutral | conflict | unknown
correlation context
event/macro provenance
AI verdict/veto provenance
```

Quy tắc:

- aligned không cộng điểm hoặc promote setup;
- neutral không sửa score;
- conflict chỉ cap/block;
- unknown không được giả thành neutral;
- AI chỉ veto/cap, không boost hoặc numeric adjustment;
- raw/confidence thiếu hoặc lỗi nguồn AI đã nhận diện không được thành `PASS`.

Adapter runtime ở Bước 12 phải chuẩn hóa lỗi từ các provider Macro khác thành dữ liệu
thiếu/`UNKNOWN` trước khi gọi gate; không truyền lỗi provider như một assessment hợp lệ.

Cấu hình mặc định hiện tại để các ngưỡng sau là `None`:

- deadband;
- confidence threshold;
- conflict cap;
- unknown cap;
- AI conviction threshold.

Với cấu hình này MacroGate trả `UNKNOWN` khi chưa đủ policy để kết luận. Đây là
hành vi mặc định có chủ ý, không phải lỗi runtime.

Module canonical: `core/macro_gate.py`.

### 5.4 Gate còn lại

Scenario, account, portfolio, journal và execution là domain riêng. Chúng không
được tính lại Safety/Macro hoặc sửa score. `READY_NOW` luôn phải qua execution
revalidation bằng dữ liệu mới.

## 6. Decision, Candidate và Ranking

### 6.1 Default threshold policy

`make_default_threshold_policy()` trả:

| Field | Giá trị |
|---|---:|
| `technical_floor` | 40 |
| `setup_floor` | 35 |
| `min_score_gap` | 5 |
| `min_risk_reward` | 2.0 |

Đây là cấu hình mặc định versioned, không sao chép threshold V3. Calibration có
thể điều chỉnh sau nhưng không chặn chương trình.

Module canonical: `core/scanner_v4_threshold_policy.py`.

### 6.2 Decision matrix

Router kiểm version/schema trước khi dựng candidate. Payload thiếu/sai/mixed version trả
`route_status=version_mismatch` và `candidate=None`; đây là từ chối input, không phải một
candidate `DATA_UNAVAILABLE`.

Với payload V4 hợp lệ, decision matrix là:

| Điều kiện | Score/Scenario | Entry | Trạng thái tối đa |
|---|---|---|---|
| Technical/snapshot critical data invalid | Không đủ | Bất kỳ | `DATA_UNAVAILABLE` |
| `BLOCK` | Bất kỳ | Bất kỳ | `BLOCKED` |
| Critical `UNKNOWN` | Bất kỳ | Bất kỳ | `BLOCKED` |
| `CAUTION` hoặc non-critical `UNKNOWN` | Bất kỳ | Bất kỳ | `WATCH_ZONE` |
| `PASS` | Dưới floor/gap/R:R | Bất kỳ | `WATCH_ZONE` |
| `PASS` | Đạt policy | Chưa xác nhận | `WAITING_CONFIRMATION` |
| `PASS` | Đạt policy | Đã xác nhận và execution fresh | `READY_NOW` |

Candidate chỉ được ghi bởi `core/scanner_v4_candidate.py::build_candidate()` (và helper
idempotent `build_candidate_with()`). `scanner_v4_strategy_router.py` chỉ validate/
orchestrate; `scanner_v4_execution_readiness.py` chỉ tạo input readiness.

Order payload chỉ là execution intent: luôn yêu cầu revalidation và không tự gửi
lệnh. Router cũng không trực tiếp execute. Ở runtime V4, controller/order service
chỉ được dispatch intent sau khi execution revalidation bằng dữ liệu mới trả PASS.

### 6.3 Ranking

Default ranking policy dùng tầng 1 — trạng thái:

```text
READY_NOW
> WAITING_CONFIRMATION
> WATCH_ZONE
> BLOCKED
> DATA_UNAVAILABLE
```

Tầng 2 — trong cùng trạng thái:

```text
setup_score
> risk_reward_ratio
> proximity
> evidence_score
> execution_quality_score
```

Tie cuối dùng symbol tăng dần để deterministic. Missing value nằm cuối nhóm.
Không trừ news/spread/macro lần nữa và không dùng Macro làm tie-break.

Module canonical: `core/scanner_v4_ranking.py`. Class policy hiện vẫn cho caller truyền
thứ tự khác; Bước 12 phải khóa đúng default trên ở runtime và không nhận ranking order
tùy biến từ config/caller.

## 7. Snapshot, composition và canonical output

### 7.1 Composition

`compose_scanner_v4(snapshot, ...)` là điểm vào duy nhất cho V4 target.

- Live và backtest dùng cùng composition.
- Adapter chỉ khác `capture_source`.
- Snapshot ID không phụ thuộc capture source.
- Snapshot quá 120 giây tuổi hoặc lệch quá 30 giây về tương lai trả fail-closed.
- Safety/Macro không làm đổi Technical/Setup score.
- Macro được đánh giá đúng selected side.

Module canonical: `core/scanner_v4_composition.py`.

### 7.2 Hai lớp output

`compose_scanner_v4()` trả `ScannerV4CompositionResult`, là wrapper đầy đủ cho một lần
chạy:

```text
composition_version, snapshot_id, symbol, captured_at, capture_source
technical + technical_errors                    # BUY/SELL
safety
macro_assessment + macro_gate                   # selected side
scenario                                        # selected side
final_scores                                    # BUY/SELL
composition_gates
decision
canonical
```

Field `canonical` là `CanonicalPairSnapshot`, nguồn dữ liệu chuẩn cho row/router/
candidate:

```text
scoring_version, feature_version, output_schema_version
safety_policy_version, macro_policy_version, ranking_version, snapshot_version
snapshot_id, symbol, captured_at
side_scores.buy/sell:
  technical_signal_score
  technical_breakdown: trend, momentum, location, smc
  evidence_score + evidence_source
  execution_quality_score + execution_quality_source
  setup_score + final_score
market_safety
macro_assessment + macro_gate
decision
```

Row đọc `composition.canonical`. Router/candidate nhận wrapper đã validate: canonical là
nguồn chuẩn cho identity, score và decision; wrapper bổ sung scenario/composition gates.
Không được nhầm wrapper key `safety` với canonical key `market_safety`.

V4 không phát `risk_condition`, `macro_alignment`, `scenario_scores.total`,
`best_score` hoặc các scored field legacy.

### 7.3 Version identity

| Contract | Version |
|---|---|
| Scoring | `scanner-v4` |
| Feature | `scanner-features-v4` |
| Output schema | `scanner-output-v4` |
| Snapshot | `scanner-pair-snapshot-v4` |
| Safety policy | `scanner-safety-policy-v4` |
| Macro policy | `scanner-macro-policy-v4` |
| Ranking | `scanner-ranking-v4` |
| Technical weights | `technical-signal-weights-v4` |
| FinalScore | `scanner-final-score-v4` |
| Threshold policy | `scanner-threshold-policy-v4` |
| Composition | `scanner-composition-v4` |
| Row | `scanner-v4-row-v1` |
| Presentation | `scanner-v4-presentation-v1` |
| Snapshot envelope | `scanner-v4-snapshot-envelope-v1` |
| Replay | `scanner-v4-replay-v1` |
| Journal | `scanner-v4-journal-v1` |
| Observability | `scanner-observability-v4` |
| Session review | `scanner-session-review-v4` |
| Backtest contract | `scanner-backtest-contract-v4` |
| Backtest config schema | `10` |

Canonical model và full composition reader đã kiểm exact identity. Một số adapter row/
compact snapshot hiện mới kiểm version của envelope và chỉ kiểm nested identity khác rỗng.
Bước 12 phải khóa exact toàn bộ version/schema trước khi các reader này nhận runtime input.

## 8. Row, UI, persistence, replay và journal

Các consumer V4 chỉ đọc canonical output:

- Row: `core/scanner_v4_row.py`.
- Presentation: `ui/scanner_v4_presentation.py`.
- Snapshot envelope: `core/scanner_v4_snapshot.py`.
- Replay: `core/scanner_v4_replay.py`.
- Journal: `services/scanner_v4_journal_models.py`,
  `services/scanner_v4_journal_converters.py`.
- Observability: `core/scanner_v4_observability.py`,
  `core/scanner_v4_session_review.py`.

Quy tắc:

- UI hiển thị đúng bốn component technical.
- Safety/Macro hiển thị như gate, không như điểm.
- `UNKNOWN` không render thành `PASS`.
- Blocked setup vẫn giữ score/scenario để giải thích.
- Full snapshot V4 có thể replay nếu đủ canonical data.
- Compact snapshot chỉ dùng hiển thị/audit.
- Artifact V3 luôn audit-only và non-replayable trong V4.
- Journal partition theo scorer/policy; không trộn semantics V3/V4.
- Serialization deterministic. Canonical/full reader là strict; Bước 12 phải hoàn tất
  exact-version/unknown-field validation ở mọi adapter external và compact reader.

## 9. Backtest, config và calibration

### 9.1 Backtest parity

Live và backtest dùng cùng `compose_scanner_v4`. Với cùng immutable input, các
field sau phải giống nhau:

- snapshot ID;
- TechnicalScore và SetupScore;
- selected side;
- gate status/reason;
- candidate status;
- version identity.

Chỉ `capture_source` được khác.

Module: `core/scanner_v4_backtest_contract.py`.

### 9.2 Config và artifact

- Contract config V4 dùng schema `10`, exact version identity và fingerprint.
- Config thiếu/sai/mang V3 fail-closed.
- Filter đọc selected-side `setup_score`, không đọc `final_score` legacy.
- Ở runtime V4 sau cutover, default threshold policy hoặc policy calibrated đều
  hợp lệ nếu version/fingerprint khớp và validation pass. Bước 12 phải bỏ yêu
  cầu calibration artifact bắt buộc khỏi config reader khi default policy được dùng,
  đồng thời bắt buộc đủ identity/fingerprint kể cả khi caller không truyền fingerprint tham chiếu.
- Backtest artifact V3 chỉ giữ để audit.

Module: `core/scanner_v4_config_invalidation.py`,
`core/scanner_v4_candidate_ledger.py`.

### 9.3 Calibration tùy chọn

`core/scanner_v4_calibration.py` và `core/scanner_v4_pit_dataset.py` hỗ trợ
calibration sau này:

- validate dữ liệu point-in-time;
- tách temporal train/OOS một lần theo `pit_boundary`;
- tạo summary/report deterministic;
- tạo report đề xuất provisional: technical/setup có thể lấy mốc quan sát, còn gap `5`
  và R:R `2.0` vẫn là default; volatility/macro chưa được suy ra từ dữ liệu.

Walk-forward và sensitivity grid chưa được triển khai. Đây là cải tiến calibration tùy
chọn về sau, không phải khả năng hiện có hoặc điều kiện cutover.

Không có dataset hoặc sample không đủ phải trả `INSUFFICIENT_SAMPLE` và threshold
`None`; không được tạo số giả. Kết quả đó không chặn trạng thái `DONE` của
Bước 09/11 vì chương trình đã có default threshold policy.

Collector `scripts/scanner_v4_pit_collector.py` là tiện ích tùy chọn, không được
runtime import và không ảnh hưởng cutover.

## 10. Kiểm thử bắt buộc

Các invariant của target code Bước 02–11 phải luôn đúng:

- TechnicalScore chỉ có bốn component và nằm 0–100.
- Thay Risk/Macro/Safety không làm TechnicalScore đổi.
- BUY/SELL gap chỉ phản ánh TechnicalScore.
- Evidence/Execution thiếu dùng 50, không copy Technical.
- FinalScore không mở khóa gate.
- `BLOCK` và critical `UNKNOWN` không bị score/rank vượt qua.
- Missing safety không thành `PASS`.
- News/spread/Macro không bị tính lặp.
- Side, scenario, gate và candidate nhất quán.
- Live/backtest dùng cùng version và composition.
- Canonical/router từ chối V3/mixed/missing version theo contract hiện có.
- Snapshot/replay/journal deterministic và version-safe.

Các invariant cutover bắt buộc ở Bước 12, không tính vào bằng chứng Bước 11:

- mọi runtime/external/compact reader kiểm exact version/schema;
- runtime khóa exact default ranking policy, caller không thể đổi eligibility order;
- execution revalidation lấy dữ liệu mới ngay trước khi dispatch lệnh thật;
- mọi V3/mixed/missing identity bị từ chối trên toàn bộ consumer path.

Test layers:

1. Unit: scorer, FinalScore, từng gate, serializer.
2. Property/invariant: range, rounding, immutability, side consistency.
3. Scenario matrix: score/gate/entry/fallback/status.
4. Integration: composition → row → router → candidate → ranking →
   snapshot/replay → presentation.
5. Regression: toàn bộ `tests/`.

Parity bắt buộc được kiểm trên frozen deterministic fixture/canonical snapshot.
PIT corpus thị trường thật chỉ phục vụ calibration tùy chọn.

Bằng chứng gần nhất được ghi trong working tree:

- Focused Bước 11: `244 passed`.
- Full suite: `3635 passed, 8 skipped, 17 xfailed`, exit code 0.
- Validation artifact: `reports/scanner-v4/validation_b11.json`.

## 11. Trạng thái triển khai

Chỉ dùng hai trạng thái:

- `DONE`: phạm vi code/test/docs của bước đã hoàn tất.
- `TODO`: chưa thực hiện.

| Bước | Nội dung | Trạng thái |
|---:|---|---|
| 00 | Hợp nhất tài liệu và khóa kiến trúc | `DONE` |
| 01 | Inventory code path và data contract V3 | `DONE` |
| 02 | Domain model, version và output schema V4 | `DONE` |
| 03 | Technical scorer bốn thành phần | `DONE` |
| 04 | MarketSafetyGate | `DONE` |
| 05 | MacroAssessment/MacroGate | `DONE` |
| 06 | FinalScore contract | `DONE` |
| 07 | V4 composition | `DONE` |
| 08 | Decision, router, candidate và ranking | `DONE` |
| 09 | Backtest contract, config/version và calibration tooling | `DONE` |
| 10 | Row, UI, snapshot, journal và observability | `DONE` |
| 11 | Invariant, scenario matrix và validation | `DONE` |
| 12 | Atomic runtime cutover và xóa executable V3 | `DONE` |
| 13 | Post-cutover audit và cập nhật runtime docs | `TODO` |

Các module Bước 02–12 hiện là V4 target và chia sẻ đường live với controller/UI sau
Bước 12 cutover. Không dùng trạng thái của từng module để ngụ ý nó đã mở order thật.

## 12. Bước 12 — Atomic runtime cutover

### 12.1 Điều kiện kỹ thuật trước cutover

- Tạo một release duy nhất đã wire V4, map default policy vào composition/router/
  backtest, cập nhật config reader và xóa executable V3 scoring/routing path.
- Khóa default ranking policy; không cho config/caller thay status order hoặc tie-break.
- Harden mọi row/snapshot/config reader để bắt exact identity/fingerprint và từ chối
  unknown/mixed schema trước khi dữ liệu vào decision path.
- Chuẩn hóa lỗi provider Macro thành missing/`UNKNOWN` trước MacroGate.
- Cấu hình tuổi tối đa của connectivity probe hoặc để adapter đánh dấu source stale;
  không dùng timestamp cũ để mở order.
- Full suite xanh trên đúng release sẽ deploy.
- Config/schema/version/fingerprint V4 hợp lệ.
- Backup/export config, snapshot và journal cần thiết.
- V3 config bị từ chối trong V4.
- Row/UI/persistence/journal/observability đọc được V4 output.
- Non-order smoke path hoạt động.
- Execution revalidation không thể bị bypass.
- `ScannerV4OrderPayload` vẫn là intent và router vẫn không execute; controller/
  order service là nơi duy nhất dispatch sau fresh revalidation.
- Có nguyên release hiện tại để rollback.

### 12.2 Trình tự

1. Dừng scan/order mới và chờ tác vụ đang chạy kết thúc.
2. Export state cần giữ.
3. Deploy đúng một lần release V4 đã chuẩn bị ở Mục 12.1, gồm code, schema và config.
4. Chạy migration additive cho persistence.
5. Khởi động scanner.
6. Chạy một scan non-order.
7. Xác nhận version, score, gate, decision, snapshot, journal và metrics.
8. Chỉ bật order workflow khi safety, macro, account, portfolio và journal policy
   bắt buộc đã được cấu hình.
   Nếu vẫn dùng default `None → UNKNOWN`, giữ scan/paper mode.

Không có thời điểm V3 và V4 cùng phục vụ live traffic.

Bước 12 chuyển sang `DONE` ngay sau khi deploy atomic và smoke test đạt. Thời gian
theo dõi sau đó thuộc riêng Bước 13.

### 12.3 Những đường V3 phải xóa

- Composite scorer V3 có Risk/Macro component.
- `risk_score < 9`.
- Numeric Macro/correlation/AI score mutation.
- Fallback `total`, `best_score`, `scenario_scores.total`.
- Dynamic/adaptive FinalScore weights.
- Evidence/Execution fallback copy từ Technical.
- Safety/news/spread logic bị tính lặp.
- Legacy ranking/enrichment.
- Generic rollout controls chỉ phục vụ đường V3 đã xóa.

### 12.4 Smoke test

- Payload đúng V4 schema và đủ version.
- Chỉ bốn technical component.
- Safety `UNKNOWN/BLOCK` không `READY_NOW`.
- Ranking status-first.
- V3 config/artifact không vào V4 decision.
- Snapshot/journal/metrics ghi đúng version.
- Order path luôn revalidate dữ liệu mới.
- Không có exception/error spike ở scanner, UI hoặc persistence.

### 12.5 Rollback

Khi có lỗi schema, version, safety, order revalidation hoặc persistence:

1. dừng order mới;
2. deploy nguyên release trước;
3. restore config/state tương thích đã export;
4. smoke safety và order path;
5. giữ artifact V4 để điều tra, không rewrite thành V3.

## 13. Bước 13 — Post-cutover audit

Sau cutover cần theo dõi:

- distribution Technical/Setup theo side/regime;
- tỷ lệ PASS/CAUTION/BLOCK/UNKNOWN;
- neutral fallback Evidence/Execution;
- candidate status;
- blocked-high-score;
- version/snapshot mismatch;
- provider/pipeline error;
- execution rejection;
- mọi order attempt.

Lấy mẫu xuyên suốt scan → row → persistence → journal → UI để xác nhận snapshot
ID, side, score, gate và version không đổi.

Khi runtime ổn định:

- cập nhật `docs/scanner/scanner-flow.md`;
- cập nhật `docs/scanner/technical-scoring-architecture.md`;
- ghi V3 là historical-only;
- đánh dấu Bước 13 `DONE`.

### 13.1 Cấu hình RuntimeOrderPolicy — GIÁ TRỊ TẠM THỜI (TRIAL, chưa phải final)

Khe cấu hình order duy nhất cho live runtime ([core/scanner_v4_order_policy.py](../core/scanner_v4_order_policy.py))
đã được wire vào release (`run_v4_pair(..., order_policy=...)`). **Nguồn duy nhất của các
giá trị thử là file [config/scanner_v4_order_policy.json](../../config/scanner_v4_order_policy.json)**
— bảng dưới chỉ phản ánh file đó; đổi số thì sửa file, không sửa bảng này. Các giá trị
**tạm thời được owner chấp nhận để chạy thử** vào 2026-08-14 — chúng **KHÔNG phải là
số hiệu chuẩn cuối cùng** và **phải được rà lại trong đợt audit Bước 13** trước khi
coi là chính thức.

**Số bắt buộc để mở** (`certified()`/`order_enabled` = `True`): threshold đủ 4 floor (đã
chốt 40/35/5/2:1) **và** safety đóng đủ 4 (connectivity age, candle SLA, spread map
non-rỗng, volatility calibrated) **và** macro đóng đủ **3 trong 5** (`deadband_points`,
`confidence_threshold`, `conflict_cap` — `unknown_cap` và `ai_conviction_threshold` là
fail-safe có giá trị nhưng **không gating order**) **và** đủ 4 portfolio/journal. Thiếu bất
kỳ số bắt buộc nào trong `RuntimeOrderPolicy.from_dict` → `order_enabled` vẫn `False` →
order workflow vẫn BLOCKED (fail-closed).

**Chưa nối vào live (đúng theo kỷ luật giữ ORDER BLOCKED):** file config mới được
persist + test load; **chưa có loader runtime nào đọc nó** và controller vẫn gọi
`run_v4_pair_from_live(...)` **không truyền `order_policy=`** → release dùng
`DEFAULT_RUNTIME_ORDER_POLICY` (safety/macro mở) → candidate luôn BLOCKED. Muốn áp dụng
các số thử lên live, cần một bước nối riêng: đọc `config/scanner_v4_order_policy.json`,
`RuntimeOrderPolicy.from_dict`, rồi truyền vào `run_v4_pair_from_live(order_policy=…)`.
Bước nối này thuộc Bước 13 và chưa làm.

| Lớp | Khóa | Giá trị tạm thời | Ghi chú thử |
|---|---|---|---|
| threshold | `technical_floor` / `setup_floor` / `min_score_gap` / `min_risk_reward` | 40 / 35 / 5 / `"2/1"` | đã chốt owner-approved từ Bước 07, giữ nguyên |
| safety | `connectivity_max_age_minutes` | 5 | heartbeat MT5 tính bằng giây |
| safety | `max_candle_age_minutes` | 3 | nguồn lệch quá 3′ = dữ liệu cũ |
| safety | `spread_threshold_by_symbol` | `{"XAUUSD": 40, "EURUSD": 25}` | điểm; thêm symbol khác theo points điển hình |
| safety | `volatility_upper_ratio` | 2.0 | ATR14 ≥2× trung bình 14 ngày → block |
| macro | `deadband_points` | 3 | buy/sell raw cách ≤3 pts = không rõ cạnh |
| macro | `confidence_threshold` | 0.6 | dữ liệu macro tin cậy ≥0.6 |
| macro | `conflict_cap` | `"WATCH_ZONE"` | đổi thành `"BLOCK"` nếu muốn nghiêm nhất |
| macro | `unknown_cap` | `"DATA_UNAVAILABLE"` | unknown → fail-closed, không trade |
| macro | `ai_conviction_threshold` | 0.7 | veto AI chỉ có hiệu lực khi conviction ≥0.7 |
| portfolio | `portfolio_position_limit` | 1 | đổi 2 nếu muốn hai lệnh |
| portfolio | `portfolio_exposure_limit` | 0.3 | ≤30% vốn over-exposure |
| journal | `journal_max_consecutive_losses` | 3 | dừng mở lệnh mới sau 3 lệnh thua liên tiếp |
| journal | `journal_drawdown_caution_ratio` | 0.1 | sụt 10% → CAUTION/WATCH |

Trạng thái đúng đắn: các số trên là điểm khởi đầu an toàn cho một tài khoản cá nhân,
**không phải là hiệu chuẩn** dựa trên V3 hoặc data thật. Quyết định áp dụng dứt điểm,
tăng độ mở (bớt conservative) hay siết chặt hơn là của owner sau khi theo dõi Bước 13.
Muốn đổi số thử, sửa `config/scanner_v4_order_policy.json`; test
`tests/test_scanner_v4_order_policy.py::TestTrialConfig` giữ cho file luôn load được
và (khi đủ số) `order_enabled is True`.

> `order_enabled=True` chỉ mở các cổng composition; lệnh thật vẫn phải đi qua chuỗi
> guard của controller (`execute_order_candidate` → `revalidate_execution` →
> `place_market_order`) theo §12.1. Và như ghi trên, các số thử hiện **chưa được nối**
> vào live — bước nối đó cũng thuộc Bước 13, chưa làm.

## 14. File map

| Khu vực | File chính |
|---|---|
| Domain/schema | `core/scanner_v4_models.py` |
| Technical score | `core/technical_signal_scorer.py` |
| Market safety | `core/market_safety_gate.py` |
| Macro | `core/macro_gate.py` |
| FinalScore | `core/final_score_v4.py` |
| Composition | `core/scanner_v4_composition.py` |
| Threshold | `core/scanner_v4_threshold_policy.py` |
| Decision/candidate | `core/scanner_v4_candidate.py`, `core/scanner_v4_strategy_router.py` |
| Order policy (Bước 12/13) | `core/scanner_v4_order_policy.py` + `config/scanner_v4_order_policy.json` (giá trị thử) |
| Ranking | `core/scanner_v4_ranking.py` |
| Backtest/config | `core/scanner_v4_backtest_contract.py`, `core/scanner_v4_config_invalidation.py` |
| Calibration optional | `core/scanner_v4_calibration.py`, `core/scanner_v4_pit_dataset.py` |
| Row/presentation | `core/scanner_v4_row.py`, `ui/scanner_v4_presentation.py` |
| Snapshot/replay | `core/scanner_v4_snapshot.py`, `core/scanner_v4_replay.py` |
| Journal | `services/scanner_v4_journal_models.py`, `services/scanner_v4_journal_converters.py` |
| Observability | `core/scanner_v4_observability.py`, `core/scanner_v4_session_review.py` |

Đây là toàn bộ contract cần thiết để tiếp tục Bước 12.
