# Scanner Flow — Luồng chạy chi tiết của hệ thống quét thị trường

## Tổng quan kiến trúc

```
ScannerScreen (UI)
  → build ScannerRequest (thresholds, symbol_auto_trade)
  → ScannerWorker (thread)
    → ScannerController.run()
      → _analyze_one_symbol() × N symbols (ThreadPoolExecutor)
        → analyze_symbol() → AnalysisPipeline.execute()  [9 bước]
        → scanner_row_from_analysis()
      → sort_scanner_rows()
      → _apply_scanner_filters()  [2 nhánh: backtest=true / false]
      → build_scanner_output()
  → ScannerScreen._scan_finished()
    → ScannerTableModel.set_rows()
    → hiển thị bảng kết quả
```

---

## Bước 1: ScannerScreen — Build ScannerRequest

**File:** `ui/screens/scanner_screen.py` — hàm `_start_scan()`

### Input
- Danh sách symbols đã chọn từ giao diện
- `Settings` từ `SettingsService` (chứa `TradingSettings.symbol_settings`)

### Xử lý

#### 1a. Build `thresholds` (ngưỡng quyết định cho Decision Engine)

Với mỗi symbol, đọc `SymbolScanSettings` từ `settings.trading.symbol_settings`:

**Nhánh 1 — `backtest = true`:**
```
thresholds = {
    "ready": min_score (nếu > 0) hoặc decision_ready,
    "watch": 999,    // vô hiệu hóa phân loại WATCH
    "wait": 999,     // vô hiệu hóa phân loại WAIT
    "min_score_gap": 10,
    "min_rr": min_expected_rr hoặc 0,
}
```
→ Decision Engine chỉ phân được 2 trạng thái: READY_TO_TRADE hoặc STAND_ASIDE.
  Không có trạng thái trung gian WATCH_ONLY / WAITING_CONFIRMATION.

**Nhánh 2 — `backtest = false` (có config):**
```
thresholds = {
    "ready": decision_ready (mặc định 65),
    "watch": decision_watch (mặc định 60),
    "wait": decision_wait (mặc định 55),
    "min_score_gap": 10,
    "min_rr": min_expected_rr hoặc 1.3,
}
```
→ Decision Engine phân loại 3 mức: READY / WATCH / WAIT.

**Không có config:**
→ Dùng `DEFAULT_DECISION_THRESHOLDS = {ready: 65, watch: 60, wait: 55}`.

#### 1b. Build `symbol_auto_trade` (cấu hình cho Nhánh 1)

Chỉ symbol có `backtest = true` mới được thêm vào:

```
symbol_auto_trade[symbol] = {
    "regime": auto_trade_regime,   // "", "trend_up", "range", ...
    "side": auto_trade_side,       // "", "buy", "sell"
    "min_score": min_score hoặc decision_ready,
}
```

### Output
- `ScannerRequest` object chứa: `thresholds`, `symbol_auto_trade`, `symbols`, `account_balance`, `risk_percent`, `min_scores`, `auto_trade_enabled`

---

## Bước 2: ScannerController.run() — Điều phối quét

**File:** `controllers/scanner_controller.py`

### Input
- `ScannerRequest` từ Bước 1
- Data provider (MT5) đã kết nối
- Progress callback để cập nhật UI

### Xử lý

#### 2a. Chuẩn bị dữ liệu (8% → 49% progress)
- Kiểm tra kết nối MT5, lấy account balance
- Với mỗi symbol: resolve broker_symbol, load candles (D1/H4/H1/M15), lấy macro context
- Build `_analyze_one_symbol` arguments

#### 2b. Quét song song (49% → 74% progress)
- `ThreadPoolExecutor` chạy `_analyze_one_symbol()` cho từng symbol
- Mỗi symbol trả về 1 row dict (có `analysis_result` bên trong)
- Gán `auto_trade_branch = "B"` nếu symbol có backtest config, `"A"` nếu không

#### 2c. Sắp xếp (74% progress)
- Gọi `sort_scanner_rows(rows)` — sắp xếp theo scanner_group > opportunity_score > final_score > RR > symbol

#### 2d. Lọc theo 2 nhánh (78% progress)
- Gọi `_apply_scanner_filters(rows, request)` — xem chi tiết ở Bước 7

#### 2e. Build output (94% progress)
- Gọi `build_scanner_output(rows, request, ai_called=0)` — xem chi tiết ở Bước 8

### Output
- `output` dict: `{mode, timestamp, symbols_scanned, summary, rows, market_brief}`

---

## Bước 3: _analyze_one_symbol() → AnalysisPipeline — Pipeline phân tích

**File:** `controllers/scanner_controller.py` → `core/analysis_engine.py` → `core/analysis_pipeline.py`

### Input
- `AnalysisInput`: symbol, broker_symbol, account_balance, risk_percent, ...
- Candles: D1 (≥60), H4 (≥60), H1 (≥30), M15
- `data_quality`: spread, terminal status, news
- `macro_alignment`: điểm macro cho buy/sell (mặc định 15/15)
- `thresholds`: ngưỡng quyết định từ Bước 1

### Pipeline 9 bước

