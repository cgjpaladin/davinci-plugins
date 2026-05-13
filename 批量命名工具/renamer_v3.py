
"""
批量文件命名工具 v3.0
- Tk 自动递增 · 重命名+归档分两步 · 目标路径 YYYYMMDD_项目名
- 重名检测 · 归档Tk自动顺号 · FIELD_RULES扩展引擎 · 纯归档模式
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import os, re, json, shutil
from datetime import datetime

FIELD_CONFIG = [
    {"key":"ep","name":"Ep","label":"Ep 集数","def":"01","regex":r"^\d{2,3}$","hint":"01"},
    {"key":"sc","name":"Sc","label":"Sc 场次","def":"01","regex":r"^\d{2,3}$","hint":"01"},
    {"key":"gr","name":"Gr","label":"Gr 小场次","def":"01","regex":r"^\d{2,3}$","hint":"01"},
    {"key":"tk","name":"Tk","label":"Tk 次数","def":"01","regex":r"^\d{2,3}$","inc":True,"hint":"01"},
    {"key":"desc","name":"","label":"镜头描述","def":"","hint":"由制作方式决定"},
    {"key":"author","name":"","label":"制作者","def":"","hint":"张谭/温欣然"},
    {"key":"method","name":"","label":"制作方式","def":"","dv":["请选择","智能分镜版","双轨版","角色专属版"]},
    {"key":"ver","name":"v","label":"v 版本号","def":"01","regex":r"^\d{2,3}(\.\d+)?$","hint":"01"},
    {"key":"status","name":"","label":"通过情况","def":"","dv":["请选择","OK","KP","NG"]},
]

METHOD_DESC_MAP = {
    "智能分镜版":{"mode":"locked","value":"全能分镜"},
    "双轨版":{"mode":"dropdown","values":["请选择","幽灵角色","空镜","手动输入…"]},
    "角色专属版":{"mode":"text","hint":"温时雨过肩中景"},
}

DESC_TO_METHOD = {"全能分镜":"智能分镜版","幽灵角色":"双轨版","空镜":"双轨版"}

FIELD_RULES = [
    {"trigger":"method","targets":["desc"],"map":{
        "智能分镜版":{"desc":{"locked":"全能分镜"}},
        "双轨版":{"desc":{"dropdown":["请选择","幽灵角色","空镜","手动输入…"]}},
        "角色专属版":{"desc":{"text_hint":"温时雨过肩中景"}},
    }},
]

T = {"bg":"#1c1c1c","surface":"#282828","border":"#3d3d3d","text":"#b8b8b8",
     "text_dim":"#707070","accent":"#e8870a","accent2":"#6a9a3a","placeholder":"#505050",
     "ff_ui":"Segoe UI","ff_mono":"Consolas"}

CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),".renamer_saved.json")
PATH_RE = re.compile(r"^(\d{8})_.+$")

def _validate_date(v):
    """Returns True if YYYYMMDD is a real calendar date"""
    m = PATH_RE.match(v)
    if not m: return False
    try:
        datetime.strptime(m.group(1), "%Y%m%d")
        return True
    except ValueError:
        return False

FILENAME_RE = re.compile(
    r"^Ep(?P<ep>\d{2,3})_Sc(?P<sc>\d{2,3})_Gr(?P<gr>\d{2,3})_Tk(?P<tk>\d{2,3})_"
    r"(?P<desc>[^_]+(?:_[^_]+)*?)_(?P<author>[^_]+)_v(?P<ver>\d{2,3}(?:\.\d+)?)_"
    r"(?P<status>\w+)(?P<ext>\.[^.]+)$")

def parse_filename(path):
    name = os.path.basename(path)
    m = FILENAME_RE.match(name)
    if not m: return None
    d = m.groupdict()
    r = {"ep":d["ep"],"sc":d["sc"],"gr":d["gr"],"tk":d["tk"],
         "desc":d["desc"],"author":d["author"],"ver":d["ver"],"status":d["status"]}
    r["method"] = DESC_TO_METHOD.get(d["desc"],"角色专属版")
    return r

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

root=TkinterDnD.Tk();root.title("批量文件命名工具");root.geometry("880x580")
root.minsize(680,400);root.configure(bg=T["bg"])
style=ttk.Style();style.theme_use("clam")

def _styles(s):
    s.configure("App.TFrame",bg=T["bg"])
    s.configure("Surface.TFrame",bg=T["surface"])
    s.configure("Title.TLabel",bg=T["surface"],fg=T["text_dim"],font=(T["ff_ui"],10))
    s.configure("Param.TLabel",bg=T["bg"],fg=T["text_dim"],font=(T["ff_ui"],8))
    s.configure("Preview.TLabel",bg=T["surface"],fg=T["accent2"],font=(T["ff_mono"],11))
    s.configure("HeroMeta.TLabel",bg=T["surface"],fg=T["text_dim"],font=(T["ff_ui"],9))
    s.configure("Status.TLabel",bg=T["bg"],fg=T["text_dim"],font=(T["ff_ui"],9))
    s.configure("Dest.TLabel",bg=T["bg"],fg=T["text_dim"],font=(T["ff_ui"],8))
    s.configure("HeroBtn.TButton",bg=T["accent"],fg="#fff",font=(T["ff_ui"],10,"bold"),borderwidth=0,padding=(14,4))
    s.map("HeroBtn.TButton",background=[("active","#ff9a2e")])
    s.configure("HeroBtnDisabled.TButton",bg="#3d3d3d",fg="#707070",font=(T["ff_ui"],10,"bold"),borderwidth=0,padding=(14,4))
    s.configure("ArchiveBtn.TButton",bg=T["surface"],fg=T["accent2"],font=(T["ff_ui"],10,"bold"),borderwidth=1,padding=(14,4))
    s.map("ArchiveBtn.TButton",background=[("active","#3a402a")],foreground=[("active",T["accent2"])])
    s.configure("ArchiveBtnDisabled.TButton",bg=T["surface"],fg="#3d3d3d",font=(T["ff_ui"],10,"bold"),borderwidth=1,padding=(14,4))
    s.configure("UndoBtn.TButton",bg=T["surface"],fg=T["text_dim"],font=(T["ff_ui"],9),padding=(8,2))
    s.configure("Small.TButton",bg=T["surface"],fg=T["text"],font=(T["ff_ui"],9),padding=(8,1))
    s.configure("Trees.Treeview",bg=T["bg"],fg=T["text"],fieldbg=T["bg"],borderwidth=0,rowheight=24,font=(T["ff_mono"],9))
    s.configure("Trees.Treeview.Heading",bg=T["surface"],fg=T["text_dim"],font=(T["ff_ui"],9),borderwidth=0,padding=(0,2))
    s.map("Trees.Treeview",background=[("selected","#3a2010")])
_styles(style)


# ═══ UI Construction ═══

# Titlebar
titlebar=ttk.Frame(root,style="Surface.TFrame");titlebar.pack(fill="x")
dots=tk.Canvas(titlebar,width=36,height=18,bg=T["surface"],highlightthickness=0)
dots.pack(side="left",padx=(8,4),pady=2)
dots.create_oval(4,6,10,12,fill=T["accent"],outline="")
dots.create_oval(14,6,20,12,fill="#555",outline="")
dots.create_oval(24,6,30,12,fill="#555",outline="")
ttk.Label(titlebar,text="批量文件命名工具",style="Title.TLabel").pack(side="left")

# Inspector
insp_frame=ttk.Frame(root,style="App.TFrame");insp_frame.pack(fill="x",padx=8,pady=(6,0))
_widgets={}

def _mk_entry(parent,fd,default_val,w=None):
    hint=fd.get("hint","");ww=w or fd.get("w",8)
    e=tk.Entry(parent,font=(T["ff_mono"],10),width=ww,fg="#e0e0e0",bg=T["surface"],
               insertbackground=T["text"],relief="flat",borderwidth=1,
               highlightbackground=T["border"],highlightthickness=1)
    if default_val and default_val!=hint:e.insert(0,str(default_val));e.config(fg="#e0e0e0")
    elif hint:e.insert(0,hint);e.config(fg=T["placeholder"])
    def fi(ev):
        if e.get()==hint and e.cget("fg")==T["placeholder"]:e.delete(0,tk.END);e.config(fg="#e0e0e0")
    def fo(ev):
        if not e.get().strip() and hint:e.delete(0,tk.END);e.insert(0,hint);e.config(fg=T["placeholder"])
    e.bind("<FocusIn>",fi);e.bind("<FocusOut>",fo)
    return e

def _mk_cb(parent,values,default_val,w=6):
    cb=ttk.Combobox(parent,values=values,state="readonly",width=w,font=(T["ff_mono"],10))
    cb.set(str(default_val) if default_val in values else values[0])
    return cb

_display_fields=[fd for fd in FIELD_CONFIG if fd["key"]!="tk"]
for fd in _display_fields:
    col=ttk.Frame(insp_frame,style="App.TFrame")
    if fd["key"]in("desc","author"):col.pack(side="left",fill="x",expand=True,padx=2)
    elif fd["key"]=="method":col.pack(side="left",padx=2)
    else:col.pack(side="left",fill="x",expand=True,padx=2)
    ttk.Label(col,text=fd["label"],style="Param.TLabel").pack(anchor="w")
    default=str(_saved_defaults.get(fd["key"],fd["def"]))
    dv=fd.get("dv")
    wgt=_mk_cb(col,dv,default,6) if dv else _mk_entry(col,fd,default)
    wgt.pack(fill="x");_widgets[fd["key"]]=(wgt,fd)

# 制作方式 → 镜头描述 (FIELD_RULES)
_desc_locked=[False]
def _reconfig_desc(cfg):
    old_wgt,fd=_widgets["desc"];parent=old_wgt.master;old_wgt.destroy()
    if cfg.get("locked"):
        e=tk.Entry(parent,font=(T["ff_mono"],10),width=16,fg="#e0e0e0",bg=T["surface"],
                   state="readonly",readonlybackground=T["surface"],relief="flat",
                   borderwidth=1,highlightbackground=T["border"],highlightthickness=1)
        e.insert(0,cfg["locked"]);e.pack(fill="x");_widgets["desc"]=(e,fd);_desc_locked[0]=True
    elif cfg.get("dropdown"):
        cb=ttk.Combobox(parent,values=cfg["dropdown"],state="readonly",width=16,font=(T["ff_mono"],10))
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
dest_frame=ttk.Frame(root,style="App.TFrame");dest_frame.pack(fill="x",padx=8,pady=(4,0))
ttk.Label(dest_frame,text="目标路径",style="Dest.TLabel").pack(side="left",padx=(4,6))
dest_var=tk.StringVar()
dest_entry=tk.Entry(dest_frame,font=(T["ff_mono"],10),width=40,fg="#e0e0e0",bg=T["surface"],
    relief="flat",borderwidth=1,highlightbackground=T["border"],highlightthickness=1)
dest_entry.pack(side="left",fill="x",expand=True)
dest_entry.insert(0,"20260404_废墟的约定");dest_entry.config(fg=T["placeholder"])
dest_ok_var=tk.StringVar()
ttk.Label(dest_frame,textvariable=dest_ok_var,style="Dest.TLabel",foreground=T["accent2"]).pack(side="left",padx=(6,0))

def _dest_focus_in(e):
    if dest_entry.cget("fg")==T["placeholder"]:dest_entry.delete(0,tk.END);dest_entry.config(fg="#e0e0e0")
def _dest_focus_out(e):
    if not dest_entry.get().strip():dest_entry.insert(0,"20260404_废墟的约定");dest_entry.config(fg=T["placeholder"])
    _check_button_states()
def _validate_dest():
    v=dest_entry.get().strip()
    if not v or dest_entry.cget("fg")==T["placeholder"]:
        dest_ok_var.set("");return None
    if PATH_RE.match(v):
        if _validate_date(v):
            dest_ok_var.set("\u2713 格式正确");return v
        else:
            dest_ok_var.set("\u2717 无效日期 (如 20250230 不存在)");return None
    else:
        dest_ok_var.set("✗ 格式: YYYYMMDD_项目名");return None

dest_entry.bind("<FocusIn>",_dest_focus_in);dest_entry.bind("<FocusOut>",_dest_focus_out)
dest_entry.bind("<KeyRelease>",lambda e:(_validate_dest(),_check_button_states()))

# Hero
hero=ttk.Frame(root,style="App.TFrame");hero.pack(fill="x",padx=8,pady=(4,0))
hi=ttk.Frame(hero,style="Surface.TFrame");hi.pack(fill="x")
pf=ttk.Frame(hi,style="Surface.TFrame");pf.pack(side="left",fill="x",expand=True,padx=(8,4),pady=6)
ttk.Label(pf,text="▸",fg=T["accent2"],bg=T["surface"],font=(T["ff_ui"],13,"bold")).pack(side="left",padx=(0,6))
preview_var=tk.StringVar(value="添加文件后显示预览")
ttk.Label(pf,textvariable=preview_var,style="Preview.TLabel").pack(side="left",fill="x",expand=True)
meta_var=tk.StringVar(value="")
ttk.Label(pf,textvariable=meta_var,style="HeroMeta.TLabel").pack(side="right",padx=(8,0))
btns=ttk.Frame(hi,style="Surface.TFrame");btns.pack(side="right",padx=(0,8),pady=6)
go_btn=ttk.Button(btns,text="批量重命名",style="HeroBtnDisabled.TButton");go_btn.pack(side="left",padx=(0,4))
archive_btn=ttk.Button(btns,text="批量归档",style="ArchiveBtnDisabled.TButton");archive_btn.pack(side="left",padx=(0,4))
undo_btn=ttk.Button(btns,text="↩ 撤销",style="UndoBtn.TButton",state="disabled");undo_btn.pack(side="left")

# File list
fs=ttk.Frame(root,style="App.TFrame");fs.pack(fill="both",expand=True,padx=8,pady=(4,0))
flb=ttk.Frame(fs,style="Surface.TFrame");flb.pack(fill="x")
file_count_var=tk.StringVar(value="文件列表 · 0 个")
ttk.Label(flb,textvariable=file_count_var,style="Title.TLabel").pack(side="left",padx=(8,0))
flbtn=ttk.Frame(flb,style="Surface.TFrame");flbtn.pack(side="right",padx=(0,4),pady=2)
add_f_btn=ttk.Button(flbtn,text="+ 文件",style="Small.TButton");add_f_btn.pack(side="left",padx=1)
add_d_btn=ttk.Button(flbtn,text="+ 文件夹",style="Small.TButton");add_d_btn.pack(side="left",padx=1)

tvf=ttk.Frame(fs,style="App.TFrame");tvf.pack(fill="both",expand=True)
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
sb=ttk.Frame(root,style="App.TFrame");sb.pack(fill="x",padx=8,pady=(2,3))
status_var=tk.StringVar(value="\u25cf 就绪  \u00b7  Ctrl+Z 撤销  \u00b7  Del 移除")
ttk.Label(sb,textvariable=status_var,style="Status.TLabel").pack(side="left",padx=(4,0))
ttk.Label(sb,text="裁缝老师的达芬奇插件工坊  \u00b7  v3.0",style="Status.TLabel",foreground="#555").pack(side="right",padx=(0,4))


# =========== Logic ===========

def _build_filename(fields):
    parts=[]
    for fd in FIELD_CONFIG:
        v=fields.get(fd["key"],fd["def"]);nm=fd["name"]
        if nm=="Ep":parts.append(f"Ep{v}")
        elif nm=="Sc":parts.append(f"Sc{v}")
        elif nm=="Gr":parts.append(f"Gr{v}")
        elif nm=="Tk":parts.append(f"Tk{v}")
        elif nm=="v":parts.append(f"v{v}")
        elif fd["key"]=="status":parts.append(v)
        else:parts.append(v.replace("/","_").replace(" ",""))
    return"_".join(parts)if parts else"unnamed"

def _get_inspector_vals():
    v={}
    for fd in _display_fields: wgt,_=_widgets[fd["key"]];v[fd["key"]]=wgt.get().strip()
    return v

def _get_real_val(wgt,fd):
    v=wgt.get().strip()
    if isinstance(wgt,tk.Entry):
        hint=fd.get("hint","")
        if v==hint and wgt.cget("fg")==T["placeholder"]:return""
    if fd.get("dv")and v in("请选择",""):return""
    return v

def _set_inspector_vals(vals):
    for fd in _display_fields:
        wgt,_=_widgets[fd["key"]];k=fd["key"]
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
        nm=_build_filename(en.fields)
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
            vs=_get_inspector_vals();nm=_build_filename(vs)
            preview_var.set(nm+_entries[0].ext+"  (未选中)")
        else:preview_var.set("添加文件后显示预览")
        meta_var.set("");return
    _apply_tk_to_selected()
    f=_entries[ix[0]];nm=_build_filename(f.fields);preview_var.set(nm+f.ext)
    ts=int(f.fields.get("tk","1"))
    meta_var.set("选中 {} 个  ·  Tk {:02d}→{:02d}".format(len(ix),ts,ts+len(ix)-1))

def _on_select(ev=None):
    if _refreshing:return
    ix=_selected_indices()
    _apply_tk_to_selected()
    if not ix:_set_inspector_vals(None)
    elif len(ix)==1:_set_inspector_vals(_entries[ix[0]].fields)
    else:
        mg={}
        for fd in _display_fields:
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
        nm=_build_filename(_entries[i].fields)+_entries[i].ext
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
        for fd in _display_fields:
            k=fd["key"]
            if k=="method":continue
            wgt,_=_widgets[k];v=_get_real_val(wgt,fd)
            if v:_entries[i].fields[k]=v
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
        for fd in _display_fields:
            if fd["key"]=="method":continue
            wgt,_=_widgets[fd["key"]];v=_get_real_val(wgt,fd)
            if not v:can_rename=False;break
    dest=_validate_dest()
    can_archive=bool(dest)
    if can_rename:go_btn.configure(style="HeroBtn.TButton")
    else:go_btn.configure(style="HeroBtnDisabled.TButton")
    if can_archive:archive_btn.configure(style="ArchiveBtn.TButton")
    else:archive_btn.configure(style="ArchiveBtnDisabled.TButton")

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
        _apply_tk_to_selected();_refresh_tree()
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
        nm=_build_filename(en.fields)+en.ext
        if nm in names:
            messagebox.showwarning("重名检测",
                "\u201c{}\u201d \u91cd\u590d ({} \u548c {})\uff0c\u8bf7\u8c03\u6574\u5b57\u6bb5\u3002".format(nm,names[nm],en.basename));return
        names[nm]=en.basename
    if len(sel)==1:
        fn=_build_filename(sel[0].fields)+sel[0].ext
        msg="确认重命名?\n{}\n→ {}".format(sel[0].basename,fn)
    else:
        fn=_build_filename(sel[0].fields)+sel[0].ext
        ln=_build_filename(sel[-1].fields)+sel[-1].ext
        msg="确认重命名 {} 个?\n{}\n  ...\n{}".format(len(sel),fn,ln)
    if not messagebox.askyesno("确认",msg):return
    sv=_get_inspector_vals()
    try:
        with open(CFG_FILE,"w",encoding="utf-8")as f:json.dump(sv,f,ensure_ascii=False,indent=2)
        global _saved_defaults;_saved_defaults=sv
    except:pass
    ok=0;fail=[];_undo_stack.clear()
    for en in sel:
        p=en.path;d=os.path.dirname(p);nm=_build_filename(en.fields)+en.ext;np=os.path.join(d,nm)
        if os.path.exists(np)and np!=p:fail.append(en.basename+"→已存在");continue
        try:os.rename(p,np);_undo_stack.append((p,np));en.path=np;ok+=1
        except Exception as e:fail.append(en.basename+":"+str(e))
    if ok:undo_btn.config(state="normal")
    _refresh_tree();msg="● 完成 {}/{}".format(ok,len(sel))
    if fail:msg+="  ·  "+"  ·  ".join(fail[:2])
    status_var.set(msg)

def _build_folder(path_root,entry):
    f=entry.fields
    compound = "EP{ep}_SC{sc}_GR{gr}_{method}_v{ver}".format(**f)
    return os.path.join(path_root,
        "EP"+f["ep"],"SC"+f["sc"],compound,
        _build_filename(f)+entry.ext)

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
    progress=ttk.Progressbar(root,mode="determinate",maximum=total,length=300)
    progress.place(relx=0.5,rely=0.93,anchor="center")
    status_var.set("\u25cf 归档中... 0/"+str(total));root.update()
    for idx,en in enumerate(sel):
        target=_build_folder(dest,en)
        tk_val=int(en.fields["tk"])
        while os.path.exists(target):
            tk_val+=1;en.fields["tk"]="%02d"%tk_val;target=_build_folder(dest,en)
        os.makedirs(os.path.dirname(target),exist_ok=True)
        try:shutil.copy2(en.path,target);ok+=1
        except Exception as e:fail.append(en.basename+":"+str(e))
        progress["value"]=idx+1
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

# =========== Bindings ===========
go_btn.configure(command=do_rename)
archive_btn.configure(command=do_archive)
undo_btn.configure(command=do_undo)
add_f_btn.configure(command=add_files)
add_d_btn.configure(command=add_folder)
file_tree.bind("<<TreeviewSelect>>",_on_select)
file_tree.drop_target_register(DND_FILES);file_tree.dnd_bind("<<Drop>>",on_drop)
root.bind("<Control-z>",lambda e:do_undo())
root.bind("<Control-Z>",lambda e:do_undo())
root.bind("<Delete>",lambda e:remove_selected())
root.bind("<BackSpace>",lambda e:remove_selected())

_validate_dest();_check_button_states();_refresh_tree();root.mainloop()
