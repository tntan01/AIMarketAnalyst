"""Compact info card used in scanner detail overview tab."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout


def _is_light_theme() -> bool:
    try:
        from services.settings_service import SettingsService
        settings = SettingsService().load()
        return settings.display.theme == "light"
    except Exception:
        return False


class InfoCard(QFrame):
    """A compact card showing a label, value, and optional detail/evaluation line."""

    def __init__(
        self,
        label: str = "",
        value: str = "--",
        detail: str = "",
        *,
        accent: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("InfoCard")
        self._light = _is_light_theme()

        if self._light:
            bg, border, hover_border = "#EAE6DF", "#D6D2C8", "#A19B90"
            label_color, detail_color = "#57534E", "#736B60"
            default_accent = "#0369A1"
        else:
            bg, border, hover_border = "#1e293b", "#334155", "#475569"
            label_color, detail_color = "#94a3b8", "#64748b"
            default_accent = "#38bdf8"

        if not accent:
            accent = default_accent

        self.setStyleSheet(
            f"QFrame#InfoCard {{ background: {bg}; border: 1px solid {border}; border-radius: 6px; }}"
            f"QFrame#InfoCard:hover {{ border-color: {hover_border}; }}"
        )
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(6)

        self._label_w = QLabel(label)
        self._label_w.setObjectName("InfoCardLabel")
        self._label_w.setStyleSheet(f"color: {label_color}; font-size: 11px;")
        
        self._value_w = QLabel(value)
        self._value_w.setObjectName("InfoCardValue")
        self._value_w.setStyleSheet(f"color: {accent}; font-size: 12px; font-weight: bold;")
        
        layout.addWidget(self._label_w)
        layout.addStretch(1)
        layout.addWidget(self._value_w)

        self._detail_w = QLabel(detail)
        self._detail_w.setObjectName("InfoCardDetail")
        self._detail_w.setStyleSheet(f"color: {detail_color}; font-size: 11px;")
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

