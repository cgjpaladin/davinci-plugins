# 达芬奇插件工坊 — 代码审查标准与流程

> 版本 2.4 | 2026-05-10 | 新增交付自检工具专属规则（R7/S10/S11）

---

## 一、业务背景（决定一切规则的上下文）

审查规则不能脱离业务现实。以下是每一项规则被制定的原因：

| 业务现实 | 含义 |
|----------|------|
| **20台 Mac mini 同时剪辑** | 所有文件操作必须 SMB 并发安全。踩过的坑：ReplaceClip 被其他用户锁定媒体池 |
| **剪辑师零技术背景** | 失败信息必须进 UI（不能只写 SMB 日志）。日志双向：SMB给运维 + UI给用户 |
| **全国几千个剪辑师零 pip** | 只能用 Python 标准库。加一个 `import requests` = 全国几千台机器全部挂 |
| **达芬奇内建 Python 3.6+** | 不能用 f-string debug（3.6支持但3.13环境差异大）、不能用 match-case（3.10+） |
| **短剧量产，按秒计费** | 计费代码的bug = 直接经济损失。1个片段多算0.5积分，1000个=¥4.55 |
| **达芬奇 API 不稳定** | GetClipProperty 返回None、ReplaceClip 静默失败、TimelineItem≠MediaPoolItem |
| **灰度发布三梯队** | 本地→灰度(1台)→全量(20台)。代码变更影响面大，回滚必须有路径 |

---

## 二、审查分级（绑定业务影响）

```
🔴 阻断项 → 合入就出生产事故，必须修
🟡 建议项 → 长期会出问题，有合理豁免理由可放过
💭 优化项 → 更好但不急，不阻塞合并
```

---

## 三、审查清单（每项绑定真实场景）

---

### 🔴 阻断项 — 生产事故级

#### R1. 零 pip 依赖

**业务原因**：达芬奇内建 Python 没有 pip，没有 requests/httpx/aiohttp。剪辑师机器上不可能手动装包。加了就全国几千台全挂。

**检查方式**：grep 以下模式，命中即阻断
```
import requests       # ❌
from requests import  # ❌
import aiohttp        # ❌
import httpx          # ❌
import urllib3        # ❌
```

**正确做法**：全部用 `urllib.request` + `urllib.error`，本项目 adapters 已全部实现：
```python
# ✅ ghostcut.py / wuhenai_v2.py — 纯 urllib 手写 multipart + OSS签名
req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
    return json.loads(resp.read().decode("utf-8"))
```

**当前状态**：✅ 全部合规。pre-commit 自动拦截。

---

#### R2. SMB 并发安全

**业务原因**：20台 Mac mini 同时往 `/Volumes/MYJC/` 读写。实际发生过「ReplaceClip 被其他用户锁定媒体池」的线上故障。

**三个硬要求**：

**(a) 写入操作原子化**
```python
# ✅ 正确 — ledger.py 的 JSONL 追加模式
# SMB 上 open(f, "a").write(一行 + "\n") 是原子的
with open(_ledger_file, "a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")

# ✅ 正确 — ledger.py maybe_cleanup() 的原子替换
# 先写临时文件，再 os.replace()（原子 rename），不是先删后写
with open(tmp, "w") as f:
    for r in kept:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
os.replace(tmp, _ledger_file)  # 原子操作
```

**(b) 并发锁有超时 + 自动回收**
```python
# ✅ 正确 — subtitle_state.py 的 os.mkdir 原子锁
# mkdir 在 SMB 上是原子操作，两人同时建同名目录只有一个成功
_LOCK_TTL = 600  # 10分钟自动过期，防止崩溃残留
# 回收条件：同机IP → 立即回收；超时>10分钟 → 自动回收
```

**(c) SMB 写入加固（随机抖动 + 重试）**
```python
# ✅ 正确 — ops_logger.py 的 SMB 写入
for attempt in range(3):
    try:
        time.sleep(random.uniform(0.001, 0.05))  # 1-50ms 随机错峰
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        break
    except (IOError, OSError):
        if attempt < 2:
            time.sleep(0.3 * (attempt + 1))  # 指数退避
```

**当前状态**：✅ ledger/subtitle_state/ops_logger 三个模块已实现完整并发安全。新模块必须同等级别。

---

#### R3. ReplaceClip 三段式 + 颜色陷阱（下载→校验→替换→恢复颜色）

**业务原因**：ReplaceClip 是达芬奇最不稳定的 API。静默失败（返回True但没替换）、锁冲突（其他用户占用媒体池）、路径不一致。必须三段式防御。

