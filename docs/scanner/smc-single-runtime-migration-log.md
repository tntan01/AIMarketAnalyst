# Log triển khai — SMC single runtime migration

> **⚠️ Tài liệu lịch sử (migration log).** Ghi lại các bước đã thực hiện để
> đưa SMC về một runtime duy nhất. Không phải runtime contract hiện hành;
> các tham chiếu SMC v1/v2/shadow trong file này mô tả trạng thái trước khi
> migration hoàn tất.

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

**Re-run xác nhận (2026-08-02, sau Bước 12 — commit `eac0c07`):**

| Chỉ số | Giá trị |
|---|---|
| Pass | 91 |
| Fail | 0 |
| Thời gian | 2.25s (lần chạy đầu 4.85s) |
| Warning | 0 |

Chênh lệch 91 vs 98 do suite đã đổi trong các bước 02–12 (test chuyển sang API canonical, xóa test router shadow). Baseline XANH — mọi lỗi có sẵn: không có.

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

## Bước 13 — Xóa scorer v1 và override path

**File chính:**

- `core/signal_engine.py` — xóa hoàn toàn:
  - `score_scenario()` (wrapper v1 gọi `smc_quality_score`; không còn caller runtime sau Bước 08 — bắt buộc xóa cùng v1).
  - `apply_smc_score_override()` (override path đã được `compose_scenario_score` thay thế từ Bước 07/08).
  - `smc_quality_score()` — thuật toán chấm điểm v1.
  - `_best_smc_zone()` — zone selector chỉ phục vụ scorer v1.
  - Import `extract_smc_trade_flags` (chỉ còn `score_scenario` dùng trong file; runtime vẫn dùng ở `analysis_pipeline.py`).
  - Docstring `calculate_direction_bias` trỏ `score_scenario` → `compose_scenario_score`.

**Tests xử lý (hệ quả bắt buộc — import/call v1 vỡ nếu không sửa):**

- `tests/test_signal_engine.py` — 2 test dùng `score_scenario` chuyển sang `compose_scenario_score` với `smc_quality` characterization cố định (plain buy=15, choch buy=4) + `extract_smc_trade_flags`; 1 test xfail strict giữ nguyên trạng thái xfail.
- `tests/test_macro_scoring_contract.py` — thêm wrapper `_scenario()` (compose + `_SMC_BUY_QUALITY_V1={"buy":15,"sell":0}` characterization) thay toàn bộ 23 call `score_scenario`; docstrings cập nhật tên hàm.
- `tests/test_smc_composition.py` — xóa `test_score_scenario_matches_composition_with_v1_quality`; `test_composition_does_not_call_smc_quality_score` → guard test `test_signal_engine_has_no_v1_scorer` (khẳng định module không còn 3 symbol v1).
- `tests/test_smc_scoring_phase0.py` — bỏ import `smc_quality_score`, helper `_active_scores` và `test_replay_fixture_locks_legacy_scores` (test khóa legacy score bằng scorer v1 — retire; Bước 28 sẽ thay bằng canonical golden fixture); bỏ import `SMC_RAW_ZONE_VERSION` không còn dùng.
- `tests/test_zone_score_single_source.py` — **retire** (xóa file): test khóa behavior v1 "đọc zone_score trực tiếp, không rescore internal" — behavior không tồn tại trong `evaluate_smc_zones` canonical (zone score tính từ components, không đọc `zone_score` từ dict).

**Xác minh theo plan:**

- `rg -n "smc_quality_score|apply_smc_score_override|_best_smc_zone" core controllers services` → **không có kết quả** (exit 1).
- `rg` toàn repo (ngoài docs): chỉ còn tên test functions, guard test và forbidden-key list — không còn import/call v1.

| Chỉ số | Giá trị |
|---|---|
| Golden + signal engine + macro + composition + phase0 | 77 passed, 2 xfailed |
| Full `python -m pytest -q` | 2217 passed, 8 skipped, 17 xfailed, 4 warnings (58.20s) |

Warnings (4, đều có sẵn từ trước, ngoài phạm vi): `PytestCollectionWarning` `TestHarness` (test_ai_eval_worker) + 3× `PytestReturnNotNoneWarning` (test_ai_eval_worker, test_lot_calculation, test_sse_parser).

