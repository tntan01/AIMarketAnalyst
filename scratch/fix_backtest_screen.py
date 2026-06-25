# -*- coding: utf-8 -*-
import os
import py_compile

def main():
    path = 'ui/screens/backtest_screen.py'
    print("Reading file...")
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update _settings_card to store self.settings_frame
    old_settings_init = """    def _settings_card(self) -> QFrame:
        frame = card(None)
        frame.setStyleSheet(self._backtest_form_stylesheet())"""
    
    new_settings_init = """    def _settings_card(self) -> QFrame:
        frame = card(None)
        self.settings_frame = frame
        self.settings_frame.setStyleSheet(self._backtest_form_stylesheet())"""

    if old_settings_init in content:
        content = content.replace(old_settings_init, new_settings_init)
        print("1. Settings card init updated.")
    else:
        print("Error: settings card init not found!")

    # 2. Update progress bar style initialization (remove hardcoded style from _settings_card)
    old_progress_style = """        self.progress = QProgressBar()
        self.progress.setObjectName("BacktestProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        self.progress.setStyleSheet(
            "QProgressBar#BacktestProgress {"
            "background: #0f172a;"
            "border: 1px solid #334155;"
            "border-radius: 5px;"
            "}"
            "QProgressBar#BacktestProgress::chunk {"
            "background: #ea580c;"
            "border-radius: 4px;"
            "}"
        )"""

    new_progress_style = """        self.progress = QProgressBar()
        self.progress.setObjectName("BacktestProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)"""

    if old_progress_style in content:
        content = content.replace(old_progress_style, new_progress_style)
        print("2. Progress bar style initialization removed.")
    else:
        print("Error: progress bar style initialization not found!")

    # 3. Update _build_ui to call self._refresh_theme_styles()
    old_build_ui = """        root.addWidget(self._settings_card())
        root.addWidget(self._trades_card(), 1)"""

    new_build_ui = """        root.addWidget(self._settings_card())
        root.addWidget(self._trades_card(), 1)
        self._refresh_theme_styles()"""

    if old_build_ui in content:
        content = content.replace(old_build_ui, new_build_ui)
        print("3. Build UI theme refresh added.")
    else:
        print("Error: Build UI not found!")

    # 4. Update _set_trades to use self.trades and call self._refresh_trade_table_style()
    old_set_trades = """    def _set_trades(self, trades: list[dict[str, object]]) -> None:
        self.table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            result = str(trade.get("result", "")).lower()
            if result == "win":
                bg = "#064e3b"  # dark green
            elif result == "loss":
                bg = "#881337"  # dark red
            elif result == "breakeven":
                bg = "#1e293b"  # dark gray
            else:
                bg = "#1a1f2e"  # default dark
            for col, (key, _label) in enumerate(self.TRADE_COLUMNS):
                if key == "stt":
                    value = str(row + 1)
                else:
                    value = self._format_trade_value(key, trade.get(key, "--"))
                item = QTableWidgetItem(value)
                item.setBackground(Qt.GlobalColor.transparent)
                if key in {"stt", "result_r", "final_score", "signal_score", "selected_zone_score"}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
            # Apply row background to all cells
            from PyQt6.QtGui import QColor
            row_color = QColor(bg)
            for col in range(len(self.TRADE_COLUMNS)):
                cell = self.table.item(row, col)
                if cell:
                    cell.setBackground(row_color)
        self._apply_trade_table_layout()"""

    new_set_trades = """    def _set_trades(self, trades: list[dict[str, object]]) -> None:
        self.trades = trades
        self.table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            for col, (key, _label) in enumerate(self.TRADE_COLUMNS):
                if key == "stt":
                    value = str(row + 1)
                else:
                    value = self._format_trade_value(key, trade.get(key, "--"))
                item = QTableWidgetItem(value)
                item.setBackground(Qt.GlobalColor.transparent)
                if key in {"stt", "result_r", "final_score", "signal_score", "selected_zone_score"}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
        self._refresh_trade_table_style()
        self._apply_trade_table_layout()"""

    if old_set_trades in content:
        content = content.replace(old_set_trades, new_set_trades)
        print("4. Set trades color setting replaced with helper call.")
    else:
        print("Error: _set_trades not found!")

    # 5. Replace _update_verdict with a theme-aware version
    old_verdict = """    def _update_verdict(self) -> None:
        \"\"\"Show a compact verdict badge inline in the header row.\"\"\"
        if not self.result:
            self.verdict_banner.hide()
            return
        summary = self.result.get("summary", {}) if isinstance(self.result.get("summary"), dict) else {}

        total = int(summary.get("total_trades", 0) or 0)
        wr = float(summary.get("win_rate", 0) or 0)
        exp_r = float(summary.get("expectancy_r", 0) or 0)
        pf = float(summary.get("profit_factor", 0) or 0)
        dd = float(summary.get("max_drawdown_r", 0) or 0)
        total_r = float(summary.get("total_r", 0) or 0)

        has_edge = exp_r > 0.10
        good_pf = pf > 1.2
        positive_total = total_r > 0

        if total == 0:
            icon, accent, bg = "⚪", "#64748b", "#1e293b"
            line = "Chưa có lệnh nào"
        elif has_edge and good_pf:
            icon, accent, bg = "🟢", "#10b981", "#064e3b"
            line = f"CÓ LỢI THẾ · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
        elif has_edge and not good_pf:
            icon, accent, bg = "🟡", "#f59e0b", "#78350f"
            line = f"LỢI THẾ YẾU · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
        elif positive_total and not has_edge:
            icon, accent, bg = "🟠", "#fb923c", "#78350f"
            line = f"CHƯA RÕ · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
        else:
            icon, accent, bg = "🔴", "#e11d48", "#881337"
            line = f"HỆ THỐNG ÂM · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"

        self.verdict_banner.setText(
            f"<span style='display:inline-block;padding:3px 14px;border-radius:4px;background:{bg};"
            f"font-size:13px;white-space:nowrap;'>"
            f"<b style='color:{accent};'>{icon} {line}</b>"
            f"<span style='color:#64748b;'>&nbsp;&nbsp;│&nbsp;&nbsp;</span>"
            f"<span style='color:#cbd5e1;'>"
            f"{total} lệnh &nbsp;·&nbsp; TL thắng {wr:.1f}% &nbsp;·&nbsp; DD {dd:.1f}R"
            f"</span>"
            f"</span>"
        )
        self.verdict_banner.show()"""

    new_verdict = """    def _update_verdict(self) -> None:
        \"\"\"Show a compact verdict badge inline in the header row.\"\"\"
        if not self.result:
            self.verdict_banner.hide()
            return
        summary = self.result.get("summary", {}) if isinstance(self.result.get("summary"), dict) else {}

        total = int(summary.get("total_trades", 0) or 0)
        wr = float(summary.get("win_rate", 0) or 0)
        exp_r = float(summary.get("expectancy_r", 0) or 0)
        pf = float(summary.get("profit_factor", 0) or 0)
        dd = float(summary.get("max_drawdown_r", 0) or 0)
        total_r = float(summary.get("total_r", 0) or 0)

        has_edge = exp_r > 0.10
        good_pf = pf > 1.2
        positive_total = total_r > 0

        light = self._is_light_theme()

        if light:
            if total == 0:
                icon, accent, bg, border, separator, text = "⚪", "#475569", "#f1f5f9", "#cbd5e1", "#cbd5e1", "#334155"
                line = "Chưa có lệnh nào"
            elif has_edge and good_pf:
                icon, accent, bg, border, separator, text = "🟢", "#047857", "#d1fae5", "#a7f3d0", "#a7f3d0", "#065f46"
                line = f"CÓ LỢI THẾ · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif has_edge and not good_pf:
                icon, accent, bg, border, separator, text = "🟡", "#b45309", "#fef3c7", "#fde68a", "#fde68a", "#78350f"
                line = f"LỢI THẾ YẾU · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif positive_total and not has_edge:
                icon, accent, bg, border, separator, text = "🟠", "#ea580c", "#ffedd5", "#fed7aa", "#fed7aa", "#7c2d12"
                line = f"CHƯA RÕ · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            else:
                icon, accent, bg, border, separator, text = "🔴", "#be123c", "#ffe4e6", "#fecdd3", "#fecdd3", "#9f1239"
                line = f"HỆ THỐNG ÂM · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
        else:
            if total == 0:
                icon, accent, bg, border, separator, text = "⚪", "#94a3b8", "#0f172a", "#1e293b", "#334155", "#cbd5e1"
                line = "Chưa có lệnh nào"
            elif has_edge and good_pf:
                icon, accent, bg, border, separator, text = "🟢", "#10b981", "#064e3b", "#065f46", "#334155", "#cbd5e1"
                line = f"CÓ LỢI THẾ · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif has_edge and not good_pf:
                icon, accent, bg, border, separator, text = "🟡", "#f59e0b", "#451a03", "#78350f", "#334155", "#cbd5e1"
                line = f"LỢI THẾ YẾU · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif positive_total and not has_edge:
                icon, accent, bg, border, separator, text = "🟠", "#fb923c", "#431407", "#7c2d12", "#334155", "#cbd5e1"
                line = f"CHƯA RÕ · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            else:
                icon, accent, bg, border, separator, text = "🔴", "#e11d48", "#4c0519", "#881337", "#334155", "#cbd5e1"
                line = f"HỆ THỐNG ÂM · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"

        self.verdict_banner.setText(
            f"<span style='display:inline-block;padding:4px 12px;border-radius:6px;background:{bg};"
            f"border: 1px solid {border};"
            f"font-size:12px;font-family:-apple-system,Segoe UI,sans-serif;white-space:nowrap;'>"
            f"<b style='color:{accent};'>{icon} {line}</b>"
            f"<span style='color:{separator};'>&nbsp;&nbsp;│&nbsp;&nbsp;</span>"
            f"<span style='color:{text};font-weight:500;'>"
            f"{total} lệnh &nbsp;·&nbsp; TL thắng {wr:.1f}% &nbsp;·&nbsp; DD {dd:.1f}R"
            f"</span>"
            f"</span>"
        )
        self.verdict_banner.show()"""

    if old_verdict in content:
        content = content.replace(old_verdict, new_verdict)
        print("5. Verdict banner updated successfully.")
    else:
        print("Error: _update_verdict block not found!")

    # 6. Replace _backtest_form_stylesheet with a dynamic method
    old_css = """    @staticmethod
    def _backtest_form_stylesheet() -> str:
        return \"\"\"
        QLabel#BacktestSectionTitle {
            color: #f8fafc;
            font-size: 13px;
            font-weight: 800;
            padding-bottom: 2px;
            border-bottom: 1px solid #334155;
        }

        \"\"\""""

    new_css = """    def _backtest_form_stylesheet(self) -> str:
        light = self._is_light_theme()
        if light:
            color = "#111827"
            border = "#cbd5e1"
        else:
            color = "#f8fafc"
            border = "#334155"
            
        return f\"\"\"
        QLabel#BacktestSectionTitle {{
            color: {color};
            font-size: 13px;
            font-weight: 800;
            padding-bottom: 2px;
            border-bottom: 1px solid {border};
        }}
        \"\"\""""

    if old_css in content:
        content = content.replace(old_css, new_css)
        print("6. Form stylesheet updated successfully.")
    else:
        print("Error: _backtest_form_stylesheet block not found!")

    # 7. Update _analyze_loaded_result dialog styles and colors
    old_dialog_block = """            dlg = QDialog(self)
            dlg.setWindowTitle("Phân tích kết quả backtest")
            dlg.setMinimumSize(740, 560)
            dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(20, 18, 20, 16)
            text = QTextEdit()
            text.setReadOnly(True)
            text.setStyleSheet(
                "QTextEdit { background: #171c24; color: #e5e7eb; font-size: 13px; border: 1px solid #2b3545; border-radius: 6px; padding: 16px; }"
            )
            
            stats_html = self._generate_stats_html()
            ai_html = self._format_ai_to_html(response)
            
            final_html = (
                f"{stats_html}"
                f"<hr style='border: 0; border-top: 1px dashed #334155; margin: 24px 0;' />"
                f"<div style='font-family:-apple-system,Segoe UI,sans-serif;'>"
                f"<h2 style='color:#f59e0b; margin-bottom: 12px; font-size: 16px;'>🤖 AI NHẬN XÉT & ĐÁNH GIÁ</h2>"
                f"{ai_html}"
                f"</div>"
            )
            
            text.setHtml(final_html)"""

    new_dialog_block = """            try:
                light = (self.app.settings_service.load().display.theme == "light" 
                         if self.app else self.controller.settings_service.load().display.theme == "light")
            except Exception:
                light = False

            dlg = QDialog(self)
            dlg.setWindowTitle("Phân tích kết quả backtest")
            dlg.setMinimumSize(740, 560)
            if light:
                dlg.setStyleSheet("QDialog { background: #FAF9F5; }")
            else:
                dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(20, 18, 20, 16)
            text = QTextEdit()
            text.setReadOnly(True)
            if light:
                text.setStyleSheet(
                    "QTextEdit { background: #ffffff; color: #111827; font-size: 13px; border: 1px solid #D6D2C8; border-radius: 6px; padding: 16px; }"
                )
            else:
                text.setStyleSheet(
                    "QTextEdit { background: #171c24; color: #e5e7eb; font-size: 13px; border: 1px solid #2b3545; border-radius: 6px; padding: 16px; }"
                )
            
            stats_html = self._generate_stats_html()
            ai_html = self._format_ai_to_html(response)
            
            hr_color = "#cbd5e1" if light else "#334155"
            header_color = "#c2410c" if light else "#f59e0b"
            final_html = (
                f"{stats_html}"
                f"<hr style='border: 0; border-top: 1px dashed {hr_color}; margin: 24px 0;' />"
                f"<div style='font-family:-apple-system,Segoe UI,sans-serif;'>"
                f"<h2 style='color:{header_color}; margin-bottom: 12px; font-size: 16px;'>🤖 AI NHẬN XÉT & ĐÁNH GIÁ</h2>"
                f"{ai_html}"
                f"</div>"
            )
            
            text.setHtml(final_html)"""

    if old_dialog_block in content:
        content = content.replace(old_dialog_block, new_dialog_block)
        print("7. Analysis dialog style block updated.")
    else:
        print("Error: Analysis dialog style block not found!")

    # 8. Update _recommend_scanner_configs dialog styles and HTML
    old_recommend_block = """        # Build HTML table
        rows_html = ""
        for symbol, cfg in sorted(recs.items()):
            if cfg is None:
                rows_html += (
                    f"<tr>"
                    f"<td style='padding:6px 10px;color:#e2e8f0;'>{symbol}</td>"
                    f"<td colspan='4' style='padding:6px 10px;color:#64748b;'>Không đủ dữ liệu</td>"
                    f"</tr>"
                )
            else:
                evidence = cfg.get("_evidence", "")
                rows_html += (
                    f"<tr>"
                    f"<td style='padding:6px 10px;color:#e2e8f0;font-weight:700;'>{symbol}</td>"
                    f"<td style='padding:6px 10px;color:#10b981;'>{cfg['regime']}</td>"
                    f"<td style='padding:6px 10px;color:#ea580c;'>{cfg['side'].upper()}</td>"
                    f"<td style='padding:6px 10px;color:#f59e0b;'>≥ {cfg['min_score']}</td>"
                    f"<td style='padding:6px 10px;color:#fb923c;'>≥ {cfg['min_rr']}</td>"
                    f"<td style='padding:6px 10px;color:#94a3b8;font-size:12px;'>{evidence}</td>"
                    f"</tr>"
                )

        html = (
            "<div style='font-family:-apple-system,Segoe UI,sans-serif;font-size:13px;'>"
            "<h2 style='color:#f59e0b;margin:0 0 4px;font-size:16px;'>Đề xuất cấu hình Scanner từ Backtest</h2>"
            "<p style='color:#64748b;font-size:11px;margin:0 0 12px;'>"
            "Dựa trên kết quả backtest, hệ thống đề xuất cấu hình cho từng cặp. "
            "Cấu hình này có thể dùng trong Settings để tự động nâng setup đủ điều kiện."
            "</p>"
            "<table style='width:100%;border-collapse:collapse;margin-bottom:16px;'>"
            "<tr>"
            "<th style='text-align:left;padding:6px 10px;border-bottom:2px solid #334155;color:#94a3b8;'>Mã</th>"
            "<th style='text-align:left;padding:6px 10px;border-bottom:2px solid #334155;color:#94a3b8;'>Regime</th>"
            "<th style='text-align:left;padding:6px 10px;border-bottom:2px solid #334155;color:#94a3b8;'>Hướng</th>"
            "<th style='text-align:left;padding:6px 10px;border-bottom:2px solid #334155;color:#94a3b8;'>Min Score</th>"
            "<th style='text-align:left;padding:6px 10px;border-bottom:2px solid #334155;color:#94a3b8;'>Min RR</th>"
            "<th style='text-align:left;padding:6px 10px;border-bottom:2px solid #334155;color:#94a3b8;'>Bằng chứng</th>"
            "</tr>"
            + rows_html +
            "</table>"
            "<p style='color:#64748b;font-size:11px;'>"
            "Tiêu chí: ≥ 10 lệnh tổng, ≥ 8 lệnh sau lọc, kỳ vọng > +0.10R, PF > 1.2. "
            "Chọn chế độ <b>Backtest</b> hoặc <b>Research</b> để có nhiều lệnh phân tích hơn."
            "</p>"
            "</div>"
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Đề xuất cấu hình Scanner")
        dlg.setMinimumSize(800, 400)
        dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 18, 20, 16)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(
            "QTextEdit { background: #171c24; color: #e5e7eb; font-size: 13px; border: 1px solid #2b3545; border-radius: 6px; padding: 12px; }"
        )
        text.setHtml(html)"""

    new_recommend_block = """        try:
            light = (self.app.settings_service.load().display.theme == "light" 
                     if self.app else self.controller.settings_service.load().display.theme == "light")
        except Exception:
            light = False

        if light:
            text_color = "#111827"
            muted_color = "#57534E"
            border_color = "#cbd5e1"
            title_color = "#b45309"
        else:
            text_color = "#cbd5e1"
            muted_color = "#94a3b8"
            border_color = "#334155"
            title_color = "#f59e0b"

        # Build HTML table
        rows_html = ""
        for symbol, cfg in sorted(recs.items()):
            if cfg is None:
                rows_html += (
                    f"<tr>"
                    f"<td style='padding:6px 10px;color:{text_color};'>{symbol}</td>"
                    f"<td colspan='4' style='padding:6px 10px;color:{muted_color};'>Không đủ dữ liệu</td>"
                    f"</tr>"
                )
            else:
                evidence = cfg.get("_evidence", "")
                rows_html += (
                    f"<tr>"
                    f"<td style='padding:6px 10px;color:{text_color};font-weight:700;'>{symbol}</td>"
                    f"<td style='padding:6px 10px;color:#10b981;'>{cfg['regime']}</td>"
                    f"<td style='padding:6px 10px;color:#ea580c;'>{cfg['side'].upper()}</td>"
                    f"<td style='padding:6px 10px;color:#f59e0b;'>≥ {cfg['min_score']}</td>"
                    f"<td style='padding:6px 10px;color:#fb923c;'>≥ {cfg['min_rr']}</td>"
                    f"<td style='padding:6px 10px;color:{muted_color};font-size:12px;'>{evidence}</td>"
                    f"</tr>"
                )

        html = (
            "<div style='font-family:-apple-system,Segoe UI,sans-serif;font-size:13px;'>"
            f"<h2 style='color:{title_color};margin:0 0 4px;font-size:16px;'>Đề xuất cấu hình Scanner từ Backtest</h2>"
            f"<p style='color:{muted_color};font-size:11px;margin:0 0 12px;'>"
            "Dựa trên kết quả backtest, hệ thống đề xuất cấu hình cho từng cặp. "
            "Cấu hình này có thể dùng trong Settings để tự động nâng setup đủ điều kiện."
            "</p>"
            "<table style='width:100%;border-collapse:collapse;margin-bottom:16px;'>"
            "<tr>"
            f"<th style='text-align:left;padding:6px 10px;border-bottom:2px solid {border_color};color:{muted_color};'>Mã</th>"
            f"<th style='text-align:left;padding:6px 10px;border-bottom:2px solid {border_color};color:{muted_color};'>Regime</th>"
            f"<th style='text-align:left;padding:6px 10px;border-bottom:2px solid {border_color};color:{muted_color};'>Hướng</th>"
            f"<th style='text-align:left;padding:6px 10px;border-bottom:2px solid {border_color};color:{muted_color};'>Min Score</th>"
            f"<th style='text-align:left;padding:6px 10px;border-bottom:2px solid {border_color};color:{muted_color};'>Min RR</th>"
            f"<th style='text-align:left;padding:6px 10px;border-bottom:2px solid {border_color};color:{muted_color};'>Bằng chứng</th>"
            "</tr>"
            + rows_html +
            "</table>"
            f"<p style='color:{muted_color};font-size:11px;'>"
            "Tiêu chí: ≥ 10 lệnh tổng, ≥ 8 lệnh sau lọc, kỳ vọng > +0.10R, PF > 1.2. "
            "Chọn chế độ <b>Backtest</b> hoặc <b>Research</b> để có nhiều lệnh phân tích hơn."
            "</p>"
            "</div>"
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Đề xuất cấu hình Scanner")
        dlg.setMinimumSize(800, 400)
        if light:
            dlg.setStyleSheet("QDialog { background: #FAF9F5; }")
        else:
            dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 18, 20, 16)

        text = QTextEdit()
        text.setReadOnly(True)
        if light:
            text.setStyleSheet(
                "QTextEdit { background: #ffffff; color: #111827; font-size: 13px; border: 1px solid #D6D2C8; border-radius: 6px; padding: 12px; }"
            )
        else:
            text.setStyleSheet(
                "QTextEdit { background: #171c24; color: #e5e7eb; font-size: 13px; border: 1px solid #2b3545; border-radius: 6px; padding: 12px; }"
            )
        text.setHtml(html)"""

    if old_recommend_block in content:
        content = content.replace(old_recommend_block, new_recommend_block)
        print("8. Recommend config dialog style block and HTML updated.")
    else:
        print("Error: Recommend config dialog style block not found!")

    # 9. Replace _generate_stats_html with a theme-aware version
    stats_start = content.find("    def _generate_stats_html(self) -> str:")
    stats_end = content.find("    @staticmethod\n    def _format_ai_to_html(raw: str) -> str:")
    
    if stats_start != -1 and stats_end != -1:
        new_stats_method = """    def _generate_stats_html(self) -> str:
        if not self.result:
            return ""
        summary = self.result.get("summary", {}) if isinstance(self.result.get("summary"), dict) else {}

        try:
            light = (self.app.settings_service.load().display.theme == "light" 
                     if self.app else self.controller.settings_service.load().display.theme == "light")
        except Exception:
            light = False

        if light:
            text_color = "#111827"
            value_color = "#111827"
            muted_color = "#57534E"
            border_color = "#cbd5e1"
            row_border = "#e2e8f0"
            card_bg = "#f1f5f9"
            card_title = "#0f172a"
            panel_title_color = "#c2410c"
            pipeline_title_color = "#c2410c"
            details_title_color = "#b45309"
        else:
            text_color = "#e2e8f0"
            value_color = "#f8fafc"
            muted_color = "#94a3b8"
            border_color = "#334155"
            row_border = "#1e293b"
            card_bg = "#1e293b"
            card_title = "#f8fafc"
            panel_title_color = "#ea580c"
            pipeline_title_color = "#f97316"
            details_title_color = "#f59e0b"

        def get_stat(d, k, fallback="--"):
            val = d.get(k)
            if val is None: return fallback
            try:
                if float(str(val)) == int(float(str(val))):
                    return f"{int(float(str(val))):,}"
                return f"{float(str(val)):,.2f}"
            except (TypeError, ValueError):
                return str(val)

        def eval_winrate(wr_val):
            if wr_val >= 55: return "<span style='color:#10b981;font-weight:bold;'>🔥 Tuyệt vời</span>"
            if wr_val >= 45: return "<span style='color:#ea580c;font-weight:bold;'>✅ Tốt</span>"
            if wr_val >= 35: return "<span style='color:#f59e0b;'>⚠️ Đạt</span>"
            return "<span style='color:#e11d48;font-weight:bold;'>❌ Thấp</span>"

        def eval_profit_factor(pf_val):
            if pf_val >= 1.6: return "<span style='color:#10b981;font-weight:bold;'>🔥 Rất cao</span>"
            if pf_val >= 1.2: return "<span style='color:#ea580c;font-weight:bold;'>✅ Khá</span>"
            if pf_val >= 1.0: return "<span style='color:#f59e0b;'>⚠️ Hòa vốn</span>"
            return "<span style='color:#e11d48;font-weight:bold;'>❌ Lỗ</span>"

        def eval_drawdown(dd_val):
            val = -abs(dd_val)
            if val > -10: return "<span style='color:#10b981;font-weight:bold;'>🛡️ An toàn</span>"
            if val > -20: return "<span style='color:#f59e0b;'>⚠️ Cần theo dõi</span>"
            return "<span style='color:#e11d48;font-weight:bold;'>🆘 Nguy hiểm</span>"

        html = [
            "<div style='font-family:-apple-system,Segoe UI,sans-serif;'>",
            f"<h2 style='color:{panel_title_color}; margin-top: 0; margin-bottom: 12px; font-size: 16px;'>📊 BẢNG KẾT QUẢ TỔNG HỢP</h2>",
        ]
        
        wr = float(summary.get("win_rate", 0) or 0)
        pf = float(summary.get("profit_factor", 0) or 0)
        dd = float(summary.get("max_drawdown_r", 0) or 0)
        
        html.append(
            f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px;'>"
            f"<tr>"
            f"<th style='text-align: left; padding: 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Chỉ số</th>"
            f"<th style='text-align: right; padding: 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Giá trị</th>"
            f"<th style='text-align: right; padding: 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Đánh giá</th>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>🔢 Tổng số lệnh</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'total_trades', '0')}</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>-</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>🎯 Tỷ lệ thắng</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'win_rate')}%</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border};'>{eval_winrate(wr)}</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>💎 Hệ số lợi nhuận</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'profit_factor')}</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border};'>{eval_profit_factor(pf)}</td>"
            f"</tr>"
 
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>🚀 Kỳ vọng</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'expectancy_r')}R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>-</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>📉 Drawdown tối đa</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'max_drawdown_r')}R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border};'>{eval_drawdown(dd)}</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>💰 Tổng R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: #10b981; font-weight: bold;'>{get_stat(summary, 'total_r')}R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>-</td>"
            f"</tr>"
            f"</table>"
        )
 
        wins = int(summary.get("wins", 0) or 0)
        losses = int(summary.get("losses", 0) or 0)
        breakeven_count = int(summary.get("breakeven", 0) or 0)
        expired_count = int(summary.get("expired", 0) or 0)
        avg_win_r = float(summary.get("average_win_r", 0) or 0)
        avg_loss_r = float(summary.get("average_loss_r", 0) or 0)
        max_consec_wins = int(summary.get("max_consecutive_wins", 0) or 0)
        max_consec_losses = int(summary.get("max_consecutive_losses", 0) or 0)
        avg_holding = float(summary.get("average_holding_bars", 0) or 0)
 
        html.append(
            f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 12px;'>"
            f"<tr>"
            f"<th style='text-align: left; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Chi tiết thắng/thua</th>"
            f"<th style='text-align: right; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color}; width: 60px;'>Số lượng</th>"
            f"<th style='text-align: left; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Chỉ số bổ sung</th>"
            f"<th style='text-align: right; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color}; width: 80px;'>Giá trị</th>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981;'>🟢 Thắng</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981; font-weight: bold;'>{wins}</td>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Trung bình R thắng</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981; font-weight: bold;'>{avg_win_r:+.2f}R</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #e11d48;'>🔴 Thua</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #e11d48; font-weight: bold;'>{losses}</td>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Trung bình R thua</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #e11d48; font-weight: bold;'>{avg_loss_r:+.2f}R</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>⚪ Hòa</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color}; font-weight: bold;'>{breakeven_count}</td>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Chuỗi thắng tối đa</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981; font-weight: bold;'>{max_consec_wins}</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>⏰ Hết hạn</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color}; font-weight: bold;'>{expired_count}</td>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Chuỗi thua tối đa</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #e11d48; font-weight: bold;'>{max_consec_losses}</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>&nbsp;</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border};'>&nbsp;</td>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Số nến giữ lệnh TB</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color}; font-weight: bold;'>{avg_holding:.0f} nến</td>"
            f"</tr>"
            f"</table>"
        )
 
        symbol_stats = self.result.get("symbol_stats", {})
        if isinstance(symbol_stats, dict) and len(symbol_stats) > 1:
            html.append(f"<h2 style='color:{details_title_color}; margin-bottom: 16px; margin-top: 24px; font-size: 16px;'>🌍 CHI TIẾT TỪNG CẶP</h2>")
            html.append("<div style='display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;'>")
            for symbol, sym_stats in sorted(symbol_stats.items()):
                if not isinstance(sym_stats, dict):
                    continue
                sym_wr = float(sym_stats.get("win_rate", 0) or 0)
                sym_pf = float(sym_stats.get("profit_factor", 0) or 0)
                
                html.append(
                    f"<div style='background-color: {card_bg}; border-radius: 8px; padding: 14px; width: calc(50% - 6px); box-sizing: border-box; border-left: 4px solid #ea580c; border: 1px solid {border_color};'>"
                    f"<div style='font-size: 15px; font-weight: bold; color: {card_title}; margin-bottom: 10px;'>✨ {symbol}</div>"
                    f"<table style='width: 100%; border-collapse: collapse; font-size: 13px;'>"
                    f"<tr>"
                    f"<td style='padding: 4px 0;'><span style='color: {muted_color};'>Lệnh:</span> <span style='color: {text_color}; font-weight: bold;'>{get_stat(sym_stats, 'total_trades', '0')}</span></td>"
                    f"<td style='padding: 4px 0;'><span style='color: {muted_color};'>Kỳ vọng:</span> <span style='color: {text_color}; font-weight: bold;'>{get_stat(sym_stats, 'expectancy_r')}R</span></td>"
                    f"</tr>"
                    f"<tr>"
                    f"<td style='padding: 4px 0;'><span style='color: {muted_color};'>Tỷ lệ thắng:</span> <span style='color: {text_color}; font-weight: bold;'>{get_stat(sym_stats, 'win_rate')}%</span> {eval_winrate(sym_wr)}</td>"
                    f"<td style='padding: 4px 0;'><span style='color: {muted_color};'>PF:</span> <span style='color: {text_color}; font-weight: bold;'>{get_stat(sym_stats, 'profit_factor')}</span> {eval_profit_factor(sym_pf)}</td>"
                    f"</tr>"
                    f"<tr>"
                    f"<td style='padding: 4px 0;'><span style='color: #10b981; font-weight: bold;'>Tổng R:</span> <span style='color: #10b981; font-weight: bold;'>{get_stat(sym_stats, 'total_r')}R</span></td>"
                    f"<td style='padding: 4px 0;'><span style='color: #e11d48; font-weight: bold;'>DD:</span> <span style='color: #e11d48; font-weight: bold;'>{get_stat(sym_stats, 'max_drawdown_r')}R</span></td>"
                    f"</tr>"
                    f"</table>"
                    f"</div>"
                )
            html.append("</div>")
 
        diagnostics = self.result.get("diagnostics", {}) if isinstance(self.result.get("diagnostics"), dict) else {}
        pipeline_stats = diagnostics.get("pipeline_stats", {})
        gate_fail_counts = diagnostics.get("gate_fail_counts", {})
        if pipeline_stats:
            html.append(f"<h2 style='color:{pipeline_title_color}; margin-bottom: 12px; margin-top: 24px; font-size: 16px;'>🔬 CHẨN ĐOÁN PIPELINE</h2>")
            html.append(
                f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 16px; font-size: 13px;'>"
                f"<tr>"
                f"<th style='text-align: left; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Bước</th>"
                f"<th style='text-align: center; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: #10b981;'>Pass</th>"
                f"<th style='text-align: center; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: #e11d48;'>Fail</th>"
                f"<th style='text-align: center; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: #f59e0b;'>Warning</th>"
                f"<th style='text-align: left; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Trạng thái</th>"
                f"</tr>"
            )
            step_labels = {
                "validate": "1. Validate",
                "correlation": "2. Correlation",
                "score": "3. Score",
                "scenarios": "4. Scenarios",
                "direction": "5. Direction",
                "gate": "6. Gate",
                "final_score": "7. Final Score",
            }
            for step_key, label in step_labels.items():
                stats = pipeline_stats.get(step_key, {})
                if not stats:
                    continue
                p = stats.get("pass", 0)
                f = stats.get("fail", 0)
                w = stats.get("warning", 0)
                total = p + f + w
                if total == 0:
                    continue
                if f > 0:
                    status_icon = "🔴"
                    status_text = "Có lỗi"
                elif w > 0:
                    status_icon = "🟡"
                    status_text = "Cảnh báo"
                else:
                    status_icon = "🟢"
                    status_text = "OK"
                html.append(
                    f"<tr>"
                    f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>{label}</td>"
                    f"<td style='text-align: center; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981;'>{p}</td>"
                    f"<td style='text-align: center; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #e11d48;'>{f}</td>"
                    f"<td style='text-align: center; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #f59e0b;'>{w}</td>"
                    f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>{status_icon} {status_text}</td>"
                    f"</tr>"
                )
            html.append("</table>")
 
            ev = diagnostics.get("snapshots_evaluated", 0)
            blk = diagnostics.get("blocked_by_gate", 0)
            low = diagnostics.get("score_below_50_count", 0)
            html.append(
                f"<div style='display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; font-size: 12px; color: {muted_color};'>"
                f"<span>📊 Tổng snapshot: <b style='color:{text_color};'>{ev}</b></span>"
                f"<span>🚫 Bị gate chặn: <b style='color:#e11d48;'>{blk}</b></span>"
                f"<span>⚠️ Điểm {'<'}50: <b style='color:#f59e0b;'>{low}</b></span>"
                f"</div>"
            )
 
        if gate_fail_counts:
            html.append(f"<h3 style='color:{pipeline_title_color}; margin-bottom: 8px; margin-top: 16px; font-size: 14px;'>🚧 Chi tiết Gate</h3>")
            html.append(
                f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 12px;'>"
                f"<tr>"
                f"<th style='text-align: left; padding: 6px 10px; border-bottom: 1px solid {border_color}; color: {muted_color};'>Gate</th>"
                f"<th style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {border_color}; color: {muted_color};'>Số lần chặn/cảnh báo</th>"
                f"</tr>"
            )
            for gate_name, count in sorted(gate_fail_counts.items(), key=lambda x: -x[1]):
                html.append(
                    f"<tr>"
                    f"<td style='padding: 4px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>{gate_name}</td>"
                    f"<td style='text-align: right; padding: 4px 10px; border-bottom: 1px solid {row_border}; color: #fb7185; font-weight: bold;'>{count}</td>"
                    f"</tr>"
                )
            html.append("</table>")
 
        html.append("</div>")
        return "".join(html)"""

    if stats_start != -1 and stats_end != -1:
        content = content[:stats_start] + new_stats_method + content[stats_end:]
        print("9. Stats HTML generation updated successfully.")
    else:
        print("Error: _generate_stats_html block not found!")

    # 10. Replace _format_ai_to_html with a theme-aware version
    # Let's find the exact block of the original _format_ai_to_html method.
    # It starts at: @staticmethod\n    def _format_ai_to_html(raw: str) -> str:
    # and ends with: return "".join(html_lines)\n
    
    ai_start_marker = "    @staticmethod\n    def _format_ai_to_html(raw: str) -> str:"
    ai_start_pos = content.find(ai_start_marker)
    
    if ai_start_pos != -1:
        # Find the next return statement of _format_ai_to_html, which is: return "".join(html_lines)
        ai_end_marker = 'return "".join(html_lines)'
        ai_end_pos = content.find(ai_end_marker, ai_start_pos)
        
        if ai_end_pos != -1:
            # We want to include the whole line 'return "".join(html_lines)'
            ai_end_pos += len(ai_end_marker)
            
            new_ai_method = """    def _format_ai_to_html(self, raw: str) -> str:
        try:
            light = (self.app.settings_service.load().display.theme == "light" 
                     if self.app else self.controller.settings_service.load().display.theme == "light")
        except Exception:
            light = False

        if light:
            heading_color = "#0f172a"
            italic_color = "#334155"
            text_color = "#111827"
        else:
            heading_color = "#f8fafc"
            italic_color = "#cbd5e1"
            text_color = "#d1d5db"

        lines = raw.splitlines()
        html_lines: list[str] = []
        in_ul = False
        in_ol = False

        def _close_lists():
            nonlocal in_ul, in_ol
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False

        i = 0
        while i < len(lines):
            line = lines[i]
            line = line.replace("**", "")
            stripped = line.strip()

            if not stripped:
                _close_lists()
                html_lines.append("<br>")
                i += 1
                continue

            is_heading = (
                stripped.isupper()
                or (stripped.endswith(":") and len(stripped) < 80 and not stripped.startswith(("-", "•", "*", "1.", "2.", "3.", "4.", "5.")))
            )

            if is_heading:
                _close_lists()
                html_lines.append(f"<p style='margin:14px 0 6px;font-weight:700;color:{heading_color};font-size:14px;'>{stripped}</p>")
                i += 1
                continue

            bullet_match = False
            prefix = ""

            m = re.match(r"^(\\s*)([-*•])\\s+(.*)", stripped)
            if m:
                bullet_match = True
                prefix = "ul"
                content_txt = m.group(3)
            else:
                m = re.match(r"^(\\s*)(\\d+)[.)]\\s+(.*)", stripped)
                if m:
                    bullet_match = True
                    prefix = "ol"
                    content_txt = m.group(3)
                else:
                    m = re.match(r"^\\*\\s*(.*?)\\*$", stripped)
                    if m:
                        _close_lists()
                        html_lines.append(f"<p style='margin:4px 0;font-style:italic;color:{italic_color};'>{m.group(1)}</p>")
                        i += 1
                        continue
                    if stripped.startswith("*") and not stripped.startswith("* "):
                        stripped = stripped.lstrip("*")

            if bullet_match:
                if prefix == "ul" and not in_ul:
                    _close_lists()
                    html_lines.append(f"<ul style='margin-top:8px; margin-bottom:8px; padding-left:24px; color:{text_color};'>")
                    in_ul = True
                elif prefix == "ol" and not in_ol:
                    _close_lists()
                    html_lines.append(f"<ol style='margin-top:8px; margin-bottom:8px; padding-left:24px; color:{text_color};'>")
                    in_ol = True
                content_txt = content_txt.replace("*", "")
                html_lines.append(f"<li style='margin-top:8px; margin-bottom:8px;'>{content_txt}</li>")
                i += 1
                continue

            _close_lists()
            clean = stripped.replace("*", "")
            html_lines.append(f"<p style='margin-top:8px; margin-bottom:8px; color:{text_color};'>{clean}</p>")
            i += 1

        _close_lists()
        return "".join(html_lines)"""
            
            content = content[:ai_start_pos] + new_ai_method + content[ai_end_pos:]
            print("10. AI HTML formatter updated successfully (SAFE).")
        else:
            print("Error: AI end marker not found!")
    else:
        print("Error: AI start marker not found!")

    # 11. Inject new helper methods and showEvent
    # Let's place them right before _selected_symbols method
    target_pos = content.find("    def _selected_symbols(self) -> list[str]:")
    if target_pos != -1:
        helper_methods = """    def _is_light_theme(self) -> bool:
        try:
            settings = (
                self.app.settings_service.load()
                if self.app
                else self.controller.settings_service.load()
            )
            return settings.display.theme == "light"
        except Exception:
            return False

    def _refresh_progress_bar_style(self) -> None:
        light = self._is_light_theme()
        if light:
            bg_color = "#e2e8f0"
            border_color = "#cbd5e1"
            chunk_color = "#ea580c"
        else:
            bg_color = "#0f172a"
            border_color = "#334155"
            chunk_color = "#ea580c"
            
        self.progress.setStyleSheet(
            f"QProgressBar#BacktestProgress {{"
            f"background: {bg_color};"
            f"border: 1px solid {border_color};"
            f"border-radius: 5px;"
            f"}}"
            f"QProgressBar#BacktestProgress::chunk {{"
            f"background: {chunk_color};"
            f"border-radius: 4px;"
            f"}}"
        )

    def _refresh_trade_table_style(self) -> None:
        if not hasattr(self, "trades") or not self.trades:
            return
        
        light = self._is_light_theme()
        
        for row, trade in enumerate(self.trades):
            result = str(trade.get("result", "")).lower()
            
            # Decide colors based on theme
            if light:
                if result == "win":
                    bg = "#d1fae5"      # soft pastel green
                    fg = "#065f46"      # dark green text
                elif result == "loss":
                    bg = "#ffe4e6"      # soft pastel red
                    fg = "#9f1239"      # dark red text
                elif result == "breakeven":
                    bg = "#f1f5f9"      # soft pastel gray
                    fg = "#334155"      # dark gray text
                else:
                    bg = "#faf9f5"      # default light background
                    fg = "#111827"
            else:
                if result == "win":
                    bg = "#064e3b"      # dark green
                    fg = "#34d399"      # light green text
                elif result == "loss":
                    bg = "#881337"      # dark red
                    fg = "#f87171"      # light red text
                elif result == "breakeven":
                    bg = "#1e293b"      # dark gray
                    fg = "#cbd5e1"      # light gray text
                else:
                    bg = "#171c24"      # default dark
                    fg = "#cbd5e1"
                    
            from PyQt6.QtGui import QColor
            row_bg_color = QColor(bg)
            row_fg_color = QColor(fg)
            for col in range(len(self.TRADE_COLUMNS)):
                cell = self.table.item(row, col)
                if cell:
                    cell.setBackground(row_bg_color)
                    cell.setForeground(row_fg_color)

    def _refresh_theme_styles(self) -> None:
        self._refresh_progress_bar_style()
        self._refresh_verdict_banner_style()
        self._refresh_trade_table_style()
        if hasattr(self, "settings_frame") and self.settings_frame:
            self.settings_frame.setStyleSheet(self._backtest_form_stylesheet())

    def _refresh_verdict_banner_style(self) -> None:
        self._update_verdict()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_theme_styles()

"""
        content = content[:target_pos] + helper_methods + content[target_pos:]
        print("11. Dynamic theme helper methods and showEvent injected successfully.")
    else:
        print("Error: _selected_symbols method not found for helper injection!")

    # 12. Save back to file
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("12. File saved successfully!")

    # 13. Compile check
    try:
        py_compile.compile(path, doraise=True)
        print("SUCCESS: The refactored file compiled perfectly with zero syntax errors!")
    except Exception as e:
        print("ERROR: Compilation failed!")
        print(e)

if __name__ == '__main__':
    main()
