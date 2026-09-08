# SD Trading Rules

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

> Rules version: `sd-rules-v1`
> Trạng thái tài liệu: `DRAFT` — không được dùng trong runtime
> Phạm vi triển khai hiện tại: phân tích Supply/Demand và cảnh báo trên máy cá nhân;
> mọi truy cập MT5 từ SD chỉ đọc, không gửi lệnh.

> Đồng bộ 08/09/2026 theo câu trả lời PO TL-PO-01–09 tại
> `03-technical-design.md`, mục 14: vùng D1, giá/ID, entry latch, evidence và
> vận hành cá nhân. Giữ `sd-rules-v1` và `DRAFT`; chưa xác minh lịch biên broker
> thực tế, chưa xác nhận implementation hoặc hiệu quả giao dịch.

Tài liệu mô tả quy tắc cho nhu cầu riêng của chủ ứng dụng. `sd-rules-v1` là mã
phiên bản bộ quy tắc để truy vết kết quả, định danh và dữ liệu khôi phục; không
đại diện cho đợt phát hành V1 hoặc lộ trình sản phẩm thương mại.

Các ngưỡng mặc định là lựa chọn đặc tả khởi đầu, chưa được kiểm chứng bằng lịch
sử sử dụng SD, backtest hoặc forward demo. Không yêu cầu có sẵn lịch sử test
hay chứng minh lợi nhuận để triển khai. Có thể tạo dữ liệu mẫu/giả lập khi viết
code để kiểm tra công thức, trạng thái, khôi phục và cảnh báo. Các phần đã đủ
quy tắc có thể triển khai và kiểm thử độc lập trong khi hoàn thiện bản `DRAFT`.

Lịch sử nến tối thiểu tại mục 1 và 18.5 phục vụ tính toán và tái dựng trạng thái,
không phải lịch sử kiểm thử chiến lược. Yêu cầu đủ dữ liệu vẫn áp dụng; phần mềm
cá nhân không được tạo `READY` từ dữ liệu thiếu hoặc quy tắc chưa được chốt.
Việc chốt quy tắc và quản lý phiên bản được giải thích tại mục 17.

## 1. Dữ liệu và quy ước

SD sử dụng D1, H4, H1 và M15. Chỉ nến đã đóng được dùng để phát hiện mẫu,
xác nhận cấu trúc và tính chỉ báo.

Mỗi nến phải có `time` (open time), `close_time`, `open`, `high`, `low`,
`close`; khoảng nến là `[time, close_time)`. Close time là biên kết thúc kỳ
theo lịch broker đã xác thực, không phải tick cuối hoặc mặc định open của
nến kế tiếp qua gap. Timestamp nến phải là giây nguyên. Lịch biên có nguồn
gốc, phạm vi hiệu lực và revision; xem mục 16. Điều kiện OHLC hợp lệ:

```text
high >= max(open, close)
low  <= min(open, close)
high > low
```

`tick_size` lấy từ `trade_tick_size` của symbol metadata MT5; nếu giá trị này
không dương thì dùng `point`. Không được suy ra tick size từ số chữ số thập
phân. Không có giá trị dương từ cả hai nguồn thì dữ liệu không an toàn với lý do
`DATA_TICK_SIZE_MISSING`.

Các đại lượng chuẩn hóa:

```text
range      = high - low
body       = abs(close - open)
body_ratio = body / range
ATR        = Wilder ATR(atr_period), tính trên chính timeframe đang xét
current_price = (Bid + Ask) / 2
spread        = Ask - Bid
```

Các giá trị số trong tài liệu là mặc định của parameter registry tại mục 17.
Code phải đọc chúng qua tên tham số, không được lặp số trần.

Không phân tích timeframe nếu có ít hơn `min_candles_per_timeframe` nến hợp lệ
hoặc chưa tính được ATR. Sai số của mỗi timeframe:

```text
epsilon = max(epsilon_min_ticks × tick_size, epsilon_atr_ratio × ATR)
```

`epsilon` áp dụng cho so sánh biên vùng, overlap, swing, breakout và thứ tự
giá. Hai giá trị có chênh lệch không quá `epsilon` được coi là bằng nhau.

ATR Wilder dùng cửa sổ hữu hạn để kết quả sau restart giống kết quả live. Với
`atr_warmup_bars = 200`, lấy đúng 200 True Range liên tiếp kết thúc tại nến cần
tính và thêm close của một nến trước cửa sổ để tính True Range đầu tiên:

```text
TR[i] = max(high[i] - low[i],
            abs(high[i] - close[i-1]),
            abs(low[i] - close[i-1]))

ATR_seed = mean(TR[0 : atr_period])
ATR[i]    = (ATR[i-1] × (atr_period - 1) + TR[i]) / atr_period
```

Không đủ đúng `atr_warmup_bars` True Range thì ATR không hợp lệ; không rút ngắn
cửa sổ và không lấy ATR đã chạy từ thời điểm tùy ý của process.

Mỗi candidate lưu `formation_atr`: ATR tại nến ngay trước base. ATR trong các
mục 3–7, 10 và 11 là `formation_atr`, nhờ đó biên vùng và trạng thái broken
không thay đổi theo biến động tương lai. `current_atr` là ATR tại nến đã đóng
mới nhất, tính bằng cùng quy tắc. Trừ nơi ghi mốc ATR riêng, các mục còn lại dùng
`current_atr` của timeframe tương ứng, kể cả khi tính `epsilon`. SL dùng
`formation_atr` của protective zone; xác nhận M15 dùng mốc ATR tại mục 12.

### 1.1 Giá dùng cho từng loại quyết định

- OHLC dùng đúng price basis do nguồn nến cung cấp và phải nhất quán trong cả
  chuỗi; với MT5 đây thường là Bid bar.
- Cấu trúc, pattern, retest lịch sử và broken dùng OHLC của nến đã đóng.
- Vị trí premium/discount dùng `current_price`.
- Chạm entry zone theo thời gian thực dùng Ask cho BUY và Bid cho SELL.
- Không được dùng mid-price để xác nhận chạm entry zone.
- Quote/touch live giữ `time_msc` hợp lệ và serialize nguyên mili giây UTC.
  Nguồn chỉ có `time` thì giữ độ chính xác giây và ghi precision; có cả hai
  phải kiểm tra nhất quán theo đơn vị, không âm thầm bỏ trường sai.
- `received_at` tách khỏi source time. Tick đúng open M15 thuộc nến mới;
  fallback giữ ref/open time của chính nến giao vùng, không dùng close time
  fallback để gán sang nến kế tiếp.

### 1.2 Nến giao với vùng

Với vùng chuẩn hóa `[zone_low, zone_high]`, một nến giao vùng khi wick của nến
chạm hoặc xuyên biên:

```text
candle.high >= zone_low - epsilon
AND candle.low <= zone_high + epsilon
```

Wick chạm là đủ; thân nến không bắt buộc đi vào vùng. Một tick giao entry zone
khi giá giao dịch theo mục 1.1 nằm trong
`[zone_low - epsilon, zone_high + epsilon]`.

`broken` không dùng phép giao vùng. Nó chỉ dùng giá đóng cửa hoặc wick vượt
distal theo mục 10.

## 2. Thuật ngữ

- **Rally:** nhịp tăng có dịch chuyển ròng đủ lớn.
- **Drop:** nhịp giảm có dịch chuyển ròng đủ lớn.
- **Base:** cụm nến cân bằng nằm giữa arrival và departure.
- **Departure:** nhịp rời base xác nhận mất cân bằng.
- **Demand:** vùng tạo bởi departure tăng.
- **Supply:** vùng tạo bởi departure giảm.
- **Proximal:** cạnh vùng gần giá rời vùng nhất.
- **Distal:** cạnh xa proximal, dùng làm biên vô hiệu cấu trúc.
- **Fresh:** chưa có lần quay lại vùng sau khi departure hoàn tất.
- **Retest:** một lần giá đi từ ngoài vào vùng.
- **Mitigation:** mức giá đã xuyên vào một phần vùng trong retest.
- **Broken:** vùng đã bị xuyên thủng theo điều kiện vô hiệu.
- **Opposing zone:** vùng hợp lệ gần nhất ngược hướng với setup.
- **Source zone:** toàn bộ vùng H1 hoặc H4 được detector tạo ra.
- **Entry zone:** phần giá dùng để xác định thời điểm có thể vào lệnh.
- **Protective zone:** source zone cung cấp distal cho SL và invalidation.

## 3. Xác định nhịp Rally và Drop

Một nhịp gồm từ 1 đến 3 nến liên tiếp và được đo bằng:

```text
net_move = abs(close_cuối - open_đầu) / ATR
```

Nhịp là **Rally** khi:

- `close_cuối > open_đầu`;
- `net_move >= 1.0`;
- ít nhất 60% tổng range thuộc các nến tăng;
- ít nhất một nến có `body_ratio >= 0.60`.

