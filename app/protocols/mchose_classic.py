"""迈丛 MCHOSE · 经典协议（Feature Report + 0xFF 反码，旧款鼠标）。

请求：Feature Report <feature_report_id>，首字节是 `命令 XOR mask`，其余填 mask。
回包：同样是反码，逐字节 XOR mask 还原；电量是 1..10 的档位，×10 才是百分比。
"""
from __future__ import annotations

import time
from typing import Any, Dict

from ..hid_core import BatteryReading, ProtocolError
from .base import Param, Protocol, parse_fields
from .registry import register


@register
class MchoseClassic(Protocol):
    id = "mchose-classic"
    label = "迈丛 MCHOSE · 经典协议"
    vendor = "MCHOSE 迈丛"
    description = "Feature Report + 0xFF 反码的旧款协议，电量档位 1..10。"
    usage_pages = (0xFF01, 0xFF0B)

    params = [
        Param("feature_report_id", "Feature 报告 ID", "hex", 0x11),
        Param("feature_report_size", "Feature 长度", "int", 20),
        Param("feature_cmd", "读取命令", "hex", 0x06),
        Param("battery_scale", "电量 ×10 换算", "bool", True),
        Param("rx_payload_offset", "回包数据起点", "int", 0),
        Param("battery_index", "电量字节下标", "int", 8),
        Param("charging_index", "充电字节下标", "int", 9),
        Param("connection_index", "连接方式下标（-1 关闭）", "int", -1),
        Param("vid_index", "VID 下标（-1 关闭）", "int", -1),
        Param("pid_index", "PID 下标（-1 关闭）", "int", -1),
        Param("xor_mask", "XOR 掩码", "hex", 0xFF, advanced=True),
        Param("timeout_ms", "超时 (ms)", "int", 600, advanced=True),
    ]

    def query(self, dev, cfg: Dict[str, Any]) -> BatteryReading:
        rid = int(cfg.get("feature_report_id", 0x11))
        size = int(cfg.get("feature_report_size", 20))
        mask = int(cfg.get("xor_mask", 0xFF)) & 0xFF
        cmd = int(cfg.get("feature_cmd", 0x06)) & 0xFF

        buf = bytearray([mask] * size)
        buf[0] = cmd ^ mask
        t0 = time.monotonic()
        try:
            dev.send_feature_report(bytes([rid]) + bytes(buf))
        except Exception as exc:                   # noqa: BLE001
            raise ProtocolError(f"Feature 写入失败：{exc}") from exc

        resp = dev.get_feature_report(rid, size + 1)
        if not resp:
            raise ProtocolError("设备未响应")
        data = bytearray(resp[1:])
        for i in range(len(data)):
            data[i] ^= mask
        return parse_fields(bytes(data), cfg, (time.monotonic() - t0) * 1000, bytes(resp))
