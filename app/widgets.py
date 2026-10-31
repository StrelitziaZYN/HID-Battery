"""Fluent 风格基础控件。"""
from __future__ import annotations

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, Property, QPropertyAnimation,
                            QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import theme


class Surface(QWidget):
    """圆角面板（弹出层、卡片共用）。"""

    def __init__(self, parent=None, radius: int = 10, fill: QColor | None = None,
                 border: QColor | None = None):
        super().__init__(parent)
        self._radius = radius
        self._fill = fill or theme.C.WINDOW
        self._border = border or theme.C.STROKE
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):                   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)
        p.fillPath(path, self._fill)
        p.setPen(QPen(self._border, 1))
        p.drawPath(path)


class HoverFrame(QWidget):
    """带悬停高亮的可点击卡片。"""

    clicked = Signal()

    def __init__(self, parent=None, radius: int = 8):
        super().__init__(parent)
        self._radius = radius
        self._hover = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event):                   # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):                   # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):            # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):                   # noqa: N802
        if self._hover:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.C.SURFACE_HOVER)
            p.drawRoundedRect(QRectF(self.rect()), self._radius, self._radius)


class ElidedLabel(QLabel):
    """宽度不足时自动省略，避免撑破布局。"""

    def __init__(self, text: str = "", parent=None, mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight):
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str):                  # noqa: N802
        self._full = text
        self._refresh()

    def minimumSizeHint(self):                     # noqa: N802
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self):                            # noqa: N802
        hint = super().sizeHint()
        return QSize(min(hint.width(), 160), hint.height())

    def fullText(self) -> str:                     # noqa: N802
        return self._full

    def resizeEvent(self, event):                  # noqa: N802
        self._refresh()
        super().resizeEvent(event)

    def _refresh(self):
        fm = self.fontMetrics()
        width = max(0, self.width() - 2)
        if width <= 0:
            super().setText(self._full)
        else:
            super().setText(fm.elidedText(self._full, self._mode, width))


class _SpinGlyph:
    """给「图标按钮」加旋转反馈：转起来表示后台正在读取，读完平滑收尾。

    不引入 Property，直接用 QVariantAnimation 改角度（更少坑），
    最少转 `MIN_MS` 毫秒，避免扫描很快时动画一闪而过反而看不见。
    """

    MIN_MS = 560
    TURN_MS = 720

    def _init_spin(self):
        self._angle = 0.0
        self._want_stop = False
        self._tail = None
        self._spin = QVariantAnimation(self)
        self._spin.setStartValue(0.0)
        self._spin.setEndValue(360.0)
        self._spin.setDuration(self.TURN_MS)
        self._spin.setLoopCount(-1)
        self._spin.setEasingCurve(QEasingCurve.Type.Linear)
        self._spin.valueChanged.connect(self._on_spin_tick)
        self._spin_min = QTimer(self)
        self._spin_min.setSingleShot(True)
        self._spin_min.setInterval(self.MIN_MS)
        self._spin_min.timeout.connect(self._on_spin_min)

    def _on_spin_tick(self, value):
        self._angle = float(value)
        self.update()

    def _on_spin_min(self):
        if self._want_stop:
            self._end_spin()

    def is_spinning(self) -> bool:
        return self._spin.state() == QAbstractAnimation.State.Running

    def start_spin(self):
        self._want_stop = False
        if self.is_spinning():
            return
        if self._tail is not None:
            self._tail.stop()
        self._angle = 0.0
        self._spin.start()
        self._spin_min.start()

    def stop_spin(self):
        if not self.is_spinning():
            if self._angle:
                self._angle = 0.0
                self.update()
            return
        self._want_stop = True
        if not self._spin_min.isActive():
            self._end_spin()

    def _end_spin(self):
        self._spin.stop()
        self._spin_min.stop()
        self._want_stop = False
        rest = (360.0 - self._angle) % 360.0
        if rest < 1.0:
            self._angle = 0.0
            self.update()
            return
        tail = QVariantAnimation(self)
        tail.setStartValue(self._angle)
        tail.setEndValue(360.0)
        tail.setDuration(max(90, int(200 * rest / 360.0)))
        tail.setEasingCurve(QEasingCurve.Type.OutCubic)
        tail.valueChanged.connect(self._on_spin_tick)
        tail.finished.connect(self._on_spin_tail_done)
        tail.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._tail = tail

    def _on_spin_tail_done(self):
        self._tail = None
        self._angle = 0.0
        self.update()

    def _apply_spin(self, p: QPainter, center: QRectF | None = None):
        """把画笔绕中心（或指定矩形中心）旋转当前角度。"""
        if not self._angle:
            return
        c = (center or QRectF(self.rect())).center()
        p.translate(c)
        p.rotate(self._angle)
        p.translate(-c)


