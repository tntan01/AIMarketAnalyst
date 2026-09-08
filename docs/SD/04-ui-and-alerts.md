# SD UI and Alerts

> Chủ trì: Tech Lead, đặc tả trình bày và tương tác theo quyết định PO.
> Ngày soạn: 08/09/2026. Trạng thái: `DRAFT` — chưa triển khai UI/runtime.
> Phạm vi: màn hình Supply–Demand và cảnh báo trong ứng dụng trên máy cá nhân.
> Nguồn: `01`, `02` và `03` đã đồng bộ TL-PO-01–09; rules `sd-rules-v1`
> vẫn `DRAFT`. Tài liệu này không thay đổi quy tắc nghiệp vụ hoặc quyền MT5.

## 1. Mục đích và nguồn chuẩn

Màn hình phải giúp chủ ứng dụng biết vùng nào đang được theo dõi, tại sao một
setup đủ/chưa đủ điều kiện, kế hoạch giá hiện tại là gì và sự kiện nào đã được
thông báo. Các thông tin phải đọc được ngay trong ứng dụng, không cần xem log
để hiểu kết quả thông thường.

| Nguồn | Trách nhiệm |
|---|---|
| [01 — Scope and Requirements](01-scope-and-requirements.md) | Phạm vi, yêu cầu chức năng, hành vi cá nhân và ranh giới chỉ đọc. |
| [02 — Trading Rules](02-trading-rules.md) | Điểm, vùng, lifecycle, giá, mode, latch, M15, READY và reason codes. |
| [03 — Technical Design](03-technical-design.md) | Contract kết quả, revision/generation, worker, commit, evidence và ledger. Mục 14 lưu câu trả lời PO. |
| Tài liệu này | Bố cục, nhãn, hiển thị trạng thái, hành vi thao tác, chart và thông báo. |
| [05 — Acceptance Criteria](05-acceptance-criteria.md) | Các tình huống kiểm tra chức năng khi triển khai, gồm cấu hình màn hình tối thiểu. |
| [UI Style Guide](../ui/style-guide.md) | Theme, layout token, control, icon, rich text và quy chuẩn UI chung. |

`01`/`02` thuộc PO. UI chỉ trình bày kết quả đã tính; không tự thêm gate, sửa
điểm, tính lại mức giá hoặc chuyển trạng thái setup để khớp hình thức hiển thị.
Nếu thiếu trường để trình bày, bổ sung presentation contract từ bằng chứng
core/service theo `03`; không suy diễn nghiệp vụ trong widget/JavaScript.

Trong UI, `READY` được gọi là **Đủ điều kiện**, kèm ý nghĩa “theo quy tắc SD
tại thời điểm đánh giá”. Không dùng nhãn đã vào lệnh, đã khớp hoặc tỷ lệ thắng.
Không có nút gửi lệnh, order dialog hoặc liên kết kích hoạt auto-entry Scanner.

## 2. Bố cục màn hình

Route `supply_demand`, nhãn điều hướng **Cung–cầu**. Màn hình dùng shell,
theme và điều hướng của ứng dụng hiện tại.

```text
┌ Cung–cầu ─ Trạng thái theo dõi ─ [Start] [Stop] [Refresh] [Cấu hình] ┐
│ Lần đánh giá gần nhất / tiến độ / thông tin nguồn                   │
├ Watchlist ───────┬ Không gian phân tích ────────────────────────────┤
│ Tìm/chọn mã     │ Bộ lọc: Symbol · Hướng · Trạng thái                │
│ Mã · nguồn     │ Danh sách setup                                  │
│ Cập nhật/lỗi   ├──────────────────────────┬───────────────────────┤
│ [Sửa danh sách]│ Chart D1 H4 H1 M15       │ Chi tiết setup/vùng   │
│                │ Vùng và Entry/SL/TP      │ Bối cảnh · Điểm · Giá │
│                │ Chú giải / lớp hiển thị  │ Điều kiện · Lý do     │
├────────────────┴──────────────────────────┴───────────────────────┤
│ Inbox cảnh báo · Chưa đọc (n) · Bộ lọc · Danh sách / Chi tiết       │
└───────────────────────────────────────────────────────────────────┘
```

Đây là sơ đồ chức năng, không phải kích thước pixel cố định:

- Thanh điều khiển luôn nhìn thấy; thông báo lỗi không đẩy nút ra khỏi vùng
  thao tác. Hiển thị tiến độ phase/symbol, không có phần trăm giả nếu service
  không cung cấp tiến độ có thể đo.
- Watchlist ở trái; vùng phân tích ở giữa. Bảng setup và chart/detail có
  splitter để điều chỉnh diện tích, không khóa chiều rộng theo từng mã.
- Inbox nằm panel dưới, có thể thu gọn; số chưa đọc vẫn hiện khi thu gọn.
  Mở inbox không yêu cầu Start hoặc kết nối MT5 nếu store đọc được.
- Khi cửa sổ hẹp, chart và detail chuyển thành hai tab dùng chung vùng nội
  dung; watchlist có thể thu gọn. Vẫn truy cập được controls, lỗi và inbox;
  bảng cho cuộn ngang, detail cho cuộn dọc, không cắt số giá hoặc chồng chữ.
- Mặc định chọn symbol đầu trong watchlist; nếu chưa chọn setup, chart mở H4
  sau khi có dữ liệu, detail hướng dẫn “Chọn setup hoặc vùng để xem chi tiết”.
  Không tự chọn một setup BUY/SELL như khuyến nghị ưu tiên của UI.

### 2.1 Màn hình tối thiểu và scale — SD-NFR-11

Quyết định PO ngày 08/09/2026, nguồn chuẩn `01` SD-FR-09/SD-NFR-11: UI phải
chạy tốt và hiển thị đầy đủ trên **cả hai** cấu hình sau, không yêu cầu giảm
scale hệ điều hành, dùng fullscreen hoặc ẩn taskbar:

| Độ phân giải màn hình | Scale hệ điều hành | Diện tích logic trước taskbar/khung cửa sổ |
|---|---:|---|
| 1366 × 768 | 100% | Khoảng 1366 × 768 |
| Full HD 1920 × 1080 | 150% | Khoảng 1280 × 720 |

Kiểm tra cửa sổ maximized trong vùng làm việc còn lại sau taskbar, có thanh
tiêu đề và shell/điều hướng của ứng dụng. Diện tích nội dung SD nhỏ hơn số
trong bảng; không dùng kích thước màn hình làm minimum size của widget SD.

"Đầy đủ" nghĩa truy cập được mọi thông tin và thao tác qua tab/panel/cuộn;
không phải ép watchlist, setup, chart, detail và inbox cùng hiện một lúc.
Tại diện tích nhỏ, ưu tiên bố cục gọn:

- Thanh Start/Stop/Refresh, trạng thái vận hành và lối mở cấu hình/inbox luôn
  nhìn thấy. Có thể xuống hàng có kiểm soát; lỗi dài mở vùng chi tiết/cuộn,
  không đẩy controls ra ngoài. Lối mở watchlist vẫn hiện khi panel thu gọn.
- Chart và detail dùng tab chung, inbox thu gọn hoặc mở trong vùng nội dung
  phù hợp; bảng setup vẫn chọn được. Giữ selection khi chuyển tab/resize.
- Bảng có thanh cuộn ngang/dọc khi cần, cột đủ rộng để đọc đầy đủ giá khi
  cuộn đến; detail/form có cuộn dọc và wrap nhãn/lý do dài. Không chỉ dựa vào
  tooltip để đọc dữ liệu bắt buộc, không ellipsis làm mất chữ số giá.
- Chart co theo viewport; trục, nhãn giá/timeframe, chú giải và nút thao tác
  phải đọc/bấm được. Có thể mở chart riêng trong tab để đủ diện tích; không
  loại dữ liệu hoặc thay giá vì màn hình nhỏ.
- Editor watchlist, cấu hình/tham số/session, detail inbox và dialog lỗi
  đều nằm trong vùng khả dụng. Nội dung form cuộn độc lập; footer Áp dụng/Hủy
  và nút đóng luôn truy cập được bằng chuột/bàn phím, không phải kéo dialog
  ra ngoài màn hình để tìm nút. Popup tự wrap/giới hạn chiều cao, có lối mở
  đầy đủ trong inbox và nút đóng, không che controls chính đang cần thao tác.
- Giữ font/control theo style chung và scale hệ điều hành; không thu nhỏ
  chữ hoặc giảm scale chart để nhét giao diện. Dark/light đều phải đọc được,
  không chồng chữ, cắt nhãn hoặc sai vùng bấm sau scale.
- Khi resize/đổi scale hoặc mở lại geometry đã lưu, bố trí lại theo diện tích
  hiện tại; không mất dữ liệu form, selection, theo dõi nền hoặc phát lại
  popup. Không giữ geometry ngoài màn hình từ cấu hình hiển thị trước.

Hỗ trợ các cấu hình này là yêu cầu khả dụng UI của phần mềm cá nhân. Kiểm tra
trực tiếp khi triển khai bằng dữ liệu mẫu, không cần lịch sử test/benchmark.

## 3. Watchlist, cấu hình và thao tác

### 3.1 Watchlist

Watchlist khởi tạo: **EUR/USD, GBP/USD, USD/JPY, XAU/USD**. Dữ liệu cấu hình
cá nhân đã lưu được ưu tiên; danh sách rỗng được giữ nguyên, không tự khôi
phục bốn mã hoặc bật tất cả. Registry lựa chọn gồm 31 mã ứng viên theo `03`;
không áp trần cứng 8 mã.

Mỗi dòng có canonical symbol, trạng thái nguồn và thời điểm đánh giá riêng.
Broker symbol và session policy nằm trong chi tiết nguồn để chẩn đoán. Mã
không có mapping/session/data vẫn hiện với lý do; UI không gọi `symbol_select`
hoặc tự chuyển broker symbol để làm mã đó hợp lệ.

Chọn symbol chỉ đổi ngữ cảnh xem chart/detail và bộ lọc symbol. **Sửa danh
sách** mới thay tập mã được theo dõi. Lọc bảng, đổi timeframe hoặc ẩn lớp
chart không thay watchlist và không dừng phân tích symbol bị ẩn.

Editor watchlist dùng lựa chọn nhiều mã, tìm kiếm, **Áp dụng** và **Hủy**.
Áp dụng validate trước khi lưu; lỗi có thông báo cụ thể, không âm thầm clamp
hoặc loại mã. Nếu đổi hợp lệ, tăng revision/hủy generation cũ theo `03`;
giữ ledger và ý định đang chạy/IDLE. Hủy không thay cấu hình đang dùng.

### 3.2 Hành vi Start/Stop/Refresh

Nhãn nút giữ **Start**, **Stop**, **Refresh**; tooltip tiếng Việt lần lượt
“Bắt đầu theo dõi”, “Dừng theo dõi”, “Phân tích đầy đủ lại”.

| Tình huống | Start | Stop | Refresh | Kết quả người dùng thấy |
|---|---|---|---|---|
| Vừa mở ứng dụng / IDLE | Khả dụng nếu watchlist không rỗng và cấu hình hợp lệ | Vô hiệu | Khả dụng cùng điều kiện Start | Chưa tự phân tích; inbox có thể xem ngay. |
| Nhấn Start | Vô hiệu trong phiên đang chạy | Khả dụng | Có thể yêu cầu một full analysis đang chờ | Khôi phục -> phân tích đầy đủ -> theo dõi định kỳ. |
| Đang poll / ACTIVE | Vô hiệu | Khả dụng | Yêu cầu full analysis theo single-flight | Không sinh job thứ hai; chỉ một yêu cầu full đang chờ. |
| Refresh từ IDLE | Vô hiệu tới khi tác vụ hoàn tất | Hủy tác vụ một lần nếu đang chạy | Không xếp thêm tác vụ trùng | Full analysis một lần, dùng cùng quy tắc cảnh báo, rồi về IDLE. |
| STOPPING | Vô hiệu | Vô hiệu sau yêu cầu dừng đầu | Vô hiệu | “Đang dừng, chờ nguồn dữ liệu phản hồi”; UI vẫn tương tác được. |
| Watchlist rỗng | Vô hiệu | Chỉ khả dụng nếu còn tác vụ cần dừng | Vô hiệu | “Chưa chọn mã theo dõi” và nút sửa danh sách. |
| Cấu hình không hợp lệ | Vô hiệu với lý do | Dừng job nếu có | Vô hiệu với lý do | Mở cấu hình và lỗi theo trường; không chạy ngầm bằng default. |

Controller quyết định availability từ lifecycle và validation, widget không
thử gọi service nhiều lần để suy trạng thái. Nguồn MT5 chưa sẵn sàng vẫn cho
người dùng thử Start/Refresh với cấu hình hợp lệ; tác vụ báo lỗi nguồn rõ
ràng, không yêu cầu quyền trade để đọc.

Nhấn Stop dừng timer và hủy generation chưa commit, giữ history/evidence.
Đổi màn hình vẫn tiếp tục theo dõi nếu đã Start. Đóng ứng dụng đi qua shutdown
của `03`, không coi đóng màn hình SD là disconnect MT5. Một kết quả đã commit
trước Stop vẫn có thể xuất hiện trong inbox; job bị hủy trước commit không
được phát mới.

