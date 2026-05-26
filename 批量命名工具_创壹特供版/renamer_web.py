"""
批量命名工具 · 创壹特供版 v1.0
Python 后端 + HTML/CSS 前端（表格版）
"""
import os, sys, json, statistics, io as _sys_io
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.naming_createone import (
    FIELD_CONFIG,
    build_filename, parse_filename,
    MEDIA_EXT, VIDEO_EXT, IMAGE_EXT, ext_to_type,
)
from shared.naming_checks import check_zero_byte, check_double_ext

import webview
import logging, tempfile
_log = logging.getLogger("renamer_createone")
_log.setLevel(logging.DEBUG)
try:
    _hdlr = logging.FileHandler(os.path.join(tempfile.gettempdir(), "renamer_createone.log"))
    _hdlr.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    _log.addHandler(_hdlr)
except Exception:
    pass

_BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
_SHARED_DIR = os.path.join(_BASE_DIR, 'shared')
if os.path.isdir(_SHARED_DIR) and _SHARED_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(_SHARED_DIR))

CFG_FILE = os.path.join(os.path.expanduser("~"), ".renamer_createone_saved.json")

_saved_defaults = {}
if os.path.exists(CFG_FILE):
    try:
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            _saved_defaults = json.load(f)
    except Exception:
        pass

THUMB_MAX = 100
_undo_stack = []
_window = None


