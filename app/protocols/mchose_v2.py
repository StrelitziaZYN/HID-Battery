"""迈丛 MCHOSE · V2 协议（64 字节 Output Report，Report ID 0x4D）。

帧结构：
    4D 01 01 <len> <cmd_lo> <cmd_hi> <biz> <seq> [payload...] <xor>
    校验：从第 2 字节起逐字节异或，写在 payload 后一字节。

电量回包 payload（相对回包 offset 8）：
    [0..1] VID  [2..3] 型号 PID  [10] 连接方式(1 有线 / 2 2.4G / 3 蓝牙)
    [11] 充电状态  [12] 电量百分比
"""
from __future__ import annotations

import time
from typing import Any, Dict

from ..hid_core import (BatteryReading, ProtocolError, field_byte, field_u16,
                        read_until, write_report)
from .base import Param, Protocol
from .registry import register


@register
class MchoseV2(Protocol):
    id = "mchose-v2"
    label = "迈丛 MCHOSE · V2 协议"
    vendor = "MCHOSE 迈丛"
    description = "64 字节 Output Report + XOR 校验，命令 0x0900 查电量，可从回包读出型号。"
    usage_pages = (0xFF01, 0xFF80, 0xFF0B)

    params = [
        Param("report_id", "报告 ID", "hex", 0x4D, "Output Report 首字节（0x00 表示无 ID）"),
        Param("report_size", "报告长度", "int", 64),
        Param("cmd_get_battery", "电量命令", "hex", 0x0900),
        Param("timeout_ms", "超时 (ms)", "int", 600, advanced=True),
        Param("rx_payload_offset", "回包数据起点", "int", 8),
        Param("battery_index", "电量字节下标", "int", 12),
        Param("charging_index", "充电字节下标", "int", 11),
        Param("connection_index", "连接方式下标", "int", 10),
        Param("vid_index", "VID 下标（-1 关闭）", "int", 0, advanced=True),
        Param("pid_index", "型号 PID 下标（-1 关闭）", "int", 2, advanced=True),
        # 设备休眠/关机时接收器仍会回包，但 VID 是 0x00FE，电量 0、连接方式 0；
        # 用期望 VID 把它挡掉，避免面板出现 0% 假告警。
        Param("expect_vid", "期望 VID（0 不校验）", "hex", 0x3837, advanced=True),
        Param("protocol_version", "协议版本字节", "hex", 0x01, advanced=True),
        Param("flags", "标志字节", "hex", 0x01, advanced=True),
        Param("biz_code", "业务码", "hex", 0x00, advanced=True),
        Param("checksum_start", "校验起始下标", "int", 2, advanced=True),
        Param("battery_payload", "附加负载", "intlist", [], advanced=True),
    ]

    # ------------------------------------------------------------------ #
    def build_frame(self, cfg: Dict[str, Any], cmd: int, payload: bytes = b"",
                    seq: int = 0) -> bytes:
        size = int(cfg.get("report_size", 64))
        frame = bytearray(size)
        frame[0] = int(cfg.get("report_id", 0x4D))
        frame[1] = int(cfg.get("protocol_version", 1))
        frame[2] = int(cfg.get("flags", 1))
        frame[3] = len(payload)
        frame[4] = cmd & 0xFF
        frame[5] = (cmd >> 8) & 0xFF
        frame[6] = int(cfg.get("biz_code", 0))
        frame[7] = seq
        frame[8:8 + len(payload)] = payload
        start = int(cfg.get("checksum_start", 2))
        chk = 0
        for i in range(start, 8 + len(payload)):
            chk ^= frame[i]
        frame[8 + len(payload)] = chk
        return bytes(frame)

    def query(self, dev, cfg: Dict[str, Any]) -> BatteryReading:
        cmd = int(cfg.get("cmd_get_battery", 0x0900))
        payload = bytes(int(b) & 0xFF for b in (cfg.get("battery_payload") or []))
        t0 = time.monotonic()
        write_report(dev, self.build_frame(cfg, cmd, payload))
        resp = read_until(
            dev,
            t0 + float(cfg.get("timeout_ms", 600)) / 1000.0,
            size=int(cfg.get("report_size", 64)),
            report_id=int(cfg.get("report_id", 0x4D)),
            match=bytes([cmd & 0xFF, (cmd >> 8) & 0xFF]),
        )
        if resp is None:
            raise ProtocolError("设备未响应（0x%04X 无回包）" % cmd)

        body = resp[int(cfg.get("rx_payload_offset", 8)):]
        real_vid = field_u16(body, cfg.get("vid_index"))
        expect_vid = int(cfg.get("expect_vid") or 0)
        if expect_vid and real_vid is not None and real_vid != expect_vid:
            raise ProtocolError(
                f"设备未连接（回包 VID {real_vid:#06x}，不是 {expect_vid:#06x}）"
                "—— 多为休眠 / 关机，唤醒后会自动恢复")

        percent = field_byte(body, cfg.get("battery_index"))
        if percent is not None and not 0 <= percent <= 100:
            percent = None
        charging = field_byte(body, cfg.get("charging_index"))
        return BatteryReading(
            percent=percent,
            charging=None if charging is None else bool(charging),
            connection=field_byte(body, cfg.get("connection_index")),
            real_vid=real_vid,
            real_pid=field_u16(body, cfg.get("pid_index")),
            raw=resp,
            latency_ms=(time.monotonic() - t0) * 1000,
        )
