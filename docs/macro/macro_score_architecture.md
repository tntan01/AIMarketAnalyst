# Macro Score Architecture & Phase 15 Changelog

**Last updated**: 2026-08-16
**Status**: Scanner V4 là runtime live; các mục bên dưới mô tả contract Macro V1
của Scanner V3 (giữ cho audit/replay). Bước 7 VIX pair-aware có data-backed map
nhưng vẫn opt-in/default OFF và chưa xác nhận giả thuyết JPY/AUD/NZD. Ngày
16/08/2026 gỡ toàn bộ shadow subsystem theo quyết định owner: Macro V2
diagnostics, Bước 5 event-impact derate và Bước 6 AI Macro Verdict.

> **Ranh giới version 11/08/2026 (cập nhật 16/08/2026):** Các mục 1–20 bên
> dưới mô tả **contract Scanner V3** (hiện giữ read-only cho audit/replay), nơi
> macro vẫn là contribution của composite score. Kiến trúc **Scanner V4 đã live
> từ 15/08/2026** nằm tại
> [`../scanner/scanner-v4-architecture.md`](../scanner/scanner-v4-architecture.md).
> Trong V4, `TechnicalSignalScore` chỉ gồm Trend/Momentum/Location/SMC;
> `MacroAssessment`/`MacroGate` và `MarketSafetyGate` không cộng hoặc trừ điểm.
> Cutover là atomic/direct: không dual scoring, không chạy V3/V4 song song và
> không dùng shadow comparison với V3. Các shadow subsystem từng có trong file
> này (Macro V2 diagnostics, Bước 5, Bước 6) đã gỡ khỏi code ngày 16/08/2026;
> các mục tương ứng bên dưới chỉ còn là ghi chú tombstone.

---

## Phase 15 Changelog Summary

