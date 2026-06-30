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
QTextEdit ,
QVBoxLayout ,
QWidget ,
)
from services .mt5_service import MT5Service 
from services .data_provider import DataProvider
from services .settings_service import SettingsService 
from ui .screens .shared import action_button ,card ,labeled_value ,page_header 


class ScannerTableModel (QAbstractTableModel ):
    COLUMNS =[
    ("rank","STT"),
    ("symbol","Mã"),
    ("scanner_action","Hành động"),
    ("direction_bias","Hướng"),
    ("price_vs_zone","Entry"),
    ("trade_permission","Quyền"),
    ("opportunity_score","Điểm"),
    ("risk_reward","R:R"),
    ("macro_bias","Vĩ mô"),
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
            if key in {"rank","scanner_action","direction_bias","price_vs_zone","trade_permission","opportunity_score","risk_reward","macro_bias","detail_action"}:
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
            "ready":QColor ("#10b981"),
            "watch":QColor ("#f59e0b"),
            "wait":QColor ("#ea580c"),
            "skip":QColor ("#e11d48"),
            }.get (action )
        if key =="direction_bias":
            side =self ._direction_bias_side (row .get (key ))
            return {"buy":QColor ("#ea580c"),"sell":QColor ("#f43f5e")}.get (side )
        if key =="trade_permission":
            return {
            "allowed":QColor ("#10b981"),
            "caution":QColor ("#f59e0b"),
            "blocked":QColor ("#e11d48"),
            }.get (str (row .get (key )))
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
    SHORT_REASON_COL =8  # overridden in __init__
    TABLE_CELL_HORIZONTAL_PADDING =24
    TABLE_EXTRA_COLUMN_PADDING ={1 :18 ,2 :18 ,5 :18 ,7 :18 ,9 :24}
    TABLE_REASON_HORIZONTAL_PADDING =30
    TABLE_MIN_REASON_WIDTH =150

    def __init__ (self ,navigate =None ,*, app =None )->None :
        super ().__init__ ()
        self .navigate =navigate
        self .app =app
        self .settings_service =app .settings_service if app else SettingsService ()
        self .data_provider =app .data_provider if app else MT5Service ()
        self .scanner_controller =app .scanner_controller if app else ScannerController (self .settings_service ,data_provider=self .data_provider )
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

    # ------------------------------------------------------------------
    # Show Orders button
    # ------------------------------------------------------------------
    def _dim_show_orders_button(self) -> None:
        """Dim the 'Hiển thị lệnh' button to indicate no scan data available."""
        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False
        muted_fg = "#9ca3af" if light else "#6b7280"
        muted_border = "#d1d5db" if light else "#374151"
        self.show_orders_button.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:500; padding:0px 6px;"
            f"  min-height:24px; max-height:24px;"
            f"  background:transparent; color:{muted_fg};"
            f"  border:1px solid {muted_border}; border-radius:6px;"
            f"}}"
        )

    def _highlight_show_orders_button(self) -> None:
        """Highlight the 'Hiển thị lệnh' button after a scan completes."""
        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False
        accent_bg = "#D94625" if light else "#ea580c"
        accent_hover = "#E0533C" if light else "#f97316"
        self.show_orders_button.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:700; padding:0px 6px;"
            f"  min-height:24px; max-height:24px;"
            f"  background:{accent_bg}; color:#ffffff; border:none; border-radius:6px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{accent_hover};"
            f"}}"
        )

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
        title_text = "Lệnh đã vào MT5" if auto_trade_enabled else "Lệnh sẽ được khớp"
        dlg.setWindowTitle(f"📋 {title_text}")
        dlg.setMinimumSize(940, 560)
        dlg.resize(980, 620)
        dlg.setObjectName("AnalysisDetailDialog")

        # Lư Trung Hỏa theme color variables
        lth_bg = "#D94625" if light else "#ea580c"
        lth_hover = "#E0533C" if light else "#f97316"
        disabled_bg = "#e5e7eb" if light else "#1f2937"
        disabled_fg = "#9ca3af" if light else "#4b5563"
        disabled_border = "#d1d5db" if light else "#374151"

        active_btn_style = f"""
            QPushButton {{
                font-size: 11px;
                font-weight: bold;
                padding-left: 12px;
                padding-right: 8px;
                padding-top: 0px;
                padding-bottom: 0px;
                min-height: 22px;
                max-height: 22px;
                border-radius: 4px;
                background-color: {lth_bg};
                color: #ffffff;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {lth_hover};
            }}
        """

        disabled_btn_style = f"""
            QPushButton {{
                font-size: 11px;
                font-weight: bold;
                padding-left: 12px;
                padding-right: 8px;
                padding-top: 0px;
                padding-bottom: 0px;
                min-height: 22px;
                max-height: 22px;
                border-radius: 4px;
                background-color: {disabled_bg};
                color: {disabled_fg};
                border: 1px solid {disabled_border};
            }}
        """

        # Action button helper for manual trade execution
        def execute_manual_order(order_info: dict, btn: QPushButton) -> None:
            btn.setEnabled(False)
            btn.setText("Đang đặt...")
            btn.setStyleSheet(disabled_btn_style)
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

            symbol = order_info.get("symbol")
            broker_symbol = order_info.get("broker_symbol")
            side = order_info.get("side")
            volume = order_info.get("volume")
            stop_loss = order_info.get("stop_loss")
            take_profit = order_info.get("take_profit")

            # Validate required numeric fields
            try:
                vol_f = float(volume or 0.0)
                sl_f = float(stop_loss) if stop_loss is not None else 0.0
                tp_f = float(take_profit) if take_profit is not None else 0.0
            except (TypeError, ValueError):
                QMessageBox.warning(dlg, "Lỗi dữ liệu",
                    f"Dữ liệu lệnh {symbol} không hợp lệ (volume/SL/TP).")
                btn.setEnabled(True)
                btn.setText("⚡ Vào lệnh")
                btn.setStyleSheet(active_btn_style)
                return
            if vol_f <= 0 or sl_f <= 0 or tp_f <= 0:
                QMessageBox.warning(dlg, "Lỗi dữ liệu",
                    f"Dữ liệu lệnh {symbol} không hợp lệ (volume/SL/TP phải > 0).\n"
                    f"Vol={vol_f}, SL={sl_f}, TP={tp_f}")
                btn.setEnabled(True)
                btn.setText("⚡ Vào lệnh")
                btn.setStyleSheet(active_btn_style)
                return

            if not broker_symbol:
                try:
                    available = self.data_provider.available_symbols()
                    broker_symbol = self.data_provider.resolve_symbol(symbol, available)
                except Exception:
                    broker_symbol = None

            if not broker_symbol:
                QMessageBox.warning(dlg, "Lỗi vào lệnh", f"Không tìm thấy mã broker cho {symbol}")
                btn.setEnabled(True)
                btn.setText("⚡ Vào lệnh")
                btn.setStyleSheet(active_btn_style)
                return

            # --- Backtest config + distance gate checks ---
            gate_blocked = False
            try:
                settings = self.settings_service.load()
                # Normalize symbol format: rows use "USDCHF", settings use "USD/CHF"
                sym_cfg = settings.trading.symbol_settings.get(symbol)
                if sym_cfg is None and "/" not in symbol and len(symbol) == 6:
                    slash_key = symbol[:3] + "/" + symbol[3:]
                    sym_cfg = settings.trading.symbol_settings.get(slash_key)
                if sym_cfg and sym_cfg.backtest:
                    # Regime check
                    cfg_regime = (sym_cfg.auto_trade_regime or "").strip().lower()
                    row_regime = str(order_info.get("market_regime", "")).strip().lower()
                    if cfg_regime and row_regime and row_regime != cfg_regime:
                        QMessageBox.warning(dlg, "Không đạt điều kiện vào lệnh",
                            f"{symbol}: chế độ thị trường hiện tại ({row_regime}) "
                            f"không khớp cấu hình backtest ({cfg_regime}).")
                        gate_blocked = True

                    # Side check
                    if not gate_blocked:
                        cfg_side = (sym_cfg.auto_trade_side or "").strip().lower()
                        order_side = str(order_info.get("side", "")).strip().lower()
                        if cfg_side in ("buy", "sell") and order_side != cfg_side:
                            QMessageBox.warning(dlg, "Không đạt điều kiện vào lệnh",
                                f"{symbol}: hướng lệnh ({order_side}) không khớp "
                                f"cấu hình backtest ({cfg_side}).")
                            gate_blocked = True

                    # Min RR check
                    if not gate_blocked:
                        cfg_min_rr = float(sym_cfg.min_expected_rr or 0)
                        if cfg_min_rr > 0:
                            row_rr = order_info.get("expected_effective_rr")
                            try:
                                row_rr_f = float(row_rr) if row_rr is not None else 0.0
                            except (TypeError, ValueError):
                                row_rr_f = 0.0
                            if row_rr_f < cfg_min_rr:
                                QMessageBox.warning(dlg, "Không đạt điều kiện vào lệnh",
                                    f"{symbol}: Expected RR ({row_rr_f:.2f}) thấp hơn "
                                    f"ngưỡng backtest ({cfg_min_rr:.2f}).")
                                gate_blocked = True

                # Entry zone check: price must be inside entry zone
                if not gate_blocked:
                    entry_zone = order_info.get("entry_zone")
                    if isinstance(entry_zone, list) and len(entry_zone) >= 2:
                        try:
                            entry_low = float(entry_zone[0])
                            entry_high = float(entry_zone[1])
                        except (TypeError, ValueError):
                            entry_low = entry_high = 0.0

                        if entry_low > 0 and entry_high > 0:
                            try:
                                import MetaTrader5 as mt5
                                tick = mt5.symbol_info_tick(broker_symbol)
                                order_side = str(order_info.get("side", "")).strip().lower()
                                current_price = float(tick.ask) if order_side == "buy" else float(tick.bid)
                            except Exception:
                                current_price = float(order_info.get("entry_price", 0) or 0)

                            if current_price > 0 and not (entry_low <= current_price <= entry_high):
                                QMessageBox.warning(dlg, "Giá ngoài vùng entry",
                                    f"{symbol}: giá hiện tại {current_price:.5f} nằm ngoài vùng entry "
                                    f"[{entry_low:.5f}–{entry_high:.5f}].\n\n"
                                    f"Chỉ vào lệnh khi giá nằm trong vùng entry.")
                                gate_blocked = True
            except Exception:
                pass  # If gate check fails for any reason, allow the order

            if gate_blocked:
                btn.setEnabled(True)
                btn.setText("⚡ Vào lệnh")
                btn.setStyleSheet(active_btn_style)
                return

            try:
                # Pre-check: MT5 terminal algo trading status
                try:
                    import MetaTrader5 as mt5
                    term_info = mt5.terminal_info()
                    if term_info and not getattr(term_info, "trade_allowed", True):
                        QMessageBox.warning(dlg, "Không thể vào lệnh",
                            f"MT5 đang chặn giao dịch tự động (Algo Trading).\n\n"
                            f"Vào MT5 → Tools → Options → Expert Advisors → "
                            f"tích chọn 'Allow Algo Trading'.\n\n"
                            f"Sau đó thử lại.")
                        btn.setEnabled(True)
                        btn.setText("⚡ Vào lệnh")
                        btn.setStyleSheet(active_btn_style)
                        return
                except Exception:
                    pass  # terminal_info() not available, proceed anyway

                if self.data_provider.has_open_position_or_order(broker_symbol):
                    QMessageBox.information(dlg, "Thông báo", f"Đã có lệnh/position cho {symbol} ({broker_symbol}).")
                    btn.setText("Đã có lệnh")
                    btn.setStyleSheet(disabled_btn_style)
                    return

                order_res = self.data_provider.place_market_order(
                    symbol=symbol,
                    broker_symbol=broker_symbol,
                    side=side,
                    volume=vol_f,
                    stop_loss=sl_f,
                    take_profit=tp_f,
                    comment=f"AMA Manual {symbol}",
                )

                if order_res and getattr(order_res, "success", False):
                    QMessageBox.information(dlg, "Thành công",
                        f"Đặt lệnh {side.upper()} {symbol} thành công!\n"
                        f"ID: {getattr(order_res, 'order_id', '--')}")
                    btn.setText("Đã vào lệnh")
                    btn.setEnabled(False)
                    btn.setStyleSheet(disabled_btn_style)
                else:
                    msg = str(getattr(order_res, "message", "") or "MT5 từ chối lệnh.")
                    # Detect common MT5 issues and give actionable guidance
                    hint = ""
                    msg_lower = msg.lower()
                    if "autotrading disabled" in msg_lower:
                        hint = ("\n\nMT5 đang chặn giao dịch tự động.\n"
                                "Vào MT5 → Tools → Options → Expert Advisors → "
                                "tích chọn 'Allow Algo Trading'.")
                    elif "trade is disabled" in msg_lower:
                        hint = ("\n\nMã này có thể đã bị vô hiệu hóa giao dịch trong MT5.\n"
                                "Kiểm tra Market Watch: chuột phải lên mã → Trade.")
                    elif "not enough money" in msg_lower:
                        hint = "\n\nTài khoản không đủ margin/ký quỹ. Giảm khối lượng hoặc nạp thêm."
                    elif "off quotes" in msg_lower or "requote" in msg_lower:
                        hint = "\n\nThị trường biến động mạnh. Thử lại sau vài giây."
                    QMessageBox.warning(dlg, "Đặt lệnh thất bại",
                        f"Đặt lệnh {symbol} thất bại:\n{msg}{hint}")
                    btn.setEnabled(True)
                    btn.setText("⚡ Thử lại")
                    btn.setStyleSheet(active_btn_style)
            except Exception as e:
                QMessageBox.critical(dlg, "Lỗi hệ thống", f"Lỗi khi đặt lệnh {symbol}:\n{str(e)}")
                btn.setEnabled(True)
                btn.setText("⚡ Vào lệnh")
                btn.setStyleSheet(active_btn_style)

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
                    if self.data_provider.has_open_position_or_order(broker_symbol):
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

            # R:R
            rr = order.get("risk_reward")
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

        close_btn = action_button("❌ Đóng")
        active_bg = "#D94625" if light else "#ea580c"
        active_hover = "#E0533C" if light else "#f97316"
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size:12px; font-weight:500; padding:0px 16px 0px 20px;"
            f"  background:transparent;"
            f"  color:{'#4b5563' if light else '#9ca3af'};"
            f"  border:1px solid {'#d1d5db' if light else '#4b5563'};"
            f"  border-radius:6px; min-height:24px; max-height:24px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{'#fce8e5' if light else '#2c1910'};"
            f"  color:{active_bg};"
            f"  border:1px solid {active_bg};"
            f"}}"
        )
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
                    "note": str(o.get("message", o.get("status", ""))),
                })
            return result

        # Not auto-trade: compute would-be orders from scan rows
        # Apply the SAME gates as _execute_auto_trades + _is_auto_trade_candidate
        try:
            settings = self.settings_service.load()
        except Exception:
            settings = None

        result: list[dict] = []
        for row in rows:
            analysis = row.get("analysis_result")
            if not isinstance(analysis, dict):
                continue
            if row.get("scanner_group") == "blocked":
                continue
            if str(row.get("trade_permission", "")).strip().lower() == "blocked":
                continue
            journal = row.get("journal_feedback") if isinstance(row.get("journal_feedback"), dict) else {}
            if journal.get("decision_cap") in {"TRADE_BLOCKED", "WATCH_ONLY"}:
                continue

            best_side = str(row.get("best_side", ""))
            if best_side not in ("buy", "sell"):
                continue

            symbol = str(row.get("symbol", "--"))

            # --- Backtest config gate (same as _is_auto_trade_candidate) ---
            if settings:
                sym_cfg = settings.trading.symbol_settings.get(symbol)
                if sym_cfg is None and "/" not in symbol and len(symbol) == 6:
                    slash_key = symbol[:3] + "/" + symbol[3:]
                    sym_cfg = settings.trading.symbol_settings.get(slash_key)

                if sym_cfg and sym_cfg.backtest:
                    # Regime
                    cfg_regime = (sym_cfg.auto_trade_regime or "").strip().lower()
                    row_regime = str(row.get("market_regime", "")).strip().lower()
                    if cfg_regime and row_regime and row_regime != cfg_regime:
                        continue

                    # Side
                    cfg_side = (sym_cfg.auto_trade_side or "").strip().lower()
                    if cfg_side in ("buy", "sell") and best_side != cfg_side:
                        continue

                    # Min RR
                    cfg_min_rr = float(sym_cfg.min_expected_rr or 0)
                    if cfg_min_rr > 0:
                        row_rr = row.get("expected_effective_rr")
                        try:
                            row_rr_f = float(row_rr) if row_rr is not None else 0.0
                        except (TypeError, ValueError):
                            row_rr_f = 0.0
                        if row_rr_f < cfg_min_rr:
                            continue

                    # Min Score
                    cfg_min_score = int(sym_cfg.min_score or 0)
                    if cfg_min_score > 0:
                        best_score = int(row.get("best_score", 0) or 0)
                        if best_score < cfg_min_score:
                            continue

            scenarios = analysis.get("scenarios", [])
            if not isinstance(scenarios, list):
                continue
            scenario = next((s for s in scenarios if isinstance(s, dict) and s.get("type") == best_side), None)
            if not scenario:
                continue

            entry_zone = scenario.get("entry_zone")
            if isinstance(entry_zone, list) and len(entry_zone) >= 2:
                entry_low = float(entry_zone[0])
                entry_high = float(entry_zone[1])
                ep = scenario.get("entry_price")
                entry_price = float(ep) if ep is not None else (entry_high if best_side == "buy" else entry_low)
            else:
                entry_low = entry_high = 0.0
                entry_price = None

            # --- Entry zone check: price must be inside entry zone ---
            technical = analysis.get("technical", {}) if isinstance(analysis, dict) else {}
            if not isinstance(technical, dict):
                technical = {}
            current_price = float(technical.get("price", 0) or 0)

            if entry_low > 0 and entry_high > 0 and current_price > 0:
                if not (entry_low <= current_price <= entry_high):
                    continue  # outside entry zone

            take_profit = scenario.get("take_profit")
            if isinstance(take_profit, list) and take_profit:
                tp = float(take_profit[0])
            else:
                try:
                    tp = float(take_profit)
                except (TypeError, ValueError):
                    tp = None

            sl = scenario.get("stop_loss")
            try:
                sl = float(sl)
            except (TypeError, ValueError):
                sl = None

            sizing = scenario.get("position_sizing", {})
            if not isinstance(sizing, dict):
                sizing = {}
            vol = sizing.get("suggested_lot")

            rr = scenario.get("risk_reward", "")

            action = str(row.get("scanner_action", ""))
            note = {
                "ready": "Sẵn sàng",
                "watch": "Theo dõi",
                "wait": "Chờ",
            }.get(action, action)

            # Extra fields for gate checks in manual order
            result.append({
                "symbol": str(row.get("symbol", "--")),
                "broker_symbol": str(row.get("broker_symbol") or "").strip(),
                "side": best_side,
                "entry_price": entry_price,
                "stop_loss": sl,
                "take_profit": tp,
                "volume": vol,
                "risk_reward": rr,
                "note": note,
                "entry_zone": entry_zone,
                "market_regime": str(row.get("market_regime", "")),
                "expected_effective_rr": row.get("expected_effective_rr"),
                "best_score": row.get("best_score", 0),
            })

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
        self .table .setVerticalScrollBarPolicy (Qt .ScrollBarPolicy .ScrollBarAlwaysOn )
        self .table .viewport ().installEventFilter (self )
        self ._configure_table_columns ()
        self .table .setSortingEnabled (False )
        self .table .clicked .connect (self ._table_clicked )
        self .table .doubleClicked .connect (self ._table_double_clicked )
        frame .layout ().addWidget (self .table ,1 )
        return frame 

    def _show_columns_help (self )->None :
        selected = self.table.selectionModel().selectedRows()
        if selected:
            row_index = selected[0].row()
            row_data = self.table_model.row_at(row_index)
            if row_data:
                dialog = ScannerRowExplanationDialog(row_data, self.table_model, self)
                dialog.exec()
                return

        dialog =ScannerColumnsHelpDialog (self )
        dialog .exec ()

    def refresh_status (self )->None :
        status =self .data_provider .connection_status ()
        self .status_labels ["MT5"].setText ('Đã kết nối'if status .connected and status .logged_in else 'Chưa kết nối đầy đủ')
        self ._refresh_symbol_availability (status )
        self ._refresh_scan_button_state ()
        self ._update_status_summary ()

    def _selected_symbols (self )->list [str ]:
        allowed =set (self .scan_symbols )&self .market_watch_symbols
        return [symbol for symbol in self .selected_scan_symbols if symbol in allowed]

    def _refresh_symbol_availability (self ,status )->None :
        matches =self .data_provider .configured_symbols_in_market_watch ()if status .connected else []
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
            if cfg:
                # Use min_score if set, otherwise fall back to decision_ready
                eff_min_score = cfg.min_score if cfg.min_score > 0 else cfg.decision_ready
                thresholds[symbol] = {
                    "ready": eff_min_score,
                    "watch": cfg.decision_watch,
                    "wait": cfg.decision_wait,
                    "min_score_gap": 10,
                    "min_rr": cfg.min_expected_rr or 0,
                }
        symbol_auto_trade: dict[str, dict] = {}
        for symbol in symbols:
            cfg = settings.trading.symbol_settings.get(symbol)
            if cfg and cfg.backtest:
                regime = (cfg.auto_trade_regime or "").strip()
                side = (cfg.auto_trade_side or "").strip()
                min_rr = cfg.min_expected_rr or 0.0
                if regime or side in ("buy", "sell") or min_rr:
                    symbol_auto_trade[symbol] = {
                        "regime": cfg.auto_trade_regime,
                        "side": cfg.auto_trade_side,
                        "min_rr": cfg.min_expected_rr or 0,
                        "min_score": cfg.min_score if cfg.min_score > 0 else cfg.decision_ready,
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
        server_time =self .data_provider .server_time_utc ()
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

        header_label = QLabel(f"Giải thích chi tiết cho cặp {symbol}")
        header_label.setObjectName("HelpHeaderLabel")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)

        self.table = QTableWidget()
        self.table.setObjectName("DataTable")
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
        keys_to_show = [
            ("Hành động", "scanner_action", "action_reason"),
            ("Xu hướng", "direction_bias", "bias_reason"),
            ("Entry", "price_vs_zone", "entry_reason"),
            ("Quyền", "trade_permission", "permission_reason"),
            ("Điểm tốt nhất", "best_score", "best_reason"),
            ("Điểm mua", "buy_score", "buy_reason"),
            ("Điểm bán", "sell_score", "sell_reason"),
            ("Vĩ mô", "macro_score", "macro_reason"),
            ("Final", "final_score", "final_reason"),
            ("Cơ hội", "opportunity_score", "opportunity_reason"),
            ("Lý do chính", "short_reason", None),
        ]

        self.row_items = []
        for title, key, reason_key in keys_to_show:
            val = self.row_data.get(key)
            if val is None or val == "":
                continue
                
            display_val = self.table_model._display_value(key, val, self.row_data)
            color = self.table_model._foreground(self.row_data, key)
            color_hex = color.name() if color else "#e5e7eb"
            
            reason_text = self.row_data.get(reason_key) if reason_key else None
            
            general_cases = ""
            default_exp = ""
            for help_item in ScannerColumnsHelpDialog.COLUMN_HELP:
                if help_item["column"] == title:
                    general_cases = help_item.get("cases", "")
                    default_exp = help_item.get("meaning", "")
                    break
                    
            explanation = ""
            if reason_text:
                explanation = str(reason_text)
            else:
                if general_cases:
                    explanation = f"{default_exp}\n({general_cases})"
                else:
                    explanation = default_exp
            
            self.row_items.append({
                "param": title,
                "value": display_val,
                "color_hex": color_hex,
                "explanation": explanation
            })

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

        QTimer.singleShot(10, self._sync_table_layout)

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



