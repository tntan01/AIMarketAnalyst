# Phân tích khoảng hở producer B/Q/L/C — kế hoạch nối lại (chờ duyệt)

> **Trạng thái:** Ca 0 **HOÀN TẤT 04/10/2026** — Owner duyệt 5 quyết định (đã ghi vào `smc-bqlc-spec.md` + `smc-parameter-table.md`). Ca 1, Ca 2, Ca 3 **HOÀN TẤT 04/10/2026** (Owner duyệt checkpoint từng ca). Ca 4 chờ thực thi, một commit nguyên tử (D2) và checkpoint Owner trước khi đóng plan.
> **Mục đích:** (1) bản đồ cấu trúc 1 trang phục vụ onboarding Tech Lead; (2) xác minh độc lập 5 phát hiện từ replay 58 snapshot thật; (3) root cause từng phát hiện với bằng chứng file:line; (4) kế hoạch nối lại 3 producer chưa đấu nối + 1 ca vệ sinh reason-code, mỗi ca một điểm chạm duy nhất, chờ checkpoint Owner.
> **Phạm vi:** chuỗi canonical SMC (B/Q/L/C) từ `derive_live_analysis` trở xuống. Không thuộc phạm vi: threshold/gate, trọng số 4/7/2/2, calibration.

Nguồn số liệu: corpus nghiệm thu `reports/scanner/smc_real_snapshots/corpus.jsonl.gz` (58 snapshot × 2 side, 13 symbol, 5 mốc 02–09/2026), replay offline qua đúng pipeline live ngày 04/10/2026 — 0 lỗi, tái lập khớp trạng thái corpus 100% (44 evaluated / 48 watch_zone / 14 out_of_strategy / 10 data_unavailable). "92 side evaluated" = 44 + 48 (side có quality breakdown `evaluated`; watch_zone vẫn có quality của candidate được chọn).

**Công thức khóa đã xác nhận đúng đặc tả:** `S = 4B + 7Q + 2L + 2C` (`core/smc_models.py:116-120`, `:298-307`), mọi thành phần ∈ [0,1], `quality_raw = round_half_up(S)` đúng một lần (`:287-296`), S ∈ [0,15]. Scorer `smc-v2`, contract `smc-scoring-canonical-2026-08` (`core/smc_scoring_result.py:29`).

## 0. Cách tái lập số liệu

- Kiểm tra corpus: `python -X utf8 scripts/smc_real_snapshots.py verify` → 58 row, 0 vấn đề.
- Replay: đọc nến trong corpus theo recipe của `scripts/smc_replay_parity.py` (`_candle` + cửa sổ production 500 nến D1/H4/H1, 100 nến M15, không kèm future_tail), gọi `core.scanner_live_producers.derive_live_analysis` với `captured_at = row["as_of"]`, `tick_size = row["tick_size"]`, `min_rr = row["min_rr"]`.
- Bảng số liệu trong tài liệu này do script phân tích scratch (baseline + mô phỏng what-if, monkeypatch in-memory, không sửa repo) sản xuất ngày 04/10/2026; mọi kết luận đều kiểm chứng lại được bằng static reading kèm file:line.

## 1. Bản đồ cấu trúc 1 trang

