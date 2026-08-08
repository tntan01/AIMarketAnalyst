# Báo cáo review Bước 6 — AI Macro Verdict + Cache + Journal

**Ngày review**: 2026-08-07
**Phạm vi**: thay đổi chưa commit trong working tree so với `HEAD` (1c6dfca)
**Phương pháp**: khảo sát phạm vi, đọc trực tiếp module + wiring, chạy test suite đầy đủ (2536 test, 2 lần), xác minh độc lập các điểm trọng yếu, workflow review 20 agent (6 reviewer độc lập theo 6 chiều → gộp cụm → xác minh đối kháng từng cụm bằng đọc code thật). Kết quả: **10/10 cụm finding đều được verifier xác nhận** (confidence high), không cụm nào bị bác bỏ.

---

## 1. Phạm vi xem xét

Working tree tại thời điểm review chứa 3 phần:

| Phần | File | Ghi chú |
|---|---|---|
| Sửa review Bước 5 | `config/settings.py`, `services/settings_service.py`, `ui/screens/settings_screen.py`, `services/event_impact_assessor.py`, `services/news_service.py` (1 phần), `scripts/validate_event_assessment.py`, tests Bước 5, `docs/macro/macro_score_architecture.md` | Đã kiểm tra nhanh: sửa đúng và đủ (flag settings, checkbox UI, dedup journal bằng `fresh_ai_keys`, cap 0.85 cho confidence gate, tính lại `hours_until` chống derate kép, log lỗi thay vì nuốt...) |
| **Bước 6** (đối tượng review) | `services/macro_ai_verdict.py` (mới), `tests/test_step6_macro_verdict.py` (mới), `core/analysis_pipeline.py` (+217), `core/trade_gate_engine.py` (+33), `core/reason_codes.py` (+6), `services/news_service.py` (flag), `data/.gitignore` | Xem chi tiết bên dưới |
| Bước 7 (ngoài phạm vi) | `core/correlation_check.py` (+151), `core/vix_pair_backtest.py`, `tests/test_vix_pair_sensitivity.py`, `data/vix_pair_sensitivity.json` | Docstring tự ghi "Bước 7" (VIX pair sensitivity) — không review sâu, chỉ xác nhận không giẫm Bước 6 |

**Trạng thái test**: suite Bước 6 + Bước 7: 98 pass. Full suite: **2535 pass, 8 skipped, 17 xfailed, 1 FAIL** — regression do chính Bước 6 gây ra (mục 3.11).

---

## 2. Đánh giá tổng quan

Module thuần `services/macro_ai_verdict.py` viết tốt: parser nghiêm ngặt, **bất đối xứng được giữ tuyệt đối** (reviewer chuyên trách truy vết mọi đường dữ liệu và xác nhận không có cửa nào để AI "làm dễ" setup), flag settings lần này nối đúng (bài học "flag chết" của Bước 5 không lặp lại), cache disk + fingerprint + journal dedup hợp lý, gate engine chỉ siết không nới.

**Nhưng phần nối dây vỡ ở 3 chỗ chí mạng**: AI không bao giờ được gọi trong app thật (c1), prompt có gọi được thì cũng rỗng dữ liệu tầng (c2), và adjustment có chạy thì cũng không trừ vào điểm nào (c3). Net effect: **Bước 6 hiện là tính năng chết về mặt hành vi** — bật flag hay không cho kết quả giống hệt nhau, không có cách nào nhận ra từ UI. 60 test Bước 6 vẫn xanh vì toàn bộ chỉ gọi module trực tiếp với mock, không test nào chạy qua pipeline thật.

---

## 3. Findings theo mức độ

### 🔴 CRITICAL 1 — `ai_service` không bao giờ vào được pipeline: AI chưa từng được gọi

- **Yêu cầu vi phạm**: V1/V4 (kéo theo V7, V8 vì cache/journal chỉ ghi khi AI thành công)
- **File**: `core/analysis_pipeline.py:1110`, `core/analysis_engine.py:50-71`, `controllers/scanner_controller.py` (2486, 2617, 2651)

Pipeline lấy AI bằng `getattr(self, "_ai_service", None)`, nhưng grep toàn repo **không có bất kỳ phép gán `_ai_service` nào**. `AnalysisPipeline.execute()` và `analyze_symbol()` không có param `ai_service`; scanner tạo `ai_svc` nhưng chỉ truyền cho NewsService (preload/data_quality_flags), không forward vào pipeline ở cả 2 call site.

