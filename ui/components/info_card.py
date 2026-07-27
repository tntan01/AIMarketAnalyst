"""Compact info card used in scanner detail overview tab."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout
from ui.theme import PALETTES
from ui.theme_manager import set_dynamic_property


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
        self._accent = accent

        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(4)

        self._label_w = QLabel(label)
        self._label_w.setObjectName("InfoCardLabel")
        
        self._value_w = QLabel(value)
        self._value_w.setObjectName("InfoCardValue")
        
        layout.addWidget(self._label_w)
        layout.addStretch(1)
        layout.addWidget(self._value_w)

        self._detail_w = QLabel(detail)
        self._detail_w.setObjectName("InfoCardDetail")
        self._detail_w.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._detail_w)

        self.refresh_theme()

    def refresh_theme(self, accent: str | None = None) -> None:
        requested = accent or self._accent
        set_dynamic_property(
            self._value_w,
            "accentRole",
            self._accent_role(requested),
        )

    @staticmethod
    def _accent_role(color: str) -> str:
        normalized = str(color or "").strip().lower()
        if not normalized:
            return "info"
        for palette in PALETTES.values():
            for role in ("accent", "success", "warning", "danger", "info"):
                if normalized == getattr(palette, role).lower():
                    return role
        return "info"

    def set_value(self, text: str, accent: str | None = None) -> None:
        self._value_w.setText(text)
        self.refresh_theme(accent=accent)

    def set_detail(self, text: str) -> None:
        self._detail_w.setText(text)
        self.refresh_theme()

    def set_label(self, text: str) -> None:
        self._label_w.setText(text)
        self.refresh_theme()

