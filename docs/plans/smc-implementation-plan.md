# Kế hoạch thực hiện nâng cấp SMC — checklist cho Coder

Ngày kế hoạch: 2026-09-10. Cập nhật trạng thái: 2026-09-11. **Tạm dừng triển khai để hoàn thiện mục tiêu/phạm vi cho người dùng xem xét.** Gate 16/40/56 đã APPROVED; task 57–71 đã có implementation, gate 72 còn CHANGES_REQUESTED. Trạng thái từng task lấy từ [nhật ký tiến độ](smc-implementation-progress.md).

Tài liệu này là checklist thực hiện của [bản thiết kế SMC](smc-scoring-upgrade-plan.md). Yêu cầu mới nhất: chia việc nhỏ, đánh số liên tục, dừng tại mốc Tech Lead review. Các quy định review ở đây thay thế hướng dẫn cũ cho phép làm xuyên suốt không dừng.

## Cách Coder thực hiện

**Ưu tiên hiện tại:** hoàn thiện và xem xét mục tiêu tại [§1.1–1.2 của thiết kế](smc-scoring-upgrade-plan.md). Chưa tiếp tục F01.1–F01.4 hoặc task 73. Checklist 144 task bên dưới giữ làm phạm vi phương án đầy đủ; chỉ tiếp tục sau quyết định của người dùng. Nếu chọn thu gọn, cập nhật mapping task giữ/sửa/hoãn trước khi triển khai, giữ lịch sử số task và review.

- Làm task **1 → 144**, không bắt đầu chặng sau khi review chặng trước còn chờ. Task sau kế thừa đầu ra task trước; tham chiếu task cụ thể là phụ thuộc bổ sung, không phải quyền bỏ qua các bước ở giữa.
- Mỗi dòng là một đơn vị công việc: một model, một quy tắc, một consumer hoặc một nhóm kiểm thử cùng hành vi. Chỉ sửa đúng phạm vi cần để đạt đầu ra của dòng đó.
- Tên file là điểm bắt đầu đã tìm thấy trong repository. Có thể tách helper nhỏ khi cần; ghi vị trí mới vào nhật ký. Không dựng framework, dịch vụ hoặc database mới.
- Các task đặc tả đầu chặng A tạo tài liệu/quy tắc để duyệt; chưa thay runtime. Không tự đoán ngưỡng còn thiếu rồi triển khai ở chặng sau.
- Coder được tự xử lý chi tiết triển khai trong quy tắc đã duyệt. Thay công thức, ngưỡng đã khóa, điều kiện entry, hình học rủi ro hoặc contract cần trình lại Tech Lead trước khi làm phần phụ thuộc.
- Giữ sản phẩm cá nhân đơn giản: tên SMC, một công thức mặc định, ít thông tin trên màn hình chính. Không thêm menu chọn engine hoặc nhãn số thế hệ.
- Dùng branch/checkout phát triển phù hợp và giữ thay đổi đang có của người dùng. Không cần mỗi task một branch hoặc một PR.
- Không gửi lệnh tiền thật để test, không tự bật auto-trade. Dùng fixture, dữ liệu lịch sử, replay ngắn, mock/dry-run cho dispatch.
- Bộ test chỉ khóa hành vi có ý nghĩa. Không tạo test sao chép công thức production làm expected, không viết một test cho mỗi dòng code.
- Bắt gặp lỗi ngoài phạm vi thì ghi riêng, không tự mở rộng đợt nâng cấp. Nếu không có dữ liệu thật/công cụ UI thì ghi task liên quan BLOCKED và nêu phần cần cung cấp; không thay bằng giả định đã kiểm tra.
- Các thay đổi contract có thể làm test consumer cũ cần cập nhật ở chặng E. Ghi rõ lỗi đã dự kiến và task xử lý; không che lỗi mới, không đánh dấu toàn hệ thống xanh khi chưa tích hợp.
- Phần mềm phải giữ lịch sử và lệnh đang mở. Kiểm tra tương thích nội bộ không được hiển thị thành tên sản phẩm.
- Đây là kế hoạch nâng cấp kỹ thuật. Không yêu cầu backtest tối ưu lợi nhuận; cũng không lấy QA kỹ thuật thay cho các điều kiện chứng nhận giao dịch mà chương trình đang yêu cầu.

## Cách ghi tiến độ

Tạo một nhật ký ngắn trong cùng thư mục: `smc-implementation-progress.md` khi bắt đầu triển khai. Không cần tracker hoặc ứng dụng quản lý công việc mới.

Mỗi dòng ghi: **task | TODO/DOING/DONE/BLOCKED/WAITING_REVIEW | file/hàm đã đổi | kiểm tra và kết quả | tồn tại**. Task chưa thực hiện không được đánh DONE. Task review chỉ DONE sau khi có APPROVED từ Tech Lead.

Nếu một lỗi được phát hiện sau review, sửa lại task chịu trách nhiệm và ghi lần kiểm tra mới; không đổi số các task đã tồn tại. Nếu cần mở rộng phạm vi bằng task mới, chỉ thêm số từ **145** trở đi sau khi Tech Lead chốt; cập nhật phụ thuộc và mở lại review nghiệm thu nếu cần.

## Các điểm dừng bắt buộc

| Task review | Nội dung Tech Lead duyệt | Khi chưa APPROVED |
|---|---|---|
| **16** | Định nghĩa, tham số, công thức, readiness, selection và compatibility | Không làm task 17 |
| **40** | Dữ liệu, nhân quả, protected swing và BOS/CHoCH | Không làm task 41 |
| **56** | Detector OB/FVG/S-D, thời điểm có thể dùng vùng, nhóm setup | Không làm task 57 |
| **72** | Lifecycle, sweep, full fill và D1 reaction | Không làm task 73 |
| **100** | Điểm, M15, chọn vùng, plan và raw projection | Không làm task 101 |
| **116** | Tích hợp đường chạy, parity và gate/revalidation | Không làm task 117 |
| **128** | Persistence, lịch sử và UI cá nhân | Không làm task 129 |
| **144** | Kiểm thử, dữ liệu thật, replay, build và bàn giao | Chưa nghiệm thu hoặc thay bản đang dùng |

