"""
批量文件命名工具 v3.0
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import customtkinter as ctk
import os, re, json, shutil, sys, statistics
from datetime import datetime

# 共享命名模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.naming import (
    FIELD_CONFIG, DISPLAY_FIELDS, METHOD_DESC_MAP, DESC_TO_METHOD, FIELD_RULES,
    build_filename, parse_filename, build_folder,
    check_zero_byte, check_double_ext, check_name_format,
    check_field_completeness, check_size_anomaly, MEDIA_EXT, sanitize_text,
)

T = {"bg":"#151515","surface":"#1e1e1e","surface2":"#282828",
     "border":"#3d3d3d","border_hi":"#555555","text":"#c0c0c0","text_bright":"#e8e8e8",
     "text_dim":"#707070","accent":"#e8870a","accent_dim":"#8a5000",
     "green":"#6a9a3a","red":"#c04040","placeholder":"#505050",
     "ff_ui":"Segoe UI","ff_mono":"Consolas"}

CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),".renamer_saved.json")
PATH_RE = re.compile(r"^(\d{8})_(.+)$")

def _validate_project_name(path):
    """返回 (ok: bool, error_msg: str). 日期 + 项目名 完整校验."""
    m = PATH_RE.match(path)
    if not m: return False,"格式: YYYYMMDD_项目名"
    if not _validate_date(path): return False,"无效日期"
    name = m.group(2)
    cleaned, warns = sanitize_text(name, for_filename=True)
    if not cleaned: return False,"项目名不能为空"
    if warns: return False,"; ".join(warns)
    if len(cleaned) > 50: return False,"项目名过长 (≤50字)"
    return True,""

def _validate_date(v):
    m = PATH_RE.match(v)
    if not m: return False
    try:
        datetime.strptime(m.group(1), "%Y%m%d")
        return True
    except ValueError:
        return False

class FileEntry:
    __slots__=("path","fields")
    def __init__(s,p,defaults=None,parsed=None):
        s.path=p;s.fields={}
        for fd in FIELD_CONFIG:
            k=fd["key"]
            if parsed and k in parsed: s.fields[k]=parsed[k]
            elif defaults and k in defaults: s.fields[k]=defaults.get(k,fd["def"])
            else: s.fields[k]=fd["def"]
    @property
    def basename(s):return os.path.basename(s.path)
    @property
    def ext(s):_,e=os.path.splitext(s.basename);return e

_entries=[];_undo_stack=[];_saved_defaults={};_refreshing=False

if os.path.exists(CFG_FILE):
    try:
        with open(CFG_FILE,"r",encoding="utf-8")as f:_saved_defaults=json.load(f)
    except:pass

ctk.set_appearance_mode("dark");ctk.set_default_color_theme("blue")
root=ctk.CTk();root.title("批量文件命名工具");root.geometry("880x580")
root.minsize(680,400);root.configure(fg_color=T["bg"])
# Enable drag-and-drop for CustomTkinter root
try: root.tk.call('package','require','tkdnd')
except: pass

# ═══ UI Construction ═══

# Titlebar
titlebar=ctk.CTkFrame(root,fg_color=T["surface"]);titlebar.pack(fill="x")
dots=tk.Canvas(titlebar,width=36,height=18,bg=T["surface"],highlightthickness=0)
dots.pack(side="left",padx=(8,4),pady=2)
dots.create_oval(4,6,10,12,fill=T["accent"],outline="")
dots.create_oval(14,6,20,12,fill="#555",outline="")
dots.create_oval(24,6,30,12,fill="#555",outline="")
ctk.CTkLabel(titlebar,text="批量文件命名工具",text_color=T["text_dim"], fg_color=T["surface"]).pack(side="left")

# Inspector
insp_frame=ctk.CTkFrame(root,fg_color=T["bg"]);insp_frame.pack(fill="x",padx=8,pady=(6,0))
_widgets={}

def _mk_entry(parent,fd,default_val,w=None):
    hint=fd.get("hint","");ww=(w or fd.get("w",8))*8
    e=ctk.CTkEntry(parent,font=(T["ff_mono"],10),width=ww,height=26,
                   fg_color=T["surface2"],border_color=T["border"],text_color="#e8e8e8")
    if default_val and default_val!=hint:e.insert(0,str(default_val))
    elif hint:e.insert(0,hint);e.configure(text_color=T["placeholder"])
    def fi(ev):
        if e.get()==hint and e.cget("text_color")==T["placeholder"]:e.delete(0,tk.END);e.configure(text_color="#e8e8e8")
    def fo(ev):
        if not e.get().strip() and hint:e.delete(0,tk.END);e.insert(0,hint);e.configure(text_color=T["placeholder"])
    e.bind("<FocusIn>",fi);e.bind("<FocusOut>",fo)
    return e

def _mk_cb(parent,values,default_val,w=6):
    cb=ctk.CTkComboBox(parent,values=values,state="readonly",width=w,font=(T["ff_mono"],10))
    cb.set(str(default_val) if default_val in values else values[0])
    return cb

for fd in DISPLAY_FIELDS:
    col=ctk.CTkFrame(insp_frame,fg_color=T["bg"])
    if fd["key"]in("desc","author"):col.pack(side="left",fill="x",expand=True,padx=2)
    elif fd["key"]=="method":col.pack(side="left",padx=2,fill="x",expand=True)
    else:col.pack(side="left",fill="x",expand=True,padx=2)
    ctk.CTkLabel(col,text=fd["label"],text_color=T["text_dim"], fg_color=T["bg"]).pack(anchor="w")
    default=str(_saved_defaults.get(fd["key"],fd["def"]))
    dv=fd.get("dv")
    wgt=_mk_cb(col,dv,default,6) if dv else _mk_entry(col,fd,default)
    wgt.pack(fill="x");_widgets[fd["key"]]=(wgt,fd)
    # Tk 插在 Gr 之后
    if fd["key"]=="gr":
        tk_col=ctk.CTkFrame(insp_frame,fg_color=T["bg"]);tk_col.pack(side="left",padx=2)
        ctk.CTkLabel(tk_col,text="Tk 次数",text_color=T["text_dim"], fg_color=T["bg"]).pack(anchor="w")
        tk_display=ctk.CTkEntry(tk_col,font=(T["ff_mono"],10),width=36,height=26,
            fg_color=T["surface"],border_color=T["border"],text_color=T["placeholder"])
        tk_display.insert(0,"自动")
        tk_display.configure(state="disabled")
        tk_display.pack()
        _widgets["tk_display"]=(tk_display,{"key":"tk","hint":"","dv":None})

# 制作方式 → 镜头描述 (FIELD_RULES)
_desc_locked=[False]
def _reconfig_desc(cfg):
    old_wgt,fd=_widgets["desc"];parent=old_wgt.master;old_wgt.destroy()
    if cfg.get("locked"):
        e=tk.Entry(parent,font=(T["ff_mono"],10),width=16,fg="#e0e0e0",bg=T["surface"],
                   relief="flat",borderwidth=1,
                   highlightbackground=T["border"],highlightthickness=1)
        e.insert(0,cfg["locked"])
        e.configure(state="readonly",readonlybackground=T["surface"])
        e.pack(fill="x");_widgets["desc"]=(e,fd);_desc_locked[0]=True
    elif cfg.get("dropdown"):
        cb=ctk.CTkComboBox(parent,values=cfg["dropdown"],state="readonly",width=16,font=(T["ff_mono"],10))
        cb.set(cfg["dropdown"][0])
        def _toggle(ev=None):
            if cb.get()=="手动输入…":cb.configure(state="normal");cb.set("");cb.focus_set()
            else:cb.configure(state="readonly");_on_param_change()
        cb.bind("<<ComboboxSelected>>",_toggle,add="+")
        cb.bind("<FocusOut>",lambda e:_on_param_change(),add="+")
        cb.pack(fill="x");_widgets["desc"]=(cb,fd);_desc_locked[0]=False
    else:
        hint=cfg.get("text_hint","请输入");e=_mk_entry(parent,fd,"",16)
        e.delete(0,tk.END);e.insert(0,hint);e.config(fg=T["placeholder"])
        e.bind("<KeyRelease>",lambda e:root.after(50,_on_param_change))
        e.bind("<FocusOut>",lambda e:_on_param_change(),add="+")
        e.pack(fill="x");_widgets["desc"]=(e,fd);_desc_locked[0]=False

def _on_method_change(ev=None):
    mv=_widgets["method"][0].get()
    if mv in("请选择",""):_reconfig_desc({"text_hint":"请先选择制作方式"});return
    for rule in FIELD_RULES:
        if rule["trigger"]!="method":continue
        cfg=rule["map"].get(mv,{})
        for tgt in rule["targets"]:
            if tgt=="desc":_reconfig_desc(cfg.get("desc",{}))
    idx=_selected_indices()
    if idx:
        for i in idx:
            _entries[i].fields["method"]=mv
            cm=METHOD_DESC_MAP.get(mv,{})
            if cm.get("mode")=="locked":_entries[i].fields["desc"]=cm["value"]
            elif cm.get("mode")=="dropdown":_entries[i].fields["desc"]=cm["values"][0] if cm["values"] else ""
            else:_entries[i].fields["desc"]=""
        _refresh_tree()
    _check_button_states()

_widgets["method"][0].bind("<<ComboboxSelected>>",_on_method_change)
init_m=_saved_defaults.get("method","请选择")
if init_m and init_m!="请选择":
    _widgets["method"][0].set(init_m);_on_method_change()

# 目标路径
dest_frame=ctk.CTkFrame(root,fg_color=T["bg"]);dest_frame.pack(fill="x",padx=8,pady=(4,0))
ctk.CTkLabel(dest_frame,text="目标路径",text_color=T["text_dim"], fg_color=T["bg"]).pack(side="left",padx=(4,6))
dest_entry=ctk.CTkEntry(dest_frame,font=(T["ff_mono"],10),width=300,height=26,
    fg_color=T["surface"],border_color=T["border"],text_color=T["placeholder"])
dest_entry.pack(side="left",fill="x",expand=True)
dest_entry.insert(0,"20260404_废墟的约定")
dest_ok_var=tk.StringVar()
ctk.CTkLabel(dest_frame,textvariable=dest_ok_var,text_color=T["green"], fg_color=T["bg"]).pack(side="left",padx=(6,0))

def _dest_focus_in(e):
    if dest_entry.cget("text_color")==T["placeholder"]:dest_entry.delete(0,tk.END);dest_entry.configure(text_color="#e8e8e8")
def _dest_focus_out(e):
    if not dest_entry.get().strip():dest_entry.insert(0,"20260404_废墟的约定");dest_entry.configure(text_color=T["placeholder"])
    _check_button_states()
def _validate_dest():
    v=dest_entry.get().strip()
    if not v or dest_entry.cget("text_color")==T["placeholder"]:
        dest_ok_var.set("");return None
    ok,err=_validate_project_name(v)
    if ok: dest_ok_var.set("\u2713 格式正确");return v
    else: dest_ok_var.set("\u2717 "+err);return None

dest_entry.bind("<FocusIn>",_dest_focus_in);dest_entry.bind("<FocusOut>",_dest_focus_out)
dest_entry.bind("<KeyRelease>",lambda e:(_validate_dest(),_check_button_states()))

# Hero
hero=ctk.CTkFrame(root,fg_color=T["bg"]);hero.pack(fill="x",padx=8,pady=(4,0))
hi=ctk.CTkFrame(hero,fg_color=T["surface"]);hi.pack(fill="x")
pf=ctk.CTkFrame(hi,fg_color=T["surface"]);pf.pack(side="left",fill="x",expand=True,padx=(8,4),pady=6)
ctk.CTkLabel(pf,text="▸",text_color=T["green"],fg_color=T["surface"],font=(T["ff_ui"],13,"bold")).pack(side="left",padx=(0,6))
preview_var=tk.StringVar(value="添加文件后显示预览")
ctk.CTkLabel(pf,textvariable=preview_var,text_color=T["green"], fg_color=T["surface"]).pack(side="left",fill="x",expand=True)
meta_var=tk.StringVar(value="")
ctk.CTkLabel(pf,textvariable=meta_var,text_color=T["text_dim"], fg_color=T["surface"]).pack(side="right",padx=(8,0))
btns=ctk.CTkFrame(hi,fg_color=T["surface"]);btns.pack(side="right",padx=(0,8),pady=6)
go_btn=ctk.CTkButton(btns,text="批量重命名",fg_color="#3d3d3d", text_color="#707070", hover_color="#3d3d3d", state="disabled");go_btn.pack(side="left",padx=(0,4))
archive_btn=ctk.CTkButton(btns,text="批量归档",fg_color="transparent", text_color="#3d3d3d", border_color="#3d3d3d", border_width=1, state="disabled", hover_color=T["surface"]);archive_btn.pack(side="left",padx=(0,4))
check_btn=ctk.CTkButton(btns,text="检查",fg_color="transparent", text_color=T["text_dim"], hover_color=T["border_hi"]);check_btn.pack(side="left",padx=(0,4))
undo_btn=ctk.CTkButton(btns,text="↩ 撤销",fg_color="transparent", text_color=T["text_dim"], hover_color=T["border_hi"]);undo_btn.pack(side="left")

# File list
fs=ctk.CTkFrame(root,fg_color=T["bg"]);fs.pack(fill="both",expand=True,padx=8,pady=(4,0))
flb=ctk.CTkFrame(fs,fg_color=T["surface"]);flb.pack(fill="x")
file_count_var=tk.StringVar(value="文件列表 · 0 个")
ctk.CTkLabel(flb,textvariable=file_count_var,text_color=T["text_dim"], fg_color=T["surface"]).pack(side="left",padx=(8,0))
flbtn=ctk.CTkFrame(flb,fg_color=T["surface"]);flbtn.pack(side="right",padx=(0,4),pady=2)
add_f_btn=ctk.CTkButton(flbtn,text="+ 文件",fg_color="transparent", text_color=T["text"], hover_color=T["bg"]);add_f_btn.pack(side="left",padx=1)
add_d_btn=ctk.CTkButton(flbtn,text="+ 文件夹",fg_color="transparent", text_color=T["text"], hover_color=T["bg"]);add_d_btn.pack(side="left",padx=1)

tvf=ctk.CTkFrame(fs,fg_color=T["bg"]);tvf.pack(fill="both",expand=True)
tvf.rowconfigure(0,weight=1);tvf.columnconfigure(0,weight=1)
cols=("thumb","new_name","arrow","old_name")
file_tree=ttk.Treeview(tvf,columns=cols,show="headings",style="Trees.Treeview",selectmode="extended")
file_tree.heading("thumb",text="");file_tree.column("thumb",width=30,stretch=False,anchor="center")
file_tree.heading("new_name",text="");file_tree.column("new_name",width=380,stretch=True,anchor="w")
file_tree.heading("arrow",text="");file_tree.column("arrow",width=24,stretch=False,anchor="center")
file_tree.heading("old_name",text="");file_tree.column("old_name",width=200,stretch=True,anchor="w")
vsb=ttk.Scrollbar(tvf,orient="vertical",command=file_tree.yview);hsb=ttk.Scrollbar(tvf,orient="horizontal",command=file_tree.xview)
file_tree.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
file_tree.grid(row=0,column=0,sticky="nsew");vsb.grid(row=0,column=1,sticky="ns");hsb.grid(row=1,column=0,sticky="ew")

# Check tags
file_tree.tag_configure("zerobyte",background="#4a1515",foreground="#f06060")
file_tree.tag_configure("size_warn",background="#3a3010",foreground="#e0c040")
file_tree.tag_configure("fmt_warn",background="#2a1a30",foreground="#c080d0")

# Thumbnails
_TW,_TH=24,40;_TC=["#2a3a1a","#1a2a3a","#3a201a","#2a1a3a","#1a3a2a","#3a301a","#1a3a3a","#302a1a"];_TI=[]
def _mkthumb(clr):
    im=tk.PhotoImage(width=_TW,height=_TH)
    h=clr.lstrip("#");r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16);cs=f"#"+h
    for y in range(_TH):im.put("{"+" ".join([cs]*_TW)+"}",to=(0,y))
    cx,cy=_TW//2,_TH//2;tri=[(cx-3,cy-4),(cx-3,cy+4),(cx+4,cy)]
    for y in range(max(0,min(t[1]for t in tri)),min(_TH,max(t[1]for t in tri)+1)):
        for x in range(max(0,min(t[0]for t in tri)),min(_TW,max(t[0]for t in tri)+1)):
            x1,y1=tri[0];x2,y2=tri[1];x3,y3=tri[2]
            d1=(x-x2)*(y1-y2)-(x1-x2)*(y-y2);d2=(x-x3)*(y2-y3)-(x2-x3)*(y-y3);d3=(x-x1)*(y3-y1)-(x3-x1)*(y-y1)
            if(d1>=0 and d2>=0 and d3>=0)or(d1<=0 and d2<=0 and d3<=0):im.put("#ffffff",to=(x,y))
    return im
for clr in _TC:_TI.append(_mkthumb(clr))

# Status bar
sb=ctk.CTkFrame(root,fg_color=T["bg"]);sb.pack(fill="x",padx=8,pady=(2,3))
status_var=tk.StringVar(value="\u25cf 就绪  \u00b7  Ctrl+Z 撤销  \u00b7  Del 移除")
ctk.CTkLabel(sb,textvariable=status_var,text_color=T["text_dim"], fg_color=T["bg"]).pack(side="left",padx=(4,0))
ctk.CTkLabel(sb,text="裁缝老师的达芬奇插件工坊  \u00b7  v3.0",text_color="#555", fg_color=T["bg"]).pack(side="right",padx=(0,4))


# =========== Logic ===========

def _get_inspector_vals():
    v={}
    for fd in DISPLAY_FIELDS: wgt,_=_widgets[fd["key"]];v[fd["key"]]=wgt.get().strip()
    return v

def _get_real_val(wgt,fd):
    v=wgt.get().strip()
    if isinstance(wgt,ctk.CTkEntry):
        hint=fd.get("hint","")
        if v==hint and wgt.cget("text_color")==T["placeholder"]:return""
    elif isinstance(wgt,tk.Entry):
        hint=fd.get("hint","")
        if v==hint and wgt.cget("fg")==T["placeholder"]:return""
    if fd.get("dv")and v in("请选择",""):return""
    return v

def _set_inspector_vals(vals):
    for fd in DISPLAY_FIELDS:
        wgt,_=_widgets[fd["key"]];k=fd["key"]
        if k=="desc" and _desc_locked[0]:continue  # 锁定时不覆盖
        if vals is None or vals.get(k)is None:
            if isinstance(wgt,ttk.Combobox):wgt.set((fd.get("dv")or[""])[0])
            else:
                wgt.delete(0,tk.END);hint=fd.get("hint","")
                if hint:wgt.insert(0,hint);wgt.config(fg=T["placeholder"])
        else:
            vv=str(vals[k])
            if isinstance(wgt,ttk.Combobox):
                vl=wgt.cget("values")or();wgt.set(vv if vv in vl else vl[0])
            else:
                wgt.delete(0,tk.END)
                if vv:wgt.insert(0,vv);wgt.config(fg="#e0e0e0")
                else:
                    hint=fd.get("hint","")
                    if hint:wgt.insert(0,hint);wgt.config(fg=T["placeholder"])

def _refresh_tree():
    global _refreshing;_refreshing=True
    sp={_entries[i].path for i in _selected_indices()}
    file_tree.delete(*file_tree.get_children())
    for i,en in enumerate(_entries):
        nm=build_filename(en.fields)
        iid=file_tree.insert("","end",values=("",f"{nm}{en.ext}","←",en.basename),image=_TI[i%len(_TI)])
        if en.path in sp:file_tree.selection_add(iid)
    _upd_counts();_upd_preview();_check_button_states();_refreshing=False

def _selected_indices():
    ai=file_tree.get_children();si=set(file_tree.selection())
    return[ai.index(ii)for ii in ai if ii in si]

def _upd_counts():
    s=len(_selected_indices());t=len(_entries)
    file_count_var.set("文件列表 · {} 个  ·  选中 {}".format(t,s))

def _upd_preview():
    ix=_selected_indices()
    if not ix:
        if _entries:
            vs=_get_inspector_vals();nm=build_filename(vs)
            preview_var.set(nm+_entries[0].ext+"  (未选中)")
        else:preview_var.set("添加文件后显示预览")
        meta_var.set("");return
    _apply_tk_to_selected()
    f=_entries[ix[0]];nm=build_filename(f.fields);preview_var.set(nm+f.ext)
    ts=int(f.fields.get("tk","1"))
    meta_var.set("选中 {} 个  ·  Tk {:02d}→{:02d}".format(len(ix),ts,ts+len(ix)-1))
    # 更新 Tk 显示
    try:
        tk_display.configure(state="normal");tk_display.delete(0,tk.END)
        tk_display.insert(0,"自动" if not ix else "%02d"%ts)
        tk_display.configure(state="disabled")
    except:pass

def _on_select(ev=None):
    if _refreshing:return
    ix=_selected_indices()
    _apply_tk_to_selected()
    if not ix:_set_inspector_vals(None)
    elif len(ix)==1:_set_inspector_vals(_entries[ix[0]].fields)
    else:
        mg={}
        for fd in DISPLAY_FIELDS:
            k=fd["key"];vs={_entries[i].fields[k]for i in ix};mg[k]=next(iter(vs))if len(vs)==1 else""
        _set_inspector_vals(mg)
    _upd_counts();_upd_preview()

def _apply_tk_to_selected():
    ix=_selected_indices()
    if not ix:return
    start=1  # Tk starts at 01, purely for anti-collision
    for j,i in enumerate(ix):
        _entries[i].fields["tk"]="%02d"%(start+j)

def _check_name_collision():
    ix=_selected_indices()
    if not ix:return None
    names={}
    for i in ix:
        nm=build_filename(_entries[i].fields)+_entries[i].ext
        if nm in names:return(nm,_entries[i].basename,names[nm])
        names[nm]=_entries[i].basename
    return None

def _apply_to_selected():
    ix=_selected_indices()
    if not ix:return
    col=_check_name_collision()
    if col:
        messagebox.showwarning("重名检测",
            "“{}” 重复。已存在于 {} 和 {}。请调整字段使名称唯一。".format(col[0],col[1],col[2]))
        return
    for i in ix:
        for fd in DISPLAY_FIELDS:
            k=fd["key"]
            if k=="method":continue
            wgt,_=_widgets[k];v=_get_real_val(wgt,fd)
            if v:
                # 清洗文件系统禁字 (desc/author 等手动输入字段)
                if k in ("desc","author","ver","ep","sc","gr"):
                    v,_=sanitize_text(v)
                _entries[i].fields[k]=v
    dwgt,_=_widgets["desc"];dcfg=METHOD_DESC_MAP.get(_widgets["method"][0].get(),{})
    for i in ix:
        if dcfg.get("mode")=="locked":_entries[i].fields["desc"]=dcfg["value"]
        elif dcfg.get("mode")=="dropdown":
            dv=dwgt.get()
            if dv and dv!="请选择":_entries[i].fields["desc"]=dv
        elif dcfg.get("mode")=="text":
            dv=dwgt.get().strip();hint=dcfg.get("hint","")
            if dv!=hint:_entries[i].fields["desc"]=dv
    _refresh_tree()

def _on_param_change(ev=None):root.after(50,_apply_to_selected)

def _check_button_states():
    ix=_selected_indices()
    can_rename=bool(ix)
    if can_rename:
        for fd in DISPLAY_FIELDS:
            wgt,_=_widgets[fd["key"]];v=_get_real_val(wgt,fd)
            if not v:can_rename=False;break
    dest=_validate_dest()
    can_archive=bool(dest) and bool(ix)
    if can_rename:go_btn.configure(fg_color=T["accent"], text_color="#fff", hover_color="#ff9a2e")
    else:go_btn.configure(fg_color="#3d3d3d", text_color="#707070", hover_color="#3d3d3d", state="disabled")
    if can_archive:archive_btn.configure(fg_color="transparent", text_color=T["green"], border_color=T["green"], border_width=1, hover_color="#3a402a")
    else:archive_btn.configure(fg_color="transparent", text_color="#3d3d3d", border_color="#3d3d3d", border_width=1, state="disabled", hover_color=T["surface"])

for key,(wgt,fd)in _widgets.items():
    if key=="method":continue
    if isinstance(wgt,tk.Entry):
        wgt.bind("<KeyRelease>",lambda e:(_on_param_change(),_check_button_states()))
        wgt.bind("<FocusOut>",lambda e:(_on_param_change(),_check_button_states()),add="+")
    elif isinstance(wgt,ttk.Combobox):
        wgt.bind("<<ComboboxSelected>>",lambda e:(_on_param_change(),_check_button_states()))

# =========== File operations ===========

def _add_paths(paths):
    ex={e.path for e in _entries};added=0
    for p in paths:
        if p in ex:continue
        parsed=parse_filename(p)
        if parsed:_entries.append(FileEntry(p,parsed=parsed))
        else:_entries.append(FileEntry(p,_saved_defaults))
        ex.add(p);added+=1
    if added:
        _apply_tk_to_selected();_refresh_tree();_annotate_checks()
        status_var.set("● 已添加 {} 个文件".format(added))

def add_files():_add_paths(filedialog.askopenfilenames(title="选择文件"))
def add_folder():
    d=filedialog.askdirectory(title="选择文件夹")
    if d:
        paths=[os.path.join(d,f)for f in sorted(os.listdir(d))if os.path.isfile(os.path.join(d,f))]
        _add_paths(paths)

def remove_selected():
    ix=_selected_indices()
    if not ix:return
    for i in sorted(ix,reverse=True):del _entries[i]
    _refresh_tree();status_var.set("● 已移除 {} 个".format(len(ix)))

def do_rename():
    ix=_selected_indices()
    if not ix:messagebox.showwarning("提示","请先选择文件");return
    _apply_tk_to_selected()
    sel=[_entries[i]for i in ix]
    for j,en in enumerate(sel):
        for fd in FIELD_CONFIG:
            v=en.fields.get(fd["key"],"").strip()
            if not v:
                messagebox.showerror("参数错误",
                    "「{}」不能为空 (第{}个)".format(fd['label'],ix[j]+1));return
            rx=fd.get("regex")
            if rx and not re.match(rx,v):
                messagebox.showerror("参数错误",
                    "「{}」格式错误 (第{}个)".format(fd['label'],ix[j]+1));return
    names={}
    for en in sel:
        nm=build_filename(en.fields)+en.ext
        if nm in names:
            messagebox.showwarning("重名检测",
                "\u201c{}\u201d \u91cd\u590d ({} \u548c {})\uff0c\u8bf7\u8c03\u6574\u5b57\u6bb5\u3002".format(nm,names[nm],en.basename));return
        names[nm]=en.basename
    if len(sel)==1:
        fn=build_filename(sel[0].fields)+sel[0].ext
        msg="确认重命名?\n{}\n→ {}".format(sel[0].basename,fn)
    else:
        fn=build_filename(sel[0].fields)+sel[0].ext
        ln=build_filename(sel[-1].fields)+sel[-1].ext
        msg="确认重命名 {} 个?\n{}\n  ...\n{}".format(len(sel),fn,ln)
    if not messagebox.askyesno("确认",msg):return
    sv=_get_inspector_vals()
    try:
        with open(CFG_FILE,"w",encoding="utf-8")as f:json.dump(sv,f,ensure_ascii=False,indent=2)
        global _saved_defaults;_saved_defaults=sv
    except:pass
    ok=0;fail=[];_undo_stack.clear()
    for en in sel:
        p=en.path;d=os.path.dirname(p);nm=build_filename(en.fields)+en.ext;np=os.path.join(d,nm)
        if os.path.exists(np)and np!=p:fail.append(en.basename+"→已存在");continue
        try:os.rename(p,np);_undo_stack.append((p,np));en.path=np;ok+=1
        except Exception as e:fail.append(en.basename+":"+str(e))
    if ok:undo_btn.config(state="normal")
    _refresh_tree();msg="● 完成 {}/{}".format(ok,len(sel))
    if fail:msg+="  ·  "+"  ·  ".join(fail[:2])
    status_var.set(msg)

def do_archive():
    dest=_validate_dest()
    if not dest:
        messagebox.showwarning("提示",
            "请先输入有效目标路径\n格式: YYYYMMDD_项目名")
        return
    ix=_selected_indices()
    if not ix:messagebox.showwarning("提示","请先选择文件");return
    _apply_tk_to_selected()
    sel=[_entries[i]for i in ix]
    for j,en in enumerate(sel):
        for fd in FIELD_CONFIG:
            v=en.fields.get(fd["key"],"").strip()
            if not v:
                messagebox.showerror("参数错误",
                    "「{}」不能为空 (第{}个)".format(fd['label'],ix[j]+1));return
    msg="确认归档 {} 个文件到?\n  {}/EP{}/SC{}/EP{}_SC{}_GR{}_{}_v{}/(复制模式)".format(
        len(sel),dest,sel[0].fields["ep"],sel[0].fields["sc"],
        sel[0].fields["ep"],sel[0].fields["sc"],sel[0].fields["gr"],
        sel[0].fields["method"],sel[0].fields["ver"])
    if not messagebox.askyesno("确认",msg):return
    ok=0;fail=[]
    total=len(sel)
    progress=ctk.CTkProgressBar(root,mode="determinate",width=300)
    progress.place(relx=0.5,rely=0.93,anchor="center")
    status_var.set("\u25cf 归档中... 0/"+str(total));root.update()
    for idx,en in enumerate(sel):
        target=build_folder(dest,en)
        tk_val=int(en.fields["tk"])
        while os.path.exists(target):
            tk_val+=1;en.fields["tk"]="%02d"%tk_val;target=build_folder(dest,en)
        os.makedirs(os.path.dirname(target),exist_ok=True)
        try:shutil.copy2(en.path,target);ok+=1
        except Exception as e:fail.append(en.basename+":"+str(e))
        progress.set((idx+1)/total)
        status_var.set("\u25cf 归档中... {}/{}".format(idx+1,total));root.update()
    progress.destroy()
    _refresh_tree();msg="\u25cf 归档 {}/{}".format(ok,total)
    if fail:msg+="  ·  "+"  ·  ".join(fail[:2])
    status_var.set(msg)

def do_undo():
    if not _undo_stack:return
    if not messagebox.askyesno("撤销","撤销 {} 个?".format(len(_undo_stack))):return
    ud=0
    for op,np in _undo_stack:
        try:
            os.rename(np,op)
            for e in _entries:
                if e.path==np:e.path=op;break
            ud+=1
        except Exception as e:messagebox.showwarning("撤销失败",os.path.basename(np)+":"+str(e))
    _undo_stack.clear();undo_btn.config(state="disabled")
    _refresh_tree();status_var.set("● 已撤销 {} 个".format(ud))

def on_drop(ev):
    fs=root.tk.splitlist(ev.data)
    paths=[]
    for f in fs:
        f=f.strip()
        if f and os.path.isfile(f):paths.append(f)
        elif f and os.path.isdir(f):
            for sf in os.listdir(f):
                sfp=os.path.join(f,sf)
                if os.path.isfile(sfp):paths.append(sfp)
    if paths:_add_paths(paths)

# =========== Check ===========

def _annotate_checks():
    """给文件列表标注检查结果 (运行时标注)"""
    # 清除旧标签
    for iid in file_tree.get_children():
        file_tree.item(iid,tags=())
    zero_count=0;size_count=0;fmt_count=0;dbl_count=0
    filepaths=[e.path for e in _entries]
    anomalies=set(fp for fp,_ in check_size_anomaly(filepaths))
    for i,en in enumerate(_entries):
        iid=file_tree.get_children()[i]
        tags=[]
        if check_zero_byte(en.path):tags.append("zerobyte");zero_count+=1
        elif en.path in anomalies:tags.append("size_warn");size_count+=1
        if _entries and not parse_filename(en.path):
            tags.append("fmt_warn");fmt_count+=1
        if check_double_ext(en.basename):dbl_count+=1
        if tags:file_tree.item(iid,tags=tuple(tags))
    return zero_count,size_count,fmt_count,dbl_count

def do_check():
    """运行全套检查并弹窗"""
    zero,size_w,fmt,dbl=_annotate_checks()
    issues=0
    msgs=[]
    if zero:msgs.append(f"零字节: {zero} 个");issues+=zero
    if size_w:msgs.append(f"大小异常: {size_w} 个");issues+=size_w
    if fmt:msgs.append(f"命名格式不符: {fmt} 个");issues+=fmt
    if dbl:msgs.append(f"扩展名重复: {dbl} 个");issues+=dbl
    if issues:
        messagebox.showwarning("检查结果","\n".join(msgs))
    else:
        messagebox.showinfo("检查结果","全部通过")
    status_var.set("● 检查完成: {} 项问题".format(issues) if issues else "● 检查通过")
    _refresh_tree()

# =========== Bindings ===========
go_btn.configure(command=do_rename)
archive_btn.configure(command=do_archive)
check_btn.configure(command=do_check)
undo_btn.configure(command=do_undo)
add_f_btn.configure(command=add_files)
add_d_btn.configure(command=add_folder)
file_tree.bind("<<TreeviewSelect>>",_on_select)
try:
    file_tree.drop_target_register(DND_FILES);file_tree.dnd_bind("<<Drop>>",on_drop)
except:pass
root.bind("<Control-z>",lambda e:do_undo())
root.bind("<Control-Z>",lambda e:do_undo())
root.bind("<Delete>",lambda e:remove_selected())
root.bind("<BackSpace>",lambda e:remove_selected())

_validate_dest();_check_button_states();_refresh_tree();root.mainloop()
