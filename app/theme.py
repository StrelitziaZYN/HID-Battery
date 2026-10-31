"""Fluent 视觉常量与小工具。"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QLabel, QWidget


class C:
    # 底色（半透明，叠在窗口模糊层上）
    WINDOW = QColor(249, 249, 249, 246)
    SURFACE = QColor(255, 255, 255, 235)
    SURFACE_HOVER = QColor(0, 0, 0, 8)
    SURFACE_PRESSED = QColor(0, 0, 0, 14)
    STROKE = QColor(0, 0, 0, 20)
    STROKE_STRONG = QColor(0, 0, 0, 38)

    TEXT = QColor(26, 26, 26)
    TEXT_SECONDARY = QColor(96, 96, 96)
    TEXT_TERTIARY = QColor(138, 138, 138)

    ACCENT = QColor(0, 103, 192)
    ACCENT_SOFT = QColor(0, 103, 192, 26)
    DANGER = QColor(196, 43, 28)
    WARN = QColor(157, 93, 0)
    OK = QColor(15, 123, 15)

    TRACK = QColor(0, 0, 0, 26)

    RADIUS = 10
    RADIUS_SMALL = 6


_UI_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"]
_DISPLAY_FAMILIES = ["Segoe UI Variable Display", "Segoe UI", "Microsoft YaHei UI"]


def ui_font(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont()
    f.setFamilies(_UI_FAMILIES)
    f.setPointSize(size)
    f.setWeight(weight)
    return f


def display_font(size: int = 20, weight: QFont.Weight = QFont.Weight.DemiBold) -> QFont:
    f = QFont()
    f.setFamilies(_DISPLAY_FAMILIES)
    f.setPointSize(size)
    f.setWeight(weight)
    return f


_ICON_FONT: str | None = None


def icon_font(size: int = 10) -> QFont:
    global _ICON_FONT
    if _ICON_FONT is None:
        families = set(QFontDatabase.families())
        for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
            if name in families:
                _ICON_FONT = name
                break
        else:
            _ICON_FONT = ""
    f = QFont(_ICON_FONT or "Segoe UI")
    f.setPointSize(size)
    return f


def icon_label(glyph: str, size: int = 10, color: QColor | None = None) -> QLabel:
    lb = QLabel(glyph)
    lb.setFont(icon_font(size))
    lb.setStyleSheet(f"color: {color.name() if color else C.TEXT.name()}; background: transparent;")
    from PySide6.QtCore import Qt as _Qt
    lb.setAttribute(_Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    return lb


# Fluent 图标码位
ICON = {
    "refresh": "\uE72C",
    "settings": "\uE713",
    "back": "\uE72B",
    "add": "\uE710",
    "delete": "\uE74D",
    "edit": "\uE70F",
    "check": "\uE73E",
    "close": "\uE711",
    "bolt": "\uE945",
    "chevron": "\uE76C",
    "down": "\uE70D",
    "up": "\uE70E",
    "more": "\uE712",
    "info": "\uE946",
    "link": "\uE71B",
    "device": "\uE7F4",
    "upload": "\uE898",
    "image": "\uE8B9",
    "chart": "\uE9D2",
    "history": "\uE81C",
    "pin": "\uE718",
}


def apply_shadow_color(widget: QWidget, color: QColor) -> None:
    widget.setStyleSheet(widget.styleSheet() + f"color: {color.name()};")


# 通用输入控件样式（设置页、对话框共用）
INPUT_QSS = """
QLineEdit, QComboBox, QPlainTextEdit {
    background: rgba(255,255,255,235);
    border: 1px solid rgba(0,0,0,32);
    border-bottom: 1px solid rgba(0,0,0,70);
    border-radius: 5px;
    padding: 4px 8px;
    color: #1A1A1A;
    selection-background-color: #0067C0;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
    border-bottom: 1px solid #0067C0;
    background: #FFFFFF;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #FFFFFF; border: 1px solid rgba(0,0,0,30); border-radius: 6px;
    selection-background-color: rgba(0,103,192,25); color: #1A1A1A; outline: none;
}
"""
