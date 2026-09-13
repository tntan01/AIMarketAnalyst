# Gate72 F01 acceptance matrix — Checkpoint A lần4

**HIỆN HÀNH — TASK72 APPROVED / D PASS (2026-09-12).** R72-01…09 CLOSED theo response mục0 và fix-progress §A3.157; acceptance129P, probes16P, full983P. Các bảng/ô RED checkpoint A và trạng thái C trước là lịch sử. Không rollout canonical production; task73 chưa thực hiện.

> **TRẠNG THÁI HIỆN HÀNH (2026-09-12, snapshot trình D): toàn bộ acceptance 129/129 PASS và 16/16 reviewer probes PASS.** Các **bảng case-level bên dưới là ảnh chụp lịch sử tại checkpoint A** (expected đã duyệt + Actual/RED **lúc đó**): mọi ô ghi `RED — implementation` trong các bảng đó **không** còn là trạng thái hiện tại. Chuyển trạng thái thật của từng cụm nằm ở các khối **“Refresh …”** ngay dưới tiêu đề mỗi mục R72-0X; các khối này giữ nguyên văn cũ (lịch sử) và bổ sung kết quả mới nhất. Bản trình cuối: [smc-task-72-response.md](smc-task-72-response.md).

**Hiện hành — F11 xong, D `WAITING_REVIEW`, TL 2026-09-12.** F11 đồng bộ Actual/inventory hiện hành + mapping end-to-end và thêm 1 node chuỗi (a): acceptance **129P/0F**, probes **16P/0F**, task57–71 108P, retained 854P, full §5 **983P/0F**; Δcollection đúng +1, không mất/đổi tên node cũ. C PASS trước đó (§A3.155): C-R1/C-R2 đạt, G1/G2 theo §A3.153, A/B giữ PASS. Chưa CLOSED 9 finding / APPROVED gate72 / task73. Kết quả cũ giữ làm lịch sử.

**TL C lần2 — §A3.153:** full981P, C-R2/same-pool đạt; canonical caller thiếu reclaimed_at vẫn phải fail closed, không điền time thay thế. Bổ sung vế missing-time tại caller C-R1. G1: min child availability theo setup được TL chấp nhận ở adapter; G2: claim time trước class, setup ưu tiên chỉ khi hòa mixed-class. Giữ A/B PASS, chưa F11.

**C review — CHANGES_REQUESTED, §A3.151 (2026-09-12):** thêm regression cho same-pool observation qua caller thật và conflicting same-pool histories dưới permutation. Tests hiện có xanh chưa bao phủ hai diagnostic này; giữ A/B PASS, chưa F11/task73.

**TL §A3.146:** public `_smc_for_timeframe` vẫn là legacy theo gate40; phải chọn compatibility route tường minh, không coi canonical records rỗng/lỗi là legacy. F07/r1 thêm regression public caller và giữ R72-01 canonical xanh trước F08; không tự migrate swing_points hoặc thay policy pool-selection.

**TL 2026-09-11 — usable_at của swing producer (§A3.143 fix-progress):** `_confirmed_swing_points` phát usable_at=confirmed_at cho confirmed/usable/non-provisional source, tại close nến xác nhận bên phải. Provisional/unusable không cấp mốc usable có hiệu lực. Không fallback ở pool/sweep cho payload thiếu field; đây không là luật chung cho mọi loại source. F06/r1 nối producer→pool trước F07; giữ quyết định A/B PASS.

**Quyết định hiện hành — B lần4 PASS, TL 2026-09-11 (§A3.141 fix-progress).** B-R1/B-R2 đạt trong phạm vi review; collection/mapping121/121, acceptance29F/92P. Coder chuyển F06; giữ A PASS và các quyết định interface đã duyệt. Các nhận xét B trước bên dưới là lịch sử.

**B lần3 — §A3.139:** 73 node r72_05…09 PASS; còn diagnostic B-R2/history chưa được regression hiện có bao phủ. Known-invalid + thiếu tick không được biến visit đã closed_by_invalidation thành reaction sau terminal; bổ sung vế này trong cùng lượt sửa B-R2. Giữ B-R1 và các ca terminal/timestamp đã đạt, chưa F06.

**Review B lần2 — §A3.137:** B-R1 đạt; B-R2 còn CHANGES_REQUESTED khi cửa sổ vượt lifetime. Collection hiện hành121 node; ba regression r72_05/r72_07 thuộc mapping acceptance, cần bổ sung ba hàng và cập nhật header trong cùng lượt sửa B-R2. Các inventory118 bên dưới là snapshot trước bổ sung regression, không phải collection hiện hành.

**B-R2/r1 (2026-09-11):** collection hiện hành **121 node / 79 hàm** — đã bổ sung **ba hàng mapping** cho `test_r72_05_zone_nonterminal_defaults_cannot_mask_active_lifecycle_terminal` (bảng R72-05 → **9 node**) và `test_r72_07_known_expired_is_preserved_when_metadata_is_missing` / `test_r72_07_known_invalid_is_preserved_when_metadata_is_missing` (bảng R72-07 → **21 node**). Inventory **118 node / 76 hàm** và số full `69 failed / 49 passed` bên dưới là **snapshot A lần4**, giữ làm lịch sử.

**Checkpoint B — TL 2026-09-11: CHANGES_REQUESTED**, xem fix-progress §A3.135. A vẫn PASS. GREEN của suite hiện có không bao phủ B-R1 (zone False che lifecycle terminal) và B-R2 (thiếu metadata dựng invalidation0 và ghi đè expired); bổ sung regression tối thiểu cho hai lỗi trong cùng lượt sửa B, không mở rộng audit.

**Status:** checkpoint A lần4 **PASS** — Tech Lead 2026-09-11, [fix-progress §A3.129](smc-task-72-fix-progress.md). Duyệt oracle/coverage F01, không duyệt implementation. Collection118/76; acceptance69 failed/49 passed.
**Quyết định hiện hành:** §A3.129 thay CHANGES_REQUESTED của A lần3; 5/5 nhóm A3R3 đã đáp ứng. Giữ các quyết định interface review A lần3 §3 và A-D01…A-D07. Mapping118/118. Hai node F06/F07 chưa cô lập không là bằng chứng temporal độc lập. Số liệu/nhận xét các lượt cũ bên dưới giữ lịch sử.
**Review reference:** [`smc-task-72-checkpoint-a-review.md`](smc-task-72-checkpoint-a-review.md)  
**Scope:** F01 oracle/coverage đã duyệt; coder được làm F02…F05 theo fix-plan rồi dừng trình B. Chưa F06/task73. Lượt review này không sửa core/tests/probe/R56.
Expected values below are written from the fix-plan, lifecycle spec, P7/P8,
BQLC and decisions A-D01…A-D07. They are not derived from production output.
`DONE` means the case is written and ran; `RED` means the expected contract
currently exposes an implementation gap; `PENDING` means a later owner
cluster must make it green.

**Lịch sử review A lần3:** năm nhóm oracle/coverage A3R3-01…05 đã xử lý và được chấp nhận tại A lần4 (§A3.129). Các nhận xét cũ bên dưới không thay quyết định hiện hành.

## A-D01…A-D07 decisions applied

| Decision | Locked rule used by cases |
|---|---|
| A-D01 | Closed-bar temporal gate is inclusive: `pool_usable_at <= sweep.reclaimed_at`; all required sources must be valid/confirmed. Before usable rejects; equal/after may pass only if excursion/reclaim also pass. |
| A-D02 | Canonical claim requires both `reclaimed_at` and `setup_available_at`; missing either fails closed. Owner ranks `max()` and ties by stable setup ID. |
| A-D03 | Historical owner with no current child keeps owner/assignment but current contribution is 0; never reassigns to a late setup. |
| A-D04 | Cutoff exactly equal to `invalidated_at` or `expired_at` is terminal for active D1 evidence; prior history remains. |
| A-D05 | Per candle order is availability/cutoff → invalidation/expiry gate → exit → reaction. A reaction before a later terminal candle stays in history; same terminal candle and later candles cannot create one. |
| A-D06 | Same causal pool identity remains the same across observation time, list order and rolling index. A genuinely new pool must carry new source IDs/lineage; metadata alone is insufficient. |
| A-D07 | Item-only, argument-only and equal-both tick sources have parity. Conflicting same-scope canonical sources are unknown/unavailable; missing ATR remains missing and never becomes threshold 0. |

## Fixture validity and R72-09 integration ledger

| Case ID | Fixture change | Expected |
|---|---|---|
| F01-T59 | task59 exit low `111.2` → `110.2` for close `110.2` | Valid OHLC; still outside high+tolerance, no displacement |
| F01-T60-BUY | lows `111.2/110.5/111.5` → `110.2/110.3/110.5` | Same exit, middle candles below threshold, third candle reacts |
| F01-T60-SELL | invalid rows → `(98,99.8,97.5,99.8)`, `(99,99.7,98,99.7)`, `(98,99.5,97,99.5)` | Valid below-zone exit and reaction at `99.5` |
| F01-T62-BUY | formation low `105` → `102` | Valid formation; post-formation partial/full output unchanged |
| F01-T63-SELL | wick-only low `109` → `104.5` | Wick may cross; close-not-wick invalidation unchanged |
| F01-T65-BUY | formation low `105` → `102` | Valid formation; partial/full identity and bounds unchanged |

The five positive factories call `validate_smc_candles`; intentional invalid
fixtures remain negative. The integration node below uses the real gate56
fixture, `detect_order_block_candidates`, `enrich_zones`, `SmcZone` round-trip,
`analyze_zone_lifecycle`, and `build_d1_reaction_evidence`. Its no-reaction
expected is explicit: a real detector chain with no completed reacted visit
must produce D1 `valid=False, score=0`; this does not claim R72-09 closed.

A3-057 adds the missing **confirmed D1 source**: a 37-bar D1 fixture whose
order-block candidate is promoted by `confirm_order_block_candidate` using the
bullish BOS produced by `replay_smc_structure` over the same bars, so both the
bounds and the confirming source come from the fixture (see
`test_r72_09_d1_source_is_confirmed_by_fixture_break`). The D1 lifecycle
integration on top of that source is A3-058…A3-062; R72-09 stays open until
those land. A3-058 then runs that same confirmed zone through `enrich_zones`
over five appended retest bars (`_D1_RETEST_ROWS`) and checks the lifecycle
timeline against the fixture's own bar closes; A3-059 then restores that zone
through `SmcZone` and re-checks identity/bounds/timeline against the same
fixture values. A3-060 then reads the D1 reaction off that canonical lifecycle
before any terminal (with a control showing legacy flags cannot substitute the
canonical visit). A3-061 then appends the invalidation bars: the earlier reaction
history must survive while the terminal makes the zone invalid/unusable and the
D1 consumer stops reading a reaction at that close. A3-062 grows the same chain
past the D1 lifetime for the expiry branch (expired/unusable, D1 invalid with
`D1_REACTION_STALE`). Both terminal branches now have nodes; only the
invalidation branch is still RED, so R72-09 stays open until its fix lands.

| Case-level node | Input / metadata / cutoff | Expected | Status |
|---|---|---|---|
| `test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid` | corrected T59/T60/T62/T63/T65 rows | validator returns no issue | DONE/GREEN |
| `test_r72_09_d1_source_is_confirmed_by_fixture_break` (A3-057) | D1 fixture `_D1_SOURCE_ROWS` (warm-up zigzag + base bar 32 + departure bar 33 + break bar 34); detector → `confirm_order_block_candidate` with the replay's own bullish BOS | candidate promoted to `confirmed`; `available_at` = close of the fixture break bar; break/source IDs = the fixture swing high and BOS event; bounds `[99.2, 100.2]` and identity preserved; input candidate not mutated | DONE/GREEN (confirmation path already correct; no lifecycle call yet) |
| `test_r72_09_d1_confirmed_zone_timeline_comes_from_fixture_retest` (A3-058) | the A3-057 confirmed zone (fixture `tick_size`/`atr_current`) → `enrich_zones` over `_D1_RETEST_ROWS` (append 5 retest bars) | `enrich_zones` lifecycle: 1 `completed_reacted` visit; `entered_at`/`exited_at`/`reacted_at` = closes of the fixture retest bars 38/40/41; not broken, not expired, not stale | DONE/GREEN (canonical lifecycle matches the fixture retest; no second lifecycle call with a locally assigned ATR) |
| `test_r72_09_d1_enriched_zone_survives_typed_restore` (A3-059) | the A3-058 enriched zone → `SmcZone.from_dict(enriched)` → `SmcZone.from_dict(typed.to_dict())` | identity/bounds/timeframe/lifecycle status and the full retest timeline survive both models, each field compared against the fixture bars (base bar bounds, closes of bars 34/38/40/41) rather than against the other serialization | DONE/GREEN (typed restore is lossless for this zone; the visit stays `completed_reacted`) |
| `test_r72_09_d1_reaction_positive_reads_canonical_lifecycle` (A3-060) | the A3-059 restored typed payload + the canonical `enrich_zones` lifecycle; `as_of` = close of the fixture's last bar | `valid=True`, `score=1.0`, `zone_id` matches, `source_visit_id` = canonical visit, `reacted_at` = close of bar 41, reason `D1_REACTION_COMPLETED_REACTED`; control with the canonical visit removed and legacy `d1_reaction`/`proximity` true is invalid with `D1_REACTION_NOT_COMPLETED_REACTED` | DONE/GREEN (D1 consumer reads the canonical visit; legacy flags cannot substitute it) |
| `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` (A3-061) | the A3-060 chain plus `_D1_INVALIDATION_ROWS` (bar 42 outside, bar 43 closes `98.6` = zone low − buffer); terminal close = close of bar 43 | earlier reaction history survives (`visit-1` `completed_reacted`), the breakdown bar opens `visit-2` `closed_by_invalidation`, and the pre-terminal cutoff is still valid; at the terminal close: `lifecycle_status == "invalid"`, `usable is False`, D1 `valid=False`/`score=0` and never `D1_REACTION_NOT_COMPLETED_REACTED` | **RED — implementation** (2026-09-11): precondition PASS (terminal timestamps from the fixture, history kept, pre-terminal control valid) but canonical status stays `confirmed` (R72-08), the `usable` key is absent, and the D1 consumer still reads `valid=True`/`1.0` at the terminal (F05 / A-D04) | F03/F05 |
| `test_r72_09_d1_expired_source_is_terminal_for_the_consumer` (A3-062) | the A3-060 chain plus `_D1_EXPIRY_ROWS` (14 bars outside the zone) so the zone age reaches the D1 lifetime at bar 55; expiry close = close of bar 55 | `expiry_index == 55`, `expired_at` from the fixture bar, `lifecycle_expired`/`lifecycle_stale` true with no invalidation and fixture metadata intact; the reacted visit survives; at the expiry close `lifecycle_status == "expired"`, `usable is False`, `ZONE_EXPIRED` present, D1 `valid=False`/`score=0` with `reason_codes == ["D1_REACTION_STALE"]` (never a missing reaction) | DONE/GREEN (the expiry branch was already correct end-to-end) | — |
| `test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture` → **A3-056 đổi tên** thành `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke` | real `smc_gate56_zone_pipeline` rows; detector→context→typed→lifecycle→D1 at last candle | real zone ID and original `[99,101]` survive; no reacted visit ⇒ D1 invalid/0 | DONE/GREEN (giữ nguyên hành vi; chỉ thu hẹp tên/phạm vi — ca này là **H1 candidate smoke**, bằng chứng confirmed D1 end-to-end là A3-057…A3-062) |
| `test_r72_09_existing_task60_positive_fixture_must_have_valid_ohlc` (**reviewer probe** — không nằm trong file acceptance) | task60 positive factory | validator returns no issue | DONE/GREEN |
| `test_r56_02_ob_requires_atr_ids_validity_and_causal_close_provenance` (existing) | real detector fixture and BUY/SELL mirror | candidate source/bounds valid and direction preserved | REFERENCED/DONE |
| `test_d1_reaction_requires_canonical_completed_reacted_visit` (existing) | canonical completed-reacted visit | D1 valid/positive before terminal | REFERENCED/DONE |

## R72 obligation cases

### R72-01 — pool/source-time

| Node ID | Case and expected | Status |
|---|---|---|
| `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[buy]`, `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[sell]` | source confirmed at hour6, sweep reclaimed hour3 ⇒ no event | RED |
| `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy]`, `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[sell]` | equal pool has two confirmed sources, usable time is max source time, source IDs preserved | RED: current numeric projection has no lineage |
| `test_r72_01_provisional_source_cannot_create_a_sweep` | provisional source ⇒ no sweep | DONE/GREEN |
| `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` | equal-source pool with all source confirmation at reclaimed close ⇒ inclusive temporal gate and source lineage | RED: current pool is numeric; A-D01 |

### R72-02 — all eligible claims before ownership

| Node ID | Case and expected | Status |
|---|---|---|
| `test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time` | early-far claim at13:00 beats late-near at15:00 | RED |
| `test_r72_02_same_time_tie_is_stable_under_claim_permutation` | same causal time chooses stable setup ID `early` under both input orders | DONE/GREEN |
| `test_r72_02_missing_canonical_claim_time_fails_closed` | missing `setup_available_at` with `reclaimed_at` present ⇒ no assignment and `SWEEP_CLAIM_TIME_MISSING` | RED |

### R72-03 — contribution only among owner children

