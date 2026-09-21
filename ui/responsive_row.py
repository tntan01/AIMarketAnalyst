"""Helper bố cục tự thích ứng theo bề ngang khả dụng (R2/R3).

Gồm: ``ResponsiveRow`` (hàng control tách hai hàng), ``ResponsiveGrid`` (lưới
giảm cột) và ``ResponsiveSplitter`` (hai panel chuyển dọc khi hết chỗ).

Bố cục desktop được giữ nguyên: nhóm trái, khoảng giãn, nhóm phải nằm sát phải
trên một hàng. Khi bề ngang khả dụng nhỏ hơn tổng minimum của hai nhóm, widget
chuyển sang hai hàng — nhóm trái ở trên, nhóm phải ở dưới, vẫn căn phải — thay
vì bóp control hoặc đẩy chúng ra ngoài vùng nhìn thấy.

Hai điểm cốt lõi:

* Hai nhóm nằm ở hai hàng layout **riêng**, không dùng chung một grid cột. Nếu
  dùng chung cột thì minimum của hàng hai hàng bằng *tổng* hai nhóm, tức là việc
  tách hàng không hạ được sàn bề ngang — đúng thứ cần hạ.
* ``minimumSizeHint()`` trả về sàn của chế độ hai hàng, nên chế độ một hàng
  không tự biến mình thành minimum của cả màn hình. Nhờ vậy hàng co được xuống
  dưới bề ngang desktop và tự quyết định ngay lúc resize, không cần breakpoint
  hard-code cho từng screen.
"""

from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

DEFAULT_SPACING = 8


