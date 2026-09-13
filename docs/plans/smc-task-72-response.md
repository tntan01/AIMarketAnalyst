# Gate72 — Nghiệm thu cuối — APPROVED

## 0. Quyết định Tech Lead — 2026-09-12

**Checkpoint D PASS; task72 APPROVED. R72-01…R72-09 CLOSED trong phạm vi gate72 đã chốt.** A/B/C PASS giữ nguyên; F11 đã nghiệm thu. Các đoạn WAITING_REVIEW/chưa APPROVED bên dưới là bản trình lịch sử của coder, không thay quyết định này. Sổ quyết định: fix-progress §A3.157.

Reviewer đọc hai chuỗi end-to-end và chạy độc lập full §5: **983 passed, 0 failed**; reviewer probes **16 passed**; task57–71 **108 passed**. Acceptance129 + retained854 =983. Năm hash core + hash acceptance khớp manifest mục6; probe/golden/4 R56 **6/6 không đổi**. Hash acceptance được duyệt: `978AA7ECD044B9D41FF7AEBCDE650D2D5191DB5BAD8869D5C709A73A317E8E11`.

| Finding | Quyết định | Căn cứ |
|---|---|---|
| R72-01 | CLOSED | Pool/source-time, canonical lineage và causal gate; actual producer chain; legacy boundary tường minh |
| R72-02 | CLOSED | Owner theo causal claim time, tie-break, missing-time fail closed qua caller |
| R72-03 | CLOSED | Contribution chỉ trong owner children; duplicate/permutation và history-only controls |
| R72-04 | CLOSED | Replay/JSON restore, same-pool observation qua caller, conflicting history fail closed |
| R72-05 | CLOSED | Terminal D1 consumer, canonical thắng flags legacy, positive prefix/history |
| R72-06 | CLOSED | Expiry/invalidation trước reaction, D1/H4 boundaries và prefix parity |
| R72-07 | CLOSED | Metadata source/unknown/override và typed round-trip; giữ terminal/history khi thiếu nguồn |
| R72-08 | CLOSED | Canonical invalid/unusable nhất quán qua typed/enrich/restore |
| R72-09 | CLOSED | Valid fixtures, fill/identity controls và hai chuỗi actual producer tại mục3 |

**Giới hạn phê duyệt:** implementation/evidence task57–72 theo kế hoạch, không chứng nhận giao dịch có lợi nhuận/live execution hoặc rollout canonical vào Analyze/Scanner. Route legacy, pool cap và các quyết định G1/G2 giữ phạm vi đã chốt; deferred cleanup không được biến thành yêu cầu làm lại gate. Hai ca thiếu usable_at không phải bằng chứng temporal độc lập; các ca explicit usable-time/producer bổ sung bằng chứng đó. Thiết lập này không cho phép tự chuyển production sang canonical.

**Task72 đã hoàn tất; task73 hết bị chặn bởi gate72 nhưng chưa được thực hiện.** Không sửa code/test trong lượt review, không commit/reset. Đính chính nhãn baseline trong bản trình: 116 node/65F51P là snapshot A lần3, không phải baseline ban đầu F00. Mục7.8 “reviewer chưa chạy F11” đã được quyết định này thay thế.

**Ngày:** 2026-09-12. **Trạng thái:** F00…F11 đã thực hiện; **checkpoint D = `WAITING_REVIEW`**. A/B/C **PASS** theo §A3.129/§A3.141/§A3.155. **Gate72 chưa APPROVED**, 9 finding chưa CLOSED, **chưa task73**, chưa production rollout.

Đây là **báo cáo cuối duy nhất** của chuỗi sửa gate72 (không tạo báo cáo phụ). Nhật ký chi tiết theo từng lượt nằm ở [fix-progress](smc-task-72-fix-progress.md); ma trận case-level ở [acceptance-matrix](smc-task-72-acceptance-matrix.md); kế hoạch/phạm vi ở [fix-plan](smc-task-72-fix-plan.md).

