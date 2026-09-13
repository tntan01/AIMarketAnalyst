# Gate72 — Checkpoint A, review lần 2

**CHANGES_REQUESTED. Chỉ hoàn thiện F01; chưa F02, chưa task73.**

Tech Lead, 2026-09-11. Quyết định hiện hành thay trạng thái chờ review lần2; A-D01…07 trong review lần1 vẫn áp dụng. Giữ F00 và năm fixture fixes cũ đã PASS, không làm lại. RED do core chưa sửa là bình thường; A chưa đạt vì fixture/oracle/interface chưa nhất quán, không vì số tests RED.

## Evidence reviewer

- Acceptance: **30 failed, 19 passed in 0.83s** (49 cases).
- Reviewer probes: **13 failed, 3 passed in 0.13s**.
- Task57–71: **108 passed in 1.27s**.
- Retained SMC/scanner: **854 passed in 9.01s**.
- Năm core files và reviewer probe giữ SHA256 trong ledger F00. Reviewer không sửa implementation/tests.

## Giao CODER2 bốn việc nhỏ, theo thứ tự

### F01.1 — Khóa representation, đồng bộ docs/tests

Tech Lead chốt các điểm đang mâu thuẫn để Coder không phải đoán:

- **Pool:** numeric keys `swing_lows/swing_highs/equal_lows/equal_highs` giữ legacy projection. Canonical thêm container `records`; record có `pool_id`, `kind`, `level`, `source_ids`, `sources`, `usable_at`. Sources giữ per-source ID và confirmed/usable times. Tests lineage đọc records, không đòi `equal_lows[0]` vừa float vừa dict. Canonical sweep thiếu records/provenance không fallback numeric. Identity theo causal source, không observation time/index.
- **History:** giữ compatibility default hiện có của helper; canonical caller truyền `history_complete` tường minh theo dữ liệu thật. Complete fixture truyền True, unknown/incomplete truyền False. Không đề xuất default False rồi positive tests bỏ argument. Claim canonical cần cả reclaimed và setup-available times; parameterize thiếu từng field. Pool/source lineage phải theo claim vào assignment history.
- **Unknown metadata:** `metadata_state="unknown"`, `metadata_reason` không rỗng, `usable=False`; threshold không tính được là None, không0/NaN. Không thêm unknown vào lifecycle enum. Với confirmed input chưa có terminal evidence, giữ status confirmed/broken=False; unknown là data-quality state riêng. Terminal đã biết vẫn giữ invalid/expired/history. Forward qua lifecycle→context→typed round-trip. Tách missing ATR, missing tick, nonfinite và conflict thành cases độc lập; không assert status thuộc `{unknown,candidate,invalid}` hoặc chỉ `buffer != 0`.

**Đạt khi:** matrix/tests cùng schema, positive fixtures có completeness rõ, unknown khác invalid. Đây là interface cho F02/F06/F10, chưa sửa core.

### F01.2 — Validate mọi positive factory mới

`tests/test_smc_gate72_fix_acceptance.py:83–84` có close thấp hơn low. Reviewer chạy validator: `SMC_OHLC_INVALID` tại indices20/21/22 trong cả ba BUY reaction-index fixtures. Dòng501 cũng có `(112,114,111,110.5)` sai OHLC.

- Dùng exit `(110.2,110.22,110.15,110.2)` và reaction `(112,114,111,113)` như fixture R72-06 hợp lệ đã có. Zone[100,110], tick.1/ATR1: exit vượt tolerance.1 nhưng chưa displacement.25; reaction đạt. SELL mirror quanh210.
- Tất cả positive factories mới, kể cả local `run(rows)`, gọi validator với đúng timeframe. Invalid-data tests tách riêng, không nới validator.
- Test invalidation-versus-expiry hiện đặt invalidation row20, chưa collision với expiry. Đặt đúng candle age21 của D1 lifetime20; assert timestamp/index, không chỉ broken=True.
- Reaction trước terminal giữ đúng close-time/history sau append; reaction tại/sau terminal bị chặn. Có D1/H4 theo lifetime tương ứng.

