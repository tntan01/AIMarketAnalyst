# RR Anchor Semantics

> **Phase 6–14 — locked contract.** Do NOT change anchor, meaning, or consumer
> without updating this document and all regression tests.

## Field inventory

### Nominal RR (no spread adjustment)

These fields express reward-to-risk ratio using raw price distance (no spread
cost deducted). They exist mainly for display / human consumption.

| Field | Anchor | Formula | Consumer |
|---|---|---|---|
| `risk_reward` | **best edge** (`entry_for_rr`, aggressiveness=0.0) | `f"1:{reward_risk(entry_best, sl, tp):.1f}"` | Scanner row field (parsers), Telegram alert nominal reference, entry checklist, display fallback |
| `risk_reward_base` | **midpoint** (`entry_for_selection`, aggressiveness=0.5) | `reward_risk(entry_mid, sl, tp)` rounded | Tooltip detail, diagnostic reference |
| `risk_reward_worst` | **far edge** (aggressiveness=1.0) | `reward_risk(entry_far, sl, tp)` rounded | Tooltip detail, diagnostic reference |
| `risk_reward_range` | dict `{best, base, worst}` | See above | Order dialog R:R tooltip, scanner detail screen |

**Backward compat:** `risk_reward` must always be the best-case "1:X.X" string.
Consumers that parse it (e.g., `_parse_rr()`, `parse_risk_reward()`) must be
aware it is best-case. Do NOT change its meaning.

**Display primary anchor:** the human-facing main R:R number is **base**
(zone midpoint), with the worst–best range shown alongside; best is secondary.
`ui.scanner_rr_formatters.format_order_rr_text()` and the scanner detail
R:R card implement this. `risk_reward` itself stays best-case for parsers.

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
fallback). They drive the execution guard and may appear as diagnostics in
the order dialog, but never replace the main best/base RR fields in the scan
result, gate, or ranking.

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

## TP1 quality and entry-zone contract

`build_trade_plan()` applies a quality floor before accepting TP1:

1. Candidate order: equal level → structural target zones from nearest to
   farthest → Fibonacci 0.382 (outside range regime) → nearest swing.
2. Candidate must be finite, on the correct side, and past the far edge of
   the entry zone.
3. Directional clearance must be at least `0.15 × ATR`.
4. Nominal RR from the midpoint must be at least `1.0`.
5. Spread-adjusted RR from the midpoint must be at least `1.3`.

For structural target zones, the executable TP1 is conservative:

- BUY: `zone.low - 0.03 × ATR`.
- SELL: `zone.high + 0.03 × ATR`.
- Missing/invalid boundaries fall back to `zone.level`.

Targets are filtered, sorted, and deduplicated by this executable price. If
the nearest target fails quality validation, the next target is tested. TP2
keeps its separate next-target/Fibonacci logic and minimum `0.15 × ATR` gap
from TP1.

Phase 16 separates source and execution geometry:

1. `source_zone` stores the original boundaries and zone-quality metadata.
   It is analysis/display data and cannot authorize execution.
2. `structural_execution_zone` is a proximal sub-zone fully contained within
   the source boundaries. Its target width comes from
   `execution_zone_width_atr_by_quality`, tiered by effective zone quality:
   `strong` 0.12 × ATR, `moderate` 0.18 × ATR, `weak` 0.25 × ATR. Higher-quality
   zones get a tighter sub-zone so TP1 keeps a reasonable clearance to both
   entry edges; lower-quality zones keep the wider legacy target.

   **Deliberate inverse (accepted trade-off):** a zone penalized for quality
   (stale, mitigated, over-tested, etc.) drops to a lower tier and therefore
   gets a *wider* entry band (`weak` 0.25 is the legacy width). This is
   intentional — `weak` deliberately keeps the legacy fill behavior instead of
   being tightened along with `strong`/`moderate`. Do not "fix" this direction:
   a worse zone keeping a wider band is by design, not a bug.

   **Values are heuristic (not swept):** the 0.12 / 0.18 / 0.25 targets are
   experience-based, not yet optimized by `param_sensitivity.py` / backtest
   sweep. They are the accepted *step 2* of the plan; confirm fill-rate impact
   on the backtest before treating them as calibrated.
3. BUY preserves the source high edge and moves the low edge inward. SELL
   preserves the source low edge and moves the high edge inward.
4. After SL and TP1 are selected, `_trim_execution_zone_for_effective_rr()`
   intersects the structural zone with the range satisfying
   `execution_zone_min_effective_rr`.
