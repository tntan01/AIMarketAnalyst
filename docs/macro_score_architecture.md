# Báo cáo kiến trúc: Điểm "Vĩ mô" trên màn hình Chi tiết từ quét thị trường

**Ngày**: 2026-07-20
**Trạng thái**: Điều tra — chỉ đọc code, không sửa

---

## 1. Danh sách file liên quan

| File | Vai trò |
|------|--------|
| `ui/screens/scanner_detail_screen.py` | UI — hiển thị điểm Vĩ mô và trạng thái Thuận/Trung lập/Xung đột |
| `ui/screens/scanner_screen.py` | UI — bảng kết quả quét (hiển thị cột Vĩ mô) |
| `core/scanner.py` | Logic — `scanner_row_from_analysis()` tạo row chứa `macro_score`, `macro_bias`, `macro_confidence` |
| `core/analysis_pipeline.py` | Pipeline — `AnalysisPipeline.analyze()` gọi `score_scenario()` với `macro_alignment` |
| `core/analysis_engine.py` | Engine — `analyze_symbol()` → `AnalysisPipeline` |
| `core/signal_engine.py` | Signal — `score_scenario()` kết hợp macro với technical/risk |
| `core/scanner_ai_auditor.py` | AI audit — truyền `macro_score` vào prompt audit |
| `controllers/scanner_controller.py` | Controller — gọi `NewsService.data_quality_flags()` lấy `macro_context` |
| `services/news_service.py` | Service — `_compute_macro_tiers()` tính điểm 3 tier (0-30) |
| `services/forex_factory_client.py` | Data — `calendar_events()` lấy lịch kinh tế từ ForexFactory |
| `services/interest_rate_service.py` | Data — `get_latest_rates()` lấy lãi suất từ FRED + FF |
| `services/calendar_helpers.py` | Utility — shared helpers |
| `config/interest_rates.json` | Config — lãi suất fallback |
| `tests/test_news_service.py` | Test — `TestMacroTier1` kiểm tra tier 1 |
| `scripts/backtest_macro_score.py` | Script — backtest điểm vĩ mô |

---

## 2. Danh sách class liên quan

| Class | File | Vai trò |
|-------|------|--------|
| `ScannerDetailScreen` | `scanner_detail_screen.py` | Màn hình chi tiết — hiển thị card Vĩ mô |
| `NewsService` | `news_service.py` | Tính toán 3-tier macro score |
| `ForexFactoryClient` | `forex_factory_client.py` | Lấy dữ liệu lịch kinh tế |
| `AnalysisPipeline` | `analysis_pipeline.py` | Pipeline phân tích — tích hợp macro vào điểm tổng |
| `ScannerController` | `scanner_controller.py` | Controller quét — điều phối NewsService + AnalysisPipeline |

---

## 3. Danh sách method liên quan

| Method | File:Dòng | Vai trò |
|--------|-----------|--------|
| `_dialog_card_macro()` | `scanner_detail_screen.py:448` | Render card Vĩ mô (X/30 + trạng thái) |
| `_classify_macro_bias()` | `scanner.py:438` | Phân loại Thuận/Trung lập/Phân kỳ |
| `scanner_row_from_analysis()` | `scanner.py:30` | Tạo scanner row với `macro_score`, `macro_bias` |
| `_step_score_scenarios()` | `analysis_pipeline.py:302` | Tích hợp `macro_alignment` vào `score_scenario()` |
| `_fetch_one_symbol_mt5()` | `scanner_controller.py:785` | Lấy `macro_context` từ `NewsService` |
| `latest_macro_context()` | `news_service.py:103` | Full pipeline: calendar + headlines + tier scoring |
| `data_quality_flags()` | `news_service.py:147` | Trả về `macro_context` + quality flags |
| `_compute_macro_tiers()` | `news_service.py:629` | Tính 3-tier macro score |
| `_macro_tier1()` | `news_service.py:738` | Tier 1: Lãi suất & Chính sách tiền tệ (0-12) |
| `_macro_tier2()` | `news_service.py:822` | Tier 2: Lịch kinh tế (0-10) |
| `_macro_tier3()` | `news_service.py:918` | Tier 3: Tâm lý rủi ro & Địa chính trị (0-8) |
| `_macro_data_quality()` | `news_service.py:1099` | Chất lượng dữ liệu vĩ mô (0.0-1.0) |
| `score_scenario()` | `signal_engine.py:88` | Điểm tổng hợp (technical + macro + risk) |