class IconButton(_SpinGlyph, QAbstractButton):
    def __init__(self, glyph: str, parent=None, size: int = 30, icon_size: int = 10,
                 color: QColor | None = None, tooltip: str = "", spin: bool = False):
        super().__init__(parent)
        self._glyph = glyph
        self._icon_size = icon_size
        self._color = color or theme.C.TEXT_SECONDARY
        self._hover = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if spin:
            self._init_spin()

    def sizeHint(self):                            # noqa: N802
        return QSize(self.width(), self.height())

    def enterEvent(self, event):                   # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):                   # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):                   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.C.SURFACE_HOVER)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)
        color = theme.C.TEXT if self._hover else self._color
        if hasattr(self, "_spin") and self._angle:
            # 转圈时换成「开口圆环」：圆形箭头本身近似中心对称，只转头很难看出在动；
            # 圆环的开口/收尾角度一转就很明显，是明确的「正在读取」反馈。
            p.save()
            c = QRectF(self.rect()).center()
            p.translate(c)
            p.rotate(self._angle)
            d = min(self.width(), self.height()) * 0.52   # 与 9pt 图标的视觉大小相当
            ring = QRectF(-d / 2, -d / 2, d, d)
            pen = QPen(color, 1.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(ring, 100 * 16, 280 * 16)
            p.restore()
            return
        p.setFont(theme.icon_font(self._icon_size))
        p.setPen(QPen(color))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._glyph)


class BatteryBar(QWidget):
    def __init__(self, parent=None, width: int = 64, height: int = 4):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._percent: int | None = None
        self._charging = False

    def set_state(self, percent: int | None, charging: bool = False):
        self._percent = percent
        self._charging = charging
        self.update()

    def paintEvent(self, event):                   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.C.TRACK)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self._percent is not None and self._percent > 0:
            ratio = max(0.04, min(1.0, self._percent / 100.0))
            color = theme.C.ACCENT if self._charging else theme.C.TEXT
            if self._percent <= 15 and not self._charging:
                color = theme.C.DANGER
            fill = QRectF(r.left(), r.top(), r.width() * ratio, r.height())
            p.setBrush(color)
            p.drawRoundedRect(fill, r.height() / 2, r.height() / 2)


class DeviceRow(QWidget):
    """设备行：图标（仅用户上传过才显示）+ 名称 + 连接方式 + 电量。"""

    clicked = Signal(dict)

    def __init__(self, device: dict, parent=None):
        super().__init__(parent)
        self.device = device
        self.setFixedHeight(64)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 不要给设备行（及其子控件）设 tooltip：Qt 会把子控件的 ToolTip 事件冒泡到父控件，
        # 鼠标停在名称/电量这些 QLabel 上也会弹出一整块系统样式的黑框，面板里不需要。
        self.setToolTip("")
        self._hover = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(10)

        # 图标：只有用户自己上传过才显示，没有就不占位、不绘制任何剪影
        self.icon = None
        path = device.get("icon_path")
        if path:
            from PySide6.QtGui import QPixmap
            raw = QPixmap(path)
            if not raw.isNull():
                self.icon = QLabel()
                self.icon.setFixedSize(40, 40)
                self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.icon.setPixmap(raw.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
                self.icon.setStyleSheet("background: transparent;")
                lay.addWidget(self.icon)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        self.name = ElidedLabel(device.get("name") or device.get("product") or "未知设备")
        self.name.setFont(theme.ui_font(10, QFont.Weight.DemiBold))
        self.name.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        self.sub = ElidedLabel(self._subtitle(device))
        self.sub.setFont(theme.ui_font(8))
        self.sub.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        col.addWidget(self.name)
        col.addWidget(self.sub)
        lay.addLayout(col, 1)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(5)
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        percent = device.get("percent")
        self.percent = QLabel("--" if percent is None else f"{percent}%")
        self.percent.setFont(theme.ui_font(11, QFont.Weight.DemiBold))
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.percent.setStyleSheet(f"color: {self._percent_color(percent)};")
        right.addWidget(self.percent)

        self.bar = BatteryBar(width=52, height=4)
        self.bar.set_state(percent, bool(device.get("charging")))
        right.addWidget(self.bar, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(right)

    @staticmethod
    def _percent_color(percent) -> str:
        if percent is None:
            return theme.C.TEXT_TERTIARY.name()
        if percent <= 15:
            return theme.C.DANGER.name()
        return theme.C.TEXT.name()

    @staticmethod
    def _subtitle(device: dict) -> str:
        conn = {1: "有线 USB", 2: "2.4G 无线", 3: "蓝牙"}.get(device.get("connection"), "连接未知")
        parts = [conn]
        if device.get("charging"):
            parts.append("充电中")
        if device.get("protocol"):
            parts.append(f"协议 {device['protocol']}")
        return " · ".join(parts)

    def mouseReleaseEvent(self, event):             # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit(self.device)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):                   # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):                   # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):                   # noqa: N802
        if self._hover:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.C.SURFACE_HOVER)
            p.drawRoundedRect(QRectF(self.rect()), 8, 8)


class ToggleSwitch(QAbstractButton):
    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 22)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"handle", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._on_toggle)

    def _on_toggle(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _get_handle(self):
        return self._pos

    def _set_handle(self, value: float):
        self._pos = value
        self.update()

    handle = Property(float, _get_handle, _set_handle)

    def paintEvent(self, event):                   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        p.setPen(QPen(theme.C.ACCENT if self.isChecked() else QColor(0, 0, 0, 55), 1))
        p.setBrush(theme.C.ACCENT if self.isChecked() else QColor(0, 0, 0, 12))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.left() + 2 + (r.width() - d - 4) * self._pos
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255) if self.isChecked() else QColor(90, 90, 90))
        p.drawEllipse(QRectF(x, r.top() + 2, d, d))


