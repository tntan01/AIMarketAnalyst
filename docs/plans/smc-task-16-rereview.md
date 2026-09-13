# Tech Lead review lại — SMC task 16

**Quyết định: CHANGES_REQUESTED. Chưa được bắt đầu task 17.**

- Reviewer: Codex, vai trò Tech Lead do người dùng chỉ định.
- Ngày review: 2026-09-10, 15:12 Asia/Saigon.
- Runtime HEAD: `fb9ea527ee7ff0eb48c53875e24796260008e92c`, branch `main`; không có diff tracked/staged.
- Hồ sơ: 14 file trong manifest của `smc-task-16-review-response.md`, đối chiếu hai kế hoạch gốc và báo cáo review lần đầu.
- Đã xác minh đủ 14 SHA256 file và aggregate submission digest: `528524F8A2C2E57D88D706A5DB8CE291A113C6109955DFBCFB474C2D90B0A6D7`.
- SHA256 response được review: `5444119C9EFD56A9B72BBC6FFC8E1D4C200EF48F4443B9CB8E1ADAC9ABD269D3`.
- SHA256 báo cáo lần đầu hiện tại: `B856A93B0C6AC72185F12FE930A36237D98687E77581E028CC8113D2045BB99A`. Báo cáo này không chỉnh sửa báo cáo gốc, response, spec hoặc runtime của coder.

## Kết quả theo finding gốc

| Finding | Kết quả review lại | Phần đã đạt / phần còn thiếu |
|---|---|---|
| R16-01 | OPEN — P1 | Có candidate-local reversal state và fallback provisional; source interval và bootstrap BOS đầu tiên vẫn thiếu/sai so với ví dụ nguồn |
| R16-02 | OPEN — P1 | Tách parent quality lifecycle và M15 entry visit đúng hướng; parent ID trước H4 close, selection invariant và readiness/plan còn mâu thuẫn |
| R16-03 | CLOSED ở mức đặc tả | M15 penalty không còn tác động current quality/projection; fixture expected mới penalty=0 |
| R16-04 | PARTIALLY RESOLVED — P1 | Age/dwell/reclaim đã thống nhất; exclusive sweep ownership giữa nhiều setup chưa có quy tắc nhân quả |
| R16-05 | OPEN — P1 | Có inventory planner và phân lớp cache; chưa có một policy thực thi đủ cụ thể để duyệt; ba ví dụ RR sai |
| R16-06 | OPEN — nâng lên P1 | Phương trình mới đảo wick BUY/SELL trong parameter, fixture và response |
| R16-07 | CLOSED ở mức đặc tả | D1 proximity/open/completed-unreacted không còn nhận reaction feature C |
| R16-08 | PARTIALLY RESOLVED — P2 | Bounds validation đã tách khỏi Q; feature thay thế OB/S-D chưa có phương trình/mốc số |
| R16-09 | CLOSED ở mức đặc tả | Watch-no-plan giữ selected IDs/quality/lifecycle; plan/reference null, phân biệt no-zone |

Đóng finding về đặc tả không phải chứng nhận runtime của chặng sau. Tổng cộng **3 finding đóng, 6 finding còn mở/toàn phần hoặc một phần**.

## Findings còn mở và bằng chứng

### R16-06 — [P1] Wick BUY/SELL bị đảo chiều

**Owner:** task 8, đồng bộ task 4/12/15 và response.

**Vị trí:** `smc-parameter-table.md:119`, `tests/fixtures/smc_m15_stale_rejection.json:382–383`, `smc-task-16-review-response.md:81–82`.

Hồ sơ mới ghi BUY dùng upper wick và SELL dùng lower wick. `core/smc_m15_confirmation.py:169–177` và bằng chứng lần review đầu là chiều ngược lại:

```text
BUY:  lower_wick = min(open, close) - low; close > open
SELL: upper_wick = high - max(open, close); close < open
threshold = max(0.80 * abs(close-open), 0.25 * (high-low))
directional_wick >= threshold
```

Probe chạy trong lần review này:

| Side | O/C/H/L | Threshold | Wick theo hồ sơ mới | Runtime hiện tại | Công thức hồ sơ mới |
|---|---|---:|---:|---|---|
| BUY | 100 / 100.4 / 100.5 / 99.4 | 0.32 | 0.10 | Rejection=true | false |
| SELL | 100 / 99.6 / 100.6 / 99.5 | 0.32 | 0.10 | Rejection=true | false |

Đây là lỗi hướng của công thức, không phải khác biệt rounding. Fixture chỉ parse JSON và kiểm marker sẽ không phát hiện được nó.

**Quyết định Tech Lead:** giữ đúng directional wick của runtime như công thức trên; không duyệt proposal đảo wick. Follow-through/visit vẫn là điều kiện bổ sung của contract mới.

