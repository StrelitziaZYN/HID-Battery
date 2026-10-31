"""接口探测页：把每个已启用接口对应的厂商 HID 集合回包全打出来。

用途：适配新设备时确认「哪个集合能读到电量、回包长什么样」。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget)

from . import theme
from .scanner import probe_interfaces
from .widgets import FlatButton


class ProbePage(QWidget):
    def __init__(self, config_provider: Callable[[], Dict[str, Any]], parent=None):
        super().__init__(parent)
        self._config_provider = config_provider

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        title = QLabel("接口探测")
        title.setFont(theme.ui_font(13, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        head.addWidget(title)
        head.addStretch(1)
        self.btn_run = FlatButton("开始探测", glyph=theme.ICON["info"], primary=True)
        self.btn_run.clicked.connect(lambda *_: self.run_probe())
        self.btn_copy = FlatButton("复制结果", glyph=theme.ICON["link"])
        self.btn_copy.clicked.connect(lambda *_: self._copy())
        head.addWidget(self.btn_run)
        head.addWidget(self.btn_copy)
        root.addLayout(head)
        root.addSpacing(6)

        hint = QLabel("对每个已启用接口的厂商私有集合（Usage Page ≥ 0xFF00）发一次电量命令，"
                      "打印电量与原始回包。调试新设备时先看这里，再决定参数。")
        hint.setWordWrap(True)
        hint.setFont(theme.ui_font(8))
        hint.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        root.addWidget(hint)
        root.addSpacing(8)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        mono = theme.ui_font(9)
        mono.setFamilies(["Cascadia Mono", "Consolas", "Microsoft YaHei UI"])
        self.text.setFont(mono)
        self.text.setStyleSheet(theme.INPUT_QSS + "QPlainTextEdit{padding:8px 10px;}")
        root.addWidget(self.text, 1)

        self.status = QLabel("尚未探测")
        self.status.setFont(theme.ui_font(8))
        self.status.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()}; padding-top:4px;")
        root.addWidget(self.status)
        self._last_run = 0.0

    # ------------------------------------------------------------------ #
    def auto_run(self):
        """切到本页时按需自动探测：已有结果且一分钟内不再重复（避免每次切页都卡一下）。"""
        if not self.text.toPlainText() or time.time() - self._last_run > 60:
            self.run_probe()

    def run_probe(self):
        config = self._config_provider() or {}
        profiles = [p for p in config.get("profiles", []) if p.get("enabled", True)]
        self._last_run = time.time()
        self.status.setText("正在探测…")
        QGuiApplication.processEvents()

        lines: List[str] = []
        count = 0
        for profile in profiles:
            vid = int(profile.get("vendor_id", 0))
            items = probe_interfaces(vid, profile)
            if not items:
                continue
            lines.append(f"=== {profile.get('name') or profile.get('id')} "
                         f"({profile.get('protocol')}) · VID {vid:#06x} ===")
            for item in items:
                count += 1
                lines.append(f"[{item['usage_page']:#06x}/{item['usage']:#04x}] "
                             f"PID {item['product_id']:#06x} · {item['product']}")
                if item["ok"]:
                    conn = {1: "有线", 2: "2.4G", 3: "蓝牙"}.get(item.get("connection"), "未知")
                    lines.append(f"   电量 {item['percent']}% · "
                                 f"{'充电中' if item['charging'] else '放电中'} · {conn}")
                else:
                    lines.append(f"   ✕ {item['error']}")
                if item["raw"]:
                    lines.append(f"   raw: {item['raw'][:120]}")
            lines.append("")

        if not lines:
            self.text.setPlainText("没有可探测的厂商私有集合（Usage Page ≥ 0xFF00）。\n"
                                   "请确认接收器已插入，或先在「接口设置」里启用对应厂商接口。")
            self.status.setText("探测完成：0 个集合")
            return

        self.text.setPlainText("\n".join(lines).rstrip())
        self.status.setText(f"探测完成：{len(profiles)} 个接口 · {count} 个私有集合")

    def _copy(self):
        text = self.text.toPlainText()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.status.setText("已复制到剪贴板")
