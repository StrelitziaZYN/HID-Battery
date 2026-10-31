"""端到端冒烟：托盘 → 弹出面板 → 设备行 → 提示词 → 独立窗口（统计/设置/探测）→ 失焦收起。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QApplication

from app import theme
from app.prompt_page import PromptDialog
from main import TrayApp

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(OUT, exist_ok=True)
state = {"clicked": None}
app = QApplication(sys.argv)
app.setFont(theme.ui_font(9))
ta = TrayApp(app)


def wait(ms=400):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def step1():
    print("tray visible:", ta.tray.isVisible())
    print("tooltip:", ta.tray.toolTip().replace("\n", " | "))
    ta.flyout.popup()
    QTimer.singleShot(1200, step2)


def step2():
    app.processEvents()
    # 冒烟全程要测量可见状态下的尺寸，先停掉「失焦兜底收起」定时器，免得中途被收起来
    ta.flyout._watchdog.stop()
    ta.flyout.grab().save(os.path.join(OUT, "live_devices.png"))
    page = ta.flyout.devices_page
    print("flyout:", ta.flyout.isVisible(), ta.flyout.width(), "x", ta.flyout.height())
    print("flyout stack?", hasattr(ta.flyout, "stack"))

    try:
        page.device_clicked.disconnect()
    except Exception:                              # noqa: BLE001
        pass
    page.device_clicked.connect(lambda d: state.update(clicked=d.get("name")))
    rows = [w for w in page.list_host.findChildren(object)
            if w.__class__.__name__ == "DeviceRow" and w.isVisible()]
    print("device rows:", len(rows))

    # 悬停设备行不能弹 tooltip；先用「临时加 tooltip」做正对照，证明检测手段有效
    if rows:
        from PySide6.QtGui import QHelpEvent
        from PySide6.QtWidgets import QToolTip

        def hover(widget):
            local = widget.rect().center()
            ev = QHelpEvent(QEvent.Type.ToolTip, local, widget.mapToGlobal(local))
            QApplication.sendEvent(widget, ev)
            wait(150)
            shown = QToolTip.isVisible()
            QToolTip.hideText()
            wait(320)                              # 等淡出结束，避免影响下一次判定
            return shown

        target = rows[0].percent
        negative_a = hover(target)                 # 移除后：不该出现
        rows[0].setToolTip("正对照")
        positive = hover(target)                   # 临时加回来：必须出现，证明检测有效
        rows[0].setToolTip("")
        negative_b = hover(target)
        print(f"tooltip 正对照 {positive} / 移除后 {negative_a},{negative_b} (应为 True / False,False)")

    if rows:
        rows[0].clicked.emit(rows[0].device)
    app.processEvents()
    print("device_clicked ->", state["clicked"])

    # 刷新重绘：设备列表变化时窗口高度要跟着变，且内容不能溢出
    keep = list(page._devices)
    h_dev = ta.flyout.height()
    page.set_devices([])
    wait(260)
    h_empty = ta.flyout.height()
    fit_empty = page.height() <= ta.flyout.surface.height()
    ta.flyout.grab().save(os.path.join(OUT, "live_empty.png"))
    page.set_devices(keep)
    wait(260)
    h_back = ta.flyout.height()
    fit_back = page.height() <= ta.flyout.surface.height()
    print(f"刷新重绘：高度 {h_dev}→{h_empty}→{h_back} | 内容未溢出 {fit_empty},{fit_back} "
          f"| 行数 {page.row_count()}/{len(keep)}")

    dlg = PromptDialog(ta.config, page._devices[0] if rows else None)
    text = dlg.text.toPlainText()
    print("prompt dialog: devices =", dlg.combo.count(),
          "| lines =", len(text.splitlines()),
          "| bundle 格式:", "strelitzia-hid-battery-profile" in text,
          "| code_lines:", "code_lines" in text)
    dlg.grab().save(os.path.join(OUT, "live_prompt.png"))
    dlg.close()

    console = ta._ensure_console()
    console.show()
    app.processEvents()
    for key, name in (("stats", "live_history"), ("settings", "live_settings"),
                      ("probe", "live_probe")):
        console.open_page(key)
        app.processEvents()
        app.processEvents()
        print(f"console[{key}] window {console.width()}x{console.height()} "
              f"page {console.stack.currentWidget().__class__.__name__}")
        console.grab().save(os.path.join(OUT, f"{name}.png"))

    sp = console.settings_page
    icon_rows = [w for w in sp.icon_box.parentWidget().findChildren(object)
                 if w.__class__.__name__ == "IconRow"]
    print("settings scroll max:", sp.scroll.verticalScrollBar().maximum(),
          "| icon rows:", len(icon_rows))
    print("probe status:", console.probe_page.status.text())
    print("history chart:", console.history_page.chart.width(),
          "x", console.history_page.chart.height())
    console.close()
    wait(300)

    # 设置页 → 接口探测（页面切换）
    console.open_page("settings")
    console.settings_page.probe_requested.emit()
    wait(300)
    print("settings -> probe switch:", console.stack.currentWidget().__class__.__name__)

    # UI 层导入接入包（临时文件，导入后回滚）
    import json
    import shutil
    import tempfile

    from app import plugin_store, profiles

    backup = profiles.PROFILE_PATH + ".smoke.bak"
    shutil.copy2(profiles.PROFILE_PATH, backup)
    tmpdir = tempfile.mkdtemp()
    plugin_file = os.path.join(plugin_store.PLUGIN_DIR, "smoke_bundle.py")
    try:
        bundle = {
            "kind": "strelitzia-hid-battery-profile",
            "version": 1,
            "protocol": {"filename": "smoke_bundle.py", "code_lines": [
                "from __future__ import annotations",
                "from typing import Any, Dict",
                "from app.hid_core import BatteryReading",
                "from app.protocols.base import Param, Protocol",
                "from app.protocols.registry import register",
                "",
                "@register",
                "class SmokeBundle(Protocol):",
                "    id = \"smoke-bundle\"",
                "    label = \"冒烟 · 接入包\"",
                "    vendor = \"SMOKE\"",
                "    usage_pages = (0xFFF1,)",
                "    params = [Param(\"report_id\", \"ID\", \"hex\", 0)]",
                "    def query(self, dev, cfg: Dict[str, Any]) -> BatteryReading:",
                "        return BatteryReading(percent=66)",
            ]},
            "profile": {"id": "smoke-bundle", "name": "冒烟 · 接入包", "vendor_id": 0x9911,
                        "usage_pages": [0xFFF1], "protocol": "smoke-bundle", "models": {}},
        }
        path = os.path.join(tmpdir, "bundle.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(bundle, fh, ensure_ascii=False)
        ok = console.import_bundle(path)
        print("bundle import:", ok, "|", console.settings_page.import_hint.text()[:46],
              "| profiles:", len(ta.config["profiles"]))
    finally:
        shutil.move(backup, profiles.PROFILE_PATH)
        if os.path.isfile(plugin_file):
            os.remove(plugin_file)
        shutil.rmtree(tmpdir, ignore_errors=True)
    console.close()
    wait(200)

    # 失焦自动收起
    ta.flyout.popup()
    wait(500)
    print("popup visible:", ta.flyout.isVisible())
    ta.flyout.event(QEvent(QEvent.Type.WindowDeactivate))
    wait(600)
    print("after deactivate -> visible:", ta.flyout.isVisible(), "(应为 False)")

    # 面板设置按钮 → 独立窗口
    ta.flyout.popup()
    wait(400)
    ta.flyout.devices_page.settings_requested.emit()
    wait(500)
    print("settings button -> console:", ta._console.isVisible(),
          "| page:", ta._console.stack.currentWidget().__class__.__name__,
          "| window title:", ta._console.windowTitle(),
          "| flyout hidden:", not ta.flyout.isVisible())
    ta._console.close()
    QTimer.singleShot(300, done)


def done():
    print("OK")
    app.quit()


QTimer.singleShot(1800, step1)
QTimer.singleShot(16000, app.quit)
sys.exit(app.exec())