```
MT5 (services/mt5_service.py — load_primary_timeframes, D1/H4/H1/M15)
 │
 ├─ controllers/scanner_controller.py — _fetch_one_symbol_mt5: đóng băng MỘT cutoff
 │   cho cả packet (smc-data-spec §1); gọi derive_live_analysis (:3419)
 │   và run_pair_from_live (:3433); revalidate trước lệnh thật (:2577)
 ▼
 core/scanner_live_producers.py: derive_live_analysis (:282)
 │   1) build_smc_snapshot (core/smc_snapshot.py:168) — lọc nến đóng tại cutoff,
 │      core verdict từ core/smc_history.py (assess_smc_history)
 │      → context canonical: core/smc_canonical_context.py: build_canonical_smc_context (:75)
 │         • structure: core/smc_structure_replay.py (BOS/CHoCH events + structure_state)
 │         • zones: detect/confirm OB·FVG·S-D (core/smc_context.py) + apply_zone_availability (:4042)
 │         • sweep linking: _attach_zone_sweep_links (smc_context.py:4894 → smc_sweep_linking.py)
 │         • lifecycle visits: enrich_zones (smc_context.py:5239 → smc_lifecycle.py: analyze_zone_lifecycle)
 │   2) evaluate_smc_snapshot (core/smc_snapshot.py:294)
 │      • evaluate_candidate_sets (core/smc_quality.py:123) — B/Q/L/C theo smc-bqlc-spec
 │      • select_canonical_sides (core/smc_selection.py:294) — thử từng candidate qua plan seam
 │        (core/scanner_scenario_producers.py: plan_for_candidate)
 │      • finalize_canonical_result (smc_selection.py:413) → SmcScoringResult
 │   3) derive_technical_raws_with_location (core/scanner_features.py) — Trend/Momentum/Location
 ▼
 core/scanner_release.py: run_pair_from_live (:115) → compose_scanner (core/scanner_composition.py:1162)
 │   • score_technical_signal (core/technical_signal_scorer.py:714) — 4 thành phần
 │     (Trend 25 / Momentum 20 / Location 25 / SMC 15, trọng số theo regime §3.2);
 │     SMC raw = quality_raw (0–15) qua project_smc_quality_raw (:935)
 │   • MarketSafetyGate (core/market_safety_gate.py) + MacroGate (core/macro_gate.py,
 │     nguồn NewsMacroProvider + core/macro_tiers.py đọc news.db)
 ▼
 decision → router (core/scanner_v4_strategy_router.py) → candidate (core/scanner_candidate.py)
 → ranking (core/scanner_ranking.py: trạng thái trước, setup_score sau)
 → row (core/scanner_row.py) → UI (ui/scanner_v4_presentation.py)
 → persistence (services/scanner_persistence_service.py) + journal + observability
```

Vai trò các thư mục khớp `docs/architecture/architecture.md`: `main.py` entry; `workers/` (scanner/news/backup worker QThread); `controllers/` (AppController = DI singleton + ScannerController); `services/` (MT5, news.db qua NewsRepository, journal, order management, AI…); `core/` (domain thuần + toàn bộ scoring/gate/decision); `ui/` (PyQt6); `config/` (đơn vị chính sách live: `scanner_order_policy.json`, `news_policy.json`); `scripts/` (nghiệm thu SMC); `reports/scanner/smc_real_snapshots/` (corpus bằng chứng); `tests/`. Chiều phụ thuộc `ui → controllers → core ← services` được import-linter canh (`.importlinter`).

## 2. Xác minh 5 phát hiện (số liệu tái lập 04/10/2026)

| # | Phát hiện | Kết luận | Số liệu tái lập |
|---|---|---|---|
| 1 | L = 0 mọi side, NO_RELATED_SWEEP | **Đồng ý** | L=0 đúng 92/92; NO_RELATED_SWEEP 92/92. Sâu hơn: **0 sweep được dò** trên cả 58 snapshot ở H4 lẫn H1 (`swept_lows=0, swept_highs=0`) dù pool records tồn tại (398 H4 / 393 H1) |
| 2 | D1 reaction = 0 (D1_REACTION_NOT_COMPLETED_REACTED) | **Đồng ý** | 92/92; UNAVAILABLE 0; STALE 0. Không D1 zone nào (kể cả ngoài zone đầu tiên) có visit `completed_reacted`: 0/92 |
| 3 | STRUCTURE_EVENT_TIME_UNAVAILABLE | **Đồng ý** | 92/92; `structure_event_age_bars` xuất hiện 0/92; grep toàn repo: chỉ có bên đọc `core/smc_quality.py:602`, không có producer |
| 4 | LIFECYCLE_EVIDENCE_UNAVAILABLE 43/92 (~47%) | **Đồng ý về số; phản bác diễn giải "integrity suy giảm"** | 43/43 thuộc nhánh zone fresh (0 visits) — integrity mean nhóm này **0.957** (state/penetration/dwell đều 1.0). Nhóm đã visit (49 side, integrity 0.485) không mang mã này |
| 5 | Dải nén | **Đồng ý** | S ∈ [3.6277, 10.0696], mean 7.3905; raw 4–10 (4×6, 5×12, 6×10, 7×19, 8×29, 9×14, 10×2); 1 side S≥10, 0 side ≤2 |

