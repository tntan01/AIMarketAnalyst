# [ĐÁNH GIÁ ĐỘC LẬP] Code Review — Entry, SL, TP

> **Ngày đánh giá:** 2026-07-03
> **Người đánh giá:** Deepseek-v4-pro
> **Phương pháp:** Đọc toàn bộ source code + chạy test thực tế, không dựa trên cảm tính

---

## Phạm vi đã đọc

| File | Dòng | Mức độ |
|------|------|--------|
| `core/entry_engine.py` | 1–564 | Toàn bộ |
| `core/risk_engine.py` | 403–710 | `build_trade_plan` + helpers (SL, TP, sizing) |
| `tests/test_entry_engine.py` | 1–112 | Toàn bộ |
| `tests/test_risk_engine.py` | Phần Entry/SL/TP | Các test liên quan |

---

## Kết quả chạy test thực tế

```
tests/test_entry_engine.py → 4/4 PASSED ✅ (2 bug đã sửa)
tests/test_risk_engine.py  → 30/30 PASSED ✅ (6 skipped — cần MT5)
```

**Trước sửa:** 2 tests FAIL với `UnboundLocalError`. **Sau sửa:** 0 FAIL.

---

## A. TÍNH ĐÚNG ĐẮN

### ✅ Ưu điểm

**1. Cascade TP 5 bậc với guard R:R từng bước**

`build_trade_plan` thử TP theo thứ tự: Equal Highs/Lows → S/R Zones → Fibonacci Extension → Swing-based TP → fallback. Mỗi bậc đều kiểm tra `tp - entry > entry - sl` (R:R > 1:1) trước khi chấp nhận (`risk_engine.py:493-510`). Đây là cơ chế phòng thủ tốt — không bao giờ trả về TP có R:R < 1.

**2. Entry Ladder với sub-zone sizing**

Phân loại top/mid/bottom dựa trên vị trí giá trong entry zone (`entry_engine.py:32-56`), mỗi sub-zone có yêu cầu xác nhận và size multiplier khác nhau:
- **Top**: 40% size, chỉ cần M15 loose+ (`entry_engine.py:255-275`)
- **Mid**: 70% size, cần M15 strict (`entry_engine.py:277-307`)
- **Bottom**: 100% size, cần M15 strict + SMC sweep (`entry_engine.py:309-351`)
- **Bottom không sweep** → degrade xuống mid (70%) (`entry_engine.py:320-331`)

**3. SL placement đa tầng với guard**

- SMC zone boundary + buffer 0.10×ATR nếu có preferred_zone (`risk_engine.py:472-475`)
- Fallback: swing nearest từ H4+H1 + buffer 0.15×ATR (`risk_engine.py:477-481`)
- Fallback cuối: ATR-based với cap 1.5× (`risk_engine.py:483`)
- Guard SL floor/ceiling: SL phải nằm ngoài entry zone ít nhất 0.10×ATR (`risk_engine.py:485-487`)
- Guard min distance: từ chối plan nếu SL quá gần entry (`risk_engine.py:489-491`)

**4. Dynamic regime-aware parameters**

- `REGIME_SL_MULTIPLIER`: SL rộng hơn trong volatile (0.85×), hẹp hơn trong trend (0.65×) (`risk_engine.py:26-32`)
- `REGIME_ZONE_DISTANCE_MULT`: zone distance cho phép xa hơn trong trend (3.5×ATR) (`risk_engine.py:33-39`)
- `watch_zone_atr_mult` thay đổi theo regime: volatile=0.70, trend=0.40, range=0.50 (`risk_engine.py:422-429`)

**5. Position sizing với quote-to-USD conversion**

`position_sizing` tự động lấy quote currency rate từ MT5 để tính loss_per_lot cho non-USD pairs (`risk_engine.py:777-798`). Có guard `loss_per_lot > 0` tránh chia cho 0.

**6. Defensive type checking nhất quán**

Pattern `smc.get("H4", {}) if isinstance(smc, dict) else {}` được dùng nhất quán khắp `risk_engine.py` và `entry_engine.py`.

**7. M15 confirmation 2 lớp với score multiplier**

