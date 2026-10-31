"""飞智 Flydigi · NewXInput 协议（VID 0x37D7，`5A A5` 帧，32 字节 HID 报告）。

适用机型（实测/公开资料）：Apex 5（37D7:2501）、Vader 5 Pro（37D7:2401）、Apex 6。
报告 ID 由设备描述符决定：Apex 5 为输出 3 / 输入 4；Vader 5 Pro 无编号（输出 0）。

请求帧（32 字节，未用字节补 0）：
    [0] 报告 ID  [1] 5A  [2] A5  [3] 命令字  [4] 长度（负载字节数 + 2）  [5..] 负载
    实测 5A A5 帧不强制校验：请求末字节补 0x00 即可，设备照常应答。

info 回包（命令 0x01，去掉报告 ID 后 body 自 0x5A 起）：
    [0..1] 5A A5     [2] 命令字
    [5]    设备号     0x80 = 128 = Apex 5（0x82 = 130 = Vader 5 Pro）
    [6]    连接方式   2 = 2.4G 无线 / 1 = 有线（旧架构编码；新架构为 0 有线、1 无线）
    [11]   电量字节   高 4 位 0=电池供电 1=充电中 2=已充满；低 4 位档位 ×20 %
    [15..16] 固件版本 低字节在前，逐 nibble 读作 7.0.4.5
    [30]   末字节     实测为 0x00（不是字节和，故不做校验）

本机实测（Apex 5，dongle）：
    04 5a a5 01 01 00 80 02 00 00 00 00 15 45 01 00 70 45 21 31 45 29 …
    → 设备号 0x80、连接 2（无线）、电量字节 0x15（充电中 / 100 %）、固件 7.0.4.5
"""
from __future__ import annotations

import time
from typing import Any, Dict

from ..hid_core import (BatteryReading, ProtocolError, field_byte, read_until,
                        write_report)
from .base import Param, Protocol
from .registry import register


@register
class FlydigiNewXInput(Protocol):
    id = "flydigi-newxinput"
    label = "飞智 Flydigi · NewXInput"
    vendor = "Flydigi 飞智"
    description = "32 字节报告 + 5A A5 帧头，命令 0x01 查设备信息，电量在高 4 位状态 + 低 4 位档位。"
    usage_pages = (0xFFA0,)

    params = [
        Param("report_id", "报告 ID", "hex", 0x03, "输出报告 ID（Apex 5 = 0x03；无编号报告填 0x00）"),
        Param("report_size", "报告长度", "int", 32, "含报告 ID 的总字节数"),
        Param("magic", "帧头 Magic", "hex", 0x5AA5, "5A A5"),
        Param("cmd_get_battery", "电量命令", "hex", 0x01, "0x01 = get info"),
        Param("timeout_ms", "超时 (ms)", "int", 800, advanced=True),
        Param("retries", "重试次数", "int", 2, advanced=True),
        Param("rx_payload_offset", "回包 5A 下标", "int", 1,
              "原始回包里 0x5A 的位置：有报告 ID 时为 1，无编号报告时为 0"),
        Param("battery_index", "电量字节下标", "int", 11, "相对 5A 起算"),
        Param("charging_index", "状态字节下标", "int", 11, "与电量同字节的高 4 位"),
        Param("connection_index", "连接方式下标", "int", 6),
        Param("battery_scale", "档位倍率", "int", 20, "低 4 位档位 × 该倍率 = 百分比（Apex 6 为 10）",
              advanced=True),
        Param("status_shift", "状态位右移", "int", 4, advanced=True),
        Param("level_mask", "档位掩码", "hex", 0x0F, advanced=True),
        Param("conn_wireless_value", "无线编码值", "int", 2,
              "连接字节等于该值判为 2.4G，其余 0/1 判为有线", advanced=True),
    ]

    # ------------------------------------------------------------------ #
    def build_frame(self, cfg: Dict[str, Any]) -> bytes:
        """按配置拼一帧 get info 请求（32 字节，未用字节补 0）。"""
        size = int(cfg.get("report_size", 32))
        magic = int(cfg.get("magic", 0x5AA5))
        frame = bytearray(size)
        frame[0] = int(cfg.get("report_id", 0x03)) & 0xFF
        frame[1] = (magic >> 8) & 0xFF
        frame[2] = magic & 0xFF
        frame[3] = int(cfg.get("cmd_get_battery", 0x01)) & 0xFF
        frame[4] = 2                                  # 负载 0 字节 → 长度 = 0 + 2
        frame[5] = 0
        return bytes(frame)

    def query(self, dev, cfg: Dict[str, Any]) -> BatteryReading:
        frame = self.build_frame(cfg)
        size = int(cfg.get("report_size", 32))
        offset = int(cfg.get("rx_payload_offset", 1))
        cmd = int(cfg.get("cmd_get_battery", 0x01)) & 0xFF
        magic = int(cfg.get("magic", 0x5AA5))
        # 只认「5A A5 <cmd>」的应答，避免把输入流（5A A5 EF …）当成回复
        expect = bytes([(magic >> 8) & 0xFF, magic & 0xFF, cmd])

        t0 = time.monotonic()
        resp = None
        for _ in range(max(1, int(cfg.get("retries", 2)))):
            write_report(dev, frame)
            resp = read_until(dev, time.monotonic() + float(cfg.get("timeout_ms", 800)) / 1000.0,
                              size=size, report_id=None, match=expect, offset=offset)
            if resp is not None:
                break
        if resp is None:
            raise ProtocolError("设备未响应（0x%02X 无 5A A5 回包）" % cmd)

        body = resp[offset:]
        bat_byte = field_byte(body, cfg.get("battery_index"))
        if bat_byte is None:
            raise ProtocolError("回包过短（%d 字节），电量下标 %s 越界"
                               % (len(resp), cfg.get("battery_index")))

        sta_byte = field_byte(body, cfg.get("charging_index"))
        if sta_byte is None:
            sta_byte = bat_byte

        shift = int(cfg.get("status_shift", 4))
        mask = int(cfg.get("level_mask", 0x0F))
        status = (sta_byte >> shift) & mask
        level = bat_byte & mask
        scale = int(cfg.get("battery_scale", 20))

        if status == 2:                               # 2 = 已充满
            percent = 100
        else:
            percent = level * scale
        percent = max(0, min(100, percent))

        charging = None
        if status in (0, 1, 2):
            charging = status in (1, 2)               # 充电中 / 已充满都算接着电源

        conn_raw = field_byte(body, cfg.get("connection_index"))
        connection = None
        if conn_raw is not None:
            connection = 2 if conn_raw == int(cfg.get("conn_wireless_value", 2)) else 1

        return BatteryReading(
            percent=percent,
            charging=charging,
            connection=connection,
            raw=resp,
            latency_ms=(time.monotonic() - t0) * 1000,
        )
