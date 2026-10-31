# Strelitzia HID Battery

Windows 托盘小程序：读取 2.4G 接收器（HID）后面设备的电量。
托盘图标显示**当前电量最低的设备**，点击托盘图标在通知区域旁弹出 Fluent 风格悬浮面板，
设置 / 统计 / 探测集中在一个独立窗口里。

设备图标**全部由使用者自己上传**：没上传就不显示图标，程序不抓取在线图片，也不绘制设备剪影。

电量按可调间隔（5 / 10 / 30 / 60 分钟）写入本机 SQLite，可看 24 小时 / 7 天 / 30 天曲线，
并按线性回归估算「还能用多久」。

## 运行

```bash
pip install -r requirements.txt
python main.py          # 或双击 启动.bat（无控制台窗口）
```

免安装版：`python tools/build_exe.py` → `dist/StrelitziaHIDBattery.exe`，双击即用。

## 界面：一块悬浮面板 + 一个独立窗口

**① 悬浮面板**（点托盘图标，或托盘菜单「打开面板」）

- 吸附在通知区域一侧（自动识别任务栏在上/下/左/右），**失焦或按 Esc 立即收起**，不占任务栏、不进 Alt-Tab。
- 只做「看一眼电量」：**列出全部已识别设备**（设备图标仅上传后显示）+ 名称 + 连接方式 + 电量 + 最后更新时间；
  副标题是**读取状态 + 汇总**：「正在读取设备…」→「已完成读取 · N 台设备 · 最低 x%」，超过 8 台时列表改为滚动。
- 刷新按钮按下后**图标变成旋转的开口圆环**：「设备清单 + 每台电量」在同一个线程里一次读完，
  读完自动停转并回到普通图标（至少转 0.56 秒，避免一闪而过看不见）。
- 设备列表刷新时窗口高度同步重算（按页面真实 sizeHint 取高，且不超过屏幕可用高度），不会把内容挤出边界。
- **只有一个刷新间隔**（接口设置里的「刷新间隔」）：设备清单的重新枚举与每台设备的电量读取绑定在同一轮里，
  并且下一轮从「上一轮读完」开始计时，扫描慢也不会把定时触发顶掉。单轮超过 15 秒视为超时，
  面板落到「读取超时，稍后自动重试」，不会永远停在「正在读取设备…」。
- **按住标题栏或面板边缘可拖动**，位置会记住；托盘菜单「重置窗口位置」恢复吸附。
- 右上角三个按钮：电量统计、立即刷新、**打开设置窗口**。点设备行 → 生成该设备的接入提示词。

**② 独立窗口**（面板齿轮 / 折线图标 / 托盘菜单，普通带边框窗口，可最小化、可缩放）

左侧导航三页：

| 页面 | 内容 |
| --- | --- |
| 电量统计 | 设备下拉（数据按设备独立存储）、24 小时 / 7 天 / 30 天曲线、剩余可用时长预测、按设备/全部清除 |
| 接口设置 | 通用（刷新间隔＝设备清单＋电量共用 / 记录间隔 / 开机自启）、厂商接口插件、AI 接入包导入、设备图标上传、诊断 |
| 接口探测 | 对每个已启用接口的厂商私有集合发一次命令，打印电量与原始回包 |

窗口里可以直接把 AI 返回的 `.json` 接入包**拖进去导入**。

**托盘图标**：电池按最低电量填充，≤30% 琥珀黄、≤15% 红色（外框一起变红），充电中不告警。
充电时叠加闪电：闪电压在电量填充上的部分用任务栏底色、落在空白区的部分用前景色，
交界沿填充边缘自动形成一圈反色描边——深色 / 浅色任务栏、任意电量比例下都看得清。

## 目录结构