Nhịp là **Drop** với điều kiện đối xứng theo hướng giảm. Nhịp không đạt một
trong các điều kiện trên không được dùng làm arrival hoặc departure.

## 4. Xác định Base

Base gồm từ 1 đến 4 nến liên tiếp ngay trước departure. Một cụm là base hợp lệ
khi đồng thời thỏa mãn:

- mỗi nến có `range <= 0.80 × ATR`;
- mỗi nến có `body_ratio <= 0.50`;
- toàn cụm có `base_high - base_low <= 1.20 × ATR`;
- với base từ hai nến, ít nhất 50% số cặp liên tiếp phải giao nhau theo mục 1.2;
  base một nến tự đạt điều kiện này;
- không có gap giữa hai nến liên tiếp lớn hơn `0.10 × ATR`; gap của một cặp là
  `max(0, current.low - previous.high, previous.low - current.high)`.

Tỷ lệ overlap của base được tính bằng
`số_cặp_giao_nhau / (số_nến_base - 1)`.

Nếu nhiều độ dài base cùng hợp lệ trước một departure, chọn cụm ngắn nhất. Nếu
cùng độ dài, chọn cụm có độ rộng nhỏ nhất.

## 5. Xác nhận Departure

Departure là Rally hoặc Drop từ 1 đến 3 nến ngay sau base. Ngoài quy tắc tại
mục 3, departure phải thỏa mãn:

```text
departure_move = abs(close_cuối - open_đầu) / ATR >= 1.50
```

Và:

- departure tăng đóng trên `base_high + 0.10 × ATR`;
- departure giảm đóng dưới `base_low - 0.10 × ATR`;
- departure tăng không có close dưới
  `base_high - 0.50 × base_width`; departure giảm không có close trên
  `base_low + 0.50 × base_width`;
- ít nhất một nến departure có `body_ratio >= 0.65`.

Vùng chỉ được xác nhận sau khi nến cuối của departure đóng. Nến departure
không được tính là retest.

## 6. Phân loại mẫu

Arrival dùng từ 1 đến 3 nến liền trước base và áp dụng quy tắc Rally/Drop tại
mục 3. Detector thử lần lượt cửa sổ 1, 2 và 3 nến:

- nếu nhiều cửa sổ hợp lệ cùng hướng, chọn cửa sổ dài nhất;
- nếu có cả Rally và Drop hợp lệ, loại candidate với lý do
  `AMBIGUOUS_ARRIVAL`;
- nếu không cửa sổ nào hợp lệ, không tạo vùng.

Do từng cửa sổ được đánh giá độc lập, cửa sổ 3 nến không đạt nhưng cửa sổ 2
nến đạt thì dùng cửa sổ 2 nến.

| Arrival | Departure | Pattern | Loại vùng |
|---|---|---|---|
| Rally | Rally | RBR | Demand tiếp diễn |
| Drop | Rally | DBR | Demand đảo chiều |
| Rally | Drop | RBD | Supply đảo chiều |
| Drop | Drop | DBD | Supply tiếp diễn |

Một base chỉ tạo một vùng từ departure đầu tiên được xác nhận.

Detector quét nến từ cũ đến mới theo thời điểm kết thúc departure. Nến có thể
đóng vai trò trong hai candidate khác nhau; departure của vùng cũ được phép làm
arrival hoặc base của mẫu sau. Trong cùng một candidate, một nến chỉ có một vai
trò và thứ tự bắt buộc là `arrival -> base -> departure`.

Sau khi phát hiện, hai vùng cùng loại trên cùng timeframe được coi là trùng khi
thời điểm xác nhận cách nhau không quá 3 nến và
`overlap_width / min(zone_width_1, zone_width_2) >= 0.80`. Chỉ giữ candidate
theo thứ tự: tổng điểm Departure + Base tại mục 11 cao hơn, vùng hẹp hơn, thời
điểm xác nhận sớm hơn, rồi định danh tăng dần. Không dùng vị trí, freshness hoặc
R:R động để khử trùng.

## 7. Biên vùng

Với Demand:

```text
distal   = min(low của các nến base)
proximal = max(max(open, close) của các nến base)
zone     = [distal, proximal]
```

Với Supply:

```text
proximal = min(min(open, close) của các nến base)
distal   = max(high của các nến base)
zone     = [proximal, distal]
```

Vùng bị loại nếu:

- `distal == proximal` sau khi làm tròn theo tick size;
- `zone_width > 1.20 × ATR`;
- `zone_width < 2 × tick_size`.

Biên vùng được làm tròn ra ngoài: Demand làm tròn distal xuống và proximal
lên; Supply làm tròn proximal xuống và distal lên.

## 8. Cấu trúc và vị trí D1

Swing trên mọi timeframe dùng pivot hai phía. Với `epsilon` của timeframe:

- swing high phải cao hơn từng high của hai nến trước và hai nến sau ít nhất
  `epsilon`;
- swing low phải thấp hơn từng low của hai nến trước và hai nến sau ít nhất
  `epsilon`.

Pivot chỉ được dùng sau khi hai nến bên phải đã đóng. Swing bằng nhau trong
phạm vi `epsilon` không tạo higher high, higher low, lower high hoặc lower low.
Mục này áp dụng các swing D1 để xác định thiên hướng.

Thiên hướng D1:

- `BUY` khi hai swing high và hai swing low gần nhất trong 250 nến D1 đều cao
  dần quá `epsilon`;
- `SELL` khi hai swing high và hai swing low gần nhất trong 250 nến D1 đều thấp
  dần quá `epsilon`;
- `NEUTRAL` trong các trường hợp còn lại.

Dealing range là khoảng giữa swing high và swing low D1 đã xác nhận gần nhất.
Vị trí hiện tại:

```text
position = (current_price - range_low) / (range_high - range_low)
```

Nếu thiếu một trong hai swing, `range_high <= range_low + epsilon` hoặc
`current_price` không hợp lệ thì dealing range là `UNKNOWN`, thiên hướng là
`NEUTRAL` và không tính `position`.

- `discount`: `position <= 0.45`;
- `equilibrium`: `0.45 < position < 0.55`;
- `premium`: `position >= 0.55`.

BUY chỉ hợp lệ khi thiên hướng D1 là `BUY` và giá ở discount. SELL chỉ hợp lệ
khi thiên hướng D1 là `SELL` và giá ở premium. `NEUTRAL`, equilibrium hoặc vị
trí ngược hướng không được tạo setup `READY`.

## 9. Liên kết đa khung thời gian

H4 là vùng cha; H1 là vùng vào lệnh ưu tiên. Hai vùng liên kết khi:

- cùng loại Demand hoặc cùng loại Supply;
- H1 được xác nhận sau thời điểm bắt đầu base H4;
- phần giao nhau chiếm ít nhất 80% độ rộng vùng H1;
- cả hai vùng đang hoạt động: chưa broken và chưa expired.

```text
overlap_ratio = overlap_width / h1_zone_width
```

Quy tắc chọn:

1. Ưu tiên H1 fresh nằm trong H4 fresh cùng hướng.
2. Nếu nhiều H1 cùng hợp lệ, chọn vùng có chất lượng cao nhất.
3. Nếu bằng điểm, chọn vùng gần giá hiện tại hơn; tiếp theo chọn vùng mới hơn.
4. H4 không có H1 liên kết vẫn được theo dõi nhưng luôn cần xác nhận M15.
5. H1 không có H4 cha đang hoạt động không được chuyển sang `READY`.
6. Khi H4 cha broken, setup H1 chuyển `INVALIDATED`; khi H4 cha expired, setup
   H1 chuyển `EXPIRED`. H4 cha expired được coi là không còn tồn tại cho mọi
   liên kết mới.

D1 xác định thiên hướng, vị trí và vùng cung–cầu bối cảnh tại mục 9.1.
D1 không được dùng trực tiếp làm entry zone.

### 9.1 Vùng cung–cầu bối cảnh D1

Theo quyết định TL-PO-01: D1 cung cấp bối cảnh/vùng cản; H4 tìm setup,
H1 xác định entry chi tiết và M15 xác nhận khi cần.

- Tái sử dụng detector RBR/DBR/RBD/DBD, base/departure, biên và khử trùng trên
  nến D1; tính formation ATR D1 tại cùng mốc quy định cho detector.
- D1 chỉ có điểm hình thành Departure + Base tối đa 50 và tình trạng sử dụng;
  không áp grade A/B/C hoặc thang 100 điểm setup cho D1 độc lập.
- Vòng đời D1 tại mục 10 cho phép nhiều retest tới khi broken/quá tuổi;
  không mở rộng quyền dùng retest thứ hai của H4/H1.

Đồng thuận D1–H4 yêu cầu cùng loại, cả hai vùng hoạt động, D1 confirmation
không muộn hơn H4 confirmation và
`overlap_width / h4_zone_width >= d1_h4_min_overlap_ratio` (mặc định 0.80).
Nhiều D1 hợp lệ: overlap cao hơn -> Departure + Base cao hơn -> confirmation
mới hơn -> ID tăng dần. D1 broken/expired thì bỏ liên kết và đánh giá lại
bối cảnh, không tự invalidated H4. H4 không bắt buộc nằm trong vùng D1.