---

## 4. Nguồn dữ liệu

| Nguồn | File | Method | Dữ liệu lấy | Dùng để |
|-------|------|--------|------------|---------|
| **ForexFactory JSON API** | `forex_factory_client.py` | `_fetch_json_events()` | Calendar events (currency, event, impact, time) | Tier 2: đếm sự kiện sắp tới |
| **ForexFactory HTML** | `forex_factory_client.py` | `_fetch_html_events()` | Actual values cho merge | Self-heal cache |
| **FRED API** | `interest_rate_service.py` | `_fetch_from_fred()` | Lãi suất 8 currencies | Tier 1: rate differential |
| **ForexFactory HTML (rate)** | `interest_rate_service.py` | `_update_from_forexfactory()` | Lãi suất từ FF calendar | Tier 1: fallback nếu FRED lỗi |
| **config/interest_rates.json** | `interest_rates.json` | `_load_fallback()` | Lãi suất tĩnh | Tier 1: fallback cuối cùng |
| **Google News RSS** | `news_service.py` | `_macro_headlines()` | Headlines (title, published_utc) | Tier 1: stance analysis, Tier 3: sentiment |
| **Official Statements RSS** | `news_service.py` | `_latest_official_statements()` | Phát biểu chính thức | Hotspot detection |
| **Yahoo Finance (^VIX)** | `news_service.py` | `_fetch_vix()` | VIX index | Tier 3: VIX adjustment |
| **Yahoo Finance (^TNX, ^FVX)** | `news_service.py` | `_fetch_yield_spread()` | 10Y-5Y yield spread | Tier 1: yield curve |
| **AI Service (Gemini/DeepSeek)** | `news_service.py` | `_ai_currency_stance()` | hawkish/dovish/neutral per currency | Tier 1 + Tier 3: stance |
| **Static Rules** | `news_service.py` | `SENTIMENT_LEXICON`, `EVENT_SEVERITY` | Keyword weights | Tier 2 + Tier 3: severity/sentiment |
| **Disk Cache** | `forex_factory_client.py` | `_cached_calendar_events()` | Calendar events cached | Giảm HTTP calls |
| **NewsService cache** | `news_service.py` | `_tier_scores_cache` | Tier scores per symbol | 5-min TTL |

---

## 5. Pipeline đầy đủ

