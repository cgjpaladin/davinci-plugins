---
name: delivery-checker
description: 交付自检工具开发指南。新增检查项、修改检查逻辑、操作 CHECKS 注册表时使用。触发词：交付自检、加检查、CHECKS、check_core、AI校对、错别字。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
---
# 交付自检工具开发

> 基于真实代码：`ui.py`（~2700行）+ `check_core.py`（1845行）+ `config.py` + `launcher.py`
> v2.5.7 | 最后更新：2026-06-16

---

## CHECKS 注册表（唯一真相来源）

`ui.py` 中的 `CHECKS` 列表驱动所有检查项。每个 dict：

```python
{"id": "black_border", "section": "黑边", "chk_id": CHK_BORDER,
 "group": "视频", "subgroup": "黑边", "run_fn": _run_black_border_check,
 "tracks": ["video"], "gate": "video"}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | snake_case 唯一标识 |
| `section` | ✅ | CheckBox 显示文字 |
| `chk_id` | ✅ | CheckBox 控件 ID 常量 |
| `group` | ✅ | 一级分组：工程/视频/音频/字幕/色彩 |
| `subgroup` | ✅ | 二级分组 |
| `run_fn` | ✅ | runner 函数，`None`=待开发（灰色不可勾） |
| `tracks` | ✅ | 预加载轨道类型列表，`[]`=不预加载 |
| `gate` | ✅ | 门控制。`""`=第零道门永远跑；其他值受 `gate_all_ok` 控制 |
| `hidden` | 可选 | `True`=完全隐藏（不显示 CheckBox） |

### 当前 subgroup 完整格局（v2.0.29）

```
工程: 设置 / 路径(2项) / 轨道 / 启用
视频: 夹帧 / 黑帧 / 黑边 / 变速 / 越轨 / 直通(隐藏) / 尾板
音频: 声道(2项) / 越轨
字幕: 文本(2项) / 合规(3项)
色彩: 色彩 / 调色标记
```

括号内为共享 subgroup 的检查数。22 条注册中共 5 个 subgroup 跨检查共享（同组内，正常），仅「越轨」跨 group 共享（视频+音频），需 `(group, subgroup)` 组合键过滤。

`GROUP_ORDER = ["工程", "视频", "音频", "字幕", "色彩"]`

### 当前活跃项（22 条注册，2 条 run_fn=None）

run_fn=None 的项：`through_edit`（直通编辑，隐藏）、`audio_loudness`（音量，灰色）

---

## 门机制

### 四扇并行门

四个门是**并行**的，没有层级。任一不通 → 全部门控检查跳过。

| 门 | 变量 | 条件（严格模式，勾了「轨道结构」） |
|----|------|-----------------------------------|
| 工程门 | `engineering_ok` | 未勾「工程设置」→ 恒 True；勾了 → 时码必须归零 |
| 字幕门 | `gates["subtitle"]` | 工程门 ∧ 轨数=预设 ∧ 全启用 |
| 视频门 | `gates["video"]` | 工程门 ∧ 轨数=预设 ∧ 全启用 |
| 音频门 | `gates["audio"]` | 工程门 ∧ 轨数=预设 ∧ 全启用 ∧ 名称匹配 |

```python
gates_ok = engineering_ok and all(gates.values())
```

### 两种模式

由用户是否勾选「轨道结构」控制：

| 模式 | 条件 | 三门行为 |
|------|------|---------|
| 严格 | `itm[CHK_TRACK].Checked` | 每门 = 工程门 ∧ 轨数匹配 ∧ 全启用 |
| 宽松 | `not checked` | 每门 = 工程门 即可 |

### 门如何控制检查

```python
g = check.get("gate", "")
if g and not gates_ok:       # gate="" → 不跳；gate≠"" → 任一失败全跳
    continue
```

| gate 值 | 行为 |
|---------|------|
| `""` | 不用门控制，直接跑 |
| 非空 | 全用 `gates_ok`，四扇并行门全过才跑 |

### 预加载优化

门关闭 → 对应轨道的预加载也跳过：

```python
needed = set()
for check in CHECKS:
    if check.get("run_fn") and itm[check["chk_id"]].Checked:
        if not check.get("gate") or gate_all_ok:   # gate="" 或门通过
            needed.update(check.get("tracks", []))
