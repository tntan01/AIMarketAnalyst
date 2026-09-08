# Ngữ nghĩa Anchor R:R

> **Hợp đồng chốt Phase 6–14.** KHÔNG được đổi anchor, ý nghĩa hoặc consumer mà
> không cập nhật tài liệu này cùng toàn bộ regression test.

## Bảng field

### R:R danh nghĩa (chưa trừ spread)

Các field này biểu thị tỷ lệ reward-to-risk dựa trên khoảng cách giá thô (chưa
khấu trừ chi phí spread). Chúng tồn tại chủ yếu để hiển thị / con người đọc.

| Field | Anchor | Công thức | Consumer |
|---|---|---|---|
| `risk_reward` | **best edge** (`entry_for_rr`, aggressiveness=0.0) | `f"1:{reward_risk(entry_best, sl, tp):.1f}"` | Scanner row field (các parser), tham chiếu danh nghĩa Telegram alert, entry checklist, display fallback |
| `risk_reward_base` | **midpoint** (`entry_for_selection`, aggressiveness=0.5) | `reward_risk(entry_mid, sl, tp)` làm tròn | Tooltip chi tiết, tham chiếu diagnostic |
| `risk_reward_worst` | **far edge** (aggressiveness=1.0) | `reward_risk(entry_far, sl, tp)` làm tròn | Tooltip chi tiết, tham chiếu diagnostic |
| `risk_reward_range` | dict `{best, base, worst}` | Xem ở trên | Order dialog tooltip R:R, scanner detail screen |

**Tương thích ngược:** `risk_reward` phải luôn là chuỗi best-case `"1:X.X"`.
Các consumer parse nó (vd `_parse_rr()`, `parse_risk_reward()`) phải biết đây là
best-case. KHÔNG đổi ý nghĩa.

**Anchor hiển thị chính:** con số R:R chính mà người dùng nhìn thấy là **base**
(midpoint vùng), hiển thị kèm range worst–best nằm bên cạnh; best là phụ.
`ui.scanner_rr_formatters.format_order_rr_text()` và card R:R trong scanner detail
triển khai quy tắc này. `risk_reward` vẫn giữ best-case cho các parser.

### R:R hiệu dụng (đã trừ spread)

Các field này đã điều chỉnh theo spread: `effective_risk = risk + spread_cost`,
`effective_reward = reward - spread_cost`. Dùng cho gate decisions, ranking và
execution guard.

| Field | Anchor | Consumer |
|---|---|---|
| `expected_effective_rr` | **best edge** (giống `risk_reward`) | Hiển thị legacy, fallback cho gate/ranking |
| `expected_effective_rr_base` | **midpoint** (giống `risk_reward_base`) | **Gate** (qua `expected_effective_rr_for_gate`), **ranking** (`_safe_rr`, `calculate_opportunity_score`) |
| `expected_effective_rr_worst` | **far edge** | Tham chiếu diagnostic |
| `risk_reward_effective_range` | dict `{best, base, worst}` | Tham chiếu diagnostic, scanner row field |

**Thứ tự ưu tiên khi vào gate:**
1. `expected_effective_rr_for_gate` (được gán bằng `expected_effective_rr_base` nếu có)
2. `expected_effective_rr` (fallback best-case)

**Thứ tự ưu tiên khi ranking:**
1. `expected_effective_rr_base`
2. `expected_effective_rr`
3. `risk_reward` chuỗi (parse)

### R:R theo giá hiện tại (execution live)

Các field này được tính tại thời điểm thực thi bằng giá MT5 live (hoặc fallback).
Chúng điều khiển execution guard và có thể xuất hiện như diagnostic trong order
dialog, nhưng KHÔNG bao giờ thay thế các field R:R best/base chính trong kết quả
scan, gate, hoặc ranking.

| Field | Anchor | Consumer |
|---|---|---|
| `current_entry_price` | Tick MT5 live (`tick.ask`/`tick.bid`) hoặc fallback `technical.price` | Execution guard, tooltip order dialog |
| `current_effective_rr` | Giá live/fallback | **Auto-trade guard** (skip nếu < `min_rr`), **manual order guard** (block nếu < `min_rr`) |
| `current_rr_source` | `"current_price"` / `"no_current_price"` / `"no_stop_loss"` / `"no_take_profit"` / `"price_behind_sl"` / `"invalid_direction"` | Diagnostic, guard eligibility |
| `current_price_in_entry_zone` | `bool \| None` | Diagnostic, tooltip order dialog |

