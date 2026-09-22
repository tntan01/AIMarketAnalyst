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

**Ngoài phạm vi lô này** (V2 — không vẽ kèm hành vi): 6 nút thanh công cụ được
vẽ đúng nhãn đã đăng ký nhưng để **disabled** — hành vi của chúng thuộc L3.3
(2 nút ForexFactory + nhập tin), L3.4 (xuất/nhập file), L3.5 (AI nhận định);
hai nút gợi ý trong empty state cũng vậy.  Không có đường ghi nào trong lô này.

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
from datetime import UTC, datetime, time as clock_time

from PyQt6.QtCore import QAbstractTableModel, QDate, QModelIndex, Qt, QThread
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
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
# Màn
# ---------------------------------------------------------------------------


class NewsScreen(QWidget):
    """Màn Quản lý tin — khung bảng lọc + chi tiết dòng (plan lô L3.2)."""

    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.news_controller = getattr(app, "news_controller", None) if app is not None else None
        self.table_model = NewsTableModel()
        self._rows: list[NewsRow] = []
        self._thread: QThread | None = None
        self._worker: NewsReadWorker | None = None
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
            button.setEnabled(False)
            empty_layout.addWidget(button)
            self.empty_state_buttons[label] = button
        empty_layout.addStretch(1)
        table_card.layout().addWidget(self.empty_actions)
        return table_card

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
        """Nút thanh công cụ — VẼ đúng nhãn đã đăng ký, hành vi thuộc lô sau."""
        button = action_button(label)
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
        super().closeEvent(event)

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