---

## 1. Phạm vi đã đạt

| Hạng mục | Kết quả trên snapshot trình D |
|---|---|
| Acceptance `tests/test_smc_gate72_fix_acceptance.py` | **129 node — 129 passed / 0 failed** (baseline F00: 116 node, 65 failed / 51 passed) |
| Reviewer probes `docs/plans/probes/test_smc_gate72_review.py` | **16 node — 16 passed / 0 failed** (baseline: 13 failed / 3 passed) |
| task57–71 (15 file) | **108 passed** (không đổi suốt chuỗi) |
| Retained SMC + 6 file integration (loại acceptance) | **854 passed** (không đổi) |
| Full §5 (acceptance + retained) | **983 passed / 0 failed** |
| Artifact bảo vệ | **6/6 khớp ledger F00** (probe + canonical golden + 4 R56) |
| `git diff --check` | sạch |

**RED còn lại: 0.** Không mất GREEN ở bất kỳ cụm nào; không giảm assertion, không skip/xfail, không sửa probe/golden/R56 để làm xanh.

---

## 2. Mapping R72-01…09 → nguyên nhân gốc → sửa → node/evidence

| Finding | Nguyên nhân gốc | Sửa (file/hàm) | Evidence chính (node thật) |
|---|---|---|---|
| **R72-01** (P1) Sweep phát trước source confirmation; pool mất provenance thời gian | Pool chỉ có level numeric, không có identity/provenance; sweep dựng candidate từ key numeric và không có cổng thời gian; claim của caller không mang lineage | `smc_context.py`: `detect_liquidity_pools` phát container canonical `records`; `_confirmed_swing_points` phát `usable_at`; `detect_liquidity_sweeps` dựng candidate **chỉ** từ `records`, nối `source_pool_id` = `records.pool_id`, cổng `usable_at <= reclaimed_at`; `_attach_zone_sweep_links` truyền canonical provenance + `reclaimed_at` thật | `positive_pool_keeps_source_lineage_and_usable_time[buy]`/`[sell]`, `pool_identity_survives_source_permutation`, `pool_sweep_evidence_survives_future_bars`, `canonical_sweep_requires_pool_records_not_numeric_levels[buy]`/`[sell]`, `missing_pool_provenance_fails_closed[5]`, `acceptance_source_must_be_usable_at_sweep_close[buy]`/`[sell]`, `source_usable_after_sweep_close_is_rejected[buy]`/`[sell]`, `actual_swing_producer_feeds_pool_and_sweep` + probe `test_r72_01_sweep_must_not_precede_source_confirmation[buy]`/`[sell]` |
| **R72-02** (P1) Linker chọn setup theo khoảng cách trước ownership | `associate_sweeps_to_zones` xếp hạng `(distance_atr, departure_gap, …)` và khoá setup ngay ở bước enumerate; `claim_time` lấy mốc còn lại/alias thay mốc thiếu | `smc_sweep_linking.py`: rank theo claim time `max(reclaimed_at, setup_available_at)` → setup ID; `claim_time` buộc đủ hai mốc cho claim canonical + `SWEEP_CLAIM_TIME_MISSING`; `setup_availability_by_owner` chốt availability theo **setup** | `acceptance_context_ranks_all_eligible_claims_by_causal_time`, `context_owner_follows_claim_time_under_input_permutation`, `context_same_time_tie_follows_stable_setup_id`, `claim_outside_distance_boundary_cannot_own_a_sweep`, `claim_outside_time_window_cannot_own_a_sweep`, `opposite_side_claim_cannot_own_a_sweep`, `missing_canonical_claim_time_fails_closed[reclaimed_at]`/`[setup_available_at]` + probe `test_r72_02_context_…before_distance_rank` |
| **R72-03** (P2) Child non-owner chiếm slot contribution | `contribution_winner` chọn trên **toàn bộ** claims rồi mới kiểm owner ⇒ non-owner thắng khoá và vế owner chặn luôn owner (tổng 0) | `assign_sweep_ownership`: chọn winner **trong owner children**, tie-break `(zone_id, visit_id, input order)` giữ nguyên | `acceptance_contribution_is_selected_within_owner_children`, `duplicate_owner_children_keep_one_contribution_under_permutation`, `contribution_is_counted_per_sweep_not_per_list`, `historical_owner_without_current_child_gets_zero_contribution` + probe `test_r72_03_nonowner_child_cannot_take_contribution_slot` |
| **R72-04** (P1) Context gán lại owner/assignment của sweep đã consumed | Caller không truyền history; history tra chỉ theo `sweep_id`; record không tôn trọng được thì rơi xuống nhánh cấp owner mới; owner history-only không được phát assignment; sweep consumed vẫn link cho setup khác | `smc_sweep_linking.py`: `SweepAssignment` mang `pool_id`/`source_ids`; tra history theo sweep ID → **causal pool lineage**; `conflicting_history` fail closed + `SWEEP_OWNER_HISTORY_CONFLICT`; owner history-only vẫn phát assignment; sweep consumed chỉ link lại bởi chính setup sở hữu. `smc_context.py`: caller dựng `assignment_history` từ payload + giữ `linked_zone_id` đã biết | `acceptance_context_preserves_consumed_assignment_on_replay`, `context_repeat_after_json_restore_keeps_assignment`, `same_pool_observation_cannot_bypass_consumption`, `conflicting_assignment_history_fails_closed`, `incomplete_history_returns_explicit_reason`, `assignment_survives_json_restore_with_late_only_window`, `caller_same_pool_observation_keeps_consumption`, `caller_canonical_claim_without_reclaim_time_gets_no_owner`, `conflicting_history_is_order_independent_and_fails_closed` + probe `test_r72_04_context_must_not_reassign_already_consumed_sweep` |
| **R72-05** (P1) D1 canonical lifecycle đã broken vẫn cấp reaction | `build_d1_reaction_evidence` chỉ đọc cờ legacy, không đọc canonical terminal của lifecycle/typed zone | `smc_confluence.py::build_d1_reaction_evidence`: cổng canonical terminal đọc **cả** typed/serialized zone **và** `ZoneLifecycle`, gồm mốc `invalidated_at`/`expired_at` **bao gồm** tại cutoff ⇒ `valid=False`, `score=0`, reason `D1_REACTION_STALE` | `acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction[buy]`/`[sell]`, `serialized_terminal_mapping_overrides_legacy_reaction_flags[buy]`/`[sell]`, `cutoff_equal_invalidated_at_is_terminal[buy]`/`[sell]`, `cutoff_equal_expired_at_is_terminal[buy]`/`[sell]`, `zone_nonterminal_defaults_cannot_mask_active_lifecycle_terminal` + probe `test_r72_05_broken_d1_lifecycle_cannot_supply_active_reaction[buy]`/`[sell]` |
| **R72-06** (P2) Follow-through vượt ranh giới expiry | Vòng tìm reaction không dùng cùng biên lifetime như lifecycle chính | `smc_lifecycle.py`: `_expiry_boundary_index` + `_follow_through_reaction_at` nhận `terminal_index` ⇒ cắt cửa sổ follow-through tại biên | `acceptance_reaction_cannot_cross_expiry_boundary[buy]`/`[sell]`, `terminal_order_before_reaction_is_explicit[20/21/22-buy/sell]`, `invalidation_precedes_expiry_and_reaction[buy]`/`[sell]`, `h4_reaction_before/at/after_terminal_*` + probe `test_r72_06_expiry_candle_cannot_create_reaction_for_earlier_exit[buy]`/`[sell]` |
| **R72-07** (P1) Tick bị mất; thiếu metadata thành threshold 0 | `enrich_zones` không forward tick vào lifecycle; metadata thiếu ⇒ `0.0` thay vì unknown | `smc_lifecycle.py` threshold metadata-dependent trả `None` + reason; `smc_context.enrich_zones` forward tick; `smc_models` mang `metadata_state`/`metadata_reason` | `acceptance_explicit_tick_is_forwarded_to_lifecycle[buy]`/`[sell]`, `item_and_argument_tick_sources_have_parity[buy]`/`[sell]`, `missing_canonical_atr_is_unknown_and_unusable`, `missing_canonical_tick_is_unknown_and_unusable`, `nonfinite_canonical_metadata_is_unknown_and_unusable[atr_current]`/`[tick_size]`, `conflicting_same_scope_tick_sources_fail_closed`, `known_expired/known_invalid_is_preserved_when_metadata_is_missing`, `lifecycle_threshold_overrides_only_replace_their_own_rule`, `formation_atr_is_causal_and_never_latest_fallback` + probe `test_r72_07_enrich_must_forward_explicit_tick_to_lifecycle[buy]`/`[sell]` |
| **R72-08** (P1) Zone invalidated vẫn giữ confirmed/usable | `enrich_zones` không chiếu terminal canonical; cờ legacy thắng canonical | `smc_context.enrich_zones` chiếu canonical terminal (`invalid` ⇒ status invalid + `usable=False` + `broken=True`, giữ `invalidated_at`/reason/history; invalidation thắng expiry); `smc_models.SmcZone` có `usable`, canonical `invalid` thắng cờ legacy | `acceptance_invalidated_projection_is_not_confirmed_usable[buy]`/`[sell]`, `invalid_canonical_zone_survives_typed_round_trip_consistently`, `canonical_invalid_status_wins_legacy_boolean[False]`/`[True]`, `typed_terminal_projection_reaches_d1_consumer[buy]`/`[sell]`, `typed_expired_projection_blocks_d1_and_keeps_history[buy]`/`[sell]` + probe `test_r72_08_invalidated_zone_must_not_keep_confirmed_usable_flags[buy]`/`[sell]` |
| **R72-09** (P2) Fixture OHLC không hợp lệ; thiếu bằng chứng end-to-end | Fixture task57–71 chứa bar sai (close dưới low) và các case dựa trên snapshot tương lai | Sửa 5 fixture (F01) giữ nguyên ý nghĩa ca; thêm validator vào factory; positive control dùng **prefix thật** thay vì rewind payload terminal; tách ca invalid-data có chủ đích | `acceptance_corrected_task57_71_positive_fixtures_are_valid`, `intentional_invalid_data_reports_its_own_reason`, `full_fvg_fill_is_not_a_break`, `d1_invalidated_source_is_terminal_for_the_consumer`, `d1_expired_source_is_terminal_for_the_consumer`, `h1_candidate_chain_reaches_d1_consumer_smoke` + probe `test_r72_09_existing_task60_positive_fixture_must_have_valid_ohlc` |

