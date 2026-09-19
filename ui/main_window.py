from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QSize
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from controllers.app_controller import AppController
from ui.icons import flat_icon
from ui.navigation import NAV_ICONS, NAV_ITEMS
from ui.screens.dashboard_screen import DashboardScreen
from ui.screens.journal_detail_screen import JournalDetailScreen
from ui.screens.journal_screen import JournalScreen
from ui.screens.scanner_detail_screen import ScannerDetailScreen
from ui.screens.scanner_screen import ScannerScreen
from ui.screens.orders_screen import OrdersScreen
from ui.screens.settings_screen import SettingsScreen
from ui.theme_manager import ThemeManager, resolve_theme
from ui.window_state import (
    MINIMUM_WINDOW_SIZE,
    StartupDecision,
    WindowStateStore,
    default_settings,
    normal_window_rect,
    resolve_startup,
)


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
    """Cửa sổ chính kiêm owner duy nhất của policy geometry (R1).

    Constructor **không** đụng tới hình học hay `QSettings`: mọi quyết định
    startup/restore/persist chỉ chạy khi caller gọi `apply_startup_policy()`
    (production: `main.py`). Nhờ vậy test/tool dựng `MainWindow` để kiểm tra
    giao diện không ghi state của người dùng.
    """

    def __init__(
        self,
        app: AppController | None = None,
        *,
        window_state: WindowStateStore | None = None,
    ) -> None:
        super().__init__()
        self.app = app or AppController()
        self.setWindowTitle("AI Market Analyst")
        self.setMinimumSize(*MINIMUM_WINDOW_SIZE)
        self._window_state = window_state
        self._persist_window_state = False
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

    def _title_bar_inset(self) -> int:
        """Chiều cao title bar theo logical pixel của style đang dùng (F-R5-01).

        `resolve_startup()` phải thuần/deterministic nên metric nền tảng được
        đọc ở đây rồi truyền vào tường minh; module policy không hard-code offset
        DPI/vật lý. Không đọc được metric thì trả 0 — policy vẫn đúng, chỉ mất
        phần nới dải chrome theo style.
        """
        style = self.style()
        if style is None:
            return 0
        try:
            height = style.pixelMetric(
                QStyle.PixelMetric.PM_TitleBarHeight, None, self
            )
        except (TypeError, AttributeError):
            return 0
        return max(int(height), 0)

    def apply_startup_policy(self, *, normal_window: bool = False) -> StartupDecision:
        """Entry point duy nhất cho startup/restore/show của cửa sổ chính.

        Production gọi đúng một lần từ `main.py`. Restore chỉ dựa trên
        `QScreen.availableGeometry()` (logical pixel) qua `resolve_startup()`;
        state thiếu/hỏng/ngoài màn hình đều quay về maximize.

        Geometry normal "giả maximized" (F-R5-01) cũng quay về maximize: cửa sổ
        chạm dải chrome trên trong khi phủ gần toàn vùng làm việc thì title bar
        và nút hệ thống không thao tác được, nên restore nguyên trạng là trạng
        thái hỏng chứ không phải trạng thái người dùng chọn.

        `normal_window=True` là policy tường minh cho test/dev: bỏ qua state đã
        lưu và **không** ghi state khi đóng, để không đè geometry người dùng.
        """
        if self._window_state is None:
            self._window_state = WindowStateStore(default_settings())
        available = [screen.availableGeometry() for screen in QApplication.screens()]

        normal_size: tuple[int, int] | None = None
        if normal_window and available:
            normal_rect = normal_window_rect(available[0])
            normal_size = (normal_rect.width(), normal_rect.height())

        decision = resolve_startup(
            None if normal_window else self._window_state.load(),
            available,
            normal_window_size=normal_size,
            chrome_inset=self._title_bar_inset(),
        )
        if decision.maximized:
            self.showMaximized()
        else:
            self.setGeometry(decision.rect)
            self.show()
        self._persist_window_state = not normal_window
        return decision

    def closeEvent(self, event) -> None:
        """Lưu geometry/state trước khi đóng; không đổi hành vi shutdown khác."""
        if self._window_state is not None and self._persist_window_state:
            try:
                self._window_state.save_from(self)
            except Exception:
                # Không để lỗi ghi state chặn việc đóng ứng dụng.
                pass
        super().closeEvent(event)

    def navigate(self, route: str, payload: dict[str, object] | None = None) -> None:
        widget = self.screens.get(route)
        if widget is None:
            # Tuyến không tồn tại (vd. route cũ "backtest" còn sót trong mã
            # hoặc trạng thái điều hướng cũ): đưa ứng dụng về màn hình hợp lệ
            # thay vì đứng yên ở stack hiện tại.
            if route != "dashboard" and "dashboard" in self.screens:
                self.navigate("dashboard")
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
            button.setIconSize(QSize(24, 24))
            button.clicked.connect(lambda _checked=False, name=key: self.navigate(nav_route(name)))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            _NavIconFilter(button, NAV_ICONS[key], "text", "selection_text")
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)

        # Nút khởi động lại (icon-only + tooltip)
        restart_btn = QPushButton()
        restart_btn.setToolTip("Khởi động lại")
        restart_btn.setIconSize(QSize(24, 24))
        self.restart_btn = restart_btn
        restart_btn.setObjectName("RestartButton")
        restart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restart_btn.clicked.connect(self._restart_app)
        _NavIconFilter(restart_btn, "refresh", "text", "selection_text")
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
        if route.startswith("journal"):
            return "journal"
        return route

def nav_route(key: str) -> str:
    return {
        "dashboard": "dashboard",
        "scanner": "scanner",
        "orders": "orders",
        "journal": "journal",
        "settings": "settings",
    }.get(key, "dashboard")


def button_label(key: str) -> str:
    return dict(NAV_ITEMS).get(key, key)
