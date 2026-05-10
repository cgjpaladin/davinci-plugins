#!/usr/bin/env python3
# launcher.py — 交付自检工具启动器
# 部署策略：
#   本地开发    → ~/Library/.../本地版/交付自检_v1.1.0-dev.py
#   灰度测试    → 灰度机 ~/Library/.../本地版/交付自检_v1.1.0-dev.py
#   全公司发布  → ~/Library/.../公司版/交付自检.py（无版本号）
#
# 自检：python3 launcher.py --dry-run

import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

if "--dry-run" in sys.argv:
    print("═══ 交付自检 部署自检 ═══")
    checks = []

    # Python 版本
    v = sys.version_info
    checks.append(("Python", v >= (3, 9), f"{v.major}.{v.minor}.{v.micro}"))

    # 核心模块
    for mod in ["config", "ui", "check_core"]:
        try:
            __import__(mod)
            checks.append((mod, True, "OK"))
        except Exception as e:
            checks.append((mod, False, str(e)[:60]))

    # 版本号
    try:
        from config import version_string
        checks.append(("版本", True, version_string()))
    except:
        checks.append(("版本", False, "ERR"))

    # 结果
    ok = all(c[1] for c in checks)
    for name, passed, detail in checks:
        print(f"  {'✅' if passed else '❌'} {name}: {detail}")
    print()
    if ok:
        print("✅ 部署自检通过")
    else:
        print("❌ 部署自检失败")
        sys.exit(1)
else:
    # 正常启动 UI
    import ui
    ui.main()
