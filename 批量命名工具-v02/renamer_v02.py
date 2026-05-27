#!/usr/bin/env python3
"""批量命名工具 v4.0 — Handsontable 版"""
import sys, os, json, logging, hashlib, statistics
from urllib.parse import unquote

from naming import FIELD_CONFIG, build_filename, parse_filename, DESC_TO_METHOD, FALLBACK_RE
from naming_checks import check_zero_byte, check_double_ext

_log = logging.getLogger('renamer_hot')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

MAX_FILES = 500
VIDEO_EXT = {'.mp4', '.mov', '.mxf', '.avi', '.mkv', '.webm', '.m4v', '.mts', '.mpg', '.mpeg', '.wmv', '.3gp', '.flv', '.r3d', '.braw'}


class RenamerAPI:
    """Bottle-compatible API class for pywebview."""
    
    _dbg_buf = []
    _undo_stack = []
    
    def debug_log(self, msg):
        if msg:
            self._dbg_buf.append(msg)
            if len(self._dbg_buf) > 500:
                self._dbg_buf = self._dbg_buf[-500:]
            _log.info(f"[JS] {msg}")
            return "ok"
        return {"log": list(self._dbg_buf)}
    
    def echo(self, x):
        return {"received": x}
    
    def get_config(self):
        fields = [{"key": f["key"], "label": f["label"], "def": f.get("def", ""), "hint": f.get("hint", ""),
                   "dv": f.get("dv", [])} for f in FIELD_CONFIG]
        method_desc_map = {
            "智能分镜版": {"mode": "locked", "value": "智能分镜"},
            "双轨版": {"mode": "dropdown", "values": ["请选择", "智能分镜", "幽灵角色", "空镜", "请手动输入…"]},
            "角色专属版": {"mode": "dropdown", "values": ["请选择", "智能分镜", "请手动输入…"]},
        }
        name_format = [{"pfx": f["name"], "key": f["key"]} for f in FIELD_CONFIG if f["key"] != "tk"]
        field_rules = [{"trigger": "method", "targets": ["desc"], "map": method_desc_map}]
        return {
            "fields": fields, "defaults": {}, "method_desc_map": method_desc_map,
            "name_format": name_format, "field_rules": field_rules
        }
    
    def process_drop_paths(self, paths_json):
        paths = json.loads(paths_json)
        return self._process_paths(paths)
    
    def add_files_via_dialog(self):
        try:
            w = __import__('webview').active_window()
            result = w.create_file_dialog(__import__('webview').OPEN_DIALOG, allow_multiple=True)
            return self._process_paths(result or [])
        except Exception as e:
            _log.error(f"add_files dialog: {e}")
            return {"files": [], "total": 0, "duplicates": 0, "skipped": 0}
    
    def add_folder_via_dialog(self):
        try:
            w = __import__('webview').active_window()
            result = w.create_file_dialog(__import__('webview').FOLDER_DIALOG)
            if not result: return {"files": [], "total": 0, "duplicates": 0, "skipped": 0}
            folder = result[0]
            paths = []
            for root, dirs, filenames in os.walk(folder):
                for fn in filenames:
                    paths.append(os.path.join(root, fn))
            return self._process_paths(paths)
        except Exception as e:
            _log.error(f"add_folder dialog: {e}")
            return {"files": [], "total": 0, "duplicates": 0, "skipped": 0}
    
    def _process_paths(self, paths):
        files = []; duplicates = 0; skipped = 0; truncated = False
        seen_fp = set()
        _EMPTY_KEYS = {'ep', 'sc', 'gr', 'tk', 'ver'}
        parsed_count = 0; no_parse_count = 0
        
        for p in paths[:MAX_FILES]:
            if len(files) >= MAX_FILES: truncated = True; break
            p = str(p).strip()
            if p.startswith("file://"): p = unquote(p[7:])
            if not os.path.isfile(p):
                skipped += 1; continue
            
            ext = os.path.splitext(p)[1].lower()
            if ext not in VIDEO_EXT:
                skipped += 1; continue
            
            if p in {f["path"] for f in files}: duplicates += 1; continue
            try:
                st = os.stat(p)
                fp_key = f"{st.st_size}:{hashlib.md5(open(p, 'rb').read(65536)).hexdigest()}"
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
                else: fields[k] = fd.get("def", "")
            
            basename = os.path.basename(p)
            files.append({"path": p, "basename": basename, "ext": ext, "fields": fields, "fp": fp_key})
            if parsed: parsed_count += 1
            else: no_parse_count += 1
        
        _log.info(f"_process_paths: {len(files)} files, {parsed_count} parsed, {no_parse_count} raw, {duplicates} dup, {skipped} skipped")
        return {"files": files, "total": len(files), "duplicates": duplicates, "skipped": skipped, "truncated": truncated, "max": MAX_FILES}
    
    def do_rename(self, paths, fields_json):
        paths = json.loads(paths) if isinstance(paths, str) else paths
        fields_list = json.loads(fields_json) if isinstance(fields_json, str) else fields_json
        renamed = []
        pairs = []
        for i, src in enumerate(paths):
            fields = fields_list[i]
            new_name = build_filename(fields) + os.path.splitext(src)[1]
            dst = os.path.join(os.path.dirname(src), new_name)
            if os.path.exists(src) and src != dst:
                os.rename(src, dst)
                renamed.append({"old_path": src, "new_path": dst})
                pairs.append((src, dst))
                _log.info(f"renamed: {os.path.basename(src)} → {new_name}")
        self._undo_stack.append({"type": "rename", "pairs": pairs})
        _log.info(f"do_rename: {len(renamed)} renamed, undo_stack: {len(self._undo_stack)}")
        return {"ok": len(renamed), "msg": f"已重命名 {len(renamed)} 个", "remaining": len(self._undo_stack)}
    
    def do_archive(self, paths, fields_json):
        return {"ok": 0, "msg": "归档功能待移植", "remaining": len(self._undo_stack)}
    
    def undo(self):
        if not self._undo_stack: return {"ok": 0, "msg": "无可撤销"}
        entry = self._undo_stack.pop()
        ud = 0
        for op, np in entry.get("pairs", []):
            try:
                if entry["type"] == "archive": os.remove(np)
                else: os.rename(np, op)
                ud += 1
            except Exception:
                pass
        _log.info(f"undo: {ud}/{len(entry.get('pairs',[]))} reversed, remaining: {len(self._undo_stack)}")
        return {"ok": ud, "msg": f"已撤销 {ud} 个", "remaining": len(self._undo_stack)}
    
    def undo_available(self):
        return len(self._undo_stack) > 0
    
    def get_thumbs(self, paths_json):
        return []