preload_timeline_items(timeline, track_types=list(needed))
```

### 失败可见性

门失败 → 窗口顶部显示 `lbl_gate_warn` 黄色警告文字（仅当用户勾了「轨道结构」时才显示具体哪个门失败）。

---

## 分级规则

| 等级 | 图标 | 触发检查 |
|------|------|---------|
| **fail** ❌ | 默认 | 所有未列在 warn 中的检查 |
| **warn** ⚠ | 仅5类 | 夹帧、直通编辑(隐藏)、异体字、系统词典违禁词、尾板 |

---

## 加新检查（3 步）

### 步骤 1：写检查函数 → `check_core.py`

```python
def check_xxx(timeline, fps=25.0, io_range=None, debug_log=None) -> list:
    """检查 XXX。Returns: list[dict]，第一条 is_summary=True"""
    issues = []
    # 检查逻辑，issue 必须带 track + timecode:
    # issues.append(_make_result("fail", track="V4", timecode=tc,
    #     detail="描述", reason="建议"))
    if not issues:
        return [_make_result("pass", detail="XXX: 全部通过", is_summary=True)]
    results = [_make_result("fail", detail=f"XXX: {len(issues)} 处", is_summary=True)]
    results.extend(issues)
    return results
```

**铁律**：
- 第一条 MUST `is_summary=True`
- 返回 ≥2 条（1 summary + ≥1 detail）。纯 summary = UI 不渲染
- 汇总格式：`"检查名: N 处"` / `"检查名: 全部通过"`

### 步骤 2：注册 CHECKS + 写 runner → `ui.py`

```python
# ① 常量区加 CheckBox ID
CHK_XXX = "chk_xxx"

# ② import 加函数名
from check_core import (..., check_xxx)

# ③ CHECKS 注册表加一条
{"id": "xxx", "section": "检查名", "chk_id": CHK_XXX,
 "group": "视频", "subgroup": "越轨", "run_fn": _run_xxx_check,
 "tracks": ["video"], "gate": "video"},

# ④ runner（必须转发 io_range）
def _run_xxx_check(timeline, fps, **_kw):
    return check_xxx(timeline, fps, io_range=_kw.get("io_range"))
```

### 步骤 3：验证 → `bash build_local.sh`

```bash
cd 交付自检工具 && bash build_local.sh   # 编译+本地部署
```
然后在达芬奇里跑一次完整检查，看日志 `~/.workbuddy/logs/.../ui_*.log`：
- 新检查是否出现、是否正常通过/失败
- 无崩溃/报错
- 结果 Tree 中新 section 正确显示（注意 subgroup 不重名）

---

## 数据流（全链路）

```
check_core._make_result(status, track, timecode, detail, reason, is_summary)
    → {status, track, timecode, detail, reason, is_summary}
        ↓ _process_result() + FIELD_TO_COLUMN
    → {track, tc, msg, reason}   (❌/⚠ 图标拼入 msg 开头)
        ↓ _start_check() 分组
    → section: {group, subgroup, title, summary, rows, all_ok}
        ↓ _render_group()
    → Tree: 行按 group → subgroup 分组平铺
```

#### FIELD_TO_COLUMN 映射

```python
FIELD_TO_COLUMN = {
    "track": "track", "timecode": "tc", "detail": "msg", "reason": "reason"
}
```

#### _process_result 行为

- `pass` 状态 → 返回 is_pass=True，不入 rows
- `fail` → msg 前加 `❌ | `，入 rows
- `warn` → msg 前加 `⚠ | `，入 rows

---

## detail/reason 语义

- `detail` → "问题"列 = 完整描述（标识 + 诊断），如 `"文件名，左声道静音"`
- `reason` → "建议"列 = 修复建议，如 `"请将音频片段复制为立体声"`

```python
# ✅ _make_result("fail", detail=f"{name}，未启用", reason="请在时间线上启用该片段")
# ❌ _make_result("fail", detail=name, reason="未启用")
```

---

## AI 错别字校对面板（右侧独立）

`_run_ai_typo()` 中直接构造 Tree 行，不走 `_make_result` + `FIELD_TO_COLUMN`：

| Tree 列 | 内容 | 代码 |
|---------|------|------|
| 轨道 | `ST1`（硬编码） | `"track": "ST1"` |
| 问题 | `原文——错误类型` | `f"{c['original']}——{c.get('reason', '')}"` |
| 建议 | `应改为「正确字词」` | `f"应改为「{c['correction']}」"` |

数据流：`parse_script(src)` → `{"lines": [...]}` → `check_typos()` → DeepSeek V4 Pro → 渲染

> **v2.5.7 重构**：`parse_script` 不再做角色提取、分集分割。只做格式提取（`docx/doc/pdf/txt/md` → 纯文本行），全量文本直接喂给 AI，AI 自行理解角色名、性别、集号。集号手动输入功能已删除。
>
> **LLM 提示词要点**：system prompt 告诉 AI 自己从人物小传提取角色名和性别。user message 只含剧本全文 + 时间线名 + 字幕行。不传「集号」「--- 第N集 ---」标记。

---

## IO 选区

`_start_check()` 读 `timeline.GetMarkInOut()` → `io_range=(in, out)` → 每个 runner 转发给 check 函数 → check 函数内 `_in_io_range(it, io_range)` 过滤。没设 IO → `io_range=None` → 全通过。

---

## 运行环境

`_start_check` 传给每个 runner 的 kwargs：

```python
check["run_fn"](timeline=timeline, fps=fps, project=project,
                personal_enabled=itm[CHK_CENSOR_PERSONAL].Checked,
                io_range=io_range, debug_log=_action_log)
