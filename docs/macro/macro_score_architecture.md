# Macro Score Architecture & Phase 15 Changelog

**Last updated**: 2026-08-09
**Status**: Production V1 stable, V2 in shadow data collection; Bước 7 VIX
pair-aware đã có data-backed map nhưng vẫn opt-in/default OFF và chưa xác nhận
giả thuyết JPY/AUD/NZD

---

## Phase 15 Changelog Summary

| Phase | Date | Change | Impact |
|-------|------|--------|--------|
| **15A** | 2026-07-23 | Audit macro scoring contracts + tests | 15 tests, no code change |
| **15B** | 2026-07-23 | Remove surplus weight redistribution in `score_scenario` | Confidence decrease no longer increases score |
| **15C** | 2026-07-23 | Tier 2 calendar always neutral (buy=sell=5) | Calendar events no longer create fake directional bias |
| **15C.1** | 2026-07-23 | Harden: `actual`/`forecast` diagnostic only, never directional | Event risk tracked as separate diagnostic field |
| **15D** | 2026-07-23 | Add Macro V2 pair-relative shadow model | New `_compute_macro_v2()` — currency strength diff |
| **15D.1** | 2026-07-23 | Harden V2: exact symmetry (sell=30-buy), missing→neutral | Added confidence + availability tracking |
| **15D.2** | 2026-07-23 | Expose `macro_v2` in `latest_macro_context` + scanner | End-to-end shadow diagnostics |
| **15E** | 2026-07-23 | Remove VIX/AI double-count from Tier 3 | AI stance only in Tier 1; VIX only via `correlation_adjustment` |
| **15F** | 2026-07-23 | Add `macro_data_quality_detail` provenance breakdown | Per-component availability, source, freshness, confidence |
| **15F.1** | 2026-07-23 | Fix rates availability (rate=0 valid), no re-fetch | Calendar confidence based on source fetch, not event count |
| **15F.2** | 2026-07-23 | Rename yield spread: `yield_spread_2s10s` → `yield_spread_10y_5y` | ^TNX-^FVX = 10Y-5Y, deprecated alias kept |
| **15G** | 2026-07-23 | V1 vs V2 comparison script + shadow metrics | `scripts/compare_macro_v1_v2.py` |
| **15G.1–6** | 2026-07-23 | Sensitivity grid, fix symbol parsing, edge deadband | Config A (db=2) and B (db=3) candidates |
| **15G.7** | 2026-07-23 | Forward outcome validation tool | `scripts/validate_macro_v2.py` — record/label/report |
| **Bước 5** | 2026-08-07 | AI Event Impact Assessment — derate macro_confidence cho sự kiện high-impact trong 4-48h (shadow → active) | Module `event_impact_assessor.py`, derate trong pipeline, reason code mới, UI warning |
| **Bước 5 review fixes** | 2026-08-07 | Fix theo báo cáo review: cờ derate/verdict bật được từ UI + sống sót qua lưu cài đặt; journal chỉ ghi assessment AI mới (dedup); tính lại hours_until trước derate (hết double-derate quanh mốc 4h); confidence gate cap ≤ 0.85; tài liệu sửa theo code thật | R9 (kết quả nhìn thấy được) hoạt động thực tế |
| **Bước 7 remediation** | 2026-08-09 | Pair-aware VIX trở thành opt-in, data-gated; sửa opposed-flow penalty, common-date alignment, runtime path/TTL/cache và thêm runner | Candidate ineligible bị bỏ qua; không còn eligible candidate → flat; backtest thật 31/31 pair, 3 raw-actionable |

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
| `services/news_service.py` | Service — `_compute_macro_tiers()` tính 3-tier (0-30) + `_compute_macro_v2()` shadow |
| `services/event_impact_assessor.py` | Bước 5 — AI event impact assessment logic, in-memory cache 2 tầng TTL, decision table |
| `scripts/validate_event_assessment.py` | Bước 5 — công cụ kiểm chứng priced_in (record/label/report) |
| `data/event_assessment_journal.jsonl` | Bước 5 — journal assessments (gitignored) |
| `data/event_assessment_labels.jsonl` | Bước 5 — ground-truth labels (gitignored) |
| `tests/test_step5_event_impact.py` | Test — 39 tests cho parser, decision table, cache, orchestrator |
| `tests/test_step5_shadow_wiring.py` | Test — 11 tests cho shadow wiring news_service → pipeline |
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
| `EventImpactAssessor` | `event_impact_assessor.py` | Bước 5 — đánh giá tác động sự kiện 4-48h, gọi AI, cache, decision table |
| `EventImpactAssessment` | `event_impact_assessor.py` | Bước 5 — dataclass kết quả đánh giá 1 sự kiện |
| `EventImpactAssessmentCache` | `event_impact_assessor.py` | Bước 5 — **in-memory** cache 2 tầng TTL cho assessment (không ghi disk) |

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
| `_macro_tier3()` | `news_service.py:2511` | Tier 3: Tâm lý rủi ro & Địa chính trị (0-8) |
| `_macro_data_quality()` | `news_service.py:2709` | Chất lượng dữ liệu vĩ mô (0.0-1.0) |
| `compose_scenario_score()` | `signal_engine.py:90` | Điểm tổng hợp (technical + macro + risk) |
| `assess_upcoming_events()` | `event_impact_assessor.py:529` | Bước 5 — gọi AI đánh giá tác động, cache, fallback |
| `derate_factor()` | `event_impact_assessor.py:279` | Bước 5 — tính hệ số derate từ decision table |
| `select_dominant_assessment()` | `event_impact_assessor.py:318` | Bước 5 — chọn assessment nghiêm trọng nhất cho cặp |
| `_preload_event_impact_assessments()` | `news_service.py:483` | Bước 5 — preload assessment trong background |
| `_upcoming_event_assessments_for_symbol()` | `news_service.py:640` | Bước 5 — lọc assessment khớp cặp tiền |
| `_select_event_ahead_payload()` | `analysis_pipeline.py:802` | Bước 5 — chọn assessment từ data_quality |
| `_step_compute_correlation()` | `analysis_pipeline.py:630` | Bước 5 derate + floor và Bước 7 flag wiring trong bước correlation |
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