| Phase | Date | Change | Impact |
|-------|------|--------|--------|
| **15A** | 2026-07-23 | Audit macro scoring contracts + tests | 15 tests, no code change |
| **15B** | 2026-07-23 | Remove surplus weight redistribution in `score_scenario` | Confidence decrease no longer increases score |
| **15C** | 2026-07-23 | Tier 2 calendar always neutral (buy=sell=5) | Calendar events no longer create fake directional bias |
| **15C.1** | 2026-07-23 | Harden: `actual`/`forecast` diagnostic only, never directional | Event risk tracked as separate diagnostic field |
| **15D** | 2026-07-23 | Add Macro V2 pair-relative shadow model — **đã gỡ 16/08/2026** | Module `_compute_macro_v2()` không còn trong code |
| **15D.1** | 2026-07-23 | Harden V2: exact symmetry (sell=30-buy), missing→neutral — **đã gỡ 16/08/2026** | Cùng module `_compute_macro_v2()` |
| **15D.2** | 2026-07-23 | Expose `macro_v2` in `latest_macro_context` + scanner — **đã gỡ 16/08/2026** | Key `macro_v2` không còn trong payload |
| **15E** | 2026-07-23 | Remove VIX/AI double-count from Tier 3 | AI stance only in Tier 1; VIX only via `correlation_adjustment` |
| **15F** | 2026-07-23 | Add `macro_data_quality_detail` provenance breakdown | Per-component availability, source, freshness, confidence |
| **15F.1** | 2026-07-23 | Fix rates availability (rate=0 valid), no re-fetch | Calendar confidence based on source fetch, not event count |
| **15F.2** | 2026-07-23 | Rename yield spread: `yield_spread_2s10s` → `yield_spread_10y_5y` | ^TNX-^FVX = 10Y-5Y, deprecated alias kept |
| **15G** | 2026-07-23 | V1 vs V2 comparison script + shadow metrics — **đã gỡ 16/08/2026** | `scripts/compare_macro_v1_v2.py` không còn |
| **15G.1–6** | 2026-07-23 | Sensitivity grid, fix symbol parsing, edge deadband — **đã gỡ 16/08/2026** | Config candidates không còn dùng |
| **15G.7** | 2026-07-23 | Forward outcome validation tool — **đã gỡ 16/08/2026** | `scripts/validate_macro_v2.py` không còn |
| **Bước 5** | 2026-08-07 | AI Event Impact Assessment — **đã gỡ 16/08/2026** | `event_impact_assessor.py` + derate không còn trong pipeline |
| **Bước 5 review fixes** | 2026-08-07 | Fix theo báo cáo review — **đã gỡ 16/08/2026 cùng Bước 5** | Không còn hành vi |
| **Bước 7 remediation** | 2026-08-09 | Pair-aware VIX trở thành opt-in, data-gated; sửa opposed-flow penalty, common-date alignment, runtime path/TTL/cache và thêm runner | Candidate ineligible bị bỏ qua; không còn eligible candidate → flat; backtest thật 31/31 pair, 3 raw-actionable |
| **Gỡ shadow** | 2026-08-16 | Gỡ toàn bộ shadow subsystem theo quyết định owner: Macro V2 diagnostics, Bước 5 event-impact derate, Bước 6 AI Macro Verdict, backtest engine shadow trong release gate, và `ai_verdict` dimension của V4 macro gate | Đường live V4 vốn không tiêu thụ shadow nên quyết định live không đổi; release report version bump `backtest-phase7-release-report-v2`; suite **3598 passed, 8 skipped, 16 xfailed** |

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
| `services/news_service.py` | Service — `_compute_macro_tiers()` tính 3-tier (0-30) |
| `services/forex_factory_client.py` | Data — `calendar_events()` lấy lịch kinh tế từ ForexFactory |
| `services/interest_rate_service.py` | Data — `get_latest_rates()` lấy lãi suất từ FRED + FF |
| `services/calendar_helpers.py` | Utility — shared helpers |
| `config/interest_rates.json` | Config — lãi suất fallback |
| `tests/test_news_service.py` | Test — `TestMacroTier1` kiểm tra tier 1 |
| `scripts/backtest_macro_score.py` | Script — backtest điểm vĩ mô |
| `core/correlation_check.py` | Bước 7 runtime — tính VIX base contribution, đọc eligible map và modulate theo pair/side khi flag bật |
| `core/vix_pair_backtest.py` | Bước 7 engine — align common dates, Pearson/Fisher-z gate, schema/TTL/eligibility và atomic persistence |
| `scripts/run_vix_pair_backtest.py` | Bước 7 runner — tải `^VIX` + 31 symbol, in summary và chỉ lưu map đủ điều kiện |
| `data/vix_pair_sensitivity.json` | Bước 7 — schema-2 map data-backed được bundle làm runtime fallback |
| `reports/vix_pair_sensitivity_2026-08-09.json` | Bước 7 — evidence snapshot được giữ để review, không phải archive tự sinh của runner |
| `config/settings.py`, `services/settings_service.py` | Bước 7 — flag mặc định OFF và persistence fail-closed |
| `services/news_service.py`, `core/analysis_pipeline.py` | Bước 7 — truyền flag qua data quality cho cả BUY/SELL scoring |
| `ui/screens/settings_screen.py` | Bước 7 — checkbox Advanced, cảnh báo chỉ bật sau backtest |
| `packaging/pyinstaller.spec` | Bước 7 — bundle tracked validated map làm fallback |
| `tests/test_vix_pair_sensitivity.py` | Bước 7 — scoring, map, loader và regression |
| `tests/test_step7_review_fixes.py` | Bước 7 — review regressions: path, stale, reload, malformed, flag và alignment |
| `tests/test_vix_pair_backtest_runner.py` | Bước 7 — ticker/fetch/validate/save contract của runner |

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
| `_dialog_card_macro()` | `scanner_detail_screen.py:1119` | Render card Vĩ mô (X/30 + trạng thái) |
| `_classify_macro_bias()` | `scanner.py:647` | Phân loại Thuận/Trung lập/Phân kỳ |
| `scanner_row_from_analysis()` | `scanner.py:60` | Tạo scanner row với `macro_score`, `macro_bias` |
| `_step_score_scenarios()` | `analysis_pipeline.py:836` | Tích hợp `macro_alignment` vào `score_scenario()` |
| `_fetch_one_symbol_mt5()` | `scanner_controller.py:2547` | Lấy `macro_context` từ `NewsService` |
| `latest_macro_context()` | `news_service.py:283` | Full pipeline: calendar + headlines + tier scoring |
| `data_quality_flags()` | `news_service.py:432` | Trả về `macro_context` + quality flags |
| `_compute_macro_tiers()` | `news_service.py:1802` | Tính 3-tier macro score |
| `_macro_tier1()` | `news_service.py:2252` | Tier 1: Lãi suất & Chính sách tiền tệ (0-12) |
| `_macro_tier2()` | `news_service.py:2355` | Tier 2: Lịch kinh tế (0-10) |
| `_macro_tier3()` | `news_service.py:2511` | Tier 3: Tâm lý rủi ro (0-8) + Địa chính trị (0-4), tổng 0-12 |
| `_macro_data_quality()` | `news_service.py:2709` | Chất lượng dữ liệu vĩ mô (0.0-1.0) |
| `compose_scenario_score()` | `signal_engine.py:90` | Điểm tổng hợp (technical + macro + risk) |
| `_step_compute_correlation()` | `analysis_pipeline.py:630` | Sàn macro_confidence 0.15 + Bước 7 flag wiring trong bước correlation |
| `compute_correlation_adjustment()` | `correlation_check.py:794` | Tổng hợp DXY/VIX/yields; nhận flag pair-aware và gọi `_vix_score()` |
| `_vix_score()` | `correlation_check.py:522` | Bước 7 — base VIX score, eligible-map lookup và side-aware modulation |
| `compute_vix_pair_sensitivity()` | `vix_pair_backtest.py:319` | Backtest ΔVIX% so với pair returns trên common close dates |
| `sensitivity_map_ineligibility_reason()` | `vix_pair_backtest.py:716` | Giải thích vì sao map không được phép tác động runtime |

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
| **Yahoo Finance (^VIX)** | `news_service.py`, `market_data_service.py` | `_fetch_vix()`, correlation context | VIX index | Tier3 diagnostic-only (`vix_applied_to_score=false`); scoring chỉ qua `correlation_adjustment`, pair modulation là opt-in Bước 7 |
| **Yahoo Finance (pair history)** | `scripts/run_vix_pair_backtest.py` | `run_vix_pair_backtest()` | FX `BASEQUOTE=X`, XAU `GC=F`, XAG `SI=F`, BTC `BTC-USD` | Tạo schema-2 VIX sensitivity map; XAU/XAG là futures proxy |
| **Yahoo Finance (^TNX, ^FVX)** | `news_service.py` | `_fetch_yield_spread()` | 10Y-5Y yield spread | Tier 1: yield curve (Phase 15F.2: renamed from 2s10s) |
| **AI Service (Gemini/DeepSeek)** | `news_service.py` | `_ai_currency_stance()` | hawkish/dovish/neutral per currency | Tier 1 stance only (Phase 15E: removed from Tier 3) |
| **Static Rules** | `news_service.py` | `SENTIMENT_LEXICON`, `EVENT_SEVERITY` | Keyword weights | Tier 2 + Tier 3: severity/sentiment |
| **Disk Cache** | `forex_factory_client.py` | `_cached_calendar_events()` | Calendar events cached | Giảm HTTP calls |
| **NewsService cache** | `news_service.py` | `_tier_scores_cache` | Tier scores per symbol | 5-min TTL |

