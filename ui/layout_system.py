from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QDialog,
    QGridLayout,
    QLabel,
    QLayout,
    QProgressBar,
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

    CONTROL_HEIGHT = 32
    PROGRESS_HEIGHT = 20
    HELP_SIZE = 24
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
    widget.setFixedHeight(LayoutTokens.CONTROL_HEIGHT)
    if width is not None:
        widget.setFixedWidth(width)
    widget.setSizePolicy(horizontal_policy, QSizePolicy.Policy.Fixed)


def configure_form_label(
    label: QLabel,
    *,
    width: int = LayoutTokens.FORM_LABEL_WIDTH,
) -> None:
    label.setFixedSize(width, LayoutTokens.CONTROL_HEIGHT)
    label.setAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def configure_button(button: QAbstractButton) -> None:
    button.setFixedHeight(LayoutTokens.CONTROL_HEIGHT)
    button.setIconSize(QSize(LayoutTokens.ICON_SIZE, LayoutTokens.ICON_SIZE))
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def configure_checkbox(checkbox: QCheckBox) -> None:
    checkbox.setFixedHeight(LayoutTokens.CONTROL_HEIGHT)
    checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def configure_help_button(button: QAbstractButton) -> None:
    button.setFixedSize(LayoutTokens.HELP_SIZE, LayoutTokens.HELP_SIZE)
    button.setIconSize(QSize(LayoutTokens.ICON_SIZE, LayoutTokens.ICON_SIZE))


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
    horizontal = table.horizontalHeader()
    horizontal.setFixedHeight(LayoutTokens.TABLE_HEADER_HEIGHT)
    horizontal.setMinimumSectionSize(LayoutTokens.SPACE_6)
    vertical = table.verticalHeader()
    vertical.setDefaultSectionSize(LayoutTokens.TABLE_ROW_HEIGHT)
    vertical.setMinimumSectionSize(LayoutTokens.TABLE_ROW_HEIGHT)
