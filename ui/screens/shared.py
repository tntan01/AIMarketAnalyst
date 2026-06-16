from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def page_header(title: str, subtitle: str = "", badge: str | None = None) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(14)

    text_box = QVBoxLayout()
    text_box.setSpacing(4)
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    text_box.addWidget(title_label)
    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubtitle")
        subtitle_label.setWordWrap(True)
        text_box.addWidget(subtitle_label)

    layout.addLayout(text_box, 1)
    if badge:
        badge_label = QLabel(badge)
        badge_label.setObjectName("HeaderBadge")
        badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge_label)
    return widget


def card(title: str | None = None, object_name: str = "PanelCard") -> QFrame:
    frame = QFrame()
    frame.setObjectName(object_name)
    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    if title:
        label = QLabel(title)
        label.setObjectName("PanelTitle")
        layout.addWidget(label)
    return frame


def labeled_value(title: str, value: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("MiniStat")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(6, 4, 6, 4)
    layout.setSpacing(0)
    title_label = QLabel(title)
    title_label.setObjectName("MiniStatTitle")
    value_label = QLabel(value)
    value_label.setObjectName("MiniStatValue")
    value_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(value_label)
    return frame


def form_row(label: str, field: QWidget) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    label_widget = QLabel(label)
    label_widget.setObjectName("FormLabel")
    label_widget.setMinimumWidth(150)
    layout.addWidget(label_widget)
    layout.addWidget(field, 1)
    return widget


def action_button(text: str, primary: bool = False, color: str | None = None) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("PrimaryButton" if primary else "SecondaryButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if color:
        button.setProperty("btnColor", color)
    return button


def chart_placeholder(title: str = "Biểu đồ") -> QFrame:
    frame = QFrame()
    frame.setObjectName("ChartPanel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(8)
    title_label = QLabel(title)
    title_label.setObjectName("PanelTitle")
    empty = QLabel("Chưa có dữ liệu biểu đồ")
    empty.setObjectName("EmptyText")
    empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title_label)
    layout.addWidget(empty, 1)
    return frame
