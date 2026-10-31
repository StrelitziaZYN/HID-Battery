"""生成多尺寸 .ico（16/24/32/48/64/256），供 EXE 图标与快捷方式使用。

用 Qt 画（和托盘同一个 battery_pixmap），再把各尺寸 PNG 直接塞进 ICO 容器；
Windows Vista 以后支持 PNG 压缩的图标项，体积比 BMP 小很多。
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SIZES = (16, 24, 32, 48, 64, 256)

_APP = None                                        # 必须常驻，否则 QApplication 被回收会崩


def _ensure_app():
    global _APP
    from PySide6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
    return _APP


def _png_bytes(size: int) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, Qt
    from PySide6.QtGui import QImage, QPainter, QColor

    from app.icons import battery_pixmap

    _ensure_app()
    canvas = QImage(size, size, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setBrush(QColor(24, 24, 24))
    p.setPen(Qt.PenStyle.NoPen)
    radius = max(3.0, size * 0.22)
    p.drawRoundedRect(0, 0, size, size, radius, radius)
    inner = max(8, int(size * 0.80))
    pm = battery_pixmap(64, on_dark=True, size=inner, dpr=1.0)
    p.drawPixmap((size - inner) // 2, (size - inner) // 2, pm)
    p.end()

    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    canvas.save(buf, "PNG")
    buf.close()
    return bytes(data)


def make_icon(path: str, sizes=SIZES) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    images = [(s, _png_bytes(s)) for s in sizes]

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)

    with open(path, "wb") as fh:
        fh.write(header + entries + blobs)
    return path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join("build", "StrelitziaHIDBattery.ico")
    print("icon ->", make_icon(target), os.path.getsize(target), "bytes")