5. The resulting final zone is exposed as both `entry_zone` and
   `execution_zone`. All RR anchors and position sizing are recalculated from
   this final zone.
6. If TP1 is unavailable, RR-aware trimming is not applicable and the
   structural zone is preserved for monitoring. If the RR-valid intersection
   is empty, `entry_zone`/`execution_zone` are `None` and
   `EXECUTION_ZONE_RR_EMPTY` is emitted.

Directional SMC compatibility is strict:

- BUY: `demand_zone`, `bullish_order_block`, `bullish_fvg`.
- SELL: `supply_zone`, `bearish_order_block`, `bearish_fvg`.
- Broken or opposite-family zones cannot participate in preferred or fallback
  selection.
- Legacy explicitly selected payloads with `source="smc_selected"` and no
  type remain readable for backward compatibility; newly generated production
  zones always carry a canonical type.

Price quantization may make the measured ATR width differ slightly from its
target. The final rounded zone must remain inside the source zone and preserve
BUY/SELL symmetry.

### Entry/TP1 diagnostics

| Field | Meaning |
|---|---|
| `entry_zone_width` / `entry_zone_width_atr` | Actual entry-zone width in price/ATR units |
| `entry_zone_source` | Source of the selected entry zone |
| `source_zone` | Original zone boundaries, raw/effective score and selection metadata; reference only |
| `structural_execution_zone` | Proximal execution sub-zone before RR trimming |
| `execution_zone` | Alias of the final RR-valid `entry_zone` |
| `execution_zone_quality` / `execution_zone_width_atr_target` | Width tier and configured ATR target |
| `rr_trimmed` / `rr_trim_diagnostics` | Trim status, structural zone, RR boundary, final zone and pre/post worst RR |
| `tp1_source` | `equal_level`, `target_zone`, `fib_extension`, `swing`, or `none` |
| `tp1_clearance_from_far_edge` / `tp1_clearance_atr` | Directional distance from the far entry edge to TP1 |
| `tp1_effective_rr_base` | Alias of `expected_effective_rr_base` for the selected TP1 |
| `tp1_selection_diagnostics` | Candidate count, rejection counts, selected source, and 1-based target rank |

The score/source breakdown and TP-selection diagnostics are observational.
`structural_execution_zone`, final `entry_zone`/`execution_zone`, and
`rr_trim_diagnostics` are production planning contracts and therefore affect
whether an executable plan exists.

### Execution-zone consumer contract

| Consumer | Zone field | Same-scenario rule |
|---|---|---|
| Gate context | final `entry_zone` | Must match `best_side`; never borrow the opposite scenario |
| Scanner row | final `entry_zone` | Copied from the strict best-side scenario |
| Auto eligibility | final `entry_zone` | Missing/invalid zone rejects the candidate |
| Auto live guard | final `entry_zone` | Live ask/bid must remain inside it |
| Manual candidate/guard | final `entry_zone` | Uses the same scenario as SL/TP/RR |
| Order dialog | final `entry_zone` | `source_zone` appears only in tooltip/reference text |
| Scanner Detail | final `entry_zone` | Shows source/execution width and trim/reject reason |
| Chart payload | final `entry_zone` | Marked `execution_eligible=true`; source is `false` |

No consumer may fall back from a missing final execution zone to
`source_zone`, `watch_zone`, or an opposite-side scenario.

## Consumer contract matrix