Refresh đang theo dõi không đổi ý định chạy liên tục. Nếu có yêu cầu full đang
chờ, hiển thị “Đã yêu cầu phân tích đầy đủ” và không cộng dồn lượt nhấn. Full
analysis có ưu tiên hơn pending poll. Chu kỳ mặc định 5 giây là lịch yêu cầu
cập nhật; không hiển thị cam kết kết quả mới mỗi 5 giây khi nguồn chậm.

### 3.3 Cấu hình

Trong panel cấu hình SD, nhóm **Theo dõi**, **Thông báo** và **Nâng cao**:

- Theo dõi: watchlist và chu kỳ; hiển thị tên/đơn vị/min/max từ registry `02`.
- Thông báo: **Popup trong ứng dụng** mặc định bật; **Âm thanh** mặc định tắt.
  Inbox luôn lưu khi commit sự kiện, không có công tắc “tắt inbox”.
- Nâng cao: tham số SD và mapping/session override theo `03`, hiển thị policy
  thực tế, nguồn default/override và lỗi validation. Không cho sửa trực tiếp
  ID, state, point grade, ledger hoặc đánh dấu rules APPROVED từ màn hình này.

Áp dụng thay đổi phân tích phải giữ terminal/evidence/ledger và tái phân tích
theo revision mới. Các tùy chọn thuần trình bày không tự sửa tham số nghiệp vụ
hoặc biến sự kiện cũ thành mới. Mở dialog không dừng worker; lỗi lưu giữ dialog
và dữ liệu đã nhập, không báo “Đã lưu” khi store thất bại.

## 4. Trạng thái vận hành, độ mới và dữ liệu thiếu

Phân biệt ba trục: **vận hành** của worker/service, **an toàn/độ mới** của dữ
liệu từng symbol và **trạng thái nghiệp vụ** từng setup. Không dùng một badge
“Đang chạy” để suy mọi symbol đều an toàn hoặc có READY.

| Operational status từ `03` | Nhãn UI | Hiển thị đi kèm |
|---|---|---|
| IDLE | Chưa theo dõi | Có thể xem inbox; kết quả RAM lần trước ghi “Lần đánh giá gần nhất”, không giả đang theo dõi. |
| LOADING | Đang tải dữ liệu | Symbol/timeframe/phase đang tải; vùng cũ nếu có được đánh dấu cũ. |
| RESTORING | Đang khôi phục | Đang tải/replay evidence; chưa có kết quả hiện tại đủ điều kiện. |
| ACTIVE | Đang theo dõi | Thời điểm từng symbol, phase hiện tại hoặc chờ chu kỳ tiếp theo. |
| SESSION_CLOSED | Ngoài phiên | Policy/timezone phiên; không đếm thiếu nến hoặc tăng tuổi từ đồng hồ UI. |
| DEGRADED | Hoạt động chưa đầy đủ | Phạm vi lỗi, last-good timestamp và thao tác phù hợp; ví dụ lỗi lưu cảnh báo. |
| ERROR | Có lỗi | Tác vụ/nguồn bị lỗi, thông báo đọc được và xem chi tiết; không hiển thị kết quả dở dang như hiện tại. |
| STOPPING | Đang dừng | Đã nhận yêu cầu, chờ I/O; không hứa hủy SDK tức thì. |
| SPEC_PENDING | Chưa đủ đặc tả sử dụng | Chưa bật runtime với rules DRAFT hoặc có thiếu sót đặc tả được báo cụ thể. Không gán trạng thái này chỉ vì chưa benchmark. |

D1 context PENDING do dữ liệu chưa đủ là trạng thái dữ liệu, không phải thông
báo “PO chưa chốt D1”. Lịch biên broker chưa xác minh hiển thị “Chưa xác định
được biên nến của nguồn”, timeframe/mốc liên quan, theo
`DATA_CANDLE_BOUNDARY_UNRESOLVED`.

Mỗi kết quả có **Đánh giá lúc**, **Dữ liệu đến** theo timeframe và nguồn quote.
Batch nhiều symbol không lấy timestamp mới nhất của một mã để làm mới các mã
khác. UI không tự tính lại stale/session safety; hiển thị kết luận service.

Khi generation/config/scope đổi hoặc nguồn lỗi, last-good nếu còn trong RAM
chỉ để xem với banner “Kết quả trước — đang chờ đánh giá lại” và timestamp.
Badge cũ ghi “Lần trước: Đủ điều kiện” thay vì trình bày READY hiện tại. Không
đổi state entity bằng UI để che kết quả cũ; phần đếm READY hiện tại chỉ lấy
kết quả hiện tại hợp lệ do controller cung cấp.

Sau restart, chỉ inbox/evidence theo store được đọc lại; không giả định có
snapshot plan/READY để dựng màn hình phân tích cũ. Chưa phân tích thì chart và
setup có empty state, inbox vẫn giữ kế hoạch lịch sử trong payload cảnh báo.

Giá trị `None` hiển thị **—** và lý do cạnh trường hoặc trong detail. Giá trị
0 hợp lệ như mitigation 0%, điểm thành phần 0 hoặc chưa có retest vẫn hiển
thị 0; không dùng phép kiểm tra truthiness để biến tất cả 0 thành thiếu dữ liệu.

## 5. Danh sách setup và chọn kết quả

### 5.1 Cột và bộ lọc

| Cột | Nội dung |
|---|---|
| Symbol / Hướng | Canonical symbol, BUY hoặc SELL với chữ và icon. |
| Nguồn setup | H1 trong H4 hoặc chỉ H4; phân biệt source với vùng bối cảnh D1. |
| Trạng thái | Nhãn setup ở mục 5.2; kết quả cũ luôn có nhãn thời điểm. |
| Grade / Điểm | A/B/C và tổng `/100`; không gắn `%`. |
| Mode | Chạm vùng (TOUCH) hoặc Xác nhận M15. |
| Entry / SL / TP | Giá kế hoạch cuối từ core, đã rounding; TP cho biết D1 hoặc H4. |
| R:R | Tỷ lệ tham khảo được format, kèm trạng thái đạt/chưa đạt từ core. |
| Lý do / Đánh giá lúc | Lý do chính để đọc nhanh, mở detail xem đầy đủ; timestamp riêng. |

Mặc định bộ lọc là mọi hướng/mọi trạng thái cho symbol đang chọn. Có lựa chọn
**Tất cả mã theo dõi**, BUY/SELL và từng setup state. Bộ lọc chỉ tác động bảng;
không ảnh hưởng scoring, lựa chọn READY hoặc khả năng nhận cảnh báo.

Thứ tự trong từng nhóm candidate cùng hướng giữ thứ tự core theo `02`, mục
15; UI không tự chấm hạng lại hoặc chọn BUY thay SELL khi conflict. Nếu người
dùng sort cột để xem, thể hiện rõ đây là sắp xếp bảng, không thay thứ hạng
nghiệp vụ. Cập nhật giữ selection bằng setup ID, không theo số dòng.

