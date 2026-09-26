# Đề xuất — Hiển thị thời gian theo múi giờ người dùng trên màn Quản lý tin

> **Trạng thái: DUYỆT — Owner quyết 25/09/2026.**  Đã chốt **Q1 = PA1**: thời
> gian hiển thị lấy theo khóa `settings.display.timezone`, Settings cho 3 lựa
> chọn `Asia/Ho_Chi_Minh` / `Asia/Bangkok` / `UTC` (mặc định `Asia/Ho_Chi_Minh`).
> **Q2 = PA-B và Q3** (ngày theo múi giờ người dùng) được chốt cùng ngày — "Tất
> cả đều theo múi giờ người dùng" (form giờ đăng thu theo múi giờ; lọc khoảng
> ngày + tuần FF theo múi giờ; `day_key` lưu trữ vẫn UTC).
> **Bước 1 (tài liệu) + Bước 2 (code) đã thực hiện** theo mục "Thực thi đã quyết
> định" bên dưới; tài liệu này giữ làm biên bản quyết định cho đến khi ca hoàn
> tất (D3 → xóa).
>
> Nguồn gốc: điều tra kênh dán mã nguồn FF (25/09/2026) — người dùng nhận thấy
> giờ hiển thị trên màn Quản lý tin khác giờ hiển thị trên trang ForexFactory.

---

## 1. Vấn đề

Sự kiện lịch kinh tế nhập qua kênh dán mã nguồn trang hiển thị trên màn Quản lý
tin **theo giờ UTC**, trong khi phần còn lại của app điều chỉnh theo **múi giờ
người dùng** (`settings.display.timezone`). Với múi giờ Việt Nam (GMT+7), cùng
một sự kiện:

- Trang FF hiển thị: `RBA Assist Gov Hunter Speaks` lúc **2:00am 22/09** (giờ
  trình duyệt GMT+7).
- Màn Quản lý tin hiển thị: **giờ UTC tương ứng** (21:00 ngày 21/09) → người
  dùng thấy "lệch 7 giờ".

Hệ quả kèm theo: sự kiện local rạng sáng (0h–6h59) bị gắn `day_key` của ngày
hôm trước theo UTC (vd GfK `6:01am 25/09` local = `23:01 24/09` UTC → xếp vào
ngày "24/09" khi lọc/đếm theo ngày). Việc này đúng theo contract (lưu UTC) nhưng
khó đọc đối với người dùng Việt Nam.

## 2. Hiện trạng (bằng chứng)

| Khâu | Hành vi | Vị trí |
|---|---|---|
| Lưu trữ | `dateline` (Unix epoch UTC) → `event_time_utc` UTC + `day_key` UTC — **giữ nguyên, không đổi** | `services/ff_source_parser.py` d.268-275 |
| UI màn Quản lý tin | Hiển thị **cứng UTC**: `_display_time` ép `astimezone(UTC)`; cột xem trước nhãn **"Thời gian (UTC)"**; form giờ đăng thu `Qt.TimeSpec.UTC` (D2) | `ui/screens/news_screen.py` d.887-897, d.430, d.113-114 |
| Settings | Đã có khóa `display.timezone` (mặc định `Asia/Ho_Chi_Minh`), Settings cho chọn `Asia/Ho_Chi_Minh` / `Asia/Bangkok` / `UTC` | `services/settings_service.py` d.231; `ui/screens/settings_screen.py` d.1508-1510 |
| Dashboard / Scanner | Đã chuyển về `settings.display.timezone` (ZoneInfo + `astimezone`) để hiển thị | `ui/screens/dashboard_screen.py` d.564-573, d.635-638; `ui/screens/scanner_screen.py` d.1850 |
| Mâu thuẫn tài liệu nội tại | `screen_design.md`: mục AI bulletin "**Tất cả thời gian hiển thị theo múi giờ người dùng đã chọn**" (d.603) **≠** mục News preview "**Thời gian (UTC)**" (d.1595) → theo V2, mâu thuẫn = defect tài liệu phải đóng | `docs/ui/screen_design.md` d.603, d.1595 |

Màn Quản lý tin là **trường hợp ngoại lệ duy nhất** hiển thị cứng UTC so với các
màn còn lại.

## 3. Đề xuất

**Chỉ thay đổi tầng trình bày (UI), không đổi dữ liệu.**

1. **`_display_time` đọc `settings.display.timezone`** (fallback `Asia/Ho_Chi_Minh`
   theo khuôn Dashboard d.564-573) → đổi mốc UTC về múi giờ người dùng trước khi
   format `%d/%m/%Y %H:%M`. Dữ liệu `event_time_utc`/`day_key` trong DB **bất
   biến** (vẫn UTC — contract §6.1 bước 3 "không suy đoán timezone" chưa đổi).
2. **Nhãn cột xem trước** bỏ hậu tố: `Thời gian (UTC)` → `Thời gian` (khớp nhãn
   bảng chính d.263) tại `news_screen.py` d.430 và `screen_design.md` d.1595.
3. **Form giờ đăng nhập tay (D2):** đây là điểm cần Owner bấm nút — xem mục 4.

**Điểm chạm duy nhất cho mỗi thay đổi (D4/§11a):**

