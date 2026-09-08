# SD Scope and Requirements

> **QUYỀN SỞ HỮU VÀ KIỂM SOÁT THAY ĐỔI — PO**
>
> Tài liệu này thuộc quyền sở hữu và quản lý của Product Owner (PO).
> **Nghiêm cấm bất kỳ cá nhân, coder hoặc AI agent nào tự ý sửa, bổ sung, xóa,
> đổi cấu trúc hoặc thay thế nội dung tài liệu khi chưa được PO cho phép rõ ràng.**
> Mọi thay đổi chỉ được thực hiện trong phạm vi PO đã cho phép. Việc được giao
> triển khai, kiểm thử, refactor hoặc đồng bộ tài liệu không mặc nhiên cấp quyền
> thay đổi tài liệu này. Nếu phát hiện sai sót, mâu thuẫn hoặc cần điều chỉnh,
> phải báo cáo đề xuất cho PO và giữ nguyên nội dung cho đến khi được phép.
> Quy định này áp dụng cả khi tài liệu đang ở trạng thái `DRAFT`.

> Trạng thái tài liệu: `DRAFT` — đặc tả, chưa phải chức năng runtime.
> Quy tắc tham chiếu: `sd-rules-v1`, hiện ở trạng thái `DRAFT`.
> Phạm vi triển khai hiện tại: phân tích Supply/Demand và cảnh báo cho cá nhân;
> mọi truy cập MT5 từ SD chỉ được phép đọc.
> Đồng bộ 08/09/2026 theo TL-PO-01–09 tại `03`, mục 14; giữ `DRAFT`.
> Câu trả lời PO đã được đưa vào yêu cầu và quy tắc; xác minh broker thực tế
> và triển khai/kiểm thử vẫn là công việc tiếp theo.

## 1. Mục đích và nguồn chuẩn

Tài liệu xác định SD giải quyết nhu cầu nào trên máy cá nhân, những chức năng
cần triển khai hiện tại, các giới hạn và cách kiểm tra tính đúng đắn khi xây
dựng. Đây là cơ sở viết thiết kế kỹ thuật, thiết kế UI và kiểm thử logic.

SD phục vụ riêng chủ ứng dụng. Phạm vi này không đặt lộ trình phát hành V1/V2
hoặc yêu cầu chứng nhận cho sản phẩm thương mại. `sd-rules-v1` là mã phiên bản
bộ quy tắc để truy vết kết quả và dữ liệu lưu, không phải phiên bản phát hành
phần mềm. Chủ ứng dụng đồng thời là người chốt yêu cầu và quy tắc (PO).

| Tài liệu | Trách nhiệm |
|---|---|
| [README](README.md) | Mục tiêu, nguyên tắc độc lập và định hướng kiến trúc SD. |
| `01-scope-and-requirements.md` | Phạm vi, yêu cầu chức năng và phi chức năng. |
| [02-trading-rules.md](02-trading-rules.md) | Công thức, ngưỡng, vòng đời, lựa chọn setup, điều kiện `READY`, parameter registry và định danh nghiệp vụ. |
| [03-technical-design.md](03-technical-design.md) | Module, contract, API, lưu trữ và tích hợp. |
| [04-ui-and-alerts.md](04-ui-and-alerts.md) | Bố cục, tương tác, biểu đồ và cách phát cảnh báo. |
| [05-acceptance-criteria.md](05-acceptance-criteria.md) | Các tình huống kiểm tra chức năng, dữ liệu mẫu và kết quả mong đợi cho sử dụng cá nhân. |

Các yêu cầu dưới đây xác định phạm vi triển khai hiện tại, trừ nội dung được
ghi rõ là ngoài phạm vi hoặc chưa chốt. Mã `SD-FR-*` và `SD-NFR-*` dùng để truy
vết từ yêu cầu sang thiết kế và kiểm thử, không thay thế reason code của nghiệp vụ.

Tài liệu này không định nghĩa lại thuật toán của `02`. Những con số được nhắc
lại chỉ mô tả cấu hình mặc định; tên tham số, đơn vị, giới hạn và ràng buộc chéo
phải theo parameter registry của `02`, mục 17. Nếu tài liệu hoặc fixture mâu
thuẫn, phải chốt lại nguồn chuẩn trước khi triển khai phần bị ảnh hưởng.

## 2. Người dùng và mục tiêu sử dụng

Người dùng là chủ ứng dụng AI Market Analyst, sử dụng trên máy cá nhân và tự
quyết định việc giao dịch. SD phải giúp người dùng:

- thấy các vùng Supply/Demand được phát hiện từ dữ liệu thị trường;
- hiểu chất lượng, trạng thái và quan hệ đa khung của từng vùng;
- xem kế hoạch tham khảo gồm hướng, Entry, Stop Loss, Take Profit và R:R;
- biết vì sao một setup đang được theo dõi, đủ điều kiện hoặc bị loại;
- nhận cảnh báo khi setup chuyển sang `READY`, không bị báo lặp mỗi lần quét;
- tiếp tục theo dõi sau khi khởi động lại ứng dụng.

`READY` chỉ có nghĩa setup đáp ứng bộ quy tắc SD tại thời điểm đánh giá. Nó
không phải trạng thái lệnh, xác nhận khớp lệnh hoặc cam kết kết quả giao dịch.
Hiệu quả lợi nhuận, win rate và P&L không phải điều kiện để triển khai hoặc
sử dụng tính năng phân tích/cảnh báo cá nhân.

Hiện chưa có lịch sử kiểm thử hoặc kết quả sử dụng SD. Không yêu cầu phải có
sẵn backtest, forward demo, lịch sử giao dịch hay báo cáo hiệu quả trước khi
bắt đầu triển khai. Kiểm thử logic được xây dựng cùng code bằng dữ liệu mẫu
hoặc giả lập; việc chưa có lịch sử test không đồng nghĩa được bỏ kiểm tra
tính đúng đắn của giá, trạng thái, khôi phục và cảnh báo.