Kế hoạch xét cản H4 fresh và D1 hoạt động theo mục 13. Tìm thêm cản D1 phía
trước gần nhất kể cả khi TP chọn H4. Nhãn `D1_OPPOSING_ZONE_NEAR` khi khoảng
cách **Entry tham chiếu -> proximal cản D1** không quá
`d1_obstacle_near_atr × current_atr_H4` (mặc định 0.50 ATR H4). UI ghi rõ mốc
đo từ Entry, không phải current price. Entry nằm trong cản xử lý riêng bằng
`ENTRY_INSIDE_OPPOSING_ZONE`, không bỏ qua cản bao quanh Entry.

Ví dụ: BUY H4 tiến sát Supply D1 có vùng cản phía trước; Demand H4 trong
Demand D1 có đồng thuận. SELL áp dụng đối xứng. D1 `TESTED`/`RETESTING` vẫn
có thể là cản hoặc vùng đồng thuận nếu chưa broken/quá tuổi.

Giữ thang điểm và xếp hạng setup: không thưởng đồng thuận D1–H4 hoặc phạt
riêng nhãn gần cản. Cản ảnh hưởng qua TP/R:R và điểm khoảng trống; RR dưới
ngưỡng hoặc Entry nằm trong cản chặn READY. D1 bias, premium/discount và
conflict vẫn áp dụng; đồng thuận không thay thế các gate đó.

`D1_ZONE_ALIGNED`, `D1_ZONE_UNALIGNED`, `D1_OPPOSING_ZONE_NEAR` là lý do thông
tin. Không có đồng thuận không phải dữ liệu lỗi; chưa tính đủ context D1
mới là pending và chặn READY theo data safety. Lịch sử tối thiểu D1 mặc định
395 nến theo mục 18.5, có thể cần tải thêm để replay.

## 10. Vòng đời vùng

Vòng đời bắt đầu từ nến ngay sau khi departure được xác nhận và luôn gắn với
source zone đầy đủ.

Với H4/H1, một retest bắt đầu khi source zone đang fresh; với D1, vùng có
thể đang `FRESH` hoặc `TESTED`. Retest bắt đầu khi xảy ra một trong hai sự kiện:

- tick live đi từ ngoài vào source zone: Demand dùng Ask, Supply dùng Bid; hoặc
- ở mỗi lần nhận nến mới đóng, kể cả khi khôi phục lịch sử, nến hiện tại giao
  source zone theo mục 1.2 và là nến đầu tiên sau departure hoặc nến lifecycle
  hợp lệ ngay trước đó không giao source zone.

Nhánh nến đóng là cơ chế bù cho lần chạm xảy ra giữa hai chu kỳ poll. Với tick
live, `started_at` là timestamp của tick; với nến đóng hoặc restore, `started_at`
là close time của nến giao vùng và `start_source` phân biệt nguồn phát hiện.
Lưu cả ref/open time của nến fallback; timestamp live giữ nguyên precision
nguồn. Liên kết source retest và entry touch bằng khoảng nến/evidence, không
loại entry touch chỉ vì close time fallback H4/H1 muộn hơn tick/M15 touch.

Các nến liên tiếp còn giao source zone thuộc cùng retest. Retest kết thúc khi
một nến đã đóng không còn giao source zone. Tick thời gian thực có thể bắt đầu
retest nhưng không tự kết thúc retest.

Mức mitigation:

```text
Demand = (proximal - giá thấp nhất trong retest) / zone_width
Supply = (giá cao nhất trong retest - proximal) / zone_width
```

Kết quả được chặn trong `[0, 1]`. Theo quy tắc hiện tại, mitigation chỉ dùng để
hiển thị độ xuyên sâu và ghi log; nó không tự thay đổi điểm hoặc trạng thái.
`BROKEN` và chính sách retest riêng D1/H4/H1 bên dưới quyết định vòng đời.

Vùng bị `BROKEN` khi xảy ra một trong hai điều kiện:

- Demand có giá đóng cửa `< distal - epsilon`; Supply có giá đóng cửa
  `> distal + epsilon`;
- wick vượt distal quá `0.20 × ATR` dù giá đóng cửa quay lại vùng.

Với setup H1 trong H4, source zone H1 và H4 có vòng đời độc lập. H1 broken hoặc
H4 cha broken đều làm setup `INVALIDATED`. Entry sub-zone không có quy tắc
broken riêng.

Vùng là `FRESH` trước retest đầu tiên. H4/H1 chỉ tạo setup cho lần quay lại
đầu tiên: khi retest đầu kết thúc, vùng chưa broken chuyển `EXPIRED` với
`FIRST_RETEST_COMPLETED`, dù setup đã READY hay chưa.

D1 dùng nhiều retest: `FRESH -> RETESTING -> TESTED`, các lần sau
`TESTED -> RETESTING -> TESTED`; không trở lại FRESH và không hết hạn chỉ vì
retest kết thúc. Đếm ordinal cho từng lần để hiển thị, không cộng điểm theo
số lần chạm. `TESTED` chỉ hợp lệ cho D1. Broken dùng close/wick D1 và
formation ATR D1; quá tuổi dùng nến D1 đóng sau confirmation. Broken có ưu
tiên cao hơn expired trên mọi khung. D1 mất hiệu lực chỉ bỏ liên kết bối
cảnh; protective H1/H4 và H4 cha vẫn quyết định invalidation của setup.

Giới hạn tuổi mặc định tính từ lúc xác nhận departure:

| Timeframe | Số nến tối đa |
|---|---:|
| D1 | 120 |
| H4 | 120 |
| H1 | 240 |

Vượt giới hạn trên thì vùng chuyển `EXPIRED`. `BROKEN` có ưu tiên cao hơn
`EXPIRED`.

## 11. Điểm chất lượng vùng

Chỉ chấm điểm sau khi vùng vượt qua điều kiện bắt buộc ở các mục 3–10.
Setup H4/H1 có tổng tối đa 100; D1 độc lập chỉ có Departure + Base tối đa 50
và trạng thái/retest, không grade setup:

### 11.1 Departure — tối đa 30

| `departure_move` | Điểm |
|---|---:|
| `1.50–<2.00 ATR` | 18 |
| `2.00–<2.50 ATR` | 23 |
| `>=2.50 ATR` | 26 |

Cộng 4 điểm nếu departure đóng vượt swing gần nhất cùng timeframe theo hướng
departure. Chỉ xét swing được xác nhận trong 60 nến ngay trước nến departure
đầu tiên; không có swing trong cửa sổ thì không cộng điểm. Tổng thành phần bị
chặn ở 30.

### 11.2 Base — tối đa 20

- 8 điểm nếu số nến base <= `quality_base_compact_max_bars`, ngược lại 5
  trong miền base hợp lệ tối đa 4 nến; mặc định 1–2 được 8, 3–4 được 5;
- 7 điểm nếu `zone_width <= 0.60 × ATR`, ngược lại 4 điểm;
- 5 điểm nếu mọi nến base có `body_ratio <= 0.35`, ngược lại 2 điểm.

### 11.3 Freshness — 20

Thành phần này dùng cho setup H4/H1, không áp cho vùng bối cảnh D1 độc lập.

- 20 điểm khi chưa có retest;
- 0 điểm sau khi retest đầu tiên kết thúc.

Trong lúc retest đầu tiên đang diễn ra, giữ 20 điểm để đánh giá setup.

### 11.4 Vị trí — tối đa 15

- 15 điểm cho Demand ở discount hoặc Supply ở premium;
- 0 điểm cho vị trí khác.

### 11.5 Khoảng trống tới mục tiêu — tối đa 15

Tính preliminary R:R theo mục 13:

| R:R | Điểm |
|---|---:|
| `>=3.0` | 15 |
| `2.5–<3.0` | 12 |
| `2.0–<2.5` | 9 |
| `<2.0` | 0 |

Không có opposing zone hợp lệ hoặc không tính được preliminary R:R thì mục này
được 0 điểm.

Phân hạng:

- Grade A: `score >= 85`;
- Grade B: `70 <= score < 85`;
- Grade C: `score < 70`.

Grade C chỉ được hiển thị để tham khảo, không được tạo `READY`.

### 11.6 Cách hiểu điểm mạnh/yếu ở góc nhìn sản phẩm

Quy trình đánh giá gồm hai bước: kiểm tra vùng hợp lệ trước, rồi mới tính điểm
để đánh giá setup. Broken/expired và các điều kiện bắt buộc không được bù bằng
điểm cao. Sau retest đầu, mức freshness 0 chỉ giải thích tình trạng vùng H4/H1 đã hết
hạn; không cho phép tiếp tục giao dịch bằng các điểm thành phần khác.

