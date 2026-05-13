"""
批量命名工具 · WebView 生产版
Python 后端 + HTML/CSS 前端
"""
import os, sys, json, re, shutil
from datetime import datetime
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.naming import (
    FIELD_CONFIG, DISPLAY_FIELDS, METHOD_DESC_MAP, FIELD_RULES,
    build_filename, parse_filename, build_folder,
    check_zero_byte, check_double_ext, check_size_anomaly,
    MEDIA_EXT, sanitize_text,
)

import webview
import logging
_log = logging.getLogger("renamer_web")
_log.setLevel(logging.DEBUG)
_hdlr = logging.FileHandler("/tmp/renamer_web.log")
_hdlr.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
_log.addHandler(_hdlr)

# pyinstaller 打包后 sys._MEIPASS = app bundle 资源目录
_BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
_SHARED_DIR = os.path.join(_BASE_DIR, 'shared')
if os.path.isdir(_SHARED_DIR) and _SHARED_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(_SHARED_DIR))

CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".renamer_saved.json")
PATH_RE = re.compile(r"^(\d{8})_(.+)$")

_saved_defaults = {}
if os.path.exists(CFG_FILE):
    try:
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            _saved_defaults = json.load(f)
    except:
        pass

_undo_stack = []  # list of lists: [[(old,new),...], [(old,new),...]]
_window = None  # 存引用


