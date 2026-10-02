# Ca đấu nối (b) — Vĩ mô Scanner đọc miền Tin tức: plan cho CODER

Ngày: **2026-10-02**
Trạng thái: **DUYỆT — owner đã duyệt phương án 02/10/2026; đặc tả contract đã ghi
trong [`../macro/macro_score_architecture.md`](../macro/macro_score_architecture.md)
mục 0. Tài liệu này là kế hoạch thi hành, chưa sửa runtime.**

> Số dòng code dẫn chứng lấy tại working tree 02/10/2026 (sau lần sửa
> SNAPSHOT_STALE cùng ngày) — có thể lệch ±vài dòng khi bắt đầu ca; CODER đối
> chiếu bằng tên hàm/biến trước khi sửa.

## 0. CODER cần đọc gì và làm đến đâu?

1. Đọc contract trước khi viết dòng nào:
   - [`../macro/macro_score_architecture.md`](../macro/macro_score_architecture.md) **mục 0** (toàn bộ — nguyên tắc, mapping, fail-closed, lộ trình);
   - [`../news/news-architecture.md`](../news/news-architecture.md) §3.1 (B7), §8 (hợp đồng repository), §12, §13 (QĐ owner);
   - [`../scanner/scanner-architecture.md`](../scanner/scanner-architecture.md) §5.2/§5.3 (2 gap đã ghi).
2. Làm 4 nhóm work item tại §5 theo đúng thứ tự. **Điểm dừng bắt buộc** (báo
   kết quả + chờ xác nhận trước khi làm nhóm kế tiếp):
   - **D1** — sau WI-1 (B3 pin pass trên path cũ);
   - **D2** — sau WI-3 (module mới + test pass, CHƯA đấu nối runtime);
   - **D3** — sau WI-7 (đấu nối + xóa + toàn bộ kiểm chứng pass, một commit duy
     nhất cho WI-4→WI-7);
   - **D4** — sau WI-8 (nghiệm thu runtime + cập nhật tài liệu).
3. Nguyên tắc bất di bất dịch: **không sửa `core/macro_gate.py`,
   `MacroPolicy`, `compose_scanner`, giá trị ngưỡng**; không đưa verdict AI vào
   gate; không dual-run (path cũ bị xóa trong cùng commit đấu nối — D2 rule).

## 1. Phạm vi

| Trong phạm vi | Ngoài phạm vi (cấm đụng) |
|---|---|
| Nguồn dữ liệu `macro_raw_buy/sell` + `macro_confidence` của Scanner (đổi sang đọc `news.db` qua `NewsRepository`) | `core/macro_gate.py`, `MacroPolicy`, `core/scanner_composition.py` |
| 4 seam gọi `news_service` trong `ScannerController` + wiring `AppController` | Verdict AI (`ai_trend_verdicts`), `core/pair_bias.py` — advisory-only |
| 2 gap đã ghi: `news_events` vào safety context, `news_in_3h` thật | VIX/correlation context (`market_data_service`, Bước 7 VIX pair sensitivity, `macro_market_cache`) |
| Port công thức 3-tier sang `core/macro_tiers.py` (thuần) | `services/news_repository.py` + producers miền Tin tức (đã nghiệm thu — chỉ ĐỌC) |
| Reason code `MACRO_CALENDAR_STALE` + hint UI "Cần dán lịch FF" | Dashboard/news screen/AI dialog (ca đấu nối a riêng) |
| Xóa `news_service.py` + `forex_factory_client.py` + `interest_rate_service.py` (D2, cùng commit đấu nối) | Giao thức, UI layout ngoài 1 dòng hint ở Scanner |

## 2. Hiện trạng — bằng chứng

