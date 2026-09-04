from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QSize
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from controllers.app_controller import AppController
from ui.icons import flat_icon
from ui.navigation import NAV_ICONS, NAV_ITEMS
from ui.screens.backtest_screen import BacktestScreen
from ui.screens.dashboard_screen import DashboardScreen
from ui.screens.journal_detail_screen import JournalDetailScreen
from ui.screens.journal_screen import JournalScreen
from ui.screens.scanner_detail_screen import ScannerDetailScreen
from ui.screens.scanner_screen import ScannerScreen
from ui.screens.orders_screen import OrdersScreen
from ui.screens.settings_screen import SettingsScreen
from ui.theme_manager import ThemeManager, resolve_theme


class _NavIconFilter(QObject):
    """Đổi màu icon nav theo trạng thái hover/checked.

    QSS `color:` không tint được QIcon và QPushButton không request QIcon
    mode Active khi hover (cùng lý do như LinkToneHoverFilter ở
    dashboard_screen), nên filter tự swap QIcon theo role:
    bình thường `normal_role`, hover hoặc checked `hover_role`
    (thường là "selection_text" — trắng trên nền accent).
    """

    def __init__(self, button, icon_name, normal_role, hover_role, parent=None):
        super().__init__(parent)
        self.button = button
        self.icon_name = icon_name
        self.normal_role = normal_role
        self.hover_role = hover_role
        self._hovered = False
        button.installEventFilter(self)
        button.toggled.connect(self._apply)
        self._apply()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.HoverEnter:
            self._hovered = True
            self._apply()
        elif event.type() == QEvent.Type.HoverLeave:
            self._hovered = False
            self._apply()
        return super().eventFilter(obj, event)

    def _apply(self, *args) -> None:
        active = self._hovered or self.button.isChecked()
        role = self.hover_role if active else self.normal_role
        self.button.setIcon(flat_icon(self.icon_name, role))


class MainWindow(QMainWindow):
    def __init__(self, app: AppController | None = None) -> None:
        super().__init__()
        self.app = app or AppController()
        self.setWindowTitle("AI Market Analyst")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 700)
        self._apply_styles()

        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.sidebar_width = 48

        central = QWidget()
        central.setObjectName("AppShell")
        self.central_shell = central
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentStack")
        self.screens: dict[str, QWidget] = {}

        self.sidebar = self._build_sidebar()
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._build_screens()
        self.navigate("dashboard")
        self.statusBar().showMessage("Sẵn sàng")

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
        settings_service = (
            self.app.settings_service
            if hasattr(self, "app") and self.app
            else None
        )
        theme = resolve_theme(settings_service=settings_service)
        manager = getattr(self, "_theme_manager", None)
        if manager is None:
            manager = ThemeManager()
            self._theme_manager = manager
        manager.apply(
            self,
            theme=theme,
            settings_service=settings_service,
        )
            
        if hasattr(self, "screens"):
            for screen in self.screens.values():
                if hasattr(screen, "refresh_theme_styles"):
                    screen.refresh_theme_styles()

    def _build_screens(self) -> None:
        screen_factories = {
            "dashboard": DashboardScreen,
            "scanner": ScannerScreen,
            "orders": OrdersScreen,
            "scanner_detail": ScannerDetailScreen,
            "backtest": BacktestScreen,
            "journal": JournalScreen,
            "journal_detail": JournalDetailScreen,
            "settings": SettingsScreen,
        }
        for route, factory in screen_factories.items():
            screen = factory(self.navigate, app=self.app)
            self.screens[route] = screen
            self.stack.addWidget(screen)
        # Order Management is application-owned and remains active regardless
        # of which screen is visible. Scanner workers publish registrations to
        # this service; they never call OrdersScreen/QWidget directly.
        if self.app:
            self.app.order_management_service.start()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(self.sidebar_width)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        # Icon rail gắn cứng: mỗi mục là một nút icon-only + tooltip tên mục.
        for key, label in NAV_ITEMS:
            button = QPushButton()
            button.setObjectName("NavButton")
            button.setToolTip(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setCheckable(True)
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(lambda _checked=False, name=key: self.navigate(nav_route(name)))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            _NavIconFilter(button, NAV_ICONS[key], "text", "selection_text")
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)

        # Nút khởi động lại (icon-only + tooltip)
        restart_btn = QPushButton()
        restart_btn.setToolTip("Khởi động lại")
        restart_btn.setIconSize(QSize(16, 16))
        self.restart_btn = restart_btn
        restart_btn.setObjectName("RestartButton")
        restart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restart_btn.clicked.connect(self._restart_app)
        _NavIconFilter(restart_btn, "refresh", "accent", "accent_hover")
        layout.addWidget(restart_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        return sidebar

    def _restart_app(self) -> None:
        """Xác nhận và khởi động lại ứng dụng."""
        from PyQt6.QtWidgets import QMessageBox
        import subprocess, sys, os

        reply = QMessageBox.question(
            self, "Khởi động lại",
            "Khởi động lại ứng dụng?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Release application-owned resources before spawning the replacement.
        try:
            self.app.shutdown()
        except Exception:
            pass

        # Launch new process
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable]
        else:
            cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'main.py')]
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)

        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

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
        "orders": "orders",
        "backtest": "backtest",
        "journal": "journal",
        "settings": "settings",
    }[key]


def button_label(key: str) -> str:
    return dict(NAV_ITEMS).get(key, key)
