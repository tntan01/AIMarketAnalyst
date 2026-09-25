"""ui/screens/news_screen.py — màn Quản lý tin: khung bảng + bộ lọc + chi tiết dòng (plan lô L3.2).

Phạm vi lô: **bố cục và đường đọc** của màn (screen_design "Bố cục" +
"Trạng thái tải và rỗng").  Màn chỉ ĐỌC qua ``NewsController`` → ``NewsRepository``
(hợp đồng §8), và mọi lần đọc chạy trong worker nền (``NewsReadWorker``) —
không query ở GUI thread (screen_design "Nguyên tắc").  UI không tính toán
nghiệp vụ, không gọi nguồn ngoài, không chứa công thức/ngưỡng (L1, S2).

**Từ điển hiển thị** (S5 — screen_design d.1557, Owner duyệt 21/09/2026): mọi
nhãn enum dưới đây chép NGUYÊN VĂN từ bảng đã đăng ký; không có nhãn nào được
tự đặt thêm.  Bốn chuỗi ngoài bảng đó đều có nguồn đã đăng ký:

* ``EVENT_TEXT = "Sự kiện"`` — nguyên văn bullet bộ lọc của screen_design
  (d.1551: "theo ``kind`` (sự kiện/headline/phát biểu/nhập tay)") + thuật ngữ
  contract §2 ("Sự kiện lịch kinh tế").  Đây là giá trị lọc riêng của màn
  (bảng hợp nhất hai nguồn), không phải một enum của contract.
* nhãn cột / nhãn bộ lọc / nhãn nút thanh công cụ — nguyên văn khối "Bố cục".
* mục "(tất cả …)" của mỗi combo — khuôn có sẵn của repo
  (``journal_screen.py``: "Tất cả mã", "Tất cả trạng thái"...), ghép từ chính
  nhãn bộ lọc đã đăng ký.
* ``LOADING_TEXT = "Đang tải..."`` — chuỗi có sẵn của repo
  (``dashboard_screen.py``) cho chỉ báo loading mà screen_design yêu cầu.

**Đợt 3 (24/09/2026 — ca "Nguồn dán FF", plan F1):** thanh công cụ chỉ còn
**[ Nhập tin | AI nhận định xu hướng ]** — hai nút "Lấy lịch kinh tế"/"Cập nhật
actual" (lô L3.3 cũ) và hai nút "Xuất file"/"Nhập file" (lô L3.4 cũ) cùng toàn
bộ slot thread/dialog riêng của chúng đã bị **GỠ** (contract §13/§10 đợt 3 — bỏ
thu tự động FF, bỏ xuất/nhập file; app không phát request mạng nào tới
ForexFactory).  Gợi ý "Nhập actual bằng tay" cũng bỏ (dán source là kênh actual
duy nhất — contract §13 đợt 3).  Nhãn hiển thị nguồn đổi 3 chuỗi theo Từ điển
đợt 3 (``ff_html`` = "ForexFactory (mã nguồn trang)", ``ff_json`` = "ForexFactory
(lịch — dữ liệu cũ)", ``import`` = "Nhập file (dữ liệu cũ)" — nhãn cũ phục vụ
dữ liệu cũ, GIỮ); empty state gợi ý "Dán mã nguồn trang".

**Lô F4 — dialog dán mã nguồn 2 pha + panel thiếu số liệu** (screen_design
"Hành vi dán mã nguồn trang ForexFactory" d.1579-1617 + "Bố cục" d.1544-1547 +
từ điển d.1577; contract §6.1 đợt 3+4; QĐ-F6/F9/F10): toolbar
**[ Dán mã nguồn trang | Nhập tin | AI nhận định xu hướng ]** — nút đầu và nút
empty state cùng nhãn mở ``PasteSourceDialog`` (2 pha).  Pha 1: dán source hoặc
chọn file `.html` (đọc file TRONG WORKER — không block GUI) → "Bóc tách" →
``controller.parse_pasted_source`` trong ``NewsReadWorker`` (khuôn D10 — không
processEvents); lỗi parse → thông báo theo ``PARSE_ERROR_TEXT`` (L3 — ánh xạ mã
lỗi có kiểu của parser, không đặt chuỗi này trong services), giữ pha 1.  Pha 2:
bảng xem trước đúng cột d.1594-1596 + đếm quan sát lãi suất; **chỉ cột "Thực
tế" sửa được** (QĐ-F6/đợt 4), cột còn lại read-only, không checkbox/xóa dòng;
sửa actual → badge "Đã sửa" + phân loại lại qua ``controller.reclassify_pasted_rows``
(QĐ-F9 — UI không tự phân loại, S2); "Cập nhật" → ``commit_pasted_source(preview,
edited_actuals)`` trong worker → tóm tắt mới/cập nhật/xung đột → đóng dialog (màn
làm mới bảng tin + panel); "Hủy" → reject, không ghi/không run (§6.1 bước 6).
Panel "Sự kiện đang thiếu số liệu" đọc ``events_pending_actual`` qua worker
(contract §8 — chỉ nuôi panel hướng dẫn, không phục vụ fetch tự động); nút "Mở
trang ForexFactory" mỗi dòng → ``QDesktopServices.openUrl`` URL trang lịch TUẦN
tương ứng (QĐ-F10 — chỉ mở link bằng trình duyệt ngoài, app không phát request
mạng nào tới ForexFactory; QĐ-F4).

Khai báo đọc-hiểu lô F4 (V2):

* Worker của mọi thao tác nền trong dialog dán (parse / đọc file / phân loại
  lại / commit) là ``NewsReadWorker`` dùng chung — một task một thread, khuôn
  D10; phân loại lại sau sửa actual có cờ đợi (``_reclassify_pending``) để
  không chồng lời gọi khi người dùng sửa liên tiếp.
* "Đã sửa" là trạng thái hiển thị ƯU TIÊN của dòng đã sửa actual (d.1602 "trạng
  thái chuyển 'Đã sửa'"); kết quả ``reclassify_pasted_rows`` vẫn được tính (và
  giữ) để phân loại các dòng chưa sửa.
* Dialog đóng (accept) ngay sau "Cập nhật" thành công — màn chủ lo phần làm mới
  bảng tin + panel (d.1611-1612); "Hủy" reject không chạm controller.
* URLs ``https://www.forexfactory.com/calendar...`` là hằng số QĐ-F10 (bốn
  URL) — là nơi DUY NHẤT chứa "http" trên màn, luôn đi qua
  ``QDesktopServices.openUrl`` để mở trình duyệt ngoài; màn không import mạng.

**Lô L3.5 — cửa sổ AI nhận định xu hướng** (screen_design d.1621-1649; contract
§9.1-§9.2): nút "AI nhận định xu hướng" mở ``AiTrendDialog`` (520×640, không
modal toàn app — WindowModal, d.1624); phạm vi = cặp tiền ``SUPPORTED_SYMBOLS``
(tiêu thụ) hoặc 1 đồng tiền rút từ chính danh sách cặp; dòng đếm qua
``controller.ai_scope_preview`` (không gọi AI); dưới ``ai_min_items`` hiện
d.1642 và nút "Nhận định" không gọi AI (B4); lời gọi AI chạy trong worker nền
(khuôn worker D10 của màn — không gọi ``analyze()`` đồng bộ trong callback,
không processEvents); lỗi provider/parser → thông báo thân thiện; 3 thẻ chân
trời nhãn đúng từ điển d.1570-1572, ký hiệu ▲/▼/— màu semantic; dẫn chứng bấm
được → đóng dialog + ``_jump_to_evidence`` nhảy dòng bảng; lịch sử
``verdicts_for`` mới nhất trước; cảnh báo advisory d.1638 THƯỜNG TRỰC.

Khai báo đọc-hiểu (V2):

* Cơ chế nhảy dòng theo dẫn chứng (d.1646-1647, chưa được tài liệu ghim — id
  evidence là int CHUNG hai bảng, ``_evidence_ids`` của builder): ưu tiên khớp
  ``item.id`` rồi ``event.id`` trong tập dòng đã đọc; chỉ nhảy khi dòng đang
  hiển thị trên bảng (bị bộ lọc che thì chỉ đóng dialog — không tự đổi bộ lọc).
* Limit lịch sử verdicts_for = 5 (``AI_HISTORY_LIMIT``) — hằng TRÌNH BÀY của
  dialog, không phải giá trị vận hành (B5: không thêm khóa policy).
* Lỗi provider: adapter đã dịch qua ``friendly_error()`` khi raise → dialog
  hiển thị ``error_message`` của result nguyên văn (không dịch lại ở UI).
* "Nhận định" là nút duy nhất khởi động lượt AI; không có lấy lại tự động
  (retry do controller theo tín hiệu retryable của parser — UI không biết).

**Lô L3.3 — hành vi nhập tin + chi tiết dòng** (screen_design "Hành vi nhập/sửa
tin", contract §6.4):

* **Form nhập/sửa ``user_note``** (``UserNoteDialog``): trường bắt buộc giờ
  đăng/loại tin/nội dung/đồng tiền, tùy chọn mức tác động + URL; thiếu trường
  bắt buộc → lỗi hiện trên form, KHÔNG gọi controller (không ghi DB); lỗi
  validate controller trả về hiện đúng từng trường, form không đóng.  Ghi qua
  ``NewsController.add_user_note``/``update_user_note`` (không tự dựng
  ``NewsItem``, không tính ``dedupe_key`` — S1/S2).
* **Sửa/xóa/toggle theo dòng** nằm trong dialog chi tiết dòng (D7 — không thêm
  nút toolbar, không thêm cột bảng đã đóng băng): tin ``source=user`` có "Sửa"
  + "Xóa", mọi dòng tin văn bản có toggle "Loại trừ"; dòng sự kiện không có
  (cờ ``excluded`` chỉ tồn tại ở ``news_items`` — §4.3).  Sau mỗi lượt ghi,
  bảng đọc lại qua `reload_rows()`.

Khai báo đọc-hiểu lô L3.3 (V2 — bên dưới, xem từng điểm):

* **D2 — giờ đăng theo UTC:** widget giờ của form thu UTC (``Qt.TimeSpec.UTC``),
  nhất quán với ``_display_time`` của bảng.
* **D3 — "Loại tin" cố định "Nhập tay":** combo chỉ có ``user_note``, không
  chào lựa chọn tự động (controller từ chối kind tự động — ``not_manual_note``).
* **D4 — "Đồng tiền" là danh sách mã:** control cho nhập tự do (phẩy ngăn cách),
  gợi ý lấy từ chính ``currency_combo`` của màn (không bịa danh sách tiền tệ).
* **D5 — combo "Mức tác động"** chỉ ``high``/``medium``/``low`` (``ImpactHint``)
  + mục trống đầu tiên cho trường tùy chọn.

Khai báo đọc-hiểu (V2):

* Bảng hợp nhất ``news_events`` + ``news_items`` theo thời gian — đúng bullet
  "Bảng tin" của screen_design; việc hợp nhất là trình bày, không phải tính
  toán nghiệp vụ.
* Bộ lọc là lọc HIỂN THỊ trên tập dòng đã đọc theo khoảng ngày; khoảng ngày
  đẩy xuống repository (``events_in_range``/``items_in_range``), các bộ lọc
  enum còn lại lọc tại chỗ (chúng trộn cả hai nguồn nên không đẩy xuống được).
* Màn đọc tin văn bản với ``exclude_flagged=False`` — nếu không, hàng
  ``excluded=1`` không bao giờ hiện ra để mang badge "Đã loại trừ"/để lọc
  theo trạng thái đó (screen_design yêu cầu cột Trạng thái hiển thị cờ này).
* Khi ``app`` không cấp ``news_controller`` (app giả của bộ test shell —
  ``tools/capture_ui_style_baseline._fake_app`` — không có thuộc tính này và
  file đó ngoài sổ điểm chạm), màn **không đọc gì** và hiện empty state: không
  tự dựng controller thật để tránh mở ``news.db`` trong test của màn khác.
* Bố cục dùng ``ResponsiveGrid`` (khuôn ``ui/responsive_row.py``) cho dãy bộ lọc
  và thanh công cụ: một hàng đầy đủ ở desktop, tự xuống nhiều hàng khi hẹp, nên
  sàn bề ngang của màn là bề ngang MỘT hàng compact — màn vừa 800px (điểm review
  của lô).  Combo/date-edit được đặt sàn bề ngang tường minh
  (``setMinimumWidth``) vì nhãn item dài (vd "ForexFactory (mã nguồn trang)")
  sẽ đẩy sàn vượt 800px nếu để mặc định.  Thanh công cụ 2 nút (đợt 3) càng
  không vượt sàn.
* Bảng đặt bề ngang cột tường minh (khuôn ``scanner_screen._configure_table_columns``):
  cột "Tiêu đề/Nội dung" giãn, các cột còn lại cố định đủ đọc trọn nhãn cột;
  cửa sổ hẹp thì bảng cuộn ngang (``ScrollBarAsNeeded``) thay vì bóp cột tới mức
  chữ bị cắt.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, time as clock_time

from PyQt6.QtCore import (
    QAbstractTableModel,
    QDate,
    QDateTime,
    QModelIndex,
    QTime,
    Qt,
    QThread,
    QUrl,
)
from PyQt6.QtGui import QColor, QDesktopServices, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from config.constants import SUPPORTED_SYMBOLS
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    ImpactHint,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    TrendVerdict,
)
from ui.layout_system import configure_table
from ui.responsive_row import ResponsiveGrid
from ui.rich_text import compile_rich_html, empty_state_html, set_rich_html
from ui.screens.shared import action_button, card, form_row, page_header
from ui.theme_manager import semantic_qcolor
from workers.news_worker import NewsReadWorker

# ---------------------------------------------------------------------------
# Từ điển hiển thị (S5 — screen_design d.1557, Owner duyệt 21/09/2026)
# ---------------------------------------------------------------------------

STATUS_TEXT: dict[str, str] = {
    "scheduled": "Chưa tới giờ",
    "released": "Đã có số liệu",
    "stale": "Thiếu số liệu",
}
EXCLUDED_TEXT = "Đã loại trừ"
KIND_TEXT: dict[str, str] = {
    "headline": "Headline",
    "statement": "Phát biểu",
    "user_note": "Nhập tay",
}
IMPACT_TEXT: dict[str, str] = {
    "high": "Cao",
    "medium": "Trung bình",
    "low": "Thấp",
    "non": "Không đáng kể",
}
SOURCE_TEXT: dict[str, str] = {
    "ff_json": "ForexFactory (lịch — dữ liệu cũ)",
    "ff_html": "ForexFactory (mã nguồn trang)",
    "google_news_rss": "Google News",
    "fxstreet_rss": "FXStreet",
    "investing_rss": "Investing",
    "fred": "FRED",
    "config_fallback": "Cấu hình dự phòng",
    "user": "Nhập tay",
    "import": "Nhập file (dữ liệu cũ)",
}

# Nhãn loại dòng sự kiện — bullet bộ lọc screen_design d.1551 + contract §2.
EVENT_TEXT = "Sự kiện"

# Vai trò màu semantic cho badge (screen_design: "badge theo semantic palette").
STATUS_ROLE: dict[str, str] = {
    "scheduled": "text_muted",
    "released": "success",
    "stale": "warning",
}
EXCLUDED_ROLE = "danger"
IMPACT_ROLE: dict[str, str] = {
    "high": "danger",
    "medium": "warning",
    "low": "info",
    "non": "text_muted",
}
DETAIL_ROLE = "info"
EMPTY_TONE = "muted"

# Nhãn khối "Bố cục" (nguyên văn screen_design).
COLUMN_LABELS: tuple[str, ...] = (
    "Thời gian",
    "Loại",
    "Nguồn",
    "Đồng tiền",
    "Tiêu đề/Nội dung",
    "Tác động",
    "Thực tế",
    "Trạng thái",
    "Chi tiết",
)
FILTER_LABELS: tuple[str, ...] = (
    "Loại tin",
    "Đồng tiền",
    "Tác động",
    "Nguồn",
    "Trạng thái",
    "Khoảng ngày",
)
TOOLBAR_LABELS: tuple[str, ...] = (
    "Dán mã nguồn trang",
    "Nhập tin",
    "AI nhận định xu hướng",
)
EMPTY_TEXT = "Không có tin trong khoảng lọc"
LOADING_TEXT = "Đang tải..."
DETAIL_TEXT = "Chi tiết"
ALL_PREFIX = "Tất cả"
NO_VALUE = "—"

# Nút gợi ý empty state (screen_design "Trạng thái tải và rỗng" d.1634-1635:
# "nới khoảng ngày / 'Dán mã nguồn trang' / 'Nhập tin'").  "Dán mã nguồn trang"
# = nút thanh công cụ thứ nhất (F4 — cùng nhãn, cùng handler `open_paste_dialog`);
# "Nhập tin" đi thẳng form nhập tay.
PASTE_SOURCE_TEXT = TOOLBAR_LABELS[0]
EMPTY_STATE_LABELS: tuple[str, ...] = (TOOLBAR_LABELS[0], TOOLBAR_LABELS[1])

# Nhãn dùng trong dialog chi tiết (đều đã có nguồn: nhãn cột hoặc câu chữ screen_design).
PROVENANCE_LABELS: tuple[str, ...] = ("Thời gian", "Nguồn", "Giờ fetch", "Liên kết")

# ---------------------------------------------------------------------------
# Từ điển lô L3.3 — form nhập/sửa tin (screen_design "Hành vi nhập/sửa tin"
# d.1593-1601).  Mọi chuỗi ở đây đều có nguồn đã đăng ký; không phát minh nhãn.
# ---------------------------------------------------------------------------

# Nhãn dialog/nút (nguồn: nhãn nút thanh công cụ đã đăng ký + khối "Bố cục" +
# chuỗi có sẵn của repo).
NOTE_DIALOG_TITLE = TOOLBAR_LABELS[1]  # "Nhập tin" (nhãn nút đã đăng ký)
EDIT_DIALOG_TITLE = "Sửa tin"  # screen_design d.1598 "Sửa/xóa"
EXCLUDE_TEXT = "Loại trừ"  # screen_design d.1598 "toggle Loại trừ"
EDIT_TEXT = "Sửa"  # screen_design d.1598 "Sửa/xóa"
DELETE_TEXT = "Xóa"  # screen_design d.1598 "Sửa/xóa"
SAVE_TEXT = "Lưu"  # chuỗi có sẵn repo (settings_screen d.198)
CANCEL_TEXT = "Hủy"  # chuỗi có sẵn repo (scanner_screen d.2351)
CLOSE_TEXT = "Đóng"  # chuỗi có sẵn repo (journal_screen d.1885)

# Nhãn trường form (nguyên văn screen_design d.1595-1596).
FORM_FIELD_LABELS: dict[str, str] = {
    "published_utc": "Giờ đăng",
    "kind": "Loại tin",
    "content": "Nội dung",
    "currencies": "Đồng tiền",
    "impact_hint": "Mức tác động",
    "url": "URL",
}
# Ánh xạ mã lý do (máy đọc, ``UserNoteFieldError.reason``) → thông báo tiếng Việt
# (tầng trình bày — L3; nguồn: controller docstring §6.4 + screen_design d.1597).
FORM_ERROR_TEXT: dict[str, str] = {
    "missing": "thiếu trường bắt buộc",
    "not_manual_note": "chỉ nhận loại tin nhập tay",
    "invalid_timestamp": "giờ đăng không đọc được",
    "invalid_currency": "thiếu mã đồng tiền hợp lệ",
    "invalid_impact_hint": "mức tác động không hợp lệ",
}

# ---------------------------------------------------------------------------
# Từ điển lô L3.5 — cửa sổ AI nhận định xu hướng (screen_design d.1621-1649 +
# bảng từ điển d.1570-1572; mọi chuỗi có nguồn đăng ký, không phát minh nhãn).
# ---------------------------------------------------------------------------
AI_TEXT = TOOLBAR_LABELS[2]  # "AI nhận định xu hướng" (nhãn nút đã đăng ký)
AI_SCOPE_LABEL = "Phạm vi"  # mockup d.1628
AI_SCOPE_HINT = "hoặc chuyển sang chọn 1 đồng tiền"  # mockup d.1628 (nguyên văn)
AI_COUNT_TEXT = "Cửa sổ tin: {window_days} ngày gần nhất — {count} tin/sự kiện liên quan"  # d.1629
AI_INSUFFICIENT_TEXT = "Không đủ dữ liệu nhận định"  # d.1642 (nguyên văn)
AI_ANALYZE_TEXT = "Nhận định"  # mockup d.1631
# Chuỗi có sẵn của repo (dashboard_screen d.1393) cho chỉ báo tiến trình.
AI_PROGRESS_TEXT = "Đang phân tích..."
AI_ADVISORY_TEXT = "⚠ Nhận định của AI chỉ để tham khảo — không tham gia bất cứ quy trình nào"  # d.1638 (nguyên văn)
AI_HISTORY_TEXT = "Lịch sử nhận định của phạm vi này (mới nhất trước)"  # d.1637 (nguyên văn)
AI_RESULT_HEADER_TEXT = "─ Kết quả (3 thẻ chân trời, theo ai_horizons trong chính sách) ─"  # d.1632
AI_EVIDENCE_TEXT = "Dẫn chứng"  # d.1633/1637 (từ vựng mockup)

# Từ điển verdict (screen_design d.1570-1572 — ĐÚNG TỪNG CHUỖI).
HORIZON_TEXT: dict[str, str] = {
    "short": "Ngắn hạn",
    "mid": "Trung hạn",
    "long": "Dài hạn",
}
DIRECTION_TEXT: dict[str, str] = {
    "bullish": "Tăng",
    "bearish": "Giảm",
    "neutral": "Trung lập",
    "insufficient_data": "Không đủ dữ liệu",
}
CONFIDENCE_TEXT: dict[str, str] = {
    "high": "Cao",
    "medium": "Trung bình",
    "low": "Thấp",
    "none": "Không có",
}
# Ký hiệu xu hướng (d.1633 "▲/▼/—") + vai trò màu semantic (V2): insufficient_data
# không có xu hướng → "—" cùng tông text_muted; bullish=success, bearish=danger.
DIRECTION_SYMBOL: dict[str, str] = {
    "bullish": "▲",
    "bearish": "▼",
    "neutral": "—",
    "insufficient_data": "—",
}
DIRECTION_ROLE: dict[str, str] = {
    "bullish": "success",
    "bearish": "danger",
    "neutral": "text_muted",
    "insufficient_data": "text_muted",
}
AI_HISTORY_LIMIT = 5  # đọc-hiểu trình bày (B5 — không phải giá trị vận hành)

# ---------------------------------------------------------------------------
# Từ điển lô F4 — dialog dán mã nguồn 2 pha + panel thiếu số liệu
# (screen_design từ điển d.1577 + "Hành vi dán mã nguồn trang ForexFactory"
# d.1579-1617 + "Bố cục" d.1544-1547; mọi chuỗi có nguồn đăng ký — không phát
# minh nhãn; L3: chuỗi thân thiện cho lỗi parser đặt TẠI đây, không trong
# services).
# ---------------------------------------------------------------------------

# Bốn nhãn trạng thái dòng bảng xem trước (d.1577 — ĐÚNG TỪNG CHUỖI; dẫn xuất,
# không persist).
PREVIEW_STATUS_TEXT: dict[str, str] = {
    "new": "Mới",
    "will_update": "Sẽ cập nhật",
    "conflict_keep_manual": "Xung đột — giữ nhập tay",
    "edited": "Đã sửa",
}
# Vai trò màu semantic cho badge (screen_design: "badge theo semantic palette").
PREVIEW_STATUS_ROLE: dict[str, str] = {
    "new": "info",
    "will_update": "success",
    "conflict_keep_manual": "warning",
    "edited": "danger",
}

PASTE_DIALOG_TITLE = TOOLBAR_LABELS[0]  # "Dán mã nguồn trang" (nhãn nút đã đăng ký)
PASTE_PARSE_TEXT = "Bóc tách"  # d.1590
PASTE_COMMIT_TEXT = "Cập nhật"  # d.1606
PASTE_FILE_TEXT = "Chọn file .html"  # d.1588 "nút chọn file `.html` đã lưu"
# Hướng dẫn 3 bước (d.1588-1590 — nguyên văn ba cụm, mỗi cụm một dòng).
PASTE_STEP_TEXTS: tuple[str, ...] = (
    "Mở trang lịch FF",
    "Xem mã nguồn trang, chọn tất cả, sao chép",
    "Dán vào đây",
)
# Ánh xạ mã lỗi có kiểu của parser → thông báo tiếng Việt (L3 — nguồn docstring
# ff_source_parser.py d.114-118; không đặt chuỗi hiển thị trong services).
PARSE_ERROR_TEXT: dict[str, str] = {
    "not_found": "source không chứa dữ liệu lịch",
    "malformed": "JSON lịch hỏng/cắt cụt",
}
# Cột bảng xem trước (d.1594-1596).  CHỈ cột "Thực tế" (actual) sửa được — QĐ-F6/đợt 4.
_PREVIEW_COLUMNS: tuple[tuple[str, str], ...] = (
    ("event_time_utc", "Thời gian (UTC)"),
    ("currency", "Đồng tiền"),
    ("title", "Sự kiện"),
    ("impact", "Tác động"),
    ("forecast", "Dự báo"),
    ("previous", "Kỳ trước"),
    ("actual", "Thực tế"),
    ("disposition", "Trạng thái dòng"),
)
PREVIEW_COLUMN_LABELS: tuple[str, ...] = tuple(label for _key, label in _PREVIEW_COLUMNS)
PREVIEW_ACTUAL_COLUMN = "Thực tế"
_PREVIEW_COLUMN_WIDTHS: dict[str, int] = {
    "event_time_utc": 130,
    "currency": 90,
    "impact": 90,
    "forecast": 100,
    "previous": 100,
    "actual": 100,
    "disposition": 180,
}
_PREVIEW_STRETCH_COLUMN = "title"

PASTE_RATES_TEXT = "Số quan sát lãi suất bóc được: {count}"  # d.1598
PASTE_SUMMARY_TEXT = "Mới: {inserted} · Cập nhật: {updated} · Xung đột: {conflicts} · Lãi suất: {rates}"  # d.1611-1612
# Chỉ báo tiến trình (d.1618-1620 "pha 'Bóc tách' hiện progress... pha ghi hiện
# progress") + nhắc form (V2 — khuyên dùng trình bày, không phải chuỗi enum).
PASTE_PARSE_PROGRESS_TEXT = "Đang bóc tách..."
PASTE_COMMIT_PROGRESS_TEXT = "Đang ghi..."
PASTE_FILE_LOAD_PROGRESS_TEXT = "Đang đọc file..."
PASTE_EMPTY_SOURCE_TEXT = "Hãy dán mã nguồn trang vào ô bên trên trước khi bóc tách."

# Panel "Sự kiện đang thiếu số liệu" (d.1544-1545, d.1613-1617).
PANEL_TITLE_TEXT = "Sự kiện đang thiếu số liệu"
OPEN_FF_TEXT = "Mở trang ForexFactory"  # d.1614

# ---------------------------------------------------------------------------
# URL trang lịch tuần ForexFactory (QĐ-F10 — căn cứ code legacy
# forex_factory_client.py d.57-58: this/next + interest_rate_service.py d.89-90:
# this/last).  Chỉ mở bằng trình duyệt ngoài (QDesktopServices.openUrl) — app
# không phát request mạng nào tới ForexFactory (contract §6.1 đợt 3, QĐ-F4).
# ---------------------------------------------------------------------------

FF_CALENDAR_BASE_URL = "https://www.forexfactory.com/calendar"
FF_WEEK_THIS_URL = f"{FF_CALENDAR_BASE_URL}?week=this"
FF_WEEK_NEXT_URL = f"{FF_CALENDAR_BASE_URL}?week=next"
FF_WEEK_LAST_URL = f"{FF_CALENDAR_BASE_URL}?week=last"


def _week_start_utc(moment: datetime) -> datetime:
    """Thứ 2 00:00 (UTC) của tuần chứa một mốc — tuần = Thứ 2 → Chủ nhật (QĐ-F10)."""
    moment_utc = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    moment_utc = moment_utc.astimezone(UTC)
    monday = moment_utc - timedelta(days=moment_utc.weekday())
    return datetime.combine(monday.date(), clock_time.min, tzinfo=UTC)


def ff_week_url_for_event(event_time_utc: str, *, now: datetime | None = None) -> str:
    """URL trang lịch tuần FF tương ứng vị trí tuần của sự kiện (QĐ-F10).

    Vị trí tuần tính theo UTC từ ``event_time_utc`` (tuần = Thứ 2 → Chủ nhật):
    tuần hiện tại → ``?week=this``; kế sau → ``?week=next``; liền trước →
    ``?week=last``; xa hơn → trang mặc định (declared fallback — legacy không
    có URL tuần tùy ý).  ``now`` là seam kiểm thử; luôn mở qua
    ``QDesktopServices.openUrl`` (chỉ mở link, không fetch)."""
    try:
        event_week = _week_start_utc(
            datetime.fromisoformat(str(event_time_utc).replace("Z", "+00:00"))
        )
    except ValueError:
        return FF_CALENDAR_BASE_URL
    moment = now if now is not None else datetime.now(UTC)
    current_week = _week_start_utc(moment)
    delta_weeks = (event_week.date() - current_week.date()).days // 7
    if delta_weeks == 0:
        return FF_WEEK_THIS_URL
    if delta_weeks == 1:
        return FF_WEEK_NEXT_URL
    if delta_weeks == -1:
        return FF_WEEK_LAST_URL
    return FF_CALENDAR_BASE_URL


def _read_source_file(path: str) -> str:
    """Đọc file `.html` đã lưu — chạy TRONG worker (không block GUI; d.1588)."""
    with open(path, mode="r", encoding="utf-8", errors="replace") as fh:
        return fh.read()

EVENT_ROW = "event"
ITEM_ROW = "item"

# Tên object (ASCII) cho combo lọc — dùng cho QSS/kiểm thử.
_COMBO_NAMES: dict[str, str] = {
    FILTER_LABELS[0]: "Kind",
    FILTER_LABELS[1]: "Currency",
    FILTER_LABELS[2]: "Impact",
    FILTER_LABELS[3]: "Source",
    FILTER_LABELS[4]: "Status",
}


# ---------------------------------------------------------------------------
# Dòng bảng (mô hình trình bày — hợp nhất 2 nguồn, không phải mô hình miền)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NewsRow:
    """Một dòng của bảng tin: sự kiện lịch kinh tế hoặc tin văn bản.

    Giữ nguyên đối tượng miền tương ứng để dialog chi tiết đọc provenance
    (``source``/``fetched_at``/``raw_json``/``url``) mà không phải đọc lại DB.
    """

    row_type: str
    timestamp_utc: str
    source: str
    currencies: tuple[str, ...]
    title: str
    impact: str | None
    actual: str | None
    status: str | None
    excluded: bool
    event: CalendarEvent | None = None
    item: NewsItem | None = None

    @property
    def kind(self) -> str:
        """Giá trị ``kind`` hiển thị: sự kiện có nhãn riêng, tin văn bản theo enum."""
        if self.row_type == EVENT_ROW:
            return EVENT_TEXT
        return self.item.kind.value if self.item is not None else ""

    @property
    def kind_value(self) -> str:
        """Giá trị lọc theo bullet bộ lọc (``event`` cho sự kiện, còn lại là enum)."""
        if self.row_type == EVENT_ROW:
            return EVENT_ROW
        return self.item.kind.value if self.item is not None else ""


def _row_from_event(event: CalendarEvent) -> NewsRow:
    return NewsRow(
        row_type=EVENT_ROW,
        timestamp_utc=event.event_time_utc,
        source=event.source.value,
        currencies=(event.currency,) if event.currency else (),
        title=event.title,
        impact=event.impact.value,
        actual=event.actual,
        status=event.status.value,
        excluded=False,
        event=event,
    )


def _row_from_item(item: NewsItem) -> NewsRow:
    return NewsRow(
        row_type=ITEM_ROW,
        timestamp_utc=item.published_utc,
        source=item.source.value,
        currencies=tuple(item.currencies),
        title=item.title,
        impact=item.impact_hint.value if item.impact_hint is not None else None,
        actual=None,
        status=None,
        excluded=item.excluded,
        item=item,
    )


def build_rows(
    events: list[CalendarEvent], items: list[NewsItem]
) -> list[NewsRow]:
    """Hợp nhất hai nguồn thành dòng bảng, sắp theo thời gian (screen_design bullet "Bảng tin").

    Cùng mốc thời gian thì xếp theo loại dòng rồi tiêu đề để thứ tự ổn định.
    """
    rows = [_row_from_event(event) for event in events]
    rows.extend(_row_from_item(item) for item in items)
    rows.sort(key=lambda row: (row.timestamp_utc, row.row_type, row.title))
    return rows


def filter_rows(
    rows: list[NewsRow],
    *,
    kind: str | None = None,
    currency: str | None = None,
    impact: str | None = None,
    source: str | None = None,
    status: str | None = None,
) -> list[NewsRow]:
    """Lọc hiển thị theo tập giá trị enum của contract (S5).

    ``None`` = không lọc.  ``status`` nhận ba trạng thái sự kiện hoặc
    ``"excluded"`` cho cờ loại trừ của tin văn bản — đúng hai thứ cột Trạng thái
    hiển thị.
    """
    return [
        row for row in rows if _row_matches(row, kind, currency, impact, source, status)
    ]


def _row_matches(
    row: NewsRow,
    kind: str | None,
    currency: str | None,
    impact: str | None,
    source: str | None,
    status: str | None,
) -> bool:
    if kind is not None and row.kind_value != kind:
        return False
    if currency is not None and currency not in row.currencies:
        return False
    if impact is not None and row.impact != impact:
        return False
    if source is not None and row.source != source:
        return False
    if status is not None:
        if status == "excluded":
            return row.excluded
        return row.status == status
    return True


# ---------------------------------------------------------------------------
# Table model (khuôn JournalTableModel)
# ---------------------------------------------------------------------------

# Bề ngang từng cột (khuôn scanner_screen._configure_table_columns): cột tiêu
# đề giãn theo chỗ trống, các cột còn lại cố định đủ để đọc trọn nhãn; bảng
# cuộn ngang khi cửa sổ hẹp — không bóp cột tới mức chữ bị cắt.
_COLUMN_WIDTHS: dict[str, int] = {
    "timestamp_utc": 130,
    "kind": 90,
    "source": 160,
    "currencies": 90,
    "impact": 90,
    "actual": 80,
    "status": 110,
    "detail": 80,
}
_STRETCH_COLUMN = "title"

_COLUMNS: tuple[tuple[str, str], ...] = (
    ("timestamp_utc", COLUMN_LABELS[0]),
    ("kind", COLUMN_LABELS[1]),
    ("source", COLUMN_LABELS[2]),
    ("currencies", COLUMN_LABELS[3]),
    ("title", COLUMN_LABELS[4]),
    ("impact", COLUMN_LABELS[5]),
    ("actual", COLUMN_LABELS[6]),
    ("status", COLUMN_LABELS[7]),
    ("detail", COLUMN_LABELS[8]),
)


class NewsTableModel(QAbstractTableModel):
    """Bảng tin hợp nhất: DisplayRole + ForegroundRole (semantic) + ToolTipRole."""

    COLUMNS = _COLUMNS

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[NewsRow] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = self.COLUMNS[index.column()][0]
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(row, key)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if key in {"timestamp_utc", "kind", "source", "currencies", "impact", "actual", "status", "detail"}:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if role == Qt.ItemDataRole.ForegroundRole:
            return self._foreground(row, key)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(row, key)
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section][1]
        return str(section + 1)

    def set_rows(self, rows: list[NewsRow]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def row_at(self, index: int) -> NewsRow | None:
        if 0 <= index < len(self.rows):
            return self.rows[index]
        return None

    # -- cell rendering ---------------------------------------------------------

    def _display(self, row: NewsRow, key: str) -> str:
        if key == "timestamp_utc":
            return _display_time(row.timestamp_utc)
        if key == "kind":
            return KIND_TEXT.get(row.kind, row.kind) if row.row_type == ITEM_ROW else EVENT_TEXT
        if key == "source":
            return SOURCE_TEXT.get(row.source, row.source or NO_VALUE)
        if key == "currencies":
            return ", ".join(row.currencies) if row.currencies else NO_VALUE
        if key == "title":
            return row.title or NO_VALUE
        if key == "impact":
            if row.impact is None:
                return NO_VALUE
            return IMPACT_TEXT.get(row.impact, row.impact)
        if key == "actual":
            return row.actual or NO_VALUE
        if key == "status":
            if row.excluded:
                return EXCLUDED_TEXT
            if row.status is None:
                return NO_VALUE
            return STATUS_TEXT.get(row.status, row.status)
        if key == "detail":
            return DETAIL_TEXT
        return NO_VALUE

    def _foreground(self, row: NewsRow, key: str) -> QColor | None:
        if key == "detail":
            return semantic_qcolor(DETAIL_ROLE)
        if key == "status":
            if row.excluded:
                return semantic_qcolor(EXCLUDED_ROLE)
            role = STATUS_ROLE.get(row.status or "")
            return semantic_qcolor(role) if role else None
        if key == "impact" and row.impact is not None:
            role = IMPACT_ROLE.get(row.impact)
            return semantic_qcolor(role) if role else None
        return None

    def _tooltip(self, row: NewsRow, key: str) -> str | None:
        if key == "title":
            return row.title
        if key == "status":
            if row.excluded:
                return EXCLUDED_TEXT
            return STATUS_TEXT.get(row.status or "")
        if key == "detail":
            return DETAIL_TEXT
        return None


def _display_time(value: str) -> str:
    """Hiển thị mốc thời gian của dòng (giữ nguyên dạng ISO đã lưu nếu không đọc được)."""
    if not value:
        return NO_VALUE
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%d/%m/%Y %H:%M")


def _iso_to_qdatetime(value: str) -> QDateTime | None:
    """Đọc một mốc ISO-8601 (UTC) thành ``QDateTime`` mang wall-time UTC."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC).replace(tzinfo=None)
    stamp = QDateTime(QDate(moment.year, moment.month, moment.day), QTime(moment.hour, moment.minute, moment.second))
    stamp.setTimeSpec(Qt.TimeSpec.UTC)
    return stamp