**Tách bạch mức bằng chứng:** mỗi hàng ở trên có **cả** node helper (đơn vị) **và** node chạy qua caller/producer thật (integration). Các kết luận end-to-end ở mục 3 **không** suy từ tổng số PASS cũng không suy từ các helper test độc lập.

---

## 3. Hai chuỗi end-to-end (nghĩa vụ F11)

### Chuỗi (a) actual swing → pool → sweep → linked setup children → assignment → repeat/JSON restore

Node: **`test_r72_chain_actual_producer_pool_sweep_reaches_owner_and_survives_restore`** (thêm ở F11 — trước đó chuỗi này chỉ có bằng chứng rời: producer→pool→sweep ở A3-044/A3-066 và link→assignment→restore dùng sweep tổng hợp của probe).

| Mắt xích | Nguồn thật | Giá trị khẳng định (suy từ fixture) |
|---|---|---|
| swing producer | `external_swing_points(values, symbol="EURUSD", timeframe="H1", lookback=2)` trên 16 bar H1 `_POOL_CAUSAL_ROWS` | pivot low `index 4`, level `99.5`, `pivot_time stamp(4)`, `confirmed_at = usable_at = stamp(7)` |
| pool | `detect_liquidity_pools(values, swings, tick_size=0.1, atr_value=1.0)` | record `swing_low` level `99.5`, `source_ids = [<swing_id>]`, `usable_at = stamp(7)` |
| sweep | `detect_liquidity_sweeps(..., causal_only=True, lookback_bars=len(values), liquidity_pools=pools)` | event `index 10`, level `99.5`, `reclaimed_at = stamp(11)`; **lineage:** `sweep["source_pool_id"] == record["pool_id"]` |
| link + assignment | `_attach_zone_sweep_links((("demand", zones),), sweeps, candles=values, …)` với zone setup `producer-setup` (available `stamp(13)`, bounds `[99.0, 100.0]`) và zone setup `later-setup` (available `stamp(15)`) | owner `producer-setup`; `claim_eligible_at = max(stamp(11), stamp(13)) = stamp(13)`; `linked_zone_id = "producer-child"`; contribution owner `True`, child `later-setup` không link / không owner / không contribution |
| repeat | attach lại cùng payload | owner + `assignment_id` giữ nguyên |
| JSON restore | `json.loads(json.dumps(sweeps))` rồi attach cửa sổ **late-only** | owner, `assignment_id`, `linked_zone_id`, `claim_eligible_at` giữ nguyên sau restore |

