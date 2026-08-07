# Báo cáo review Bước 7 — VIX theo cặp tiền

**Ngày review**: 2026-08-07
**Phạm vi**: thay đổi Bước 7, đã commit trong `d9eb515` (branch `buoc5-review-fixes-va-buoc6-buoc7`) — `core/vix_pair_backtest.py` (mới, 738 dòng), `core/correlation_check.py` (+151: `_vix_score(symbol, side, vix_candles)` pair-aware), `data/vix_pair_sensitivity.json` (mới, 31 cặp), `tests/test_vix_pair_sensitivity.py` (mới, 48 test)
**Phương pháp**: khảo sát phạm vi, đọc trực tiếp backtest engine + scoring + mapping JSON, tự tính tay kiểm chứng công thức, chạy full suite (2560 passed, 0 failed), workflow review 18 agent (5 reviewer độc lập theo 5 chiều → merge đọc code thật kiểm chứng → xác minh đối kháng từng cụm). Kết quả: **10/10 cụm finding được verifier xác nhận** (confidence high), không cụm nào bị bác.

---

## 1. Đánh giá tổng quan

Phần "máy móc" của Bước 7 viết cẩn thận và test kỹ: scope W2 sạch tuyệt đối (5/5 reviewer xác nhận chỉ `_vix_score` đổi, `check_vix_context`/VIX chẩn đoán giữ nguyên), không có `if JPY` trong scoring, fallback về flat khi thiếu map, symbol slash-form khớp map keys (đã chạy thử xác nhận nạp đủ 31 cặp), bonus VIX<15 không đụng, 48 test không flaky.

**Nhưng yêu cầu chặn của spec — W4 "phải backtest xác nhận trong data của mình TRƯỚC KHI code" — bị vi phạm hoàn toàn**: scoring live đang chạy trên mapping **seed viết tay, 0 ngày dữ liệu**, và vòng kiểm chứng data (W5→W6→W7) chưa khép ở bất kỳ khâu nào. Thêm một bug công thức nghiêm trọng: **trade ngược flow nguy hiểm nhất lại bị phạt nhẹ nhất** — bug này tồn tại độc lập với data, map thật hay seed đều dính.

**Trạng thái test**: full suite 2560 passed, 8 skipped, 17 xfailed, 0 failed.

---

## 2. Findings theo mức độ

### 🔴 CRITICAL 1 — W4 vi phạm chặn: scoring live chạy trên seed map 0 ngày dữ liệu, không có flag tắt

- **Yêu cầu vi phạm**: W4 (kéo theo W3, W9)
- **File**: `data/vix_pair_sensitivity.json` (meta), `core/correlation_check.py:54-59`, `core/vix_pair_backtest.py:403-415`

Mapping đang điều chỉnh điểm của cả 31 cặp là output tất định của dict viết tay `CURRENCY_APPRECIATION_ON_VIX_UP` (JPY 0.45, CHF 0.30, USD 0.10, AUD −0.35, NZD −0.32, CAD −0.25... → `pair_corr = base_appreciation − quote_appreciation`: AUD/JPY = −0.80, USD/JPY = −0.35 — khớp từng số trong JSON). Meta tự khai: `is_seed: true`, `vix_data_points: 0`, `lookback_days: 0`, `data_start: "N/A (seed data)"`, warning `"SEED DATA dựa trên kiến thức thị trường, CHƯA được backtest xác nhận"`.

Chuỗi bằng chứng:
- Grep toàn repo: **0 production caller** của `compute_vix_pair_sensitivity`/`get_vix_sensitivity_map`/`save_sensitivity_map` (chỉ tests) — backtest chưa từng chạy.
- Không có settings flag nào để tắt pair-aware VIX (grep `config/settings.py` + `settings_service.py`: 0 hit).
- Chính code tự nhận map không hợp lệ: `is_sensitivity_map_stale()` trả `True` cho mọi seed map (`vix_pair_backtest.py:533-535`) — nhưng production loader `_load_vix_sensitivity` không bao giờ hỏi, chỉ `logger.warning` rồi vẫn return map.
- Nhóm test F (`test_jpy_pairs_are_safe_haven`, `test_aud_nzd_pairs_risk_sensitive`) ghim chính giả thuyết chưa kiểm chứng thành acceptance criteria.