Thang 100 điểm ở trên gồm ba nhóm ý nghĩa:

| Nhóm | Thành phần | Điểm tối đa | Đặc tính |
|---|---|---:|---|
| Chất lượng hình thành vùng | Departure + Base | 50 | Được xác định từ nến hình thành và swing hợp lệ tại thời điểm đó, dùng formation ATR; không đổi theo giá tương lai với cùng dữ liệu và rules. |
| Tình trạng sử dụng vùng | Freshness | 20 | Theo chính sách retest đầu; giữ 20 khi retest đầu đang diễn ra. |
| Mức phù hợp của setup | Vị trí + Khoảng trống tới mục tiêu | 30 | Phụ thuộc vị trí hiện tại trong dealing range D1 và R:R tới opposing zone H4/D1 hợp lệ. |

Đây là cách nhóm và giải thích các thành phần hiện có, không tạo thêm trường
điểm bắt buộc, trọng số mới hoặc thang grade riêng. UI cần cho xem điểm thành
phần để tránh đồng nhất tổng điểm setup với độ bền nội tại của vùng.

Ví dụ: departure từ 2.50 ATR và phá swing hợp lệ được 30 điểm; base đạt đủ
ba tiêu chí cao nhất được 20; chưa retest được 20; vị trí phù hợp được 15;
R:R = 2.2 được 9. Tổng là **94 điểm, Grade A**. Nếu chỉ vị trí hiện tại chuyển
sang không phù hợp, điểm vị trí về 0 và tổng còn **79 điểm, Grade B**; chất
lượng hình thành vẫn là 50 điểm. Setup lúc này không được `READY` vì mất điều
kiện vị trí, dù grade vẫn là B.

Nguyên tắc diễn giải:

- Grade A/B/C là phân hạng theo bộ quy tắc, không phải xác suất giữ vùng hoặc
  tỷ lệ thắng. 85 điểm không có nghĩa xác suất thành công 85%.
- Vùng chất lượng cao vẫn có thể không có setup hợp lệ do thiếu khoảng trống
  mục tiêu, sai bối cảnh, thiếu xác nhận, dữ liệu không an toàn hoặc conflict.
- Không cộng điểm vì chạm vùng nhiều lần. H4/H1 chỉ dùng retest đầu; D1 được
  retest nhiều lần nhưng không nhận điểm thưởng. Mitigation chỉ hiển thị/ghi log.
- Không cộng điểm chỉ vì timeframe lớn hơn. Đồng thuận/gần cản D1 không có
  điểm thưởng/phạt riêng; cản tác động qua TP/R:R và điểm khoảng trống.
- D1 độc lập chỉ hiển thị Departure + Base tối đa 50 và tình trạng sử dụng,
  không áp tổng điểm/grade setup H4/H1.

## 12. Entry và xác nhận M15

Ba loại vùng phải được lưu riêng:

| Setup | Source zone | Entry zone | Protective zone |
|---|---|---|---|
| H1 trong H4 | Toàn bộ H1 | Toàn bộ H1 | Toàn bộ H1 |
| Chỉ có H4 | Toàn bộ H4 | 50% phía proximal của H4 | Toàn bộ H4 |

Với setup chỉ có H4, H4 cha, source zone và protective zone là cùng một vùng.

Entry zone của setup chỉ có H4:

```text
Demand = [proximal - 0.50 × zone_width, proximal]
Supply = [proximal, proximal + 0.50 × zone_width]
```

Entry zone chỉ dùng để phát hiện chạm. Giữ proximal H4; biên trong Demand
làm tròn lên tick, biên trong Supply làm tròn xuống để sub-zone không rộng
hơn tỷ lệ đã chọn. Sub-zone rộng bằng 0: `INVALID_TRADE_GEOMETRY`, không nới
biên tùy ý. H1 dùng toàn vùng đã làm tròn. Distal của protective zone đầy đủ
luôn dùng cho SL/invalidation, không dùng distal của entry sub-zone.

Giá dùng để kiểm tra chạm vùng:

- BUY dùng Ask;
- SELL dùng Bid.

Chạm entry zone dùng cơ chế kép tại mục 10 nhưng áp dụng trên chính entry zone:
tick live hoặc nến M15 đã đóng giao vùng. Nến M15 chứa tick chạm đầu tiên, hoặc
nến M15 fallback đầu tiên giao vùng, là nến số 1 của cửa sổ xác nhận 8 nến.

Entry-touch latch là điều kiện bắt buộc độc lập với source retest. Bật
`entry_touch_latched` khi tick đúng phía giá hoặc nến M15 đã đóng giao chính
entry zone. Lưu first touch, source time, nến M15 chứa touch/fallback và
first retest ID. Tick đúng open thuộc M15 mới; fallback dùng ref nến giao
vùng, không suy nến số 1 từ close time fallback.

Giữ latch khi giá rời entry nhưng first retest source còn diễn ra; chạm lại
không ghi đè mốc hoặc reset cửa sổ. M15 rejection được đóng ngoài entry.
Retest kết thúc/broken/quá tuổi/timeout áp dụng terminal; latch cũ không mở
cơ hội mới. Chưa latch dùng `ENTRY_NOT_REACHED`.

Mode động theo grade, không thuộc setup ID:

| Tình huống setup chưa terminal | Mode / hành vi |
|---|---|
| H1 trong H4, Grade A | TOUCH, vẫn cần latch và các gate READY. |
| Grade B hoặc chỉ H4 | M15_CONFIRMATION. |
| A -> B | Chưa xác nhận thì WATCHING trong cửa sổ còn hiệu lực; có xác nhận thì xét mọi gate. |
| B -> A | Có thể TOUCH nếu chưa terminal; không tạo ID/alert key mới. |
| Grade C | Chặn READY, giữ mode gần nhất để xử lý timeout đã bắt đầu; chưa từng A/B thì dùng M15_CONFIRMATION. |

Các mode dùng cùng mốc first entry touch và cửa sổ
`m15_confirmation_max_bars` (mặc định 8 nến). Luôn theo dõi bằng chứng M15
trong cửa sổ kể cả TOUCH. TOUCH không cần xác nhận và không tự timeout chỉ
vì hết cửa sổ; khi M15 có hiệu lực, xét xác nhận tới hết nến số 8 trước khi
timeout. Đổi sang M15 sau cửa sổ mà trong cửa sổ không có xác nhận thì
EXPIRED ngay. Timeout đã xảy ra không được grade tăng/config/restart hồi
sinh. Lưu input sự kiện đổi mode để replay, không suy mode cũ từ grade mới.

Một trong các xác nhận M15 sau là đủ:

1. **Rejection:** nến chạm entry zone và đóng ra ngoài qua proximal theo hướng
   giao dịch. Với BUY dùng lower wick
   `min(open, close) - low`; với SELL dùng upper wick
   `high - max(open, close)`. Nến phải có `body_ratio >= 0.20`,
   `body >= 0.10 × ATR_M15`, thân cùng hướng và rejection wick dài ít nhất bằng
   thân. BUY phải đóng `> proximal + epsilon_M15`; SELL phải đóng
   `< proximal - epsilon_M15`. Doji không hợp lệ. `ATR_M15` lấy tại nến ngay
   trước nến xác nhận. Chính rejection wick phải giao entry zone: BUY kiểm tra
   đoạn `[low, min(open, close)]`, SELL kiểm tra đoạn
   `[max(open, close), high]` theo công thức overlap tại mục 1.2.
2. **Engulfing:** thân nến cùng hướng bao phủ toàn bộ thân nến trước với sai số
   `epsilon_M15`: `current_body_low <= previous_body_low + epsilon_M15` và
   `current_body_high >= previous_body_high - epsilon_M15`. BUY phải đóng
   `> previous_high + epsilon_M15`; SELL phải đóng
   `< previous_low - epsilon_M15`.
3. **Micro BOS:** sau khi chạm vùng, giá đóng vượt swing high M15 gần nhất đối
   với BUY hoặc swing low M15 gần nhất đối với SELL quá `epsilon_M15`. Swing
   phải được xác nhận trong 40 nến M15 ngay trước lần chạm; không có swing trong
   cửa sổ thì Micro BOS không hợp lệ.

Khi mode M15 có hiệu lực, không có xác nhận trong cửa sổ thì setup EXPIRED
theo quy tắc trên. Retest đầu kết thúc làm setup EXPIRED ở mọi mode; broken
và quá tuổi giữ nguyên ưu tiên tại mục 14.

## 13. Stop Loss, Take Profit và R:R

Entry tham chiếu dùng proximal của entry zone sau rounding. SL dựa trên
protective zone đầy đủ:

```text
sl_buffer = max(sl_buffer_atr × protective_zone.formation_atr,
                sl_buffer_min_ticks × tick_size)
BUY  SL = floor_to_tick(protective_distal - sl_buffer)
SELL SL = ceil_to_tick(protective_distal + sl_buffer)
```

