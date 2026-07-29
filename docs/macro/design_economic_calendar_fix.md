# Design Proposal: Economic Calendar Actual Value Bug Fix

**Date**: 2026-07-20
**Status**: PENDING APPROVAL
**Bug**: CNY 5-y Loan Prime Rate shows actual=3.00% instead of 3.50% (copied from 1-y event)

---

## 1. Confirmed Root Causes (from debug trace)

The bug is a chain of 4 interrelated issues in `services/forex_factory_client.py`:

| # | Root Cause | File:Line | Severity |
|---|-----------|-----------|----------|
| RC1 | HTML parser cannot extract time from `rowspan`-shared cells | `_parse_html()` :435-437 | Critical (trigger) |
| RC2 | `_merge_actual_from_html` Step 3 matches by time only, ignoring event name | `_merge_actual_from_html()` :608-621 | Critical (direct cause) |
| RC3 | Corrupted cache values block self-healing (merge skips if actual already populated) | `_merge_actual_from_html()` :604 | Medium (persistence) |
| RC4 | Dedup key mismatch: HTML row (time='') ≠ cache row (time=ISO) → duplicate events | `calendar_events_window()` :229 | Low (cosmetic) |

### Chain of causation

```
ForexFactory HTML: <td rowspan="2">8:00am</td>
        │
        ▼
[RC1] _parse_html() finds calendar__time only in 1st <tr>
      → 5-y row gets time_utc='', date_key=''
        │
        ▼
[RC1] html_lookup[('CNY','5 y loan prime rate','')] = '3.50%'
      JSON  lookup key   = ('CNY','5 y loan prime rate','20260720')
      → date_key mismatch → Step 1 MISS
        │
        ▼
[RC2] Step 3: find CNY event within ±30min → finds 1-y first
      → copies actual='3.00%' to 5-y ← BUG
        │
        ▼
[RC3] Cache stores 5-y with actual='3.00%'
      Next run: actual already populated → merge skips entirely
      → corrupted value lives forever
        │
        ▼
[RC4] HTML 5-y (time='') + Cache 5-y (time='2026-07-20T01:00Z')
      → different dedup keys → both appear in results
```

---

## 2. Data Trust Hierarchy

Before proposing individual fixes, we must define the trust model that governs
how actual values flow and which source wins when sources disagree.

### 2.1 Source ranking (highest trust first)

| Rank | Source | Trust Rationale |
|------|--------|-----------------|
| **1** | **Fresh HTML** (fetched this session, ≤5 min old) | Direct scrape of ForexFactory.com — the primary source. Contains actual values updated in near-real-time after economic releases. |
| **2** | **JSON API** (nfs.faireconomy.media, this session) | NFS mirrors FF data but may lag on actual values for recently-released events (observed: actual='' while HTML already has the value). Forecast and previous are reliable. |
| **3** | **Disk Cache** (economic_calendar_thisweek.json, ≤24h old) | Persisted from previous sessions. Subject to drift and corruption if a prior merge produced wrong data. Useful for offline fallback but must be overridable. |

### 2.2 Merge confidence levels

Not all matches are equal. We classify each match attempt by confidence:

| Level | Criteria | Action Allowed |
|-------|----------|---------------|
| **High Confidence** | currency match + normalized event name match + date match (all 3 dimensions) | ✅ Fill empty actual, ✅ Overwrite existing actual (self-heal) |
| **Medium Confidence** | currency match + raw event name match (no date check, used by `lookup_actuals_batch`) | ✅ Fill empty actual only. ❌ Never overwrite existing. |
| **Low Confidence** | currency match + time proximity only (Step 3 current behavior) | ❌ Never allowed. Too dangerous — provably copies wrong data. |

### 2.3 Merge decision matrix

```
                    ┌──────────────────────────────────────────────────┐
                    │          MERGE DECISION MATRIX                   │
                    │                                                  │
                    │  Source providing the value:                     │
                    │  Fresh HTML > JSON API > Disk Cache              │
                    │                                                  │
                    │  Confidence required to OVERWRITE:               │
                    │  HIGH (currency + norm_event + date)            │
                    │                                                  │
                    │  Confidence required to FILL EMPTY:              │
                    │  HIGH or MEDIUM                                  │
                    │                                                  │
                    │  LOW confidence → NEVER merge                    │
                    └──────────────────────────────────────────────────┘
```

---

## 3. Proposed Fixes

### Fix 1: HTML rowspan time propagation

**File**: `services/forex_factory_client.py`
**Method**: `_parse_html()` (line ~412)