**Chuỗi hậu quả**: `assess()` luôn nhận `ai_service=None` → trả `MacroVerdict.fallback` → pipeline skip vì `source != "ai"` → không lời gọi AI, không cache ghi (V7), không dòng journal runtime (V8). User bật toggle "AI trọng tài vĩ mô (Bước 6)" trong Settings thì hành vi vẫn byte-identical với khi tắt, chỉ khác 1 dòng log. Đây là biến thể mới của bài học Bước 5: flag roundtrip SỐNG nhưng tính năng vẫn chết lặng lẽ vì thiếu wiring — và suite test vẫn xanh.

**Fix**:
1. Thêm param `ai_service: object | None = None` vào `AnalysisPipeline.execute()`, gán `self._ai_service` ở Step 0 (hoặc ép qua constructor thay vì getattr thăm dò).
2. Thêm param tương đương vào `analyze_symbol` (`core/analysis_engine.py`) và forward.
3. `scanner_controller.py`: truyền `ai_svc` (đã có sẵn) vào cả 2 call site `analyze_symbol` + thêm param cho `_analyze_one_symbol`.
4. Thêm integration test kiểu `test_step5_shadow_wiring.py`: chạy `AnalysisPipeline.execute()` thật với `macro_ai_verdict_enabled=True` trong data_quality, macro score ≥ 20, MagicMock AI trả JSON hợp lệ → assert verdict có hiệu lực (reason code, cache.put/journal được gọi). Khóa wiring để tính năng không thể chết lặng lần nữa.

---

### 🔴 CRITICAL 2 — Context gửi AI rỗng ruột: giá trị độc nhất V6 bất khả thi

- **Yêu cầu vi phạm**: V6 (kéo theo V4)
- **File**: `core/analysis_pipeline.py:1181-1209` (`_build_macro_verdict_context`)

Hàm này đọc `tier1/tier2/tier3/macro_v2/stance` từ `self._macro_alignment_in` — nhưng pipeline chỉ nhận được `macro_alignment_scores` = `{"buy": X, "sell": Y}` (`scanner_controller.py:2480/2646`: `macro_alignment = macro_context.get("macro_alignment_scores")`). Mọi `.get("tier1", {})` đều trả `{}` → prompt AI nhận **rỗng toàn bộ dữ liệu tầng**, chỉ còn 2 con số alignment + vài boolean correlation (`has_dxy`, `buy_corr_adj`...) + event assessments.

Ví dụ đầu bài của V6 — "tier 1 nói USD hawkish vì lợi suất tăng nhưng DXY thực tế đang giảm" — không thể phát hiện vì AI không thấy dữ liệu tier 1 lẫn chuyển động DXY. Trớ trêu: dữ liệu đầy đủ **có sẵn** trong `macro_context["macro_tier_detail"]` (gồm `tier1_interest_rate`, `tier2_calendar`, `tier3_sentiment`, mỗi cái có `{"buy","sell","detail"}` đúng shape prompt chờ) ở controller, chỉ không được forward.

**Fix**: truyền gói đầy đủ vào pipeline — thêm kwarg riêng (vd `macro_verdict_context`) cho `AnalysisPipeline.execute`/`analyze_symbol`, scanner lấy từ `macro_context` đang có sẵn trong scope: map `tier1_interest_rate→"tier1"`, `tier2_calendar→"tier2"`, `tier3_sentiment→"tier3"`, kèm `macro_v2`, `stance_journal`. Bổ sung dữ liệu chuyển động DXY (hướng/% thay đổi) để V6 có nguyên liệu đúng nghĩa.

---

### 🔴 CRITICAL 3 — Adjustment áp dụng SAU bước chấm điểm: "trừ điểm" là no-op

- **Yêu cầu vi phạm**: V5
- **File**: `core/analysis_pipeline.py` — thứ tự `execute()`: Step 3 `_step_score_scenarios` (chấm điểm, dòng 870 `compose_scenario_score`) → Step 5 `_step_determine_direction` → **Step 5.5 `_step_ai_macro_verdict`** → Step 6 gates → Step 7 `_step_compute_final_score`

Đã xác minh độc lập: scoring ăn `macro_confidence` tại Step 3 (`effective_macro_weight = int(macro_cap × conf)` trong `compose_scenario_score`); adjustment của verdict nhân vào `_macro_confidence_in` ở Step 5.5 — **sau khi điểm đã chốt**; Step 7 `calculate_final_score(signal_score, evidence_score, execution_quality_score)` không nhận lại confidence. Vậy adjustment ×0.95 **không làm giảm signal_score/final_score nào** — chỉ thay đổi field hiển thị `result["macro"]["macro_confidence"]`.

Hệ quả: V5 "adjustment âm → trừ điểm" chết; trọng tài AI chỉ còn mỗi quyền veto (all-or-nothing), mất hẳn nấc thang giảm dần mà spec thiết kế. Lưu ý: thất bại theo chiều an toàn (không làm dễ setup), nhưng cơ chế spec yêu cầu không tồn tại.

