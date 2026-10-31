"""把当前工作区整理成一份可归档、可分发的产物包。

产物结构（release/StrelitziaHIDBattery_v<版本>_<日期>/）：

    src/         源码（main.py、app/、tools/、requirements.txt、启动.bat）
    docs/        README、CHANGELOG、归档说明
    config/      接口配置、设备图片映射、商城索引
    assets/      设备图片
    protocols/   用户插件目录模板
    bin/         打包好的 EXE（若已构建）
    MANIFEST.md  文件清单（大小 + SHA256）
    manifest.json 同上的机器可读版本

同时产出两个 zip：完整包（含 EXE）与纯源码包。

用法：python tools/make_release.py [--no-zip]
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.branding import APP_NAME, EXE_STEM, VERSION  # noqa: E402

RELEASE_ROOT = ROOT / "release"

SRC_FILES = ["main.py", "requirements.txt", "启动.bat"]
SRC_DIRS = ["app", "tools"]
DOCS = ["README.md", "CHANGELOG.md"]
CONFIG = ["profiles.json", "device_images.json", "mall_index.json"]
SKIP_DIRS = {"__pycache__", ".git", "build", "dist", "release", "data", ".idea", ".vscode"}
SKIP_SUFFIX = {".pyc", ".pyo", ".db", ".log", ".spec"}


def _skip(path: Path) -> bool:
    if path.suffix in SKIP_SUFFIX:
        return True
    return any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)


def _copy_tree(src: Path, dst: Path) -> list[Path]:
    """按白名单/黑名单复制一个目录，返回实际落盘的文件列表。"""
    out: list[Path] = []
    for item in sorted(src.rglob("*")):
        if not item.is_file() or _skip(item):
            continue
        target = dst / item.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        out.append(target)
    return out


def _sha256(path: Path, limit: int = 12) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:limit]


def human(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.1f} MB"


def build() -> Path:
    stamp = datetime.now().strftime("%Y%m%d")
    name = f"{EXE_STEM}_v{VERSION}_{stamp}"
    out = RELEASE_ROOT / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    written: list[Path] = []

    # 源码
    for f in SRC_FILES:
        src = ROOT / f
        if src.exists():
            dst = out / "src" / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            written.append(dst)
    for d in SRC_DIRS:
        written += _copy_tree(ROOT / d, out / "src")

    # 文档
    for f in DOCS:
        src = ROOT / f
        if src.exists():
            dst = out / "docs" / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            written.append(dst)

    # 配置与资源
    for f in CONFIG:
        src = ROOT / "config" / f
        if src.exists():
            dst = out / "config" / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            written.append(dst)
    if (ROOT / "assets").exists():
        written += _copy_tree(ROOT / "assets", out)
    if (ROOT / "protocols" / "README.txt").exists():
        dst = out / "protocols" / "README.txt"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "protocols" / "README.txt", dst)
        written.append(dst)

    # 构建产物
    exe = ROOT / "dist" / f"{EXE_STEM}.exe"
    if exe.exists():
        dst = out / "bin" / exe.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe, dst)
        written.append(dst)

    _write_manifest(out, written, name)
    return out


def _write_manifest(out: Path, files: list[Path], name: str) -> None:
    rows = []
    for f in sorted(files):
        rel = f.relative_to(out).as_posix()
        rows.append({"path": rel, "bytes": f.stat().st_size,
                     "size": human(f.stat().st_size), "sha256": _sha256(f)})

    total = sum(r["bytes"] for r in rows)
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["path"].split("/")[0], []).append(r)

    lines = [
        f"# {APP_NAME} v{VERSION} · 产物清单",
        "",
        f"- 归档时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 包名：`{name}`",
        f"- 文件总数：{len(rows)}",
        f"- 总体积：{human(total)}",
        f"- 源码行数：{_py_lines(out)} 行（Python）",
        "",
        "| 目录 | 文件数 | 体积 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    notes = {
        "src": "源码：main.py、app/（UI/协议/扫描/历史）、tools/（自检、冒烟、诊断）",
        "docs": "文档：README、变更记录",
        "config": "配置：接口插件配置、设备图片映射、商城索引",
        "assets": "资源：设备图片",
        "protocols": "用户插件目录模板（放 .py 或接入包 .json）",
        "bin": "构建产物：免安装 EXE",
    }
    for key in sorted(groups):
        g = groups[key]
        lines.append(f"| `{key}/` | {len(g)} | {human(sum(x['bytes'] for x in g))} | "
                     f"{notes.get(key, '')} |")
    lines += ["", "## 文件明细", "", "| 文件 | 大小 | SHA256（前 12 位） |",
              "| --- | --- | --- |"]
    for r in rows:
        lines.append(f"| `{r['path']}` | {r['size']} | `{r['sha256']}` |")
    (out / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps({"app": APP_NAME, "version": VERSION, "package": name,
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "total_bytes": total, "files": rows},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _py_lines(out: Path) -> int:
    return sum(len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
               for p in out.rglob("*.py"))


def zip_dir(src: Path, zip_path: Path, skip_bin: bool = False) -> Path:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in sorted(src.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(src.parent)
            if skip_bin and rel.parts[:2] == (src.name, "bin"):
                continue
            zf.write(f, rel.as_posix())
    return zip_path


def main() -> int:
    out = build()
    print(f"[release] {out}")
    if "--no-zip" not in sys.argv:
        full = RELEASE_ROOT / f"{out.name}.zip"
        src = RELEASE_ROOT / f"{out.name}_src.zip"
        zip_dir(out, full)
        zip_dir(out, src, skip_bin=True)
        print(f"[zip] {full.name}  {human(full.stat().st_size)}")
        print(f"[zip] {src.name}  {human(src.stat().st_size)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
