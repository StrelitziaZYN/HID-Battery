"""现场复现：开面板 → 等扫描 → 截真实屏幕，检查状态文字是否真的重绘了。

用法：python tools/live_probe.py [输出图前缀]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer                                # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402

from app import theme                                            # noqa: E402

app = QApplication(sys.argv[:1])
app.setFont(theme.ui_font(9))

import main as M                                                 # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "build/live_probe.png"
t = M.TrayApp(app)


def wait(ms: int):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def shot(tag: str):
    """用控件自身的绘制结果（= 屏幕最终看到的内容），不受多屏坐标系影响。"""
    pm = t.flyout.grab()
    path = OUT.replace(".png", f"_{tag}.png")
    pm.save(path)
    print(f"[shot] {tag} -> {path} ({pm.width()}x{pm.height()}) angle="
          f"{getattr(t.flyout.devices_page.btn_refresh, '_angle', None)}", flush=True)


SLOW = "--slow" in sys.argv
if SLOW:
    import main as _m

    _real = _m.scan_devices

    def slow_scan(cfg):
        time.sleep(2.5)
        return _real(cfg)

    _m.scan_devices = slow_scan


def main():
    wait(2500)
    print("popup 前:", repr(t.flyout.devices_page.subtitle.text()),
          "| thread", t._thread, "running", None if t._thread is None else t._thread.isRunning(),
          "| pending", t._pending, flush=True)
    t.flyout.popup()
    print("popup 后: thread", None if t._thread is None else t._thread.isRunning(),
          "| pending", t._pending, flush=True)
    wait(350)
    shot("t0")
    for i in range(10):
        wait(500)
        print(f"{(i + 1) * 0.5:>4.1f}s",
              repr(t.flyout.devices_page.subtitle.text()),
              "|", repr(t.flyout.devices_page.status.text()),
              "| rows", t.flyout.devices_page.row_count(), flush=True)
    shot("t5")
    app.quit()


QTimer.singleShot(100, main)
app.exec()