#### Step 1: Validate & Build Context
- Kiểm tra đủ candles (D1≥60, H4≥60, H1≥30)
- `build_technical_snapshot(D1, H4, H1)`:
  - Tính EMA(50) cho D1 và H4, EMA(200) cho D1
  - Tính RSI(14) cho H4
  - Tính MACD histogram cho H4
  - Tính ATR(14) cho H4, D1
  - Phát hiện support/resistance zones (pivot-based)
  - Xác định structure (HH/HL, LH/LL) cho D1, H4
- `build_smc_context(D1, H4, H1)`:
  - Với mỗi timeframe: `swing_points(candles, lookback=5)` — cửa sổ 11 nến (external swings)
  - **Fallback:** Nếu `lookback=5` trả về 0 swings (cả highs và lows), tự động thử lại với `lookback=2` và đặt `swing_source = "fallback"`
  - `_filter_swings_by_atr()` — lọc swing có khoảng cách < 0.2×ATR so với swing trước đó
  - `_detect_internal_structure()` — tìm internal swings (lookback=2) trong từng leg giữa các external swings
  - `detect_bos_choch(swings, candles)` — phát hiện BOS/CHOCH từ 2 swing cuối
  - `_cross_validate_structure(d1, h4, h1)` — cross-validate D1→H4→H1, tính `confluence_score` (-3 đến +5)
  - Kết quả lưu: `external_swings`, `internal_swings` (có tag `leg`), `leg_count`, `confluence`, `swing_source` (`"standard"` hoặc `"fallback"`)
  - Supply/Demand zones, Order Blocks, FVG
  - Liquidity pools (equal highs/lows), Liquidity sweeps
  - Premium/Discount classification
  - Mỗi zone được chấm `zone_score` (0-100) dựa trên:
    - Số lần test và giữ được (+0 đến +20)
    - Độ mới (freshness) (+0 đến +10)
    - Displacement multiple (+0 đến +15)
    - Liquidity sweep (+10)
    - Vị trí premium/discount (-8 đến +12)
- `detect_market_regime()`: xác định `trend_up`, `trend_down`, `range`, `volatile`

**Output Step 1:** `technical` (EMA, RSI, MACD, ATR, S/R zones, structure), `smc` (BOS/CHOCH, zones, sweeps), `market_regime`, `risk_score`

#### Step 2: Correlation Adjustments
- Tính DXY/VIX/US10Y correlation → điều chỉnh buy/sell score
- Nếu DXY tăng → penalty cho buy EUR/USD, bonus cho sell
- `correlation_adjustment` là số điểm cộng/thêm vào macro score

**Output Step 2:** `buy_corr_adj`, `sell_corr_adj`

#### Step 3: Score Scenarios
- Gọi `score_scenario("buy", ...)` và `score_scenario("sell", ...)` từ `signal_engine.py`
- **Công thức tính signal_score (0-100):**

  **a) 6 thành phần với trọng số động theo regime:**

  | Regime | Trend | Momentum | Location | SMC | Risk | Macro |
  |---|---|---|---|---|---|---|
  | trending_up/down | 25 | 15 | 15 | 15 | 15 | 15 |
  | range | 10 | 10 | 25 | 25 | 15 | 15 |
  | volatile | 10 | 5 | 15 | 10 | 40 | 20 |
  | unknown | 18 | 14 | 17 | 15 | 16 | 20 |

  **b) Trend Alignment (0-25):**
  - BUY: EMA50>EMA200 (D1) = +8, price>EMA200 = +5, price>EMA50 = +5, H4 HH/HL = +5, D1+H4 HH/HL = +2
  - SELL: ngược lại

  **c) Momentum Alignment (0-20):**
  - Kết hợp RSI(14) H4 + MACD histogram H4
  - BUY — RSI (`_choose_one` lấy điều kiện đầu tiên khớp):
    - RSI 30-50 và đang tăng = +8
    - RSI 40-60 và không giảm = +6
    - RSI 60-70 và không giảm = +3
    - RSI > 75 = 0
  - BUY — MACD:
    - MACD > 0 và rising (now > prev > prev2) = +10
    - MACD < 0 và rising (now > prev > prev2) = +6
    - MACD > prev = +3
    - MACD > 0 nhưng falling = +5
  - SELL — RSI:
    - RSI 50-70 và đang giảm = +8
    - RSI 40-60 và không tăng = +6
    - RSI 30-40 và không tăng = +3
    - RSI < 25 = 0
  - SELL — MACD:
    - MACD < 0 và falling (now < prev < prev2) = +10
    - MACD > 0 và falling (now < prev < prev2) = +6
    - MACD < prev = +3
    - MACD < 0 nhưng rising = +5
  - Tổng = clamp(RSI score + MACD score, 0, 20)

  **d) Location Quality (0-25):**
  - BUY: giá trong vùng support = +15, gần support (≤0.5 ATR) = +10
  - Bonus: confluence ≥3 = +5, round number = +3
  - Penalty: test_count ≥3 = -5; nếu ≥5 thì cộng dồn thêm -3 (tổng -8)

  **e) SMC Quality (0-15):**
  - H4 BOS đúng hướng: +5 (strong, legs≥3) / +4 (normal, legs≥2) / +3 (weak, legs=1)
  - H1 BOS/CHOCH đúng hướng: +4 (strong) / +3 (normal) / +2 (weak)
  - `leg_count` = số cặp HH/HL hoặc LH/LL liên tiếp cùng hướng xu hướng (từ `_count_trend_legs()`)
  - CHOCH confirmed (legs≥3) → tín hiệu đảo chiều mạnh hơn
  - **Multi-TF Confluence**: H1∥H4=+2, H4∥D1=+2, all-3-TF=+1 (tổng +5), H1⟂H4=-3
  - Zone score ≥75 = +4, ≥55 = +3, <55 = +1
  - Zone ở đúng premium/discount = +3, equilibrium = +1, ngược = -2
  - Zone-level liquidity sweep = +1, H1-level swept_lows/swept_highs = +2, cross-validate technical swing = +2
  - Cap: H4 CHOCH ngược hướng = max 4 điểm, H1 CHOCH ngược = max 6 điểm

  **f) Risk Condition (0-15 scale, scaled to risk weight):**
  - ATR ổn định (0.8-1.2× trung bình 14 ngày) = +6
  - Không có news trong 3h = +6
  - Spread bình thường = +3

  **g) Macro Alignment (0-30 scale, scaled to macro weight):**
  - macro_score × macro_confidence × macro_weight / 30
  - Cộng correlation_adjustment

  **h) Tổng hợp — Direct Sum:**
  ```
  total = technical_scaled + risk_scaled + macro_effective
  ```
  Trọng số các thành phần đã sum = 100, không cần chuẩn hóa thêm.
  Khi thiếu dữ liệu vĩ mô, điểm tổng tự nhiên thấp hơn → phản ánh đúng mức độ tin cậy.

  **i) Macro modifier:**
  - Macro aligned → +5 × macro_confidence
  - Macro conflict → -15 × macro_confidence
  - Macro unclear → 0

  **j) CHOCH cap:** Nếu CHOCH ngược hướng → cap total ≤ 60

  **k) Final signal_score = total (clamp 0-100)**

