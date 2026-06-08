from __future__ import annotations

import json

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QLabel, QDialog, QFrame, QGridLayout, QHBoxLayout, QMessageBox, QPushButton, QSizePolicy, QTabWidget, QTextEdit, QVBoxLayout, QWidget

from controllers.journal_controller import JournalController
from ui.components.chart_view import AnalysisChartView
from ui.screens.shared import action_button, card, labeled_value, page_header
from ui.translation import vi_term, vi_text


class SingleAnalysisResultScreen(QWidget):
    def __init__(self, navigate=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.journal_controller = JournalController()
        self.result: dict[str, object] | None = None
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(22, 16, 22, 16)
        self.root.setSpacing(10)
        self.header = page_header(
            "Kết quả phân tích",
            "Quyết định nhanh, biểu đồ và kế hoạch lệnh.",
            "--",
        )
        self.header_symbol_badge = self.header.findChild(QLabel, "HeaderBadge")
        self.root.addWidget(self.header)

        self.summary = QGridLayout()
        self.summary.setSpacing(10)
        self.summary_items: dict[str, QWidget] = {}
        self.summary_value_labels: dict[str, QLabel] = {}
        for index, (title, value) in enumerate(self._empty_summary()):
            item, value_label = self._inline_value(title, value)
            item.setMinimumHeight(46)
            item.setMaximumHeight(54)
            self.summary_value_labels[title] = value_label
            self.summary_items[title] = item
            self.summary.addWidget(item, 0, index)
            self.summary.setColumnStretch(index, 1)
        self.root.addLayout(self.summary)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.chart = AnalysisChartView()
        self.chart_frame = QFrame()
        self.chart_frame.setObjectName("AnalysisChartFrame")
        chart_layout = QVBoxLayout(self.chart_frame)
        chart_layout.setContentsMargins(8, 8, 8, 8)
        chart_layout.setSpacing(0)
        chart_layout.addWidget(self.chart)
        body.addWidget(self.chart_frame, 7)
        self.trade_plan_card = self._trade_plan_card()
        self.trade_plan_card.setMinimumWidth(320)
        self.trade_plan_card.setMaximumWidth(520)
        self.trade_plan_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        body.addWidget(self.trade_plan_card, 3)
        body.setStretch(0, 7)
        body.setStretch(1, 3)
        self.root.addLayout(body, 1)

        self.conditions_card = self._conditions_card()
        self.root.addWidget(self.conditions_card)

        self.tabs = self._tabs()
        self.debug_tabs = self._debug_tabs()

        actions = QHBoxLayout()
        back = action_button("Quay lại")
        self.detail_button = action_button("Chi tiết phân tích")
        self.debug_button = action_button("Dữ liệu & debug")
        self.save_button = action_button("Lưu nhật ký", primary=True)
        if self.navigate:
            back.clicked.connect(lambda: self.navigate("analysis_input"))
        self.detail_button.clicked.connect(self._show_detail_dialog)
        self.debug_button.clicked.connect(self._show_debug_dialog)
        self.save_button.clicked.connect(self._save_to_journal)
        actions.addWidget(back)
        actions.addStretch(1)
        actions.addWidget(self.detail_button)
        actions.addWidget(self.debug_button)
        actions.addWidget(self.save_button)
        self.root.addLayout(actions)

    def set_analysis_result(self, result: dict[str, object]) -> None:
        self.result = result
        if self.header_symbol_badge is not None:
            self.header_symbol_badge.setText(str(result.get("symbol") or "--"))
        self._refresh_summary()
        self._refresh_trade_plan()
        self._refresh_conditions()
        self._refresh_tabs()
        self._refresh_debug_tabs()
        self._refresh_chart()

    def _trade_plan_card(self) -> QWidget:
        frame = card("Kế hoạch lệnh")
        self.trade_plan_labels: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        rows = [
            ("Chiều lệnh", "--"),
            ("Vùng vào lệnh", "--"),
            ("Vùng theo dõi", "--"),
            ("Cắt lỗ", "--"),
            ("Chốt lời", "--"),
            ("R:R", "--"),
            ("R:R hiệu dụng", "--"),
            ("Khối lượng", "--"),
            ("Rủi ro tối đa", "--"),
            ("Điều kiện vô hiệu", "--"),
        ]
        positions = {
            "Chiều lệnh": (0, 0, 1, 1),
            "Khối lượng": (0, 1, 1, 1),
            "Vùng vào lệnh": (1, 0, 1, 2),
            "Vùng theo dõi": (2, 0, 1, 2),
            "Cắt lỗ": (3, 0, 1, 1),
            "Chốt lời": (3, 1, 1, 1),
            "R:R": (4, 0, 1, 1),
            "R:R hiệu dụng": (4, 1, 1, 1),
            "Rủi ro tối đa": (5, 0, 1, 2),
            "Điều kiện vô hiệu": (6, 0, 1, 2),
        }
        for title, value in rows:
            item, value_label = self._inline_value(title, value)
            item.setMinimumHeight(38)
            self.trade_plan_labels[title] = value_label
            grid.addWidget(item, *positions[title])
        frame.layout().addLayout(grid)
        frame.layout().addStretch(1)
        return frame

    def _conditions_card(self) -> QWidget:
        frame = QWidget()
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        self.condition_labels: dict[str, QTextEdit] = {}
        cards = [
            ("Điều kiện vào lệnh", "ConditionInfoCardEntry"),
            ("Lý do chưa sẵn sàng", "ConditionInfoCardWait"),
            ("Khi nào bỏ qua", "ConditionInfoCardSkip"),
        ]
        for index, (title, object_name) in enumerate(cards):
            item, value = self._condition_info_card(title, object_name)
            self.condition_labels[title] = value
            grid.addWidget(item, 0, index)
            grid.setColumnStretch(index, 1)
        frame.setLayout(grid)
        return frame

    def _condition_info_card(self, title: str, object_name: str) -> tuple[QFrame, QTextEdit]:
        frame = QFrame()
        frame.setObjectName(object_name)
        frame.setFixedHeight(150)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("ConditionInfoTitle")
        body_label = QTextEdit("--")
        body_label.setObjectName("ConditionInfoBody")
        body_label.setReadOnly(True)
        body_label.setFrameShape(QFrame.Shape.NoFrame)
        body_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        body_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(title_label)
        layout.addWidget(body_label, 1)
        return frame, body_label

    def _inline_value(self, title: str, value: str) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setObjectName("InlineStat")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("MiniStatTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        value_label = QLabel(value)
        value_label.setObjectName("MiniStatValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        value_label.setWordWrap(False)
        layout.addWidget(title_label)
        layout.addStretch(1)
        layout.addWidget(value_label)
        return frame, value_label

    def _refresh_chart(self) -> None:
        """Update chart with analysis result data."""
        if not self.result:
            self.chart.show_empty()
            return
        try:
            from core.chart_payload import build_full_chart_payload
            symbol = str(self.result.get("symbol", ""))
            payload = build_full_chart_payload(symbol, self.result)
            self.chart.set_payload(payload)
        except Exception:
            self.chart.show_error("Khong the tao du lieu bieu do tu ket qua phan tich.")

    def _empty_summary(self) -> list[tuple[str, str]]:
        return [
            ("Kết luận", "Đứng ngoài"),
            ("Quyết định", "--"),
            ("Điểm tổng hợp", "--"),
            ("Thiên hướng", "Trung lập"),
            ("Trạng thái vào lệnh", "--"),
            ("Bộ lọc giao dịch", "--"),
        ]

    def _refresh_summary(self) -> None:
        if not self.result:
            return
        values = dict(self._summary_values())
        for title, value_label in self.summary_value_labels.items():
            value_label.setText(values.get(title, "--"))

    def _summary_values(self) -> list[tuple[str, str]]:
        result = self.result or {}
        scenarios = result.get("scenarios", [])
        primary = scenarios[0] if isinstance(scenarios, list) and scenarios else {}
        decision = result.get("decision_summary", {}) if isinstance(result.get("decision_summary", {}), dict) else {}
        decision_engine = result.get("decision_engine", {}) if isinstance(result.get("decision_engine", {}), dict) else {}
        trade_gate = result.get("trade_gate", {}) if isinstance(result.get("trade_gate", {}), dict) else {}
        return [
            ("Kết luận", self._vi_term(decision.get("action", "--"))),
            ("Quyết định", self._vi_term(decision_engine.get("decision", decision.get("decision_engine_decision", "--")))),
            ("Điểm tổng hợp", self._score_text(result.get("final_score"))),
            ("Thiên hướng", self._direction_text(result.get("direction_bias", "--"))),
            ("Trạng thái vào lệnh", self._vi_term(primary.get("entry_status", "--") if isinstance(primary, dict) else "--")),
            ("Bộ lọc giao dịch", self._vi_term(trade_gate.get("decision_cap", decision.get("gate_decision_cap", "--")))),
        ]

    def _refresh_trade_plan(self) -> None:
        if not self.result:
            return
        primary = self._primary_scenario()
        sizing = primary.get("position_sizing", {}) if isinstance(primary.get("position_sizing", {}), dict) else {}
        tp = primary.get("take_profit", [])
        values = {
            "Chiều lệnh": self._vi_term(primary.get("type", "--")),
            "Vùng vào lệnh": self._range_text(primary.get("entry_zone")),
            "Vùng theo dõi": self._range_text(primary.get("watch_zone")),
            "Cắt lỗ": self._plain_text(primary.get("stop_loss")),
            "Chốt lời": ", ".join(str(item) for item in tp) if isinstance(tp, list) and tp else "--",
            "R:R": self._plain_text(primary.get("risk_reward")),
            "R:R hiệu dụng": self._plain_text(primary.get("expected_effective_rr")),
            "Khối lượng": self._plain_text(sizing.get("suggested_lot")),
            "Rủi ro tối đa": self._max_loss_text(sizing),
            "Điều kiện vô hiệu": vi_text(primary.get("invalidation", "--")),
        }
        for title, label in self.trade_plan_labels.items():
            label.setText(values.get(title, "--"))

    def _refresh_conditions(self) -> None:
        if not self.result:
            return
        primary = self._primary_scenario()
        checklist = self.result.get("entry_checklist", [])
        pass_items: list[str] = []
        wait_items: list[str] = []
        if isinstance(checklist, list):
            for item in checklist:
                if not isinstance(item, dict):
                    continue
                label = vi_text(item.get("label", "--"))
                note = vi_text(item.get("note", ""))
                text = f"{label}: {note}" if note else label
                if item.get("status") == "pass":
                    pass_items.append(text)
                else:
                    wait_items.append(text)
        entry_condition = vi_text(primary.get("condition", "--")) if isinstance(primary, dict) else "--"
        invalid_reason = vi_text(primary.get("invalid_reason") or primary.get("reason") or "--") if isinstance(primary, dict) else "--"
        invalidation = vi_text(primary.get("invalidation", "--")) if isinstance(primary, dict) else "--"
        self.condition_labels["Điều kiện vào lệnh"].setText(self._short_lines([entry_condition, *pass_items], 3))
        self.condition_labels["Lý do chưa sẵn sàng"].setText(self._short_lines([invalid_reason, *wait_items], 3))
        self.condition_labels["Khi nào bỏ qua"].setText(self._short_lines([invalidation, "Spread giãn bất thường", "Có tin tác động cao quá gần"], 3))

    def _tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("ContentTabs")
        tabs.tabBar().setExpanding(False)
        tabs.tabBar().setUsesScrollButtons(False)
        tabs.tabBar().setElideMode(Qt.TextElideMode.ElideRight)
        scenario_panel, self.scenario_text = self._text_panel("Kịch bản", "Chưa có kết quả phân tích.")
        plan_panel, self.plan_text = self._text_panel("Kế hoạch", "Vào lệnh: --\nCắt lỗ: --\nChốt lời: --\nTỷ lệ rủi ro/lợi nhuận: --\nKhối lượng: --")
        checklist_panel, self.checklist_text = self._text_panel("Checklist", "Chưa có checklist.")
        replay_panel, self.replay_text = self._text_panel("Replay", "Chưa có dữ liệu replay.")
        macro_panel, self.macro_text = self._text_panel("Vĩ mô", "Chưa có dữ liệu vĩ mô.")
        ai_panel, self.ai_text = self._text_panel("Nhận định AI", "Chưa có nhận định AI.")
        tabs.addTab(scenario_panel, "Kịch bản")
        tabs.addTab(plan_panel, "Kế hoạch")
        tabs.addTab(checklist_panel, "Checklist")
        tabs.addTab(replay_panel, "Replay")
        tabs.addTab(macro_panel, "Vĩ mô & tin tức")
        tabs.addTab(ai_panel, "Nhận định AI")
        tabs.currentChanged.connect(self._sync_result_tab_nav)
        return tabs

    def _debug_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("ContentTabs")
        gate_panel, self.gate_text = self._text_panel("Trade gate", "Chưa có dữ liệu gate.")
        data_panel, self.data_text = self._text_panel("Raw JSON", "MT5: --")
        tabs.addTab(gate_panel, "Trade gate")
        tabs.addTab(data_panel, "Raw JSON")
        return tabs

    def _tab_stack(self) -> QWidget:
        container = QWidget()
        container.setObjectName("ResultTabStack")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(8)
        self.prev_tab_button = QPushButton("<")
        self.prev_tab_button.setObjectName("ResultTabArrow")
        self.prev_tab_button.setToolTip("Chuyển sang tab bên trái")
        self.prev_tab_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_tab_button.clicked.connect(lambda: self._move_result_tab(-1))

        self.tab_position_label = QLabel("")
        self.tab_position_label.setObjectName("ResultTabPosition")
        self.tab_position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.next_tab_button = QPushButton(">")
        self.next_tab_button.setObjectName("ResultTabArrow")
        self.next_tab_button.setToolTip("Chuyển sang tab bên phải")
        self.next_tab_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_tab_button.clicked.connect(lambda: self._move_result_tab(1))

        nav.addWidget(self.prev_tab_button)
        nav.addWidget(self.tab_position_label, 1)
        nav.addWidget(self.next_tab_button)
        layout.addLayout(nav)
        layout.addWidget(self.tabs, 1)
        QTimer.singleShot(0, self._sync_result_tab_nav)
        return container

    def _move_result_tab(self, delta: int) -> None:
        total = self.tabs.count()
        if total <= 0:
            return
        self.tabs.setCurrentIndex((self.tabs.currentIndex() + delta) % total)

    def _sync_result_tab_nav(self) -> None:
        if not hasattr(self, "tab_position_label"):
            return
        index = self.tabs.currentIndex()
        total = self.tabs.count()
        title = self.tabs.tabText(index) if index >= 0 else "--"
        self.tab_position_label.setText(f"{index + 1}/{total} - {title}")
        enabled = total > 1
        self.prev_tab_button.setEnabled(enabled)
        self.next_tab_button.setEnabled(enabled)

    def _refresh_tabs(self) -> None:
        if not self.result:
            return
        result = self.result
        decision = result.get("decision_summary", {})
        regime = result.get("market_regime", {})
        scenarios = result.get("scenarios", [])
        primary = scenarios[0] if isinstance(scenarios, list) and scenarios else {}
        self.scenario_text.setPlainText(
            "\n".join(
                [
                    f"Nhận định chính: {vi_text(decision.get('main_view', '--') if isinstance(decision, dict) else '--')}",
                    f"Trạng thái thị trường: {self._vi_term(regime.get('primary', '--') if isinstance(regime, dict) else '--')}",
                    f"Cấu trúc giá: {self._vi_term(regime.get('structure', '--') if isinstance(regime, dict) else '--')}",
                    f"Lý do đứng ngoài/kịch bản phụ: {vi_text(primary.get('reason', primary.get('invalidation', '--')) if isinstance(primary, dict) else '--')}",
                ]
            )
        )
        self.plan_text.setPlainText(self._format_plan(primary))
        self.checklist_text.setPlainText(self._format_entry_checklist())
        self.replay_text.setPlainText(self._format_replay(result.get("backtest", {})))
        macro = result.get("macro", {}) if isinstance(result.get("macro", {}), dict) else {}
        self.macro_text.setPlainText(self._format_macro(macro, result.get("economic_events", []), result.get("scenario_scores", {})))
        self.ai_text.setPlainText(vi_text(macro.get("ai_summary", "Chưa có nhận định AI.")))
        self.ai_text.moveCursor(QTextCursor.MoveOperation.Start)

    def _refresh_debug_tabs(self) -> None:
        if not self.result:
            return
        result = self.result
        decision = result.get("decision_engine", {}) if isinstance(result.get("decision_engine", {}), dict) else {}
        gate = result.get("trade_gate", {}) if isinstance(result.get("trade_gate", {}), dict) else {}
        data_quality = result.get("data_quality", {}) if isinstance(result.get("data_quality", {}), dict) else {}
        lines = [
            f"Decision: {decision.get('decision', '--')}",
            f"Legacy action: {decision.get('legacy_action', '--')}",
            f"Final score: {result.get('final_score', '--')}",
            f"Gate cap: {gate.get('decision_cap', '--')}",
            f"Gate allowed: {gate.get('allowed', '--')}",
            f"Warning codes: {gate.get('warning_codes', result.get('warning_codes', []))}",
            f"Block codes: {gate.get('block_codes', result.get('block_codes', []))}",
            f"Spread: {data_quality.get('spread_status', '--')}",
            f"Data warning: {data_quality.get('warning', '--')}",
        ]
        self.gate_text.setPlainText("\n".join(lines))
        self.data_text.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))

    def _format_plan(self, scenario: dict[str, object]) -> str:
        if not scenario or scenario.get("type") == "stand_aside":
            return vi_text(scenario.get("reason", "Không có thiết lập giao dịch sạch / đứng ngoài tốt hơn."))
        sizing = scenario.get("position_sizing", {})
        return "\n".join(
            [
                f"Loại kịch bản: {self._vi_term(scenario.get('type', '--'))}",
                f"Trạng thái vào lệnh: {self._vi_term(scenario.get('entry_status', '--'))}",
                f"Điểm xác nhận: {scenario.get('confirmation_score', '--')} / 100",
                f"Tín hiệu kích hoạt: {self._vi_term(scenario.get('trigger_type', '--'))}",
                f"Vùng vào lệnh: {scenario.get('entry_zone', '--')}",
                f"Cắt lỗ: {scenario.get('stop_loss', '--')}",
                f"Chốt lời: {scenario.get('take_profit', '--')}",
                f"Tỷ lệ rủi ro/lợi nhuận: {scenario.get('risk_reward', '--')}",
                f"Khối lượng: {sizing.get('suggested_lot', '--') if isinstance(sizing, dict) else '--'}",
                f"Điều kiện: {vi_text(scenario.get('condition', '--'))}",
                f"Lý do chưa sẵn sàng: {vi_text(scenario.get('invalid_reason', '--') or '--')}",
                f"Điều kiện vô hiệu: {vi_text(scenario.get('invalidation', '--'))}",
                "",
                "Checklist vào lệnh:",
                self._format_entry_checklist(),
            ]
        )

    def _format_entry_checklist(self) -> str:
        checklist = self.result.get("entry_checklist", []) if self.result else []
        if not isinstance(checklist, list) or not checklist:
            return "--"
        rows = []
        for item in checklist:
            if not isinstance(item, dict):
                continue
            marker = "Đạt" if item.get("status") == "pass" else "Chờ"
            rows.append(
                f"- {vi_text(item.get('label', '--'))}: {marker} | {self._vi_term(item.get('value', '--'))} | {vi_text(item.get('note', ''))}"
            )
        return "\n".join(rows)

    def _format_replay(self, backtest: object) -> str:
        if not isinstance(backtest, dict):
            return "Chưa có dữ liệu replay."
        summary = backtest.get("summary", {}) if isinstance(backtest.get("summary"), dict) else {}
        by_session = backtest.get("by_session", {}) if isinstance(backtest.get("by_session"), dict) else {}
        lines = [
            f"Số lệnh replay: {summary.get('trade_count', 0)}",
            f"Tỷ lệ thắng: {summary.get('win_rate', 0)}%",
            f"Kỳ vọng lợi nhuận: {summary.get('expectancy_r', 0)} R",
            f"R trung bình: {summary.get('average_r', 0)} R",
            f"MFE/MAE trung bình: {summary.get('average_mfe_r', 0)} R / {summary.get('average_mae_r', 0)} R",
            f"Sụt giảm tối đa: {summary.get('max_drawdown_r', 0)} R",
        ]
        if backtest.get("reason"):
            lines.append(f"Ghi chú: {vi_text(backtest['reason'])}")
        if by_session:
            lines.extend(["", "Theo phiên:"])
            for session, metrics in by_session.items():
                if isinstance(metrics, dict):
                    lines.append(
                        f"- {self._vi_term(session)}: {metrics.get('trade_count', 0)} lệnh, "
                        f"tỷ lệ thắng {metrics.get('win_rate', 0)}%, kỳ vọng {metrics.get('expectancy_r', 0)} R"
                    )
        return "\n".join(lines)

    def _format_macro(self, macro: object, events: object, scores: object) -> str:
        if not isinstance(macro, dict):
            return "Chưa có dữ liệu vĩ mô."
        context = macro.get("driver_context", {}) if isinstance(macro.get("driver_context"), dict) else {}
        headlines = context.get("latest_headlines", []) if isinstance(context.get("latest_headlines"), list) else []
        statements = context.get("latest_statements", []) if isinstance(context.get("latest_statements"), list) else []
        themes = context.get("macro_themes", []) if isinstance(context.get("macro_themes"), list) else []
        hotspots = context.get("geopolitical_hotspots", []) if isinstance(context.get("geopolitical_hotspots"), list) else []
        score_text = "--"
        if isinstance(scores, dict):
            buy_macro = scores.get("buy", {}).get("macro_alignment") if isinstance(scores.get("buy"), dict) else "--"
            sell_macro = scores.get("sell", {}).get("macro_alignment") if isinstance(scores.get("sell"), dict) else "--"
            score_text = f"Mua {buy_macro} / Bán {sell_macro}"
        lines = [f"Điểm vĩ mô: {score_text}"]
        if themes:
            lines.extend(["", "Chủ đề vĩ mô:"])
            for item in themes:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('currency', '--')}: {self._vi_term(item.get('stance', 'neutral'))} ({item.get('headline_count', 0)} tin)")
        if headlines or statements:
            lines.extend(["", "Tin mới nhất:"])
            for item in headlines[:8]:
                if isinstance(item, dict):
                    lines.append(f"- {self._format_news_line(item)}")
            for item in statements[:10]:
                if isinstance(item, dict):
                    lines.append(f"- {self._format_news_line(item)}")
        else:
            lines.extend(["", "Tin mới nhất: Không có dữ liệu tiêu đề mới từ nguồn đã kiểm tra."])
        if hotspots:
            lines.extend(["", "Điểm nóng thế giới:"])
            for item in hotspots[:5]:
                if isinstance(item, dict):
                    lines.append(f"- {self._format_news_line(item)}")
        else:
            lines.extend(["", "Điểm nóng thế giới: Không có dữ liệu điểm nóng khớp bộ lọc."])
        if isinstance(events, list) and events:
            lines.extend(["", "Lịch kinh tế:"])
            for event in events[:6]:
                if isinstance(event, dict):
                    lines.append(f"- {self._format_event_line(event)}")
        return "\n".join(lines)

    def _format_event_line(self, event: dict[str, object]) -> str:
        time_text = str(event.get("event_time_local") or event.get("time_vn") or event.get("time_utc") or "--")
        title = str(event.get("event_vi") or vi_text(event.get("event", "--")))
        currency = str(event.get("currency", "--"))
        impact = str(event.get("impact_assessment") or f"ảnh hưởng {self._vi_term(event.get('impact', '--'))} tới {currency}")
        return f"{time_text}: {title} -> {impact}"

    def _format_news_line(self, item: dict[str, object]) -> str:
        time_text = str(item.get("published_local") or item.get("published_utc") or "--")
        title = str(item.get("title_vi") or vi_text(item.get("title", "--")))
        impact = str(item.get("impact_assessment") or item.get("impact_note") or "").strip()
        return f"{time_text}: {title} -> {impact}" if impact else f"{time_text}: {title}"

    def _vi_term(self, value: object) -> str:
        local = {
            "buy": "Ưu tiên mua",
            "sell": "Ưu tiên bán",
            "stand_aside": "Đứng ngoài",
            "watch": "Theo dõi",
            "caution": "Cẩn trọng",
            "allowed": "Được phép",
            "blocked": "Bị chặn",
            "waiting_confirmation": "Chờ xác nhận",
            "watch_zone": "Vùng theo dõi",
            "confirmed_entry": "Đã xác nhận",
            "invalidated": "Đã vô hiệu",
            "READY_TO_TRADE": "Sẵn sàng giao dịch",
            "WAITING_CONFIRMATION": "Chờ xác nhận",
            "WATCH_ONLY": "Chỉ theo dõi",
            "TRADE_BLOCKED": "Bị chặn",
        }
        text = str(value if value is not None else "").strip()
        return local.get(text, vi_term(text))

    def _primary_scenario(self) -> dict[str, object]:
        scenarios = self.result.get("scenarios", []) if self.result else []
        if isinstance(scenarios, list) and scenarios and isinstance(scenarios[0], dict):
            return scenarios[0]
        return {}

    def _direction_text(self, value: object) -> str:
        if isinstance(value, dict):
            side = value.get("best_side") or value.get("direction") or value.get("bias")
            gap = value.get("score_gap")
            text = self._vi_term(side or "--")
            return f"{text} | gap {gap}" if gap not in (None, "") else text
        return self._vi_term(value)

    def _score_text(self, value: object) -> str:
        if value in (None, ""):
            return "--"
        try:
            return f"{int(float(value))}/100"
        except (TypeError, ValueError):
            return str(value)

    def _range_text(self, value: object) -> str:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return f"{value[0]} - {value[1]}"
        return self._plain_text(value)

    def _plain_text(self, value: object) -> str:
        if value in (None, "", []):
            return "--"
        if isinstance(value, float):
            return f"{value:.4g}"
        return str(value)

    def _max_loss_text(self, sizing: object) -> str:
        if not isinstance(sizing, dict):
            return "--"
        amount = sizing.get("risk_amount_usd")
        pct = sizing.get("risk_pct")
        if amount in (None, ""):
            return "--"
        try:
            amount_text = f"{float(amount):,.2f} USD"
        except (TypeError, ValueError):
            amount_text = str(amount)
        return f"{amount_text} ({pct}%)" if pct not in (None, "") else amount_text

    def _short_lines(self, lines: list[str], limit: int) -> str:
        cleaned = [line for line in lines if line and line != "--"]
        if not cleaned:
            return "--"
        return "\n".join(cleaned[:limit])

    def _show_detail_dialog(self) -> None:
        self._show_tabs_dialog("Chi tiết phân tích", self.tabs)

    def _show_debug_dialog(self) -> None:
        self._show_tabs_dialog("Dữ liệu & debug", self.debug_tabs)

    def _show_tabs_dialog(self, title: str, tabs: QTabWidget) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setObjectName("AnalysisDetailDialog")
        dialog.resize(980, 680)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        tabs.setParent(dialog)
        layout.addWidget(tabs)
        close_button = action_button("Đóng", primary=True)
        close_button.clicked.connect(dialog.accept)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        dialog.exec()
        tabs.setParent(None)

    def _text_panel(self, title: str, text: str) -> tuple[QWidget, QTextEdit]:
        frame = card(title)
        editor = QTextEdit(text)
        editor.setObjectName("ReadonlyText")
        editor.setReadOnly(True)
        frame.layout().addWidget(editor)
        return frame, editor

    def _save_to_journal(self) -> None:
        if not self.result:
            return
        entry_id = self.journal_controller.save_analysis(self.result, mode="single_analysis")
        QMessageBox.information(self, "Đã lưu nhật ký", f"Đã lưu bản ghi nhật ký #{entry_id}.")
