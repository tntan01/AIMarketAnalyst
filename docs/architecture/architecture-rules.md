# Quy tắc kiến trúc — Kim chỉ nam thiết kế

> **Trạng thái: BAN HÀNH** theo quyết định của Owner ngày 20/09/2026.
> Áp dụng cho **mọi code mới và mọi ca sửa thiết kế** kể từ ngày ban hành.
> Vi phạm hiện hữu của code cũ không buộc sửa ngay — được đặt tên và lên lịch
> trong Sổ nợ kiến trúc (Phụ lục B) theo quy tắc B6.
>
> Tài liệu này là quy định **tính quy định (prescriptive)**: nó mô tả hệ thống
> phải được thiết kế thế nào theo ý Owner. Khi tài liệu này và code khác nhau,
> đó là defect phải đóng (quy tắc V2), không phải trạng thái chấp nhận được.

---

## Nguyên tắc tối thượng: Nguồn chân lý duy nhất + Một điểm thay đổi duy nhất

> **Nguồn chân lý duy nhất:** mọi quy tắc nghiệp vụ, công thức, ngưỡng, quyết
> định nghiệp vụ có đúng **một mô-đun chủ sở hữu**.
>
> **Một điểm thay đổi duy nhất:** phạm vi ảnh hưởng của mọi yêu cầu thay đổi =
> **đúng một đơn vị logic** (+ kiểm thử của nó + tài liệu đăng ký). Phần còn lại
> được cách ly bởi hợp đồng ổn định và kiểm thử hợp đồng.
>
> **Tiêu chí nghiệm thu của mọi phiên rà soát thiết kế:** phân tích tác động
> thay đổi — câu hỏi *"sửa tệp nào?"* phải trả về đúng **một** tệp logic.
> Nhiều hơn một tệp logic (sửa rải rác nhiều nơi) = thiết kế bị từ chối.

Hai tính chất này độc lập nhau: nguồn chân lý duy nhất chống **trùng lặp ngữ
nghĩa** (nhiều nơi cùng suy ra một tín hiệu); một điểm thay đổi duy nhất chống
**lan truyền thay đổi** (sửa một chỗ mà rung nhiều nơi). Thiếu một trong hai,
kiến trúc không đạt.

**Phép thử điển hình** (dùng khi duyệt mọi thiết kế mới): với mỗi nhu cầu thay
đổi dự kiến — đổi nguồn dữ liệu, đổi công thức, đổi ngưỡng, đổi hiển thị — thiết
kế phải trả lời được *"chỉ sửa đúng một tệp/lớp/hàm nào?"*. Ví dụ: đổi khuôn
dạng RSS → chỉ sửa bộ chuyển đổi RSS; đổi công thức chấm điểm vĩ mô → chỉ sửa
`core/macro_scoring.py`; đổi ngưỡng → chỉ sửa chính sách. Đáp án không quy về
một điểm chạm = thiết kế trượt.

---

## Chương 1 — Quy tắc sở hữu (nguồn chân lý duy nhất)