### Chuỗi (b) actual confirmed zone → visit → exit/reaction → invalidation/expiry → D1 evidence

Chuỗi này đã có bằng chứng đầy đủ từ A3-056…A3-062 (không cần thêm node):

| Mắt xích | Node | Nội dung |
|---|---|---|
| detector candidate → confirmed zone | `test_r72_09_d1_source_is_confirmed_by_fixture_break` (A3-057) | `detect_order_block_candidates` + `replay_smc_structure` thật ⇒ zone `confirmed`, bounds/ID từ fixture |
| confirmed → enrich → visit timeline | `test_r72_09_d1_confirmed_zone_timeline_comes_from_fixture_retest` (A3-058) | `enrich_zones` trên retest bars: `entered_at`/`exited_at`/`reacted_at` = close của bar 38/40/41; không broken/expired/stale |
| typed round-trip | `test_r72_09_d1_enriched_zone_survives_typed_restore` (A3-059) | identity/bounds/lifecycle sống qua `SmcZone` → dict → `SmcZone` |
| reaction hợp lệ → D1 | `test_r72_09_d1_reaction_positive_reads_canonical_lifecycle` (A3-060) | `valid=True`, `score=1.0`, `source_visit_id` = canonical visit, reason `D1_REACTION_COMPLETED_REACTED`; control bỏ canonical visit + cờ legacy ⇒ invalid |
| invalidation → D1 | `test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer` (A3-061) | tiền tố tới invalidation ⇒ `valid=False`, `score=0`, reason `D1_REACTION_STALE` |
| expiry → D1 | `test_r72_09_d1_expired_source_is_terminal_for_the_consumer` (A3-062) | tương tự cho expiry; `typed_expired_projection_blocks_d1_and_keeps_history[buy]`/`[sell]` giữ history |

