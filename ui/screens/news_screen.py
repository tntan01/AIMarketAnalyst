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
* mục "Tất cả" của mỗi combo — rút gọn từ khuôn "(tất cả …)" của repo
  (``journal_screen.py``: "Tất cả mã", "Tất tất trạng thái"...); Owner quyết
  26/09/2026: nhãn gọn cạnh ô đã nói ô đó lọc gì nên mục đầu chỉ còn "Tất cả"
  (không lặp "Tất tất loại tin/đồng tiền/…").
* ``LOADING_TEXT = "Đang tải..."`` — chuỗi có sẵn của repo
  (``dashboard_screen.py``) cho chỉ báo loading mà screen_design yêu cầu.

**Đợt 3 (24/09/2026 — ca "Nguồn dán FF", plan F1):** thanh công cụ chỉ còn
**[ Nhập tin | AI nhận định xu hướng ]** — hai nút "Lấy lịch kinh tế"/"Cập nhật
actual" (lô L3.3 cũ) và hai nút "Xuất file"/"Nhập file" (lô L3.4 cũ) cùng toàn
bộ slot thread/dialog riêng của chúng đã bị **GỠ** (contract §13/§10 đợt 3 — bỏ
thu tự động FF, bỏ xuất/nhập file; app không phát request mạng nào tới
ForexFactory).  Gợi ý "Nhập actual bằng tay" cũng bỏ (dán source là kênh actual
duy nhất — contract §13 đợt 3).  Nhãn hiển thị nguồn đổi 3 chuỗi theo Từ điển
đợt 3 (``ff_html`` = "Forex Factory", ``ff_json`` = "ForexFactory
(lịch — dữ liệu cũ)", ``import`` = "Nhập file (dữ liệu cũ)" — nhãn cũ phục vụ
dữ liệu cũ, GIỮ).

**Lô F4 — dialog dán mã nguồn 2 pha** (screen_design
"Hành vi dán mã nguồn trang ForexFactory" d.1579-1617 + "Bố cục" d.1544-1547 +
từ điển d.1577; contract §6.1 đợt 3+4; QĐ-F6/F9): toolbar
**[ Dán mã nguồn trang | Nhập tin | AI nhận định xu hướng ]** — nút đầu mở
``PasteSourceDialog`` (2 pha).  Pha 1: dán source hoặc
chọn file `.html` (đọc file TRONG WORKER — không block GUI) → "Bóc tách" →
``controller.parse_pasted_source`` trong ``NewsReadWorker`` (khuôn D10 — không
processEvents); lỗi parse → thông báo theo ``PARSE_ERROR_TEXT`` (L3 — ánh xạ mã
lỗi có kiểu của parser, không đặt chuỗi này trong services), giữ pha 1.  Pha 2:
bảng xem trước đúng cột d.1594-1596 + đếm quan sát lãi suất; **chỉ cột "Thực
tế" sửa được** (QĐ-F6/đợt 4), cột còn lại read-only, không checkbox/xóa dòng;
sửa actual → badge "Đã sửa" + phân loại lại qua ``controller.reclassify_pasted_rows``
(QĐ-F9 — UI không tự phân loại, S2); "Cập nhật" → ``commit_pasted_source(preview,
edited_actuals)`` trong worker → tóm tắt mới/cập nhật/xung đột → đóng dialog (màn
làm mới bảng tin); "Hủy" → reject, không ghi/không run (§6.1 bước 6).

Khai báo đọc-hiểu lô F4 (V2):

* Worker của mọi thao tác nền trong dialog dán (parse / đọc file / phân loại
  lại / commit) là ``NewsReadWorker`` dùng chung — một task một thread, khuôn
  D10; phân loại lại sau sửa actual có cờ đợi (``_reclassify_pending``) để
  không chồng lời gọi khi người dùng sửa liên tiếp.
* "Đã sửa" là trạng thái hiển thị ƯU TIÊN của dòng đã sửa actual (d.1602 "trạng
  thái chuyển 'Đã sửa'"); kết quả ``reclassify_pasted_rows`` vẫn được tính (và
  giữ) để phân loại các dòng chưa sửa.
* Dialog đóng (accept) ngay sau "Cập nhật" thành công — màn chủ lo phần làm mới
  bảng tin (d.1611-1612); "Hủy" reject không chạm controller.

**Lô L3.5 — cửa sổ AI nhận định xu hướng** (screen_design d.1621-1649; contract
§9.1-§9.2): nút "AI nhận định xu hướng" mở ``AiTrendDialog`` (800×600 cố định, không
modal toàn app — WindowModal, d.1624); phạm vi = cặp tiền ``SUPPORTED_SYMBOLS``
(tiêu thụ) hoặc 1 đồng tiền rút từ chính danh sách cặp; dòng đếm qua
``controller.ai_scope_preview`` (không gọi AI); dưới ``ai_min_items`` hiện
d.1642 và nút "Nhận định" không gọi AI (B4); lời gọi AI chạy trong worker nền
(khuôn worker D10 của màn — không gọi ``analyze()`` đồng bộ trong callback,
không processEvents); lỗi provider/parser → thông báo thân thiện; 3 thẻ chân
trời nhãn đúng từ điển d.1570-1572, ký hiệu ▲/▼/— màu semantic; **thân hai tab
"Chi tiết" và "Cặp forex" nằm trong vùng cuộn** (dialog cố định 800×600, nút hành
động ở ngoài vùng cuộn — Owner báo 30/09/2026); **tab "Chi tiết" KHÔNG hiện hàng
dẫn chứng** ở MỌI tab (Owner chốt 30/09/2026 — dẫn chứng vẫn được lưu trong
``ai_trend_verdicts``, chỉ không hiển thị; đường "bấm dẫn chứng để nhảy dòng"
đã gỡ cùng); lịch sử
``verdicts_for`` mới nhất trước; cảnh báo advisory d.1638 THƯỜNG TRỰC.

Khai báo đọc-hiểu (V2):

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
* **Sửa/xóa theo dòng** nằm trong dialog chi tiết dòng (D7 — không thêm
  nút toolbar, không thêm cột bảng đã đóng băng): chỉ tin ``source=user`` có
  "Sửa" + "Xóa"; dòng sự kiện và tin tự động không có nút sửa nào.  Toggle
  "Loại trừ" đã **GỠ** (Owner chốt 30/09/2026 — cờ ``excluded`` vẫn là dữ liệu
  của miền, không còn đường sửa từ giao diện).  Sau mỗi lượt ghi, bảng đọc lại
  qua `reload_rows()`.

Khai báo đọc-hiểu lô L3.3 (V2 — bên dưới, xem từng điểm):

* **D2 — giờ đăng theo múi giờ người dùng:** widget giờ của form thu theo khóa
  ``settings.display.timezone`` (Settings chọn `Asia/Ho_Chi_Minh` / `Asia/Bangkok`
  / `UTC` — Owner quyết 25/09/2026); giá trị lưu ``published_utc`` vẫn UTC —
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
* Card tìm kiếm KHÔNG tự áp khi chọn ô — chỉ tìm khi bấm nút "Tìm kiếm"
  (Owner duyệt 26/09/2026): nút gọi ``reload_rows`` (đọc lại DB theo cửa sổ
  ngày mới rồi áp 5 bộ lọc — đổi ngày phải đọc lại DB nên không dùng lọc
  in-memory cho nút này).
* **Vòng 6 (Owner duyệt 26/09/2026):** nút "Tìm kiếm" trở thành ô cuối lưới
  (phần tử bình thường của dải lọc — nút bám trái ô, không neo mép phải cửa
  sổ; icon ``search``) thay ``_action_cell`` → lưới đủ 7 ô: Loại tin, Đồng
  tiền, Tác động, Nguồn, Trạng thái, Khoảng ngày, nút tìm; bộ lọc lệch lần
  áp cuối → nút nhấn qua property QSS ``filterDirty`` (snapshot chốt mỗi
  ``reload_rows``, so sánh 7 control — trạng thái không tính riêng ô nào).
* Màn đọc tin văn bản với ``exclude_flagged=False`` — nếu không, hàng
  ``excluded=1`` không bao giờ hiện ra để mang badge "Đã loại trừ"/để lọc
  theo trạng thái đó (screen_design yêu cầu cột Trạng thái hiển thị cờ này).
* Khi ``app`` không cấp ``news_controller`` (app giả của bộ test shell —
  ``tools/capture_ui_style_baseline._fake_app`` — không có thuộc tính này và
  file đó ngoài sổ điểm chạm), màn **không đọc gì** và để bảng rỗng: không
  tự dựng controller thật để tránh mở ``news.db`` trong test của màn khác.
* Kết quả lọc rỗng → bảng không có dòng nào, **không** hiện thông báo rỗng/không
  thêm nút gợi ý (các nút hành vi đã có sẵn ở thanh công cụ) — Owner quyết
  27/09/2026.
* Bố cục dùng ``ResponsiveGrid`` (khuôn ``ui/responsive_row.py``) cho dãy bộ lọc
  và thanh công cụ. Dải lọc bật chế độ **fluid** (opt-in 26/09/2026): số cột
  lấy lớn nhất vừa bề ngang thực tế trong [1..đầy] — không rơi thẳng về compact
  ở bề ngang trung bình (defect 1920×1200@150% = 1280px logic); mỗi ô
  ``_filter_cell`` (nhãn Fixed + ô Maximum + ``addStretch`` cuối ô — thay
  ``form_row`` nhãn 150px + ô giãn làm card phình): nhãn/ô không giãn theo
  cột, phần dư dồn về SAU ô (không rải vào khe nhãn–ô). Sàn bề ngang của màn
  là bề ngang Ô RỘNG NHẤT (compact 1 cột = bố cục chảy: hết chỗ thì xuống
  dòng từng ô, không nén méo/tràn) — màn vừa shell 800px.
  Mỗi ô nhập tự định cỡ theo NỘI DUNG THẬT nó phải chứa (Owner 26/09/2026 —
  không dùng chung một sàn cho mọi ô): combo lọc dùng
  ``AdjustToContents`` nên rộng đủ hiển thị TRỌN mục dài nhất trong danh sách
  (vd "ForexFactory (lịch — dữ liệu cũ)" — bề rộng mỗi combo là của riêng nó,
  theo font đang dùng); ô ngày đo ``sizeHint()`` của ``QDateEdit`` (Qt tính từ
  format "dd/MM/yyyy" + frame/nút bật lịch), không hard-code số px. Khi màn
  hẹp, lưới fluid xuống dòng liên tục (4 → 2 → 1 cột) giữ mọi ô nguyên nội
  dung — không bóp chữ, không tràn. Thanh công cụ 2 nút (đợt 3) càng không
  vượt sàn.
* Bảng đặt bề ngang cột tường minh (khuôn ``scanner_screen._configure_table_columns``):
  cột "Nội dung" giãn, các cột còn lại cố định đủ đọc trọn nhãn cột;
  cửa sổ hẹp thì bảng cuộn ngang (``ScrollBarAsNeeded``) thay vì bóp cột tới mức
  chữ bị cắt.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time as clock_time, timedelta, tzinfo
from zoneinfo import ZoneInfo

from PyQt6.QtCore import (
    QAbstractTableModel,
    QDate,
    QDateTime,
    QModelIndex,
    QSize,
    QTime,
    QUrl,
    QTimer,
    Qt,
    QThread,
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
    QScrollArea,
    QTabWidget,
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
from core.pair_bias import derive_pair_bias
from ui.icons import flat_icon
from ui.layout_system import LayoutTokens, configure_table
from ui.responsive_row import ResponsiveGrid
from ui.rich_text import compile_rich_html, empty_state_html, set_rich_html
from ui.screens.shared import action_button, card, form_row, page_header
from ui.theme.fonts import get_body_font, get_subtitle_font
from ui.theme_manager import semantic_qcolor, set_dynamic_property
from workers.news_worker import NewsAiBatchWorker, NewsReadWorker

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
    "ff_html": "Forex Factory",
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

# Glyph icon mức tác động của cột "Loại" — lấy NGUYÊN khuôn dashboard
# (``NewsTypeIcon``: "●" cho sự kiện, "▤" cho tin văn bản; màu theo ``impact``
# qua semantic palette — dashboard_screen._render_news_rows + ui/styles/base.qss).
EVENT_ICON = "●"
ITEM_ICON = "▤"

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
    "Nguồn",
    "Đồng tiền",
    "Loại",
    "Nội dung",
    "Kỳ trước",
    "Dự báo",
    "Thực tế",
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
    "Tải lại",
)
# Icon của các nút thanh công cụ — khuôn nút hành động hệ thống (primary + color
# + icon_role "selection_text"), glyph phẳng từ ``ui/icons.py`` (style-guide §2).
TOOLBAR_ICONS: dict[str, str] = {
    TOOLBAR_LABELS[0]: "clipboard",  # dán mã nguồn trang
    TOOLBAR_LABELS[1]: "edit",  # nhập tin
    TOOLBAR_LABELS[2]: "bot",  # AI nhận định xu hướng
    TOOLBAR_LABELS[3]: "refresh",  # tải lại (cập nhật trạng thái mới nhất)
}
# Nút áp bộ lọc của card tìm kiếm (screen_design "Bố cục" d.1543-1545 — Owner
# duyệt 26/09/2026: KHÔNG tự tìm khi chọn ô, chỉ tìm khi bấm nút; nút đọc lại
# DB theo cửa sổ ngày mới).
SEARCH_BUTTON_TEXT = "Tìm kiếm"
# Nút chọn nhanh tuần (Owner yêu cầu 30/09/2026) — đặt cạnh nút "Tìm kiếm" trong
# card tìm kiếm, dùng đúng khuôn nút hành động chung của hệ thống
# (``action_button`` → objectName ``SecondaryButton``): một chạm đặt khoảng ngày
# về tuần tương ứng rồi đọc lại dữ liệu.
WEEK_BUTTON_LABELS: tuple[str, ...] = ("Tuần trước", "Tuần này", "Tuần sau")
DATE_RANGE_ARROW_TEXT = "→"  # nối 2 ô ngày trong cụm "Khoảng ngày"
LOADING_TEXT = "Đang tải..."
DETAIL_TEXT = "Chi tiết"
ALL_PREFIX = "Tất cả"
NO_VALUE = "—"

