"""Flydigi APEX5 一次性探测脚本（只用于逆向，不进插件）。

用法：
    python tools/probe_flydigi.py --listen 3            # 被动监听，不写任何帧
    python tools/probe_flydigi.py --sweep               # 扫报告 ID + 候选命令字
    python tools/probe_flydigi.py --send 05 5a a5 ...   # 发一帧看回包
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.hid_core import (close_quietly, enumerate_interfaces, load_caps,  # noqa: E402
                          open_interface)

VID = 0x37D7


def targets(page: int = 0):
    out = []
    for i in enumerate_interfaces():
        if i.vendor_id != VID or i.product_id != 0x2501:
            continue
        if page and i.usage_page != page:
            continue
        if i.usage_page < 0xFF00:
            continue
        out.append(i)
    return out


def listen(iface, seconds: float) -> None:
    caps = load_caps(iface.path)
    size = max(caps.input_len if caps else 32, 32)
    print(f"监听 {iface.usage_page:#06x} IN={size} {seconds}s ...")
    dev = open_interface(iface)
    try:
        deadline = time.monotonic() + seconds
        n = 0
        while time.monotonic() < deadline:
            pkt = dev.read(size, timeout_ms=200)
            if pkt:
                n += 1
                print(f"  [{n:03d}] {bytes(pkt).hex(' ')}")
                if n >= 20:
                    break
        print(f"  共 {n} 帧")
    finally:
        close_quietly(dev)


def send_one(iface, frame: bytes, timeout: float = 0.35):
    caps = load_caps(iface.path)
    size = max(caps.input_len if caps else len(frame), len(frame))
    dev = open_interface(iface)
    got = []
    try:
        dev.write(frame)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pkt = dev.read(size, timeout_ms=120)
            if pkt:
                got.append(bytes(pkt))
                if len(got) >= 2:
                    break
    except Exception as exc:                        # noqa: BLE001
        return got, f"EXC {exc}"
    finally:
        close_quietly(dev)
    return got, ""


def sweep() -> None:
    for iface in targets():
        caps = load_caps(iface.path)
        print(f"\n===== usage {iface.usage_page:#06x} IN={caps.input_len if caps else '?'} "
              f"OUT={caps.output_len if caps else '?'}")
        size = max(caps.output_len if caps and caps.output_len else 32, 9)
        # 候选：报告 ID × 命令字位置。先试「全零 + 第2字节=命令」
        for rid in (0x00, 0x05, 0x01, 0x04, 0x03, 0x02):
            hits = 0
            for cmd in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x08, 0x0A, 0x10, 0x81):
                frame = bytearray(size)
                frame[0] = rid
                frame[1] = cmd
                got, err = send_one(iface, bytes(frame))
                if got:
                    hits += 1
                    print(f"  rid={rid:#04x} cmd={cmd:#04x} -> {[g.hex(' ') for g in got]}")
                elif err:
                    print(f"  rid={rid:#04x} cmd={cmd:#04x} -> {err}")
            if hits:
                print(f"  ^ rid={rid:#04x} 有 {hits} 个命中")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=float, default=0)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--send", nargs="*", default=None)
    ap.add_argument("--page", default="", help="0xffa0 / 0xffee")
    args = ap.parse_args()

    page = int(args.page, 0) if args.page else 0
    if args.listen:
        for iface in targets(page):
            listen(iface, args.listen)
        return 0
    if args.send:
        frame = bytes(int(t, 16) for t in args.send)
        for iface in targets(page):
            got, err = send_one(iface, frame, timeout=1.0)
            print(f"== usage {iface.usage_page:#06x}: {[g.hex(' ') for g in got]} {err}")
        return 0
    if args.sweep:
        sweep()
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