**Kết luận:** Source runtime không còn chứa thuật toán chấm điểm v1; không còn đường gọi `smc_quality_score`/`apply_smc_score_override`/`_best_smc_zone`. Điều kiện hoàn thành Bước 13 đạt.

## Bước 14 — Một nguồn selected zone duy nhất

**File chính:**

- `core/smc_context.py`:
  - **Tách** `extract_smc_trade_flags()`: chỉ còn structural flags (`choch_against_direction`, `liquidity_sweep_aligned`, `displacement_aligned`, `raw`). Bỏ toàn bộ phần tự chọn zone (`has_selected_zone`/`selected_zone_*`) vốn được chọn qua `_find_best_zone_for_direction` — dead code vì `_merge_active_smc_flags` (analysis_pipeline) đã ghi đè selected zone từ consumer canonical. `zone_broken` cũng bỏ (selector legacy đã lọc zone broken nên nó luôn False; nguồn chính xác là consumer).
  - **Xóa** `_find_best_zone_for_direction()` + `get_preferred_zone()` (không còn caller runtime; `get_preferred_zone` chỉ còn tests) cùng 2 hằng `_EFFECTIVE_ZONE_PREFERRED_MIN_SCORE`/`_EFFECTIVE_ZONE_HIGH_TEST_COUNT` và import `isfinite`/`SelectedSmcZone` chỉ chúng dùng.
  - Giữ `calculate_effective_zone_score`/`zone_matches_direction` (Bước 24 sẽ quyết định số phận).
- `core/trade_gate_engine.py` — `_gate_zone_relevance` fail-closed: zone canonical (`zone_scoring_version="smc-v2"`) thiếu `zone_relevance_score` → WATCH_ONLY + `ZONE_RELEVANCE_LOW` + reason thay vì bỏ qua; zone legacy (`smc-v1`/không version) vẫn là historical, bỏ qua.
- `core/risk_engine.py` — comment line 719 tham chiếu `get_preferred_zone` đã xóa → "canonical selected zone from the SMC result/consumer". Branch `watch_only_fallback` (line ~1176) giữ nguyên: chỉ kích hoạt với field từ selector đã xóa, consumer zone không có field này → dead-safe.

**Tests xử lý:**

- `tests/test_effective_zone_selection.py` — **retire** (7 test khóa `get_preferred_zone`).
- `tests/test_effective_zone_score.py` — xóa `test_effective_selection_replaces_raw_selection_in_phase_16c` (dùng get_preferred_zone); giữ 10 test `calculate_effective_zone_score`/diagnostics/gate.
- `tests/test_source_zone_diagnostics.py` — xóa `test_preferred_zone_preserves_source_metadata`.
- `tests/test_smc_domain_models.py` — `test_enriched_zone_identity_reaches_selection_flags_and_risk_adapter` → `..._structural_flags_and_risk_adapter`: bỏ get_preferred_zone, assert `"selected_zone_id" not in flags` (khóa tách), giữ structural flags + `_smc_zones_to_levels` adapter.
- `tests/test_smc_sweep_linking.py` — bỏ get_preferred_zone; assert `"selected_zone_linked_sweep_id" not in flags`, giữ level adapter.
- `tests/test_trade_gate_engine.py` — thêm `TestZoneRelevanceFailClosed` (3 test): canonical thiếu relevance → WATCH_ONLY; legacy thiếu relevance → không cap; relevance thấp (35) → WATCH_ONLY.

**Xác minh:**

- `rg "get_preferred_zone|_find_best_zone_for_direction"` (ngoài docs) → không có kết quả.
- Selected zone cho quyết định giao dịch chỉ từ SMC result/consumer: pipeline vốn đã truyền `preferred_zones` từ `selected_zone_for_side()` (canonical) vào `build_trade_plan`; golden test khóa selected zone ID/type/timeframe cho BUY/SELL/no-zone/broken/stale.

| Chỉ số | Giá trị |
|---|---|
| Targeted (golden + domain + sweep + effective + diagnostics + gate + pipeline + composition + signal + macro + prefilter) | 152 passed, 2 xfailed |
| Full `python -m pytest -q` | 2211 passed, 8 skipped, 17 xfailed, 4 warnings (60.12s) |

Chênh lệch -6 vs Bước 13: -7 (selection retired) -1 (effective_score) -1 (source_zone_diagnostics) +3 (trade gate fail-closed) = khớp.