**Chính sách execution guard:** Skip/block khi CẢ HAI điều kiện:
- `current_rr_source == "current_price"` (đã tính được R:R có nghĩa)
- `current_effective_rr < min_rr`

Khi source là bất kỳ giá trị nào khác, guard KHÔNG kích hoạt (dữ liệu thiếu
không bị coi là block).

## Hợp đồng chất lượng TP1 và vùng entry

`build_trade_plan()` áp dụng một sàn chất lượng trước khi chấp nhận TP1:

1. Thứ tự ứng viên: level bằng nhau → structural target zones từ gần tới xa →
   Fibonacci 0.382 (ngoài regime range) → swing gần nhất.
2. Ứng viên phải hữu hạn, đúng side, và nằm vượt qua far edge của vùng entry.
3. Khoảng clearance theo hướng phải đạt tối thiểu `0.15 × ATR` **và** tối thiểu
   `k × zone_width` (Phase 13B.3), với `zone_width` là bề rộng band entry cấu trúc
   và `k = tp1_clearance_zone_width_mult`. Lấy `max` của hai sàn, nên TP1 luôn nằm
   đủ xa past far edge so với band — một band rộng không thể che đi khoảng TP1
   quá mỏng. `k` là heuristic (xem bảng config), giá trị kinh nghiệm — Backtest
   đã gỡ nên không còn sweep tự động.
4. R:R danh nghĩa tính từ midpoint phải đạt tối thiểu `1.0`.
5. R:R hiệu dụng tính từ midpoint phải đạt tối thiểu `1.3`.

Với structural target zones, TP1 thực thi được chọn theo hướng thận trọng:

- BUY: `zone.low - 0.03 × ATR`.
- SELL: `zone.high + 0.03 × ATR`.
- biên thiếu/không hợp lệ fallback về `zone.level`.

Target được lọc, sắp xếp và khử trùng lặp theo giá thực thi này. Nếu target gần
nhất fail quality validation, một target kế tiếp được thử. TP2 giữ logic
next-target/Fibonacci riêng và yêu cầu khoảng gap tối thiểu `0.15 × ATR` từ TP1.

Phase 16 tách nguồn và geometry thực thi:

1. `source_zone` lưu biên gốc và metadata chất lượng vùng. Đây là dữ liệu
   phân tích/hiển thị và không được phép cấp quyền thực thi.
2. `structural_execution_zone` là một sub-zone gần, nằm hoàn toàn trong biên
   nguồn. Bề rộng target lấy từ `execution_zone_width_atr_by_quality`, chia theo
   chất lượng vùng hiệu dụng: `strong` 0.12 × ATR, `moderate` 0.18 × ATR,
   `weak` 0.25 × ATR. Vùng chất lượng cao hơn nhận sub-zone chặt hơn để TP1 giữ
   clearance hợp lý tới cả hai cạnh entry; vùng chất lượng thấp hơn giữ target
   rộng legacy.

   **Nghịch lý chủ ý (trade-off được chấp nhận):** một vùng bị phạt chất lượng
   (stale, mitigated, over-tested...) rơi xuống tier thấp hơn, nhờ đó nhận band
   entry *rộng hơn* (`weak` 0.25 là bề rộng legacy). Điều này có chủ đích —
   `weak` cố tình giữ hành vi fill legacy thay vì bị siết chặt cùng `strong`/
   `moderate`. KHÔNG "sửa" hướng này: một vùng kém hơn nhưng giữ band rộng hơn
   là theo thiết kế, không phải bug.

   **Giá trị là heuristic (không sweep):** các target 0.12 / 0.18 / 0.25 dựa trên
   kinh nghiệm, chưa được tối ưu tự động (Backtest/sweep đã gỡ). Đây là *bước 2* được chấp nhận của kế hoạch; cần xác
   nhận tác động lên fill-rate trên backtest trước khi coi là đã hiệu chỉnh.
3. BUY giữ cạnh high nguồn và dịch cạnh low vào trong. SELL giữ cạnh low nguồn và
   dịch cạnh high vào trong.