---

## 4. Quyết định checkpoint (A/B/C) và các điểm TL đã chốt

| Checkpoint | Quyết định | Sổ |
|---|---|---|
| **A** (lần 4) | **PASS** — expected/interface đủ chuẩn để sửa core; 5/5 nhóm A3R3 chấp nhận | §A3.129 |
| **B** (lần 4) | **PASS** — cụm lifecycle → typed projection → D1 (F02–F05) | §A3.141 |
| **C** | **PASS** sau 3 lần trình (C-R1/C-R2 rồi phần reclaim-time của C-R1) | §A3.151 → §A3.152 → §A3.153 → §A3.155 |
| **D** | **WAITING_REVIEW** (bản này) | — |

Quyết định kèm theo đã chốt: `usable_at = confirmed_at` cho confirmed/usable/non-provisional (§A3.143); boundary legacy tường minh cho route công khai `pool_provenance="legacy"` (§A3.146); G1 = availability tổng hợp của setup là **min instant hợp lệ** các child; G2 = thứ hạng **completeness/claim time trước, class sau**, setup-scoped chỉ ưu tiên khi **đồng hạng** (§A3.153); không bổ sung invariant `assignment.contribution_applied` ↔ tổng claims.

---

## 5. Commands/results — chạy mới trên cùng snapshot trình D (2026-09-12)

