# Python 虚拟环境策略：隔离、验证与集群部署

> **来源**：
> - https://blog.csdn.net/a772304419/article/details/145733773 (pyvenv.cfg 详解)
> - https://docs.python.org/3.13/tutorial/venv.html (Python 官方 venv 教程, Python 3.13 文档)
> - https://developer.cloud.tencent.com/article/2588759 (Python 多版本管理)
>
> **发布日期**：综合 2025.02 ~ 2025.12 (CSDN 2025-02 / Python 官方持续更新 / 腾讯云 2025-11)
>
> **适用版本范围**：Python 3.3+ (venv 自 3.3 进入标准库)，pyvenv.cfg 格式通用
>
> **对我们环境的适用性**：✅ **直接适用**。我们 19 台 Mac mini M4 运行达芬奇插件和运维脚本，虚拟环境是隔离多 Python 版本（3.9/3.13/3.14 + 达芬奇内嵌 3.6）的唯一可靠方案。之前 `python_env_audit.sh` 已覆盖基础审计，本文补充策略层面。

---

## 一、venv 隔离原理深度解析

### 1.1 虚拟环境的本质

venv 创建的是一个**轻量级"影子"Python**，不是一个完整的独立安装：

```
myenv/
├── bin/                    # (macOS/Linux) 或 Scripts\ (Windows)
│   ├── activate            # 激活脚本（修改 PATH + 提示符）
│   ├── python              # → 指向原始解释器的链接
│   └── pip                 # → 环境专属的 pip
├── lib/
│   └── pythonX.Y/
│       └── site-packages/  # ← 独立的包安装目录（核心！）
└── pyvenv.cfg             # ← 配置文件（灵魂）
```

**关键认知**：`bin/python` 不是完整解释器，而是指向创建该 venv 的原始 Python 的**链接/副本**。其行为被 `pyvenv.cfg` 修改。

### 1.2 pyvenv.cfg 字段速查

| 字段 | 含义 | 示例 | 可修改 |
|------|------|------|--------|
| `home` | 原始 Python 安装目录 | `/Library/Frameworks/Python.framework/Versions/3.13` | ⚠️ 迁移时需改 |
| `include-system-site-packages` | 是否继承系统全局包 | `false` / `true` | ✅ |
| `version` | Python 版本号 | `3.13.13` | ❌ 只读 |
| `executable` | 原始 Python 可执行文件路径 | `/path/to/python3` | ⚠️ 迁移时需改 |
| `command` | 创建时的完整命令记录 | `python3 -m venv myenv` | ❌ 历史记录 |

### 1.3 `include-system-site-packages` 的关键决策

这是 **最重要的安全配置项**，直接影响隔离性：

```bash
# 默认 false = 完全隔离（推荐 ✅）
python -m venv myenv          # include-system-site-packages = false

# 继承系统包（慎用 ⚠️）
python -m venv --system-site-packages myenv  # = true
```

| 设定值 | 行为 | 适用场景 |
|--------|------|----------|
| `false`（默认） | **完全隔离**，看不到系统全局包 | ✅ 绝大多数场景，尤其是插件/脚本 |
| `true` | 能看到并使用系统全局包，但 venv 内安装的优先级更高 | 极少数需要大型编译库的场景 |

**对我们环境的铁律**：
- 达芬奇插件内的 venv：**必须 `false`**（防止全局包污染插件行为）
- 运维脚本 venv：**必须 `false`**（保证跨机器一致性）
- 永远不设 `true`——我们的场景没有需要继承系统包的理由

### 1.4 激活机制（PATH 修改）

激活脚本只做两件事：

1. **修改 shell 提示符**：添加 `(envname)` 前缀
2. **将 venv/bin 插入 PATH 最前面**：

```bash
# 激活前
PATH=/usr/local/bin:/usr/bin:/bin

# 激活后 (source myenv/bin/activate)
PATH=/Users/bryan/myenv/bin:/usr/local/bin:/usr/bin:/bin
```