**Kết luận:** Chỉ scorer canonical có quyền chọn zone cho quyết định giao dịch; structural flags giữ CHOCH/displacement/sweep; trade gate fail-closed khi zone canonical thiếu relevance. Điều kiện hoàn thành Bước 14 đạt.

## Bước 15 — Xóa setting SMC mode

**File:**

- `config/settings.py` — xóa `FeatureFlagSettings.smc_scoring_mode`.
- `services/settings_service.py` — `_load_feature_flags` bỏ parser `legacy/shadow/v2` (kể cả fallback invalid → legacy) và field; settings JSON cũ có key này tự nhiên bị bỏ qua; `asdict()` khi save không còn field → key cũ không ghi lại. Không thêm env variable.
- `ui/screens/settings_screen.py` — sửa tối thiểu để không vỡ UI (ripple bắt buộc): bỏ 3 dòng ghi `features.smc_scoring_mode` khi save rollout; label bỏ chữ "và SMC mode". Widget combo `smc_mode` vẫn hiện đến Bước 16 (đọc bằng `getattr` an toàn, không crash).

**Tests:**

- `tests/test_smc_scoring_phase0.py` — `test_smc_mode_settings_default_load_and_round_trip` → `test_smc_scoring_mode_setting_is_gone_and_old_keys_ignored`: load JSON cũ với `legacy`/`shadow`/`v2`/`invalid`/`""` đều không còn field; round-trip save → `smc_scoring_mode` không xuất hiện trong file; bỏ import `FeatureFlagSettings` không còn dùng.
- `tests/test_backtest_simplification_phase5.py` — assert `settings.features.smc_scoring_mode == "v2"` → `not hasattr(settings.features, "smc_scoring_mode")`.

**Xác minh:** `rg "features.smc_scoring_mode" core controllers services config ui workers scripts` → không có kết quả (chỉ còn `getattr(..., "smc_scoring_mode", "v2")` ở scanner_screen — Bước 16 xóa hẳn).

| Chỉ số | Giá trị |
|---|---|
| Targeted (phase0 + backtest_simplification + scanner_phase0_settings + backtest_config_validation + golden) | 44 passed |
| Full `python -m pytest -q` | 2211 passed, 8 skipped, 17 xfailed, 4 warnings (57.19s) |

**Kết luận:** Không có config path nào kích hoạt scorer khác — settings cũ bị bỏ qua, save không tái ghi key. Điều kiện hoàn thành Bước 15 đạt.

## Bước 16 — Xóa SMC mode khỏi UI

**File:**

- `ui/screens/settings_screen.py`:
  - Xóa widget combo `smc_mode` ("legacy"/"shadow"/"v2") + tooltip (1341-1356 cũ).
  - Xóa `self.rollout_smc_mode_input = smc_mode` và row `"SMC scoring mode"`.
  - Đổi label `shadow_compare` từ "Ghi so sánh V1/V2" → **"So sánh Scanner V1/V2"** (phân biệt subsystem: Scanner Candidate Engine comparison, không phải SMC).
  - Giữ nguyên: rollout stage combo (DISABLED/SHADOW/DEMO_LIMITED/DEMO_FULL/CANARY/PRODUCTION), kill switch, allowed_symbols, canary risk, min_shadow/demo/canary, disagreement/revalidation/degradation.
- `ui/screens/scanner_screen.py` — bỏ `smc_scoring_mode=...` khỏi `ScannerRequest(...)` (param vẫn còn default trong ScannerRequest đến Bước 17).

**Xác minh:**

- `rg "smc_scoring_mode|smc_mode|rollout_smc_mode_input|SMC scoring mode" ui` → không có kết quả.
- Import cả 2 module UI: OK.
- UI tests: 27 passed (layout + density + improvements).
- Không có screenshot baseline tự động trong repo; mở Settings không còn control SMC mode — rollout stage + generic comparison vẫn hiện (giữ nguyên code path).

| Chỉ số | Giá trị |
|---|---|
| UI tests | 27 passed |
| Full `python -m pytest -q` | 2211 passed, 8 skipped, 17 xfailed, 4 warnings (57.73s) |

**Kết luận:** Không còn control SMC v1/v2/shadow trên UI; Scanner rollout controls giữ nguyên. Điều kiện hoàn thành Bước 16 đạt.