```

| 参数 | 来源 | 何时需要 |
|------|------|---------|
| `timeline` | `project.GetCurrentTimeline()` | 全部 |
| `fps` | `float(project.GetSetting("timelineFrameRate"))` | 时码计算 |
| `project` | `resolve.GetProjectManager().GetCurrentProject()` | 项目设置/色彩/黑边 |
| `personal_enabled` | CheckBox 勾选状态 | 仅个人违禁词 |
| `io_range` | `timeline.GetMarkInOut()` | IO 过滤 |

---

## 预加载缓存

`preload_timeline_items(timeline, track_types)` — 每次 `_start_check` 开头调用。内部调 `_clear_clip_files_cache()`。

`_get_cached(item, key, default)` 在 `check_core.py`：

| key | 范围 | 说明 |
|-----|------|------|
| `enabled`, `start`, `end`, `mp`, `props` | 全部轨 | 通用 |
| `name`, `mp_name`, `mp_resolution`, `mp_fps` | 有 MP | 媒体池 |
| `source_start`, `source_end` | 视频轨 | 素材帧范围 |
| `channel_mapping`, `audio_dur` | 音频轨 | 声道 + 时长 |

### 共享缓存

`_collect_clip_files()` — 脱机+路径检测共用，阻断重复 IPC。`_get_items()` 自带 `_items_cache`。

---

## 脱机检测

达芬奇仅两种脱机模式：
1. **MediaPoolItem 被删**：时间线上还在，媒体池里找不到 → `mp=None`
2. **源文件丢失**：mp 存在，`File Path` 为空（文件被移动/删除/改名）

无 MP 时按扩展名判定（有媒体扩展名 = 脱机），有 MP 时检查 path 是否为空。复合/合成片段自动跳过。

---

## 全半角检测（系统检测，不通过 AI）

正则 `[\uff00-\uffef]` 扫描字幕原文，`str.maketrans` 生成半角建议。`status=fail`，分类「字幕 → 文本」（与换行/时长同类）。

**防重复**：全角 `U+FF01-U+FF5E` 已从 `bad_char_ranges.txt` 注释掉，避免异体字检测重复报。

```python
def _run_fw_check(timeline, fps, **_kw):
    fw_pattern = re.compile(r'[\uff00-\uffef]')
    fw_to_hw = str.maketrans('０１２...', '012...')
    for it in (timeline.GetItemListInTrack("subtitle", 1) or []):
        text = it.GetName() or ""
        if fw_pattern.findall(text):
            fixed = text.translate(fw_to_hw)
            if fixed != text:
                results.append({"status": "fail", "detail": f"{text} → {fixed}"})
```

## 错别字提示词优化方法论

详见 `knowledge/LLM提示词优化方法论.md`。核心：
- 每条规则 = 正例（应报）+ 反例（不改）+ 原因标注
- 所有示例为完整句子（original → correction），不写字对
- JSON example 与规则文字必须对齐
- `reason` 归一化：AI 偶尔输出「错字」→ `reason.replace("错字", "错别字")`

路径：`~/Library/Preferences/Blackmagic Design/DaVinci Resolve/Fairlight/Presets/CONSOLE_FLEXI/交付总线设置.dat`

`check_track_structure()` 音频部分两层检查：
1. MD5 哈希 vs 参考值 `eb3ad5485026fa8e568608638d118a2d` — 文件缺失/版本不对同一出口
2. 轨名/数量比对 — 推断是否正确应用到时间线

20.0 兼容：纯文件 I/O，不依赖 `GetFairlightPresets()` API。

---

## 路径检测可配置化

**白名单模式**：`deploy.json` 的 `smb_paths` 字段（数组）。

- 空 → `check_path_location()` 返回「未配置，已跳过」→ 全放行
- 非空 → 素材路径只要匹配任一项即通过，否则报「不在服务器路径」
- 全程不依赖 `/Volumes/MYJC` 硬编码，旧 `smb_mount` 兼容已砍

```python
# check_core.py — 每次现场读，不缓存
from deploy_config import get_smb_paths
prefixes = get_smb_paths()
if not prefixes and not os.environ.get("WORKBUDDY_PERSONAL"):
    return [_make_result("pass", detail="路径检测: 未配置服务器路径，已跳过", is_summary=True)]
