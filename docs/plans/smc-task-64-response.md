# Task 64 — Implementation response

Trạng thái: **DONE / WAITING_REVIEW tại gate 72**. Đã dừng sau task 64; chưa triển khai task 65.

## Phạm vi

Task 64 bổ sung age decay và zone expiry theo timeframe. Tuổi canonical bắt đầu tại `available_at` khi có; expiry là terminal usability state nhưng không xóa identity, visit hoặc history.

## Mapping contract → code → tests

| Contract | Code | Tests |
|---|---|---|
| Age bắt đầu tại `available_at`, fallback formation/origin | `_age_anchor_index` chọn candle đầu tiên có close boundary tại/sau `available_at`; không có availability thì dùng `origin_index` | `test_age_anchor_starts_at_available_at_not_formation_index` |
| Lifetime D1/H4/H1/M15 là 20/30/50/80 bar | `stale_after_bars` hiện hữu được dùng làm canonical lifetime trong lifecycle | `test_age_decay_keeps_lifetime_boundary_alive_at_score_quarter`, `test_age_one_past_lifetime_expires_at_that_close` |
| Age decay `max(0.25, 1 - 0.75*age/lifetime)`, 0 sau expiry | `_age_decay_score` ghi `ZoneLifecycle.age_score`; biên lifetime còn `.25`, quá lifetime bằng `0` | `test_age_decay_keeps_lifetime_boundary_alive_at_score_quarter`, `test_age_one_past_lifetime_expires_at_that_close`, `test_age_anchor_starts_at_available_at_not_formation_index` |
| Expiry strict khi `age_bars > threshold`, timestamp là close candle vượt ngưỡng | Vòng lifecycle dừng tại candle expiry và lưu `expiry_index`/`expired_at`; `lifecycle_expired` và `lifecycle_stale` được set canonical | `test_age_one_past_lifetime_expires_at_that_close` |
| Invalidation và expiry cùng candle: invalidation ưu tiên | Kiểm tra buffered invalidation trước expiry; candle phá boundary đi vào terminal invalidation, không tạo expiry | `test_invalidation_wins_over_expiry_on_same_candle`, `test_invalidation_before_lifetime_does_not_become_later_expiry` |
| Expired zone không selected/usable nhưng giữ history | `enrich_zones` set `lifecycle_status=expired`, `usable=False`, thêm `ZONE_EXPIRED`; visits/identity vẫn nằm trong payload | `test_enrichment_marks_expired_zone_unusable_and_keeps_history` |

## Verification

- Task 64 + Task 57–63/lifecycle regression: **53 passed**.
- Full SMC/scanner integration command: **802 passed** (`8.46s`).
- `py_compile` cho lifecycle/context/model/test và `git diff --check`: **passed**.

## Gate

Đã hoàn thành phạm vi Task 64 và chuyển trạng thái **WAITING_REVIEW**. Dừng tại gate 72, không làm Task 65.