## Bước 17 — Xóa mode khỏi Scanner call chain

**Runtime (signature không còn khái niệm lựa chọn scorer):**

- `core/scanner.py` — xóa `smc_scoring_mode` khỏi `ScannerRequest`; xóa 3 output mappings (`smc_scoring_mode` trong row, fallback row, summary) — giữ `smc_scorer_version` trong provenance/output cho audit.
- `core/analysis_engine.py` — xóa param `smc_scoring_mode` khỏi `analyze_symbol()` + propagation vào pipeline.
- `core/analysis_pipeline.py` — xóa param khỏi `AnalysisPipeline.execute()` + field `self._smc_scoring_mode`.
- `controllers/scanner_controller.py` — xóa: `"smc_scoring_mode"` khỏi SCAN_STARTED telemetry payload (dòng 413), khỏi `analyze_kwargs` (dòng 719, truyền `request.smc_scoring_mode`), khỏi 2 helper `_scan_one_symbol`/`_analyze_one_symbol` (param + dòng truyền vào `analyze_symbol`).
- `core/system_backtest_engine.py` — ripple bắt buộc: bỏ `smc_scoring_mode=request.smc_scoring_mode` khi gọi `analyze_symbol` (Bước 22 sẽ xóa field khỏi `BacktestRequest`).
- `scripts/compare_scanner_fast_path.py` (2 call), `scripts/tier2_feasibility_gate.py` (1 call) — ripple bắt buộc: bỏ param khỏi `analyze_symbol` (Bước 27 dọn vòng lặp mode trong script).

**Tests (ripple bắt buộc — call `analyze_symbol`/đọc `ScannerRequest` field):**

- `test_smc_canonical_golden.py` — bỏ `smc_scoring_mode="v2"` ở 2 helpers (full + tier1).
- `test_smc_scoring_phase0.py` — `test_default_scan_contract_uses_active_v2_version`: bỏ assert `request.smc_scoring_mode`/`output["smc_scoring_mode"]`, thêm assert `not hasattr`/key không tồn tại; `test_smc_modes_all_route_to_single_canonical_scorer` → `test_analysis_outputs_single_canonical_scorer` (2 lần chạy cùng input → cùng output; diagnostics canonical không policy/shadow/active/comparison).
- `test_scanner_fast_path.py` (2 helpers), `test_scanner_fast_path_baseline.py` (1 helper) — bỏ param.

**Xác minh:** `rg "smc_scoring_mode"` trong `core/scanner.py analysis_engine.py analysis_pipeline.py controllers/scanner_controller.py workers` → không có kết quả. Còn lại đúng theo plan: `core/scanner_observability.py` (Bước 18), `core/system_backtest_engine.py` (Bước 22), `services/journal_*` (Bước 25), scripts (Bước 27) — chưa đụng.

| Chỉ số | Giá trị |
|---|---|
| Targeted (golden + phase0 + fast_path ×2 + pipeline_integration + phase8_rollout + backtest point-in-time/parity/replay) | 111 passed |
| Full `python -m pytest -q` | 2211 passed, 8 skipped, 17 xfailed, 4 warnings (53.71s) |

**Kết luận:** Không còn mode trong Scanner API hoặc call chain; `smc_scorer_version` giữ trong provenance. Điều kiện hoàn thành Bước 17 đạt.

## Bước 18 — Đơn giản hóa observability + provenance

**File:**

- `core/scoring_provenance.py` — xóa `"smc_scoring_mode": "v2"` và `"smc_decision_source": SMC_SCORER_VERSION` khỏi `build_scoring_provenance()`. Provenance giờ chỉ còn: `provenance_version` (contract), `score_metric`, `scanner_scorer_version`, `scanner_feature_version`, `smc_scorer_version`, `smc_domain_version` — một scorer version + contract version, không còn mode/decision source. `normalize_scoring_provenance` tự bỏ key lạ (fallback keys) → reader chịu được event lịch sử có field cũ.
- `core/scanner_observability.py` — xóa field `smc_scoring_mode` khỏi `ScannerScanContext` + `create_scan_context`; xóa 3 chỗ ghi `"smc_scoring_mode"` trong `attach_row_observability` (observability payload, row update, candidate order payload). Giữ `smc_scorer_version` + `smc_domain_version`.

