"""设置窗口里的两个「设置类」页面（各自作为左侧导航的一个标签页）。

- GeneralSettingsPage：通用设置（刷新节奏、开机自启、恢复默认）
- InterfaceSettingsPage：接口设置（协议插件、AI 接入包、设备图标、接口调试）
电量统计页在 history_page.py（含采样间隔），三页共同组成左侧导航的三个标签。
"""
from __future__ import annotations

import copy
import json
import os
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFrame,
                               QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget)

from . import autostart, icon_store, plugin_store, theme
from .paths import CONFIG_DIR, DATA_DIR, PLUGIN_DIR
from .probe_page import ProbePanel
from .profiles import default_config, new_profile, save_config
from .protocols import all_protocols, get_protocol
from .widgets import ElidedLabel, FlatButton, IconButton, Surface, ToggleSwitch

INPUT_QSS = theme.INPUT_QSS


class SectionLabel(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setFont(theme.ui_font(8, QFont.Weight.DemiBold))
        self.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()}; padding: 4px 2px 2px 2px;")


class SectionCard(Surface):
    """一个区域卡片：图标 + 标题 + 一句话说明，下面挂内容。"""

    def __init__(self, title: str, glyph: str, subtitle: str = "", parent=None):
        super().__init__(parent, radius=10, fill=theme.C.SURFACE, border=theme.C.STROKE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(8)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(9)
        icon = theme.icon_label(theme.ICON.get(glyph, glyph), size=12, color=theme.C.ACCENT)
        head.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        name = QLabel(title)
        name.setFont(theme.ui_font(10, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        col.addWidget(name)
        if subtitle:
            tip = QLabel(subtitle)
            tip.setFont(theme.ui_font(7))
            tip.setWordWrap(True)
            tip.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
            col.addWidget(tip)
        head.addLayout(col, 1)
        outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 2, 0, 0)
        self.body.setSpacing(2)
        outer.addLayout(self.body)


class ProfileRow(QWidget):
    edited = Signal(str)
    toggled = Signal(str, bool)
    removed = Signal(str)

    def __init__(self, profile: dict, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setFixedHeight(52)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 6, 4)
        lay.setSpacing(8)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        name = ElidedLabel(profile.get("name", "未命名接口"))
        name.setFont(theme.ui_font(9, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        vid = profile.get("vendor_id", 0)
        proto = get_protocol(str(profile.get("protocol", "")))
        label = f"插件 {proto.id}" if proto else f"{profile.get('protocol', '?')}（未注册）"
        summary = ElidedLabel(f"VID {int(vid):#06x} · {label}")
        summary.setFont(theme.ui_font(7))
        summary.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        col.addWidget(name)
        col.addWidget(summary)
        lay.addLayout(col, 1)

        self.toggle = ToggleSwitch(profile.get("enabled", True))
        self.toggle.toggled.connect(lambda v: self.toggled.emit(profile.get("id", ""), v))
        lay.addWidget(self.toggle)

        btn_edit = IconButton(theme.ICON["edit"], size=26, icon_size=8, tooltip="编辑")
        btn_edit.clicked.connect(lambda: self.edited.emit(profile.get("id", "")))
        lay.addWidget(btn_edit)

        btn_del = IconButton(theme.ICON["delete"], size=26, icon_size=8, tooltip="删除")
        btn_del.clicked.connect(lambda: self.removed.emit(profile.get("id", "")))
        lay.addWidget(btn_del)

    def paintEvent(self, event):                   # noqa: N802
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 8))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0, 2, 0, -2), 7, 7)