```text
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q
  129 tests collected
python -m pytest tests/test_smc_gate72_fix_acceptance.py --collect-only -q -k "not chain_actual_producer"
  128/129 tests collected (1 deselected)          ← Δcollection đúng +1, không mất node cũ
python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=line
  129 passed / 0 failed
python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=line
  16 passed / 0 failed
$gate72Tests = @(rg --files tests -g '*task5[7-9].py' -g '*task6[0-9].py' -g '*task7[01].py')
python -m pytest @gate72Tests -q --tb=short
  108 passed
$retainedSmcTests = @(rg --files tests -g 'test_smc*.py' | Where-Object { $_ -notmatch 'test_smc_gate72_fix_acceptance.py$' })
python -m pytest @retainedSmcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q --tb=line
  854 passed
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/… -q --tb=no
  983 passed / 0 failed
git diff --check
  sạch (exit=0)
```

**Đối chiếu inventory node (không chỉ so tổng count):** không node cũ nào bị xoá hoặc đổi tên ở F11 (`-k "not chain_actual_producer"` ⇒ đúng 128 node cũ còn nguyên); retained 854 **không đổi** suốt chuỗi. Danh sách node **thêm** theo từng mốc: 116 (A) → 118 (A3-066/e, A3-043/b) → 121 (3 regression B) → 123 (F06/r1 ×2) → 125 (F07/r1 ×2) → 127 (C-R1/C-R2 ×2) → 128 (C-R1 reclaim-time ×1) → **129 (F11 ×1: `test_r72_chain_actual_producer_pool_sweep_reaches_owner_and_survives_restore`)**. Không node nào bị đổi tên trong F06→F11.

---

## 6. Manifest — hash code/tests và fingerprint bảo vệ

| Artifact | SHA256 |
|---|---|
| `core/smc_context.py` | `0B87C6349DBAA072F1D0F04D50C84CBB1AA9DDEF5ACFDC97EA8BD12887A571FD` |
| `core/smc_sweep_linking.py` | `5B3C2DA85C910E432FA6C087486DD3AB2231D144AA6BD4732D2897D769658495` |
| `core/smc_models.py` | `AEE437971AE15BF4A0B6995A30A3ED3C9F903550FF20C394670E7D3D1C47794B` |
| `core/smc_lifecycle.py` | `A99A338B4F9040242A0D00840150AA50E8269F20834DD58BA610E79167DEA45C` |
| `core/smc_confluence.py` | `EA5C4A52D4C4806F2E37AC1DCE6B18A2A07BE49F5D981317633A1D58C38D7051` |
| `tests/test_smc_gate72_fix_acceptance.py` | `978AA7ECD044B9D41FF7AEBCDE650D2D5191DB5BAD8869D5C709A73A317E8E11` |