**Coder phải dừng tại các task này.** Test xanh không thay cho review. Coder không tự ghi APPROVED thay Tech Lead. Trong lúc chờ chỉ sửa finding của chặng đang review, bổ sung bằng chứng hoặc làm rõ tài liệu; không làm task tiếp theo.

Tech Lead có thể là người hoặc vai trò được người dùng chỉ định. Kế hoạch không yêu cầu một nhóm nhiều người, hệ thống review riêng hoặc tự động tạo agent.

### Hồ sơ trình tại mỗi review

Một bản ghi ngắn gồm: phạm vi task đã hoàn tất; diff/revision được review; thay đổi hành vi; ví dụ input/output hoặc ảnh khi liên quan UI; command test và kết quả; finding còn mở; quyết định cần Tech Lead chốt.

Tech Lead ghi **APPROVED** hoặc **CHANGES_REQUESTED**, kèm người/vai trò duyệt, thời điểm và revision/phạm vi đã duyệt. Finding phải chỉ rõ task chịu trách nhiệm và cách kiểm tra lại. Sửa phần ảnh hưởng quy tắc sau APPROVED thì mở lại review tương ứng.

## Danh sách công việc

### Chặng A — Khóa quy tắc và phạm vi

Chưa thay đường chạy. Chốt những quy tắc còn thiếu trước khi viết thuật toán; mỗi quyết định phải có ví dụ BUY và SELL.

| Task | File / phạm vi | Việc Coder cần làm | Đầu ra / điều kiện hoàn thành |
|---|---|---|---|
| 1 | Tài liệu / Git | Ghi revision nền và các file đang sửa dở; xác định phần thay đổi thuộc SMC. | Có baseline, không ghi đè việc khác. |
| 2 | Caller SMC | Lập bảng caller thực tế của scorer, producer và consumer: Scanner, Analyze, prefilter, replay, scenario, entry. | Mỗi caller có file/hàm, input, output và đường chạy; không suy luận từ tên module. |
| 3 | Tests hiện có | Chạy bộ test SMC/technical projection liên quan và ghi command, kết quả, lỗi nền. | Có baseline tái chạy được; không lấy con số 163 trước đây làm kết quả mới. |
| 4 | Fixture lỗi M15 | Lưu ca rejection cũ rồi 47 nến trong vùng bằng dữ liệu tổng hợp. | Tái hiện xác nhận cũ sai; ghi expected sau sửa, chưa khóa hành vi sai thành chuẩn. |
| 5 | Fixture D1 / cấu trúc | Lưu riêng ca D1 chỉ gần vùng và ca last swing khác protected swing. | Hai fixture có timeline và kết quả kỳ vọng giải thích được. |
| 6 | Đặc tả dữ liệu | Chốt cutoff, candle close time, tick size, ATR tham chiếu và cách xử lý thiếu nến. | Có bảng required/optional cho D1/H4/H1/M15, nguồn metadata và reason khi thiếu. |
| 7 | Đặc tả cấu trúc | Viết bảng chuyển trạng thái trend, BOS, protected swing, CHoCH candidate/confirmed/reclaim. | Có quy tắc bootstrap, cập nhật protected level và đồng thời nhiều break; BUY/SELL đối xứng. |
| 8 | Bảng tham số | Liệt kê và điền giá trị khởi đầu cho các ngưỡng trong phụ lục P; ghi đơn vị, lý do và điều kiện biên. | Không còn ô TBD cho ngưỡng bắt buộc; dùng dữ liệu/code hiện có làm căn cứ, không gọi là tối ưu. |
| 9 | Đặc tả vùng | Chốt điều kiện candidate/confirmed cho OB, FVG, S/D; biên gốc, entry refinement và setup chung. | Mỗi family có một ví dụ đạt, một ví dụ không đạt; thời điểm có thể sử dụng được ghi rõ. |
| 10 | Đặc tả lifecycle | Viết bảng formed/entered/exited/reacted/invalidated/expired và cách phân biệt visit. | Chốt exit tolerance, full fill FVG, penetration, open/completed visit và trigger expiry. |
| 11 | Đặc tả B/Q/L/C | Điền bảng feature -> giá trị [0,1] -> trọng số theo phụ lục F. | Đủ công thức số, mốc nội suy, missing-data policy và owner từng bằng chứng; không chỉ mô tả bằng chữ 'mạnh/yếu'. |
| 12 | Đặc tả readiness | Chốt bảng SMC state -> trạng thái consumer và trường hợp được phép xét entry. | Thiếu M15, vùng hỏng, countertrend, no-zone, thiếu core data có kết quả riêng; không bypass gate khác. |
| 13 | Đặc tả selection / plan | Chốt thứ tự xét candidate và seam giữa scorer, planner, canonical result theo phụ lục S. | Không import vòng; biết ai chọn lần cuối và cách thử candidate kế tiếp khi plan không hợp lệ. |
| 14 | Đặc tả compatibility | Chốt round-half-up một lần, component float/raw int, null/no-zone, cache identity và đọc lịch sử. | Giữ raw tối đa 15, trọng số TechnicalScore ngoài SMC; không có nhãn số thế hệ trên UI. |
| 15 | Tài liệu nghiệm thu | Ghép mapping phát hiện -> task sửa -> test; chọn danh sách command kiểm tra và nguồn snapshot. | Có checklist logic, dữ liệu thật, replay ngắn, UI và performance; không yêu cầu backtest lớn. |
| 16 | TECH LEAD REVIEW — DỪNG | Trình baseline, các bảng quy tắc/tham số/feature/readiness/selection và compatibility. | Chỉ làm task 17 khi Tech Lead ghi APPROVED cho task 16; nếu cần sửa, sửa hồ sơ rồi review lại. |

### Chặng B — Dữ liệu, swing và cấu trúc

Chỉ làm sau review task 16. Xây thuật toán và test trên nhánh làm việc; chưa thay producer production.

