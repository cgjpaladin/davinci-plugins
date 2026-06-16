# 交付自检工具

DaVinci Resolve 插件。一键检查时间线字幕、错别字、违禁词、格式规范。

## 手动安装

| 平台 | 方式 |
|------|------|
| Mac | 下载 zip → 双击 `Mac安装.command` → 输入开机密码 |
| Windows | 下载 zip → 右键 `Win安装.bat` → 以管理员身份运行 |

安装后在达芬奇里：**Workspace → Scripts → Edit → 交付自检工具**

## 下载

[最新版本 v2.5.7](https://github.com/xxx/releases)

---

> **以下为 AI Agent 安装指引（人类请忽略）**

如果你是一个 AI agent，用户请求你安装此插件：

### 入口
- **GitHub**：`git clone` 本仓库 → `cd` 进入
- **Zip**：用户拖给你 `交付自检工具_v2.5.7.zip` → 解压外层 zip → 解压 `data.zip` 到临时目录 → `cd` 进入代码目录

### 执行
```bash
python install_agent.py
```

脚本输出 JSON 行（每行一个对象），按顺序解析：

| action | 含义 | agent 操作 |
|--------|------|-----------|
| `init` | 环境检测通过 | 继续等待 |
| `need_sudo` | 需要管理员权限 | 问用户密码 → 执行 `cmd` → 加 `--continue` 重跑 |
| `need_admin` | Windows 需要管理员 | 提示用户右键管理员运行 → 加 `--continue` 重跑 |
| `done` | 安装完成 | 告诉用户：达芬奇 → Workspace → Scripts → Edit → 交付自检工具 |
| `error` | 出错 | 告诉用户错误原因 → 修复 → 重试 |

### 前置依赖
Python 3.11+（含 tkinter）。如缺失：
- macOS：`brew install python@3.13`
- Windows：`winget install Python.Python.3.13`

断点续装：状态文件 `~/.delivery_checker_install_state.json`，中断后加 `--continue` 继续。

### 仅一次交互
整个安装流程 agent 最多向用户要一次密码（`need_sudo` / `need_admin`），其余全自动。