Default buffer là max(0.10 formation ATR, 2 tick). Cản đối diện là Supply
cho BUY, Demand cho SELL; xét **H4 fresh và D1 hoạt động** đã xác nhận tại
mốc đánh giá. D1 FRESH/RETESTING/TESTED đều hợp lệ nếu chưa broken/quá tuổi.

1. Kiểm tra Entry nằm trong bất kỳ cản hợp lệ nào, kể cả chạm biên theo
   epsilon của timeframe cản. Nếu có, `ENTRY_INSIDE_OPPOSING_ZONE`, chặn READY
   và loại candidate khỏi conflict. Không bỏ qua cản bao quanh Entry chỉ vì
   proximal không ở phía trước.
2. Chọn proximal phía trước Entry: BUY > Entry + epsilon cản; SELL < Entry -
   epsilon cản. Khoảng cách dương nhỏ nhất thắng; bằng nhau chính xác thì
   ưu tiên D1 rồi ID tăng dần. Giá so sánh là Decimal sau rounding.
3. TP BUY làm tròn xuống tick, TP SELL làm tròn lên tick nếu cần. Không có
   cản làm TP hợp lệ thì `OPPOSING_ZONE_MISSING`, không tự dựng TP theo số R.
4. Tìm cản D1 phía trước gần nhất riêng để hiển thị nhãn gần theo mục 9.1,
   kể cả khi TP đang chọn H4; lưu timeframe/ID cản được chọn.

Thứ tự tính bắt buộc: giá -> rounding -> kiểm tra hình học/risk -> R:R ->
điểm khoảng trống/grade -> READY. Với giá kế hoạch cuối:

```text
BUY  RR = (TP - Entry) / (Entry - SL)
SELL RR = (Entry - TP) / (SL - Entry)
```

Entry/SL/TP phải đúng thứ tự; risk >= `min_risk_ticks × tick_size` (default
2 tick); R:R >= `min_rr` (default 2.0). Spread/risk dùng risk sau rounding.
Không dùng R:R hiển thị: 1.9996 không đạt 2.0 dù UI làm tròn thành 2.00.

Target được đánh giá lại mỗi chu kỳ cho setup chưa terminal, kể cả READY;
tập cản thay đổi phải cập nhật TP/R:R và điểm khoảng trống. Mất R:R hoặc
Entry lọt vào cản mới làm setup về WATCHING; khi đạt lại trong cùng retest
có thể READY nhưng không phát lại cùng alert key. Không thưởng/phạt thêm
vì đồng thuận D1 hoặc nhãn tiến sát; tác động cản đã nằm trong kế hoạch.

## 14. Trạng thái setup và cảnh báo

`INVALIDATED` và `EXPIRED` là trạng thái cuối. Ba trạng thái còn lại được đánh
giá lại ở mỗi chu kỳ.

| Trạng thái | Điều kiện hiện tại |
|---|---|
| `DETECTED` | Vùng hoạt động, chưa retest và giá cách entry zone trên `0.50 × current_atr` của entry timeframe. |
| `WATCHING` | Vùng hoạt động nhưng chưa đạt `READY`, bao gồm gần vùng, điều kiện tạm thời không đạt hoặc đang có conflict. |
| `READY` | Công thức `READY` bên dưới đúng tại chu kỳ hiện tại. |
| `INVALIDATED` | Protective zone hoặc H4 cha bị broken. |
| `EXPIRED` | Protective zone hoặc H4 cha quá tuổi; mode M15 có hiệu lực và hết cửa sổ không xác nhận; hoặc retest đầu tiên kết thúc. |

Công thức `READY`:

```text
READY =
    protective_zone_active
    AND h4_parent_active
    AND d1_bias_aligned
    AND premium_discount_aligned
    AND quality_grade IN {A, B}
    AND first_retest_active
    AND entry_touch_latched
    AND required_m15_confirmation_passed
    AND valid_sl_tp
    AND NOT entry_inside_opposing_zone
    AND RR >= 2.0
    AND market_data_safe
    AND NOT direction_conflict
```

`required_m15_confirmation_passed` luôn đúng khi mode hiện tại là TOUCH;
mode M15 phải có xác nhận thực tế trong cửa sổ. Grade C luôn chặn READY.
`entry_touch_latched` giữ hiệu lực trong cùng first retest theo mục 12; không
yêu cầu current price còn trong entry zone khi đã có latch/xác nhận hợp lệ.

Khoảng cách từ giá giao dịch tới entry zone bằng 0 khi giá nằm trong vùng;
ngược lại là khoảng cách tuyệt đối tới biên gần nhất. Ngưỡng theo dõi dùng
`current_atr` của timeframe chứa entry zone.

### 14.1 Bảng chuyển trạng thái

| Từ | Sự kiện | Sang |
|---|---|---|
| Mới | Vùng được xác nhận | `DETECTED` hoặc `WATCHING` theo khoảng cách |
| `DETECTED` | Giá tiến vào phạm vi `0.50 × current_atr` | `WATCHING` |
| `WATCHING` | Giá rời xa khi chưa retest | `DETECTED` |
| `DETECTED`/`WATCHING` | Công thức `READY` đúng | `READY` |
| `READY` | D1/vị trí sai, grade không đạt, mode M15 còn cửa sổ nhưng thiếu xác nhận, R:R dưới ngưỡng, Entry trong cản, dữ liệu không an toàn hoặc conflict | `WATCHING` |
| `WATCHING` sau khi hạ từ `READY` | Công thức `READY` đúng lại trong cùng retest | `READY` |
| Bất kỳ trạng thái chưa cuối | Protective zone hoặc H4 cha broken | `INVALIDATED` |
| Bất kỳ trạng thái chưa cuối | Protective zone hoặc H4 cha quá tuổi | `EXPIRED` |
| `WATCHING`/`READY` | Retest đầu tiên kết thúc | `EXPIRED` |
| Trạng thái chưa cuối | Mode M15 có hiệu lực và hết cửa sổ không xác nhận, kể cả vừa đổi từ TOUCH sau cửa sổ | `EXPIRED` |
| `INVALIDATED`/`EXPIRED` | Mọi sự kiện | Giữ nguyên |

Thứ tự ưu tiên khi nhiều sự kiện cùng chu kỳ:

```text
INVALIDATED > EXPIRED > READY > WATCHING > DETECTED
```

Live chỉ phát một cảnh báo khi setup chuyển sang `READY` và key chưa có.
Sau restore/full analysis, đánh giá hiện tại riêng theo mục 18.5: hiện đủ
READY và chưa key thì phát `RESTORE_CURRENT`, không phát bù trạng thái quá
khứ. Không phát lại khi quét tiếp hoặc `READY -> WATCHING -> READY` trong
cùng retest. Khóa chống lặp là `setup_id + first_retest_id`, không đổi theo mode.

## 15. Xung đột và thứ tự lựa chọn

Khi có nhiều setup cùng hướng, sắp xếp theo thứ tự:

1. Grade A trước Grade B;
2. điểm chất lượng cao hơn;
3. R:R cao hơn;
4. khoảng cách tới entry zone nhỏ hơn;
5. thời điểm xác nhận vùng mới hơn;
6. định danh vùng theo thứ tự tăng dần để kết quả luôn xác định.

Chỉ một setup mỗi symbol được phép ở trạng thái `READY`. `DIRECTION_CONFLICT`
xảy ra khi candidate BUY và SELL cao nhất đồng thời thỏa tất cả điều kiện sau:

- protective zone và H4 cha đang hoạt động;
- Grade A hoặc B;
- kế hoạch đã xét cản H4/D1, Entry không nằm trong cản, giá hợp lệ và R:R đạt `min_rr`;
- giá nằm trong phạm vi `0.50 × ATR` của cả hai entry zone;
- dữ liệu an toàn.

Hai điều kiện D1 bias và premium/discount không tham gia phát hiện conflict.
Cả hai candidate giữ `WATCHING`; thiên hướng D1 không tự chọn một bên khi
conflict vẫn tồn tại.

Supply và Demand giao nhau không bị xóa tự động. Mỗi vùng giữ vòng đời riêng,
nhưng vùng nằm trong khu vực giao nhau không được tạo `READY` cho đến khi xung
đột hướng được giải quyết.

Conflict được giải quyết khi chỉ còn tối đa một phía thỏa các điều kiện trên,
do vùng phía kia broken, expired, kết thúc retest, mất chất lượng, mất R:R, ra
khỏi phạm vi theo dõi hoặc không còn dữ liệu hợp lệ. Sau đó phía còn lại vẫn
phải thỏa thiên hướng D1 và toàn bộ công thức `READY`; riêng việc D1 đổi hướng
không đủ để xóa conflict.

## 16. Dữ liệu không an toàn

Toàn bộ timestamp được chuẩn hóa sang UTC tại adapter. Timezone hệ điều hành và
timezone hiển thị không tham gia tính toán. D1/H4/H1/M15 giữ nguyên biên nến do
nguồn MT5 cung cấp; SD không tự ghép lại nến theo giờ địa phương.