**Fingerprint bảo vệ — 6/6 KHỚP ledger F00** (probe `5B040D6A…B618B1C6`, canonical golden `45437A90…70C79999`, R56 session-contract `F04A0E64…433D50BB`, coder-handoff `AA682DA1…F28D301`, fixture `698CF8A2…54D2BDD5`, test R56 `F1975050…A253A5CA`). **5 file `core/` khác ledger F00 là thay đổi có chủ đích** của chuỗi F02→F11 (F02 `smc_lifecycle`/`smc_context`/`smc_models`; F03 `smc_context`/`smc_models`; F04 `smc_lifecycle`; F05 `smc_confluence`; F06–F07 `smc_context`; F08–F10 `smc_sweep_linking`/`smc_context`; C-R1/C-R2 + F11 `smc_sweep_linking`/`smc_context`). Không thêm/xoá file; không commit/reset/xoá; giữ nguyên dirty changes.

---

## 7. Giới hạn chưa kiểm (TL quyết định cuối)

1. **Legacy production route chưa được nâng cấp.** `_smc_for_timeframe` (Analyze/Scanner) vẫn chạy producer legacy `swing_points` (không `confirmed`/`usable`/`usable_at`) và khai `pool_provenance="legacy"` tường minh (§A3.146). Vì vậy route này **không** dùng được canonical pool lineage/usable-time; muốn chuyển phải đồng bộ producer legacy theo contract `usable_at` rồi chốt lại cờ — **ngoài scope F11**.
2. **Chưa có production rollout canonical.** Không đổi hành vi Analyze/Scanner ngoài việc khôi phục đúng hành vi legacy đã có (§A3.147).
3. **Pool record bị cắt theo `_MAX_LIQUIDITY_LEVELS`** để khớp 1:1 projection numeric; nếu cần record cho mọi pool eligible phải chốt cùng lúc với việc bỏ fallback numeric (§A3.142).
4. **G1/G2** không có fixture khóa cho ca nhiều child cùng setup khai `available_at` khác nhau và ca mixed setup/zone-only; đã ghi đúng semantics TL chốt nhưng chưa có ca biên tương ứng (§A3.153).
5. **`used_owners` trong `associate_sweeps_to_zones`** vẫn là biến ghi-mà-không-đọc (có trước F08) — deferred cleanup, không blocker.
6. **Quan hệ `SweepAssignment.contribution_applied` ↔ tổng contribution trên claims** không ràng buộc bởi bất biến nào (§A3.149) — F09 chỉ bảo đảm tổng trên claims theo A-D03.
7. **`source_swing_id = None` cho equal pool nhiều source** và evidence canonical mang thêm `source_ids`/`source_pool_usable_at` (khác schema legacy) — khác biệt có chủ ý (§A3.145).
8. **Chưa kiểm độc lập**: reviewer chưa chạy lại full F11 trong lượt này; các số ở mục 5 là do Coder chạy trên snapshot nêu trên.

---

## 8. Bản trình D — mẫu gửi TL

```text
Checkpoint D — WAITING_REVIEW
Đã làm F00…F11; A/B/C PASS (§A3.129/§A3.141/§A3.155). Chưa task73, chưa APPROVED gate72.
Bản trình cuối: docs/plans/smc-task-72-response.md (mục 2 mapping9 finding, mục 3 hai chuỗi e2e,
mục 5 commands/counts, mục 6 manifest/hash, mục 7 giới hạn).
Kết quả snapshot trình D: acceptance 129P/0F (baseline 65F/51P ở 116 node) · probes 16P/0F
(baseline 13F/3P) · task57–71 108P · retained 854P (không đổi) · full §5 983P/0F.
Δcollection +1 node (F11 chain), không mất/đổi tên node cũ.
Fingerprint bảo vệ 6/6 khớp ledger F00; git diff --check sạch.
Blocker: không. Giới hạn: legacy production route chưa nâng cấp (mục 7.1) và 7 điểm khác ở mục 7.
Không task73, không production rollout; chờ TL quyết định checkpoint D.
```

**Kết luận:** nghĩa vụ F11 đạt trên snapshot này — hai chuỗi end-to-end có bằng chứng chạy thật (mục 3), toàn bộ acceptance + 16 reviewer probes xanh, không regression. **Chưa** CLOSED 9 finding, **chưa** APPROVED gate72; **không** thực hiện task73.