## 5. Pipeline đầy đủ

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
                            │ _step_compute_       │
                            │  correlation()       │──► DXY/VIX/yields adjustment
                            │  └─ pair-aware VIX   │    opt-in, eligible map only
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

## 7. Phase 15B: `score_scenario` macro confidence fix

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

## 8. Macro V2 — Pair-Relative Currency Strength (SHADOW)

**File**: `services/news_service.py:_compute_macro_v2()`
**Status**: Shadow mode — NOT used in scoring/gate/ranking

### Formula

```
base_strength  = rate_score(base)  + trend_score(base)  + stance_score(base)   [0-12]
quote_strength = rate_score(quote) + trend_score(quote) + stance_score(quote)  [0-12]
pair_edge      = base_strength - quote_strength                                 [-12,+12]
buy_v2         = round(clamp(15 + pair_edge * 1.25, 0, 30))
sell_v2        = 30 - buy_v2   (exact symmetry)
confidence     = fraction of 6 components with valid data (0.0-1.0)
```

### Key differences from V1

| | V1 | V2 |
|---|---|---|
| Components | 3 tiers (rate, calendar, sentiment) | rate + trend + stance only |
| Calendar | Neutral (5/5) | Not included |
| VIX | Correlation adjustment only | Not included |
| Symmetry | buy + sell can be anything | **buy + sell = 30 always** |
| Base/quote reversal | Implicit via split scores | **Explicit via pair_edge sign flip** |
| Missing data | Falls back to neutral | Confidence tracking per component |

### Config candidates (tested in shadow, not production)

| Config | Deadband | Multiplier | Behavior |
|--------|----------|------------|----------|
| A | 2 | 1.0 | \|edge\| ≤ 2 → neutral 15/15; else directional |
| B | 3 | 1.0 | \|edge\| ≤ 3 → neutral 15/15; else directional |

### Forward validation

Tool: `scripts/validate_macro_v2.py` — record/label/report cycle.
Data: `data/shadow_records.jsonl` (gitignored).
Target: >=200 labeled rows + >=5 trading days before rollout decision.

---

## 9. Data Quality Provenance (Phase 15F)

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

### Tier 2 (0-10): Calendar — "Có sự kiện nào sắp gây biến động không?"

Trả lời câu hỏi: "Trong 72h tới, currency nào có nhiều sự kiện quan trọng?"