Nguồn chuẩn về giờ mở cửa là `SDSessionPolicy` theo symbol, được khai báo trong
cấu hình SD bằng timezone IANA, giờ mở/đóng tuần và các khoảng nghỉ hằng ngày.
Timestamp từ API Python MT5 đã ở UTC, không dịch thêm broker offset. Chỉ
chuyển timezone khi nguồn thực sự trả giờ địa phương có convention rõ.
Không có session policy hợp lệ cho symbol thì dữ liệu không an toàn.

Lịch chia nến broker độc lập với lịch mở thị trường. `close_time` là biên
kết thúc kỳ `[open, close)` theo lịch đã xác thực, không phải tick cuối;
không suy từ open kế tiếp qua gap hoặc mặc định open + duration cho mọi
nến cắt phiên/DST. Giữ nến ngắn thật của nguồn; giờ nghỉ trong H4/D1 không
tự cắt kỳ. Lưu provenance, hiệu lực và revision theo source/symbol/timeframe;
dùng cùng lịch cho watermark, ID, tuổi/stale và M15 window. Thiếu lịch/close
time đáng tin cậy: `DATA_CANDLE_BOUNDARY_UNRESOLVED`, chặn READY symbol đó.
Convention broker thực tế được kiểm tra khi triển khai, chưa xác nhận chỉ
bằng việc đồng bộ tài liệu.

Profile mặc định:

| Nhóm | Timezone | Phiên mặc định |
|---|---|---|
| Forex | `America/New_York` | Chủ nhật 17:00 đến thứ Sáu 17:00, không có nghỉ ngày |
| Kim loại | `America/New_York` | Chủ nhật 18:00 đến thứ Sáu 17:00; nghỉ 17:00–18:00 từ thứ Hai đến thứ Năm |
| Crypto | `UTC` | 24 giờ mỗi ngày, 7 ngày mỗi tuần |

Profile có thể ghi đè theo symbol để khớp broker cá nhân. Thay đổi profile có
hiệu lực từ lần phân tích kế tiếp trên cả dữ liệu đã tải, xóa kết quả safety đã
cache và buộc mọi vùng đang lưu được đánh giá lại trước khi có thể `READY`.

Một khoảng thiếu nến là gap trong phiên nếu thời gian giữa hai open time lớn
hơn duration của timeframe cộng `candle_time_tolerance_seconds` và khoảng bị
thiếu chứa ít nhất một biên nến mà `SDSessionPolicy` đánh dấu thị trường mở.
Khoảng thị trường đóng không phải gap dữ liệu.

Độ cũ của nến được đo bằng số biên đóng nến kỳ vọng trong phiên, không dùng
thời gian lịch. Dữ liệu stale khi đã đi qua hai biên đóng kỳ vọng mà chưa có nến
đã đóng mới.

Không tạo `READY` khi:

- thiếu một trong các timeframe bắt buộc hoặc chưa tính đủ context vùng D1;
- chưa xác định được lịch biên/close time của nguồn;
- nến sai thứ tự thời gian hoặc OHLC không hợp lệ;
- giá Bid/Ask hiện tại không có hoặc không dương;
- spread không có, không dương hoặc lớn hơn 10% khoảng Entry–SL;
- nến cuối đã đóng bị stale theo quy tắc trên;
- dữ liệu chứa gap chưa được phân loại là thời gian thị trường đóng cửa.

Khi dữ liệu không an toàn, giữ vùng đã lưu nhưng trạng thái setup tối đa là
`WATCHING` và phải kèm lý do cụ thể.

## 17. Parameter registry

Mọi tham số dưới đây thuộc namespace `sd`. Min/max là giới hạn validation bao
gồm hai đầu. Giá trị ngoài giới hạn làm cấu hình không hợp lệ; không tự clamp.

### 17.1 Dữ liệu và pattern

| Tên | Đơn vị | Mặc định | Min | Max |
|---|---|---:|---:|---:|
| `min_candles_per_timeframe` | nến | 100 | 30 | 5000 |
| `atr_period` | nến | 14 | 5 | 100 |
| `atr_warmup_bars` | True Range | 200 | 50 | 5000 |
| `epsilon_atr_ratio` | ATR | 0.01 | 0 | 0.10 |
| `epsilon_min_ticks` | tick | 1 | 1 | 10 |
| `leg_min_bars` | nến | 1 | 1 | 3 |
| `leg_max_bars` | nến | 3 | 1 | 10 |
| `leg_min_net_move_atr` | ATR | 1.00 | 0.25 | 5.00 |
| `leg_min_directional_range_ratio` | tỷ lệ | 0.60 | 0.50 | 1.00 |
| `leg_min_body_ratio` | tỷ lệ | 0.60 | 0.10 | 1.00 |
| `base_min_bars` | nến | 1 | 1 | 4 |
| `base_max_bars` | nến | 4 | 1 | 4 |
| `base_max_candle_range_atr` | ATR | 0.80 | 0.10 | 3.00 |
| `base_max_body_ratio` | tỷ lệ | 0.50 | 0.05 | 1.00 |
| `base_max_cluster_width_atr` | ATR | 1.20 | 0.10 | 5.00 |
| `base_min_overlap_ratio` | tỷ lệ nến | 0.50 | 0 | 1.00 |
| `base_max_gap_atr` | ATR | 0.10 | 0 | 1.00 |
| `departure_min_move_atr` | ATR | 1.50 | 0.50 | 6.00 |
| `departure_breakout_atr` | ATR | 0.10 | 0 | 1.00 |
| `departure_max_base_reentry_ratio` | tỷ lệ base | 0.50 | 0 | 1.00 |
| `departure_min_body_ratio` | tỷ lệ | 0.65 | 0.10 | 1.00 |
| `duplicate_confirmation_window_bars` | nến | 3 | 0 | 20 |
| `duplicate_min_overlap_ratio` | tỷ lệ | 0.80 | 0.50 | 1.00 |
| `zone_max_width_atr` | ATR | 1.20 | 0.10 | 5.00 |
| `zone_min_width_ticks` | tick | 2 | 1 | 20 |

### 17.2 Cấu trúc, đa khung và vòng đời

| Tên | Đơn vị | Mặc định | Min | Max |
|---|---|---:|---:|---:|
| `swing_left_bars` | nến | 2 | 1 | 10 |
| `swing_right_bars` | nến | 2 | 1 | 10 |
| `d1_structure_lookback_bars` | nến D1 | 250 | 20 | 2000 |
| `discount_position_max` | tỷ lệ range | 0.45 | 0 | 0.50 |
| `premium_position_min` | tỷ lệ range | 0.55 | 0.50 | 1.00 |
| `nested_min_overlap_ratio` | tỷ lệ H1 | 0.80 | 0.50 | 1.00 |
| `break_wick_buffer_atr` | ATR | 0.20 | 0 | 2.00 |
| `zone_max_age_d1_bars` | nến D1 | 120 | 20 | 500 |
| `d1_h4_min_overlap_ratio` | tỷ lệ độ rộng H4 | 0.80 | 0.50 | 1.00 |
| `d1_obstacle_near_atr` | current ATR H4 | 0.50 | 0 | 2.00 |
| `zone_max_age_h4_bars` | nến H4 | 120 | 10 | 2000 |
| `zone_max_age_h1_bars` | nến H1 | 240 | 10 | 5000 |
| `departure_swing_lookback_bars` | nến cùng TF | 60 | 5 | 500 |
| `m15_swing_lookback_bars` | nến M15 | 40 | 5 | 500 |

### 17.3 Chất lượng, entry và kế hoạch

| Tên | Đơn vị | Mặc định | Min | Max |
|---|---|---:|---:|---:|
| `quality_departure_mid_atr` | ATR | 2.00 | 1.50 | 5.00 |
| `quality_departure_high_atr` | ATR | 2.50 | 1.50 | 6.00 |
| `quality_base_compact_max_bars` | nến | 2 | 1 | 4 |
| `quality_base_narrow_width_atr` | ATR | 0.60 | 0.10 | 1.20 |
| `quality_base_small_body_ratio` | tỷ lệ | 0.35 | 0.05 | 0.50 |
| `quality_rr_mid` | R | 2.50 | 1.00 | 10.00 |
| `quality_rr_high` | R | 3.00 | 1.00 | 15.00 |
| `quality_grade_a_min` | điểm | 85 | 70 | 100 |
| `quality_grade_b_min` | điểm | 70 | 1 | 99 |
| `h4_entry_proximal_ratio` | tỷ lệ vùng | 0.50 | 0.10 | 1.00 |
| `watch_distance_atr` | ATR | 0.50 | 0 | 5.00 |
| `m15_confirmation_max_bars` | nến M15 | 8 | 1 | 50 |
| `rejection_min_body_ratio` | tỷ lệ | 0.20 | 0.01 | 1.00 |
| `rejection_min_body_atr` | ATR M15 | 0.10 | 0 | 2.00 |
| `rejection_min_wick_body_ratio` | wick/body | 1.00 | 0 | 10.00 |
| `sl_buffer_atr` | formation ATR protective zone | 0.10 | 0 | 2.00 |
| `sl_buffer_min_ticks` | tick | 2 | 1 | 20 |
| `min_risk_ticks` | tick | 2 | 1 | 20 |
| `min_rr` | R | 2.00 | 1.00 | 10.00 |

