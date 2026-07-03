# [ĐÁNH GIÁ ĐỘC LẬP] Code Review — Score Scenarios

> **Ngày đánh giá:** 2026-07-03
> **Người đánh giá:** Claude Opus 4.7
> **Phương pháp:** Đọc toàn bộ source code + chạy test thực tế, không dựa trên cảm tính

---

## Phạm vi đã đọc

| File | Dòng | Mức độ |
|------|------|--------|
| `core/signal_engine.py` | 1–590 | Toàn bộ |
| `core/final_score_engine.py` | 1–681 | Toàn bộ |
| `tests/test_signal_engine.py` | 1–128 | Toàn bộ |
| `tests/test_final_score_engine.py` | — | Toàn bộ |

---

## Kết quả chạy test thực tế

```
tests/test_signal_engine.py      → 4/4 PASSED ✅
tests/test_final_score_engine.py → 4/4 PASSED ✅
```

**8/8 tests pass.** Không có test fail.

---

## A. TÍNH ĐÚNG ĐẮN

### ✅ Ưu điểm

**1. Dynamic weights theo market regime — phản ánh đúng triết lý giao dịch**

`DYNAMIC_WEIGHTS` (`signal_engine.py:29-35`) thay đổi trọng số theo 4 regime:
- **Trending**: trend=25, SMC=15 — ưu tiên trend following
- **Ranging**: location=25, SMC=25 — ưu tiên biên range và SMC zones
- **Volatile**: risk=40 — ưu tiên quản trị rủi ro
- **Unknown**: phân bổ đều

**Dẫn chứng định lượng:**

| Regime | signal_score | trend | momentum | location | smc | risk | macro |
|--------|:-----------:|:-----:|:--------:|:--------:|:---:|:----:|:-----:|
| trending_up | 96 | 25 | 13 | 9 | 15 | 15 | 12 |
| ranging | 93 | 10 | 9 | 15 | 25 | 15 | 12 |
| volatile | 97 | 10 | 4 | 9 | 10 | 40 | 16 |
| unknown | 95 | 18 | 12 | 10 | 15 | 16 | 16 |

**2. Normalized scoring — chống "score deflation" khi thiếu dữ liệu**

```python
# signal_engine.py:132-140
non_macro_score = technical_scaled + risk_scaled
available_budget = max(0, 100 - macro_effective)
normalized_non_macro = int(non_macro_score * available_budget / non_macro_max)
```

Khi macro data không có (neutral 15/15), `macro_effective` chỉ đạt ~50% `macro_cap`. Không normalize → tổng điểm bị kéo xuống ~80-85 dù mọi thứ khác hoàn hảo. Cơ chế này scale phần non-macro để lấp đầy budget → `signal_score` luôn có ý nghĩa "tốt nhất có thể với dữ liệu hiện có".

**3. Layered scoring với modifier rõ ràng**

Thứ tự áp dụng: base score → normalized → macro modifier → CHOCH cap → return (`signal_engine.py:142-167`):
- Macro aligned: `+5 × confidence`
- Macro conflict: `-15 × confidence`
- CHOCH against direction: cap về `≤60`

Mỗi layer có reason code riêng, dễ debug.

**4. `_choose_one` — pattern đúng cho scoring có độ ưu tiên**

```python
# signal_engine.py:297-301
def _choose_one(candidates: list[tuple[bool, int]]) -> int:
    for condition, score in candidates:
        if condition:
            return score
    return 0
```

Điều kiện đầu tiên đúng sẽ thắng — tránh bug "cộng dồn tất cả điều kiện đúng" thường gặp trong scoring engine.

**5. Edge case handling không crash**

- SMC=None → `smc_quality=0`, `smc_reason` có text (`signal_engine.py:349-350`)
- macro_context=None → `macro_status="unclear"`, modifier=0 (`signal_engine.py:60-61`)
- `macro_confidence=0.0` → macro modifier tự động = 0 (`signal_engine.py:151,156`)
- `risk_score=0, macro_score=30` → vẫn tính bình thường, không divide-by-zero
- `entry_context=None` → bonus=0, không crash (`signal_engine.py:170`)

**6. `final_score_engine.py` — defensive programming xuất sắc**

- `safe_score()` xử lý `None`, `NaN`, `Inf`, string rỗng, non-numeric (`final_score_engine.py:87-110`)
- `normalize_weights()` chống sum=0, negative weights, missing keys (`final_score_engine.py:113-142`)
- `_is_valid_score_value()` dùng riêng cho fallback detection (`final_score_engine.py:408-428`)
- Docstring ghi "Never raises" — và code thực sự không raise

**7. Payload extraction linh hoạt**

`pick_signal_score()`, `pick_evidence_score()`, `pick_execution_quality_score()` — mỗi hàm có 3-4 fallback path, đọc được từ nhiều cấu trúc payload khác nhau (`final_score_engine.py:436-548`).