if not any(path.startswith(p) for p in prefixes):
    issues.append(...)
```

**注册表铁律**：路径/脱机检测的 `tracks` 必须含 `["video", "audio"]`。只写 `video` 会导致音频轨漏检。

**缓存清理**：每次「开始检查」前调 `_clear_clip_files_cache()`。`_clip_files_cache` 是模块级变量，不清理会在 I/O 范围变化或素材增减时返回旧数据。

### 配置页 SMB 路径编辑

`CONFIG_SECTIONS` 中 `smb_paths` 类型：
- ComboBox 下拉展示所有路径，`+ 添加路径` 弹出文件夹选择器
- `− 删除路径` 从 ComboBox 选中项中删除
- 保存写 `deploy.json` 的 `smb_paths` 字段
- 公司版和个人版均可见
- ComboBox API：`CurrentText` 取值（非 `Text`），`Clear()`+`AddItem()` 刷新

---

## 字典文件

| 文件 | 用途 | 格式 |
|------|------|------|
| `dicts/censor_cn.txt` / `censor_en.txt` / `censor_bw.txt` / `censor_bw_sms.txt` | 系统词典（4本，配置勾选启用） | 一行一词，#注释 |
| `dicts/censor_nrta.txt` | 空/占位 | — |
| `dicts/短剧违禁词表.csv` | 个人词典 | `白名单, ,黑名单,建议一,建议二` |
| `dicts/bad_char_ranges.txt` | 异体字 Unicode 范围 | `U+XXXX-U+YYYY  # 说明` |

黑白名单：个人先跑 → 白名单词个人+系统两级均跳过 → 系统结果 `_filter_covered()` 去重。

---

## 缓存策略（2026-05-30 沉淀）

三套缓存，全部在 `~/Library/Application Support/交付自检/` 下：

| 缓存 | 键 | 失效条件 |
|------|-----|----------|
| **飞书文档** `docx_{token}.docx` + `.rev` | `revision_id`（轻量 API，零网络下载） | 文档内容编辑 → revision 变化 |
| **飞书文件** `file_{token}.docx` + `.meta` | `modified_time`（轻量 API） | 文件替换 |
| **本地文件** `local_{hash}.json` | 文件 SHA256 + 路径 | 文件内容或路径变化 |
| **LLM 结果** `typo_cache.json` | 字幕行 + 剧本行联合 SHA256 | 字幕或剧本变化 |

**飞书文档 key 细节**：`GET /open-apis/docx/v1/documents/{token}` 返回 `revision_id`（整数，随编辑累加），不返回 `modified_time`。`drive/v1/files/{token}` 对 docx 返回 404。两个端点分工：docx API 用于原生文档，drive API 用于上传文件。

**降级行为**：API 不可达时使用旧缓存（不阻塞用户流程）。首次无缓存 + API 不可达 → 下载失败有对应 Error。

## 配置系统

`CONFIG_SECTIONS` 注册表驱动，持久化到 `~/Library/Application Support/交付自检/config.json`。

| 项 | type | 全局变量 | 默认值 |
|----|------|---------|--------|
| 轨道数量 | `track_preset` | `_track_values` | [1,5,10] |
| 字幕时长阈值 | `clamp_threshold` | `_clamp_value` | 5帧 |
| 视频夹帧阈值 | `video_clamp_threshold` | `_video_clamp_threshold` | 2帧 |
| 黑帧时长阈值 | `black_frame_sec` | `_black_frame_sec` | 1.0秒 |
| 系统词典 | `censor_system_subs` | `_censor_subs` | 4本全开 |
| 个人词典 | `censor_personal` | — | 编辑按钮 |

---

## 日志系统（v2.0.22 补齐）

### 三层日志

| 层级 | 函数 | 路径 | 内容 |
|------|------|------|------|
| UI 运行 | `_action_log(msg)` → `_log.ui()` | `~/.workbuddy/logs/交付自检工具/ui_{hostname}_{date}.log` | 逐条检查结果、操作记录、错误 |
| 结构化 | `_log.ops({...})` | `~/.workbuddy/logs/交付自检工具/ops_{hostname}_{date}.jsonl` | 完整检查结果 JSON |
| Launcher | `_log.launcher(...)` | 同上 launcher 前缀 | 启动路由、版本号 |

### 检查结果自动记日志