运行 `python` 时，shell 先找到 `myenv/bin/python` → 使用 venv 版本。

**sys.path 变化**：

```python
import sys
# 激活后 sys.path 中 venv 的 site-packages 排在前面：
# ['', '.../myenv/lib/python3.13/site-packages', '/Library/Frameworks/...']
# ↑ venv 优先生效
```

---

## 二、虚拟环境不可迁移！

### 2.1 为什么不能复制 venv

`pyvenv.cfg` 中硬编码了**创建机器的绝对路径**：

```cfg
home = /Library/Frameworks/Python.framework/Versions/3.13
executable = /Library/Frameworks/Python.framework/Versions/3.13/bin/python3
command = /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv /Users/bryan/project/env
```

直接 `scp -r` 到另一台机器 → 路径不存在 → `Fatal error in launcher: ...`

### 2.2 正确的跨机器方案

**不要迁移 venv，迁移声明文件**：

```
机器 A                          机器 B
┌─────────────┐                ┌─────────────┐
│ pyproject.toml│ ───── copy ──→│ pyproject.toml│
│ uv.lock      │ ───── copy ──→│ uv.lock      │
└──────┬──────┘                └──────┬──────┘
       │ uv sync                       │ uv sync
       ▼                               ▼
┌─────────────┐                ┌─────────────┐
│ .venv/ (A)  │                │ .venv/ (B)  │
└─────────────┘                └─────────────┘
# 内容一致，但各自独立创建
```

**传统方案等价物**：

```
requirements.txt ──copy──→  requirements.txt
                            ↓ pip install -r
                        .venv/ (独立创建)
```

### 2.3 同机迁移修复（仅限路径变更）

如果只是 Python 安装路径变了（如 Homebrew 重装），可手动改 `pyvenv.cfg`：

```bash
# 编辑 .venv/pyvenv.cfg 中的 home / executable / command
# 改为新路径
vim .venv/pyvenv.cfg

# 然后重装 pip（符号链可能断裂）
.venv/bin/python -m ensurepip --upgrade
```

---

## 三、多版本共存时的 veng 管理策略

### 3.1 我们的混乱现状

| 来源 | 版本 | 路径 | 机器数 |
|------|------|------|--------|
| 系统 Python (macOS 自带) | 3.9.6 | `/usr/bin/python3` | 3 台 |
| Framework Python | 3.13.13 | `/Library/Frameworks/Python.framework/...` | 3 台 (102,132,136,138) |
| Homebrew/其他 | 3.14.3 | `/opt/homebrew/bin/python3` | 1 台 |
| 达芬奇内嵌 | 3.6 | DR bundle 内部 | 全部 |

### 3.2 选择正确的 Python 创建 venv

```bash
# ❌ 错误：不确定用的是哪个 python
python3 -m venv myenv

# ✅ 正确一：用绝对路径
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv myenv

# ✅ 正确二：用 managed Python
~/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -m venv myenv

# ✅ 正确三：用 uv（自动处理版本）
uv venv --python 3.13
```

**创建后立即验证**：

```bash
# 检查 pyvenv.cfg 中的 home 是否正确
cat .venv/pyvenv.cfg

# 确认 Python 版本
.venv/bin/python3 --version

# 确认隔离性（不应看到系统包）
.venv/bin/python3 -c "import sys; print([p for p in sys.path if 'site-packages' in p])"

# 确认 include-system-site-packages=false
grep 'include-system' .venv/pyvenv.cfg
```

### 3.3 subprocess 中使用 venv 的安全模式

这是达芬奇插件和运维脚本最关键的坑：

