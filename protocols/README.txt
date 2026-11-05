把 AI 生成的协议插件放这里，程序启动时会自动加载（文件名随意，建议与插件 id 对齐）。

推荐做法：让 AI 输出一个「接入包」JSON，然后在程序里点
「接口设置 → 导入接入包」选择该文件 —— 插件与接口配置会一起装好，不用手动改任何东西。

接入包格式：
{
  "kind": "hid-battery-hub-profile",
  "version": 1,
  "protocol": { "filename": "vendor_protocol.py", "code_lines": ["from __future__ import annotations", "..."] },
  "profile":  { "id": "vendor-protocol", "name": "厂商 · 协议", "vendor_id": 14391,
                "usage_pages": [65280], "protocol": "vendor-protocol", "enabled": true, "models": {} }
}

也可以只放一个 .py 插件文件（必须带 @register 与唯一的 id）。
