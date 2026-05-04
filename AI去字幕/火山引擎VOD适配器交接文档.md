# 火山引擎 VOD 精细化字幕擦除 — 适配器交接文档

> 日期: 2026-05-04
> 作者: 小裁缝 (AI)
> 前序工作: 完成 API 签名调通、端到端测试、质量验证
> 交接目标: 达芬奇插件工坊，封装为正式适配器

---

## 一、今日成果总览

### ✅ 已完成

1. **API 签名认证彻底搞通** — 之前卡了很长时间的签名问题已解决
2. **StartExecution 调通** — Auto 模式字幕擦除任务提交成功，返回 RunId
3. **GetExecution 调通** — GET 方法查询任务状态，成功获取完整结果
4. **端到端测试通过** — 用真实视频（Vid: `v02cd3g10068d7rroniljhtd9qao75v0`）跑通全流程
5. **裁缝老师确认质量满意**

### ❌ 未完成

1. `adapters/volcengine_vod.py` 需要重写（现有代码用错了 SDK 类和参数）
2. 下载产物视频需要绑定加速域名（裁缝老师已在处理）

---

## 二、关键技术发现（踩坑记录）

### 2.1 签名格式 — 最大的坑

火山引擎用的是**自定义签名格式**，不是标准 AWS SigV4。区别如下：

| 项目 | 火山引擎 | 标准 AWS SigV4 |
|---|---|---|
| 算法名 | `HMAC-SHA256` | `AWS4-HMAC-SHA256` |
| Credential scope 末尾 | `request` | `aws4_request` |
| 日期 header | `X-Date` | `X-Amz-Date` |
| 签名 header | `X-Content-Sha256` | `X-Amz-Content-Sha256` |

**参考实现**: https://github.com/volcengine/volc-openapi-demos/blob/main/signature/python/sign.py

### 2.2 Endpoint 和 Region

| 接口 | Host | Region | Service |
|---|---|---|---|
| StartExecution (2025-01-01) | `vod.volcengineapi.com` | `cn-north-1` | `vod` |
| GetExecution (2025-01-01) | `vod.volcengineapi.com` | `cn-north-1` | `vod` |
| GetPlayInfo (2023-01-01) | ❌ 新空间不支持 | - | - |

**⚠️ 重要**: Region 必须是 `cn-north-1`，不是 `cn-beijing`。之前一直用错 region 导致签名不匹配。

### 2.3 请求格式

```
POST https://vod.volcengineapi.com/?Action=StartExecution&Version=2025-01-01
GET  https://vod.volcengineapi.com/?Action=GetExecution&Version=2025-01-01&RunId=xxx
```

- Path 固定为 `/`
- Action 和 Version 通过 query 参数传递
- 请求体为 JSON

### 2.4 已上传视频的 Vid

裁缝老师已上传一个测试视频到空间 `space-xutfyw`:
- **Vid**: `v02cd3g10068d7rroniljhtd9qao75v0`
- 可直接用 `Type: "Vid"` 调用 StartExecution，无需再上传

---

## 三、签名算法详解

### 3.1 密钥派生链

```
SK → k_date → k_region → k_service → k_signing
```

```python
k_date    = HMAC-SHA256(SK,          YYYYMMDD)
k_region  = HMAC-SHA256(k_date,      "cn-north-1")
k_service = HMAC-SHA256(k_region,    "vod")
k_signing = HMAC-SHA256(k_service,   "request")
```

### 3.2 Canonical Request 格式

```
{METHOD}
/
{normalized_query}
content-type:application/json
host:vod.volcengineapi.com
x-content-sha256:{body_hash}
x-date:{x_date}

content-type;host;x-content-sha256;x-date
{body_hash}
```

注意：
- 第4行是 headers（每行一个，按字母序排列）
- 第5行是**空行**（headers 后必须有一个空行）
- 第6行是 signed_headers 列表（分号分隔）
- 第7行是 body 的 SHA256 哈希

### 3.3 String to Sign 格式

```
HMAC-SHA256
{x_date}
{YYYYMMDD}/cn-north-1/vod/request
{SHA256(canonical_request)}
```

### 3.4 Authorization Header

```
HMAC-SHA256 Credential={AK}/{YYYYMMDD}/cn-north-1/vod/request, SignedHeaders=content-type;host;x-content-sha256;x-date, Signature={signature}
```

---

## 四、可工作的参考代码

### 4.1 核心签名函数

完整可运行的参考实现见: **`test_vod_official.py`**（测试工作目录下）

