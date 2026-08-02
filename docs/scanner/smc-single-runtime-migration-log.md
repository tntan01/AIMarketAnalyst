# Log triển khai — SMC single runtime migration

> Đi kèm: `docs/scanner/smc-single-runtime-migration-plan.md`
> Bắt đầu: 2026-08-02

## Bước 01 — Baseline kiểm thử

Lệnh:

```powershell
python -m pytest -q tests/test_smc_scorer_v2.py tests/test_smc_scoring_phase0.py tests/test_smc_consumer_phase6.py tests/test_smc_prefilter.py tests/test_analysis_pipeline_integration.py tests/test_scanner_observability.py tests/test_smc_phase8_rollout.py tests/test_backtest_config_validation.py
```

| Chỉ số | Giá trị |
|---|---|
| Pass | 98 |
| Fail | 0 |
| Thời gian | 2.06s |
| Warning | 1 |

Warning (duy nhất, ngoài phạm vi dự án):

```
DeprecationWarning: datetime.datetime.utcfromtimestamp() is deprecated
  C:\Users\tntan\AppData\Roaming\Python\Python314\site-packages\google\protobuf\internal\well_known_types.py:91
```

**Kết luận:** Baseline XANH — khớp mục tiêu 98 pass. Không có lỗi có sẵn cần PO chấp nhận.

## Bước 02 — Golden fixture của kết quả SMC chuẩn

**File tạo mới:**

- `tests/fixtures/smc_canonical/golden_cases.json` — fixture `smc-canonical-golden-v1`, 8 case.
- `tests/test_smc_canonical_golden.py` — test characterization riêng (10 test).

**8 case tối thiểu (đều đạt đúng kịch bản mong muốn):**

| Case | Kịch bản | Kết quả khóa |
|---|---|---|
| `buy_selected_zone` | BUY có selected zone | buy smc=12/15, zone `z-buy-h4` (demand_zone, H4) |
| `sell_selected_zone` | SELL có selected zone | sell smc=5/15, zone `z-sell-h4` (supply_zone, H4) |
| `no_zone` | No-zone | cả 2 side không có zone; scenario fallback |
| `fvg_h1_only` | FVG H1-only | buy zone `z-buy-h1-fvg` (bullish_fvg, H1) |
| `order_block` | Order block | buy zone `z-buy-h4-ob` (bullish_order_block, H4) |
| `broken_stale` | Broken/stale zone | sell broken → no-zone; buy stale vẫn được chọn |
| `choch_cap` | CHOCH cap | buy smc=8, cap `H1_CONFIRMED_CHOCH_CAP_8`, penalty `H1_CHOCH_AGAINST_SIDE` |
| `missing_data_valid` | Thiếu dữ liệu hợp lệ | ATR thiếu → no-zone, scenario `stand_aside`, không crash |

**Field khóa (không lấy từ payload legacy/shadow/comparison):** `smc_quality`, `signal_score`, `scoring_version`, selected zone ID/type/timeframe, `score_breakdown`, `direction_bias.best_side`, `trade_gate`, `decision_engine`, order payload của primary scenario.

**Cách chạy:** test monkeypatch `build_smc_context`/`build_technical_snapshot`/`detect_market_regime` trong `core.analysis_pipeline`, chạy `analyze_symbol(..., smc_scoring_mode="v2")`, đối chiếu toàn bộ expected. Guard test khẳng định expected không chứa key SMC shadow/legacy/comparison.

| Chỉ số | Giá trị |
|---|---|
| Golden test | 10 passed |
| Baseline sau khi thêm | 98 passed, 0 fail |

**Kết luận:** Golden test pass trên code chưa refactor và không phụ thuộc payload `legacy/shadow/comparison`. Điều kiện hoàn thành Bước 02 đạt.

## Bước 03 — Khóa lớp an toàn Scanner rollout

**File sửa (chỉ thêm test):**

- `tests/test_scanner_phase8_rollout.py` — thêm 3 test.
- `tests/test_scanner_observability.py` — thêm 1 test.

**Test thêm mới:**

