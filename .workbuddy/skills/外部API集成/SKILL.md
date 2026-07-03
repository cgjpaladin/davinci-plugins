---
name: api-integrator
description: 外部API集成专家。对接任何AI视频/音频API（去字幕/换口型/语音克隆/超分等）时使用。开发适配器、处理认证、批量并行、成本优化。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
agent_created: true
# 适配器开发标准见 `达芬奇代码审查` skill
# 适配器行为契约见 `AI去字幕开发` skill
---

# 外部 API 集成 — 适配器开发指南

本 skill 基于鬼手+无痕两个生产适配器（共 ~1500 行代码）提炼。新 API 开发适配器时按此规范。

## 一、公共接口（BaseAdapter）

所有适配器继承 `adapters/__init__.py::BaseAdapter`，实现以下方法：

```
必须实现（abstract）:
  submit(task) -> task_id          # 提交到 API，返回服务端任务 ID
  wait_for_result(task_id, timeout, cancel_check) -> SubtitleResult

可选覆盖:
  provider_key -> str              # 映射 config key 到 pricing key
  check_health() -> bool           # 健康检查（默认 True）
  get_balance() -> dict            # 余额查询
  cancel(task_id) -> bool          # 取消任务
  _process_impl(tasks, timeout, cancel_check, progress_callback) -> list[SubtitleResult]
```

### 模板方法（禁止子类覆盖）

`process(task, timeout, output_path, cancel_check)` — 单任务一键处理，submit → wait → return SubtitleResult。
`process_batch(tasks, timeout, cancel_check, progress_callback)` — 批量处理模板，自动记录 ops_log 的 task_submit/task_result/task_error 事件。

### produce 的 invocability contract

```python
# 1. process() 必须捕获所有异常，封装为 SubtitleResult(success=False)
# 2. 绝不让异常穿透 adapter 层
# 3. process_batch() 是 final 模板，子类只覆盖 _process_impl()
```

## 二、当前适配器差异

| 维度 | 鬼手 (GhostCut) | 无痕AI V2 (WuhenAI) |
|------|----------------|---------------------|
| 认证 | AppKey + AppSign (MD5 双重签名) | API Key → Bearer access_token (7天有效) |
| 文件存储 | 通过 API 上传到其 OSS，取临时 CDN URL | 上传到自有阿里云 OSS 桶，预签名 URL |
| 提交方式 | 一次 POST 提交全部 urls | 逐个 POST video_removal |
| 取消 | ❌ 不支持（API 无接口），仅记录日志 | ✅ POST task/cancel |
| 进度回调 | 2 阶段 (upload, processing) | 3 阶段 (upload, submit, processing)，处理中按片段时长加权 |
| 临时文件清理 | 无需（CDN URL 自动过期） | 主动删除 OSS 的 input_key + output_key |
| OSS 费用追踪 | 无 | `oss_tracker.track_upload/download()` |
| 大文件限制 | 500MB warning | 100MB 阻断 |
| 本地依赖 | 纯标准库 | 纯标准库 + ffprobe（分辨率检测用） |

## 三、错误处理三分类

```
永久错误（应直接 fail）:
  - ValueError（输入验证失败）
  - FileNotFoundError（文件不存在）
  - urllib.error.HTTPError（服务端拒绝，包装为 RuntimeError 含状态码+body 前 200 字符）
  - KeyError/IndexError（API 响应解析失败，包装为 RuntimeError 含完整响应体）

瞬态错误（应重试）:
  - urllib.error.URLError（网络中断）
  - OSError（连接重置/SMB 断连）
  - ssl.SSLError（证书验证失败）→ 见下方 curl fallback

预期错误（应特殊处理）:
  - RuntimeError（cancel 返回 False）→ cancel 失败，继续等待
  - subprocess.SubprocessError（ffprobe 失败）→ fallback 默认分辨率，不阻断
```

### curl fallback 双层网络栈

macOS Python SSL 上下文在 3.13↔3.14 之间不一致。标准模式：

```python
_SSL_CTX = ssl._create_unverified_context()

def _api_post(self, path, payload):
    try:
        req = Request(url, data=body, headers=headers)
        with urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, ssl.SSLError) as e:
        # fallback 到 curl 子进程
        data = http_fallback.curl_post(url, body, headers, timeout=35)
        return json.loads(data)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API {e.code}: {e.read().decode()[:200]}")
```

> `_SSL_CTX` 跳过证书验证——仍 TLS 加密但失去 MITM 防御。仅用于可信目标（自家 FC/阿里云 OSS）。

## 四、重试策略

| 场景 | 次数 | 回退 | 位置 |
|------|:--:|------|------|
| OSS 上传（无痕） | 3 次 | `time.sleep(2)` 固定 | `_upload_to_oss()` |
| API 轮询（两个） | 无限 | `poll_interval * 1.5` 指数增长，从 5s→30s 上限 | `wait_for_result()` |
| ops_logger SMB 写 | 3 次 | `0.3 * attempt` 递增 | 内部 `_write()` |

**网络错误不视为永久失败**——轮询循环中用 `except (URLError, OSError)` 捕获，继续等待不退出。

**API HTTP 错误视为永久**——不是 2xx 就是永久失败，包装为 RuntimeError。

## 五、OSS 双模式

### 模式 A：API 托管 OSS（鬼手）

```
POST /upload/policy/apply → 获取临时 accessid/policy/signature
  → multipart/form-data 直传 OSS endpoint（手工构建，不依赖 requests）
  → 拼接 CDN URL = policy["urlPrefix"] + filename
```

- 无需保存 AK/SK，每次获取临时凭证
- URL 有效期 14-30 天
- 上传 timeout 120s

### 模式 B：自有 OSS 桶（无痕）

