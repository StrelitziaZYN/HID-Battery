"""用户协议插件目录 + AI 接入包导入。

为什么需要这一层：
  * 打包成单文件 EXE 后，`app/protocols/` 在 PyInstaller 的临时解包目录里（退出即删），
    AI 生成的新插件**不能**放进去；
  * 所以插件分两处加载：内置的来自 `app/protocols/`，用户的来自
    `<数据目录>/protocols/*.py`（EXE 旁边），启动与导入时自动 exec 触发 `@register`。

对外：
    load_user_plugins()            加载/重载用户插件
    install_source(name, code)     落盘一个插件源码文件
    import_file(path, config)      导入 .json 接入包 / .py 插件，返回摘要
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple

from . import branding
from .paths import PLUGIN_DIR

_LOADED: Dict[str, float] = {}                     # 文件名 → mtime
_ERRORS: List[str] = []

_ID_RE = re.compile(r"^\s*id\s*=\s*['\"]([a-z0-9][a-z0-9\-]*)['\"]", re.MULTILINE)


class BundleError(Exception):
    """接入包格式不对 / 插件装载失败，消息直接展示给用户。"""


def errors() -> List[str]:
    return list(_ERRORS)


def _safe_filename(name: str, fallback: str = "plugin.py") -> str:
    base = os.path.basename(str(name or "").replace("\\", "/")).strip() or fallback
    if not base.lower().endswith(".py"):
        base += ".py"
    base = re.sub(r"[^0-9A-Za-z_.\-]", "_", base)
    if not re.match(r"^[A-Za-z_]", base):
        base = "p_" + base
    return base


def _module_name(filename: str) -> str:
    stem = os.path.splitext(filename)[0]
    return "hidbattery_plugin_" + re.sub(r"[^0-9A-Za-z_]", "_", stem)


def _registered_ids() -> List[str]:
    from .protocols import registry

    return registry.ids()


def _exec_file(path: str) -> None:
    """按文件路径导入一个插件模块（内部会调用 @register）。"""
    name = _module_name(os.path.basename(path))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BundleError(f"无法加载插件文件：{os.path.basename(path)}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


def load_user_plugins(force: bool = False) -> List[str]:
    """加载 `<数据目录>/protocols/` 下的插件，返回注册成功的文件名。"""
    _ERRORS.clear()
    if not os.path.isdir(PLUGIN_DIR):
        return []
    ok: List[str] = []
    for filename in sorted(os.listdir(PLUGIN_DIR)):
        if not filename.lower().endswith(".py"):
            continue
        path = os.path.join(PLUGIN_DIR, filename)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if not force and _LOADED.get(filename) == mtime:
            ok.append(filename)
            continue
        try:
            _exec_file(path)
            _LOADED[filename] = mtime
            ok.append(filename)
        except Exception as exc:                   # noqa: BLE001
            _ERRORS.append(f"{filename}：{exc}")
    return ok


def install_source(filename: str, code: str) -> str:
    """把插件源码写到用户插件目录，并立即加载；返回插件 id。"""
    if not str(code or "").strip():
        raise BundleError("接入包里没有插件代码（protocol.code / code_lines 为空）")
    if "@register" not in code:
        raise BundleError("插件代码缺少 @register，无法被识别")
    match = _ID_RE.search(code)
    if match is None:
        raise BundleError("插件代码里找不到形如 id = \"vendor-protocol\" 的声明")

    target_name = _safe_filename(filename or f"{match.group(1).replace('-', '_')}.py")
    os.makedirs(PLUGIN_DIR, exist_ok=True)
    target = os.path.join(PLUGIN_DIR, target_name)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(code if code.endswith("\n") else code + "\n")
    os.replace(tmp, target)

    before = set(_registered_ids())
    load_user_plugins(force=True)
    after = set(_registered_ids())
    plugin_id = match.group(1)
    if plugin_id not in after:
        detail = _ERRORS[-1] if _ERRORS else "注册表里没有出现该插件 id"
        raise BundleError(f"插件已写入 protocols/{target_name}，但未注册成功：{detail}")
    if not after - before:
        # 同 id 覆盖更新，注册表数量不变，也算成功
        pass
    return plugin_id


def _code_of(protocol_block: Dict[str, Any]) -> Tuple[str, str]:
    filename = str(protocol_block.get("filename") or "")
    code = protocol_block.get("code")
    if isinstance(protocol_block.get("code_lines"), list):
        code = "\n".join(str(line) for line in protocol_block["code_lines"])
    if not isinstance(code, str) or not code.strip():
        raise BundleError("接入包的 protocol 段缺少 code 或 code_lines")
    return filename, code


def _merge_profiles(config: Dict[str, Any], profiles: List[Dict[str, Any]]) -> List[str]:
    """按 id 覆盖写入接口配置，返回被写入的接口名。"""
    from .profiles import _with_defaults

    bucket = config.setdefault("profiles", [])
    named: List[str] = []
    for raw in profiles:
        if not isinstance(raw, dict):
            continue
        profile = _with_defaults(dict(raw))
        pid = str(profile.get("protocol") or "")
        if not pid:
            raise BundleError("接入包的 profile 缺少 protocol 字段")
        profile.setdefault("id", pid)
        profile.setdefault("name", pid)
        profile.setdefault("enabled", True)
        profile.setdefault("models", {})
        profile.setdefault("usage_pages", [])
        index = next((i for i, p in enumerate(bucket)
                      if p.get("id") == profile["id"]), None)
        if index is None:
            index = next((i for i, p in enumerate(bucket)
                          if p.get("protocol") == pid
                          and int(p.get("vendor_id", 0)) == int(profile.get("vendor_id", 0))), None)
        if index is None:
            bucket.append(profile)
        else:
            bucket[index] = profile
        named.append(str(profile.get("name") or profile["id"]))
    return named


def import_file(path: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """导入接入包 / 插件 / 配置片段。

    返回 {"protocol": 插件id, "profiles": [接口名...], "file": 落盘路径}
    """
    from .profiles import save_config

    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        with open(path, "r", encoding="utf-8") as fh:
            code = fh.read()
        plugin_id = install_source(os.path.basename(path), code)
        return {"protocol": plugin_id, "profiles": [], "file": path}

    if ext not in (".json", ".txt"):
        raise BundleError("只支持 .json 接入包或 .py 插件文件")

    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except Exception as exc:                       # noqa: BLE001
        raise BundleError(f"JSON 解析失败：{exc}") from exc
    if not isinstance(data, dict):
        raise BundleError("接入包必须是 JSON 对象")

    kind = str(data.get("kind") or "")
    has_protocol = isinstance(data.get("protocol"), dict)
    single_profile = isinstance(data.get("protocol"), str) and "vendor_id" in data
    profile_list = data.get("profiles")

    if not (has_protocol or single_profile or isinstance(profile_list, list)):
        raise BundleError(f"无法识别该接入包（kind={kind or '空'}），"
                          f"应包含 protocol+profile，或 profiles 数组")

    plugin_id = ""
    if has_protocol:
        filename, code = _code_of(data["protocol"])
        plugin_id = install_source(filename, code)

    targets: List[Dict[str, Any]] = []
    if isinstance(data.get("profile"), dict):
        targets.append(data["profile"])
    if single_profile:
        targets.append(data)
    if isinstance(profile_list, list):
        targets.extend(p for p in profile_list if isinstance(p, dict))

    for profile in targets:
        if isinstance(profile.get("protocol"), dict):
            continue
        if plugin_id and not profile.get("protocol"):
            profile["protocol"] = plugin_id

    # 校验：profile 指向的协议必须已经注册，否则导入了也读不到电量
    from .protocols.registry import resolve_id

    for profile in targets:
        pid = str(profile.get("protocol") or "")
        if pid and not resolve_id(pid):
            raise BundleError(
                f"接口配置里的 protocol=\"{pid}\" 没有找到对应插件；"
                f"请检查 profile.protocol 与插件类里的 id 是否一致")

    named = _merge_profiles(config, targets) if targets else []
    save_config(config)
    return {"protocol": plugin_id or (targets[0].get("protocol") if targets else ""),
            "profiles": named, "file": path}


def write_example(directory: str) -> str:
    """落一份接入包示例，便于对着改（设置页「导出示例接入包」用）。"""
    sample = {
        "kind": branding.BUNDLE_KIND,
        "version": 1,
        "protocol": {
            "filename": "example_protocol.py",
            "code_lines": [
                "from __future__ import annotations",
                "",
                "import time",
                "from typing import Any, Dict",
                "",
                "from app.hid_core import (BatteryReading, ProtocolError, field_byte,",
                "                          read_until, write_report)",
                "from app.protocols.base import Param, Protocol",
                "from app.protocols.registry import register",
                "",
                "",
                "@register",
                "class ExampleProtocol(Protocol):",
                "    id = \"example-protocol\"",
                "    label = \"示例 · 协议\"",
                "    vendor = \"示例厂商\"",
                "    description = \"示例：写一帧、读一帧、按偏移取电量\"",
                "    usage_pages = (0xFF00,)",
                "",
                "    params = [",
                "        Param(\"report_id\", \"报告 ID\", \"hex\", 0x00),",
                "        Param(\"report_size\", \"报告长度\", \"int\", 64),",
                "        Param(\"battery_index\", \"电量字节下标\", \"int\", 0),",
                "    ]",
                "",
                "    def query(self, dev, cfg: Dict[str, Any]) -> BatteryReading:",
                "        frame = bytearray(int(cfg[\"report_size\"]))",
                "        frame[0] = int(cfg[\"report_id\"])",
                "        write_report(dev, bytes(frame))",
                "        resp = read_until(dev, time.monotonic() + 0.6, size=len(frame))",
                "        if resp is None:",
                "            raise ProtocolError(\"设备未响应\")",
                "        return BatteryReading(percent=field_byte(resp, cfg[\"battery_index\"]),",
                "                              raw=resp)",
            ],
        },
        "profile": {
            "id": "example-protocol",
            "name": "示例 · 协议",
            "vendor_id": 0,
            "enabled": True,
            "usage_pages": [65280],
            "protocol": "example-protocol",
            "models": {},
        },
    }
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "example_bundle.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sample, fh, ensure_ascii=False, indent=2)
    return path