**Problem**: When two or more events share the same time, ForexFactory renders `<td rowspan="N">` for the time cell. The time cell only exists in the first `<tr class="calendar__row">`. Subsequent rows within the same time group have no `calendar__time` cell, so `_html_cell_text()` returns empty string.

**Solution**: Maintain a `current_time_text` variable that persists across rows within the same date. When a row has no time text AND the row is not an "All Day"/"Tentative" row, inherit the time from the previous row. Reset when the date changes.

**Logic**:
```
current_time_text = None  # alongside current_date

For each row block:
  time_text = extract from calendar__time cell
  if time_text is empty AND current_time_text is not None:
      time_text = current_time_text  # inherit from previous row (rowspan)
  else if time_text is not empty:
      current_time_text = time_text  # update for next rows

  if date changes:
      current_time_text = None  # reset on date boundary
```

**Advantages**:
- Standard HTML table parsing technique
- Fixes the trigger (RC1) of the entire bug chain
- HTML rows get correct `time_utc` → correct `date_key` → Step 1 matching achieves High Confidence
- Automatically resolves RC4 (dedup key mismatch)

**Risks**: Very low. Time inheritance within the same calendar date is always correct — ForexFactory groups events by time slot and all events in a time group share the exact same time.

**Edge cases considered**:
- "All Day" events: `_parse_html_time()` returns `None` for "All Day"/"Tentative". We do NOT inherit time for these — they stay as `time_utc=''`.
- Date boundary: `current_time_text` is reset to `None` when `current_date` changes.

---

### Fix 2: Step 3 — Evaluation & Decision

#### Option A: Remove Step 3 entirely

Delete the time-proximity fallback at lines 608-621 and 654-666.

| Factor | Assessment |
|--------|-----------|
| **Safety** | ✅ Eliminates the bug root cause. No more same-time-same-currency miscopying. |
| **Coverage loss** | Some events that previously got actual via Step 3 will now show empty. See mitigation below. |
| **Code simplicity** | ✅ Removes ~27 lines of unsafe heuristic. |
| **Trust hierarchy alignment** | ✅ Step 3 is Low Confidence — should never have been allowed per our trust model. |

**Mitigation for coverage loss**:
- `lookup_actuals_batch()` in `news_service.py` already runs after the merge, fetching HTML from thisweek + lastweek and matching by raw event name (Medium Confidence). This fills most remaining gaps.
- Brave Search (`lookup_actual_single()`) provides on-demand lookup from the Dashboard UI.
- Empty actual is the honest answer when data isn't available; wrong actual is actively harmful.

#### Option B: Keep Step 3 with strict conditions

Keep the time-proximity fallback but gate it behind additional constraints:

```
Only activate Step 3 when ALL of:
  1. currency matches (existing)
  2. time within ±30 min (existing)
  3. At least one significant word overlap in normalized event names
     (e.g., both contain "cpi" or both contain "loan prime rate")
  4. NOT when multiple HTML events for the same currency exist within
     the same ±30 min window (ambiguous → skip)
  5. Only FILL EMPTY actual — never overwrite existing
```

| Factor | Assessment |
|--------|-----------|
| **Safety** | Better than current, but condition (3) is heuristic and can still misfire. Condition (4) eliminates the case that triggered this bug (2 CNY events in same window). |
| **Coverage** | Preserves some fill capability for isolated events where event names differ between JSON and HTML. |
| **Complexity** | Adds ~15 lines of non-trivial logic. Two-level gating is harder to reason about. |
| **Trust hierarchy alignment** | Still Low Confidence at core — the word-overlap heuristic doesn't elevate it to Medium. |

#### Decision: **Option A — Remove Step 3**

**Rationale**:

1. **Trust hierarchy is the guiding principle.** Step 3 is fundamentally a Low Confidence match — matching by time alone. No amount of gating can elevate it to High Confidence without effectively turning it into Step 1 (which we already have).

2. **Option B's condition (4) addresses this specific bug but doesn't fix the class of problem.** What if 3 events share the same time slot? Condition (4) would skip all of them, even if the event names actually match. We'd be replacing one failure mode with another.

3. **Coverage loss is bounded and has fallbacks.** The `lookup_actuals_batch()` in news_service already runs after the merge with Medium Confidence matching. Events that Step 3 would have incorrectly filled are now correctly left empty and handled by downstream fallbacks.

4. **Simplicity.** Removing unsafe code is always preferable to adding guardrails around it. The merge logic becomes: Step 1 (High Confidence match) → Step 2 (re-fetch fresh HTML if stale). Clean, auditable, correct.