---

### ❌ Nhược điểm / Rủi ro

**[MAGIC NUMBERS — 🟡 MEDIUM] 30+ số hardcode trong scoring**

| Dòng | Ví dụ | Vai trò |
|------|-------|--------|
| 114-117 | `25, 20, 25, 15` | Component max scores (clamp ceilings) |
| 151, 156 | `-15, 5` | Macro modifier multipliers |
| 165 | `60` | CHOCH cap threshold |
| 184 | `12.5` | Entry bonus multiplier (scale 0-8 → 0-100) |
| 218-224 | `80, 65, 50` | Rating thresholds |
| 232-245 | `8, 5, 5, 5, 2` | Trend alignment point values |
| 263-283 | `8, 6, 3, 0, 10, 6, 3, 5` | RSI + MACD point values |
| 338-344 | `3, 5, 5, 3` | Location bonus/penalty thresholds |
| `DYNAMIC_WEIGHTS` | 20 số | Regime weight matrix |

Không có module-level constant. So sánh: `smc_context.py` có 30 constants (Phase 7), `risk_engine.py` có 8 (Phase 8b).

**[DEAD COMPUTATION — 🟡 MEDIUM] `entry_quality_bonus` tính nhưng không cộng vào `signal_score`**

```python
# signal_engine.py:169-184
entry_quality_bonus = 0
...
entry_quality_bonus = int(clamp(entry_quality_bonus * 12.5, 0, 100))

return {
    "signal_score": total,               # ← KHÔNG bao gồm entry_quality_bonus
    "entry_quality_bonus": entry_quality_bonus,  # ← trả về riêng, không ai đọc
}
```

`entry_quality_bonus` được tính kỹ lưỡng (sub-zone + distance + spread + direction, scale 0-100) nhưng **không được cộng vào `signal_score`**. `analysis_pipeline.py` không đọc field này trong `_step_score_scenarios()`. Đây là dead computation — hoặc quên tích hợp, hoặc tính năng chưa hoàn thiện.

**[LOGIC GAP — 🟡 MEDIUM] MACD falling + RSI rising = phân kỳ, nhưng vẫn được cộng điểm**

```python
# signal_engine.py:269-275 (BUY MACD)
macd_score = _choose_one([
    (now > 0 and now > prev > prev2, 10),   # strongest
    (now < 0 and now > prev > prev2, 6),    # turning up
    (now > prev, 3),                         # just rising
    (now > 0 and now < prev, 5),             # positive but falling ← VẪN +5 ĐIỂM
])
```

Điều kiện cuối cùng `now > 0 and now < prev` = MACD dương nhưng đang giảm → vẫn được +5 điểm. Nếu đồng thời RSI đang tăng (+8), tổng = 13/20. Nhưng **MACD falling + RSI rising = bearish divergence** — tín hiệu đảo chiều, đáng lẽ phải bị phạt. Code hiện tại không detect divergence, cộng điểm cho cả 2 hướng.

**[DESIGN — 🟢 LOW] `DYNAMIC_WEIGHTS` không validate tổng = 100**

Tất cả 4 bộ weights hiện tại có tổng = 100, nhưng không có assertion hoặc test. Nếu thêm regime mới với tổng ≠ 100, normalized scoring cho ra điểm sai mà không có cảnh báo.

**[CODE DUPLICATION — 🟢 LOW] `trend_alignment_score` BUY/SELL gần như đối xứng**

```python
# signal_engine.py:227-247 — 2 nhánh dài 10 dòng, chỉ khác dấu > vs <
if side == "buy":
    return sum([8 if t["ema50_d1"] > t["ema200_d1"] else 0, ...])
return sum([8 if t["ema50_d1"] < t["ema200_d1"] else 0, ...])
```

Có thể gộp với tham số `direction = 1/-1`.

**[TEST GAP — 🟡 MEDIUM] 0 tests cho 8 component scoring functions**

4 tests trong `test_signal_engine.py` chỉ test integration (`score_scenario` + `calculate_direction_bias`). Không có test riêng cho:

| Hàm | Tests | Risk |
|-----|:-----:|------|
| `trend_alignment_score` | 0 | Core scoring (0-25) |
| `momentum_alignment_score` | 0 | Core scoring (0-20) |
| `location_quality_score` | 0 | Core scoring (0-25) |
| `smc_quality_score` | 0 | Core scoring (0-15) |
| `calc_risk_condition` | 0 | Risk scoring (0-15) |
| `score_rating` | 0 | User-facing label |
| `_resolve_regime_key` | 0 | Regime routing |
| `_detect_macro_status` | 0 | Macro alignment |

---

## B. HIỆU NĂNG

### ✅ Ưu điểm

