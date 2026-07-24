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
from ui .screens .shared import action_button ,card ,labeled_value ,page_header
from ui.translation import vi_term


class ScannerTableModel (QAbstractTableModel ):
    COLUMNS =[
    ("rank","STT"),
    ("symbol","Mã"),
    ("candidate_status","Trạng thái"),
    ("selected_side","Hướng"),
    ("market_regime","Chế độ TT"),
    ("setup_score","Setup"),
    ("opportunity_rank","Cơ hội"),
    ("evidence_confidence","Bằng chứng"),
    ("execution_readiness","Thực thi"),
    ("expected_effective_rr","R:R thực"),
    ("auto_trade_branch","Nhánh"),
    ("strategy_config_status","Config"),
    ("detail_action","Chi tiết"),
    ]

    ACTION_TEXT ={"ready":'Sẵn sàng',"watch":'Theo dõi',"wait":'Chờ',"skip":'Bỏ qua'}
    BIAS_TEXT ={"buy":"Mua","sell":'Bán',"neutral":'Trung lập',"stand_aside":'Đứng ngoài'}
    PERMISSION_TEXT ={"allowed":'Được phép',"caution":'Cẩn trọng',"blocked":'Bị chặn'}
    MACRO_BIAS_TEXT ={"aligned":'Thuận',"neutral":'Trung tính',"divergent":'Ngược'}
    ENTRY_ZONE_TEXT ={"in_zone":"Trong vùng","near_zone":"Gần vùng","far":"Còn xa","unknown":"Chưa có vùng"}
    GROUP_TEXT ={"ready_now":"Sẵn sàng ngay","waiting_confirmation":"Chờ xác nhận","watch_zone":"Theo dõi","blocked":"Bị chặn"}
    STATUS_TEXT ={
        "READY_NOW":"Sẵn sàng",
        "WAITING_CONFIRMATION":"Chờ xác nhận",
        "WATCH_ZONE":"Theo dõi",
        "OUT_OF_STRATEGY":"Ngoài chiến lược",
        "BLOCKED":"Bị chặn",
        "DATA_UNAVAILABLE":"Thiếu dữ liệu",
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
            if key =="direction_bias":
                return self ._direction_bias_tooltip (value )
            if key =="entry_status":
                return self ._entry_status_tooltip (value ,row )
            if key =="price_vs_zone":
                entry_status_val =row .get ("entry_status")if row else None
                return self ._entry_status_tooltip (entry_status_val ,row )
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
        self .rows =rows 
        self .endResetModel ()

    def row_at (self ,row :int )->dict [str ,object ]|None :
        if 0 <=row <len (self .rows ):
            return self .rows [row ]
        return None 

    def _has_real_plan(self, row: dict[str, object] | None) -> bool:
        """Check if at least one scenario has a real (non-fallback) trade plan."""
        if not row:
            return False
        analysis = row.get("analysis_result")
        if not isinstance(analysis, dict):
            return False
        scenarios = analysis.get("scenarios", [])
        if not isinstance(scenarios, list):
            return False
        return any(
            isinstance(s, dict) and s.get("entry_zone_source") not in (None, "fallback")
            for s in scenarios
        )

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
        """Row is low-confidence when no real trade plan exists."""
        return not self._has_real_plan(row)

    def _display_value (self ,key :str ,value :object ,row :dict [str ,object ]|None =None )->str :
        if self._is_fallback_row(row) and key in {"price_vs_zone","m15_quality","macro_bias"}:
            return "--"
        if key =="candidate_status":
            return self.STATUS_TEXT.get(str(value or "").upper(), str(value or "--"))
        if key =="selected_side":
            return self.BIAS_TEXT.get(str(value or "").lower(), str(value or "--"))
        if key =="direction_bias":
            return self ._format_direction_bias (value )
        if key =="price_vs_zone":
            return self .ENTRY_ZONE_TEXT .get (str (value ),str (value or "--"))
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
        if key =="detail_action":
            return "Xem"
        if key =="short_reason":
            text =str (value if value is not None else "--")
            if row is not None and bool (row .get ("ai_summary_available")):
                return f"AI: {text }"
            return text 
        return str (value if value is not None else "--")

    def _foreground (self ,row :dict [str ,object ],key :str ):
        if key =="candidate_status":
            return {
                "READY_NOW":QColor ("#10b981"),
                "WAITING_CONFIRMATION":QColor ("#f59e0b"),
                "WATCH_ZONE":QColor ("#ea580c"),
                "OUT_OF_STRATEGY":QColor ("#94a3b8"),
                "BLOCKED":QColor ("#e11d48"),
                "DATA_UNAVAILABLE":QColor ("#64748b"),
            }.get(str(row.get(key, "")).upper())
        if key =="selected_side":
            return {
                "buy":QColor ("#ea580c"),
                "sell":QColor ("#f43f5e"),
            }.get(str(row.get(key, "")).lower())
        if key in {"opportunity_rank","setup_score","evidence_confidence","execution_readiness"}:
            try:
                value = float(row.get(key))
            except (TypeError, ValueError):
                return QColor("#94a3b8")
            if value >= 70:
                return QColor("#10b981")
            if value >= 40:
                return QColor("#f59e0b")
            return QColor("#94a3b8")
        if key =="strategy_config_status":
            return {
                "VALIDATED":QColor("#10b981"),
                "NOT_CONFIGURED":QColor("#94a3b8"),
                "DRAFT":QColor("#f59e0b"),
                "EXPIRED":QColor("#e11d48"),
                "INVALID":QColor("#e11d48"),
                "VERSION_MISMATCH":QColor("#e11d48"),
            }.get(str(row.get(key, "")).upper(), QColor("#94a3b8"))
        if key =="scanner_group":
            group =str (row .get ("scanner_group",""))
            return {
            "ready_now":QColor ("#10b981"),
            "waiting_confirmation":QColor ("#f59e0b"),
            "watch_zone":QColor ("#ea580c"),
            "blocked":QColor ("#e11d48"),
            }.get (group )
        if key =="direction_bias":
            side =self ._direction_bias_side (row .get (key ))
            return {"buy":QColor ("#ea580c"),"sell":QColor ("#f43f5e")}.get (side )
        if key =="market_regime":
            regime =str (row .get (key ,""))
            return {
            "trend_up":QColor ("#10b981"),
            "trend_down":QColor ("#e11d48"),
            "range":QColor ("#f59e0b"),
            "volatile":QColor ("#ea580c"),
            "unknown":QColor ("#94a3b8"),
            }.get (regime )
        if key =="m15_quality":
            quality =str (row .get (key ,""))
            return {
            "strict":QColor ("#10b981"),
            "loose":QColor ("#f59e0b"),
            "none":QColor ("#e11d48"),
            "backtest_fallback":QColor ("#94a3b8"),
            }.get (quality )
        if key =="expected_effective_rr":
            try:
                val =float (row .get (key ))
            except (TypeError ,ValueError ):
                return QColor ("#94a3b8")
            if val >=2.0 :
                return QColor ("#10b981")
            if val >=1.3 :
                return QColor ("#f59e0b")
            return QColor ("#e11d48")
        if key =="price_vs_zone":
            return {
            "in_zone":QColor ("#10b981"),
            "near_zone":QColor ("#f59e0b"),
            "far":QColor ("#94a3b8"),
            "unknown":QColor ("#94a3b8"),
            }.get (str (row .get (key )))
        if key =="macro_bias":
            return {
            "aligned":QColor ("#10b981"),
            "neutral":QColor ("#f59e0b"),
            "divergent":QColor ("#e11d48"),
            }.get (str (row .get (key )))
        if key =="macro_score":
            val =int (row .get ("macro_score",15 ))
            if val >=22 :
                return QColor ("#10b981")
            if val >=15 :
                return QColor ("#f59e0b")
            return QColor ("#94a3b8")
        if key =="journal_expectancy_r":
            try:
                val =float (row .get ("journal_expectancy_r"))
            except (TypeError ,ValueError ):
                return QColor ("#94a3b8")
            if val >0 :
                return QColor ("#10b981")
            if val <0 :
                return QColor ("#e11d48")
            return QColor ("#94a3b8")
        if key =="journal_sample_size":
            return QColor ("#9ca3af")
        if key =="entry_status":
            if self ._has_no_entry_zone (row ):
                return QColor ("#94a3b8")
            raw =str (row .get (key ,"")).strip ().lower ()
            if raw in ("confirmed_entry","ready","ready_to_trade"):
                return QColor ("#10b981")
            if raw in ("waiting_confirmation","waiting_for_confirmation","watch_zone","in_zone","near_zone"):
                return QColor ("#f59e0b")
            if raw in ("invalidated","no_setup","data_unavailable","","none"):
                return QColor ("#94a3b8")
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
    # Product safety lock: Scanner may analyze and show manual candidates, but
    # it must not request automatic MT5 execution from the UI.
    AUTO_TRADE_UI_ENABLED =False
    # Dynamically resolved from COLUMNS
    SHORT_REASON_COL =12  # overridden in __init__
    TABLE_CELL_HORIZONTAL_PADDING =24
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
        # Session flag: chỉ auto-scan 1 lần khi mới mở tab Scanner
        self ._auto_scanned_this_session =False
        self .scan_thread =None 
        self .scan_worker =None 
        self .scan_result :dict [str ,object ]|None =None
        self._market_brief_text = ""
        self .symbol_boxes :list [QCheckBox ]=[]
        self .market_watch_symbols :set [str ]=set ()
        self .scan_symbols :list [str ]=[]
        self .selected_scan_symbols :list [str ]=[]
        self .table_model =ScannerTableModel ()
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
        # Luôn auto-scan lần đầu khi mở tab Scanner trong phiên
        def _auto_scan_once ():
            if not self ._auto_scanned_this_session:
                self ._auto_scanned_this_session =True
                self ._run_scan ()
        QTimer .singleShot (1500 ,_auto_scan_once )

    def _settings_card (self )->QFrame :
        frame =card (None )
        frame .layout ().setSpacing (4 )
        frame .layout ().setContentsMargins (14 ,8 ,14 ,8 )
        frame .layout ().setAlignment (Qt .AlignmentFlag .AlignTop )
        settings = self.settings_service.load()
        self .scan_symbols =self ._configured_scan_symbols (settings )
        self .selected_scan_symbols =list (self .scan_symbols )

        # Lần đầu mở tab Scanner trong phiên: chọn tất cả mã
        if not self ._auto_scanned_this_session:
            self .scan_symbols =list (SUPPORTED_SYMBOLS )
            self .selected_scan_symbols =list (SUPPORTED_SYMBOLS )

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
        if not self ._auto_scanned_this_session:
            self .scan_mode_combo .setCurrentIndex (1 )   # "Quét theo khoảng thời gian"
            m5_idx =self .scan_interval_combo .findData (300 )
            self .scan_interval_combo .setCurrentIndex (m5_idx if m5_idx >=0 else 0 )
        self.auto_trade_check = QPushButton("🤖 Tự động vào lệnh MT5")
        self.auto_trade_check.setObjectName("AutoTradeToggle")
        self.auto_trade_check.setCheckable(True)
        self.auto_trade_check.setCursor(Qt.CursorShape.ArrowCursor)
        self .auto_trade_check .setToolTip (
            "Chức năng tự động vào lệnh MT5 đang bị vô hiệu hóa. "
            "Scanner sẽ không tự gửi lệnh; thao tác vào lệnh thủ công vẫn "
            "phải qua các cổng an toàn."
        )
        self .auto_trade_check .setChecked (False )
        self .auto_trade_check .toggled .connect (self ._update_auto_trade_toggle_style )
        self .scan_mode_combo .currentIndexChanged .connect (self ._update_auto_trade_toggle_state )
        self ._update_auto_trade_toggle_state ()

        self.scan_button = action_button("🔍 Quét thị trường", primary=True, color="info")
        self .scan_button .clicked .connect (self ._run_scan )
        self .stop_auto_scan_button =action_button ("⏹️ Dừng quét tự động",primary =True ,color ="danger")
        self .stop_auto_scan_button .setVisible (False )
        self .stop_auto_scan_button .clicked .connect (self ._stop_auto_scan )

        self.show_orders_button = action_button("📋 Hiển thị lệnh", primary=True, color="info")
        self.show_orders_button.setToolTip("Xem danh sách lệnh sẽ được vào / đã vào từ MT5")
        self.show_orders_button.clicked.connect(self._show_orders_dialog)
        self._dim_show_orders_button()

        scan_options =QHBoxLayout ()
        scan_options .addWidget (QLabel ("Chế độ"))
        scan_options .addWidget (self .scan_mode_combo )
        scan_options .addWidget (QLabel ("Khoảng thời gian"))
        scan_options .addWidget (self .scan_interval_combo )
        scan_options .addWidget (self .auto_trade_check )
        scan_options .addWidget (self .stop_auto_scan_button )
        scan_options .addWidget (self .scan_button )
        scan_options .addWidget (self .show_orders_button )
        scan_options .addStretch (1 )
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
        mt5 =self .status_labels .get ("MT5",QLabel ("--")).text ()
        scanned =self .status_labels .get ("Đã quét",QLabel ("--")).text ()
        ai =self .status_labels .get ("AI đã gọi",QLabel ("--")).text ()
        last =self .status_labels .get ("Lần quét gần nhất",QLabel ("--")).text ()
        rollout =self .status_labels .get ("Rollout",QLabel ("--")).text ()
        parts =[f"MT5: {mt5 }",f"Đã quét: {scanned }",f"AI: {ai }"]
        if rollout not in ("--",""):
            parts .append (f"Rollout: {rollout }")
        if last not in ("--",""):
            parts .append (f"Lần quét: {last }")
        self .status_summary_label .setText ("  •  ".join (parts ))

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

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        auto_trade_enabled = self._auto_trade_enabled()
        auto_results = scan_result.get("auto_trade_results", {})
        if not isinstance(auto_results, dict):
            auto_results = {}

        order_rows = self._build_order_rows(rows, auto_trade_enabled, auto_results)
        if not order_rows:
            QMessageBox.information(self, "Hiển thị lệnh",
                "Không có lệnh nào được khớp.\n"
                "Kiểm tra lại điều kiện vào lệnh hoặc kết quả quét.")
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
        rollout_blocks_orders = (
            rollout_policy.get("kill_switch") is True
            or rollout_stage in {"DISABLED", "SHADOW"}
        )
        title_text = (
            f"Kết quả rollout {rollout_stage}"
            if rollout_blocks_orders
            else "Lệnh đã vào MT5"
            if auto_trade_enabled
            else "Lệnh sẽ được khớp"
        )
        dlg.setWindowTitle(f"📋 {title_text}")
        dlg.setMinimumSize(940, 560)
        dlg.resize(980, 620)
        dlg.setObjectName("AnalysisDetailDialog")

        active_btn_style = ""
        disabled_btn_style = ""

        # Action button helper for manual trade execution
        def execute_manual_order(order_info: dict, btn: QPushButton) -> None:
            btn.setEnabled(False)
            btn.setText("Đang đặt...")
            btn.setStyleSheet(disabled_btn_style)
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

            # Manual and automatic orders share the same Phase-3 realtime
            # revalidation path.  The controller recalculates volume from the
            # live bid/ask and returns structured block codes on failure.
            try:
                execution = self.scanner_controller.execute_order_candidate(
                    order_info,
                    comment=f"AMA Manual {order_info.get('symbol') or '--'}",
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
                btn.setStyleSheet(disabled_btn_style)
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
                QMessageBox.warning(
                    dlg,
                    "Không thể vào lệnh",
                    (
                        f"{execution.get('message') or 'Lệnh không vượt qua cổng thực thi.'}"
                        + (f"\n\nMã chặn: {detail}" if detail else "")
                    ),
                )
                btn.setEnabled(True)
                btn.setText("⚡ Thử lại")
                btn.setStyleSheet(active_btn_style)
            return

        def create_order_button(row_order: dict) -> QWidget:
            btn_container = QWidget()
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(0)
            
            btn = action_button("⚡ Vào lệnh", primary=True)
            
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
                btn.setStyleSheet(disabled_btn_style)
            else:
                btn.setStyleSheet(active_btn_style)
                
            btn.clicked.connect(lambda: execute_manual_order(row_order, btn))
            btn_layout.addWidget(btn)
            return btn_container

        root = QVBoxLayout(dlg)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Beautiful Header Card
        header_frame = QFrame()
        header_frame.setObjectName("PanelCard")
        header_accent = "#10b981" if auto_trade_enabled else "#fb923c"
        header_frame.setStyleSheet(
            f"QFrame#PanelCard {{"
            f"  border-left: 4px solid {header_accent};"
            f"  background: {'#fbfbfb' if light else '#171c24'};"
            f"}}"
        )
        header_frame.setStyleSheet(
            f"QFrame#PanelCard {{"
            f"  border-left: 4px solid {header_accent};"
            f"  background: {'#fbfbfb' if light else '#171c24'};"
            f"}}"
        )
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(4)

        title_label = QLabel(f"📋 {title_text}")
        title_label.setObjectName("ActionTitle")
        title_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {'#111827' if light else '#f8fafc'};"
        )
        
        subtitle_text = (
            f"{len(order_rows)} lệnh được khớp từ kết quả quét thị trường."
            if auto_trade_enabled
            else f"{len(order_rows)} lệnh dự kiến từ kết quả quét thị trường "
                  f"(chưa vào MT5 vì chưa bật tự động vào lệnh)."
        )
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("CardDetail")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"font-size: 12px; color: {'#4b5563' if light else '#9ca3af'};"
        )
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle)
        root.addWidget(header_frame)


        # Table
        table = QTableWidget()
        table.setObjectName("EconTable")
        columns = ["STT", "Mã", "Hướng", "Entry", "SL", "TP", "KL", "R:R", "Ghi chú"]
        if not auto_trade_enabled:
            columns.append("Thao tác")
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setWordWrap(True)

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

        buy_color = QColor("#059669" if light else "#10b981")
        sell_color = QColor("#b91c1c" if light else "#f87171")
        neutral_fg = QColor("#4b5563" if light else "#9ca3af")

        def create_direction_pill(direction: str, light_theme: bool) -> QWidget:
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(0)
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if direction == "buy":
                label.setText(" MUA ")
                bg = "#d1fae5" if light_theme else "#064e3b"
                fg = "#065f46" if light_theme else "#34d399"
            elif direction == "sell":
                label.setText(" BÁN ")
                bg = "#ffe4e6" if light_theme else "#4c0519"
                fg = "#9f1239" if light_theme else "#f87171"
            else:
                label.setText(" -- ")
                bg = "#e5e7eb" if light_theme else "#1f2937"
                fg = "#374151" if light_theme else "#9ca3af"
            label.setStyleSheet(
                f"QLabel {{"
                f"  background-color: {bg};"
                f"  color: {fg};"
                f"  font-size: 11px;"
                f"  font-weight: bold;"
                f"  border-radius: 4px;"
                f"  padding: 3px 12px;"
                f"}}"
            )
            layout.addWidget(label)
            return container

        for idx, order in enumerate(order_rows):
            direction = str(order.get("side", "")).lower()

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
            f = sym_item.font()
            f.setBold(True)
            sym_item.setFont(f)
            table.setItem(idx, 1, sym_item)

            # Direction pill
            table.setCellWidget(idx, 2, create_direction_pill(direction, light))

            # Entry
            entry = order.get("entry_price")
            entry_text = f"{float(entry):.5f}" if entry is not None else "--"
            table.setItem(idx, 3, styled_item(entry_text))

            # SL
            sl = order.get("stop_loss")
            sl_text = f"{float(sl):.5f}" if sl is not None else "--"
            sl_item = styled_item(sl_text)
            sl_item.setForeground(sell_color)
            table.setItem(idx, 4, sl_item)

            # TP
            tp = order.get("take_profit")
            tp_text = f"{float(tp):.5f}" if tp is not None else "--"
            tp_item = styled_item(tp_text)
            tp_item.setForeground(buy_color)
            table.setItem(idx, 5, tp_item)

            # Volume
            vol = order.get("volume")
            vol_text = f"{float(vol):.2f}" if vol is not None else "--"
            table.setItem(idx, 6, styled_item(vol_text))

            # R:R — show range if available: "5.6 (2.9–5.6)"
            rr = order.get("risk_reward")
            rr_range = order.get("risk_reward_range")
            if rr_range and isinstance(rr_range, dict):
                best = rr_range.get("best")
                worst = rr_range.get("worst")
                if best is not None and worst is not None and best != worst:
                    rr_text = f"{best:.1f} ({worst:.1f}–{best:.1f})"
                elif best is not None:
                    rr_text = f"{best:.1f}"
                else:
                    rr_text = str(rr) if rr else "--"
            else:
                rr_text = str(rr) if rr else "--"
            table.setItem(idx, 7, styled_item(rr_text))

            # Note
            note = str(order.get("note", "") or order.get("message", ""))
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

            table.setRowHeight(idx, 36)

        root.addWidget(table, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        close_btn = action_button("❌ Đóng", primary=False, color="danger")
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)
        root.addLayout(btn_layout)

        if light:
            dlg.setStyleSheet("QDialog { background: #F4F1EA; }")
        else:
            dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
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
        self .table .setObjectName ("EconTable")
        self .table .setShowGrid (False )
        self .table .setModel (self .table_model )
        self .table .setWordWrap (True )
        self .table .verticalHeader ().setSectionResizeMode (QHeaderView .ResizeMode .ResizeToContents )
        self .table .setSelectionBehavior (QTableView .SelectionBehavior .SelectRows )
        self .table .setSelectionMode (QTableView .SelectionMode .SingleSelection )
        self .table .setAlternatingRowColors (True )
        self .table .verticalHeader ().setVisible (False )
        self .table .horizontalHeader ().setStretchLastSection (False )
        self .table .horizontalHeader ().setDefaultAlignment (Qt .AlignmentFlag .AlignCenter )
        self .table .horizontalHeader ().setHighlightSections (False )
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
        # Lần đầu scan: MT5 có thể chưa kết nối → market_watch_symbols rỗng → dùng trực tiếp selected_scan_symbols
        if not symbols and not self ._auto_scanned_this_session and self .selected_scan_symbols:
            symbols =list (self .selected_scan_symbols )
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
            "backtest_config_v2": bool(
                getattr(feature_settings, "backtest_config_v2", False)
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
        smc_scoring_mode =str (
            getattr (feature_settings ,"smc_scoring_mode","v2")or "v2"
        ),
        )
        thread ,worker =self .scanner_controller .create_scan_worker (request )
        self .scan_thread =thread 
        self .scan_worker =worker 
        worker .progress .connect (self ._scan_progress )
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
        self .scan_result =result
        rows =list (result .get ("rows",[]))

        # Backend owns the canonical order.  UI must not re-rank by plan/SMC.

        self .table_model .set_rows (rows )
        self .status_labels ['Đã quét'].setText (f"{result .get ('symbols_scanned',0 )} / {len (self ._selected_symbols ())}")
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
        shadow_report = (
            result.get("shadow_report")
            if isinstance(result.get("shadow_report"), dict)
            else {}
        )
        readiness = (
            result.get("release_readiness")
            if isinstance(result.get("release_readiness"), dict)
            else {}
        )
        rollout_text = str(rollout_policy.get("stage", "--") or "--")
        if shadow_report.get("enabled") is True:
            rollout_text += (
                f", Δ {shadow_report.get('disagreements', 0)}"
                f"/{shadow_report.get('samples', 0)}"
            )
        rollout_text += (
            ", gate đạt"
            if readiness.get("ready") is True
            else ", gate chờ"
        )
        if "Rollout" in self.status_labels:
            self.status_labels["Rollout"].setText(rollout_text)
        if sent :
            self .scan_button .setText (f"Đã gửi {sent} alert Telegram")
        self .status_labels ['Lần quét gần nhất'].setText (str (result .get ("timestamp","--")).replace ("T"," ")[:19 ])
        self .detail_button .setEnabled (bool (rows ))
        self .save_button .setEnabled (bool (rows ))
        self ._highlight_show_orders_button ()
        self ._update_status_summary ()

        # --- Market Brief ---
        market_brief = str(result.get("market_brief", "")).strip()
        if market_brief:
            self._market_brief_text = market_brief
        else:
            self._market_brief_text = ""
            err = str(result.get("market_brief_error", ""))
            if err:
                self._market_brief_text = f"Lỗi tạo bản tin: {err}"
        self .progress_bar .setValue (100 )
        self .progress_bar .setVisible (False )
        self .progress_container .setVisible (False )
        self ._configure_table_columns ()

    def _scan_failed (self ,message :str )->None :
        self .progress_bar .setVisible (False )
        self .progress_container .setVisible (False )
        QMessageBox .warning (self ,'Không thể quét thị trường',message )

    def _scan_thread_finished (self )->None :
        self.scan_button.setText("🔍 Quét thị trường")
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
        if index .column ()==len (ScannerTableModel .COLUMNS )-1 :
            self ._open_row_detail (index .row ())

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

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        dlg = QDialog(self)
        dlg.setWindowTitle("Bản tin thị trường")
        dlg.setMinimumSize(850, 650)
        
        if light:
            dlg.setStyleSheet("QDialog { background: #F4F1EA; }")
        else:
            dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
            
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Header Section
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        
        title = QLabel("📊 BẢN TIN THỊ TRƯỜNG")
        title.setObjectName("PanelTitle")
        if light:
            title.setStyleSheet("font-size: 16px; color: #D94625; font-weight: bold;")
        else:
            title.setStyleSheet("font-size: 16px; color: #ea580c; font-weight: bold;")
        header_layout.addWidget(title)

        timestamp = str(self.scan_result.get("timestamp", "") if self.scan_result else "")
        ts_text = f"Thời gian quét: {timestamp.replace('T', ' ')[:19]}" if timestamp else "Bản tin tổng hợp từ AI"
        ts_label = QLabel(ts_text)
        ts_label.setObjectName("HelperText")
        if light:
            ts_label.setStyleSheet("color: #736B60; font-size: 11px;")
        else:
            ts_label.setStyleSheet("color: #64748b; font-size: 11px;")
        header_layout.addWidget(ts_label)
        layout.addLayout(header_layout)

        # Content Container (Outer Frame)
        container_frame = QFrame()
        container_frame.setObjectName("ContainerFrame")
        if light:
            container_frame.setStyleSheet(
                "QFrame#ContainerFrame { background: #EDEBE4; border: 1px solid #D6D2C8; border-radius: 8px; }"
            )
        else:
            container_frame.setStyleSheet(
                "QFrame#ContainerFrame { background: #171c24; border: 1px solid #2b3545; border-radius: 8px; }"
            )
            
        container_layout = QVBoxLayout(container_frame)
        container_layout.setContentsMargins(4, 4, 4, 4)
        
        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        
        scroll_content = QWidget()
        scroll_content.setObjectName("ScrollContent")
        scroll_content.setStyleSheet("background: transparent;")
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(12, 12, 12, 12)
        scroll_content_layout.setSpacing(12)
        
        # Parse the brief text into sections
        sections = parse_market_brief(self._market_brief_text)
        
        for sec in sections:
            card = QFrame()
            card.setObjectName("SectionCard")
            if light:
                card.setStyleSheet(
                    "QFrame#SectionCard { background: #ffffff; border: 1px solid #D6D2C8; border-radius: 8px; }"
                )
            else:
                card.setStyleSheet(
                    "QFrame#SectionCard { background: #1e2533; border: 1px solid #2b3545; border-radius: 8px; }"
                )
                
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(8)
            
            # Section Header (Icon + Title)
            sec_title = QLabel(f"{sec['icon']}  {sec['title'].upper()}")
            sec_title.setObjectName("SectionTitle")
            if light:
                sec_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #D94625;")
            else:
                sec_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ea580c;")
            card_layout.addWidget(sec_title)
            
            # Section Body Content
            sec_content = QLabel()
            sec_content.setObjectName("SectionContent")
            sec_content.setWordWrap(True)
            sec_content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            
            formatted_html = _format_section_content_to_html(sec['content'], light=light)
            sec_content.setText(formatted_html)
            
            if light:
                sec_content.setStyleSheet("font-size: 13px; color: #111827; line-height: 1.5;")
            else:
                sec_content.setStyleSheet("font-size: 13px; color: #cbd5e1; line-height: 1.5;")
                
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
            "rank": {"weight": 0, "min_width": 45},
            "symbol": {"weight": 1, "min_width": 75},
            "candidate_status": {"weight": 3, "min_width": 115},
            "selected_side": {"weight": 1, "min_width": 70},
            "market_regime": {"weight": 3, "min_width": 95},
            "setup_score": {"weight": 0, "min_width": 65},
            "opportunity_rank": {"weight": 0, "min_width": 70},
            "evidence_confidence": {"weight": 0, "min_width": 85},
            "execution_readiness": {"weight": 0, "min_width": 75},
            "expected_effective_rr": {"weight": 0, "min_width": 75},
            "auto_trade_branch": {"weight": 2, "min_width": 85},
            "strategy_config_status": {"weight": 2, "min_width": 90},
            "detail_action": {"weight": 0, "min_width": 65},
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
        width =header .fontMetrics ().horizontalAdvance (header_text )+padding
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
        self.table.setObjectName("EconTable")
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Thông số", "Giá trị", "Giải thích chi tiết"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setWordWrap(True)
        self.table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setFrameShape(QFrame.Shape.NoFrame)

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
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setContentsMargins(4, 2, 4, 2)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        label.setStyleSheet(f"color: {color}; background: transparent;")
        if bold:
            font = label.font()
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
                "Vị trí xếp hạng",
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

        # Check if light theme
        try:
            light = SettingsService().load().display.theme == "light"
        except Exception:
            light = False

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
                f"{display_value} là vị trí ưu tiên hiện tại của mã sau khi "
                "phân loại trạng thái. Trong cùng trạng thái, hệ thống so sánh "
                "Cơ hội, bằng chứng, mức sẵn sàng, R:R rồi mới dùng tên mã."
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
                    "Chưa tính được R:R thực do thiếu entry, SL hoặc TP hợp lệ."
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
            return "Chưa xác định được nhánh chiến lược của mã này."
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
        if key == "detail_action":
            return (
                "Bấm Xem hoặc nhấp đúp dòng để mở toàn bộ phân tích của mã: "
                "scenario, vùng entry, SL/TP, gate, SMC, macro và reason codes."
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
                "cơ hội này không khớp quy tắc giao dịch, chẳng hạn sai bối cảnh, "
                "sai hướng, điểm chất lượng hoặc tỷ lệ lời/lỗ dưới mức yêu cầu, "
                "hay chưa có kế hoạch hợp lệ; điều này không có nghĩa dữ liệu bị lỗi"
            ),
            "BLOCKED": (
                "điều kiện an toàn đang chặn giao dịch, ví dụ dữ liệu chưa tốt, "
                "chênh lệch giá bất thường, có tin mạnh hoặc giới hạn rủi ro"
            ),
            "DATA_UNAVAILABLE": (
                "thiếu dữ liệu bắt buộc nên hệ thống không thể đánh giá an toàn"
            ),
        }
        reason = self._selected_reason_summary()
        suffix = f" Lý do của mã này: {reason}" if reason else ""
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
                "Bỏ qua trong lần quét hiện tại",
                (
                    "Mã chưa khớp quy tắc giao dịch. Không cố vào lệnh; chờ "
                    "lần quét sau khi điểm, bối cảnh hoặc tỷ lệ lời/lỗ thay đổi."
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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_table_layout()



class ScannerColumnsHelpDialog(QDialog):
    COLUMN_HELP: list[dict[str, str]] = [
        {
            "column": "STT",
            "meaning": "Thứ tự ưu tiên sau khi Scanner hoàn tất phân loại và xếp hạng.",
            "cases": (
                "Ưu tiên theo Trạng thái trước, sau đó lần lượt theo Cơ hội, "
                "độ tin cậy chiến lược, mức sẵn sàng thực thi, R:R và tên mã. "
                "STT có thể thay đổi ở mỗi lần quét."
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
            "meaning": "Kết luận hiện tại của hệ thống về cơ hội giao dịch.",
            "cases": (
                "Sẵn sàng = đã đủ điều kiện ở thời điểm quét; Chờ xác nhận = còn "
                "thiếu tín hiệu vào lệnh; Theo dõi = chưa nên hành động; Ngoài "
                "chiến lược = không khớp quy tắc giao dịch; Bị chặn = vi phạm "
                "điều kiện an toàn; Thiếu dữ liệu = chưa đủ đầu vào. Trạng thái "
                "Sẵn sàng vẫn phải được kiểm tra lại trước khi đặt lệnh."
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
            "column": "Chế độ TT",
            "meaning": "Trạng thái thị trường hiện tại do pipeline nhận diện.",
            "cases": (
                "Xu hướng tăng, Xu hướng giảm, Đi ngang, Biến động mạnh hoặc "
                "Chưa rõ. Nhánh Backtest còn yêu cầu regime này khớp config."
            ),
        },
        {
            "column": "Setup",
            "meaning": "Điểm chất lượng của cơ hội theo đúng hướng đã chọn, thang 0–100.",
            "cases": (
                "Hệ thống so sánh điểm này với mức điểm tối thiểu của chiến lược. "
                "Điểm cao không tự động cho phép vào lệnh; cơ hội vẫn phải đạt "
                "điều kiện an toàn, tỷ lệ lời/lỗ và xác nhận điểm vào."
            ),
        },
        {
            "column": "Cơ hội",
            "meaning": "Điểm 0–100 dùng để xếp hạng các cơ hội sau khi đã phân loại.",
            "cases": (
                "Điểm này giúp chọn mã đáng xem trước trong cùng một trạng thái. "
                "Nó tổng hợp chất lượng cơ hội, tỷ lệ lời/lỗ, vị trí giá, dữ liệu "
                "lịch sử và mức sẵn sàng; không phải điều kiện cho phép đặt lệnh."
            ),
        },
        {
            "column": "Bằng chứng",
            "meaning": "Độ tin cậy của bằng chứng lịch sử, hiển thị theo phần trăm.",
            "cases": (
                "Nếu có cấu hình đã kiểm chứng, hệ thống dùng kết quả trên dữ liệu "
                "kiểm tra độc lập. Nếu không, nhật ký giao dịch đủ mẫu có thể được "
                "dùng. Thiếu bằng chứng hiển thị 0%. Đây không phải tỷ lệ thắng."
            ),
        },
        {
            "column": "Thực thi",
            "meaning": "Mức gần với khả năng thực thi tại thời điểm quét.",
            "cases": (
                "Sẵn sàng = 100%; Chờ xác nhận = 60%; Theo dõi = 30%; "
                "các trạng thái khác = 0%. Đây không phải xác suất thành công "
                "và không thay thế việc kiểm tra lại theo giá mới."
            ),
        },
        {
            "column": "R:R thực",
            "meaning": "Tỷ lệ lợi nhuận/rủi ro dự kiến của đúng hướng đã chọn.",
            "cases": (
                "Từ 2.0 trở lên hiển thị xanh; từ 1.3 đến dưới 2.0 hiển thị vàng; "
                "thấp hơn hiển thị đỏ. R:R được tính lại theo bid/ask mới trước "
                "khi gửi lệnh."
            ),
        },
        {
            "column": "Nhánh",
            "meaning": "Nguồn quy tắc được áp dụng cho mã trong lần quét.",
            "cases": (
                "Đã kiểm chứng = dùng quy tắc rút ra từ kết quả kiểm tra dữ liệu "
                "quá khứ; Mặc định = chưa có cấu hình kiểm chứng; Cấu hình lỗi = "
                "có cấu hình nhưng chưa hợp lệ và không được tự động giao dịch."
            ),
        },
        {
            "column": "Config",
            "meaning": "Tình trạng của cấu hình kiểm chứng bằng dữ liệu quá khứ.",
            "cases": (
                "Hợp lệ, Mặc định, Bản nháp, Hết hạn, Không hợp lệ, Sai phiên "
                "bản hoặc Đã tắt. Luôn đọc cột này cùng cột Nhánh."
            ),
        },
        {
            "column": "Chi tiết",
            "meaning": "Mở màn hình phân tích đầy đủ của mã được chọn.",
            "cases": (
                "Bấm Xem để đọc kịch bản, vùng vào lệnh, mức cắt lỗ, mục tiêu "
                "chốt lời, điều kiện chiến lược, bối cảnh vĩ mô và danh sách "
                "kiểm tra."
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
            "Bảng dưới đây giải thích đúng 13 cột của Scanner V2. "
            "Cách đọc nhanh: Trạng thái → Nhánh và Config → Hướng, Setup và "
            "R:R → Bằng chứng, Thực thi và Cơ hội."
        )
        intro.setObjectName("HelperText")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        table = QTableWidget(len(self.COLUMN_HELP), 3)
        table.setObjectName("EconTable")
        table.setShowGrid(False)
        table.setHorizontalHeaderLabels(
            ["Cột", "Ý nghĩa", "Cách đọc / Trường hợp thường gặp"]
        )
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setWordWrap(True)
        table.setTextElideMode(Qt.TextElideMode.ElideNone)
        table.setAlternatingRowColors(True)
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
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 155)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.help_table = table
        layout.addWidget(table, 1)

        note = QLabel(
            "Lưu ý: READY_NOW chỉ là sẵn sàng tại thời điểm quét. "
            "Rollout SHADOW hoặc execution revalidation vẫn có thể chặn lệnh."
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
        
    return "\n".join(html_lines)
