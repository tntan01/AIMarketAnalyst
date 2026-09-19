"""R1 — policy geometry cửa sổ chính, kiểm tra thuần bằng QRect/dict.

Không dùng monitor thật: mọi `availableGeometry` đều được bơm vào qua tham số
`screens`, còn state đã lưu là các dict/dataclass dựng tại chỗ.
"""

from __future__ import annotations

import pytest

from PyQt6.QtCore import QRect

from ui.window_state import (
    MINIMUM_WINDOW_SIZE,
    REASON_CLAMPED,
    REASON_DEV_NORMAL,
    REASON_FAUX_MAXIMIZED,
    REASON_FIRST_LAUNCH,
    REASON_INVALID_STATE,
    REASON_NO_SCREEN,
    REASON_OFF_SCREEN,
    REASON_SAVED_MAXIMIZED,
    REASON_SAVED_NORMAL,
    SavedWindowState,
    clamp_to_available,
    covers_work_area,
    is_acceptably_visible,
    is_faux_maximized_normal_rect,
    normal_window_rect,
    parse_saved_state,
    resolve_startup,
    violates_top_chrome,
    visible_fraction,
)

# Viewport contract: Full HD/150% sau taskbar (1920×1080 vật lý, taskbar 48px).
FULL_HD_150 = QRect(0, 0, 1280, 688)
FULL_HD = QRect(0, 0, 1920, 1080)
# Vùng làm việc logical của máy báo lỗi F-R5-01 (1920×1200 @150%, có taskbar).
WORK_AREA_1280x760 = QRect(0, 0, 1280, 760)
# State thật đọc được trên máy đó: cao đúng bằng work area, mép trên và mép
# phải áp sát vùng làm việc, lệch 30px trái, cờ maximized=false.
FAUX_MAXIMIZED_STATE = SavedWindowState(QRect(30, 0, 1250, 752), False)
# Chiều cao title bar logical thật của platform (Qt `PM_TitleBarHeight`).
NATIVE_TITLE_BAR_INSET = 21


def _state(x: int, y: int, width: int, height: int, *, maximized: bool = False):
    return SavedWindowState(QRect(x, y, width, height), maximized)


def _raw(x=100, y=100, width=1280, height=800, maximized=False):
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "maximized": maximized,
    }


# --- parse_saved_state -------------------------------------------------------


def test_missing_state_is_not_parsed() -> None:
    assert parse_saved_state(None) is None
    assert parse_saved_state({}) is None


def test_valid_state_is_parsed() -> None:
    parsed = parse_saved_state(_raw(x=200, y=150, width=1400, height=900))
    assert parsed is not None
    assert parsed.rect == QRect(200, 150, 1400, 900)
    assert parsed.maximized is False


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(_raw(x="khong-phai-so"), id="non-numeric-x"),
        pytest.param(_raw(width=None), id="missing-width"),
        pytest.param(_raw(maximized="khong-phai-bool"), id="bad-maximized"),
        pytest.param({**_raw(), "maximized": None}, id="null-maximized"),
        pytest.param(_raw(width=0, height=0), id="zero-size"),
        pytest.param(_raw(width=640, height=400), id="below-minimum-size"),
        pytest.param(_raw(width=-1280), id="negative-width"),
        pytest.param({"x": 10, "y": 10, "width": 1280}, id="incomplete-keys"),
    ],
)
def test_corrupt_or_obsolete_state_is_rejected(raw) -> None:
    assert parse_saved_state(raw) is None


def test_ini_style_string_values_are_accepted() -> None:
    parsed = parse_saved_state(
        {"x": "12", "y": "34", "width": "1280", "height": "720", "maximized": "true"}
    )
    assert parsed is not None
    assert parsed.rect == QRect(12, 34, 1280, 720)
    assert parsed.maximized is True


# --- visibility thresholds ---------------------------------------------------


def test_visible_fraction_counts_intersection_area() -> None:
    assert visible_fraction(QRect(0, 0, 1000, 500), QRect(0, 0, 1000, 500)) == 1.0
    assert visible_fraction(QRect(500, 0, 1000, 500), QRect(0, 0, 1000, 500)) == 0.5
    assert visible_fraction(QRect(2000, 0, 1000, 500), QRect(0, 0, 1000, 500)) == 0.0


