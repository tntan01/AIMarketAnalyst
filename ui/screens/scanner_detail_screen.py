from __future__ import annotations

from html import escape

from config.paths import app_data_dir
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QProgressBar,
    QScrollArea, QSizePolicy, QSplitter, QTabWidget, QTextEdit, QVBoxLayout,
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
from ui.screens.shared import action_button, card, page_header


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

        ov = QSplitter(Qt.Orientation.Horizontal)
        ov.setChildrenCollapsible(False)

        # --- Left container: button + trade panel + score panel + checklist ---
        left_container = QWidget()
        left_container.setMinimumWidth(260)
        left_col = QVBoxLayout(left_container)
        left_col.setSpacing(4)
        left_col.setContentsMargins(0, 0, 0, 0)

        # -- Button + Trade Panel + Score Panel + Checklist Panel --
        self.show_detail_btn = action_button("📋 Xem đầy đủ", primary=True, color="warning")
        self.show_detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show_detail_btn.setToolTip("Xem toàn bộ 16 chỉ số phân tích chi tiết")
        self.show_detail_btn.setFixedHeight(28)
        self.show_detail_btn.setStyleSheet(
            "QPushButton {"
            "  padding: 4px 12px;"
            "  border-radius: 8px;"
            "  font-size: 12px;"
            "  font-weight: 600;"
            "  background: #D97706;"
            "  border: 1px solid #D97706;"
            "  color: #ffffff;"
            "}"
            "QPushButton:hover, QPushButton:pressed {"
            "  background: #F59E0B;"
            "  border-color: #B45309;"
            "  color: #ffffff;"
            "}"
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

        ov.addWidget(left_container)

        # --- Right container: hero bar + chart ---
        right_container = QWidget()
        right_container.setMinimumWidth(360)
        right_col = QVBoxLayout(right_container)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(4)

        # -- Hero verdict bar --
        self.hero_bar = QLabel("")
        self.hero_bar.setObjectName("ScannerDetailHero")
        self.hero_bar.setFixedHeight(28)
        self.hero_bar.setWordWrap(False)
        self.hero_bar.setTextFormat(Qt.TextFormat.RichText)
        self.hero_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hero_bar.setStyleSheet(
            "QLabel#ScannerDetailHero { border-radius: 8px; padding: 4px 12px; font-size: 12px; background: #1e293b; border: 1px solid #334155; }"
        )
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

        ov.addWidget(right_container)
        ov.setStretchFactor(0, 1)
        ov.setStretchFactor(1, 4)
        ov.setSizes([280, 900])

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(ov)
        overview_tab.layout().addWidget(scroll)

        self.tabs.addTab(overview_tab, "📊 Tổng quan")

        # ---- Tab 2: Chẩn đoán (score + gate + checklist) ----------------
        diag_tab = card()
        self.diag_text = QTextEdit()
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
        self.audit_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        btn_row.addWidget(self.audit_btn)
        btn_row.addWidget(self.audit_status)
        btn_row.addStretch()
        audit_layout.addLayout(btn_row)
        # Result area
        self.audit_text = QTextEdit()
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

    def _show_scan_detail_dialog(self) -> None:
        """Open a dialog showing all InfoCards and the entry checklist."""
        if not self.row:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Chưa có dữ liệu", "Chưa chọn mã nào từ bảng quét.")
            return

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        symbol = str(self.row.get("symbol", "--"))
        dlg = QDialog(self)
        dlg.setWindowTitle(f"📋 Chi tiết kết quả quét — {symbol}")
        dlg.setMinimumSize(880, 580)
        dlg.resize(980, 680)
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
        title = QLabel(f"<b style='font-size:18px;color:{title_color};'>📋 CHI TIẾT KẾT QUẢ QUÉT — {symbol}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        # Overview Pills
        # 1. Signal Bias Pill
        bias_val = self.row.get("direction_bias", {})
        side = "buy"
        bias_text = "TRUNG LẬP"
        pill_side_obj = "SummaryPillNeutral"
        side_color = "#f59e0b"
        if isinstance(bias_val, dict):
            side = str(bias_val.get("best_side", ""))
            is_clear = bias_val.get("is_clear_bias", False)
            if side == "buy":
                bias_text = f"MUA {'RÕ' if is_clear else 'TB'}"
                pill_side_obj = "SummaryPillBuy"
                side_color = "#10b981"
            elif side == "sell":
                bias_text = f"BÁN {'RÕ' if is_clear else 'TB'}"
                pill_side_obj = "SummaryPillSell"
                side_color = "#f43f5e"

        bias_pill = QFrame()
        bias_pill.setObjectName(pill_side_obj)
        bias_pill_layout = QHBoxLayout(bias_pill)
        bias_pill_layout.setContentsMargins(8, 4, 8, 4)
        bias_lbl = QLabel(bias_text)
        bias_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {side_color}; background: transparent; border: none;")
        bias_pill_layout.addWidget(bias_lbl)
        header_layout.addWidget(bias_pill)

        # 2. Final Score Pill
        final_v = self.row.get("final_score", "--")
        score_pill = QFrame()
        score_pill.setObjectName("SummaryPillScore")
        score_pill_layout = QHBoxLayout(score_pill)
        score_pill_layout.setContentsMargins(8, 4, 8, 4)
        score_lbl = QLabel(f"Điểm: {final_v}/100")
        score_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {'#0f172a' if light else '#f8fafc'}; background: transparent; border: none;")
        score_pill_layout.addWidget(score_lbl)
        header_layout.addWidget(score_pill)

        # 3. R:R Pill
        rr = self._rr_main_text()
        rr_pill = QFrame()
        rr_pill.setObjectName("SummaryPillRR")
        rr_pill_layout = QHBoxLayout(rr_pill)
        rr_pill_layout.setContentsMargins(8, 4, 8, 4)
        rr_lbl = QLabel(f"R:R: {rr}")
        rr_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #f59e0b; background: transparent; border: none;")
        rr_pill_layout.addWidget(rr_lbl)
        header_layout.addWidget(rr_pill)

        # 4. Permission Pill
        perm = str(self.row.get("trade_permission") or "--").lower()
        perm_map = {"allowed": "Được phép", "caution": "Cẩn trọng", "blocked": "Bị chặn", "--": "--"}
        perm_accent = {"allowed": "#10b981", "caution": "#f59e0b", "blocked": "#f43f5e"}.get(perm, "#94a3b8")
        perm_pill = QFrame()
        perm_pill.setObjectName("SummaryPillPerm")
        perm_pill_layout = QHBoxLayout(perm_pill)
        perm_pill_layout.setContentsMargins(8, 4, 8, 4)
        perm_lbl = QLabel(f"Quyền: {perm_map.get(perm, perm)}")
        perm_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {perm_accent}; background: transparent; border: none;")
        perm_pill_layout.addWidget(perm_lbl)
        header_layout.addWidget(perm_pill)

        root.addLayout(header_layout)

        # -----------------------------------------------------------------------
        # Scroll Area
        # -----------------------------------------------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        
        label_color = "#475569" if light else "#94a3b8"
        value_color = "#0f172a" if light else "#f1f5f9"

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
            lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {label_color}; background: transparent; border: none;")
            lbl.setToolTip(tooltip_txt)

            val = QLabel(val_txt)
            val.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {val_color}; background: transparent; border: none;")
            val.setWordWrap(True)

            card_w_layout.addWidget(lbl)
            card_w_layout.addWidget(val)
            return card_widget

        # -----------------------------------------------------------------------
        # CỘT TRÁI - PHẦN 1: BỐI CẢNH KỸ THUẬT
        # -----------------------------------------------------------------------
        tech_title = QLabel("🔍 BỐI CẢNH KỸ THUẬT")
        tech_title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {value_color}; background: transparent; border: none; margin-top: 4px;")
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
        macro_title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {value_color}; background: transparent; border: none; margin-top: 4px;")
        left_col.addWidget(macro_title)

        macro_card = QFrame()
        macro_card.setObjectName("MacroContextCard")
        macro_card_layout = QVBoxLayout(macro_card)
        macro_card_layout.setContentsMargins(14, 12, 14, 12)
        macro_card_layout.setSpacing(10)

        # Macro Score Header
        macro_val_raw = self.row.get("macro_score", "--")
        try:
            macro_num = int(macro_val_raw)
        except (TypeError, ValueError):
            macro_num = 15
        macro_accent = "#10b981" if macro_num >= 22 else ("#f59e0b" if macro_num >= 15 else "#94a3b8")
        macro_conf = float(self.row.get("macro_confidence", 1.0))
        macro_dot = "●" if macro_conf >= 0.8 else ("○" if macro_conf >= 0.5 else "◌")
        macro_bias_raw = str(self.row.get("macro_bias", "") or "").lower()
        macro_bias_text = {
            "aligned": "Thuận",
            "conflict": "Xung đột",
            "divergent": "Xung đột",
            "neutral": "Trung lập",
            "unclear": "Chưa rõ"
        }.get(macro_bias_raw, macro_bias_raw.title())

        macro_hdr = QHBoxLayout()
        macro_hdr_lbl = QLabel("Điểm số Vĩ mô")
        macro_hdr_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {label_color};")
        macro_hdr_val = QLabel(f"{macro_dot} {macro_num}/30 ({macro_bias_text})")
        macro_hdr_val.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {macro_accent};")
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
            tier_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {value_color};")
            tier_score = QLabel(f"{t_val}/{t_max}")
            tier_score.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {value_color};")
            tier_info.addWidget(tier_lbl)
            tier_info.addStretch(1)
            tier_info.addWidget(tier_score)
            tier_row.addLayout(tier_info)

            # Styled QProgressBar
            bar = QProgressBar()
            bar.setRange(0, t_max)
            bar.setValue(t_val)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            p_color = "#10b981" if t_val >= t_max * 0.7 else ("#f59e0b" if t_val >= t_max * 0.4 else "#94a3b8")
            bg_color = "#1e293b" if not light else "#e2e8f0"
            bar.setStyleSheet(f"""
                QProgressBar {{ background-color: {bg_color}; border: none; border-radius: 3px; }}
                QProgressBar::chunk {{ background-color: {p_color}; border-radius: 3px; }}
            """)
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
            ind_lbl.setStyleSheet(f"font-size: 11px; color: {label_color}; border-top: 1px solid {'#242b3d' if not light else '#e2e8f0'}; padding-top: 6px; margin-top: 4px;")
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
                buy_lbl.setStyleSheet("font-size: 11px; color: #cbd5e1;" if not light else "font-size: 11px; color: #475569;")
                buy_lbl.setWordWrap(True)
                buy_lbl.setTextFormat(Qt.TextFormat.RichText)
                reasons_layout.addWidget(buy_lbl)
                has_reasons = True
            if sell_r:
                sell_lbl = QLabel(f"🔴 <b style='color:#f43f5e;'>BÁN:</b> {sell_r}")
                sell_lbl.setStyleSheet("font-size: 11px; color: #cbd5e1;" if not light else "font-size: 11px; color: #475569;")
                sell_lbl.setWordWrap(True)
                sell_lbl.setTextFormat(Qt.TextFormat.RichText)
                reasons_layout.addWidget(sell_lbl)
                has_reasons = True

        if has_reasons:
            reasons_container = QWidget()
            reasons_container.setStyleSheet("background: transparent;")
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
        journal_title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {value_color}; background: transparent; border: none; margin-top: 4px;")
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
            warn_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {"rgba(245, 158, 11, 0.08)" if not light else "rgba(245, 158, 11, 0.05)"};
                    border: 1px solid rgba(245, 158, 11, 0.2);
                    border-radius: 6px;
                }}
            """)
            warn_l = QHBoxLayout(warn_frame)
            warn_l.setContentsMargins(10, 6, 10, 6)
            warn_l.setSpacing(6)
            
            warn_icon = QLabel("⚠️")
            warn_icon.setStyleSheet("font-size: 12px; background: transparent; border: none;")
            warn_txt = QLabel("Mẫu quá ít, kỳ vọng chưa đáng tin cậy")
            warn_txt.setStyleSheet("font-size: 11px; font-weight: 600; color: #f59e0b; background: transparent; border: none;")
            warn_l.addWidget(warn_icon)
            warn_l.addWidget(warn_txt)
            warn_l.addStretch(1)
            right_col.addWidget(warn_frame)

        # -----------------------------------------------------------------------
        # CỘT PHẢI - PHẦN 4: ĐIỀU KIỆN VÀO LỆNH (CHECKLIST)
        # -----------------------------------------------------------------------
        checklist_title = QLabel("🔍 ĐIỀU KIỆN VÀO LỆNH (CHECKLIST)")
        checklist_title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {value_color}; background: transparent; border: none; margin-top: 4px;")
        right_col.addWidget(checklist_title)

        checklist_card = QFrame()
        checklist_card.setObjectName("ChecklistCard")
        cl_layout = QVBoxLayout(checklist_card)
        cl_layout.setContentsMargins(12, 12, 12, 12)
        cl_layout.setSpacing(6)

        green_color = "#10b981"
        red_color = "#f43f5e"

        for item in self._build_entry_checklist():
            row_card = QFrame()
            row_card.setObjectName("ChecklistRowCardPass" if item["pass"] else "ChecklistRowCardFail")
            
            row_l = QHBoxLayout(row_card)
            row_l.setContentsMargins(10, 6, 10, 6)
            row_l.setSpacing(8)
            row_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            icon_lbl = QLabel("✅" if item["pass"] else "❌")
            icon_lbl.setStyleSheet("font-size: 11px; background: transparent; border: none;")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            row_l.addWidget(icon_lbl)

            text_lbl = QLabel(item["label"])
            text_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {green_color if item['pass'] else red_color}; background: transparent; border: none;")
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
        macro_val = self.row.get("macro_score", "--")
        try:
            macro_num = int(macro_val)
        except (TypeError, ValueError):
            macro_num = 15
        conf = float(self.row.get("macro_confidence", 1.0))
        dot = "●" if conf >= 0.8 else ("○" if conf >= 0.5 else "◌")
        accent = "#10b981" if macro_num >= 22 else ("#f59e0b" if macro_num >= 15 else "#94a3b8")
        macro_raw = str(self.row.get("macro_bias", "") or "").lower()
        bias = {
            "aligned": "Thuận",
            "conflict": "Xung đột",
            "divergent": "Xung đột",
            "neutral": "Trung lập",
            "unclear": "Chưa rõ"
        }.get(macro_raw, macro_raw.title())

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
                f"<span style='font-size:10px;color:#6b7280;'>{label}</span> "
                f"<span style='font-size:10px;'>{bar} {score_val}/{max_val}</span>"
                f"<br><span style='font-size:9px;color:#9ca3af;margin-left:8px;'>{reason}</span>"
            )

        # --- Sub-components ---
        d1 = md["t1_detail"]
        if isinstance(d1, dict) and d1:
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
                        f"<span style='font-size:9px;color:#9ca3af;margin-left:8px;'>"
                        f"  {sub_label} {self._tier_bar(sv, sub_max, True)} {sv}/{sub_max}</span>"
                    )
            ys = d1.get("yield_spread_2s10s")
            if ys is not None:
                steep = "dốc lên" if d1.get("yield_spread_steepening") else "phẳng"
                parts.append(
                    f"<span style='font-size:9px;color:#9ca3af;margin-left:8px;'>"
                    f"Đường cong LS: {ys:+.2f} ({steep})</span>"
                )

        d3 = md["t3_detail"]
        if isinstance(d3, dict) and d3:
            comps = d3.get("components", {})
            if isinstance(comps, dict):
                rs = comps.get("risk_sentiment", {})
                geo = comps.get("geopolitical", {})
                for sub_label, sub_dict, sub_max in [
                    ("Tâm lý TT", rs, 8), ("Địa chính trị", geo, 4),
                ]:
                    sv = int(sub_dict.get(side, 0) or 0)
                    parts.append(
                        f"<span style='font-size:9px;color:#9ca3af;margin-left:8px;'>"
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
                    f"<span style='font-size:9px;color:#9ca3af;margin-left:8px;'>"
                    f"VIX {vix:.1f} · {vix_note}</span>"
                )

        # --- BUY / SELL reasons ---
        reasons = md["reasons"]
        if isinstance(reasons, dict):
            buy_r = reasons.get("buy", "")
            sell_r = reasons.get("sell", "")
            if buy_r:
                parts.append(
                    f"<br><span style='font-size:9px;font-weight:bold;color:#ea580c;'>MUA:</span> "
                    f"<span style='font-size:9px;color:#9ca3af;'>{buy_r}</span>"
                )
            if sell_r:
                parts.append(
                    f"<span style='font-size:9px;font-weight:bold;color:#f43f5e;'>BÁN:</span> "
                    f"<span style='font-size:9px;color:#9ca3af;'>{sell_r}</span>"
                )

        detail = f"{bias}<br><br>{'<br>'.join(parts)}" if parts else bias
        return f"{dot} {macro_num}/30", detail, accent

    def _dialog_card_rr(self) -> tuple[str, str, str]:
        rr_ctx = self._rr_context()
        rr = rr_ctx.get("risk_reward") or self._rr_main_text()
        eff_rr = rr_ctx.get("expected_effective_rr")
        rr_range = rr_ctx.get("risk_reward_range")
        new_detail = self._rr_detail_text(
            rr_range,
            rr_ctx.get("risk_reward_effective_range"),
            eff_rr,
            rr_ctx.get("expected_effective_rr_base"),
        )
        if new_detail:
            return str(rr), new_detail, "#ea580c"
        if rr_range and isinstance(rr_range, dict):
            worst = rr_range.get("worst")
            if worst is not None:
                detail = f"dải {worst:.1f}–{rr_range.get('best', '?'):.1f}"
                if eff_rr is not None:
                    detail += f" | thực ~{eff_rr:.1f}"
                return str(rr), detail, "#ea580c"
        detail = f"~{eff_rr:.1f}" if eff_rr is not None else ""
        if not detail and self._has_entry_without_rr():
            detail = "Chưa có TP1 hợp lệ nên chưa tính R:R."
        return str(rr), detail, "#ea580c"

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
        sl = self._plan_field("stop_loss")
        if isinstance(sl, (int, float)):
            return f"{sl:.5f}", "", "#e11d48"
        return "--", "", "#94a3b8"

    def _dialog_card_tp(self) -> tuple[str, str, str]:
        if self._has_no_entry_zone():
            return "--", "", "#94a3b8"
        tp = self._plan_field("take_profit")
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
        price_zone = str(self.row.get("price_vs_zone") or "").lower()
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
        group_raw = str(self.row.get("scanner_group") or "--")
        group_map = {"ready_now": "Sẵn sàng ngay", "waiting_confirmation": "Chờ xác nhận",
                     "watch_zone": "Theo dõi", "blocked": "Bị chặn"}
        accent = {"ready_now": "#10b981", "waiting_confirmation": "#f59e0b",
                  "watch_zone": "#f59e0b", "blocked": "#e11d48"}.get(group_raw, "#94a3b8")

        detail = ""
        if group_raw == "blocked":
            analysis = self.row.get("analysis_result", {}) if isinstance(self.row.get("analysis_result"), dict) else {}
            gate = analysis.get("trade_gate", {}) if isinstance(analysis, dict) else {}
            reasons = gate.get("reasons", []) if isinstance(gate, dict) else []
            if reasons:
                detail = " | ".join(str(r) for r in reasons)
        return group_map.get(group_raw, group_raw), detail, accent

    def _dialog_card_regime(self) -> tuple[str, str, str]:
        regime = str(self.row.get("market_regime") or "--").lower()
        regime_map = {"trend_up": "Tăng", "trend_down": "Giảm", "range": "Đi ngang",
                      "volatile": "Biến động", "unknown": "Chưa rõ", "--": "--"}
        return regime_map.get(regime, regime.title()), "", "#fb7185"

    def _dialog_card_permission(self) -> tuple[str, str, str]:
        perm = str(self.row.get("trade_permission") or "--").lower()
        perm_map = {"allowed": "Được phép", "caution": "Cẩn trọng", "blocked": "Bị chặn", "--": "--"}
        accent = {"allowed": "#10b981", "caution": "#f59e0b", "blocked": "#e11d48"}.get(perm, "#94a3b8")
        return perm_map.get(perm, perm.title()), "", accent

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
                "Chi tiết từ quét thị trường",
                "",
                symbol,
            )
        )
        
        # Apply transparent theme-appropriate styling to text views
        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False
            
        if light:
            self.diag_text.setStyleSheet(
                "QTextEdit { background: transparent; color: #111827; font-size: 13px; border: none; padding: 2px; }"
            )
            self.audit_text.setStyleSheet(
                "QTextEdit { background: transparent; color: #111827; font-size: 13px; border: none; padding: 2px; }"
            )
        else:
            self.diag_text.setStyleSheet(
                "QTextEdit { background: transparent; color: #e5e7eb; font-size: 13px; border: none; padding: 2px; }"
            )
            self.audit_text.setStyleSheet(
                "QTextEdit { background: transparent; color: #e5e7eb; font-size: 13px; border: none; padding: 2px; }"
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
            payload = build_full_chart_payload(symbol, analysis_result)
            
            # Inject current theme to payload
            try:
                light = self.settings_service.load().display.theme == "light"
            except Exception:
                light = False
            payload["theme"] = "light" if light else "dark"
            
            self.chart.set_payload(payload)
        except Exception:
            self.chart.show_error("Không thể tạo dữ liệu biểu đồ từ kết quả quét.")

    def _refresh_hero(self) -> None:
        """Render the colored verdict bar at the top of the overview."""
        if not self.row:
            self.hero_bar.setText("")
            self.hero_bar.hide()
            return

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        # Xác định xu hướng giao dịch (buy/sell/neutral)
        bias_val = self.row.get("direction_bias", {})
        side = "neutral"
        if isinstance(bias_val, dict):
            side = str(bias_val.get("best_side", "neutral")).lower()
        
        # Xác định điểm số cao nhất để định lượng cường độ (mạnh hay không)
        best_score_raw = self.row.get("best_score", 0)
        try:
            best_score = int(best_score_raw)
        except (TypeError, ValueError):
            best_score = 0

        status_text = "TRUNG TÍNH"
        status_color = "#f59e0b"
        status_border = "#78350f"
        status_bg = "#451a03"

        if light:
            status_bg = "#fef3c7"
            status_border = "#f59e0b"
            status_color = "#b45309"

        if side == "buy":
            if best_score >= 80:
                status_text = "MUA MẠNH"
                status_color = "#10b981"  # xanh lá đậm
                status_border = "#059669"
                status_bg = "#064e3b"
                if light:
                    status_bg = "#d1fae5"
                    status_border = "#10b981"
                    status_color = "#047857"
            elif best_score >= 65:
                status_text = "MUA"
                status_color = "#34d399"  # xanh lá vừa
                status_border = "#059669"
                status_bg = "#064e3b"
                if light:
                    status_bg = "#e6fcf5"
                    status_border = "#34d399"
                    status_color = "#059669"
            else:
                status_text = "TRUNG TÍNH"
        elif side == "sell":
            if best_score >= 80:
                status_text = "BÁN MẠNH"
                status_color = "#f43f5e"  # đỏ đậm
                status_border = "#e11d48"
                status_bg = "#4c0519"
                if light:
                    status_bg = "#ffe4e6"
                    status_border = "#f43f5e"
                    status_color = "#be123c"
            elif best_score >= 65:
                status_text = "BÁN"
                status_color = "#fb7185"  # đỏ vừa
                status_border = "#e11d48"
                status_bg = "#4c0519"
                if light:
                    status_bg = "#fff0f2"
                    status_border = "#fb7185"
                    status_color = "#e11d48"
            else:
                status_text = "TRUNG TÍNH"

        self.hero_bar.setStyleSheet(
            f"QLabel#ScannerDetailHero {{"
            f"  background-color: {status_bg};"
            f"  border: 1px solid {status_border};"
            f"  border-radius: 8px;"
            f"  padding: 4px 12px;"
            f"  font-size: 13px;"
            f"  font-weight: bold;"
            f"  color: {status_color};"
            f"}}"
        )

        self.hero_bar.setText(status_text)
        self.hero_bar.show()

    # ------------------------------------------------------------------
    # Macro section (trade panel)
    # ------------------------------------------------------------------

    @staticmethod
    def _tier_bar(value: int, max_val: int, light: bool) -> str:
        """Segmented progress bar using Unicode block characters."""
        ratio = max(0.0, min(1.0, value / max(max_val, 1)))
        total_segs = 10
        filled = max(0, min(total_segs, round(ratio * total_segs)))
        empty = total_segs - filled
        if value >= max_val * 0.7:
            color = "#10b981"
        elif value >= max_val * 0.4:
            color = "#f59e0b"
        else:
            color = "#94a3b8"
        fill = f"<span style='color:{color};'>{'█' * filled}</span>"
        emp = f"<span style='color:{'#e5e7eb' if light else '#334155'};'>{'░' * empty}</span>"
        return fill + emp

    def _get_macro_detail(self) -> dict:
        """Safely extract tier detail from analysis_result with defaults."""
        default = {"buy": 5, "sell": 5, "detail": {}}
        ar = (self.row or {}).get("analysis_result", {}) or {}
        td = ar.get("macro", {}).get("macro_tier_detail", {})
        dc = ar.get("macro", {}).get("driver_context", {})

        t1 = td.get("tier1_interest_rate", default) if isinstance(td, dict) else default
        t2 = td.get("tier2_calendar", default) if isinstance(td, dict) else default
        t3 = td.get("tier3_sentiment", default) if isinstance(td, dict) else default
        reasons = dc.get("macro_alignment_reasons", {}) if isinstance(dc, dict) else {}
        side = (self.row or {}).get("best_side", "buy")

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
        t1_reason = f"{base} {br} ({bs_vn}) so với {quote} {qr} ({qs_vn})"

        # Tier 2 short reason
        bc = d2.get("base_event_count", 0) if isinstance(d2, dict) else 0
        qc = d2.get("quote_event_count", 0) if isinstance(d2, dict) else 0
        t2_reason = f"{base}: {bc} sự kiện · {quote}: {qc} sự kiện"

        # Tier 3 short reason
        sent = d3.get("risk_sentiment", "neutral") if isinstance(d3, dict) else "neutral"
        sent_map = {"risk_on": "Chấp nhận rủi ro", "risk_off": "Né tránh rủi ro", "neutral": "Trung tính"}
        vix = d3.get("vix_level") if isinstance(d3, dict) else None
        hs = d3.get("hotspot_count", 0) if isinstance(d3, dict) else 0
        vix_str = f"VIX {vix:.1f} · " if vix is not None else ""
        t3_reason = f"{sent_map.get(sent, sent)} · {vix_str}{hs} điểm nóng"

        return {
            "best_side": side,
            "t1": int(t1.get(side, 5)) if isinstance(t1, dict) else 5,
            "t2": int(t2.get(side, 5)) if isinstance(t2, dict) else 5,
            "t3": int(t3.get(side, 5)) if isinstance(t3, dict) else 5,
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

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        bg = "#ffffff" if light else "#1a1f2e"
        border_color = "#d1d5db" if light else "#2b3545"
        label_color = "#475569" if light else "#94a3b8"
        val_color = "#0f172a" if light else "#f1f5f9"

        self.trade_panel.setStyleSheet(
            f"QFrame#TradePanelCard {{ background: {bg}; border: 1px solid {border_color}; border-radius: 6px; }}"
        )

        title = QLabel("🎯 Số liệu giao dịch")
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {val_color}; margin-bottom: 4px;")
        layout.addWidget(title)

        if not self.row:
            layout.addWidget(QLabel("—"))
            return

        entry_val, _, _ = self._dialog_card_entry()
        sl_val, _, _ = self._dialog_card_sl()
        tp_val, tp_detail, _ = self._dialog_card_tp()
        rr_val, rr_detail, _ = self._dialog_card_rr()
        macro_val, _, _ = self._dialog_card_macro()
        regime_val, _, _ = self._dialog_card_regime()

        entry_ok = self.row.get("entry_status") == "confirmed_entry" if self.row else False
        entry_accent = "#22c55e" if entry_ok else "#f59e0b"

        rr_ctx = self._rr_context()
        rr_range = rr_ctx.get("risk_reward_range")
        rr_range_str = ""
        if rr_range and isinstance(rr_range, dict):
            worst = rr_range.get("worst")
            if worst is not None:
                rr_range_str = f" ({worst:.1f}–{rr_range.get('best', '?'):.1f})"

        eff_rr = rr_ctx.get("expected_effective_rr")
        eff_rr_str = f"~{eff_rr:.1f}" if eff_rr is not None else "—"

        eff_rr_base = rr_ctx.get("expected_effective_rr_base")
        rr_eff_suffix = ""
        if eff_rr_base is not None:
            try:
                eff_rr_str = f"base ~{float(eff_rr_base):.1f}"
                rr_eff_suffix = f" | {eff_rr_str}"
            except (TypeError, ValueError):
                pass
        elif eff_rr is not None:
            rr_eff_suffix = f" | {eff_rr_str}"

        rr_val = f"{rr_val}{rr_range_str}{rr_eff_suffix}"
        rr_range_str = ""

        scenario = self._best_detail_scenario()
        zone_context = dict(scenario) if scenario else {}
        zone_context.setdefault("symbol", self.row.get("symbol"))
        execution_zone_text = format_execution_zone_text(zone_context)
        source_zone_text = format_source_zone_text(zone_context)
        zone_width_text = format_execution_zone_width(zone_context)
        trim_reason_text = format_rr_trim_reason(zone_context) or "Không cần điều chỉnh"

        rows = [
            ("Execution zone", execution_zone_text, "#f59e0b"),
            ("Source zone", source_zone_text, label_color),
            ("Độ rộng execution", zone_width_text, label_color),
            ("Điều chỉnh R:R", trim_reason_text, label_color),
            ("Vùng vào lệnh", entry_val, entry_accent),
            ("Stop Loss", sl_val, "#e11d48"),
            ("Take Profit", f"{tp_val}{' · ' + tp_detail if tp_detail else ''}", "#10b981"),
            ("R:R", rr_val, "#f59e0b"),
            ("Chế độ TT", regime_val, val_color),
            ("Điểm vĩ mô", macro_val, "#38bdf8"),
        ]

        for label_text, value_text, accent in rows:
            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 12px; color: {label_color};")
            val = QLabel(value_text)
            val.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {accent};")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            val.setWordWrap(True)
            row_l.addWidget(lbl, 1)
            row_l.addWidget(val, 1)
            # R:R row: show effective RR as tooltip
            if label_text == "R:R":
                row_w.setToolTip(f"R:R thực tế ~{eff_rr_str}" if eff_rr_str != "—" else "")
            layout.addWidget(row_w)

    def _refresh_score_panel(self) -> None:
        """Cập nhật panel Điểm phân tích ở cột phải tab Tổng quan."""
        layout = self.score_panel.layout()
        self._clear_layout(layout)

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        bg = "#ffffff" if light else "#1a1f2e"
        border_color = "#d1d5db" if light else "#2b3545"
        label_color = "#475569" if light else "#94a3b8"
        val_color = "#0f172a" if light else "#f1f5f9"

        self.score_panel.setStyleSheet(
            f"QFrame#ScorePanelCard {{ background: {bg}; border: 1px solid {border_color}; border-radius: 6px; }}"
        )

        title = QLabel("📊 Điểm phân tích")
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {val_color}; margin-bottom: 4px;")
        layout.addWidget(title)

        if not self.row:
            layout.addWidget(QLabel("—"))
            return

        best_val, best_detail, best_accent = self._dialog_card_best()
        final_val, final_detail, final_accent = self._dialog_card_final()
        buysell_val, buysell_detail, _ = self._dialog_card_buysell()
        gap_val, gap_detail, gap_accent = self._dialog_card_gap()
        m15_val, _, m15_accent = self._dialog_card_m15()
        perm_val, _, perm_accent = self._dialog_card_permission()

        rows = [
            ("Điểm tốt nhất", f"{best_val} {best_detail}".strip(), best_accent, True),
            ("Điểm cuối", f"{final_val} {final_detail}".strip(), final_accent, True),
            ("Buy / Sell", f"{buysell_val} {buysell_detail}".strip(), val_color, False),
            ("Gap", f"{gap_val} ({gap_detail})", gap_accent, False),
            ("M15", m15_val, m15_accent, False),
            ("Quyền GD", perm_val, perm_accent, False),
        ]

        for label_text, value_text, accent, is_secondary in rows:
            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(4)
            lbl = QLabel(label_text)
            if is_secondary:
                lbl.setStyleSheet(f"font-size: 11px; color: {label_color};")
                val = QLabel(value_text)
                val.setStyleSheet(f"font-size: 11px; color: {label_color};")
            else:
                lbl.setStyleSheet(f"font-size: 12px; color: {label_color};")
                val = QLabel(value_text)
                val.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {accent};")
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

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        bg = "#ffffff" if light else "#1a1f2e"
        border_color = "#d1d5db" if light else "#2b3545"
        label_color = "#475569" if light else "#94a3b8"
        val_color = "#0f172a" if light else "#f1f5f9"

        self.checklist_panel.setStyleSheet(
            f"QFrame#ChecklistPanelCard {{ background: {bg}; border: 1px solid {border_color}; border-radius: 6px; }}"
        )

        title = QLabel("🔍 Điều kiện vào lệnh")
        title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {val_color}; margin-bottom: 4px;")
        layout.addWidget(title)

        if not self.row:
            layout.addWidget(QLabel("—"))
            return

        items = self._build_entry_checklist()
        if not items:
            layout.addWidget(QLabel("—"))
            return

        SHORT_NAMES = [
            "Quyền GD", "Gate", "Chênh lệch", "Entry",
            "Vị trí", "M15", "R:R",
        ]

        green = "#10b981"
        red = "#e11d48"

        # Fail count summary
        fail_count = sum(1 for it in items[:7] if not it["pass"])
        if fail_count >= 1:
            summary = QLabel(f"⚠️ {fail_count}/7 điều kiện chưa đạt")
            summary.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {red}; padding: 2px 0;")
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
            passed = item_data["pass"]
            full_label = item_data["label"]
            short_name = SHORT_NAMES[i] if i < len(SHORT_NAMES) else full_label[:12]
            icon = "✅" if passed else "❌"
            color = green if passed else red
            row_i, col_i = divmod(i, 2) if i < 6 else (3, 0)
            # Last item (index 6, R:R) spans full width in row 3 col 0-1
            if i == 6:
                item_w = QWidget()
                item_w.setStyleSheet("background: transparent;")
                item_l = QHBoxLayout(item_w)
                item_l.setContentsMargins(0, 0, 0, 0)
                item_l.setSpacing(3)
                icon_lbl = QLabel(icon)
                icon_lbl.setStyleSheet("font-size: 11px;")
                name_lbl = QLabel(short_name)
                name_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {color};")
                item_l.addWidget(icon_lbl)
                item_l.addWidget(name_lbl)
                item_l.addStretch()
                item_w.setToolTip(full_label)
                grid.addWidget(item_w, row_i, col_i, 1, 2)
            else:
                item_w = QWidget()
                item_w.setStyleSheet("background: transparent;")
                item_l = QHBoxLayout(item_w)
                item_l.setContentsMargins(0, 0, 0, 0)
                item_l.setSpacing(3)
                icon_lbl = QLabel(icon)
                icon_lbl.setStyleSheet("font-size: 11px;")
                name_lbl = QLabel(short_name)
                name_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {color};")
                item_l.addWidget(icon_lbl)
                item_l.addWidget(name_lbl)
                item_l.addStretch()
                item_w.setToolTip(full_label)
                grid.addWidget(item_w, row_i, col_i)
        layout.addLayout(grid)

    def _build_entry_checklist(self) -> list[dict]:
        """Build a list of {pass: bool, label: str} for entry conditions."""
        if not self.row:
            return []

        items = []
        best = int(self.row.get("best_score", 0) or 0)
        gap = int(self.row.get("score_gap", 0) or 0)
        buy_s = int(self.row.get("buy_score", 0) or 0)
        sell_s = int(self.row.get("sell_score", 0) or 0)
        stronger = "MUA" if buy_s > sell_s else "BÁN" if sell_s > buy_s else "Cân bằng"
        perm = str(self.row.get("trade_permission", ""))
        entry = str(self.row.get("entry_status", ""))
        m15 = str(self.row.get("m15_quality", "")).lower()
        price_zone = str(self.row.get("price_vs_zone", ""))
        rr = str(self._rr_field("risk_reward") or "")
        min_score = int(self.row.get("min_score", 65) or 65)
        analysis = self.row.get("analysis_result", {}) if isinstance(self.row.get("analysis_result"), dict) else {}
        gate = analysis.get("trade_gate", {}) if isinstance(analysis, dict) else {}
        gate_allowed = bool(gate.get("allowed", True)) if isinstance(gate, dict) else True

        perm_map = {"allowed": "Được phép", "caution": "Cẩn trọng", "blocked": "Bị chặn", "--": "--"}
        perm_vn = perm_map.get(perm.lower(), perm)

        # 1. Trade Permission
        items.append({
            "pass": perm == "allowed",
            "label": f"Quyền giao dịch: Điểm {best}/{min_score} — {perm_vn}",
        })

        # 2. Gate
        gate_reasons = gate.get("reasons", []) if isinstance(gate, dict) else []
        gate_text = "; ".join(gate_reasons[:2]) if gate_reasons else "không bị cổng lọc chặn"
        items.append({
            "pass": gate_allowed,
            "label": f"Cổng lọc (Gate): {'ĐẠT' if gate_allowed else 'BỊ CHẶN'} — {gate_text}"
        })

        # 3. Score Gap
        items.append({
            "pass": gap >= 10,
            "label": f"Chênh lệch Mua/Bán: Mua {buy_s} vs Bán {sell_s} → khoảng cách {gap} điểm (yêu cầu ≥10) → {'rõ hướng (' + stronger + ')' if gap >= 10 else 'chưa rõ hướng'}"
        })

        # 4. Entry confirmed
        entry_ok = entry in ("confirmed_entry", "ready", "ready_to_trade")
        entry_map = {
            "confirmed_entry": "đã xác nhận",
            "watch_zone": "giá chưa vào vùng giá hoặc chưa có nến xác nhận",
            "waiting_confirmation": "chờ xác nhận H1/M15",
            "no_setup": "chưa có thiết lập giao dịch (setup)",
        }
        entry_label = entry_map.get(entry, entry)
        items.append({
            "pass": entry_ok,
            "label": f"Xác nhận điểm vào lệnh (entry): {entry_label}"
        })

        # 5. Price in zone
        in_zone = price_zone == "in_zone"
        zone_map = {"in_zone": "đang trong vùng giá", "near_zone": "gần vùng giá", "far": "còn xa vùng giá"}
        items.append({
            "pass": in_zone,
            "label": f"Vị trí giá: {zone_map.get(price_zone, price_zone)}"
        })

        # 6. M15
        m15_ok = m15 in ("strict",)
        m15_label = {"strict": "chặt chẽ", "loose": "lỏng lel", "none": "chưa xác nhận", "": "chưa có dữ liệu"}
        # Fix typo lỏng lel thành lỏng lẻo
        m15_label["loose"] = "lỏng lẻo"
        items.append({
            "pass": m15_ok,
            "label": f"M15: {m15_label.get(m15, m15)}"
        })

        # 7. R:R
        min_rr = float(self.row.get("min_rr", 1.3) or 1.3)
        rr_val = 0.0
        try:
            if ":" in str(rr):
                rr_val = float(str(rr).split(":")[1])
            else:
                rr_val = float(rr)
        except (ValueError, TypeError):
            pass
        rr_ok = rr_val >= min_rr
        rr_extra = self._rr_detail_text(
            self._rr_field("risk_reward_range"),
            self._rr_field("risk_reward_effective_range"),
            self._rr_field("expected_effective_rr"),
            self._rr_field("expected_effective_rr_base"),
        )
        if rr_extra:
            rr = f"{rr} ({rr_extra})"
        items.append({
            "pass": rr_ok,
            "label": f"Tỷ lệ R:R là {rr} — {'đạt' if rr_ok else f'dưới tỷ lệ R:R tối thiểu là 1:{min_rr:.1f}'}"
        })

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
        price_zone = str(self.row.get("price_vs_zone") or "").strip().lower() if self.row else ""
        raw = str(self.row.get("entry_status") or "--").strip().lower() if self.row else "--"
        if price_zone == "unknown" and raw in {
            "waiting_confirmation",
            "waiting_for_confirmation",
            "watch_zone",
            "unknown",
            "--",
        }:
            return "Chưa có vùng"
        return self._entry_status_text(raw)

    def _has_no_entry_zone(self) -> bool:
        price_zone = str(self.row.get("price_vs_zone") or "").strip().lower() if self.row else ""
        zones = self._plan_field("entry_zone") if self.row else None
        return price_zone == "unknown" or (price_zone in {"", "--", "none"} and not zones)

    def _m15_text(self) -> str:
        raw = str(self.row.get("m15_quality") or "").strip()
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
            self.diag_text.setHtml("<p style='color:#94a3b8;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;'>Chọn một dòng trong bảng quét để xem chẩn đoán.</p>")
            return
        analysis = self.row.get("analysis_result")
        if not isinstance(analysis, dict):
            self.diag_text.setHtml("<p style='color:#94a3b8;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;'>Không có dữ liệu phân tích để hiển thị chẩn đoán.</p>")
            return

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        body_text_color = "#334155" if light else "#e2e8f0"
        parts: list[str] = []
        parts.append(f"<div style='font-family:-apple-system,Segoe UI,sans-serif;font-size:13px;color:{body_text_color};line-height:1.5;'>")
        parts.append(self._diag_branch_html(light=light))
        parts.append(self._diag_score_breakdown_html(analysis, light=light))
        parts.append(self._diag_gate_html(analysis, light=light))
        parts.append(self._diag_checklist_html(analysis, light=light))
        parts.append(self._diag_pipeline_steps_html(analysis, light=light))
        parts.append(self._diag_final_score_html(analysis, light=light))
        parts.append("</div>")
        self.diag_text.setHtml("\n".join(parts))

    # -- AI Setup Audit ----------------------------------------------------

    def _refresh_ai_audit(self) -> None:
        if not hasattr(self, "audit_text"):
            return
        if not self.row:
            self.audit_text.setHtml("<p style='color:#94a3b8;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;'>Chọn một dòng trong bảng quét để xem AI kiểm định.</p>")
            if getattr(self, "audit_btn", None):
                self.audit_btn.setEnabled(False)
            return
        if getattr(self, "audit_btn", None):
            self.audit_btn.setEnabled(True)
        audit = self.row.get("ai_setup_audit")
        if not isinstance(audit, dict) or not audit:
            self.audit_text.setHtml(
                "<p style='color:#94a3b8;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;'>Chưa có kết quả kiểm định AI. Bấm nút <b>Chạy kiểm định AI</b> để AI phân tích setup này.</p>"
            )
            return

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        self.audit_text.setHtml(self._ai_audit_html(audit, light=light))

    def _run_ai_audit(self) -> None:
        """Run AI audit on-demand for the current row."""
        if not self.row:
            return
        if not self.app or not hasattr(self.app, "scanner_controller"):
            self.audit_status.setText("Lỗi: không tìm thấy scanner controller.")
            return

        self.audit_btn.setEnabled(False)
        self.audit_status.setText("Đang gọi AI...")
        self.audit_text.setHtml("<p style='color:#f59e0b;'>⏳ Đang chờ AI phản hồi...</p>")

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
            raw_display = f"<pre style='color:#94a3b8;font-size:11px;max-height:200px;overflow:auto;'>{raw}</pre>" if raw else ""
            self.audit_status.setText(f"Lỗi: {audit['auditor_error']}")
            self.audit_text.setHtml(
                f"<p style='color:#e11d48;'>Lỗi kiểm định: {audit['auditor_error']}</p>"
                f"<p style='color:#94a3b8;'>AI không trả về JSON hợp lệ.</p>"
                f"{raw_display}"
            )
        else:
            self.audit_status.setText("Hoàn tất kiểm định.")
            self.row["ai_setup_audit"] = audit
            try:
                light = self.settings_service.load().display.theme == "light"
            except Exception:
                light = False
            self.audit_text.setHtml(self._ai_audit_html(audit, light=light))

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
            "<div style='font-family:-apple-system,Segoe UI,sans-serif;font-size:13px;'>",
            f"<h2 style='color:{title_color};margin:0 0 4px;font-size:14px;font-weight:bold;'>AI Setup Auditor</h2>",
            f"<p style='color:{desc_color};font-size:12px;margin:0 0 12px;'>"
            "AI chỉ kiểm định setup rule engine đã tạo. Phần này không tự thay đổi quyết định, gate hoặc auto trade."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:14px;background:{bg_color};border-radius:6px;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;'>",
            "<tr>",
            f"<td style='padding:4px 12px;color:{text_color};width:120px;font-size:13px;'>Kết luận</td>",
            f"<td style='padding:4px 12px;color:{color};font-weight:bold;font-size:13px;'>{label}</td>",
            f"<td style='padding:4px 12px;color:{text_color};width:90px;font-size:13px;'>Tin cậy</td>",
            f"<td style='padding:4px 12px;color:{value_color};font-weight:bold;font-size:13px;'>{confidence}/100</td>",
            f"<td style='padding:4px 12px;color:{text_color};width:110px;font-size:13px;'>Chất lượng plan</td>",
            f"<td style='padding:4px 12px;color:{value_color};font-weight:bold;font-size:13px;'>{quality}/100</td>",
            "</tr>",
            "</table>",
        ]
        if error:
            rows.append(
                f"<div style='color:{error_text};background:{error_bg};border:1px solid {error_border};"
                f"border-radius:6px;padding:10px 12px;margin-bottom:12px;font-size:13px;'>AI auditor lỗi: {error}</div>"
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
            f"<h3 style='color:{color};margin:16px 0 6px;font-size:13px;font-weight:bold;'>{escape(title)}</h3>"
            f"<div style='color:{text_color};background:{bg_color};border:1px solid {border_color};"
            f"border-radius:6px;padding:10px 12px;margin-bottom:8px;font-size:13px;'>{body}</div>"
        )

    def _audit_list_block(self, title: str, values: object, color: str, light: bool = False) -> str:
        items = values if isinstance(values, list) else []
        muted_color = "#736B60" if light else "#94a3b8"
        text_color = "#111827" if light else "#e2e8f0"
        bg_color = "#ffffff" if light else "#111827"
        border_color = "#D6D2C8" if light else "#334155"

        if not items:
            body = f"<span style='color:{muted_color};font-size:13px;'>Không có mục đáng chú ý.</span>"
        else:
            body = "<ul style='margin:0;padding-left:18px;font-size:13px;'>" + "".join(
                f"<li style='margin:4px 0;color:{text_color};font-size:13px;'>{escape(str(item))}</li>"
                for item in items
                if str(item).strip()
            ) + "</ul>"
        return (
            f"<h3 style='color:{color};margin:16px 0 6px;font-size:13px;font-weight:bold;'>{escape(title)}</h3>"
            f"<div style='background:{bg_color};border:1px solid {border_color};border-radius:6px;"
            f"padding:10px 12px;margin-bottom:8px;font-size:13px;'>{body}</div>"
        )

    # -- Branch indicator ---------------------------------------------------

    def _diag_branch_html(self, light: bool = False) -> str:
        """Show whether this symbol runs on Branch A (default) or Branch B (backtest config)."""
        branch = str(self.row.get("auto_trade_branch", "A")).upper()
        sc = "#736B60" if light else "#94a3b8"

        if branch == "B":
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
                f"<table style='width:100%;border-collapse:collapse;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;"
                f"background:{sub_bg};border:1px solid {sub_border};border-radius:6px;margin-bottom:8px;'>"
                f"<tr>"
                f"<td style='padding:4px 10px;color:{sc};width:140px;font-size:13px;'>Chế độ thị trường:</td>"
                f"<td style='padding:4px 10px;color:{text_color};font-weight:bold;font-size:13px;'>{regime_text}</td>"
                f"</tr>"
                f"<tr>"
                f"<td style='padding:4px 10px;color:{sc};font-size:13px;'>Hướng vào lệnh:</td>"
                f"<td style='padding:4px 10px;color:{text_color};font-weight:bold;font-size:13px;'>{side_text}</td>"
                f"</tr>"
                f"<tr>"
                f"<td style='padding:4px 10px;color:{sc};font-size:13px;'>Điểm tối thiểu:</td>"
                f"<td style='padding:4px 10px;color:{text_color};font-weight:bold;font-size:13px;'>{min_score_val} điểm <span style='font-weight:normal;color:{sc};'>{score_desc}</span></td>"
                f"</tr>"
                f"<tr>"
                f"<td style='padding:4px 10px;color:{sc};font-size:13px;'>R:R tối thiểu:</td>"
                f"<td style='padding:4px 10px;color:{text_color};font-weight:bold;font-size:13px;'>{rr_text}</td>"
                f"</tr>"
                f"</table>"
            )

            return (
                f"<table style='width:100%;border-collapse:collapse;background:{bg};border-left:4px solid {accent};margin:8px 0 12px;'>"
                f"<tr>"
                f"<td style='padding:4px 16px;'>"
                f"<div style='font-size:16px;font-weight:bold;color:{accent};margin-bottom:8px;'>"
                f"✅ Nhánh B — Có cấu hình Backtest</div>"
                f"{config_table_html}"
                f"<div style='font-size:12px;color:{ref_color};background:{ref_bg};border:1px solid {ref_border};"
                f"padding:8px 12px;border-radius:6px;line-height:1.5;'>"
                f"💡 Khi vào lệnh tự động, pipeline <b>chỉ để tham khảo</b>. "
                f"Hệ thống dùng các thông số trên để quyết định, "
                f"không phụ thuộc trạng thái Ready/Watch/Wait/Stand Aside của pipeline."
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
                f"<div style='font-size:14px;font-weight:bold;color:{accent};margin-bottom:4px;'>"
                f"⚙️ Nhánh A — Không có cấu hình Backtest</div>"
                f"<div style='font-size:13px;color:{sc};line-height:1.5;'>"
                f"Phải được pipeline đánh giá <b>Ready + Allowed</b> mới vào lệnh tự động. "
                f"Các thông số bên dưới quyết định trực tiếp việc vào lệnh.</div>"
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
            "<div style='font-family:-apple-system,Segoe UI,sans-serif;font-size:13px;'>",
            f"<h2 style='color:{title_color};margin:0 0 4px;font-size:14px;font-weight:bold;'>Phân rã điểm số</h2>",
            f"<p style='color:{desc_color};font-size:12px;margin:0 0 12px;'>"
            "Hệ thống chấm điểm 6 thành phần cho mỗi hướng MUA và BÁN. "
            "<b>Xu hướng</b> (EMA50/200, cấu trúc HH/HL) · "
            "<b>Động lượng</b> (RSI, MACD) · "
            "<b>Vị trí</b> (gần hỗ trợ/kháng cự) · "
            "<b>SMC</b> (BOS, CHOCH, vùng cung/cầu) · "
            "<b>Rủi ro</b> (ATR, spread, tin tức) · "
            "<b>Vĩ mô</b> (lãi suất, DXY, VIX, US10Y). "
            "Tổng 0-100; &ge;80 Mạnh, &ge;65 Khá, &ge;50 Trung bình, &lt;50 Yếu."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:16px;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;'>",
            "<tr>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};font-size:13px;font-weight:bold;' title='Thành phần được chấm điểm'>Thành phần</th>",
            f"<th style='text-align:center;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:55px;font-size:13px;font-weight:bold;' title='Điểm tối đa của thành phần này'>Max</th>",
            f"<th style='text-align:center;padding:4px 10px;border-bottom:2px solid #ea580c;color:#ea580c;width:55px;font-size:13px;font-weight:bold;' title='Điểm kịch bản MUA'>MUA</th>",
            f"<th style='text-align:center;padding:4px 10px;border-bottom:2px solid #f43f5e;color:#f43f5e;width:55px;font-size:13px;font-weight:bold;' title='Điểm kịch bản BÁN'>BÁN</th>",
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
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-size:13px;' title='{tooltip}'>{label}</td>"
                f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};font-size:13px;'>{eff_max}</td>"
                f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{_color(int(bv), eff_max)};font-weight:bold;font-size:13px;'>{int(bv)}</td>"
                f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{_color(int(sv), eff_max)};font-weight:bold;font-size:13px;'>{int(sv)}</td>"
                f"</tr>"
            )

        rows.append(
            f"<tr style='border-top:2px solid {border_color};'>"
            f"<td style='padding:4px 10px;color:{label_color};font-weight:bold;font-size:13px;' title='Tổng điểm tín hiệu sau khi chuẩn hóa (0-100)'>TỔNG</td>"
            f"<td style='text-align:center;padding:4px 10px;color:{desc_color};font-size:13px;'>100</td>"
            f"<td style='text-align:center;padding:4px 10px;color:#ea580c;font-weight:bold;font-size:13px;'>{buy_total}</td>"
            f"<td style='text-align:center;padding:4px 10px;color:#f43f5e;font-weight:bold;font-size:13px;'>{sell_total}</td>"
            f"</tr>"
        )
        rows.append("</table>")

        # Rating + modifiers — use table for reliable rendering
        rows.append(
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:14px;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;background:{bg_color};border-radius:6px;'>"
            "<tr>"
            f"<td style='padding:4px 12px;color:{muted_color};width:110px;font-size:13px;'>Đánh giá MUA</td>"
            f"<td style='padding:4px 12px;color:{text_color};font-size:13px;'>{_rating(buy_total)}</td>"
            f"<td style='padding:4px 12px;color:{muted_color};width:110px;font-size:13px;'>Tương quan MUA</td>"
            f"<td style='padding:4px 12px;color:{text_color};font-size:13px;'><b>{buy_corr:+.0f}</b></td>"
            "</tr>"
            "<tr>"
            f"<td style='padding:4px 12px;color:{muted_color};font-size:13px;'>Đánh giá BÁN</td>"
            f"<td style='padding:4px 12px;color:{text_color};font-size:13px;'>{_rating(sell_total)}</td>"
            f"<td style='padding:4px 12px;color:{muted_color};width:110px;font-size:13px;'>Tương quan BÁN</td>"
            f"<td style='padding:4px 12px;color:{text_color};font-size:13px;'><b>{sell_corr:+.0f}</b></td>"
            "</tr>"
        )

        if buy_macro_status or sell_macro_status:
            rows.append(
                "<tr>"
                f"<td style='padding:4px 12px;color:{muted_color};font-size:13px;'>Vĩ mô MUA</td>"
                f"<td style='padding:4px 12px;color:{text_color};font-size:13px;'><b>{buy_macro_status or 'trung lập'}</b></td>"
                f"<td style='padding:4px 12px;color:{muted_color};font-size:13px;'>Vĩ mô BÁN</td>"
                f"<td style='padding:4px 12px;color:{text_color};font-size:13px;'><b>{sell_macro_status or 'trung lập'}</b></td>"
                "</tr>"
            )
        rows.append(
            "<tr>"
            f"<td style='padding:4px 12px;color:{muted_color};font-size:13px;'>Phạt MUA</td>"
            f"<td style='padding:4px 12px;color:{desc_color};font-size:13px;'>{buy_penalty}</td>"
            f"<td style='padding:4px 12px;color:{muted_color};font-size:13px;'>Phạt BÁN</td>"
            f"<td style='padding:4px 12px;color:{desc_color};font-size:13px;'>{sell_penalty}</td>"
            "</tr>"
        )
        rows.append(
            "<tr>"
            f"<td style='padding:4px 12px;color:{muted_color};font-size:13px;'>Lý do MUA</td>"
            f"<td style='padding:4px 12px;color:{desc_color};font-size:13px;'>{buy_reason}</td>"
            f"<td style='padding:4px 12px;color:{muted_color};font-size:13px;'>Lý do BÁN</td>"
            f"<td style='padding:4px 12px;color:{desc_color};font-size:13px;'>{sell_reason}</td>"
            "</tr>"
        )

        # SMC reason
        buy_smc = buy.get("smc_reason", "")
        sell_smc = sell.get("smc_reason", "")
        if buy_smc or sell_smc:
            rows.append(
                "<tr>"
                f"<td style='padding:6px 12px;color:{muted_color};font-size:13px;'>SMC MUA</td>"
                f"<td style='padding:6px 12px;color:{desc_color};font-size:13px;'>{buy_smc or '--'}</td>"
                f"<td style='padding:6px 12px;color:{muted_color};font-size:13px;'>SMC BÁN</td>"
                f"<td style='padding:6px 12px;color:{desc_color};font-size:13px;'>{sell_smc or '--'}</td>"
                "</tr>"
            )
        rows.append("</table>")

        rows.append("</div>")
        return "\n".join(rows)

    # -- Gate Diagnostics --------------------------------------------------

    def _diag_gate_html(self, analysis: dict, light: bool = False) -> str:
        gate = analysis.get("trade_gate", {})
        if not isinstance(gate, dict):
            gate = {}
        permission = analysis.get("trade_permission", {})
        if not isinstance(permission, dict):
            permission = {}

        # Try pipeline diagnostics first (from backtest), fall back to trade_gate
        pipe_diags = analysis.get("pipeline_diagnostics")
        gate_checks: list[dict] = []
        if isinstance(pipe_diags, list):
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
        }

        title_color = "#D94625" if light else "#f97316"
        desc_color = "#736B60" if light else "#64748b"
        border_color = "#D6D2C8" if light else "#334155"
        row_border_color = "#EAE6DF" if light else "#1e293b"
        text_color = "#111827" if light else "#e2e8f0"
        muted_color = "#57534E" if light else "#94a3b8"
        bg_color = "#f1f5f9" if light else "#1e293b"

        rows = [
            f"<h2 style='color:{title_color};margin:20px 0 4px;font-size:14px;font-weight:bold;'>Gate kiểm tra</h2>",
            f"<p style='color:{desc_color};font-size:12px;margin:0 0 12px;'>"
            "Gate là các lớp kiểm tra trước khi cho phép vào lệnh. "
            "Mỗi gate có thể <b style='color:#22c55e;'>Cho qua</b>, "
            "<b style='color:#fbbf24;'>Cảnh báo</b> (giới hạn mức quyết định), "
            "hoặc <b style='color:#ef4444;'>Chặn</b> (cấm vào lệnh). "
            "Thứ tự ưu tiên: CHẶN > CẢNH BÁO > Pass."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;'>",
            "<tr>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:110px;font-size:13px;font-weight:bold;'>Gate</th>",
            f"<th colspan='2' style='text-align:left;padding:4px 10px;padding-left:10px;border-bottom:2px solid {border_color};color:{muted_color};width:95px;font-size:13px;font-weight:bold;'>Kết quả</th>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};font-size:13px;font-weight:bold;'>Ý nghĩa / Chi tiết</th>",
            "</tr>",
        ]

        for gc in gate_checks:
            if not isinstance(gc, dict):
                continue
            g_name = gc.get("gate", "?")
            g_status = gc.get("status", "pass")
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
            else:
                icon = "🟢"
                color = "#22c55e"
                text = "Qua"

            rows.append(
                f"<tr>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-size:13px;' title='{g_explain}'>{g_label}</td>"
                f"<td style='width:24px;text-align:right;padding:4px 0;border-bottom:1px solid {row_border_color};font-family:\"Segoe UI Emoji\",\"Apple Color Emoji\",\"Segoe UI\";font-size:13px;'>{icon}</td>"
                f"<td style='width:71px;text-align:left;padding:4px 0 4px;padding-left:6px;border-bottom:1px solid {row_border_color};color:{color};font-weight:bold;font-size:13px;'>{text}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{muted_color};font-size:13px;'>{g_explain} &mdash; {g_detail}</td>"
                f"</tr>"
            )
        rows.append("</table>")

        # Summary
        allowed = gate.get("allowed", True)
        cap = gate.get("decision_cap") or permission.get("decision_cap") or "không"
        reasons = gate.get("reasons", []) or []
        perm_status = permission.get("status", "?")
        perm_text = {"allowed": "Được phép", "caution": "Cẩn trọng", "blocked": "Bị chặn"}.get(perm_status, perm_status)

        if not allowed:
            summary_color = "#ef4444"
            summary_text = f"BỊ CHẶN (mức: {cap})"
        elif cap in ("WATCH_ONLY", "WAITING_CONFIRMATION"):
            summary_color = "#fbbf24"
            summary_text = f"CẢNH BÁO (mức: {cap})"
        else:
            summary_color = "#22c55e"
            summary_text = f"CHO PHÉP (mức: {cap})"

        rows.append(
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:8px;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;"
            f"background:{bg_color};border-radius:6px;'>"
            f"<tr>"
            f"<td style='padding:8px 12px;color:{muted_color};width:130px;font-size:13px;'>KẾT LUẬN GATE</td>"
            f"<td style='padding:8px 12px;color:{summary_color};font-weight:bold;font-size:13px;'>{summary_text}</td>"
            f"<td style='padding:8px 12px;color:{muted_color};width:60px;font-size:13px;'>Quyền</td>"
            f"<td style='padding:8px 12px;color:{text_color};font-size:13px;'>{perm_text}</td>"
            f"</tr>"
            f"</table>"
        )
        if reasons:
            rows.append(
                f"<div style='font-size:13px;color:#ef4444;padding:4px 12px;margin-bottom:8px;'>"
                f"Lý do: {'; '.join(reasons)}"
                f"</div>"
            )

        rows.append("</div>")
        return "\n".join(rows)

    def _build_gate_checks_from_result(self, analysis: dict) -> list[dict]:
        """Build gate checks from trade_gate + data_quality when pipeline diagnostics unavailable."""
        gate = analysis.get("trade_gate", {})
        if not isinstance(gate, dict):
            gate = {}
        dq = analysis.get("data_quality", {})
        if not isinstance(dq, dict):
            dq = {}
        direction = analysis.get("direction_bias", {})
        if not isinstance(direction, dict):
            direction = {}
        primary = analysis.get("scenarios", [{}])[0] if isinstance(analysis.get("scenarios"), list) else {}

        block_codes = set(gate.get("block_codes", []) or [])
        warning_codes = set(gate.get("warning_codes", []) or [])

        def _st(code: str) -> str:
            if code in block_codes:
                return "block"
            if code in warning_codes:
                return "warning"
            return "pass"

        from core.reason_codes import (
            MT5_NOT_READY, SPREAD_ABNORMAL, DATA_QUALITY_WARNING,
            HIGH_IMPACT_NEWS_NEARBY, DAILY_LOSS_LIMIT_REACHED, WEEKLY_LOSS_LIMIT_REACHED,
            M15_NOT_CONFIRMED, M15_LOOSE_CONFIRMATION, EXPECTED_RR_TOO_LOW,
            BUY_SELL_SCORE_GAP_LOW, ZONE_BROKEN,
        )

        return [
            {"gate": "MT5", "status": _st(MT5_NOT_READY),
             "detail": "MT5 sẵn sàng" if _st(MT5_NOT_READY) == "pass" else "MT5 chưa sẵn sàng"},
            {"gate": "Spread", "status": _st(SPREAD_ABNORMAL),
             "detail": f"spread={dq.get('spread_status', 'normal')}"},
            {"gate": "DataQuality", "status": _st(DATA_QUALITY_WARNING),
             "detail": "không cảnh báo" if _st(DATA_QUALITY_WARNING) == "pass" else str(dq.get('warning', ''))},
            {"gate": "News", "status": _st(HIGH_IMPACT_NEWS_NEARBY),
             "detail": "không có tin gần" if _st(HIGH_IMPACT_NEWS_NEARBY) == "pass" else "có tin tác động cao trong 30 phút"},
            {"gate": "DailyWeeklyLoss", "status": _st(DAILY_LOSS_LIMIT_REACHED) if _st(DAILY_LOSS_LIMIT_REACHED) != "pass" else _st(WEEKLY_LOSS_LIMIT_REACHED),
             "detail": "trong giới hạn" if _st(DAILY_LOSS_LIMIT_REACHED) == "pass" and _st(WEEKLY_LOSS_LIMIT_REACHED) == "pass" else "vượt giới hạn lỗ"},
            {"gate": "AccountGuard", "status": "pass",
             "detail": "không kiểm tra (thiếu dữ liệu pipeline)"},
            {"gate": "Journal", "status": "pass",
             "detail": "không kiểm tra (thiếu dữ liệu pipeline)"},
            {"gate": "M15", "status": _st(M15_NOT_CONFIRMED) if _st(M15_NOT_CONFIRMED) != "pass" else _st(M15_LOOSE_CONFIRMATION),
             "detail": f"M15={primary.get('m15_quality', '?')}"},
            {"gate": "ExpectedRR", "status": _st(EXPECTED_RR_TOO_LOW),
             "detail": f"R:R={primary.get('expected_effective_rr', '?')} sau spread (danh nghĩa {primary.get('risk_reward', '?')}, dải {ScannerDetailScreen._rr_range_compact(primary.get('risk_reward_range'))})"},
            {"gate": "ScoreGap", "status": _st(BUY_SELL_SCORE_GAP_LOW),
             "detail": f"chênh lệch={direction.get('score_gap', '?')} (tối thiểu {direction.get('min_gap', 10)})"},
            {"gate": "ZoneBroken", "status": _st(ZONE_BROKEN),
             "detail": "vùng còn nguyên" if _st(ZONE_BROKEN) == "pass" else "vùng đã bị phá"},
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
            f"<h2 style='color:{title_color};margin:20px 0 4px;font-size:14px;font-weight:bold;'>Điều kiện vào lệnh</h2>",
            f"<p style='color:{desc_color};font-size:12px;margin:0 0 12px;'>"
            "Các điều kiện cần đạt trước khi vào lệnh thật. "
            "<b style='color:#22c55e;'>✅ Đạt</b> = đã thỏa mãn. "
            "<b style='color:#fbbf24;'>⏳ Chờ</b> = cần theo dõi thêm, chưa nên vào lệnh vội."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;'>",
            "<tr>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:110px;font-size:13px;font-weight:bold;'>Điều kiện</th>",
            f"<th colspan='2' style='text-align:left;padding:4px 10px;padding-left:10px;border-bottom:2px solid {border_color};color:{muted_color};width:95px;font-size:13px;font-weight:bold;'>Trạng thái</th>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:160px;font-size:13px;font-weight:bold;'>Giá trị</th>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};font-size:13px;font-weight:bold;'>Ghi chú</th>",
            "</tr>",
        ]

        for item in checklist:
            if not isinstance(item, dict):
                continue
            label = item.get("label", "?")
            passed = item.get("status") == "pass"
            value = item.get("value", "--")
            note = item.get("note", "")

            icon = "✅" if passed else "⏳"
            status_text = "Đạt" if passed else "Chờ"
            color = "#22c55e" if passed else "#fbbf24"

            rows.append(
                f"<tr>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-size:13px;'>{label}</td>"
                f"<td style='width:24px;text-align:right;padding:4px 0;border-bottom:1px solid {row_border_color};font-family:\"Segoe UI Emoji\",\"Apple Color Emoji\",\"Segoe UI\";font-size:13px;'>{icon}</td>"
                f"<td style='width:71px;text-align:left;padding:4px 0 4px;padding-left:6px;border-bottom:1px solid {row_border_color};color:{color};font-weight:bold;font-size:13px;'>{status_text}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{muted_color};font-size:13px;'>{value}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};font-size:13px;'>{note}</td>"
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
        }

        title_color = "#D94625" if light else "#fb923c"
        desc_color = "#736B60" if light else "#64748b"
        border_color = "#D6D2C8" if light else "#334155"
        row_border_color = "#EAE6DF" if light else "#1e293b"
        text_color = "#111827" if light else "#e2e8f0"
        muted_color = "#57534E" if light else "#94a3b8"

        rows = [
            f"<h2 style='color:{title_color};margin:20px 0 4px;font-size:14px;font-weight:bold;'>Pipeline từng bước</h2>",
            f"<p style='color:{desc_color};font-size:12px;margin:0 0 12px;'>"
            "Quy trình phân tích tuần tự 7 bước. Nếu một bước <b style='color:#ef4444;'>thất bại</b>, "
            "các bước sau không chạy. Bước <b style='color:#fbbf24;'>cảnh báo</b> vẫn tiếp tục "
            "nhưng có thể ảnh hưởng kết quả cuối cùng."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;'>",
            "<tr>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:120px;font-size:13px;font-weight:bold;'>Bước</th>",
            f"<th colspan='2' style='text-align:left;padding:4px 10px;padding-left:10px;border-bottom:2px solid {border_color};color:{muted_color};width:95px;font-size:13px;font-weight:bold;'>Kết quả</th>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};font-size:13px;font-weight:bold;'>Diễn giải / Tóm tắt</th>",
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
        }

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
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-size:13px;' title='{explain}'>{label}</td>"
                f"<td style='width:24px;text-align:right;padding:4px 0;border-bottom:1px solid {row_border_color};font-family:\"Segoe UI Emoji\",\"Apple Color Emoji\",\"Segoe UI\";font-size:13px;'>{icon}</td>"
                f"<td style='width:71px;text-align:left;padding:4px 0 4px;padding-left:6px;border-bottom:1px solid {row_border_color};color:{color};font-weight:bold;font-size:13px;'>{text}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{muted_color};font-size:13px;'>{summary}</td>"
                f"</tr>"
            )
        rows.append("</table>")
        return "\n".join(rows)

    # -- Final Score Breakdown ----------------------------------------------

    def _diag_final_score_html(self, analysis: dict, light: bool = False) -> str:
        final_detail = analysis.get("final_score_detail", {})
        if not isinstance(final_detail, dict):
            final_detail = {}
        final_score = analysis.get("final_score", 0)
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
            f"<h2 style='color:{title_color};margin:20px 0 4px;font-size:14px;font-weight:bold;'>Điểm cuối cùng</h2>",
            f"<p style='color:{desc_color};font-size:12px;margin:0 0 12px;'>"
            "Điểm tổng hợp từ 3 nguồn: <b>Tín hiệu</b> (điểm kỹ thuật/SMC/vĩ mô), "
            "<b>Bằng chứng nhật ký</b> (hiệu suất lịch sử của setup tương tự), "
            "<b>Chất lượng thực thi</b> (tỷ lệ vào lệnh thành công trước đây). "
            "Điểm này quyết định hành động cuối cùng."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;'>",
            "<tr>",
            f"<th style='text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};font-size:13px;font-weight:bold;'>Thành phần</th>",
            f"<th style='text-align:center;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:60px;font-size:13px;font-weight:bold;' title='Trọng lượng trong công thức'>TL</th>",
            f"<th style='text-align:center;padding:4px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:60px;font-size:13px;font-weight:bold;' title='Điểm thành phần'>Điểm</th>",
            "</tr>",
            f"<tr><td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-size:13px;' title='Điểm tín hiệu từ bước chấm điểm (0-100)'>Tín hiệu</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};font-size:13px;'>65%</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-weight:bold;font-size:13px;'>{signal_s}</td></tr>",
            f"<tr><td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-size:13px;' title='Điểm từ nhật ký giao dịch cũ (setup tương tự từng thắng không)'>Bằng chứng (NK)</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};font-size:13px;'>20%</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-weight:bold;font-size:13px;'>{evidence_s}</td></tr>",
            f"<tr><td style='padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-size:13px;' title='Điểm chất lượng thực thi lệnh (tỷ lệ khớp lệnh thành công)'>Chất lượng thực thi</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};font-size:13px;'>15%</td>"
            f"<td style='text-align:center;padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-weight:bold;font-size:13px;'>{exec_s}</td></tr>",
            f"<tr style='border-top:2px solid {border_color};'>"
            f"<td style='padding:4px 10px;color:{label_color};font-weight:bold;font-size:13px;' title='Điểm cuối cùng = Tín hiệu×0.65 + Bằng chứng×0.20 + Thực thi×0.15'>ĐIỂM CUỐI</td>"
            f"<td style='text-align:center;padding:4px 10px;color:{desc_color};font-size:13px;'>100%</td>"
            f"<td style='text-align:center;padding:4px 10px;color:#22c55e;font-weight:bold;font-size:13px;'>{final_score}</td></tr>",
            "</table>",
        ]

        # Decision
        dec_decision = decision.get("decision", "?")
        dec_action = decision.get("legacy_action", "?")
        DECISION_EXPLAIN = {
            "READY_TO_TRADE": "Sẵn sàng giao dịch — mọi điều kiện đều đạt",
            "WAITING_CONFIRMATION": "Chờ xác nhận thêm — cần thêm tín hiệu H1/M15",
            "WATCH_ONLY": "Chỉ theo dõi — chưa đủ điều kiện vào lệnh",
            "AGGRESSIVE_SETUP": "Setup táo bạo — rủi ro cao hơn bình thường",
            "STAND_ASIDE": "Đứng ngoài — không nên giao dịch lúc này",
            "TRADE_BLOCKED": "Bị chặn — gate đã chặn không cho vào lệnh",
        }
        dec_explain = DECISION_EXPLAIN.get(dec_decision, "")
        rows.append(
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;background:{bg_color};border-radius:6px;'>"
            "<tr>"
            f"<td style='padding:4px 12px;color:{muted_color};width:110px;font-size:13px;'>Quyết định</td>"
            f"<td style='padding:4px 12px;color:{text_color};font-size:13px;'><b>{dec_decision}</b>"
            + (f" <span style='color:{desc_color};font-size:13px;'>({dec_explain})</span>" if dec_explain else "")
            + f" → hành động: <b>{dec_action}</b></td>"
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