4. Sau khi chọn SL và TP1, `_trim_execution_zone_for_effective_rr()` giao thủ
   vùng cấu trúc với dải thỏa `execution_zone_min_effective_rr`.
5. Vùng cuối cùng được expose dưới dạng cả `entry_zone` và `execution_zone`.
   Toàn bộ anchor R:R và position sizing được tính lại từ vùng cuối này.
6. Nếu TP1 không có, việc trim theo R:R không áp dụng và vùng cấu trúc được giữ
   để theo dõi. Nếu giao R:R-valid rỗng, `entry_zone`/`execution_zone` là `None`
   và `EXECUTION_ZONE_RR_EMPTY` được phát.

Tương thích SMC theo hướng là nghiêm ngặt:

- BUY: `demand_zone`, `bullish_order_block`, `bullish_fvg`.
- SELL: `supply_zone`, `bearish_order_block`, `bearish_fvg`.
- Vùng broken hoặc khác family không được tham gia tuyển chọn preferred hoặc
  fallback.
- Legacy tuyển chọn payload có `source="smc_selected"` và không có type vẫn đọc
  được để tương thích ngược; zone production mới sinh ra luôn mang type chuẩn.

Định lượng giá có thể khiến bề rộng ATR đo được lệch nhẹ so với target. Vùng
làm tròn cuối phải nằm trong source zone và bảo toàn tính đối xứng BUY/SELL.

### Diagnostic entry/TP1

| Field | Ý nghĩa |
|---|---|
| `entry_zone_width` / `entry_zone_width_atr` | Bề rộng vùng entry thực tế, đơn vị giá/ATR |
| `entry_zone_source` | Nguồn của vùng entry được chọn |
| `source_zone` | biên vùng gốc, raw/effective score và metadata tuyển chọn; chỉ để tham chiếu |
| `structural_execution_zone` | Sub-zone thực thi gần, trước khi trim theo R:R |
| `execution_zone` | Alias của `entry_zone` cuối cùng đã pass R:R |
| `execution_zone_quality` / `execution_zone_width_atr_target` | Tier bề rộng và target ATR đã cấu hình |
| `rr_trimmed` / `rr_trim_diagnostics` | Trạng thái trim, vùng cấu trúc, biên R:R, vùng cuối và R:R worst pre/post |
| `tp1_source` | `equal_level`, `target_zone`, `fib_extension`, `swing`, hoặc `none` |
| `tp1_clearance_from_far_edge` / `tp1_clearance_atr` | Khoảng cách theo hướng từ far edge entry tới TP1 |
| `tp1_effective_rr_base` | Alias của `expected_effective_rr_base` cho TP1 đã chọn |
| `tp1_selection_diagnostics` | Số ứng viên, số bị loại, nguồn chọn và thứ hạng target (1-based) |

Phân rã score/source và diagnostic tuyển chọn TP1 chỉ mang tính quan sát.
`structural_execution_zone`, `entry_zone`/`execution_zone` cuối và
`rr_trim_diagnostics` là hợp đồng lập kế hoạch production nên ảnh hưởng tới việc
có tồn tại plan thực thi hay không.

### Hợp đồng consumer vùng thực thi

| Consumer | Trường vùng | Quy tắc cùng scenario |
|---|---|---|
| Gate context | `entry_zone` cuối | Phải khớp `best_side`; không bao giờ mượn scenario ngược lại |
| Scanner row | `entry_zone` cuối | Sao chép từ scenario best-side nghiêm ngặt |
| Auto eligibility | `entry_zone` cuối | Vùng thiếu/không hợp lệ loại candidate |
| Auto live guard | `entry_zone` cuối | Ask/bid live phải nằm trong vùng |
| Manual candidate/guard | `entry_zone` cuối | Dùng cùng scenario với SL/TP/RR |
| Order dialog | `entry_zone` cuối | `source_zone` chỉ xuất hiện trong tooltip/văn bản tham chiếu |
| Scanner Detail | `entry_zone` cuối | Hiển thị width source/execution và lý do trim/loại |
| Chart payload | `entry_zone` cuối | Đánh dấu `execution_eligible=true`; source là `false` |

Không consumer nào được fallback từ vùng thực thi cuối bị thiếu về `source_zone`,
`watch_zone`, hoặc scenario side ngược.