Chạy thật với VIX=30 (đã kiểm chứng):
| Trade | Flat cũ | Pair-aware (seed) |
|---|---|---|
| AUD/JPY sell | −5.0 | **−0.0** |
| USD/JPY sell | −5.0 | **−1.0** |
| USD/JPY buy | −5.0 | −3.8 |
| EUR/USD buy/sell | −5.0 | −5.0 |

Đây đúng là kịch bản W9 cảnh báo: nếu thị trường rơi vào regime 2022-2024 (BOJ phân kỳ, JPY yếu kéo dài dù risk-off — phản ví dụ ghi ngay trong spec), hệ thống **giảm phạt phía SELL JPY crosses (phía thua trong regime đó)** với 0 ngày dữ liệu chứng minh — bias hệ thống đi thẳng vào điểm macro.

**Fix**:
1. Thêm flag `vix_pair_aware_enabled` mặc định **False** vào AdvancedSettings (đúng pattern cờ Bước 5/6: loader đọc key, checkbox UI, save carry-over).
2. Gate production: `_load_vix_sensitivity` (hoặc caller) gọi `is_sensitivity_map_stale()` + check `is_seed` — nếu seed/stale thì trả `{}` để về flat scoring thay vì warning rồi vẫn dùng.
3. Đổi test nhóm F thành "seed sanity" (không phải nghiệm thu giả thuyết thị trường) hoặc skip khi chưa có data xác nhận.
4. Chỉ bật pair-aware scoring sau khi backtest trên data thật xác nhận hypothesis — đúng trình tự W4/W9.

---

### 🔴 CRITICAL 2 — Công thức penalty ngược flow sụp về gần 0 khi |corr| cao: trade nguy hiểm nhất bị phạt nhẹ nhất

- **Yêu cầu vi phạm**: W3 ("AUD/NZD phạt nặng hơn")
- **File**: `core/correlation_check.py` — nhánh ngược flow của `_vix_score`: `effective_factor = factor * 0.8 + 0.2`

Đã tự tính tay kiểm chứng với VIX=26 (base penalty −5):

| Trade | corr | factor | eff | Penalty |
|---|---|---|---|---|
| **BUY AUD/JPY** (ngược flow — cược chống lại cú rơi risk-off rất dễ đoán) | −0.8 | 0.0 | 0.2 | **−1.0** |
| BUY EUR/USD (indeterminate) | −0.10 | 1.0 | 1.0 | **−5.0** |
| BUY USD/JPY (ngược flow vừa) | −0.35 | 0.69 | 0.752 | −3.76 |
| SELL AUD/JPY (thuận flow) | −0.8 | 0.0 | 0.0 | −0.0 ✓ đúng chủ đích W1 |

`sensitivity_factor` được thiết kế với nghĩa "VIX giải thích tốt chuyển động của cặp → giảm phạt" — đúng cho phía **thuận** flow (trade đi cùng dòng chảy risk-off, ít rủi ro bất ngờ), nhưng khi áp cho phía **ngược** flow, nó làm penalty của trade nguy hiểm nhất sụp về sàn 0.2: corr càng mạnh, cược ngược dòng chảy càng được phạt nhẹ. W3 yêu cầu AUD/NZD (risk-on) bị phạt nặng hơn khi cược ngược risk-off — công thức hiện tại làm ngược lại.

Lưu ý: bug này **độc lập với data** — thay map backtest thật vẫn dính. Chiều giảm nhẹ (verifier runtime): VIX contribution vẫn luôn ≤ 0, không bao giờ thành điểm cộng, bất đối xứng tổng thể giữ nguyên — nhưng thứ hạng so sánh giữa các setup trong scanner bị đảo đúng chỗ nguy hiểm nhất.

