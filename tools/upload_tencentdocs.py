"""把归档文档上传到腾讯文档（智能文档），并归入指定文件夹。

注意：重复运行会重复创建文档（接口不按标题去重）。
"""
import json
import sys
from pathlib import Path

SKILL = Path(r"C:\Users\zhan_\.workbuddy\plugins\cache\workbuddy-builtin\tencent-docs-plugin"
             r"\5.9.3-wb.42398134.gd4692421.h480e8d1fee0f\skills\tencent-docs")
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tencentdocs  # noqa: E402

from app.branding import VERSION  # noqa: E402

REL = Path(r"E:\Program Files\Workbuddy Files\个人vibe\HIDBattery\release"
           rf"\StrelitziaHIDBattery_v{VERSION}_20261101")
FOLDER = "UTJXdoiglGfE"

ITEMS = [
    (f"Strelitzia HID Battery v{VERSION} · 使用说明", REL / "docs" / "README.md"),
    ("Strelitzia HID Battery · 变更记录", REL / "docs" / "CHANGELOG.md"),
    (f"v{VERSION} · 产物归档清单", REL / "MANIFEST.md"),
]


def call(tool: str, args: dict) -> dict:
    """tencentdocs.call_tool 返回 (jsonrpc 报文, 附加信息)，这里只取结构化结果。"""
    r, _ = tencentdocs.call_tool("tencent-docs", tool, args)
    return (r.get("result") or {}).get("structuredContent") or {}


def main():
    results = []
    for title, path in ITEMS:
        text = path.read_text(encoding="utf-8")
        info = call("create_smartcanvas_by_mdx",
                    {"title": title, "mdx": text, "content_format": "markdown"})
        print(f"[create] {title} -> {info.get('file_id')} {info.get('url', '')} err={info.get('error')}")
        if info.get("file_id"):
            mv = call("manage.move_file", {"file_id": info["file_id"],
                                           "target_folder_id": FOLDER})
            print(f"         move -> err={mv.get('error')}")
        results.append({"title": title, "source": path.name, **info})
    Path(REL.parent / "upload_tencentdocs.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
