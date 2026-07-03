---
name: 批量命名开发
description: 批量文件命名工具开发上下文——字段配置、审查模式、导出 Excel、媒体播放、打包分发。当裁缝老师要加/改字段、修改命名规则、扩展 UI 功能时自动激活。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
agent_created: true
---
# 批量命名工具开发

触发词：改名、字段、规则、联动、命名、renamer、审查、预览、导出、excel、播放、缩略图、ffmpeg

## 文件结构（2026-07-03 更新）

```
批量命名工具/               # 原版 v3.6 — 通用8字段
├── renamer_web.py          # Python 后端（from shared.naming）
├── app_table.css            # 表格版 CSS
├── app_table.js             # 表格版 JS（APP_VERSION 版本号唯一来源）
├── renamer_table.html       # 表格版 HTML 模板
├── _splice.py               # CSS+JS+HTML 拼接 + version_info.txt 自动生成
├── build.sh                 # macOS 打包（ditto + which ffmpeg）
├── build_win.bat            # Windows 打包（py -3.11 + onefile）
├── app_icon.icns / .ico     # macOS/Windows 图标
└── card/                    # 卡片版（备用，不常规构建）

批量命名工具_创壹特供版/     # 创壹特供版 v1.1 — 独立代码库，9字段
├── renamer_web.py           # Python 后端（from shared.naming_createone）
├── app.js / app.css / renamer_web.html  # 仅表格版，无卡片版
├── _splice.py / build.sh / build_win.bat
└── shared → ../shared       # 共享库符号链接
```

## 命名规则单一来源

`shared/naming.py` 的 `FIELD_CONFIG` — 所有命名逻辑的唯一入口。
`shared/naming_checks.py` — 检查函数（零字节/双扩展名/大小异常）。

### 命名格式

```
Ep{ep}_Sc{sc}_Gr{gr}_Tk{tk}_{desc}_{method}_{author}_v{ver}_{status}.ext
   ↑     ↑     ↑     ↑      ↑        ↑        ↑      ↑      ↑
  集数  场次  小场次  次数  镜头描述  制作方式  制作者  制作批次  通过情况
```

字段顺序由 `FIELD_CONFIG` 决定：`ep → sc → gr → tk → desc → method → author → ver（制作批次）→ status`。

### FIELD_CONFIG 实际结构（原版）

```python
# shared/naming.py — 原版 9 字段
FIELD_CONFIG = [
    {"key":"ep",     "name":"Ep",  "label":"Ep 集数",   "def":"","regex":r"^\d{2,3}$","hint":"01"},
    {"key":"sc",     "name":"Sc",  "label":"Sc 场次",   "def":"","regex":r"^\d{2,3}$","hint":"01"},
    {"key":"gr",     "name":"Gr",  "label":"Gr 小场次", "def":"","regex":r"^\d{2,3}$","hint":"01"},
    {"key":"tk",     "name":"Tk",  "label":"Tk 次数",   "def":"","regex":r"^\d{2,3}$","inc":True,"hint":"01"},
    {"key":"desc",   "name":"",    "label":"镜头描述",   "def":"","hint":"由制作方式决定"},
    {"key":"method", "name":"",    "label":"制作方式",   "def":"","dv":["请选择","智能分镜版","双轨版","角色专属版"]},
    {"key":"author", "name":"",    "label":"制作者",     "def":"","hint":"请输入姓名"},
    {"key":"ver",    "name":"v",   "label":"制作批次",   "def":"01","regex":r"^\d{2,3}(\.\d+)?$","hint":"01"},
    {"key":"status", "name":"",    "label":"通过情况",   "def":"","dv":["请选择","OK","KP","NG"]},
]
```

**创壹特供版**字段不同：`shared/naming_createone.py` — `shot` 替代 `gr`，`type` 替代 `method`，9 字段 `ep/sc/shot/tk/desc/type/author/ver/status`。desc 无 method 联动。type 决定 AIVID/AIPIC 展示逻辑。

### 两版差异速查

