"""电量历史：SQLite 采样存储 + 区间聚合 + 剩余可用时长预测。

设计要点：
  * 每台设备按 `interval` 节流写入（同一设备两条记录之间至少间隔 interval·0.9），
    采样由主程序的扫描回调驱动，不额外开 USB 通道。
  * 时间统一存 Unix 秒（本地时区无关）；查询时按桶（bucket）取平均，避免长区间点太多。
  * 预测只用「放电中」的样本做最小二乘，充电样本会把斜率拉正，必须排除。
"""
from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from .paths import DATA_SUBDIR, HISTORY_DB

# 可选的记录间隔（秒）：5 / 10 / 30 / 60 分钟
INTERVALS: Tuple[int, ...] = (300, 600, 1800, 3600)

# 图表区间：key → (跨度秒, 聚合桶秒, 轴标签格式)
RANGES: Dict[str, Tuple[int, int, str]] = {
    "24h": (24 * 3600, 900, "%H:%M"),
    "7d": (7 * 86400, 3 * 3600, "%m/%d"),
    "30d": (30 * 86400, 12 * 3600, "%m/%d"),
}

RETENTION_DAYS = 90

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    uid      TEXT    NOT NULL,
    name     TEXT    NOT NULL DEFAULT '',
    percent  INTEGER NOT NULL,
    charging INTEGER NOT NULL DEFAULT 0,
    ts       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_uid_ts ON samples(uid, ts);
