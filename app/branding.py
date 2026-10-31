"""产品名称与版本：所有界面、托盘、打包脚本都从这里取，改名只改一处。"""
from __future__ import annotations

APP_NAME = "Strelitzia HID Battery"
APP_SHORT = "Strelitzia"
TAGLINE = "2.4G 设备电量监测"
VERSION = "2.0.0"

# EXE / 图标 / 注册表项统一用无空格标识
EXE_STEM = "StrelitziaHIDBattery"
REG_KEY_VALUE = "StrelitziaHIDBattery"

# 数据目录名（EXE 同目录可写时直接用 EXE 目录，否则退回 %LOCALAPPDATA%\<这个>）
DATA_FOLDER = "StrelitziaHIDBattery"

# 接入包（AI 产出的 JSON）标识
BUNDLE_KIND = "strelitzia-hid-battery-profile"


def window_title(suffix: str = "") -> str:
    return f"{APP_NAME} · {suffix}" if suffix else APP_NAME
