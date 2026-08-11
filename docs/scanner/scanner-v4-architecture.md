# Scanner V4 — Kiến trúc scoring và gate đã chốt

> - **Trạng thái:** APPROVED DESIGN — NON-RUNTIME
> - **Ngày chốt:** 11/08/2026
> - **Runtime hiện tại:** `scanner-v3` / `scanner-features-v3`
> - **Target:** `scanner-v4` / `scanner-features-v4`
> - **Migration:** direct cutover, không dual scoring, không shadow so với v3

Tài liệu này là nguồn chuẩn cho kiến trúc Scanner V4 và kế hoạch phân tích từng
bước trước khi sửa code. Cho đến khi cutover hoàn tất, mô tả runtime thực tế vẫn
nằm tại [`scanner-flow.md`](scanner-flow.md) và
[`technical-scoring-architecture.md`](technical-scoring-architecture.md).

Tài liệu này thay thế hoàn toàn proposal năm thành phần trước đây. Các bảng chứa
Risk, phép chuẩn hóa từ trọng số v3 và kế hoạch shadow cũ không còn hiệu lực.

## 1. Quyết định đã khóa

1. `TechnicalSignalScore` chỉ có bốn thành phần: **Trend, Momentum, Location,
   SMC**.
2. **Risk không đóng góp điểm.** News, spread, dữ liệu, connectivity và
   volatility đi qua `MarketSafetyGate`.
3. **Macro không đóng góp điểm.** Macro raw/confidence/status/correlation/AI
   được giữ trong `MacroAssessment` và chỉ tác động qua policy/gate.
4. Macro thuận không được cộng điểm, promote setup yếu hoặc làm tie-break số
   trong ranking.
5. Gate `BLOCK` không thể bị score cao bù lại. Gate `CAUTION` cap quyết định ở
   `WAIT`/`WATCH`.
6. `FinalScore` tiếp tục blend Technical/Evidence/Execution, nhưng ba input phải
   độc lập; không fallback Evidence hoặc Execution về Technical.
7. Migration là **direct cutover** sang v4. Không chạy v3/v4 song song, không
   dùng sample disagreement với v3 làm tiêu chí đúng/sai.
8. Config, snapshot hoặc backtest artifact mang scorer/feature v3 chỉ được đọc
   để audit/replay; không được dùng cho quyết định live v4.
9. Không giữ hai đường runtime sau cutover. Rollback dùng release artifact/Git,
   không dùng router dual-score trong production.

Trong quyết định này, “Risk” là component legacy `risk_condition` đang trộn ATR,
news và spread vào score. Quản trị rủi ro giao dịch như SL/TP, position sizing,
account loss, portfolio exposure và execution guard vẫn là các domain bắt buộc,
không bị loại bỏ.

## 2. Lý do chốt và trade-off

| Mặt được | Mặt mất/chi phí |
|---|---|
| TechnicalScore trả lời đúng một câu hỏi: setup kỹ thuật mạnh tới đâu. | Đây là breaking change xuyên scorer, pipeline, decision, ranking, backtest, UI và persistence. |
| Điều kiện nguy hiểm không thể được điểm kỹ thuật cao bù lại. | Threshold V3 không thể đổi cơ học; phải calibration lại bằng chính V4. |
| News, spread và macro không còn bị tính lặp ở score, gate và ranking. | `UNKNOWN` fail-closed có thể làm giảm số candidate khi nguồn dữ liệu chưa ổn định. |
| BUY/SELL gap phản ánh directional technical, không chứa Risk common-mode. | Ranking và tỷ lệ READY/WATCH/BLOCKED sẽ đổi, không dùng V3 làm chuẩn đúng/sai. |
| UI giải thích được “setup tốt nhưng đang bị chặn”. | Macro thuận không còn là soft boost/tie-break; nếu cần ưu tiên phải thiết kế policy riêng, không lén đưa lại vào số. |
| Live và backtest có thể kiểm cùng invariant score/gate. | Direct cutover đòi hỏi schema, consumer, test và rollback artifact sẵn sàng trong cùng release. |