## Ma trận hợp đồng consumer

| Consumer | Field R:R dùng | Anchor | Phase |
|---|---|---|---|
| **Gate** (`_gate_expected_effective_rr`) | `expected_effective_rr_for_gate` → `expected_effective_rr_base` → `expected_effective_rr` | base → fallback best | Phase 3 |
| **Ranking RR bonus** (`calculate_opportunity_score`) | `expected_effective_rr_base` → `expected_effective_rr` → `risk_reward` | base → fallback best | Phase 4A |
| **Sort `_safe_rr`** | `expected_effective_rr_base` → `expected_effective_rr` → `risk_reward` | base → fallback best | Phase 4A |
| **Cột Scanner table** | `expected_effective_rr` | best hiển thị; ngưỡng màu cũng dùng best | Phase 8 |
| **Cột R:R trong order dialog** | `risk_reward_range`/`risk_reward_base` (base) chính + range worst–best kèm bên; tooltip base/best/current; `risk_reward` (chuỗi best) chỉ làm fallback | base hiển thị + diagnostic | Phase 5C, 8 |
| **Auto-trade guard** | `current_effective_rr` tại giá live/fallback | live current | Phase 5B |
| **Manual order guard** | `current_effective_rr` tại giá live/`order_entry_fallback` | live current | Phase 5B |
| **Telegram alert** | `risk_reward` (chuỗi best) làm tham chiếu danh nghĩa; hiển thị chính dùng `expected_effective_rr_base` (base) với fallback `expected_effective_rr` (best) | base chính + tham chiếu best | Phase 7 |
| **Entry checklist** | `risk_reward` (chuỗi best) qua `_parse_rr()` cho pass/fail; ghi chú hiển thị base/effective range làm tham chiếu | best (không đổi) | Phase 11 |
| **Auto-trade eligibility** | `expected_effective_rr` (best hiệu dụng) cho backtest gate pre-filter | best hiệu dụng | Phase 11 |
| **Diagnostics** (`result["diagnostics"]`) | Toàn bộ field R:R | best + base + current | Phase 5D |
| **Manual `execution_guard`** | `current_effective_rr` + `price_source` | live / order_entry_fallback / none | Phase 5D.1 |
| **Chất lượng TP1** | `tp1_effective_rr_base` từ midpoint | base floor hiệu dụng | Phase 13B |

## Sơ đồ quan hệ field

```
build_trade_plan()
  ├─ entry_for_rr (best edge, agg=0.0) ──► risk_reward, expected_effective_rr,
  │                                         entry_price (hiển thị)
  ├─ entry_for_selection (midpoint, agg=0.5) ──► risk_reward_base,
  │     expected_effective_rr_base, TP validation, anchor hiển thị chính
  ├─ entry_worst (far edge, agg=1.0) ──► risk_reward_worst,
  │     expected_effective_rr_worst, position_sizing (lot thận trọng)
  └─ TP1 candidate validation ──► tp1_source, tp1_clearance_atr,
        tp1_effective_rr_base, tp1_selection_diagnostics

scanner_row_from_analysis()
  ├─ Sao chép toàn bộ field R:R từ best_plan
  └─ enrich_scanner_row_with_ranking()
       ├─ Kéo expected_effective_rr_base từ analysis_result.scenarios
       ├─ calculate_opportunity_score() dùng base RR cho bonus
       └─ scanner_group được gán

check_trade_gates()
  └─ _gate_expected_effective_rr()
       ├─ expected_effective_rr_for_gate (ưu tiên base)
       └─ Fallback về expected_effective_rr (best)

_get_alert_order_candidates() / _build_order_rows()
  └─ calculate_current_effective_rr(current_price=live/fallback)
       ├─ current_effective_rr
       ├─ current_rr_source
       └─ current_price_in_entry_zone

_execute_auto_trades()
  ├─ Kiểm tra vùng entry với giá live
  ├─ Guard R:R hiện tại: skip nếu cur_rr < min_rr
  └─ Payload diagnostic nối vào result["diagnostics"]

Manual order dialog
  ├─ Kiểm tra vùng entry với giá live
  ├─ Guard R:R hiện tại: cảnh báo block nếu cur_rr < min_rr
  └─ execution_guard diagnostic trên order_info
```