class ResponsiveRow(QWidget):
    """Một hàng control: một hàng khi đủ chỗ, hai hàng khi thiếu ngang."""

    def __init__(
        self,
        *,
        left: Iterable[QWidget] = (),
        right: Iterable[QWidget] = (),
        spacing: int = DEFAULT_SPACING,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ResponsiveRow")
        self._left = list(left)
        self._right = list(right)
        self._spacing = spacing
        self._rows = 0

        self._primary = QWidget(self)
        self._primary.setObjectName("ResponsiveRowPrimary")
        self._primary_layout = QHBoxLayout(self._primary)
        self._primary_layout.setContentsMargins(0, 0, 0, 0)
        self._primary_layout.setSpacing(spacing)

        self._secondary = QWidget(self)
        self._secondary.setObjectName("ResponsiveRowSecondary")
        self._secondary_layout = QHBoxLayout(self._secondary)
        self._secondary_layout.setContentsMargins(0, 0, 0, 0)
        self._secondary_layout.setSpacing(spacing)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # Không để layout tự ghim minimumSize của widget: mặc định Qt sẽ ghim
        # minimum vào bề ngang của chế độ đang dùng, và chế độ một hàng sẽ khoá
        # cứng bề ngang khiến widget không bao giờ co được để tách hàng. Sàn
        # thật được khai qua minimumSizeHint() bên dưới.
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        outer.addWidget(self._primary)
        outer.addWidget(self._secondary)

        # Preferred (không phải Fixed) để Qt dùng minimumSizeHint làm sàn —
        # xem docstring module.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._secondary.setVisible(False)
        self._relayout(force=True)

    # -- bố cục ------------------------------------------------------------

    @staticmethod
    def _widget_floor(widget: QWidget) -> int:
        """Bề ngang tối thiểu mà Qt thật sự cấp cho widget này.

        Bám theo quy tắc của ``qSmartMinSize``: control không co được (Fixed /
        Maximum) giữ nguyên ``sizeHint``, còn lại lấy ``minimumSizeHint``. Nếu
        dùng ``minimumSizeHint`` cho mọi control thì combo/button Fixed sẽ bị
        tính hụt, và hàng tưởng là vừa trong khi layout thật đã tràn.
        """

        policy = widget.sizePolicy().horizontalPolicy()
        explicit = widget.minimumWidth()
        if policy in (QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum):
            return max(
                widget.sizeHint().width(), widget.minimumSizeHint().width(), explicit
            )
        return max(widget.minimumSizeHint().width(), explicit)

    def _line_width(self, widgets: list[QWidget]) -> int:
        if not widgets:
            return 0
        total = sum(self._widget_floor(widget) for widget in widgets)
        return total + self._spacing * (len(widgets) - 1)

    def required_width(self) -> int:
        """Bề ngang tối thiểu để giữ cả hai nhóm trên một hàng."""

        left = self._line_width(self._left)
        right = self._line_width(self._right)
        if not self._left or not self._right:
            return left + right
        return left + right + self._spacing

    def row_count(self) -> int:
        """Số hàng đang dùng (1 hoặc 2) — điểm neo cho test hành vi."""

        return self._rows

    def minimumSizeHint(self) -> QSize:
        floor = max(self._line_width(self._left), self._line_width(self._right))
        return QSize(floor, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    @staticmethod
    def _explicitly_hidden(widget: QWidget) -> bool:
        """Widget bị chính screen ẩn (vd. nút dừng quét) hay không."""

        return widget.testAttribute(Qt.WidgetAttribute.WA_WState_ExplicitShowHide) and (
            widget.isHidden()
        )

    @staticmethod
    def _clear(layout: QHBoxLayout) -> None:
        """Tháo widget và spacer khỏi layout; widget vẫn thuộc row này."""

        while layout.count():
            layout.takeAt(0)

    def _relayout(self, *, force: bool = False) -> None:
        target_rows = 2 if self.width() < self.required_width() else 1
        if target_rows == self._rows and not force:
            return

        # setParent khi đổi hàng làm widget bị ẩn đi; ghi lại ý định ẩn/hiện
        # trước khi tháo để khôi phục đúng, không vô tình bật lại control mà
        # screen đã chủ động ẩn.
        hidden_by_caller = {
            widget: self._explicitly_hidden(widget)
            for widget in (*self._left, *self._right)
        }

        self._clear(self._primary_layout)
        self._clear(self._secondary_layout)
        self._rows = target_rows

        for widget in self._left:
            self._primary_layout.addWidget(widget)
        self._primary_layout.addStretch(1)

        if self._rows == 1:
            for widget in self._right:
                self._primary_layout.addWidget(widget)
            self._secondary.setVisible(False)
        else:
            self._secondary_layout.addStretch(1)
            for widget in self._right:
                self._secondary_layout.addWidget(widget)
            self._secondary.setVisible(True)

        for widget, hidden in hidden_by_caller.items():
            if not hidden:
                widget.show()

        self.updateGeometry()


class ResponsiveSplitter(QSplitter):
    """Splitter hai panel tự chuyển dọc khi không đủ chỗ cho hai panel ngang.

    Ngưỡng lấy từ **không gian layout thật**: tổng bề ngang tối thiểu của hai
    panel cộng thanh chia. Khi bề ngang khả dụng nhỏ hơn ngưỡng đó, hai panel
    xếp trên/dưới để panel thứ hai vẫn nằm trong viewport — thay vì để người
    dùng phải cuộn ngang mới tới được cấu hình chính.

    Ở chế độ dọc, sàn bề ngang của cả splitter chỉ còn ``max(panel)`` nên màn
    hình chứa nó không bị đẩy rộng ra.
    """

    def __init__(
        self,
        first: QWidget,
        second: QWidget,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName("ResponsiveSplitter")
        self.setChildrenCollapsible(False)
        self._first = first
        self._second = second
        self.addWidget(first)
        self.addWidget(second)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)
        self._vertical = False
        # Minimum của panel có thể đổi sau khi dựng (đổi provider, đổi font
        # theo theme, hiện thêm ô nhập) mà bề ngang splitter thì không đổi —
        # không nghe LayoutRequest thì sẽ bỏ sót lúc phải chuyển sang dọc.
        for widget in (self, first, second):
            widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.Resize):
            self._apply_orientation()
        return super().eventFilter(obj, event)

    def required_width(self) -> int:
        """Bề ngang tối thiểu để giữ hai panel cạnh nhau."""

        return (
            ResponsiveRow._widget_floor(self._first)
            + ResponsiveRow._widget_floor(self._second)
            + self.handleWidth()
        )

    def is_vertical(self) -> bool:
        """Đang xếp dọc hay không — điểm neo cho test hành vi."""

        return self._vertical

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        if not self._vertical:
            return hint
        widest = max(
            ResponsiveRow._widget_floor(self._first),
            ResponsiveRow._widget_floor(self._second),
        )
        return QSize(widest, hint.height())

    def available_width(self) -> int:
        """Bề ngang thật mà splitter được phép dùng.

        Khi nằm trong vùng cuộn (Settings), bề ngang khả dụng là viewport của
        vùng cuộn chứ không phải bề ngang hiện tại: ``widgetResizable`` cho
        widget bên trong rộng hơn viewport, nên so với ``width()`` sẽ không bao
        giờ thấy được việc phải cuộn ngang mới tới được panel thứ hai.
        """

        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                return parent.viewport().width()
            parent = parent.parentWidget()
        return self.width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_orientation()

    def _apply_orientation(self) -> None:
        target_vertical = self.available_width() < self.required_width()
        if target_vertical == self._vertical:
            return
        self._vertical = target_vertical
        sizes = self.sizes()
        self.setOrientation(
            Qt.Orientation.Vertical if target_vertical else Qt.Orientation.Horizontal
        )
        # Giữ tỉ lệ đang có khi đổi trục, để đổi viewport không nhảy layout.
        if target_vertical:
            total = sum(sizes) or 1
            self.setSizes([max(1, total // 3), max(1, total - total // 3)])
        else:
            total = sum(sizes) or 1
            left = min(
                max(ResponsiveRow._widget_floor(self._first), total // 4), total // 2
            )
            self.setSizes([left, max(1, total - left)])
        self.updateGeometry()


class ResponsiveGrid(QWidget):
    """Lưới card/ô tự giảm số cột khi thiếu bề ngang.

    Desktop giữ nguyên số cột đã duyệt; khi bề ngang khả dụng nhỏ hơn tổng
    minimum của một hàng đầy đủ, lưới chuyển sang ``compact_columns`` cột và
    xuống nhiều hàng — thay vì bóp mỗi ô tới mức chữ trong ô bị cắt.

    ``stretch=True`` (mặc định) cho các ô giãn đầy bề ngang — dùng cho lưới
    card. ``stretch=False`` giữ mỗi ô đúng bề ngang tự nhiên và xếp trái, đúng
    bố cục dãy nút hiện có, chỉ khác là biết xuống dòng khi thiếu chỗ.
    """

    def __init__(
        self,
        *,
        widgets: Iterable[QWidget] = (),
        columns: int = 4,
        compact_columns: int | None = None,
        spacing: int = DEFAULT_SPACING,
        stretch: bool = True,
        item_min_width: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ResponsiveGrid")
        self._widgets = list(widgets)
        self._columns = max(1, columns)
        self._compact_columns = max(
            1, compact_columns if compact_columns is not None else max(1, self._columns // 2)
        )
        self._spacing = spacing
        self._stretch = stretch
        # Bề ngang tối thiểu của MỘT ô, khi caller biết rõ nội dung cần bao
        # nhiêu (widget tự báo minimum ~0 vì nhãn dùng elide thì không dùng được).
        self._item_min_width = item_min_width
        self._active_columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)
        # Cùng lý do như ResponsiveRow: không để layout ghim minimumSize của
        # widget, sàn thật khai qua minimumSizeHint().
        self._grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        for widget in self._widgets:
            widget.installEventFilter(self)
        self._relayout(force=True)

    def eventFilter(self, obj, event):
        # Control do screen ẩn/hiện (vd. nút xóa trailing) phải được xếp lại:
        # lưới bỏ qua widget đang ẩn nên không để lại ô trống.
        if event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            self._relayout(force=True)
        return super().eventFilter(obj, event)

    def _visible_widgets(self) -> list[QWidget]:
        return [
            widget
            for widget in self._widgets
            if not ResponsiveRow._explicitly_hidden(widget)
        ]

    def _line_width(self, count: int) -> int:
        """Bề ngang cần cho một hàng gồm ``count`` ô rộng nhất."""

        widgets = self._visible_widgets()
        if not widgets or count <= 0:
            return 0
        if self._item_min_width is not None:
            per_row = min(count, len(widgets))
            return per_row * self._item_min_width + self._spacing * (per_row - 1)
        floors = sorted(
            (ResponsiveRow._widget_floor(widget) for widget in widgets),
            reverse=True,
        )
        per_row = floors[:count]
        return sum(per_row) + self._spacing * (len(per_row) - 1)

    def required_width(self) -> int:
        """Bề ngang tối thiểu để giữ đủ số cột ở chế độ desktop."""

        return self._line_width(self._columns)

    def column_count(self) -> int:
        """Số cột đang dùng — điểm neo cho test hành vi."""

        return self._active_columns

    def minimumSizeHint(self) -> QSize:
        floor = self._line_width(self._compact_columns)
        return QSize(floor, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self, *, force: bool = False) -> None:
        target = (
            self._compact_columns
            if self.width() < self.required_width()
            else self._columns
        )
        if target == self._active_columns and not force:
            return

        widgets = self._visible_widgets()
        hidden_by_caller = {
            widget: ResponsiveRow._explicitly_hidden(widget)
            for widget in self._widgets
        }
        while self._grid.count():
            self._grid.takeAt(0)
        self._active_columns = target
        for index, widget in enumerate(widgets):
            self._grid.addWidget(widget, index // target, index % target)
        # Xoá stretch của MỌI cột lưới từng dùng trước khi áp cho các cột đang
        # hoạt động. Nếu chỉ đặt cho ``range(target)`` thì stretch của các cột
        # cũ còn sót lại, và Qt chia phần bề ngang dư cho cả những cột không
        # còn item — lưới 4 cột chuyển thành 2 cột vẫn bị chia bốn (F-R4-01).
        for column in range(max(self._columns, self._compact_columns) + 1):
            self._grid.setColumnStretch(column, 0)
        for column in range(target):
            self._grid.setColumnStretch(column, 1 if self._stretch else 0)
        for widget, hidden in hidden_by_caller.items():
            if not hidden:
                widget.show()
        self.updateGeometry()