`_start_check()` 循环内自动记录每条非 pass 结果：
- 日志格式: `{track} {timecode}  {detail}`
- 通过的结果不写（去噪）
- 崩溃写 `traceback.format_exc()`

---

### ops 日志注意

- sections 字典的键是 `"title"` 不是 `"section"`
- 写入失败不能 `except: pass`——至少要记 `_action_log` 警告

### 达芬奇日志

路径：`~/Library/Application Support/Blackmagic Design/DaVinci Resolve/logs/ResolveDebug.txt` — 查 Fusion 脚本报错时有用。

## 架构速查

| 组件 | 位置 | 用途 |
|------|------|------|
| `_make_result()` | check_core.py | 统一构造返回 dict |
| `_process_result()` | ui.py | FIELD_TO_COLUMN 映射 + ❌/⚠ 图标 |
| `_filter_covered()` | ui.py | 系统词典去重 |
| `_make_result_passthrough()` | ui.py | 同格式 dict（避免跨模块循环 import） |
| `_render_group()` | ui.py | 渲染 subgroup 到 Tree |
| `_build_group_rows()` | ui.py | 从 CHECKS 生成 CheckBox 布局 |
| `_validate_checks()` | ui.py | 启动时校验 run_fn 可调用（用完自毁） |

## UIManager 已知限制

| 限制 | 影响 |
|------|------|
| 无 ScrollArea | 列表型 UI 不可行，CheckBox 只能平铺 |
| Tree 无 SetItemText/SetItemChecked | Tree 只能做纯展示，不能做交互式勾选清单 |
| VGroup 不裁剪溢出 | 控件多时窗口会撑破屏幕 |
| 控件 API: `({"ID": "x", ...})` | 不是 `("x", {...})` — ID 必须在 dict 里 |
| ComboBox: `Text` 返回 None | 取选中值用 `CurrentText`，不是 `Text` |
| ComboBox: `AddItem()` 需在 `Show()` 前 | 否则下拉为空 |
| ComboBox: 运行时刷新需 `Clear()` + `AddItem()` + `Text=""` | 没有 `setItems()` 方法 |

## debug_log 调试回调（v2.0.26）

`_start_check()` 自动传 `debug_log=_action_log` 给所有 runner。check 函数签加 `debug_log=None` 后直接用：

```python
def check_xxx(timeline, fps=25.0, io_range=None, debug_log=None):
    if some_skip_condition:
        if debug_log: debug_log("跳过: 原因...")
        return [...]
```

已有调试点：
- 视频越轨：轨数≠5 → `"视频越轨跳过: 轨数 X ≠ 5"`
- 音频越轨：轨数≠10 → `"音频越轨跳过: 音轨数 X ≠ 10"`
- 音频越轨：轨名不匹配 → `"音频越轨跳过: 轨名与预设不匹配"`

加新调试只用 `if debug_log: debug_log("...")`，不需要改 ui.py。

## launcher 路径（v2.0.28）

**import 顺序铁律**：`sys.path.insert` 必须在 `from shared.xxx import` 之前。launcher 先搜索 shared/ 目录再 import：

```python
_SHARED_CANDIDATES = [
    os.path.join(_HERE, '..', 'shared'),              # ① 项目目录
    os.path.expanduser("~/WorkBuddy/达芬奇插件工坊/shared"),  # ② WorkBuddy
    "/Volumes/MYJC/06_Software/达芬奇脚本/shared",     # ③ SMB
]
for _d in _SHARED_CANDIDATES:
    if os.path.isdir(_d):
        sys.path.insert(0, _d)
        break
from deploy_config import load      # ← 路径就绪后才能 import
```

诊断日志（`_log.launcher`）：Python 版本、路由 DEV/SMB、SMB 挂载状态、代码源路径。

## 构建与部署

### 版本号

`config.py` 中的 `__version__` 三位语义：`主.次.补丁`。`VERSION_BUMP=patch bash build_local.sh` 自动递增。

- patch（0.0.1）：bug 修复
- minor（0.1.0）：新检查项/小特性
- major（1.0.0）：架构变更

### 部署三梯队

| 命令 | 作用 | 场景 |
|------|------|------|
| `bash build_local.sh` | 编译 + 拷贝到 Fusion Scripts | 每轮改完 |
| `bash push_all.sh` | 同步 SMB + gray.json | 推全公司 |
| 灰度 | `GRAY_CHOICE=1` 先拷灰度目录 | 重大变更前 |

`push_all.sh` 内 MD5 逐文件对比，不一致硬拦截。

## HINT 文案规范

窗口底部 `HINT_LB` 状态栏，三种终态：

