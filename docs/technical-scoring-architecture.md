# Luồng chạy chi tiết: một cặp giao dịch đi qua Scanner như thế nào

> Nguồn: `ui/screens/scanner_screen.py`, `controllers/scanner_controller.py`, `core/analysis_pipeline.py`, `core/entry_engine.py`, `core/scanner.py`, `core/scanner_ranking_engine.py`, `core/decision_engine.py`, `core/trade_gate_engine.py`

## Sơ đồ tổng quan

```
ScannerScreen (UI)
  → build ScannerRequest (thresholds, symbol_auto_trade)
  → ScannerWorker (thread riêng, không đơ UI)
    → ScannerController.run()
      → _analyze_one_symbol() × N symbols (chạy song song, ThreadPoolExecutor)
        → analyze_symbol() → AnalysisPipeline.execute()  [Pipeline 9 bước]
        → scanner_row_from_analysis()
      → sort_scanner_rows()
      → _apply_scanner_filters()   [2 nhánh auto-trade: A / B]
      → build_scanner_output()
  → ScannerScreen._scan_finished()
    → ScannerTableModel.set_rows()
    → hiển thị bảng kết quả
```

Một mã (ví dụ `EUR/USD`) đi qua **9 bước lớn**, trong đó Bước 3 (Pipeline phân tích) tự nó có **9 bước con**.

---

## Bước 1 — Build ScannerRequest

**File:** `ui/screens/scanner_screen.py` → `_start_scan()`

### Đầu vào
- Danh sách symbol được chọn trên UI
- `SymbolScanSettings` của từng symbol (đọc từ `settings.trading.symbol_settings`)

### Xử lý

**1a. Xây dựng `thresholds`** — ngưỡng quyết định cho Decision Engine của riêng từng mã:

- Nếu symbol bật **Backtest = true** (Nhánh B):
  - `ready` = `min_score` nếu >0, ngược lại lấy `decision_ready`
  - `watch = 999`, `wait = 999` → **vô hiệu hóa** 2 mức trung gian, Decision Engine chỉ còn phân được READY hoặc STAND_ASIDE
  - `min_rr` = `min_expected_rr` hoặc 0
- Nếu symbol **Backtest = false** (Nhánh A) nhưng có config:
  - `ready/watch/wait` = `decision_ready/watch/wait` (mặc định 65/60/55)
  - `min_rr` = `min_expected_rr` hoặc 1.3 (mặc định cứng)
- Không có config gì → dùng mặc định hệ thống: 65/60/55

**1b. Xây dựng `symbol_auto_trade`** — chỉ những mã có `backtest = true` mới được đưa vào dict này, kèm `regime`, `side`, `min_score` riêng.

### Đầu ra
`ScannerRequest`: `{thresholds, symbol_auto_trade, symbols, account_balance, risk_percent, min_scores, auto_trade_enabled}`

---

## Bước 2 — ScannerController.run() điều phối quét

**File:** `controllers/scanner_controller.py`

1. **Chuẩn bị dữ liệu (8%→49% progress bar):** kiểm tra MT5 đã kết nối, lấy account balance thật, với mỗi symbol resolve `broker_symbol` (VD `EURUSD` → `EURUSDm`), tải nến D1/H4/H1/M15, lấy macro context.
2. **Quét song song (49%→74%):** `ThreadPoolExecutor` chạy `_analyze_one_symbol()` cho tất cả symbol cùng lúc → mỗi symbol trả 1 row, gán `auto_trade_branch = "B"` nếu có backtest config, `"A"` nếu không.
3. **Sắp xếp (74%):** `sort_scanner_rows()`.
4. **Lọc theo 2 nhánh (78%):** `_apply_scanner_filters()` (chi tiết Bước 7).
5. **Đóng gói output (94%):** `build_scanner_output()`.

---

## Bước 3 — AnalysisPipeline: pipeline phân tích 1 mã (9 bước con)

**File:** `core/analysis_engine.py` → `core/analysis_pipeline.py`

### Step 1 — Validate & xây dựng context
- Kiểm tra đủ dữ liệu nến tối thiểu: D1≥60, H4≥60, H1≥30 nến. Thiếu → chặn ngay.
- `build_technical_snapshot()`: EMA50/EMA200 (D1, H4), RSI14 (H4), MACD histogram (H4), ATR14 (H4, D1), phát hiện vùng support/resistance (pivot-based), xác định cấu trúc HH/HL hoặc LH/LL cho D1/H4.
- `build_smc_context()`: tìm swing point (external + internal), phát hiện BOS/CHOCH, order block, FVG, liquidity pool/sweep, phân loại premium/discount, chấm `zone_score` (0–100) cho mỗi vùng.
- `detect_market_regime()`: phân loại `trend_up / trend_down / range / volatile`.
- Tính luôn **Risk score (0–15đ)**.

