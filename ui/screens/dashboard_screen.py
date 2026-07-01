from __future__ import annotations

from config.constants import SUPPORTED_SYMBOLS
from datetime import datetime, timedelta, timezone
from PyQt6.QtCore import Qt, QTimer, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from ui.screens.shared import action_button
from services.data_provider import ConnectionStatus
from services.market_data_service import fetch_market_overview
from services.mt5_service import MT5ConnectionStatus, MT5Service
from services.forex_factory_client import ForexFactoryClient
from services.settings_service import SettingsService

class MarketWorker(QThread):
    finished = pyqtSignal(dict)

    def run(self):
        self.finished.emit(fetch_market_overview())

class NewsWorker(QThread):
    """Fetch news headlines + economic calendar for the given date window."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, currencies=None, from_date=None, to_date=None):
        super().__init__()
        self.currencies = currencies or []
        self.from_date = from_date
        self.to_date = to_date

    def run(self):
        try:
            from services.news_service import NewsService
            svc = NewsService()
            result = svc.fetch_news_window(
                from_date=self.from_date,
                to_date=self.to_date,
                currencies=self.currencies,
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ActualLookupWorker(QThread):
    result_ready = pyqtSignal(str)

    def __init__(self, currency: str, event_name: str, ev_time_str: str, news_service, forecast: str = "", previous: str = ""):
        super().__init__()
        self.currency = currency
        self.event_name = event_name
        self.ev_time_str = ev_time_str
        self.news_service = news_service
        self.forecast = forecast
        self.previous = previous

    def run(self):
        result = self.news_service.lookup_actual_single(
            self.currency,
            self.event_name,
            self.ev_time_str,
            self.forecast,
            self.previous,
        )
        self.result_ready.emit(result)


class DashboardScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.data_provider = app.data_provider if app else MT5Service()
        self.settings_service = app.settings_service if app else SettingsService()
        self.status_cards: dict[str, tuple[QFrame, QLabel, QLabel]] = {}
        self._light = self._is_light_theme()
        self._news_tab = "this_week"
        self._news_data: dict = {}
        self.setObjectName("DashboardScreen")
        self._build_ui()
        self.refresh_status()

    def refresh_theme_styles(self) -> None:
        self._light = self._is_light_theme()
        self._refresh_market_overview()
        self.refresh_news_section()

    def _is_light_theme(self) -> bool:
        try:
            settings = self.settings_service.load()
            return settings.display.theme == "light"
        except Exception:
            return False

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(18)
        root.addLayout(self._build_header())
        root.addLayout(self._build_status_grid())
        self.mt5_warning = self._build_mt5_warning()
        root.addWidget(self.mt5_warning)
        self.market_overview = self._build_market_overview()
        root.addWidget(self.market_overview)
        self.news_section = self._build_news_section()
        root.addWidget(self.news_section)
        QTimer.singleShot(3000, self._refresh_market_overview)

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)
        title_box = QVBoxLayout()
        title = QLabel("Bảng điều khiển")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Kiểm tra trạng thái hệ thống và bắt đầu phân tích thị trường.")
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        coverage = QLabel(f"{len(SUPPORTED_SYMBOLS)} mã")
        coverage.setObjectName("HeaderBadge")
        coverage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(title_box, 1)
        layout.addWidget(coverage)
        return layout

    def _build_status_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(8)
        items = [
            ("Kết nối", "Đang kiểm tra", "Đang đọc kết nối dữ liệu", "warning"),
            ("Broker", "Đang kiểm tra", "Đang đọc tài khoản", "warning"),
            ("AI", "Đang kiểm tra", "Đang đọc cấu hình AI", "warning"),
            ("Nguồn dữ liệu", "Đang kiểm tra", "Đang xác định nguồn dữ liệu", "warning"),
        ]
        for index, item in enumerate(items):
            card = self._status_card(*item)
            grid.addWidget(card, 0, index)
            grid.setColumnStretch(index, 1)
        return grid

    def _status_card(self, title: str, value: str, detail: str, state: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("StatusCard")
        frame.setProperty("state", state)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        value_label = None
        detail_label = None
        for text, name in [(title, "CardTitle"), (value, "CardValue"), (detail, "CardDetail")]:
            label = QLabel(text)
            label.setObjectName(name)
            label.setWordWrap(True)
            layout.addWidget(label)
            if name == "CardValue":
                value_label = label
            elif name == "CardDetail":
                detail_label = label
        if value_label and detail_label:
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
        retry = action_button("🔄 Thử lại", primary=True, color="info")
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

        _badge_color = "#374151" if self._light else "#e5e7eb"
        self.dxy_label = QLabel("DXY: Đang tải...")
        self.dxy_label.setObjectName("MarketBadge")
        self.dxy_label.setStyleSheet(f"font-weight:700;font-size:14px;color:{_badge_color};")

        self.vix_label = QLabel("VIX: Đang tải...")
        self.vix_label.setObjectName("MarketBadge")
        self.vix_label.setStyleSheet(f"font-weight:700;font-size:14px;color:{_badge_color};")

        self.us10y_label = QLabel("US10Y: Đang tải...")
        self.us10y_label.setObjectName("MarketBadge")
        self.us10y_label.setStyleSheet(f"font-weight:700;font-size:14px;color:{_badge_color};")

        self.us2y_label = QLabel("US2Y: Đang tải...")
        self.us2y_label.setObjectName("MarketBadge")
        self.us2y_label.setStyleSheet(f"font-weight:700;font-size:14px;color:{_badge_color};")

        layout.addWidget(self.dxy_label)
        layout.addWidget(self.vix_label)
        layout.addWidget(self.us10y_label)
        layout.addWidget(self.us2y_label)
        help_btn = action_button("❓ Giải thích chỉ số", primary=True, color="info")
        help_btn.setToolTip("Ý nghĩa các chỉ số")
        help_btn.clicked.connect(self._show_market_help)
        layout.addWidget(help_btn)
        layout.addStretch(1)
        return panel

    def _build_news_section(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header row
        header_layout = QHBoxLayout()
        title = QLabel("Tin tức & Sự kiện")
        title.setObjectName("PanelTitle")
        header_layout.addWidget(title)

        self.news_date_range = QLabel("")
        self.news_date_range.setObjectName("CardDetail")
        header_layout.addWidget(self.news_date_range)
        header_layout.addStretch()

        self.news_source_label = QLabel("")
        self.news_source_label.setObjectName("CardDetail")
        header_layout.addWidget(self.news_source_label)
        layout.addLayout(header_layout)

        # Tab bar
        tab_layout = QHBoxLayout()
        tab_layout.setSpacing(4)

        self.tab_buttons: dict[str, QPushButton] = {}
        tab_configs = [
            ("last_week", "📅 Tuần trước"),
            ("this_week", "📅 Tuần này"),
            ("next_week", "📅 Tuần sau"),
        ]
        for tab_key, tab_label in tab_configs:
            btn = QPushButton(tab_label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("newsTab", tab_key)
            btn.clicked.connect(lambda checked, k=tab_key: self._switch_news_tab(k))
            self.tab_buttons[tab_key] = btn
            tab_layout.addWidget(btn)

        self.news_scroll_btn = action_button("📍 Xem tin sắp tới", primary=True, color="info")
        self.news_scroll_btn.setToolTip("Chuyển sang tuần này và kéo tới tin sắp tới gần nhất")
        self.news_scroll_btn.clicked.connect(self._go_to_nearest)
        tab_layout.addWidget(self.news_scroll_btn)

        self.eval_today_btn = action_button("📊 Đánh giá hôm nay", primary=True, color="info")
        self.eval_today_btn.setToolTip("AI nhận định & đánh giá tin tức hôm nay")
        self.eval_today_btn.clicked.connect(lambda: self._show_ai_evaluation("today"))
        tab_layout.addWidget(self.eval_today_btn)

        self.eval_week_btn = action_button("📈 Đánh giá tuần này", primary=True, color="info")
        self.eval_week_btn.setToolTip("AI nhận định & đánh giá tin tức tuần này")
        self.eval_week_btn.clicked.connect(lambda: self._show_ai_evaluation("week"))
        tab_layout.addWidget(self.eval_week_btn)

        self.eval_next_week_btn = action_button("🔮 Đánh giá tuần tới", primary=True, color="info")
        self.eval_next_week_btn.setToolTip("AI nhận định & đánh giá tin tức tuần tới")
        self.eval_next_week_btn.clicked.connect(lambda: self._show_ai_evaluation("next_week"))
        tab_layout.addWidget(self.eval_next_week_btn)

        tab_layout.addStretch()

        self.news_refresh_button = action_button("🔄 Làm mới", primary=True, color="info")
        self.news_refresh_button.setToolTip("Tải lại chỉ số thị trường, tin tức & sự kiện (3 tuần)")
        self.news_refresh_button.clicked.connect(self.refresh_news_section)
        tab_layout.addWidget(self.news_refresh_button)

        layout.addLayout(tab_layout)

        # Table
        self.news_table = QTableWidget()
        self.news_table.setObjectName("EconTable")
        self.news_table.setColumnCount(8)
        self.news_table.setHorizontalHeaderLabels(["Thời gian", "Loại", "Nội dung", "Kỳ trước", "Dự báo", "Thực tế", "Nguồn", ""])
        self.news_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.news_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.news_table.setAlternatingRowColors(True)
        self.news_table.verticalHeader().setVisible(False)
        self.news_table.setShowGrid(False)
        self.news_table.setWordWrap(True)
        self.news_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.news_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        header = self.news_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.news_table.setColumnWidth(0, 185)
        self.news_table.setColumnWidth(1, 55)
        self.news_table.setColumnWidth(3, 85)
        self.news_table.setColumnWidth(4, 85)
        self.news_table.setColumnWidth(5, 85)
        self.news_table.setColumnWidth(6, 115)
        self.news_table.setColumnWidth(7, 50)

        layout.addWidget(self.news_table)

        # Initial tab style + trigger first load
        self._update_tab_styles()
        QTimer.singleShot(1500, self.refresh_news_section)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return panel

    def refresh_news_section(self) -> None:
        btn = getattr(self, "news_refresh_button", None)
        if btn is not None:
            btn.setEnabled(False)
            btn.setText("⏳ Đang tải...")
            QApplication.processEvents()

        self._refresh_market_overview()

        # Compute date range: last Monday 00:00 → next Sunday 23:59 (covers all 3 weeks)
        from zoneinfo import ZoneInfo
        try:
            try:
                settings = self.settings_service.load()
                tz_str = settings.display.timezone
            except Exception:
                tz_str = "Asia/Ho_Chi_Minh"
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Ho_Chi_Minh")

        now_local = datetime.now(tz)
        weekday = now_local.weekday()  # Monday=0
        this_monday = (now_local - timedelta(days=weekday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        from_date = (this_monday - timedelta(days=7)).astimezone(timezone.utc)
        to_date = (this_monday + timedelta(days=14)).astimezone(timezone.utc)

        self.news_worker = NewsWorker(currencies=[], from_date=from_date, to_date=to_date)
        self.news_worker.finished.connect(self._on_news_data_ready)
        self.news_worker.error.connect(lambda e: self._show_news_empty(f"Lỗi: {e}"))
        self.news_worker.finished.connect(lambda: self._reset_news_button(btn))
        self.news_worker.error.connect(lambda: self._reset_news_button(btn))
        self.news_worker.start()

    def _reset_news_button(self, btn):
        if btn is not None:
            btn.setText("🔄 Làm mới")
            btn.setEnabled(True)

    def _on_news_data_ready(self, result: dict) -> None:
        self._light = self._is_light_theme()
        self._news_data = result

        from zoneinfo import ZoneInfo
        try:
            try:
                settings = self.settings_service.load()
                tz_str = settings.display.timezone
            except Exception:
                tz_str = "Asia/Ho_Chi_Minh"
            try:
                tz = ZoneInfo(tz_str)
            except Exception:
                tz = ZoneInfo("Asia/Ho_Chi_Minh")
        except Exception:
            tz = ZoneInfo("Asia/Ho_Chi_Minh")

        combined = result.get("combined", [])
        if not isinstance(combined, list):
            combined = []

        if not combined:
            self._show_news_empty("Chưa có dữ liệu tin tức & sự kiện. Kiểm tra kết nối mạng.")
            return

        # Update date range label
        try:
            fd = datetime.fromisoformat(str(result.get("from_date", "")))
            td = datetime.fromisoformat(str(result.get("to_date", "")))
            # Convert to user timezone for display
            fd_local = fd.astimezone(tz) if fd.tzinfo else fd.replace(tzinfo=timezone.utc).astimezone(tz)
            td_local = td.astimezone(tz) if td.tzinfo else td.replace(tzinfo=timezone.utc).astimezone(tz)
            self.news_date_range.setText(f"({fd_local.strftime('%d/%m')} — {td_local.strftime('%d/%m')})")
        except Exception:
            self.news_date_range.setText("")

        # Update sources label
        sources = result.get("sources", {})
        src_text = str(sources.get("headlines", [])).strip("[]").replace("'", "")
        cal_src = str(sources.get("calendar", ""))
        if cal_src and cal_src != "unavailable":
            src_text = (src_text + ", " + cal_src) if src_text else cal_src
        self.news_source_label.setText(f"Nguồn: {src_text}" if src_text else "")

        now_utc = datetime.now(timezone.utc)

        # Filter by active tab
        rows = self._filter_news_rows(combined)
        self._render_news_rows(rows, tz, now_utc, self._news_tab)

    def _filter_news_rows(self, combined: list) -> list:
        """Filter combined news items by the active week tab (Mon 00:00 – Sun 23:59)."""
        from zoneinfo import ZoneInfo

        try:
            try:
                settings = self.settings_service.load()
                tz_str = settings.display.timezone
            except Exception:
                tz_str = "Asia/Ho_Chi_Minh"
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Ho_Chi_Minh")

        now_local = datetime.now(tz)
        weekday = now_local.weekday()  # Monday=0
        this_monday = (now_local - timedelta(days=weekday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        if self._news_tab == "last_week":
            start_local = this_monday - timedelta(days=7)
            end_local = this_monday
        elif self._news_tab == "next_week":
            start_local = this_monday + timedelta(days=7)
            end_local = this_monday + timedelta(days=14)
        else:  # this_week
            start_local = this_monday
            end_local = this_monday + timedelta(days=7)

        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        filtered: list[dict] = []
        for r in combined:
            dt = r.get("display_time")
            if isinstance(dt, datetime) and start_utc <= dt < end_utc:
                filtered.append(r)
        return filtered

    def _switch_news_tab(self, tab_key: str) -> None:
        self._news_tab = tab_key
        self._update_tab_styles()
        if self._news_data:
            from zoneinfo import ZoneInfo
            try:
                try:
                    settings = self.settings_service.load()
                    tz_str = settings.display.timezone
                except Exception:
                    tz_str = "Asia/Ho_Chi_Minh"
                tz = ZoneInfo(tz_str)
            except Exception:
                tz = ZoneInfo("Asia/Ho_Chi_Minh")
            self._render_news_rows(
                self._filter_news_rows(self._news_data.get("combined", [])),
                tz,
                datetime.now(timezone.utc),
                self._news_tab,
            )

    def _update_tab_styles(self) -> None:
        # Lư Trung Hỏa theme color variables
        active_bg = "#D94625" if self._light else "#ea580c"
        active_hover = "#E0533C" if self._light else "#f97316"
        
        inactive_fg = "#4b5563" if self._light else "#9ca3af"
        inactive_border = "#d1d5db" if self._light else "#4b5563"
        inactive_hover_bg = "#fce8e5" if self._light else "#2c1910"
        inactive_hover_fg = "#D94625" if self._light else "#ea580c"
        inactive_hover_border = "#D94625" if self._light else "#ea580c"

        active_style = (
            f"QPushButton {{"
            f"  font-size:12px; font-weight:700; padding:6px 14px;"
            f"  background:{active_bg}; color:#ffffff; border:none; border-radius:6px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{active_hover};"
            f"}}"
        )
        inactive_style = (
            f"QPushButton {{"
            f"  font-size:12px; font-weight:500; padding:6px 14px;"
            f"  background:transparent;"
            f"  color:{inactive_fg};"
            f"  border:1px solid {inactive_border};"
            f"  border-radius:6px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{inactive_hover_bg};"
            f"  color:{inactive_hover_fg};"
            f"  border:1px solid {inactive_hover_border};"
            f"}}"
        )
        for key, btn in self.tab_buttons.items():
            if key == self._news_tab:
                btn.setStyleSheet(active_style)
                btn.setChecked(True)
            else:
                btn.setStyleSheet(inactive_style)
                btn.setChecked(False)

    def _render_news_rows(self, rows: list, tz, now_utc: datetime, tab_key: str = "this_week") -> None:
        self._light = self._is_light_theme()
        table = self.news_table
        table.setRowCount(0)

        if not rows:
            self._show_news_empty("Không có mục nào để hiển thị.")
            return

        impact_dots = {"high": "🔴", "medium": "🟡", "low": "⚪"}

        # --- Split into zones based on tab context ---
        past_rows: list[dict] = []
        nearest_row: dict | None = None
        future_rows: list[dict] = []

        for row in rows:
            dt = row.get("display_time")
            if not isinstance(dt, datetime):
                future_rows.append(row)
                continue
            if dt < now_utc:
                past_rows.append(row)
            elif tab_key == "next_week":
                future_rows.append(row)  # no "nearest" highlight for next week
            elif nearest_row is None:
                nearest_row = row
            else:
                future_rows.append(row)

        # --- Build display rows with zone headers ---
        display_rows: list[dict] = []

        if past_rows:
            display_rows.append({"is_zone_header": True, "zone": "past"})
            display_rows.extend(past_rows)

        if nearest_row is not None:
            display_rows.append({"is_zone_header": True, "zone": "nearest"})
            display_rows.append(nearest_row)

        if future_rows:
            display_rows.append({"is_zone_header": True, "zone": "future"})
            display_rows.extend(future_rows)

        # --- Render ---
        table.setRowCount(len(display_rows))
        for i, row in enumerate(display_rows):
            if row.get("is_zone_header"):
                self._render_zone_header(table, i, str(row.get("zone", "")))
                continue

            row_type = str(row.get("type", ""))
            dt = row.get("display_time")
            zone = self._row_zone(row, past_rows, nearest_row)
            impact = str(row.get("impact", "")).lower()

            # Determine colors and fonts based on zone and impact
            bg_color = None
            fg_color = None
            is_bold = False

            if zone == "past":
                fg_color = QColor("#6b7280" if self._light else "#8b949e")
                bg_color = None  # Let it inherit table's default alternating colors
                is_bold = False
            elif zone == "nearest":
                fg_color = QColor("#137333" if self._light else "#10b981")
                bg_color = QColor("#eafaf1" if self._light else "#082f25")
                is_bold = True
            else:  # future zone
                is_bold = False
                if row_type == "event":
                    if impact == "high":
                        fg_color = QColor("#b91c1c" if self._light else "#f87171")
                        bg_color = QColor("#fdf2f2" if self._light else "#2a0d11")
                    elif impact == "medium":
                        fg_color = QColor("#b45309" if self._light else "#fbbf24")
                        bg_color = QColor("#fffbeb" if self._light else "#251608")
                    else:
                        fg_color = None
                        bg_color = None
                else:  # headline
                    fg_color = None
                    bg_color = None

            # Helper function to style an item
            def style_item(item: QTableWidgetItem):
                if fg_color:
                    item.setForeground(fg_color)
                if bg_color:
                    item.setBackground(bg_color)
                if is_bold:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)

            # Column 0: Time
            if isinstance(dt, datetime):
                local_dt = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone(tz)
                w_day = local_dt.weekday()
                w_name = {
                    0: "Thứ 2",
                    1: "Thứ 3",
                    2: "Thứ 4",
                    3: "Thứ 5",
                    4: "Thứ 6",
                    5: "Thứ 7",
                    6: "Chủ Nhật"
                }.get(w_day, "")
                time_text = f"{w_name} ngày {local_dt.strftime('%d/%m %H:%M')}"
            else:
                time_text = "—"

            time_item = QTableWidgetItem(time_text)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            style_item(time_item)
            table.setItem(i, 0, time_item)

            # Column 1: Type icon
            if row_type == "headline":
                type_icon = "📰"
                type_tooltip = "Tin tức"
            else:
                type_icon = impact_dots.get(impact, "⚪")
                type_tooltip = f"Sự kiện ({impact})"

            type_item = QTableWidgetItem(type_icon)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            type_item.setToolTip(type_tooltip)
            style_item(type_item)
            table.setItem(i, 1, type_item)

            # Column 2: Content
            title = str(row.get("title", ""))
            currency = str(row.get("currency", ""))

            if row_type == "headline":
                content_text = title
            else:
                content_text = f"{currency}: {title}"

            content_item = QTableWidgetItem(content_text)
            style_item(content_item)
            table.setItem(i, 2, content_item)

            # Column 3: Previous
            if row_type == "event":
                previous = str(row.get("previous", ""))
            else:
                previous = "—"
            prev_item = QTableWidgetItem(previous if previous else "—")
            prev_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            style_item(prev_item)
            table.setItem(i, 3, prev_item)

            # Column 4: Forecast
            if row_type == "event":
                forecast = str(row.get("forecast", ""))
            else:
                forecast = "—"
            fore_item = QTableWidgetItem(forecast if forecast else "—")
            fore_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            style_item(fore_item)
            table.setItem(i, 4, fore_item)

            # Column 5: Actual (bold, colored if deviates from forecast)
            if row_type == "event":
                actual = str(row.get("actual", ""))
            else:
                actual = "—"
            actual_item = QTableWidgetItem(actual if actual else "—")
            actual_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if actual and actual not in ("", "—"):
                f = actual_item.font()
                f.setBold(True)
                actual_item.setFont(f)
                try:
                    av = float(actual.replace("%", "").replace(",", ""))
                    fv = float(forecast.replace("%", "").replace(",", ""))
                    if av > fv:
                        actual_item.setForeground(QColor("#137333" if self._light else "#10b981"))
                    elif av < fv:
                        actual_item.setForeground(QColor("#b91c1c" if self._light else "#f87171"))
                except (ValueError, TypeError):
                    pass
            style_item(actual_item)
            table.setItem(i, 5, actual_item)

            # Column 6: Source
            source_text = str(row.get("source", ""))
            short_source = source_text.split(" ")[0][:12] if source_text else "—"
            src_item = QTableWidgetItem(short_source)
            src_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            style_item(src_item)
            table.setItem(i, 6, src_item)

            # Column 7: Action button / link
            action_item = QTableWidgetItem()
            style_item(action_item)
            table.setItem(i, 7, action_item)

            if row_type == "event":
                link_color, link_hover = self._zone_link_colors(zone)
                if zone == "nearest":
                    link_color = "#137333" if self._light else "#10b981"
                    link_hover = "#065f46" if self._light else "#34d399"
                elif impact == "high" and zone == "future":
                    link_color = "#b91c1c" if self._light else "#f87171"
                    link_hover = "#7f1d1d" if self._light else "#fca5a5"
                elif impact == "medium" and zone == "future":
                    link_color = "#b45309" if self._light else "#fbbf24"
                    link_hover = "#78350f" if self._light else "#fcd34d"

                detail_btn = QPushButton("Xem")
                detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                detail_btn.setStyleSheet(
                    f"QPushButton {{"
                    f"  font-size:11px; padding:2px 0; margin:0;"
                    f"  background:transparent; color:{link_color}; border:none;"
                    f"  text-decoration:underline;"
                    f"}}"
                    f"QPushButton:hover {{ color:{link_hover}; }}"
                )
                detail_btn.clicked.connect(lambda checked, r=row: self._show_news_event_detail(r, tz))
                table.setCellWidget(i, 7, detail_btn)
            else:
                url = str(row.get("url", ""))
                title = str(row.get("title", ""))
                if url or title:
                    link_color, link_hover = self._zone_link_colors(zone)
                    if zone == "nearest":
                        link_color = "#137333" if self._light else "#10b981"
                        link_hover = "#065f46" if self._light else "#34d399"
                    
                    detail_btn = QPushButton("🔗")
                    detail_btn.setToolTip("Xem tóm tắt & chi tiết tin tức")
                    detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    detail_btn.setStyleSheet(
                        f"QPushButton {{"
                        f"  font-size:14px; padding:2px 0; margin:0;"
                        f"  background:transparent; color:{link_color}; border:none;"
                        f"}}"
                        f"QPushButton:hover {{ color:{link_hover}; }}"
                    )
                    detail_btn.clicked.connect(lambda checked, r=row: self._show_headline_detail(r, tz))
                    table.setCellWidget(i, 7, detail_btn)

            table.setRowHeight(i, 32)

        # Auto-scroll to nearest upcoming after render
        QTimer.singleShot(50, self._scroll_to_nearest)

    def _go_to_nearest(self) -> None:
        """Switch to this week's tab and scroll to the nearest upcoming item."""
        if self._news_tab != "this_week":
            self._switch_news_tab("this_week")
        else:
            self._scroll_to_nearest()

    def _scroll_to_nearest(self) -> None:
        """Scroll the news table so the nearest upcoming item is at the top."""
        table = self.news_table
        for r in range(table.rowCount()):
            item = table.item(r, 0)
            if item and "SẮP TỚI GẦN NHẤT" in (item.text() or ""):
                table.scrollToItem(table.item(r + 1, 0) or item, QTableWidget.ScrollHint.PositionAtTop)
                return
        # Fallback: scroll to first future zone header
        for r in range(table.rowCount()):
            item = table.item(r, 0)
            if item and "SẮP TỚI" in (item.text() or "") and "GẦN" not in (item.text() or ""):
                table.scrollToItem(table.item(r + 1, 0) or item, QTableWidget.ScrollHint.PositionAtTop)
                return

    # ------------------------------------------------------------------
    # Zone helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _row_zone(row: dict, past_rows: list, nearest_row: dict | None) -> str:
        """Return 'past', 'nearest', or 'future' for a data row."""
        if row in past_rows:
            return "past"
        if row is nearest_row:
            return "nearest"
        return "future"

    def _render_zone_header(self, table: QTableWidget, row_idx: int, zone: str) -> None:
        """Render a colored zone separator row with full background fill."""
        configs = {
            "past":    ("─── 📅 ĐÃ QUA ───",                        "#78716C", "#94a3b8", "#F4F1EA", "#1F242F"),
            "nearest": ("─── ⚡ SẮP TỚI GẦN NHẤT ───",              "#137333", "#10b981", "#E6F4EA", "#082f25"),
            "future":  ("─── 📅 SẮP TỚI ───",                       "#B06000", "#fb923c", "#FEF7E0", "#251608"),
        }
        text, fg_light, fg_dark, bg_light, bg_dark = configs.get(zone, ("───", "#aaa", "#aaa", "#fff", "#000"))
        fg_color = QColor(fg_light if self._light else fg_dark)
        bg_color = QColor(bg_light if self._light else bg_dark)

        sep_item = QTableWidgetItem(text)
        sep_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        sep_item.setForeground(fg_color)
        sep_item.setBackground(bg_color)
        f = sep_item.font()
        f.setBold(True)
        sep_item.setFont(f)
        table.setItem(row_idx, 0, sep_item)
        table.setSpan(row_idx, 0, 1, 5)
        
        # Fill rest of row columns with backgrounds to prevent visual glitches on spans
        for c in range(1, 5):
            dummy = QTableWidgetItem()
            dummy.setBackground(bg_color)
            table.setItem(row_idx, c, dummy)
            
        table.setRowHeight(row_idx, 30)

    def _zone_link_colors(self, zone: str) -> tuple[str, str]:
        """Return (color, hover_color) for the detail button based on zone."""
        if zone == "past":
            return ("#78716C", "#94a3b8") if self._light else ("#64748b", "#94a3b8")
        if zone == "nearest":
            return ("#059669", "#047857") if self._light else ("#10b981", "#34d399")
        return ("#C2410C", "#9A3412") if self._light else ("#ea580c", "#fb923c")

    def _show_news_event_detail(self, row: dict, tz) -> None:
        """Show detail dialog for a calendar event from the news feed."""
        ev = {
            "currency": str(row.get("currency", "")),
            "event": str(row.get("title", "")),
            "impact": str(row.get("impact", "low")),
            "forecast": str(row.get("forecast", "")),
            "previous": str(row.get("previous", "")),
            "actual": str(row.get("actual", "")),
            "time_utc": str(row.get("time_utc", "")),
        }
        ev_time = row.get("display_time")
        if isinstance(ev_time, datetime):
            self._show_event_detail(ev, ev_time, tz)

    def _show_headline_detail(self, row: dict, tz) -> None:
        """Show detail dialog for a news headline from the feed."""
        title_text = str(row.get("title", ""))
        source = str(row.get("source", ""))
        url = str(row.get("url", ""))
        dt = row.get("display_time")
        
        local_time_str = ""
        if isinstance(dt, datetime):
            local_dt = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone(tz)
            local_time_str = local_dt.strftime("%d/%m/%Y %H:%M")

        dlg = QDialog(self)
        dlg.setWindowTitle(f"📰 Chi tiết tin tức — {source}")
        dlg.setMinimumSize(700, 450)
        dlg.resize(750, 480)
        dlg.setObjectName("AnalysisDetailDialog")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Title
        title_lbl = QLabel(f"📰 {title_text}")
        title_lbl.setObjectName("ActionTitle")
        title_lbl.setWordWrap(True)
        root.addWidget(title_lbl)

        # Info grid — 2 columns
        info_frame = QFrame()
        info_frame.setStyleSheet("QFrame { background:transparent; border:none; }")
        info_layout = QGridLayout(info_frame)
        info_layout.setContentsMargins(0, 4, 0, 4)
        info_layout.setHorizontalSpacing(40)
        info_layout.setVerticalSpacing(8)

        left_items = [
            ("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>⏰</span> Thời gian", local_time_str or "—"),
            ("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>📰</span> Nguồn", source),
        ]
        
        url_link = f"<a href='{url}' style='color:#ea580c;'>Link gốc</a>" if url else "—"
        right_items = [
            ("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>🔗</span> Liên kết", url_link),
        ]

        for row_idx, (lbl_txt, val_txt) in enumerate(left_items):
            lbl = QLabel(lbl_txt)
            lbl.setObjectName("CardDetail")
            lbl.setFixedWidth(120)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            val = QLabel(val_txt)
            val.setObjectName("CardValue")
            val.setTextFormat(Qt.TextFormat.RichText)
            val.setWordWrap(True)
            info_layout.addWidget(lbl, row_idx, 0)
            info_layout.addWidget(val, row_idx, 1)

        for row_idx, (lbl_txt, val_txt) in enumerate(right_items):
            lbl = QLabel(lbl_txt)
            lbl.setObjectName("CardDetail")
            lbl.setFixedWidth(120)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            val = QLabel(val_txt)
            val.setObjectName("CardValue")
            val.setTextFormat(Qt.TextFormat.RichText)
            val.setWordWrap(True)
            val.setOpenExternalLinks(True)
            info_layout.addWidget(lbl, row_idx, 2)
            info_layout.addWidget(val, row_idx, 3)

        root.addWidget(info_frame)

        # AI analysis area
        ai_response = QTextEdit()
        ai_response.setObjectName("ReadonlyText")
        ai_response.setReadOnly(True)
        ai_response.setMinimumHeight(140)
        ai_response.setPlaceholderText("Bấm \"Tóm tắt AI\" để xem tóm tắt và đánh giá tác động...")
        root.addWidget(ai_response, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        ai_btn = action_button("🤖 Tóm tắt AI", primary=True)
        # Apply Lư Trung Hỏa styling to the action button
        active_bg = "#D94625" if self._light else "#ea580c"
        active_hover = "#E0533C" if self._light else "#f97316"
        disabled_bg = "#DEDAD0" if self._light else "#1f2937"
        disabled_border = "#D6D2C8" if self._light else "#273244"
        disabled_fg = "#736B60" if self._light else "#6b7280"
        
        ai_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:700; padding:0 16px;"
            f"  background:{active_bg}; color:#ffffff; border:none; border-radius:6px;"
            f"  min-height:24px; max-height:24px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{active_hover};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background:{disabled_bg};"
            f"  color:{disabled_fg};"
            f"  border:1px solid {disabled_border};"
            f"}}"
        )
        btn_layout.addWidget(ai_btn)
        btn_layout.addStretch()

        close_btn = action_button("❌ Đóng")
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:500; padding:0 16px;"
            f"  background:transparent;"
            f"  color:{'#4b5563' if self._light else '#9ca3af'};"
            f"  border:1px solid {'#d1d5db' if self._light else '#4b5563'};"
            f"  border-radius:6px; min-height:24px; max-height:24px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{'#fce8e5' if self._light else '#2c1910'};"
            f"  color:{'#D94625' if self._light else '#ea580c'};"
            f"  border:1px solid {'#D94625' if self._light else '#ea580c'};"
            f"}}"
        )
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)

        root.addLayout(btn_layout)

        # Request AI handler
        def request_summary():
            ai_btn.setEnabled(False)
            ai_btn.setText("⏳ Đang tóm tắt...")
            QApplication.processEvents()

            try:
                settings = self.settings_service.load()
                active = settings.ai.active_provider()
                if not active or not (active.api_key or active.api_key_ref):
                    ai_response.setHtml(
                        "<p style='color:#e11d48;font-size:13px;'>"
                        "⚠️ Chưa cấu hình AI. Vào <b>Cài đặt</b> để chọn nhà cung cấp và nhập API key."
                        "</p>"
                    )
                    ai_btn.setText("🤖 Tóm tắt AI")
                    ai_btn.setEnabled(True)
                    return

                from services.ai_service import AIService, AIProviderConfig
                ai_config = AIProviderConfig(
                    provider=active.provider,
                    model=active.model,
                    api_key=active.api_key,
                )
                ai = AIService(ai_config)

                prompt_lines = [
                    f"Tóm tắt tin tức tài chính sau bằng tiếng Việt và phân tích tác động tiềm năng của nó tới thị trường tiền tệ (Forex):",
                    f"- Tiêu đề: {title_text}",
                    f"- Nguồn: {source}",
                ]
                prompt_lines.append("\nHãy phân tích ngắn gọn, trực diện, dễ hiểu cho nhà giao dịch.")
                prompt = "\n".join(prompt_lines)

                summary_text = ai.analyze(prompt)
                ai_response.setMarkdown(summary_text)

            except Exception as e:
                ai_response.setText(f"Lỗi phân tích: {e}")
            finally:
                ai_btn.setText("🤖 Tóm tắt AI")
                ai_btn.setEnabled(True)

        ai_btn.clicked.connect(request_summary)
        dlg.exec()

    def _show_ai_evaluation(self, scope: str) -> None:
        """Show AI evaluation dialog for today's or this week's news.

        Args:
            scope: 'today' or 'week'
        """
        from zoneinfo import ZoneInfo
        try:
            try:
                settings = self.settings_service.load()
                tz_str = settings.display.timezone
            except Exception:
                tz_str = "Asia/Ho_Chi_Minh"
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Ho_Chi_Minh")

        now_utc = datetime.now(timezone.utc)
        now_local = datetime.now(tz)

        if scope == "today":
            start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            end_local = start_local + timedelta(days=1)
            scope_label = "hôm nay"
            scope_date = now_local.strftime("%d/%m/%Y")
        elif scope == "week":
            weekday = now_local.weekday()
            start_local = (now_local - timedelta(days=weekday)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_local = start_local + timedelta(days=7)
            scope_label = "tuần này"
            scope_date = f"{start_local.strftime('%d/%m')} — {now_local.strftime('%d/%m/%Y')}"
        else:  # next_week
            weekday = now_local.weekday()
            this_monday = (now_local - timedelta(days=weekday)).replace(hour=0, minute=0, second=0, microsecond=0)
            start_local = this_monday + timedelta(days=7)
            end_local = start_local + timedelta(days=7)
            scope_label = "tuần tới"
            scope_date = f"{start_local.strftime('%d/%m')} — {(end_local - timedelta(days=1)).strftime('%d/%m/%Y')}"

        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        # Gather items in scope
        combined = self._news_data.get("combined", [])
        if not isinstance(combined, list):
            combined = []

        scope_items: list[dict] = []
        for item in combined:
            dt_val = item.get("display_time")
            if isinstance(dt_val, datetime):
                if start_utc <= dt_val < end_utc:
                    scope_items.append(item)

        # Build dialog
        _light = self._light
        scope_icon = {"today": "📊", "week": "📈", "next_week": "🔮"}.get(scope, "📈")
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{scope_icon} Đánh giá {scope_label} — {scope_date}")
        dlg.setMinimumSize(800, 580)
        dlg.resize(850, 640)
        dlg.setObjectName("AnalysisDetailDialog")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        # Title
        title = QLabel(f"{scope_icon} Đánh giá tin tức {scope_label}")
        title.setObjectName("ActionTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        sub = QLabel(f"Khoảng thời gian: {scope_date}  •  {len(scope_items)} mục tin tức & sự kiện")
        sub.setObjectName("CardDetail")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # Badge summary actual
        actual_count = 0
        better_count = 0
        worse_count = 0
        same_count = 0
        for it in scope_items:
            if it.get("type") == "event":
                actual = str(it.get("actual", "")).strip()
                forecast = str(it.get("forecast", "")).strip()
                if actual and forecast:
                    actual_count += 1
                    try:
                        av = float(actual.replace("%","").replace("M","").replace("B","").replace("K","").replace("$","").replace(",","").strip())
                        fv = float(forecast.replace("%","").replace("M","").replace("B","").replace("K","").replace("$","").replace(",","").strip())
                        if av > fv:
                            better_count += 1
                        elif av < fv:
                            worse_count += 1
                        else:
                            same_count += 1
                    except ValueError:
                        pass

        if actual_count > 0:
            badge_parts = [f"📊 Actual: {actual_count} sự kiện"]
            if better_count > 0:
                badge_parts.append(f"{better_count} tốt hơn")
            if same_count > 0:
                badge_parts.append(f"{same_count} đúng dự báo")
            
            green_text = " — ".join(badge_parts)
            green_color = "#059669" if _light else "#34d399"
            red_color = "#BE123C" if _light else "#e11d48"
            
            if worse_count > 0:
                badge_text = f"<div style='line-height: 140%;'><span style='color: {green_color}; font-weight: 600;'>{green_text} — </span><span style='color: {red_color}; font-weight: 600;'>{worse_count} xấu hơn</span></div>"
            else:
                badge_text = f"<div style='line-height: 140%;'><span style='color: {green_color}; font-weight: 600;'>{green_text}</span></div>"
                
            badge = QLabel(badge_text)
            badge.setObjectName("CardDetail")
            badge.setWordWrap(True)
            badge.setStyleSheet("padding: 4px 0px;")
            root.addWidget(badge)

        # Summary of items to be evaluated (using a QTableWidget for professional look)
        preview_table = QTableWidget()
        preview_table.setObjectName("EconTable")
        preview_table.setColumnCount(3)
        preview_table.setHorizontalHeaderLabels(["Thời gian", "Loại", "Nội dung"])
        preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        preview_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        preview_table.setAlternatingRowColors(True)
        preview_table.verticalHeader().setVisible(False)
        preview_table.setShowGrid(False)
        preview_table.setWordWrap(True)
        preview_table.setMaximumHeight(160)
        preview_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
 
        if scope_items:
            preview_table.setRowCount(len(scope_items))
            for idx, it in enumerate(scope_items):
                it_type = it.get("type", "")
                it_title = str(it.get("title", ""))
                it_currency = str(it.get("currency", ""))
                it_impact = str(it.get("impact", "")).lower()
                dt_val = it.get("display_time")
                
                # Format Time: Thứ 2 28/06 19:30
                if isinstance(dt_val, datetime):
                    local_dt = dt_val.astimezone(tz) if dt_val.tzinfo else dt_val.replace(tzinfo=timezone.utc).astimezone(tz)
                    w_day = local_dt.weekday()
                    w_name = {
                        0: "Thứ 2",
                        1: "Thứ 3",
                        2: "Thứ 4",
                        3: "Thứ 5",
                        4: "Thứ 6",
                        5: "Thứ 7",
                        6: "Chủ Nhật"
                     }.get(w_day, "")
                    time_text = f"{w_name} {local_dt.strftime('%d/%m %H:%M')}"
                else:
                    time_text = "—"
                
                # Row coloring variables
                bg_color = None
                fg_color = None
                
                # Color code impacts and mute past items
                if isinstance(dt_val, datetime) and dt_val < now_utc:
                    fg_color = QColor("#6b7280" if _light else "#8b949e")
                else:
                    if it_type == "event":
                        if it_impact == "high":
                            fg_color = QColor("#b91c1c" if _light else "#f87171")
                            bg_color = QColor("#fdf2f2" if _light else "#2a0d11")
                        elif it_impact == "medium":
                            fg_color = QColor("#b45309" if _light else "#fbbf24")
                            bg_color = QColor("#fffbeb" if _light else "#251608")
                
                def style_cell(cell_item):
                    if fg_color:
                        cell_item.setForeground(fg_color)
                    if bg_color:
                        cell_item.setBackground(bg_color)
                
                # Col 0: Time
                time_item = QTableWidgetItem(time_text)
                time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                style_cell(time_item)
                preview_table.setItem(idx, 0, time_item)
                
                # Col 1: Type
                if it_type == "headline":
                    type_text = "Tin"
                else:
                    type_text = {"high": "Mạnh", "medium": "Vừa", "low": "Yếu"}.get(it_impact, "Yếu")
                type_item = QTableWidgetItem(type_text)
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                style_cell(type_item)
                preview_table.setItem(idx, 1, type_item)
                
                # Col 2: Content
                content_text = it_title if it_type == "headline" else f"{it_currency}: {it_title}"
                content_item = QTableWidgetItem(content_text)
                style_cell(content_item)
                preview_table.setItem(idx, 2, content_item)
                
                preview_table.setRowHeight(idx, 34)
        else:
            preview_table.setRowCount(1)
            preview_table.setSpan(0, 0, 1, 3)
            empty_item = QTableWidgetItem("(Không có tin tức/sự kiện nào trong khoảng thời gian này)")
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_item.setForeground(QColor("#78716C" if _light else "#94a3b8"))
            preview_table.setItem(0, 0, empty_item)
            preview_table.setRowHeight(0, 40)

        # Header adjustments
        header = preview_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        preview_table.setColumnWidth(0, 130)
        preview_table.setColumnWidth(1, 70)
        
        root.addWidget(preview_table)

        # AI response area
        ai_response = QTextEdit()
        ai_response.setObjectName("ReadonlyText")
        ai_response.setReadOnly(True)
        ai_response.setMinimumHeight(200)
        ai_response.setPlaceholderText("Bấm \"Phân tích ngay\" để AI đánh giá...")
        root.addWidget(ai_response, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        ai_btn = action_button("🤖 Phân tích ngay", primary=True)
        # Apply Lư Trung Hỏa styling to the action button
        active_bg = "#D94625" if self._light else "#ea580c"
        active_hover = "#E0533C" if self._light else "#f97316"
        disabled_bg = "#DEDAD0" if self._light else "#1f2937"
        disabled_border = "#D6D2C8" if self._light else "#273244"
        disabled_fg = "#736B60" if self._light else "#6b7280"
        
        ai_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:700; padding:0 16px;"
            f"  background:{active_bg}; color:#ffffff; border:none; border-radius:6px;"
            f"  min-height:24px; max-height:24px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{active_hover};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background:{disabled_bg};"
            f"  color:{disabled_fg};"
            f"  border:1px solid {disabled_border};"
            f"}}"
        )
        btn_layout.addWidget(ai_btn)
        btn_layout.addStretch()

        close_btn = action_button("❌ Đóng")
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:500; padding:0 16px;"
            f"  background:transparent;"
            f"  color:{'#4b5563' if self._light else '#9ca3af'};"
            f"  border:1px solid {'#d1d5db' if self._light else '#4b5563'};"
            f"  border-radius:6px; min-height:24px; max-height:24px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{'#fce8e5' if self._light else '#2c1910'};"
            f"  color:{'#D94625' if self._light else '#ea580c'};"
            f"  border:1px solid {'#D94625' if self._light else '#ea580c'};"
            f"}}"
        )
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)
        root.addLayout(btn_layout)

        # --- AI request handler ---
        def request_evaluation():
            ai_btn.setEnabled(False)
            ai_btn.setText("⏳ Đang phân tích...")
            QApplication.processEvents()

            try:
                settings = self.settings_service.load()
                active = settings.ai.active_provider()
                if not active or not (active.api_key or active.api_key_ref):
                    ai_response.setHtml(
                        "<p style='color:#e11d48;font-size:13px;'>"
                        "⚠️ Chưa cấu hình AI. Vào <b>Cài đặt</b> để chọn nhà cung cấp và nhập API key."
                        "</p>"
                    )
                    return

                from services.ai_service import AIService, AIProviderConfig
                ai_config = AIProviderConfig(
                    provider=active.provider,
                    model=active.model,
                    api_key=active.api_key,
                )
                ai = AIService(ai_config)

                # Build data context for AI
                data_context = self._build_eval_context(scope_items, tz)

                prompt = f"""Bạn là chuyên gia phân tích thị trường tài chính (Forex, Vàng, Crypto).
Hãy đánh giá các tin tức & sự kiện kinh tế {scope_label} ({scope_date}) dưới đây.
{"Đây là các sự kiện SẮP DIỄN RA. Hãy dự báo tác động." if scope == "next_week" else ""}

=== DỮ LIỆU ===
{data_context}

=== YÊU CẦU ===
Trả lời bằng tiếng Việt, định dạng MARKDOWN, CỰC KỲ NGẮN GỌN. Tối đa 8-10 gạch đầu dòng. Không viết đoạn văn dài.

Cấu trúc bắt buộc:

## Biến động {scope_label}
- **Mức biến động chung**: [Thấp / Trung bình / Cao / Rất cao] — (1 câu ngắn)

## Sự kiện đã diễn ra (đánh giá thực tế)
- Dựa vào phần "SO SÁNH THỰC TẾ vs DỰ BÁO", phân tích:
  + Currency nào có nhiều actual TỐT HƠN dự báo → nền kinh tế mạnh hơn kỳ vọng → bullish
  + Currency nào có nhiều actual XẤU HƠN dự báo → nền kinh tế yếu hơn kỳ vọng → bearish
  + Nếu actual == forecast → phản ứng trung tính, thị trường đã priced in

## Sự kiện sắp diễn ra (dự báo)
- Liệt kê các sự kiện quan trọng SẮP diễn ra (ưu tiên tác động cao)
- Dự báo tác động nếu forecast đúng / tốt hơn / xấu hơn

## Tổng hợp xu hướng
- **Cặp tiền/tài sản dự kiến TĂNG**: (liệt kê + lý do dựa trên actual + forecast)
- **Cặp tiền/tài sản dự kiến GIẢM**: (liệt kê + lý do)
- **Khuyến nghị**: (1-2 câu ngắn cho trader)

QUAN TRỌNG:
- SO SÁNH actual vs forecast để đánh giá sức khỏe nền kinh tế từng currency
- Nếu currency có nhiều actual tích cực → xu hướng tăng giá
- Không bịa số liệu. Chỉ dựa trên dữ liệu được cung cấp.
- Nếu không có dữ liệu actual, ghi rõ "Chưa có dữ liệu thực tế để so sánh"
- Tuyệt đối không viết dài dòng."""

                summary_text = ai.analyze(prompt, max_tokens=2500)
                ai_response.setMarkdown(summary_text)

            except Exception as e:
                ai_response.setHtml(
                    f"<p style='color:#e11d48;font-size:13px;'>"
                    f"❌ Lỗi phân tích: {e}"
                    f"</p>"
                )
            finally:
                ai_btn.setText("🤖 Phân tích ngay")
                ai_btn.setEnabled(True)

        ai_btn.clicked.connect(request_evaluation)
        dlg.exec()

    @staticmethod
    def _build_eval_context(items: list[dict], tz) -> str:
        """Build a structured text context from news items for the AI evaluation prompt."""
        if not items:
            return "(Không có tin tức/sự kiện nào trong khoảng thời gian này)"

        def _fmt_time(dt_val) -> str:
            if isinstance(dt_val, datetime):
                local_dt = dt_val.astimezone(tz) if dt_val.tzinfo else dt_val.replace(tzinfo=timezone.utc).astimezone(tz)
                w_day = local_dt.weekday()
                w_name = {0: "Thứ 2", 1: "Thứ 3", 2: "Thứ 4", 3: "Thứ 5", 4: "Thứ 6", 5: "Thứ 7", 6: "Chủ Nhật"}.get(w_day, "")
                return f"{w_name} {local_dt.strftime('%d/%m/%Y %H:%M')}"
            return ""

        lines: list[str] = []
        lines.append(f"Tổng số: {len(items)} mục\n")

        events = [it for it in items if it.get("type") == "event"]
        headlines = [it for it in items if it.get("type") == "headline"]

        if events:
            lines.append("--- SỰ KIỆN KINH TẾ ---")
            for ev in events:
                currency = str(ev.get("currency", ""))
                title = str(ev.get("title", ""))
                impact = str(ev.get("impact", "low")).upper()
                forecast = str(ev.get("forecast", ""))
                previous = str(ev.get("previous", ""))
                actual = str(ev.get("actual", ""))
                time_s = _fmt_time(ev.get("display_time"))
                parts = [f"[{time_s}] {currency}: {title} (Tác động: {impact})"]
                if forecast:
                    parts.append(f"  Dự báo: {forecast}")
                if previous:
                    parts.append(f"  Kỳ trước: {previous}")
                if actual:
                    parts.append(f"  Thực tế: {actual}")
                lines.extend(parts)
            lines.append("")

        if headlines:
            lines.append("--- TIN TỨC ---")
            for h in headlines:
                title = str(h.get("title", ""))
                source = str(h.get("source", ""))
                time_s = _fmt_time(h.get("display_time"))
                if source:
                    lines.append(f"[{time_s}] {title} (Nguồn: {source})")
                else:
                    lines.append(f"[{time_s}] {title}")

        # Comparison section: actual vs forecast
        def _parse_num(val: str) -> float | None:
            val = val.strip().replace(",", "")
            for suffix in ["%", "M", "B", "K", "$"]:
                if val.endswith(suffix):
                    val = val[:-len(suffix)]
                    break
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        lines.append("--- SO SÁNH THỰC TẾ vs DỰ BÁO ---")
        cmp_events: list[tuple] = []
        for ev in events:
            actual = str(ev.get("actual", "")).strip()
            forecast = str(ev.get("forecast", "")).strip()
            if actual and forecast:
                a_val = _parse_num(actual)
                f_val = _parse_num(forecast)
                if a_val is not None and f_val is not None:
                    cmp_events.append((ev, actual, forecast, a_val, f_val))

        if cmp_events:
            lines.append(f"({len(cmp_events)} sự kiện đã có actual)")
            for ev, actual, forecast, a_val, f_val in cmp_events:
                currency = str(ev.get("currency", ""))
                title = str(ev.get("title", ""))
                if a_val > f_val:
                    result = "TỐT HƠN dự báo 📈"
                elif a_val < f_val:
                    result = "XẤU HƠN dự báo 📉"
                else:
                    result = "ĐÚNG dự báo ➡️"
                lines.append(f"{currency} {title}: Thực tế {actual} / Dự báo {forecast} → {result}")
        else:
            lines.append("Không có sự kiện nào đã có actual để so sánh")

        return "\n".join(lines)

    def _show_news_empty(self, message: str) -> None:
        self._light = self._is_light_theme()
        table = self.news_table
        table.setRowCount(1)
        table.setSpan(0, 0, 1, 5)
        item = QTableWidgetItem(message)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor("#78716C" if self._light else "#94a3b8"))
        table.setItem(0, 0, item)
        table.setRowHeight(0, 40)

    def _show_event_detail(self, ev: dict, ev_time: datetime, tz) -> None:
        impact = str(ev.get("impact", "low"))
        currency = str(ev.get("currency", ""))
        event_name = str(ev.get("event", "Sự kiện"))
        forecast = str(ev.get("forecast", "--"))
        previous = str(ev.get("previous", "--"))
        actual = str(ev.get("actual", ""))
        # Guard: clear actual for future events
        now_utc = datetime.now(timezone.utc)
        if ev_time >= now_utc:
            actual = ""
        local_time = ev_time.astimezone(tz)
        time_str = local_time.strftime("%d/%m/%Y %H:%M")

        dlg = QDialog(self)
        dlg.setWindowTitle(f"📊 Chi tiết sự kiện — {currency}")
        dlg.setMinimumSize(700, 480)
        dlg.resize(750, 520)
        dlg.setObjectName("AnalysisDetailDialog")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Title
        title = QLabel(f"📊 {currency}: {event_name}")
        title.setObjectName("ActionTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        # Info grid — 2 columns
        info_frame = QFrame()
        info_frame.setStyleSheet("QFrame { background:transparent; border:none; }")
        info_layout = QGridLayout(info_frame)
        info_layout.setContentsMargins(0, 4, 0, 4)
        info_layout.setHorizontalSpacing(40)
        info_layout.setVerticalSpacing(8)

        impact_map = {
            "high": "<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>🔴</span> Cao",
            "medium": "<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>🟡</span> Trung bình",
            "low": "<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>⚪</span> Thấp"
        }
        impact_text = impact_map.get(impact.lower(), impact)

        left_items = [
            ("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>⏰</span> Thời gian", time_str),
            ("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>💱</span> Tiền tệ", currency),
            ("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>📊</span> Mức tác động", impact_text),
        ]
        right_items = [
            ("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>📈</span> Dự báo", forecast),
            ("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>📉</span> Kỳ trước", previous),
        ]
        actual_val_label = None
        if actual:
            right_items.append(("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>✅</span> Kết quả", actual))
        elif ev_time < now_utc:
            right_items.append(("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>🔄</span> Kết quả", "Đang tra cứu..."))

        for row_idx, (label_text, value_text) in enumerate(left_items):
            lbl = QLabel(label_text)
            lbl.setObjectName("CardDetail")
            lbl.setFixedWidth(120)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            val = QLabel(value_text)
            val.setObjectName("CardValue")
            val.setMargin(2)
            val.setTextFormat(Qt.TextFormat.RichText)
            val.setWordWrap(True)
            if "Mức tác động" in label_text:
                val.setProperty("impact", impact.lower())
            info_layout.addWidget(lbl, row_idx, 0)
            info_layout.addWidget(val, row_idx, 1)

        for row_idx, (label_text, value_text) in enumerate(right_items):
            lbl = QLabel(label_text)
            lbl.setObjectName("CardDetail")
            lbl.setFixedWidth(120)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            val = QLabel(value_text)
            val.setObjectName("CardValue")
            val.setMargin(2)
            val.setTextFormat(Qt.TextFormat.RichText)
            val.setWordWrap(True)
            info_layout.addWidget(lbl, row_idx, 2)
            info_layout.addWidget(val, row_idx, 3)
            if value_text == "Đang tra cứu...":
                actual_val_label = val

        root.addWidget(info_frame)

        if actual_val_label is not None:
            from services.news_service import NewsService
            svc = NewsService()
            worker = ActualLookupWorker(currency, event_name, ev_time.strftime("%Y-%m-%d"), svc, forecast, previous)
            worker.result_ready.connect(
                lambda result, lbl=actual_val_label: lbl.setText(f"✅ {result}" if result else "❌ Không tìm thấy")
            )
            worker.start()

        # AI analysis area
        self._event_ai_response = QTextEdit()
        self._event_ai_response.setObjectName("ReadonlyText")
        self._event_ai_response.setReadOnly(True)
        self._event_ai_response.setMinimumHeight(140)
        self._event_ai_response.setPlaceholderText("Bấm \"Xem tác động\" để AI phân tích...")
        root.addWidget(self._event_ai_response, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        ai_btn = action_button("🤖 Xem tác động", primary=True)
        # Apply Lư Trung Hỏa styling to the action button
        active_bg = "#D94625" if self._light else "#ea580c"
        active_hover = "#E0533C" if self._light else "#f97316"
        disabled_bg = "#DEDAD0" if self._light else "#1f2937"
        disabled_border = "#D6D2C8" if self._light else "#273244"
        disabled_fg = "#736B60" if self._light else "#6b7280"
        
        ai_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:700; padding:0 16px;"
            f"  background:{active_bg}; color:#ffffff; border:none; border-radius:6px;"
            f"  min-height:24px; max-height:24px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{active_hover};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background:{disabled_bg};"
            f"  color:{disabled_fg};"
            f"  border:1px solid {disabled_border};"
            f"}}"
        )
        btn_layout.addWidget(ai_btn)
        btn_layout.addStretch()

        close_btn = action_button("❌ Đóng")
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:500; padding:0 16px;"
            f"  background:transparent;"
            f"  color:{'#4b5563' if self._light else '#9ca3af'};"
            f"  border:1px solid {'#d1d5db' if self._light else '#4b5563'};"
            f"  border-radius:6px; min-height:24px; max-height:24px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{'#fce8e5' if self._light else '#2c1910'};"
            f"  color:{'#D94625' if self._light else '#ea580c'};"
            f"  border:1px solid {'#D94625' if self._light else '#ea580c'};"
            f"}}"
        )
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)

        root.addLayout(btn_layout)

        # Connect AI button
        ai_btn.clicked.connect(lambda: self._request_ai_impact(ai_btn, ev, self._event_ai_response))

        dlg.exec()

    def _request_ai_impact(self, btn: QPushButton, ev: dict, text_widget: QTextEdit) -> None:
        btn.setEnabled(False)
        btn.setText("⏳ Đang phân tích...")
        QApplication.processEvents()

        try:
            settings = self.settings_service.load()
            active = settings.ai.active_provider()
            if not active or not (active.api_key or active.api_key_ref):
                text_widget.setHtml(
                    "<p style='color:#e11d48;font-size:13px;'>"
                    "⚠️ Chưa cấu hình AI. Vào <b>Cài đặt</b> để chọn nhà cung cấp và nhập API key."
                    "</p>"
                )
                btn.setText("🤖 Xem tác động")
                btn.setEnabled(True)
                return

            from services.ai_service import AIService, AIProviderConfig

            ai_config = AIProviderConfig(
                provider=active.provider,
                model=active.model,
                api_key=active.api_key,
            )
            ai = AIService(ai_config)

            currency = str(ev.get("currency", ""))
            event_name = str(ev.get("event", ""))
            impact = str(ev.get("impact", ""))
            forecast = str(ev.get("forecast", "--"))
            previous = str(ev.get("previous", "--"))
            actual = str(ev.get("actual", ""))

            prompt_lines = [
                f"Phân tích ngắn gọn bằng tiếng Việt sự kiện kinh tế sau:",
                f"- Sự kiện: {event_name}",
                f"- Tiền tệ: {currency}",
                f"- Mức tác động: {impact}",
                f"- Dự báo: {forecast}",
                f"- Kỳ trước: {previous}",
            ]
            if actual:
                prompt_lines.append(f"- Kết quả thực tế: {actual}")
                prompt_lines.append("(Đây là tin đã ra — phân tích dựa trên kết quả thực tế này)")
            prompt_lines.extend([
                "",
                "Trả lời theo cấu trúc sau (dùng markdown, ngắn gọn):",
                "### 📌 Tin này là gì?",
                "(Giải thích 1-2 câu)",
                "",
                "### 📈 Tác động đến các cặp tiền và tài sản:",
                f"- Nêu cụ thể từng cặp tiền/tài sản bị ảnh hưởng nếu có ({currency} là chính)",
                "- Với vàng (XAU), bạc (XAG), BTC: nêu rõ nếu có liên quan",
                "- Dùng bullet point, mỗi dòng 1 ý",
                "",
                "### ⚡ Mức độ ảnh hưởng:",
                "(Cao/Trung bình/Thấp — kèm lý do ngắn)",
            ])
            prompt = "\n".join(prompt_lines)

            response = ai.analyze(prompt)

            # Convert markdown to plain text for consistent display
            lines: list[str] = []
            for line in response.split("\n"):
                stripped = line.strip()
                stripped = stripped.replace("**", "").replace("*", "").replace("### ", "").replace("- ", "  • ")
                if not stripped:
                    lines.append("")
                else:
                    lines.append(stripped)
            text_widget.setPlainText("\n".join(lines))

        except Exception as exc:
            text_widget.setHtml(
                f"<p style='color:#e11d48;font-size:13px;'>"
                f"❌ Lỗi khi gọi AI: {exc}"
                f"</p>"
            )
        finally:
            btn.setText("🤖 Xem tác động")
            btn.setEnabled(True)

    def _refresh_market_overview(self) -> None:
        """Fetch market overview data using MarketWorker to avoid freezing UI."""
        self.market_worker = MarketWorker()
        self.market_worker.finished.connect(self._on_market_data_ready)
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
        neutral = "#374151" if self._light else "#e5e7eb"
        green = "#059669" if self._light else "#10b981"
        red = "#BE123C" if self._light else "#e11d48"
        yellow = "#B45309" if self._light else "#f59e0b"
        if tag == "VIX":
            if close > 25:
                status, color = "Rủi ro cao", red
            elif close >= 20:
                status, color = "Cảnh báo", yellow
            else:
                status, color = "Bình thường", green
            label.setText(f"VIX: {close:.1f} — {status}")
        elif tag == "DXY":
            color = green if change_pct > 0 else red if change_pct < 0 else neutral
            label.setText(f"DXY: {close:.2f} {arrow} {abs_change:.1f}%")
        else:  # US10Y / US2Y: lợi suất GIẢM → tốt (xanh), TĂNG → xấu (đỏ)
            color = red if change_pct > 0 else green if change_pct < 0 else neutral
            yr = "10Y" if tag == "US10Y" else "2Y"
            label.setText(f"{tag}: {close:.2f}% {arrow}")
        label.setStyleSheet(f"font-weight:700;font-size:14px;color:{color};")

    def _show_market_help(self) -> None:
        from PyQt6.QtWidgets import QDialog

        self._light = self._is_light_theme()
        dlg = QDialog(self)
        dlg.setWindowTitle("Ý nghĩa các chỉ số thị trường")
        dlg.setMinimumSize(900, 640)
        dlg.resize(960, 680)

        root_layout = QVBoxLayout(dlg)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(14)

        _title_color = "#111827" if self._light else "#f8fafc"
        title = QLabel(f"<b style='font-size:17px;color:{_title_color};'>📊 Hướng dẫn đọc chỉ số thị trường</b>")
        root_layout.addWidget(title)

        # Current market values line (colored like dashboard)
        neutral = "#374151" if self._light else "#e5e7eb"
        green = "#059669" if self._light else "#10b981"
        red = "#BE123C" if self._light else "#e11d48"
        yellow = "#B45309" if self._light else "#f59e0b"

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
        vals_label = QLabel(vals_html)
        vals_label.setObjectName("CardValue")
        vals_label.setWordWrap(True)
        vals_label.setTextFormat(Qt.TextFormat.RichText)
        root_layout.addWidget(vals_label)

        # AI analysis area
        ai_response = QTextEdit()
        ai_response.setObjectName("ReadonlyText")
        ai_response.setReadOnly(True)
        ai_response.setMinimumHeight(150)
        ai_response.setPlaceholderText("Bấm \"🤖 Phân tích AI\" để AI đánh giá ảnh hưởng của các chỉ số hiện tại đến thị trường...")
        root_layout.addWidget(ai_response, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        ai_btn = action_button("🤖 Phân tích AI", primary=True)
        active_bg = "#D94625" if self._light else "#ea580c"
        active_hover = "#E0533C" if self._light else "#f97316"
        disabled_bg = "#DEDAD0" if self._light else "#1f2937"
        disabled_border = "#D6D2C8" if self._light else "#273244"
        disabled_fg = "#736B60" if self._light else "#6b7280"

        ai_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:700; padding:0 16px;"
            f"  background:{active_bg}; color:#ffffff; border:none; border-radius:6px;"
            f"  min-height:24px; max-height:24px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{active_hover};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background:{disabled_bg};"
            f"  color:{disabled_fg};"
            f"  border:1px solid {disabled_border};"
            f"}}"
        )
        btn_layout.addWidget(ai_btn)
        btn_layout.addStretch()

        close_btn = action_button("❌ Đóng")
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:500; padding:0 16px;"
            f"  background:transparent;"
            f"  color:{'#4b5563' if self._light else '#9ca3af'};"
            f"  border:1px solid {'#d1d5db' if self._light else '#4b5563'};"
            f"  border-radius:6px; min-height:24px; max-height:24px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{'#fce8e5' if self._light else '#2c1910'};"
            f"  color:{'#D94625' if self._light else '#ea580c'};"
            f"  border:1px solid {'#D94625' if self._light else '#ea580c'};"
            f"}}"
        )
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)
        root_layout.addLayout(btn_layout)

        def request_analysis():
            ai_btn.setEnabled(False)
            ai_btn.setText("⏳ Đang phân tích...")
            QApplication.processEvents()

            try:
                settings = self.settings_service.load()
                active = settings.ai.active_provider()
                if not active or not (active.api_key or active.api_key_ref):
                    ai_response.setHtml(
                        "<p style='color:#e11d48;font-size:13px;'>"
                        "⚠️ Chưa cấu hình AI. Vào <b>Cài đặt</b> để chọn nhà cung cấp và nhập API key."
                        "</p>"
                    )
                    return

                from services.ai_service import AIService, AIProviderConfig
                ai_config = AIProviderConfig(
                    provider=active.provider,
                    model=active.model,
                    api_key=active.api_key,
                )
                ai = AIService(ai_config)

                mv = getattr(self, "_market_values", None) or {}

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

                result = ai.analyze(prompt, max_tokens=4000)
                ai_response.setMarkdown(result)

            except Exception as e:
                ai_response.setHtml(
                    f"<p style='color:#e11d48;font-size:13px;'>"
                    f"❌ Lỗi phân tích: {e}"
                    f"</p>"
                )
            finally:
                ai_btn.setText("🤖 Phân tích AI")
                ai_btn.setEnabled(True)

        ai_btn.clicked.connect(request_analysis)

        if self._light:
            dlg.setStyleSheet("QDialog { background: #F4F1EA; }")
        else:
            dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
        dlg.exec()

    def set_analysis_result(self, result: dict[str, object]) -> None:
        self.refresh_mt5_status()
        self.refresh_ai_status()

    def refresh_status(self) -> None:
        self.refresh_mt5_status()
        self.refresh_ai_status()

    def refresh_mt5_status(self) -> None:
        status = self.data_provider.connection_status()
        self._apply_connection_status(status)

    def refresh_ai_status(self) -> None:
        settings = self.settings_service.load()
        active = settings.ai.active_provider()
        has_key = bool(active and (active.api_key or active.api_key_ref))
        if active and active.provider and active.model and has_key:
            detail = f"{active.provider} / {active.model}"
            self._set_status_card("AI", "Đã cấu hình", detail, "ok")
        else:
            self._set_status_card("AI", "Chưa cấu hình", "Chọn nhà cung cấp, mô hình và nhập khóa API", "warning")

        # Update data source card
        source = settings.data_source
        source_name = "cTrader" if source == "ctrader" else "MetaTrader 5"
        self._set_status_card("Nguồn dữ liệu", source_name, f"Đang dùng {source_name}", "ok")

    def _apply_connection_status(self, status: ConnectionStatus) -> None:
        provider = status.provider_name or "Dữ liệu"
        if status.initialized and status.connected:
            self._set_status_card("Kết nối", "Đã kết nối", f"{provider}: {status.message}", "ok")
        else:
            detail = status.message
            if status.error_code is not None:
                detail = f"{detail} ({status.error_code})"
            self._set_status_card("Kết nối", "Chưa kết nối", detail, "danger")

        if status.logged_in:
            account = f"{status.login} - {status.server}" if status.login else str(status.server)
            self._set_status_card("Broker", "Đã đăng nhập", account, "ok")
        else:
            self._set_status_card("Broker", "Chưa đăng nhập", f"Cần đăng nhập tài khoản trên {provider}", "warning")

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
        frame.setProperty("state", state)
        frame.style().unpolish(frame)
        frame.style().polish(frame)