| Node ID | Case and expected | Status |
|---|---|---|
| `test_r72_03_acceptance_contribution_is_selected_within_owner_children` | owner early plus non-owner child with smaller ID ⇒ exactly one owner contribution | RED |
| `test_r72_03_duplicate_owner_children_keep_one_contribution_under_permutation` | duplicate/permuted same-owner children ⇒ total exactly one | DONE/GREEN |
| `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | restored historical assignment, empty current child list ⇒ assignment retained, contribution 0 | RED: current caller does not project history without claims |

### R72-04 — consumed/replay/history

| Node ID | Case and expected | Status |
|---|---|---|
| `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` | context same dict twice ⇒ original owner/assignment unchanged | RED |
| `test_r72_04_assignment_survives_json_restore_with_late_only_window` | serialize/restore assignment, current window has only late child ⇒ original owner retained and late contribution false | DONE/GREEN |
| `test_r72_04_incomplete_history_returns_explicit_reason` | `history_complete=False`, no history ⇒ no assignment and `SWEEP_OWNER_HISTORY_INCOMPLETE` | DONE/GREEN |
| `test_r72_04_same_pool_observation_cannot_bypass_consumption` | same pool/source IDs with new observation time/index ⇒ original owner and no new contribution | DONE/GREEN; A-D06 |

### R72-05 — terminal D1 consumer

| Node ID | Case and expected | Status |
|---|---|---|
| `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[buy]`, `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[sell]` | typed lifecycle broken after reaction history ⇒ D1 invalid/0 | RED |
| `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[buy]`, `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[sell]` | serialized canonical `lifecycle_status=invalid` plus legacy reaction/proximity true ⇒ invalid/0 | RED |
| `test_control_live_d1_reaction_still_accepted` (reviewer) | canonical live completed reaction before terminal ⇒ valid | REFERENCED/DONE |
| `test_r72_05_cutoff_equal_invalidated_at_is_terminal` | `as_of == invalidated_at` ⇒ invalid/0, prior visit history retained | DONE/GREEN; A-D04 |

### R72-06 — terminal/reaction order

| Node ID | Case and expected | Status |
|---|---|---|
| `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[buy]`, `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[sell]` | prospective reaction at expiry candle ⇒ no reaction | RED |
| `test_r72_06_terminal_order_before_reaction_is_explicit[20-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[20-sell]` | reaction at age20, before age21 expiry ⇒ reacted history retained | DONE/GREEN |
| `test_r72_06_terminal_order_before_reaction_is_explicit[21-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[21-sell]`, `test_r72_06_terminal_order_before_reaction_is_explicit[22-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[22-sell]` | reaction at terminal or after terminal ⇒ no reaction; terminal state wins | RED |
| `test_r72_06_invalidation_precedes_expiry_and_reaction[buy]`, `test_r72_06_invalidation_precedes_expiry_and_reaction[sell]` | invalidation and prospective reaction conflict ⇒ invalidation, no reaction | DONE/GREEN |

### R72-07 — metadata source and unknown

| Node ID | Case and expected | Status |
|---|---|---|
| `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[buy]`, `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[sell]` | argument tick `.1`, item absent ⇒ buffer `.1`, not broken | RED |
| `test_r72_07_item_and_argument_tick_sources_have_parity[buy]`, `test_r72_07_item_and_argument_tick_sources_have_parity[sell]` | item-only/argument-only/equal-both `.1` ⇒ same buffer and broken state | RED |
| `test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero` (**tên lịch sử** — đã tách tại A3-016/A3-017 thành `test_r72_07_missing_canonical_atr_is_unknown_and_unusable`, `test_r72_07_missing_canonical_tick_is_unknown_and_unusable`, `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]`, `[tick_size]`) | missing ATR/nonfinite tick ⇒ unavailable/unknown, never zero threshold or usable | RED (nonfinite currently raises; missing remains confirmed/usable). **Đã tách ở A3-015/A3-016/A3-017**: missing ATR → `missing_canonical_atr_...`, missing tick → `missing_canonical_tick_...`, nonfinite → `nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current\|tick_size]` |
| `test_r72_07_conflicting_same_scope_tick_sources_fail_closed` | item `.2` vs argument `.1` ⇒ unknown/unusable | RED |
| `test_r72_07_equal_and_outside_buffer_buy_sell` | BUY/SELL closes at exact `.1` buffer remain live; beyond `.1` invalidates; same source scope parity | DONE/GREEN; A-D07 |

### R72-08 — canonical terminal projection

| Node ID | Case and expected | Status |
|---|---|---|
| `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[buy]`, `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[sell]` | context invalidation ⇒ status invalid, usable false | RED |
| `test_r72_08_invalid_canonical_zone_survives_typed_round_trip_consistently` | typed serialize/restore preserves invalid, broken and usable false | RED: model has no serialized `usable` field |
| `test_r72_08_canonical_invalid_status_wins_legacy_boolean[False]`, `test_r72_08_canonical_invalid_status_wins_legacy_boolean[True]` | canonical invalid wins both legacy boolean values; broken true | one RED/one GREEN; false case currently loses canonical state |
| `test_r72_08_typed_terminal_projection_reaches_d1_consumer[buy]`, `test_r72_08_typed_terminal_projection_reaches_d1_consumer[sell]` | restored canonical terminal zone cannot provide active D1 evidence | DONE/GREEN; A-D04 |

## Interface proposal for TL approval

These are proposals only; no API was added in F01.

> **Đã bị thay thế một phần (2026-09-11):** dòng `detect_liquidity_pools → detect_liquidity_sweeps`
> được thay bởi [Interface pool (A3-005)](#interface-pool--chốt-theo-review-a-lần2-a3-005); phần
> `history_complete` của dòng `_attach_zone_sweep_links → assign_sweep_ownership` được thay bởi
> [Interface history (A3-006)](#interface-history--chốt-theo-review-a-lần2-a3-006); phần còn lại của
> dòng đó cùng dòng `assignment → contribution projection` được thay bởi
> [Interface claim → assignment (A3-008)](#interface-claim--assignment--chốt-theo-review-a-lần2-a3-008);
> dòng `enrich_zones → lifecycle → context` được thay bởi
> [Interface metadata (A3-007)](#interface-metadata--chốt-theo-review-a-lần2-a3-007). Ba dòng dưới giữ
> nguyên làm lịch sử; đọc mục mới để lấy giá trị đang hiệu lực.

| Caller → owner | Proposed signature/fields | Propagation and boundary |
|---|---|---|
| `detect_liquidity_pools` → `detect_liquidity_sweeps` | `LiquidityPoolRecord(pool_id, kind, level, source_ids, sources[{swing_id, confirmed_at, usable_at, provisional}], observation_index)`; `detect_liquidity_sweeps(..., liquidity_pools, cutoff_at=None, causal_only=True)` | Canonical record is authority. Numeric `swing_lows/equal_lows` remains legacy projection only. Sweep accepts only all sources valid and `usable_at <= reclaimed_at` (A-D01). |
| `_attach_zone_sweep_links` → `assign_sweep_ownership` | `assign_sweep_ownership(claims, *, assignment_history=None, history_complete=False)`; canonical `SweepClaim(sweep_id, setup_id, zone_id, side, reclaimed_at, setup_available_at, pool_id, claim_source)` | Caller passes all eligible claims before ranking. Missing either claim timestamp emits `SWEEP_CLAIM_TIME_MISSING`; history conflict/incompleteness emits explicit reason and fails closed (A-D02/A-D06). |
| assignment → contribution projection | `SweepAssignment(owner_setup_id, assignment_id, claim_eligible_at, assigned_at, pool_id, source_ids)` plus current owner-child claims | Historical owner may survive with no current children; contribution is 0. Current owner children total 1 (A-D03). |
| `enrich_zones` → lifecycle → context | `ZoneLifecycle.metadata_state: available | unknown` and `metadata_reason`; `tick_size_source`, `atr_source`; context projects canonical `lifecycle_status`, `usable`, `broken`, `terminal_at`, `terminal_reason` | Canonical missing/nonfinite metadata is unknown/fail-closed. Legacy payload is adapted only at explicit boundary; item/argument equal values have parity, conflict is unknown (A-D07). |
| lifecycle → typed `SmcZone` → D1 | Typed/serialized fields proposed: `usable: bool`, `terminal_at`, `terminal_reason`, canonical `lifecycle_status`; retain visits and original bounds | Terminal status is authoritative over legacy flags. Cutoff equal terminal is inactive; history remains auditable (A-D04/A-D05). |
| pool identity across observations | `pool_id` derived from canonical source lineage (`kind + sorted source_ids + source causal records`), not level/list/index | Observation timestamp, input order or rolling index cannot mint a new ID. New source IDs/lineage are required for new pool (A-D06). |

## Actual F01 run ledger

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
49 tests collected

python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=short
30 failed, 19 passed in 0.81s; no skip/xfail

python -m pytest tests/test_smc_zone_lifecycle_task59.py tests/test_smc_zone_lifecycle_task60.py tests/test_smc_fvg_fill_task62.py tests/test_smc_zone_lifecycle_task63.py tests/test_smc_lifecycle_task65.py -q --tb=short
32 passed

python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=short
13 failed, 3 passed (R72-09 fixture probe GREEN)

python -m pytest @gate72Tests -q --tb=short
108 passed

retained SMC/scanner baseline excluding acceptance file: 854 passed
```

No production output was used as expected. Proposed/PENDING cases are named
explicitly rather than claimed as covered. **Checkpoint A lần 2 —
`WAITING_REVIEW`; TL must PASS or identify a matrix cell. Stop here.**

---

## Đối chiếu F01.1…F01.4 với code hiện tại — A3-003

Ghi ngày 2026-09-11 theo [fix-plan §8.3][§8]. **Chỉ đối chiếu và ghi nhận; không sửa `core/`,
test, fixture hay mục nào ở trên.** Trạng thái mỗi điểm: `ĐÚNG RỒI` (đã đạt, giữ nguyên) /
`MỘT PHẦN` / `CÒN THIẾU` / `CHƯA RÕ`. Trích theo **tên hàm**; số dòng chỉ để định vị và có thể
lệch nếu file được sửa tiếp.

### F01.1 — Representation và đồng bộ docs/tests

| Điểm | Kết quả | Bằng chứng (tên hàm / vị trí) | Mã A3 |
|---|---|---|---|
| Pool: numeric giữ legacy projection, canonical thêm `records` (`pool_id/kind/level/source_ids/sources/usable_at`); test lineage đọc `records`, không đòi `equal_lows[0]` vừa float vừa dict | **CÒN THIẾU** | `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time` vẫn `levels = pools["equal_lows"\|"equal_highs"]; isinstance(levels[0], dict); levels[0]["source_ids"] / ["usable_at"]`. `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` cùng dạng trên `pools["equal_lows"][0]`. Chưa có key `records`; M §Interface proposal mới nêu `LiquidityPoolRecord` dạng đề xuất, chưa ghi schema `records`. → **Cập nhật 2026-09-11 (A3-009/A3-010):** assertion lineage đã đọc `records` (node `positive_pool_keeps_source_lineage`), và đã thêm ca fail-closed `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels` khi thiếu `records`. Phần còn thiếu nay chỉ là **implementation** `records` (F06) — `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` vẫn dạng numeric-as-dict, thuộc A3-039/A3-022. → **Cập nhật 2026-09-11 (A3-022):** assertion numeric-as-dict cuối cùng trong file acceptance đã được chuyển sang interface (`equal_lows` giữ `float`; provenance đọc từ `records`); phần còn lại của node đó là fixture/detector thật, thuộc **A3-039**. | A3-005, A3-009, A3-010, A3-022 |
| History: giữ compatibility default của helper; canonical caller truyền `history_complete` tường minh | **MỘT PHẦN** → **ĐÃ ĐỦ (A3-011)** | Đã tường minh: `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` (True), `test_r72_04_assignment_survives_json_restore_with_late_only_window` (True), `test_r72_04_same_pool_observation_cannot_bypass_consumption` (True), `test_r72_04_incomplete_history_returns_explicit_reason` (False). **Còn dựa default**: `test_r72_03_acceptance_contribution_is_selected_within_owner_children`, `test_r72_02_same_time_tie_is_stable_under_claim_permutation`, `test_r72_02_missing_canonical_claim_time_fails_closed`, `test_r72_03_duplicate_owner_children_keep_one_contribution_under_permutation`. M §Interface proposal còn đề xuất default `history_complete=False`. *(Đã đính chính ở A3-006: default hiện hữu trong code là `True`; đề xuất cũ chỉ còn là lịch sử.)* → **Cập nhật 2026-09-11 (A3-011):** bốn ca "còn dựa default" cùng 3 call site dựng history ban đầu đã truyền `True` tường minh; cả **11 call site** `assign_sweep_ownership` trong file acceptance nay đều truyền cờ (10 `True`, 1 `False`). | A3-006, A3-008, A3-011, A3-012 |
| Claim canonical cần cả `reclaimed_at` và `setup_available_at`; parameterize thiếu **từng** field | **CÒN THIẾU** → **ĐÃ ĐỦ (A3-013)** | Chỉ có ca thiếu `setup_available_at`: `test_r72_02_missing_canonical_claim_time_fails_closed` (`missing.pop("setup_available_at")`). Chưa có ca thiếu riêng `reclaimed_at`. → **Cập nhật 2026-09-11 (A3-013):** node đã parameterize `[reclaimed_at]`/`[setup_available_at]`, claim giữ field còn lại + lineage và assert precondition từng field. | A3-013, A3-014 |
| Unknown metadata: `metadata_state="unknown"`, `metadata_reason` không rỗng, `usable=False`, threshold `None`; không thêm unknown vào lifecycle enum; tách missing ATR / missing tick / nonfinite / conflict | **CÒN THIẾU** | `test_r72_07_missing_or_nonfinite_canonical_metadata_is_unknown_not_zero` assert đúng dạng review cấm: `lifecycle_status in {"unknown","candidate","invalid"}` và `invalidation_buffer != 0.0`; không assert `metadata_state`/`metadata_reason`/threshold `None`. `test_r72_07_conflicting_same_scope_tick_sources_fail_closed` assert `lifecycle_status == "unknown"` (unknown là data-quality, không phải lifecycle status). Chưa có ca thiếu riêng **tick**; chưa có round-trip metadata (A3-021); chưa có ca terminal + metadata thiếu. → **Cập nhật 2026-09-11 (A3-015):** đã thêm node `test_r72_07_missing_canonical_atr_is_unknown_and_unusable` khóa **thiếu riêng ATR** với assertion đúng contract (`metadata_state`/`metadata_reason`/`usable False`/threshold `None`) + control; ca thiếu tick (A3-016), nonfinite (A3-017), conflict (A3-018), round-trip (A3-021) vẫn còn thiếu. → **Cập nhật 2026-09-11 (A3-016):** đã thêm node `test_r72_07_missing_canonical_tick_is_unknown_and_unusable` khóa **thiếu riêng tick** (ATR hợp lệ, không `digits` fallback) với cùng bộ assertion + control; còn lại nonfinite (A3-017), conflict (A3-018), terminal + thiếu (A3-020), round-trip (A3-021). → **Cập nhật 2026-09-11 (A3-017):** node bundled đã được **đổi tên + parameterize** thành `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]`, `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[tick_size]` (nonfinite tách khỏi missing; assertion theo contract, bỏ dạng bị cấm); còn lại conflict (A3-018), terminal + thiếu (A3-020), round-trip (A3-021). → **Cập nhật 2026-09-11 (A3-018):** ca conflict đã sửa expected sang `metadata_state`/`metadata_reason`/`usable False`/threshold `None` (bỏ assert `lifecycle_status == "unknown"` — đó là data-quality, không phải lifecycle status) và thêm precondition hai nguồn mâu thuẫn + ATR hợp lệ + vùng chưa terminal; còn lại terminal + thiếu (A3-020), round-trip (A3-021). → **Cập nhật 2026-09-11 (A3-019):** ca parity ba cách cấp tick đã siết sang expected **tuyệt đối** cho từng biến thể (`buffer ≈ 0.1`, `broken False`, `confirmed`, kèm assert ba khai báo thực sự khác nhau) thay vì chỉ so ba kết quả với nhau; còn lại terminal + thiếu (A3-020), round-trip (A3-021). → **Cập nhật 2026-09-11 (A3-020):** đã thêm node `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[expired_by_age]`, `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[already_invalid]` khóa ca **terminal + metadata thiếu** (giữ `expired`/`invalid`, `usable False`, `visits` còn nguyên, threshold `None`, kèm control có tick ⇒ cùng trạng thái terminal); **chỉ còn** round-trip metadata (A3-021). → **Cập nhật 2026-09-11 (A3-021):** đã thêm node `test_r72_07_metadata_survives_context_to_typed_round_trip` (lifecycle→context→`SmcZone.from_dict`→JSON) ⇒ **cụm R72-07 metadata đã đủ node**; phần còn lại của F01.1 là rà mô tả schema cũ (A3-022). | A3-007, A3-015, A3-016, A3-017, A3-018, A3-019, A3-020, A3-021 |

### F01.2 — Validate mọi positive factory

| Điểm | Kết quả | Bằng chứng (tên hàm / vị trí) | Mã A3 |
|---|---|---|---|
| Exit/reaction OHLC theo review: exit `(110.2,110.22,110.15,110.2)`, reaction `(112,114,111,113)`, SELL mirror; dòng 501 cũ `(112,114,111,110.5)` | **ĐÚNG RỒI — KHÔNG GHI ĐÈ** | `_terminal_candles` đã dùng exit `(110.2,110.22,110.15,110.2)`, reaction `(112,114,111,113)`, SELL mirror `(99.8,99.85,99.78,99.8)` / `(98,99,96,97)`. `test_r72_06_invalidation_precedes_expiry_and_reaction` đã là `[(112,114,111,113)] * 22`; mẫu `110.5` không còn. `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary` cũng khớp probe R72-06. → **Cập nhật 2026-09-11 (A3-024):** xác minh **BUY exit candle** bằng số học độc lập trên chính `rows` (không qua hàm production): với zone `[100,110]`, `tick=0.1`, `ATR=1` ⇒ tolerance `max(1*tick, 0.05*ATR)=0.1`, ngưỡng reaction `0.25*ATR=0.25`; exit `(110.2,110.22,110.15,110.2)` có `low 110.15 > 110.1` (ngoài vùng mở rộng) và `close-110 = 0.2 < 0.25` (chưa đạt reaction) ⇒ **giữ nguyên fixture**, chỉ thêm 2 assert bất biến ngay trong nhánh BUY của `_terminal_candles` để chặn hồi quy. → **Cập nhật 2026-09-11 (A3-025):** xác minh **BUY reaction candle** `(112,114,111,113)`: envelope OHLC hợp lệ, và điều kiện follow-through của BUY `close >= zone_high + 0.25*ATR = 110.25` đạt với biên `2.75` (close 113); nến không phải invalidation ⇒ **giữ nguyên fixture**, thêm 3 assert bất biến (envelope + ngưỡng reaction) vào nhánh BUY **không chỉ dựa vào validator**. → **Cập nhật 2026-09-11 (A3-026):** xác minh **SELL mirror** của exit/reaction: `exit (99.8,99.85,99.78,99.8) == mirror(110.2,110.22,110.15,110.2)` và `reaction (98,99,96,97) == mirror(112,114,111,113)` với phép mirror quanh 210 `(o,h,l,c)→(210−o,210−l,210−h,210−c)` — **khớp tuyệt đối**; nghĩa đối xứng đạt (exit dưới vùng mở rộng `99.85 < 99.9`, `100−close = 0.2 < 0.25`; reaction `close 97 ≤ 99.75`) ⇒ giữ nguyên fixture, thêm assert mirror + assert nghĩa vào nhánh SELL. Riêng **candle touch** `rows[19]` không phải mirror tuyệt đối (ghi ở §CHƯA RÕ, chờ A3-080). | A3-024, A3-025, A3-026 — chỉ xác minh |
| Mọi positive factory, kể cả local `run(rows)`, gọi validator đúng timeframe | **MỘT PHẦN** | Đã assert `validate_smc_candles`: `_terminal_candles` (D1), local `run()` trong `test_r72_07_equal_and_outside_buffer_buy_sell` (H1), các ca D1 `test_r72_05_cutoff_equal_invalidated_at_is_terminal` / `test_r72_06_invalidation_precedes_expiry_and_reaction`, và `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke` (tên cũ `test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture`, đổi tại A3-056). Các factory dùng `_probe.candles` được probe tự validate. **Chưa ghi danh sách factory/caller vào M** (A3-023). → **Cập nhật 2026-09-11 (A3-023):** đã lập danh sách đầy đủ 10 đường dựng nến (caller/timeframe/bước timestamp/nơi validate/loại) ở [Danh sách candle factory/caller](#danh-sách-candle-factorycaller--a3-023). Kết quả: **không** đường nào thiếu validator; **một** đường sai cadence (#7, H1 + bước ngày) ⇒ A3-028; **không** có fixture invalid-data cố ý trong file acceptance. → **Cập nhật 2026-09-11 (A3-027):** rà lại theo tiêu chí "validate **đúng timeframe** và **trước evaluator**": 6 call site validator tường minh trong file acceptance (dòng 131 `"D1"` `_terminal_candles`; 333 `"H1"` 5 fixture task59/60/62/63/65; 678 `"D1"`; 722 `"D1"`; 1000 `"H1"` local `run()`; 1074 `"H1"` gate56) + 2 trong probe (dòng 39 `"D1" if hours == 24 else "H1"`, dòng 187 `"H1"`). Mọi đường còn lại đi qua `_probe.candles`/`_terminal_candles` nên đã validate trước khi tới evaluator (`analyze_zone_lifecycle`/`enrich_zones`/detector/`_attach_zone_sweep_links`); **không** call nào thiếu timeframe (không nới validator) và **không** có fixture invalid-data cố ý ⇒ **không cần bổ sung validator**. | A3-023, A3-027, A3-028 |
| Invalidation đặt đúng candle age21 của D1 lifetime20, assert timestamp/index (không chỉ `broken=True`) | **CÒN THIẾU** | `test_r72_06_invalidation_precedes_expiry_and_reaction` vẫn đặt `rows[20] = (99,100,98,99)` trên 22 nến ⇒ age20, chưa collision với expiry age21; chỉ assert `lifecycle_broken is True` và `visits[0].reacted_at is None`. *(Mốc index/age/close của fixture D1: xem §[Timeline D1 terminal](#timeline-d1-terminal--a3-029) — age21 = index 21, `expired_at = 2026-09-23T00:00Z`.)* → **Cập nhật 2026-09-11 (A3-037):** fixture đã sửa đúng — invalidation đặt tại **idx21** (không còn row20): touch idx19, exit idx20 (`(110.2,…)`, chưa đủ reaction), invalidation idx21 `(99,100,98,99)` (SELL `(111,112,109,111)`); assert thêm `invalidation_index == 21`, `invalidated_at == 2026-09-23T00:00Z`, `expiry_index is None`, `lifecycle_expired is False` (invalidation **thắng** expiry cùng candle) + visit `completed_unreacted`. | A3-037 |
| Reaction trước / đúng / sau terminal, có D1 **và H4** theo lifetime tương ứng | **MỘT PHẦN** | D1 có: `test_r72_06_terminal_order_before_reaction_is_explicit[20-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[20-sell]`, `test_r72_06_terminal_order_before_reaction_is_explicit[21-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[21-sell]`, `test_r72_06_terminal_order_before_reaction_is_explicit[22-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[22-sell]` và `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[buy]`, `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[sell]`. **H4: không có node nào** (chuỗi `"H4"` trong file chỉ là payload `SmcZone`, không phải timeline H4). *(Mốc index/age/close của fixture D1: xem §[Timeline D1 terminal](#timeline-d1-terminal--a3-029).)* → **Cập nhật 2026-09-11 (A3-033):** đã ghi §[Timeline H4 terminal](#timeline-h4-terminal--a3-033) — lifetime 30 ⇒ terminal ở index 31, sau terminal index 32, cần **33 nến** bước 4h, kèm close cutoff và follow-through window `exit_index…exit_index+3`; A3-034…A3-036 dùng làm chuẩn. → **Cập nhật 2026-09-11 (A3-034):** H4 **đã có node** — `test_r72_06_h4_reaction_before_terminal_is_retained[buy]`, `test_r72_06_h4_reaction_before_terminal_is_retained[sell]` (33 nến bước 4h, reaction ở age30 trước terminal idx31, GREEN); A3-035/A3-036 còn phải thêm node cho "đúng terminal" và "sau terminal". → **Cập nhật 2026-09-11 (A3-035):** đã thêm node "H4 reaction **đúng terminal**" — `test_r72_06_h4_reaction_at_terminal_is_blocked[buy]`, `test_r72_06_h4_reaction_at_terminal_is_blocked[sell]` (reaction đặt tại idx31 = `expiry_index`); chỉ còn A3-036 cho "sau terminal". → **Cập nhật 2026-09-11 (A3-036):** đã thêm node "H4 reaction **sau terminal**" — `test_r72_06_h4_reaction_after_terminal_is_blocked[buy]`, `test_r72_06_h4_reaction_after_terminal_is_blocked[sell]` (reaction tại idx32 > terminal idx31, kèm so `[:32]` để chứng minh candle sau terminal không đổi lịch sử) ⇒ **H4 đã đủ 3 mốc** trước/đúng/sau terminal. | A3-030, A3-031, A3-032, A3-034, A3-035, A3-036 |
| Timeline D1/H4 ghi độc lập vào M (index so với age, availability→expiry) | **CÒN THIẾU** | M chưa có dòng timeline D1 (availability→expiry, index so với age) và H4 tương ứng. | A3-029, A3-033 |
| Cadence timestamp khớp timeframe fixture | **ĐÃ SỬA (A3-028)** | `test_r72_07_equal_and_outside_buffer_buy_sell` tạo nến H1 (`timeframe="H1"`, `tf_minutes=60`) bằng `start + timedelta(days=i)` — đúng dạng lỗi A3-028. → **Cập nhật 2026-09-11 (A3-028):** đổi sang `timedelta(hours=i)` (H1 = bước giờ) và thêm assert bất biến `values[1].time - values[0].time == timedelta(hours=1)` để chặn hồi quy; 3 đường D1 còn lại (`_terminal_candles` dòng 126, R72-05 dòng 676, R72-06 dòng 720) đã dùng bước **ngày** đúng timeframe, giữ nguyên. | A3-028 |
| Terminal repeat qua enrich→serialize→restore→enrich lại | **CÒN THIẾU** | Không có node nào; `test_r72_08_invalid_canonical_zone_survives_typed_round_trip_consistently` chỉ round-trip `SmcZone`, không qua `enrich_zones` lần hai. | A3-038 |

### F01.3 — Test chưa chứng minh đúng nhánh

| Hàng review | Kết quả | Bằng chứng (tên hàm) | Mã A3 |
|---|---|---|---|
| equal usable/reclaimed — chỉ tạo pool, không gọi sweep detector | **CÒN THIẾU** | `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` chỉ gọi `detect_liquidity_pools`; không excursion/reclaim, không parameterize source usable trước/bằng/sau close. Negative "sau" có ở `test_r72_01_acceptance_source_must_be_usable_at_sweep_close` nhưng bằng source đơn synthetic, không phải equal pool. → **Cập nhật 2026-09-11 (A3-039):** fixture đã có **excursion/reclaim thật** (nến idx1 `(100.3,100.5,99.5,100.3)`, `low 99.5 < 100.025 − 0.2`, `close 100.3 > 100.025`) và test **đã gọi `detect_liquidity_sweeps`** (`lookback_bars=8`, `causal_only=True`) với expected idx1/`level 100.025`/`reclaimed_at == stamp(2) == pool_usable_at`; đây là ca **biên "equal"** để A3-040 (trước) / A3-041 (đúng biên) / A3-042 (sau) parameterize trên cùng fixture. → **Cập nhật 2026-09-11 (A3-041):** ca biên **"equal"** đã được xác nhận khóa đúng (`pool_usable_at == reclaimed_at == stamp(2)`, sweep vẫn được **chấp nhận** theo A-D01) và đã ghi rõ trong test đây là **temporal seam synthetic** (`usable_at` do fixture khai, không chứng minh pivot producer — ca end-to-end thuộc A3-044). | A3-039, A3-040, A3-041, A3-042, A3-043 |
| actual swing→pool→sweep positive | **CÒN THIẾU** | Mọi positive pool/sweep hiện dùng source dict synthetic từ `_probe`; không node nào chạy actual swing producer. | A3-044 |
| same-pool observation — cả hai claim cùng `sweep_id`/`reclaimed_at` | **CÒN THIẾU** | `test_r72_04_same_pool_observation_cannot_bypass_consumption` gọi `_probe.claim` hai lần ⇒ cả hai cùng `sweep_id="sweep"`, `reclaimed_at=stamp(11)` (probe `claim`). Chưa đổi observation time/rolling index; chưa new-source control; chưa history conflict. → **Cập nhật 2026-09-11 (A3-045):** lượt 1 của node đã được **xác minh tường minh** (lineage `pool_id`/`source_ids` trên claim, `reason_codes == []`, owner `original`, `assignment_id` không rỗng, `claim_eligible_at == max(stamp(11),stamp(13))`, history qua JSON round-trip nguyên vẹn) ⇒ phần "assignment ban đầu" đã xong; việc **đổi observation** (sweep ID/time/rolling index) vẫn thuộc **A3-046**, còn A3-047/A3-048 cho control/history conflict. → **Cập nhật 2026-09-11 (A3-046):** lượt 2 nay là **observation mới thật** (`sweep_id="sweep-later"`, `reclaimed_at=stamp(17)`, index `99`, giữ `pool_id`/`source_ids`) và assert owner/assignment giữ nguyên + late contribution `False` ⇒ node chuyển từ "pass trivial" sang **RED đúng loại `implementation`** (F10): hiện `assignments["sweep-later"]["owner_setup_id"]` trả `"later"`. → **Cập nhật 2026-09-11 (A3-047):** đã thêm **control pool mới thật** (`pool_id="pool-2"`/`source_ids=["swing-2"]`, sweep `sweep-new`): không bị khóa nhầm bởi pool cũ (`reason_codes == []`, owner `"new-setup"`, contribution `True`) — chặn khả năng fix F10 over-block. | A3-045, A3-046, A3-047, A3-048 |
| cutoff==invalidated_at — `reacted_at=None` | **CÒN THIẾU** | `test_r72_05_cutoff_equal_invalidated_at_is_terminal` chỉ outside→touch→close phá vùng; **không có exit+reaction trước terminal**, nên không chứng minh prefix `valid/score>0`; chưa có ca expiry cutoff đối ứng. → **Cập nhật 2026-09-11 (A3-049):** fixture đã thành **4 nến** (outside → touch → **exit+reaction** → invalidation) và đã có **prefix positive** (`as_of = close nến idx2` ⇒ `valid True`/`score > 0`, cùng `zone_id`/`source_visit_id`) ⇒ chain đã chứng minh reaction thật trước terminal; hệ quả: node chuyển từ GREEN-nhưng-yếu sang **RED đúng loại `implementation` (F05)** vì tại cutoff bằng `invalidated_at` consumer vẫn trả `valid=True/score=1.0`. Ca **expiry cutoff** đối ứng vẫn thuộc A3-051. → **Cập nhật 2026-09-11 (A3-051):** đã thêm node `test_r72_05_cutoff_equal_expired_at_is_terminal[buy]`, `test_r72_05_cutoff_equal_expired_at_is_terminal[sell]` trên `_terminal_candles(side, 20)`: prefix 21 nến là positive thật (`reacted_at == 2026-09-22T00:00Z` và evidence tại close đó `valid True`/`score>0`), còn tại `expired_at == 2026-09-23T00:00Z` (`expiry_index == 21`) evidence `valid False`/`score 0` và reaction giữ nguyên ⇒ **GREEN** (reason `D1_REACTION_STALE`) — đối chiếu: nhánh **invalidation** cutoff thì **chưa** bị chặn, đó là gap F05. | A3-049, A3-050, A3-051 |
| typed terminal→D1 — `dict()` không typed, zone/zone khác nhau, cutoff trước reaction | **CÒN THIẾU** | `test_r72_08_typed_terminal_projection_reaches_d1_consumer` vẫn `restored = dict(terminal_zone)` thay vì `SmcZone.from_dict(...).to_dict()`; `zone_id="terminal-zone"` còn khác zone `"zone"` của `_probe.lifecycle`. → **Cập nhật 2026-09-11 (A3-052):** đã chuẩn hóa — payload dựng bằng `SmcZone.from_dict({... "timeframe": "D1", "zone_id": visit.zone_id ...}).to_dict()` (không còn `dict()`), cutoff `stamp(96)` **sau** reaction `stamp(72)`, và thêm 2 assert loại trừ kết luận sai nhánh (không do ID lệch, không do cutoff trước reaction). Hệ quả: node chuyển từ GREEN-nhưng-sai-nhánh sang **RED đúng loại `implementation` (F05)** — vùng canonical terminal vẫn cấp evidence hoạt động; A3-053/054/055 tiếp tục cho control positive / invalid / expired. | A3-052, A3-053, A3-054, A3-055 |
| detector→lifecycle→D1 — candidate chưa confirmed, ATR tự gán, so chính serialization | **ĐÃ XỬ LÝ (A3-056)** — phần phạm vi/tên và assertion rỗng; nguồn confirmed D1 end-to-end vẫn CÒN THIẾU | `test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture` vẫn dùng `detect_order_block_candidates` (candidate, không confirmed), `atr_current=5.0` tự gán, và assert `lifecycle.to_dict()["visits"] == [visit.to_dict() for visit in lifecycle.visits]`; tên còn ghi `d1_context_chain` nhưng thực chạy H1. → **A3-056 (2026-09-11):** đã đổi tên thành `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke`, thêm `assert candidate["lifecycle_status"] == "candidate"` + `assert candidate.get("confirmed") is not True`, gỡ assertion tautology (`to_dict()` so chính nó), và ghi rõ `atr_current=5.0` là do ca smoke tự gán ⇒ **hết mập mờ phạm vi**; nguồn confirmed thật (`confirm_order_block_candidate(s)`) vẫn là việc của A3-057…A3-062, **không** lấy ca này làm bằng chứng. | A3-057, A3-058, A3-059, A3-060, A3-061, A3-062 |

### F01.4 — Audit coverage và bàn giao

| Điểm | Kết quả | Bằng chứng | Mã A3 |
|---|---|---|---|
| Map từng ô bảy cụm §4 → full test path + parameter ID; trình một lần | **CÒN THIẾU** | M chưa có mapping §4; mục "Actual F01 run ledger" ở trên vẫn là số của A lần2 (49 collected / 30 failed 19 passed), chưa phải kết quả lượt A3. | A3-063…A3-090 |

### Fixture đã sửa — nhận diện để KHÔNG ghi đè

Các thay đổi này đã có sẵn trước lượt A3-003 (xem thêm §A3.4 trong fix-progress):

- `_terminal_candles` — exit/reaction/mirror đã đúng theo F01.2.
- `test_r72_06_invalidation_precedes_expiry_and_reaction` — dòng `rows` mở đầu không còn mẫu `110.5` sai OHLC.
- `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary` — đã khớp giá trị exit/reaction của probe R72-06.
- Năm fixture task59/60/62/63/65 — đã sửa ở F01, giữ PASS (bảng old→new ở fix-progress §F01 result).

### CHƯA RÕ — cần xác minh ở A3-080

- `test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid` hard-code `rows` trong chính file acceptance rồi gọi `module._candles(rows)`. Nó validate **bản sao hard-code**, không phải rows mà module task59/60/62/63/65 thực dùng, nên chưa chắc là bằng chứng R72-09 đầy đủ.
- **Candle touch của `_terminal_candles` nhánh SELL không phải mirror tuyệt đối của BUY** (phát hiện ở A3-026): `rows[19]` BUY `(109,110,105,109)` mirror quanh 210 cho `(101,105,100,101)`, nhưng fixture SELL dùng `(101,105,99,102)` — lệch `low` 1 đơn vị và `close` 1 đơn vị. **Tương đương về nghĩa** (cả hai đều overlap zone `[100,110]` để mở visit và đều không invalidate), nên A3-026 **không đổi** (ngoài phạm vi hàng: A3-026 chỉ khóa exit/reaction). Cần A3-080/A3-063 quyết định có chuẩn hoá thành mirror tuyệt đối hay giữ nguyên (sửa sẽ đổi fixture dùng bởi `test_r72_06_terminal_order_before_reaction_is_explicit` nên phải chạy lại nhóm đó).

---

## Bảng theo dõi ca nghiệm thu — A3-004

Cột chuẩn hóa theo [fix-plan §8.2][§8] (A3-004). **Một hàng cho mỗi full node ID chạy được** — không
dùng `[buy]`, `%%SPLITNAME%%[sell]` làm node. 49 hàng = 49 node collect được ở §A3.5 của fix-progress; **A3-010 thêm 2 node
mới** (R72-01, ca canonical thiếu `records`); **A3-013 parameterize 1 node R72-02 thành 2** (thiếu
`reclaimed_at` / thiếu `setup_available_at`); **A3-015/A3-016 thêm 2 node R72-07** (thiếu riêng ATR; thiếu
riêng tick); **A3-017 đổi node bundled `missing_or_nonfinite` thành 2 node nonfinite** (ATR/tick NaN);
**A3-020 thêm 2 node R72-07** (terminal + metadata thiếu: expired/giữ nguyên invalid); **A3-021 thêm 1 node
R72-07** (metadata qua lifecycle→context→typed round-trip); **A3-034 thêm 2 node R72-06** (H4 reaction trước
terminal); **A3-035 thêm 2 node R72-06** (H4 reaction đúng terminal); **A3-036 thêm 2 node R72-06** (H4 reaction sau
terminal); **A3-038 thêm 4 node R72-06** (terminal state qua enrich→restore→enrich × `expired`/`invalid`); **A3-040 thêm
1 node R72-01** (equal pool usable **trước** sweep close ⇒ nhận sweep); **A3-042 thêm 2 node R72-01** (nguồn
usable **sau** sweep close ⇒ reject, BUY/SELL); **A3-043 thêm 2 node R72-01** (usable time = max cả hai source;
thiếu source usable ⇒ không có equal pool); **A3-044 thêm 1 node R72-01** (end-to-end swing producer →
pool → sweep); **A3-048 thêm 1 node R72-04** (assignment history mâu thuẫn ⇒ fail closed); **A3-051 thêm 2 node R72-05**
(cutoff bằng `expired_at` ⇒ terminal, BUY/SELL); **A3-053 thêm 2 node R72-08** (typed D1 positive control — payload
không terminal giữ valid/positive qua round-trip); **A3-054 thêm 2 node R72-08** (typed invalid thắng legacy flags
trái canonical ⇒ D1 invalid/0); **A3-055 thêm 2 node R72-08** (typed expired ⇒ D1 invalid/0, giữ reacted history)
⇒ đoạn tăng trưởng trên là lịch sử tới A3-055. **Bản trình A3-090 có116 node** (reviewer collect xác nhận); các số cụm cũ không phải inventory hiện hành.

- `Actual` còn khoảng80 hàng trống là lệch đồng bộ của bản trình, không phải test chưa chạy: actual116 node ở fix-progress §A3.87 và reviewer §A3.94. A3-081/A3-090 cập nhật hàng theo bản sửa kế tiếp; không dùng số A lần2 hoặc để lịch sử GREEN che finding A3R3. GREEN không tự là finding CLOSED.
- `Loại RED` chỉ điền sau khi chạy. Giá trị hợp lệ: `implementation` (core chưa sửa, expected đúng),
  `interface` (thiếu field/API đã duyệt tại A), `assertion` (assert sai nhánh), `fixture` (dữ liệu
  test sai), `collection` (import/collect lỗi), `green`.
- `Precond` là điều kiện phải đúng để phép assert có nghĩa, tách khỏi input.
- Ghi chú `⇒ cần sửa` ở cột Expected là hệ quả của A3-003: expected hiện tại chưa khớp contract.

### R72-01 — pool/source-time (31 node, xanh toàn bộ từ F07 2026-09-11)

| Full node ID | Rule ref | Input / timeframe / cutoff | Precond | Expected | Actual | Loại RED |
|---|---|---|---|---|---|---|
| `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[buy]` | R72-01, A-D01 | H1 8 nến, `rows[2]=(110,111,99.5,100.1)`; cutoff = nến cuối; sweep candle idx2 đóng 03:00 | source `confirmed=True/usable=True/provisional=False` tại snapshot; `confirmed_at=06:00 > 03:00` | `swept_lows == []` | **RED — implementation** · F06/F07 (chưa cô lập) · §A3.118 | F06/F07 (chưa cô lập) |
| `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[sell]` | R72-01, A-D01 | Mirror SELL quanh 210, cùng cadence H1 | như trên, pool `swept_highs` | `swept_highs == []` | **RED — implementation** · F06/F07 (chưa cô lập) · §A3.118 | F06/F07 (chưa cô lập) |
| `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy]` | R72-01, A-D06, A3-005, A3-009 | H1 8 nến; 2 equal source level `100`/`100.05`, `confirmed_at=usable_at=stamp(1)`/`stamp(2)` | equal tolerance `.10*ATR=0.1`, `ATR=1`, `tick=.1` | numeric projection vẫn `list[float]` = trung bình cặp `100.025` (không phải dict); `records` có **đúng một** record `source_ids=["source-a","source-b"]`, `pool_id`/`kind` không rỗng, `usable_at = max(stamp(1),stamp(2)) = stamp(2)` tính từ fixture, `sources` giữ `confirmed_at`/`usable_at`/`provisional=False` từng source. Đã chuyển assertion sang `records` ở A3-009 | **RED — implementation** · F06 · §A3.118 → **GREEN** (2026-09-11, **F06**): `detect_liquidity_pools` phát `records` canonical; projection numeric `float` giữ nguyên | — |
| `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[sell]` | R72-01, A-D06, A3-005, A3-009 | Mirror SELL: level `110`/`109.95` | như trên | như trên, pool `equal_highs` = `109.975`; cùng bộ assertion `records` | **RED — implementation** · F06 · §A3.118 → **GREEN** (2026-09-11, **F06**): mirror SELL của node `[buy]`, cùng nguồn `records` | — |
| `test_r72_01_provisional_source_cannot_create_a_sweep` | R72-01, P7 | H1 8 nến, `rows[2]=(110,111,99.5,100.1)`; source `provisional=True` | excursion vượt pool strict, reclaim trong candle | `swept_lows == []` | **GREEN** | — |
| `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` | A-D01 inclusive, A3-022, A3-039, A3-041 | H1 8 nến; **nến idx1 = `(100.3,100.5,99.5,100.3)`** (excursion + reclaim thật); 2 source equal `100`/`100.05`, cả hai `confirmed_at=usable_at=stamp(2)`; `tick=.1`, `ATR=1` | `pool_usable_at == reclaimed_at` (biên); geometry: `low 99.5 < 100.025 − excursion(0.2)` và `close 100.3 > 100.025`; numeric projection giữ `float`; provenance đọc từ `records`; **temporal seam synthetic** (usable_at do fixture khai, không phải pivot producer — ca end-to-end là A3-044); `pool_usable_at` tính **từ fixture** với precondition `pool_usable_at == usable_at == stamp(2)` | numeric `equal_lows == [100.025]` (không phải dict); **target event** lọc theo **level `100.025` + candle `index 1`** (**không** dùng vị trí list) phải **tồn tại** và có `reclaimed_at == pool_usable_at == stamp(2)` (equality **được chấp nhận** theo A-D01); `swept_highs == []` (không khai swing high). **Không** assert tổng số `swept_lows`, pool priority hay dedupe. Sau đó mới đọc canonical `records`: đúng **một** record `source_ids=["source-a","source-b"]`, `usable_at == max == stamp(2)` | **RED — implementation** (2026-09-11, **A3-039 + A3-041**): toàn bộ assertion temporal target **PASS** (target event `idx1`, `level 100.025`, `reclaimed_at == pool_usable_at == stamp(2)`); fail sau đó tại `assert len(records) == 1` → `assert 0 == 1` vì `core/` chưa phát `records` — **EXPECTED_IMPLEMENTATION_RED F06**, không phải lỗi temporal → **GREEN** (2026-09-11, **F06**): `records` có đúng một record `source_ids=["source-a","source-b"]`, `usable_at == max == stamp(2)`; temporal seam không đổi | — |
| `test_r72_01_equal_pool_usable_before_sweep_close_is_accepted` (**A3-040**) | A-D01 gate, A3-040 | H1 8 nến; **nến idx2 = `(100.3,100.5,99.5,100.3)`**; 2 source equal `100`/`100.05` usable/confirmed tại `stamp(2)`, non-provisional; `tick=.1`, `ATR=1` | `pool_usable_at = stamp(2)` **<** event close `stamp(3)` (usable **trước** sweep close); geometry: `low 99.5 < 100.025 − 0.2`, `close 100.3 > 100.025`; equal pool **thật sự tồn tại** ở `expected_level` và `expected_level` **khác cả hai** level single-source ⇒ lọc theo level không bắt nhầm | **target event** lọc theo **level `100.025` + candle `index 2`** (**không** dùng vị trí list) phải **tồn tại** và khớp `kind == "swept_low"`, `side == "buy"`, `time == stamp(2)` (open), `reclaimed_at == stamp(3)` (close), `excursion_buffer ≈ 0.2`; `swept_highs == []` (không khai swing high). **Không** assert tổng số `swept_lows`, pool priority hay dedupe | **GREEN** (2026-09-11, A3-040) — gate A-D01 nhận đúng vế before/equality; oracle không còn khóa priority/cardinality | — |
| `test_r72_01_source_usable_after_sweep_close_is_rejected[buy]` | A-D01 gate, A3-042 | H1 8 nến; **cùng geometry như control A3-040** (nến idx2 `(100.3,100.5,99.5,100.3)`) nhưng 2 source equal `100`/`100.05` chỉ usable/confirmed tại **`stamp(4)`** | `pool_usable_at = stamp(4)` **>** event close `stamp(3)` (nguồn **tương lai**); geometry excursion/reclaim vẫn hợp lệ | **không** dùng nguồn tương lai: `swept_lows == []` **và** `swept_highs == []` (khác control chỉ ở mốc usable ⇒ reject phải do gate A-D01; hiện RED đến khi F07 implement) | **RED — implementation** · F07 · §A3.118 | F07 |
| `test_r72_01_source_usable_after_sweep_close_is_rejected[sell]` | A-D01 gate, A3-042 | Mirror SELL: pool `equal_highs` `110`/`109.95` (level `109.975`), nến idx2 mirror `(109.7,110.5,109.5,109.7)`, usable tại `stamp(4)` | như trên (`high 110.5 > 109.975 + 0.2`, `close 109.7 < 109.975`) | như trên, kiểm `swept_highs` | **RED — implementation** · F07 · §A3.118 | F07 |
| `test_r72_01_equal_pool_usable_time_is_max_of_both_sources` (**A3-043/a**) | A-D01 max-of-sources, A3-043, **A3R3-05** | H1 8 nến; 2 source equal `100`/`100.05` với **usable/confirmed khác nhau**: `source-a = stamp(1)`, `source-b = stamp(3)`; nến idx1 `(100.3,100.5,99.5,100.3)` | equal pool tồn tại; `pool_usable_at = max = stamp(3)`; event close `stamp(2)` **nằm giữa** hai mốc (`stamp(1) < stamp(2) < stamp(3)`) ⇒ chỉ dùng mốc source đầu sẽ nhận sai; **`expected_level` khác cả hai level single-source** ⇒ lọc theo level chỉ bắt được equal pool | danh sách event **của riêng target equal pool** (lọc `sweep["level"] == expected_level`, **không** theo vị trí list) phải **rỗng** — khóa luật **max cả hai source**; `swept_highs == []` (fixture không khai swing high nào). **Không** khóa tổng số sweep, pool priority hay dedupe: single-source sweep hợp lệ của `source-a` (level `100`, usable `stamp(1)`) **không** bị oracle này cấm (control riêng thuộc A3-043/b) | **RED — implementation** (2026-09-11, A3-043/a): precondition + hình học + precondition phân biệt level PASS; fail tại `assert equal_pool_events == []` (còn `index 1`, level `100.025`, `reclaimed_at stamp(2)` trong khi equal pool usable `stamp(3)`) ⇒ gate A-D01 `usable_at <= reclaimed_at` chưa được áp | F07 |
| `test_r72_01_single_source_pool_usable_before_sweep_close_is_accepted` (**A3-043/b**) | R72-01, A3-043/b, A3R3-05 control | H1 8 nến — **đúng geometry của A3-043/a** (nến idx1 `(100.3,100.5,99.5,100.3)`) nhưng **chỉ khai một low source**: `source-a` level `100.0`, `confirmed_at = usable_at = stamp(1)`, non-provisional; `tick=0.1`, `ATR=1.0` | nguồn confirmed/usable/non-provisional; `stamp(1) < stamp(2)` (usable **trước** close nến sweep); geometry thật: `low 99.5 < 100 − 0.2` và `close 100.3 > 100` | một nguồn không thể tạo equal pool nên `equal_lows == []` và `swing_lows == [100.0]`; event **của riêng level `100.0`** (lọc theo level, **không** theo vị trí list) phải tồn tại và khớp `index 1`, `reclaimed_at stamp(2)`, `source_swing_id "source-a"`. **Không** assert tổng số `swept_lows`, pool priority hay dedupe; **không** dùng/đòi canonical `records` | **GREEN** (2026-09-11, A3-043/b) — single-source sweep hợp lệ, đúng vế mà negative A3-043/a **không** được cấm | — |
| `test_r72_01_equal_pool_without_usable_source_does_not_exist` | A3-043 thiếu/chưa usable một source | H1 8 nến; `source-b.usable = False` (level `100.05`), `source-a` usable tại `stamp(2)`; nến idx2 `(100.3,100.5,99.5,100.3)` | source không usable bị loại khỏi projection | `equal_lows == []` (không có equal pool để sweep) và `swing_lows == [100.0]` (chỉ còn level của source hợp lệ) | **GREEN** | — |
| `test_r72_01_actual_swing_producer_feeds_pool_and_sweep` | R72-01 end-to-end, A3-044 | H1 **12 nến OHLC thật**; `external_swing_points(symbol="EURUSD", timeframe="H1", lookback=2)` phát **một** swing low tại idx4 (level `99.5`); nến idx10 `(100,100.6,99.0,100.2)` là candle sweep | producer: `pivot_time == stamp(4)` (open pivot), `confirmed_at == stamp(7)` (close của idx4+lookback), `confirmed/usable True`, non-provisional; geometry sweep: `low 99.0 < 99.5 − 0.2`, `close 100.2 > 99.5` | `swing_lows == [99.5]` (pool dựng từ chính swing producer phát); sweep: đúng **idx10**, `level == 99.5`, `reclaimed_at == stamp(11)`, **`source_swing_id == swing["swing_id"]`** (lineage về swing thật); `confirmed_at` (stamp 7) **<** `reclaimed_at` (stamp 11) — sweep **sau** usable; tách hẳn fixture synthetic 039–043 (nguồn do producer tạo, không khai tay) | **GREEN** | — |
| `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[buy]` | R72-01, A3-005 luật 3, A3-010 | H1 8 nến, `rows[2]=(110,111,99.5,100.1)`; payload pool numeric-only `swing_lows=[100.0]`, **không** có `records`; `tick=.1`, `ATR=1` | numeric level còn tồn tại; geometry fixture: `low 99.5 < 100 - excursion(0.2)` và `close 100.1 > 100` (excursion + reclaim thật); control no-pool sweep tại idx2 PASS | `swept_lows == []` và `swept_highs == []` — numeric level không đủ cấp sweep canonical (fail closed) | **RED — implementation** · F06 · §A3.118 | F06 |
| `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[sell]` | R72-01, A3-005 luật 3, A3-010 | Mirror SELL quanh 210: pool `swing_highs=[110.0]`, không `records`; `high 110.5 > 110 + 0.2`, `close 109.9 < 110` | như trên | `swept_highs == []` và `swept_lows == []` | **RED — implementation** · F06 · §A3.118 | F06 |
| `test_r72_01_missing_pool_provenance_fails_closed[record_for_other_level]`, `test_r72_01_missing_pool_provenance_fails_closed[no_sources]`, `test_r72_01_missing_pool_provenance_fails_closed[dangling_source_id]`, `test_r72_01_missing_pool_provenance_fails_closed[source_without_provenance_id]`, `test_r72_01_missing_pool_provenance_fails_closed[source_without_usable_at]` | R72-01, A3-064, A3-005 luật 3 | H1 8 nến `rows[2]=(110,111,99.5,100.1)` (excursion `0.5 > 0.2` + reclaim trong nến); pool có `records` 1 record khớp level `100` **kèm đúng một khuyết điểm provenance** do tham số đặt tên; `swing_lows=[100.0]` vẫn là projection numeric; control: cùng nến/swing chạy đường legacy (không `liquidity_pools`) | record khớp level và **chỉ** thiếu phần provenance được nêu: sai `level`; không `sources`; `source_ids` trỏ nguồn vắng; source thiếu `swing_id`; source thiếu `usable_at` | canonical `swept_lows == []` và `swept_highs == []` (fail closed, không fallback numeric); control legacy vẫn sweep ở `index 2` ⇒ kết quả rỗng là do provenance | **RED 5/5 — implementation** (2026-09-11): core chưa đọc `records` nên vẫn cấp sweep từ level numeric (`index 2`, `source_swing_id="pool-source"`); precondition + control PASS | F06 |
| `test_r72_01_excursion_threshold_is_strict[below-buy]`, `test_r72_01_excursion_threshold_is_strict[below-sell]`, `test_r72_01_excursion_threshold_is_strict[equal-buy]`, `test_r72_01_excursion_threshold_is_strict[equal-sell]`, `test_r72_01_excursion_threshold_is_strict[beyond-buy]`, `test_r72_01_excursion_threshold_is_strict[beyond-sell]` | R72-01, A3-065 strict excursion | H1 8 nến buy-shape `rows[2]=(110,111,100−depth,100.1)`, `depth = max(2×tick, 0.10×ATR) + slack`, slack `−0.05`/`0`/`+0.05`; SELL dùng đúng fixture đó qua mirror của probe; source confirmed/usable/non-provisional | penetration **đúng** `excursion + slack`; nến reclaim level trong cùng nến ở cả 3 mức; `below` = dưới biên, `equal` = **đúng biên**, `beyond` = vượt biên | `below`/`equal` ⇒ `swept_* == []` (**đúng biên chưa đủ**); `beyond` ⇒ đúng 1 sweep `index 2`, `level` khớp, `depth == excursion + 0.05`, `excursion_buffer == max(2×tick, 0.10×ATR)`, `source_swing_id` khớp | **GREEN 6/6** (2026-09-11) — rule strict đã đúng trong `core/`; audit không cần sửa | — |
| `test_r72_01_pool_sweep_evidence_survives_future_bars` (A3-066) | R72-01, A3-066 causal prefix/batch | H1: prefix = 12 nến đầu của `_POOL_CAUSAL_ROWS` (fixture A3-044: pivot low idx4, sweep idx10), batch = đủ 16 nến (thêm swing high idx13 + swept high idx14); cả hai chạy producer → pool → sweep với `lookback_bars = len(series)`; cutoff = close nến 11 | batch **thật sự** khác prefix (2 low swing thay vì 1; nhiều hơn 1 high swing); pivot idx4 giữ nguyên `swing_id`/`level`/`pivot_time`/`confirmed_at` (không backdate); pool `swing_lows == [99.5]` | evidence của sweep đã **reclaim (close) ≤ cutoff** **giống hệt** giữa prefix và batch trên 12 field causal (sweep_id/level/time/occurred_at/reclaimed_at/depth/excursion_buffer/source_swing_id/source_pool_id/…); lọc theo `reclaimed_at` chứ **không** theo `time` (open nến), toán tử **bao gồm** tại đúng cutoff; sweep đuôi `swept_highs == [14]` chỉ batch có; canonical (**A3-066/b, /c**): record chọn theo **kind + lineage** (không theo vị trí list/level), `pool_id` không rỗng, `sources` khớp swing fixture, `usable_at == max(usable_at các source)`, **`sweep["source_pool_id"] == record["pool_id"]`** cho **cả hai** lượt, và pool thứ hai cùng kind (idx10 level `99.0`) được phân biệt bằng lineage | **RED — implementation** (2026-09-11, A3-066/a…/c): khối causal (kể cả lọc theo reclaim close) **PASS**; fail tại `_pool_record_for` → `assert 0 == 1` vì payload **không có `records`** (F06); `source_pool_id` hiện bằng `source_swing_id` (fallback `core/smc_context.py:4408-4415`) → **F06/r1** (2026-09-11): producer phát `usable_at` ⇒ `records` **có**; toàn bộ assertion pool chạy tới và **PASS** (`_pool_record_for` theo kind+lineage, `_assert_pool_record_matches_source`, `pool_id`/`source_ids`/`usable_at`/`level` giữ nguyên prefix↔batch); fail kế tiếp tại **dòng nối sweep** `sweep["source_pool_id"] == record["pool_id"]` → owner **F07** | F06 (lịch sử) → **F07** |
| `test_r72_01_pool_sweep_identity_survives_rolling_index` (A3-066) | R72-01, A3-066, A-D06 rolling index | batch 16 nến vs rolled 15 nến (bỏ nến cũ nhất, **giữ nguyên timestamp** của các nến còn lại, không thêm nến mới); cùng producer/pool/sweep | `rolled[0].time == batch[1].time`; số nến giảm 1; `swing_lows` pool giống nhau | pivot cùng mốc thời gian giữ **nguyên** `swing_id`/`level`/`confirmed_at` chỉ `index` 4 → 3; sweep giữ **nguyên** identity (`sweep_id`, `reclaimed_at`, level, depth, source IDs) chỉ `index` 10 → 9; canonical (**A3-066/d**): record của **cùng** pool ở batch (idx4) và rolled (idx3) giữ **cùng** `pool_id`/`source_ids`/`kind`/`level`/**`usable_at`**, và `sweep["source_pool_id"] == record["pool_id"]` ở **cả hai** lượt | **RED — implementation** (2026-09-11, A3-066/d): precondition + `_pool_causal_evidence` parity **PASS**; fail tại `_pool_record_for` → `assert 0 == 1` (`records` chưa có — F06) → **F06/r1** (2026-09-11): `records` **có**; precondition + record parity (`pool_id`/`source_ids`/`kind`/`level`/`usable_at` batch↔rolled) **PASS**; fail kế tiếp tại **dòng nối sweep** `batch_sweep["source_pool_id"] == batch_record["pool_id"]` → owner **F07** | F06 (lịch sử) → **F07** |
| `test_r72_01_pool_identity_survives_source_permutation` (A3-066/e, **/e-r1**) | R72-01, A3-066/e, A-D06 permutation | H1 8 nến buy-shape; 2 source equal `100.0`/`100.05` **cố ý để thứ tự causal NGƯỢC thứ tự sort ID**: `source-z` idx0 `pivot_time stamp(0)` usable `stamp(1)` (pivot **sớm**, sort **cuối**); `source-a` idx1 `pivot_time stamp(1)` usable `stamp(2)` (pivot **muộn**, sort **đầu**); chạy `detect_liquidity_pools` cho **cả hai** thứ tự input | hai thứ tự input **khác nhau** (permutation thật); `causal_ids == ["source-z","source-a"]`, `sorted_ids == ["source-a","source-z"]`, **hai quy tắc khác nhau** (test phân biệt được, không thể pass nhờ so hai output với nhau); fixture phát **cả** swing pool (`swing_lows [100.0, 100.05]`) lẫn equal pool ⇒ chọn record theo `kind` là bắt buộc | chọn record theo **kind + lineage sort ID** `["source-a","source-z"]`: **`source_ids` là danh sách ĐÃ SORT ổn định** (không theo input order, không theo causal order); `usable_at == max(usable) == stamp(2)` (từ fixture); numeric projection `equal_lows == [100.025]`; **từng source** giữ đúng `confirmed_at`/`usable_at`/`provisional` tra **theo `swing_id`** (không theo vị trí list `sources`); hai lượt giữ **cùng** `pool_id`/`source_ids`/`usable_at`/`kind "equal_low"`/`level`; **không** assert số lượng sweep, pool priority hay dedupe | **RED — implementation** (2026-09-11, A3-066/e + /e-r1): precondition permutation **PASS**; fail tại `_pool_record_for` → `assert 0 == 1` với thông báo `('equal_low', ['source-a', 'source-z'], [])` (`records` chưa có — F06). Đã kiểm độc lập: record synthetic `source_ids` **sort** ⇒ ACCEPTED, `source_ids` **causal** ⇒ REJECTED ⇒ assertion phân biệt đúng hai quy tắc → **GREEN** (2026-09-11, **F06**): record `kind "equal_low"`, `source_ids` **đã sort** `["source-a","source-z"]`, `usable_at == max == stamp(2)`, `pool_id`/`level` giữ nguyên qua cả hai thứ tự input; từng source tra theo `swing_id` | — |
| `test_r72_05_zone_nonterminal_defaults_cannot_mask_active_lifecycle_terminal` (**B-R1**) | R72-05, A-D04, **B-R1** | `_probe.lifecycle` D1 BUY 4 nến `(112,114,111,113),(109,110,105,109),(112,114,111,113),(99,100,98,99)` ⇒ `broken=True` + `visits[0]=completed_reacted`; zone mapping mang cờ non-terminal/default (`lifecycle_status="confirmed"`, `broken`/`lifecycle_broken`/`lifecycle_expired`/`lifecycle_stale=False`, `age_bars=0`) | lifecycle thật sự terminal; zone chỉ có cờ mặc định, **không** mang evidence terminal nào | cờ non-terminal của zone **không** che terminal của lifecycle ⇒ `valid=False`, `score=0`, reason `D1_REACTION_STALE`; control cùng shape zone nhưng lifecycle **không** terminal ⇒ `valid=True`, `score>0` | **GREEN** (2026-09-11, B-R1) | — |
| `test_r72_07_known_expired_is_preserved_when_metadata_is_missing` (**B-R2**) | R72-07, A3-007 §4, **B-R2** | vế cửa sổ ngắn: H1 3 nến, payload `lifecycle_status="expired"`, `expired_at=stamp(2)`, thiếu tick; vế vượt lifetime: D1 `_probe.candles([(112,114,111,113)]*25, hours=24)`, cùng payload với `expired_at=stamp(48)` | `metadata_state="unknown"`, `invalidation_buffer=None`; lifetime D1 = 20 ⇒ index vượt tuổi đầu tiên là 21, close của nó = `stamp(24*22)` (suy từ fixture) | terminal đã khai được giữ **verbatim**: `lifecycle_status="expired"`, `expired_at` = đúng mốc khai (và **khác** mốc expiry suy ra), `lifecycle_expired=True`, `lifecycle_broken=False`, `usable=False`; không có `ZONE_INVALIDATED` | **GREEN** (2026-09-11, B-R2/r1) | — |
| `test_r72_07_known_invalid_is_preserved_when_metadata_is_missing` (**B-R2**) | R72-07, A3-007 §4, **B-R2** | vế cửa sổ ngắn: H1 2 nến, payload `lifecycle_status="invalid"`, `broken=True`, `invalidated_at=stamp(2)`, thiếu tick; vế vượt lifetime: D1 25 nến như trên với `invalidated_at=stamp(48)` | `metadata_state="unknown"`, `invalidation_buffer=None`; derivation **có** sinh expiry ở vế dài nhưng không được phép ghi đè | giữ **invalid** + `invalidated_at` đã khai (không chuyển thành expiry muộn hơn), `broken=True`, `lifecycle_broken=True`, `lifecycle_expired=False`, `expired_at=None`, `usable=False`, reason có `ZONE_INVALIDATED` và **không** có `ZONE_EXPIRED`. **Vế history (B-R2/history):** với `visits` lấy từ `_probe.lifecycle` thật (D1 6 nến, `invalidated_at=stamp(96)`, visit-2 `closed_by_invalidation`), enrich thiếu tick phải giữ nguyên history đầu vào (`visit-2` vẫn `closed_by_invalidation`, `reacted_at=None`), **không** mutate payload của caller và **không** sinh reaction tại/sau terminal đã biết | **GREEN** (2026-09-11, B-R2/r1 + B-R2/history) | — |

**Refresh F07/r1 (2026-09-11, public route compatibility):** **baseline xác minh được** cho hành vi route public trước tác động canonical — (B1) contract tests retained đang xanh: `tests/test_smc_liquidity_sweeps_task67.py::test_pool_levels_are_used_when_explicitly_supplied` (payload numeric ⇒ `source_pool_id == "equal_high:110"`), `tests/test_smc_liquidity_context_task71.py` (`source_pool_id` = swing id ở route không payload), `tests/test_smc_context.py::TestDetectLiquiditySweeps`, `tests/test_smc_sweep_linking.py`; (B2) **bản ghi có ngày trước thay đổi**: fix-progress bảng A3.118 (dòng ghi `assert canonical[swept_key] == []` → `[{… 'index': 2, …}]`, “core **cấp sweep từ level numeric**”) và §A3.142 — tức trước F06/F07 numeric **swing** level của payload vẫn cấp sweep; (B3) contract payload tại `docs/plans/smc-task-67-response.md` (“explicit pool levels là source; legacy swing-only route vẫn tương thích”); (B4) đoạn code legacy được khôi phục nguyên văn. **HEAD (fb9ea52) bị loại làm baseline** — đã kiểm: `core/smc_context.py` ở HEAD chỉ 1223 dòng (bản hiện tại ~4700) và `detect_liquidity_sweeps` ở HEAD **không có** tham số `liquidity_pools`, tức HEAD cũ hơn cả chuỗi task72 chứ không phải “ngay trước F07”.

**Thay đổi F07/r1:** thêm tham số caller-facing `pool_provenance: "canonical" | "legacy"` (mặc định `canonical`, giá trị khác ⇒ `ValueError`); nhánh `legacy` khôi phục **nguyên văn** quy tắc tiền-canonical (mọi level numeric của phía là candidate, source = swing cùng level, `pool_id` fallback dạng `kind:level`/swing id, không cổng usable). `core/smc_context.py::_smc_for_timeframe` — route Analyze/Scanner công khai — **khai báo tường minh** `pool_provenance="legacy"` cho cả `liquidity_sweeps` và `zone_link_sweeps`. Detector **không** tự suy legacy từ `records` rỗng/lỗi: canonical vẫn fail closed (control trong node mới xác nhận cùng payload đọc mặc định vẫn ra rỗng).

**Regression qua `_smc_for_timeframe` thật (+2 node, collection 123 → 125):** `test_r72_01_public_route_keeps_legacy_pool_sweeps` (fixture diagnostic 12 nến) và `test_r72_01_public_route_keeps_legacy_equal_pool_sweep` (control equal-pool). Expected tính từ fixture: pivot low idx4 level 99.5, bar 10 low 99.0 < 99.5 và close 100.2 > 99.5 ⇒ event `idx10`, `reclaimed_at = stamp(11)`; control equal: hai pivot low 99.5/99.55 (idx4/idx7) ⇒ mean `99.525`, `liquidity_sweeps` = `[(10, 99.525)]`, `zone_link_sweeps` = `[(4, 99.525), (10, 99.525)]` (route này quét từ bar 0 và excursion = 0 vì caller không truyền tick/ATR). Kèm khẳng định **không bịa canonical**: `source_pool_id` giữ dạng numeric `swing_low:99.5`/`equal_low:99.525`, `source_swing_id` rỗng/None, evidence **không có** `source_ids`/`source_pool_usable_at`.

**Refresh F07 (2026-09-11, chỉ R72-01):** `detect_liquidity_sweeps` dựng candidate canonical từ `liquidity_pools["records"]`, nối `source_pool_id` = `records.pool_id` và áp cổng A-D01 `usable_at <= reclaimed_at` (max-usable của mọi source; equality được phép). R72-01: **31 passed / 0 failed** (trước F07: 14 failed / 17 passed). **R72-01 xanh toàn bộ**; toàn bộ 14 node RED của lượt trước nay PASS:

- **7 node numeric-only / thiếu provenance** — `canonical_sweep_requires_pool_records_not_numeric_levels[buy]`/`[sell]`, `missing_pool_provenance_fails_closed[...]`×5: numeric swing level và record khiếm khuyết đều **không** cấp sweep; control legacy (không pool payload) vẫn sweep ⇒ kết quả rỗng đúng do provenance.
- **2 node actual producer→pool** — `pool_sweep_evidence_survives_future_bars`, `pool_sweep_identity_survives_rolling_index`: causation parity prefix/batch + rolling giữ nguyên, **và** dòng nối `sweep["source_pool_id"] == record["pool_id"]` nay PASS cho cả hai lượt.
- **5 node temporal** — `acceptance_source_must_be_usable_at_sweep_close[buy]`/`[sell]`, `source_usable_after_sweep_close_is_rejected[buy]`/`[sell]`, `equal_pool_usable_time_is_max_of_both_sources`.
- Cộng thêm 2 node F06/r1 (internal/provisional producer) vẫn xanh ⇒ collection R72-01 = **31 node**.

**Hai fixture cố ý thiếu `usable_at` (`acceptance_source_must_be_usable_at_sweep_close`) PASS với tư cách ca thiếu provenance**, không phải bằng chứng temporal độc lập: nguồn không khai `usable_at` ⇒ pool không có record ⇒ sweep rỗng vì thiếu provenance, chứ không phải vì so mốc thời gian. Bằng chứng temporal thật nằm ở A3-040/041/042/043 và các node producer (usable_at suy từ fixture).

**Boundary canonical/legacy đã chốt tại F07 (ghi để review):** payload **có** key `records` ⇒ canonical, chỉ `records` có quyền (numeric key bị bỏ hoàn toàn, kể cả khi `records` rỗng). Payload **không** có `records` ⇒ route numeric legacy do caller cấp: chỉ giữ **equal** level (contract task67 `test_pool_levels_are_used_when_explicitly_supplied`, giữ `source_pool_id` dạng `equal_high:110`), numeric **swing** level không cấp sweep vì không thể truy lineage từ level (A3-005 luật 3). Không có pool payload ⇒ legacy adapter path như cũ.

**Refresh F06/r1 (2026-09-11, chỉ R72-01):** producer `_confirmed_swing_points` nay phát `usable_at` cho confirmed/usable/non-provisional (TL chốt tại [fix-progress §A3.143](smc-task-72-fix-progress.md)) ⇒ pool dựng từ producer thật **có** canonical `records`. R72-01 chạy lại: **14 failed / 17 passed** (trước F06/r1: 14 failed / 15 passed; **0 RED mới**, +2 node mới). **Toàn bộ 14 node R72-01 còn RED nay thuộc F07** — phân loại **F06** ở cột *Loại RED* của các hàng tương ứng là **baseline lịch sử**, không sửa lại; owner sửa tiếp là **F07**.

- **7 node kiểm sweep từ numeric-only / thiếu provenance** — `canonical_sweep_requires_pool_records_not_numeric_levels[buy]`/`[sell]`, `missing_pool_provenance_fails_closed[record_for_other_level|no_sources|dangling_source_id|source_without_provenance_id|source_without_usable_at]`: assertion **pool** đã PASS (payload `records`/khiếm khuyết provenance không còn là bài toán pool); fail tại consumer sweep vì `detect_liquidity_sweeps` vẫn dựng candidate từ key numeric. Owner: **F07** (fix-plan F07 “Tách canonical vs legacy explicit”).
- **2 node actual producer→pool** — `pool_sweep_evidence_survives_future_bars`, `pool_sweep_identity_survives_rolling_index`: trước F06/r1 dừng ở `records` rỗng (**phần nối F06**, không phải F07 thuần); nay **đã chạy tới và PASS** toàn bộ assertion pool — producer parity (`usable_at` thêm vào tuple so sánh prefix/batch), `_pool_record_for` theo kind+lineage, `_assert_pool_record_matches_source`, `pool_id`/`source_ids`/`usable_at`/`level` giữ nguyên qua prefix/batch và rolling — rồi fail ở **dòng nối sweep**: `sweep["source_pool_id"] == record["pool_id"]` (hiện `source_pool_id` = swing ID). Owner: **F07** (link).
- **5 node temporal** — `acceptance_source_must_be_usable_at_sweep_close[buy]`/`[sell]`, `source_usable_after_sweep_close_is_rejected[buy]`/`[sell]`, `equal_pool_usable_time_is_max_of_both_sources`: cần cổng `usable_at <= reclaimed_at` (A-D01) tại sweep. Owner: **F07**.

**Node mới trong lượt F06/r1 (+2, collection 121 → 123):** `test_r72_01_internal_producer_declares_usable_at_at_confirmation_close` (seam internal), `test_r72_01_provisional_producer_declares_no_usable_at_and_no_canonical_record` (provisional ⇒ không mốc usability, pool không cấp record). Cùng lượt, node `test_r72_01_actual_swing_producer_feeds_pool_and_sweep` được **thêm** assertion producer→record `usable_at` (không thay expected cũ).

**Refresh F06 (2026-09-11, chỉ R72-01):** R72-01 chạy lại sau khi `detect_liquidity_pools` phát canonical `records`: **14 failed / 15 passed** (trước F06: 18 failed / 11 passed; **0 RED mới**). Bốn node đổi trạng thái **RED → GREEN** và hàng tương ứng ở trên đã ghi actual mới: `positive_pool_keeps_source_lineage_and_usable_time[buy]`, `[sell]`, `equal_usable_at_reclaimed_is_temporally_eligible`, `pool_identity_survives_source_permutation`. Mười bốn node còn RED, **giữ nguyên actual cũ**, phân loại điểm fail kế tiếp:

- **Còn RED nhưng assertion pool đã PASS — việc còn lại là của F07 (sweep)**: `canonical_sweep_requires_pool_records_not_numeric_levels[buy]`/`[sell]` và `missing_pool_provenance_fails_closed[record_for_other_level|no_sources|dangling_source_id|source_without_provenance_id|source_without_usable_at]` — payload `records`/thiếu provenance không còn là bài toán pool; `detect_liquidity_sweeps` vẫn dựng candidate từ key numeric. Chuyển sang canonical/legacy tường minh thuộc F07 (fix-plan F07: “Tách canonical vs legacy explicit; thiếu provenance không trở thành nguồn hợp lệ qua numeric pool fallback”).
- **Còn RED vì temporal gate — F07**: `acceptance_source_must_be_usable_at_sweep_close[buy]`/`[sell]`, `source_usable_after_sweep_close_is_rejected[buy]`/`[sell]`, `equal_pool_usable_time_is_max_of_both_sources` — cần `usable_at <= reclaimed_at` (A-D01) ở sweep; F06 không đụng cổng thời gian.
- **Còn RED vì thiếu `usable_at` trên producer thật — điểm cần TL quyết định (không phải RED do F07)**: `pool_sweep_evidence_survives_future_bars`, `pool_sweep_identity_survives_rolling_index` — toàn bộ khối causal parity (prefix/batch, rolling, lọc theo reclaim close) **PASS**; fail tại `_pool_record_for` → `assert 0 == 1` vì swing producer **không phát `usable_at`** nên F06 không cấp record (fail closed, không tự suy từ `confirmed_at`). Chi tiết tại [fix-progress §A3.142](smc-task-72-fix-progress.md). *(Đã được TL chốt tại §A3.143 và xử lý ở F06/r1 — xem **Refresh F06/r1** ở đầu mục này; hai node nay fail ở dòng nối sweep, owner F07.)*

**Refresh A3-081/r1a (2026-09-11, chỉ R72-01):** collection hiện hành của `T` = `tests/test_smc_gate72_fix_acceptance.py` có **29/29** node R72-01. Đối chiếu từng ID trong bảng này với `--collect-only`: 2 usable-at control, 2 positive-lineage param, provisional, equal usable-at, equal-before, 2 after-close param, equal-max, single-source control, equal-without-usable, actual producer, 2 canonical-record param, 5 missing-provenance param, 6 strict-excursion param, prefix/batch, rolling và permutation — **không thiếu, không thừa, không trùng**. Mọi param dùng ID thật; các hàng A3-039/040/041/043/a/043/b và A3-066/a…/e-r1 giữ Expected/Actual/F06/F07 hiện hành. Collection toàn file là **118 node / 76 hàm**; số full acceptance `69 failed / 49 passed` chưa được refresh ở lượt này (thuộc A3-084/r1).

### R72-02 — ownership theo claim time (9 node, xanh toàn bộ từ F08 2026-09-11)

**Refresh F08 (2026-09-11):** R72-02 **9 passed / 0 failed** (trước F08: 5 failed / 4 passed) và probe `test_r72_02_context_must_consider_earliest_eligible_setup_before_distance_rank` **xanh** (trước: `assert 'late' == 'early'` — zone gần thắng). Năm node RED → GREEN, giữ nguyên expected đã duyệt ở A:

| Node | Điểm fail trước | Nay |
|---|---|---|
| `test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time` | owner `"late"` (rank theo khoảng cách) | owner `"early"` |
| `test_r72_02_context_owner_follows_claim_time_under_input_permutation` | cả hai thứ tự chiếu owner `"late"` | `"early"`, `linked_zone_id "early-child"`, `claim_eligible_at stamp(13)`, bất biến qua permutation |
| `test_r72_02_context_same_time_tie_follows_stable_setup_id` | tie-break theo **zone ID** ⇒ `"beta-setup"` | tie-break theo **setup ID** ⇒ `"alpha-setup"` / `z-winner-child` |
| `test_r72_02_missing_canonical_claim_time_fails_closed[reclaimed_at]`, `[setup_available_at]` | cấp owner từ mốc còn lại | `assignments == {}` + `SWEEP_CLAIM_TIME_MISSING`; control đủ hai mốc vẫn thắng |

**Thay đổi (chỉ ở `core/`, không sửa test — hash `T` không đổi):** `core/smc_sweep_linking.py`:
- `associate_sweeps_to_zones`: rank owner = **causal claim time** `max(reclaimed_at, setup_available_at)` sớm nhất → **setup ID ổn định** → (chỉ để tất định) legacy keys. Distance/departure/time_delta **không còn** quyết định owner.
- Thêm `setup_availability_by_owner` + `setup_owner_key`: availability của **setup** chốt một lần cho cả owner (child nào đứng trước cũng không đổi nghĩa), order-independent.
- **Boundary tường minh** giữ GREEN retained: claim **gắn setup** đi theo claim time; zone **không có setup metadata** giữ nguyên thứ hạng legacy một-một (`distance_atr, departure_gap, |time_delta|, zone_id, sweep_id`) — khóa bởi `tests/test_smc_sweep_linking.py::test_one_sweep_is_assigned_to_only_one_best_zone` (`zone-departure-near`). Class được tách ở một vị trí riêng trong tuple rank nên hai nhánh không bao giờ so chéo.
- `assign_sweep_ownership`: claim **canonical** (khai `pool_id` hoặc `source_ids`) **buộc đủ** `reclaimed_at` **và** `setup_available_at`; thiếu mốc ⇒ không vào ownership + reason `SWEEP_CLAIM_TIME_MISSING`, **không** lấy mốc còn lại/alias thay thế. Claim **legacy** (không lineage) giữ nguyên compatibility default (alias + fallback một mốc) → không mất GREEN.

`core/smc_context.py::_attach_zone_sweep_links`: `setup_available_at` của claim lấy từ map theo **setup** thay vì `zone.get("available_at")` của child được chiếu. Sweep ID/level/lineage từ F06/F07 giữ nguyên; không node nào đổi điểm fail sang F09/F10 (R72-03 vẫn dừng ở `contribution_applied is True`, R72-04 vẫn ở owner replay).

| Full node ID | Rule ref | Input / timeframe / cutoff | Precond | Expected | Actual | Loại RED |
|---|---|---|---|---|---|---|
| `test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time` | R72-02, A-D02 | H1; early available 13:00 bounds `[105.2,106]`; late available 15:00 bounds `[100,110]`; sweep reclaimed 11:00, ATR 2 | cả hai claim cùng side BUY, distance ≤ `.25*ATR`, window hợp lệ, đủ provenance | `owner_setup_id == "early"` — không theo distance rank | **RED — implementation** · F08 · §A3.119 | F08 |
| `test_r72_02_context_owner_follows_claim_time_under_input_permutation` (A3-069) | R72-02, A3-069, A-D02, F08 | 2 zone claim cùng sweep: `early` (available hour 13, bounds `[105.2,106]` — xa) và `late` (hour 15, bounds `[100,110]` — gần); chạy `_attach_zone_sweep_links` với **cả hai thứ tự** `[early, late]` và `[late, early]`; đọc payload sweep được chiếu | caller phải thực hiện enumerate→assign→project: payload có `owner_setup_id`/`assignment_id`/`consumed True`/`contribution_applied True` ở cả hai thứ tự; đảo thứ tự **không** đổi owner/assignment/linked zone/claim time | owner = claim **sớm nhất** (`"early"`), `linked_zone_id == "early-child"`, `claim_eligible_at == stamp(13)` | **RED — implementation** (2026-09-11): precondition + invariance PASS nhưng cả hai thứ tự đều chiếu owner `"late"` (zone gần) cùng `linked_zone_id "late-child"`, `claim_eligible_at stamp(15)` ⇒ caller đang rank theo distance (F08) | F08 |
| `test_r72_02_opposite_side_claim_cannot_own_a_sweep` (A3-070) | R72-02, A3-070 owner eligibility | zone sai chiều `supply_zone`/`sell` bounds `[104.95,105.05]` (khe giá `0.05` tới level `105` — **gần hơn**) + zone hợp lệ `demand_zone`/`buy` bounds `[105.2,106]` (khe `0.2`); sweep `swept_low` level `105`, ATR `1.0`; chạy cả hai thứ tự | fixture: `sweep_side == "buy"`, zone sai chiều khác chiều sweep và **gần hơn** về giá (`0.05 < 0.2`) ⇒ chỉ rule chiều mới loại được nó | tầng link `associate_sweeps_to_zones` chỉ trả link cho zone hợp lệ với `distance_atr == 0.2`; caller context chiếu `owner_setup_id "right-side"`, `linked_zone_id "right-side-child"`; zone sai chiều `liquidity_sweep_linked False`, `linked_sweep_id None`; đúng như vậy ở **cả hai thứ tự** | **GREEN** (2026-09-11) — rule chiều đã đúng ở cả tầng link và caller | — |
| `test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep` (A3-071) | R72-02, A3-071 owner eligibility, **A3R3-01** | sweep level `105`, ATR `1.0`, tolerance `0.25`: band `[104,106]` (**trong**), `[105.25,106]` (**đúng biên**, khe `0.25`), `[105.26,106]` (**ngoài**, khe `0.26`); context: candle input **local** `(120, 120.5, 119.5, 120) × 20` ⇒ `TR = 1.0` mọi nến ⇒ ATR caller **1.0** (không còn ATR `2.0` của probe fixture); zone ngoài khoảng available `hour 13` (sớm hơn) vs zone trong khoảng `hour 15` | fixture: `TR` mọi nến `= 1.0` ⇒ ATR dẫn xuất độc lập `= 1.0` (TR hằng số ⇒ trung bình Wilder = chính hằng số đó, không đọc production); mỗi zone chạy **một mình** qua chính caller trước khi ghép cặp; khe `0.25` là **biên của rule đã chốt** (`tolerance_atr = 0.25`); zone ngoài khoảng có `available_at` **sớm hơn** nên chỉ rule khoảng cách mới loại được nó | helper control: trong ⇒ link `distance_atr 0.0`; đúng biên ⇒ link `distance_atr 0.25` (biên **bao gồm**); ngoài ⇒ `None`. Caller từng zone riêng (**A3-071/b**): trong ⇒ `linked_sweep_distance_atr == 0.0`, event `linked_zone_id "inside-child"`/owner `"inside"`/`consumed True`; đúng biên ⇒ `linked_sweep_distance_atr == 0.25`, event `linked_zone_id "exact-child"`/owner `"exact"`/`consumed True`; ngoài ⇒ `liquidity_sweep_linked False`, `linked_sweep_id None`, event `consumed False`/`linked_zone_id None`/không có `owner_setup_id`. Ghép cặp (**A3-071/c**: mỗi thứ tự dựng **pair mới**, không dùng lại dict đã bị caller ghi link payload): outside-early `hour 13` **sớm hơn** inside-late `hour 15` ⇒ owner `"inside-late"`, `linked_zone_id "inside-late-child"`, `consumed True`, inside `sweep_owner_setup_id "inside-late"`, outside **không** có `sweep_owner_setup_id`/`sweep_assignment_id`; hai thứ tự cho cùng `owner_setup_id`/`assignment_id`/`linked_zone_id`/`claim_eligible_at` ⇒ claim không đủ **không** thắng bằng timestamp sớm | **GREEN** (2026-09-11, A3-071/a — sau sửa A3R3-01; A3-071/b bổ sung vế event-level; A3-071/c bổ sung vế hai thứ tự): fixture context dùng **ATR thật `1.0`**, zone "ngoài" **không** link (kể cả đứng một mình), zone trong/đúng biên **được link và sở hữu sweep**, owner không đổi khi đảo thứ tự input | — |
| `test_r72_02_claim_outside_time_window_cannot_own_a_sweep` (A3-072) | R72-02, A3-072 owner eligibility | sweep idx `10`, `max_time_bars = 3` (**tham số đã có**, không chỉnh): formation_start `8` (delta `2`), `7` (delta `3` = **đúng biên**), `6` (delta `4`), và cửa sổ kết thúc trước sweep (`formation_start 0`, `departure_end_index 9`); context (window mặc định `20`): zone hết cửa sổ available `hour 13` (sớm hơn) vs zone trong cửa sổ `hour 15` | fixture: delta tính từ `sweep_index − formation_start_index`; zone ngoài cửa sổ có `available_at` **sớm hơn** nên chỉ rule cửa sổ mới loại được nó; không nới window | delta `2` ⇒ link; **đúng biên** delta `3 == max_time_bars` ⇒ **vẫn** link; delta `4` ⇒ **không** link; cửa sổ trước sweep ⇒ **không** link; context: owner `"in-window"`/`linked_zone_id "in-window-child"`, zone hết cửa sổ `liquidity_sweep_linked False`, giống nhau ở cả hai thứ tự | **GREEN** (2026-09-11) — biên cửa sổ bao gồm, ngoài cửa sổ fail closed | — |
| `test_r72_02_context_same_time_tie_follows_stable_setup_id` (A3-073) | R72-02, A3-073 tie-break, A-D02 | hai zone cùng `available_at stamp(13)`, cùng ăn sweep: `alpha-setup` (setup ID nhỏ, zone ID `z-winner-child` — lớn) và `beta-setup` (setup ID lớn, zone ID `a-loser-child` — nhỏ); chạy caller với **cả hai thứ tự** | mỗi zone link được khi chạy riêng (tie thật); link one-to-one nên đúng **1** zone mang link mỗi lượt; đảo thứ tự không đổi owner/assignment/linked zone; `claim_eligible_at == stamp(13)` | owner = setup ID ổn định `"alpha-setup"`, `linked_zone_id == "z-winner-child"` | **RED — implementation** (2026-09-11): precondition + invariance PASS nhưng caller chọn `"beta-setup"`/`a-loser-child` (theo **zone ID**) thay vì setup ID ổn định ⇒ cùng họ F08, ở chiều tie-break | F08 |
| `test_r72_02_same_time_tie_is_stable_under_claim_permutation` | A-D02 tie-break | 2 claim cùng `available 13:00`: `early/z-owner`, `late/a-nonowner`; chạy xuôi và đảo | cùng claim time, setup ID khác nhau | cả hai thứ tự ⇒ owner `"early"` | **GREEN** | — |
| `test_r72_02_missing_canonical_claim_time_fails_closed[reclaimed_at]` | A-D02 fail-closed, A3-013/A3-014 | Claim `setup/child` có `setup_available_at=stamp(13)` **và** `pool_id="pool-1"`/`source_ids=["swing-1"]`, **thiếu** `reclaimed_at` | field còn lại hợp lệ (assert `== stamp(13)`), lineage hợp lệ, `history_complete=True` tường minh; control cùng claim đủ 2 mốc ⇒ owner `setup` (A3-014) | `assignments == {}`; `SWEEP_CLAIM_TIME_MISSING` trong `reason_codes`; **không** fallback sang setup time | **RED — implementation** · F08 · §A3.119 | F08 |
| `test_r72_02_missing_canonical_claim_time_fails_closed[setup_available_at]` | A-D02 fail-closed, A3-014 | Claim `setup/child` có `reclaimed_at=stamp(11)` + lineage, **thiếu** `setup_available_at` | field còn lại hợp lệ (assert `== stamp(11)`); control đủ 2 mốc ⇒ owner `setup`, `claim_eligible_at = max(stamp(11),stamp(13)) = stamp(13)` (A3-014) | như trên; không fallback sang reclaimed time | **RED — implementation** · F08 · §A3.119 | F08 |

### R72-03 — contribution trong owner children (4 node)

**Refresh F09 (2026-09-11):** R72-03 **3 passed / 1 failed** (trước F09: 2 failed / 2 passed) và probe `test_r72_03_nonowner_child_cannot_take_contribution_slot` **xanh** (trước: `sum(contribution_applied) == 1` nhận `0`).

**Thay đổi (chỉ `core/`, không sửa test — hash `T` không đổi):** `core/smc_sweep_linking.py::assign_sweep_ownership` chọn `contribution_winner[sweep_id]` **trong owner children** (`claim.setup_id == assignment.owner_setup_id`) thay vì trên **toàn bộ** `normalized_claims`. Tie-break giữ nguyên `(zone_id, visit_id, input order)` — **không** thêm priority mới, **không** hạ cờ `assignment.contribution_applied`, **không** thêm bất biến assignment-flag↔tổng-claim (chưa chốt). Nguyên nhân gốc: winner chọn toàn cục nên `a-nonowner` (zone ID nhỏ hơn) thắng khoá, rồi vế owner chặn luôn cả owner ⇒ **cả hai** claim `contribution_applied False` (tổng 0) dù assignment báo `True` — xem phân tích [§A3.120](smc-task-72-fix-progress.md).

| Node | Trước F09 | Nay |
|---|---|---|
| `test_r72_03_acceptance_contribution_is_selected_within_owner_children` | owner `"early"` PASS, non-owner `False` PASS, fail tại `owner_claim["contribution_applied"] is True` (`assert False is True`) | **GREEN** — assertions phía sau nay chạy: T:589 tổng trên claims `== 1`, T:590 claim được credit là `"early"` |
| `test_r72_03_duplicate_owner_children_keep_one_contribution_under_permutation` | GREEN | GREEN (tổng `== 1` giữ nguyên; winner là `child-a` bất kể thứ tự) |
| `test_r72_03_contribution_is_counted_per_sweep_not_per_list` | GREEN | GREEN (`{"sweep-a": 1, "sweep-b": 1}`, con credit `child-a`/`child-d`) |
| `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | RED — `KeyError: 'sweep'` (assignment history-only bị mất) | **RED — F10**, giữ nguyên điểm fail (`restored["assignments"] == {}`); vế “current contribution 0” vẫn PASS. Không sửa ké ở F09 |

| Full node ID | Rule ref | Input / timeframe / cutoff | Precond | Expected | Actual | Loại RED |
|---|---|---|---|---|---|---|
| `test_r72_03_acceptance_contribution_is_selected_within_owner_children` | R72-03, A-D03, A3-075 | claim `early/z-owner` 13:00; claim `late/a-nonowner` 15:00; `"a-nonowner" < "z-owner"` (non-owner có zone ID **nhỏ hơn**) | non-owner ID nhỏ hơn **không** được chiếm contribution slot | owner `"early"`; `non_owner_claim["contribution_applied"] is False`; `owner_claim["contribution_applied"] is True`; tổng `== 1`; claim được cấp có `setup_id == "early"` | **RED — implementation** (2026-09-11, A3-075): PASS `owner_setup_id == "early"` và `non_owner … is False`, nhưng **cả hai** claim đều `contribution_applied False` ⇒ dừng ở `owner_claim … is True`; probe cùng fixture: tổng `0`, dù `assignments[...]["contribution_applied"] is True` ⇒ slot chọn trên toàn bộ children nên non-owner ID nhỏ chiếm khoá (F09) | F09 |
| `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | A-D03, A3-076 | Lần 1: claim `owner/child` 13:00. Lần 2: `claims=[]`, `assignment_history=lần1`, `history_complete=True` | owner chỉ còn trong history (không có child hiện tại) | `restored["claims"] == []` (current contribution **0**); `restored["assignments"]["sweep"] == first["assignments"]["sweep"]` (giữ owner **và** `assignment_id`/`claim_eligible_at`/`assigned_at`); `owner_setup_id == "owner"` | **RED — implementation** (2026-09-11, A3-076): PASS `claims == []`; RED ở assert assignment: `restored["assignments"] == {}` ⇒ assignment history-only bị **mất** (KeyError `'sweep'`) — F10. Vế "không chuyển cho late child" đã đủ ở `test_r72_04_assignment_survives_json_restore_with_late_only_window` (GREEN) | F10 |
| `test_r72_03_duplicate_owner_children_keep_one_contribution_under_permutation` | A-D03 dedupe | 3 claim: `owner/child-b`, `owner/child-a` ×2; chạy xuôi và đảo | duplicate zone ID cùng owner | tổng contribution `== 1`; mọi claim `setup_id == "owner"` | **GREEN** | — |
| `test_r72_03_contribution_is_counted_per_sweep_not_per_list` (A3-074) | R72-03, A3-074 per-sweep | 5 claim của **cùng owner** `owner-1` trên **2 sweep độc lập**: `sweep-a` ← `child-b`, `child-a` (`family="fvg"`), `child-c` (`family="ob"` + `note` metadata); `sweep-b` ← `child-d`, `child-e` (`family="fvg"`); cùng claim time | duplicate/multi-family/metadata không được tăng hoặc làm mất contribution; rule là **theo từng sweep**, không phải cap toàn danh sách | mỗi sweep đúng **1** contribution ⇒ `per_sweep == {"sweep-a": 1, "sweep-b": 1}`, tổng danh sách **2**; owner mỗi sweep `owner-1`; con được credit là con **đầu tiên theo zone ID** (`child-a`, `child-d`); đảo thứ tự input ⇒ per-sweep count và con credit **không đổi** | **GREEN** (2026-09-11) — contribution per-sweep đã đúng, không cap toàn danh sách | — |

### R72-04 — consumed/replay/history (6 node, xanh toàn bộ từ F10 2026-09-11)

**Refresh F10 (2026-09-11):** R72-04 **6 passed / 0 failed** (trước F10: 4 failed / 2 passed); cùng lượt, node history-only của R72-03 (`test_r72_03_historical_owner_without_current_child_gets_zero_contribution`) **xanh**, probe `test_r72_04_context_must_not_reassign_already_consumed_sweep` **xanh**. **Toàn bộ acceptance 125/125 và 16/16 reviewer probes GREEN.**

| Node | Actual trước F10 | Nay |
|---|---|---|
| `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` | `'later-owner' == 'original-owner'` (T:602) | GREEN — caller dùng consumption đã ghi làm authority |
| `test_r72_04_context_repeat_after_json_restore_keeps_assignment` | `'later-owner' == 'original-owner'` (T:2271) | GREEN — owner/`assignment_id`/`linked_zone_id`/`claim_eligible_at` giữ nguyên sau JSON restore |
| `test_r72_04_same_pool_observation_cannot_bypass_consumption` | `'later' == 'original'` (T:2353) | GREEN — observation mới của cùng `pool_id`/`source_ids` giữ owner + `assignment_id`; control pool mới (`pool-2`) vẫn độc lập |
| `test_r72_04_conflicting_assignment_history_fails_closed` | `{'sweep': {...}} == {}` (T:2413) | GREEN — fail closed + reason nhóm conflict; không báo nhầm `SWEEP_OWNER_HISTORY_INCOMPLETE` |
| `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | `KeyError: 'sweep'` (T:2229) | GREEN — assignment history-only sống sót, `claims == []` |
| `test_r72_04_assignment_survives_json_restore_with_late_only_window`, `test_r72_04_incomplete_history_returns_explicit_reason` | GREEN | GREEN (giữ nguyên) |

**Refresh C-R1/C-R2 (2026-09-12, sau review checkpoint C §A3.151):** hai lỗi contract mà bộ test lúc trình C **không** phủ đã được tái lập bằng diagnostic read-only, sửa, và khóa bằng **2 node regression mới** (collection **125 → 127**; toàn bộ acceptance **127/127**, probes **16/16**).

| Finding | Tái lập (actual trước sửa) | Sửa | Node khóa |
|---|---|---|---|
| **C-R1** canonical lineage/time mất tại caller ⇒ cùng pool cấp owner mới | `attach([zone old/original 13])` rồi thêm observation `sweep-later` cùng `pool-A`/`source-A` và attach `zone new/later 15`: sweep cũ `original`/`smca-2c5edcc5aad86fd41d5a`, sweep-later **`later`/`smca-31db2bd735ee7bdacf49`** (history nằm ngay trong payload) | `_attach_zone_sweep_links` truyền canonical `pool_id`/`source_ids` + `reclaimed_at` thật vào claim (chỉ khi sweep có canonical `source_ids`; legacy giữ nguyên §A3.146) | `test_r72_04_caller_same_pool_observation_keeps_consumption` — nay `sweep-later` giữ `original` + cùng `assignment_id`; `late_zone.sweep_contribution_applied is False`; JSON restore giữa hai lượt; control `pool-B` vẫn độc lập |
| **C-R2** history mâu thuẫn cùng pool phụ thuộc insertion order | hai history `old-1`/`old-2` cùng `pool-A`/`source-A` nhưng owner `first`/`second`, assignment `id-first`/`id-second`: thứ tự xuôi ⇒ owner `first`, đảo ⇒ owner `second`, `reason_codes == []` cả hai | `assign_sweep_ownership` kiểm consistency **mọi** history cùng sweep_id **hoặc** cùng lineage trước khi restore/assign (kể cả khi có exact `sweep_id` match) ⇒ mâu thuẫn ⇒ fail closed + `SWEEP_OWNER_HISTORY_CONFLICT` | `test_r72_04_conflicting_history_is_order_independent_and_fails_closed` — hai thứ tự đều `assignments == {}` + reason conflict (không báo nhầm `…_HISTORY_INCOMPLETE`); control nhiều observation **nhất quán** vẫn cấp assignment, `reason_codes == []` |
**Refresh C-R1 (phần còn lại) + chốt G1/G2 (2026-09-12, sau review C lần2 §A3.153):** canonical sweep thiếu `reclaimed_at` nhưng còn `time` **vẫn được cấp owner** ở caller cũ (`linked_sweep.get('reclaimed_at', linked_sweep.get('time',''))` thay mốc thiếu bằng open time; diagnostic: `consumed=True`, `owner_setup_id=owner`, `assignment_id=smca-371aca1fa03ccf132f88`, `claim_eligible_at=stamp(13)` dù sweep không có `reclaimed_at`). Sửa: caller **chỉ** truyền `reclaimed_at` thật, **không** set key khi sweep không khai (để `.get()` của nhánh legacy không bị `None` chặn) ⇒ canonical thiếu mốc ⇒ `SWEEP_CLAIM_TIME_MISSING`, không owner/consumption/contribution. Node khóa: `test_r72_04_caller_canonical_claim_without_reclaim_time_gets_no_owner` (collection **127 → 128**) — thiếu mốc ⇒ sweep `consumed is not True`/không owner/không contribution (link vẫn có, chỉ ownership bị giữ lại); **control đủ mốc** ⇒ owner + contribution `True`; **control legacy** (không lineage, chỉ còn `time`) ⇒ vẫn cấp owner (alias chỉ sống ở nhánh legacy tường minh).

**G1 — đã chốt:** availability tổng hợp của setup = **min instant hợp lệ** trong các child cùng setup (setup được biết khi child đầu tiên available); child ra đời muộn không dời mốc; không yêu cầu mọi child cùng `available_at`. Không đồng nghĩa được lấy `reclaimed_at` thay setup availability — canonical thiếu mốc vẫn fail closed. Không mở service/model availability mới ở task72.

**G2 — đã chốt và đính chính mô tả:** thứ hạng thực tế là **completeness/claim time trước, class sau**; setup-scoped chỉ được ưu tiên khi **đồng hạng** claim instant với zone-only (đo trực tiếp: setup stamp15 đấu zone-only stamp12 ⇒ zone-only thắng; stamp15 ⇒ setup thắng; stamp17 ⇒ setup thắng). Mô tả cũ “setup thắng bất kể claim time” là **sai**. Pure setup tie vẫn theo stable setup ID; legacy giữ tie-break đã cam kết. Không đổi thuật toán class.

**Thay đổi F10 (chỉ `core/`, không sửa test — hash `T` không đổi ở lượt F10):**

- `core/smc_sweep_linking.py::SweepAssignment` mang thêm `pool_id`/`source_ids` (**list**, không tuple — để dict `to_dict()` sống qua JSON round-trip) = lineage của lần cấp owner.
- `assign_sweep_ownership`: tra history theo **sweep ID trước, rồi theo causal pool lineage** (không theo sweep/index/thời điểm/level) ⇒ observation mới cùng pool không né consumption, pool mới vẫn độc lập; record **không thể tôn trọng** ⇒ **fail closed** + `SWEEP_OWNER_HISTORY_CONFLICT` (nhóm conflict, không reset history rồi cấp owner mới, không báo nhầm nhóm `…_HISTORY_INCOMPLETE`); owner chỉ còn trong **history** vẫn phát assignment đã biết.
- `associate_sweeps_to_zones`: sweep **đã consumed** chỉ được link lại bởi **chính setup sở hữu** — “sweep đã consumed không thành claim mới cho setup khác”.
- `core/smc_context.py::_attach_zone_sweep_links`: dựng `assignment_history` từ chính payload sweep đã consumed (kèm `pool_id` **chỉ khi** sweep có canonical `source_ids`; legacy numeric pool id **không** được coi là identity) và truyền `history_complete=True` tường minh; giữ `linked_zone_id` đã biết khi cửa sổ hiện tại không còn child; `mark_sweeps_consumed` đặt `contribution_applied=False` cho sweep chỉ còn owner trong history (không còn child hiện tại ⇒ current contribution 0).

| Full node ID | Rule ref | Input / timeframe / cutoff | Precond | Expected | Actual | Loại RED |
|---|---|---|---|---|---|---|
| `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` | R72-04, A-D06 | attach zone `old-child/original-owner` 13:00 → prior; attach lại `new-child/later-owner` 15:00, cùng sweep | `prior["consumed"] is True` (assert trước) | `owner_setup_id` và `assignment_id` giữ nguyên như prior | **RED — implementation** · F10 · §A3.121 | F10 |
| `test_r72_04_assignment_survives_json_restore_with_late_only_window` | R72-04, A-D06 | Lần 1: claim `original/child` 13:00 → JSON dump/load. Lần 2: window chỉ có `later/late-child` 15:00, `history_complete=True` | history round-trip qua JSON còn nguyên | owner `"original"`; claim late `contribution_applied is False` | **GREEN** | — |
| `test_r72_04_context_repeat_after_json_restore_keeps_assignment` (A3-078) | R72-04, A3-078 repeat/restore, A3-046 | lượt 1: `_attach_zone_sweep_links` với `old-child/original-owner` 13:00 → payload sweep có owner/`assignment_id`/`consumed True`; **JSON restore** `json.loads(json.dumps(sweeps))` (khác ca in-RAM của A3-004); lượt 2: attach `new-child/later-owner` 15:00 trên payload đã restore | payload restore là **bản độc lập** (`restored is not sweeps`) và giữ nguyên owner/`assignment_id`/`consumed` **trước** lượt 2 | owner/`assignment_id`/`linked_zone_id`/`claim_eligible_at` giữ đúng như lượt 1; `consumed` vẫn `True`; setup muộn **không** lấy owner hay assignment mới | **RED — implementation** (2026-09-11): precondition + restore PASS nhưng lượt 2 đổi owner thành `"later-owner"` với `assignment_id` mới và `linked_zone_id` mới ⇒ caller không tôn trọng assignment đã ghi sau restore (F10) | F10 |
| `test_r72_04_incomplete_history_returns_explicit_reason` | R72-04 fail-closed, A3-012 | claim `late/child` 15:00 **đầy đủ canonical** (`reclaimed_at=stamp(11)`, `setup_available_at=stamp(15)`, `pool_id="pool-1"`, `source_ids=["swing-1"]`), `history_complete=False`, không truyền history | canonical caller truyền cờ tường minh; claim không thiếu field nào khác (A-D02/A-D06) | `assignments == {}`; `reason_codes == ["SWEEP_OWNER_HISTORY_INCOMPLETE"]` (đúng một reason); control cùng claim với `history_complete=True` ⇒ có owner `late` (A3-012) | **GREEN** | — |
| `test_r72_04_same_pool_observation_cannot_bypass_consumption` | R72-04, A-D06, A3-045, A3-046, A3-047 | lượt 1 (A3-045): `original/child` 13:00 + `pool_id="pool-1"`/`source_ids=["swing-1"]`, observation index `7`; lượt 2 (A3-046) = **observation MỚI của cùng causal pool**: `sweep_id="sweep-later"`, `reclaimed_at=stamp(17)`, index `99`, **giữ** `pool_id`/`source_ids`; **control (A3-047)** = pool **mới thật**: `sweep_id="sweep-new"`, `reclaimed_at=stamp(21)`, index `199`, `pool_id="pool-2"`, `source_ids=["swing-2"]`, cùng `restored_history` | lượt 1 đã xác minh (owner `original`, `assignment_id` không rỗng, `claim_eligible_at == max(stamp(11),stamp(13))`, JSON round-trip); control: `pool_id`/`source_ids`/`sweep_id` **khác** lượt 1, hai mốc claim hợp lệ (`reclaimed_at=stamp(21)`, `setup_available_at=stamp(19)`) | (A3-046) `assignments["sweep-later"]["owner_setup_id"] == "original"` và cùng `assignment_id`, late contribution `False` — hiện RED (F10); (A3-047) control **không** bị khóa nhầm: `reason_codes == []`, `assignments["sweep-new"]["owner_setup_id"] == "new-setup"`, `contribution_applied is True` | **RED — implementation** · F10 · §A3.121 | F10 |
| `test_r72_04_conflicting_assignment_history_fails_closed` | R72-04, A-D06 fail-closed, A3-048 | claim `late/child` 15:00 **đầy đủ canonical** (`reclaimed_at=stamp(11)`, `setup_available_at=stamp(15)`, `pool_id="pool-1"`, `source_ids=["swing-1"]`, `index=3`); history **mâu thuẫn**: `{"sweep": {"sweep_id": "sweep", "owner_setup_id": "original"}}` (thiếu `assignment_id`/timestamps) | claim không thiếu field nào (không fail vì thiếu fixture timestamp); history record không thể được tôn trọng | **fail closed**: `assignments == {}` (không cấp lại owner cho sweep) và `reason_codes` **không rỗng**; **A3-077** bổ sung vế phân nhóm: `"SWEEP_OWNER_HISTORY_INCOMPLETE" not in reason_codes` (fixture khai `history_complete=True` và có record ⇒ không được báo nhầm nhóm thiếu) | **RED — implementation** (F10): sweep bị **cấp lại** cho `late` (`owner_setup_id "late"`, `assignment_id` mới, `contribution_applied True`) và `reason_codes == []`; vế phân nhóm PASS | F10 |

### R72-05 — terminal D1 consumer (9 node)

| Full node ID | Rule ref | Input / timeframe / cutoff | Precond | Expected | Actual | Loại RED |
|---|---|---|---|---|---|---|
| `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[buy]` | R72-05, A-D04 | D1 4 nến: outside, touch, reaction, close `99` phá vùng; cutoff `as_of=stamp(4*24)` | visit đã `completed_reacted` trước khi vùng broken | `lifecycle_broken is True`; `evidence["valid"] is False`; `score == 0` | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[sell]` | R72-05, A-D04 | Mirror SELL, cùng cutoff | như trên | như trên | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[buy]` | R72-05, A-D04 | serialized `state.to_dict()` + override `lifecycle_status="invalid"`, legacy `d1_reaction=True`, `proximity=True`, `broken=False`; `as_of=stamp(4*24)` | canonical invalid thắng legacy | `valid is False`; `score == 0` | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[sell]` | R72-05, A-D04 | Mirror SELL | như trên | như trên | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_05_cutoff_equal_invalidated_at_is_terminal[buy]` | A-D04 cutoff bằng terminal, A3-049, A3-050 | D1 **4 nến**: outside, touch `(105,111,105,108)`, **exit+reaction** `(112,114,111,113)`, invalidation `(99,100,98,99)`; cutoff `as_of == state.invalidated_at` | prefix = 3 nến đầu có visit `completed_reacted` (`reacted_at == 2026-09-04T00:00Z`, close nến idx2) ⇒ có reaction **thật** trước terminal; `invalidated_at == 2026-09-05T00:00Z` (close idx3) | **prefix (A3-049)**: tại `as_of = 2026-09-04T00:00Z` ⇒ `valid is True`, `score > 0`, `zone_id == "equal-terminal"`, `source_visit_id == prefix_visit.visit_id`; **tại terminal (A3-050)**: `invalidated_at == start+4d`, `visits[0].reacted_at == prefix_cutoff` (**giữ nguyên**), `valid is False`, `score == 0`, và reject **không** vì thiếu reaction (`"D1_REACTION_NOT_COMPLETED_REACTED" not in reason_codes`) — hiện RED (implementation, F05) vì consumer vẫn trả `valid=True/score=1.0` tại cutoff bằng `invalidated_at` | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_05_cutoff_equal_invalidated_at_is_terminal[sell]` | A-D04 cutoff bằng terminal, A3-049, A3-050 | Mirror SELL: outside, touch `(101,105,99,102)`, exit+reaction `(98,99,96,97)`, invalidation `(111,112,109,111)` | như trên | như trên | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_05_cutoff_equal_expired_at_is_terminal[buy]` | A-D04 cutoff bằng terminal, A3-051 | D1 23 nến `_terminal_candles(buy, 20)` (touch idx19, **exit+reaction idx20**, hết lifetime ở idx21 **không** invalidation); cutoff `as_of == state.expired_at` | prefix 21 nến: visit `completed_reacted`, `reacted_at == 2026-09-22T00:00Z` (close idx20) và evidence tại chính close đó `valid True`/`score > 0` ⇒ không thể pass vì stale/no-reaction/cutoff-trước-reaction; `expiry_index == 21` | tại `expired_at == 2026-09-23T00:00Z` (close idx21): `valid is False`, `score == 0`; `visits[0].reacted_at` **giữ nguyên** `2026-09-22T00:00Z`; reject không vì thiếu reaction (`"D1_REACTION_NOT_COMPLETED_REACTED" not in reason_codes`) — hiện **GREEN** (reason `D1_REACTION_STALE`) | **GREEN** | — |
| `test_r72_05_cutoff_equal_expired_at_is_terminal[sell]` | A-D04 cutoff bằng terminal, A3-051 | Mirror SELL (cùng `_terminal_candles(sell, 20)`) | như trên | như trên | **GREEN** | — |

### R72-06 — terminal/reaction order (20 node)

| Full node ID | Rule ref | Input / timeframe / cutoff | Precond | Expected | Actual | Loại RED |
|---|---|---|---|---|---|---|
| `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[buy]` | R72-06, A-D05 | D1 22 nến; idx19 open visit, idx20 exit `(110.2,110.22,110.15,110.2)`, idx21 candle reaction; prefix = 21 nến | lifetime D1 20; exit ngoài tolerance `.1` nhưng chưa đạt `.25 ATR` | prefix: `completed_unreacted`; full: `lifecycle_expired` + `expiry_index==21`, `reacted_at is None`, `completed_unreacted` | **GREEN** (F04 sửa 2026-09-11 — trước đó RED F04, §A3.123) | — |
| `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[sell]` | R72-06, A-D05 | Mirror SELL, cùng cadence | như trên | như trên | **GREEN** (F04 sửa 2026-09-11 — trước đó RED F04, §A3.123) | — |
| `test_r72_06_terminal_order_before_reaction_is_explicit[20-buy]` | A-D05, A3-030 | `_terminal_candles(buy, 20)` — D1 23 nến, idx20 vừa exit vừa reaction; thêm **prefix 21 nến** (kết thúc ở idx20) | reaction index = 20 < terminal 21; close idx20 = `2026-09-22T00:00Z` | `reacted_at == "2026-09-22T00:00:00+00:00"` (đúng thời điểm, không chỉ non-None) cho **cả prefix và full**; `completed_reacted`; prefix `lifecycle_expired is False` ⇒ append candle terminal **không đổi** thời điểm/lịch sử | **GREEN** | — |
| `test_r72_06_terminal_order_before_reaction_is_explicit[20-sell]` | A-D05, A3-030 | Mirror SELL, cùng prefix/full | như trên | như trên | **GREEN** | — |
| `test_r72_06_terminal_order_before_reaction_is_explicit[21-buy]` | A-D05, A3-031 | `_terminal_candles(buy, 21)` — reaction tại đúng candle terminal | **vùng thật sự được vào/rời trước terminal** (assert `entered_at` = close idx19, `exited_at` = close idx20, `bars_spent_inside ≥ 1`) ⇒ không pass vì "chưa từng vào vùng"; `reaction_index = 21 = expiry_index` | `lifecycle_expired is True`; `expiry_index == 21`; `expired_at == "2026-09-23T00:00:00+00:00"` (close idx21); `reacted_at is None`; `completed_unreacted` | **GREEN** (F04 sửa 2026-09-11 — trước đó RED F04, §A3.123) | — |
| `test_r72_06_terminal_order_before_reaction_is_explicit[21-sell]` | A-D05, A3-031 | Mirror SELL, cùng khóa entry/exit + terminal | như trên | như trên | **GREEN** (F04 sửa 2026-09-11 — trước đó RED F04, §A3.123) | — |
| `test_r72_06_terminal_order_before_reaction_is_explicit[22-buy]` | A-D05, A3-031/A3-032 | `_terminal_candles(buy, 22)` — reaction sau terminal | như trên (cùng nhánh assertion với [21]); `reaction_index = 22 > expiry_index = 21`; thêm so **bỏ candle sau terminal** (`[:22]`) | như trên (terminal vẫn ở index 21); `trimmed.visits[0] == visit` ⇒ candle sau terminal **không** đổi lịch sử (A3-032) | **GREEN** (F04 sửa 2026-09-11 — trước đó RED F04, §A3.123) | — |
| `test_r72_06_terminal_order_before_reaction_is_explicit[22-sell]` | A-D05, A3-031/A3-032 | Mirror SELL | như trên | như trên | **GREEN** (F04 sửa 2026-09-11 — trước đó RED F04, §A3.123) | — |
| `test_r72_06_h4_reaction_before_terminal_is_retained[buy]` | R72-06, A-D05, A3-033, A3-034 | **H4 mới**: 33 nến bước **4h** (`_h4_terminal_candles`), start `2026-09-01T00:00Z`; touch idx29, exit **idx30 có reaction**, terminal idx31, sau idx32; zone `[100,110]`, `tick=.1`, `ATR=1` | H4 lifetime = 30 bars ⇒ age30 (idx30) chưa terminal; exit ngoài tolerance `.1` và reaction đạt (`close ≥ 110.25`); validator H4 + assert cadence 4h | `entered_at == 2026-09-06T00:00Z` (close idx29); `exited_at == reacted_at == 2026-09-06T04:00Z` (close idx30 — exit và reaction cùng close, chưa terminal); `completed_reacted`; `lifecycle_expired is True`; `expiry_index == 31`; `expired_at == 2026-09-06T08:00Z` (close idx31) | **GREEN** | — |
| `test_r72_06_h4_reaction_before_terminal_is_retained[sell]` | R72-06, A-D05, A3-033, A3-034 | Mirror SELL (mirror quanh 210, cùng 33 nến bước 4h) | như trên (exit dưới vùng mở rộng, reaction `close ≤ 99.75`) | như trên | **GREEN** | — |
| `test_r72_06_h4_reaction_at_terminal_is_blocked[buy]` | R72-06, A-D05, A3-033, A3-035 | **H4**: `_h4_terminal_candles(buy, 31)` — reaction đặt đúng candle terminal idx31 (33 nến bước 4h) | reaction index 31 **= `expiry_index`**; vùng thật sự được vào/rời trước đó (assert entry/exit/bars) | `entered_at == 2026-09-06T00:00Z`; `exited_at == 2026-09-06T04:00Z`; `bars_spent_inside ≥ 1`; `lifecycle_expired is True`; `expiry_index == 31`; `expired_at == 2026-09-06T08:00Z`; **`reacted_at is None`**; `completed_unreacted` | **GREEN** (F04 sửa 2026-09-11 — trước đó RED F04, §A3.123) | — |
| `test_r72_06_h4_reaction_at_terminal_is_blocked[sell]` | R72-06, A-D05, A3-033, A3-035 | Mirror SELL, cùng 33 nến bước 4h | như trên | như trên | **GREEN** (F04 sửa 2026-09-11 — trước đó RED F04, §A3.123) | — |
| `test_r72_06_h4_reaction_after_terminal_is_blocked[buy]` | R72-06, A-D05, A3-033, A3-036 | **H4**: `_h4_terminal_candles(buy, 32)` — reaction đặt **sau** candle terminal (idx32), terminal vẫn ở idx31 | `reaction_index = 32 > expiry_index = 31`; vùng thật sự được vào/rời trước đó; bỏ candle sau terminal (`[:32]`) cho cùng visit | `entered_at == 2026-09-06T00:00Z`; `exited_at == 2026-09-06T04:00Z`; `bars_spent_inside ≥ 1`; `lifecycle_expired is True`; `expiry_index == 31`; `expired_at == 2026-09-06T08:00Z`; **`reacted_at is None`**; `completed_unreacted`; `trimmed.visits[0] == visit` | **GREEN** (F04 sửa 2026-09-11 — trước đó RED F04, §A3.123) | — |
| `test_r72_06_h4_reaction_after_terminal_is_blocked[sell]` | R72-06, A-D05, A3-033, A3-036 | Mirror SELL, cùng 33 nến bước 4h | như trên | như trên | **GREEN** (F04 sửa 2026-09-11 — trước đó RED F04, §A3.123) | — |
| `test_r72_06_terminal_state_survives_enrich_restore_enrich[expired-buy]` | R72-06, A3-038, §2029 | D1 23 nến `_terminal_candles(buy, 20)` (reaction age20, hết lifetime ở idx21 **không** invalidation); item `tick_size=.1`, `atr_current=1` | enrich → `json.dumps/loads` → enrich lại; reaction trước terminal `2026-09-22T00:00Z`; terminal `expired_at == 2026-09-23T00:00Z` | `zone_id` không đổi; `lifecycle_status == "expired"` ở **cả hai** lượt enrich; `usable is False`; `expired_at == 2026-09-23T00:00Z`, `expiry_index == 21`; `visits` lượt 2 **giống** lượt 1 (reaction `2026-09-22T00:00Z` giữ nguyên, không reaction mới); D1 `valid is False`, `score == 0` | **GREEN** (F03 sửa 2026-09-11 — trước đó RED F03, §A3.124/§A3.130) | — |
| `test_r72_06_terminal_state_survives_enrich_restore_enrich[expired-sell]` | R72-06, A3-038 | Mirror SELL | như trên | như trên | **GREEN** (F03 sửa 2026-09-11 — trước đó RED F03, §A3.124/§A3.130) | — |
| `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-buy]` | R72-06, A3-038, R72-08 | D1 23 nến: touch idx19, reaction idx20, **invalidation idx21** `(99,100,98,99)` (thay expiry); cùng chuỗi enrich→restore→enrich | invalidation trùng mốc hết lifetime nên thắng expiry; reaction **trước** terminal phải được giữ | `zone_id` không đổi; `lifecycle_status == "invalid"` (≠ `confirmed`) ở cả hai lượt; `usable is False`; `invalidated_at == 2026-09-23T00:00Z`, `invalidation_index == 21`, `lifecycle_expired is False`; `visits` giữ nguyên; D1 `valid is False`/`score == 0` | **GREEN** (F03 sửa 2026-09-11 — trước đó RED F03, §A3.124/§A3.130) | — |
| `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-sell]` | R72-06, A3-038, R72-08 | Mirror SELL: touch `(101,105,99,102)`, reaction `(98,99,96,97)`, invalidation idx21 `(111,112,109,111)` | như trên | như trên | **GREEN** (F03 sửa 2026-09-11 — trước đó RED F03, §A3.124/§A3.130) | — |
| `test_r72_06_invalidation_precedes_expiry_and_reaction[buy]` | A-D05 invalidation ưu tiên, A3-037 | D1 22 nến; touch idx19 `(109,110,105,109)`; exit idx20 `(110.2,110.22,110.15,110.2)` (chưa đủ reaction); **invalidation idx21** `(99,100,98,99)` = candle hết lifetime | invalidation nằm trong follow-through window `20…23` và trùng mốc expiry (age21 > lifetime 20) | `lifecycle_broken is True`; `invalidation_index == 21`; `invalidated_at == 2026-09-23T00:00Z` (close idx21); **`expiry_index is None`**; **`lifecycle_expired is False`** (invalidation thắng); visit `entered_at == 2026-09-21T00:00Z`, `exited_at == 2026-09-22T00:00Z`, `completed_unreacted`, `reacted_at is None` | **GREEN** | — |
| `test_r72_06_invalidation_precedes_expiry_and_reaction[sell]` | A-D05 invalidation ưu tiên, A3-037 | Mirror SELL: touch `(101,105,99,102)`, exit `(99.8,99.85,99.78,99.8)`, invalidation idx21 `(111,112,109,111)` | như trên | như trên | **GREEN** | — |

### R72-07 — metadata source và unknown (21 node)

| Full node ID | Rule ref | Input / timeframe / cutoff | Precond | Expected | Actual | Loại RED |
|---|---|---|---|---|---|---|
| `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[buy]` | R72-07, A-D07 | H1 2 nến; item không có tick; `enrich_zones(..., tick_size=0.1)`; `atr_current=1`; close `99.98` | zone `[100,110]`; buffer hợp lệ `.1` nên close còn trong ngưỡng | `invalidation_buffer ≈ 0.1`; `lifecycle_broken is False` | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[sell]` | R72-07, A-D07 | Mirror SELL | như trên | như trên | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_item_and_argument_tick_sources_have_parity[buy]` | A-D07 parity, A3-019 | H1 2 nến `[(112,114,111,113),(100,101,99.95,99.98)]`; `atr_current=1`; 3 biến thể: item-only `.1` (item không có tick ⇒ assert vắng), argument-only `.1`, equal-both `.1` | cả ba khai báo tick khác nhau thật; close `99.98` nằm trong buffer `.1` nên zone còn live | mỗi biến thể **tuyệt đối**: `invalidation_buffer ≈ 0.1` (= `max(tick,0.05*ATR)` tính từ fixture), `lifecycle_broken is False`, `lifecycle_status == "confirmed"` — không chỉ so ba kết quả với nhau | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_item_and_argument_tick_sources_have_parity[sell]` | A-D07 parity, A3-019 | Mirror SELL quanh 210, cùng cadence | như trên | như trên | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]` | R72-07, A3-007, A3-017 | H1 2 nến `[(112,114,111,113),(102,103,101,102.5)]`; item `atr_current=NaN`, `tick_size=0.1` **hợp lệ**, close `102.5` trong zone `[100,110]` | field còn lại hợp lệ (assert `tick_size == 0.1`); `math.isnan(atr_current)`; chưa terminal | `metadata_state=="unknown"`; `metadata_reason` chuỗi không rỗng; `usable is False`; `invalidation_buffer is None` (không `0`/NaN); giữ `confirmed`/`broken is False`. Nonfinite **tách** khỏi missing (A3-015/A3-016) | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[tick_size]` | R72-07, A3-007, A3-017 | item `tick_size=NaN`, `atr_current=1` **hợp lệ** | field còn lại hợp lệ (assert `atr_current == 1`); `math.isnan(tick_size)` | như trên | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_conflicting_same_scope_tick_sources_fail_closed` | R72-07, A-D07, A3-018 | H1 2 nến `[(112,114,111,113),(102,103,101,102.5)]`; item tick `0.2` vs argument tick `0.1` cùng scope, `atr_current=1`, close `102.5` trong zone `[100,110]` | hai nguồn tick khai báo **mâu thuẫn** (`0.2 != 0.1`), ATR hợp lệ, chưa terminal | `metadata_state=="unknown"`; `metadata_reason` chuỗi không rỗng; `usable is False`; `invalidation_buffer is None` (không dùng cả `0.1` lẫn `0.2`); giữ `lifecycle_status=="confirmed"`/`broken is False` — unknown là **data-quality**, không phải lifecycle status | **RED — implementation** · F02 · §A3.124 | F02 |
| `test_r72_07_missing_canonical_atr_is_unknown_and_unusable` | R72-07, A3-007, A3-015 | H1 2 nến `[(112,114,111,113),(102,103,101,102.5)]`; item có `tick_size=0.1`, `atr_current=None`, `available_at=stamp(1)`, close `102.5` trong zone `[100,110]` | tick hợp lệ (`== 0.1`); ATR thiếu; `low < close < high` (chưa terminal, `lifecycle_expired is False`); control cùng fixture với `atr_current=1` ⇒ `invalidation_buffer ≈ 0.1`, `confirmed`, `broken=False` | `metadata_state=="unknown"`; `metadata_reason` là chuỗi không rỗng; `usable is False`; `invalidation_buffer is None` (không `0`/NaN); giữ `lifecycle_status=="confirmed"` và `broken is False` | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_missing_canonical_tick_is_unknown_and_unusable` | R72-07, A3-007, A3-016 | H1 2 nến `[(112,114,111,113),(102,103,101,102.5)]`; item **không** có `tick_size`/`digits`/`point`, `atr_current=1`, close `102.5` trong zone `[100,110]` | ATR hợp lệ (`== 1`); không nguồn tick nào được khai (không có đường fallback `digits`); chưa terminal; control cùng fixture với `tick_size=0.1` ⇒ `invalidation_buffer ≈ 0.1`, `confirmed`, `broken=False` | `metadata_state=="unknown"`; `metadata_reason` chuỗi không rỗng; `usable is False`; `invalidation_buffer is None` (không tự lấy `digits`, không điền `0`); giữ `confirmed`/`broken is False` | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[expired_by_age]` | R72-07, A3-007, A3-020 | H1 **52 nến** đều trong zone `[(105,106,104,105.5)]×52` (lifetime H1 = 50 bars); item `atr_current=1`, **không** có nguồn tick nào | ATR hợp lệ; không khai `tick_size`/`digits`/`point`; expiry theo age (độc lập metadata); control cùng nến với `tick_size=0.1` ⇒ vẫn `expired`, `usable False` | `lifecycle_status == "expired"` (≠ `confirmed`); `lifecycle_expired is True`; `usable is False`; `visits` còn (state `open`); `metadata_state=="unknown"`; `metadata_reason` không rỗng; `invalidation_buffer is None` | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[already_invalid]` | R72-07, A3-007, A3-020 | H1 `[(112,114,111,113),(99,100,98,99)]`; item đã mang terminal evidence (`lifecycle_status="invalid"`, `broken=True`, `usable=False`), không có tick | như trên; control cùng nến với tick ⇒ vẫn `invalid`, `usable False` | `lifecycle_status == "invalid"` (≠ `confirmed`); `lifecycle_expired is False`; `usable is False`; `visits[0].visit_state == "closed_by_invalidation"`; unknown metadata + threshold `None` | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_metadata_survives_context_to_typed_round_trip` | R72-07, A3-007, A3-021 | H1 2 nến `[(112,114,111,113),(102,103,101,102.5)]`; item `tick_size=0.1` hợp lệ, `atr_current=None`, close `102.5` trong zone | tick hợp lệ; ATR thiếu; chưa terminal; control: round-trip vẫn giữ `zone_id`/bounds/`lifecycle_status`/`visits` (round-trip không hỏng) | `context` và `SmcZone.from_dict(json.loads(json.dumps(context))).to_dict()` đều có `metadata_state=="unknown"`, `metadata_reason` không rỗng, `usable is False`; context có `invalidation_buffer is None` | **GREEN** (F03 sửa 2026-09-11 — trước đó RED F03, §A3.124/§A3.130) | — |
| `test_r72_07_equal_and_outside_buffer_buy_sell[buy]` | A-D07 boundary, A3-028 | H1 2 nến **bước giờ** (`timedelta(hours=i)`, assert cadence); `atr_current=2`, `tick=.1`: exact close `99.9`, beyond close `99.89` | buffer = `max(tick, 0.05*ATR) = .1`; cadence khớp H1 (A3-028) | exact ⇒ `invalidation_buffer ≈ 0.1`, `lifecycle_broken is False`; beyond ⇒ `lifecycle_broken is True` | **GREEN** | — |
| `test_r72_07_equal_and_outside_buffer_buy_sell[sell]` | A-D07 boundary | Mirror SELL: exact `110.1`, beyond `110.11` | như trên | như trên | **GREEN** | — |
| `test_r72_07_excursion_override_only_replaces_its_own_rule` | A3-067 override, R72-01 | H1 8 nến `rows[2]=(110,111,99.9,100.1)` ⇒ penetration `0.10`, dưới `max(2×tick, 0.10×ATR) = 0.2` nhưng trên override `0.05`; source hợp lệ và 3 biến thể ineligible (`provisional`/`usable=False`/`confirmed=False`) | override chỉ thay rule excursion; source vẫn phải eligible | control không override ⇒ `swept_lows == []`; có override hợp lệ ⇒ 1 sweep `index 2` với `excursion_buffer == 0.05`; cả 3 source ineligible ⇒ `[]` | **GREEN** (2026-09-11) | — |
| `test_r72_07_equal_tolerance_override_only_replaces_its_own_rule` | A3-067 override, A3-005 | 2 swing low `100.0`/`100.05` (lệch `0.05`), 4 nến H1 | mặc định `equal_tolerance = 0.2` ⇒ cặp equal; override `0.01` ⇒ không cặp; override `1.0` với 1 source `usable=False` | mặc định: `equal_lows == [100.025]`; `0.01`: `equal_lows == []` nhưng `swing_lows` vẫn `[100.0, 100.05]`; `1.0` + ineligible: `equal_lows == []` | **GREEN** (2026-09-11) — override không cứu source ineligible | — |
| `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule` | A3-067 override, A3-007, **A3R3-02**, A3-067/b cross-control | 2 nến H1: nến chạm `(110.4,111.0,110.3,110.8)` ngoài tolerance tính toán; nến đóng `99.93` (cách đáy vùng `0.07`); thêm biến thể **thiếu tick/ATR** cho cả hai fixture; **mỗi override còn chạy trên fixture của rule kia** | `zone_tolerance=0.5` chỉ đổi rule overlap; `break_buffer=0.05` chỉ đổi ngưỡng invalidation; cả hai không tạo metadata; rule phụ thuộc metadata không tính được ⇒ `None`/`unknown`, **không** `0.0` | mặc định: `visits == ()`, buffer `0.1`; `zone_tolerance=0.5`: 1 visit nhưng buffer vẫn `0.1`, `lifecycle_broken False`; `break_buffer=0.05`: buffer `0.05`, `lifecycle_broken True`. **Cross-control** (A3-067/b): `break_buffer=0.05` trên fixture chạm ⇒ buffer `0.05` nhưng `visits == ()` (rule overlap **không** đổi); `zone_tolerance=0.5` trên fixture phá ⇒ buffer vẫn `0.1` (**không** phải `0.5`) và `lifecycle_broken False`. **Thiếu tick/ATR** (nến chạm): `metadata_state == "unknown"`; `metadata_reason` chuỗi không rỗng; `invalidation_buffer is None`; `lifecycle_broken is False`. **Thiếu tick/ATR** (nến `99.93`): như trên — buffer `0` không được biến close sát biên thành invalidation (`lifecycle_broken is False`) | **GREEN** (F02 sửa 2026-09-11 — trước đó RED F02, §A3.124) | — |
| `test_r72_07_formation_atr_is_causal_and_never_latest_fallback` | A3-068 nguồn ATR, A3-015/A3-016 | H1: 16 nến calm + base bearish idx16 + departure idx17 + 2 nến đuôi; biến thể 5 nến biến động sau; biến thể warm-up ngắn (10 calm + base + departure, departure idx11) | reference phải nằm ở **close trước** nến sự kiện; nến sau không đổi giá trị; trước warm-up nguồn phải **thiếu** (không latest fallback) | `reference_time == stamp(17)`, `event_time == stamp(18)`; thêm 5 nến biến động ⇒ giá trị **không đổi**; warm-up ngắn ⇒ `atr_reference_before_event(...) is None`, `measure_departure(status="unavailable", reason=["DEPARTURE_ATR_UNAVAILABLE"])`, candidate `unavailable`, BOS hợp lệ vẫn giữ `candidate` + `available_at is None` + `OB_DEPARTURE_MEASUREMENT_UNAVAILABLE`; control cùng event shape promote được candidate có ATR (`confirmed`, `available_at == stamp(19)`) | **GREEN** (2026-09-11) | — |
| `test_r72_07_formation_and_current_atr_keep_their_own_source` | A3-068 phân biệt formation/current | H1 chuỗi trên + **4 nến biến động** đuôi ⇒ ATR formation @idx17 = `2.0357` ≠ ATR current @nến cuối = `9.666`; tick `0.1` | detector phải dùng **formation**; lifecycle dùng **current** truyền vào; timeframe/cutoff phải fail-closed | `candidate["departure_measurement"]["atr_before_event"] == formation`; `invalidation_buffer == max(1×tick, 0.05×current)` khi truyền current và `== max(1×tick, 0.05×formation)` khi truyền formation (hai giá trị **khác nhau**); `timeframe="M1"` ⇒ `ValueError`; `event_time` không khớp candle close ⇒ `ValueError` | **GREEN** (2026-09-11) | — |

### R72-08 — canonical terminal projection (13 node)

| Full node ID | Rule ref | Input / timeframe / cutoff | Precond | Expected | Actual | Loại RED |
|---|---|---|---|---|---|---|
| `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[buy]` | R72-08 | H1 2 nến; item đủ `tick_size=.1`, `atr_current=1`, input `lifecycle_status=confirmed`, `usable=True`; close `99` | close phá vùng vượt buffer | `lifecycle_broken is True`; `usable is False`; `lifecycle_status == "invalid"` | **GREEN** (F03 sửa 2026-09-11 — trước đó RED F03, §A3.124/§A3.130) | — |
| `test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable[sell]` | R72-08 | Mirror SELL | như trên | như trên | **GREEN** (F03 sửa 2026-09-11 — trước đó RED F03, §A3.124/§A3.130) | — |
| `test_r72_08_invalid_canonical_zone_survives_typed_round_trip_consistently` | R72-08 | payload `SmcZone` H4: `lifecycle_status=invalid`, `usable=False`, `invalidated_at` | `SmcZone.from_dict` rồi `to_dict` | round-trip giữ `lifecycle_status=="invalid"`, `broken is True`, `usable is False` | **GREEN** (F03 sửa 2026-09-11 — trước đó RED F03, §A3.124/§A3.130) | — |
| `test_r72_08_canonical_invalid_status_wins_legacy_boolean[False]` | R72-08 canonical thắng legacy | payload `lifecycle_status=invalid` + legacy `broken=False` | legacy mâu thuẫn canonical | restored `lifecycle_status=="invalid"` và `broken is True` | **GREEN** (F03 sửa 2026-09-11 — trước đó RED F03, §A3.124/§A3.130) | — |
| `test_r72_08_canonical_invalid_status_wins_legacy_boolean[True]` | R72-08 canonical thắng legacy | payload `lifecycle_status=invalid` + legacy `broken=True` | legacy đồng thuận | như trên | **GREEN** (F03 sửa 2026-09-11 — trước đó RED F03, §A3.124/§A3.130) | — |
| `test_r72_08_typed_terminal_projection_reaches_d1_consumer[buy]` | R72-05/R72-08, A-D04, A3-052 | probe lifecycle 3 nến D1 (outside, touch, reaction) ⇒ `visit.zone_id == "zone"`, `reacted_at == stamp(72)`; payload **typed thật** `SmcZone.from_dict({zone_id: visit.zone_id, direction, timeframe "D1", low 100/high 110, lifecycle_status "invalid", broken True, invalidated_at}).to_dict()`; `as_of = stamp(96)` (close D1 kế tiếp, **sau** reaction) | round-trip typed giữ `zone_id == visit.zone_id`, `timeframe == "D1"`, `lifecycle_status == "invalid"`; `visit.reacted_at (stamp 72) < cutoff (stamp 96)` | `valid is False`; `score == 0`; **không** kết luận sai nhánh: `"D1_REACTION_NOT_COMPLETED_REACTED" not in reason_codes` (không do ID lệch) và `"D1_REACTION_AFTER_CUTOFF" not in reason_codes` (không do cutoff trước reaction) — hiện RED (implementation, F05: vùng canonical terminal vẫn cấp evidence hoạt động) | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_08_typed_terminal_projection_reaches_d1_consumer[sell]` | R72-05/R72-08, A-D04, A3-052 | Mirror SELL (`zone_type` bearish, cùng zone D1/`visit.zone_id`) | như trên | như trên | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_08_typed_d1_projection_keeps_valid_reaction[buy]` | R72-08, A3-053 | probe lifecycle 3 nến D1 (outside, touch, reaction) ⇒ `visit.zone_id == "zone"`, `visit_id == "zone:visit-1"`, `reacted_at == stamp(72)`; payload **typed** `SmcZone.from_dict({zone_id, direction, timeframe "D1", low 100/high 110, available_at stamp(24), lifecycle_status "confirmed", broken False, visits [visit.to_dict()]}).to_dict()`; `as_of = stamp(96)` | vùng **chưa terminal**, `visit.reacted_at (stamp 72) < cutoff (stamp 96)`; round-trip giữ `zone_id`/`low`/`high`/`available_at`/`lifecycle_status`/1 visit (`visit_id`, `reacted_at`, `visit_state` khớp) | **positive control**: `valid is True`, `score > 0`, `zone_id == visit.zone_id`, `source_visit_id == visit.visit_id` — chứng minh payload typed hoạt động, nên ca terminal (A3-052/A3-054) không thể "xanh vì mọi payload typed đều fail" — hiện **GREEN** | **GREEN** | — |
| `test_r72_08_typed_d1_projection_keeps_valid_reaction[sell]` | R72-08, A3-053 | Mirror SELL (cùng zone D1) | như trên | như trên | **GREEN** | — |
| `test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[buy]` | R72-08, A-D04, A3-054 | **cùng nguồn A3-053** (probe lifecycle 3 nến D1, visit `completed_reacted`, `reacted_at stamp(72)`); payload typed `SmcZone.from_dict({..., lifecycle_status "invalid", broken True, invalidated_at stamp(96), visits [visit.to_dict()], d1_reaction True, proximity True}).to_dict()`; lifecycle payload = `state.to_dict()` + `{lifecycle_status "invalid", lifecycle_broken False, broken False, d1_reaction True, proximity True}` (legacy **trái** canonical); `as_of = stamp(96)` | round-trip giữ canonical (`invalid`, `broken True`, `invalidated_at stamp(96)`); legacy `d1_reaction`/`proximity` **không** thuộc payload typed (`not in`); lifecycle payload có legacy flags trái canonical | **canonical thắng**: `valid is False`, `score == 0` — hiện RED (implementation, F05/F03: trạng thái canonical invalid chưa chặn evidence hoạt động) | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags[sell]` | R72-08, A-D04, A3-054 | Mirror SELL (cùng zone D1) | như trên | như trên | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_08_typed_expired_projection_blocks_d1_and_keeps_history[buy]` | R72-08, A-D04, A3-055 | D1 23 nến `_terminal_lifecycle(buy, 20)` (reaction idx20, expiry idx21) ⇒ `lifecycle_expired True`, `expiry_index == 21`, `visit.reacted_at == stamp(504)` (close idx20), `expired_at == stamp(528)` (close idx21); payload typed `SmcZone.from_dict({..., lifecycle_status "expired", broken False, expired_at, visits [visit.to_dict()]}).to_dict()`; `as_of = expired_at` | payload giữ **cùng `zone_id`** với visit (`"terminal-zone"` — guard "không pass bằng mismatched ID"), `lifecycle_status == "expired"`, `expired_at` khớp, 1 visit với `reacted_at` **còn nguyên** (không mất history) | `valid is False`, `score == 0`, `zone_id == visit.zone_id` — hiện **GREEN** (reason `D1_REACTION_STALE`) | **GREEN** | — |
| `test_r72_08_typed_expired_projection_blocks_d1_and_keeps_history[sell]` | R72-08, A-D04, A3-055 | Mirror SELL (cùng `_terminal_lifecycle(sell, 20)`) | như trên | như trên | **GREEN** | — |

### R72-09 — fixture validity và chuỗi thật (10 node)

| Full node ID | Rule ref | Input / timeframe / cutoff | Precond | Expected | Actual | Loại RED |
|---|---|---|---|---|---|---|
| `test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid` | R72-09 | 5 bộ `rows` hard-code cho task59/60/62/63/65, nạp qua `module._candles(rows)` | bản rows phải là bản module thực dùng (xem mục CHƯA RÕ ở A3-003) | `validate_smc_candles` không trả lỗi cho từng bộ | **GREEN** | — |
| `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke` (A3-056 đổi tên từ `test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture`) | R72-09 | gate56 fixture rows → `detect_order_block_candidates` → `enrich_zones` → `SmcZone` round-trip → `analyze_zone_lifecycle` → `build_d1_reaction_evidence`; cutoff = nến cuối | H1; fixture qua validator | zone ID khớp qua các tầng; `original_bounds == {low:99, high:101}`; D1 `valid False`/`score 0` ⇒ cần sửa (candidate chưa confirmed, ATR tự gán, so chính serialization) | **GREEN** | — |
| `test_r72_09_d1_source_is_confirmed_by_fixture_break` (A3-057) | R72-09 | fixture D1 37 nến `_D1_SOURCE_ROWS` (0..31 warm-up zigzag, 32 base bearish, 33 departure, 34 nến phá đỉnh swing 103.0, 35..36 đuôi) → `detect_order_block_candidates` → `confirm_order_block_candidate` với BOS thật của `replay_smc_structure`; chưa gọi lifecycle (đó là A3-058) | validator D1 sạch; warm-up 33 nến trước departure (≥15 cho ATR); đúng 1 buy candidate tại nến base 32; candidate **chưa** confirmed/available_at (không tự gán); BOS `status=confirmed`, `broken_level_id` = swing high thật của fixture | candidate được promote thành `confirmed`; `available_at == confirmed_at ==` close nến phá đỉnh (tính từ fixture: `candles[34].time + 1 ngày`); `confirmation_event_id`/`related_structure_event_id` = `event_id` BOS, `broken_level_id` = swing high ID; bounds `{low:99.2, high:100.2}` và identity (zone_id/setup_id/origin_time/departure_source_id) giữ nguyên; candidate đầu vào không bị mutate | **GREEN** (2026-09-11) — confirmation đã đúng; node là positive control cho nguồn confirmed D1 dùng ở A3-058…A3-062 | — |
| `test_r72_09_d1_confirmed_zone_timeline_comes_from_fixture_retest` (A3-058) | R72-09 | chính vùng confirmed của A3-057 (`_d1_confirmed_source`) kèm metadata fixture `tick_size=0.1`/`atr_current=1.0` đi qua `enrich_zones` trên chuỗi `_D1_RETEST_ROWS` (5 nến retest: bar 38 vào vùng, 39 trong vùng, 40 thoát lên, 41 follow-through); `tf_minutes=1440` | `_d1_retest_candles()` assert hình học theo metadata fixture: không nến nào (34..37) chạm vùng; bar 38 là overlap đầu tiên; bar 40 thoát lên nhưng close < `zone_high + 0.25×ATR`; bar 41 close ≥ threshold; không nến nào đóng qua buffer invalidation | `first_retest_index == 38`, `first_retest_time ==` close bar 38; đúng 1 visit `completed_reacted` với `entered_at`/`exited_at`/`reacted_at` = close bar 38/40/41 (tính từ fixture), `start_index 38`, `end_index 39`, `bars_spent_inside 2`; `lifecycle_mitigated True`, `lifecycle_broken/stale False`, `invalidation_index`/`expiry_index` None; zone_id/bounds/`available_at` giữ nguyên; **không** gọi `analyze_zone_lifecycle` lần hai để thay output | **GREEN** (2026-09-11) — lifecycle canonical tính đúng timeline của fixture | — |
| `test_r72_09_d1_enriched_zone_survives_typed_restore` (A3-059) | R72-09 | vùng enriched của A3-058 (`_d1_enriched_source()`) → `SmcZone.from_dict(enriched)` → `SmcZone.from_dict(typed.to_dict())` | zone_id khớp qua các tầng; `symbol` chuẩn hoá `EURUSD`; direction `buy`, family `ob`, timeframe `D1`; `tick_size`/`atr_current` là metadata fixture | **Mỗi** model (typed và restored) đều khớp bộ expected **tính từ fixture**: `low/high/original_low/original_high` = 99.2/100.2 (nến base); `origin_index 32`, `departure_end_index 33`; `confirmation_event_id` = event_id BOS, `confirmed_at`/`available_at` = close nến 34; `first_retest_index 38` + `first_retest_time` = close nến 38; `independent_retest_count 1`, `bars_spent_inside 2`, `lifecycle_mitigated True`, `broken False`, `invalidation_index`/`invalidated_at`/`expired_at` None; 1 visit `completed_reacted` (`start_index 38`, `end_index 39`, `entered_at`/`exited_at`/`reacted_at` = close nến 38/40/41) — **không** so `typed.to_dict()` với `restored.to_dict()` | **GREEN** (2026-09-11) — typed restore không mất identity/biên/timeline | — |
| `test_r72_09_d1_reaction_positive_reads_canonical_lifecycle` (A3-060) | R72-09 | payload typed đã restore (A3-059) + **chính** lifecycle của `enrich_zones` (A3-058); `as_of` = close nến cuối fixture (`_d1_close_at(candles, len-1)`); **không** gọi `analyze_zone_lifecycle`/lifecycle lần hai | payload không mang legacy `d1_reaction`/`proximity`; canonical lifecycle có đúng 1 visit `completed_reacted` với `entered_at`/`reacted_at` = close nến 38/41; `available_at` = close nến 34 và `< cutoff`; không có `invalidation_index`/`invalidated_at`/`expiry_index`/`expired_at` (chưa terminal) | `valid True`, `score > 0`, `zone_id` khớp, `source_visit_id` = `typed.visits[0].visit_id`, `reacted_at` = close nến 41, `reason_codes == ["D1_REACTION_COMPLETED_REACTED"]`; **control**: bỏ visit canonical ở cả payload và lifecycle + bật legacy `d1_reaction`/`proximity` = True ⇒ `valid False`/`score 0`/`D1_REACTION_NOT_COMPLETED_REACTED` ⇒ pass **không** đến từ legacy flag | **GREEN** (2026-09-11) — consumer D1 đọc đúng visit canonical | — |
| `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` (A3-061) | R72-09, A-D04, R72-08, **A3R3-03** | payload typed từ vùng enriched trên chuỗi `_D1_INVALIDATION_ROWS` (bar 42 ngoài vùng, bar 43 đóng `98.6 < zone_low − 0.2`); `as_of` = close nến 43 (`_d1_close_at(candles, 43)`); **positive control = prefix thật** `_D1_RETEST_ROWS` (chuỗi bỏ 2 nến terminal) enrich **riêng** bằng `_d1_enriched_source()`, `as_of` = close cuối của chính prefix = close nến 41 | `_d1_invalidated_candles()` assert: không nến nào (38..42) đóng qua buffer; bar 43 đóng qua buffer; reaction nến 41 vẫn trước breakdown; **bản append kết thúc đúng tại invalidation close** (A3-061/b: `_D1_INVALIDATION_INDEX == len(candles) − 1`, `terminal_at` = close cuối của chính snapshot ⇒ **không** rewind) ⇒ `invalidation_index 43`, `invalidated_at` = close nến 43, `lifecycle_broken`/`broken` True, không expiry, `available_at` giữ nguyên (close nến 34); 2 visit: visit-1 `completed_reacted` (entered/exited/reacted = close nến 38/40/41) và visit-2 `closed_by_invalidation` (start=end=43, `reacted_at` None); **prefix chưa terminal** (`confirmed`, `broken False`, `invalidation_index`/`invalidated_at`/`expiry_index`/`expired_at` đều `None`) và **identity/history khớp bản append** (`zone_id`, `low`/`high`, `available_at`, `visits[0]` bằng nhau) | Tại close terminal phải có: `lifecycle_status == "invalid"`, `usable is False`, `evidence["valid"] is False`, `score == 0`, và reject **không** vì thiếu reaction (`D1_REACTION_NOT_COMPLETED_REACTED` không xuất hiện). Control: trên prefix, consumer trả `valid True`/`score > 0` với `source_visit_id` = visit-1 của **chính prefix**. Thực tế: control prefix **PASS**; terminal dừng ở `lifecycle_status == "confirmed"` — probe cùng chuỗi cho thấy `usable` **thiếu key** và D1 trả `valid True`/`1.0` (reason `D1_REACTION_COMPLETED_REACTED`) | **GREEN** (F05 sửa 2026-09-11 — trước đó RED F05, §A3.122/§A3.124) | — |
| `test_r72_09_d1_expired_source_is_terminal_for_the_consumer` (A3-062) | R72-09, A-D04 | payload typed từ vùng enriched trên chuỗi `_D1_EXPIRY_ROWS` (chuỗi retest + 14 nến ngoài vùng, low > tolerance, không đóng qua buffer); `as_of` = close nến 55 | `_d1_expired_candles()` assert: mọi nến sau reaction vẫn ngoài vùng và không invalidate; `_D1_EXPIRY_INDEX == _D1_BREAK_INDEX + 21` và là nến cuối ⇒ tuổi vùng (`_D1_EXPIRY_INDEX − _D1_BREAK_INDEX`) vượt lifetime D1 20 nến; metadata fixture (`tick_size`/`atr_current`) vẫn nguyên | `expiry_index 55`, `expired_at` = close nến 55 (tính từ fixture), `lifecycle_expired`/`lifecycle_stale` True, `lifecycle_broken`/`broken` False, không invalidation; 1 visit `completed_reacted` giữ nguyên `reacted_at`; tại expiry: `lifecycle_status == "expired"`, `usable is False`, reason có `ZONE_EXPIRED`, D1 `valid False`/`score 0` với `reason_codes == ["D1_REACTION_STALE"]` và **không** `D1_REACTION_NOT_COMPLETED_REACTED` | **GREEN** (2026-09-11) — nhánh expiry đúng end-to-end; đối chiếu A3-060 là positive control cùng vùng trước expiry | — |
| `test_r72_09_full_fvg_fill_is_not_a_break` (A3-079) | R72-09, A3-079 fill/R56 invariant | H1 4 nến của fixture task62 full-fill: `(100,101,99,100)`, `(100,102,99,101)`, `(102,112,102,110)`, `(110,111,99,100)`; FVG zone `low 100`/`high 110`, `origin_index 2`/`formation_end_index 2`, `lifecycle_status "confirmed"`, `broken False` | fixture hợp lệ qua `validate_smc_candles`; gap bị quét hết bởi nến cuối; reuse rows task62 (không tạo fixture mới) | `fill_status "filled"`, `fill_ratio 1.0`, `remaining_bounds {low:100, high:100}`; `zone_id`/`setup_id`/`original_bounds`/`low`/`high` **không đổi**; `broken is False` và `lifecycle_status "confirmed"` ⇒ **full fill không tự là break** | **GREEN** (2026-09-11) — fill giữ identity/bounds và không nâng terminal state; kèm reuse task62 + R56 session (121 passed) | — |
| `test_r72_09_intentional_invalid_data_reports_its_own_reason` (A3-080) | R72-09, A3-080, A3-023 | H1 5 nến, bar 4 là **ví dụ invalid của R72-09**: `(112,113,111.2,110.2)` — close **dưới** low; control: cùng bar đã sửa theo **F01-T60-BUY** `(112,113,110.2,110.2)` (close == low); 4 nến đầu giống nhau ở cả hai series | positive và negative phải tách nhau **bằng cùng một validator**, reason do dữ liệu chứ không do họ fixture | negative: `validate_smc_candles` trả **đúng một** issue `code "SMC_OHLC_INVALID"`, `index 4`, `field "ohlc"`; control: validator trả `()`; close/low của 4 nến đầu khớp nhau giữa hai series | **GREEN** (2026-09-11) — negative có reason riêng, positive (năm fixture fixes) đã PASS ở node reused | — |

---

## Interface pool — chốt theo review A lần2 (A3-005)

Ghi ngày 2026-09-11. Mục này **thay** dòng `detect_liquidity_pools → detect_liquidity_sweeps` trong
"Interface proposal for TL approval" ở trên; dòng cũ giữ làm lịch sử. Đây là schema mà A3-009/A3-010
sẽ viết test theo, **chưa sửa `core/`**.

### Hiện trạng numeric (giữ nguyên làm legacy projection)

`detect_liquidity_pools` trả `dict` với bốn key numeric là `list[float]`:

| Key | Kiểu | Nội dung hiện tại |
|---|---|---|
| `swing_highs`, `swing_lows` | `list[float]` | level của các swing hợp lệ (confirmed + usable + non-provisional), sort theo causal key `(index, pivot_time, swing_id)` |
| `equal_highs`, `equal_lows` | `list[float]` | **trung bình cặp** `(value + other) / 2.0` trong `tolerance` — **không bằng level của source nào**, nên không thể tra ngược source từ level |
| `equal_tolerance` | `float` | `max(2*tick, 0.10*ATR)`; có `equal_tolerance` override; nhánh legacy không metadata dùng `max(avg_range*0.15, 0.0001)` |
| `status`, `reason_codes` | `str`, `list[str]` | chỉ khi typed metadata thiếu tolerance: `"unknown"` / `SMC_EQUAL_LEVEL_TOLERANCE_UNAVAILABLE` |

Bốn key numeric **giữ nguyên kiểu `float`** ở nhánh canonical; chúng chỉ là projection để đọc nhanh,
không phải nguồn authority.

### `records` — container canonical (mới)

| Field | Kiểu | Ý nghĩa / nguồn |
|---|---|---|
| `pool_id` | `str` | Ổn định theo **causal source lineage**: `kind` + `source_ids` đã sort + causal record của source. Không sinh ID theo level, thứ tự list, rolling index hay observation time (A-D06). |
| `kind` | `str` | Một trong `swing_low` / `swing_high` / `equal_low` / `equal_high` — (đề xuất, xem câu hỏi mở 1). |
| `level` | `float` | Level canonical của pool. Equal pool dùng trung bình như projection; **lineage lấy từ `source_ids`, không tra ngược từ `level`**. |
| `source_ids` | `list[str]` | ID các swing nguồn, **sắp xếp ổn định** (`sorted`) và ổn định dưới permutation — không theo thứ tự input và không theo thứ tự causal. Thời điểm/biên của từng nguồn nằm trong `sources`, tra theo `swing_id`; không suy lineage từ level. |
| `sources` | `list[dict]` | Mỗi phần tử giữ **thời điểm và ID**: `{swing_id, confirmed_at, usable_at, provisional}`. |
| `usable_at` | `str` (ISO UTC) | `max(source.usable_at)`. Equal pool chỉ hợp lệ khi **mọi** source đã usable (A-D01 inclusive `usable_at <= reclaimed_at`). |

### Luật bắt buộc

1. **Không key nào vừa `float` vừa `dict`.** `equal_lows[0]` là `float`; record nằm trong `records`.
2. Test lineage đọc `records`; giá trị numeric chỉ được kiểm như projection (A3-009).
3. Canonical sweep thiếu `records` hoặc thiếu provenance ⇒ **fail closed**, không fallback sang level
   numeric (A3-010).
4. Equal pool giữ **cả** source, không tìm ngược source bằng cách so level với từng swing.
5. Source `confirmed/usable` tại snapshot **không** đồng nghĩa đã usable tại candle quá khứ; `usable_at`
   là mốc dùng để kiểm causal (A3-040…043).
6. `pool_id` không đổi khi đổi observation time/thứ tự input/rolling index; pool mới phải có
   `source_ids`/lineage mới (A-D06).

### Câu hỏi pool của bản trình — đã chốt tại review A lần3 §3

1. **Tên enum `kind`**: đề xuất `swing_low` / `swing_high` / `equal_low` / `equal_high`. Review chỉ nêu
   tên field `kind`, chưa chốt giá trị.
2. **Swing pool một source** có nằm trong `records` không? Đề xuất: có, mỗi level trong `swing_lows` /
   `swing_highs` cũng có record với `source_ids` một phần tử — để sweep kiểm causal được cho cả swing
   pool lẫn equal pool (R72-01 yêu cầu kiểm cả hai).
3. **`level` của equal pool**: giữ trung bình (đồng nhất với projection hiện tại) hay dùng level của
   source sớm nhất? Đề xuất giữ trung bình + `source_ids` làm authority.

---

## Interface history — chốt theo review A lần2 (A3-006)

Ghi ngày 2026-09-11. Mục này **thay phần `history_complete`** trong dòng
`_attach_zone_sweep_links → assign_sweep_ownership` của "Interface proposal for TL approval" ở trên;
dòng cũ giữ làm lịch sử. Chỉ là đính chính đề xuất — **không sửa `core/`**, vì code hiện tại đã đúng
quyết định.

### Đính chính

Đề xuất cũ ghi `history_complete=False` như giá trị mặc định. **Sai với quyết định review A lần2**:
phải giữ compatibility default đang có của helper, không đề xuất đổi default ngầm. Đề xuất đúng:

```text
assign_sweep_ownership(claims, *, assignment_history=None, history_complete=True)
```

`history_complete: bool = True` là **default hiện hữu** trong code, không phải giá trị mới:
`core/smc_sweep_linking.py:279` (và wrapper cùng file ở `:444`).

### Ngữ nghĩa hiện tại (đọc từ code, không thay đổi)

| Tình huống | Hành vi |
|---|---|
| `assignment_history` có record cho sweep | History là authority: trả nguyên `owner_setup_id`/`assignment_id` đã có, **bất kể** `history_complete` |
| Không có historical record và `history_complete=False` | Ghi `SWEEP_OWNER_HISTORY_INCOMPLETE`, **không** cấp owner mới cho setup hiện tại |
| Không có historical record và `history_complete=True` | Xếp hạng claims hiện tại theo `(claim_eligible_at, setup_id, zone_id)` rồi cấp owner |

### Nghĩa vụ của canonical caller

1. Truyền `history_complete` **tường minh** theo dữ liệu thật: đủ history ⇒ `True`; thiếu/không xác
   định ⇒ `False`. Không dựa vào default để chứng minh canonical path.
2. Vì default là `True`, caller canonical khai báo cửa sổ thiếu **phải** truyền `False` — nếu không sẽ
   nhận assignment như thể history đầy đủ.
3. `_attach_zone_sweep_links` (context) phải truyền history/completeness thật xuống, không để helper
   tự mặc định (R72-04).

Ràng buộc này là cơ sở cho A3-011 (positive fixture truyền `True` tường minh) và A3-012 (ca
thiếu/unknown truyền `False` tường minh).

## Interface metadata — chốt theo review A lần2 (A3-007)

Ghi ngày 2026-09-11. Mục này **thay** dòng `enrich_zones → lifecycle → context` của "Interface proposal
for TL approval" ở trên; dòng cũ giữ làm lịch sử. Đây là contract cho F02 — **không sửa `core/`** ở
checkpoint A; mọi mục "hiện trạng" dưới đây chỉ là bằng chứng đọc code.

### 1. Field và giá trị đang hiệu lực

| Field | Vị trí | Kiểu / giá trị | Ý nghĩa |
|---|---|---|---|
| `metadata_state` | `ZoneLifecycle` (đề xuất, chưa có trong code) | `"available"` \| `"unknown"` | Trạng thái **chất lượng dữ liệu** của rule phụ thuộc metadata; tách hẳn khỏi `lifecycle_status`. |
| `metadata_reason` | `ZoneLifecycle` | `str` **không rỗng** khi `unknown` | Lý do cụ thể (thiếu tick / thiếu ATR / nonfinite / conflict), giữ được truy vết. |
| `tick_size_source`, `atr_source` | provenance truyền xuống | `str` \| `None` | Nguồn metadata. `tick_size_source` dùng đúng tập đã duyệt ở `core/smc_models.py:31-35`; `atr_source` theo [parameter table](smc-parameter-table.md). |
| `usable` | projection ở context (dict) | `False` khi `metadata_state == "unknown"` | Không được `True` khi chưa tính được threshold phụ thuộc metadata. |
| threshold không tính được | `invalidation_buffer` (break buffer) và zone tolerance | `None` | **Không** `0`, **không** `NaN`. `0` là giá trị hợp lệ của một ngưỡng thật (`explicit`/override hợp lệ) nên không được dùng làm nghĩa "không biết". |
| `lifecycle_status` | enum đóng | **không đổi** | Không thêm `unknown` vào enum — xem mục 3. |

### 2. Bảng theo từng ca (A3-015…A3-018, A3-020)

`metadata_state`/`usable`/threshold là các cột contract; cột cuối chỉ ghi điều **được phép** thay đổi.

| Ca | Nguồn còn hợp lệ | `metadata_state` | `usable` | threshold | `lifecycle_status` / `broken` |
|---|---|---|---|---|---|
| Thiếu riêng ATR, tick hợp lệ | tick | `unknown` | `False` | `None` (phần phụ thuộc ATR) | giữ theo bằng chứng terminal; chưa terminal ⇒ `confirmed` / `broken=False` |
| Thiếu riêng tick, ATR hợp lệ | ATR | `unknown` | `False` | `None` | như trên; **không** tự lấy `digits` hay điền threshold `0` |
| Nonfinite (parameterize ATR / tick; trường còn lại hợp lệ) | trường còn lại | `unknown` | `False` | `None` | như trên; nonfinite **tách** khỏi missing |
| Conflict: tick item vs tick argument cùng scope, khác giá trị | — (hai nguồn mâu thuẫn) | `unknown` | `False` | `None` | như trên; **không** tự chọn bên thuận lợi (A-D07) |
| Parity: hai nguồn tick cùng scope **cùng** giá trị | cả hai | `available` | theo lifecycle | tính từ tick/ATR | như bình thường |
| Chỉ một nguồn tick hợp lệ được khai báo | nguồn đó | `available` | theo lifecycle | tính từ nguồn đó | như bình thường (A-D07) |
| Terminal đã biết + metadata thiếu | — | `unknown` | `False` | `None` | giữ `invalid`/`expired` + history tương ứng; không "cứu" `usable` (A3-020) |

Ghi chú bắt buộc: mọi hàng `unknown` có `metadata_reason` không rỗng. Assertion theo contract này khóa
`metadata_state`/`metadata_reason`/threshold `None` — **không** assert `lifecycle_status` thuộc
`{unknown, candidate, invalid}` và **không** chỉ `invalidation_buffer != 0` (dạng assert bị review cấm ở
[§F01.1](#f011--representation-và-đồng-bộ-docstests)).

### 3. Ranh giới với lifecycle enum

`lifecycle_status` là enum đóng `core/smc_models.py:38-45`
(`candidate`, `confirmed`, `usable`, `watch`, `invalid`, `expired`); `SmcZone.__post_init__` ném
`ValueError` với giá trị ngoài tập (`core/smc_models.py:1012-1014`). Đã kiểm bằng Python:
`SmcZone(..., lifecycle_status="unknown")` ⇒ `ValueError: Invalid SMC zone lifecycle status: unknown`.
Vì vậy `unknown` **chỉ** sống ở `metadata_state`; consumer lọc bằng `usable is False`, không bằng một
status mới. `unknown` là data-quality state, **không** phải lifecycle status.

### 4. Ranh giới với terminal (giữ nguyên A-D04/A-D05)

- Bằng chứng terminal đã biết **thắng**: metadata thiếu không đổi `invalid`/`expired` sang trạng thái
  khác, không làm mất reaction history trước terminal, không làm `usable` trở lại.
- Threshold `None` **không** được dùng để suy ra invalidation. Khi chưa có bằng chứng terminal, `unknown`
  chỉ hạ `usable`, không tự tạo `broken` (hiện tại buffer `0.0` làm close sát biên bị coi là invalidation —
  xem mục 6).
- Thứ tự terminal trước reaction giữ như A-02/A-D05.

### 5. Đường truyền metadata

- **Hai nguồn cùng scope**: key `tick_size` trên item zone và tham số `tick_size` của `enrich_zones`
  (`core/smc_context.py:4846`). Cùng giá trị ⇒ parity; khác giá trị ⇒ `unknown` (A-D07).
- **ATR canonical là causal**: ATR **trước** sự kiện (`atr_value_before_event`,
  `core/smc_context.py:4771`), không lấy ATR mới nhất; `atr_source` ghi nguồn/fallback.
- **Forward**: lifecycle → context projection → typed round-trip; `metadata_state`/`metadata_reason`/
  `usable` phải đi cùng nhau qua JSON (A3-021). `SmcZone` hiện **chưa** có field `usable` (đã kiểm:
  không nằm trong `SmcZone.__dataclass_fields__`) — bổ sung thuộc F03/R72-08, không thuộc mục này.

### 6. Hiện trạng code — nền RED cho F02 (không sửa ở checkpoint A)

> **Đã sửa ở F02 (2026-09-11):** toàn bộ 6 hành vi dưới đây đã được xử lý — threshold metadata-dependent trả `None` + reason thay vì `0.0`, nonfinite là `unknown` (không raise), `invalidation_buffer` đổi sang `float | None`, call site forward **cả** item tick và argument tick (conflict cùng scope ⇒ `unknown`), và `metadata_state`/`metadata_reason` đã tồn tại. Bảng dưới giữ nguyên làm **ảnh chụp lịch sử** trước F02. Bằng chứng: `fix-progress` §A3.130 (F02) và §A3.131 (F02/r1 khép 5 regression fixture).

| Hành vi hiện tại | Vị trí | Đối chiếu contract |
|---|---|---|
| Thiếu tick **hoặc** thiếu ATR ⇒ `zone_tolerance`/break buffer trả `0.0` | `core/smc_lifecycle.py:477-478`, `497-498` | Sai: phải `unknown` + threshold `None`. Spec đã ghi "thiếu tick/ATR phải ghi unknown cho rule phụ thuộc, không âm thầm chọn digits" ([smc-lifecycle-spec.md:68](smc-lifecycle-spec.md)). |
| Nonfinite tick/ATR ⇒ `ValueError` | `_finite_float`, `core/smc_lifecycle.py:668-675` | Sai nhánh: nonfinite phải là `unknown`, tách khỏi missing (A3-017). |
| `ZoneLifecycle.invalidation_buffer: float = 0.0` | `core/smc_lifecycle.py:46` | Ngưỡng `None` cần kiểu `float \| None` — thay đổi interface ở F02. |
| Call site chỉ đọc `item.get("tick_size")`, **bỏ qua** tham số `tick_size` của `enrich_zones` | `core/smc_context.py:4912-4926` | Sai: argument-only tick không được forward (A-D07) — nền RED của `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle`. |
| Item tick khác argument tick ⇒ item thắng **âm thầm** | như trên | Sai: cùng scope mà mâu thuẫn phải `unknown`, không chọn bên thuận lợi. |
| Chưa có `metadata_state`/`metadata_reason` ở module nào | grep toàn repo = 0 hit | Phần F02 phải thêm. |
| Caller production gọi `enrich_zones` **không** truyền `tick_size`, detector không set `atr_current` | `core/smc_context.py:971-994` | Nhánh canonical hiện chưa có metadata ⇒ zone đi đường này đang "thiếu" ngầm; F02/F06 phải nối nguồn thật, không được coi `0.0` là hợp lệ. |

Tiền lệ đã có trong code để dùng lại (không phải quy tắc mới): `measure_fvg_gap` trả `minimum_gap: None`
+ `accepted: False` + reason `SMC_TICK_SIZE_UNAVAILABLE`/`FVG_ATR_UNAVAILABLE` (`core/smc_context.py:307-325`),
và nhánh equal-level ghi `status="unknown"` + `SMC_EQUAL_LEVEL_TOLERANCE_UNAVAILABLE`
(`core/smc_context.py:4312`).

### 7. Node sẽ khóa contract này

| Node | Trạng thái hiện tại | Việc của mã |
|---|---|---|
| `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]` / `[tick_size]` | RED | Đã parameterize ở A3-017 (đổi tên từ node bundled `missing_or_nonfinite`), assertion theo `metadata_state`/`metadata_reason`/threshold `None`; missing do A3-015/A3-016 khóa riêng. |
| `test_r72_07_conflicting_same_scope_tick_sources_fail_closed` | RED | A3-018 đã sửa expected (assert `lifecycle_status == "unknown"` bị bỏ; nay khóa `metadata_state`/`metadata_reason`/threshold `None`). |
| `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle` | RED | A3-019 kiểm forward của cả ba cách cấp tick (item-only, argument-only, equal-both). |
| `test_r72_07_item_and_argument_tick_sources_have_parity` | RED | A3-019 đã siết sang expected tuyệt đối theo từng biến thể (`buffer ≈ 0.1`, `broken False`, `confirmed`); gap còn lại là argument tick chưa được forward (F02). |
| Ca thiếu riêng ATR / thiếu riêng tick / terminal + metadata thiếu | đã có node | A3-015 (`missing_canonical_atr_...`), A3-016 (`missing_canonical_tick_...`), A3-020 (`unknown_metadata_does_not_revive_terminal_zone[...]`). |
| Round-trip metadata qua lifecycle → context → typed | chưa có node | A3-021. |

### Câu hỏi metadata của bản trình — đã chốt tại review A lần3 §3

1. **Tên reason code cụ thể**: review chỉ chốt "reason không rỗng". Đề xuất theo convention đang có
   (`SMC_TICK_SIZE_UNAVAILABLE`, `FVG_ATR_UNAVAILABLE`, `SMC_EQUAL_LEVEL_TOLERANCE_UNAVAILABLE`):
   `SMC_METADATA_ATR_UNAVAILABLE`, `SMC_METADATA_TICK_UNAVAILABLE`, `SMC_METADATA_NONFINITE`,
   `SMC_METADATA_SOURCE_CONFLICT`. **Không chặn A3-015…018** nếu assertion chỉ đòi reason không rỗng;
   cần TL chốt nếu muốn khóa đúng chuỗi.

## Interface claim → assignment — chốt theo review A lần2 (A3-008)

Ghi ngày 2026-09-11. Mục này **thay phần còn lại** của hai dòng `_attach_zone_sweep_links →
assign_sweep_ownership` (ngoài `history_complete` đã chốt ở A3-006) và `assignment → contribution
projection` trong "Interface proposal for TL approval"; dòng cũ giữ làm lịch sử. Chỉ ghi interface —
**không sửa `core/`** và **không thêm thuật toán ownership mới**: mọi luật dưới đây lấy từ A-D02/A-D03/
A-D06.

### 1. Chuỗi caller → owner → output

| Bước | Nơi | Vào | Ra |
|---|---|---|---|
| 1. Sweep record | `detect_liquidity_sweeps` (`core/smc_context.py:4488-4515`) | swing/pool + candle | `sweep_id`, `side`, `kind`, `level`, `index`, `time`/`occurred_at`, `reclaimed_at`, `source_pool_id`/`source_pool`, `source_swing_id`, `source_swing_time`, `depth`, `occurred_at` |
| 2. Link | `associate_sweeps_to_zones` (`core/smc_sweep_linking.py:104`) | zone + sweep | `SweepZoneLink`; hiện chỉ giữ `sweep_time` = `sweep.get("reclaimed_at", sweep.get("time"))` (`:234-236`) và **bỏ** pool/source lineage |
| 3. Claim | caller dựng claim (`_attach_zone_sweep_links`, `core/smc_context.py:4647-4653`) | link + zone | claim dict (xem mục 2) |
| 4. Owner | `assign_sweep_ownership` (`core/smc_sweep_linking.py:275`) | claims + `assignment_history` + `history_complete` | `assignments{sweep_id: SweepAssignment}`, `claims[]` (projection), `reason_codes[]` |
| 5. Output | `mark_sweeps_consumed` (`:439`) → projection của caller (`core/smc_context.py:4662-4671`) | ownership | sweep: `consumed`, `pool_consumed`, `owner_setup_id`, `assignment_id`, `assigned_at`, `claim_eligible_at`, `contribution_applied`; zone: `sweep_assignment_id`, `sweep_owner_setup_id`, `sweep_assigned_at`, `sweep_contribution_applied` |

### 2. Claim canonical

| Field | Bắt buộc | Ý nghĩa |
|---|---|---|
| `sweep_id`, `setup_id`, `zone_id`, `side` | có | danh tính claim; thiếu hoặc `side` lạ ⇒ claim không được xếp hạng |
| `reclaimed_at` | **có** | close của sweep candle (A-D02); sweep record đã có key này (`core/smc_context.py:4500`) |
| `setup_available_at` | **có** | thời điểm setup khả dụng (A-D02) |
| `pool_id` | **có** khi claim khai pool | canonical pool identity theo A3-005 (`records.pool_id` từ causal source lineage), không phải `kind:level` |
| `source_ids` | **có** khi claim khai pool | ID swing nguồn của pool, dùng để chứng minh pool mới (A-D06) |
| `claim_source` | có | nhánh phát claim (canonical vs adapter legacy) |

Luật bắt buộc:

1. Thiếu **một trong hai** thời điểm ⇒ **fail closed**: sweep đó không có assignment, reason
   `SWEEP_CLAIM_TIME_MISSING`. **Không** fallback sang timestamp còn lại (A-D02, A3-013/A3-014).
2. `claim_eligible_at` = `max(reclaimed_at, setup_available_at)`; owner là claim có eligibility sớm nhất,
   tie ⇒ setup ID ổn định (A-D02). Code hiện thêm `zone_id` làm chốt cuối (`smc_sweep_linking.py:374-381`)
   — giữ nguyên làm tính xác định, không phải quyết định mới.
3. Caller canonical truyền `reclaimed_at` **tường minh**; không để helper suy từ `sweep_time` của link.
4. Alias legacy (`sweep_time`, `sweep_reclaim_at`, `time`, `available_at`) chỉ được chấp nhận ở **ranh
   giới adapter tường minh**; alias **không** cứu claim canonical thiếu field.

### 3. Owner record và history

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `sweep_id`, `owner_setup_id`, `assignment_id`, `claim_eligible_at`, `assigned_at` | có | `assignment_id` = hash `(sweep_id, owner_setup_id, claim_eligible_at)` (`smc_sweep_linking.py:93-101`) |
| `pool_id`, `source_ids` | **có** | lineage của pool đã cấp owner; **phải theo claim vào history record** để observation mới của cùng pool không né được consumed (A-D06) |
| `contribution_applied` | chỉ ở projection per-claim | không phải field của authority để tính lại contribution |

Luật bắt buộc:

5. History là authority: sweep đã có record ⇒ giữ nguyên `owner_setup_id`/`assignment_id` (A3-006).
6. Owner chỉ còn trong history, **không có child hiện tại** ⇒ giữ owner/assignment với `claims == []`,
   contribution trên child list hiện tại bằng `0`; không chuyển cho setup muộn (A-D03).
7. Owner hiện tại có nhiều child ⇒ tổng contribution của các child **cùng owner** bằng `1`.
8. Observation mới của **cùng** causal pool (đổi sweep ID/thời điểm/rolling index nhưng giữ
   `pool_id` + `source_ids`) không tạo owner mới; claim khai pool mới phải kèm `source_ids`/lineage chứng
   minh (A-D06).

### 4. Hiện trạng code — nền RED cho F08/F09/F10 (không sửa ở checkpoint A)

| Hành vi hiện tại | Vị trí | Đối chiếu contract |
|---|---|---|
| `claim_time` fallback: thiếu `reclaimed_at` → dùng `sweep_time`/`available_at`; thiếu một field vẫn cấp assignment | `smc_sweep_linking.py:312-326` | Sai luật 1: phải `SWEEP_CLAIM_TIME_MISSING` và không assignment |
| Claim thiếu **cả hai** thời điểm bị bỏ im lặng, không reason | `:337-341` | Sai: cần reason code explicit |
| Không có chuỗi `SWEEP_CLAIM_TIME_MISSING` trong code (chỉ có trong test) | grep `core/` = 0 hit | Phần F08 phải thêm |
| `SweepAssignment` **không** có `pool_id`/`source_ids`; `assignment_id` không gồm lineage | `:55-67`, `:93-101` | Sai luật 8: history không giữ lineage nên không chứng minh được pool identity |
| Nhánh history dựng lại assignment từ record mà không có lineage | `:352-369` | Như trên |
| Sweep chỉ còn trong history (không child hiện tại) ⇒ `assignments == {}` | vòng lặp chỉ chạy theo sweep có trong `claims` (`:352`) | Sai luật 6 (A-D03) |
| Caller dựng claim từ `link.to_dict()` ⇒ chỉ có `sweep_time`, **không** `reclaimed_at` | `core/smc_context.py:4647-4653` | Sai luật 3: caller phải truyền reclaim time tường minh |
| Caller gọi `mark_sweeps_consumed` **không** truyền `assignment_history`/`history_complete` | `core/smc_context.py:4655` | Sai luật 5: replay context cấp lại owner (R72-04) |
| Projection zone không có `claim_eligible_at`/lineage; projection sweep không có lineage | `core/smc_context.py:4662-4671`, `smc_sweep_linking.py:478-488` | Bổ sung ở F10 cùng lineage |
| `pool_id` của sweep hiện là `source.pool_id`/`swing_id` hoặc `kind:level` (`core/smc_context.py:4408-4415`, `:4454`) | — | Chưa phải canonical lineage của A3-005; F06 thay bằng `records.pool_id` |

### 5. Node sẽ khóa contract

| Node | Trạng thái hiện tại | Việc của mã |
|---|---|---|
| `test_r72_02_missing_canonical_claim_time_fails_closed[reclaimed_at]` / `[setup_available_at]` | RED (vẫn cấp owner, dùng timestamp còn lại) | Đã parameterize ở A3-013 (claim giữ field còn lại + lineage); F08 phải fail closed cả hai field, không fallback |
| `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | RED (`KeyError: 'sweep'` — history-only bị mất) | A3-045/A3-046; luật 6 |
| `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` | RED (owner đổi thành `later-owner`) | A3-069 cùng A-D06; caller phải truyền history thật |
| `test_r72_04_same_pool_observation_cannot_bypass_consumption` | GREEN **nhưng pass trivial** (hai claim cùng `sweep_id="sweep"` nên history khớp ID, chưa chứng minh lineage) | A3-046 đổi observation sweep ID/time/rolling index, giữ `pool_id`+`source_ids` |
| Ca control nguồn pool mới + history conflict | chưa có node | A3-047, A3-048 |

### Câu hỏi mở (không tự quyết)

1. **Claim không khai `pool_id`/`source_ids`** (legacy hoặc thiếu provenance): fail closed như thiếu claim
   time, hay nhận với reason riêng? A-D06 chỉ chốt "claim khai pool mới phải có lineage chứng minh", chưa
   nói ca thiếu hẳn lineage. Ảnh hưởng assertion của A3-045/A3-047 nếu muốn khóa theo fail-closed; đề xuất:
   fail closed với reason riêng để không tự chọn nguồn thuận lợi.

## Danh sách candle factory/caller — A3-023

Ghi ngày 2026-09-11. Kiểm kê mọi đường **dựng nến** dùng cho các ca F01 trong
`tests/test_smc_gate72_fix_acceptance.py` (kèm helper read-only của reviewer probe) để A3-027 (validator còn
thiếu) và A3-028 (cadence) dùng làm đầu vào. **Không sửa code** ở mục này.

| # | Factory / đường dựng | Caller (node trong file acceptance) | Timeframe | Bước timestamp | Validate ở đâu | Loại |
|---|---|---|---|---|---|---|
| 1 | `_probe.candles(rows, side="buy", hours=1)` (probe, read-only) | ~15 call site: R72-01 (`test_r72_01_positive_pool_keeps_source_lineage_and_usable_time`, `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels`, `test_r72_01_provisional_source_cannot_create_a_sweep`, `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible`), R72-05 (`test_r72_05_cutoff_equal_invalidated_at_is_terminal[buy]`, `test_r72_05_cutoff_equal_invalidated_at_is_terminal[sell]`, `test_r72_05_cutoff_equal_expired_at_is_terminal[buy]`, `test_r72_05_cutoff_equal_expired_at_is_terminal[sell]`, `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction`), R72-06 (`test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary`), R72-07 (metadata/parity/buffer: `test_r72_07_missing_canonical_atr_is_unknown_and_unusable`, `test_r72_07_missing_canonical_tick_is_unknown_and_unusable`, `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]`, `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[tick_size]`, `test_r72_07_item_and_argument_tick_sources_have_parity`, `test_r72_07_equal_and_outside_buffer_buy_sell`), R72-08, R72-09 | H1 mặc định; **D1 khi `hours=24`** | `START + i*hours` (giờ; 24h = ngày) | ngay trong probe: `assert not validate_smc_candles(values, "D1" if hours == 24 else "H1")` | positive |
| 2 | `_probe.lifecycle(rows, side="buy", hours=24)` (probe, read-only) | `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[buy]`, `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[sell]`, `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[buy]`, `test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags[sell]`, `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[buy]`, `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary[sell]`, `test_r72_08_typed_terminal_projection_reaches_d1_consumer[buy]`, `test_r72_08_typed_terminal_projection_reaches_d1_consumer[sell]` | D1 (`hours=24`) | như #1 (`days` vì `hours=24`) | gián tiếp qua `_probe.candles` (#1) | positive |
| 3 | `_terminal_candles(side, reaction_index)` (file acceptance, dòng 80) | `test_r72_06_terminal_order_before_reaction_is_explicit` (`reaction_index` 20/21/22 × buy/sell) | D1 | `start + timedelta(days=index)` | trong factory: `assert not validate_smc_candles(values, "D1")` | positive |
| 4 | `_metadata_item()` + `_metadata_result(values=None)` (file acceptance) | 8 node R72-07 metadata (missing ATR/tick, nonfinite, conflict, parity, terminal, round-trip) | H1 | `values` mặc định lấy từ #1 | gián tiếp qua #1 | positive |
| 5 | dựng D1 inline trong `test_r72_05_cutoff_equal_invalidated_at_is_terminal` | chính test đó | D1 | `start + timedelta(days=i)` | ngay sau khi dựng: `assert not validate_smc_candles(values, "D1")` | positive |
| 6 | dựng D1 inline trong `test_r72_06_invalidation_precedes_expiry_and_reaction` | chính test đó | D1 | `start + timedelta(days=i)` | ngay sau khi dựng: `assert not validate_smc_candles(values, "D1")` | positive |
| 7 | local `run(rows)` trong `test_r72_07_equal_and_outside_buffer_buy_sell` (dòng 965) | chính test đó (exact/beyond × buy/sell) | **H1** | `start + timedelta(days=i)` ⚠️ **sai cadence** | trong `run`: `assert not validate_smc_candles(values, "H1")` | positive |
| 8 | `module._candles(rows)` của 5 module task59/60/62/63/65 | `test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid` | H1 | do module (bước giờ) | re-validate trong acceptance: `assert not validate_smc_candles(values, "H1"), name` | positive |
| 9 | `module._candles(module._fixture_rows())` của fixture gate56 | `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke` (**A3-056** đổi tên từ `test_r72_09_actual_detector_lifecycle_d1_context_chain_uses_valid_source_fixture`) | H1 | do module | `assert not validate_smc_candles(candles, "H1")` | positive |
| 10 | `_probe.sweep()` + `_probe.zone()` + `_probe.attach()` (probe, read-only) | R72-02/R72-03/R72-04 qua context path | H1 | `candles([(120,121,119,120)]*20)` trong `attach` (bước giờ) | gián tiếp qua #1 | positive |

Kết luận kiểm kê:

1. **Mọi** đường dựng nến ở trên đều đã gọi `validate_smc_candles` với **đúng timeframe** (trực tiếp hoặc
   gián tiếp qua `_probe.candles`); hiện **không** thấy đường nào thiếu validator ⇒ A3-027 xác nhận lại khi bổ sung.
2. **Một** đường sai cadence: #7 — H1 nhưng bước `timedelta(days=i)` (đúng dạng lỗi) ⇒ thuộc **A3-028**.
3. **Không** có fixture invalid-data cố ý trong file acceptance: không có `pytest.raises`/`assert
   validate_smc_candles` nào kỳ vọng validator *thất bại*; các ca negative ở đây là negative về **hành vi**
   (không sweep, không assignment, metadata unknown, terminal giữ nguyên), không phải OHLC sai. Vì vậy không
   có ca nào "validate negative cố ý như positive".
4. Nguồn nến nằm **ngoài** file acceptance (#8, #9) được acceptance re-validate tại chỗ; nếu module đổi fixture
   thì test này bắt được (A3-080 xác minh lại khi audit fixture).

## Timeline D1 terminal — A3-029

Ghi ngày 2026-09-11. Timeline **độc lập** (tính từ quy tắc + fixture, không lấy output production làm expected)
cho fixture D1 terminal dùng bởi nhóm R72-06, để A3-030…A3-032/A3-037 dùng làm chuẩn.

**Fixture:** `_terminal_candles(side, reaction_index)` — **23 nến D1**, `time = 2026-09-01T00:00Z + index ngày`;
consumer `_terminal_lifecycle` truyền `origin_index=0`, `departure_end_index=0`, `tf_minutes=1440`, **không**
truyền `available_at`.

**Quy tắc index ↔ age (không mặc định index = age):** `_age_anchor_index` (`core/smc_lifecycle.py:522-537`)
trả `safe_origin` khi `available_at is None`; fixture này `origin_index = 0` và không có `available_at`
⇒ `age(i) = i − 0 = i`. Nếu fixture truyền `available_at`, anchor là nến đầu có close ≥ mốc đó và
`age(i) = i − anchor ≠ i` — vì vậy mọi mã sau phải tính age từ anchor thật, không suy từ index.

**Lifetime:** `_STALE_AFTER_BARS["D1"] = 20` ⇒ điều kiện expiry là `age > 20` ⇒ mốc terminal đầu tiên là
**index 21** (age 21).

| Index | Age | Open (fixture) | Close D1 (`candle_close_at` = open + 1 ngày) | Vai trò / expected |
|---|---|---|---|---|
| 19 | 19 | `2026-09-20T00:00Z` | `2026-09-21T00:00Z` | Candle touch — mở visit (inside zone `[100,110]`) |
| **20** | **20** | `2026-09-21T00:00Z` | **`2026-09-22T00:00Z`** | **Age 20 = 20, KHÔNG > 20 ⇒ chưa terminal**: exit tại đây (close vượt tolerance nhưng chưa đủ reaction) — reaction hợp lệ nếu `reaction_index=20` (trước terminal) |
| **21** | **21** | `2026-09-22T00:00Z` | **`2026-09-23T00:00Z`** | **Terminal**: age 21 > 20 ⇒ `expiry_index = 21`, `expired_at = 2026-09-23T00:00Z` — reaction tại chính candle này **không** được tạo (A-D05) |
| **22** | **22** | `2026-09-23T00:00Z` | `2026-09-24T00:00Z` | **Sau terminal**: không tạo reaction mới; lịch sử trước terminal giữ nguyên |

Hệ quả cho các ca đã có:

- `test_r72_06_terminal_order_before_reaction_is_explicit[20-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[20-sell]`, `test_r72_06_terminal_order_before_reaction_is_explicit[21-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[21-sell]`, `test_r72_06_terminal_order_before_reaction_is_explicit[22-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[22-sell]` — reaction ở **age 20 < terminal 21** ⇒
  `reacted_at` có thật, visit `completed_reacted` (node **GREEN**).
- `[21-*]` — reaction đặt đúng candle **terminal 21**; `[22-*]` — reaction đặt **sau** terminal ⇒ hợp đồng yêu
  cầu `lifecycle_expired is True` + `reacted_at is None` + `completed_unreacted`. Hiện cả 4 node **RED** vì
  implementation ghi reaction ở index 21/22 (reaction "prospective" vượt mốc expiry) — thuộc **F04**, không
  phải lỗi fixture.
- Fixture thứ hai `test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary` (22 nến D1, cùng origin/anchor,
  idx19 mở visit, idx20 exit `(110.2,110.22,110.15,110.2)`, idx21 candle reaction) có cùng mốc: **expiry tại
  index 21** (`expired_at = 2026-09-23T00:00Z`).

**Kiểm chứng (chỉ để xác nhận, không dùng làm expected):** `_terminal_lifecycle` cho cả 3 `reaction_index`
đều trả `expiry_index = 21`, `expired_at = 2026-09-23T00:00:00+00:00` và `age_bars = 22`; đúng mốc đã tính ở
bảng trên. Khác biệt nằm ở `reacted_at` (hiện có giá trị ở cả 21/22) — chính là gap F04.

## Timeline H4 terminal — A3-033

Ghi ngày 2026-09-11. Bản **đối ứng H4** của [Timeline D1 terminal (A3-029)](#timeline-d1-terminal--a3-029); mọi
con số lấy từ hằng số đã duyệt trong code + quy tắc A-D04/A-D05, **không** thêm quy tắc/ngưỡng mới. Đây là
**fixture đề xuất** cho A3-034…A3-036 (các mã đó viết node; mục này chỉ ghi timeline).

**Hằng số (đọc code):** `_STALE_AFTER_BARS["H4"] = 30` (`core/smc_lifecycle.py:16-27`);
`SMC_TIMEFRAME_INTERVALS["H4"] = 14 400s = 4h` (`core/smc_models.py:24-29`) ⇒
`candle_close_at(open, "H4") = open + 4h`.

**Suy ra từ quy tắc đã dùng cho D1** (lifetime `L` ⇒ touch ở `L−1`, exit ở `L`, terminal ở `L+1`, sau terminal ở
`L+2`, tổng `L+3` nến):

- `L = 30` ⇒ **age 30 = index 30** (chưa terminal vì `30 > 30` sai), **terminal = index 31**, sau terminal =
  index 32 ⇒ fixture cần **33 nến** (index 0…32).
- Đối chiếu chéo: `L = 20` cho D1 ⇒ touch 19 / exit 20 / terminal 21 / sau 22 / **23 nến** — **khớp đúng**
  fixture `_terminal_candles` đang dùng, nên công thức này nhất quán với fixture D1 thật.

**Anchor:** nếu fixture không truyền `available_at` và `origin_index = 0` thì anchor = origin ⇒ `age(i) = i`
(quy tắc `_age_anchor_index`, `core/smc_lifecycle.py:522-537`); có `available_at` thì anchor là nến đầu có close
≥ mốc và `age(i) = i − anchor` — không suy age từ index.

| Index | Age | Open (fixture `start = 2026-09-01T00:00Z`, bước 4h) | Close H4 (open + 4h) | Vai trò / expected |
|---|---|---|---|---|
| 29 | 29 | `2026-09-05T20:00Z` | `2026-09-06T00:00Z` | touch — mở visit (trong zone) |
| **30** | **30** | `2026-09-06T00:00Z` | **`2026-09-06T04:00Z`** | **Age 30 = 30, KHÔNG > 30 ⇒ chưa terminal**: exit tại đây (ngoài vùng mở rộng, chưa đủ reaction) — reaction hợp lệ nếu candle này/ trong window còn **trước** terminal (A3-034) |
| **31** | **31** | `2026-09-06T04:00Z` | **`2026-09-06T08:00Z`** | **Terminal**: `expiry_index = 31`, `expired_at = 2026-09-06T08:00Z`; reaction tại chính candle này **không** được tạo (A-D05, A3-035) |
| **32** | **32** | `2026-09-06T08:00Z` | `2026-09-06T12:00Z` | Sau terminal: không reaction mới; visit/history trước terminal giữ nguyên (A3-036) |

**Cutoff và thứ tự (dùng đúng quy tắc đang áp dụng cho D1, không đổi):** mọi sự kiện đánh giá tại **candle
close** (mô hình closed-bar); cutoff **bằng** mốc `invalidated_at`/`expired_at` là terminal (A-D04); mỗi candle
theo thứ tự availability/cutoff → invalidation/expiry → exit → reaction (A-D05).

**Follow-through window:** `_follow_through_reaction_at` (`core/smc_lifecycle.py:583-634`) quét
`exit_index … exit_index + 3` (bao gồm candle exit), ngưỡng `0.25 * ATR`, và **invalidation trong window có ưu
thế terminal** (gặp invalidation ⇒ trả `None`). Với fixture H4 đề xuất, exit ở index 30 ⇒ window là
`30…33`; nhưng vòng lặp dừng ở terminal index 31 nên reaction sau terminal không được xét.

---

## Mapping coverage §4 — bảy cụm (A3-063)

Nguồn ô: bảng **§4 "Acceptance obligations"** của [fix-plan](smc-task-72-fix-plan.md) (7 cụm × 3 ô:
positive/control — negative/boundary — integration/parity). Node lấy từ
`python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q` ngày 2026-09-11 (**89 node**).

Quy ước ghi node (A3-081): mỗi ô nêu **node chạy được** phải kèm **parameter ID thật** trong ngoặc vuông (`...[buy]`, `...[record_for_other_level]`, …). Tên **không** có ngoặc vuông là **tên họ node** (family) — các param chạy được của nó nằm ở bảng theo dõi theo finding (R72-01…R72-09) trong tài liệu này. Không dùng dạng ngoặc **gộp nhiều param** (gộp hai chiều mua/bán, dải chỉ số, hay dấu ba chấm bên trong ngoặc) như thể là node chạy được; tên lịch sử/đã đổi tên hoặc probe của reviewer được ghi chú ngay tại ô.

Quy ước trạng thái:

- **ĐỦ** — đã có node acceptance chạy được trong file acceptance, assert đúng ô đó.
- **MỘT PHẦN** — có node nhưng chỉ phủ một phần ô; phần thiếu ghi kèm mã A3 sẽ bù.
- **THIẾU** — chưa có node nào; mã A3 trong §8.6 chịu trách nhiệm bù.
- **REFERENCED** — test đã có sẵn ngoài file acceptance (task57–71 hoặc R56); chỉ map/reuse, không tạo bản sao.

### Metadata

| Ô §4 | Node/nguồn hiện có | Trạng thái |
|---|---|---|
| Positive/control: tick argument = tick item; đủ ATR/tick | `test_r72_07_item_and_argument_tick_sources_have_parity[buy]`, `test_r72_07_item_and_argument_tick_sources_have_parity[sell]` | ĐỦ |
| Negative/boundary: missing/invalid, explicit override, đúng/vượt buffer | `test_r72_07_missing_canonical_atr_is_unknown_and_unusable`, `test_r72_07_missing_canonical_tick_is_unknown_and_unusable`, `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]`, `test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable[tick_size]`, `test_r72_07_conflicting_same_scope_tick_sources_fail_closed`, `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[buy]`, `test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle[sell]`, `test_r72_07_equal_and_outside_buffer_buy_sell[buy]`, `test_r72_07_equal_and_outside_buffer_buy_sell[sell]`, `test_r72_07_excursion_override_only_replaces_its_own_rule`, `test_r72_07_equal_tolerance_override_only_replaces_its_own_rule`, `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule` (**A3-067** — xem [Override audit](#override-audit--a3-067)) | ĐỦ |
| Integration/parity: context → lifecycle; nguồn causal, không latest fallback | `test_r72_07_metadata_survives_context_to_typed_round_trip`, `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[expired_by_age]`, `test_r72_07_unknown_metadata_does_not_revive_terminal_zone[already_invalid]` cho phần **context → lifecycle**; phần **nguồn causal / không latest fallback**: `test_r72_07_formation_atr_is_causal_and_never_latest_fallback`, `test_r72_07_formation_and_current_atr_keep_their_own_source` (**A3-068** — formation đọc tại close trước sự kiện, nến tương lai không đổi, thiếu warm-up ⇒ `None`; formation vs current giữ đúng nguồn, timeframe/cutoff fail-closed) | ĐỦ (A3-068) |

### Terminal/reaction

| Ô §4 | Node/nguồn hiện có | Trạng thái |
|---|---|---|
| Positive/control: exit+reaction hợp lệ, trước terminal | `test_r72_06_h4_reaction_before_terminal_is_retained[buy]`, `test_r72_06_h4_reaction_before_terminal_is_retained[sell]`, `test_r72_08_typed_d1_projection_keeps_valid_reaction[buy]`, `test_r72_08_typed_d1_projection_keeps_valid_reaction[sell]`, `test_r72_09_d1_reaction_positive_reads_canonical_lifecycle` | ĐỦ |
| Negative/boundary: invalidation/expiry trước/đúng/sau reaction | `test_r72_06_terminal_order_before_reaction_is_explicit[20-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[20-sell]`, `test_r72_06_terminal_order_before_reaction_is_explicit[21-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[21-sell]`, `test_r72_06_terminal_order_before_reaction_is_explicit[22-buy]`, `test_r72_06_terminal_order_before_reaction_is_explicit[22-sell]`, `test_r72_06_h4_reaction_at_terminal_is_blocked[buy]`, `test_r72_06_h4_reaction_at_terminal_is_blocked[sell]`, `test_r72_06_h4_reaction_after_terminal_is_blocked[buy]`, `test_r72_06_h4_reaction_after_terminal_is_blocked[sell]`, `test_r72_06_invalidation_precedes_expiry_and_reaction[buy]`, `test_r72_06_invalidation_precedes_expiry_and_reaction[sell]`, `test_r72_05_cutoff_equal_invalidated_at_is_terminal[buy]`, `test_r72_05_cutoff_equal_invalidated_at_is_terminal[sell]`, `test_r72_05_cutoff_equal_expired_at_is_terminal[buy]`, `test_r72_05_cutoff_equal_expired_at_is_terminal[sell]`, `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[buy]`, `test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[sell]` | ĐỦ |
| Integration/parity: prefix, repeat, typed round-trip, D1 consumer | Prefix nằm trong phase đầu của `test_r72_05_cutoff_equal_invalidated_at_is_terminal[buy]`, `test_r72_05_cutoff_equal_invalidated_at_is_terminal[sell]` / `test_r72_05_cutoff_equal_expired_at_is_terminal[buy]`, `test_r72_05_cutoff_equal_expired_at_is_terminal[sell]`; repeat + typed: `test_r72_08_typed_terminal_projection_reaches_d1_consumer[buy]`, `test_r72_08_typed_terminal_projection_reaches_d1_consumer[sell]`, `test_r72_06_terminal_state_survives_enrich_restore_enrich[expired-buy]`, `test_r72_06_terminal_state_survives_enrich_restore_enrich[expired-sell]`, `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-buy]`, `test_r72_06_terminal_state_survives_enrich_restore_enrich[invalid-sell]`; D1 consumer: `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` (**RED — F03/F05**), `test_r72_09_d1_expired_source_is_terminal_for_the_consumer` (GREEN) | ĐỦ (1 node RED do core) |

### Pool/sweep

| Ô §4 | Node/nguồn hiện có | Trạng thái |
|---|---|---|
| Positive/control: confirmed usable source; valid excursion/reclaim | `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[buy]`, `test_r72_01_positive_pool_keeps_source_lineage_and_usable_time[sell]`, `test_r72_01_equal_pool_usable_before_sweep_close_is_accepted`, `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[buy]`, `test_r72_01_acceptance_source_must_be_usable_at_sweep_close[sell]`, `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible`, `test_r72_01_single_source_pool_usable_before_sweep_close_is_accepted` (**A3-043/b** — control GREEN: pool single-source usable `stamp(1)` **trước** close sweep `stamp(2)` vẫn được nhận); `test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible` (**A3-039/A3-041** — target event lọc theo level + candle index, **không** khóa priority/cardinality); `test_r72_01_equal_pool_usable_before_sweep_close_is_accepted` (**A3-040** — target event theo level + `index 2`, không khóa priority/cardinality) | ĐỦ (A3-039/A3-040/A3-041/A3-043/b) |
| Negative/boundary: before confirmation, provisional/missing source, equal-source time, threshold equality | `test_r72_01_provisional_source_cannot_create_a_sweep` (provisional), `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[buy]`, `test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels[sell]` (thiếu `records`), `test_r72_01_missing_pool_provenance_fails_closed[record_for_other_level]`, `test_r72_01_missing_pool_provenance_fails_closed[no_sources]`, `test_r72_01_missing_pool_provenance_fails_closed[dangling_source_id]`, `test_r72_01_missing_pool_provenance_fails_closed[source_without_provenance_id]`, `test_r72_01_missing_pool_provenance_fails_closed[source_without_usable_at]` (**A3-064**), `test_r72_01_excursion_threshold_is_strict[below-buy]`, `test_r72_01_excursion_threshold_is_strict[below-sell]`, `test_r72_01_excursion_threshold_is_strict[equal-buy]`, `test_r72_01_excursion_threshold_is_strict[equal-sell]`, `test_r72_01_excursion_threshold_is_strict[beyond-buy]`, `test_r72_01_excursion_threshold_is_strict[beyond-sell]` (**A3-065** — đúng biên chưa đủ), `test_r72_01_equal_pool_without_usable_source_does_not_exist`, `test_r72_01_source_usable_after_sweep_close_is_rejected[buy]`, `test_r72_01_source_usable_after_sweep_close_is_rejected[sell]`, `test_r72_01_equal_pool_usable_time_is_max_of_both_sources` (**A3-043/a** — negative nay chỉ khóa event **của đúng target equal pool** theo level, **không** cấm single-source sweep hợp lệ; vế được phép đó có control riêng `test_r72_01_single_source_pool_usable_before_sweep_close_is_accepted` — **A3-043/b**, GREEN) | ĐỦ (missing source/provenance: A3-064; threshold equality: A3-065) |
| Integration/parity: actual producer; pool ID/provenance qua prefix/batch | `test_r72_01_actual_swing_producer_feeds_pool_and_sweep` cho **actual producer**; **prefix/batch + rolling index**: `test_r72_01_pool_sweep_evidence_survives_future_bars`, `test_r72_01_pool_sweep_identity_survives_rolling_index`, `test_r72_01_pool_identity_survives_source_permutation` (**A3-066/a…/e**). Từ 2026-09-11 ba node này **assert canonical `records.pool_id`/`source_ids`/`usable_at` và nối `source_pool_id` → `pool_id`**, kèm lọc cutoff theo `reclaimed_at`; `source_ids` được khóa theo **danh sách sort ổn định** (node /e cố ý đặt causal order ngược sort order để phân biệt hai quy tắc); cả ba **RED — implementation (F06)** vì `core/` chưa phát `records` (xem A3-064/A3-010). Expected canonical đã được viết ở A, không còn hoãn tới F06. *(Cập nhật F06/r1 2026-09-11: producer phát `usable_at` ⇒ cả ba node có `records`; permutation đã **GREEN**, hai node prefix/batch + rolling **PASS toàn bộ assertion pool** và chỉ còn fail ở dòng nối `source_pool_id` → owner **F07**.)* | ĐỦ về coverage (2 node còn RED do dòng nối sweep — F07) |

### Owner

| Ô §4 | Node/nguồn hiện có | Trạng thái |
|---|---|---|
| Positive/control: earliest claim, same-time tie | `test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time` (early-far thắng late-near), `test_r72_02_same_time_tie_is_stable_under_claim_permutation` (helper: cùng claim time ⇒ setup ID ổn định, cả hai thứ tự), `test_r72_02_context_same_time_tie_follows_stable_setup_id` (**A3-073** — cùng tie ở tầng context; **RED — F08** vì caller theo zone ID) | ĐỦ về coverage (1 node RED do core) |
| Negative/boundary: nearer-late, unrelated side/distance/time, missing claim time | `test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time` (nearer-late), `test_r72_02_opposite_side_claim_cannot_own_a_sweep` (**A3-070**), `test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep` (**A3-071**), `test_r72_02_claim_outside_time_window_cannot_own_a_sweep` (**A3-072** — biên cửa sổ bao gồm, ngoài cửa sổ fail closed), `test_r72_02_missing_canonical_claim_time_fails_closed[reclaimed_at]`, `test_r72_02_missing_canonical_claim_time_fails_closed[setup_available_at]` | ĐỦ (A3-070/071/072) |
| Integration/parity: context enumerate→assign→project, input permutation | Permutation có ở `test_r72_02_same_time_tie_is_stable_under_claim_permutation` (helper) và `test_r72_02_context_owner_follows_claim_time_under_input_permutation` (**A3-069** — chạy cả hai thứ tự qua `_attach_zone_sweep_links`, đọc payload sweep được chiếu ⇒ caller thực sự enumerate→assign→project; owner theo claim time **RED — F08** hiện đang theo distance) | ĐỦ về coverage (1 node RED do core) |

### Contribution

| Ô §4 | Node/nguồn hiện có | Trạng thái |
|---|---|---|
| Positive/control: nhiều child cùng owner tổng 1 | `test_r72_03_acceptance_contribution_is_selected_within_owner_children` | ĐỦ |
| Negative/boundary: non-owner ID nhỏ hơn, duplicate, owner absent | `test_r72_03_acceptance_contribution_is_selected_within_owner_children` (non-owner `late/a-nonowner` có ID nhỏ hơn), `test_r72_03_duplicate_owner_children_keep_one_contribution_under_permutation`, `test_r72_03_historical_owner_without_current_child_gets_zero_contribution` | ĐỦ |
| Integration/parity: thêm metadata/child không tăng/mất evidence | `test_r72_03_contribution_is_counted_per_sweep_not_per_list` (**A3-074** — 2 sweep độc lập cùng owner, multi-family + metadata + duplicate: mỗi sweep đúng 1 contribution, tổng danh sách 2 ⇒ **không** cap toàn danh sách; đảo thứ tự input không đổi kết quả) | ĐỦ (A3-074) |

### Consumed

| Ô §4 | Node/nguồn hiện có | Trạng thái |
|---|---|---|
| Positive/control: restore đúng assignment | `test_r72_04_assignment_survives_json_restore_with_late_only_window`, `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` | ĐỦ |
| Negative/boundary: late-only window, missing/inconsistent history, repeated same-pool observation | `test_r72_04_assignment_survives_json_restore_with_late_only_window` (late-only), `test_r72_04_incomplete_history_returns_explicit_reason` (missing), `test_r72_04_conflicting_assignment_history_fails_closed` (inconsistent), `test_r72_04_same_pool_observation_cannot_bypass_consumption` (repeated same-pool) | ĐỦ |
| Integration/parity: first run→serialize→restore→repeat, không đổi owner/ID | `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` phủ replay trên context; **vòng run→JSON→restore→repeat trên caller thực tế** (không chỉ cùng dict trong RAM) chưa có node | MỘT PHẦN — thiếu A3-078 |

### Fixtures/fill

| Ô §4 | Node/nguồn hiện có | Trạng thái |
|---|---|---|
| Positive/control: valid BUY/SELL, partial/full fill bounds | `test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid` (valid BUY/SELL T59/60/62/63/65); partial/full fill bounds: REFERENCED `tests/test_smc_fvg_fill_task62.py` + `test_r72_09_full_fvg_fill_is_not_a_break` (**A3-079** — fill giữ identity/bounds, full fill **không** là break) | ĐỦ (A3-079) |
| Negative/boundary: invalid data có chủ đích tách khỏi positive; no-break/full-fill | **Invalid-data cố ý**: `test_r72_09_intentional_invalid_data_reports_its_own_reason` (**A3-080** — bar `(112,113,111.2,110.2)` ⇒ reason riêng `SMC_OHLC_INVALID` tại `index 4`; control sửa theo F01-T60-BUY ⇒ `()`); no-break/full-fill: REFERENCED task62 + `test_r72_09_full_fvg_fill_is_not_a_break` (**A3-079**) + R56 | ĐỦ (A3-079/080) |
| Integration/parity: detector→lifecycle; original IDs/bounds và R56 invariant | `test_r72_09_d1_source_is_confirmed_by_fixture_break`, `test_r72_09_d1_confirmed_zone_timeline_comes_from_fixture_retest`, `test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke` (detector→confirm→enrich→lifecycle); R56 invariant: REFERENCED `tests/test_smc_r56_01_session_acceptance.py` + `test_r56_02_ob_requires_atr_ids_validity_and_causal_close_provenance` | ĐỦ (R56: REFERENCED) |

**Kết luận A3-063:** 21 ô §4 = **13 ô ĐỦ** (3 trong số đó có phần phải reuse test có sẵn — REFERENCED: fill bounds ở ô Fixtures positive, no-break/full-fill ở ô Fixtures negative, R56 invariant ở ô Fixtures integration) + **6 ô MỘT PHẦN** (Metadata integration; Pool negative; Pool integration; Owner negative; Owner integration; Consumed integration) + **2 ô THIẾU** (Contribution integration; Fixtures negative phần invalid-data cố ý). Phần còn thiếu được giao đúng mã: A3-065 (threshold equality), A3-066 (prefix/batch provenance), A3-068 (nguồn causal/không latest fallback), A3-069 (context enumerate→assign→project), A3-070/071/072 (owner eligibility), A3-074 (contribution integration + hai sweep độc lập), A3-078 (run→restore→repeat trên caller), A3-079 (fill audit), A3-080 (invalid-data tách khỏi positive). Các mã này **chưa làm** ở A3-063. → **Cập nhật bản trình A lần4 (2026-09-11):** toàn bộ các mã được giao ở câu trên nay **đã IMPLEMENTED** — A3-064, A3-065, A3-066, A3-068, A3-069, A3-070, A3-071, A3-072, A3-074, A3-078, A3-079, A3-080 (trạng thái và bằng chứng ở `fix-progress` hàng tương ứng). Vì vậy tổng **13 ĐỦ / 6 MỘT PHẦN / 2 THIẾU** phía trên là **ảnh chụp lịch sử tại thời điểm A3-063**, không phải trạng thái hiện hành; các ô từng MỘT PHẦN/THIẾU nay đều đã có node (Metadata integration: A3-067/A3-068; Pool negative: A3-064/A3-065; Pool integration: A3-066; Owner negative: A3-070/071/072; Owner integration: A3-069/A3-073; Consumed integration: A3-074/A3-078; Contribution integration: A3-074; Fixtures negative invalid-data: A3-080).

---

## Override audit — A3-067

Các **explicit override** đang được `core/` hỗ trợ (đọc trực tiếp từ chữ ký hàm, không thêm mới), rule mà
chúng thay, và giới hạn "chỉ thay rule đó":

| Parameter | Nơi nhận | Rule bị thay | Chỉ thay rule đó — không cứu gì khác | Node |
|---|---|---|---|---|
| `excursion_buffer` | `detect_liquidity_sweeps(..., excursion_buffer=)` | excursion `max(2*tick, 0.10*ATR)`; phải finite và `>= 0` (nếu không ⇒ `ValueError`) | Source vẫn phải **eligible** (`confirmed` + `usable` + non-provisional) — override không cứu source provisional/không usable/không confirmed | `test_r72_07_excursion_override_only_replaces_its_own_rule` |
| `equal_tolerance` | `detect_liquidity_pools(..., equal_tolerance=)` | tolerance gộp equal-level `max(2*tick, 0.10*ATR)`; phải finite và `>= 0` | Source vẫn phải eligible; override không ghép được cặp khi một source không usable; `swing_lows`/`swing_highs` vẫn giữ level | `test_r72_07_equal_tolerance_override_only_replaces_its_own_rule` |
| `zone_tolerance` | `analyze_zone_lifecycle(..., zone_tolerance=)` | tolerance overlap `max(1*tick, 0.05*ATR)` | **Không** thay buffer invalidation (vẫn `max(1*tick, 0.05*ATR)` tính từ metadata) và **không** tạo metadata: thiếu tick/ATR ⇒ rule phụ thuộc metadata **không tính được** ⇒ threshold `None` + `metadata_state unknown` + reason, **không** `0.0` (A3R3-02) | `test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule` |
| `break_buffer` | `analyze_zone_lifecycle(..., break_buffer=)`; `enrich_zones` forward `item["break_buffer"]` | ngưỡng invalidation `max(1*tick, 0.05*ATR)` | Không thay tolerance overlap; không tạo metadata — cùng semantics `unknown`/`None` khi thiếu tick/ATR, và `unknown` **không** tự tạo `broken` | như trên |
| `tick_size` (đối số) | lifecycle/context seams | nguồn tick để tính các ngưỡng | **A-D07**: khi item có tick **mâu thuẫn**, đối số không tự thắng — fail closed; khi hai nguồn đồng ý thì parity | **reuse** `test_r72_07_conflicting_same_scope_tick_sources_fail_closed`, `test_r72_07_item_and_argument_tick_sources_have_parity[buy]`, `test_r72_07_item_and_argument_tick_sources_have_parity[sell]` |

Ghi chú kiểm kê (đọc code, không sửa):

- `enrich_zones` **không** có tham số `zone_tolerance`; nó chỉ forward `available_at`, `tick_size`,
  `atr_current`, `break_buffer` từ item vào `analyze_zone_lifecycle`.
- `structure_break_buffer(atr_value, tick_size)` **không** có override: cần **cả hai** nguồn, thiếu một ⇒
  `None` (đã kiểm ở A3-015/A3-016/A3-017). Không thêm override mới ở A3-067.
- Các override trên đều **chỉ** thay giá trị ngưỡng của rule tương ứng; điều kiện nguồn/provenance/eligibility
  nằm ở nhánh khác và giữ nguyên (3 node A3-067 kiểm đúng tính chất đó).

[§8]: smc-task-72-fix-plan.md#8-checklist-rất-nhỏ-cho-checkpoint-a-lần-3