Lịch sử nến dùng để tính ATR, phát hiện vùng và khôi phục trạng thái là dữ liệu
đầu vào của thuật toán, khác với lịch sử kiểm thử. Các yêu cầu đủ nến và an
toàn dữ liệu trong `02` vẫn áp dụng khi phân tích.

## 3. Phạm vi triển khai hiện tại

### 3.1 Trong phạm vi

| Nhóm | Nội dung |
|---|---|
| Dữ liệu | OHLC đã đóng trên D1, H4, H1, M15; Bid/Ask hiện tại; symbol metadata và lịch phiên theo symbol. |
| Phát hiện | Arrival, base, departure; bốn mẫu RBR, DBR, RBD, DBD; biên proximal/distal và khử vùng trùng. |
| Theo dõi vùng | H4/H1 chỉ retest đầu; D1 nhiều retest với TESTED; mitigation, broken và expired theo từng khung. |
| Đa khung | Thiên hướng/vị trí và vùng cung–cầu bối cảnh D1, setup/vùng cha H4, vùng vào lệnh H1 và xác nhận M15; phần mở rộng vùng D1 theo mục 3.3. |
| Setup | Chất lượng A/B/C, entry mode, kế hoạch giá, lựa chọn ưu tiên và xử lý xung đột hướng. |
| Trình bày | Màn hình SD riêng, biểu đồ vùng, chi tiết setup, trạng thái dữ liệu và lý do nghiệp vụ. |
| Cảnh báo | Sự kiện chuyển sang `READY`, định danh ổn định và lịch sử chống lặp. |
| Vận hành cá nhân | Phân tích nền, cấu hình SD, lưu cục bộ và khôi phục sau restart. |

SD phân tích symbol được cấu hình và có mapping hợp lệ tới nguồn MT5, canonical
symbol, nhóm tài sản và session policy. Các nhóm phiên đã được mô tả trong `02`
là `FOREX`, `METAL` và `CRYPTO`. Danh sách theo dõi được chọn theo nhu cầu của
chủ ứng dụng; mức tải đồng thời được điều chỉnh theo khả năng máy cá nhân khi
sử dụng. Không mặc nhiên coi mọi symbol của broker đều được hỗ trợ hoặc cam
kết quét toàn bộ danh mục trong một chu kỳ.

### 3.2 Ngoài phạm vi

- Gửi lệnh tới MT5 bằng bất kỳ hình thức tự động, bán tự động hoặc thủ công nào.
- Sửa, đóng, hủy lệnh hoặc vị thế; quản lý thực thi và trạng thái khớp lệnh.
- Backtest OOS, forward demo và tối ưu tham số tự động.
- Quản lý nhiều người dùng, phân quyền hoặc đồng bộ đám mây.
- Sử dụng quyết định, điểm số hoặc điều kiện cho phép giao dịch từ SMC, Scanner,
  Strategy Router, Decision Engine, Risk Engine hay Backtest hiện có.
- Dùng AI để tự diễn giải mẫu hình, thêm quy tắc hoặc quyết định trạng thái SD.

Khả năng gửi lệnh của các tính năng khác trong ứng dụng không mở rộng quyền của
SD. Cảnh báo SD không được kích hoạt đường thực thi lệnh của tính năng khác.
Mọi bổ sung thực thi giao dịch phải được xét như một phạm vi riêng.

### 3.3 Định hướng PO đã thống nhất: vai trò D1–H4–H1–M15

Ngày 08/09/2026, người dùng đồng ý lưu định hướng sản phẩm sau vào bộ đặc tả:

| Khung | Vai trò mong muốn |
|---|---|
| **D1** | Xác định vùng cung–cầu lớn để đánh giá bối cảnh và vùng cản đối diện, bên cạnh thiên hướng và premium/discount. |
| **H4** | Tìm setup trong bối cảnh D1. |
| **H1** | Xác định vùng vào lệnh chi tiết. |
| **M15** | Xác nhận phản ứng giá khi cần. |

Hai tình huống sản phẩm phải nhận diện và giải thích được:

- Setup BUY H4 đang tiến sát Supply D1: có vùng cản lớn phía trước, cần đánh
  giá ảnh hưởng tới khoảng trống giao dịch và mức phù hợp của setup.
- Demand H4 nằm trong Demand D1: có sự đồng thuận giữa vùng setup và vùng bối
  cảnh; cần thể hiện quan hệ này trong kết quả đánh giá.

Các tình huống SELL áp dụng đối xứng: Demand D1 có thể là vùng cản phía trước
setup SELL H4; Supply H4 trong Supply D1 là sự đồng thuận cùng hướng.

Vùng D1 không trực tiếp làm entry zone. Nhãn timeframe D1 không tự chứng minh
vùng mạnh hơn H4; vẫn phải xét chất lượng hình thành, tình trạng vùng và bối
cảnh. Có sự đồng thuận cũng không tự làm setup đủ điều kiện `READY`.

PO đã định lượng tại `03`, mục 14.1 và đồng bộ vào `02`, mục 9–10, 13–18:
D1 có tuổi mặc định 120 nến, nhiều retest với trạng thái TESTED; H4/H1 vẫn
chỉ dùng retest đầu. Đồng thuận cùng loại yêu cầu D1 xác nhận không muộn hơn
H4, cả hai hoạt động và overlap mặc định ít nhất 80% H4. D1 mất hiệu lực
không tự vô hiệu H4; H4 không bắt buộc nằm trong D1.

