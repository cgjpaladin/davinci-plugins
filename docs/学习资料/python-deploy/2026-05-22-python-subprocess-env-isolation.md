# Python 子进程环境隔离与 venv 深度指南

> 日期：2026-05-22（周五 · Python 部署）
> 来源：CSDN pyvenv.cfg 解析 + Deepinout subprocess+venv 实践 + markaicode.com Python 3.13 排障
> 关联工具：`tools/python_env_audit.sh`

---

## 一、核心问题

达芬奇插件运行在达芬奇内嵌的 Python 3.13 环境中（`/Applications/DaVinci Resolve.framework/Resources/python/lib/python3.13/`），同时通过 `subprocess` 调用外部命令。**子进程默认继承父进程的完整 `os.environ`**，这导致：

1. **PATH 污染**：子进程可能找到系统 Python 而非达芬奇内嵌 Python
2. **site-packages 泄露**：`include-system-site-packages=true` 时，全局安装的包会污染插件环境
3. **VIRTUAL_ENV 未传递**：达芬奇不是在 venv 中启动的，子进程没有 VIRTUAL_ENV 标识
4. **PYTHONHOME 干扰**：如果设置了 PYTHONHOME，Python 解释器会找错库路径

---

## 二、pyvenv.cfg 字段速查表

| 字段 | 含义 | 我们的场景 |
|------|------|-----------|
| `home` | 父级 Python 环境路径 | 达芬奇内嵌 = `/Applications/DaVinci Resolve.framework/...` |
| `implementation` | CPython / PyPy 等 | 固定 CPython |
| `version_info` | 精确版本号 | `3.13.x.final.0` |
| `include-system-site-packages` | 是否共享全局包 | ⚠️ **关键开关，详见下文** |
| `base-prefix` / `base-exec-prefix` | 父环境路径 | 同 home |
| `base-executable` | 父环境解释器绝对路径 | 必须指向达芬奇内嵌 python3 |

### include-system-site-packages 的两种模式

| 设置值 | 行为 | 适用场景 |
|--------|------|---------|
| `false`（默认）✅ | 彻底隔离，只用 venv 自带的包 | 达芬奇插件、生产环境 |
| `true` | 继承父环境的 site-packages | 开发调试时临时用 |

**我们的结论**：达芬奇插件必须保持 `false`。如果设为 `true`，Homebrew/Framework Python 安装的包会混入达芬奇环境，导致不可预测的 import 行为。

---

## 三、subprocess + venv 正确用法矩阵

### 方法 1：绝对路径指定解释器（⭐⭐⭐⭐⭐ 最可靠）

```python
import subprocess

# 直接指定达芬奇内嵌 Python
davinci_python = "/Applications/DaVinci Resolve.framework/Resources/python/bin/python3"
subprocess.run([davinci_python, "script.py"])
```

### 方法 2：sys.executable（⭐⭐⭐⭐⭐ 同环境最佳）

```python
import sys, subprocess

# sys.executable 始终指向当前运行的 Python 解释器
subprocess.run([sys.executable, "script.py"])
```

> **这是达芬奇插件内的首选方案**——因为插件代码本身就在达芬奇的 Python 3.13 中运行，sys.executable 自动指向正确位置。

### 方法 3：env 参数显式传递干净环境（⭐⭐⭐⭐ 需要精细控制时）

```python
import subprocess, os, sys

clean_env = os.environ.copy()
# 确保 PATH 不引入其他 Python
clean_env["PATH"] = f"{os.path.dirname(sys.executable)}:{clean_env.get('PATH', '')}"
# 清空可能干扰的变量
clean_env.pop("PYTHONHOME", None)
clean_env.pop("PYTHONPATH", None)

subprocess.run(["python", "script.py"], env=clean_env)
```

### ❌ 常见错误

```python
# 错误1: activate 效果不会跨进程传递！
subprocess.run("source /path/to/venv/bin/activate", shell=True)  # 进程A退出后环境变量丢失
subprocess.run("python script.py", shell=True)                   # 进程B用的还是原始环境！

# 错误2: shell=True + 不指定解释器 → 可能找到系统 python
subprocess.run("python script.py", shell=True)  # PATH 里第一个 python 不一定是想要的

# 错误3: 继承全部环境变量，包含被污染的 PATH
subprocess.run(["python", "script.py"])  # env=os.environ 默认继承全部
```

---

## 四、达芬奇插件环境链路分析