```python
# ✅ 正确模式 — core.py download_and_apply() 的完整流程

# 第1段：下载
urllib.request.urlretrieve(result.output_path, dl)

# 第2段：校验（文件存在 + 大小>0），不合格不替换
if not os.path.exists(dl) or os.path.getsize(dl) == 0:
    fail_list.append({"name": name, "error": "下载文件为空或不存在"})
    release_lock(name)
    continue  # ← 关键：不执行 ReplaceClip

# 第3段：替换 + 验证 + 降级
try:
    replaced = mp_item.ReplaceClipPreserveSubClip(dl)
except Exception:
    replaced = False
    _smb_log(f"[core] ReplaceClip 异常（可能被其他用户锁定媒体池）: {name}")

# 降级策略：无论 ReplaceClip 是否成功，下载已完成就记入账本
# 下次可以直接缓存命中，不需要重新下载
ledger.record_completed(fn, output_path_for_ledger, ...)
```

**也适用于非 ReplaceClip 的文件写入**：
```python
# ❌ 错误 — 先删后写（删成功了写失败了 = 数据丢失）
os.remove(path)
with open(path, "w") as f:
    f.write(data)  # 写失败了？文件已经没了

# ✅ 正确 — 先写临时文件再原子替换
with open(path + ".tmp", "w") as f:
    f.write(data)
os.replace(path + ".tmp", path)  # 原子：只有写成功才替换
```

**当前状态**：✅ `download_and_apply` 已正确实现三段式。⚠ `subtitle_state.py` 的备份轮转用 copy2 而非原子操作，低风险（备份丢失不影响主流程）。

**🆕 ReplaceClip 颜色陷阱（v2.3 补充，MEMORY#16）**：
`ReplaceClip` 会重置同一 MediaPoolItem 的**所有** TimelineItem 颜色。同文件多段时，去重跳过的片段也必须在 ReplaceClip 后恢复颜色。
```python
# ✅ — core.py 通过 ClipEntry.alt_tl_items 收集并批量恢复
for alt in clip.alt_tl_items:
    try:
        alt.SetClipColor("Orange")
    except Exception:
        _smb_log(f"颜色恢复失败: {name}")
```

---

#### R4. API 计费准确

**业务原因**：短剧量产，100集×10个片段=1000次API调用。计费bug哪怕每次差0.5积分，就是500积分=¥4.55。这是直接经济损失。

**检查点**：
- [ ] 新计费模型有测试覆盖（`pricing.py` 的 `estimate_cost` 有对应 test case）
- [ ] 计费单位取整方向正确（`math.ceil` 不是 `round` 或 `int`）
- [ ] `point_to_yuan` 汇率与飞书文档/供应商官方定价一致
- [ ] 计费逻辑改了之后更新 `test_estimate_cost` 的期望值

```python
# ✅ 正确 — pricing.py
# 按秒计费，向上取整（1.1秒=2秒计费）
total_units = sum(math.ceil(t.duration) for t in tasks)
total_points = math.ceil(total_units * unit_cost)

# ❌ 错误 — 如果用了 round 或 int
total_units = sum(int(t.duration) for t in tasks)  # 1.9秒→1秒，少算
```

**当前状态**：✅ `pricing.py` 计费逻辑正确，有 `test_estimate_cost` 覆盖。⚠ OSS 费用追踪（`oss_tracker`）的 `traffic_cost` 用了忙时单价 0.50，实际可能闲时 0.25，多估算不造成损失但日志数据不精确。

---

#### R5. 达芬奇 API 判空（每次调用）

**业务原因**：达芬奇 API 返回值不稳定。`GetCurrentProject()` 在协作模式下可能返回 None（PostgreSQL 断开时）。`GetClipProperty("Frames")` 经常返回 None 或 ""。不判空 = Crash 给 20 个人看。

```python
# ✅ 正确 — 每次判空 + 默认值
project = resolve.GetProjectManager().GetCurrentProject()
if not project:
    raise RuntimeError("请先打开一个项目")  # ← 明确报错，用户能理解

frames = int(mp_item.GetClipProperty("Frames") or 0)   # None→0
fps = float(mp_item.GetClipProperty("FPS") or 24)       # None→24

# ❌ 错误 — 不判空
frames = int(mp_item.GetClipProperty("Frames"))  # None→TypeError crash
fps = mp_item.GetClipProperty("FPS")             # None→后续除零
```

