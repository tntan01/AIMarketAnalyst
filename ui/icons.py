"""Bộ icon phẳng (flat SVG) của ứng dụng.

Nguồn icon DUY NHẤT cho UI: mọi nút/thẻ dùng glyph monochrome từ registry
`ICONS` bên dưới, render qua `QSvgRenderer` và tint theo semantic palette
(`ui.theme.color_for_role` / `ui.theme_manager.current_palette`).

Quy ước:
- Glyph vẽ theo lưới 24x24, stroke-based (stroke-width 2, round caps/joins)
  kiểu feather — nét mảnh, đọc tốt ở 16px, đúng chất "phẳng".
- Màu đặt bằng `currentColor` trên thẻ <svg>; `_svg_bytes()` thay
  `currentColor` bằng hex của palette trước khi parse. KHÔNG hardcode hex
  trong file này (ràng buộc style-lock).
- Cache khóa theo (name, hex[, size, dpr]): đổi theme → hex khác → key
  khác → cache tự "invalidate" mà không cần themeChanged signal.
- `PyQt6.QtSvg` đã có sẵn trong wheel PyQt6/PyQt6-Qt6 — không thêm
  dependency vào requirements.txt.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QIconEngine, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from ui.theme import color_for_role
from ui.theme_manager import current_palette

ICON_VIEWBOX = 24
ICON_DEFAULT_SIZE = 16

# ---------------------------------------------------------------------------
# Glyph registry — geometry only (stroke-based, fill none).
# Tên glyph → markup SVG (viewBox 24×24, stroke="currentColor", stroke-width 2,
# round caps/joins). `currentColor` được thay bằng hex palette trước khi parse.
# ---------------------------------------------------------------------------
ICONS: dict[str, str] = {
    # Mũi tên vòng ~300° + đầu chevron (refresh/reload)
    "refresh": (
        '<polyline points="23 4 23 10 17 10"/>'
        '<polyline points="1 20 1 14 7 14"/>'
        '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10"/>'
        '<path d="M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>'
    ),
    # Vòng tròn + móc hỏi + chấm
    "help-circle": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/>'
    ),
    # Pin định vị + chấm tâm
    "map-pin": (
        '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
        '<circle cx="12" cy="10" r="3"/>'
    ),
    # Đầu robot: anten + thân bo góc + hai mắt (chấm round-cap)
    "bot": (
        '<line x1="12" y1="2" x2="12" y2="5"/>'
        '<rect x="4" y="5" width="16" height="13" rx="3"/>'
        '<line x1="9" y1="11" x2="9.01" y2="11"/>'
        '<line x1="15" y1="11" x2="15.01" y2="11"/>'
    ),
    # Hai đường chéo (đóng)
    "x": (
        '<line x1="18" y1="6" x2="6" y2="18"/>'
        '<line x1="6" y1="6" x2="18" y2="18"/>'
    ),
    # Phích cắm: hai chân + thân + dây
    "plug": (
        '<path d="M12 22v-5"/>'
        '<path d="M9 8V2"/>'
        '<path d="M15 8V2"/>'
        '<path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/>'
    ),
    # Người: đầu tròn + vai
    "user": (
        '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>'
        '<circle cx="12" cy="7" r="4"/>'
    ),
    # Ba cột dọc (biểu đồ)
    "bar-chart": (
        '<line x1="18" y1="20" x2="18" y2="10"/>'
        '<line x1="12" y1="20" x2="12" y2="4"/>'
        '<line x1="6" y1="20" x2="6" y2="14"/>'
    ),
    # Khung + mũi tên góc trên phải (mở link ngoài)
    "external-link": (
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
        '<polyline points="15 3 21 3 21 9"/>'
        '<line x1="10" y1="14" x2="21" y2="3"/>'
    ),
    # Lịch (dự phòng cho tab tin tức)
    "calendar": (
        '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>'
        '<line x1="16" y1="2" x2="16" y2="6"/>'
        '<line x1="8" y1="2" x2="8" y2="6"/>'
        '<line x1="3" y1="10" x2="21" y2="10"/>'
    ),
    # Tia sét (dự phòng cho zone "sắp tới")
    "zap": (
        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
    ),
    # Mắt (dự phòng cho nút "xem")
    "eye": (
        '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    # Kính lúp (tìm kiếm / quét / kiểm định)
    "search": (
        '<circle cx="11" cy="11" r="8"/>'
        '<line x1="21" y1="21" x2="16.65" y2="16.65"/>'
    ),
    # Vuông bo góc (dừng quét / tắt)
    "stop": (
        '<rect x="5" y="5" width="14" height="14" rx="2"/>'
    ),
    # Bảng kẹp (kế hoạch lệnh / áp dụng cấu hình / sao chép)
    "clipboard": (
        '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
        '<rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>'
    ),
    # Máy ảnh (lưu snapshot)
    "camera": (
        '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
        '<circle cx="12" cy="13" r="4"/>'
    ),
    # Dấu tick (áp dụng / chọn / bật)
    "check": (
        '<polyline points="20 6 9 17 4 12"/>'
    ),
    # Tâm ngắm (trailing stop / tỷ lệ thắng)
    "crosshair": (
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="22" y1="12" x2="18" y2="12"/>'
        '<line x1="6" y1="12" x2="2" y2="12"/>'
        '<line x1="12" y1="6" x2="12" y2="2"/>'
        '<line x1="12" y1="22" x2="12" y2="18"/>'
    ),
    # Thùng rác (xóa trailing / xóa bản ghi / hủy lệnh chờ)
    "trash": (
        '<polyline points="3 6 5 6 21 6"/>'
        '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
        '<line x1="10" y1="11" x2="10" y2="17"/>'
        '<line x1="14" y1="11" x2="14" y2="17"/>'
    ),
    # Bút chỉnh (sửa SL/TP / sửa lệnh chờ / điền R)
    "edit": (
        '<path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>'
    ),
    # Tam giác cảnh báo (flatten / missing R / điều kiện chưa đạt)
    "alert-triangle": (
        '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>'
        '<line x1="12" y1="9" x2="12" y2="13"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/>'
    ),
    # Đĩa mềm (lưu cấu hình / lưu ghi chú / lưu nhật ký)
    "save": (
        '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
        '<polyline points="17 21 17 13 7 13 7 21"/>'
        '<polyline points="7 3 7 8 15 8"/>'
    ),
    # Bình nón thí nghiệm (kiểm tra AI / nghiên cứu nâng cao)
    "flask": (
        '<path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"/>'
        '<path d="M8.5 2h7"/>'
        '<path d="M7 16h10"/>'
    ),
    # Thư mục mở (mở kết quả / mở báo cáo)
    "folder-open": (
        '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
    ),
    # Tam giác chạy (chạy backtest / chạy quét / bộ lọc)
    "play": (
        '<polygon points="5 3 19 12 5 21 5 3"/>'
    ),
    # Sách mở (giải thích)
    "book-open": (
        '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>'
        '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>'
    ),
    # Mũi tên xuống khay (đồng bộ MT5)
    "download": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/>'
        '<line x1="12" y1="15" x2="12" y2="3"/>'
    ),
    # Mũi tên trái (quay lại)
    "arrow-left": (
        '<line x1="19" y1="12" x2="5" y2="12"/>'
        '<polyline points="12 19 5 12 12 5"/>'
    ),
    # Mũi tên lên khay (xuất JSON)
    "upload": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="17 8 12 3 7 8"/>'
        '<line x1="12" y1="3" x2="12" y2="15"/>'
    ),
    # Bong bóng ghi chú (cột ghi chú journal)
    "message-square": (
        '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'
    ),
    # Nửa tròn (đóng một phần)
    "half": (
        '<circle cx="12" cy="12" r="9"/>'
        '<line x1="12" y1="3" x2="12" y2="21"/>'
    ),
    # Dấu trừ ngang (chưa xác định / trung tính)
    "minus": (
        '<line x1="5" y1="12" x2="19" y2="12"/>'
    ),
    # Ba gạch ngang (menu sidebar)
    "menu": (
        '<line x1="3" y1="6" x2="21" y2="6"/>'
        '<line x1="3" y1="12" x2="21" y2="12"/>'
        '<line x1="3" y1="18" x2="21" y2="18"/>'
    ),
    # Chấm tin cậy: đầy (cao) / nửa (trung bình) / rỗng (thấp)
    "dot-high": (
        '<circle cx="12" cy="12" r="7" fill="currentColor" stroke="none"/>'
    ),
    "dot-mid": (
        '<circle cx="12" cy="12" r="7"/>'
        '<path d="M12 5a7 7 0 0 1 0 14z" fill="currentColor" stroke="none"/>'
    ),
    "dot-low": (
        '<circle cx="12" cy="12" r="7"/>'
    ),
}

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb} {vb}" '
    'fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)

# (name, hex) -> QSvgRenderer
_renderer_cache: dict[tuple[str, str], QSvgRenderer] = {}
# (name, hex, size, dpr) -> QPixmap
_pixmap_cache: dict[tuple[str, str, int, float], QPixmap] = {}
# (name, hex, size) -> data-URI PNG
_data_uri_cache: dict[tuple[str, str, int], str] = {}


def clear_icon_caches() -> None:
    """Xóa cache renderer/pixmap (dùng trong test; runtime tự invalidate
    theo key khi đổi theme)."""
    _renderer_cache.clear()
    _pixmap_cache.clear()
    _data_uri_cache.clear()


def _svg_bytes(name: str, color_hex: str) -> bytes:
    """Trả SVG hoàn chỉnh của glyph `name`, thay currentColor bằng `color_hex`.

    KeyError nếu tên glyph không tồn tại trong registry.
    """
    body = ICONS[name]
    doc = _SVG_TEMPLATE.format(vb=ICON_VIEWBOX, body=body).replace(
        "currentColor", color_hex
    )
    return doc.encode("utf-8")


def _get_renderer(name: str, color_hex: str) -> QSvgRenderer:
    key = (name, color_hex)
    renderer = _renderer_cache.get(key)
    if renderer is None:
        renderer = QSvgRenderer(QByteArray(_svg_bytes(name, color_hex)))
        if not renderer.isValid():
            raise ValueError(f"Invalid flat SVG glyph: {name}")
        _renderer_cache[key] = renderer
    return renderer


def _device_pixel_ratio() -> float:
    app = QApplication.instance()
    if app is not None:
        screen = app.primaryScreen()
        if screen is not None:
            dpr = screen.devicePixelRatio()
            if dpr > 0:
                return float(dpr)
    return 1.0


def flat_icon(
    name: str,
    role: str = "text",
    *,
    size: int = ICON_DEFAULT_SIZE,
    disabled_role: str = "muted",
    active_role: str | None = None,
) -> QIcon:
    """Trả QIcon vẽ glyph `name` với màu resolve LAZY tại thời điểm vẽ.

    Engine giữ semantic role (không giữ màu) nên icon tự đổi màu khi đổi
    theme: `MainWindow._apply_styles()` → setStyleSheet → repaint →
    `FlatIconEngine.paint()` đọc `current_palette()` mới.
    - Normal/Selected → `role`
    - Disabled → `disabled_role` (tránh auto-grayscale xấu của Qt)
    - Active → `active_role` (nếu truyền), else `role`
    """
    return QIcon(FlatIconEngine(name, role, size, disabled_role, active_role))


def flat_icon_fixed(name: str, color_hex: str, *, size: int = ICON_DEFAULT_SIZE) -> QIcon:
    """QIcon vẽ glyph `name` bằng màu CỐ ĐỊNH `color_hex` (phải resolve từ
    palette ở nơi gọi — không hardcode). Dùng cho trạng thái phái sinh như
    hover của nút link trong bảng, nơi cần lighter/darker của màu role."""
    return QIcon(FlatIconEngine(name, "text", size, "muted", None, fixed_color=color_hex))


class FlatIconEngine(QIconEngine):
    """QIconEngine vẽ glyph SVG từ registry, tint theo palette tại paint-time.

    Nếu `fixed_color` được truyền, mọi mode vẽ bằng hex đó thay vì role —
    dùng cho icon trạng thái ngắn hạn (hover)."""

    def __init__(
        self,
        name: str,
        role: str = "text",
        size: int = ICON_DEFAULT_SIZE,
        disabled_role: str = "muted",
        active_role: str | None = None,
        fixed_color: str | None = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.role = role
        self.size = size
        self.disabled_role = disabled_role
        self.active_role = active_role
        self.fixed_color = fixed_color

    def _role_for_mode(self, mode: QIcon.Mode) -> str:
        if mode == QIcon.Mode.Disabled:
            return self.disabled_role
        if mode == QIcon.Mode.Active and self.active_role:
            return self.active_role
        return self.role

    def paint(self, painter, rect, mode, state) -> None:  # noqa: ANN001
        if self.fixed_color:
            color_hex = self.fixed_color
        else:
            palette = current_palette()
            color_hex = color_for_role(palette, self._role_for_mode(mode))
        renderer = _get_renderer(self.name, color_hex)
        renderer.render(painter, QRectF(rect))

    def pixmap(self, size, mode, state) -> QPixmap:  # noqa: ANN001
        dpr = _device_pixel_ratio()
        pixel = max(1, round(size.width() * dpr))
        image = QImage(pixel, pixel, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            self.paint(painter, QRectF(0.0, 0.0, float(pixel), float(pixel)), mode, state)
        finally:
            painter.end()
        image.setDevicePixelRatio(dpr)
        return QPixmap.fromImage(image)

    def actualSize(self, size, mode, state) -> QSize:  # noqa: ANN001
        side = min(size.width(), size.height())
        return QSize(side, side)

    def key(self) -> str:
        return f"FlatIconEngine/{self.name}"

    def clone(self) -> "FlatIconEngine":
        return FlatIconEngine(
            self.name,
            self.role,
            self.size,
            self.disabled_role,
            self.active_role,
            self.fixed_color,
        )


def flat_data_uri(
    name: str,
    role: str = "text",
    *,
    size: int = ICON_DEFAULT_SIZE,
) -> str:
    """Data-URI PNG của glyph để nhúng `<img>` trong rich text (QTextEdit).

    Màu resolve từ palette theo `role` tại thời điểm gọi (cache khóa theo hex
    nên đổi theme → key mới). Dùng khi rich text cần icon phẳng mà không thể
    đặt QLabel pixmap (vd mục "Phân rã điểm số" tab Chẩn đoán)."""
    color_hex = color_for_role(current_palette(), role)
    key = (name, color_hex, size)
    cached = _data_uri_cache.get(key)
    if cached is not None:
        return cached
    pixmap = flat_pixmap(name, role, size=size)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        pixmap.save(buf, "PNG")
    finally:
        buf.close()
    uri = "data:image/png;base64," + bytes(buf.data().toBase64()).decode("ascii")
    _data_uri_cache[key] = uri
    return uri


def flat_pixmap(
    name: str,
    role: str = "text",
    *,
    size: int = ICON_DEFAULT_SIZE,
    palette=None,
) -> QPixmap:
    """Render glyph `name` thành QPixmap vuông `size`px (DPR-aware), tint theo
    semantic `role` của palette hiện hành (hoặc palette truyền vào)."""
    color_hex = color_for_role(palette or current_palette(), role)
    dpr = _device_pixel_ratio()
    key = (name, color_hex, size, dpr)
    cached = _pixmap_cache.get(key)
    if cached is not None:
        return cached

    renderer = _get_renderer(name, color_hex)
    pixel = max(1, round(size * dpr))
    image = QImage(pixel, pixel, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        renderer.render(painter, QRectF(0.0, 0.0, float(pixel), float(pixel)))
    finally:
        painter.end()
    image.setDevicePixelRatio(dpr)
    pixmap = QPixmap.fromImage(image)
    _pixmap_cache[key] = pixmap
    return pixmap


def flat_pixmap_fixed(
    name: str,
    color_hex: str,
    *,
    size: int = ICON_DEFAULT_SIZE,
) -> QPixmap:
    """Pixmap glyph vẽ bằng màu CỐ ĐỊNH `color_hex` — giá trị phải resolve
    từ palette tại nơi gọi (vd `palette.warning`, `palette.accent_hover`),
    KHÔNG hardcode hex. Dùng cho delegate/hover cần màu ngoài semantic role."""
    dpr = _device_pixel_ratio()
    key = (name, color_hex, size, dpr)
    cached = _pixmap_cache.get(key)
    if cached is not None:
        return cached
    renderer = _get_renderer(name, color_hex)
    pixel = max(1, round(size * dpr))
    image = QImage(pixel, pixel, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        renderer.render(painter, QRectF(0.0, 0.0, float(pixel), float(pixel)))
    finally:
        painter.end()
    image.setDevicePixelRatio(dpr)
    pixmap = QPixmap.fromImage(image)
    _pixmap_cache[key] = pixmap
    return pixmap
