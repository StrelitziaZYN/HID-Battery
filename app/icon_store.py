"""设备图标仓库：只用「用户自己上传」的图片。

程序不抓取任何在线图片，也不绘制设备剪影：
  * 没上传过图标 → 列表里不显示图标；
  * 上传后按「VID-型号PID」存到 assets/icons/，同一型号的多台设备共用；
  * 图片会被归一化成 ≤128px 的 PNG（保留透明通道），避免占空间。

存储布局：
    assets/icons/3837-2025.png
"""
from __future__ import annotations

import os
from typing import List, Optional

from .paths import APP_DIR, ASSETS_DIR

ICON_DIR = os.path.join(ASSETS_DIR, "icons")

MAX_SIDE = 128
_EXTS = (".png", ".webp", ".jpg", ".jpeg")
_PICK_FILTER = "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.ico)"


def key_of(vendor_id: int, product_id: int) -> str:
    """图标键：厂商 + 型号，保证同型号共用一张图。"""
    return f"{int(vendor_id or 0):04X}-{int(product_id or 0):04X}"


def ensure_dir() -> None:
    os.makedirs(ICON_DIR, exist_ok=True)


def path_of(key: str) -> Optional[str]:
    if not key:
        return None
    for ext in _EXTS:
        path = os.path.join(ICON_DIR, key + ext)
        if os.path.isfile(path):
            return path
    return None


def resolve(vendor_id: int, product_id: int) -> Optional[str]:
    return path_of(key_of(vendor_id, product_id))


def save(key: str, source: str) -> str:
    """把用户选的图片归一化后存成 PNG，返回落盘路径。"""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    image = QImage(source)
    if image.isNull():
        raise ValueError("无法读取该图片，请换一张 PNG / JPG")
    if max(image.width(), image.height()) > MAX_SIDE:
        image = image.scaled(MAX_SIDE, MAX_SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)

    ensure_dir()
    target = os.path.join(ICON_DIR, key + ".png")
    tmp = target + ".tmp.png"
    if not image.save(tmp, "PNG"):
        raise ValueError("保存图片失败，请检查目录权限")
    os.replace(tmp, target)

    for ext in _EXTS:
        stale = os.path.join(ICON_DIR, key + ext)
        if ext != ".png" and os.path.isfile(stale):
            os.remove(stale)
    return target


def clear(key: str) -> bool:
    removed = False
    for ext in _EXTS:
        path = os.path.join(ICON_DIR, key + ext)
        if os.path.isfile(path):
            os.remove(path)
            removed = True
    return removed


def keys() -> List[str]:
    if not os.path.isdir(ICON_DIR):
        return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(ICON_DIR)
                  if f.lower().endswith(_EXTS) and not f.endswith(".tmp.png"))


def count() -> int:
    return len(keys())
