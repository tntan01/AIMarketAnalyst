# Plan triển khai — Ca "Panel thiếu số liệu cuộn được" (sửa layout panel "Sự kiện đang thiếu số liệu")

> **Trạng thái: DUYỆT — Owner duyệt 25/09/2026** (lập 25/09/2026, vai trò Tech Lead).
> Vòng đời theo D3 (`docs/README.md`): hoàn tất ca → **xóa file này** (lịch sử
> trong Git); điều khoản còn hiệu lực đã nằm trong tài liệu chính đích danh
> (screen_design — câu điều khoản mới cập nhật trong commit D2 của lô).
> Nguồn thẩm quyền: [`../ui/screen_design.md`](../ui/screen_design.md) mục News
> Screen ("panel không phá layout", d.1613-1617, d.1683-1684) +
> [`../architecture/architecture-rules.md`](../architecture/architecture-rules.md).
> Gốc defect: nghiệm thu sử dụng thật 25/09/2026 — panel hiển thị 70 sự kiện
> stale (DB thật) không giới hạn chiều cao → layout nén, chữ chồng lên nhau.
> Miền dữ liệu (DB/parser/controller/repository) ĐÃ kiểm chứng sạch — lỗi thuần
> trình bày.

---

## 1. Mục tiêu

Panel "Sự kiện đang thiếu số liệu" hiển thị **chuyên nghiệp ở mọi số lượng
dòng** (kể cả 70+): danh sách nằm trong vùng cuộn giới hạn chiều cao, mỗi dòng
một hàng cố định, tiêu đề dài cắt "…", bảng tin và toolbar không bị nén. Hành
vi dữ liệu GIỮ NGUYÊN 100% (đọc `events_pending_actual` qua worker, nút mở
trang FF tuần QĐ-F10, tự ẩn khi rỗng, tự làm mới sau lượt dán).

## 2. Phạm vi

**Trong phạm vi:** 1 lô P1 — sửa trình bày panel + test ghim + 1 câu điều khoản
screen_design.

**Ngoài phạm vi (cấm):**
- Mọi file ngoài danh sách lô: 4 file legacy (`news_service.py`,
  `forex_factory_client.py`, `interest_rate_service.py`, `dashboard_screen.py`),
  `controllers/`, `services/` (đặc biệt `ff_source_parser.py`,
  `news_repository.py`), `core/`, `workers/`, `main.py`, `app_controller.py`,
  `ui/main_window.py`, `ui/navigation.py`.
- Không đổi hành vi dữ liệu/nhãn: từ điển nhãn giữ nguyên từng chuỗi (L3);
  không thêm nhãn/luồng mới.
- Density-baseline/UI lock: news screen KHÔNG thuộc bộ lock hiện hành
  (scanner/journal/settings/orders/dashboard) — không được tạo lock mới.

## 3. Ràng buộc nền

| # | Ràng buộc | Nguồn |
|---|---|---|
| R1 | Chỉ đụng file liệt kê trong lô; mọi file khác diff rỗng (`git diff` máy-đọc) | B7 kế thừa |
| R2 | Một commit D2: code + test + docs (câu điều khoản screen_design) cùng commit; message nêu mục tài liệu | D2 |
| R3 | Điều khoản trình bày (vùng cuộn + chiều cao tối đa + dòng 1 hàng cắt "…") phải nằm trong screen_design **trong chính commit lô** (D1); thấy mâu thuẫn → DỪNG báo Owner | D1, V2 |
| R4 | Con số UI duy nhất: token `PANEL_LIST_MAX_HEIGHT` đăng ký tại `LayoutTokens` (giá trị 180); dòng dùng `TABLE_ROW_HEIGHT` có sẵn — không phát minh số rải rác | style-guide/khuôn token |
| R5 | Commit message: E1 đủ 4 câu + `Co-Authored-By: Claude Code <noreply@anthropic.com>`; cập nhật KÉP (mục lô + bảng §8); temp không rác | E1 |
| R6 | Không tên phiên bản trong định danh mới (V3); không mạng (chỉ `openUrl` như hiện hành) | V3, QĐ-F4 |
| R7 | Battery đối chiếu danh tính R9 (họ `tests/test_step3_fred.py` 4-6 failed + collection error `tests/test_smc_gate72_fix_acceptance.py`) — ngoài danh tính = ĐỎ, DỪNG | R9 kế thừa |

## 4. Lô P1 — Panel cuộn + dòng 1 hàng elide (S)

- **File sửa:** `ui/layout_system.py` (THÊM đúng 1 hằng `PANEL_LIST_MAX_HEIGHT
  = 180` trong `LayoutTokens`), `ui/screens/news_screen.py` (panel),
  `tests/test_news_screen_actions.py`, `tests/test_news_screen_smoke.py` (nếu
  inventory smoke đổi), `docs/ui/screen_design.md` (1 câu điều khoản).
