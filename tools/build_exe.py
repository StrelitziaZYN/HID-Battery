"""打包免安装单文件 EXE（PyInstaller --onefile --windowed）。

用法：
    python tools/build_exe.py

产物：dist/StrelitziaHIDBattery.exe —— 双击即用。运行期目录（都在 EXE 旁边）：

    config/profiles.json     接口配置
    protocols/               AI 接入包装好的用户插件（自动加载）
    assets/icons/            用户上传的设备图标
    data/history.db          电量历史

换电脑时只拷 EXE 也能跑；把整目录拷过去则连配置与历史一起带走。
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")

sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import branding                                    # noqa: E402

ICON = os.path.join(BUILD, branding.EXE_STEM + ".ico")
VERSION_FILE = os.path.join(BUILD, "version_info.txt")

# EXE「属性 → 详细信息」里显示的字段
VERSION_TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vers},
    prodvers={vers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [StringStruct('CompanyName', '{company}'),
         StringStruct('FileDescription', '{desc}'),
         StringStruct('FileVersion', '{filever}'),
         StringStruct('InternalName', '{stem}'),
         StringStruct('LegalCopyright', '{copyright}'),
         StringStruct('OriginalFilename', '{stem}.exe'),
         StringStruct('ProductName', '{name}'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def write_version_file(path: str) -> str:
    """生成 PyInstaller 用的版本资源，让 EXE 属性里显示文件版本 = branding.VERSION。"""
    v = branding.version_tuple()
    text = VERSION_TEMPLATE.format(
        vers=v,
        filever=".".join(str(x) for x in v),
        version=branding.VERSION,
        name=branding.APP_NAME,
        stem=branding.EXE_STEM,
        desc=f"{branding.APP_NAME} · {branding.TAGLINE}",
        company=branding.APP_NAME,
        copyright="Copyright (c) 2026 Strelitzia",
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def main() -> int:
    from make_ico import make_icon

    os.makedirs(BUILD, exist_ok=True)
    make_icon(ICON)
    print("图标:", ICON, os.path.getsize(ICON), "bytes")
    write_version_file(VERSION_FILE)
    print("版本资源:", VERSION_FILE, "文件版本", ".".join(map(str, branding.version_tuple())))

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", branding.EXE_STEM,
        f"--icon={ICON}",
        f"--version-file={VERSION_FILE}",
        "--distpath", DIST,
        "--workpath", os.path.join(BUILD, "work"),
        "--specpath", BUILD,
        # 协议插件靠自动发现；窗口/导入模块是懒加载，必须显式收集
        "--collect-submodules", "app",
        # hidapi 的 .dll 需要一起打进去
        "--collect-all", "hid",
        "--exclude-module", "tkinter",
        os.path.join(ROOT, "main.py"),
    ]
    print("PyInstaller:", " ".join(args[2:]))
    code = subprocess.call(args, cwd=ROOT)
    if code != 0:
        print("打包失败，退出码", code)
        return code

    exe = os.path.join(DIST, branding.EXE_STEM + ".exe")
    print("完成:", exe, round(os.path.getsize(exe) / 1048576, 1), "MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