class RenamerAPI:

    def on_drop_files(self, paths_json):
        """JS 通知 Python 处理拖放路径（从 Python 端 DOM 事件拿到完整路径）"""
        try:
            paths = json.loads(paths_json)
        except:
            return {"files": [], "total": 0}
        _log.info(f"on_drop_files: {paths[:5]}")
        result = self._process_paths(paths)
        # 通知 JS 更新 UI
        if _window:
            _window.evaluate_js(f"onDropResult({json.dumps(result)})")
        return result

    def pick_dest_folder(self):
        """打开文件夹选择框，返回路径"""
        result = _window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            return {"path": result[0]}
        return {"path": ""}

    def normalize_path(self, path):
        """转换粘贴的路径：smb:// → /Volumes/，去掉尾部文件名"""
        import re as _re
        v = str(path).strip()
        # SMB URL → 本地挂载路径
        v = _re.sub(r'^smb://[\d.]+/', '/Volumes/', v)
        # 尾部有扩展名 → 可能是文件路径，取父目录
        if '.' in os.path.basename(v) and not os.path.isdir(v):
            parent = os.path.dirname(v)
            if parent and os.path.isdir(parent):
                v = parent
        return {"normalized": v, "exists": os.path.isdir(v)}

    def generate_thumbnails(self, paths):
        """用 ffmpeg 提取视频第一帧，返回 base64 data URI"""
        import subprocess, base64, tempfile, shutil as _shutil
        ffmpeg = _shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
        _log.info(f"generate_thumbnails: {len(paths)} files, ffmpeg={ffmpeg}")
        thumbs = {}
        for p in paths:
            try:
                tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                tmp.close()
                result = subprocess.run(
                    [ffmpeg, '-y', '-i', p, '-vframes', '1', '-s', '48x72', '-q:v', '5', tmp.name],
                    capture_output=True, timeout=5
                )
                if result.returncode != 0:
                    _log.info(f"  ffmpeg fail: {result.stderr[:200]}")
                if os.path.isfile(tmp.name) and os.path.getsize(tmp.name) > 100:
                    with open(tmp.name, 'rb') as f:
                        b64 = base64.b64encode(f.read()).decode()
                    thumbs[p] = f"data:image/jpg;base64,{b64}"
                os.unlink(tmp.name)
            except Exception as e:
                _log.info(f"  thumb error: {e}")
                try: os.unlink(tmp.name)
                except: pass
        _log.info(f"generate_thumbnails done: {len(thumbs)} thumbs")
        return {"thumbs": thumbs}

    def get_config(self):
        fmt = []
        for fd in FIELD_CONFIG:
            nm = fd["name"]; k = fd["key"]
            if nm == "Ep": fmt.append({"pfx":"Ep","key":"ep"})
            elif nm == "Sc": fmt.append({"pfx":"Sc","key":"sc"})
            elif nm == "Gr": fmt.append({"pfx":"Gr","key":"gr"})
            elif nm == "Tk": fmt.append({"pfx":"Tk","key":"tk"})
            elif nm == "v": fmt.append({"pfx":"v","key":"ver"})
            elif k == "status": fmt.append({"pfx":"","key":"status"})
            else: fmt.append({"pfx":"","key":k})
        return {
            "fields": DISPLAY_FIELDS,
            "defaults": _saved_defaults,
            "method_desc_map": METHOD_DESC_MAP,
            "field_rules": FIELD_RULES,
            "name_format": fmt,
        }

    def add_files_via_dialog(self):
        result = _window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True,
            file_types=("媒体文件 (*.mp4;*.mov;*.mxf;*.avi;*.mkv;*.r3d;*.braw)",),
        )
        if not result:
            return {"files": [], "total": 0}
        paths = result if isinstance(result, list) else [result]
        return self._process_paths(paths)

    def add_folder_via_dialog(self):
        result = _window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result or len(result) == 0:
            return {"files": [], "total": 0}
        folder = result[0]
        paths = []
        try:
            for f in sorted(os.listdir(folder)):
                fp = os.path.join(folder, f)
                if os.path.isfile(fp):
                    paths.append(fp)
        except:
            pass
        return self._process_paths(paths)

    def add_files_by_paths(self, paths):
        _log.info(f"add_files_by_paths paths={[str(p)[:80] for p in (paths or [])[:5]]}")
        return self._process_paths(paths)

    def debug_log(self, msg):
        _log.info(f"[JS] {msg}")
        return "ok"

    def echo(self, x):
        _log.info(f"ECHO: {x!r}")
        return {"received": x}

    def _process_paths(self, paths_):
        _log.info(f"_process_paths received {len(paths_)} paths")
        MAX_FILES = 500
        files = []; duplicates = 0; subdirs = 0; truncated = False
        defaults = _saved_defaults
        # 用户必须手动填，不给默认值
        _EMPTY_KEYS = {'ep','sc','gr','ver'}

        for p_ in paths_[:MAX_FILES + 500]:
            if len(files) >= MAX_FILES: truncated = True; break
            p = str(p_).strip()
            if p.startswith("file://"): p = unquote(p[7:])
            p = os.path.expanduser(p)

            if os.path.isfile(p):
                if p in {f["path"] for f in files}: duplicates += 1; continue
                parsed = parse_filename(p)
                fields = {}
                for fd in FIELD_CONFIG:
                    k = fd["key"]
                    if parsed and k in parsed: fields[k] = parsed[k]
                    elif defaults and k in defaults and k not in _EMPTY_KEYS: fields[k] = defaults.get(k, fd["def"])
                    elif k in _EMPTY_KEYS: fields[k] = ""
                    else: fields[k] = fd["def"]
                files.append({"path":p,"basename":os.path.basename(p),"ext":os.path.splitext(os.path.basename(p))[1],"fields":fields})
            elif os.path.isdir(p):
                try:
                    for f in sorted(os.listdir(p)):
                        fp = os.path.join(p, f)
                        if os.path.isfile(fp):
                            if fp in {x["path"] for x in files}: duplicates += 1; continue
                            if len(files) >= MAX_FILES: truncated = True; break
                            parsed = parse_filename(fp)
                            fields = {}
                            for fd in FIELD_CONFIG:
                                k = fd["key"]
                                if parsed and k in parsed: fields[k] = parsed[k]
                                elif defaults and k in defaults and k not in _EMPTY_KEYS: fields[k] = defaults.get(k, fd["def"])
                                elif k in _EMPTY_KEYS: fields[k] = ""
                                else: fields[k] = fd["def"]
                            files.append({"path":fp,"basename":os.path.basename(fp),"ext":os.path.splitext(os.path.basename(fp))[1],"fields":fields})
                        elif os.path.isdir(fp): subdirs += 1
                except: pass

        _log.info(f"_process_paths: {len(files)} files, {duplicates} dup, {subdirs} subdirs skip, truncated={truncated}")
        # 自动检查
        anomalies = set()
        try:
            from statistics import mean, stdev
            sp = [(f,p) for f in files for p in [f["path"]] if os.path.getsize(p) > 0]
            vals = [s for _,s in sp]
            if len(vals) >= 3:
                mu = mean(vals); sd = stdev(vals)
                if sd > 0 and mu > 0 and sd/mu > 1.0:
                    anomalies = {fp for fp,_ in sp if abs(os.path.getsize(fp)-mu) > 2*sd}
        except: pass
        for f in files:
            tags = []
            if check_zero_byte(f["path"]): tags.append("zero")
            if check_double_ext(f["basename"]): tags.append("dbl_ext")
            if f["path"] in anomalies: tags.append("size")
            f["tags"] = tags
        return {"files":files,"total":len(files),"duplicates":duplicates,"subdirs_skipped":subdirs,"truncated":truncated,"max":MAX_FILES}

    def do_rename(self, files):
        global _undo_stack
        ok = 0; fail = []; batch = []; renamed = []
        for f in files:
            p = f["path"]
            d = os.path.dirname(p)
            ext = os.path.splitext(os.path.basename(p))[1]
            nm = build_filename(f["fields"]) + ext
            np = os.path.join(d, nm)
            if os.path.exists(np) and np != p:
                fail.append(os.path.basename(p) + " → 已存在")
                continue
            try:
                os.rename(p, np)
                batch.append((p, np))
                renamed.append({"old_path": p, "new_path": np})
                ok += 1
            except Exception as e:
                fail.append(os.path.basename(p) + ": " + str(e))
        if files:
            sv = {k: v for k, v in files[0]["fields"].items() if k != "tk"}
            try:
                with open(CFG_FILE, "w", encoding="utf-8") as fp:
                    json.dump(sv, fp, ensure_ascii=False, indent=2)
                global _saved_defaults
                _saved_defaults = sv
            except:
                pass
        if batch:
            _undo_stack.append(batch)
        _log.info(f"do_rename: {ok} ok, batch={len(batch)}, stack_depth={len(_undo_stack)}")
        return {"ok": ok, "fail": fail, "total": len(files), "renamed": renamed, "stack_depth": len(_undo_stack)}

    def do_undo(self):
        global _undo_stack
        if not _undo_stack:
            return {"ok": 0, "msg": "没有可撤销的操作"}
        batch = _undo_stack.pop()
        ud = 0
        for op, np in batch:
            try:
                os.rename(np, op)
                ud += 1
            except:
                pass
        _log.info(f"do_undo: {ud}/{len(batch)} reversed, remaining batches: {len(_undo_stack)}")
        return {"ok": ud, "msg": f"已撤销 {ud} 个", "remaining": len(_undo_stack)}

    def validate_dest(self, dest):
        v = str(dest).strip()
        if not v: return {"ok": False, "msg": ""}
        # smb:// → /Volumes/ 静默转换
        v = re.sub(r'^smb://[\d.]+/', '/Volumes/', v)
        m = PATH_RE.match(os.path.basename(v))
        if not m: return {"ok": False, "msg": "✗ 格式: YYYYMMDD_项目名"}
        try: datetime.strptime(m.group(1), "%Y%m%d")
        except ValueError: return {"ok": False, "msg": "✗ 无效日期"}
        name = m.group(2)
        cleaned, warns = sanitize_text(name, for_filename=True)
        if not cleaned: return {"ok": False, "msg": "✗ 项目名不能为空"}
        if warns: return {"ok": False, "msg": "✗ " + "; ".join(warns)}
        if len(cleaned) > 50: return {"ok": False, "msg": "✗ 项目名过长 (≤50字)"}
        return {"ok": True, "msg": "✓ 格式正确"}

    def do_archive(self, files, dest):
        _log.info(f"do_archive: {len(files)} files, dest={dest}")
        ok = 0; fail = []; dest = re.sub(r'^smb://[\d.]+/', '/Volumes/', str(dest).strip())
        for f in files:
            fd = f.get("fields", {})
            ext = f.get("ext", ".mp4")
            target = build_folder(dest, type('E',(),{'fields':fd,'ext':ext})())
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try: shutil.copy2(f["path"], target); ok += 1
            except Exception as e: fail.append(os.path.basename(f["path"]) + ": " + str(e))
        return {"ok": ok, "fail": fail, "total": len(files)}


