"""生成「刷新按钮旋转帧 + 面板完成态」预览图（不改程序，只用于确认观感）。

    python tools/spin_preview.py build/spin_preview.png
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRectF, Qt                              # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter          # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

from app import theme                                             # noqa: E402
from app.ui import Flyout                                         # noqa: E402
from app.widgets import IconButton                                # noqa: E402

app = QApplication(sys.argv[:1])
app.setFont(theme.ui_font(9))

DEVICES = [
    {"uid": "a", "name": "MCHOSE A7 V3 Pro", "percent": 100, "charging": False,
     "connection": 2, "protocol": "mchose-v2"},
    {"uid": "b", "name": "MCHOSE G98 V3", "percent": 99, "charging": True,
     "connection": 2, "protocol": "mchose-v2"},
    {"uid": "c", "name": "Flydigi APEX5 Wireless", "percent": 100, "charging": True,
     "connection": 2, "protocol": "flydigi-newxinput"},
]


def build():
    out = sys.argv[1] if len(sys.argv) > 1 else "build/spin_preview.png"
    base = os.path.dirname(out) or "."
    os.makedirs(base, exist_ok=True)

    fly = Flyout({})
    fly.devices_page.set_devices(DEVICES)
    fly.devices_page.set_reading(True)
    fly.adjustSize()
    end = time.monotonic() + 0.2                  # 让旋转走一小段，截到「正在读」的样子
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    print("reading angle:", round(fly.devices_page.btn_refresh._angle, 1))
    fly.grab().save(out.replace(".png", "_reading.png"))

    fly.devices_page.set_reading(False)
    end = time.monotonic() + 1.1                  # 等旋转收尾，图标回到常态
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    fly.grab().save(out.replace(".png", "_done.png"))

    btn = IconButton(theme.ICON["refresh"], size=28, icon_size=9, spin=True)
    btn.resize(28, 28)
    frames = [(0, "0°"), (60, "60°"), (120, "120°"), (180, "180°"), (240, "240°"), (300, "300°")]
    cell = 84
    img = QImage(cell * len(frames) + 24, 160, QImage.Format.Format_ARGB32)
    img.fill(QColor(250, 250, 250))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    f = QFont(theme.ui_font(8))
    p.setFont(f)
    p.setPen(theme.C.TEXT_SECONDARY)
    p.drawText(QRectF(12, 6, img.width() - 24, 20),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               "刷新按钮旋转帧（上：2× 放大 · 下：28×28 实际大小）")
    for i, (angle, label) in enumerate(frames):
        btn._angle = float(angle)
        pm = btn.grab()
        x = 12 + i * cell
        p.drawPixmap(x + 26, 60, pm)                       # 1:1 实际大小
        big = pm.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(x + 8, 32, big)                       # 2× 供检查
        p.drawText(QRectF(x, 100, cell, 18), Qt.AlignmentFlag.AlignCenter, label)
    p.end()
    img.save(out)
    print("saved", out, "| reading/done 面板见同目录 *_reading.png / *_done.png")


build()