| 状态 | 文案 | 颜色 |
|------|------|------|
| 失败 | `❌ N 项未通过，请修复后重新检查` | 默认 |
| 失败+警告 | `❌ N 项未通过，请修复后重新检查，⚠ M 项警告` | 默认 |
| 仅警告 | `⚠ M 项警告` | 默认 |
| 通过 | `全部检查通过 ✓ 现在可以交付渲染了` | **绿色** |

中间态：`检查中...`、`AI 校对中...`、崩溃时 `❌ 检查崩溃: {e}`。

## 常见踩坑

| # | 坑 | 教训 |
|---|-----|------|
| 1 | subgroup 同名串组 | `_render_group` 过滤必须 `(group, subgroup)` 全键 |
| 2 | `_log.ops` 键名 `"section"` vs `"title"` | sections dict 的键是后者 |
| 3 | `except: pass` 静默吞错 | ops 日志写失败至少记 `_action_log` 警告 |
| 4 | import 在 `sys.path` 之前 | launcher 先搜 shared/ 路径再 import |
| 5 | `is_summary=True` 缺失 | 每个 check 函数第一条返回必须带 |
| 6 | check_core 不记日志 | 用 `debug_log` 参数 |
| 7 | 修完只改一处 | grep 搜同款代码全函数全项目 |
| 8 | 蒸馏 ≠ 删除 | 写精简版留原文件，绝不 `rm` |
| 9 | tracks 漏写 audio | 路径/脱机检测只配 `["video"]` → 音频轨漏检 |
| 10 | `_clip_files_cache` 复用 | 模块级缓存不随 I/O 变化/素材增减刷新 → 每次检查前清 |
| 11 | 全半角被异体字重复检测 | 独立检测后需从 `bad_char_ranges.txt` 注释全角行 |
| 12 | `_get_cached` 未预加载的轨道 | 返回 default → 需兜底 `it.GetMediaPoolItem()` / `it.GetStart()` |

## 生命周期

### 启动（`main()`）

1. `bmd.scriptapp('Resolve')` 连接
2. 创建 UIManager 窗口 `dlg.Show()`（900×520，右上角）
3. `_validate_checks()` — 校验 CHECKS 中 `run_fn` 可调用，用完自毁
4. 加载配置 → `disp.RunLoop()` 进入事件循环

### 关闭（`_on_close()`）

```python
def _on_close(ev):
    global _checking
    _checking = False
    _action_log("窗口关闭")
    disp.ExitLoop()
```

### 运行检查（`_start_check()` 6 阶段）

1. **门控** — 工程门（时码归零）→ 三门（轨数+启用）→ `gates_ok`
2. **预加载** — `preload_timeline_items()` 按需加载轨道数据
3. **遍历 CHECKS** — 对每个勾选且门开的检查：调 `run_fn()` → 汇总 → 逐条记日志
4. **分组** — 按 `(group, subgroup)` 建 `sections`
5. **渲染** — 左侧 Tree 建组/子类，右侧 Tree 渲染第一组
6. **汇总** — HINT_LB 写 `❌/⚠/✅` 状态 + ops 持久化

崩溃保护：单个检查崩溃用 `try/except` 兜底不阻断其他检查。

## 窗口控件速查

| ID | 类型 | 用途 |
|----|------|------|
| `GROUP_TREE` | Tree | 左侧分组导航 |
| `TREE_RESULT` | Tree | 右侧检查结果 |
| `BTN_START` | Button | 开始检查（蓝色） |
| `BTN_CONFIG` | Button | 配置弹窗 |
| `HINT_LB` | Label | 底部状态栏（多态） |
| `lbl_gate_warn` | Label | 门失败警告（黄色，顶部） |
| `lbl_check_title` | Label | 左区标题「常规检查」 |
| `BTN_{gn}` ×5 | Button | 分组全选/全不选开关 |

## 点击树跳转时间码

单击 `TREE_RESULT` 行 → `timeline.SetCurrentTimecode(row["tc"])`，达芬奇播放头跳到对应位置。UI 写 `🎯 跳转到 {tc}` 日志。

## 内部工具函数

| 函数 | 位置 | 作用 |
|------|------|------|
| `_ts()` | ui.py | `"MM-DD HH:MM:SS"` |
| `_action_log(msg)` | ui.py | UI 日志 + 时戳 |
| `_get_smpte(fps)` | check_core.py | 缓存 SMPTE 实例 |
| `_in_io_range(it, io_range)` | check_core.py | 片段在 IO 区间 |
| `_get_clip_name(item)` | check_core.py | 取片段名称（优先 mp_name） |
| `_get_items(timeline, type, idx)` | check_core.py | 缓存轨道片段列表 |
| `_clear_clip_files_cache()` | check_core.py | 每轮检查前清 |
| `_collect_clip_files()` | check_core.py | 脱机+路径共用 |

