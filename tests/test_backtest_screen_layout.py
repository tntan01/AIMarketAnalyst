from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from ui.layout_system import LayoutTokens
from ui.theme_manager import ThemeManager
import ui.screens.backtest_screen as backtest_screen_module
from ui.screens.backtest_screen import BacktestScreen, SymbolSelectionDialog
from ui.screens.settings_screen import SettingsScreen


DISPLAY_VIEWPORTS = (
    (1110, 700),   # usable area on a compact 14" display
    (1280, 720),   # 15.6"
    (1440, 800),   # 16"
    (1920, 1000),  # 24"
    (2560, 1400),  # 27"
    (3200, 1800),  # 32"
)
STANDARD_CONTROL_HEIGHT = 24
COMPACT_CONTROL_HEIGHT = 20


def _screen(width: int = 1110, height: int = 700) -> BacktestScreen:
    app_instance = QApplication.instance() or QApplication([])
    screen = BacktestScreen(app=MagicMock())
    ThemeManager().apply(screen, theme="dark")
    screen.resize(width, height)
    screen.show()
    app_instance.processEvents()
    return screen


def _mapped_rect(widget: QWidget, ancestor: QWidget) -> QRect:
    return QRect(widget.mapTo(ancestor, widget.rect().topLeft()), widget.size())


def _assert_inside(widget: QWidget, ancestor: QWidget) -> None:
    rect = _mapped_rect(widget, ancestor)
    assert rect.left() >= -1
    assert rect.top() >= -1
    assert rect.right() <= ancestor.width()
    assert rect.bottom() <= ancestor.height()


def _assert_no_overlap(widgets: tuple[QWidget, ...], ancestor: QWidget) -> None:
    rectangles = [
        (_mapped_rect(widget, ancestor), widget)
        for widget in widgets
        if widget.isVisible()
    ]
    for index, (left_rect, left_widget) in enumerate(rectangles):
        for right_rect, right_widget in rectangles[index + 1 :]:
            assert not left_rect.intersects(right_rect), (
                f"{left_widget.objectName() or type(left_widget).__name__} "
                f"overlaps {right_widget.objectName() or type(right_widget).__name__}"
            )


@pytest.mark.parametrize(("width", "height"), DISPLAY_VIEWPORTS)
def test_backtest_layout_fits_supported_display_sizes(
    width: int,
    height: int,
) -> None:
    screen = _screen(width, height)
    try:
        assert screen.height() == height
        assert screen.minimumSizeHint().height() <= DISPLAY_VIEWPORTS[0][1]

        _assert_inside(screen.settings_frame, screen)
        _assert_inside(screen.tabs, screen)

        for tab_index in range(screen.tabs.count()):
            screen.tabs.setCurrentIndex(tab_index)
            QApplication.processEvents()
            current = screen.tabs.currentWidget()
            _assert_inside(current, screen)
            for child in current.findChildren(QWidget):
                if child.isVisible() and child.window() is screen.window():
                    _assert_inside(child, screen)

        tab_width = sum(
            screen.tabs.tabBar().tabRect(index).width()
            for index in range(screen.tabs.count())
        )
        assert tab_width <= screen.tabs.tabBar().width()
    finally:
        screen.close()


def test_backtest_main_form_uses_aligned_grid_without_overlap() -> None:
    screen = _screen()
    try:
        assert isinstance(screen.settings_input_layout, (QGridLayout, QHBoxLayout))
        margins = screen.layout().contentsMargins()
        assert (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        ) == (LayoutTokens.PAGE_MARGIN,) * 4

        configuration_controls = (
            screen.symbol_summary,
            screen.symbol_button,
            screen.balance_input,
            screen.start_date,
            screen.end_date,
            screen.risk_input,
            screen.purpose_combo,
            screen.mode_summary_label,
        )
        center_lines = [
            widget.mapTo(screen.settings_frame, widget.rect().center()).y()
            for widget in configuration_controls
        ]
        assert max(center_lines) - min(center_lines) <= 1

        _assert_no_overlap(
            (
                screen.symbol_summary,
                screen.symbol_button,
                screen.start_date,
                screen.end_date,
            ),
            screen.settings_frame,
        )
        _assert_no_overlap(
            (
                screen.balance_input,
                screen.risk_input,
                screen.purpose_combo,
                screen.run_button,
                screen.cancel_backtest_btn,
                screen.apply_config_btn,
            ),
            screen.settings_frame,
        )
        _assert_no_overlap(
            (
                screen.progress,
                screen.status_label,
                screen.mode_summary_label,
            ),
            screen.settings_frame,
        )

        assert screen.status_label.wordWrap()
        assert screen.snapshot_label.wordWrap()
        assert screen.verdict_banner.wordWrap()
    finally:
        screen.close()