class IconRow(QWidget):
    """一个设备的图标行：预览 + 名称 + 上传 / 清除。图标全部由用户自己提供。"""

    upload_requested = Signal(str)
    clear_requested = Signal(str)

    def __init__(self, device: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.device = device
        self.icon_key = device.get("icon_key") or icon_store.key_of(
            device.get("vendor_id", 0), device.get("product_id", 0))
        self.setFixedHeight(48)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 4, 4)
        lay.setSpacing(8)

        self.preview = QLabel()
        self.preview.setFixedSize(32, 32)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_preview(device.get("icon_path"))
        lay.addWidget(self.preview)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        name = ElidedLabel(device.get("name") or "未知设备")
        name.setFont(theme.ui_font(9, QFont.Weight.DemiBold))
        name.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        vid = int(device.get("vendor_id") or 0)
        pid = int(device.get("real_pid") or device.get("product_id") or 0)
        state = "已上传" if device.get("icon_path") else "未上传"
        sub = ElidedLabel(f"VID {vid:#06x} · PID {pid:#06x} · 图标{state}")
        sub.setFont(theme.ui_font(7))
        sub.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        col.addWidget(name)
        col.addWidget(sub)
        lay.addLayout(col, 1)

        btn_up = IconButton(theme.ICON["upload"], size=26, icon_size=8, tooltip="上传图标")
        btn_up.clicked.connect(lambda *_: self.upload_requested.emit(self.icon_key))
        lay.addWidget(btn_up)

        if device.get("icon_path"):
            btn_clear = IconButton(theme.ICON["delete"], size=26, icon_size=8, tooltip="清除图标")
            btn_clear.clicked.connect(lambda *_: self.clear_requested.emit(self.icon_key))
            lay.addWidget(btn_clear)

    def _apply_preview(self, path: Optional[str]):
        if path:
            raw = QPixmap(path)
            if not raw.isNull():
                self.preview.setPixmap(raw.scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation))
                self.preview.setStyleSheet("background: transparent;")
                return
        self.preview.setText("—")
        self.preview.setFont(theme.ui_font(9))
        self.preview.setStyleSheet(
            f"color: {theme.C.TEXT_TERTIARY.name()}; background: rgba(0,0,0,8);"
            "border: 1px dashed rgba(0,0,0,45); border-radius: 7px;")


class SettingsPageBase(QWidget):
    """设置类页面的公共外壳：标题 + 滚动区 + 内容 body。"""

    back_requested = Signal()
    config_changed = Signal()

    def __init__(self, config: dict, title: str, embedded: bool = False, parent=None):
        super().__init__(parent)
        self.config = config
        self.embedded = embedded

        root = QVBoxLayout(self)
        root.setContentsMargins(0 if embedded else 16, 0 if embedded else 12,
                                0 if embedded else 16, 0 if embedded else 12)
        root.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(4)
        self.btn_back = IconButton(theme.ICON["back"], size=28, icon_size=9, tooltip="返回")
        self.btn_back.clicked.connect(lambda *_: self.back_requested.emit())
        head.addWidget(self.btn_back)
        if embedded:
            self.btn_back.hide()
        lb = QLabel(title)
        lb.setFont(theme.ui_font(13, QFont.Weight.DemiBold))
        lb.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        head.addWidget(lb)
        head.addStretch(1)
        root.addLayout(head)
        root.addSpacing(10)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;}"
                                  "QScrollBar:vertical{width:6px;background:transparent;margin:2px 0;}"
                                  "QScrollBar::handle:vertical{background:rgba(0,0,0,60);border-radius:3px;min-height:24px;}"
                                  "QScrollBar::add-line, QScrollBar::sub-line{height:0;}")
        self.host = QWidget()
        self.host.setStyleSheet("background: transparent;")
        self.body = QVBoxLayout(self.host)
        self.body.setContentsMargins(0, 0, 10, 0)
        self.body.setSpacing(12)
        self.scroll.setWidget(self.host)
        root.addWidget(self.scroll, 1)

    # ------------------------------------------------------------------ #
    def reload(self, config: dict):
        self.config = config
        self._reload()

    def _reload(self):                             # pragma: no cover - 子类实现
        raise NotImplementedError

    def _commit(self):
        save_config(self.config)
        self.config_changed.emit()

    def _row(self, label: str, widget: QWidget, hint: str = "") -> QVBoxLayout:
        """「左标签 + 右控件」的一行，可带右对齐的灰色说明。"""
        col = QVBoxLayout()
        col.setContentsMargins(2, 2, 2, 6)
        col.setSpacing(2)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        lb = QLabel(label)
        lb.setFont(theme.ui_font(9))
        lb.setStyleSheet(f"color: {theme.C.TEXT_SECONDARY.name()};")
        row.addWidget(lb)
        row.addStretch(1)
        row.addWidget(widget)
        col.addLayout(row)
        if hint:
            tip = QLabel(hint)
            tip.setFont(theme.ui_font(7))
            tip.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
            tip.setAlignment(Qt.AlignmentFlag.AlignRight)
            tip.setWordWrap(True)                  # 长说明必须换行，否则会把整页顶宽
            tip.setMinimumWidth(0)
            col.addWidget(tip)
        return col

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(0,0,0,22); border: none;")
        return line

    def preferred_height(self) -> int:
        """页面内容高度（不含面板外框留白，由 Flyout._fit 叠加）。"""
        if self.host.layout() is not None:
            self.host.layout().activate()
        hint = self.host.sizeHint().height()
        if hint <= 0:
            return 640
        return hint + 12 + 28 + 6 + 12


