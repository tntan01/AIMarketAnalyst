from __future__ import annotations

from config.paths import app_data_dir
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
from controllers.journal_controller import JournalController
from services.storage_service import JsonStorage

from ui.components.chart_view import AnalysisChartView
from ui.screens.shared import action_button, card, page_header


class ScannerDetailScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
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

        self.stats = QGridLayout()
        self.stats.setSpacing(10)
        self.stat_value_labels = []
        for index, (title, value) in enumerate(
            [("Xếp hạng", "--"), ("Điểm tốt nhất", "--"), ("Thiên hướng", "--"), ("Quyền", "--")]
        ):
            widget, value_label = self._compact_stat(title, value)
            self.stat_value_labels.append(value_label)
            self.stats.addWidget(widget, 0, index)
            self.stats.setColumnStretch(index, 1)

        body = QHBoxLayout()
        body.setSpacing(10)
        
        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        left_col.addLayout(self.stats)
        
        self.chart = AnalysisChartView()
        self.chart_frame = QFrame()
        self.chart_frame.setObjectName("AnalysisChartFrame")
        chart_layout = QVBoxLayout(self.chart_frame)
        chart_layout.setContentsMargins(8, 8, 8, 8)
        chart_layout.setSpacing(0)
        chart_layout.addWidget(self.chart)
        
        left_col.addWidget(self.chart_frame, 1)
        body.addLayout(left_col, 7)
        
        detail = self._decision_card()
        detail.setMinimumWidth(320)
        detail.setMaximumWidth(520)
        body.addWidget(detail, 3)
        body.setStretch(0, 7)
        body.setStretch(1, 3)
        root.addLayout(body, 1)

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

    def _decision_card(self):
        frame = card("Bảng quyết định", object_name="ScannerDecisionPanel")

        self.decision_hero = QFrame()
        self.decision_hero.setObjectName("ScannerDecisionHero")
        hero_layout = QVBoxLayout(self.decision_hero)
        hero_layout.setContentsMargins(12, 10, 12, 10)
        hero_layout.setSpacing(4)
        self.action_label = QLabel("--")
        self.action_label.setObjectName("ScannerDecisionAction")
        self.action_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.action_reason_label = QLabel("--")
        self.action_reason_label.setObjectName("ScannerDecisionReason")
        self.action_reason_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.action_reason_label.setWordWrap(True)
        hero_layout.addWidget(self.action_label)
        hero_layout.addWidget(self.action_reason_label)
        frame.layout().addWidget(self.decision_hero)

        self.metric_labels: dict[str, QLabel] = {}
        metrics = QGridLayout()
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(8)
        metrics.setVerticalSpacing(8)
        for index, (key, title) in enumerate(
            [
                ("best_score", "Điểm tốt nhất"),
                ("buy_sell", "Buy / Sell"),
                ("gap", "Gap"),
                ("rr", "R:R"),
                ("m15", "M15"),
                ("entry", "Entry"),
            ]
        ):
            item, value_label = self._metric_tile(title, "--")
            self.metric_labels[key] = value_label
            metrics.addWidget(item, index // 2, index % 2)
        frame.layout().addLayout(metrics)

        scroll = QScrollArea()
        scroll.setObjectName("ScannerDecisionScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_content.setObjectName("ScannerDecisionScrollContent")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 4, 0)
        scroll_layout.setSpacing(8)

        scroll_layout.addWidget(self._section_title("Điều kiện cần chờ"))
        self.wait_layout = QVBoxLayout()
        self.wait_layout.setContentsMargins(0, 0, 0, 0)
        self.wait_layout.setSpacing(6)
        scroll_layout.addLayout(self.wait_layout)

        scroll_layout.addWidget(self._section_title("Luận điểm & rủi ro"))
        self.insight_layout = QVBoxLayout()
        self.insight_layout.setContentsMargins(0, 0, 0, 0)
        self.insight_layout.setSpacing(6)
        scroll_layout.addLayout(self.insight_layout)
        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        frame.layout().addWidget(scroll, 1)
        return frame

    def _metric_tile(self, title: str, value: str) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setObjectName("ScannerDecisionMetric")
        frame.setMinimumHeight(48)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("ScannerDecisionMetricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("ScannerDecisionMetricValue")
        value_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return frame, value_label

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

    def _compact_stat(self, title: str, value: str) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setObjectName("ScannerDetailStat")
        frame.setMinimumHeight(32)
        frame.setMaximumHeight(36)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("ScannerDetailStatTitle")
        value_label = QLabel(value)
        value_label.setObjectName("ScannerDetailStatValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_label.setWordWrap(False)
        layout.addWidget(title_label)
        layout.addStretch(1)
        layout.addWidget(value_label)
        return frame, value_label

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
        values = [
            f"#{self.row.get('rank', '--')}",
            f"{self.row.get('best_score', '--')} / 100",
            self._bias_text(self.row.get("direction_bias", "--")),
            self._permission_text(str(self.row.get("trade_permission", "--"))),
        ]
        for label, value in zip(self.stat_value_labels, values):
            label.setText(str(value))
        self._refresh_decision_panel()
        self._refresh_chart()

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
            self.chart.set_payload(payload)
        except Exception:
            self.chart.show_error("Khong the tao du lieu bieu do tu ket qua quet.")

    def _refresh_decision_panel(self) -> None:
        if not self.row:
            self.action_label.setText("--")
            self.action_reason_label.setText("Chọn một dòng trong bảng quét để xem chi tiết.")
            return

        action_code = str(self.row.get("display_action") or self.row.get("scanner_action") or "--")
        action_text = self._action_text(action_code)
        self.action_label.setText(action_text.upper())
        self.action_label.setProperty("state", action_code)
        self.action_label.style().unpolish(self.action_label)
        self.action_label.style().polish(self.action_label)
        self.action_reason_label.setText(self._decision_reason())

        self.metric_labels["best_score"].setText(f"{self.row.get('best_score', '--')} / 100")
        self.metric_labels["buy_sell"].setText(f"{self.row.get('buy_score', '--')} / {self.row.get('sell_score', '--')}")
        self.metric_labels["gap"].setText(self._gap_text())
        self.metric_labels["rr"].setText(str(self.row.get("risk_reward") or "Chưa có"))
        self.metric_labels["m15"].setText(self._m15_text())
        self.metric_labels["entry"].setText(self._entry_status_display())

        self._fill_pills(self.wait_layout, self._wait_conditions(), "wait")
        self._fill_pills(self.insight_layout, self._insights(), "risk")

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
        return {"ready": "Sẵn sàng", "watch": "Theo dõi", "wait": "Chờ", "skip": "Bỏ qua"}.get(value, value)

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
            "no_setup": "Không có setup",
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

    def _gap_text(self) -> str:
        gap, min_gap = self._gap_numbers()
        if gap is None:
            return "--"
        if min_gap is None:
            return self._compact_number(gap)
        return f"{self._compact_number(gap)} / {self._compact_number(min_gap)}"

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