# Nhãn dùng trong dialog chi tiết (đều đã có nguồn: nhãn cột hoặc câu chữ screen_design).
PROVENANCE_LABELS: tuple[str, ...] = ("Thời gian", "Nguồn", "Liên kết")
# Cặp nhãn/giá trị của dialog xem 1 TIN SỰ KIỆN FF (Owner yêu cầu 30/09/2026:
# bỏ "Giờ fetch"/"raw_json" — vô nghĩa với người dùng — thay bằng chính số liệu
# của sự kiện).  Nhãn lấy từ COLUMN_LABELS đã đăng ký, không phát minh chuỗi.
EVENT_DATA_LABELS: tuple[str, ...] = ("Thời gian", "Nguồn", "Kỳ trước", "Dự báo", "Thực tế")

# ---------------------------------------------------------------------------
# Từ điển lô L3.3 — form nhập/sửa tin (screen_design "Hành vi nhập/sửa tin"
# d.1593-1601).  Mọi chuỗi ở đây đều có nguồn đã đăng ký; không phát minh nhãn.
# ---------------------------------------------------------------------------

# Nhãn dialog/nút (nguồn: nhãn nút thanh công cụ đã đăng ký + khối "Bố cục" +
# chuỗi có sẵn của repo).
NOTE_DIALOG_TITLE = TOOLBAR_LABELS[1]  # "Nhập tin" (nhãn nút đã đăng ký)
EDIT_DIALOG_TITLE = "Sửa tin"  # screen_design d.1598 "Sửa/xóa"
EDIT_TEXT = "Sửa"  # screen_design d.1598 "Sửa/xóa"
DELETE_TEXT = "Xóa"  # screen_design d.1598 "Sửa/xóa"
SAVE_TEXT = "Lưu"  # chuỗi có sẵn repo (settings_screen d.198)
CANCEL_TEXT = "Hủy"  # chuỗi có sẵn repo (scanner_screen d.2351)
CLOSE_TEXT = "Đóng"  # chuỗi có sẵn repo (journal_screen d.1885)
# Khung giải thích chỉ số bằng AI trong dialog xem 1 tin sự kiện FF (Owner yêu
# cầu 30/09/2026): nhãn nút + trạng thái đang chạy + câu gợi ý trong khung.
EXPLAIN_HEADER_TEXT = "Giải thích chỉ số"  # chuỗi có sẵn repo (dashboard d.439)
EXPLAIN_TEXT = "Giải thích"  # chuỗi có sẵn repo (journal_screen d.1235)
AI_EXPLAINING_TEXT = "AI đang giải thích"  # nguyên văn yêu cầu Owner 30/09/2026
EXPLAIN_HINT_TEXT = "Bấm nút để AI giải thích chỉ số này."
# Nút mở liên kết của tin tự động (URL rất dài — Owner yêu cầu 30/09/2026).
LINK_OPEN_TEXT = "Xem"
# Khối + nút "Phân tích" bài viết bằng AI trong dialog xem 1 tin văn bản
# (Owner yêu cầu 30/09/2026) — song song với "Giải thích chỉ số" của sự kiện.
ANALYZE_HEADER_TEXT = "Phân tích bài viết"
ANALYZE_TEXT = "Phân tích"
AI_ANALYZING_TEXT = "AI đang phân tích"
ANALYZE_HINT_TEXT = "Bấm nút để AI phân tích bài viết này."

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

# --- đợt 5 (B4): dialog 3 tab — Tổng quan / Chi tiết / Cặp forex (screen_design
# "thiết kế lại 3 tab" d.1704-1791).  Mọi nhãn mới có nguồn: tên tab theo mockup,
# nhãn bias theo contract §9.3 khoản 2, còn lại là chuỗi có sẵn của repo.
AI_TAB_OVERVIEW_TEXT = "Tổng quan"  # mockup d.1716
AI_TAB_DETAIL_TEXT = "Chi tiết"  # mockup d.1716
AI_TAB_PAIR_TEXT = "Cặp forex"  # mockup d.1716
AI_BATCH_TEXT = "Nhận định tất cả"  # mockup d.1720
AI_BATCH_PROGRESS_TEXT = "Đang nhận định {done}/{total} · {scope}"  # d.1720 "n/11"
AI_BATCH_SUMMARY_TEXT = "Xong: {ok} đủ · {insufficient} thiếu dữ liệu · {error} lỗi"  # d.1755-1756
# Dòng thứ hai của tổng kết batch: LÝ DO của các phạm vi lỗi (Owner yêu cầu
# 30/09/2026 — "9 lỗi" mà không nói vì sao thì phải điều tra lại).  Lý do lấy
# nguyên văn thông báo thân thiện do controller/provider trả về.
AI_BATCH_REASON_TEXT = "Lý do lỗi: {detail}"
AI_BATCH_NO_REASON_TEXT = "không rõ lý do"
AI_PAIR_LABEL = "Cặp"  # mockup d.1737
PAIR_BIAS_TEXT: dict[str, str] = {  # contract §9.3 khoản 2 (nhãn bias)
    "bullish": "Nghiêng tăng",
    "bearish": "Nghiêng giảm",
    "neutral": "Trung lập",
    "unclear": "Không rõ",
}
AI_PAIR_BIAS_PREFIX = "→ Bias cặp:"  # mockup d.1739
AI_PAIR_NOTE_TEXT = (
    "suy ra từ nhận định từng đồng — không phải verdict riêng của AI"
)  # mockup d.1739-1740
AI_PAIR_DEEP_TEXT = "Nhận định chuyên sâu cặp này"  # mockup d.1741
AI_NO_VERDICT_TEXT = "Chưa có"  # mockup d.1723/1748
AI_CONTEXT_PREFIX = "Ngữ cảnh:"  # mockup d.1730
# --- đợt 6 (C4): panel độ phủ theo chân trời + dòng ngữ cảnh mở rộng
# (screen_design "bổ sung đợt 6" — sketch d.1708-1712; thẩm quyền hiển thị).
# Mọi số đến từ ``ai_scope_preview`` (passthrough policy) — UI không tự tính,
# không hard-code 7/42/180/50 (L1/S2).
AI_COVERAGE_LABEL = "Độ phủ theo chân trời"  # d.1708 (nhãn đăng ký)
AI_COVERAGE_MAX_LABEL = "tối đa"  # d.1709 (nhãn đăng ký)
AI_COVERAGE_HORIZON_TEXT: dict[str, str] = {  # d.1708 — Ngắn/Trung/Dài
    "short": "Ngắn",
    "mid": "Trung",
    "long": "Dài",
}
AI_COVERAGE_TEXT = (
    "{label}: {short} {short_days} ngày: {short_rows} dòng"
    " · {mid} {mid_days} ngày: {mid_rows} dòng"
    " · {long} {long_days} ngày: {long_rows} dòng"
    " ({max_label} {long_max_rows})"
)  # d.1708-1709 (nguyên khuôn wrap của sketch)
AI_YIELD_MARK_3M = "3m"  # d.1711 (mốc delta)
AI_YIELD_MARK_6M = "6m"  # d.1711
AI_RATE_PATH_LABEL = "Rate path 6 tháng"  # d.1712 (nhãn đăng ký)
AI_RATE_PATH_TEXT = "{label}: {change} (từ {then} → {now})"  # d.1712
AI_YIELD_2Y_TEXT = "US 2Y {value}% ({delta}; {mark3} {d3}; {mark6} {d6})"  # d.1710
AI_YIELD_10Y_TEXT = "US 10Y {value}% ({delta}; {mark3} {d3}; {mark6} {d6})"  # d.1710
AI_YIELD_SPREAD_TEXT = "Spread 2Y10Y {spread}"  # d.1710 (giữ đợt 5)
AI_YIELD_REAL_TEXT = "Real yield {real}%"  # d.1710 (giữ đợt 5)
AI_OVERVIEW_COLUMNS: tuple[str, ...] = (
    "Tài sản",
    "Ngắn hạn",
    "Trung hạn",
    "Dài hạn",
    "Verdict lúc",
)  # mockup d.1722
AI_OVERVIEW_LIMIT = 10  # đọc-hiểu trình bày (B5 — không phải giá trị vận hành)

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
# Từ điển lô F4 — dialog dán mã nguồn 2 pha
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
    ("event_time_utc", "Thời gian"),
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


def _read_source_file(path: str) -> str:
    """Đọc file `.html` đã lưu — chạy TRONG worker (không block GUI; d.1588)."""
    with open(path, mode="r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _filter_label(text: str) -> QLabel:
    """Nhãn/glyph ô lọc gọn — co theo chữ (Owner duyệt 26/09/2026).

    Chính sách ngang ``Fixed``: nhãn KHÔNG giãn khi cột lưới rộng hơn — nhãn
    giãn đẩy ô nhập xa mất (defect 1920×1200@150%)."""
    label = QLabel(text)
    label.setObjectName("FormLabel")
    label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    return label


def _filter_label_width() -> int:
    """Bề rộng CỘT NHÃN đồng nhất cho mọi ô lọc (Owner yêu cầu 26/09/2026:
    "sắp thẳng cột" — nhãn và ô nhập phải thẳng hàng giữa 2 dòng).

    Lấy bề rộng nhãn lớn nhất (đo qua ``ensurePolished`` để font QSS
    ``font-weight: 600`` của FormLabel được tính) + biên an toàn kerning.
    Tập đo gồm 6 nhãn ``FILTER_LABELS``.
    Cột nhãn đồng nhất ⇒ mọi ô nhập bắt đầu tại cùng một tọa độ ⇒ thẳng cột
    ở mọi chế độ xếp (kể cả khi lưới co xuống dòng)."""
    widths = []
    for text in FILTER_LABELS:
        label = _filter_label(text)
        label.ensurePolished()
        widths.append(label.sizeHint().width())
    return max(widths) + 4


def _filter_cell(label: str, *fields: QWidget, label_width: int) -> QWidget:
    """Một ô lọc gọn: cột nhãn đồng nhất + các ô nhập co theo nội dung.

    Thay ``form_row`` (nhãn cố định 150px + ô giãn) cho card tìm kiếm —
    6 ô × (150 + sàn ô) là nguyên nhân card phình to (sửa 26/09/2026).
    Nhãn ``label_width`` đồng nhất mọi ô, chữ **căn trái** (Owner quyết
    26/09/2026 — vòng 7) — cột nhãn đồng nhất giữ ô nhập dòng 1/dòng 2 cùng
    cột lưới bắt đầu tại cùng tọa độ (thẳng cột — Owner yêu cầu 26/09/2026).
    ``addStretch(1)`` cuối ô: phần bề ngang dư của cột dồn hết về SAU — không
    rải vào giữa nhãn và ô (defect 1920×1200@150%: Qt chia dư đều, khe nhãn–ô
    phình 76px)."""
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    label_widget = _filter_label(label)
    label_widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    label_widget.setFixedWidth(label_width)
    layout.addWidget(label_widget)
    for field in fields:
        layout.addWidget(field)
    layout.addStretch(1)
    return widget


def _button_cell(field: QWidget) -> QWidget:
    """Ô nút "Tìm kiếm" — MỘT PHẦN TỬ BÌNH THƯỜNG của dải lọc, ô cuối lưới
    ngay sau ô "Khoảng ngày" (Owner duyệt 26/09/2026): nút nằm SÁT ô lọc trước nó
    (khe = đúng gap lưới), KHÔNG bám mép phải cửa sổ — ``addStretch`` đặt SAU
    nút dồn phần bề ngang dư của cột về bên PHẢI nút → nút bám trái ô, khoảng
    trống thừa nằm ở rìa phải ngoài cùng; cửa sổ rộng bao nhiêu nút không
    trôi dạt theo (thay ``_action_cell`` có spacer cột nhãn — cũ căn phải)."""
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    layout.addWidget(field)
    layout.addStretch(1)
    return widget


EVENT_ROW = "event"
ITEM_ROW = "item"
SECTION_ROW = "section"  # dòng ngăn cách nhóm (khuôn zone header của dashboard)
# Nguyên văn 2 nhãn vùng của dashboard (dashboard_screen._render_zone_header):
# "SẮP TỚI GẦN NHẤT" = đúng dòng sắp tới gần nhất; "SẮP TỚI" = các dòng sắp tới
# còn lại.
NEAREST_SECTION_TEXT = "─── SẮP TỚI GẦN NHẤT ───"
FUTURE_SECTION_TEXT = "─── SẮP TỚI ───"
SECTION_ROLE = "success"  # vai trò màu của vùng "sắp tới gần nhất" (dashboard)
FUTURE_ROLE = "warning"  # vai trò màu của vùng "sắp tới" (dashboard)

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
    previous: str | None
    forecast: str | None
    actual: str | None
    status: str | None
    excluded: bool
    event: CalendarEvent | None = None
    item: NewsItem | None = None
    section_text: str | None = None
    section_role: str | None = None

    @classmethod
    def section(cls, text: str, role: str = SECTION_ROLE) -> "NewsRow":
        """Dòng ngăn cách nhóm (khuôn zone header dashboard) — không phải tin.

        ``role`` là vai trò màu semantic của vùng (dashboard: "sắp tới gần nhất"
        = ``success``, "sắp tới" = ``warning``)."""
        return cls(
            row_type=SECTION_ROW,
            timestamp_utc="",
            source="",
            currencies=(),
            title=text,
            impact=None,
            previous=None,
            forecast=None,
            actual=None,
            status=None,
            excluded=False,
            section_text=text,
            section_role=role,
        )

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
        previous=event.previous,
        forecast=event.forecast,
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
        previous=None,
        forecast=None,
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
    "kind": 48,
    "source": 150,
    "currencies": 80,
    "previous": 90,
    "forecast": 90,
    "actual": 85,
    "detail": 44,
}
_STRETCH_COLUMN = "title"