Đổi grade/mode giữ nguyên dòng khi setup ID giữ nguyên. Nếu dòng không còn
trong bộ lọc sau cập nhật, hiện “Setup đang chọn không thuộc bộ lọc hiện tại”
và cho mở detail; không âm thầm chuyển selection sang một setup khác. Nếu
setup không còn trong kết quả, detail báo không có kết quả hiện tại; không
tái tạo entity từ payload inbox.

### 5.2 Nhãn trạng thái setup

| State | Nhãn | Ý nghĩa hiển thị |
|---|---|---|
| DETECTED | Đã phát hiện | Có vùng/setup, chưa tới điều kiện theo dõi gần/entry theo core. |
| WATCHING | Đang theo dõi | Chưa đủ gate; hiển thị lý do cụ thể, có thể đang conflict hoặc chờ M15. |
| READY | Đủ điều kiện | Thỏa quy tắc tại as-of hiện tại; không có nghĩa đã gửi lệnh. |
| INVALIDATED | Đã vô hiệu | Protective zone hoặc H4 cha broken; trạng thái cuối. |
| EXPIRED | Đã hết hạn | Tuổi, retest đầu hoặc timeout theo mode; trạng thái cuối. |

Grade A không tự mang màu/nhãn READY. Grade C vẫn xem được. Không hiện nút
“Bật lại”, “Bỏ qua gate” hoặc “Xác nhận thủ công” để hồi sinh setup cuối.

Empty states phân biệt: chưa phân tích; không phát hiện setup; không có dòng
khớp bộ lọc; symbol lỗi/thiếu dữ liệu. Mỗi trường hợp có hành động phù hợp
(Start/Refresh, bỏ bộ lọc, xem lỗi nguồn), không cùng dùng “Không có tín hiệu”.

## 6. Biểu đồ và chi tiết vùng

### 6.1 Timeframe, lớp vùng và điều hướng

Chart có D1/H4/H1/M15, mặc định H4 khi chưa chọn setup. Chọn setup lần đầu
đưa chart tới symbol và source timeframe tương ứng; sau đó đổi timeframe là
thao tác xem và không bị mỗi poll giật về source. Có nút **Về vùng đang chọn**
để đưa viewport về vùng; không auto-pan/rezoom khi người dùng đang xem lịch sử.

Chart dùng nến đóng từ result đã kiểm tra; giá hiện tại có thể là đường quote
riêng có timestamp/nhãn Bid/Ask. Không vẽ một bar đang mở như nến đã xác nhận
hoặc dùng hình nến đang vẽ để quyết định pattern. Đổi timeframe không resample
lại biên nến theo giờ máy hoặc timezone hiển thị.

Các lớp có thể bật/tắt: **D1 bối cảnh**, **H4**, **H1**, **Vùng đã mất hiệu
lực**, **Entry/SL/TP**. Mặc định hiện vùng hoạt động liên quan setup đang chọn
và kế hoạch; nếu chưa chọn setup, hiện vùng hoạt động của timeframe hiện tại.
Hiện vùng D1 trên H1/M15 vẫn ghi rõ nhãn D1; không tạo “vùng H1” mới từ overlay.

Đối với vùng chưa được xác nhận ở đoạn lịch sử đang xem, phần vùng hoạt động
không bắt đầu trước confirmation. Có thể đánh dấu cụm base bằng marker riêng
với nhãn “Base”, không tô nó như vùng đã biết trước departure đóng. Tooltip
cho cả base time và confirmation time.

### 6.2 Biểu diễn vai trò

| Thành phần | Cách thể hiện |
|---|---|
| Demand / Supply | Fill nhẹ theo semantic buy/sell, viền và chữ Demand/Supply; không chỉ dựa vào màu. |
| Proximal / Distal | Nhãn cạnh vùng và giá; tooltip giải thích cạnh gần departure / cạnh bảo vệ đầy đủ. |
| Source zone | Viền chính, nhãn `H1 nguồn` hoặc `H4 nguồn`. |
| Entry zone | Fill/viền nhấn trong source, nhãn “Vùng entry”; chỉ phần đã rounding từ core. |
| Protective zone | Viền nét đứt cùng nhãn “Vùng bảo vệ”; distal dùng cho SL. |
| H4 cha | Nhãn “H4 cha”, liên kết từ detail tới zone; không nhầm với D1 đồng thuận. |
| D1 đồng thuận | Viền bối cảnh, nhãn “D1 đồng thuận”; hiển thị overlap nhận từ core. |
| Cản chọn làm TP | Nhấn proximal và nhãn “Cản TP · D1/H4”; nối TP với đúng zone ID. |
| Cản D1 gần riêng | Nhãn “Cản D1 gần Entry”, ngay cả khi TP chọn H4; không tự tạo TP thứ hai. |
| Entry / SL / TP | Ba đường có chữ, giá và kiểu nét phân biệt; đây là kế hoạch tham khảo. |

Cùng zone ID có nhiều vai trò thì một vùng nhận nhiều nhãn/kiểu viền, không
nhân bản thành nhiều vùng hoặc đếm lại. H1 trong H4 có thể dùng cùng toàn H1
cho source/entry/protective. Chỉ H4 dùng entry sub-zone, protective vẫn toàn
H4; không kéo SL tới distal của phần entry.

Khi cản D1 ngoài viewport, detail vẫn hiển thị giá/khoảng cách và nút **Xem
cản D1**; không ép chart thu nhỏ tới mức nến không đọc được. Vùng chồng nhau
cho chọn qua danh sách/tooltip tên khung/ID rút gọn, không tự xóa một phía.

### 6.3 Trạng thái vùng

| Zone state | Nhãn và biểu diễn |
|---|---|
| FRESH | Chưa retest; viền thường, số retest đúng dữ liệu. |
| RETESTING | Đang retest; nhấn viền, hiện ordinal và mitigation nếu có. |
| TESTED | Đã retest · D1; viền chấm, số retest. Vẫn là context/cản hợp lệ nếu core xác nhận hoạt động. |
| BROKEN | Đã phá; nét đứt/mờ và badge lý do, không vẽ như vùng hoạt động. |
| EXPIRED | Đã hết hạn; mờ và nhãn nguyên nhân tuổi/retest, phân biệt với broken. |

`TESTED` chỉ cho D1. H4/H1 retest đầu kết thúc phải thể hiện EXPIRED theo
result. Nếu payload không phù hợp enum/timeframe, báo dữ liệu trình bày không
hợp lệ; UI không tự chuyển TESTED sang FRESH hoặc áp quy tắc khác.

