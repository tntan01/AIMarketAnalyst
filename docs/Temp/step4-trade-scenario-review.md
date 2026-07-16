# Đánh giá Step 4 — Xây dựng Trade Scenario (Entry/SL/TP)

> Nguồn: `core/risk_engine.py` (`build_trade_plan`, `build_scenarios`), `core/entry_engine.py` (`evaluate_entry`), `core/analysis_pipeline.py` (fallback scenario), `controllers/scanner_controller.py` (`_execute_auto_trades`), `core/scanner.py` (`enrich_scanner_row`), `ui/screens/scanner_screen.py` (table R:R), `ui/screens/scanner_detail_screen.py` (detail RR range)

## Bối cảnh

Step 4 nhận điểm số buy/sell từ Step 3, chọn vùng giá (SMC zone hoặc S/R zone), rồi tính ra Entry zone, Stop Loss, Take Profit (cascade 5 bước), R:R, và position sizing. Đây là bước **quan trọng nhất về mặt rủi ro thực tế** — mọi lỗi ở đây đều biến thành tiền mất thật khi auto-trade bật.

---

## Ưu điểm

### 1. Từ chối bịa TP khi dùng SMC zone thật (`use_preferred`)
Khi entry dựa trên SMC zone (order block/demand-supply) và không tìm được target cấu trúc thật (equal high/low, S/R, Fib, swing), code **để `tp1 = None`** thay vì tự vẽ ra TP giả:
```python
if use_preferred:
    tp1 = None   # không có TP thật → để trống, không dùng fallback nhân tạo
```
Đây là kỷ luật kỹ thuật tốt, đúng với nguyên tắc "an toàn" đã ghi trong `product_spec.md`: *AI/hệ thống không được tự bịa entry/SL/TP*.

### 2. TP cascade nhiều lớp, ưu tiên theo độ tin cậy
Thứ tự tìm TP: **Equal highs/lows (liquidity) → S/R zone → Fibonacci extension → Swing gần nhất**, dừng ngay khi tìm được target đạt RR tối thiểu. Cách tiếp cận này hợp lý về mặt price action — ưu tiên các vùng thanh khoản thật trước khi dùng công cụ toán học (Fib) mang tính suy diễn.

### 3. Nhiều lớp guard chống trade plan vô lý
- `min_stop_distance` = max(ATR×0.20, spread×N) — chặn SL quá sát khiến bị stop-out bởi nhiễu giá
- SL phải nằm ngoài entry zone tối thiểu 0.10×ATR (`sl_floor`/`sl_ceiling`)
- `_EQ_TP_MAX_RR = 3.0` — chặn TP dựa trên equal-level nếu xa bất hợp lý (RR giả tạo cao)
- `_TP2_MIN_GAP_ATR` — TP2 phải cách TP1 tối thiểu để có ý nghĩa, tránh 2 TP dính sát nhau

### 4. Trọng số SL/vùng zone thích ứng theo regime thị trường
`REGIME_SL_MULTIPLIER` và `REGIME_ZONE_DISTANCE_MULT` khác nhau cho trending/ranging/volatile — trend cho phép SL rộng hơn (0.65) và tìm zone xa hơn (3.5×ATR), range dùng SL chặt hơn tương đối. Đây là tư duy đúng: không dùng 1 công thức cứng cho mọi điều kiện thị trường.

### 5. Position sizing gắn liền với chất lượng entry (Entry Ladder)
`size_multiplier` từ `entry_ladder` (Step 4 detail) làm giảm khối lượng lệnh nếu giá đang ở vùng entry kém lý tưởng (top zone = 0.4×, bottom zone = 1.0×). Cơ chế này hiếm gặp ở các bot đơn giản — nó tự động risk-scale theo xác suất setup, không phải all-or-nothing.

### 6. Kiểm tra lại giá trước khi bắn lệnh auto-trade
`_execute_auto_trades()` có bước xác nhận `current_price` (lấy từ `technical.price`) còn nằm trong `entry_zone` trước khi gọi `place_market_order()` — tránh vào lệnh khi giá đã chạy khỏi vùng dự kiến giữa lúc scan xong và lúc gửi lệnh.

