---
name: plugin-skeleton
description: 达芬奇插件工坊新产品启动流程。当裁缝老师说"开新产品"或"启动AI换口型"等时自动加载。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
---
# 新产品启动流程

> 从 AI去字幕 的成熟模式中提炼。新产品的目标：**只写 adapter + config，其他全部复用**。

---

## 第一步：确认需求（产品定义）

在写任何代码前，确认：
1. **产品名**：AI换口型 / AI语音克隆 / ...
2. **输入**：用户选什么？（时间线片段？音频文件？）
3. **输出**：结果放哪里？（替换原片？追加新轨？导出文件？）
4. **API供应商**：哪家？调研报告有了吗？
5. **定价**：怎么计费？一分多少钱？

---

## 第二步：创建产品目录

```bash
mkdir -p AI换口型/adapters
mkdir -p AI换口型/tests
```

或者直接复用 AI去字幕 的目录结构作为模板：

```bash
# 复制目录结构
cp -r AI去字幕/ AI换口型/
# 删除去字幕专属文件
rm AI换口型/adapters/wuhenai_v2.py
rm AI换口型/adapters/ghostcut.py
rm AI换口型/adapters/__pycache__/*
```

---

## 第三步：写 config.py（填空）

参照 `AI去字幕/config.py`，只需改：
- `__version__` = "0.1.0-dev"
- API 密钥环境变量名
- brand 品牌覆写（见 `shared/brand_template.py`）
- 输出子目录名

**其余全从 shared/ 导入，零新增代码。**

---

## 第四步：写 adapter（这是唯一要新写的代码）

### 4.1 创建 adapter 接口（如果通用接口不适用）

`AI去字幕/adapters/__init__.py` 中的 `BaseAdapter` 是通用基类。新产品直接继承它。

### 4.2 写具体 adapter

参照 `AI去字幕/adapters/wuhenai_v2.py` 的模式。**adapter 架构（2026-05-26 重构）：**

```python
# adapters/myengine.py
class MyEngineAdapter(BaseAdapter):
    """引擎适配器"""
    
    @property
    def provider_key(self) -> str:
        """pricing/ADAPTER_PRIORITY 用的内部 key。只有 config key ≠ pricing key 时才需覆盖"""
        return self.key  # 通常相同

    def __init__(self, config: dict):
        super().__init__("myengine", config)  # 传 config key，不是显示名!
        # config["name"] 自动成为 self.name（显示名）
```

**key/name 分离架构：**
- `self.key` — 内部标识，永不变（如 `"ghostcut"`, `"wuhenai_v21"`）
- `self.name` — 显示名，从 `config["name"]` 自动读取（如 `"鬼手"`, `"无痕AI 2.1"`）
- `self.provider_key` — 定价/ADAPTER_PRIORITY 用的 key，默认等于 `self.key`
- **改名只需改 `config.py` 的 `name` 字段**，代码零改动

**config.py 注册：**
```python
ADAPTER_CONFIGS = {
    "myengine": {
        "name": "我的引擎",     # 显示名，改名只改这里
        "enabled": True,
        "api_key": ...,
    },
}
```

---

## 第五步：覆写 UI（如果 UI 与去字幕不同）

`stable_ui.py` → 改 WIN_ID、品牌引用
`ui_widgets.py` → 当前 629 行，大部分是去字幕专用。新产品可以根据需要简化。
`ui_pipeline.py` → 当前 631 行，业务逻辑。新产品重写或大幅删减。

---

## 第六步：部署脚本

从 AI去字幕 复制以下脚本，搜索替换「AI去字幕」→ 新产品名：
- `build_local.sh` — 本地验证（含版本提醒、launcher自动命名、`--save` checkpoint）
- `push_all.sh` — 全量发布
- `sync.sh` — SMB 同步
- `bump_version.sh` — 版本号 MINOR +0.1
- `gray.sh` — 灰度管理

`build_local.sh` 已内置：
- 📝 当前版本号显示
- ⚠ 本地 `__channel__` = "dev" vs SMB `__channel__` = ""
- 📦 `--save` 自动 git commit checkpoint
- 📝 launcher 自动命名（`产品_v1.0.0-dev.py`）

`bump_version.sh`：自动 `config.py` `__version__` MINOR +0.1。用 `version_string()` 返回 `1.1.0-dev`。

---

## 第七步：launcher

launcher.py 是薄包装，调用 `shared/launcher_router.py`（按 hostname 自动路由到本地/SMB）。只需改产品名即可。
部署：个人版用 `build_personal.sh` 构建 zip → 百度网盘分发；内部版用 `deploy.json` + `push_all.sh`（壳已一次性部署，不再需要 `deploy_one.sh`）。

---

## 已就绪（不用写，直接复用）

| 模块 | 用途 |
|------|------|
| `shared/fusionscript_loader.py` | 达芬奇连接 |
| `shared/ledger.py` | 缓存/撤销/记录 |
| `shared/pricing.py` | 计费模型 |
| `shared/subtitle_state.py` | SMB并发锁 |
| `shared/ops_logger.py` | 运维日志 |
| `shared/resolution.py` | 分辨率解析 |
| `shared/timecode.py` | SMPTE时码 |
| `shared/mappings.py` | 映射表 |
| `tools/quick_verify.sh` | 语法+导入链验证 |
| `tools/smoke_test.py` | 冒烟测试框架 |
| 壳部署 | `cp SMB/shell.py → 本地Fusion目录`（一次性） |

---

## 开发守则

1. **默认本地开发**：用 `build_local.sh`，不动 SMB
2. **灰度不能跳**：先一台验证，再全量
3. **改完跑验证**：`build_local.sh` 全绿再交付
4. **新建文件立刻加 sync.sh**
5. **失败信息进 UI，不只写 SMB**

---

## 参考

- 完整产品示例：`AI去字幕/`
- 品牌模板：`shared/brand_template.py`

## Launcher 环境变量（2026-06-01 必加）

所有插件的 Launcher 必须设：
```python
_env["PYTHONIOENCODING"] = "utf-8"
_env["PYTHONUTF8"] = "1"              # PEP 540 全局 UTF-8
_env["WORKBUDDY_PERSONAL"] = "1"      # 个人版才设
subprocess.Popen([_PYTHON, "-B", _UI_SCRIPT], env=_env)
# -B: 不生成 .pyc，杜绝 root 权限死锁和缓存脏读
```
- 代码质量：pre-commit.sh 自动化检查（语法/打进去不装上去/密钥泄露）
