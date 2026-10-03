from __future__ import annotations

from config.constants import SUPPORTED_SYMBOLS
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QEvent, QObject
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from ui.screens.shared import action_button
from services.data_provider import ConnectionStatus
from services.market_data_service import fetch_market_overview
from services.mt5_service import MT5Service
from services.settings_service import SettingsService
from ui.icons import flat_pixmap
from ui.responsive_row import ResponsiveGrid
from ui.rich_text import compile_rich_html, empty_state_html, set_rich_html
from ui.theme.fonts import QSS_TITLE
from ui.theme_manager import (
    current_palette,
    is_light_theme,
    set_dynamic_property,
)


class MarketWorker(QThread):
    finished = pyqtSignal(dict)

    def run(self):
        self.finished.emit(fetch_market_overview())


_BRIEFING_IDLE_HINT = (
    "Bản tin AI tổng hợp DXY, VIX, lợi suất trái phiếu Mỹ và sự kiện ảnh "
    "hưởng lớn sắp tới thành kịch bản phiên. Bấm \"Tạo bản tin\" để bắt đầu."
)


def _display_timezone(settings_service) -> ZoneInfo:
    """Timezone hiển thị từ settings, fallback Asia/Ho_Chi_Minh."""
    try:
        tz_str = settings_service.load().display.timezone
    except Exception:
        tz_str = "Asia/Ho_Chi_Minh"
    try:
        return ZoneInfo(tz_str)
    except Exception:
        return ZoneInfo("Asia/Ho_Chi_Minh")


def _iso_utc_seconds(moment: datetime) -> str:
    """Khuôn ISO-8601 UTC mà producer ghi (``YYYY-MM-DDTHH:MM:SSZ``).

    ``NewsRepository.events_in_range`` so sánh ``event_time_utc`` dạng CHUỖI, nên
    biên cửa sổ phải cùng khuôn mới đúng thứ tự thời gian (cùng helper với
    ``services/news_macro_provider._utc_iso``).
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fetch_upcoming_red_events(*, limit: int = 4, hours_ahead: int = 72) -> list[dict]:
    """Sự kiện impact cao trong ``hours_ahead`` giờ tới (đọc ``news.db``).

    Nguồn: ``NewsRepository.events_in_range`` (một nguồn chân lý của miền Tin tức).
    Đây là giao-tạm cho ca đấu nối (a): Dashboard chưa có đặc tả riêng nên hàm giữ
    NGUYÊN hành vi cũ (không lọc currency, cap ``limit``, sắp ASC) chỉ đổi nguồn
    dữ liệu; ca (a) sẽ thẩm định lại đúng quy cách.
    """
    from services.calendar_helpers import _is_high_impact, parse_event_time
    from services.news_repository import NewsRepository

    now = datetime.now(timezone.utc)
    try:
        events = NewsRepository().events_in_range(
            _iso_utc_seconds(now),
            _iso_utc_seconds(now + timedelta(hours=hours_ahead)),
        )
    except Exception:
        return []
    upcoming: list[tuple[datetime, dict]] = []
    for event in events:
        impact = getattr(getattr(event, "impact", ""), "value", getattr(event, "impact", ""))
        if not _is_high_impact(str(impact)):
            continue
        time_utc = str(getattr(event, "event_time_utc", ""))
        dt = parse_event_time(time_utc)
        if dt is None or dt < now:
            continue
        upcoming.append(
            (
                dt,
                {
                    "currency": str(getattr(event, "currency", "")),
                    "event": str(getattr(event, "title", "")),
                    "impact": str(impact),
                    "forecast": getattr(event, "forecast", None),
                    "previous": getattr(event, "previous", None),
                    "time_utc": time_utc,
                    "display_time": dt,
                },
            )
        )
    upcoming.sort(key=lambda pair: pair[0])
    return [ev for _dt, ev in upcoming[:limit]]


def _build_briefing_prompt(overview: dict, events: list[dict], tz: ZoneInfo | None = None) -> str:
    def fmt(tag: str) -> str:
        pair = overview.get(tag)
        if isinstance(pair, (tuple, list)) and len(pair) == 2:
            close, change_pct = float(pair[0]), float(pair[1])
            arrow = "tăng" if change_pct > 0 else "giảm" if change_pct < 0 else "đi ngang"
            return f"{close:.2f} ({arrow} {abs(change_pct):.1f}%)"
        return "không có dữ liệu"

    tz_label = str(getattr(tz, "key", "")) or "UTC"
    now = datetime.now(tz) if tz is not None else datetime.now(timezone.utc)

    def fmt_event_time(when: datetime) -> str:
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if tz is not None:
            when = when.astimezone(tz)
        return when.strftime("%d/%m %H:%M")

    lines: list[str] = [
        "Bạn là chuyên gia phân tích thị trường của ứng dụng giao dịch. Soạn \"Bản tin hôm nay\" NGẮN GỌN (khoảng 350 từ) bằng tiếng Việt cho trader Forex/Vàng/BTC, dựa CHỈ trên dữ liệu thực tế dưới đây:",
        f"- Thời điểm tạo bản tin: {now.strftime('%d/%m/%Y %H:%M')} (giờ {tz_label})",
        f"- DXY: {fmt('DXY')}",
        f"- VIX: {fmt('VIX')}",
        f"- US10Y: {fmt('US10Y')}",
        f"- US2Y: {fmt('US2Y')}",
    ]
    if events:
        lines.append(f"- Sự kiện ảnh hưởng lớn sắp tới (giờ {tz_label}):")
        for ev in events:
            when = ev.get("display_time")
            when_str = fmt_event_time(when) if isinstance(when, datetime) else "không rõ giờ"
            item = f"  - {str(ev.get('currency', ''))} {str(ev.get('event', ''))} lúc {when_str}"
            if ev.get("forecast"):
                item += f", dự báo {ev['forecast']}"
            if ev.get("previous"):
                item += f", kỳ trước {ev['previous']}"
            lines.append(item)
    else:
        lines.append("- Sự kiện ảnh hưởng lớn trong 72 giờ tới: không có.")
    lines.extend(
        [
            "",
            "Trả lời bằng markdown, đúng cấu trúc sau:",
            "### Bối cảnh thị trường",
            "(2-3 câu: USD mạnh/yếu, tâm lý risk-on/off, mức biến động)",
            "",
            "### Điểm đáng chú ý hôm nay",
            "(2-3 gạch đầu dòng: cặp tiền/tài sản đáng theo dõi, hướng thiên về, lý do bám vào dữ liệu trên)",
            "",
            "### Rủi ro cần né",
            "(1-2 gạch đầu dòng: sự kiện đỏ kèm giờ cụ thể, cảnh báo thanh khoản nếu VIX bất thường)",
            "",
            "### Chốt nhanh",
            "(một câu hành động cho phiên hôm nay)",
            "",
            "QUAN TRỌNG: không bịa số liệu, không liệt kê lại input, đi thẳng vào phân tích.",
        ]
    )
    return "\n".join(lines)


def _briefing_cache_key(overview: dict, events: list[dict]) -> str:
    """Khóa cache bản tin: ngày + snapshot vĩ mô + danh sách sự kiện đỏ."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    macro = ",".join(
        f"{tag}:{float(overview[tag][0]):.2f}"
        for tag in ("DXY", "VIX", "US10Y", "US2Y")
        if tag in overview
    )
    ev = "|".join(
        f"{str(item.get('time_utc', ''))}:{str(item.get('currency', ''))}:{str(item.get('event', ''))}"
        for item in events
    )
    return f"{day}|{macro}|{ev}"