Phân rã mean S = 7.39: B = 0.677 → 2.71/4; Q = 0.598 → 4.19/7; **L = 0.000 → 0/2**; C = 0.248 → 0.50/2. Trong C: `independent_htf_reaction_score` mean **0.0000**; parent_child 0.220; direction 0.620. Trong B: state 0.781, trigger 0.772 (fallback tuổi zone), event 0.288 (dist: 0.0×42, 0.5×47, 1.0×3). Trong Q: formation 0.476 (body_atr 0.282 — yếu nhất), geometry 0.624, integrity 0.705.

## 3. Root cause từng phát hiện

### 3.1 Phát hiện 1 — L: (a) producer chưa nối, chết ở tầng dò sweep

- **Ai phải link sweep vào zone:** `_attach_zone_sweep_links` (`core/smc_context.py:4894`) qua `associate_sweeps_to_zones` (`core/smc_sweep_linking.py:163`), được façade gọi tại `core/smc_canonical_context.py:248-260`. Gate 0.25 ATR / 20 bar (`smc_sweep_linking.py:19`, `max_time_bars=20`) nằm trong linker và **chưa từng được đánh giá** — vì danh sách sweep đầu vào luôn rỗng.
- **Cơ chế:** façade gọi `detect_liquidity_sweeps` (`core/smc_canonical_context.py:238-247`) **không truyền `tick_size`/`atr_value`/`excursion_buffer`**. Trong detector có guard fail-closed (`core/smc_context.py:4544-4545`): swings canonical mang typed metadata (`confirmed`/`usable`/`provisional`) mà cả ba ngưỡng đều None → trả rỗng ngay. Guard đúng tinh thần B4 (không bịa ngưỡng excursion) — nhưng caller chưa bao giờ nối dữ liệu vào.
- **Bằng chứng cô lập** (EUR/USD 2026-02-19, H4): gọi đúng như canonical → 0 sweep; truyền `tick_size + atr_value` → 1 swept_high + 2 swept_lows; `excursion_buffer=0` → 2 + 6.
- **Chuỗi hệ quả:** sweeps rỗng → `zone_link_sweeps` rỗng → không zone nào được `liquidity_sweep_linked=True` → `_liquidity_features` (`core/smc_quality.py:779-791`) trả toàn 0 + NO_RELATED_SWEEP → L=0.
- **Ghi chú cấu trúc:** kể cả khi sweep sống, route link theo **visit** trong linker (`smc_sweep_linking.py:260-279`) đọc `zone["visits"]` — nhưng `_attach_zone_sweep_links` chạy **trước** `enrich_zones` (visits chỉ sinh sau đó, `smc_canonical_context.py:248` vs `:262-279`) → chỉ route cửa sổ formation hoạt động trong canonical path.

### 3.2 Phát hiện 2 — D1 reaction: (a) producer chưa nối — `atr_current` không ai sản xuất

- **Điều kiện `completed_reacted`:** visit đóng (ngoài→trong→ngoài) **và** có follow-through — close thoát zone ≥ `0.25×ATR` trong ≤3 bar sau exit, do `_follow_through_reaction_at` (`core/smc_lifecycle.py:748-802`) tính; `ZoneVisit.__post_init__` (`core/smc_models.py:1345-1351`) mới suy ra nhãn `completed_reacted` khi có `reacted_at`. Sau đó `build_d1_reaction_evidence` (`core/smc_confluence.py:112-268`) mới chấp nhận — kèm điều kiện không terminal và `age_bars ≤ 20` (D1_REACTION_LIFETIME_BARS, `smc_confluence.py:18`).
- **Vì sao 0/92:** `_follow_through_reaction_at` return None ngay khi `atr_current is None` (`smc_lifecycle.py:772-776`). `enrich_zones` đọc `zone["atr_current"]` (`core/smc_context.py:5366`) nhưng **không detector/producer nào set field này** (grep toàn repo: chỉ tests gán). D1 zone luôn tồn tại (0 side thiếu zone); first-zone states: completed_unreacted 50, open 26, no-visits 16 — "bằng chứng reaction" là nguyên nhân, không phải thiếu zone.
- **Tác động dây chuyền của cùng producer thiếu:** break_buffer cũng tính từ tick+ATR (`smc_lifecycle.py:625-638`) → None → invalidation không bao giờ chạy (zone chỉ chết vì expiry), `metadata_state=unknown` → `usable=False` trên 92/92 zone được chọn.

