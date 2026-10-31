"""把托盘图标的所有当前状态渲染成一张对照图（含深/浅任务栏两版 + 放大细节）。

用法： python tools/tray_matrix.py [输出路径]
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRectF, Qt                          # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap     # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402

from app import theme                                          # noqa: E402
from app.icons import battery_pixmap                           # noqa: E402

STATES = [
    ("unknown", "未读到电量 / 无设备", None, False, "空心电池 + 中间短横线"),
    ("full", "已充满 100%（status 2）", 100, True, "转成 charging=True；闪电整个压在填充上（底色挖空）"),
    ("charge", "充电中 60%（status 1）", 60, True, "左半压填充用底色、右半在空白区用前景色"),
    ("normal", "放电 80%", 80, False, "中性前景色"),
    ("mid", "放电 45%", 45, False, "中性前景色"),
    ("warn", "放电 25%", 25, False, "琥珀黄（≤30%）"),
    ("crit", "放电 10%", 10, False, "红色（≤15%，外框也红）"),
]

CELL_W = 190
CELL_H = 128
PAD = 24
ICON = 40
ZOOM = 104


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "tray_matrix.png"
    app = QApplication.instance() or QApplication(sys.argv[:1])

    cols = len(STATES)
    band_h = CELL_H
    zoom_h = ZOOM + 56
    w = PAD * 2 + cols * CELL_W
    h = PAD * 2 + band_h * 2 + zoom_h * 2 + 30
    canvas = QPixmap(w, h)
    canvas.fill(QColor("#8A8A8A"))

    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    f_title = theme.ui_font(11, QFont.Weight.DemiBold)
    f_small = theme.ui_font(9)
    f_note = theme.ui_font(8)

    y = PAD
    for on_dark, bg, label in [
            (True, QColor("#1C1C1C"), "深色任务栏（on_dark=True）"),
            (False, QColor("#F3F3F3"), "浅色任务栏（on_dark=False）")]:
        rect = QRectF(PAD, y, cols * CELL_W, band_h - 10)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, 10, 10)

        p.setFont(f_title)
        p.setPen(QColor("#FFD166") if on_dark else QColor("#B45309"))
        p.drawText(QRectF(rect.left() + 14, rect.top() + 6, rect.width() - 28, 22),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), label)

        for i, (key, name, percent, charging, note) in enumerate(STATES):
            cx = rect.left() + i * CELL_W
            pm = battery_pixmap(percent, on_dark=on_dark, charging=charging, size=ICON, dpr=1.0)
            p.drawPixmap(int(cx + 16), int(rect.top() + 34), pm)

            p.setFont(f_small)
            p.setPen(QColor("#EDEDED") if on_dark else QColor("#1A1A1A"))
            p.drawText(QRectF(cx + 62, rect.top() + 34, CELL_W - 68, 18),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), name)
            p.setFont(f_note)
            p.setPen(QColor("#9A9A9A") if on_dark else QColor("#6B6B6B"))
            p.drawText(QRectF(cx + 62, rect.top() + 54, CELL_W - 68, 56),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                           | Qt.TextFlag.TextWordWrap), note)
        y += band_h

    # 放大：充电 / 充满 两种状态在深色底上的真实观感
    for on_dark, bg in [(True, QColor("#1C1C1C")), (False, QColor("#F3F3F3"))]:
        rect = QRectF(PAD, y, cols * CELL_W, zoom_h - 10)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, 10, 10)
        p.setFont(f_title)
        p.setPen(QColor("#FFD166") if on_dark else QColor("#B45309"))
        p.drawText(QRectF(rect.left() + 14, rect.top() + 6, rect.width() - 28, 22),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   "放大 2.6×：" + ("深色任务栏" if on_dark else "浅色任务栏"))
        for i, (percent, charging, note) in enumerate([
                (100, True, "已充满：闪电在填充上挖空，清晰可见"),
                (60, True, "充电 60%：闪电跨填充边缘，两侧自动反色"),
                (25, False, "对照：放电 25% 为琥珀告警色"),
        ]):
            pm = battery_pixmap(percent, on_dark=on_dark, charging=charging,
                                size=ZOOM, dpr=1.0)
            x = rect.left() + 16 + i * (ZOOM + 130)
            p.drawPixmap(int(x), int(rect.top() + 30), pm)
            p.setFont(f_note)
            p.setPen(QColor("#EDEDED") if on_dark else QColor("#1A1A1A"))
            p.drawText(QRectF(x + ZOOM + 10, rect.top() + 30, 190, 60),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                           | Qt.TextFlag.TextWordWrap), note)
        y += zoom_h

    p.end()
    canvas.save(out)
    print("saved", out, canvas.width(), "x", canvas.height())
    return 0


if __name__ == "__main__":
    sys.exit(main())