- Ít sự kiện cho base → ít bất định → điểm buy cao
- Nhiều sự kiện → rủi ro biến động → điểm thấp
- Sự kiện càng gần, severity càng cao → quality càng lớn

### Tier 3 (0-8): Sentiment — "Thị trường đang risk_on hay risk_off?"

Trả lời câu hỏi: "Tâm lý thị trường hiện tại ủng hộ risk hay safe haven?"

- Các nhóm risk-on/safe-haven ở đây là heuristic từ headline sentiment, không
  phải kết luận của VIX pair backtest.
- Từ Phase 15E, `vix_adj` không còn cộng vào Tier 3; VIX trong Tier 3 chỉ là
  diagnostic. VIX scoring thật đi qua `correlation_adjustment`.
- Bước 7 chỉ modulate VIX penalty khi flag bật và pair có bằng chứng actionable
  trong eligible map. Snapshot 2026-08-09 không xác nhận bất kỳ JPY pair nào.

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
| `_advanced_flag_cache` | `news_service.py:131` | 60 giây | Cache flags Bước 5/6/7; lỗi đọc settings → mọi flag false |
| VIX sensitivity cache | `correlation_check.py:18-124` | Fingerprint + TTL map 90 ngày | Reload khi path/mtime/size đổi; eligibility được recheck mỗi call nên stale tự flat |

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

---

## 16. Bước 5 — AI Event Impact Assessment (4-48h)

**Status**: Active (Prompt 4 — derate enabled behind flag `event_impact_derate_enabled`)
**Files**: `services/event_impact_assessor.py`, `core/analysis_pipeline.py`, `services/news_service.py`

### Mục đích

Bước 5 dùng AI để đánh giá tác động của sự kiện kinh tế high-impact trong cửa sổ 4-48 giờ tới. Kết quả được dùng **chỉ để phòng thủ**: giảm `macro_confidence` và hiển thị cảnh báo — không bao giờ tăng điểm hoặc tạo directional bias.

**Cửa sổ đánh giá ≠ cửa sổ derate.** Assessment được tạo cho mọi sự kiện high-impact trong (4, 48]h và luôn hiện trong payload/cảnh báo UI. Nhưng derate chỉ kích hoạt khi `hours_until ≤ risk_window_hours`. Vì parser validate `1 ≤ risk_window_hours ≤ 24` (AI bị buộc trả 1-24), sự kiện còn xa hơn 24h KHÔNG BAO GIỜ bị derate — chúng chỉ được đánh giá + cảnh báo. Ô "high + priced_in → 0.91" của bảng decision vì vậy không đạt được qua derate thực tế (xem ghi chú dưới bảng).

**Proxy giá gần đây.** Prompt AI nhận headlines liên quan sự kiện + stance 2 đồng tiền, KHÔNG nhận dữ liệu biến động giá gần đây (spec deviation đã chốt): headlines được chọn làm proxy cho mức độ price-in vì tin là thứ thị trường phản ứng trước tiên. Nếu sau này cần, bổ sung trường price volatility vào prompt là thay đổi cục bộ trong `build_event_prompt()`.

**Floor 0.15 luôn áp dụng.** Pipeline áp `macro_confidence = max(conf, 0.15)` bất kể cờ derate bật/tắt (chủ ý từ Prompt 4 — bảo vệ confidence khỏi về 0 khi nhiều tầng phòng thủ chồng nhau). Hệ quả: flag OFF không còn "bit-identical" với pipeline trước Bước 5 ở các case confidence < 0.15. Test `test_step5_floor_kich_hoat_that` khóa hành vi này.

### Ranh giới với Bước 3

| | Bước 3 | Bước 5 |
|---|---|---|
| **Cửa sổ** | 0.5h < hours_until ≤ 4.0h | 4.0h < hours_until ≤ 48.0h |
| **Cơ chế** | Hardcode factor 0.8 | AI decision table (0.70-1.0) |
| **Reason code** | `MACRO_HIGH_IMPACT_EVENT_NEARBY` | `MACRO_HIGH_IMPACT_EVENT_AHEAD` |
| **Mốc 4.0h** | Thuộc Bước 3 | Không overlap |

### Luồng dữ liệu