class RenamerAPI:
    def generate_thumbnails(self, paths):
        import subprocess, base64, tempfile, shutil, sys as _sys, json as _json
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            for pfx in (_sys._MEIPASS if getattr(_sys,'_MEIPASS',False) else '', '/opt/homebrew/bin', '/usr/local/bin'):
                exe_name = 'ffmpeg.exe' if _sys.platform == 'win32' else 'ffmpeg'
                test = os.path.join(pfx, exe_name) if pfx else 'ffmpeg'
                if os.path.exists(test): ffmpeg = test; break
        if not ffmpeg: ffmpeg = 'ffmpeg'
        _log.info(f"generate_thumbnails: {len(paths)} files")
        total = 0
        for p in paths[:THUMB_MAX]:
            try:
                ext = os.path.splitext(p)[1].lower()
                if ext in IMAGE_EXT:
                    from PIL import Image
                    img = Image.open(p)
                    # EXIF 自变换
                    try:
                        from PIL import ImageOps
                        img = ImageOps.exif_transpose(img)
                    except Exception:
                        pass
                    img.thumbnail((120, 120), Image.LANCZOS)
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    buf = _sys_io.BytesIO()
                    img.save(buf, format='JPEG', quality=80)
                    b64 = base64.b64encode(buf.getvalue()).decode()
                    thumb = f"data:image/jpeg;base64,{b64}"
                    if _window:
                        _window.evaluate_js(f"setThumb({_json.dumps(p)},{_json.dumps(thumb)})")
                    total += 1
                else:
                    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                    tmp.close()
                    kw = dict(capture_output=True, timeout=8)
                    if _sys.platform == 'win32':
                        kw['creationflags'] = subprocess.CREATE_NO_WINDOW
                    for ss in ('00:00:01', '00:00:00.1'):
                        subprocess.run(
                            [ffmpeg, '-y', '-ss', ss, '-i', p, '-vframes', '1',
                             '-vf', 'scale=120:120:force_original_aspect_ratio=decrease',
                             '-q:v', '8', tmp.name],
                            **kw
                        )
                        if os.path.isfile(tmp.name) and os.path.getsize(tmp.name) > 100:
                            break
                    if os.path.isfile(tmp.name) and os.path.getsize(tmp.name) > 100:
                        with open(tmp.name, 'rb') as f:
                            b64 = base64.b64encode(f.read()).decode()
                        thumb = f"data:image/jpeg;base64,{b64}"
                        if _window:
                            _window.evaluate_js(f"setThumb({_json.dumps(p)},{_json.dumps(thumb)})")
                        total += 1
                    try: os.unlink(tmp.name)
                    except OSError: pass
            except Exception as e:
                _log.info(f"  thumb error: {e}")
        _log.info(f"generate_thumbnails done: {total} thumbs")
        return {"thumbs": {}, "total": total}

    def get_config(self):
        fmt = []
        for fd in FIELD_CONFIG:
            nm = fd["name"]; k = fd["key"]
            if nm == "EP":      fmt.append({"pfx":"EP","key":"ep"})
            elif nm == "SC":    fmt.append({"pfx":"SC","key":"sc"})
            elif nm == "SH":    fmt.append({"pfx":"SH","key":"shot"})
            elif nm == "TK":    fmt.append({"pfx":"TK","key":"tk"})
            elif nm == "V":     fmt.append({"pfx":"V","key":"ver"})
            elif k == "status": fmt.append({"pfx":"","key":"status"})
            else:               fmt.append({"pfx":"","key":k})
        is_dev = not getattr(sys, '_MEIPASS', False)
        return {
            "fields": FIELD_CONFIG,
            "dev": is_dev,
            "defaults": _saved_defaults,
            "name_format": fmt,
        }

    def add_files_via_dialog(self):
        result = _window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True,
            file_types=("媒体文件 (*.mp4;*.mov;*.mxf;*.avi;*.mkv;*.png;*.jpg;*.jpeg;*.tiff;*.tif;*.bmp)",),
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
                    paths.append(os.path.realpath(fp))
        except Exception:
            pass
        return self._process_paths(paths)

    def add_files_by_paths(self, paths):
        _log.info(f"add_files_by_paths paths={[str(p)[:80] for p in (paths or [])[:5]]}")
        return self._process_paths(paths)

    _dbg_buf = []

    def debug_log(self, msg):
        if msg:
            self._dbg_buf.append(msg)
            if len(self._dbg_buf) > 500:
                self._dbg_buf = self._dbg_buf[-500:]
            _log.info(f"[JS] {msg}")
            return "ok"
        return {"log": list(self._dbg_buf)}

    def echo(self, x):
        _log.info(f"ECHO: {x!r}")
        return {"received": x}

    def _process_paths(self, paths_):
        _log.info(f"_process_paths: {len(paths_)} paths -> scanning")
        MAX_FILES = 100
        files = []; duplicates = 0; subdirs = 0; truncated = False
        seen_fp = set()
        _EMPTY_KEYS = {'ep','sc','shot','tk','ver'}
        parsed_count = 0; no_parse_count = 0
        for p_ in paths_[:MAX_FILES]:
            if len(files) >= MAX_FILES: truncated = True; break
            p = str(p_).strip()
            if p.startswith("file://"): p = unquote(p[7:])

            if os.path.isfile(p):
                ext = os.path.splitext(p)[1].lower()
                if ext not in MEDIA_EXT:
                    _log.debug(f"  skip non-media: {os.path.basename(p)}")
                    continue
                if p in {f["path"] for f in files}: duplicates += 1; continue
                try:
                    import hashlib
                    st = os.stat(p)
                    fp_key = f"{st.st_size}:{hashlib.md5(open(p,'rb').read(65536)).hexdigest()}"
                except OSError:
                    fp_key = p
                if fp_key in seen_fp: duplicates += 1; continue
                seen_fp.add(fp_key)
                parsed = parse_filename(p)
                fields = {}
                for fd in FIELD_CONFIG:
                    k = fd["key"]
                    if parsed and k in parsed: fields[k] = parsed[k]
                    elif k in _EMPTY_KEYS: fields[k] = ""
                    else: fields[k] = fd["def"]
                fields["type"] = ext_to_type(ext)
                if parsed: parsed_count += 1
                else: no_parse_count += 1
                _log.debug(f"  + {os.path.basename(p)} parsed={bool(parsed)} ep={fields.get('ep')} sc={fields.get('sc')} shot={fields.get('shot')} type={fields.get('type')}")
                files.append({"path":p,"basename":os.path.basename(p),"ext":ext,"fields":fields,"fp":fp_key})
            elif os.path.isdir(p):
                try:
                    for f in sorted(os.listdir(p)):
                        fp = os.path.join(p, f)
                        if os.path.isfile(fp):
                            ext2 = os.path.splitext(fp)[1].lower()
                            if ext2 not in MEDIA_EXT: continue
                            if fp in {x["path"] for x in files}: duplicates += 1; continue
                            try:
                                st = os.stat(fp)
                                fp_key2 = f"{st.st_size}:{hashlib.md5(open(fp,'rb').read(65536)).hexdigest()}"
                            except OSError:
                                fp_key2 = fp
                            if fp_key2 in {x.get("fp","") for x in files}: duplicates += 1; continue
                            if len(files) >= MAX_FILES: truncated = True; break
                            parsed = parse_filename(fp)
                            fields = {}
                            for fd in FIELD_CONFIG:
                                k = fd["key"]
                                if parsed and k in parsed: fields[k] = parsed[k]
                                elif k in _EMPTY_KEYS: fields[k] = ""
                                else: fields[k] = fd["def"]
                            fields["type"] = ext_to_type(ext2)
                            if parsed: parsed_count += 1
                            else: no_parse_count += 1
                            files.append({"path":fp,"basename":os.path.basename(fp),"ext":ext2,"fields":fields,"fp":fp_key2})
                        elif os.path.isdir(fp): subdirs += 1
                except Exception: pass

        _log.info(f"_process_paths: {len(files)} files, {parsed_count} parsed, {no_parse_count} raw, {duplicates} dup")
        anomalies = set()
        try:
            sp = [(fp, os.path.getsize(fp)) for f in files for fp in [f["path"]] if os.path.getsize(fp) > 0]
            vals = [s for _,s in sp]
            if len(vals) >= 3:
                mu = statistics.mean(vals); sd = statistics.stdev(vals)
                cv = sd/mu if mu > 0 else 0
                _log.info(f"auto-check: {len(vals)} files, cv={cv:.2f}")
                if cv > 1.0:
                    anomalies = {fp for fp,_ in sp if abs(os.path.getsize(fp)-mu) > 2*sd}
        except Exception as e:
            _log.info(f"  auto-check error: {e}")
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
        _log.info(f"do_rename: {len(files)} files")
        for f in files:
            p = f["path"]
            d = os.path.dirname(p)
            ext = f.get("ext", os.path.splitext(os.path.basename(p))[1])
            fd = f.get("fields", {})
            nm = build_filename(fd) + ext
            np = os.path.join(d, nm)
            if os.path.exists(np) and os.path.normcase(np) != os.path.normcase(p):
                fail.append(os.path.basename(p) + " -> 已存在")
                _log.warning(f"  rename collision: {os.path.basename(p)} -> {os.path.basename(np)}")
                continue
            try:
                os.rename(p, np)
                batch.append((p, np))
                renamed.append({"old_path": p, "new_path": np})
                _log.debug(f"  ok {os.path.basename(p)} -> {os.path.basename(np)}")
                ok += 1
            except Exception as e:
                fail.append(os.path.basename(p) + ": " + str(e))
        if files:
            sv = {k: v for k, v in files[0].get("fields", {}).items() if k != "tk"}
            try:
                with open(CFG_FILE, "w", encoding="utf-8") as fp:
                    json.dump(sv, fp, ensure_ascii=False, indent=2)
                global _saved_defaults
                _saved_defaults = sv
            except Exception:
                pass
        if batch:
            _undo_stack.append({"type": "rename", "pairs": [(op, np) for op, np in batch]})
        _log.info(f"do_rename: {ok} ok, stack_depth={len(_undo_stack)}")
        return {"ok": ok, "fail": fail, "total": len(files), "renamed": renamed, "stack_depth": len(_undo_stack)}

    def do_undo(self):
        global _undo_stack
        if not _undo_stack:
            return {"ok": 0, "msg": "没有可撤销的操作"}
        entry = _undo_stack.pop()
        if isinstance(entry, list):
            entry = {"type": "rename", "pairs": entry}
        pairs = entry.get("pairs", [])
        ud = 0; renamed = []
        for op, np in pairs:
            try:
                os.rename(np, op)
                renamed.append({"old_path": np, "new_path": op})
                ud += 1
            except Exception:
                pass
        _log.info(f"do_undo: {ud}/{len(pairs)} reversed, remaining: {len(_undo_stack)}")
        return {"ok": ud, "msg": f"已撤销 {ud} 个", "remaining": len(_undo_stack), "renamed": renamed}