| 特性 | 原版 | 创壹特供版 |
|:--|:--:|:--:|
| 命名模块 | `shared/naming.py` | `shared/naming_createone.py` |
| 字段 | ep/sc/**gr**/tk/desc/**method**/author/ver/status | ep/sc/**shot**/tk/desc/**type**/author/ver/status |
| desc 联动 | DESC_TO_METHOD + FIELD_RULES | 无联动（type 决定） |
| build_folder | ✅ `naming.py` | ❌ |
| _EMPTY_KEYS 动态推导 | ✅ | ✅ |
| version_info 自动生成 | ✅ `_splice.py` | ✅ `_splice.py`（2026-07-02 同步） |
| 审查模式 video/desc | method 下拉联动 desc | AIVID 只读「视频无需描述」 |
| 打包 | ditto macOS + 分号 Windows | 同左 |

`name` 非空用作前缀（Ep/Sc/Gr/Tk/v），`name` 为空只参与拼接不输出前缀。

### 文件名生成

`build_filename(fields)` 遍历 `FIELD_CONFIG`，用 `fd["name"]` 作前缀（Ep/Sc/Gr/Tk/v），拼接成字符串。method/author 和 status 参与文件名完整拼写。

### 文件名解析

`parse_filename(path)` 两段解析：
1. **主正则** `FILENAME_RE`：从 `FIELD_CONFIG` 自动生成（`_build_filename_re`），匹配全部字段。desc 前瞻断言动态计算其后到 v 之间的字段数。
2. **Fallback** `FALLBACK_RE`：只匹配 `Ep/Sc/Gr/Tk` 前缀 + `v/status` 后缀。中间不拆 desc/method/author。
3. method 由 desc 反查 `DESC_TO_METHOD`。desc 为空时跳过推断。

### 改字段顺序

只改 `FIELD_CONFIG` 一处。`build_filename`、`_build_filename_re`（含 desc 前瞻断言）、`parse_filename` 全部自动跟随。重建 `build.sh table` 即可。

### 容错设计

- 含下划线的 desc 会被贪婪截断——不拆 method/author
- 缺字段旧文件名 → fallback 解析 prefix+suffix
- 完全无法解析（如 `测试用.mp4`）→ 返回 None，字段全空

## 去重系统（2026-05-24 终版）

- `seen_fp`：`_process_paths` 局部变量，size + 前 64KB MD5，**仅本批**。类级变量跨批泄漏是系统性反模式——绝不再用。
- JS 侧：`fp || path` 优先级，`result.duplicates` 优先于本地重算
- WKWebView 双火 drop 事件 → 不防抖，靠局部 `seen_fp` 自然去重

## 字段赋值（`_process_paths`）

```
if parsed and k in parsed → 使用解析值
elif k in _EMPTY_KEYS    → 强制 ""
else                      → fd["def"]
```

`_EMPTY_KEYS = {fd["key"] for fd in FIELD_CONFIG if fd.get("name")}`。动态从 `FIELD_CONFIG` 提取所有有 `name`（前缀）的字段——加新带前缀字段自动跟进，不手写。解析失败的文件全部留空，不继承 `_saved_defaults`。

## 构建

### macOS
```bash
bash build.sh table    # 表格版（默认）→ 桌面 批量命名工具-表格版.app
bash build.sh          # 卡片版 → 桌面 批量命名工具-卡片版.app
```
- 用 `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`（python.org 安装版，有 PyInstaller）
- 用 `ditto` 原子替换桌面 app（避免 `cp -R` 嵌套 + SIP 权限）
- 自动 git commit + node check + 验证 CSS/JS 嵌入

### Windows
```cmd
build_win.bat table    # 表格版（默认）
build_win.bat card     # 卡片版
```
- `--add-data` 用分号分隔
- `--hidden-import webview.platforms.edgechromium`

### 拼接预览
```bash
python3 _splice.py table    # 输出 _build/renamer_table.html
python3 _splice.py          # 默认表格版 — 输出 _build/renamer_table.html
python3 _splice.py card     # 输出 _build/renamer_web.html
```

### _splice.py 嵌入机制

HTML 模板含两个占位符：
```html
<style>/* CSS_PLACEHOLDER */</style>
<script>// JS_PLACEHOLDER</script>
```

`_splice.py` 读取 CSS + JS 全文 → `str.replace` 注入占位符 → 注入 git hash（`APP_GIT_HASH`/`APP_BRANCH`/`APP_BUILD_TIME`）→ **从 JS 提取 `APP_VERSION` 自动生成 `version_info.txt`** → 写 `_build/`。PyInstaller 只打包拼接后的单文件。