- Toàn bộ `score_scenario()` là O(1) — pure computation trên dict fields, không loop, không I/O
- `DYNAMIC_WEIGHTS` là static dict lookup
- `_choose_one` early-exit — dừng ở điều kiện đầu tiên đúng
- `final_score_engine.py` — toàn bộ O(1), không vòng lặp

### ❌ Nhược điểm

Không phát hiện vấn đề hiệu năng. Module này là pure computation nhẹ nhất trong toàn bộ pipeline.

---

## C. KHẢ NĂNG BẢO TRÌ

### ✅ Ưu điểm

**1. Dynamic weights tách biệt khỏi scoring logic**

`DYNAMIC_WEIGHTS` là static dict ở đầu file — muốn điều chỉnh trọng số không cần đọc code scoring.

**2. Normalized scoring có comment giải thích rõ ràng**

```python
# signal_engine.py:128-131
# When macro data is unavailable (neutral 15/15), macro_effective only reaches
# ~50% of macro_cap. Without normalization, total scores are artificially depressed.
```

Comment giải thích WHY, không chỉ WHAT.

**3. `final_score_engine.py` — module docstring đầy đủ**

Mô tả design principles, public API, weight evolution strategy (`final_score_engine.py:1-29`).

### ❌ Nhược điểm

- 30+ magic numbers không constant
- `entry_quality_bonus` dead code không có comment giải thích
- 0 tests cho 8 component functions

---

## D. BẢO MẬT

Không có attack surface: pure computation trên internal data structures. Không I/O, không user input.

---

## Tổng hợp

### ✅ Ưu điểm (có dẫn chứng)

| # | Điểm mạnh | Dẫn chứng |
|---|-----------|-----------|
| 1 | Dynamic weights 4 regime — phản ánh triết lý giao dịch | `signal_engine.py:29-35` |
| 2 | Normalized scoring chống deflation khi thiếu macro | `signal_engine.py:128-140` |
| 3 | Layered modifier (macro → CHOCH) với reason code | `signal_engine.py:144-167` |
| 4 | `_choose_one` — pattern đúng cho priority scoring | `signal_engine.py:297-301` |
| 5 | `final_score_engine` defensive programming xuất sắc | `final_score_engine.py:87-110, 113-142, 408-428` |
| 6 | Payload extraction linh hoạt (3-4 fallback paths) | `final_score_engine.py:436-548` |
| 7 | Edge case: None SMC, None macro, confidence=0 — không crash | `signal_engine.py:60-61, 170, 349-350` |

### ❌ Nhược điểm / Rủi ro (có dẫn chứng)

| # | Vấn đề | Mức độ | Dẫn chứng |
|---|--------|--------|-----------|
| 1 | 30+ magic numbers trong scoring — không constant | 🟡 Medium | `signal_engine.py:114-117, 151, 165, 184, 218-224, 232-283, DYNAMIC_WEIGHTS` |
| 2 | `entry_quality_bonus` dead computation — không cộng vào signal_score | 🟡 Medium | `signal_engine.py:169-184` |
| 3 | MACD falling + RSI rising → divergence không bị phạt | 🟡 Medium | `signal_engine.py:269-275, 261-267` |
| 4 | 0 tests cho 8 component scoring functions | 🟡 Medium | 0 tests |
| 5 | `DYNAMIC_WEIGHTS` không validate tổng = 100 | 🟢 Low | `signal_engine.py:29-35` |
| 6 | `trend_alignment_score` code duplication BUY/SELL | 🟢 Low | `signal_engine.py:227-247` |

### Không đủ dữ liệu để kết luận

- Tương quan `signal_score` với win rate thực tế từ backtest
- Phân phối điểm trên 28 symbols (có bị cluster ở 50-70 không)
- Hiệu quả của normalized scoring khi có đủ macro data

---

## Điểm tổng quan: **7.0 / 10**

| Tiêu chí | Điểm | Nhận xét |
|----------|------|----------|
| A. Tính đúng đắn | 7.0/10 | Không crash, edge case tốt. `entry_quality_bonus` dead code + divergence không detect |
| B. Hiệu năng | 8.5/10 | O(1) toàn bộ — pure computation, không loop, không I/O |
| C. Khả năng bảo trì | 5.5/10 | Dynamic weights + normalized scoring rõ ràng, nhưng 30+ magic numbers + 0 test cho 8 component functions |
| D. Bảo mật | N/A | Pure computation |

**Tổng quan:** Hệ thống scoring có architecture tốt nhất trong các module đã đánh giá — dynamic weights theo regime, normalized scoring chống deflation, layered modifier với reason code. `final_score_engine.py` là hình mẫu defensive programming. Điểm yếu chính: (1) `entry_quality_bonus` được tính nhưng không dùng → dead code, (2) MACD/RSI divergence không được phát hiện, (3) 30+ magic numbers chưa extract, (4) 0 test cho 8 component scoring functions.