Chọn vùng mở detail: khung/loại/pattern, base và confirmation, proximal/distal,
độ rộng, formation ATR, tuổi theo nến, retest/mitigation, state và lý do. D1
độc lập hiển thị **Điểm hình thành x/50**, Departure x/30, Base x/20; không
grade A/B/C hoặc tổng 100. Số retest không dùng làm nhãn “mạnh hơn”.

## 7. Panel chi tiết setup

### 7.1 Thứ tự thông tin

1. **Kết quả hiện tại:** symbol, hướng, state, grade/tổng, mode, as-of và độ mới.
2. **Kế hoạch:** vùng entry, Entry/SL/TP/R:R và cản TP; nguồn/protective/H4 cha.
3. **Bối cảnh D1:** bias, vị trí/range, zone đồng thuận, cản D1 và khoảng cách
   từ Entry; trạng thái COMPLETE/PENDING của context.
4. **Điểm thành phần:** giải thích phần hình thành, tình trạng sử dụng và mức
   phù hợp; không suy xác suất thắng từ điểm.
5. **Entry và M15:** first retest, first entry touch, latch, mode và evidence.
6. **Điều kiện/lý do:** gate đạt/chưa đạt/thiếu dữ liệu, nguyên nhân terminal.
7. **Thông tin đối chiếu** thu gọn: ID, rules/config/data revision, precision
   nguồn, candle refs và liên kết sự kiện inbox liên quan nếu có.

Phần đối chiếu chỉ dành cho nhu cầu xem sâu; không đưa hash, schema hoặc
canonical input vào dòng quyết định chính của người dùng.

### 7.2 Giá và điểm

Giá hiển thị phải đủ số chữ số biểu diễn tick size và đúng giá kế hoạch từ
core; không suy tick size chỉ từ digits, không rounding lại để ra plan mới.
R:R mặc định có thể hiển thị hai chữ số thập phân, nhưng badge đạt/chưa đạt
và grade lấy từ kết quả chưa format của core.

Ví dụ R:R gốc 1.9996: bảng có thể hiện `2.00 · Chưa đạt`; detail phải cho
xem giá trị đủ chính xác và ngưỡng `min_rr` thực tế để giải thích. Không dùng
con số `2.00` đã format làm đủ điều kiện. Khi thiếu TP, TP/R:R là — và lý do
thiếu cản, không dựng TP giả hoặc hiển thị RR vô hạn.

Điểm setup hiển thị thành bảng:

| Nhóm | Thành phần |
|---|---|
| Hình thành vùng | Departure x/30, Base x/20. |
| Tình trạng sử dụng | Freshness x/20. |
| Mức phù hợp của setup | Vị trí x/15, khoảng trống tới mục tiêu x/15. |
| Tổng | x/100 và Grade A/B/C từ core. |

Không cộng điểm cho đồng thuận D1 hoặc trừ riêng vì gần cản. Khi cản làm TP
đổi, trình bày TP/R:R/điểm mới cùng as-of mới, không sửa payload cảnh báo cũ.
Không biến thiếu breakdown thành các thành phần 0 để khớp tổng.

### 7.3 Entry latch và mode động

Hiển thị tách biệt **Source đang retest** và **Đã chạm entry**. Source touch
không đủ chứng minh entry sub-zone đã chạm. Latch do core cung cấp, kèm lần
chạm đầu và ref M15; tick có mili giây được giữ trong detail đối chiếu.

| Trường hợp | Nội dung UI |
|---|---|
| Chưa entry latch | “Chưa chạm vùng entry”; không bắt đầu countdown từ source touch. |
| TOUCH có latch | “Chạm entry đã ghi nhận; không bắt buộc xác nhận M15”; các gate khác vẫn có thể chặn READY. |
| M15 đang chờ | “Chờ xác nhận M15”, nến đã đóng trong cửa sổ và giới hạn từ config; nếu core cung cấp nến hiện tại thì ghi rõ chưa đóng. |
| Có xác nhận | Loại Rejection/Engulfing/Micro BOS và candle/time evidence thực tế; không tự chọn một loại khác từ hình chart. |
| TOUCH sau cửa sổ | “Cửa sổ M15 đã kết thúc; mode TOUCH không bắt buộc xác nhận”; không tự gắn EXPIRED. |
| Đổi A -> B | Mode M15, giữ mốc/latch/ID, phản ánh WATCHING hoặc timeout hiện tại từ core. |
| Grade C | “Chất lượng chưa đạt”; mode giữ theo core, không ẩn timeout đã bắt đầu. |
| Đã terminal | Hiển thị nguyên nhân, giữ evidence để xem; không có thao tác reset cửa sổ. |

Mốc đếm dùng nến M15 đúng ref/lịch biên nguồn và cấu hình hiện tại, không dùng
đồng hồ UI đếm 8 × 15 phút lịch. Rejection đóng ngoài entry hoặc giá rời entry
khi source retest còn diễn ra không tự xóa latch. Đổi grade/mode không làm
dòng setup nhảy sang ID mới hoặc tạo notification mới bằng phía UI.

### 7.4 Bối cảnh và lý do

D1 không có đồng thuận: “Không có vùng D1 đồng thuận”, là thông tin. D1 chưa
tính đủ: “Bối cảnh D1 chưa đầy đủ”, không giả lập kết luận không có cản. Nhãn
gần cản ghi “Từ Entry đến cản D1: …”, đơn vị giá/ATR nhận từ result.

| Reason / nhóm | Diễn đạt và nơi hiển thị |
|---|---|
| D1_ZONE_ALIGNED / UNALIGNED | Có/không có đồng thuận D1; phần bối cảnh, không tự gắn fail gate. |
| D1_OPPOSING_ZONE_NEAR | Cản D1 gần Entry; thông tin, không tự đồng nghĩa bị chặn. |
| ENTRY_INSIDE_OPPOSING_ZONE | Entry nằm trong vùng cản; gate kế hoạch chưa đạt, highlight đúng cản. |
| ENTRY_NOT_REACHED | Chưa ghi nhận chạm entry; cạnh latch/cửa sổ M15. |
| M15_CONFIRMATION_REQUIRED / TIMEOUT | Chờ xác nhận hoặc đã hết cửa sổ theo mode; hiện evidence/giới hạn từ core. |
| RR_BELOW_MIN / OPPOSING_ZONE_MISSING | RR chưa đạt hoặc chưa có cản làm TP; cạnh kế hoạch. |
| DIRECTION_CONFLICT | Có thiết lập hai chiều xung đột; không tự dùng bias để chọn một bên. |
| D1_BIAS_UNALIGNED / LOCATION_UNALIGNED | Thiên hướng/vị trí chưa phù hợp; cạnh context và checklist. |
| H4_PARENT_* / PROTECTIVE_ZONE_* | Thiếu hoặc vùng cha/bảo vệ đã mất hiệu lực; liên kết đến đúng zone. |
| DATA_* | Lỗi/thiếu dữ liệu cụ thể theo symbol/timeframe; banner nguồn và detail. |
| FULL_ANALYSIS_PENDING / STATE_* / RULES_VERSION_MISMATCH | Đang/không thể khôi phục đầy đủ; không khẳng định kết quả cũ là hiện tại. |
| Pattern rejection / QUALITY_BELOW_MIN | Chi tiết phát hiện/chất lượng; không biến candidate đã loại thành READY. |

