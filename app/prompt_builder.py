"""根据「已检测到的设备信息」生成标准化的接入提示词。

提示词只依赖设备自身的可观测信息：名称、厂商、连接状态、VID/PID、HID 集合。
交给任意 AI Agent，即可换回一个**可直接导入的 JSON 接入包**（插件 + 接口配置二合一），
不需要用户手工改任何文件。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from . import branding, i18n, paths

_CODE_TEMPLATE = '''from __future__ import annotations

import time
from typing import Any, Dict

from app.hid_core import (BatteryReading, ProtocolError, field_byte,
                          read_until, write_report)
from app.protocols.base import Param, Protocol
from app.protocols.registry import register


@register
class VendorProtocol(Protocol):
    id = "vendor-protocol"                 # 小写连字符，与文件名一致
    label = "厂商 · 协议"
    vendor = "厂商"
    description = "一句话描述帧结构与电量命令"
    usage_pages = (0xFF00,)

    params = [
        Param("report_id", "报告 ID", "hex", 0x00),
        Param("report_size", "报告长度", "int", 64),
        Param("cmd_get_battery", "电量命令", "hex", 0x0000),
        Param("rx_payload_offset", "回包数据起点", "int", 0),
        Param("battery_index", "电量字节下标", "int", 0),
        Param("charging_index", "充电字节下标", "int", -1),
        Param("connection_index", "连接方式下标", "int", -1),
    ]

    def query(self, dev, cfg: Dict[str, Any]) -> BatteryReading:
        cmd = int(cfg["cmd_get_battery"])
        frame = bytearray(int(cfg["report_size"]))
        frame[0] = int(cfg["report_id"])
        frame[1] = cmd & 0xFF
        write_report(dev, bytes(frame))

        resp = read_until(dev, time.monotonic() + 0.6,
                          size=len(frame), report_id=int(cfg["report_id"]))
        if resp is None:
            raise ProtocolError("设备未响应")

        body = resp[int(cfg["rx_payload_offset"]):]
        return BatteryReading(
            percent=field_byte(body, cfg["battery_index"]),
            charging=bool(field_byte(body, cfg["charging_index"]) or 0),
            connection=field_byte(body, cfg["connection_index"]),
            raw=resp,
        )
'''


def conn_text(device: Dict[str, Any]) -> str:
    """连接状态的一句话描述（提示词与界面共用）。"""
    supported = bool(device.get("supported", True))
    conn = device.get("connection")
    if supported and conn is not None:
        label = {1: i18n.T("有线 USB"), 2: i18n.T("2.4G 无线"),
                 3: i18n.T("蓝牙")}.get(conn, i18n.TF("未知（{}）", conn))
        bits = [label]
        if device.get("percent") is not None:
            bits.append(i18n.TF("电量 {}%", device['percent']))
        bits.append(i18n.T("充电中") if device.get("charging") else i18n.T("放电中"))
        return " · ".join(bits)
    if supported:
        return i18n.T("已接入协议，但本次未读到电量（可再点一次刷新）")
    return i18n.T("未知 —— 尚未接入协议，需由 HID 集合与命令响应推断")


def _identity_lines(device: Dict[str, Any]) -> List[str]:
    vid = int(device.get("vendor_id") or 0)
    pid = int(device.get("product_id") or 0)
    real_pid = device.get("real_pid")
    lines = [
        f"- 设备名称：{device.get('product') or device.get('name') or '未知设备'}",
        f"- 厂商：{device.get('vendor') or f'VID {vid:04X}'}",
        f"- 连接状态：{conn_text(device)}",
        f"- VID : PID：0x{vid:04X} : 0x{pid:04X}",
    ]
    if real_pid:
        lines.append(f"- 型号 PID（回包读出）：0x{int(real_pid):04X}（{device.get('model') or '-'}）")
    lines.append(f"- 序列号：{device.get('serial_number') or '-'}")
    if device.get("protocol"):
        lines.append(f"- 当前协议插件：{device['protocol']}（{device.get('profile_name') or '已启用'}）")
    else:
        lines.append("- 当前协议插件：无 —— 需要新建")
    lines.append(f"- HID 集合数量：{len(device.get('interfaces') or [])}")
    return lines


def _interface_lines(device: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for idx, item in enumerate(device.get("interfaces") or [], start=1):
        page = int(item.get("usage_page") or 0)
        usage = int(item.get("usage") or 0)
        out_len = int(item.get("output_len") or 0)
        feat_len = int(item.get("feature_len") or 0)
        if page >= 0xFF00:
            note = "厂商私有通道（首选）" if (out_len or feat_len) else "厂商私有，但没有可写报告"
        elif page == 0x0001:
            note = "标准键盘/鼠标集合，一般不含厂商电量命令"
        else:
            note = "其他标准集合"
        lines.append(f"{idx}) Usage Page 0x{page:04X} · Usage 0x{usage:04X} · "
                     f"IN {item.get('input_len') or 0} / OUT {out_len} / FEAT {feat_len}")
        lines.append(f"   → {note}")
    if not lines:
        lines.append("（没有读到集合信息，请在程序「接口探测」页重新探测）")
    return lines


def _observed_lines(device: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    if device.get("percent") is not None:
        lines.append(f"- 当前读数：电量 {device['percent']}% · "
                     f"{'充电中' if device.get('charging') else '放电中'}")
    if device.get("latency_ms"):
        lines.append(f"- 单次读取耗时：{device['latency_ms']} ms")
    raw = device.get("raw")
    if raw:
        lines.append(f"- 最近一次原始回包：`{raw}`")
    if not lines:
        lines.append("- 尚无成功读数（设备未接入协议，读不到电量）")
    return lines


def _vendor_pages(device: Dict[str, Any]) -> List[int]:
    pages = sorted({int(i.get("usage_page") or 0)
                    for i in device.get("interfaces") or []
                    if int(i.get("usage_page") or 0) >= 0xFF00})
    return pages or [0xFF00]


def _bundle_example(device: Dict[str, Any]) -> str:
    vid = int(device.get("vendor_id") or 0)
    pid = int(device.get("product_id") or 0)
    bundle = {
        "kind": branding.BUNDLE_KIND,
        "version": 1,
        "protocol": {
            "filename": "vendor_protocol.py",
            "code_lines": [
                "from __future__ import annotations",
                "",
                "…完整实现按第 6 节契约写全，每行一个字符串元素…",
            ],
        },
        "profile": {
            "id": "vendor-protocol",
            "name": f"{device.get('vendor') or '厂商'} · 协议名",
            "vendor_id": vid,
            "product_ids": [pid],
            "enabled": True,
            "usage_pages": _vendor_pages(device),
            "protocol": "vendor-protocol",
            "models": {},
        },
    }
    return json.dumps(bundle, ensure_ascii=False, indent=2)


def _probe_block(vid: int) -> List[str]:
    if paths.IS_FROZEN:
        return [
            "程序自带「接口探测」页：会对每个已启用接口的厂商私有集合发一次电量命令，"
            "并打印电量与原始回包。让用户把该页的输出贴回来即可继续分析，不需要 Python 环境。",
        ]
    return [
        "```bat",
        "python tools/hid_probe.py                     :: 列出所有 HID 设备与集合",
        f"python tools/hid_probe.py --vid 0x{vid:04X}      :: 只看这台设备的集合",
        f"python tools/hid_probe.py --vid 0x{vid:04X} --send \"4d 01 01 00 00 09 00 00\""
        "   :: 发原始帧看回包",
        "```",
    ]


def build(device: Dict[str, Any]) -> str:
    """生成可整段复制给 AI Agent 的接入提示词。"""
    name = device.get("product") or device.get("name") or "未知设备"
    vendor = device.get("vendor") or "未知厂商"
    vid = int(device.get("vendor_id") or 0)

    lines = [
        f"# 任务：为「{name}」编写 {branding.APP_NAME} 的 2.4G HID 电量协议插件",
        "",
        f"你是一名 Windows HID 协议工程师。下面的信息来自本机对这台设备（厂商：{vendor}）的"
        "**实时枚举结果**，没有任何猜测成分。请据此判断厂商私有通道与电量读取协议，"
        "并输出一个**可以直接导入的 JSON 接入包**。",
        "",
        "## 1. 设备信息",
        "",
        *_identity_lines(device),
        "",
        "## 2. 该设备的 HID 集合（枚举实测）",
        "",
        *_interface_lines(device),
        "",
        "## 3. 已观测到的数据",
        "",
        *_observed_lines(device),
        "",
        "## 4. 需要你给出的结论",
        "",
        "1. 哪个集合承载厂商私有命令通道（优先 Usage Page ≥ 0xFF00、且 OUT 或 FEATURE 长度 ≥ 8 的那个）。",
        "2. 查询电量的**完整请求帧**：报告 ID、总长度、命令字（注意字节序）、固定头、"
        "校验算法（给出逐字节示例）。",
        "3. **回包结构**：电量、充电状态、连接方式的字节偏移与取值范围；"
        "如果回包里带型号/PID，也请说明偏移。",
        "4. 万一设备对命令无响应：给出下一步最小实验（换哪个集合、试哪些命令字、如何判定成功）。",
        "",
        "## 5. 交付格式（最重要）",
        "",
        "只输出**一个 JSON 文件**（建议命名 `<vendor>_<protocol>.json`），"
        f"`kind` 固定为 `{branding.BUNDLE_KIND}`，结构如下：",
        "",
        "```json",
        _bundle_example(device),
        "```",
        "",
        "字段说明：",
        "",
        "- `protocol.filename`：插件文件名（与插件 id 对应，连字符换成下划线，例如 `acme_hid.py`）。",
        "- `protocol.code_lines`：**插件源码按行拆成的字符串数组**，程序会用换行符拼接。"
        "也接受 `protocol.code` 单个字符串（内部含 \\n），但数组更不容易出错。",
        "- `profile`：要写进接口配置的对象（程序会自己并入配置文件）。"
        "`vendor_id` / `product_ids` 请填上面的实测值，`product_ids` 用十进制整数；"
        "`usage_pages` 填真正能读到电量的集合。",
        "- `profile.protocol` 必须等于插件里的 `id`。",
        "- 其余协议参数（报告 ID、命令字、字段偏移等）直接以扁平字段写在 `profile` 里，"
        "键名与 `params` 中的 `key` 一致。",
        "",
        "用户可以把这个 JSON 拖到程序窗口上，或点「接口设置 → 导入接入包」选中它；"
        "程序会自动把插件写进 protocols/ 目录、注册协议、合并接口配置。",
        "不要输出需要用户手工复制文件、手工编辑 profiles.json 的方案。",
        "",
        "若确实无法输出单个 JSON，退化为两个文件也可以导入：一个 `.py` 插件"
        "（含 `@register`）+ 一个只含 `profile` 对象的 `.json`。",
        "",
        "## 6. 插件契约（必须遵守）",
        "",
        "```python",
        _CODE_TEMPLATE.rstrip(),
        "```",
        "",
        "硬性要求：",
        "",
        "- 类上加 `@register`；`id` 用小写连字符，且与文件名一致（`vendor_protocol.py` ↔ `vendor-protocol`）。",
        "- 报告 ID、命令字、字段偏移全部声明进 `params`，不要硬编码在 `query()` 里。",
        "- `query()` 只做「写一帧、读一帧、按偏移解析」；失败抛 `ProtocolError(\"...\")`，不要吞异常。",
        "- 只允许 import 标准库与 `app.hid_core` / `app.protocols.base` / `app.protocols.registry`；"
        "不得联网、不得读写文件。",
        "- 电量必须归一化成 0–100 的百分比（若设备给 1–10 档位，请在插件里 ×10）。",
        "- 只用一个文件、一个类；不要在模块顶层执行任何 I/O。",
        "",
        "## 7. 约束",
        "",
        "- 只根据上面的实测信息和你自己设计的探测实验下结论，**不要编造未观测到的字节偏移**。",
        "- 无法确定的项写「待验证」，并给出验证方法，而不是给一个看起来合理的猜测。",
        "- 本机可用的探测方式：",
        "",
        *_probe_block(vid),
        "",
        "## 8. 验收标准",
        "",
        "- 导入接入包后主面板出现该设备，电量与官方驱动显示一致（±1%）。",
        "- 连续刷新 3 次不报错、不超时。",
        "- 断开/重连接收器后能自动恢复读数。",
        "",
    ]
    return "\n".join(lines)