→ Output: `technical`, `smc`, `market_regime`, `risk_score`.

### Step 2 — Điều chỉnh tương quan (Correlation)
- Tính tương quan DXY/VIX/US10Y. VD: DXY tăng → phạt điểm BUY của EUR/USD, cộng điểm SELL.
→ Output: `buy_corr_adj`, `sell_corr_adj`.

### Step 3 — Chấm điểm 2 kịch bản BUY & SELL
- Gọi `score_scenario()` 2 lần (buy, sell) — tính `signal_score` 0–100 từ 6 thành phần (Trend/Momentum/Location/SMC/Risk/Macro), trọng số động theo regime, có normalize, macro modifier, và CHOCH cap.
- *(Xem chi tiết công thức trong file `technical-scoring-system.md` đã xuất trước đó — không lặp lại ở đây.)*
→ Output: `scores = {buy: {...}, sell: {...}}`.

### Step 4 — Xây dựng Trade Scenario (Entry/SL/TP)
1. `calc_trade_permission()`: kiểm tra MT5/spread/news → `allowed / caution / blocked`.
2. `get_preferred_zone()`: tìm SMC zone tốt nhất cho mỗi hướng.
3. `build_trade_plan()` cho mỗi side:
   - **Chọn zone:** ưu tiên SMC zone nếu đủ gần (≤ `atr × zone_dist_mult`), không thì chọn support/resistance zone gần nhất.
   - **Entry zone:** vùng hẹp quanh mức zone, độ rộng = `clamp(zone_width/atr × 0.5, 0.10, 0.30) × ATR`.
   - **Stop Loss:** ưu tiên swing structural gần nhất (H4+H1) → fallback cạnh SMC zone → fallback ATR, có guard đảm bảo SL cách entry tối thiểu 0.20×ATR (SMC) hoặc 0.50×ATR (technical).
   - **Take Profit — cascade 5 bước**, dừng ở bước đầu tiên có kết quả: (1) Equal Highs/Lows → (2) S/R zone → (3) Fibonacci extension 0.382 → (4) Swing-based TP → (5) nếu vẫn không có và đang dùng SMC zone thì **để trống TP** (không tự bịa).
   - **R:R** và `expected_effective_rr` (đã trừ hao chi phí spread), kèm `risk_reward_range` (best/base/worst theo 3 vị trí khớp lệnh).
   - **Position sizing:** `risk_amount = balance × risk% × size_multiplier`, chia cho `loss_per_lot` để ra lot đề xuất, làm tròn theo bước lot của broker.
4. Gọi `evaluate_entry()` để xác nhận trạng thái entry (chi tiết bên dưới).

→ Output: `scenarios[]`, mỗi cái có `entry_zone, stop_loss, take_profit, risk_reward, risk_reward_range, entry_status`.

#### Step 4 chi tiết — `evaluate_entry()` (core/entry_engine.py)

Đây là nơi **duy nhất** trong hệ thống được phép xác nhận trạng thái sẵn sàng vào lệnh.

1. **Phân loại vị trí giá vs entry zone:** `in_zone` / `near_zone` (≤0.5 ATR) / `far` / `broken` (giá đã phá qua zone theo hướng bất lợi).
2. **H1 Confirmation (0–35đ):** engulfing đúng hướng = 35, rejection wick dài = 30, micro break = 25, không có = 0.
3. **SMC Confirmation (0–30đ):** H1 BOS/CHOCH đúng hướng +20, H4 BOS đúng hướng +10, liquidity sweep đúng hướng +10.
4. **Location score (0–15đ):** BUY ở discount zone / SELL ở premium zone = 15đ (vị trí lý tưởng), equilibrium = 8đ, ngược lại = 0đ.
5. **M15 layer:** kiểm tra cấu trúc M15 (higher low/lower high) + displacement candle. Cả 2 đạt → `m15_quality = "strict"` (hệ số 1.0); 1 đạt → `"loose"` (0.85); không đạt → `"none"` (0.7) — nhân vào `confirmation_score`.
6. **Entry ladder (chia entry zone thành 3 lớp):** top (0–33%, size×0.4, cần M15 loose+) / mid (33–66%, size×0.7, cần M15 strict) / bottom (66–100%, size×1.0, cần M15 strict + SMC sweep).
7. **Quyết định `entry_status` cuối cùng:**