**达芬奇 API 已知不稳定点**：
| API | 风险 | 当前处理 |
|-----|------|---------|
| `GetCurrentProject()` | 协作模式下可能None | ✅ `connect_resolve()` 判空抛异常 |
| `GetClipProperty("Frames")` | 经常返回None/"" | ✅ `get_video_duration()` or 0 |
| `GetClipProperty("FPS")` | 可能返回None | ✅ or 24 |
| `GetClipProperty("File Path")` | SMB断连时返回空 | ✅ `scan_io_clips` 判空跳过 |
| `ReplaceClipPreserveSubClip()` | 静默失败/异常 | ✅ `download_and_apply` try/except |
| `SetClipColor()` | 协作模式下偶发异常 | ✅ try/except + _smb_log |
| `GetMarkInOut()` | 可能返回None | ✅ `get_io()` 返回(0,0)兜底 |

**当前状态**：✅ `core.py` 所有达芬奇API调用已判空。新代码必须同等对待。

> 📖 完整坑位清单见：`达芬奇学习资料/达芬奇API已知坑位.md`（8个不稳定API + 修复模式 + 自检流程）

---

#### R6. API 密钥安全

**业务原因**：无痕AI密钥有余额（¥1000+）。泄露到 git = 任何人都能用裁缝老师的钱调API。

```python
# ✅ 正确 — 从环境变量读取，留空
WUHENAI_V2_API_KEY = os.environ.get("WUHENAI_V2_API_KEY", "")

# ❌ 阻断 — 任何形式的硬编码
api_key = "sk-abc123..."  # 直接阻断
```

**.env 加载顺序**（业务定制，非通用模式）：
```
1. {PLUGIN_DIR}/.env          → 本地开发（优先）
2. /Volumes/MYJC/.../.env     → SMB团队共享（生产机与第1条同路径）
3. ~/.subtitle.env            → 个人备用（SMB断连时兜底）
4. ~/.watermark.env           → 旧名兼容
```
先加载的优先，后加载不覆盖已有 key。这是为了让裁缝老师的开发机可以用自己的测试密钥，不影响生产机用团队密钥。

**当前状态**：✅ `config.py` 已正确实现。`.env` 在 `.gitignore`。pre-commit 自动扫描硬编码密钥。

---

#### R7. CHECKS 注册表完整性（v2.4 新增 — 交付自检工具专属）

**业务现实**：交付自检工具的 30+ 检查项通过 `CHECKS` 注册表驱动，布局从 CHECKS 自动生成。CHECKS 中缺失 `group` 字段的项不会被渲染到 UI，用户看不到。

**审查规则**：
- CHECKS 中 `run_fn` 不为 `None` 的每项 MUST 有 `group` 字段 = 🔴
- `layout_row` 字段可选，同分组需拆多行时使用
- 新增检查时同步检查 `GROUP_ORDER` 是否包含对应分组

**检查方式**：
```python
# 模块加载时自动校验（已集成到 _validate_checks）
for c in CHECKS:
    if c.get("run_fn") and "group" not in c:
        raise AssertionError(f"CHECKS['{c['id']}'] 缺少 group 字段")
```

---

### 🟡 建议项 — 长期会出问题

---

#### S1. 异常处理：分场景对待

**业务现实**：不是所有 `except: pass` 都是坏的。需要区分三种场景。

**场景A：绝对不能吞的异常**（🔴级别）
```python
# ❌ — core.py download_and_apply() 的磁盘预检
# 当前写法（619行）：
except:
    pass  # 检查失败不阻塞

# 问题：吞掉的不只是 statvfs 失败，还可能是 MemoryError、KeyboardInterrupt
# 建议改为：
except OSError:
    _smb_log("[core] 磁盘空间预检跳过（SMB可能不可用）")
```

**场景B：故意静默的异常**（✅合格，但需要注释说明原因）
```python
# ✅ — ledger.py _append() 
except Exception:
    pass  # 账本写入失败不能阻塞主流程：宁可不记也不能让剪辑师处理中断

# ✅ — subtitle_state.py release_lock()
except OSError:
    pass  # 锁可能已被其他人清理，删不掉正常

# ✅ — ghostcut.py cancel()
except Exception:
    pass  # 取消API不存在，异常预期内，上层有兜底
```

**场景C：应该传播的异常**（缺失）
```python
# 当前缺失：达芬奇断连检测
# remove_subtitle.py 301-307 已有检查，但 core.py 的 process_single_clip 没有
# 如果 API 处理中达芬奇崩溃，不会感知到
```

**审查规则**：
- 任何 `except Exception: pass` 必须有一行注释解释「为什么吞异常」
- 没有注释的 = 🟡 建议补
- `except:`（裸except，连 BaseException 都吞）= 🔴 除非有极强理由

**当前状态**：43处裸except/泛化except，约15处是故意设计（ledger/ops_logger/锁释放），约10处缺注释，约5处应改为精确异常类型。

---

#### S2. print() vs logger：分模块对待

**业务现实**：不是所有模块都有 logger 注入条件。需要根据模块角色判断：