```
                            ┌──────────────────────┐
                            │   NGUỒN DỮ LIỆU      │
                            ├──────────────────────┤
                            │ ForexFactory JSON    │──► Calendar events (Tier 2)
                            │ ForexFactory HTML    │──► Actual merge
                            │ FRED API             │──► Interest rates (Tier 1)
                            │ Yahoo Finance        │──► VIX, TNX, FVX (Tier 1,3)
                            │ Google News RSS      │──► Headlines (Tier 1,3)
                            │ AI (Gemini/DeepSeek) │──► Stance analysis (Tier 1,3)
                            │ Static config/rules  │──► Severity, sentiment weights
                            └──────────┬───────────┘
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │    NewsService        │
                            │  latest_macro_context │
                            ├──────────────────────┤
                            │ 1. calendar_events()  │──► ForexFactoryClient
                            │ 2. _get_headlines()   │──► Google News RSS
                            │ 3. _latest_statements │──► Official RSS
                            │ 4. _compute_macro_    │
                            │    tiers()            │
                            │    ├─ _macro_tier1()  │──► Interest rate (0-12)
                            │    ├─ _macro_tier2()  │──► Calendar (0-10)
                            │    └─ _macro_tier3()  │──► Sentiment/Geo (0-8)
                            │ 5. _macro_data_       │
                            │    quality()          │──► Confidence (0.0-1.0)
                            └──────────┬───────────┘
                                       │
                            macro_alignment_scores
                            {"buy": X, "sell": Y}    (mỗi bên 0-30)
                            macro_data_quality       (0.0-1.0)
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │  ScannerController    │
                            │  _fetch_one_symbol    │
                            ├──────────────────────┤
                            │ data_quality_flags()  │──► lấy macro_context
                            │ freshness_multiplier  │──► 0.6-1.0 tùy tuổi data
                            │ macro_confidence =    │
                            │   quality × freshness │
                            └──────────┬───────────┘
                                       │
                              macro_alignment, macro_confidence
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │   AnalysisPipeline    │
                            │      analyze()       │
                            ├──────────────────────┤
                            │ _step_score_scenarios│
                            │  └─ score_scenario() │──► signal_engine.py
                            │      macro_alignment  │    (0-30) → scaled to
                            │      macro_confidence │    signal_score /100
                            └──────────┬───────────┘
                                       │
                              result["scenario_scores"]
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │   core/scanner.py     │
                            │ scanner_row_from      │
                            │ _analysis()           │
                            ├──────────────────────┤
                            │ macro_score =         │
                            │   scores[best_side]   │
                            │   ["macro_alignment"] │
                            │ macro_bias =          │
                            │   _classify_macro_    │
                            │   bias(result, side)  │
                            └──────────┬───────────┘
                                       │
                              row["macro_score"]     (0-30)
                              row["macro_bias"]      (aligned/neutral/divergent)
                              row["macro_confidence"] (0.0-1.0)
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │ ScannerDetailScreen   │
                            │ _dialog_card_macro()  │
                            ├──────────────────────┤
                            │ Hiển thị:             │
                            │  "● 22/30 Thuận"     │
                            │  hoặc                 │
                            │  "○ 15/30 Trung lập" │
                            │  hoặc                 │
                            │  "◌ 3/30 Xung đột"   │
                            │                       │
                            │ Màu sắc:              │
                            │  ≥22: xanh            │
                            │  ≥15: vàng            │
                            │  <15: xám             │
                            │                       │
                            │ Dot indicator:        │
                            │  ● conf ≥ 0.8         │
                            │  ○ conf ≥ 0.5         │
                            │  ◌ conf < 0.5         │
                            └──────────────────────┘
```

---

## 6. Công thức tính điểm

### Tổng quan

```
macro_score (0-30) = tier1_buy + tier2_buy + tier3_buy   (nếu best_side=buy)
macro_score (0-30) = tier1_sell + tier2_sell + tier3_sell (nếu best_side=sell)
```

Mỗi tier đóng góp vào điểm buy VÀ sell riêng biệt.

### Tier 1 — Lãi suất & Chính sách tiền tệ (0-12)

**File**: `news_service.py:738-819`
**Input**: base currency, quote currency, base_stance, quote_stance

| Thành phần | Điểm | Công thức |
|-----------|------|-----------|
| Rate differential | 0-4 | `round(4 × |base_rate - quote_rate| / 5.0)`, về phe có lãi suất cao hơn |
| Rate trend | 0-4 | `trend_map = {"hike": 4, "hold": 2, "cut": 0}`; diff mapped to 0-4 mỗi bên |
| Stance (từ headlines) | 0-4 | `stance_value = {"hawkish": 1, "neutral": 0, "dovish": -1}`; delta mapped |
| Yield spread (2s10s) | -2 đến +2 | Chỉ cho cặp có USD; âm = recession signal |
| **Tổng Tier 1** | **0-12** | `diff + trend + stance + yield_adj` |