```python
import subprocess, sys, os

# ❌ 危险：依赖 PATH，可能调到错误 python
subprocess.run(["python3", "script.py"])

# ❌ 危险：shell=True 继承 os.environ
subprocess.run("python3 script.py", shell=True)

# ✅ 安全一：用当前解释器的绝对路径
subprocess.run([sys.executable, "script.py"])

# ✅ 安全二：用 venv 的绝对路径
VENV_PYTHON = "/path/to/.venv/bin/python3"
subprocess.run([VENV_PYTHON, "script.py"], env={**os.environ, "PATH": "/usr/bin:/bin"})

# ✅ 安全三：指定 python 并清空 PATH（最强隔离）
subprocess.run(
    ["/absolute/path/to/python3", "script.py"],
    env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}  # 最小 PATH
)
```

---

## 四、生产 Checklist

### 4.1 创建 venv 时

- [ ] 用绝对路径或 `uv venv --python X.Y` 创建（不用裸 `python3 -m venv`）
- [ ] 确认 `include-system-site-packages=false`
- [ ] 目录名用 `.venv`（点开头隐藏）
- [ ] `.gitignore` 加入 `.venv/`, `venv/`

### 4.2 依赖管理时

- [ ] 用 `requirements.in` + `pip-compile` 或 `pyproject.toml` + `uv lock`（不用 `pip freeze > requirements.txt`）
- [ ] 锁文件纳入版本控制
- [ ] CI/CD 用 `pip-sync` 或 `uv sync --frozen`（不用 `pip install -r`）

### 4.3 跨机器部署时

- [ ] 传递声明文件（`.in` / `pyproject.toml` + lock），**不传递 venv 目录**
- [ ] 目标机上重新 `pip-sync` 或 `uv sync`
- [ ] 部署后跑 `pipdeptree --freeze` 对比依赖树

### 4.4 达芬奇插件特殊要求

- [ ] venv 创建在插件目录内或 `~/Library/Application Support/` 下
- [ ] `include-system-site-packages=false`（铁律）
- [ ] subprocess 调用子进程必须用 `sys.executable` 或绝对路径
- [ ] 不假设任何全局包可用（包括 requests, psycopg2 等）

### 4.5 故障排查速查

| 症状 | 原因 | 修复 |
|------|------|------|
| `Fatal error in launcher` | venv 被复制到另一台机器 | 删除重建，不要 scp venv |
| `ModuleNotFoundError` 但全局有这个包 | `include-system-site-packages=false`（正常的） | 在 venv 里 `pip install` |
| `pip install` 装到了全局而不是 venv | 未激活 venv 就执行了 pip | 先 `source .venv/bin/activate` |
| 脚本在 A 机器正常 B 机器报错 | B 机器缺少依赖或 Python 版本不同 | 检查 `pyvenv.cfg` + 重新 `uv sync` |
| subprocess 调用了错误的 Python | 依赖 PATH 解析 python | 改用 `sys.executable` 或绝对路径 |

---

## 五、vnev vs virtualenv vs uv venv 对比

| 特性 | stdlib `venv` | `virtualenv` | `uv venv` |
|------|--------------|-------------|-----------|
| 安装需求 | 无（标准库） | `pip install virtualenv` | `pip install uv` |
| 创建速度 | 快 | 较慢（拷贝更多文件） | 极快（Rust） |
| 种子包支持 | ❌ | ✅（--seed） | ✅ |
| 创建者缓存 | ❌ | ✅（加速重复创建） | ✅ |
| Python 版本切换 | ❌（绑定创建时版本） | ❌ | ✅（`--python 3.12`） |
| PEP 621 集成 | ❌ | 部分 | ✅ 原生 |
| 推荐场景 | 简单项目 / 插件内 | 需要种子包的复杂项目 | **我们的运维工具首选** |

**结论**：对于我们的环境（19 台 M4 Mac 运维脚本 + 达芬奇插件）：
- **运维脚本层**：`uv venv`（快、自动版本管理、一体化）
- **达芬奇插件层**：stdlib `venv`（零依赖、达芬奇内嵌即可用）