def test_visibility_requires_area_and_minimum_intersection() -> None:
    screen = QRect(0, 0, 1280, 720)
    # 30% diện tích nhưng chỉ 100px ngang nhìn thấy ⇒ không đủ 160×120.
    assert is_acceptably_visible(QRect(1180, 0, 1000, 720), screen) is False
    # 30% diện tích và giao 300×720 ⇒ đạt.
    assert is_acceptably_visible(QRect(980, 0, 1000, 720), screen) is True
    # 20% diện tích, dù giao lớn hơn 160×120 ⇒ không đạt ngưỡng 25%.
    assert is_acceptably_visible(QRect(1024, 0, 1280, 720), screen) is False


# --- startup decision table --------------------------------------------------


def test_first_launch_maximizes() -> None:
    decision = resolve_startup(None, [FULL_HD_150])
    assert decision.maximized is True
    assert decision.rect is None
    assert decision.reason == REASON_FIRST_LAUNCH


def test_invalid_state_maximizes() -> None:
    # State đọc được nhưng nhỏ hơn mức minimum đang áp ⇒ quay về maximize.
    decision = resolve_startup(_state(0, 0, 1280, 800), [FULL_HD], minimum_size=(1400, 900))
    assert decision.maximized is True
    assert decision.reason == REASON_INVALID_STATE

    # State hỏng/sai kiểu bị parse thành None ⇒ cùng nhánh first-launch.
    assert parse_saved_state(_raw(width="x")) is None
    assert resolve_startup(None, [FULL_HD_150]).reason == REASON_FIRST_LAUNCH


def test_no_available_geometry_maximizes() -> None:
    decision = resolve_startup(_state(0, 0, 1280, 800), [])
    assert decision.maximized is True
    assert decision.reason == REASON_NO_SCREEN


def test_saved_maximized_reopens_maximized() -> None:
    decision = resolve_startup(_state(40, 40, 1280, 800, maximized=True), [FULL_HD])
    assert decision.maximized is True
    assert decision.rect is None
    assert decision.reason == REASON_SAVED_MAXIMIZED


def test_saved_normal_geometry_is_restored_unchanged() -> None:
    decision = resolve_startup(_state(60, 40, 1280, 800), [FULL_HD])
    assert decision.maximized is False
    assert decision.rect == QRect(60, 40, 1280, 800)
    assert decision.reason == REASON_SAVED_NORMAL


def test_geometry_fully_off_screen_maximizes() -> None:
    decision = resolve_startup(_state(2400, 300, 1280, 800), [FULL_HD])
    assert decision.maximized is True
    assert decision.reason == REASON_OFF_SCREEN


def test_geometry_mostly_off_screen_maximizes() -> None:
    # Chỉ ~6% diện tích còn nhìn thấy ⇒ coi như mất màn hình.
    decision = resolve_startup(_state(1800, 0, 1280, 800), [FULL_HD])
    assert decision.maximized is True
    assert decision.reason == REASON_OFF_SCREEN


def test_partially_visible_geometry_is_clamped_into_the_new_screen() -> None:
    # Cửa sổ từng nằm trên màn hình rộng hơn; sau khi đổi monitor chỉ còn một
    # phần nằm trong vùng làm việc mới ⇒ phải kẹp lại nhưng giữ kích thước.
    saved = _state(400, 120, 1000, 600)
    decision = resolve_startup(saved, [FULL_HD_150])
    assert decision.maximized is False
    assert decision.reason == REASON_CLAMPED
    # x kẹp về 1280-1000, y kẹp về 688-600; kích thước giữ nguyên.
    assert decision.rect == QRect(280, 88, 1000, 600)
    assert is_acceptably_visible(decision.rect, FULL_HD_150) is True


def test_clamped_geometry_picks_the_screen_with_largest_intersection() -> None:
    left = QRect(0, 0, 1280, 720)
    right = QRect(1280, 0, 1280, 720)
    decision = resolve_startup(_state(1300, 60, 900, 600), [left, right])
    assert decision.maximized is False
    assert decision.rect.x() >= right.left()


# --- Full HD / 150% ----------------------------------------------------------


def test_minimum_window_size_fits_full_hd_150_after_taskbar() -> None:
    # Lỗi R0: minimum height 700 > available height 688 ⇒ cửa sổ cao hơn màn hình.
    assert MINIMUM_WINDOW_SIZE[1] <= FULL_HD_150.height()
    assert MINIMUM_WINDOW_SIZE[0] <= FULL_HD_150.width()


def test_saved_geometry_taller_than_the_work_area_is_capped() -> None:
    # State cũ lưu ở màn hình cao hơn (700 > 688) ⇒ kẹp xuống đúng vùng làm việc.
    # Bản cùng cỡ nhưng phủ trọn bề ngang là faux-maximized, xem mục F-R5-01.
    decision = resolve_startup(_state(0, 0, 900, 700), [FULL_HD_150])
    assert decision.maximized is False
    assert decision.rect == QRect(0, 0, 900, 688)
    assert decision.reason == REASON_CLAMPED