## 预加载机制

`preload_timeline_items(timeline, track_types)` 在 `_start_check` 开头调用：

1. 清 `_items_cache` + `_props_cache`
2. 按需从 track_types 遍历轨道 → 调 `GetItemListInTrack()` → 存缓存
3. 每个 item 预取 `enabled/start/end/mp/name/props` 等键
4. 后续 `_get_items()` / `_get_cached()` 走缓存，不再 IPC

门关闭的轨道不加载。

## _on_show 空壳

```python
def _on_show(ev):
    pass  # 初始化放在 main() 里，Show 事件在子进程模式下不可靠
```

`dlg.On[WIN_ID].Show = _on_show` 但什么都不做——DaVinci 子进程模式下 Show 事件时序不可靠，所以所有初始化都在 `main()` 里做完再 `disp.RunLoop()`。

## 测试方法

### 编译测试（无需达芬奇）

```bash
python3 -m py_compile check_core.py ui.py config.py launcher.py
```

### 导入测试

```python
import sys; sys.path.insert(0, '../shared')
import check_core, config  # 不导入 ui.py（需要 fusionscript）
```

### 集成测试（需达芬奇运行）

测试机：**dd-mbp**（邓邓的 MBP，借来当测试机。ZT 10.163.15.58, User ttttt, SSH 免密已配 `~/.ssh/config`）

```bash
scp 交付自检工具/ui.py dd-mbp:'/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/交付自检工具/ui.py'
```

裁缝老师在 dd-mbp 上打开达芬奇，跑对应操作验证。

### 日志验证

```bash
tail -50 ~/.workbuddy/logs/交付自检工具/ui_*.log
# 检查：无崩溃、检查数正确、结果不失真
```

## UI 设计参数（2026-05-31）

改皮肤/换样式 → 只改 `ui.py` 顶部 `# ── 设计参数 ──` 块：

```python
FONT_H1/H2/BODY/SM/XS    # 字号
SPACE_NONE/TIGHT/SM/NORMAL/RELAXED/WIDE  # 间距
SIZE_BTN_* / SIZE_TOGGLE / SIZE_LINE_H    # 尺寸
PAD_BTN/PANEL              # 内边距
RAD_BTN/PANEL              # 圆角
STYLE_HEADING/ACCENT/DIM/HINT/DIVIDER/WARN  # 复合样式
```

## 配置页（v2.3.0+）

```
激活码 → DeepSeek Key → 飞书 ID → 飞书 Secret → 个人词典 → 停用按钮
```

### 布局模式

- **分区+分隔符**：`_sec("▸ 标题")` 灰色加粗 + `_sep()` "─"×48 分隔线，每区一个 `VGroup`
- **三行固定布局（授权区）**：Label → HGroup(输入) → HGroup(按钮)，永不隐藏只用 `Enabled`/`Text`/`StyleSheet` 切换
- **金区(TRIAL_LB)=授权（gold#DCB43C）**：状态→天数→异常提示，永不空
- **灰区(HINT_LB)=指引（gray#828282）**：操作反馈→结果→默认提示，永不空
- **启动校验模式**：Show 前灰按钮 + "⏳ 联网校验中…" → Show → 同步 verify → 恢复；单线程零竞态
- **配置/授权解耦**：保存只管 API Key；激活/停用独立回调；授权中灰掉保存/关闭

### 控件规则

- SMB 用户只显示个人词典：`if not WORKBUDDY_PERSONAL: filter`
- API Key 密文显示：`_mask("sk-ab…xyz")`，保存时检测掩码保真值
- 首次 `_load_api_keys()` 从 `.env` 自动迁移（`encoding="utf-8"` 必加）
- 停用按钮试用期灰掉：`if cred.get("is_trial"): cfg[...].Enabled = False`
- 激活错误不关闭对话框：`if err: return` 留在页面

## License 体系（v2.3.0+）

- FC: `activate` 检查 key→FP，`max_devices=1`；`deactivate` 删 license + 重置 key
- 插件：`from shared.license import activate/heartbeat/deactivate`
- AI 到期锁：`_ai_allowed = d > 0` → `itm[BTN_AI_TYPO].Enabled = False`

## 更新弹窗（v2.3.4+）

```python
_items = {};  _items["btn"] = ui.Button(...)
dlg = disp.AddWindow(..., _items["btn"])
dlg.Show()
_items = dlg.GetItems()           # ← 唯一正确：蓝图 → 真控件
_items["btn"].Text = "下载中…"     # ← 正确的赋值方式
_items["btn"].Enabled = False
```

