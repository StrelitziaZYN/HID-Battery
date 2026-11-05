"""运行期路径：源码运行与 PyInstaller 单文件 EXE 都要能找到可写的配置 / 数据目录。

PyInstaller 单文件模式会把代码解到临时目录（sys._MEIPASS，退出即删），
配置、图标、插件、历史库不能放那里，必须落在 **EXE 旁边**：

    HIDBatteryHub.exe
    config/profiles.json     接口配置
    protocols/*.py           AI/手工加进来的协议插件（启动时自动加载）
    assets/icons/            用户上传的设备图标
    data/history.db          电量历史

若 EXE 被放到 Program Files 这类不可写目录，则整棵目录退回到
%LOCALAPPDATA%\\HIDBatteryHub（`USING_EXE_DIR` 为 False，界面会标注原因）。
"""
from __future__ import annotations

import os
import sys

from . import branding


def _bundle_dir() -> str:
    """程序自身所在目录：EXE 旁边；源码运行时是项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("1")
        os.remove(probe)
        return True
    except Exception:                              # noqa: BLE001
        return False


def _fallback_dir() -> str:
    """EXE 目录不可写时的备用目录；兼容旧版留下的数据目录（StrelitziaHIDBattery / HIDBattery）。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    new = os.path.join(base, branding.DATA_FOLDER)
    olds = [os.path.join(base, name) for name in ("StrelitziaHIDBattery", "HIDBattery")]
    for old in olds:
        if not os.path.isdir(new) and os.path.isdir(old):
            return old
    return new


APP_DIR = _bundle_dir()                            # 兼容旧引用
EXE_DIR = APP_DIR                                  # 程序自身所在目录（EXE 旁 / 源码项目根）
DATA_DIR = EXE_DIR if _writable(EXE_DIR) else _fallback_dir()
USING_EXE_DIR = os.path.normcase(os.path.abspath(DATA_DIR)) == \
    os.path.normcase(os.path.abspath(EXE_DIR))
DATA_DIR_NOTE = "" if USING_EXE_DIR else f"EXE 目录不可写，已切换到 {DATA_DIR}"

CONFIG_DIR = os.path.join(DATA_DIR, "config")
ASSETS_DIR = os.path.join(DATA_DIR, "assets")
DATA_SUBDIR = os.path.join(DATA_DIR, "data")
PLUGIN_DIR = os.path.join(DATA_DIR, "protocols")
HISTORY_DB = os.path.join(DATA_SUBDIR, "history.db")

IS_FROZEN = bool(getattr(sys, "frozen", False))

_README = """\
把 AI 生成的协议插件放这里，程序启动时会自动加载（文件名随意，建议与插件 id 对齐）。

推荐做法：让 AI 输出一个「接入包」JSON，然后在程序里点
「接口设置 → 导入接入包」选择该文件 —— 插件与接口配置会一起装好，不用手动改任何东西。

接入包格式：
{
  "kind": "hid-battery-hub-profile",
  "version": 1,
  "protocol": { "filename": "vendor_protocol.py", "code_lines": ["from __future__ import annotations", "..."] },
  "profile":  { "id": "vendor-protocol", "name": "厂商 · 协议", "vendor_id": 14391,
                "usage_pages": [65280], "protocol": "vendor-protocol", "enabled": true, "models": {} }
}

也可以只放一个 .py 插件文件（必须带 @register 与唯一的 id）。
"""


def ensure_dirs() -> None:
    for path in (CONFIG_DIR, ASSETS_DIR, DATA_SUBDIR, PLUGIN_DIR):
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:                          # noqa: BLE001
            pass
    try:
        note = os.path.join(PLUGIN_DIR, "README.txt")
        if not os.path.exists(note):
            with open(note, "w", encoding="utf-8") as fh:
                fh.write(_README)
    except Exception:                              # noqa: BLE001
        pass


ensure_dirs()
