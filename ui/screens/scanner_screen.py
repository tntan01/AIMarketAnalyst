from __future__ import annotations 

from config.constants import SUPPORTED_SYMBOLS
from controllers .scanner_controller import ScannerController 
from core .scanner import ScannerRequest
from core.backtest_config import (
    analysis_thresholds_for_symbol,
    serialize_backtest_config,
)
from core.risk_engine import AnalysisInput, position_sizing, recalc_execution_lot
from core.reason_codes import codes_to_messages
from core.scanner_zone_origin import zone_origin_from_row
from PyQt6 .QtCore import QAbstractTableModel ,QEvent ,QModelIndex ,QRect ,QSize ,Qt ,QTimer
from PyQt6 .QtGui import QColor ,QIcon
from PyQt6 .QtWidgets import (
QCheckBox ,
QComboBox ,
QDialog ,
QDialogButtonBox ,
QFrame ,
QGridLayout ,
QHBoxLayout ,
QHeaderView ,
QLabel ,
QMessageBox ,
QProgressBar ,
QPushButton ,
QScrollArea ,
QSizePolicy ,
QStyle ,
QTableView ,
QTableWidget ,
QTableWidgetItem ,
QTextEdit ,
QVBoxLayout ,
QWidget ,
)
from services .mt5_service import MT5Service
from services .settings_service import SettingsService
from ui.layout_system import configure_table
from ui .screens .shared import action_button ,card ,labeled_value ,page_header
from ui.scanner_presentation import sort_scanner_rows_for_display
from ui.scanner_rr_formatters import (
    enrich_order_note_with_current_rr,
    format_order_entry_tooltip,
    format_order_rr_text,
    format_order_rr_tooltip,
)
from ui.rich_text import compile_rich_html
from ui.theme import palette_for, semantic_role_for_color
from ui.theme.fonts import get_body_font
from ui.theme_manager import current_palette, is_light_theme, set_dynamic_property
from ui.translation import vi_term


class ScannerTableModel (QAbstractTableModel ):
    COLUMNS =[
    ("presentation_rank","STT"),
    ("symbol","Mã"),
    ("candidate_status","Trạng thái"),
    ("selected_side","Hướng"),
    ("market_regime","Bối cảnh TT"),
    ("zone_origin_class","Loại vùng"),
    ("price_vs_zone","Vùng"),
    ("setup_score","Điểm thiết lập"),
    ("opportunity_rank","Ưu tiên"),
    ("evidence_confidence","Tin cậy LS"),
    ("execution_readiness","Sẵn sàng"),
    ("expected_effective_rr","R:R dự kiến"),
    ("auto_trade_branch","Quy tắc"),
    ("strategy_config_status","Cấu hình BT"),
    ]

    ACTION_TEXT ={"ready":'Sẵn sàng',"watch":'Theo dõi',"wait":'Chờ',"skip":'Bỏ qua'}
    BIAS_TEXT ={"buy":"Mua","sell":'Bán',"neutral":'Trung lập',"stand_aside":'Đứng ngoài'}
    PERMISSION_TEXT ={"allowed":'Được phép',"caution":'Cẩn trọng',"blocked":'Bị chặn'}
    MACRO_BIAS_TEXT ={"aligned":'Thuận',"neutral":'Trung tính',"divergent":'Ngược'}
    ENTRY_ZONE_TEXT ={"in_zone":"Trong vùng","near_zone":"Ngoài vùng","far":"Ngoài vùng","unknown":"--"}
    GROUP_TEXT ={"ready_now":"Sẵn sàng ngay","waiting_confirmation":"Chờ xác nhận","watch_zone":"Theo dõi","blocked":"Bị chặn"}
    STATUS_TEXT ={
        "READY_NOW":"Đạt điều kiện",
        "WAITING_CONFIRMATION":"Chờ xác nhận",
        "WATCH_ZONE":"Đang theo dõi",
        "OUT_OF_STRATEGY":"Chưa đạt quy tắc",
        "BLOCKED":"Bị chặn an toàn",
        "DATA_UNAVAILABLE":"Không đủ dữ liệu",
    }
    ENTRY_STATUS_TEXT ={
        "confirmed_entry":"Đã xác nhận",
        "ready":"Đã xác nhận",
        "ready_to_trade":"Đã xác nhận",
        "waiting_confirmation":"Chờ xác nhận",
        "waiting_for_confirmation":"Chờ xác nhận",
        "watch_zone":"Theo dõi vùng",
        "in_zone":"Trong vùng",
        "near_zone":"Gần vùng",
        "invalidated":"Vô hiệu",
        "no_setup":"Chưa có setup",
        "data_unavailable":"Thiếu dữ liệu",
        "unknown":"--",
    }

    def __init__ (self )->None :
        super ().__init__ ()
        self .rows :list [dict [str ,object ]]=[]
        self._theme = "dark"

    def set_theme(self, theme: object) -> None:
        self._theme = str(theme or "dark").strip().lower()

    def rowCount (self ,parent :QModelIndex =QModelIndex ())->int :
        return 0 if parent .isValid ()else len (self .rows )

    def columnCount (self ,parent :QModelIndex =QModelIndex ())->int :
        return 0 if parent .isValid ()else len (self .COLUMNS )

    def data (self ,index :QModelIndex ,role :int =Qt .ItemDataRole .DisplayRole ):
        if not index .isValid ():
            return None 
        row =self .rows [index .row ()]
        key =self .COLUMNS [index .column ()][0 ]
        value =row .get (key )
        if role ==Qt .ItemDataRole .DisplayRole :
            return self ._display_value (key ,value ,row )
        if role ==Qt .ItemDataRole .TextAlignmentRole :
            if key !="symbol":
                return Qt .AlignmentFlag .AlignCenter
            return Qt .AlignmentFlag .AlignVCenter |Qt .AlignmentFlag .AlignLeft 
        if role ==Qt .ItemDataRole .BackgroundRole :
            return self ._row_background (row )
        if role ==Qt .ItemDataRole .ForegroundRole :
            return self ._foreground (row ,key )
        if role ==Qt .ItemDataRole .ToolTipRole :
            if key =="candidate_status":
                return self ._candidate_status_tooltip (row )
            if key =="direction_bias":
                return self ._direction_bias_tooltip (value )
            if key =="entry_status":
                return self ._entry_status_tooltip (value ,row )
            if key =="price_vs_zone":
                return self ._price_vs_zone_tooltip (row )
            if key in {"opportunity_score","opportunity_rank"}:
                return self ._opportunity_score_tooltip (row )
            if key in {"journal_sample_size","journal_expectancy_r"}:
                feedback = row.get("journal_feedback") if isinstance(row.get("journal_feedback"), dict) else {}
                reasons = feedback.get("reasons", []) if isinstance(feedback, dict) else []
                return "\n".join(str(item) for item in reasons) if reasons else "Phản hồi từ nhật ký các lệnh đã đóng."
            return str (row .get ("permission_reason")or row .get ("short_reason")or "")
        # Cot ly do chinh: tat text elide de hien thi day du, khong cat "..."
        reason_col = next((idx for idx, (col_key, _label) in enumerate(self.COLUMNS) if col_key == "short_reason"), -1)
        if role ==0x010B and index .column ()==reason_col :
            return Qt .TextElideMode .ElideNone
        return None

    def headerData (self ,section :int ,orientation :Qt .Orientation ,role :int =Qt .ItemDataRole .DisplayRole ):
        if orientation ==Qt .Orientation .Horizontal :
            if role ==Qt .ItemDataRole .DisplayRole :
                return self .COLUMNS [section ][1 ]
            if role ==Qt .ItemDataRole .TextAlignmentRole :
                return Qt .AlignmentFlag .AlignCenter 
            if role ==Qt .ItemDataRole .ToolTipRole :
                return self .COLUMNS [section ][1 ]
            return None 
        if role !=Qt .ItemDataRole .DisplayRole :
            return None 
        return str (section +1 )

    def set_rows (self ,rows :list [dict [str ,object ]])->None :
        self .beginResetModel ()
        display_rows :list [dict [str ,object ]]=[]
        for source in rows :
            if not isinstance (source ,dict ):
                continue
            display_row =dict (source )
            display_row .pop ("presentation_rank",None )
            display_row ["presentation_rank"]=len (display_rows )+1
            display_rows .append (display_row )
        self .rows =display_rows
        self .endResetModel ()

    def row_at (self ,row :int )->dict [str ,object ]|None :
        if 0 <=row <len (self .rows ):
            return self .rows [row ]
        return None 

    def _has_real_plan(self, row: dict[str, object] | None) -> bool:
        """Check if the row has a real zone (SMC or technical), not fallback/none."""
        origin = zone_origin_from_row(row)
        return origin in ("smc", "technical")

    def _zone_tier(self, row: dict[str, object] | None) -> str:
        """Return zone quality tier by inspecting raw SMC/technical context.

        Returns:
            \"smc\"       — at least one SMC zone exists on H4
            \"technical\" — only technical swing zones, no SMC
            \"fallback\"  — no zones at all
        """
        if not row:
            return "fallback"
        analysis = row.get("analysis_result")
        if not isinstance(analysis, dict):
            return "fallback"

        smc = analysis.get("smc")
        if isinstance(smc, dict):
            h4 = smc.get("H4", {})
            if isinstance(h4, dict):
                for key in ("demand_zones", "supply_zones", "order_blocks", "fvg"):
                    zones = h4.get(key, [])
                    if isinstance(zones, list) and len(zones) > 0:
                        for z in zones:
                            if isinstance(z, dict) and not z.get("broken") and z.get("zone_score", 0) >= 55:
                                return "smc"

        technical = analysis.get("technical")
        if isinstance(technical, dict):
            supports = technical.get("support_zones", [])
            resistances = technical.get("resistance_zones", [])
            if (isinstance(supports, list) and len(supports) > 0) or \
               (isinstance(resistances, list) and len(resistances) > 0):
                return "technical"

        return "fallback"

    def _is_fallback_row(self, row: dict[str, object] | None) -> bool:
        """Row is classified as fallback (ATR display-only) zone origin."""
        return zone_origin_from_row(row) == "fallback"

    def _display_value (self ,key :str ,value :object ,row :dict [str ,object ]|None =None )->str :
        if not self._has_real_plan(row) and key in {
            "price_vs_zone",
            "m15_quality",
            "macro_bias",
            "expected_effective_rr",
        }:
            return "--"
        if key =="zone_origin_class":
            return {
                "smc":"SMC thật",
                "technical":"Technical",
                "fallback":"Fallback",
                "none":"--",
            }.get(str(value or "").strip().lower(),"--")
        if key =="candidate_status":
            return self.STATUS_TEXT.get(str(value or "").upper(), str(value or "--"))
        if key =="selected_side":
            return self.BIAS_TEXT.get(str(value or "").lower(), str(value or "--"))
        if key =="direction_bias":
            return self ._format_direction_bias (value )
        if key =="price_vs_zone":
            normalized = str(value or "").strip().lower()
            return self .ENTRY_ZONE_TEXT .get (normalized ,"--")
        if key =="market_regime":
            return vi_term(value)
        if key =="macro_score":
            score_val =int (value )if isinstance (value ,(int ,float ))else 15 
            conf =float (row .get ("macro_confidence",1.0 ))if row else 1.0 
            quality_dot ="●"if conf >=0.8 else ("○"if conf >=0.5 else "◌")
            return f"{quality_dot } {score_val }"
        if key =="macro_bias":
            return self .MACRO_BIAS_TEXT .get (str (value ),str (value or "--"))
        if key =="expected_effective_rr":
            if isinstance (value ,(int ,float )):
                return f"{value:.1f}"
            return "-"
        if key =="entry_zone":
            if isinstance (value ,list )and len (value )==2 :
                return f"{value[0]:.5f}–{value[1]:.5f}"
            return "--"
        if key =="stop_loss":
            if isinstance (value ,(int ,float )):
                return f"{value:.5f}"
            return "--"
        if key =="take_profit":
            if isinstance (value ,list )and value :
                return f"{value[0]:.5f}"
            if isinstance (value ,(int ,float )):
                return f"{value:.5f}"
            return "--"
        if key =="journal_sample_size":
            return str (int (value ))if isinstance (value ,(int ,float ))else "0"
        if key =="journal_expectancy_r":
            return f"{float(value):.2f}R" if isinstance(value, (int, float)) else "--"
        if key =="final_score":
            return str (int (value ))if isinstance (value ,(int ,float ))else "--"
        if key =="setup_score":
            return str (int (value ))if isinstance (value ,(int ,float ))else "--"
        if key =="opportunity_score":
            return str (int (value ))if isinstance (value ,(int ,float ))else "--"
        if key =="opportunity_rank":
            return f"{float(value):.0f}" if isinstance(value, (int, float)) else "--"
        if key in {"evidence_confidence","execution_readiness"}:
            return f"{float(value):.0f}%" if isinstance(value, (int, float)) else "--"
        if key =="auto_trade_branch":
            return {
                "BACKTEST_VALIDATED":"Backtest",
                "DEFAULT_RULES":"Mặc định",
                "BACKTEST_INVALID":"BT lỗi",
            }.get(str(value or ""), str(value or "--"))
        if key =="strategy_config_status":
            return {
                "VALIDATED":"Hợp lệ",
                "NOT_CONFIGURED":"Mặc định",
                "DRAFT":"Bản nháp",
                "EXPIRED":"Hết hạn",
                "INVALID":"Không hợp lệ",
                "VERSION_MISMATCH":"Sai phiên bản",
                "DISABLED":"Đã tắt",
            }.get(str(value or "").upper(), str(value or "--"))
        if key =="scanner_group":
            return self .GROUP_TEXT .get (str (value ),str (value or "--"))
        if key =="entry_status":
            if self ._has_no_entry_zone (row )and str (value or "").strip ().lower ()in {
                "waiting_confirmation",
                "waiting_for_confirmation",
                "watch_zone",
                "unknown",
                "",
            }:
                return "Chưa có vùng"
            return self .ENTRY_STATUS_TEXT .get (
                str (value or "").strip ().lower (),str (value or "--")
            )
        if key =="m15_quality":
            m15_map ={"strict":"Chặt","loose":"Lỏng","none":"Không đạt","backtest_fallback":"Mô phỏng"}
            return m15_map .get (str (value ),str (value or "--"))
        if key =="score_gap":
            return str (int (value ))if isinstance (value ,(int ,float ))else "--"
        if key =="short_reason":
            text =str (value if value is not None else "--")
            if row is not None and bool (row .get ("ai_summary_available")):
                return f"AI: {text }"
            return text 
        return str (value if value is not None else "--")

    @staticmethod
    def _strategy_gap_messages(
        row: dict[str, object] | None,
    ) -> tuple[str, ...]:
        """Return concise user-facing reasons why the active rule is not met."""

        if not isinstance(row, dict):
            return ()
        decision = (
            row.get("scanner_candidate_decision")
            if isinstance(row.get("scanner_candidate_decision"), dict)
            else {}
        )
        strategy = (
            decision.get("strategy")
            if isinstance(decision.get("strategy"), dict)
            else {}
        )
        codes: list[str] = []
        for source in (
            strategy.get("reason_codes"),
            decision.get("reason_codes"),
            row.get("auto_trade_reason_codes"),
        ):
            if not isinstance(source, (list, tuple)):
                continue
            for code in source:
                normalized = str(code).strip()
                if normalized and normalized not in codes:
                    codes.append(normalized)

        def number(value: object) -> float | None:
            try:
                return float(value)
            except (TypeError, ValueError, OverflowError):
                return None

        setup = number(strategy.get("score_value", row.get("setup_score")))
        min_setup = number(strategy.get("min_score", row.get("min_score")))
        rr = number(
            strategy.get(
                "expected_effective_rr",
                row.get("expected_effective_rr"),
            )
        )
        min_rr = number(strategy.get("min_rr", row.get("min_rr")))
        messages: list[str] = []

        for code in codes:
            if code in {
                "SETUP_SCORE_BELOW_DEFAULT_MIN",
                "SETUP_SCORE_BELOW_MIN",
            }:
                if setup is not None and min_setup is not None:
                    message = (
                        f"Điểm thiết lập {setup:.0f}/{min_setup:.0f}, "
                        "chưa đạt ngưỡng."
                    )
                else:
                    message = "Điểm thiết lập chưa đạt ngưỡng yêu cầu."
            elif code in {"NO_TRADE_SIDE", "MISSING_SELECTED_SIDE"}:
                message = "Chưa xác định được hướng Mua/Bán đủ điều kiện."
            elif code in {"BEST_SIDE_NOT_CLEAR", "SCORE_GAP_BELOW_MIN"}:
                message = "Chênh lệch điểm Mua/Bán chưa đủ rõ."
            elif code in {
                "MISSING_SIDE_EVALUATION",
                "SETUP_SCORE_MISSING",
            }:
                message = "Chưa có đánh giá thiết lập hợp lệ cho hướng giao dịch."
            elif code == "EXPECTED_RR_MISSING":
                message = "Chưa có Entry, SL và TP hợp lệ để tính R:R dự kiến."
            elif code in {
                "EXPECTED_RR_BELOW_DEFAULT_MIN",
                "EXPECTED_RR_BELOW_MIN",
            }:
                if rr is not None and min_rr is not None:
                    message = (
                        f"R:R dự kiến {rr:.1f}/{min_rr:.1f}, "
                        "chưa đạt ngưỡng."
                    )
                else:
                    message = "R:R dự kiến chưa đạt ngưỡng yêu cầu."
            else:
                translated = codes_to_messages([code])
                message = translated[0] if translated else code
                if message == code:
                    continue
            if message not in messages:
                messages.append(message)
        return tuple(messages)

    def _candidate_status_tooltip(
        self,
        row: dict[str, object] | None,
    ) -> str:
        if not isinstance(row, dict):
            return "--"
        status = str(row.get("candidate_status") or "").strip().upper()
        label = self.STATUS_TEXT.get(status, status or "--")
        if status == "OUT_OF_STRATEGY":
            headline = (
                f"{label}: cặp vẫn được hỗ trợ nhưng chưa đáp ứng đủ "
                "quy tắc giao dịch trong lần quét này."
            )
        elif status == "READY_NOW":
            headline = (
                f"{label}: đạt điều kiện tại lúc quét, chưa đồng nghĩa "
                "lệnh chắc chắn được gửi."
            )
        else:
            headline = label
        details = list(self._strategy_gap_messages(row))
        if not details:
            fallback = str(
                row.get("permission_reason")
                or row.get("short_reason")
                or ""
            ).strip()
            if fallback:
                details.append(fallback)
        return "\n".join([headline, *details[:4]])

    def _foreground (self ,row :dict [str ,object ],key :str ):
        palette = palette_for(self._theme)
        colors = {
            "success": QColor(palette.success),
            "warning": QColor(palette.warning),
            "danger": QColor(palette.danger),
            "muted": QColor(palette.text_muted),
            "subtle": QColor(palette.text_subtle),
            "buy": QColor(palette.buy),
            "sell": QColor(palette.sell),
        }
        if key =="candidate_status":
            return {
                "READY_NOW":colors["success"],
                "WAITING_CONFIRMATION":colors["warning"],
                "WATCH_ZONE":colors["warning"],
                "OUT_OF_STRATEGY":colors["muted"],
                "BLOCKED":colors["danger"],
                "DATA_UNAVAILABLE":colors["subtle"],
            }.get(str(row.get(key, "")).upper())
        if key =="selected_side":
            return {
                "buy":colors["buy"],
                "sell":colors["sell"],
            }.get(str(row.get(key, "")).lower())
        if key in {"opportunity_rank","setup_score","evidence_confidence","execution_readiness"}:
            try:
                value = float(row.get(key))
            except (TypeError, ValueError):
                return colors["muted"]
            if value >= 70:
                return colors["success"]
            if value >= 40:
                return colors["warning"]
            return colors["muted"]
        if key =="strategy_config_status":
            return {
                "VALIDATED":colors["success"],
                "NOT_CONFIGURED":colors["muted"],
                "DRAFT":colors["warning"],
                "EXPIRED":colors["danger"],
                "INVALID":colors["danger"],
                "VERSION_MISMATCH":colors["danger"],
            }.get(str(row.get(key, "")).upper(), colors["muted"])
        if key =="scanner_group":
            group =str (row .get ("scanner_group",""))
            return {
            "ready_now":colors["success"],
            "waiting_confirmation":colors["warning"],
            "watch_zone":colors["warning"],
            "blocked":colors["danger"],
            }.get (group )
        if key =="direction_bias":
            side =self ._direction_bias_side (row .get (key ))
            return {"buy":colors["buy"],"sell":colors["sell"]}.get (side )
        if key =="zone_origin_class":
            return {
                "smc":colors["success"],
                "technical":colors["warning"],
                "fallback":colors["muted"],
                "none":colors["subtle"],
            }.get(str(row.get(key,"")).strip().lower())
        if key =="market_regime":
            regime =str (row .get (key ,""))
            return {
            "trend_up":colors["success"],
            "trend_down":colors["danger"],
            "range":colors["warning"],
            "volatile":colors["warning"],
            "unknown":colors["muted"],
            }.get (regime )
        if key =="m15_quality":
            quality =str (row .get (key ,""))
            return {
            "strict":colors["success"],
            "loose":colors["warning"],
            "none":colors["danger"],
            "backtest_fallback":colors["muted"],
            }.get (quality )
        if key =="expected_effective_rr":
            try:
                val =float (row .get (key ))
            except (TypeError ,ValueError ):
                return colors["muted"]
            if val >=2.0 :
                return colors["success"]
            if val >=1.3 :
                return colors["warning"]
            return colors["danger"]
        if key =="price_vs_zone":
            if not self._has_real_plan(row):
                return colors["subtle"]
            normalized = str(row.get(key, "")).strip().lower()
            return {
            "in_zone":colors["success"],
            "near_zone":colors["muted"],
            "far":colors["muted"],
            "unknown":colors["subtle"],
            }.get (normalized ,colors["muted"])
        if key =="macro_bias":
            return {
            "aligned":colors["success"],
            "neutral":colors["warning"],
            "divergent":colors["danger"],
            }.get (str (row .get (key )))
        if key =="macro_score":
            val =int (row .get ("macro_score",15 ))
            if val >=22 :
                return colors["success"]
            if val >=15 :
                return colors["warning"]
            return colors["muted"]
        if key =="journal_expectancy_r":
            try:
                val =float (row .get ("journal_expectancy_r"))
            except (TypeError ,ValueError ):
                return colors["muted"]
            if val >0 :
                return colors["success"]
            if val <0 :
                return colors["danger"]
            return colors["muted"]
        if key =="journal_sample_size":
            return colors["muted"]
        if key =="entry_status":
            if self ._has_no_entry_zone (row ):
                return colors["muted"]
            raw =str (row .get (key ,"")).strip ().lower ()
            if raw in ("confirmed_entry","ready","ready_to_trade"):
                return colors["success"]
            if raw in ("waiting_confirmation","waiting_for_confirmation","watch_zone","in_zone","near_zone"):
                return colors["warning"]
            if raw in ("invalidated","no_setup","data_unavailable","","none"):
                return colors["muted"]
            return None
        return None

    @staticmethod
    def _row_background(row: dict[str, object]) -> QColor | None:
        """Return row background color — all rows use Qt default alternating colors."""
        return None

    @staticmethod
    def _has_no_entry_zone(row: dict[str, object] | None) -> bool:
        if not row:
            return False
        price_zone = str(row.get("price_vs_zone") or "").strip().lower()
        if price_zone == "unknown":
            return True
        zones = row.get("entry_zone") or row.get("entry_zones")
        return price_zone in ("", "none", "--") and not zones

    # ---- direction_bias display helpers ----

    @staticmethod
    def _direction_bias_tooltip(value: object) -> str:
        """Build a compact tooltip for the direction_bias column.

        Dict:  "BUY 54 / SELL 44 | Gap 10 | Min 10"
        String: legacy text or "--".
        """
        if isinstance(value, dict):
            side = value.get("best_side", "?")
            buy = value.get("buy_score", "?")
            sell = value.get("sell_score", "?")
            gap = value.get("score_gap", "?")
            min_gap = value.get("min_gap", "?")
            return f"{side.upper()} {buy} / SELL {sell} | Gap {gap} | Min {min_gap}"
        if isinstance(value, str) and value.strip():
            return str(value)
        return "--"

    @staticmethod
    def _price_vs_zone_tooltip(row: dict[str, object] | None = None) -> str:
        return (
            "Trạng thái giá tại thời điểm quét so với vùng entry đã chọn.\n"
            "Trong vùng = giá nằm trong hoặc đúng biên vùng.\n"
            "Ngoài vùng = giá nằm ngoài hai biên.\n"
            "-- = chưa có vùng thật hoặc thiếu dữ liệu.\n"
            "Giá sẽ được kiểm tra lại theo bid/ask live trước khi gửi lệnh."
        )

    @staticmethod
    def _entry_status_tooltip(value: object, row: dict[str, object] | None = None) -> str:
        """Tooltip showing both the Vietnamese label and technical code."""
        if ScannerTableModel._has_no_entry_zone(row):
            return "Chưa có vùng entry nên chưa thể xác nhận điểm vào lệnh."
        display = ScannerTableModel.ENTRY_STATUS_TEXT.get(
            str(value or "").strip().lower(), str(value or "--")
        )
        raw = str(value).strip() if value is not None and str(value).strip() else ""
        if raw:
            return f"Trang thai entry: {display} | Ma ky thuat: {raw}"
        return f"Trang thai entry: {display}"

    @staticmethod
    def _opportunity_score_tooltip(row: dict[str, object] | None) -> str:
        """Tooltip showing final_score + opportunity breakdown."""
        if not row:
            return "--"
        final = row.get("final_score")
        if not isinstance(final, (int, float)):
            analysis = row.get("analysis_result")
            if isinstance(analysis, dict):
                final = analysis.get("final_score")
        final_str = f"{int(final)}" if isinstance(final, (int, float)) else "--"
        breakdown = row.get("ranking_score_breakdown")
        if isinstance(breakdown, dict):
            if "setup_component" in breakdown:
                return (
                    f"Opportunity Rank: {float(row.get('opportunity_rank', 0) or 0):.1f}/100\n"
                    f"Setup: {float(breakdown.get('setup_component', 0) or 0):.1f}"
                    f" | RR: {float(breakdown.get('rr_component', 0) or 0):.1f}"
                    f" | Vị trí: {float(breakdown.get('proximity_component', 0) or 0):.1f}\n"
                    f"Bằng chứng: {float(breakdown.get('evidence_component', 0) or 0):.1f}"
                    f" | Thực thi: {float(breakdown.get('execution_component', 0) or 0):.1f}"
                    f" | Phạt: {float(breakdown.get('penalty_component', 0) or 0):.1f}\n"
                    f"Trạng thái: {breakdown.get('status', '--')}"
                )
            base = breakdown.get("base_final_score", "?")
            prox = breakdown.get("proximity_bonus", 0)
            ready = breakdown.get("readiness_bonus", 0)
            rr = breakdown.get("rr_bonus", 0)
            spread = breakdown.get("spread_penalty", 0)
            news = breakdown.get("news_penalty", 0)
            return (
                f"Final Score: {final_str}\n"
                f"  + Proximity: {prox:+d}  |  Readiness: {ready:+d}  |  RR bonus: {rr:+d}\n"
                f"  - Spread: {spread}  |  News: {news}\n"
                f"Base: {base}"
            )
        return f"Final Score: {final_str}"

    @staticmethod
    def _direction_bias_side(value: object) -> str | None:
        """Extract best_side from dict or string value."""
        if isinstance(value, dict):
            side = value.get("best_side")
            return str(side) if side in ("buy", "sell") else None
        if isinstance(value, str):
            s = value.strip().lower()
            return s if s in ("buy", "sell") else None
        return None

    @staticmethod
    def _format_direction_bias(value: object) -> str:
        """Format direction_bias dict or string to a short Vietnamese label.

        Dict:  best_side + is_clear_bias → "BUY rõ", "BUY yếu", etc.
        String: legacy mapping via BIAS_TEXT.
        """
        if isinstance(value, dict):
            side = value.get("best_side")
            gap = value.get("score_gap")
            score = value.get("buy_score") if side == "buy" else value.get("sell_score")
            try:
                score_num = float(score)
            except (TypeError, ValueError):
                score_num = 0.0
            try:
                gap_num = int(float(gap))
            except (TypeError, ValueError):
                gap_num = None
            if score_num >= 65:
                strength = "rõ" if value.get("is_clear_bias", False) else "trung bình"
            elif score_num >= 50:
                strength = "trung bình"
            else:
                strength = "yếu"
            suffix = f" · Gap {gap_num}" if gap_num is not None else ""
            if side == "buy":
                return f"BUY {strength}{suffix}"
            if side == "sell":
                return f"SELL {strength}{suffix}"
            return "Trung lập"
        if isinstance(value, str):
            return ScannerTableModel.BIAS_TEXT.get(
                value.strip().lower(), str(value or "--")
            )
        return "--"