**Fix tối thiểu**: nhánh ngược flow → `effective_factor = 1.0` (giữ nguyên base penalty, không giảm theo factor). Đúng W3 hơn: `effective_factor = 1.0 + (1.0 − factor) × K` với K ∈ [0.2, 0.5] — corr càng mạnh, cược ngược flow phạt càng nặng (clamp tổng adjustment trong [-6,+5] nếu muốn giữ trần).

---

### 🟠 MAJOR 3 — Save một đằng load một nẻo: seed trong repo che vĩnh viễn map backtest thật — vòng W5→W6 gãy

- **File**: `core/correlation_check.py:34-43` (đọc repo `data/` TRƯỚC, `%APPDATA%` sau) vs `core/vix_pair_backtest.py:55-63, 571` (ghi mặc định vào `app_data_dir()` = `%APPDATA%`)
- Thực nghiệm của verifier: đặt map backtest thật (251 data points) vào `%APPDATA%` → loader vẫn trả seed repo với `data_points=0`, corr −0.35. Ngay cả khi làm đúng W5, kết quả không bao giờ được dùng.
- Comment `vix_pair_backtest.py:60` ("app_data_dir() trả về ./data trong project") sai sự thật (config/paths.py: `%APPDATA%/ai-market-analyst`).
- Góc tăng nặng: PyInstaller spec không bundle sensitivity file theo cách nhất quán — nếu bỏ file khỏi repo thì bản đóng gói về flat, hành vi khác bản dev; giữ file trong repo thì seed thắng mãi mãi.

**Fix**: thống nhất một convention — khuyến nghị đọc/ghi đều tại `<repo>/data/vix_pair_sensitivity.json` (khớp Bước 5, `.gitignore` có nghĩa, tooling biết chỗ tìm); hoặc loader ưu tiên `%APPDATA%` TRƯỚC repo. Sửa comment sai.

### 🟠 MAJOR 4 — W5 không có điểm thực thi: app chỉ fetch VIX 5 ngày, không tồn tại runner

- **File**: `services/market_data_service.py:122` (`fetch_macro_correlation_context(period="5d")` — nguồn VIX candles duy nhất), `core/vix_pair_backtest.py` (engine cần ≥20 nến, mặc định 252)
- Không có script/UI/CLI nào gọi `compute_vix_pair_sensitivity()` với data thật; người dùng muốn chạy backtest cũng không có đường.
- Infra có sẵn (yfinance qua `MacroMarketCache`), chỉ cần runner với `period="2y"` cho `^VIX` + 31 cặp.

**Fix**: viết runner (vd `scripts/run_vix_pair_backtest.py` hoặc nút trong UI) — fetch VIX + pair daily, gọi `compute_vix_pair_sensitivity(lookback_days=252)`, `save_sensitivity_map`, in summary để đọc kết quả trước khi bật flag.

### 🟠 MAJOR 5 — Backtest align ΔVIX vs pair returns theo VỊ TRÍ, không theo NGÀY — correlation artifact khi chạy data thật

- **File**: `core/vix_pair_backtest.py:290-293` (`vix_changes[-min_len:]` / `pair_returns[-min_len:]`), `:81-82` (`_daily_pct_changes` bỏ bar close≤0 bằng `continue`)
- VIX đóng cửa theo giờ Mỹ, FX chạy 24/5, lịch nghỉ khác nhau → 2 chuỗi tail-align có thể lệch ngày; bar bị bỏ làm index 2 chuỗi lệch nhau im lặng. Thực nghiệm của verifier: dịch chuỗi +1 ngày lịch cho correlation gần như y hệt mà warnings rỗng; zero-close giữa chuỗi làm corr từ −0.999 thành −0.505 không cảnh báo.
- `candle.time` chỉ được dùng để hiển thị `data_start/data_end` (:245-246), không dùng để join.

**Fix**: align theo ngày — build dict `{date: pct_change}` cho mỗi chuỗi, join trên intersection của dates, yêu cầu min overlap đủ lớn; log số ngày bị loại mỗi phía.

### 🟠 MAJOR 6 — Cơ chế re-validate W7 là dead code trên đường runtime