**版本号唯一来源**：`app_table.js` 第 1 行 `const APP_VERSION='x.y'`。改版只改此处，splice 自动同步 version_info.txt，HTML 运行时注入。不再需要手动改 4 处。

**默认表格版**：`python3 _splice.py` 裸跑走表格版。传 `card` 走卡片版。build.sh 始终显式传参。

### build 失败排查

| 症状 | 检查 |
|------|------|
| CSS/JS 未嵌入 | `_build/renamer_table.html` 是否生成？占位符是否被替换？card/ 下三文件存在？ |
| node check 报错 | `node --check app_table.js` 看具体行号 |
| PyInstaller 失败 | 系统 Python 有 PyInstaller？`pip install pyinstaller` |
| 桌面 app 打不开 | `open -a Console` → 搜 crash report；或终端直接运行 `./app.app/Contents/MacOS/批量命名工具` 看 stderr |

## 表格版 UX 规则

| 规则 | 说明 |
|------|------|
| 纯粹性 | 不加面板、不加侧栏、不加额外按钮。纯粹电子表格。 |
| 双击编辑 | `click.detail >= 2`，不是自制 timer |
| 列宽 | `table-layout:fixed`，`col-desc` 149px，`col-base` 80px，其余 60-66px |
| 对齐 | 所有列 `text-align:left` |
| 字号 | 表头 10.5px，数据 13px，统一 `var(--tbl-cell)` 色 |
| 表头 | 序号/缩略图/Ep 集数/Sc 场次/Gr 小场次/Tk 次数/镜头描述/制作方式/制作者/制作批次/通过/原文件名 |
| 行完成度 | `::before` 伪元素圆点：绿（满）/黄（缺）/红（空） |
| 空单元格 | `.empty{background:#2d1212}` |
| 归档行 | `.archived{opacity:.45}` |

## 拖拽排序（2026-07-03 新增）

**实现**：鼠标事件（`mousedown` on col-num + `mousemove` + `mouseup`），不用 HTML5 DnD。pywebview 原生文件拖放拦截 `dragover`——与 Tauri 同病。

| 操作 | 效果 |
|------|------|
| `mousedown` on `col-num` | 取 `tr.dataset.index` → 升起 ghost 行（`position:fixed` + `opacity:.85`） |
| `mousemove` | ghost 跟鼠标 + `elementFromPoint` 找目标行 → 插入蓝色 placeholder |
| `mouseup` | `files.splice` → `reindex` → **只移 DOM 节点不重绘整表** |

约束：
- **placeholder td 必须 `border:none!important`**：`tbody td{border-bottom:1px}` 会污染。
- **显式列宽**：从真实行 `cells[c].offsetWidth` 取宽设给 placeholder。
- **拖拽清排序**：`_sortKey=null` 避免后续加文件被重排。
- **拖拽清选择**：`sel.clear()` ——索引全变了。
- **lazy undo clone**：只在成功 drop 时 `files.map()`。
- **归档行不可拖**、右键菜单+拖拽冲突已处理。
- **审查面板开着时**：overlay 全覆盖，拖拽不会触发。

## TK 设计决策（2026-07-03）

TK 不手写，纯自动编号。拖拽排序是 TK 唯一控制手段。`buildTK(i)` 遍历 `files[0..i]` 按分组键计数。

## 图片缩略图（2026-07-03 新增）

最优路径：
```
Image.open(filepath) → ImageOps.exif_transpose → thumbnail(LANCZOS,120,120) → RGBA/P→RGB → BytesIO.save(JPEG,q80) → base64 → setThumb
```
- 直接文件句柄（不读全文件），SMB 性能与视频持平
- EXIF 自动旋转、RGBA 透明转 RGB
- 不写临时文件（BytesIO 直接编码）

## 字段校验

`DIGIT_STRICT`——定义在 `app_table.js` 顶部：
```javascript
const DIGIT_STRICT = {
  ep: /^(0[1-9]|[1-9]\d{1,2})$/,
  sc: /^(0[1-9]|[1-9]\d)$/,
  gr: /^(0[1-9]|[1-9]\d)$/,
  ver: /^(0[1-9]|[1-9]\d)(\.\d)?$/
}
```
校验位置：`commit` 函数内 + `blur` 事件。00 必拦。失败退旧值不留输入框。

