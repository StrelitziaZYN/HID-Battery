"""自绘折线图：电量随时间变化（0–100 纵向网格 + 渐变面积 + 低电量阈值线）。

不引 QtCharts（PySide6-Essentials 里没有），也没有 matplotlib 依赖，
打包体积和启动速度都不受影响。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import QWidget

from . import theme

LOW_THRESHOLD = 20                                 # 低于此值画红色阈值线


class LineChart(QWidget):
    def __init__(self, parent=None, height: int = 168):
        super().__init__(parent)
        self._points: List[Tuple[int, float]] = []
        self._span = 24 * 3600
        self._now: int = 0
        self._fmt = "%H:%M"
        self.setMinimumHeight(height)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    # ------------------------------------------------------------------ #
    def set_data(self, points: Sequence[Tuple[int, float]], span: int,
                 label_fmt: str = "%H:%M", now: Optional[int] = None) -> None:
        self._points = [(int(t), float(v)) for t, v in points]
        self._span = max(60, int(span))
        self._fmt = label_fmt
        self._now = int(now if now is not None else
                        (self._points[-1][0] if self._points else 0))
        self.update()

    # ------------------------------------------------------------------ #
    def paintEvent(self, event):                   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        left, right, top, bottom = 30.0, 8.0, 10.0, 20.0
        plot = QRectF(left, top, max(10.0, self.width() - left - right),
                      max(10.0, self.height() - top - bottom))

        small = theme.ui_font(7)
        p.setFont(small)

        # 横向网格 + 纵轴刻度
        for value in (0, 25, 50, 75, 100):
            y = plot.bottom() - plot.height() * value / 100.0
            p.setPen(QPen(QColor(0, 0, 0, 16), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QPen(theme.C.TEXT_TERTIARY))
            p.drawText(QRectF(0, y - 7, left - 5, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{value}")

        # 低电量阈值线
        ty = plot.bottom() - plot.height() * LOW_THRESHOLD / 100.0
        pen = QPen(QColor(theme.C.DANGER.red(), theme.C.DANGER.green(),
                          theme.C.DANGER.blue(), 110), 1)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(plot.left(), ty), QPointF(plot.right(), ty))

        if len(self._points) < 2:
            p.setPen(QPen(theme.C.TEXT_TERTIARY))
            p.setFont(theme.ui_font(8))
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter,
                       "还没有足够的记录" if not self._points else "采样点不足以连线")
            self._draw_x_axis(p, plot, small)
            return

        start = self._now - self._span
        xs = [plot.left() + (t - start) / self._span * plot.width() for t, _ in self._points]
        ys = [plot.bottom() - max(0.0, min(100.0, v)) / 100.0 * plot.height()
              for _, v in self._points]

        line = QPainterPath(QPointF(xs[0], ys[0]))
        for x, y in zip(xs[1:], ys[1:]):
            line.lineTo(QPointF(x, y))

        area = QPainterPath(line)
        area.lineTo(QPointF(xs[-1], plot.bottom()))
        area.lineTo(QPointF(xs[0], plot.bottom()))
        area.closeSubpath()

        grad = QLinearGradient(0, plot.top(), 0, plot.bottom())
        accent = theme.C.ACCENT
        grad.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 70))
        grad.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 4))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPath(area)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(accent, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawPath(line)

        # 末点高亮
        p.setPen(QPen(QColor(255, 255, 255), 1.6))
        p.setBrush(QColor(accent))
        p.drawEllipse(QPointF(xs[-1], ys[-1]), 3.2, 3.2)

        self._draw_x_axis(p, plot, small)

    def _draw_x_axis(self, p: QPainter, plot: QRectF, font: QFont) -> None:
        p.setFont(font)
        p.setPen(QPen(theme.C.TEXT_TERTIARY))
        start = self._now - self._span
        for i in range(4):
            ratio = i / 3.0
            x = plot.left() + plot.width() * ratio
            stamp = start + self._span * ratio
            try:
                text = datetime.fromtimestamp(stamp).strftime(self._fmt)
            except (OSError, OverflowError, ValueError):
                text = ""
            align = (Qt.AlignmentFlag.AlignLeft if i == 0 else
                     Qt.AlignmentFlag.AlignRight if i == 3 else Qt.AlignmentFlag.AlignHCenter)
            x0 = max(0.0, min(x - 26, self.width() - 52.0))
            p.drawText(QRectF(x0, plot.bottom() + 4, 52, 14), align, text)