- **File**: `core/vix_pair_backtest.py:510-550` (`is_sensitivity_map_stale`, TTL 90 ngày, seed luôn stale) vs `core/correlation_check.py:20-65` (loader runtime không gọi staleness check, cache module-level latch vĩnh viễn, warning chỉ vào log file)
- Safe-haven status không vĩnh viễn (chính spec nêu) — nhưng map hết hạn vẫn chấm điểm bình thường cho đến khi ai đó tình cờ đọc log.

**Fix**: loader runtime gọi `is_sensitivity_map_stale()` — stale/seed → trả `{}` (flat) kèm warning nổi bật hơn, hoặc tự trigger runner nếu có; cân nhắc thông báo trên UI scanner khi map stale.

### 🟠 MAJOR 7 — Bộ test che kín các bug trên (verifier hạ từ major xuống minor sau khi bác 1 phần)

- Loader runtime `_load_vix_sensitivity` (45 dòng, đường dẫn phân phối thật) có **0 test trực tiếp** — mọi test scoring đều inject cache toàn cục; `TestSensitivityMapLoading` test bộ API không có production caller.
- Không test end-to-end với file thật (read path, candidate order, symbol slash-form contract); integration không chạm biên clamp [-6,+5]; injection không có autouse reset → pollute global cache giữa tests.
- Một phần claim (pollute gây sai kết quả ở cấp suite) bị verifier bác — suite vẫn xanh vì isolation tình cờ đủ tốt; core finding (runtime path không được ghim) đứng.

**Fix**: thêm test đọc file thật qua `_load_vix_sensitivity` (tmp_path + reset fixture), test candidate order repo-vs-appdata, test clamp với VIX penalty, test "seed/stale → flat" sau khi nối gate.

---

### 🟡 MINOR 8 — Mapping thiếu nền tảng thống kê

Không significance gate (với n=252, r=0.15 tương đương p≈0.017 — ngưỡng ±0.15 sát sàn nhiễu; cặp 20-60 ngày lookback thì r phải cao hơn nhiều mới có nghĩa); `MIN_LOOKBACK_DAYS=20` quá thấp cho kết luận regime; nhánh `|corr|≥0.8 → factor 0.0` gần như chỉ seed chạm tới (FX hiếm có |r|≥0.8 với VIX). → Thêm significance check (t-stat hoặc bootstrap CI), nâng MIN_LOOKBACK, cân nhắc bỏ/cap nhánh 0.8.

### 🟡 MINOR 9 — Chú thích và phân loại sai bản chất nhân quả

`_classify_pair` dán nhãn `"safe_haven"` cho mọi cặp corr < −0.25 — kể cả AUD/USD (corr âm do AUD yếu khi risk-off, không phải safe-haven demand); `_build_pair_note` cho AUD/JPY mô tả đúng hiện tượng nhưng gán nhân quả safe-haven cho cặp risk-on. Chỉ ảnh hưởng note/interpretation (scoring dùng corr/factor/vix_direction), nhưng sẽ gây hiểu nhầm khi đọc report kiểm chứng W5. → Phân loại theo currency-level (base risk-on vs quote safe-haven) thay vì pair-level corr.

### 🟡 MINOR 10 — Docstring/comment mâu thuẫn code (nit)

`_correlation_to_sensitivity` docstring nói "dùng correlation^2" nhưng code là piecewise-linear; comment `app_data_dir() trả về ./data` sai; biến `corr` đọc từ map trong `_vix_score` không được dùng sau đó.

---

## 3. Những gì ĐÚNG (xác nhận qua truy vết đối kháng)