### 17.4 An toàn dữ liệu

| Tên | Đơn vị | Mặc định | Min | Max |
|---|---|---:|---:|---:|
| `max_spread_risk_ratio` | tỷ lệ Entry–SL | 0.10 | 0 | 0.50 |
| `data_stale_expected_bars` | biên đóng nến | 2 | 1 | 10 |
| `candle_time_tolerance_seconds` | giây | 1 | 0 | 60 |
| `analysis_poll_seconds` | giây | 5 | 1 | 60 |

Ràng buộc chéo:

```text
leg_min_bars <= leg_max_bars
base_min_bars <= base_max_bars
atr_period <= atr_warmup_bars
discount_position_max < premium_position_min
departure_min_move_atr <= quality_departure_mid_atr
quality_departure_mid_atr < quality_departure_high_atr
min_rr <= quality_rr_mid < quality_rr_high
quality_grade_b_min < quality_grade_a_min
quality_base_compact_max_bars <= base_max_bars
quality_base_narrow_width_atr <= base_max_cluster_width_atr
quality_base_narrow_width_atr <= zone_max_width_atr
quality_base_small_body_ratio <= base_max_body_ratio
```

Điểm thành phần tại mục 11 là hằng số của `sd-rules-v1`, không phải cấu hình
người dùng. Sau khi bộ quy tắc được chốt lần đầu, thay đổi điểm phải tạo phiên
bản rules mới theo quy định bên dưới.

Chuỗi rules version chính xác của tài liệu này là `sd-rules-v1`.
`DRAFT` là trạng thái tài liệu riêng, không thuộc chuỗi version và không được đưa
vào canonical ID. Runtime chỉ được dùng tài liệu đã chuyển sang `APPROVED`.

`APPROVED` nghĩa là chủ ứng dụng, trong vai trò PO, đã chốt bộ quy tắc để sử
dụng cá nhân; không có nghĩa đã chứng minh lợi nhuận, có lịch sử test hay đạt
điều kiện phát hành thương mại. Không yêu cầu báo cáo backtest, forward demo
hoặc benchmark làm điều kiện chốt quy tắc. Khi triển khai vẫn kiểm tra logic
quan trọng và vận hành trực tiếp trên máy cá nhân theo `01`, mục 6–7.

Chủ ứng dụng có thể điều chỉnh tham số trong giới hạn hợp lệ sau khi sử dụng;
việc áp dụng cấu hình và tái dựng theo mục 16, 18.4–18.5. Chọn giá trị cấu hình
cá nhân trong registry không tự tạo phiên bản rules mới; sửa công thức hoặc
registry đã chốt thì áp dụng quy định tăng version bên dưới. Không tối ưu tham
số tự động hoặc ngầm coi giá trị mặc định là đã được kiểm chứng hiệu quả.

Sau lần `APPROVED` đầu tiên, phải tăng version (`sd-rules-v2`, `sd-rules-v3`,
...) khi thay đổi quy tắc phát hiện, biên vùng, vòng đời, scoring, lựa chọn setup,
điều kiện `READY`, giá trị mặc định/giới hạn tham số, session policy hoặc trường
canonical ID. Khi còn `DRAFT`, nội dung được phép hoàn thiện mà không tăng
version vì chưa được chạy. Sửa chính tả, diễn đạt hay refactor không đổi kết quả
không làm tăng version.

## 18. Contract dữ liệu tối thiểu

Mục này chỉ chốt các định nghĩa mà Trading Rules phụ thuộc. Kiểu Python, file
lưu, schema JSON và API cụ thể thuộc `03-technical-design.md`.

Yêu cầu màn hình tối thiểu theo `01`, `SD-NFR-11`: hỗ trợ cả 1366 × 768 scale
100% và Full HD 1920 × 1080 scale 150%. UI thích ứng theo `04` nhưng vẫn phải
cho xem đầy đủ giá, điểm thành phần, vùng/context, mode, trạng thái và lý do
do core cung cấp. Tab/thu gọn/cuộn hoặc scale không được làm mất trường, giảm
độ chính xác nghiệp vụ, đổi gate READY, ID hoặc cảnh báo. Đây là yêu cầu trình
bày, không thêm tham số vào registry `sd` và không làm tăng rules version.

### 18.1 Registry thực thể

| Thực thể | Trường bắt buộc tối thiểu |
|---|---|
| Zone | `zone_id`, `canonical_symbol`, `timeframe`, `side`, `pattern`, `base_start_time`, `confirmation_time`, `proximal`, `distal`, `formation_atr`, `state`, `retest_count`, `rules_version` |
| Setup | `setup_id`, `source_zone_id`, `protective_zone_id`, `h4_parent_zone_id`, `entry_mode`, `entry_touch_latched`, `first_retest_id`, `entry_touch_evidence_id`, `entry_low`, `entry_high`, `entry`, `sl`, `tp`, `rr`, `opposing_zone_id`, `opposing_timeframe`, `quality_score`, `state`, `reason_codes`, `rules_version` |
| Retest | `retest_id`, `zone_id`, `ordinal`, `started_at`, `ended_at`, `mitigation`, `start_source` |
| D1 context | `status`, `aligned_d1_zone_id`, `nearest_d1_opposing_zone_id`, `entry_to_d1_obstacle_distance`, `reason_codes` |
| Replay evidence | Event ID/order, entity refs, source/received time và precision, Bid/Ask tại sự kiện, candle refs, config/session/data revisions và đầu vào truy xuất được theo mục 18.5 |
| Alert ledger | `alert_key`, `setup_id`, `retest_id`, `event`, `first_emitted_at`, `detection_source`, payload tại sự kiện |

`side` chỉ nhận `DEMAND` hoặc `SUPPLY`; `timeframe` chỉ nhận `D1`, `H4`, `H1`
hoặc `M15`; `entry_mode` chỉ nhận `TOUCH` hoặc `M15_CONFIRMATION`.
`start_source` chỉ nhận `LIVE_TICK`, `CLOSED_CANDLE` hoặc `RESTORE`.

Zone state:

```text
FRESH | RETESTING | TESTED | BROKEN | EXPIRED
```

`TESTED` chỉ hợp lệ cho D1; H4/H1 hết hạn sau retest đầu.

Setup state:

```text
DETECTED | WATCHING | READY | INVALIDATED | EXPIRED
```

### 18.2 Định danh ổn định

Trước khi tạo ID, symbol broker phải được đổi sang `canonical_symbol` dạng chữ
hoa có dấu `/`, ví dụ `EUR/USD`. Giá được đổi sang số nguyên tick:

```text
price_ticks = floor(price / tick_size + 0.5)
```

Canonical input của zone:

```text
["sd-zone-id-v1", rules_version, canonical_symbol, timeframe, side,
 confirmation_time_utc_iso_z, distal_ticks, proximal_ticks]
```

`confirmation_time_utc_iso_z` là close time của nến departure cuối, chuẩn hóa
UTC và serialize chính xác theo `YYYY-MM-DDTHH:MM:SSZ`, không có phần mili-giây.
Timestamp candle/ID có phần nhỏ hơn giây khác 0 là dữ liệu không hợp lệ,
không tự làm tròn/cắt bỏ. Quy định này không áp cho quote/touch evidence;
giữ mili giây nguồn theo mục 1.1.

Serialize thành JSON UTF-8 compact, giữ đúng thứ tự trên. Định danh:

```text
zone_id = "SDZ1-" + first_24_hex(SHA256(UTF8(canonical_json)))
```

Canonical input của setup:

```text
["sd-setup-id-v1", rules_version, source_zone_id, protective_zone_id,
 h4_parent_zone_id_or_source_zone_id]
```

```text
setup_id  = "SDS1-" + first_24_hex(SHA256(UTF8(canonical_json)))
retest_id = "SDR1-" + zone_id + "-" + ordinal
alert_key = "SDA1-" + setup_id + "-" + retest_id + "-READY"
```

Cùng dữ liệu và rules version phải tạo cùng ID sau khi restart. ID không chứa
entry mode, score, trạng thái, TP hoặc R:R vì các giá trị này có thể đổi theo
chu kỳ. Đổi grade/mode không đổi setup ID, first retest ID hoặc alert key;
không reset terminal/cửa sổ/ledger khi đổi config hoặc restart. Thay canonical
input trong bản DRAFT chưa chạy này không tự tăng rules version, nhưng phải
cập nhật fixture ID; snapshot theo canonical input cũ không được tin dùng.