- **Nội dung:**
  - `_pending_panel`: bọc danh sách trong `QScrollArea` — khuôn
    `DialogBodyScroll` (`ui/layout_system.py` d.87: `setWidgetResizable(True)`
    + `ScrollBarAsNeeded`; dashboard d.294-298 cùng khuôn); panel
    `setMaximumHeight(LayoutTokens.PANEL_LIST_MAX_HEIGHT)` (QĐ-P1).
  - Mỗi dòng: 1 hàng cố định cao `TABLE_ROW_HEIGHT`, KHÔNG word-wrap; nhãn
    tiêu đề cắt "…" khi dài (khuôn `_ElidedLabel` dashboard d.107-125) (QĐ-P2).
  - GIỮ NGUYÊN (QĐ-P3): đọc worker, nút "Mở trang ForexFactory" từng dòng
    (URL tuần QĐ-F10), tự ẩn khi rỗng, tự làm mới sau lượt dán, mọi chuỗi nhãn.
- **Test (offscreen, controller giả):** fake **70+** sự kiện → (a)
  `panel.maximumHeight() == LayoutTokens.PANEL_LIST_MAX_HEIGHT` + scroll cuộn
  tới dòng cuối; (b) tại 800×500: mọi dòng cao đúng token và **không 2 widget
  dòng nào giao nhau** (assert geometry — ghim defect "chữ chèn vào nhau");
  (c) bảng tin vẫn hiển thị (không bị nén về 0); (d) nút mở link đúng từng
  dòng; (e) panel rỗng → ẩn; (f) test hiện có của panel xanh nguyên trạng.
- **DoD:** pytest 4 bộ news test xanh; battery R9 (danh tính); smoke
  non-offscreen `QT_QPA_PLATFORM=windows python -X utf8
  scripts/smc_ui_smoke.py` EXIT=0 (artifact reports/ hoàn nguyên);
  `git diff HEAD~1 --stat` đúng danh sách file; diff danh sách cấm = RỖNG.
- **Điểm review:** grep `setMaximumHeight|QScrollArea` chỉ trong panel mới;
  không `setStyleSheet` cục bộ; không word-wrap ở dòng panel; nhãn đúng TỪNG
  CHUỖI.
- **Trạng thái:** IMPLEMENTED (25/09/2026 — collector D2; bảng §8 cập nhật KÉP)

## 5. Quyết định triển khai

- **QĐ-P1 — Vùng cuộn + max-height qua token** (Owner duyệt 25/09/2026):
  `QScrollArea` khuôn repo + `LayoutTokens.PANEL_LIST_MAX_HEIGHT = 180` (≈4
  dòng 36px + header + scrollbar). Con số UI đăng ký tập trung tại
  `LayoutTokens` (khuôn `PROGRESS_HEIGHT`/`TABLE_ROW_HEIGHT`), không rải rác.
- **QĐ-P2 — Dòng 1 hàng elide** (Owner duyệt 25/09/2026): bỏ word-wrap, cắt
  "…" theo khuôn `_ElidedLabel` — nhất quán mật độ hiển thị dashboard.
- **QĐ-P3 — Chỉ đổi trình bày** (Owner duyệt 25/09/2026): mọi hành vi dữ liệu
  giữ nguyên; defect là thuần layout nên điều khoản screen_design chỉ bổ sung
  1 câu trình bày (không sinh hành vi mới).

## 6. Rủi ro và giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| Test geometry giao nhau nhạy DPI/nền tảng | Assert bằng tọa độ logic Qt (QRect), chạy offscreen + non-offscreen smoke |
| Sửa panel làm vỡ test panel hiện có | Test hiện có chạy nguyên trạng trong lô (điều kiện (f)) |
| Token/scroll phá mật độ các màn khác | Token chỉ dùng bởi panel này; không đổi token có sẵn |

## 7. Tiêu chí nghiệm thu (DoD toàn ca)

1. Lô P1 IMPLEMENTED + toàn bộ DoD lô đạt (bằng chứng máy-đọc dán commit).
2. Panel 70+ dòng hiển thị đúng chuyên nghiệp (test geometry + smoke).
3. Tài liệu screen_design có câu điều khoản trình bày; plan xóa (D3) sau khi
   Tech Lead nghiệm thu.

## 8. Bảng trạng thái

| Lô | Nội dung | Cỡ | Trạng thái |
|---|---|---|---|
| P1 | Panel cuộn + max-height token + dòng elide + test ghim 70+ dòng + 1 câu screen_design | S | IMPLEMENTED |

## Phụ lục — Khuôn prompt giao lô (A3)

PO tự chuyển prompt sang phiên coder; Tech Lead chỉ soạn prompt + nghiệm thu.
Khuôn 6 mục: [1] Đọc trước; [2] Sản phẩm (file + CẤM); [3] Hành vi đối chiếu
QĐ-P1/P2/P3; [4] Test; [5] DoD máy-đọc + D2/E1/Co-Authored-By; [6] Kỷ luật
dừng.