**Ripple bắt buộc (consumer đọc key đã xóa):**

- `core/system_backtest_engine.py` — bỏ `smc_scoring_mode` khỏi `scoring_contract` (dòng 327) và khỏi `BacktestResult` init (dòng 1805); field `BacktestResult.smc_scoring_mode` còn đến Bước 22.
- `tests/test_smc_phase8_rollout.py` — assert provenance: `smc_scoring_mode`/`smc_decision_source` → `not in provenance`; scoring_contract: `"smc_scoring_mode" not in ...`; journal: `loaded.smc_scoring_mode is None` (không còn nguồn ghi — Bước 25 tiếp).

**Test mới:** `test_scanner_observability.py::test_new_telemetry_has_no_smc_mode_or_decision_source_keys` — provenance/context/observability/order payload không chứa 2 key; request cũ truyền `smc_scoring_mode="legacy"` vào `create_scan_context` vẫn chạy và context vẫn `smc_scorer_version=="smc-v2"` (historical tolerance).

**Xác minh:** `rg "smc_scoring_mode|smc_decision_source" core/scanner_observability.py core/scoring_provenance.py` → không có kết quả.

| Chỉ số | Giá trị |
|---|---|
| Targeted (observability + phase8_rollout + persistence_aftercare + backtest point-in-time + golden + phase0) | 78 passed |
| Full `python -m pytest -q` | 2212 passed, 8 skipped, 17 xfailed, 4 warnings (53.80s) |

**Kết luận:** Telemetry mới chỉ có SMC canonical provenance; không ghi mode/decision source; reader chịu được event lịch sử. Điều kiện hoàn thành Bước 18 đạt.

## Bước 19 — Xóa SMC shadow event

**File:** `controllers/scanner_controller.py`.

**Xóa:**

- `_compact_smc_shadow_payload()` — builder payload comparison (policy/shadow_status/comparison/active/shadow/consumer_contract) + schema `smc-shadow-summary-v1`.
- Helper chỉ phục vụ event này: `_compact_event_value()`, `_compact_smc_side()`, `_compact_smc_side_metrics()` + hằng `_SMC_EVENT_TEXT_LIMIT`/`_SMC_EVENT_SIDE_FIELDS` (kiểm tra caller trước khi xóa — chỉ dùng trong 4 hàm trên).
- Emit path `SMC_SHADOW_COMPARISON` trong `_emit_candidate_events` (block đọc `smc_policy.shadow_enabled`/`comparison` — field không còn trong `smc_scoring` nên block đã chết).

**Tests:**

- `test_scanner_observability.py` — xóa `test_smc_shadow_event_payload_is_compact_and_omits_full_zone_data` (khóa event đã xóa); rotation test đổi event_type placeholder `SMC_SHADOW_COMPARISON` → `SCAN_STARTED` (tránh quảng bá tên cấm).
- Giữ guard `test_scanner_phase8_rollout.py:700` (`"SMC_SHADOW_COMPARISON" not in event_types`) — đúng yêu cầu plan: test scan không phát sinh event; generic `SHADOW_DECISION_COMPARISON` vẫn phát khi bật (test_scanner_observability giữ).

**Xác minh:** `rg "SMC_SHADOW_COMPARISON|_compact_smc_shadow_payload|smc-shadow-summary" controllers core services` → chỉ còn guard test `not in event_types`.

| Chỉ số | Giá trị |
|---|---|
| Targeted (observability + phase8_rollout ×2 + persistence_aftercare) | 72 passed |
| Full `python -m pytest -q` | 2211 passed, 8 skipped, 17 xfailed, 4 warnings (54.60s) |

**Kết luận:** Không còn SMC comparison event trong code runtime; generic Scanner shadow vẫn hoạt động. Điều kiện hoàn thành Bước 19 đạt.

## Bước 21 — Cập nhật rollback drill

**File:**

- `core/scanner_rollout.py` — `run_rollback_drill()`:
  - Kiểm tra "rollback SMC về legacy/v1" đã được xóa từ Bước 06/12 (chỉ còn kill-switch check).
  - Thêm check **`shadow_stage_blocks_order`**: policy `stage=SHADOW`, `kill_switch=False` → `order_decision.allowed is False` + reason `SHADOW_MODE_ORDER_SUPPRESSED`.
  - Giữ check `kill_switch_blocks_order` (`ROLLOUT_KILL_SWITCH_ACTIVE`).
  - Output thêm `shadow_order_decision` (bằng chứng SHADOW chặn order).
