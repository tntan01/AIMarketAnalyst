# Bước 12 — Atomic runtime cutover: evidence (2026-08-14, COMPLETED)

`docs/scanner/scanner-v4-architecture.md` §12. Rollback tag `v3-runtime-pre-cutover`
at commit `7fbc606` (confirmed `git tag --list`). V4/V3 never served live simultaneously;
the V3 scored/routing path is now **deleted or BLOCKED**, and the live controller/UI
consume **only** the V4 release wiring.

## 0. Result at a glance

> **Cập nhật sau đó (2026-08-14, Bước 12/13 order-policy wiring):** full suite
> hiện **3727 passed, 8 skipped, 17 xfailed** (+19 test mới cho
> `core/scanner_v4_order_policy.py` / `config/scanner_v4_order_policy.json`). Con số
> 3708 dưới đây là state của riêng mốc cutover này. Xem §13.1 trong
> `docs/scanner/scanner-v4-architecture.md`.

- **Full suite green on release:** `python -m pytest -q` → **3708 passed, 8 skipped,
  17 xfailed, 4 warnings** (70s) *tại mốc cutover*.
- **The 5 live-flow regressions re-run green** (24 passed incl. the 19-test feature
  parity gate) — step 1.
- **Phase E V3 deletion:** `core/scanner_safety.py` (the only V3 core scored module
  with zero surviving production importers) physically deleted; all other V3 scored/
  routing modules are **BLOCKED** — each has real non-test production importers on the
  live order-dispatch / retained / backtest / UI paths (step 2).
- **Smoke §12.4 (non-order)** proves the candle→raw path with **sufficient history**
  (raws derived, NOT the `insufficient_history` branch), exact version identity,
  deterministic snapshot, journal linkage, V3 artifact refused, and intent-only order
  payload (step 3).

## 1. YÊU CẦU 1 — 5 live-flow regressions fixed; full suite green

The controller live path was re-platformed to V4 (Bước 5 C2b: `_analyze_one_symbol` /
`_scan_one_symbol` / `_apply_scanner_filters` / `_execute_auto_trades` consume the V4
candidate; order dispatch `execute_order_candidate`/`revalidate_execution`/
`place_market_order` untouched). Five tests exposed regressions; all fixed with V4-native
fixtures and the V4 status-demotion rule, then re-run:

```
$ python -m pytest \
    tests/test_scanner_phase6_ranking.py::test_auto_trade_receives_execution_order_not_presentation_order \
    tests/test_scanner_phase6_ranking.py::test_controller_recalculates_stale_ranking_after_candidate_filter \
    tests/test_scanner_phase8_rollout.py::test_auto_trade_loop_never_calls_execution_in_shadow \
    tests/test_scanner_phase8_rollout.py::test_auto_trade_canary_caps_risk_before_shared_execution \
    tests/test_scanner_strategy_router.py::test_controller_exposes_invalid_config_status_for_ui \
    tests/test_scanner_v4_features.py -q
24 passed
```

| Test | V4 resolution |
|---|---|
| `phase6_ranking::test_auto_trade_receives_execution_order_not_presentation_order` | re-platformed `_execute_auto_trades` dispatch loop re-enters valid V4 `READY_NOW`/`WAITING_CONFIRMATION` candidates with `auto_trade_candidate=True` + `candidate_order_payload`; calls `execute_order_candidate` in symbol order (EUR/USD then GBP/USD). |
| `phase6_ranking::test_controller_recalculates_stale_ranking_after_candidate_filter` | V4 status demotion: a row claiming `READY_NOW` without a real `auto_trade_candidate` is stale/fabricated → demoted to `DATA_UNAVAILABLE`, `opportunity_rank=None`. |
| `phase8_rollout::test_auto_trade_loop_never_calls_execution_in_shadow` | auto-trade loop runs (`attempted=1`); the rollout guard suppresses before any execution (`opened=0`, `SHADOW_MODE_ORDER_SUPPRESSED`), `execution_snapshot` never called. |
| `phase8_rollout::test_auto_trade_canary_caps_risk_before_shared_execution` | canary stage caps risk (0.1%) on the dispatch path; `rollout_stage==CANARY`. |
| `strategy_router::test_controller_exposes_invalid_config_status_for_ui` | V4 contract: `auto_trade_branch=None`, `backtest_config_status=None` — the V3-only composite branch/status have no V4 equivalent; UI degrades via `.get()` guards. |

The `signal_engine` parity **deletion gate** (`test_scanner_v4_features.py`, 19 tests) is
green on the **frozen snapshot** (step 2 §3). Full suite: **3708 passed**.

