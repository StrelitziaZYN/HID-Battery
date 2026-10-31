"""开机自启：写 HKCU\\...\\Run，免安装 EXE 也不需要管理员权限。"""
from __future__ import annotations

import os
import sys

from . import branding

try:
    import winreg
except ImportError:                                # pragma: no cover - 非 Windows
    winreg = None                                  # type: ignore[assignment]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = branding.REG_KEY_VALUE
LEGACY_VALUE = "HIDBattery"                        # 旧版写入的项，切换时顺手清掉


def command() -> str:
    """开机时执行的命令行：打包后直接跑 EXE，源码运行则用 pythonw + main.py。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    runner = pythonw if os.path.exists(pythonw) else exe
    main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return f'"{runner}" "{main_py}"'


def current() -> str:
    """注册表里当前的启动命令，没有则空串（兼容旧版 HIDBattery 项）。"""
    if winreg is None:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            for name in (VALUE_NAME, LEGACY_VALUE):
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                    return str(value)
                except FileNotFoundError:
                    continue
    except OSError:
        pass
    return ""


def is_enabled() -> bool:
    return bool(current())


def set_enabled(enabled: bool) -> bool:
    """返回是否操作成功。"""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
                try:                                # 清理旧版同名项，避免开机起两个
                    winreg.DeleteValue(key, LEGACY_VALUE)
                except FileNotFoundError:
                    pass
            else:
                for name in (VALUE_NAME, LEGACY_VALUE):
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
        return True
    except OSError:
        return False