关键函数签名流程：
```python
def sign_and_request(action: str, body_dict: dict, method: str = "POST") -> dict:
    """
    核心签名流程：
    1. 构造 Canonical Request (method + path + query + headers + signed_headers + body_hash)
    2. 构造 String to Sign (HMAC-SHA256 + x_date + credential_scope + hashed_canonical_request)
    3. 计算签名密钥链 (SK → k_date → k_region → k_service → k_signing)
    4. 拼装 Authorization header
    """
```

### 4.2 StartExecution 请求体

```python
# Auto 模式（推荐，自动识别字幕）
body = {
    "Input": {
        "Type": "Vid",
        "Vid": "v02cd3g10068d7rroniljhtd9qao75v0",
    },
    "Operation": {
        "Type": "Task",
        "Task": {
            "Type": "Erase",
            "Erase": {
                "Mode": "Auto",
                "Auto": {
                    "Type": "Subtitle",
                    "SubtitleFilter": {},
                },
                "WithEraseInfo": True,
                "NewVid": True,  # 生成新 Vid，方便后续获取产物
            },
        },
    },
}

# Manual 模式（框选擦除）
body = {
    "Input": {
        "Type": "Vid",
        "Vid": "v02cd3g10068d7rroniljhtd9qao75v0",
    },
    "Operation": {
        "Type": "Task",
        "Task": {
            "Type": "Erase",
            "Erase": {
                "Mode": "Manual",
                "Manual": {
                    "Locations": [
                        {
                            "RatioLocation": {
                                "TopLeftX": 0.10,   # 左上角 X (0-1 比例)
                                "TopLeftY": 0.85,   # 左上角 Y
                                "BottomRightX": 0.90, # 右下角 X
                                "BottomRightY": 0.95, # 右下角 Y
                            }
                        }
                    ]
                },
                "WithEraseInfo": True,
                "NewVid": True,
            },
        },
    },
}
```

### 4.3 GetExecution 查询

```python
# GET 方法，RunId 放在 query 参数里
params = {"Action": "GetExecution", "Version": "2025-01-01", "RunId": run_id}
# 请求体为空字符串 ""
```

### 4.4 实际测试结果

```
请求: StartExecution (Auto 模式)
响应: 200 OK
RunId: lb:71d0d89f09a51ac051714f65d9c0b79b

请求: GetExecution
响应: 200 OK
Status: Running → (约4分钟后) → Success
输出:
  - Duration: 15.07 秒
  - FileName: d6efac59d7ce4f9797a1ede340eaad65
  - Vid: v02cd3g10068d7rsoiiljht4mfqt0nh0
  - Size: 24187279 (~23MB)
  - Width: 720, Height: 1280
  - 检测到多处字幕区域（含精确像素坐标和时间段）
```

---

## 五、现有适配器的问题

### `adapters/volcengine_vod.py` 需要重写

**问题清单**:

1. **Region 错误**: 代码里写的 `cn-beijing`，应该是 `cn-north-1`
2. **SDK 类不存在**: `VOD20250101Api` 在 `volcenginesdkvod20250101` 模块里不存在
3. **Import 错误**: `from volcenginesdkvod20250101 import VOD20250101Api` 会直接报错
4. **签名方式不对**: 用了 `UniversalApi`，但实际上应该用 `test_vod_official.py` 里的手写签名
5. **输出结果解析**: `_extract_output_url` 方法的逻辑需要根据实际响应结构调整

**建议**: 基于 `test_vod_official.py` 的签名逻辑重写，不依赖 SDK 的高级封装。

---

## 六、产物下载的限制

### 当前状态

- GetExecution 返回的 Output 包含 `FileName` 和新 `Vid`
- 但**不能直接下载**，需要在 VOD 控制台给空间绑定加速域名
- 绑定域名后，URL 格式: `https://{你的域名}/{FileName}`

### 裁缝老师的进展

裁缝老师已在控制台通过 DirectUrl 模式搜索 FileName 下载了产物视频。确认加速域名绑定完成后，再告知插件工坊用于拼接下载 URL。

### 适配器实现建议

在 `wait_for_result()` 中：
1. 先轮询 GetExecution 等待 Status 变为 Success
2. 获取 FileName 和 Vid
3. 尝试通过 GetPlayInfo 或手动拼接 URL 下载
4. 如果无法下载（未绑定域名），返回 FileName/Vid 让用户手动获取

---

## 七、适配器重写指南

### 7.1 推荐实现方式

**不依赖 SDK**，用 `test_vod_official.py` 的手写签名方式。理由：
- SDK 的 `volcenginesdkvod20250101` 只有 `StartExecution` 和 `GetExecution` 相关接口
- SDK 的签名实现（`SignerV4`）和 endpoint 路由有 bug
- 手写签名代码量小（~50行），完全可控