**Output Step 3:** `scores = {buy: {signal_score, trend_alignment, momentum_alignment, ...}, sell: {...}}`

#### Step 4: Build Trade Scenarios
- `calc_trade_permission()`: kiểm tra MT5 status, spread, news → `allowed` / `caution` / `blocked`
- `get_preferred_zone(smc, side, price)`: tìm SMC zone tốt nhất cho mỗi hướng
- `build_scenarios()` → gọi `build_trade_plan()` cho mỗi side (buy/sell)

  **build_trade_plan() — Tính Entry, SL, TP:**

  **a) Chọn zone:**
  - Nếu có `preferred_zone` (SMC) VÀ zone cách giá ≤ `atr × zone_dist_mult`:
    → `use_preferred = True`, dùng SMC zone làm entry
  - Ngược lại: `select_best_level(support/resistance_zones, price, max_distance, below/above)`

  **b) Tính Source và Execution Zone (Phase 16):**
  ```
  source_zone = original zone boundaries + quality metadata

  BUY structural execution:
    entry_high = source.high
    entry_low  = max(source.low, source.high - target_width)

  SELL structural execution:
    entry_low  = source.low
    entry_high = min(source.high, source.low + target_width)

  target_width = ATR × execution_zone_width_atr_by_quality[tier]
  final entry_zone = structural_execution_zone ∩ RR-valid range
  ```
  - Current width target là `0.25×ATR` cho strong/moderate/weak.
  - `entry_for_rr`, midpoint và worst edge được tính lại sau RR-aware trim.
  - Source zone không được dùng để cho phép execution.

  **c) Tính Stop Loss (ưu tiên: swing → zone boundary → ATR):**
  1. **Luôn tìm swing trước** — `_find_nearest_swing_for_sl()` gom tất cả swing H4+H1, chọn swing gần `level` nhất
     → SL = swing - atr × 0.15 (BUY) hoặc swing + atr × 0.15 (SELL)
  2. Không có swing + có `use_preferred`: SL = zone_low - atr × 0.10 (BUY) hoặc zone_high + atr × 0.10 (SELL)
  3. Không có swing + không có preferred: ATR-based SL (`_calc_stop_loss_buy/sell`)
  - Floor guard: SL phải nằm ngoài entry zone ít nhất `atr × 0.20`
  - Min distance guard: khoảng cách `entry_for_rr → SL` ≥ `atr × 0.20` (SMC) hoặc `atr × 0.50` (technical)

  **d) Tính Take Profit (quality cascade):**
  1. **Equal Highs/Lows** (liquidity clusters từ H4/H1)
  2. **S/R Zones**: duyệt target gần→xa theo executable boundary; BUY dùng `zone.low - 0.03×ATR`, SELL dùng `zone.high + 0.03×ATR`
  3. **Fibonacci Extension** (0.382 từ impulse swing H4, trừ range)
  4. **Swing-based TP** (swing high/low gần nhất từ cả H4+H1)
  - Mọi candidate phải past far edge, clearance ≥`0.15×ATR`, nominal base RR ≥1.0 và effective base RR ≥1.3 sau spread
  - Candidate fail thì thử candidate kế tiếp; không có target thật thì SMC plan để TP/RR trống, technical plan bị loại

  **e) TP2:** next S/R zone sau TP1, hoặc Fib 0.618

  **f) R:R calculation:**
  ```
  risk_reward / expected_effective_rr        = best edge
  risk_reward_base / expected_effective_rr_base = midpoint
  risk_reward_worst / expected_effective_rr_worst = far edge
  ```

  **g) evaluate_entry()** — Xác nhận entry (xem Step 4 detail bên dưới)

  **h) Position Sizing:**
  ```
  risk_amount = balance × risk_percent / 100 × size_multiplier
  loss_per_lot = |entry - sl| × contract_size × quote_to_usd_rate
  suggested_lot = round_lot(risk_amount / loss_per_lot)
  ```