# ============================================================
# 主入口
# ============================================================
HTML_FILE_NAME = "renamer_web.html"
HTML_FILE = os.path.join(_BASE_DIR, HTML_FILE_NAME)

if __name__ == "__main__":
    import threading, socket, io as _io
    from bottle import route, run, static_file

    @route('/')
    def index():
        return static_file(HTML_FILE_NAME, root=_BASE_DIR)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()

    t = threading.Thread(target=lambda: run(host='127.0.0.1', port=port, quiet=True), daemon=True)
    t.start()

    import time, urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)

    api = RenamerAPI()
    _window = webview.create_window(
        title="批量文件命名工具 · 创壹特供版",
        url=f"http://127.0.0.1:{port}",
        js_api=api,
        width=880, height=620,
        min_size=(680, 400),
        resizable=True,
        background_color='#151515',
        text_select=True,
    )

    def _bind_drop():
        from webview.dom import DOMEventHandler
        def _on_drop(e):
            files = e['dataTransfer']['files']
            paths = []
            for f in files:
                fp = f.get('pywebviewFullPath', '')
                if not fp: continue
                if os.path.isfile(fp):
                    paths.append(os.path.realpath(fp))
                elif os.path.isdir(fp):
                    try:
                        for sf in sorted(os.listdir(fp)):
                            sfp = os.path.realpath(os.path.join(fp, sf))
                            if os.path.isfile(sfp):
                                paths.append(sfp)
                    except Exception: pass
            if not paths: return
            _log.info(f"DOM drop: {len(paths)} items")
            result = api._process_paths(paths)
            duplicates = result.get('duplicates', 0)
            if duplicates and not result.get('files'):
                _window.evaluate_js(f'toast("全部重复 · {duplicates} 个已跳过")')
            else:
                _window.evaluate_js(f"onDropResult({json.dumps(result)})")

        _window.dom.document.events.dragover += DOMEventHandler(lambda e: e, prevent_default=True)
        _window.dom.document.events.drop += DOMEventHandler(_on_drop, prevent_default=True, stop_propagation=True)
        _log.info("DOM drop handler bound")

    _window.events.loaded += _bind_drop

    webview.start(debug=False)