| # | Quy tắc |
|---|---|
| S1 | **Một phép tính — một chủ sở hữu.** Mỗi công thức nghiệp vụ có đúng một mô-đun sở hữu, đăng ký trong tài liệu chính của miền (D4). Hai nơi cùng suy ra một tín hiệu = khuyết tật (đếm trùng). |
| S2 | **Cấm tính toán bóng.** Bên tiêu thụ gọi API của chủ sở hữu; cấm tự suy diễn lại từ dữ liệu thô (ví dụ: controller tự lấy hai số từ dict rồi tự trừ/nhân hệ số). |
| S3 | **Một loại quyết định — một thẩm quyền duy nhất.** Kết luận/cổng chặn (gate, verdict, status) chỉ do mô-đun chủ sở hữu ban hành; chủ sở hữu **tự dẫn xuất lại** từ đầu vào và **từ chối** dữ liệu bất nhất. Thiếu dữ liệu → KHÔNG XÁC ĐỊNH (`UNKNOWN`), không bao giờ mặc định lạc quan (fail-closed). |
| S4 | **Một ngưỡng — một nguồn có phiên bản.** Mọi con số nghiệp vụ (ngưỡng, trọng số, thời hạn sống, vùng chết) nằm trong đối tượng chính sách/cấu hình có phiên bản, có bằng chứng hiệu chuẩn hoặc nhãn `OPEN` tường minh. Cấm số ma thuật rải trong logic; cấm sao chép một con số sang tệp thứ hai (tài liệu trỏ về nguồn, không chép giá trị — D5). |
| S5 | **Một từ vựng — một định nghĩa.** Thuật ngữ miền (`aligned/conflict/neutral`, mã lý do, trạng thái `fresh/stale/unavailable`) định nghĩa một lần tại mô-đun từ vựng tập trung. Không mô-đun nào phát minh nhãn mới cho khái niệm đã có tên. |
| S6 | **Một cửa thông tin.** Mỗi loại tín hiệu đầu vào (tin tức, giá vĩ mô, lịch kinh tế, sự kiện) có đúng một mô-đun sản xuất đăng ký trong sổ đăng ký sự kiện/tín hiệu. Khi một sự kiện đã được sổ đăng ký nắm giữ, các bộ phận khác không đếm lại tín hiệu đó dưới hình thức khác — chống đếm trùng tận gốc. |

---

## Chương 2 — Cách ly thay đổi

| # | Quy tắc |
|---|---|
| C1 | **Hợp đồng theo ý định, không theo cách thực thi.** Giao diện mô-đun khai báo *ý định + ngữ nghĩa* (đầu vào/đầu ra là gì, cam kết gì), không phơi bày thuật toán bên trong. Đổi cách tính phải giữ nguyên chữ ký hàm và ngữ nghĩa đầu ra — bên tiêu thụ không phải sửa. |
| C2 | **Tầng chống ăn mòn tại biên hệ thống.** Mọi nguồn dữ liệu ngoài (RSS, Yahoo, FRED, ForexFactory, nhà cung cấp AI, MT5) phải có bộ chuyển đổi riêng trong `services/`. Bộ chuyển đổi biên dịch dữ liệu thô → **mô hình miền có tên** ngay tại biên; dữ liệu thô **không được tồn tại bên ngoài** bộ chuyển đổi. Đổi nhà cung cấp = thay bộ chuyển đổi, giữ nguyên mô hình; thêm nhà cung cấp thứ hai = bộ chuyển đổi thứ hai cùng xuất một mô hình (tái sử dụng ngay). |
| C3 | **Dữ liệu qua ranh giới mô-đun = mô hình có kiểu.** Dataclass/mô hình có trường khai báo tường minh. Dict lồng không kiểu cấm vượt biên mô-đun; dict chỉ được phép dùng *bên trong* một mô-đun. Bên gọi nhận dict không kiểu rồi moi ruột theo đường dẫn chuỗi = cờ đỏ mặc định. |
| C4 | **Kiểm thử hợp đồng làm bằng chứng cách ly.** Kiểm thử của bên tiêu thụ ghim *hành vi họ cần* theo hợp đồng, không ghim giá trị trung gian nội bộ của chủ sở hữu. Khi chủ sở hữu đổi công thức: kiểm thử của chủ sở hữu cập nhật theo chủ sở hữu; bộ kiểm thử hạ nguồn **xanh nguyên trạng không cần sửa** = bằng chứng máy-đọc-được rằng ảnh hưởng đã bị nhốt. |

---

## Chương 3 — Phân lớp và chiều phụ thuộc

