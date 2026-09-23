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

**Lô L3.4 — xuất/nhập file CSV-JSON** (contract §10; screen_design "Hành vi
xuất file" d.1603-1607 + "Hành vi nhập file" d.1600-1601 + "Trạng thái tải và
rỗng" d.1618-1619): nút "Xuất file"/"Nhập file" chạy theo đúng khuôn luồng nền
của 2 nút ForexFactory (D10 — slot thread riêng, disable khi chạy, chỉ báo tiến
trình, thông báo kết thúc).  Màn chỉ đi qua ``NewsController`` → mọi
serializer/parser nằm trong ``services/news_file_transfer.py`` (UI không tự
parse — "Nguyên tắc"); "AI nhận định xu hướng" VẪN disabled (L3.5).

Khai báo đọc-hiểu (V2):

* Xuất theo **khoảng ngày đang lọc** (d.1605); đường dẫn file hiện trong thông
  báo (d.1607).  Xuất/nhập chạy trên slot thread riêng ``_transfer_thread``
  (khuôn ``_fetch_thread`` L3.3) — không đụng lượt đọc bảng.
* Cơ chế chọn format chưa được tài liệu ghim (d.1605 "CSV hoặc JSON") → hộp hai
  nút "CSV"/"JSON" (chuỗi nguyên văn của chính d.1605); cơ chế chọn file nhập →
  ``QFileDialog.getOpenFileName`` với bộ lọc ``*.csv;*.json``, thư mục mở đầu là
  thư mục exports chuẩn.
* Khi một lượt xuất/nhập chạy, disable toàn bộ nhóm nút ghi (2 nút FF + Nhập
  tin + Xuất + Nhập) — khuôn D10; khi kết thúc re-enable; sau lượt NHẬP đọc lại
  bảng (dữ liệu đã đổi), sau lượt XUẤT không cần.

**Lô L3.3 — hành vi tương tác** (screen_design "Hành vi lấy dữ liệu ForexFactory
(2 nút)" + "Hành vi nhập/sửa tin"; contract §6.1/§6.4):

* **2 nút ForexFactory** đi qua ``NewsController`` → ``ff_calendar_producer``
  (screen_design "Nguyên tắc": UI không gọi thẳng producer, mạng chỉ nằm trong
  producer).  Lượt fetch chạy trong worker nền riêng (``NewsReadWorker``, slot
  thread của nút — D10), disable cả 2 nút FF + nút "Nhập tin" khi chạy; kết thúc
  hiện thông báo có kiểu của result (``QMessageBox`` khuôn ``journal_screen`` —
  D8) rồi đọc lại bảng qua `reload_rows()`.
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
* **D9 — prefill "Nhập actual bằng tay":** chọn sự kiện đến hạn sớm nhất của
  tuần bị lỗi từ ``controller.events_pending_actual(now)``; hết sự kiện → form
  trống; KHÔNG tạo đường ghi nào vào ``news_events``.  Vì UI không được import
  ``services/`` (L1) nên thẻ tuần Monday–Sunday được soi gương bằng một hàm
  thuần cục bộ `_ff_week_label` — chỉ dùng cho gợi ý prefill, KHÔNG dùng cho
  quyết định URL fetch (producer giữ thẩm quyền đó).

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
  (``setMinimumWidth``) vì nhãn item dài (vd "ForexFactory (actual)") sẽ đẩy sàn
  vượt 800px nếu để mặc định.
* Bảng đặt bề ngang cột tường minh (khuôn ``scanner_screen._configure_table_columns``):
  cột "Tiêu đề/Nội dung" giãn, các cột còn lại cố định đủ đọc trọn nhãn cột;
  cửa sổ hẹp thì bảng cuộn ngang (``ScrollBarAsNeeded``) thay vì bóp cột tới mức
  chữ bị cắt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time as clock_time, timedelta

from PyQt6.QtCore import (
    QAbstractTableModel,
    QDate,
    QDateTime,
    QModelIndex,
    QTime,
    Qt,
    QThread,
)
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
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

from config.paths import exports_dir
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    ImpactHint,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
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
    "ff_json": "ForexFactory (lịch)",
    "ff_html": "ForexFactory (actual)",
    "google_news_rss": "Google News",
    "fxstreet_rss": "FXStreet",
    "investing_rss": "Investing",
    "fred": "FRED",
    "config_fallback": "Cấu hình dự phòng",
    "user": "Nhập tay",
    "import": "Nhập file",
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
    "Lấy lịch kinh tế",
    "Cập nhật actual",
    "Nhập tin",
    "Xuất file",
    "Nhập file",
    "AI nhận định xu hướng",
)
EMPTY_TEXT = "Không có tin trong khoảng lọc"
LOADING_TEXT = "Đang tải..."
DETAIL_TEXT = "Chi tiết"
ALL_PREFIX = "Tất cả"
NO_VALUE = "—"

# Nhãn dùng trong dialog chi tiết (đều đã có nguồn: nhãn cột hoặc câu chữ screen_design).
PROVENANCE_LABELS: tuple[str, ...] = ("Thời gian", "Nguồn", "Giờ fetch", "Liên kết")

# ---------------------------------------------------------------------------
# Từ điển lô L3.3 — form nhập/sửa tin + 2 nút ForexFactory (screen_design
# "Hành vi nhập/sửa tin" d.1593-1601 + "Hành vi lấy dữ liệu ForexFactory (2 nút)"
# d.1574-1591).  Mọi chuỗi ở đây đều có nguồn đã đăng ký; không phát minh nhãn.
# ---------------------------------------------------------------------------

# Nhãn dialog/nút (nguồn: nhãn nút thanh công cụ đã đăng ký + khối "Bố cục" +
# chuỗi có sẵn của repo).
NOTE_DIALOG_TITLE = TOOLBAR_LABELS[2]  # "Nhập tin" (nhãn nút đã đăng ký)
EDIT_DIALOG_TITLE = "Sửa tin"  # screen_design d.1598 "Sửa/xóa"
EXCLUDE_TEXT = "Loại trừ"  # screen_design d.1598 "toggle Loại trừ"
EDIT_TEXT = "Sửa"  # screen_design d.1598 "Sửa/xóa"
DELETE_TEXT = "Xóa"  # screen_design d.1598 "Sửa/xóa"
MANUAL_ACTUAL_TEXT = "Nhập actual bằng tay"  # screen_design d.1588 (nguyên văn)
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

# Câu thông báo kết quả 2 nút (ghép câu chữ screen_design d.1582-1587 + số liệu
# có kiểu của result — D8).
FETCH_JSON_TITLE = TOOLBAR_LABELS[0]  # "Lấy lịch kinh tế"
FETCH_HTML_TITLE = TOOLBAR_LABELS[1]  # "Cập nhật actual"
JSON_SUCCESS_TEXT = "Đã đồng bộ lịch kinh tế: {inserted} sự kiện mới, {updated} sự kiện cập nhật."
JSON_ERROR_TEXT = "Lấy lịch kinh tế thất bại: {error_type} — {detail}"
HTML_SUCCESS_TEXT = "Đã ghi actual cho {written} sự kiện."
HTML_ERROR_TEXT = "Cập nhật actual thất bại: {error_type} — {detail}"

# Ba hành động bật trong lô này (D10: disable trong lúc một lượt fetch chạy).
FETCH_BUSY_LABELS: tuple[str, ...] = (
    TOOLBAR_LABELS[0],
    TOOLBAR_LABELS[1],
    TOOLBAR_LABELS[2],
)

# Nhãn hành vi lô L3.4 — xuất/nhập file (screen_design d.1600-1607 + d.1618-1619;
# mọi chuỗi có nguồn đăng ký, không phát minh nhãn).
EXPORT_TEXT = TOOLBAR_LABELS[3]  # "Xuất file" (nhãn nút đã đăng ký)
IMPORT_TEXT = TOOLBAR_LABELS[4]  # "Nhập file" (nhãn nút đã đăng ký)
# Câu mời hộp chọn định dạng — nguyên văn screen_design d.1605.
EXPORT_FORMAT_PROMPT = "Xuất CSV hoặc JSON theo khoảng ngày đang lọc"
EXPORT_SUCCESS_TEXT = "Đã xuất file: {path}"  # d.1607: "kết thúc hiện đường dẫn file trong thông báo"
EXPORT_ERROR_TEXT = "Xuất file thất bại: {detail}"
IMPORT_SUCCESS_TEXT = (
    "Nhập file hoàn tất: {inserted} bản ghi mới, {updated} bản ghi cập nhật, {skipped} bỏ qua trùng."
)  # d.1601: "số bản ghi mới / cập nhật / bỏ qua trùng"
IMPORT_ERROR_TEXT = "Nhập file thất bại: {detail}"
IMPORT_DIALOG_TITLE = IMPORT_TEXT

# Nhóm nút disable khi một lượt xuất/nhập đang chạy (khuôn D10 mở rộng từ
# FETCH_BUSY_LABELS: thêm 2 nút của chính lô).
TRANSFER_BUSY_LABELS: tuple[str, ...] = FETCH_BUSY_LABELS + (
    TOOLBAR_LABELS[3],
    TOOLBAR_LABELS[4],
)

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


# ---------------------------------------------------------------------------
# Gợi ý điền sẵn cho "Nhập actual bằng tay" (D9) — hàm thuần
# ---------------------------------------------------------------------------


def _ff_week_label(day_key: str, now: datetime) -> str | None:
    """Thẻ tuần ForexFactory (Monday–Sunday) của một ``day_key`` — hàm thuần.

    Soi gương công thức lịch tuần mà ``ff_calendar_producer`` dùng để chọn trang
    HTML (``this``/``next``/``None``).  UI **không được** import ``services/``
    (L1) nên thẻ tuần được tính lại tại đây, nhưng **chỉ** để chọn sự kiện điền
    sẵn cho form "Nhập actual bằng tay" (D9) — quyết định URL fetch vẫn thuộc
    producer.  Giá trị trả về là chuỗi máy đọc, không phải chuỗi hiển thị.
    """
    try:
        event_date = datetime.strptime(day_key, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    this_monday = now.date() - timedelta(days=now.date().weekday())
    delta_days = (event_date - this_monday).days
    if 0 <= delta_days < 7:
        return "this"
    if 7 <= delta_days < 14:
        return "next"
    return None


def suggest_manual_actual_event(
    pending: list[CalendarEvent], error_week: str = "", now: datetime | None = None
) -> CalendarEvent | None:
    """Chọn sự kiện điền sẵn cho "Nhập actual bằng tay" (D9) — hàm thuần.

    Sự kiện đến hạn sớm nhất **của tuần bị lỗi** (``error_week``); không còn sự
    kiện nào → ``None`` (form mở trống).  Chỉ đọc mốc thời gian — không tạo
    đường ghi nào vào ``news_events``.
    """
    if not pending:
        return None
    moment = now or datetime.now(UTC)
    candidates = pending
    if error_week:
        in_week = [
            event for event in pending if _ff_week_label(event.day_key, moment) == error_week
        ]
        if in_week:
            candidates = in_week
    return min(candidates, key=lambda event: event.event_time_utc)


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
        # Slot thread riêng cho lượt fetch của 2 nút FF (D10) — không đụng lượt
        # đọc bảng đang chạy (``shutdown()`` chỉ dành cho đọc).
        self._fetch_thread: QThread | None = None
        self._fetch_worker: NewsReadWorker | None = None
        self._fetch_channel: str | None = None
        # Slot thread riêng cho xuất/nhập file (L3.4 — khuôn D10).
        self._transfer_thread: QThread | None = None
        self._transfer_worker: NewsReadWorker | None = None
        self._transfer_channel: str | None = None
        self._transfer_fmt: str = ""
        self._transfer_path: str = ""
        self.toolbar_buttons: dict[str, QPushButton] = {}
        self.empty_state_buttons: dict[str, QPushButton] = {}
        self.setObjectName("FormScreen")
        self._build_ui()
        self.reload_rows()

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
        for label in (TOOLBAR_LABELS[0], TOOLBAR_LABELS[2]):
            button = action_button(label)
            # Nút gợi ý empty state đi cùng 2 hành vi đã bật ở toolbar (L3.3).
            button.clicked.connect(self._empty_action_handler(label))
            empty_layout.addWidget(button)
            self.empty_state_buttons[label] = button
        empty_layout.addStretch(1)
        table_card.layout().addWidget(self.empty_actions)
        return table_card

    def _empty_action_handler(self, label: str):
        if label == TOOLBAR_LABELS[0]:
            return lambda: self._start_fetch("json")
        return lambda: self.open_note_dialog()

    def _toolbar(self) -> QWidget:
        toolbar = ResponsiveGrid(
            widgets=[self._toolbar_button(label) for label in TOOLBAR_LABELS],
            columns=len(TOOLBAR_LABELS),
            compact_columns=3,
            stretch=False,
        )
        toolbar.setObjectName("NewsToolbarRow")
        return toolbar

    def _toolbar_button(self, label: str) -> QPushButton:
        """Nút thanh công cụ — 5 nút hành vi đã nối (L3.3 + L3.4);
        "AI nhận định xu hướng" vẫn disabled (L3.5)."""
        button = action_button(label)
        if label == TOOLBAR_LABELS[0]:
            button.clicked.connect(lambda: self._start_fetch("json"))
        elif label == TOOLBAR_LABELS[1]:
            button.clicked.connect(lambda: self._start_fetch("html"))
        elif label == TOOLBAR_LABELS[2]:
            button.clicked.connect(lambda: self.open_note_dialog())
        elif label == TOOLBAR_LABELS[3]:
            button.clicked.connect(self._on_export_clicked)
        elif label == TOOLBAR_LABELS[4]:
            button.clicked.connect(self._on_import_clicked)
        else:
            button.setEnabled(False)
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
        """Đóng màn thì dừng luôn worker nền (không để thread sống ngoài màn)."""
        self.shutdown()
        self._shutdown_fetch()
        self._shutdown_transfer()
        super().closeEvent(event)

    def _shutdown_fetch(self) -> None:
        """Dừng lượt fetch FF nền (D10) — slot thread riêng, chờ có giới hạn."""
        thread = self._fetch_thread
        self._fetch_thread = None
        self._fetch_worker = None
        self._fetch_channel = None
        if thread is None:
            return
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(2000)
        except RuntimeError:
            pass

    # -- xuất/nhập file (§10, screen_design "Hành vi xuất file"/"Hành vi nhập file") --

    def _on_export_clicked(self) -> None:
        """Nút "Xuất file": chọn định dạng rồi chạy lượt xuất nền (L3.4)."""
        fmt = self._choose_export_format()
        if fmt is not None:
            self._start_export(fmt)

    def _choose_export_format(self) -> str | None:
        """Hộp chọn định dạng xuất — hai nút CSV/JSON (V2: cơ chế chọn format
        chưa được tài liệu ghim; chuỗi nguyên văn screen_design d.1605)."""
        box = QMessageBox(self)
        box.setWindowTitle(EXPORT_TEXT)
        box.setText(EXPORT_FORMAT_PROMPT)
        csv_button = action_button("CSV", icon="save", icon_role="text", icon_disabled_role="text")
        box.addButton(csv_button, QMessageBox.ButtonRole.AcceptRole)
        json_button = action_button("JSON", icon="save", icon_role="text", icon_disabled_role="text")
        box.addButton(json_button, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(
            action_button(CANCEL_TEXT, icon="x", icon_role="text", icon_disabled_role="text"),
            QMessageBox.ButtonRole.RejectRole,
        )
        box.exec()
        if box.clickedButton() is csv_button:
            return "csv"
        if box.clickedButton() is json_button:
            return "json"
        return None

    def _start_export(self, fmt: str) -> None:
        """Chạy lượt xuất nền theo khuôn ``_start_fetch`` (D10): disable nhóm
        nút ghi + chỉ báo tiến trình; kết thúc re-enable và thông báo đường dẫn
        file (d.1607).  Màn chỉ gọi ``NewsController`` — parse/serialize nằm
        trong ``services/news_file_transfer.py``."""
        if self.news_controller is None:
            return
        self._transfer_channel = "export"
        self._transfer_fmt = fmt
        self._start_transfer_worker(self._export_task)

    def _export_task(self):
        from_utc, to_utc = self._window_bounds()
        return self.news_controller.export_news_range(from_utc, to_utc, self._transfer_fmt)

    def _on_import_clicked(self) -> None:
        """Nút "Nhập file": chọn file rồi chạy lượt nhập nền (L3.4)."""
        path = self._pick_import_path()
        if path:
            self._start_import(path)

    def _pick_import_path(self) -> str:
        """Chọn file nhập qua hộp chọn file (V2: cơ chế chọn file chưa được tài
        liệu ghim) — thư mục mở đầu là thư mục exports chuẩn."""
        path, _selected = QFileDialog.getOpenFileName(
            self,
            IMPORT_DIALOG_TITLE,
            str(exports_dir()),
            "CSV (*.csv);;JSON (*.json)",
        )
        return path

    def _start_import(self, path: str) -> None:
        """Chạy lượt nhập nền theo khuôn ``_start_fetch`` (D10); kết thúc hiện
        tóm tắt mới/cập nhật/bỏ qua trùng (d.1601) rồi đọc lại bảng."""
        if self.news_controller is None:
            return
        self._transfer_channel = "import"
        self._transfer_path = path
        self._start_transfer_worker(self._import_task)

    def _import_task(self):
        return self.news_controller.import_news_file(self._transfer_path)

    def _start_transfer_worker(self, task) -> None:
        self._set_transfer_busy(True)
        self._set_status(LOADING_TEXT)
        thread = QThread(self)
        worker = NewsReadWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_transfer_succeeded)
        worker.failed.connect(self._on_transfer_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._on_transfer_worker_done)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._forget_transfer_thread(thread))
        self._transfer_thread = thread
        self._transfer_worker = worker
        thread.start()

    def _forget_transfer_thread(self, thread: QThread) -> None:
        if self._transfer_thread is thread:
            self._transfer_thread = None
            self._transfer_worker = None

    def _set_transfer_busy(self, busy: bool) -> None:
        """Disable/enable nhóm nút ghi khi một lượt xuất/nhập chạy (khuôn D10)."""
        for label in TRANSFER_BUSY_LABELS:
            for button in (self.toolbar_buttons.get(label), self.empty_state_buttons.get(label)):
                if button is not None:
                    button.setEnabled(not busy)

    def _on_transfer_worker_done(self) -> None:
        self._set_transfer_busy(False)
        if self._transfer_channel == "import":
            self.reload_rows()  # dữ liệu đã đổi sau lượt nhập

    def _on_transfer_succeeded(self, payload) -> None:
        if self._transfer_channel == "export":
            self._notify(EXPORT_TEXT, EXPORT_SUCCESS_TEXT.format(path=payload.path))
        else:
            self._notify(
                IMPORT_TEXT,
                IMPORT_SUCCESS_TEXT.format(
                    inserted=payload.inserted,
                    updated=payload.updated,
                    skipped=payload.skipped_duplicates,
                ),
            )

    def _on_transfer_failed(self, message: str) -> None:
        if self._transfer_channel == "export":
            self._notify(EXPORT_TEXT, EXPORT_ERROR_TEXT.format(detail=message))
        else:
            self._notify(IMPORT_TEXT, IMPORT_ERROR_TEXT.format(detail=message))

    def _shutdown_transfer(self) -> None:
        """Dừng lượt xuất/nhập nền (L3.4) — slot thread riêng, chờ có giới hạn."""
        thread = self._transfer_thread
        self._transfer_thread = None
        self._transfer_worker = None
        self._transfer_channel = None
        if thread is None:
            return
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(2000)
        except RuntimeError:
            pass

    # -- 2 nút ForexFactory (§6.1 lượt 2-3, screen_design d.1574-1591) -----------

    def _start_fetch(self, channel: str) -> None:
        """Chạy một lượt fetch FF trong worker nền riêng (D10).

        Nút được disable + chỉ báo tiến trình khi chạy; kết thúc re-enable và đọc
        lại bảng.  Màn chỉ gọi ``NewsController`` — mạng nằm trong producer
        (screen_design "Nguyên tắc")."""
        if self.news_controller is None:
            return
        self._fetch_channel = channel
        self._set_fetch_busy(True)
        self._set_status(LOADING_TEXT)
        thread = QThread(self)
        worker = NewsReadWorker(self._fetch_json_task if channel == "json" else self._fetch_html_task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_fetch_succeeded)
        worker.failed.connect(self._on_fetch_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._on_fetch_worker_done)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._forget_fetch_thread(thread))
        self._fetch_thread = thread
        self._fetch_worker = worker
        thread.start()

    def _fetch_json_task(self):
        return self.news_controller.fetch_calendar_json()

    def _fetch_html_task(self):
        return self.news_controller.fetch_actual_html()

    def _forget_fetch_thread(self, thread: QThread) -> None:
        if self._fetch_thread is thread:
            self._fetch_thread = None
            self._fetch_worker = None

    def _set_fetch_busy(self, busy: bool) -> None:
        """Disable/enable 2 nút FF + nút "Nhập tin" (cả toolbar lẫn empty state) — D10."""
        for label in FETCH_BUSY_LABELS:
            for button in (self.toolbar_buttons.get(label), self.empty_state_buttons.get(label)):
                if button is not None:
                    button.setEnabled(not busy)

    def _on_fetch_worker_done(self) -> None:
        self._set_fetch_busy(False)
        self.reload_rows()

    def _on_fetch_succeeded(self, payload: object) -> None:
        if self._fetch_channel == "json":
            self._notify_json_result(payload)
        else:
            self._notify_html_result(payload)

    def _on_fetch_failed(self, message: str) -> None:
        title = FETCH_HTML_TITLE if self._fetch_channel == "html" else FETCH_JSON_TITLE
        self._notify(title, message)

    def _notify_json_result(self, result) -> None:
        """Thông báo tóm tắt/lỗi lượt JSON (D8)."""
        if result.feed_errors:
            first = result.feed_errors[0]
            self._notify(
                FETCH_JSON_TITLE,
                JSON_ERROR_TEXT.format(error_type=first.error_type, detail=first.detail),
            )
        else:
            self._notify(
                FETCH_JSON_TITLE,
                JSON_SUCCESS_TEXT.format(inserted=result.inserted, updated=result.updated),
            )

    def _notify_html_result(self, result) -> None:
        """Thông báo lượt HTML (D8) — lỗi kèm gợi ý "Nhập actual bằng tay" bấm được."""
        if result.fetch_errors:
            first = result.fetch_errors[0]
            self._notify(
                FETCH_HTML_TITLE,
                HTML_ERROR_TEXT.format(error_type=first.error_type, detail=first.detail),
                suggestion=MANUAL_ACTUAL_TEXT,
                on_suggestion=lambda: self.open_note_dialog(
                    prefill_event=self._suggested_pending_event(first.week)
                ),
            )
        else:
            self._notify(
                FETCH_HTML_TITLE,
                HTML_SUCCESS_TEXT.format(written=result.written),
            )

    def _suggested_pending_event(self, week: str) -> CalendarEvent | None:
        """Sự kiện điền sẵn cho "Nhập actual bằng tay" (D9) — đọc qua controller."""
        if self.news_controller is None:
            return None
        moment = datetime.now(UTC)
        try:
            pending = list(self.news_controller.events_pending_actual(moment))
        except Exception:
            return None
        return suggest_manual_actual_event(pending, week, moment)

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

    def _currency_codes(self) -> list[str]:
        codes: list[str] = []
        for index in range(1, self.currency_combo.count()):
            code = self.currency_combo.itemData(index)
            if code:
                codes.append(str(code))
        return codes

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