TP xét cản H4 fresh và D1 hoạt động; Entry nằm trong cản chặn READY. Nhãn
gần cản D1 đo từ Entry tới proximal, mặc định không quá 0.50 current ATR H4.
Không có điểm thưởng/phạt riêng cho đồng thuận hoặc nhãn gần; tác động cản
qua TP/R:R và điểm khoảng trống. D1 độc lập chỉ có Departure + Base tối đa
50 điểm và tình trạng sử dụng, không grade setup. Context D1 chưa tính đủ
là dữ liệu pending, khác với đã tính đủ nhưng không có đồng thuận.

### 3.4 Cách đánh giá mạnh/yếu và cách hiểu điểm số

Đánh giá theo hai bước: kiểm tra tính hợp lệ trước, sau đó mới chấm chất lượng.
Vùng sai mẫu, broken hoặc expired không được dùng để tạo setup hợp lệ chỉ vì
các thành phần còn lại có điểm cao.

Thang điểm hiện có trong `02`, mục 11 được giữ làm cơ sở:

| Nhóm đánh giá | Thành phần | Điểm tối đa | Ý nghĩa |
|---|---|---:|---|
| Chất lượng hình thành vùng | Departure + Base | 30 + 20 | Nhịp rời vùng mạnh, base ngắn/gọn; tính từ dữ liệu hình thành đã xác nhận. |
| Tình trạng sử dụng vùng | Freshness | 20 | Chưa retest hoặc retest đầu đang diễn ra theo quy tắc hiện tại. |
| Mức phù hợp của setup | Vị trí + Khoảng trống tới mục tiêu | 15 + 15 | Bối cảnh vị trí D1 hiện tại và R:R tới opposing zone hợp lệ. |

Tổng điểm tối đa 100; mặc định Grade A từ 85, Grade B từ 70 đến dưới 85,
Grade C dưới 70. Công thức và ngưỡng chi tiết nằm tại `02`, mục 11 và 17;
không tạo một bảng tham số riêng ở tài liệu phạm vi.

Kết quả cần trình bày điểm thành phần để người dùng phân biệt chất lượng vùng
khi hình thành với mức phù hợp của setup tại thời điểm đánh giá. Cùng một vùng
có thể thay đổi tổng điểm khi vị trí hoặc R:R thay đổi mà không thay đổi
Departure/Base. Tổng điểm và grade không phải xác suất giữ vùng hay tỷ lệ
thắng; 85 điểm không có nghĩa xác suất thành công 85%.

Không cộng điểm vì vùng đã được chạm nhiều lần. H4/H1 chỉ dùng retest đầu;
D1 cho nhiều retest nhưng không có thưởng freshness hoặc grade setup độc
lập. Mitigation chỉ hiển thị/ghi log. Không thưởng riêng D1–H4 hoặc phạt nhãn
gần cản D1; TP/R:R sau rounding phản ánh vùng cản theo `02`, mục 13.

## 4. Đầu vào, đầu ra và luồng sử dụng

### 4.1 Đầu vào và đầu ra

| Loại | Nội dung tối thiểu |
|---|---|
| Nến | `time`/`close_time` theo lịch biên broker có revision, OHLC, timeframe và price basis nhất quán; timestamp giây nguyên. |
| Giá hiện tại | Bid, Ask và thời điểm của quote để xử lý touch/retest và kiểm tra dữ liệu. |
| Metadata | Broker symbol, canonical symbol, `trade_tick_size` hoặc `point` dương. |
| Cấu hình | Tham số namespace `sd`, mapping nhóm tài sản, session policy và rules version. |
| Dữ liệu khôi phục | ID, touch/mode event evidence, quote/candle refs, config/session/data revisions với nội dung truy xuất được và alert ledger; không dùng snapshot state làm nguồn sự thật. |
| Kết quả vùng | ID, loại vùng, pattern, timeframe, thời điểm hình thành/xác nhận, biên, formation ATR và vòng đời. |
| Kết quả setup | Liên kết các vùng, hướng, entry mode/entry zone, Entry, SL, TP, R:R, chất lượng, trạng thái và reason codes. |
| Kết quả vận hành | Trạng thái dữ liệu, thời điểm phân tích, sự kiện cảnh báo và thông tin chẩn đoán. |

Contract thực thể tối thiểu theo `02`, mục 18; kiểu Python, schema và vị trí lưu
thuộc `03`. Không tự điền giá hoặc kế hoạch giả khi dữ liệu chưa đủ để tính.

### 4.2 Luồng chính

1. Ứng dụng khởi động IDLE, có thể xem inbox; watchlist mặc định EUR/USD,
   GBP/USD, USD/JPY, XAU/USD nếu chưa có cấu hình cá nhân.
2. Người dùng Start hoặc Refresh; hệ thống đọc lịch sử/evidence và kiểm tra
   cấu hình/dữ liệu. Start theo dõi liên tục, Refresh ở IDLE chỉ chạy một lần.
3. Phân tích đầy đủ để tái dựng vùng, vòng đời và setup trước khi cho phép
   `READY`.
4. Worker cập nhật quote/nến theo chu kỳ, đánh giá phần dữ liệu thay đổi và đưa
   kết quả lên UI.
5. Người dùng xem vùng, kế hoạch và lý do; hệ thống phát cảnh báo cho sự kiện
   `READY` chưa có trong ledger.
6. Khi dữ liệu lỗi, vùng bị vô hiệu hoặc hết hạn, UI phản ánh trạng thái mới.
   Lần khởi động sau phải tái dựng từ dữ liệu thay vì tin trạng thái cũ.

## 5. Yêu cầu chức năng

### SD-FR-01 — Đọc và chuẩn hóa dữ liệu

- Đọc đủ D1, H4, H1 và M15 qua adapter chỉ đọc. Logic SD nhận contract riêng,
  không nhận model quyết định của các engine khác.
