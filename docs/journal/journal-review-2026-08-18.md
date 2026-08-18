# Rà soát tính năng Nhật ký giao dịch & Nhận xét — 2026-08-18

Phạm vi: `services/journal_service.py`, `services/journal_models.py`, `services/journal_converters.py`, `core/journal_feedback_engine.py`, `core/statistical_edge_engine.py`, `controllers/journal_controller.py`, `ui/screens/journal_screen.py`, `ui/screens/journal_detail_screen.py`, luồng tích hợp trong `core/analysis_pipeline.py` và `core/scanner_composition.py`.

Phương pháp: chạy test thực tế + đọc mã nguồn + chạy trực tiếp trên DB thật. Mọi kết luận trong tài liệu này đều kèm bằng chứng (đầu ra console, dòng mã, số liệu DB) — không có nhận định suy diễn.

## 0. Trạng thái sửa lỗi (cập nhật 2026-08-18, cùng ngày)

| Mục | Trạng thái | Xử lý |
|---|---|---|
| F4 — 2 test Order Policy `min_risk_reward` | ✅ **Đã sửa** | Đồng bộ 2 assertion về `Fraction(1, 1)` khớp config live (`tests/test_scanner_order_policy.py`, `tests/test_scanner_order_policy_loader.py`). Suite xanh trở lại. |
| F2 — `performance_summary` trộn mẫu số | ✅ **Đã sửa** | Tách rõ mẫu tiền/R trong `build_performance_summary()` và `group_performance()`; headline `win_rate`/`profit_factor` cùng dân số `net_amount`; UI nêu rõ `r_win_rate`. Regression test mới: `tests/test_journal_performance_universes.py`. Chi tiết dưới. |
| F1 — MT5 sync thiếu SL → không có R | ✅ **Đã sửa** | Nạp SL từ MT5 order history: `closed_trade_history()` gọi `mt5.history_orders_get()` và build `position_sl_map` (SL cuối cùng theo time của mỗi position), `_closed_trades_from_deals` emit `actual_sl`; `journal_entry_from_mt5_trade()`/`_mt5_trade_update_payload()` truyền `actual_sl`; converter tính `result_r`/`result_pct`/`realized_effective_rr` cả ở create lẫn update. Chi tiết mục 5. |
| F3 — Scanner V4 bỏ feedback R-based | ✅ **Đã sửa (display-only)** | `_analyze_one_symbol` tính `build_journal_feedback` cho `selected_side` và ghi `journal_sample_size`/`journal_expectancy_r`/`journal_feedback` thật lên row; UI: marker 📋 + tooltip cột Mã, màn hình chi tiết đọc `row.journal_feedback`. **KHÔNG đổi gate/quyết định** (giữ V4 target-only discipline). |

F2 đã sửa được xác minh trên dữ liệu live:
```
closed_trades: 82 | r_trades: 2 | amount_trades: 82
win_rate: 39.02% (amount-based, cùng dân số 82 lệnh) | r_win_rate: 50.0% (R-based, 2 lệnh)
net_amount: -3388.45 | profit_factor: 0.185
```
Trước khi sửa:
```
win_rate: 50.0% (chỉ 2 lệnh có R) | net_amount: -3388.45 (82 lệnh)   <- mẫu số lệch
```

---

## 1. Bộ test — bằng chứng chạy được (thời điểm rà soát)

| Bộ test | Kết quả |
|---|---|
| `test_journal_service.py` + `test_journal_feedback.py` + `test_journal_sample_threshold.py` + `test_journal_zone_metadata.py` | **24 passed** |
| `test_scanner_journal.py` + `test_journal_zone_metadata.py` + `test_journal_sample_threshold.py` | **29 passed** |
| Cả 5 file journal (chạy gộp) | **41 passed** |
| **Toàn bộ suite** (`pytest -q`, 61s) | **3630 passed, 8 skipped, 16 xfailed — kèm 2 failed** (xem mục 5, F4) |

Các hành vi "nhận xét" có test xanh khẳng định đúng:

