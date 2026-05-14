"""
批量命名工具 · WebView 生产版
Python 后端 + HTML/CSS 前端
"""
import os, sys, json, re, shutil, statistics
from datetime import datetime
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.naming import (
    FIELD_CONFIG, DISPLAY_FIELDS, METHOD_DESC_MAP, FIELD_RULES,
    build_filename, parse_filename, build_folder,
    MEDIA_EXT, sanitize_text,
)
from shared.naming_checks import check_zero_byte, check_double_ext, check_size_anomaly

# 日志
import logging
_log = logging.getLogger("renamer")
_log.setLevel(logging.INFO)
_h = logging.FileHandler("/tmp/renamer_web.log")
_h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
_log.addHandler(_h)

# 配置持久化
CFG_FILE = os.path.expanduser("~/.renamer_defaults.json")
_saved_defaults = {}
try:
    with open(CFG_FILE, encoding="utf-8") as fp:
        _saved_defaults = json.load(fp)
except:
    pass

_undo_stack = []
MAX_FILES = 500
_BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
_SHARED_DIR = os.path.join(_BASE_DIR, 'shared')
HTML_FILE = os.path.join(_BASE_DIR, "renamer_web.html")

# pywebview 延迟导入（PyInstaller 需要）
_window = None


class RenamerAPI:
    def __getattr__(self, name):
        """未定义 API → 返回错误而不沉默"""
        return lambda *a,**k: {"error": f"API not found: {name}"}

    def echo(self, msg):
        _log.info(f"ECHO: {msg!r}")
        return {"received": msg}

    def debug_log(self, msg):
        _log.info(f"[JS] {msg}")
        return "ok"

    def generate_thumbnails(self, paths):
        """生成视频缩略图 (base64)"""
        import subprocess, tempfile, base64
        thumbs = {}
        ffmpeg = "/opt/homebrew/bin/ffmpeg"
        if not os.path.exists(ffmpeg):
            ffmpeg = "ffmpeg"
        for p in paths[:200]:
            try:
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                tmp.close()
                subprocess.run(
                    [ffmpeg, "-y", "-ss", "00:00:01", "-i", p, "-vframes", "1", "-s", "160x90", tmp.name],
                    capture_output=True, timeout=5,
                )
                with open(tmp.name, "rb") as fp:
                    data = base64.b64encode(fp.read()).decode()
                    thumbs[p] = f"data:image/jpeg;base64,{data}"
                try: os.unlink(tmp.name)
                except: pass
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
        is_dev = not getattr(sys, '_MEIPASS', False)
        return {
            "dev": is_dev,
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
        if result:
            return self._process_paths(result)
        return {"files": [], "total": 0}

    def add_folder_via_dialog(self):
        result = _window.create_file_dialog(
            webview.FOLDER_DIALOG,
        )
        if result:
            return self._process_paths(result)
        return {"files": [], "total": 0}

    def _process_paths(self, paths_):
        truncated = False
        duplicates = 0
        subdirs = 0
        files = []
        defaults = _saved_defaults
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
            sp = [(f,p) for f in files for p in [f["path"]] if os.path.getsize(p) > 0]
            vals = [s for _,s in sp]
            if len(vals) >= 3:
                mu = statistics.mean(vals); sd = statistics.stdev(vals)
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
        return {"ok": ud, "msg": f"撤销 {ud} 个", "remaining": len(_undo_stack)}

    def validate_dest(self, dest):
        v = str(dest).strip()
        if not v: return {"ok": False, "msg": ""}
        v = re.sub(r'^smb://[\d.]+/', '/Volumes/', v)
        m = PATH_RE.match(os.path.basename(v))
        if m:
            return {"ok": True, "msg": "✓ 格式正确"}
        return {"ok": False, "msg": "目标路径格式不正确"}

    def pick_dest_folder(self):
        result = _window.create_file_dialog(webview.FOLDER_DIALOG)
        if result:
            return {"path": result[0]}
        return {"path": ""}

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


PATH_RE = re.compile(r"^EP\d{2,3}_.*")

if __name__ == "__main__":
    import threading, socket, webview
    from bottle import route, run, static_file

    @route('/')
    def index():
        return static_file('renamer_web.html', root=_BASE_DIR)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()

    threading.Thread(target=lambda: run(host='127.0.0.1', port=port, quiet=True), daemon=True).start()

    api = RenamerAPI()
    _window = webview.create_window(
        '批量命名工具', f'http://127.0.0.1:{port}',
        js_api=api, width=900, height=700,
    )

    # 注册 DOM 事件处理器（pywebview 6.x DOM API）
    def _bind_drop():
        from webview.dom import DOMEventHandler
        def _on_drop(e):
            _log.info(f"DROP EVENT: type={type(e).__name__}")
            files = e['dataTransfer']['files']
            paths = []
            for f in files:
                fp = f.get('pywebviewFullPath', '')
                if not fp: continue
                if os.path.isfile(fp):
                    paths.append(fp)
            if paths:
                _log.info(f"DOM drop: {len(paths)} items")
                result = api._process_paths(paths)
                _window.evaluate_js(f"onDropResult({json.dumps(result)})")
        _window.dom.document.events.dragover += DOMEventHandler(lambda e: e, True, True)
        _window.dom.document.events.drop += DOMEventHandler(_on_drop, True, True)
        _log.info("DOM drop handler bound")

    _window.events.loaded += _bind_drop

    import time, urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=0.5)
            break
        except:
            time.sleep(0.3)

    webview.start()