- Resolve broker symbol sang canonical symbol trước khi phân tích và tạo ID.
  Thiếu mapping hoặc session policy hợp lệ phải có lý do dữ liệu không an toàn.
- Chuẩn hóa timestamp sang UTC, giữ biên nến của nguồn; không ghép lại nến theo
  timezone hiển thị hoặc timezone hệ điều hành.
- Kiểm tra OHLC, thứ tự thời gian, tick size, quote, spread, ATR, độ sâu lịch sử,
  gap trong phiên và stale theo `02`, mục 1, 16 và 18.5.
- Tải đủ lịch sử cho cả warmup và tái dựng; không chỉ dựa vào
  `min_candles_per_timeframe`. Độ sâu mặc định khi restore theo `02` là D1 = 395,
  H4 = 395, H1 = 515 và M15 = 253 nến đóng; mở rộng theo mốc replay nếu cần.
- Giữ tick mili giây và ref nến fallback; không dịch thêm offset cho UTC MT5.
  Lịch close/biên nguồn chưa rõ chặn READY với DATA_CANDLE_BOUNDARY_UNRESOLVED.

### SD-FR-02 — Phát hiện mẫu và tạo vùng

- Phát hiện RBR/DBR thành Demand, RBD/DBD thành Supply theo quy tắc arrival,
  base và departure của `02`, mục 3–6.
- Chỉ xác nhận vùng khi nến departure cuối đã đóng; không dùng nến tương lai
  hoặc tick để tạo pattern.
- Tính proximal/distal, làm tròn biên ra ngoài theo tick size và loại vùng không
  đạt độ rộng theo `02`, mục 7.
- Lưu `formation_atr` tại mốc quy định; khử trùng bằng tiêu chí xác định, không
  dùng điểm động hoặc R:R động để thay đổi danh tính vùng.
- Candidate bị loại phải có lý do thuộc registry; cùng đầu vào phải chọn cùng
  vùng và tạo cùng ID.

### SD-FR-03 — Theo dõi vòng đời vùng

- Quản lý `FRESH`, `RETESTING`, `BROKEN`, `EXPIRED` và `TESTED` chỉ cho D1.
- Bắt đầu retest bằng tick đúng phía giá hoặc nến đã đóng theo cơ chế bù trong
  `02`, mục 10. Departure không được tính là retest.
- Chỉ kết thúc retest khi nến đã đóng không còn giao source zone; tick không
  tự kết thúc retest hoặc xác nhận broken.
- H4/H1 chỉ sử dụng retest đầu; kết thúc thì vùng chưa broken hết hạn dù
  setup đã READY hay chưa. D1 đi RETESTING -> TESTED, tiếp tục qua nhiều retest
  tới khi broken/quá tuổi; không trở lại FRESH hoặc thưởng điểm số lần chạm.
- Tính mitigation để hiển thị/ghi log; không dùng mitigation làm điều kiện
  chấm điểm hoặc chuyển trạng thái mới.
- Áp dụng tuổi vùng, broken và ưu tiên trạng thái theo `02`; vòng đời luôn gắn
  với vùng đầy đủ, không gắn với phần entry bị thu hẹp.

### SD-FR-04 — Phân tích đa khung

- D1 xác định thiên hướng và vị trí discount/equilibrium/premium bằng swing đã
  xác nhận, đồng thời bổ sung vùng cung–cầu bối cảnh theo định hướng mục 3.3;
  D1 không trực tiếp làm entry zone. Phải nhận diện vùng cản D1 đối diện và
  sự đồng thuận D1–H4 theo `02`, mục 9.1; D1 mất hiệu lực không tự phá H4.
- Liên kết H1 với H4 cùng loại theo thời điểm, overlap và trạng thái hoạt động
  tại `02`, mục 9; ưu tiên H1 fresh trong H4 fresh.
- H1 không có H4 cha hoạt động không được `READY`. H4 cha broken/expired phải
  làm setup con chuyển `INVALIDATED`/`EXPIRED` tương ứng.
- H4 không có H1 liên kết vẫn được theo dõi nhưng bắt buộc xác nhận M15.
- D1 `NEUTRAL`, dealing range `UNKNOWN`, equilibrium hoặc vị trí ngược hướng
  phải chặn `READY` theo `02`, mục 8.

### SD-FR-05 — Chấm chất lượng và lựa chọn setup

- Tính điểm Departure, Base, Freshness, Vị trí và Khoảng trống tới mục tiêu;
  cung cấp tổng điểm, điểm thành phần và grade theo `02`, mục 11.
- Phân biệt chất lượng hình thành, tình trạng sử dụng vùng và mức phù hợp của
  setup theo mục 3.4; không biểu diễn grade như xác suất thành công hoặc tự
  cộng/trừ điểm riêng cho đồng thuận/gần cản D1; tác động qua plan/R:R.
- D1 độc lập chỉ có Departure + Base tối đa 50; base hợp lệ tối đa 4 nến.
  Thứ tự chấm setup dùng giá đã rounding, không dùng R:R đã format.
- Grade C chỉ để tham khảo, không được `READY`. Trong retest đầu đang diễn ra,
  giữ điểm freshness theo quy tắc thay vì trừ ngay khi giá chạm.
- Xếp hạng setup cùng hướng bằng đầy đủ tiêu chí tại `02`, mục 15, bao gồm
  tiêu chí ID cuối cùng để xử lý trường hợp bằng nhau.
- Mỗi symbol có tối đa một setup `READY`. Khi có `DIRECTION_CONFLICT`, cả hai
  phía giữ `WATCHING`; riêng thay đổi thiên hướng D1 không xóa conflict.

### SD-FR-06 — Entry và xác nhận M15