| Task | File / phạm vi | Việc Coder cần làm | Đầu ra / điều kiện hoàn thành |
|---|---|---|---|
| 17 | smc_models.py | Thêm model snapshot SMC và trạng thái chất lượng dữ liệu theo schema đã duyệt. | Required field được validate; metadata không bị tự chế khi thiếu. |
| 18 | Dữ liệu SMC | Tạo bộ lọc nến đóng tại cutoff dùng chung. | Nến chưa đóng bị loại theo thời gian đóng thực; không cắt mù nến cuối. |
| 19 | Dữ liệu SMC | Kiểm tra OHLC, timestamp, thứ tự và bản ghi trùng theo chính sách. | Dữ liệu sai có reason; không tự chữa OHLC sai thành tín hiệu hợp lệ. |
| 20 | History / market data | Áp dụng kiểm tra lịch phiên, warm-up và coverage cần cho lifetime. | Giờ nghỉ hợp lệ không thành missing; thiếu nguồn gốc vùng không bị coi là fresh. |
| 21 | smc_models.py | Thêm model swing có ID, pivot time và confirmed_at. | ID không phụ thuộc index rolling; swing chưa confirmed chưa usable. |
| 22 | smc_models.py | Thêm model structure event có level nguồn, hướng, thời điểm và invalidation. | Các timestamp/reference bắt buộc được kiểm tra; serialize được. |
| 23 | smc_context.py / chỉ báo | Tạo phép lấy ATR trước sự kiện theo đúng timeframe. | Formation không dùng ATR cuối snapshot hoặc ATR chứa nến sự kiện. |
| 24 | tests dữ liệu SMC | Kiểm tra cutoff, duplicate, session gap, thiếu warm-up và ATR tham chiếu. | Mỗi nhóm có dữ liệu đạt/không đạt và expected status. |
| 25 | smc_context.py | Phát hiện pivot external với confirmation delay đã chốt. | Không phát swing trước đủ nến bên phải; pivot time khác confirmed_at. |
| 26 | smc_context.py | Áp dụng cùng detector cho pivot internal với độ rộng riêng. | Không thay thuật toán chỉ để tạo tín hiệu sớm; có test pivot ít nến. |
| 27 | smc_context.py | Xử lý equal highs/lows và chuẩn hóa chuỗi swing theo thời gian. | Plateau có kết quả ổn định; không ghép high/low bằng chỉ số hai danh sách. |
| 28 | smc_context.py | Khởi tạo trạng thái cấu trúc từ swing đã xác nhận. | Dữ liệu chưa đủ trả unknown; không tự mặc định up/down. |
| 29 | smc_context.py | Tạo BOS khi close vượt mức hợp lệ với buffer. | Wick-only không BOS; boundary đúng buffer có expected rõ. |
| 30 | smc_context.py | Chặn phát lại BOS trên mức đã bị phá. | Nhiều scan/nến tiếp diễn chỉ có một event gốc cho một break. |
| 31 | smc_context.py | Cập nhật protected low/high từ swing dẫn đến BOS. | Không tự chọn last swing; lưu được BOS và swing nguồn. |
| 32 | smc_context.py | Tạo CHoCH candidate khi close phá protected level ngược hướng. | Không dùng số legs cũ làm xác nhận; fixture task 5 đạt. |
| 33 | smc_context.py | Hủy CHoCH candidate khi reclaim xảy ra trước xác nhận. | Candidate có invalidated_at và reason; không lưu cờ confirmed cũ. |
| 34 | smc_context.py | Xác nhận chuyển cấu trúc bằng HL/LH và BOS mới. | Đủ chuỗi mới confirmed; thiếu follow-through vẫn candidate. |
| 35 | smc_context.py | Áp dụng thời hạn event theo rule đã duyệt. | Event cũ vẫn có thể giữ lịch sử cấu trúc nhưng không là trigger mới; không xóa protected state vì trigger hết hạn. |
| 36 | tests cấu trúc | Kiểm tra BUY/SELL mirror, bootstrap, protected swing và wick/reclaim. | Kết quả so với expected độc lập; không chỉ sao công thức implementation. |
| 37 | tests cấu trúc | Kiểm tra batch tại cutoff trùng replay từng prefix. | Không dùng nến tương lai; so event ID, confirmed_at, state và protected level. |
| 38 | Snapshot / cache SMC | Tính dấu nhận diện input gồm candle content, cutoff, metadata và rule identity nội bộ. | Nến broker sửa làm cache miss; thêm history tương đương không tạo ID vùng mới giả. |
| 39 | tests snapshot / cache | Kiểm tra restart, cache rỗng, candle correction và rolling coverage. | Cùng dữ liệu đủ -> cùng kết quả; thiếu history -> trạng thái thiếu dữ liệu có lý do. |
| 40 | TECH LEAD REVIEW — DỪNG | Trình timeline BUY/SELL, test nhân quả, protected swing và xử lý dữ liệu. | Chỉ làm task 41 khi task 40 được APPROVED; không đưa cấu trúc chưa duyệt vào detector vùng. |

### Chặng C — Vùng, lifecycle và thanh khoản

Chỉ làm sau review task 40. Chặng này có hai điểm dừng: review detector tại task 56, review lifecycle/liquidity tại task 72.