**Output Step 4:** `scenarios = [{type, entry_zone, stop_loss, take_profit, risk_reward, risk_reward_range, ...}, ...]`
  - Sắp xếp theo score giảm dần
  - Mỗi scenario có `entry_status` từ `evaluate_entry()`

#### Phase 16 detail: source zone và final execution zone

Luồng production dùng contract sau:

1. `get_preferred_zone()` chỉ xét zone đúng hướng:
   - BUY: `demand_zone`, `bullish_order_block`, `bullish_fvg`.
   - SELL: `supply_zone`, `bearish_order_block`, `bearish_fvg`.
   - Zone broken hoặc sai family bị loại khỏi cả preferred và fallback.
2. Zone được xếp theo `effective_zone_score`. Breakdown gồm freshness,
   stale/mitigated, test count, source width/ATR, displacement, liquidity
   sweep và premium/discount.
3. `source_zone` giữ nguyên original boundaries và metadata. Nó chỉ dùng để
   phân tích, tooltip và chart reference.
4. `_build_execution_sub_zone()` tạo proximal
   `structural_execution_zone` nằm hoàn toàn trong source:
   - BUY giữ source high.
   - SELL giữ source low.
   - Width target lấy từ `execution_zone_width_atr_by_quality`, hiện là
     `0.25 ATR` cho cả ba tier.
5. Sau khi chọn SL/TP1, `_trim_execution_zone_for_effective_rr()` giao
   structural zone với vùng có worst-edge effective RR đạt
   `execution_zone_min_effective_rr=1.3`, tolerance `0.0001`.
6. Final zone được ghi đồng thời vào `entry_zone` và `execution_zone`. RR
   best/base/worst, entry anchors và lot được tính lại từ final zone.
7. Giao rỗng trả `entry_zone=None`, `execution_zone=None`,
   `rr_trim_diagnostics.status="empty"` và reason code
   `EXECUTION_ZONE_RR_EMPTY`.

Scenario `smc_distant`, `watch_only_fallback` hoặc chưa có TP1 vẫn có thể giữ
source/structural data để theo dõi, nhưng không được dùng source zone thay cho
final execution zone.

#### Step 4 detail: evaluate_entry() — Xác nhận entry với M15

**File:** `core/entry_engine.py`

**Input:** side, technical, smc, H1 candles, entry_zone, M15 candles

**Xử lý:**

**a) Phân loại vị trí giá so với entry zone:**
- `in_zone`: giá đang nằm trong zone
- `near_zone`: giá cách zone ≤ atr × 0.5
- `far`: giá còn xa zone
- `broken` (invalidated): giá đã phá qua zone (BUY: close < zone_low - atr×0.25)

**b) H1 Confirmation (0-35 điểm):**
- BUY: engulfing tăng = 35, rejection tail dài (lower wick ≥ body×0.8) = 30, micro break = 25
- SELL: engulfing giảm = 35, rejection tail dài (upper wick ≥ body×0.8) = 30, micro break = 25
- Không có → 0 điểm, trigger_type = "none"

**c) SMC Confirmation (0-30 điểm):**
- H1 BOS/CHOCH đúng hướng = 20
- H4 BOS đúng hướng = 10
- Liquidity sweep đúng hướng = 10

**d) Location Score (0-15 điểm):**
- BUY ở discount zone = 15, equilibrium = 8, premium = 0
- SELL ở premium zone = 15, equilibrium = 8, discount = 0

**e) Tổng confirmation score:**
```
score = (in_zone? 25 : near_zone? 15 : 0) + h1_score + smc_score + location_score
```

**f) M15 Layer — đánh giá structure + displacement trên M15:**
- `_confirm_m15_structure()`: tìm higher low (BUY) hoặc lower high (SELL) → passed
- `_confirm_m15_displacement()`: nến M15 có body > 0.3×ATR đúng hướng → passed
- Cả 2 passed → `m15_quality = "strict"`, multiplier = 1.0
- 1 passed → `m15_quality = "loose"`, multiplier = 0.85
- 0 passed → `m15_quality = "none"`, multiplier = 0.7
- `confirmation_score *= m15_score_multiplier`

