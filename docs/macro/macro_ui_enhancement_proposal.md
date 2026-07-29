# UI Design Proposal — Enhanced Macro Section for Scanner Detail

**Date**: 2026-07-20
**Status**: Design Only — No Implementation
**Constraint**: Use ONLY existing data; zero backend changes

---

## 1. Layout Overview

Replace the current single-row `"Vĩ mô"` trade panel entry with a multi-row expandable section.

```
┌─────────────────────────────────────────────────────────┐
│ VĨ MÔ                           ● 22/30   Thuận         │
│                                                         │
│ ▸ Tier 1 — Lãi suất              8/12  ████████░░░░     │
│   USD 5.50% (hawkish) vs EUR 2.50% (dovish)             │
│                                                         │
│ ▸ Tier 2 — Lịch kinh tế           7/9   ███████░░░      │
│   Ít sự kiện cho USD, nhiều cho EUR                      │
│                                                         │
│ ▸ Tier 3 — Tâm lý thị trường      7/9   ███████░░░      │
│   Risk-on · VIX 16.5 · 2 điểm nóng                      │
│                                                         │
│ [▼ Chi tiết]                                            │
└─────────────────────────────────────────────────────────┘
```

Expanded detail view:

```
┌─────────────────────────────────────────────────────────┐
│ VĨ MÔ                           ● 22/30   Thuận         │
│                                                         │
│ ▸ Tier 1 — Lãi suất              8/12  ████████░░░░     │
│   Chênh lệch        ████░░  3/4                         │
│   Xu hướng          █████████  4/4   USD giữ, EUR cắt   │
│   Lập trường        ████░░  3/4   hawkish vs dovish     │
│   Đường cong LS     +0.42  đang dốc lên                 │
│                                                         │
│ ▸ Tier 2 — Lịch kinh tế           7/9   ███████░░░      │
│   USD: 1 sự kiện (CL 1.0)                               │
│   EUR: 3 sự kiện (CL 6.0)  ←  kéo điểm xuống            │
│   Sắp tới: ECB Speech (2h), GDP (14h)...                 │
│                                                         │
│ ▸ Tier 3 — Tâm lý thị trường      7/9   ███████░░░      │
│   Tâm lý  ██████░░  6/8   Risk-on → lợi cho AUD,NZD,CAD│
│   Địa CT  ██░░░░  2/2   2 điểm nóng                     │
│   VIX     16.5  ←  bình thường                           │
│                                                         │
│ ▸ Kết luận                                              │
│   MUA: Vĩ mô ủng hộ. USD lãi suất cao hơn, ít sự kiện,  │
│   tâm lý risk-on hỗ trợ USD.                             │
│                                                         │
│   BÁN: Vĩ mô không ủng hộ. EUR lãi suất thấp hơn,       │
│   nhiều sự kiện sắp tới gây bất ổn.                      │
│   [▲ Thu gọn]                                           │
└─────────────────────────────────────────────────────────┘
```

## 2. Component Specification

### 2.1 Overall Macro Score (Header Row)

| Aspect | Detail |
|--------|--------|
| **Data source** | `row["macro_score"]`, `row["macro_bias"]`, `row["macro_confidence"]` |
| **Existing variable** | Same as current `_dialog_card_macro()` |
| **Rendering** | QLabel with HTML — reuses existing logic, same as current |
| **Backend changes** | **NONE** — identical to current implementation |

### 2.2 Tier 1 — Interest Rate

| Aspect | Detail |
|--------|--------|
| **Data source** | `row["analysis_result"]["macro"]["macro_tier_detail"]["tier1_interest_rate"]` |
| **Variables** | `tier1["buy"]` (int), `tier1["sell"]` (int), `tier1["detail"][...]` |
| **Score display** | `{value}/{12}` with progress bar — `████░░░░` proportional to 12 |
| **Short reason** | Built from `detail["base_rate"]`, `detail["quote_rate"]`, `detail["base_stance"]`, `detail["quote_stance"]` — e.g. `"USD 5.50% (hawkish) vs EUR 2.50% (dovish)"` |
| **Expanded detail** | Sub-components: rate_diff, rate_trend, stance — each with mini progress bar. Plus yield_spread if not None. |
| **Progress bar** | Segmented bar: 12 segments. Filled count = tier1 value. Color: green (≥9), yellow (≥5), gray (<5). |
| **Rendering complexity** | Low — all values are flat ints/strings. No nested iteration. |
| **Backend changes** | **NONE** |