| Khâu | Hiện hành | Vị trí |
|---|---|---|
| Preload macro mỗi scan | `news_service.preload_macro_contexts` (fetch mạng FF/RSS/yfinance, TTL 5 phút) | `controllers/scanner_controller.py` d.738 (submit), `services/news_service.py` d.1086 |
| Freshness multiplier | `news_service.macro_freshness_status()` — theo tuổi lần fetch cuối (1.0/0.85/0.6, ngưỡng 4h/24h) | `scanner_controller.py` d.781; `news_service.py` d.1547-1562 |
| Macro context từng symbol | `news_service.data_quality_flags()` → `macro_context` (3-tier, events, headlines) | `scanner_controller.py` d.3079; `news_service.py` d.401-438 |
| News status lúc gửi lệnh | `news_service.execution_news_status()` (re-validation) | `scanner_controller.py` d.1581; `news_service.py` d.440-515 |
| Công thức 3-tier | `_compute_macro_tiers`/`_macro_tier1`/`_macro_tier2`/`_macro_tier3`/`_macro_data_quality` — nằm trong `services/`, trộn I/O | `news_service.py` d.1567, d.1876, d.1979, d.2135, d.2333 |
| AI stance Tier 1 | `_ai_currency_stance_detail` (gọi AI, cache 24h, fallback keyword) | `news_service.py` d.1639-1750 |
| Wiring | `AppController` tạo `NewsService` và tiêm vào `ScannerController` | `controllers/app_controller.py` d.20, d.74-77, d.136 |
| **Gap 1** | `build_live_market_safety_context` KHÔNG nhận `news_events` → sub-gate News không thấy event để chặn | `scanner_controller.py` d.3127-3146; gate chặn 0-30m/caution 180m tại `core/market_safety_gate.py` |
| **Gap 2** | `news_in_3h` bị hardcode `False` → regime không bao giờ thấy event gần | `scanner_controller.py` d.3374, d.3390; tiêu thụ tại `core/scanner_live_producers.resolve_technical_regime` |

Đối tác đọc (miền Tin tức, đã IMPLEMENTED): `NewsRepository.events_in_range /
items_in_range / latest_rates / rate_paths / latest_bond_yields / store_state`
(`services/news_repository.py` d.664-846); mô hình `CalendarEvent` (news_models:
`event_time_utc`, `currency`, `title`, `impact`, `forecast`, `previous`,
`actual`), `CurrencyRateTrend` (`latest.rate`, `trend` enum hike/hold/cut),
`YieldContext` (`yield_2y`, `yield_10y`, `spread_2y10y`, `delta_6m.delta_spread`),
`StoreState` (`*_state` = fresh | degraded | unavailable + `*_last_success_at`).

## 3. Thiết kế đích

### 3.1 `core/macro_tiers.py` — port nguyên thức (WI-2)

Module **thuần** (không I/O, không AI, không clock — `now` là tham số). Port
nguyên từng dòng công thức từ `news_service.py` (dẫn dẫn ở §2), chỉ tách phần
lấy dữ liệu:

```python
# hằng số lexicon port nguyên văn
CURRENCY_KEYWORDS, HAWKISH_TERMS, DOVISH_TERMS, HOTSPOT_TERMS,
EVENT_SEVERITY (d.1980), SENTIMENT_LEXICON, NEGATION_WORDS (d.2142)

def matches_currency(item: Mapping, currency: str) -> bool          # port _matches_currency (d.2766)
def currency_stance(...) / stance_value(...) / macro_score_from_delta(...)  # giữ nguyên ngữ nghĩa
def macro_themes(...) / geopolitical_hotspots(...)                   # port _macro_themes/_geopolitical_hotspots (thuần)
def macro_tier1(base, quote, base_stance, quote_stance, *, rates: Mapping, yield_payload: Mapping) -> (buy, sell, detail)
def macro_tier2(base, quote, events, *, now: datetime) -> (buy, sell, detail)
def macro_tier3(currencies, headlines, hotspots, *, vix_level=None) -> (buy, sell, detail)
def macro_data_quality(headlines, events, *, now: datetime) -> float
def compute_macro_tiers(...) -> dict   # tổng hợp đúng shape cũ {"tier1","tier2","tier3","raw_total","alignment","reasons"}
```

Quy tắc port:
- **Tier 1** (d.1876-1976): rate differential (0-4), rate trend (0-4), stance
  (0-4), yield adjustment (±2/±1 — chỉ áp cho cặp có USD) — giữ nguyên từng
  hằng số (MAX_DIFF 5.0, trend_score_map, ngưỡng spread <0 / >0.5+steepening).
- **Tier 2** (d.1979-2090): luôn neutral 5/5 (Phase 15C); severity×time_weight
  chỉ vào detail/event_risk — giữ nguyên.
- **Tier 3** (d.2135-2330): lexicon + negation + risk/safe-haven map +
  hotspot — giữ nguyên. `vix_level=None` mặc định: các trường VIX trong detail
  là `None`, `vix_applied_to_score=False` (đã diagnostic-only từ Phase 15E).