| Điều kiện | entry_status |
|---|---|
| In zone + có trigger + score ≥70 + đủ điều kiện sub-zone | `confirmed_entry` |
| In zone + có trigger + score ≥70 nhưng M15 chưa đủ | `waiting_confirmation` |
| In zone nhưng thiếu trigger hoặc score <70 | `waiting_confirmation` |
| Near zone | `watch_zone` |
| Far | `watch_zone` |
| Zone đã bị phá | `invalidated` |
| Thiếu dữ liệu | `no_setup` |

### Step 5 — Xác định hướng (Direction Bias)
- `calculate_direction_bias(buy, sell, min_gap=10)`: hướng nào điểm cao hơn thắng, nhưng chỉ coi là "rõ ràng" (`is_clear_bias`) nếu chênh lệch ≥10 điểm.
- Chọn `primary_scenario` khớp `best_side`.

### Step 6 — Áp dụng Gate an toàn (11 gate)
- `calc_trade_permission()`, `check_account_guard()` (daily/weekly loss, chuỗi thua liên tiếp), `build_journal_feedback()` (thống kê từ nhật ký cũ), rồi `check_trade_gates()` chạy tuần tự 11 gate:

| # | Gate | Kiểm tra | Nếu fail |
|---|---|---|---|
| 1 | MT5 | Terminal đã kết nối + đã đăng nhập | BLOCK |
| 2 | Spread | Spread không "abnormal" | BLOCK |
| 3 | DataQuality | Không có warning dữ liệu | BLOCK |
| 4 | News | Không có tin lớn trong 30 phút tới | BLOCK |
| 5 | DailyWeeklyLoss | Chưa vượt hạn mức lỗ ngày/tuần | BLOCK |
| 6 | AccountGuard | Không bị chặn theo account guard | BLOCK |
| 7 | Journal | Journal feedback không có block | BLOCK/WARN |
| 8 | M15 | `m15_quality` đạt yêu cầu | WARN |
| 9 | ExpectedRR | `expected_effective_rr` ≥ `min_expected_rr` | WARN |
| 10 | ScoreGap | Chênh lệch điểm BUY/SELL ≥10 | WARN |
| 11 | ZoneBroken | Entry zone chưa bị phá | WARN |

- Gate **BLOCK** → `decision_cap = TRADE_BLOCKED` → hạ thẳng xuống `stand_aside`.
- Gate **WARN** → hạ cap xuống `WATCH_ONLY` hoặc `WAITING_CONFIRMATION`, không chặn hẳn.

### Step 7 — Tính Final Score & ra quyết định
- `calculate_final_score()`: `final_score = signal_score×0.65 + evidence_score×0.20 + execution_quality×0.15`.
- `make_final_decision()` — Decision Engine, xét theo thứ tự ưu tiên từ trên xuống (dừng ở điều kiện đầu tiên khớp):

| Ưu tiên | Điều kiện | Kết quả |
|---|---|---|
| A | Gate không cho phép hoặc trade_permission = blocked | `TRADE_BLOCKED` |
| B | decision_cap = TRADE_BLOCKED (từ gate) | `TRADE_BLOCKED` |
| C | decision_cap = WATCH_ONLY | `WATCH_ONLY` |
| D | decision_cap = WAITING_CONFIRMATION | `WAITING_CONFIRMATION` |
| E | score_gap < 10 (hướng chưa rõ ràng) | `WAITING_CONFIRMATION` |
| E2 | Chế độ aggressive bật + entry đang waiting + score ≥ ready + không bị cap | `AGGRESSIVE_SETUP` |
| F | entry_status = watch_zone | `WATCH_ONLY` |
| F | entry_status = invalidated / no_setup | `STAND_ASIDE` |
| F | entry_status = waiting_confirmation | `WAITING_CONFIRMATION` |
| G | entry confirmed + score ≥ ready | **`READY_TO_TRADE`** |
| G | entry confirmed + score ≥ watch | `WATCH_ONLY` |
| G | entry confirmed + score ≥ wait | `WAITING_CONFIRMATION` |
| G | entry confirmed + score < wait | `STAND_ASIDE` |

