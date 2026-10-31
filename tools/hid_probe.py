"""命令行探测工具：列出 HID 设备 / 发送原始帧看回包。

用法：
    python tools/hid_probe.py                          # 列出全部 HID 设备与集合
    python tools/hid_probe.py --vid 0x3837             # 只看某个厂商
    python tools/hid_probe.py --vid 0x3837 --send "4d 01 01 00 00 09 00 00"
                                                       # 向厂商通道发送一帧并打印回包
    python tools/hid_probe.py --path "\\\\?\\hid#..." --send "..."
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.hid_core import (close_quietly, enumerate_interfaces, load_caps,  # noqa: E402
                          open_interface)


def parse_vid(text: str) -> int:
    return int(text, 0) if text else 0


def list_devices(vid: int) -> None:
    interfaces = enumerate_interfaces()
    if vid:
        interfaces = [i for i in interfaces if i.vendor_id == vid]
    if not interfaces:
        print("没有匹配的 HID 设备")
        return

    current = None
    for iface in sorted(interfaces, key=lambda i: (i.vendor_id, i.product_id, i.interface_number)):
        key = (iface.vendor_id, iface.product_id, iface.serial_number or iface.product_string)
        if key != current:
            current = key
            print(f"\n[{iface.product_string or '未知设备'}]  "
                  f"{iface.manufacturer or '未知厂商'}  "
                  f"{iface.vendor_id:04X}:{iface.product_id:04X}  "
                  f"SN={iface.serial_number or '-'}")
        caps = load_caps(iface.path)
        print(f"  if{iface.interface_number:<3} usage {iface.usage_page:#06x}/{iface.usage:#04x}  "
              f"IN={caps.input_len if caps else '?':<6} OUT={caps.output_len if caps else '?':<6} "
              f"FEAT={caps.feature_len if caps else '?'}")
        print(f"       path {iface.path}")


def send_frame(vid: int, path: str, payload_hex: str, timeout: float) -> None:
    data = bytes(int(t, 16) for t in payload_hex.replace(",", " ").split())
    if not data:
        print("--send 需要一个十六进制帧，例如 \"4d 01 01 00 00 09 00 00\"")
        return

    interfaces = enumerate_interfaces()
    targets = []
    for iface in interfaces:
        if vid and iface.vendor_id != vid:
            continue
        if path and iface.path.decode(errors="ignore") != path:
            continue
        if not path and iface.usage_page < 0xFF00:
            continue
        targets.append(iface)

    if not targets:
        print("没有找到可写入的厂商集合，先用默认参数列一下设备")
        return

    for iface in targets:
        print(f"\n== {iface.product_string} usage {iface.usage_page:#06x} "
              f"if{iface.interface_number} pid {iface.product_id:04x}")
        try:
            dev = open_interface(iface)
        except Exception as exc:                   # noqa: BLE001
            print(f"   打开失败：{exc}")
            continue
        try:
            dev.write(data)
            deadline = time.monotonic() + timeout
            seen = 0
            while time.monotonic() < deadline:
                resp = dev.read(max(len(data), 64), timeout_ms=120)
                if resp:
                    seen += 1
                    print(f"   IN  {bytes(resp).hex(' ')}")
                    if seen >= 3:
                        break
            if not seen:
                print("   (无回包)")
        except Exception as exc:                   # noqa: BLE001
            print(f"   通信异常：{exc}")
        finally:
            close_quietly(dev)


def main() -> int:
    ap = argparse.ArgumentParser(description="HID 探测工具")
    ap.add_argument("--vid", default="", help="按厂商 ID 过滤，支持 0x3837 或 14391")
    ap.add_argument("--path", default="", help="直接指定设备路径")
    ap.add_argument("--send", default="", help="发送的十六进制帧")
    ap.add_argument("--timeout", type=float, default=1.2, help="等待回包秒数")
    args = ap.parse_args()

    vid = parse_vid(args.vid)
    if args.send:
        send_frame(vid, args.path, args.send, args.timeout)
    else:
        list_devices(vid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