| 模块角色 | 日志方式 | 原因 |
|----------|---------|------|
| `core.py` 纯函数 | ❌ 不应有 print/log | 设计原则：零副作用，只返回数据 |
| `remove_subtitle.py` 编排层 | ✅ 走 `logger` 模块 | 有 CLI/UI 双模式，logger 可注入 |
| `adapters/ghostcut.py` | ✅ 可以用 print | 独立适配器，有自己的 `[GhostCut]` 前缀，且可能被替代 |
| `adapters/wuhenai_v2.py` | ✅ 走 `wuhenai_set_logger` 注入 | 有自己的日志注入机制 |
| `shared/` 库模块 | ❌ 不应 print | 被多模块引用，print 会污染所有调用者的输出 |
| `tools/` 运维脚本 | ✅ 可以用 print | 独立运维工具，直接在终端跑 |

**当前问题**：
```python
# 🟡 — ghostcut.py 全线用 print，但已带 [GhostCut] 前缀，作为独立适配器可接受
print(f"[GhostCut] 检测到本地文件，自动上传: {os.path.basename(video_url)}")

# 🟡 — wuhenai_v2.py 默认 _log = print，但提供了 wuhenai_set_logger() 注入
# UI模式下会注入 UI logger 覆盖，CLI 模式下用 print 合理
```

**审查规则**：看模块角色。core/shared 里出现 print = 🟡。adapters 里 print 带前缀 = ✅。tools 里 print = ✅。

---

#### S3. 全局状态管理

**业务现实**：达芬奇插件是「加载一次、运行多次」的模式。模块级全局变量在达芬奇 Python 环境中是持久化的（脚本重新执行时模块不会重新加载）。

**当前全局变量分级**：

| 变量 | 位置 | 风险 | 处理 |
|------|------|------|------|
| `logger._log` | shared/logger.py | 🟡 中 | ✅ `set_logger()` 注入，切换模式安全 |
| `ledger._ledger_file` | shared/ledger.py | 🟡 中 | ✅ `init()` 设置，每次处理前重置 |
| `ops_logger._log_dir` | shared/ops_logger.py | 🟡 中 | ✅ `init()` 设置 |
| `subtitle_state._state_file` | shared/subtitle_state.py | 🟡 中 | ✅ `init()` 设置 |
| `pricing.oss_tracker` | shared/pricing.py | 🟢 低 | ✅ 有 `reset()` + `threading.Lock` |
| `config.PROJECT_ROOT` | AI去字幕/config.py | 🔴 高 | ⚠ 只有环境变量覆盖，没有 setter |

**审查规则**：
- 模块级可变状态 = 🟡，必须有 `init()` 或 `reset()` 方法
- 没有 init/reset 的全局可变状态 = 🔴
- 达芬奇持久化环境的变量要考虑「第二次运行时上一次的值还在」

**当前状态**：⚠ `config.PROJECT_ROOT` 没有显式 setter。UI 模式通过用户选择来设置，但走的环境变量路径。需要确认 UI→config 的路径设置是否正确传递。

---

#### S4. 类型标注：能做就做，不能不强求

**业务现实**：达芬奇 API 对象（MediaPoolItem、TimelineItem）是 SWIG 生成的动态类型，Python 类型系统无法表达。标注成 `object` 反而降低可读性。

**标注优先级**：

```python
# ✅ 有价值 — 纯函数的输入输出类型明确
def sanitize_filename(text: str) -> str:
    ...

def estimate_cost(tasks: list, mode: str, provider: str = None) -> tuple:
    """Returns: (total_units, total_points, unit_cost, yuan)"""
    ...

# ✅ 有价值 — NamedTuple 字段注释
class ClipEntry(NamedTuple):
    mp_item: object          # MediaPoolItem（达芬奇动态类型）
    name: str                # 时间线显示名
    path: str                # 磁盘文件路径

# 💭 不强求 — 涉及达芬奇对象的函数
def scan_io_clips(timeline, clip_color: str = "Orange") -> tuple:
    # timeline 类型是 PyRemoteObject，Python 类型系统无法表达
    ...

# 💭 不强求 — 返回值是复杂 tuple
def download_and_apply(results, output_dir, mode, ...) -> tuple:
    # Returns: (success_count: int, fail_list: list, output_files: list)
    # 用文档注释代替类型标注更合适
```

**审查规则**：
- NamedTuple/dataclass 字段必须有注释 = 🟡
- 纯函数（不涉及达芬奇API对象）应该有类型标注 = 🟡
- 涉及达芬奇对象的函数不强求 = 💭

**当前状态**：✅ `core.py` 的 NamedTuple 和纯函数标注较好。⚠ `query_balance`、`post_check` 缺少返回值类型。