```
OSS Signature V1（HMAC-SHA1 + Base64）签名
  → upload: HEAD 去重检查 → PUT 上传（timeout 120s, 3 次重试）
  → download: GET 下载原始字节 → 写入本地文件
  → cleanup: DELETE input_key + output_key
  → presigned_url: GET/PUT 预签名 URL（默认 48h, 下载 1h）
```

- 环境变量 `OSS_ACCESS_KEY_ID/SECRET/BUCKET/REGION`
- 用量追踪：`oss_tracker.track_upload(size)` / `track_download(size)`
- 大文件限制 100MB

### OSS 费用模型

| 项目 | 价格 |
|------|------|
| 存储 | 0.09 元/GB/月 |
| 外网流出（忙时） | 0.50 元/GB |
| 外网流出（闲时） | 0.25 元/GB |
| PUT/GET 请求 | 0.01 元/万次（免费额度内为 0） |

> `OSSCostTracker`（`shared/pricing.py`）线程安全追踪用量，仅计算外网流出流量。

## 六、计费系统

### 定价结构（`shared/pricing_defaults.py`）

```python
PRICING = {
    "wuhenai": {"models": {...}, "point_to_yuan": 0.0091},  # ¥1000 = 110000积分
    "ghostcut": {"models": {...}, "point_to_yuan": 0.19},    # ¥189 = 1000积分
}
```

鬼手按 30 秒单位计费，无痕按秒计费。`estimate_cost(duration, provider)` 用 `ceil(duration / unit)` 计算预估费用。

### 余额保护

`create_preferred_adapter()` 按 `ADAPTER_PRIORITY` 顺序尝试，余额 >= 5 积分才采用。失败自动尝试下一个。所有不可用时返回 None。

**已知财务 bug（2026-06 修复）**：
- `WUHENAI_YUAN_PER_SEC` 曾硬编码导致费率错误（已修）
- `get_provider_rate()` 默认使用 `ACTIVE_PROVIDER`，不传参数时用错汇率（已修）

## 七、适配器选择与降级

```python
ADAPTER_PRIORITY = ["wuhenai", "ghostcut"]       # 首选无痕（更便宜）

adapter = create_preferred_adapter(exclude=None)  # exclude 防止递归
# → 按优先级逐个尝试 → 余额检查 >= 5 → 健康检查 → 返回
# → 全部不可用返回 None → UI 显示 "引擎不可用"
```

## 八、取消模式

```
cancel_check() → 轮询循环中检测 → cancel(task_id)
  ├─ 鬼手: 不支持取消 → 标记为 "用户取消（未取消远端）"
  ├─ 无痕: POST task/cancel → 失败则继续等待
  └─ 批量处理: cancel_done 标志防止重复取消
```

取消失败不阻塞——采用 best-effort 策略。批量模式下 Pending 任务统一标记为 "用户取消"。

## 九、线程安全

**适配器本身不是线程安全的**。以下外部模块有线程保护：

| 模块 | 锁 | 保护范围 |
|------|-----|----------|
| `OSSCostTracker` | `threading.Lock()` | 用量计数器 |
| `ops_logger._write()` | `threading.Lock()` | JSONL 文件写入 |
| `_DailyWriter` | `threading.Lock()` | 日志文件追加 |

> 代码注释标注：`"达芬奇子进程+SMB挂载+线程=不可靠，改顺序执行"`。原计划并发上传改为串行。

## 十、进度回调规范

```python
progress_callback(phase: str, ratio: float)
# phase ∈ {"upload", "submit", "processing"}
# ratio: 0.0 ~ 1.0

# 标准分配:
#  upload:      0.0 ~ 0.2   (每个文件上传完回调)
#  submit:      0.2 ~ 0.3   (每个任务提交完回调)
#  processing:  0.3 ~ 0.9   (每次轮询回调，按片段时长加权)
#  download:    无回调（静默）
```

进度回调异常用 `try/except` 吞掉，不影响批量处理主流程。

## 十一、新适配器开发流程

1. 读 API 文档 → 确认认证方式、接口格式、限制
2. 写 `MyAdapter(BaseAdapter)` → 实现 `submit` + `wait_for_result` + `_process_impl`
3. 实现 OSS 存储（选模式 A 或 B，或新模式）
4. 写 `check_health` + `get_balance` + `cancel`（API 不支持则标注）
5. 注册到 `ADAPTER_CONFIGS` + `ADAPTER_PRIORITY` + `PRICING`
6. 写 dry-run 测试（0 积分）
7. 写对比报告：价格/速度/质量 vs 现有方案

## 十二、已知踩坑

| # | 坑 | 解法 |
|---|-----|------|
| 1 | `print()` 泄漏到 UI 日志区 | adapter 统一用 `_log()`，不直接用 print |
| 2 | 缓存费率写死 → 后续改动不生效 | 费率从 `pricing_defaults` 动态读 |
| 3 | `_cached_provider` 初始值硬编码 | 切 adapter 时主动更新缓存 |
| 4 | 余额汇率用 `ACTIVE_PROVIDER` → 非主引擎显示错 | `get_provider_rate()` 显式传 provider |
| 5 | `set_logger` 吞掉 init 代码（缩进 bug） | `set_logger` 只设 logger，不走业务逻辑 |
| 6 | `_log` 回调签名不兼容（单参 vs 双参） | 统一用 `*args` |
| 7 | 灰度 gray.json 指向旧目录 | 灰度推新时同步更新配置路径 |
| 8 | DaVinci 子进程 SSL 不一致 | 用 curl fallback 或 `_create_unverified_context()` |
| 9 | 并发上传在达芬奇环境不稳定 | 串行执行，ThreadPool 留作注释 |