# Ngân sách token cho bản tin. Model suy luận (DeepSeek-R1 line) đốt phần lớn
# ngân sách vào ``reasoning_content`` TRƯỚC khi viết câu trả lời (~350 từ) —
# SSE parser cố ý bỏ qua delta reasoning nên ngân sách quá thấp (vd 1200)
# khiến stream về rỗng (finish_reason=length, chưa kịp content). 4000 đủ dứt
# điểm (đo thật: reasoning ~5.5k ký tự + content ~1.5k ký tự → stop). Lần
# fallback nâng ngân sách — khuôn retry news controller §9.1 (tối đa 2 lần gọi).
_BRIEFING_MAX_TOKENS = 4000
_BRIEFING_FALLBACK_MAX_TOKENS = 8000


class BriefingWorker(QThread):
    """Soạn bản tin AI hằng ngày: fetch dữ liệu rồi stream phản hồi.

    Dữ liệu vào: ``fetch_market_overview`` (service đã cache 30 phút) và
    sự kiện impact cao từ Forex Factory. ``tz`` là múi giờ hiển thị từ
    Settings — giờ sự kiện trong prompt được quy đổi sang múi giờ này.
    Phản hồi stream qua ``chunk_ready`` để UI render dần; kết quả cuối
    (markdown) trả qua ``finished`` kèm ``cache_key`` để phiên sau không
    gọi lại AI khi dữ liệu chưa đổi.

    Stream về rỗng (model suy luận nuốt hết ngân sách vào reasoning) →
    gọi lại MỘT lần đường non-stream với ngân sách cao hơn — đường này có
    typed error (``AIOutputBudgetError``) và fallback reasoning_content
    cho gateway trả lời nguyên trong reasoning.
    """

    status = pyqtSignal(str)
    events_ready = pyqtSignal(list)
    chunk_ready = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, ai_config, market_values: dict | None = None, tz: ZoneInfo | None = None):
        super().__init__()
        self.ai_config = ai_config
        self.market_values = dict(market_values or {})
        self.tz = tz
        self.stop_flag = False

    def run(self):
        try:
            from services.ai_service import AIService, AIOutputBudgetError

            self.status.emit("Đang tải chỉ số thị trường...")
            overview = self.market_values or fetch_market_overview()

            self.status.emit("Đang tải sự kiện ảnh hưởng lớn...")
            events = _fetch_upcoming_red_events()
            self.events_ready.emit(events)

            prompt = _build_briefing_prompt(overview, events, tz=self.tz)
            ai = AIService(self.ai_config)

            self.status.emit("AI đang soạn bản tin...")
            parts: list[str] = []
            for chunk in ai.analyze_stream(prompt, max_tokens=_BRIEFING_MAX_TOKENS):
                if self.stop_flag:
                    return
                parts.append(chunk)
                self.chunk_ready.emit(chunk)
            text = "".join(parts).strip()

            if not text:
                self.status.emit("AI đang soạn lại với ngân sách lớn hơn...")
                try:
                    text = ai.analyze(
                        prompt, max_tokens=_BRIEFING_FALLBACK_MAX_TOKENS
                    ).strip()
                except AIOutputBudgetError as exc:
                    self.error.emit(f"{exc} Thử lại hoặc đổi model ít suy luận hơn.")
                    return
                if text:
                    self.chunk_ready.emit(text)

            if not text:
                self.error.emit("AI trả về phản hồi rỗng.")
                return
            self.finished.emit(
                {
                    "text": text,
                    "overview": overview,
                    "events": events,
                    "cache_key": _briefing_cache_key(overview, events),
                }
            )
        except Exception as exc:
            if not self.stop_flag:
                self.error.emit(str(exc))


