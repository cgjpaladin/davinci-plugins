# UI 去重保护 — 修复方案

> 两个插件都是外部 subprocess 启动，达芬奇不会自动防重复窗口。用户连续点两次菜单 → 两个独立窗口，第二个连不上达芬奇、按钮灰掉、日志乱写。
>
> 2026-05-13 小裁缝整理

---

## 改哪个文件

| 插件 | 文件 | 插入位置 |
|------|------|---------|
| AI去字幕 | `AI去字幕/stable_ui.py` | `main()` 函数第一行 |
| 交付自检工具 | `交付自检工具/ui.py` | `main()` 函数第一行（如果有的话），否则在 `dlg.Show()` 之前 |

---

## 要插入的代码

在两个文件的 `import` 区已有 `import subprocess, sys`，只需在窗口显示前加 5 行：

```python
# 防重复窗口（外部进程独有问题，FindWindow 跨进程无效）
import subprocess as _sp, os as _os
_result = _sp.run(["pgrep", "-f", _os.path.basename(__file__)], capture_output=True, text=True)
if len(_result.stdout.strip().split("\n")) > 1:
    sys.exit(0)
```

---

## AI去字幕 具体操作

文件：`/Users/bryan/WorkBuddy/达芬奇插件工坊/AI去字幕/stable_ui.py`

找到 `def main():` 函数（约第 143 行），在函数体第一行 `try:` **之前**插入上述代码。

```python
def main():
    """显示 UI 窗口并进入事件循环（阻塞直到用户关闭）。窗口打开后刷余额。"""
    # ← 在这里插入防重复代码
    try:
        dlg.Show()
        ...
```

---

## 交付自检工具 具体操作

文件：`/Users/bryan/WorkBuddy/达芬奇插件工坊/交付自检工具/ui.py`

找到 `if __name__ == "__main__":` 块（通常在文件末尾），在 `dlg.Show()` **之前**插入上述代码。

```python
if __name__ == "__main__":
    # ← 在这里插入防重复代码
    dlg.Show()
    disp.RunLoop()
    dlg.Hide()
```

---

## 原理

- `pgrep -f <脚本名>` 列出所有包含该脚本名的进程
- 如果结果 > 1 行（自身 + 另一个实例），说明已有窗口在跑
- 直接 `sys.exit(0)` 退出，不创建新窗口

为什么不用 `FindWindow`：`FindWindow` 是 dispatcher 级别的方法，外部进程的 dispatcher 是独立实例，跨进程找不到另一进程的窗口。HEIBA 等内嵌脚本不需要这个因为达芬奇不会重复触发同一脚本。

---

## 验证方式

1. 在达芬奇里启动插件 → 窗口正常打开
2. 不关窗口，再次启动插件 → 应该静默退出，不弹出第二个窗口
3. 关掉窗口，再次启动 → 窗口正常打开