| Lớp | Sở hữu | Cấm |
|---|---|---|
| `core/` | Logic miền thuần: công thức, cổng quyết định, mô hình, phân loại | Vào/ra (mạng, DB, tệp), tác dụng phụ, chuỗi văn bản hiển thị, import ngược lên `services/ui/controllers` |
| `services/` | Vào/ra + bộ chuyển đổi nguồn ngoài + cache; biên dịch dữ liệu thô → mô hình miền | Chứa công thức chấm điểm; tự phong quyết định nghiệp vụ |
| `controllers/` | Điều phối: gọi services → đưa core → trao ui; quản lý vòng đời job | Tự tính toán; moi ruột dict/mô hình của lớp dưới |
| `ui/` | Hiển thị dữ liệu miền đã được định dạng | Chứa công thức, ngưỡng, logic nghiệp vụ |
| `workers/` | Bao bọc concurrency (thread nền) | Logic nghiệp vụ |

- **L1 — Phụ thuộc một chiều:** `ui → controllers → core ← services`. `core/`
  không import bất kỳ lớp nào phía trên. Vi phạm chiều mũi tên = thiết kế sai,
  không có "tạm chấp nhận". Chặn tự động bằng import-linter (không chu trình).
- **L2 — Chuẩn kiểm chứng được:** mô-đun `core/` phải khởi tạo/gọi được
  **không cần dựng đối tượng giả cho vào/ra** (tính thuần). Phải giả lập ≥3 thứ
  mới gọi được = không thuần = không tái sử dụng được.
- **L3 — Tách dữ liệu – quyết định – hiển thị:** phép tính trả *giá trị + nhãn
  enum*; tầng trình bày mới biến chúng thành *chuỗi cho người đọc* (kể cả tiếng
  Việt). Một hàm vừa tính điểm vừa sinh câu cảnh báo hiển thị là vi phạm, bất
  kể ngắn hay dài.

---

## Chương 4 — Thiết kế mô-đun

- **M1 — Kích thước là triệu chứng, không phải bệnh.** Không có trần số dòng.
  Phân rã theo *lý do thay đổi* (một trách nhiệm duy nhất), không theo độ dài.
  Tệp lớn nhưng đúng một chức năng, cấu trúc mục lục nội bộ rõ, kiểm thử đầy
  đủ, được tái sử dụng = **hợp lệ, không phải sửa**. Tệp ngắn nhưng gánh hai
  lý do thay đổi = vi phạm.