class _ElidedLabel(QLabel):
    """QLabel that truncates long text with "..." instead of wrapping."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:
        self._full_text = text or ""
        super().setText(self._full_text)
        self._apply_elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        elided = self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, self.width()
        )
        if elided != self.text():
            super().setText(elided)


# Icon phẳng (glyph trong ui/icons.py) cho mỗi thẻ trạng thái — pixmap tint
# theo state, đặt trong nền tròn mờ bên trái thẻ (thay emoji cũ).
STATUS_CARD_FLAT_ICONS = {
    "Kết nối": "plug",
    "Broker": "user",
    "AI": "bot",
    "Nguồn dữ liệu": "bar-chart",
}

# State của thẻ → semantic role tint glyph.
_STATE_ICON_ROLES = {"ok": "success", "warning": "warning", "danger": "danger"}


class StatusCardEventFilter(QObject):
    def __init__(self, screen, icon, value_label, parent=None, icon_name=None):
        super().__init__(parent)
        self.screen = screen
        self.icon = icon
        self.value_label = value_label
        self.icon_name = icon_name

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.DynamicPropertyChange, QEvent.Type.StyleChange):
            if event.type() == QEvent.Type.DynamicPropertyChange and event.propertyName() != b"state":
                return super().eventFilter(obj, event)

            state = obj.property("state") or "warning"

            set_dynamic_property(self.icon, "state", state)
            self._apply_flat_icon(state)
        return super().eventFilter(obj, event)

    def _apply_flat_icon(self, state):
        """Re-set pixmap glyph theo state mới (QSS chỉ tint được text, pixmap
        phải re-render tay)."""
        if not self.icon_name or self.icon is None:
            return
        role = _STATE_ICON_ROLES.get(state, "warning")
        self.icon.setPixmap(flat_pixmap(self.icon_name, role, size=16))


def _status_card_content_width(card: QFrame) -> int:
    """Bề ngang tối thiểu để thẻ hiển thị trọn chữ của nó.

    Nhãn trong thẻ dùng elide (``_ElidedLabel``, ``QSizePolicy.Ignored``) nên
    ``minimumSizeHint`` của thẻ gần 0 — không dùng được để quyết định lưới có
    phải giảm cột hay không. Đo trực tiếp chữ dài nhất cộng icon và lề.
    """

    widest_text = 0
    for label in card.findChildren(_ElidedLabel):
        full_text = getattr(label, "_full_text", "") or ""
        widest_text = max(
            widest_text, label.fontMetrics().horizontalAdvance(full_text)
        )
    layout = card.layout()
    margins = layout.contentsMargins() if layout is not None else None
    spacing = layout.spacing() if layout is not None else 0
    icon = card.findChild(QLabel, "StatusIcon")
    icon_width = icon.width() if icon is not None and icon.width() > 0 else 28
    side_margins = (margins.left() + margins.right()) if margins is not None else 28
    return widest_text + side_margins + spacing + icon_width


class DashboardScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.mt5 = app.mt5 if app else MT5Service()
        self.settings_service = app.settings_service if app else SettingsService()
        self.status_cards: dict[str, tuple[QFrame, QLabel, QLabel]] = {}
        self._light = self._is_light_theme()
        self._ai_last_snapshot: str = ""
        self._ai_cached_response: str = ""
        self._market_values: dict = {}
        self._briefing_text: str = ""
        self._briefing_cache_key: str = ""
        self._briefing_worker: QThread | None = None
        self.setObjectName("DashboardScreen")
        self._build_ui()
        self.refresh_status()

    def refresh_theme_styles(self) -> None:
        self._light = self._is_light_theme()
        self._retint_status_icons()
        self._refresh_market_overview()
        if not self._briefing_text and getattr(self, "briefing_text", None) is not None:
            self._show_briefing_empty(_BRIEFING_IDLE_HINT)

    def _is_light_theme(self) -> bool:
        return is_light_theme(self.settings_service)

    def _retint_status_icons(self) -> None:
        """Re-render pixmap glyph của 4 thẻ trạng thái theo theme hiện hành.

        QPixmap nằm ngoài cơ chế lazy-tint của FlatIconEngine (QIcon) nên
        phải re-set tay khi đổi theme; button dùng QIcon không cần bước này.
        """
        for title, (frame, _value_label, _detail_label) in self.status_cards.items():
            icon_name = STATUS_CARD_FLAT_ICONS.get(title)
            if not icon_name:
                continue
            for label in frame.findChildren(QLabel):
                if label.objectName() == "StatusIcon":
                    state = label.property("state") or frame.property("state") or "warning"
                    label.setPixmap(
                        flat_pixmap(icon_name, _STATE_ICON_ROLES.get(state, "warning"), size=16)
                    )
                    break

    def _build_ui(self) -> None:
        # Ở viewport compact, lưới thẻ 2×2 làm nội dung cao hơn vùng hiển thị;
        # đặt toàn bộ nội dung trong vùng cuộn dọc để không mất phần dưới.
        # Desktop đã vừa nên không mọc thanh cuộn.
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(18)
        root.addLayout(self._build_header())
        root.addWidget(self._build_status_grid())
        self.mt5_warning = self._build_mt5_warning()
        root.addWidget(self.mt5_warning)
        self.market_overview = self._build_market_overview()
        root.addWidget(self.market_overview)
        self.briefing_section = self._build_briefing_section()
        root.addWidget(self.briefing_section)

        scroll = QScrollArea()
        scroll.setObjectName("DashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(scroll)
        self._refresh_market_overview()

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)
        title_box = QVBoxLayout()
        title = QLabel("Bảng điều khiển")
        title.setObjectName("PageTitle")
        title_box.addWidget(title)
        coverage = QLabel(f"{len(SUPPORTED_SYMBOLS)} mã")
        coverage.setObjectName("HeaderBadge")
        coverage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(title_box, 1)
        layout.addWidget(coverage)
        return layout

    def _build_status_grid(self) -> QWidget:
        # Lưới card tự giảm còn 2 cột khi viewport hẹp: ở compact hàng 4 card
        # làm chữ trong thẻ bị cắt, trái với "không cắt card" của contract R3.
        items = [
            ("Kết nối", "Đang kiểm tra", "Đang đọc kết nối dữ liệu", "warning"),
            ("Broker", "Đang kiểm tra", "Đang đọc tài khoản", "warning"),
            ("AI", "Đang kiểm tra", "Đang đọc cấu hình AI", "warning"),
            ("Nguồn dữ liệu", "Đang kiểm tra", "Đang xác định nguồn dữ liệu", "warning"),
        ]
        cards = [self._status_card(*item) for item in items]
        self.status_grid = ResponsiveGrid(
            widgets=cards,
            columns=len(cards),
            compact_columns=2,
            item_min_width=max(_status_card_content_width(card) for card in cards),
        )
        return self.status_grid

    def _status_card(self, title: str, value: str, detail: str, state: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("StatusCard")
        frame.setProperty("state", state)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        frame.setFixedHeight(64)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        # Icon phẳng (pixmap glyph) trong nền tròn mờ bên trái thẻ
        icon_name = STATUS_CARD_FLAT_ICONS.get(title)
        icon_label = QLabel()
        icon_label.setObjectName("StatusIcon")
        icon_label.setFixedSize(28, 28)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setProperty("state", state)
        if icon_name:
            icon_label.setPixmap(
                flat_pixmap(icon_name, _STATE_ICON_ROLES.get(state, "warning"), size=16)
            )

        # Vertical layout for text (value + detail)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Dòng 1: tên thẻ (nhỏ, nhạt) — Dòng 2: thông tin chi tiết (đậm)
        value_label = _ElidedLabel(value)
        value_label.setObjectName("CardValue")

        detail_label = _ElidedLabel(detail)
        detail_label.setObjectName("CardDetailLabel")

        text_layout.addWidget(value_label)
        text_layout.addWidget(detail_label)

        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(text_layout, 1)

        # Propagate state changes to the icon so its tinted background follows
        event_filter = StatusCardEventFilter(self, icon_label, value_label, frame, icon_name=icon_name)
        frame.installEventFilter(event_filter)

        self.status_cards[title] = (frame, value_label, detail_label)
        return frame

    def _build_mt5_warning(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("WarningPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)
        text_box = QVBoxLayout()
        self.mt5_warning_title = QLabel("Dữ liệu chưa sẵn sàng")
        self.mt5_warning_title.setObjectName("WarningTitle")
        self.mt5_warning_detail = QLabel("Hãy kiểm tra kết nối dữ liệu và đăng nhập tài khoản.")
        self.mt5_warning_detail.setObjectName("WarningDetail")
        self.mt5_warning_detail.setWordWrap(True)
        text_box.addWidget(self.mt5_warning_title)
        text_box.addWidget(self.mt5_warning_detail)
        retry = action_button(
            "Thử lại",
            primary=True,
            color="info",
            icon="refresh",
            icon_role="selection_text",
            icon_disabled_role="selection_text",
        )
        retry.clicked.connect(self.refresh_mt5_status)
        layout.addLayout(text_box, 1)
        layout.addWidget(retry)
        return panel

    def _build_market_overview(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(20)

        self.dxy_label = QLabel("DXY: Đang tải...")
        self.dxy_label.setObjectName("MarketBadge")

        self.vix_label = QLabel("VIX: Đang tải...")
        self.vix_label.setObjectName("MarketBadge")

        self.us10y_label = QLabel("US10Y: Đang tải...")
        self.us10y_label.setObjectName("MarketBadge")

        self.us2y_label = QLabel("US2Y: Đang tải...")
        self.us2y_label.setObjectName("MarketBadge")

        layout.addWidget(self.dxy_label)
        layout.addWidget(self.vix_label)
        layout.addWidget(self.us10y_label)
        layout.addWidget(self.us2y_label)
        help_btn = action_button(
            "Giải thích chỉ số",
            primary=True,
            color="info",
            icon="help-circle",
            icon_role="selection_text",
            icon_disabled_role="selection_text",
        )
        help_btn.setToolTip("Ý nghĩa các chỉ số")
        help_btn.clicked.connect(self._show_market_help)
        layout.addWidget(help_btn)
        layout.addStretch(1)
        return panel

    # ------------------------------------------------------------------
    # AI Daily Briefing
    # ------------------------------------------------------------------
    def _build_briefing_section(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header row
        header_layout = QHBoxLayout()
        title = QLabel("Bản tin AI hôm nay")
        title.setObjectName("PanelTitle")
        header_layout.addWidget(title)

        self.briefing_date_label = QLabel("")
        self.briefing_date_label.setObjectName("CardDetail")
        header_layout.addWidget(self.briefing_date_label)
        header_layout.addStretch()

        self.briefing_status_label = QLabel("")
        self.briefing_status_label.setObjectName("CardDetail")
        header_layout.addWidget(self.briefing_status_label)
        layout.addLayout(header_layout)

        # Next red-event line (countdown context, not a news list)
        self.briefing_next_event_label = QLabel("")
        self.briefing_next_event_label.setObjectName("CardDetail")
        self.briefing_next_event_label.setWordWrap(True)
        layout.addWidget(self.briefing_next_event_label)

        # Briefing body — streamed plain text, markdown at the end
        self.briefing_text = QTextEdit()
        self.briefing_text.setObjectName("ReadonlyText")
        self.briefing_text.setReadOnly(True)
        self.briefing_text.setMinimumHeight(200)
        layout.addWidget(self.briefing_text, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.briefing_button = action_button(
            "Tạo bản tin",
            primary=True,
            color="info",
            icon="bot",
            icon_role="selection_text",
            icon_disabled_role="selection_text",
        )
        self.briefing_button.setToolTip(
            "AI tổng hợp DXY, VIX, lợi suất trái phiếu Mỹ và sự kiện ảnh hưởng lớn thành kịch bản phiên"
        )
        self.briefing_button.clicked.connect(lambda: self._start_briefing(force=True))
        btn_layout.addWidget(self.briefing_button)

        news_btn = action_button(
            "Xem tin tức đầy đủ",
            primary=False,
            icon="external-link",
        )
        news_btn.setToolTip("Mở màn hình Tin tức & Sự kiện")
        news_btn.clicked.connect(self._open_news_screen)
        btn_layout.addWidget(news_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._show_briefing_empty(_BRIEFING_IDLE_HINT)
        # Auto-generate on first paint (guarded: chỉ khi AI đã cấu hình).
        QTimer.singleShot(2000, self._maybe_auto_briefing)
        return panel

    def _open_news_screen(self) -> None:
        if self.navigate:
            self.navigate("news")

    def _active_ai_config(self):
        settings = self.settings_service.load()
        active = settings.ai.active_provider()
        if not active or not (active.api_key or active.api_key_ref):
            return None
        from services.ai_service import AIProviderConfig

        return AIProviderConfig(
            provider=active.provider,
            model=active.model,
            api_key=active.api_key,
            base_url=active.base_url,
        )

    def _maybe_auto_briefing(self) -> None:
        """Tự tạo bản tin một lần mỗi phiên khi AI đã được cấu hình."""
        if self._briefing_text:
            return
        if self._briefing_worker is not None:
            return
        if self._active_ai_config() is None:
            return
        self._start_briefing()

    def _start_briefing(self, *, force: bool = False) -> None:
        if self._briefing_worker is not None:
            try:
                if self._briefing_worker.isRunning():
                    return
            except RuntimeError:
                pass
            self._briefing_worker = None

        if not force and self._briefing_text:
            return

        config = self._active_ai_config()
        if config is None:
            self._show_briefing_empty(
                "Chưa cấu hình AI. Vào Cài đặt để chọn nhà cung cấp và nhập API key.",
                tone="danger",
            )
            return

        self.briefing_button.setEnabled(False)
        self.briefing_button.setText("Đang soạn...")
        QApplication.processEvents()

        self.briefing_text.clear()
        self.briefing_text.setPlainText("Đang chờ AI phản hồi...\n\n")
        self.briefing_status_label.setText("Đang chuẩn bị dữ liệu...")

        worker = BriefingWorker(
            config,
            market_values=self._market_values,
            tz=_display_timezone(self.settings_service),
        )
        self._briefing_worker = worker
        worker.status.connect(self._on_briefing_status)
        worker.events_ready.connect(self._on_briefing_events)
        worker.chunk_ready.connect(self._on_briefing_chunk)
        worker.finished.connect(self._on_briefing_finished)
        worker.error.connect(self._on_briefing_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()

    def _on_briefing_status(self, message: str) -> None:
        self.briefing_status_label.setText(message)

    def _on_briefing_events(self, events: list) -> None:
        tz = _display_timezone(self.settings_service)
        now_utc = datetime.now(timezone.utc)
        parts: list[str] = []
        for ev in events[:3]:
            dt = ev.get("display_time")
            if not isinstance(dt, datetime):
                continue
            local_dt = (
                dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone(tz)
            )
            when = local_dt.strftime("%d/%m %H:%M")
            hours = (dt - now_utc).total_seconds() / 3600
            countdown = f" (còn ~{hours:.0f}h)" if hours >= 1 else " (sắp diễn ra)"
            name = f"{str(ev.get('currency', ''))} {str(ev.get('event', ''))}".strip()
            parts.append(f"{name} — {when}{countdown}")
        if parts:
            self.briefing_next_event_label.setText(
                "Sự kiện ảnh hưởng lớn sắp tới: " + " · ".join(parts)
            )
        else:
            self.briefing_next_event_label.setText(
                "Không có sự kiện ảnh hưởng lớn nào trong 72 giờ tới."
            )

    def _on_briefing_chunk(self, chunk: str) -> None:
        self.briefing_text.insertPlainText(chunk)
        scrollbar = self.briefing_text.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    def _on_briefing_finished(self, result: dict) -> None:
        self._briefing_text = str(result.get("text", ""))
        self._briefing_cache_key = str(result.get("cache_key", ""))
        tz = _display_timezone(self.settings_service)
        now_local = datetime.now(tz)
        self.briefing_date_label.setText(f"({now_local.strftime('%d/%m/%Y')})")
        self.briefing_text.setMarkdown(self._briefing_text)
        self.briefing_status_label.setText(
            f"Đã tạo lúc {now_local.strftime('%H:%M')} — tổng hợp từ chỉ số thị trường & lịch kinh tế"
        )
        self._on_briefing_events(result.get("events", []))
        self._reset_briefing_button()
        self._briefing_worker = None

    def _on_briefing_error(self, message: str) -> None:
        self._show_briefing_empty(f"Lỗi khi soạn bản tin: {message}", tone="danger")
        self.briefing_status_label.setText("")
        self._reset_briefing_button()
        self._briefing_worker = None

    def _reset_briefing_button(self) -> None:
        self.briefing_button.setText("Tạo lại bản tin")
        self.briefing_button.setEnabled(True)

    def _show_briefing_empty(self, message: str, tone: str = "muted") -> None:
        icon = "alert-triangle" if tone == "danger" else "bot"
        icon_role = "danger" if tone == "danger" else "text"
        set_rich_html(
            self.briefing_text,
            empty_state_html(message, tone=tone, icon=icon, icon_role=icon_role),
        )

    def _refresh_market_overview(self) -> None:
        """Fetch market overview data using MarketWorker to avoid freezing UI."""
        if hasattr(self, 'market_worker') and self.market_worker is not None:
            try:
                if self.market_worker.isRunning():
                    return
            except RuntimeError:
                pass
            self.market_worker = None
        self.market_worker = MarketWorker()
        self.market_worker.finished.connect(self._on_market_data_ready)
        self.market_worker.finished.connect(self.market_worker.deleteLater)
        self.market_worker.start()

    def _on_market_data_ready(self, data: dict) -> None:
        if "DXY" in data:
            self._format_market_label("DXY", data["DXY"][0], data["DXY"][1], self.dxy_label)
        else:
            self.dxy_label.setText("DXY: Không có dữ liệu")
            
        if "VIX" in data:
            self._format_market_label("VIX", data["VIX"][0], data["VIX"][1], self.vix_label)
        else:
            self.vix_label.setText("VIX: Không có dữ liệu")
            
        if "US10Y" in data:
            self._format_market_label("US10Y", data["US10Y"][0], data["US10Y"][1], self.us10y_label)
        else:
            self.us10y_label.setText("US10Y: Không có dữ liệu")

        if "US2Y" in data:
            self._format_market_label("US2Y", data["US2Y"][0], data["US2Y"][1], self.us2y_label)
        else:
            self.us2y_label.setText("US2Y: Không có dữ liệu")

        self._market_values = {}
        if "DXY" in data:
            self._market_values["DXY"] = (data["DXY"][0], data["DXY"][1])
        if "VIX" in data:
            self._market_values["VIX"] = (data["VIX"][0], data["VIX"][1])
        if "US10Y" in data:
            self._market_values["US10Y"] = (data["US10Y"][0], data["US10Y"][1])
        if "US2Y" in data:
            self._market_values["US2Y"] = (data["US2Y"][0], data["US2Y"][1])

    def _format_market_label(self, tag: str, close: float, change_pct: float, label: QLabel) -> None:
        self._light = self._is_light_theme()
        arrow = "↑" if change_pct > 0 else "↓" if change_pct < 0 else ""
        abs_change = abs(change_pct)
        if tag == "VIX":
            if close > 25:
                status, tone = "Rủi ro cao", "danger"
            elif close >= 20:
                status, tone = "Cảnh báo", "warning"
            else:
                status, tone = "Bình thường", "positive"
            label.setText(f"VIX: {close:.1f} — {status}")
        elif tag == "DXY":
            tone = "positive" if change_pct > 0 else "danger" if change_pct < 0 else "neutral"
            label.setText(f"DXY: {close:.2f} {arrow} {abs_change:.1f}%")
        else:  # US10Y / US2Y: lợi suất GIẢM → tốt (xanh), TĂNG → xấu (đỏ)
            tone = "danger" if change_pct > 0 else "positive" if change_pct < 0 else "neutral"
            label.setText(f"{tag}: {close:.2f}% {arrow}")
        set_dynamic_property(label, "metricTone", tone)

    def _show_market_help(self) -> None:
        from PyQt6.QtWidgets import QDialog

        self._light = self._is_light_theme()
        dlg = QDialog(self)
        dlg.setObjectName("MarketHelpDialog")
        dlg.setWindowTitle("Ý nghĩa các chỉ số thị trường")
        dlg.setMinimumSize(900, 640)
        dlg.resize(960, 680)

        root_layout = QVBoxLayout(dlg)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(14)

        palette = current_palette(self.settings_service)
        _title_color = palette.text
        title = QLabel(
            compile_rich_html(
                f'<b style="{QSS_TITLE}color:{_title_color};">'
                "Hướng dẫn đọc chỉ số thị trường</b>"
            )
        )
        root_layout.addWidget(title)

        # Current market values line (colored like dashboard)
        neutral = palette.text
        green = palette.success
        red = palette.danger
        yellow = palette.warning

        mv = getattr(self, "_market_values", None) or {}
        spans = []
        for tag in ("DXY", "VIX", "US10Y", "US2Y"):
            pair = mv.get(tag)
            if pair:
                close, change_pct = pair
                if tag == "DXY":
                    arrow = "↑" if change_pct > 0 else "↓" if change_pct < 0 else ""
                    color = green if change_pct > 0 else red if change_pct < 0 else neutral
                    spans.append(f"<span style='color:{color};'>{tag}: {close:.2f} ({arrow} {abs(change_pct):.1f}%)</span>")
                elif tag == "VIX":
                    if close > 25:
                        color = red
                    elif close >= 20:
                        color = yellow
                    else:
                        color = green
                    spans.append(f"<span style='color:{color};'>VIX: {close:.1f}</span>")
                else:
                    arrow = "↑" if change_pct > 0 else "↓" if change_pct < 0 else ""
                    color = red if change_pct > 0 else green if change_pct < 0 else neutral
                    spans.append(f"<span style='color:{color};'>{tag}: {close:.2f}% {arrow}</span>")
            else:
                spans.append(f"<span style='color:{neutral};'>{tag}: —</span>")
        vals_html = "  |  ".join(spans)
        vals_label = QLabel(compile_rich_html(vals_html))
        vals_label.setObjectName("CardValue")
        vals_label.setWordWrap(True)
        vals_label.setTextFormat(Qt.TextFormat.RichText)
        root_layout.addWidget(vals_label)

        # AI analysis area
        ai_response = QTextEdit()
        ai_response.setObjectName("ReadonlyText")
        ai_response.setReadOnly(True)
        ai_response.setMinimumHeight(150)
        ai_response.setPlaceholderText("Bấm \"Phân tích AI\" để AI đánh giá ảnh hưởng của các chỉ số hiện tại đến thị trường...")
        root_layout.addWidget(ai_response, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        ai_btn = action_button(
            "Phân tích AI",
            primary=True,
            icon="bot",
            icon_role="selection_text",
        )
        ai_btn.setObjectName("DialogAiButton")
        btn_layout.addWidget(ai_btn)
        btn_layout.addStretch()

        close_btn = action_button(
            "Đóng",
            primary=False,
            color="danger",
            icon="x",
            icon_role="danger",
        )
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)
        root_layout.addLayout(btn_layout)

        def request_analysis():
            mv = getattr(self, "_market_values", None) or {}
            snapshot = str(mv)
            if snapshot and snapshot == self._ai_last_snapshot and self._ai_cached_response:
                ai_response.setMarkdown(self._ai_cached_response)
                return

            settings = self.settings_service.load()
            active = settings.ai.active_provider()
            if not active or not (active.api_key or active.api_key_ref):
                set_rich_html(
                    ai_response,
                    empty_state_html(
                        "⚠️ Chưa cấu hình AI. Vào Cài đặt để chọn nhà cung cấp "
                        "và nhập API key.",
                        tone="danger",
                    ),
                )
                return

            from services.ai_service import AIService, AIProviderConfig
            ai_config = AIProviderConfig(
                provider=active.provider,
                model=active.model,
                api_key=active.api_key,
                base_url=active.base_url,
            )
            ai = AIService(ai_config)

            def _fmt_val(tag):
                pair = mv.get(tag)
                if pair:
                    close, change_pct = pair
                    arrow = "↑" if change_pct > 0 else "↓" if change_pct < 0 else "—"
                    if tag in ("US10Y", "US2Y"):
                        return f"{close:.2f}% (thay đổi: {arrow} {abs(change_pct):.1f}%)"
                    elif tag == "VIX":
                        return f"{close:.1f} (thay đổi: {arrow} {abs(change_pct):.1f}%)"
                    else:
                        return f"{close:.2f} (thay đổi: {arrow} {abs(change_pct):.1f}%)"
                return "—"

            prompt = f"""Bạn là chuyên gia phân tích thị trường tài chính. Dựa trên số liệu hiện tại:
- DXY: {_fmt_val("DXY")}
- VIX: {_fmt_val("VIX")}
- US10Y: {_fmt_val("US10Y")}
- US2Y: {_fmt_val("US2Y")}

Hãy phân tích CHI TIẾT từng chỉ số và ĐÁNH GIÁ MỨC ĐỘ ẢNH HƯỞNG đến các đồng tiền/cặp tiền sau:
- EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, NZD/USD
- Vàng (XAU/USD), Bạc (XAG/USD), Bitcoin

Trả lời bằng tiếng Việt, định dạng markdown. Cấu trúc BẮT BUỘC:

## Phân tích từng chỉ số

### DXY — Chỉ số sức mạnh USD ({_fmt_val("DXY")})
- **Diễn biến**: (DXY hiện tại đang ở mức cao/thấp/trung bình? Xu hướng ngắn hạn?)
- **Nguyên nhân**: (Yếu tố nào đang chi phối — chính sách FED, dữ liệu kinh tế Mỹ, dòng vốn, rủi ro toàn cầu?)
- **Ảnh hưởng đến Forex**: (USD mạnh/yếu ảnh hưởng cụ thể đến EUR, GBP, JPY, AUD, CAD, NZD ra sao?)
- **Ảnh hưởng đến Vàng & Crypto**: (DXY tác động đến XAU, XAG, BTC như thế nào?)