### 3.3 Phát hiện 3 — trigger B: (a) field không có producer

- **Ai phải điền `structure_event_age_bars`:** producer zone payload — hoặc hàm confirm OB khi đã gắn `confirmation_event_id` (`core/smc_context.py:3525-3535`), hoặc façade sau khi đã có cả zones lẫn `structure_events` (`core/smc_canonical_context.py:295`). Dữ liệu nguồn **đã tồn tại**: `SmcStructureEvent` mang `event_id/occurred_at/confirmed_at` (`core/smc_models.py:1110-1125`); chỉ thiếu phép join event→zone để quy tuổi ra bar.
- **Vì sao trống:** không dòng code nào viết field này; `_structure_features` (`core/smc_quality.py:601-610`) fallback sang `zone["age_bars"]` — tuổi zone neo tại `available_at` (`core/smc_lifecycle.py:683-697`).
- **Mức sai lệch của fallback:** với OB được confirm, `available_at = confirmed_at` của event (`core/smc_context.py:3531`) nên fallback xấp xỉ tuổi event. Nhưng chỉ **3/92** zone được chọn có `confirmation_event_id` (chỉ OB gắn event; FVG/S-D không) — với 89/92 zone còn lại, fallback đo **tuổi từ departure**, không phải tuổi trigger theo đặc tả §3.1 (lifetime D1 20/H4 40/H1 80/M15 48 — bảng P2, code đúng tại `core/smc_quality.py:58`).

### 3.4 Phát hiện 4 — lifecycle evidence: (a) nhưng là lỗi reason-code, không phải thiếu dữ liệu thật

- **Nguồn lifecycle:** `analyze_zone_lifecycle` (`core/smc_lifecycle.py:84`) sinh `visits` (list visit dict đủ nhãn chuẩn). Evidence **có** — vấn đề nằm ở bên đọc.
- **Cơ chế:** `_integrity_features` (`core/smc_quality.py:745-748`) — khi `visits` rỗng, `last_visit = {}` → `max_penetration_ratio` None → gắn `LIFECYCLE_EVIDENCE_UNAVAILABLE`; nhưng penetration_score tính `1 - (None or 0.0)` = **1.0**, dwell = 1.0, lifecycle_state = 1.00 (nhánh "fresh" tại `:728-729`). Tức reason nói "thiếu bằng chứng" trên đúng nhóm zone có integrity cao nhất (0.957), còn nhóm thực sự giảm điểm (visited, 0.485) không có mã — mâu thuẫn reason↔giá trị (vi phạm tinh thần S5/B4).
- **Tác động điểm thật của cùng mạch producer (§3.2):** visit đã đóng không bao giờ đạt `completed_reacted` (1.00) — 23 side `completed_unreacted` kẹt 0.80 (mất ≈0.147 S/side); 26 side `open` 0.60 là đúng đặc tả.

## 4. Mức độ nghiêm trọng và hệ quả

Định lượng phần thang đang chết (mean S = 7.39):

| Thành phần | Đóng góp hiện tại | Trần | Trạng thái |
|---|---:|---:|---|
| L (2/15) | 0.00 | 2.0 | Chết hoàn toàn — producer |
| C-reaction (0.5/15) | 0.00 | 0.5 | Chết hoàn toàn — producer (atr_current) |
| C-parent/direction (1.5/15) | 0.37 | 1.5 | Sống, yếu (0.22/0.62) |
| B-event (1/15) | 0.29 | 1.0 | Suy giảm — chỉ 3/92 zone có confirmation event |
| B-state+trigger (3/15) | 2.42 | 3.0 | Sống; trigger đo đúng nguồn 0% |
| Q (7/15) | 4.19 | 7.0 | Sống; formation là điểm yếu lớn (body_atr 0.28) |