class ScannerColumnsHelpDialog (QDialog ):
    COLUMN_COL_WIDTH =150
    MEANING_COL_WIDTH =320
    MIN_ROW_HEIGHT =32
    CELL_VERTICAL_PADDING =32
    CELL_HORIZONTAL_PADDING =34

    COLUMN_HELP :list [dict [str ,str ]]=[
        {"icon":"💸","column":"Mã","meaning":"Cặp tiền hoặc sản phẩm được quét.","cases":"28 cặp Forex (ngoại hối) + XAU/USD (vàng) + XAG/USD (bạc) + BTC/USD; chỉ hiển thị mã đang có trong Market Watch (danh sách theo dõi) của MT5."},
        {"icon":"🚀","column":"Hành động","meaning":"Mức độ sẵn sàng giao dịch sau khi xét các điều kiện.","cases":"Sẵn sàng = có thể xem xét; Theo dõi = đáng chú ý; Chờ = cần xác nhận; Bỏ qua = chưa đạt hoặc bị chặn."},
        {"icon":"🧭","column":"Hướng","meaning":"Thiên hướng giao dịch được hệ thống đánh giá từ điểm BUY (mua) và SELL (bán).","cases":"BUY rõ (mua rõ) / SELL rõ (bán rõ) = nghiêng rõ một phía; BUY yếu / SELL yếu = có nghiêng nhưng chưa mạnh; Trung lập = chưa đủ lệch."},
        {"icon":"🎯","column":"Entry","meaning":"Entry (vùng vào lệnh): vị trí giá hiện tại so với vùng vào lệnh dự kiến.","cases":"Trong vùng = có thể theo sát; Gần vùng = chuẩn bị quan sát; Còn xa = chưa vội; -- = thiếu dữ liệu."},
        {"icon":"🛡️","column":"Quyền","meaning":"Trạng thái cho phép giao dịch dựa trên dữ liệu và rủi ro.","cases":"Được phép = dữ liệu ổn, có thể xem xét; Cẩn trọng = có rủi ro phụ như tin tức hoặc spread (chênh lệch giá); Bị chặn = không nên vào lệnh."},
        {"icon":"🔍","column":"Điểm","meaning":"Điểm xếp hạng cơ hội giao dịch tổng hợp trong scanner (bộ quét thị trường).","cases":">= 100 = cơ hội cao; 80-99 = khá; < 50 = thấp. Ưu tiên setup (thiết lập) gần vùng, rõ hướng, ít bị chặn. Xem chi tiết các điểm thành phần trong trang Chi tiết."},
        {"icon":"⚖️","column":"R:R","meaning":"R:R (rủi ro/lợi nhuận): tỷ lệ rủi ro so với lợi nhuận dự kiến của kế hoạch.","cases":"1:2.0 = lợi nhuận kỳ vọng gấp 2 lần rủi ro; >= 1:1.5 = chấp nhận được; < 1:1.0 = quá thấp, thường bị bỏ qua."},
        {"icon":"🤝","column":"Vĩ mô","meaning":"Mức độ đồng thuận của vĩ mô (lãi suất, DXY, tin tức) với xu hướng kỹ thuật.","cases":"Thuận = vĩ mô cùng chiều với kỹ thuật; Trung tính = chưa rõ; Ngược = mâu thuẫn, cảnh báo nên thận trọng. Điểm vĩ mô chi tiết có trong trang Chi tiết."},
        {"icon":"💡","column":"Lý do chính","meaning":"Tóm tắt ngắn vì sao mã được xếp hạng như vậy.","cases":"Tiền tố AI (trí tuệ nhân tạo): = nhận định do AI viết; không có AI = rule engine (bộ luật chấm điểm) sinh. Luôn đọc kèm trạng thái entry và quyền."},
        {"icon":"🧐","column":"Chi tiết","meaning":"Mở màn hình chi tiết của mã được chọn.","cases":"Bấm ô Xem trên dòng hoặc chọn dòng rồi bấm nút Xem chi tiết để mở Scanner Detail (màn hình chi tiết quét) với đầy đủ điểm thành phần, gate, chẩn đoán và AI kiểm định."},
    ]

    def __init__ (self ,parent :QWidget |None =None )->None :
        super ().__init__ (parent )
        self .setWindowTitle ('Giải thích Bảng kết quả quét')
        self .setObjectName ("ScannerHelpDialog")
        self .setModal (True )
        self .setMinimumSize (780 ,500 )
        self .resize (880 ,600 )

        layout =QVBoxLayout (self )
        layout .setContentsMargins (20 ,18 ,20 ,16 )
        layout .setSpacing (12 )

        intro =QLabel (
            'Các cột dưới đây giúp đọc nhanh kết quả quét. '
            'Giá trị trong bảng đã được rút gọn để dễ so sánh. '
            'Các điểm thành phần (best_score, buy_score, sell_score, final_score, score_gap, macro_score, '
            'entry_status, m15_quality, scanner_group, journal) được hiển thị trong trang Chi tiết.'
        )
        intro .setObjectName ("HelperText")
        intro .setWordWrap (True )
        layout .addWidget (intro )

        table =QTableWidget (len (self .COLUMN_HELP ),3 )
        table .setObjectName ("DataTable")
        table .setHorizontalHeaderLabels (['Cột','Ý nghĩa','Trường hợp thường gặp'])
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
        table .verticalHeader ().setDefaultSectionSize (self .MIN_ROW_HEIGHT )

        # Check if light theme
        try:
            light = SettingsService().load().display.theme == "light"
        except Exception:
            light = False

        if light:
            col0_color = "#0f766e"
            col1_color = "#1f2937"
            col2_color = "#4b5563"
        else:
            col0_color = "#5eead4"
            col1_color = "#e5e7eb"
            col2_color = "#94a3b8"

        for row ,item in enumerate (self .COLUMN_HELP ):
            for col in range (3 ):
                cell =QTableWidgetItem ("")
                cell .setFlags (Qt .ItemFlag .ItemIsEnabled )
                cell .setTextAlignment (Qt .AlignmentFlag .AlignTop |Qt .AlignmentFlag .AlignLeft )
                table .setItem (row ,col ,cell )
            table .setCellWidget (row ,0 ,self ._help_cell_label (item .get ("column",""),bold =True ,color =col0_color))
            table .setCellWidget (row ,1 ,self ._help_cell_label (item .get ("meaning",""),color =col1_color))
            table .setCellWidget (row ,2 ,self ._help_cell_label (item .get ("cases",""),color =col2_color))
        header =table .horizontalHeader ()
        header .setSectionResizeMode (0 ,QHeaderView .ResizeMode .Fixed )
        header .resizeSection (0 ,self .COLUMN_COL_WIDTH )
        header .setSectionResizeMode (1 ,QHeaderView .ResizeMode .Fixed )
        header .resizeSection (1 ,self .MEANING_COL_WIDTH )
        header .setSectionResizeMode (2 ,QHeaderView .ResizeMode .Stretch )
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

    def _help_cell_label (self ,text :str ,*,bold :bool =False ,color :str ="#e5e7eb")->QLabel :
        label =QLabel (text )
        label .setObjectName ("ScannerHelpCell")
        label .setWordWrap (True )
        label .setTextInteractionFlags (Qt .TextInteractionFlag .NoTextInteraction )
        label .setAlignment (Qt .AlignmentFlag .AlignTop |Qt .AlignmentFlag .AlignLeft )
        label .setContentsMargins (6 ,4 ,6 ,4 )
        label .setSizePolicy (QSizePolicy .Policy .Expanding ,QSizePolicy .Policy .Preferred )
        label .setStyleSheet (f"color: {color}; background: transparent;")
        if bold :
            font =label .font ()
            font .setBold (True )
            label .setFont (font )
        return label

    def _sync_help_table_layout (self )->None :
        table =self .help_table
        header =table .horizontalHeader ()
        viewport_width =max (table .viewport ().width (),self .width ()-80 )
        scrollbar_width =table .verticalScrollBar ().sizeHint ().width ()
        fixed_width =self .COLUMN_COL_WIDTH +self .MEANING_COL_WIDTH
        cases_width =max (280 ,viewport_width -fixed_width -scrollbar_width -6 )
        
        header .resizeSection (0 ,self .COLUMN_COL_WIDTH )
        header .resizeSection (1 ,self .MEANING_COL_WIDTH )
        header .resizeSection (2 ,cases_width )

        column_widths ={0 :self .COLUMN_COL_WIDTH ,1 :self .MEANING_COL_WIDTH ,2 :cases_width}
        
        for row ,item in enumerate (self .COLUMN_HELP ):
            heights =[self .MIN_ROW_HEIGHT ]
            for col in range (3 ):
                label =table .cellWidget (row ,col )
                if isinstance (label ,QLabel ):
                    usable_width = max(50, column_widths[col] - 24)
                    label .setFixedWidth (usable_width)
                    heights .append (label .heightForWidth (usable_width) + 24)
            
            row_height =max (heights )
            table .setRowHeight (row ,row_height )


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
                cleaned = cleaned.strip().rstrip(":").strip()
                # Keep the heading concise (first 60 chars)
                if len(cleaned) > 60:
                    cleaned = cleaned[:60]
                return (cleaned, icon)
        return None

    def looks_like_heading(line: str) -> bool:
        """Quick check if a line is likely a heading (short, starts with number/marker)."""
        stripped = line.strip()
        if len(stripped) > 80:
            return False
        upper = stripped.upper()
        # Starts with optional number/marker + keyword
        if re.match(r"^[\d\s.)\-•*#]+\s*", stripped):
            return any(kw in upper for kw, _ in SECTION_PATTERNS)
        # Or the entire line is just a heading keyword phrase
        return any(kw in upper and len(stripped) < 60 for kw, _ in SECTION_PATTERNS)

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
