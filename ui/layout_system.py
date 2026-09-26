from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QLayout,
    QProgressBar,
    QHeaderView,
    QScrollArea,
    QSizePolicy,
    QTableView,
    QWidget,
)


class LayoutTokens:
    """Shared 4 px grid used by application tool screens and dialogs."""

    SPACE_1 = 4
    SPACE_2 = 8
    SPACE_3 = 12
    SPACE_4 = 16
    SPACE_6 = 24

    PAGE_MARGIN = SPACE_3
    CARD_MARGIN = SPACE_3
    DIALOG_MARGIN = SPACE_4

    PROGRESS_HEIGHT = 20
    ICON_SIZE = 16

    FIELD_SM = 96
    FIELD_NUMERIC_SM = 112
    FIELD_MD = 160
    FIELD_DATE = 168
    FIELD_NUMERIC_LG = 192
    FIELD_LG = 200
    FIELD_XL = 240

    TOOLBAR_LABEL_WIDTH = 72
    FORM_LABEL_WIDTH = 112
    SETTINGS_LABEL_WIDTH = 132
    SETTINGS_FIELD_WIDTH = 220
    TABLE_HEADER_HEIGHT = 32
    TABLE_ROW_HEIGHT = 36
    CHART_MIN_HEIGHT = 240

    DIALOG_SM_WIDTH = 420
    DIALOG_MD_WIDTH = 800
    DIALOG_MD_HEIGHT = 600
    DIALOG_LG_WIDTH = 840


def configure_layout(
    layout: QLayout,
    *,
    margins: int | tuple[int, int, int, int] = 0,
    spacing: int = LayoutTokens.SPACE_2,
) -> None:
    if isinstance(margins, int):
        layout.setContentsMargins(margins, margins, margins, margins)
    else:
        layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)


def configure_dialog(
    dialog: QDialog,
    *,
    minimum_width: int,
    minimum_height: int,
) -> None:
    dialog.setMinimumSize(minimum_width, minimum_height)
    dialog.setSizeGripEnabled(True)


DIALOG_CHROME_HEIGHT = 160
DIALOG_BODY_FLOOR = 240


class DialogBodyScroll(QScrollArea):
    """Vùng cuộn cho thân dialog: cao theo nội dung nhưng không vượt vùng làm việc.

    Nhờ ``sizeHint`` tự kẹp theo ``QScreen.availableGeometry()`` (logical pixel),
    dialog tự mở đủ cao để thấy trọn nội dung khi màn hình cho phép và tự thu lại
    khi màn hình thấp — phần thân còn lại do thanh cuộn xử lý, nên hàng nút nằm
    ngoài vùng cuộn luôn trong tầm nhìn. Không dùng setFixedHeight/setMinimumHeight
    nên không vi phạm contract density của style guide.
    """

    def __init__(
        self,
        *,
        floor: int = DIALOG_BODY_FLOOR,
        chrome: int = DIALOG_CHROME_HEIGHT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._floor = floor
        self._chrome = chrome
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _available_height(self) -> int:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return 0
        return screen.availableGeometry().height()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        inner = self.widget()
        content = inner.sizeHint().height() if inner is not None else 0
        height = dialog_body_height(
            content + self.frameWidth() * 2, self._available_height(), floor=self._floor
        )
        return QSize(hint.width(), height)

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        height = min(self._floor, hint.height()) if hint.height() > 0 else self._floor
        return QSize(hint.width(), height)


def dialog_body_height(
    desired: int,
    available_height: int,
    *,
    chrome: int = DIALOG_CHROME_HEIGHT,
    floor: int = DIALOG_BODY_FLOOR,
) -> int:
    """Chiều cao thân dialog để hàng nút luôn nằm trong vùng làm việc.

    Trả về chiều cao mong muốn khi màn hình đủ chỗ, và kẹp lại theo
    ``available_height`` (logical pixel từ ``QScreen.availableGeometry()``) khi
    không — phần thân còn lại do vùng cuộn của dialog xử lý. Hàm thuần để đo
    được ở mọi kích thước màn hình, không phụ thuộc màn hình thật.
    """

    if desired < floor:
        return desired
    if available_height <= 0:
        return desired
    return max(floor, min(desired, available_height - chrome))


def configure_form_grid(
    layout: QGridLayout,
    *,
    label_columns: tuple[int, ...] = (0,),
    label_width: int = LayoutTokens.FORM_LABEL_WIDTH,
) -> None:
    configure_layout(layout, spacing=LayoutTokens.SPACE_2)
    layout.setHorizontalSpacing(LayoutTokens.SPACE_3)
    layout.setVerticalSpacing(LayoutTokens.SPACE_2)
    for column in label_columns:
        layout.setColumnMinimumWidth(column, label_width)


def configure_control(
    widget: QWidget,
    *,
    width: int | None = None,
    horizontal_policy: QSizePolicy.Policy = QSizePolicy.Policy.Fixed,
) -> None:
    if width is not None:
        widget.setFixedWidth(width)
    widget.setSizePolicy(horizontal_policy, QSizePolicy.Policy.Fixed)


def configure_form_label(
    label: QLabel,
    *,
    width: int = LayoutTokens.FORM_LABEL_WIDTH,
) -> None:
    label.setFixedWidth(width)
    label.setAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def configure_button(button: QAbstractButton) -> None:
    button.setIconSize(QSize(LayoutTokens.ICON_SIZE, LayoutTokens.ICON_SIZE))
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def configure_checkbox(checkbox: QCheckBox) -> None:
    checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def configure_help_button(button: QAbstractButton) -> None:
    button.setIconSize(QSize(LayoutTokens.ICON_SIZE, LayoutTokens.ICON_SIZE))
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def configure_progress(
    progress: QProgressBar,
    *,
    minimum_width: int = LayoutTokens.FIELD_LG,
) -> None:
    progress.setFixedHeight(LayoutTokens.PROGRESS_HEIGHT)
    progress.setMinimumWidth(minimum_width)
    progress.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )


def configure_table(table: QTableView) -> None:
    table.setObjectName("EconTable")
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)
    table.setWordWrap(True)

    horizontal = table.horizontalHeader()
    horizontal.setMinimumSectionSize(LayoutTokens.SPACE_6)
    horizontal.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    horizontal.setHighlightSections(False)

    vertical = table.verticalHeader()
    vertical.setVisible(False)
    vertical.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
