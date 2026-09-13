# Tech Lead review — task 16, lần 3

**Quyết định: CHANGES_REQUESTED. Chưa được bắt đầu task 17.**

- Reviewer: Codex, Tech Lead do người dùng chỉ định.
- Thời điểm: 2026-09-10 17:09 Asia/Saigon.
- Runtime HEAD: `fb9ea527ee7ff0eb48c53875e24796260008e92c`, branch `main`; tracked/staged diff rỗng.
- Phạm vi: bản response hiện tại và 14 file trong manifest; đối chiếu hai kế hoạch gốc và hai báo cáo review trước.
- Đã xác minh đủ 14 file, không hash mismatch. Aggregate digest: `92375BEA6B9955BBA8657369EC1F4686AAF34D4FD3F1FC63E198F218AF8D8F29`.
- Response SHA256: `36EC436E4350796BCD5DD5F03411FBBDFBEAD96DC08FF38DE00E4578326B085D`.
- Hai báo cáo trước giữ nguyên hash: review đầu `B856A93B0C6AC72185F12FE930A36237D98687E77581E028CC8113D2045BB99A`; rereview `39C885656A4038798E4083CAC69FE19BA8B4EC1AEA67F837EDC892F5891F4A20`.

## Kết quả

| Finding | Kết quả lần này |
|---|---|
| R16-01 | OPEN — P1: bootstrap-ready time vẫn loại source swing; fixture gán anchor không tuân theo rule |
| R16-02 | PARTIALLY RESOLVED — còn P2: nullable parent ID, expiry và plan đã sửa; còn invariant selected-zone trái selection |
| R16-03 | CLOSED ở mức đặc tả, giữ quyết định lần trước |
| R16-04 | CLOSED ở mức đặc tả: owner theo claim time, stable ID chỉ tie cùng thời điểm |
| R16-05 | PARTIALLY RESOLVED — còn P2: policy planner và RR đã rõ; bảng tham số vẫn chọn ATR khác cho hard distance |
| R16-06 | CLOSED ở mức đặc tả: directional wick đúng; 6 boundary cases tính lại đạt |
| R16-07 | CLOSED ở mức đặc tả, giữ quyết định lần trước |
| R16-08 | PARTIALLY RESOLVED — P2: có phương trình, nhưng raw examples vi phạm zone bounds và một feature mới đạt trần ngay tại detector minimum |
| R16-09 | CLOSED ở mức đặc tả, giữ quyết định lần trước |

Tổng: **5 finding đóng, 4 finding còn mở hoặc một phần**. Không yêu cầu làm lại phần đã được đóng. Các quyết định thành phần không thay thế APPROVED toàn gate 16.

## Các phần phải sửa trước khi trình lại

### R16-01 — [P1] Bootstrap anchor không thể chọn source đã nêu trong fixture

**Owner:** task 7/8, fixture task 5. **Vị trí:** `smc-structure-spec.md:133–135`; `tests/fixtures/smc_protected_swing_differs_from_latest.json:142`.

Spec đặt `bootstrap_anchor_at` bằng thời điểm cặp directional đầu tiên đủ confirmed, rồi yêu cầu source có `pivot_time > anchor_start_at`. Swing tham gia bootstrap luôn có pivot trước thời điểm chính nó được confirmed. Do đó source low L1 của cặp bootstrap bị loại theo chính rule mới.

Trong timeline spec: L1 pivot `2026-01-04 00:00`, confirmed `2026-01-05 00:00`; nếu cặp HH/HL đầu tiên cần L1 thì bootstrap-ready không sớm hơn 05/01. Phép lọc `04/01 > 05/01` sai, nhưng dòng first BOS vẫn kỳ vọng chọn L1. Fixture còn đặt anchor `03/01`, trong khi timeline fixture đến `04/01` mới có L1 — low thứ hai để đủ bootstrap 2 highs + 2 lows. Hai cách mô tả đều chưa chứng minh được first BOS có source hợp lệ.

**Quyết định/hướng sửa:** tách `bootstrap_ready_at` (thời điểm được phép đánh giá cấu trúc) khỏi mốc bắt đầu tìm source trong lịch sử. Source của BOS đầu tiên được xét trong interval nguồn có thể bắt đầu trước ready time, nhưng phải `confirmed_at <= break_close`; không backdate BOS về lúc chưa đủ bootstrap. Ví dụ dùng tracked pivot làm source interval anchor phải ghi rõ interval và boundary. BOS tiếp diễn tiếp tục dùng anchor BOS trước theo quy tắc đã đề xuất.