| Test | Khóa hành vi |
|---|---|
| `test_scan_emits_generic_shadow_decision_comparison_when_enabled` | Chạy `_run_market_scan_core` với comparison bật → emit `SHADOW_DECISION_COMPARISON`, **không** emit `SMC_SHADOW_COMPARISON`; payload generic (v1/v2) |
| `test_scan_does_not_emit_shadow_comparison_when_disabled` | `shadow_compare_enabled=False` → không emit `SHADOW_DECISION_COMPARISON` |
| `test_generic_shadow_comparison_stays_gated_by_enabled_flag` | `build_shadow_report(enabled=True/False)` → comparison có/không |
| `test_generic_shadow_comparison_feeds_candidate_not_smc_payload` | Comparison generic chứa field candidate `v1`/`v2`, không chứa key SMC shadow router |

**Test giữ sẵn (đã có, xác nhận pass):** Stage `SHADOW` chặn order với `SHADOW_MODE_ORDER_SUPPRESSED`; kill switch ưu tiên chặn execution; release gate dùng generic sample/disagreement.

| Chỉ số | Giá trị |
|---|---|
| `test_scanner_phase8_rollout.py` + `test_scanner_observability.py` | 41 passed |
| Baseline + golden + rollout | 136 passed, 0 fail |

**Kết luận:** Có test đỏ nếu ai xóa generic Scanner shadow (`ROLLOUT_SHADOW` / `SHADOW_MODE_ORDER_SUPPRESSED` / `SHADOW_DECISION_COMPARISON` / generic comparison). Điều kiện hoàn thành Bước 03 đạt.

## Bước 04 — Kết quả SMC canonical duy nhất (contract đích)

**File tạo mới:**

- `core/smc_scoring_result.py` — module contract trung tính.
- `tests/test_smc_scoring_result.py` — 17 test.

**Contract đích (khớp mục 3.2):**

- `SmcScoringResult`: `contract_version="smc-scoring-canonical-2026-08"`, `scoring_version` (provenance, không phải mode), `sides` (buy/sell).
- `SmcSideScoringResult`: `score`, `selected_zone`, `selected_zone_id/type/timeframe`, `breakdown`, `reason_codes` — đủ cho consumer/risk/UI.
- `to_dict()` / `from_dict()` trung tính; `from_dict` bỏ qua key lạ (legacy/shadow/comparison/policy) để đọc snapshot cũ mà không chọn nhánh v1.

**Tính trung lập:**

- Public name chỉ gồm `SmcScoringResult`, `SmcSideScoringResult`, `SMC_SCORING_CONTRACT_VERSION`, `VALID_SIDES` — không chứa v1/v2/legacy/shadow.
- Hằng version nhập từ `core.smc_versions` được alias private (`_CANONICAL_SCORER_VERSION`), không lộ tên public.
- Không có mode selector: test khẳng định module không có `resolve_smc_scoring_policy`, `normalize_smc_scoring_mode`, `SMC_MODE_*`, `build_smc_phase0_diagnostics`, `apply_smc_score_override`.

| Chỉ số | Giá trị |
|---|---|
| `tests/test_smc_scoring_result.py` | 17 passed |
| Baseline + golden + rollout + result | 153 passed, 0 fail |

**Kết luận:** Contract mới đứng độc lập, chưa thay runtime, không có mode selector. Điều kiện hoàn thành Bước 04 đạt.

## Bước 05 — Scorer hiện tại thành module SMC canonical

**File đổi:**

- `core/smc_scorer_v2.py` → `core/smc_scorer.py` (git mv, giữ nguyên nội dung công thức).
- Đổi `score_smc_v2()` → `score_smc()`; `select_smc_zone_v2()` → `select_smc_zone()`.
- Giữ `evaluate_smc_zones()`, `EvaluatedSmcZone`; `SMC_SCORER_V2_VERSION` chỉ là provenance dữ liệu.
- Docstring module bỏ cụm "used in shadow mode".
- **Không tạo wrapper runtime** tên `score_smc_v2`.

**Cập nhật import trực tiếp:**