Presentation phải có nhãn cho toàn bộ enum trong `02`, mục 18.3; bảng trên là
cách nhóm, không thêm mã mới. Giữ reason codes theo thứ tự core, hiển thị đầy
đủ khi mở detail. Reason thông tin không được tô như điều kiện bắt buộc thất
bại. Mã chưa nhận biết báo “Lý do chưa được hỗ trợ” cùng mã đối chiếu và lỗi
contract, không diễn giải là đạt.

Checklist READY trình bày từng predicate của `02`, mục 14 từ core/evidence:
protective/H4 active, bias/location, grade, first retest, entry latch, M15 nếu
bắt buộc, plan, Entry ngoài cản, RR, data safety và không conflict. Badge
**Đạt / Chưa đạt / Chưa đủ dữ liệu / Không bắt buộc** dựa trên kết quả được
producer cung cấp; widget không chạy lại công thức. TOUCH cho dòng xác nhận
M15 “Không bắt buộc”, không giả rằng đã có nến xác nhận.

## 8. Inbox và nội dung cảnh báo

### 8.1 Danh sách và thao tác

Inbox lấy từ ledger cục bộ theo source scope, xếp mới nhất trước; thời điểm
bằng nhau giữ thứ tự ổn định theo alert key. Mỗi sự kiện có một dòng nhận diện
bằng key. Phân trang/tải thêm qua API `03`, không tải mọi payload vào chart.

Cột: chưa đọc/đã đọc, thời điểm phát, symbol, hướng, grade, mode, nguồn phát
hiện và tóm tắt Entry/SL/TP/R:R. Bộ lọc riêng gồm chưa đọc/tất cả và symbol;
không dùng bộ lọc setup để làm mất lịch sử inbox. Badge chưa đọc lấy từ store
trên scope hiện tại, không chỉ đếm phần danh sách đã tải.

Thao tác:

- **Xem cảnh báo:** mở payload bất biến tại sự kiện; không tự đổi kế hoạch
  sang giá hiện tại. Xem popup không tự đánh dấu đã đọc.
- **Đánh dấu đã đọc:** cập nhật receipt bền vững; lỗi ghi báo rõ và không
  giả giảm số chưa đọc. Không xóa ledger hoặc reset khóa khi đánh dấu.
- **Mở setup hiện tại:** dùng setup ID/scope, chuyển tới màn hình SD và chọn
  setup nếu result hiện tại có nó. Không tự Start, Refresh hoặc dựng state
  bằng lịch sử khi không có kết quả; hiện “Chưa có kết quả hiện tại” và cho
  người dùng chọn Start/Refresh.

Setup đã expired/invalidated/không còn trong watchlist vẫn có lịch sử inbox.
Đổi tài khoản/nguồn phải ghi rõ scope lịch sử; không ghép sự kiện broker cũ
vào setup broker mới dù symbol giống nhau. Không có nút xóa lịch sử để nhận
lại tín hiệu; retention/khóa chống lặp theo store trong `03`.

### 8.2 Payload sự kiện

Nội dung tối thiểu để người dùng hiểu và đối chiếu:

| Trường | Hiển thị |
|---|---|
| Symbol, hướng | Ví dụ `EUR/USD · BUY`. |
| Loại sự kiện | “Setup đủ điều kiện theo SD”. |
| Thời điểm phát / as-of | Tách thời điểm ghi nhận cảnh báo và thời điểm đánh giá nếu khác nhau. |
| Nguồn phát hiện | LIVE: “Theo dõi hiện tại”; RESTORE_CURRENT: “Đánh giá hiện tại sau khôi phục”. |
| Grade, điểm, mode | Tại thời điểm sự kiện; không dùng mode hiện tại để sửa quá khứ. |
| Entry/SL/TP/R:R | Giá kế hoạch tại sự kiện, giữ nguyên khi target hoặc điểm về sau đổi. |
| Source/parent/target | Khung nguồn và cản TP nếu payload có, để phân biệt H1/H4/D1. |
| Định danh đối chiếu | Setup/retest/alert key, rules/revisions trong phần thu gọn; không bắt người dùng đọc hash. |

Ví dụ template popup, mọi placeholder lấy từ event đã commit:

```text
{symbol} · {BUY/SELL} — Đủ điều kiện
Grade {grade} · {score}/100 · {mode_label}
Entry {entry}   SL {sl}   TP {tp}   R:R {rr_display}
Đánh giá lúc {as_of_display}
{live_or_restore_label}
[Xem cảnh báo] [Mở setup hiện tại] [Đóng]
```

Payload thiếu trường tối thiểu báo lỗi hợp đồng/thông báo; không lấy plan cũ
khác hoặc quote mới để điền vào sự kiện. Sự kiện inbox là lịch sử đủ điều kiện
tại thời điểm đó; khi mở sau này không khẳng định setup vẫn còn READY.

## 9. Popup, âm thanh và chống lặp

### 9.1 Luồng hiển thị

1. Service xét transition live hoặc đánh giá hiện tại sau restore theo `02`.
2. Commit evidence/revisions và một ledger row bằng alert key duy nhất.
3. Controller nhận sự kiện vừa insert thuộc scope/generation hợp lệ; UI
   upsert inbox. Event duplicate hoặc chỉ tải lại danh sách không phát hiệu ứng.
4. Nếu popup bật, hiện thông báo không modal trong cửa sổ ứng dụng; nếu âm
   thanh bật, phát một hiệu ứng cho lần thông báo mới được trình bày.

Popup gắn shell ứng dụng để vẫn thấy khi đang ở màn hình khác; không tự
chuyển màn hình, lấy focus, mở order dialog hoặc ép ứng dụng lên foreground.
Đóng popup chỉ đóng trình bày; sự kiện còn trong inbox, trạng thái đọc không
thay đổi nếu chưa có thao tác đánh dấu.

Khi nhiều sự kiện đến cùng batch, gộp thành thông báo “Có n setup đủ điều
kiện” và nút **Mở inbox**; mỗi alert key vẫn có một dòng riêng. Nếu popup
đang mở, cập nhật danh sách sự kiện mới trong vùng popup thay vì mở các modal
chồng nhau. Chỉ sự kiện mới chưa trình bày được thêm; không phát chuỗi âm
thanh theo mọi lần repaint hoặc cập nhật bảng.

