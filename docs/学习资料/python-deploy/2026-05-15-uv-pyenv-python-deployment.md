# Python 环境管理与部署 — uv + pyenv + Framework 三轨制

> **日期**: 2026-05-15（周五 · Python 部署主题）
> **来源**: [uv 完整指南 (pydevtools.com)](https://pydevtools.com/handbook/explanation/uv-complete-guide/)、[pyenv macOS 指南 (lvtao.net)](https://www.lvtao.net/system/macos-python-version-management-pyenv-guide.html)、[知乎 Python 虚拟环境对比](https://zhuanlan.zhihu.com/p/663735038)

---

## 一、当前工具格局

| 工具 | 开发者 | 语言 | 替代目标 | 速度 |
|------|--------|------|---------|------|
| **uv** | Astral (Ruff 团队) | Rust | pip + pyenv + virtualenv + pipx + poetry | 10-100x |
| **pyenv** | pyenv/pyenv | Shell | 无（纯版本管理） | 慢（源码编译） |
| **pip** | PyPA | Python | 原生包管理 | 基准 |
| **venv/virtualenv** | PyPA / pypa | Python | 虚拟环境隔离 | 基准 |
| **Poetry** | Python Poetry | Python | 依赖管理+打包 | 中等 |

---

## 二、uv 核心能力

### 2.1 一个工具替代所有

```
uv = pyenv + virtualenv + pip-tools/pip + pipx + Ruff formatter + Poetry
```

### 2.2 安装

```bash
# 方式一：官方脚本（无预依赖，无需 Python）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 方式二：Homebrew（推荐批量部署）
brew install uv

# 验证
uv --version
```

### 2.3 关键命令速查

```bash
# === Python 版本管理（替代 pyenv）===
uv python install 3.13          # 安装指定版本（下载预编译二进制，秒级）
uv python install 3.11 3.12 3.13 # 批量安装
uv python list                  # 列出可用/已安装版本
uv python pin 3.13              # 写入 .python-version 文件

# === 项目管理（替代 venv + pip + requirements.txt）===
uv init my-project              # 创建项目骨架
uv add requests pandas          # 添加依赖（自动写入 pyproject.toml + 更新 uv.lock）
uv add --dev pytest ruff        # 开发依赖
uv sync                         # 同步环境（创建 .venv + 锁定依赖）
uv run python main.py           # 在项目环境中运行

# === pip 兼容模式（渐进迁移）===
uv pip install -r requirements.txt   # 从现有 requirements.txt 安装
uv pip install requests              # 单包安装
uv pip compile requirements.in -o requirements.txt  # 生成锁定文件
uv pip sync requirements.txt         # 精确同步

# === CLI 工具管理（替代 pipx）===
uvx ruff check .                # 临时运行工具
uv tool install ruff            # 全局安装工具

# === 格式化（内置 Ruff）===
uv format                       # 格式化代码
uv format --check               # 仅检查
```

### 2.4 性能数据（Apple Silicon, Python 3.14）

| 操作 | pip/venv | uv | 提速 |
|------|---------|-----|------|
| 创建虚拟环境 | 1.95s | 0.03s | **56x** |
| 安装 23 包（冷缓存） | 13.1s | 0.87s | **15x** |
| 安装 23 包（热缓存） | 6.6s | 0.15s | **44x** |

---

## 三、pyenv 核心知识（遗留方案参考）

### 3.1 安装与配置

```bash
brew install pyenv

# ~/.zshrc 必须添加：
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

source ~/.zshrc
```

### 3.2 版本切换机制

```
优先级: shell > local > global

shell: pyenv shell 3.13    → 仅当前会话
local: pyenv local 3.13     → 当前目录（写入 .python-version）
global: pyenv global 3.13   → 全局默认（写入 ~/.pyenv/version）
```

### 3.3 工作原理

```
用户输入 python → PATH 中 pyenv shim 目录拦截
→ 读取 .python-version / global 配置
→ 重定向到 ~/.pyenv/versions/ 下对应版本
```

### 3.4 ⚠️ 常见坑点

1. **编译失败** → 缺 Xcode CLT 或 brew 依赖：`brew install openssl readline sqlite3 xz zlib`
2. **命令找不到** → `.zshrc` 未 source 或 PATH 顺序问题
3. **版本不切换** → 其他 Python 路径在 PATH 中优先于 pyenv shim
4. **pip 装包失败** → which pip 确认指向正确 Python

---

## 四、macOS 多台机器 Python 部署最佳实践

### 4.1 推荐方案：uv 统一管理（新标准）

```bash
# 每台新机器只需三步：
brew install uv                    # 1. 安装 uv
cd /path/to/project                # 2. 进入有 .python-version + uv.lock 的项目
uv sync                            # 3. 自动下载正确 Python + 所有依赖
uv run python main.py              # 4. 直接运行
```

**关键优势**：
- `uv python install` 下载预编译二进制，不编译（pyenv 的最大痛点消除）
- `uv.lock` 跨平台一致，提交 Git 即可保证所有机器环境相同
- 无需手动配置 pyenv、无需创建 venv、无需管 pip

### 4.2 遗留方案：pyenv（已有环境兼容）

```bash
# 已有 pyenv 的机器保持不变
# 新机器直接上 uv，不再装 pyenv
pyenv install 3.13.13
pyenv local 3.13.13
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.3 Framework Python（我们当前的现状）

```bash
# macOS 自带的 Python Framework 安装在：
/Library/Frameworks/Python.framework/Versions/

# 特点：
# - 由 python.org 安装器安装
# - 需要 sudo 权限
# - 不受 pyenv/uv 管理
# - 达芬奇插件可能引用此路径
# - 多个版本可共存（如 3.7 + 3.13 + 3.14）

# 查看：
ls /Library/Frameworks/Python.framework/Versions/
```

---

## 五、🔗 对我们意味着什么（达芬奇运维专家）

### 5.1 当前环境诊断

**19 台 Mac mini 的 Python 现状（来自 machine_registry.json）**：

| 版本分布 | 机器数 | 具体情况 |
|----------|--------|----------|
| 仅 3.13 | 11台 | mini02/04/05/06/07/08/09/10/12/130/137 |
| 3.13 + 3.14 | 7台 | mini00/01/03/10(xiaolvhua)/g/mini138/mini134 |
| 3.9.6 + 3.13 + 3.14 + 3.7 | 1台 | mini101（最混乱）|
| 空（未记录）| 1台 | mini200（裁缝老师本机）|

**核心问题**：

1. **版本来源混乱** — 有些是系统自带 CLT Python 3.9.6，有些是 Framework Python，有些可能是 Homebrew Python
2. **mini101 最严重** — `_note` 明确写了「CLT Python=3.9.6, Framework有3.13+3.14+3.7, shim被CLT劫持」
3. **无统一管理工具** — 没有 pyenv，没有 uv，每台都是手动装的 Framework Python
4. **目标版本已定为 3.13** — `_config.python_target = "3.13"`

### 5.2 适用性评估

| 方案 | 适用？ | 理由 |
|------|--------|------|
| **uv（全面采用）** | ⚠️ 条件适用 | ✅ 能统一解决版本混乱；⚠️ 但达芬奇内嵌 Python 3.6 是硬约束，插件运行在达芬奇的 subprocess 里，不是独立环境。uv 管不了达芬奇内部的 Python |
| **uv（仅新机部署）** | ✅ 强烈推荐 | 新机器或重装时用 `brew install uv && uv sync` 一键初始化。比现有的 `install_python313.sh` 手动装 Framework Python 快且可靠 |
| **pyenv（补装）** | ❌ 不推荐 | 我们已经有 Framework Python 在跑了，pyenv 会引入第三套路径体系，更乱。而且 pyenv 编译太慢，19 台机器逐台等编译不可接受 |
| **维持 Framework Python** | ✅ 当前默认 | 已装好的不动，达芬奇插件引用 `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` 这个路径。改路径 = 改插件代码 = 风险大 |
| **uv pip 替换 pip** | ✅ 可行 | 在现有 Framework Python 之上，可以用 `uv pip install` 替代 `pip install`，加速依赖安装，不改 Python 解释器路径 |

### 5.3 行动建议

#### 立即可做（低风险高收益）

1. **在本机安装 uv**，用于日常开发和脚本测试：
   ```bash
   brew install uv
   ```

2. **将现有 `install_python313.sh` 升级为双模式**：
   - 默认走 uv（快速、预编译）
   - fallback 到 Framework 安装器（uv 失败时）

3. **新机器/重装机器部署流程改为**：
   ```bash
   brew install uv
   uv python install 3.13.13
   # 如果达芬奇需要 Framework 路径兼容，额外装一份 Framework
   ```

#### 中期规划（需验证）

4. **验证 uv 安装的 Python 3.13 与达芬奇 subprocess 的兼容性**
   — 达芬奇通过 `/Applications/DaVinci Resolve.app/.../python` 启动脚本
   — 脚本里如果硬编码了 `/Library/Frameworks/...` 路径则无法替换
   — 需要读插件启动逻辑确认

5. **用 uv 管理运维脚本自身的依赖**（patrol.py 等）
   — 运维脚本是独立的，不经过达芬奇
   — 可以完全用 uv 管理

#### 不做（明确排除）

6. **不在生产机器上大规模替换已有的 Framework Python**
   — 能跑就不动，风险 > 收益
   — 只在新机和重装机上用新方案

### 5.4 关键文件关联

| 文件 | 影响 |
|------|------|
| `tools/install_python313.sh` | 可升级为 uv-first 安装脚本 |
| `tools/patrol.py` | 运维巡检脚本，可用 uv 管理依赖 |
| `machine_registry.json._config.python_target` | 目标版本 3.13，uv 也应锁定此版本 |
| 插件工坊的 `requirements.txt` | 可迁移到 `pyproject.toml + uv.lock`（插件工坊的事，非运维范围）|

---

## 六、参考链接

- [uv 官方文档](https://docs.astral.sh/uv/)
- [uv 完整指南 (pydevtools.com, 2026-05-08)](https://pydevtools.com/handbook/explanation/uv-complete-guide/)
- [pyenv macOS 完全指南 (lvtao.net, 2025-09)](https://www.lvtao.net/system/macos-python-version-management-pyenv-guide.html)
- [Python 虚拟环境选择对比 (知乎, 2025-01)](https://zhuanlan.zhihu.com/p/663735038)
- [uv 入门教程 (菜鸟教程)](https://www.runoob.com/python3/uv-tutorial.html)