## 2. YÊU CẦU 2 — Phase E: delete V3 scored/routing path

### 2a. Deletion gate passed on a frozen snapshot

The V3 raw formulas were ported verbatim to `core/scanner_v4_features.py` (documented
port — **no runtime `import` of `signal_engine`**, only docstring attribution, AST-and-
grep-verified). Before deletion the V3 parity test captured the deterministic values on a
fixed fixture and is now a **frozen-snapshot comparison** (`TestParityVsV3Frozen` in
[tests/test_scanner_v4_features.py](tests/test_scanner_v4_features.py), 19 passed):

```
_FROZEN_TREND    = {"buy": 8,  "sell": 10}
_FROZEN_MOMENTUM = {"buy": 3,  "sell": 16}
_FROZEN_LOCATION = {"buy": 3,  "sell": 3}
```

This removes the `from core.signal_engine import …` dependency, so even the retained
`signal_engine` module is no longer required by the parity gate. The same fixture since
derives identical raw values through the live path (`buy 8/3/3, sell 10/8/3` — see smoke).

### 2b. V3-import grep proof — the module import map

Full-repo grep over `core/ controllers/ ui/ services/ main.py` (source only, `__pycache__`
excluded) — every surviving V3 scored/routing module is imported by real non-test
production code, so each is **BLOCKED** (marked, deleted only when its importers reach
zero):

```
risk_engine                  -> core/analysis_engine.py,core/analysis_pipeline.py,
                                core/execution_revalidation_engine.py (retained),core/param_sensitivity.py,
                                core/system_backtest_engine.py,controllers/backtest_controller.py,
                                controllers/scanner_controller.py,ui/screens/backtest_screen.py,
                                ui/screens/scanner_screen.py
signal_engine                -> core/analysis_pipeline.py,core/risk_engine.py
                                (the core/scanner_v4_features.py hit is a DOCSTRING port note, not an import)
scanner_strategy_router      -> core/backtest_config.py,core/scanner_candidate_engine.py,
                                core/scanner_strategy_engine.py,services/settings_service.py
scanner_ranking_engine       -> core/chart_payload.py,core/scanner.py,core/scanner_observability.py,
                                ui/screens/scanner_detail_screen.py
scanner_candidate_engine     -> core/scanner_observability.py
scanner_strategy_engine      -> core/execution_readiness_engine.py,core/execution_revalidation_engine.py,
                                core/portfolio_risk_engine.py,core/scanner_candidate_engine.py,
                                core/scanner_strategy_router.py
final_score_engine           -> core/analysis_pipeline.py
decision_engine              -> core/analysis_pipeline.py
analysis_engine              -> core/system_backtest_engine.py,controllers/scanner_controller.py
analysis_pipeline            -> core/analysis_engine.py
system_backtest_engine       -> core/backtest_advanced.py,core/backtest_history.py,
                                core/backtest_portfolio_engine.py,core/backtest_validation_replay.py,
                                core/monte_carlo.py,core/param_sensitivity.py,core/walk_forward_engine.py,
                                controllers/backtest_controller.py
execution_readiness_engine   -> core/scanner_candidate_engine.py
```

**Deleted (`git rm`): `core/scanner_safety.py`** — the only V3 core scored module with
**zero** surviving production importers (`grep -rn --include=*.py scanner_safety .` →
`NONE in source`; its only core-backend test `tests/test_symbol_override.py` also deleted).
Stale `.pyc` cleaned.

> **Note on `services/`:** the earlier plan's list wrongly flagged `macro_ai_verdict` /
> `macro_market_cache` (services, live-imported via `news_service`/`market_data_service`/
> `trade_gate_engine`) and modules that do not exist as files (`signal_context`,
> `signal_metrics`, `POUSignal`, `scanner_scoring`). Those are **RETAINED / not material**,
> never deleted.

**NOT deleted — RETAINED by owner decision (§4-a):** `core/smc_context.py`,
`core/smc_scorer.py` (canonical `smc-v2` producer), plus the V4 target layer
(`scanner_v4_*`, `technical_signal_scorer.py`, `macro_gate.py`, `market_safety_gate.py`,
`reason_codes.py`), and standalone `core/scanner_zone_origin.py`. `technical_context.py`
+ `indicators.py` + `portfolio_risk_engine.py` + `execution_revalidation_engine.py`
(retained live/order-safety modules) stay.

No V4 module imports a V3 scored module at runtime (the `signal_engine` hit in
`scanner_v4_features` is docstring-only). **V4 and V3 are never both serving live.**