| Task | File / phạm vi | Việc Coder cần làm | Đầu ra / điều kiện hoàn thành |
|---|---|---|---|
| 41 | smc_models.py | Thêm model zone/setup với bounds gốc, family, direction, departure và available_at. | Vùng có ID theo nguồn hình thành; original bounds không đổi khi retest. |
| 42 | smc_context.py | Tạo phép đo departure dùng chung: body/ATR, body/range, close location. | BUY/SELL đối xứng, ATR trước sự kiện; xử lý range=0 rõ ràng. |
| 43 | smc_context.py — OB | Tìm nến/base ngược chiều trước departure làm OB candidate. | Candidate chưa được dùng entry; lưu formation start/end. |
| 44 | smc_context.py — OB | Nâng OB candidate thành vùng đủ chuẩn sau break cấu trúc liên quan. | available_at không sớm hơn break xác nhận; không đòi sweep/FVG ở mọi OB. |
| 45 | smc_context.py — FVG | Tạo bounds gap ba nến và kiểm tra độ rộng tối thiểu. | Tiny gap bị loại theo tick/ATR; bullish/bearish đối xứng. |
| 46 | smc_context.py — FVG | Kiểm tra thân, close location và hướng nến giữa. | Gap có middle candle yếu không trở thành vùng đủ chuẩn. |
| 47 | smc_context.py — FVG | Phân biệt gap liên tục và gap qua giờ nghỉ phiên. | Gap phiên không tự được coi là displacement; không cần dịch vụ calendar mới. |
| 48 | smc_context.py — S/D | Tìm base nén theo số nến và độ rộng đã duyệt. | Base dùng thống kê trước departure; có reason khi quá rộng. |
| 49 | smc_context.py — S/D | Xác nhận departure đóng ra khỏi base với body/efficiency đạt chuẩn. | Nến chỉ có râu dài không đủ; formation feature không đổi theo nến tương lai. |
| 50 | smc_context.py / setup | Gán setup_id chung cho family cùng nguồn departure và cùng chiều. | Không gom chỉ vì overlap; cùng event nhiều family không thành nhiều setup. |
| 51 | smc_models.py / setup | Giữ danh sách child zone và nguồn bằng chứng của mỗi setup. | Mỗi child còn original bounds; không trộn biên thành vùng lớn giả. |
| 52 | smc_context.py | Áp dụng available_at và lifetime history cho danh sách candidate. | Vùng hình thành chưa hoàn tất không usable; thiếu lịch sử nguồn được báo. |
| 53 | smc_context.py | Bỏ cắt theo số lượng trước lifecycle; giữ giới hạn history có định nghĩa. | Top-K phục vụ output/UI; vùng mới invalid không đẩy mất vùng cũ đủ chuẩn. |
| 54 | tests detector | Kiểm tra OB không break, FVG nhỏ/yếu/session gap và S/D râu dài. | Mỗi detector có ca nhận đúng và loại đúng ở hai chiều. |
| 55 | tests zone identity | Kiểm tra thêm nến, đảo thứ tự candidate và family trùng. | ID/bounds formation giữ nguyên; setup count không tăng giả. |
| 56 | TECH LEAD REVIEW — DỪNG | Trình fixture và chart/timeline detector, available_at, grouping và giới hạn history. | Chỉ làm task 57 khi task 56 được APPROVED; Tech Lead xác nhận detector không quá dễ hoặc loại gần hết vùng. |
| 57 | smc_models.py / lifecycle | Bổ sung model visit và trạng thái open/completed/reacted. | Một visit có zone nguồn, entered/exited/reacted time và ID ổn định. |
| 58 | smc_lifecycle.py | Bắt đầu visit ở lần overlap hợp lệ sau departure hoàn tất. | Nến departure không tính retest; chạm biên có quy tắc nhất quán. |
| 59 | smc_lifecycle.py | Kết thúc visit bằng điều kiện rời vùng đã duyệt. | Rung sát biên không tạo retest giả; nhiều nến overlap vẫn một visit. |
| 60 | smc_lifecycle.py | Xác định visit phản ứng thành công theo follow-through. | Open visit hoặc chạm đơn thuần không nhận nhãn retest thành công. |
| 61 | smc_lifecycle.py | Tính penetration và thời gian liên tục trong vùng. | Phân biệt dwell hiện tại và tổng dwell; không cộng count theo số lần scanner chạy. |
| 62 | smc_lifecycle.py — FVG | Cập nhật remaining gap và full-fill state. | Fill không đổi original bounds/ID; full fill không còn điểm imbalance nguyên vẹn. |
| 63 | smc_lifecycle.py | Vô hiệu vùng bằng close ngoài distal boundary cộng buffer. | Wick được ghi penetration/sweep; không tự đổi vùng invalid thành breaker. |
| 64 | smc_lifecycle.py | Áp dụng suy giảm tuổi và expiry theo timeframe. | Tuổi suy giảm một nơi; trigger expiry riêng, vùng expired không selected. |
| 65 | tests lifecycle | Khóa departure, open visit, dwell dài, boundary jitter, fill và invalidation. | Không dùng số lần scan làm tuổi/retest; round-trip state không đổi kết quả. |
| 66 | smc_context.py — liquidity | Tạo pool từ swing confirmed/equal highs-lows theo tolerance. | Pool có nguồn/thời điểm usable; không dùng pivot chưa confirmed. |
| 67 | smc_context.py — sweep | Phát sweep khi xuyên đủ ngưỡng rồi close reclaim. | Lưu depth, reclaimed_at, source pool; wick chưa reclaim không đủ. |
| 68 | smc_sweep_linking.py | Liên kết sweep với setup hoặc visit đúng chiều/thời gian/khoảng cách. | Unrelated sweep không có điểm; nhiều child cùng setup được tham chiếu cùng evidence. |
| 69 | smc_sweep_linking.py | Đánh dấu pool/sweep consumed và khử trùng contribution. | Cùng sweep chỉ tính một lần mỗi setup, không được phát lại vô hạn. |
| 70 | smc_confluence.py | Tạo quan hệ H1/H4 parent-child và evidence D1 reaction từ lifecycle. | Proximity chỉ là metadata; reaction có visit/event còn hiệu lực và đọc cờ canonical. |
| 71 | tests liquidity / context | Kiểm tra source time, consumed, family trùng, D1 proximity và cờ legacy mâu thuẫn. | Một nguồn lifecycle quyết định; tăng metadata trùng không tăng bằng chứng. |
| 72 | TECH LEAD REVIEW — DỪNG | Trình state transition, full fill, sweep linking và D1 reaction. | Chỉ làm task 73 khi task 72 được APPROVED; mọi ca lifecycle/sweep bắt buộc đạt. |

### Chặng D — Xác nhận, điểm và chọn setup

Chỉ làm sau review task 72. Dùng bảng feature/tham số đã duyệt ở task 16; thay quy tắc ngoài bảng phải trình Tech Lead trước khi thực hiện phần phụ thuộc.