---

## 5. Pipeline đầy đủ — Scanner V3 runtime

```
                            ┌──────────────────────┐
                            │   NGUỒN DỮ LIỆU      │
                            ├──────────────────────┤
                            │ ForexFactory JSON    │──► Calendar events (Tier 2)
                            │ ForexFactory HTML    │──► Actual merge
                            │ FRED API             │──► Interest rates (Tier 1)
                            │ Yahoo Finance        │──► TNX/FVX (Tier 1), VIX diagnostic
                            │ Google News RSS      │──► Headlines (Tier 1,3)
                            │ AI (Gemini/DeepSeek) │──► Stance analysis (Tier 1)
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
                            │    └─ _macro_tier3()  │──► Sentiment/Geo (0-12)
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
                            │ _step_compute_       │
                            │  correlation()       │──► DXY/VIX/yields adjustment
                            │  └─ pair-aware VIX   │    opt-in, eligible map only
                            │ _step_score_scenarios│
                            │  └─ score_scenario() │──► signal_engine.py
                            │      macro input raw  │    (0-30) → scaled to
                            │      macro_confidence │    effective contribution
                            └──────────┬───────────┘
                                       │
                              result["scenario_scores"]
                              ├─ macro_raw: raw input 0-30
                              └─ macro_alignment: 0-effective_macro_weight
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
                              row["macro_score"]     (compat lossy từ effective)
                              row["macro_bias"]      (aligned/neutral/divergent)
                              row["macro_confidence"] (0.0-1.0)
                              canonical detail reads scenario macro_raw/30
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

## 6. Công thức tính điểm — Scanner V3 runtime

### Tổng quan

```
macro_raw (0-30) = tier1_buy + tier2_buy + tier3_buy   (nếu best_side=buy)
macro_raw (0-30) = tier1_sell + tier2_sell + tier3_sell (nếu best_side=sell)
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

**Lưu ý hiện hành**: Tier 1 đã clamp từng side về 0-12 sau khi cộng yield
adjustment (`news_service.py:2351-2352`).

### Tier 2 — Lịch kinh tế (0-10 → luôn 5/5 trung lập)

**File**: `news_service.py:_macro_tier2()`
**Status**: **Phase 15C.1 — ALWAYS neutral (buy=sell=5)**

