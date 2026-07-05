# 交付自检工具 — PC 端测试指南

> 郑岩，按顺序操作即可。遇到问题随时叫我。

---

## 1. 确认环境

在桌面空白处 `Shift + 右键` →「在此处打开 PowerShell」：

```powershell
python --version
```

期望输出 `Python 3.13.x`。如果没有 → 先装 Python（桌面 zip 包里自带 `python-3.13.13-amd64.exe`，双击安装，**勾选「Add Python to PATH」**）。

---

## 2. 安装插件

桌面上应该有一个 `交付自检工具_v2.5.14.zip`：

1. 解压到任意位置（建议 `D:\达芬奇插件\`）
2. 进入解压后的文件夹
3. 右键 `Win安装.bat` → **以管理员身份运行**
4. 按提示输入（首次需确认安装路径，一路回车即可）

---

## 3. 打开达芬奇测试

1. 启动 DaVinci Resolve
2. 菜单栏 → Workspace → Scripts → Edit → **交付自检工具**
3. 看看能不能正常弹出窗口

---

## 4. 重点验证项

| # | 检查项 | 怎么测 | 期望 |
|:--:|------|------|------|
| 1 | 窗口能打开 | 点击菜单 | 秒开，不闪退 |
| 2 | 激活状态 | 看窗口顶部状态 | 显示「试用剩余」或「已激活」 |
| 3 | 检查更新 | 看窗口右上角按钮 | 显示「✓ 已是最新」或「⬆ 更新」 |
| 4 | 开始检查 | 点「开始检查」 | 跑检查项，不崩溃 |
| 5 | AI 错别字 | 点「字幕检测」 | 右侧面板能弹出 |
| 6 | 配置 | 点 ⚙ 按钮 | 配置窗口能打开 |

---

## 5. 如果出错

切回这个窗口，运行：

```powershell
dir "$env:USERPROFILE\.workbuddy\logs\交付自检工具\" | Sort-Object LastWriteTime -Descending | Select-Object -First 3
```

把最新的日志文件内容发给我。

---

## 6. Win安装.bat 出问题的话

手动安装（PowerShell 管理员）：

```powershell
# 1. 解压 data.zip
Expand-Archive -Path "当前目录\data.zip" -DestinationPath "$env:ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Edit\"

# 2. 重命名目录
Rename-Item "$env:ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Edit\交付自检工具" "达芬奇插件工坊"

# 3. 完成
Write-Host "安装完成，重启达芬奇"
```