**Fix** (cần chốt kiến trúc, chọn 1 — cả hai giữ bất đối xứng):
- **(a)** Chạy `_step_ai_macro_verdict` TRƯỚC `_step_score_scenarios`, chọn side xét verdict bằng `max(macro_buy, macro_sell) ≥ MIN_MACRO_SCORE_FOR_VERDICT` thay vì `best_side` (chưa tồn tại ở thời điểm đó) → confidence đã giảm được `compose_scenario_score` tiêu thụ thật. Đánh đổi: verdict không còn theo đúng hướng best_side.
- **(b)** Giữ vị trí hiện tại nhưng áp adjustment như **khoản trừ điểm trực tiếp** vào signal/final score tại Step 7 (trước `_step_enrich`) — sát nghĩa đen "trừ điểm" của spec hơn.

Lưu ý thêm: kể cả hướng (a), adjustment −5 chỉ đổi `int(cap×conf)` tối đa ~1-2 điểm final; nếu muốn adjustment có răng hơn, cân nhắc thang −5..0 trừ thẳng vào điểm macro component (0-30).

---

### 🟠 MAJOR 4 — Reason codes Bước 6 bị khối lắp ráp ghi đè, không bao giờ xuất hiện

- **File**: `core/analysis_pipeline.py` — `_step_ai_macro_verdict` append `MACRO_AI_ADJUSTMENT`/`MACRO_AI_VERDICT_SKIPPED` thẳng vào `self._reason_codes`; `_step_enrich` (~dòng 1658) **gán lại** `self._reason_codes = normalize_codes(combined_reason_codes)` dựng từ scenario/gate/account-guard + 3 biến reason riêng của macro (Bước 3/5) → 2 code Bước 6 bị xóa khỏi kết quả cuối. `MACRO_AI_VETO` sống sót vì đi qua gate `warning_codes` (con đường khác).
- **Fix**: theo pattern Bước 3/5 — lưu biến riêng (vd `self._macro_ai_reason_codes`), append vào `combined_reason_codes` trong `_step_enrich` trước `normalize_codes`; reset trong `_ensure_safe_defaults`.

### 🟠 MAJOR 5 — Backtest không bao giờ chạm verdict: V7 (reproducible) chết

- **File**: `core/system_backtest_engine.py` → `analyze_symbol` (cùng pipeline)
- Data_quality backtest không chứa `macro_ai_verdict_enabled` (Guard 1 skip ngay); kể cả bật flag, `ai_service=None` → `fingerprint(None)` (`{"enabled": false,...}`) khác fingerprint live → cache quá khứ **luôn miss** → fallback không áp. "Backtest đọc lại cache, không gọi AI lại, reproducible" không có đường chạy.
- **Fix**: chốt policy rõ và khóa bằng test — thêm flag vào data_quality backtest (`_run_analysis_snapshot`), cho `MacroVerdictAssessor` chế độ **read-cache-only** khi `is_backtest=True` (thread `is_backtest` qua pipeline step): chỉ đọc cache theo `(pair, trade_date)`, miss → skip trung tính, tuyệt đối không gọi AI; đồng thời xử lý fingerprint cho mode không-AI khi đọc cache.

### 🟠 MAJOR 6 — Cache/journal không phân biệt best_side

- **File**: `services/macro_ai_verdict.py:153` (`verdict_cache_key`), `:399-401` (`_file_path`), `_journal_verdict`
- Prompt và verdict phụ thuộc hướng đang xét ("HƯỚNG ĐANG XÉT: BUY"), nhưng cache key chỉ `(pair, date)` → setup BUY sáng nay được cache, setup SELL chiều nay **lãnh nguyên verdict của BUY** (veto "mâu thuẫn chống buy" có thể giết oan setup sell ngon — vẫn trong chiều an toàn của V2, nhưng sai ngữ nghĩa và người dùng không thể biết). Journal cũng không ghi `best_side` → V8 sau này không biết đối chiếu theo hướng nào.
- **Fix**: thêm `best_side` vào `MacroVerdict` + `to_dict`; đưa side vào `_file_path` (vd `{pair}_{date}_{side}.json`) và `get()/put()` (side khác → miss); ghi `best_side` vào journal record.

### 🟠 MAJOR 7 — Timeout V9 chỉ tồn tại trên danh nghĩa, đường nóng blocking 30-120s

