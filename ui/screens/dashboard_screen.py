from __future__ import annotations

from config.constants import SUPPORTED_SYMBOLS
from datetime import datetime, timedelta, timezone
from PyQt6.QtCore import Qt, QTimer
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
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import requests
from services.mt5_service import MT5ConnectionStatus, MT5Service
from services.news_service import NewsService
from services.settings_service import SettingsService


class DashboardScreen(QWidget):
    def __init__(self, navigate=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.mt5_service = MT5Service()
        self.settings_service = SettingsService()
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
            ("MT5", "Đang kiểm tra", "Đang đọc terminal MT5", "warning"),
            ("Broker", "Đang kiểm tra", "Đang đọc tài khoản broker", "warning"),
            ("AI", "Đang kiểm tra", "Đang đọc cấu hình AI", "warning"),
            ("Nguồn dữ liệu", "MetaTrader 5", "Không dùng nguồn giá thay thế", "ok"),
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
        self.mt5_warning_title = QLabel("MT5 chưa sẵn sàng")
        self.mt5_warning_title.setObjectName("WarningTitle")
        self.mt5_warning_detail = QLabel("Hãy mở MetaTrader 5, đăng nhập broker và kiểm tra mã trong Market Watch.")
        self.mt5_warning_detail.setObjectName("WarningDetail")
        self.mt5_warning_detail.setWordWrap(True)
        text_box.addWidget(self.mt5_warning_title)
        text_box.addWidget(self.mt5_warning_detail)
        retry = QPushButton("Thử lại MT5")
        retry.setObjectName("PrimaryButton")
        retry.setCursor(Qt.CursorShape.PointingHandCursor)
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
        help_btn = QPushButton("Giải thích chỉ số")
        help_btn.setObjectName("MarketHelpBtn")
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.econ_table.setStyleSheet(
            "QTableWidget#EconTable {"
            "  background:#161a22; border:none; border-radius:4px; color:#e5e7eb;"
            "  alternate-background-color:#191e28;"
            "}"
            "QTableWidget#EconTable::item {"
            "  font-size:13px; padding:6px 8px; border:none;"
            "}"
            "QHeaderView::section {"
            "  background:#11151d; color:#64748b; font-size:11px; font-weight:700;"
            "  padding:8px 8px; border:none; border-bottom:2px solid #2563eb;"
            "  text-transform:uppercase;"
            "}"
        )

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

        QTimer.singleShot(1000, self._refresh_economic_calendar)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return panel

    def _refresh_economic_calendar(self) -> None:
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

            news = NewsService()
            # Merge JSON + HTML + Cache to get full picture (past + upcoming events)
            events: list[dict] = []
            try:
                json_events = news._fetch_forex_factory_json_events()
                events = json_events
            except Exception:
                pass

            try:
                html_events = news._fetch_forex_factory_html_events()
                if events:
                    news._merge_actual_from_html(events, html_events)
                    existing_keys = set()
                    for ev in events:
                        t = str(ev.get("time_utc", ""))
                        c = str(ev.get("currency", ""))
                        e = str(ev.get("event", ""))
                        existing_keys.add((t, c, e))
                    for hev in html_events:
                        t = str(hev.get("time_utc", ""))
                        c = str(hev.get("currency", ""))
                        e = str(hev.get("event", ""))
                        if (t, c, e) not in existing_keys:
                            events.append(hev)
                else:
                    events = html_events
            except Exception:
                pass

            # Merge cached events: cache stores events from earlier fetches,
            # capturing past-today events that are no longer in live feeds.
            try:
                cached = news._cached_calendar_events()
                if cached and events:
                    existing_keys = set()
                    for ev in events:
                        t = str(ev.get("time_utc", ""))
                        c = str(ev.get("currency", ""))
                        e = str(ev.get("event", ""))
                        existing_keys.add((t, c, e))
                    for cev in cached:
                        t = str(cev.get("time_utc", ""))
                        c = str(cev.get("currency", ""))
                        e = str(cev.get("event", ""))
                        if (t, c, e) not in existing_keys:
                            events.append(cev)
                elif cached and not events:
                    events = cached
            except Exception:
                pass

            if not events:
                self._show_empty_events("Chưa có dữ liệu lịch kinh tế. Kiểm tra kết nối mạng.")
                return

            # Store merged events to cache so future refreshes can show past events
            try:
                news._store_calendar_cache(events)
            except Exception:
                pass

            now = datetime.now(timezone.utc)
            # Calculate today_start in user's timezone, then convert to UTC
            # Example: 06:50 VN Jun 12 = 23:50 UTC Jun 11.
            # Using UTC midnight would incorrectly treat this as "yesterday".
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

            # Find nearest upcoming event index
            nearest_upcoming_idx = None
            for i, (ev_time, _) in enumerate(upcoming):
                if ev_time >= now:
                    nearest_upcoming_idx = i
                    break

            # Insert a separator row between past and upcoming events
            # First pass: build rows with separator markers
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

            # Find the split point (first future event)
            split_idx = None
            for idx, dr in enumerate(display_rows):
                if not dr["is_past"]:
                    split_idx = idx
                    break

            # Insert separator right before first future event
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
                    # Separator row showing "↑ Đã qua | Sắp tới ↓"
                    sep_item = QTableWidgetItem("─── Đã qua ▲  |  ▼ Sắp tới ───")
                    sep_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    sep_item.setForeground(QColor("#ffaa00"))
                    f = sep_item.font()
                    f.setBold(True)
                    sep_item.setFont(f)
                    table.setItem(i, 0, sep_item)
                    # Span across all 6 columns
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

                # Safety: clear actual for future events (should never have actual, but guard against data issues)
                if not is_past and actual:
                    actual = ""

                # --- Cột 0: Thời gian ---
                time_text = local_time.strftime("%d/%m %H:%M")
                time_item = QTableWidgetItem(time_text)
                time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_nearest:
                    time_item.setForeground(QColor("#4caf50"))
                    time_item.setData(Qt.ItemDataRole.UserRole, "▶ ")
                elif is_past:
                    time_item.setForeground(QColor("#64748b"))
                else:
                    time_item.setForeground(QColor("#e5e7eb"))
                font = time_item.font()
                font.setBold(is_nearest)
                time_item.setFont(font)
                table.setItem(i, 0, time_item)

                # --- Cột 1: Sự kiện ---
                if is_nearest:
                    ev_text = f"▶ {dot} {currency}: {event_name}  ← Sắp tới"
                    ev_color = QColor("#4caf50")
                elif is_past:
                    ev_text = f"{dot} {currency}: {event_name}"
                    ev_color = QColor("#64748b")
                else:
                    ev_text = f"{dot} {currency}: {event_name}"
                    if impact == "high":
                        ev_color = QColor("#f44336")
                    elif impact == "medium":
                        ev_color = QColor("#ffaa00")
                    else:
                        ev_color = QColor("#e5e7eb")

                ev_item = QTableWidgetItem(ev_text)
                ev_item.setForeground(ev_color)
                if is_nearest:
                    f = ev_item.font()
                    f.setBold(True)
                    ev_item.setFont(f)
                table.setItem(i, 1, ev_item)

                # --- Cột 2: Dự báo ---
                fc_item = QTableWidgetItem(forecast if forecast else "—")
                fc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_nearest:
                    fc_item.setForeground(QColor("#4caf50"))
                    f = fc_item.font()
                    f.setBold(True)
                    fc_item.setFont(f)
                elif is_past:
                    fc_item.setForeground(QColor("#94a3b8"))
                else:
                    fc_item.setForeground(QColor("#e5e7eb"))
                table.setItem(i, 2, fc_item)

                # --- Cột 3: Kỳ trước ---
                pv_item = QTableWidgetItem(previous if previous else "—")
                pv_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_nearest:
                    pv_item.setForeground(QColor("#4caf50"))
                    f = pv_item.font()
                    f.setBold(True)
                    pv_item.setFont(f)
                elif is_past:
                    pv_item.setForeground(QColor("#94a3b8"))
                else:
                    pv_item.setForeground(QColor("#e5e7eb"))
                table.setItem(i, 3, pv_item)

                # --- Cột 4: Kết quả ---
                if actual:
                    act_item = QTableWidgetItem(actual)
                    act_color = QColor("#4caf50")
                elif is_past:
                    act_item = QTableWidgetItem("Đang cập nhật")
                    act_color = QColor("#f59e0b")
                elif is_nearest:
                    act_item = QTableWidgetItem("—")
                    act_color = QColor("#4caf50")
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

                # --- Cột 5: Link chi tiết ---
                link_color = "#4caf50" if is_nearest else "#60a5fa"
                link_hover = "#66bb6a" if is_nearest else "#93c5fd"
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

                # Row height
                table.setRowHeight(i, 32)

        except Exception:
            self._show_empty_events("Không thể tải lịch kinh tế (lỗi kết nối).")

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
        dlg.setStyleSheet("QDialog { background: #1a1f2e; }")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Title
        title = QLabel(f"<b style='font-size:16px;color:#f8fafc;'>{currency}: {event_name}</b>")
        title.setWordWrap(True)
        root.addWidget(title)

        # Info grid — 2 columns
        info_frame = QFrame()
        info_frame.setStyleSheet("QFrame { background:transparent; border:none; }")
        info_layout = QGridLayout(info_frame)
        info_layout.setContentsMargins(0, 4, 0, 4)
        info_layout.setHorizontalSpacing(40)
        info_layout.setVerticalSpacing(8)

        impact_map = {"high": "🔴 Cao", "medium": "🟡 Trung bình", "low": "⚪ Thấp"}
        impact_text = impact_map.get(impact.lower(), impact)

        left_items = [
            ("⏰ Thời gian", time_str),
            ("💱 Tiền tệ", currency),
            ("📊 Mức tác động", impact_text),
        ]
        right_items = [
            ("📈 Dự báo", forecast),
            ("📉 Kỳ trước", previous),
        ]
        if actual:
            right_items.append(("✅ Kết quả", actual))

        for row_idx, (label_text, value_text) in enumerate(left_items):
            lbl = QLabel(f"<span style='color:#94a3b8;font-size:13px;'>{label_text}:</span>")
            lbl.setFixedWidth(120)
            val = QLabel(f"<span style='color:#e5e7eb;font-size:13px;font-weight:600;'>{value_text}</span>")
            val.setWordWrap(True)
            info_layout.addWidget(lbl, row_idx, 0)
            info_layout.addWidget(val, row_idx, 1)

        for row_idx, (label_text, value_text) in enumerate(right_items):
            lbl = QLabel(f"<span style='color:#94a3b8;font-size:13px;'>{label_text}:</span>")
            lbl.setFixedWidth(120)
            val = QLabel(f"<span style='color:#e5e7eb;font-size:13px;font-weight:600;'>{value_text}</span>")
            val.setWordWrap(True)
            info_layout.addWidget(lbl, row_idx, 2)
            info_layout.addWidget(val, row_idx, 3)

        root.addWidget(info_frame)

        # AI analysis area
        self._event_ai_response = QTextEdit()
        self._event_ai_response.setReadOnly(True)
        self._event_ai_response.setMinimumHeight(140)
        self._event_ai_response.setStyleSheet(
            "QTextEdit { background:#171c24; color:#e5e7eb; font-size:13px; font-family:Segoe UI;"
            "  border:1px solid #2b3545; border-radius:6px; padding:12px;"
            "  selection-background-color:#2563eb; }"
        )
        self._event_ai_response.setPlaceholderText("Bấm \"Xem tác động\" để AI phân tích...")
        root.addWidget(self._event_ai_response, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        ai_btn = QPushButton("🤖 Xem tác động")
        ai_btn.setObjectName("AIImpactBtn")
        ai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ai_btn.setStyleSheet(
            "QPushButton#AIImpactBtn {"
            "  font-size:13px; font-weight:600; padding:8px 18px;"
            "  background:#2563eb; color:#fff; border:none; border-radius:6px;"
            "}"
            "QPushButton#AIImpactBtn:hover { background:#1d4ed8; }"
            "QPushButton#AIImpactBtn:disabled { background:#334155; color:#64748b; }"
        )

        btn_layout.addWidget(ai_btn)
        btn_layout.addStretch()

        close_btn = QPushButton("Đóng")
        close_btn.setObjectName("PrimaryButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
                    "<p style='color:#f44336;font-size:13px;'>"
                    "⚠️ Chưa cấu hình AI. Vào <b>Settings</b> để chọn provider và nhập API key."
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
                f"<p style='color:#f44336;font-size:13px;'>"
                f"❌ Lỗi khi gọi AI: {exc}"
                f"</p>"
            )
        finally:
            btn.setText("🤖 Xem tác động")
            btn.setEnabled(True)

    def _refresh_market_overview(self) -> None:
        """Lấy DXY/VIX/US10Y: thử yfinance trước, tradingview backup."""
        if self._try_market_from_yfinance():
            return
        if self._try_market_from_tradingview():
            return
        self.dxy_label.setText("DXY: Không có dữ liệu")
        self.vix_label.setText("VIX: Không có dữ liệu")
        self.us10y_label.setText("US10Y: Không có dữ liệu")

    def _try_market_from_yfinance(self) -> bool:
        try:
            import yfinance as yf
        except ImportError:
            return False
        tickers = {"DXY": "DX-Y.NYB", "VIX": "^VIX", "US10Y": "^TNX"}
        any_success = False
        for tag, ticker in tickers.items():
            label = getattr(self, f"{tag.lower()}_label")
            try:
                data = yf.download(ticker, period="5d", interval="1d", progress=False)
                if data.empty or len(data) < 2:
                    label.setText(f"{tag}: Chờ dữ liệu...")
                    continue
                close_series = data["Close"]
                close_val = close_series.iloc[-1]
                prev_val = close_series.iloc[-2]
                if hasattr(close_val, "iloc"):
                    close = float(close_val.iloc[0])
                    prev = float(prev_val.iloc[0])
                else:
                    close = float(close_val)
                    prev = float(prev_val)
                change_pct = (close - prev) / prev * 100 if prev != 0 else 0
                self._format_market_label(tag, close, change_pct, label)
                any_success = True
            except Exception:
                label.setText(f"{tag}: Chờ dữ liệu...")
        return any_success

    def _try_market_from_tradingview(self) -> bool:
        """Fallback: Yahoo Finance v8 chart API."""
        tickers = {"DXY": "DX-Y.NYB", "VIX": "^VIX", "US10Y": "^TNX"}
        any_success = False
        for tag, ticker in tickers.items():
            label = getattr(self, f"{tag.lower()}_label")
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 429:
                    import time
                    time.sleep(2)
                    resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code}")
                data = resp.json()
                result = data.get("chart", {}).get("result", [])
                if not result:
                    raise Exception("no chart result")
                quotes = result[0].get("indicators", {}).get("quote", [])
                if not quotes:
                    raise Exception("no quote data")
                closes = quotes[0].get("close", [])
                closes = [c for c in closes if c is not None]
                if len(closes) < 2:
                    raise Exception("not enough close prices")
                close = closes[-1]
                prev = closes[-2]
                change_pct = (close - prev) / prev * 100 if prev != 0 else 0
                self._format_market_label(tag, close, change_pct, label)
                any_success = True
            except Exception:
                continue
        return any_success

    def _format_market_label(self, tag: str, close: float, change_pct: float, label: QLabel) -> None:
        arrow = "↑" if change_pct > 0 else "↓" if change_pct < 0 else ""
        abs_change = abs(change_pct)
        if tag == "VIX":
            if close > 25:
                status, color = "Rủi ro cao", "#f44336"
            elif close >= 20:
                status, color = "Cảnh báo", "#ffaa00"
            else:
                status, color = "Bình thường", "#4caf50"
            label.setText(f"VIX: {close:.1f} — {status}  (sợ hãi thị trường)")
        elif tag == "DXY":
            color = "#4caf50" if change_pct > 0 else "#f44336" if change_pct < 0 else "#e5e7eb"
            label.setText(f"DXY: {close:.2f} {arrow} {abs_change:.1f}%  (sức mạnh USD)")
        else:  # US10Y: lợi suất GIẢM → tốt (xanh), TĂNG → xấu (đỏ)
            color = "#f44336" if change_pct > 0 else "#4caf50" if change_pct < 0 else "#e5e7eb"
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
                        item.setForeground(QColor("#f44336"))
                    elif "Vàng" in val:
                        item.setForeground(QColor("#ffaa00"))
                    elif "Xanh" in val:
                        item.setForeground(QColor("#4caf50"))
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
        close_btn = QPushButton("Đóng")
        close_btn.setObjectName("PrimaryButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        status = self.mt5_service.connection_status()
        self._apply_mt5_status(status)

    def refresh_ai_status(self) -> None:
        settings = self.settings_service.load()
        active = settings.ai.active_provider()
        has_key = bool(active and (active.api_key or active.api_key_ref))
        if active and active.provider and active.model and has_key:
            detail = f"{active.provider} / {active.model}"
            self._set_status_card("AI", "Đã cấu hình", detail, "ok")
        else:
            self._set_status_card("AI", "Chưa cấu hình", "Chọn nhà cung cấp, mô hình và nhập khóa API", "warning")

    def _apply_mt5_status(self, status: MT5ConnectionStatus) -> None:
        if status.initialized and status.terminal_connected:
            self._set_status_card("MT5", "Đã kết nối", status.terminal_name or status.message, "ok")
        else:
            detail = status.message
            if status.error_code is not None:
                detail = f"{detail} ({status.error_code})"
            self._set_status_card("MT5", "Chưa kết nối", detail, "danger")

        if status.logged_in:
            account = f"{status.login} - {status.server}" if status.login else status.server
            self._set_status_card("Broker", "Đã đăng nhập", account, "ok")
        else:
            self._set_status_card("Broker", "Chưa đăng nhập", "Cần đăng nhập tài khoản broker trong MT5", "warning")

        ready = status.initialized and status.terminal_connected and status.logged_in
        self.mt5_warning.setVisible(not ready)
        if ready:
            self.mt5_warning_title.setText("MT5 đã sẵn sàng")
            self.mt5_warning_detail.setText("Đã đọc được terminal và tài khoản broker.")
        else:
            self.mt5_warning_title.setText("MT5 chưa sẵn sàng")
            self.mt5_warning_detail.setText(status.message or "Hãy mở MetaTrader 5, đăng nhập broker và bấm thử lại.")

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