- `_confirm_m15_structure`: kiểm tra higher low (BUY) / lower high (SELL) trên M15 (`entry_engine.py:72-83`)
- `_confirm_m15_displacement`: kiểm tra nến displacement đủ mạnh (`entry_engine.py:86-105`)
- Strict = cả 2 pass (×1.0), Loose = 1 pass (×0.85), None = 0 pass (×0.7) (`entry_engine.py:200-208`)

**8. Backtest fallback cho M15**

Khi thiếu M15 trong backtest, tự động giả định M15 loose để sub-zone logic vẫn hoạt động (`entry_engine.py:231-236`).

---

### ❌ Nhược điểm / Rủi ro

**[BUG #1 — ĐÃ SỬA] `UnboundLocalError`: `internal_structure` referenced before assignment**

```python
# entry_engine.py:159-164
if len(entry_zone) != 2 or price <= 0 or atr_value <= 0:
    reason = "Thiếu dữ liệu giá, ATR hoặc vùng vào lệnh."
    if not m15_available:
        reason += " | M15 data unavailable"
    return _result("no_setup", "none", 0, reason,
                   m15_available=m15_available,
                   internal_structure=internal_structure)  # ← UNBOUND! (assigned at line 213)

# entry_engine.py:171-177 — same bug
if broken:
    reason = "Giá đã phá vùng vào lệnh dự kiến."
    if not m15_available:
        reason += " | M15 data unavailable"
    return _result("invalidated", "zone_broken", 0, reason,
                   m15_available=m15_available,
                   warning_codes=[ZONE_BROKEN],
                   internal_structure=internal_structure)  # ← UNBOUND! (assigned at line 213)
```

**Dẫn chứng:** 2 tests FAIL với `UnboundLocalError`:
- `test_entry_invalidates_when_price_breaks_zone` → crash tại `entry_engine.py:177`
- `test_entry_returns_no_setup_for_missing_price_atr_or_zone` → crash tại `entry_engine.py:164`

**[BUG #2 — ĐÃ SỬA] Missing `internal_structure` kwarg — bị đưa nhầm vào string**

```python
# entry_engine.py:324-331
return _result("confirmed_entry", trigger_type, confirmation_score,
    "Bottom zone — thiếu SMC sweep, degrade xuống mid (70% size, internal_structure=internal_structure).",
    #                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    #                "internal_structure=internal_structure" nằm TRONG CHUỖI, không phải keyword argument!
    in_zone, True,
    m15_structure=m15_structure, m15_displacement=m15_displacement,
    m15_available=m15_available, m15_quality=m15_quality,
    m15_score_multiplier=m15_score_multiplier,
    entry_ladder=entry_ladder)
    # ← THIẾU: internal_structure=internal_structure
```

Tất cả 16 `_result()` calls khác trong hàm đều có `internal_structure=internal_structure` ở vị trí kwarg. Riêng call này bị đưa nhầm vào trong string do lỗi copy-paste. Hậu quả: `internal_structure` key bị thiếu trong result dict của bottom-zone degrade path. Downstream code đọc `entry_context.get("internal_structure")` sẽ nhận `None`.

**[MAGIC NUMBERS — ĐÃ SỬA] — Đã extract 16 constants trong `risk_engine.py` và `entry_engine.py`**

| Dòng | Giá trị | Vai trò |
|------|---------|---------|
| `risk_engine.py:418` | `atr_value * 0.20` | Min stop distance multiplier |
| `risk_engine.py:418` | `spread_price * 3` | Spread multiplier for min stop |
| `risk_engine.py:464` | `zone_width_atr * 0.5` | Entry zone ATR width multiplier |
| `risk_engine.py:467,537` | `atr_value * 0.10` | Watch zone offset |
| `risk_engine.py:170` | `atr_value * 0.25` | Zone broken threshold |
| `risk_engine.py:169` | `atr_value * 0.5` | Near zone threshold |
| `risk_engine.py:485,555` | `atr_value * 0.10` | SL floor/ceiling buffer |
| `risk_engine.py:422-429` | `0.70, 0.40, 0.50` | Watch zone ATR multipliers by regime |
| `entry_engine.py:86` | `threshold_atr: float = 0.3` | M15 displacement threshold |
| `entry_engine.py:502` | `body * 0.8, candle_range * 0.25` | H1 rejection wick ratio thresholds |
| `entry_engine.py:503` | `candles[-3:-1]` | H1 micro break window size |
| `entry_engine.py:73,87` | `12, 15` | Min M15 candles for structure/displacement |

**[DESIGN — 🟡 MEDIUM] Entry aggressiveness mặc định = 0.0 có thể quá optimistic**

```python
# risk_engine.py:58
_ENTRY_AGGRESSIVENESS = 0.0  # 0.0=nearest edge (best RR), 1.0=farthest edge (old behavior)
```

Entry price cho R:R được tính ở cạnh TỐT NHẤT của entry zone (BUY = entry_low, SELL = entry_high). Trong thực tế, giá hiếm khi fill chính xác ở cạnh tốt nhất → R:R thực tế thường thấp hơn R:R hiển thị. Không phải bug, nhưng có thể gây kỳ vọng sai khi so sánh R:R hiển thị với kết quả thực tế.

**[DESIGN — 🟢 LOW] Condition text hardcode tiếng Việt**

```python
# risk_engine.py:689-705
def _build_buy_condition(h4_smc: dict[str, Any]) -> str:
    base = "Chỉ cân nhắc nếu H1 đóng nến tăng tại vùng hỗ trợ và spread vẫn bình thường."
```

Condition/invalidation text không configurable, không hỗ trợ i18n. Tác động thấp vì đây là app nội bộ.

**[TEST COVERAGE — 🟡 MEDIUM]**

- `evaluate_entry()`: 4 tests, 2 fail. Chưa test M15 sub-zone logic (top/mid/bottom/degrade)
- `build_trade_plan()`: test gián tiếp qua integration test. Chưa test riêng TP cascade, SL guard, position sizing edge cases
- `_h1_confirmation()`: chưa có test riêng cho engulfing/rejection/micro_break
- `_smc_confirmation()`: chưa có test riêng
- `_confirm_m15_structure()`: chưa có test riêng
- `_confirm_m15_displacement()`: chưa có test riêng
- `_classify_sub_zone()`: chưa có test riêng

---

## B. HIỆU NĂNG

### ✅ Ưu điểm

- Tất cả hàm O(n) với n = số nến (thường < 50 nến H1/M15)
- `_find_swings_m15` dùng window scanning O(n×w) với w=11 — chấp nhận được
- Không có vòng lặp lồng phức tạp trong `build_trade_plan`
- `select_best_level`, `nearest_target`, `next_target` đều O(n) với n = số zones (< 20)
- Không có memory leak rõ ràng (pure functions)

### ❌ Nhược điểm / Rủi ro

Không phát hiện vấn đề hiệu năng đáng kể.

---

## C. KHẢ NĂNG BẢO TRÌ

### ✅ Ưu điểm

**1. Entry Ladder architecture rõ ràng**

Mỗi sub-zone (top/mid/bottom) có code path riêng, điều kiện xác nhận rõ ràng. Dễ mở rộng thêm sub-zone mới hoặc điều chỉnh yêu cầu xác nhận.

**2. TP cascade dễ theo dõi**

5 bậc TP được viết tuần tự, mỗi bậc có comment rõ ràng (`risk_engine.py:493-510`). Mỗi bậc có guard R:R riêng.

**3. Constants có tên cho một số giá trị**

```python
_ENTRY_AGGRESSIVENESS = 0.0
_SWING_SL_BUFFER_ATR = 0.15
_MIN_SL_DISTANCE_ATR = 0.5
_EQ_TP_MAX_RR = 3.0
_FIB_TP1 = 0.382
ENTRY_ZONE_ATR_MULT = 0.20
_ENTRY_ZONE_ATR_MIN = 0.10
_ENTRY_ZONE_ATR_MAX = 0.30
_ZONE_SL_BUFFER_ATR = 0.10
_ZONE_SL_CAP_RATIO = 1.5
```

### ❌ Nhược điểm / Rủi ro

- 20+ magic numbers không có constant (xem bảng trên)
- Code duplication: `build_trade_plan` có 2 nhánh BUY/SELL gần như đối xứng (200+ dòng), khó bảo trì khi thay đổi logic TP/SL
- Condition text hardcode tiếng Việt, không configurable

---

## D. BẢO MẬT

Không có attack surface đáng kể:
- Không nhận user input trực tiếp (symbol/side/price từ internal pipeline)
- Không có I/O, DB query, HTTP call
- `contract_size_for` đọc từ SYMBOL_CONFIG static dict, không injection risk

---

## Tổng hợp

### ✅ Ưu điểm (có dẫn chứng)

| # | Điểm mạnh | Dẫn chứng |
|---|-----------|-----------|
| 1 | Cascade TP 5 bậc + guard R:R từng bước | `risk_engine.py:493-510` |
| 2 | Entry Ladder top/mid/bottom với sizing + degrade | `entry_engine.py:255-351` |
| 3 | SL placement đa tầng (SMC → swing → ATR) với guard | `risk_engine.py:472-491` |
| 4 | Dynamic regime-aware parameters | `risk_engine.py:26-39, 422-429` |
| 5 | Position sizing với quote-to-USD conversion | `risk_engine.py:777-798` |
| 6 | M15 confirmation 2 lớp với score multiplier | `entry_engine.py:72-105, 200-208` |
| 7 | Backtest fallback cho M15 | `entry_engine.py:231-236` |
| 8 | Defensive type checking nhất quán | `entry_engine.py:115, 222-227, 526-527` |

### ❌ Nhược điểm / Rủi ro (có dẫn chứng)

| # | Vấn đề | Mức độ | Dẫn chứng |
|---|--------|--------|-----------|
| 1 | **UnboundLocalError**: `internal_structure` used before assignment ở 2 early-return paths | 🔴 High | `entry_engine.py:164, 177` |
| 2 | **Missing kwarg**: `internal_structure=internal_structure` bị đưa vào string thay vì kwarg | 🟡 Medium | `entry_engine.py:324-331` |
| 3 | 20+ magic numbers không constant trong Entry/SL/TP | 🟡 Medium | `entry_engine.py:86, 169-170, 467, 502-503` |
| 4 | Code duplication BUY/SELL trong `build_trade_plan` (200+ dòng mỗi nhánh) | 🟡 Medium | `risk_engine.py:450-589` |
| 5 | Entry aggressiveness=0.0 có thể cho R:R optimistic | 🟡 Medium | `risk_engine.py:58` |
| 6 | `_classify_sub_zone`, `_h1_confirmation`, `_smc_confirmation`, `_confirm_m15_*` không có test riêng | 🟡 Medium | 0 tests |
| 7 | Condition text hardcode tiếng Việt | 🟢 Low | `risk_engine.py:689-733` |

### Không đủ dữ liệu để kết luận

- Win rate phân theo sub-zone (top/mid/bottom) từ backtest
- Tỷ lệ TP1 bị giới hạn bởi `_EQ_TP_MAX_RR = 3.0`
- Fibonacci extension accuracy so với S/R zones
- Hiệu quả thực tế của M15 confirmation 2 lớp (strict/loose/none)

---

## Điểm tổng quan: **7.5 / 10** (đã cập nhật sau sửa)

| Tiêu chí | Điểm | Nhận xét |
|----------|------|----------|
| A. Tính đúng đắn | 7.5/10 | 2 bug đã sửa (UnboundLocalError + missing kwarg). Còn Entry aggressiveness=0.0 optimistic |
| B. Hiệu năng | 8.0/10 | O(n), không vòng lặp lồng, không memory leak |
| C. Khả năng bảo trì | 8.0/10 | 16 module-level constants thay thế toàn bộ magic numbers; sub-zone ladder rõ ràng |
| D. Bảo mật | N/A | Pure computation |

**Tổng quan (đã cập nhật):** Architecture của hệ thống Entry/SL/TP rất tốt — cascade TP 5 bậc với guard R:R, Entry Ladder sub-zone sizing, SL đa tầng với guard. 2 bug đã được sửa: (1) `UnboundLocalError` trong 2 early-return paths — thêm `internal_structure = None` ở đầu hàm, (2) missing `internal_structure` kwarg — đưa ra khỏi string thành kwarg thực sự. 16 module-level constants đã thay thế toàn bộ magic numbers trong `risk_engine.py` và `entry_engine.py`, giải quyết triệt để vấn đề `0.10` trùng lặp (3 ngữ cảnh → 3 tên riêng).