**Đạt khi:** positive fixtures hợp lệ; timeline trước/đúng/sau terminal rõ; không sửa expected theo output.

### F01.3 — Sửa test chưa chứng minh đúng nhánh

Các line dưới thuộc `tests/test_smc_gate72_fix_acceptance.py` bản49 cases.

| Test / line | Bằng chứng vấn đề | Sửa và expected |
|---|---|---|
| equal usable/reclaimed,344 | Chỉ tạo pool, không gọi sweep detector | Có actual excursion/reclaim; cố định event close, parameterize source usable trước/bằng/sau close. Sweep nhận khi source usable trước/bằng, reject khi source usable sau. Equal pool cần cả hai source/max usable. Ghi rõ synthetic temporal seam, tách actual producer positive. |
| same-pool observation,420 | Cả hai claims đều sweep_id=sweep, reclaimed11:00 | Đổi observation sweep ID/time/rolling index nhưng giữ pool/source identity; serialize/restore history. Owner/assignment ID cũ giữ, late setup contribution0. Thêm new-source lineage control và history conflict fail-closed. Không chỉ same-sweep replay. |
| cutoff==invalidated_at,457 | reacted_at=None; actual reject reason `D1_REACTION_NOT_COMPLETED_REACTED` | Outside→touch→exit+reaction→invalidation. Prefix trước terminal valid/score>0; tại terminal invalid/0, cùng source/zone, giữ reacted_at cũ. Thêm expiry cutoff đối ứng. |
| typed terminal→D1,610 | `dict()` không typed; zone terminal-zone khác visit zone; cutoff3 giờ trước reaction3 ngày | Thật sự `SmcZone.from_dict(...).to_dict()`, khớp ID, dùng close cutoff sau reaction. Control nonterminal valid; canonical terminal tại cutoff invalid/0. Không pass vì mismatch/no-reaction/after-cutoff. |
| detector→lifecycle→D1,631 | Candidate H1 chưa confirmed; lifecycle H1 tính riêng với ATR tự gán, cutoff candle open; visits so với chính serialization | Có thể giữ dưới tên candidate/H1 smoke. Bổ sung confirmed detector zone D1→enrich lifecycle→typed restore→D1. Availability thật, cùng ID/source, close cutoff, expected bounds/event times từ fixture. Positive reaction trước terminal và negative tại terminal; dùng chính canonical lifecycle, không tính lại một lifecycle thay thế. |

**Đạt khi:** negative quan trọng có positive control, reject đúng nhánh. Cho phép behavior RED trước core fix; seam chưa có phải fail bằng assertion hợp đồng rõ, không làm hỏng collection.

### F01.4 — Audit coverage rồi trình một lần

- Map từng ô fix-plan §4 tới full test path + parameterized node ID. Reuse tests có sẵn nếu assertions đủ; không tăng count hình thức.
- Kiểm rõ node cho missing source; actual swing→pool→sweep positive; prefix/batch/stable pool identity; explicit override; causal metadata source; context owner permutation/filter; history missing/conflict; same-pool observation/new-source control; terminal repeat/typed/D1. Chưa có thì bổ sung, không ghi covered theo tên finding.
- Mỗi row ghi expected, preconditions đã assert, actual run và phân loại implementation RED/test defect. Chạy acceptance, probes, task57–71 và retained baseline theo fix-plan §5. Không xóa/skip/xfail tests hoặc sửa protected probes/golden/core.
- Trình **Checkpoint A lần3 — WAITING_REVIEW**, mapping F01.1…4→files/nodes/results, rồi dừng. Chỉ TL PASS mới F02; chưa CLOSED findings.

## Các cụm sau A giữ nguyên

F02 metadata→F03 terminal projection→F04 expiry/reaction→F05 D1 (**B**); F06 pool→F07 causal sweep→F08 owner→F09 contribution→F10 consumption/history (**C**); F11 end-to-end/regression/handoff (**D**). A PASS chỉ khóa tests/contracts, không phải gate72 APPROVED.