```
ForexFactory Calendar
        │
        ▼
NewsService._preload_event_impact_assessments()
  ├─ Lọc sự kiện high-impact, tính lại hours_until từ time_utc
  ├─ Gọi EventImpactAssessor.assess_upcoming_events()
  │   → trả (assessments, fresh_ai_keys)
  │   ├─ Kiểm tra cache (key = event_key + AI fingerprint, in-memory)
  │   ├─ Gọi AI (Gemini/DeepSeek) → parse JSON → EventImpactAssessment
  │   └─ Fallback: magnitude="medium", priced_in="unknown" → factor 0.85
  ├─ Lưu kết quả vào self._last_event_assessments
  └─ Ghi journal CHỈ cho assessment có event_key ∈ fresh_ai_keys
     (cache hit không ghi lại — dedup theo chu kỳ)
        │
        ▼
NewsService.data_quality_flags()
  ├─ _upcoming_event_assessments_for_symbol() → lọc theo currency
  └─ Trả về data_quality["upcoming_event_assessments"]
        │
        ▼
AnalysisPipeline._step_compute_correlation()
  ├─ _select_event_ahead_payload() → select_dominant_assessment()
  ├─ Nếu flag event_impact_derate_enabled = True:
  │   ├─ TÍNH LẠI hours từ assessment.time_utc (_hours_until_high_impact)
  │   │  — payload.hours_until có thể lệch ≤5 phút, dùng số cũ sẽ gây
  │   │    double-derate với Bước 3 quanh mốc 4h
  │   ├─ derate_factor(assessment, hours)
  │   ├─ self._macro_confidence_in *= factor
  │   └─ self._macro_event_ahead_reason_code = MACRO_HIGH_IMPACT_EVENT_AHEAD
  ├─ Floor: max(self._macro_confidence_in, 0.15)  (luôn áp dụng)
  └─ Payload: result["macro"]["event_assessments"][0]["applied_derate"]
        │
        ▼
ScannerDetailScreen._dialog_card_macro()
  └─ Nếu applied_derate ≠ None → hiển thị ⚠ warning
```

### Schema JSON AI Response

AI trả về JSON PHẲNG (không bọc trong object `"assessment"`), parser nhận cả khi bị bọc markdown fence:

```json
{
  "magnitude": "high" | "medium" | "low",
  "priced_in": "priced_in" | "partial" | "not_priced_in" | "unknown",
  "expected_direction": "currency_up" | "currency_down" | "two_way" | "unknown",
  "risk_window_hours": 1-24,
  "confidence": 0.0-1.0,
  "evidence": ["string", ...]
}
```

Validate (`_validate_event_json`): đủ 6 trường, enum đúng tập cho phép, `1 ≤ risk_window_hours ≤ 24`, `0 ≤ confidence ≤ 1`, evidence là list[str]; evidence rỗng mà priced_in ≠ unknown → hạ priced_in xuống `"unknown"`. Trường `confidence` được lưu vào dataclass dưới tên `ai_confidence`.

### Decision Table

| Magnitude | Penalty | Priced-in | Surplus | Factor |
|-----------|---------|-----------|---------|--------|
| high | 0.30 | not_priced_in | 1.0 | **0.70** |
| high | 0.30 | partial | 0.6 | **0.82** |
| high | 0.30 | priced_in | 0.3 | **0.91** |
| medium | 0.15 | not_priced_in | 1.0 | **0.85** |
| medium | 0.15 | partial | 0.6 | **0.91** |
| medium | 0.15 | priced_in | 0.3 | **0.955** |
| low | 0.05 | not_priced_in | 1.0 | **0.95** |
| low | 0.05 | partial | 0.6 | **0.97** |
| low | 0.05 | priced_in | 0.3 | **0.985** |

**Công thức**: `factor = 1.0 - penalty × surplus`

**Quy tắc đặc biệt**:
- `ai_confidence < 0.5` (confidence gate) → coi `priced_in` như `"unknown"` (surplus = 1.0) **VÀ cap factor ≤ 0.85** — AI thiếu tự tin không được phòng thủ NHẸ hơn AI chết hẳn (fallback medium/unknown = 0.85, nguyên tắc D6)
- `priced_in = "unknown"` → surplus = 1.0 (an toàn: giả định chưa price-in)
- Backstop: `magnitude = "high"` + `hours_until ≤ 24` → factor ≤ 0.85
- Floor: factor không bao giờ dưới 0.15
- Cap: factor không bao giờ trên 1.0
- `hours_until > risk_window_hours` → factor = 1.0 (ngoài cửa sổ rủi ro của sự kiện; vì risk_window ≤ 24 nên sự kiện 24-48h không bao giờ bị derate)