Trước đây: `buy_cal = clamp(5 - base_quality, 1, 9)` — sự kiện cho base currency làm giảm điểm buy.
**Phase 15C.1 sửa**: Calendar events không có actual-vs-forecast → không được tạo directional bias.
`buy_cal = sell_cal = 5` luôn luôn. `actual`/`forecast` chỉ dùng cho diagnostic `has_surprise_data`.

**Event risk** được theo dõi riêng qua `event_risk_score` và `event_risk_level` (low/medium/high) nhưng KHÔNG ảnh hưởng điểm directional.

### Tier 3 — Tâm lý rủi ro & Địa chính trị (0-12)

**File**: `news_service.py:_macro_tier3()`
**Status**: **Phase 15E — AI stance và VIX đã loại bỏ khỏi scoring**

| Thành phần | Điểm | Ghi chú |
|-----------|------|--------|
| Sentiment (keyword lexicon) | Biến động | Quét headlines tìm 40+ từ khóa, có negation detection |
| ~~Sentiment (AI)~~ | ~~Đã loại bỏ~~ | Phase 15E: `ai_sentiment_score * 3` không còn cộng vào raw_sentiment — AI stance chỉ ở Tier 1 |
| ~~VIX adjustment~~ | ~~Đã loại bỏ~~ | Phase 15E: `vix_adj` không còn cộng vào raw_sentiment — VIX chỉ qua `correlation_adjustment()` |
| Risk sentiment (0-8) | 0-8 | Raw sentiment mapped to 0-8, split buy/sell theo safe haven vs risk |
| Geopolitical (0-4) | 0-4 | Severity của hotspot keywords |

---

## 7. Phase 15B: `score_scenario` macro confidence fix — Scanner V3

**File**: `core/signal_engine.py:score_scenario()`

**Trước**: `effective_macro_weight = macro_cap * conf`. Surplus weight từ macro được PHÂN PHỐI LẠI cho 5 technical categories. Khi confidence giảm, technical được tăng weight → tổng điểm TĂNG (84→87→89).

**Sau (Phase 15B)**: Surplus weight bị DISCARD. Khi confidence giảm, điểm kỹ thuật không đổi, chỉ điểm macro giảm → tổng điểm GIẢM (84→80→77).

```python
# Before (bug):
weights["macro"] = effective_macro_weight
surplus = macro_cap - effective_macro_weight
for k in tech_keys:
    weights[k] += surplus_each  # WRONG: inflates tech scores

# After (fix):
weights["macro"] = effective_macro_weight
# surplus discarded — technical scores unchanged
```

---

## 8. Data Quality Provenance (Phase 15F)

**File**: `services/news_service.py:_macro_data_quality_detail()`

Per-component breakdown exposed at `latest_macro_context()["macro_data_quality_detail"]`:

```json
{
  "rates": {"available": true, "source": "fred", "is_fallback": false, "confidence": 1.0},
  "calendar": {"available": true, "source": "forex_factory", "event_count": 0, "confidence": 1.0},
  "headlines": {"base_count": 3, "base_freshness": "fresh", "base_confidence": 1.0, ...},
  "ai_stance": {"available": false, "source": "keyword_fallback", "confidence": 0.4},
  "market_proxies": {"vix": {"available": true, "level": 18.5, ...}, "yield_spread": {...}}
}
```

Key rule: **global headlines not counted for currency coverage** (`global_not_counted_for_coverage: true`).
Calendar `available` = source fetch succeeded (not event_count > 0).
Rate `available` = value parseable as float (rate=0 is valid data).

### Tier 1 (0-12): Lãi suất — "Tiền tệ nào đang thắt chặt?"

Trả lời câu hỏi: "Base currency có lợi thế lãi suất so với quote không?"

- **Rate diff**: Base có lãi suất cao hơn quote → điểm buy. Công thức tuyến tính, bão hòa ở 5% diff.
- **Rate trend**: Base đang hike, quote đang cut → điểm buy tối đa. Cả 2 hold → trung lập (2-2).
- **Stance**: AI hoặc keyword phân tích hawkish/dovish từ headlines.
- **Yield spread**: Đường cong lợi suất Mỹ đảo ngược (2s10s < 0) → cảnh báo suy thoái.

### Tier 2 (contract 0-10, runtime directional score luôn 5/5): Calendar

Runtime hiện hành không suy ra hướng từ calendar khi chưa có surprise-direction
engine chuẩn. `buy_cal = sell_cal = 5`; event count, severity, time weight và
actual/forecast chỉ tạo diagnostic `event_risk_score`, `event_risk_level` và
`has_surprise_data`. Event risk được xử lý riêng qua confidence/gate, không làm
calendar BUY/SELL lệch nhau.

### Tier 3 (0-12): Sentiment & Geopolitical

