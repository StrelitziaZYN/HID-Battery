"""接入新设备：检测已连接设备 → 生成标准化提示词 → 导入 AI 返回的接入包。

界面与流程一一对应：
  ① 检测已连接的 HID 设备（下拉列表，可重新检测）
  ② 选中设备 → 生成提示词 → 复制给 AI Agent
  ③ AI 给出 JSON 接入包 → 点「导入接入包」直接装好
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QTextCursor
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget)

from . import plugin_store, prompt_builder, scanner, theme
from .widgets import ElidedLabel, FlatButton, IconButton, Surface


class PromptDialog(QDialog):
    """设备接入提示词对话框。device 为空时只展示检测结果。"""

    bundle_imported = Signal()

    def __init__(self, config: Dict[str, Any], device: Optional[Dict[str, Any]] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self._devices: List[Dict[str, Any]] = []
        self._device: Dict[str, Any] = {}

        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setFixedWidth(660)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        surf = Surface(radius=12)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 70))
        surf.setGraphicsEffect(shadow)
        outer.addWidget(surf)

        lay = QVBoxLayout(surf)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)

        # 标题
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        title = QLabel("接入新设备")
        title.setFont(theme.ui_font(12, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        head.addWidget(title)
        head.addStretch(1)
        close = IconButton(theme.ICON["close"], size=26, icon_size=8, tooltip="关闭")
        close.clicked.connect(lambda *_: self.reject())
        head.addWidget(close)
        lay.addLayout(head)

        subtitle = QLabel("① 检测已连接设备　② 生成提示词交给 AI　③ 导入 AI 返回的接入包")
        subtitle.setFont(theme.ui_font(8))
        subtitle.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        lay.addWidget(subtitle)
        lay.addSpacing(2)

        # ① 检测
        self.step1 = QLabel("① 已连接的 HID 设备")
        self.step1.setFont(theme.ui_font(8, QFont.Weight.DemiBold))
        self.step1.setStyleSheet(f"color: {theme.C.TEXT_SECONDARY.name()};")
        lay.addWidget(self.step1)

        pick = QHBoxLayout()
        pick.setContentsMargins(0, 0, 0, 0)
        pick.setSpacing(6)
        self.combo = QComboBox()
        self.combo.setStyleSheet(theme.INPUT_QSS)
        self.combo.setFont(theme.ui_font(9))
        self.combo.setMinimumWidth(380)
        self.combo.currentIndexChanged.connect(lambda *_: self._on_pick())
        pick.addWidget(self.combo, 1)
        self.btn_detect = FlatButton("重新检测", glyph=theme.ICON["refresh"])
        self.btn_detect.clicked.connect(lambda *_: self.detect(preselect_uid=self._device.get("uid")))
        pick.addWidget(self.btn_detect)
        lay.addLayout(pick)

        self.summary = ElidedLabel("")
        self.summary.setFont(theme.ui_font(8))
        self.summary.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()}; padding: 2px 0 0 2px;")
        lay.addWidget(self.summary)
        lay.addSpacing(4)

        # ② 提示词
        step2_head = QHBoxLayout()
        step2_head.setContentsMargins(0, 0, 0, 0)
        step2 = QLabel("② 接入提示词")
        step2.setFont(theme.ui_font(8, QFont.Weight.DemiBold))
        step2.setStyleSheet(f"color: {theme.C.TEXT_SECONDARY.name()};")
        step2_head.addWidget(step2)
        step2_head.addStretch(1)
        self.counter = QLabel("")
        self.counter.setFont(theme.ui_font(7))
        self.counter.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        step2_head.addWidget(self.counter)
        lay.addLayout(step2_head)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFixedHeight(322)
        mono = theme.ui_font(8)
        mono.setFamilies(["Cascadia Mono", "Consolas", "Microsoft YaHei UI"])
        self.text.setFont(mono)
        self.text.setStyleSheet(theme.INPUT_QSS + "QPlainTextEdit{padding:6px 8px;}")
        lay.addWidget(self.text)

        tip = QLabel("提示词只包含本机实测信息，并要求 AI 返回一个 JSON 接入包；"
                     "拿到后点「导入接入包」选中它，插件与接口配置会自动装好。")
        tip.setWordWrap(True)
        tip.setFont(theme.ui_font(7))
        tip.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()}; padding: 2px;")
        lay.addWidget(tip)

        # 底部
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        self.hint = QLabel("")
        self.hint.setFont(theme.ui_font(8))
        self.hint.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        actions.addWidget(self.hint)
        actions.addStretch(1)
        self.btn_import = FlatButton("导入接入包", glyph=theme.ICON["upload"])
        self.btn_import.clicked.connect(lambda *_: self._pick_bundle())
        actions.addWidget(self.btn_import)
        copy = FlatButton("复制提示词", glyph=theme.ICON["link"], primary=True)
        copy.clicked.connect(lambda *_: self._copy())
        actions.addWidget(copy)
        lay.addLayout(actions)

        self.detect(initial=device)

    # ------------------------------------------------------------------ #
    def detect(self, preselect_uid: str = "", initial: Optional[Dict[str, Any]] = None):
        """第一步：枚举本机所有 HID 设备。"""
        self.hint.setText("正在检测…")
        QGuiApplication.processEvents()
        self._devices = scanner.list_connected(self.config)
        self.combo.blockSignals(True)
        self.combo.clear()
        for idx, dev in enumerate(self._devices):
            mark = "已支持" if dev.get("supported") else "未接入"
            self.combo.addItem(f"{dev['name']} · {dev['vendor']} · {mark}", idx)

        target = None
        if initial:
            target = self._find(initial)
            if target is not None:
                # 用主面板已有的读数补齐（避免重复查询）
                target.update({k: initial[k] for k in
                               ("percent", "charging", "connection", "real_pid", "model")
                               if initial.get(k) is not None})
                target["supported"] = True
        elif preselect_uid:
            target = self._find({"uid": preselect_uid})

        self.step1.setText(f"① 已连接的 HID 设备（{len(self._devices)}）")
        if self._devices:
            idx = self._devices.index(target) if target in self._devices else 0
            self.combo.setCurrentIndex(max(0, idx))
            self.hint.setText(f"检测到 {len(self._devices)} 个 HID 设备")
        else:
            self.combo.blockSignals(False)
            self._device = {}
            self.text.setPlainText("未检测到任何 HID 设备，请插入接收器后点「重新检测」。")
            self.summary.setText("")
            self.counter.setText("")
            self.hint.setText("没有可用设备")
            return
        # 只在选定后生成一次，避免重复查询设备
        self.combo.blockSignals(False)
        self._on_pick()

    def _find(self, sample: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        vid = sample.get("vendor_id")
        pid = sample.get("product_id")
        product = sample.get("product_string") or sample.get("product") or ""
        for dev in self._devices:
            if vid is not None and dev.get("vendor_id") != vid:
                continue
            if pid is not None and dev.get("product_id") != pid:
                continue
            if product and dev.get("product_string") and dev["product_string"] != product:
                continue
            return dev
        return None

    def _on_pick(self):
        """第二步：选中设备 → 生成提示词。"""
        idx = self.combo.currentIndex()
        if not (0 <= idx < len(self._devices)):
            return
        dev = self._devices[idx]
        self.hint.setText("正在补全设备信息…")
        QGuiApplication.processEvents()
        try:
            self._device = scanner.enrich(dev, self.config)
        except Exception:                          # noqa: BLE001
            self._device = dev

        d = self._device
        bits = [d.get("name"), d.get("vendor"), prompt_builder.conn_text(d)]
        self.summary.setText(" · ".join(b for b in bits if b))

        prompt = prompt_builder.build(d)
        self.text.setPlainText(prompt)
        self.text.moveCursor(QTextCursor.MoveOperation.Start)
        self.counter.setText(f"{len(prompt.splitlines())} 行 · {len(prompt)} 字")
        self.hint.setText("提示词已生成" if d.get("supported") else "该设备尚未接入，提示词将要求 AI 逆向协议")

    def _copy(self):
        text = self.text.toPlainText()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.hint.setText("已复制到剪贴板，粘贴给 AI Agent 即可")

    def _pick_bundle(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 AI 返回的接入包", "",
            "接入包 (*.json *.py);;JSON (*.json);;插件 (*.py);;所有文件 (*.*)")
        if path:
            self.import_bundle(path)

    def import_bundle(self, path: str) -> bool:
        try:
            info = plugin_store.import_file(path, self.config)
        except Exception as exc:                   # noqa: BLE001
            self.hint.setText(f"导入失败：{exc}")
            self.hint.setStyleSheet(f"color: {theme.C.DANGER.name()};")
            return False

        names = "、".join(info.get("profiles") or []) or "（未带接口配置，需在设置页新增接口）"
        self.hint.setStyleSheet(f"color: {theme.C.OK.name()};")
        self.hint.setText(f"已导入插件 {info.get('protocol') or '-'} · 接口 {names}")
        self.bundle_imported.emit()
        self.detect(preselect_uid=self._device.get("uid"))
        return True

    def selected_device(self) -> Dict[str, Any]:
        return self._device