## DESC_TO_METHOD 联动（原版专用）

`shared/naming.py` 顶部常量——desc 到 method 的推断映射。**创壹特供版无此特性**（type 字段替代 method）。

```python
DESC_TO_METHOD = {"智能分镜": "智能分镜版", "幽灵角色": "双轨版", "空镜": "双轨版"}
# 默认 fallback: "角色专属版"
```

### FIELD_RULES（desc←method 反向控制，原版专用）

```python
FIELD_RULES = [{"trigger":"method", "targets":["desc"], "map":{
    "智能分镜版": {"desc":{"locked":"智能分镜"}},
    "双轨版":     {"desc":{"dropdown":["请选择","智能分镜","幽灵角色","空镜","请手动输入…"]}},
    "角色专属版": {"desc":{"dropdown":["请选择","智能分镜","请手动输入…"]}},
}}]
```

表格版：`onMethodChange` 批量写选中行 → `renderList(true)` → desc 格 0.35s 黄底高亮闪烁。

## 新增字段 — 端到端 7 步

改 `FIELD_CONFIG` 一处后，必须同步以下 7 处：

| # | 位置 | 改什么 |
|---|------|------|
| 1 | `shared/naming.py` | `FIELD_CONFIG` 添加字段 dict |
| 2 | `renamer_web.py` | `_EMPTY_KEYS` 是否需要加入新 key |
| 3 | `app_table.js` | `DIGIT_STRICT` 是否需要新增校验规则 |
| 4 | `app_table.css` | 新增 `col-{key}` class + 列宽 + 对齐 |
| 5 | `renamer_table.html` | 表头 `<th>` 新增列 |
| 6 | `renamer_web.py` `_process_paths` | 验证赋值逻辑不继承错误默认值 |
| 7 | `app_table.js` L1 | **版本号唯一来源**（`APP_VERSION`），splice 自动生成 `version_info.txt` |

每改完一步 `build.sh table` 构建验证。

## 日志系统

- `_process_paths`：`_log.debug` 逐文件（`basename parsed=bool ep= sc= gr= desc|method|author|v|status`）
- `_process_paths` 汇总：`_log.info`（`{N} files, {M} parsed, {K} raw, {D} dup`）
- `do_rename` / `do_archive`：逐文件 `✓ 原名 → 新名`
- `result()`：加 `call('debug_log', ...)` 确认持久结果写入

## TK 自动计算（2026-07-03 更新：不手写）

JS 侧 `buildTK(i)` 遍历 `files[0..i]` 按分组键 `(ep,sc,gr,desc,method,ver)` 计数——拖拽排序是 TK 唯一控制手段。

归档时扫描目标文件夹：用 `tk='00'` 构建模板 → `split('_Tk00_', 1)` 切出前缀 → `startswith(tk_prefix)` 匹配同组文件 → 正则提取最大 TK 号 +1。

关键约束：
- **只用 `startswith`**，不用 `endswith`（desc 后缀可能误匹配，如"智能分镜" vs "某某智能分镜"）
- **无 fallback**——旧版 `replace('??','')` 回退逻辑已删除。`split` 失败 = `max_tk=0`，安全
- 同组定义：Ep/Sc/Gr/desc/method/author/ver/status 全部相同（非仅 desc）

## 归档路径结构

```
root/EP{ep}/V{ver}/EP{ep}_SC{sc}_v{ver}/file.mp4
```

- `build_folder()` 在 `shared/naming.py`（v3.6+，原版专用）。三阶段路径：EP 层 → V（制作批次）→ compound 子文件夹
- **去掉制作方式**（v3.6.1）：文件夹名不再含 `_{method}`，`EP01_SC01_v01/` 而非 `EP01_SC01_智能分镜版_v01/`
- ver 字段 UI 标签：「版本号」→「制作批次」（v3.6）
- TK 正则修复（v3.6.1）：`\bTk` → `_Tk`（`\b` 在 `_` 后不匹配，TK 扫描始终归零）

## 归档预扫描

`do_archive` 开始前置步骤：遍历目标文件夹建 `{hash: path}` 映射，同内容文件只归档一次。

- **上限 200 文件**：`len(seen) >= 200` 停止扫描，防大目录性能问题
- **异常安全**：`except OSError`，不吞 `KeyboardInterrupt`/`SystemExit`