class GeneralSettingsPage(SettingsPageBase):
    """区域一：通用设置（刷新间隔 / 开机自启 / 恢复默认）。"""

    def __init__(self, config: dict, embedded: bool = False, parent=None):
        super().__init__(config, "通用设置", embedded, parent)

        card = SectionCard("通用设置", "settings", "设备清单的刷新节奏与开机行为")

        self.interval = QComboBox()
        self.interval.setStyleSheet(INPUT_QSS)
        self.interval.setFont(theme.ui_font(9))
        self.interval.setFixedWidth(104)
        for label, sec in (("30 秒", 30), ("1 分钟", 60), ("2 分钟", 120), ("5 分钟", 300)):
            self.interval.addItem(label, sec)
        self.interval.currentIndexChanged.connect(self._on_interval)
        card.body.addLayout(self._row("刷新间隔", self.interval,
                                      "设备清单与电量读数一起按此间隔刷新"))

        self.autostart_switch = ToggleSwitch(autostart.is_enabled())
        self.autostart_switch.toggled.connect(self._on_autostart)
        card.body.addLayout(self._row("开机自动启动", self.autostart_switch,
                                      "登录 Windows 后自动驻留托盘"))

        card.body.addWidget(self._divider())
        self.btn_reset = FlatButton("恢复默认", glyph=theme.ICON["refresh"])
        self.btn_reset.clicked.connect(lambda *_: self._reset())
        card.body.addLayout(self._row("恢复默认设置", self.btn_reset,
                                      "清空接口配置与偏好设置，回到出厂状态"))

        self.body.addWidget(card)
        self.body.addStretch(1)
        self.reload(config)

    def _reload(self):
        idx = self.interval.findData(int(self.config.get("refresh_interval", 60)))
        self.interval.blockSignals(True)
        self.interval.setCurrentIndex(idx if idx >= 0 else 1)
        self.interval.blockSignals(False)

        # 开机自启也可能被托盘右键菜单改过，这里始终重读注册表
        self.autostart_switch.blockSignals(True)
        self.autostart_switch.setChecked(autostart.is_enabled())
        self.autostart_switch.blockSignals(False)

    def _on_interval(self, _index: int):
        self.config["refresh_interval"] = int(self.interval.currentData())
        self._commit()

    def _on_autostart(self, checked: bool):
        if autostart.set_enabled(bool(checked)):
            return
        # 写注册表失败：把开关拨回去，避免界面与实际不一致
        self.autostart_switch.blockSignals(True)
        self.autostart_switch.setChecked(not checked)
        self.autostart_switch.blockSignals(False)
        self.autostart_switch.setToolTip("写入注册表失败，可能被安全软件拦截")

    def _reset(self):
        self.config.clear()
        self.config.update(json.loads(json.dumps(default_config())))
        self.reload(self.config)
        self._commit()