- `scripts/run_scanner_rollback_drill.py` — không đổi logic (đã gọi `perform_rollback_drill()`); chạy thực tế exit 0, không import scorer v1 (chỉ import `ScannerRolloutMetricsService`).

**Tests:** `test_smc_phase8_rollout.py::test_rollback_drill_blocks_orders_and_drops_v1_rollback` — thêm assert `shadow_stage_blocks_order is True` + `"v1" not in json.dumps(checks)`; thêm import json.

**Ghi chú vận hành (mục 4 plan — runbook deployment trỏ artifact phát hành trước):** repo không có runbook deployment Scanner riêng; hướng dẫn nằm ở Bước 33/34 của plan ("Lưu artifact/build hiện tại để deployment rollback", "Redeploy artifact phát hành trước"). Không tạo file runbook mới trong bước này.

**Xác minh:** `python scripts/run_scanner_rollback_drill.py` → `passed: true` (cả 2 checks), exit 0, không import `smc_quality_score`/scorer v1.

| Chỉ số | Giá trị |
|---|---|
| Targeted (phase8_rollout ×2) | 34 passed |
| Full `python -m pytest -q` | 2211 passed, 8 skipped, 17 xfailed, 4 warnings (57.23s) |

**Kết luận:** Rollback vận hành đầy đủ với SMC canonical: kill switch và Scanner SHADOW stage đều chặn order; không còn kiểm tra rollback về v1. Điều kiện hoàn thành Bước 21 đạt.

## Bước 22 — Xóa mode khỏi Backtest runtime

**File:** `core/system_backtest_engine.py` (+ ripple đã xử lý từ Bước 17/18).

**Thay đổi:**

- Xóa `BacktestRequest.smc_scoring_mode` (field default "v2") — request không còn mode.
- Xóa `BacktestTrade.smc_scoring_mode` — kết quả trade mới chỉ ghi `smc_scorer_version` (canonical).
- Propagation vào `analyze_symbol()` đã bỏ từ Bước 17 (dòng `smc_scoring_mode=request.smc_scoring_mode`); đọc provenance mode đã bỏ từ Bước 18 (scoring_contract + BacktestTrade init).

**Fail-closed scorer error (mục 4):** pipeline đã fail-closed từ Bước 10 — scorer exception → structural reject với `SMC_SCORING_ERROR` → scenario `stand_aside`/`entry_status=no_setup`, `trade_permission.status=blocked` → backtest funnel không tạo trade. Thêm test khóa: `test_backtest_execution_parity.py::test_backtest_blocks_trade_on_scorer_error_analysis` — `simulate_trade_from_analysis` với analysis blocked shape → `None`.

**Xác minh:** `rg "smc_scoring_mode" core/system_backtest_engine.py controllers/backtest_controller.py scripts/run_baseline_validation.py core/param_sensitivity.py` → không có kết quả. Backtest/live parity trên golden corpus: full suite backtest + golden pass.

| Chỉ số | Giá trị |
|---|---|
| Targeted (parity + point-in-time + candidate_replay + execution_sequence + simulation_diagnostics + phase8_rollout + config_validation + run_baseline_validation) | 120 passed |
| Full `python -m pytest -q` | 2212 passed, 8 skipped, 17 xfailed, 4 warnings (60.49s) |

**Kết luận:** Không thể chạy backtest bằng v1 hoặc shadow — request không mode, trade chỉ ghi scorer version canonical, scorer error fail-closed. Điều kiện hoàn thành Bước 22 đạt.

## Bước 24 — Dọn domain model + producer legacy

**File:** `core/smc_models.py`, `core/smc_context.py`, `core/smc_confluence.py`, `core/risk_engine.py`.

