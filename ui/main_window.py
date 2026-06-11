from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.navigation import NAV_ITEMS
from ui.screens.backtest_screen import BacktestScreen
from ui.screens.dashboard_screen import DashboardScreen
from ui.screens.journal_detail_screen import JournalDetailScreen
from ui.screens.journal_screen import JournalScreen
from ui.screens.scanner_detail_screen import ScannerDetailScreen
from ui.screens.scanner_screen import ScannerScreen
from ui.screens.settings_screen import SettingsScreen


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Market Analyst")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 700)
        self._apply_styles()

        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.sidebar_width = 242
        self.sidebar_open = True

        central = QWidget()
        central.setObjectName("AppShell")
        self.central_shell = central
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentStack")
        self.screens: dict[str, QWidget] = {}

        layout.addWidget(self.stack, 1)
        self.sidebar = self._build_sidebar()
        self.sidebar.setParent(central)
        self.sidebar.raise_()
        self.sidebar_toggle = QPushButton("☰", central)
        self.sidebar_toggle.setObjectName("FloatingSidebarToggle")
        self.sidebar_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_toggle.clicked.connect(lambda: self._set_sidebar_open(True))
        self.sidebar_toggle.hide()
        self.setCentralWidget(central)
        self._build_screens()
        self.navigate("dashboard")
        self.statusBar().showMessage("Sẵn sàng")
        self._position_sidebar()

    def navigate(self, route: str, payload: dict[str, object] | None = None) -> None:
        widget = self.screens.get(route)
        if widget is None:
            return
        if payload is not None and hasattr(widget, "set_analysis_result"):
            widget.set_analysis_result(payload)
        if hasattr(widget, "refresh_status"):
            widget.refresh_status()
        self.stack.setCurrentWidget(widget)
        active_nav = self._nav_key_for_route(route)
        for key, button in self.nav_buttons.items():
            button.setChecked(key == active_nav)
        self.statusBar().showMessage(f"Đang mở: {button_label(active_nav)}", 2500)

    def _apply_styles(self) -> None:
        import sys

        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS) / "ui"
        else:
            base = Path(__file__).resolve().parent
        style_path = base / "styles.qss"
        if style_path.exists():
            self.setStyleSheet(style_path.read_text(encoding="utf-8"))

    def _build_screens(self) -> None:
        screen_factories = {
            "dashboard": DashboardScreen,
            "scanner": ScannerScreen,
            "scanner_detail": ScannerDetailScreen,
            "backtest": BacktestScreen,
            "journal": JournalScreen,
            "journal_detail": JournalDetailScreen,
            "settings": SettingsScreen,
        }
        for route, factory in screen_factories.items():
            screen = factory(self.navigate)
            self.screens[route] = screen
            self.stack.addWidget(screen)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(self.sidebar_width)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 18, 16, 18)
        layout.setSpacing(10)

        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)
        title = QLabel("AI Market Analyst")
        title.setObjectName("SidebarTitle")
        close_button = QPushButton("×")
        close_button.setObjectName("SidebarToggleButton")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(lambda: self._set_sidebar_open(False))
        top_layout.addWidget(title, 1)
        top_layout.addWidget(close_button)
        subtitle = QLabel("Nhà phân tích thị trường")
        subtitle.setObjectName("SidebarSubtitle")
        layout.addWidget(top)
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        for key, label in NAV_ITEMS:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, name=key: self.navigate(nav_route(name)))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        footer = QLabel("Dữ liệu: MT5\nDanh sách: 28 Forex + XAU/USD + XAG/USD + BTC/USD")
        footer.setObjectName("SidebarFooter")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        return sidebar

    def _set_sidebar_open(self, open_: bool) -> None:
        self.sidebar_open = open_
        self.sidebar.setVisible(open_)
        self.sidebar_toggle.setVisible(not open_)
        self._position_sidebar()

    def _position_sidebar(self) -> None:
        if not hasattr(self, "central_shell"):
            return
        height = self.central_shell.height()
        self.sidebar.setGeometry(0, 0, self.sidebar_width, height)
        self.sidebar.raise_()
        self.sidebar_toggle.setGeometry(12, max(12, height - 56), 40, 36)
        self.sidebar_toggle.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_sidebar()

    def _nav_key_for_route(self, route: str) -> str:
        if route.startswith("scanner"):
            return "scanner"
        if route.startswith("backtest"):
            return "backtest"
        if route.startswith("journal"):
            return "journal"
        return route


def nav_route(key: str) -> str:
    return {
        "dashboard": "dashboard",
        "scanner": "scanner",
        "backtest": "backtest",
        "journal": "journal",
        "settings": "settings",
    }[key]


def button_label(key: str) -> str:
    return dict(NAV_ITEMS).get(key, key)
