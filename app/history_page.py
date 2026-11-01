"""电量统计页：设备选择 + 24 小时 / 7 天 / 30 天图表 + 预测 + 采样间隔 + 清除记录。

图表固定 3:2 宽高比（宽度随窗口变化，高度按比例反推），
页面放进滚动区，窗口变小时自动出现滚动条而不压缩图表比例。
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QScrollArea,
                               QVBoxLayout, QWidget)

from . import history, theme
from .chart import LineChart
from .profiles import save_config
from .widgets import DragArea, FlatButton, IconButton, Segmented, Surface

RANGE_LABELS = [("24h", "24 小时"), ("7d", "7 天"), ("30d", "30 天")]
RECORD_OPTIONS = (("5 分钟", 300), ("10 分钟", 600),
                  ("30 分钟", 1800), ("1 小时", 3600))


def _duration(hours: float) -> str:
    if hours >= 100:
        return "100 小时以上"
    total = int(round(hours * 60))
    hh, mm = divmod(total, 60)
    if hh <= 0:
        return f"{max(mm, 1)} 分钟"
    if mm == 0:
        return f"{hh} 小时"
    return f"{hh} 小时 {mm} 分"


class HistoryPage(QWidget):
    back_requested = Signal()
    config_changed = Signal()

    def __init__(self, embedded: bool = False, config: dict | None = None, parent=None):
        super().__init__(parent)
        self.config = config if config is not None else {}
        self._uid = ""
        self._range = "24h"
        self._confirm_uid = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0 if embedded else 16, 0 if embedded else 12,
                                0 if embedded else 16, 0 if embedded else 14)
        root.setSpacing(0)

        head = DragArea() if not embedded else QWidget()
        head_lay = QHBoxLayout(head)
        head_lay.setContentsMargins(0, 0, 0, 0)
        head_lay.setSpacing(4)
        self.btn_back = IconButton(theme.ICON["back"], size=28, icon_size=9, tooltip="返回")
        self.btn_back.clicked.connect(lambda *_: self.back_requested.emit())
        head_lay.addWidget(self.btn_back)
        if embedded:
            self.btn_back.hide()
        title = QLabel("电量统计")
        title.setFont(theme.ui_font(13, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        head_lay.addWidget(title)
        head_lay.addStretch(1)
        self.btn_refresh = IconButton(theme.ICON["refresh"], size=28, icon_size=9, tooltip="刷新图表")
        self.btn_refresh.clicked.connect(lambda *_: self.refresh())
        head_lay.addWidget(self.btn_refresh)
        root.addWidget(head)
        root.addSpacing(10)

        # ---------------- 可滚动内容 ---------------- #
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
        self.body.setContentsMargins(0, 0, 8, 0)
        self.body.setSpacing(0)
        self.scroll.setWidget(self.host)
        root.addWidget(self.scroll, 1)

        self.combo = QComboBox()
        self.combo.setStyleSheet(theme.INPUT_QSS)
        self.combo.setFont(theme.ui_font(9))
        self.combo.currentIndexChanged.connect(self._on_device_changed)
        self.body.addWidget(self.combo)
        self.body.addSpacing(8)

        self.seg = Segmented(RANGE_LABELS)
        self.seg.setFixedHeight(32)
        self.seg.changed.connect(self._on_range_changed)
        self.body.addWidget(self.seg)
        self.body.addSpacing(8)

        # 采样设置（原「设置 → 电量统计」）放在图表上方，进页即可见
        rec = QHBoxLayout()
        rec.setContentsMargins(2, 0, 2, 0)
        rec.setSpacing(6)
        rec_label = QLabel("记录间隔")
        rec_label.setFont(theme.ui_font(8))
        rec_label.setStyleSheet(f"color: {theme.C.TEXT_SECONDARY.name()};")
        self.record = QComboBox()
        self.record.setStyleSheet(theme.INPUT_QSS)
        self.record.setFont(theme.ui_font(8))
        self.record.setFixedWidth(96)
        for label, sec in RECORD_OPTIONS:
            self.record.addItem(label, sec)
        self.record.currentIndexChanged.connect(self._on_record_interval)
        rec_hint = QLabel(f"按此间隔采样，保留 {history.RETENTION_DAYS} 天")
        rec_hint.setFont(theme.ui_font(7))
        rec_hint.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        rec.addWidget(rec_label)
        rec.addWidget(self.record)
        rec.addStretch(1)
        rec.addWidget(rec_hint)
        self.body.addLayout(rec)
        self.body.addSpacing(8)

        self.chart = LineChart(ratio=(3, 2))       # 3:2，宽度变高度跟着变
        self.body.addWidget(self.chart)
        self.body.addSpacing(6)

        self.stats = QLabel("—")
        self.stats.setFont(theme.ui_font(8))
        self.stats.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        self.body.addWidget(self.stats)
        self.body.addSpacing(8)

        self.card = Surface(radius=10, fill=QColor(0, 0, 0, 10),
                            border=QColor(0, 0, 0, 16))
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(12, 9, 12, 9)
        card_lay.setSpacing(2)
        self.predict_title = QLabel("—")
        self.predict_title.setFont(theme.ui_font(10, QFont.Weight.DemiBold))
        self.predict_title.setStyleSheet(f"color: {theme.C.TEXT.name()};")
        self.predict_sub = QLabel("")
        self.predict_sub.setWordWrap(True)
        self.predict_sub.setFont(theme.ui_font(7))
        self.predict_sub.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        card_lay.addWidget(self.predict_title)
        card_lay.addWidget(self.predict_sub)
        self.body.addWidget(self.card)
        self.body.addSpacing(10)

        self.empty = QLabel("还没有历史记录。\n程序会按下方「记录间隔」自动采样，"
                            "积累几次后这里会出现曲线和预测。")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setFont(theme.ui_font(8))
        self.empty.setStyleSheet(f"color: {theme.C.TEXT_TERTIARY.name()};")
        self.empty.hide()
        self.body.addWidget(self.empty)

        self.body.addStretch(1)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 6, 0, 0)
        foot.setSpacing(6)
        self.btn_clear = FlatButton("清除该设备记录", glyph=theme.ICON["delete"])
        self.btn_clear.clicked.connect(self._clear_device)
        self.btn_clear_all = FlatButton("全部清除")
        self.btn_clear_all.clicked.connect(self._clear_all)
        foot.addWidget(self.btn_clear)
        foot.addWidget(self.btn_clear_all)
        foot.addStretch(1)
        root.addLayout(foot)

        self._confirm_timer = QTimer(self)
        self._confirm_timer.setSingleShot(True)
        self._confirm_timer.setInterval(4000)
        self._confirm_timer.timeout.connect(self._reset_confirm)

        self.reload()

    # ------------------------------------------------------------------ #
    def reload(self) -> None:
        """打开页面时重建设备列表并重绘。"""
        self._reset_confirm()
        self._sync_record_interval()
        devices = history.devices()
        self.combo.blockSignals(True)
        self.combo.clear()
        for dev in devices:
            self.combo.addItem(dev["name"], dev["uid"])
        self.combo.blockSignals(False)

        if not devices:
            self._uid = ""
            self._show_empty(True)
            return

        idx = 0
        for i, dev in enumerate(devices):
            if dev["uid"] == self._uid:
                idx = i
                break
        self.combo.setCurrentIndex(idx)
        self._uid = self.combo.itemData(idx) or devices[0]["uid"]
        self._show_empty(False)
        self.refresh()

    def _sync_record_interval(self) -> None:
        try:
            current = int(self.config.get("record_interval", 300))
        except (TypeError, ValueError):
            current = 300
        idx = self.record.findData(current)
        self.record.blockSignals(True)
        self.record.setCurrentIndex(idx if idx >= 0 else 0)
        self.record.blockSignals(False)

    def refresh(self) -> None:
        """按当前设备与区间重画（主程序每次采样后调用）。"""
        uid = self._uid
        if not uid:
            self._show_empty(True)
            return
        span, _bucket, fmt = history.RANGES[self._range]
        now = int(time.time())
        pts = history.points(uid, self._range, now)
        self.chart.set_data(pts, span, fmt, now=now)

        st = history.stats(uid, self._range, now)
        if st["count"]:
            span_text = dict(RANGE_LABELS)[self._range]
            self.stats.setText(
                f"{span_text}：最低 {st['min']}% · 最高 {st['max']}% · "
                f"平均 {st['avg']}% · {st['count']} 次采样")
        else:
            self.stats.setText("该区间还没有采样")
        self._update_prediction(uid, now)

    def _update_prediction(self, uid: str, now: int) -> None:
        info = history.predict(uid, now)
        if info.get("ready"):
            self.predict_title.setText(f"预计还能用 {_duration(info['hours'])}")
            self.predict_sub.setText(
                f"当前 {info['percent']}% · 近 {info['window_h']} 小时平均掉电 "
                f"{info['rate']} %/小时 · 基于 {info['samples']} 个放电样本")
        else:
            self.predict_title.setText(str(info.get("reason") or "暂无预测"))
            if info.get("percent") is not None:
                self.predict_sub.setText(
                    f"当前 {info['percent']}% · 继续积累放电记录后会自动给出估算")
            else:
                self.predict_sub.setText("需要至少 3 次放电采样，且间隔覆盖半小时以上")

    def _show_empty(self, empty: bool) -> None:
        for w in (self.combo, self.seg, self.chart, self.stats, self.card):
            w.setVisible(not empty)
        self.btn_clear.setEnabled(not empty)
        self.btn_clear_all.setEnabled(bool(history.devices()))
        self.empty.setVisible(empty)

    # ------------------------------------------------------------------ #
    def _on_device_changed(self, index: int) -> None:
        uid = self.combo.itemData(index)
        if uid:
            self._uid = str(uid)
            self._reset_confirm()
            self.refresh()

    def _on_range_changed(self, key: str) -> None:
        self._range = key
        self.refresh()

    def _on_record_interval(self, _index: int) -> None:
        try:
            value = int(self.record.currentData())
        except (TypeError, ValueError):
            return
        self.config["record_interval"] = value
        try:
            save_config(self.config)
        except Exception:                          # noqa: BLE001
            pass
        self.config_changed.emit()

    def _clear_device(self) -> None:
        if not self._uid:
            return
        if self._confirm_uid != self._uid:
            self._confirm_uid = self._uid
            self.btn_clear.setText("再点一次确认清除")
            self._confirm_timer.start()
            return
        history.clear_device(self._uid)
        self._reset_confirm()
        self.reload()

    def _clear_all(self) -> None:
        if self._confirm_uid != "*":
            self._confirm_uid = "*"
            self.btn_clear_all.setText("再点一次确认")
            self._confirm_timer.start()
            return
        history.clear_all()
        self._reset_confirm()
        self._uid = ""
        self.reload()

    def _reset_confirm(self) -> None:
        self._confirm_uid = ""
        self.btn_clear.setText("清除该设备记录")
        self.btn_clear_all.setText("全部清除")
        self.btn_clear.setEnabled(bool(self._uid))
        self.btn_clear_all.setEnabled(bool(history.devices()))

    # ------------------------------------------------------------------ #
    def preferred_height(self) -> int:
        """页面内容高度（不含面板外框留白，由 Flyout._fit 叠加）。"""
        lay = self.layout()
        if lay is not None:
            lay.activate()
        need = lay.sizeHint().height() if lay is not None else 0
        return max(need, 430)
