"""Owner duy nhất cho policy geometry của cửa sổ chính (R1).

Module này tách phần *quyết định* hình học ra khỏi `MainWindow` để test được
thuần bằng `QRect`/`dict`, không cần monitor thật:

* `resolve_startup()` — hàm thuần quyết định maximize hay mở ở geometry đã lưu;
* `WindowStateStore` — lớp mỏng bọc `QSettings`, chỉ đọc/ghi trong group
  versioned `ui/main_window/v1`, tách hoàn toàn khỏi `settings.json` nghiệp vụ.

Mọi ngưỡng đều tính trên `QScreen.availableGeometry()` theo **logical pixel**;
không dùng độ phân giải vật lý hay `devicePixelRatio()`.

F-R5-01 bổ sung nhánh *faux-maximized*: geometry normal phủ gần toàn vùng làm
việc **và** chạm dải chrome trên (title bar/nút hệ thống ở mép màn hình) không
được restore nguyên trạng — nó trông như maximized nhưng state là normal nên
người dùng không thao tác được chrome. Nhánh này mở maximized thật. Chiều cao
title bar (`chrome_inset`) do caller truyền vào theo logical pixel; module này
không hard-code offset DPI/vật lý.

Trạng thái lưu là các khóa số nguyên tường minh (`x`, `y`, `width`, `height`,
`maximized`) thay vì blob `saveGeometry()`: contract R1 yêu cầu kẹp geometry
theo `availableGeometry()` trước khi restore, việc đó bắt buộc phải đọc/kiểm
tra được từng thành phần. Đây là "format Qt tương đương" mà kế hoạch cho phép.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from PyQt6.QtCore import QRect, QSettings
from PyQt6.QtWidgets import QMainWindow

from config.constants import APP_ID

SETTINGS_GROUP = "ui/main_window/v1"

GEOMETRY_KEYS = ("x", "y", "width", "height")
MAXIMIZED_KEY = "maximized"
STATE_KEYS = (*GEOMETRY_KEYS, MAXIMIZED_KEY)

# Mức tối thiểu kỹ thuật của app shell theo contract: chỉ để app còn mở được,
# không phải ngưỡng chuyển compact layout (compact là việc của R2/R3).
MINIMUM_WINDOW_SIZE = (800, 500)

# Ngưỡng "còn nhìn thấy đáng kể" trước khi chấp nhận geometry đã lưu.
MIN_VISIBLE_FRACTION = 0.25
MIN_VISIBLE_SIZE = (160, 120)

# Policy cửa sổ normal tường minh cho test/dev (contract R1 mục 4).
DEV_NORMAL_MAX_SIZE = (1440, 900)
DEV_NORMAL_WIDTH_RATIO = 0.92
DEV_NORMAL_HEIGHT_RATIO = 0.90

# Dải chrome hệ thống trên cùng (title bar) theo logical pixel, do caller truyền
# vào. Mặc định 0 = "không có tri thức nền tảng": khi đó cửa sổ áp sát mép trên
# vùng làm việc vẫn tính là chạm dải chrome, vì đó đúng là trạng thái không thao
# tác được mà F-R5-01 xử lý. `MainWindow` lấy metric thật từ Qt style.
DEFAULT_CHROME_INSET = 0

# Ngưỡng "phủ gần toàn vùng làm việc" của F-R5-01, áp cho cả hai chiều: một cửa
# sổ chỉ rộng hoặc chỉ cao gần bằng vùng làm việc vẫn còn chrome thao tác được.
FAUX_MAXIMIZED_COVERAGE_RATIO = 0.95

REASON_FIRST_LAUNCH = "first-launch"
REASON_INVALID_STATE = "invalid-state"
REASON_SAVED_MAXIMIZED = "saved-maximized"
REASON_SAVED_NORMAL = "saved-normal"
REASON_CLAMPED = "clamped-to-available"
REASON_OFF_SCREEN = "off-screen"
REASON_NO_SCREEN = "no-available-geometry"
REASON_FAUX_MAXIMIZED = "faux-maximized-normal"
REASON_DEV_NORMAL = "dev-normal-window"


@dataclass(frozen=True)
class SavedWindowState:
    """Geometry normal + trạng thái maximized đọc từ QSettings."""

    rect: QRect
    maximized: bool


@dataclass(frozen=True)
class StartupDecision:
    """Kết quả policy khởi động: maximize hay mở ở một rect cụ thể."""

    maximized: bool
    rect: QRect | None
    reason: str


def _coerce_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if float(value).is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _coerce_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value) if value in (0, 1) else None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return None


def parse_saved_state(raw: Mapping[str, object] | None) -> SavedWindowState | None:
    """Đọc state thô thành `SavedWindowState`, trả `None` nếu thiếu/sai kiểu.

    Fail-safe theo contract: bất kỳ khóa nào thiếu, sai kiểu, không ép được về
    số nguyên, hoặc kích thước vô lý đều bị coi là state không hợp lệ — không
    raise, không đoán giá trị mặc định.
    """
    if not raw:
        return None
    values: dict[str, int] = {}
    for key in GEOMETRY_KEYS:
        coerced = _coerce_int(raw.get(key))
        if coerced is None:
            return None
        values[key] = coerced
    maximized = _coerce_bool(raw.get(MAXIMIZED_KEY))
    if maximized is None:
        return None
    if values["width"] < MINIMUM_WINDOW_SIZE[0] or values["height"] < MINIMUM_WINDOW_SIZE[1]:
        return None
    return SavedWindowState(
        rect=QRect(values["x"], values["y"], values["width"], values["height"]),
        maximized=maximized,
    )


def visible_fraction(rect: QRect, available: QRect) -> float:
    """Tỷ lệ diện tích của `rect` còn nằm trong `available`."""
    frame_area = rect.width() * rect.height()
    if frame_area <= 0:
        return 0.0
    intersection = rect.intersected(available)
    if intersection.isEmpty():
        return 0.0
    return (intersection.width() * intersection.height()) / frame_area


def is_acceptably_visible(rect: QRect, available: QRect) -> bool:
    """True khi `rect` còn đủ phần nhìn thấy để người dùng thao tác được."""
    intersection = rect.intersected(available)
    if intersection.isEmpty():
        return False
    if (
        intersection.width() < MIN_VISIBLE_SIZE[0]
        or intersection.height() < MIN_VISIBLE_SIZE[1]
    ):
        return False
    return visible_fraction(rect, available) >= MIN_VISIBLE_FRACTION


def covers_work_area(
    rect: QRect,
    available: QRect,
    *,
    coverage: float = FAUX_MAXIMIZED_COVERAGE_RATIO,
) -> bool:
    """True khi `rect` phủ gần toàn bộ vùng làm việc theo cả hai chiều."""
    if available.width() <= 0 or available.height() <= 0:
        return False
    return (
        rect.width() >= available.width() * coverage
        and rect.height() >= available.height() * coverage
    )


def violates_top_chrome(
    rect: QRect,
    available: QRect,
    *,
    chrome_inset: int = DEFAULT_CHROME_INSET,
) -> bool:
    """True khi mép trên cửa sổ nằm trong dải chrome hệ thống của vùng làm việc.

    `chrome_inset` là chiều cao title bar theo logical pixel do caller cung cấp
    (`MainWindow` lấy từ Qt style pixel metric). Mặc định 0 nghĩa là "không có
    tri thức nền tảng": cửa sổ áp sát mép trên vẫn tính là chạm dải chrome, vì
    đó chính là trạng thái không thao tác được mà F-R5-01 xử lý.
    """
    return rect.top() <= available.top() + max(int(chrome_inset), 0)


def is_faux_maximized_normal_rect(
    rect: QRect,
    available: QRect,
    *,
    chrome_inset: int = DEFAULT_CHROME_INSET,
    coverage: float = FAUX_MAXIMIZED_COVERAGE_RATIO,
) -> bool:
    """True khi geometry normal "giả maximized" — không an toàn cho thao tác chrome.

    `rect` là geometry **sẽ hiển thị** (đã kẹp vào `available` nếu cần): cửa sổ
    vừa chạm dải chrome trên (title bar/nút hệ thống ở mép màn hình) vừa phủ gần
    toàn vùng làm việc. Người dùng thấy một cửa sổ trông như đang maximized
    nhưng state lưu là normal, nên phần chrome không thao tác được. Maximize
    thật là trạng thái an toàn tương đương, và là điều người dùng đã ngụ ý khi
    cửa sổ chiếm trọn vùng làm việc.

    Phải thỏa **cả hai** điều kiện: chỉ chạm mép trên (cửa sổ nhỏ nằm sát trên)
    hoặc chỉ phủ rộng (cửa sổ lớn còn chừa dải chrome) đều vẫn thao tác được.
    """
    if not covers_work_area(rect, available, coverage=coverage):
        return False
    return violates_top_chrome(rect, available, chrome_inset=chrome_inset)


def select_screen(rect: QRect, screens: Iterable[QRect]) -> QRect | None:
    """Chọn availableGeometry giao với `rect` nhiều nhất."""
    best: QRect | None = None
    best_area = -1
    for available in screens:
        intersection = rect.intersected(available)
        area = (
            intersection.width() * intersection.height()
            if not intersection.isEmpty()
            else 0
        )
        if area > best_area:
            best = available
            best_area = area
    return best


def clamp_to_available(
    rect: QRect,
    available: QRect,
    *,
    minimum_size: tuple[int, int] = MINIMUM_WINDOW_SIZE,
) -> QRect:
    """Kẹp `rect` vào `available`, giữ kích thước hợp lý.

    Kích thước không bao giờ vượt vùng làm việc — kể cả khi mức minimum của app
    lớn hơn vùng đó (Full HD/150% sau taskbar), vì cửa sổ cao/rộng hơn màn hình
    sẽ làm mất phần dưới của app shell.
    """
    width = min(rect.width(), available.width())
    height = min(rect.height(), available.height())
    width = max(width, min(minimum_size[0], available.width()))
    height = max(height, min(minimum_size[1], available.height()))
    x = min(max(rect.x(), available.left()), available.right() - width + 1)
    y = min(max(rect.y(), available.top()), available.bottom() - height + 1)
    return QRect(x, y, width, height)


def normal_window_rect(
    available: QRect,
    *,
    minimum_size: tuple[int, int] = MINIMUM_WINDOW_SIZE,
) -> QRect:
    """Policy cửa sổ normal tường minh cho test/dev (không đè state người dùng)."""
    width = min(DEV_NORMAL_MAX_SIZE[0], round(available.width() * DEV_NORMAL_WIDTH_RATIO))
    height = min(
        DEV_NORMAL_MAX_SIZE[1], round(available.height() * DEV_NORMAL_HEIGHT_RATIO)
    )
    rect = QRect(
        available.x() + (available.width() - width) // 2,
        available.y() + (available.height() - height) // 2,
        width,
        height,
    )
    return clamp_to_available(rect, available, minimum_size=minimum_size)


def usable_screens(screens: Iterable[QRect]) -> list[QRect]:
    return [
        QRect(rect)
        for rect in screens
        if rect.isValid() and rect.width() > 0 and rect.height() > 0
    ]


def resolve_startup(
    saved: SavedWindowState | None,
    screens: Iterable[QRect],
    *,
    minimum_size: tuple[int, int] = MINIMUM_WINDOW_SIZE,
    normal_window_size: tuple[int, int] | None = None,
    chrome_inset: int = DEFAULT_CHROME_INSET,
) -> StartupDecision:
    """Quyết định trạng thái cửa sổ lúc khởi động.

    Bảng quyết định (theo thứ tự):

    1. Caller xin cửa sổ normal tường minh (test/dev) → dùng policy normal.
    2. Không có geometry khả dụng → maximize (first launch).
    3. Không có `availableGeometry` nào → maximize.
    4. State không hợp lệ/thiếu/sai kiểu/quá nhỏ → maximize.
    5. Lần đóng trước ở trạng thái maximized → maximize.
    6. Geometry normal không còn đủ phần nhìn thấy → maximize.
    7. Geometry normal "giả maximized" — sau khi kẹp vẫn chạm dải chrome trên
       **và** phủ gần toàn vùng làm việc → maximize (F-R5-01).
    8. Geometry normal hợp lệ nhưng lệch một phần (đổi monitor/DPI) → kẹp lại.
    9. Còn lại → khôi phục đúng geometry đã lưu.

    `chrome_inset` là chiều cao title bar theo logical pixel; hàm vẫn thuần và
    deterministic vì metric nền tảng do caller truyền vào, không tự đọc.
    """
    available_rects = usable_screens(screens)

    if normal_window_size is not None and available_rects:
        available = available_rects[0]
        return StartupDecision(
            maximized=False,
            rect=clamp_to_available(
                QRect(
                    available.x()
                    + (available.width() - normal_window_size[0]) // 2,
                    available.y()
                    + (available.height() - normal_window_size[1]) // 2,
                    normal_window_size[0],
                    normal_window_size[1],
                ),
                available,
                minimum_size=minimum_size,
            ),
            reason=REASON_DEV_NORMAL,
        )

    if saved is None:
        return StartupDecision(True, None, REASON_FIRST_LAUNCH)
    if not available_rects:
        return StartupDecision(True, None, REASON_NO_SCREEN)

    rect = QRect(saved.rect)
    if rect.width() < minimum_size[0] or rect.height() < minimum_size[1]:
        return StartupDecision(True, None, REASON_INVALID_STATE)
    if saved.maximized:
        return StartupDecision(True, None, REASON_SAVED_MAXIMIZED)

    target = select_screen(rect, available_rects)
    if target is None or not is_acceptably_visible(rect, target):
        return StartupDecision(True, None, REASON_OFF_SCREEN)

    # F-R5-01 kiểm tra trên geometry **sẽ hiển thị** (sau kẹp), không phải rect
    # thô: kẹp có thể tự tạo ra một cửa sổ chạm mép trên và phủ trọn vùng làm
    # việc, và như vậy vẫn là cửa sổ faux-maximized không thao tác được chrome.
    clamped = clamp_to_available(rect, target, minimum_size=minimum_size)
    if is_faux_maximized_normal_rect(clamped, target, chrome_inset=chrome_inset):
        return StartupDecision(True, None, REASON_FAUX_MAXIMIZED)
    if clamped != rect:
        return StartupDecision(False, clamped, REASON_CLAMPED)
    return StartupDecision(False, clamped, REASON_SAVED_NORMAL)


def default_settings() -> QSettings:
    """QSettings riêng cho UI window state, tách khỏi settings nghiệp vụ."""
    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        APP_ID,
        APP_ID,
    )


class WindowStateStore:
    """Đọc/ghi state cửa sổ trong group `ui/main_window/v1`."""

    def __init__(self, settings: QSettings) -> None:
        self._settings = settings

    def load(self) -> SavedWindowState | None:
        try:
            self._settings.beginGroup(SETTINGS_GROUP)
            try:
                raw = {key: self._settings.value(key) for key in STATE_KEYS}
            finally:
                self._settings.endGroup()
        except Exception:
            # State hỏng/không đọc được không được phép chặn khởi động.
            return None
        return parse_saved_state(raw)

    def save(self, rect: QRect, maximized: bool) -> None:
        self._settings.beginGroup(SETTINGS_GROUP)
        try:
            self._settings.setValue("x", int(rect.x()))
            self._settings.setValue("y", int(rect.y()))
            self._settings.setValue("width", int(rect.width()))
            self._settings.setValue("height", int(rect.height()))
            self._settings.setValue(MAXIMIZED_KEY, bool(maximized))
        finally:
            self._settings.endGroup()
        self._settings.sync()

    def save_from(self, window: QMainWindow) -> None:
        """Lưu trạng thái hiện tại; maximized thì lưu geometry normal."""
        maximized = window.isMaximized()
        rect = window.normalGeometry() if maximized else window.geometry()
        self.save(rect, maximized)

    def clear(self) -> None:
        self._settings.beginGroup(SETTINGS_GROUP)
        try:
            self._settings.remove("")
        finally:
            self._settings.endGroup()
        self._settings.sync()