Độ phức tạp được đánh giá **cao và cross-cutting**. Direct cutover loại bỏ chi
phí xây/duy trì hai scorer và logic disagreement, nhưng không làm nhỏ phạm vi
implementation. Impact map và kế hoạch 13 bước phía dưới là ranh giới công việc
bắt buộc trước khi cutover.

### 2.1 Bằng chứng V3 làm cơ sở tách Risk

Code hiện hành chưa bị sửa bởi quyết định tài liệu này:

- `core/signal_engine.py::calc_risk_condition()` tạo raw 0–15 từ ATR tối đa 6,
  không có news trong 3 giờ cộng 6 và spread đúng `normal` cộng 3;
- `score_scenario()` scale raw Risk theo regime rồi `int()` contribution trước
  khi cộng vào composite score;
- `core/analysis_pipeline.py` truyền cùng một Risk raw cho BUY và SELL, nên Risk
  là common-mode và không tự tạo directional gap;
- news/spread đồng thời còn được xử lý tại trade permission/gate và ranking, tạo
  nhiều owner cho cùng một policy;
- một số fallback V3 mang tính optimistic: thiếu news có thể thành `False`, thiếu
  spread có thể thành `normal`, thiếu ATR average có thể dùng chính ATR hiện tại.

Đây là bằng chứng về boundary hiện hành, không phải policy gate V4. Bước 01 phải
chốt lại file/line/caller/consumer; Bước 04 phải thiết kế fail-closed semantics
cho từng safety input trước khi sửa code.

## 3. Ranh giới hệ thống

```text
Một immutable pair snapshot
  ├─ Technical Context + SMC
  │    ├─ TechnicalSignalScore BUY
  │    └─ TechnicalSignalScore SELL
  ├─ MarketSafetyGate
  │    ├─ Data/Connectivity
  │    ├─ Spread
  │    ├─ News/Event
  │    └─ Volatility
  ├─ MacroAssessment → MacroGate
  ├─ EvidenceScore theo side
  ├─ ExecutionQualityScore theo side
  └─ Scenario/Account/Portfolio/Execution gates
       → FinalDecision
```

Ba câu hỏi phải tách biệt:

- **TechnicalScore:** setup kỹ thuật mạnh đến đâu?
- **Gate:** setup có đủ điều kiện để tiếp tục không?
- **Decision:** với score, scenario và toàn bộ gate, hành động tối đa là gì?

## 4. TechnicalSignalScore

### 4.1 Thành phần

| Component | Raw range hiện có | Vai trò |
|---|---:|---|
| Trend | 0–25 | Hướng và cấu trúc xu hướng |
| Momentum | 0–20 | Xác nhận động lượng |
| Location | 0–25 | Chất lượng vị trí vào lệnh |
| SMC | 0–15 | Cấu trúc/vùng SMC canonical |

Risk, Macro, correlation adjustment, AI verdict và CHOCH cap không được sửa
`TechnicalSignalScore`.

### 4.2 Trọng số theo regime

| Regime | Trend | Momentum | Location | SMC | Tổng |
|---|---:|---:|---:|---:|---:|
| `trending_up` / `trending_down` | 40 | 20 | 20 | 20 | 100 |
| `ranging` | 10 | 10 | 40 | 40 | 100 |
| `volatile` | 20 | 10 | 40 | 30 | 100 |
| `unknown` | 25 | 25 | 25 | 25 | 100 |

Đây là **policy thiết kế dễ giải thích**, không phải phép chuẩn hóa cơ học từ
trọng số v3 và chưa phải bằng chứng về edge:

- Trending ưu tiên hướng chính; ba lớp xác nhận còn lại bằng nhau.
- Ranging ưu tiên biên/vị trí và cấu trúc SMC.
- Volatile ưu tiên location và SMC; momentum thấp nhất vì dễ nhiễu.
- Unknown không áp đặt ưu thế khi regime chưa xác định.

### 4.3 Công thức và rounding

```text
contribution_i = clamp(raw_i, 0, raw_max_i) / raw_max_i × regime_weight_i
technical_signal_score = ROUND_HALF_UP(clamp(sum(contribution_i), 0, 100))
```

Yêu cầu:

- tính contribution ở precision đầy đủ;
- không `int()` từng component;
- chỉ làm tròn `ROUND_HALF_UP` một lần sau khi cộng;
- lưu raw và scaled breakdown theo đúng side;
- BUY/SELL gap chỉ được tính từ TechnicalSignalScore BUY/SELL.

## 5. FinalScore

```text
setup_score = technical_signal_score × 0.65
            + evidence_score × 0.20
            + execution_quality_score × 0.15

final_score = setup_score  # compatibility alias
```

Matrix fallback đã khóa:

| Input | Khi thiếu/invalid | Hệ quả |
|---|---|---|
| Technical | Không có fallback số | `DATA_UNAVAILABLE`, không tạo lệnh |
| Evidence | 50 neutral + warning/source | Giữ component 20% |
| Execution quality | 50 neutral + warning/source | Giữ component 15% |

Không copy Technical vào Evidence/Execution và không dynamic-renormalize trọng
số khi thiếu input. Tính ba contribution ở precision đầy đủ, clamp 0–100 và làm
tròn `ROUND_HALF_UP` đúng một lần.

`FinalScore` không phải gate và không có quyền mở lệnh.

## 6. MarketSafetyGate

Mỗi sub-gate trả:

```text
status: PASS | CAUTION | BLOCK | UNKNOWN
reason_codes: [...]
observed_value
threshold/policy_version
checked_at
source/provenance
```

Aggregation:

```text
BLOCK > CAUTION > PASS
UNKNOWN ở dữ liệu safety bắt buộc → không auto-entry
```

Baseline policy:

| Gate | Điều kiện | Kết quả |
|---|---|---|
| Connectivity | MT5/broker không sẵn sàng | `BLOCK` |
| Data | Candle/critical data thiếu hoặc stale | `BLOCK`/`UNKNOWN` |
| Spread | Normal | `PASS` |
| Spread | Abnormal | `BLOCK` |
| Spread | Unknown | `UNKNOWN`, chặn auto-entry |
| News | High-impact trong 0–30 phút | `BLOCK` |
| News | High-impact trong 30 phút–3 giờ | `CAUTION` |
| News | Không có event gần và nguồn hợp lệ | `PASS` |
| News | Không lấy được trạng thái | `UNKNOWN`, chặn auto-entry |
| Volatility | Dữ liệu hợp lệ, không extreme | `PASS` |
| Volatility | Extreme theo policy đã calibration | `CAUTION` |
| Volatility | ATR/metric thiếu hoặc invalid | `UNKNOWN` |

ATR vẫn phục vụ regime, zone distance, SL/TP và execution sizing. Nó không tạo
điểm thưởng. Metric/band volatility phải được phân tích ở Bước 04; không được
đưa tỷ lệ H4-vs-D1 hiện hành thành gate production mà chưa xác nhận semantics.

Khi MarketSafetyGate được đưa vào runtime, phải bỏ `risk_score < 9`, bỏ Risk
component và bỏ penalty news/spread lặp trong ranking. Điều kiện bình thường là
`PASS`, không phải điểm cộng.

## 7. MacroAssessment và MacroGate

MacroAssessment giữ dữ liệu, không giữ contribution score:

```text
raw_buy / raw_sell
confidence
status: aligned | neutral | conflict | unknown
correlation context
event/macro provenance
AI verdict/veto provenance
```

Invariant:

- `aligned`: không cộng score, không promote, không tie-break số;
- `neutral`: không sửa score;
- `conflict`: chỉ cap/block theo policy có version;
- `unknown`: không được giả thành neutral; policy quyết định cap hoặc chặn
  auto-entry;
- AI adjustment số bị loại; chỉ giữ veto/cap có reason code;
- CHOCH không cap score; giữ dưới dạng structure/safety gate.

Threshold confidence/deadband và mapping conflict → `WATCH` hay `BLOCK` sẽ được
khóa tại Bước 05. Trước bước đó không tài liệu nào được tuyên bố threshold cụ
thể là runtime contract.

## 8. Luồng một pair