---

#### S5. 测试策略

**业务现实**：`tests/` 被 `.gitignore` 排除是有意设计——测试脚本包含本地路径，且需要达芬奇运行环境。但纯函数测试应该保留。

**三层测试策略**：

| 层级 | 内容 | 运行环境 | git 跟踪 |
|------|------|---------|---------|
| 纯函数单元测试 | 计费、字符串处理、路径构建 | 任何地方 | ✅ 应该跟踪 |
| 适配器集成测试 | API 调用、上传下载 | 开发机 | ✅ 可跟踪（用 mock） |
| 达芬奇冒烟测试 | IO扫描、ReplaceClip、UI | 达芬奇内 | ❌ 不跟踪（路径敏感） |

**当前问题**：`tests/` 整体被 gitignore 排除，导致纯函数测试（`test_core.py`）也没进版本控制。

```python
# 当前 test_core.py 的问题和改进：
# 现状：裸 assert，没有测试框架
assert extract_ep("EP01_g1_01_v01.mp4") == "EP01"

# 建议：用标准库 unittest（零依赖），失败时能知道哪个case挂了
import unittest
class TestCore(unittest.TestCase):
    def test_extract_ep(self):
        self.assertEqual(extract_ep("EP01_g1_01_v01.mp4"), "EP01")
        self.assertEqual(extract_ep("clip_without_ep.mp4"), "EP00")
        self.assertEqual(extract_ep(""), "EP00")
```

**审查规则**：
- 纯函数新增/修改 → 🟡 需要对应的测试用例
- 计费逻辑修改 → 🔴 必须更新 `test_estimate_cost` 期望值
- 适配器修改 → 🟡 建议加 mock 测试

**当前状态**：⚠ `tests/` 整体被 gitignore，包含有价值的纯函数测试。建议将纯函数测试移出 tests/ 或调整 gitignore 规则。

---

#### S6. 魔法数字与硬编码路径

**业务现实**：项目有大量业务相关的阈值（30秒最大片段、600秒API超时、10MB账本清理、180天保留）。这些数字都有业务含义，必须用常量。

**当前良好实践**：
```python
# ✅ config.py 已集中管理
MAX_SOURCE_DURATION = 30   # 短剧片段通常15-20秒
API_TIMEOUT = 600          # 无痕AI最长10分钟
_LOCK_TTL = 600            # 锁10分钟自动过期
_CLEANUP_SIZE_MB = 10      # 账本超10MB触发清理
_CLEANUP_DAYS = 180        # 保留最近180天
_BAK_KEEP = 7              # 状态文件备份保留7天
```

**仍需改进的硬编码**：
```python
# ✅ 已修复（v1.8.0）— wuhenai_v2.py 改用 shared/platform.py
from platform import ffprobe_path
_FFPROBE = ffprobe_path()  # 自动检测 Apple Silicon / Intel / PATH

# D1 解耦（2026-05-09）：平台路径统一到 shared/platform.py
# 未来新增路径只需改一处，不用扫全项目 grep
```

**审查规则**：
- 出现两次以上的数字 → 🟡 提取为常量
- 有业务含义的数字（超时/阈值/保留天数）→ 🟡 提取为常量并注释含义
- 路径硬编码 → 🟡 至少有一个 fallback

---

#### S7. 导入规范

**业务现实**：达芬奇插件需要运行时 `sys.path` 注入（因为脚本目录不在 PYTHONPATH）。这导致 import 顺序与标准 Python 项目不同。

**本项目约定的导入顺序**：
```python
# 1. 标准库
import os
import time
from typing import Optional

# 2. 路径注入（达芬奇特有，必须放在本地 import 之前）
sys.path.insert(0, _plugin_root)
sys.path.insert(0, _shared_root)

# 3. 本地模块
from config import DEBUG, DEFAULT_MODE
from core import connect_resolve, scan_io_clips
```

**当前问题**：
```python
# 💭 launcher.py — 逗号导入风格，仅此一个文件
import os, subprocess, sys, time, atexit, tempfile
```
launcher.py 是本地测试启动器，不在生产路径，且不会频繁修改。💭 不紧急。

**审查规则**：
- 新文件：每个 import 独占一行 = 🟡
- 旧文件（launcher.py）：不强制改，改其他东西时顺手修 = 💭
- E402（import不在顶部）豁免：达芬奇需要 sys.path 注入
- 标准库模块不要在函数内 import = 🟡（除非有明确的延迟加载理由，如避免循环导入）

