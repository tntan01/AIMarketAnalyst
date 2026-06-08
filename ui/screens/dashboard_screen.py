from __future__ import annotations

from config.constants import SUPPORTED_SYMBOLS
from datetime import datetime, timedelta, timezone
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
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
        root.addLayout(self._build_footer_strip())
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
        grid.setSpacing(12)
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
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(7)
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
        title = QLabel("Lịch kinh tế (48h tới)")
        title.setObjectName("PanelTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self.econ_events_widget = QWidget()
        self.econ_events_widget.setStyleSheet("background:transparent;")
        self.econ_events_container = QVBoxLayout(self.econ_events_widget)
        self.econ_events_container.setContentsMargins(0, 0, 0, 0)
        self.econ_events_container.setSpacing(6)
        self.econ_events_container.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("EconScroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.econ_events_widget)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea#EconScroll{border:none;background:transparent;}")
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(scroll)

        QTimer.singleShot(3500, self._refresh_economic_calendar)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return panel

    def _refresh_economic_calendar(self) -> None:
        from zoneinfo import ZoneInfo

        while self.econ_events_container.count() > 1:
            item = self.econ_events_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

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
            try:
                events = news._fetch_forex_factory_json_events()
            except Exception:
                events = news._cached_calendar_events()

            if not events:
                self._show_empty_events("Chưa có dữ liệu lịch kinh tế. Kiểm tra kết nối mạng.")
                return

            now = datetime.now(timezone.utc)
            cutoff = now + timedelta(hours=48)

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
                if now <= ev_time <= cutoff:
                    upcoming.append((ev_time, ev))

            upcoming.sort(key=lambda x: x[0])

            if not upcoming:
                self._show_empty_events("Không có sự kiện kinh tế nào trong 48h tới.")
                return

            impact_labels = {"high": "🔴", "medium": "🟡", "low": "⚪"}
            impact_colors = {"high": "#f44336", "medium": "#ffaa00", "low": "#e5e7eb"}

            for ev_time, ev in upcoming:
                impact = str(ev.get("impact", "low")).lower()
                if impact not in impact_colors:
                    impact = "low"
                currency = str(ev.get("currency", ""))
                event_name = str(ev.get("event", "Sự kiện"))
                local_time = ev_time.astimezone(tz)
                time_str = local_time.strftime("%d/%m %H:%M")

                dot = impact_labels.get(impact, "⚪")
                color = impact_colors.get(impact, "#e5e7eb")
                line_text = f"{dot} {time_str} — {currency}: {event_name}"
                label = QLabel(line_text)
                label.setStyleSheet(f"font-size:13px;color:{color};padding:2px 0;")
                label.setWordWrap(True)
                self.econ_events_container.addWidget(label)

        except Exception:
            self._show_empty_events("Không thể tải lịch kinh tế (lỗi kết nối).")

    def _show_empty_events(self, message: str) -> None:
        label = QLabel(message)
        label.setStyleSheet("font-size:13px;color:#8b9dc3;padding:4px 0;")
        label.setWordWrap(True)
        self.econ_events_container.addWidget(label)

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
                data = yf.download(ticker, period="2d", interval="1d", progress=False)
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
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=2d&interval=1d"
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
            self.ai_mode_value.setText(detail)
        else:
            self._set_status_card("AI", "Chưa cấu hình", "Chọn nhà cung cấp, mô hình và nhập khóa API", "warning")
            self.ai_mode_value.setText("Chưa cấu hình")

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

    def _build_footer_strip(self) -> QHBoxLayout:
        from ui.screens.shared import labeled_value

        layout = QHBoxLayout()
        layout.setSpacing(12)
        layout.addWidget(labeled_value("Múi giờ", "Asia/Ho_Chi_Minh"))
        layout.addWidget(labeled_value("Khung chính", "D1 / H4 / H1"))
        ai_mode = labeled_value("Chế độ AI", "Đang kiểm tra")
        self.ai_mode_value = ai_mode.findChildren(QLabel)[1]
        layout.addWidget(ai_mode)
        return layout
