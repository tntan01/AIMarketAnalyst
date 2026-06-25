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
from services.news_service import NewsService
from services.settings_service import SettingsService

class MarketWorker(QThread):
    finished = pyqtSignal(dict)
    
    def run(self):
        self.finished.emit(fetch_market_overview())

class CalendarWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, force_refresh):
        super().__init__()
        self.force_refresh = force_refresh

    def run(self):
        try:
            from services.news_service import NewsService
            
            if self.force_refresh:
                NewsService._calendar_cache.pop("global", None)

            news = NewsService()
            events = []
            
            try:
                events = news._fetch_forex_factory_json_events()
            except Exception:
                pass
                
            try:
                html_events = news._fetch_forex_factory_html_events()
                if events:
                    news._merge_actual_from_html(events, html_events)
                    existing_keys = set()
                    for ev in events:
                        existing_keys.add((str(ev.get("time_utc", "")), str(ev.get("currency", "")), str(ev.get("event", ""))))
                    for hev in html_events:
                        k = (str(hev.get("time_utc", "")), str(hev.get("currency", "")), str(hev.get("event", "")))
                        if k not in existing_keys:
                            events.append(hev)
                else:
                    events = html_events
            except Exception:
                pass
                
            try:
                cached = news._cached_calendar_events()
                if cached and events:
                    existing_keys = set()
                    for ev in events:
                        existing_keys.add((str(ev.get("time_utc", "")), str(ev.get("currency", "")), str(ev.get("event", ""))))
                    for cev in cached:
                        k = (str(cev.get("time_utc", "")), str(cev.get("currency", "")), str(cev.get("event", "")))
                        if k not in existing_keys:
                            events.append(cev)
                elif cached and not events:
                    events = cached
            except Exception:
                pass
                
            try:
                if events:
                    news._store_calendar_cache(events)
            except Exception:
                pass
                
            self.finished.emit(events)
        except Exception as e:
            self.error.emit(str(e))


class DashboardScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.data_provider = app.data_provider if app else MT5Service()
        self.settings_service = app.settings_service if app else SettingsService()
        self.status_cards: dict[str, tuple[QFrame, QLabel, QLabel]] = {}
        self.setObjectName("DashboardScreen")
        self._build_ui()
        self.refresh_status()

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
        self.economic_calendar = self._build_economic_calendar()
        root.addWidget(self.economic_calendar)
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

        self.dxy_label = QLabel("DXY: Đang tải...")
        self.dxy_label.setObjectName("MarketBadge")
        self.dxy_label.setStyleSheet("font-weight:700;font-size:14px;color:#e5e7eb;")

        self.vix_label = QLabel("VIX: Đang tải...")
        self.vix_label.setObjectName("MarketBadge")
        self.vix_label.setStyleSheet("font-weight:700;font-size:14px;color:#e5e7eb;")

        self.us10y_label = QLabel("US10Y: Đang tải...")
        self.us10y_label.setObjectName("MarketBadge")
        self.us10y_label.setStyleSheet("font-weight:700;font-size:14px;color:#e5e7eb;")

        layout.addWidget(self.dxy_label)
        layout.addWidget(self.vix_label)
        layout.addWidget(self.us10y_label)
        help_btn = action_button("❓ Giải thích chỉ số", primary=True, color="info")
        help_btn.setToolTip("Ý nghĩa các chỉ số")
        help_btn.clicked.connect(self._show_market_help)
        layout.addWidget(help_btn)
        layout.addStretch(1)
        return panel

    def _build_economic_calendar(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        title = QLabel("Lịch kinh tế (Hôm nay: Đã qua + Sắp tới)")
        title.setObjectName("PanelTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.econ_refresh_button = action_button("🔄 Làm mới", primary=True, color="info")
        self.econ_refresh_button.setToolTip("Tải lại toàn bộ lịch kinh tế")
        self.econ_refresh_button.clicked.connect(lambda: self.refresh_economic_calendar(force_refresh=True))
        header_layout.addWidget(self.econ_refresh_button)
        layout.addLayout(header_layout)

        self.econ_table = QTableWidget()
        self.econ_table.setObjectName("EconTable")
        self.econ_table.setColumnCount(6)
        self.econ_table.setHorizontalHeaderLabels(["Thời gian", "Sự kiện", "Dự báo", "Kỳ trước", "Kết quả", ""])
        self.econ_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.econ_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.econ_table.setAlternatingRowColors(True)
        self.econ_table.verticalHeader().setVisible(False)
        self.econ_table.setShowGrid(False)
        self.econ_table.setWordWrap(True)
        self.econ_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        header = self.econ_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)    # Thời gian
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Sự kiện
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # Dự báo
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)    # Kỳ trước
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # Kết quả
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)    # Chi tiết
        self.econ_table.setColumnWidth(0, 95)
        self.econ_table.setColumnWidth(2, 85)
        self.econ_table.setColumnWidth(3, 85)
        self.econ_table.setColumnWidth(4, 100)
        self.econ_table.setColumnWidth(5, 45)

        layout.addWidget(self.econ_table)

        QTimer.singleShot(1000, self.refresh_economic_calendar)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return panel

    def refresh_economic_calendar(self, *, force_refresh: bool = False) -> None:
        refresh_button = getattr(self, "econ_refresh_button", None)
        if refresh_button is not None:
            refresh_button.setEnabled(False)
            refresh_button.setText("Đang tải...")
            QApplication.processEvents()

        self.calendar_worker = CalendarWorker(force_refresh)
        self.calendar_worker.finished.connect(self._on_calendar_data_ready)
        self.calendar_worker.error.connect(lambda e: self._show_empty_events(f"Lỗi: {e}"))
        self.calendar_worker.finished.connect(lambda: self._reset_calendar_button(refresh_button))
        self.calendar_worker.error.connect(lambda: self._reset_calendar_button(refresh_button))
        self.calendar_worker.start()

    def _reset_calendar_button(self, refresh_button):
        if refresh_button is not None:
            refresh_button.setText("🔄 Làm mới")
            refresh_button.setEnabled(True)

    def _on_calendar_data_ready(self, events: list) -> None:
        from zoneinfo import ZoneInfo
        table = self.econ_table
        table.setRowCount(0)

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

            if not events:
                self._show_empty_events("Chưa có dữ liệu lịch kinh tế. Kiểm tra kết nối mạng.")
                return

            now = datetime.now(timezone.utc)
            now_local = datetime.now(tz)
            today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start = today_start_local.astimezone(timezone.utc)
            tomorrow_end = today_start + timedelta(days=2)

            upcoming: list[tuple[datetime, dict]] = []
            for ev in events:
                time_str = ev.get("time_utc", "")
                if not time_str:
                    continue
                try:
                    ev_time = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
                except Exception:
                    continue
                if ev_time.tzinfo is None:
                    ev_time = ev_time.replace(tzinfo=timezone.utc)
                if today_start <= ev_time < tomorrow_end:
                    upcoming.append((ev_time, ev))

            upcoming.sort(key=lambda x: x[0])

            if not upcoming:
                self._show_empty_events("Không có sự kiện kinh tế nào hôm nay và ngày mai.")
                return

            nearest_upcoming_idx = None
            for i, (ev_time, _) in enumerate(upcoming):
                if ev_time >= now:
                    nearest_upcoming_idx = i
                    break

            display_rows: list[dict] = []
            for i, (ev_time, ev) in enumerate(upcoming):
                is_past = ev_time < now
                is_nearest = (i == nearest_upcoming_idx)
                display_rows.append({
                    "ev_time": ev_time,
                    "ev": ev,
                    "is_past": is_past,
                    "is_nearest": is_nearest,
                    "is_separator": False,
                })

            split_idx = None
            for idx, dr in enumerate(display_rows):
                if not dr["is_past"]:
                    split_idx = idx
                    break

            if split_idx is not None and split_idx > 0:
                display_rows.insert(split_idx, {
                    "ev_time": None,
                    "ev": {},
                    "is_past": False,
                    "is_nearest": False,
                    "is_separator": True,
                })

            impact_dots = {"high": "🔴", "medium": "🟡", "low": "⚪"}

            table.setRowCount(len(display_rows))
            for i, dr in enumerate(display_rows):
                if dr["is_separator"]:
                    sep_item = QTableWidgetItem("─── Đã qua ▲  |  ▼ Sắp tới ───")
                    sep_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    sep_item.setForeground(QColor("#f59e0b"))
                    f = sep_item.font()
                    f.setBold(True)
                    sep_item.setFont(f)
                    table.setItem(i, 0, sep_item)
                    table.setSpan(i, 0, 1, 6)
                    table.setRowHeight(i, 28)
                    continue

                ev_time = dr["ev_time"]
                ev = dr["ev"]
                is_past = dr["is_past"]
                is_nearest = dr["is_nearest"]
                impact = str(ev.get("impact", "low")).lower()
                currency = str(ev.get("currency", ""))
                event_name = str(ev.get("event", "Sự kiện"))
                forecast = str(ev.get("forecast", ""))
                previous = str(ev.get("previous", ""))
                actual = str(ev.get("actual", ""))
                local_time = ev_time.astimezone(tz)

                dot = impact_dots.get(impact, "⚪")

                if not is_past and actual:
                    actual = ""

                time_text = local_time.strftime("%d/%m %H:%M")
                time_item = QTableWidgetItem(time_text)
                time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_nearest:
                    time_item.setForeground(QColor("#10b981"))
                    time_item.setData(Qt.ItemDataRole.UserRole, "▶ ")
                elif is_past:
                    time_item.setForeground(QColor("#64748b"))
                font = time_item.font()
                font.setBold(is_nearest)
                time_item.setFont(font)
                table.setItem(i, 0, time_item)

                if is_nearest:
                    ev_text = f"▶ {dot} {currency}: {event_name}  ← Sắp tới"
                    ev_color = QColor("#10b981")
                elif is_past:
                    ev_text = f"{dot} {currency}: {event_name}"
                    ev_color = QColor("#64748b")
                else:
                    ev_text = f"{dot} {currency}: {event_name}"
                    if impact == "high":
                        ev_color = QColor("#e11d48")
                    elif impact == "medium":
                        ev_color = QColor("#f59e0b")
                    else:
                        ev_color = None

                ev_item = QTableWidgetItem(ev_text)
                if ev_color:
                    ev_item.setForeground(ev_color)
                if is_nearest:
                    f = ev_item.font()
                    f.setBold(True)
                    ev_item.setFont(f)
                table.setItem(i, 1, ev_item)

                fc_item = QTableWidgetItem(forecast if forecast else "—")
                fc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_nearest:
                    fc_item.setForeground(QColor("#10b981"))
                    f = fc_item.font()
                    f.setBold(True)
                    fc_item.setFont(f)
                elif is_past:
                    fc_item.setForeground(QColor("#94a3b8"))
                table.setItem(i, 2, fc_item)

                pv_item = QTableWidgetItem(previous if previous else "—")
                pv_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_nearest:
                    pv_item.setForeground(QColor("#10b981"))
                    f = pv_item.font()
                    f.setBold(True)
                    pv_item.setFont(f)
                elif is_past:
                    pv_item.setForeground(QColor("#94a3b8"))
                table.setItem(i, 3, pv_item)

                if actual:
                    act_item = QTableWidgetItem(actual)
                    act_color = QColor("#10b981")
                elif is_past:
                    act_item = QTableWidgetItem("Đang cập nhật")
                    act_color = QColor("#f59e0b")
                elif is_nearest:
                    act_item = QTableWidgetItem("—")
                    act_color = QColor("#10b981")
                else:
                    act_item = QTableWidgetItem("—")
                    act_color = QColor("#64748b")
                act_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                act_item.setForeground(act_color)
                if is_nearest:
                    f = act_item.font()
                    f.setBold(True)
                    act_item.setFont(f)
                table.setItem(i, 4, act_item)

                link_color = "#10b981" if is_nearest else "#ea580c"
                link_hover = "#34d399" if is_nearest else "#fb923c"
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
                detail_btn.clicked.connect(lambda checked, ev=ev, ev_time=ev_time, tz=tz: self._show_event_detail(ev, ev_time, tz))
                table.setCellWidget(i, 5, detail_btn)

                table.setRowHeight(i, 32)

        except Exception:
            self._show_empty_events("Không thể tải lịch kinh tế (lỗi xử lý giao diện).")

    def _show_empty_events(self, message: str) -> None:
        table = self.econ_table
        table.setRowCount(1)
        table.setSpan(0, 0, 1, 6)
        item = QTableWidgetItem(message)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor("#94a3b8"))
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
        dlg.setWindowTitle(f"Chi tiết sự kiện — {currency}")
        dlg.setMinimumSize(700, 480)
        dlg.resize(750, 520)
        dlg.setObjectName("AnalysisDetailDialog")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Title
        title = QLabel(f"{currency}: {event_name}")
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
        if actual:
            right_items.append(("<span style='font-weight:normal; font-family:\"Segoe UI Emoji\";'>✅</span> Kết quả", actual))

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

        root.addWidget(info_frame)

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

        ai_btn = action_button("🤖 Xem tác động", primary=True, color="info")

        btn_layout.addWidget(ai_btn)
        btn_layout.addStretch()

        close_btn = action_button("❌ Đóng")
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

    def _format_market_label(self, tag: str, close: float, change_pct: float, label: QLabel) -> None:
        arrow = "↑" if change_pct > 0 else "↓" if change_pct < 0 else ""
        abs_change = abs(change_pct)
        if tag == "VIX":
            if close > 25:
                status, color = "Rủi ro cao", "#e11d48"
            elif close >= 20:
                status, color = "Cảnh báo", "#f59e0b"
            else:
                status, color = "Bình thường", "#10b981"
            label.setText(f"VIX: {close:.1f} — {status}  (sợ hãi thị trường)")
        elif tag == "DXY":
            color = "#10b981" if change_pct > 0 else "#e11d48" if change_pct < 0 else "#e5e7eb"
            label.setText(f"DXY: {close:.2f} {arrow} {abs_change:.1f}%  (sức mạnh USD)")
        else:  # US10Y: lợi suất GIẢM → tốt (xanh), TĂNG → xấu (đỏ)
            color = "#e11d48" if change_pct > 0 else "#10b981" if change_pct < 0 else "#e5e7eb"
            label.setText(f"US10Y: {close:.2f}% {arrow}  (lợi suất TPCP Mỹ 10Y)")
        label.setStyleSheet(f"font-weight:700;font-size:14px;color:{color};")

    def _show_market_help(self) -> None:
        from PyQt6.QtWidgets import QDialog

        dlg = QDialog(self)
        dlg.setWindowTitle("Ý nghĩa các chỉ số thị trường")
        dlg.setMinimumSize(900, 540)
        dlg.resize(960, 580)

        root_layout = QVBoxLayout(dlg)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(18)

        title = QLabel("<b style='font-size:17px;color:#f8fafc;'>📊 Hướng dẫn đọc chỉ số thị trường</b>")
        root_layout.addWidget(title)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["", "Chỉ số", "Màu sắc", "Ý nghĩa"])
        table.setRowCount(8)

        data = [
            ["📈", "DXY", "🟢 Xanh", "USD mạnh lên so với hôm qua — tốt cho USD, xấu cho vàng"],
            ["📈", "DXY", "🔴 Đỏ", "USD yếu đi so với hôm qua — tốt cho vàng, EUR, GBP..."],
            ["😱", "VIX", "🟢 Xanh (< 20)", "Thị trường ổn định, ít sợ hãi — giao dịch bình thường"],
            ["😱", "VIX", "🟡 Vàng (20-25)", "Cảnh báo, bắt đầu bất ổn — giao dịch cẩn thận"],
            ["😱", "VIX", "🔴 Đỏ (> 25)", "Rủi ro cao, thị trường hoảng loạn — hạn chế giao dịch"],
            ["💰", "US10Y", "🟢 Xanh", "Lợi suất giảm → tiền rẻ hơn, tốt cho thị trường"],
            ["💰", "US10Y", "🔴 Đỏ", "Lợi suất tăng → tiền đắt hơn, áp lực lên thị trường"],
            ["", "", "⚪️ Trắng", "Không có dữ liệu hoặc không thay đổi"],
        ]

        for r, row_data in enumerate(data):
            for c, val in enumerate(row_data):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c < 2 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if c == 2:
                    if "Đỏ" in val:
                        item.setForeground(QColor("#e11d48"))
                    elif "Vàng" in val:
                        item.setForeground(QColor("#f59e0b"))
                    elif "Xanh" in val:
                        item.setForeground(QColor("#10b981"))
                table.setItem(r, c, item)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

        table.setMinimumHeight(280)
        table.setStyleSheet(
            "QTableWidget { background: #171c24; border: 1px solid #2b3545; border-radius: 6px; }"
            "QTableWidget::item { color: #e5e7eb; font-size: 13px; padding: 8px 10px; }"
            "QHeaderView::section { background: #1e293b; color: #94a3b8; font-size: 12px; font-weight: 700; padding: 8px 10px; border: none; border-bottom: 1px solid #334155; }"
        )
        root_layout.addWidget(table)

        note = QLabel("<span style='color:#94a3b8;font-size:12px;'><b>Ghi chú:</b> DXY tăng = xanh (USD mạnh). US10Y tăng = đỏ (ngược với DXY vì lợi suất tăng gây áp lực lên thị trường).</span>")
        note.setWordWrap(True)
        root_layout.addWidget(note)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = action_button("❌ Đóng")
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)
        root_layout.addLayout(btn_layout)

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
