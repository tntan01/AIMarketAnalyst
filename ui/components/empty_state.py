from __future__ import annotations

from PyQt6.QtWidgets import QLabel


class EmptyState(QLabel):
    def __init__(self) -> None:
        super().__init__("Chua co du lieu")
