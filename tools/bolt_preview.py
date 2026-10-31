"""把真实托盘图标的充电态放大 8× 摆在深/浅底色上看（验证闪电可辨识度）。

    python tools/bolt_preview.py build/bolt_preview.png
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRectF, Qt                            # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap              # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402

from app import theme                                            # noqa: E402
from app.icons import battery_pixmap                             # noqa: E402

SCALE = 8
ICON = 40
CASES = [(20, True), (60, True), (99, True), (100, True), (60, False)]


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "bolt_preview.png"
    app = QApplication.instance() or QApplication(sys.argv[:1])
    cell = ICON * SCALE + 16
    row_h = cell + 26
    w = 16 + cell * len(CASES)
    h = 16 + row_h * 2
    canvas = QPixmap(w, h)
    canvas.fill(QColor("#7A7A7A"))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    f = theme.ui_font(9)

    y = 8
    for on_dark, bg in [(True, QColor("#1C1C1C")), (False, QColor("#F3F3F3"))]:
        for i, (pct, charging) in enumerate(CASES):
            x = 8 + i * cell
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(x, y, cell - 6, cell - 6), 8, 8)
            pm = battery_pixmap(pct, on_dark=on_dark, charging=charging, size=ICON, dpr=1.0)
            big = pm.scaled(ICON * SCALE, ICON * SCALE, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.FastTransformation)
            p.drawPixmap(int(x + 6), int(y + 6), big)
            p.setFont(f)
            p.setPen(QColor("#FFD166") if on_dark else QColor("#8A4B00"))
            p.drawText(int(x + 10), int(y + cell - 8), f"{pct}% {'充电' if charging else '放电'}")
        y += row_h

    p.end()
    canvas.save(out)
    print("saved", out, canvas.width(), "x", canvas.height())
    return 0


if __name__ == "__main__":
    sys.exit(main())