**Short reason logic** (inline, no new function):
```python
base_rate = d.get("base_rate", "--")
quote_rate = d.get("quote_rate", "--")
base_stance = d.get("base_stance", "--")
quote_stance = d.get("quote_stance", "--")
short = f"{base} {base_rate} ({base_stance}) vs {quote} {quote_rate} ({quote_stance})"
```

### 2.3 Tier 2 — Economic Calendar

| Aspect | Detail |
|--------|--------|
| **Data source** | `row["analysis_result"]["macro"]["macro_tier_detail"]["tier2_calendar"]` |
| **Variables** | `tier2["buy"]` (int), `tier2["sell"]` (int), `tier2["detail"][...]` |
| **Score display** | `{value}/{9}` with progress bar |
| **Short reason** | Built from event counts: `"USD: {n} sự kiện (CL {q}), EUR: {m} sự kiện (CL {q2})"` where fewer events = higher score |
| **Expanded detail** | List upcoming events by currency with severity + time (from `base_events`/`quote_events` lists). Each event: title, hours_until, severity icon. |
| **Progress bar** | 9 segments. Color: green (≥7), yellow (≥4), gray (<4). Higher = fewer disruptive events. |
| **Rendering complexity** | Medium — event list requires iteration over `base_events`/`quote_events` arrays (max ~10 items each). |
| **Backend changes** | **NONE** |

**Short reason logic**:
```python
base_cnt = d.get("base_event_count", 0)
quote_cnt = d.get("quote_event_count", 0)
base_q = d.get("base_quality", 0)
quote_q = d.get("quote_quality", 0)
short = f"{base}: {base_cnt} sự kiện · {quote}: {quote_cnt} sự kiện"
# Add quality note: higher quality = more disruptive = lower score
```

### 2.4 Tier 3 — Risk Sentiment

| Aspect | Detail |
|--------|--------|
| **Data source** | `row["analysis_result"]["macro"]["macro_tier_detail"]["tier3_sentiment"]` |
| **Variables** | `tier3["buy"]` (int), `tier3["sell"]` (int), `tier3["detail"][...]` |
| **Score display** | `{value}/{12}` with progress bar |
| **Short reason** | Built from sentiment + VIX: `"{risk_on/risk_off/neutral} · VIX {level}"` |
| **Expanded detail** | Risk sentiment sub-score (0-8) + Geopolitical sub-score (0-4). VIX level with interpretation. Hotspot count. |
| **Progress bar** | 12 segments. Color: green (≥9), yellow (≥5), gray (<5). |
| **Rendering complexity** | Low — all values are flat ints/strings. |
| **Backend changes** | **NONE** |

**Short reason logic**:
```python
sentiment = d.get("risk_sentiment", "neutral")
sent_label = {"risk_on": "Risk-on", "risk_off": "Risk-off", "neutral": "Trung tính"}.get(sentiment, sentiment)
vix = d.get("vix_level")
vix_str = f"VIX {vix:.1f}" if vix is not None else ""
hotspots = d.get("hotspot_count", 0)
short = f"{sent_label} · {vix_str} · {hotspots} điểm nóng" if vix_str else f"{sent_label} · {hotspots} điểm nóng"
```

### 2.5 BUY/SELL Explanation

| Aspect | Detail |
|--------|--------|
| **Data source** | `row["analysis_result"]["macro"]["driver_context"]["macro_alignment_reasons"]` |
| **Variables** | `reasons["buy"]` (str), `reasons["sell"]` (str) |
| **Display** | Pre-formatted human-readable strings. Already generated by `_build_macro_reason()`. Just display. |
| **Format** | `"[T1] USD=5.50%(hawkish) vs EUR=2.50%(dovish) \| [T2] Calendar: base=0, quote=2 \| [T3] Sentiment=risk_on, hotspots=2"` |
| **Rendering complexity** | Trivial — display a string. Could be split by `"|"` for cleaner formatting. |
| **Backend changes** | **NONE** |

### 2.6 Color Usage

| Element | Color | Threshold |
|---------|-------|-----------|
| Score ≥ 22 | `#10b981` (green) | Strong macro support |
| Score ≥ 15 | `#f59e0b` (yellow) | Neutral/moderate |
| Score < 15 | `#94a3b8` (gray) | Weak/contrary macro |
| Progress bar filled | Matches score color | |
| Progress bar empty | `#e5e7eb` light / `#1e293b` dark | |
| Confidence dot ● | `#10b981` | conf ≥ 0.8 |
| Confidence dot ○ | `#f59e0b` | conf ≥ 0.5 |
| Confidence dot ◌ | `#94a3b8` | conf < 0.5 |
| Tier labels | `#6b7280` light / `#94a3b8` dark | Muted, consistent |
| Buy/Sell labels | `#ea580c` (buy) / `#f43f5e` (sell) | Per convention |