HTML_FILE = os.path.join(_BASE_DIR, "renamer_web.html")

if __name__ == "__main__":
    import threading, socket
    from bottle import route, run, static_file

    # 用 bottle HTTP 服务绕过 WKWebView 沙箱限制
    @route('/')
    def index():
        return static_file('renamer_web.html', root=_BASE_DIR)

    # 找空闲端口
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()

    # 后台启动 bottle
    t = threading.Thread(target=lambda: run(host='127.0.0.1', port=port, quiet=True), daemon=True)
    t.start()

    # 等 bottle 就绪
    import time, urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=0.5)
            break
        except:
            time.sleep(0.1)

    api = RenamerAPI()
    _window = webview.create_window(
        title="批量文件命名工具",
        url=f"http://127.0.0.1:{port}",
        js_api=api,
        width=880, height=620,
        min_size=(680, 400),
        resizable=True,
        background_color='#151515',
        text_select=True,
    )

    # 拖放：用 loaded 事件在 DOM 就绪后绑定 Python 端 handler
    def _bind_drop():
        from webview.dom import DOMEventHandler
        def _on_drop(e):
            files = e['dataTransfer']['files']
            paths = []
            for f in files:
                fp = f.get('pywebviewFullPath', '')
                if not fp: continue
                if os.path.isfile(fp):
                    paths.append(fp)
                elif os.path.isdir(fp):
                    # 展开文件夹内容
                    try:
                        for sf in sorted(os.listdir(fp)):
                            sfp = os.path.join(fp, sf)
                            if os.path.isfile(sfp):
                                paths.append(sfp)
                    except: pass
            if paths:
                _log.info(f"DOM drop: {len(paths)} items")
                result = api._process_paths(paths)
                _window.evaluate_js(f"onDropResult({json.dumps(result)})")
        _window.dom.document.events.dragover += DOMEventHandler(lambda e: e, True, True)
        _window.dom.document.events.drop += DOMEventHandler(_on_drop, True, True)
        _log.info("DOM drop handler bound")

    _window.events.loaded += _bind_drop

    webview.start(debug=False)