**Ô không đạt được trong thực tế**: hàng "high + priced_in → 0.91". Sự kiện ≤ 24h bị backstop kéo về ≤ 0.85; sự kiện > 24h không bị derate (risk_window ≤ 24). Ô này vẫn tồn tại trong bảng vì `derate_factor()` là hàm thuần — test vẫn tính nó — nhưng pipeline thực tế không bao giờ áp 0.91.

### Cache (in-memory)

`EventImpactAssessmentCache` giữ **1 entry duy nhất cho mỗi (event, AI fingerprint)** — không có key suffix riêng. Hai tầng TTL được suy ra từ cùng entry khi `get()`:

| Tầng | Cách tính | TTL |
|------|-----------|-----|
| Key | `json({"event_key": sha1(time_utc\|currency\|event_name), "ai": fingerprint(provider+model)})` — đổi model AI hoặc tắt AI là cache miss | — |
| Nhóm trường tĩnh (magnitude, expected_direction, risk_window_hours) | hết hạn tại `put_time + min(hours_until, 24h)` | tối đa 24h |
| Trường priced_in | `now ≥ put_time + 6h` → cờ `priced_in_stale=True` trả về caller; assessor gọi AI đánh giá lại sự kiện và **ghi đè toàn bộ entry** (không chỉ trường priced_in) | 6h |
| Negative cache | entry có `source="fallback"` bị cap TTL xuống 30 min | 30 min |
| Over-quota | sự kiện không được gọi AI vì hết quota KHÔNG được cache (không có entry) — chu kỳ sau quota hồi là gọi lại ngay | không cache |

### Fail-safe

- **AI error**: fallback `{magnitude: "medium", priced_in: "unknown"}` → factor 0.85 (fail-closed D6, không bao giờ nhẹ hơn mức này cho sự kiện trong cửa sổ)
- **Pipeline error**: try/except + `_log_step("event_impact_derate", "warning", ...)` — bỏ derate, không crash, không im lặng
- **UI error**: try/except bỏ qua warning, không crash
- **Flag mặc định TẮT**: `event_impact_derate_enabled = False` trong AdvancedSettings; bật/tắt bằng checkbox trong Settings → tab Advanced và **sống sót qua các lần lưu cài đặt** (review fix: `_save_advanced_settings()` carry-over cờ từ UI thay vì rebuild về mặc định)

### Reason Code

| Code | Message |
|------|---------|
| `MACRO_HIGH_IMPACT_EVENT_AHEAD` | "Có sự kiện vĩ mô tác động mạnh trong 4-48 giờ tới, giảm mức tin cậy vĩ mô." |

### Kiểm chứng

**Tool**: `scripts/validate_event_assessment.py`
- `label` — nhập nhãn thực tế cho sự kiện đã diễn ra
- `report` — in ma trận 3×3 (predicted vs actual priced_in) + độ chính xác hướng
- Cả 2 lệnh dedup theo `event_key` (`_latest_by_event_key`) — mỗi event chỉ đếm/liệt kê 1 lần theo dự đoán mới nhất, phòng dòng trùng từ các chu kỳ preload trước khi có dedup journal

**Journal**: chỉ ghi assessment AI MỚI trong chu kỳ (`event_key ∈ fresh_ai_keys` do `assess_upcoming_events()` trả về) — cache hit không ghi lại.

**Tests**:
- `tests/test_step5_event_impact.py` — parser, decision table, cache, orchestrator
- `tests/test_step5_shadow_wiring.py` — shadow wiring
- `tests/test_analysis_pipeline_integration.py` — derate integration
- `tests/test_step5_review_fixes.py` — các fix của báo cáo review: flag roundtrip qua SettingsService + UI, e2e R9 (applied_derate), dedup journal 2 chu kỳ, priced_in refresh >6h, negative cache hết hạn, fallback e2e, over-quota không cache, floor, double-derate mốc 4h, confidence gate cap

---