### 18.3 Reason-code registry

Reason codes là enum đóng; không phát sinh chuỗi tự do trong core:

| Nhóm | Reason codes |
|---|---|
| Dữ liệu | `DATA_SYMBOL_UNRESOLVED`, `DATA_MISSING_TIMEFRAME`, `DATA_INVALID_OHLC`, `DATA_TIMESTAMP_INVALID`, `DATA_ATR_INSUFFICIENT`, `DATA_TICK_SIZE_MISSING`, `DATA_QUOTE_MISSING`, `DATA_SPREAD_INVALID`, `DATA_STALE`, `DATA_SESSION_POLICY_MISSING`, `DATA_SESSION_GAP`, `DATA_CANDLE_BOUNDARY_UNRESOLVED` |
| Pattern | `AMBIGUOUS_ARRIVAL`, `INVALID_ARRIVAL`, `INVALID_BASE`, `INVALID_DEPARTURE`, `ZONE_TOO_WIDE`, `ZONE_TOO_NARROW`, `DUPLICATE_ZONE` |
| Đa khung | `D1_BIAS_UNALIGNED`, `LOCATION_UNALIGNED`, `H4_PARENT_MISSING`, `H4_PARENT_BROKEN`, `H4_PARENT_EXPIRED`, `DIRECTION_CONFLICT`, `D1_ZONE_ALIGNED`, `D1_ZONE_UNALIGNED`, `D1_OPPOSING_ZONE_NEAR` |
| Vòng đời | `ENTRY_NOT_REACHED`, `PROTECTIVE_ZONE_BROKEN`, `PROTECTIVE_ZONE_EXPIRED`, `FIRST_RETEST_COMPLETED` |
| Xác nhận | `M15_CONFIRMATION_REQUIRED`, `M15_CONFIRMATION_TIMEOUT`, `M15_REJECTION`, `M15_ENGULFING`, `M15_MICRO_BOS` |
| Kế hoạch | `QUALITY_BELOW_MIN`, `OPPOSING_ZONE_MISSING`, `INVALID_TRADE_GEOMETRY`, `RR_BELOW_MIN`, `ENTRY_INSIDE_OPPOSING_ZONE` |
| Khôi phục | `STATE_SNAPSHOT_INVALID`, `RULES_VERSION_MISMATCH`, `ZONE_NOT_RECONSTRUCTED`, `FULL_ANALYSIS_PENDING`, `STATE_RESTORED` |
| Kết quả | `READY` |

Một setup có thể có nhiều reason code. `reason_codes` phải được sắp theo thứ tự
nhóm trong bảng rồi theo tên tăng dần để output xác định. Trạng thái vẫn tuân
theo ưu tiên tại mục 14.1; reason code không được tự thay đổi trạng thái.

### 18.4 Cadence phân tích

- Khởi động ứng dụng ở IDLE; chỉ đọc inbox. Start hoặc Refresh mới tải lịch
  sử/restore và full analysis trước khi cho phép READY hiện tại.
- Start chạy poll sau restore; Refresh ở IDLE chạy một lần rồi về IDLE,
  Refresh lúc đang chạy yêu cầu full analysis theo single-flight. Stop hủy
  generation chưa commit, giữ history/ledger; đổi màn hình không dừng theo dõi.
- Mỗi `analysis_poll_seconds`: lấy quote và kiểm tra có nến mới đóng hay không.
- Không có nến mới: cập nhật touch/retest theo tick, vị trí theo current price,
  khoảng cách và nhãn cản D1, spread/data safety cùng quality/mode/state phụ
  thuộc các giá trị đó; không dùng tick để tạo pattern hoặc broken.
- Có nến mới ở bất kỳ timeframe nào: chạy lại phần phụ thuộc timeframe đó;
  cập nhật lifecycle, quality, target, R:R, conflict và setup state.
- Pattern D1/H4/H1/M15 chỉ được tính lại từ nến đã đóng; tick không được tạo
  pattern, swing, broken hoặc xác nhận M15.
- Khi session đóng: không poll quote để đổi trạng thái; tuổi và stale không
  tăng trong các biên nến ngoài session.

### 18.5 Khôi phục sau restart

Tái dựng state từ nến và evidence đầu vào theo cấu hình đúng từng mốc; không
tin nhãn state snapshot. Evidence bền vững gồm refs zone/setup/retest; loại
source/entry touch, nguồn phát hiện và thứ tự sự kiện; source time nguyên
precision, received-at, Bid/Ask tick gây touch, ref M15 chứa touch và ref
nến fallback. Giữ rules/scope, config/session revision với nội dung truy
xuất được, watermarks/data revisions, sự kiện đổi mode ảnh hưởng timeout và
đầu vào quote/nến/context/plan/grade để tái tính. Grade/mode lưu kèm chỉ để
đối chiếu, không dùng thay replay. Không bắt buộc lưu toàn bộ tick feed.

Snapshot/evidence/ledger commit cùng cycle. Ledger là lịch sử thông báo,
không cung cấp READY/EXPIRED hoặc plan cho core. Config mới áp dụng cho
đánh giá hiện tại, không viết lại terminal đã xảy ra với config cũ; giữ
evidence/config cũ cần chứng minh terminal.

Mức sàn nến đóng cần tải (adapter được tải thêm):

```text
zone_history(tf) = zone_max_age_<tf>_bars +
                   leg_max_bars + base_max_bars + leg_max_bars +
                   departure_swing_lookback_bars +
                   swing_left_bars + swing_right_bars + atr_warmup_bars + 1

D1 = max(min_candles_per_timeframe,
         d1_structure_lookback_bars + swing_left_bars + swing_right_bars,
         atr_warmup_bars + 1, zone_history(D1))
H4/H1 = max(min_candles_per_timeframe, zone_history(H4/H1))
M15 = max(min_candles_per_timeframe,
          m15_confirmation_max_bars + m15_swing_lookback_bars +
          swing_left_bars + swing_right_bars + atr_warmup_bars + 1)
```

`+1` là close trước True Range đầu; không bỏ departure swing lookback hoặc
warmup. Default: **D1 = 395, H4 = 395, H1 = 515, M15 = 253 nến đóng**.

M15 phải phủ mốc sớm nhất cần tìm entry touch cộng warmup ATR, swing lookback
và nến hai phía, kéo tới hiện tại để tái dựng confirmation/timeout/retest.
Có khoảng offline hoặc chưa biết touch: mở rộng từ confirmation của source
zone liên quan, không chỉ từ touch đã lưu có thể muộn hơn fallback lịch sử.
Các timeframe khác cũng tải thêm nếu việc tái tính grade/mode tại sự kiện
cần dữ liệu cũ. 253 M15 là sàn, không phải giới hạn replay.

Quy trình:

1. Load snapshot, evidence/config history và ledger; giữ FULL_ANALYSIS_PENDING.
2. Schema/rules mismatch: bỏ snapshot nghiệp vụ, giữ bản chẩn đoán, ghi
   STATE_SNAPSHOT_INVALID/RULES_VERSION_MISMATCH; giữ ledger hợp lệ. Không
   âm thầm bỏ evidence cũ cần chứng minh terminal rồi tạo cơ hội mới.
3. Tải lịch sử đủ mốc replay, chạy theo thời gian với input/config tại từng
   sự kiện; không lấy quote hiện tại để dựng grade/mode quá khứ.
4. Ghép ID, tái dựng latch, mode, M15 timeout và state cuối. Timeout/terminal
   không bị xóa bởi config mới hoặc mất khỏi cửa sổ cache.
5. Lịch sử/evidence chưa đủ: giữ FULL_ANALYSIS_PENDING và chặn READY symbol
   đó, nêu phần thiếu; vùng thực sự không tái dựng được xử lý EXPIRED với
   ZONE_NOT_RECONSTRUCTED. Không tạo vùng giả hoặc retest mới để thay thế.
6. Trong replay không phát READY/popup/âm thanh. Sau full analysis không lỗi,
   thoát replay và đánh giá **hiện tại** riêng với quote an toàn.
7. Hiện còn đủ READY, key chưa có: commit một sự kiện hiện tại có
   `detection_source = RESTORE_CURRENT`, không backdate. Không phụ thuộc nhãn
   READY tạm trong RAM sau replay; dùng cùng transaction/dedup như live.
8. Key đã có thì giữ sự kiện cũ; nếu chỉ đủ READY trong quá khứ mà hiện không
   còn đạt thì không phát bù. RESTORE_CURRENT chỉ là metadata cảnh báo,
   không phải state hoặc reason code mới.

Popup mới sau commit; reload inbox không phát lại popup/âm thanh. Không
tuyên bố hiệu ứng UI có delivery exactly-once; sự kiện durable tra được
trong inbox. Kiểm tra bằng dữ liệu giả lập touch cũ hơn sàn, timeout trước
restart, mode/config đổi, evidence thiếu và crash trước/sau commit.
