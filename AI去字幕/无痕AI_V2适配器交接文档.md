# 无痕AI V2.1 适配器交接文档

> 状态: ✅ 生产就绪
> 完成日期: 2026-05-04
> 署名: 小裁缝 (AI)

---

## 一、基本信息

| 项目 | 内容 |
|---|---|
| 供应商 | 杭州岁羽网络科技有限公司 |
| 产品名 | 无痕AI V2.1 |
| Base URL | `https://api.wuhenai.com/v2/` |
| 认证方式 | API Key → Bearer access_token (7天有效) |
| 数据格式 | JSON, UTF-8 |
| 存储架构 | 自备阿里云 OSS（用户上传+下载），API 不存储文件 |
| 适配器文件 | `adapters/wuhenai_v2.py` |
| 测试脚本 | `test_wuhenai_v2.py`, `test_wuhenai_e2e.py`, `test_wuhenai_compare.py` |
| API 文档 | `wuhenapi_2_1.md` (客服提供) |

---

## 二、账户信息

| 项目 | 内容 |
|---|---|
| 账户 | 西安幕屿剧创文化传媒有限责任公司 (ID: 371044) |
| API Key | `sk_live_8b7bf70bb2a706bac58bfe7c321201b03330` |
| OSS Bucket | `wuhenai-clipflow` (cn-hangzhou) |
| OSS 生命周期 | 1天自动过期（兜底清理） |
| 初始积分 | 600（赠送） |
| 余额 | 536（截至 2026-05-04 测试后） |

---

## 三、调用架构

```
本地视频
  │
  ├─ Step 1: OSS PUT 上传 → input/{ts}_{filename}
  │
  ├─ Step 2: 生成两个预签名 URL
  │   ├─ video_url   (GET, 24h, 供无痕AI拉取)
  │   └─ upload_url  (PUT, 24h, 供无痕AI回传结果)
  │
  ├─ Step 3: POST /v2/video_removal
  │   └─ body: {video_url, upload_url, upload_headers, model, method, rect?}
  │
  ├─ Step 4: GET /v2/status 轮询
  │   └─ created → queued → processing → success / failed / paused
  │
  ├─ Step 5: OSS GET 下载 → output/{ts}_{filename}_clean.mp4
  │
  └─ Step 6: OSS DELETE 清理临时文件
```

---

## 四、API 接口清单

| 接口 | 方法 | 用途 | 适配器实现 |
|---|---|---|---|
| `/user/access_token` | GET | API Key → access_token | `_ensure_token()` |
| `/user/me` | GET | 查询余额 | `check_health()`, `get_balance()` |
| `/user/billings` | GET | 账单明细（文档标"暂未开放"，实测可用） | 未实现 |
| `/user/notify_callback` | GET | 注册回调URL | 未实现（走轮询） |
| `/video_removal` | POST | 提交去字幕任务 | `submit()` |
| `/status` | GET | 轮询任务状态（文档未列出，实测可用） | `wait_for_result()` |
| `/cancel` | POST | 取消排队任务，不扣积分 | 未实现 |
| `/video_eraser` | POST | 视频元素消除 | 暂未开放 |
| `/photo_eraser` | POST | 图片消除 | 暂未开放 |

---

## 五、核心参数 & 最优配置

### 模型选择

| model | 适用范围 | 去 Seedance 字幕 |
|---|---|---|
| `video_removal_std` | 标准模型 | ✅ 够用（客服确认） |
| `video_removal_pro` | 更多水印样式覆盖 | 对字幕无增益，贵 |

### 处理方式

| method | 行为 | 积分/16秒 | ¥/分钟 (9折) |
|---|---|---|---|
| `all_area` | AI 自动检测字幕区域 | 24 积分 | 0.54 |
| `sel_area` | 手动框选底部35% | **16 积分** | **0.36** |

### ✅ 最终定案

```python
model:  "video_removal_std"
method: "sel_area"
成本:   ¥0.36/分钟
```

Seedance 字幕固定屏幕底部，用 sel_area 框选底部 35%：
- 快 2.3 倍（70s vs 162s 处理15秒视频）
- 省 33% 积分（16 vs 24）

---

## 六、踩坑记录

### Bug 1: OSS 预签名 PUT URL 缺少 Content-Type

**现象**: 任务 processing 到 38% 后报 "上传失败"

