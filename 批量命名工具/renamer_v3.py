"""
批量文件命名工具 v3.0
- Inspector = 选中项编辑器，修改只作用于当前选中的文件
- 多选时若某字段值不一致 → 显示空白
- Tk 按选中顺序自动递增
- 快捷键: Ctrl+Z 撤销, Del 移除选中
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import os, re, json

# ============================================================
# 字段配置
# ============================================================
FIELD_CONFIG = [
    {"key":"ep",     "name":"Ep",  "label":"Ep 集数",     "def":"01", "regex":r"^\d{2,3}$"},
    {"key":"sc",     "name":"Sc",  "label":"Sc 场次",     "def":"01", "regex":r"^\d{2,3}$"},
    {"key":"gr",     "name":"Gr",  "label":"Gr 小场次",   "def":"01", "regex":r"^\d{2,3}$"},
    {"key":"tk",     "name":"Tk",  "label":"Tk 次数",     "def":"01", "regex":r"^\d{2,3}$", "inc":True},
    {"key":"desc",   "name":"",    "label":"镜头描述",     "def":"",   "w":16},
    {"key":"author", "name":"",    "label":"制作者",       "def":"",   "w":9},
    {"key":"method", "name":"",    "label":"制作方式",     "def":"",   "w":13},
    {"key":"ver",    "name":"v",   "label":"v 版本号",     "def":"01", "regex":r"^\d{2,3}(\.\d+)?$"},
    {"key":"status", "name":"",    "label":"通过情况",     "def":"OK", "dv":["OK","KP","NG","自定义…"]},
]

CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".renamer_saved.json")

# ============================================================
# 设计 Token
# ============================================================
T = {
    "bg":       "#1c1c1c",
    "surface":  "#282828",
    "border":   "#3d3d3d",
    "text":     "#b8b8b8",
    "text_dim": "#707070",
    "accent":   "#e8870a",
    "accent2":  "#6a9a3a",
    "ff_ui":    "Segoe UI",
    "ff_mono":  "Consolas",
}

# ============================================================
# Style
# ============================================================
def setup_styles(s):
    s.configure("App.TFrame",     background=T["bg"])
    s.configure("Surface.TFrame", background=T["surface"])
    s.configure("Title.TLabel",   background=T["surface"], foreground=T["text_dim"], font=(T["ff_ui"], 10))
    s.configure("Param.TLabel",   background=T["bg"],      foreground=T["text_dim"], font=(T["ff_ui"], 8))
    s.configure("Preview.TLabel", background=T["surface"], foreground=T["accent2"],  font=(T["ff_mono"], 11))
    s.configure("HeroMeta.TLabel",background=T["surface"], foreground=T["text_dim"], font=(T["ff_ui"], 9))
    s.configure("Status.TLabel",  background=T["bg"],      foreground=T["text_dim"], font=(T["ff_ui"], 9))
    s.configure("HeroBtn.TButton",
        background=T["accent"], foreground="#ffffff", font=(T["ff_ui"], 10, "bold"),
        borderwidth=0, padding=(14, 4))
    s.map("HeroBtn.TButton", background=[("active", "#ff9a2e")])
    s.configure("UndoBtn.TButton",
        background=T["surface"], foreground=T["text_dim"], font=(T["ff_ui"], 9), padding=(8, 2))
    s.configure("Small.TButton",
        background=T["surface"], foreground=T["text"], font=(T["ff_ui"], 9), padding=(8, 1))
    s.configure("Trees.Treeview",
        background=T["bg"], foreground=T["text"], fieldbackground=T["bg"],
        borderwidth=0, rowheight=24, font=(T["ff_mono"], 9))
    s.configure("Trees.Treeview.Heading",
        background=T["surface"], foreground=T["text_dim"], font=(T["ff_ui"], 9),
        borderwidth=0, padding=(0, 2))
    s.map("Trees.Treeview", background=[("selected", "#3a2010")], foreground=[("selected", T["text"])])

# ============================================================
# 数据模型
# ============================================================
class FileEntry:
    __slots__ = ("path", "fields")
    def __init__(self, path, defaults):
        self.path = path
        self.fields = {}
        for fd in FIELD_CONFIG:
            k = fd["key"]
            self.fields[k] = defaults.get(k, fd["def"]) if defaults else fd["def"]

    @property
    def basename(self):  return os.path.basename(self.path)
    @property
    def ext(self):
        _, e = os.path.splitext(self.basename); return e
    def new_name(self):
        return _build_filename(self.fields) + self.ext

# ============================================================
# 全局状态
# ============================================================
_entries = []            # [FileEntry, ...]
_undo_stack = []         # [(old_path, new_path), ...]
_saved_defaults = {}     # 持久化默认值
_refreshing = False      # 防 Treeview 重建时触发选择事件

if os.path.exists(CFG_FILE):
    try:
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            _saved_defaults = json.load(f)
    except: pass

# ============================================================
# 主窗口
# ============================================================
root = TkinterDnD.Tk()
root.title("批量文件命名工具")
root.geometry("840x520")
root.minsize(640, 360)
root.configure(bg=T["bg"])

style = ttk.Style()
style.theme_use("clam")
setup_styles(style)

# ═══ 标题栏 ═══
titlebar = ttk.Frame(root, style="Surface.TFrame")
titlebar.pack(fill="x")

dots = tk.Canvas(titlebar, width=36, height=18, bg=T["surface"], highlightthickness=0)
dots.pack(side="left", padx=(8, 4), pady=2)
dots.create_oval(4, 6, 10, 12, fill=T["accent"], outline="")
dots.create_oval(14, 6, 20, 12, fill="#555", outline="")
dots.create_oval(24, 6, 30, 12, fill="#555", outline="")

ttk.Label(titlebar, text="批量文件命名工具", style="Title.TLabel").pack(side="left")

# ═══ Inspector (9 字段同一行) ═══
insp_frame = ttk.Frame(root, style="App.TFrame")
insp_frame.pack(fill="x", padx=8, pady=(6, 0))

_widgets = {}   # key → widget

for fd in FIELD_CONFIG:
    col = ttk.Frame(insp_frame, style="App.TFrame")
    w = fd.get("w", 8)
    if fd["key"] == "desc":
        col.pack(side="left", fill="x", expand=True, padx=2)  # wider
    else:
        col.pack(side="left", fill="x", expand=True, padx=2)

    ttk.Label(col, text=fd["label"], style="Param.TLabel").pack(anchor="w")

    dv = fd.get("dv")
    default = str(_saved_defaults.get(fd["key"], fd["def"]))

    if dv:
        wgt = ttk.Combobox(col, values=dv, state="readonly", width=w if w < 10 else 6,
                           font=(T["ff_mono"], 10))
        wgt.set(default)
    else:
        wgt = ttk.Entry(col, width=w, font=(T["ff_mono"], 10))
        wgt.insert(0, default)
    wgt.pack(fill="x")
    _widgets[fd["key"]] = (wgt, fd)

# 通过情况「自定义…」→ 切换为可输入
def _on_status_custom(event=None):
    wgt, _ = _widgets["status"]
    if wgt.get() == "自定义…":
        wgt.configure(state="normal")
        wgt.set("")
        wgt.focus_set()
    else:
        wgt.configure(state="readonly")
        _on_param_change()

status_wgt, _ = _widgets["status"]
status_wgt.bind("<<ComboboxSelected>>", _on_status_custom, add="+")
status_wgt.bind("<FocusOut>", lambda e: _on_param_change(), add="+")

# ═══ Hero (预览 + 按钮) ═══
hero = ttk.Frame(root, style="App.TFrame")
hero.pack(fill="x", padx=8, pady=(6, 0))

hero_inner = ttk.Frame(hero, style="Surface.TFrame")
hero_inner.pack(fill="x")

pf = ttk.Frame(hero_inner, style="Surface.TFrame")
pf.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=6)

ttk.Label(pf, text="▸", foreground=T["accent2"], background=T["surface"],
          font=(T["ff_ui"], 13, "bold")).pack(side="left", padx=(0, 6))
preview_var = tk.StringVar(value="添加文件后显示预览")
ttk.Label(pf, textvariable=preview_var, style="Preview.TLabel").pack(side="left", fill="x", expand=True)
meta_var = tk.StringVar(value="")
ttk.Label(pf, textvariable=meta_var, style="HeroMeta.TLabel").pack(side="right", padx=(8, 0))

btns = ttk.Frame(hero_inner, style="Surface.TFrame")
btns.pack(side="right", padx=(0, 8), pady=6)
go_btn = ttk.Button(btns, text="批量重命名", style="HeroBtn.TButton")
go_btn.pack(side="left", padx=(0, 4))
undo_btn = ttk.Button(btns, text="↩ 撤销", style="UndoBtn.TButton", state="disabled")
undo_btn.pack(side="left")

# ═══ 文件列表 ═══
file_section = ttk.Frame(root, style="App.TFrame")
file_section.pack(fill="both", expand=True, padx=8, pady=(6, 0))

fl_bar = ttk.Frame(file_section, style="Surface.TFrame")
fl_bar.pack(fill="x")
file_count_var = tk.StringVar(value="文件列表 · 0 个")
ttk.Label(fl_bar, textvariable=file_count_var, style="Title.TLabel").pack(side="left", padx=(8, 0))

fl_btns = ttk.Frame(fl_bar, style="Surface.TFrame")
fl_btns.pack(side="right", padx=(0, 4), pady=2)
add_f_btn = ttk.Button(fl_btns, text="+ 文件", style="Small.TButton")
add_f_btn.pack(side="left", padx=1)
add_d_btn = ttk.Button(fl_btns, text="+ 文件夹", style="Small.TButton")
add_d_btn.pack(side="left", padx=1)

# Treeview + 滚动条
tv_frame = ttk.Frame(file_section, style="App.TFrame")
tv_frame.pack(fill="both", expand=True)
tv_frame.rowconfigure(0, weight=1)
tv_frame.columnconfigure(0, weight=1)

cols = ("thumb", "new_name", "arrow", "old_name")
file_tree = ttk.Treeview(tv_frame, columns=cols, show="headings", style="Trees.Treeview",
                          selectmode="extended")
file_tree.heading("thumb", text="");       file_tree.column("thumb",    width=30, stretch=False, anchor="center")
file_tree.heading("new_name", text="");    file_tree.column("new_name", width=360, stretch=True,  anchor="w")
file_tree.heading("arrow", text="");       file_tree.column("arrow",    width=24, stretch=False, anchor="center")
file_tree.heading("old_name", text="");    file_tree.column("old_name", width=200, stretch=True,  anchor="w")

vsb = ttk.Scrollbar(tv_frame, orient="vertical", command=file_tree.yview)
hsb = ttk.Scrollbar(tv_frame, orient="horizontal", command=file_tree.xview)
file_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

file_tree.grid(row=0, column=0, sticky="nsew")
vsb.grid(row=0, column=1, sticky="ns")
hsb.grid(row=1, column=0, sticky="ew")

# 竖屏缩略图 (24×40, 9:16 近似)
_THUMB_COLORS = ["#2a3a1a", "#1a2a3a", "#3a201a", "#2a1a3a", "#1a3a2a", "#3a301a", "#1a3a3a", "#302a1a"]
_THUMB_W, _THUMB_H = 24, 40
_thumb_images = []

def _make_thumb(clr):
    """生成竖幅纯色+播放三角 PhotoImage"""
    from tkinter import PhotoImage
    img = PhotoImage(width=_THUMB_W, height=_THUMB_H)
    # 逐行填充纯色
    hex_rgb = clr.lstrip("#")
    r, g, b = int(hex_rgb[0:2], 16), int(hex_rgb[2:4], 16), int(hex_rgb[4:6], 16)
    color_spec = f"#{r:02x}{g:02x}{b:02x}"
    for y in range(_THUMB_H):
        row_data = "{" + " ".join([color_spec] * _THUMB_W) + "}"
        img.put(row_data, to=(0, y))
    # 中心播放三角 (简单5像素)
    cx, cy = _THUMB_W // 2, _THUMB_H // 2
    tri = [(cx-3, cy-4), (cx-3, cy+4), (cx+4, cy)]
    for y in range(max(0, min(t[1] for t in tri)), min(_THUMB_H, max(t[1] for t in tri)+1)):
        for x in range(max(0, min(t[0] for t in tri)), min(_THUMB_W, max(t[0] for t in tri)+1)):
            # barycentric inside-triangle test
            def _in_tri(px, py):
                x1,y1=tri[0]; x2,y2=tri[1]; x3,y3=tri[2]
                d1 = (px-x2)*(y1-y2) - (x1-x2)*(py-y2)
                d2 = (px-x3)*(y2-y3) - (x2-x3)*(py-y3)
                d3 = (px-x1)*(y3-y1) - (x3-x1)*(py-y1)
                return (d1>=0 and d2>=0 and d3>=0) or (d1<=0 and d2<=0 and d3<=0)
            if _in_tri(x, y):
                img.put("#ffffff", to=(x, y))
    return img

for clr in _THUMB_COLORS:
    _thumb_images.append(_make_thumb(clr))

# ═══ 状态栏 ═══
statusbar = ttk.Frame(root, style="App.TFrame")
statusbar.pack(fill="x", padx=8, pady=(2, 3))

status_var = tk.StringVar(value="● 就绪  ·  Ctrl+Z 撤销  ·  Del 移除")
ttk.Label(statusbar, textvariable=status_var, style="Status.TLabel").pack(side="left", padx=(4, 0))
ttk.Label(statusbar, text="裁缝老师的达芬奇插件工坊  ·  v3.0", style="Status.TLabel",
          foreground="#555").pack(side="right", padx=(0, 4))


# ═══════════════════════════════════════════════════════════
# 逻辑
# ═══════════════════════════════════════════════════════════

def _get_inspector_vals():
    vals = {}
    for fd in FIELD_CONFIG:
        wgt, _ = _widgets[fd["key"]]
        vals[fd["key"]] = wgt.get().strip()
    return vals

def _set_inspector_vals(vals):
    """vals=None 清空所有字段"""
    for fd in FIELD_CONFIG:
        wgt, _ = _widgets[fd["key"]]
        k = fd["key"]
        if vals is None or vals.get(k) is None:
            if isinstance(wgt, ttk.Combobox): wgt.set("")
            else: wgt.delete(0, tk.END)
        else:
            v = str(vals[k])
            if isinstance(wgt, ttk.Combobox): wgt.set(v)
            else: wgt.delete(0, tk.END); wgt.insert(0, v)

def _build_filename(fields):
    parts = []
    for fd in FIELD_CONFIG:
        v = fields.get(fd["key"], fd["def"])
        nm = fd["name"]
        if nm   == "Ep":     parts.append(f"Ep{v}")
        elif nm == "Sc":     parts.append(f"Sc{v}")
        elif nm == "Gr":     parts.append(f"Gr{v}")
        elif nm == "Tk":     parts.append(f"Tk{v}")
        elif nm == "v":      parts.append(f"v{v}")
        elif fd["key"] == "status": parts.append(v)
        else:                parts.append(v.replace("/","_").replace(" ",""))
    return "_".join(parts) if parts else "unnamed"

def _refresh_tree():
    global _refreshing
    _refreshing = True

    # 记住哪些路径被选中
    selected_paths = {_entries[i].path for i in _selected_indices()}

    file_tree.delete(*file_tree.get_children())
    for i, entry in enumerate(_entries):
        nm = _build_filename(entry.fields)
        iid = file_tree.insert("", "end",
            values=("", f"{nm}{entry.ext}", "←", entry.basename),
            image=_thumb_images[i % len(_thumb_images)])
        if entry.path in selected_paths:
            file_tree.selection_add(iid)

    _update_counts()
    _update_preview()
    _refreshing = False

def _selected_indices():
    """返回选中条目对应的 _entries 索引列表（按 Treeview 顺序）"""
    all_iids = file_tree.get_children()
    sel_iids = set(file_tree.selection())
    return [all_iids.index(iid) for iid in all_iids if iid in sel_iids]

def _update_counts():
    sel = len(_selected_indices())
    total = len(_entries)
    file_count_var.set(f"文件列表 · {total} 个  ·  选中 {sel}")

def _update_preview():
    indices = _selected_indices()
    if not indices:
        if _entries:
            vals = _get_inspector_vals()
            nm = _build_filename(vals)
            preview_var.set(f"{nm}{_entries[0].ext}  (未选中，显示默认值)")
        else:
            preview_var.set("添加文件后显示预览")
        meta_var.set("")
        return

    first = _entries[indices[0]]
    nm = _build_filename(first.fields)
    preview_var.set(f"{nm}{first.ext}")

    tk_start = int(first.fields.get("tk", "1"))
    tk_end = tk_start + len(indices) - 1
    meta_var.set(f"选中 {len(indices)} 个  ·  Tk {tk_start:02d}→{tk_end:02d}")

def _on_select(event=None):
    if _refreshing:
        return

    indices = _selected_indices()
    if not indices:
        _set_inspector_vals(None)
    elif len(indices) == 1:
        _set_inspector_vals(_entries[indices[0]].fields)
    else:
        # 多选: 相同值显示, 不同值留空
        merged = {}
        for fd in FIELD_CONFIG:
            k = fd["key"]
            vals = {_entries[i].fields[k] for i in indices}
            merged[k] = next(iter(vals)) if len(vals) == 1 else ""
        _set_inspector_vals(merged)

    _update_counts()
    _update_preview()

def _apply_to_selected():
    indices = _selected_indices()
    if not indices:
        return
    vals = _get_inspector_vals()
    for i in indices:
        for fd in FIELD_CONFIG:
            k = fd["key"]
            v = vals.get(k, "")
            if v:   # 非空才覆盖 (多选留空不覆盖)
                _entries[i].fields[k] = v
    _refresh_tree()

def _on_param_change(event=None):
    root.after(50, _apply_to_selected)

# 绑定 Inspector 输入事件
for key, (wgt, fd) in _widgets.items():
    if isinstance(wgt, ttk.Entry):
        wgt.bind("<KeyRelease>", lambda e, k=key: _on_param_change())
    else:
        wgt.bind("<<ComboboxSelected>>", lambda e: _on_param_change())

# ═══ 文件操作 ═══
def add_files():
    paths = filedialog.askopenfilenames(title="选择文件")
    _add_paths(paths)

def add_folder():
    d = filedialog.askdirectory(title="选择文件夹")
    if not d: return
    paths = [os.path.join(d, f) for f in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, f))]
    _add_paths(paths)

def _add_paths(paths):
    existing = {e.path for e in _entries}
    added = 0
    for p in paths:
        if p not in existing:
            _entries.append(FileEntry(p, _saved_defaults))
            existing.add(p)
            added += 1
    if added:
        _refresh_tree()
        status_var.set(f"● 已添加 {added} 个文件")

def remove_selected():
    indices = _selected_indices()
    if not indices:
        return
    for i in sorted(indices, reverse=True):
        del _entries[i]
    _refresh_tree()
    status_var.set(f"● 已移除 {len(indices)} 个文件")

def do_rename():
    indices = _selected_indices()
    if not indices:
        messagebox.showwarning("提示", "请先在文件列表中选择要重命名的文件")
        return
    sel = [_entries[i] for i in indices]

    # 验证
    for i, entry in enumerate(sel):
        for fd in FIELD_CONFIG:
            v = entry.fields.get(fd["key"], "").strip()
            if not v:
                messagebox.showerror("参数错误",
                    f"「{fd['label']}」不能为空 (第 {indices[i]+1} 个文件)")
                return
            rx = fd.get("regex")
            if rx and not re.match(rx, v):
                messagebox.showerror("参数错误",
                    f"「{fd['label']}」格式错误: {v} (第 {indices[i]+1} 个文件)")
                return

    # 确认
    if len(sel) == 1:
        nm = _build_filename(sel[0].fields) + sel[0].ext
        msg = f"确认重命名?\n{sel[0].basename}\n→ {nm}"
    else:
        first_nm = _build_filename(sel[0].fields) + sel[0].ext
        last_nm  = _build_filename(sel[-1].fields) + sel[-1].ext
        msg = f"确认重命名 {len(sel)} 个文件?\n{first_nm}\n  ...\n{last_nm}"
    if not messagebox.askyesno("确认", msg):
        return

    # 保存 Inspector 值
    sv = _get_inspector_vals()
    try:
        with open(CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(sv, f, ensure_ascii=False, indent=2)
        global _saved_defaults
        _saved_defaults = sv
    except: pass

    # 执行
    ok, fail = 0, []
    _undo_stack.clear()
    for entry in sel:
        path = entry.path
        folder = os.path.dirname(path)
        nm = _build_filename(entry.fields) + entry.ext
        np = os.path.join(folder, nm)
        if os.path.exists(np) and np != path:
            fail.append(f"{entry.basename} → 已存在")
            continue
        try:
            os.rename(path, np)
            _undo_stack.append((path, np))
            entry.path = np
            ok += 1
        except Exception as e:
            fail.append(f"{entry.basename}: {e}")

    if ok:
        undo_btn.config(state="normal")
    _refresh_tree()
    msg = f"● 完成 {ok}/{len(sel)}"
    if fail:
        msg += "  ·  " + "  ·  ".join(fail[:2])
    status_var.set(msg)

def do_undo():
    if not _undo_stack:
        return
    if not messagebox.askyesno("撤销", f"撤销 {len(_undo_stack)} 个文件的重命名?"):
        return
    undone = 0
    for old_path, new_path in _undo_stack:
        try:
            os.rename(new_path, old_path)
            for e in _entries:
                if e.path == new_path:
                    e.path = old_path
                    break
            undone += 1
        except Exception as e:
            messagebox.showwarning("撤销失败", f"{os.path.basename(new_path)}: {e}")
    _undo_stack.clear()
    undo_btn.config(state="disabled")
    _refresh_tree()
    status_var.set(f"● 已撤销 {undone} 个")

def on_drop(event):
    files = root.tk.splitlist(event.data)
    paths = [f.strip() for f in files if f.strip() and os.path.isfile(f.strip())]
    _add_paths(paths)

# ═══ 绑定 ═══
go_btn.configure(command=do_rename)
undo_btn.configure(command=do_undo)
add_f_btn.configure(command=add_files)
add_d_btn.configure(command=add_folder)

file_tree.bind("<<TreeviewSelect>>", _on_select)
file_tree.drop_target_register(DND_FILES)
file_tree.dnd_bind("<<Drop>>", on_drop)

root.bind("<Control-z>", lambda e: do_undo())
root.bind("<Control-Z>", lambda e: do_undo())
root.bind("<Delete>",     lambda e: remove_selected())
root.bind("<BackSpace>",  lambda e: remove_selected())

# 初始
_refresh_tree()
root.mainloop()
