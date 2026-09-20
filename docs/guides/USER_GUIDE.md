# Hướng dẫn sử dụng AIMarketAnalyst

## Mục lục

1. [Introduction (Giới thiệu)](#1-introduction-giới-thiệu)
2. [Setup & Launch (Cài đặt và khởi chạy)](#2-setup--launch-cài-đặt-và-khởi-chạy)
3. [Scanner (Bộ quét)](#3-scanner-bộ-quét)
4. [Journal (Nhật ký)](#4-journal-nhật-ký)
5. [Auto-trade (Giao dịch tự động)](#5-auto-trade-giao-dịch-tự-động)
6. [Diagnostics (Chẩn đoán)](#6-diagnostics-chẩn-đoán)
7. [Settings (Cài đặt)](#7-settings-cài-đặt)
8. [Troubleshooting (Khắc phục sự cố)](#8-troubleshooting-khắc-phục-sự-cố)

## 1. Introduction (Giới thiệu)

(Đang cập nhật)

## 2. Setup & Launch (Cài đặt và khởi chạy)

(Đang cập nhật)

## 3. Scanner (Bộ quét)

(Đang cập nhật)

> Ứng dụng hiện chạy Scanner. Đây là thiết kế đã được phê duyệt và là hành vi
> runtime hiện hành. Location đã được nối sau H01/H02 và R5 đã được Tech Lead duyệt ngày 10/09/2026;
> xem
> [`scanner-architecture.md`](../scanner/scanner-architecture.md).

### 3.1 Location nâng cấp — đã nối runtime, R5 đã duyệt

**Trạng thái 10/09/2026: runtime đã nối, Tech Lead đã duyệt R5 sau review lại.**
Chi tiết kỹ thuật tại [Scanner architecture](../scanner/scanner-architecture.md), mục Location runtime.

Location cho biết giá close H1 có gần vùng H4 hỗ trợ hướng giao dịch
và còn khoảng trống tới vùng cản hay không. Trong chi tiết Scanner, người dùng
sẽ xem điểm 0–25, phần đóng góp vào điểm kỹ thuật, vùng tham chiếu, khoảng cách
theo ATR và lý do chấm điểm.

- Điểm thấp/0 có thể do không có vùng phù hợp, giá xa vùng hoặc đang ở vùng
  cản. “Không đủ dữ liệu” là trạng thái khác, không phải điểm 0.
- Điểm cao chỉ phản ánh vị trí theo dữ liệu đang xét; vẫn cần xem Momentum,
  Trend, SMC, macro/safety và plan entry/SL/TP. Close H1 có thể khác giá entry.
- Điểm kỹ thuật, hướng ưu tiên và thứ hạng có thể đổi sau nâng cấp. Tính năng
  không tự đóng lệnh đang mở hoặc sửa SL/TP, và không bảo đảm lợi nhuận.
- Bản lưu cũ giữ nguyên điểm. Nếu chưa có detail Location, giao diện sẽ báo
  rõ thay vì tính lại lịch sử bằng công thức mới.
- Bản runtime hiện chưa được nghiệm thu bằng smoke production; smoke hiện có
  chỉ intent-only, không gửi lệnh thật và không thay thế review R5.

Không cần nhập vùng hoặc tin thủ công để sử dụng Location bản đầu; không cần
đăng ký nguồn dữ liệu trả phí hay cài database mới riêng cho phần này.

### 3.2 Vùng SMC — đọc điểm, trạng thái và lý do chưa vào lệnh

**Trạng thái 17/09/2026: đã nối vào Scanner, màn chi tiết và Chart; đang được
kiểm chứng kỹ thuật, chưa nghiệm thu để thay bản đang dùng và chưa tự động vào
lệnh.**

#### Vùng SMC là gì

SMC là lớp đọc **cấu trúc thị trường** trên các khung lớn (D1/H4/H1). Từ cấu
trúc đó, ứng dụng tìm ra những **vùng giá** mà trước đây thị trường đã có phản
ứng rõ — vùng đối ứng của một nhịp đẩy mạnh, khoảng trống giá, hoặc vùng
cung/cầu. Ứng dụng chọn ra **một vùng cho hướng MUA và một vùng cho hướng BÁN**,
rồi theo dõi xem giá có quay lại và phản ứng hay không.

Vùng SMC không phải lệnh chờ đặt sẵn và không phải khuyến nghị. Nó là **hồ sơ
đang được theo dõi**, kèm lý do rõ ràng cho từng bước.

#### Điểm SMC và bốn thành phần B/Q/L/C có nghĩa là gì

Trong màn chi tiết, mục **SMC** hiển thị **Điểm SMC** trên thang `0–15`, và bảng
**Thành phần SMC** hiển thị bốn thành phần `B · Q · L · C`, mỗi thành phần trong
khoảng `0–1`:

| Thành phần | Nghĩa |
|---|---|
| **B** | Cấu trúc thị trường quanh vùng |
| **Q** | Chất lượng của chính vùng đó |
| **L** | Bằng chứng thanh khoản liên quan tới vùng |
| **C** | Bối cảnh khung lớn đi kèm vùng |

**Đây là thang chất lượng của hồ sơ vùng — mức độ đầy đủ và đáng tin của bằng
chứng đang có. Không phải xác suất thắng, không phải tỷ lệ thành công, không
phải phần trăm lợi nhuận và không phải dự báo giá.** Điểm cao nghĩa là hồ sơ
vùng chỉn chu hơn về mặt dữ liệu, không có nghĩa là lệnh này sẽ thắng.

Hai kết quả trông có vẻ giống nhau nhưng khác hẳn nhau — và ứng dụng ghi rõ
bằng chữ, không để bạn tự đoán:

- **`0/15 · chưa có setup hợp lệ`** — đã xét đủ dữ liệu và kết luận không có
  vùng nào đạt. Đây là **một kết luận**.
- **`Thiếu dữ liệu`** — chưa đủ dữ liệu để kết luận, nên **không** cho điểm.
  Đây **không phải** điểm thấp.
- **`Chưa có dữ liệu SMC`** — dòng này chưa từng có kết quả SMC nào.

Trong bảng **Thành phần SMC**, ô nào không có số sẽ hiển thị `—` (đúng nghĩa
"không có giá trị"), khác hẳn với số `0` (có giá trị và giá trị đó bằng 0).

Bạn không cần — và không nên — chỉnh các ngưỡng phía sau những con số này. Không
có màn hình chỉnh hàng loạt cho chúng.

#### Các trạng thái bạn sẽ gặp

Màn chi tiết có **ba ô trạng thái riêng biệt**, và chúng trả lời ba câu hỏi khác
nhau. Đừng đọc ô này bằng nghĩa của ô kia:

**Ô "Trạng thái" — vùng này có dùng được để vào lệnh không?**

| Trạng thái hiển thị | Nghĩa | Bạn cần làm gì |
|---|---|---|
| **Đã chọn được vùng** | Đã chọn được một vùng để xét | Xem tiếp các ô còn lại |
| **Theo dõi vùng** / **Theo dõi vùng, chưa có kế hoạch** | Vùng hợp lệ nhưng chưa đủ điều kiện; chưa dựng được kế hoạch | Quan sát; không có gì để đặt |
| **Chờ xác nhận** | Giá đã vào vùng, đang chờ tín hiệu xác nhận trên khung nhỏ | Chờ; xem mục lý do để biết đang chờ gì |
| **Đủ điều kiện kiểm tra lần cuối** | Trạng thái gần nhất với "sẵn sàng" — nhưng **chưa phải lệnh** | Vẫn phải qua bước kiểm tra lại ngay trước khi gửi |
| **Thiếu dữ liệu** | Chưa kết luận được vì thiếu dữ liệu đầu vào | Xem lý do; đây **không phải** điểm thấp |
| **Chưa đạt quy tắc** / **Bị chặn** | Vùng hoặc bối cảnh không thỏa điều kiện của ứng dụng | Đọc lý do cụ thể |
| **Chưa có setup hợp lệ** | Đã xét đủ dữ liệu và không có vùng nào đạt | Đây là một kết luận, không phải lỗi |

**Ô "Vòng đời vùng" — vùng đang ở bước nào của đời nó?**

| Vòng đời hiển thị | Nghĩa |
|---|---|
| **Vùng mới hình thành, chưa dùng được** | Vùng vừa được nhận diện, chưa đủ điều kiện sử dụng |
| **Vùng đã xác nhận** | Vùng đã qua bước xác nhận cấu trúc |
| **Vùng dùng được** | Vùng đang dùng được |
| **Vùng đang theo dõi** | Vùng đang được theo dõi |
| **Vùng đã bị phá** | Giá đã đóng vượt biên vùng; vùng hết giá trị |
| **Vùng đã hết hạn** | Vùng quá cũ theo thời hạn của khung thời gian |

**Ô "Xác nhận vào lệnh" — tín hiệu vào lệnh đang ở đâu?**

| Xác nhận hiển thị | Nghĩa |
|---|---|
| **Đã có xác nhận vào lệnh** | Đã có tín hiệu; vẫn còn bước kiểm tra lần cuối |
| **Đang chờ xác nhận vào lệnh** | Đã vào vùng nhưng chưa có tín hiệu |
| **Vùng chưa được kiểm tra lại** | Giá chưa quay lại vùng này |
| **Xác nhận đã bị vô hiệu** | Tín hiệu cũ bị vô hiệu; phải chờ tín hiệu mới |
| **Xác nhận đã hết hạn** | Tín hiệu cũ quá hạn; phải chờ tín hiệu mới |
| **Thiếu dữ liệu để xác nhận** | Chưa đủ dữ liệu khung nhỏ để xác nhận |

**Hai dòng không dùng được để vào lệnh:**

| Hiển thị | Nghĩa | Bạn cần làm gì |
|---|---|---|
| **Kết quả SMC theo định dạng cũ** | Dòng được lưu từ trước và không đọc được bằng quy tắc hiện hành | Chỉ xem lại lịch sử — **không dùng để vào lệnh** |
| **Không đọc được kết quả SMC đã lưu** | Phần dữ liệu đã lưu bị hỏng | Không dùng dòng này; chạy lại phân tích nếu cần |

Kết quả **lịch sử**, **thiếu dữ liệu** và **không đọc được** đều **không phải
tín hiệu live**. Ứng dụng không tính lại lịch sử bằng công thức mới và không
suy diễn một tín hiệu từ dữ liệu còn thiếu.

#### Vì sao chưa được vào lệnh — đọc phần lý do

Màn chi tiết của mỗi dòng có mục **"Vì sao chọn vùng này"**. Đây là nơi trả lời
câu hỏi "tại sao chưa vào lệnh", và nó gồm bốn nhóm thông tin. Các tên dưới đây
là đúng nhãn bạn thấy trong bảng:

1. **Vòng đời vùng** — vùng mới hình thành, đã xác nhận, đang dùng được, đang
   theo dõi, đã bị phá hoặc đã hết hạn. Một vùng đi qua các bước này theo thời
   gian; vùng bị phá hoặc hết hạn thì không quay lại trạng thái dùng được.
   Đi kèm là **Vùng được chọn** (vùng nào đang được xét) và **Mã vùng / mã
   setup** (mã kỹ thuật để tra cứu, không cần ghi nhớ).
2. **Lần giá vào vùng** — mỗi lần giá quay lại vùng là một **lần vào vùng**
   riêng, có mã riêng. Ứng dụng theo dõi hai lần vào vùng: **Lần giá vào vùng
   (vòng đời)** ở khung lớn, và **Lần vào vùng trên M15 (xác nhận vào lệnh)** ở
   khung nhỏ dùng để xác nhận. Hai lần này có thể khác nhau.
3. **Xác nhận vào lệnh** — **Loại tín hiệu xác nhận** (phá cấu trúc nhỏ, hoặc
   phản ứng tại vùng), **Thời điểm tín hiệu**, **Xác nhận lúc**, **Hiệu lực
   đến** và **Vô hiệu lúc**. Xác nhận có hạn dùng; hết hạn thì phải chờ tín
   hiệu mới.
4. **Lý do** — câu chữ cụ thể, ví dụ:
   - "Đang chờ giá quay lại vùng."
   - "Đang chờ phản ứng của giá tại vùng."
   - "M15 chưa xác nhận tín hiệu vào lệnh."
   - "Giá đã đi quá xa vùng vào lệnh, không còn phù hợp để vào lệnh."
   - "Giá lấy lại vùng theo hướng ngược, xác nhận bị vô hiệu."
   - "Vùng đã bị phá hoặc hết hạn."
   - "Thiếu dữ liệu M15 nên chưa xác nhận được."
   - "Đủ điều kiện để kiểm tra lần cuối trước khi vào lệnh."
   - "Đã xét đủ dữ liệu nhưng không có setup hợp lệ."

Nếu bạn thấy trạng thái là "Chờ xác nhận" nhưng không rõ đang chờ gì, phần lý do
là chỗ trả lời — không cần suy đoán từ biểu đồ.

#### Chart, tooltip và màn chi tiết đọc cùng một kết quả

Scanner, tooltip cột **Vị trí**, màn chi tiết và lớp SMC trên Chart đều đọc
**cùng một kết quả** của lần phân tích đó. Vì vậy:

- Điểm, vùng, trạng thái và lý do ở ba nơi phải khớp nhau. Nếu chúng khác nhau,
  hãy ghi lại và báo — đó là lỗi hiển thị, không phải hai quan điểm khác nhau.
- Chart chỉ vẽ lại đúng những gì kết quả đó nói: vùng đang chọn, vùng chỉ để
  theo dõi, vùng đã mất hiệu lực và các mốc thời gian của tín hiệu. Chart
  **không** tự dò vùng mới hay tự tính điểm.
- Dù trạng thái là gì, **vẫn luôn còn một bước kiểm tra lại ngay trước khi gửi
  lệnh**. "Đủ điều kiện kiểm tra lần cuối" nghĩa đúng như tên gọi: đủ điều kiện
  để *kiểm tra*, chưa phải để *gửi*.

#### Đường "Đỉnh/đáy bảo vệ" trên Chart

Khi cấu trúc thị trường của khung đang xem thật sự có một mức bảo vệ — mức mà
một nhịp đảo chiều sẽ phải phá để cấu trúc đổi hướng — Chart vẽ **một đường
nằm ngang nét đứt** ở mức đó, có nhãn:

> **Đỉnh/đáy bảo vệ**

Đường này là **mức của cấu trúc**, không phải lệnh và không phải điểm dừng lỗ.
Nó khác SL của kế hoạch vào lệnh: SL do kế hoạch giao dịch đặt, còn đường này do
cấu trúc thị trường đặt.

- Đường **chỉ xuất hiện khi có đủ bằng chứng**. Khi khung đang xem không có mức
  bảo vệ nào, ứng dụng **không vẽ gì cả** và nói rõ là chưa có — chứ không lấy
  SL, lấy biên vùng hay lấy một mức cũ nào để thay vào.
- Vì vậy **không thấy đường này là chuyện bình thường**, không phải lỗi.
- Khi bạn đổi khung thời gian (D1/H4/H1), đường này có thể đổi hoặc biến mất —
  mỗi khung có cấu trúc riêng.

#### Những điều SMC không làm

- Không tự gửi lệnh và không tự bật chế độ giao dịch tự động.
- Không tự đóng lệnh đang mở và không tự sửa SL/TP.
- Không bảo đảm lợi nhuận và không đưa ra xác suất thắng.
- Không sửa hoặc tính lại kết quả đã lưu trong lịch sử.
- Không cần bạn nhập vùng thủ công, đăng ký nguồn dữ liệu trả phí hay cài
  database riêng.

## 4. Journal (Nhật ký)

Journal lưu analysis payload và correlation adjustment tổng hợp. Với VIX theo
pair, có thể so sánh outcome theo symbol/side/regime để phát hiện drift ở mức
tổng quát, nhưng phiên bản hiện tại chưa hiển thị riêng map version, factor,
direction hoặc chính xác bao nhiêu điểm đến từ VIX modulation.

## 5. Auto-trade (Giao dịch tự động)

(Đang cập nhật)

## 6. Diagnostics (Chẩn đoán)

(Đang cập nhật)

## 7. Settings (Cài đặt)

### VIX theo độ nhạy từng cặp tiền

Mở **Cài đặt → Nâng cao** và tìm checkbox:

> VIX theo độ nhạy từng cặp tiền (Bước 7 — cần dữ liệu hiệu chuẩn cặp)

Checkbox mặc định tắt. Khi tắt, VIX dùng penalty phẳng như trước. Khi bật, ứng
dụng chỉ điều chỉnh theo pair nếu loader tìm được map độ nhạy đủ điều kiện, còn
TTL và pair đó `actionable=true`. Candidate seed/stale/lỗi bị bỏ qua để thử
bundled fallback; chỉ khi không còn eligible candidate hoặc pair neutral mới
giữ penalty phẳng.

Trước khi bật:

1. chạy và review calibration theo
   [`macro_score_architecture.md`](../macro/macro_score_architecture.md), mục
   **Bước 7 — VIX Pair Sensitivity**;
2. kiểm tra window, sample overlap, p-value, factor, Yahoo ticker/proxy và mọi
   warning;
3. xác nhận người chịu trách nhiệm chấp nhận giới hạn thống kê;
4. lưu Settings và đợi tối đa khoảng 60 giây hoặc sang chu kỳ scan tiếp theo để
   cache advanced flags được refresh.

Runner hiện có trong source checkout, không nằm trong packaged UI. Nếu chỉ có
bản `.exe` mà không có quy trình calibration do operator cung cấp, giữ checkbox
OFF.

Snapshot ngày 09/08/2026 không xác nhận JPY là safe haven trong sample: cả 7
JPY pairs và AUD/NZD đều neutral; chỉ BTC/USD, XAG/USD và XAU/USD actionable
theo raw gate. Vì vậy bật flag hiện tại không làm JPY pairs được giảm phạt.

## 8. Troubleshooting (Khắc phục sự cố)

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Đã bật VIX theo pair nhưng điểm không đổi | Cache flag chưa refresh; loader không tìm được eligible candidate; symbol non-actionable; hoặc VIX không có base penalty âm | Đợi tối đa 60 giây, kiểm tra runbook/log, map source/expiry và mức VIX; không cố sửa map bằng tay |
| JPY vẫn bị phạt như các pair khác khi VIX cao | Bản đồ độ nhạy VIX hiện tại không xác nhận direction của JPY pair | Đây là fail-safe đúng; không hardcode JPY. Giữ flat hoặc chạy lại calibration trên regime đã phê duyệt |
| Runner báo `hypothesis_not_confirmed` | Đủ dữ liệu nhưng không pair nào qua effect/significance gate | Giữ flag OFF. Runner hiện để map cũ nguyên trạng, vì vậy không coi map cũ là tiếp tục được phê duyệt |
| Bản cài đặt không có nút chạy lại VIX calibration | Runner chưa được bundle vào packaged app | Operator phải chạy từ source checkout; người dùng packaged app giữ feature OFF |
| Checkbox bật nhưng APPDATA map stale | UI chưa hiển thị source/age/reason; loader có thể dùng bundled fallback thay vì flat | Tắt flag, kiểm tra log để xác định map thực sự được dùng, chạy re-validation và review report trước khi bật lại |