| Task | File / phạm vi | Việc Coder cần làm | Đầu ra / điều kiện hoàn thành |
|---|---|---|---|
| 73 | smc_models.py / M15 | Tạo kết quả confirmation gắn zone_id, visit_id và trigger event. | Có confirmed_at, expires_at, invalidated_at, reason; không có boolean vô nguồn. |
| 74 | smc_m15_confirmation.py | Chọn visit hiện tại hoặc visit vừa hoàn tất còn hiệu lực. | Không dò touch đầu tiên tùy ý trong 48 nến; loại event trước available_at. |
| 75 | smc_m15_confirmation.py | Xác nhận nhánh micro break kèm departure ra khỏi vùng. | HL/LH đơn lẻ hoặc break mức chưa confirmed không đạt. |
| 76 | smc_m15_confirmation.py | Xác nhận nhánh rejection tại vùng kèm follow-through. | Nến cùng màu ở xa vùng và wick không follow-through không đạt. |
| 77 | smc_m15_confirmation.py | Hủy confirmation khi visit mới, phá vùng, reclaim, timeout hoặc entry quá xa. | Hủy có reason; xác nhận cũ không sống lại khi mở app. |
| 78 | smc_m15_confirmation.py | Trả trạng thái rõ khi thiếu M15, chưa chạm và đang chờ. | Không trừ quality; thiếu M15 không cấp SMC entry confirmation. |
| 79 | tests M15 | Chuyển fixture task 4 thành regression cho expected mới. | Ca 47 nến, visit mới, xa vùng, timeout, thiếu dữ liệu đều đúng. |
| 80 | smc_scorer.py — B | Tính feature cấu trúc B theo bảng đã duyệt. | Chỉ nhận structure event hợp lệ; không cộng lại body strength hoặc alignment Trend. |
| 81 | smc_scorer.py — Q | Tính thành phần formation/departure cho từng family. | Dùng chuẩn đã duyệt và ATR formation; không thưởng chỉ vì đủ trường. |
| 82 | smc_scorer.py — Q | Tính thành phần hình học vùng theo family. | Dùng bounds đúng mục đích; không cộng proximity hiện tại vào quality. |
| 83 | smc_scorer.py — Q | Tính thành phần integrity từ lifecycle. | Dwell, visit, penetration/age theo bảng; cùng yếu tố tuổi không phạt lại ở relevance. |
| 84 | smc_scorer.py — Q | Ghép Q với tỷ lệ formation 50%, geometry 20%, integrity 30%. | Các feature ở [0,1], null khác 0; có ví dụ số tính tay. |
| 85 | smc_scorer.py — L | Tính điểm liquidity từ evidence liên quan setup. | Không có sweep trên dữ liệu đủ -> L=0; không chia lại trọng số. |
| 86 | smc_scorer.py — C | Tính điểm bối cảnh SMC từ evidence độc lập còn hiệu lực. | Không cộng alignment đơn thuần hoặc lặp event đã được tính. |
| 87 | smc_scorer.py | Ghép S=4B+7Q+2L+2C, quality_score và raw làm tròn một lần. | Raw 0..15; breakdown có contribution thật, không ép mỗi component thành số nguyên. |
| 88 | tests score | Kiểm tra các mốc nội suy và rounding bằng ví dụ tính tay. | Có zero/max/boundary/null; không dùng chính helper production để tính expected. |
| 89 | Shared zone geometry | Tách điều kiện width/distance/ordering dùng chung scorer và planner. | Một owner cho ngưỡng; không thay risk/SL/TP để làm SMC test xanh. |
| 90 | SMC readiness | Đánh giá candidate đang chờ/confirmed/invalid/conflict theo bảng. | Mâu thuẫn cấu trúc không được điểm cao cứu; gate của luận điểm áp nhất quán. |
| 91 | smc_scorer.py — selection | Sắp candidate theo confirmation group, quality, distance, H4 khi hòa và ID. | H4 không thắng tuyệt đối; permutation input cho cùng thứ tự đầu ra. |
| 92 | scanner_scenario_producers.py | Tạo hàm kiểm tra/lập plan cho một candidate chưa cần canonical result cuối. | Pure function/seam đã duyệt; không import vòng giữa result và planner. |
| 93 | Selection coordinator | Thử candidate theo thứ tự và giữ lý do plan reject. | Candidate đầu không dùng được không che candidate sau; không tính lại quality theo R:R. |
| 94 | smc_scoring_result.py | Tạo một kết quả cuối mỗi side từ candidate thực sự được chọn. | Score, selected_zone, confirmation và plan reference cùng setup; alternative chỉ giải thích. |
| 95 | smc_scoring_result.py | Áp dụng contract no-zone, no-plan và thiếu core data. | No-zone raw=0; data unavailable raw=null; watch zone không plan không READY. |
| 96 | technical_signal_scorer.py / contract | Cập nhật validator và projection để đọc quality_raw và B/Q/L/C. | Không áp cap/phạt cũ hoặc tái tạo subtotal cũ; giữ raw max và outer weights. |
| 97 | tests selection | Kiểm tra H1 thắng H4, H4 quá rộng và ứng viên kế tiếp có plan. | Selected ID, quality và scenario ID khớp; tie-break ổn định. |
| 98 | tests invariants | Kiểm tra đổi scale giá, mirror BUY/SELL, duplicate evidence và M15 độc lập quality. | Cùng setup đổi M15 không đổi quality; có thể đổi selection với reason rõ. |
| 99 | smc_validation.py | Cho replay kết quả mới theo snapshot, dùng chung evaluator và planner seam. | Replay không gọi scorer với bộ input thiếu khác live; status được suy ra, không chỉ nhận nhãn tự khai. |
| 100 | TECH LEAD REVIEW — DỪNG | Trình bảng điểm tính tay, candidate trace, confirmation và readiness matrix. | Chỉ làm task 101 khi task 100 được APPROVED; chưa nối production nếu còn sai score/plan/selection. |

### Chặng E — Nối chương trình và giao diện

