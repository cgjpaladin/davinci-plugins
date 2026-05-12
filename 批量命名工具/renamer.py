"""
批量文件命名工具 v2.1
所有字段由 FIELD_CONFIG 定义，增删改只碰配置。
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import os, re, json

# ============================================================
# 🔧 字段配置
# ============================================================
FIELD_CONFIG = [
    {"key":"ep",     "label":"Ep(集数)",     "def":"01", "regex":r"^\d{2,3}$"},
    {"key":"sc",     "label":"Sc(场次)",     "def":"01", "regex":r"^\d{2,3}$"},
    {"key":"gr",     "label":"Gr(小场次)",   "def":"01", "regex":r"^\d{2,3}$"},
    {"key":"tk",     "label":"Tk(次数)",     "def":"01", "regex":r"^\d{2,3}$", "inc":True},
    {"key":"desc",   "label":"镜头描述",      "def":"",   "w":16},
    {"key":"author", "label":"制作者",        "def":"",   "w":9},
    {"key":"method", "label":"制作方式",      "def":"",   "w":13},
    {"key":"ver",    "label":"v(版本号)",     "def":"01", "regex":r"^\d{2,3}(\.\d+)?$"},
    {"key":"status", "label":"通过情况",      "def":"OK", "dv":["OK","KP","NG"]},
]

CFG_FILE = os.path.join(os.path.dirname(__file__), ".renamer_saved.json")
# ============================================================

root = TkinterDnD.Tk()
root.title("批量文件命名工具 v2.1")
root.geometry("1120x360")
root.resizable(True, True)

saved = {}
if os.path.exists(CFG_FILE):
    try:
        with open(CFG_FILE,"r",encoding="utf-8") as f: saved = json.load(f)
    except: pass

# ─── 参数区：每列一个 Frame，标签+输入框上下对齐 ───
param_frame = ttk.LabelFrame(root, text="命名参数", padding=6)
param_frame.pack(fill="x", padx=8, pady=(8,4))

widgets = {}
cols = []
for i, fd in enumerate(FIELD_CONFIG):
    col = ttk.Frame(param_frame)
    col.pack(side="left", padx=4, pady=2)
    cols.append(col)

    lbl = fd["label"]
    dv = fd.get("dv")
    w = fd.get("w", 8)
    default = saved.get(fd["key"], fd.get("def",""))

    # 标签（居框上方）
    ttk.Label(col, text=lbl, anchor="w").pack(fill="x")
    
    # 输入框
    if dv:
        wgt = ttk.Combobox(col, values=dv, state="readonly", width=w)
        wgt.set(str(default))
    else:
        wgt = ttk.Entry(col, width=w, justify="left")
        wgt.insert(0, str(default))
    wgt.pack(fill="x")
    widgets[fd["key"]] = (wgt, fd)

    if isinstance(wgt, ttk.Entry):
        wgt.bind("<KeyRelease>", lambda e: root.after(100, update_preview))
    else:
        wgt.bind("<<ComboboxSelected>>", lambda e: update_preview())

# ─── 预览栏（参数区下，文件区上）───
preview_var = tk.StringVar(value="→ 添加文件后显示预览")
preview_bar = ttk.Label(root, textvariable=preview_var, anchor="w",
    font=("Consolas",10), background="#fffacd", padding=6, relief="sunken")
preview_bar.pack(fill="x", padx=8, pady=(0,4))

# ─── 文件区 + 按钮 ───
mid = ttk.Frame(root, padding=(10,6))
mid.pack(fill="both", expand=True)
mid.columnconfigure(0, weight=1)

file_frame = ttk.LabelFrame(mid, text="文件列表", padding=4)
file_frame.grid(row=0, column=0, sticky="nsew", padx=(0,6))
file_frame.rowconfigure(0, weight=1)
file_frame.columnconfigure(0, weight=1)

file_list = tk.Listbox(file_frame, selectmode="extended", font=("Consolas",10))
file_list.grid(row=0, column=0, sticky="nsew")
file_list.bind("<<ListboxSelect>>", lambda e: update_preview())

# 按钮
bpnl = ttk.Frame(mid)
bpnl.grid(row=0, column=1, sticky="ns")
ttk.Button(bpnl, text="📁 添加文件", command=lambda: add_files()).pack(fill="x", pady=2)
ttk.Button(bpnl, text="📂 添加文件夹", command=lambda: add_folder()).pack(fill="x", pady=2)
ttk.Button(bpnl, text="🧹 清空", command=lambda:(file_list.delete(0,tk.END),update_preview())).pack(fill="x", pady=2)
tk.Frame(bpnl, height=16).pack()
go_btn = ttk.Button(bpnl, text="✅ 批量重命名", command=None)
go_btn.pack(fill="x", pady=4)
undo_btn = ttk.Button(bpnl, text="↩ 撤销上次", command=None, state="disabled")
undo_btn.pack(fill="x", pady=2)

# ─── 状态栏 ───
status = ttk.Label(root, text="就绪", anchor="w", padding=(10,4))
status.pack(fill="x")

_undo_stack = []  # [(old_path, new_path), ...]

# ══════ 逻辑 ══════

def get_vals():
    r = []
    for fd in FIELD_CONFIG:
        wgt, _ = widgets[fd["key"]]
        v = wgt.get().strip()
        r.append((fd, v))
    return r

def build_prefix(items):
    s = []
    for fd, v in items:
        lbl = fd["label"]
        # 解析前缀
        if lbl.startswith("Ep("): s.append(f"Ep{v}")
        elif lbl.startswith("Sc("): s.append(f"Sc{v}")
        elif lbl.startswith("Gr("): s.append(f"Gr{v}")
        elif lbl.startswith("Tk("): s.append(f"Tk{v}")
        elif lbl.startswith("v("): s.append(f"v{v}")
        elif lbl == "通过情况": s.append(v)
        else: s.append(v.replace("/","_").replace(" ",""))
    return "_".join(s) if s else "unnamed"

def update_preview():
    errs = []
    for fd in FIELD_CONFIG:
        wgt, _ = widgets[fd["key"]]
        v = wgt.get().strip()
        if not v:
            errs.append(f"「{fd['label']}」不能为空")
            continue
        rx = fd.get("regex")
        if rx and not re.match(rx, v):
            errs.append(f"「{fd['label']}」格式错误")
    if errs:
        preview_var.set("⚠️ " + " | ".join(errs))
        return
    items = get_vals()
    px = build_prefix(items)
    sel = file_list.curselection()
    if sel:
        _, ext = os.path.splitext(file_list.get(sel[0]))
        preview_var.set(f"预览: {px}{ext}  |  选中 {len(sel)} 个")
    else:
        preview_var.set(f"预览: {px}")

def on_drop(event):
    """拖拽文件放入列表"""
    # tkinterdnd2 用 {} 包裹路径，可能有空格和换行
    files = root.tk.splitlist(event.data)
    for f in files:
        f = f.strip()
        if f and os.path.isfile(f) and f not in file_list.get(0, tk.END):
            file_list.insert(tk.END, f)
    update_preview()

def add_files():
    for p in filedialog.askopenfilenames(title="选择文件"):
        if p not in file_list.get(0,tk.END): file_list.insert(tk.END, p)
    update_preview()

def add_folder():
    d = filedialog.askdirectory(title="选择文件夹")
    if not d: return
    for f in sorted(os.listdir(d)):
        fp = os.path.join(d,f)
        if os.path.isfile(fp) and fp not in file_list.get(0,tk.END):
            file_list.insert(tk.END, fp)
    update_preview()

def remove_sel():
    for i in reversed(file_list.curselection()): file_list.delete(i)
    update_preview()

def do_rename():
    sel = file_list.curselection()
    if not sel: messagebox.showwarning("提示","请先选择文件"); return

    for fd in FIELD_CONFIG:
        wgt, _ = widgets[fd["key"]]
        v = wgt.get().strip()
        rx = fd.get("regex")
        if not v:
            messagebox.showerror("参数错误", f"「{fd['label']}」不能为空")
            return
        if rx and not re.match(rx, v):
            messagebox.showerror("参数错误", f"「{fd['label']}」格式错误")
            return

    items = get_vals()
    px = build_prefix(items)

    if not messagebox.askyesno("确认", f"重命名 {len(sel)} 个\n前缀: {px}"):
        return

    # 保存
    sv = {fd["key"]: widgets[fd["key"]][0].get().strip() for fd in FIELD_CONFIG}
    try:
        with open(CFG_FILE,"w",encoding="utf-8") as f: json.dump(sv, f, ensure_ascii=False, indent=2)
    except: pass

    ok = 0; fail = []
    _undo_stack.clear()
    # 找 Tk 字段用于递增
    tk_base = None
    for fd in FIELD_CONFIG:
        if fd.get("inc"):
            tk_base = int(widgets[fd["key"]][0].get().strip() or "1")
            break

    for i, idx in enumerate(sel):
        path = file_list.get(idx)
        folder = os.path.dirname(path)
        _, ext = os.path.splitext(os.path.basename(path))
        # 批量时：每递增一个修改 Tk，重新生成前缀
        if len(sel) > 1 and tk_base is not None:
            tk_val = tk_base + i
            tk_fd = next(fd for fd in FIELD_CONFIG if fd.get("inc"))
            widgets[tk_fd["key"]][0].delete(0, tk.END)
            widgets[tk_fd["key"]][0].insert(0, str(tk_val).zfill(2))
            new_px = build_prefix(get_vals())
            # 恢复原值（不要残留）
            widgets[tk_fd["key"]][0].delete(0, tk.END)
            widgets[tk_fd["key"]][0].insert(0, str(tk_base).zfill(2))
        else:
            new_px = px
        nm = f"{new_px}{ext}"
        np = os.path.join(folder, nm)
        if os.path.exists(np) and np != path:
            fail.append(f"{os.path.basename(path)} → 已存在"); continue
        try:
            os.rename(path, np)
            _undo_stack.append((path, np))
            file_list.delete(idx); file_list.insert(idx, np)
            ok += 1
        except Exception as e:
            fail.append(f"{os.path.basename(path)}: {e}")

    if ok > 0:
        undo_btn.config(state="normal")
    msg = f"✅ {ok}/{len(sel)}"
    if fail: msg += "\n" + "\n".join(fail[:5])
    status.config(text=msg)
    messagebox.showinfo("完成", msg)
    update_preview()


def do_undo():
    if not _undo_stack:
        return
    if not messagebox.askyesno("撤销", f"撤销 {len(_undo_stack)} 个文件的重命名?"):
        return
    undone = 0
    for old_path, new_path in _undo_stack:
        try:
            os.rename(new_path, old_path)
            # 更新文件列表
            for idx in range(file_list.size()):
                if file_list.get(idx) == new_path:
                    file_list.delete(idx)
                    file_list.insert(idx, old_path)
                    break
            undone += 1
        except Exception as e:
            messagebox.showwarning("撤销失败", f"{os.path.basename(new_path)}: {e}")
    _undo_stack.clear()
    undo_btn.config(state="disabled")
    status.config(text=f"↩ 已撤销 {undone} 个")

go_btn.configure(command=do_rename)
undo_btn.configure(command=do_undo)
update_preview()

# 拖放支持（放在最后，所有函数已定义）
file_list.drop_target_register(DND_FILES)
file_list.dnd_bind("<<Drop>>", on_drop)

root.mainloop()