def test_clamp_never_exceeds_a_work_area_smaller_than_the_minimum() -> None:
    tiny = QRect(0, 0, 700, 400)
    clamped = clamp_to_available(QRect(0, 0, 1280, 800), tiny)
    assert clamped == QRect(0, 0, 700, 400)


# --- F-R5-01: geometry normal "giả maximized" ---------------------------------
#
# Input tái lập: máy 1920×1200 @150% ⇒ vùng làm việc logical 1280×760; state đã
# lưu `QRect(30, 0, 1250, 752), maximized=False` — cao đúng bằng vùng làm việc,
# mép trên và mép phải áp sát, lệch 30px trái. Cửa sổ trông như maximized nhưng
# state là normal nên title bar/nút hệ thống không thao tác được.


def test_covers_work_area_requires_both_dimensions() -> None:
    assert covers_work_area(QRect(0, 0, 1280, 760), WORK_AREA_1280x760) is True
    # Đúng ngưỡng 95% ở cả hai chiều vẫn tính là phủ.
    assert covers_work_area(QRect(0, 0, 1216, 722), WORK_AREA_1280x760) is True
    # Chỉ rộng gần bằng hoặc chỉ cao gần bằng thì không.
    assert covers_work_area(QRect(0, 0, 1215, 760), WORK_AREA_1280x760) is False
    assert covers_work_area(QRect(0, 0, 1280, 721), WORK_AREA_1280x760) is False
    # Vùng làm việc suy biến không được coi là "bị phủ".
    assert covers_work_area(QRect(0, 0, 1280, 760), QRect(0, 0, 0, 0)) is False


def test_violates_top_chrome_counts_the_platform_band() -> None:
    # inset 0 = "không có tri thức nền tảng": áp sát mép trên vẫn tính là chạm.
    assert violates_top_chrome(QRect(0, 0, 400, 300), WORK_AREA_1280x760) is True
    assert violates_top_chrome(QRect(0, 1, 400, 300), WORK_AREA_1280x760) is False
    # Có metric thật của platform thì cả dải title bar bị coi là không an toàn.
    assert (
        violates_top_chrome(
            QRect(0, 12, 400, 300),
            WORK_AREA_1280x760,
            chrome_inset=NATIVE_TITLE_BAR_INSET,
        )
        is True
    )
    assert (
        violates_top_chrome(
            QRect(0, 40, 400, 300),
            WORK_AREA_1280x760,
            chrome_inset=NATIVE_TITLE_BAR_INSET,
        )
        is False
    )


def test_faux_maximized_requires_both_conditions() -> None:
    # Chỉ chạm mép trên nhưng cửa sổ nhỏ ⇒ chrome vẫn thao tác được.
    assert (
        is_faux_maximized_normal_rect(QRect(0, 0, 800, 520), WORK_AREA_1280x760)
        is False
    )
    # Chỉ phủ gần toàn vùng làm việc nhưng chừa dải chrome phía trên ⇒ vẫn được.
    assert (
        is_faux_maximized_normal_rect(QRect(30, 40, 1220, 745), WORK_AREA_1280x760)
        is False
    )
    # Đủ cả hai điều kiện ⇒ faux-maximized.
    assert (
        is_faux_maximized_normal_rect(
            FAUX_MAXIMIZED_STATE.rect,
            WORK_AREA_1280x760,
            chrome_inset=NATIVE_TITLE_BAR_INSET,
        )
        is True
    )


def test_faux_maximized_uses_the_platform_chrome_inset() -> None:
    # Cửa sổ chừa 12px phía trên: chưa vi phạm khi chưa biết chiều cao title bar,
    # nhưng vi phạm khi style cho biết title bar cao hơn 12px. Không hard-code
    # offset DPI/vật lý (30/32px) — metric do caller truyền vào.
    rect = QRect(0, 12, 1280, 748)
    assert is_faux_maximized_normal_rect(rect, WORK_AREA_1280x760) is False
    assert (
        is_faux_maximized_normal_rect(
            rect, WORK_AREA_1280x760, chrome_inset=NATIVE_TITLE_BAR_INSET
        )
        is True
    )
    assert (
        resolve_startup(_state(0, 12, 1280, 748), [WORK_AREA_1280x760]).maximized
        is False
    )
    assert (
        resolve_startup(
            _state(0, 12, 1280, 748),
            [WORK_AREA_1280x760],
            chrome_inset=NATIVE_TITLE_BAR_INSET,
        ).reason
        == REASON_FAUX_MAXIMIZED
    )