# ---------------------------------------------------------------------------
# Form nhập/sửa tin ``user_note`` (screen_design "Hành vi nhập/sửa tin", §6.4)
# ---------------------------------------------------------------------------


class UserNoteDialog(QDialog):
    """Form nhập/sửa một tin ``user_note`` — validate hiện lỗi NGAY TRÊN FORM.

    Trường bắt buộc: giờ đăng, loại tin, nội dung, đồng tiền; tùy chọn: mức tác
    động (``impact_hint``) + URL (screen_design d.1595-1596).  Loại tin cố định
    "Nhập tay" (D3); giờ đăng thu UTC (D2).  Thiếu trường bắt buộc → hiện lỗi
    từng trường và KHÔNG gọi controller (không ghi DB); lỗi validate controller
    trả về hiện lên đúng trường, form KHÔNG đóng.  Draft hợp lệ đi qua
    ``NewsController.add_user_note`` (nhập) hoặc ``update_user_note`` (sửa — D1,
    không tự dựng model, không tính ``dedupe_key``).
    """

    def __init__(
        self,
        controller,
        parent=None,
        *,
        prefill: CalendarEvent | None = None,
        editing_item: NewsItem | None = None,
        currencies: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._prefill = prefill
        self._editing_item = editing_item
        self._field_errors: dict[str, QLabel] = {}
        self._empty_moment = QDateTime(QDate(2000, 1, 1), QTime(0, 0))
        self._empty_moment.setTimeSpec(Qt.TimeSpec.UTC)
        self.setObjectName("NewsNoteDialog")
        self.setWindowTitle(EDIT_DIALOG_TITLE if editing_item is not None else NOTE_DIALOG_TITLE)
        self._build(currencies or [])
        self._fill_from_source()

    # -- dựng form --------------------------------------------------------------

    def _build(self, currencies: list[str]) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(10)

        # Giờ đăng (UTC — D2): giá trị đặc biệt (bằng minimum) hiển thị rỗng =
        # "chưa nhập", nên trường bắt buộc này thực sự có thể thiếu.
        self.time_edit = QDateTimeEdit(self._empty_moment)
        self.time_edit.setObjectName("NewsNoteTime")
        self.time_edit.setTimeSpec(Qt.TimeSpec.UTC)
        self.time_edit.setMinimumDateTime(self._empty_moment)
        self.time_edit.setSpecialValueText("")
        self.time_edit.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.time_edit.setCalendarPopup(True)

        # Loại tin cố định "Nhập tay" (D3).
        self.kind_combo = QComboBox()
        self.kind_combo.setObjectName("NewsNoteKind")
        self.kind_combo.addItem(KIND_TEXT["user_note"], "user_note")
        self.kind_combo.setEnabled(False)

        self.content_edit = QTextEdit()
        self.content_edit.setObjectName("NewsNoteContent")
        self.content_edit.setAcceptRichText(False)

        # Đồng tiền (D4): danh sách mã, cho nhập tự do; gợi ý lấy từ dữ liệu màn.
        self.currency_edit = QComboBox()
        self.currency_edit.setObjectName("NewsNoteCurrencies")
        self.currency_edit.setEditable(True)
        self.currency_edit.setMinimumWidth(120)
        self.currency_edit.addItem("")
        for code in currencies:
            self.currency_edit.addItem(code)

        # Mức tác động (D5): trống (tùy chọn) + high/medium/low (không "non").
        self.impact_combo = QComboBox()
        self.impact_combo.setObjectName("NewsNoteImpact")
        self.impact_combo.setMinimumWidth(120)
        self.impact_combo.addItem("", None)
        for member in ImpactHint:
            self.impact_combo.addItem(IMPACT_TEXT[member.value], member.value)

        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("NewsNoteUrl")

        self.form_error_label = QLabel("")
        self.form_error_label.setObjectName("NewsFormError")
        self.form_error_label.setWordWrap(True)
        self.form_error_label.setVisible(False)

        root.addWidget(self._field_block("Giờ đăng", self.time_edit, "published_utc"))
        root.addWidget(self._field_block("Loại tin", self.kind_combo, "kind"))
        root.addWidget(self._field_block("Nội dung", self.content_edit, "content"))
        root.addWidget(self._field_block("Đồng tiền", self.currency_edit, "currencies"))
        root.addWidget(self._field_block("Mức tác động", self.impact_combo, "impact_hint"))
        root.addWidget(self._field_block("URL", self.url_edit, "url"))
        root.addWidget(self.form_error_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self.cancel_button = action_button(CANCEL_TEXT, icon="x", icon_role="text", icon_disabled_role="text")
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = action_button(
            SAVE_TEXT, primary=True, color="success", icon="save", icon_role="selection_text", icon_disabled_role="selection_text"
        )
        self.save_button.clicked.connect(self._on_save_clicked)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        root.addLayout(buttons)

    def _field_block(self, label: str, control: QWidget, field: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(form_row(label, control))
        error = QLabel("")
        error.setObjectName("NewsFormError")
        error.setWordWrap(True)
        error.setVisible(False)
        layout.addWidget(error)
        self._field_errors[field] = error
        return container

    # -- nạp giá trị ban đầu -----------------------------------------------------

    def _fill_from_source(self) -> None:
        if self._editing_item is not None:
            self._load_item(self._editing_item)
        elif self._prefill is not None:
            self._load_prefill(self._prefill)

    def _load_prefill(self, event: CalendarEvent) -> None:
        """Điền sẵn từ sự kiện liên quan (D9): giờ đăng/đồng tiền/nội dung."""
        self._set_time(event.event_time_utc)
        self.content_edit.setPlainText(event.title or "")
        self._set_currencies([event.currency] if event.currency else [])

    def _load_item(self, item: NewsItem) -> None:
        self._set_time(item.published_utc)
        self.content_edit.setPlainText(item.content or item.title or "")
        self._set_currencies(list(item.currencies))
        if item.impact_hint is not None:
            self._select_data(self.impact_combo, item.impact_hint.value)
        if item.url:
            self.url_edit.setText(item.url)

    def _set_time(self, value: str) -> None:
        stamp = _iso_to_qdatetime(value)
        if stamp is not None:
            self.time_edit.setDateTime(stamp)

    def _set_currencies(self, codes: list[str]) -> None:
        self.currency_edit.setCurrentText(", ".join(code for code in codes if code))

    @staticmethod
    def _select_data(combo: QComboBox, data: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == data:
                combo.setCurrentIndex(index)
                return

    # -- đọc/validate/ghi --------------------------------------------------------

    def _time_missing(self) -> bool:
        return self.time_edit.dateTime() <= self.time_edit.minimumDateTime()

    def time_value(self) -> datetime | None:
        """Giờ đăng đang nhập (UTC) — ``None`` khi trường còn trống."""
        if self._time_missing():
            return None
        moment = self.time_edit.dateTime().toPyDateTime()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(UTC)

    def currency_values(self) -> list[str]:
        """Danh sách mã đồng tiền đang nhập (phẩy ngăn cách) — D4."""
        text = self.currency_edit.currentText()
        return [code.strip() for code in text.split(",") if code.strip()]

    def field_error_text(self, field: str) -> str:
        """Lỗi đang hiển thị ở một trường (rỗng khi trường hợp lệ) — cho test."""
        label = self._field_errors.get(field)
        return label.text() if label is not None else ""

    def form_error_text(self) -> str:
        return self.form_error_label.text()

    def _presence_errors(self) -> dict[str, str]:
        """Kiểm tra hiện diện trường bắt buộc NGAY TRÊN FORM (không gọi controller)."""
        errors: dict[str, str] = {}
        if self._time_missing():
            errors["published_utc"] = "missing"
        if not self.content_edit.toPlainText().strip():
            errors["content"] = "missing"
        if not self.currency_values():
            errors["currencies"] = "missing"
        return errors

    def _draft_kwargs(self) -> dict[str, object]:
        return {
            "kind": NewsItemKind.USER_NOTE.value,
            "published_utc": self.time_value(),
            "content": self.content_edit.toPlainText().strip(),
            "currencies": self.currency_values(),
            "url": self.url_edit.text().strip() or None,
            "impact_hint": self.impact_combo.currentData(),
        }

    def _on_save_clicked(self) -> None:
        presence = self._presence_errors()
        if presence:
            self._show_errors(presence)
            return
        try:
            if self._editing_item is not None:
                result = self._controller.update_user_note(self._editing_item.id, **self._draft_kwargs())
            else:
                result = self._controller.add_user_note(**self._draft_kwargs())
        except Exception as exc:
            self._show_errors({"_form": str(exc)})
            return
        if getattr(result, "ok", False):
            self.accept()
        else:
            self._show_errors({error.field: error.reason for error in result.errors})

    def _show_errors(self, errors: dict[str, str]) -> None:
        for field, label in self._field_errors.items():
            reason = errors.get(field)
            if reason:
                label.setText(
                    f"{FORM_FIELD_LABELS.get(field, field)}: {FORM_ERROR_TEXT.get(reason, reason)}"
                )
                label.setVisible(True)
            else:
                label.clear()
                label.setVisible(False)
        form_reason = errors.get("_form")
        if form_reason:
            self.form_error_label.setText(form_reason)
            self.form_error_label.setVisible(True)
        else:
            self.form_error_label.clear()
            self.form_error_label.setVisible(False)


# ---------------------------------------------------------------------------
# Cửa sổ AI nhận định xu hướng (screen_design d.1621-1649; contract §9.1-§9.2)
# ---------------------------------------------------------------------------


class AiTrendDialog(QDialog):
    """Cửa sổ AI nhận định xu hướng — 520×640, không modal toàn app (d.1624).

    * Phạm vi: một combo chứa các cặp tiền ``SUPPORTED_SYMBOLS`` (tiêu thụ, không
      bịa danh sách) rồi đến từng đồng tiền rút từ chính danh sách cặp (V2 —
      "hoặc chuyển sang chọn 1 đồng tiền", d.1628).
    * Dòng đếm qua ``controller.ai_scope_preview`` (KHÔNG gọi AI — §9.1 bước 2);
      dưới ``ai_min_items`` hiện chuỗi d.1642 và nút "Nhận định" không gọi AI
      (fail-closed, B4).
    * Lời gọi AI chạy trong worker nền (``NewsReadWorker`` — khuôn worker D10
      D10 của màn): lúc chờ disable nút "Nhận định" + chỉ báo tiến trình
      (d.1615-1616), không block GUI, không processEvents.
    * Kết quả = 3 thẻ chân trời (nhãn từ điển d.1570-1572, ký hiệu ▲/▼/— màu
      semantic); lỗi provider/parser hiện thông báo thân thiện (d.1644-1645).
    * Dẫn chứng bấm được → đóng dialog rồi nhảy dòng bảng (d.1646-1647).
    * Cảnh báo advisory (d.1638) THƯỜNG TRỰC — không phải tooltip.
    * Modal WindowModal (d.1624 "không modal toàn app").
    """

    def __init__(self, controller, on_evidence, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._on_evidence = on_evidence
        self._preview = None
        self._ai_thread: QThread | None = None
        self._ai_worker: NewsReadWorker | None = None
        self._cards: dict[str, dict[str, object]] = {}
        self.setObjectName("NewsAiDialog")
        self.setWindowTitle(AI_TEXT)
        self.resize(520, 640)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self._build()
        self._on_scope_changed()

    # -- dựng form ----------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(8)

        scope_row = QHBoxLayout()
        scope_row.setSpacing(8)
        scope_label = QLabel(AI_SCOPE_LABEL)
        scope_label.setObjectName("CardDetail")
        scope_row.addWidget(scope_label)
        self._scope_combo = QComboBox()
        self._scope_combo.setObjectName("NewsAiScope")
        self._scope_combo.setMinimumWidth(220)
        self._fill_scope_combo()
        self._scope_combo.currentIndexChanged.connect(lambda _i: self._on_scope_changed())
        scope_row.addWidget(self._scope_combo, 1)
        root.addLayout(scope_row)

        hint = QLabel(AI_SCOPE_HINT)
        hint.setObjectName("CardDetail")
        root.addWidget(hint)

        self._count_label = QLabel("")
        self._count_label.setObjectName("NewsAiCount")
        self._count_label.setWordWrap(True)
        root.addWidget(self._count_label)

        self._status_label = QLabel("")
        self._status_label.setObjectName("NewsAiStatus")
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

        self._analyze_button = action_button(AI_ANALYZE_TEXT, primary=True, color="success")
        self._analyze_button.clicked.connect(self._on_analyze_clicked)

        header = QLabel(AI_RESULT_HEADER_TEXT)
        header.setObjectName("CardDetail")
        root.addWidget(header)
        for horizon in ("short", "mid", "long"):
            card = self._make_card(horizon)
            root.addWidget(card["frame"])
            self._cards[horizon] = card

        history_header = QLabel(AI_HISTORY_TEXT)
        history_header.setObjectName("CardDetail")
        root.addWidget(history_header)
        history_widget = QWidget()
        self._history_layout = QVBoxLayout(history_widget)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(2)
        root.addWidget(history_widget, 1)

        root.addWidget(self._analyze_button)
        advisory = QLabel(AI_ADVISORY_TEXT)
        advisory.setObjectName("NewsAiAdvisory")
        advisory.setWordWrap(True)
        root.addWidget(advisory)

    def _make_card(self, horizon: str) -> dict[str, object]:
        """Một thẻ chân trời: header (hướng + ký hiệu màu semantic), confidence,
        lập luận, hàng dẫn chứng bấm được.

        Màu semantic của hướng tô qua QPalette (không dùng `style=` HTML hay
        setStyleSheet — giữ bộ đếm nợ UI style của file mới bằng 0, khuôn
        docs/ui/style/ui-style-baseline.json)."""
        frame = QFrame()
        frame.setObjectName(f"NewsAiCard{horizon.capitalize()}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header = QLabel("")
        header.setObjectName(f"NewsAi{horizon.capitalize()}Header")
        header.setWordWrap(False)
        header_row.addWidget(header)
        direction = QLabel("")
        direction.setObjectName(f"NewsAi{horizon.capitalize()}Direction")
        header_row.addWidget(direction)
        header_row.addStretch(1)
        layout.addLayout(header_row)
        conf = QLabel("")
        conf.setObjectName("CardDetail")
        layout.addWidget(conf)
        rationale = QLabel("")
        rationale.setObjectName("CardValue")
        rationale.setWordWrap(True)
        rationale.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(rationale)
        evidence_row = QWidget()
        ev_layout = QHBoxLayout(evidence_row)
        ev_layout.setContentsMargins(0, 0, 0, 0)
        ev_layout.setSpacing(6)
        layout.addWidget(evidence_row)
        frame.setVisible(False)
        return {
            "frame": frame,
            "header": header,
            "direction": direction,
            "conf": conf,
            "rationale": rationale,
            "layout": ev_layout,
        }

    def _fill_scope_combo(self) -> None:
        """Các cặp tiền ``SUPPORTED_SYMBOLS`` rồi đến từng đồng tiền rút từ
        chính danh sách cặp (V2 — không bịa danh sách)."""
        for symbol in SUPPORTED_SYMBOLS:
            self._scope_combo.addItem(symbol, ("pair", symbol))
        seen: set[str] = set()
        for symbol in SUPPORTED_SYMBOLS:
            for code in symbol.split("/"):
                code = code.strip()
                if code and code not in seen:
                    seen.add(code)
                    self._scope_combo.addItem(code, ("currency", code))

    def _current_scope(self) -> tuple[str, str] | None:
        data = self._scope_combo.currentData()
        if data is None:
            return None
        return (str(data[0]), str(data[1]))

    # -- dòng đếm + lịch sử (không gọi AI) -----------------------------------

    def _on_scope_changed(self) -> None:
        """Cập nhật dòng đếm (§9.1 bước 2 — KHÔNG gọi AI) + lịch sử."""
        scope = self._current_scope()
        if scope is None:
            return
        try:
            self._preview = self._controller.ai_scope_preview(scope[0], scope[1])
        except Exception:
            self._preview = None
            self._count_label.clear()
            self._status_label.setText(AI_INSUFFICIENT_TEXT)
            return
        self._update_count_line()
        self._load_history()

    def _update_count_line(self) -> None:
        preview = self._preview
        if preview is None:
            return
        count = preview.event_count + preview.item_count
        self._count_label.setText(
            AI_COUNT_TEXT.format(window_days=preview.window_days, count=count)
        )
        if preview.insufficient:
            # d.1642 — fail-closed: không gọi AI.
            self._status_label.setText(AI_INSUFFICIENT_TEXT)
        elif self._status_label.text() == AI_PROGRESS_TEXT:
            # Sau lượt nhận định: chỉ xóa trạng thái "đang phân tích" — lỗi/kết
            # quả vừa hiện không bị dòng đếm làm mất (V2).
            self._status_label.clear()

    def _load_history(self) -> None:
        """Lịch sử nhận định của phạm vi này, mới nhất trước (d.1637) — limit
        là hằng trình bày (B5: không phải giá trị vận hành)."""
        self._clear_layout(self._history_layout)
        scope = self._current_scope()
        if scope is None:
            return
        try:
            verdicts = self._controller.verdicts_for(scope[0], scope[1], AI_HISTORY_LIMIT)
        except Exception:
            return
        for verdict in verdicts:
            label = QLabel(self._history_line(verdict))
            label.setObjectName("CardDetail")
            label.setWordWrap(True)
            self._history_layout.addWidget(label)

    @staticmethod
    def _history_line(verdict: TrendVerdict) -> str:
        return (
            f"{_display_time(verdict.created_at)} · "
            f"{HORIZON_TEXT.get(verdict.horizon.value, verdict.horizon.value)} · "
            f"{DIRECTION_TEXT.get(verdict.direction.value, verdict.direction.value)} · "
            f"{CONFIDENCE_TEXT.get(verdict.confidence.value, verdict.confidence.value)}"
        )

    # -- lượt nhận định (worker nền — khuôn D10) -------------------------------

    def _on_analyze_clicked(self) -> None:
        preview = self._preview
        if preview is None or preview.insufficient:
            # Fail-closed: dưới ai_min_items → hiện d.1642, KHÔNG gọi AI (B4).
            self._status_label.setText(AI_INSUFFICIENT_TEXT)
            return
        self._start_analysis()

    def _start_analysis(self) -> None:
        scope = self._current_scope()
        if scope is None or self._ai_worker is not None:
            return
        self._analyze_button.setEnabled(False)
        self._scope_combo.setEnabled(False)
        self._status_label.setText(AI_PROGRESS_TEXT)  # d.1615-1616: progress + disable
        thread = QThread(self)
        controller = self._controller
        worker = NewsReadWorker(lambda: controller.analyze_trend(scope[0], scope[1]))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_ai_succeeded)
        worker.failed.connect(self._on_ai_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._on_ai_worker_done)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._forget_ai_thread(thread))
        self._ai_thread = thread
        self._ai_worker = worker
        thread.start()

    def _forget_ai_thread(self, thread: QThread) -> None:
        if self._ai_thread is thread:
            self._ai_thread = None
            self._ai_worker = None

    def _on_ai_succeeded(self, payload) -> None:
        if getattr(payload, "insufficient", False):
            self._status_label.setText(AI_INSUFFICIENT_TEXT)
            return
        if not payload.ok:
            self._status_label.setText(payload.error_message or AI_TEXT)
            self._clear_result()
            return
        self._status_label.clear()
        self._render_verdicts(payload.verdicts)

    def _on_ai_failed(self, message: str) -> None:
        self._status_label.setText(message)
        self._clear_result()

    def _on_ai_worker_done(self) -> None:
        self._analyze_button.setEnabled(True)
        self._scope_combo.setEnabled(True)
        self._on_scope_changed()  # dòng đếm + lịch sử sau lượt nhận định

    # -- kết quả --------------------------------------------------------------

    def _render_verdicts(self, verdicts) -> None:
        self._clear_result()
        by_horizon = {verdict.horizon.value: verdict for verdict in verdicts}
        for horizon, card in self._cards.items():
            verdict = by_horizon.get(horizon)
            if verdict is None:
                continue
            role = DIRECTION_ROLE.get(verdict.direction.value, "text_muted")
            color = semantic_qcolor(role)
            symbol = DIRECTION_SYMBOL.get(verdict.direction.value, "—")
            direction = DIRECTION_TEXT.get(verdict.direction.value, verdict.direction.value)
            card["header"].setText(f"<b>{HORIZON_TEXT.get(horizon, horizon)}</b>")
            direction_label = card["direction"]
            direction_label.setText(f"{symbol} {direction}")
            palette = direction_label.palette()
            palette.setColor(QPalette.ColorRole.WindowText, color)
            direction_label.setPalette(palette)
            card["conf"].setText(
                CONFIDENCE_TEXT.get(verdict.confidence.value, verdict.confidence.value)
            )
            card["rationale"].setText(verdict.rationale)
            self._fill_evidence(card, verdict.evidence_item_ids)
            card["frame"].setVisible(True)

    def _fill_evidence(self, card: dict[str, object], ids) -> None:
        """Hàng dẫn chứng — mỗi id một nút bấm được (d.1646-1647)."""
        self._clear_layout(card["layout"])
        label = QLabel(AI_EVIDENCE_TEXT)
        label.setObjectName("CardDetail")
        card["layout"].addWidget(label)
        for row_id in ids:
            button = action_button(str(row_id))
            button.clicked.connect(
                lambda _checked=False, rid=int(row_id): self._pick_evidence(rid)
            )
            card["layout"].addWidget(button)
        card["layout"].addStretch(1)

    def _pick_evidence(self, row_id: int) -> None:
        """Dẫn chứng bấm → đóng dialog rồi screen nhảy dòng (d.1646-1647)."""
        self.accept()
        if self._on_evidence is not None:
            self._on_evidence(row_id)

    def _clear_result(self) -> None:
        for card in self._cards.values():
            card["frame"].setVisible(False)
            card["header"].clear()
            card["direction"].clear()
            card["conf"].clear()
            card["rationale"].clear()
            self._clear_layout(card["layout"])

    @staticmethod
    def _clear_layout(layout: QVBoxLayout | QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    # -- dọn worker ------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - tên Qt
        self._shutdown_ai()
        super().closeEvent(event)

    def _shutdown_ai(self) -> None:
        """Dừng lượt AI nền (khuôn shutdown của màn) — chờ có giới hạn."""
        thread = self._ai_thread
        self._ai_thread = None
        self._ai_worker = None
        if thread is None:
            return
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(2000)
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Dialog dán mã nguồn 2 pha + bảng xem trước
# (screen_design "Hành vi dán mã nguồn trang ForexFactory" d.1579-1617; QĐ-F6/F9)
# ---------------------------------------------------------------------------


class PastePreviewModel(QAbstractTableModel):
    """Bảng xem trước của dialog dán mã nguồn (pha 2 — d.1594-1596, QĐ-F6).

    CHỈ cột "Thực tế" (actual) sửa được (Owner đợt 4): mọi cột còn lại read-only,
    không checkbox/không xóa dòng (all-or-nothing).  Dòng đã sửa → trạng thái
    "Đã sửa" (d.1577).  Disposition của dòng chưa sửa do dialog đổ vào sau mỗi
    lần phân loại lại QUA CONTROLLER (``reclassify_pasted_rows`` — UI không tự
    phân loại, S2); mô hình này không giữ công thức/phân loại nghiệp vụ nào.
    """

    COLUMNS = _PREVIEW_COLUMNS
    ACTUAL_KEY = "actual"
    DISPOSITION_KEY = "disposition"

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[CalendarEvent] = []
        self.dispositions: list[str] = []
        self.edited: set[str] = set()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section][1]
        return str(section + 1)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        event = self.rows[index.row()]
        key = self.COLUMNS[index.column()][0]
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(event, key, index.row())
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if key in {"event_time_utc", "currency", "impact", "forecast", "previous", "actual", "disposition"}:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if role == Qt.ItemDataRole.ForegroundRole and key == self.DISPOSITION_KEY:
            return semantic_qcolor(PREVIEW_STATUS_ROLE.get(self._disposition_value(index.row()), "info"))
        if role == Qt.ItemDataRole.ToolTipRole:
            return event.title
        return None

    def flags(self, index: QModelIndex) -> int:
        base = super().flags(index) | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self.COLUMNS[index.column()][0] == self.ACTUAL_KEY:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or not self.flags(index) & Qt.ItemFlag.ItemIsEditable:
            return False
        row_index = index.row()
        event = self.rows[row_index]
        actual = str(value).strip() or None
        if actual == event.actual:
            return False  # gõ lại đúng giá trị bóc không phải một chỉnh sửa
        self.rows[row_index] = replace(event, actual=actual)
        self.edited.add(event.dedupe_key)
        top = self.index(row_index, 0)
        bottom = self.index(row_index, self.columnCount() - 1)
        self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ForegroundRole])
        return True

    def set_preview(self, preview) -> None:
        """Nạp một lô bóc tách (pha 1 → pha 2): events + disposition ban đầu."""
        self.beginResetModel()
        self.rows = list(preview.events)
        self.dispositions = [d.value for d in preview.dispositions]
        self.edited.clear()
        self.endResetModel()

    def set_dispositions(self, values) -> None:
        """Đổ kết quả phân loại lại (controller) — không thay đổi gì khi lệch số dòng."""
        if not values or len(values) != len(self.rows):
            return
        self.dispositions = [str(d) for d in values]
        column = next(
            i for i, (key, _label) in enumerate(self.COLUMNS) if key == self.DISPOSITION_KEY
        )
        self.dataChanged.emit(
            self.index(0, column),
            self.index(len(self.rows) - 1, column),
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ForegroundRole],
        )

    def edited_actuals_mapping(self) -> dict[str, str]:
        """Khóa = ``dedupe_key`` · giá trị = actual mới của dòng ĐÃ SỬA (chuỗi
        rỗng khi user xóa sạch — parser quy rỗng về NULL; tránh str(None)="None")."""
        return {
            event.dedupe_key: str(event.actual) if event.actual is not None else ""
            for event in self.rows
            if event.dedupe_key in self.edited
        }

    def row_at(self, index: int) -> CalendarEvent | None:
        if 0 <= index < len(self.rows):
            return self.rows[index]
        return None

    def _display(self, event: CalendarEvent, key: str, row_index: int) -> str:
        if key == "event_time_utc":
            return _display_time(event.event_time_utc)
        if key == "currency":
            return event.currency
        if key == "title":
            return event.title or NO_VALUE
        if key == "impact":
            return IMPACT_TEXT.get(event.impact.value, event.impact.value)
        if key == "forecast":
            return event.forecast or NO_VALUE
        if key == "previous":
            return event.previous or NO_VALUE
        if key == "actual":
            return event.actual or NO_VALUE
        if key == self.DISPOSITION_KEY:
            value = self._disposition_value(row_index)
            return PREVIEW_STATUS_TEXT.get(value, value)
        return NO_VALUE

    def _disposition_value(self, row_index: int) -> str:
        if self.rows[row_index].dedupe_key in self.edited:
            return "edited"
        if row_index < len(self.dispositions):
            return self.dispositions[row_index]
        return "new"


class PasteSourceDialog(QDialog):
    """Dialog dán mã nguồn 2 pha (screen_design d.1579-1617; QĐ-F6/F9).

    * **Pha 1 — dán + bóc tách:** ô text dán source / nút chọn file `.html`
      (đọc file TRONG WORKER — không block GUI) + hướng dẫn 3 bước + nút
      **"Bóc tách"** → ``controller.parse_pasted_source`` trong
      ``NewsReadWorker`` (khuôn D10 — không processEvents).  Parse lỗi → thông
      báo từ điển ``PARSE_ERROR_TEXT`` và GIỮ pha 1 để dán lại.  Không ghi gì
      ở pha này (contract §6.1 bước 2).
    * **Pha 2 — bảng xem trước:** chỉ cột "Thực tế" sửa được (QĐ-F6); sửa
      actual → badge "Đã sửa" + phân loại lại qua
      ``controller.reclassify_pasted_rows`` (UI không tự phân loại — S2).
      **"Cập nhật"** → ``controller.commit_pasted_source(preview, edited_actuals)``
      trong worker → tóm tắt mới/cập nhật/xung đột (sự kiện + lãi suất) rồi
      đóng dialog (màn chủ làm mới bảng tin + panel).  **"Hủy"** → reject,
      không ghi/không run, loại bỏ cả chỉnh sửa (§6.1 bước 6).
    """

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._preview = None
        self._task_thread: QThread | None = None
        self._task_worker: NewsReadWorker | None = None
        self._task_tag = ""
        self._busy = False
        self._reclassify_pending = False
        self._file_parse_pending = False
        self.preview_model = PastePreviewModel()
        self.preview_model.dataChanged.connect(self._on_preview_edited)
        self.setObjectName("NewsPasteDialog")
        self.setWindowTitle(PASTE_DIALOG_TITLE)
        self.resize(880, 600)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self._build()

    # -- dựng giao diện ------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        self._phase_1 = self._build_phase_1()
        self._phase_2 = self._build_phase_2()
        root.addWidget(self._phase_1, 1)
        root.addWidget(self._phase_2, 1)
        self._phase_2.setVisible(False)
        self._status_label = QLabel("")
        self._status_label.setObjectName("NewsPasteStatus")
        self._status_label.setWordWrap(True)
        self._status_label.setVisible(False)
        root.addWidget(self._status_label)

    def _build_phase_1(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        steps = QLabel("\n".join(f"• {step}" for step in PASTE_STEP_TEXTS))
        steps.setObjectName("CardDetail")
        steps.setWordWrap(True)
        layout.addWidget(steps)
        self.source_edit = QTextEdit()
        self.source_edit.setObjectName("NewsPasteSource")
        self.source_edit.setAcceptRichText(False)
        layout.addWidget(self.source_edit, 1)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.file_button = action_button(PASTE_FILE_TEXT)
        self.file_button.clicked.connect(self._on_file_clicked)
        self.parse_button = action_button(PASTE_PARSE_TEXT, primary=True, color="success")
        self.parse_button.clicked.connect(self._on_parse_clicked)
        controls.addWidget(self.file_button)
        controls.addStretch(1)
        controls.addWidget(self.parse_button)
        layout.addLayout(controls)
        return widget

    def _build_phase_2(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.preview_table = QTableView()
        self.preview_table.setObjectName("NewsPastePreviewTable")
        configure_table(self.preview_table)
        self.preview_table.setModel(self.preview_model)
        header = self.preview_table.horizontalHeader()
        header.setStretchLastSection(False)
        for index, (key, _label) in enumerate(self.preview_model.COLUMNS):
            if key == _PREVIEW_STRETCH_COLUMN:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)
                continue
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Fixed)
            self.preview_table.setColumnWidth(index, _PREVIEW_COLUMN_WIDTHS.get(key, 110))
        self.preview_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.preview_table.verticalHeader().setDefaultSectionSize(30)
        self.preview_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.preview_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.preview_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        layout.addWidget(self.preview_table, 1)
        self.rates_label = QLabel("")
        self.rates_label.setObjectName("CardDetail")
        layout.addWidget(self.rates_label)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("NewsPasteSummary")
        self.summary_label.setWordWrap(True)
        self.summary_label.setVisible(False)
        layout.addWidget(self.summary_label)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.cancel_button = action_button(CANCEL_TEXT, icon="x", icon_role="text", icon_disabled_role="text")
        self.cancel_button.clicked.connect(self.reject)
        self.commit_button = action_button(
            PASTE_COMMIT_TEXT, primary=True, color="success", icon="save",
            icon_role="selection_text", icon_disabled_role="selection_text",
        )
        self.commit_button.clicked.connect(self._on_commit_clicked)
        controls.addStretch(1)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.commit_button)
        layout.addLayout(controls)
        return widget

    # -- worker nền chung (khuôn AiTrendDialog/D10) ---------------------------

    def _run_task(self, task, tag: str) -> None:
        thread = QThread(self)
        worker = NewsReadWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_task_succeeded)
        worker.failed.connect(self._on_task_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._on_task_thread_finished(thread))
        self._task_tag = tag
        self._task_thread = thread
        self._task_worker = worker
        self._busy = True
        thread.start()

    def _on_task_thread_finished(self, thread: QThread) -> None:
        if self._task_thread is thread:
            self._task_thread = None
            self._task_worker = None
        self._busy = False
        self._pump_reclassify()
        self._pump_file_parse()

    def _on_task_succeeded(self, payload) -> None:
        tag = self._task_tag
        if tag == "parse":
            self._apply_preview(payload)
        elif tag == "file":
            self._file_loaded(payload)
        elif tag == "reclassify":
            self._apply_dispositions(payload)
        elif tag == "commit":
            self._on_commit_succeeded(payload)

    def _on_task_failed(self, message: str) -> None:
        tag = self._task_tag
        if tag in ("parse", "file"):
            self.parse_button.setEnabled(True)
            self.file_button.setEnabled(True)
            self._set_status(message)  # giữ pha 1 để dán lại
        elif tag == "commit":
            self.commit_button.setEnabled(True)
            self.cancel_button.setEnabled(True)
            self._set_status(message)
        elif tag == "reclassify":
            pass  # chỉ là đọc lại — giữ disposition cũ, không làm mất chỉnh sửa

    # -- pha 1: dán + bóc tách -------------------------------------------------

    def _on_parse_clicked(self) -> None:
        if self._busy:
            return
        source = self.source_edit.toPlainText()
        if not source.strip():
            self._set_status(PASTE_EMPTY_SOURCE_TEXT)
            return
        self._set_status(PASTE_PARSE_PROGRESS_TEXT)
        self.parse_button.setEnabled(False)
        self.file_button.setEnabled(False)
        self._run_task(lambda: self._controller.parse_pasted_source(source), "parse")

    def _on_file_clicked(self) -> None:
        if self._busy:
            return
        path, _selected = QFileDialog.getOpenFileName(
            self, PASTE_DIALOG_TITLE, "", "HTML files (*.html *.htm);;All files (*)"
        )
        if not path:
            return
        self._set_status(PASTE_FILE_LOAD_PROGRESS_TEXT)
        self.parse_button.setEnabled(False)
        self.file_button.setEnabled(False)
        self._run_task(lambda: _read_source_file(str(path)), "file")

    def _file_loaded(self, content) -> None:
        self.parse_button.setEnabled(True)
        self.file_button.setEnabled(True)
        self._set_status("")
        self.source_edit.setPlainText(str(content))
        self._file_parse_pending = True  # bóc ngay sau khi worker file dừng hẳn (không busy)

    def _apply_preview(self, payload) -> None:
        self.parse_button.setEnabled(True)
        self.file_button.setEnabled(True)
        error = getattr(payload, "error", None)
        if error is not None:
            self._set_status(PARSE_ERROR_TEXT.get(error.kind.value, error.kind.value))
            return  # dialog giữ pha 1 — dán lại
        self._preview = payload
        self.summary_label.setVisible(False)
        self.preview_model.set_preview(payload)
        self.rates_label.setText(PASTE_RATES_TEXT.format(count=len(payload.rates)))
        self._set_status("")
        self._phase_1.setVisible(False)
        self._phase_2.setVisible(True)

    # -- pha 2: sửa actual → phân loại lại; Cập nhật / Hủy --------------------

    def _on_preview_edited(self, *signal_args) -> None:
        """Chỉ khi ô cột "Thực tế" đổi (dataChanged do setData / set_dispositions
        đều đi qua đây) — tránh vòng lặp: set_dispositions phát lại dataChanged
        cho cột trạng thái không được kích phân loại lại."""
        if self._preview is None or len(signal_args) < 2:
            return
        top_left = signal_args[0]
        bottom_right = signal_args[1]
        for row in range(top_left.row(), bottom_right.row() + 1):
            for column in range(top_left.column(), bottom_right.column() + 1):
                if self.preview_model.COLUMNS[column][0] == self.preview_model.ACTUAL_KEY:
                    # Badge "Đã sửa" do model tự cập nhật (edited set); phân loại
                    # lại qua controller — UI không tự phân loại (S2).
                    self._reclassify_pending = True
                    self._pump_reclassify()
                    return

    def _pump_reclassify(self) -> None:
        if not self._reclassify_pending or self._busy or self._preview is None:
            return
        self._reclassify_pending = False
        preview = self._preview
        edited = dict(self.preview_model.edited_actuals_mapping())
        self._run_task(
            lambda: self._controller.reclassify_pasted_rows(preview, edited),
            "reclassify",
        )

    def _pump_file_parse(self) -> None:
        if not self._file_parse_pending or self._busy:
            return
        self._file_parse_pending = False
        self._on_parse_clicked()  # đưa nội dung file vào luồng bóc

    def _apply_dispositions(self, payload) -> None:
        values = [getattr(d, "value", None) or str(d) for d in payload]
        self.preview_model.set_dispositions(values)

    def _on_commit_clicked(self) -> None:
        if self._busy or self._preview is None:
            return
        edited = dict(self.preview_model.edited_actuals_mapping())
        self.commit_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self._set_status(PASTE_COMMIT_PROGRESS_TEXT)
        self._run_task(
            lambda: self._controller.commit_pasted_source(self._preview, edited),
            "commit",
        )

    def _on_commit_succeeded(self, result) -> None:
        self._set_status("")
        self.summary_label.setText(
            PASTE_SUMMARY_TEXT.format(
                inserted=getattr(result, "inserted", 0),
                updated=getattr(result, "updated", 0),
                conflicts=len(getattr(result, "conflicts", ())),
                rates=getattr(result, "rates_written", 0),
            )
        )
        self.summary_label.setVisible(True)
        self.accept()  # đóng dialog — màn chủ làm mới bảng tin + panel (d.1611-1612)

    def _set_status(self, message: str) -> None:
        self._status_label.setText(message)
        self._status_label.setVisible(bool(message))

    # -- dọn worker khi đóng (khuôn AiTrendDialog.closeEvent/_shutdown_ai) -----

    def closeEvent(self, event) -> None:  # noqa: N802 - tên Qt
        self._shutdown_tasks()
        super().closeEvent(event)

    def _shutdown_tasks(self) -> None:
        thread = self._task_thread
        self._task_thread = None
        self._task_worker = None
        self._busy = False
        if thread is None:
            return
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(2000)
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Màn
# ---------------------------------------------------------------------------