- Phân biệt source zone, entry zone và protective zone. Setup H1 trong H4 dùng
  toàn bộ H1; setup chỉ H4 dùng phần phía proximal làm entry và toàn bộ H4 để
  bảo vệ theo `02`, mục 12.
- Chạm live dùng Ask cho BUY, Bid cho SELL; không dùng mid-price. Có cơ chế bù
  bằng nến M15 đã đóng giao entry zone theo quy tắc.
- Grade A có H1 trong H4 dùng `TOUCH`; Grade B hoặc setup chỉ H4 dùng
  `M15_CONFIRMATION`. Cả hai vẫn phải đạt toàn bộ điều kiện `READY`.
- Bắt buộc entry-touch latch của first retest, giữ khi giá rời entry mà
  source retest chưa kết thúc. Đổi grade/mode không reset latch/cửa sổ/ID.
- Chấp nhận Rejection, Engulfing hoặc Micro BOS trong cửa sổ từ first entry
  touch. TOUCH không tự timeout vì thiếu M15; mode M15 đang hiệu lực hết cửa
  sổ không xác nhận thì EXPIRED, kể cả đổi từ TOUCH sau cửa sổ. Grade C giữ
  mode gần nhất, chưa từng A/B thì dùng M15. Terminal không hồi sinh.

### SD-FR-07 — Xây dựng kế hoạch tham khảo

- Cung cấp hướng, Entry tham chiếu tại proximal của entry zone, SL ngoài distal
  của protective zone đầy đủ và TP từ cản H4 fresh/D1 hoạt động gần nhất.
- Rounding entry sub-zone vào trong, SL ra ngoài và TP bảo thủ theo chiều
  giao dịch; kiểm tra hình học/risk rồi R:R, điểm/grade và READY. Risk/spread
  dùng giá cuối; R:R chưa format so với ngưỡng default 2.0.
- Entry nằm trong bất kỳ cản hợp lệ nào chặn READY. Chọn cản theo khoảng
  cách dương, bằng nhau ưu tiên D1 rồi ID; hiển thị cản D1 gần riêng dù TP H4.
- Thiếu opposing zone hợp lệ thì không tạo `READY`; không tự dựng TP bằng số R
  cố định để làm setup đạt yêu cầu.
- Đánh giá lại target/R:R khi setup chưa cuối, kể cả đang `READY`, theo cadence
  ở `02`, mục 18.4. Mất điều kiện phải cập nhật trạng thái và lý do.
- Kế hoạch không tạo yêu cầu gửi lệnh hoặc thay đổi tài khoản MT5.

### SD-FR-08 — Quản lý trạng thái setup

- Sử dụng đúng `DETECTED`, `WATCHING`, `READY`, `INVALIDATED`, `EXPIRED`; không
  đồng nhất trạng thái setup với trạng thái zone.
- Chỉ chuyển `READY` khi đồng thời đạt toàn bộ công thức tại `02`, mục 14:
  vùng bảo vệ/H4 cha hoạt động, D1 và vị trí phù hợp, grade A/B, retest đầu đang
  diễn ra, entry-touch latch có hiệu lực, xác nhận bắt buộc đạt, kế hoạch
  hợp lệ, Entry ngoài cản, đủ R:R, dữ liệu an toàn và không có xung đột hướng.
- Áp dụng bảng chuyển trạng thái và ưu tiên
  `INVALIDATED > EXPIRED > READY > WATCHING > DETECTED`.
- `INVALIDATED` và `EXPIRED` là trạng thái cuối. Không hồi sinh setup cuối khi
  giá quay lại hoặc khi restart.
- Có reason codes cho điều kiện thiếu, lý do chọn/loại và thay đổi trạng thái;
  dùng enum đóng và thứ tự ổn định theo `02`, mục 18.3.

### SD-FR-09 — Màn hình và biểu đồ SD

- Có màn hình riêng để xem kết quả theo symbol và các timeframe SD.
- UI phải chạy tốt và cho xem đầy đủ thông tin/thao tác ở cả màn hình
  **1366 × 768, scale 100%** và **Full HD 1920 × 1080, scale 150%** theo
  `SD-NFR-11`. Áp dụng cho màn hình SD, cấu hình/watchlist, inbox và popup.
- Hiển thị vùng Supply/Demand, proximal/distal, source/entry/protective zone,
  quan hệ H1–H4, trạng thái vùng và mitigation mà người dùng có thể phân biệt.
- Bổ sung cách thể hiện vùng bối cảnh D1, vùng cản đối diện và sự đồng thuận
  D1–H4 theo mục 3.3; phân biệt các thông tin này với vùng vào lệnh và điểm số.
- Hiển thị thiên hướng/vị trí D1, grade/điểm, Entry/SL/TP/R:R, entry mode,
  trạng thái setup và lý do chưa `READY` hoặc đã hết hiệu lực.
- Thể hiện thời điểm kết quả, trạng thái tải/phân tích, thiếu dữ liệu, dữ liệu
  không an toàn và lỗi; không trình bày kết quả lưu cũ như một `READY` hiện tại
  khi chưa đánh giá lại.
- Start/Stop/Refresh theo ý định chạy; đổi màn hình không ngắt theo dõi,
  Stop giữ dữ liệu và hiện STOPPING khi SDK chưa trả. Đổi watchlist/config
  validate, tăng revision, hủy generation cũ và giữ ledger.
- Watchlist mặc định bốn mã nêu ở mục 4.2, chọn từ registry 31 mã; danh sách
  rỗng không chạy, không áp trần cứng 8 hoặc tự đổi Market Watch. Lọc symbol,
  hướng, trạng thái; chọn setup mở detail/chart. `04` cụ thể hóa bố cục/màu,
  không được tự tính điểm hoặc thay đổi quyết định nghiệp vụ.