Chỉ làm sau review task 100. Đổi tất cả consumer đồng bộ trên nhánh làm việc, không bật đường cũ làm fallback khi integration chưa xong. Review an toàn luồng tại task 116, review persistence/UI tại task 128.

| Task | File / phạm vi | Việc Coder cần làm | Đầu ra / điều kiện hoàn thành |
|---|---|---|---|
| 101 | workers / producer input | Nối builder snapshot chung vào nguồn dữ liệu hiện có, gồm M15 và symbol metadata. | Cùng cutoff; dữ liệu thiếu có trạng thái thật; không yêu cầu dịch vụ mới. |
| 102 | scanner_live_producers.py | Nối evaluator/coordinator chung vào Scanner. | Một lần dựng kết quả mỗi snapshot; không còn caller ngầm bỏ M15 bắt buộc. |
| 103 | analysis_pipeline.py | Dùng cùng builder/evaluator cho Analyze. | Không tự tính lại cấu trúc/vùng sau selected result; giữ cutoff/metadata. |
| 104 | smc_prefilter.py | Cập nhật prefilter để phân biệt no-setup và thiếu dữ liệu. | Không loại setup chỉ vì đang chờ M15; reuse result thay vì score lần hai. |
| 105 | scanner_features.py | Đọc raw trực tiếp từ projection mới. | Không tự chế SMC từ candle hoặc subtotal cũ; thiếu core data đúng contract. |
| 106 | technical_signal_scorer.py | Nối contribution mới vào TechnicalScore và metadata. | Giữ nguyên công thức/weights Trend, Momentum, Location; tổng rounding theo contract hiện có. |
| 107 | smc_consumer_contract.py / scenario | Chuyển consumer và scenario sang selected result/plan cùng nguồn. | Không tự dò lại vùng khác; không tạo circular dependency. |
| 108 | scanner_composition.py / candidate | Nối quality, plan và SMC readiness vào candidate/composition. | Status, selected side/zone và technical evidence khớp nhau. |
| 109 | scanner_execution_readiness.py | Áp dụng SMC readiness cùng các điều kiện execution hiện có. | Quality cao không vượt invalidation/missing confirmation; không thay rule tài khoản. |
| 110 | entry_engine.py | Rà và thay phần entry đang tự suy luận SMC/M15 trùng evaluator. | SMC trigger đọc kết quả canonical; điều kiện entry ngoài SMC còn nguyên. |
| 111 | execution_revalidation_engine.py | Tái kiểm tra selected setup với snapshot mới trước dispatch. | Vùng hết hạn/bị phá không gửi; không đổi ngầm setup rồi gửi theo phê duyệt cũ. |
| 112 | AI / đường tính cũ | Gỡ ảnh hưởng AI penalty và các cap/phép tính SMC cũ khỏi đường chạy mới. | AI diễn giải có thể giữ; không xóa AI policy/gate độc lập ngoài SMC. |
| 113 | tests consumer / composition | Cập nhật test contract và payload malformed/no-zone/data unavailable. | Không fallback score/vùng giả; sai contract có lý do và không READY. |
| 114 | tests Scanner / Analyze | So kết quả hai đường với cùng snapshot và với replay. | So raw, selected ID, lifecycle, reasons, readiness; số lần gọi evaluator đúng. |
| 115 | tests gate / scenario | Kiểm tra technical fallback, structural conflict, macro/risk/safety blocked. | Fallback không bypass luận điểm SMC invalid; không thay các gate khác để test đạt. |
| 116 | TECH LEAD REVIEW — DỪNG | Trình flow thực tế, parity và ca blocked/unknown/fallback/revalidation. | Chỉ làm task 117 khi task 116 được APPROVED; chưa cho auto-entry dùng build đang nghiệm thu. |
| 117 | services/scanner_persistence_service.py | Lưu các trường result/visit/confirmation/provenance cần đọc lại. | Round-trip không mất raw/null/reason/source; không cần database riêng. |
| 118 | Cache SMC / metadata | Cập nhật dấu tương thích cache và chứng nhận cấu hình bị ảnh hưởng. | Cache/chứng nhận cũ không tự hợp lệ với logic mới; không đổi nhãn để lách policy. |
| 119 | Persistence readers | Giữ đọc lịch sử theo ý nghĩa dữ liệu cũ. | Không biến điểm cũ thành điểm mới; không xóa journal hoặc sửa lệnh đang mở. |
| 120 | tests persistence / cache | Kiểm tra payload cũ/mới, cache miss, corrupted data và restart. | Lịch sử mở được; payload không tương thích không trở thành kết quả live hợp lệ. |
| 121 | ui/scanner_presentation.py | Hiển thị điểm, vùng, trạng thái và tối đa ba lý do. | Không gọi điểm là % thắng; format null/0 khác nhau và dễ hiểu. |
| 122 | ui/screens/scanner_detail_screen.py | Hiển thị B/Q/L/C, visit, trigger, expiry và lý do chọn vùng khi mở chi tiết. | Chỉ đọc result; không tính score hoặc dò vùng tại UI. |
| 123 | core/chart_payload.py | Thêm payload vùng active/invalid, protected swing và trigger. | ID/time/bounds khớp canonical; không dời event về trước confirmed_at. |
| 124 | ui/chart_bridge.py / chart_view.py | Render lớp SMC mới trên chart hiện có. | Vùng invalid nhạt, selected dễ nhận biết; không thêm thư viện/chart framework. |
| 125 | UI strings / docs người dùng | Bỏ nhãn số thế hệ và lựa chọn engine; thêm mô tả chờ xác nhận. | Giao diện chỉ gọi SMC; mã tương thích chỉ ở dữ liệu kỹ thuật nội bộ. |
| 126 | tests presentation / chart | Kiểm tra missing, waiting, confirmed, invalid và historical rows. | Text, status và chart source thống nhất; không lộ điểm tính cũ. |
| 127 | UI smoke cục bộ | Mở Scanner -> Detail -> Chart với fixture đủ trạng thái. | Không crash, không cần thêm cấu hình; ghi ảnh hoặc ghi nhận quan sát có thật. |
| 128 | TECH LEAD REVIEW — DỪNG | Trình persistence round-trip, ảnh UI và ví dụ người dùng đọc lý do chờ. | Chỉ làm task 129 khi task 128 được APPROVED; Tech Lead duyệt độ đơn giản và việc giữ lịch sử. |

