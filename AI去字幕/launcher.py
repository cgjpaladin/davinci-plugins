#!/usr/bin/env python3
# launcher.py — AI去字幕 启动器
# 部署到达芬奇 Fusion/Scripts/Edit/，通过 subprocess 外挂外部 Python 进程运行 UI
# 注意: DaVinci Fusion 内 __file__ 不存在，需 fallback
import subprocess, os, sys, time, tempfile

_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if not os.path.exists(_PYTHON):
    _PYTHON = "/usr/bin/python3"

# __file__ 在 DaVinci Fusion 引擎内不存在，fallback 到已知路径
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = os.path.join(os.path.expanduser("~"),
        "Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit")

_PRODUCT_DIRS = [
    '/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕',   # SMB 生产
    os.path.join(_HERE, '..', '..', 'AI去字幕'),         # 本地开发
]

_STABLE_UI = None
for d in _PRODUCT_DIRS:
    candidate = os.path.join(d, 'stable_ui.py')
    if os.path.exists(candidate):
        _STABLE_UI = candidate
        break

if not _STABLE_UI:
    _LOG = os.path.join(tempfile.gettempdir(), "ai_subtitle_launcher.err")
    with open(_LOG, "w") as f:
        f.write(f"找不到 stable_ui.py\n搜索路径: {_PRODUCT_DIRS}\n")
    raise FileNotFoundError(f"找不到 stable_ui.py")

# 日志
_log = os.path.join(tempfile.gettempdir(), "ai_subtitle_ui.log")
with open(_log, "a", encoding="utf-8") as f:
    f.write(f"\n=== AI去字幕 UI 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    f.write(f"stable_ui: {_STABLE_UI}\n")
    f.write(f"python: {_PYTHON}\n")

# dry-run 自检（仅外部 Python 可见，Fusion 内点脚本不会带这个参数）
if '--dry-run' in sys.argv:
    import socket
    print(f"═══ AI去字幕 部署自检 ═══")
    checks = []
    v = sys.version_info
    checks.append(("Python", v >= (3, 9), f"{v.major}.{v.minor}.{v.micro}"))
    host = socket.gethostname()
    routing = "DEV" if host in {"BryandeMac-mini.local", "BryandeMac-mini"} else "SMB"
    checks.append(("路由", True, routing))
    checks.append(("stable_ui", os.path.exists(_STABLE_UI), _STABLE_UI))
    checks.append(("python", os.path.exists(_PYTHON), _PYTHON))
    result = subprocess.run([_PYTHON, '-c',
        f'import sys; sys.path.insert(0,"{os.path.dirname(_STABLE_UI)}"); sys.path.insert(0,"{os.path.dirname(_STABLE_UI)}/../shared"); import config; print(config.version_string())'
    ], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        checks.append(("模块导入", True, result.stdout.strip()))
    else:
        checks.append(("模块导入", False, result.stderr.strip()[:60]))
    ok = all(c[1] for c in checks)
    for name, passed, detail in checks:
        print(f"  {'✅' if passed else '❌'} {name}: {detail}")
    print(f"\n{'✅ 部署自检通过' if ok else '❌ 部署自检失败'}")
    sys.exit(0 if ok else 1)

# 启动外部 Python 进程
_env = os.environ.copy()
_env["PYTHONIOENCODING"] = "utf-8"
_stdout = open(_log, "a", encoding="utf-8")
_stderr = open(_log, "a", encoding="utf-8")
subprocess.Popen([_PYTHON, _STABLE_UI], env=_env, stdout=_stdout, stderr=_stderr)