**g) Entry Ladder — phân loại sub-zone (top/mid/bottom):**
```
depth_pct = (high - price) / zone_width  (BUY)
depth_pct = (price - low) / zone_width   (SELL)
top    (0-33%):  size_multiplier=0.4, cần M15 loose+
mid    (33-66%): size_multiplier=0.7, cần M15 strict
bottom (66-100%): size_multiplier=1.0, cần M15 strict + SMC sweep
```

**h) Quyết định entry_status:**
| Điều kiện | entry_status |
|---|---|
| In zone + trigger + score ≥70 + sub-zone confirm | `confirmed_entry` |
| In zone + trigger + score ≥70 + chưa đủ M15 | `waiting_confirmation` |
| In zone nhưng thiếu trigger hoặc score <70 | `waiting_confirmation` |
| Near zone | `watch_zone` |
| Far | `watch_zone` |
| Zone broken | `invalidated` |
| Thiếu dữ liệu | `no_setup` |

**Output evaluate_entry:** `{entry_status, trigger_type, confirmation_score, m15_quality, ready_to_trade, entry_ladder, internal_structure, ...}`

- `internal_structure`: kiểm tra H1 internal swings xác nhận hướng trade (BUY → internal higher low, SELL → internal lower high). Chứa `passed`, `reason`, `last_level`, `prev_level`.

#### Step 5: Determine Direction
- `calculate_direction_bias(buy_scores, sell_scores, min_gap=10)`:
  - `best_side = "buy"` nếu buy_score > sell_score
  - `best_side = "sell"` nếu sell_score > buy_score
  - `is_clear_bias = True` nếu `score_gap ≥ 10`
- Chọn `primary_scenario` khớp với `best_side`
- Chọn `smc_trade_flags` khớp với `best_side`

**Output Step 5:** `direction_bias, best_side, best_score, primary_scenario, smc_trade_flags`

#### Step 6: Apply Gates

- `calc_trade_permission()` — kiểm tra MT5, spread, news, risk_score, best_score → `allowed/caution/blocked`
- `check_account_guard()` — kiểm tra daily loss, weekly loss, consecutive losses
- `build_journal_feedback()` — thống kê từ nhật ký giao dịch cũ
- `check_trade_gates()` — chạy qua 11 gate checks:

  | # | Gate | Điều kiện | Nếu fail |
  |---|---|---|---|
  | 1 | MT5 | terminal_connected + broker_logged_in | BLOCK |
  | 2 | Spread | spread_status != "abnormal" | BLOCK |
  | 3 | DataQuality | không có warning | BLOCK |
  | 4 | News | không có high_impact_event trong 30m | BLOCK |
  | 5 | DailyWeeklyLoss | không vượt daily/weekly loss limit | BLOCK |
  | 6 | AccountGuard | check_account_guard không block | BLOCK |
  | 7 | Journal | journal_feedback không có blocks | BLOCK/WARN |
  | 8 | M15 | m15_quality đạt yêu cầu | WARN |
  | 9 | ExpectedRR | expected_effective_rr_for_gate ưu tiên base, fallback best ≥ min_expected_rr | WARN |
  | 10 | ScoreGap | score_gap ≥ min_score_gap (10) | WARN |
  | 11 | ZoneBroken | entry zone chưa bị phá | WARN |

  - Gate block → `decision_cap = TRADE_BLOCKED` → `scanner_action = stand_aside`
  - Gate warning → `decision_cap = WATCH_ONLY` hoặc `WAITING_CONFIRMATION`

**Output Step 6:** `trade_permission, gate_result, journal_feedback`

#### Step 7: Compute Final Score

- `calculate_final_score()`:
  ```
  final_score = signal_score × 0.65 + evidence_score × 0.20 + execution_quality × 0.15
  ```
  - `signal_score`: điểm từ Step 3
  - `evidence_score`: từ nhật ký giao dịch cũ (nếu có)
  - `execution_quality`: từ execution quality score

- `make_final_decision()` — **Decision Engine**:

  **Thứ tự ưu tiên (layer A → G):**

  | Layer | Điều kiện | Decision |
  |---|---|---|
  | A | Gate không allowed hoặc trade_permission blocked | TRADE_BLOCKED |
  | B | decision_cap == TRADE_BLOCKED | TRADE_BLOCKED |
  | C | decision_cap == WATCH_ONLY | WATCH_ONLY |
  | D | decision_cap == WAITING_CONFIRMATION | WAITING_CONFIRMATION |
  | E | score_gap < min_score_gap (=10) | WAITING_CONFIRMATION |
  | E2 | allow_aggressive_setup + entry waiting_confirmation + score ≥ ready + không có cap | AGGRESSIVE_SETUP |
  | F | entry_status = watch_zone | WATCH_ONLY |
  | F | entry_status = invalidated/no_setup | STAND_ASIDE |
  | F | entry_status = waiting_confirmation | WAITING_CONFIRMATION |
  | G | entry confirmed + score ≥ ready | **READY_TO_TRADE** |
  | G | entry confirmed + score ≥ watch | WATCH_ONLY |
  | G | entry confirmed + score ≥ wait | WAITING_CONFIRMATION |
  | G | entry confirmed + score < wait | STAND_ASIDE |

  - Với **Nhánh 1** (watch=999, wait=999): Layer G chỉ cho READY_TO_TRADE (score ≥ min_score) hoặc STAND_ASIDE (score < min_score). Layer F vẫn áp dụng nếu entry chưa confirmed.
  - Với **Nhánh 2**: Phân loại đủ 3 mức + STAND_ASIDE.

  `legacy_action = decision_to_legacy_action(decision)`:
  - READY_TO_TRADE → `"ready"`
  - WATCH_ONLY → `"watch"`
  - WAITING_CONFIRMATION → `"wait_for_confirmation"`
  - TRADE_BLOCKED / STAND_ASIDE → `"stand_aside"`