Ứng dụng đang ẩn/thu nhỏ: vẫn ghi inbox; không tự bật OS notification hoặc
kênh bên ngoài. Khi trở lại, cập nhật badge/inbox và không phát lại hiệu ứng
cho backlog chỉ vì màn hình xuất hiện. Các hiệu ứng UI không được bảo đảm
exactly-once; ledger mới là lịch sử bền vững. Nếu bỏ lỡ popup, người dùng vẫn
xem được sự kiện đã lưu.

### 9.2 Ma trận phát cảnh báo

| Sự kiện | Ledger mới | Popup/âm thanh |
|---|---|---|
| Live chuyển READY, key chưa có, commit thành công | Có | Theo cài đặt, cho sự kiện mới. |
| Poll tiếp vẫn READY | Không | Không. |
| READY -> WATCHING -> READY, cùng first retest/key đã có | Không | Không. |
| Grade/mode đổi trong cùng setup/retest | Không chỉ vì đổi mode | Không; vẫn áp điều kiện sự kiện READY/key thực tế. |
| Đang replay/khôi phục | Không | Không. |
| Chỉ từng READY trong quá khứ, hiện không đạt | Không phát bù | Không. |
| Restore xong, hiện READY với quote an toàn, key chưa có | Có, RESTORE_CURRENT, thời gian hiện tại | Theo cài đặt sau commit, không backdate. |
| Restore key đã có / reload inbox / mở lại app | Không | Không phát lại hiệu ứng. |
| Refresh một lần tạo READY hiện tại hợp lệ/key mới | Có theo cùng flow | Theo cài đặt, dù sau tác vụ trở về IDLE. |
| Lỗi commit hoặc job hủy trước commit | Không | Không. |
| Commit xong rồi crash trước signal | Row đã có | Đọc lại inbox, không phát lại hiệu ứng sau restart. |
| Popup tắt, âm thanh tắt | Vẫn có nếu sự kiện hợp lệ | Không; badge/inbox cập nhật. |
| Popup tắt, âm thanh bật | Vẫn có | Âm thanh cho sự kiện mới; không tạo popup. |

UI không tự sinh alert key, đánh dấu đã phát trước commit hoặc coi thao tác
đóng/đọc popup là điều kiện đủ để core được READY lần nữa. Không kiểm tra
notification bằng cách tạo setup/READY giả trong runtime; dùng harness/store
tạm theo `03`.

## 10. Thời gian, theme và khả năng thao tác

### 10.1 Định dạng và độ chính xác

Thời gian người dùng theo timezone hiển thị đã chọn của ứng dụng, nhãn có
timezone hoặc UTC offset để phân biệt; detail đối chiếu có UTC nguyên gốc.
Format mặc định `dd/MM/yyyy HH:mm:ss`, tick detail thêm mili giây nếu nguồn
có. Không bịa phần lẻ cho nguồn giây hoặc cắt tick mili giây trước lưu/replay.

Clock UI chỉ format thời gian và thông báo thời gian đã trôi qua, không tính
lại nến đã đóng/tuổi vùng/cửa sổ M15. Khi DST làm giờ địa phương lặp, UTC/
offset trong detail phân biệt hai mốc. Tooltip thời gian nến gồm open/close
theo broker; thời gian nhận quote không thay source time.

### 10.2 Theme và bố cục

Tuân [style guide](../ui/style-guide.md): semantic palette hiện có, dynamic
properties, layout tokens, glyph `flat_icon`, stylesheet tập trung. Không
hardcode HEX hoặc gọi `setStyleSheet()` tại screen/chart component. Dark và
light phải giữ cùng hierarchy, nhãn/kiểu nét và trạng thái tương tác.

Demand/BUY dùng semantic buy, Supply/SELL dùng sell; READY dùng success,
WATCHING dùng warning, lỗi/broken dùng danger, thông tin/cũ dùng neutral.
Zone loại Supply không vì màu sell mà bị hiểu thành lỗi: luôn có nhãn chữ.
Màu nền vùng nhẹ để đọc nến; đường giá/zone có label/kiểu nét cho người không
phân biệt màu. Grade A/B/C không dùng màu để thay kết luận gate.

Control chuẩn theo contract 24/20 px trong QSS chung, không gán chiều cao
cố định cục bộ để ép bố cục. Các token layout/control áp dụng theo hệ tọa độ
logic của UI; không hiểu là pixel vật lý để bỏ qua scale. Đối chiếu hiển thị
thực tế theo mục 2.1. Text dài wrap hoặc mở detail; số giá không bị
ellipsis làm mất chữ số quan trọng. Bảng căn giá/điểm về phải, nhãn về trái.

### 10.3 Bàn phím và lỗi trình bày

Tab order: controls -> watchlist/filter -> bảng -> chart/detail -> inbox.
Focus nhìn thấy; nút có accessible name và tooltip nêu chức năng/lý do bị
vô hiệu. Enter chọn dòng/mở detail; Escape đóng popup/dialog khi phù hợp,
không gửi Stop ngầm hoặc xóa cấu hình đã lưu. Không tự lấy focus khi poll.

WebEngine unavailable: hiển thị “Biểu đồ chưa khả dụng”, vẫn có bảng/detail/
inbox. Chart render lỗi không dừng service hoặc làm vùng expired. Dữ liệu
widget không phù hợp contract giữ thông báo lỗi, không sửa giá hoặc state để
vẽ cho được. Nội dung động dùng renderer/escaping của ứng dụng, không chèn
symbol/reason tùy ý thành HTML/JavaScript có thể thực thi.

## 11. Contract trình bày và cập nhật kết quả

Màn hình nhận immutable result cùng request/generation/scope/revisions và
as-of từ controller theo `03`. Update chart, table và detail của một symbol
từ cùng result version; không ghép giá mới với score cũ rồi gắn timestamp
hiện tại. Result cũ sai generation bị loại trước commit/publish, UI kiểm tra
selection để tránh response chậm của mã trước ghi đè mã vừa chọn.

Presentation adapter cần cung cấp các nhóm dữ liệu sau từ contract/bằng chứng
đã có hoặc bổ sung DTO trình bày tương ứng khi viết code:

| Nhóm | Thông tin cần để render |
|---|---|
| Vận hành | Operational status, run intent, command availability, phase/progress và issues. |
| Độ mới | Scope, as-of, watermark từng khung, quote source/received time, current/last-good và pending. |
| Setup | ID, thứ hạng core, giá/grade/breakdown/mode/state, reasons và từng gate đã đánh giá. |
| Vùng/context | Zone role/timeframe/state, hình học, formation score, retest/age/mitigation, aligned D1, selected TP và nearest D1 obstacle. |
| Confirmation | Latch/first touch, M15 candle ref, window progress/limit, confirmation type/evidence và terminal reason. |
| Inbox | Immutable payload, key, scope, detection source, read receipt, unread count/cursor và cờ sự kiện mới sau commit. |

