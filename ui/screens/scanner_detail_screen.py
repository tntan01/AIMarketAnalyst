from __future__ import annotations

from html import escape

from config.paths import app_data_dir
from core.scanner_models import (
    BRANCH_BACKTEST_INVALID,
    BRANCH_BACKTEST_VALIDATED,
)
from core.reason_codes import REASON_CODE_MESSAGES
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QProgressBar,
    QScrollArea, QSizePolicy, QTabWidget, QTextEdit, QVBoxLayout,
    QWidget,
)
from controllers.journal_controller import JournalController
from services.storage_service import JsonStorage

from core.scanner_ranking_engine import _find_scenario_for_side
from ui.scanner_rr_formatters import (
    format_execution_zone_text,
    format_execution_zone_width,
    format_rr_trim_reason,
    format_source_zone_text,
)
from ui.components.chart_view import AnalysisChartView
from ui.rich_text import empty_state_html, set_rich_html
from ui.screens.shared import action_button, card, page_header
from ui.theme import chart_palette, semantic_role_for_color
from ui.theme.fonts import QSS_BODY, QSS_NUMBER, QSS_SMALL, QSS_SUBTITLE, QSS_TITLE
from ui.theme_manager import current_palette, is_light_theme, set_dynamic_property


# HTML style attributes in this screen use single quotes.  The shared QSS
# tokens quote font-family names, so strip only those quotes before embedding.
_HTML_BODY = QSS_BODY.replace("'", "")
_HTML_NUMBER = QSS_NUMBER.replace("'", "")
_HTML_SMALL = QSS_SMALL.replace("'", "")
_HTML_SUBTITLE = QSS_SUBTITLE.replace("'", "")
_HTML_TITLE = QSS_TITLE.replace("'", "")


# ---------------------------------------------------------------------------
# Translation maps for code constants → Vietnamese display
# ---------------------------------------------------------------------------

_VN_CODE = {
    # Reason codes
    "MACRO_ALIGNED": "Vĩ mô thuận",
    "MACRO_CONFLICT": "Vĩ mô xung đột",
    "MACRO_UNCLEAR": "Vĩ mô chưa rõ",
    # Penalty codes
    "CHOCH_AGAINST_DIRECTION": "CHOCH ngược hướng",
    # Common values
    "neutral": "trung lập",
    "conflict": "xung đột",
    "aligned": "thuận",
    "unclear": "chưa rõ",
}

_VN_MACRO = {
    "neutral": "trung lập",
    "conflict": "xung đột",
    "aligned": "thuận",
    "unclear": "chưa rõ",
    "": "trung lập",
}

_CANDIDATE_STATUS = {
    "READY_NOW": ("Đạt điều kiện tại lúc quét", "ready"),
    "WAITING_CONFIRMATION": ("Chờ xác nhận", "wait"),
    "WATCH_ZONE": ("Đang theo dõi vùng giá", "watch"),
    "OUT_OF_STRATEGY": ("Chưa đạt quy tắc giao dịch", "neutral"),
    "BLOCKED": ("Bị cổng an toàn chặn", "blocked"),
    "DATA_UNAVAILABLE": ("Không đủ dữ liệu để đánh giá", "data"),
}

_SCANNER_REASON_MESSAGES = {
    "SETUP_SCORE_BELOW_DEFAULT_MIN": "Điểm thiết lập thấp hơn ngưỡng Ready đang cấu hình.",
    "SETUP_SCORE_BELOW_MIN": "Điểm thiết lập thấp hơn ngưỡng của cấu hình Backtest.",
    "SCANNER_NOT_READY": "Pipeline chưa đánh giá thiết lập là sẵn sàng.",
    "DECISION_NOT_READY": "Decision Engine chưa cho trạng thái sẵn sàng giao dịch.",
    "ENTRY_NOT_CONFIRMED": "Điểm vào lệnh chưa được xác nhận.",
    "SCENARIO_NOT_READY": "Kịch bản của hướng được chọn chưa sẵn sàng.",
    "M15_NOT_STRICT": "M15 chưa xác nhận chặt.",
    "TRADE_PERMISSION_NOT_ALLOWED": "Quyền giao dịch tại thời điểm quét chưa được cho phép.",
    "TRADE_GATE_NOT_ALLOWED": "Cổng an toàn đang chặn giao dịch.",
    "TRADE_GATE_DECISION_CAP": "Cổng an toàn đang giới hạn quyết định ở mức theo dõi/chờ.",
    "EXPECTED_EFFECTIVE_RR_BELOW_MIN": "R:R sau chi phí thấp hơn mức tối thiểu.",
    "MISSING_SELECTED_SIDE_SCENARIO": "Không có kịch bản hợp lệ cho hướng được chọn.",
    "MISSING_SELECTED_SIDE": "Không xác định được hướng giao dịch.",
    "BACKTEST_CONFIG_INVALID": "Cấu hình Backtest không hợp lệ.",
    "STRUCTURAL_SMC_REJECT": "Không có vùng SMC canonical phù hợp; không tạo thiết lập giao dịch.",
    "NO_ACTIONABLE_SMC_ZONE": "Cả BUY và SELL đều không có vùng SMC canonical đủ điều kiện.",
    "NO_RAW_SMC_CANDIDATE": "Không phát hiện raw SMC candidate ở các khung thời gian yêu cầu.",
}


def _translate_codes(codes: list[str]) -> list[str]:
    """Translate reason/penalty code constants to Vietnamese display text."""
    result: list[str] = []
    for c in codes:
        result.append(_VN_CODE.get(c, c))
    return result



# ---------------------------------------------------------------------------

class ScannerDetailScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        from services.settings_service import SettingsService
        self.settings_service = app.settings_service if app else SettingsService()
        self.journal_controller = app.journal_controller if app else JournalController()
        self.row: dict[str, object] = {}
        self.scanner_result: dict[str, object] = {}
        self.setObjectName("FormScreen")
        self._build_ui()

    def _is_light_theme(self) -> bool:
        state = self.__dict__
        settings_service = state.get("settings_service")
        if settings_service is None:
            return bool(state.get("_light", False))
        return is_light_theme(settings_service)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        self.header_slot = QVBoxLayout()
        root.addLayout(self.header_slot)

        # ---- Tab widget: Tổng quan | Chẩn đoán | AI kiểm định ---------------
        self.tabs = QTabWidget()
        self.tabs.setObjectName("ContentTabs")

        # ---- Tab 1: Tổng quan (verdict + cards + chart + conditions) --------
        overview_tab = card()

        overview_container = QWidget()
        overview_layout = QHBoxLayout(overview_container)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(10)

        # --- Left container: button + trade panel + score panel + checklist ---
        left_container = QWidget()
        left_container.setMinimumWidth(200)
        left_col = QVBoxLayout(left_container)
        left_col.setSpacing(4)
        left_col.setContentsMargins(0, 0, 0, 0)

        # -- Button + Trade Panel + Score Panel + Checklist Panel --
        self.show_detail_btn = action_button("📋 Xem đầy đủ", primary=True, color="warning")
        self.show_detail_btn.setObjectName("ScannerDetailFullButton")
        self.show_detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show_detail_btn.setToolTip(
            "Xem bối cảnh kỹ thuật, vĩ mô, nhật ký và các điều kiện "
            "của kết quả quét"
        )
        self.show_detail_btn.clicked.connect(self._show_scan_detail_dialog)
        left_col.addWidget(self.show_detail_btn)

        # -- Panel: Số liệu giao dịch --
        self.trade_panel = QFrame()
        self.trade_panel.setObjectName("TradePanelCard")
        trade_panel_layout = QVBoxLayout(self.trade_panel)
        trade_panel_layout.setContentsMargins(10, 6, 10, 6)
        trade_panel_layout.setSpacing(2)
        left_col.addWidget(self.trade_panel)

        # -- Panel: Điểm phân tích --
        self.score_panel = QFrame()
        self.score_panel.setObjectName("ScorePanelCard")
        score_panel_layout = QVBoxLayout(self.score_panel)
        score_panel_layout.setContentsMargins(6, 4, 6, 4)
        score_panel_layout.setSpacing(2)
        left_col.addWidget(self.score_panel)

        # -- Panel: Điều kiện vào lệnh --
        self.checklist_panel = QFrame()
        self.checklist_panel.setObjectName("ChecklistPanelCard")
        checklist_panel_layout = QVBoxLayout(self.checklist_panel)
        checklist_panel_layout.setContentsMargins(6, 4, 6, 4)
        checklist_panel_layout.setSpacing(2)
        left_col.addWidget(self.checklist_panel)
        left_col.addStretch(1)

        overview_layout.addWidget(left_container, 25)

        # --- Right container: hero bar + chart ---
        right_container = QWidget()
        right_container.setMinimumWidth(360)
        right_col = QVBoxLayout(right_container)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(4)

        # -- Hero verdict bar --
        self.hero_bar = QLabel("")
        self.hero_bar.setObjectName("ScannerDetailHero")
        self.hero_bar.setWordWrap(False)
        self.hero_bar.setTextFormat(Qt.TextFormat.RichText)
        self.hero_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_col.addWidget(self.hero_bar)

        # -- Chart --
        self.chart = AnalysisChartView()
        self.chart_frame = QFrame()
        self.chart_frame.setObjectName("AnalysisChartFrame")
        cl = QVBoxLayout(self.chart_frame)
        cl.setContentsMargins(4, 4, 4, 4)
        cl.setSpacing(0)
        cl.addWidget(self.chart)
        right_col.addWidget(self.chart_frame, 1)

        overview_layout.addWidget(right_container, 75)
        self.overview_layout = overview_layout

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(overview_container)
        overview_tab.layout().addWidget(scroll)

        self.tabs.addTab(overview_tab, "📊 Tổng quan")

        # ---- Tab 2: Chẩn đoán (score + gate + checklist) ----------------
        diag_tab = card()
        self.diag_text = QTextEdit()
        self.diag_text.setObjectName("ScannerDetailText")
        self.diag_text.setReadOnly(True)
        diag_tab.layout().addWidget(self.diag_text, 1)
        self.tabs.addTab(diag_tab, "🔬 Chẩn đoán")

        # ---- Tab 3: Kiểm định AI ----------------------------------------
        audit_tab = card()
        audit_layout = audit_tab.layout()
        # Button row
        btn_row = QHBoxLayout()
        self.audit_btn = action_button("🔍 Chạy kiểm định AI", primary=True, color="warning")
        self.audit_btn.clicked.connect(self._run_ai_audit)
        self.audit_status = QLabel("")
        self.audit_status.setObjectName("ScannerAuditStatus")
        btn_row.addWidget(self.audit_btn)
        btn_row.addWidget(self.audit_status)
        btn_row.addStretch()
        audit_layout.addLayout(btn_row)
        # Result area
        self.audit_text = QTextEdit()
        self.audit_text.setObjectName("ScannerDetailText")
        self.audit_text.setReadOnly(True)
        audit_layout.addWidget(self.audit_text, 1)
        self.tabs.addTab(audit_tab, "🤖 Kiểm định AI")

        root.addWidget(self.tabs, 1)

        actions = QHBoxLayout()
        self.back_button = action_button("⬅️ Quay lại")
        self.save_button = action_button("💾 Lưu nhật ký", primary=True, color="success")
        self.export_button = action_button("📤 Xuất JSON")
        if self.navigate:
            self.back_button.clicked.connect(lambda: self.navigate("scanner"))
        self.save_button.clicked.connect(self._save_to_journal)
        self.export_button.clicked.connect(self._export_json)
        actions.addWidget(self.back_button)
        actions.addStretch(1)
        actions.addWidget(self.export_button)
        actions.addWidget(self.save_button)
        root.addLayout(actions)
        self._render()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.show_detail_btn.setFixedHeight(26)
        self.hero_bar.setFixedHeight(26)

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("ScannerDecisionSectionTitle")
        return label

    def _pill(self, text: str, state: str = "neutral") -> QLabel:
        label = QLabel(text)
        label.setObjectName("ScannerDecisionPill")
        label.setProperty("state", state)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return label

    def set_analysis_result(self, payload: dict[str, object]) -> None:
        self.row = dict(payload.get("scanner_row", {}) or {})
        self.scanner_result = dict(payload.get("scanner_result", {}) or {})
        self._render()

    @staticmethod
    def _as_dict(value: object) -> dict:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _number(value: object) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _score_text(value: object) -> str:
        number = ScannerDetailScreen._number(value)
        if number is None:
            return "--"
        return str(int(number)) if number.is_integer() else f"{number:.1f}"

    def _candidate_decision(self) -> dict:
        return self._as_dict(self.row.get("scanner_candidate_decision"))

    def _candidate_strategy(self) -> dict:
        return self._as_dict(self._candidate_decision().get("strategy"))

    def _candidate_execution(self) -> dict:
        return self._as_dict(self._candidate_decision().get("execution"))

    def _selected_side(self) -> str:
        decision = self._candidate_decision()
        raw_side = (
            decision.get("selected_side")
            if decision
            else self.row.get("selected_side")
        )
        side = str(raw_side or "").strip().lower()
        if side in {"buy", "sell"}:
            return side

        if decision:
            return ""

        # Compatibility only for old snapshots that predate the canonical
        # candidate contract.
        side = str(self.row.get("best_side") or "").strip().lower()
        if side in {"buy", "sell"}:
            return side
        bias = self._as_dict(self.row.get("direction_bias"))
        side = str(bias.get("best_side") or "").strip().lower()
        return side if side in {"buy", "sell"} else ""

    def _selected_side_evaluation(self) -> dict:
        decision = self._candidate_decision()
        selected = self._as_dict(decision.get("side_evaluation"))
        side = self._selected_side()
        if selected and (
            not side or str(selected.get("side") or "").lower() == side
        ):
            return selected
        sides = self._as_dict(decision.get("side_evaluations"))
        return self._as_dict(sides.get(side))

    def _selected_scenario(self, analysis: dict | None = None) -> dict:
        source = analysis if isinstance(analysis, dict) else self._as_dict(
            self.row.get("analysis_result")
        )
        scenarios = source.get("scenarios")
        if not isinstance(scenarios, list):
            return {}
        side = self._selected_side()
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                continue
            scenario_side = str(
                scenario.get("type")
                or scenario.get("side")
                or scenario.get("direction")
                or ""
            ).strip().lower()
            if side and scenario_side == side:
                return scenario
        if len(scenarios) == 1 and isinstance(scenarios[0], dict):
            return scenarios[0]
        return {}

    def _selected_price_vs_zone(self) -> str:
        """Return price position for the canonical selected-side zone."""
        decision = self._candidate_decision()
        side_eval = self._selected_side_evaluation()
        entry_zone = side_eval.get("entry_zone")
        if entry_zone is None:
            entry_zone = self._selected_scenario().get("entry_zone")

        if decision:
            analysis = self._as_dict(self.row.get("analysis_result"))
            technical = self._as_dict(analysis.get("technical"))
            price = self._number(technical.get("price"))
            atr = self._number(
                technical.get("atr_h4") or technical.get("atr_d1")
            )
            if (
                price is not None
                and isinstance(entry_zone, (list, tuple))
                and len(entry_zone) == 2
            ):
                low = self._number(entry_zone[0])
                high = self._number(entry_zone[1])
                if low is not None and high is not None:
                    low, high = min(low, high), max(low, high)
                    if low <= price <= high:
                        return "in_zone"
                    distance = low - price if price < low else price - high
                    if atr is not None and atr > 0 and distance <= atr * 0.5:
                        return "near_zone"
                    return "far"
            # A canonical row must not borrow the position calculated for a
            # different legacy best-side zone.
            return "unknown"

        return str(self.row.get("price_vs_zone") or "unknown").lower()

    def _canonical_status(self) -> str:
        decision = self._candidate_decision()
        raw_status = (
            decision.get("status")
            if decision
            else self.row.get("candidate_status")
        )
        raw = str(raw_status or "").strip().upper()
        if raw in _CANDIDATE_STATUS:
            return raw
        if decision:
            return "DATA_UNAVAILABLE"
        legacy = str(self.row.get("scanner_group") or "").strip().upper()
        legacy_map = {
            "READY": "READY_NOW",
            "READY_NOW": "READY_NOW",
            "WAIT": "WAITING_CONFIRMATION",
            "WAITING_CONFIRMATION": "WAITING_CONFIRMATION",
            "WATCH": "WATCH_ZONE",
            "WATCH_ZONE": "WATCH_ZONE",
            "BLOCKED": "BLOCKED",
        }
        return legacy_map.get(legacy, "DATA_UNAVAILABLE")

    def _canonical_setup_score(self) -> float | None:
        strategy = self._candidate_strategy()
        decision = self._candidate_decision()
        values = (
            (strategy.get("score_value"), decision.get("setup_score"))
            if decision
            else (
                self.row.get("setup_score"),
                self.row.get("final_score"),
            )
        )
        for value in values:
            number = self._number(value)
            if number is not None:
                return number
        return None

    def _required_min_score(self) -> float | None:
        strategy = self._candidate_strategy()
        values = (
            (strategy.get("min_score"),)
            if self._candidate_decision()
            else (self.row.get("min_score"),)
        )
        for value in values:
            number = self._number(value)
            if number is not None:
                return number
        return None

    def _effective_rr(self) -> float | None:
        strategy = self._candidate_strategy()
        side_eval = self._selected_side_evaluation()
        scenario = self._selected_scenario()
        values = (
            (
                strategy.get("expected_effective_rr"),
                side_eval.get("expected_effective_rr"),
            )
            if self._candidate_decision()
            else (
                self.row.get("expected_effective_rr_base"),
                scenario.get("expected_effective_rr_base"),
                self.row.get("expected_effective_rr"),
                scenario.get("expected_effective_rr"),
            )
        )
        for value in values:
            number = self._number(value)
            if number is not None:
                return number
        return None

    def _required_min_rr(self) -> float | None:
        strategy = self._candidate_strategy()
        values = (
            (strategy.get("min_rr"),)
            if self._candidate_decision()
            else (self.row.get("min_rr"),)
        )
        for value in values:
            number = self._number(value)
            if number is not None:
                return number
        return None

    def _scan_trade_allowed(self) -> bool | None:
        decision = self._candidate_decision()
        if decision:
            value = self._candidate_execution().get("trade_allowed")
        else:
            value = self.row.get("trade_allowed")
        return value if isinstance(value, bool) else None

    def _selected_macro_metrics(
        self,
    ) -> tuple[float | None, float | None, str]:
        """Return raw /30 macro score, confidence and status for selected side."""
        if self._candidate_decision():
            analysis = self._as_dict(self.row.get("analysis_result"))
            scores = self._as_dict(analysis.get("scenario_scores"))
            selected = self._as_dict(scores.get(self._selected_side()))
            return (
                self._number(selected.get("macro_raw")),
                self._number(selected.get("macro_confidence")),
                str(selected.get("macro_status") or "unclear").lower(),
            )
        return (
            self._number(self.row.get("macro_score")),
            self._number(self.row.get("macro_confidence")),
            str(self.row.get("macro_bias") or "unclear").lower(),
        )

    def _rollout_stage(self) -> str:
        stage = str(self.row.get("rollout_stage") or "").strip().upper()
        if stage:
            return stage
        scanner_result = self._as_dict(getattr(self, "scanner_result", {}))
        policy = self._as_dict(scanner_result.get("rollout_policy"))
        return str(policy.get("stage") or "UNKNOWN").strip().upper()

    def _rollout_display(self) -> str:
        stage = self._rollout_stage()
        return {
            "DISABLED": "TẮT · không gửi lệnh thật",
            "SHADOW": "SHADOW · chỉ quan sát, không gửi lệnh thật",
            "DEMO_LIMITED": "DEMO GIỚI HẠN",
            "DEMO_FULL": "DEMO ĐẦY ĐỦ",
            "CANARY": "CANARY · chạy thật giới hạn",
            "PRODUCTION": "PRODUCTION · chạy thật",
            "UNKNOWN": "CHƯA XÁC ĐỊNH",
            "INVALID": "CẤU HÌNH KHÔNG HỢP LỆ",
        }.get(stage, stage)

    def _candidate_reason_messages(self) -> list[str]:
        decision = self._candidate_decision()
        reasons = decision.get("reason_codes")
        if not decision and not isinstance(reasons, list):
            reasons = self.row.get("auto_trade_reason_codes")
        if not isinstance(reasons, list):
            return []
        return [
            REASON_CODE_MESSAGES.get(
                str(code),
                _SCANNER_REASON_MESSAGES.get(str(code), str(code)),
            )
            for code in reasons
            if str(code).strip()
        ]

    def _show_scan_detail_dialog(self) -> None:
        """Open a dialog showing all InfoCards and the entry checklist."""
        if not self.row:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Chưa có dữ liệu", "Chưa chọn mã nào từ bảng quét.")
            return

        light = self._is_light_theme()

        symbol = str(self.row.get("symbol", "--"))
        dlg = QDialog(self)
        dlg.setWindowTitle(f"📋 Chi tiết kết quả quét — {symbol}")
        dlg.setMinimumSize(880, 580)
        dlg.resize(1040, 680)
        dlg.setObjectName("ScanAnalysisDetailDialog")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # -----------------------------------------------------------------------
        # Header Layout
        # -----------------------------------------------------------------------
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)
        
        title_color = "#0f172a" if light else "#f8fafc"
        title = QLabel(f"<b style='{_HTML_TITLE}color:{title_color};'>📋 CHI TIẾT KẾT QUẢ QUÉT — {symbol}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        root.addLayout(header_layout)

        # Keep the decision summary on its own row. This prevents the title
        # and six status pills from being squeezed or clipped on smaller
        # screens.
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(8)

        # Overview pills use the canonical candidate contract. Raw BUY/SELL
        # bias is analysis context, not a recommendation to place an order.
        status = self._canonical_status()
        status_label, status_state = _CANDIDATE_STATUS[status]
        side = self._selected_side()
        bias_text = f"HƯỚNG: { {'buy': 'MUA', 'sell': 'BÁN'}.get(side, '--') }"
        pill_side_obj = {
            "buy": "SummaryPillBuy",
            "sell": "SummaryPillSell",
        }.get(side, "SummaryPillNeutral")

        bias_pill = QFrame()
        bias_pill.setObjectName(pill_side_obj)
        bias_pill_layout = QHBoxLayout(bias_pill)
        bias_pill_layout.setContentsMargins(8, 4, 8, 4)
        bias_lbl = QLabel(bias_text)
        bias_lbl.setObjectName("ScannerSummaryText")
        bias_lbl.setProperty("metricTone", side or "neutral")
        bias_pill_layout.addWidget(bias_lbl)
        summary_layout.addWidget(bias_pill)

        status_pill = QFrame()
        status_pill.setObjectName("SummaryPillStatus")
        status_pill_layout = QHBoxLayout(status_pill)
        status_pill_layout.setContentsMargins(8, 4, 8, 4)
        status_lbl = QLabel(status_label)
        status_lbl.setObjectName("ScannerSummaryText")
        status_lbl.setProperty(
            "metricTone",
            {
                "ready": "success",
                "wait": "warning",
                "watch": "warning",
                "blocked": "danger",
                "neutral": "neutral",
                "data": "muted",
            }[status_state],
        )
        status_pill_layout.addWidget(status_lbl)
        summary_layout.addWidget(status_pill)

        # Setup score of the canonical selected side.
        setup_text = self._score_text(self._canonical_setup_score())
        min_score_text = self._score_text(self._required_min_score())
        score_pill = QFrame()
        score_pill.setObjectName("SummaryPillScore")
        score_pill_layout = QHBoxLayout(score_pill)
        score_pill_layout.setContentsMargins(8, 4, 8, 4)
        score_lbl = QLabel(f"Setup: {setup_text}/{min_score_text}")
        score_lbl.setObjectName("ScannerSummaryText")
        score_lbl.setProperty("metricTone", "text")
        score_pill_layout.addWidget(score_lbl)
        summary_layout.addWidget(score_pill)

        # Effective R:R is used by Strategy Router; nominal R:R is not.
        effective_rr = self._effective_rr()
        min_rr = self._required_min_rr()
        rr_text = (
            f"{effective_rr:.2f}/{min_rr:.2f}"
            if effective_rr is not None and min_rr is not None
            else "--"
        )
        rr_pill = QFrame()
        rr_pill.setObjectName("SummaryPillRR")
        rr_pill_layout = QHBoxLayout(rr_pill)
        rr_pill_layout.setContentsMargins(8, 4, 8, 4)
        rr_lbl = QLabel(f"R:R thực: {rr_text}")
        rr_lbl.setObjectName("ScannerSummaryRR")
        rr_pill_layout.addWidget(rr_lbl)
        summary_layout.addWidget(rr_pill)

        # Scan-time permission is canonical. It still does not bypass rollout
        # or final execution revalidation.
        trade_allowed = self._scan_trade_allowed()
        perm_text = (
            "Cho phép tại lúc quét"
            if trade_allowed is True
            else "Không cho phép tại lúc quét"
            if trade_allowed is False
            else "Chưa có kết quả"
        )
        perm_pill = QFrame()
        perm_pill.setObjectName("SummaryPillPerm")
        perm_pill_layout = QHBoxLayout(perm_pill)
        perm_pill_layout.setContentsMargins(8, 4, 8, 4)
        perm_lbl = QLabel(perm_text)
        perm_lbl.setObjectName("ScannerSummaryText")
        perm_lbl.setProperty(
            "metricTone",
            "success"
            if trade_allowed is True
            else "danger"
            if trade_allowed is False
            else "neutral",
        )
        perm_pill_layout.addWidget(perm_lbl)
        summary_layout.addWidget(perm_pill)

        rollout_pill = QFrame()
        rollout_pill.setObjectName("SummaryPillRollout")
        rollout_layout = QHBoxLayout(rollout_pill)
        rollout_layout.setContentsMargins(8, 4, 8, 4)
        rollout_lbl = QLabel(self._rollout_display())
        rollout_lbl.setObjectName("ScannerSummaryRollout")
        rollout_layout.addWidget(rollout_lbl)
        summary_layout.addWidget(rollout_pill)
        summary_layout.addStretch(1)
        root.addLayout(summary_layout)

        # -----------------------------------------------------------------------
        # Scroll Area
        # -----------------------------------------------------------------------
        scroll = QScrollArea()
        scroll.setObjectName("ScannerDetailDialogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setObjectName("ScannerDetailDialogContent")
        
        # Main horizontal layout inside scroll area (2 columns)
        body_layout = QHBoxLayout(content)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)

        # Cột Trái (Technical & Macro)
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # Cột Phải (Checklist & Journal)
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        body_layout.addLayout(left_col, 1)
        body_layout.addLayout(right_col, 1)

        # Helper function to create standard small info cards
        def create_info_card(obj_name, title_txt, val_txt, val_color, tooltip_txt):
            card_widget = QFrame()
            card_widget.setObjectName(obj_name)
            card_w_layout = QVBoxLayout(card_widget)
            card_w_layout.setContentsMargins(12, 10, 12, 10)
            card_w_layout.setSpacing(2)
            card_widget.setToolTip(tooltip_txt)

            lbl = QLabel(title_txt)
            lbl.setObjectName("ScannerInfoLabel")
            lbl.setToolTip(tooltip_txt)

            val = QLabel(val_txt)
            val.setObjectName("ScannerInfoValue")
            set_dynamic_property(
                val,
                "metricTone",
                semantic_role_for_color(val_color),
            )
            val.setWordWrap(True)

            card_w_layout.addWidget(lbl)
            card_w_layout.addWidget(val)
            return card_widget

        # -----------------------------------------------------------------------
        # CỘT TRÁI - PHẦN 1: BỐI CẢNH KỸ THUẬT
        # -----------------------------------------------------------------------
        tech_title = QLabel("🔍 BỐI CẢNH KỸ THUẬT")
        tech_title.setObjectName("ScannerDialogSectionTitle")
        left_col.addWidget(tech_title)

        tech_grid = QGridLayout()
        tech_grid.setHorizontalSpacing(8)
        tech_grid.setVerticalSpacing(8)

        pos_val, _, pos_color = self._dialog_card_position()
        grp_val, grp_detail, grp_color = self._dialog_card_group()
        m15_val, _, m15_color = self._dialog_card_m15()

        card_pos = create_info_card("PriceCard", "VỊ TRÍ GIÁ", pos_val, pos_color, "Giá hiện tại đang ở đâu so với vùng vào lệnh đã xác định")
        card_grp = create_info_card("ScannerGroupCard", "TRẠNG THÁI QUÉT", grp_val, grp_color, grp_detail or "Phân loại mã theo mức độ sẵn sàng vào lệnh của bộ quét")
        card_m15 = create_info_card("M15Card", "XÁC NHẬN M15", m15_val, m15_color, "Độ chặt chẽ của tín hiệu xác nhận ở khung thời gian 15 phút")

        tech_grid.addWidget(card_pos, 0, 0)
        tech_grid.addWidget(card_grp, 0, 1)
        tech_grid.addWidget(card_m15, 0, 2)
        left_col.addLayout(tech_grid)

        # -----------------------------------------------------------------------
        # CỘT TRÁI - PHẦN 2: BỐI CẢNH VĨ MÔ
        # -----------------------------------------------------------------------
        macro_title = QLabel("🌐 BỐI CẢNH VĨ MÔ")
        macro_title.setObjectName("ScannerDialogSectionTitle")
        left_col.addWidget(macro_title)

        macro_card = QFrame()
        macro_card.setObjectName("MacroContextCard")
        macro_card_layout = QVBoxLayout(macro_card)
        macro_card_layout.setContentsMargins(14, 12, 14, 12)
        macro_card_layout.setSpacing(10)

        # Macro Score Header
        macro_num, macro_conf, macro_bias_raw = (
            self._selected_macro_metrics()
        )
        macro_dot = (
            "●"
            if macro_conf is not None and macro_conf >= 0.8
            else "○"
            if macro_conf is not None and macro_conf >= 0.5
            else "◌"
        )
        macro_bias_text = {
            "aligned": "Thuận",
            "conflict": "Xung đột",
            "divergent": "Xung đột",
            "neutral": "Trung lập",
            "unclear": "Chưa rõ"
        }.get(macro_bias_raw, macro_bias_raw.title() or "Chưa rõ")

        macro_hdr = QHBoxLayout()
        macro_hdr_lbl = QLabel("Điểm vĩ mô gốc")
        macro_hdr_lbl.setObjectName("ScannerInfoLabel")
        macro_hdr_val = QLabel(
            f"{macro_dot} {self._score_text(macro_num)}/30 "
            f"({macro_bias_text})"
        )
        macro_hdr_val.setObjectName("ScannerMacroScore")
        macro_hdr_val.setProperty(
            "metricTone",
            "success"
            if macro_num is not None and macro_num >= 22
            else "warning"
            if macro_num is not None and macro_num >= 15
            else "neutral",
        )
        macro_hdr.addWidget(macro_hdr_lbl)
        macro_hdr.addStretch(1)
        macro_hdr.addWidget(macro_hdr_val)
        macro_card_layout.addLayout(macro_hdr)

        # Macro Tiers Progress Bars
        md = self._get_macro_detail()
        tiers = [
            ("T1 · Lãi suất", md["t1"], 12, md["t1_reason"]),
            ("T2 · Lịch kinh tế", md["t2"], 9, md["t2_reason"]),
            ("T3 · Tâm lý", md["t3"], 12, md["t3_reason"]),
        ]

        for t_label, t_val, t_max, t_reason in tiers:
            tier_row = QVBoxLayout()
            tier_row.setSpacing(3)

            tier_info = QHBoxLayout()
            tier_lbl = QLabel(t_label)
            tier_lbl.setObjectName("ScannerTierLabel")
            tier_score = QLabel(f"{self._score_text(t_val)}/{t_max}")
            tier_score.setObjectName("ScannerTierScore")
            tier_info.addWidget(tier_lbl)
            tier_info.addStretch(1)
            tier_info.addWidget(tier_score)
            tier_row.addLayout(tier_info)

            # Styled QProgressBar
            bar = QProgressBar()
            bar.setObjectName("ScannerTierProgress")
            bar.setRange(0, t_max)
            bar.setValue(int(t_val) if isinstance(t_val, (int, float)) else 0)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            progress_tone = (
                "success"
                if isinstance(t_val, (int, float)) and t_val >= t_max * 0.7
                else "warning"
                if isinstance(t_val, (int, float)) and t_val >= t_max * 0.4
                else "neutral"
            )
            set_dynamic_property(bar, "metricTone", progress_tone)
            tier_row.addWidget(bar)

            if t_reason:
                reason_lbl = QLabel(t_reason)
                reason_lbl.setObjectName("MacroReasonLabel")
                reason_lbl.setWordWrap(True)
                tier_row.addWidget(reason_lbl)

            macro_card_layout.addLayout(tier_row)

        # Micro Indicators: Yield Spread & VIX
        d1 = md["t1_detail"]
        d3 = md["t3_detail"]
        indicator_parts = []
        if isinstance(d1, dict) and d1.get("yield_spread_2s10s") is not None:
            ys = d1.get("yield_spread_2s10s")
            steep = "dốc lên" if d1.get("yield_spread_steepening") else "phẳng"
            indicator_parts.append(f"Đường cong LS: <b>{ys:+.2f}</b> ({steep})")
        if isinstance(d3, dict) and d3.get("vix_level") is not None:
            vix = d3.get("vix_level")
            if vix < 15: vix_note = "thấp"
            elif vix < 20: vix_note = "bình thường"
            elif vix < 25: vix_note = "cao"
            elif vix < 30: vix_note = "rất cao"
            else: vix_note = "cực đoan"
            indicator_parts.append(f"VIX: <b>{vix:.1f}</b> ({vix_note})")

        if indicator_parts:
            ind_lbl = QLabel(" &nbsp;&bull;&nbsp; ".join(indicator_parts))
            ind_lbl.setObjectName("ScannerMacroIndicators")
            ind_lbl.setTextFormat(Qt.TextFormat.RichText)
            macro_card_layout.addWidget(ind_lbl)

        # Buy/Sell Reasons
        reasons_dict = md["reasons"]
        reasons_layout = QVBoxLayout()
        reasons_layout.setSpacing(4)
        has_reasons = False
        if isinstance(reasons_dict, dict):
            buy_r = reasons_dict.get("buy", "")
            sell_r = reasons_dict.get("sell", "")
            if buy_r:
                buy_lbl = QLabel(f"🟢 <b style='color:#10b981;'>MUA:</b> {buy_r}")
                buy_lbl.setObjectName("ScannerReasonText")
                buy_lbl.setWordWrap(True)
                buy_lbl.setTextFormat(Qt.TextFormat.RichText)
                reasons_layout.addWidget(buy_lbl)
                has_reasons = True
            if sell_r:
                sell_lbl = QLabel(f"🔴 <b style='color:#f43f5e;'>BÁN:</b> {sell_r}")
                sell_lbl.setObjectName("ScannerReasonText")
                sell_lbl.setWordWrap(True)
                sell_lbl.setTextFormat(Qt.TextFormat.RichText)
                reasons_layout.addWidget(sell_lbl)
                has_reasons = True

        if has_reasons:
            reasons_container = QWidget()
            reasons_container.setObjectName("TransparentWidget")
            reasons_container_layout = QVBoxLayout(reasons_container)
            reasons_container_layout.setContentsMargins(0, 4, 0, 0)
            reasons_container_layout.addLayout(reasons_layout)
            macro_card_layout.addWidget(reasons_container)

        left_col.addWidget(macro_card)
        left_col.addStretch(1)

        # -----------------------------------------------------------------------
        # CỘT PHẢI - PHẦN 3: HIỆU SUẤT NHẬT KÝ
        # -----------------------------------------------------------------------
        journal_title = QLabel("📔 HIỆU SUẤT NHẬT KÝ")
        journal_title.setObjectName("ScannerDialogSectionTitle")
        right_col.addWidget(journal_title)

        sample_val, _, sample_accent = self._dialog_card_journal_sample()
        exp_val, _, exp_accent = self._dialog_card_journal_exp()
        try:
            sample_num = int(sample_val)
        except (TypeError, ValueError):
            sample_num = 0

        journal_grid = QGridLayout()
        journal_grid.setHorizontalSpacing(8)
        journal_grid.setVerticalSpacing(8)

        card_sample = create_info_card("JournalSampleCard", "MẪU NHẬT KÝ", f"{sample_val} mẫu", "#9ca3af", "Số lệnh đã ghi nhật ký khớp với thiết lập tương tự")
        card_exp = create_info_card("JournalExpectancyCard", "KỲ VỌNG HỆ THỐNG", exp_val, exp_accent, "Kỳ vọng lợi nhuận trung bình theo R, tính từ lịch sử nhật ký")

        journal_grid.addWidget(card_sample, 0, 0)
        journal_grid.addWidget(card_exp, 0, 1)
        right_col.addLayout(journal_grid)

        # Warning Banner for small sample sizes
        if sample_num < 20:
            warn_frame = QFrame()
            warn_frame.setObjectName("ScannerWarningBanner")
            warn_l = QHBoxLayout(warn_frame)
            warn_l.setContentsMargins(10, 6, 10, 6)
            warn_l.setSpacing(6)
            
            warn_icon = QLabel("⚠️")
            warn_icon.setObjectName("ScannerWarningIcon")
            warn_txt = QLabel("Mẫu quá ít, kỳ vọng chưa đáng tin cậy")
            warn_txt.setObjectName("ScannerWarningText")
            warn_l.addWidget(warn_icon)
            warn_l.addWidget(warn_txt)
            warn_l.addStretch(1)
            right_col.addWidget(warn_frame)

        # -----------------------------------------------------------------------
        # CỘT PHẢI - PHẦN 4: ĐIỀU KIỆN VÀO LỆNH (CHECKLIST)
        # -----------------------------------------------------------------------
        checklist_title = QLabel("🔍 ĐIỀU KIỆN VÀO LỆNH (CHECKLIST)")
        checklist_title.setObjectName("ScannerDialogSectionTitle")
        right_col.addWidget(checklist_title)

        checklist_card = QFrame()
        checklist_card.setObjectName("ChecklistCard")
        cl_layout = QVBoxLayout(checklist_card)
        cl_layout.setContentsMargins(12, 12, 12, 12)
        cl_layout.setSpacing(6)

        for item in self._build_entry_checklist():
            state = str(item.get("state") or "unknown")
            passed = state == "pass"
            row_card = QFrame()
            row_card.setObjectName(
                "ChecklistRowCardPass"
                if passed
                else "ChecklistRowCardFail"
                if state == "fail"
                else "ChecklistRowCardUnknown"
            )
            
            row_l = QHBoxLayout(row_card)
            row_l.setContentsMargins(10, 6, 10, 6)
            row_l.setSpacing(8)
            row_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            icon_lbl = QLabel(
                "✅" if passed else "❌" if state == "fail" else "➖"
            )
            icon_lbl.setObjectName("ScannerChecklistIcon")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            row_l.addWidget(icon_lbl)

            text_lbl = QLabel(item["label"])
            text_lbl.setObjectName("ScannerChecklistText")
            text_lbl.setProperty("checkState", state)
            text_lbl.setWordWrap(True)
            row_l.addWidget(text_lbl, 1)

            cl_layout.addWidget(row_card)

        right_col.addWidget(checklist_card)
        right_col.addStretch(1)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = action_button("✖ Đóng")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        dlg.exec()

    # ---------------------------------------------------------------------------
    # Dialog card value helpers — read from self.row, return (value, detail, accent)
    # ---------------------------------------------------------------------------

    def _dialog_card_best(self) -> tuple[str, str, str]:
        best = self.row.get("best_score", "--")
        rating = self._score_rating(int(best) if str(best).isdigit() else 0)
        return f"{best}/100", rating, "#ea580c"

    def _dialog_card_buysell(self) -> tuple[str, str, str]:
        buy_s = self.row.get("buy_score", "--")
        sell_s = self.row.get("sell_score", "--")
        bias = self.row.get("direction_bias", {})
        side_label = ""
        if isinstance(bias, dict):
            side = str(bias.get("best_side", ""))
            clarity = "rõ" if bias.get("is_clear_bias") else "TB"
            side_label = f"{'MUA' if side == 'buy' else 'BÁN' if side == 'sell' else '?'} {clarity}"
        return f"{buy_s} / {sell_s}", side_label, "#fb7185"

    def _dialog_card_final(self) -> tuple[str, str, str]:
        final_v = self.row.get("final_score", "--")
        return (f"{final_v}/100",
                self._score_rating(int(final_v) if str(final_v).isdigit() else 0),
                "#10b981")

    def _dialog_card_gap(self) -> tuple[str, str, str]:
        gap = self.row.get("score_gap", "--")
        bias = self.row.get("direction_bias", {})
        min_gap = str(bias.get("min_gap", "10")) if isinstance(bias, dict) else "10"
        return self._compact_number(gap), f"tối thiểu {min_gap}", "#f59e0b"

    def _dialog_card_macro(self) -> tuple[str, str, str]:
        macro_num, conf, macro_raw = self._selected_macro_metrics()
        dot = (
            "●"
            if conf is not None and conf >= 0.8
            else "○"
            if conf is not None and conf >= 0.5
            else "◌"
        )
        accent = (
            "#10b981"
            if macro_num is not None and macro_num >= 22
            else "#f59e0b"
            if macro_num is not None and macro_num >= 15
            else "#94a3b8"
        )
        bias = {
            "aligned": "Thuận",
            "conflict": "Xung đột",
            "divergent": "Xung đột",
            "neutral": "Trung lập",
            "unclear": "Chưa rõ"
        }.get(macro_raw, macro_raw.title() or "Chưa rõ")

        # Build detailed HTML for the full-detail dialog
        md = self._get_macro_detail()
        side = md["best_side"]
        parts: list[str] = []

        tiers = [
            ("T1 · Lãi suất", md["t1"], 12, md["t1_reason"]),
            ("T2 · Lịch kinh tế", md["t2"], 9, md["t2_reason"]),
            ("T3 · Tâm lý", md["t3"], 12, md["t3_reason"]),
        ]
        for label, score_val, max_val, reason in tiers:
            bar = self._tier_bar(score_val, max_val, True)  # light=True for HTML
            parts.append(
                f"<span style='{_HTML_SMALL}color:#6b7280;'>{label}</span> "
                f"<span style='{_HTML_NUMBER}'>{bar} "
                f"{self._score_text(score_val)}/{max_val}</span>"
                f"<br><span style='{_HTML_SMALL}color:#9ca3af;margin-left:8px;'>{reason}</span>"
            )

        # --- Sub-components ---
        d1 = md["t1_detail"]
        if side and isinstance(d1, dict) and d1:
            comps = d1.get("components", {})
            if isinstance(comps, dict):
                rd = comps.get("rate_diff", {})
                rt = comps.get("rate_trend", {})
                st = comps.get("stance", {})
                for sub_label, sub_dict, sub_max in [
                    ("Chênh lệch LS", rd, 4), ("Xu hướng", rt, 4), ("Lập trường", st, 4),
                ]:
                    sv = int(sub_dict.get(side, 0) or 0)
                    parts.append(
                        f"<span style='{_HTML_SMALL}color:#9ca3af;margin-left:8px;'>"
                        f"  {sub_label} {self._tier_bar(sv, sub_max, True)} {sv}/{sub_max}</span>"
                    )
            ys = d1.get("yield_spread_2s10s")
            if ys is not None:
                steep = "dốc lên" if d1.get("yield_spread_steepening") else "phẳng"
                parts.append(
                    f"<span style='{_HTML_SMALL}color:#9ca3af;margin-left:8px;'>"
                    f"Đường cong LS: {ys:+.2f} ({steep})</span>"
                )

        d3 = md["t3_detail"]
        if side and isinstance(d3, dict) and d3:
            comps = d3.get("components", {})
            if isinstance(comps, dict):
                rs = comps.get("risk_sentiment", {})
                geo = comps.get("geopolitical", {})
                for sub_label, sub_dict, sub_max in [
                    ("Tâm lý TT", rs, 8), ("Địa chính trị", geo, 4),
                ]:
                    sv = int(sub_dict.get(side, 0) or 0)
                    parts.append(
                        f"<span style='{_HTML_SMALL}color:#9ca3af;margin-left:8px;'>"
                        f"  {sub_label} {self._tier_bar(sv, sub_max, True)} {sv}/{sub_max}</span>"
                    )
            vix = d3.get("vix_level")
            if vix is not None:
                if vix < 15: vix_note = "thấp"
                elif vix < 20: vix_note = "bình thường"
                elif vix < 25: vix_note = "cao"
                elif vix < 30: vix_note = "rất cao"
                else: vix_note = "cực đoan"
                parts.append(
                    f"<span style='{_HTML_SMALL}color:#9ca3af;margin-left:8px;'>"
                    f"VIX {vix:.1f} · {vix_note}</span>"
                )

        # --- BUY / SELL reasons ---
        reasons = md["reasons"]
        if isinstance(reasons, dict):
            buy_r = reasons.get("buy", "")
            sell_r = reasons.get("sell", "")
            if buy_r:
                parts.append(
                    f"<br><span style='{_HTML_SMALL}font-weight:bold;color:#ea580c;'>MUA:</span> "
                    f"<span style='{_HTML_SMALL}color:#9ca3af;'>{buy_r}</span>"
                )
            if sell_r:
                parts.append(
                    f"<span style='{_HTML_SMALL}font-weight:bold;color:#f43f5e;'>BÁN:</span> "
                    f"<span style='{_HTML_SMALL}color:#9ca3af;'>{sell_r}</span>"
                )

        detail = f"{bias}<br><br>{'<br>'.join(parts)}" if parts else bias
        return f"{dot} {self._score_text(macro_num)}/30", detail, accent

    def _dialog_card_rr(self) -> tuple[str, str, str]:
        scenario = self._selected_scenario()
        if self._candidate_decision():
            rr = scenario.get("risk_reward") or "--"
            rr_range = scenario.get("risk_reward_range")
        else:
            rr = self._rr_main_text()
            rr_range = self._rr_field("risk_reward_range")
        eff_rr = self._effective_rr()
        min_rr = self._required_min_rr()
        if not self._candidate_decision():
            if rr == "N/A":
                return (
                    "N/A",
                    "Chưa có TP1 hợp lệ để tính R:R.",
                    "#94a3b8",
                )
            detail = f"danh nghĩa {rr}"
            if eff_rr is not None:
                detail += f"; base sau spread ~{eff_rr:.1f}"
            if min_rr is not None:
                detail += f"; tối thiểu {min_rr:.2f}"
            return str(rr), detail, "#ea580c"
        primary = (
            f"{eff_rr:.2f}"
            if eff_rr is not None
            else "--"
        )
        if rr_range and isinstance(rr_range, dict):
            worst = rr_range.get("worst")
            if worst is not None:
                best = self._number(rr_range.get("best"))
                detail = (
                    f"danh nghĩa {rr}; dải {worst:.1f}–"
                    f"{best:.1f}" if best is not None else f"danh nghĩa {rr}"
                )
                if min_rr is not None:
                    detail += f"; tối thiểu {min_rr:.2f}"
                return primary, detail, "#ea580c"
        detail = f"danh nghĩa {rr}"
        if min_rr is not None:
            detail += f"; tối thiểu {min_rr:.2f}"
        return primary, detail, "#ea580c"

    def _best_detail_scenario(self) -> dict[str, object]:
        analysis = self.row.get("analysis_result") if isinstance(self.row, dict) else None
        if not isinstance(analysis, dict):
            return {}
        scenarios = analysis.get("scenarios")
        if not isinstance(scenarios, list):
            return {}
        best_side = str(self.row.get("best_side") or "").strip().lower()
        scenario = _find_scenario_for_side(
            scenarios,
            best_side,
            fallback_to_first=best_side not in {"buy", "sell"},
        )
        return scenario if isinstance(scenario, dict) else {}

    def _rr_field(self, key: str) -> object:
        scenario = self._best_detail_scenario()
        value = scenario.get(key)
        if value is not None and value != "":
            return value
        best_side = str(self.row.get("best_side") or "").strip().lower()
        if best_side in {"buy", "sell"} and not scenario:
            return None
        value = self.row.get(key)
        if value is not None and value != "":
            return value
        return None

    def _plan_field(self, key: str) -> object:
        scenario = self._best_detail_scenario()
        if scenario:
            return scenario.get(key)
        best_side = str(self.row.get("best_side") or "").strip().lower()
        return None if best_side in {"buy", "sell"} else self.row.get(key)

    def _rr_context(self) -> dict[str, object]:
        keys = (
            "risk_reward",
            "risk_reward_range",
            "risk_reward_effective_range",
            "expected_effective_rr",
            "expected_effective_rr_base",
        )
        return {key: self._rr_field(key) for key in keys}

    def _has_entry_without_rr(self) -> bool:
        entry_zone = self._plan_field("entry_zone")
        return bool(entry_zone)

    def _rr_main_text(self) -> str:
        rr = self._rr_field("risk_reward")
        if rr:
            return str(rr)
        rr_range = self._rr_field("risk_reward_range")
        if isinstance(rr_range, dict):
            try:
                best = rr_range.get("best")
                if best is not None:
                    return f"1:{float(best):.1f}"
            except (TypeError, ValueError):
                pass
        if self._has_entry_without_rr():
            return "N/A"
        return "--"

    def _dialog_card_sl(self) -> tuple[str, str, str]:
        if self._has_no_entry_zone():
            return "--", "", "#94a3b8"
        sl = (
            self._selected_side_evaluation().get("stop_loss")
            or self.row.get("stop_loss")
        )
        if isinstance(sl, (int, float)):
            return f"{sl:.5f}", "", "#e11d48"
        return "--", "", "#94a3b8"

    def _dialog_card_tp(self) -> tuple[str, str, str]:
        if self._has_no_entry_zone():
            return "--", "", "#94a3b8"
        tp = (
            self._selected_side_evaluation().get("take_profit")
            or self.row.get("take_profit")
        )
        if isinstance(tp, list) and tp:
            tp1 = f"{tp[0]:.5f}"
            tp2 = f"TP2: {tp[1]:.5f}" if len(tp) > 1 else ""
            return tp1, tp2, "#10b981"
        if isinstance(tp, (int, float)):
            return f"{tp:.5f}", "", "#10b981"
        return "--", "", "#94a3b8"

    def _dialog_card_entry(self) -> tuple[str, str, str]:
        val = self._entry_status_display()
        accent = "#22c55e" if "Đã xác nhận" in val else "#fbbf24"
        return val, "", accent

    def _dialog_card_position(self) -> tuple[str, str, str]:
        price_zone = self._selected_price_vs_zone()
        zone_map = {"in_zone": "Trong vùng", "near_zone": "Gần vùng", "far": "Còn xa", "unknown": "Chưa rõ"}
        val = zone_map.get(price_zone, "Chưa rõ" if price_zone in ("unknown", "--", "") else price_zone.title())
        return val, "", "#f59e0b"

    def _dialog_card_m15(self) -> tuple[str, str, str]:
        m15_raw = self._m15_text().lower()
        m15_map = {"strict": "Chặt chẽ", "loose": "Lỏng lẻo", "chưa xác nhận": "Chưa xác nhận"}
        val = m15_map.get(m15_raw, m15_raw.title())
        accent = "#10b981" if m15_raw == "strict" else ("#f59e0b" if m15_raw == "loose" else "#e11d48")
        return val, "", accent

    def _dialog_card_group(self) -> tuple[str, str, str]:
        status = self._canonical_status()
        label, state = _CANDIDATE_STATUS[status]
        accent = {
            "ready": "#10b981",
            "wait": "#f59e0b",
            "watch": "#f59e0b",
            "neutral": "#94a3b8",
            "blocked": "#e11d48",
            "data": "#64748b",
        }[state]
        detail = " | ".join(self._candidate_reason_messages()[:4])
        return label, detail, accent

    def _dialog_card_regime(self) -> tuple[str, str, str]:
        regime = str(self.row.get("market_regime") or "--").lower()
        regime_map = {"trend_up": "Tăng", "trend_down": "Giảm", "range": "Đi ngang",
                      "volatile": "Biến động", "unknown": "Chưa rõ", "--": "--"}
        return regime_map.get(regime, regime.title()), "", "#fb7185"

    def _dialog_card_permission(self) -> tuple[str, str, str]:
        allowed = self._scan_trade_allowed()
        if allowed is True:
            return "Được phép tại lúc quét", "", "#10b981"
        if allowed is False:
            return "Không được phép tại lúc quét", "", "#e11d48"
        return "Chưa có kết quả", "", "#94a3b8"

    def _dialog_card_journal_sample(self) -> tuple[str, str, str]:
        sample = self.row.get("journal_sample_size", 0)
        try:
            val = str(int(sample))
        except (TypeError, ValueError):
            val = "0"
        return val, "", "#9ca3af"

    def _dialog_card_journal_exp(self) -> tuple[str, str, str]:
        exp_r = self.row.get("journal_expectancy_r")
        try:
            exp_num = float(exp_r)
            text = f"{exp_num:.2f}R"
            accent = "#10b981" if exp_num > 0 else ("#e11d48" if exp_num < 0 else "#94a3b8")
        except (TypeError, ValueError):
            text = "--"
            accent = "#94a3b8"
        return text, "", accent



    def _render(self) -> None:
        while self.header_slot.count():
            item = self.header_slot.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        symbol = str(self.row.get("symbol", "Chưa chọn"))
        self.header_slot.addWidget(
            page_header(
                "Chi tiết kết quả quét",
                "",
                symbol,
            )
        )
        
        self._refresh_hero()
        self._refresh_trade_panel()
        self._refresh_score_panel()
        self._refresh_checklist_panel()
        self._refresh_chart()
        self._refresh_diagnostics()
        self._refresh_ai_audit()

    def _refresh_chart(self) -> None:
        if not hasattr(self, "chart"):
            return
        analysis_result = self.row.get("analysis_result") if self.row else None
        if not isinstance(analysis_result, dict):
            self.chart.show_empty()
            return
        try:
            from core.chart_payload import build_full_chart_payload

            symbol = str(analysis_result.get("symbol") or self.row.get("symbol") or "")
            payload = build_full_chart_payload(
                symbol,
                analysis_result,
                active_timeframe="D1",
            )
            
            # Inject current theme to payload
            light = self._is_light_theme()
            payload["theme"] = "light" if light else "dark"
            payload["palette"] = chart_palette(current_palette())
            
            self.chart.set_payload(payload)
        except Exception:
            self.chart.show_error("Không thể tạo dữ liệu biểu đồ từ kết quả quét.")

    def refresh_theme_styles(self) -> None:
        """Keep the embedded WebEngine chart in sync with the active theme."""

        self.show_detail_btn.setFixedHeight(26)
        self.hero_bar.setFixedHeight(26)
        if hasattr(self, "chart"):
            self.chart.refresh_theme(current_palette())

    def _refresh_hero(self) -> None:
        """Render the canonical Scanner verdict, never a raw directional bias."""
        if not self.row:
            self.hero_bar.setText("")
            self.hero_bar.hide()
            return

        status = self._canonical_status()
        status_label, visual_state = _CANDIDATE_STATUS[status]

        side = self._selected_side()
        side_text = {"buy": "MUA", "sell": "BÁN"}.get(
            side,
            "CHƯA XÁC ĐỊNH",
        )
        setup = self._score_text(self._canonical_setup_score())
        min_score = self._score_text(self._required_min_score())
        score_text = (
            f"Setup {setup}/{min_score}"
            if min_score != "--"
            else f"Setup {setup}"
        )
        rollout_text = self._rollout_display()
        status_text = (
            f"{status_label.upper()} · Hướng phân tích: {side_text} · "
            f"{score_text} · {rollout_text}"
        )

        set_dynamic_property(
            self.hero_bar,
            "candidateState",
            visual_state,
        )

        self.hero_bar.setText(status_text)
        reasons = self._candidate_reason_messages()
        self.hero_bar.setToolTip(
            "\n".join(reasons[:6])
            if reasons
            else (
                "Đây là trạng thái chuẩn của Scanner tại thời điểm quét; "
                "không phải xác nhận đặt lệnh cuối cùng."
            )
        )
        self.hero_bar.show()

    # ------------------------------------------------------------------
    # Macro section (trade panel)
    # ------------------------------------------------------------------

    @staticmethod
    def _tier_bar(value: object, max_val: int, light: bool) -> str:
        """Segmented progress bar using Unicode block characters."""
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = 0.0
        ratio = max(0.0, min(1.0, numeric_value / max(max_val, 1)))
        total_segs = 10
        filled = max(0, min(total_segs, round(ratio * total_segs)))
        empty = total_segs - filled
        if numeric_value >= max_val * 0.7:
            color = "#10b981"
        elif numeric_value >= max_val * 0.4:
            color = "#f59e0b"
        else:
            color = "#94a3b8"
        fill = f"<span style='color:{color};'>{'█' * filled}</span>"
        emp = f"<span style='color:{'#e5e7eb' if light else '#334155'};'>{'░' * empty}</span>"
        return fill + emp

    def _get_macro_detail(self) -> dict:
        """Safely extract tier detail from analysis_result with defaults."""
        default = {"buy": None, "sell": None, "detail": {}}
        ar = (self.row or {}).get("analysis_result", {}) or {}
        td = ar.get("macro", {}).get("macro_tier_detail", {})
        dc = ar.get("macro", {}).get("driver_context", {})

        t1 = td.get("tier1_interest_rate", default) if isinstance(td, dict) else default
        t2 = td.get("tier2_calendar", default) if isinstance(td, dict) else default
        t3 = td.get("tier3_sentiment", default) if isinstance(td, dict) else default
        reasons = dc.get("macro_alignment_reasons", {}) if isinstance(dc, dict) else {}
        side = self._selected_side()

        d1 = t1.get("detail", {}) if isinstance(t1, dict) else {}
        d2 = t2.get("detail", {}) if isinstance(t2, dict) else {}
        d3 = t3.get("detail", {}) if isinstance(t3, dict) else {}

        # Tier 1 short reason
        base = (self.row or {}).get("symbol", "EUR/USD").split("/")[0] if self.row else "BASE"
        quote = (self.row or {}).get("symbol", "EUR/USD").split("/")[-1] if self.row else "QUOTE"
        br = d1.get("base_rate", "--") if isinstance(d1, dict) else "--"
        qr = d1.get("quote_rate", "--") if isinstance(d1, dict) else "--"
        bs = d1.get("base_stance", "--") if isinstance(d1, dict) else "--"
        qs = d1.get("quote_stance", "--") if isinstance(d1, dict) else "--"
        
        stance_map = {"hawkish": "Thắt chặt", "dovish": "Nới lỏng", "neutral": "Trung tính"}
        bs_vn = stance_map.get(str(bs).lower(), bs)
        qs_vn = stance_map.get(str(qs).lower(), qs)
        t1_reason = (
            f"{base} {br} ({bs_vn}) so với {quote} {qr} ({qs_vn})"
            if d1
            else "Chưa có dữ liệu lãi suất."
        )

        # Tier 2 short reason
        bc = d2.get("base_event_count", 0) if isinstance(d2, dict) else 0
        qc = d2.get("quote_event_count", 0) if isinstance(d2, dict) else 0
        t2_reason = (
            f"{base}: {bc} sự kiện · {quote}: {qc} sự kiện"
            if d2
            else "Chưa có dữ liệu lịch kinh tế."
        )

        # Tier 3 short reason
        sent = d3.get("risk_sentiment", "neutral") if isinstance(d3, dict) else "neutral"
        sent_map = {"risk_on": "Chấp nhận rủi ro", "risk_off": "Né tránh rủi ro", "neutral": "Trung tính"}
        vix = d3.get("vix_level") if isinstance(d3, dict) else None
        hs = d3.get("hotspot_count", 0) if isinstance(d3, dict) else 0
        vix_str = f"VIX {vix:.1f} · " if vix is not None else ""
        t3_reason = (
            f"{sent_map.get(sent, sent)} · {vix_str}{hs} điểm nóng"
            if d3
            else "Chưa có dữ liệu tâm lý thị trường."
        )

        return {
            "best_side": side,
            "t1": (
                self._number(t1.get(side))
                if side and isinstance(t1, dict)
                else None
            ),
            "t2": (
                self._number(t2.get(side))
                if side and isinstance(t2, dict)
                else None
            ),
            "t3": (
                self._number(t3.get(side))
                if side and isinstance(t3, dict)
                else None
            ),
            "t1_reason": t1_reason,
            "t2_reason": t2_reason,
            "t3_reason": t3_reason,
            "t1_detail": d1,
            "t2_detail": d2,
            "t3_detail": d3,
            "reasons": reasons,
        }

    def _refresh_trade_panel(self) -> None:
        """Cập nhật panel Số liệu giao dịch ở cột phải tab Tổng quan."""
        layout = self.trade_panel.layout()
        self._clear_layout(layout)

        title = QLabel("🎯 Số liệu giao dịch")
        title.setObjectName("ScannerPanelTitle")
        layout.addWidget(title)

        if not self.row:
            layout.addWidget(QLabel("—"))
            return

        entry_val, _, _ = self._dialog_card_entry()
        sl_val, _, _ = self._dialog_card_sl()
        tp_val, tp_detail, _ = self._dialog_card_tp()
        tp2_val = tp_detail.removeprefix("TP2: ") if tp_detail else "--"
        rr_val, rr_detail, _ = self._dialog_card_rr()
        regime_val, _, _ = self._dialog_card_regime()
        side_text = {
            "buy": "MUA",
            "sell": "BÁN",
        }.get(self._selected_side(), "Chưa xác định")

        entry_ok = (
            str(
                self._selected_side_evaluation().get("entry_status")
                or self.row.get("entry_status")
                or ""
            ).lower()
            == "confirmed_entry"
        )
        entry_tone = "success" if entry_ok else "warning"

        rows = [
            ("Hướng phân tích", side_text, self._selected_side() or "neutral"),
            ("Vùng vào lệnh", entry_val, entry_tone),
            ("Stop Loss", sl_val, "danger"),
            ("TP1", tp_val, "success"),
            ("TP2", tp2_val, "success"),
            ("R:R thực", rr_val, "warning"),
            ("Chế độ TT", regime_val, "text"),
        ]

        for label_text, value_text, tone in rows:
            row_w = QWidget()
            row_w.setObjectName("TransparentWidget")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setObjectName("ScannerPanelLabel")
            val = QLabel(value_text)
            val.setObjectName("ScannerPanelValue")
            val.setProperty("metricTone", tone)
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            val.setWordWrap(True)
            row_l.addWidget(lbl, 1)
            row_l.addWidget(val, 1)
            if label_text == "R:R thực":
                row_w.setToolTip(rr_detail)
            layout.addWidget(row_w)

    def _refresh_score_panel(self) -> None:
        """Cập nhật panel Điểm phân tích ở cột phải tab Tổng quan."""
        layout = self.score_panel.layout()
        self._clear_layout(layout)

        title = QLabel("📊 Điểm phân tích")
        title.setObjectName("ScannerPanelTitle")
        layout.addWidget(title)

        if not self.row:
            layout.addWidget(QLabel("—"))
            return

        status = self._canonical_status()
        status_label, status_state = _CANDIDATE_STATUS[status]
        if status == "OUT_OF_STRATEGY":
            status_label = "Chưa đạt quy tắc GD"
        status_tone = {
            "ready": "success",
            "wait": "warning",
            "watch": "warning",
            "neutral": "neutral",
            "blocked": "danger",
            "data": "muted",
        }[status_state]
        setup = self._score_text(self._canonical_setup_score())
        min_score = self._score_text(self._required_min_score())
        opportunity = self._score_text(self.row.get("opportunity_rank"))
        evidence = self._score_text(self.row.get("evidence_confidence"))
        execution = self._score_text(self.row.get("execution_readiness"))
        rows = [
            ("Trạng thái", status_label, status_tone),
            ("Điểm thiết lập", f"{setup}/{min_score}", "info"),
            ("Ưu tiên cơ hội", f"{opportunity}/100", "accent"),
            ("Bằng chứng", f"{evidence}/100", "text"),
            ("Mức sẵn sàng", f"{execution}/100", "text"),
            (
                "Chế độ chạy",
                self._rollout_display(),
                "info",
            ),
        ]

        for label_text, value_text, tone in rows:
            row_w = QWidget()
            row_w.setObjectName("TransparentWidget")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setObjectName("ScannerPanelLabel")
            val = QLabel(value_text)
            val.setObjectName("ScannerPanelValue")
            val.setProperty("metricTone", tone)
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            val.setWordWrap(True)
            row_l.addWidget(lbl, 1)
            row_l.addWidget(val, 1)
            layout.addWidget(row_w)

    @staticmethod
    def _clear_layout(layout: QLayout | None) -> None:
        """Recursively clear a QLayout including child layouts and widgets."""
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                child_lay = item.layout()
                ScannerDetailScreen._clear_layout(child_lay)
                child_lay.deleteLater()

    def _refresh_checklist_panel(self) -> None:
        """Fill the checklist panel with 7 compact entry condition items."""
        if not hasattr(self, "checklist_panel"):
            return

        layout = self.checklist_panel.layout()
        self._clear_layout(layout)

        title = QLabel("🔍 Điều kiện vào lệnh")
        title.setObjectName("ScannerPanelTitle")
        layout.addWidget(title)

        if not self.row:
            layout.addWidget(QLabel("—"))
            return

        items = self._build_entry_checklist()
        if not items:
            layout.addWidget(QLabel("—"))
            return

        SHORT_NAMES = [
            "Chiến lược", "Điểm setup", "Entry",
            "Vùng giá", "M15", "R:R thực", "Quyền quét",
        ]

        fail_count = sum(
            1 for item in items[:7] if item.get("state") == "fail"
        )
        unknown_count = sum(
            1 for item in items[:7] if item.get("state") == "unknown"
        )
        if fail_count >= 1:
            summary = QLabel(f"⚠️ {fail_count}/7 điều kiện chưa đạt")
            summary.setObjectName("ScannerChecklistSummary")
            summary.setProperty("checkState", "fail")
            layout.addWidget(summary)
        elif unknown_count:
            summary = QLabel(
                f"➖ {unknown_count}/7 điều kiện chưa có dữ liệu"
            )
            summary.setObjectName("ScannerChecklistSummary")
            summary.setProperty("checkState", "unknown")
            layout.addWidget(summary)

        # 2-column grid for compact display
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnMinimumWidth(0, 100)
        grid.setColumnMinimumWidth(1, 100)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(1)
        for i, item_data in enumerate(items[:7]):
            state = str(item_data.get("state") or "unknown")
            passed = state == "pass"
            full_label = item_data["label"]
            short_name = SHORT_NAMES[i] if i < len(SHORT_NAMES) else full_label[:12]
            icon = "✅" if passed else "❌" if state == "fail" else "➖"
            row_i, col_i = divmod(i, 2) if i < 6 else (3, 0)
            # The final permission item spans the full width.
            if i == 6:
                item_w = QWidget()
                item_w.setObjectName("TransparentWidget")
                item_l = QHBoxLayout(item_w)
                item_l.setContentsMargins(0, 0, 0, 0)
                item_l.setSpacing(3)
                icon_lbl = QLabel(icon)
                icon_lbl.setObjectName("ScannerCompactIcon")
                name_lbl = QLabel(short_name)
                name_lbl.setObjectName("ScannerChecklistName")
                name_lbl.setProperty("checkState", state)
                item_l.addWidget(icon_lbl)
                item_l.addWidget(name_lbl)
                item_l.addStretch()
                item_w.setToolTip(full_label)
                grid.addWidget(item_w, row_i, col_i, 1, 2)
            else:
                item_w = QWidget()
                item_w.setObjectName("TransparentWidget")
                item_l = QHBoxLayout(item_w)
                item_l.setContentsMargins(0, 0, 0, 0)
                item_l.setSpacing(3)
                icon_lbl = QLabel(icon)
                icon_lbl.setObjectName("ScannerCompactIcon")
                name_lbl = QLabel(short_name)
                name_lbl.setObjectName("ScannerChecklistName")
                name_lbl.setProperty("checkState", state)
                item_l.addWidget(icon_lbl)
                item_l.addWidget(name_lbl)
                item_l.addStretch()
                item_w.setToolTip(full_label)
                grid.addWidget(item_w, row_i, col_i)
        layout.addLayout(grid)

    def _build_entry_checklist(self) -> list[dict]:
        """Build seven checks from the canonical selected-side decision."""
        if not self.row:
            return []

        def _item(state: str, label: str) -> dict:
            return {
                "state": state,
                "pass": state == "pass",
                "label": label,
            }

        items: list[dict] = []
        decision = self._candidate_decision()
        strategy = self._candidate_strategy()
        execution = self._candidate_execution()
        side_eval = self._selected_side_evaluation()
        side = self._selected_side()
        side_text = {"buy": "MUA", "sell": "BÁN"}.get(
            side,
            "chưa xác định",
        )

        eligible = strategy.get(
            "eligible",
            self.row.get("strategy_eligible"),
        )
        strategy_reasons = strategy.get("reason_codes")
        if not isinstance(strategy_reasons, list):
            strategy_reasons = []
        strategy_detail = "; ".join(
            REASON_CODE_MESSAGES.get(
                str(code),
                _SCANNER_REASON_MESSAGES.get(str(code), str(code)),
            )
            for code in strategy_reasons[:2]
        )
        strategy_state = (
            "pass"
            if eligible is True
            else "fail"
            if eligible is False
            else "unknown"
        )
        items.append(_item(
            strategy_state,
            f"Chiến lược: hướng {side_text} "
            f"{'phù hợp' if eligible is True else 'chưa phù hợp' if eligible is False else 'chưa có kết quả'}"
            + (f" — {strategy_detail}" if strategy_detail else ""),
        ))

        setup = self._canonical_setup_score()
        min_score = self._required_min_score()
        score_state = (
            "pass"
            if setup is not None and min_score is not None and setup >= min_score
            else "fail"
            if setup is not None and min_score is not None
            else "unknown"
        )
        items.append(_item(
            score_state,
            f"Điểm thiết lập ({side_text}): "
            f"{self._score_text(setup)}/{self._score_text(min_score)}",
        ))

        entry = str(
            side_eval.get("entry_status")
            or self.row.get("entry_status")
            or ""
        ).lower()
        entry_known = bool(entry)
        entry_ok = entry in ("confirmed_entry", "ready", "ready_to_trade")
        entry_map = {
            "confirmed_entry": "đã xác nhận",
            "watch_zone": "giá chưa vào vùng giá hoặc chưa có nến xác nhận",
            "waiting_confirmation": "chờ xác nhận H1/M15",
            "no_setup": "chưa có thiết lập giao dịch (setup)",
        }
        items.append(_item(
            "pass" if entry_ok else "fail" if entry_known else "unknown",
            f"Xác nhận điểm vào lệnh: "
            f"{entry_map.get(entry, entry) if entry else 'chưa có dữ liệu'}",
        ))

        entry_zone = side_eval.get("entry_zone")
        if entry_zone is None:
            entry_zone = self.row.get("entry_zone") or self.row.get(
                "entry_zones"
            )
        price_zone = self._selected_price_vs_zone()
        zone_map = {
            "in_zone": "giá đang trong vùng",
            "near_zone": "giá đang gần vùng",
            "far": "giá còn xa vùng",
            "unknown": "chưa xác định được vị trí giá",
        }
        zone_ok = bool(entry_zone) and price_zone == "in_zone"
        zone_state = (
            "pass"
            if zone_ok
            else "fail"
            if price_zone in {"near_zone", "far"}
            else "unknown"
        )
        items.append(_item(
            zone_state,
            f"Vùng vào lệnh: "
            f"{zone_map.get(price_zone, price_zone or 'chưa có dữ liệu')}",
        ))

        m15 = str(
            side_eval.get("m15_quality")
            or self.row.get("m15_quality")
            or ""
        ).lower()
        m15_label = {
            "strict": "xác nhận chặt",
            "loose": "xác nhận lỏng",
            "none": "chưa xác nhận",
            "": "chưa có dữ liệu",
        }
        items.append(_item(
            "pass" if m15 == "strict" else "fail" if m15 else "unknown",
            f"M15: {m15_label.get(m15, m15)}",
        ))

        effective_rr = self._effective_rr()
        min_rr = self._required_min_rr()
        rr_state = (
            "pass"
            if (
                effective_rr is not None
                and min_rr is not None
                and effective_rr >= min_rr
            )
            else "fail"
            if effective_rr is not None and min_rr is not None
            else "unknown"
        )
        items.append(_item(
            rr_state,
            f"R:R sau spread/chi phí: "
            f"{self._score_text(effective_rr) if decision else self._rr_main_text()}/"
            f"{self._score_text(min_rr)}",
        ))

        trade_allowed = self._scan_trade_allowed()
        execution_reasons = execution.get("reason_codes")
        if not isinstance(execution_reasons, list):
            execution_reasons = decision.get("reason_codes")
        if not isinstance(execution_reasons, list):
            execution_reasons = []
        permission_detail = "; ".join(
            REASON_CODE_MESSAGES.get(
                str(code),
                _SCANNER_REASON_MESSAGES.get(str(code), str(code)),
            )
            for code in execution_reasons[:2]
        )
        permission_state = (
            "pass"
            if trade_allowed is True
            else "fail"
            if trade_allowed is False
            else "unknown"
        )
        items.append(_item(
            permission_state,
            "Quyền tại thời điểm quét: "
            + (
                "được phép"
                if trade_allowed is True
                else "không được phép"
                if trade_allowed is False
                else "chưa có kết quả"
            )
            + (f" — {permission_detail}" if permission_detail else ""),
        ))

        return items

    def _refresh_conditions(self) -> None:
        """Refresh wait conditions and insights at the bottom."""
        if not self.row:
            return
        self._fill_pills(self.wait_layout, self._wait_conditions(), "wait")
        self._fill_pills(self.insight_layout, self._insights(), "risk")

    @staticmethod
    def _score_rating(sc: int) -> str:
        if sc >= 80:
            return "Mạnh"
        if sc >= 65:
            return "Khá"
        if sc >= 50:
            return "TB"
        return "Yếu"

    def _fill_pills(self, layout: QVBoxLayout, items: list[tuple[str, str]], fallback_state: str) -> None:
        self._clear_layout(layout)
        if not items:
            items = [("Không có cảnh báo lớn từ scanner.", "ok")]
        for text, state in items:
            layout.addWidget(self._pill(text, state or fallback_state))

    def _decision_reason(self) -> str:
        if self._has_no_entry_zone():
            return "Chưa có vùng entry, chưa nên vào lệnh."
        action = str(self.row.get("display_action") or self.row.get("scanner_action") or "")
        if action == "ready":
            return "Có thể xem xét, vẫn cần kiểm tra lệnh trước khi vào."
        if action in {"wait", "watch"}:
            return "Setup cần thêm xác nhận trước khi giao dịch."
        return "Rủi ro hoặc dữ liệu chưa đạt yêu cầu."

    def _wait_conditions(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        if self._has_no_entry_zone():
            items.append(("Có vùng entry rõ ràng trên biểu đồ.", "wait"))
        if self._m15_text() == "Chưa xác nhận":
            items.append(("M15 xác nhận đúng hướng trước khi vào lệnh.", "wait"))
        gap, min_gap = self._gap_numbers()
        if gap is not None and min_gap is not None and gap < min_gap:
            items.append((f"Gap mua-bán đạt tối thiểu {self._compact_number(min_gap)}.", "wait"))
        if not self._rr_field("risk_reward"):
            items.append(("Có R:R hợp lệ trước khi lập kế hoạch lệnh.", "wait"))
        return items

    def _insights(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        bias = self.row.get("direction_bias")
        if isinstance(bias, dict):
            side = str(bias.get("best_side") or "").lower()
            buy = bias.get("buy_score", "--")
            sell = bias.get("sell_score", "--")
            if side in {"buy", "sell"}:
                items.append((f"Ủng hộ: {self._bias_text(bias)}.", "ok"))
            try:
                best = float(buy if side == "buy" else sell)
            except (TypeError, ValueError):
                best = 0.0
            if best < 50:
                items.append((f"Rủi ro: điểm {side.upper() if side else 'setup'} chỉ {self._compact_number(best)}.", "risk"))
        reason = str(self.row.get("short_reason") or "").strip()
        if reason:
            items.append((f"Lý do chính: {reason}", "risk"))
        return items

    def _action_text(self, value: str) -> str:
        return {"ready": "Sẵn sàng", "watch": "Theo dõi", "wait": "Chờ đợi", "skip": "Bỏ qua"}.get(value, value)

    def _bias_text(self, value: object) -> str:
        side_map = {"buy": "Mua", "sell": "Bán", "neutral": "Trung lập", "stand_aside": "Đứng ngoài"}
        if isinstance(value, dict):
            side = str(value.get("best_side", "--"))
            buy = value.get("buy_score", "--")
            sell = value.get("sell_score", "--")
            gap = value.get("score_gap", "--")
            score = value.get("buy_score") if side == "buy" else value.get("sell_score")
            try:
                score_num = float(score)
            except (TypeError, ValueError):
                score_num = 0.0
            if score_num >= 65:
                clarity = "rõ" if value.get("is_clear_bias") else "trung bình"
            elif score_num >= 50:
                clarity = "trung bình"
            else:
                clarity = "yếu"
            return f"{side_map.get(side, side)} {clarity} · {self._compact_number(buy)}/{self._compact_number(sell)} · Gap {self._compact_number(gap)}"
        text = str(value)
        return side_map.get(text, text)

    def _compact_number(self, value: object) -> str:
        try:
            number = float(str(value))
        except (TypeError, ValueError):
            return str(value)
        return str(int(number)) if number.is_integer() else f"{number:.1f}"

    @staticmethod
    def _rr_detail_text(
        rr_range: object,
        effective_range: object,
        expected_effective_rr: object,
        expected_effective_rr_base: object,
    ) -> str:
        return ScannerDetailScreen._rr_detail_text_ascii(
            rr_range,
            effective_range,
            expected_effective_rr,
            expected_effective_rr_base,
        )

    @staticmethod
    def _rr_detail_text_ascii(
        rr_range: object,
        effective_range: object,
        expected_effective_rr: object,
        expected_effective_rr_base: object,
    ) -> str:
        parts: list[str] = []
        nominal_range = ScannerDetailScreen._rr_range_ascii(rr_range)
        if nominal_range:
            parts.append(f"dai {nominal_range}")
        effective_range_text = ScannerDetailScreen._rr_range_ascii(effective_range)
        if effective_range_text:
            parts.append(f"dai thuc {effective_range_text}")
        try:
            base = float(expected_effective_rr_base) if expected_effective_rr_base is not None else None
        except (TypeError, ValueError):
            base = None
        try:
            best = float(expected_effective_rr) if expected_effective_rr is not None else None
        except (TypeError, ValueError):
            best = None
        if base is not None:
            parts.append(f"base sau spread ~{base:.1f}")
        elif best is not None:
            parts.append(f"thuc ~{best:.1f}")
        return " | ".join(parts)

    @staticmethod
    def _rr_range_ascii(value: object) -> str:
        if not isinstance(value, dict):
            return ""
        try:
            best = float(value["best"]) if value.get("best") is not None else None
            worst = float(value["worst"]) if value.get("worst") is not None else None
        except (TypeError, ValueError):
            return ""
        if best is None or worst is None:
            return ""
        if best == worst:
            return f"{best:.1f}"
        return f"{worst:.1f}-{best:.1f}"

    @staticmethod
    def _rr_range_compact(rr_range: object) -> str:
        """Format risk_reward_range as compact string: '2.9–5.6' or '—'."""
        if not isinstance(rr_range, dict):
            return "—"
        best = rr_range.get("best")
        worst = rr_range.get("worst")
        if best is None or worst is None:
            return "—"
        if best == worst:
            return f"{best:.1f}"
        return f"{worst:.1f}–{best:.1f}"

    def _permission_text(self, value: str) -> str:
        return {"allowed": "Được phép", "caution": "Cẩn trọng", "blocked": "Bị chặn"}.get(value, value)

    def _entry_status_text(self, value: str) -> str:
        return {
            "confirmed_entry": "Đã xác nhận",
            "waiting_confirmation": "Chờ xác nhận",
            "waiting_for_confirmation": "Chờ xác nhận",
            "watch_zone": "Vùng theo dõi",
            "invalidated": "Đã vô hiệu",
            "no_setup": "Không có thiết lập",
            "data_unavailable": "Thiếu dữ liệu",
        }.get(value, value)

    def _entry_status_display(self) -> str:
        side_eval = self._selected_side_evaluation()
        raw = str(
            side_eval.get("entry_status")
            or self.row.get("entry_status")
            or "--"
        ).strip().lower() if self.row else "--"
        if self._has_no_entry_zone() and raw in {
            "waiting_confirmation",
            "waiting_for_confirmation",
            "watch_zone",
            "unknown",
            "--",
        }:
            return "Chưa có vùng"
        return self._entry_status_text(raw)

    def _has_no_entry_zone(self) -> bool:
        side_eval = self._selected_side_evaluation()
        scenario = self._selected_scenario()
        zones = (
            side_eval.get("entry_zone")
            or scenario.get("entry_zone")
            or self.row.get("entry_zone")
            or self.row.get("entry_zones")
            if self.row
            else None
        )
        if scenario.get("entry_zone_source") == "fallback":
            return True
        return not (
            isinstance(zones, (list, tuple))
            and len(zones) == 2
            and self._number(zones[0]) is not None
            and self._number(zones[1]) is not None
        )

    def _m15_text(self) -> str:
        raw = str(
            self._selected_side_evaluation().get("m15_quality")
            or self.row.get("m15_quality")
            or ""
        ).strip()
        if not raw or raw in {"--", "-", "none", "unknown"}:
            return "Chưa xác nhận"
        return raw

    def _gap_numbers(self) -> tuple[float | None, float | None]:
        bias = self.row.get("direction_bias") if self.row else None
        gap = self.row.get("score_gap")
        min_gap: object = 10
        if isinstance(bias, dict):
            gap = bias.get("score_gap", gap)
            min_gap = bias.get("min_gap", min_gap)
        try:
            gap_num = float(str(gap))
        except (TypeError, ValueError):
            gap_num = None
        try:
            min_gap_num = float(str(min_gap))
        except (TypeError, ValueError):
            min_gap_num = None
        return gap_num, min_gap_num

    def _refresh_diagnostics(self) -> None:
        if not hasattr(self, "diag_text"):
            return
        if not self.row:
            set_rich_html(
                self.diag_text,
                empty_state_html(
                    "Chọn một dòng trong bảng quét để xem chẩn đoán."
                ),
            )
            return
        analysis = self.row.get("analysis_result")
        if not isinstance(analysis, dict):
            set_rich_html(
                self.diag_text,
                empty_state_html(
                    "Không có dữ liệu phân tích để hiển thị chẩn đoán."
                ),
            )
            return

        light = self._is_light_theme()

        body_text_color = "#334155" if light else "#e2e8f0"
        parts: list[str] = []
        parts.append(f"<div style='{_HTML_BODY}color:{body_text_color};line-height:1.5;'>")
        parts.append(self._diag_branch_html(light=light))
        parts.append(self._diag_score_breakdown_html(analysis, light=light))
        parts.append(self._diag_gate_html(analysis, light=light))
        parts.append(self._diag_checklist_html(analysis, light=light))
        parts.append(self._diag_pipeline_steps_html(analysis, light=light))
        parts.append(self._diag_final_score_html(analysis, light=light))
        parts.append("</div>")
        set_rich_html(
            self.diag_text,
            "\n".join(parts),
            theme="light" if light else "dark",
        )

    # -- AI Setup Audit ----------------------------------------------------

    def _refresh_ai_audit(self) -> None:
        if not hasattr(self, "audit_text"):
            return
        if not self.row:
            set_rich_html(
                self.audit_text,
                empty_state_html(
                    "Chọn một dòng trong bảng quét để xem AI kiểm định."
                ),
            )
            if getattr(self, "audit_btn", None):
                self.audit_btn.setEnabled(False)
            return
        if getattr(self, "audit_btn", None):
            self.audit_btn.setEnabled(True)
        audit = self.row.get("ai_setup_audit")
        if not isinstance(audit, dict) or not audit:
            set_rich_html(
                self.audit_text,
                empty_state_html(
                    "Chưa có kết quả kiểm định AI. Bấm nút Chạy kiểm định AI "
                    "để AI phân tích setup này."
                ),
            )
            return

        light = self._is_light_theme()

        set_rich_html(
            self.audit_text,
            self._ai_audit_html(audit, light=light),
            theme="light" if light else "dark",
        )

    def _run_ai_audit(self) -> None:
        """Run AI audit on-demand for the current row."""
        if not self.row:
            return
        if not self.app or not hasattr(self.app, "scanner_controller"):
            self.audit_status.setText("Lỗi: không tìm thấy scanner controller.")
            return

        self.audit_btn.setEnabled(False)
        self.audit_status.setText("Đang gọi AI...")
        set_rich_html(
            self.audit_text,
            empty_state_html(
                "⏳ Đang chờ AI phản hồi...",
                tone="warning",
            ),
        )

        # Run in a simple thread to not block UI
        from PyQt6.QtCore import QThread, pyqtSignal

        class AuditWorker(QThread):
            finished_audit = pyqtSignal(dict)

            def __init__(self, controller, row):
                super().__init__()
                self.controller = controller
                self.row = row

            def run(self):
                result = self.controller.audit_single_row(self.row)
                self.finished_audit.emit(result)

        self._audit_worker = AuditWorker(self.app.scanner_controller, self.row)
        self._audit_worker.finished_audit.connect(self._on_audit_done)
        self._audit_worker.start()

    def _on_audit_done(self, audit: dict) -> None:
        """Handle AI audit result."""
        self.audit_btn.setEnabled(True)
        if audit.get("auditor_error"):
            raw = str(audit.get("raw_response", "") or "")[:800]
            raw_display = f"<pre style='color:#94a3b8;{_HTML_NUMBER}max-height:200px;overflow:auto;'>{raw}</pre>" if raw else ""
            self.audit_status.setText(f"Lỗi: {audit['auditor_error']}")
            set_rich_html(
                self.audit_text,
                f"<p style='color:#e11d48;'>Lỗi kiểm định: {audit['auditor_error']}</p>"
                f"<p style='color:#94a3b8;'>AI không trả về JSON hợp lệ.</p>"
                f"{raw_display}",
            )
        else:
            self.audit_status.setText("Hoàn tất kiểm định.")
            self.row["ai_setup_audit"] = audit
            light = self._is_light_theme()
            set_rich_html(
                self.audit_text,
                self._ai_audit_html(audit, light=light),
                theme="light" if light else "dark",
            )

    def _ai_audit_html(self, audit: dict, light: bool = False) -> str:
        agreement = str(audit.get("agreement") or "caution").strip().lower()
        label_map = {
            "agree": ("ĐỒNG THUẬN", "#22c55e"),
            "caution": ("CẢNH BÁO", "#fbbf24"),
            "disagree": ("KHÔNG ĐỒNG THUẬN", "#ef4444"),
        }
        label, color = label_map.get(agreement, label_map["caution"])
        confidence = self._compact_number(audit.get("confidence_score", 0))
        quality = self._compact_number(audit.get("trade_plan_quality", 0))
        setup_summary = escape(str(audit.get("setup_summary") or "").strip() or "AI chưa có tóm tắt setup.")
        market_summary = escape(str(audit.get("market_context_summary") or "").strip() or "AI chưa có tóm tắt bối cảnh.")
        no_trade = escape(str(audit.get("do_not_trade_reason") or "").strip())
        error = escape(str(audit.get("auditor_error") or "").strip())

        text_color = "#334155" if light else "#94a3b8"
        value_color = "#0f172a" if light else "#e2e8f0"
        bg_color = "#f1f5f9" if light else "#1e293b"
        border_color = "#cbd5e1" if light else "#2b3545"
        desc_color = "#736B60" if light else "#64748b"
        title_color = "#0369A1" if light else "#38bdf8"
        error_bg = "#fef2f2" if light else "#2b2330"
        error_border = "#fca5a5" if light else "#854d0e"
        error_text = "#991b1b" if light else "#fbbf24"

        rows = [
            f"<div style='{_HTML_BODY}'>",
            f"<h2 style='color:{title_color};margin:0 0 4px;{_HTML_SUBTITLE}'>AI Setup Auditor</h2>",
            f"<p style='color:{desc_color};{_HTML_SMALL}margin:0 0 12px;'>"
            "AI chỉ kiểm định setup rule engine đã tạo. Phần này không tự thay đổi quyết định, gate hoặc auto trade."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:14px;background:{bg_color};border-radius:6px;{_HTML_BODY}'>",
            "<tr>",
            f"<td style='padding:4px 12px;color:{text_color};width:120px;{_HTML_BODY}'>Kết luận</td>",
            f"<td style='padding:4px 12px;color:{color};{_HTML_BODY}font-weight:bold;'>{label}</td>",
            f"<td style='padding:4px 12px;color:{text_color};width:90px;{_HTML_BODY}'>Tin cậy</td>",
            f"<td style='padding:4px 12px;color:{value_color};{_HTML_NUMBER}'>{confidence}/100</td>",
            f"<td style='padding:4px 12px;color:{text_color};width:110px;{_HTML_BODY}'>Chất lượng plan</td>",
            f"<td style='padding:4px 12px;color:{value_color};{_HTML_NUMBER}'>{quality}/100</td>",
            "</tr>",
            "</table>",
        ]
        if error:
            rows.append(
                f"<div style='color:{error_text};background:{error_bg};border:1px solid {error_border};"
                f"border-radius:6px;padding:10px 12px;margin-bottom:12px;{_HTML_BODY}'>AI auditor lỗi: {error}</div>"
            )
        rows.extend([
            self._audit_block("Tóm tắt setup", setup_summary, "#38bdf8" if not light else "#0284c7", light=light),
            self._audit_block("Bối cảnh thị trường", market_summary, "#a78bfa" if not light else "#7c3aed", light=light),
            self._audit_list_block("Cảnh báo rủi ro", audit.get("risk_flags"), "#f97316" if not light else "#ea580c", light=light),
            self._audit_list_block("Điều kiện còn thiếu", audit.get("missing_confirmations"), "#fbbf24" if not light else "#d97706", light=light),
        ])
        if no_trade:
            rows.append(self._audit_block("Lý do không nên giao dịch", no_trade, "#ef4444", light=light))
        rows.append("</div>")
        return "\n".join(rows)

    def _audit_block(self, title: str, body: str, color: str, light: bool = False) -> str:
        text_color = "#111827" if light else "#e2e8f0"
        bg_color = "#ffffff" if light else "#111827"
        border_color = "#D6D2C8" if light else "#334155"
        return (
            f"<h3 style='color:{color};margin:16px 0 6px;{_HTML_SUBTITLE}'>{escape(title)}</h3>"
            f"<div style='color:{text_color};background:{bg_color};border:1px solid {border_color};"
            f"border-radius:6px;padding:10px 12px;margin-bottom:8px;{_HTML_BODY}'>{body}</div>"
        )

    def _audit_list_block(self, title: str, values: object, color: str, light: bool = False) -> str:
        items = values if isinstance(values, list) else []
        muted_color = "#736B60" if light else "#94a3b8"
        text_color = "#111827" if light else "#e2e8f0"
        bg_color = "#ffffff" if light else "#111827"
        border_color = "#D6D2C8" if light else "#334155"

        if not items:
            body = f"<span style='color:{muted_color};{_HTML_BODY}'>Không có mục đáng chú ý.</span>"
        else:
            body = f"<ul style='margin:0;padding-left:18px;{_HTML_BODY}'>" + "".join(
                f"<li style='margin:4px 0;color:{text_color};{_HTML_BODY}'>{escape(str(item))}</li>"
                for item in items
                if str(item).strip()
            ) + "</ul>"
        return (
            f"<h3 style='color:{color};margin:16px 0 6px;{_HTML_SUBTITLE}'>{escape(title)}</h3>"
            f"<div style='background:{bg_color};border:1px solid {border_color};border-radius:6px;"
            f"padding:10px 12px;margin-bottom:8px;{_HTML_BODY}'>{body}</div>"
        )

    # -- Branch indicator ---------------------------------------------------

    def _diag_branch_html(self, light: bool = False) -> str:
        """Show the canonical strategy branch and Phase-0 safety status."""
        branch = str(
            self.row.get("auto_trade_branch", "DEFAULT_RULES")
        ).strip().upper()
        sc = "#736B60" if light else "#94a3b8"

        if branch == BRANCH_BACKTEST_INVALID:
            reasons = self._candidate_reason_messages()
            reason_text = "; ".join(escape(reason) for reason in reasons) or (
                "BACKTEST_CONFIG_INVALID"
            )
            accent = "#b91c1c" if light else "#f87171"
            bg = "#fef2f2" if light else "#2b1111"
            return (
                f"<table style='width:100%;border-collapse:collapse;background:{bg};"
                f"border-left:4px solid {accent};margin:8px 0 12px;'>"
                f"<tr><td style='padding:12px 16px;'>"
                f"<div style='{_HTML_SUBTITLE}color:{accent};"
                f"margin-bottom:6px;'>⛔ BACKTEST_CONFIG_INVALID</div>"
                f"<div style='{_HTML_BODY}color:{sc};line-height:1.5;'>"
                f"Scanner chỉ tính kết quả quy tắc mặc định để tham khảo hiển thị; "
                f"nhánh chiến lược này luôn <b>không đủ điều kiện</b> và không "
                f"được tạo lệnh.<br>"
                f"<b>Lý do:</b> {reason_text}</div>"
                f"</td></tr></table>"
            )

        if branch == BRANCH_BACKTEST_VALIDATED:
            cfg = self.row.get("auto_trade_config")
            if not isinstance(cfg, dict):
                cfg = {}
            regime_raw = str(cfg.get("regime", "")).strip()
            side_raw = str(cfg.get("side", "")).strip()
            min_score = int(cfg.get("min_score", 0) or 0)
            min_rr = float(cfg.get("min_rr", 0) or 0)

            # Human-readable regime
            regime_map = {
                "range": "Đi ngang (Range)",
                "trend_up": "Xu hướng tăng (Trend Up)",
                "trend_down": "Xu hướng giảm (Trend Down)",
                "volatile": "Biến động mạnh (Volatile)",
            }
            regime_text = regime_map.get(regime_raw, regime_raw if regime_raw else "Không giới hạn")

            # Human-readable side
            side_map = {"buy": "Chỉ MUA", "sell": "Chỉ BÁN"}
            side_text = side_map.get(side_raw, "Theo pipeline (Buy hoặc Sell)")

            min_score_val = min_score if min_score > 0 else 65
            score_desc = "(cấu hình)" if min_score > 0 else "(mặc định)"
            rr_text = f"1:{min_rr:.1f}" if min_rr > 0 else "Không giới hạn"

            # "Lư trung hỏa" (Fire in the Hearth) color palette
            accent = "#dc2626" if light else "#f97316"  # Fiery red (light) / Ember orange (dark)
            bg = "#fff7ed" if light else "#2a1510"      # Warm peach (light) / Hearth coal (dark)
            
            sub_bg = "#ffffff" if light else "#1c0d07"
            sub_border = "#ffedd5" if light else "#7c2d12"
            
            ref_bg = "#fffaf0" if light else "#3c1f13"
            ref_color = "#9a3412" if light else "#fdba74"
            ref_border = "#fed7aa" if light else "#9a3412"
            
            text_color = "#111827" if light else "#fca5a5"

            config_table_html = (
                f"<table style='width:100%;border-collapse:collapse;{_HTML_BODY}"
                f"background:{sub_bg};border:1px solid {sub_border};border-radius:6px;margin-bottom:8px;'>"
                f"<tr>"
                f"<td style='padding:4px 10px;color:{sc};width:140px;{_HTML_BODY}'>Chế độ thị trường:</td>"
                f"<td style='padding:4px 10px;color:{text_color};{_HTML_BODY}font-weight:bold;'>{regime_text}</td>"
                f"</tr>"
                f"<tr>"
                f"<td style='padding:4px 10px;color:{sc};{_HTML_BODY}'>Hướng vào lệnh:</td>"
                f"<td style='padding:4px 10px;color:{text_color};{_HTML_BODY}font-weight:bold;'>{side_text}</td>"
                f"</tr>"
                f"<tr>"
                f"<td style='padding:4px 10px;color:{sc};{_HTML_BODY}'>Điểm tối thiểu:</td>"
                f"<td style='padding:4px 10px;color:{text_color};{_HTML_NUMBER}'>{min_score_val} điểm <span style='{_HTML_BODY}color:{sc};'>{score_desc}</span></td>"
                f"</tr>"
                f"<tr>"
                f"<td style='padding:4px 10px;color:{sc};{_HTML_BODY}'>R:R tối thiểu:</td>"
                f"<td style='padding:4px 10px;color:{text_color};{_HTML_NUMBER}'>{rr_text}</td>"
                f"</tr>"
                f"</table>"
            )

            return (
                f"<table style='width:100%;border-collapse:collapse;background:{bg};border-left:4px solid {accent};margin:8px 0 12px;'>"
                f"<tr>"
                f"<td style='padding:4px 16px;'>"
                f"<div style='{_HTML_TITLE}color:{accent};margin-bottom:8px;'>"
                f"✅ BACKTEST_VALIDATED — Cấu hình Backtest hợp lệ</div>"
                f"{config_table_html}"
                f"<div style='{_HTML_SMALL}color:{ref_color};background:{ref_bg};border:1px solid {ref_border};"
                f"padding:8px 12px;border-radius:6px;line-height:1.5;'>"
                f"💡 Cấu hình backtest chỉ xác định setup có phù hợp chiến lược. "
                f"Lệnh tự động vẫn bắt buộc <b>READY_TO_TRADE + Allowed + entry đã xác nhận</b>; "
                f"Watch/Wait/Stand Aside luôn bị chặn."
                f"</div>"
                f"</td>"
                f"</tr>"
                f"</table>"
            )
        else:
            accent = "#B45309" if light else "#f59e0b"
            bg = "#FFFBEB" if light else "#291700"
            return (
                f"<table style='width:100%;border-collapse:collapse;background:{bg};border-left:4px solid {accent};margin:8px 0 12px;'>"
                f"<tr>"
                f"<td style='padding:12px 16px;'>"
                f"<div style='{_HTML_SUBTITLE}color:{accent};margin-bottom:4px;'>"
                f"⚙️ DEFAULT_RULES — Không có cấu hình Backtest</div>"
                f"<div style='{_HTML_BODY}color:{sc};line-height:1.5;'>"
                f"Không có cấu hình Backtest đang hoạt động. Strategy Router dùng "
                f"ngưỡng live; kết quả vẫn phải qua entry, gate, rollout và "
                f"tái kiểm tra ngay trước khi đặt lệnh.</div>"
                f"</td>"
                f"</tr>"
                f"</table>"
            )

    # -- Score Breakdown -------------------------------------------------

    def _diag_score_breakdown_html(self, analysis: dict, light: bool = False) -> str:
        scores = analysis.get("scenario_scores", {})
        if not isinstance(scores, dict):
            return ""

        buy = scores.get("buy", {}) if isinstance(scores.get("buy"), dict) else {}
        sell = scores.get("sell", {}) if isinstance(scores.get("sell"), dict) else {}

        def _sc(comp: str, side_dict: dict) -> str:
            val = side_dict.get(comp, 0)
            try:
                return str(int(val))
            except (TypeError, ValueError):
                return str(val)

        def _rating(sc: int) -> str:
            if sc >= 80:
                return '<span style="color:#10b981;">MẠNH</span>'
            if sc >= 65:
                return '<span style="color:#ea580c;">KHÁ</span>'
            if sc >= 50:
                return '<span style="color:#f59e0b;">TRUNG BÌNH</span>'
            return '<span style="color:#e11d48;">YẾU</span>'

        def _color(val: int, max_val: int) -> str:
            pct = val / max(max_val, 1)
            if pct >= 0.7:
                return "#10b981"
            if pct >= 0.4:
                return "#f59e0b"
            return "#e11d48"

        buy_total = int(buy.get("signal_score", buy.get("total", 0)) or 0)
        sell_total = int(sell.get("signal_score", sell.get("total", 0)) or 0)
        buy_macro_status = _VN_MACRO.get(buy.get("macro_status", ""), buy.get("macro_status", ""))
        sell_macro_status = _VN_MACRO.get(sell.get("macro_status", ""), sell.get("macro_status", ""))
        buy_penalty = ", ".join(_translate_codes(buy.get("penalty_codes", []) or [])) or "không"
        sell_penalty = ", ".join(_translate_codes(sell.get("penalty_codes", []) or [])) or "không"
        buy_reason = ", ".join(_translate_codes(buy.get("reason_codes", []) or [])) or "không"
        sell_reason = ", ".join(_translate_codes(sell.get("reason_codes", []) or [])) or "không"
        buy_corr = buy.get("correlation_adjustment", 0) or 0
        sell_corr = sell.get("correlation_adjustment", 0) or 0

        title_color = "#D94625" if light else "#ea580c"
        desc_color = "#736B60" if light else "#64748b"
        border_color = "#D6D2C8" if light else "#334155"
        row_border_color = "#EAE6DF" if light else "#1e293b"
        text_color = "#111827" if light else "#e2e8f0"
        label_color = "#111827" if light else "#f8fafc"
        muted_color = "#57534E" if light else "#94a3b8"
        bg_color = "#f1f5f9" if light else "#1e293b"

        rows = [
            f"<div style='{_HTML_BODY}'>",
            f"<h2 style='color:{title_color};margin:0 0 4px;{_HTML_SUBTITLE}'>Phân rã điểm số</h2>",
            f"<p style='color:{desc_color};{_HTML_SMALL}margin:0 0 12px;'>"
            "Hệ thống chấm điểm 6 thành phần cho mỗi hướng MUA và BÁN. "
            "<b>Xu hướng</b> (EMA50/200, cấu trúc HH/HL) · "
            "<b>Động lượng</b> (RSI, MACD) · "
            "<b>Vị trí</b> (gần hỗ trợ/kháng cự) · "
            "<b>SMC</b> (BOS, CHOCH, vùng cung/cầu) · "
            "<b>Rủi ro</b> (ATR, spread, tin tức) · "
            "<b>Vĩ mô</b> (lãi suất, DXY, VIX, US10Y). "
            "Tổng 0-100; &ge;80 Mạnh, &ge;65 Khá, &ge;50 Trung bình, &lt;50 Yếu."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:16px;{_HTML_BODY}'>",
            "<tr>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};{_HTML_BODY}font-weight:bold;' title='Thành phần được chấm điểm'>Thành phần</th>",
            f"<th style='text-align:center;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:55px;{_HTML_BODY}font-weight:bold;' title='Điểm tối đa của thành phần này'>Max</th>",
            f"<th style='text-align:center;padding:4px 10px;border-bottom:2px solid #ea580c;color:#ea580c;width:55px;{_HTML_BODY}font-weight:bold;' title='Điểm kịch bản MUA'>MUA</th>",
            f"<th style='text-align:center;padding:4px 10px;border-bottom:2px solid #f43f5e;color:#f43f5e;width:55px;{_HTML_BODY}font-weight:bold;' title='Điểm kịch bản BÁN'>BÁN</th>",
            "</tr>",
        ]

        components = [
            ("Xu hướng", "trend_alignment", 25, "EMA50/200, cấu trúc đỉnh/đáy H4/D1"),
            ("Động lượng", "momentum_alignment", 20, "RSI, MACD histogram"),
            ("Vị trí", "location_quality", 25, "Khoảng cách đến hỗ trợ/kháng cự gần nhất"),
            ("SMC", "smc_quality", 15, "BOS, CHOCH, displacement, vùng cung/cầu, thanh khoản"),
            ("Rủi ro", "risk_condition", 15, "ATR, spread, tin tức tác động cao"),
            ("Vĩ mô", "macro_alignment", None, "Lãi suất, DXY, VIX, US10Y, tâm lý thị trường"),
        ]
        for label, key, max_v, tooltip in components:
            bv = buy.get(key, 0) or 0
            sv = sell.get(key, 0) or 0
            eff_max = max_v if max_v is not None else max(int(bv), int(sv), 1)
            rows.append(
                f"<tr>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};{_HTML_BODY}' title='{tooltip}'>{label}</td>"
                f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};{_HTML_NUMBER}'>{eff_max}</td>"
                f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{_color(int(bv), eff_max)};{_HTML_NUMBER}'>{int(bv)}</td>"
                f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{_color(int(sv), eff_max)};{_HTML_NUMBER}'>{int(sv)}</td>"
                f"</tr>"
            )

        rows.append(
            f"<tr style='border-top:2px solid {border_color};'>"
            f"<td style='padding:4px 10px;color:{label_color};{_HTML_BODY}font-weight:bold;' title='Tổng điểm tín hiệu sau khi chuẩn hóa (0-100)'>TỔNG</td>"
            f"<td style='text-align:center;padding:4px 10px;color:{desc_color};{_HTML_NUMBER}'>100</td>"
            f"<td style='text-align:center;padding:4px 10px;color:#ea580c;{_HTML_NUMBER}'>{buy_total}</td>"
            f"<td style='text-align:center;padding:4px 10px;color:#f43f5e;{_HTML_NUMBER}'>{sell_total}</td>"
            f"</tr>"
        )
        rows.append("</table>")

        # Rating + modifiers — use table for reliable rendering
        rows.append(
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:14px;{_HTML_BODY}background:{bg_color};border-radius:6px;'>"
            "<tr>"
            f"<td style='padding:4px 12px;color:{muted_color};width:110px;{_HTML_BODY}'>Đánh giá MUA</td>"
            f"<td style='padding:4px 12px;color:{text_color};{_HTML_BODY}'>{_rating(buy_total)}</td>"
            f"<td style='padding:4px 12px;color:{muted_color};width:110px;{_HTML_BODY}'>Tương quan MUA</td>"
            f"<td style='padding:4px 12px;color:{text_color};{_HTML_NUMBER}'>{buy_corr:+.0f}</td>"
            "</tr>"
            "<tr>"
            f"<td style='padding:4px 12px;color:{muted_color};{_HTML_BODY}'>Đánh giá BÁN</td>"
            f"<td style='padding:4px 12px;color:{text_color};{_HTML_BODY}'>{_rating(sell_total)}</td>"
            f"<td style='padding:4px 12px;color:{muted_color};width:110px;{_HTML_BODY}'>Tương quan BÁN</td>"
            f"<td style='padding:4px 12px;color:{text_color};{_HTML_NUMBER}'>{sell_corr:+.0f}</td>"
            "</tr>"
        )

        if buy_macro_status or sell_macro_status:
            rows.append(
                "<tr>"
                f"<td style='padding:4px 12px;color:{muted_color};{_HTML_BODY}'>Vĩ mô MUA</td>"
                f"<td style='padding:4px 12px;color:{text_color};{_HTML_BODY}'><b>{buy_macro_status or 'trung lập'}</b></td>"
                f"<td style='padding:4px 12px;color:{muted_color};{_HTML_BODY}'>Vĩ mô BÁN</td>"
                f"<td style='padding:4px 12px;color:{text_color};{_HTML_BODY}'><b>{sell_macro_status or 'trung lập'}</b></td>"
                "</tr>"
            )
        rows.append(
            "<tr>"
            f"<td style='padding:4px 12px;color:{muted_color};{_HTML_BODY}'>Phạt MUA</td>"
            f"<td style='padding:4px 12px;color:{desc_color};{_HTML_BODY}'>{buy_penalty}</td>"
            f"<td style='padding:4px 12px;color:{muted_color};{_HTML_BODY}'>Phạt BÁN</td>"
            f"<td style='padding:4px 12px;color:{desc_color};{_HTML_BODY}'>{sell_penalty}</td>"
            "</tr>"
        )
        rows.append(
            "<tr>"
            f"<td style='padding:4px 12px;color:{muted_color};{_HTML_BODY}'>Lý do MUA</td>"
            f"<td style='padding:4px 12px;color:{desc_color};{_HTML_BODY}'>{buy_reason}</td>"
            f"<td style='padding:4px 12px;color:{muted_color};{_HTML_BODY}'>Lý do BÁN</td>"
            f"<td style='padding:4px 12px;color:{desc_color};{_HTML_BODY}'>{sell_reason}</td>"
            "</tr>"
        )

        # SMC reason
        buy_smc = buy.get("smc_reason", "")
        sell_smc = sell.get("smc_reason", "")
        if buy_smc or sell_smc:
            rows.append(
                "<tr>"
                f"<td style='padding:6px 12px;color:{muted_color};{_HTML_BODY}'>SMC MUA</td>"
                f"<td style='padding:6px 12px;color:{desc_color};{_HTML_BODY}'>{buy_smc or '--'}</td>"
                f"<td style='padding:6px 12px;color:{muted_color};{_HTML_BODY}'>SMC BÁN</td>"
                f"<td style='padding:6px 12px;color:{desc_color};{_HTML_BODY}'>{sell_smc or '--'}</td>"
                "</tr>"
            )
        rows.append("</table>")

        consumer = analysis.get("smc_consumer")
        consumer_sides = (
            consumer.get("sides")
            if isinstance(consumer, dict)
            and isinstance(consumer.get("sides"), dict)
            else {}
        )
        if consumer_sides:
            rows.extend([
                f"<h3 style='color:{title_color};margin:14px 0 6px;{_HTML_SUBTITLE}'>Vùng SMC được chọn</h3>",
                f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;{_HTML_BODY}'>",
                "<tr>",
                f"<th style='padding:5px 8px;border-bottom:2px solid {border_color};color:{muted_color};text-align:left;'>Hướng</th>",
                f"<th style='padding:5px 8px;border-bottom:2px solid {border_color};color:{muted_color};text-align:left;'>Zone ID / phiên bản</th>",
                f"<th style='padding:5px 8px;border-bottom:2px solid {border_color};color:{muted_color};text-align:center;'>Quality</th>",
                f"<th style='padding:5px 8px;border-bottom:2px solid {border_color};color:{muted_color};text-align:center;'>Relevance</th>",
                f"<th style='padding:5px 8px;border-bottom:2px solid {border_color};color:{muted_color};text-align:center;'>Setup</th>",
                f"<th style='padding:5px 8px;border-bottom:2px solid {border_color};color:{muted_color};text-align:left;'>Lý do</th>",
                "</tr>",
            ])
            for side, label in (("buy", "MUA"), ("sell", "BÁN")):
                item = (
                    consumer_sides.get(side)
                    if isinstance(consumer_sides.get(side), dict)
                    else {}
                )
                breakdown = (
                    item.get("score_breakdown")
                    if isinstance(item.get("score_breakdown"), dict)
                    else {}
                )
                zone_id = item.get("selected_zone_id") or "--"
                version = item.get("scoring_version") or "--"
                reason_codes = breakdown.get("reason_codes", [])
                reason = (
                    ", ".join(str(code) for code in reason_codes)
                    if isinstance(reason_codes, list) and reason_codes
                    else "--"
                )
                rows.append(
                    "<tr>"
                    f"<td style='padding:5px 8px;border-bottom:1px solid {row_border_color};color:{text_color};font-weight:bold;'>{label}</td>"
                    f"<td style='padding:5px 8px;border-bottom:1px solid {row_border_color};color:{desc_color};'>{zone_id}<br><span style='{_HTML_SMALL}'>{version}</span></td>"
                    f"<td style='padding:5px 8px;border-bottom:1px solid {row_border_color};color:{text_color};text-align:center;'>{item.get('selected_zone_quality_score') if item.get('selected_zone_quality_score') is not None else '--'}</td>"
                    f"<td style='padding:5px 8px;border-bottom:1px solid {row_border_color};color:{text_color};text-align:center;'>{item.get('selected_zone_relevance_score') if item.get('selected_zone_relevance_score') is not None else '--'}</td>"
                    f"<td style='padding:5px 8px;border-bottom:1px solid {row_border_color};color:{text_color};text-align:center;'>{item.get('selected_zone_setup_score') if item.get('selected_zone_setup_score') is not None else '--'}</td>"
                    f"<td style='padding:5px 8px;border-bottom:1px solid {row_border_color};color:{desc_color};'>{reason}</td>"
                    "</tr>"
                )
            rows.append("</table>")

        rows.append("</div>")
        return "\n".join(rows)

    # -- Gate Diagnostics --------------------------------------------------

    def _diag_gate_html(self, analysis: dict, light: bool = False) -> str:
        canonical_decision = self._candidate_decision()
        side_gate = self._selected_side_evaluation().get("gate_result")
        gate = (
            side_gate if isinstance(side_gate, dict) else {}
        ) if canonical_decision else (
            analysis.get("trade_gate", {})
        )
        if not isinstance(gate, dict):
            gate = {}
        permission = analysis.get("trade_permission", {})
        if not isinstance(permission, dict):
            permission = {}

        # Pipeline diagnostics contain the legacy best-side gate. A canonical
        # decision must use the selected-side result and must not borrow a
        # pass/fail result from the other side.
        pipe_diags = analysis.get("pipeline_diagnostics")
        gate_checks: list[dict] = []
        if not canonical_decision and isinstance(pipe_diags, list):
            for d in pipe_diags:
                if isinstance(d, dict) and d.get("step") == "gate":
                    gate_checks = d.get("details", {}).get("gate_checks", []) or []
                    break

        # Build from trade_gate if no pipeline diagnostics
        if not gate_checks:
            gate_checks = self._build_gate_checks_from_result(analysis)

        GATE_VN_NAME = {
            "MT5": "MT5 (kết nối)", "Spread": "Spread (chênh lệch)",
            "DataQuality": "Chất lượng DL", "News": "Tin tức",
            "DailyWeeklyLoss": "Lỗ ngày/tuần", "AccountGuard": "Bảo vệ TK",
            "Journal": "Nhật ký", "M15": "M15 (xác nhận)",
            "ExpectedRR": "R:R kỳ vọng", "ScoreGap": "Chênh lệch điểm",
            "ZoneBroken": "Vùng bị phá",
            "ZoneRelevance": "Độ liên quan vùng",
            "ZonePriceRelation": "Giá so với vùng",
            "H4ConfirmedCHOCH": "CHOCH H4 ngược hướng",
        }
        GATE_EXPLAIN = {
            "MT5": "Kiểm tra kết nối MT5 — terminal và broker đã đăng nhập chưa",
            "Spread": "Kiểm tra chênh lệch mua/bán có bất thường không",
            "DataQuality": "Kiểm tra cảnh báo chất lượng dữ liệu từ broker",
            "News": "Kiểm tra tin tức tác động cao trong 30 phút tới",
            "DailyWeeklyLoss": "Kiểm tra giới hạn thua lỗ ngày/tuần đã đạt chưa",
            "AccountGuard": "Kiểm tra bảo vệ tài khoản (số dư, chuỗi thua)",
            "Journal": "Kiểm tra phản hồi từ nhật ký giao dịch cũ",
            "M15": "Kiểm tra khung M15 xác nhận tín hiệu vào lệnh",
            "ExpectedRR": "Kiểm tra tỷ lệ R:R kỳ vọng có đạt tối thiểu không",
            "ScoreGap": "Kiểm tra chênh lệch điểm BUY/SELL có đủ rõ ràng không",
            "ZoneBroken": "Kiểm tra vùng entry có bị phá vỡ không",
            "ZoneRelevance": "Kiểm tra vùng giá đã chọn còn phù hợp với bối cảnh hiện tại",
            "ZonePriceRelation": "Kiểm tra kịch bản đang dùng đúng vùng giá đã chọn",
            "H4ConfirmedCHOCH": "CHOCH H4 đã xác nhận ngược hướng luôn giới hạn quyết định ở WATCH_ONLY",
        }

        title_color = "#D94625" if light else "#f97316"
        desc_color = "#736B60" if light else "#64748b"
        border_color = "#D6D2C8" if light else "#334155"
        row_border_color = "#EAE6DF" if light else "#1e293b"
        text_color = "#111827" if light else "#e2e8f0"
        muted_color = "#57534E" if light else "#94a3b8"
        bg_color = "#f1f5f9" if light else "#1e293b"

        rows = [
            f"<h2 style='color:{title_color};margin:20px 0 4px;{_HTML_SUBTITLE}'>Gate kiểm tra</h2>",
            f"<p style='color:{desc_color};{_HTML_SMALL}margin:0 0 12px;'>"
            "Gate là các lớp kiểm tra trước khi cho phép vào lệnh. "
            "Mỗi gate có thể <b style='color:#22c55e;'>Cho qua</b>, "
            "<b style='color:#fbbf24;'>Cảnh báo</b> (giới hạn mức quyết định), "
            "hoặc <b style='color:#ef4444;'>Chặn</b> (cấm vào lệnh). "
            "Thứ tự ưu tiên: CHẶN > CẢNH BÁO > Pass."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;{_HTML_BODY}'>",
            "<tr>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:110px;{_HTML_BODY}font-weight:bold;'>Gate</th>",
            f"<th colspan='2' style='text-align:left;padding:4px 10px;padding-left:10px;border-bottom:2px solid {border_color};color:{muted_color};width:95px;{_HTML_BODY}font-weight:bold;'>Kết quả</th>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};{_HTML_BODY}font-weight:bold;'>Ý nghĩa / Chi tiết</th>",
            "</tr>",
        ]

        for gc in gate_checks:
            if not isinstance(gc, dict):
                continue
            g_name = gc.get("gate", "?")
            g_status = gc.get("status", "unknown")
            g_detail = gc.get("detail", "")
            g_explain = GATE_EXPLAIN.get(g_name, "")
            g_label = GATE_VN_NAME.get(g_name, g_name)

            if g_status == "block":
                icon = "🔴"
                color = "#ef4444"
                text = "CHẶN"
            elif g_status == "warning":
                icon = "🟡"
                color = "#fbbf24"
                text = "C.BÁO"
            elif g_status == "unknown":
                icon = "⚪"
                color = "#94a3b8"
                text = "CHƯA KT"
            else:
                icon = "🟢"
                color = "#22c55e"
                text = "Qua"

            rows.append(
                f"<tr>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};{_HTML_BODY}' title='{g_explain}'>{g_label}</td>"
                f"<td style='width:24px;text-align:right;padding:4px 0;border-bottom:1px solid {row_border_color};{_HTML_BODY}'>{icon}</td>"
                f"<td style='width:71px;text-align:left;padding:4px 0 4px;padding-left:6px;border-bottom:1px solid {row_border_color};color:{color};{_HTML_BODY}font-weight:bold;'>{text}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{muted_color};{_HTML_BODY}'>{g_explain} &mdash; {g_detail}</td>"
                f"</tr>"
            )
        rows.append("</table>")

        # Summary
        allowed = gate.get("allowed")
        cap = gate.get("decision_cap") or permission.get("decision_cap") or "không"
        reasons = gate.get("reasons", []) or []
        canonical_allowed = self._scan_trade_allowed()
        perm_status = permission.get("status", "?")
        perm_text = (
            "Được phép tại lúc quét"
            if canonical_allowed is True
            else "Không được phép tại lúc quét"
            if canonical_allowed is False
            else {
                "allowed": "Được phép",
                "caution": "Cẩn trọng",
                "blocked": "Bị chặn",
            }.get(perm_status, perm_status)
        )

        if allowed is False:
            summary_color = "#ef4444"
            summary_text = f"BỊ CHẶN (mức: {cap})"
        elif allowed is True and cap in ("WATCH_ONLY", "WAITING_CONFIRMATION"):
            summary_color = "#fbbf24"
            summary_text = f"CẢNH BÁO (mức: {cap})"
        elif allowed is True:
            summary_color = "#22c55e"
            summary_text = f"CHO PHÉP (mức: {cap})"
        else:
            summary_color = "#94a3b8"
            summary_text = "CHƯA CÓ KẾT QUẢ GATE"

        rows.append(
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:8px;{_HTML_BODY}"
            f"background:{bg_color};border-radius:6px;'>"
            f"<tr>"
            f"<td style='padding:8px 12px;color:{muted_color};width:130px;{_HTML_BODY}'>KẾT LUẬN GATE</td>"
            f"<td style='padding:8px 12px;color:{summary_color};{_HTML_BODY}font-weight:bold;'>{summary_text}</td>"
            f"<td style='padding:8px 12px;color:{muted_color};width:60px;{_HTML_BODY}'>Quyền</td>"
            f"<td style='padding:8px 12px;color:{text_color};{_HTML_BODY}'>{perm_text}</td>"
            f"</tr>"
            f"</table>"
        )
        if reasons:
            rows.append(
                f"<div style='{_HTML_BODY}color:#ef4444;padding:4px 12px;margin-bottom:8px;'>"
                f"Lý do: {'; '.join(reasons)}"
                f"</div>"
            )

        rows.append("</div>")
        return "\n".join(rows)

    def _build_gate_checks_from_result(self, analysis: dict) -> list[dict]:
        """Build gate checks for the canonical selected side."""
        canonical_decision = self._candidate_decision()
        side_gate = self._selected_side_evaluation().get("gate_result")
        gate = (
            side_gate if isinstance(side_gate, dict) else {}
        ) if canonical_decision else (
            analysis.get("trade_gate", {})
        )
        if not isinstance(gate, dict):
            gate = {}
        dq = analysis.get("data_quality", {})
        if not isinstance(dq, dict):
            dq = {}
        direction = analysis.get("direction_bias", {})
        if not isinstance(direction, dict):
            direction = {}
        primary = self._selected_scenario(analysis)

        block_codes = set(gate.get("block_codes", []) or [])
        warning_codes = set(gate.get("warning_codes", []) or [])

        gate_evaluated = "allowed" in gate

        def _st(code: str, *, explicit_evidence: bool = False) -> str:
            if code in block_codes:
                return "block"
            if code in warning_codes:
                return "warning"
            if gate_evaluated or explicit_evidence:
                return "pass"
            return "unknown"

        from core.reason_codes import (
            MT5_NOT_READY, SPREAD_ABNORMAL, DATA_QUALITY_WARNING,
            HIGH_IMPACT_NEWS_NEARBY, DAILY_LOSS_LIMIT_REACHED, WEEKLY_LOSS_LIMIT_REACHED,
            MAX_CONSECUTIVE_LOSSES_REACHED, MAX_OPEN_RISK_REACHED,
            M15_NOT_CONFIRMED, M15_LOOSE_CONFIRMATION, EXPECTED_RR_TOO_LOW,
            BUY_SELL_SCORE_GAP_LOW, ZONE_BROKEN, ZONE_RELEVANCE_LOW,
            ZONE_PRICE_RELATION_INVALID, CHOCH_AGAINST_DIRECTION,
        )

        def _combined_status(codes: tuple[str, ...]) -> str:
            statuses = [_st(code) for code in codes]
            if "block" in statuses:
                return "block"
            if "warning" in statuses:
                return "warning"
            if "pass" in statuses:
                return "pass"
            return "unknown"

        account_codes = (
            MAX_CONSECUTIVE_LOSSES_REACHED,
            MAX_OPEN_RISK_REACHED,
        )
        if any(code in block_codes for code in account_codes):
            account_status = "block"
        elif any(code in warning_codes for code in account_codes):
            account_status = "warning"
        else:
            account_status = (
                "pass"
                if isinstance(gate.get("account_guard_stats"), dict)
                else "unknown"
            )

        mt5_status = _st(
            MT5_NOT_READY,
            explicit_evidence=(
                dq.get("terminal_connected") is True
                and dq.get("broker_logged_in") is True
            ),
        )
        spread_status = _st(
            SPREAD_ABNORMAL,
            explicit_evidence=bool(dq.get("spread_status")),
        )
        data_status = _st(
            DATA_QUALITY_WARNING,
            explicit_evidence=bool(dq),
        )
        news_status = _st(HIGH_IMPACT_NEWS_NEARBY)
        loss_status = _combined_status((
            DAILY_LOSS_LIMIT_REACHED,
            WEEKLY_LOSS_LIMIT_REACHED,
        ))
        m15_status = _combined_status((
            M15_NOT_CONFIRMED,
            M15_LOOSE_CONFIRMATION,
        ))
        rr_status = _st(EXPECTED_RR_TOO_LOW)
        gap_status = _st(BUY_SELL_SCORE_GAP_LOW)
        zone_broken_status = _st(ZONE_BROKEN)
        zone_relevance_status = _st(ZONE_RELEVANCE_LOW)
        zone_relation_status = _st(ZONE_PRICE_RELATION_INVALID)
        choch_status = _st(CHOCH_AGAINST_DIRECTION)

        def _detail(
            status: str,
            *,
            passed: str,
            failed: str,
            unknown: str = "chưa có dữ liệu kiểm tra",
        ) -> str:
            if status == "pass":
                return passed
            if status in {"warning", "block"}:
                return failed
            return unknown

        return [
            {"gate": "MT5", "status": mt5_status,
             "detail": _detail(
                 mt5_status,
                 passed="MT5 sẵn sàng",
                 failed="MT5 chưa sẵn sàng",
             )},
            {"gate": "Spread", "status": spread_status,
             "detail": f"spread={dq.get('spread_status', 'chưa có dữ liệu')}"},
            {"gate": "DataQuality", "status": data_status,
             "detail": _detail(
                 data_status,
                 passed="không có cảnh báo",
                 failed=str(dq.get("warning") or "có cảnh báo dữ liệu"),
             )},
            {"gate": "News", "status": news_status,
             "detail": _detail(
                 news_status,
                 passed="không có tin tác động cao ở gần",
                 failed="có tin tác động cao trong 30 phút",
             )},
            {"gate": "DailyWeeklyLoss", "status": loss_status,
             "detail": _detail(
                 loss_status,
                 passed="đang trong giới hạn",
                 failed="đã chạm hoặc vượt giới hạn lỗ",
             )},
            {"gate": "AccountGuard", "status": account_status,
             "detail": _detail(
                 account_status,
                 passed="đã kiểm tra, không có cảnh báo",
                 failed="bảo vệ tài khoản đang cảnh báo hoặc chặn",
             )},
            {"gate": "Journal", "status": (
                "block"
                if self._as_dict(gate.get("journal_feedback")).get("block_codes")
                else "warning"
                if self._as_dict(gate.get("journal_feedback")).get("warning_codes")
                else "pass"
                if isinstance(gate.get("journal_feedback"), dict)
                else "unknown"
             ),
             "detail": "đã kiểm tra phản hồi nhật ký" if isinstance(gate.get("journal_feedback"), dict) else "chưa có dữ liệu kiểm tra"},
            {"gate": "M15", "status": m15_status,
             "detail": f"M15={primary.get('m15_quality', '?')}"},
            {"gate": "ExpectedRR", "status": rr_status,
             "detail": f"R:R={primary.get('expected_effective_rr', '?')} sau spread (danh nghĩa {primary.get('risk_reward', '?')}, dải {ScannerDetailScreen._rr_range_compact(primary.get('risk_reward_range'))})"},
            {"gate": "ScoreGap", "status": gap_status,
             "detail": f"chênh lệch={direction.get('score_gap', '?')} (tối thiểu {direction.get('min_gap', 10)})"},
            {"gate": "ZoneBroken", "status": zone_broken_status,
             "detail": _detail(
                 zone_broken_status,
                 passed="vùng chưa bị phá",
                 failed="vùng đã bị phá",
             )},
            {"gate": "ZoneRelevance", "status": zone_relevance_status,
             "detail": _detail(
                 zone_relevance_status,
                 passed="vùng còn đủ liên quan",
                 failed="độ liên quan của vùng dưới ngưỡng",
             )},
            {"gate": "ZonePriceRelation", "status": zone_relation_status,
             "detail": _detail(
                 zone_relation_status,
                 passed="vùng đã chọn khớp với kịch bản",
                 failed="vùng đã chọn không còn khớp với kịch bản",
             )},
            {"gate": "H4ConfirmedCHOCH", "status": choch_status,
             "detail": _detail(
                 choch_status,
                 passed="không có CHOCH H4 đã xác nhận ngược hướng",
                 failed="có CHOCH H4 đã xác nhận ngược hướng",
             )},
        ]

    # -- Entry Checklist ----------------------------------------------------

    def _diag_checklist_html(self, analysis: dict, light: bool = False) -> str:
        checklist = analysis.get("entry_checklist")
        if not isinstance(checklist, list) or not checklist:
            return ""

        title_color = "#0369A1" if light else "#a78bfa"
        desc_color = "#736B60" if light else "#64748b"
        border_color = "#D6D2C8" if light else "#334155"
        row_border_color = "#EAE6DF" if light else "#1e293b"
        text_color = "#111827" if light else "#e2e8f0"
        muted_color = "#57534E" if light else "#94a3b8"

        rows = [
            f"<h2 style='color:{title_color};margin:20px 0 4px;{_HTML_SUBTITLE}'>Điều kiện vào lệnh</h2>",
            f"<p style='color:{desc_color};{_HTML_SMALL}margin:0 0 12px;'>"
            "Các điều kiện cần đạt trước khi vào lệnh thật. "
            "<b style='color:#22c55e;'>✅ Đạt</b> = đã thỏa mãn. "
            "<b style='color:#fbbf24;'>⏳ Chờ</b> = cần theo dõi thêm, chưa nên vào lệnh vội."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;{_HTML_BODY}'>",
            "<tr>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:110px;{_HTML_BODY}font-weight:bold;'>Điều kiện</th>",
            f"<th colspan='2' style='text-align:left;padding:4px 10px;padding-left:10px;border-bottom:2px solid {border_color};color:{muted_color};width:95px;{_HTML_BODY}font-weight:bold;'>Trạng thái</th>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:160px;{_HTML_BODY}font-weight:bold;'>Giá trị</th>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};{_HTML_BODY}font-weight:bold;'>Ghi chú</th>",
            "</tr>",
        ]

        for item in checklist:
            if not isinstance(item, dict):
                continue
            label = item.get("label", "?")
            item_status = str(item.get("status") or "").lower()
            passed = item_status == "pass"
            failed = item_status in {"fail", "failed", "block", "blocked"}
            value = item.get("value", "--")
            note = item.get("note", "")

            icon = "✅" if passed else "❌" if failed else "⏳"
            status_text = "Đạt" if passed else "Không đạt" if failed else "Chờ"
            color = "#22c55e" if passed else "#ef4444" if failed else "#fbbf24"

            rows.append(
                f"<tr>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};{_HTML_BODY}'>{label}</td>"
                f"<td style='width:24px;text-align:right;padding:4px 0;border-bottom:1px solid {row_border_color};{_HTML_BODY}'>{icon}</td>"
                f"<td style='width:71px;text-align:left;padding:4px 0 4px;padding-left:6px;border-bottom:1px solid {row_border_color};color:{color};{_HTML_BODY}font-weight:bold;'>{status_text}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{muted_color};{_HTML_BODY}'>{value}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};{_HTML_BODY}'>{note}</td>"
                f"</tr>"
            )
        rows.append("</table>")
        return "\n".join(rows)

    # -- Pipeline Steps ----------------------------------------------------

    def _diag_pipeline_steps_html(self, analysis: dict, light: bool = False) -> str:
        pipe_diags = analysis.get("pipeline_diagnostics")
        if not isinstance(pipe_diags, list) or not pipe_diags:
            return ""

        STEP_EXPLAIN = {
            "validate": "Kiểm tra dữ liệu đầu vào (đủ số nến D1/H4/H1 chưa), xác định chế độ thị trường, rủi ro",
            "correlation": "Tính điều chỉnh tương quan từ DXY (USD index), VIX (sợ hãi), US10Y (lợi suất trái phiếu)",
            "score": "Chấm điểm 6 thành phần (xu hướng, động lượng, vị trí, SMC, rủi ro, vĩ mô) cho cả 2 hướng",
            "scenarios": "Xây dựng kế hoạch giao dịch: vùng entry, SL, TP, cỡ lot, đánh giá chất lượng M15",
            "direction": "So sánh điểm BUY vs SELL để chọn hướng giao dịch tốt nhất",
            "gate": "Chạy 11 gate kiểm tra: MT5, spread, tin tức, bảo vệ TK, M15, R:R, chênh lệch điểm...",
            "final_score": "Tổng hợp điểm cuối cùng (tín hiệu×65% + bằng chứng NK×20% + thực thi×15%) và ra quyết định",
            "structural_reject": "Dừng sớm có chủ đích: SMC đã được kiểm tra đủ để xác nhận không có thiết lập. Đây không phải lỗi dữ liệu.",
        }

        title_color = "#D94625" if light else "#fb923c"
        desc_color = "#736B60" if light else "#64748b"
        border_color = "#D6D2C8" if light else "#334155"
        row_border_color = "#EAE6DF" if light else "#1e293b"
        text_color = "#111827" if light else "#e2e8f0"
        muted_color = "#57534E" if light else "#94a3b8"

        rows = [
            f"<h2 style='color:{title_color};margin:20px 0 4px;{_HTML_SUBTITLE}'>Pipeline từng bước</h2>",
            f"<p style='color:{desc_color};{_HTML_SMALL}margin:0 0 12px;'>"
            "Quy trình phân tích tuần tự 7 bước. Nếu một bước <b style='color:#ef4444;'>thất bại</b>, "
            "các bước sau không chạy. Bước <b style='color:#fbbf24;'>cảnh báo</b> vẫn tiếp tục "
            "nhưng có thể ảnh hưởng kết quả cuối cùng."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;{_HTML_BODY}'>",
            "<tr>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:120px;{_HTML_BODY}font-weight:bold;'>Bước</th>",
            f"<th colspan='2' style='text-align:left;padding:4px 10px;padding-left:10px;border-bottom:2px solid {border_color};color:{muted_color};width:95px;{_HTML_BODY}font-weight:bold;'>Kết quả</th>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};{_HTML_BODY}font-weight:bold;'>Diễn giải / Tóm tắt</th>",
            "</tr>",
        ]

        step_labels = {
            "validate": "1. Kiểm tra DL",
            "correlation": "2. Tương quan",
            "score": "3. Chấm điểm",
            "scenarios": "4. Kế hoạch",
            "direction": "5. Chọn hướng",
            "gate": "6. Gate",
            "final_score": "7. Điểm cuối",
            "structural_reject": "Fast reject SMC",
        }

        route = str(analysis.get("pipeline_route", "") or "").strip()
        reason = str(analysis.get("fast_reject_reason", "") or "").strip()
        if route and reason:
            rows.insert(
                2,
                f"<p style='color:{desc_color};{_HTML_SMALL}margin:0 0 12px;'>"
                f"Đường xử lý: <b>{route}</b> · Lý do: <b>{reason}</b>. "
                "Kết quả là không có thiết lập, không phải thiếu dữ liệu."
                "</p>",
            )

        for entry in pipe_diags:
            if not isinstance(entry, dict):
                continue
            step = entry.get("step", "?")
            status = entry.get("status", "pass")
            summary = entry.get("summary", "")

            if status == "fail":
                icon = "🔴"
                color = "#ef4444"
                text = "LỖI"
            elif status == "warning":
                icon = "🟡"
                color = "#fbbf24"
                text = "C.BÁO"
            else:
                icon = "🟢"
                color = "#22c55e"
                text = "QUA"

            label = step_labels.get(step, step)
            explain = STEP_EXPLAIN.get(step, "")
            rows.append(
                f"<tr>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};{_HTML_BODY}' title='{explain}'>{label}</td>"
                f"<td style='width:24px;text-align:right;padding:4px 0;border-bottom:1px solid {row_border_color};{_HTML_BODY}'>{icon}</td>"
                f"<td style='width:71px;text-align:left;padding:4px 0 4px;padding-left:6px;border-bottom:1px solid {row_border_color};color:{color};{_HTML_BODY}font-weight:bold;'>{text}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{muted_color};{_HTML_BODY}'>{summary}</td>"
                f"</tr>"
            )
        rows.append("</table>")
        return "\n".join(rows)

    # -- Final Score Breakdown ----------------------------------------------

    def _diag_final_score_html(self, analysis: dict, light: bool = False) -> str:
        final_detail = analysis.get("final_score_detail", {})
        if not isinstance(final_detail, dict):
            final_detail = {}
        final_score = self._canonical_setup_score()
        decision = analysis.get("decision_engine", {})
        if not isinstance(decision, dict):
            decision = {}

        signal_s = final_detail.get("signal_score", "?")
        evidence_s = final_detail.get("evidence_score", "?")
        exec_s = final_detail.get("execution_quality_score", "?")

        title_color = "#047857" if light else "#22c55e"
        desc_color = "#736B60" if light else "#64748b"
        border_color = "#D6D2C8" if light else "#334155"
        row_border_color = "#EAE6DF" if light else "#1e293b"
        text_color = "#111827" if light else "#e2e8f0"
        muted_color = "#57534E" if light else "#94a3b8"
        label_color = "#111827" if light else "#f8fafc"
        bg_color = "#f1f5f9" if light else "#1e293b"

        rows = [
            f"<h2 style='color:{title_color};margin:20px 0 4px;{_HTML_SUBTITLE}'>Điểm thiết lập của hướng đã chọn</h2>",
            f"<p style='color:{desc_color};{_HTML_SMALL}margin:0 0 12px;'>"
            "Điểm tổng hợp từ 3 nguồn: <b>Tín hiệu</b> (điểm kỹ thuật/SMC/vĩ mô), "
            "<b>Bằng chứng nhật ký</b> (hiệu suất lịch sử của setup tương tự), "
            "<b>Chất lượng thực thi</b> (tỷ lệ vào lệnh thành công trước đây). "
            "Đây là điểm <b>setup_score</b> dùng để so với ngưỡng chiến lược. "
            "Điểm cao không tự đồng nghĩa được vào lệnh; entry, gate, rollout "
            "và tái kiểm tra trước khi đặt lệnh vẫn có quyền chặn."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;{_HTML_BODY}'>",
            "<tr>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};{_HTML_BODY}font-weight:bold;'>Thành phần</th>",
            f"<th style='text-align:center;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:60px;{_HTML_BODY}font-weight:bold;' title='Trọng lượng trong công thức'>TL</th>",
            f"<th style='text-align:center;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:60px;{_HTML_BODY}font-weight:bold;' title='Điểm thành phần'>Điểm</th>",
            "</tr>",
            f"<tr><td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};{_HTML_BODY}' title='Điểm tín hiệu từ bước chấm điểm (0-100)'>Tín hiệu</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};{_HTML_NUMBER}'>65%</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};{_HTML_NUMBER}'>{signal_s}</td></tr>",
            f"<tr><td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};{_HTML_BODY}' title='Điểm từ nhật ký giao dịch cũ (setup tương tự từng thắng không)'>Bằng chứng (NK)</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};{_HTML_NUMBER}'>20%</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};{_HTML_NUMBER}'>{evidence_s}</td></tr>",
            f"<tr><td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};{_HTML_BODY}' title='Điểm chất lượng thực thi lệnh (tỷ lệ khớp lệnh thành công)'>Chất lượng thực thi</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};{_HTML_NUMBER}'>15%</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};{_HTML_NUMBER}'>{exec_s}</td></tr>",
            f"<tr style='border-top:2px solid {border_color};'>"
            f"<td style='padding:4px 10px;color:{label_color};{_HTML_BODY}font-weight:bold;' title='setup_score = Tín hiệu×0.65 + Bằng chứng×0.20 + Thực thi×0.15'>SETUP SCORE</td>"
            f"<td style='text-align:center;padding:4px 10px;color:{desc_color};{_HTML_NUMBER}'>100%</td>"
            f"<td style='text-align:center;padding:4px 10px;color:#22c55e;{_HTML_NUMBER}'>{self._score_text(final_score)}</td></tr>",
            "</table>",
        ]

        # Canonical Scanner decision. The older pipeline Decision Engine is
        # retained as context only and must not overwrite candidate status.
        dec_decision = decision.get("decision", "?")
        DECISION_EXPLAIN = {
            "READY_TO_TRADE": "Sẵn sàng giao dịch — mọi điều kiện đều đạt",
            "WAITING_CONFIRMATION": "Chờ xác nhận thêm — cần thêm tín hiệu H1/M15",
            "WATCH_ONLY": "Chỉ theo dõi — chưa đủ điều kiện vào lệnh",
            "AGGRESSIVE_SETUP": "Setup táo bạo — rủi ro cao hơn bình thường",
            "STAND_ASIDE": "Đứng ngoài — không nên giao dịch lúc này",
            "TRADE_BLOCKED": "Bị chặn — gate đã chặn không cho vào lệnh",
        }
        dec_explain = DECISION_EXPLAIN.get(dec_decision, "")
        candidate_status = self._canonical_status()
        candidate_label = _CANDIDATE_STATUS[candidate_status][0]
        selected_side = {
            "buy": "MUA",
            "sell": "BÁN",
        }.get(self._selected_side(), "CHƯA XÁC ĐỊNH")
        rows.append(
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;{_HTML_BODY}background:{bg_color};border-radius:6px;'>"
            "<tr>"
            f"<td style='padding:4px 12px;color:{muted_color};width:110px;{_HTML_BODY}'>Scanner chuẩn</td>"
            f"<td style='padding:4px 12px;color:{text_color};{_HTML_BODY}'><b>{candidate_label}</b>"
            f" · Hướng phân tích: <b>{selected_side}</b></td>"
            "</tr><tr>"
            f"<td style='padding:4px 12px;color:{muted_color};{_HTML_BODY}'>Pipeline tham khảo</td>"
            f"<td style='padding:4px 12px;color:{text_color};{_HTML_BODY}'><b>{dec_decision}</b>"
            + (f" <span style='color:{desc_color};{_HTML_BODY}'>({dec_explain})</span>" if dec_explain else "")
            + "</td>"
            "</tr>"
            "</table>"
        )
        rows.append("</div>")
        return "\n".join(rows)

    # ------------------------------------------------------------------

    def _export_json(self) -> None:
        if not self.row:
            return
        export_dir = app_data_dir() / "scanner_details"
        export_dir.mkdir(parents=True, exist_ok=True)
        symbol = str(self.row.get("symbol", "scanner")).replace("/", "")
        rank = str(self.row.get("rank", "0"))
        path = export_dir / f"scanner_detail_{rank}_{symbol}.json"
        payload = {key: value for key, value in self.row.items() if key != "analysis_result"}
        JsonStorage(path).save(payload)

    def _save_to_journal(self) -> None:
        if not self.row:
            return
        self.journal_controller.save_scanner_row(self.row)
        if self.navigate:
            self.navigate("journal")