**Output Step 7:** `final_score, decision_engine, legacy_action`

#### Step 8: Enrich
- Build `main_view` (text mô tả)
- Tính `pattern_feedback` (H1 pattern backtest confidence)
- Tổng hợp `reason_codes`, `warning_codes`, `block_codes` từ tất cả layers

#### Step 9: Assemble Result
Tổng hợp tất cả output thành 1 dict với các key chính:
```
{symbol, data_quality, market_regime, direction_bias, trade_permission,
 decision_summary, trade_gate, journal_feedback, technical, smc,
 smc_trade_flags, scenario_scores, scenarios, entry_checklist,
 chart_payload, final_score, decision_engine, pipeline_diagnostics, ...}
```

### Output Bước 3
- `result` dict — full pipeline output cho 1 symbol

---

## Bước 4: scanner_row_from_analysis() — Chuyển pipeline result thành scanner row

**File:** `core/scanner.py`

### Input
- `result` dict từ AnalysisPipeline
- `broker_symbol`

### Xử lý
- Trích xuất các trường từ `result`:
  - `buy_score`, `sell_score` từ `scenario_scores`
  - `best_side = "buy"` nếu buy_score ≥ sell_score
  - `best_score = max(buy_score, sell_score)`
  - `best_plan`: scenario đầu tiên khớp `best_side`
  - `scanner_action`: từ `decision_engine.legacy_action`
  - `risk_reward`, `risk_reward_range`, `stop_loss`, `take_profit`,
    final `entry_zone`: từ scenario khớp chính xác `best_side`
  - `source_zone`, `structural_execution_zone`, `rr_trim_diagnostics`: cùng
    scenario với final entry; không trộn metadata từ side khác
  - `price_vs_zone`: `in_zone` / `near_zone` / `far` dựa trên giá vs entry_zone
  - `macro_score`, `macro_bias`, `macro_confidence`
  - `final_score`, `score_gap`, `m15_quality`, `expected_effective_rr`
  - `journal_feedback`: `sample_size`, `expectancy_r`, `evidence_score`
- Gán `analysis_result = result` (full pipeline output, dùng cho màn hình chi tiết)
- Gọi `enrich_scanner_row_with_ranking(row)` → tính `opportunity_score` + `scanner_group`

### Output
- `row` dict với ~35 trường, bao gồm cả `analysis_result`

---

## Bước 5: Scanner Ranking Engine — Xếp hạng và phân nhóm

**File:** `core/scanner_ranking_engine.py`

### Input
- `row` dict từ Bước 4

### Xử lý

#### 5a. Tính opportunity_score (0-120)

Công thức cộng điểm (additive bonus):
```
opportunity = final_score
            + proximity_bonus    (+8 in_zone, +4 near, 0 far)
            + readiness_bonus    (+10 ready_now, +3 waiting_confirmation, 0 còn lại)
            + rr_bonus           (+5 RR≥2.0, +3 RR≥1.5, +1 RR≥1.3, 0 còn lại)
            + zone_quality_bonus (+0~6, tính từ entry_zone_score: 6×(score-50)/50)
            - spread_penalty     (-8 abnormal, -4 caution, 0 normal)
            - news_penalty       (-10 high-impact trong 30m, -5 news trong 3h)
            - journal_penalty    (từ journal_feedback nếu sample ≥ 8)
```
- Kết quả clamp về 0–120.
- Row bị BLOCKED: cap ở mức tối đa 20 điểm.

| Thành phần | Cách tính |
|---|---|
| final_score (base) | Từ pipeline |
| proximity_bonus | in_zone=+8, near_zone=+4, far=0 |
| readiness_bonus | ready_now=+10, waiting_confirmation=+3, khác=0 |
| rr_bonus | RR≥2.0=+5, RR≥1.5=+3, RR≥1.3=+1, thấp hơn=0 |
| zone_quality_bonus | 6 × max(0, (entry_zone_score - 50) / 50), không có zone_score → 0 |
| spread_penalty | abnormal=-8, caution=-4, normal=0 |
| news_penalty | high_impact_30m=-10, news_in_3h=-5, không có=0 |
| journal_penalty | Từ `journal_feedback.opportunity_penalty` nếu sample ≥ 8 |

#### 5b. Phân loại scanner_group

`classify_scanner_group()` phân loại theo **6 lớp ưu tiên** (lớp trên ghi đè lớp dưới):