CREATE TABLE IF NOT EXISTS devices (
    uid          TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    vendor       TEXT NOT NULL DEFAULT '',
    first_ts     INTEGER NOT NULL DEFAULT 0,
    last_ts      INTEGER NOT NULL DEFAULT 0,
    last_percent INTEGER
);
"""


@contextmanager
def _db():
    os.makedirs(DATA_SUBDIR, exist_ok=True)
    conn = sqlite3.connect(HISTORY_DB, timeout=5.0)
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# 写入
# --------------------------------------------------------------------------- #
def record(devices: List[Dict[str, Any]], interval: int = 300,
           now: Optional[int] = None) -> int:
    """按间隔把本轮扫描结果落库；返回实际写入的样本数。"""
    moment = int(now if now is not None else time.time())
    interval = max(60, int(interval))
    saved = 0
    with _db() as conn:
        for dev in devices:
            pct = dev.get("percent")
            if pct is None:
                continue
            uid = str(dev.get("uid") or f"{dev.get('vendor_id')}:{dev.get('product_id')}")
            name = str(dev.get("name") or dev.get("model") or "设备")[:64]
            row = conn.execute("SELECT last_ts FROM devices WHERE uid=?", (uid,)).fetchone()
            if row and moment - int(row[0]) < interval * 0.9:
                continue
            conn.execute(
                "INSERT INTO samples(uid, name, percent, charging, ts) VALUES(?,?,?,?,?)",
                (uid, name, int(pct), 1 if dev.get("charging") else 0, moment))
            conn.execute(
                "INSERT INTO devices(uid, name, vendor, first_ts, last_ts, last_percent) "
                "VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(uid) DO UPDATE SET name=excluded.name, last_ts=excluded.last_ts, "
                "last_percent=excluded.last_percent",
                (uid, name, str(dev.get("vendor") or ""), moment, moment, int(pct)))
            saved += 1
    return saved


def prune(days: int = RETENTION_DAYS, now: Optional[int] = None) -> int:
    """删除超过保留期的样本，避免库无限增长。"""
    cutoff = int((now if now is not None else time.time()) - days * 86400)
    with _db() as conn:
        cur = conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
        return cur.rowcount or 0


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def devices() -> List[Dict[str, Any]]:
    """有历史记录的设备（含已拔掉的），按最近记录时间倒序。"""
    with _db() as conn:
        rows = conn.execute(
            "SELECT d.uid, d.name, d.vendor, d.last_ts, d.last_percent, "
            "       (SELECT COUNT(*) FROM samples s WHERE s.uid = d.uid) "
            "FROM devices d ORDER BY d.last_ts DESC").fetchall()
    return [{"uid": r[0], "name": r[1] or "设备", "vendor": r[2] or "",
             "last_ts": int(r[3]), "last_percent": r[4], "samples": int(r[5])}
            for r in rows]


def has_data(uid: str) -> bool:
    with _db() as conn:
        return conn.execute("SELECT 1 FROM samples WHERE uid=? LIMIT 1", (uid,)).fetchone() is not None


def points(uid: str, range_key: str = "24h", now: Optional[int] = None
           ) -> List[Tuple[int, float]]:
    """返回 [(时间戳, 平均电量)]，按 range 对应的桶聚合。"""
    span, bucket, _ = RANGES.get(range_key, RANGES["24h"])
    end = int(now if now is not None else time.time())
    start = end - span
    with _db() as conn:
        rows = conn.execute(
            "SELECT (ts / ?) * ? AS t, AVG(percent) FROM samples "
            "WHERE uid=? AND ts>=? GROUP BY t ORDER BY t",
            (bucket, bucket, uid, start)).fetchall()
    return [(int(r[0]), float(r[1])) for r in rows]


def stats(uid: str, range_key: str = "24h", now: Optional[int] = None) -> Dict[str, Any]:
    span, _, _ = RANGES.get(range_key, RANGES["24h"])
    end = int(now if now is not None else time.time())
    start = end - span
    with _db() as conn:
        row = conn.execute(
            "SELECT MIN(percent), MAX(percent), AVG(percent), COUNT(*), MAX(ts) "
            "FROM samples WHERE uid=? AND ts>=?", (uid, start)).fetchone()
    return {"min": row[0], "max": row[1], "avg": round(row[2], 1) if row[2] is not None else None,
            "count": int(row[3] or 0), "last_ts": int(row[4]) if row[4] else None}


def _slope(pairs: List[Tuple[int, int]]) -> Optional[float]:
    """最小二乘斜率（百分点 / 小时），样本不足返回 None。"""
    if len(pairs) < 3:
        return None
    t0 = pairs[0][0]
    xs = [(p[0] - t0) / 3600.0 for p in pairs]
    ys = [float(p[1]) for p in pairs]
    if xs[-1] - xs[0] < 0.4:                      # 跨度太小，斜率没意义
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def predict(uid: str, now: Optional[int] = None) -> Dict[str, Any]:
    """用近 24 小时（不够则用全部）的放电样本估算还能用多久。"""
    end = int(now if now is not None else time.time())
    with _db() as conn:
        rows = conn.execute(
            "SELECT ts, percent, charging FROM samples WHERE uid=? AND charging=0 "
            "AND ts>=? ORDER BY ts", (uid, end - 24 * 3600)).fetchall()
        if len(rows) < 3:
            rows = conn.execute(
                "SELECT ts, percent, charging FROM samples WHERE uid=? AND charging=0 "
                "ORDER BY ts DESC LIMIT 400", (uid,)).fetchall()[::-1]
        last = conn.execute(
            "SELECT percent, charging, ts FROM samples WHERE uid=? ORDER BY ts DESC LIMIT 1",
            (uid,)).fetchone()

    if last is None:
        return {"ready": False, "reason": "还没有记录"}
    percent, charging, last_ts = int(last[0]), bool(last[1]), int(last[2])
    if charging:
        return {"ready": False, "reason": "正在充电", "percent": percent}

    pairs = [(int(r[0]), int(r[1])) for r in rows]
    slope = _slope(pairs)
    if slope is None:
        return {"ready": False, "reason": "数据不足（至少需要 3 次放电采样）", "percent": percent}

    drain = -slope                                  # %/小时，正数表示在掉电
    span_h = (pairs[-1][0] - pairs[0][0]) / 3600.0
    if drain <= 0.2:
        return {"ready": False, "reason": "近 24 小时电量基本没变化",
                "percent": percent, "rate": round(drain, 2)}
    hours = percent / drain
    return {
        "ready": True,
        "hours": min(hours, 999.0),
        "rate": round(drain, 2),
        "percent": percent,
        "window_h": round(span_h, 1),
        "samples": len(pairs),
        "updated": last_ts,
    }


# --------------------------------------------------------------------------- #
# 清除
# --------------------------------------------------------------------------- #
def clear_device(uid: str) -> int:
    with _db() as conn:
        cur = conn.execute("DELETE FROM samples WHERE uid=?", (uid,))
        conn.execute("DELETE FROM devices WHERE uid=?", (uid,))
        return cur.rowcount or 0


def clear_all() -> int:
    with _db() as conn:
        cur = conn.execute("DELETE FROM samples")
        conn.execute("DELETE FROM devices")
        return cur.rowcount or 0