**Lưu ý**: Yield spread có thể làm Tier 1 vượt quá 12 hoặc dưới 0 (không clamp).

### Tier 2 — Lịch kinh tế (0-10)

**File**: `news_service.py:822-899`
**Input**: base currency, quote currency, events

| Thành phần | Giá trị |
|-----------|--------|
| Phạm vi thời gian | 72 giờ tới |
| Event severity | 1 (thường), 2 (quan trọng), 3 (rất quan trọng) |
| Time weight | 3.0 (<6h), 2.0 (<24h), 1.5 (<48h), 1.0 (<72h) |
| Quality per event | `severity × time_weight` |
| Điểm nền | 5 |
| **Công thức** | `buy_cal = clamp(5 - base_quality, 1, 9)` |
| | `sell_cal = clamp(5 - quote_quality, 1, 9)` |

**Ý nghĩa**: ÍT sự kiện quan trọng cho base currency → điểm buy CAO hơn (5 - 0 = 5). NHIỀU sự kiện → điểm thấp hơn (5 - 9 = -4 → clamp về 1).

### Tier 3 — Tâm lý rủi ro & Địa chính trị (0-8)

**File**: `news_service.py:918-1096`
**Input**: currencies, headlines, hotspots

| Thành phần | Điểm | Công thức |
|-----------|------|-----------|
| Sentiment (lexicon) | Biến động | Quét headlines tìm 40+ từ khóa positive/negative, có negation detection |
| Sentiment (AI) | Biến động | AI stance → score map: hawkish=-2, dovish=2, neutral=0 |
| VIX adjustment | -3 đến +2 | <15: +2, <20: 0, <25: -1, <30: -2, ≥30: -3 |
| Risk sentiment (0-8) | 0-8 | Raw sentiment mapped to 0-8 scale, split buy/sell dựa trên safe haven vs risk currency |
| Geopolitical (0-4) | 0-4 | Dựa trên severity của hotspot keywords |
| **Tổng Tier 3** | **0-12** | `risk_sentiment(0-8) + geopolitical(0-4)` |

**Safe havens**: USD, JPY, CHF, XAU — được lợi khi risk_off
**Risk currencies**: AUD, NZD, CAD — được lợi khi risk_on

---

## 7. Giải thích từng Tier

### Tier 1 (0-12): Lãi suất — "Tiền tệ nào đang thắt chặt?"

Trả lời câu hỏi: "Base currency có lợi thế lãi suất so với quote không?"

- **Rate diff**: Base có lãi suất cao hơn quote → điểm buy. Công thức tuyến tính, bão hòa ở 5% diff.
- **Rate trend**: Base đang hike, quote đang cut → điểm buy tối đa. Cả 2 hold → trung lập (2-2).
- **Stance**: AI hoặc keyword phân tích hawkish/dovish từ headlines.
- **Yield spread**: Đường cong lợi suất Mỹ đảo ngược (2s10s < 0) → cảnh báo suy thoái.

### Tier 2 (0-10): Calendar — "Có sự kiện nào sắp gây biến động không?"

Trả lời câu hỏi: "Trong 72h tới, currency nào có nhiều sự kiện quan trọng?"

- Ít sự kiện cho base → ít bất định → điểm buy cao
- Nhiều sự kiện → rủi ro biến động → điểm thấp
- Sự kiện càng gần, severity càng cao → quality càng lớn

### Tier 3 (0-8): Sentiment — "Thị trường đang risk_on hay risk_off?"

Trả lời câu hỏi: "Tâm lý thị trường hiện tại ủng hộ risk hay safe haven?"

- Risk_on → AUD, NZD, CAD được lợi
- Risk_off → USD, JPY, CHF, XAU được lợi
- VIX cao → risk_off → điều chỉnh điểm

---

## 8. Trọng số từng Tier

| Tier | Phạm vi | Trọng số trong 30 |
|------|--------|-------------------|
| Tier 1 (Lãi suất) | 0-12 | 40% |
| Tier 2 (Calendar) | 1-9 | ~27% |
| Tier 3 (Sentiment) | 0-8 (risk) + 0-4 (geo) = 0-12 | 40% |

