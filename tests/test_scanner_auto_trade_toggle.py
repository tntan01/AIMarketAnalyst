from __future__ import annotations

from ui.screens.scanner_screen import ScannerScreen


class _Combo:
    def __init__(self, mode: str = "auto") -> None:
        self.mode = mode

    def currentData(self) -> str:
        return self.mode


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


def test_scanner_auto_trade_can_be_enabled_in_auto_scan_mode() -> None:
    owner = type(
        "Owner",
        (),
        {
            "AUTO_TRADE_UI_ENABLED": True,
            "scan_mode_combo": _Combo(),
            "auto_trade_check": _Button(checked=True),
        },
    )()

    assert ScannerScreen._auto_trade_enabled(owner) is True


def test_scanner_auto_trade_toggle_is_available_in_auto_scan_mode() -> None:
    button = _Button(checked=True)
    style_updates: list[bool] = []
    owner = type(
        "Owner",
        (),
        {
            "AUTO_TRADE_UI_ENABLED": True,
            "scan_mode_combo": _Combo(),
            "auto_trade_check": button,
            "_update_auto_trade_toggle_style": lambda self: style_updates.append(
                True
            ),
        },
    )()

    ScannerScreen._update_auto_trade_toggle_state(owner)

    assert button.enabled is True
    assert button.checked is True
    assert style_updates == [True]


def test_scanner_auto_trade_toggle_is_reset_in_one_shot_mode() -> None:
    button = _Button(checked=True)
    style_updates: list[bool] = []
    owner = type(
        "Owner",
        (),
        {
            "AUTO_TRADE_UI_ENABLED": True,
            "scan_mode_combo": _Combo("once"),
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
