"""协议注册表：自动发现 `app/protocols/*.py` 里的 Protocol 子类。

新增协议只需要在 `app/protocols/` 里加一个文件并加 `@register`，
这里不需要任何登记动作；导入时用 pkgutil 扫一遍目录即可。
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, List, Optional, Type

from .base import Protocol

_REGISTRY: Dict[str, Type[Protocol]] = {}
_INSTANCES: Dict[str, Protocol] = {}
_LOADED = False

# 旧配置里的协议名 → 现在的插件 id（保证老 profiles.json 直接可用）
LEGACY_IDS = {
    "report64": "mchose-v2",
    "feature_xor": "mchose-classic",
}

_SKIP = {"base", "registry"}

# 打包成 EXE 后 pkgutil 可能扫不到 PYZ 里的模块，这里做一次兜底导入（新增插件时记得加进来）
_BUILTIN = ("mchose_v2", "mchose_classic", "flydigi_newxinput")


def register(cls: Type[Protocol]) -> Type[Protocol]:
    """类装饰器：把一个协议实现登记进注册表。"""
    if not cls.id:
        raise ValueError(f"{cls.__name__} 缺少 id")
    _REGISTRY[cls.id] = cls
    _INSTANCES.pop(cls.id, None)                   # 同 id 覆盖更新时丢掉旧实例
    return cls


def load_all() -> None:
    """导入包内所有模块以触发注册（幂等，可重复调用）。"""
    global _LOADED
    if _LOADED:
        return
    from . import __path__ as pkg_path

    found = 0
    for mod in pkgutil.iter_modules(list(pkg_path)):
        if mod.name.startswith("_") or mod.name in _SKIP:
            continue
        importlib.import_module(f"{__package__}.{mod.name}")
        found += 1

    if not found:                                  # 冻结环境兜底
        for name in _BUILTIN:
            try:
                importlib.import_module(f"{__package__}.{name}")
            except Exception:                      # noqa: BLE001
                pass
    _LOADED = True

    # 用户插件（EXE 旁边的 protocols/，由 AI 接入包安装）——失败不影响内置协议
    try:
        from ..plugin_store import load_user_plugins

        load_user_plugins()
    except Exception:                              # noqa: BLE001
        pass


def get(protocol_id: str) -> Optional[Protocol]:
    load_all()
    pid = LEGACY_IDS.get(protocol_id, protocol_id)
    if pid not in _INSTANCES:
        cls = _REGISTRY.get(pid)
        if cls is None:
            return None
        _INSTANCES[pid] = cls()
    return _INSTANCES[pid]


def resolve_id(protocol_id: str) -> str:
    load_all()
    pid = LEGACY_IDS.get(protocol_id, protocol_id)
    return pid if pid in _REGISTRY else ""


def all_protocols() -> List[Protocol]:
    load_all()
    return [get(pid) for pid in sorted(_REGISTRY)]


def ids() -> List[str]:
    load_all()
    return sorted(_REGISTRY)