---

### Fix 3: Cache self-healing via High Confidence overwrite

**File**: `services/forex_factory_client.py`
**Method**: `_merge_actual_from_html()` Step 1 (line ~604)

**Problem**: The current merge condition `not str(row.get("actual", "")).strip()` means events that already have an actual value — even a corrupted one from disk cache — are never re-evaluated against fresh HTML. Once corrupted, always corrupted (RC3).

**Solution**: Apply the trust hierarchy. When Step 1 achieves a **High Confidence** match (currency + normalized event name + date all match), allow overwriting an existing actual value with the fresh HTML value if they disagree.

**Logic change**:
```
# BEFORE (current):
if key in html_lookup and not str(row.get("actual", "")).strip():
    row["actual"] = html_lookup[key]

# AFTER (proposed):
if key in html_lookup:
    current_actual = str(row.get("actual", "")).strip()
    html_actual = html_lookup[key]
    if not current_actual:
        row["actual"] = html_actual      # Fill empty (existing behavior)
    elif current_actual != html_actual:
        row["actual"] = html_actual      # Self-heal: High Confidence overwrite
    # else: values agree → no change needed
```

**Why this is safe**:

This only applies to **High Confidence** matches: same currency, same normalized event name, same calendar date. This is the strongest possible match — it means we've identified the exact same economic event across two data sources. When such a match exists and the values differ, the trust hierarchy says Fresh HTML wins.

**Advantages**:
- Fixes existing corrupted cache entries automatically on next fetch
- Prevents future cache corruption from persisting
- Respects the trust hierarchy (Fresh HTML > Disk Cache)
- Only acts on High Confidence matches — never on uncertain data

**Risks**: Very low. A High Confidence match means we've confirmed it's the same event. The only scenario where HTML would have a worse value than cache is if ForexFactory.com itself has incorrect data — in which case the cache is also wrong (since it originated from FF data).

---

### Fix 4: (Not needed)

Fixing RC1 automatically resolves RC4. When HTML rows have correct `time_utc`, the dedup key `(time_utc, currency, event)` will match cache rows identically, and duplicates will be correctly removed in the `calendar_events_window` dedup step.

No separate fix required.

---

## 4. Summary of Code Changes

All changes are in a **single file**: `services/forex_factory_client.py`

| Fix | Method | Change | Net Lines |
|-----|--------|--------|-----------|
| 1 | `_parse_html()` | Add `current_time_text` propagation for rowspan handling | +10 |
| 2a | `_merge_actual_from_html()` | Delete Step 3 time-proximity fallback (original) | -14 |
| 2b | `_merge_actual_from_html()` | Delete Step 3 time-proximity fallback (fresh-HTML re-fetch) | -13 |
| 3 | `_merge_actual_from_html()` | Step 1: High Confidence overwrite instead of fill-empty-only | ~6 changed |

**Total**: 3 methods modified. No new files. No API changes. No schema changes. No config changes.

---

## 5. Test Plan

### 5.1 Regression Fixture — Real ForexFactory HTML with rowspan

We must test against real-world HTML structure, not just hand-crafted snippets.

**Fixture**: Capture a real ForexFactory HTML response for a week containing the CNY Loan Prime Rate events (or similar multi-event time slot). Extract the relevant `<tr>` blocks and store as a test fixture.

**Real FF HTML structure (observed)**:

```html
<tr class="calendar__row" data-id="..." data-event-datetime="...">
  <td class="calendar__cell calendar__date"></td>
  <td class="calendar__time calendar__cell" rowspan="2">8:00am</td>
  <td class="calendar__currency calendar__cell">CNY</td>
  <td class="calendar__event-title calendar__cell">
    <span>1-y Loan Prime Rate</span>
  </td>
  <td class="calendar__impact calendar__cell">
    <span class="calendar__impact-icon--yellow"></span>
  </td>
  <td class="calendar__forecast calendar__cell">3.00%</td>
  <td class="calendar__previous calendar__cell">3.00%</td>
  <td class="calendar__actual calendar__cell revised">3.00%</td>
</tr>
<tr class="calendar__row" data-id="..." data-event-datetime="...">
  <td class="calendar__cell calendar__date"></td>
  <!-- NO time cell here — rowspan on previous row -->
  <td class="calendar__currency calendar__cell">CNY</td>
  <td class="calendar__event-title calendar__cell">
    <span>5-y Loan Prime Rate</span>
  </td>
  <td class="calendar__impact calendar__cell">
    <span class="calendar__impact-icon--yellow"></span>
  </td>
  <td class="calendar__forecast calendar__cell">3.50%</td>
  <td class="calendar__previous calendar__cell">3.50%</td>
  <td class="calendar__actual calendar__cell revised">3.50%</td>
</tr>
```