class InterfaceSettingsPage(SettingsPageBase):
    """区域三：接口设置（协议插件 / AI 接入包 / 设备图标 / 接口调试）。"""

    prompt_requested = Signal()
    icons_changed = Signal()

    def __init__(self, config: dict,
                 devices_provider: Optional[Callable[[], List[dict]]] = None,
                 embedded: bool = True, parent=None):
        self._devices_provider = devices_provider or (lambda: [])
        super().__init__(config, "接口设置", embedded, parent)

        iface = SectionCard("接口设置", "device", "协议插件、设备接入、图标与调试")

        iface.body.addWidget(SectionLabel("协议插件（厂商接口）"))
        self.profile_box = QVBoxLayout()
        self.profile_box.setSpacing(2)
        iface.body.addLayout(self.profile_box)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 4, 0, 2)
        self.btn_add = FlatButton("新增接口", glyph=theme.ICON["add"])
        self.btn_add.clicked.connect(lambda *_: self._add_profile())
        add_row.addWidget(self.btn_add)
        add_row.addStretch(1)
        iface.body.addLayout(add_row)

        iface.body.addWidget(SectionLabel("设备接入（AI 接入包）"))
        newdev = QHBoxLayout()
        newdev.setContentsMargins(0, 0, 0, 2)
        newdev.setSpacing(6)
        self.btn_new = FlatButton("检测设备并生成提示词", glyph=theme.ICON["device"], primary=True)
        self.btn_new.clicked.connect(lambda *_: self.prompt_requested.emit())
        self.btn_import = FlatButton("导入接入包", glyph=theme.ICON["upload"])
        self.btn_import.clicked.connect(lambda *_: self._pick_bundle())
        newdev.addWidget(self.btn_new)
        newdev.addWidget(self.btn_import)
        newdev.addStretch(1)
        iface.body.addLayout(newdev)

        newdev_hint = QLabel("① 点「检测设备并生成提示词」，把提示词交给 AI；"
                             "② AI 会给出一个 .json 接入包；③ 点「导入接入包」选中它 —— "
                             "插件与接口配置会自动装好，无需手动改文件。")
        newdev_hint.setWordWrap(True)
        newdev_hint.setFont(theme.ui_font(7))
        newdev_hint.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()}; padding: 0 2px 4px 2px;")
        iface.body.addWidget(newdev_hint)

        self.import_hint = QLabel("")
        self.import_hint.setWordWrap(True)
        self.import_hint.setFont(theme.ui_font(7))
        self.import_hint.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()}; padding: 0 2px 4px 2px;")
        self.import_hint.hide()
        iface.body.addWidget(self.import_hint)

        iface.body.addWidget(SectionLabel("设备图标（本机上传）"))
        self.icon_box = QVBoxLayout()
        self.icon_box.setSpacing(2)
        iface.body.addLayout(self.icon_box)

        self.icon_hint = QLabel("")
        self.icon_hint.setWordWrap(True)
        self.icon_hint.setFont(theme.ui_font(7))
        self.icon_hint.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()}; padding: 2px 2px 4px 2px;")
        iface.body.addWidget(self.icon_hint)

        iface.body.addWidget(self._divider())
        self.probe_panel = ProbePanel(lambda: self.config)
        iface.body.addWidget(self.probe_panel)

        iface.body.addWidget(self._divider())
        tools = QHBoxLayout()
        tools.setContentsMargins(0, 4, 0, 4)
        tools.setSpacing(6)
        self.btn_example = FlatButton("导出示例接入包")
        self.btn_example.clicked.connect(lambda *_: self._export_example())
        self.btn_folder = FlatButton("打开数据目录", glyph=theme.ICON["device"])
        self.btn_folder.clicked.connect(lambda *_: self._open_folder())
        tools.addWidget(self.btn_example)
        tools.addWidget(self.btn_folder)
        tools.addStretch(1)
        iface.body.addLayout(tools)

        self.data_hint = QLabel(f"数据目录：{DATA_DIR}　·　用户插件：{PLUGIN_DIR}")
        self.data_hint.setWordWrap(True)
        self.data_hint.setFont(theme.ui_font(7))
        self.data_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.data_hint.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()}; padding: 0 2px 2px 2px;")
        iface.body.addWidget(self.data_hint)

        self.body.addWidget(iface)
        self.body.addStretch(1)
        self.reload(config)

    # ------------------------------------------------------------------ #
    def _reload(self):
        while self.profile_box.count():
            item = self.profile_box.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        for prof in self.config.get("profiles", []):
            row = ProfileRow(prof)
            row.edited.connect(self._edit_profile)
            row.toggled.connect(self._toggle_profile)
            row.removed.connect(self._remove_profile)
            self.profile_box.addWidget(row)

        self._reload_icons()
        self._show_plugin_errors()

    def _show_plugin_errors(self):
        """用户插件目录里加载失败的插件，直接在设置页提示出来。"""
        errors = plugin_store.errors()
        if not errors:
            if self.import_hint.text().startswith("以下插件加载失败"):
                self.import_hint.hide()
            return
        self._set_import_hint("以下插件加载失败（可修正后重启）：" + "；".join(errors[:3]),
                              error=True)

    def _reload_icons(self):
        while self.icon_box.count():
            item = self.icon_box.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        devices = list(self._devices_provider() or [])
        self._icon_count = len(devices)
        if devices:
            for dev in devices:
                row = IconRow(dev)
                row.upload_requested.connect(self._upload_icon)
                row.clear_requested.connect(self._clear_icon)
                self.icon_box.addWidget(row)
        else:
            empty = QLabel("暂无可设置图标的设备：先让主面板检测到设备再回到这里")
            empty.setWordWrap(True)
            empty.setFont(theme.ui_font(7))
            empty.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()}; padding: 2px;")
            self.icon_box.addWidget(empty)

        self.icon_hint.setText(
            f"图标由你自己上传（PNG/JPG，自动裁到 128px），存在本机 assets/icons/，"
            f"当前 {icon_store.count()} 张；未上传的设备不显示图标。")

    # ------------------------------------------------------------------ #
    def _upload_icon(self, key: str):
        path, _ = QFileDialog.getOpenFileName(self, "选择设备图标", "",
                                              "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.ico)")
        if not path:
            return
        try:
            icon_store.save(key, path)
        except Exception as exc:                   # noqa: BLE001
            self.icon_hint.setText(f"上传失败：{exc}")
            return
        self._reload_icons()
        self.icons_changed.emit()

    def _clear_icon(self, key: str):
        if icon_store.clear(key):
            self._reload_icons()
            self.icons_changed.emit()

    def _toggle_profile(self, pid: str, enabled: bool):
        for prof in self.config.get("profiles", []):
            if prof.get("id") == pid:
                prof["enabled"] = enabled
                break
        self._commit()

    def _remove_profile(self, pid: str):
        self.config["profiles"] = [p for p in self.config.get("profiles", []) if p.get("id") != pid]
        self.reload(self.config)
        self._commit()

    def _add_profile(self):
        protos = all_protocols()
        if not protos:
            return
        current = next((p.get("protocol") for p in self.config.get("profiles", [])
                        if p.get("enabled", True)), "")
        dlg = ProtocolPicker(protos, current, self.window())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        proto = dlg.selected()
        if proto is None:
            return
        profile = new_profile(proto.id, index=len(self.config.get("profiles", [])))
        self._open_editor(profile, is_new=True)

    def _edit_profile(self, pid: str):
        for prof in self.config.get("profiles", []):
            if prof.get("id") == pid:
                self._open_editor(copy.deepcopy(prof), is_new=False)
                return

    def _open_editor(self, profile: dict, is_new: bool):
        dlg = ProfileDialog(profile, self.window())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.result_profile()
            existing = {p.get("id"): i for i, p in enumerate(self.config.get("profiles", []))}
            if not is_new and profile.get("id") in existing:
                self.config["profiles"][existing[profile["id"]]] = data
            else:
                self.config.setdefault("profiles", []).append(data)
            self.reload(self.config)
            self._commit()

    # ------------------------------------------------------------------ #
    def _set_import_hint(self, text: str, error: bool = False):
        self.import_hint.setText(text)
        color = theme.C.DANGER.name() if error else theme.C.OK.name()
        self.import_hint.setStyleSheet(f"color: {color}; padding: 0 2px 4px 2px;")
        self.import_hint.show()

    def _pick_bundle(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 AI 接入包", "",
            "接入包 (*.json *.py);;JSON 配置 (*.json);;协议插件 (*.py);;所有文件 (*.*)")
        if path:
            self.import_bundle(path)

    def import_bundle(self, path: str) -> bool:
        """导入 .json 接入包 / .py 插件；成功后立刻刷新接口列表。"""
        try:
            info = plugin_store.import_file(path, self.config)
        except plugin_store.BundleError as exc:
            self._set_import_hint(f"导入失败：{exc}", error=True)
            return False
        except Exception as exc:                   # noqa: BLE001
            self._set_import_hint(f"导入失败：{exc}", error=True)
            return False

        self.reload(self.config)
        self.config_changed.emit()
        names = "、".join(info.get("profiles") or []) or "（未附带接口配置，请手动新增接口）"
        plugin = info.get("protocol") or "-"
        self._set_import_hint(f"已导入：插件 {plugin} · 接口 {names}。"
                              f"若主面板还没出现设备，点一下刷新。")
        return True

    def _export_example(self):
        path = plugin_store.write_example(CONFIG_DIR)
        self._set_import_hint(f"示例接入包已写入：{path}")

    def _open_folder(self):
        os.startfile(DATA_DIR)                     # noqa: S606  (Windows 专用)