Trả lời câu hỏi: "Tâm lý thị trường hiện tại ủng hộ risk hay safe haven?"

- Risk sentiment tạo 0-8 điểm và geopolitical tạo thêm 0-4 điểm cho mỗi side.
- Các nhóm risk-on/safe-haven ở đây là heuristic từ headline sentiment, không
  phải kết luận của VIX pair backtest.
- Từ Phase 15E, `vix_adj` không còn cộng vào Tier 3; VIX trong Tier 3 chỉ là
  diagnostic. Trong Scanner V3, contribution VIX đi qua
  `correlation_adjustment`. Target V4 chỉ giữ dữ liệu này trong
  `MacroAssessment`/`MacroGate`, không đưa vào `TechnicalSignalScore`.
- Bước 7 chỉ modulate VIX penalty khi flag bật và pair có bằng chứng actionable
  trong eligible map. Snapshot 2026-08-09 không xác nhận bất kỳ JPY pair nào.

---

## 9. Trọng số từng Tier

| Tier | Phạm vi | Trọng số trong 30 |
|------|--------|-------------------|
| Tier 1 (Lãi suất) | 0-12 | 40% |
| Tier 2 (Calendar) | runtime luôn 5 | 16.7% của raw scale 30 ở trạng thái hiện hành |
| Tier 3 (Sentiment) | 0-8 (risk) + 0-4 (geo) = 0-12 | 40% |

Tier 1 và Tier 3 đều có cap 12. Tier 2 giữ contract 0-10 nhưng runtime hiện hành
phát hành 5/5 trung lập cho tới khi có surprise-direction engine chuẩn.

**Lưu ý**: Điểm trung lập mặc định là 15/30 (không có lợi thế cho bên nào).

---

## 10. Điều kiện "Thuận lợi / Trung lập / Bất lợi" — Scanner V3

**File**: `core/scanner.py:438-456` — `_classify_macro_bias()`