### 7. Hiển thị dải RR (risk_reward_range) trên cả Scanner Table và Detail Screen (MỚI 2026-07-16)
`build_trade_plan()` trả về `risk_reward_range` với 3 mức best/base/worst tương ứng 3 vị trí khớp lệnh trong entry zone. Field này được hiển thị ở:
- **Scanner Table** (`ui/screens/scanner_screen.py`): cột R:R hiển thị dạng `"5.6 (2.9–5.6)"` — best case + khoảng worst–best
- **Detail Screen** (`ui/screens/scanner_detail_screen.py`): Hero bar, Dialog card, và Gate checks đều hiển thị dải RR
- **Data flow**: `core/scanner.py` → row dict → `controllers/scanner_controller.py` → candidates → UI
Người dùng thấy ngay được RR có thể co giãn từ đâu đến đâu, không bị ảo tưởng bởi 1 con số best-case duy nhất.

---

## Nhược điểm

### 1. ~~Trùng lặp code buy/sell rất lớn (maintainability risk)~~ ✅ ĐÃ SỬA (2026-07-16)
`build_trade_plan()` viết gần như 2 bản sao gương nhau cho `side == "buy"` và `else` (sell) — khoảng 150 dòng lặp lại logic tương tự chỉ đổi dấu. Rủi ro thực tế: khi sửa bug hoặc thêm rule mới cho 1 chiều, rất dễ quên áp dụng cho chiều còn lại (asymmetric bug). Đã có dấu hiệu việc này từng xảy ra — file `tests/test_tp2_min_gap_fix.py` và `tests/diagnose_rr_smc.py` cho thấy lịch sử phải vá riêng logic TP2/RR.

	**Đã refactor ngày 2026-07-16:** Gộp 2 nhánh buy/sell thành 1 luồng logic duy nhất dùng direction sign (`sign = 1` cho buy, `-1` cho sell). Giảm 142 dòng (-43 net), toàn bộ phép so sánh và phép tính dùng `sign` thay vì if/else riêng cho từng chiều. Verified bằng baseline snapshot 8 fixtures khớp 100% field-by-field + 12 test symmetry mới. File: `core/risk_engine.py:459-567`, tests: `tests/test_build_trade_plan_symmetry.py`.

	**Sửa kèm:** Test `test_entry_zone_atr_mult_is_020` → `test_entry_zone_atr_mult_is_035` (hằng số đã đổi 0.20→0.35 từ commit `0e06700` nhưng test chưa được cập nhật).

### 2. Rất nhiều hằng số ATR-multiplier "hard-code" thiếu căn cứ thực nghiệm rõ ràng
Đếm được **hơn 15 hằng số** kiểu `_ZONE_SL_BUFFER_ATR = 0.10`, `_SWING_SL_BUFFER_ATR = 0.15`, `_MIN_SL_DISTANCE_ATR = 0.5`, `_WATCH_ZONE_ATR_TREND = 0.40`... Không có comment nào chỉ ra chúng được tối ưu từ dữ liệu backtest thật hay chỉ là "cảm giác hợp lý" của người viết. Đây chính là kiểu **tham số dễ overfit** — khớp với lo ngại "overfitting risk" mà mày từng ghi nhận với `build_fallback_scenario` và thiếu walk-forward validation. Nếu chưa chạy walk-forward cho từng hằng số này, không có gì đảm bảo chúng còn tối ưu ngoài giai đoạn dữ liệu đã test.

### 3. ~~`entry_aggressiveness = 0.0` cố định → luôn giả định lệnh khớp ở giá tốt nhất~~ ✅ ĐÃ CẢI THIỆN (2026-07-16)
```python
_ENTRY_AGGRESSIVENESS = 0.0        # vẫn dùng cho DISPLAY (mép gần, best-case)
_TP_SELECTION_AGGRESSIVENESS = 0.5 # dùng để CHỌN/DUYỆT TP (trung điểm, thận trọng hơn)
```
Entry vẫn hiển thị ở **mép gần nhất** (giữ nguyên UI/backtest) nhưng TP được **chọn dựa trên trung điểm** entry zone — tức 1 target chỉ được chấp nhận nếu đạt RR>=1 ngay cả khi lệnh khớp ở giữa zone, không chỉ mép tốt nhất. Điều này giảm rủi ro chọn TP quá dễ dãi (gần) so với thực tế khớp lệnh.

