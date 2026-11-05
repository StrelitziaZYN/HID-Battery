"""接口调试面板：由用户点击按钮触发一次，打印已启用接口的私有集合回包。

只在用户主动点击「开始调试」时执行，不做任何自动探测 / 定时发送。
用途：适配新设备时确认「哪个集合能读到电量、回包长什么样」。

界面只负责「工具条 + 说明 + 输出区」，标题与状态胶囊由外层设置页的卡片提供。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout,
                               QWidget)

from . import i18n, theme
from .scanner import probe_interfaces
from .widgets import Badge, FlatButton


class ProbePanel(QWidget):
    """嵌在「接口设置」里的调试块：按钮 + 只读日志，绝不自动运行。"""

    def __init__(self, config_provider: Callable[[], Dict[str, Any]], parent=None):
        super().__init__(parent)
        self._config_provider = config_provider
        self._last_run = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # 状态胶囊：由外层卡片放进标题右侧，这里只负责更新它的文字
        self.status = Badge(i18n.T("尚未调试"), "neutral")

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)
        self.btn_run = FlatButton(i18n.T("开始调试"), glyph=theme.ICON["terminal"], primary=True)
        self.btn_run.clicked.connect(lambda *_: self.run())
        self.btn_copy = FlatButton(i18n.T("复制结果"), glyph=theme.ICON["copy"])
        self.btn_copy.clicked.connect(lambda *_: self._copy())
        self.btn_clear = FlatButton(i18n.T("清空"))
        self.btn_clear.clicked.connect(lambda *_: self.clear())
        bar.addWidget(self.btn_run)
        bar.addWidget(self.btn_copy)
        bar.addWidget(self.btn_clear)
        bar.addStretch(1)
        root.addLayout(bar)

        hint = QLabel(i18n.T("点击「开始调试」才会对已启用接口的厂商私有集合"
                      "（Usage Page ≥ 0xFF00）发一次电量命令；平时不发送任何探测包。"))
        hint.setWordWrap(True)
        hint.setFont(theme.ui_font(7))
        hint.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        root.addWidget(hint)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFixedHeight(142)
        mono = theme.ui_font(8)
        mono.setFamilies(["Cascadia Mono", "Consolas", "Microsoft YaHei UI"])
        self.text.setFont(mono)
        self.text.setStyleSheet(
            theme.INPUT_QSS + "QPlainTextEdit{padding:9px 11px; border-radius:6px;"
            "background: rgba(255,255,255,235);}")
        self.text.setPlaceholderText(
            i18n.T("调试结果会显示在这里（仅在点击「开始调试」后产生）"))
        root.addWidget(self.text)

    # ------------------------------------------------------------------ #
    def clear(self):
        self.text.clear()
        self.status.setText(i18n.T("尚未调试"), "neutral")

    def run(self):
        """用户主动触发的唯一入口。"""
        config = self._config_provider() or {}
        profiles = [p for p in config.get("profiles", []) if p.get("enabled", True)]
        self._last_run = time.time()
        self.status.setText(i18n.T("正在调试…"), "accent")
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
                    conn = {1: i18n.T("有线"), 2: i18n.T("2.4G"),
                            3: i18n.T("蓝牙")}.get(item.get("connection"), i18n.T("未知"))
                    lines.append("   " + i18n.TF("电量 {}% · {} · {}", item['percent'],
                                 i18n.T("充电中") if item['charging'] else i18n.T("放电中"), conn))
                else:
                    lines.append(f"   ✕ {item['error']}")
                if item["raw"]:
                    lines.append(f"   raw: {item['raw'][:120]}")
            lines.append("")

        if not lines:
            self.text.setPlainText(i18n.T("没有可调试的厂商私有集合（Usage Page ≥ 0xFF00）。\n"
                                   "请确认接收器已插入，或在上方启用对应厂商接口。"))
            self.status.setText(i18n.T("调试完成 · 0 个集合"), "warn")
            return

        self.text.setPlainText("\n".join(lines).rstrip())
        self.status.setText(i18n.TF("调试完成 · {} 个接口 · {} 个私有集合",
                                    len(profiles), count), "ok")

    def _copy(self):
        text = self.text.toPlainText()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.status.setText(i18n.T("已复制到剪贴板"), "accent")