### 7.2 接口映射

| BaseAdapter 方法 | 火山引擎实现 |
|---|---|
| `submit(task)` | 上传视频 → StartExecution → 返回 RunId |
| `wait_for_result(task_id)` | GetExecution 轮询 → 返回结果 |
| `process(task)` | 直接调用基类默认实现 |
| `check_health()` | 调用 GetExecution 测试连通性 |

### 7.3 Auto vs Manual 模式选择

| 场景 | 模式 | 说明 |
|---|---|---|
| 默认 | Auto + Subtitle | 自动识别字幕，推荐 |
| 短剧出海 | Auto + Subtitle | 自动识别中英文字幕 |
| 避免误擦 | Auto + Locations | 框选区域 + OCR 识别 |
| 小语种 | Manual + Locations | 直接擦除框内文字，不依赖 OCR |
| 强制擦除 | Manual + Locations | Auto 漏擦时用 |

### 7.4 按时间段擦除

支持 `EraseOption.ClipFilter` 参数：
- `Mode: "Selected"` — 仅擦除选中时间段
- `Mode: "Skip"` — 跳过选中时间段（适合保留片头片尾）

---

## 八、价格对比

| 方案 | 价格 | 状态 |
|---|---|---|
| **火山引擎 VOD** | ¥1.00/分钟 | ✅ 已调通，质量OK |
| **鬼手 GhostCut** | ¥1.90/分钟（正式出片）| ✅ 已集成，当前主力 |
| **鬼手快速预览** | ¥0.38/分钟 | 质量较低 |
| **阿里云** | ¥0.40/分钟 | ❌ 测试不过，3种方式都没去干净 |
| **无痕AI** | ¥1.20/分钟 | ⏸ API需人工开通 |

**结论**: 火山引擎价格只有鬼手的一半，质量相当，值得作为主力方案。

---

## 九、待办事项

### 达芬奇插件工坊

- [ ] 重写 `adapters/volcengine_vod.py`（基于 `test_vod_official.py` 签名逻辑）
- [ ] 实现视频上传流程（ApplyUploadInfo → PUT → CommitUploadInfo）
- [ ] 实现产物下载（需要等裁缝老师配置加速域名）
- [ ] 集成到插件主流程
- [ ] 测试 Auto/Manual 两种模式

### 裁缝老师

- [x] 在 VOD 控制台绑定加速域名（已操作）
- [ ] 确认加速域名，告知插件工坊用于拼接下载 URL
- [ ] 对比火山引擎 vs 鬼手的擦除质量，确认主力方案

---

## 十、文件索引

| 文件 | 位置 | 说明 |
|---|---|---|
| `test_vod_official.py` | 测试工作目录 | ✅ **核心参考** — 可运行的签名实现 |
| `adapters/volcengine_vod.py` | AI去字幕/adapters/ | ❌ 需要重写 — 当前代码不可用 |
| `adapters/ghostcut.py` | AI去字幕/adapters/ | ✅ 鬼手适配器，已集成可用 |
| `adapters/__init__.py` | AI去字幕/adapters/ | ✅ BaseAdapter 接口定义 |
| `config.py` | AI去字幕/ | ✅ 配置基本正确 |
| `API比测汇总报告.md` | 测试工作目录 | 📄 五家供应商对比报告 |

---

## 十一、FAQ

**Q: 为什么不用官方 SDK？**
A: SDK 的 `volcenginesdkvod20250101` 模块只有 `StartExecution` 和 `GetExecution` 相关接口，没有 `VOD20250101Api` 这个高级封装类。而且 SDK 的签名实现（`SignerV4`）和 endpoint 路由有 bug，调试花了很长时间也没解决。手写签名代码量小（~50行），完全可控。

**Q: Region 为什么不是 `cn-beijing`？**
A: 火山引擎 VOD 的 API Region 是 `cn-north-1`，不是 `cn-beijing`。之前一直用错 region 导致签名不匹配，这是最大的坑。

**Q: GetPlayInfo 为什么不能用？**
A: GetPlayInfo API（版本 2023-01-01）不支持新的 VOD 空间。需要用加速域名手动拼接 URL 下载产物视频。

**Q: 火山引擎比鬼手便宜一半，质量能接受吗？**
A: 裁缝老师已确认质量满意。火山引擎用的是 DiT Diffusion Transformer + 字体级分割技术，号称 10000+ 视频验证 100% 擦除成功率。

---

*本文档由小裁缝 (AI) 在 2026-05-04 完成 API 调通和端到端测试后编写。*
*如有问题，请联系裁缝老师或查看 `test_vod_official.py` 中的完整实现。*