**Sửa và kiểm tra lại:** sửa đồng bộ cả ba nơi; đưa OHLC BUY/SELL đạt/không đạt, wick bằng/dưới ngưỡng, doji, stale/ngoài visit vào bảng expected. Tính wick và threshold từ OHLC độc lập, không chỉ chép nhãn accepted.

### R16-05 — [P1] Planner chưa có policy thống nhất; RR sai có thể đổi verdict min-RR

**Owner:** task 13, đồng bộ task 8/14/15.

**Vị trí:** `smc-selection-spec.md:249–257`.

Ba ví dụ mới sai phép tính pre-spread RR:

```text
RR = abs(TP-entry) / abs(entry-SL)
```

| Entry | SL | TP | RR ghi trong hồ sơ | RR đúng |
|---:|---:|---:|---:|---:|
| 98.5 | 97.5 | 104 | 6.5 | 5.5 |
| 98.5 | 96.5 | 104 | 3.75 | 2.75 |
| 101.5 | 102.5 | 96 | 3.67 | 5.5 |

Nếu min-RR=3, ví dụ thứ hai bị ghi nhầm thành pass trong khi phải reject. Không thể dùng các số này làm expected parity.

Bảng vẫn để `route-owned SL adapter`, TP là tên `take_profit_policy` chưa có phép chọn, execution ATR “chờ duyệt nguồn”. Như vậy còn nhiều policy khả dĩ; không có một bộ quy tắc đủ cụ thể để Tech Lead duyệt chỉ bằng cách chọn “dùng chung”. Ví dụ `SL=entry-1` chưa chỉ rõ giữ/thay nhánh risk hiện hữu nào. Technical fallback vẫn chưa có ma trận allowed/blocked đủ rõ.

**Quyết định Tech Lead:** Analyze/Scanner/replay phải dùng cùng thuật toán plan và cùng execution policy khi input/policy giống nhau; route adapter chỉ chuyển dữ liệu, không sở hữu công thức SL/TP khác nhau. Đồng ý tách formation ATR phục vụ quality và execution ATR phục vụ plan, đồng ý tách evaluation cache và plan cache. Không dùng route identity để hợp thức hóa plan khác nhau trên cùng semantic input. Chưa duyệt công thức `SL=entry-1` thay policy hiện hữu.

**Sửa và kiểm tra lại:** đề xuất đúng một mapping cụ thể từ nhánh code hiện hữu sang shared planner: entry/refinement, SL source/buffer/floor, TP rule, execution ATR source/fallback, width/distance và technical fallback. Ghi tác động route nào thay đổi; không tự đổi runtime/risk policy. Tính lại BUY/SELL và min-RR boundary bằng số đúng, có selected candidate/trace. Naming một policy hoặc giữ nhiều lựa chọn mở chưa đáp ứng finding này.

### R16-02 — [P1] Parent visit ID và invariant M15 vẫn làm contract không thực thi nhất quán

**Owner:** task 10/12/13/14.

**Vị trí:** `smc-lifecycle-spec.md:192–205`, `smc-readiness-spec.md:29, 70, 207–219`, `smc-selection-spec.md:259`.

Ba vấn đề cụ thể:

1. **Parent ID chưa tồn tại:** vùng H4 đã available từ 08:00, lần chạm đầu tiên là M15 08:15, confirmation lúc 08:45; H4 08:00–12:00 chưa đóng. Parent lifecycle chỉ dùng H4 đã đóng nên chưa có `parent_lifecycle_visit_id` cho lần chạm này. Hồ sơ lại bắt buộc ID đó trong confirmation và minh họa parent đã open vì H4 đang forming. Muốn tạo parent visit trước 12:00 sẽ vi phạm cutoff/quality ownership; muốn chờ 12:00 sẽ quay lại chặn M15 hợp lệ.
2. **Cấm đổi selected zone trái selection policy:** §11 lifecycle và §12 selection cấm M15 làm đổi selected IDs. Nhưng §4 selection ưu tiên current confirmation. Cho A quality=90, B quality=80 và cả hai có plan: chỉ B confirmed thì chọn B; đổi M15 để chỉ A confirmed thì phải chọn A. Quality của từng candidate không đổi, nhưng selected IDs và raw của result cuối có thể đổi. Thiết kế gốc §9/§10 đã cho phép điều này.
3. **Readiness/plan chưa đồng bộ:** matrix cũ vẫn chặn open parent visit, phần bổ sung lại cho READY khi M15 đủ. Readiness §10 còn đặt `plan=null` khi M15 expiry, dù expiry không làm TP/SL/geometry mất hợp lệ. Khi ghép với precedence “no-plan → WATCH_ZONE” sẽ mâu thuẫn expected `WAITING_CONFIRMATION`.