- **AI stance bỏ hẳn**: `base_stance`/`quote_stance` do caller tính bằng
  `currency_stance` (keyword) — tức đường "AI off" của code cũ. `stance_journal`
  không còn; thay bằng `stance_detail` keyword (source="keyword").
- Tier 2/Tier 3 dùng `datetime.now(UTC)` nội bộ — port thành tham số `now` để
  deterministic (fixture test ghim).

### 3.2 `services/news_macro_provider.py` — provider đọc news.db (WI-3)

Class `NewsMacroProvider` — **duck-type đúng 5 method mà Scanner đang gọi**
(tên method + tham số + shape đầu ra giữ nguyên để `ScannerController` không
phải đổi gì ngoài nguồn):

| Method | Đọc từ | Ghi chú |
|---|---|---|
| `preload_macro_contexts(symbols, progress_callback, ai_service=None, performance_tracker=None)` | 1 lần `store_state()` + đọc chung: events window, items window, `latest_rates` (toàn bộ currency của các symbol), `latest_bond_yields(["USD"])` → build context từng symbol | Không còn HTTP; progress giữ khuôn "Đang tải snapshot vĩ mô..." / "Đang phân tích vĩ mô {symbol}..."; cache in-memory TTL 5 phút (parity `_macro_context_cache_ttl`) |
| `latest_macro_context(symbol, include_latest_statements=True, ai_service=None, ...)` | cache TTL 5 phút; miss → build từ các read trên + `core.macro_tiers` | `ai_service` nhận nhưng **bỏ qua** (không gọi AI — QĐ đã ghi) |
| `data_quality_flags(symbol, buffer_minutes=30, include_latest_statements=True, ...)` | `latest_macro_context` + tính `news_in_3h`/`high_impact_event_within_30m`/`next_high_impact_event`/`resume_after` (công thức d.419-430 port nguyên) | `vix_pair_aware_enabled`: đọc `SettingsService` fail-closed False + cache 60s (port `_read_vix_pair_aware_enabled` d.172) — flag này còn dòng tiêu thụ ở route Analyze |
| `macro_freshness_status()` | `store_state()` | Mapping worst-of 4 scope: tất cả fresh → `("fresh", 1.0)`; bất kỳ degraded → `("stale", 0.85)`; bất kỳ unavailable → `("expired", 0.6)`. `age_minutes` = phút cách ingest success mới nhất (min các scope có dữ liệu; không có → 9999). Giữ key shape `{"status","age_minutes","confidence_multiplier"}` |
| `execution_news_status(symbol, *, before_minutes=30, after_minutes=30, now=None)` | `events_in_range(now-after, now+before, currencies)` (đã lọc currency) | Port logic chọn blackout d.486-504 nguyên văn (high-impact, khoảng [-after, +before], gần nhất). `available=False` + `NEWS_STATUS_UNAVAILABLE` khi scope events `unavailable` (chưa từng ingest); stale vẫn `available=True` (dữ liệu có — fail-closed độ tươi nằm ở confidence macro) |

Mapping đầu vào (provider → dạng dict mà công thức port đang đọc):

| Nguồn repository | Dict đầu ra |
|---|---|
| `CalendarEvent` | `{"currency", "event": title, "impact": impact.value, "forecast", "previous", "actual", "time_utc": event_time_utc}` — đúng key mà `_event_time` (đọc `time_utc`) và Tier 2 (đọc `event`) đang dùng |
| `NewsItem` | `{"title", "published_utc", "currencies"}` — headlines |
| `CurrencyRateTrend` | `{"rate": latest.rate, "trend": trend.value, "rate_label": f"{latest.rate:.2f}%"}` |
| `YieldContext` | `{"spread": spread_2y10y, "steepening": (delta_6m.delta_spread or 0) > 0, "ten_year_yield": yield_10y, "five_year_yield": None, "two_year_yield": yield_2y, "tnx": yield_10y, "fvx": None}` — **đổi series có chủ ý** đã ghi ở contract §0.2 (10y-5y → 2y-10y); các key `tnx`/`fvx` giữ làm alias để detail không vỡ |
| `config/interest_rates.json` | fallback cuối cho rate khi `latest_rates` không trả về currency (giữ chuỗi fallback cũ: FRED→FF→config giờ là news.db→config) |