### Chặng F — Kiểm chứng, bàn giao và đưa vào sử dụng

Chỉ làm sau review task 128. Không yêu cầu backtest tối ưu lợi nhuận hoặc đặt lệnh tiền thật. Thiếu dữ liệu/thao tác UI phải ghi BLOCKED cho task tương ứng, không tự báo đã test.

| Task | File / phạm vi | Việc Coder cần làm | Đầu ra / điều kiện hoàn thành |
|---|---|---|---|
| 129 | Golden fixtures | Cập nhật expected của các fixture có hành vi đổi đã được duyệt. | Mỗi khác biệt có lý do; giữ các invariant không thuộc SMC. |
| 130 | Regression suite | Chạy bộ test phạm vi đã chốt ở task 15. | Lưu command/kết quả; tách lỗi nền khỏi lỗi mới, không bỏ qua lỗi mới. |
| 131 | Snapshot thực tế | Thu 20–30 snapshot từ symbol thường dùng bằng nguồn có sẵn. | Có dữ liệu/cutoff và đủ nhóm tăng/giảm/range, vùng tốt/hỏng, thiếu/đủ M15; không dùng synthetic để giả dữ liệu thật. |
| 132 | QA chart thực tế | Đối chiếu các snapshot task 131 với vùng, protected swing và trạng thái. | Ghi expected/observed, nhận xét từng ca; không chỉ chụp ảnh không đánh giá. |
| 133 | Replay ngắn | Replay một số đoạn đại diện theo nến đóng từ dữ liệu thực tế. | So với batch cùng cutoff; không đọc tương lai, không cần thống kê lợi nhuận để task đạt. |
| 134 | Smoke restart / history | Quét danh sách, restart, mở lịch sử và tải lại cache. | Không mất dữ liệu; kết quả không đổi vô cớ khi input đủ và giống nhau. |
| 135 | Execution smoke không gửi lệnh | Giả lập revalidation khi vùng hỏng, quote cũ, mất M15 và setup đổi. | Mock/dry-run broker dispatch; xác minh không có lệnh thực được gửi. |
| 136 | Performance cục bộ | Đo thời gian scan p50/p95 và số lần evaluator trên cùng bộ input/máy với baseline. | So sánh được; regression vượt giới hạn task 15 phải giải quyết hoặc Tech Lead chấp thuận rõ. |
| 137 | Sửa lỗi nghiệm thu | Xử lý lần lượt lỗi mới trong nhật ký nghiệm thu; mỗi bản sửa gắn task gốc và nguyên nhân. | Không gộp thay mô hình ngoài scope; sửa rule đã duyệt phải qua review lại gate chịu ảnh hưởng. |
| 138 | Kiểm tra lại sau sửa | Chạy lại test bị ảnh hưởng và kiểm tra tích hợp tương ứng. | Không cần lặp toàn bộ suite nếu không có lý do; ghi evidence sau bản sửa cuối. |
| 139 | Tài liệu sử dụng | Viết hướng dẫn ngắn đọc score, vùng, chờ xác nhận và thiếu dữ liệu. | Không có nhãn số thế hệ hoặc cách chỉnh tham số hàng loạt. |
| 140 | Dọn đường chạy | Rà caller cũ, cap/phạt ngầm, scorer trùng và imports không còn dùng. | Chỉ một công thức live; giữ reader lịch sử nếu cần, không xóa file ngoài scope. |
| 141 | Khôi phục / chuyển đổi | Chuẩn bị build nền, bản sao cấu hình/dữ liệu liên quan và quy trình khôi phục. | Không xóa lịch sử, không chỉnh lệnh mở; xác định cache nào được làm mới. |
| 142 | Build kiểm tra cục bộ | Tạo/chạy build hoặc cách khởi động ứng dụng hiện dùng; kiểm tra import và màn hình chính. | Artifact sẵn sàng bàn giao; chưa tự thay bản đang dùng hoặc bật auto-trade trước review cuối. |
| 143 | Hồ sơ bàn giao | Tổng hợp task đã làm, review, test, snapshot QA, performance và tồn tại. | Phân biệt xác minh kỹ thuật với hiệu quả giao dịch chưa xác lập; không giấu task BLOCKED. |
| 144 | TECH LEAD REVIEW — DỪNG / NGHIỆM THU | Review hồ sơ cuối và quyết định cho phép thay bản đang dùng. | APPROVED mới hoàn tất chặng và bàn giao build; không tự bật auto-trade, không bỏ điều kiện chứng nhận execution hiện có. |

## Phụ lục P — Những thông số phải điền ở task 8

Không để việc lựa chọn ngưỡng rải rác trong lúc code. Dùng một bảng có các cột: tên, giá trị khởi đầu, đơn vị, timeframe/family, nguồn tham chiếu, phép so sánh ở biên, lý do. Tech Lead duyệt bảng tại task 16. Không thêm UI chỉnh từng ngưỡng.

| Nhóm | Nội dung phải có |
|---|---|
| Nến/ATR | ATR period và warm-up; giờ đóng theo timeframe; nguồn tick size; session gap; coverage và cách xử lý thiếu metadata |
| Swing/structure | External/internal pivot width; equal-level tolerance; break/reclaim buffer; bootstrap; BOS/CHoCH trigger lifetime |
| Departure | Body/ATR minimum; body/range; close-location; lookback trước formation; tối đa số nến chờ break cho OB |
| OB | Số nến tìm base đối màu; giới hạn base; điều kiện association với structure event |
| FVG | Gap minimum theo tick/ATR; ngưỡng middle candle; session-gap policy; full-fill tolerance |
| S/D | Số nến base; compression limit; departure efficiency; điều kiện candidate hết hạn |
| Lifecycle | Visit entry/exit tolerance; reaction follow-through; dwell penalty; penetration; age decay; lifetime theo timeframe/family |
| Liquidity | Pool tolerance; sweep excursion/reclaim; consumed policy; link distance và time window |
| D1/H4/H1 | Parent-child containment/overlap; chiều hợp lệ; D1 reaction lifetime; rule countertrend |
| M15 | Minimum data; trigger lookback sau visit; follow-through limit; expiry; tối đa khoảng chạy khỏi entry |
| Geometry | Min/max width, hard distance, ATR nguồn; vùng protective và vùng refined dùng ở đâu |
| Output/performance | Top-K hiển thị/alternative; history đủ lifetime; độ chính xác số; mục tiêu thời gian scan trên máy cá nhân |