**Quyết định Tech Lead:** chấp nhận tách lifecycle theo source timeframe và entry visit M15. Invariant độc lập M15 áp dụng cho quality/lifecycle của **cùng candidate**, không đóng băng selection toàn hệ thống. M15 expiry chỉ hủy quyền xác nhận; không tự xóa một geometric plan còn hợp lệ.

**Sửa và kiểm tra lại:** chốt M15 confirmation ID không phụ thuộc vào một parent visit tương lai; parent link có thể nullable khi chưa có event hợp lệ, và việc bổ sung link sau không đổi identity trigger. Định nghĩa rõ M15 visit exit/re-entry/expiry ở biên. Thay các matrix/câu cũ đang mâu thuẫn, không chỉ thêm một mục cuối file. Có timeline first-touch trước H4 close, sau H4 close, hai candidate đổi confirmation, expired trigger nhưng plan còn valid; ghi exact ID/nullability, quality và readiness expected.

### R16-01 — [P1] Source interval loại mất pullback cần bảo vệ và chưa bootstrap BOS đầu tiên

**Owner:** task 7/8, đồng bộ fixture task 5.

**Vị trí:** `smc-structure-spec.md:133–143, 154–158`.

Rule mới chỉ xét source low từ `previous_bos_close` đến `continuation_high.pivot_time`. Nó loại mọi pullback low nằm sau tracked high nhưng trước candle phá high. Đây chính là kiểu nguồn đã có trong fixture gốc: `H1=110` ở 03/01 → `L1=100` ở 04/01 → BOS phá H1 ở 05/01. L1 nằm ngoài interval kết thúc tại H1 nhưng fixture vẫn yêu cầu protected=L1. Với BOS đầu tiên sau bootstrap còn chưa có `previous_bos_close`, spec không định nghĩa anchor thay thế.

Ví dụ tiếp diễn tương tự: BOS cũ t0 → high mới t1 → low pullback t2 đã confirmed → close phá high ở t3. Rule mới không thể chọn low t2, dù đó là swing dẫn đến break. Việc chỉ đặt tên “source hợp lệ” trong timeline không chứng minh phép chọn đúng.

Boundary reclaim cũng chưa nhất quán: bước 10.3 yêu cầu strict `> level+buffer`, timeline lại dùng `>=`; công thức cuối file dùng `+epsilon` cho cả hai hướng, trong khi bearish break phải đi xuống dưới `level-buffer`.

**Sửa và kiểm tra lại:** chốt initial tracked level/anchor cho BOS đầu tiên và interval source cho các BOS sau, bao gồm pullback trước break; định nghĩa bằng pivot time và confirmed time riêng. Chọn một boundary reclaim thống nhất. Timeline BUY/SELL phải có timestamp/pivot/confirmed_at/source IDs thực sự được rule chọn, gồm fixture gốc, nhiều pullback, equal boundary và reversal. Không cần viết runtime chặng B để sửa tài liệu này.

**Phần chấp nhận:** external width-2 provisional không phát canonical BOS/CHoCH/protected; candidate-local reversal state là hướng xử lý hợp lý. Phần đó không tự giải quyết source/anchor còn thiếu.

### R16-04 — [P1] Dedupe theo cặp không xác định owner duy nhất giữa các setup theo thời gian

**Owner:** task 8/11, liên quan rule sweep linking task 68/69 sau này.

**Vị trí:** `smc-parameter-table.md:96, 145`; `smc-bqlc-spec.md:153`.

Age, dwell và one-candle reclaim đã có công thức/boundary nhất quán; chấp nhận các phần này ở mức đặc tả. Phần consumed vẫn đồng thời quy định:

- Dedupe `(setup_id,sweep_id)`.
- Hai setup khác nhau không được tái dùng cùng sweep.
- Sort stable ID trước khi link sẽ bảo đảm batch/incremental giống nhau.

Hai cặp `(A,S)` và `(B,S)` khác nhau nên dedupe theo cặp không thực thi exclusive ownership. Nếu lấy setup theo ID nhỏ nhất của toàn snapshot, setup `Z` có trước đã nhận sweep, setup `A` xuất hiện muộn hơn có thể lấy lại evidence khi batch rebuild; incremental giữ owner cũ thì lệch batch, còn rút evidence khỏi Z thì trái yêu cầu contribution không biến mất chỉ vì snapshot sau.

**Quyết định Tech Lead:** nếu giữ policy exclusive giữa các setup như proposal, cần owner theo thời điểm setup đủ điều kiện liên kết trước; stable ID chỉ tie-break khi cùng thời điểm. Setup xuất hiện muộn không được rút evidence đã gắn hợp lệ. Phân biệt pool consumption, assignment cho setup và dedupe child contribution.