def test_reported_state_is_faux_maximized_and_maximizes() -> None:
    """Nghiệm thu F-R5-01: state thật của máy báo lỗi phải mở maximized."""
    for inset in (0, NATIVE_TITLE_BAR_INSET):
        decision = resolve_startup(
            FAUX_MAXIMIZED_STATE, [WORK_AREA_1280x760], chrome_inset=inset
        )
        assert decision.maximized is True
        assert decision.rect is None
        assert decision.reason == REASON_FAUX_MAXIMIZED


def test_faux_maximized_reason_code_is_its_own() -> None:
    maximize_reasons = {
        REASON_FIRST_LAUNCH,
        REASON_INVALID_STATE,
        REASON_SAVED_MAXIMIZED,
        REASON_OFF_SCREEN,
        REASON_NO_SCREEN,
    }
    assert REASON_FAUX_MAXIMIZED not in maximize_reasons
    assert REASON_FAUX_MAXIMIZED not in {
        REASON_SAVED_NORMAL,
        REASON_CLAMPED,
        REASON_DEV_NORMAL,
    }


def test_genuinely_normal_window_is_still_restored() -> None:
    """Nghiệm thu F-R5-01: cửa sổ normal thật vẫn restore nguyên trạng."""
    saved = _state(240, 120, 800, 520)
    for inset in (0, NATIVE_TITLE_BAR_INSET):
        decision = resolve_startup(saved, [WORK_AREA_1280x760], chrome_inset=inset)
        assert decision.maximized is False
        assert decision.rect == QRect(240, 120, 800, 520)
        assert decision.reason == REASON_SAVED_NORMAL


def test_full_width_geometry_taller_than_the_work_area_maximizes() -> None:
    """F-R5-01: state này trước đây chỉ bị kẹp thành cửa sổ phủ trọn vùng làm
    việc và chạm mép trên — đúng cửa sổ faux-maximized."""
    decision = resolve_startup(
        _state(0, 0, 1280, 700), [FULL_HD_150], chrome_inset=NATIVE_TITLE_BAR_INSET
    )
    assert decision.maximized is True
    assert decision.rect is None
    assert decision.reason == REASON_FAUX_MAXIMIZED


def test_clamping_never_produces_a_faux_maximized_window() -> None:
    # Kẹp một state cao hơn vùng làm việc sẽ hạ mép trên xuống 0 và phủ trọn vùng
    # làm việc — chính là cửa sổ faux-maximized — nên nhánh này phải maximize
    # thay vì trả về geometry đã kẹp.
    raw = QRect(30, 40, 1220, 745)
    clamped = clamp_to_available(raw, FULL_HD_150)
    assert clamped == QRect(30, 0, 1220, 688)
    assert (
        is_faux_maximized_normal_rect(
            clamped, FULL_HD_150, chrome_inset=NATIVE_TITLE_BAR_INSET
        )
        is True
    )

    decision = resolve_startup(
        _state(30, 40, 1220, 745), [FULL_HD_150], chrome_inset=NATIVE_TITLE_BAR_INSET
    )
    assert decision.maximized is True
    assert decision.reason == REASON_FAUX_MAXIMIZED


# --- dev/test normal window policy -------------------------------------------


def test_normal_window_policy_uses_ratios_and_caps() -> None:
    # min(1440, 0.92×1920)=1440 × min(900, 0.90×1080)=900, canh giữa màn hình.
    rect = normal_window_rect(FULL_HD)
    assert rect.size().width() == 1440
    assert rect.size().height() == 900
    assert rect.center() == FULL_HD.center()


def test_normal_window_policy_shrinks_on_a_small_work_area() -> None:
    rect = normal_window_rect(FULL_HD_150)
    assert rect.width() == round(1280 * 0.92)
    assert rect.height() == min(900, round(688 * 0.90))
    assert FULL_HD_150.contains(rect)


def test_dev_normal_window_is_explicit_and_never_reads_saved_state() -> None:
    saved = _state(60, 40, 1280, 800, maximized=True)
    decision = resolve_startup(
        saved,
        [FULL_HD],
        normal_window_size=(1440, 900),
    )
    assert decision.reason == REASON_DEV_NORMAL
    assert decision.maximized is False
    assert decision.rect is not None
    assert decision.rect.size().width() == 1440
