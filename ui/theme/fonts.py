"""
Font constants - định nghĩa font chuẩn cho toàn bộ ứng dụng.
Import các biến này thay vì hard-code font-family/size trực tiếp trong code.

Cách dùng:
    from ui.theme.fonts import get_font, FONT_SIZE_TITLE
    label.setFont(get_font(FONT_SIZE_TITLE, bold=True))

Hoặc dùng trong style sheet (QSS):
    from ui.theme.fonts import FONT_FAMILY, FONT_SIZE_BODY
    widget.setStyleSheet(f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_BODY}pt;")
"""

from PyQt6.QtGui import QFont

# ============================================================
# FONT FAMILY - Font chữ chuẩn toàn app
# ============================================================
FONT_FAMILY = "Segoe UI"
FONT_FAMILY_FALLBACK = ["Segoe UI", "Roboto", "Arial", "sans-serif"]

# Font riêng cho số liệu (giá, %, điểm AI) - cần canh cột đều
FONT_FAMILY_NUMBER = "Consolas"
FONT_FAMILY_NUMBER_FALLBACK = ["Consolas", "JetBrains Mono", "Courier New", "monospace"]

# ============================================================
# FONT SIZE - Các cấp size chuẩn (đơn vị: pt)
# ============================================================
FONT_SIZE_TITLE = 14       # Tiêu đề màn hình, tên panel (bold)
FONT_SIZE_SUBTITLE = 12    # Tiêu đề phụ, tên section (bold)
FONT_SIZE_BODY = 10        # Text thường, label, nội dung bảng (regular)
FONT_SIZE_NUMBER = 11      # Giá, % , điểm AI, RR (semi-bold, dùng font monospace)
FONT_SIZE_SMALL = 9        # Ghi chú, timestamp, phụ đề nhỏ (regular)
FONT_SIZE_BUTTON = 10      # Nút bấm (medium)


# ============================================================
# HELPER FUNCTIONS - Tạo QFont nhanh, tránh lặp code
# ============================================================
def get_font(size: int = FONT_SIZE_BODY, bold: bool = False, family: str = FONT_FAMILY) -> QFont:
    """
    Tạo QFont chuẩn theo size/family đã định nghĩa.

    Args:
        size: size chữ (pt), dùng 1 trong các hằng số FONT_SIZE_*
        bold: True nếu muốn chữ đậm
        family: mặc định FONT_FAMILY, đổi sang FONT_FAMILY_NUMBER nếu cần font số

    Returns:
        QFont đã cấu hình sẵn
    """
    font = QFont(family, size)
    font.setBold(bold)
    return font


def get_title_font() -> QFont:
    """Font cho tiêu đề màn hình / tên panel."""
    return get_font(FONT_SIZE_TITLE, bold=True)


def get_subtitle_font() -> QFont:
    """Font cho tiêu đề phụ / tên section."""
    return get_font(FONT_SIZE_SUBTITLE, bold=True)


def get_body_font() -> QFont:
    """Font cho text thường / label / nội dung bảng."""
    return get_font(FONT_SIZE_BODY, bold=False)


def get_number_font(bold: bool = True) -> QFont:
    """Font cho số liệu (giá, %, điểm AI, RR) - dùng font monospace để canh cột."""
    return get_font(FONT_SIZE_NUMBER, bold=bold, family=FONT_FAMILY_NUMBER)


def get_small_font() -> QFont:
    """Font cho ghi chú / timestamp / phụ đề nhỏ."""
    return get_font(FONT_SIZE_SMALL, bold=False)


def get_button_font() -> QFont:
    """Font cho nút bấm."""
    return get_font(FONT_SIZE_BUTTON, bold=False)


# ============================================================
# QSS STRING - Dùng nếu style bằng style sheet thay vì QFont object
# ============================================================
QSS_FONT_BASE = f"font-family: '{FONT_FAMILY}', {', '.join(FONT_FAMILY_FALLBACK[1:])};"

QSS_TITLE = f"{QSS_FONT_BASE} font-size: {FONT_SIZE_TITLE}pt; font-weight: bold;"
QSS_SUBTITLE = f"{QSS_FONT_BASE} font-size: {FONT_SIZE_SUBTITLE}pt; font-weight: bold;"
QSS_BODY = f"{QSS_FONT_BASE} font-size: {FONT_SIZE_BODY}pt; font-weight: normal;"
QSS_NUMBER = f"font-family: '{FONT_FAMILY_NUMBER}', monospace; font-size: {FONT_SIZE_NUMBER}pt; font-weight: 600;"
QSS_SMALL = f"{QSS_FONT_BASE} font-size: {FONT_SIZE_SMALL}pt; font-weight: normal;"
QSS_BUTTON = f"{QSS_FONT_BASE} font-size: {FONT_SIZE_BUTTON}pt; font-weight: 500;"