**Sửa và kiểm tra lại:** ghi thuật toán owner/eligibility/availability tường minh. Timeline S → Z đủ điều kiện → A xuất hiện muộn có ID nhỏ hơn; same-time ties; child trùng; restart/rebuild/prefix. Ghi assignment/contribution expected, không chỉ khẳng định order-invariant.

### R16-08 — [P2] Feature thay thế vẫn là tên mô tả, chưa có công thức

**Owner:** task 11/8.

**Vị trí:** `smc-bqlc-spec.md:113–116, 283–284`.

Đã bỏ bonus do ordered/finite, nhưng `family_geometry_score` cho OB chỉ được gọi là “compactness … so với formation ATR”, S/D là “compression … so với giới hạn base”. Chưa có phương trình, endpoints, clamp/missing policy hoặc expected từ raw input. Ví dụ đưa compactness `.40` và `.90` như input có sẵn, nên chỉ chứng minh phép cộng `0.65/0.35`, không chứng minh detector/scorer tính được các feature đó.

Nếu coder tự dùng `1-width/ATR` cho OB, width=1 ATR sẽ cho 0, không phải .40 như ví dụ. Nếu dùng feature khác thì cần đặc tả nó trước gate 16. Cũng cần chỉ rõ có tái sử dụng feature formation hay không và tổng trọng số thực tế khi dùng lại cùng đại lượng.

**Quyết định Tech Lead:** bounds validity tiếp tục là gate, không là quality feature. Chưa duyệt `.40/.90` hoặc công thức family chỉ qua mô tả compactness/compression.

**Sửa và kiểm tra lại:** điền công thức OB/FVG/S-D, đơn vị, ATR/statistics nguồn, mốc chuẩn hóa và missing policy; ví dụ raw bounds/base/ATR → normalized feature → geometry → Q → S. Kiểm weak/good/boundary và BUY/SELL. Không cần scorer runtime cho bước này.

## Quyết định cho các mục đã đóng

- **R16-03:** chấp nhận zero M15 quality delta. Nếu giữ field penalty để tương thích, current phải cố định 0/audit-only và validator không cho tác động S/projected raw; không cần thêm proposal loại field mới để đóng finding này.
- **R16-07:** chấp nhận reaction feature bằng 0 khi chưa completed-reacted. Không bổ sung partial-reaction event trong phạm vi lần sửa này. Các component C độc lập khác vẫn được tính theo bằng chứng của chúng.
- **R16-09:** chấp nhận selected watch IDs không phụ thuộc plan availability. `selected_visit_id` giữ khi đã có visit hợp lệ dù plan null; chưa có visit thì null. Candidate pending chưa confirmed chỉ là trace, không là selected usable zone. Vấn đề M15 expiry tự xóa plan được giữ tại R16-02, không mở lại nội dung null/no-zone đã sửa đúng.

Các quyết định thành phần trên giúp coder hoàn chỉnh hồ sơ; **không phải APPROVED toàn gate 16**.

## Kiểm tra đã thực hiện trong lần review lại

- `git rev-parse HEAD`, `git status --short`, `git diff --exit-code`, `git diff --cached --exit-code`: HEAD giữ nguyên; tracked/staged không đổi.
- Tính lại SHA256 14 file và aggregate theo đúng phương pháp response: tất cả khớp.
- Parse ba fixture bằng `ConvertFrom-Json`: tất cả hợp lệ. JSON hợp lệ không chứng minh công thức wick/expected đúng.
- Python probe read-only gọi `_m15_rejection` với hai OHLC BUY/SELL và đối chiếu công thức hồ sơ mới: hai trường hợp đều khác kết quả như bảng R16-06.
- Tính độc lập ba RR từ entry/SL/TP: `5.5`, `2.75`, `5.5`.
- Thử tuple confirmation-first trên hai candidate giả định có plan hợp lệ: thay confirmation chọn `B → A`; đây là kiểm tra logic đặc tả, không gọi là test implementation mới.
- Không chạy lại toàn bộ 418 test vì runtime và tracked tests không đổi; kết quả `418 passed in 3.41s` thuộc lần review trước, không được ghi thành kết quả mới của lượt này. Chưa chạy runtime feature mới, UI/PIT/replay/performance/execution.

## Yêu cầu trình lại

Giữ số finding gốc. Coder sửa sáu finding còn mở, cập nhật response với nội dung còn thiếu và bằng chứng số/timeline cụ thể. Sửa trực tiếp các rule/matrix mâu thuẫn để mỗi hành vi chỉ có một định nghĩa áp dụng; không dùng câu “supersedes” để bỏ qua các bảng/fixture còn sai. Tạo manifest mới cho hồ sơ cuối, giữ task 16 ở WAITING_REVIEW và dừng trước task 17.
