from __future__ import annotations

import re


TERM_TEXT = {
    "ready": "Sẵn sàng",
    "watch": "Theo dõi",
    "wait": "Chờ",
    "wait_for_confirmation": "Chờ xác nhận",
    "stand_aside": "Đứng ngoài",
    "skip": "Bỏ qua",
    "buy": "Mua",
    "sell": "Bán",
    "neutral": "Trung lập",
    "bullish": "Tăng",
    "bearish": "Giảm",
    "allowed": "Được phép",
    "caution": "Cẩn trọng",
    "blocked": "Bị chặn",
    "trend_up": "Xu hướng tăng",
    "trend_down": "Xu hướng giảm",
    "range": "Đi ngang",
    "volatile": "Biến động mạnh",
    "news_sensitive": "Nhạy tin tức",
    "unknown": "Chưa rõ",
    "normal": "Bình thường",
    "abnormal": "Bất thường",
    "high": "Cao",
    "medium": "Trung bình",
    "low": "Thấp",
    "holiday": "Ngày nghỉ",
    "confirmed_entry": "Đã xác nhận điểm vào",
    "waiting_confirmation": "Chờ xác nhận",
    "watch_zone": "Vùng theo dõi",
    "invalidated": "Đã vô hiệu",
    "no_setup": "Không có thiết lập",
    "none": "Chưa có",
    "zone_broken": "Vùng giá đã bị phá",
    "h1_bullish_engulfing": "Nến H1 bao trùm tăng",
    "h1_bearish_engulfing": "Nến H1 bao trùm giảm",
    "h1_bullish_rejection": "Nến H1 rút chân tăng",
    "h1_bearish_rejection": "Nến H1 rút râu giảm",
    "h1_bullish_break": "H1 phá lên",
    "h1_bearish_break": "H1 phá xuống",
    "h1_bos_bullish": "H1 phá cấu trúc tăng",
    "h1_bos_bearish": "H1 phá cấu trúc giảm",
    "h1_choch_bullish": "H1 đảo cấu trúc tăng",
    "h1_choch_bearish": "H1 đảo cấu trúc giảm",
    "h4_bos_bullish": "H4 phá cấu trúc tăng",
    "h4_bos_bearish": "H4 phá cấu trúc giảm",
    "liquidity_sweep_low": "Quét thanh khoản đáy",
    "liquidity_sweep_high": "Quét thanh khoản đỉnh",
    "HH/HL": "Đỉnh cao hơn / đáy cao hơn",
    "LH/LL": "Đỉnh thấp hơn / đáy thấp hơn",
    "mixed": "Hỗn hợp",
    "Asia": "Phiên Á",
    "London": "Phiên London",
    "New York": "Phiên New York",
    "Late US": "Cuối phiên Mỹ",
    "win": "Thắng",
    "loss": "Thua",
    "timeout": "Hết thời gian giữ lệnh",
    "hawkish": "Thắt chặt",
    "dovish": "Nới lỏng",
    "fallback_neutral": "Dự phòng trung lập",
}


PHRASE_TRANSLATIONS = [
    ("No clean setup", "Không có thiết lập giao dịch sạch"),
    ("stand aside", "đứng ngoài"),
    ("better", "tốt hơn"),
    ("Buy/Sell score", "Điểm mua/bán"),
    ("Buy score", "Điểm mua"),
    ("Sell score", "Điểm bán"),
    ("Trade permission", "Quyền giao dịch"),
    ("H4 structure", "Cấu trúc H4"),
    ("D1 structure", "Cấu trúc D1"),
    ("Market Regime", "Trạng thái thị trường"),
    ("Direction Bias", "Thiên hướng giao dịch"),
    ("Risk/Reward", "Tỷ lệ rủi ro/lợi nhuận"),
    ("Entry Zone", "Vùng vào lệnh"),
    ("Stop Loss", "Cắt lỗ"),
    ("Take Profit", "Chốt lời"),
    ("Spread", "Chênh lệch giá mua-bán"),
    ("displacement", "độ dịch chuyển"),
    ("premium", "vùng giá cao"),
    ("discount", "vùng giá thấp"),
    ("equilibrium", "vùng cân bằng"),
    ("waiting confirmation", "chờ xác nhận"),
    ("watch zone", "vùng theo dõi"),
    ("confirmed entry", "đã xác nhận điểm vào"),
    ("price action", "diễn biến giá"),
    ("central bank", "ngân hàng trung ương"),
    ("interest rate", "lãi suất"),
    ("rate cut", "cắt giảm lãi suất"),
    ("rate hike", "tăng lãi suất"),
    ("inflation", "lạm phát"),
    ("employment", "việc làm"),
    ("non-farm", "bảng lương phi nông nghiệp"),
    ("payrolls", "bảng lương"),
    ("GDP", "GDP (tổng sản phẩm quốc nội)"),
    ("CPI", "CPI (chỉ số giá tiêu dùng)"),
    ("PMI", "PMI (chỉ số quản lý thu mua)"),
    ("Fed", "Fed (Cục Dự trữ Liên bang Mỹ)"),
    ("FOMC", "FOMC (Ủy ban Thị trường Mở Liên bang)"),
    ("BoC", "BoC (Ngân hàng Trung ương Canada)"),
    ("ECB", "ECB (Ngân hàng Trung ương châu Âu)"),
    ("BoE", "BoE (Ngân hàng Trung ương Anh)"),
    ("BoJ", "BoJ (Ngân hàng Trung ương Nhật Bản)"),
    ("RBA", "RBA (Ngân hàng Trung ương Úc)"),
    ("RBNZ", "RBNZ (Ngân hàng Trung ương New Zealand)"),
    ("SNB", "SNB (Ngân hàng Trung ương Thụy Sĩ)"),
    ("hawkish", "thắt chặt"),
    ("dovish", "nới lỏng"),
    ("neutral", "trung lập"),
    ("bullish", "tăng"),
    ("bearish", "giảm"),
]


def vi_term(value: object) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        return "--"
    return TERM_TEXT.get(text, TERM_TEXT.get(text.lower(), text))


def vi_text(value: object) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        return "--"
    if text in TERM_TEXT or text.lower() in TERM_TEXT:
        return vi_term(text)

    result = text
    for source, target in PHRASE_TRANSLATIONS:
        result = re.sub(rf"\b{re.escape(source)}\b", target, result, flags=re.IGNORECASE)

    result = re.sub(r"\bBUY\b", "mua", result)
    result = re.sub(r"\bSELL\b", "bán", result)
    result = re.sub(r"\bbuy\b", "mua", result)
    result = re.sub(r"\bsell\b", "bán", result)
    return result