Cửa sổ đọc (đối chiếu với code cũ trước khi chốt; nếu khác, ghi chú vào PR):
- Events: `[now − 24h, now + 72h]`, lọc theo 2 currency của symbol, **cap 8
  sự kiện** (giữ `[:8]` như `_calendar_context_from_snapshot` d.1079), ASC.
- Headlines: `items_in_range(now − 24h, now)` (cutoff 24h của
  `_macro_headlines` d.1474), lọc bằng `matches_currency` (giữ cả nhánh
  "keep global headline" d.1539 để không đổi hành vi).
- Statements: `items_in_range(now − 24h, now)` kind statement (nếu repository
  phân loại được qua `kinds`; không có → gộp chung headlines).

Lỗi đọc DB (sqliteException...) → không crash scan: context rỗng +
`macro_data_quality` tụt (−0.30/−0.10 như công thức cũ cho "không headlines /
không events") và `macro_freshness_status()` trả expired/0.6. Ghi log qua
`observability` nếu có sẵn seam — không thêm logger mới.

### 3.3 Đấu nối `ScannerController` (WI-4)

- Thuộc tính **giữ tên `self.news_service`** (đỡ phá fixture test đang
  duck-type) nhưng kiểu/đối tượng là `NewsMacroProvider`. `__init__` đổi default
  `news_service=None → NewsMacroProvider()` (bỏ import `NewsService`).
- 4 seam (d.738, d.781, d.1581, d.3079) không đổi chữ ký gọi — chỉ đổi nguồn.
- **Vá Gap 1** (`news_events`): trong `_fetch_one_symbol_mt5`, gọi
  `build_live_market_safety_context(..., news_events=tuple(events))` với
  `events = macro_context["events"]` (đã có sẵn trong packet). Đồng thời
  `news_source_verified` đổi từ `"macro_tier_detail" in macro_context` (d.3123)
  thành **scope events ≠ unavailable** (đọc từ `macro_freshness_status()` hoặc
  provider expose `store_state()` một lần mỗi scan) — đúng hợp đồng "news gate
  đọc events + trạng thái stale, fail-closed" (news-architecture §12).
- **Vá Gap 2** (`news_in_3h`): `data_quality_flags` đã trả `news_in_3h` — đưa
  vào packet (`pkt["news_in_3h"]`), `_analyze_one_symbol` đọc thay
  `news_in_3h=False` (d.3374, d.3390). Hiệu ứng dự kiến (đã ghi
  scanner-architecture §3.2): event impact cao ≤3h → regime `volatile` → trọng
  số Technical theo regime — đúng thiết kế, không đổi logic.
- `data_quality["macro_freshness"]` (d.3096) tiếp tục mang dict mới
  (status/age/multiplier + thêm `reason_codes` — xem §3.5).

### 3.4 Wiring `AppController` (WI-5)

- Bỏ `from services.news_service import NewsService` (d.20) + property
  `news_service` (d.74-77) — `AppController` chỉ còn tiêm `NewsMacroProvider`
  cho Scanner (d.136: `news_service=NewsMacroProvider()` hoặc lazy property
  `news_macro_provider`). `NewsService` không còn consumer nào sau ca này.

### 3.5 `MACRO_CALENDAR_STALE` + hint UI (WI-6)

- `core/reason_codes.py`: thêm hằng số `MACRO_CALENDAR_STALE` + message "Lịch
  kinh tế không tươi — cần dán mã nguồn trang ForexFactory (màn Quản lý tin)."
- **KHÔNG phải gate code** — không vào `MacroGate`/decision reason_codes. Nó
  nằm trong `macro_context["macro_freshness"]["reason_codes"]` (provider gắn
  khi scope events ∈ {degraded, unavailable}) và được `_analyze_one_symbol`
  copy sang `row["macro"]["freshness_reason_codes"]` (display-only, cùng chỗ
  với `macro_confidence` d.3501).
- `ui/screens/scanner_screen.py`: sau khi scan hoàn tất, nếu bất kỳ row nào có
  `macro.freshness_reason_codes` chứa `MACRO_CALENDAR_STALE` → hiển thị MỘT
  dòng hint ở nhãn trạng thái quét (dùng label/status-bar hiện có, không thêm
  widget): "Cần dán lịch ForexFactory (màn Quản lý tin) — phạm vi lịch kinh tế
  không tươi." Chỉ hiển thị khi lá cờ tồn tại; không chặn gì.
- (Cosmetic, tùy chọn nếu không phá test ghim): `scanner_live_producers.py`
  d.255 label `source="news_service"` → `"news_repository"`; kiểm tra
  `tests/test_market_safety_gate.py` + `tests/scanner_testkit.py` d.299 trước
  khi đổi — nếu test ghim chuỗi cũ thì để lần sau.

### 3.6 Xóa path cũ (WI-7 — D2, cùng commit với WI-4/5/6)

Xóa file:
- `services/news_service.py`, `services/forex_factory_client.py`,
  `services/interest_rate_service.py`
- Test của path cũ: `tests/test_news_service.py`,
  `tests/test_news_service_macro_cache.py`,
  `tests/test_macro_global_snapshot.py`,
  `tests/test_forex_factory_client.py`, `tests/test_fix_calendar_cache.py`,
  `tests/test_step3_fred.py`, `tests/test_step4_ai_stance.py`
- Port/rewrite (KHÔNG xóa mất độ phủ): `tests/test_macro_scoring_contract.py`
  → nhắm `core/macro_tiers.py`; `tests/test_execution_news_status.py` → nhắm
  `NewsMacroProvider.execution_news_status` (fake repository).
- Kiểm tra và cập nhật nếu còn import: `scripts/smc_execution_smoke.py` (d.204
  dùng fake `_News` — vẫn ổn vì duck-type), `tests/test_app_controller_di.py`
  (DI ghim `news_service` — đổi sang provider).

Giữ lại (có consumer khác): `services/macro_market_cache.py` +
`services/market_data_service.py` (VIX/correlation cho regime/correlation
context — ngoài phạm vi).

## 4. B3 pin (WI-1) — chi tiết

File mới `tests/test_macro_cutover_b3_pin.py`, 2 cụm:

**Pin A — tiêu thụ (không đổi sau cutover):** gọi `_analyze_one_symbol` với
packet fixture (`v4_captured_at`/`location_cutoff`/`v4_observed_at` gần
now), `macro_context` cố định 3 kịch bản:
1. aligned: `macro_alignment_scores {"buy": 18, "sell": 8}`,
   `macro_data_quality 0.9` → row `macro_score`/`macro_confidence` + gate
   reason `MACRO_ALIGNED` (PASS);
2. conflict: `{"buy": 8, "sell": 18}` → `MACRO_CONFLICT` + cap WATCH_ZONE;
3. low confidence: quality 0.4 (× multiplier 1.0 = 0.4 < 0.6) →
   `MACRO_LOW_CONFIDENCE`, status UNKNOWN → BLOCKED (macro là critical gate).
Assert cả `row["macro"]["macro_confidence"]`, `row["economic_events"]`.

**Pin B — công thức (phải khớp tuyệt đối sau port):** fixture inputs cố định →
gọi `NewsService._compute_macro_tiers(..., ai_service=None)` (monkeypatch
`_load_interest_rates` trả rate cố định, `yield_spread_data` cố định; events
dùng `time_utc` động `now+48h`/`now+20h` để bucket time_weight ổn định) →
ghim expected `tier1/tier2/tier3/raw_total` bằng hằng số trong test. Sau WI-2,
thêm test đối chiếu: cùng input → `core.macro_tiers.compute_macro_tiers` ra
**giá trị bằng hệt**. Pin B cố tình chạy AI-off (đó chính là hành vi đích).

## 5. Work items

| WI | Việc | File | Kiểm chứng | Nhóm/commit |
|---|---|---|---|---|
| WI-1 | B3 pin (§4) trên path cũ | `tests/test_macro_cutover_b3_pin.py` | Test pass trên HEAD; số liệu pin ghi thành hằng số | A (commit riêng) — **STOP D1** |
| WI-2 | Port công thức (§3.1) | `core/macro_tiers.py` + test đơn vị (fixture thuần, `now` ghim) | Pin B đối chiếu pass; không import services/ui; import-linter sạch | B — **STOP D2** |
| WI-3 | Provider (§3.2) + test với repository giả | `services/news_macro_provider.py`, `tests/test_news_macro_provider.py` | 5 method đúng shape; không HTTP; TTL/cache hoạt động; lỗi DB → fail-closed | B |
| WI-4 | Đấu nối 4 seam + vá Gap 1/2 (§3.3) | `controllers/scanner_controller.py` | Pin A pass; `news_in_3h` thật đến regime (thêm 1 test: event +2h → regime volatile); safety news sub-gate chặn được event 15 phút tới (test `_fetch_one_symbol_mt5` truyền events) | C (một commit C cho WI-4→7) — **STOP D3** |
| WI-5 | Wiring `AppController` (§3.4) | `controllers/app_controller.py` | `test_app_controller_di.py` pass; app khởi chạy offscreen không lỗi import | C |
| WI-6 | `MACRO_CALENDAR_STALE` + hint (§3.5) | `core/reason_codes.py`, `services/news_macro_provider.py`, `controllers/scanner_controller.py`, `ui/screens/scanner_screen.py` | Test: scope events degraded → row có `freshness_reason_codes`; UI hint hiển thị đúng 1 dòng khi có cờ | C |
| WI-7 | Xóa path cũ + port/rewrite test (§3.6) | §3.6 | Pin A+B pass; `pytest tests/ -k "scanner or news or macro"` toàn xanh; grep không còn import `news_service`/`forex_factory_client`/`interest_rate_service` ngoài tài liệu | C |
| WI-8 | Nghiệm thu runtime + cập nhật tài liệu (D3 xóa plan) | `docs/macro/macro_score_architecture.md` mục 0 → IMPLEMENTED; `docs/architecture/runtime-status.md`; `docs/news/news-architecture.md` §12; `docs/scanner/scanner-architecture.md` §5.2/§5.3 (gap → đã vá); `docs/architecture/architecture.md` (module map bỏ news_service) | Quét 1 symbol + 31 symbol thật: không crash, macro raws/confidence hợp lý, hint đúng khi chưa dán lịch; xóa file plan này | D — **STOP D4** |

Lệnh kiểm chuẩn mỗi nhóm: `pytest tests/ -k "scanner or news or macro" -q`
(bỏ `tests/test_smc_gate72_fix_acceptance.py` — lỗi collection sẵn có) và
`python scripts/scanner_smoke.py` offscreen cho nhóm C/D.

## 6. Checklist nghiệm thu

- [ ] Pin A + Pin B pass (tương đương trừ các đổi nguồn đã ghi: AI stance →
      keyword, yield 10y-5y → 2y-10y, freshness theo store_state).
- [ ] Không còn request mạng nào trên đường vĩ mô (breakpoint/log: chỉ SQLite).
- [ ] Sub-gate News của MarketSafetyGate nhận events thật (chặn 0-30m khi có
      event high-impact gần).
- [ ] `news_in_3h` thật đi vào regime.
- [ ] Scope events unavailable/degraded → confidence tụt + hint UI, KHÔNG crash,
      KHÔNG tự chế neutral.
- [ ] `MacroGate`/`MacroPolicy`/`compose_scanner`: 0 dòng diff.
- [ ] 3 service cũ + test cũ đã xóa; không import mồ côi.
- [ ] Tài liệu mục 0 → IMPLEMENTED; plan này xóa (D3).

## 7. Rủi ro & lưu ý

- **Boundary time_weight (Tier 2):** fixture đặt event `+48h`/`+20h` để không
  rơi vào biên bucket; sau port giữ nguyên các ngưỡng 6/24/48h.
- **Danh sách test xóa lớn:** chạy full suite (`pytest tests/ -q`) một lần cuối
  ở nhóm C để bắt import mồ côi ngoài phạm vi `-k`.
- **`_filter_by_currencies` fallback "giữ mọi headline":** hành vi cũ giữ nguyên
  (d.1539) — đừng "sửa" nó trong ca này (đổi phạm vi headlines = đổi điểm).
- **Duck-type `self.news_service`:** nhiều fixture test fake theo tên method —
  giữ tên thuộc tính cho đến khi mọi test chuyển; chỉ đổi kiểu đối tượng.
- **Calibration sau:** mọi chênh lệch điểmmacro sau cutover phải giải thích được
  bằng 3 thay đổi nguồn đã ghi (AI stance, yield series, freshness semantics);
  không đổi ngưỡng MacroPolicy để "ép khớp".