**Test cases using this fixture**:

| Test | What it verifies |
|------|-----------------|
| `test_rowspan_time_inheritance` | Both rows get `time_utc='2026-07-20T01:00Z'` |
| `test_rowspan_both_events_parsed` | Both "1-y" and "5-y" appear in parsed output |
| `test_rowspan_actual_not_mixed` | 1-y actual=3.00%, 5-y actual=3.50% (distinct, correct) |
| `test_rowspan_merge_step1_high_confidence` | After merge, 5-y actual=3.50% (from HTML, High Confidence match) |
| `test_rowspan_no_duplicates` | Dedup produces exactly 1 row per event |

### 5.2 Parser Robustness Tests

Test the HTML parser's resilience against real-world HTML variations:

| Test Category | Specific Tests |
|---------------|---------------|
| **Nested elements** | `<td class="calendar__actual"><span class="revised">3.50%</span></td>` — value inside nested span |
| **Nested elements** | `<td class="calendar__actual"><span><b>3.50%</b></span></td>` — deeply nested |
| **Missing optional cells** | Row without `calendar__forecast` — should return empty, not crash |
| **Missing optional cells** | Row without `calendar__previous` — should return empty, not crash |
| **Missing optional cells** | Row without `calendar__impact` — should return empty impact, not crash |
| **Rowspan variations** | 3 events sharing same time (`rowspan="3"`) — all 3 inherit time |
| **Rowspan variations** | Rowspan followed by All Day event — All Day does NOT inherit time |
| **Rowspan variations** | Rowspan across date boundary — time resets on new date |
| **Class name changes** | FF changes `calendar__actual` to `calendar__actual--new` — parser returns empty (graceful degradation, not crash) |
| **Class name changes** | FF adds additional CSS classes — `calendar__cell calendar__actual revised` — parser still matches via substring |
| **Empty table** | HTML with no `calendar__row` rows — returns empty list |
| **Malformed HTML** | Unclosed tags, missing `</tr>` — regex still extracts per-block |
| **Special characters** | Event names with `&amp;`, `&quot;`, Unicode — `clean_text()` handles |
| **Impact variants** | `ff-impact-red`, `calendar__impact-icon--red`, `high impact` — all map to "High" |

### 5.3 Existing Test Suite Regression

Run and verify:
- `tests/test_forex_factory_client.py` — all 14 tests must pass
- `tests/test_fix_calendar_cache.py` — all 9 tests must pass
- `tests/test_news_service.py` — all tests must pass

---

## 6. Pipeline Impact Analysis

Changes are confined to `ForexFactoryClient` in `services/forex_factory_client.py`.
No other file is modified. Below is the impact assessment for every downstream consumer.

### 6.1 Data flow diagram

```
ForexFactoryClient                             NewsService
─────────────────                             ───────────
calendar_events()                              latest_macro_context()
calendar_events_window()                       fetch_news_window()
       │                                            │
       │  returns list[dict] with                    │
       │  currency, event, actual,                   │
       │  forecast, previous, time_utc,              │
       │  impact, source                             │
       │                                            │
       ▼                                            ▼
  ┌──────────────────┐                    ┌──────────────────┐
  │ Fix 1: rowspan   │                    │ lookup_actuals_  │
  │ time propagation │                    │ batch()          │
  │ Fix 2: remove    │                    │ (separate HTML   │
  │ Step 3           │                    │  fetch + raw     │
  │ Fix 3: self-heal │                    │  name match)     │
  └──────────────────┘                    └──────────────────┘
       │                                            │
       └────────────┬───────────────────────────────┘
                    │
                    ▼
          ┌──────────────────┐
          │   DASHBOARD      │
          │ _render_news_rows│
          │ (reads `actual`  │
          │  from event dict)│
          └──────────────────┘
                    │
                    ▼
          ┌──────────────────┐
          │  SCANNER         │
          │ _fetch_one_      │
          │ symbol_mt5()     │
          │ data_quality_    │
          │ flags()          │
          └──────────────────┘
```

### 6.2 Component-by-component analysis

#### Dashboard (`ui/screens/dashboard_screen.py`)