- **File**: `services/macro_ai_verdict.py:42` (`AI_TIMEOUT_S = 15.0`), `:506-510` (lưu `self._timeout_s`), `:581` (gọi `analyze` không timeout)
- `self._timeout_s` không được dùng ở bất kỳ đâu. Adapter AI của dự án tự timeout 30-120s; verdict chạy trong pipeline của **mỗi top candidate** trên đường nóng → AI treo làm scan block 30-120s/cặp, vi phạm "không để AI làm nghẽn đường nóng".
- **Fix**: thực thi budget trong `assess()` — chạy `ai_service.analyze` trong `ThreadPoolExecutor` riêng, chờ `future.result(timeout=self._timeout_s)` → `TimeoutError` → fallback (chấp nhận thread zombie, ghi log); hoặc sạch hơn: thêm param `timeout` xuyên `AIService.analyze` → adapter.

### 🟠 MAJOR 8 — Vòng phản hồi V8 hở cả hai đầu

- **File**: `services/macro_ai_verdict.py:467-487` (`_journal_verdict`)
- `trade_result_r`/`trade_outcome` là `None` vĩnh viễn: grep toàn repo không code nào điền lại, không code nào đọc `macro_verdict_journal.jsonl`, không có công cụ label/report tương đương `scripts/validate_event_assessment.py` của Bước 5, và verdict không được ghi vào trade journal (sqlite) khi vào lệnh → không có khóa join về sau. "Sau ~100 lệnh biết AI chính xác bao nhiêu %, veto có đúng không" hiện không thể đạt.
- **Fix**: (1) ghi `best_side` vào record (xem Major 6); (2) khép đầu outcome — backfill `trade_result_r`/`trade_outcome` khi lệnh đóng (hook vào `journal_service.update_trade_outcome`, join theo `(pair, date, best_side)`), hoặc tối thiểu viết script label/report đọc journal + trade DB; (3) ghi cả trường hợp verdict bị skip do AI lỗi để đo "đốt token vs giá trị".

---

### 🟡 MINOR 9 — Không negative cache / circuit-breaker

AI hỏng → fallback **không được cache** (khác fallback của Step 5 có negative cache 30 phút) → mỗi scan sau lại gọi AI lại cho mọi top candidate, cả ngày, vừa tốn vừa kéo dài đường nóng nếu adapter chậm.
**Fix**: entry failure trong cache với TTL ngắn (15-30 phút), hoặc circuit-breaker: N failure liên tiếp cùng fingerprint → skip AI đến cuối ngày, trả fallback ngay không blocking.

### 🟡 MINOR 10 — Lệch đường dẫn cache/journal vs `.gitignore` và convention Bước 5

Cache/journal ghi vào `%APPDATA%/AIMarketAnalyst/...` (`config.paths.app_data_dir()`) nhưng `data/.gitignore` khai báo `macro_verdict_journal.jsonl` + `macro_verdict_cache/` trong repo `data/` → dòng ignore vô tác dụng; lệch convention với Bước 5 (ghi trong repo `data/`, nơi các script kiểm chứng tìm đọc).
**Fix**: thống nhất về `<repo>/data/` (`Path(__file__).resolve().parents[1]/"data"/...`) để `.gitignore` có nghĩa và tooling tương lai biết chỗ tìm.

### 🟡 MINOR 11 — Regression test suite: `pipeline_diagnostics` vi phạm contract (workflow không phát hiện, xác minh trực tiếp)

`tests/test_pipeline_diagnostics.py::test_pipeline_generates_diagnostics` **FAIL** trên working tree, pass 8/8 trên HEAD. Nguyên nhân: `_log_step("macro_verdict", "skip"/"fallback"/"veto"/"ok"/"adjustment", ...)` đưa các status ngoài hợp đồng `("pass","fail","warning")` vào `result["pipeline_diagnostics"]`. UI (`scanner_detail_screen.py:3175/3573`) đọc `pipeline_diagnostics` nhưng chỉ dùng step `gate` nên không crash; tuy nhiên contract test đỏ thì không commit được.
**Fix**: map status verdict về `pass`/`warning` (vd skip→pass, veto/adjustment→warning), hoặc mở rộng contract kèm cập nhật test + consumer.

### 🟡 MINOR 12 — Tài liệu

Không có dòng nào về Bước 6 trong `docs/macro/macro_score_architecture.md` (Bước 5 có mục riêng, sơ đồ luồng, decision table); file handoff `docs/macro/step5_deepseek_handoff.md` bị xóa khỏi working tree mà không có bản thay thế cho Bước 6. Nên bổ sung mục Bước 6 (luồng dữ liệu, schema JSON, decision rules, cache/journal, flag) trước khi commit.

---

## 4. Những gì ĐÚNG (xác nhận qua truy vết đối kháng)

