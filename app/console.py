"""主窗口：左侧导航三个标签页——通用设置 / 电量统计 / 接口设置。

托盘弹出面板只负责「看一眼电量」，需要操作时点齿轮/图表打开这个窗口。
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import branding, theme
from .history_page import HistoryPage
from .icons import app_icon
from .settings_page import GeneralSettingsPage, InterfaceSettingsPage
from .widgets import FlatButton

NAV = [
    ("general", "通用设置", "settings"),
    ("stats", "电量统计", "chart"),
    ("iface", "接口设置", "device"),
]


class NavItem(QAbstractButton):
    """左侧导航项：图标 + 文字，选中时左侧一条强调色指示条。"""

    def __init__(self, label: str, glyph: str, parent=None):
        super().__init__(parent)
        self.setText(label)
        self._glyph = glyph
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(theme.ui_font(10))
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedHeight(40)

    def enterEvent(self, event):                   # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):                   # noqa: N802
        self.update()
        super().leaveEvent(event)

    def sizeHint(self):                            # noqa: N802
        return QSize(184, 40)

    def paintEvent(self, event):                   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(8, 2, -8, -2)
        if self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 20))
            p.drawRoundedRect(r, 6, 6)
            p.setBrush(theme.C.ACCENT)
            p.drawRoundedRect(QRectF(2, r.top() + 9, 3, r.height() - 18), 1.5, 1.5)
        elif self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 10))
            p.drawRoundedRect(r, 6, 6)

        color = theme.C.TEXT if self.isChecked() else theme.C.TEXT_SECONDARY
        p.setPen(QPen(color))
        p.setFont(theme.icon_font(11))
        p.drawText(QRectF(r.left() + 12, r.top(), 22, r.height()),
                   Qt.AlignmentFlag.AlignCenter, theme.ICON.get(self._glyph, ""))
        p.setFont(self.font())
        p.drawText(QRectF(r.left() + 40, r.top(), r.width() - 46, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())


class ConsoleWindow(QWidget):
    """独立设置窗口（普通带边框窗口，可最小化 / 缩放）。"""

    config_changed = Signal()
    icons_changed = Signal()
    refresh_requested = Signal()
    opened = Signal()

    def __init__(self, config: Dict[str, Any],
                 devices_provider: Callable[[], list],
                 parent=None):
        super().__init__(parent)
        self.config = config
        self._devices_provider = devices_provider
        self._current = "general"

        self.setWindowTitle(branding.APP_NAME)
        self.setWindowIcon(QIcon(app_icon(False)))
        self.resize(940, 820)                      # 3:2 图表需要更充裕的纵向空间
        self.setMinimumSize(800, 560)
        self.setAcceptDrops(True)
        self.setStyleSheet(f"QWidget#consoleRoot{{background:{theme.C.WINDOW.name()};}}")

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------------- 左侧导航 ---------------- #
        nav = QWidget()
        nav.setFixedWidth(208)
        nav.setStyleSheet("background: #F3F3F3; border-right: 1px solid rgba(0,0,0,18);")
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(12, 18, 12, 16)
        nav_lay.setSpacing(2)

        title = QLabel(branding.APP_NAME)
        title.setFont(theme.ui_font(12, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        title.setWordWrap(True)
        nav_lay.addWidget(title)
        sub = QLabel(f"{branding.TAGLINE} · v{branding.VERSION}")
        sub.setFont(theme.ui_font(7))
        sub.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        nav_lay.addWidget(sub)

        self.nav_status = QLabel("—")
        self.nav_status.setFont(theme.ui_font(7))
        self.nav_status.setWordWrap(True)
        self.nav_status.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()}; padding-top:4px;")
        nav_lay.addWidget(self.nav_status)
        nav_lay.addSpacing(12)

        self._nav: Dict[str, NavItem] = {}
        for key, label, glyph in NAV:
            item = NavItem(label, glyph)
            item.clicked.connect(lambda _checked=False, k=key: self.open_page(k))
            self._nav[key] = item
            nav_lay.addWidget(item)

        nav_lay.addStretch(1)
        self.btn_refresh = FlatButton("立即刷新", glyph=theme.ICON["refresh"], spin=True)
        self.btn_refresh.clicked.connect(lambda *_: self.refresh_requested.emit())
        nav_lay.addWidget(self.btn_refresh)
        root.addWidget(nav)

        # ---------------- 右侧内容 ---------------- #
        content = QWidget()
        content.setObjectName("consoleRoot")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(26, 20, 26, 20)
        content_lay.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent;")
        content_lay.addWidget(self.stack)

        self.general_page = GeneralSettingsPage(config, embedded=True)
        self.history_page = HistoryPage(embedded=True, config=config)
        self.iface_page = InterfaceSettingsPage(config, devices_provider, embedded=True)
        for page in (self.general_page, self.history_page, self.iface_page):
            self.stack.addWidget(page)

        self.general_page.config_changed.connect(self._on_config_changed)
        self.iface_page.config_changed.connect(self._on_config_changed)
        self.history_page.config_changed.connect(self._on_config_changed)
        self.iface_page.icons_changed.connect(self.icons_changed)
        self.iface_page.prompt_requested.connect(self.open_prompt)

        root.addWidget(content, 1)
        self._pages = {"general": self.general_page,
                       "stats": self.history_page,
                       "iface": self.iface_page}
        self.open_page("general", refresh=False)

    def _on_config_changed(self):
        """任一页改了配置：三页都重读一次（间隔 / 自启 / 插件列表可能互相影响）。"""
        self.general_page.reload(self.config)
        self.history_page.reload()
        self.iface_page.reload(self.config)
        self.config_changed.emit()

    # ------------------------------------------------------------------ #
    def set_status(self, text: str):
        self.nav_status.setText(text)

    def set_reading(self, reading: bool):
        """与悬浮面板同步：读的时候「立即刷新」按钮转圈，读完停。"""
        if not hasattr(self.btn_refresh, "_spin"):
            return
        if reading:
            self.btn_refresh.start_spin()
        else:
            self.btn_refresh.stop_spin()

    def open_page(self, key: str, refresh: bool = True):
        if key == "settings":                      # 兼容旧入口：设置 = 通用设置页
            key = "general"
        page = self._pages.get(key)
        if page is None:
            key, page = "general", self.general_page
        self._current = key
        for name, item in self._nav.items():
            item.setChecked(name == key)
        self.stack.setCurrentWidget(page)
        if refresh:
            self._reload_current()

    def _reload_current(self):
        if self._current == "general":
            self.general_page.reload(self.config)
        elif self._current == "stats":
            self.history_page.reload()
        elif self._current == "iface":
            self.iface_page.reload(self.config)

    def open_prompt(self, device: Dict[str, Any] | None = None):
        from .prompt_page import PromptDialog

        dlg = PromptDialog(self.config, device, self)
        dlg.bundle_imported.connect(self._on_bundle_imported)
        dlg.exec()

    def _on_bundle_imported(self):
        self.general_page.reload(self.config)
        self.history_page.reload()
        self.iface_page.reload(self.config)
        self.config_changed.emit()

    def import_bundle(self, path: str) -> bool:
        ok = self.iface_page.import_bundle(path)
        self.open_page("iface", refresh=False)
        return ok

    # ------------------------------------------------------------------ #
    def showEvent(self, event):                    # noqa: N802
        super().showEvent(event)
        self.general_page.reload(self.config)
        self.history_page.reload()
        self.iface_page.reload(self.config)
        self._reload_current()
        self.opened.emit()

    def dragEnterEvent(self, event):               # noqa: N802
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(u.toLocalFile().lower().endswith((".json", ".py")) for u in urls):
            event.acceptProposedAction()

    def dropEvent(self, event):                    # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".json", ".py")):
                self.import_bundle(path)
                event.acceptProposedAction()
                return