_COLUMNS: tuple[tuple[str, str], ...] = (
    ("timestamp_utc", COLUMN_LABELS[0]),
    ("source", COLUMN_LABELS[1]),
    ("currencies", COLUMN_LABELS[2]),
    ("kind", COLUMN_LABELS[3]),
    ("title", COLUMN_LABELS[4]),
    ("previous", COLUMN_LABELS[5]),
    ("forecast", COLUMN_LABELS[6]),
    ("actual", COLUMN_LABELS[7]),
    ("detail", COLUMN_LABELS[8]),
)


class NewsTableModel(QAbstractTableModel):
    """Bảng tin hợp nhất: DisplayRole + ForegroundRole (semantic) + ToolTipRole."""

    COLUMNS = _COLUMNS

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[NewsRow] = []
        # Dòng "sắp tới gần nhất" (đánh dấu xanh in đậm — khuôn dashboard);
        # giữ THAM CHIẾU tới dòng gốc để nhận diện đúng dòng khi cuộn/tô.
        self.nearest: NewsRow | None = None

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
            if row.section_text is not None:
                return Qt.AlignmentFlag.AlignCenter
            if key in {"timestamp_utc", "kind", "source", "currencies", "previous", "forecast", "actual", "detail"}:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if role == Qt.ItemDataRole.FontRole:
            return self._font(row)
        if role == Qt.ItemDataRole.DecorationRole:
            return self._decoration(row, key)
        if role == Qt.ItemDataRole.ForegroundRole:
            return self._foreground(row, key)
        if role == Qt.ItemDataRole.BackgroundRole:
            return self._background(row, key)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(row, key)
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if orientation == Qt.Orientation.Horizontal:
            key, label = self.COLUMNS[section]
            if key == "detail":
                # Tiêu đề cột "Chi tiết" thay chữ bằng icon mắt.
                if role == Qt.ItemDataRole.DecorationRole:
                    return flat_icon("eye", DETAIL_ROLE)
                return "" if role == Qt.ItemDataRole.DisplayRole else None
            return label if role == Qt.ItemDataRole.DisplayRole else None
        return str(section + 1) if role == Qt.ItemDataRole.DisplayRole else None

    def set_rows(self, rows: list[NewsRow], *, nearest: NewsRow | None = None) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.nearest = nearest
        self.endResetModel()

    def row_at(self, index: int) -> NewsRow | None:
        if 0 <= index < len(self.rows):
            return self.rows[index]
        return None

    # -- cell rendering ---------------------------------------------------------

    def _display(self, row: NewsRow, key: str) -> str:
        if row.section_text is not None:
            return row.section_text if key == self.COLUMNS[0][0] else ""
        if key == "timestamp_utc":
            return _display_time(row.timestamp_utc)
        if key == "kind":
            return EVENT_ICON if row.row_type == EVENT_ROW else ITEM_ICON
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
        if key == "previous":
            return row.previous or NO_VALUE
        if key == "forecast":
            return row.forecast or NO_VALUE
        if key == "actual":
            return row.actual or NO_VALUE
        if key == "detail":
            # Cột "Chi tiết" thay chữ bằng ICON (DecorationRole) — xem ``_decoration``.
            return ""
        return NO_VALUE

    def _decoration(self, row: NewsRow, key: str):
        """Icon của cột "Chi tiết": glyph mắt phẳng (``ui/icons.py``), tint theo
        semantic role ``DETAIL_ROLE`` — tự đổi màu khi đổi theme."""
        if key != "detail" or row.section_text is not None:
            return None
        return flat_icon("eye", DETAIL_ROLE)

    def _foreground(self, row: NewsRow, key: str) -> QColor | None:
        if row.section_text is not None:
            return semantic_qcolor(row.section_role or SECTION_ROLE)
        if row is self.nearest:
            return semantic_qcolor("success")
        role = self._row_impact_role(row)
        if role is not None:
            return semantic_qcolor(role)
        if key == "detail":
            return semantic_qcolor(DETAIL_ROLE)
        return None

    def _background(self, row: NewsRow, key: str) -> QColor | None:
        """Nền dòng: màu vùng cho dòng ngăn cách, xanh cho dòng sắp tới gần nhất
        (khuôn dashboard), còn lại tô theo mức tác động (danger/warning, alpha 25);
        mức thấp/không rõ để nguyên nền mặc định."""
        if row.section_text is not None:
            return semantic_qcolor(row.section_role or SECTION_ROLE, alpha=24)
        if row is self.nearest:
            return semantic_qcolor("success", alpha=28)
        role = self._row_impact_role(row)
        if role is not None:
            return semantic_qcolor(role, alpha=25)
        return None

    def _font(self, row: NewsRow):
        """Chữ đậm cho dòng ngăn cách (khuôn subtitle) và dòng sắp tới gần nhất
        (in đậm — dashboard); dòng thường trả ``None`` (font mặc định)."""
        if row.section_text is not None:
            return get_subtitle_font()
        if row is self.nearest:
            font = get_body_font()
            font.setBold(True)
            return font
        return None

    @staticmethod
    def _row_impact_role(row: NewsRow) -> str | None:
        """Vai trò màu semantic theo mức tác động của dòng (dashboard: đỏ =
        ``high``, cam = ``medium``; thấp/không rõ → không đổi màu)."""
        if row.impact == "high":
            return "danger"
        if row.impact == "medium":
            return "warning"
        return None

    def _tooltip(self, row: NewsRow, key: str) -> str | None:
        if key == "title":
            return row.title
        if key == "detail":
            return DETAIL_TEXT
        return None


_DISPLAY_TZ: tzinfo | None = None
_DEFAULT_TZ_NAME = "Asia/Ho_Chi_Minh"


def _configure_display_timezone(name: str | None) -> tzinfo:
    """Chốt múi giờ hiển thị của màn khi dựng (gọi từ ``NewsScreen._build_ui``).

    Tên múi giờ đến từ SEAM ``news_controller.display_timezone()`` (controller
    đọc ``settings.display.timezone`` — news_screen cấm import ``services``,
    L1/E2; khuôn ``_fred_api_key`` d.473-484).  Khóa thiếu/hỏng → fallback
    ``Asia/Ho_Chi_Minh`` (B4).  Cache module để ``_display_time`` chạy mỗi ô
    bảng không đọc settings."""
    global _DISPLAY_TZ
    try:
        _DISPLAY_TZ = ZoneInfo(name or _DEFAULT_TZ_NAME)
    except Exception:
        _DISPLAY_TZ = ZoneInfo(_DEFAULT_TZ_NAME)
    return _DISPLAY_TZ


def _display_timezone() -> tzinfo:
    """Múi giờ hiển thị đang chốt của tầng trình bày (khóa
    ``settings.display.timezone`` — Owner quyết 25/09/2026).  Chưa cấu hình
    (chưa dựng màn) → fallback ``Asia/Ho_Chi_Minh`` — caller hợp lệ luôn gọi
    sau ``_configure_display_timezone`` qua ``NewsScreen._build_ui``."""
    return _DISPLAY_TZ if _DISPLAY_TZ is not None else ZoneInfo(_DEFAULT_TZ_NAME)


def _display_time(value: str) -> str:
    """Hiển thị mốc thời gian của dòng theo múi giờ người dùng (khóa
    `settings.display.timezone` — Owner quyết 25/09/2026; giữ nguyên dạng ISO
    đã lưu nếu không đọc được)."""
    if not value:
        return NO_VALUE
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(_display_timezone()).strftime("%d/%m/%Y %H:%M")


def _now_utc() -> datetime:
    """Mốc "hiện tại" để xác định tin sắp tới gần nhất (seam cho test)."""
    return datetime.now(UTC)


def _row_moment(value: str) -> datetime | None:
    """Đọc mốc ISO-8601 của dòng thành ``datetime`` UTC; hỏng/thiếu → ``None``."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _ai_number(value: object) -> str:
    """Định dạng một số ngữ cảnh AI 2 chữ số thập phân; thiếu → "—" (không bịa)."""
    if value is None:
        return NO_VALUE
    return f"{float(value):.2f}"


def _ai_signed(value: object) -> str:
    """Định dạng một delta/spread có dấu (vd +0.19, -0.08); thiếu → "—"."""
    if value is None:
        return NO_VALUE
    return f"{float(value):+.2f}"


def batch_error_detail(payload: object) -> str:
    """Lý do lỗi của các phạm vi trong lượt batch "Nhận định tất cả" (thuần).

    Gom các phạm vi lỗi **theo lý do** (mỗi lý do một nhóm, kèm danh sách phạm
    vi) để dòng tổng kết nói được VÌ SAO chứ không chỉ đếm — nhiều phạm vi lỗi
    cùng một nguyên nhân (vd model suy luận bị cắt vì ngân sách token) thì hiện
    đúng một lần.  Phạm vi ``ok``/``insufficient`` không phải lỗi nên không vào
    đây.  Lý do lấy nguyên văn ``error_message`` do controller/provider trả về;
    thiếu chuỗi → nhãn "không rõ lý do" (không bịa).  Không có phạm vi lỗi →
    chuỗi rỗng (dòng tổng kết giữ nguyên một dòng).
    """
    grouped: dict[str, list[str]] = {}
    for entry in getattr(payload, "results", ()) or ():
        result = getattr(entry, "result", None)
        if result is None or getattr(result, "ok", False):
            continue
        if getattr(result, "insufficient", False):
            continue
        reason = str(getattr(result, "error_message", "") or "").strip()
        grouped.setdefault(reason or AI_BATCH_NO_REASON_TEXT, []).append(
            str(getattr(entry, "scope", ""))
        )
    return " · ".join(
        f"{reason} ({', '.join(scopes)})" for reason, scopes in grouped.items()
    )


def _iso_to_qdatetime(value: str) -> QDateTime | None:
    """Đọc một mốc ISO-8601 (UTC) thành ``QDateTime`` mang wall-time theo múi
    giờ người dùng (khóa `settings.display.timezone` — Owner quyết 25/09/2026)."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(_display_timezone()).replace(tzinfo=None)
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
    "Nhập tay" (D3); giờ đăng thu theo MÚI GIỜ NGƯỜI DÙNG đã chọn (D2 — Owner
    quyết 25/09/2026), giá trị lưu ``published_utc`` vẫn UTC (contract §4.3).
    Thiếu trường bắt buộc → hiện lỗi từng trường và KHÔNG gọi controller
    (không ghi DB); lỗi validate controller trả về hiện lên đúng trường, form
    KHÔNG đóng.  Draft hợp lệ đi qua ``NewsController.add_user_note`` (nhập)
    hoặc ``update_user_note`` (sửa — D1, không tự dựng model, không tính
    ``dedupe_key``).
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

        # Giờ đăng (theo MÚI GIỜ NGƯỜI DÙNG — D2, Owner quyết 25/09/2026): giá
        # trị đặc biệt (bằng minimum) hiển thị rỗng = "chưa nhập", nên trường
        # bắt buộc này thực sự có thể thiếu.
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
        """Giờ đăng đang nhập, quy về UTC cho controller — ``None`` khi trống.

        Widget giờ mang wall-time theo múi giờ người dùng (khóa
        ``settings.display.timezone`` — Owner quyết 25/09/2026); đọc thành mốc
        UTC trước khi gửi (lưu trữ bất biến — contract §4.3 ``published_utc``).
        ``toPyDateTime`` của QDateTime spec-UTC không mang tzinfo, nên wall-time
        được gán tz là múi giờ người dùng (cùng khóa ``_iso_to_qdatetime``)."""
        if self._time_missing():
            return None
        moment = self.time_edit.dateTime().toPyDateTime()
        return moment.replace(tzinfo=_display_timezone()).astimezone(UTC)

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