```
达芬奇主进程 (macOS native)
  └─ Fusion/Resolve 内嵌 Python 3.13 (sys.executable 指向这里)
       ├─ 插件代码运行在此环境中
       │    └─ import 的包来自:
       │         ├── /Applications/DaVinci Resolve.framework/.../lib/python3.13/ (标准库)
       │         ├── /Applications/DaVinci Resolve.framework/.../site-packages/ (达芬自带)
       │         └── 插件目录下的模块
       │
       └─ subprocess.run() 调用子进程
            └─ 默认继承父进程 os.environ
                 └─ PATH 中的第一个 "python" 决定了解释器是谁！
```

### 对我们意味着什么

| 问题 | 影响 | 我们的环境是否受影响 | 解决方案 |
|------|------|---------------------|---------|
| PATH 中有 Homebrew Python | 子进程可能用 `/opt/homebrew/bin/python3.13` 而非达芬奇内嵌 | ✅ **是** — 3 台机器装了 Framework Python 3.13 | subprocess 中始终用 `[sys.executable, ...]` |
| 全局 pip 装了同名但不同版本的包 | import 可能拿到错误的包 | ⚠️ **潜在风险** — 如果有人 `sudo pip3 install` 过 | 定期审计全局 site-packages |
| 达芬奇内嵌 Python 无 pip | 无法直接在达芬奇环境装包 | ✅ **已知限制** | 用 `sys.prefix` 确认路径后手动拷贝 |
| subprocess 中 shell=True | 触发 shell PATH 解析，不可控 | ✅ **高风险** | 禁止 shell=True，始终 list 传参 |

---

## 五、Python 环境诊断清单

当遇到「import 失败」「找不到模块」「版本不对」等问题时：

```
1. 确认当前解释器：
   $ which python
   $ python -c "import sys; print(sys.executable)"
   $ python -c "import sys; print(sys.path)"

2. 确认 site-packages 来源：
   $ python -c "import pkg_resources; print([p.project_name for p in pkg_resources.working_set])"

3. 确认 pyvenv.cfg（如果有 venv）：
   $ cat .venv/pyvenv.cfg | grep include-system

4. 确认 PATH 优先级：
   $ echo $PATH | tr ':' '\n' | grep python

5. 确认是否有 PYTHONHOME/PYTHONPATH 干扰：
   $ echo $PYTHONHOME
   $ echo $PYTHONPATH
```

---

## 六、Python 3.13 特殊注意事项

根据 markaicode.com (2025-08) 实测报告：

| 问题 | 表现 | 解决方案 |
|------|------|---------|
| SSL 证书错误 | `pip install` 报 SSL CERTIFICATE_VERIFY_FAILED | 重装 OpenSSL 或用 `--trusted-host` |
| 包兼容性缺口 | 部分 PyPI 包尚未适配 3.13 | 先试 `pip install --pre <pkg>` 或锁定旧版 |
| 路径冲突（多 Python 共存） | `/usr/bin/python3`(系统) vs `/opt/homebrew/bin/python3.13` vs Framework | 创建 venv 时**始终用显式完整路径** |

### 我们的 19 台机器 Python 来源现状（已知）

| 来源 | 数量 | 路径特征 |
|------|------|---------|
| 系统 Python 3.9.6 | 3台 | `/usr/bin/python3` |
| 系统 Python 3.14.3 | 1台 | `/usr/bin/python3` |
| 系统 Python 3.13.13 | 3台 | `/usr/bin/python3` |
| Framework Python 3.13.13 | 4台 | `/Library/Frameworks/...` |
| 达芬奇内嵌 3.6.x | 全部 | 达芬奇 .framework 内 |

**关键发现**：同一台机器上最多存在 3 个不同的 Python。达芬奇插件通过 fusionscript 加载时用的是达芬奇内嵌的那个，而 `subprocess` 默认走 PATH 第一个。

---

## 七、生产环境 Checklist

- [ ] 所有 `subprocess.run()` 调用都使用 `[sys.executable, ...]` 或绝对路径
- [ ] 禁止使用 `shell=True`（除非必要且已确认 PATH 安全）
- [ ] 插件代码不依赖全局 `site-packages`
- [ ] `include-system-site-packages = false`（所有 venv）
- [ ] 不设置 `PYTHONHOME` 和 `PYTHONPATH` 环境变量
- [ ] 新机器部署后执行 `python_env_audit.sh --full` 验证环境干净度
- [ ] 定期检查是否有 `sudo pip3 install` 污染全局环境