class ProtocolPicker(QDialog):
    """新增接口时先选一个协议插件。"""

    def __init__(self, protos, preselect: str = "", parent=None):
        super().__init__(parent)
        self._protos = protos
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setFixedWidth(420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        surf = Surface(radius=12)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 70))
        surf.setGraphicsEffect(shadow)
        outer.addWidget(surf)

        lay = QVBoxLayout(surf)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)

        title = QLabel("选择协议插件")
        title.setFont(theme.ui_font(11, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        lay.addWidget(title)

        self.combo = QComboBox()
        self.combo.setStyleSheet(INPUT_QSS)
        self.combo.setFont(theme.ui_font(9))
        for proto in protos:
            self.combo.addItem(f"{proto.label} · {proto.id}", proto.id)
        if preselect:
            idx = self.combo.findData(preselect)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
        lay.addWidget(self.combo)

        self.desc = QLabel(protos[0].description)
        self.desc.setWordWrap(True)
        self.desc.setFont(theme.ui_font(8))
        self.desc.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        lay.addWidget(self.desc)
        self.combo.currentIndexChanged.connect(self._on_change)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = FlatButton("取消")
        cancel.clicked.connect(lambda *_: self.reject())
        ok = FlatButton("下一步", primary=True)
        ok.clicked.connect(lambda *_: self.accept())
        actions.addWidget(cancel)
        actions.addWidget(ok)
        lay.addLayout(actions)

    def _on_change(self, index: int):
        if 0 <= index < len(self._protos):
            self.desc.setText(self._protos[index].description)

    def selected(self):
        return get_protocol(self.combo.currentData())


class ProfileDialog(QDialog):
    """接口编辑对话框：字段由协议插件声明，自动生成。"""

    BASE_FIELDS = [
        ("name", "名称", "str"),
        ("vendor_id", "厂商 VID (十进制)", "int"),
        ("usage_pages", "Usage Page 列表", "intlist"),
        ("protocol", "协议插件", "choice"),
    ]

    def __init__(self, profile: dict, parent=None):
        super().__init__(parent)
        self.profile = copy.deepcopy(profile)
        self._editors: dict[str, QWidget] = {}

        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        surf = Surface(radius=12)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 70))
        surf.setGraphicsEffect(shadow)
        outer.addWidget(surf)

        lay = QVBoxLayout(surf)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        title = QLabel("接口参数")
        title.setFont(theme.ui_font(12, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        lay.addWidget(title)

        form = QVBoxLayout()
        form.setSpacing(6)
        for key, label, kind in self.BASE_FIELDS:
            form.addLayout(self._make_row(key, label, kind))
        lay.addLayout(form)

        self.params_label = SectionLabel("协议参数")
        lay.addWidget(self.params_label)
        self.param_box = QVBoxLayout()
        self.param_box.setSpacing(6)
        lay.addLayout(self.param_box)
        self._build_params()

        self.json_box = QPlainTextEdit()
        self.json_box.setStyleSheet(INPUT_QSS)
        self.json_box.setFont(theme.ui_font(8))
        self.json_box.setFixedHeight(150)
        self.json_box.setPlainText(json.dumps(self.profile, ensure_ascii=False, indent=2))
        self.json_box.hide()
        lay.addWidget(self.json_box)

        self.btn_json = FlatButton("高级参数 (JSON)", glyph=theme.ICON["down"])
        self.btn_json.clicked.connect(lambda *_: self._toggle_json())
        lay.addWidget(self.btn_json, 0, Qt.AlignmentFlag.AlignLeft)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = FlatButton("取消")
        cancel.clicked.connect(lambda *_: self.reject())
        ok = FlatButton("保存", primary=True)
        ok.clicked.connect(lambda *_: self._accept())
        actions.addWidget(cancel)
        actions.addWidget(ok)
        lay.addLayout(actions)

        self.setFixedWidth(520)

    # ------------------------------------------------------------------ #
    def _make_row(self, key: str, label: str, kind: str):
        row = QHBoxLayout()
        row.setSpacing(10)
        lb = QLabel(label)
        lb.setFont(theme.ui_font(9))
        lb.setStyleSheet(f"color: {theme.C.TEXT_SECONDARY.name()};")
        lb.setFixedWidth(132)
        row.addWidget(lb)

        if kind == "choice":
            w = QComboBox()
            w.setStyleSheet(INPUT_QSS)
            w.setFont(theme.ui_font(9))
            for proto in all_protocols():
                w.addItem(proto.label, proto.id)
            idx = w.findData(self.profile.get(key, ""))
            w.setCurrentIndex(max(0, idx))
            w.currentIndexChanged.connect(lambda *_: self._on_protocol())
        elif kind == "bool":
            w = QComboBox()
            w.setStyleSheet(INPUT_QSS)
            w.setFont(theme.ui_font(9))
            w.addItem("是", True)
            w.addItem("否", False)
            idx = w.findData(bool(self.profile.get(key, False)))
            w.setCurrentIndex(max(0, idx))
        else:
            w = QLineEdit()
            w.setStyleSheet(INPUT_QSS)
            w.setFont(theme.ui_font(9))
            w.setText(self._format(key, kind))
        self._editors[key] = w
        row.addWidget(w, 1)
        return row

    def _build_params(self):
        while self.param_box.count():
            item = self.param_box.takeAt(0)
            layout = item.layout()
            if layout is not None:
                while layout.count():
                    child = layout.takeAt(0)
                    w = child.widget()
                    if w is not None:
                        w.hide()
                        w.setParent(None)
                        w.deleteLater()
                layout.deleteLater()
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        # 清掉已失效的编辑器引用
        self._editors = {k: v for k, v in self._editors.items()
                         if k in {f[0] for f in self.BASE_FIELDS}}

        proto = get_protocol(str(self._current_protocol()))
        if proto is None:
            self.params_label.setText("协议参数（插件未注册，请用 JSON 编辑）")
            return
        self.params_label.setText(f"协议参数 · {proto.label}")
        for param in proto.params:
            if param.advanced:
                continue
            self.param_box.addLayout(self._make_row(param.key, param.label, param.kind))

    def _current_protocol(self) -> str:
        w = self._editors.get("protocol")
        if isinstance(w, QComboBox):
            return str(w.currentData() or "")
        return str(self.profile.get("protocol", ""))

    def _on_protocol(self):
        proto = get_protocol(self._current_protocol())
        if proto is None:
            return
        for key, value in proto.defaults().items():
            self.profile.setdefault(key, value)
        self.profile["protocol"] = proto.id
        if not self.profile.get("usage_pages"):
            self.profile["usage_pages"] = list(proto.usage_pages)
        self._build_params()

    # ------------------------------------------------------------------ #
    def _format(self, key: str, kind: str) -> str:
        value = self.profile.get(key, "")
        if kind == "hex":
            try:
                number = int(value)
                return f"{number:#04x}" if number <= 0xFF else f"{number:#06x}"
            except Exception:                      # noqa: BLE001
                return str(value)
        if kind == "intlist":
            return ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
        return str(value)

    def _toggle_json(self):
        visible = not self.json_box.isVisible()
        self.json_box.setVisible(visible)
        self.btn_json.setText("收起高级参数" if visible else "高级参数 (JSON)")
        self.btn_json._glyph = theme.ICON["up"] if visible else theme.ICON["down"]
        self.btn_json.update()
        self.adjustSize()
        if visible:
            self._collect()
            self.json_box.setPlainText(json.dumps(self.profile, ensure_ascii=False, indent=2))

    def _collect(self):
        for key, _label, kind in self.BASE_FIELDS:
            w = self._editors[key]
            if kind == "choice":
                self.profile[key] = w.currentData()
            elif kind == "int":
                try:
                    self.profile[key] = int(str(w.text()).strip())
                except ValueError:
                    pass
            elif kind == "intlist":
                parts = [p for p in str(w.text()).replace("，", ",").split(",") if p.strip()]
                values = []
                for part in parts:
                    try:
                        values.append(int(part.strip(), 0))
                    except ValueError:
                        pass
                if values:
                    self.profile[key] = values
            else:
                self.profile[key] = w.text().strip()

        proto = get_protocol(str(self.profile.get("protocol", "")))
        if proto is None:
            return
        for param in proto.params:
            w = self._editors.get(param.key)
            if w is None:
                continue
            if param.kind == "bool":
                self.profile[param.key] = bool(w.currentData())
            elif param.kind in ("int", "hex"):
                text = str(w.text()).strip()
                if not text:
                    continue
                try:
                    self.profile[param.key] = int(text, 0) if param.kind == "hex" else int(text)
                except ValueError:
                    pass
            elif param.kind == "intlist":
                parts = [p for p in str(w.text()).replace("，", ",").split(",") if p.strip()]
                try:
                    self.profile[param.key] = [int(p, 0) for p in parts]
                except ValueError:
                    pass
            else:
                self.profile[param.key] = w.text().strip()

    def _accept(self):
        if self.json_box.isVisible():
            try:
                data = json.loads(self.json_box.toPlainText())
            except Exception as exc:               # noqa: BLE001
                self.json_box.setStyleSheet(INPUT_QSS + "border: 1px solid #C42B1C;")
                self.json_box.setToolTip(f"JSON 解析失败：{exc}")
                return
            if not isinstance(data, dict):
                return
            self.profile = data
            self.accept()
            return

        self._collect()
        self.accept()

    def result_profile(self) -> dict:
        return self.profile