- **V2 bất đối xứng — pass**: parser `_validate_verdict` ép `adjustment ∈ [-5,0]` (ngoài khoảng → reject, an toàn), conviction ngoài `[0,1]` → reject, `veto=true` không conflicts → vô hiệu veto, `bias="conflict"` không conflicts → hạ thành `unclear`; fallback/skip luôn trung tính (`veto=False, adjustment=0, conviction=0.0`); gate engine `_gate_macro_ai_verdict` chỉ siết (`_resolve_cap` lấy cap chặt hơn), conviction < 0.7 bỏ qua, đã block thì veto không tác dụng thêm. Không tìm thấy đường nào AI làm dễ setup — worst-case đúng spec: mất 1 lệnh ngon.
- **V1 top-candidate gating — cơ chế đúng**: 2 lớp guard (pipeline `best_side ≥ 20`, assessor `max(buy,sell) ≥ 20`) + skip khi flag tắt.
- **V3 — pass**: điểm deterministic (`_scores`) không bị verdict sửa trực tiếp.
- **Flag roundtrip hoạt động**: `config/settings.py:153` → `settings_service.py:513` → UI checkbox (`settings_screen.py:1660/1753`, kèm carry-over brave/fred keys) → `news_service.py:461` → `data_quality_flags`. Có test hồi quy (`tests/test_step5_review_fixes.py:311-380, 950-998`).
- **Gate VETO**: `test_veto_true_caps_to_watch` + 3 test vệ tinh pass, READY→WATCH đúng.
- **Module-level quality**: 60 test Bước 6 (parser/constraints/cache/assessor/gate) viết chắc, không flaky (T0 cố định), cache test dùng `TemporaryDirectory`.
- **Journal dedup**: chỉ ghi verdict AI mới (cache hit không ghi lại) — không lặp lỗi journal của Bước 5.

## 5. Các hướng bác bỏ đã kiểm tra và loại (minh bạch)

Merge agent đã loại 10 finding thô sau khi đọc code thật, gồm: "flag roundtrip không có test hồi quy" (sai sự thật — test tồn tại); `parse_verdict_json` ném ValueError với literal NaN (đã kiểm chứng an toàn); `int()` truncation làm nhẹ hình phạt (luôn nằm trong [-5,0]); "AI trả adjustment ngoài khoảng làm hủy cả veto hợp lệ" (reject-toàn-bộ là thiết kế fail-closed); race ghi cache khi scan chồng (xác suất thấp, hậu quả = gọi AI lại); cache không cleanup (nit, gộp vào Minor 10); `MacroVerdictAssessor` mkdir mỗi lần (perf nit); guard ngưỡng bất nhất assessor/pipeline (nit, 2 lớp cùng chiều).

## 6. Ma trận yêu cầu V1-V9

| YC | Trạng thái | Lý do chính |
|---|---|---|
| V1 chỉ gọi top candidates | ⚠️ partial | gating đúng nhưng AI không đến được pipeline (Critical 1) |
| V2 bất đối xứng | ✅ pass | cơ chế đúng mọi đường (chưa phát huy vì Critical 1) |
| V3 không đổi điểm deterministic | ✅ pass | |
| V4 module + gói toàn bộ tín hiệu | ❌ fail | gói tín hiệu rỗng ruột (Critical 2) |
| V5 veto/adjustment/conviction | ❌ fail | veto OK; adjustment no-op (Critical 3); reason code mất (Major 4) |
| V6 phát hiện mâu thuẫn giữa tầng | ❌ fail | không có dữ liệu tầng trong prompt (Critical 2) |
| V7 cache (pair, ngày) + backtest repro | ❌ fail | thiếu best_side (Major 6); backtest không chạm (Major 5) |
| V8 journal vs kết quả lệnh | ❌ fail | hở cả hai đầu (Major 8) |
| V9 timeout + fallback + log | ⚠️ partial | fallback tốt; timeout chết (Major 7); không negative cache (Minor 9) |

## 7. Thứ tự sửa đề xuất

1. **Critical 1** — nối `ai_service` xuyên `execute()`/`analyze_symbol`/scanner (mở khóa mọi thứ) + wiring test.
2. **Critical 2** — truyền `macro_tier_detail` + v2 + stance + dữ liệu DXY vào prompt context.
3. **Critical 3** — chốt kiến trúc vị trí áp adjustment (hướng a/b, cần quyết định của chủ hệ thống).
4. **Major 4 + Minor 11** — reason codes theo pattern biến riêng; map status diagnostics về contract (nhanh, để test suite xanh trước khi commit).
5. **Major 6** — thêm `best_side` vào dataclass/cache key/journal.
6. **Major 7** — thực thi timeout 15s (ThreadPool budget hoặc param xuyên adapter).
7. **Major 5** — backtest read-cache-only policy + flag trong data_quality backtest.
8. **Major 8** — khép vòng V8 (backfill outcome hoặc script label/report).
9. **Minor 9, 10, 12** — negative cache, thống nhất đường dẫn `data/`, tài liệu kiến trúc Bước 6.