- `core/smc_scoring_contract.py`: import + gọi `score_smc`.
- `core/smc_prefilter.py`: import + gọi `score_smc` (+ docstring).
- `tests/test_analysis_pipeline_integration.py`: import, gọi, patch target.
- `tests/test_smc_prefilter.py`: patch target.
- `tests/test_smc_scorer_v2.py`: chuyển sang API canonical.

`rg` toàn runtime/test: không còn `smc_scorer_v2` / `score_smc_v2` / `select_smc_zone_v2` (chỉ còn trong docs lịch sử).

| Chỉ số | Giá trị |
|---|---|
| `test_smc_scorer_v2.py` + prefilter + phase0 + consumer + pipeline + golden | 72 passed |
| Full migration-relevant suite | 153 passed, 0 fail |
| Golden parity (Bước 02) | pass — output BẰNG implementation v2 cũ |

**Kết luận:** Một scorer canonical với output bằng implementation v2 cũ. Điều kiện hoàn thành Bước 05 đạt.

## Bước 06 — Chuẩn hóa version provenance

**File chính (theo plan):**

- `core/smc_versions.py`: `SMC_SCORER_VERSION = "smc-v2"` (một hằng public duy nhất); xóa `SMC_SCORER_V2_VERSION`; thêm `SMC_RAW_ZONE_VERSION = "smc-v1"` cho raw/candidate zone (Bước 24 sẽ xóa); giữ `SMC_CONFLUENCE_VERSION`.
- `core/scoring_provenance.py`: `build_scoring_provenance()` không nhận mode, luôn trả canonical `smc-v2`; `normalize_scoring_provenance()` bỏ `fallback_mode`.

**Ripple bắt buộc (version không còn phân biệt v1/v2):**

- `core/smc_models.py`: `SmcZone.scoring_version` default + `from_legacy_dict` → `SMC_RAW_ZONE_VERSION` (raw zone giữ "smc-v1", **không** gắn nhãn v2 — đúng quy tắc 4/5); `SelectedSmcZone`/`SmcScoreBreakdown` → `SMC_SCORER_VERSION`.
- `core/smc_scoring_contract.py`: xóa `SMC_SHADOW_BASELINE_VERSION`; policy dùng `SMC_SCORER_VERSION`; active snapshot version → `SMC_RAW_ZONE_VERSION` (giữ phân biệt legacy="smc-v1" vs shadow="smc-v2", tránh `SCORING_VERSION_PAIR_INVALID`).
- `core/smc_scorer.py`, `core/backtest_config.py`, `core/backtest_config_validation.py`, `core/scanner_strategy_router.py`: `SMC_SCORER_V2_VERSION` → `SMC_SCORER_VERSION`.
- Callers của provenance: `analysis_pipeline.py`, `scanner.py`, `scanner_observability.py`, `system_backtest_engine.py` — bỏ đối số mode.
- `core/scanner_rollout.py`: `run_rollback_drill` bỏ check "restore v1" (không còn v1 để rollback), thay bằng `legacy_is_metadata_only` — đúng hướng Bước 21.
- Tests: `test_smc_scorer_v2.py`, `test_smc_phase8_rollout.py` (provenance không mode), `test_smc_scoring_phase0.py`, `test_smc_domain_models.py` (raw zone label).

**Xác nhận:** `SMC_SCORER_V2_VERSION` / `SMC_SHADOW_BASELINE_VERSION` không còn trong runtime; `SmcZone` default vẫn "smc-v1"; provenance trả `smc-v2`.

| Chỉ số | Giá trị |
|---|---|
| Migration-relevant suite | 186 passed |
| Full `python -m pytest -q` | 2223 passed, 8 skipped, 17 xfailed |

**Lưu ý ngoài phạm vi:** `config/interest_rates.json` có thay đổi `_last_updated` (thuộc người dùng/PO, không do tác vụ này). Theo plan không sửa/format/revert — để nguyên.

**Kết luận:** Version là metadata, không thể dùng để route sang scorer khác. Điều kiện hoàn thành Bước 06 đạt.

## Bước 07 — Tách composition khỏi scorer v1

**File:**

