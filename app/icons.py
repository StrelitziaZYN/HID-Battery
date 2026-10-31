"""图标绘制：托盘电池图标与应用图标（设备图标不在这里画，由用户上传）。

托盘图标按 32 单位画布设计、按 size 等比缩放；电池体量放大、笔画加粗，
在任务栏里比原版更醒目。低电量分两级配色：
    ≤ 30%  黄色（提醒）
    ≤ 15%  红色（告警，连外框一起变色）
充电中不告警（接着电源，掉电不是问题）。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF)

WARN_PERCENT = 30
CRITICAL_PERCENT = 15

COLOR_WARN = QColor(0xE8, 0x9C, 0x0A)              # 琥珀黄
COLOR_CRIT = QColor(0xD9, 0x2D, 0x35)              # 告警红


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def level_color(percent: int | None, charging: bool = False) -> QColor | None:
    """低电量返回告警色，其余返回 None（用中性前景色）。"""
    if percent is None or charging:
        return None
    if percent <= CRITICAL_PERCENT:
        return COLOR_CRIT
    if percent <= WARN_PERCENT:
        return COLOR_WARN
    return None


def _draw_charging_bolt(p: QPainter, bolt: QPolygonF, filled: QRectF,
                        fg: QColor, on_dark: bool, s: float) -> None:
    """充电闪电：按「闪电压在哪一层上」分别上色，两侧背景都能看清。

    压在电量填充上的部分用任务栏底色（视觉上是挖空的缺口），落在空白区的部分用前景色。
    交界正好落在填充边缘，等于沿闪电轮廓自动生成一圈反色描边——单色闪电加边框做不到这点，
    因为边框只能对一种背景成立，另一侧必然糊掉。
    """
    back = QColor(26, 26, 26) if on_dark else QColor(250, 250, 250)
    filled_path = QPainterPath()
    filled_path.addRoundedRect(filled, 1.8 * s, 1.8 * s)

    empty_path = QPainterPath()
    empty_path.addRect(QRectF(-8 * s, -8 * s, 48 * s, 48 * s))
    empty_path = empty_path.subtracted(filled_path)

    for region, color in ((filled_path, back), (empty_path, fg)):
        p.save()
        p.setClipPath(region)
        p.setPen(_pen(color, 1.1 * s))
        p.setBrush(QBrush(color))
        p.drawPolygon(bolt)
        p.restore()


def battery_pixmap(percent: int | None, on_dark: bool = True, charging: bool = False,
                   size: int = 32, dpr: float = 1.0) -> QPixmap:
    """简约电池图标：填充比例 = 电量，低电量换色。"""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 32.0

    fg = QColor(255, 255, 255) if on_dark else QColor(17, 17, 17)
    alert = level_color(percent, charging)
    critical = (percent is not None and not charging and percent <= CRITICAL_PERCENT)

    # 外框在严重低电量时直接变红，提醒更明显
    outline = alert if critical else fg
    fill_color = alert or fg

    body = QRectF(1.6 * s, 8.2 * s, 25.4 * s, 15.6 * s)
    cap = QRectF(28.0 * s, 12.0 * s, 3.4 * s, 8.0 * s)

    p.setPen(_pen(outline, 2.5 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(body, 4.2 * s, 4.2 * s)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(outline))
    p.drawRoundedRect(cap, 1.4 * s, 1.4 * s)

    inner = body.adjusted(3.0 * s, 3.0 * s, -3.0 * s, -3.0 * s)
    filled = QRectF(inner.left(), inner.top(), 0.0, inner.height())
    if percent is None:
        faint = QColor(outline)
        faint.setAlpha(90 if on_dark else 70)
        p.setPen(_pen(faint, 2.0 * s))
        cy = inner.center().y()
        p.drawLine(QPointF(inner.center().x() - 3.4 * s, cy),
                   QPointF(inner.center().x() + 3.4 * s, cy))
    else:
        ratio = max(0.0, min(1.0, percent / 100.0))
        if ratio > 0:
            filled.setWidth(max(2.6 * s, inner.width() * ratio))
            p.setBrush(QBrush(fill_color))
            p.drawRoundedRect(filled, 1.8 * s, 1.8 * s)

    if charging:
        bx, by = inner.left(), inner.top() + 0.4 * s
        bw, bh = inner.width(), inner.height() - 0.8 * s
        bolt = QPolygonF([
            QPointF(bx + bw * 0.66, by + bh * 0.02),
            QPointF(bx + bw * 0.34, by + bh * 0.52),
            QPointF(bx + bw * 0.52, by + bh * 0.52),
            QPointF(bx + bw * 0.46, by + bh * 0.98),
            QPointF(bx + bw * 0.78, by + bh * 0.44),
            QPointF(bx + bw * 0.58, by + bh * 0.44),
        ])
        _draw_charging_bolt(p, bolt, filled, fg, on_dark, s)

    p.end()
    return pm


def app_icon(on_dark: bool = True) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    bg = QColor(24, 24, 24) if on_dark else QColor(245, 245, 245)
    p.setBrush(QBrush(bg))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
    p.end()
    pm2 = battery_pixmap(72, on_dark=on_dark, size=44, dpr=1.0)
    p = QPainter(pm)
    p.drawPixmap(10, 10, pm2)
    p.end()
    return QIcon(pm)