## 测试

```bash
# 冒烟测试（25+ 项），直接 import 项目模块运行
python3 -c "
import sys; sys.path.insert(0,'.')
import importlib
for m in ['shared.naming','shared.naming_checks']:
    importlib.import_module(m)
print('✅ 模块加载通过')
"
```

## pywebview 特殊约束

- `if(!window.pywebview)` 在注入前检查不可靠 → 用 `setTimeout + 再判断`
- `el.focus()` 不一定触发 WKWebView 原生 focus 事件
- `click.detail >= 2` 比自制 timer 可靠
- WKWebView 会双火 drop 事件 → 不防抖，靠局部 `seen_fp`
- 全量 `innerHTML = ''` 重建 DOM 容易崩溃 → 增量渲染

## 代码审查

| 规则 | 说明 |
|------|------|
| FIELD_CONFIG 单一来源 | 改字段只改一处 |
| 新字段 7 处同步 | naming.py / _EMPTY_KEYS / DIGIT_STRICT / CSS / HTML表头 / _process_paths / 版本号 |
| seen_fp 局部变量 | 不在类体或全局——跨批泄漏是系统性反模式 |
| build 通过 | macOS `ditto` + Windows 分号 `--add-data` |

详见 `达芬奇代码审查` skill 的 R/S/N 主规则。批量命名是 pywebview 标准项目——通用打包/分发/签名模式见 `独立应用开发` skill。

## 版本管理（v3.1 计划，未实施）

> 以下为历史规划，当前未部署。在线自更新方案待重新评估。

OSS bucket `renamer-dist` 存 `renamer_version.json` + ZIP。app 启动检查版本 → 兼容双平台自更新。build.sh 上传自动化。详见 `TODO.md`。

## 多选编辑

多选后编辑文本字段（ep/sc/gr/ver/author/desc），即使发起行的当前值 = 输入值，也对该字段的所有选中行写入。下拉菜单不受影响（同值不触发 change 事件）。方法选择走独立 `onMethodChange` 逻辑。

**反模式**：`finalVal !== oldVal` 用发起行的 oldVal 判断是否写入全部选中行 → 行间值不一致时其他行被跳过。

## 调试日志按钮

右上角 `📋`，点击复制全部 JS `debug_log` 到剪贴板。Python 侧 `_dbg_buf` 存最近 500 条。远程排障一步到位。

## 导出 Excel（openpyxl）

收到 `export_table(rows)` → 生成 xlsx → 返回 base64 → JS 调用 `save_file` 弹出原生保存对话框。

| 要点 | 说明 |
|------|------|
| 库 | `openpyxl`，不要手拼 XML（inlineStr 在 macOS 不兼容） |
| 缩略图 | `XLImage` + 读 PIL 实际尺寸算比例，`add_image` 锚定到单元格 |
| 补零 | EP/SC/TK/V 存为文本（`zfill(2)`），不能存 int（丢前导零） |
| 扩展名 | 从实际文件读 `f.ext`，不靠 type 推断 |
| 对话框 | `_window.create_file_dialog(webview.SAVE_DIALOG)` — 原生 macOS 保存面板 |
| 依赖 | `build.sh` 加 `--hidden-import openpyxl --hidden-import openpyxl.drawing.image` |

## ffmpeg 打包

| 要点 | 说明 |
|------|------|
| 打包 | `--add-binary "$(which ffmpeg || echo /opt/homebrew/bin/ffmpeg):."` + ffprobe 同理 |
| 运行时发现 | 优先 `os.path.join(sys._MEIPASS, 'ffmpeg')`，找不到再降级系统路径 |
| 原因 | 用户不一定装了 ffmpeg，缩略图和元数据会缺失 |

## 审查模式（2026-05-28 新增）

单击缩略图或空格键（有选中时）→ 全屏弹窗预览 + 全字段编辑。视频/图片均支持。

| 要点 | 说明 |
|------|------|
| 入口 | 单击缩略图 + 空格键（有选中时打开第一个）。不再双击 |
| × 按钮 | 放在 titlebar 左侧文件名旁，不用 emoji |
| Prev/Next | `navReview` 原地替换内容不关弹窗（避免闪烁） |
| 字段编辑 | 内联 input + 自动保存 + blur 补零 + `updateReviewTitle` 实时刷新标题 + `updateReviewMeta` 刷新完成度 |
| 完成度 | 元数据区 `filled/total 就绪`（绿满/黄缺）+ 输入框 `rf-filled` 绿色边框 |
| 表格同步 | `setReviewStatus` / `closeReview` / `navReview` 必须 `renderList(true)` 强制重建 |
| 关闭 | × / ESC / 点击遮罩 |