| Aspect | Impact |
|--------|--------|
| **Data consumed** | `row.get("actual", "")` at line 763 |
| **Effect of fix** | ✅ Actual values are now correct for same-time-same-currency events. Previously: 5-y showed 3.00% (wrong). After: 5-y shows 3.50% (correct). |
| **Empty actual handling** | Already handles empty → displays "—" (line 766). No change needed. |
| **Coloring logic** | Compares actual vs forecast (lines 772-778). With correct actual, coloring becomes correct. |
| **Risk** | None. Dashboard is a pure consumer — it reads whatever the service layer provides. |

#### Scanner (`controllers/scanner_controller.py`)

| Aspect | Impact |
|--------|--------|
| **Data consumed** | `news_service.data_quality_flags()` → `context.get("events", [])` |
| **Effect of fix** | `data_quality_flags()` identifies high-impact events and their timing. Actual values are not used for flag computation (only impact level and time). ✅ No functional change. |
| **Macro scoring** | `_compute_macro_tiers()` → `_macro_tier2()` uses event titles, impact, and timing for calendar scoring. Actual values are NOT used in tier computation. ✅ No functional change. |
| **Risk** | None. Scanner uses events for timing/impact classification only. |

#### Macro Score / NewsService (`services/news_service.py`)

| Aspect | Impact |
|--------|--------|
| **Data consumed** | `calendar_events()` and `calendar_events_window()` return values |
| **Effect of fix** | Event dicts have correct actual values. `_macro_tier2()` (calendar impact scoring) does not use actual values — uses event name, impact, and timing. ✅ No change to scoring. |
| **`lookup_actuals_batch()`** | This method independently fetches HTML and builds its own lookup by raw event name. It only fills empty actuals. After our fix, actuals should already be correct from `_merge_actual_from_html`, so this becomes a no-op for most events. ✅ No conflict. |
| **`_build_news_feed()`** | Passes through `ev.get("actual", "")` at line 439. ✅ Receives corrected values. |
| **Risk** | None. NewsService is downstream of ForexFactoryClient. |

#### Journal / Trade Log

| Aspect | Impact |
|--------|--------|
| **Data consumed** | Macro context is stored as part of trade analysis |
| **Effect of fix** | Historical journal entries with wrong actual values are not retroactively fixed (they're snapshots). New entries will have correct values. |
| **Risk** | None. Journal is write-only for macro context at trade time. |

#### Interest Rate Service (`services/interest_rate_service.py`)

| Aspect | Impact |
|--------|--------|
| **Data consumed** | Independently scrapes ForexFactory HTML for rate decisions |
| **Effect of fix** | Uses separate parsing logic via `_update_from_forexfactory()`. Not affected. |
| **Risk** | None. Completely separate code path. |

### 6.3 Summary

| Component | Impact | Risk |
|-----------|--------|------|
| ForexFactoryClient | **Modified** — 3 methods changed | Low |
| NewsService | **Indirect** — receives corrected data, no code change | None |
| Dashboard | **Indirect** — displays corrected data, no code change | None |
| Scanner | **Indirect** — no functional change (actual not used in scan logic) | None |
| Macro Score | **Indirect** — no functional change (actual not used in tier scoring) | None |
| Journal | **Indirect** — future entries get corrected data | None |
| Interest Rate Service | **Unaffected** — separate code path | None |

**Conclusion**: Changes are strictly limited to data acquisition and merging. No downstream component requires modification. The existing defensive patterns (empty actual → "—", Brave Search fallback, `lookup_actuals_batch`) all continue to work correctly with the corrected data.

---

## 7. Rollback Strategy

All changes are within a single file's method bodies. Rolling back means reverting `forex_factory_client.py` to the previous commit. No database migrations, no schema changes, no config changes, no API changes.

---

## 8. Verification Checklist

- [ ] **Rowspan fix**: Both 1-y and 5-y Loan Prime Rate have `time_utc='2026-07-20T01:00Z'` from HTML parser
- [ ] **High Confidence Step 1**: Both events find their html_lookup entries — currency + norm_event + date all match
- [ ] **Correct actual**: 1-y actual=3.00%, 5-y actual=3.50%
- [ ] **No Step 3 regression**: Events without High Confidence matches are left with empty actual (not incorrectly filled)
- [ ] **Cache self-healing**: Previously corrupted cache entry for 5-y (actual=3.00%) is overwritten with 3.50%
- [ ] **No duplicates**: Exactly one 5-y Loan Prime Rate event in final results
- [ ] **Existing tests pass**: `test_forex_factory_client.py` (14 tests), `test_fix_calendar_cache.py` (9 tests), `test_news_service.py`
- [ ] **New rowspan tests pass**: 5 new tests with real FF HTML fixture
- [ ] **New robustness tests pass**: 14 new parser resilience tests