### SD-FR-10 — Cảnh báo và chống lặp

- Live phát khi chuyển sang READY và key chưa có. Sau restore/full analysis,
  đánh giá hiện tại riêng: đủ READY với quote an toàn và key chưa có thì phát
  RESTORE_CURRENT, không backdate hoặc phát bù setup chỉ đạt trong quá khứ.
- Dùng `alert_key` ổn định theo `02`, mục 18.2, gắn với setup và retest đầu.
  Không phát lại khi quét tiếp, khi `READY -> WATCHING -> READY` trong cùng
  retest, hoặc khi restart với ledger còn hợp lệ.
- Cảnh báo phải truy về được symbol, setup, retest, thời điểm và kế hoạch tại
  sự kiện để người dùng đối chiếu với kết quả đang xem.
- Inbox cục bộ bắt buộc; popup mặc định bật, âm thanh mặc định tắt và tùy
  chọn. Hiệu ứng chỉ cho sự kiện mới sau commit; tắt hiệu ứng không bỏ inbox.
  Reload/restart không phát lại hiệu ứng; không tuyên bố exactly-once UI.
- Lưu payload lịch sử bất biến, mode/grade/plan và nguồn live/restore; hỗ trợ
  đánh dấu đã đọc, mở setup hiện tại. Telegram/email ngoài phạm vi; `03`/`04`
  cụ thể hóa lưu/phát và trình bày.

### SD-FR-11 — Cấu hình và lưu cục bộ

- Lưu cấu hình SD độc lập trong namespace `sd`, bao gồm tham số và cấu hình
  session theo symbol; không lấy cấu hình chiến lược cũ làm quyết định SD.
- Validate tên, kiểu, đơn vị, min/max và ràng buộc chéo theo registry; báo cấu
  hình không hợp lệ thay vì tự clamp hoặc âm thầm thay giá trị.
- Session override theo symbol phải có hiệu lực từ lần phân tích tiếp theo,
  xóa cache safety và đánh giá lại vùng đã lưu trước khi cho `READY`.
- Lưu event evidence tối thiểu theo `02`, mục 18.5: source/entry touch,
  quote timestamp/precision/Bid/Ask, candle refs, mode-change input và
  config/session/data revisions có thể truy xuất, cùng ledger trong cycle.
  Không bắt buộc toàn tick feed; snapshot state/grade/mode chỉ để đối chiếu.
- Mode không nằm trong setup ID. Giữ config/evidence cũ để chứng minh
  terminal; config mới không xóa terminal, reset retest/cửa sổ hoặc ledger.
- Gắn rules version vào kết quả/định danh theo contract. Trạng thái tài liệu
  `DRAFT` không thuộc chuỗi version hoặc canonical ID.

### SD-FR-12 — Khôi phục, cập nhật nền và xử lý lỗi

- Khởi động IDLE; Start/Refresh thực hiện restore ở `02`, mục 18.5 với
  snapshot/evidence/config history/ledger, đủ nến và replay bằng ID ổn định.
- Mở rộng M15 từ mốc sớm nhất cần tìm touch, hoặc source confirmation khi
  có offline/chưa biết touch, cộng warmup/swing và kéo tới hiện tại; mở rộng
  khung khác nếu cần tái tính mode. Thiếu evidence giữ FULL_ANALYSIS_PENDING.
- Snapshot sai schema/version phải được bỏ khỏi quá trình khôi phục nghiệp
  vụ nhưng giữ bản sao chẩn đoán; ghi reason code tương ứng. Giữ ledger để
  chống phát lại, không phát cảnh báo trong lúc dựng lại.
- Vùng lưu không tái dựng được phải hết hạn với `ZONE_NOT_RECONSTRUCTED`.
  Chỉ cho phép `READY` sau một full analysis hoàn tất không lỗi.
- Poll theo `analysis_poll_seconds` (mặc định 5 giây); không có nến mới thì
  cập nhật phần phụ thuộc tick/dữ liệu, có nến mới thì tính lại phần phụ thuộc
  timeframe tương ứng theo `02`, mục 18.4.
- Khi session đóng, không poll quote để đổi trạng thái; tuổi/stale không tăng
  qua các biên nến ngoài phiên.
- Khi dữ liệu không an toàn, giữ vùng đã lưu và chặn `READY`; setup chưa cuối
  có trạng thái tối đa `WATCHING`, vẫn áp dụng ưu tiên invalidation/expiration.
- Lỗi đọc nguồn, phân tích hoặc lưu trữ phải được phản ánh rõ; không dùng lỗi
  làm lý do phát sinh setup hoặc cảnh báo đủ điều kiện.

## 6. Yêu cầu phi chức năng và ràng buộc kiến trúc