---

*Review tạo bởi quy trình đa agent: 6 reviewer độc lập (bất đối xứng, nối dây runtime, cache/reproducible, journal/feedback, timeout/fallback, chất lượng test) → merge kiểm chứng bằng đọc code thật → xác minh đối kháng từng cụm. 20 agent, 0 lỗi, toàn bộ 10 cụm sống sót sau bước bác bỏ.*

---
---

# BÁO CÁO RE-REVIEW BẢN FIX BƯỚC 6 — 2026-08-08

**Đối tượng**: xác minh commit `7fc4725` ("Bước 6 review fixes — AI Macro Verdict (12 findings)") đã fix TRIỆT ĐỂ 12 finding ở phần trên chưa, và bản fix có tự gây lỗi mới không.
**Phương pháp**: chạy độc lập full test suite (✅ **2579 passed, 8 skipped, 17 xfailed** — khớp commit message, không FAIL); đọc trực tiếp diff `7fc4725` + code thật tại các điểm trọng yếu; workflow **98 agent** (15 verifier độc lập theo 12 finding + 3 chiều review chéo bất-đối-xứng/regression/test-quality → bác bỏ đối kháng 2 lens cho từng issue → completeness critic). Mọi issue nặng dưới đây đều đã được **tự reproduce bằng code thật** trước khi ghi nhận.

## Kết luận

**Cả 12 finding đều đã được xử lý ở phần lõi** — wiring sống thật, test suite xanh, bất đối xứng V2 được giữ (truy vết 6 cửa không tìm được đường nào AI/cache làm setup *dễ* hơn). Nhưng **chưa triệt để**: 3 finding ở trạng thái *partial* (C3, M8, m10), và **bản fix tự gây regression mới** — nặng nhất là nạn "bỏ đói" AI call khiến tính năng có thể lại **chết lặng lẽ trên hầu hết các cặp**, đúng loại lỗi Critical 1 từng mắc.

## Trạng thái 12 finding sau bản fix

| Finding | Trạng thái | Ghi chú |
|---|---|---|
| C1 wiring `ai_service` | ✅ triệt để* | Nối đúng cả 2 call site; *nhưng gây starvation (A1) và thiếu test lớp scanner (A7) |
| C2 context đầy đủ | ✅ triệt để* | Tier data + DXY sống thật; *1 field prompt luôn "?" (A4) |
| C3 adjustment trừ điểm | ⚠️ **partial** | Trừ thật (reproduce −3 → signal/final giảm 3) nhưng **phantom deduction khi cap CHOCH binds** + **best_score/trade_permission stale** (A2, A3) |
| M4 reason codes | ✅ triệt để | Đúng pattern Bước 3/5, cả 3 code sống sót (nit: VETO ở cả reason_codes lẫn warning_codes — chấp nhận được, 2 kênh khác mục đích) |
| M5 backtest read-cache-only | ⚠️ **partial** | Cơ chế đúng (thread `is_backtest` xuyên pipeline, miss→skip trung tính) nhưng **thiếu integration test khóa chuỗi** + giới hạn thực tế (chỉ hữu ích cho ngày live đã quét, cùng side) |
| M6 cache/journal best_side | ✅ triệt để* | *outermost exception path không truyền `best_side` (nhóm 🟡) |
| M7 timeout 15s | ✅ triệt để* | ThreadPool + `result(timeout=15)` đúng; *pool 2 worker là nguồn cơn A1 |
| M8 vòng V8 | ⚠️ **partial** | Script `label/report` chạy được, join (pair,date,side) đúng — đạt mức "tối thiểu"; nhưng **0 test** + R-multiple chết trên dữ liệu thật (mt5_sync không có result_r) |
| m9 negative cache | ✅ triệt để* | TTL 30', phân biệt fingerprint; *negative entry ghi đè verdict tích cực khi đổi fingerprint (A6) |
| m10 path `data/` | ⚠️ **partial** | Path đúng; nhưng **3 test cũ giờ ghi rác thẳng vào `data/` thật** (đã xác nhận tại chỗ: journal 187 dòng test + file negative cache) (A5) |
| m11 diagnostics contract | ✅ triệt để* | Suite xanh; *UI vẽ "skip" thành 🟢 QUA, backtest aggregator ghi key "skip" thô (nhóm 🟡) |
| m12 tài liệu | ✅ triệt để | Section 17 mô tả đúng code sau fix (nit: thiếu dòng changelog đầu file, mô tả `verdict_cache_key` vốn là code chết) |

## A. Các vấn đề CẦN SỬA (theo mức độ)

