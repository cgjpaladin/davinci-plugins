---
name: plugin-skeleton
description: 达芬奇插件工坊新产品启动流程。当裁缝老师说「开新产品」或「启动AI换口型」等时自动加载。
version: 1.1.0
agent_created: true
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
mkdir -p plugins/AI换口型/adapters
mkdir -p plugins/AI换口型/tests
```

或者直接复用 AI去字幕 的目录结构作为模板：

```bash
# 复制目录结构
cp -r AI去字幕/ plugins/AI换口型/
# 删除去字幕专属文件
rm plugins/AI换口型/adapters/wuhenai_v2.py
rm plugins/AI换口型/adapters/ghostcut.py
rm plugins/AI换口型/adapters/__pycache__/*
rm plugins/AI换口型/remove_subtitle.py
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

`shared/adapter_base.py` 已有通用接口。如果不适用，在产品的 `adapters/__init__.py` 定义专属基类。

### 4.2 写具体 adapter

参照 `AI去字幕/adapters/wuhenai_v2.py` 的模式：
1. `submit()` — 提交任务到 API
2. `wait_for_result()` — 轮询等待完成
3. `process()` — 一键：提交→等待→下载

必须：
- 零 pip（只用 urllib）
- 视频路径判空
- Token 刷新竞态安全
- 取消传播（上传/提交/轮询/下载四阶段）

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
- `deploy.sh` — 单机部署

`build_local.sh` 已内置：
- 📝 当前版本号显示
- ⚠ 本地版 == 公司版 冲突检测（提醒升版本）
- 📦 `--save` 自动 git commit checkpoint
- 📝 launcher 自动命名（`产品_v1.0.0-dev.py`）

`bump_version.sh`：自动 `config.py` `__version__` MINOR +0.1。用 `version_string()` 返回 `1.1.0-dev`。

---

## 第七步：launcher

从 AI去字幕 复制 launcher.py + launcher_ui.py，改 import 路径。

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
| `tools/deploy_new_machine.sh` | 新机一键部署 |

---

## 开发守则

1. **默认本地开发**：用 `build_local.sh`，不动 SMB
2. **灰度不能跳**：先一台验证，再全量
3. **改完跑验证**：`build_local.sh` 全绿再交付
4. **新建文件立刻加 sync.sh**
5. **失败信息进 UI，不只写 SMB**

---

## 参考

- 完整产品示例：`AI去字幕/`（v1.7.0-dev，生产级）
- 品牌模板：`shared/brand_template.py`
- 代码审查标准：`CODE_REVIEW_STANDARDS.md` v2.2