| Mã | Yêu cầu | Cách kiểm chứng |
|---|---|---|
| `SD-NFR-01` | Quyết định SD độc lập với SMC, Scanner, các engine và AI; chỉ dùng chung hạ tầng trung tính qua adapter. | Rà soát dependency và chạy core với nguồn dữ liệu giả lập, không cần các engine cũ. |
| `SD-NFR-02` | Toàn bộ đường chạy SD chỉ đọc MT5, không phát sinh tác dụng phụ lên lệnh/vị thế. | Kiểm thử bằng adapter ghi nhận lời gọi; rà soát controller, service và luồng cảnh báo không gọi API thực thi. |
| `SD-NFR-03` | Cùng nến, quote/timestamp đầu vào, cấu hình, rules version và lịch sử tick/ledger liên quan phải cho cùng kết quả và ID. | Fixture lặp lại và so sánh chạy liên tục với restore; kiểm tra tie-break và canonical ID. |
| `SD-NFR-04` | Không dùng dữ liệu tương lai; pattern, swing, ATR, broken và xác nhận M15 chỉ dùng dữ liệu được phép tại mốc đánh giá. | Kiểm thử dữ liệu theo từng tiền tố thời gian, đặc biệt departure và pivot cần nến bên phải đã đóng. |
| `SD-NFR-05` | Dữ liệu thiếu/sai/quá cũ và quá trình restore chưa xong không được tạo `READY`; lỗi phải có nguyên nhân truy được. | Fixture OHLC/timestamp/ATR/quote/spread/session sai, gap, stale và snapshot không hợp lệ. |
| `SD-NFR-06` | Đọc dữ liệu, phân tích và lưu trữ chạy nền, không chặn UI thread; kết quả được đưa lên UI qua cơ chế phù hợp kiến trúc ứng dụng. | Kiểm tra trực tiếp trên máy cá nhân: UI vẫn phản hồi khi tải/phân tích, tác vụ hoàn tất hoặc báo lỗi rõ ràng, không tích tụ tác vụ quét. |
| `SD-NFR-07` | Lưu cục bộ có kiểm tra tính hợp lệ, bảo toàn ledger qua restart và xử lý lỗi ghi/đọc rõ ràng. | Kiểm thử restart, snapshot hỏng, version mismatch và lỗi lưu; thiết kế cơ chế ghi/khôi phục trong `03`. |
| `SD-NFR-08` | Kết quả và sự kiện truy về được ID, symbol, timeframe, thời điểm, rules version và reason codes; log không chứa thông tin xác thực MT5. | Đối chiếu kết quả, log và alert ledger; rà soát nội dung log. |
| `SD-NFR-09` | Tuân theo phân lớp hiện tại: `core/`, `services/`, `controllers/`, `workers/`, `ui/`, `config/`, `tests/`; file mới dùng tiền tố `supply_demand_`. Core thuần Python, không phụ thuộc UI. | Rà soát cây file/import theo `03`; không tạo kiến trúc feature-first riêng hoặc đưa logic SD vào file `smc_*`/`scanner_*`. |
| `SD-NFR-10` | Khi triển khai hoặc đổi thuật toán, bổ sung kiểm thử logic phù hợp và cập nhật tài liệu; sau lần chốt quy tắc đầu, thay đổi ảnh hưởng kết quả phải tăng rules version theo `02`, mục 17. | Dùng dữ liệu mẫu/giả lập kiểm tra phần thay đổi; đối chiếu rules, ID và xử lý snapshot khác version. Không đòi hỏi lịch sử test có sẵn. |
| `SD-NFR-11` | UI chạy tốt, đọc được và truy cập đầy đủ thông tin/thao tác ở 1366 × 768 scale 100% và 1920 × 1080 scale 150%; không cắt mất nội dung/nút hoặc buộc giảm scale để sử dụng. | Kiểm tra riêng cả hai cấu hình trong vùng làm việc thực tế, gồm bảng/chart/detail, cấu hình, watchlist, inbox/popup, nội dung dài và dark/light; theo `04` SD-UI-18/19 và `05` AC-16/17. |

Quyết định PO về màn hình tối thiểu, ngày 08/09/2026 (`SD-NFR-11`):

- Hai cấu hình trên đều phải được hỗ trợ. Full HD ở scale 150% tương ứng
  khoảng **1280 × 720 đơn vị logic** trước khi trừ taskbar/khung cửa sổ;
  không coi đó là vùng nội dung 1920 × 1080 hoặc tương đương 1366 × 768.
- Mốc kiểm tra là cửa sổ ứng dụng maximized trong vùng làm việc khả dụng,
  taskbar vẫn hiện; tính cả thanh tiêu đề, điều hướng và các phần shell của
  ứng dụng. Không yêu cầu fullscreen, ẩn taskbar hoặc đổi scale hệ điều hành.
- "Hiển thị đầy đủ" nghĩa mọi thông tin và thao tác đều xem/đọc/sử dụng được
  qua bố cục thích ứng, tab, panel thu gọn và cuộn; không bắt buộc mọi panel
  xuất hiện cùng lúc. Không ẩn bỏ trường dữ liệu để làm vừa màn hình.
- Start/Stop/Refresh, trạng thái vận hành và lối mở cấu hình/inbox luôn truy
  cập được. Không chồng chữ, cắt số giá hoặc thu nhỏ font để nhét nội dung.
  Bảng được cuộn ngang/dọc; detail và form dài được cuộn dọc. Dialog/popup
  nằm trong vùng khả dụng, nút đóng/Áp dụng/Hủy không rơi ngoài màn hình.
- Resize/đổi scale phải bố trí lại UI, giữ ngữ cảnh đang xem và dữ liệu đang
  nhập, không đổi quyết định nghiệp vụ hoặc gián đoạn worker. Kiểm tra phản
  hồi khi phân tích nền theo `SD-NFR-06`; không đặt benchmark mới.

Chu kỳ poll là lịch yêu cầu cập nhật, không phải cam kết hoàn tất phân tích trong
5 giây. Hiệu năng được kiểm tra với watchlist thực tế trên máy cá nhân: UI phản
hồi được, kết quả có thời điểm rõ ràng và tác vụ không xếp hàng vô hạn. Số symbol
và chu kỳ quét có thể điều chỉnh trong giới hạn cấu hình hợp lệ sau khi sử dụng.

Không bắt buộc benchmark trên máy chuẩn, số lượt chạy cố định, ngưỡng p95 hay
báo cáo tải trước khi triển khai/sử dụng cá nhân. Nếu đo thời gian, RAM hoặc độ
trễ, các số đo phục vụ tìm lỗi và cải thiện trải nghiệm; chưa có số đo không
được diễn giải thành đã đạt hiệu năng.