class FlatButton(_SpinGlyph, QAbstractButton):
    """Fluent 次要按钮 / 强调按钮。"""

    def __init__(self, text: str, parent=None, primary: bool = False, glyph: str = "",
                 spin: bool = False):
        super().__init__(parent)
        self.setText(text)
        self._primary = primary
        self._glyph = glyph
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMinimumHeight(32)
        self.setFont(theme.ui_font(9))
        if spin and glyph:
            self._init_spin()

    def sizeHint(self):                            # noqa: N802
        width = self.fontMetrics().horizontalAdvance(self.text()) + 26
        if self._glyph:
            width += 18
        return QSize(max(78, width), 32)

    def enterEvent(self, event):                   # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):                   # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):                   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._primary:
            bg = QColor(theme.C.TEXT)
            if self._hover:
                bg = QColor(52, 52, 52)
            fg = QColor(255, 255, 255)
            border = QColor(0, 0, 0, 0)
        else:
            bg = QColor(255, 255, 255, 255 if self._hover else 0)
            fg = theme.C.TEXT if self._hover else theme.C.TEXT_SECONDARY
            border = theme.C.STROKE
        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 6, 6)

        fm = p.fontMetrics()
        text = self.text()
        gw = 0
        if self._glyph:
            p.setFont(theme.icon_font(9))
            gw = 18
        total = fm.horizontalAdvance(text) + gw
        start = r.center().x() - total / 2
        if self._glyph:
            box = QRectF(start, r.top(), 14, r.height())
            if hasattr(self, "_spin") and self._angle:
                # 与图标按钮一致：读取时改画旋转的开口圆环，动感明显
                p.save()
                p.translate(box.center())
                p.rotate(self._angle)
                pen = QPen(fg, 1.5)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(QRectF(-6, -6, 12, 12), 100 * 16, 280 * 16)
                p.restore()
            else:
                p.setPen(fg)
                p.drawText(box, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           self._glyph)
        p.setFont(self.font())
        p.setPen(fg)
        p.drawText(QRectF(start + gw, r.top(), total, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)


class DragArea(QWidget):
    """可拖拽区域：按住空白处可移动整个弹出面板（标题栏用法）。

    子控件（按钮、标签）自己处理鼠标事件，只有空白处的事件会走到这里，
    因此不需要给每个控件单独装事件过滤器。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def mousePressEvent(self, event):              # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            self._offset = event.globalPosition().toPoint() - win.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):               # noqa: N802
        if self._offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):            # noqa: N802
        if self._offset is not None:
            self._offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            win = self.window()
            hook = getattr(win, "on_user_moved", None)
            if callable(hook):
                hook()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _SegButton(QAbstractButton):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(theme.ui_font(8))

    def sizeHint(self):                            # noqa: N802
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 26, 26)

    def paintEvent(self, event):                   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.isChecked():
            p.setPen(QPen(QColor(0, 0, 0, 18), 1))
            p.setBrush(QColor(255, 255, 255, 250))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(Qt.BrushStyle.NoBrush)
        if self.isChecked():
            p.drawRoundedRect(r, 6, 6)
        p.setPen(QPen(theme.C.TEXT if self.isChecked() else theme.C.TEXT_SECONDARY))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class Segmented(QWidget):
    """分段控件：互斥的多选一（24 小时 / 7 天 / 30 天）。"""

    changed = Signal(str)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self._buttons: dict[str, _SegButton] = {}
        self._current = ""

        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        for key, label in items:
            btn = _SegButton(label, self)
            btn.clicked.connect(lambda _checked=False, k=key: self._select(k))
            self._buttons[key] = btn
            row.addWidget(btn, 1)

        if items:
            self._select(items[0][0], emit=False)

    def paintEvent(self, event):                   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 18))
        p.drawRoundedRect(QRectF(self.rect()), 8, 8)

    def current(self) -> str:
        return self._current

    def set_current(self, key: str, emit: bool = False) -> None:
        self._select(key, emit=emit)

    def _select(self, key: str, emit: bool = True) -> None:
        if key not in self._buttons:
            return
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)
        if key == self._current:
            return
        self._current = key
        if emit:
            self.changed.emit(key)
