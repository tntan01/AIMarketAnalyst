from __future__ import annotations

from ui.screens.scanner_screen import ScannerScreen


class _Combo:
    def currentData(self) -> str:
        return "auto"


class _Button:
    def __init__(self, checked: bool = True) -> None:
        self.checked = checked
        self.enabled = True

    def isChecked(self) -> bool:
        return self.checked

    def setChecked(self, checked: bool) -> None:
        self.checked = checked

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled


def test_scanner_auto_trade_is_disabled_even_in_auto_scan_mode() -> None:
    owner = type(
        "Owner",
        (),
        {
            "AUTO_TRADE_UI_ENABLED": False,
            "scan_mode_combo": _Combo(),
            "auto_trade_check": _Button(checked=True),
        },
    )()

    assert ScannerScreen._auto_trade_enabled(owner) is False


def test_scanner_auto_trade_toggle_is_disabled_and_reset() -> None:
    button = _Button(checked=True)
    style_updates: list[bool] = []
    owner = type(
        "Owner",
        (),
        {
            "AUTO_TRADE_UI_ENABLED": False,
            "scan_mode_combo": _Combo(),
            "auto_trade_check": button,
            "_update_auto_trade_toggle_style": lambda self: style_updates.append(
                True
            ),
        },
    )()

    ScannerScreen._update_auto_trade_toggle_state(owner)

    assert button.enabled is False
    assert button.checked is False
    assert style_updates == [True]
