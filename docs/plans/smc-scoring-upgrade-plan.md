# SMC: đề xuất nâng cấp cho phần mềm cá nhân

Ngày thiết kế: 2026-09-10. Cập nhật trạng thái: 2026-09-16. Gate 16/40/56/72/**100/116/128** đã APPROVED; task 57–72 hoàn tất; **task 73–79 và 80–91 REVIEW PASS**; **task 92–99 đã APPROVED tại gate task 100**; **task 101–111 REVIEW PASS**; **task 112–115 IMPLEMENTED → task116 APPROVED (2026-09-15)**; **task 117–120 (persistence/cache/đọc lịch sử) REVIEW PASS**; **task121–128 REVIEW PASS → Task128 APPROVED (2026-09-16)**. Trạng thái hiện hành đọc tại [nhật ký tiến độ](smc-implementation-progress.md). Chưa rollout production/auto-entry.

Theo [nhật ký tiến độ](smc-implementation-progress.md), gate 16/40/56/72 đã APPROVED và task 57–72 hoàn tất. Đã có thay đổi mã SMC; chưa hoàn tất tích hợp và nghiệm thu toàn bộ nâng cấp. Trạng thái này thay các ghi chú cũ “chưa sửa runtime”.

**Dành cho Coder:** thực hiện theo [checklist triển khai SMC](smc-implementation-plan.md), gồm 144 task đánh số liên tục và 8 mốc Tech Lead review bắt buộc. Tài liệu này giải thích thiết kế; checklist quy định thứ tự làm và điểm dừng.

## 1. Mục tiêu và giới hạn

Nâng cấp triệt để định nghĩa cấu trúc, vùng, xác nhận và cách ghép vào Scanner; giữ cách sử dụng đơn giản. Chỉ gọi là SMC, dùng một công thức mặc định, không gắn số thế hệ hoặc cho chọn engine, không yêu cầu người dùng chỉnh hàng chục ngưỡng. Tận dụng dataclass, pipeline, cache, JSON persistence và UI hiện có. Không bổ sung dịch vụ nền, cơ sở dữ liệu riêng, ML hoặc AI vào đường quyết định SMC.

Hoàn thiện nghĩa là: tính đúng theo quy tắc đã công bố, không dùng dữ liệu chưa biết, các màn hình thống nhất, trạng thái giao dịch rõ, lỗi có giải thích và có kiểm thử. Không đồng nghĩa cam kết lợi nhuận hoặc gọi các trọng số đề xuất là tối ưu.

Phạm vi ngoài SMC chỉ gồm cập nhật adapter, validator, scenario, readiness, chart và persistence cần thiết để dùng cùng kết quả. Giữ bốn thành phần TechnicalScore và trọng số regime bên ngoài. Không thay công thức Trend/Momentum/Location hoặc cách quản lý vốn để phục vụ SMC.

### 1.1. Mục tiêu sử dụng để người dùng xem xét

Bản nâng cấp cần giúp người dùng mở Scanner, chọn một symbol và hiểu được: có setup SMC nào đáng theo dõi, vùng giá nào là mốc, bằng chứng còn hiệu lực không, và cần chờ điều kiện gì tiếp theo. Điểm số, vùng giá và trạng thái trên màn hình phải cùng giải thích một setup.

Các đầu ra có thể kiểm tra khi nghiệm thu:

| Người dùng cần biết | Đầu ra mong đợi | Cách nhận biết đã đạt |
|---|---|---|
| Có setup nào đáng theo dõi? | Vùng được chọn mỗi chiều, timeframe, family và chất lượng | Có lý do chọn; không để vùng hỏng hoặc không dùng được che mất ứng viên hợp lệ |
| Vì sao setup có giá trị? | Tối đa ba lý do chính; chi tiết mở khi cần | Lý do dựa trên dữ liệu/sự kiện thực, không cộng trùng một bằng chứng |
| Bây giờ cần làm gì? | Chờ giá, chờ xác nhận, đủ xác nhận, vô hiệu hoặc thiếu dữ liệu | Xác nhận cũ, vùng bị phá và thiếu dữ liệu không hiện như setup sẵn sàng |
| Có thể đối chiếu trên chart không? | Vùng và sự kiện của chính kết quả đã chọn | Scanner, Detail và Chart khớp nguồn, thời điểm và trạng thái |
| Có dễ dùng và bảo trì không? | Một cách tính mặc định, dùng hạ tầng hiện có | Không cần chỉnh hàng chục tham số; phần chi tiết không lấn màn hình chính |

Điểm chất lượng vẫn được thiết kế trên thang 0–15. Quyền vào lệnh tổng còn phụ thuộc các điều kiện hiện có của ứng dụng. Trọng số và hiệu quả giao dịch chưa được chứng minh tối ưu; hoàn thành kỹ thuật được đánh giá bằng hành vi đúng, dữ liệu thực tế, replay và khả năng sử dụng như §12–14.

### 1.2. Giới hạn đơn giản hóa và lựa chọn phạm vi

“Dùng cá nhân” xác định mức đầu tư và cách sử dụng, không tự quyết định bỏ timeframe, loại vùng hoặc thay phương pháp giao dịch. Các gợi ý trước đó như chỉ dùng H1, bỏ S/D, bỏ B/Q/L/C hoặc đổi sang ba trạng thái M15 chưa được người dùng chọn và **chưa thay thế thiết kế** trong tài liệu này.

| Phần cần cân nhắc | Đề xuất để xem xét | Điều kiện trước khi thay đổi |
|---|---|---|
| Tài liệu và quy trình | Dùng kế hoạch này cho mục tiêu, checklist cho phạm vi công việc, progress cho trạng thái; dẫn tới spec/review khi cần | Không yêu cầu đọc toàn bộ lịch sử review để nắm tiến độ; báo cáo cũ vẫn giữ bằng chứng quyết định |
| Dữ liệu và tín hiệu | Giữ nến đóng, thời điểm xác nhận, hủy xác nhận cũ, vùng hỏng và missing-data rõ ràng | Đây là điều kiện để đầu ra đúng và hiểu được |
| D1/H4/H1/M15; OB/FVG/S-D; B/Q/L/C | Giữ làm phương án đầy đủ đang có | Chỉ cắt sau khi chốt người dùng thực sự cần những tín hiệu nào; cập nhật công thức và consumer liên quan đồng bộ |
| Sweep ownership, consumed history, D1 reaction | Đánh giá riêng chi phí/lợi ích nếu thu gọn chức năng | Nếu vẫn sử dụng bằng chứng này để tính điểm/xác nhận thì phải sửa lỗi nguồn gốc, tính trùng và hết hiệu lực tương ứng |
| UI chi tiết, giải thích alternative, tối ưu cache | Có thể xem xét lùi phần phục vụ chẩn đoán hoặc tối ưu chưa cần thiết | Vẫn phải thể hiện đúng vùng/trạng thái; restart hoặc dữ liệu cũ không tạo kết quả hợp lệ giả |
| Kiểm chứng | Tập trung ca lỗi đã biết, chuỗi xử lý được giữ lại, snapshot thật và smoke test | Không lấy số lượng task/tests làm thước đo hoàn thành; consumer còn sử dụng phải thống nhất kết quả |

Ba hướng để người dùng quyết định sau khi đọc bản mục tiêu này:

1. **Giữ phạm vi SMC đầy đủ, gọn cách quản lý:** dùng lại thiết kế/đặc tả và mã đã làm; sửa gate 72 rồi tiếp tục phạm vi còn lại. Giảm tài liệu lặp và thao tác review hành chính; các điều kiện nghiệm thu kỹ thuật vẫn còn.
2. **Thu gọn chức năng:** chốt rõ timeframe, family, bằng chứng và đầu ra còn cần, rồi lập mapping giữ/sửa/hoãn cho task và mã hiện có. Chưa có đủ căn cứ để gọi hướng này là ít công hơn: mã đã liên kết với nhau, cần đánh giá tác động trước.
3. **Dừng nâng cấp:** giữ hồ sơ và thay đổi đang có để tham khảo; quyết định riêng việc xử lý mã dở dang trước khi dùng một build ổn định. Dừng kế hoạch không đồng nghĩa mã đã tự quay về bản cũ.

Khuyến nghị hiện tại là hoàn thiện cách đọc tài liệu và mục tiêu trước, sau đó chọn một trong ba hướng. Chưa ấn định số task mới hoặc thời gian hoàn thành khi phạm vi chưa chốt. §2–14 và checklist 144 task tiếp tục mô tả phương án đầy đủ để đối chiếu; không phải lệnh tiếp tục triển khai trong giai đoạn xem xét này.

## 2. Phát hiện hiện tại: phân biệt lỗi với lựa chọn thiết kế

| Mục | Bằng chứng trong mã | Phân loại và xử lý |
|---|---|---|
| M15 giữ xác nhận cũ | `smc_m15_confirmation.py` chọn touch đầu tiên trong 48 nến, chấp nhận rejection cũ | Sửa: xác nhận theo visit hiện tại, hết hạn và bị hủy khi có diễn biến bất lợi |
| M15 gọi HL/LH là CHoCH | `_m15_choch` chỉ so hai đáy/đỉnh | Sửa ngữ nghĩa: phải có break một mức cấu trúc đã xác nhận |
| D1 reaction chỉ kiểm tra khoảng cách | `_d1_zone_reaction_bonus` không nhận nến phản ứng | Sửa: tách proximity và reaction; chỉ reaction được coi là xác nhận |
| D1 đọc lifecycle cũ | Bonus đọc `broken/mitigated`, trong khi `enrich_zones` có cả cờ legacy và canonical | Sửa: một nguồn lifecycle cho mọi consumer |
| CHoCH dùng prev_low/prev_high | `detect_bos_choch` bỏ qua break last_low/last_high | Thiếu định nghĩa protected swing; không sửa máy móc thành last swing. Chuyển sang protected swing có nguồn gốc |
| Confirmed CHoCH dựa vào 3 legs trước đó | `choch_confirmed = choch and leg_count >= 3` | Thay quy tắc xác nhận: bằng chứng sau break, không phải độ dài xu hướng cũ |
| Ưu tiên tuyệt đối H4 | `select_smc_zone` loại H1 khỏi cuộc chọn nếu có H4 hợp lệ | Lựa chọn thiết kế cần thay: H4 làm bối cảnh, chất lượng quyết định vùng |
| Cắt ứng viên quá sớm | Detector giữ 6 OB/FVG và 5 S/D trước lifecycle | Hạn chế thuật toán: xét lifecycle và tính hợp lệ trước khi lấy top-K |
| Ngưỡng lịch sử phụ thuộc hiện tại | Filter swing dùng ATR cuối; S/D dùng average range 50 nến cuối | Sửa tính ổn định: tiêu chuẩn tại thời điểm hình thành; không kết luận toàn bộ backtest đang lookahead khi chưa kiểm tra caller |
| Scanner thiếu tham số | `derive_live_analysis` gọi scorer không có regime/M15; analysis pipeline có regime/M15 | Thống nhất hợp đồng input; loại regime khỏi điểm chất lượng nếu đã do lớp ngoài sở hữu |
| Scanner chiếu subtotal | `project_smc_technical_raw` chủ ý trả subtotal trước cap/phạt | Không phải lỗi số học. Thiết kế mới dùng quality + readiness rõ ràng, bỏ mô hình vừa cap vừa bỏ cap khi projection |
| Scorer chọn vùng mà planner không dùng được | Scorer không có width gate, scenario producer có width gate 1 ATR | Dùng chung điều kiện hình học; không để vùng không tạo được plan che mất ứng viên hợp lệ khác |

Rà soát công thức hiện tại trước đề xuất: 163 kiểm thử liên quan đạt. Ba probe đã xác minh: close 95 giữa hai HL 90/100 chưa CHoCH; rejection M15 cũ vẫn confirmed sau 47 nến đi ngang trong vùng; D1 proximity có thể được cộng reaction bonus không cần nến phản ứng. Đây là baseline để viết kiểm thử hành vi mới, không phải bằng chứng hiệu quả giao dịch.

## 3. Luồng đích

```text
Nến đã đóng tại cutoff + metadata symbol
  -> swing và sự kiện cấu trúc theo từng timeframe
  -> OB/FVG/Supply-Demand và vòng đời
  -> ghép các biểu diễn cùng một setup
  -> đánh giá chất lượng từng setup
  -> chọn vùng và kiểm tra visit/xác nhận
  -> một kết quả SMC canonical cho BUY và SELL
  -> TechnicalScore / Scenario / Readiness / UI
```

Chỉ chấm một lần cho cùng snapshot; consumer không tự dò vùng hoặc diễn giải lại CHoCH. Execution revalidation được phép cập nhật ở cutoff mới trước gửi lệnh, phải ghi thời điểm và nguồn dữ liệu của kết quả mới.

Ba thông tin độc lập:

- `quality_raw` 0–15: chất lượng bằng chứng của setup cụ thể, không phải xác suất thắng.
- `selected_zone`: vùng làm mốc với lý do chọn, biên, nguồn và thời điểm.
- `readiness`: vùng có thể được xem xét vào lệnh lúc này không; gồm lý do đang chờ/bị chặn.

SMC readiness là đầu vào của quyền giao dịch tổng. MarketSafety, Macro, Risk và các gate hiện có vẫn phải cho phép thì mới READY_NOW.

## 4. Dữ liệu và tính nhân quả

1. Mỗi snapshot có `as_of`, symbol, tick size, timeframe, thời gian đóng nến. D1/H4/H1/M15 dùng cùng cutoff và nến đã đóng. Giá tick dùng cho khoảng cách/revalidation, không thay close xác nhận cấu trúc.
2. Mỗi swing có thời điểm pivot và `confirmed_at`; fractal phải chờ đủ nến bên phải. Không backdate sự kiện về pivot để vào lệnh sớm.
3. ATR của tín hiệu hình thành lấy từ nến trước sự kiện trên chính timeframe đó; lưu giá trị tham chiếu. Khoảng cách hiện tại dùng ATR hiện tại nhưng không sửa đặc tính hình thành.
4. Kiểm tra OHLC, timestamp, dữ liệu trùng, gap thực và giờ nghỉ phiên; không coi cuối tuần là lỗi mất dữ liệu. Nến sửa từ broker phải làm mất hiệu lực cache và replay phần bị ảnh hưởng.
5. Không có tín hiệu trên dữ liệu đầy đủ khác với không đủ dữ liệu. Trường hợp sau trả trạng thái thiếu dữ liệu; không tự điền score tốt hoặc đổi mẫu số.
6. ID sự kiện/vùng dựa timestamp, symbol, timeframe và nguồn gốc; không dựa index tương đối của rolling window. Bounds hình thành bất biến; remaining FVG bounds có trường riêng.
7. Cần history đủ để tái dựng vùng còn hoạt động. Nếu history bị cắt mất nguồn gốc thì đánh dấu không đủ dữ liệu, không làm vùng cũ trở thành fresh. Cache là tối ưu, không được là điều kiện ngầm khiến replay sai.

## 5. Cấu trúc và BOS/CHoCH

Giữ hai cấp cấu trúc external/internal với cùng thuật toán, khác độ rộng pivot. Bản đầu dùng bộ thông số cố định; không triển khai ZigZag repaint hay tự tối ưu theo từng symbol.

- Swing high/low có xác nhận, thứ tự thời gian, và xử lý equal highs/lows bằng tolerance theo tick/ATR. Không ghép các đỉnh/đáy chỉ theo vị trí trong hai danh sách độc lập.
- BOS tăng là close phá swing high được theo dõi, có buffer và theo hướng cấu trúc trước đó; chiều giảm đối xứng. Mỗi mức chỉ phát sự kiện break một lần.
- Protected low là đáy hợp lệ dẫn đến BOS tăng gần nhất; protected high đối xứng. Chỉ cập nhật sau khi chuỗi sự kiện xác nhận được, không đổi tùy theo hai pivot cuối.
- Close phá protected swing ngược chiều tạo CHoCH candidate. Xác nhận chuyển cấu trúc cần follow-through: hình thành HL/LH và BOS theo hướng mới. Reclaim trước xác nhận hủy candidate.
- Không coi wick vượt mức là BOS/CHoCH. Wick xuyên rồi close trở lại được đánh giá ở sweep.
- Event có `occurred_at`, `confirmed_at`, `broken_level_id`, `direction`, `expires_at`, `invalidated_at`. Không tái sử dụng BOS cũ như trigger mới trên mỗi lần scan.
- M15 có thể xác nhận entry bằng micro break + displacement/reaction tại visit; không bắt buộc chờ hoàn chỉnh cả chuỗi đảo chiều external H4.

Buffer break xuất phát từ tick size và ATR, cấu hình tập trung. Độ mạnh displacement được chấm ở chất lượng vùng, không cộng lại ở structure chỉ vì cùng một nến dài.

## 6. OB, FVG và Supply/Demand

### Order Block

Tìm nến/base ngược chiều ngay trước departure có ý nghĩa. Candidate chỉ thành vùng đủ chuẩn sau displacement và break cấu trúc liên quan. FVG hoặc sweep là bằng chứng bổ sung, không bắt buộc mọi setup đều có.

Giữ biên đầy đủ để vô hiệu hóa/SL; nếu có entry refinement thì lưu riêng. Không thu hẹp biên rủi ro bằng cách bỏ wick chỉ để R:R đẹp hơn. Phân biệt OB mới, OB đã retest và vùng bị phá. Breaker/inverse FVG là mở rộng sau, không tự chuyển vùng hỏng sang chiều đối diện trong bản đầu.

### FVG

Giữ mô hình ba nến nhưng thêm gap tối thiểu theo tick/ATR, body/range và close location của nến giữa, cùng hướng departure. Loại gap quá nhỏ; nhận diện gap do phiên để không tự coi là displacement.

Lưu `original_bounds`, phần gap còn lại, fill ratio và trạng thái. Một FVG lấp kín không còn là imbalance nguyên vẹn, dù vùng OB bao quanh có thể còn giá trị. Không dùng nguyên một luật mitigation cho mọi family.

### Supply/Demand

Base phải có độ nén hợp lý và departure đóng ra ngoài base. So impulse với thống kê cục bộ trước hình thành; đo body và hiệu quả thoát base, không chỉ high-low. Giữ số lựa chọn base nhỏ như hiện tại để dễ bảo trì.

### Loại trùng và giới hạn ứng viên

OB/FVG/S-D cùng displacement có chung `setup_id`. Giữ bằng chứng con nhưng không cộng ba lần vì ba tên. Không gộp mọi vùng chồng lấn: cần cùng nguồn departure và cùng chiều.

Scan trong history có giới hạn xác định -> phát hiện -> lifecycle -> loại invalid -> nhóm setup -> xếp chất lượng -> top-K cho UI. Cửa sổ detector phải bao phủ lifetime tối đa; top-K hiển thị không quyết định sự tồn tại của vùng. Các giới hạn tài nguyên có reason khi cắt dữ liệu.

## 7. Vòng đời và xác nhận theo visit

Vòng đời gồm các sự kiện `formed`, `entered`, `exited`, `reacted`, `invalidated`, `expired`. State hiển thị có thể rút gọn fresh/testing/tested/degraded/invalid/expired. Visit đang mở và visit đã hoàn tất là hai trạng thái khác nhau.

- Một visit bắt đầu khi nến overlap sau departure đã đóng; kết thúc khi giá rời vùng đủ rõ theo tolerance. Rung một tick ngoài biên không tạo nhiều retest.
- Chạm vùng không được thưởng như retest thành công. Retest thành công cần close/di chuyển ra khỏi vùng theo hướng kỳ vọng.
- Độ suy giảm dùng số visit hoàn tất, penetration, thời gian liên tục trong vùng và tuổi theo timeframe. Không phạt cùng tuổi ở quality rồi phạt lại ở relevance.
- Wick xuyên biên là dữ kiện sweep/penetration. Invalidation cấu trúc dùng close ngoài distal boundary và buffer; execution stop thực tế vẫn do risk/broker quản lý.
- Chỉ visit hiện tại hoặc visit vừa hoàn tất còn hiệu lực được xác nhận entry. Confirmation gắn `zone_id + visit_id + event_id`; không tìm bất kỳ rejection nào trong 12 giờ.
- Confirmation hết hiệu lực khi có visit mới, close phá vùng, reclaim ngược, timeout hoặc giá đã chạy quá xa khỏi entry. Timeout của trigger khác với lifetime của vùng.

M15 chỉ phục vụ readiness. Confirm khi có micro break mức đã xác nhận và displacement ra khỏi vùng, hoặc rejection tại vùng kèm follow-through đóng ra ngoài theo hướng kỳ vọng. HL/LH đơn lẻ và nến cùng màu ở xa vùng không đủ.

Thiếu M15: vẫn hiển thị setup và quality; không READY_NOW cho entry cần M15. Chưa chạm: WATCH_ZONE; đang chạm/chờ phản ứng: WAITING_CONFIRMATION. Không tạo tùy chọn âm thầm bỏ xác nhận để tăng số lệnh.

## 8. Liquidity và bối cảnh đa khung

Liquidity pool từ swing đã xác nhận/equal highs-lows trong tolerance. Sweep phải xuyên mức đủ đáng kể rồi close reclaim; lưu nguồn pool, độ xuyên, reclaim time và hướng. Không dùng tick volume để khẳng định có lệnh tổ chức; OHLC chỉ cung cấp bằng chứng mẫu hình.

Sweep liên kết đúng setup hoặc visit, có giới hạn khoảng cách/thời gian. Một sweep đóng góp tối đa một lần trong một setup; bằng chứng có thể được tham chiếu bởi nhiều child zone cùng setup mà không mất điểm vì ID sắp xếp trước. Sweep đã consumed không tiếp tục là pool mới vô hạn.

D1 là bối cảnh; H4/H1 là ứng viên vùng; M15 là xác nhận. H4 không mặc định thắng H1. Child H1 được refine trong H4 nếu có vùng thật và cùng luận điểm. H1 đứng riêng cần chất lượng đủ chuẩn; khi ngược H4 external chưa đảo chiều xác nhận thì chỉ theo dõi.

D1 proximity chỉ là nhãn vị trí. D1 reaction cần visit/phản ứng sau formation, có hiệu lực và dùng lifecycle canonical. Không cộng bonus vì giá đang cách vùng 0,5 ATR. Alignment trend đơn giản thuộc Trend; vị trí premium/discount thuộc Location, không thưởng lại trong SMC.

## 9. Công thức đề xuất

Giữ output SMC raw 0–15. Thay các thành phần bên trong; cập nhật đồng bộ kiểm tra hợp lệ và đọc/ghi dữ liệu. Công thức dưới đây là bộ khởi đầu để kiểm tra, chưa phải trọng số đã được chứng minh tối ưu.

```text
B, Q, L, C thuộc [0, 1]
S = 4*B + 7*Q + 2*L + 2*C
quality_raw = round_half_up(S)     # đúng một lần, 0..15
quality_score = 100*S/15           # độ phân giải đầy đủ để chọn vùng
```

| Biến | Sở hữu bằng chứng | Không nhận thêm điểm vì |
|---|---|---|
| B: cấu trúc | Break đúng đối tượng, chuỗi continuation/reversal hợp lệ và còn hiệu lực | Nến dài đã chấm ở Q; alignment đã thuộc Trend |
| Q: vùng | Chất lượng departure/base hoặc gap, hình học, mức nguyên vẹn sau retest | Trường dữ liệu tồn tại; giá hiện tại gần vùng |
| L: thanh khoản | Pool/sweep/reclaim liên quan setup có nguồn gốc | Sweep chung của cả timeframe không liên quan |
| C: bối cảnh SMC | Quan hệ parent/child có ý nghĩa hoặc phản ứng HTF độc lập còn hiệu lực | Ba khung chỉ cùng HH/HL; cùng một event đã được tính |

Q khởi đầu gồm 50% formation/departure, 20% hình học theo family, 30% integrity/lifecycle. Giữ feature ở [0,1], nội suy liên tục với các mốc tập trung thay vì nhiều bậc nhảy. Detector có điều kiện bắt buộc; vượt điều kiện tối thiểu không tự nhận điểm tối đa.

Chưa có vùng hợp lệ: quality_raw = 0, selected_zone = null, lý do NO_VALID_SETUP. Dữ liệu core thiếu/hỏng: quality_raw = null, trạng thái DATA_UNAVAILABLE. Không có sweep sau khi đã đánh giá đủ dữ liệu: L=0; không tăng lại trọng số B/Q/C. Dữ liệu thiếu để tính feature bắt buộc không được coi là feature bằng 0 đã đánh giá.

Không dùng M15, AI, spread, R:R, macro, risk hoặc khoảng cách tới giá để tăng/giảm S. Distance/width vẫn được dùng cho eligibility và tie-break có giải thích. Thay selected setup có thể đổi raw; nhưng thay M15 không đổi quality của cùng một setup.

Bỏ technical validation +0..2 cũ và premium/discount trong Q để tránh trùng Location. Bỏ thưởng mặc định 20 điểm pattern validity. Bỏ trừ điểm AI/M15 và cap 4/8 khỏi raw; thay bằng readiness/state phù hợp. Không chỉ xóa cap mà bỏ quên gate bảo vệ.

## 10. Chọn vùng và nối scenario/readiness

1. Loại dữ liệu sai, vùng invalid/expired, sai chiều và hình học không đạt điều kiện chung với planner.
2. Kiểm tra mâu thuẫn cấu trúc: continuation ngược external break đã xác nhận không được READY. Setup đảo chiều cần chuỗi reversal riêng, không dùng nhãn countertrend để bỏ qua điều kiện.
3. Trong ứng viên còn lại, ưu tiên nhóm có confirmation hiện tại; nếu chưa có thì chọn vùng theo dõi tốt nhất. Trong mỗi nhóm xếp quality_score, sau đó distance, timeframe H4 khi thực sự hòa điểm, rồi ID ổn định.
4. Xây plan từ ứng viên theo thứ tự bằng cùng planner; nếu ứng viên đầu không có plan hình học hợp lệ thì thử ứng viên kế tiếp, ghi rejection reason. R:R và risk không được cộng vào SMC quality. Không đổi vùng để lách market/account gate.
5. Lưu một selected setup mỗi side. Có thể lưu tối đa 2–3 alternative cho giải thích; UI mặc định chỉ hiện selected.
6. Khi không có plan, vẫn có thể giữ watch zone nhưng phải ghi `plan_available=false`. Technical fallback hiện có phải giữ nguồn technical, không giả làm SMC; không dùng fallback để bypass structural invalidation của luận điểm SMC.

Không dùng hysteresis trong bản đầu để tránh phụ thuộc lần scan trước. Tie-break ổn định và gap chất lượng phải hiển thị nếu cần chẩn đoán việc đổi vùng. Nếu sau sử dụng thực tế cần hysteresis thì bổ sung kèm snapshot state/replay contract riêng.

## 11. Giao diện cá nhân

Mặc định chỉ hiển thị:

- Điểm: SMC 11/15 — chất lượng setup, không phải % thắng.
- Vùng: BUY, H1 OB trong H4 demand; khoảng giá.
- Trạng thái: chờ giá/chờ xác nhận/đủ xác nhận/vô hiệu/thiếu dữ liệu.
- Tối đa ba lý do dễ đọc và điều kiện kế tiếp: ví dụ “Đang test lần 1; chờ M15 đóng vượt 1.0842”.

Mở Chi tiết mới thấy B/Q/L/C, timeline, sweep liên quan, lý do loại vùng khác và thời điểm hết hạn. Chart thể hiện vùng active, vùng vô hiệu nhạt, swing bảo vệ và trigger. Không hiển thị mã kỹ thuật trừ phần chẩn đoán.

Không có màn hình chỉnh trọng số/ATR/pivot. Thông số nằm trong một cấu hình nội bộ, dùng mặc định. AI có thể diễn giải bằng chứng sẵn có theo yêu cầu, không là phụ thuộc bắt buộc hoặc quyền tự sửa score.

## 12. Kiểm chứng vừa đủ nhưng có chiều sâu

### Kiểm thử logic bắt buộc

| Nhóm | Ca cần khóa |
|---|---|
| Nhân quả | Nến chưa đóng không đổi tín hiệu; pivot chưa confirmed không được dùng; prefix replay trùng batch tại cùng cutoff |
| Cấu trúc | Protected swing khác swing mới nhất; BOS chỉ phát một lần; wick-only không BOS; break/reclaim; reversal đủ/thiếu follow-through |
| Vùng | Tiny FVG; middle candle yếu; OB không break; S/D râu dài; candidates mới invalid không che vùng tốt |
| Lifecycle | Departure không là retest; open visit không là retest thành công; 47 nến nằm trong vùng không giữ xác nhận cũ; touch/rời sát biên không tăng count giả |
| FVG | Partial/full fill; remaining bounds không đổi ID hoặc original SL geometry |
| Sweep | Trước source confirmation; pool consumed; một impulse nhiều family không tăng điểm giả; unrelated sweep không xác nhận entry |
| M15 | Xác nhận trước formation; visit cũ; trigger hết hạn; body cùng màu nhưng ở xa; missing M15 không READY |
| D1 | Proximity không reaction; legacy/canonical flags mâu thuẫn; phản ứng cũ không còn hiệu lực |
| Selection | H1 tốt hơn H4; H4 width reject; ứng viên đầu không có plan nhưng ứng viên sau có; cùng input khác thứ tự vẫn cùng kết quả |
| Hợp đồng | Scanner/Analyze/Replay cùng snapshot giống nhau; raw và breakdown khớp; UI không đổi source; cap cũ không tồn tại ngầm |
| Tính chất | BUY/SELL đối xứng khi đảo giá hợp lệ; scale giá/tick/ATR tương ứng giữ kết quả; thiếu dữ liệu không tăng điểm; thêm family trùng không tăng điểm |
| Vận hành | Restart/cache rỗng, rolling window, candle correction, stale quote, timeout không làm trạng thái thành READY giả |

Cập nhật golden test có giải thích khác biệt, không sửa expected chỉ để test xanh. Những kiểm thử đang khóa hành vi cũ sai phải chuyển thành test hành vi mới; giữ test contract còn đúng.

### Kiểm tra thực tế gọn

Chọn khoảng 20–30 snapshot từ chính symbol thường dùng, có tăng/giảm/range, vùng đẹp/vùng hỏng, đủ/thiếu M15. Xem chart, selected zone, lý do và trạng thái. Đây là QA nghiệp vụ, không phải mẫu đủ để chứng minh lợi nhuận.

Chạy replay theo nến đóng trên một số đoạn đại diện và smoke test scan toàn danh sách, restart, mở chi tiết/chart. Đo p50/p95 và số lần gọi scorer, so với baseline trên cùng máy; sửa regression đáng kể, không dựng hệ thống benchmark riêng.

Không bắt buộc một dự án backtest lớn để hoàn tất nâng cấp cá nhân. Nếu đánh giá hiệu quả giao dịch, tái sử dụng `smc_validation.py`/script hiện có: split theo thời gian, loại overlap giữa train/test và nhóm các lần scan cùng setup/visit thành một cơ hội. Khi có outcome R, dùng đúng planner/fill/cost, xử lý nến chạm cả SL/TP bằng dữ liệu thấp hơn hoặc quy ước bảo thủ. Không dùng 30 lần scan như 30 giao dịch độc lập.

Tách kết luận ENGINE_VERIFIED và EDGE_NOT_ESTABLISHED/EDGE_EVALUATED. Không đổi nhãn để vượt điều kiện chứng nhận execution hiện có. Kiểm chứng kỹ thuật xong chưa tự cấp quyền auto-trade nếu các policy hiện tại vẫn yêu cầu bằng chứng khác.

Tham khảo phương pháp: [Freqtrade lookahead analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/) giải thích rủi ro dùng dữ liệu tương lai trong backtest; [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) mô tả split thời gian và gap. Không cần cài hai công cụ này; áp dụng nguyên tắc vào replay sẵn có. Gap cố định không thay thế việc kiểm tra overlap theo tuổi thọ label.

## 13. Triển khai theo sáu chặng

| Chặng | Công việc | Đầu ra hoàn thành |
|---|---|---|
| 1. Khóa contract | Ghi baseline; định nghĩa input, event, zone, visit, score/readiness; bộ params nội bộ; inventory caller | Cấu trúc dữ liệu thống nhất, ca lỗi tái hiện, bảng mapping consumer |
| 2. Cấu trúc và dữ liệu | Cutoff, ATR tại sự kiện, confirmed swing, protected swing, BOS/CHoCH | Replay prefix và test cấu trúc đạt |
| 3. Vùng và lifecycle | Detector, group setup, fill/visit/decay, sweep linking; cắt top-K sau đánh giá | Cùng history tái dựng cùng zone/event, test family/lifecycle đạt |
| 4. Score và selection | B/Q/L/C, lựa chọn H4/H1, shared geometry, M15 readiness | Một kết quả typed cho cả hai side, đủ breakdown/reasons |
| 5. Tích hợp | Scanner, Analyze, prefilter, technical projection, planner, execution, persistence, UI | Cùng snapshot cùng kết quả; không fallback/bypass sai |
| 6. Hoàn tất | Test, snapshot QA, smoke/performance, docs, chuyển đổi dữ liệu | Một công thức SMC mặc định, cách khôi phục rõ, checklist đạt |

Khi người dùng quyết định tiếp tục phương án đầy đủ, Coder làm theo [checklist triển khai](smc-implementation-plan.md) và dừng tại các task **16, 40, 56, 72, 100, 116, 128 và 144** để Tech Lead review. Chỉ được làm phần tiếp theo sau khi mốc tương ứng được APPROVED; test xanh không thay cho review. Task128 đã **APPROVED (2026-09-16)**, nên có thể lập/giao Task129–144 theo lô riêng; không phải quyền tự động rollout/auto-entry. Các task khác thực hiện theo thứ tự, không cần xin xác nhận riêng từng task. Quy định này thay thế hướng dẫn trước cho phép làm xuyên suốt không dừng. Tiến độ hiện hành đọc tại [nhật ký](smc-implementation-progress.md); phạm vi đã chốt và đang triển khai theo lô.

Module ưu tiên sửa: `smc_context.py`, `smc_models.py`, `smc_lifecycle.py`, `smc_sweep_linking.py`, `smc_m15_confirmation.py`, `smc_confluence.py`, `smc_scorer.py`, `smc_scoring_result.py`, `smc_consumer_contract.py`. Chỉ tách thêm file khi thực sự giúp dễ đọc; không tạo framework detector/plugin tổng quát.

Consumer cần cập nhật đồng bộ: `scanner_live_producers.py`, `analysis_pipeline.py`, `smc_prefilter.py`, `technical_signal_scorer.py`, `scanner_features.py`, `scanner_scenario_producers.py`, composition/readiness/execution liên quan, persistence/renderer/chart và validation. Kiểm tra caller thực tế trước khi thay từng module; không dựa tên legacy để kết luận đường chạy.

Tương thích dữ liệu: cập nhật đồng bộ scorer, domain model, consumer và phép chiếu raw. Dùng dấu kiểm tra tương thích nội bộ để tránh tái sử dụng cache/result/config chứng nhận không còn phù hợp; không đưa mã kỹ thuật này lên giao diện. Dữ liệu lịch sử vẫn đọc theo ý nghĩa khi được tạo, không diễn giải điểm cũ thành điểm của công thức mới. Giữ journal và lệnh đang mở, không tự sửa SL/TP của chúng khi chuyển đổi. Không xóa lịch sử để chuyển đổi dễ hơn.

Thay trực tiếp công thức sau kiểm thử, chỉ một đường tính SMC trong vận hành. Có thể so fixture/offline baseline khi phát triển. Khôi phục bằng bản ứng dụng trước và snapshot cấu hình phù hợp; không để công thức cũ âm thầm làm fallback.

## 14. Tiêu chí hoàn tất

- Mọi lỗi ngữ nghĩa ở §2 có test và kết quả sửa hoặc quyết định thiết kế ghi rõ.
- Không có scoring từ nến chưa đóng; event/zone/visit có nguồn gốc và thời gian hiệu lực.
- Không có xác nhận từ visit cũ, D1 proximity giả reaction, hoặc group family tăng điểm trùng.
- Không có vùng được chọn che mất ứng viên hợp lệ do H4 ưu tiên tuyệt đối/cắt top-K sớm.
- Raw, readiness và plan dùng cùng kết quả canonical; hard invalidation không bị subtotal/fallback vượt qua.
- Missing data có lý do, không tự tăng điểm hoặc cấp READY; consumer malformed không tự chế vùng.
- Scanner/Analyze/Replay/Chart/Persistence thống nhất tại cùng snapshot.
- UI mặc định dễ đọc, không thêm thao tác cấu hình; tốc độ sử dụng trên máy cá nhân chấp nhận được.
- Regression suite phù hợp, snapshot QA, smoke restart/scan/order revalidation đạt; dữ liệu lịch sử còn đọc được.
- Không còn công thức cũ/cap cũ/AI penalty ngầm trong đường tính SMC sau nâng cấp; không tự tác động lệnh đang mở.

Các mở rộng không chặn bản này: order-flow thật, footprint, ML xác suất thắng, tự tối ưu mỗi symbol, breaker/inverse FVG đầy đủ, dashboard nghiên cứu, hysteresis có state, backtest quy mô lớn. Chỉ thêm khi sử dụng thực tế chỉ ra nhu cầu cụ thể.