## 17. Bước 6 — AI Macro Verdict (Trọng tài vĩ mô)

### Mục đích

AI nhìn TOÀN BỘ tín hiệu macro cùng lúc (Tier 1 lãi suất, Tier 2 calendar,
Tier 3 sentiment, correlation, stance, sự kiện, chuyển động DXY) và phát hiện
mâu thuẫn giữa các tầng — thứ từng tầng riêng lẻ không thấy. AI có quyền làm
KHÓ setup, không bao giờ được làm dễ (bất đối xứng).

### Luồng dữ liệu

```
Scanner (news_service.data_quality_flags + macro_context)
  │  macro_alignment_scores {"buy","sell"} + macro_tier_detail
  │  (tier1_interest_rate / tier2_calendar / tier3_sentiment / macro_v2 / stance_journal)
  ▼
scanner_controller._build_macro_verdict_context()          [C2 fix]
  │  map tier1_interest_rate→"tier1", tier2_calendar→"tier2",
  │  tier3_sentiment→"tier3" + macro_v2 + stance
  ▼
analyze_symbol(..., ai_service=ai_svc,                    [C1 fix]
               macro_verdict_context=pkg)
  ▼
AnalysisPipeline._step_ai_macro_verdict (Step 5.5)
  │  Guard 1: flag macro_ai_verdict_enabled (data_quality)
  │  Guard 2: best_side ∈ {buy, sell}
  │  Guard 3: macro score của best_side ≥ 20 (top ~33%)
  │  _build_macro_verdict_context() bổ sung alignment, data_quality,
  │     correlation + DXY movement (_dxy_movement — 2 nến D1 gần nhất)
  ▼
MacroVerdictAssessor.assess(pair, macro_context, ai_service,
                            best_side, is_backtest)
  │  cache get → hit? trả về
  │  is_backtest=True → miss → skip_backtest_no_cache (KHÔNG gọi AI)  [M5]
  │  else → AI call trong thread riêng, timeout 15s                     [M7]
  │       → parse + validate JSON (bất đối xứng)
  │       → cache.put + journal                                         [M6/M9/M10]
  ▼
Verdict áp dụng:
  │  source ≠ "ai" → skip (fallback/skip trung tính)
  │  conviction < 0.7 → bỏ qua (reason MACRO_AI_VERDICT_SKIPPED)
  │  veto=true → gate engine giáng READY → WATCH (mac_ai_veto)
  │  adjustment ∈ [-5,0] → Step 7 trừ TRỰC TIẾP vào component macro   [C3]
  │     (0-30) của best_side rồi tính lại signal_score
  ▼
Result: macro.macro_ai_verdict (to_dict) + macro.macro_ai_deducted
        reason codes: MACRO_AI_VETO / MACRO_AI_ADJUSTMENT / MACRO_AI_VERDICT_SKIPPED
```

### Schema JSON AI Response

```json
{
  "bias": "aligned"|"conflict"|"unclear",
  "conviction": 0.0-1.0,
  "conflicts": ["mô tả mâu thuẫn 1", "..."],
  "veto": true|false,
  "adjustment": -5..0,
  "evidence": ["căn cứ 1", "..."]
}
```

Parser nghiêm ngặt (`parse_verdict_json`): bias ngoài enum → reject; conviction
ngoài [0,1] → reject; adjustment ngoài [-5,0] → reject (bất đối xứng tuyệt đối);
`veto=true` mà không có conflicts → vô hiệu hóa veto; `bias=conflict` mà không
có conflicts → hạ thành `unclear`.

### Decision Rules

| Tín hiệu | Hành động | Lý do |
|---|---|---|
| `veto=true`, conviction ≥ 0.7 | Gate engine → `WATCH_ONLY` | Mâu thuẫn nghiêm trọng giữa các tầng |
| `adjustment=-N` (N=1..5) | Trừ N điểm macro component (0-30) của best_side | Làm khó, không làm dễ |
| `conviction < 0.7` | Bỏ qua toàn bộ verdict | Không chắc chắn thì không can thiệp |
| `source ≠ "ai"` (fallback/skip) | Không áp dụng gì | Fail-closed |

### Cache & Journal