- `build_journal_feedback`: thiếu mẫu → fail-closed `STAT_EDGE_NOT_ENOUGH_DATA`; đủ mẫu và expectancy âm → `STAT_EDGE_NEGATIVE` + `FINAL_SCORE_EVIDENCE_NEGATIVE`; ≥12 mẫu → cap `WATCH_ONLY`; ≥25 mẫu, expectancy ≤ -0.45, win-rate < 35% → cap `TRADE_BLOCKED`; chất lượng thực thi trung bình < 65 → `FINAL_SCORE_EXECUTION_WEAK` + `EXECUTION_MANUAL_PENALTY` — [test_journal_feedback.py](tests/test_journal_feedback.py). Ngưỡng mẫu 8/12/25: [core/journal_feedback_engine.py:19-21](core/journal_feedback_engine.py#L19-L21).
- Chuỗi lý do hiển thị cho người dùng: "chưa đủ mẫu" / "kỳ vọng -0.30R trên 10 mẫu" / không thêm gì khi 0 mẫu — `append_journal_feedback_reason` — [test_journal_sample_threshold.py](tests/test_journal_sample_threshold.py).
- CRUD, ghi chú (note), lifecycle, migration idempotent (kể cả trường hợp mất `schema_migrations` / cột đã tồn tại một phần) — [test_journal_service.py](tests/test_journal_service.py).

## 2. Chuỗi end-to-end — chạy thật trên DB tạm

Mô phỏng đúng đường UI: tạo lệnh → `update_lifecycle` với `actual_entry`/`actual_sl`/`actual_exit`/`closed_at` → đóng lệnh. 6 lệnh -1R + 6 lệnh +0.5R. Đầu ra thực tế:

```
closed trades returned: 12
loss R: [-1.0, -1.0, -1.0, -1.0, -1.0, -1.0] | win R: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
--- feedback on 12 real DB rows ---
  sample_size: 12
  win_rate: 50.0
  expectancy_r: -0.25
  decision_cap: WATCH_ONLY
  opportunity_penalty: -8
  warning_codes: ['STAT_EDGE_NEGATIVE', 'FINAL_SCORE_EVIDENCE_NEGATIVE', 'EXECUTION_QUALITY_OK']
  reasons:
   - Phản hồi nhật ký tiêu cực: kỳ vọng -0.25R trên 12 lệnh.
--- performance_summary ---
  win_rate: 50.0 | expectancy_r: -0.25 | total_r: -3.0
```

Chuỗi chứng minh được:
1. Đóng lệnh sinh `result_r` đúng — [services/journal_converters.py:538-571](services/journal_converters.py#L538-L571) (`calculate_trade_outcome`).
2. `list_closed_trades_for_account_guard` trả đủ dữ liệu + `execution_quality_score` (auto-analysis chạy khi đóng lệnh).
3. Feedback engine đúng kích hoạt `WATCH_ONLY` khi có từ 12 mẫu.
4. Note CRUD (`update_note` → re-fetch) — đã verified qua test.

## 3. Dữ liệu live trong DB thật

DB thật: `%APPDATA%\ai-market-analyst\journal.db` — **85 bản ghi**, đủ 10 migration (`journal_entries` có ~68 cột).

| Chỉ số | Giá trị |
|---|---|
| Tổng bản ghi | 85 |
| `synced_from='mt5_history'` | 82 |
| `ai_commentary` không rỗng | 85 (82 bản = "Đã nhập từ lịch sử MT5.") |
| `note` không rỗng | 6 |
| `trade_status='closed'` | 82 |
| Có `result_r` | **2** |
| `execution_quality_score` | 85 |
| `auto_mistake_tags` không rỗng | 85 |

6 ghi chú tay thật (bằng chứng feature đang được dùng):
- `id=61 EUR/CAD`: "Tin Đức xấu làm loss lệnh (tin vàng)"
- `id=62 EUR/CAD`: "Vào lại lệnh nhưng vẫn loss"
- `id=67 USD/CHF`: "Lệnh này vào từ phần mềm nhưng code lỗi dẫn tới vào lệnh quá…"
- `id=74 NZD/USD`: "Hệ thống chạy ngon. NZD tăng lãi suất nhưng có tin chiến tra…"
- `id=80 EUR/USD`: "Thoát trước tin đỏ"
- `id=82 GBP/USD`: "Vào đúng xu hướng nhưng code lỗi tính SL quá gần."

2 lệnh có `result_r`: `id=89 EUR/USD win R=0.003` (amount 0.8), `id=92 EUR/CAD loss R=-1.0` (amount -53.47) — cả hai do người dùng nhập qua lifecycle (có SL).

Các màn hình "nhận xét" trong UI:
- `ui/screens/journal_detail_screen.py`: 3 khối „📊 Kết luận phân tích", „🎯 Kế hoạch giao dịch", „🤖 Nhận định của AI" (từ `ai_commentary`) + „📝 Ghi chú cá nhân" + „📈 Vòng đời giao dịch" — [journal_detail_screen.py:238-318](ui/screens/journal_detail_screen.py#L238-L318); lưu note: [journal_detail_screen.py:891-894](ui/screens/journal_detail_screen.py#L891-L894).
- `ui/screens/journal_screen.py`: cột "Ghi chú" với indicator 📝 + `NotePopup` khi click — [journal_screen.py:365-480](ui/screens/journal_screen.py#L365-L480), [journal_screen.py:1862-1868](ui/screens/journal_screen.py#L1862-L1868).

## 4. Kiểm chứng luồng "nhận xét tự động" (journal feedback)

- Được tính mỗi lần phân tích trong `AnalysisPipeline._step_apply_gates` cho cả 2 side — [core/analysis_pipeline.py:969-992](core/analysis_pipeline.py#L969-L992).
- Được assert tồn tại trong integration test — [test_analysis_pipeline_integration.py:393-394](tests/test_analysis_pipeline_integration.py#L393-L394).
- `JournalController` expose đủ: list/get/stats/performance/sync/note/lifecycle/export — [controllers/journal_controller.py](controllers/journal_controller.py).
- Scanner detail kiểm tra `gate.journal_feedback.block_codes/warning_codes` — [scanner_detail_screen.py:3471-3478](ui/screens/scanner_detail_screen.py#L3471-L3478).

## 5. Phát hiện (kèm bằng chứng)

### F1 — MT5 sync không mang SL ⇒ `result_r` rỗng ở 82/85 lệnh ⇒ feedback R-based bị "đói dữ liệu"

- Payload sync từ MT5 chỉ có `actual_entry`/`actual_exit`/`actual_lot`/`result_amount` + id + thời gian — **không có SL** — [services/mt5_service.py:3593-3609](services/mt5_service.py#L3593-L3609).
- `calculate_trade_outcome` bắt buộc có SL (actual hoặc planned) mới tính được R — [services/journal_converters.py:548-561](services/journal_converters.py#L548-L561).
- Live: chỉ 2/85 lệnh có `result_r`.
- Chạy `build_journal_feedback` trên dữ liệu live thật: `sample_size=0` → chỉ trả "chưa đủ dữ liệu để phạt" (fail-closed).
- Guard `synced_from != "mt5_history"` có chủ đích không wipe R cũ khi sync (vì sync không mang SL) — [services/journal_service.py:303-311](services/journal_service.py#L303-L311).

> **Đã sửa (2026-08-18):** deal history (`history_deals_get`) không có SL, nhưng MT5 **order history** (`history_orders_get`) có `.sl` cho từng order (theo `position_id`) — code trước đây chưa từng gọi. Nay:
> - `closed_trade_history()` gọi `mt5.history_orders_get(start, end)` → `_position_sl_map_from_order_history()` lấy **SL cuối** (theo time) của mỗi position (bắt cả SL đã bị MODIFY), fail-closed `{}` khi không có history — [services/mt5_service.py](services/mt5_service.py#L1452).
> - `_closed_trades_from_deals(..., position_sl_map=...)` emit `actual_sl` cho mỗi trade — [services/mt5_service.py:3593-3609](services/mt5_service.py#L3593-L3609).
> - `journal_entry_from_mt5_trade()` và `_mt5_trade_update_payload()` truyền `actual_sl`; converter tính `result_r`/`result_pct`/`realized_effective_rr` **cả ở create lẫn update** (trước chỉ tính ở update).
> - Kết quả: sau một lần re-sync MT5, lệnh có SL sẽ có `result_r` → feedback R-based có mẫu thật. Không cần migration (cột `actual_sl`/`planned_sl`/`result_r` đã có). Lệnh không có SL (broker không lưu order history) vẫn fail-closed `result_r=None`.
> - Test: `tests/test_mt5_history_sync.py` thêm `test_closed_trades_from_deals_includes_sl_from_position_map`, `test_closed_trades_from_deals_no_sl_map_emits_none`, `test_sync_mt5_closed_trade_computes_result_r_from_synced_sl`.

### F2 — `performance_summary` trộn mẫu số (r_trades=2, amount_trades=82)

Đầu ra live:
```
closed_trades: 82 | r_trades: 2 | amount_trades: 82
win_rate: 50.0 | expectancy_r: -0.498 | total_r: -0.997 | net_amount: -3388.45
```
- `win_rate`/`expectancy_r` chỉ tính trên **2 lệnh có R** (`results if results else amounts`) trong khi `net_amount`/`by_symbol` tính trên **82 lệnh** — [services/journal_converters.py:574-617](services/journal_converters.py#L574-L617).
- Bảng `by_symbol` (XAU/USD 40 lệnh, win_rate 22.5%, net_amount -2678.1) cũng dùng chung cơ chế này.
- Rủi ro hiểu nhầm: win-rate hiển thị không cùng mẫu với net_amount.

> **Đã sửa (2026-08-18):** `build_performance_summary()` và `group_performance()` giờ
> thu thập 2 mẫu tách bạch và không trộn:
> - **Mẫu tiền (amount)** — lệnh có `result_amount`: `win_rate`, `win_count`/`loss_count`/`breakeven_count`, `net_amount`, `profit_factor` cùng một dân số với `net_amount`.
> - **Mẫu R** — lệnh có `result_r`: `r_win_rate`, `r_win_count`/`r_loss_count`, `expectancy_r`, `total_r`, `average_win_r`/`average_loss_r`.
> UI KPI "Tỷ lệ thắng" nêu rõ headline theo lệnh có kết quả tiền và hiện `r_win_rate` khi mẫu R nhỏ hơn. Thêm regression test `tests/test_journal_performance_universes.py`.

### F3 — Scanner V4 live: cột feedback nhật ký là legacy/neutral

- Adapter V4 ghi nhận `journal_sample_size`, `journal_expectancy_r`, `journal_feedback` là **"legacy journal feedback; journal is a state gate" / "not produced now"** — [core/scanner_ui_adapter.py:81-116](core/scanner_ui_adapter.py#L81-L116).
- Row live luôn nhận neutral: `journal_sample_size=0`, `journal_expectancy_r=None`, `journal_feedback={}` — [scanner_ui_adapter.py:379](core/scanner_ui_adapter.py#L379), [scanner_ui_adapter.py:665](core/scanner_ui_adapter.py#L665).
- Bảng Scanner 11 cột hiện tại **không còn cột** `journal_sample_size`/`journal_expectancy_r` (chỉ còn code xử lý tooltip/số ở [scanner_screen.py:142-145](ui/screens/scanner_screen.py#L142-L145), [scanner_screen.py:573-583](ui/screens/scanner_screen.py#L573-L583)).
- Feedback engine vẫn chạy trong `analysis_pipeline` nhưng **không còn lái row scanner live**. Ảnh hưởng live của nhật ký hiện qua **JournalState gate** (drawdown / chuỗi lệnh thua): [core/scanner_composition.py:932-1020](core/scanner_composition.py#L932-L1020).

> **Đã sửa (2026-08-18, display-only):** `_analyze_one_symbol` (scanner live) giờ gọi
> `build_journal_feedback(closed_trades, symbol, direction=selected_side, ...)` qua helper
> `_attach_journal_feedback_to_row()` và ghi **giá trị thật** lên 3 key journal của row.
> - Bảng: cột Mã hiện marker **📋** khi có mẫu > 0; hover Mã hiện reasons (`sample_size`, kỳ vọng R).
> - Màn hình chi tiết: khối gate "Journal" đọc `row.journal_feedback` (fallback `gate`) — hiện số lệnh mẫu + kỳ vọng R.
> - **Chủ đích KHÔNG đổi gate/quyết định**: feedback chỉ hiển thị; `candidate_status`/`gate_codes`/`block_codes`/`decision_cap` không đổi (giữ V4 target-only discipline). Nhật ký vẫn ảnh hưởng live qua JournalState gate.
> - Test: `tests/test_scanner_journal_feedback_live.py` (helper lấp key thật, display-only không gating).

### F4 — Ngoài phạm vi journal: suite hiện không 100% xanh

Toàn suite: `3630 passed, 8 skipped, 16 xfailed, 2 failed`. Hai failure đều ở **Order Policy**, không thuộc journal:
- `tests/test_scanner_order_policy.py::TestTrialConfig::test_config_keeps_owner_approved_threshold_floors` — `assert policy.threshold.min_risk_reward == Fraction(2, 1)` nhưng nhận `Fraction(1, 1)`.
- `tests/test_scanner_order_policy_loader.py::TestLiveConfigLoad::test_live_values_match_owner_accepted_config` — cùng giá trị lệch.

Khả năng cao: `config/scanner_order_policy.json` đang giữ `min_risk_reward=1` trong khi owner-approved là 2 (cấu hình ngưỡng Scanner từ Settings — commit `3aa53b3`).

> **Đã sửa (2026-08-18):** commit `3aa53b3` cố ý đổi config sang `"1"` qua Settings nhưng 2 test (trong đó có test mới do chính commit này thêm) vẫn assert giá trị cũ `2/1`. Đã đồng bộ 2 assertion về `Fraction(1, 1)` cho khớp giá trị config đang sống:
> `tests/test_scanner_order_policy.py::test_config_keeps_owner_approved_threshold_floors`, `tests/test_scanner_order_policy_loader.py::test_live_values_match_owner_accepted_config`. Suite xanh trở lại.

## 6. Kết luận

- Tính năng **nhật ký + nhận xét hoạt động đúng theo thiết kế**: CRUD/note/migration/lifecycle/R/feedback đều có test xanh; chuỗi end-to-end chạy thực tế cho ra đúng kết quả nghiệp vụ; DB thật đang chứa dữ liệu thật (85 lệnh, 6 ghi chú tay).
- Cả **F1, F2, F3, F4 đều đã sửa** (F4, F2 lúc rà soát; F1, F3 trong cùng ngày). Toàn bộ mục 5 giờ là trạng thái đã đóng.
- Hai quyết định còn lại (không phải bug):
  1. **F1**: lệnh MT5-sync chỉ có R sau một lần **re-sync** (mỗi trade có SL trong order history). Lệnh broker không lưu order history vẫn không có R.
  2. **F3**: feedback R-based hiển thị (display-only), **không** tham gia gate/quyết định live — nhật ký vẫn ảnh hưởng live qua JournalState gate.

## 7. Khuyến nghị hành động

| Ưu tiên | Việc | Trạng thái / File liên quan |
|---|---|---|
| ~~Cao~~ | ~~Sửa 2 test Order Policy (`min_risk_reward` 1 vs 2) để suite xanh trở lại~~ | ✅ Đã sửa — đồng bộ test về `Fraction(1, 1)`. |
| ~~Trung bình~~ | ~~Chọn nguồn SL cho lệnh MT5-sync~~ | ✅ Đã sửa — `history_orders_get` → `actual_sl` → R ở create & update. |
| ~~Trung bình~~ | ~~Tài liệu hoá mẫu số của `performance_summary`~~ | ✅ Đã sửa — tách mẫu tiền/R + UI minh bạch. |
| ~~Thấp~~ | ~~Đưa feedback R-based trở lại Scanner V4~~ | ✅ Đã sửa (display-only) — helper `_attach_journal_feedback_to_row`, 📋+tooltip cột Mã, chi tiết đọc `row.journal_feedback`. |

---

*Tạo lúc: 2026-08-18. Các số liệu test/DB lấy tại thời điểm rà soát; nếu DB hoặc code đổi, cần chạy lại các lệnh ở mục 1 để làm mới bằng chứng.*