def test_backtest_same_control_types_share_metrics() -> None:
    screen = _screen()
    try:
        fields = (
            screen.symbol_summary,
            screen.start_date,
            screen.end_date,
            screen.balance_input,
            screen.risk_input,
            screen.purpose_combo,
            screen.advanced_execution_combo,
            screen.sweep_params_combo,
            screen.sweep_period_combo,
        )
        buttons = (
            screen.symbol_button,
            screen.run_button,
            screen.cancel_backtest_btn,
            screen.apply_config_btn,
            screen.load_result_button,
            screen.analyze_btn,
            screen.sweep_run_btn,
            screen.sweep_cancel_btn,
            screen.sweep_report_btn,
        )
        checkboxes = (
            screen.research_validation_checkbox,
            screen.portfolio_mode_checkbox,
            screen.monte_carlo_checkbox,
            screen.sweep_all_symbols_checkbox,
        )
        help_buttons = tuple(
            screen._sweep_tab.findChildren(QPushButton, "HelpButton")
        )

        assert {widget.height() for widget in fields} == {STANDARD_CONTROL_HEIGHT}
        assert {widget.height() for widget in buttons} == {STANDARD_CONTROL_HEIGHT}
        assert {widget.iconSize().width() for widget in buttons} == {
            LayoutTokens.ICON_SIZE
        }
        assert {widget.height() for widget in checkboxes} == {STANDARD_CONTROL_HEIGHT}
        assert help_buttons
        assert {button.size().width() for button in help_buttons} == {
            COMPACT_CONTROL_HEIGHT
        }
        assert {button.size().height() for button in help_buttons} == {
            COMPACT_CONTROL_HEIGHT
        }
        assert screen.progress.height() == LayoutTokens.PROGRESS_HEIGHT
        assert screen.sweep_progress.height() == LayoutTokens.PROGRESS_HEIGHT
    finally:
        screen.close()


def test_backtest_fields_fit_their_largest_displayed_values() -> None:
    screen = _screen()
    try:
        # Date fields use fixed width set by layout (130px) —
        # verify against minimum needed for "dd/MM/yyyy" + FilterField chrome
        assert screen.start_date.width() >= 110
        assert screen.end_date.width() >= 110
        # ComboBox Mục đích: fixed width 112 — verify against runtime minimum
        assert screen.purpose_combo.width() >= 110

        value_cases = (
            (screen.advanced_execution_combo, "Research nhanh", 24),
            (screen.sweep_params_combo, "Tất cả 10", 24),
        )
        for widget, text, chrome_width in value_cases:
            text_width = widget.fontMetrics().horizontalAdvance(text)
            assert widget.width() >= text_width + chrome_width

        screen.balance_input.setValue(screen.balance_input.maximum())
        screen.risk_input.setValue(screen.risk_input.maximum())
        QApplication.processEvents()
        for spinbox in (screen.balance_input, screen.risk_input):
            text_width = spinbox.fontMetrics().horizontalAdvance(spinbox.text())
            assert spinbox.width() >= min(text_width + 16, spinbox.width())

        longest_period = max(
            (
                screen.sweep_period_combo.itemText(index)
                for index in range(screen.sweep_period_combo.count())
            ),
            key=screen.sweep_period_combo.fontMetrics().horizontalAdvance,
        )
        period_width = screen.sweep_period_combo.fontMetrics().horizontalAdvance(
            longest_period
        )
        assert screen.sweep_period_combo.width() >= period_width + 30
    finally:
        screen.close()


def test_backtest_table_chart_and_advanced_cards_use_shared_grid() -> None:
    screen = _screen()
    try:
        assert isinstance(screen.advanced_options_grid, QGridLayout)
        assert isinstance(screen.sweep_controls_grid, QGridLayout)
        assert screen.research_card.height() == screen.sweep_card.height()
        assert (
            screen.table.horizontalHeader().height()
            == LayoutTokens.TABLE_HEADER_HEIGHT
        )
        assert (
            screen.table.verticalHeader().defaultSectionSize()
            == LayoutTokens.TABLE_ROW_HEIGHT
        )
        assert screen.table.wordWrap() is False
        assert (
            screen._equity_canvas is None
            or screen._equity_canvas.minimumHeight()
            == LayoutTokens.CHART_MIN_HEIGHT
        )
    finally:
        screen.close()