**Thêm `risk_reward_range`:** Dict trả về có thêm field `risk_reward_range = {"best": RR_mép_gần, "base": RR_trung_điểm, "worst": RR_mép_xa}` — cho phép UI hiển thị dải RR thay vì 1 con số duy nhất. File: `core/risk_engine.py:613-645`, tests: `tests/test_tp_selection_anchor.py`, `tests/test_risk_reward_range.py`.

### 4. Fallback scenario (khi không có scenario thật) dùng số liệu hoàn toàn tùy ý
Trong `analysis_pipeline.py`, khi Step 4 không tạo được scenario nào (`self._scenarios` rỗng), hệ thống tự tạo:
```python
sl = price - atr * 1.2 (buy)
tp = price + atr * 2.4
risk_reward = "1:2.0"  # luôn luôn cố định
```
Dù bị chặn khỏi auto-trade và Telegram, **vẫn hiển thị trong bảng Scanner** với RR "1:2.0" nhìn như một con số phân tích thật. Người dùng lướt nhanh bảng rất dễ nhầm đây là 1 setup có cấu trúc, trong khi nó chỉ là placeholder ATR×const.

### 5. Việc re-check giá trước khi đặt lệnh dùng dữ liệu "cũ" (snapshot lúc scan)
`current_price` trong `_execute_auto_trades()` lấy từ `technical.price` — tức giá tại **thời điểm phân tích**, không phải tick mới nhất ngay trước khi gửi lệnh market order. Với chu kỳ auto-scan vài chục giây đến vài phút, giữa lúc scan xong và lúc thực sự gửi lệnh vẫn có độ trễ; nếu thị trường biến động nhanh trong khoảng đó, guard này không bắt được.

### 6. Không tính đến giới hạn thực tế của broker (stop level / freeze level)
`min_stop_distance` chỉ dựa trên ATR và spread, không kiểm tra `SYMBOL_INFO.trade_stops_level` (khoảng cách tối thiểu broker cho phép đặt SL/TP cách giá hiện tại) hay `freeze_level`. Về lý thuyết plan có thể hợp lệ theo logic nội bộ nhưng vẫn bị MT5 từ chối lúc gửi lệnh thật (`invalid stops`).

### 7. Buffer SL cố định theo % ATR, không theo chất lượng/độ rộng thực của zone
`_ZONE_SL_BUFFER_ATR = 0.10` áp dụng như nhau cho mọi SMC zone bất kể zone đó rộng hay hẹp, mới hay cũ, test nhiều hay ít lần. Một zone rộng (biến động cao) và zone hẹp (biến động thấp) đang được đối xử SL-buffer giống hệt nhau về tỷ lệ ATR — có thể dẫn tới SL quá sát ở zone chất lượng thấp hoặc quá xa ở zone chất lượng cao.

### 8. Cascade TP dừng ở "target đầu tiên đạt RR", không so sánh chất lượng giữa các lựa chọn
Logic hiện tại là **thỏa mãn điều kiện đầu tiên** (equal-high → S/R → Fib → swing) chứ không phải "chọn target tốt nhất trong các lựa chọn khả dụng". Có thể một Fib target ở xa hơn/tin cậy hơn bị bỏ qua chỉ vì một equal-level gần hơn (nhưng yếu hơn) đã thỏa mãn điều kiện RR trước.

---

## Đề xuất nâng cấp

### Ưu tiên cao

1. **✅ ĐÃ HOÀN THÀNH (2026-07-16) — Refactor buy/sell thành 1 hàm dùng dấu (`sign = 1 nếu buy, -1 nếu sell`)**
   Đã gộp 2 nhánh buy/sell trong `build_trade_plan()` thành 1 luồng logic duy nhất. Giảm 142 dòng (-43 net). Approach: direction sign dùng cho mọi phép so sánh (watch zone, SL, TP guard, entry zone boundary). Verified: 8 fixture baseline snapshot khớp 100% + 12 test symmetry + toàn bộ test suite cũ pass. File: `core/risk_engine.py:459-567`, tests: `tests/test_build_trade_plan_symmetry.py`.