| Ưu tiên | Lớp | Điều kiện | scanner_group |
|---|---|---|---|
| 1 | Hard block | `decision == TRADE_BLOCKED` hoặc `trade_permission.status == blocked` | `blocked` |
| 2 | Decision engine | `READY_TO_TRADE` | `ready_now` |
| 2 | Decision engine | `WAITING_CONFIRMATION` / `AGGRESSIVE_SETUP` | `waiting_confirmation` |
| 2 | Decision engine | `WATCH_ONLY` / `STAND_ASIDE` | `watch_zone` |
| 3 | Legacy fallback | `scanner_action == "ready"` + `ready_to_trade` truthy | `ready_now` |
| 3 | Legacy fallback | `scanner_action == "wait"` / `"wait_for_confirmation"` | `waiting_confirmation` |
| 3 | Legacy fallback | `scanner_action == "watch"` | `watch_zone` |
| 4 | Entry status | `waiting_confirmation` | `waiting_confirmation` |
| 4 | Entry status | `watch_zone` | `watch_zone` |
| 4 | Entry status | `invalidated` / `no_setup` / `data_unavailable` | `blocked` |
| 5 | Legacy skip | `scanner_action == "skip"` / `"stand_aside"` | `blocked` |
| 6 | Fallback | Không khớp lớp nào ở trên | `watch_zone` |

Ngoài ra, `journal_feedback.decision_cap` (nếu sample ≥ 8) có thể override:
- `TRADE_BLOCKED` → `blocked`
- `WATCH_ONLY` → hạ `ready_now` và `waiting_confirmation` xuống `watch_zone`
- `WAITING_CONFIRMATION` → hạ `ready_now` xuống `waiting_confirmation`

### Output
- Row được thêm: `opportunity_score`, `scanner_group`, `proximity_score`, `rr_score`

---

## Bước 6: sort_scanner_rows() — Sắp xếp kết quả

**File:** `core/scanner.py`

### Xử lý
Sắp xếp theo thứ tự ưu tiên (từ cao xuống thấp):
1. **scanner_group**: `ready_now` (0) > `waiting_confirmation` (1) > `watch_zone` (2) > `blocked` (3)
2. **opportunity_score**: giảm dần (cao nhất trước)
3. **final_score** (hoặc best_score): giảm dần
4. **expected_effective_rr_base** → **expected_effective_rr** → **risk_reward**: giảm dần
5. **symbol**: alphabet

Sau khi sắp xếp, gán `rank` từ 1 → N.

### Output
- `rows` đã sắp xếp, mỗi row có `rank`

---

## Bước 7: _apply_scanner_filters() — Lọc theo 2 nhánh

**File:** `controllers/scanner_controller.py`

### Input
- `rows` đã sắp xếp từ Bước 6
- `ScannerRequest` (chứa `symbol_auto_trade`)

### Xử lý
Với mỗi row:
1. Gọi `_auto_trade_config(request, symbol)`:
   - Symbol có trong `symbol_auto_trade` → trả về config dict → **Nhánh 1**
   - Symbol không có → trả về None → **Nhánh 2**

2. Gọi `_is_auto_trade_candidate(row, at_cfg)`:

   **Guard chung (cả 2 nhánh):**
   - Phải có `analysis_result`
   - `scanner_group != "blocked"`
   - `trade_permission != "blocked"`
   - `journal_feedback.decision_cap` không phải `TRADE_BLOCKED` hoặc `WATCH_ONLY`
   - **`entry_zone_source != "fallback"`** — fallback scenario (zone ATR giả, RR=1:2.0) bị chặn khỏi auto-trade và Hiển thị lệnh

   **Nhánh 1 — `at_cfg is not None` (backtest=true):**
   - Nếu `auto_trade_regime` được set → row's `market_regime` phải khớp
   - `best_score` phải ≥ `min_score` (hoặc 65 nếu min_score=0)
   - Nếu `auto_trade_side` được set → phải có scenario cho side đó
   - Nếu `min_expected_rr > 0` → `expected_effective_rr` phải ≥ `min_expected_rr`. Đây là eligibility filter dùng best effective RR; ExpectedRR gate riêng vẫn ưu tiên base.
   - **Không** check `scanner_action == "ready"` — ghi đè toàn bộ

   **Nhánh 2 — `at_cfg is None` (backtest=false hoặc không config):**
   - `scanner_action == "ready"` (từ Decision Engine dùng `decision_ready`)
   - `trade_permission == "allowed"`
   - Có scenario hợp lệ cho `best_side`

3. Row không pass → đánh dấu:
   - `scanner_action = "skip"`
   - `scanner_group = "blocked"`
   - Thêm tag vào `short_reason`:
     - Nhánh 1: `[Loc: khong dat backtest — can regime=X, side=Y, min_score=Z]`
     - Nhánh 2: `[Loc: chua dat ready]`

4. Re-sort: pass rows trước, fail rows cuối bảng

### Output
- `rows` đã lọc + sắp xếp lại

---

## Bước 8: build_scanner_output() — Đóng gói kết quả

**File:** `core/scanner.py`

### Input
- `rows` đã lọc + sắp xếp
- `ScannerRequest`