### 媒体播放

| 要点 | 说明 |
|------|------|
| 视频加载 | JS API `get_media_data` → base64 → Blob URL。不用 bottle 静态文件或 `file://` URL |
| WKWebView | `<video playsinline webkit-playsinline>` + CSS 不设 `display:none`（JS 管显隐） |
| 播放控件 | `video.removeAttribute('controls')` + 自定义控制栏（进度条/音量/速度/逐帧/全屏/截图） |
| 快捷键 | Space 暂停、← → 跳 2 秒、`, .` 逐帧、J 减速 K 暂停 L 加速、Ctrl+← → 切文件 |
| 点击播放 | `video.onclick = togglePlay` |
| 状态按钮 | OK/KP/NG 三大按钮高亮切换，快捷键已移除（与 JKL 冲突） |
| 清理 | `closeReview` / `navReview` 时 `URL.revokeObjectURL` + `clearInterval(_rcInterval)` + 事件监听器清理 |
| 事件去重 | `initReviewControls` 用 `ctrls._init` 标记 + 存储 `_ontu/_onend` 引用 → remove 后再 add |
| 异步过滤 | `_metaGen` 计数器：`loadMediaMeta` 回调检查 `_generation` 过滤过期导航结果 |

### 元数据

| 要点 | 说明 |
|------|------|
| 来源 | ffprobe（优先 bundle 内）→ 分辨率/帧率/编码/时长 |
| 降级 | ffprobe 不可用时降级 HTML5 `loadedmetadata` 事件 |

## 导出 Excel 列决策

| 规则 | 说明 |
|------|------|
| 不要序号 | 表格序号是显示层概念，导出不保留 |
| 不要原文件名 | 用户要的是新命名结果 |
| 要缩略图 | `XLImage` + PIL 实际尺寸比例 + `ws.add_image` |
| 要新文件名列 | 格式同 `build_filename(fields)`，扩展名从实际文件读 |
| 补零 | EP/SC/GR/TK/VER 存为文本 (`zfill(2)`) |
| 按钮文字 | 中文无 emoji：`导出为表格` |

## 开发阻断项（实际触发过）

| 规则 | 说明 |
|------|------|
| **tk 不能参与必填校验** | `buildTK(i)` 运行时计算，`files[i].fields.tk` 始终为空。`updButtons` 读 `fieldKeys`（从 FIELD_CONFIG 动态推导）做必填检查，tk 通过 `fieldKeys` 配置排除 |
| **文件名分隔符必须文件系统兼容** | 多镜 SH 用 `/` 串联 → `os.rename` 把它当路径分隔符。用 `-` 或 `_` |
| **RGBA PNG 不能直接存 JPEG** | `img.save('JPEG')` 报错。提前 `img.mode=='RGBA'` → `convert('RGB')` |
| **`<th>` 默认 `text-align:center`** | 不设 `text-align:left` 表头偏中，和左对齐数据列不一致 |
| **数字 blur 补零排除 0** | `padStart(2,'0')` 把 "0"→"00" → 无意义。加 `parseInt>0` 守卫 |

## 内联多值编辑器（已移除）

旧版多镜号 `[+][-]` 编辑器已在当前代码中删除。审查模式中字段编辑统一走内联 input，不再有独立的多值编辑面板。

## 石家庄交叉同步

石家庄团队也在维护这套代码，会通过 zip 发回改动。接包时严格执行：

1. **不假设「全量替换 = 全部对齐」**——文件覆盖不等于每行改动都落仓。必须用 `git diff` 逐文件和改动记录对照。
2. 对照清单：`app_table.js` / `renamer_web.py` / `app_table.css` / `build_win.bat` — 这四个是高频改动点。
3. 发现漏项立即补（2026-06-04 教训：CSS overlay、CREATE_NO_WINDOW 两处修复在「全量替换」后仍缺失）。
4. 双方改动合并后必须 `build.sh table` 冒烟验证。
