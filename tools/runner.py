#!/usr/bin/env python3
"""
tools/runner.py — 达芬奇脚本自动化运行器
─────────────────────────────────────────
自动打开DaVinci → 加载项目 → 设IO → 跑测试 → 崩溃自愈

用法：
  python3 tools/runner.py [ui|scan|all]

配置（通过环境变量覆盖）：
  WATERMARK_TEST_PROJECT   测试项目名
  WATERMARK_TEST_TIMELINE  测试时间线
  WATERMARK_TEST_IO_START  IO入点帧
  WATERMARK_TEST_IO_END    IO出点帧
  WATERMARK_SMB_PLUGIN     SMB插件路径
"""
import sys, os, time, subprocess, threading, json, traceback
from datetime import datetime

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
import _env
_env.setup()

# ── 测试配置（可通过环境变量覆盖）──
TEST_PROJECT = os.environ.get("WATERMARK_TEST_PROJECT", "20260424_小龙虾测试中)")
TEST_TIMELINE = os.environ.get("WATERMARK_TEST_TIMELINE", "EP01_剪辑_v01")
TEST_IO_START = int(os.environ.get("WATERMARK_TEST_IO_START", "4753"))
TEST_IO_END = int(os.environ.get("WATERMARK_TEST_IO_END", "4949"))
SMB_PLUGIN = os.environ.get("WATERMARK_SMB_PLUGIN", "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕")
MAX_RETRIES = 3

# 从 _env 取路径（跨平台）
RESOLVE_API = _env.RESOLVE_SCRIPT_API
RESOLVE_LIB = _env.RESOLVE_SCRIPT_LIB
RESOLVE_MODULES = _env.RESOLVE_MODULES
CRASH_LOG = _env.CRASH_LOG


def resolve_script(code):
    """在达芬奇环境中执行一段 Python 代码，返回 stdout"""
    env = os.environ.copy()
    env["RESOLVE_SCRIPT_API"] = RESOLVE_API
    env["RESOLVE_SCRIPT_LIB"] = RESOLVE_LIB
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") + ":" + RESOLVE_MODULES
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
        env=env
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


# ═══════════════════════════════════════════
# DaVinci 生命周期
# ═══════════════════════════════════════════

def dv_running():
    """DaVinci 进程是否在跑"""
    r = subprocess.run(["pgrep", "-l", "Resolve"], capture_output=True, text=True)
    return r.returncode == 0


def dv_ready():
    """DaVinci 是否接受脚本连接"""
    out, _, rc = resolve_script("""
import DaVinciResolveScript as bmd
r = bmd.scriptapp('Resolve')
print('OK' if r else 'NO')
""")
    return "OK" in out