### Xử lý
- `scanner_summary(rows)`: đếm số lượng theo `scanner_group` + tính `top_opportunity_score`, `average_opportunity_score`

### Output
```python
{
    "mode": "scanner",
    "timestamp": "2026-07-02T...",
    "symbols_scanned": N,
    "ai_details_limit": 3,
    "ai_called": 0,
    "summary": {
        "ready_now_count": X,
        "waiting_confirmation_count": Y,
        "watch_zone_count": Z,
        "blocked_count": W,
        "top_opportunity_score": S,
        "average_opportunity_score": A,
    },
    "rows": [...],  # danh sách row đã sắp xếp
}
```

---

## Bước 9: ScannerTableModel — Hiển thị bảng kết quả

**File:** `ui/screens/scanner_screen.py`

### Input
- `output` dict từ Bước 8

### Xử lý
- `ScannerTableModel.set_rows(output["rows"])` — cập nhật model
- Bảng hiển thị các cột:

| Cột | Key | Cách hiển thị |
|---|---|---|
| STT | rank | Số thứ tự sau sắp xếp |
| Mã | symbol | Tên symbol |
| Nhóm | scanner_group | "Sẵn sàng ngay" / "Chờ xác nhận" / "Theo dõi" / "Bị chặn" |
| Hướng | direction_bias | "BUY rõ · Gap 28" |
| Chế độ TT | market_regime | "trend_up" / "trend_down" / "range" / "volatile" |
| Entry | price_vs_zone | "Trong vùng" / "Gần vùng" / "Còn xa" (+ tooltip entry_status) |
| M15 | m15_quality | "Chặt" / "Lỏng" / "Không đạt" |
| Điểm | opportunity_score | "105" (+ tooltip final_score + breakdown) |
| R:R thực | expected_effective_rr | Best-case effective RR; base/current nằm trong diagnostic tooltip/order dialog |
| Vĩ mô | macro_bias | "Thuận" / "Trung tính" / "Ngược" |
| Chi tiết | detail_action | "Xem" |

- Màu sắc hàng dựa trên `scanner_group`:
  - `ready_now`: xanh lá
  - `waiting_confirmation`: vàng
  - `watch_zone`: xám
  - `blocked`: đỏ

- **Fallback scenario**: Khi pipeline không tìm được SMC/technical zone thật, `_assemble_result()` tạo fallback với `entry_zone_source = "fallback"`, `entry_zone_score = 50`, `RR = 1:2.0` (SL = price - ATR×1.2, TP = price + ATR×2.4). Fallback **vẫn hiển thị trong bảng** để trader tham khảo, nhưng **bị chặn** khỏi "Hiển thị lệnh", auto-trade, và Telegram alerts.

### Khi click vào 1 row
- Mở `ScannerDetailScreen` → gọi `_refresh_chart()`:
  - `build_full_chart_payload(symbol, analysis_result)` → tạo dữ liệu cho biểu đồ Lightweight Charts
  - Hiển thị: nến (H1 mặc định) + EMA + SMC zones + Entry zone + SL + TP lines
  - Hiển thị cards: best_score, buy/sell, final_score, gap, macro, RR, entry_status, position, M15, regime, permission, journal

### Khi thực thi auto/manual order

- Auto-trade lấy live ask/bid qua `MT5Service.get_live_price()`, fallback về
  `technical.price` khi cần.
- Giá phải còn trong entry zone và `current_effective_rr >= min_rr`; nếu không,
  order bị skip với diagnostic reason.
- Manual order dùng live price, fallback `order_info.entry_price`, và block với
  warning khi current RR không đạt.
- Auto result trả `diagnostics[]`; manual order gắn `execution_guard`.
- Gate, eligibility, auto/manual guard, order dialog và chart đều đọc final
  `entry_zone` của cùng scenario. Thiếu final zone thì candidate bị loại; không
  fallback sang `source_zone`, `watch_zone` hoặc scenario đối diện.
- Chart payload đánh dấu final entry bằng `execution_eligible=true`; source
  zone dùng style tham khảo và `execution_eligible=false`.

---

## Tổng kết luồng dữ liệu

```
Settings (symbol_settings)
  │
  ├── thresholds[ symbol ] → AnalysisPipeline → make_final_decision() → scanner_action
  │
  └── symbol_auto_trade[ symbol ] → _auto_trade_config() → _is_auto_trade_candidate()
                                                                  │
                    ┌─────────────────────────────────────────────┤
                    │                                             │
              Nhánh 1 (at_cfg not None)                    Nhánh 2 (at_cfg is None)
              backtest=true                                backtest=false / no config
                    │                                             │
              Check: regime + side + min_score + min_rr   Check: scanner_action == "ready"
              (ghi đè toàn bộ)                             (từ decision_ready/watch/wait)
                    │                                             │
                    └─────────────────────────────────────────────┤
                                                                  │
                                                    _apply_scanner_filters()
                                                          │
                                                    ┌─────┴─────┐
                                                    │             │
                                                  PASS          FAIL
                                                    │             │
                                              hiển thị       scanner_action="skip"
                                              bình thường    scanner_group="blocked"
                                                             đẩy xuống cuối bảng
```