**Bằng chứng cần có để đóng:** ghi đủ pivot/confirmed_at của H0/L0/H1/L1, tính ready time từ các trường đó, liệt kê candidates sau filter và source được chọn. Fixture expected phải được suy ra đúng phép lọc, không gán thủ công anchor sớm để ép L1 vào. Làm BUY/SELL first BOS và một BOS tiếp diễn; không cần runtime chặng B ở lượt sửa hồ sơ.

### R16-02 — [P2] Lifecycle vẫn cấm selected zone đổi khi M15 đổi

**Owner:** task 10, đồng bộ task 12/13/14. **Vị trí:** `smc-lifecycle-spec.md:205`.

Các phần nullable parent link, confirmation ID không chứa parent ID, giữ plan khi trigger expired và matrix parent-open đã sửa đúng. Tuy nhiên câu cuối §11 vẫn yêu cầu thay toàn bộ M15 phải giữ nguyên **selected zone**, và gọi đây là invariant runtime test. `smc-selection-spec.md:259` lại có ví dụ đúng: A quality 90 waiting/B quality 80 confirmed → chọn B; khi A cũng confirmed → chọn A.

**Quyết định:** invariant chỉ áp dụng cho B/Q/L/C, quality và parent lifecycle của **từng candidate cố định**. Selection toàn danh sách phải được thay đổi khi confirmation rank đổi; final raw có thể thay vì selected candidate thay. Không sửa selection để làm invariant cũ đạt.

**Bằng chứng cần có để đóng:** sửa trực tiếp câu ở lifecycle và các câu đồng nghĩa còn sót; đặt cạnh nhau expected per-candidate quality không đổi và selected ID B→A. Phần còn lại của R16-02 không cần thiết kế lại.

### R16-05 — [P2] Hard-distance gate dùng hai nguồn ATR

**Owner:** task 8/13, kiểm tra tham chiếu task 6. **Vị trí:** `smc-parameter-table.md:129–130`; `smc-selection-spec.md:251–252`.

Selection đã chốt `execution_atr = first_finite_positive(technical.atr_h4, technical.atr_d1)` và distance `<= 3*execution_atr`. Nhưng P11 vẫn ghi current ATR **cùng timeframe** dùng cho distance. Với H1 zone, current H1 ATR=1, execution H4 ATR=2 và distance=4, P11 reject vì 4>3; selection pass vì 4<=6. Scorer/planner theo hai bảng sẽ lệch eligibility dù cùng snapshot.

**Quyết định:** chấp nhận nguồn execution ATR chung H4→D1 fallback từ frozen snapshot như proposal mới. Width/quality dùng formation ATR của zone; hard execution distance dùng execution ATR chung. Cập nhật P11 và các tham chiếu liên quan cho đúng phân quyền này, không thay công thức để dùng một ATR cho cả hai mục đích.

**Các phần chấp nhận của proposal:** dùng chung planner theo mapping risk-engine/TP cascade đã ghi; adapter không tự sở hữu công thức SL 1 ATR riêng; RR pre-spread đúng là `5.5/2.75/5.5` ở ba ví dụ; evaluation/plan cache tách và không phân biệt route trên cùng semantic input; technical fallback chỉ cho NO_ZONE/core đủ và caller explicit allow, không vượt gate SMC invalid/countertrend/watch-no-plan. Quyết định này cho hồ sơ, chưa cho triển khai trước khi toàn gate đạt.

**Bằng chứng cần có để đóng:** một dòng P11 cho từng ATR purpose và bảng H1/H4 ATR khác nhau chứng minh evaluator/planner cùng verdict. Giữ các ví dụ RR đã sửa, không cần chạy lại toàn bộ baseline.

### R16-08 — [P2] Ví dụ normalized feature chưa tuân theo input contract; feature S/D mới trở thành điểm mặc định

**Owner:** task 11/8, đối chiếu zone contract task 9. **Vị trí:** `smc-bqlc-spec.md:92, 116, 283–285`; `smc-zone-spec.md:52`.