| Thay đổi | Điểm chạm | Cơ chế bảo vệ |
|---|---|---|
| Đổi format hiển thị giờ | `ui/screens/news_screen.py` (`_display_time` + nhãn cột xem trước) | test UI ghim chuỗi hiển thị; `_display_time` là hàm thuần tầng trình bày |
| Đồng bộ tài liệu | `docs/ui/screen_design.md` d.1595 (+ d.603 không đổi) | D5 — trỏ, không chép |
| Nếu đổi cả form giờ đăng | `ui/screens/news_screen.py` (D2, d.113-114 + d.963) | tùy quyết định Owner (mục 4) |

## 4. Quyết định đã chốt (Owner 25/09/2026)

**Q1 — nguồn múi giờ hiển thị:** ✅ **PA1** — theo `settings.display.timezone`
(người dùng chọn trong Settings: `Asia/Ho_Chi_Minh` / `Asia/Bangkok` / `UTC`, mặc
định `Asia/Ho_Chi_Minh`; khóa tồn tại sẵn `services/settings_service.py` d.231).
PA2 (giờ máy) bị bác — lệch chuẩn chung của app.

**Q2 — phạm vi:** ✅ **PA-B** (Owner 25/09/2026 — "Tất cả đều theo múi giờ người
dùng") — đổi cả form giờ đăng: widget nhập/sửa thu theo múi giờ người dùng,
`published_utc` lưu vẫn UTC (D2 cập nhật theo quyết định; `news_screen.py` D2).

**Q3 — khái niệm "ngày" hiển thị:** ✅ **Theo múi giờ người dùng** (Owner
25/09/2026) — `_window_bounds` (khoảng ngày lọc từ/đến) quy về UTC qua múi giờ
người dùng; `_week_start_utc`/`ff_week_url_for_event` (tuần mở trang FF) cũng
tính theo múi giờ người dùng cho nhất quán. **`day_key` lưu trữ KHÔNG đổi**
(UTC — contract §4.2, không ảnh hưởng vĩ mô).

## 5. Rủi ro và giới hạn

- **Không đổi dữ liệu**: mọi bên tiêu thụ vĩ mô/gate (đấu nối b) đọc theo UTC —
  không ảnh hưởng.
- **Lịch sử đã lưu**: chỉ đổi cách hiển thị, không đổi giá trị `day_key` đã
  persist → đơn giản, không cần migration.
- **Test**: `_display_time` trở thành hàm phụ thuộc settings → test ghim chuỗi
  hiển thị phải ép setting cố định (đã có khuôn Dashboard). Nhãn cột thay đổi
  có thể chạm test ghim chuỗi "Thời gian (UTC)" (rà khi triển khai).
- **Lệch giờ là ảo giác chứ không phải lỗi dữ liệu**: thời điểm UTC trong DB
  chính xác; đây thuần là vấn đề trình bày.

## 6. Thực thi đã quyết định

**Bước 1 — Tài liệu (đã thực hiện 25/09/2026):**

1. `docs/ui/screen_design.md` d.1595: "Thời gian (UTC)" → "Thời gian" (khớp nhãn
   bảng chính); thêm bullet "Múi giờ hiển thị" nêu mọi cột thời gian trên màn
   theo khóa `settings.display.timezone` (3 lựa chọn) — dữ liệu lưu vẫn UTC.
2. `docs/news/news-architecture.md` d.319 (§6.1 bước 5 — bảng xem trước):
   "thời gian (UTC)" → "thời gian (hiển thị theo múi giờ người dùng đã chọn —
   khóa `display.timezone`; giá trị lưu trữ vẫn UTC, mục 4.2)".
3. Mâu thuẫn doc d.603 ≠ d.1595 trong `screen_design.md` đã đóng (cả hai cùng
   nói "hiển thị theo múi giờ người dùng đã chọn").

**Bước 2 — Code (đã thực hiện 25/09/2026 — theo Q1=PA1 + Q2=PA-B + Q3):**

1. `_display_time` đọc múi giờ theo khóa `settings.display.timezone` qua seam
   `NewsController.display_timezone()` (news_screen cấm import services — L1/E2;
   khuôn `_fred_api_key`) → format `%d/%m/%Y %H:%M` theo múi giờ người dùng.
2. Đổi nhãn `_PREVIEW_COLUMNS` "Thời gian (UTC)" → "Thời gian".
3. Form giờ đăng (D2 → PA-B): `_iso_to_qdatetime` mang wall-time theo múi giờ
   người dùng; `time_value()` quy về UTC trước khi gửi (lưu trữ bất biến).
4. `_window_bounds` (lọc khoảng ngày — Q3): ngày chọn theo múi giờ người dùng,
   quy về UTC cho truy vấn; `day_key` không đổi (UTC).
5. `_week_start_utc`→`_week_start` + `ff_week_url_for_event` (Q3): tuần mở trang
   FF tính theo múi giờ người dùng.
6. Test: 3 test ghim chuỗi UTC cập nhật sang hiển thị múi giờ cố định
   (Asia/Ho_Chi_Minh) — deterministic, không phụ thuộc settings máy chạy test;
   battery news 401 passed; battery tổng chạy đối chiếu ngoại lệ pre-existing.