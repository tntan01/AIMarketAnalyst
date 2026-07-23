# RR Anchor Semantics

> **Phase 6 — locked contract.** Do NOT change anchor, meaning, or consumer
> without updating this document and all regression tests.

## Field inventory

### Nominal RR (no spread adjustment)

These fields express reward-to-risk ratio using raw price distance (no spread
cost deducted). They exist mainly for display / human consumption.

| Field | Anchor | Formula | Consumer |
|---|---|---|---|
| `risk_reward` | **best edge** (`entry_for_rr`, aggressiveness=0.0) | `f"1:{reward_risk(entry_best, sl, tp):.1f}"` | Scanner table, order dialog R:R column, Telegram alert, entry checklist |
| `risk_reward_base` | **midpoint** (`entry_for_selection`, aggressiveness=0.5) | `reward_risk(entry_mid, sl, tp)` rounded | Tooltip detail, diagnostic reference |
| `risk_reward_worst` | **far edge** (aggressiveness=1.0) | `reward_risk(entry_far, sl, tp)` rounded | Tooltip detail, diagnostic reference |
| `risk_reward_range` | dict `{best, base, worst}` | See above | Order dialog R:R tooltip, scanner detail screen |

**Backward compat:** `risk_reward` must always be the best-case "1:X.X" string.
Consumers that parse it (e.g., `_parse_rr()`, `parse_risk_reward()`) must be
aware it is best-case. Do NOT change its meaning.

### Effective RR (spread-adjusted)

These fields are adjusted for spread: `effective_risk = risk + spread_cost`,
`effective_reward = reward - spread_cost`. Used for gate decisions,
ranking, and execution guard.

| Field | Anchor | Consumer |
|---|---|---|
| `expected_effective_rr` | **best edge** (same as `risk_reward`) | Legacy display, fallback for gate/ranking |
| `expected_effective_rr_base` | **midpoint** (same as `risk_reward_base`) | **Gate** (via `expected_effective_rr_for_gate`), **ranking** (`_safe_rr`, `calculate_opportunity_score`) |
| `expected_effective_rr_worst` | **far edge** | Diagnostic reference |
| `risk_reward_effective_range` | dict `{best, base, worst}` | Diagnostic reference, scanner row field |

**Gate resolution order:**
1. `expected_effective_rr_for_gate` (set to `expected_effective_rr_base` if available)
2. `expected_effective_rr` (best-case fallback)

**Ranking resolution order:**
1. `expected_effective_rr_base`
2. `expected_effective_rr`
3. `risk_reward` string (parsed)

### Current-price RR (live execution)

These fields are computed at execution time using live MT5 price (or
fallback). Used ONLY for execution guard — never for gate, ranking, or
display of the scan result.

| Field | Anchor | Consumer |
|---|---|---|
| `current_entry_price` | Live MT5 tick (`tick.ask`/`tick.bid`) or fallback `technical.price` | Execution guard, order dialog tooltip |
| `current_effective_rr` | Live/fallback price | **Auto-trade guard** (skip if < `min_rr`), **manual order guard** (block if < `min_rr`) |
| `current_rr_source` | `"current_price"` / `"no_current_price"` / `"no_stop_loss"` / `"no_take_profit"` / `"price_behind_sl"` / `"invalid_direction"` | Diagnostic, guard eligibility |
| `current_price_in_entry_zone` | `bool | None` | Diagnostic, order dialog tooltip |

**Execution guard policy:** Skip/block when BOTH:
- `current_rr_source == "current_price"` (meaningful RR was computed)
- `current_effective_rr < min_rr`

When source is anything else, the guard does NOT trigger (missing data is
not treated as a block).

## Consumer contract matrix

| Consumer | RR field used | Anchor | Phase |
|---|---|---|---|
| **Gate** (`_gate_expected_effective_rr`) | `expected_effective_rr_for_gate` → `expected_effective_rr_base` → `expected_effective_rr` | base → best fallback | Phase 3 |
| **Ranking RR bonus** (`calculate_opportunity_score`) | `expected_effective_rr_base` → `expected_effective_rr` → `risk_reward` | base → best fallback | Phase 4A |
| **Sort `_safe_rr`** | `expected_effective_rr_base` → `expected_effective_rr` → `risk_reward` | base → best fallback | Phase 4A |
| **Scanner table column** | `expected_effective_rr` (best) + tooltip shows base/current | best display + base/current diagnostic | Phase 5C, 8 |
| **Order dialog R:R column** | `risk_reward` (best string) + tooltip shows best/base/current | best display + diagnostic | Phase 5C, 8 |
| **Auto-trade guard** | `current_effective_rr` at live/fallback price | live current | Phase 5B |
| **Manual order guard** | `current_effective_rr` at live/order_entry_fallback price | live current | Phase 5B |
| **Telegram alert** | `risk_reward` (best string) as nominal reference; primary display uses `expected_effective_rr_base` (base) with fallback `expected_effective_rr` (best) | base primary + best reference | Phase 7 |
| **Entry checklist** | `risk_reward` (best string) via `_parse_rr()` for pass/fail; note shows base/effective range as reference | best (unchanged) | Phase 11 |
| **Auto-trade eligibility** | `expected_effective_rr` (best effective) for backtest gate pre-filter | best effective | Phase 11 |
| **Diagnostics** (`result["diagnostics"]`) | All RR fields | best + base + current | Phase 5D |
| **Manual `execution_guard`** | `current_effective_rr` + `price_source` | live / order_entry_fallback / none | Phase 5D.1 |

## Field relationship diagram

```
build_trade_plan()
  ├─ entry_for_rr (best edge, agg=0.0) ──► risk_reward, expected_effective_rr,
  │                                         entry_price, position_sizing
  ├─ entry_for_selection (midpoint, agg=0.5) ──► risk_reward_base,
  │     expected_effective_rr_base, TP validation
  └─ entry_worst (far edge, agg=1.0) ──► risk_reward_worst,
        expected_effective_rr_worst

scanner_row_from_analysis()
  ├─ Copies all RR fields from best_plan
  └─ enrich_scanner_row_with_ranking()
       ├─ Pulls expected_effective_rr_base from analysis_result.scenarios
       ├─ calculate_opportunity_score() uses base RR for bonus
       └─ scanner_group assigned

check_trade_gates()
  └─ _gate_expected_effective_rr()
       ├─ expected_effective_rr_for_gate (prefers base)
       └─ Falls back to expected_effective_rr (best)

_get_alert_order_candidates() / _build_order_rows()
  └─ calculate_current_effective_rr(current_price=live/fallback)
       ├─ current_effective_rr
       ├─ current_rr_source
       └─ current_price_in_entry_zone

_execute_auto_trades()
  ├─ Entry zone check with live price
  ├─ Current RR guard: skip if cur_rr < min_rr
  └─ Diagnostic payload appended to result["diagnostics"]

Manual order dialog
  ├─ Entry zone check with live price
  ├─ Current RR guard: block warning if cur_rr < min_rr
  └─ execution_guard diagnostic on order_info
```

## Backward compatibility rules

1. `risk_reward` string MUST remain `"1:X.X"` from best edge. Never change.
2. `expected_effective_rr` MUST remain best-case effective RR. Never change.
3. `risk_reward_range` keys `{best, base, worst}` MUST NOT be reordered or renamed.
4. Any new field must be ADDITIVE — do not remove or rename existing keys.
5. Thresholds (`_RR_STRONG=2.0`, `_RR_WEAK=1.3`, `min_rr=1.3`) must only change in a dedicated recalibration phase with data-driven justification.