- 置顶：`"WindowFlags": {"Window": True, "WindowStaysOnTopHint": True}`
- 别调用 `ProcessEvents()` — UIManager 下会阻塞
- 弹窗全程显示，下载完成变「关闭」
- ghproxy 优先 + `importlib.reload(updater)` 强刷链路

## 抖音时长合规（v2.4.0）

`check_core.py` 的 `check_timeline` 函数，在已有 <41s 检查下方加 `elif >180s`：

```python
elif duration_sec > 180:
    results.append(_make_result("fail",
        detail=f"时长 {_fmt_duration(duration_sec)}（超过180s）",
        reason="抖音单集≤3分钟，超时驳回。建议优化至90秒左右"))
```

对外公告写在 CHANGELOG.md 里——用户点「⬆ 更新」弹窗直接看到。

## 激活码体系（v2.5.7）

### 格式
- `XXXX-XXXX-XXXX`（12 位字母数字，三段）
- 输入：tkinter 子进程三框弹窗（防 IME 崩溃，2026-06-16 替代原 LineEdit）
- 容错：用户可不带横线输入，自动格式化 `DDDDDDDD0002` → `DDDD-DDDD-0002`
- 校验：`isascii() and isalnum()` 双重拦截，中文/符号无法穿透
- FC 归一化：`_normalize(code)` → 去横线 + 大写

### 生成
```bash
python3 tools/gen_key.py 3                # 3 个 sold 码
python3 tools/gen_key.py 1 --status unused # 1 个未使用
```

### 激活流程
1. 用户点「激活」→ tkinter 三框弹窗 → 自动大写+自动跳格 → 点「确定」
2. FC `activate` → 检查 key 状态 + 指纹 → `max_devices=1` 强制唯一
3. 成功后写本地凭证 → 显示「已激活 ✓」
4. 配置页底部错误提示（格式/无效/网络），不关闭对话框

### 停用转移
1. 配置页「停用」→ FC `deactivate` → 重置 key 为可转移状态
2. 试用期灰掉停用按钮（`is_trial=True`）
3. 新机输入同码即激活

### 支付入口
- 配置页激活码下方：「💬 联系购买: 微信 paladinpp」
- 主窗口试用天数旁同样一行
- 无自动化支付——全手动微信转账

## 更新全流程（v2.3.4+）

```
用户发现 ⬆ 更新按钮
  → 点击 → 弹窗显示更新公告（GitHub Release body）
  → 点击「立即更新」
  → 按钮变「下载中…」灰掉
  → importlib.reload(updater) 强刷新 ghproxy 链路
  → 下载 179KB（ghproxy 优先，GitHub 兜底）
  → 安装脚本自动运行（sudo osascript）
  → install_update.command --update 覆盖安装 + 保护 .env/dicts
  → 弹窗变「✅ 更新完成」
  → 用户点「关闭」
  → 重启达芬奇生效
```

### 关键实现点
- Launcher `-B` 永不生成 pyc：安装后无缓存污染
- `PYTHONUTF8=1`：zipfile/open 默认 UTF-8，中文文件名不乱码
- 出厂检验：`build_personal.sh` 内 zip 版本号硬拦截
- raw version.json（优先，含完整 history）→ jsdelivr CDN → ghproxy → GitHub Releases API（兜底）
- release body = 用户看到的更新公告

60 处 UI 控件全部引用这些常量，不再散落魔法数字。

## 已知踩坑（2026-06-16 更新）

| 坑 | 表现 | 解法 |
|----|------|------|
| LineEdit + CJK 输入法 | 达芬奇 SIGSEGV 闪退（`FindLocalObject`） | 用 osascript `display dialog` 或 tkinter 子进程替代 |
| `"中".isalnum()=True` | 中文穿透 tkinter 校验 | 双重拦截 `isascii() and isalnum()` |
| osascript 单引号 `\n` | 弹窗显示原始 `\n` 字符 | 用 `$'...\n...'` 或 Python f-string 拼接 |
| subprocess.run 阻塞 | 按钮连点排队（N 次 = N 个弹窗） | `Enabled=False` 在 `try` 前，`finally` 恢复 |
| `_write_env.py` URL ≠ `license.py` 默认值 | 新用户请求发到错的 FC | 全项目 grep 统一（2026-06-16 从 `license-yqvhkhvhgf` → `license-node-mtqaghwijy`） |
| GitHub Release 中文文件名 | 资产名截成 `_` | 更新包固定 ASCII 名 `update_latest.zip` |
| 百度网盘下文件夹 | Unix +x 权限丢失 | zip 分发（Archive Utility 保留权限） |