- Với mã dùng Nhánh B (watch/wait bị đặt =999) → chỉ còn 2 kết quả khả dĩ ở lớp G: READY hoặc STAND_ASIDE.
- `legacy_action` quy đổi: READY_TO_TRADE→`"ready"`, WATCH_ONLY→`"watch"`, WAITING_CONFIRMATION→`"wait_for_confirmation"`, còn lại→`"stand_aside"`.

### Step 8 — Làm giàu dữ liệu (Enrich)
- Build `main_view` (mô tả dạng văn bản), `pattern_feedback` (độ tin cậy pattern H1 theo backtest), gộp toàn bộ `reason_codes/warning_codes/block_codes` từ mọi lớp.

### Step 9 — Đóng gói kết quả
- Gộp tất cả thành 1 dict lớn: `symbol, data_quality, market_regime, direction_bias, trade_permission, decision_summary, trade_gate, journal_feedback, technical, smc, scenario_scores, scenarios, entry_checklist, chart_payload, final_score, decision_engine, pipeline_diagnostics...`

---

## Bước 4 — scanner_row_from_analysis(): chuyển kết quả pipeline thành 1 dòng bảng

**File:** `core/scanner.py`

Trích các trường quan trọng ra thành `row` phẳng để hiển thị (buy_score, sell_score, best_side, best_score, scanner_action, risk_reward, risk_reward_range, entry_zone, price_vs_zone, macro_score/bias, final_score, score_gap, m15_quality, expected_effective_rr, journal_feedback...), giữ nguyên `analysis_result` đầy đủ để dùng cho màn hình chi tiết. Sau đó gọi `enrich_scanner_row_with_ranking()` (Bước 5).

---

## Bước 5 — Scanner Ranking Engine: xếp hạng & phân nhóm

**File:** `core/scanner_ranking_engine.py`

### 5a. Tính `opportunity_score` (0–120)

```
opportunity = final_score
            + proximity_bonus    (in_zone=+8, near_zone=+4, far=0)
            + readiness_bonus    (ready_now=+10, waiting_confirmation=+3, khác=0)
            + rr_bonus           (RR≥2.0=+5, RR≥1.5=+3, RR≥1.3=+1, thấp hơn=0)
            + zone_quality_bonus (+0~6, từ entry_zone_score: 6×(score-50)/50)
            − spread_penalty     (abnormal=-8, caution=-4, normal=0)
            − news_penalty       (tin lớn trong 30m=-10, tin trong 3h=-5)
            − journal_penalty    (từ journal_feedback, chỉ áp dụng nếu sample ≥8)
```
Clamp 0–120. Row bị BLOCKED → cap cứng tối đa 20 điểm.

### 5b. Phân loại `scanner_group` (6 lớp ưu tiên, lớp trên ghi đè lớp dưới)

1. **Hard block:** decision = TRADE_BLOCKED hoặc trade_permission blocked → `blocked`
2. **Decision engine:** READY_TO_TRADE → `ready_now`; WAITING_CONFIRMATION/AGGRESSIVE_SETUP → `waiting_confirmation`; WATCH_ONLY/STAND_ASIDE → `watch_zone`
3. **Legacy fallback** (nếu Decision Engine không có kết quả): dựa theo `scanner_action` cũ
4. **Entry status** làm fallback tiếp theo
5. **Legacy skip:** `scanner_action` = skip/stand_aside → `blocked`
6. **Fallback cuối:** không khớp gì → `watch_zone`

- `journal_feedback.decision_cap` (nếu đủ mẫu ≥8 lệnh lịch sử) có thể **hạ cấp thêm**: TRADE_BLOCKED → blocked; WATCH_ONLY → hạ ready_now/waiting_confirmation xuống watch_zone; WAITING_CONFIRMATION → hạ ready_now xuống waiting_confirmation.

---

## Bước 6 — sort_scanner_rows(): sắp xếp

**File:** `core/scanner.py`

Thứ tự ưu tiên khi sắp xếp (giảm dần):
1. `scanner_group`: ready_now > waiting_confirmation > watch_zone > blocked
2. `opportunity_score` (cao nhất trước)
3. `final_score` (hoặc best_score nếu thiếu)
4. `expected_effective_rr` (hoặc risk_reward)
5. `symbol` (alphabet)

Sau đó gán `rank` từ 1→N.

---

## Bước 7 — _apply_scanner_filters(): lọc theo 2 nhánh auto-trade

**File:** `controllers/scanner_controller.py`