## 7. Kiểm tra tính đúng đắn và truy vết

`05-acceptance-criteria.md` ghi các tình huống kiểm tra theo nhóm dưới đây khi
triển khai phần chức năng tương ứng. Fixture là bộ dữ liệu mẫu có đầu vào và
kết quả mong đợi, có thể tự tạo hoặc giả lập; không yêu cầu lịch sử test có sẵn.
Ưu tiên kiểm thử tự động cho logic giá/R:R, vòng đời, khôi phục, chống lặp và
ranh giới MT5 chỉ đọc; kiểm tra UI/vận hành trực tiếp trên máy cá nhân.

Bảng này xác định hành vi cần kiểm tra, không khẳng định test đã tồn tại hoặc
đã đạt, không đặt quy trình nghiệm thu phát hành thương mại và không yêu cầu
chứng minh lợi nhuận. Có thể triển khai từng phần đã đủ quy tắc; nội dung chưa
chốt chỉ chặn phần phụ thuộc, không chặn công việc độc lập.

| Nhóm kiểm tra | Yêu cầu liên quan | Kết quả mong đợi |
|---|---|---|
| Dữ liệu và phiên | FR-01, FR-12; NFR-04, NFR-05 | Chuẩn hóa đúng, tải đủ lịch sử, phân biệt nghỉ phiên với gap/stale và chặn `READY` khi dữ liệu không an toàn. |
| Pattern và biên | FR-02; NFR-03, NFR-04 | Đúng bốn mẫu, loại candidate sai, làm tròn đúng tick, khử trùng xác định và không nhìn trước. |
| Vòng đời | FR-03, FR-04, FR-08 | Tick/nến bù tạo cùng retest phù hợp; broken/expired đúng ưu tiên, H4 cha tác động đúng và không hồi sinh trạng thái cuối. |
| Chất lượng và kế hoạch | FR-05, FR-06, FR-07 | Điểm/grade, liên kết đa khung, TOUCH/M15, Entry/SL/TP/R:R và conflict đúng `02`. |
| Bối cảnh vùng D1 | FR-04, FR-05, FR-09 | Theo `02`, mục 9.1: nhận diện BUY H4 gần Supply D1, Demand H4 trong Demand D1 và các trường hợp SELL đối xứng; kiểm chứng tác động đúng quy tắc đã chốt, không tự cộng điểm. |
| Điều kiện READY | FR-04 đến FR-08, FR-12 | Mỗi điều kiện bắt buộc có trường hợp đạt/không đạt; tối đa một `READY` mỗi symbol và hạ trạng thái khi mất điều kiện. |
| Cảnh báo và restore | FR-10, FR-11, FR-12; NFR-03, NFR-07 | Một cảnh báo cho cùng khóa, không lặp qua chuyển trạng thái/restart; không tin snapshot state và xử lý dữ liệu lưu không hợp lệ. |
| UI và vận hành | FR-09, FR-12; NFR-06, NFR-08 | Hiển thị vùng/kế hoạch/lý do nhất quán, phân biệt kết quả cũ và dữ liệu lỗi, UI vẫn tương tác được. |
| Màn hình tối thiểu và scale | FR-09; NFR-06, NFR-11 | Kiểm tra riêng 1366 × 768/100% và 1920 × 1080/150% với taskbar/shell; xem đủ dữ liệu, thao tác được mọi form/popup, không cắt/chồng hoặc buộc giảm scale. |
| Ranh giới tích hợp | FR-07, FR-10; NFR-01, NFR-02, NFR-09, NFR-10 | Không phụ thuộc quyết định engine cũ, không gửi lệnh, đúng phân lớp và quản lý version. |

Trong bảng, `FR-*` và `NFR-*` là cách viết gọn của `SD-FR-*` và `SD-NFR-*`.

## 8. Trạng thái đồng bộ và công việc còn lại

TL-PO-01–09 tại `03`, mục 14 đã được đồng bộ vào `01`/`02` và phần thiết kế
liên quan. Giữ DRAFT, chưa xác nhận runtime hoặc hiệu quả. Các bước còn lại:

| Nội dung | Nơi thực hiện |
|---|---|
| Xác minh lịch biên/close time của broker đang dùng bằng metadata/cấu hình và dữ liệu đọc được; thiếu thì chặn READY symbol liên quan. | `03`, adapter/session; TL-PO-02 |
| Viết code theo contract đã đồng bộ, tạo dữ liệu mẫu/giả lập và kiểm tra logic quan trọng cùng triển khai. | `03`, `05` |
| Cụ thể hóa bố cục/UI theo Start/Stop/Refresh, inbox/popup/âm thanh đã chốt, không thêm yêu cầu thương mại. | `04` |
| Kiểm tra trực tiếp trên máy cá nhân, điều chỉnh watchlist/tải trong giới hạn hợp lệ; không bắt buộc benchmark hoặc lịch sử test. | `03`, `05` |
| Chủ ứng dụng chuyển rules sang APPROVED khi chốt sử dụng; không tự đổi trạng thái vì đã đồng bộ tài liệu. | `02` |

Việc hoàn tất tài liệu phạm vi không đồng nghĩa SD đã được triển khai hoặc được
phép chạy runtime. Runtime chỉ dùng rules đã chuyển sang `APPROVED` theo `02`;
`APPROVED` ghi nhận chủ ứng dụng đã chốt quy tắc sử dụng, không chứng nhận hiệu
quả giao dịch hoặc hoàn tất một đợt phát hành. Trạng thái hiện vẫn là `DRAFT`;
việc điều chỉnh phạm vi cá nhân không tự chốt các công thức còn thiếu. Không
tự diễn giải video, bài viết hoặc biểu đồ bên ngoài để lấp chỗ trống trong bộ
đặc tả.