**Mô phỏng what-if (monkeypatch in-memory, nối 2 producer, 58 row):** sweep H4 271 + H1 308 được dò; L>0 trên **19/89** side (L mean 0.18); D1 reaction đạt **3/89** (37 STALE do tuổi >20 D1 bar/terminal); mean S 7.39→**7.85**, max 10.07→**11.67**, raw mở tới 12; evaluated 92→89 (break buffer sống lại làm vài zone chết đúng hơn thành invalid). Kết luận: nối producer thu hồi ~0.5 điểm mean và ~1.6 điểm max — tách biệt tốt hơn, nhưng **không tự mở nửa trên thang**; phần nén còn lại đến từ chất lượng formation của detector (body_atr thấp), event evidence (3/92) và parent_child (0.22).

**Hệ quả vận hành:**

- **Khả năng phân biệt:** raw thực tế dồn 4–10; ranh "tốt/rất tốt" (raw 8–10, 45/92) và "rất hay" không tách được vì trần hiệu dụng 10.
- **Ngưỡng quyết định:** threshold policy hiện hành chấm trên dải nén; khi producer được nối, điểm tăng cơ cấu → phân bố WAITING/WATCH dịch. **Không chỉnh threshold để khớp kết quả cũ** — thay đổi semantics phải version hoá, owner đánh giá lại trên dải mới.
- **Hygiene chẩn đoán:** phát hiện 4 khiến reason-code chẩn đoán sai hướng (audit đọc "evidence unavailable" sẽ đổ lỗi nhầm); `usable=False` + `metadata_state=unknown` đồng loạt trên 92/92 zone cũng là tín hiệu producer thiếu, không phải thị trường.

## 5. Kế hoạch sửa — 4 ca, mỗi ca một điểm chạm duy nhất (Ca 0 đã xong, ca 1–4 chờ thực thi)

**Quyết định đã chốt ở Ca 0 (Owner duyệt 04/10/2026):**

1. `atr_current` = ATR hiện tại của timeframe tại cutoff, tính trên nến đã đóng; field riêng, không đè ATR formation (đúng data-spec §4).
2. `structure_event_age_bars` chỉ sinh cho zone có `confirmation_event_id` (OB); FVG/S-D giữ fallback tuổi zone — gắn event cho mọi family là plan riêng nếu sau này muốn.
3. Sweep linking giữ route cửa sổ formation; không đảo thứ tự attach/enrich.
4. Bump `SMC_SCORING_CONTRACT_VERSION` **một lần chung cả nhóm ca**: `smc-scoring-canonical-2026-08` → `smc-scoring-canonical-2026-10`.
5. Thực hiện đủ 4 ca code theo thứ tự 1→4; tiêu chí diff replay corpus: không side nào giảm điểm ngoài dự kiến (Ca 3 là giảm có chủ ý theo tuổi event — duyệt riêng từng side).

Nguyên tắc: mỗi ca một điểm chạm logic (S1/D1/D2); semantics đổi → version hoá qua `SMC_SCORING_CONTRACT_VERSION` (`core/smc_scoring_result.py:29`); chuỗi cũ đã persist giữ nguyên theo ngoại lệ V3(a); `smc_rule_versions()` (`core/smc_snapshot_cache.py`) sẵn sàng làm identity cache. **Không đổi** trọng số 4/7/2/2, gate 0.25 ATR/20 bar, bảng lifetime P2/P7.

