#!/usr/bin/env python3
"""
达芬奇 UI 沙盒 — 独立窗口，改 UI 前先验证，不污染生产插件。

用法:
  python3 tools/davinci_ui_sandbox.py              # 写入你的测试代码
  python3 tools/davinci_ui_sandbox.py --nogui       # 自动启动 nogui 达芬奇
  python3 tools/davinci_ui_sandbox.py --nogui --quit # 测完自动退出

Template:
  def my_test(ui, disp):
      win = disp.AddWindow({'ID':'t','Geometry':[500,300,300,200],...}, [...])
      itm = win.GetItems()
      # ... test logic ...
      print('✅ Passed')
      disp.ExitLoop(); win.Hide()

  register('My Test', my_test)
"""
import sys
import os
import time
import subprocess
import argparse

RESOLVE_MODULES = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
_FUSION_SO = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"


def _start_davinci():
    """启动 nogui 达芬奇，等待就绪。返回是否成功。"""
    if _connect():
        return True  # 已经在跑
    print("启动 DaVinci nogui...")
    subprocess.Popen([
        "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/MacOS/Resolve",
        "-nogui"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i in range(30):
        time.sleep(2)
        if _connect():
            print(f"就绪 ({i*2+2}s)")
            return True
    print("❌ 达芬奇启动超时")
    return False


def _connect():
    """尝试连接达芬奇。返回 resolve 对象或 None。"""
    try:
        sys.path.insert(0, RESOLVE_MODULES)
        import DaVinciResolveScript as bmd
        return bmd.scriptapp("Resolve")
    except Exception:
        return None


def register(name, fn):
    """注册一个测试函数。"""
    global _tests
    _tests.append((name, fn))


_tests = []


# ═══════════════════════════════════════════
# 👇 在这里写你的测试
# ═══════════════════════════════════════════

def test_button(ui, disp):
    """按钮点击测试"""
    win = disp.AddWindow({
        'ID': 'sandbox_btn', 'Geometry': [500, 300, 300, 200],
        'WindowFlags': {'Window': True},
    }, [
        ui.VGroup({'Spacing': 10}, [
            ui.Button({'ID': 'btn', 'Text': 'Click Me'}),
            ui.Label({'ID': 'lb', 'Text': 'waiting...'}),
        ]),
    ])
    itm = win.GetItems()
    def on_click(ev):
        itm['lb'].Text = 'clicked!'
        disp.ExitLoop()
    win.On['btn'].Clicked = on_click
    win.Show()
    disp.RunLoop()
    win.Hide()
    assert itm['lb'].Text == 'clicked!', f"Expected 'clicked!', got '{itm['lb'].Text}'"
register('Button Click', test_button)


# ═══════════════════════════════════════════

def main():
    args = argparse.Namespace()
    # 解析简单命令行参数
    args.nogui = '--nogui' in sys.argv
    args.quit = '--quit' in sys.argv

    if not _connect():
        if args.nogui:
            if not _start_davinci():
                sys.exit(1)
        else:
            print("达芬奇未运行。加 --nogui 自动启动，或手动打开达芬奇。")
            sys.exit(1)

    import importlib.machinery
    loader = importlib.machinery.ExtensionFileLoader("fusionscript", _FUSION_SO)
    bmd = loader.load_module()
    fu = bmd.scriptapp("Fusion")
    ui = fu.UIManager
    disp = bmd.UIDispatcher(ui)

    passed = 0
    failed = 0
    for name, fn in _tests:
        try:
            print(f"  {name}...", end=" ")
            fn(ui, disp)
            print("✅")
            passed += 1
        except Exception as e:
            print(f"❌ {e}")
            failed += 1
            try: disp.ExitLoop()
            except: pass

    print(f"\n✅ {passed}  |  ❌ {failed}")

    if args.quit:
        try:
            bmd.scriptapp("Resolve").Quit()
        except:
            pass


if __name__ == "__main__":
    main()