**🆕 懒加载解耦模式（v2.3 新增）**：
当模块级 import 会导致循环依赖或产品耦合时，允许函数内懒加载：
```python
# ✅ — core.py query_balance() 避免模块级耦合适配器
cfg = adapter_config or deepcopy(ADAPTER_CONFIGS["wuhenai_v21"])
from adapters.wuhenai_v2 import WuhenAIV21Adapter  # 懒加载
adapter = WuhenAIV21Adapter(cfg)

# ✅ — ui_widgets.py 避免模块级 import macos_utils（非关键路径）
from macos_utils import mount_smb
```
此模式适用于：
- 适配器实例化（产品不应硬依赖具体适配器）
- macOS 工具类（非关键路径，失败可降级）
- 未来可能替换的模块
不符合时应标注原因 = 🟡。

---

#### S8. 适配器专项检查（v2.1 新增）

**业务现实**：适配器是独立可替换组件，有自己的特殊性。

| 检查项 | 说明 |
|--------|------|
| **video_path 判空** | 适配器不应假设调用者已做前置校验。`task.video_path` 可能为空（达芬奇 SMB 断连时 `GetClipProperty("File Path")` 返回空字符串） |
| **OSS 生命周期** | 上传的文件是否会被清理？预签名 URL 有效期是否足够？ |
| **Token 刷新竞态** | 多线程/多任务并发时，token 刷新是否有竞态条件？ |
| **取消传播** | `cancel_check` 回调是否在所有阶段都检查了？（上传/提交/轮询/下载） |
| **批量处理部分失败** | 批量模式下，一个片段失败不应影响其他片段。阶段间状态传递要健壮 |

**当前状态**：⚠ `wuhenai_v2.py` 的 `submit()` 补上了 video_path 判空（v2.1审查修复）。批量处理的四阶段流水线设计合理。

---

#### S9. 死代码检测（v2.3 新增）

**业务现实**：`DaVinciPipelineUI` 从创建到 S4 接全之前，从未被真实调用——语法/导入/单元测试全绿，但在达芬奇里一跑就炸（`_ui_write()` 参数错误）。死代码自带 bug 但永远不会被发现。

**审查规则**：
- 任何新增的 class/function 必须在至少一个调用路径中被实际使用 = 🟡
- 代码审查时发现「看起来对但没跑过」的代码 → 🟡 加实测注释
- 抽象接口的每个方法都必须在子类中有实现（`@abstractmethod` 确保编译期检查）

**检查方式**：
```bash
# 检查 class 是否有实际调用方（排除定义自身）
grep -rn "ClassName" --include="*.py" | grep -v "class ClassName"
```

---

#### S10. check_ 函数 is_summary 约定（v2.4 新增 — 交付自检工具专属）

**业务现实**：每个 `check_` 函数的第一条结果 MUST 设 `is_summary=True`。UI 将其提取为标题栏汇总。不遵循约定会导致标题栏空着，用户体验差但不报错。

**审查规则**：
- 新增 `check_` 函数第一条 `_make_result()` 必须传 `is_summary=True` = 🟡
- 修改现有检查逻辑后确认汇总行仍准确 = 🟡

---

#### S11. 布局自动化禁止硬编码 CheckBox（v2.4 新增 — 交付自检工具专属）

**业务现实**：检查项数量增长（30+），手写布局维护成本线性增长。`_build_group_rows()` 从 CHECKS 全自动生成 CheckBox 行。

**审查规则**：
- 交付自检工具的 `window_layout` 中禁止 `_cb(CHK_xxx, "text")` 或 `_disabled_cb(CHK_xxx, "text")` = 🟡
- 必须通过 `_section_checkboxes(*ids)` 或 `_build_group_rows(name)` 生成
- 特殊非 CheckBox 控件（轨道编辑、夹帧阈值）走 `extras` 参数注入

---

### 💭 优化项 — 不阻塞合并

---

#### N1. 函数长度

**业务现实**：编排函数（orchestrator）长是正常的。`remove_subtitle.py` 的 `run_pipeline` 约300行，但它做的事情是：
```
环境自检 → OSS预检 → 连接达芬奇 → 扫描IO → 项目路径 → 任务准备 →
余额检查 → 干跑判断 → 串行/批量处理 → 下载替换 → Post-check → 报告输出
```
这是12个步骤的顺序编排，拆分后反而更难看到完整的流程。**编排函数允许长**。

反之，纯逻辑函数应该短：
```python
# ✅ 短纯函数 — extract_ep 8行
def extract_ep(filename: str) -> str:
    m = re.match(r'(EP\d+)', filename)
    return m.group(1) if m else "EP00"

# ✅ 短纯函数 — sanitize_filename 12行
# ✅ 短纯函数 — normalize_for_match 8行
# ✅ 短纯函数 — post_check 25行
```

