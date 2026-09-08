from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ui.layout_system import LayoutTokens, configure_layout
from ui.screens.shared import page_header


class SupplyDemandScreen(QWidget):
    """Placeholder for the Supply–Demand feature; starts no background work."""

    def __init__(self, navigate, app=None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        configure_layout(layout, margins=LayoutTokens.PAGE_MARGIN)
        layout.addWidget(
            page_header(
                "Cung–cầu",
                "Chức năng phân tích Supply–Demand đang được xây dựng.",
            )
        )
        layout.addStretch(1)