### Guard chung (áp dụng cho cả 2 nhánh)
- Phải có `analysis_result`
- `scanner_group != "blocked"`
- `trade_permission != "blocked"`
- `journal_feedback.decision_cap` không phải TRADE_BLOCKED / WATCH_ONLY
- `entry_zone_source != "fallback"` — **scenario dựng từ ATR giả (không có zone thật)** bị chặn hoàn toàn khỏi auto-trade, kể cả khi hiển thị trong bảng để tham khảo

### Nhánh A — symbol không có config backtest riêng
- `scanner_action == "ready"` (đến từ Decision Engine dùng ngưỡng `decision_ready` mặc định)
- `trade_permission == "allowed"`
- Có scenario hợp lệ cho `best_side`

### Nhánh B — symbol có `backtest = true` + filter riêng
- Regime khớp `auto_trade_regime` (nếu có đặt)
- `best_score` ≥ `min_score` (fallback 65 nếu để trống)
- Side khớp `auto_trade_side` (nếu có đặt)
- `expected_effective_rr` ≥ `min_expected_rr` (nếu >0)
- **Không** yêu cầu `scanner_action == "ready"` — filter riêng có quyền "phủ quyết" pipeline

Row nào không pass → gán `scanner_action = "skip"`, `scanner_group = "blocked"`, thêm dòng lý do vào `short_reason`, rồi re-sort để đẩy các row fail xuống cuối bảng.

---

## Bước 8 — build_scanner_output(): đóng gói kết quả cuối

**File:** `core/scanner.py`

Tính `scanner_summary()` (đếm số lượng theo từng scanner_group + điểm cơ hội cao nhất/trung bình), gói thành:

```python
{
  "mode": "scanner", "timestamp": "...", "symbols_scanned": N,
  "summary": {"ready_now_count": X, "waiting_confirmation_count": Y,
              "watch_zone_count": Z, "blocked_count": W,
              "top_opportunity_score": S, "average_opportunity_score": A},
  "rows": [...]  # đã sắp xếp
}
```

---

## Bước 9 — Hiển thị bảng kết quả (ScannerTableModel)

**File:** `ui/screens/scanner_screen.py`

Cột hiển thị: STT (rank) · Mã · Nhóm (màu theo scanner_group) · Hướng (kèm score gap) · Chế độ TT (regime) · Entry (trong/gần/xa vùng) · M15 (chặt/lỏng/không đạt) · Điểm (opportunity_score, tooltip breakdown) · R:R (dạng "5.6 (2.9–5.6)" — best + dải worst–best từ `risk_reward_range`) · Vĩ mô (thuận/trung tính/ngược) · nút Xem chi tiết.

**Lưu ý về fallback scenario:** khi pipeline không tìm được zone SMC/technical thật, hệ thống vẫn tạo 1 scenario "giả" để tham khảo (`entry_zone_source = "fallback"`, RR cố định 1:2.0 dựa trên ATR). Row này **vẫn hiển thị trong bảng** nhưng **luôn bị chặn** khỏi auto-trade, "Hiển thị lệnh", và Telegram alert.

Click vào 1 row → mở `ScannerDetailScreen`, load biểu đồ (nến H1 + EMA + SMC zone + Entry/SL/TP) và các card thông tin: best_score, buy/sell, final_score, gap, macro, RR, entry_status, vị trí giá, M15, regime, permission, journal.

---

## Tổng kết sơ đồ quyết định auto-trade

```
Settings (symbol_settings)
  │
  ├── thresholds[symbol] → AnalysisPipeline → make_final_decision() → scanner_action
  │
  └── symbol_auto_trade[symbol] → _auto_trade_config() → _is_auto_trade_candidate()
                                                                │
                    ┌───────────────────────────────────────────┤
                    │                                           │
              NHÁNH B (có config)                        NHÁNH A (không config)
              backtest = true                             backtest = false
                    │                                           │
        Check: regime + side + min_score + min_rr       Check: scanner_action=="ready"
        (ghi đè quyết định của pipeline nếu đạt)          (theo đúng decision_ready/watch/wait)
                    │                                           │
                    └───────────────────────────────────────────┤
                                                                 │
                                              _apply_scanner_filters()
                                                     │
                                            ┌────────┴────────┐
                                          PASS               FAIL
                                            │                  │
                                     hiển thị bình thường   scanner_action="skip"
                                     (có thể auto-trade      scanner_group="blocked"
                                      nếu bật auto-entry)    đẩy xuống cuối bảng
```