# Task 57 — implementation response

Trạng thái: **DONE / chờ review gate 72**. Task 57 đã hoàn tất trong phạm vi model visit; chưa triển khai task 58–65, chưa tự APPROVED gate 72 và chưa rollout production.

## Mapping yêu cầu → code → tests

| Yêu cầu | Implementation | Bằng chứng |
|---|---|---|
| Model visit có zone nguồn và ID ổn định | `ZoneVisit` thêm `zone_id`, stable ID dạng `<zone_id>:visit-<ordinal>` qua `ZoneVisit.build_id`; lifecycle adapter dùng cùng builder. Legacy payload có thể suy ra zone từ visit ID. | `test_visit_id_is_stable_and_source_zone_is_explicit`; `test_legacy_visit_id_infers_source_zone_for_compatibility`. |
| Lưu entered/exited/reacted time | `ZoneVisit` thêm `reacted_at`; timestamp UTC được validate và quan hệ causal entered ≤ exited ≤ reacted được khóa. | `test_visit_states_require_their_causal_timestamps`; `test_visit_evidence_survives_zone_round_trip`. |
| Trạng thái open/completed/reacted | Thêm canonical `visit_state`: `open`, `completed_unreacted`, `completed_reacted`, `closed_by_invalidation`; state được suy ra khi payload legacy chưa có field. Có aliases đọc `state`/`status` cho consumer tương thích. | `test_visit_states_require_their_causal_timestamps`; invalid state/timestamp cases trong `test_visit_rejects_inconsistent_state_or_measurement`. |
| Evidence giữ qua typed zone | `SmcZone` đã có tuple visits; serialization/deserialization giữ đầy đủ zone source, state và reacted timestamp. | `test_visit_evidence_survives_zone_round_trip`; domain model/lifecycle regression. |
| Không mở rộng transition engine ngoài task 57 | `core/smc_lifecycle.py` chỉ chuyển adapter sang stable ID, truyền source zone và đánh dấu visit đóng do invalidation; không triển khai follow-through/reaction detection của task 60. | `tests/test_smc_zone_lifecycle.py` giữ nguyên semantics hiện có; task 58–65 vẫn chưa làm. |

## Files thay đổi

- `core/smc_models.py`: typed `ZoneVisit`, states, validation, stable ID builder và aliases.
- `core/smc_lifecycle.py`: dùng stable ID/source zone và state `closed_by_invalidation` cho visit bị đóng bởi invalidation.
- `tests/test_smc_zone_visit_task57.py`: regression contract mới cho model, states, validation và round-trip.
- `docs/plans/smc-implementation-progress.md`: ghi Task 57 DONE, chờ review gate 72.
- `docs/plans/smc-task-57-response.md`: báo cáo này.

## Verification

Targeted Task 57 + domain/lifecycle:

```text
python -m pytest tests/test_smc_zone_visit_task57.py tests/test_smc_domain_models.py tests/test_smc_zone_lifecycle.py -q
27 passed in 0.33s
```

Toàn bộ SMC và integration review suite:

```text
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
757 passed in 7.93s
```

`py_compile` cho model/lifecycle/task57 test đạt; `git diff --check` đạt, chỉ có warning LF/CRLF chuẩn của Git trên Windows.

Full repository smoke run có 3842 passed, 8 skipped, 16 xfailed và 7 failure không thuộc Task 57: 1 assertion UI navigation hiện có và 6 FRED fallback tests do fixture/runtime fallback ngoài phạm vi. SMC/integration suite liên quan Task 57 hoàn toàn xanh.

## SHA256

| File | SHA256 |
|---|---|
| `core/smc_models.py` | `66453868D9B0B39368B4C24CEC5F274CDB1A104D3703C75F1D5C22234E05C519` |
| `core/smc_lifecycle.py` | `D0B0C2FB3EB6AEBC16A66F4110E7C0AA674295A076BFA4A8EE51DB11FEBB941B` |
| `tests/test_smc_zone_visit_task57.py` | `4916BFD2CD092647932C89E8449AB407380C2B0E6A0348AF41CDD759A5E4E3A5` |
| `docs/plans/smc-implementation-progress.md` | `5C996B5ED85F9C1B27D347E4DB45C46EE1DFB8545DE666A1E492FC4F33376458` |

## Handoff

Task 57 đã hoàn thành và sẵn sàng cho Tech Lead review tại gate 72. Không làm task 58–65 trong lượt này.
