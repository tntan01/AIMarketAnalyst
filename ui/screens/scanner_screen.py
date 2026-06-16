from __future__ import annotations 

from config.constants import SUPPORTED_SYMBOLS
from controllers .scanner_controller import ScannerController 
from core .scanner import ScannerRequest 
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
QVBoxLayout ,
QWidget ,
)
from services .mt5_service import MT5Service 
from services .settings_service import SettingsService 
from ui .screens .shared import action_button ,card ,labeled_value ,page_header 


class ScannerTableModel (QAbstractTableModel ):
    COLUMNS =[
    ("rank","Xếp hạng"),
    ("symbol","Mã"),
    ("scanner_action","Hành động"),
    ("direction_bias","Xu hướng"),
    ("price_vs_zone","Entry"),
    ("trade_permission","Quyền"),
    ("best_score","Điểm tốt nhất"),
    ("final_score","Final"),
    ("opportunity_score","Cơ hội"),
    ("scanner_group","Nhóm"),
    ("entry_status","Trạng thái entry"),
    ("m15_quality","M15"),
    ("score_gap","Gap"),
    ("buy_score","Điểm mua"),
    ("sell_score","Điểm bán"),
    ("macro_score","Vĩ mô (0-30)"),
    ("macro_bias","Thuận vĩ mô"),
    ("risk_reward","R:R"),
    ("journal_sample_size","Mẫu NK"),
    ("journal_expectancy_r","Kỳ vọng NK"),
    ("short_reason","Lý do chính"),
    ("detail_action","Chi tiết"),
    ]

    ACTION_TEXT ={"ready":'Sẵn sàng',"watch":'Theo dõi',"wait":'Chờ',"skip":'Bỏ qua'}
    BIAS_TEXT ={"buy":"Mua","sell":'Bán',"neutral":'Trung lập',"stand_aside":'Đứng ngoài'}
    PERMISSION_TEXT ={"allowed":'Được phép',"caution":'Cẩn trọng',"blocked":'Bị chặn'}
    MACRO_BIAS_TEXT ={"aligned":'Thuận',"neutral":'Trung tính',"divergent":'Ngược'}
    ENTRY_ZONE_TEXT ={"in_zone":"Trong vùng","near_zone":"Gần vùng","far":"Còn xa","unknown":"Chưa có vùng"}
    GROUP_TEXT ={"ready_now":"Sẵn sàng ngay","waiting_confirmation":"Chờ xác nhận","watch_zone":"Theo dõi","blocked":"Bị chặn"}
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
            if key in {"rank","best_score","buy_score","sell_score","macro_score","macro_bias","price_vs_zone","risk_reward","detail_action","final_score","opportunity_score","scanner_group","entry_status","m15_quality","score_gap","direction_bias","journal_sample_size","journal_expectancy_r"}:
                return Qt .AlignmentFlag .AlignCenter
            return Qt .AlignmentFlag .AlignVCenter |Qt .AlignmentFlag .AlignLeft 
        if role ==Qt .ItemDataRole .ForegroundRole :
            return self ._foreground (row ,key )
        if role ==Qt .ItemDataRole .ToolTipRole :
            if key =="direction_bias":
                return self ._direction_bias_tooltip (value )
            if key =="entry_status":
                return self ._entry_status_tooltip (value ,row )
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

    def _display_value (self ,key :str ,value :object ,row :dict [str ,object ]|None =None )->str :
        if key =="scanner_action":
            action =row .get ("display_action",value )if row else value
            return self .ACTION_TEXT .get (str (action ),str (action or "--"))
        if key =="direction_bias":
            return self ._format_direction_bias (value )
        if key =="trade_permission":
            return self .PERMISSION_TEXT .get (str (value ),str (value or "--"))
        if key =="price_vs_zone":
            return self .ENTRY_ZONE_TEXT .get (str (value ),str (value or "--"))
        if key =="macro_score":
            score_val =int (value )if isinstance (value ,(int ,float ))else 15 
            conf =float (row .get ("macro_confidence",1.0 ))if row else 1.0 
            quality_dot ="●"if conf >=0.8 else ("○"if conf >=0.5 else "◌")
            return f"{quality_dot } {score_val }"
        if key =="macro_bias":
            return self .MACRO_BIAS_TEXT .get (str (value ),str (value or "--"))
        if key =="risk_reward":
            return str (value or "-")
        if key =="journal_sample_size":
            return str (int (value ))if isinstance (value ,(int ,float ))else "0"
        if key =="journal_expectancy_r":
            return f"{float(value):.2f}R" if isinstance(value, (int, float)) else "--"
        if key =="final_score":
            return str (int (value ))if isinstance (value ,(int ,float ))else "--"
        if key =="opportunity_score":
            return str (int (value ))if isinstance (value ,(int ,float ))else "--"
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
            return str (value or "--")
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
        if key =="scanner_action":
            action =str (row .get ("display_action")or row .get (key ))
            return {
            "ready":QColor ("#5eead4"),
            "watch":QColor ("#93c5fd"),
            "wait":QColor ("#facc15"),
            "skip":QColor ("#94a3b8"),
            }.get (action )
        if key =="direction_bias":
            side =self ._direction_bias_side (row .get (key ))
            return {"buy":QColor ("#5eead4"),"sell":QColor ("#fb7185")}.get (side )
        if key =="trade_permission":
            return {
            "allowed":QColor ("#5eead4"),
            "caution":QColor ("#facc15"),
            "blocked":QColor ("#94a3b8"),
            }.get (str (row .get (key )))
        if key =="price_vs_zone":
            return {
            "in_zone":QColor ("#5eead4"),
            "near_zone":QColor ("#facc15"),
            "far":QColor ("#94a3b8"),
            "unknown":QColor ("#94a3b8"),
            }.get (str (row .get (key )))
        if key =="macro_bias":
            return {
            "aligned":QColor ("#5eead4"),
            "neutral":QColor ("#facc15"),
            "divergent":QColor ("#fb7185"),
            }.get (str (row .get (key )))
        if key =="macro_score":
            val =int (row .get ("macro_score",15 ))
            if val >=22 :
                return QColor ("#5eead4")
            if val >=15 :
                return QColor ("#facc15")
            return QColor ("#94a3b8")
        if key =="journal_expectancy_r":
            try:
                val =float (row .get ("journal_expectancy_r"))
            except (TypeError ,ValueError ):
                return QColor ("#94a3b8")
            if val >0 :
                return QColor ("#5eead4")
            if val <0 :
                return QColor ("#fb7185")
            return QColor ("#94a3b8")
        if key =="journal_sample_size":
            return QColor ("#9ca3af")
        if key =="entry_status":
            if self ._has_no_entry_zone (row ):
                return QColor ("#94a3b8")
            raw =str (row .get (key ,"")).strip ().lower ()
            if raw in ("confirmed_entry","ready","ready_to_trade"):
                return QColor ("#5eead4")
            if raw in ("waiting_confirmation","waiting_for_confirmation","watch_zone","in_zone","near_zone"):
                return QColor ("#facc15")
            if raw in ("invalidated","no_setup","data_unavailable","","none"):
                return QColor ("#94a3b8")
            return None
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
    # Dynamically resolved from COLUMNS
    SHORT_REASON_COL =12  # overridden in __init__
    TABLE_CELL_HORIZONTAL_PADDING =24
    TABLE_EXTRA_COLUMN_PADDING ={2 :18 ,3 :18 ,6 :18 ,10 :18 ,15 :22 ,16 :22 ,17 :24, 19 :24 }
    TABLE_REASON_HORIZONTAL_PADDING =30
    TABLE_MIN_REASON_WIDTH =150

    def __init__ (self ,navigate =None ,*, app =None )->None :
        super ().__init__ ()
        self .navigate =navigate
        self .app =app
        self .settings_service =app .settings_service if app else SettingsService ()
        self .mt5_service =app .mt5_service if app else MT5Service ()
        self .scanner_controller =ScannerController (self .settings_service ,self .mt5_service )
        self .scan_thread =None 
        self .scan_worker =None 
        self .scan_result :dict [str ,object ]|None =None 
        self .symbol_boxes :list [QCheckBox ]=[]
        self .market_watch_symbols :set [str ]=set ()
        self .scan_symbols :list [str ]=[]
        self .selected_scan_symbols :list [str ]=[]
        self .table_model =ScannerTableModel ()
        # Resolve SHORT_REASON_COL dynamically from COLUMNS
        reason_keys =[k for k,_ in self .table_model .COLUMNS]
        self .SHORT_REASON_COL =reason_keys .index ("short_reason")if "short_reason"in reason_keys else 18
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
        'Chọn mã và quét setup đủ điều kiện.',
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
        self.auto_trade_check = QPushButton("🤖 Tự động vào lệnh MT5")
        self.auto_trade_check.setObjectName("AutoTradeToggle")
        self.auto_trade_check.setCheckable(True)
        self.auto_trade_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self .auto_trade_check .setToolTip (
            "Chỉ dùng khi quét tự động. Khi bật, hệ thống có thể đặt lệnh MT5 cho setup sẵn sàng."
        )
        self .auto_trade_check .setChecked (False )
        self .auto_trade_check .toggled .connect (self ._update_auto_trade_toggle_style )
        self .scan_mode_combo .currentIndexChanged .connect (self ._update_auto_trade_toggle_state )
        self ._update_auto_trade_toggle_state ()

        self .scan_button =action_button ('🔎 Quét thị trường',primary =True ,color ="info")
        self .scan_button .clicked .connect (self ._run_scan )
        self .stop_auto_scan_button =action_button ("⏹️ Dừng quét tự động",primary =True ,color ="danger")
        self .stop_auto_scan_button .setVisible (False )
        self .stop_auto_scan_button .clicked .connect (self ._stop_auto_scan )

        scan_options =QHBoxLayout ()
        scan_options .addWidget (QLabel ("Chế độ"))
        scan_options .addWidget (self .scan_mode_combo )
        scan_options .addWidget (QLabel ("Khoảng thời gian"))
        scan_options .addWidget (self .scan_interval_combo )
        scan_options .addWidget (self .auto_trade_check )
        scan_options .addWidget (self .stop_auto_scan_button )
        scan_options .addWidget (self .scan_button )
        scan_options .addStretch (1 )
        frame .layout ().addLayout (scan_options )

        # ---- Status backing labels (not added to UI, used for summary) ----
        self .status_labels :dict [str ,QLabel ]={}
        for title in ("MT5","Đã quét","AI đã gọi","Telegram","Lần quét gần nhất"):
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
        self .progress_bar .setFixedHeight (22 )
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
        parts =[f"MT5: {mt5 }",f"Đã quét: {scanned }",f"AI: {ai }"]
        if last not in ("--",""):
            parts .append (f"Lần quét: {last }")
        self .status_summary_label .setText ("  •  ".join (parts ))

    def _auto_trade_enabled (self )->bool :
        return bool (
            hasattr (self ,"scan_mode_combo")
            and hasattr (self ,"auto_trade_check")
            and self .scan_mode_combo .currentData ()=="auto"
            and self .auto_trade_check .isChecked ()
        )

    def _update_auto_trade_toggle_state (self )->None :
        if not hasattr (self ,"auto_trade_check"):
            return
        is_auto_mode =bool (hasattr (self ,"scan_mode_combo")and self .scan_mode_combo .currentData ()=="auto")
        self .auto_trade_check .setEnabled (is_auto_mode )
        if not is_auto_mode and self .auto_trade_check .isChecked ():
            self .auto_trade_check .setChecked (False )
        self ._update_auto_trade_toggle_style ()

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
            header_layout .addWidget (self .detail_button )
            header_layout .addWidget (self .save_button )
            frame .layout ().insertWidget (0 ,header )

        self .table =QTableView ()
        self .table .setObjectName ("DataTable")
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
        self .table .viewport ().installEventFilter (self )
        self ._configure_table_columns ()
        self .table .setSortingEnabled (False )
        self .table .clicked .connect (self ._table_clicked )
        frame .layout ().addWidget (self .table ,1 )
        return frame 

    def _show_columns_help (self )->None :
        dialog =ScannerColumnsHelpDialog (self )
        dialog .exec ()

    def refresh_status (self )->None :
        status =self .mt5_service .connection_status ()
        self .status_labels ["MT5"].setText ('Đã kết nối'if status .terminal_connected and status .logged_in else 'Chưa kết nối đầy đủ')
        self ._refresh_symbol_availability (status )
        self ._refresh_scan_button_state ()
        self ._update_status_summary ()

    def _selected_symbols (self )->list [str ]:
        allowed =set (self .scan_symbols )&self .market_watch_symbols
        return [symbol for symbol in self .selected_scan_symbols if symbol in allowed]

    def _refresh_symbol_availability (self ,status )->None :
        matches =self .mt5_service .configured_symbols_in_market_watch ()if status .terminal_connected else []
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
            if settings .trading .symbol_settings .get (symbol)and settings .trading .symbol_settings [symbol].backtest
        ]

    def _update_symbol_summary (self )->None :
        if not hasattr (self ,"symbol_summary_label"):
            return
        selected =self ._selected_symbols ()
        if not self .scan_symbols:
            self .symbol_summary_label .setText ("Chưa có mã nào được đánh dấu Kiểm thử trong Cài đặt.")
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
        symbol_auto_trade: dict[str, dict] = {}
        for symbol in symbols:
            cfg = settings.trading.symbol_settings.get(symbol)
            if cfg and cfg.backtest:
                regime = (cfg.auto_trade_regime or "").strip()
                side = (cfg.auto_trade_side or "").strip()
                min_rr = cfg.auto_trade_min_rr or 0.0
                if regime or side in ("buy", "sell") or min_rr:
                    symbol_auto_trade[symbol] = {
                        "regime": cfg.auto_trade_regime,
                        "side": cfg.auto_trade_side,
                        "min_rr": cfg.auto_trade_min_rr,
                        "min_score": cfg.min_score,
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
        server_time =self .mt5_service .server_time_utc ()
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
        if sent :
            self .scan_button .setText (f"Đã gửi {sent} alert Telegram")
        self .status_labels ['Lần quét gần nhất'].setText (str (result .get ("timestamp","--")).replace ("T"," ")[:19 ])
        self .detail_button .setEnabled (bool (rows ))
        self .save_button .setEnabled (bool (rows ))
        self ._update_status_summary ()
        self .progress_bar .setValue (100 )
        self .progress_bar .setVisible (False )
        self .progress_container .setVisible (False )
        self ._configure_table_columns ()

    def _scan_failed (self ,message :str )->None :
        self .progress_bar .setVisible (False )
        self .progress_container .setVisible (False )
        QMessageBox .warning (self ,'Không thể quét thị trường',message )

    def _scan_thread_finished (self )->None :
        self .scan_button .setText ('Quét thị trường')
        self .scan_thread =None
        self .scan_worker =None
        self ._refresh_scan_button_state ()
        self .progress_bar .setVisible (False )
        self .progress_container .setVisible (False )
        self .refresh_status ()
        self ._schedule_next_auto_scan ()

    def _table_clicked (self ,index :QModelIndex )->None :
        self .detail_button .setEnabled (index .isValid ())
        if index .column ()==len (ScannerTableModel .COLUMNS )-1 :
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

        fixed_total =0
        for col in range (self .table_model .columnCount ()):
            if col ==self .SHORT_REASON_COL :
                header .setSectionResizeMode (col ,QHeaderView .ResizeMode .Interactive )
                continue
            header .setSectionResizeMode (col ,QHeaderView .ResizeMode .Fixed )
            width =self ._content_width_for_column (
            col ,
            self .TABLE_CELL_HORIZONTAL_PADDING +self .TABLE_EXTRA_COLUMN_PADDING .get (col ,0 ),
            )
            header .resizeSection (col ,width )
            fixed_total +=width

        reason_content_width =self ._content_width_for_column (
        self .SHORT_REASON_COL ,
        self .TABLE_REASON_HORIZONTAL_PADDING ,
        )
        viewport_width =max (
        self .table .viewport ().width (),
        self .table .contentsRect ().width (),
        )
        remaining_width =viewport_width -fixed_total
        reason_width =max (
        self .TABLE_MIN_REASON_WIDTH ,
        reason_content_width ,
        remaining_width ,
        )
        header .resizeSection (self .SHORT_REASON_COL ,reason_width )

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
            "Chỉ những mã đã tick Kiểm thử trong Cài đặt và có trong Market Watch mới chọn được."
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
            selectable = in_market_watch and is_backtested
            checkbox.setEnabled(selectable)
            checkbox.setChecked(selectable and symbol in selected_set)
            if not selectable:
                if not is_backtested:
                    checkbox.setToolTip("Mã này chưa được đánh dấu Kiểm thử trong Cài đặt.")
                elif not in_market_watch:
                    checkbox.setToolTip("Mã này chưa có trong Market Watch của MT5.")
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


class ScannerColumnsHelpDialog (QDialog ):
    ICON_COL_WIDTH =64
    COLUMN_COL_WIDTH =190
    MEANING_COL_WIDTH =330
    MIN_ROW_HEIGHT =86
    CELL_VERTICAL_PADDING =42
    CELL_HORIZONTAL_PADDING =18

    COLUMN_HELP :list [dict [str ,str ]]=[
        {"icon":"🏆","column":"Xếp hạng","meaning":"Thứ tự ưu tiên sau khi sắp xếp. Số nhỏ hơn nghĩa là đáng xem trước hơn.","cases":"1 = ưu tiên cao nhất; 2 = tiếp theo; các dòng sau giảm dần mức ưu tiên."},
        {"icon":"💸","column":"Mã","meaning":"Cặp tiền hoặc sản phẩm được quét.","cases":"28 cặp Forex (ngoại hối) + XAU/USD (vàng) + XAG/USD (bạc) + BTC/USD; chỉ hiển thị mã đang có trong Market Watch (danh sách theo dõi) của MT5."},
        {"icon":"🚀","column":"Hành động","meaning":"Mức độ sẵn sàng giao dịch sau khi xét các điều kiện.","cases":"Sẵn sàng = có thể xem xét; Theo dõi = đáng chú ý; Chờ = cần xác nhận; Bỏ qua = chưa đạt hoặc bị chặn."},
        {"icon":"🧭","column":"Xu hướng","meaning":"Thiên hướng giao dịch được hệ thống đánh giá từ điểm BUY (mua) và SELL (bán).","cases":"BUY rõ (mua rõ) / SELL rõ (bán rõ) = nghiêng rõ một phía; BUY yếu / SELL yếu = có nghiêng nhưng chưa mạnh; Trung lập = chưa đủ lệch."},
        {"icon":"🎯","column":"Entry","meaning":"Entry (vùng vào lệnh): vị trí giá hiện tại so với vùng vào lệnh dự kiến.","cases":"Trong vùng = có thể theo sát; Gần vùng = chuẩn bị quan sát; Còn xa = chưa vội; -- = thiếu dữ liệu."},
        {"icon":"🛡️","column":"Quyền","meaning":"Trạng thái cho phép giao dịch dựa trên dữ liệu và rủi ro.","cases":"Được phép = dữ liệu ổn, có thể xem xét; Cẩn trọng = có rủi ro phụ như tin tức hoặc spread (chênh lệch giá); Bị chặn = không nên vào lệnh."},
        {"icon":"🌟","column":"Điểm tốt nhất","meaning":"Điểm cao nhất giữa kịch bản mua và bán.","cases":"Thang 0-100; >= 70 = tốt; 50-69 = trung bình/khá; < 50 = yếu. Điểm này trước khi qua các gate (cổng lọc điều kiện)."},
        {"icon":"✅","column":"Final","meaning":"Final (điểm cuối): điểm sau khi đi qua gate (cổng lọc) và điều kiện xác nhận.","cases":"Bằng Điểm tốt nhất = setup (thiết lập) sạch; thấp hơn = bị cap (giới hạn điểm) hoặc bị phạt; 0 = bị chặn hoàn toàn."},
        {"icon":"🔍","column":"Cơ hội","meaning":"Điểm xếp hạng cơ hội giao dịch trong scanner (bộ quét thị trường).","cases":">= 100 = cơ hội cao; 80-99 = khá; < 50 = thấp. Ưu tiên setup (thiết lập) gần vùng, rõ hướng, ít bị chặn."},
        {"icon":"🧺","column":"Nhóm","meaning":"Nhóm phân loại theo mức độ sẵn sàng.","cases":"Sẵn sàng ngay = ưu tiên cao nhất; Chờ xác nhận = cần thêm tín hiệu; Theo dõi = chưa đủ điều kiện; Bị chặn = không xét."},
        {"icon":"🚦","column":"Trạng thái entry","meaning":"Trạng thái xác nhận entry (vùng vào lệnh) hiện tại.","cases":"Sẵn sàng / Đã xác nhận = có entry; Chờ xác nhận = cần trigger (tín hiệu kích hoạt); Theo dõi vùng = chờ giá; Vô hiệu / Thiếu dữ liệu = không dùng."},
        {"icon":"⏰","column":"M15","meaning":"M15 (khung 15 phút): chất lượng xác nhận entry trên khung thời gian 15 phút.","cases":"strict (xác nhận chặt) = nhiều nến đóng thuận; loose (xác nhận yếu) = tín hiệu chưa mạnh; none (không có) / -- = chưa có dữ liệu hoặc không đạt."},
        {"icon":"📏","column":"Gap","meaning":"Gap (độ lệch điểm): khoảng cách điểm giữa BUY (mua) và SELL (bán).","cases":"Gap (độ lệch điểm) càng lớn thì xu hướng càng rõ; gap >= 10 = lệch rõ; gap < 10 = chưa rõ ràng, cần thận trọng."},
        {"icon":"🟢","column":"Điểm mua","meaning":"Điểm riêng của kịch bản BUY (mua).","cases":"Thang 0-100; >= 65 = khá mạnh; 50-64 = trung bình; < 50 = yếu. Tổng hợp từ xu hướng, động lượng, vị trí, SMC (cấu trúc dòng tiền), rủi ro, vĩ mô."},
        {"icon":"🔴","column":"Điểm bán","meaning":"Điểm riêng của kịch bản SELL (bán).","cases":"Thang 0-100; >= 65 = khá mạnh; 50-64 = trung bình; < 50 = yếu. Tổng hợp từ xu hướng, động lượng, vị trí, SMC (cấu trúc dòng tiền), rủi ro, vĩ mô."},
        {"icon":"🌍","column":"Vĩ mô (0-30)","meaning":"Điểm vĩ mô từ lãi suất, lịch kinh tế, tâm lý rủi ro và bối cảnh tin tức.","cases":">= 22 = macro (vĩ mô) thuận lợi; 15-21 = trung bình; < 15 = bất lợi. Chấm đầu dòng: ● dữ liệu tốt; ○ thiếu 1 phần; ◌ thiếu nhiều."},
        {"icon":"🤝","column":"Thuận vĩ mô","meaning":"Mức độ đồng thuận của vĩ mô với xu hướng kỹ thuật.","cases":"Thuận = vĩ mô cùng chiều với kỹ thuật; Trung tính = chưa rõ; Ngược = mâu thuẫn, cảnh báo nên thận trọng."},
        {"icon":"⚖️","column":"R:R","meaning":"R:R (rủi ro/lợi nhuận): tỷ lệ rủi ro so với lợi nhuận dự kiến của kế hoạch.","cases":"1:2.0 = lợi nhuận kỳ vọng gấp 2 lần rủi ro; >= 1:1.5 = chấp nhận được; < 1:1.0 = quá thấp, thường bị bỏ qua."},
        {"icon":"💡","column":"Lý do chính","meaning":"Tóm tắt ngắn vì sao mã được xếp hạng như vậy.","cases":"Tiền tố AI (trí tuệ nhân tạo): = nhận định do AI viết; không có AI = rule engine (bộ luật chấm điểm) sinh. Luôn đọc kèm trạng thái entry và quyền."},
        {"icon":"🧐","column":"Chi tiết","meaning":"Mở màn hình chi tiết của mã được chọn.","cases":"Bấm ô Xem trên dòng hoặc chọn dòng rồi bấm nút Xem chi tiết để mở Scanner Detail (màn hình chi tiết quét)."},
    ]

    def __init__ (self ,parent :QWidget |None =None )->None :
        super ().__init__ (parent )
        self .setWindowTitle ('Giải thích Bảng kết quả quét')
        self .setObjectName ("ScannerHelpDialog")
        self .setModal (True )
        self .setMinimumSize (920 ,600 )
        self .resize (1040 ,700 )

        layout =QVBoxLayout (self )
        layout .setContentsMargins (20 ,18 ,20 ,16 )
        layout .setSpacing (12 )

        intro =QLabel (
            'Các cột dưới đây giúp đọc nhanh kết quả quét. '
            'Giá trị trong bảng đã được rút gọn để dễ so sánh.'
        )
        intro .setObjectName ("HelperText")
        intro .setWordWrap (True )
        layout .addWidget (intro )

        table =QTableWidget (len (self .COLUMN_HELP ),4 )
        table .setObjectName ("DataTable")
        table .setHorizontalHeaderLabels (['','Cột','Ý nghĩa','Trường hợp thường gặp'])
        table .verticalHeader ().setVisible (False )
        table .setEditTriggers (QTableWidget .EditTrigger .NoEditTriggers )
        table .setSelectionMode (QTableWidget .SelectionMode .NoSelection )
        table .setFocusPolicy (Qt .FocusPolicy .NoFocus )
        table .setWordWrap (True )
        table .setTextElideMode (Qt .TextElideMode .ElideNone )
        table .setAlternatingRowColors (True )
        table .setHorizontalScrollBarPolicy (Qt .ScrollBarPolicy .ScrollBarAlwaysOff )
        table .setVerticalScrollBarPolicy (Qt .ScrollBarPolicy .ScrollBarAsNeeded )
        table .setVerticalScrollMode (QTableWidget .ScrollMode .ScrollPerPixel )
        table .setIconSize (QSize (30 ,30 ))
        table .verticalHeader ().setDefaultSectionSize (self .MIN_ROW_HEIGHT )
        for row ,item in enumerate (self .COLUMN_HELP ):
            icon_item =QTableWidgetItem ("")
            icon_item .setFlags (Qt .ItemFlag .ItemIsEnabled )
            icon_item .setTextAlignment (Qt .AlignmentFlag .AlignCenter )
            column_item =QTableWidgetItem ("")
            column_item .setFlags (Qt .ItemFlag .ItemIsEnabled )
            column_item .setTextAlignment (Qt .AlignmentFlag .AlignTop |Qt .AlignmentFlag .AlignLeft )
            meaning_item =QTableWidgetItem ("")
            meaning_item .setFlags (Qt .ItemFlag .ItemIsEnabled )
            meaning_item .setTextAlignment (Qt .AlignmentFlag .AlignTop |Qt .AlignmentFlag .AlignLeft )
            cases_item =QTableWidgetItem ("")
            cases_item .setFlags (Qt .ItemFlag .ItemIsEnabled )
            cases_item .setTextAlignment (Qt .AlignmentFlag .AlignTop |Qt .AlignmentFlag .AlignLeft )
            table .setItem (row ,0 ,icon_item )
            table .setItem (row ,1 ,column_item )
            table .setItem (row ,2 ,meaning_item )
            table .setItem (row ,3 ,cases_item )
            table .setCellWidget (row ,0 ,self ._help_icon_label (item .get ("icon","")))
            table .setCellWidget (row ,1 ,self ._help_cell_label (item .get ("column",""),bold =False ))
            table .setCellWidget (row ,2 ,self ._help_cell_label (item .get ("meaning","")))
            table .setCellWidget (row ,3 ,self ._help_cell_label (item .get ("cases","")))
        header =table .horizontalHeader ()
        header .setSectionResizeMode (0 ,QHeaderView .ResizeMode .Fixed )
        header .resizeSection (0 ,self .ICON_COL_WIDTH )
        header .setSectionResizeMode (1 ,QHeaderView .ResizeMode .Fixed )
        header .resizeSection (1 ,self .COLUMN_COL_WIDTH )
        header .setSectionResizeMode (2 ,QHeaderView .ResizeMode .Fixed )
        header .resizeSection (2 ,self .MEANING_COL_WIDTH )
        header .setSectionResizeMode (3 ,QHeaderView .ResizeMode .Stretch )
        header .setMinimumSectionSize (30 )
        self .help_table =table
        layout .addWidget (table ,1 )

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 8, 0, 0)
        buttons_layout.addStretch(1)
        close_btn = action_button("❌ Đóng")
        close_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(close_btn)
        layout.addLayout(buttons_layout)
        self ._sync_help_table_layout ()

    def showEvent (self ,event )->None :
        super ().showEvent (event )
        if hasattr (self ,"help_table"):
            self ._sync_help_table_layout ()

    def resizeEvent (self ,event )->None :
        super ().resizeEvent (event )
        if hasattr (self ,"help_table"):
            QTimer .singleShot (0 ,self ._sync_help_table_layout )

    def _help_cell_label (self ,text :str ,*,bold :bool =False )->QLabel :
        label =QLabel (text )
        label .setObjectName ("ScannerHelpCell")
        label .setWordWrap (True )
        label .setTextInteractionFlags (Qt .TextInteractionFlag .NoTextInteraction )
        label .setAlignment (Qt .AlignmentFlag .AlignTop |Qt .AlignmentFlag .AlignLeft )
        label .setContentsMargins (9 ,8 ,9 ,8 )
        label .setSizePolicy (QSizePolicy .Policy .Expanding ,QSizePolicy .Policy .Preferred )
        if bold :
            font =label .font ()
            font .setBold (True )
            label .setFont (font )
        return label

    def _help_icon_label (self ,text :str )->QLabel :
        label =QLabel (text )
        label .setObjectName ("ScannerHelpEmoji")
        label .setAlignment (Qt .AlignmentFlag .AlignCenter )
        label .setContentsMargins (0 ,0 ,0 ,0 )
        label .setMinimumSize (self .ICON_COL_WIDTH ,self .MIN_ROW_HEIGHT )
        label .setSizePolicy (QSizePolicy .Policy .Expanding ,QSizePolicy .Policy .Expanding )
        font =label .font ()
        font .setFamily ("Segoe UI Emoji")
        font .setPointSize (13 )
        label .setFont (font )
        label .setStyleSheet ("background: transparent;")
        return label

    def _sync_help_table_layout (self )->None :
        table =self .help_table
        header =table .horizontalHeader ()
        viewport_width =max (table .viewport ().width (),self .width ()-80 )
        scrollbar_width =table .verticalScrollBar ().sizeHint ().width ()
        fixed_width =self .ICON_COL_WIDTH +self .COLUMN_COL_WIDTH +self .MEANING_COL_WIDTH
        cases_width =max (360 ,viewport_width -fixed_width -scrollbar_width -6 )
        header .resizeSection (0 ,self .ICON_COL_WIDTH )
        header .resizeSection (1 ,self .COLUMN_COL_WIDTH )
        header .resizeSection (2 ,self .MEANING_COL_WIDTH )
        header .resizeSection (3 ,cases_width )

        column_widths ={1 :self .COLUMN_COL_WIDTH ,2 :self .MEANING_COL_WIDTH ,3 :cases_width}
        for row ,item in enumerate (self .COLUMN_HELP ):
            heights =[self .MIN_ROW_HEIGHT ]
            for col ,key in ((1 ,"column"),(2 ,"meaning"),(3 ,"cases")):
                label =table .cellWidget (row ,col )
                if isinstance (label ,QLabel ):
                    content_width =max (80 ,column_widths [col ]-self .CELL_HORIZONTAL_PADDING )
                    label .setFixedWidth (column_widths [col ])
                    text_rect =label .fontMetrics ().boundingRect (
                    QRect (0 ,0 ,content_width ,2000 ),
                    Qt .TextFlag .TextWordWrap ,
                    item .get (key ,""),
                    )
                    heights .append (text_rect .height ()+self .CELL_VERTICAL_PADDING )
            row_height =max (heights )
            table .setRowHeight (row ,row_height )
            icon_label =table .cellWidget (row ,0 )
            if isinstance (icon_label ,QLabel ):
                icon_label .setFixedSize (header .sectionSize (0 ),row_height )

    @staticmethod
    def _style_icon_for_row (row :int )->int |None :
        """Map row index to QStyle.StandardPixmap for a meaningful icon.

        Returns None when no suitable Qt icon exists; caller falls back to
        the emoji text already stored in the item.
        """
        return [
            QStyle .StandardPixmap .SP_ArrowUp,           # 0  Xep hang
            QStyle .StandardPixmap .SP_DriveNetIcon,       # 1  Ma
            QStyle .StandardPixmap .SP_MediaPlay,           # 2  Hanh dong
            QStyle .StandardPixmap .SP_ArrowForward,        # 3  Xu huong
            QStyle .StandardPixmap .SP_FileDialogContentsView,  # 4  Entry
            QStyle .StandardPixmap .SP_DialogApplyButton,   # 5  Quyen
            QStyle .StandardPixmap .SP_FileDialogInfoView,  # 6  Diem tot nhat
            QStyle .StandardPixmap .SP_DialogOkButton,      # 7  Final
            QStyle .StandardPixmap .SP_FileDialogListView,  # 8  Co hoi
            QStyle .StandardPixmap .SP_DirOpenIcon,         # 9  Nhom
            QStyle .StandardPixmap .SP_MessageBoxQuestion,  # 10 Trang thai entry
            QStyle .StandardPixmap .SP_MediaPause,          # 11 M15
            QStyle .StandardPixmap .SP_ArrowRight,          # 12 Gap
            QStyle .StandardPixmap .SP_ArrowUp,             # 13 Diem mua
            QStyle .StandardPixmap .SP_ArrowDown,           # 14 Diem ban
            QStyle .StandardPixmap .SP_ComputerIcon,        # 15 Vi mo (0-30)
            QStyle .StandardPixmap .SP_CommandLink,         # 16 Thuan vi mo
            QStyle .StandardPixmap .SP_FileDialogDetailedView,  # 17 R:R
            QStyle .StandardPixmap .SP_MessageBoxInformation,   # 18 Ly do chinh
            QStyle .StandardPixmap .SP_FileDialogDetailedView,  # 19 Chi tiet
        ][row ]