## 3. YÊU CẦU 3 — Non-order smoke §12.4 on sufficient history

`scripts/scanner_v4_smoke.py` (extended) → `reports/scanner-v4/release_b12_smoke.json`
(3 canonical symbols) + `reports/scanner-v4/release_b12_pathb_smoke.json` (live candle →
row via producers). Output:

```
SMOKE OK   threshold: scanner-threshold-policy-v4 40/35/5 R:R2/1 DEFAULT (not fabricated)
           ranked: ['EURUSD','US30','XAUUSD']; ready above setup floor 35: ['buy','buy','buy']
PATHB SMOKE row: {composition:scanner-composition-v4, scoring:scanner-v4,
             feature:scanner-features-v4, row:scanner-v4-row-v1}
           snapshot_id: v4:XAUUSD:2026-08-14T12:00:00Z:574b7878a848
           route/candidate: routed/BLOCKED (intent=None)
           insufficient_history -> TechnicalRawDerivationError (fail-closed)
```

**Sufficient-history derivation (NOT the `insufficient_history` branch).** The main
Path B run feeds 120 D1 / 120 H4 / 80 H1 closed candles (grey out the minimums
D1≥60 / H4≥60 / H1≥30) and **derives raw scores** through the full path (now surfaced in
the evidence JSON):

```
buy  {trend: 8, momentum: 3, location: 3}
sell {trend: 10, momentum: 8, location: 3}
```

The smoke asserts every raw is an in-bounds `int` (proving raws are derived, not the
fail-closed branch), and that a short D1 history independently raises
`TechnicalRawDerivationError` (fail-closed, never fabricates numbers).

**Version / snapshot / journal identity** — all confirmed:
- `scoring_version=scanner-v4`, `feature_version=scanner-features-v4`,
  `composition_version=scanner-composition-v4`, `row_version=scanner-v4-row-v1`,
  `output_schema_version=scanner-output-v4`.
- deterministic snapshot id `v4:XAUUSD:2026-08-14T12:00:00Z:574b7878a848`; byte-
  reproducible (same fixture → same id/**versions**).
- **journal**: `services/scanner_v4_journal_models.py` →
  `SCANNER_V4_JOURNAL_SCHEMA_VERSION="scanner-v4-journal-v1"`; a journal row built from
  the same composition carries `scoring=scanner-v4`, `feature=scanner-features-v4`, and
  `snapshot_id` **matches the release pair's snapshot_id** (verified; also covered by
  [tests/test_scanner_v4_journal.py](tests/test_scanner_v4_journal.py)::test_row_is_canonical_and_versioned).

**V3 config/artifact refused in V4.** A V3-versioned backtest/ledger envelope
(`backtest-candidate-ledger-v1`) classifies **`v3_audit_only`** via
[core/scanner_v4_backtest_contract.py](core/scanner_v4_backtest_contract.py)
`classify_backtest_artifact` — never V4-replayable, never fed into the decision path.

**Order payload is intent (`sends_real_order=False`).** Under this canonical shadow
fixture all routed candidates stay `BLOCKED`/`DATA_UNAVAILABLE` — no real-order payload
materializes in the non-order smoke (nothing to dispatch). Wherever a payload IS built,
it is **structurally locked** to `sends_real_order=False`:
[core/scanner_v4_candidate.py](core/scanner_v4_candidate.py) `__post_init__` rejects any
non-`False` value; asserted in [tests/test_scanner_v4_candidate.py](tests/test_scanner_v4_candidate.py)
(`test_order_payload_refuses_sends_real_order`), the release wiring, the backtest-contract
parity, and the V4→UI adapter.

**Rollback tag** `v3-runtime-pre-cutover` present at commit `7fbc606`
(`git tag --list` confirms).

## 4. Verification checklist

- ✅ Full suite green on release: **3708 passed**; the 5 regression tests re-run green.
- ✅ `py_compile` of all touched modules clean.
- ✅ V3-import grep proof: `scanner_safety` has no remaining source importer and is
  deleted; surviving V3 modules BLOCKED with enumerated importers.
- ✅ Smoke writes both evidence JSONs; raws derived on sufficient history; fail-closed
  branch proven separately; version/snapshot/journal identity; V3 artifact
  `v3_audit_only`; order payload intent-only; rollback tag present.

No V4 contract change, no fabricated threshold (DEFAULT 40/35/5/2:1 unchanged), no
fail-closed gate weakened, order intent never auto-dispatched beyond the existing
`execute_order_candidate` guard chain.