- `core/signal_engine.py` — thêm `compose_scenario_score()`; `score_scenario()` giờ gọi nó (vẫn dùng `smc_quality_score` v1 cho SMC input).

**`compose_scenario_score(side, technical, *, smc_quality, smc_reason, smc_flags, risk_score, macro_score, macro_confidence, market_regime, correlation_adjustment, macro_context, scoring_version, smc_score_breakdown)`:**

- Nhận SMC side score/flags/breakdown đã tính sẵn — **không gọi `smc_quality_score`**.
- Giữ nguyên: regime weight (kể cả discard Phase 15B), CHOCH cap, penalty cleanup, score clamping.
- `score_scenario` v1: `smc_quality, smc_reason = smc_quality_score(...)`; `smc_flags = extract_smc_trade_flags(...)`; rồi gọi composition. Output giữ nguyên (test xác nhận).
- `apply_smc_score_override` chưa đụng (Bước 08 sẽ thay đường pipeline; Bước 13 xóa).

**Test mới `tests/test_smc_composition.py` (3 test):**

| Test | Khóa |
|---|---|
| `test_composition_reproduces_golden_v2_final_scores` | Composition (với `smc_quality` golden + `extract_smc_trade_flags` + `calc_risk_condition` + macro defaults) tái tạo đúng `signal_score`/`smc_quality` của golden fixture cho cả buy/sell cả 8 case |
| `test_composition_does_not_call_smc_quality_score` | Patch `smc_quality_score` ném lỗi → composition vẫn chạy |
| `test_score_scenario_matches_composition_with_v1_quality` | `score_scenario` vs `compose_scenario_score` cùng input → cùng `signal_score`/`smc_quality`/`penalty_codes`/`smc_score_cap` |

| Chỉ số | Giá trị |
|---|---|
| `tests/test_smc_composition.py` | 3 passed |
| Migration-relevant suite | 164 passed |
| Full `python -m pytest -q` | 2226 passed, 8 skipped, 17 xfailed |

**Kết luận:** Tính được final scenario score KHÔNG cần gọi `smc_quality_score()`. Điều kiện hoàn thành Bước 07 đạt.

## Bước 08 — Pipeline gọi SMC canonical đúng MỘT lần

**File chính:**

- `core/analysis_pipeline.py` — viết lại `_step_score_scenarios`:
  - Gọi `score_smc()` **một lần** (reuse `_precomputed_v2_result` nếu Tier-1 đã tính).
  - Compose BUY/SELL qua `compose_scenario_score` (không dùng `score_scenario` v1, không `apply_smc_score_override`).
  - Consumer build từ chính result canonical (`build_smc_consumer_from_canonical_result`).
  - `_smc_scoring_diagnostics` = `{contract_version, scoring_version, sides, consumer_contract}` — **không** đọc `decision`/`active`/`shadow`; không gọi `build_smc_phase0_diagnostics`.
- `core/smc_consumer_contract.py` — thêm `build_smc_consumer_from_canonical_result(result)`.

**Hệ quả (đúng hướng plan):** `smc_scoring_mode` không còn route scorer; mọi mode cho cùng kết quả canonical. Event `SMC_SHADOW_COMPARISON` không còn phát sinh từ pipeline (Bước 19); SMC comparison metrics trong `build_shadow_report` = 0 (Bước 20).

**Kiểm tra "gọi đúng 1 lần":**
- Spy test mới `test_score_smc_is_called_exactly_once_per_symbol` (trong `test_smc_canonical_golden.py`).
- `test_tier1_survivor_reuses_precomputed_v2_result_and_runs_full_pipeline` — patch target đổi sang `core.analysis_pipeline.score_smc`.

**Tests cập nhật do contract đổi:**
- `test_smc_scoring_phase0.py`: `test_shadow_is_isolated_...` → `test_smc_modes_all_route_to_single_canonical_scorer` (mọi mode cùng output; `smc_scoring` không còn policy/shadow/comparison).
- `test_scanner_fast_path.py` + `test_scanner_fast_path_baseline.py`: helpers đọc `sides` thay vì `decision`/`policy`; `full-oracles.json` regenerate (selected_zone_ids giữ nguyên, bỏ `smc_policy`, thêm `scoring_version`; `mode_legacy`/`mode_shadow` giờ trùng v2).