### 🔴 A1 — Starvation AI call: pool 2 worker vs 6 luồng scan (regression MỚI, major)
`services/macro_ai_verdict.py:51` — `_AI_EXECUTOR` singleton **max_workers=2**; scanner chạy **tối đa 6** pipeline song song (`controllers/scanner_controller.py:595`). `future.result(timeout=15)` tính từ lúc *submit* nên thời gian xếp hàng bị tính vào budget. Đã **reproduce với 6 luồng thật, AI 12s/call: chỉ 2 "ok", 4 TimeoutError** → fallback + **negative cache 30 phút**. Hệ quả: scan có ≥3 top candidate → đa số cặp âm thầm không có verdict AI trong 30 phút tiếp theo. Fail-closed nên không sai quyết định, nhưng đây chính là biến thể "flag bật mà tính năng chết lặng" của Critical 1.
**Fix**: nâng `max_workers` ≥ số thread scan (6), hoặc tách budget thành queue-timeout + exec-timeout; và **không ghi negative cache khi lỗi chỉ là timeout xếp hàng** (AI chưa từng được gọi).

### 🔴 A2 — Phantom deduction khi cap CHOCH binds (major — Critical 3 chưa triệt để ở nhánh này)
Đã reproduce trực tiếp: `{technical_scaled:30, risk_condition:15, macro_alignment:20, smc_score_cap:60}`, adjustment=−5 → `deducted=5` nhưng **signal_score giữ nguyên 60**. `core/analysis_pipeline.py:1763-1773` trừ vào component rồi áp lại cap — khi cap đã bind, deduction vô hình trong khi `macro_ai_deducted` và log vẫn báo "trừ 5 điểm".
**Fix**: trừ SAU cap (`new_total = min(total, cap) − deduction`, floor 0) — adjustment có răng cả trên setup capped; và/hoặc tính `deducted` = chênh lệch total thực tế để log/payload không nói sai.

### 🔴 A3 — `best_score` / `trade_permission` dùng điểm TRƯỚC deduction (major — lỗi MỚI do fix)
`_best_score` chốt ở Step 5 (`core/analysis_pipeline.py:1032`), `calc_trade_permission` chạy ở Step 6 với `_best_score` cũ (`:1287-1290`) — đều **trước** deduction ở Step 7 (`:1797`). Payload cuối chứa cả hai: `decision_summary.best_score` (`:2091`) = điểm cũ, `final_score`/`scenario_scores` = điểm mới. Permission READY xét điểm chưa trừ → adjustment không chạm được ngưỡng READY.
**Fix**: tính lại `_best_score` + `trade_permission` sau deduction, hoặc dời deduction lên trước Step 6.

### 🟠 A4 — Prompt đọc `event_risk_level` sai tầng (minor — C2 còn lỗ nhỏ)
`services/macro_ai_verdict.py:224` đọc `tier2.get('event_risk_level')` nhưng shape production là `tier2 = {buy, sell, detail:{...}}` với field nằm trong `detail` (`services/news_service.py:1847, 2439-2447`) → prompt luôn hiện **"Event risk level: ?"**. Test mock shape top-level nên không phát hiện (`tests/test_step6_macro_verdict.py:65`, `tests/test_step6_review_fixes.py:246`).
**Fix**: `tier2.get('detail', {}).get('event_risk_level')` + sửa mock về đúng shape production.

### 🟠 A5 — Unit test ghi rác vào `data/` production (minor→major, đã xác nhận LIVE)
`tests/test_step6_macro_verdict.py:400/411/420` khởi tạo `MacroVerdictAssessor()` không inject storage → sau fix m10, default là `<repo>/data/`. Trên máy dev đang có **187 dòng journal test** + 1 file negative cache trong `data/` — chính đầu vào mà script M8 sẽ đọc để tính win-rate.
**Fix**: inject temp dir cho 3 test này (pattern `_assessor_with_temp_storage` có sẵn trong `tests/test_step6_review_fixes.py`); dọn 2 file đang ô nhiễm.

### 🟠 A6 — Negative cache ghi đè verdict tích cực cùng file path (minor, mất veto)
Đã được 2 refuter reproduce: positive verdict (fp-A, veto=true) → user đổi model AI (fp-B) → miss → AI fail → `put()` **ghi đè** fallback lên file verdict cũ. Trong 30 phút tiếp theo, verdict veto của ngày biến mất. Chiều an toàn (không làm dễ) nhưng làm mất lớp bảo vệ.
**Fix**: entry negative tách namespace (vd suffix `_neg`) hoặc policy "không ghi đè positive entry còn hạn trong ngày".