```python
macro_buy  = scores["buy"]["macro_alignment"]     # 0-effective_macro_weight
macro_sell = scores["sell"]["macro_alignment"]    # 0-effective_macro_weight
macro_diff = macro_buy - macro_sell                 # ±effective_macro_weight

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

**Threshold compatibility row**: ±5 trên effective contribution, không phải ±5
trên raw scale 30. Tỷ lệ khoảng 33% base cap 15 hoặc 25% base cap 20 chỉ đúng khi
confidence=1; confidence thấp làm `effective_macro_weight` nhỏ hơn, nên threshold
có thể chiếm tỷ lệ lớn hơn hoặc không thể đạt.

**Ghi chú hiện hành**: UI đã map cả `"conflict"` và `"divergent"`. Canonical
Scanner Detail ưu tiên `scenario_scores[selected_side].macro_raw` và
`macro_status`; `row["macro_score"]`/`macro_bias` chỉ là compatibility path.
Riêng `row["macro_score"]` dùng `int(value or 15)`, nên effective 0 bị coercion
thành 15; không được dùng field này để suy ngược canonical raw/effective score.

---

## 11. Giải thích điểm 3/30

Mô tả 3/30 bên dưới là **ví dụ lịch sử trước Phase 15C.1**, khi Tier 2 từng tạo
directional score. Runtime hiện hành giữ Tier 2 ở 5/5, nên không được dùng ví dụ
này để giải thích score mới.

Điểm 3/30 từng là trường hợp **cực kỳ bất lợi** cho một hướng:

1. **Tier 1 (lãi suất)**: Quote có lãi suất cao hơn nhiều + base đang cut + quote đang hike + stance dồn về quote
2. **Tier 2 (calendar)**: Nhiều sự kiện quan trọng cho base, ít cho quote → base quality cao → `5 - quality` thấp
3. **Tier 3 (sentiment)**: Risk_off + base là risk currency → điểm thấp

Điểm thấp nhất có thể: Tier1 âm (yield adj), Tier2=1 (clamp), Tier3 ~0 → tổng có thể < 3.

**Mặc định**: `15/30` — điểm trung lập khi không đủ dữ liệu hoặc cân bằng.

---

## 12. Cache

| Cache | Vị trí | TTL | Ghi chú |
|-------|--------|-----|---------|
| `_tier_scores_cache` | `news_service.py:65` | 5 phút (qua `_preload_cache_ttl`) | Cache per symbol — tránh tính lại macro score liên tục |
| `_calendar_cache` | `forex_factory_client.py:136` | 24 giờ | Calendar events từ FF |
| `_stance_cache` | `news_service.py:70` | 30 phút | AI stance per currency |
| `interest_rate_service._CACHE` | `interest_rate_service.py:40` | 6 giờ | Lãi suất từ FRED |
| Preload cache | `news_service.py:179` | 5 phút | Toàn bộ macro context cho tất cả symbols |
| `_advanced_flag_cache` | `news_service.py:131` | 60 giây | Cache flag Bước 7 (`vix_pair_aware_enabled`); lỗi đọc settings → flag false |
| VIX sensitivity cache | `correlation_check.py:18-124` | Fingerprint + TTL map 90 ngày | Reload khi path/mtime/size đổi; eligibility được recheck mỗi call nên stale tự flat |

**Refresh**: Scanner gọi `preload_macro_contexts()` mỗi lần quét (có 5-min guard). Sau đó mỗi symbol gọi `data_quality_flags()` → `latest_macro_context()` có cache check.

---

## 13. AI tham gia ở đâu

| Bước | Method | Vai trò AI |
|------|--------|-----------|
| **Stance analysis** | `_ai_currency_stance()` (news_service.py:666) | Đọc headlines → phân loại hawkish/dovish/neutral |
| **Tier 1** | `_compute_macro_tiers()` → `_macro_tier1()` | Dùng stance từ AI để tính stance score |
| **Tier 3** | `_macro_tier3()` | AI stance vẫn được thu làm diagnostic nhưng `ai_applied_to_score=false`; scoring dùng keyword sentiment + geopolitical |
| **Fallback** | `_ai_currency_stance()` | Nếu AI lỗi → `currency_stance()` keyword-based |

AI không tham gia trực tiếp vào Tier 2 (calendar). AI stance ảnh hưởng Tier 1 qua `base_stance`/`quote_stance`.

---

## 14. Đánh giá kiến trúc

### Điểm mạnh

- **3-tier separation rõ ràng**: Lãi suất, Calendar, Sentiment — mỗi tier độc lập, dễ hiểu
- **Multi-source**: Kết hợp 7+ nguồn dữ liệu (FRED, FF, Yahoo, RSS, AI, static config)
- **Có fallback ở mọi tầng**: AI → keyword, FRED → ForexFactory → JSON file
- **Confidence scoring**: `_macro_data_quality()` đánh giá độ tin cậy, freshness_multiplier điều chỉnh
- **Cache đa tầng**: Calendar (24h), rates (6h), stance (30m), tier scores (5m)

### Điểm yếu

- **Compatibility field lossy**: `row["macro_score"]` lấy effective contribution
  qua `value or 15`, nên effective 0 bị đổi thành 15; canonical consumer phải đọc
  `scenario_scores[selected_side]`.
- **Tier 2 chưa có directional edge**: runtime cố ý giữ 5/5 cho tới khi có
  surprise-direction engine được chuẩn hóa.
- **Hardcode trong Tier 2 diagnostic**: `EVENT_SEVERITY` chỉ có một tập pattern
  giới hạn, có thể bỏ lỡ event khi tính event-risk diagnostic.
- **Không có trọng số tier động**: composition macro giữ cấu trúc cố định, không
  tự đổi theo regime.
- **Actual/forecast chỉ là diagnostic**: chưa có normalization theo từng loại
  event/currency để dùng an toàn cho hướng BUY/SELL.

---

## 15. Bước 5 / Bước 6 — đã gỡ (16/08/2026)

Bước 5 (AI Event Impact Assessment + derate `macro_confidence`) và Bước 6 (AI
Macro Verdict) đã được gỡ khỏi code theo quyết định của owner ngày 16/08/2026:
module, script kiểm chứng, settings flag, UI checkbox, journal/cache wiring và
tests tương ứng không còn trong codebase. Đường live Scanner V4 vốn không tiêu
thụ hai bước này nên quyết định live không đổi. Sàn `macro_confidence` 0.15 vô
điều kiện trong `_step_compute_correlation()` được giữ lại (không thuộc derate);
event-window Bước 3 (`MACRO_HIGH_IMPACT_EVENT_NEARBY`, cửa sổ 0.5-4h, factor 0.8
hardcode) vẫn hoạt động. Chi tiết: dòng **Gỡ shadow** trong changelog ở trên và
[`../architecture/runtime-status.md`](../architecture/runtime-status.md).

---

## 18. Bước 7 — VIX Pair Sensitivity

### Mục đích và ranh giới

Bước 7 thay penalty VIX cào bằng bằng một modulation theo symbol và side, nhưng
chỉ khi dữ liệu của chính hệ thống xác nhận quan hệ. Production scoring không
hardcode JPY/AUD/NZD; seed diagnostic còn assumption tĩnh nhưng luôn ineligible.

Đây là contract VIX của Scanner V3. Với target V4, cùng dữ liệu pair-aware là
input của `MacroAssessment`/`MacroGate`; nó không được sửa
`TechnicalSignalScore`, `FinalScore` hoặc ranking bằng phép cộng/trừ điểm.

Bước 7 không thay VIX ở các nơi khác:

- Tier 3 tiếp tục có `vix_applied_to_score=false`;
- `check_vix_context` và VIX diagnostics không đổi;
- VIX trong `risk_engine` không đổi;
- bonus VIX `<15` vẫn là `+2` cho mọi pair.

### Flag và luồng dữ liệu

```text
config.settings.AdvancedSettings.vix_pair_aware_enabled=false
  → SettingsService load/save
  → SettingsScreen checkbox (Advanced)
  → NewsService._read_all_advanced_flags() [cache 60s, fail-closed]
  → data_quality_flags["vix_pair_aware_enabled"]
  → AnalysisPipeline._step_compute_correlation()
  → compute_correlation_adjustment(..., vix_pair_aware_enabled=flag)
  → _vix_score(..., pair_aware_enabled=flag)