| Chỉ số | Giá trị |
|---|---|
| Golden parity | pass |
| Migration-relevant suite | 176 passed |
| Fast-path suite | 32 passed |
| Full `python -m pytest -q` | 2227 passed, 8 skipped, 17 xfailed |

**Kết luận:** Full analysis không đi qua scorer v1 hoặc shadow router; `score_smc()` gọi đúng 1 lần/symbol (Tier-1 reuse). Điều kiện hoàn thành Bước 08 đạt.

## Bước 09 — Tái sử dụng kết quả Tier-1 prefilter

**File:**

- `core/smc_prefilter.py` — xóa tham số `mode` + `resolve_smc_scoring_policy` khỏi prefilter; `_base_decision` bỏ `requested_mode`/`mode`; prefilter luôn gọi `score_smc()` và trả `precomputed_smc` (canonical result).
- `core/analysis_pipeline.py` — Tier-1 gọi `evaluate_post_context_prefilter(smc=..., technical=..., market_regime=...)` (không mode); rename `_precomputed_v2_result` → `_precomputed_smc`; full route reuse nguyên object (không serialize/deserialize).

**Tests:**

- `test_smc_prefilter.py`: bỏ `mode=` ở mọi call; xóa `test_legacy_and_shadow_always_fail_open` (không còn khái niệm mode fail-open); rename `precomputed_smc`.
- `test_scanner_fast_path.py`: `_derive_would_reject` bỏ `mode=`; helpers đã dùng canonical (Bước 08).
- `test_analysis_pipeline_integration.py`: `test_tier1_survivor_reuses_precomputed_smc_and_runs_full_pipeline`.
- `test_smc_canonical_golden.py`: thêm `test_tier1_survivor_total_score_smc_calls_is_one` — spy cả `smc_prefilter.score_smc` + `analysis_pipeline.score_smc`, chạy với `scanner_fast_tier1=True` (real prefilter), khẳng định **tổng call = 1**.

| Chỉ số | Giá trị |
|---|---|
| Golden + spy tests | 12 passed |
| Prefilter + integration + fast-path | 66 passed |
| Full `python -m pytest -q` | 2226 passed, 8 skipped, 17 xfailed |

**Kết luận:** Fast path và full route cùng dùng một scorer (`score_smc`) và một kết quả (`precomputed_smc`), tổng call count = 1/symbol. Điều kiện hoàn thành Bước 09 đạt.

## Bước 10 — Fail-closed khi SMC lỗi

**File:**

- `core/smc_prefilter.py`:
  - **Phân biệt**: insufficient-data (`_is_evaluable_context` False — thiếu price/ATR/zone malformed) → `_fail_open` (full route chạy an toàn).
  - Scorer exception (`score_smc`/`_selected_zone_ids` ném lỗi) → **fail-closed**: `should_reject=True`, `fail_open=False`, `reason_code=SMC_SCORING_ERROR`, `scorer_error=True`.
- `core/analysis_pipeline.py`:
  - Tier-1: decision fail-closed (SMC_SCORING_ERROR) → `_prepare_structural_reject` → return sớm, **không retry full route**.
  - `_step_score_scenarios`: `score_smc` exception → `_prepare_structural_reject(SMC_SCORING_ERROR)` + return; `execute` kiểm tra `_structural_reject` sau step 3 → trả blocked result ngay (không chạy scenarios/gate/final).
  - Fix `require_preferred_zones=True` (canonical selected zone là nguồn duy nhất).
- `controllers/scanner_controller.py`: **không cần đổi logic** — rule 4 đã được đảm bảo: row `structural_reject` → `_apply_scanner_filters` set `candidate_order_payload=None` (`is_structural_reject_row`), `_execute_auto_trades` skip khi `auto_trade_candidate=False`. Đã xác minh empirical (`auto_trade_candidate=False`, `candidate_status=OUT_OF_STRATEGY`).

**Tests:**