- **M2 — Class = một trục thay đổi.** Đếm *lý do thay đổi*, không đếm thuộc
  tính: nếu mô tả class cần chữ "và" (ví dụ: "lấy tin **và** chấm điểm **và**
  gọi AI **và** chặn tin") → tách theo từng trục lý do. Thuộc tính phình to là
  hệ quả của việc gánh nhiều vai — chữa vai, thuộc tính tự gọn.
- **M3 — Tách phải giảm liên kết, không phải tăng số tệp.** Sau khi tách, mỗi
  bên gọi được phép *biết ít hơn* về nội bộ mô-đun khác; chỉ phụ thuộc hợp đồng
  công bố (trích giao diện/mặt tiền khi cần). Tách xong mà bên gọi vẫn phải
  với vào nội bộ 3 mô-đun để tự ghép kết quả = ca tách thất bại, phải thiết kế
  lại giao diện.
- **M4 — Chỉ tách dùng chung khi có bên tiêu thụ thứ hai thật sự.** Hàm mới mặc
  định thiết kế để tái sử dụng được (tham số tường minh, không đọc trạng thái
  toàn cục, không tác dụng phụ ẩn) — nhưng **không dựng sẵn** mô-đun "dùng
  chung" đầu cơ. Cấm bãi chứa `utils/common` vô chủ: cái gì cũng vào được thì
  không ai sở hữu.
- **M5 — Phép thử danh tính mô-đun:** docstring của mô-đun/class phải trả lời
  "đơn vị này sở hữu tri thức gì?" bằng **một câu không chứa chữ "và"**.
  Không trả lời được = chưa đủ điều kiện tồn tại độc lập (phải tách hoặc phải
  sáp nhập vào chủ sở hữu đúng).

---

## Chương 5 — Tài liệu song hành với mã nguồn

- **D1 — Định nghĩa Sẵn sàng (tài liệu trước khi code):** task chỉ được bắt đầu
  khi tài liệu chính của miền có mục mô tả hành vi mới, **đăng ký chủ sở hữu**
  của phép tính/quyết định sắp tạo, kèm trạng thái `PLANNED`. Chưa có mục tài
  liệu → chưa mở trình soạn thảo code.
- **D2 — Định nghĩa Hoàn thành (thay đổi nguyên tử):** code + kiểm thử hợp đồng
  + cập nhật tài liệu nằm trong **cùng một commit**; thông điệp commit nêu tên
  mục tài liệu đã sửa. Cấm nợ tài liệu sang commit sau.
- **D3 — Danh sách tài liệu chính là danh sách đóng** (đăng tại `docs/README.md`).
  Task mới không tự đẻ tài liệu riêng; nội dung đi vào tài liệu chính đúng miền.
  Việc đang mở: một tệp `docs/plans/<tên>-plan.md` theo vòng đời đã chốt — hoàn
  tất thì xóa (lịch sử trong Git), hợp đồng còn hiệu lực thì sáp nhập vào tài
  liệu chính đích danh.
- **D4 — Danh mục thay đổi bắt buộc + sổ đăng ký sở hữu:** mỗi tài liệu kiến trúc
  miền có (a) bảng *yêu cầu thay đổi → điểm chạm duy nhất → cơ chế bảo vệ* và
  (b) bảng *chủ sở hữu của từng phép tính/quyết định*. Phải trình tại rà soát
  thiết kế cho 5–10 thay đổi dự kiến. Đây là công cụ thực thi S1: muốn thêm chỗ
  tính mới phải sửa sổ đăng ký — và phiên rà soát sẽ hỏi "tại sao chủ sở hữu cũ
  không làm việc này?".
- **D5 — Tài liệu trỏ về nguồn, không chép giá trị:** tài liệu ghi "ngưỡng lấy
  từ tệp chính sách nào, khóa nào" — không ghi lại con số, để không tồn tại bản
  sao thứ hai có thể lệch pha (cặp với S4).
- **D6 — Chuẩn ngôn ngữ tài liệu:**
  1. **Tên tệp/thư mục tài liệu: tiếng Anh không dấu**, chữ thường nối bằng
     gạch ngang (`architecture-rules.md`) — đường dẫn phải an toàn đa nền tảng
     (Windows/Linux, git, công cụ tìm kiếm, link tương đối) và code còn tham
     chiếu bằng đường dẫn.
  2. **Nội dung tài liệu: tiếng Việt có dấu đầy đủ.**
  3. **Thuật ngữ tiếng Anh phải dịch tối đa ra tiếng Việt có dấu.** Chỉ giữ
     tiếng Anh với ba nhóm không thể/không nên dịch: (a) **mã định danh của
     code** — tên tệp/lớp/hàm/biến, khóa cấu hình, mã lý do, nhãn enum, giữ
     nguyên xi như trong code; (b) **tên riêng công cụ/thư viện** —
     import-linter, PyInstaller, pytest, yfinance, PyQt6; (c) **thuật ngữ ngành
     mà dịch sẽ mất chính xác hoặc mất khả năng tra cứu** — khi đó viết tiếng
     Việt trước, tiếng Anh trong ngoặc ở lần xuất hiện đầu ("tầng chống ăn mòn
     (anti-corruption layer)"), các lần sau chỉ dùng tiếng Việt.
  4. **Một khái niệm — một từ tiếng Việt** trên toàn cây tài liệu (nối với S5:
     từ vựng miền đăng ký tập trung); cấm nhiều biến thể tiếng Việt cho cùng
     một thuật ngữ, cấm dùng lại tiếng Anh khi đã có từ tiếng Việt đăng ký.
  5. **Nghiệm thu:** tài liệu mới vi phạm = từ chối ở rà soát (E1); tài liệu cũ
     vi phạm sửa dần theo B6.

---

## Chương 6 — Đo lường bảo trì được và cưỡng chế

- **B1 — Sửa rải rác nhiều nơi = khuyết tật.** Một thay đổi hành vi phải sửa
  đến tệp logic thứ hai → không vá cả hai; hợp nhất sở hữu về một chủ trước
  (S1), rồi mới sửa.
- **B2 — Khả năng truy vết ≤5 phút:** người chưa từng làm task đó, xuất phát từ
  `docs/README.md`, tìm được mô-đun chủ sở hữu của một hành vi bất kỳ trong
  ≤5 phút.
- **B3 — Kiểm thử đặc trưng trước khi tái cấu trúc:** mọi ca tái cấu trúc di sản
  phải có kiểm thử ghim đầu ra hiện hành (đặc trưng hóa) *trước* khi dời code;
  ca tái cấu trúc thuần phải giữ nguyên hành vi — bộ kiểm thử đặc trưng xanh
  là nghiệm thu.
- **B4 — Mặc định fail-closed:** thiếu dữ liệu → KHÔNG XÁC ĐỊNH + giảm cấp
  tường minh, có provenance/log. Không bao giờ suy diễn giá trị lạc quan hay im
  lặng coi như trung tính.
- **B5 — Không bịa ngưỡng:** mọi con số phải có bằng chứng (hiệu chuẩn/dữ
  liệu/kiểm thử) hoặc nhãn `OPEN` tường minh trong chính sách. Cấm chép mặc
  định từ hệ cũ sang hệ mới khi chưa có bằng chứng riêng.
- **B6 — Sổ nợ kiến trúc:** vi phạm di sản được đặt tên + mốc xử lý trong Phụ
  lục B. Code mới tuân thủ 100%; code cũ lên lịch sửa tăng dần — mỗi ca một
  commit tái cấu trúc thuần có kiểm thử bảo vệ. **Cấm viết lại toàn bộ một lần.**
- **E1 — Bốn câu hỏi rà soát bắt buộc** (mọi PR/task):
  1. Chủ sở hữu của phép tính này là ai — tôi đang *tiêu thụ* hay đang *nhân bản*?
  2. Mô-đun/class tôi chạm vào có đúng **một lý do thay đổi** duy nhất?
  3. Hành vi này đã có **điều khoản tài liệu** mô tả chưa; chủ sở hữu mới (nếu có) đã đăng ký chưa?
  4. Có **định danh phiên bản** nào lọt vào tên mới không (V3)?
- **E2 — Cổng kiểm tra tự động trong battery:** import-linter chặn phụ thuộc
  ngược vào `core/`; quét chuỗi văn bản hiển thị trong `core/`; danh sách trường
  cấm; kiểm tra trùng lặp đã đăng ký. Luật không có cơ chế tự động thì chỉ là
  khuyến cáo.
- **E3 — Ngoại lệ bằng văn bản:** PO/Tech Lead duyệt ngoại lệ → ghi vào sổ nợ
  kèm lý do + ngày hết hạn. Không có ngoại lệ ngầm, không có "lần này thôi".

---

## Chương 7 — Quyền quyết định của Owner và nguyên tắc không phiên bản

- **V1 — Một người quyết định duy nhất.** Đây là phần mềm cá nhân: quyết định
  thay đổi của Owner là quyết định cuối cùng, hiệu lực ngay, không hội đồng phê
  duyệt. Quy trình chuẩn: *Owner phát biểu ý định → tài liệu chính cập nhật
  chính xác ý định đó → code viết đúng tài liệu → kiểm thử ghim tài liệu.*
  Không bước nào được đi tắt (không code trước khi tài liệu mô tả xong — nối
  với D1).
- **V2 — Tài liệu là đặc tả thẩm quyền.** Tài liệu chính mô tả **chính xác
  những gì Owner muốn**; code là bản hiện thực phải đúng từng hành vi theo mô
  tả đó. Hệ quả bắt buộc:
  - Lệch tài liệu ↔ code = **defect**, chỉ được chữa theo một trong hai hướng:
    sửa code cho đúng tài liệu, hoặc Owner sửa tài liệu theo ý định mới. Cấm để
    hai bên lệch nhau "chấp nhận được".
  - **Cấm hành vi không khai báo:** code không được có hành vi nghiệp vụ mà tài
    liệu không mô tả. Hành vi muốn tồn tại phải có điều khoản; không có điều
    khoản = gỡ bỏ.
  - Kiểm thử là *bản khả thi của tài liệu:* mỗi điều khoản hành vi có kiểm thử
    tương ứng; đổi điều khoản = đổi kiểm thử trong cùng commit (D2).
  - Thứ tự ưu tiên khi đối chiếu: **(1) ý định Owner trong tài liệu chính (tính
    quy định — code phải theo); (2) code/test đang chạy (phản ánh hiện trạng);
    mâu thuẫn giữa hai nguồn = defect phải đóng.**
- **V3 — Không đặt tên phiên bản cho tính năng.** Hệ thống chỉ có **một trạng
  thái hiện hành**. Khi Owner quyết thay đổi: thiết kế cũ bị *thay thế hoặc
  xóa* — không lưu "v2/v3/v4" trong tên mô-đun, class, hàm, cấu hình, UI hay
  tài liệu; lịch sử thuộc về Git. Cấm mô-đun twin song song ("bản mới chạy,
  bản cũ giữ tên"). Hai ngoại lệ giới hạn chặt:
  - **(a) Khóa tương thích dữ liệu:** chuỗi đã persist vào dữ liệu cũ
    (`policy_version`, mã lý do, khóa schema journal — ví dụ
    `"scanner-macro-policy-v4"`, họ mã `BACKTEST_*`) được giữ nguyên chuỗi lịch
    sử nhưng **đóng băng**: chỉ là khóa máy đọc phục vụ tương thích/truy vết,
    không bao giờ xuất hiện như tên tính năng trên UI/tài liệu mới. Các hằng
    `*_VERSION` nội bộ dùng truy vết provenance thuộc nhóm này. **Tuyệt đối
    không đổi giá trị chuỗi đã persist** — chỉ được đổi tên biến/hằng bao quanh.
  - **(b) Hợp đồng mới:** khi cần phân biệt ngữ nghĩa, đặt tên **mô tả nội
    dung** (ví dụ: `macro_gate`, `location_runtime`) — không đánh số phiên bản
    nối tiếp.

---

## Phụ lục A — Danh mục thay đổi mẫu (miền Macro, sau tách lớp)

Bảng này là khuôn mẫu bắt buộc cho mọi tài liệu kiến trúc miền (D4):

| Yêu cầu thay đổi | Điểm chạm duy nhất | Cơ chế bảo vệ |
|---|---|---|
| Đổi công thức chấm điểm vĩ mô | `core/macro_scoring.py` | chữ ký `MacroScores` bất biến + bộ kiểm thử cổng/điều phối xanh nguyên trạng |
| Đổi ngưỡng (vùng chết, độ tin cậy) | `config/scanner_order_policy.json` | chính sách có phiên bản; không đổi code |
| Đổi quy tắc quyết định (mâu thuẫn → CHẶN) | `core/macro_gate.py` | thẩm quyền kết luận duy nhất (S3) |
| Đổi/thêm nguồn tin (RSS) | bộ chuyển đổi RSS trong `services/` | hợp đồng mô hình `Headline` (C2) |
| Đổi nguồn giá vĩ mô (Yahoo → FRED) | bộ chuyển đổi nguồn + sổ đăng ký | mô hình quan sát chuẩn hóa (C2) |
| Đổi cách hiển thị cột vĩ mô | mô-đun trình bày | `MacroScores` bất biến (C1) |
| Đổi ảnh hưởng của sự kiện địa chính trị | sổ đăng ký sự kiện (chủ sở hữu tín hiệu) | một cửa thông tin (S6) |

**Đối chiếu hiện trạng (đo mức vi phạm hôm nay):** "đổi công thức tính điểm vĩ
mô" hiện chạm tối thiểu 4 tệp logic (`news_service.py`, `analysis_pipeline.py`,
`scanner_controller.py`, `signal_engine.py`). Sau ca tách lớp, câu trả lời phải
là 1 — đó là nghiệm thu của ca refactor đầu tiên theo luật này.

## Phụ lục B — Sổ nợ kiến trúc (vi phạm hiện hữu đã đặt tên)

| # | Vi phạm | Quy tắc | Mốc xử lý |
|---|---|---|---|
| 1 | `NewsService` — 4 lý do thay đổi (khuôn tin/công thức điểm/nhà cung cấp AI/chính sách cổng tin) trong 3.080 dòng | M2, S1 | ca tách lớp macro |
| 2 | Tín hiệu risk-off bị chấm tại 4 điểm độc lập (lexicon tier3, AI stance, VIX score, correlation adjustment) | S1, S6 | sổ đăng ký sự kiện |
| 3 | `correlation_check.py` trộn phép tính + chuỗi cảnh báo tiếng Việt | L3 | ca tách lớp macro |
| 4 | `scanner_controller.py` moi ruột dict không kiểu + tự nhân hệ số freshness | S2, C3 | mô hình có kiểu cho snapshot |
| 5 | Hệ số nhân độ tin cậy inline trong `analysis_pipeline` (×0.4/×0.8/×0.8, floor 0.15) | S4, M2 | ca tách lớp macro |
| 6 | Đường điểm số vĩ mô di sản (`signal_engine`) song song `MacroGate` | S3, V3 | Bước 07/12 (đã có lịch trong `scanner-architecture.md`) |
| 7 | 5 mô-đun twin `*_v4_*` + ~108 định danh `v2/v3/v4` trong code sản xuất | V3 | đổi tên mô tả nội dung theo từng ca (B6); chuỗi persist đã đóng băng giữ nguyên theo ngoại lệ V3(a) |
| 8 | Thứ tự ưu tiên tài-liệu-vs-code cũ trong `docs/README.md` theo hướng mô tả (code thắng) | V2 | **ĐÃ XỬ LÝ 20/09/2026** — README sửa cùng đợt ban hành luật |

## Phụ lục C — Án lệ tốt trong repo (khuôn mẫu để nhân bản)

| Khuôn mẫu | Án lệ | Quy tắc minh họa |
|---|---|---|
| Thẩm quyền quyết định duy nhất, tự dẫn xuất lại, fail-closed | `core/macro_gate.py` (`MacroGate.evaluate`) | S3, B4 |
| Từ vựng tập trung | `core/reason_codes.py` | S5 |
| Chính sách có phiên bản, giá trị `OPEN` tường minh | `MacroPolicy` + `config/scanner_order_policy.json` | S4, B5 |
| Trạng thái dữ liệu tường minh, không im lặng lạc quan | `MacroMarketCache` (`fresh/stale/unavailable`) | B4 |
| Danh sách trường cấm, cưỡng chế bằng test | `FORBIDDEN_V3_JOURNAL_FIELDS` | E2 |
| Kiểm thử hợp đồng ghim đặc tả điểm số | `tests/test_macro_scoring_contract.py` | C4, B3 |
| Mô hình có kiểu qua ranh giới | `MacroAssessment`, `ScenarioPlan` | C3 |