**原因**: GPU 服务器 PUT 结果到 OSS 时带 `Content-Type: application/octet-stream`，
但预签名 URL 的签名里没有包含 Content-Type，导致签名不匹配。

**修复**: `_oss_presigned_url()` 增加 `content_type` 参数，PUT URL 签名时包含 `application/octet-stream`。

```python
# 修复前
string_to_sign = f"{method}\n\n\n{expires}\n/{self.bucket}/{object_key}"

# 修复后
string_to_sign = f"{method}\n\n{content_type}\n{expires}\n/{self.bucket}/{object_key}"
```

### Bug 2: 任务状态映射错误

**现象**: `wait_for_result()` 永远匹配不到完成状态

**原因**: API 返回 `"success"`，适配器写死 `if status == "complete"`

**修复**: `"complete"` → `"success"`

### Bug 3: sel_area 坐标硬编码 1920×1080

**现象**: 非标准分辨率视频的框选区域计算错误

**原因**: `submit()` 中 rect 坐标转换写死 `* 1920` / `* 1080`

**修复**: 新增 `_get_video_resolution()` 方法，用 ffprobe 动态获取真实分辨率

---

## 七、成本对比

| 方案 | ¥/分钟 | 积分/分钟 | 16秒耗时 | 状态 |
|---|---|---|---|---|
| **无痕AI V2 (sel_area)** | **0.36** | 60 | 70s | ✅ 生产就绪 |
| 无痕AI V2 (all_area) | 0.54 | 90 | 162s | ✅ 可用 |
| 火山引擎 VOD | 1.00 | — | ~240s | ✅ 可用 |
| 鬼手 GhostCut | 1.90 | — | — | 当前主力 |
| 阿里云 | 0.40 | — | — | ❌ 去不干净 |
| 腾讯云 | 3.00 | — | — | 未测 |

---

## 八、批量处理 `process_batch()`

单片段用 `submit()` + `wait_for_result()`，批量用 `process_batch()`。

### 原理

无痕 GPU 服务器天然并行——同时扔 N 个任务上去，它们一起跑。

```
串行:  upload①→submit→wait→download→upload②→...
       5片段 × 70s = 350s

批量:  upload①②③④⑤ → submit①②③④⑤ → 一起轮询 → 逐个下载
       最慢那个 ≈ 70s + I/O ≈ 95s
```

### 接口

```python
adapter.process_batch(tasks: list[WatermarkTask], timeout=600) -> list[WatermarkResult]
```

- 输入: 需要处理的片段列表
- 输出: 与输入顺序一致的结果列表
- 不需要多线程——纯顺序 HTTP I/O
- 自动清理 OSS 临时文件
- 超时后返回已完成的 + 未完成的标记失败

### 性能

| 片段数 | 串行耗时 | 批量耗时 | 加速比 |
|---|---|---|---|
| 5 | ~350s | ~95s | 3.7x |
| 10 | ~700s | ~100s | 7x |
| 30 | ~2100s | ~120s | 17x |

> 实际瓶颈从 GPU 移到 OSS 带宽和积分配额。

### 注意事项

- 批量测试烧积分（5片段 = 80积分），确认无误后再大规模跑
- 达芬奇脚本环境不需要支持并发——process_batch 全程 HTTP，不碰 Resolve API

---

## 九、适配器依赖

仅 Python 标准库，零 pip install：

```python
hashlib, hmac, json, os, secrets, ssl, subprocess,
time, urllib.request, urllib.error, urllib.parse,
email.utils, typing
```

全国几千个剪辑师拿到就能跑。

---

## 十、待实现

| 功能 | 优先级 | 说明 |
|---|---|---|
| `cancel` 接口 | 中 | 取消排队任务，零成本安全网 |
| 回调通知 | 低 | 替代轮询，适合服务端部署 |
| 账单查询 | 低 | `/user/billings` 文档标暂未开放但实测可用 |
| pro 模型支持 | 低 | 客服确认去字幕无增益，保留接口即可 |

---

## 十一、测试产出

| 文件 | 内容 |
|---|---|
| `/02_结果/EP01_g1_01_12_v03_wuhenai_v2.mp4` | 首次 E2E (all_area) |
| `/02_结果/wuhenai_v2_A_std_all_area.mp4` | A/B 对比 A 组 |
| `/02_结果/wuhenai_v2_B_std_sel_area.mp4` | A/B 对比 B 组 (最优) |

输出质量：720×1280 h264，分辨率/时长/编码完整保留，裁缝老师确认质量 OK。