1. Thu thập một snapshot có timestamp/provenance chung.
2. Validate dữ liệu technical bắt buộc.
3. Dựng Technical Context, SMC và market regime.
4. Dựng `MarketSafetyContext` và chạy các safety sub-gate.
5. Tính TechnicalSignalScore độc lập cho BUY và SELL.
6. Chọn best side và score gap chỉ từ TechnicalSignalScore.
7. Dựng scenario/entry/SL/TP/R:R cho side đủ floor.
8. Tính EvidenceScore và ExecutionQualityScore đúng side.
9. Tính Setup/FinalScore; không đưa gate hoặc Macro vào số.
10. Chạy zone, M15, R:R, account, portfolio, journal và MacroGate.
11. Decision Engine áp score thresholds và cap mạnh nhất từ gate.
12. Ranking theo eligibility trước, score sau.
13. Candidate `READY` phải revalidate snapshot thực thi trước khi đặt lệnh.

Gate `BLOCK` không cần ngăn hệ thống dựng/hiển thị scenario nếu dữ liệu kỹ thuật
vẫn đủ; UI phải thể hiện “setup tốt nhưng hiện bị chặn” thay vì giấu score.

## 9. Decision matrix

| Gate tổng hợp | Technical/Setup | Entry | Kết quả tối đa |
|---|---|---|---|
| `BLOCK`/critical `UNKNOWN` | Bất kỳ | Bất kỳ | `BLOCKED`/`DATA_UNAVAILABLE` |
| `CAUTION` | Bất kỳ | Bất kỳ | `WAITING_CONFIRMATION` hoặc `WATCH_ZONE` |
| `PASS` | Dưới floor | Bất kỳ | Không candidate hoặc `WATCH_ZONE` |
| `PASS` | Đạt floor | Chưa xác nhận | `WAITING_CONFIRMATION` |
| `PASS` | Đạt floor | Đã xác nhận | Có thể `READY_NOW` |

`READY_NOW` vẫn phải qua execution revalidation, account và portfolio guard.

## 10. Ranking

Ranking v4 thực hiện hai tầng:

1. eligibility/status: `READY_NOW` > `WAITING_CONFIRMATION` > `WATCH_ZONE` >
   `BLOCKED`/`DATA_UNAVAILABLE`;
2. trong cùng nhóm: SetupScore, effective R:R, proximity, evidence và execution
   readiness theo contract ranking v4.

Không trừ news/spread/macro lần nữa. Macro aligned không dùng làm tie-break.

## 11. Output canonical

```text
scoring_version: scanner-v4
feature_version: scanner-features-v4

side_scores:
  buy/sell:
    technical_signal_score
    technical_breakdown:
      trend
      momentum
      location
      smc
    evidence_score
    evidence_source
    execution_quality_score
    execution_quality_source
    setup_score
    final_score  # compatibility alias của setup_score

market_safety:
  status
  checks
  reason_codes

macro_assessment:
  raw_buy/raw_sell
  confidence
  status
  provenance

macro_gate:
  status: PASS | CAUTION | BLOCK | UNKNOWN
  decision_cap
  reason_codes
  policy_version

decision:
  selected_side
  score_gap
  candidate_status
  decision_cap
  gate/reason/block_codes
```

Không phát hành `risk_condition` hoặc `macro_alignment` như scored component ở
payload v4. Snapshot v3 chỉ đọc dưới chế độ historical/replay.

## 12. Direct cutover

Không có `legacy/new score`, dual write, shadow report hoặc tiêu chí disagreement
cho migration v4. Trình tự release:

1. hoàn thành contract, code, consumer và test trên một branch/release;
2. bump scorer/feature/config/snapshot version;
3. làm config v3 fail-closed cho live và giữ read-only replay nếu cần;
4. chạy test invariant, scenario matrix và backtest v4 độc lập;
5. deploy v4 làm đường duy nhất;
6. xóa executable v3 scoring/routing path trong cùng migration;
7. rollback bằng release artifact nếu có lỗi kỹ thuật nghiêm trọng.

Generic rollout/shadow code đang tồn tại ở scanner-v3 không phải bằng chứng cho
độ đúng của v4 và không phải điều kiện cutover. Việc loại bỏ control/metric V1/V2
cũ nằm trong Bước 12; không được dùng nó để tạo dual-scoring v4.

## 13. Verification không dựa vào legacy

Các invariant bắt buộc:

- thay Macro/Risk không làm TechnicalSignalScore đổi;
- TechnicalScore chỉ có đúng bốn contribution và tổng nằm 0–100;
- BUY/SELL gap không chứa common-mode Risk;
- `BLOCK` không thể bị score/final/rank vượt qua;
- missing safety data không được mặc định pass;
- news/spread chỉ có một owner policy, không bị trừ lặp;
- Evidence/Execution thiếu dùng 50 neutral, không copy Technical;
- FinalScore không mở khóa gate;
- backtest và live dùng cùng scorer/feature/gate version;
- execution revalidation luôn dùng dữ liệu mới.

Validation outcome của v4 dùng backtest/OOS/walk-forward hoặc forward evidence
của chính v4 khi có; không cần so kết quả với scorer v3 chưa được kiểm chứng.

## 14. Kế hoạch phân tích và triển khai từng bước

| Bước | Nội dung | Trạng thái |
|---:|---|---|
| 00 | Rà soát/hợp nhất tài liệu và khóa architecture | `COMPLETED` |
| 01 | Inventory code path, data contract và owner hiện hành | `PENDING` |
| 02 | Domain model, version và output schema v4 | `PENDING` |
| 03 | Technical scorer bốn thành phần | `PENDING` |
| 04 | MarketSafetyGate và volatility semantics | `PENDING` |
| 05 | MacroAssessment/MacroGate policy | `PENDING` |
| 06 | FinalScore fallback và rounding contract | `PENDING` |
| 07 | Analysis pipeline/direct composition | `PENDING` |
| 08 | Decision, Strategy Router, Candidate và Ranking | `PENDING` |
| 09 | Backtest, threshold, config và version invalidation | `PENDING` |
| 10 | UI, API, snapshot, journal và observability | `PENDING` |
| 11 | Test invariant, scenario matrix và v4 validation | `PENDING` |
| 12 | Atomic cutover, xóa v3/dual comparison path | `PENDING` |
| 13 | Post-cutover audit và cập nhật runtime docs | `PENDING` |

### Quy tắc cập nhật từng bước

Trước khi sửa code của một bước, bổ sung ngay trong tài liệu này:

1. bằng chứng code hiện hành (`file:line`, caller/consumer);
2. contract đầu vào/đầu ra đã chốt;
3. danh sách file dự kiến sửa/xóa;
4. incompatibility và dữ liệu cần migrate;
5. test/invariant/acceptance criteria;
6. quyết định còn mở và owner;
7. trạng thái `PENDING → ANALYZED → IMPLEMENTED → VERIFIED`.

Không chuyển bước sang `IMPLEMENTED` chỉ vì tài liệu đã viết xong. Không chuyển
sang `VERIFIED` nếu acceptance criteria chưa có bằng chứng.

## 15. Impact map dự kiến

| Khu vực | Tác động chính |
|---|---|
| `core/signal_engine.py` | Scorer bốn component; bỏ Risk/Macro/CHOCH score mutation |
| `core/analysis_pipeline.py` | Tách score, safety, macro và fallback |
| `core/risk_engine.py` | Bỏ `risk_score < 9`; giữ trade-plan risk riêng |
| `core/trade_gate_engine.py` | Canonical safety/macro/structure gates |
| `core/final_score_engine.py` | Một fallback matrix và round-once |
| Decision/Strategy/Candidate | Đọc v4 score + gate contract |
| Ranking | Eligibility first; bỏ penalty trùng |
| Backtest/config | V4 parity, threshold mới, v3 fail-closed |
| UI/API/snapshot | Breakdown 4 component + gate cards |
| Tests/fixtures | Xóa fixture 6 component; khóa invariant v4 |

## 16. Điều chưa được phép tự suy diễn

Các mục sau phải được phân tích trong đúng bước, không ngăn việc khóa kiến trúc:

- threshold Technical/Setup mới;
- volatility metric và band production;
- macro deadband/confidence/cap cụ thể;
- threshold score gap v4;
- exact ranking weights trong cùng eligibility group;
- thời hạn đọc compatibility snapshot v3;
- policy cho manual order khi safety `UNKNOWN`.

Mọi quyết định trên phải được ghi vào tài liệu này trước khi implementation.
