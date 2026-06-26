from __future__ import annotations

from html import escape

from config.paths import app_data_dir
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)
from controllers.journal_controller import JournalController
from services.storage_service import JsonStorage

from ui.components.chart_view import AnalysisChartView
from ui.components.info_card import InfoCard
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
        ov = QHBoxLayout()
        ov.setContentsMargins(0, 0, 0, 0)
        ov.setSpacing(12)
        overview_tab.layout().addLayout(ov)

        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        # -- Hero verdict bar --
        self.hero_bar = QLabel("")
        self.hero_bar.setObjectName("ScannerDetailHero")
        self.hero_bar.setWordWrap(True)
        self.hero_bar.setTextFormat(Qt.TextFormat.RichText)
        self.hero_bar.setStyleSheet(
            "QLabel#ScannerDetailHero { border-radius: 6px; padding: 4px 12px; font-size: 14px; background: #1e293b; border: 1px solid #334155; }"
        )
        left_col.addWidget(self.hero_bar)

        # -- Chart --
        self.chart = AnalysisChartView()
        self.chart_frame = QFrame()
        self.chart_frame.setObjectName("AnalysisChartFrame")
        cl = QVBoxLayout(self.chart_frame)
        cl.setContentsMargins(4, 4, 4, 4)
        cl.setSpacing(0)
        cl.addWidget(self.chart)
        left_col.addWidget(self.chart_frame, 1)

        ov.addLayout(left_col, 7)

        # -- Right Col: Info Cards (2-column grid) --
        right_widget = QWidget()
        right_grid = QGridLayout(right_widget)
        right_grid.setHorizontalSpacing(8)
        right_grid.setVerticalSpacing(8)
        right_grid.setContentsMargins(0, 0, 0, 0)

        self.card_best = InfoCard("Điểm tốt nhất", "--", "", accent="#ea580c")
        self.card_buysell = InfoCard("Mua / Bán", "--", "", accent="#fb7185")
        self.card_final = InfoCard("Điểm cuối", "--", "", accent="#10b981")
        self.card_gap = InfoCard("Chênh lệch", "--", "", accent="#f59e0b")
        self.card_macro_score = InfoCard("Điểm vĩ mô", "--", "", accent="#38bdf8")
        self.card_rr = InfoCard("Tỷ lệ R:R", "--", "", accent="#ea580c")

        self.card_entry = InfoCard("Vùng vào lệnh", "--", "", accent="#10b981")
        self.card_position = InfoCard("Vị trí giá", "--", "", accent="#f59e0b")
        self.card_m15 = InfoCard("Khung M15", "--", "", accent="#f59e0b")
        self.card_scanner_group = InfoCard("Nhóm scanner", "--", "", accent="#a78bfa")
        self.card_regime = InfoCard("Chế độ TT", "--", "", accent="#fb7185")
        self.card_permission = InfoCard("Quyền giao dịch", "--", "", accent="#e11d48")
        self.card_journal_sample = InfoCard("Mẫu nhật ký", "--", "", accent="#9ca3af")
        self.card_journal_expectancy = InfoCard("Kỳ vọng NK", "--", "", accent="#38bdf8")

        right_grid.addWidget(self.card_best, 0, 0)
        right_grid.addWidget(self.card_buysell, 0, 1)
        right_grid.addWidget(self.card_final, 1, 0)
        right_grid.addWidget(self.card_gap, 1, 1)
        right_grid.addWidget(self.card_macro_score, 2, 0)
        right_grid.addWidget(self.card_rr, 2, 1)
        right_grid.addWidget(self.card_entry, 3, 0)
        right_grid.addWidget(self.card_position, 3, 1)
        right_grid.addWidget(self.card_m15, 4, 0)
        right_grid.addWidget(self.card_scanner_group, 4, 1)
        right_grid.addWidget(self.card_regime, 5, 0)
        right_grid.addWidget(self.card_permission, 5, 1)
        right_grid.addWidget(self.card_journal_sample, 6, 0)
        right_grid.addWidget(self.card_journal_expectancy, 6, 1)

        # Entry checklist card (row 7, span 2 cols)
        self.entry_checklist_card = QFrame()
        self.entry_checklist_card.setObjectName("EntryChecklistCard")
        self.entry_checklist_layout = QVBoxLayout(self.entry_checklist_card)
        self.entry_checklist_layout.setContentsMargins(12, 10, 12, 10)
        self.entry_checklist_layout.setSpacing(4)
        right_grid.addWidget(self.entry_checklist_card, 7, 0, 1, 2)

        right_grid.setRowStretch(8, 1)

        ov.addWidget(right_widget, 2)

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
        self._render()

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
                "Tóm tắt mã được chọn từ bảng Scanner; chạy phân tích đầy đủ khi cần trade plan chi tiết.",
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
        self._refresh_cards()
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
            self.chart.show_error("Khong the tao du lieu bieu do tu ket qua quet.")

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

        action_code = str(self.row.get("display_action") or self.row.get("scanner_action") or "--")
        action_text = self._action_text(action_code)
        rank = self.row.get("rank", "--")
        reason = self._decision_reason()

        if light:
            if action_code == "ready":
                bg, border, accent, icon = "#d1fae5", "#10b981", "#047857", "✅"
            elif action_code in ("watch", "wait"):
                bg, border, accent, icon = "#fef3c7", "#f59e0b", "#b45309", "⏳"
            elif action_code == "skip":
                bg, border, accent, icon = "#ffe4e6", "#e11d48", "#be123c", "❌"
            else:
                bg, border, accent, icon = "#f1f5f9", "#cbd5e1", "#475569", "ℹ️"
        else:
            if action_code == "ready":
                bg, border, accent, icon = "#064e3b", "#065f46", "#10b981", "✅"
            elif action_code in ("watch", "wait"):
                bg, border, accent, icon = "#451a03", "#78350f", "#f59e0b", "⏳"
            elif action_code == "skip":
                bg, border, accent, icon = "#4c0519", "#881337", "#e11d48", "❌"
            else:
                bg, border, accent, icon = "#0f172a", "#1e293b", "#94a3b8", "ℹ️"

        self.hero_bar.setStyleSheet(
            f"QLabel#ScannerDetailHero {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {border};"
            f"  border-radius: 6px;"
            f"  padding: 6px 12px;"
            f"}}"
        )

        text_color = "#1e293b" if light else "#cbd5e1"
        bold_color = "#0f172a" if light else "#f8fafc"

        self.hero_bar.setText(
            f"<table width='100%' style='margin:0;padding:0;border:none;'><tr>"
            f"<td width='120' style='vertical-align:middle;'>"
            f"<span style='color:{accent};font-size:15px;font-weight:bold;letter-spacing:1px;'>{icon} {action_text.upper()}</span>"
            f"</td>"
            f"<td style='vertical-align:middle;'>"
            f"<span style='color:{text_color};font-size:14px;font-weight:normal;'>"
            f"Hạng <b style='color:{bold_color};'>#{rank}</b> &nbsp;&bull;&nbsp; {reason}"
            f"</span>"
            f"</td>"
            f"</tr></table>"
        )
        self.hero_bar.show()

    def _refresh_cards(self) -> None:
        """Populate the 10 info cards with scanner row data."""
        if not self.row:
            return

        # Row 1: scores
        best = self.row.get("best_score", "--")
        self.card_best.set_value(f"{best}/100")
        rating = self._score_rating(int(best) if str(best).isdigit() else 0)
        self.card_best.set_detail(rating)

        buy_s = self.row.get("buy_score", "--")
        sell_s = self.row.get("sell_score", "--")
        bias = self.row.get("direction_bias", {})
        side_label = ""
        if isinstance(bias, dict):
            side = str(bias.get("best_side", ""))
            clarity = "rõ" if bias.get("is_clear_bias") else "TB"
            side_label = f"{'MUA' if side == 'buy' else 'BÁN' if side == 'sell' else '?'} {clarity}"
        self.card_buysell.set_value(f"{buy_s} / {sell_s}")
        self.card_buysell.set_detail(side_label)

        final_v = self.row.get("final_score", "--")
        self.card_final.set_value(f"{final_v}/100")
        self.card_final.set_detail(self._score_rating(int(final_v) if str(final_v).isdigit() else 0))

        gap = self.row.get("score_gap", "--")
        min_gap = "10"
        if isinstance(bias, dict):
            min_gap = str(bias.get("min_gap", "10"))
        self.card_gap.set_value(f"{self._compact_number(gap)}")
        self.card_gap.set_detail(f"tối thiểu {min_gap}")

        rr = self.row.get("risk_reward") or "--"
        self.card_rr.set_value(str(rr))
        eff_rr = self.row.get("expected_effective_rr")
        rr_detail = f"~{eff_rr:.1f}" if eff_rr is not None else ""
        self.card_rr.set_detail(rr_detail)

        # Row 2: context
        entry_raw = str(self.row.get("entry_status") or "--")
        self.card_entry.set_value(self._entry_status_display(),
                                   accent="#22c55e" if "Đã xác nhận" in self._entry_status_display() else "#fbbf24")

        price_zone = str(self.row.get("price_vs_zone") or "").lower()
        zone_map = {"in_zone": "Trong vùng", "near_zone": "Gần vùng", "far": "Còn xa", "unknown": "Chưa rõ"}
        pz_val = zone_map.get(price_zone)
        if not pz_val:
            pz_val = "Chưa rõ" if price_zone in ("unknown", "--", "") else price_zone.title()
        self.card_position.set_value(pz_val)

        m15_raw = self._m15_text().lower()
        m15_map = {"strict": "Chặt chẽ", "loose": "Lỏng lẻo", "chưa xác nhận": "Chưa xác nhận"}
        m15_val = m15_map.get(m15_raw, m15_raw.title())
        m15_accent = "#10b981" if m15_raw == "strict" else ("#f59e0b" if m15_raw == "loose" else "#e11d48")
        self.card_m15.set_value(m15_val, accent=m15_accent)

        regime = str(self.row.get("market_regime") or "--").lower()
        regime_map = {"trend_up": "Tăng", "trend_down": "Giảm", "range": "Đi ngang",
                       "volatile": "Biến động", "unknown": "Chưa rõ", "--": "--"}
        self.card_regime.set_value(regime_map.get(regime, regime.title()))

        perm = str(self.row.get("trade_permission") or "--").lower()
        perm_map = {"allowed": "Được phép", "caution": "Cẩn trọng", "blocked": "Bị chặn", "--": "--"}
        perm_accent = {"allowed": "#10b981", "caution": "#f59e0b", "blocked": "#e11d48"}.get(perm, "#94a3b8")
        self.card_permission.set_value(perm_map.get(perm, perm.title()), accent=perm_accent)

        # Row 3: removed-from-overview columns now shown here
        macro_val = self.row.get("macro_score", "--")
        try:
            macro_num = int(macro_val)
        except (TypeError, ValueError):
            macro_num = 15
        conf = float(self.row.get("macro_confidence", 1.0))
        quality_dot = "●" if conf >= 0.8 else ("○" if conf >= 0.5 else "◌")
        macro_accent = "#10b981" if macro_num >= 22 else ("#f59e0b" if macro_num >= 15 else "#94a3b8")
        self.card_macro_score.set_value(f"{quality_dot} {macro_num}/30", accent=macro_accent)
        macro_detail = self.row.get("macro_bias", "--")
        if isinstance(macro_detail, str):
            self.card_macro_score.set_detail(macro_detail.title())

        group_raw = str(self.row.get("scanner_group") or "--")
        group_map = {"ready_now": "Sẵn sàng ngay", "waiting_confirmation": "Chờ xác nhận",
                     "watch_zone": "Theo dõi", "blocked": "Bị chặn"}
        group_accent = {"ready_now": "#10b981", "waiting_confirmation": "#f59e0b",
                       "watch_zone": "#f59e0b", "blocked": "#e11d48"}.get(group_raw, "#94a3b8")
        self.card_scanner_group.set_value(group_map.get(group_raw, group_raw), accent=group_accent)

        sample = self.row.get("journal_sample_size", 0)
        try:
            sample_num = int(sample)
        except (TypeError, ValueError):
            sample_num = 0
        self.card_journal_sample.set_value(str(sample_num))

        exp_r = self.row.get("journal_expectancy_r")
        try:
            exp_num = float(exp_r)
            exp_text = f"{exp_num:.2f}R"
            exp_accent = "#10b981" if exp_num > 0 else ("#e11d48" if exp_num < 0 else "#94a3b8")
        except (TypeError, ValueError):
            exp_text = "--"
            exp_accent = "#94a3b8"
        self.card_journal_expectancy.set_value(exp_text, accent=exp_accent)

        # Entry checklist
        self._refresh_entry_checklist()

    def _refresh_entry_checklist(self) -> None:
        """Show what conditions are met / missing for trade entry."""
        if not self.row:
            return

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        bg = "#ffffff" if light else "#1a1f2e"
        border = "#d1d5db" if light else "#2b3545"
        text_color = "#111827" if light else "#cbd5e1"
        green = "#10b981"
        red = "#e11d48"
        yellow = "#f59e0b"
        gray = "#94a3b8"

        items = self._build_entry_checklist()

        # Clear existing
        while self.entry_checklist_layout.count():
            child = self.entry_checklist_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Title
        title = QLabel("🔍 Điều kiện vào lệnh")
        title.setStyleSheet(f"font-weight: bold; font-size: 12px; color: {text_color}; margin-bottom: 2px;")
        self.entry_checklist_layout.addWidget(title)

        self.entry_checklist_card.setStyleSheet(
            f"QFrame#EntryChecklistCard {{ background: {bg}; border: 1px solid {border}; border-radius: 6px; }}"
        )

        for item in items:
            icon = "✅" if item["pass"] else "❌"
            color = green if item["pass"] else red
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 1, 0, 1)
            row_l.setSpacing(6)
            row_l.setAlignment(Qt.AlignmentFlag.AlignTop)
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet(f"font-size: 11px;")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
            row_l.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)
            text_lbl = QLabel(item["label"])
            text_lbl.setStyleSheet(f"font-size: 11px; color: {color};")
            text_lbl.setWordWrap(True)
            row_l.addWidget(text_lbl, 1)
            self.entry_checklist_layout.addWidget(row_w)

    def _build_entry_checklist(self) -> list[dict]:
        """Build a list of {pass: bool, label: str} for entry conditions."""
        if not self.row:
            return []

        items = []
        best = int(self.row.get("best_score", 0) or 0)
        gap = int(self.row.get("score_gap", 0) or 0)
        perm = str(self.row.get("trade_permission", ""))
        entry = str(self.row.get("entry_status", ""))
        m15 = str(self.row.get("m15_quality", "")).lower()
        price_zone = str(self.row.get("price_vs_zone", ""))
        rr = str(self.row.get("risk_reward", ""))
        min_score = int(self.row.get("min_score", 65) or 65)
        analysis = self.row.get("analysis_result", {}) if isinstance(self.row.get("analysis_result"), dict) else {}
        gate = analysis.get("trade_gate", {}) if isinstance(analysis, dict) else {}
        gate_allowed = bool(gate.get("allowed", True)) if isinstance(gate, dict) else True

        # 1. Trade Permission
        items.append({
            "pass": perm == "allowed",
            "label": f"Quyền giao dịch: {perm} (điểm {best}/{min_score})" if perm != "allowed"
                     else f"Quyền giao dịch: allowed (điểm {best} >= {min_score})"
        })

        # 2. Gate
        gate_reasons = gate.get("reasons", []) if isinstance(gate, dict) else []
        gate_text = "; ".join(gate_reasons[:2]) if gate_reasons else "không bị gate chặn"
        items.append({
            "pass": gate_allowed,
            "label": f"Gate: {'PASS' if gate_allowed else 'BLOCKED'} — {gate_text}"
        })

        # 3. Score Gap
        items.append({
            "pass": gap >= 10,
            "label": f"Chênh lệch Buy/Sell: {gap}/10 — {'rõ hướng' if gap >= 10 else 'chưa rõ hướng'}"
        })

        # 4. Entry confirmed
        entry_ok = entry in ("confirmed_entry", "ready", "ready_to_trade")
        entry_map = {
            "confirmed_entry": "đã xác nhận",
            "watch_zone": "giá chưa vào zone hoặc chưa có nến xác nhận",
            "waiting_confirmation": "chờ xác nhận H1/M15",
            "no_setup": "chưa có setup",
        }
        entry_label = entry_map.get(entry, entry)
        items.append({
            "pass": entry_ok,
            "label": f"Xác nhận entry: {entry_label}"
        })

        # 5. Price in zone
        in_zone = price_zone == "in_zone"
        zone_map = {"in_zone": "đang trong zone", "near_zone": "gần zone", "far": "còn xa zone"}
        items.append({
            "pass": in_zone,
            "label": f"Vị trí giá: {zone_map.get(price_zone, price_zone)}"
        })

        # 6. M15
        m15_ok = m15 in ("strict",)
        m15_label = {"strict": "chặt chẽ", "loose": "lỏng lẻo", "none": "chưa xác nhận", "": "chưa có dữ liệu"}
        items.append({
            "pass": m15_ok,
            "label": f"M15: {m15_label.get(m15, m15)}"
        })

        # 7. R:R
        rr_val = 0.0
        try:
            if ":" in str(rr):
                rr_val = float(str(rr).split(":")[1])
            else:
                rr_val = float(rr)
        except (ValueError, TypeError):
            pass
        rr_ok = rr_val >= 1.5
        items.append({
            "pass": rr_ok,
            "label": f"R:R: {rr} — {'đủ' if rr_ok else 'dưới 1.5:1'}"
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
            return "🟢 Mạnh"
        if sc >= 65:
            return "🟠 Khá"
        if sc >= 50:
            return "🟡 TB"
        return "🔴 Yếu"

    def _fill_pills(self, layout: QVBoxLayout, items: list[tuple[str, str]], fallback_state: str) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
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
        if not self.row.get("risk_reward"):
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
        zones = self.row.get("entry_zone") or self.row.get("entry_zones") if self.row else None
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
            self.diag_text.setHtml("<p style='color:#94a3b8;'>Chọn một dòng trong bảng quét để xem chẩn đoán.</p>")
            return
        analysis = self.row.get("analysis_result")
        if not isinstance(analysis, dict):
            self.diag_text.setHtml("<p style='color:#94a3b8;'>Không có dữ liệu phân tích để hiển thị chẩn đoán.</p>")
            return

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        parts: list[str] = []
        parts.append(self._diag_score_breakdown_html(analysis, light=light))
        parts.append(self._diag_gate_html(analysis, light=light))
        parts.append(self._diag_checklist_html(analysis, light=light))
        parts.append(self._diag_pipeline_steps_html(analysis, light=light))
        parts.append(self._diag_final_score_html(analysis, light=light))
        self.diag_text.setHtml("\n".join(parts))

    # -- AI Setup Audit ----------------------------------------------------

    def _refresh_ai_audit(self) -> None:
        if not hasattr(self, "audit_text"):
            return
        if not self.row:
            self.audit_text.setHtml("<p style='color:#94a3b8;'>Chọn một dòng trong bảng quét để xem AI kiểm định.</p>")
            if getattr(self, "audit_btn", None):
                self.audit_btn.setEnabled(False)
            return
        if getattr(self, "audit_btn", None):
            self.audit_btn.setEnabled(True)
        audit = self.row.get("ai_setup_audit")
        if not isinstance(audit, dict) or not audit:
            self.audit_text.setHtml(
                "<p style='color:#94a3b8;'>Chưa có kết quả kiểm định AI. Bấm nút <b>Chạy kiểm định AI</b> để AI phân tích setup này.</p>"
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
            f"<h2 style='color:{title_color};margin:0 0 4px;font-size:16px;'>AI Setup Auditor</h2>",
            f"<p style='color:{desc_color};font-size:11px;margin:0 0 12px;'>"
            "AI chỉ kiểm định setup rule engine đã tạo. Phần này không tự thay đổi quyết định, gate hoặc auto trade."
            "</p>",
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:14px;background:{bg_color};border-radius:6px;'>",
            "<tr>",
            f"<td style='padding:10px 12px;color:{text_color};width:120px;'>Kết luận</td>",
            f"<td style='padding:10px 12px;color:{color};font-weight:800;font-size:15px;'>{label}</td>",
            f"<td style='padding:10px 12px;color:{text_color};width:90px;'>Tin cậy</td>",
            f"<td style='padding:10px 12px;color:{value_color};font-weight:700;'>{confidence}/100</td>",
            f"<td style='padding:10px 12px;color:{text_color};width:110px;'>Chất lượng plan</td>",
            f"<td style='padding:10px 12px;color:{value_color};font-weight:700;'>{quality}/100</td>",
            "</tr>",
            "</table>",
        ]
        if error:
            rows.append(
                f"<div style='color:{error_text};background:{error_bg};border:1px solid {error_border};"
                f"border-radius:6px;padding:10px 12px;margin-bottom:12px;'>AI auditor lỗi: {error}</div>"
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
            f"<h3 style='color:{color};margin:16px 0 6px;font-size:14px;'>{escape(title)}</h3>"
            f"<div style='color:{text_color};background:{bg_color};border:1px solid {border_color};"
            f"border-radius:6px;padding:10px 12px;margin-bottom:8px;'>{body}</div>"
        )

    def _audit_list_block(self, title: str, values: object, color: str, light: bool = False) -> str:
        items = values if isinstance(values, list) else []
        muted_color = "#736B60" if light else "#94a3b8"
        text_color = "#111827" if light else "#e2e8f0"
        bg_color = "#ffffff" if light else "#111827"
        border_color = "#D6D2C8" if light else "#334155"

        if not items:
            body = f"<span style='color:{muted_color};'>Không có mục đáng chú ý.</span>"
        else:
            body = "<ul style='margin:0;padding-left:18px;'>" + "".join(
                f"<li style='margin:4px 0;color:{text_color};'>{escape(str(item))}</li>"
                for item in items
                if str(item).strip()
            ) + "</ul>"
        return (
            f"<h3 style='color:{color};margin:16px 0 6px;font-size:14px;'>{escape(title)}</h3>"
            f"<div style='background:{bg_color};border:1px solid {border_color};border-radius:6px;"
            f"padding:10px 12px;margin-bottom:8px;'>{body}</div>"
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
            f"<h2 style='color:{title_color};margin:0 0 4px;font-size:16px;'>Phân rã điểm số</h2>",
            f"<p style='color:{desc_color};font-size:11px;margin:0 0 12px;'>"
            "Hệ thống chấm điểm 6 thành phần cho mỗi hướng MUA và BÁN. "
            "<b>Xu hướng</b> (EMA50/200, cấu trúc HH/HL) · "
            "<b>Động lượng</b> (RSI, MACD) · "
            "<b>Vị trí</b> (gần hỗ trợ/kháng cự) · "
            "<b>SMC</b> (BOS, CHOCH, vùng cung/cầu) · "
            "<b>Rủi ro</b> (ATR, spread, tin tức) · "
            "<b>Vĩ mô</b> (lãi suất, DXY, VIX, US10Y). "
            "Tổng 0-100; &ge;80 Mạnh, &ge;65 Khá, &ge;50 Trung bình, &lt;50 Yếu."
            "</p>",
            "<table style='width:100%;border-collapse:collapse;margin-bottom:16px;'>",
            "<tr>",
            f"<th style='text-align:left;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};' title='Thành phần được chấm điểm'>Thành phần</th>",
            f"<th style='text-align:center;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:55px;' title='Điểm tối đa của thành phần này'>Max</th>",
            f"<th style='text-align:center;padding:8px 10px;border-bottom:2px solid #ea580c;color:#ea580c;width:55px;' title='Điểm kịch bản MUA'>MUA</th>",
            f"<th style='text-align:center;padding:8px 10px;border-bottom:2px solid #f43f5e;color:#f43f5e;width:55px;' title='Điểm kịch bản BÁN'>BÁN</th>",
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
                f"<td style='padding:6px 10px;border-bottom:1px solid {row_border_color};color:{text_color};' title='{tooltip}'>{label}</td>"
                f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};'>{eff_max}</td>"
                f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{_color(int(bv), eff_max)};font-weight:700;'>{int(bv)}</td>"
                f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{_color(int(sv), eff_max)};font-weight:700;'>{int(sv)}</td>"
                f"</tr>"
            )

        rows.append(
            f"<tr style='border-top:2px solid {border_color};'>"
            f"<td style='padding:8px 10px;color:{label_color};font-weight:700;' title='Tổng điểm tín hiệu sau khi chuẩn hóa (0-100)'>TỔNG</td>"
            f"<td style='text-align:center;padding:8px 10px;color:{desc_color};'>100</td>"
            f"<td style='text-align:center;padding:8px 10px;color:#ea580c;font-weight:700;font-size:15px;'>{buy_total}</td>"
            f"<td style='text-align:center;padding:8px 10px;color:#f43f5e;font-weight:700;font-size:15px;'>{sell_total}</td>"
            f"</tr>"
        )
        rows.append("</table>")

        # Rating + modifiers — use table for reliable rendering
        rows.append(
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:14px;font-size:12px;background:{bg_color};border-radius:6px;'>"
            "<tr>"
            f"<td style='padding:6px 12px;color:{muted_color};width:110px;'>Đánh giá MUA</td>"
            f"<td style='padding:6px 12px;color:{text_color};'>{_rating(buy_total)}</td>"
            f"<td style='padding:6px 12px;color:{muted_color};width:110px;'>Tương quan MUA</td>"
            f"<td style='padding:6px 12px;color:{text_color};'><b>{buy_corr:+.0f}</b></td>"
            "</tr>"
            "<tr>"
            f"<td style='padding:6px 12px;color:{muted_color};'>Đánh giá BÁN</td>"
            f"<td style='padding:6px 12px;color:{text_color};'>{_rating(sell_total)}</td>"
            f"<td style='padding:6px 12px;color:{muted_color};width:110px;'>Tương quan BÁN</td>"
            f"<td style='padding:6px 12px;color:{text_color};'><b>{sell_corr:+.0f}</b></td>"
            "</tr>"
        )

        if buy_macro_status or sell_macro_status:
            rows.append(
                "<tr>"
                f"<td style='padding:6px 12px;color:{muted_color};'>Vĩ mô MUA</td>"
                f"<td style='padding:6px 12px;color:{text_color};'><b>{buy_macro_status or 'trung lập'}</b></td>"
                f"<td style='padding:6px 12px;color:{muted_color};'>Vĩ mô BÁN</td>"
                f"<td style='padding:6px 12px;color:{text_color};'><b>{sell_macro_status or 'trung lập'}</b></td>"
                "</tr>"
            )
        rows.append(
            "<tr>"
            f"<td style='padding:6px 12px;color:{muted_color};'>Phạt MUA</td>"
            f"<td style='padding:6px 12px;color:{desc_color};'>{buy_penalty}</td>"
            f"<td style='padding:6px 12px;color:{muted_color};'>Phạt BÁN</td>"
            f"<td style='padding:6px 12px;color:{desc_color};'>{sell_penalty}</td>"
            "</tr>"
        )
        rows.append(
            "<tr>"
            f"<td style='padding:6px 12px;color:{muted_color};'>Lý do MUA</td>"
            f"<td style='padding:6px 12px;color:{desc_color};'>{buy_reason}</td>"
            f"<td style='padding:6px 12px;color:{muted_color};'>Lý do BÁN</td>"
            f"<td style='padding:6px 12px;color:{desc_color};'>{sell_reason}</td>"
            "</tr>"
        )

        # SMC reason
        buy_smc = buy.get("smc_reason", "")
        sell_smc = sell.get("smc_reason", "")
        if buy_smc or sell_smc:
            rows.append(
                "<tr>"
                f"<td style='padding:6px 12px;color:{muted_color};'>SMC MUA</td>"
                f"<td style='padding:6px 12px;color:{desc_color};'>{buy_smc or '--'}</td>"
                f"<td style='padding:6px 12px;color:{muted_color};'>SMC BÁN</td>"
                f"<td style='padding:6px 12px;color:{desc_color};'>{sell_smc or '--'}</td>"
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
            f"<h2 style='color:{title_color};margin:20px 0 4px;font-size:16px;'>Gate kiểm tra</h2>",
            f"<p style='color:{desc_color};font-size:11px;margin:0 0 12px;'>"
            "Gate là các lớp kiểm tra trước khi cho phép vào lệnh. "
            "Mỗi gate có thể <b style='color:#22c55e;'>Cho qua</b>, "
            "<b style='color:#fbbf24;'>Cảnh báo</b> (giới hạn mức quyết định), "
            "hoặc <b style='color:#ef4444;'>Chặn</b> (cấm vào lệnh). "
            "Thứ tự ưu tiên: CHẶN > CẢNH BÁO > Pass."
            "</p>",
            "<table style='width:100%;border-collapse:collapse;margin-bottom:12px;'>",
            "<tr>",
            f"<th style='text-align:left;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:110px;'>Gate</th>",
            f"<th style='text-align:center;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:70px;'>Kết quả</th>",
            f"<th style='text-align:left;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};'>Ý nghĩa / Chi tiết</th>",
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
                f"<td style='padding:6px 10px;border-bottom:1px solid {row_border_color};color:{text_color};' title='{g_explain}'>{g_label}</td>"
                f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{color};font-weight:700;'>{icon} {text}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid {row_border_color};color:{muted_color};font-size:12px;'>{g_explain} &mdash; {g_detail}</td>"
                f"</tr>"
            )
        rows.append("</table>")

        # Summary
        allowed = gate.get("allowed", True)
        cap = gate.get("decision_cap") or permission.get("decision_cap") or "không"
        reasons = gate.get("reasons", []) or []
        perm_status = permission.get("status", "?")
        perm_text = {"allowed": "Được phép", "caution": "Cẩn trọng", "blocked": "Bị chặn"}.get(perm_status, perm_status)

        if allowed:
            summary_color = "#22c55e"
            summary_text = f"CHO PHÉP (mức: {cap})"
        elif not allowed:
            summary_color = "#ef4444"
            summary_text = f"BỊ CHẶN (mức: {cap})"
        else:
            summary_color = "#fbbf24"
            summary_text = f"CẢNH BÁO (mức: {cap})"

        rows.append(
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:8px;font-size:13px;"
            f"background:{bg_color};border-radius:6px;'>"
            f"<tr>"
            f"<td style='padding:8px 12px;color:{muted_color};width:130px;'>KẾT LUẬN GATE</td>"
            f"<td style='padding:8px 12px;color:{summary_color};font-weight:700;'>{summary_text}</td>"
            f"<td style='padding:8px 12px;color:{muted_color};width:60px;'>Quyền</td>"
            f"<td style='padding:8px 12px;color:{text_color};'>{perm_text}</td>"
            f"</tr>"
            f"</table>"
        )
        if reasons:
            rows.append(
                f"<div style='font-size:12px;color:#ef4444;padding:4px 12px;margin-bottom:8px;'>"
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
             "detail": "bảo vệ OK"},
            {"gate": "Journal", "status": "pass",
             "detail": "không vấn đề"},
            {"gate": "M15", "status": _st(M15_NOT_CONFIRMED) if _st(M15_NOT_CONFIRMED) != "pass" else _st(M15_LOOSE_CONFIRMATION),
             "detail": f"M15={primary.get('m15_quality', '?')}"},
            {"gate": "ExpectedRR", "status": _st(EXPECTED_RR_TOO_LOW),
             "detail": f"R:R={primary.get('expected_effective_rr', '?')}"},
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
            f"<h2 style='color:{title_color};margin:20px 0 4px;font-size:16px;'>Điều kiện vào lệnh</h2>",
            f"<p style='color:{desc_color};font-size:11px;margin:0 0 12px;'>"
            "Các điều kiện cần đạt trước khi vào lệnh thật. "
            "<b style='color:#22c55e;'>✅ Đạt</b> = đã thỏa mãn. "
            "<b style='color:#fbbf24;'>⏳ Chờ</b> = cần theo dõi thêm, chưa nên vào lệnh vội."
            "</p>",
            "<table style='width:100%;border-collapse:collapse;margin-bottom:12px;'>",
            "<tr>",
            f"<th style='text-align:left;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:110px;'>Điều kiện</th>",
            f"<th style='text-align:center;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:70px;'>Trạng thái</th>",
            f"<th style='text-align:left;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:160px;'>Giá trị</th>",
            f"<th style='text-align:left;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};'>Ghi chú</th>",
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
                f"<td style='padding:6px 10px;border-bottom:1px solid {row_border_color};color:{text_color};'>{label}</td>"
                f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{color};font-weight:700;'>{icon} {status_text}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid {row_border_color};color:{muted_color};font-size:12px;'>{value}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};font-size:12px;'>{note}</td>"
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
            f"<h2 style='color:{title_color};margin:20px 0 4px;font-size:16px;'>Pipeline từng bước</h2>",
            f"<p style='color:{desc_color};font-size:11px;margin:0 0 12px;'>"
            "Quy trình phân tích tuần tự 7 bước. Nếu một bước <b style='color:#ef4444;'>thất bại</b>, "
            "các bước sau không chạy. Bước <b style='color:#fbbf24;'>cảnh báo</b> vẫn tiếp tục "
            "nhưng có thể ảnh hưởng kết quả cuối cùng."
            "</p>",
            "<table style='width:100%;border-collapse:collapse;margin-bottom:12px;'>",
            "<tr>",
            f"<th style='text-align:left;padding:6px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:120px;'>Bước</th>",
            f"<th style='text-align:center;padding:6px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:70px;'>Kết quả</th>",
            f"<th style='text-align:left;padding:6px 10px;border-bottom:2px solid {border_color};color:{muted_color};'>Diễn giải / Tóm tắt</th>",
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
                f"<td style='padding:5px 10px;border-bottom:1px solid {row_border_color};color:{text_color};' title='{explain}'>{label}</td>"
                f"<td style='text-align:center;padding:5px 10px;border-bottom:1px solid {row_border_color};color:{color};font-weight:700;'>{icon} {text}</td>"
                f"<td style='padding:5px 10px;border-bottom:1px solid {row_border_color};color:{muted_color};font-size:12px;'>{summary}</td>"
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
            f"<h2 style='color:{title_color};margin:20px 0 4px;font-size:16px;'>Điểm cuối cùng</h2>",
            f"<p style='color:{desc_color};font-size:11px;margin:0 0 12px;'>"
            "Điểm tổng hợp từ 3 nguồn: <b>Tín hiệu</b> (điểm kỹ thuật/SMC/vĩ mô), "
            "<b>Bằng chứng nhật ký</b> (hiệu suất lịch sử của setup tương tự), "
            "<b>Chất lượng thực thi</b> (tỷ lệ vào lệnh thành công trước đây). "
            "Điểm này quyết định hành động cuối cùng."
            "</p>",
            "<table style='width:100%;border-collapse:collapse;margin-bottom:12px;'>",
            "<tr>",
            f"<th style='text-align:left;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};'>Thành phần</th>",
            f"<th style='text-align:center;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:60px;' title='Trọng lượng trong công thức'>TL</th>",
            f"<th style='text-align:center;padding:8px 10px;border-bottom:2px solid {border_color};color:{muted_color};width:60px;' title='Điểm thành phần'>Điểm</th>",
            "</tr>",
            f"<tr><td style='padding:6px 10px;border-bottom:1px solid {row_border_color};color:{text_color};' title='Điểm tín hiệu từ bước chấm điểm (0-100)'>Tín hiệu</td>"
            f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};'>65%</td>"
            f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-weight:700;'>{signal_s}</td></tr>",
            f"<tr><td style='padding:6px 10px;border-bottom:1px solid {row_border_color};color:{text_color};' title='Điểm từ nhật ký giao dịch cũ (setup tương tự từng thắng không)'>Bằng chứng (NK)</td>"
            f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};'>20%</td>"
            f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-weight:700;'>{evidence_s}</td></tr>",
            f"<tr><td style='padding:6px 10px;border-bottom:1px solid {row_border_color};color:{text_color};' title='Điểm chất lượng thực thi lệnh (tỷ lệ khớp lệnh thành công)'>Chất lượng thực thi</td>"
            f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{desc_color};'>15%</td>"
            f"<td style='text-align:center;padding:6px 10px;border-bottom:1px solid {row_border_color};color:{text_color};font-weight:700;'>{exec_s}</td></tr>",
            f"<tr style='border-top:2px solid {border_color};'>"
            f"<td style='padding:8px 10px;color:{label_color};font-weight:700;' title='Điểm cuối cùng = Tín hiệu×0.65 + Bằng chứng×0.20 + Thực thi×0.15'>ĐIỂM CUỐI</td>"
            f"<td style='text-align:center;padding:8px 10px;color:{desc_color};'>100%</td>"
            f"<td style='text-align:center;padding:8px 10px;color:#22c55e;font-weight:700;font-size:15px;'>{final_score}</td></tr>",
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
            f"<table style='width:100%;border-collapse:collapse;margin-bottom:12px;font-size:12px;background:{bg_color};border-radius:6px;'>"
            "<tr>"
            f"<td style='padding:6px 12px;color:{muted_color};width:110px;'>Quyết định</td>"
            f"<td style='padding:6px 12px;color:{text_color};'><b>{dec_decision}</b>"
            + (f" <span style='color:{desc_color};'>({dec_explain})</span>" if dec_explain else "")
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