def test_backtest_symbol_dialog_uses_dialog_grid_tokens() -> None:
    app_instance = QApplication.instance() or QApplication([])
    dialog = SymbolSelectionDialog(["EUR/USD"])
    ThemeManager().apply(dialog, theme="dark")
    dialog.show()
    app_instance.processEvents()
    try:
        margins = dialog.layout().contentsMargins()
        assert (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        ) == (LayoutTokens.DIALOG_MARGIN,) * 4
        assert dialog.layout().spacing() == LayoutTokens.SPACE_3
        assert dialog.isSizeGripEnabled()
        assert dialog.minimumWidth() == LayoutTokens.DIALOG_SM_WIDTH
        assert {box.height() for box in dialog._symbol_checks} == {
            STANDARD_CONTROL_HEIGHT
        }
        action_buttons = tuple(
            button
            for button in dialog.findChildren(QPushButton)
            if button.objectName() in {"PrimaryButton", "SecondaryButton"}
        )
        assert {button.height() for button in action_buttons} == {
            STANDARD_CONTROL_HEIGHT
        }
    finally:
        dialog.close()


def test_backtest_analysis_dialog_uses_shared_dialog_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen = _screen()
    captured: list[QDialog] = []
    screen._ai_thread = MagicMock()
    monkeypatch.setattr(screen, "_generate_stats_html", lambda: "")
    monkeypatch.setattr(
        QDialog,
        "exec",
        lambda dialog: captured.append(dialog) or 0,
    )
    try:
        screen._on_ai_analysis_done("Kết quả phân tích")
        assert len(captured) == 1
        dialog = captured[0]
        ThemeManager().apply(dialog, theme="dark")
        dialog.show()
        QApplication.processEvents()
        margins = dialog.layout().contentsMargins()
        assert dialog.objectName() == "BacktestAnalysisDialog"
        assert dialog.minimumWidth() == LayoutTokens.DIALOG_MD_WIDTH
        assert dialog.minimumHeight() == LayoutTokens.DIALOG_MD_HEIGHT
        assert dialog.isSizeGripEnabled()
        assert (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        ) == (LayoutTokens.DIALOG_MARGIN,) * 4
        close_button = dialog.findChild(QPushButton, "SecondaryButton")
        assert close_button is not None
        assert close_button.height() == STANDARD_CONTROL_HEIGHT
    finally:
        screen.close()


def test_backtest_config_dialog_uses_shared_dialog_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen = _screen()
    captured: list[QDialog] = []
    action = SimpleNamespace(
        visible=True,
        label="💾 Lưu bản nháp",
        kind=backtest_screen_module.ACTION_SAVE_DRAFT,
    )
    config = {
        "status": "DRAFT",
        "regime": "aligned",
        "side": "buy",
        "min_score": 65,
        "min_rr": 2.0,
        "_evidence": "Đủ dữ liệu nghiên cứu",
        "out_of_sample_trades": 0,
        "walk_forward_windows": 0,
        "validation_reasons": [],
    }
    settings = SimpleNamespace(
        display=SimpleNamespace(theme="light"),
        trading=SimpleNamespace(symbol_settings={}),
    )
    screen.result = {"summary": {}}
    screen.app.settings_service.load.return_value = settings
    monkeypatch.setattr(
        backtest_screen_module,
        "result_action",
        lambda *_args, **_kwargs: action,
    )
    import core.backtest_config_validation as validation_module

    monkeypatch.setattr(
        validation_module,
        "build_backtest_config",
        lambda *_args, **_kwargs: config,
    )
    monkeypatch.setattr(
        QDialog,
        "exec",
        lambda dialog: captured.append(dialog) or 0,
    )
    try:
        screen._apply_scanner_config()
        assert len(captured) == 1
        dialog = captured[0]
        ThemeManager().apply(dialog, theme="light")
        dialog.show()
        QApplication.processEvents()
        margins = dialog.layout().contentsMargins()
        assert dialog.objectName() == "BacktestConfigDialog"
        assert dialog.minimumWidth() == LayoutTokens.DIALOG_LG_WIDTH
        assert dialog.minimumHeight() == 320
        assert dialog.isSizeGripEnabled()
        assert (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        ) == (LayoutTokens.DIALOG_MARGIN,) * 4
        action_buttons = tuple(
            button
            for button in dialog.findChildren(QPushButton)
            if button.objectName() in {"PrimaryButton", "SecondaryButton"}
        )
        assert {button.height() for button in action_buttons} == {
            STANDARD_CONTROL_HEIGHT
        }
    finally:
        screen.close()


def test_settings_backtest_cost_fields_share_layout_tokens() -> None:
    field = QDoubleSpinBox()
    row = SettingsScreen._compact_form_row(
        None,
        "Trượt giá Backtest",
        field,
    )
    ThemeManager().apply(row, theme="dark")
    QApplication.processEvents()
    try:
        label = row.findChild(QLabel, "FormLabel")
        assert label is not None
        assert label.width() == LayoutTokens.SETTINGS_LABEL_WIDTH
        assert label.height() == STANDARD_CONTROL_HEIGHT
        assert field.width() == LayoutTokens.SETTINGS_FIELD_WIDTH
        assert field.height() == STANDARD_CONTROL_HEIGHT
        assert row.layout().spacing() == LayoutTokens.SPACE_2
    finally:
        row.close()