def dv_open(timeout=90):
    """打开 DaVinci 并等待就绪"""
    if dv_ready():
        print("[DaVinci] 已在运行 ✅")
        return True
    
    if dv_running():
        print("[DaVinci] 进程在但不接受脚本，等待...")
        for i in range(timeout // 5):
            time.sleep(5)
            if dv_ready():
                print(f"[DaVinci] ✅ ({ (i+1)*5 }秒)")
                return True
    
    print("[DaVinci] 启动...")
    subprocess.run(["open", "-a", "DaVinci Resolve"])
    for i in range(timeout // 5):
        time.sleep(5)
        if dv_ready():
            print(f"[DaVinci] ✅ ({ (i+1)*5 }秒)")
            return True
    
    print("[DaVinci] ❌ 超时")
    return False


def dv_kill():
    """杀掉 DaVinci"""
    subprocess.run(["killall", "Resolve"], capture_output=True)
    time.sleep(3)


def dv_restart():
    """重启 DaVinci"""
    print("[DaVinci] 重启...")
    dv_kill()
    return dv_open()


def dv_crash_reason():
    """分析最近一次崩溃"""
    if not os.path.exists(CRASH_LOG):
        return None
    try:
        mtime = os.path.getmtime(CRASH_LOG)
        if time.time() - mtime > 600:
            return None
        with open(CRASH_LOG) as f:
            content = f.read()
        if "ScriptSymbolD0Ev" in content:
            return "ScriptSymbolD0Ev (widget构造崩溃)"
        if "HandleUIE" in content:
            return "HandleUIE (UI渲染崩溃)"
        return "未知崩溃"
    except:
        return None


# ═══════════════════════════════════════════
# 项目操作
# ═══════════════════════════════════════════

def project_setup():
    """加载测试项目，选中时间线，设 IO"""
    print("[Project] 加载测试项目...")
    code = """
import DaVinciResolveScript as bmd
r = bmd.scriptapp('Resolve')
if not r:
    print('NO_RESOLVE')
    exit(1)
pm = r.GetProjectManager()
pj = pm.LoadProject('""" + TEST_PROJECT + """')
if not pj:
    print('NO_PROJECT')
    exit(1)
print('PROJECT:' + pj.GetName())
# 找 EP01_素材 时间线
tc = pj.GetTimelineCount()
for i in range(1, tc+1):
    tl = pj.GetTimelineByIndex(i)
    if '""" + TEST_TIMELINE + """' in tl.GetName():
        pj.SetCurrentTimeline(tl)
        items = tl.GetItemListInTrack('video', 1)
        tl.SetMarkInOut(""" + str(TEST_IO_START) + """, """ + str(TEST_IO_END) + """)
        count = 0
        if items:
            for item in items:
                s, e = item.GetStart(), item.GetEnd()
                if s >= """ + str(TEST_IO_END) + """ or e <= """ + str(TEST_IO_START) + """:
                    continue
                count += 1
        print('OK:' + tl.GetName() + ':' + str(""" + str(TEST_IO_START) + """) + ':' + str(""" + str(TEST_IO_END) + """) + ':' + str(count) + ' clips')
        exit(0)
print('NO_TIMELINE')
"""
    out, err, rc = resolve_script(code)
    print(f"  {out}")
    if err:
        print(f"  stderr: {err[:200]}")
    return "OK:" in out


# ═══════════════════════════════════════════
# 测试模块
# ═══════════════════════════════════════════

def test_basic_window():
    """测试1: 基础窗口构造"""
    print("[测试] 基础窗口构造...")
    out, err, rc = resolve_script("""
import DaVinciResolveScript as bmd
fu = bmd.scriptapp('Fusion')
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)
dlg = disp.AddWindow({'WindowTitle':'Test','ID':'tb','Geometry':[800,300,300,100]},
    [ui.Label({'ID':'l','Text':'OK'})])
print('PASS')
""")
    ok = "PASS" in out
    print(f"  {'✅' if ok else '❌'} {out}")
    if err: print(f"  err: {err[:100]}")
    return ok


def test_full_window():
    """测试2: 完整 UI 窗口构造（SMB 加载）"""
    print("[测试] 完整 UI 构造 (SMB)...")
    code = """import sys, traceback
sys.path.append('""" + SMB_PLUGIN + """')
sys.path.append('""" + RESOLVE_MODULES + """')
import DaVinciResolveScript as bmd
from config import DEFAULT_MODE, MODE_LABELS, __version__

fu = bmd.scriptapp('Fusion')
ui = fu.UIManager
disp = bmd.UIDispatcher(ui)

try:
    dlg = disp.AddWindow({
        'WindowTitle': 'AI xxxx',
        'ID': 'test_full',
        'Geometry': [800, 300, 500, 520],
    }, [
        ui.VGroup({'Spacing': 8}, [
            ui.HGroup({'Spacing': 10}, [
                ui.Label({'ID': 'lb1', 'Text': 'OK'}),
                ui.ComboBox({'ID': 'cb1'}),
            ]),
            ui.HGroup({'Spacing': 10}, [
                ui.Button({'ID': 'b1', 'Text': 'btn1'}),
                ui.Button({'ID': 'b2', 'Text': 'btn2'}),
            ]),
            ui.Label({'ID': 'log', 'Text': ''}),
            ui.Stack({'ID': 'pg'}, [
                ui.Label({'ID': 'pg_bg', 'StyleSheet': 'max-height: 3px; background-color: rgb(37,37,37);'}),
                ui.Label({'ID': 'pg_bar', 'StyleSheet': 'max-height: 1px; background-color: rgb(102,221,39);'}),
            ]),
            ui.Label({'ID': 'st', 'Text': 'ready'}),
        ]),
    ])
    print('PASS')
except Exception as ex:
    print('FAIL:' + str(ex)[:200])
    traceback.print_exc()
"""
    out, err, rc = resolve_script(code)
    ok = "PASS" in out
    print(f"  {'✅' if ok else '❌'} {out[:300]}")
    if err: print(f"  err: {err[:200]}")
    return ok


def test_project_io():
    """测试3: 项目 IO 扫描"""
    print("[测试] 扫描 IO 内片段...")
    out, err, rc = resolve_script("""
import DaVinciResolveScript as bmd
r = bmd.scriptapp('Resolve')
pj = r.GetProjectManager().GetCurrentProject()
tl = pj.GetCurrentTimeline()
io = tl.GetMarkInOut()
v = io.get('video', {})
i_in, i_out = v.get('in', 0), v.get('out', 0)
count = 0
for t in range(1, tl.GetTrackCount('video') + 1):
    items = tl.GetItemListInTrack('video', t)
    if not items: continue
    for item in items:
        s, e = item.GetStart(), item.GetEnd()
        if s >= i_out or e <= i_in: continue
        count += 1
print(f'IO:{i_in}-{i_out}:{count} clips')
""")
    print(f"  {out}")
    return "IO:" in out


# ═══════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════

def run_test_cycle(test_func, name):
    """带崩溃检测的单测试循环"""
    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print(f"\n[重试 {attempt}/{MAX_RETRIES}]")
            crash = dv_crash_reason()
            if crash:
                print(f"  上次崩溃: {crash}")
            if not dv_running():
                dv_open()
            elif not dv_ready():
                time.sleep(5)
        
        ok = test_func()
        if ok:
            return True
        
        # 失败，查原因
        if not dv_running():
            print("  DaVinci 已崩溃")
            crash = dv_crash_reason()
            if crash:
                print(f"  原因: {crash}")
            dv_open()
        else:
            print("  测试失败但 DaVinci 仍在运行")
    
    return False


def main():
    test_name = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    print("╔" + "═" * 58 + "╗")
    print(f"║  达芬奇自动化测试  {datetime.now().strftime('%H:%M:%S')}".ljust(61) + "║")
    print("╚" + "═" * 58 + "╝")
    
    # Step 1: 确保 DaVinci 运行
    if not dv_open():
        print("\n❌ 无法启动 DaVinci")
        return 1
    
    # Step 2: 加载测试项目
    if not project_setup():
        print("\n❌ 无法加载测试项目")
        return 1
    
    # Step 3: 跑测试
    results = {}
    
    if test_name in ("ui", "all"):
        results["基础窗口"] = run_test_cycle(test_basic_window, "基础窗口")
    
    if test_name in ("ui", "all"):
        results["完整UI"] = run_test_cycle(test_full_window, "完整UI")
    
    if test_name in ("scan", "all"):
        results["IO扫描"] = run_test_cycle(test_project_io, "IO扫描")
    
    # 汇总
    print("\n" + "=" * 60)
    print("  测试结果")
    print("=" * 60)
    all_ok = True
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name}")
        if not ok:
            all_ok = False
    
    if all_ok and results:
        print("\n  🎉 全部通过！")
    else:
        print(f"\n  ⚠️ {sum(1 for v in results.values() if not v)}/{len(results)} 失败")
    
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
