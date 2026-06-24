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
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(6)

        self._label_w = QLabel(label)
        self._label_w.setObjectName("InfoCardLabel")
        self._label_w.setStyleSheet("color: #94a3b8; font-size: 11px;")
        
        self._value_w = QLabel(value)
        self._value_w.setObjectName("InfoCardValue")
        self._value_w.setStyleSheet(f"color: {accent}; font-size: 12px; font-weight: bold;")
        
        layout.addWidget(self._label_w)
        layout.addStretch(1)
        layout.addWidget(self._value_w)

        self._detail_w = QLabel(detail)
        self._detail_w.setObjectName("InfoCardDetail")
        self._detail_w.setStyleSheet("color: #64748b; font-size: 11px;")
        self._detail_w.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._detail_w)

    def set_value(self, text: str, accent: str | None = None) -> None:
        self._value_w.setText(text)
        if accent:
            self._value_w.setStyleSheet(f"color: {accent}; font-size: 12px; font-weight: bold;")

    def set_detail(self, text: str) -> None:
        self._detail_w.setText(text)

    def set_label(self, text: str) -> None:
        self._label_w.setText(text)