- **Cache disk**: `<repo>/data/macro_verdict_cache/{pair}_{date}_{side}.json`
  (Minor 10 — thống nhất với Bước 5 trong repo `data/`). Key gồm fingerprint
  (provider/model) + best_side (Major 6 — setup SELL không lãnh verdict của BUY).
- **Negative cache** (Minor 9): AI hỏng/timeout → fallback được cache với
  `expires_at_utc` = 30 phút; trong cửa sổ không gọi lại AI.
- **Journal**: `<repo>/data/macro_verdict_journal.jsonl` — 1 dòng JSONL mỗi
  verdict AI, gồm `pair`, `date`, `best_side`, `trade_result_r: null`,
  `trade_outcome: null` (Major 8 — script `scripts/validate_macro_verdict.py`
  `label` backfill outcome từ trade DB, `report` in ma trận chính xác).

### Backtest policy (Major 5)

Backtest KHÔNG gọi AI (reproducible). `BacktestRequest.macro_ai_verdict_enabled`
được set từ settings trong `backtest_controller.build_request`, đi vào
`data_quality` của `_run_analysis_snapshot`. `assess(is_backtest=True)` chạy
**read-cache-only**: đọc cache theo (pair, date, side) KHÔNG kiểm tra fingerprint
(đọc lại verdict live đã ghi); miss → `skip_backtest_no_cache` trung tính.

### Flag

`config/settings.py → advanced.macro_ai_verdict_enabled` → SettingsService →
UI checkbox (`ui/screens/settings_screen.py`) → `news_service.data_quality_flags`
→ pipeline `data_quality["macro_ai_verdict_enabled"]`. Fail-closed: mặc định
False.

### Kiểm chứng

- `tests/test_step6_macro_verdict.py` — parser, constraints, cache, assessor,
  prompt, fingerprint, gate engine
- `tests/test_step6_review_fixes.py` — fix của báo cáo review: pipeline wiring
  e2e (C1), macro_verdict_context + DXY (C2), adjustment trừ thẳng (C3),
  reason codes giữ được (M4), backtest read-cache-only (M5), cache/journal
  best_side (M6), timeout (M7), negative cache (M9), diagnostics contract (M11)
- `scripts/validate_macro_verdict.py` — `label` (backfill outcome) + `report`
  (ma trận chính xác bias/veto/adjustment)

---

## 18. Bước 7 — VIX Pair Sensitivity

### Mục đích và ranh giới

Bước 7 thay penalty VIX cào bằng bằng một modulation theo symbol và side, nhưng
chỉ khi dữ liệu của chính hệ thống xác nhận quan hệ. Production scoring không
hardcode JPY/AUD/NZD; seed diagnostic còn assumption tĩnh nhưng luôn ineligible.
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

Runbook chi tiết: `step7_vix_pair_sensitivity_operations.md`. Review lịch sử và
ma trận remediation: `step7_vix_pair_sensitivity_review.md`.

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
| **1** | `_classify_macro_bias` trả về "divergent", UI map expect "conflict" → hiển thị sai | Medium | `scanner.py:456` vs `scanner_detail_screen.py:678` |
| **2** | Tier 1 có thể vượt 12 do yield_adj không clamp | Low | `news_service.py:818-819` |
| **3** | `EVENT_SEVERITY` hardcode, thiếu nhiều sự kiện quan trọng | Low | `news_service.py:823-828` |
| **4** | Tier 2 luôn 1-9, mất khả năng đạt 0 hoặc 10 | Low | `news_service.py:887-888` |

---

## 20. Đề xuất cải tiến (KHÔNG sửa code — chỉ đề xuất)

1. **Sửa mismatch "divergent" → "conflict"**: Thêm "divergent" vào `_VN_MACRO` và inline dict ở line 678
2. **Clamp Tier 1 về 0-12**: `max(0, min(12, total))` để giữ tổng 0-30
3. **Mở rộng EVENT_SEVERITY**: Thêm patterns từ calendar parser hoặc dùng impact field thay vì keyword match
4. **Thêm actual values vào Tier 2**: Sự kiện đã có actual tốt hơn/bằng/kém hơn forecast → điều chỉnh quality
5. **Không đưa VIX trở lại Tier 3**: đề xuất lịch sử “VIX > 25 tăng trọng số
   Tier 3” bị loại bởi Phase 15E/Bước 7; VIX chỉ đi qua
   `correlation_adjustment` để tránh double-count.
