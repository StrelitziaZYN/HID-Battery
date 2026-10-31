"""托盘图标改版预览（不会改动 app/icons.py，仅用于确认视觉方案）。

    python tools/tray_mock.py build/tray_mock.png

画出「现状」与「建议方案」两套，深色 / 浅色任务栏各一行，末尾附 2.6× 放大。
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QRectF, Qt                # noqa: E402
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter,   # noqa: E402
                           QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import QApplication                    # noqa: E402

from app import theme                                         # noqa: E402
from app.icons import battery_pixmap                          # noqa: E402

WARN = QColor(0xE8, 0x9C, 0x0A)
CRIT = QColor(0xD9, 0x2D, 0x35)
CHARGE_DARK = QColor(0x4C, 0x9E, 0xFF)
CHARGE_LIGHT = QColor(0x0A, 0x66, 0xC2)
FULL_DARK = QColor(0x4A, 0xD1, 0x64)
FULL_LIGHT = QColor(0x0F, 0x7B, 0x0F)


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def proposal(percent: int | None, on_dark: bool, charging: bool = False,
             full: bool = False, size: int = 40) -> QPixmap:
    """建议方案：电量→中性/琥珀/红；充电→蓝色轨道 + 白色闪电；充满→绿色实心。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 32.0

    fg = QColor(255, 255, 255) if on_dark else QColor(0x11, 0x11, 0x11)
    if full:
        color = FULL_DARK if on_dark else FULL_LIGHT
        alert = False
    elif charging:
        color = CHARGE_DARK if on_dark else CHARGE_LIGHT
        alert = False
    elif percent is None:
        color = fg
        alert = False
    elif percent <= 15:
        color, alert = CRIT, True
    elif percent <= 30:
        color, alert = WARN, False
    else:
        color, alert = fg, False

    body = QRectF(1.6 * s, 8.2 * s, 25.4 * s, 15.6 * s)
    cap = QRectF(28.0 * s, 12.0 * s, 3.4 * s, 8.0 * s)
    inner = body.adjusted(3.0 * s, 3.0 * s, -3.0 * s, -3.0 * s)

    p.setPen(_pen(color if not alert else CRIT, 2.5 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(body, 4.2 * s, 4.2 * s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color if not alert else CRIT))
    p.drawRoundedRect(cap, 1.4 * s, 1.4 * s)

    if charging:
        track = QColor(color)
        track.setAlpha(54)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(track))
        p.drawRoundedRect(inner, 1.8 * s, 1.8 * s)

    if percent is None:
        faint = QColor(color)
        faint.setAlpha(90 if on_dark else 70)
        p.setPen(_pen(faint, 2.0 * s))
        cy = inner.center().y()
        p.drawLine(QPointF(inner.center().x() - 3.4 * s, cy),
                   QPointF(inner.center().x() + 3.4 * s, cy))
    else:
        ratio = max(0.0, min(1.0, percent / 100.0))
        if ratio > 0:
            width = max(2.6 * s, inner.width() * ratio)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawRoundedRect(QRectF(inner.left(), inner.top(), width, inner.height()),
                              1.8 * s, 1.8 * s)

    if charging and percent is not None and percent < 100:
        bolt = QPolygonF([
            QPointF(inner.center().x() + 1.6 * s, inner.top() - 0.6 * s),
            QPointF(inner.center().x() - 3.4 * s, inner.center().y() + 0.6 * s),
            QPointF(inner.center().x() - 0.6 * s, inner.center().y() + 0.6 * s),
            QPointF(inner.center().x() - 1.6 * s, inner.bottom() + 0.6 * s),
            QPointF(inner.center().x() + 3.6 * s, inner.center().y() - 0.6 * s),
            QPointF(inner.center().x() + 0.8 * s, inner.center().y() - 0.6 * s),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawPolygon(bolt)

    if full:
        # 满电：右下角一个小对勾，和"充电中"明确区分
        p.setPen(_pen(QColor(255, 255, 255), 1.6 * s))
        p.drawLine(QPointF(inner.center().x() - 2.6 * s, inner.center().y() + 0.2 * s),
                   QPointF(inner.center().x() - 0.6 * s, inner.center().y() + 2.2 * s))
        p.drawLine(QPointF(inner.center().x() - 0.6 * s, inner.center().y() + 2.2 * s),
                   QPointF(inner.center().x() + 3.0 * s, inner.center().y() - 2.4 * s))

    p.end()
    return pm


ROWS = [
    ("现状", battery_pixmap, [
        ("读取中 / 无设备", dict(percent=None)),
        ("放电 80%", dict(percent=80)),
        ("放电 25%", dict(percent=25)),
        ("放电 10%", dict(percent=10)),
        ("充电 60%", dict(percent=60, charging=True)),
        ("已充满", dict(percent=100, charging=True)),
    ]),
    ("建议", proposal, [
        ("读取中 / 无设备", dict(percent=None)),
        ("放电 80%", dict(percent=80)),
        ("放电 25%", dict(percent=25)),
        ("放电 10%", dict(percent=10)),
        ("充电 60%", dict(percent=60, charging=True)),
        ("已充满", dict(percent=100, full=True)),
    ]),
]

CELL_W = 150
CELL_H = 74
PAD = 22


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "tray_mock.png"
    app = QApplication.instance() or QApplication(sys.argv[:1])

    cols = len(ROWS[0][2])
    w = PAD * 2 + cols * CELL_W
    h = PAD * 2 + 4 * (CELL_H + 26) + 2 * 110 + 20
    canvas = QPixmap(w, h)
    canvas.fill(QColor("#7E7E7E"))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    f_name = theme.ui_font(8)
    f_tag = theme.ui_font(9, QFont.Weight.DemiBold)

    y = PAD
    for tag, fn, states in ROWS:
        for on_dark, bg in [(True, QColor("#1C1C1C")), (False, QColor("#F3F3F3"))]:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(PAD, y, cols * CELL_W, CELL_H), 10, 10)
            p.setFont(f_tag)
            p.setPen(QColor("#FFD166") if on_dark else QColor("#B45309"))
            p.drawText(QRectF(PAD + 12, y + 2, 240, 16),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       f"{tag} · {'深色' if on_dark else '浅色'}任务栏")
            for i, (name, kw) in enumerate(states):
                x = PAD + i * CELL_W + 12
                pm = fn(on_dark=on_dark, size=40, **kw)
                p.drawPixmap(int(x), int(y + 24), pm)
                p.setFont(f_name)
                p.setPen(QColor("#E8E8E8") if on_dark else QColor("#333333"))
                p.drawText(QRectF(x + 46, y + 24, CELL_W - 54, 40),
                           int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                               | Qt.TextFlag.TextWordWrap), name)
            y += CELL_H + 8
        y += 18

    # 放大 2.6×：建议方案里两个新增状态
    for on_dark, bg in [(True, QColor("#1C1C1C")), (False, QColor("#F3F3F3"))]:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(PAD, y, cols * CELL_W, 104), 10, 10)
        p.setFont(f_tag)
        p.setPen(QColor("#FFD166") if on_dark else QColor("#B45309"))
        p.drawText(QRectF(PAD + 12, y + 2, 240, 16),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   f"建议 · 放大 2.6×（{'深色' if on_dark else '浅色'}）")
        for i, kw in enumerate([dict(percent=60, charging=True), dict(percent=100, full=True)]):
            pm = proposal(on_dark=on_dark, size=104, **kw)
            p.drawPixmap(int(PAD + 14 + i * 200), int(y + 22), pm)
        y += 104 + 8

    p.end()
    canvas.save(out)
    print("saved", out, canvas.width(), "x", canvas.height())
    return 0


if __name__ == "__main__":
    sys.exit(main())
