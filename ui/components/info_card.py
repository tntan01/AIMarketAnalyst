"""Compact info card used in scanner detail overview tab."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout


class InfoCard(QFrame):
    """A compact card showing a label, value, and optional detail/evaluation line."""

    def __init__(
        self,
        label: str = "",
        value: str = "--",
        detail: str = "",
        *,
        accent: str = "#38bdf8",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("InfoCard")
        self.setStyleSheet(
            "QFrame#InfoCard { background: #1e293b; border: 1px solid #334155; border-radius: 6px; }"
            "QFrame#InfoCard:hover { border-color: #475569; }"
        )
        self.setMinimumHeight(52)
        self.setMaximumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(0)

        left = QVBoxLayout()
        left.setSpacing(1)
        self._label_w = QLabel(label)
        self._label_w.setObjectName("InfoCardLabel")
        self._label_w.setStyleSheet("color: #94a3b8; font-size: 10px;")
        self._value_w = QLabel(value)
        self._value_w.setObjectName("InfoCardValue")
        self._value_w.setStyleSheet(f"color: {accent}; font-size: 15px; font-weight: 700;")
        left.addWidget(self._label_w)
        left.addWidget(self._value_w)
        layout.addLayout(left, 1)

        self._detail_w = QLabel(detail)
        self._detail_w.setObjectName("InfoCardDetail")
        self._detail_w.setStyleSheet("color: #64748b; font-size: 11px;")
        self._detail_w.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._detail_w.setWordWrap(True)
        self._detail_w.setMaximumWidth(100)
        layout.addWidget(self._detail_w)

    def set_value(self, text: str, accent: str | None = None) -> None:
        self._value_w.setText(text)
        if accent:
            self._value_w.setStyleSheet(f"color: {accent}; font-size: 15px; font-weight: 700;")

    def set_detail(self, text: str) -> None:
        self._detail_w.setText(text)

    def set_label(self, text: str) -> None:
        self._label_w.setText(text)