**审查规则**：
- 编排函数（orchestrator）→ 不限制长度，但需要步骤注释清晰
- 纯逻辑函数 → 建议不超过 50 行
- 适配器方法 → 建议不超过 80 行（`submit` 方法70行，可接受）

---

#### N2. 注释质量

**业务现实**：达芬奇API的行为经常违反直觉。注释需要解释「达芬奇为什么会这样」。

**好注释示例**（来自现有代码）：
```python
# ✅ core.py scan_io_clips — 过滤链完整文档
"""
过滤链（与 subtitle-plugin-rules SKILL.md 严格一致）：
  ❌ IO 未设 → 返回 None
  ❌ GetClipEnabled()==False → skipped_disabled
  ❌ 颜色≠目标颜色 → 静默跳过
  ...
"""

# ✅ subtitle_state.py — 解释设计选择
# SMB 上 os.mkdir() 是原子操作。两人同时建同名目录只有一个成功。

# ✅ core.py download_and_apply — 解释降级策略
# 无论 ReplaceClip 是否成功，下载已完成，记录到账本（下次可直接复用缓存）
```

**审查规则**：
- 看起来奇怪但实际正确的代码 → 💭 需要注释解释「为什么」
- 达芬奇 API 的坑 → 💭 需要注释标注
- 业务阈值 → 💭 需要注释（如「短剧片段通常15-20秒」）

---

#### N3. 命名一致性

**业务现实**：项目有两种命名体系共存——旧名（watermark）和新名（subtitle）。

| 旧名 | 新名 | 说明 |
|------|------|------|
| `~/.watermark.env` | `~/.subtitle.env` | 个人备用配置 |
| `WATERMARK_DEBUG` | `SUBTITLE_DEBUG` | 环境变量前缀 |
| 去水印 | 去字幕 | 功能描述 |

`config.py` 的 `_env()` 函数已做兼容（新名优先，旧名兜底）。新代码统一用新名。

#### N4. 实例属性初始化（v2.1 新增）

**业务现实**：`hasattr(self, "_task_map")` 模式——在方法中动态创建实例属性，而非在 `__init__` 声明。

```python
# 💭 当前 wuhenai_v2.py submit()
if not hasattr(self, "_task_map"):
    self._task_map = {}
```

这本身不产生 bug（`wait_for_result` 通过 `getattr(..., {})` 安全访问），但会降低代码自文档化程度。阅读者需要在多个方法间跳转才能理解属性的完整生命周期。

**审查规则**：
- `__init__` 中声明并初始化为合理默认值（如 `{}`、`None`）= 💭 建议
- 如果属性只在特定场景使用且体积大（如大 dict），延迟初始化可接受但需要注释说明

#### N5. 数据格式 — 返回结构化字段，不做字符串拼接再拆分（v2.3 新增）

**现实案例**：check_core 返回 `{"message": "❌ ST1 00:02:15  text  (1帧)"}`，UI 用 `re.sub` 剥离 ❌/时码/轨道前缀。裁缝老师：「为什么不直接拿干净的原数据？」

**审查规则**：
- 🟡 core 函数返回独立字段（`track`/`timecode`/`detail`），不拼接成 `message` 后再拆分
- 🟡 图标不放数据字段，由 UI 按 `status` 自行选择
- 💭 汇总行用 `is_summary: True`，不用特殊 type 值

#### N6. 改完自查全量引用（v2.3 新增）

**现实案例**：从 ui.py 删了 `check_weather` 但 check.py 还 import 着；改了汇总格式但旧代码残留两份。

**审查规则**：
- 🟡 删/改名后 grep 搜索全量引用，确认无遗漏
- 🟡 改函数签名后 grep 所有调用点

---

## 四、审查流程

### 4.1 触发时机

| 场景 | 级别 | 审查人 | 阻断标准 |
|------|------|--------|---------|
| 新插件（如AI换口型） | 完整 | 裁缝老师 + AI | 全部🔴 + 关键🟡 |
| 修改 `shared/` | 完整 | 裁缝老师 + AI | 影响20台机器 |
| 修改 `core.py` / 计费逻辑 | 完整 | 裁缝老师 + AI | 计费bug=直接损失 |
| 修改适配器 | 标准 | 开发者 + AI | API调用链 |
| Bug修复（UI/配置） | 快速 | 开发者 + AI | 回归风险 |
| 紧急热修复（生产挂了） | 事后补 | 24h内补齐 | 先修再审 |

### 4.2 审查步骤

```
自审(清单) → 自动检查(pre-commit) → AI审查 → 人工审查(裁缝老师) → 达芬奇实测 → 合并
```

**Step 1: 自审（开发者）**
- 对照本文 🔴 清单逐项自查
- 运行 `python3 tools/check.py`
- 运行 `python3 AI去字幕/tests/test_core.py`