### 🟠 A7 — Thiếu test cho các lớp wiring/logic mới (major về mặt khóa regression)
Đúng lớp từng gây Critical 1: (1) forward `ai_service`/`macro_verdict_context` trong `_analyze_one_symbol` (`controllers/scanner_controller.py:2692`) — 0 test; (2) `_build_macro_verdict_context` (`:2434`) — 0 test; (3) chuỗi backtest `is_backtest=True` từ `_run_analysis_snapshot` — test dùng fake nuốt kwargs; (4) script `validate_macro_verdict.py` — 0 test; (5) convention `data/` (m10) — 0 test.
**Fix**: mỗi lớp 1 test nhỏ (unit cho `_analyze_one_symbol`/mapping; integration backtest thật với cache có sẵn; test `_match_trade`/`_label`/`_report` với sqlite tmp).

### 🟠 A8 — Các vấn đề của script M8 trên dữ liệu thật (minor)
Toàn bộ 74 lệnh đóng trong DB thật là `mode='mt5_sync'` với `result_r=None` (`services/journal_converters.py:402`) → mục "Trung bình R-multiple theo adjustment" của report **chết**; report đếm cả verdict bị bỏ do conviction<0.7; label không refresh khi outcome trong DB bị sửa; `except Exception: return []` nuốt lỗi DB thành "chưa có dữ liệu".

### 🟡 Nhóm nhỏ khác (gộp 1 commit dọn dẹp)
- `except Exception` chung trong `assess()` không log (`services/macro_ai_verdict.py:683-687`) — chỉ nhánh timeout có log.
- `_AI_EXECUTOR` không bao giờ `shutdown()` — thoát app có thể chờ zombie AI call tới timeout adapter; token vẫn đốt sau khi scan đã bỏ cuộc.
- UI vẽ status `skip` thành 🟢 "QUA" (`ui/screens/scanner_detail_screen.py:3646-3650`); `_aggregate_pipeline_diag` ghi key "skip" thô vào `pipeline_stats` (`core/system_backtest_engine.py:2283`).
- Outermost exception path không truyền `best_side` (`services/macro_ai_verdict.py:719-721`).
- Journal append từ 6 thread pipeline không atomic (Windows) — thêm lock module-level.
- Cache read không re-validate: `bool(data.get('veto'))` coerce string `"false"`→`True`; backtest `match_fingerprint=False` tin mọi file.
- Log `core/analysis_pipeline.py:1182` báo số adjustment *yêu cầu*, `macro_ai_deducted` là số *thực trừ* — lệch khi component bị floor.
- Không migration dữ liệu cũ ở `%APPDATA%` (chấp nhận mất thì nên ghi chú trong docs).
- `macro_ai_deducted`/verdict chưa có consumer ở scanner row/UI — "răng" của feature vô hình với người dùng.

## B. Cần chủ hệ thống quyết định (thiết kế)

1. **Deduction trừ vào component đã SCALE (0..~15-20 theo confidence) thay vì raw (0-30)** như docstring/commit/docs tuyên bố. Hệ quả: khi `macro_confidence` thấp, adjustment gần như không có răng (probe: raw=25 qua guard, conf=0.3 → scaled≈0 → deducted=0 dù payload vẫn báo adjustment=−5). Bước 7 VIX penalty (−2..−5) cũng ăn cùng component → đúng cặp VIX cao (nơi cần trọng tài nhất) lại dễ bị floor nhất. Muốn "đúng nghĩa đen thang −5..0" thì trừ vào raw hoặc trừ sau cap (kết hợp fix A2).
2. **Backtest V7** chỉ hữu ích khi replay ngày live đã quét và trùng side — nên ghi rõ giới hạn này trong docs section 17.

## C. Điểm làm tốt (xác nhận qua truy vết đối kháng)

Bất đối xứng tuyệt đối được giữ qua mọi đường mới; công thức tính lại Step 7 khớp từng thành phần với `compose_scenario_score`; integration test mới (`tests/test_step6_review_fixes.py:153`) chạy pipeline thật end-to-end — đúng bài học Bước 5; journal/cache không rò API key (đã kiểm tra log sensitivity); dedup journal trên cache hit giữ nguyên.

## Thứ tự sửa đề xuất

1. **A1** (starvation — khóa tính năng sống thật)
2. **A2 + A3** (điểm số nhất quán)
3. **A4 + A5** (nhanh, vệ sinh)
4. **A7** (test khóa wiring)
5. **A6 + A8**
6. Nhóm 🟡
7. Quyết định thiết kế **B1**

---

*Re-review tạo bởi quy trình đa agent (98 agent, model `deepseek-v4-flash` cho tầng verifier/refuter) kết hợp đọc code + reproduce trực tiếp ở tầng điều phối. Full test suite độc lập: 2579 passed, 8 skipped, 17 xfailed.*