Tier 1 và Tier 3 có trọng số bằng nhau (0-12). Tier 2 nhẹ hơn (1-9, không bao giờ đạt 0 hoặc 10).

**Lưu ý**: Điểm trung lập mặc định là 15/30 (không có lợi thế cho bên nào).

---

## 9. Điều kiện "Thuận lợi / Trung lập / Bất lợi"

**File**: `core/scanner.py:438-456` — `_classify_macro_bias()`

```python
macro_buy  = scores["buy"]["macro_alignment"]     # 0-30
macro_sell = scores["sell"]["macro_alignment"]    # 0-30
macro_diff = macro_buy - macro_sell               # -30 đến +30

if abs(macro_diff) < 5:                           → "neutral" (Trung lập)
elif best_side == "buy" and macro_diff >= 5:      → "aligned" (Thuận)
elif best_side == "sell" and macro_diff <= -5:    → "aligned" (Thuận)
else:                                              → "divergent" (Xung đột/Bất lợi)
```

| Điều kiện | Kết quả | Ý nghĩa |
|-----------|---------|---------|
| `\|macro_buy - macro_sell\| < 5` | **Trung lập** | Không có sự khác biệt đáng kể giữa buy và sell |
| `best_side=buy AND macro_buy - macro_sell ≥ 5` | **Thuận** | Vĩ mô ủng hộ hướng buy |
| `best_side=sell AND macro_buy - macro_sell ≤ -5` | **Thuận** | Vĩ mô ủng hộ hướng sell |
| Còn lại (best_side trái ngược với macro) | **Xung đột** | Kỹ thuật nói buy nhưng vĩ mô nói sell (hoặc ngược lại) |

**Threshold**: ±5 điểm trên thang 30 (~17% của thang điểm).

**Ghi chú**: UI mapping (`scanner_detail_screen.py:678`) dùng key `"conflict"` nhưng `_classify_macro_bias()` trả về `"divergent"`. Đây là mismatch — nếu `macro_bias = "divergent"`, UI hiển thị `"—"` (không map được). Đây có thể là một bug tiềm ẩn.

---

## 10. Giải thích điểm 3/30

Điểm 3/30 là trường hợp **cực kỳ bất lợi** cho một hướng. Để đạt 3/30:

1. **Tier 1 (lãi suất)**: Quote có lãi suất cao hơn nhiều + base đang cut + quote đang hike + stance dồn về quote
2. **Tier 2 (calendar)**: Nhiều sự kiện quan trọng cho base, ít cho quote → base quality cao → `5 - quality` thấp
3. **Tier 3 (sentiment)**: Risk_off + base là risk currency → điểm thấp

Điểm thấp nhất có thể: Tier1 âm (yield adj), Tier2=1 (clamp), Tier3 ~0 → tổng có thể < 3.

**Mặc định**: `15/30` — điểm trung lập khi không đủ dữ liệu hoặc cân bằng.

---

## 11. Cache

| Cache | Vị trí | TTL | Ghi chú |
|-------|--------|-----|---------|
| `_tier_scores_cache` | `news_service.py:65` | 5 phút (qua `_preload_cache_ttl`) | Cache per symbol — tránh tính lại macro score liên tục |
| `_calendar_cache` | `forex_factory_client.py:136` | 24 giờ | Calendar events từ FF |
| `_stance_cache` | `news_service.py:70` | 30 phút | AI stance per currency |
| `interest_rate_service._CACHE` | `interest_rate_service.py:40` | 6 giờ | Lãi suất từ FRED |
| Preload cache | `news_service.py:179` | 5 phút | Toàn bộ macro context cho tất cả symbols |

**Refresh**: Scanner gọi `preload_macro_contexts()` mỗi lần quét (có 5-min guard). Sau đó mỗi symbol gọi `data_quality_flags()` → `latest_macro_context()` có cache check.