- **W2 — pass (5/5 reviewer)**: chỉ `_vix_score` thay đổi; `check_vix_context`, VIX trong `risk_engine`/news diagnostic (`vix_applied_to_score=False`) giữ nguyên; clamp [-6,+5] nhóm USD áp trước VIX như cũ.
- **W1 cơ chế đúng**: aligned JPY-pair SELL giảm/bỏ phạt đúng chủ đích (AUD/JPY sell VIX=30 → −0.0; USD/JPY sell → −1.0), bonus VIX<15 không điều chỉnh, unknown pair → flat.
- **Không hardcode if-JPY trong scoring** (W3 vế đầu): nhánh JPY chỉ tồn tại trong note text.
- **Fail-open an toàn**: thiếu/lỗi map → flat scoring; parse lỗi → bỏ qua từng file.
- **Symbol runtime khớp map**: pipeline nhận slash-form từ `SUPPORTED_SYMBOLS` qua `AnalysisInput.symbol`, `_vix_score` lookup `symbol.upper()` — đã chạy thật xác nhận nạp 31/31 cặp.
- **Scaffolding kiểm chứng tốt**: TTL/staleness utilities, seed tự dán nhãn + warning, meta đầy đủ (`vix_data_points`, `data_start/end`, `methodology`) — chỉ thiếu gate runtime và vòng data.
- **Test cơ khí tốt**: 48 test phủ engine/scoring/loading/staleness/integration/seed, không flaky (ngày giờ cố định + `random.seed`).

## 4. Ma trận yêu cầu W1-W9

| YC | Trạng thái | Lý do chính |
|---|---|---|
| W1 VIX phạt phân hóa theo cặp | ⚠️ partial | cơ chế đúng nhưng chạy trên seed + bug c2 |
| W2 chỉ đụng VIX trong điểm macro | ✅ pass | 5/5 reviewer xác nhận, diff xác nhận |
| W3 mapping data, AUD/NZD nặng hơn | ❌ fail | seed viết tay (c1) + công thức ngược flow (c2) |
| W4 backtest trước khi code (yêu cầu chặn) | ❌ fail | 0 ngày dữ liệu, 0 backtest đã chạy (c1) |
| W5 chạy backtest ΔVIX vs returns | ❌ fail | không runner, data live 5d, align lỗi (c4, c5) |
| W6 mapping từ kết quả backtest | ❌ fail | vòng W5→W6 gãy vì path mismatch (c3) |
| W7 re-validate định kỳ | ⚠️ partial | TTL/stale có nhưng dead code runtime (c6) |
| W8 journal Bước 6 làm lưới an toàn | ⚠️ unclear | chỉ nhắc trong log text; journal Bước 6 chưa khép vòng |
| W9 lý do làm cuối (quy trình) | — | chính c1 là hiện thực hóa rủi ro W9 cảnh báo |

## 5. Thứ tự sửa đề xuất

1. **Flag kill-switch `vix_pair_aware_enabled` mặc định OFF + loader gate seed/stale → flat** — đưa hệ thống về trạng thái an toàn ngay, đúng tinh thần W4/W9 (không đưa giả thuyết chưa kiểm chứng vào scoring).
2. **Sửa công thức ngược flow (c2)** — độc lập với data; tối thiểu `effective_factor = 1.0` cho nhánh ngược flow.
3. **Viết runner backtest** (`period="2y"` cho ^VIX + returns 31 cặp, lookback 252) — khép W5.
4. **Align theo ngày** trong engine (c5) trước khi chạy data thật.
5. **Thống nhất đường dẫn save/load** về `data/` repo (c3); sửa comment sai; quyết định policy PyInstaller bundle.
6. **Nối staleness vào runtime loader** (c6).
7. Chạy backtest thật, đọc kết quả kèm significance (c8), xác nhận hoặc bác giả thuyết — rồi mới bật flag.
8. Bổ sung test loader runtime + end-to-end file thật + clamp (c7).

---

## 6. Ghi chú ngoài phạm vi

Commit `d9eb515` cũng chứa Bước 6 "as-is" — các critical trong báo cáo review Bước 6 (`docs/macro/step6_ai_macro_verdict_review.md`: ai_service chưa inject vào pipeline, context rỗng ruột, adjustment sau bước chấm điểm) vẫn còn mở trong branch này.

---

*Review tạo bởi quy trình đa agent: 5 reviewer độc lập (data-driven, phương pháp backtest, scoring, re-validate/vận hành, chất lượng test) → merge kiểm chứng bằng đọc code thật và chạy snippet runtime → xác minh đối kháng từng cụm. 18 agent, 0 lỗi, toàn bộ 10 cụm sống sót sau bước bác bỏ.*