```
main.py                     程序入口（托盘 + 定时刷新 + 后台扫描线程 + 窗口调度）
app/
  branding.py               产品名与版本（改名只改这一处）
  hid_core.py               传输层：枚举 / 打开 / 报告收发 / HidP_GetCaps（不含厂商知识）
  protocols/                ★ 内置协议插件：一种协议一个文件
    base.py                 Protocol / Param / parse_fields
    registry.py             @register + 自动发现 + 旧 id 映射 + 加载用户插件
    mchose_v2.py            迈丛 V2（64 字节 0x4D 帧）
    mchose_classic.py       迈丛经典（Feature + 0xFF 反码）
    flydigi_newxinput.py    飞智 NewXInput（32 字节 5A A5 帧）
  plugin_store.py           ★ 用户插件目录 + AI 接入包导入（EXE 环境的关键）
  scanner.py                枚举聚合 / 读电量 / 绑定图标 / 检测全部已连接设备
  prompt_builder.py         ★ 生成「要求 AI 返回接入包」的标准化提示词
  prompt_page.py            ★ 接入对话框（检测 → 提示词 → 导入）
  console.py                ★ 独立窗口（左侧导航 + 三个页面）
  probe_page.py             ★ 接口探测页
  history.py / history_page.py / chart.py    电量历史、统计页、自绘折线图
  settings_page.py          设置页（通用 / 插件 / 接入包 / 图标 / 诊断）
  icon_store.py             用户上传图标的归一化与本地存储
  autostart.py              开机启动（HKCU Run 读写）
  paths.py                  运行期路径（EXE 旁边 / %LOCALAPPDATA% 兜底）
  profiles.py               配置读写（插件默认值自动补齐）
  ui.py                     ★ 悬浮面板（失焦收起、吸附、拖拽）
  widgets.py / icons.py / theme.py / winapi.py

运行期目录（源码运行在项目根，EXE 运行在 EXE 旁边）
  config/profiles.json      接口配置
  protocols/*.py            用户插件（AI 接入包装进来的，启动自动加载）
  assets/icons/             用户上传的设备图标（<VID>-<型号PID>.png）
  data/history.db           电量历史库（保留 90 天）

tools/
  selftest.py               回归自测（无 GUI）
  hid_probe.py / hid_desc.py / probe_flydigi.py   命令行 HID 排查
  build_exe.py / make_ico.py                      打包
  shot.py / smoke.py                              截图与冒烟
```

## 一、命名

产品名集中在 `app/branding.py`：`APP_NAME = "Strelitzia HID Battery"`。
窗口标题、托盘提示、托盘通知、应用名、EXE 文件名（`StrelitziaHIDBattery.exe`）、
开机启动注册表项名都由它派生，改名只改这一处再重新打包。

## 二、设备图标：只有你自己上传的

- 设置页「设备图标（本机上传）」列出当前检测到的设备：`—` 表示未上传，上传后立即出现在面板里。
- 点 ↑ 上传任意 PNG / JPG（也支持 WebP / BMP / ICO），统一裁到 **≤128px 的 PNG**，
  存成 `assets/icons/<VID>-<型号PID>.png`，**同一型号共用一张**。
- 点垃圾桶清除，图标立刻从面板消失；没上传的设备行内不占位、不画占位图。

## 三、协议模块化

`app/protocols/` 每个文件描述一种协议，注册表自动发现 `@register` 的类；
**新增协议只要加一个文件**，设置页下拉、参数表单、配置默认值全部自动出现：

```python
from app.hid_core import BatteryReading, ProtocolError, write_report, read_until
from app.protocols.base import Param, Protocol
from app.protocols.registry import register


@register
class MyVendor(Protocol):
    id = "vendor-slug"                  # 与文件名一致，写进配置的 protocol 字段
    label = "厂商 · 协议名"
    vendor = "厂商名"
    usage_pages = (0xFF00,)
    params = [
        Param("report_id", "报告 ID", "hex", 0x4D),
        Param("battery_index", "电量字节下标", "int", 12),
    ]

    def query(self, dev, cfg) -> BatteryReading:
        ...
```

- `params` 用 `Param(key, label, kind, default, hint, advanced)` 声明，
  `kind` 支持 `int / hex / intlist / bool / str`；`advanced=True` 只出现在「高级参数 (JSON)」。
- `query()` 只做「写一帧、读一帧、按偏移解析」，失败抛 `ProtocolError`。
- `usage_pages` 声明值得尝试的集合，扫描时按它排序尝试。

**用户插件**放 `protocols/*.py`（EXE 旁边），启动时由 `plugin_store` 逐个 exec 触发注册，
因此**不用重新打包 EXE** 也能加厂商。

## 四、接入新设备：检测 → 提示词 → 导入接入包

1. **检测**：`scanner.list_connected()` 枚举本机所有物理 HID 设备（不只已支持的），
   记录厂商名、VID:PID、序列号、每个集合的 Usage Page / Usage / IN / OUT / FEAT 长度，
   下拉标注「已支持 / 未接入」，可随时重新检测。
2. **生成**：选中设备后 `prompt_builder.build()` 产出提示词（含设备信息、HID 集合清单、
   已观测到的原始回包、要求 AI 给出的结论、插件契约、约束、验收标准）。
3. **导入**：把提示词给任意 AI Agent，它按第 5 节格式返回**一个 JSON 接入包**；
   点「导入接入包」选中（或直接拖到窗口上），程序自动：
   - 把 `protocol.code_lines` 拼成源码写入 `protocols/<filename>`；
   - 立即加载插件、校验 `@register` 与 id；
   - 把 `profile` 合并进 `config/profiles.json`（同 id 覆盖，不重复）；
   - 刷新接口列表并触发一次扫描。

接入包格式（`kind` 固定）：