**Mục 4 — Xóa legacy lifecycle fields (hoàn thành):**
- `SmcZone`: xóa 5 fields `legacy_test_count/legacy_mitigated/legacy_stale/legacy_broken/legacy_liquidity_sweep` + parse khỏi `from_dict` + compat keys trong `to_dict` giờ lấy từ canonical (`test_count←independent_retest_count`, `mitigated←lifecycle_mitigated`, `stale←stale`, `broken←broken`, `liquidity_sweep←liquidity_sweep_linked`).
- Xóa property `SmcZone.zone_score` ("Compatibility alias used by the legacy scorer" — scorer v1 đã xóa Bước 13); `to_dict` dùng `zone_setup_score`.
- `enrich_zones`: bỏ `legacy_*` keys khỏi record; đổi tên biến local legacy_* → trung tính (test_count/broken/mitigated/stale/liquidity_sweep).
- `risk_engine.py` (~1425): bỏ đọc `legacy_liquidity_sweep` (giữ `liquidity_sweep` + `liquidity_sweep_linked`).

**Mục 5 — Xóa scalar confluence v1 (hoàn thành):**
- `DirectionalConfluence.legacy_score` field + `confluence_score` compat key trong `to_dict` + parse — xóa.
- `build_directional_confluence()` bỏ param `legacy_score`.
- `_cross_validate_structure()` (producer scalar confluence) — không còn caller → xóa.
- `build_smc_context` không còn bọc adapter; `confluence = directional_confluence.to_dict()`.

**Mục 6 — `zone_quality_score()` (giữ, có điều kiện):** vẫn còn caller runtime `enrich_zones` (gắn `zone_score/zone_quality_score/zone_setup_score` cho consumer dict — risk_engine/trade plan/UI đọc trực tiếp) + `scripts/backfill_zone_metadata.py` (Bước 27 xử lý). Điều kiện "nếu không còn caller" không thỏa → giữ, ghi chú PO.

**Mục 7 — `calculate_effective_zone_score()` (giữ):** xác nhận là diagnostic/risk signal độc lập (dùng ở `build_source_zone_diagnostics` + test_effective_zone_score), không phải scorer v1 trá hình.

**Mục 8 — Parser trung tính + xóa public legacy adapter (hoàn thành):**
- `SmcZone.from_legacy_dict` → `SmcZone.from_dict`; `DirectionalConfluence.from_legacy_dict` → `from_dict`; `SmcScoreBreakdown.from_legacy_score` → `from_score`. Parser vẫn đọc dict cũ (key lạ bị bỏ qua — historical tolerance).
- Xóa `adapt_legacy_zone_payload` + `adapt_legacy_confluence_payload`; chuyển callers: `smc_context` (enrich_zones dùng `from_dict(...).to_dict()` không cần — item đã đủ keys), `smc_scorer.py` (`from_dict`).

**Mục 1-3 (tách raw/evaluated — giới hạn đã ghi nhận):** raw/evaluated đã phân lớp qua `EvaluatedSmcZone` wrapper (smc_scorer) + `SelectedSmcZone` canonical; evaluated scores chỉ từ `score_smc()`. `SmcZone` giữ score fields vì consumer dict (risk_engine/trade plan/UI) đọc zone scores trực tiếp — không tách field trong bước này (tránh phá trade plan/UI); `scoring_version` mặc định `SMC_RAW_ZONE_VERSION` là identity raw zone, không thể route scorer (Bước 06 đã khóa). Ghi chú PO nếu cần tách sâu hơn.

**Tests:** sửa `test_smc_domain_models` (adapter → from_dict/to_dict, legacy_score/legacy_score asserts → not hasattr/not in), `test_smc_zone_lifecycle` (legacy fields → not hasattr), `test_smc_sweep_linking` (legacy_liquidity_sweep → not in/not hasattr; from_dict), `test_smc_directional_confluence` (bỏ legacy_score/confluence_score asserts; bỏ import `_cross_validate_structure`), `test_smc_scorer_v2` (from_dict).

| Chỉ số | Giá trị |
|---|---|
| Targeted (domain + lifecycle + sweep + confluence + scorer + golden + phase0 + effective + diagnostics + pipeline) | 91 passed |
| Full `python -m pytest -q` | 2212 passed, 8 skipped, 17 xfailed, 4 warnings (61.88s) |

**Kết luận:** Record mới không còn legacy_* lifecycle fields và scalar confluence v1; parser trung tính `from_dict`; public legacy adapters đã xóa; `zone_quality_score` giữ vì còn caller runtime. Điều kiện hoàn thành Bước 24 đạt (với ghi chú mục 1-3/6 nêu trên).