| Ca | Nội dung | Điểm chạm duy nhất | Checkpoint Owner |
|---|---|---|---|
| 0 | Chốt semantics + cập nhật đặc tả (tài liệu trước code — D1) | `docs/plans/smc-bqlc-spec.md` + `smc-parameter-table.md` | **HOÀN TẤT 04/10/2026** — 5 quyết định ghi ở trên |
| 1 (P1) | Nối ngưỡng cho sweep detector: truyền `tick_size` + `atr_value=_latest_atr(closed)` tại call site canonical | `core/smc_canonical_context.py` | **HOÀN TẤT 04/10/2026** — diff replay: 20 side đổi, 15 tăng raw, 0 giảm, 0 đổi trạng thái; L>0 17/92 (finalized); sweep dò được 271 H4 + 308 H1; bump contract → `smc-scoring-canonical-2026-10` + phân loại historical cho payload 2026-08 |
| 2 (P2) | Stamp `atr_current` lên zone tại cùng chỗ stamp tick_size | `core/smc_canonical_context.py` | **HOÀN TẤT 04/10/2026** — diff replay khớp what-if từng con số: trạng thái 41/48/16/11, S mean 7.85, `atr_current` 89/89, metadata available 89/89, usable 53/89, zone có completed_reacted 0→33, D1 reaction 3/89; 23 side đổi (12 tăng/11 giảm — giảm truy về break buffer sống đúng dự kiến); full suite 5740 pass (5 fail có sẵn + 1 flake UI) |
| 3 (P3) | Sinh `structure_event_age_bars`: join `confirmation_event_id` ↔ `structure_events` (occurred/confirmed index → bar đến cutoff) trong producer zone | `core/smc_canonical_context.py` | **HOÀN TẤT 04/10/2026** (coder thực hiện, Tech Lead review diff + tự chạy lại test) — field có mặt 3/89, STRUCTURE_EVENT_TIME_UNAVAILABLE 89→86, **0 side đổi điểm**: cả 3 zone có event_age == zone_age (OB neo available_at tại confirmed_at của event — fallback từng đo đúng nguồn cho nhóm zone duy nhất có event). Giảm điểm có chủ ý không xảy ra trên corpus |
| 4 (P4) | Vệ sinh reason-code: nhánh fresh-zone không còn gắn `LIFECYCLE_EVIDENCE_UNAVAILABLE` (mã riêng hoặc bỏ — đăng ký từ vựng theo S5) | `core/smc_quality.py:746-748` | Xác nhận không đổi điểm, chỉ đổi diagnostics |

Mỗi ca kèm: test hợp đồng mới (C4), replay 58-row corpus chấm diff trước/sau, full pytest, bump `SMC_SCORING_CONTRACT_VERSION` **một lần chung cho cả nhóm ca** (quyết định 4 ở Ca 0). Downstream: snapshot cache (identity đổi → tự vô hiệu), journal/observability (version mới phân vùng), không chạm threshold/gate.

## 6. Câu hỏi mở và giả định chưa kiểm chứng

1. **Nguồn ATR của reaction/break-buffer (P7):** đặc tả không nói `atr_current` lấy ATR nào. What-if dùng ATR hiện tại của timeframe — con số 7.85/11.67 chỉ là ước lượng cận trên thô, không phải dự báo chính xác.
2. **FVG/S-D không bao giờ có `confirmation_event_id`:** chỉ OB confirm qua structure event (`core/smc_context.py:3529`) → event_score trần 0.5 cho 89/92 zone được chọn. Thiết kế hay gap? Ảnh hưởng lớn hơn cả 4 producer nếu owner muốn gắn event cho mọi family.
3. **`_SWEEP_LOOKBACK_BARS = 60`:** zone hình thành sớm hơn 60 bar không bao giờ có sweep để link. 60 bar có đủ cho ngữ nghĩa "sweep gây formation" không?
4. **Trigger lifetime H4 = 40 (P2) vs zone lifetime H4 = 30 (P7):** hai bảng khác nhau đúng đặc tả; khi `structure_event_age_bars` được nối, tuổi event dùng lifetime 40 — một số side trigger sẽ giảm, owner cần biết trước.
5. **Giả định replay:** corpus 58 snapshot (13 symbol, 02–09/2026) đại diện thị trường bình thường; what-if dùng production window 500 nến giống live fetch.
6. **Ngoài phạm vi 5 phát hiện, đáng vào sổ theo dõi:** `body_atr_score` mean 0.282 (đa số departure dưới mốc 0.30 → 0 điểm) là nguồn nén lớn nhất của Q; `state=0.55/event=0` trên 29 side (CHoCH candidate chưa confirm) — khảo sát detector formation riêng, không gộp vào các ca này.

## 7. Kết luận

Cả 5 phát hiện đều đúng về số liệu; 3 trong 4 root cause là **producer chưa nối** (sweep guard thiếu tick/ATR; `atr_current` không ai sản xuất; `structure_event_age_bars` không có producer); phát hiện 4 là **lỗi reason-code trên nhóm fresh zone** (không giảm điểm). Công thức B/Q/L/C ở `core/smc_quality.py` đúng đặc tả 100% — bệnh nằm ở tầng context producer. Chưa sửa code; 4 ca chờ Owner duyệt theo §5.