```

Flag OFF, pair không actionable, direction không rõ hoặc không còn candidate map
eligible đều trả về VIX base contribution. Candidate APPDATA lỗi/stale bị bỏ
qua trước khi loader thử repo/bundled fallback. Runner không được quyền tự bật
flag.

### Map và runtime eligibility

Loader ưu tiên `%APPDATA%/ai-market-analyst/vix_pair_sensitivity.json`, rồi mới
dùng `data/vix_pair_sensitivity.json` trong repo/bundle. Cache fingerprint theo
path/mtime/size để hot-reload và recheck TTL mỗi lần dùng.

Schema-2 eligibility yêu cầu:

- `is_seed=false`, `status=validated`, schema/alignment method hiện hành;
- tối thiểu 120 VIX/pair common-date returns;
- pair records có finite correlation, p-value, factor và significance fields
  nhất quán;
- TTL 90 ngày chưa hết;
- có ít nhất một pair `actionable=true`.

Seed map chỉ còn phục vụ sanity/tooling và luôn bị runtime từ chối. Writer dùng
temporary file + atomic replace để tránh map nửa chừng.

### Backtest engine và runner

`scripts/run_vix_pair_backtest.py` tải daily data `2y` cho `^VIX` và 31 symbol,
dùng 252 return observations. Engine intersect **close dates trước khi tính
returns**, do đó cả hai chuỗi dùng cùng interval cho từng observation.

Pair actionable khi:

```text
common-date observations >= 120
AND abs(Pearson r) > 0.15
AND two-sided Fisher-z approximate p <= 0.05
```

Không actionable thì factor bị neutralize về `1.0`, direction về
`indeterminate`; correlation thô vẫn được giữ trong report để review.

### Công thức runtime

```text
base VIX: >25 => -5; >20 => -2; <15 => +2; còn lại => 0

