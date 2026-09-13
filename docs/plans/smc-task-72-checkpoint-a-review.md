# Gate72 — Checkpoint A, review lần 1

**Quyết định: CHANGES_REQUESTED tại checkpoint A. Chưa được làm F02.**

Tech Lead, 2026-09-11. Phạm vi review chỉ F00/F01, không yêu cầu sửa core lúc này. Gate72 vẫn CHANGES_REQUESTED; không task73. Bản trình gồm fix-progress, acceptance-matrix và `tests/test_smc_gate72_fix_acceptance.py`.

## 1. Phần đã đạt, không làm lại

- **F00 PASS:** baseline được tái lập; năm core files và reviewer probes giữ nguyên SHA256 của review gate72.
- **F01 phần đính chính OHLC PASS:** năm test factories đã dùng validator; fixture-validity probe R72-09 đạt. Giữ các sửa đổi này, không quay lại OHLC sai.
- Reviewer chạy lại task57–71: **108 passed in 1.26s**; retained SMC/scanner baseline (loại file acceptance mới): **854 passed in 8.95s**.
- Acceptance mới + reviewer probes chạy chung: **26 failed, 4 passed in 0.26s**; tương ứng acceptance mới13 fail/1 pass và probes13 fail/3 pass. RED behavior trước core fix là đúng quy trình, **không phải lý do từ chối A**.

Lý do A chưa đạt là coverage được mô tả nhưng chưa có tests/expected cụ thể, và một quy tắc thứ tự event ghi ngược. Không yêu cầu làm toàn bộ implementation xanh để qua A.

## 2. Các mục F01 cần bổ sung

### A-01 — Matrix đang gán coverage rộng cho test chỉ tái hiện một lỗi

14 cases mới gần như sao lại reviewer probes; thêm số test không tự bổ sung coverage. Dùng lại helper fixture không phải vấn đề, nhưng node phải thực sự kiểm chứng điều matrix tuyên bố.

Ví dụ:

- R72-01 node chỉ kiểm sweep trước confirmed_at; không có positive sau usable, equality, provisional/missing, equal pool hai source hay prefix/batch.
- R72-04 node gọi attach hai lần trên cùng dict; không serialize/restore, không kiểm history missing/conflict hoặc cùng pool với observation khác.
- R72-07 node chỉ kiểm forward tick argument; không có item parity, missing/nonfinite metadata, explicit override và equality/outside buffers.
- R72-08 chưa có typed round-trip/consumer; R72-05 chỉ dùng typed lifecycle, chưa serialized mapping/legacy conflict cho terminal path.
- R72-09 node gọi các factory bằng rows viết riêng rồi validate; **không chạy detector → lifecycle → D1/context**. OHLC hợp lệ chưa chứng minh zone bounds/source thực sự do detector tạo. Không ghi toàn bộ obligation09 GREEN chỉ từ fixture-validity pass.

**Cách sửa:** tách matrix thành từng case cụ thể, mỗi case có input/metadata/cutoff, expected chính xác, contract/decision reference và node ID thực sự chạy. Có thể tham chiếu test Coder có sẵn nếu assertions thật sự đủ; không bắt duplicate mọi test vào file mới. Với tests mới, cho phép RED nhưng phải collect/run, không skip/xfail. Bao phủ đủ §4 của fix-plan trước A; không đợi sửa implementation rồi mới nghĩ expected.

### A-02 — Thứ tự terminal/reaction đang bị ghi ngược

Matrix, interface ledger dòng lifecycle follow-through, ghi “Same-candle exit then reaction remains ordered before terminal check”. Điều này trái lifecycle spec §1/§8 và sẽ tái tạo R72-06.

**Đúng:** validate/cutoff/availability → invalidation/expiry gate → exit → reaction. Nếu candle đã terminal thì không tạo reaction tại close đó. Chỉ khi candle chưa terminal mới cho exit rồi reaction cùng close. Reaction hợp lệ của candle trước terminal vẫn giữ trong history.

Sửa dòng này và thêm ba test: reaction trước terminal được giữ; reaction đúng candle terminal bị chặn; reaction sau terminal bị chặn. Kiểm BUY/SELL và priority invalidation so với expiry; không dùng actual output làm expected.

### A-03 — Interface ledger chưa đủ cho Coder triển khai không đoán

Các dòng hiện là mô tả trách nhiệm, chưa chỉ rõ cấu trúc/caller propagation. Bổ sung tối thiểu:

- Pool record: identity/source IDs/per-source confirmed-or-usable times, canonical versus numeric legacy projection; caller nào chuyển dữ liệu này tới sweep.
- Ownership: chữ ký/caller nào nhận assignment history và history completeness, record nào giữ owner khi current window mất owner, cách báo conflict.
- Metadata: cách biểu diễn unknown/fail-closed qua ZoneLifecycle → context → typed model; tick/ATR lấy từ đâu tại từng sự kiện và cách phân biệt canonical thiếu field với legacy payload.
- Setup availability phải có nguồn rõ ràng, không lấy thời điểm child tình cờ đứng đầu; pool identity phải phân biệt observation mới và nguồn pool thật sự mới.

Đề xuất tên field/signature cụ thể trong tài liệu/tests, **không sửa core để thử API**. Nếu chưa có seam, test có thể assert callable hoặc contract payload requirement có thông báo rõ thay vì import lỗi cả suite. TL sẽ duyệt phần representation ở A lần2; các business decisions dưới đây không cần hỏi lại.

## 3. Tech Lead chốt các boundary đã được hỏi

Đây là quyết định làm rõ cho F01; ghi reference tới báo cáo này trong matrix, không sửa lịch sử review/golden R56.

| ID | Quyết định | Expected cần khóa |
|---|---|---|
| A-D01 | Session này đánh giá sweep tại **candle close/reclaimed_at** theo mô hình closed-bar, không suy diễn thứ tự tick. `pool_usable_at <= reclaimed_at` là temporal gate inclusive; equal-pool usable không sớm hơn max usable time của tất cả source cần thiết. Mọi source phải hợp lệ/confirmed, không thể chỉ dựa boolean tại snapshot tương lai. | Trước usable: reject; đúng/sau usable: temporal gate đạt, nhưng chỉ nhận sweep nếu excursion/reclaim và source validity cũng đạt. Synthetic equality test tách riêng temporal contract; actual detector test không được dựng pivot mâu thuẫn với OHLC. |
| A-D02 | Claim canonical cần cả reclaimed_at và setup_available_at; missing một trong hai fail closed. Owner theo max hai thời điểm, tie stable setup ID. | Không fallback sang timestamp còn lại để cấp assignment. |
| A-D03 | Nếu owner chỉ còn history và không có child hiện tại, giữ owner/assignment, contribution trên current child list bằng0. | Không cấp cho late setup; owner hiện diện nhiều child tổng1. |
| A-D04 | Tại cutoff bằng invalidated_at/expired_at, active D1 reaction đã bị chặn. | valid=false/score0; history trước terminal giữ nguyên. |
| A-D05 | Terminal check luôn trước reaction của cùng candle, như A-02. | Before/at/after terminal matrix không có reaction mới tại/sau terminal. |
| A-D06 | Cùng nguồn và cùng causal pool identity, thay observation time/list order/rolling index không tạo pool mới để né consumed. New-source claim phải giữ source IDs/lineage chứng minh pool mới; thêm metadata hoặc cấp ID tùy ý không đủ. | Same-pool observation không tái cấp ownership; history/identity mâu thuẫn phải fail closed, không tự thay owner. Ghi proposal identity/lineage cụ thể để TL xác minh ở A lần2. |
| A-D07 | Tick argument và tick trong canonical item cùng scope nếu cùng giá trị phải tương đương. Chỉ một nguồn hợp lệ được cung cấp thì forward nguồn đó. Khi hai nguồn được khai báo cùng scope nhưng mâu thuẫn, trả unavailable/unknown thay vì âm thầm chọn bên thuận tiện. | Item-only/argument-only/equal-both parity; conflicting/nonfinite canonical data không ra threshold0 hoặc cấp usable. Missing ATR riêng vẫn là missing dù tick đã có. |

Các quyết định temporal không cho phép bypass quality/provenance, không yêu cầu một persistence service mới và không mở task73.

## 4. Việc giao tiếp theo — chỉ F01 bổ sung

1. Giữ F00 và fixture fixes đã đạt; không làm lại baseline audit dài hoặc đổi core.
2. Sửa A-02, ghi A-D01…07 vào matrix; triển khai coverage còn thiếu A-01 và interface proposal A-03.
3. Matrix phải trỏ tới **case-level node IDs**, phân biệt DONE/RED/PENDING evidence. Case chưa viết không được gán nhãn covered chỉ vì có tên finding.
4. Chạy targeted fixtures, full matrix tests + reviewer probes và retained baseline; ghi actual/known RED. Nếu thêm tests làm lộ vấn đề trong phạm vi đã liệt kê, giữ RED có giải thích, không sửa production.
5. Trình lại **Checkpoint A lần2 — WAITING_REVIEW**. Chỉ TL mới chuyển A sang PASS; không F02 cho tới lúc đó. R72-09 mới đạt phần fixture-validity, chưa CLOSED toàn finding vì end-to-end còn thiếu.