### VIX — Chỉ số sợ hãi ({_fmt_val("VIX")})
- **Diễn biến**: (VIX đang ở vùng thấp/trung bình/cao? Thị trường đang bình tĩnh hay lo lắng?)
- **Nguyên nhân**: (Sự kiện nào gây biến động — địa chính trị, kinh tế, chính sách tiền tệ?)
- **Ảnh hưởng**: (VIX cao → dòng tiền chạy vào tài sản trú ẩn nào? Ngược lại VIX thấp → risk-on không?)
- **Chiến lược**: (Trader nên làm gì với mức VIX hiện tại?)

### US10Y — Lợi suất trái phiếu Mỹ 10 năm ({_fmt_val("US10Y")})
- **Diễn biến**: (Lợi suất đang ở mức nào so với lịch sử gần đây? Xu hướng tăng/giảm?)
- **Nguyên nhân**: (Kỳ vọng lạm phát, tăng trưởng, nợ công, phát hành trái phiếu?)
- **Ảnh hưởng**: (US10Y thay đổi tác động đến USD, chứng khoán, Vàng như thế nào?)
- **So sánh với US2Y**: (Đường cong lợi suất đang steepening hay flattening? Ý nghĩa?)

### US2Y — Lợi suất trái phiếu Mỹ 2 năm ({_fmt_val("US2Y")})
- **Diễn biến**: (US2Y phản ánh kỳ vọng FED ra sao? Thị trường đang định giá mấy lần cắt/tăng lãi suất?)
- **Nguyên nhân**: (Phát biểu của FED, dữ liệu việc làm, CPI, PCE ảnh hưởng thế nào?)
- **Ảnh hưởng**: (US2Y thay đổi → tác động trực tiếp đến USD/JPY, USD/CAD, Vàng?)
- **Chênh lệch 2Y-10Y**: (Spread hiện tại bao nhiêu? Dương hay âm? Nguy cơ suy thoái?)

