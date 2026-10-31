"""dump HID 报告描述符并用最小解析器列出每个集合的报告 ID / 长度 / 用途。

用法：python tools/hid_desc.py --vid 0x37D7
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.hid_core import enumerate_interfaces  # noqa: E402


def get_descriptor(path) -> bytes:
    hid = ctypes.WinDLL("hid.dll")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wt.HANDLE
    k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                wt.DWORD, wt.DWORD, wt.HANDLE]
    if isinstance(path, (bytes, bytearray)):
        path = path.decode(errors="ignore")
    h = k32.CreateFileW(path, 0, 1 | 2, None, 3, 0, None)
    if h == wt.HANDLE(-1).value:
        raise OSError("CreateFileW failed")
    try:
        buf = ctypes.create_string_buffer(4096)
        n = wt.DWORD()
        if not hid.HidD_GetReportDescriptor(wt.HANDLE(h), buf, 4096, ctypes.byref(n)):
            raise OSError("HidD_GetReportDescriptor failed")
        return buf.raw[:n.value]
    finally:
        k32.CloseHandle(wt.HANDLE(h))


PAGE_NAMES = {0x01: "GenericDesktop", 0x09: "Button", 0x0C: "Consumer",
              0xFFA0: "Vendor FFA0", 0xFFEE: "Vendor FFEE", 0x06: "GenericDevice"}


def fmt_usage(usage_page: int, u: int) -> str:
    return f"{PAGE_NAMES.get(usage_page, hex(usage_page))}/{u:#06x}"


def parse(desc: bytes) -> None:
    """按 HID 规范解析 item 流，输出每个 Report ID 下各主项的位数。"""
    i = 0
    g_usage_page = 0
    g_usage = None
    r_id = None
    r_size = 8
    r_count = 0
    usages_min: list[int] = []
    usages: list[int] = []
    usages_min = []
    print("  -- items --")
    while i < len(desc):
        prefix = desc[i]
        if prefix == 0xFE:                      # long item
            size = desc[i + 1]
            i += 3 + size
            continue
        nbytes = (0, 1, 2, 4)[prefix & 0x03]
        typ = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        val = int.from_bytes(desc[i + 1:i + 1 + nbytes], "little") if nbytes else 0
        if nbytes == 1 and typ == 1 and val > 0x7F:
            val -= 0x100
        i += 1 + nbytes

        if typ == 1:                            # Global
            if tag == 0x0:
                g_usage_page = val
            elif tag == 0x7:
                r_size = val
            elif tag == 0x8:
                r_id = val
                print(f"  ReportID {val:#04x}")
            elif tag == 0x9:
                r_count = val
        elif typ == 2:                          # Local
            if tag == 0x0:
                usages.append(val)
            elif tag == 0x1:
                usages_min.append(val)
        elif typ == 0:                          # Main
            if tag == 0x8:                      # Input
                bits = r_count * r_size
                kind = "IN "
            elif tag == 0x9:                    # Output
                bits = r_count * r_size
                kind = "OUT"
            elif tag == 0xB:                    # Feature
                bits = r_count * r_size
                kind = "FEA"
            else:
                usages.clear()
                usages_min.clear()
                continue
            u = usages[0] if usages else (usages_min[0] if usages_min else 0)
            print(f"  {kind} id={r_id if r_id is not None else 0:#04x} "
                  f"{bits:>4} bits ({bits // 8:>3} B)  count={r_count} size={r_size}  "
                  f"usage={fmt_usage(g_usage_page, u)}")
            usages.clear()
            usages_min.clear()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vid", default="")
    ap.add_argument("--pid", default="")
    args = ap.parse_args()
    vid = int(args.vid, 0) if args.vid else 0
    pid = int(args.pid, 0) if args.pid else 0

    seen = set()
    for iface in sorted(enumerate_interfaces(), key=lambda x: (x.vendor_id, x.interface_number)):
        if vid and iface.vendor_id != vid:
            continue
        if pid and iface.product_id != pid:
            continue
        if iface.usage_page < 0xFF00:
            continue
        if iface.path in seen:
            continue
        seen.add(iface.path)
        print(f"\n[{iface.product_string}] {iface.vendor_id:04x}:{iface.product_id:04x} "
              f"if{iface.interface_number} usage {iface.usage_page:#06x}/{iface.usage:#06x}")
        try:
            desc = get_descriptor(iface.path)
        except Exception as exc:                # noqa: BLE001
            print(f"  描述符读取失败：{exc}")
            continue
        print(f"  descriptor {len(desc)} bytes: {desc.hex(' ')}")
        parse(desc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