aligned contribution = base_penalty × factor
opposed contribution = base_penalty × [1 + (1-factor) × 0.2]
indeterminate/fallback = base_penalty
```

Factor do backtest engine hiện hành sinh có floor 0.10; eligibility layer chỉ
kiểm tra factor finite trong `[0,1]` và chưa enforce floor như schema invariant.
Opposed-flow không bao giờ được discount và có thể tăng penalty tối đa 20%; tổng
range của `compute_correlation_adjustment` khi pair-aware có thể xuống `-12`
thay vì range flat cũ `-11`.

### Evidence snapshot 2026-08-09

Run thật dùng window 2025-08-07 → 2026-08-07, 252 VIX returns, 31/31 pair đủ dữ
liệu. Chỉ ba pair qua gate raw hiện hành:

| Pair | r | p | Factor |
|---|---:|---:|---:|
| BTC/USD | -0.4341 | <0.000001 (report round thành 0) | 0.56 |
| XAG/USD | -0.1786 | 0.004385 | 0.96 |
| XAU/USD | -0.1716 | 0.006233 | 0.97 |

Cả 7 JPY pairs và AUD/NZD không actionable. Bước 7 vì vậy **không chứng minh**
JPY là safe haven trong sample này; hệ thống giữ các pair đó ở flat VIX
penalty. XAU/XAG dùng futures proxy `GC=F`/`SI=F`.

### Trạng thái và gap còn mở

- Feature vẫn default OFF; runtime settings hiện hành được ghi riêng trong
  `../architecture/runtime-status.md`.
- Raw p-values chưa có multiple-testing correction; BH-FDR 5% trên snapshot
  chỉ giữ BTC/USD. Chưa có rolling/regime split hay spike-conditioned test.
- Runner không overwrite map cũ khi run mới đủ dữ liệu nhưng `0 actionable`,
  nên operator phải tắt flag trước revalidation và giữ OFF nếu hypothesis bị
  từ chối bởi gate hiện hành.
- Journal mới có analysis/correlation aggregate, chưa có map provenance,
  factor/direction hay VIX contribution riêng.
- PyInstaller bundle tracked map, nhưng chưa bundle runner/docs và UI chưa có
  source/age/stale status.

Runbook, evidence và các giới hạn vận hành được hợp nhất ngay trong
[mục Bước 7 của tài liệu này](#18-bước-7--vix-pair-sensitivity), gồm Flag/luồng
dữ liệu, map eligibility, backtest runner, công thức runtime, evidence snapshot
và gap còn mở. Không tham chiếu các file Step 7 tách rời không tồn tại.

### Kiểm chứng

- `tests/test_vix_pair_sensitivity.py`;
- `tests/test_step7_review_fixes.py`;
- `tests/test_vix_pair_backtest_runner.py`;
- regression `tests/test_step2_correlation.py`.

Full suite sau remediation: **2615 passed, 8 skipped, 17 xfailed, 4 warnings**.

---

## 19. Các vấn đề phát hiện

| # | Vấn đề | Mức độ | Vị trí |
|---|--------|--------|--------|
| **1** | Lịch sử: `_classify_macro_bias` trả về "divergent" trong khi UI từng chỉ map "conflict" | Resolved | UI hiện map cả `divergent` và `conflict` |
| **2** | Lịch sử: Tier 1 từng có thể vượt 12 do yield adjustment | Resolved | Runtime hiện clamp 0-12 tại `news_service.py:2351-2352` |
| **3** | `EVENT_SEVERITY` hardcode, thiếu nhiều sự kiện quan trọng | Low | `news_service.py:823-828` |
| **4** | Tier 2 contract 0-10 nhưng runtime cố ý luôn 5/5 directional-neutral | Accepted constraint | Chờ surprise-direction engine chuẩn |

---

## 20. Đề xuất cải tiến (KHÔNG sửa code — chỉ đề xuất)

1. **Resolved — mismatch "divergent" / "conflict"**: UI hiện hỗ trợ cả hai key; giữ compatibility khi đọc snapshot cũ.
2. **Resolved — clamp Tier 1 về 0-12**: runtime đã clamp từng side sau yield adjustment.
3. **Mở rộng EVENT_SEVERITY**: Thêm patterns từ calendar parser hoặc dùng impact field thay vì keyword match
4. **Thiết kế surprise-direction engine trước khi đổi Tier 2**: chỉ dùng actual
   tốt hơn/bằng/kém forecast khi có normalization theo từng event/currency; cho
   tới lúc đó giữ directional score 5/5.
5. **Không đưa VIX trở lại Tier 3**: đề xuất lịch sử “VIX > 25 tăng trọng số
   Tier 3” bị loại bởi Phase 15E/Bước 7; VIX chỉ đi qua
   `correlation_adjustment` để tránh double-count.

## 21. Scanner V4 — runtime live từ 15/08/2026

Quyết định ngày 11/08/2026 không bỏ tính năng macro, nhưng thay đổi boundary:

- `TechnicalSignalScore` 0–100 chỉ gồm Trend, Momentum, Location và SMC;
- Risk/news/spread/data/connectivity/volatility đi qua `MarketSafetyGate`, không
  tạo điểm thưởng hoặc penalty;
- macro raw BUY/SELL, confidence, status, correlation và event provenance được
  giữ trong `MacroAssessment`;
- macro chỉ có thể cap/block/caution qua `MacroGate`; macro thuận không cộng
  điểm, không promote setup yếu và không làm tie-break số trong ranking;
- AI macro dimension bị loại hoàn toàn (16/08/2026, quyết định owner): không
  `ai_verdict` dimension, không AI adjustment/veto; các dimension còn lại của
  `MacroGate` là deterministic và cap/block luôn kèm reason code;
- `FinalScore` không được tái đưa Macro hoặc Risk vào score qua fallback.

Migration đã hoàn tất bằng **direct atomic cutover** sang `scanner-v4` /
`scanner-features-v4` ngày 15/08/2026: không phát hành legacy/new score song
song, không shadow V3/V4 và không dùng disagreement với V3 làm tiêu chí
validation. Artifact/config V3 chỉ được giữ read-only cho audit/replay.

Nguồn chuẩn duy nhất cho contract V4 là
[`../scanner/scanner-v4-architecture.md`](../scanner/scanner-v4-architecture.md).
Mọi `macro_alignment`/`signal_score` ở các mục mô tả Scanner V3 phía trên là
contract composite V3 (giữ cho audit/replay), không phải mô tả runtime V4.