Không biến cờ “đang tải” của widget thành predicate `market_data_safe`.
Thao tác xem/ẩn vùng, sắp bảng, đánh dấu đã đọc và đóng popup không thay model
nghiệp vụ. Lỗi persistence receipt không được báo như setup thất bại.

## 12. Các tình huống kiểm tra khi triển khai

Các mã `SD-UI-*` dùng để truy vết UI sang `01`/`03` và `05`, không phải enum
reason hoặc tham số nghiệp vụ. Dữ liệu ví dụ có thể tạo giả lập cùng code;
không yêu cầu lịch sử giao dịch/backtest/benchmark trước khi triển khai.

| Mã | Tình huống | Kết quả cần kiểm tra | Yêu cầu |
|---|---|---|---|
| SD-UI-01 | Mở ứng dụng lần đầu / watchlist đã lưu rỗng | IDLE, bốn mã chỉ khi chưa có cấu hình; không tự Start hoặc bật tất cả; inbox xem được. | FR-09/11/12 |
| SD-UI-02 | Start, Refresh liên tiếp, Stop khi MT5 chậm, đổi màn hình | Single-flight, pending full không bị poll ghi đè, STOPPING phản hồi, đổi màn hình không ngắt theo dõi. | FR-12, NFR-06 |
| SD-UI-03 | Đổi config/scope trong lúc worker chạy | Generation cũ không ghi đè/popup; last-good ghi rõ cũ, ledger giữ theo scope. | FR-11/12 |
| SD-UI-04 | Thiếu quote/ATR/biên broker, D1 pending, source đóng phiên | Lý do đúng symbol/timeframe, không READY giả; chưa xác minh nguồn khác với không có đồng thuận. | FR-01/04/09 |
| SD-UI-05 | Chọn/lọc/sort setup khi poll và mode đổi | Giữ selection bằng ID, không tự đổi hướng/ranking nghiệp vụ hoặc thêm dòng mode mới. | FR-05/09 |
| SD-UI-06 | H1 trong H4 và setup chỉ H4 | Vùng source/entry/protective đúng contract, không dùng sub-zone distal đặt SL, nhiều role không nhân bản zone. | FR-06/07/09 |
| SD-UI-07 | D1 TESTED nhiều lần, mất hiệu lực, H4/H1 kết thúc retest đầu | D1 /50 và TESTED vẫn làm context khi active; H4/H1 EXPIRED; D1 mất hiệu lực không tự phá H4 trên UI. | FR-03/04/05 |
| SD-UI-08 | Cản TP H4 nhưng D1 gần; Entry trong cản | Nhãn D1 đo từ Entry, đúng target ID/timeframe, Entry trong cản là gate fail; không thêm bonus/phạt riêng. | FR-04/07/08 |
| SD-UI-09 | Source touch chưa entry, rejection ngoài entry, A->B->A, timeout->A | Latch/M15 hiển thị theo evidence; không reset cửa sổ/ID, TOUCH không timeout giả, terminal không hồi sinh. | FR-06/08 |
| SD-UI-10 | RR 1.9996 hiển thị 2.00, thiếu TP, điểm/mitigation 0 | Đạt/chưa đạt theo core, detail giải thích đủ chính xác, None khác 0, không suy score thành phần trăm. | FR-05/07/09 |
| SD-UI-11 | READY mới, READY lặp, đổi mode, READY->WATCHING->READY | Một key/dòng inbox, popup/sound chỉ theo sự kiện mới sau commit. | FR-10 |
| SD-UI-12 | Replay, RESTORE_CURRENT chưa key, sự kiện chỉ đạt quá khứ, crash sau commit | Không hiệu ứng replay/backfill, current READY ghi đúng thời gian, reload chỉ đọc inbox không phát lại. | FR-10/12 |
| SD-UI-13 | Tắt popup/sound, đọc/đóng sự kiện, plan hiện tại đổi | Inbox không mất; receipt không xóa key, payload lịch sử bất biến, mở setup không dựng từ event cũ. | FR-09/10/11 |
| SD-UI-14 | Nhiều READY cùng batch, app ở màn hình khác/thu nhỏ | Gộp trình bày, không modal chồng/focus steal; mỗi key vẫn riêng; trở lại không replay backlog. | FR-10, NFR-06 |
| SD-UI-15 | Store lỗi, chart lỗi hoặc WebEngine thiếu | Không báo lưu thành công giả, không có popup trước commit; bảng/detail còn dùng được khi chart lỗi. | FR-09/10/12 |
| SD-UI-16 | Dark/light, cửa sổ hẹp, bàn phím, lý do dài | Đọc được giá/nhãn, focus rõ, controls truy cập được, không stylesheet/màu cục bộ. | FR-09, NFR-06/09 |
| SD-UI-17 | Rà soát mọi nút, link và callback alert | Không có đường gửi/sửa/đóng/hủy lệnh, không mở auto-entry Scanner. | NFR-01/02 |
| SD-UI-18 | Lần lượt 1366 × 768/100% và 1920 × 1080/150%, maximized, taskbar/shell đầy đủ, dark/light | Controls/trạng thái luôn truy cập được; xem đủ bảng/chart/detail/inbox, giá dài và lý do dài qua tab/scroll; cấu hình/watchlist/popup không tràn màn hình, footer và nút đóng dùng được; UI phản hồi khi phân tích nền. | FR-09/10/12, NFR-06/11 |
| SD-UI-19 | Resize, đổi scale giữa hai cấu hình và mở lại geometry đã lưu; form đang nhập và setup đang chọn | Bố trí lại không chồng/cắt hoặc sai vùng bấm; dialog trong vùng khả dụng; giữ selection/dữ liệu nhập/worker, không đổi state nghiệp vụ hoặc phát lại cảnh báo. | FR-09/11/12, NFR-11 |

`FR-*`/`NFR-*` viết gọn từ `SD-FR-*`/`SD-NFR-*` trong `01`. Khi có code UI,
thực hiện kiểm tra style/layout phù hợp quy chuẩn chung và kiểm tra trực tiếp
trên máy cá nhân; không biến kiểm tra SD thành chứng nhận phát hành thương
mại hoặc yêu cầu số lượt/p95/RAM bắt buộc chưa được PO đặt ra.

Tài liệu này hoàn thành đặc tả trình bày cho phạm vi đã chốt. Layout và nhãn
cần được kiểm tra khi triển khai; chưa có screenshot UI hoạt động, code hoặc
bằng chứng runtime từ việc viết tài liệu. Yêu cầu màn hình được đồng bộ với
`01` SD-NFR-11, `02` contract trình bày và `03` mục 12–14; rules vẫn DRAFT.
Lịch biên broker thực tế còn phải xác minh theo TL-PO-02.
