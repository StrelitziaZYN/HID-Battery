"""协议插件基类。

新增一个厂商 / 一种协议 = 在 `app/protocols/` 下新建一个 `.py` 文件：
声明 `id / label / vendor / usage_pages / params`，实现 `query()` 即可。
注册表（registry.py）会自动发现，设置页表单、配置默认值、Prompt 都跟着变，
不需要改动基类、界面或配置文件。

约定：
  * 一个文件只描述一种协议，文件名与 `id` 保持一致（`mchose_v2` ↔ `mchose-v2`）。
  * 参数用 `Param` 声明，配置里就是同名的扁平字段（见 config/profiles.json）。
  * `query()` 只负责「发一帧、收一帧、解析」，异常统一抛 `ProtocolError`。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..hid_core import BatteryReading, HidInterface


@dataclass
class Param:
    """一个可配置的协议参数。设置页按 `kind` 生成对应控件。"""

    key: str                                  # 配置字段名
    label: str                                # 界面标签
    kind: str = "int"                         # int | hex | intlist | bool | str
    default: Any = 0                          # 缺省值
    hint: str = ""                            # 悬浮提示
    advanced: bool = False                    # 只在「高级参数」里出现


class Protocol:
    """一种厂商协议的实现。子类只声明类属性 + 实现 query()。"""

    id: str = ""                              # 唯一标识，写进配置的 protocol 字段
    label: str = ""                           # 界面显示名
    vendor: str = ""                          # 厂商名
    description: str = ""                     # 一句话说明
    usage_pages: Tuple[int, ...] = ()         # 值得尝试的集合；空表示该 VID 下全试
    params: List[Param] = []

    # ---------------------------------------------------------------- #
    @property
    def title(self) -> str:
        return self.label or self.id

    def defaults(self) -> Dict[str, Any]:
        return {p.key: p.default for p in self.params}

    def matches(self, interface: HidInterface) -> bool:
        if not self.usage_pages:
            return True
        return interface.usage_page in self.usage_pages

    def query(self, dev, cfg: Dict[str, Any]) -> BatteryReading:
        """向已经打开的设备查询一次电量。"""
        raise NotImplementedError

    def config_template(self) -> Dict[str, Any]:
        """新建接口时写进 profiles.json 的骨架。"""
        return {
            "id": self.id,
            "name": self.label,
            "vendor_id": 0,
            "enabled": True,
            "usage_pages": list(self.usage_pages),
            "protocol": self.id,
            "models": {},
        }

    def __repr__(self) -> str:                # pragma: no cover
        return f"<Protocol {self.id}>"


# --------------------------------------------------------------------------- #
# 解析辅助：多数字节型协议共用「按偏移取字段」的语义
# --------------------------------------------------------------------------- #
def parse_fields(payload: bytes, cfg: Dict[str, Any], latency_ms: float,
                 raw: bytes) -> BatteryReading:
    from ..hid_core import field_byte, field_u16

    percent = field_byte(payload, cfg.get("battery_index"))
    charging_raw = field_byte(payload, cfg.get("charging_index"))
    conn = field_byte(payload, cfg.get("connection_index"))
    real_vid = field_u16(payload, cfg.get("vid_index"))
    real_pid = field_u16(payload, cfg.get("pid_index"))

    if percent is not None:
        if cfg.get("battery_scale") and 0 < percent <= 10:
            percent = percent * 10
        if not 0 <= percent <= 100:
            percent = None

    charging: Optional[bool] = None
    if charging_raw is not None:
        charging = bool(charging_raw)

    return BatteryReading(
        percent=percent,
        charging=charging,
        connection=conn,
        real_vid=real_vid,
        real_pid=real_pid,
        raw=raw,
        latency_ms=latency_ms,
    )
