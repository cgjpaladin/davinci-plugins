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

_undo_stack = []
_window = None  # 存引用


class RenamerAPI:

    def get_config(self):
        return {
            "fields": DISPLAY_FIELDS,
            "defaults": _saved_defaults,
            "method_desc_map": METHOD_DESC_MAP,
            "field_rules": FIELD_RULES,
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

    def _process_paths(self, paths):
        _log.info(f"_process_paths received {len(paths)} paths")
        for i, p in enumerate(paths[:5]):
            _log.info(f"  [{i}] raw={p!r}")
        files = []
        defaults = _saved_defaults
        home = os.path.expanduser("~")
        desktop = os.path.join(home, "Desktop")
        downloads = os.path.join(home, "Downloads")
        for p in paths:
            p = str(p).strip()
            if p.startswith("file://"):
                p = unquote(p[7:])
            p = os.path.expanduser(p)

            # 只有文件名 → 搜索常用位置
            if os.path.basename(p) == p and not os.path.isabs(p):
                found = False
                for d in [desktop, downloads, home]:
                    candidate = os.path.join(d, p)
                    if os.path.isfile(candidate):
                        p = candidate; found = True; break
                if not found:
                    _log.info(f"  SKIP cannot resolve: {p!r}")
                    continue

            if not os.path.isfile(p):
                _log.info(f"  SKIP not a file: {p!r}")
                continue
            parsed = parse_filename(p)
            fields = {}
            for fd in FIELD_CONFIG:
                k = fd["key"]
                if parsed and k in parsed:
                    fields[k] = parsed[k]
                elif defaults and k in defaults:
                    fields[k] = defaults.get(k, fd["def"])
                else:
                    fields[k] = fd["def"]
            files.append({
                "path": p,
                "basename": os.path.basename(p),
                "ext": os.path.splitext(os.path.basename(p))[1],
                "fields": fields,
            })
        return {"files": files, "total": len(files)}

    def build_preview_filename(self, fields):
        return {"filename": build_filename(fields)}

    def do_rename(self, files):
        global _undo_stack
        ok = 0
        fail = []
        _undo_stack.clear()
        renamed = []
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
                _undo_stack.append((p, np))
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
        return {"ok": ok, "fail": fail, "total": len(files), "renamed": renamed}

    def do_undo(self):
        global _undo_stack
        if not _undo_stack:
            return {"ok": 0, "msg": "没有可撤销的操作"}
        ud = 0
        for op, np in _undo_stack:
            try:
                os.rename(np, op)
                ud += 1
            except:
                pass
        _undo_stack.clear()
        return {"ok": ud, "msg": f"已撤销 {ud} 个"}

    def do_check(self, paths):
        zero = 0; size_w = 0; fmt_w = 0; dbl = 0
        anomalies = set()
        if paths:
            anomalies = {fp for fp, _ in check_size_anomaly(paths)}
        results = []
        for p in paths:
            tags = []
            if check_zero_byte(p):
                tags.append("zero"); zero += 1
            elif p in anomalies:
                tags.append("size"); size_w += 1
            if not parse_filename(p):
                tags.append("fmt"); fmt_w += 1
            if check_double_ext(os.path.basename(p)):
                tags.append("dbl_ext"); dbl += 1
            results.append({"path": p, "tags": tags})
        msgs = []
        if zero: msgs.append(f"零字节: {zero} 个")
        if size_w: msgs.append(f"大小异常: {size_w} 个")
        if fmt_w: msgs.append(f"命名格式不符: {fmt_w} 个")
        if dbl: msgs.append(f"扩展名重复: {dbl} 个")
        return {"issues": zero + size_w + fmt_w + dbl, "msgs": msgs, "per_file": results}

    def validate_dest(self, dest):
        v = dest.strip()
        if not v: return {"ok": False, "msg": ""}
        m = PATH_RE.match(v)
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
        ok = 0; fail = []
        for f in files:
            target = build_folder(dest, {
                "path": f["path"], "fields": f["fields"],
                "ext": os.path.splitext(f["basename"])[1],
            })
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
    )
    webview.start(debug=False)