class ScannerScreen (QWidget ):
    # Automatic execution is available only in periodic scan mode. The user
    # must still opt in explicitly and every order remains subject to rollout
    # and execution safety gates.
    AUTO_TRADE_UI_ENABLED =True
    # Dynamically resolved from COLUMNS
    SHORT_REASON_COL =12  # overridden in __init__
    TABLE_CELL_HORIZONTAL_PADDING =24
    TABLE_HEADER_HORIZONTAL_PADDING =40
    TABLE_EXTRA_COLUMN_PADDING ={1 :18 ,2 :18 ,8 :18 ,10 :18 ,12 :24}
    TABLE_REASON_HORIZONTAL_PADDING =30
    TABLE_MIN_REASON_WIDTH =150

    def __init__ (self ,navigate =None ,*, app =None )->None :
        super ().__init__ ()
        self .navigate =navigate
        self .app =app
        self .settings_service =app .settings_service if app else SettingsService ()
        self .mt5 =app .mt5 if app else MT5Service ()
        self .scanner_controller =app .scanner_controller if app else ScannerController (self .settings_service ,mt5=self .mt5 )
        self .scan_thread =None 
        self .scan_worker =None 
        self .scan_result :dict [str ,object ]|None =None
        self._active_scan_id = ""
        self._market_brief_text = ""
        self .symbol_boxes :list [QCheckBox ]=[]
        self .market_watch_symbols :set [str ]=set ()
        self .scan_symbols :list [str ]=[]
        self .selected_scan_symbols :list [str ]=[]
        self .table_model =ScannerTableModel ()
        self.table_model.set_theme(
            "light" if is_light_theme(self.settings_service) else "dark"
        )
        # Resolve SHORT_REASON_COL dynamically from COLUMNS
        reason_keys =[k for k,_ in self .table_model .COLUMNS]
        self .SHORT_REASON_COL =reason_keys .index ("short_reason")if "short_reason"in reason_keys else -1
        self .auto_scan_active =False
        self .auto_scan_timer =QTimer (self )
        self .auto_scan_timer .setSingleShot (True )
        self .auto_scan_timer .timeout .connect (self ._run_scan )
        self .setObjectName ("FormScreen")
        self ._build_ui ()

    def _build_ui (self )->None :
        root =QVBoxLayout (self )
        root .setContentsMargins (18 ,14 ,18 ,14 )
        root .setSpacing (10 )
        root .addWidget (
        page_header (
        'Quét thị trường',
        "",
        "",
        )
        )

        root .addWidget (self ._settings_card ())
        root .addWidget (self ._table_card (),1 )
        self .refresh_status ()

    def _settings_card (self )->QFrame :
        frame =card (None )
        frame .layout ().setSpacing (4 )
        frame .layout ().setContentsMargins (14 ,8 ,14 ,8 )
        frame .layout ().setAlignment (Qt .AlignmentFlag .AlignTop )
        settings = self.settings_service.load()
        self .scan_symbols =self ._configured_scan_symbols (settings )
        self .selected_scan_symbols =list (self .scan_symbols )


        symbol_row =QHBoxLayout ()
        symbol_row .setSpacing (10 )
        self.symbol_select_button = action_button("🔍 Chọn mã quét", primary=True, color="info")
        self .symbol_select_button .clicked .connect (self ._show_symbol_dialog )
        self .symbol_summary_label =QLabel ("")
        self .symbol_summary_label .setObjectName ("HelperText")
        self .symbol_summary_label .setWordWrap (True )
        symbol_row .addWidget (self .symbol_select_button )
        symbol_row .addWidget (self .symbol_summary_label ,1 )
        frame .layout ().addLayout (symbol_row )

        self .scan_mode_combo =QComboBox ()
        self .scan_mode_combo .addItem ("Quét 1 lần","once")
        self .scan_mode_combo .addItem ("Quét theo khoảng thời gian","auto")
        self .scan_interval_combo =QComboBox ()
        for label ,seconds in [
            ("M5 (theo nến MT5)",300 ),
            ("M15 (theo nến MT5)",900 ),
            ("H1 (theo nến MT5)",3600 ),
            ("H4 (theo nến MT5)",14400 ),
        ]:
            self .scan_interval_combo .addItem (label ,seconds )
        old_to_tf ={1 :300 ,5 :300 ,15 :900 ,30 :900 ,60 :3600 ,240 :14400 ,1440 :14400 }
        tf_seconds =old_to_tf .get (settings .notifications .auto_scan_interval_minutes ,900 )
        interval_index =self .scan_interval_combo .findData (tf_seconds )
        self .scan_interval_combo .setCurrentIndex (interval_index if interval_index >=0 else 1 )
        self .scan_mode_combo .setSizeAdjustPolicy (QComboBox .SizeAdjustPolicy .AdjustToContents )
        self .scan_interval_combo .setSizeAdjustPolicy (QComboBox .SizeAdjustPolicy .AdjustToContents )
        for combo in (self .scan_mode_combo ,self .scan_interval_combo ):
            combo .setSizePolicy (QSizePolicy .Policy .Fixed ,QSizePolicy .Policy .Fixed )
        self.auto_trade_check = QPushButton("🤖 Tự động vào lệnh MT5")
        self.auto_trade_check.setObjectName("AutoTradeToggle")
        self.auto_trade_check.setCheckable(True)
        self.auto_trade_check.setCursor(Qt.CursorShape.ArrowCursor)
        self .auto_trade_check .setToolTip (
            "Chỉ dùng trong chế độ quét theo khoảng thời gian. Khi bật, Scanner "
            "có thể gửi lệnh thật tới MT5; mọi lệnh vẫn phải vượt qua cổng phát "
            "hành và các kiểm tra an toàn."
        )
        self .auto_trade_check .setChecked (False )
        self .auto_trade_check .toggled .connect (self ._update_auto_trade_toggle_style )
        self .scan_mode_combo .currentIndexChanged .connect (self ._on_scan_mode_changed )
        self ._update_auto_trade_toggle_state ()

        self.scan_button = action_button("🔍 Quét thị trường", primary=True, color="info")
        self .scan_button .clicked .connect (self ._run_scan )
        self .stop_auto_scan_button =action_button ("⏹️ Dừng quét tự động",primary =True ,color ="danger")
        self .stop_auto_scan_button .setVisible (False )
        self .stop_auto_scan_button .clicked .connect (self ._stop_auto_scan )

        self.show_orders_button = action_button("📋 Kế hoạch lệnh", primary=True, color="info")
        self.show_orders_button.setToolTip(
            "Xem ứng viên, kết quả kiểm tra và trạng thái gửi lệnh của lần quét gần nhất"
        )
        self.show_orders_button.clicked.connect(self._show_orders_dialog)
        self._dim_show_orders_button()

        self .scan_mode_label =QLabel ("Chế độ")
        self .scan_mode_label .setObjectName ("FormLabel")
        self .scan_interval_label =QLabel ("Khoảng thời gian")
        self .scan_interval_label .setObjectName ("FormLabel")
        compact_controls =(
            self .scan_mode_label ,
            self .scan_interval_label ,
            self .auto_trade_check ,
            self .scan_button ,
            self .stop_auto_scan_button ,
            self .show_orders_button ,
        )
        for control in compact_controls:
            control .setSizePolicy (QSizePolicy .Policy .Fixed ,QSizePolicy .Policy .Fixed )

        scan_options =QHBoxLayout ()
        scan_options .setContentsMargins (0 ,0 ,0 ,0 )
        scan_options .setSpacing (8 )
        scan_options .addWidget (self .scan_mode_label )
        scan_options .addWidget (self .scan_mode_combo )
        scan_options .addWidget (self .scan_interval_label )
        scan_options .addWidget (self .scan_interval_combo )
        scan_options .addWidget (self .auto_trade_check )
        scan_options .addWidget (self .scan_button )
        scan_options .addWidget (self .stop_auto_scan_button )
        scan_options .addWidget (self .show_orders_button )
        scan_options .addStretch (1 )
        self .scan_options_layout =scan_options
        frame .layout ().addLayout (scan_options )

        # ---- Status backing labels (not added to UI, used for summary) ----
        self .status_labels :dict [str ,QLabel ]={}
        for title in ("MT5","Đã quét","AI đã gọi","Telegram","Rollout","Lần quét gần nhất"):
            self .status_labels [title ]=QLabel ("--")
        self .status_summary_label =QLabel ("--")
        self .status_summary_label .setObjectName ("HelperText")
        self .status_summary_label .setWordWrap (True )
        frame .layout ().addWidget (self .status_summary_label )

        self .progress_bar =QProgressBar ()
        self .progress_bar .setObjectName ("AnalysisProgressBar")
        self .progress_bar .setRange (0 ,100 )
        self .progress_bar .setValue (0 )
        self .progress_bar .setTextVisible (True )
        self .progress_bar .setFormat ("%p%")
        self .progress_bar .setFixedHeight (16 )
        self .progress_bar .setVisible (False )

        progress_container =QWidget ()
        progress_container .setObjectName ("ProgressContainer")
        progress_layout =QVBoxLayout (progress_container )
        progress_layout .setContentsMargins (0 ,4 ,0 ,6 )
        progress_layout .setSpacing (0 )
        progress_layout .addWidget (self .progress_bar )
        progress_container .setVisible (False )
        self .progress_container =progress_container
        frame .layout ().addWidget (progress_container )

        self ._update_status_summary ()
        return frame

    def _update_status_summary (self )->None :
        scanned =self .status_labels .get ("Đã quét",QLabel ("--")).text ()
        last =self .status_labels .get ("Lần quét gần nhất",QLabel ("--")).text ()
        self .status_summary_label .setText (
            f"Đã quét: {scanned}  •  Lần quét gần nhất: {last}"
        )

    def _auto_trade_enabled (self )->bool :
        return bool (
            self .AUTO_TRADE_UI_ENABLED
            and hasattr (self ,"scan_mode_combo")
            and hasattr (self ,"auto_trade_check")
            and self .scan_mode_combo .currentData ()=="auto"
            and self .auto_trade_check .isChecked ()
        )

    def _update_auto_trade_toggle_state (self )->None :
        if not hasattr (self ,"auto_trade_check"):
            return
        is_auto_mode =bool (hasattr (self ,"scan_mode_combo")and self .scan_mode_combo .currentData ()=="auto")
        can_enable =bool (self .AUTO_TRADE_UI_ENABLED and is_auto_mode )
        self .auto_trade_check .setEnabled (can_enable )
        if not can_enable and self .auto_trade_check .isChecked ():
            self .auto_trade_check .setChecked (False )
        self ._update_auto_trade_toggle_style ()

    def _on_scan_mode_changed(self) -> None:
        """Keep auto-scan opt-in: changing back to one-shot stops its timer."""
        self._update_auto_trade_toggle_state()
        if (
            self.scan_mode_combo.currentData() != "auto"
            and self.auto_scan_active
        ):
            self._stop_auto_scan()

    # ------------------------------------------------------------------
    # Show Orders button
    # ------------------------------------------------------------------
    def _dim_show_orders_button(self) -> None:
        """Dim the 'Hiển thị lệnh' button to indicate no scan data available."""
        self.show_orders_button.setProperty("btnState", "dimmed")
        self.show_orders_button.style().unpolish(self.show_orders_button)
        self.show_orders_button.style().polish(self.show_orders_button)
        self.show_orders_button.update()

    def _highlight_show_orders_button(self) -> None:
        """Highlight the 'Hiển thị lệnh' button after a scan completes."""
        self.show_orders_button.setProperty("btnState", "highlighted")
        self.show_orders_button.style().unpolish(self.show_orders_button)
        self.show_orders_button.style().polish(self.show_orders_button)
        self.show_orders_button.update()

    def _show_orders_dialog(self) -> None:
        """Show a dialog listing trade orders (actual or would-be)."""
        scan_result = getattr(self, "scan_result", None)
        if not scan_result:
            QMessageBox.information(self, "Hiển thị lệnh",
                "Chưa có kết quả quét.\nHãy quét thị trường trước.")
            return

        rows = list(scan_result.get("rows", []))
        if not rows:
            QMessageBox.information(self, "Hiển thị lệnh",
                "Kết quả quét không có mã nào.")
            return

        light = is_light_theme(self.settings_service)

        auto_results = scan_result.get("auto_trade_results", {})
        if not isinstance(auto_results, dict):
            auto_results = {}
        # Read the request captured by this scan result. The current button
        # state may have changed after the scan and must not rewrite history.
        auto_trade_enabled = auto_results.get("enabled") is True

        order_rows = self._build_order_rows(rows, auto_trade_enabled, auto_results)
        if not order_rows:
            if auto_trade_enabled:
                attempted = int(auto_results.get("attempted", 0) or 0)
                skipped = int(auto_results.get("skipped", 0) or 0)
                rollout_blocked = int(
                    auto_results.get("rollout_blocked", 0) or 0
                )
                message = (
                    "Lần quét này không mở lệnh MT5 nào.\n"
                    f"Đã kiểm tra: {attempted} • Bỏ qua: {skipped} • "
                    f"Bị rollout chặn: {rollout_blocked}.\n"
                    "Xem trạng thái và lý do của từng cặp trong bảng kết quả."
                )
            else:
                message = (
                    "Lần quét này không có ứng viên nào đủ dữ liệu để lập "
                    "kế hoạch lệnh.\nXem cột Trạng thái và bấm Giải thích để "
                    "biết điều kiện còn thiếu."
                )
            QMessageBox.information(self, "Kế hoạch lệnh", message)
            return

        # Build dialog
        dlg = QDialog(self)
        rollout_policy = (
            scan_result.get("rollout_policy")
            if isinstance(scan_result.get("rollout_policy"), dict)
            else {}
        )
        rollout_stage = str(
            rollout_policy.get("stage", "") or ""
        ).upper()
        opened = int(auto_results.get("opened", 0) or 0)
        attempted = int(auto_results.get("attempted", 0) or 0)
        skipped = int(auto_results.get("skipped", 0) or 0)
        rollout_blocked = int(auto_results.get("rollout_blocked", 0) or 0)
        title_text = (
            "Kết quả vào lệnh tự động"
            if auto_trade_enabled
            else "Kế hoạch lệnh có thể xem xét"
        )
        dlg.setWindowTitle(f"📋 {title_text}")
        dlg.setMinimumSize(940, 560)
        dlg.resize(980, 620)
        dlg.setObjectName("AnalysisDetailDialog")
        dlg.setProperty("scannerOrderDialog", True)

        # Action button helper for manual trade execution
        def execute_manual_order(order_info: dict, btn: QPushButton) -> None:
            btn.setEnabled(False)
            btn.setText("Đang đặt...")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

            # Manual and automatic orders share the same Phase-3 realtime
            # revalidation path.  The controller recalculates volume from the
            # live bid/ask and returns structured block codes on failure.
            try:
                execution = self.scanner_controller.execute_order_candidate(
                    order_info,
                    comment=f"AMA Manual {order_info.get('symbol') or '--'}",
                    manual_release_gate_override=True,
                )
            except Exception as exc:
                execution = {
                    "success": False,
                    "message": str(exc),
                    "revalidation": {
                        "allowed": False,
                        "block_codes": ["EXECUTION_REVALIDATION_FAILED"],
                    },
                }

            if execution.get("success"):
                QMessageBox.information(
                    dlg,
                    "Thành công",
                    (
                        f"Đặt lệnh {str(execution.get('side') or '').upper()} "
                        f"{execution.get('symbol') or '--'} thành công!\n"
                        f"ID: {execution.get('order_id') or '--'}"
                    ),
                )
                btn.setText("Đã vào lệnh")
                btn.setEnabled(False)
            else:
                validation = execution.get("revalidation")
                block_codes = (
                    validation.get("block_codes", [])
                    if isinstance(validation, dict)
                    else []
                )
                portfolio = execution.get("portfolio_guard")
                portfolio_codes = (
                    portfolio.get("block_codes", [])
                    if isinstance(portfolio, dict)
                    else []
                )
                detail = ", ".join(
                    dict.fromkeys(
                        str(code)
                        for code in (*block_codes, *portfolio_codes)
                    )
                )
                user_reasons = self._user_facing_block_reasons(
                    [*block_codes, *portfolio_codes]
                )
                reason_text = (
                    "\n\nLý do:\n- " + "\n- ".join(user_reasons)
                    if user_reasons
                    else ""
                )
                QMessageBox.warning(
                    dlg,
                    "Không thể vào lệnh",
                    (
                        "Lệnh chưa được gửi tới MT5 vì chưa vượt qua đầy đủ "
                        "các bước kiểm tra."
                        + reason_text
                        + (f"\n\nMã kỹ thuật: {detail}" if detail else "")
                    ),
                )
                btn.setEnabled(True)
                btn.setText("⚡ Thử lại")
            return

        def create_order_button(row_order: dict) -> QWidget:
            btn_container = QWidget()
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(0)
            
            btn = action_button("⚡ Vào lệnh", primary=True)
            btn.setProperty("manualOrder", True)
            
            broker_symbol = row_order.get("broker_symbol")
            has_existing = False
            if broker_symbol:
                try:
                    if self.mt5.has_open_position_or_order(broker_symbol):
                        has_existing = True
                except Exception:
                    pass
            
            if has_existing:
                btn.setText("Đã có lệnh")
                btn.setEnabled(False)
                
            btn.clicked.connect(lambda: execute_manual_order(row_order, btn))
            btn_layout.addWidget(btn)
            return btn_container

        root = QVBoxLayout(dlg)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Beautiful Header Card
        header_frame = QFrame()
        header_frame.setObjectName("PanelCard")
        set_dynamic_property(
            header_frame,
            "headerTone",
            "success" if auto_trade_enabled and opened > 0 else "warning",
        )
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(4)

        title_label = QLabel(f"📋 {title_text}")
        title_label.setObjectName("OrderDialogTitle")
        
        subtitle_text = (
            (
                f"Đã mở {opened}/{attempted} lệnh MT5 • Bỏ qua {skipped} • "
                f"Rollout chặn {rollout_blocked} • Stage {rollout_stage or '--'}. "
                "Các dòng bên dưới là kết quả xử lý, không mặc định là lệnh đã khớp."
            )
            if auto_trade_enabled
            else (
                f"{len(order_rows)} ứng viên có kế hoạch lệnh từ lần quét gần nhất. "
                "Đây chưa phải lệnh đã gửi tới MT5; bấm Vào lệnh để hệ thống "
                "kiểm tra lại toàn bộ điều kiện theo giá mới."
            )
        )
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("OrderDialogSubtitle")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle)
        root.addWidget(header_frame)


        # Table
        table = QTableWidget()
        configure_table(table)
        columns = ["STT", "Mã", "Hướng", "Entry", "SL", "TP", "KL", "R:R", "Ghi chú"]
        if not auto_trade_enabled:
            columns.append("Thao tác")
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        
        table.setColumnWidth(0, 45)
        table.setColumnWidth(1, 80)
        table.setColumnWidth(2, 85)
        table.setColumnWidth(3, 90)
        table.setColumnWidth(4, 90)
        table.setColumnWidth(5, 90)
        table.setColumnWidth(6, 70)
        table.setColumnWidth(7, 70)

        if not auto_trade_enabled:
            header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(9, 120)
        else:
            header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

        table.setRowCount(len(order_rows))

        palette = current_palette(self.settings_service)
        buy_color = QColor(palette.buy)
        sell_color = QColor(palette.sell)
        neutral_fg = QColor(palette.text_muted)

        def create_direction_pill(direction: str, light_theme: bool) -> QWidget:
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(0)
            label = QLabel()
            label.setObjectName("OrderDirectionPill")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if direction == "buy":
                label.setText(" MUA ")
                set_dynamic_property(label, "direction", "buy")
            elif direction == "sell":
                label.setText(" BÁN ")
                set_dynamic_property(label, "direction", "sell")
            else:
                label.setText(" -- ")
                set_dynamic_property(label, "direction", "neutral")
            layout.addWidget(label)
            return container

        for idx, order in enumerate(order_rows):
            direction = str(order.get("side", "")).lower()
            price_digits = order.get("price_digits")
            if not isinstance(price_digits, int):
                normalized_symbol = "".join(
                    c for c in str(order.get("symbol", "")).upper() if c.isalpha()
                )
                price_digits = 3 if normalized_symbol.endswith("JPY") else 5

            def styled_item(text: str, align=Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setTextAlignment(align)
                return item

            # STT
            stt_item = styled_item(str(idx + 1))
            stt_item.setForeground(neutral_fg)
            table.setItem(idx, 0, stt_item)

            # Symbol
            sym_item = styled_item(str(order.get("symbol", "--")))
            symbol_font = get_body_font()
            symbol_font.setBold(True)
            sym_item.setFont(symbol_font)
            table.setItem(idx, 1, sym_item)

            # Direction pill
            table.setCellWidget(idx, 2, create_direction_pill(direction, light))

            # Entry
            entry = order.get("entry_price")
            entry_text = f"{float(entry):.{price_digits}f}" if entry is not None else "--"
            entry_item = styled_item(entry_text)
            entry_tip = format_order_entry_tooltip(order)
            if entry_tip:
                entry_item.setToolTip(entry_tip)
            table.setItem(idx, 3, entry_item)

            # SL
            sl = order.get("stop_loss")
            sl_text = f"{float(sl):.{price_digits}f}" if sl is not None else "--"
            sl_item = styled_item(sl_text)
            sl_item.setForeground(sell_color)
            table.setItem(idx, 4, sl_item)

            # TP
            tp = order.get("take_profit")
            tp_text = f"{float(tp):.{price_digits}f}" if tp is not None else "--"
            tp_item = styled_item(tp_text)
            tp_item.setForeground(buy_color)
            table.setItem(idx, 5, tp_item)

            # Volume
            vol = order.get("volume")
            vol_text = f"{float(vol):.2f}" if vol is not None else "--"
            table.setItem(idx, 6, styled_item(vol_text))

            # R:R — show range if available: "5.6 (2.9–5.6)"
            rr_text = format_order_rr_text(order)
            rr_item = styled_item(rr_text)
            rr_tooltip = format_order_rr_tooltip(order)
            if rr_tooltip:
                rr_item.setToolTip(rr_tooltip)
            table.setItem(idx, 7, rr_item)

            # Note — with current RR diagnostic (Phase 9 shared formatter)
            note = enrich_order_note_with_current_rr(order)
            note_item = QTableWidgetItem(note if note else "--")
            note_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if note:
                note_lower = note.lower()
                if "lỗi" in note_lower or "từ chối" in note_lower or "fail" in note_lower or "error" in note_lower:
                    note_item.setForeground(sell_color)
                elif "thành công" in note_lower or "success" in note_lower or "ok" in note_lower:
                    note_item.setForeground(buy_color)
                else:
                    note_item.setForeground(neutral_fg)
            else:
                note_item.setForeground(neutral_fg)
            table.setItem(idx, 8, note_item)

            if not auto_trade_enabled:
                table.setCellWidget(idx, 9, create_order_button(order))

        root.addWidget(table, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        close_btn = action_button("❌ Đóng", primary=False, color="danger")
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)
        root.addLayout(btn_layout)

        dlg.exec()

    def _build_order_rows(
        self,
        rows: list[dict],
        auto_trade_enabled: bool,
        auto_results: dict,
    ) -> list[dict]:
        """Build a list of order dicts from scanner rows."""
        if auto_trade_enabled:
            orders = auto_results.get("orders", [])
            if not isinstance(orders, list):
                return []
            result: list[dict] = []
            for o in orders:
                if not isinstance(o, dict):
                    continue
                result.append({
                    "symbol": str(o.get("symbol", o.get("broker_symbol", "--"))),
                    "broker_symbol": str(o.get("broker_symbol", "")),
                    "side": str(o.get("side", "")),
                    "entry_price": o.get("entry_price") or o.get("price"),
                    "stop_loss": o.get("stop_loss") or o.get("sl"),
                    "take_profit": o.get("take_profit") or o.get("tp"),
                    "volume": o.get("volume"),
                    "risk_reward": o.get("risk_reward", ""),
                    "risk_reward_range": o.get("risk_reward_range"),
                    "entry_zone": o.get("entry_zone"),
                    "source_zone": o.get("source_zone"),
                    "structural_execution_zone": o.get("structural_execution_zone"),
                    "rr_trimmed": o.get("rr_trimmed", False),
                    "rr_trim_diagnostics": o.get("rr_trim_diagnostics"),
                    "entry_zone_width": o.get("entry_zone_width"),
                    "entry_zone_width_atr": o.get("entry_zone_width_atr"),
                    "price_digits": o.get("price_digits"),
                    "expected_effective_rr_base": o.get("expected_effective_rr_base"),
                    "note": str(o.get("message", o.get("status", ""))),
                })
            return result

        # Reuse the candidate payload captured by the backend scan decision.
        result: list[dict] = []
        for row in rows:
            stored = row.get("candidate_order_payload")
            if not isinstance(stored, dict):
                continue
            payload = dict(stored)
            payload.update({
                "rank": row.get("rank"),
                "candidate_status": row.get("candidate_status"),
                "opportunity_rank": row.get("opportunity_rank"),
                "evidence_confidence": row.get("evidence_confidence"),
                "execution_readiness": row.get("execution_readiness"),
                "strategy_branch": row.get("auto_trade_branch"),
                "config_health": row.get("strategy_config_status"),
                "ranking_version": row.get("ranking_version"),
                "note": ScannerTableModel.STATUS_TEXT.get(
                    str(row.get("candidate_status", "") or "").upper(),
                    str(row.get("candidate_status", "") or ""),
                ),
            })
            result.append(payload)

        return result

    @staticmethod
    def _user_facing_block_reasons(codes: list[object]) -> list[str]:
        rollout_messages = {
            "RELEASE_GATE_NOT_READY": (
                "Cổng phát hành chưa đạt; hệ thống còn thiếu bằng chứng "
                "vận hành bắt buộc."
            ),
            "PRODUCTION_APPROVAL_REQUIRED": (
                "Chưa có phê duyệt cho giao dịch production."
            ),
            "SHADOW_MODE_ORDER_SUPPRESSED": (
                "Hệ thống đang ở chế độ chỉ quan sát, không gửi lệnh."
            ),
            "ROLLOUT_KILL_SWITCH_ACTIVE": (
                "Công tắc dừng khẩn cấp đang được bật."
            ),
            "DEMO_ACCOUNT_REQUIRED": (
                "Giai đoạn hiện tại chỉ cho phép tài khoản demo."
            ),
            "CANARY_GATE_NOT_READY": (
                "Giai đoạn canary chưa đủ điều kiện để gửi lệnh."
            ),
            "SYMBOL_NOT_IN_LIMITED_ROLLOUT": (
                "Cặp này chưa nằm trong danh sách được phép ở giai đoạn giới hạn."
            ),
            "USER_AUTO_TRADE_DISABLED": (
                "Người dùng chưa bật tự động vào lệnh cho lần quét này."
            ),
        }
        normalized: list[str] = []
        for value in codes:
            code = str(value or "").strip()
            if code and code not in normalized:
                normalized.append(code)
        translated = codes_to_messages(normalized)
        messages: list[str] = []
        for code, generic in zip(normalized, translated):
            message = rollout_messages.get(code)
            if message is None and generic != code:
                message = generic
            if message is None:
                message = f"Một điều kiện an toàn chưa đạt ({code})."
            if message not in messages:
                messages.append(message)
        return messages

    def _update_auto_trade_toggle_style (self )->None :
        if not hasattr (self ,"auto_trade_check"):
            return
        active =self ._auto_trade_enabled ()
        self .auto_trade_check .setProperty ("autoTradeActive",active )
        self .auto_trade_check .style ().unpolish (self .auto_trade_check )
        self .auto_trade_check .style ().polish (self .auto_trade_check )
        self .auto_trade_check .update ()

    def _table_card (self )->QFrame :
        frame =card ('Bảng kết quả quét')
        title_row =frame .layout ().itemAt (0 ).widget ()
        if isinstance (title_row ,QLabel ):
            frame .layout ().removeWidget (title_row )
            title_row .deleteLater ()
            header =QWidget ()
            header_layout =QHBoxLayout (header )
            header_layout .setContentsMargins (0 ,0 ,0 ,0 )
            header_layout .setSpacing (8 )
            header_label =QLabel ('Bảng kết quả quét')
            header_label .setObjectName ("PanelTitle")
            header_layout .addWidget (header_label )
            self.help_button = action_button("❓ Giải thích", primary=True, color="info")
            self .help_button .setToolTip ('Xem giải thích các thông số trong bảng')
            self .help_button .clicked .connect (self ._show_columns_help )
            header_layout .addWidget (self .help_button )
            header_layout .addStretch (1 )
            self .detail_button =action_button ('🔍 Xem chi tiết',primary =True )
            self .detail_button .setEnabled (False )
            self .detail_button .clicked .connect (self ._open_selected_detail )
            self .save_button =action_button ('📸 Lưu snapshot',primary =True ,color ="success")
            self .save_button .setEnabled (False )
            self .save_button .clicked .connect (self ._save_snapshot )
            self .brief_button = action_button ('📊 Bản tin thị trường', primary=True, color="warning")
            self.brief_button.setToolTip("Xem bản tin thị trường do AI tổng hợp từ kết quả quét.")
            self .brief_button .clicked .connect (self ._show_market_brief )
            header_layout .addWidget (self .detail_button )
            header_layout .addWidget (self .save_button )
            header_layout .addWidget (self .brief_button )
            frame .layout ().insertWidget (0 ,header )

        self .table =QTableView ()
        configure_table(self.table)
        self .table .setModel (self .table_model )
        self .table .setSelectionBehavior (QTableView .SelectionBehavior .SelectRows )
        self .table .setSelectionMode (QTableView .SelectionMode .SingleSelection )
        self .table .horizontalHeader ().setStretchLastSection (False )
        self .table .setHorizontalScrollBarPolicy (Qt .ScrollBarPolicy .ScrollBarAsNeeded )
        self .table .setHorizontalScrollMode (QTableView .ScrollMode .ScrollPerPixel )
        self .table .setVerticalScrollBarPolicy (Qt .ScrollBarPolicy .ScrollBarAlwaysOn )
        self .table .viewport ().installEventFilter (self )
        self ._configure_table_columns ()
        self .table .setSortingEnabled (False )
        self .table .clicked .connect (self ._table_clicked )
        self .table .doubleClicked .connect (self ._table_double_clicked )
        frame .layout ().addWidget (self .table ,1 )
        return frame 

    def _show_columns_help (self )->None :
        row = ScannerScreen._selected_scanner_row(self)
        if row is None:
            dialog = ScannerColumnsHelpDialog(self)
        else:
            dialog = ScannerRowExplanationDialog(
                row,
                self.table_model,
                self,
            )
        dialog .exec ()

    def _selected_scanner_row(self) -> dict[str, object] | None:
        """Return the selected result row, or ``None`` when selection is empty."""

        table = getattr(self, "table", None)
        table_model = getattr(self, "table_model", None)
        if table is None or table_model is None:
            return None
        selection_model = table.selectionModel()
        if selection_model is None:
            return None
        selected = selection_model.selectedRows()
        if not selected:
            return None
        index = selected[0]
        if not index.isValid():
            return None
        row = table_model.row_at(index.row())
        return row if isinstance(row, dict) else None

    def refresh_status (self )->None :
        status =self .mt5 .connection_status ()
        self .status_labels ["MT5"].setText ('Đã kết nối'if status .connected and status .logged_in else 'Chưa kết nối đầy đủ')
        self ._refresh_symbol_availability (status )
        self ._refresh_scan_button_state ()
        self ._update_status_summary ()

    def _selected_symbols (self )->list [str ]:
        allowed =set (self .scan_symbols )&self .market_watch_symbols
        return [symbol for symbol in self .selected_scan_symbols if symbol in allowed]

    def _refresh_symbol_availability (self ,status )->None :
        matches =self .mt5 .configured_symbols_in_market_watch ()if status .connected else []
        self .market_watch_symbols ={symbol for symbol ,_broker_symbol in matches }
        settings =self .settings_service .load ()
        self .scan_symbols =self ._configured_scan_symbols (settings )
        if not self .selected_scan_symbols:
            self .selected_scan_symbols =[symbol for symbol in self .scan_symbols if symbol in self .market_watch_symbols]
        else:
            self .selected_scan_symbols =[symbol for symbol in self .selected_scan_symbols if symbol in self .scan_symbols]
        self ._update_symbol_summary ()
        self ._refresh_scan_button_state ()

    def _configured_scan_symbols (self ,settings )->list [str ]:
        return [
            symbol for symbol in SUPPORTED_SYMBOLS
            if settings .trading .symbol_settings .get (symbol)
        ]

    def _update_symbol_summary (self )->None :
        if not hasattr (self ,"symbol_summary_label"):
            return
        selected =self ._selected_symbols ()
        if not self .scan_symbols:
            self .symbol_summary_label .setText ("Chưa có mã nào được cấu hình trong Cài đặt.")
        elif not selected:
            self .symbol_summary_label .setText ("Chưa chọn mã khả dụng để quét.")
        elif len (selected )<=5:
            self .symbol_summary_label .setText (", ".join (selected ))
        else:
            self .symbol_summary_label .setText (f"{len (selected )} mã: {', '.join (selected [:5])}, ...")

    def _show_symbol_dialog (self )->None :
        backtest_verified =set (self .scan_symbols )
        dialog =ScannerSymbolSelectionDialog (
            sorted (SUPPORTED_SYMBOLS ),
            backtest_verified,
            self .market_watch_symbols,
            self .selected_scan_symbols,
            self,
        )
        if dialog .exec ()==QDialog .DialogCode .Accepted:
            self .selected_scan_symbols =dialog .selected_symbols ()
            self ._update_symbol_summary ()
            self ._refresh_scan_button_state ()

    def _toggle_all_symbols (self ,checked :bool )->None :
        self .selected_scan_symbols =[
            symbol for symbol in self .scan_symbols if checked and symbol in self .market_watch_symbols
        ]
        self ._update_symbol_summary ()
        self ._refresh_scan_button_state ()

    def _sync_all_symbols_check (self )->None :
        self ._update_symbol_summary ()
        self ._refresh_scan_button_state ()

    def _refresh_scan_button_state (self )->None :
        if hasattr (self ,"scan_button"):
            self .scan_button .setEnabled (bool (self ._selected_symbols ())and self .scan_thread is None )
        if hasattr (self ,"stop_auto_scan_button"):
            self .stop_auto_scan_button .setVisible (self .auto_scan_active )

    def _run_scan (self )->None :
        if self .scan_thread is not None :
            return 
        symbols =self ._selected_symbols ()
        if not symbols :
            QMessageBox .warning (self ,'Không thể quét','Chọn ít nhất một mã giao dịch trước khi quét.')
            return 
        if hasattr (self ,"scan_mode_combo")and self .scan_mode_combo .currentData ()=="auto":
            self .auto_scan_active =True
            self .stop_auto_scan_button .setVisible (True )
        self .scan_button .setEnabled (False )
        self .scan_button .setText ('Đang quét...')
        self .detail_button .setEnabled (False )
        self .save_button .setEnabled (False )
        self ._dim_show_orders_button ()
        self .progress_bar .setValue (0 )
        self .progress_bar .setVisible (True )
        self .progress_container .setVisible (True )
        self .status_labels ['Đã quét'].setText (f"0 / {len (symbols )}")
        self ._update_status_summary ()
        settings =self .settings_service .load ()
        auto_trade_enabled =self ._auto_trade_enabled ()
        min_scores ={
            symbol:int (settings .trading .symbol_settings .get (symbol).min_score )
            for symbol in symbols
            if settings .trading .symbol_settings .get (symbol)
        }
        thresholds: dict[str, dict[str, int]] = {}
        for symbol in symbols:
            # Settings store symbol as 'USD/CAD', but scan uses 'USDCAD'
            cfg = settings.trading.symbol_settings.get(symbol)
            if cfg is None:
                # Try with slash: 'USDCAD' -> 'USD/CAD'
                slash_symbol = f"{symbol[:3]}/{symbol[3:]}"
                cfg = settings.trading.symbol_settings.get(slash_symbol)
            symbol_thresholds = analysis_thresholds_for_symbol(cfg)
            if symbol_thresholds is not None:
                thresholds[symbol] = symbol_thresholds
            # else: khong config -> DEFAULT_DECISION_THRESHOLDS (65/60/55)
        symbol_auto_trade: dict[str, dict] = {}
        for symbol in symbols:
            cfg = settings.trading.symbol_settings.get(symbol)
            if cfg is None:
                slash_symbol = f"{symbol[:3]}/{symbol[3:]}"
                cfg = settings.trading.symbol_settings.get(slash_symbol)
            backtest_config = serialize_backtest_config(cfg, symbol=symbol)
            if backtest_config is not None:
                symbol_auto_trade[symbol] = backtest_config
        feature_settings = getattr(settings, "features", None)
        feature_flags = {
            "scanner_architecture_v2": bool(
                getattr(feature_settings, "scanner_architecture_v2", False)
            ),
            "auto_trade_v2": bool(
                getattr(feature_settings, "auto_trade_v2", False)
            ),
            "scanner_fast_tier1": bool(
                getattr(feature_settings, "scanner_fast_tier1", False)
            ),
            "scanner_fast_tier2": bool(
                getattr(feature_settings, "scanner_fast_tier2", False)
            ),
            "scanner_mt5_history_cache": bool(
                getattr(feature_settings, "scanner_mt5_history_cache", False)
            ),
            "scanner_core_result_early": bool(
                getattr(feature_settings, "scanner_core_result_early", False)
            ),
        }
        request =ScannerRequest (
        symbols =symbols ,
        account_balance =settings .trading .account_balance ,
        risk_percent =settings .trading .default_risk_percent ,
        timezone_name =settings .display .timezone ,
        max_ai_details =settings .advanced .scanner_ai_detail_limit ,
        auto_trade_enabled =auto_trade_enabled ,
        min_scores =min_scores ,
        symbol_auto_trade =symbol_auto_trade ,
        thresholds =thresholds ,
        feature_flags =feature_flags ,
        persistence_mode =("summary" if hasattr (self ,"scan_mode_combo")and self .scan_mode_combo .currentData ()=="auto" else "full"),
        )
        thread ,worker =self .scanner_controller .create_scan_worker (request )
        self .scan_thread =thread
        self .scan_worker =worker
        worker .progress .connect (self ._scan_progress )
        if worker .split_aftercare :
            worker .core_succeeded .connect (self ._scan_core_finished )
            worker .aftercare_progress .connect (self ._scan_aftercare_progress )
            worker .aftercare_succeeded .connect (self ._scan_aftercare_finished )
        else :
            worker .succeeded .connect (self ._scan_finished )
        worker .failed .connect (self ._scan_failed )
        thread .finished .connect (self ._scan_thread_finished )
        thread .start ()

    def _stop_auto_scan (self )->None :
        self .auto_scan_active =False
        self .auto_scan_timer .stop ()
        if hasattr (self ,"stop_auto_scan_button"):
            self .stop_auto_scan_button .setVisible (False )
        if self .scan_thread is None :
            self ._refresh_scan_button_state ()

    def _selected_timeframe_seconds (self )->int :
        if not hasattr (self ,"scan_interval_combo"):
            return 900
        try :
            return int (self .scan_interval_combo .currentData ()or 900 )
        except (TypeError ,ValueError ):
            return 900

    def _compute_next_candle_delay_ms (self ,timeframe_seconds :int )->int :
        server_time =self .mt5 .server_time_utc ()
        if server_time is None :
            return timeframe_seconds *1000
        now_ms =int (server_time .timestamp ()*1000 )
        tf_ms =timeframe_seconds *1000
        ms_to_next =tf_ms -(now_ms %tf_ms )
        return ms_to_next +3000

    def _schedule_next_auto_scan (self )->None :
        if not self .auto_scan_active or self .scan_thread is not None :
            return
        tf_seconds =self ._selected_timeframe_seconds ()
        delay_ms =self ._compute_next_candle_delay_ms (tf_seconds )
        self .auto_scan_timer .start (delay_ms )

    def _scan_progress (self ,percent :int ,message :str )->None :
        if not self .progress_bar .isVisible ():
            self .progress_bar .setVisible (True )
            self .progress_container .setVisible (True )
        self .progress_bar .setValue (percent )
        self .scan_button .setText (message )

    def _scan_finished (self ,result :dict [str ,object ])->None :
        self ._active_scan_id =str (result .get ("scan_id","")or "")
        self .scan_result =result
        self ._render_scan_table (result )
        self ._apply_scan_status (result )
        self ._apply_market_brief (result )
        self .progress_bar .setValue (100 )
        self .progress_bar .setVisible (False )
        self .progress_container .setVisible (False )
        self ._configure_table_columns ()

    def _scan_core_finished (self ,result :dict [str ,object ])->None :
        """Core analysis is done: render the table now; aftercare is pending."""
        self ._active_scan_id =str (result .get ("scan_id","")or "")
        self .scan_result =result
        self ._render_scan_table (result )
        self.status_labels["AI đã gọi"].setText("Đang tạo bản tin...")
        if "Telegram" in self.status_labels:
            self.status_labels["Telegram"].setText("Đang gửi...")
        if "Rollout" in self.status_labels:
            self.status_labels["Rollout"].setText("Đang ghi nhận...")
        self .status_labels ['Lần quét gần nhất'].setText (str (result .get ("timestamp","--")).replace ("T"," ")[:19 ])
        self ._update_status_summary ()
        self .progress_bar .setValue (96 )
        self .scan_button .setText ("Đang gửi/lưu kết quả...")

    def _scan_aftercare_finished (self ,delta :dict [str ,object ])->None :
        """Merge the aftercare delta into the core result on the GUI thread.

        A stale delta (scan_id mismatch) is dropped so it can never overwrite a
        newer scan.
        """
        if str (delta .get ("scan_id","")or "")!=self ._active_scan_id :
            return
        base =self .scan_result if isinstance (self .scan_result ,dict )else {}
        merged :dict [str ,object ]={**base ,**delta }
        self .scan_result =merged
        self ._apply_scan_status (merged )
        self ._apply_market_brief (merged )
        self .progress_bar .setValue (100 )
        self .progress_bar .setVisible (False )
        self .progress_container .setVisible (False )
        self ._configure_table_columns ()

    def _scan_aftercare_progress (self ,percent :int ,message :str )->None :
        self .progress_bar .setValue (percent )
        self .scan_button .setText (message )

    def _render_scan_table (self ,result :dict [str ,object ])->None :
        execution_rows =list (result .get ("rows",[]))
        # Presentation order for the UI table only.
        # Backend execution order is preserved in self.scan_result.
        presentation_rows =sort_scanner_rows_for_display (execution_rows )
        self .table_model .set_rows (presentation_rows )
        self .status_labels ['Đã quét'].setText (f"{result .get ('symbols_scanned',0 )} / {len (self ._selected_symbols ())}")
        self .detail_button .setEnabled (bool (execution_rows ))
        self .save_button .setEnabled (bool (execution_rows ))
        self ._highlight_show_orders_button ()

    def _apply_scan_status (self ,result :dict [str ,object ])->None :
        self.status_labels["AI đã gọi"].setText(f"{result.get('ai_called', 0)} mã")
        alerts =result .get ("telegram_alerts",{})if isinstance (result .get ("telegram_alerts",{}),dict )else {}
        sent =alerts .get ("sent",0 )
        errors =alerts .get ("errors",[])
        telegram_text =f"{sent} alert"
        if errors :
            telegram_text =f"{sent} alert, {len (errors )} lỗi"
        if "Telegram"in self .status_labels :
            self .status_labels ["Telegram"].setText (telegram_text )
        rollout_policy = (
            result.get("rollout_policy")
            if isinstance(result.get("rollout_policy"), dict)
            else {}
        )
        readiness = (
            result.get("release_readiness")
            if isinstance(result.get("release_readiness"), dict)
            else {}
        )
        rollout_text = str(rollout_policy.get("stage", "--") or "--")
        rollout_text += (
            ", cổng phát hành đạt"
            if readiness.get("ready") is True
            else ", cổng phát hành chưa đạt"
        )
        if "Rollout" in self.status_labels:
            self.status_labels["Rollout"].setText(rollout_text)
        if sent :
            self .scan_button .setText (f"Đã gửi {sent} alert Telegram")
        self .status_labels ['Lần quét gần nhất'].setText (str (result .get ("timestamp","--")).replace ("T"," ")[:19 ])
        self ._update_status_summary ()

    def _apply_market_brief (self ,result :dict [str ,object ])->None :
        market_brief = str(result.get("market_brief", "")).strip()
        if market_brief:
            self._market_brief_text = market_brief
        else:
            self._market_brief_text = ""
            err = str(result.get("market_brief_error", ""))
            if err:
                self._market_brief_text = f"Lỗi tạo bản tin: {err}"

    def _scan_failed (self ,message :str )->None :
        self .progress_bar .setVisible (False )
        self .progress_container .setVisible (False )
        QMessageBox .warning (self ,'Không thể quét thị trường',message )

    def _scan_thread_finished (self )->None :
        self.scan_button.setText("🔍 Quét thị trường")
        self ._active_scan_id =""
        self .scan_thread =None
        self .scan_worker =None
        self ._refresh_scan_button_state ()
        self .progress_bar .setVisible (False )
        self .progress_container .setVisible (False )
        self .refresh_status ()
        self ._schedule_next_auto_scan ()

    def _table_clicked (self ,index :QModelIndex )->None :
        self .detail_button .setEnabled (index .isValid ())
        if hasattr(self, "help_button"):
            symbol = ""
            row = self.table_model.row_at(index.row()) if index.isValid() else None
            if isinstance(row, dict):
                symbol = str(row.get("symbol") or "")
            self.help_button.setToolTip(
                f"Giải thích chi tiết các thông số của {symbol}"
                if symbol
                else "Xem giải thích các thông số trong bảng"
            )
    def _table_double_clicked (self ,index :QModelIndex )->None :
        if index .isValid ():
            self ._open_row_detail (index .row ())

    def _open_selected_detail (self )->None :
        selected =self .table .selectionModel ().selectedRows ()
        if selected :
            self ._open_row_detail (selected [0 ].row ())

    def _open_row_detail (self ,row_index :int )->None :
        row =self .table_model .row_at (row_index )
        if not row or not self .navigate :
            return
        self .navigate ("scanner_detail",{"scanner_row":row ,"scanner_result":self .scan_result or {}})

    def _show_market_brief(self) -> None:
        """Open a dialog displaying the AI-generated market brief."""
        try:
            self._show_market_brief_impl()
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi hiển thị", f"Không thể hiển thị bản tin:\n{exc}")

    def _show_market_brief_impl(self) -> None:
        from html import escape
        from PyQt6.QtWidgets import QApplication, QScrollArea, QFrame

        if not getattr(self, "_market_brief_text", ""):
            QMessageBox.information(self, "Bản tin thị trường",
                "Chưa có dữ liệu bản tin.\nCần quét thị trường và bật AI để tạo bản tin.")
            return

        light = is_light_theme(self.settings_service)

        dlg = QDialog(self)
        dlg.setObjectName("MarketBriefDialog")
        dlg.setWindowTitle("Bản tin thị trường")
        dlg.setMinimumSize(850, 650)
            
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Header Section
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        
        title = QLabel("📊 BẢN TIN THỊ TRƯỜNG")
        title.setObjectName("MarketBriefTitle")
        header_layout.addWidget(title)

        timestamp = str(self.scan_result.get("timestamp", "") if self.scan_result else "")
        ts_text = f"Thời gian quét: {timestamp.replace('T', ' ')[:19]}" if timestamp else "Bản tin tổng hợp từ AI"
        ts_label = QLabel(ts_text)
        ts_label.setObjectName("MarketBriefTimestamp")
        header_layout.addWidget(ts_label)
        layout.addLayout(header_layout)

        # Content Container (Outer Frame)
        container_frame = QFrame()
        container_frame.setObjectName("MarketBriefContainer")
            
        container_layout = QVBoxLayout(container_frame)
        container_layout.setContentsMargins(4, 4, 4, 4)
        
        # Scroll Area
        scroll = QScrollArea()
        scroll.setObjectName("MarketBriefScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setObjectName("MarketBriefViewport")
        
        scroll_content = QWidget()
        scroll_content.setObjectName("MarketBriefScrollContent")
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(12, 12, 12, 12)
        scroll_content_layout.setSpacing(12)
        
        # Parse the brief text into sections
        sections = parse_market_brief(self._market_brief_text)
        
        for sec in sections:
            card = QFrame()
            card.setObjectName("MarketBriefSectionCard")
                
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(8)
            
            # Section Header (Icon + Title)
            sec_title = QLabel(f"{sec['icon']}  {sec['title'].upper()}")
            sec_title.setObjectName("MarketBriefSectionTitle")
            card_layout.addWidget(sec_title)
            
            # Section Body Content
            sec_content = QLabel()
            sec_content.setObjectName("MarketBriefSectionContent")
            sec_content.setWordWrap(True)
            sec_content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            
            formatted_html = _format_section_content_to_html(sec['content'], light=light)
            sec_content.setText(formatted_html)
            
            card_layout.addWidget(sec_content)
            scroll_content_layout.addWidget(card)
            
        scroll_content_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        container_layout.addWidget(scroll)
        layout.addWidget(container_frame, 1)

        # Buttons Row
        btn_row = QHBoxLayout()
        copy_btn = action_button("📋 Sao chép", color="info")
        copy_btn.clicked.connect(
            lambda: (QApplication.clipboard().setText(self._market_brief_text),
                     QMessageBox.information(dlg, "Đã sao chép", "Đã sao chép bản tin vào clipboard."))
        )
        close_btn = action_button("❌ Đóng")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        
        dlg.exec()

    def _save_snapshot (self )->None :
        if not self .scan_result :
            return 
        path =self .scanner_controller .save_snapshot (self .scan_result )
        QMessageBox.information(self, "Đã lưu snapshot", f"Đã lưu kết quả quét vào:\n{path}")

    def resizeEvent (self ,event )->None :
        super ().resizeEvent (event )
        compact =self .width ()<1280 
        for index ,box in enumerate (self .symbol_boxes ):
            box .setMinimumWidth (68 if compact else 76 )
        if hasattr (self ,"table"):
            self ._configure_table_columns ()
            QTimer .singleShot (0 ,self ._configure_table_columns )

    def eventFilter (self ,obj ,event )->bool :
        if hasattr (self ,"table")and obj is self .table .viewport ()and event .type ()==QEvent .Type .Resize :
            QTimer .singleShot (0 ,self ._configure_table_columns )
        return super ().eventFilter (obj ,event )

    def _configure_table_columns (self )->None :
        header =self .table .horizontalHeader ()
        header .setMinimumSectionSize (35 )
        header .setStretchLastSection (False )

        # Tat word wrap + elide cho toan bo bang
        self .table .setWordWrap (False )
        self .table .setTextElideMode (Qt .TextElideMode .ElideNone )

        column_configs = {
            "presentation_rank": {"weight": 0, "min_width": 45},
            "symbol": {"weight": 1, "min_width": 75},
            "candidate_status": {"weight": 3, "min_width": 145},
            "selected_side": {"weight": 1, "min_width": 70},
            "market_regime": {"weight": 3, "min_width": 110},
            "zone_origin_class": {"weight": 2, "min_width": 90},
            "price_vs_zone": {"weight": 1, "min_width": 95},
            "setup_score": {"weight": 0, "min_width": 110},
            "opportunity_rank": {"weight": 0, "min_width": 80},
            "evidence_confidence": {"weight": 0, "min_width": 100},
            "execution_readiness": {"weight": 0, "min_width": 90},
            "expected_effective_rr": {"weight": 0, "min_width": 105},
            "auto_trade_branch": {"weight": 2, "min_width": 90},
            "strategy_config_status": {"weight": 2, "min_width": 105},
        }

        col_count = self.table_model.columnCount()
        min_widths = []
        weights = []

        for col in range(col_count):
            col_key = self.table_model.COLUMNS[col][0]
            config = column_configs.get(col_key, {"weight": 1, "min_width": 80})
            
            # Compute dynamic content width
            padding = self.TABLE_CELL_HORIZONTAL_PADDING
            content_w = self._content_width_for_column(col, padding)
            
            min_w = max(config["min_width"], content_w)
            min_widths.append(min_w)
            weights.append(config["weight"])

        sum_min_widths = sum(min_widths)
        sum_weights = sum(weights)

        viewport_width = self.table.viewport().width()
        if viewport_width < 100:
            viewport_width = self.table.contentsRect().width()
        if viewport_width < 100:
            viewport_width = sum_min_widths

        if viewport_width <= sum_min_widths or sum_weights == 0:
            for col in range(col_count):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
                header.resizeSection(col, min_widths[col])
        else:
            extra_space = viewport_width - sum_min_widths
            widths = []
            current_total = 0
            
            stretch_indices = [i for i, w in enumerate(weights) if w > 0]
            
            for col in range(col_count):
                w = min_widths[col]
                if weights[col] > 0:
                    w += (extra_space * weights[col]) // sum_weights
                widths.append(w)
                current_total += w
                
            diff = viewport_width - current_total
            if diff > 0 and stretch_indices:
                widths[stretch_indices[-1]] += diff
                
            for col in range(col_count):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
                header.resizeSection(col, widths[col])

    def _content_width_for_column (self ,col :int ,padding :int )->int :
        header =self .table .horizontalHeader ()
        header_text =str (self .table_model .headerData (col ,Qt .Orientation .Horizontal )or "")
        # Header sections use bold text plus 8px QSS padding on both sides.
        # Keep an additional safety margin so no title is elided at common DPI.
        width =(
            header .fontMetrics ().horizontalAdvance (header_text )
            +self .TABLE_HEADER_HORIZONTAL_PADDING
        )
        for row in range (self .table_model .rowCount ()):
            index =self .table_model .index (row ,col )
            text =str (self .table_model .data (index ,Qt .ItemDataRole .DisplayRole )or "")
            width =max (width ,self .table .fontMetrics ().horizontalAdvance (text )+padding )
        return max (header .minimumSectionSize (),width )


class ScannerSymbolSelectionDialog (QDialog ):
    def __init__ (
        self,
        all_symbols: list[str],
        backtest_verified_symbols: set[str],
        market_watch_symbols: set[str],
        selected_symbols: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chọn mã quét")
        self.setObjectName("ScannerHelpDialog")
        self.setModal(True)
        self.setMinimumSize(560, 520)
        self.checkboxes: dict[str, QCheckBox] = {}
        self.market_watch_symbols = set(market_watch_symbols)
        self.backtest_verified_symbols = set(backtest_verified_symbols)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        intro = QLabel(
            "Tất cả các mã trong hệ thống. "
            "Mã có trong Market Watch là chọn được. Mã đã tick Backtest sẽ có đánh dấu ✅."
        )
        intro.setObjectName("HelperText")
        intro.setWordWrap(True)
        root.addWidget(intro)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.select_all_button = action_button("✅ Chọn tất cả khả dụng", primary=True, color="success")
        self.clear_button = action_button("❌ Bỏ chọn", primary=True, color="danger")
        for button in (self.select_all_button, self.clear_button):
            controls.addWidget(button)
        controls.addStretch(1)
        root.addLayout(controls)

        scroll = QScrollArea()
        scroll.setObjectName("SymbolSelectionScroll")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("SymbolSelectionContent")
        grid = QGridLayout(content)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        selected_set = set(selected_symbols)
        for index, symbol in enumerate(sorted(all_symbols)):
            checkbox = QCheckBox(symbol)
            checkbox.setObjectName("ScannerSymbolCheck")
            in_market_watch = symbol in self.market_watch_symbols
            is_backtested = symbol in self.backtest_verified_symbols
            selectable = in_market_watch
            checkbox.setEnabled(selectable)
            checkbox.setChecked(selectable and symbol in selected_set)
            if not selectable:
                checkbox.setToolTip("Mã này chưa có trong Market Watch của MT5.")
            elif is_backtested:
                checkbox.setText(f"{symbol}  ✅")
                checkbox.setToolTip("Đã cấu hình Backtest — dùng filter từ backtest nếu có.")
            else:
                checkbox.setToolTip("Chưa tick Backtest — chạy theo điều kiện Ready mặc định.")
            self.checkboxes[symbol] = checkbox
            grid.addWidget(checkbox, index // 3, index % 3)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 8, 0, 0)
        buttons_layout.setSpacing(8)
        buttons_layout.addStretch(1)
        cancel_btn = action_button("❌ Hủy", primary=False, color="danger")
        ok_btn = action_button("✅ Áp dụng", primary=True, color="success")
        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(ok_btn)
        root.addLayout(buttons_layout)

        self.select_all_button.clicked.connect(self._select_all_available)
        self.clear_button.clicked.connect(self._clear_all)
        ok_btn.clicked.connect(self._accept_if_valid)
        cancel_btn.clicked.connect(self.reject)

    def selected_symbols(self) -> list[str]:
        return [
            symbol for symbol, checkbox in self.checkboxes.items()
            if checkbox.isEnabled() and checkbox.isChecked()
        ]

    def _select_all_available (self )->None :
        for checkbox in self .checkboxes .values ():
            if checkbox .isEnabled ():
                checkbox .setChecked (True )

    def _clear_all (self )->None :
        for checkbox in self .checkboxes .values ():
            if checkbox .isEnabled ():
                checkbox .setChecked (False )

    def _accept_if_valid (self )->None :
        if not self .selected_symbols ():
            QMessageBox .warning (self ,"Chưa chọn mã","Cần chọn ít nhất một mã khả dụng để quét.")
            return
        self .accept ()


class ScannerRowExplanationDialog(QDialog):
    PARAM_COL_WIDTH = 150
    VALUE_COL_WIDTH = 220
    MIN_ROW_HEIGHT = 20
    CELL_VERTICAL_PADDING = 32
    CELL_HORIZONTAL_PADDING = 32

    def __init__(self, row_data: dict[str, object], table_model: ScannerTableModel, parent=None):
        super().__init__(parent)
        self.row_data = row_data
        self.table_model = table_model
        
        symbol = str(row_data.get('symbol', 'Mã'))
        self.setWindowTitle(f'Giải thích chi tiết - {symbol}')
        self.setMinimumSize(880, 500)
        self.resize(880, 600)
        self.setObjectName("ScannerHelpDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        header_label = QLabel(f"Tóm tắt dễ hiểu cho {symbol}")
        header_label.setObjectName("HelpHeaderLabel")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)

        self.table = QTableWidget()
        configure_table(self.table)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Thông số", "Giá trị", "Giải thích chi tiết"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

        layout.addWidget(self.table)

        self.technical_check = QCheckBox("Hiển thị thông tin kỹ thuật")
        self.technical_check.setToolTip(
            "Hiển thị ID, phiên bản, mã lý do và chi tiết phục vụ kiểm tra hệ thống."
        )
        self.technical_check.toggled.connect(self._toggle_technical_rows)
        layout.addWidget(self.technical_check)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 8, 0, 0)
        buttons_layout.addStretch(1)
        close_btn = action_button("❌ Đóng")
        close_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(close_btn)
        layout.addLayout(buttons_layout)

        self._populate_table()

    def _help_cell_label(self, text: str, *, bold: bool = False, color: str = "#e5e7eb") -> QLabel:
        label = QLabel(text)
        label.setObjectName("ScannerHelpCell")
        set_dynamic_property(
            label,
            "metricTone",
            semantic_role_for_color(color),
        )
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setContentsMargins(4, 2, 4, 2)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if bold:
            font = get_body_font()
            font.setBold(True)
            label.setFont(font)
        return label

    def _populate_table(self):
        row = self.row_data
        next_action, next_action_explanation = self._next_action()
        reason_summary = (
            self._selected_reason_summary()
            or "Hệ thống chưa cung cấp lý do cụ thể cho mã này."
        )

        visible_fields: list[tuple[str, str, object, str | None]] = [
            ("Trạng thái", "candidate_status", row.get("candidate_status"), None),
            ("Hướng đang đánh giá", "selected_side", row.get("selected_side"), None),
            ("Nên làm gì", "_next_action", next_action, next_action_explanation),
            ("Lý do chính", "_reason_summary", reason_summary, reason_summary),
            ("Chất lượng thiết lập", "setup_score", row.get("setup_score"), None),
            (
                "Tỷ lệ lời/lỗ dự kiến",
                "expected_effective_rr",
                row.get("expected_effective_rr"),
                None,
            ),
            (
                "Mức sẵn sàng vào lệnh",
                "execution_readiness",
                row.get("execution_readiness"),
                None,
            ),
            (
                "Bối cảnh thị trường",
                "market_regime",
                row.get("market_regime"),
                None,
            ),
            (
                "Độ tin cậy dữ liệu lịch sử",
                "evidence_confidence",
                row.get("evidence_confidence"),
                None,
            ),
            ("Điểm ưu tiên", "opportunity_rank", row.get("opportunity_rank"), None),
            (
                "Quy tắc đang áp dụng",
                "_rule_source",
                self._rule_source_value(),
                self._rule_source_explanation(),
            ),
        ]

        self.row_items = [
            self._build_explanation_item(
                title,
                key,
                value,
                explanation_override=explanation,
                technical=False,
            )
            for title, key, value, explanation in visible_fields
        ]

        technical_fields: list[tuple[str, str, object, str]] = [
            (
                "Hạng vận hành",
                "rank",
                row.get("rank"),
                self._explain_value(
                    "rank",
                    row.get("rank"),
                    str(row.get("rank") or "--"),
                ),
            ),
            (
                "Mã giao dịch tại broker",
                "_broker_symbol",
                row.get("broker_symbol") or "--",
                "Tên mã thực tế ứng dụng dùng khi giao tiếp với phần mềm giao dịch.",
            ),
            (
                "Chi tiết tính điểm ưu tiên",
                "_ranking_breakdown",
                self._compact_breakdown(
                    row.get("ranking_score_breakdown")
                    if isinstance(row.get("ranking_score_breakdown"), dict)
                    else {}
                ),
                "Các thành phần nội bộ tạo nên Điểm ưu tiên; không phải điều kiện cho phép vào lệnh.",
            ),
            (
                "Đánh giá vùng giá",
                "_zone_summary",
                self._zone_summary(),
                (
                    "Gồm chất lượng nội tại của vùng, mức phù hợp với giá hiện "
                    "tại và điểm tổng hợp. Chỉ dùng để phân tích sâu."
                ),
            ),
            (
                "ID vùng giá",
                "selected_zone_id",
                row.get("selected_zone_id") or "--",
                "Định danh kỹ thuật dùng để truy vết cùng một vùng giá xuyên hệ thống.",
            ),
            (
                "Phiên bản cách chấm vùng",
                "entry_zone_scoring_version",
                row.get("entry_zone_scoring_version") or "--",
                "Phiên bản kỹ thuật giúp hệ thống không trộn kết quả được tính theo các quy tắc khác nhau.",
            ),
            (
                "Mã lý do kỹ thuật",
                "_reason_codes",
                self._technical_reason_codes() or "--",
                "Mã nội bộ dành cho kiểm thử và truy vết; người dùng nên đọc hàng Lý do chính ở phía trên.",
            ),
        ]
        self.row_items.extend(
            self._build_explanation_item(
                title,
                key,
                value,
                explanation_override=explanation,
                technical=True,
            )
            for title, key, value, explanation in technical_fields
        )

        light = is_light_theme()

        self.table.setRowCount(len(self.row_items))
        for row, item in enumerate(self.row_items):
            if light:
                param_color = "#0f766e"
                val_color = item["color_hex"]
                if val_color.lower() == "#e5e7eb":
                    val_color = "#111827"
                exp_color = "#1f2937"
            else:
                param_color = "#5eead4"
                val_color = item["color_hex"]
                exp_color = "#e5e7eb"

            param_label = self._help_cell_label(item["param"], bold=True, color=param_color)
            val_label = self._help_cell_label(item["value"], bold=True, color=val_color)
            exp_label = self._help_cell_label(item["explanation"], color=exp_color)
            
            self.table.setCellWidget(row, 0, param_label)
            self.table.setCellWidget(row, 1, val_label)
            self.table.setCellWidget(row, 2, exp_label)
            self.table.setRowHidden(row, bool(item.get("technical")))

        QTimer.singleShot(10, self._sync_table_layout)

    def _build_explanation_item(
        self,
        title: str,
        key: str,
        value: object,
        *,
        explanation_override: str | None,
        technical: bool,
    ) -> dict[str, object]:
        if key in {column_key for column_key, _label in ScannerTableModel.COLUMNS}:
            display_value = self.table_model._display_value(
                key,
                value,
                self.row_data,
            )
            color = self.table_model._foreground(self.row_data, key)
            color_hex = color.name() if color else "#e5e7eb"
        else:
            display_value = str(value if value not in (None, "") else "--")
            color_hex = "#94a3b8" if technical else "#e5e7eb"
        explanation = (
            explanation_override
            if explanation_override is not None
            else self._explain_value(key, value, display_value)
        )
        return {
            "param": title,
            "value": display_value,
            "color_hex": color_hex,
            "explanation": explanation,
            "technical": technical,
        }

    def _toggle_technical_rows(self, visible: bool) -> None:
        for index, item in enumerate(self.row_items):
            if item.get("technical"):
                self.table.setRowHidden(index, not visible)
        QTimer.singleShot(0, self._sync_table_layout)

    def _explain_value(
        self,
        key: str,
        value: object,
        display_value: str,
    ) -> str:
        """Explain the actual value of one selected scanner row."""

        row = self.row_data
        if key == "rank":
            return (
                f"{display_value} là hạng vận hành (execution rank) của mã sau khi "
                "phân loại trạng thái. Trong cùng trạng thái, hệ thống so sánh "
                "Ưu tiên, tin cậy lịch sử, mức sẵn sàng, R:R rồi mới dùng tên mã. "
                "Đây không phải STT trên bảng; STT trên bảng dùng thứ tự hiển thị "
                "riêng theo loại vùng (SMC thật → Technical → Fallback → --)."
            )
        if key == "symbol":
            broker_symbol = str(row.get("broker_symbol") or "").strip()
            suffix = (
                f" Broker symbol đang dùng là {broker_symbol}."
                if broker_symbol
                else ""
            )
            return (
                f"{display_value} là mã giao dịch chuẩn đang được Scanner "
                f"đánh giá.{suffix}"
            )
        if key == "candidate_status":
            return self._explain_candidate_status(value, display_value)
        if key == "selected_side":
            side = str(value or "").strip().lower()
            if side == "sell":
                return (
                    "Bán nghĩa là bộ chọn chiến lược đang đánh giá kịch bản bán. "
                    "Điểm thiết lập, vùng vào lệnh, mức cắt lỗ, mục tiêu chốt lời "
                    "và tỷ lệ lời/lỗ đều phải thuộc phía bán. Đây không phải yêu "
                    "cầu bán ngay và cũng không khẳng định giá chắc chắn giảm."
                )
            if side == "buy":
                return (
                    "Mua nghĩa là bộ chọn chiến lược đang đánh giá kịch bản mua. "
                    "Điểm thiết lập, vùng vào lệnh, mức cắt lỗ, mục tiêu chốt lời "
                    "và tỷ lệ lời/lỗ đều phải thuộc phía mua. Đây không phải yêu "
                    "cầu mua ngay và cũng không khẳng định giá chắc chắn tăng."
                )
            return (
                "Chưa chọn được hướng Mua/Bán hợp lệ, nên mã này không có "
                "candidate giao dịch hoàn chỉnh."
            )
        if key == "market_regime":
            descriptions = {
                "trend_up": "thị trường đang có cấu trúc xu hướng tăng",
                "trending_up": "thị trường đang có cấu trúc xu hướng tăng",
                "trend_down": "thị trường đang có cấu trúc xu hướng giảm",
                "trending_down": "thị trường đang có cấu trúc xu hướng giảm",
                "range": "thị trường đang dao động đi ngang",
                "ranging": "thị trường đang dao động đi ngang",
                "volatile": "biến động hiện tại cao và rủi ro thực thi lớn hơn",
                "unknown": "dữ liệu chưa đủ để phân loại chế độ thị trường",
            }
            detail = descriptions.get(
                str(value or "").lower(),
                "đây là chế độ thị trường pipeline đang nhận diện",
            )
            return (
                f"{display_value}: {detail}. Quy tắc đã kiểm chứng bằng dữ liệu "
                "quá khứ chỉ được áp dụng khi bối cảnh này khớp cấu hình."
            )
        if key == "setup_score":
            score = self._number(value)
            min_score = self._strategy_threshold("min_score", 65.0)
            relation = (
                "đạt"
                if score is not None and score >= min_score
                else "chưa đạt"
            )
            score_text = f"{score:.0f}" if score is not None else "--"
            return (
                f"Điểm chất lượng {score_text}/100 {relation} mức yêu cầu "
                f"{min_score:.0f}. Đây là đánh giá tổng hợp cho đúng hướng đã "
                "chọn, nhưng vẫn phải vượt điều kiện an toàn và xác nhận điểm vào."
            )
        if key == "opportunity_rank":
            score = self._number(value)
            score_text = f"{score:.0f}/100" if score is not None else "--"
            status = self.table_model._display_value(
                "candidate_status",
                row.get("candidate_status"),
                row,
            )
            return (
                f"Điểm ưu tiên {score_text} chỉ dùng để sắp xếp các mã đang có "
                f"cùng trạng thái {status}; điểm này không thể tự nâng mã sang "
                "trạng thái tốt hơn. Cách tính chi tiết nằm trong phần thông "
                "tin kỹ thuật."
            )
        if key == "evidence_confidence":
            score = self._number(value)
            breakdown = (
                row.get("ranking_score_breakdown")
                if isinstance(row.get("ranking_score_breakdown"), dict)
                else {}
            )
            source = self._evidence_source_text(
                breakdown.get("evidence_source")
                or row.get("evidence_source")
                or "chưa có nguồn đủ mẫu"
            )
            return (
                f"Độ tin cậy từ dữ liệu lịch sử là "
                f"{score:.0f}%, nguồn: {source}. Đây không phải tỷ lệ thắng." if score is not None else
                "Chưa có bằng chứng lịch sử đủ điều kiện; giá trị này không "
                "phải tỷ lệ thắng."
            )
        if key == "execution_readiness":
            score = self._number(value)
            if score is None:
                return "Chưa xác định được mức sẵn sàng thực thi."
            interpretation = (
                "đã sẵn sàng tại scan-time"
                if score >= 100
                else "đang chờ thêm xác nhận"
                if score >= 60
                else "chỉ nên theo dõi"
                if score > 0
                else "chưa có điều kiện thực thi"
            )
            return (
                f"Mức sẵn sàng {score:.0f}% nghĩa là cơ hội này {interpretation}. "
                "Đây không phải tỷ lệ thắng; hệ thống vẫn phải kiểm tra lại theo "
                "giá mua và giá bán mới nhất trước khi đặt lệnh."
            )
        if key == "expected_effective_rr":
            rr = self._number(value)
            min_rr = self._strategy_threshold("min_rr", 1.3)
            if rr is None:
                return (
                    "Chưa tính được R:R dự kiến do thiếu Entry, SL hoặc TP hợp lệ."
                )
            relation = "đạt" if rr >= min_rr else "chưa đạt"
            return (
                f"Tỷ lệ {rr:.1f} nghĩa là với mỗi 1 phần rủi ro, lợi nhuận kỳ "
                f"vọng là {rr:.1f} phần. Mức này {relation} yêu cầu {min_rr:.1f}. "
                "Hệ thống đã xét chênh lệch giá mua/bán và sẽ tính lại trước lệnh."
            )
        if key == "auto_trade_branch":
            branch = str(value or "").upper()
            if branch == "BACKTEST_VALIDATED":
                return (
                    "Đã kiểm chứng bằng dữ liệu quá khứ: hệ thống dùng các mức "
                    "điểm và tỷ lệ lời/lỗ đã được kiểm tra cho mã này."
                )
            if branch == "DEFAULT_RULES":
                return (
                    "Mặc định: mã không có cấu hình Backtest hợp lệ nên dùng "
                    "quy tắc chung của hệ thống và vẫn phải qua mọi điều kiện an toàn."
                )
            if branch == "BACKTEST_INVALID":
                return (
                    "Cấu hình kiểm chứng bị lỗi hoặc hết hiệu lực; cơ hội này "
                    "không được dùng để tự động vào lệnh."
                )
            return "Chưa xác định được bộ quy tắc áp dụng cho cặp này."
        if key == "strategy_config_status":
            status = str(value or "").upper()
            meanings = {
                "VALIDATED": "cấu hình Backtest đã qua validation và còn hiệu lực",
                "NOT_CONFIGURED": "không có cấu hình Backtest; dùng quy tắc mặc định",
                "DRAFT": "cấu hình vẫn là bản nháp, chưa được dùng để giao dịch",
                "EXPIRED": "cấu hình đã hết hạn và phải validation lại",
                "INVALID": "cấu hình không đạt điều kiện an toàn",
                "VERSION_MISMATCH": "phiên bản scorer/feature không khớp",
                "DISABLED": "cấu hình đã bị tắt",
            }
            return (
                f"{display_value}: "
                f"{meanings.get(status, 'chưa có mô tả trạng thái config')}."
            )
        return self._general_column_explanation(key)

    def _explain_candidate_status(
        self,
        value: object,
        display_value: str,
    ) -> str:
        status = str(value or "").strip().upper()
        meanings = {
            "READY_NOW": (
                "đã khớp quy tắc giao dịch và đủ điều kiện tại thời điểm quét; "
                "hệ thống vẫn phải kiểm tra an toàn và giá mới trước khi đặt lệnh"
            ),
            "WAITING_CONFIRMATION": (
                "setup phù hợp nhưng còn thiếu trigger/xác nhận entry"
            ),
            "WATCH_ZONE": (
                "có yếu tố đáng theo dõi nhưng chưa đủ điều kiện hành động"
            ),
            "OUT_OF_STRATEGY": (
                "cặp này vẫn được hỗ trợ nhưng chưa đáp ứng một hoặc nhiều điều "
                "kiện của bộ quy tắc đang áp dụng, chẳng hạn chưa rõ hướng, điểm "
                "thiết lập hoặc R:R chưa đạt, hay chưa có kế hoạch hợp lệ"
            ),
            "BLOCKED": (
                "điều kiện an toàn đang chặn giao dịch, ví dụ dữ liệu chưa tốt, "
                "chênh lệch giá bất thường, có tin mạnh hoặc giới hạn rủi ro"
            ),
            "DATA_UNAVAILABLE": (
                "thiếu dữ liệu bắt buộc nên hệ thống không thể đánh giá an toàn"
            ),
        }
        strategy_gaps = ScannerTableModel._strategy_gap_messages(self.row_data)
        reason = "; ".join(strategy_gaps[:4]) or self._selected_reason_summary()
        suffix = f" Điều kiện còn thiếu: {reason}" if reason else ""
        return (
            f"{display_value} nghĩa là {meanings.get(status, 'trạng thái chưa được nhận diện')}."
            f"{suffix}"
        )

    def _next_action(self) -> tuple[str, str]:
        status = str(
            self.row_data.get("candidate_status") or ""
        ).strip().upper()
        actions = {
            "READY_NOW": (
                "Chuẩn bị kế hoạch, chưa vào lệnh ngay",
                (
                    "Có thể mở màn hình chi tiết để kiểm tra vùng vào, cắt lỗ "
                    "và chốt lời. Chỉ đặt lệnh sau khi hệ thống kiểm tra lại "
                    "điều kiện an toàn và giá mới nhất."
                ),
            ),
            "WAITING_CONFIRMATION": (
                "Chờ tín hiệu xác nhận điểm vào",
                (
                    "Không vào lệnh sớm. Chờ tín hiệu xác nhận theo kế hoạch, "
                    "thường từ khung thời gian vào lệnh."
                ),
            ),
            "WATCH_ZONE": (
                "Theo dõi, chưa hành động",
                (
                    "Chờ giá tiến gần hoặc đi vào vùng quan sát và chờ điều "
                    "kiện xác nhận. Điểm cao không làm trạng thái này tự sẵn sàng."
                ),
            ),
            "OUT_OF_STRATEGY": (
                "Chưa giao dịch; xem điều kiện còn thiếu",
                (
                    "Cặp vẫn nằm trong phạm vi Scanner nhưng chưa đạt bộ quy tắc "
                    "đang áp dụng. Xem điểm/ngưỡng, hướng và R:R còn thiếu; chỉ "
                    "đánh giá lại ở lần quét sau, không cố vào lệnh."
                ),
            ),
            "BLOCKED": (
                "Không giao dịch",
                (
                    "Một điều kiện an toàn đang chặn mã này. Cần xử lý nguyên "
                    "nhân như dữ liệu, chênh lệch giá, tin tức hoặc giới hạn rủi ro."
                ),
            ),
            "DATA_UNAVAILABLE": (
                "Kiểm tra lại dữ liệu",
                (
                    "Chưa đủ dữ liệu để đánh giá an toàn. Kiểm tra kết nối phần "
                    "mềm giao dịch, lịch sử giá và nguồn dữ liệu rồi quét lại."
                ),
            ),
        }
        return actions.get(
            status,
            (
                "Chưa có hành động phù hợp",
                "Hệ thống chưa nhận diện được trạng thái của mã này.",
            ),
        )

    def _rule_source_value(self) -> str:
        branch = str(
            self.row_data.get("auto_trade_branch") or ""
        ).strip().upper()
        config = str(
            self.row_data.get("strategy_config_status") or ""
        ).strip().upper()
        branch_text = {
            "BACKTEST_VALIDATED": "Quy tắc đã kiểm chứng",
            "DEFAULT_RULES": "Quy tắc mặc định",
            "BACKTEST_INVALID": "Cấu hình kiểm chứng bị lỗi",
        }.get(branch, "Chưa xác định quy tắc")
        config_text = {
            "VALIDATED": "còn hiệu lực",
            "NOT_CONFIGURED": "không có cấu hình riêng",
            "DRAFT": "bản nháp",
            "EXPIRED": "đã hết hạn",
            "INVALID": "không hợp lệ",
            "VERSION_MISMATCH": "không khớp phiên bản",
            "DISABLED": "đã tắt",
        }.get(config, "chưa rõ tình trạng")
        return f"{branch_text} • {config_text}"

    def _rule_source_explanation(self) -> str:
        branch = str(
            self.row_data.get("auto_trade_branch") or ""
        ).strip().upper()
        if branch == "BACKTEST_VALIDATED":
            return (
                "Mã đang dùng ngưỡng điểm và tỷ lệ lời/lỗ đã được kiểm tra "
                "trên dữ liệu quá khứ và còn hiệu lực."
            )
        if branch == "DEFAULT_RULES":
            return (
                "Mã chưa có cấu hình kiểm chứng riêng nên dùng ngưỡng chung "
                "của hệ thống."
            )
        if branch == "BACKTEST_INVALID":
            return (
                "Có cấu hình kiểm chứng nhưng cấu hình không còn hợp lệ; hệ "
                "thống không cho phép dùng nó để tự động vào lệnh."
            )
        return "Chưa xác định được nguồn quy tắc đang áp dụng."

    def _zone_summary(self) -> str:
        quality = self.row_data.get("entry_zone_quality_score")
        relevance = self.row_data.get("entry_zone_relevance_score")
        setup = self.row_data.get("entry_zone_setup_score")
        if quality is None and relevance is None and setup is None:
            return "Chưa có vùng giá SMC được chọn"
        return (
            f"Chất lượng={quality if quality is not None else '--'} • "
            f"Phù hợp hiện tại={relevance if relevance is not None else '--'} • "
            f"Tổng hợp={setup if setup is not None else '--'}"
        )

    def _technical_reason_codes(self) -> str:
        values: list[str] = []
        decision = (
            self.row_data.get("scanner_candidate_decision")
            if isinstance(
                self.row_data.get("scanner_candidate_decision"),
                dict,
            )
            else {}
        )
        for source in (
            self.row_data.get("auto_trade_reason_codes"),
            decision.get("reason_codes"),
        ):
            if not isinstance(source, (list, tuple)):
                continue
            for code in source:
                text = str(code).strip()
                if text and text not in values:
                    values.append(text)
        return ", ".join(values)

    @staticmethod
    def _evidence_source_text(value: object) -> str:
        source = str(value or "").strip().lower()
        return {
            "backtest_oos": "kết quả kiểm chứng ngoài mẫu",
            "backtest": "kết quả kiểm chứng dữ liệu quá khứ",
            "journal": "nhật ký giao dịch đã đóng",
            "journal_evidence": "nhật ký giao dịch đã đóng",
            "none": "chưa có nguồn đủ mẫu",
            "not_enough_data": "chưa có nguồn đủ mẫu",
        }.get(source, "nguồn dữ liệu lịch sử của hệ thống")

    def _general_column_explanation(self, key: str) -> str:
        label = next(
            (
                column_label
                for column_key, column_label in ScannerTableModel.COLUMNS
                if column_key == key
            ),
            "",
        )
        for item in ScannerColumnsHelpDialog.COLUMN_HELP:
            if item.get("column") == label:
                return (
                    f"{item.get('meaning', '')} "
                    f"{item.get('cases', '')}"
                ).strip()
        return "Chưa có giải thích cho thông số này."

    def _selected_reason_summary(self) -> str:
        row = self.row_data
        values: list[str] = []
        for field in (
            "short_reason",
            "permission_reason",
            "strategy_reason",
            "entry_reason",
        ):
            text = str(row.get(field) or "").strip()
            if text and text not in values:
                values.append(text)

        decision = (
            row.get("scanner_candidate_decision")
            if isinstance(row.get("scanner_candidate_decision"), dict)
            else {}
        )
        for source in (
            row.get("auto_trade_reason_codes"),
            decision.get("reason_codes"),
        ):
            if not isinstance(source, (list, tuple)):
                continue
            codes = [str(code) for code in source if str(code).strip()]
            for code, message in zip(codes, codes_to_messages(codes)):
                # Unknown internal codes remain available in the hidden
                # technical section, not in the user-facing explanation.
                if message == code:
                    continue
                if message and message not in values:
                    values.append(message)
        return "; ".join(values[:3])

    def _strategy_threshold(self, key: str, default: float) -> float:
        direct = self._number(self.row_data.get(key))
        if direct is not None:
            return direct
        decision = (
            self.row_data.get("scanner_candidate_decision")
            if isinstance(
                self.row_data.get("scanner_candidate_decision"),
                dict,
            )
            else {}
        )
        strategy = (
            decision.get("strategy")
            if isinstance(decision.get("strategy"), dict)
            else {}
        )
        nested = self._number(strategy.get(key))
        return nested if nested is not None else default

    @staticmethod
    def _number(value: object) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _compact_breakdown(value: dict[str, object]) -> str:
        fields = (
            ("Setup", "setup_component"),
            ("R:R", "rr_component"),
            ("Vị trí", "proximity_component"),
            ("Bằng chứng", "evidence_component"),
            ("Thực thi", "execution_component"),
            ("Phạt", "penalty_component"),
        )
        parts = [
            f"{label}={value.get(key)}"
            for label, key in fields
            if value.get(key) is not None
        ]
        return ", ".join(parts) if parts else "chưa có breakdown"

    @staticmethod
    def _explain_zone_value(key: str) -> str:
        return {
            "selected_zone_id": (
                "ID của đúng vùng SMC được truyền xuyên score, scenario và gate."
            ),
            "entry_zone_quality_score": (
                "Quality 0–100 đo chất lượng nội tại của vùng, không phụ thuộc "
                "riêng vào khoảng cách giá hiện tại."
            ),
            "entry_zone_relevance_score": (
                "Relevance 0–100 đo độ phù hợp hiện tại theo phía giá, khoảng "
                "cách ATR, tuổi vùng và market regime."
            ),
            "entry_zone_setup_score": (
                "Setup vùng tổng hợp Quality và Relevance; ranking không cộng "
                "lặp lại bằng chứng này."
            ),
            "entry_zone_scoring_version": (
                "Phiên bản semantics của điểm vùng; thống kê không trộn các "
                "phiên bản khác nhau."
            ),
        }.get(key, "")

    def _sync_table_layout(self) -> None:
        header = self.table.horizontalHeader()
        viewport_width = max(self.table.viewport().width(), self.width() - 80)
        scrollbar_width = self.table.verticalScrollBar().sizeHint().width()
        fixed_width = self.PARAM_COL_WIDTH + self.VALUE_COL_WIDTH
        exp_width = max(280, viewport_width - fixed_width - scrollbar_width - 6)
        
        header.resizeSection(0, self.PARAM_COL_WIDTH)
        header.resizeSection(1, self.VALUE_COL_WIDTH)
        header.resizeSection(2, exp_width)

        column_widths = {0: self.PARAM_COL_WIDTH, 1: self.VALUE_COL_WIDTH, 2: exp_width}
        
        for row, item in enumerate(self.row_items):
            heights = [self.MIN_ROW_HEIGHT]
            
            for col in range(3):
                label = self.table.cellWidget(row, col)
                if isinstance(label, QLabel):
                    usable_width = max(50, column_widths[col] - 16)
                    label.setFixedWidth(usable_width)
                    heights.append(label.heightForWidth(usable_width) + 6)
            
            row_height = max(heights)
            self.table.setRowHeight(row, row_height)

    def refresh_theme_styles(self) -> None:
        self.table_model.set_theme(
            "light" if is_light_theme(self.settings_service) else "dark"
        )
        self.table_model.layoutChanged.emit()
        self._sync_table_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_table_layout()



class ScannerColumnsHelpDialog(QDialog):
    COLUMN_HELP: list[dict[str, str]] = [
        {
            "column": "STT",
            "meaning": "Số thứ tự dòng 1..N theo thứ tự hiển thị SMC thật → Technical → Fallback → --.",
            "cases": (
                "STT được tính lại mỗi lần quét theo thứ tự ưu tiên loại vùng. "
                "Không phải hạng chất lượng hay mức ưu tiên thực thi. "
                "Hạng vận hành gốc (execution rank) vẫn được giữ nguyên trên từng dòng."
            ),
        },
        {
            "column": "Mã",
            "meaning": "Mã giao dịch chuẩn của ứng dụng đang được quét.",
            "cases": (
                "Ví dụ EUR/USD, XAU/USD. Broker symbol thực có thể có hậu tố "
                "như EURUSDm và được hiển thị trong trang Chi tiết."
            ),
        },
        {
            "column": "Trạng thái",
            "meaning": "Kết luận tại thời điểm quét về mức đáp ứng quy tắc giao dịch.",
            "cases": (
                "Đạt điều kiện = đã khớp quy tắc ở thời điểm quét; Chờ xác nhận = "
                "còn thiếu tín hiệu vào lệnh; Đang theo dõi = chưa nên hành động; "
                "Chưa đạt quy tắc = cặp vẫn được hỗ trợ nhưng còn thiếu điểm, hướng, "
                "R:R hoặc kế hoạch hợp lệ; Bị chặn an toàn = safety gate không cho "
                "phép; Không đủ dữ liệu = thiếu đầu vào bắt buộc. Đạt điều kiện vẫn "
                "phải được kiểm tra lại trước khi đặt lệnh."
            ),
        },
        {
            "column": "Hướng",
            "meaning": "Hướng Mua hoặc Bán mà hệ thống đang đánh giá.",
            "cases": (
                "Điểm chất lượng, kịch bản, vùng vào lệnh, mức cắt lỗ, mục tiêu "
                "chốt lời và tỷ lệ lời/lỗ đều phải thuộc đúng hướng này. Dấu -- "
                "nghĩa là chưa chọn được hướng hợp lệ."
            ),
        },
        {
            "column": "Bối cảnh TT",
            "meaning": "Bối cảnh thị trường hiện tại do hệ thống nhận diện.",
            "cases": (
                "Xu hướng tăng, Xu hướng giảm, Đi ngang, Biến động mạnh hoặc "
                "Chưa rõ. Quy tắc Backtest còn yêu cầu bối cảnh này khớp cấu hình."
            ),
        },
        {
            "column": "Loại vùng",
            "meaning": "Phân loại nguồn gốc của vùng vào lệnh được chọn.",
            "cases": (
                "SMC thật = vùng SMC canonical (bao gồm smc_distant) — đây là "
                "vùng cấu trúc thực được phát hiện bởi bộ dò SMC. "
                "Technical = vùng swing kỹ thuật thực nhưng không phải SMC. "
                "Fallback = vùng ATR giả lập để hiển thị khi không có vùng phù hợp. "
                "-- = không có selected-side plan hoặc dữ liệu không đủ."
            ),
        },
        {
            "column": "Vùng",
            "meaning": "Trạng thái giá tại thời điểm quét so với vùng entry đã chọn.",
            "cases": (
                "Trong vùng = giá nằm trong hoặc đúng biên vùng entry. "
                "Ngoài vùng = giá nằm ngoài hai biên vùng. "
                "-- = chưa có vùng thật (Fallback) hoặc thiếu dữ liệu. "
                "Cột chỉ phản ánh giá tại thời điểm quét, không tự cập nhật. "
                "Giá sẽ được kiểm tra lại theo bid/ask live trước khi gửi lệnh."
            ),
        },
        {
            "column": "Điểm thiết lập",
            "meaning": "Điểm chất lượng của cơ hội theo đúng hướng đã chọn, thang 0–100.",
            "cases": (
                "Hệ thống so sánh điểm này với mức điểm tối thiểu của chiến lược. "
                "Điểm cao không tự động cho phép vào lệnh; cơ hội vẫn phải đạt "
                "điều kiện an toàn, tỷ lệ lời/lỗ và xác nhận điểm vào."
            ),
        },
        {
            "column": "Ưu tiên",
            "meaning": "Điểm 0–100 dùng để xếp hạng các cơ hội sau khi đã phân loại.",
            "cases": (
                "Điểm này giúp chọn mã đáng xem trước trong cùng một trạng thái. "
                "Nó tổng hợp chất lượng cơ hội, tỷ lệ lời/lỗ, vị trí giá, dữ liệu "
                "lịch sử và mức sẵn sàng; không phải điều kiện cho phép đặt lệnh."
            ),
        },
        {
            "column": "Tin cậy LS",
            "meaning": "Độ tin cậy của bằng chứng lịch sử, hiển thị theo phần trăm.",
            "cases": (
                "Nếu có cấu hình đã kiểm chứng, hệ thống dùng kết quả trên dữ liệu "
                "kiểm tra độc lập. Nếu không, nhật ký giao dịch đủ mẫu có thể được "
                "dùng. Thiếu bằng chứng hiển thị 0%. Đây không phải tỷ lệ thắng."
            ),
        },
        {
            "column": "Sẵn sàng",
            "meaning": "Mức gần với khả năng thực thi tại thời điểm quét.",
            "cases": (
                "Đạt điều kiện = 100%; Chờ xác nhận = 60%; Đang theo dõi = 30%; "
                "các trạng thái khác = 0%. Đây không phải xác suất thành công "
                "và không thay thế việc kiểm tra lại theo giá mới."
            ),
        },
        {
            "column": "R:R dự kiến",
            "meaning": "Tỷ lệ lợi nhuận/rủi ro dự kiến của đúng hướng đã chọn.",
            "cases": (
                "Từ 2.0 trở lên hiển thị xanh; từ 1.3 đến dưới 2.0 hiển thị vàng; "
                "thấp hơn hiển thị đỏ. R:R được tính lại theo bid/ask mới trước "
                "khi gửi lệnh."
            ),
        },
        {
            "column": "Quy tắc",
            "meaning": "Nguồn quy tắc được áp dụng cho mã trong lần quét.",
            "cases": (
                "Đã kiểm chứng = dùng quy tắc rút ra từ kết quả kiểm tra dữ liệu "
                "quá khứ; Mặc định = chưa có cấu hình kiểm chứng; Cấu hình lỗi = "
                "có cấu hình nhưng chưa hợp lệ và không được tự động giao dịch."
            ),
        },
        {
            "column": "Cấu hình BT",
            "meaning": "Tình trạng của cấu hình kiểm chứng bằng dữ liệu quá khứ.",
            "cases": (
                "Hợp lệ, Mặc định, Bản nháp, Hết hạn, Không hợp lệ, Sai phiên "
                "bản hoặc Đã tắt. Luôn đọc cột này cùng cột Quy tắc."
            ),
        },
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Giải thích Bảng kết quả quét")
        self.setObjectName("ScannerHelpDialog")
        self.setModal(True)
        self.setMinimumSize(920, 560)
        self.resize(1040, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        intro = QLabel(
            "Bảng dưới đây giải thích đúng 14 cột của Scanner V2. "
            "Cách đọc nhanh: Trạng thái → Quy tắc và Cấu hình BT → Hướng, "
            "Điểm thiết lập và R:R dự kiến → Tin cậy LS, Sẵn sàng và Ưu tiên."
        )
        intro.setObjectName("HelperText")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        table = QTableWidget(len(self.COLUMN_HELP), 3)
        configure_table(table)
        table.setHorizontalHeaderLabels(
            ["Cột", "Ý nghĩa", "Cách đọc / Trường hợp thường gặp"]
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setTextElideMode(Qt.TextElideMode.ElideNone)
        table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

        for row, help_item in enumerate(self.COLUMN_HELP):
            values = (
                help_item["column"],
                help_item["meaning"],
                help_item["cases"],
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                )
                table.setItem(row, column, item)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 155)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.help_table = table
        layout.addWidget(table, 1)

        note = QLabel(
            "Lưu ý: Đạt điều kiện chỉ là kết quả tại thời điểm quét. "
            "Cổng phát hành và bước kiểm tra lại theo giá mới vẫn có thể chặn lệnh."
        )
        note.setObjectName("HelperText")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 8, 0, 0)
        buttons_layout.addStretch(1)
        close_btn = action_button("❌ Đóng")
        close_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(close_btn)
        layout.addLayout(buttons_layout)


# ---------------------------------------------------------------------------
# Market brief HTML formatter (module-level helper)
# ---------------------------------------------------------------------------

def parse_market_brief(raw: str) -> list[dict]:
    import re

    # Section keywords with their icons — order matters (first match wins)
    SECTION_PATTERNS: list[tuple[str, str]] = [
        ("TỔNG QUAN", "🌍"),
        ("ƯU TIÊN", "⭐"),
        ("TRÁNH", "🚫"),
        ("RỦI RO", "🛡️"),
        ("CHỜ", "⏳"),
        ("KẾT LUẬN", "📌"),
    ]

    def match_heading(line: str) -> tuple[str, str] | None:
        """Try to extract a section heading from a line. Returns (heading, icon) or None."""
        upper = line.upper()
        for keyword, icon in SECTION_PATTERNS:
            if keyword in upper:
                # Extract the heading text: strip leading numbers, bullets, markdown
                cleaned = re.sub(r"^[\d\s.)\-•*#]+\s*", "", line)
                # Take only the part before the colon (heading keyword only, not AI commentary)
                colon_idx = cleaned.find(":")
                if colon_idx > 0:
                    cleaned = cleaned[:colon_idx]
                cleaned = cleaned.strip().rstrip(":").strip()
                # Keep the heading concise (first 60 chars)
                if len(cleaned) > 60:
                    cleaned = cleaned[:60]
                return (cleaned, icon)
        return None

    def looks_like_heading(line: str) -> bool:
        """Quick check if a line is likely a heading (starts with number prefix like 1. or 2))."""
        stripped = line.strip()
        if len(stripped) > 80:
            return False
        # Must start with a number prefix: "1.", "2)", "3." etc.
        if not re.match(r"^\d+[.)]\s+", stripped):
            return False
        upper = stripped.upper()
        return any(kw in upper for kw, _ in SECTION_PATTERNS)

    lines = raw.splitlines()
    sections: list[dict] = []
    current_section: dict | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Strip leading markdown bold/heading markers for cleaner matching
        cleaned = re.sub(r"^(\*{1,3}\s*|#{1,3}\s*)", "", stripped)

        heading_match = match_heading(cleaned)
        is_heading = heading_match is not None and looks_like_heading(cleaned)

        if is_heading:
            heading, icon = heading_match  # type: ignore[misc]
            current_section = {"title": heading, "icon": icon, "lines": []}
            sections.append(current_section)
            # Check if there's content after a colon on the same line
            rest = re.sub(r"^[\d\s.)\-•*#]+\s*", "", stripped)
            colon_idx = rest.find(":")
            if colon_idx > 0:
                after_colon = rest[colon_idx + 1:].strip()
                if after_colon:
                    current_section["lines"].append(after_colon)
        else:
            if current_section is not None:
                current_section["lines"].append(stripped)
            else:
                current_section = {
                    "title": "Bản tin",
                    "icon": "📊",
                    "lines": [stripped],
                }
                sections.append(current_section)

    # Fallback: if only 1 default "Bản tin" section, try harder to split
    if len(sections) == 1 and sections[0]["title"] == "Bản tin":
        content = "\n".join(sections[0]["lines"])
        # Split on numbered headings like "1. TỔNG QUAN" or "2) ƯU TIÊN"
        parts = re.split(r"\n(?=\d+[.)]\s*[A-Za-zÀ-ỸĐ])", content)
        if len(parts) > 1:
            sections = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                hm = match_heading(part.split("\n")[0])
                if hm:
                    heading, icon = hm
                    # Remove heading line from body
                    body_lines = part.split("\n")
                    first = body_lines[0]
                    rest_first = re.sub(r"^[\d\s.)\-•*#]+\s*", "", first)
                    colon_idx = rest_first.find(":")
                    if colon_idx > 0:
                        after = rest_first[colon_idx + 1:].strip()
                        if after:
                            body_lines = [after] + body_lines[1:]
                        else:
                            body_lines = body_lines[1:]
                    else:
                        body_lines = body_lines[1:]
                    body = "\n".join(line.strip() for line in body_lines if line.strip())
                    sections.append({"title": heading, "icon": icon, "lines": [body] if body else []})
                else:
                    sections.append({"title": "Bản tin", "icon": "📊", "lines": [part]})

    # Third fallback: continuous narrative without headings — split by topic transitions
    if len(sections) == 1:
        content = "\n".join(sections[0]["lines"])
        # Transition markers: (regex, title, icon) — first match determines section boundary
        TRANSITIONS: list[tuple[str, str, str]] = [
            (r"(?:tuyệt\s*đối\s*)?(?:nên|hãy|cần|phải)\s*tránh", "NHÓM NÊN TRÁNH", "🚫"),
            (r"tránh\s*giao\s*dịch", "NHÓM NÊN TRÁNH", "🚫"),
            (r"rủi\s*ro\s*toàn\s*hệ\s*thống", "MỨC RỦI RO KHUYẾN NGHỊ", "🛡️"),
            (r"(?:mức|quản\s*trị)\s*rủi\s*ro", "MỨC RỦI RO KHUYẾN NGHỊ", "🛡️"),
            (r"(?:đang|còn)\s*chờ\s*(?:tín\s*hiệu|xác\s*nhận)", "SETUP ĐANG CHỜ", "⏳"),
            (r"các\s*mã\s*đang\s*chờ", "SETUP ĐANG CHỜ", "⏳"),
            (r"(?:nhóm|tập\s*trung)\s*(?:nên|đáng|cần)\s*(?:ưu\s*tiên|tập\s*trung|chú\s*ý)", "NHÓM NÊN ƯU TIÊN", "⭐"),
            (r"nên\s*tập\s*trung", "NHÓM NÊN ƯU TIÊN", "⭐"),
            (r"kết\s*luận", "KẾT LUẬN", "📌"),
        ]
        # Split content into sentences, then find where topic transitions occur
        sentences = re.split(r"(?<=[.!?])\s+", content)
        if len(sentences) > 1:
            new_sections: list[dict] = []
            cur_title = sections[0]["title"]
            cur_icon = sections[0]["icon"]
            cur_lines: list[str] = []
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                # Check if this sentence starts a new topic
                matched = False
                for pattern, title, icon in TRANSITIONS:
                    if re.search(pattern, sent, re.IGNORECASE):
                        # Save current section before switching
                        if cur_lines:
                            new_sections.append({"title": cur_title, "icon": cur_icon, "lines": list(cur_lines)})
                        cur_title = title
                        cur_icon = icon
                        cur_lines = [sent]
                        matched = True
                        break
                if not matched:
                    cur_lines.append(sent)
            if cur_lines:
                new_sections.append({"title": cur_title, "icon": cur_icon, "lines": cur_lines})
            if len(new_sections) > 1:
                sections = new_sections

    # Rename default first section if it contains market overview content
    if sections and sections[0]["title"] == "Bản tin":
        first_text = "\n".join(sections[0]["lines"]).lower()
        if any(kw in first_text for kw in ("thị trường hôm nay", "tổng quan", "xu hướng", "phiên")):
            sections[0]["title"] = "TỔNG QUAN PHIÊN"
            sections[0]["icon"] = "🌍"

    # Post-process: deduplicate consecutive sections with same title
    merged: list[dict] = []
    for s in sections:
        s_title = s["title"]
        s_icon = s["icon"]
        if merged and merged[-1]["title"] == s_title:
            merged[-1]["lines"].extend(s["lines"])
        else:
            merged.append(s)

    # Build final output
    formatted_sections = []
    for s in merged:
        content = "\n".join(s["lines"])
        formatted_sections.append({
            "title": s["title"],
            "icon": s["icon"],
            "content": content,
        })
    return formatted_sections


def _format_section_content_to_html(text: str, light: bool = False) -> str:
    from html import escape
    import re
    
    text_color = "#111827" if light else "#cbd5e1"
    list_color = "#1f2937" if light else "#d1d5db"
    
    lines = text.splitlines()
    html_lines = []
    list_type = None
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if list_type:
                html_lines.append(f"</{list_type}>")
                list_type = None
            continue
            
        m = re.match(r"^[-•*]\s+(.*)", stripped)
        if m:
            if list_type == "ol":
                html_lines.append("</ol>")
                list_type = None
            if not list_type:
                html_lines.append(
                    f"<ul style='margin: 4px 0; padding-left: 20px; color: {list_color}; list-style-type: disc;'>"
                )
                list_type = "ul"
            html_lines.append(f"<li style='margin: 3px 0; line-height: 1.4;'>{escape(m.group(1))}</li>")
            continue
            
        m = re.match(r"^\d+[.)]\s+(.*)", stripped)
        if m:
            if list_type == "ul":
                html_lines.append("</ul>")
                list_type = None
            if not list_type:
                html_lines.append(
                    f"<ol style='margin: 4px 0; padding-left: 20px; color: {list_color};'>"
                )
                list_type = "ol"
            html_lines.append(f"<li style='margin: 3px 0; line-height: 1.4;'>{escape(m.group(1))}</li>")
            continue
            
        if list_type:
            html_lines.append(f"</{list_type}>")
            list_type = None
            
        html_lines.append(f"<p style='margin: 4px 0; color: {text_color}; line-height: 1.5;'>{escape(stripped)}</p>")
        
    if list_type:
        html_lines.append(f"</{list_type}>")
        
    return compile_rich_html(
        "\n".join(html_lines),
        theme="light" if light else "dark",
    )