```json
{
  "kind": "strelitzia-hid-battery-profile",
  "version": 1,
  "protocol": { "filename": "vendor_protocol.py", "code_lines": ["from __future__ import annotations", "..."] },
  "profile": {
    "id": "vendor-protocol", "name": "厂商 · 协议", "vendor_id": 14391,
    "product_ids": [9473], "enabled": true, "usage_pages": [65280],
    "protocol": "vendor-protocol", "models": {}
  }
}
```

- 也支持只导入 `.py` 插件（之后手动「新增接口」），或只导入含 `profile` 的 `.json`。
- 设置页「导出示例接入包」会在 `config/` 下写一份 `example_bundle.json` 供对照。

## 配置速查

`config/profiles.json`

```json
{
  "config_version": 2,
  "refresh_interval": 60,
  "record_interval": 300,
  "profiles": [
    {
      "id": "mchose-v2",
      "name": "迈丛 MCHOSE · V2 协议",
      "vendor_id": 14391,
      "enabled": true,
      "usage_pages": [65281, 65408, 65291],
      "protocol": "mchose-v2",
      "models": {"16422": "A7 V3 Pro", "8229": "G98 V3"}
    }
  ]
}
```

其余字段（`report_id`、`cmd_get_battery`、`battery_index` …）由插件声明默认值，缺省自动补齐。
旧配置里的 `report64 / feature_xor` 会自动映射到 `mchose-v2 / mchose-classic`。

## 已适配设备（迈丛 MCHOSE，VID 0x3837）

| 设备 | 接收器 PID | 型号 PID | 协议 | 通道 |
| --- | --- | --- | --- | --- |
| A7 V3 Pro | 0x1014 | 0x4026 | mchose-v2 | usage 0xFF01 |
| G98 V3 2.4G | 0x1015 | 0x2025 | mchose-v2 | usage 0xFF80 |

### V2 帧格式

64 字节输出报告，报告 ID `0x4D`：

| 偏移 | 含义 |
| --- | --- |
| 0 | `0x4D` 帧头 |
| 1 / 2 | 版本 `0x01` / 标志 `0x01` |
| 3 | 数据长度 |
| 4–5 | 命令 ID（小端），电量查询 `0x0900` |
| 6 / 7 | BizCode / 序号 |
| 8.. | 数据 |
| 8+len | XOR 校验（从字节 2 起异或） |

回包同为 `0x4D` 帧，数据区从偏移 8 开始：

| 偏移 | 含义 |
| --- | --- |
| 0–1 | 设备 VID（小端） |
| 2–3 | 设备型号 PID（小端） |
| 10 | 连接方式：1 有线 / 2 2.4G / 3 蓝牙 |
| 11 | 充电状态：0 放电 / 1 充电 |
| 12 | 电量百分比 0–100 |

> 设备休眠 / 关机时接收器仍会回包，但 payload 里的 VID 变成 `0x00FE`、电量 0、连接方式 0。
> 插件用 `expect_vid`（默认 `0x3837`）挡掉这种回包，避免面板出现 0% 假告警；
> 唤醒后下一次刷新自动恢复。

## 已适配设备（飞智 Flydigi，VID 0x37D7）

| 设备 | PID | 协议 | 通道 | 报告 ID |
| --- | --- | --- | --- | --- |
| APEX5 Wireless | 0x2501 | flydigi-newxinput | usage 0xFFA0 | 输出 3 / 输入 4（31 字节数据） |
| Vader 5 Pro（同族） | 0x2401 | flydigi-newxinput | usage 0xFFA0 | 无编号报告（输出 0） |

> 同 VID 的**充电底座 CD2（0x6001）**同样暴露 0xFFA0（65 字节、无报告 ID），
> 配置里用 `product_ids: [0x2501]` 把它排除，避免往底座写空帧。

### 帧格式

32 字节输出报告，未用字节补 0（实测不强制校验）：

| 偏移 | 含义 |
| --- | --- |
| 0 | 报告 ID（Apex 5 = `0x03`，无编号设备为 `0x00`） |
| 1 / 2 | Magic `5A A5` |
| 3 | 命令字，`0x01` = get info（电量） |
| 4 | 长度 = 负载字节数 + 2（无负载为 `0x02`） |
| 5.. | 负载 / 参数（get info 填 `0x00`） |

回包（去掉报告 ID，正文自 `5A A5` 起）：

| 偏移 | 含义 |
| --- | --- |
| 0–1 | `5A A5` 帧头 |
| 2 | 命令字回显（`0x01`） |
| 5 | 设备号：`0x80`(128) Apex 5，`0x82`(130) Vader 5 Pro |
| 6 | 连接方式：2 = 2.4G 无线 / 1 = 有线（旧架构编码） |
| 11 | 高 4 位状态 0 放电 / 1 充电 / 2 已充满；低 4 位档位 ×20 = 电量 % |
| 15–16 | 固件版本，低字节在前（`70 45` → 7.0.4.5） |
| 30 | 末字节，实测 `0x00`（非校验和，故不校验） |