| Consumer | RR field used | Anchor | Phase |
|---|---|---|---|
| **Gate** (`_gate_expected_effective_rr`) | `expected_effective_rr_for_gate` → `expected_effective_rr_base` → `expected_effective_rr` | base → best fallback | Phase 3 |
| **Ranking RR bonus** (`calculate_opportunity_score`) | `expected_effective_rr_base` → `expected_effective_rr` → `risk_reward` | base → best fallback | Phase 4A |
| **Sort `_safe_rr`** | `expected_effective_rr_base` → `expected_effective_rr` → `risk_reward` | base → best fallback | Phase 4A |
| **Scanner table column** | `expected_effective_rr` | best display; color thresholds also use best | Phase 8 |
| **Order dialog R:R column** | `risk_reward_range`/`risk_reward_base` (base) primary + worst–best range alongside; tooltip base/best/current; `risk_reward` (best string) only as fallback | base display + diagnostic | Phase 5C, 8 |
| **Auto-trade guard** | `current_effective_rr` at live/fallback price | live current | Phase 5B |
| **Manual order guard** | `current_effective_rr` at live/order_entry_fallback price | live current | Phase 5B |
| **Telegram alert** | `risk_reward` (best string) as nominal reference; primary display uses `expected_effective_rr_base` (base) with fallback `expected_effective_rr` (best) | base primary + best reference | Phase 7 |
| **Entry checklist** | `risk_reward` (best string) via `_parse_rr()` for pass/fail; note shows base/effective range as reference | best (unchanged) | Phase 11 |
| **Auto-trade eligibility** | `expected_effective_rr` (best effective) for backtest gate pre-filter | best effective | Phase 11 |
| **Diagnostics** (`result["diagnostics"]`) | All RR fields | best + base + current | Phase 5D |
| **Manual `execution_guard`** | `current_effective_rr` + `price_source` | live / order_entry_fallback / none | Phase 5D.1 |
| **TP1 quality selection** | `tp1_effective_rr_base` from midpoint | base effective quality floor | Phase 13B |

## Field relationship diagram

```
build_trade_plan()
  ├─ entry_for_rr (best edge, agg=0.0) ──► risk_reward, expected_effective_rr,
  │                                         entry_price (display)
  ├─ entry_for_selection (midpoint, agg=0.5) ──► risk_reward_base,
  │     expected_effective_rr_base, TP validation, display primary anchor
  ├─ entry_worst (far edge, agg=1.0) ──► risk_reward_worst,
  │     expected_effective_rr_worst, position_sizing (conservative lot)
  └─ TP1 candidate validation ──► tp1_source, tp1_clearance_atr,
        tp1_effective_rr_base, tp1_selection_diagnostics

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
6. `position_sizing` is anchored to the **far edge** (`entry_worst`, aggressiveness=1.0). This keeps real money risk at or below the configured percent for every fill inside the zone. Do not re-anchor to the best edge.
7. The human-facing main R:R display is **base** with the worst–best range alongside; best is secondary. Do not restore best-case as the primary display number.

## Config-backed quality parameters

| Parameter | Default |
|---|---:|
| `tp1_min_clearance_atr` | 0.15 |
| `tp1_min_effective_rr_base` | 1.3 |
| `tp_target_buffer_atr` | 0.03 |
| `entry_zone_buffer_atr` | 0.05 (legacy parameter; superseded by Phase 16 sub-zone logic) |
| `entry_zone_max_width_atr` | 0.50 (legacy parameter; superseded by Phase 16 sub-zone logic) |
| `entry_zone_half_width_atr` | 0.25 |
| `execution_zone_width_atr_by_quality.strong` | 0.12 |
| `execution_zone_width_atr_by_quality.moderate` | 0.18 |
| `execution_zone_width_atr_by_quality.weak` | 0.25 |
| `execution_zone_quality_thresholds.strong` | 70 |
| `execution_zone_quality_thresholds.moderate` | 50 |
| `execution_zone_min_effective_rr` | 1.3 |
| `execution_zone_rr_tolerance` | 0.0001 |

## Impact-analysis tools

- `scripts/compare_rr_anchor_impact.py` compares best/base effective RR impact.
- `scripts/compare_entry_tp_quality.py` reports entry width, TP1 clearance,
  rejection reasons, selected target rank, and optional baseline comparison.
- Operational snapshots may contain broker/market data and are local-only;
  `data/operational_baseline.json` is intentionally gitignored.

## Phase 16 validation and rollback

- Baseline comparison must separate source/watch scenarios from executable
  plans. A row containing source boundaries is not automatically executable.
- Required release metrics include directional mismatch count, source/effective
  score distribution, structural/final width in ATR, trim/reject rate, plans
  without TP1, and base/worst effective RR.
- Phase 16G.1 production validation found and fixed a fallback path that could
  select a bearish order block for BUY. Regression coverage now locks exact
  zone-family compatibility for preferred/fallback BUY and SELL paths.
- Operational snapshots are local, redacted, and gitignored. They are not a
  deterministic replay because market inputs can change between scans.
- Exact rollback is code-scoped: restore the pre-Phase-16 zone selection and
  planning implementation together with its consumers. Changing only width/RR
  config can soften behavior but cannot recreate the previous selection
  semantics.
- Never use `git reset --hard` on a dirty worktree. Create a scoped patch or
  commit checkpoint before rollout once repository changes are approved.