## Đánh giá ảnh hưởng đến từng cặp tiền/tài sản
(Với mỗi cặp, ghi rõ mức độ: Tích cực / Tiêu cực / Trung tính — kèm 1-2 câu lý do)
- EUR/USD
- GBP/USD
- USD/JPY
- AUD/USD
- USD/CAD
- NZD/USD
- Vàng (XAU/USD)
- Bạc (XAG/USD)
- Bitcoin

## Tổng quan & Khuyến nghị
- **Xu hướng chung của USD**: (tăng/giảm/đi ngang — lý do chính)
- **Rủi ro chính cần theo dõi**: (1-2 rủi ro)
- **Khuyến nghị cho trader**: (2-3 câu cụ thể, có thể hành động được)

QUAN TRỌNG:
- Phân tích ĐẦY ĐỦ cả 4 chỉ số, mỗi chỉ số một mục riêng
- KHÔNG viết chung chung. Phải dựa TRÊN SỐ LIỆU THỰC TẾ được cung cấp
- KHÔNG gộp US2Y với US10Y — đây là 2 chỉ số KHÁC NHAU"""

            ai_btn.setEnabled(False)
            ai_btn.setText("Đang phân tích...")
            ai_response.clear()
            ai_response.insertPlainText("Đang chờ AI phản hồi...\n\n")

            # Stop any running worker
            _prev = getattr(self, '_market_help_worker', None)
            if _prev is not None and _prev.isRunning():
                _prev.stop_flag = True
                _prev.quit()
                _prev.wait(3000)

            class MarketHelpWorker(QThread):
                finished = pyqtSignal(str)
                error = pyqtSignal(str)
                chunk_ready = pyqtSignal(str)

                def __init__(self, ai_service, prompt_text, max_tokens):
                    super().__init__()
                    self.ai_service = ai_service
                    self.prompt_text = prompt_text
                    self.max_tokens = max_tokens
                    self.stop_flag = False

                def run(self):
                    try:
                        full_text = ""
                        for chunk in self.ai_service.analyze_stream(self.prompt_text, max_tokens=self.max_tokens):
                            if self.stop_flag:
                                return
                            full_text += chunk
                            self.chunk_ready.emit(chunk)
                        if not self.stop_flag:
                            self.finished.emit(full_text)
                    except Exception as exc:
                        if not self.stop_flag:
                            self.error.emit(str(exc))

            worker = MarketHelpWorker(ai, prompt, max_tokens=2500)
            self._market_help_worker = worker

            def on_chunk(text):
                ai_response.insertPlainText(text)
                scrollbar = ai_response.verticalScrollBar()
                if scrollbar:
                    scrollbar.setValue(scrollbar.maximum())

            def on_finished(text):
                ai_response.setMarkdown(text)
                ai_btn.setText("Phân tích AI")
                ai_btn.setEnabled(True)
                self._ai_last_snapshot = snapshot
                self._ai_cached_response = text
                self._market_help_worker = None

            def on_error(err_msg):
                set_rich_html(
                    ai_response,
                    empty_state_html(
                        f"Lỗi phân tích: {err_msg}",
                        tone="danger",
                    ),
                )
                ai_btn.setText("Phân tích AI")
                ai_btn.setEnabled(True)
                self._market_help_worker = None

            worker.chunk_ready.connect(on_chunk)
            worker.finished.connect(on_finished)
            worker.error.connect(on_error)
            worker.finished.connect(worker.deleteLater)
            worker.error.connect(worker.deleteLater)
            worker.start()

        ai_btn.clicked.connect(request_analysis)

        dlg.exec()

        # Cleanup worker if still running after dialog closes
        _w = getattr(self, '_market_help_worker', None)
        if _w is not None and _w.isRunning():
            _w.stop_flag = True
            _w.quit()
            _w.wait(3000)
            self._market_help_worker = None

    def set_analysis_result(self, result: dict[str, object]) -> None:
        self.refresh_mt5_status()
        self.refresh_ai_status()

    def refresh_status(self) -> None:
        self.refresh_mt5_status()
        self.refresh_ai_status()

    def refresh_mt5_status(self) -> None:
        self.mt5.connect()
        status = self.mt5.connection_status()
        self._apply_connection_status(status)

    def refresh_ai_status(self) -> None:
        settings = self.settings_service.load()
        active = settings.ai.active_provider()
        has_key = bool(active and (active.api_key or active.api_key_ref))
        if active and active.provider and active.model and has_key:
            detail = active.model
            self._set_status_card("AI", "Trí tuệ nhân tạo", detail, "ok")
        else:
            self._set_status_card("AI", "Trí tuệ nhân tạo", "Chọn nhà cung cấp, mô hình và nhập khóa API", "warning")

        # Update data source card
        source_name = "MetaTrader 5"
        self._set_status_card("Nguồn dữ liệu", "Nguồn dữ liệu", f"Đang dùng {source_name}", "ok")

    def _apply_connection_status(self, status: ConnectionStatus) -> None:
        provider = status.provider_name or "Dữ liệu"
        if status.initialized and status.connected:
            self._set_status_card("Kết nối", "Kết nối dữ liệu", f"{provider}: {status.message}", "ok")
        else:
            detail = status.message
            if status.error_code is not None:
                detail = f"{detail} ({status.error_code})"
            self._set_status_card("Kết nối", "Kết nối dữ liệu", detail, "danger")

        if status.logged_in:
            account = f"{status.login} - {status.server}" if status.login else str(status.server)
            self._set_status_card("Broker", "Tài khoản giao dịch", account, "ok")
        else:
            self._set_status_card("Broker", "Tài khoản giao dịch", f"Cần đăng nhập tài khoản trên {provider}", "warning")

        ready = status.initialized and status.connected and status.logged_in
        self.mt5_warning.setVisible(not ready)
        if ready:
            self.mt5_warning_title.setText(f"{provider} đã sẵn sàng")
            self.mt5_warning_detail.setText(f"Đã kết nối và đăng nhập thành công.")
        else:
            self.mt5_warning_title.setText(f"{provider} chưa sẵn sàng")
            self.mt5_warning_detail.setText(status.message or "Hãy kiểm tra kết nối và thử lại.")

    def _set_status_card(self, title: str, value: str, detail: str, state: str) -> None:
        card_data = self.status_cards.get(title)
        if not card_data:
            return
        frame, value_label, detail_label = card_data
        value_label.setText(value)
        detail_label.setText(detail)
        set_dynamic_property(frame, "state", state)