## Quy tắc tương thích ngược

1. Chuỗi `risk_reward` PHẢI luôn là `"1:X.X"` từ best edge. Không bao giờ đổi.
2. `expected_effective_rr` PHẢI luôn là best-case effective RR. Không bao giờ đổi.
3. Các key `{best, base, worst}` của `risk_reward_range` KHÔNG được sắp lại thứ
   tự hoặc đổi tên.
4. Mọi field mới phải ADDITIVE — không được xóa hoặc đổi tên key sẵn có.
5. Ngưỡng (`_RR_STRONG=2.0`, `_RR_WEAK=1.3`, `min_rr=1.3`) chỉ được đổi trong
   một phase hiệu chỉnh riêng với lý do dựa trên dữ liệu.
6. `position_sizing` neo vào **far edge** (`entry_worst`, aggressiveness=1.0).
   Điều này giữ rủi ro tiền thật ở mức bằng hoặc dưới phần trăm cấu hình cho mọi
   fill trong vùng. Không neo lại vào best edge.
7. Số R:R chính mà người dùng nhìn thấy là **base**, kèm range worst–best nằm
   bên; best là phụ. Không khôi phục best-case làm số hiển thị chính.

## Tham số chất lượng từ config

| Parameter | Mặc định |
|---|---:|
| `tp1_min_clearance_atr` | 0.15 |
| `tp1_min_effective_rr_base` | 1.3 |
| `tp1_clearance_zone_width_mult` | 1.0 (heuristic; Backtest/sweep đã gỡ, không tự tinh chỉnh) |
| `tp_target_buffer_atr` | 0.03 |
| `entry_zone_buffer_atr` | 0.05 (tham số legacy; đã bị logic sub-zone Phase 16 thay thế) |
| `entry_zone_max_width_atr` | 0.50 (tham số legacy; đã bị logic sub-zone Phase 16 thay thế) |
| `entry_zone_half_width_atr` | 0.25 |
| `execution_zone_width_atr_by_quality.strong` | 0.12 |
| `execution_zone_width_atr_by_quality.moderate` | 0.18 |
| `execution_zone_width_atr_by_quality.weak` | 0.25 |
| `execution_zone_quality_thresholds.strong` | 70 |
| `execution_zone_quality_thresholds.moderate` | 50 |
| `execution_zone_min_effective_rr` | 1.3 |
| `execution_zone_rr_tolerance` | 0.0001 |

## Công cụ phân tích tác động

- `scripts/compare_rr_anchor_impact.py` so sánh tác động R:R hiệu dụng best/base.
- `scripts/compare_entry_tp_quality.py` báo cáo bề rộng entry, clearance TP1,
  lý do loại, thứ hạng target được chọn và so sánh baseline tùy chọn.
- Operational snapshot có thể chứa dữ liệu broker/market và chỉ tồn tại cục bộ;
  `data/operational_baseline.json` được gitignore có chủ đích.

## Validate và rollback Phase 16

- So sánh baseline phải tách scenario source/watch khỏi plan thực thi. Một row
  chứa biên source không tự động nghĩa là thực thi được.
- Chỉ số release bắt buộc gồm số directional mismatch, phân bố score
  source/effective, bề rộng structural/final theo ATR, tỉ lệ trim/reject, plan
  không có TP1, và R:R hiệu dụng base/worst.
- Validate production Phase 16G.1 phát hiện và sửa một đường fallback có thể chọn
  bearish order block cho BUY. Regression coverage giờ khóa chính xác tính hợp
  lệ zone-family cho cả đường preferred/fallback BUY và SELL.
- Operational snapshot là dữ liệu cục bộ, đã ẩn và gitignore. Chúng không phải
  replay xác định vì input thị trường có thể thay đổi giữa các lần scan.
- Rollback chính xác là code-scoped: khôi phục triển khai chọn zone và lập kế
  hoạch pre-Phase-16 cùng với consumer của nó. Chỉ đổi config width/RR có thể làm
  dịu hành vi nhưng không tái tạo được ngữ nghĩa tuyển chọn cũ.
- Không bao giờ dùng `git reset --hard` trên worktree bẩn. Tạo patch scoped hoặc
  commit checkpoint trước khi rollout sau khi các thay đổi repo được phê duyệt.
