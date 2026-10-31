"""Win32 相关：任务栏位置、通知区域矩形、任务栏明暗。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QRect

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

ABM_GETTASKBARPOS = 0x00000005
EDGE_LEFT, EDGE_TOP, EDGE_RIGHT, EDGE_BOTTOM = 0, 1, 2, 3


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", wintypes.RECT),
        ("lParam", wintypes.LPARAM),
    ]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def taskbar_rect() -> tuple[QRect | None, int]:
    """返回 (任务栏矩形, 边缘)。边缘: 0 左 / 1 上 / 2 右 / 3 下。"""
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    try:
        if shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(abd)):
            r = abd.rc
            return QRect(r.left, r.top, r.right - r.left, r.bottom - r.top), int(abd.uEdge)
    except Exception:                              # noqa: BLE001
        pass
    return None, EDGE_BOTTOM


def tray_notify_rect() -> QRect | None:
    """通知区域（托盘图标所在容器）的屏幕矩形。"""
    try:
        hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        if not hwnd:
            return None
        child = user32.FindWindowExW(hwnd, 0, "TrayNotifyWnd", None)
        if not child:
            return None
        rect = RECT()
        if not user32.GetWindowRect(child, ctypes.byref(rect)):
            return None
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None
        return QRect(rect.left, rect.top, w, h)
    except Exception:                              # noqa: BLE001
        return None


def taskbar_is_dark() -> bool:
    """任务栏是否为深色（决定托盘图标用白还是黑）。"""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        winreg.CloseKey(key)
        return int(value) == 0
    except Exception:                              # noqa: BLE001
        return True