Ưu tiên tái sử dụng tham số hiện có nếu đúng nghĩa mới, ghi rõ trường hợp thay. Các giá trị là quy ước triển khai, không trình bày như ngưỡng giao dịch đã tối ưu. Task 16 không được APPROVED nếu còn thiếu giá trị bắt buộc hoặc thiếu cách xử lý biên.

## Phụ lục F — Bảng công thức phải hoàn chỉnh ở task 11

Công thức tổng giữ như thiết kế:

```text
S = 4*B + 7*Q + 2*L + 2*C
Q = 0.50*formation + 0.20*geometry + 0.30*integrity
quality_score = 100*S/15
quality_raw = round_half_up(S)
```

B/Q/L/C và feature con thuộc [0,1]. Chốt bảng cụ thể trước implementation:

- Với B: state/event nào có điểm nào; event nào chỉ là bằng chứng lịch sử; phân biệt structure bias và trigger còn hiệu lực.
- Với formation: đầu vào, phép chuẩn hóa và cách ghép body/ATR, body/range, close location, base/gap theo family.
- Với geometry: các mốc rộng/hẹp theo ATR và family; biên gốc hay remaining bounds; không thưởng khoảng cách tới giá.
- Với integrity: công thức visit, dwell, penetration, age; trình tự ghép và chặn [0,1]; quy tắc full fill riêng FVG.
- Với L: pool/sweep/reclaim nào đóng góp, độ sâu/chất lượng dùng ra sao; event nào bị loại do thời gian/khoảng cách.
- Với C: parent-child/reaction nào đủ nghĩa; loại bằng chứng trùng với B/Q/L và alignment đã thuộc Trend.
- Mỗi feature cần nguồn input, mốc nội suy hoặc bảng mapping, expected tại biên, absence và missing-data policy.
- Không tự chuẩn hóa lại phần còn lại khi thiếu một feature. Feature optional đã đánh giá đủ mà không có evidence có thể bằng 0; thiếu dữ liệu bắt buộc phải có trạng thái riêng.
- Giữ component contribution dưới dạng số có phần thập phân; raw nguyên được làm tròn một lần. Validator hiện tại phải thay tương ứng, không ép mỗi contribution nguyên rồi cộng.

Có tối thiểu ví dụ tính tay: no-zone, quality thấp/cao, đúng điểm làm tròn, no-sweep, thiếu core data, thiếu M15 và family trùng. Không coi các giá trị này là xác suất thắng.

## Phụ lục S — Chốt quyền chọn vùng ở task 13

Hiện tại scorer trả selected zone trước khi scenario producer xét plan. Thiết kế mới cần thử candidate kế tiếp khi candidate đầu không tạo được plan. Nếu không phân quyền rõ sẽ tạo vòng phụ thuộc hoặc score không khớp plan.

Seam đề xuất cần Tech Lead chốt:

```text
build_snapshot
  -> evaluate_candidates (quality + geometry + per-candidate confirmation)
  -> order_candidates
  -> coordinator gọi pure plan_for_candidate theo thứ tự
  -> finalize_canonical_result cho selected candidate
  -> consumer đọc result/plan, không chọn lại
```

- Hàm plan cho một candidate nhận zone và technical context trực tiếp, không đòi canonical result cuối.
- Coordinator không gọi network, UI hoặc broker; không gọi scorer lần nữa để đổi thứ tự theo R:R.
- Điều kiện plan dùng rule đã có; không chỉnh SL/TP hoặc risk floor để candidate đạt.
- Không có plan nhưng còn vùng theo dõi: selected watch zone có quality và `plan_available=false`; không READY.
- Core data không hợp lệ: result có trạng thái thiếu dữ liệu; không giả lập no-zone đã đánh giá đầy đủ.
- Market/account gate chặn toàn luận điểm thì không thử vùng khác để lách gate.
- Technical fallback giữ source riêng. Chốt trường hợp nào thực sự là luận điểm technical độc lập và trường hợp nào là bypass SMC bị cấm.
- Kết quả cuối có selected ID, quality, lifecycle, confirmation và plan reference cùng candidate. UI, projection, persistence chỉ đọc kết quả này.
- Trong lúc chuyển đổi, mọi caller phải được cập nhật theo inventory task 2; không để adapter cũ âm thầm chọn lại.

## Phụ lục kiểm tra — mức hoàn thiện cho phần mềm cá nhân

**Bắt buộc:** test logic liên quan; parity tại cùng cutoff; 20–30 snapshot dữ liệu thật; replay ngắn; UI/scan/restart smoke; execution dry-run; đo performance đơn giản; đọc lịch sử và kiểm tra khôi phục.

**Không bắt buộc:** backtest quy mô lớn, tối ưu lợi nhuận, ML, order-flow thật, dashboard nghiên cứu, giao dịch tiền thật. Không bỏ kiểm tra dữ liệu thực bằng cách gọi toàn bộ synthetic fixture là test thực tế.

Mức chấp nhận performance và nguồn snapshot phải được ghi ở task 15, duyệt task 16. Thiếu dữ liệu không tự trở thành APPROVED. Nếu cần thu hẹp một bước nghiệm thu, Tech Lead phải ghi rõ ngoại lệ và giới hạn; Coder không tự bỏ bước.

Nghiệm thu chỉ hoàn tất khi các task bắt buộc DONE, finding chặn đã sửa, các review được duyệt và artifact cuối đã smoke test. Không tuyên bố cải thiện win rate/lợi nhuận chỉ từ các kiểm tra kỹ thuật.