### 2.7 Tooltips

| Element | Tooltip |
|---------|---------|
| Tier 1 header | "Lãi suất & Chính sách tiền tệ: Chênh lệch lãi suất, xu hướng, lập trường ngân hàng trung ương, đường cong lợi suất" |
| Tier 2 header | "Lịch kinh tế: Sự kiện 72h tới. Điểm cao = ít sự kiện gây biến động cho đồng tiền này" |
| Tier 3 header | "Tâm lý thị trường & Địa chính trị: Phân tích sentiment từ tin tức, VIX, điểm nóng địa chính trị" |
| Progress bar | "{value}/{max} điểm — click để xem chi tiết" |
| Confidence dot | "Độ tin cậy dữ liệu: {conf*100:.0f}%" |
| VIX level | VIX interpretation based on level |

## 3. Implementation Plan

### 3.1 Files to Modify

| File | Change |
|------|--------|
| `ui/screens/scanner_detail_screen.py` | Replace single macro row in trade panel with expandable section. Add helper `_render_macro_section()`. |

**That's it. One file. Zero backend changes.**

### 3.2 New Methods (in ScannerDetailScreen)

| Method | Purpose | Lines (est.) |
|--------|---------|-------------|
| `_render_macro_section(layout)` | Main entry — renders the entire macro section in the trade panel or a new card | ~80 |
| `_macro_tier_row(detail, max_val, label, short_reason)` | Renders one tier row with score + progress bar + reason | ~30 |
| `_macro_progress_bar(value, max_val, width_chars)` | Returns HTML string for a segmented progress bar | ~15 |
| `_macro_expanded_detail(tier1, tier2, tier3, reasons, side)` | Renders the expanded detail view | ~60 |

### 3.3 Integration Point

Replace lines 762-767 in `_refresh_trade_panel()`:

```python
# Current (line 762-768):
# ("Vĩ mô", f"{macro_val} {macro_detail}".strip(), "#38bdf8"),

# Proposed:
# The entire macro section is rendered by _render_macro_section()
# which adds multiple rows to the trade panel layout
```

The macro section becomes a dedicated `QWidget` inserted above the existing trade panel rows, with its own internal layout.

### 3.4 Data Access Pattern

```python
def _get_macro_data(self):
    """Safely extract all macro data from row, with defaults for every path."""
    ar = self.row.get("analysis_result", {}) if self.row else {}
    td = ar.get("macro", {}).get("macro_tier_detail", {})
    dc = ar.get("macro", {}).get("driver_context", {})
    
    return {
        "score": self.row.get("macro_score", 15) if self.row else 15,
        "bias": self.row.get("macro_bias", "neutral") if self.row else "neutral",
        "confidence": self.row.get("macro_confidence", 1.0) if self.row else 1.0,
        "best_side": self.row.get("best_side", "buy") if self.row else "buy",
        "tier1": td.get("tier1_interest_rate", {}),
        "tier2": td.get("tier2_calendar", {}),
        "tier3": td.get("tier3_sentiment", {}),
        "reasons": dc.get("macro_alignment_reasons", {}),
    }
```

### 3.5 Collapse/Expand

- Default state: **collapsed** — shows header row + 3 tier summary rows (compact)
- Click "▼ Chi tiết" → expands to show sub-components + buy/sell explanations
- Click "▲ Thu gọn" → collapses back
- State stored in `self._macro_expanded` boolean

## 4. What This Does NOT Change

- Does not add new scoring logic
- Does not call any new APIs
- Does not modify any backend file
- Does not change the existing `_dialog_card_macro()` behavior (detail dialog remains unchanged)
- Does not require new data to be computed
- Does not change the scanner row schema
- Does not affect the scanner table, hero bar, or any other screen

## 5. Estimated Effort

| Phase | Hours |
|-------|-------|
| Implement `_render_macro_section` + helpers | 2-3 |
| Implement collapse/expand | 0.5 |
| Style + color tuning | 1 |
| Testing (manual + automated) | 1 |
| **Total** | **4.5-5.5** |