class NewsScreen(QWidget):
    """Màn Quản lý tin — bảng lọc + chi tiết dòng + hành vi tương tác (lô L3.2/L3.3)."""

    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.news_controller = getattr(app, "news_controller", None) if app is not None else None
        self.table_model = NewsTableModel()
        self._rows: list[NewsRow] = []
        self._thread: QThread | None = None
        self._worker: NewsReadWorker | None = None
        self._pending_events: list[CalendarEvent] = []
        self._pending_thread: QThread | None = None
        self._pending_worker: NewsReadWorker | None = None
        # (Đợt 3 — slot thread riêng của 2 nút FF và của xuất/nhập file đã được
        # gỡ cùng hai đường hành vi đó; màn chỉ còn worker đọc bảng + worker AI
        # nằm trong chính dialog.  F4 thêm worker đọc panel thiếu số liệu.)
        self.toolbar_buttons: dict[str, QPushButton] = {}
        self.empty_state_buttons: dict[str, QPushButton] = {}
        self.setObjectName("FormScreen")
        self._build_ui()
        self.reload_rows()
        self._reload_pending()

    # -- dựng giao diện ---------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)
        root.addWidget(page_header("Tin tức", "Quản lý tin"))

        filter_card = card()
        filter_card.layout().setContentsMargins(12, 6, 12, 6)
        filter_card.layout().addWidget(self._filter_bar())
        root.addWidget(filter_card)

        root.addWidget(self._table_card(), 1)
        root.addWidget(self._pending_panel())
        root.addWidget(self._toolbar())

    def _filter_bar(self) -> QWidget:
        self.kind_combo = self._enum_combo(
            "Loại tin",
            [(EVENT_ROW, EVENT_TEXT)]
            + [(member.value, KIND_TEXT[member.value]) for member in NewsItemKind],
        )
        self.currency_combo = self._enum_combo("Đồng tiền", [])
        self.impact_combo = self._enum_combo(
            "Tác động",
            [(member.value, IMPACT_TEXT[member.value]) for member in EventImpact],
        )
        self.source_combo = self._enum_combo(
            "Nguồn",
            [(member.value, SOURCE_TEXT[member.value]) for member in EventSource]
            + [(member.value, SOURCE_TEXT[member.value]) for member in NewsItemSource],
        )
        self.status_combo = self._enum_combo(
            "Trạng thái",
            [(member.value, STATUS_TEXT[member.value]) for member in EventStatus]
            + [("excluded", EXCLUDED_TEXT)],
        )
        for combo in (
            self.kind_combo,
            self.currency_combo,
            self.impact_combo,
            self.source_combo,
            self.status_combo,
        ):
            combo.currentIndexChanged.connect(lambda _index: self.refresh_rows())

        self.date_from_input = QDateEdit()
        self.date_from_input.setObjectName("NewsDateFrom")
        self.date_from_input.setCalendarPopup(True)
        self.date_from_input.setDisplayFormat("dd/MM/yyyy")
        self.date_from_input.setButtonSymbols(QDateEdit.ButtonSymbols.NoButtons)
        self.date_from_input.setMinimumWidth(118)
        self.date_from_input.setDate(QDate.currentDate().addMonths(-1))
        self.date_from_input.dateChanged.connect(lambda _date: self.refresh_rows())

        self.date_to_input = QDateEdit()
        self.date_to_input.setObjectName("NewsDateTo")
        self.date_to_input.setCalendarPopup(True)
        self.date_to_input.setDisplayFormat("dd/MM/yyyy")
        self.date_to_input.setButtonSymbols(QDateEdit.ButtonSymbols.NoButtons)
        self.date_to_input.setMinimumWidth(118)
        self.date_to_input.setDate(QDate.currentDate())
        self.date_to_input.dateChanged.connect(lambda _date: self.refresh_rows())

        date_field = QWidget()
        date_layout = QHBoxLayout(date_field)
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.setSpacing(6)
        date_layout.addWidget(self.date_from_input)
        date_layout.addWidget(self.date_to_input)

        # Lưới tự giảm cột khi thiếu bề ngang (khuôn ui/responsive_row.py): một
        # hàng đầy đủ ở desktop, xuống nhiều hàng ở 800px — sàn bề ngang của màn
        # là bề ngang MỘT hàng compact, không phải tổng cả hàng.
        return ResponsiveGrid(
            widgets=[
                form_row(FILTER_LABELS[0], self.kind_combo),
                form_row(FILTER_LABELS[1], self.currency_combo),
                form_row(FILTER_LABELS[2], self.impact_combo),
                form_row(FILTER_LABELS[3], self.source_combo),
                form_row(FILTER_LABELS[4], self.status_combo),
                form_row(FILTER_LABELS[5], date_field),
            ],
            columns=len(FILTER_LABELS),
            compact_columns=2,
            stretch=False,
        )

    def _enum_combo(self, label: str, options: list[tuple[str, str]]) -> QComboBox:
        """Combo lọc: mục đầu là "(tất cả …)" (khuôn repo), rồi đúng giá trị enum."""
        combo = QComboBox()
        combo.setObjectName(f"NewsFilter{_COMBO_NAMES[label]}")
        # Sàn bề ngang của control do lưới lo; combo không xin bề ngang theo
        # item dài nhất (danh sách nguồn có nhãn dài) — nếu không, sàn của màn
        # vượt 800px (điểm review của lô).
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(12)
        combo.setMinimumWidth(120)
        combo.addItem(f"{ALL_PREFIX} {label.lower()}", None)
        for value, text in options:
            combo.addItem(text, value)
        return combo

    def _table_card(self) -> QFrame:
        table_card = card()
        self.table = QTableView()
        self.table.setObjectName("NewsTable")
        configure_table(self.table)
        self.table.setModel(self.table_model)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for index, (key, _label) in enumerate(self.table_model.COLUMNS):
            if key == _STRETCH_COLUMN:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)
                continue
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(index, _COLUMN_WIDTHS.get(key, 100))
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.clicked.connect(self._on_cell_clicked)
        table_card.layout().addWidget(self.table, 1)

        # Vùng thông báo (loading / rỗng / lỗi) — QTextEdit như khuôn dashboard
        # vì ``set_rich_html``/``empty_state_html`` giao HTML đã biên dịch.
        self.status_message = QTextEdit()
        self.status_message.setObjectName("ReadonlyText")
        self.status_message.setReadOnly(True)
        # Không ghim chiều cao cứng (kỷ luật density: mọi setMinimum/FixedHeight
        # đều là nợ phải rà) — QTextEdit tự lấy chiều cao theo bố cục.
        self.status_message.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self.status_message.setVisible(False)
        table_card.layout().addWidget(self.status_message)

        self.empty_actions = QWidget()
        empty_layout = QHBoxLayout(self.empty_actions)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(8)
        empty_layout.addStretch(1)
        for label in EMPTY_STATE_LABELS:
            button = action_button(label)
            button.clicked.connect(self._empty_action_handler(label))
            empty_layout.addWidget(button)
            self.empty_state_buttons[label] = button
        empty_layout.addStretch(1)
        table_card.layout().addWidget(self.empty_actions)
        return table_card

    def _empty_action_handler(self, label: str):
        """Nút gợi ý empty state (d.1634-1635): "Dán mã nguồn trang" đi thẳng
        dialog dán (F4 — cùng handler nút toolbar); "Nhập tin" đi form nhập tay."""
        if label == TOOLBAR_LABELS[0]:
            return lambda: self.open_paste_dialog()
        if label == TOOLBAR_LABELS[1]:
            return lambda: self.open_note_dialog()
        return lambda: None

    def _pending_panel(self) -> QFrame:
        """Panel "Sự kiện đang thiếu số liệu" (d.1544-1545, d.1613-1617): chỉ
        hiển thị khi có sự kiện stale (ẩn khi rỗng — không phát minh nhãn rỗng)."""
        panel = card()
        panel.setObjectName("NewsPendingPanel")
        title = QLabel(PANEL_TITLE_TEXT)
        title.setObjectName("PanelTitle")
        panel.layout().addWidget(title)
        self._pending_list = QWidget()
        self._pending_layout = QVBoxLayout(self._pending_list)
        self._pending_layout.setContentsMargins(0, 0, 0, 0)
        self._pending_layout.setSpacing(4)
        panel.layout().addWidget(self._pending_list)
        self._pending_panel = panel
        return panel

    def _toolbar(self) -> QWidget:
        toolbar = ResponsiveGrid(
            widgets=[self._toolbar_button(label) for label in TOOLBAR_LABELS],
            columns=len(TOOLBAR_LABELS),
            compact_columns=len(TOOLBAR_LABELS),
            stretch=False,
        )
        toolbar.setObjectName("NewsToolbarRow")
        return toolbar

    def _toolbar_button(self, label: str) -> QPushButton:
        """Nút thanh công cụ — đúng 3 nút nối hành vi (F4: [Dán | Nhập | AI])."""
        button = action_button(label)
        if label == TOOLBAR_LABELS[0]:
            button.clicked.connect(self.open_paste_dialog)
        elif label == TOOLBAR_LABELS[1]:
            button.clicked.connect(lambda: self.open_note_dialog())
        else:
            button.clicked.connect(self.open_ai_dialog)
        self.toolbar_buttons[label] = button
        return button

    # -- đọc dữ liệu ------------------------------------------------------------

    def reload_rows(self) -> None:
        """Đọc lại bảng trong worker nền (mở màn / đổi bộ lọc — screen_design)."""
        if self.news_controller is None:
            self._rows = []
            self._apply_rows([])
            return
        self.shutdown()  # dừng lượt đọc còn dở (nếu có) trước khi mở lượt mới
        self._set_status(LOADING_TEXT)
        thread = QThread(self)
        worker = NewsReadWorker(self._read_window)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_rows_loaded)
        worker.failed.connect(self._on_rows_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._forget_thread(thread))
        self._thread = thread
        self._worker = worker
        thread.start()

    def _forget_thread(self, thread: QThread) -> None:
        """Quên lượt đọc đã kết thúc (QThread bị ``deleteLater`` xoá C++ object)."""
        if self._thread is thread:
            self._thread = None
            self._worker = None

    def shutdown(self) -> None:
        """Dừng worker đọc nền (màn đóng / mở lượt đọc mới) — chờ có giới hạn."""
        self._stop_pending_worker()
        thread = self._thread
        self._thread = None
        self._worker = None
        if thread is None:
            return
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(2000)
        except RuntimeError:
            # QThread đã bị xoá (deleteLater) — không còn gì để dừng.
            pass

    def closeEvent(self, event) -> None:  # noqa: N802 - tên Qt
        """Đóng màn thì dừng luôn worker đọc nền (không để thread sống ngoài màn).

        (Đợt 3 — trước đây còn dừng slot thread của 2 nút FF và của xuất/nhập
        file; hai slot đó đã gỡ cùng hai đường hành vi.  F4 thêm worker đọc
        panel thiếu số liệu.)"""
        self.shutdown()
        super().closeEvent(event)

    # -- panel "Sự kiện đang thiếu số liệu" (d.1544-1545, d.1613-1617) -----------

    def _reload_pending(self) -> None:
        """Đọc ``events_pending_actual`` qua worker nền (khuôn đọc bảng hiện có
        — contract §8: chỉ nuôi panel hướng dẫn, không phục vụ fetch tự động)."""
        if self.news_controller is None:
            self._show_pending([])
            return

        def read() -> list[CalendarEvent]:
            return list(self.news_controller.events_pending_actual(datetime.now(UTC)))

        self._stop_pending_worker()
        thread = QThread(self)
        worker = NewsReadWorker(read)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_pending_loaded)
        worker.failed.connect(lambda _message: self._show_pending([]))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._forget_pending_thread(thread))
        self._pending_thread = thread
        self._pending_worker = worker
        thread.start()

    def _forget_pending_thread(self, thread: QThread) -> None:
        if self._pending_thread is thread:
            self._pending_thread = None
            self._pending_worker = None

    def _stop_pending_worker(self) -> None:
        thread = self._pending_thread
        self._pending_thread = None
        self._pending_worker = None
        if thread is None:
            return
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(2000)
        except RuntimeError:
            pass

    def _on_pending_loaded(self, payload: object) -> None:
        self._show_pending(list(payload) if isinstance(payload, list) else [])

    def _show_pending(self, events: list[CalendarEvent]) -> None:
        """Dựng lại nội dung panel (mỗi dòng: sự kiện + nút mở trang FF tuần)."""
        self._clear_layout(self._pending_layout)
        self._pending_events = list(events)
        for event in events:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            label = QLabel(
                f"{_display_time(event.event_time_utc)} · {event.currency} · {event.title}"
            )
            label.setObjectName("CardDetail")
            label.setWordWrap(True)
            row_layout.addWidget(label, 1)
            button = action_button(OPEN_FF_TEXT)
            button.clicked.connect(lambda _checked=False, ev=event: self._open_ff_page(ev))
            row_layout.addWidget(button)
            self._pending_layout.addWidget(row)
        self._pending_panel.setVisible(bool(events))

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _open_ff_page(self, event: CalendarEvent) -> None:
        """Mở trang lịch tuần FF bằng trình duyệt ngoài (QĐ-F4/F10 — chỉ
        ``QDesktopServices.openUrl``; app không phát request mạng nào)."""
        QDesktopServices.openUrl(QUrl(ff_week_url_for_event(event.event_time_utc)))

    def _notify(self, title: str, text: str, *, suggestion: str | None = None, on_suggestion=None) -> None:
        """QMessageBox khuôn ``journal_screen`` (D8) — gợi ý là nút AcceptRole."""
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Warning if suggestion else QMessageBox.Icon.Information)
        suggested_button = None
        if suggestion:
            suggested_button = action_button(suggestion, icon="edit", icon_role="text", icon_disabled_role="text")
            box.addButton(suggested_button, QMessageBox.ButtonRole.AcceptRole)
            box.addButton(
                action_button(CLOSE_TEXT, icon="x", icon_role="text", icon_disabled_role="text"),
                QMessageBox.ButtonRole.RejectRole,
            )
        else:
            box.addButton(
                action_button(CLOSE_TEXT, icon="x", icon_role="text", icon_disabled_role="text"),
                QMessageBox.ButtonRole.AcceptRole,
            )
        box.exec()
        if suggested_button is not None and box.clickedButton() is suggested_button and on_suggestion is not None:
            on_suggestion()

    # -- form nhập/sửa tin (§6.4, screen_design "Hành vi nhập/sửa tin") -----------

    def open_note_dialog(self, *, prefill_event: CalendarEvent | None = None, editing_item: NewsItem | None = None) -> None:
        """Mở form nhập/sửa tin (chặn) — ghi xong thì đọc lại bảng."""
        if self.news_controller is None:
            return
        dialog = self.create_note_dialog(prefill_event=prefill_event, editing_item=editing_item)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload_rows()

    def create_note_dialog(self, *, prefill_event: CalendarEvent | None = None, editing_item: NewsItem | None = None) -> UserNoteDialog:
        """Dựng (không mở) form nhập/sửa tin — gợi ý đồng tiền lấy từ dữ liệu màn (D4)."""
        return UserNoteDialog(
            self.news_controller,
            self,
            prefill=prefill_event,
            editing_item=editing_item,
            currencies=self._currency_codes(),
        )

    # -- dialog dán mã nguồn 2 pha (F4 — §6.1 đợt 3+4) --------------------------

    def open_paste_dialog(self) -> None:
        """Mở dialog dán mã nguồn 2 pha (chặn) — sau "Cập nhật" làm mới bảng tin
        + panel (d.1611-1612); "Hủy" reject = không ghi, không run (§6.1 bước 6)."""
        if self.news_controller is None:
            return
        dialog = self.create_paste_dialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload_rows()
            self._reload_pending()

    def create_paste_dialog(self) -> PasteSourceDialog:
        """Dựng (không mở) dialog dán mã nguồn 2 pha."""
        return PasteSourceDialog(self.news_controller, self)

    def _currency_codes(self) -> list[str]:
        codes: list[str] = []
        for index in range(1, self.currency_combo.count()):
            code = self.currency_combo.itemData(index)
            if code:
                codes.append(str(code))
        return codes

    # -- cửa sổ AI nhận định xu hướng (L3.5 — §9.1/§9.2) -----------------------

    def open_ai_dialog(self) -> None:
        """Mở cửa sổ AI nhận định xu hướng — không modal toàn app (d.1624)."""
        if self.news_controller is None:
            return
        dialog = AiTrendDialog(self.news_controller, self._jump_to_evidence, self)
        dialog.exec()

    def _jump_to_evidence(self, row_id: int) -> None:
        """Nhảy tới dòng của một dẫn chứng (d.1646-1647) — V2: ưu tiên khớp
        item rồi event trong tập dòng đã đọc; chỉ nhảy khi dòng đang hiển thị
        (không tự đổi bộ lọc)."""
        target: NewsRow | None = None
        for row in self._rows:
            if row.item is not None and row.item.id == row_id:
                target = row
                break
        if target is None:
            for row in self._rows:
                if row.event is not None and row.event.id == row_id:
                    target = row
                    break
        if target is None:
            return
        if not any(row is target for row in self.table_model.rows):
            return
        index = self.table_model.rows.index(target)
        self.table.selectRow(index)
        self.table.scrollTo(
            self.table_model.index(index, 0), QAbstractItemView.ScrollHint.EnsureVisible
        )

    # -- sửa/xóa/toggle theo dòng (D7 — trong dialog chi tiết dòng) ---------------

    def _row_actions(self, dialog: QDialog, row: NewsRow) -> QWidget | None:
        """Hàng điều khiển dòng: toggle Loại trừ (mọi tin văn bản) + Sửa/Xóa (source=user)."""
        if row.row_type != ITEM_ROW or row.item is None:
            return None
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        toggle = action_button(EXCLUDE_TEXT, icon="eye", icon_role="text", icon_disabled_role="text")
        toggle.setCheckable(True)
        toggle.setChecked(row.excluded)
        toggle.toggled.connect(lambda checked: self._toggle_excluded(row.item.id, checked))
        layout.addWidget(toggle)
        if row.source == NewsItemSource.USER.value:
            edit = action_button(EDIT_TEXT, icon="edit", icon_role="text", icon_disabled_role="text")
            edit.clicked.connect(lambda: self._edit_item(row.item, dialog))
            layout.addWidget(edit)
            remove = action_button(
                DELETE_TEXT, primary=True, color="danger", icon="trash", icon_role="selection_text", icon_disabled_role="selection_text"
            )
            remove.clicked.connect(lambda: self._delete_item(row.item, dialog))
            layout.addWidget(remove)
        layout.addStretch(1)
        return container

    def _toggle_excluded(self, item_id: int | None, checked: bool) -> None:
        if self.news_controller is None:
            return
        try:
            self.news_controller.set_excluded(item_id, bool(checked))
        except Exception as exc:
            self._notify(EXCLUDE_TEXT, str(exc))
            return
        self.reload_rows()

    def _edit_item(self, item: NewsItem, dialog: QDialog) -> None:
        if self.news_controller is None:
            return
        note = self.create_note_dialog(editing_item=item)
        if note.exec() == QDialog.DialogCode.Accepted:
            dialog.accept()
            self.reload_rows()

    def _delete_item(self, item: NewsItem, dialog: QDialog) -> None:
        if self.news_controller is None:
            return
        if not self._confirm_delete(item):
            return
        try:
            self.news_controller.delete_user_note(item.id)
        except Exception as exc:
            self._notify(DELETE_TEXT, str(exc))
            return
        dialog.accept()
        self.reload_rows()

    def _confirm_delete(self, item: NewsItem) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(DELETE_TEXT)
        box.setText(item.title)
        box.setIcon(QMessageBox.Icon.Warning)
        confirm = action_button(DELETE_TEXT, icon="trash", icon_role="text", icon_disabled_role="text")
        box.addButton(confirm, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(
            action_button(CANCEL_TEXT, icon="x", icon_role="text", icon_disabled_role="text"),
            QMessageBox.ButtonRole.RejectRole,
        )
        box.exec()
        return box.clickedButton() is confirm

    def _read_window(self) -> list[NewsRow]:
        """Đọc cửa sổ đang lọc qua controller — chạy TRONG worker (không GUI thread)."""
        from_utc, to_utc = self._window_bounds()
        controller = self.news_controller
        events = controller.events_in_range(from_utc, to_utc)
        items = controller.items_in_range(from_utc, to_utc, exclude_flagged=False)
        return build_rows(list(events), list(items))

    def _window_bounds(self) -> tuple[str, str]:
        """Khoảng ngày của bộ lọc → mốc ISO UTC (đầu ngày đầu, cuối ngày cuối)."""
        start = self.date_from_input.date().toPyDate()
        end = self.date_to_input.date().toPyDate()
        from_utc = datetime.combine(start, clock_time.min, tzinfo=UTC)
        to_utc = datetime.combine(end, clock_time.max, tzinfo=UTC)
        return _iso(from_utc), _iso(to_utc)

    def refresh_rows(self) -> None:
        """Áp lại bộ lọc hiển thị trên tập dòng đã đọc (không đọc lại DB)."""
        self._apply_rows(self._rows)

    def _selected(self, combo: QComboBox) -> str | None:
        value = combo.currentData()
        return str(value) if value is not None else None

    def _apply_rows(self, rows: list[NewsRow]) -> None:
        visible = filter_rows(
            rows,
            kind=self._selected(self.kind_combo),
            currency=self._selected(self.currency_combo),
            impact=self._selected(self.impact_combo),
            source=self._selected(self.source_combo),
            status=self._selected(self.status_combo),
        )
        self._sync_currency_options(rows)
        self.table_model.set_rows(visible)
        if not visible:
            self._show_empty_state()
        else:
            self.status_message.setVisible(False)
            self.empty_actions.setVisible(False)

    def _sync_currency_options(self, rows: list[NewsRow]) -> None:
        """Danh mục đồng tiền của bộ lọc lấy từ chính dữ liệu đã đọc (không bịa danh sách)."""
        codes = sorted({code for row in rows for code in row.currencies if code})
        current = self._selected(self.currency_combo)
        existing = [self.currency_combo.itemData(index) for index in range(self.currency_combo.count())]
        if existing[1:] == codes:
            return
        self.currency_combo.blockSignals(True)
        self.currency_combo.clear()
        self.currency_combo.addItem(f"{ALL_PREFIX} {FILTER_LABELS[1].lower()}", None)
        for code in codes:
            self.currency_combo.addItem(code, code)
        if current in codes:
            self.currency_combo.setCurrentIndex(codes.index(current) + 1)
        self.currency_combo.blockSignals(False)

    def _show_empty_state(self) -> None:
        set_rich_html(
            self.status_message,
            empty_state_html(EMPTY_TEXT, tone=EMPTY_TONE, icon="search", icon_role="muted"),
        )
        self.status_message.setVisible(True)
        self.empty_actions.setVisible(True)

    def _set_status(self, message: str) -> None:
        set_rich_html(self.status_message, empty_state_html(message, tone=EMPTY_TONE))
        self.status_message.setVisible(True)
        self.empty_actions.setVisible(False)

    def _on_rows_loaded(self, payload: object) -> None:
        self._rows = list(payload) if isinstance(payload, list) else []
        self._apply_rows(self._rows)

    def _on_rows_failed(self, message: str) -> None:
        set_rich_html(self.status_message, empty_state_html(message, tone="danger", icon="alert-triangle", icon_role="danger"))
        self.status_message.setVisible(True)
        self.empty_actions.setVisible(False)

    # -- chi tiết dòng ----------------------------------------------------------

    def _on_cell_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        if self.table_model.COLUMNS[index.column()][0] != "detail":
            return
        row = self.table_model.row_at(index.row())
        if row is not None:
            self.show_row_detail(row)

    def show_row_detail(self, row: NewsRow) -> None:
        """Mở dialog chi tiết dòng (chặn — chỉ dùng từ tương tác người dùng)."""
        self.row_detail_dialog(row).exec()

    def row_detail_dialog(self, row: NewsRow) -> QDialog:
        """Dựng dialog chi tiết: nội dung + provenance (nguồn, giờ fetch, raw_json, liên kết)."""
        dialog = QDialog(self)
        dialog.setWindowTitle(DETAIL_TEXT)
        dialog.setObjectName("NewsDetailDialog")
        dialog.resize(640, 420)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        title = QLabel(row.title)
        title.setObjectName("ActionTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(32)
        grid.setVerticalSpacing(8)
        for index, (label, value, is_link) in enumerate(self._provenance_pairs(row)):
            label_widget = QLabel(compile_rich_html(label))
            label_widget.setObjectName("CardDetail")
            label_widget.setFixedWidth(120)
            value_widget = QLabel(compile_rich_html(value))
            value_widget.setObjectName("CardValue")
            value_widget.setWordWrap(True)
            value_widget.setTextFormat(Qt.TextFormat.RichText)
            if is_link:
                value_widget.setOpenExternalLinks(True)
            grid.addWidget(label_widget, index, 0)
            grid.addWidget(value_widget, index, 1)
        root.addLayout(grid)

        body = QLabel(row.item.content if row.item is not None and row.item.content else row.title)
        body.setObjectName("CardValue")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(body, 1)

        # Điều khiển sửa/xóa/toggle theo dòng (D7 — trong dialog chi tiết dòng).
        actions = self._row_actions(dialog, row)
        if actions is not None:
            root.addWidget(actions)
        return dialog

    def _provenance_pairs(self, row: NewsRow) -> list[tuple[str, str, bool]]:
        """Cặp nhãn/giá trị provenance của một dòng — chỉ đọc, không suy diễn."""
        pairs: list[tuple[str, str, bool]] = [
            (PROVENANCE_LABELS[0], _display_time(row.timestamp_utc), False),
            (PROVENANCE_LABELS[1], SOURCE_TEXT.get(row.source, row.source or NO_VALUE), False),
        ]
        origin = row.item if row.item is not None else row.event
        pairs.append(
            (
                PROVENANCE_LABELS[2],
                _display_time(origin.fetched_at if origin is not None else ""),
                False,
            )
        )
        raw_json = row.event.raw_json if row.event is not None else None
        if raw_json:
            pairs.append(("raw_json", raw_json, False))
        url = row.item.url if row.item is not None else None
        if url:
            pairs.append((PROVENANCE_LABELS[3], f"<a href='{url}'>{url}</a>", True))
        return pairs


def _iso(moment: datetime) -> str:
    """Mốc ISO-8601 UTC — cùng khuôn mọi mốc thời gian đã lưu của miền."""
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