- `test_smc_prefilter.py`: `test_v2_scorer_exception_fails_closed` (fail-closed + `SMC_SCORING_ERROR` + `scorer_error`); insufficient-data vẫn fail-open (các test cũ).
- `test_smc_canonical_golden.py`: `test_tier1_scorer_error_fails_closed_without_retry` (inject exception → không scorer thứ 2, không candidate), `test_full_route_scorer_error_fails_closed` (blocked + no candidate).

| Chỉ số | Giá trị |
|---|---|
| Migration-relevant suite | 156 passed |
| Full `python -m pytest -q` | 2228 passed, 8 skipped, 17 xfailed |

**Kết luận:** Mọi lỗi scorer fail-closed (SMC_SCORING_ERROR), không fallback, không retry; blocked row không tạo candidate/order. Điều kiện hoàn thành Bước 10 đạt.

## Bước 11 — Đơn giản hóa SMC consumer

**File:**

- `core/smc_consumer_contract.py` — viết lại:
  - Xóa `build_smc_consumer_contract` (builder cũ đọc policy/active/shadow) + `_find_selected_zone` (chỉ phục vụ active lookup).
  - Chỉ còn `build_smc_consumer_from_canonical_result` (từ Bước 08) + `selected_zone_for_side` + `side_consumer_metadata`.
  - Xóa field `shadow_selected_zone*`, `shadow_scoring_version`, `selection_source`, `decision_source`, `decision_impact_allowed`.
  - Giữ: `selected_zone`, `selected_zone_id/type/timeframe`, `selected_zone_quality/relevance/setup_score`, `score_breakdown`, `scoring_version`.
  - Bump `SMC_CONSUMER_CONTRACT_VERSION` → `"smc-consumer-v2"`.
- `core/smc_validation.py` — fallback `shadow_selected_zone_id` → `selected_zone_id` (consumer không còn field shadow).

**Tests:**

- `test_smc_consumer_phase6.py`: `test_consumer_contract_keeps_shadow_out_of_active_decision_path` → `test_consumer_contract_selects_buy_and_sell_from_one_result` (dùng `build_smc_consumer_from_canonical_result`, xác nhận BUY/SELL selection, không có shadow fields).

`rg` toàn `core`: không còn `build_smc_consumer_contract` / `shadow_selected_zone`.

| Chỉ số | Giá trị |
|---|---|
| Migration-relevant suite | 167 passed |
| Full `python -m pytest -q` | 2228 passed, 8 skipped, 17 xfailed |

**Kết luận:** Consumer không biết khái niệm mode/shadow. Điều kiện hoàn thành Bước 11 đạt.

## Bước 23 (chèn sớm, trước Bước 12) — Bump Backtest config schema + revalidation

**File:**

- `core/backtest_config_validation.py`:
  - `BACKTEST_CONFIG_SCHEMA_VERSION` 8 → **9**; `BACKTEST_VALIDATION_VERSION` → `backtest-v9-statistical-validation-v1`.
  - Xóa `smc_scoring_mode` khỏi `_FINGERPRINT_FIELDS`, identity (config ID), và output config.
  - `_validate_scoring_contract`: bỏ check `smc_scoring_mode == SMC_MODE_V2`, **giữ** check `smc_scorer_version == SMC_SCORER_VERSION` ("smc-v2").
- `core/backtest_config.py`: xóa import `SMC_MODE_V2`; xóa `backtest_smc_scoring_mode` khỏi `_VALIDATION_SETTING_FIELDS`, `apply_validated_backtest_config`, `preserve_or_invalidate_manual_config`, `serialize_backtest_config`.
- `core/scanner_strategy_router.py`: xóa import `SMC_MODE_V2`; xóa check `smc_scoring_mode` + runtime `smc_mode`; xóa mapping entries dead `BACKTEST_SMC_SCORING_MODE_MISMATCH`/`BACKTEST_RUNTIME_SMC_MODE_MISMATCH`; **giữ** `smc_scorer_version` check + runtime version mismatch.

