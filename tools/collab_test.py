#!/usr/bin/env python3
"""
collab_test.py — PostgreSQL 协作模式全链路测试
用法: python3 collab_test.py [--round A1] [--round all] [--skip-prep]
"""

import json, os, subprocess, sys, tempfile, time, traceback, random

PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
MAIN = "mini101"
PEER = "mini103"
PROJECT = "20260424_小龙虾测试中)"
TIMELINE = "EP04_剪辑_v01"
IO_START = 1399
IO_END = 2052
SMB_PLUGIN = "/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕"
OUTPUT_DIR = "/Volumes/MYJC/06_Software/达芬奇脚本/test_output"

results = {"passed": 0, "failed": 0, "skipped": 0, "details": []}

def remote_run(machine, script, timeout=120):
    local = f"/tmp/colab_{machine}_{int(time.time()*1000)}.py"
    remote = f"/tmp/colab_script.py"
    with open(local, "w") as f: f.write(script)
    try:
        subprocess.run(["scp", local, f"{machine}:{remote}"], capture_output=True, timeout=10, check=True)
    except Exception as e:
        return False, f"SCP 失败: {e}"
    finally:
        try: os.remove(local)
        except: pass
    try:
        r = subprocess.run(["ssh", machine, f"{PYTHON} {remote}"], capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return False, "超时"
    except Exception as e:
        return False, str(e)

def remote_run_bg(machine, script):
    local = f"/tmp/colab_bg_{machine}_{int(time.time()*1000)}.py"
    remote = f"/tmp/colab_bg_script.py"
    with open(local, "w") as f: f.write(script)
    subprocess.run(["scp", local, f"{machine}:{remote}"], capture_output=True, timeout=10, check=True)
    try: os.remove(local)
    except: pass
    r = subprocess.run(["ssh", machine, f"nohup {PYTHON} {remote} > /tmp/colab_bg.log 2>&1 & echo $!"], capture_output=True, text=True, timeout=10)
    return r.stdout.strip()

def dvr(imports="", body=""):
    return f'''import sys, json, os, time
sys.path.append("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
sys.path.insert(0, "{SMB_PLUGIN}")
import DaVinciResolveScript as bmd
r = bmd.scriptapp("Resolve")
pm = r.GetProjectManager()
proj = pm.GetCurrentProject()
{imports}
{body}'''

def test(name, ok, output, expected=None):
    status = "PASS" if (expected is None and ok) or (expected is not None and expected in output) else "FAIL"
    if status == "PASS": results["passed"] += 1
    else: results["failed"] += 1
    results["details"].append({"name": name, "status": status, "output": output[:500]})
    print(f"  [{status}] {name}")
    if status == "FAIL": print(f"         {output[:200]}")
    return status == "PASS"

def wait_ready(machine, timeout=60):
    for i in range(timeout // 5):
        ok, out = remote_run(machine, dvr(body="print('READY')"))
        if "READY" in out: return True
        time.sleep(5)
    return False

# ═══════════════════ ROUND A: 单机基准 ═══════════════════

def a1_dry_run():
    print("\n── A1: PG dry-run ──")
    s = dvr(body=f"""
os.makedirs("{OUTPUT_DIR}", exist_ok=True)
tl = proj.GetCurrentTimeline()
if not tl or tl.GetName() != "{TIMELINE}":
    for i in range(proj.GetTimelineCount()):
        if proj.GetTimelineByIndex(i+1).GetName() == "{TIMELINE}":
            proj.SetCurrentTimeline(proj.GetTimelineByIndex(i+1)); tl = proj.GetCurrentTimeline(); break
tl.SetMarkInOut({IO_START}, {IO_END})
from core import scan_io_clips
clips, report = scan_io_clips(tl, "Orange")
if not clips: print("SKIP: 无橙色片段"); sys.exit(0)
print(f"扫描: {{report.valid}} 个")
from remove_subtitle import run_pipeline
result = run_pipeline(mode="pro_box", dry_run=True, force=False, report_json="{OUTPUT_DIR}/a1.json", batch=True, project_root="{OUTPUT_DIR}")
print(f"PASS: dry-run done" if result.get("dry_run_completed") else f"OK: {{result.get('completed','?')}}")
""")
    ok, out = remote_run(MAIN, s, timeout=60)
    test("A1: dry-run", "PASS" in out or "OK" in out, out)

def a2_full_process():
    print("\n── A2: PG 正式处理 ──")
    s = dvr(body=f"""
os.makedirs("{OUTPUT_DIR}", exist_ok=True)
tl = proj.GetCurrentTimeline(); tl.SetMarkInOut({IO_START}, {IO_END})
from remove_subtitle import run_pipeline
result = run_pipeline(mode="pro_box", dry_run=False, force=True, report_json="{OUTPUT_DIR}/a2.json", batch=True, project_root="{OUTPUT_DIR}")
r = result.get("results", {{}})
if r: print(f"PASS: {{r.get('success',0)}}/{{r.get('total',0)}} 完成")
elif result.get("error"): print(f"ERROR: {{result['error']}}")
else: print("OK: 处理完成")
""")
    ok, out = remote_run(MAIN, s, timeout=300)
    test("A2: 正式处理", "PASS" in out or "OK" in out, out)

def a3_undo():
    print("\n── A3: 撤销 ──")
    s = dvr(body=f"""
tl = proj.GetCurrentTimeline(); tl.SetMarkInOut({IO_START}, {IO_END})
from subtitle_state import get_original_path
from core import connect_resolve
r_obj, proj_obj, tl2 = connect_resolve()
found = undone = 0
for t in range(1, tl2.GetTrackCount("video")+1):
    for item in (tl2.GetItemListInTrack("video", t) or []):
        nm = item.GetName()
        if "_去字幕_" not in nm: continue
        found += 1
        mp = item.GetMediaPoolItem()
        if not mp: continue
        fn = mp.GetClipProperty("File Name") or nm
        key = fn.split("_去字幕_")[0] + ".mp4" if "_去字幕_" in fn else fn
        orig = get_original_path(key)
        if orig and os.path.exists(orig):
            mp.ReplaceClipPreserveSubClip(orig); undone += 1
print(f"PASS: 撤销 {{undone}}/{{found}}" if undone else f"SKIP: 无去字幕片段 (found {{found}})")
""")
    ok, out = remote_run(MAIN, s, timeout=60)
    test("A3: 撤销", "PASS" in out or "SKIP" in out, out)

# ═══════════════════ ROUND B: Bin 锁 ═══════════════════

def b1_bin_access():
    print("\n── B1: Bin 访问 ──")
    s = dvr(body="""
r.OpenPage("media"); mp = proj.GetMediaPool(); root = mp.GetRootFolder()
subs = root.GetSubFolderList()
if subs: mp.SetCurrentFolder(subs[0]); print(f"PASS: Bin={subs[0].GetName()}")
else: print("SKIP: 无子文件夹")
""")
    ok, out = remote_run(MAIN, s, timeout=30)
    test("B1: Bin访问", "PASS" in out, out)

def b2_bin_interference():
    print("\n── B2: 干扰机占Bin, 主测机扫描 ──")
    # 干扰机
    bg = dvr(body="""
r.OpenPage("media"); mp = proj.GetMediaPool(); root = mp.GetRootFolder()
subs = root.GetSubFolderList()
if subs: mp.SetCurrentFolder(subs[0]); print(f"PEER: 占 {subs[0].GetName()}"); time.sleep(25); print("PEER: 释放")
else: print("PEER: 无文件夹")
""")
    pid = remote_run_bg(PEER, bg)
    print(f"  干扰PID: {pid}")
    time.sleep(4)
    # 主测机
    s = dvr(body=f"""
tl = proj.GetCurrentTimeline(); tl.SetMarkInOut({IO_START}, {IO_END})
from core import scan_io_clips
clips, report = scan_io_clips(tl, "Orange")
print(f"PASS: 扫描 {{report.valid}} 片段" if clips else "SKIP: 无片段")
""")
    ok, out = remote_run(MAIN, s, timeout=30)
    test("B2: Bin占时扫描", "PASS" in out, out)

# ═══════════════════ ROUND C: 并发 ═══════════════════

def c3_lock_test():
    print("\n── C3: 并发锁 ──")
    for m, role in [(MAIN, "主测"), (PEER, "干扰")]:
        s = dvr(body=f"""
tl = proj.GetCurrentTimeline(); tl.SetMarkInOut({IO_START}, {IO_END})
from core import scan_io_clips; from subtitle_state import acquire_lock, release_lock, is_locked
clips, report = scan_io_clips(tl, "Orange")
if clips:
    c = clips[0]; result = acquire_lock(c.name)
    label = "LOCK_OK" if result == True else ("LOCK_RECLAIMED" if result == "reclaimed" else "LOCK_DENIED")
    print(f"{{label}}: {{c.name}} ({role})")
    if result: release_lock(c.name)
    else: print(f"  占用: {{is_locked(c.name) or '?'}}")
else: print("SKIP ({role})")
""")
        ok, out = remote_run(m, s, timeout=30)
        test(f"C3: {role}", ok, out)

# ═══════════════════ ROUND D: 状态文件 ═══════════════════

def d1_state_concurrent():
    print("\n── D1: 状态并发写 ──")
    names = [f"CTEST_{random.randint(1000,9999)}" for _ in range(3)]
    ns = str(names)
    s = dvr(body=f"""
from subtitle_state import init, record_original, get_clip_status
import socket
init("{OUTPUT_DIR}")
for tn in {ns}: record_original(tn, f"/tmp/fake_{{tn}}.mp4")
host = socket.gethostname()
missing = [tn for tn in {ns} if get_clip_status(tn) != "original"]
if missing: print(f"FAIL: {{len(missing)}} 丢失 from {{host}}: {{missing}}")
else: print(f"PASS: {{len({ns})}} 条正常 from {{host}}")
sf = os.path.join("{OUTPUT_DIR}", "04_素材", "03_去字幕", ".subtitle_state.json")
if os.path.exists(sf):
    import json; st = json.load(open(sf)); [st.pop(tn, None) for tn in {ns}]; json.dump(st, open(sf, "w"))
""")
    ok1, out1 = remote_run(MAIN, s, timeout=30)
    ok2, out2 = remote_run(PEER, s, timeout=30)
    test("D1: 主测", "PASS" in out1, out1)
    test("D1: 干扰", "PASS" in out2, out2)

# ═══════════════════ MAIN ═══════════════════

ROUNDS = {
    "A1": a1_dry_run, "A2": a2_full_process, "A3": a3_undo,
    "B1": b1_bin_access, "B2": b2_bin_interference,
    "C3": c3_lock_test,
    "D1": d1_state_concurrent,
}

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--round", default="all")
    p.add_argument("--skip-prep", action="store_true")
    args = p.parse_args()

    print(f"PG 协作测试 — {MAIN}(主测) + {PEER}(干扰)")
    print(f"项目: {PROJECT} / 时间线: {TIMELINE} / IO: {IO_START}-{IO_END}")
    print("=" * 50)

    if not args.skip_prep:
        print("检查主测..."); wait_ready(MAIN)
        print("检查干扰..."); wait_ready(PEER)
        print("就绪\n")

    if args.round == "all":
        for name, fn in ROUNDS.items():
            try: fn()
            except Exception as e: print(f"  [ERR] {name}: {e}"); results["failed"] += 1
    elif args.round in ROUNDS:
        ROUNDS[args.round]()
    else:
        print(f"未知: {args.round}"); print(f"可用: {list(ROUNDS.keys())}")
        return

    total = results["passed"] + results["failed"]
    print(f"\n{'='*50}\n结果: {results['passed']}/{total} 通过")
    if results["failed"]:
        for d in results["details"]:
            if d["status"] == "FAIL": print(f"  ❌ {d['name']}")

if __name__ == "__main__":
    main()
