from __future__ import annotations

import ast
from dataclasses import asdict
from datetime import datetime, timedelta

from PyQt6.QtCore import QAbstractTableModel, QDate, QModelIndex, Qt, QTimer, QPoint
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QHeaderView,
    QScrollArea,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QSizePolicy,
)

from controllers.journal_controller import JournalController
from services.journal_models import JournalEntry, JournalFilter
from services.journal_converters import build_performance_summary
from ui.layout_system import configure_table
from ui.rich_text import compile_rich_html
from ui.matplotlib_theme import apply_axes_theme, apply_figure_theme
from ui.screens.shared import action_button, card, labeled_value, page_header
from ui.theme.fonts import get_body_font, get_title_font
from ui.theme_manager import current_palette, set_dynamic_property

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


class PerformanceKPICard(QFrame):
    """Thẻ hiển thị số liệu KPI với label nhỏ phía trên, giá trị lớn ở trung tâm, viền màu accent và badge status."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PerformanceKPICard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(82)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("KPICardTitle")
        header_layout.addWidget(self.title_label, 1)

        self.badge_label = QLabel("")
        self.badge_label.setObjectName("KPICardBadge")
        header_layout.addWidget(self.badge_label)
        layout.addLayout(header_layout)

        self.value_label = QLabel("--")
        self.value_label.setObjectName("KPICardValue")
        layout.addWidget(self.value_label)

        self.sub_label = QLabel("")
        self.sub_label.setObjectName("KPICardSub")
        self.sub_label.setWordWrap(True)
        layout.addWidget(self.sub_label)

        self.set_state("neutral")

    def set_data(self, value: str, state: str = "neutral", sub_text: str = "", badge: str = "") -> None:
        self.value_label.setText(value)
        self.sub_label.setText(sub_text)
        self.badge_label.setText(badge)
        self.set_state(state)

    def set_state(self, state: str) -> None:
        normalized = state if state in {
            "positive", "negative", "warning", "neutral", "muted"
        } else "neutral"
        set_dynamic_property(self, "kpiState", normalized)
        set_dynamic_property(self.value_label, "kpiState", normalized)
        set_dynamic_property(self.sub_label, "kpiState", normalized)


class MissingRBanner(QFrame):
    """Banner cảnh báo nổi bật khi phát hiện các lệnh đóng chưa có dữ liệu Result R."""

    def __init__(self, on_cta_clicked, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MissingRBanner")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        icon_label = QLabel("⚠️")
        icon_label.setObjectName("MissingRIcon")
        layout.addWidget(icon_label)

        self.text_label = QLabel("")
        self.text_label.setObjectName("MissingRText")
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label, 1)

        self.cta_button = action_button("✏️ Điền Result R ngay", primary=True, color="warning")
        self.cta_button.clicked.connect(on_cta_clicked)
        layout.addWidget(self.cta_button)

    def set_missing_info(self, missing_count: int, total_closed: int) -> None:
        if total_closed > 0 and missing_count > 0:
            set_dynamic_property(self, "state", "warning")
            set_dynamic_property(self.text_label, "state", "warning")
            if missing_count == total_closed:
                msg = f"<b>Chưa có dữ liệu Result R:</b> Tất cả {total_closed} lệnh đã đóng chưa điền SL / Entry. Các chỉ số Expectancy, Tổng R, DD tối đa chưa thể tính toán."
            else:
                msg = f"<b>Phát hiện thiếu Result R:</b> Có {missing_count} / {total_closed} lệnh đã đóng chưa điền SL / Entry. Hãy cập nhật Result R để kết quả thống kê R chính xác nhất."
            self.text_label.setText(msg)
            self.setVisible(True)
        else:
            set_dynamic_property(self, "state", "hidden")
            set_dynamic_property(self.text_label, "state", "hidden")
            self.setVisible(False)


class PerformanceChartWidget(QWidget):
    """Widget vẽ 2 biểu đồ Matplotlib: Lãi/lỗ theo Mã (Bar chart) & Đường cong Lợi nhuận Lũy kế (Equity Curve)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_by_symbol: list[dict[str, object]] = []
        self._last_recent_trades: list[dict[str, object]] = []
        self._last_selected_symbol: str | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        if not HAS_MATPLOTLIB:
            fallback = QLabel("Biểu đồ yêu cầu thư viện matplotlib.")
            fallback.setObjectName("EmptyText")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(fallback)
            self.canvas = None
            return

        self.figure = Figure(
            figsize=(10, 3.0),
            tight_layout=True,
            facecolor=current_palette().background,
        )
        apply_figure_theme(self.figure)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setObjectName("MatplotlibCanvas")
        self.canvas.setMinimumHeight(210)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.canvas)
        self.update_charts([], [])

    def update_charts(
        self,
        by_symbol: list[dict[str, object]],
        recent_trades: list[dict[str, object]],
        selected_symbol: str | None = None,
    ) -> None:
        if not HAS_MATPLOTLIB or self.canvas is None:
            return

        self._last_by_symbol = list(by_symbol)
        self._last_recent_trades = list(recent_trades)
        self._last_selected_symbol = selected_symbol
        self.figure.clear()
        palette_colors = apply_figure_theme(self.figure)
        text_color = palette_colors["text"]
        grid_color = palette_colors["grid"]

        # Plot 1: Horizontal Bar Chart - P/L theo Mã
        ax1 = self.figure.add_subplot(121)
        apply_axes_theme(ax1, palette_colors)

        symbols = []
        pls = []
        colors = []

        filtered_symbol_data = [row for row in by_symbol if isinstance(row, dict) and row.get("label")]
        for row in filtered_symbol_data[:8]:
            sym = str(row.get("label", ""))
            net = float(row.get("net_amount", 0) or 0)
            symbols.append(sym)
            pls.append(net)
            if selected_symbol and sym == selected_symbol:
                colors.append(palette_colors["info"])
            else:
                colors.append(
                    palette_colors["buy"] if net >= 0
                    else palette_colors["sell"]
                )

        if symbols:
            symbols.reverse()
            pls.reverse()
            colors.reverse()

            bars = ax1.barh(symbols, pls, color=colors, height=0.55, edgecolor="none", alpha=0.85)
            ax1.axvline(0, color=grid_color, linestyle="--", linewidth=1)

            min_val = min(pls)
            max_val = max(pls)
            max_abs = max(abs(min_val), abs(max_val), 1.0)

            # Tự động set giới hạn X rộng hơn 25% để không bị cắt hoặc đè số tiền P/L
            x_margin = max_abs * 0.28
            ax1.set_xlim(min(0, min_val) - x_margin, max(0, max_val) + x_margin)

            for bar, val in zip(bars, pls):
                offset = max_abs * 0.04
                x_pos = val + offset if val >= 0 else val - offset
                ha = "left" if val >= 0 else "right"
                txt = f"+${val:,.0f}" if val >= 0 else f"-${abs(val):,.0f}"
                ax1.text(
                    x_pos,
                    bar.get_y() + bar.get_height() / 2,
                    txt,
                    va="center",
                    ha=ha,
                    color=text_color,
                    fontsize=8,
                    fontweight="bold",
                )

            ax1.set_title("Lãi/Lỗ theo Mã ($)", color=text_color, fontsize=10, fontweight="bold", pad=8)
        else:
            ax1.text(0.5, 0.5, "Chưa có dữ liệu theo mã", ha="center", va="center", color=text_color, fontsize=9)
            ax1.set_title("Lãi/Lỗ theo Mã ($)", color=text_color, fontsize=10, fontweight="bold", pad=8)
            ax1.set_xticks([])
            ax1.set_yticks([])

        ax1.tick_params(colors=text_color, labelsize=8, pad=6)
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)
        ax1.spines["left"].set_color(grid_color)
        ax1.spines["bottom"].set_color(grid_color)
        ax1.xaxis.grid(True, linestyle=":", alpha=0.4, color=grid_color)
        apply_axes_theme(ax1, palette_colors)

        # Plot 2: Line / Area Chart - Equity Curve
        ax2 = self.figure.add_subplot(122)
        apply_axes_theme(ax2, palette_colors)

        valid_trades = [t for t in recent_trades if isinstance(t, dict) and t.get("closed_at")]
        if selected_symbol:
            valid_trades = [t for t in valid_trades if t.get("symbol") == selected_symbol]

        valid_trades.sort(key=lambda x: str(x.get("closed_at", "")))

        if valid_trades:
            cum_pl = []
            running = 0.0
            for t in valid_trades:
                pl = float(t.get("result_amount", 0) or 0)
                running += pl
                cum_pl.append(running)

            x_indices = list(range(1, len(cum_pl) + 1))
            line_color = palette_colors["info"]
            if cum_pl[-1] > 0:
                line_color = palette_colors["buy"]
            elif cum_pl[-1] < 0:
                line_color = palette_colors["sell"]

            ax2.plot(x_indices, cum_pl, marker="o", markersize=3, color=line_color, linewidth=2, label="P/L Tích lũy")
            ax2.fill_between(x_indices, 0, cum_pl, color=line_color, alpha=0.15)
            ax2.axhline(0, color=grid_color, linestyle="--", linewidth=1)

            title_suffix = f" [{selected_symbol}]" if selected_symbol else ""
            ax2.set_title(
                f"Đường cong P/L Lũy kế ($){title_suffix}",
                color=text_color,
                fontsize=10,
                fontweight="bold",
                pad=8,
            )
            ax2.set_xlabel("Số lệnh đóng", color=text_color, fontsize=8)
        else:
            ax2.text(0.5, 0.5, "Chưa có lịch sử lệnh đóng", ha="center", va="center", color=text_color, fontsize=9)
            ax2.set_title("Đường cong P/L Lũy kế ($)", color=text_color, fontsize=10, fontweight="bold", pad=8)
            ax2.set_xticks([])
            ax2.set_yticks([])

        ax2.tick_params(colors=text_color, labelsize=8)
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_visible(False)
        ax2.spines["left"].set_color(grid_color)
        ax2.spines["bottom"].set_color(grid_color)
        ax2.yaxis.grid(True, linestyle=":", alpha=0.4, color=grid_color)
        apply_axes_theme(ax2, palette_colors)

        self.figure.tight_layout()
        self.canvas.draw()

    def refresh_theme_styles(self) -> None:
        """Redraw cached chart data with the active semantic palette."""

        self.update_charts(
            self._last_by_symbol,
            self._last_recent_trades,
            selected_symbol=self._last_selected_symbol,
        )