class AiOverviewModel(QAbstractTableModel):
    """Lưới tab "Tổng quan": 11 tài sản × (Ngắn/Trung/Dài + "Verdict lúc").

    Chỉ đọc dữ liệu controller đã đưa vào (UI không gọi AI, không tự tính —
    L1/S2).  Mỗi dòng: ``{"scope": str, "verdicts": {horizon: TrendVerdict},
    "at": str | None}``; tài sản chưa từng nhận định → cột giờ "Chưa có", các ô
    chân trời "—"."""

    HORIZONS: tuple[str, ...] = ("short", "mid", "long")

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, object]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(AI_OVERVIEW_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return AI_OVERVIEW_COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        column = index.column()
        last = len(AI_OVERVIEW_COLUMNS) - 1
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return str(row["scope"])
            if column == last:
                created_at = row.get("at")
                return _display_time(str(created_at)) if created_at else AI_NO_VERDICT_TEXT
            verdict = self._verdict(row, column)
            if verdict is None:
                return NO_VALUE
            symbol = DIRECTION_SYMBOL.get(verdict.direction.value, NO_VALUE)
            confidence = CONFIDENCE_TEXT.get(
                verdict.confidence.value, verdict.confidence.value
            )
            return f"{symbol} {confidence}"
        if role == Qt.ItemDataRole.ForegroundRole and 0 < column < last:
            verdict = self._verdict(row, column)
            if verdict is not None:
                return semantic_qcolor(
                    DIRECTION_ROLE.get(verdict.direction.value, "text_muted")
                )
            return None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column > 0:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(row["scope"])
        return None

    def flags(self, index: QModelIndex) -> int:
        return super().flags(index) | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_rows(self, rows: list[dict[str, object]]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def scope_at(self, row_index: int) -> str | None:
        if 0 <= row_index < len(self.rows):
            return str(self.rows[row_index]["scope"])
        return None

    @staticmethod
    def _verdict(row: dict[str, object], column: int) -> TrendVerdict | None:
        verdicts = row.get("verdicts")
        if not isinstance(verdicts, dict):
            return None
        return verdicts.get(AiOverviewModel.HORIZONS[column - 1])


class AiTrendDialog(QDialog):
    """Cửa sổ AI nhận định xu hướng — 800×600 cố định, không modal toàn app (d.1704).

    Thiết kế lại **3 tab** (đợt 5 — B4; screen_design d.1704-1791):

    * **Tổng quan**: lưới 11 tài sản đọc verdict mới nhất mỗi chân trời qua
      ``verdicts_for`` (CHỈ ĐỌC — không gọi AI); nút "Nhận định tất cả" chạy
      tuần tự 11 phạm vi trong worker nền (``NewsAiBatchWorker``), progress
      "n/11", một phạm vi lỗi không dừng lô (D2).
    * **Chi tiết**: giữ khuôn 3 thẻ chân trời + lịch sử; combo 11 tài sản theo
      ``controller.AI_ASSET_SCOPES`` (không tự sinh danh sách); dòng ngữ cảnh
      lãi suất/lợi suất từ ``ai_scope_preview.context`` (UI chỉ định dạng).
    * **Cặp forex**: 2 verdict thành phần cạnh nhau + 1 dòng bias mỗi chân trời
      từ ``core.pair_bias.derive_pair_bias`` (UI không tự tính; bias không lưu
      DB); nút "Nhận định chuyên sâu cặp này" gọi ``analyze_trend("pair", …)``.

    Dòng đếm/ngữ cảnh dưới ``ai_min_items`` → fail-closed, không gọi AI (B4).
    Lời gọi AI chạy trong worker nền (``NewsReadWorker`` — khuôn D10), không
    block GUI, không processEvents.  Dẫn chứng bấm được → đóng dialog rồi nhảy
    dòng bảng (d.1646-1647).  Cảnh báo advisory (d.1638) THƯỜNG TRỰC mọi tab.
    """

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._preview = None
        self._overview_model = AiOverviewModel()
        self._cards: dict[str, dict[str, object]] = {}
        self._pair_cards: dict[str, dict[str, object]] = {}
        self._pair_rows: dict[str, dict[str, QLabel]] = {}
        self._ai_thread: QThread | None = None
        self._ai_worker: NewsReadWorker | None = None
        self._pair_thread: QThread | None = None
        self._pair_worker: NewsReadWorker | None = None
        self._batch_thread: QThread | None = None
        self._batch_worker = None
        self.setObjectName("NewsAiDialog")
        self.setWindowTitle(AI_TEXT)
        self.setFixedSize(800, 600)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self._build()
        self._reload_overview()
        self._on_detail_scope_changed()
        self._reload_pair_bias()

    # -- dựng form ----------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(8)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("NewsAiTabs")
        self._overview_tab = self._build_overview_tab()
        self._detail_tab = self._build_detail_tab()
        self._pair_tab = self._build_pair_tab()
        self._tabs.addTab(self._overview_tab, AI_TAB_OVERVIEW_TEXT)
        self._tabs.addTab(self._detail_tab, AI_TAB_DETAIL_TEXT)
        self._tabs.addTab(self._pair_tab, AI_TAB_PAIR_TEXT)
        root.addWidget(self._tabs, 1)
        advisory = QLabel(AI_ADVISORY_TEXT)
        advisory.setObjectName("NewsAiAdvisory")
        advisory.setWordWrap(True)
        root.addWidget(advisory)

    def _build_overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(8)
        self._batch_button = action_button(AI_BATCH_TEXT, primary=True, color="success")
        self._batch_button.clicked.connect(self._on_batch_clicked)
        top.addWidget(self._batch_button)
        self._batch_status = QLabel("")
        self._batch_status.setObjectName("NewsAiBatchStatus")
        self._batch_status.setWordWrap(True)
        top.addWidget(self._batch_status, 1)
        layout.addLayout(top)
        self._overview_table = QTableView()
        self._overview_table.setObjectName("NewsAiOverview")
        configure_table(self._overview_table)
        self._overview_table.setModel(self._overview_model)
        self._overview_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._overview_table.verticalHeader().setVisible(False)
        self._overview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._overview_table.clicked.connect(self._on_overview_clicked)
        layout.addWidget(self._overview_table, 1)
        return widget

    @staticmethod
    def _scroll_body(content: QWidget) -> QScrollArea:
        """Bọc thân cuộn được của một tab (khuôn QScrollArea của Dashboard/
        Journal): dialog cố định 800×600 nên phần thân dài (3 thẻ chân trời +
        lịch sử) phải **tự cuộn** thay vì bị cắt — trước đây không có thanh cuộn
        nên nội dung dưới bị mất (defect Owner báo 30/09/2026).  Dòng chọn phạm
        vi và nút hành động nằm NGOÀI vùng cuộn để luôn trong tầm nhìn."""
        scroll = QScrollArea()
        scroll.setObjectName("NewsAiScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    def _build_detail_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        scope_row = QHBoxLayout()
        scope_row.setSpacing(8)
        scope_label = QLabel(AI_SCOPE_LABEL)
        scope_label.setObjectName("CardDetail")
        scope_row.addWidget(scope_label)
        self._detail_combo = QComboBox()
        self._detail_combo.setObjectName("NewsAiScope")
        self._detail_combo.setMinimumWidth(220)
        self._fill_detail_combo()
        self._detail_combo.currentIndexChanged.connect(
            lambda _i: self._on_detail_scope_changed()
        )
        scope_row.addWidget(self._detail_combo, 1)
        layout.addLayout(scope_row)
        self._count_label = QLabel("")
        self._count_label.setObjectName("NewsAiCount")
        self._count_label.setWordWrap(True)
        self._coverage_label = QLabel("")
        self._coverage_label.setObjectName("NewsAiCoverage")
        self._coverage_label.setWordWrap(True)
        self._context_label = QLabel("")
        self._context_label.setObjectName("NewsAiContext")
        self._context_label.setWordWrap(True)
        self._status_label = QLabel("")
        self._status_label.setObjectName("NewsAiStatus")
        self._status_label.setWordWrap(True)
        # Thân cuộn: đếm/cửa sổ, dòng ngữ cảnh, trạng thái, 3 thẻ kết quả, lịch sử.
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)
        body_layout.addWidget(self._count_label)
        body_layout.addWidget(self._coverage_label)
        body_layout.addWidget(self._context_label)
        body_layout.addWidget(self._status_label)
        header = QLabel(AI_RESULT_HEADER_TEXT)
        header.setObjectName("CardDetail")
        body_layout.addWidget(header)
        for horizon in ("short", "mid", "long"):
            card = self._make_card(horizon)
            body_layout.addWidget(card["frame"])
            self._cards[horizon] = card
        history_header = QLabel(AI_HISTORY_TEXT)
        history_header.setObjectName("CardDetail")
        body_layout.addWidget(history_header)
        history_widget = QWidget()
        self._history_layout = QVBoxLayout(history_widget)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(2)
        body_layout.addWidget(history_widget)
        body_layout.addStretch(1)
        layout.addWidget(self._scroll_body(body), 1)
        self._analyze_button = action_button(AI_ANALYZE_TEXT, primary=True, color="success")
        self._analyze_button.clicked.connect(self._on_analyze_clicked)
        layout.addWidget(self._analyze_button)
        return widget

    def _build_pair_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        pair_row = QHBoxLayout()
        pair_row.setSpacing(8)
        pair_label = QLabel(AI_PAIR_LABEL)
        pair_label.setObjectName("CardDetail")
        pair_row.addWidget(pair_label)
        self._pair_combo = QComboBox()
        self._pair_combo.setObjectName("NewsAiPair")
        self._pair_combo.setMinimumWidth(220)
        self._fill_pair_combo()
        self._pair_combo.currentIndexChanged.connect(lambda _i: self._reload_pair_bias())
        pair_row.addWidget(self._pair_combo, 1)
        layout.addLayout(pair_row)
        self._pair_status = QLabel("")
        self._pair_status.setObjectName("NewsAiPairStatus")
        self._pair_status.setWordWrap(True)
        # Thân cuộn (cùng lý do tab "Chi tiết"): hai verdict thành phần + bias +
        # ghi chú + 3 thẻ chuyên sâu + lịch sử dài hơn khung 800×600.
        body = QWidget()
        layout_body = QVBoxLayout(body)
        layout_body.setContentsMargins(0, 0, 0, 0)
        layout_body.setSpacing(8)
        layout_body.addWidget(self._pair_status)
        for horizon in ("short", "mid", "long"):
            label = QLabel(HORIZON_TEXT.get(horizon, horizon))
            label.setObjectName("CardDetail")
            layout_body.addWidget(label)
            row = QHBoxLayout()
            base = QLabel("")
            quote = QLabel("")
            bias = QLabel("")
            base.setObjectName("NewsAiPairBase")
            quote.setObjectName("NewsAiPairQuote")
            bias.setObjectName("NewsAiPairBias")
            row.addWidget(base)
            row.addWidget(quote)
            row.addWidget(bias, 1)
            layout_body.addLayout(row)
            self._pair_rows[horizon] = {"base": base, "quote": quote, "bias": bias}
        note = QLabel(AI_PAIR_NOTE_TEXT)
        note.setObjectName("CardDetail")
        note.setWordWrap(True)
        layout_body.addWidget(note)
        header = QLabel(AI_RESULT_HEADER_TEXT)
        header.setObjectName("CardDetail")
        layout_body.addWidget(header)
        for horizon in ("short", "mid", "long"):
            card = self._make_card(horizon, prefix="Pair")
            layout_body.addWidget(card["frame"])
            self._pair_cards[horizon] = card
        layout_body.addStretch(1)
        layout.addWidget(self._scroll_body(body), 1)
        self._pair_deep_button = action_button(
            AI_PAIR_DEEP_TEXT, primary=True, color="success"
        )
        self._pair_deep_button.clicked.connect(self._on_pair_deep_clicked)
        layout.addWidget(self._pair_deep_button)
        return widget

    def _make_card(self, horizon: str, prefix: str = "") -> dict[str, object]:
        """Một thẻ chân trời: header (hướng + ký hiệu màu semantic), confidence,
        lập luận.  Không có hàng dẫn chứng (Owner chốt 30/09/2026 — dẫn chứng vẫn
        được lưu trong verdict, chỉ không hiển thị ở dialog).

        Màu semantic của hướng tô qua QPalette (không dùng `style=` HTML hay
        setStyleSheet — giữ bộ đếm nợ UI style của file mới bằng 0, khuôn
        docs/ui/style/ui-style-baseline.json)."""
        frame = QFrame()
        frame.setObjectName(f"NewsAi{prefix}Card{horizon.capitalize()}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header = QLabel("")
        header.setObjectName(f"NewsAi{prefix}{horizon.capitalize()}Header")
        header.setWordWrap(False)
        header_row.addWidget(header)
        direction = QLabel("")
        direction.setObjectName(f"NewsAi{prefix}{horizon.capitalize()}Direction")
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
        frame.setVisible(False)
        return {
            "frame": frame,
            "header": header,
            "direction": direction,
            "conf": conf,
            "rationale": rationale,
        }

    def _fill_detail_combo(self) -> None:
        """Combo phạm vi = 11 tài sản theo ``controller.AI_ASSET_SCOPES``
        (tiêu thụ — UI không tự sinh danh sách, B5)."""
        for scope in self._controller.AI_ASSET_SCOPES:
            self._detail_combo.addItem(scope, scope)

    def _fill_pair_combo(self) -> None:
        """Combo cặp = ``SUPPORTED_SYMBOLS`` (tiêu thụ — không bịa danh sách)."""
        for symbol in SUPPORTED_SYMBOLS:
            self._pair_combo.addItem(symbol, symbol)

    def _current_detail_scope(self) -> str | None:
        data = self._detail_combo.currentData()
        return str(data) if data is not None else None

    def _current_pair_symbol(self) -> str | None:
        data = self._pair_combo.currentData()
        return str(data) if data is not None else None

    # -- tab Tổng quan (chỉ đọc — không gọi AI) -------------------------------

    def _reload_overview(self) -> None:
        """Nạp lưới 11 tài sản từ verdict mới nhất mỗi chân trời (CHỈ ĐỌC)."""
        rows: list[dict[str, object]] = []
        for scope in self._controller.AI_ASSET_SCOPES:
            verdicts = self._safe_history("currency", scope, AI_OVERVIEW_LIMIT)
            by_horizon: dict[str, TrendVerdict] = {}
            for verdict in verdicts:
                by_horizon.setdefault(verdict.horizon.value, verdict)
            newest = verdicts[0].created_at if verdicts else None
            rows.append({"scope": scope, "verdicts": by_horizon, "at": newest})
        self._overview_model.set_rows(rows)

    def _on_overview_clicked(self, index: QModelIndex) -> None:
        scope = self._overview_model.scope_at(index.row())
        if scope is not None:
            self._show_detail(scope)

    def _show_detail(self, scope: str) -> None:
        combo_index = self._detail_combo.findData(scope)
        if combo_index < 0:
            return
        self._detail_combo.setCurrentIndex(combo_index)  # → _on_detail_scope_changed
        self._tabs.setCurrentWidget(self._detail_tab)

    # -- tab Chi tiết ---------------------------------------------------------

    def _on_detail_scope_changed(self) -> None:
        """Cập nhật dòng đếm + ngữ cảnh + lịch sử (§9.1 bước 2 — KHÔNG gọi AI)."""
        scope = self._current_detail_scope()
        if scope is None:
            return
        try:
            self._preview = self._controller.ai_scope_preview("currency", scope)
        except Exception:
            self._preview = None
            self._count_label.clear()
            self._coverage_label.clear()
            self._context_label.clear()
            self._status_label.setText(AI_INSUFFICIENT_TEXT)
            return
        self._update_count_line()
        self._update_coverage_line()
        self._update_context_line()
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

    def _update_coverage_line(self) -> None:
        """Panel "độ phủ theo chân trời" (đợt 6) — số dòng mỗi cửa sổ đọc từ
        ``ai_scope_preview`` (passthrough policy): UI không tự tính, không gọi AI
        (L1/S2, D1)."""
        preview = self._preview
        if preview is None:
            self._coverage_label.clear()
            return
        self._coverage_label.setText(self._coverage_text(preview))

    @staticmethod
    def _coverage_text(preview) -> str:
        """Chuỗi panel độ phủ — ngày/tối đa lấy NGUYÊN VĂN từ preview (không
        hard-code 7/42/180/50; cột nào thiếu thì mặc định 0, không bịa)."""
        return AI_COVERAGE_TEXT.format(
            label=AI_COVERAGE_LABEL,
            short=AI_COVERAGE_HORIZON_TEXT["short"],
            mid=AI_COVERAGE_HORIZON_TEXT["mid"],
            long=AI_COVERAGE_HORIZON_TEXT["long"],
            short_days=getattr(preview, "short_days", 0),
            mid_days=getattr(preview, "mid_days", 0),
            long_days=getattr(preview, "long_days", 0),
            short_rows=getattr(preview, "short_rows", 0),
            mid_rows=getattr(preview, "mid_rows", 0),
            long_rows=getattr(preview, "long_rows", 0),
            max_label=AI_COVERAGE_MAX_LABEL,
            long_max_rows=getattr(preview, "long_max_rows", 0),
        )

    def _update_context_line(self) -> None:
        """Dòng ngữ cảnh dữ kiện (đợt 5 + mở rộng đợt 6) — UI chỉ ĐỊNH DẠNG giá
        trị typed từ ``ai_scope_preview.context`` (không tự tính, L1/S2); thiếu → "—"."""
        preview = self._preview
        if preview is None:
            self._context_label.clear()
            return
        self._context_label.setText(self._context_text(preview))

    @staticmethod
    def _context_text(preview) -> str:
        """Dòng ngữ cảnh: giữ khuôn đợt 5, thêm delta 3m/6m cho US 2Y/US 10Y và
        rate path 6 tháng (đợt 6 — sketch d.1710-1712); thiếu thành phần → "—"."""
        context = getattr(preview, "context", None)
        parts: list[str] = []
        rates = getattr(context, "rates", ()) if context is not None else ()
        for rate in rates:
            parts.append(
                f"Lãi suất {_ai_number(rate.latest.rate)}% ({rate.trend.value})"
            )
        yields = getattr(context, "yields", None) if context is not None else None
        if yields is not None:
            delta_3m = getattr(yields, "delta_3m", None)
            delta_6m = getattr(yields, "delta_6m", None)
            parts.append(
                AI_YIELD_2Y_TEXT.format(
                    value=_ai_number(yields.yield_2y),
                    delta=_ai_signed(yields.delta_2y),
                    mark3=AI_YIELD_MARK_3M,
                    d3=_ai_signed(getattr(delta_3m, "delta_2y", None)),
                    mark6=AI_YIELD_MARK_6M,
                    d6=_ai_signed(getattr(delta_6m, "delta_2y", None)),
                )
            )
            parts.append(
                AI_YIELD_10Y_TEXT.format(
                    value=_ai_number(yields.yield_10y),
                    delta=_ai_signed(yields.delta_10y),
                    mark3=AI_YIELD_MARK_3M,
                    d3=_ai_signed(getattr(delta_3m, "delta_10y", None)),
                    mark6=AI_YIELD_MARK_6M,
                    d6=_ai_signed(getattr(delta_6m, "delta_10y", None)),
                )
            )
            parts.append(
                AI_YIELD_SPREAD_TEXT.format(spread=_ai_signed(yields.spread_2y10y))
            )
            parts.append(
                AI_YIELD_REAL_TEXT.format(real=_ai_number(yields.real_yield_10y))
            )
        rate_path = getattr(context, "rate_path", None) if context is not None else None
        if rate_path is not None:
            parts.append(
                AI_RATE_PATH_TEXT.format(
                    label=AI_RATE_PATH_LABEL,
                    change=_ai_signed(rate_path.change),
                    then=_ai_number(rate_path.rate_then),
                    now=_ai_number(rate_path.rate_now),
                )
            )
        if not parts:
            return f"{AI_CONTEXT_PREFIX} {NO_VALUE}"
        return f"{AI_CONTEXT_PREFIX} " + " · ".join(parts)

    def _safe_history(self, scope_type: str, scope_value: str, limit: int) -> list[TrendVerdict]:
        try:
            return list(self._controller.verdicts_for(scope_type, scope_value, limit))
        except Exception:
            return []

    def _load_history(self) -> None:
        """Lịch sử nhận định của phạm vi này, mới nhất trước (d.1637) — limit
        là hằng trình bày (B5: không phải giá trị vận hành)."""
        self._clear_layout(self._history_layout)
        scope = self._current_detail_scope()
        if scope is None:
            return
        for verdict in self._safe_history("currency", scope, AI_HISTORY_LIMIT):
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

    # -- lượt nhận định chi tiết (worker nền — khuôn D10) ----------------------

    def _on_analyze_clicked(self) -> None:
        preview = self._preview
        if preview is None or preview.insufficient:
            # Fail-closed: dưới ai_min_items → hiện d.1642, KHÔNG gọi AI (B4).
            self._status_label.setText(AI_INSUFFICIENT_TEXT)
            return
        scope = self._current_detail_scope()
        if scope is None:
            return
        self._status_label.setText(AI_PROGRESS_TEXT)
        self._start_analysis(
            ("currency", scope),
            on_succeeded=self._on_ai_succeeded,
            on_failed=self._on_ai_failed,
            button=self._analyze_button,
            combo=self._detail_combo,
            done=self._on_ai_worker_done,
            thread_attr="_ai_thread",
            worker_attr="_ai_worker",
        )

    def _start_analysis(
        self,
        scope: tuple[str, str],
        *,
        on_succeeded,
        on_failed,
        button,
        combo,
        done,
        thread_attr: str,
        worker_attr: str,
    ) -> None:
        """Khởi chạy một lượt ``analyze_trend`` trong worker nền (khuôn D10).

        Dùng chung cho tab Chi tiết và tab Cặp forex (không copy đường gọi AI)."""
        if getattr(self, worker_attr) is not None:
            return
        button.setEnabled(False)
        combo.setEnabled(False)
        thread = QThread(self)
        controller = self._controller
        worker = NewsReadWorker(lambda: controller.analyze_trend(scope[0], scope[1]))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(on_succeeded)
        worker.failed.connect(on_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(done)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._forget_worker(thread, thread_attr, worker_attr))
        setattr(self, thread_attr, thread)
        setattr(self, worker_attr, worker)
        thread.start()

    def _forget_worker(self, thread: QThread, thread_attr: str, worker_attr: str) -> None:
        if getattr(self, thread_attr) is thread:
            setattr(self, thread_attr, None)
            setattr(self, worker_attr, None)

    def _forget_ai_thread(self, thread: QThread) -> None:
        self._forget_worker(thread, "_ai_thread", "_ai_worker")

    def _on_ai_succeeded(self, payload) -> None:
        if getattr(payload, "insufficient", False):
            self._status_label.setText(AI_INSUFFICIENT_TEXT)
            return
        if not payload.ok:
            self._status_label.setText(payload.error_message or AI_TEXT)
            self._clear_cards(self._cards)
            return
        self._status_label.clear()
        self._render_cards(self._cards, payload.verdicts)

    def _on_ai_failed(self, message: str) -> None:
        self._status_label.setText(message)
        self._clear_cards(self._cards)

    def _on_ai_worker_done(self) -> None:
        self._analyze_button.setEnabled(True)
        self._detail_combo.setEnabled(True)
        self._on_detail_scope_changed()  # dòng đếm + ngữ cảnh + lịch sử

    # -- tab Cặp forex (chỉ đọc — bias suy ra, không gọi AI) ------------------

    def _reload_pair_bias(self) -> None:
        """2 verdict thành phần mới nhất mỗi bên + bias suy ra mỗi chân trời
        (contract §9.3 khoản 2 — UI gọi ``core.pair_bias``, không tự tính)."""
        symbol = self._current_pair_symbol()
        if not symbol or "/" not in symbol:
            return
        base_code, quote_code = (part.strip() for part in symbol.split("/", 1))
        base_by_horizon = self._latest_by_horizon(base_code)
        quote_by_horizon = self._latest_by_horizon(quote_code)
        for horizon in ("short", "mid", "long"):
            base_verdict = base_by_horizon.get(horizon)
            quote_verdict = quote_by_horizon.get(horizon)
            bias = derive_pair_bias(base_verdict, quote_verdict)
            row = self._pair_rows[horizon]
            row["base"].setText(self._leg_text(base_code, base_verdict))
            row["quote"].setText(self._leg_text(quote_code, quote_verdict))
            bias_label = row["bias"]
            bias_label.setText(f"{AI_PAIR_BIAS_PREFIX} {PAIR_BIAS_TEXT.get(bias.value, bias.value)}")
            palette = bias_label.palette()
            palette.setColor(
                QPalette.ColorRole.WindowText,
                semantic_qcolor(DIRECTION_ROLE.get(bias.value, "text_muted")),
            )
            bias_label.setPalette(palette)

    def _latest_by_horizon(self, scope: str) -> dict[str, TrendVerdict]:
        by_horizon: dict[str, TrendVerdict] = {}
        for verdict in self._safe_history("currency", scope, AI_OVERVIEW_LIMIT):
            by_horizon.setdefault(verdict.horizon.value, verdict)
        return by_horizon

    @staticmethod
    def _leg_text(code: str, verdict: TrendVerdict | None) -> str:
        if verdict is None:
            return f"{code}: {AI_NO_VERDICT_TEXT}"
        symbol = DIRECTION_SYMBOL.get(verdict.direction.value, NO_VALUE)
        direction = DIRECTION_TEXT.get(verdict.direction.value, verdict.direction.value)
        confidence = CONFIDENCE_TEXT.get(verdict.confidence.value, verdict.confidence.value)
        return f"{code}: {symbol} {direction} ({confidence})"

    def _on_pair_deep_clicked(self) -> None:
        symbol = self._current_pair_symbol()
        if symbol is None or self._pair_worker is not None:
            return
        self._pair_status.setText(AI_PROGRESS_TEXT)
        self._start_analysis(
            ("pair", symbol),
            on_succeeded=self._on_pair_succeeded,
            on_failed=self._on_pair_failed,
            button=self._pair_deep_button,
            combo=self._pair_combo,
            done=self._on_pair_worker_done,
            thread_attr="_pair_thread",
            worker_attr="_pair_worker",
        )

    def _on_pair_succeeded(self, payload) -> None:
        if getattr(payload, "insufficient", False):
            self._pair_status.setText(AI_INSUFFICIENT_TEXT)
            return
        if not payload.ok:
            self._pair_status.setText(payload.error_message or AI_TEXT)
            self._clear_cards(self._pair_cards)
            return
        self._pair_status.clear()
        self._render_cards(self._pair_cards, payload.verdicts)

    def _on_pair_failed(self, message: str) -> None:
        self._pair_status.setText(message)
        self._clear_cards(self._pair_cards)

    def _on_pair_worker_done(self) -> None:
        self._pair_deep_button.setEnabled(True)
        self._pair_combo.setEnabled(True)
        self._reload_pair_bias()

    # -- batch "Nhận định tất cả" (worker nền — D1/D2) ------------------------

    def _on_batch_clicked(self) -> None:
        if self._batch_worker is not None:
            return
        self._batch_button.setEnabled(False)
        total = len(self._controller.AI_ASSET_SCOPES)
        self._batch_status.setText(
            AI_BATCH_PROGRESS_TEXT.format(done=0, total=total, scope="")
        )
        thread = QThread(self)
        worker = NewsAiBatchWorker(self._controller)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_batch_progress)
        worker.succeeded.connect(self._on_batch_succeeded)
        worker.failed.connect(self._on_batch_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._on_batch_finished)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._forget_batch_thread)
        self._batch_thread = thread
        self._batch_worker = worker
        thread.start()

    def _on_batch_progress(self, done: int, scope: str) -> None:
        total = len(self._controller.AI_ASSET_SCOPES)
        self._batch_status.setText(
            AI_BATCH_PROGRESS_TEXT.format(done=done, total=total, scope=scope)
        )

    def _on_batch_succeeded(self, payload) -> None:
        summary = AI_BATCH_SUMMARY_TEXT.format(
            ok=payload.ok, insufficient=payload.insufficient, error=payload.error
        )
        detail = batch_error_detail(payload)
        if detail:
            summary = f"{summary}\n{AI_BATCH_REASON_TEXT.format(detail=detail)}"
        self._batch_status.setText(summary)
        self._reload_overview()

    def _on_batch_failed(self, message: str) -> None:
        self._batch_status.setText(message)

    def _on_batch_finished(self) -> None:
        self._batch_button.setEnabled(True)

    def _forget_batch_thread(self) -> None:
        self._batch_thread = None
        self._batch_worker = None

    # -- kết quả (dùng chung Chi tiết + Cặp forex) ---------------------------

    def _render_cards(self, cards: dict[str, dict[str, object]], verdicts) -> None:
        self._clear_cards(cards)
        by_horizon = {verdict.horizon.value: verdict for verdict in verdicts}
        for horizon, card in cards.items():
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
            card["frame"].setVisible(True)

    def _clear_cards(self, cards: dict[str, dict[str, object]]) -> None:
        for card in cards.values():
            card["frame"].setVisible(False)
            card["header"].clear()
            card["direction"].clear()
            card["conf"].clear()
            card["rationale"].clear()

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
        """Dừng mọi lượt AI nền (khuôn shutdown của màn) — chờ có giới hạn."""
        for thread_attr, worker_attr in (
            ("_ai_thread", "_ai_worker"),
            ("_pair_thread", "_pair_worker"),
            ("_batch_thread", "_batch_worker"),
        ):
            thread = getattr(self, thread_attr)
            setattr(self, thread_attr, None)
            setattr(self, worker_attr, None)
            if thread is None:
                continue
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
        # (Đợt 3 — slot thread riêng của 2 nút FF và của xuất/nhập file đã được
        # gỡ cùng hai đường hành vi đó; màn chỉ còn worker đọc bảng + worker AI
        # nằm trong chính dialog.)
        self.toolbar_buttons: dict[str, QPushButton] = {}
        # Snapshot giá trị 7 control lọc tại lần áp gần nhất (vòng 6 — chốt mỗi
        # ``reload_rows``); ``None`` = chưa từng nạp được (app giả) → tắt dirty.
        self._applied_snapshot: tuple | None = None
        # Lượt nạp đang chờ được cuộn "tin sắp tới gần nhất" lên đầu khung nhìn
        # (yêu cầu 3).  Màn được dựng MỘT LẦN lúc khởi động app và nằm trong
        # QStackedWidget — lượt nạp đầu thường xong khi màn còn ẩn, lúc đó cuộn
        # vô hiệu; cờ giữ yêu cầu lại cho tới khi màn thật sự hiện.
        self._scroll_pending = False
        # Worker giải thích chỉ số của dialog xem 1 tin (Owner yêu cầu 30/09/2026).
        self._explain_thread: QThread | None = None
        self._explain_worker: NewsReadWorker | None = None
        self.setObjectName("FormScreen")
        self._build_ui()
        self.reload_rows()

    # -- dựng giao diện ---------------------------------------------------------

    def _build_ui(self) -> None:
        # Múi giờ hiển thị — khóa settings.display.timezone qua seam controller
        # (news_screen cấm import services, L1/E2; khuôn _fred_api_key).  Chốt
        # lại mỗi lần dựng màn — điều hướng tới màn phản ánh khóa mới (Owner
        # quyết 25/09/2026).  Controller thiếu/hỏng hành vi (test shell, app
        # chưa cấu hình) → fallback Asia/Ho_Chi_Minh (B4).
        try:
            zone_name = self.news_controller.display_timezone()
        except Exception:
            zone_name = None
        _configure_display_timezone(zone_name)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)
        root.addWidget(page_header("Tin tức"))

        filter_card = card()
        filter_card.layout().setContentsMargins(12, 6, 12, 6)
        filter_card.layout().addWidget(self._filter_bar())
        root.addWidget(filter_card)

        root.addWidget(self._table_card(), 1)
        root.addWidget(self._toolbar())

    def _filter_bar(self) -> QWidget:
        """Card tìm kiếm tin (screen_design "Bố cục" d.1543-1545): ô lọc gọn
        (nhãn co theo chữ + ô co theo nội dung) + nút "Tìm kiếm" cuối dải.

        KHÔNG tự áp lọc khi chọn ô (Owner duyệt 26/09/2026) — đổi combo/ngày
        không connect gì; bấm "Tìm kiếm" mới đọc lại DB theo cửa sổ ngày mới
        rồi áp 5 bộ lọc (đổi ngày phải đọc lại DB nên nút gọi ``reload_rows``,
        không lọc in-memory)."""
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

        self.date_from_input = QDateEdit()
        self.date_from_input.setObjectName("NewsDateFrom")
        self.date_from_input.setCalendarPopup(True)
        self.date_from_input.setDisplayFormat("dd/MM/yyyy")
        self.date_from_input.setButtonSymbols(QDateEdit.ButtonSymbols.NoButtons)
        # Bề rộng theo CHỮ THẬT (Owner 26/09/2026 — bỏ sàn 110px cảm tính):
        # ``sizeHint()`` của QDateEdit được Qt tính từ format "dd/MM/yyyy" theo
        # font đang dùng và đã cộng frame + nút bật lịch/đệm — đủ hiển thị trọn
        # số và dấu "/" ở mọi chữ số (worst-case "31/12/2026").
        self.date_from_input.ensurePolished()
        self.date_from_input.setMinimumWidth(self.date_from_input.sizeHint().width())
        self.date_from_input.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.date_from_input.setDate(QDate.currentDate())

        self.date_to_input = QDateEdit()
        self.date_to_input.setObjectName("NewsDateTo")
        self.date_to_input.setCalendarPopup(True)
        self.date_to_input.setDisplayFormat("dd/MM/yyyy")
        self.date_to_input.setButtonSymbols(QDateEdit.ButtonSymbols.NoButtons)
        # Cùng phép đo theo font như ô ngày bắt đầu (Owner 26/09/2026).
        self.date_to_input.ensurePolished()
        self.date_to_input.setMinimumWidth(self.date_to_input.sizeHint().width())
        self.date_to_input.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.date_to_input.setDate(QDate.currentDate())

        label_width = _filter_label_width()
        date_field = _filter_cell(
            FILTER_LABELS[5],
            self.date_from_input,
            _filter_label(DATE_RANGE_ARROW_TEXT),
            self.date_to_input,
            label_width=label_width,
        )

        self.search_button = action_button(
            SEARCH_BUTTON_TEXT,
            primary=True,
            color="success",
            icon="search",
            icon_role="selection_text",
            icon_disabled_role="selection_text",
        )
        # Chính sách ngang ``Maximum``: nút không giãn full cột lưới (defect
        # 1920×1200@150% — nút phình 612px).
        self.search_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.search_button.clicked.connect(lambda: self.reload_rows())

        # Nút chọn nhanh tuần (Owner yêu cầu 30/09/2026) — nhóm một-chạm đặt
        # khoảng ngày về tuần tương ứng rồi đọc lại dữ liệu, đặt ngay TRƯỚC nút
        # "Tìm kiếm" trong dải lọc.  Giao diện theo khuôn nút chung của hệ thống:
        # ``action_button`` (objectName ``SecondaryButton`` — cùng khuôn nút "Hủy"
        # /"Làm mới"/"Quay lại" của các màn khác), KHÔNG dùng biến thể
        # ``quickFilter`` của thanh "Lọc nhanh" Journal vì biến thể đó cao 28px,
        # lệch với các control 24px cùng hàng (style-guide §3: action button
        # render đúng 24px).  Ba nút là một nhóm loại trừ nhau; trạng thái chọn
        # SUY TỪ khoảng ngày đang áp (``_sync_week_buttons``) chứ không giữ cờ
        # riêng — khoảng ngày không trùng tuần nào thì cả ba bỏ chọn.
        self.week_buttons: dict[str, QPushButton] = {}
        for label in WEEK_BUTTON_LABELS:
            button = action_button(label)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.clicked.connect(
                lambda _checked=False, name=label: self.show_week(name)
            )
            self.week_buttons[label] = button

        # Dirty state (vòng 6 — Owner duyệt 26/09/2026): đổi 1 trong 7 control
        # lọc (5 combo + 2 ngày) mà chưa bấm "Tìm kiếm" → nhấn nút qua property
        # QSS ``filterDirty``; snapshot chốt lại mỗi lần ``reload_rows``.
        for combo in (
            self.kind_combo,
            self.currency_combo,
            self.impact_combo,
            self.source_combo,
            self.status_combo,
        ):
            combo.currentIndexChanged.connect(self._update_filter_dirty)
        self.date_from_input.dateChanged.connect(self._update_filter_dirty)
        self.date_to_input.dateChanged.connect(self._update_filter_dirty)

        # Lưới fluid (khuôn ui/responsive_row.py, opt-in — Owner quyết
        # 26/09/2026: tối đa 2 dòng — dòng 1: Loại tin/Đồng tiền/Tác động/
        # Nguồn; dòng 2: Trạng thái/Khoảng ngày/nút tuần/nút "Tìm kiếm" — 8 ô,
        # nút "Tìm kiếm" là ô cuối lưới, nhóm nút tuần nằm ngay trước nó). Mỗi ô
        # tự định cỡ theo NỘI DUNG
        # THẬT của nó (Owner 26/09/2026 — không dùng chung sàn); cột nhãn
        # đồng nhất ``label_width`` mọi ô ⇒ ô nhập của các dòng cùng cột lưới
        # bắt đầu tại cùng tọa độ (thẳng cột — Owner yêu cầu 26/09/2026).
        # Fluid quét số cột [4..1] chọn số LỚN NHẤT vừa bề ngang thực tế — màn
        # rộng (1920×1200@150% = 1280px logic) giữ nhiều cột, màn hẹp xuống
        # dần tới 1 cột (bố cục chảy như flex-wrap, không bóp ô/tràn khung).
        # Sàn bề ngang = compact 1 cột = Ô RỘNG NHẤT ⇒ màn vừa shell 800px.
        return ResponsiveGrid(
            widgets=[
                _filter_cell(FILTER_LABELS[0], self.kind_combo, label_width=label_width),
                _filter_cell(FILTER_LABELS[1], self.currency_combo, label_width=label_width),
                _filter_cell(FILTER_LABELS[2], self.impact_combo, label_width=label_width),
                _filter_cell(FILTER_LABELS[3], self.source_combo, label_width=label_width),
                _filter_cell(FILTER_LABELS[4], self.status_combo, label_width=label_width),
                date_field,
                self._week_button_cell(),
                _button_cell(self.search_button),
            ],
            columns=4,
            compact_columns=1,
            stretch=False,
            fluid=True,
        )

    def _week_button_cell(self) -> QWidget:
        """Ô lưới của nhóm nút tuần — 3 nút đứng sát nhau, phần bề ngang dư dồn về
        sau (khuôn ``_button_cell``: nút bám trái ô, không bám mép phải cửa sổ)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for label in WEEK_BUTTON_LABELS:
            layout.addWidget(self.week_buttons[label])
        layout.addStretch(1)
        return widget

    def show_week(self, label: str) -> None:
        """Nút tuần: đặt khoảng ngày về tuần của ``label`` rồi đọc lại dữ liệu.

        Nút tuần là hành động xem dữ liệu tường minh (khác các ô lọc — đổi ô lọc
        KHÔNG tự áp, phải bấm "Tìm kiếm"), nên áp ngay: đặt 2 ô ngày rồi gọi
        ``reload_rows`` (đọc lại DB theo cửa sổ mới + chốt snapshot dirty)."""
        start, end = self._week_bounds(label)
        self.date_from_input.setDate(QDate(start.year, start.month, start.day))
        self.date_to_input.setDate(QDate(end.year, end.month, end.day))
        self.reload_rows()

    def _sync_week_buttons(self) -> None:
        """Bật/tắt nhóm nút tuần theo ĐÚNG khoảng ngày đang áp.

        Trạng thái chọn suy từ dữ liệu (2 ô ngày) chứ không giữ cờ riêng: khoảng
        ngày trùng tuần nào thì nút tuần đó được chọn, không trùng tuần nào (vd
        mặc định "hôm nay → hôm nay", hay khoảng ngày người dùng tự chọn) thì cả
        ba nút bỏ chọn — nút không nói sai điều bảng đang hiển thị."""
        current = (
            self.date_from_input.date().toPyDate(),
            self.date_to_input.date().toPyDate(),
        )
        for label, button in self.week_buttons.items():
            button.setChecked(self._week_bounds(label) == current)

    @staticmethod
    def _week_bounds(label: str) -> tuple[date, date]:
        """Biên tuần (Thứ 2 → Chủ nhật) của ``label`` theo múi giờ hiển thị.

        Cùng quy ước tuần với Dashboard (``dashboard_screen``: tuần bắt đầu Thứ 2,
        tính theo ``settings.display.timezone``) — một khái niệm một định nghĩa
        (D6); "hôm nay" lấy từ seam ``_now_utc`` như phần còn lại của màn."""
        today = _now_utc().astimezone(_display_timezone()).date()
        monday = today - timedelta(days=today.weekday())
        if label == WEEK_BUTTON_LABELS[0]:
            monday -= timedelta(days=7)
        elif label == WEEK_BUTTON_LABELS[2]:
            monday += timedelta(days=7)
        return monday, monday + timedelta(days=6)

    def _current_filter_values(self) -> tuple:
        """Giá trị 7 control lọc (5 combo + 2 ngày) — vật liệu so snapshot dirty
        (vòng 6)."""
        return (
            self._selected(self.kind_combo),
            self._selected(self.currency_combo),
            self._selected(self.impact_combo),
            self._selected(self.source_combo),
            self._selected(self.status_combo),
            self.date_from_input.date(),
            self.date_to_input.date(),
        )

    def _update_filter_dirty(self, *_args) -> None:
        """Nhấn nút "Tìm kiếm" qua property QSS ``filterDirty`` khi bộ lọc lệch
        lần áp cuối (vòng 6 — snapshot chốt mỗi ``reload_rows``; đặt property
        qua ``set_dynamic_property`` — khuôn sẵn có của theme_manager, không
        tự unpolish/polish). Chưa có snapshot (màn chưa nạp được — app giả của
        test shell) thì bỏ qua."""
        if self._applied_snapshot is None:
            return
        set_dynamic_property(
            self.search_button,
            "filterDirty",
            self._current_filter_values() != self._applied_snapshot,
        )

    def _enum_combo(self, label: str, options: list[tuple[str, str]]) -> QComboBox:
        """Combo lọc: mục đầu là "Tất cả" (rút gọn — Owner quyết 26/09/2026), rồi
        đúng giá trị enum; ``label`` chỉ dùng đặt objectName cho QSS/kiểm thử."""
        combo = QComboBox()
        combo.setObjectName(f"NewsFilter{_COMBO_NAMES[label]}")
        # Kích thước theo NỘI DUNG THẬT (Owner 26/09/2026 — mỗi ô một bề rộng
        # riêng, không dùng chung sàn cho mọi combo): ``AdjustToContents`` bắt
        # Qt đo chữ theo font đang dùng và trả ``sizeHint`` rộng đủ hiển thị
        # TRỌN mục dài NHẤT trong danh sách lựa chọn (không phải mục mặc định
        # "Tất cả" hay một contents-chữ cảm tính).  Combo nguồn có nhãn dài
        # được phép rộng hơn; lưới fluid lo phần xuống hàng.
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        # Chính sách ngang ``Maximum``: combo không giãn theo cột lưới (giãn thì
        # ô trống thụt sau nhãn — defect 1920×1200@150%); bề ngang bám đúng
        # ``sizeHint`` = chiều rộng mục dài nhất + padding/icon cuộn của Qt.
        combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        # Mục đầu rút gọn "Tất cả" (Owner quyết 26/09/2026) — nhãn cạnh ô đã
        # nói ô đó lọc gì, không lặp "Tất cả loại tin/đồng tiền/…".
        combo.addItem(ALL_PREFIX, None)
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
        return table_card

    def _toolbar(self) -> QWidget:
        """Thanh công cụ: 3 nút hành vi chính căn TRÁI, nút "Tải lại" căn PHẢI
        (Owner chốt 30/09/2026).

        Nhóm trái là một ``ResponsiveGrid`` ``stretch=False`` giữ bề ngang tự nhiên
        của từng nút (không giãn theo cửa sổ) nhưng **biết xuống dòng khi bị bóp** —
        4 nút không vừa một hàng ở cửa sổ tối thiểu 800px nên dãy HBox cứng sẽ
        phá contract kích thước (đo thật: cần 832px > 752px bề ngang nội dung
        shell).  Nút "Tải lại" đứng riêng ở mép phải, sau một khoảng giãn."""
        toolbar = QWidget()
        toolbar.setObjectName("NewsToolbarRow")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        left_group = ResponsiveGrid(
            widgets=[self._toolbar_button(label) for label in TOOLBAR_LABELS[:-1]],
            columns=len(TOOLBAR_LABELS) - 1,
            compact_columns=1,
            stretch=False,
            fluid=True,
        )
        row.addWidget(left_group)
        row.addStretch(1)
        row.addWidget(self._toolbar_button(TOOLBAR_LABELS[-1]))
        return toolbar

    def _toolbar_button(self, label: str) -> QPushButton:
        """Nút thanh công cụ — mỗi nút một hành vi (F4: [Dán | Nhập | AI | Tải lại]).

        Dùng đúng khuôn nút hành động của hệ thống (``action_button`` primary +
        màu + glyph + ``icon_role``/``icon_disabled_role`` = ``selection_text``)
        để đồng nhất với các màn khác; dãy nút căn trái nên mỗi nút giữ bề ngang
        tự nhiên (vừa đủ chứa tiêu đề + icon).  "Tải lại" đọc lại database theo
        đúng bộ lọc đang áp (cập nhật trạng thái mới nhất của trang — Owner yêu
        cầu 30/09/2026) — cùng đường với nút "Tìm kiếm", không đổi cửa sổ ngày."""
        button = action_button(
            label,
            primary=True,
            color="info",
            icon=TOOLBAR_ICONS[label],
            icon_role="selection_text",
            icon_disabled_role="selection_text",
        )
        # Chính sách ngang ``Maximum``: nút giữ bề ngang tự nhiên trong ô lưới
        # (khuôn nút "Tìm kiếm" — cùng lý do: ô lưới rộng không làm nút phình ra).
        button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        if label == TOOLBAR_LABELS[0]:
            button.clicked.connect(self.open_paste_dialog)
        elif label == TOOLBAR_LABELS[1]:
            button.clicked.connect(lambda: self.open_note_dialog())
        elif label == TOOLBAR_LABELS[2]:
            button.clicked.connect(self.open_ai_dialog)
        else:
            button.clicked.connect(self.reload_rows)
        self.toolbar_buttons[label] = button
        return button

    # -- đọc dữ liệu ------------------------------------------------------------

    def reload_rows(self) -> None:
        """Đọc lại bảng trong worker nền (mở màn / bấm "Tìm kiếm" / sau ghi dữ liệu)."""
        if self.news_controller is None:
            self._rows = []
            self._apply_rows([])
            self._scroll_pending = False
            return
        # Mỗi lượt nạp là một cửa sổ dữ liệu mới ⇒ "tin sắp tới gần nhất" của
        # cửa sổ đó phải lên đầu khung nhìn (mục "Tin sắp tới gần nhất lên trên
        # cùng"); cờ được tiêu khi cú cuộn thật sự chạy được.
        self._scroll_pending = True
        # Chốt snapshot dirty-state tại thời điểm áp bộ lọc (vòng 6) rồi tắt
        # nhấn nút ngay — không chờ worker trả kết quả.
        self._applied_snapshot = self._current_filter_values()
        self._update_filter_dirty()
        # Nhóm nút tuần phản ánh khoảng ngày VỪA ÁP (không phải giá trị đang gõ).
        self._sync_week_buttons()
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
        self._shutdown_explanation()
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
        file; hai slot đó đã gỡ cùng hai đường hành vi.)"""
        self.shutdown()
        super().closeEvent(event)

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
        (d.1611-1612); "Hủy" reject = không ghi, không run (§6.1 bước 6)."""
        if self.news_controller is None:
            return
        dialog = self.create_paste_dialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload_rows()

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
        dialog = AiTrendDialog(self.news_controller, self)
        dialog.exec()

    # -- sửa/xóa/toggle theo dòng (D7 — trong dialog chi tiết dòng) ---------------

    def _row_actions(self, dialog: QDialog, row: NewsRow) -> QWidget | None:
        """Hàng điều khiển dòng: Sửa/Xóa cho tin NHẬP TAY (các loại khác không có).

        Nút toggle "Loại trừ" đã được GỠ (Owner chốt 30/09/2026) — cùng lượt gỡ cả
        ``_toggle_excluded`` để không còn code chết; cờ ``excluded`` vẫn là dữ liệu
        của miền (contract §4.3) nhưng không còn đường sửa từ màn này."""
        if row.row_type != ITEM_ROW or row.item is None:
            return None
        if row.source != NewsItemSource.USER.value:
            return None
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
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
        """Khoảng ngày của bộ lọc → mốc ISO UTC (đầu ngày đầu, cuối ngày cuối).

        Ngày người dùng chọn theo MÚI GIỜ NGƯỜI DÙNG (khóa
        ``settings.display.timezone`` — Owner quyết 25/09/2026): 00:00/23:59 của
        ngày chọn trong múi giờ đó, quy về UTC cho truy vấn (DB lưu UTC)."""
        start = self.date_from_input.date().toPyDate()
        end = self.date_to_input.date().toPyDate()
        zone = _display_timezone()
        from_utc = datetime.combine(start, clock_time.min, tzinfo=zone).astimezone(UTC)
        to_utc = datetime.combine(end, clock_time.max, tzinfo=zone).astimezone(UTC)
        return _iso(from_utc), _iso(to_utc)

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
        nearest = self._nearest_upcoming(visible)
        self.table_model.set_rows(self._zone_rows(visible, nearest), nearest=nearest)
        self._apply_section_spans()
        self.status_message.setVisible(False)

    @staticmethod
    def _zone_rows(rows: list[NewsRow], nearest: NewsRow | None) -> list[NewsRow]:
        """Chèn dòng ngăn cách vùng quanh phần tin sắp tới (khuôn Dashboard —
        ``dashboard_screen._render_zone_header``).

        Dashboard chia mục tin thành 3 vùng có dòng ngăn cách: ``ĐÃ QUA`` /
        ``SẮP TỚI GẦN NHẤT`` (đúng MỘT dòng) / ``SẮP TỚI`` (các dòng sắp tới còn
        lại), vùng rỗng thì không vẽ.  Bảng tin giữ nguyên thứ tự thời gian nên
        chỉ phần sắp tới cần dòng ngăn cách: một dòng ngay trên tin sắp tới gần
        nhất, một dòng ngay trên tin sắp tới kế tiếp (không còn tin sắp tới nào
        khác thì không chèn).  Không có tin sắp tới gần nhất → bảng giữ nguyên
        thứ tự thời gian, không dòng ngăn cách nào."""
        if nearest is None:
            return list(rows)
        at = next((i for i, row in enumerate(rows) if row is nearest), None)
        if at is None:
            return list(rows)
        display = rows[:at] + [NewsRow.section(NEAREST_SECTION_TEXT, SECTION_ROLE), nearest]
        if at + 1 < len(rows):
            display.append(NewsRow.section(FUTURE_SECTION_TEXT, FUTURE_ROLE))
        display.extend(rows[at + 1 :])
        return display

    @staticmethod
    def _nearest_upcoming(rows: list[NewsRow]) -> NewsRow | None:
        """Tin sắp tới gần nhất = dòng đầu có mốc thời gian >= hiện tại (dashboard)."""
        now = _now_utc()
        for row in rows:
            moment = _row_moment(row.timestamp_utc)
            if moment is not None and moment >= now:
                return row
        return None

    def _apply_section_spans(self) -> None:
        """Trải dòng ngăn cách qua toàn bộ bề ngang bảng (khuôn span dashboard)."""
        self.table.clearSpans()
        width = self.table_model.columnCount()
        for index, row in enumerate(self.table_model.rows):
            if row.section_text is not None:
                self.table.setSpan(index, 0, 1, width)

    def _sync_currency_options(self, rows: list[NewsRow]) -> None:
        """Danh mục đồng tiền của bộ lọc lấy từ chính dữ liệu đã đọc (không bịa danh sách)."""
        codes = sorted({code for row in rows for code in row.currencies if code})
        current = self._selected(self.currency_combo)
        existing = [self.currency_combo.itemData(index) for index in range(self.currency_combo.count())]
        if existing[1:] == codes:
            return
        self.currency_combo.blockSignals(True)
        self.currency_combo.clear()
        self.currency_combo.addItem(ALL_PREFIX, None)
        for code in codes:
            self.currency_combo.addItem(code, code)
        if current in codes:
            self.currency_combo.setCurrentIndex(codes.index(current) + 1)
        self.currency_combo.blockSignals(False)

    def _set_status(self, message: str) -> None:
        set_rich_html(self.status_message, empty_state_html(message, tone=EMPTY_TONE))
        self.status_message.setVisible(True)

    def _on_rows_loaded(self, payload: object) -> None:
        self._rows = list(payload) if isinstance(payload, list) else []
        self._apply_rows(self._rows)
        self._request_scroll_to_nearest()

    def showEvent(self, event) -> None:  # noqa: N802 — tên API của Qt
        """Màn được hiện (điều hướng tới) → chạy cú cuộn còn treo.

        Khuôn app thật: màn dựng một lần lúc khởi động và nằm trong
        ``QStackedWidget``, nên lượt nạp đầu (kèm yêu cầu cuộn) xong khi màn còn
        ẩn — cuộn lúc đó vô hiệu vì view chưa được bày."""
        super().showEvent(event)
        self._request_scroll_to_nearest()

    def _request_scroll_to_nearest(self) -> None:
        """Hoãn cú cuộn "tin sắp tới gần nhất lên đầu" tới khi chạy được.

        Chỉ cuộn khi còn yêu cầu treo (``_scroll_pending``) VÀ màn đang hiện:
        cuộn trên view chưa bày là vô hiệu.  Hoãn 1 vòng event-loop để view tính
        xong range thanh cuộn sau model reset rồi mới kéo (khuôn QTimer của
        dashboard)."""
        if not self._scroll_pending or not self.isVisible():
            return
        QTimer.singleShot(0, self._scroll_to_nearest)

    def _scroll_to_nearest(self) -> None:
        """Đưa dòng ngăn cách "SẮP TỚI GẦN NHẤT" lên đầu khung nhìn (mặc định của
        bảng — Owner chốt 30/09/2026).

        Đích cuộn là **dòng ngăn cách** của vùng, không phải dòng tin: dòng tin
        sắp tới gần nhất nằm ngay dưới nó nên cả hai cùng hiện ở đầu khung nhìn
        (cuộn thẳng tới dòng tin thì dòng ngăn cách bị đẩy ra ngoài tầm nhìn).
        Cửa sổ không có dòng nào từ hiện tại trở đi thì không cuộn (bảng giữ
        nguyên thứ tự thời gian)."""
        if not self.isVisible():
            # Màn bị ẩn trước khi timer bắn (điều hướng nhanh): cuộn lúc này vô
            # hiệu — giữ yêu cầu lại cho lần màn được hiện kế tiếp.
            return
        self._scroll_pending = False
        rows = self.table_model.rows
        nearest = self.table_model.nearest
        if nearest is None:
            return
        at = next((i for i, row in enumerate(rows) if row is nearest), None)
        if at is None:
            return
        # Dòng ngăn cách vùng "sắp tới gần nhất" nằm ngay trên dòng tin đó
        # (``_zone_rows`` chèn cùng lượt) — có thì lấy nó làm đích cuộn.
        if at > 0 and rows[at - 1].section_text == NEAREST_SECTION_TEXT:
            at -= 1
        self.table.scrollTo(
            self.table_model.index(at, 0), QAbstractItemView.ScrollHint.PositionAtTop
        )

    def _on_rows_failed(self, message: str) -> None:
        set_rich_html(self.status_message, empty_state_html(message, tone="danger", icon="alert-triangle", icon_role="danger"))
        self.status_message.setVisible(True)

    # -- chi tiết dòng ----------------------------------------------------------

    def _on_cell_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        if self.table_model.COLUMNS[index.column()][0] != "detail":
            return
        row = self.table_model.row_at(index.row())
        if row is not None and row.section_text is None:
            self.show_row_detail(row)

    def show_row_detail(self, row: NewsRow) -> None:
        """Mở dialog chi tiết dòng (chặn — chỉ dùng từ tương tác người dùng)."""
        self.row_detail_dialog(row).exec()

    def row_detail_dialog(self, row: NewsRow) -> QDialog:
        """Dựng dialog xem 1 tin: nội dung + dữ liệu của dòng + khối AI (sự kiện FF:
        "Giải thích chỉ số"; tin văn bản: "Phân tích bài viết") + nút "Đóng" của
        hệ thống.

        Hàng SỰ KIỆN FF hiển thị chính số liệu của sự kiện (Kỳ trước/Dự báo/Thực
        tế) thay cho "Giờ fetch"/"raw_json" — hai trường đó vô nghĩa với người
        dùng (Owner yêu cầu 30/09/2026).  Hàng tin văn bản giữ nguyên provenance
        cũ (không đụng — ngoài phạm vi yêu cầu)."""
        dialog = QDialog(self)
        dialog.setWindowTitle(DETAIL_TEXT)
        dialog.setObjectName("NewsDetailDialog")
        # Kích thước Owner chốt 30/09/2026 (trước là 640x420).
        dialog.resize(800, 600)

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
        for index, (label, value_widget) in enumerate(self._detail_rows(row)):
            label_widget = QLabel(compile_rich_html(label))
            label_widget.setObjectName("CardDetail")
            label_widget.setFixedWidth(120)
            # Nhãn hàng là chuỗi ngắn: không wrap + chiều cao cố định để hàng không
            # bị kéo giãn (khoảng dư dồn hết cho ô AI — Owner yêu cầu 30/09/2026).
            label_widget.setWordWrap(False)
            label_widget.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
            )
            if isinstance(value_widget, QLabel):
                # Chỉ nhãn giá trị: chiều cao cố định.  Nút (vd "Xem") giữ nguyên
                # chính sách riêng của nó (``Maximum`` — không giãn full ô lưới).
                value_widget.setSizePolicy(
                    QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
                )
            grid.addWidget(label_widget, index, 0)
            grid.addWidget(value_widget, index, 1)
        # Căn TRÁI (Owner yêu cầu 30/09/2026): bọc lưới vào một khung + stretch ở
        # sau — nếu thả lưới trực tiếp vào layout dọc thì khi ô AI giãn bề ngang,
        # lưới bị thu về bề ngang tự nhiên rồi **căn giữa** (nhãn trôi vào giữa
        # dialog).  Khung này giữ lưới sát lề trái, phần dư dồn về sau.
        grid_holder = QWidget()
        holder_layout = QHBoxLayout(grid_holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.setSpacing(0)
        holder_layout.addLayout(grid)
        holder_layout.addStretch(1)
        root.addWidget(grid_holder)

        # Khối "AI trả lời" của dialog: hàng SỰ KIỆN FF có "Giải thích chỉ số",
        # hàng TIN VĂN BẢN có "Phân tích bài viết" (Owner yêu cầu 30/09/2026).
        ai_frame: QTextEdit | None = None
        ai_task = None
        ai_idle_text = ""
        ai_running_text = ""
        if row.event is not None:
            block, ai_frame = self._ai_text_block(EXPLAIN_HEADER_TEXT, EXPLAIN_HINT_TEXT)
            ai_task = lambda: self.news_controller.explain_event(row.event)  # noqa: E731
            ai_idle_text, ai_running_text = EXPLAIN_TEXT, AI_EXPLAINING_TEXT
        elif row.item is not None:
            block, ai_frame = self._ai_text_block(ANALYZE_HEADER_TEXT, ANALYZE_HINT_TEXT)
            ai_task = lambda: self.news_controller.analyze_article(row.item)  # noqa: E731
            ai_idle_text, ai_running_text = ANALYZE_TEXT, AI_ANALYZING_TEXT
        if ai_frame is not None:
            # Ô AI là phần DUY NHẤT co giãn: mọi khoảng dư nằm trong ô, không để
            # khoảng trống thừa giữa các hàng (Owner yêu cầu 30/09/2026).
            root.addWidget(block, 1)

        # Điều khiển sửa/xóa/toggle theo dòng (D7 — trong dialog chi tiết dòng).
        actions = self._row_actions(dialog, row)
        if actions is not None:
            root.addWidget(actions)

        # Hàng nút cuối: "Giải thích" bên TRÁI, "Đóng" bên PHẢI (Owner chốt
        # 30/09/2026).  "Đóng" theo khuôn nút hệ thống (action_button phụ + icon).
        footer = QWidget()
        footer.setObjectName("NewsDetailFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)
        if ai_frame is not None:
            ai_button = action_button(
                ai_idle_text,
                primary=True,
                color="info",
                icon="bot",
                icon_role="selection_text",
                icon_disabled_role="selection_text",
            )
            ai_button.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
            )
            ai_button.clicked.connect(
                lambda _checked=False: self._start_ai_answer(
                    dialog, ai_frame, ai_button, ai_task, ai_idle_text, ai_running_text
                )
            )
            footer_layout.addWidget(ai_button)
        footer_layout.addStretch(1)
        close_button = action_button(
            CLOSE_TEXT, icon="x", icon_role="text", icon_disabled_role="text"
        )
        close_button.clicked.connect(dialog.accept)
        footer_layout.addWidget(close_button)
        root.addWidget(footer)
        return dialog

    def _detail_pairs(self, row: NewsRow) -> list[tuple[str, str, bool]]:
        """Cặp nhãn/giá trị của dialog xem 1 tin — theo LOẠI dòng.

        Hàng sự kiện FF: Thời gian, Nguồn rồi tới số liệu của chính sự kiện
        (Kỳ trước, Dự báo, Thực tế — Owner yêu cầu 30/09/2026).  Hàng tin văn bản
        giữ nguyên provenance (nguồn, giờ fetch, raw_json, liên kết)."""
        if row.event is None:
            return self._provenance_pairs(row)
        event = row.event
        return [
            (EVENT_DATA_LABELS[0], _display_time(row.timestamp_utc), False),
            (EVENT_DATA_LABELS[1], SOURCE_TEXT.get(row.source, row.source or NO_VALUE), False),
            (EVENT_DATA_LABELS[2], event.previous or NO_VALUE, False),
            (EVENT_DATA_LABELS[3], event.forecast or NO_VALUE, False),
            (EVENT_DATA_LABELS[4], event.actual or NO_VALUE, False),
        ]

    def _ai_text_block(self, header_text: str, hint_text: str) -> tuple[QWidget, QTextEdit]:
        """Khối "văn bản do AI trả lời" của dialog xem 1 tin — trả ``(khối, khung)``.

        Dùng chung cho HAI lời gọi AI của dialog: "Giải thích chỉ số" (hàng sự kiện
        FF) và "Phân tích bài viết" (hàng tin văn bản).  Khối chỉ gồm tiêu đề +
        khung văn bản (không sửa được, khởi đầu bằng câu gợi ý); **nút hành vi do
        hàng nút cuối của dialog gắn** (bên trái, cạnh nút "Đóng" — Owner chốt
        30/09/2026).  Kết quả CHỈ hiển thị cho người dùng tham khảo: không lưu
        database, không vào bất kỳ quy trình nào (§9.2)."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        header = QLabel(header_text)
        header.setObjectName("CardDetail")
        layout.addWidget(header)
        frame = QTextEdit()
        frame.setObjectName("ReadonlyText")
        frame.setReadOnly(True)
        frame.setPlainText(hint_text)
        layout.addWidget(frame, 1)
        return container, frame

    def _start_ai_answer(
        self,
        dialog: QDialog,
        frame: QTextEdit,
        button: QPushButton,
        task,
        idle_text: str,
        running_text: str,
    ) -> None:
        """Chạy một lời gọi AI của dialog trong worker nền (không block GUI).

        ``task`` là callable không tham số trả về văn bản (điều phối qua
        ``NewsController``); nút đổi sang ``running_text`` trong lúc chờ và trở lại
        ``idle_text`` khi xong — cả khi lỗi (lỗi hiện vào khung)."""
        if self.news_controller is None or task is None or self._explain_worker is not None:
            return
        button.setEnabled(False)
        button.setText(running_text)
        thread = QThread(dialog)
        worker = NewsReadWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(
            lambda text: self._on_ai_answer(frame, button, idle_text, str(text))
        )
        worker.failed.connect(
            lambda message: self._on_ai_answer_failed(frame, button, idle_text, str(message))
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._forget_explanation)
        dialog.finished.connect(self._shutdown_explanation)
        self._explain_thread = thread
        self._explain_worker = worker
        thread.start()

    def _on_ai_answer(
        self, frame: QTextEdit, button: QPushButton, idle_text: str, text: str
    ) -> None:
        """Đổ nội dung AI trả lời vào khung và trả nút về trạng thái bấm được."""
        frame.setPlainText(text)
        button.setText(idle_text)
        button.setEnabled(True)

    def _on_ai_answer_failed(
        self, frame: QTextEdit, button: QPushButton, idle_text: str, message: str
    ) -> None:
        """Lỗi provider/chưa cấu hình AI → câu thân thiện vào khung, nút bấm lại được."""
        frame.setPlainText(message)
        button.setText(idle_text)
        button.setEnabled(True)

    def _forget_explanation(self) -> None:
        self._explain_thread = None
        self._explain_worker = None

    def _shutdown_explanation(self) -> None:
        """Dialog xem 1 tin đóng → dừng worker giải thích (không để thread sống ngoài)."""
        thread = self._explain_thread
        self._explain_thread = None
        self._explain_worker = None
        if thread is None:
            return
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(2000)
        except RuntimeError:
            # QThread đã bị xoá (deleteLater) — không còn gì để dừng.
            pass

    def _detail_rows(self, row: NewsRow) -> list[tuple[str, QWidget]]:
        """Các hàng nhãn/giá trị của dialog xem 1 tin (giá trị là widget đã dựng).

        Hàng "Liên kết" do ``_link_value_widget`` quyết định dạng hiển thị (nút
        "Xem" cho tin tự động, liên kết văn bản cho tin nhập tay)."""
        rows: list[tuple[str, QWidget]] = [
            (label, self._value_label(value, is_link=is_link))
            for label, value, is_link in self._detail_pairs(row)
        ]
        link_widget = self._link_value_widget(row)
        if link_widget is not None:
            rows.append((PROVENANCE_LABELS[2], link_widget))
        return rows

    @staticmethod
    def _value_label(value: str, *, is_link: bool = False) -> QLabel:
        """Nhãn giá trị của một hàng (rich text; liên kết mở bằng trình duyệt)."""
        widget = QLabel(compile_rich_html(value))
        widget.setObjectName("CardValue")
        widget.setWordWrap(True)
        widget.setTextFormat(Qt.TextFormat.RichText)
        if is_link:
            widget.setOpenExternalLinks(True)
        return widget

    def _link_value_widget(self, row: NewsRow) -> QWidget | None:
        """Giá trị hàng "Liên kết": nút "Xem" cho tin tự động, None khi không có URL.

        Tin tự động (RSS — Google News / FXStreet / Investing) có URL rất dài nên
        in cả URL vừa rối vừa khó đọc: thay bằng **nút "Xem" mở link ngoài** (Owner
        yêu cầu 30/09/2026).  Tin NHẬP TAY giữ nguyên liên kết văn bản như trước
        (ngoài phạm vi yêu cầu)."""
        item = row.item
        url = item.url if item is not None else None
        if not url:
            return None
        if item.source is NewsItemSource.USER:
            return self._value_label(f"<a href='{url}'>{url}</a>", is_link=True)
        button = action_button(
            LINK_OPEN_TEXT,
            icon="external-link",
            icon_role="text",
            icon_disabled_role="text",
        )
        # Chính sách ngang ``Maximum``: nút giữ bề ngang tự nhiên trong ô lưới
        # (khuôn nút "Tìm kiếm" của màn).
        button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        button.clicked.connect(
            lambda _checked=False, target=str(url): self._open_link(target)
        )
        return button

    @staticmethod
    def _open_link(url: str) -> None:
        """Mở liên kết ngoài bằng trình duyệt mặc định (nút "Xem" của dialog)."""
        QDesktopServices.openUrl(QUrl(url))

    def _provenance_pairs(self, row: NewsRow) -> list[tuple[str, str, bool]]:
        """Cặp nhãn/giá trị provenance của một dòng — chỉ Thời gian + Nguồn.

        "Giờ fetch" và ``raw_json`` đã bỏ khỏi dialog (Owner chốt 30/09/2026 —
        thông tin kỹ thuật, vô nghĩa với người dùng).  URL KHÔNG nằm ở đây: hàng
        "Liên kết" do ``_link_value_widget`` dựng (nút "Xem" hoặc liên kết văn bản)."""
        return [
            (PROVENANCE_LABELS[0], _display_time(row.timestamp_utc), False),
            (PROVENANCE_LABELS[1], SOURCE_TEXT.get(row.source, row.source or NO_VALUE), False),
        ]
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
        return pairs


def _iso(moment: datetime) -> str:
    """Mốc ISO-8601 UTC — cùng khuôn mọi mốc thời gian đã lưu của miền."""
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
