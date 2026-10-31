"""协议插件包：一个文件一种协议，对外只暴露这几个函数。

    from app.protocols import get_protocol, query_device, all_protocols
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..hid_core import (BatteryReading, HidInterface, ProtocolError, close_quietly,
                        open_interface)
from .base import Param, Protocol, parse_fields
from .registry import (all_protocols, get, ids, load_all, register, resolve_id)

__all__ = [
    "Param", "Protocol", "parse_fields", "all_protocols", "get_protocol",
    "protocol_ids", "query_device", "load_all", "resolve_id",
]


def protocol_ids() -> List[str]:
    load_all()
    return ids()


def get_protocol(protocol_id: str) -> Optional[Protocol]:
    return get(protocol_id)


def query_device(interface: HidInterface, profile: Dict[str, Any]) -> BatteryReading:
    """按配置里的协议查询一台设备；任何异常都转成 BatteryReading.error。"""
    proto = get(str(profile.get("protocol", "")))
    if proto is None:
        return BatteryReading(error=f"未知协议 {profile.get('protocol')}（插件未注册）")

    cfg = dict(proto.defaults())
    cfg.update({k: v for k, v in profile.items() if v is not None})

    try:
        dev = open_interface(interface)
    except Exception as exc:                       # noqa: BLE001
        return BatteryReading(error=f"打开设备失败：{exc}")
    try:
        return proto.query(dev, cfg)
    except ProtocolError as exc:
        return BatteryReading(error=str(exc))
    except Exception as exc:                       # noqa: BLE001
        return BatteryReading(error=f"通信异常：{exc}")
    finally:
        close_quietly(dev)
