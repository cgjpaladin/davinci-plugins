#!/usr/bin/env python3
"""跨平台弹窗 — tkinter 子进程统一入口。

所有弹窗通过 subprocess 启动独立 tkinter 进程：
- 不干扰 DaVinci Qt 事件循环
- macOS Cocoa / Windows Win32 原生渲染
- 统一 API，一处编写两平台运行
"""

import subprocess
import sys
import textwrap


def _run_tk(code: str, timeout: int = 120) -> str:
    """运行 tkinter 子进程，返回 stdout（去除首尾空白）。"""
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        stderr = r.stderr.strip()
        if stderr:
            import logging
            logging.warning(f"tk_dialogs: subprocess error\n{stderr[:500]}")
    return r.stdout.strip()


def input_text(prompt: str, title: str = "交付自检工具",
               default: str = "", is_secret: bool = False) -> str:
    """单行文本输入弹窗。is_secret=True → 密码模式。"""
    show = "show='*'" if is_secret else ""
    code = textwrap.dedent(f"""
        import tkinter as tk
        root = tk.Tk()
        root.title({repr(title)})
        root.resizable(False, False)
        tk.Label(root, text={repr(prompt)}, pady=6).pack()
        entry = tk.Entry(root, width=50, {show})
        entry.pack(padx=10, pady=4)
        entry.insert(0, {repr(default)})
        entry.focus_set()
        result = [""]
        def on_ok():
            result[0] = entry.get()
            root.destroy()
        def on_cancel():
            root.destroy()
        tk.Button(root, text="确定", command=on_ok, width=10).pack(side="left", padx=10, pady=8)
        tk.Button(root, text="取消", command=on_cancel, width=10).pack(side="right", padx=10, pady=8)
        entry.bind("<Return>", lambda e: on_ok())
        root.eval('tk::PlaceWindow . center')
        root.mainloop()
        print(result[0])
    """).strip()
    return _run_tk(code)


def choose_file(prompt: str = "选择文件",
                filetypes: list[tuple[str, str]] = None) -> str:
    """文件选择器弹窗。返回选中文件路径，取消返回空字符串。"""
    if filetypes is None:
        filetypes = [("所有支持格式", ".txt .pdf .docx .doc .md"),
                     ("全部文件", "*.*")]
    ft_code = ", ".join(
        f'({repr(name)}, {repr(ext)})' for name, ext in filetypes)
    code = textwrap.dedent(f"""
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title={repr(prompt)}, filetypes=[{ft_code}])
        root.destroy()
        if path:
            print(path)
    """).strip()
    return _run_tk(code)


def choose_folder(prompt: str = "选择文件夹") -> str:
    """文件夹选择器弹窗。返回选中路径，取消返回空字符串。"""
    code = textwrap.dedent(f"""
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askdirectory(title={repr(prompt)})
        root.destroy()
        if path:
            print(path)
    """).strip()
    return _run_tk(code)