**1. OB base width không thể khác original zone width theo contract hiện tại.** Zone spec định nghĩa original OB là toàn bộ high/low của chính candle/base được chọn. Nhưng ví dụ OB yếu dùng `base_width=.60`, ATR=1, zone width=1; ví dụ OB tốt dùng base=.10, ATR=1, zone width=.35. Các cặp này không thể đồng thời đúng với cùng OB gốc. Không được dùng body/refined width thay base span để làm compactness tốt hơn khi chưa đổi contract.

Nếu giữ zone width ở ví dụ và tuân thủ base=original width, tính lại theo công thức đang đề xuất sẽ là:

| Case | Original/base width / ATR | Compactness | Geometry | Q (giữ formation/integrity giả định trong ví dụ) | S (giữ B=.8, L=.2, C=.3) |
|---|---:|---:|---:|---:|---:|
| OB yếu | 1.00 | 0 | 0 | .540 | 7.980 |
| OB tốt | .35 | .65 | .8775 | .84550 | 10.11850 |

Có thể giữ base .60/.10 và đổi zone width tương ứng, nhưng phải tính lại toàn bộ chuỗi; không trộn hai bộ input.

**2. Ví dụ FVG gọi sai phép nội suy.** Dòng 285 ghi `linear(.70,.35,1)=.4615`. Theo định nghĩa trong chính tài liệu, linear này bằng `.5384615`; **inverse** mới bằng `.4615385`. Các subtotal geometry=.475, Q=.685, S=8.995 đang khớp inverse. Sửa tên/phép tính trong expected để không hướng scorer/test đi hai hướng.

**3. S/D formation feature mới luôn đạt trần ở detector minimum.** Dòng 92 dùng `linear(impulse_range/avg_range,1.0,1.5)`, trong khi detector task 9 bắt buộc ratio `>=1.50` (`smc-zone-spec.md:155`). Mọi S/D accepted đều nhận feature=1 và contribution mặc định `7 * .50 * .20 = .70` vào S. Thiết kế gốc yêu cầu việc chỉ đạt gate không tự nhận tối đa quality. Đây là vấn đề mới phát sinh từ feature thay thế trong lần sửa R16-08.

**Quyết định/hướng sửa:** giữ bounds validity là gate; không thay original/protective geometry để cứu ví dụ. Chốt feature S/D có mốc đánh giá nằm trong miền accepted và khả năng phân biệt departure vừa đủ với mạnh hơn, hoặc đề xuất lại trọng số/feature để không tạo bonus mặc định. Không tự đổi detector minimum để phù hợp scorer.

**Bằng chứng cần có để đóng:** raw OHLC/base bounds/ATR → width → normalized feature → Q → S nhất quán cho BUY/SELL; FVG inverse đúng; S/D tại minimum và trên minimum cho mức quality phân biệt theo rule đề xuất. Các tổng formation/integrity giả định phải được ghi là giả định, không gọi là full raw-to-score probe nếu chưa cung cấp input feature của chúng.

## Những mục đã đóng và kiểm chứng lần này

- **R16-04:** chấp nhận exclusive sweep owner theo `claim_eligible_at=max(reclaim_at,setup_available_at)`, stable ID chỉ tie cùng timestamp; late setup không rút assignment; missing owner history có reason. Probe Z claim trước/A claim sau và same-time tie đạt expected.
- **R16-06:** tính lại bằng Decimal đủ 6 case wick trong bảng: `[true,false,true,false,false,false]`, đều khớp. BUY lower wick/SELL upper wick trong fixture và response đã đúng.
- **R16-03/07/09:** giữ trạng thái CLOSED ở mức đặc tả.
- Parse ba fixture: PASS. Kiểm tra 14 file hashes và aggregate: PASS. Các báo cáo cũ giữ nguyên hash.
- Probe số độc lập: RR `5.5,2.75,5.5`; bootstrap source predicate false như mô tả; OB coherent examples/FVG interpolation/SD minimum và distance mismatch như các bảng trên.
- Runtime và tracked tests không đổi. Không chạy lại suite 418 test; kết quả baseline `418 passed in 3.41s` là của lần review đầu, không phải kết quả mới. Không chạy implementation feature mới, PIT/UI/replay/performance hoặc dispatch giao dịch.

## Điều kiện trình lại

Sửa đúng R16-01/02/05/08 còn mở, giữ số finding gốc; cập nhật response/progress và manifest của hồ sơ cuối. Không sửa các báo cáo review cũ. Chỉ cần kiểm tra tĩnh, phép tính và timeline tương ứng ở gate này; không triển khai task 17 để xử lý findings của hồ sơ.
