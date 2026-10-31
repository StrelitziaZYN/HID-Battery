"""HID 传输层：设备枚举、报告收发、能力读取（不依赖 Qt，无厂商协议知识）。

厂商协议全部放在 `app/protocols/` 下，每个协议一个文件，本模块只提供通用能力：
  * enumerate_interfaces()  枚举 HID 接口
  * load_caps()             读取单个集合的报告长度（INPUT/OUTPUT/FEATURE）
  * open_interface()        打开设备（调用方负责 close）
  * write_report() / read_report()  读写并统一超时语义
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import hid


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class HidInterface:
    path: bytes
    vendor_id: int
    product_id: int
    usage_page: int
    usage: int
    product_string: str = ""
    manufacturer: str = ""
    serial_number: str = ""
    interface_number: int = -1
    release_number: int = 0

    @property
    def key(self) -> str:
        return f"{self.vendor_id:04X}:{self.product_id:04X}"

    @property
    def uid(self) -> str:
        """同一物理设备的稳定标识（同一设备可能有多个集合，共用一个 PID/序列号）。"""
        return f"{self.vendor_id:04X}:{self.product_id:04X}:{self.serial_number or self.interface_number}"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "usage_page": self.usage_page,
            "usage": self.usage,
            "product": self.product_string,
            "manufacturer": self.manufacturer,
            "serial": self.serial_number,
            "interface": self.interface_number,
            "path": self.path.decode(errors="ignore") if isinstance(self.path, (bytes, bytearray)) else str(self.path),
        }


@dataclass
class BatteryReading:
    percent: Optional[int] = None
    charging: Optional[bool] = None
    connection: Optional[int] = None      # 1=有线 2=2.4G 3=蓝牙
    real_vid: Optional[int] = None
    real_pid: Optional[int] = None
    raw: bytes = b""
    error: str = ""
    latency_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.percent is not None


@dataclass
class HidCaps:
    input_len: int = 0
    output_len: int = 0
    feature_len: int = 0
    usage_page: int = 0
    usage: int = 0


# --------------------------------------------------------------------------- #
# 枚举
# --------------------------------------------------------------------------- #
def enumerate_interfaces() -> List[HidInterface]:
    out: List[HidInterface] = []
    for d in hid.enumerate():
        out.append(
            HidInterface(
                path=d["path"],
                vendor_id=d.get("vendor_id", 0),
                product_id=d.get("product_id", 0),
                usage_page=d.get("usage_page", 0),
                usage=d.get("usage", 0),
                product_string=d.get("product_string", "") or "",
                manufacturer=d.get("manufacturer_string", "") or "",
                serial_number=d.get("serial_number", "") or "",
                interface_number=d.get("interface_number", -1),
                release_number=d.get("release_number", 0) or 0,
            )
        )
    return out


_KEYBOARD_TOKENS = ("keyboard", "kbd", "键盘", "g98", "g87", "k99", "k87", "k75", "z75",
                    "x75", "gx87", "ut98", "g75", "k7", "k61", "k68", "ace", "mix", "god")
_MOUSE_TOKENS = ("mouse", "鼠标", "a7", "a5", "a9", "ax5", "l7", "m7", "r9", "g3", "x11", "k5")
_HEADSET_TOKENS = ("headset", "audio", "耳机", "v9", "r9 pro")


def guess_device_type(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in _KEYBOARD_TOKENS):
        return "keyboard"
    if any(k in t for k in _MOUSE_TOKENS):
        return "mouse"
    if any(k in t for k in _HEADSET_TOKENS):
        return "headset"
    return "other"


# --------------------------------------------------------------------------- #
# 报告长度（HidP_GetCaps）
# --------------------------------------------------------------------------- #
class _HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", ctypes.c_ushort), ("UsagePage", ctypes.c_ushort),
        ("InputReportByteLength", ctypes.c_ushort), ("OutputReportByteLength", ctypes.c_ushort),
        ("FeatureReportByteLength", ctypes.c_ushort), ("Reserved", ctypes.c_ushort * 17),
        ("NumberLinkCollectionNodes", ctypes.c_ushort),
        ("NumberInputButtonCaps", ctypes.c_ushort), ("NumberInputValueCaps", ctypes.c_ushort),
        ("NumberInputDataIndices", ctypes.c_ushort), ("NumberOutputButtonCaps", ctypes.c_ushort),
        ("NumberOutputValueCaps", ctypes.c_ushort), ("NumberOutputDataIndices", ctypes.c_ushort),
        ("NumberFeatureButtonCaps", ctypes.c_ushort), ("NumberFeatureValueCaps", ctypes.c_ushort),
        ("NumberFeatureDataIndices", ctypes.c_ushort),
    ]


def load_caps(path) -> Optional[HidCaps]:
    """读取集合的报告长度；失败返回 None。"""
    try:
        hid_dll = ctypes.WinDLL("hid.dll")
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wt.HANDLE
        k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                    wt.DWORD, wt.DWORD, wt.HANDLE]
        if isinstance(path, (bytes, bytearray)):
            path = path.decode(errors="ignore")
        handle = k32.CreateFileW(path, 0, 1 | 2, None, 3, 0, None)
        if handle == wt.HANDLE(-1).value:
            return None
        pp = ctypes.c_void_p()
        if not hid_dll.HidD_GetPreparsedData(wt.HANDLE(handle), ctypes.byref(pp)):
            k32.CloseHandle(wt.HANDLE(handle))
            return None
        caps = _HIDP_CAPS()
        ok = hid_dll.HidP_GetCaps(pp, ctypes.byref(caps))
        hid_dll.HidD_FreePreparsedData(pp)
        k32.CloseHandle(wt.HANDLE(handle))
        if not ok:
            return None
        return HidCaps(caps.InputReportByteLength, caps.OutputReportByteLength,
                       caps.FeatureReportByteLength, caps.UsagePage, caps.Usage)
    except Exception:                              # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# 收发
# --------------------------------------------------------------------------- #
class ProtocolError(Exception):
    """协议层可预期的失败（设备未响应、回包不合法等）。"""


def open_interface(interface: HidInterface) -> "hid.device":
    dev = hid.device()
    dev.open_path(interface.path)
    dev.set_nonblocking(0)
    return dev


def close_quietly(dev) -> None:
    try:
        dev.close()
    except Exception:                              # noqa: BLE001
        pass


def write_report(dev, data: bytes) -> None:
    written = dev.write(data)
    if written is None or written < 0:
        raise ProtocolError("写入失败（该集合可能不接收输出报告）")


def read_report(dev, size: int = 64, timeout_ms: int = 80) -> bytes:
    data = dev.read(size, timeout_ms=timeout_ms)
    return bytes(data) if data else b""


def read_until(dev, deadline: float, size: int = 64,
               report_id: Optional[int] = None,
               match: Optional[bytes] = None,
               offset: int = 4) -> Optional[bytes]:
    """在 deadline 前读取一帧满足条件的回包。match 与 report[offset:offset+len] 比较。"""
    while time.monotonic() < deadline:
        pkt = read_report(dev, size, 80)
        if not pkt:
            continue
        if report_id is not None and pkt[0] != report_id:
            continue
        if match is not None and pkt[offset:offset + len(match)] != match:
            continue
        return pkt
    return None


def field_byte(payload: bytes, index: Optional[int]) -> Optional[int]:
    if index is None or index < 0 or index >= len(payload):
        return None
    return payload[index]


def field_u16(payload: bytes, index: Optional[int]) -> Optional[int]:
    if index is None or index < 0 or index + 1 >= len(payload):
        return None
    return payload[index] | (payload[index + 1] << 8)