**Xác minh (empirical):**
- Config mới: schema 9, `smc_scorer_version="smc-v2"`, **không** có `smc_scoring_mode`, status VALIDATED.
- Config cũ (schema 8): status INVALID với `BACKTEST_SCHEMA_VERSION_MISMATCH` + `BACKTEST_VALIDATION_VERSION_MISMATCH` + `BACKTEST_VALIDATION_FINGERPRINT_INVALID` → **fail-closed, yêu cầu revalidation**.
- `rg`: không còn `from core.smc_scoring_contract import SMC_MODE_V2` trong core → Bước 12 xóa `smc_scoring_contract` an toàn.

**Tests:**
- `test_backtest_config_validation.py`: bỏ `smc_scoring_mode` khỏi helper + assertion; thêm `assert "smc_scoring_mode" not in payload`.
- `test_scanner_strategy_router.py`: `test_config_without_smc_v2_scorer_version_fails_closed` (giữ version check); `test_legacy_runtime_cannot_use_thresholds_calibrated_for_v2` (bỏ mode mismatch).

**Lưu ý vận hành (rule 6):** Trước deployment phải **kiểm kê các Backtest config đang enabled** trên môi trường phát hành và revalidate theo schema 9 — đây là việc vận hành, không phải thay đổi code trong bước này.

| Chỉ số | Giá trị |
|---|---|
| Backtest + strategy router suite | 72 passed |
| Full `python -m pytest -q` | 2228 passed, 8 skipped, 17 xfailed |

**Kết luận:** Mọi Backtest config dùng cho Scanner phải chứng minh `smc_scorer_version="smc-v2"` (schema 9); config cũ fail-closed cần revalidation. Điều kiện hoàn thành Bước 23 đạt.

## Bước 12 — Xóa SMC scoring router cũ

**Đã xóa:** `core/smc_scoring_contract.py` (router `build_smc_phase0_diagnostics`, `resolve_smc_scoring_policy`, `normalize_smc_scoring_mode`, constants `SMC_MODE_LEGACY/SHADOW/V2`, comparison builder).

**Runtime importers xử lý:**

- `core/scanner.py` — `build_scanner_output` dùng `scoring_provenance["smc_scorer_version"]`/`["smc_scoring_mode"]` (canonical) thay `resolve_smc_scoring_policy`/`normalize_smc_scoring_mode`.
- `core/scanner_observability.py` — `create_scan_context` dùng `SMC_SCORER_VERSION` + `"v2"` (canonical).
- `core/scanner_rollout.py` — `run_rollback_drill` bỏ `resolve_smc_scoring_policy`/`legacy_is_metadata_only`; chỉ còn kill-switch check (không còn v1 để restore).
- `core/smc_validation.py` — `replay_smc_cases` dùng `score_smc` + `_legacy_side_snapshots` (thay `build_smc_phase0_diagnostics`/`SMC_MODE_SHADOW`).

**Tests cập nhật/xóa:**

- `test_smc_scoring_phase0.py`: xóa 4 test router; sửa settings test dùng literal "legacy"/"shadow"; sửa mode test dùng literal.
- `test_smc_scorer_v2.py`: xóa 2 test router (`test_shadow_contract_runs_v2...`, `test_active_v2_contract_promotes_shadow...`).
- `test_smc_prefilter.py`: `test_prefilter_preserves_context_and_reuses_canonical_result` (so sánh với `score_smc`).
- `test_smc_phase8_rollout.py`: rollback drill test bỏ `legacy_is_metadata_only`.

**Kiểm tra theo plan:** `rg -n "smc_scoring_contract|SMC_MODE_" core controllers services config ui scripts workers tests` → **không còn** (chỉ còn strings trong `test_smc_scoring_result.py` — forbidden-key test, không phải import). `rg "from core.smc_scoring_contract"` → không còn.

| Chỉ số | Giá trị |
|---|---|
| Migration-relevant suite | 138 passed (sau fix) |
| Full `python -m pytest -q` | 2222 passed, 8 skipped, 17 xfailed |

**Kết luận:** Không còn router chọn v1/shadow trong runtime. Điều kiện hoàn thành Bước 12 đạt.