---

## 12. AI tham gia ở đâu

| Bước | Method | Vai trò AI |
|------|--------|-----------|
| **Stance analysis** | `_ai_currency_stance()` (news_service.py:666) | Đọc headlines → phân loại hawkish/dovish/neutral |
| **Tier 1** | `_compute_macro_tiers()` → `_macro_tier1()` | Dùng stance từ AI để tính stance score |
| **Tier 3** | `_macro_tier3()` | AI sentiment score (dùng stance map: hawkish=-2, dovish=2) |
| **Fallback** | `_ai_currency_stance()` | Nếu AI lỗi → `currency_stance()` keyword-based |

AI không tham gia trực tiếp vào Tier 2 (calendar). AI stance ảnh hưởng Tier 1 qua `base_stance`/`quote_stance`.

---

## 13. Đánh giá kiến trúc

### Điểm mạnh

- **3-tier separation rõ ràng**: Lãi suất, Calendar, Sentiment — mỗi tier độc lập, dễ hiểu
- **Multi-source**: Kết hợp 7+ nguồn dữ liệu (FRED, FF, Yahoo, RSS, AI, static config)
- **Có fallback ở mọi tầng**: AI → keyword, FRED → ForexFactory → JSON file
- **Confidence scoring**: `_macro_data_quality()` đánh giá độ tin cậy, freshness_multiplier điều chỉnh
- **Cache đa tầng**: Calendar (24h), rates (6h), stance (30m), tier scores (5m)

### Điểm yếu

- **`_classify_macro_bias` trả về "divergent" nhưng UI lookup dùng "conflict"**: Mismatch key → UI hiển thị "—" thay vì "Xung đột" khi macro bất lợi
- **Tier 1 không clamp**: Yield spread có thể đẩy tier1 vượt ngoài 0-12, làm tổng >30 hoặc <0
- **Tier 2 không bao giờ đạt 0 hoặc 10**: Luôn clamp 1-9 → mất 2 điểm phân biệt
- **Hardcode trong Tier 2**: `EVENT_SEVERITY` dictionary chỉ có ~15 patterns, bỏ lỡ nhiều sự kiện
- **Không có trọng số động**: Các tier luôn cố định 12+10+8, không thay đổi theo market regime
- **Không dùng actual values trong Tier 2**: Chỉ dùng impact + time, không xét actual đã công bố

---

## 14. Các vấn đề phát hiện

| # | Vấn đề | Mức độ | Vị trí |
|---|--------|--------|--------|
| **1** | `_classify_macro_bias` trả về "divergent", UI map expect "conflict" → hiển thị sai | Medium | `scanner.py:456` vs `scanner_detail_screen.py:678` |
| **2** | Tier 1 có thể vượt 12 do yield_adj không clamp | Low | `news_service.py:818-819` |
| **3** | `EVENT_SEVERITY` hardcode, thiếu nhiều sự kiện quan trọng | Low | `news_service.py:823-828` |
| **4** | Tier 2 luôn 1-9, mất khả năng đạt 0 hoặc 10 | Low | `news_service.py:887-888` |

---

## 15. Đề xuất cải tiến (KHÔNG sửa code — chỉ đề xuất)

1. **Sửa mismatch "divergent" → "conflict"**: Thêm "divergent" vào `_VN_MACRO` và inline dict ở line 678
2. **Clamp Tier 1 về 0-12**: `max(0, min(12, total))` để giữ tổng 0-30
3. **Mở rộng EVENT_SEVERITY**: Thêm patterns từ calendar parser hoặc dùng impact field thay vì keyword match
4. **Thêm actual values vào Tier 2**: Sự kiện đã có actual tốt hơn/bằng/kém hơn forecast → điều chỉnh quality
5. **Dynamic tier weights**: Trong thị trường biến động cao (VIX > 25), tăng trọng số Tier 3