2. **Walk-forward hoặc grid-search cho các hằng số ATR-multiplier quan trọng nhất**
   Ưu tiên: `_MIN_SL_DISTANCE_ATR`, `REGIME_SL_MULTIPLIER`, `_ZONE_SL_BUFFER_ATR`, `entry_aggressiveness`. Chạy walk-forward trên nhiều giai đoạn thị trường khác nhau (trending 2023, range 2024...) để xem các giá trị hiện tại có ổn định hay chỉ tốt trên 1 giai đoạn cụ thể.

3. **✅ ĐÃ LÀM 1 PHẦN (2026-07-16) — Tách anchor TP selection khỏi display; còn lại: backtest so sánh**
   Đã tách `_TP_SELECTION_AGGRESSIVENESS = 0.5` (chọn TP) khỏi `_ENTRY_AGGRESSIVENESS = 0.0` (display). TP được chọn thận trọng hơn (từ trung điểm zone). Đã thêm `risk_reward_range` hiển thị dải best/base/worst. Việc còn lại: chạy song song 2 backtest để đo chênh lệch equity curve giữa giả định mép gần vs mô phỏng fill-rate thực tế.

### Ưu tiên trung bình

4. **Đánh dấu rõ ràng hơn cho Fallback scenario trên UI**
   Hiện `entry_zone_source = "fallback"` đã có nhưng nên hiển thị nổi bật (icon cảnh báo, màu khác, chữ "Không có cấu trúc rõ ràng — chỉ tham khảo") ngay trên bảng Scanner thay vì để RR "1:2.0" trông giống số liệu thật.

5. **Kiểm tra `trade_stops_level`/`freeze_level` từ MT5 trước khi coi 1 plan là hợp lệ**
   Thêm 1 gate nhỏ ở Step 4 hoặc Step 6 để early-reject các plan có SL/TP quá sát theo tiêu chuẩn broker, tránh lỗi "invalid stops" khi auto-trade thật.

6. **Re-fetch tick giá mới nhất ngay trước khi gọi `place_market_order()`**
   Thay vì dùng `technical.price` (snapshot), gọi thêm 1 lần lấy bid/ask hiện tại từ MT5 ngay trước lúc gửi lệnh để giảm độ trễ giữa "xác nhận entry zone" và "gửi lệnh thật".

### Ưu tiên thấp / dài hạn

7. **Buffer SL/zone theo chất lượng zone thay vì % ATR cố định**
   Ví dụ: zone có `zone_score` cao (freshness tốt, ít test) dùng buffer nhỏ hơn; zone score thấp dùng buffer lớn hơn để bù rủi ro breakout giả.

8. **So sánh nhiều target khả dụng thay vì dừng ở target đầu tiên đạt RR**
   Có thể tính điểm chất lượng cho từng loại target (liquidity > S/R > Fib > swing) rồi chọn target có `RR × confidence` cao nhất thay vì thứ tự ưu tiên cứng.

---

## Tóm tắt

Step 4 có **kỷ luật kỹ thuật tốt về nguyên tắc** (không bịa TP, nhiều guard chống plan vô lý, regime-aware). Đến 2026-07-16, **3 vấn đề lớn đã được giải quyết**:
1. ✅ Refactor buy/sell dùng direction sign — hết trùng lặp, giảm 43 dòng
2. ✅ Tách anchor TP selection (0.5) khỏi display (0.0) — TP được chọn thận trọng hơn
3. ✅ Thêm `risk_reward_range` best/base/worst hiển thị trên cả Scanner Table + Detail Screen

**Rủi ro lớn nhất còn lại**: mật độ tham số ATR-multiplier cao chưa có bằng chứng walk-forward — đúng như lo ngại overfitting đã từng ghi nhận. Ưu tiên tiếp theo: walk-forward test các hằng số SL/TP quan trọng nhất + backtest so sánh fill-rate thực tế.