DECISION_TEXT = {
    "ready": "Sẵn sàng",
    "watch": "Theo dõi",
    "wait": "Chờ",
    "wait_for_confirmation": "Chờ",
    "stand_aside": "Đứng ngoài",
    "closed": "Đã đóng",
    "skip": "Bỏ qua",
}
BIAS_TEXT = {"buy": "Mua", "sell": "Bán", "neutral": "Trung lập", "stand_aside": "Đứng ngoài"}
REGIME_TEXT = {
    "trend": "Xu hướng",
    "range": "Đi ngang",
    "volatile": "Biến động mạnh",
    "breakout": "Bứt phá",
    "pullback": "Hồi giá",
    "unknown": "Chưa XĐ",
}
PERMISSION_TEXT = {"allowed": "Được phép", "caution": "Cẩn trọng", "blocked": "Bị chặn"}


class JournalTableModel(QAbstractTableModel):
    COLUMNS = [
        ("timestamp_utc", "Thời gian"),
        ("symbol", "Mã"),
        ("setup_type", "Setup"),
        ("execution_regime", "Regime"),
        ("trade_status", "Trạng thái"),
        ("direction_bias", "Thiên hướng"),
        ("result_r", "R"),
        ("result_amount", "Lợi nhuận"),
        ("execution_quality_score", "CL Thực thi"),
        ("note", "Ghi chú"),
        ("open", "Chi tiết"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[JournalEntry] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self.entries[index.row()]
        key = self.COLUMNS[index.column()][0]
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(entry, key)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if key in {"trade_status", "direction_bias", "result_r", "execution_quality_score", "open", "note"}:
                return Qt.AlignmentFlag.AlignCenter
            if key == "result_amount":
                return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if role == Qt.ItemDataRole.ForegroundRole:
            palette = current_palette()
            if key == "open":
                return QColor(palette.info)
            if key == "trade_status":
                return {
                    "planned": QColor(palette.text_muted),
                    "opened": QColor(palette.info),
                    "closed": QColor(palette.success),
                    "cancelled": QColor(palette.danger),
                    "missed": QColor(palette.warning),
                }.get(entry.trade_status)
            if key == "direction_bias":
                return {
                    "buy": QColor(palette.buy),
                    "sell": QColor(palette.sell),
                }.get(self._direction_bias_side(entry.direction_bias))
            if key == "result_r":
                val = entry.result_r
                if val is not None:
                    return QColor(palette.success) if val > 0 else QColor(palette.danger) if val < 0 else None
            if key == "result_amount":
                val = entry.result_amount
                if val is not None:
                    return QColor(palette.success) if val > 0 else QColor(palette.danger) if val < 0 else None
        if role == Qt.ItemDataRole.ToolTipRole:
            if key == "direction_bias":
                return self._direction_bias_tooltip(entry.direction_bias)
            return entry.note or entry.ai_commentary
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section][1]
        return str(section + 1)

    def set_entries(self, entries: list[JournalEntry]) -> None:
        self.beginResetModel()
        self.entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> JournalEntry | None:
        if 0 <= row < len(self.entries):
            return self.entries[row]
        return None

    def _display(self, entry: JournalEntry, key: str) -> str:
        if key == "open":
            return "Chi tiết"
        if key == "timestamp_utc":
            return format_time(entry.timestamp_utc)
        if key == "setup_type":
            return entry.setup_type or "--"
        if key == "execution_regime":
            val = str(entry.execution_regime or "").lower()
            return REGIME_TEXT.get(val, entry.execution_regime or "Chưa XĐ")
        if key == "trade_status":
            status_map = {
                "planned": "Kế hoạch",
                "opened": "Đang mở",
                "closed": "Đã đóng",
                "cancelled": "Đã hủy",
                "missed": "Bỏ lỡ",
            }
            return status_map.get(entry.trade_status, entry.trade_status or "Kế hoạch")
        if key == "direction_bias":
            bias = self._direction_bias_payload(entry.direction_bias)
            if bias:
                side = str(bias.get("best_side") or "").strip().lower()
                return BIAS_TEXT.get(side, "Trung lập")
            raw_bias = str(entry.direction_bias or "").strip().lower()
            return BIAS_TEXT.get(raw_bias, entry.direction_bias or "--")
        if key == "result_r":
            if entry.result_r is not None:
                return f"{entry.result_r:+.2f}R"
            return "--"
        if key == "result_amount":
            if entry.result_amount is not None:
                return f"{entry.result_amount:+.2f}"
            return "--"
        if key == "execution_quality_score":
            if entry.execution_quality_score is not None:
                return f"{entry.execution_quality_score}"
            return "--"
        if key == "note":
            # Hiển thị icon nếu có ghi chú, để trống nếu không
            return "📝" if entry.note else ""
        value = getattr(entry, key)
        return str(value if value not in (None, "") else "--")

    @staticmethod
    def _direction_bias_payload(value: object) -> dict[str, object]:
        """Read the legacy Scanner direction-bias representation for display only."""
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            return {}
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @classmethod
    def _direction_bias_side(cls, value: object) -> str:
        payload = cls._direction_bias_payload(value)
        if payload:
            return str(payload.get("best_side") or "").strip().lower()
        return str(value or "").strip().lower()

    @classmethod
    def _direction_bias_tooltip(cls, value: object) -> str:
        payload = cls._direction_bias_payload(value)
        if not payload:
            return cls._display_bias_text(value)

        side = cls._direction_bias_side(value)
        label = BIAS_TEXT.get(side, "Trung lập")
        buy_score = cls._format_bias_score(payload.get("buy_score"))
        sell_score = cls._format_bias_score(payload.get("sell_score"))
        score_parts = [
            f"Điểm Mua: {buy_score}" if buy_score is not None else "",
            f"Điểm Bán: {sell_score}" if sell_score is not None else "",
        ]
        return "\n".join([f"Thiên hướng: {label}", *filter(None, score_parts)])

    @staticmethod
    def _format_bias_score(value: object) -> str | None:
        try:
            return f"{float(value):.0f}"
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _display_bias_text(value: object) -> str:
        raw_bias = str(value or "").strip().lower()
        return BIAS_TEXT.get(raw_bias, str(value or "--"))


class NotePopup(QFrame):
    """Popup hiển thị ghi chú — neo vào vị trí click, đóng khi click ra ngoài hoặc ESC."""

    _instance: NotePopup | None = None

    @classmethod
    def show_at(cls, text: str, global_pos: QPoint, parent: QWidget) -> None:
        """Hiển thị popup với nội dung 'text' tại vị trí global."""
        # Đóng popup cũ nếu đang mở
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None

        popup = cls(text, parent)
        popup.move_near(global_pos)
        popup.show()
        popup.raise_()
        cls._instance = popup

    @classmethod
    def close_active(cls) -> None:
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None

    def __init__(self, text: str, parent: QWidget) -> None:
        # Qt.WindowType.ToolTip: tự đóng khi click ngoài, không xuất hiện trong taskbar
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setObjectName("NotePopup")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(0)

        label = QLabel(text)
        label.setObjectName("NotePopupText")
        label.setWordWrap(True)
        label.setMaximumWidth(360)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(label)

        self.adjustSize()

    def move_near(self, global_pos: QPoint) -> None:
        """Neo popup nhưa dưới global_pos, tuyến lại nếu ra khỏi màn hình."""
        screen = QApplication.primaryScreen().availableGeometry()
        x = global_pos.x()
        y = global_pos.y() + 6
        w = self.sizeHint().width()
        h = self.sizeHint().height()
        if x + w > screen.right():
            x = screen.right() - w - 4
        if y + h > screen.bottom():
            y = global_pos.y() - h - 6
        self.move(x, y)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            NotePopup.close_active()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        if NotePopup._instance is self:
            NotePopup._instance = None
        super().closeEvent(event)


class NoteIconDelegate(QStyledItemDelegate):
    """Vẽ icon ghi chú 💬 với kích thước lớn, màu nổi bật và hover effect."""

    _ICON_CHAR = "💬"  # speech bubble — trực quan hơn 📝

    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        # Vẽ nền mặc định (hover/selected row highlight)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        self.parent().style().drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget
        )

        if not text:
            return

        painter.save()
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        palette = current_palette()

        # Font to hơn font dữ liệu thông thường
        font = get_title_font()
        font.setBold(False)
        painter.setFont(font)

        color = QColor(
            palette.accent_hover if is_hover else palette.warning
        )

        painter.setPen(color)
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, self._ICON_CHAR)
        painter.restore()



class LinkDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        # Vẽ nền mặc định (hover/selected row) của table
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = "" # xóa text để vẽ background rỗng
        self.parent().style().drawControl(
            QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget
        )

        painter.save()
        text = index.data(Qt.ItemDataRole.DisplayRole) or "Chi tiết"
        
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        palette = current_palette()

        # Dùng font body chuẩn, đồng nhất với các ô dữ liệu khác.
        font = get_body_font()
        if is_hover:
            font.setUnderline(True)
            color = QColor(palette.accent_hover)
        else:
            font.setUnderline(False)
            color = QColor(palette.info)

        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class JournalScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.journal_controller = (
            app.journal_controller if app else JournalController()
        )
        self.table_model = JournalTableModel()
        self._sync_buttons: list[QPushButton] = []
        self._selected_symbol_filter: str | None = None
        self._cached_perf_data: dict[str, object] = {}
        self.stat_labels: dict[str, QLabel] = {}
        self.performance_labels: dict[str, QLabel] = {}
        self.tabs: QTabWidget | None = None
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)
        root.addWidget(page_header("Nhật ký phân tích", "", "SQLite"))

        self.tabs = QTabWidget()
        self.tabs.setObjectName("ContentTabs")

        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(0, 4, 0, 0)
        tab1_layout.setSpacing(8)
        tab1_layout.addWidget(self._quick_filter_bar())
        tab1_layout.addWidget(self._filters())
        tab1_layout.addWidget(self._table_card(), 1)
        self.tabs.addTab(tab1, "Nhật ký Phân tích")

        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.setContentsMargins(0, 4, 0, 0)
        tab2_layout.setSpacing(8)
        tab2_layout.addWidget(self._performance_card(), 1)
        self.tabs.addTab(tab2, "Thống kê Hiệu suất")

        self.tabs.currentChanged.connect(self._on_tab_changed)

        root.addWidget(self.tabs, 1)
        self.refresh_status()

    def _filters(self) -> QFrame:
        frame = card()
        frame.layout().setContentsMargins(12, 6, 12, 6)
        frame_layout = QVBoxLayout()
        frame_layout.setSpacing(4)
        frame.layout().addLayout(frame_layout)

        # Row 1: Ô tìm kiếm + nút mở rộng/thu gọn + xóa lọc
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm theo mã, ghi chú, thẻ...")
        self.search_input.setObjectName("FilterField")
        self.search_input.setClearButtonEnabled(True)

        self.filter_toggle_btn = action_button("▶ Bộ lọc")
        self.filter_toggle_btn.setFixedWidth(90)
        self.filter_toggle_btn.clicked.connect(self._toggle_filter_panel)

        clear_btn = action_button("🧹 Xóa lọc")
        clear_btn.clicked.connect(self._clear_filters)

        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.filter_toggle_btn)
        search_row.addWidget(clear_btn)
        frame_layout.addLayout(search_row)

        # Collapsible filter grid
        self.filter_panel = QFrame()
        self.filter_panel.setVisible(False)
        grid = QGridLayout(self.filter_panel)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setVerticalSpacing(4)
        grid.setHorizontalSpacing(6)

        # Khởi tạo tất cả filter widgets
        self.symbol_input = QComboBox()
        self.symbol_input.setObjectName("FilterField")
        self.symbol_input.addItem("Tất cả mã", None)

        self.status_input = QComboBox()
        self.status_input.setObjectName("FilterField")
        self.status_input.addItem("Tất cả trạng thái", None)
        self.status_input.addItem("Kế hoạch", "planned")
        self.status_input.addItem("Đã mở", "opened")
        self.status_input.addItem("Đã đóng", "closed")
        self.status_input.addItem("Đã hủy", "cancelled")
        self.status_input.addItem("Bỏ lỡ", "missed")

        self.result_input = QComboBox()
        self.result_input.setObjectName("FilterField")
        self.result_input.addItem("Tất cả kết quả", None)
        self.result_input.addItem("Thắng", "win")
        self.result_input.addItem("Thua", "loss")
        self.result_input.addItem("Hòa", "breakeven")

        self.session_input = QComboBox()
        self.session_input.setObjectName("FilterField")
        self.session_input.addItem("Tất cả phiên", None)

        self.decision_input = QComboBox()
        self.decision_input.setObjectName("FilterField")
        self.decision_input.addItems(["Tất cả", "Sẵn sàng", "Theo dõi", "Chờ", "Đứng ngoài"])

        self.permission_input = QComboBox()
        self.permission_input.setObjectName("FilterField")
        self.permission_input.addItems(["Tất cả", "Được phép", "Cẩn trọng", "Bị chặn"])

        self.setup_input = QComboBox()
        self.setup_input.setObjectName("FilterField")
        self.setup_input.addItem("Tất cả setup", None)

        self.regime_input = QComboBox()
        self.regime_input.setObjectName("FilterField")
        self.regime_input.addItem("Tất cả execution_regime", None)

        self.date_from_input = QDateEdit()
        self.date_from_input.setCalendarPopup(True)
        self.date_from_input.setButtonSymbols(QDateEdit.ButtonSymbols.NoButtons)
        self.date_from_input.setDate(QDate.currentDate().addMonths(-1))
        self.date_from_input.setDisplayFormat("dd/MM/yyyy")
        self.date_from_input.setObjectName("FilterField")

        self.date_to_input = QDateEdit()
        self.date_to_input.setCalendarPopup(True)
        self.date_to_input.setButtonSymbols(QDateEdit.ButtonSymbols.NoButtons)
        self.date_to_input.setDate(QDate.currentDate())
        self.date_to_input.setDisplayFormat("dd/MM/yyyy")
        self.date_to_input.setObjectName("FilterField")

        self.min_score_input = QSpinBox()
        self.min_score_input.setRange(0, 100)
        self.min_score_input.setValue(0)
        self.min_score_input.setObjectName("FilterField")

        self.min_quality_input = QSpinBox()
        self.min_quality_input.setRange(0, 100)
        self.min_quality_input.setValue(0)
        self.min_quality_input.setObjectName("FilterField")

        # Grid 2 hàng x 6 cột
        grid.addWidget(self._filter_group("Mã", self.symbol_input), 0, 0)
        grid.addWidget(self._filter_group("Trạng thái", self.status_input), 0, 1)
        grid.addWidget(self._filter_group("Kết quả", self.result_input), 0, 2)
        grid.addWidget(self._filter_group("Phiên", self.session_input), 0, 3)
        grid.addWidget(self._filter_group("Kết luận", self.decision_input), 0, 4)
        grid.addWidget(self._filter_group("Quyền", self.permission_input), 0, 5)

        grid.addWidget(self._filter_group("Setup", self.setup_input), 1, 0)
        grid.addWidget(self._filter_group("Regime", self.regime_input), 1, 1)
        grid.addWidget(self._filter_group("Từ ngày", self.date_from_input), 1, 2)
        grid.addWidget(self._filter_group("Đến ngày", self.date_to_input), 1, 3)
        grid.addWidget(self._filter_group("Điểm AI ≥", self.min_score_input), 1, 4)
        grid.addWidget(self._filter_group("CL Thực thi ≥", self.min_quality_input), 1, 5)

        frame_layout.addWidget(self.filter_panel)

        # Debounce timer cho ô tìm kiếm (300ms)
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._apply_filters)

        self.search_input.textChanged.connect(lambda: self._debounce_timer.start())

        # Các filter khác áp dụng ngay lập tức
        for combo in [self.symbol_input, self.status_input, self.result_input,
                      self.session_input, self.decision_input, self.permission_input,
                      self.setup_input, self.regime_input]:
            combo.currentTextChanged.connect(self._apply_filters)
        self.date_from_input.dateChanged.connect(self._apply_filters)
        self.date_to_input.dateChanged.connect(self._apply_filters)
        self.min_score_input.valueChanged.connect(self._apply_filters)
        self.min_quality_input.valueChanged.connect(self._apply_filters)

        return frame

    def _filter_group(self, label: str, widget: QWidget) -> QWidget:
        """Nhóm label + widget theo chiều dọc, tiết kiệm không gian."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        lbl = QLabel(label)
        lbl.setObjectName("FormLabel")
        layout.addWidget(lbl)
        layout.addWidget(widget)
        return w

    def _toggle_filter_panel(self) -> None:
        visible = not self.filter_panel.isVisible()
        self.filter_panel.setVisible(visible)
        if visible:
            self.filter_toggle_btn.setText("▼ Thu gọn")
            self._refresh_filter_values()
        else:
            self.filter_toggle_btn.setText("▶ Bộ lọc")

    # ------------------------------------------------------------------
    # Quick Filter
    # ------------------------------------------------------------------

    # (label, group, filter_widget_attr, setter_lambda, resetter_lambda)
    # setter: gọi khi nút được chọn.  resetter: gọi khi nút bỏ chọn.
    _QUICK_FILTER_DEFS: list[tuple[str, str, str, object, object]] = [
        # Thời gian
        ("Hôm nay",    "time", "date", None, None),  # setter/resetter tính động theo days
        ("7 ngày",     "time", "date", None, None),
        ("30 ngày",    "time", "date", None, None),
        # Kết quả
        ("Lệnh thắng", "result", "result", "win", None),
        ("Lệnh thua",  "result", "result", "loss", None),
        # AI
        ("Điểm AI ≥ 85",       "ai", "min_score", 85, 0),
        ("Độ tin cậy AI ≥ 90", "ai", "min_score", 90, 0),
        # Chất lượng thực thi
        ("Thực thi tốt", "quality", "min_quality", 70, 0),
        ("Thực thi kém", "quality", "max_quality", 40, 0),
    ]

    def _quick_filter_bar(self) -> QWidget:
        """Thanh Lọc nhanh — các nút một chạm để thiết lập nhanh JournalFilter."""
        self._quick_btns: dict[str, QPushButton] = {}
        self._quick_groups: dict[str, list[str]] = {}  # group -> list of labels

        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel("Lọc nhanh:")
        lbl.setObjectName("FormLabel")
        layout.addWidget(lbl)

        days_map = {"Hôm nay": 0, "7 ngày": 7, "30 ngày": 30}

        for label, group, attr, set_val, reset_val in self._QUICK_FILTER_DEFS:
            btn = action_button(label)
            btn.setProperty("quickFilter", True)
            size_hint = btn.sizeHint()
            btn.setMinimumSize(size_hint.width() + 12, size_hint.height() + 6)
            btn.setCheckable(True)
            btn.setProperty("qf_group", group)
            btn.setProperty("qf_attr", attr)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.toggled.connect(lambda checked, b=btn: self._on_quick_filter_toggled(b, checked))
            self._quick_btns[label] = btn
            self._quick_groups.setdefault(group, []).append(label)
            layout.addWidget(btn)

            # Gán setter/resetter cho nút thời gian (động theo days)
            if attr == "date":
                days = days_map[label]
                btn.setProperty("qf_set_val", days)
                btn.setProperty("qf_reset_val", 30)  # reset về "1 tháng trước"

        layout.addStretch(1)
        self.quick_filter_layout = layout
        return widget

    def _on_quick_filter_toggled(self, btn: QPushButton, checked: bool) -> None:
        """Xử lý khi một nút Quick Filter được bật/tắt."""
        group: str = btn.property("qf_group") or ""
        attr: str = btn.property("qf_attr") or ""

        if checked:
            # Bỏ chọn các nút khác trong cùng nhóm
            for other_label in self._quick_groups.get(group, []):
                other_btn = self._quick_btns.get(other_label)
                if other_btn and other_btn is not btn and other_btn.isChecked():
                    other_btn.blockSignals(True)
                    other_btn.setChecked(False)
                    other_btn.blockSignals(False)

            # Áp dụng giá trị filter
            self._apply_quick_filter_value(attr, btn.property("qf_set_val"))
        else:
            # Khôi phục giá trị mặc định
            self._apply_quick_filter_value(attr, btn.property("qf_reset_val"))

    def _apply_quick_filter_value(self, attr: str, value: object) -> None:
        """Ghi giá trị vào widget Advanced Filter tương ứng và trigger làm mới."""
        today = QDate.currentDate()

        if attr == "date":
            days = int(value) if value is not None else 30
            self.date_from_input.blockSignals(True)
            self.date_to_input.blockSignals(True)
            self.date_from_input.setDate(today.addDays(-days))
            self.date_to_input.setDate(today)
            self.date_from_input.blockSignals(False)
            self.date_to_input.blockSignals(False)
            self._apply_filters()
            return

        if attr == "result":
            target = "win" if value == "win" else "loss" if value == "loss" else None
            self.result_input.blockSignals(True)
            if target:
                idx = self.result_input.findData(target)
                self.result_input.setCurrentIndex(idx if idx >= 0 else 0)
            else:
                self.result_input.setCurrentIndex(0)
            self.result_input.blockSignals(False)
            return

        if attr == "min_score":
            self.min_score_input.blockSignals(True)
            self.min_score_input.setValue(int(value) if value else 0)
            self.min_score_input.blockSignals(False)
            return

        if attr == "min_quality":
            self.min_quality_input.blockSignals(True)
            self.min_quality_input.setValue(int(value) if value else 0)
            self.min_quality_input.blockSignals(False)
            return

        if attr == "max_quality":
            # Ghi trực tiếp vào JournalFilter vì không có widget UI riêng
            self._apply_filters()
            return

    def _current_max_quality(self) -> int:
        """Đọc giá trị max_execution_quality từ trạng thái nút Quick Filter."""
        for label, group, attr, set_val, _ in self._QUICK_FILTER_DEFS:
            if attr == "max_quality":
                btn = self._quick_btns.get(label)
                if btn and btn.isChecked():
                    return int(set_val) if set_val else 0
        return 0

    def _filtered_stats_bar(self) -> QWidget:
        """Widget thống kê nhanh nhúng vào Header của bảng Journal."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.total_lbl = QLabel("Tổng:")
        self.total_lbl.setObjectName("StatsLabel")
        self.total_val = QLabel()
        self.total_val.setObjectName("StatsValue")

        self.dot1 = QLabel("•")
        self.dot1.setObjectName("StatsSeparator")

        self.showing_lbl = QLabel("Hiển thị:")
        self.showing_lbl.setObjectName("StatsLabel")
        self.showing_val = QLabel()
        self.showing_val.setObjectName("StatsValue")

        self.dot2 = QLabel("•")
        self.dot2.setObjectName("StatsSeparator")

        self.winrate_lbl = QLabel("Win:")
        self.winrate_lbl.setObjectName("StatsLabel")
        self.winrate_val = QLabel()
        self.winrate_val.setObjectName("StatsValue")

        self.dot3 = QLabel("•")
        self.dot3.setObjectName("StatsSeparator")

        self.expectancy_lbl = QLabel("Kỳ vọng:")
        self.expectancy_lbl.setObjectName("StatsLabel")
        self.expectancy_val = QLabel()
        self.expectancy_val.setObjectName("StatsValue")

        self.dot4 = QLabel("•")
        self.dot4.setObjectName("StatsSeparator")

        self.pf_lbl = QLabel("PF:")
        self.pf_lbl.setObjectName("StatsLabel")
        self.pf_val = QLabel()
        self.pf_val.setObjectName("StatsValue")

        layout.addWidget(self.total_lbl)
        layout.addWidget(self.total_val)
        layout.addWidget(self.dot1)
        layout.addWidget(self.showing_lbl)
        layout.addWidget(self.showing_val)
        layout.addWidget(self.dot2)
        layout.addWidget(self.winrate_lbl)
        layout.addWidget(self.winrate_val)
        layout.addWidget(self.dot3)
        layout.addWidget(self.expectancy_lbl)
        layout.addWidget(self.expectancy_val)
        layout.addWidget(self.dot4)
        layout.addWidget(self.pf_lbl)
        layout.addWidget(self.pf_val)
        return widget

    def _update_filtered_stats_bar(self, entries: list[JournalEntry]) -> None:
        total = self.journal_controller.total_entries()
        showing = len(entries)

        closed_entries = [e for e in entries if e.closed_at and e.result_r is not None]
        if closed_entries:
            trade_dicts = [asdict(e) for e in closed_entries]
            perf = build_performance_summary(trade_dicts)
            summary = perf.get("summary", {}) if isinstance(perf.get("summary"), dict) else {}

            self.winrate_val.setText(f"{summary.get('win_rate', 0)}%")
            self.expectancy_val.setText(f"{summary.get('expectancy_r', 0)}R")
            self.pf_val.setText(f"{summary.get('profit_factor', 0)}")

            self.dot2.setVisible(True)
            self.dot3.setVisible(True)
            self.dot4.setVisible(True)
            self.winrate_lbl.setVisible(True)
            self.winrate_val.setVisible(True)
            self.expectancy_lbl.setVisible(True)
            self.expectancy_val.setVisible(True)
            self.pf_lbl.setVisible(True)
            self.pf_val.setVisible(True)
        else:
            self.winrate_val.setText("")
            self.expectancy_val.setText("")
            self.pf_val.setText("")

            self.dot2.setVisible(False)
            self.dot3.setVisible(False)
            self.dot4.setVisible(False)
            self.winrate_lbl.setVisible(False)
            self.winrate_val.setVisible(False)
            self.expectancy_lbl.setVisible(False)
            self.expectancy_val.setVisible(False)
            self.pf_lbl.setVisible(False)
            self.pf_val.setVisible(False)

        self.total_val.setText(str(total))
        self.showing_val.setText(str(showing))

    def _table_card(self) -> QFrame:
        frame = card()  # Không truyền tiêu đề tĩnh để custom header layout
        frame.layout().setContentsMargins(12, 10, 12, 10)
        frame.layout().setSpacing(8)

        # Tạo custom header layout đưa nút Chi tiết lên cùng hàng với tiêu đề
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        title_label = QLabel("Danh sách nhật ký")
        title_label.setObjectName("PanelTitle")

        # Khởi tạo stats widget và nhúng trực tiếp vào header
        self.stats_widget = self._filtered_stats_bar()

        self.open_button = action_button("🔍 Chi tiết", primary=True, color="warning")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)

        self.sync_mt5_tab1_button = action_button("⬇️ Đồng bộ MT5", primary=True, color="info")
        self.sync_mt5_tab1_button.setToolTip("Nhập các lệnh đã đóng từ lịch sử MT5 trong 90 ngày gần nhất.")
        self.sync_mt5_tab1_button.clicked.connect(self._sync_mt5_history)
        self._sync_buttons.append(self.sync_mt5_tab1_button)

        header_layout.addWidget(title_label)
        header_layout.addSpacing(14)
        header_layout.addWidget(self.stats_widget)
        header_layout.addStretch(1)
        header_layout.addWidget(self.sync_mt5_tab1_button)
        header_layout.addWidget(self.open_button)

        frame.layout().addLayout(header_layout)

        self.table = QTableView()
        configure_table(self.table)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setModel(self.table_model)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.setMouseTracking(True)
        self.table.clicked.connect(self._table_clicked)
        self.table.doubleClicked.connect(self._table_double_clicked)
        self.table.entered.connect(self._table_entered)
        # Delegate cho cột Ghi chú (📝) và cột Xem
        note_col = next((i for i, (k, _) in enumerate(JournalTableModel.COLUMNS) if k == "note"), None)
        open_col = len(JournalTableModel.COLUMNS) - 1
        if note_col is not None:
            self.table.setItemDelegateForColumn(note_col, NoteIconDelegate(self.table))
        self.table.setItemDelegateForColumn(open_col, LinkDelegate(self.table))
        frame.layout().addWidget(self.table, 1)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("HelperText")
        self.empty_label.setWordWrap(True)
        frame.layout().addWidget(self.empty_label)

        return frame

    def _performance_card(self) -> QFrame:
        frame = card()
        frame.layout().setContentsMargins(14, 12, 14, 12)
        frame.layout().setSpacing(10)

        # ------------------------------------------------------------------
        # 1. Header Action Bar
        # ------------------------------------------------------------------
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 0, 0, 0)
        action_bar.setSpacing(10)

        tab_title = QLabel(
            compile_rich_html(
                'Thống kê hiệu suất giao dịch '
                '<span style="font-weight: normal; color: #E57373;">'
                '(Lần đồng bộ gần nhất: chưa đồng bộ)</span>'
            )
        )
        tab_title.setObjectName("PanelTitle")
        tab_title.setTextFormat(Qt.TextFormat.RichText)
        self.performance_title_label = tab_title

        action_bar.addWidget(tab_title, 1)

        explain_button = action_button("📖 Giải thích", primary=False)
        explain_button.clicked.connect(self._show_explanation_dialog)
        action_bar.addWidget(explain_button)

        refresh_button = action_button("🔄 Làm mới", primary=False)
        refresh_button.clicked.connect(self._refresh_performance)
        action_bar.addWidget(refresh_button)

        self.sync_mt5_button = action_button("⬇️ Đồng bộ MT5", primary=True, color="info")
        self.sync_mt5_button.setToolTip("Nhập các lệnh đã đóng từ lịch sử MT5 trong 90 ngày gần nhất.")
        self.sync_mt5_button.clicked.connect(self._sync_mt5_history)
        self._sync_buttons.append(self.sync_mt5_button)
        action_bar.addWidget(self.sync_mt5_button)

        frame.layout().addLayout(action_bar)

        # ------------------------------------------------------------------
        # 2. Sub-tabs Navigation Bar
        # ------------------------------------------------------------------
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setObjectName("PerformanceSubTabs")

        # ==================================================================
        # Sub-tab 1: 📊 Tổng quan & Biểu đồ
        # ==================================================================
        sub_tab1 = QWidget()
        sub_tab1_layout = QVBoxLayout(sub_tab1)
        sub_tab1_layout.setContentsMargins(4, 8, 4, 4)
        sub_tab1_layout.setSpacing(10)

        # KPI Cards Grid
        kpi_container = QVBoxLayout()
        kpi_container.setSpacing(10)

        group1_lbl = QLabel("🟢 TỔNG QUAN HIỆU SUẤT TÀI CHÍNH")
        group1_lbl.setObjectName("JournalSectionLabel")
        kpi_container.addWidget(group1_lbl)

        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(10)

        self.kpi_cards = {
            "net_amount": PerformanceKPICard("LÃI / LỖ RÒNG", self),
            "profit_factor": PerformanceKPICard("HỆ SỐ LỢI NHUẬN", self),
            "max_drawdown": PerformanceKPICard("DRAWDOWN TỐI ĐA", self),
            "expectancy": PerformanceKPICard("KỲ VỌNG (EXPECTANCY)", self),
            "total_r": PerformanceKPICard("TỔNG R NỔI BẬT", self),
            "closed_trades": PerformanceKPICard("LỆNH ĐÃ ĐÓNG", self),
            "win_rate": PerformanceKPICard("TỶ LỆ THẮNG", self),
            "avg_win": PerformanceKPICard("THẮNG TRUNG BÌNH", self),
            "avg_loss": PerformanceKPICard("THUA TRUNG BÌNH", self),
            "execution_quality": PerformanceKPICard("CL THỰC THI TB", self),
        }

        row1_layout.addWidget(self.kpi_cards["net_amount"])
        row1_layout.addWidget(self.kpi_cards["profit_factor"])
        row1_layout.addWidget(self.kpi_cards["max_drawdown"])
        row1_layout.addWidget(self.kpi_cards["expectancy"])
        row1_layout.addWidget(self.kpi_cards["total_r"])
        kpi_container.addLayout(row1_layout)

        group2_lbl = QLabel("🔵 THỐNG KÊ LỆNH & KỶ LUẬT THỰC THI")
        group2_lbl.setObjectName("JournalSectionLabel")
        group2_lbl.setProperty("spaced", True)
        kpi_container.addWidget(group2_lbl)

        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(10)
        row2_layout.addWidget(self.kpi_cards["closed_trades"])
        row2_layout.addWidget(self.kpi_cards["win_rate"])
        row2_layout.addWidget(self.kpi_cards["avg_win"])
        row2_layout.addWidget(self.kpi_cards["avg_loss"])
        row2_layout.addWidget(self.kpi_cards["execution_quality"])
        kpi_container.addLayout(row2_layout)

        sub_tab1_layout.addLayout(kpi_container)

        # Missing Result R Banner
        self.missing_r_banner = MissingRBanner(on_cta_clicked=self._on_fix_missing_r_clicked, parent=self)
        self.missing_r_banner.setVisible(False)
        sub_tab1_layout.addWidget(self.missing_r_banner)

        # Matplotlib Charts Panel
        self.performance_chart = PerformanceChartWidget(self)
        sub_tab1_layout.addWidget(self.performance_chart, 1)

        self.sub_tabs.addTab(sub_tab1, "📊 Tổng quan & Biểu đồ")

        # ==================================================================
        # Sub-tab 2: 📋 Chi tiết Lệnh & Nhóm
        # ==================================================================
        sub_tab2 = QWidget()
        sub_tab2_layout = QVBoxLayout(sub_tab2)
        sub_tab2_layout.setContentsMargins(4, 8, 4, 4)
        sub_tab2_layout.setSpacing(8)

        tables_layout = QHBoxLayout()
        tables_layout.setSpacing(10)

        # --- Left Box: Group Table ---
        left_box = QVBoxLayout()
        left_box.setSpacing(6)

        left_header = QHBoxLayout()
        left_header.setAlignment(Qt.AlignmentFlag.AlignLeft)
        left_header.setSpacing(8)
        left_title = QLabel("📑 Phân bổ nhóm:")
        left_title.setObjectName("JournalTableTitle")

        self.group_view_combo = QComboBox()
        self.group_view_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.group_view_combo.addItems(["Tất cả nhóm", "Theo Mã", "Theo Setup", "Theo Regime", "Theo Phiên", "Theo Hướng"])
        self.group_view_combo.setCurrentIndex(1)  # Default: Theo Mã
        self.group_view_combo.currentTextChanged.connect(self._on_group_view_changed)

        left_header.addWidget(left_title)
        left_header.addWidget(self.group_view_combo)
        left_header.addStretch(1)
        left_box.addLayout(left_header)

        self.performance_group_table = QTableWidget()
        configure_table(self.performance_group_table)
        self.performance_group_table.setColumnCount(7)
        self.performance_group_table.setHorizontalHeaderLabels(["Nhóm", "Tên", "Lệnh", "Thắng %", "Kỳ vọng R", "Tổng R", "P/L"])
        self.performance_group_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.performance_group_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.performance_group_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.performance_group_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.performance_group_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in range(2, 7):
            self.performance_group_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.performance_group_table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.performance_group_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.performance_group_table.itemClicked.connect(self._on_group_row_clicked)

        left_box.addWidget(self.performance_group_table, 1)
        tables_layout.addLayout(left_box, 1)

        # --- Right Box: Recent Trades Table with Filter Bar ---
        right_box = QVBoxLayout()
        right_box.setSpacing(6)

        right_header = QHBoxLayout()
        right_header.setAlignment(Qt.AlignmentFlag.AlignLeft)
        right_header.setSpacing(8)
        right_title = QLabel("📋 Lịch sử lệnh đóng")
        right_title.setObjectName("JournalTableTitle")
        right_header.addWidget(right_title)

        self.recent_time_combo = QComboBox()
        self.recent_time_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.recent_time_combo.addItems(["Tất cả thời gian", "7 ngày gần đây", "30 ngày gần đây", "90 ngày gần đây"])
        self.recent_time_combo.currentTextChanged.connect(self._apply_recent_table_filters)
        right_header.addWidget(self.recent_time_combo)

        self.recent_result_combo = QComboBox()
        self.recent_result_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.recent_result_combo.addItems(["Tất cả kết quả", "Lệnh thắng", "Lệnh thua", "Lệnh hòa"])
        self.recent_result_combo.currentTextChanged.connect(self._apply_recent_table_filters)
        right_header.addWidget(self.recent_result_combo)

        self.clear_cross_filter_btn = action_button("✖ Bỏ lọc mã", primary=False)
        self.clear_cross_filter_btn.setToolTip("Bỏ lọc mã hiện tại và xem tất cả lệnh đóng.")
        self.clear_cross_filter_btn.setVisible(False)
        self.clear_cross_filter_btn.clicked.connect(self._clear_cross_filter)
        right_header.addWidget(self.clear_cross_filter_btn)
        right_header.addStretch(1)

        right_box.addLayout(right_header)

        self.recent_trade_table = QTableWidget()
        configure_table(self.recent_trade_table)
        self.recent_trade_table.setColumnCount(6)
        self.recent_trade_table.setHorizontalHeaderLabels(["Đóng lúc", "Mã", "Hướng", "R", "P/L", "CL"])
        self.recent_trade_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_trade_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.recent_trade_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.recent_trade_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 5):
            self.recent_trade_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.recent_trade_table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.recent_trade_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        right_box.addWidget(self.recent_trade_table, 1)
        tables_layout.addLayout(right_box, 1)

        frame.layout().addLayout(tables_layout, 1)

        self.performance_empty_label = QLabel("")
        self.performance_empty_label.setObjectName("HelperText")
        self.performance_empty_label.setWordWrap(True)
        frame.layout().addWidget(self.performance_empty_label)

        return frame

    def _on_fix_missing_r_clicked(self) -> None:
        if hasattr(self, "tabs") and self.tabs:
            self.tabs.setCurrentIndex(0)
        idx = self.status_input.findData("closed")
        if idx >= 0:
            self.status_input.setCurrentIndex(idx)

    def _on_group_view_changed(self) -> None:
        if hasattr(self, "_cached_perf_data"):
            self._fill_group_table(self._cached_perf_data)

    def _on_group_row_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        group_item = self.performance_group_table.item(row, 0)
        label_item = self.performance_group_table.item(row, 1)
        if not group_item or not label_item:
            return

        group_name = group_item.text()
        symbol = label_item.text()

        if group_name == "Mã" and symbol and symbol != "--":
            if self._selected_symbol_filter == symbol:
                self._selected_symbol_filter = None
            else:
                self._selected_symbol_filter = symbol
            self._apply_recent_table_filters()

    def _clear_cross_filter(self) -> None:
        self._selected_symbol_filter = None
        self.performance_group_table.clearSelection()
        self._apply_recent_table_filters()

    def _show_explanation_dialog(self) -> None:
        dialog = MetricsExplanationDialog(self)
        dialog.exec()

    def refresh_status(self) -> None:
        self._refresh_symbol_filter()
        self._refresh_filter_values()
        self._apply_filters()

    def _refresh_symbol_filter(self) -> None:
        current = self.symbol_input.currentData()
        self.symbol_input.blockSignals(True)
        self.symbol_input.clear()
        self.symbol_input.addItem("Tất cả mã", None)
        for symbol in self.journal_controller.symbols():
            self.symbol_input.addItem(symbol, symbol)
        if current:
            index = self.symbol_input.findData(current)
            if index >= 0:
                self.symbol_input.setCurrentIndex(index)
        self.symbol_input.blockSignals(False)

    def _refresh_filter_values(self) -> None:
        """Nạp danh sách giá trị distinct cho các combobox session/setup/execution_regime."""
        for combo, column in [
            (self.session_input, "session"),
            (self.setup_input, "setup_type"),
            (self.regime_input, "execution_regime"),
        ]:
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(f"Tất cả {self._filter_label(column)}", None)
            for value in self.journal_controller.distinct_values(column):
                combo.addItem(str(value), str(value))
            if current:
                index = combo.findData(current)
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.blockSignals(False)

    @staticmethod
    def _filter_label(column: str) -> str:
        return {"session": "phiên", "setup_type": "setup", "execution_regime": "execution_regime"}.get(column, column)

    def _apply_filters(self) -> None:
        search_text = self.search_input.text().strip() or None
        filters = JournalFilter(
            date_from=self.date_from_input.date().toString("yyyy-MM-dd"),
            date_to=self.date_to_input.date().toString("yyyy-MM-dd"),
            symbol=self.symbol_input.currentData(),
            decision=decision_value(self.decision_input.currentText()),
            permission=permission_value(self.permission_input.currentText()),
            min_score=int(self.min_score_input.value()),
            search_text=search_text,
            trade_status=self.status_input.currentData(),
            result=self.result_input.currentData(),
            min_execution_quality=int(self.min_quality_input.value()),
            max_execution_quality=self._current_max_quality(),
            session=self.session_input.currentData(),
            setup_type=self.setup_input.currentData(),
            execution_regime=self.regime_input.currentData(),
        )
        entries = self.journal_controller.list_entries(filters)
        self.table_model.set_entries(entries)
        self.empty_label.setText("" if entries else "Chưa có bản ghi phù hợp bộ lọc.")
        self.open_button.setEnabled(False)
        QTimer.singleShot(0, self._recalculate_column_widths)
        self._update_filtered_stats_bar(entries)
        self._refresh_stats()
        if self.tabs and self.tabs.currentIndex() == 1:
            self._refresh_performance()

    def _clear_filters(self) -> None:
        # Reset Quick Filter buttons
        for btn in self._quick_btns.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        # Reset Advanced Filter widgets
        self.search_input.clear()
        self.date_from_input.setDate(QDate.currentDate().addYears(-10))
        self.date_to_input.setDate(QDate.currentDate())
        self.symbol_input.setCurrentIndex(0)
        self.status_input.setCurrentIndex(0)
        self.result_input.setCurrentIndex(0)
        self.session_input.setCurrentIndex(0)
        self.decision_input.setCurrentIndex(0)
        self.permission_input.setCurrentIndex(0)
        self.setup_input.setCurrentIndex(0)
        self.regime_input.setCurrentIndex(0)
        self.min_score_input.setValue(0)
        self.min_quality_input.setValue(0)
        self._apply_filters()

    def _refresh_stats(self) -> None:
        stats = self.journal_controller.stats()
        values = {
            "Tổng": stats.get("total", 0),
            "Sẵn sàng": stats.get("ready", 0),
            "Theo dõi": stats.get("watch", 0),
            "Chờ": stats.get("wait", 0),
            "Đứng ngoài": stats.get("stand_aside", 0),
            "Mã nhiều nhất": stats.get("top_symbol", "--"),
        }
        for title, label in self.stat_labels.items():
            label.setText(str(values.get(title, "--")))

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._refresh_performance()

    def _refresh_performance(self) -> None:
        data = self.journal_controller.performance_summary()
        self._cached_perf_data = data
        summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}

        closed_trades = int(summary.get("closed_trades", 0) or 0)
        r_trades = int(summary.get("r_trades", 0) or 0)
        net_amount = summary.get("net_amount")
        profit_factor = summary.get("profit_factor")
        max_dd = summary.get("max_drawdown_r")
        expectancy = summary.get("expectancy_r")
        total_r = summary.get("total_r")
        win_rate = summary.get("win_rate")
        avg_win = summary.get("average_win_r")
        avg_loss = summary.get("average_loss_r")
        avg_quality = summary.get("average_execution_quality")

        # 1. Lãi/Lỗ ròng
        net_val = format_metric(net_amount)
        if net_amount is not None and isinstance(net_amount, (int, float)):
            net_state = "positive" if net_amount > 0 else "negative" if net_amount < 0 else "neutral"
            net_sub = "Lời ròng thực tế" if net_amount > 0 else "Thua lỗ ròng" if net_amount < 0 else "Hòa vốn"
            net_badge = "▲" if net_amount > 0 else "▼" if net_amount < 0 else ""
        else:
            net_val = "0.00"
            net_state = "neutral"
            net_sub = "Chưa có lệnh"
            net_badge = ""
        self.kpi_cards["net_amount"].set_data(
            f"${net_val}" if not net_val.startswith("-") else f"-${net_val[1:]}", net_state, net_sub, net_badge
        )

        # 2. Profit Factor
        pf_val = format_metric(profit_factor)
        if profit_factor is not None and isinstance(profit_factor, (int, float)):
            pf_state = "positive" if profit_factor >= 1.5 else "warning" if profit_factor >= 1.0 else "negative"
            pf_sub = "Hiệu quả cao (≥1.5)" if profit_factor >= 1.5 else "Sinh lời (≥1.0)" if profit_factor >= 1.0 else "Thua lỗ (<1.0)"
            pf_badge = "🟢" if profit_factor >= 1.5 else "🟠" if profit_factor >= 1.0 else "⚠️"
        else:
            pf_val = "--"
            pf_state = "muted"
            pf_sub = "Chưa thể tính"
            pf_badge = ""
        self.kpi_cards["profit_factor"].set_data(pf_val, pf_state, pf_sub, pf_badge)

        # 3. Max Drawdown
        dd_val = format_metric(max_dd, "R")
        if max_dd is not None and isinstance(max_dd, (int, float)):
            dd_state = "negative" if max_dd < -5 else "warning" if max_dd < 0 else "neutral"
            dd_sub = "Sụt giảm đỉnh-đáy"
            dd_badge = "📉"
        else:
            dd_val = "--"
            dd_state = "muted"
            dd_sub = "Chưa có dữ liệu R"
            dd_badge = ""
        self.kpi_cards["max_drawdown"].set_data(dd_val, dd_state, dd_sub, dd_badge)

        # 4. Expectancy
        exp_val = format_metric(expectancy, "R")
        if expectancy is not None and isinstance(expectancy, (int, float)) and r_trades > 0:
            exp_state = "positive" if expectancy > 0 else "negative" if expectancy < 0 else "neutral"
            exp_sub = "Lợi thế kỳ vọng / lệnh"
            exp_badge = "📈" if expectancy > 0 else "📉"
        else:
            exp_val = "0R" if closed_trades > 0 else "--"
            exp_state = "muted"
            exp_sub = "Cần dữ liệu Result R"
            exp_badge = "❓"
        self.kpi_cards["expectancy"].set_data(exp_val, exp_state, exp_sub, exp_badge)

        # 5. Tổng R
        tr_val = format_metric(total_r, "R")
        if total_r is not None and isinstance(total_r, (int, float)) and r_trades > 0:
            tr_state = "positive" if total_r > 0 else "negative" if total_r < 0 else "neutral"
            tr_sub = "Tổng đơn vị R tích lũy"
            tr_badge = "🎯"
        else:
            tr_val = "0R" if closed_trades > 0 else "--"
            tr_state = "muted"
            tr_sub = "Cần dữ liệu Result R"
            tr_badge = "❓"
        self.kpi_cards["total_r"].set_data(tr_val, tr_state, tr_sub, tr_badge)

        # 6. Đã đóng
        self.kpi_cards["closed_trades"].set_data(
            str(closed_trades),
            "neutral" if closed_trades > 0 else "muted",
            f"{r_trades}/{closed_trades} lệnh có Result R",
            "📋",
        )

        # 7. Win rate
        wr_val = format_metric(win_rate, "%")
        if win_rate is not None and isinstance(win_rate, (int, float)):
            wr_state = "positive" if win_rate >= 50 else "warning" if win_rate >= 40 else "negative"
            wr_sub = "Tỷ lệ lệnh chiến thắng"
            wr_badge = "⚠️" if win_rate < 40 else ""
        else:
            wr_val = "0%"
            wr_state = "muted"
            wr_sub = "Chưa có lệnh"
            wr_badge = ""
        self.kpi_cards["win_rate"].set_data(wr_val, wr_state, wr_sub, wr_badge)

        # 8. Avg Win
        aw_val = format_metric(avg_win, "R")
        aw_state = "positive" if avg_win and float(avg_win) > 0 else "muted"
        self.kpi_cards["avg_win"].set_data(aw_val if r_trades > 0 else "0R", aw_state, "R trung bình khi thắng", "📈")

        # 9. Avg Loss
        al_val = format_metric(avg_loss, "R")
        al_state = "negative" if avg_loss and float(avg_loss) < 0 else "muted"
        self.kpi_cards["avg_loss"].set_data(al_val if r_trades > 0 else "0R", al_state, "R trung bình khi thua", "📉")

        # 10. Execution Quality
        eq_val = format_metric(avg_quality)
        if avg_quality is not None and isinstance(avg_quality, (int, float)):
            eq_state = "positive" if avg_quality >= 70 else "warning" if avg_quality >= 50 else "negative"
            eq_sub = "Điểm kỷ luật thực thi"
            eq_badge = "🎯"
        else:
            eq_val = "--"
            eq_state = "muted"
            eq_sub = "Chưa có đánh giá"
            eq_badge = ""
        self.kpi_cards["execution_quality"].set_data(eq_val, eq_state, eq_sub, eq_badge)

        # 2. Update Banner Alert
        missing_count = closed_trades - r_trades
        self.missing_r_banner.set_missing_info(missing_count, closed_trades)

        # 3. Update Group Table & Recent Trades Table & Charts
        self._fill_group_table(data)
        self._apply_recent_table_filters()

    def _fill_group_table(self, data: dict[str, object]) -> None:
        view = self.group_view_combo.currentText()
        key_map = {
            "Theo Mã": ("by_symbol", "Mã"),
            "Theo Setup": ("by_setup", "Setup"),
            "Theo Regime": ("by_regime", "Regime"),
            "Theo Phiên": ("by_session", "Phiên"),
            "Theo Hướng": ("by_direction", "Hướng"),
        }

        rows: list[tuple[str, dict[str, object]]] = []
        if view == "Tất cả nhóm":
            for group_key, title in key_map.values():
                group_rows = data.get(group_key, [])
                if isinstance(group_rows, list):
                    for row in group_rows:
                        if isinstance(row, dict):
                            rows.append((title, row))
        else:
            group_key, title = key_map.get(view, ("by_symbol", "Mã"))
            group_rows = data.get(group_key, [])
            if isinstance(group_rows, list):
                for row in group_rows:
                    if isinstance(row, dict):
                        rows.append((title, row))

        self.performance_group_table.setRowCount(len(rows))
        for row_index, (group, row) in enumerate(rows):
            values = [
                group,
                row.get("label", "--"),
                row.get("trades", 0),
                format_metric(row.get("win_rate"), "%"),
                format_metric(row.get("expectancy_r"), "R"),
                format_metric(row.get("total_r"), "R"),
                format_metric(row.get("net_amount")),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column >= 2:
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                if column in {4, 5, 6}:
                    color_item_by_number(item, str(value))
                self.performance_group_table.setItem(row_index, column, item)

    def _apply_recent_table_filters(self) -> None:
        # Khi có filter theo symbol: query trực tiếp toàn bộ lệnh đóng của mã đó
        # thay vì dùng "recent" từ cache (vốn bị giới hạn số lượng)
        if self._selected_symbol_filter:
            clean_rows = self.journal_controller.closed_trades_by_symbol(self._selected_symbol_filter)
            self.clear_cross_filter_btn.setText(f"✖ Xóa lọc [{self._selected_symbol_filter}]")
            self.clear_cross_filter_btn.setVisible(True)
        else:
            if not hasattr(self, "_cached_perf_data"):
                return
            data = self._cached_perf_data
            recent = data.get("recent", []) if isinstance(data.get("recent"), list) else []
            clean_rows = [row for row in recent if isinstance(row, dict)]
            self.clear_cross_filter_btn.setVisible(False)

        # Filter 2: Result combo
        res_filter = self.recent_result_combo.currentText()
        if res_filter == "Lệnh thắng":
            clean_rows = [r for r in clean_rows if float(r.get("result_amount") or 0) > 0 or float(r.get("result_r") or 0) > 0]
        elif res_filter == "Lệnh thua":
            clean_rows = [r for r in clean_rows if float(r.get("result_amount") or 0) < 0 or float(r.get("result_r") or 0) < 0]
        elif res_filter == "Lệnh hòa":
            clean_rows = [
                r for r in clean_rows if float(r.get("result_amount") or 0) == 0 and float(r.get("result_r") or 0) == 0
            ]

        # Filter 3: Time combo
        time_filter = self.recent_time_combo.currentText()
        if time_filter != "Tất cả thời gian" and clean_rows:
            days = 7 if "7" in time_filter else 30 if "30" in time_filter else 90
            cutoff = datetime.now() - timedelta(days=days)
            filtered_by_time = []
            for r in clean_rows:
                closed_at = r.get("closed_at")
                if closed_at:
                    try:
                        dt = datetime.fromisoformat(str(closed_at).replace("Z", "+00:00")).replace(tzinfo=None)
                        if dt >= cutoff:
                            filtered_by_time.append(r)
                    except ValueError:
                        filtered_by_time.append(r)
                else:
                    filtered_by_time.append(r)
            clean_rows = filtered_by_time

        self._fill_recent_trade_table(clean_rows)

        # Draw Matplotlib Charts
        data = self._cached_perf_data if hasattr(self, "_cached_perf_data") else {}
        by_symbol = data.get("by_symbol", []) if isinstance(data.get("by_symbol"), list) else []
        self.performance_chart.update_charts(by_symbol, clean_rows, selected_symbol=self._selected_symbol_filter)

    def _fill_recent_trade_table(self, rows: list[object]) -> None:
        clean_rows = [row for row in rows if isinstance(row, dict)]
        self.recent_trade_table.setRowCount(len(clean_rows))
        for row_index, row in enumerate(clean_rows):
            r_val = row.get("result_r")
            amt_val = row.get("result_amount")

            r_str = format_metric(r_val, "R")
            if r_val is not None and isinstance(r_val, (int, float)):
                if r_val > 0:
                    r_str = f"↑ +{r_str}"
                elif r_val < 0:
                    r_str = f"↓ {r_str}"

            amt_str = format_metric(amt_val)
            if amt_val is not None and isinstance(amt_val, (int, float)):
                if amt_val > 0:
                    amt_str = f"↑ +${amt_str}"
                elif amt_val < 0:
                    amt_str = f"↓ -${amt_str[1:] if amt_str.startswith('-') else amt_str}"

            direction_raw = str(row.get("direction") or "--").strip()
            direction_lower = direction_raw.lower()
            if "buy" in direction_lower or direction_lower == "long" or direction_raw == "↑":
                direction_str = "BUY"
            elif "sell" in direction_lower or direction_lower == "short" or direction_raw == "↓":
                direction_str = "SELL"
            else:
                direction_str = direction_raw

            values = [
                format_time(str(row.get("closed_at") or "")),
                row.get("symbol", "--"),
                direction_str,
                r_str,
                amt_str,
                row.get("execution_quality_score") if row.get("execution_quality_score") is not None else "--",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in {2, 3, 5}:
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                if column in {2, 3, 4}:
                    color_item_by_number(item, str(value))
                self.recent_trade_table.setItem(row_index, column, item)

    def _sync_mt5_history(self) -> None:
        for btn in self._sync_buttons:
            btn.setEnabled(False)
            btn.setText("Đang đồng bộ...")
        try:
            result = self.journal_controller.sync_mt5_history(days=90)
        except Exception as exc:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Đồng bộ MT5 thất bại")
            msg_box.setText(str(exc))
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.addButton(action_button("❌ Đóng"), QMessageBox.ButtonRole.AcceptRole)
            msg_box.exec()
            return
        finally:
            for btn in self._sync_buttons:
                btn.setText("Đồng bộ MT5")
                btn.setEnabled(True)
        self.refresh_status()
        self.performance_title_label.setText(
            compile_rich_html(
                'Thống kê hiệu suất giao dịch '
                '<span style="font-weight: normal; color: #5C8DBC;">'
                f'(Lần đồng bộ gần nhất: nhận {result.get("received", 0)}, tạo mới {result.get("created", 0)}, cập nhật {result.get("updated", 0)}, bỏ qua {result.get("skipped", 0)})'
                '</span>'
            )
        )
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Đồng bộ MT5 hoàn tất")
        msg_box.setText(
            f"Nhận: {result.get('received', 0)}\n"
            f"Tạo mới: {result.get('created', 0)}\n"
            f"Cập nhật: {result.get('updated', 0)}\n"
            f"Bỏ qua: {result.get('skipped', 0)}\n"
            f"Lỗi: {len(result.get('errors', [])) if isinstance(result.get('errors'), list) else 0}"
        )
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.addButton(action_button("❌ Đóng"), QMessageBox.ButtonRole.AcceptRole)
        msg_box.exec()

    def _table_clicked(self, index: QModelIndex) -> None:
        self.open_button.setEnabled(index.isValid())
        col = index.column()
        col_key = JournalTableModel.COLUMNS[col][0] if index.isValid() else ""
        # Cột Ghi chú (💬): mở NotePopup
        if col_key == "note":
            entry = self.table_model.entry_at(index.row())
            if entry and entry.note:
                rect = self.table.visualRect(index)
                global_pos = self.table.viewport().mapToGlobal(rect.bottomLeft())
                NotePopup.show_at(entry.note, global_pos, self)
                return
        if index.column() == len(JournalTableModel.COLUMNS) - 1:
            self._open_row(index.row())

    def _table_double_clicked(self, index: QModelIndex) -> None:
        if index.isValid():
            self._open_row(index.row())

    def _table_entered(self, index: QModelIndex) -> None:
        col_key = JournalTableModel.COLUMNS[index.column()][0] if index.isValid() else ""
        if col_key != "note":
            NotePopup.close_active()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'table'):
            self._recalculate_column_widths()

    def refresh_theme_styles(self) -> None:
        """Forward hot theme changes to the embedded Matplotlib chart."""

        if hasattr(self, "performance_chart"):
            self.performance_chart.refresh_theme_styles()

    # ------------------------------------------------------------------
    # Column width — Weight-based proportional distribution (khong Stretch)
    # ------------------------------------------------------------------

    # (col_index, min_width, stretch_weight)
    _COLUMN_WEIGHTS: list[tuple[int, int, int]] = [
        (0, 140, 0),   # Thoi gian  ← dd/mm/yyyy hh:mm
        (1,  90, 0),   # Ma         ← XXX/YYY
        (2, 150, 3),   # Setup      ← uu tien noi dung ky thuat dai
        (3, 130, 2),   # Regime     ← uu tien noi dung ky thuat dai
        (4, 120, 1),   # Trang thai
        (5, 130, 1),   # Thien huong
        (6,  55, 0),   # R
        (7, 120, 1),   # Loi nhuan
        (8, 130, 1),   # CL Thuc thi
        (9, 104, 0),   # Ghi chu    ← du tieu de, noi dung la icon popup
        (10, 90, 0),   # Chi tiet
    ]

    def _recalculate_column_widths(self) -> None:
        """Phan bo do rong cot theo trong so, khong dung Stretch cua Qt.

        - Tat ca cot deu Interactive → user co the keo chinh neu muon.
        - min_width = max(hardcoded_min, sectionSizeHint) → dam bao header
          khong bi cat chu. sectionSizeHint tu Qt da bao gom QSS padding,
          font weight, sort indicator.
        - Phan du viewport duoc chia theo ty le weight cho cac cot weight > 0.
        - Neu viewport qua nho → giu min_width, bang co thanh cuon ngang.
        """
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(35)
        header.setStretchLastSection(False)

        for col in range(len(JournalTableModel.COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        viewport_w = self.table.viewport().width()
        if viewport_w < 50:
            return  # viewport chua san sang

        # Dung sectionSizeHint cua Qt — da bao gom QSS padding, font bold, sort icon
        effective: list[tuple[int, int, int]] = []
        for idx, hard_min, weight in self._COLUMN_WEIGHTS:
            hint = header.sectionSizeHint(idx)
            minimum = (
                hard_min
                if JournalTableModel.COLUMNS[idx][0] == "note"
                else max(hard_min, hint)
            )
            effective.append((idx, minimum, weight))

        total_min = sum(mw for _, mw, _ in effective)
        total_weight = sum(w for _, _, w in effective)

        if viewport_w <= total_min or total_weight == 0:
            # Man hinh qua nho → dung min_width, de thanh cuon ngang
            for idx, min_w, _ in effective:
                self.table.setColumnWidth(idx, min_w)
            return

        extra = viewport_w - total_min
        widths: dict[int, int] = {}

        for idx, min_w, weight in effective:
            w = min_w
            if weight > 0:
                w += (extra * weight) // total_weight
            widths[idx] = w

        # Phan du con sot lai (do chia nguyen) → don vao cot co weight cao nhat cuoi cung
        allocated = sum(widths.values())
        diff = viewport_w - allocated
        if diff > 0:
            stretchable = [(idx, wgt) for idx, _, wgt in effective if wgt > 0]
            if stretchable:
                stretchable.sort(key=lambda x: x[1])
                widths[stretchable[-1][0]] += diff

        for idx, w in widths.items():
            self.table.setColumnWidth(idx, w)

    def _open_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if selected:
            self._open_row(selected[0].row())

    def _open_row(self, row_index: int) -> None:
        entry = self.table_model.entry_at(row_index)
        if entry and self.navigate:
            self.navigate("journal_detail", {"journal_id": entry.id})

    def _compact_field(self, label: str, field: QWidget) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label_widget = QLabel(label)
        label_widget.setObjectName("FormLabel")
        label_widget.setMinimumWidth(90)
        layout.addWidget(label_widget)
        layout.addWidget(field, 1)
        return widget

    def _compact_metric(self, title: str, val: str, is_stat: bool = False) -> QWidget:
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(6)
        t = QLabel(f"{title}:")
        t.setObjectName("FormLabel")
        v = QLabel(val)
        v.setObjectName("MiniStatValue")
        if is_stat:
            self.stat_labels[title] = v
        else:
            self.performance_labels[title] = v
        l.addWidget(t)
        l.addWidget(v)
        l.addStretch(1)
        return w


class MetricsExplanationDialog(QDialog):
    HELP_ROWS = [
        ("Đã đóng", "Tổng số lệnh giao dịch đã kết thúc và có kết quả cuối cùng.", "Xem tổng số lệnh để biết độ lớn mẫu thống kê."),
        ("Tỷ lệ thắng (Win rate)", "Tỉ lệ phần trăm các lệnh mang lại lợi nhuận.", "Cần kết hợp với Kỳ vọng. Winrate < 40% vẫn có lời nếu R:R > 2.0."),
        ("Kỳ vọng (Expectancy)", "Số R trung bình kiếm được trên MỖI LỆNH đặt cọc.", "Expectancy > 0.25R cho thấy hệ thống có lợi thế toán học tốt."),
        ("Tổng R", "Tổng lợi nhuận quy đổi ra đơn vị Rủi ro (R).", "Thước đo chuẩn xác nhất về hiệu suất độc lập với quy mô vốn."),
        ("Lãi/lỗ ròng (Net P/L)", "Tổng số tiền lợi nhuận hoặc thua lỗ thực tế thu về.", "Số tiền thực tế cộng/trừ vào tài khoản ($)."),
        ("Hệ số lợi nhuận (Profit Factor)", "Tỉ lệ giữa tổng số tiền kiếm được và tổng số tiền thua lỗ.", "PF > 1.5 là chiến lược vững mạnh, < 1.0 là đang thua lỗ."),
        ("DD tối đa (Max Drawdown)", "Chuỗi sụt giảm tài khoản sâu nhất từ mức đỉnh vốn.", "Đánh giá rủi ro hệ thống. Nên hạ % Risk khi DD > 15R."),
        ("Thắng TB / Thua TB", "Số R trung bình khi thắng và số R trung bình khi thua.", "Tỉ lệ Reward/Risk thực tế đạt được."),
        ("Chất lượng thực thi (CL)", "Điểm số kỷ luật tuân thủ Stoploss, TakeProfit và kế hoạch.", "CL >= 80 là kỷ luật tốt, < 60 là vi phạm nguyên tắc."),
        ("Nhóm / Tên", "Tiêu chí dùng để phân loại và gom nhóm dữ liệu.", "Gom theo Mã giao dịch, Setup, Regime, Phiên..."),
        ("Đóng lúc", "Thời gian thực tế lệnh giao dịch được thanh lý.", "Định dạng: Ngày/tháng/năm Giờ:phút."),
        ("R / P/L", "Kết quả cuối cùng của lệnh tính theo tỉ lệ R và tiền mặt ($).", "Kèm ký hiệu ▲ lệnh thắng, ▼ lệnh thua."),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Giải thích các chỉ số hiệu suất")
        self.setObjectName("ScannerHelpDialog")
        self.setModal(True)
        self.setMinimumSize(880, 560)
        self.resize(920, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        intro = QLabel("Dialog này giải thích ý nghĩa các chỉ số thống kê hiệu suất giao dịch và các cột dữ liệu trong Bảng phân bổ & Lịch sử lệnh.")
        intro.setObjectName("HelperText")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(len(self.HELP_ROWS), 3)
        configure_table(self.table)
        self.table.setHorizontalHeaderLabels(["Chỉ số / Cột", "Ý nghĩa & Ứng dụng", "Mẹo & Hướng dẫn cho Trader"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        for row, values in enumerate(self.HELP_ROWS):
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row, column, item)

        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 340)

        layout.addWidget(self.table, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        close_btn = action_button("❌ Đóng")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)


def decision_value(text: str) -> str | None:
    return {"Sẵn sàng": "ready", "Theo dõi": "watch", "Chờ": "wait_for_confirmation", "Đứng ngoài": "stand_aside"}.get(text)


def permission_value(text: str) -> str | None:
    return {"Được phép": "allowed", "Cẩn trọng": "caution", "Bị chặn": "blocked"}.get(text)


def format_time(value: str) -> str:
    if not value or value == "--":
        return "--"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
        return parsed.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value


def format_metric(value: object, suffix: str = "") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def color_item_by_number(item: QTableWidgetItem, value: str) -> None:
    palette = current_palette()
    val_str = str(value).upper()
    if "↑" in val_str or "▲" in val_str or "BUY" in val_str or "LONG" in val_str:
        item.setForeground(QColor(palette.buy))
        return
    if "↓" in val_str or "▼" in val_str or "SELL" in val_str or "SHORT" in val_str:
        item.setForeground(QColor(palette.sell))
        return

    clean_text = (
        val_str.replace("R", "")
        .replace("%", "")
        .replace("$", "")
        .replace("+", "")
        .replace("▲", "")
        .replace("▼", "")
        .replace("↑", "")
        .replace("↓", "")
        .strip()
    )
    try:
        number = float(clean_text)
    except ValueError:
        return

    if number > 0:
        item.setForeground(QColor(palette.success))
    elif number < 0:
        item.setForeground(QColor(palette.danger))