# === Bottle App ===
import bottle
bottle.debug(False)
api = RenamerAPI()

@bottle.route('/')
def index():
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    # PyInstaller 环境：HTML 在 MEIPASS 根目录
    html = os.path.join(base, 'table_v02.html')
    return bottle.static_file(html, root='/')

@bottle.route('/api/<method>')
def api_handler(method):
    try:
        result = getattr(api, method, lambda: {"error": "unknown method"})(**dict(bottle.request.query))
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        _log.error(f"API {method}: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@bottle.post('/api/<method>')
def api_post(method):
    try:
        body = bottle.request.body.read().decode('utf-8')
        result = getattr(api, method, lambda _: {"error": "unknown method"})(body)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        _log.error(f"API POST {method}: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)

if __name__ == '__main__':
    import webview
    import threading
    from webview import DOMEventHandler
    
    HOST = '127.0.0.1'; PORT = 18882
    bottle_thread = threading.Thread(target=lambda: bottle.run(host=HOST, port=PORT, quiet=True), daemon=True)
    bottle_thread.start()
    
    print(f'批量命名工具 v4.0 — http://{HOST}:{PORT}')
    _window = webview.create_window('批量命名工具 v4.0', f'http://{HOST}:{PORT}', width=1200, height=800, js_api=api)
    
    def _bind_drop():
        def _on_drop(e):
            paths = []
            for item in e['dataTransfer']['files']:
                p = item.get('path', '') or item.get('name', '')
                if p: paths.append(p)
            if not paths: return
            result = api._process_paths(paths)
            _window.evaluate_js(f"onDropResult({json.dumps(result, ensure_ascii=False)})")
        _window.dom.document.events.drop += DOMEventHandler(_on_drop, prevent_default=True, stop_propagation=True)
    
    _window.events.loaded += _bind_drop
    webview.start()