电量粒度只有 5 档（0/20/…/100%），是设备协议本身的限制，不是解析精度问题。

## 电量历史与预测

- **采样**：主程序每次扫描完成后按「记录间隔」节流落库（同一设备两条记录至少间隔 `间隔 × 0.9`），
  不额外开 USB 通道。
- **表结构**：`samples(uid, name, percent, charging, ts)` + `devices(uid, name, vendor, first_ts, last_ts, last_percent)`；
  `uid` 用 `VID:PID:序号`，设备拔掉后历史仍保留、仍可清除。
- **聚合**：24 小时→15 分钟桶、7 天→3 小时桶、30 天→12 小时桶，取桶内平均。
- **预测**：取近 24 小时 `charging = 0` 的样本做最小二乘，斜率即 `%/小时`，
  剩余时长 = 当前电量 ÷ 速率；样本少于 3 个或跨度不足 0.4 小时提示「数据不足」，充电中提示「正在充电」。
- **清除**：按设备删除样本与设备行；默认保留 90 天，程序启动 6 秒后清理一次过期样本。

## 打包与开机启动

```bash
python tools/build_exe.py          # → dist/StrelitziaHIDBattery.exe（约 37 MB，单文件免安装）
```

单文件 EXE 运行期解压到临时目录（退出即删），因此**所有可写数据都落在 EXE 旁边**：

```
StrelitziaHIDBattery.exe
config/profiles.json     接口配置（导入接入包时自动创建 / 更新）
protocols/               用户插件目录 + README.txt（格式说明）
assets/icons/            上传的图标
data/history.db          历史库
```

- 换电脑只需拷 EXE；想连配置一起带走就整个目录拷过去。
- 若放在 `Program Files` 这类不可写目录，整棵目录退回 `%LOCALAPPDATA%\StrelitziaHIDBattery`（见 `app/paths.py`）。
- 打包用 `--collect-submodules app` 覆盖懒加载模块（`console` / `plugin_store` / `prompt_page`）；
  内置协议另有 `_BUILTIN` 兜底导入。
- 开机启动：设置页开关写 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 的
  `StrelitziaHIDBattery` 值（旧版的 `HIDBattery` 会被顺手清掉），免管理员。

## 验证

```bash
python tools/selftest.py                 # 回归：协议 / 配置 / 扫描 / 检测 / 提示词 / 图标 / 历史 / 配色 / 接入包
python tools/hid_probe.py --vid 0x3837   # 命令行枚举，核对集合与报告长度
python tools/hid_desc.py --vid 0x37D7    # dump 报告描述符：看清每个集合的报告 ID 与长度
python tools/smoke.py                    # 端到端：托盘 → 面板 → 设备行 → 提示词 → 独立窗口三页
python tools/build_exe.py                # 打包免安装 EXE
python tools/shot.py --demo-icon         # 生成界面截图
```

手工核对：

1. 托盘提示为 `Strelitzia HID Battery`，图标显示最低电量。
2. 点托盘弹出面板 → 点桌面任意窗口，面板自动收起；再点托盘又出现，位置与上次一致。
3. 面板列出全部设备；插拔接收器让设备数量变化，面板高度跟着变、不出现裁切。
4. 给设备插上充电线 → 托盘图标出现闪电（深/浅任务栏都清晰），且不弹低电量告警。
5. 面板齿轮 → 独立窗口打开（有标题栏、可缩放）→ 左侧三页正常切换。
6. 设置页「导入接入包」选一个接入包 → 接口列表出现新插件，面板出现对应设备。
7. 电量 ≤30% 图标变黄、≤15% 变红。
8. 点面板刷新按钮 → 图标变成旋转圆环，读完回到普通图标，副标题从「正在读取设备…」变成「已完成读取 · N 台设备」；
   若某台设备休眠不响应，15 秒后面板显示「读取超时，稍后自动重试」，过一轮会自动恢复。

## 常见问题

- **托盘图标没直接显示**：Windows 默认折叠进任务栏 `^`，把电池图标拖到任务栏即可常驻。
- **面板里没有图标**：图标只来自本机上传，设置页「设备图标」里点 ↑ 选一张图。
- **读不到电量**：多为设备休眠或接收器被官方驱动独占；唤醒后刷新，「接口探测」页看回包。
- **设备没出现在面板**：还没有对应协议。点设备行生成提示词 → AI 返回接入包 → 导入。
- **导入报「未注册成功」**：说明插件代码有语法错误或 `id` 与 `profile.protocol` 不一致，
  看提示里的具体异常，或把 `protocols/README.txt` 与插件源码对照修正。
- **电量与实际不符**：不同固件字段偏移可能不同，编辑接口的「高级参数 (JSON)」调整 `battery_index` 等。