**Step 2: 自动检查（pre-commit hook）**
- 语法编译、零pip、SMB安全、硬编码密钥、调试残留、裸except — 见 `tools/pre-commit.sh`

**Step 3: AI 审查**
- 安全漏洞、达芬奇API误用、SMB并发、计费逻辑
- 标记 🔴/🟡/💭

**Step 4: 人工审查（裁缝老师）**
- 业务流程正确性、达芬奇实测、UI体验

**Step 5: 达芬奇实测**
- 必须在达芬奇内真正跑一次。代码在终端能跑 ≠ 在达芬奇能跑

### 4.3 审查评论格式

```markdown
🔴 **R3: ReplaceClip 缺少下载后校验**
文件: plugin/core.py L642
场景: 如果 OSS 返回200但body为空，文件大小为0，ReplaceClip会替换成空文件
建议: 在 urlretrieve 后加 if os.path.getsize(dl) == 0 检查
参考: download_and_apply 已有的三段式模式
```

---

## 五、自动化检查

### 5.1 Pre-commit（自动触发）

```bash
# 每次 git commit 自动运行
bash tools/pre-commit.sh
```

7项检查：语法编译 → 零pip → SMB安全 → 硬编码密钥 → .env保护 → 调试残留 → 裸except

### 5.2 手动检查

```bash
# 环境体检
python3 tools/check.py

# 纯函数测试
cd AI去字幕 && python3 tests/test_core.py

# 达芬奇冒烟测试（需要达芬奇运行中）
python3 tools/smoke_test.py

# 代码风格（开发机可选）
pip3 install flake8 && flake8 AI去字幕/ shared/ tools/ --config=.flake8
```

---

## 六、常见问题判断速查

| 你看到 | 实际判断 |
|--------|---------|
| `except Exception: pass` + 有注释「不阻塞主流程」 | ✅ 合格（ledger/ops_logger 风格） |
| `except Exception: pass` + 无注释 | 🟡 补注释 |
| `except: pass`（裸 except） | 🔴 改为 `except OSError` 或加注释 |
| `print(f"[GhostCut] ...")` | ✅ adapters 可以用 print |
| `print(f"处理完成")` 在 `core.py` 中 | 🟡 改用 logger |
| `import os, sys, time` | 💭 旧代码不强制，新代码改 |
| `run_pipeline` 300行 | ✅ 编排函数允许长 |
| `test_core.py` 裸 assert | 🟡 可改为 unittest（零依赖） |
| `# TODO` 注释 | 🟡 需要关联 issue 或明确计划 |
| `GetClipProperty("X")` 不判空 | 🔴 必须 `or default` |

---

## 六、快速参考十问（审查前自检）

```
┌─────────────────────────────────────────────┐
│         达芬奇插件工坊 Code Review 十问        │
├─────────────────────────────────────────────┤
│ 改代码前问自己：                               │
│                                              │
│  1. 💰 余额检查 → 阻断 → 日志，链完整吗？       │
│  2. 🎬 ReplaceClip 前取了干净 File Name 吗？   │
│  3. 🔑 密钥在 .env 不在代码里？                 │
│  4. 📦 只用了标准库？没偷偷 import pip 包？     │
│  5. 🔄 改 core.py → 双入口同步了吗？            │
│  6. 🔒 加锁的地方有 release_lock（含异常路径）？ │
│  7. 🚫 没有 find/grep -r /Volumes/MYJC？      │
│  8. 📊 ops_logger 关键节点都记录了？            │
│  9. ⚠️  达芬奇 API 返回值检查了 None？          │
│ 10. 🧪 跑过 build_local.sh 了吗？                 │
└─────────────────────────────────────────────┘
```

---

## 七、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 2.4 | 2026-05-09 | 新增 N5(数据格式规范)、N6(改完自查全量引用) |
| 2.3 | 2026-05-09 | S6 更新 ffprobe 解耦状态；S7 新增懒加载解耦模式；R3 补充 ReplaceClip 颜色陷阱；新增 S9 死代码检测；十问 Q10 修正为 build_local.sh |
| 2.2 | 2026-05-09 | 合并 code-review-standards skill 的「快速参考十问」；删除过时 skill，统一为本文档 |
| 2.1 | 2026-05-09 | 实战审查 wuhenai_v2.py 后修订：新增 S8(适配器专项)、N4(实例属性初始化)、S7 扩展(标准库不在函数内import) |
| 2.0 | 2026-05-09 | 深度结合业务重写：每项规则绑定真实场景，区分「故意设计」vs「真正问题」，增加分场景判断逻辑 |
| 1.0 | 2026-05-09 | 初始版本 |
