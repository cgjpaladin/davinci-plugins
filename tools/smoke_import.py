#!/usr/bin/env python3
"""
smoke_import.py — ui.py 模块级冒烟测试。
绕过 DaVinci 依赖，只测 Python 层面的 import 完整性。
检测 NameError / ImportError / AssertionError，用于 pre-commit。
"""
import sys, os, re

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# 只加 shared/ 和 交付自检工具/，绝对不加 PROJECT_ROOT（会带入 tools/ 遮蔽 stdlib）
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'shared'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, '交付自检工具'))
# 移除 CWD 和所有可能含 tools/ 的路径
sys.path = [p for p in sys.path if 'tools' not in p]

with open(os.path.join(PROJECT_ROOT, '交付自检工具', 'ui.py'), encoding='utf-8') as f:
    code = f.read()

# 注入 DaVinci mock（确保模块级代码完整执行，不做窗口操作）
_dv_mock = (
    'import types\n'
    '_fu_mock = types.SimpleNamespace(UIManager=None)\n'
    'bmd = types.SimpleNamespace(\n'
    '    scriptapp=lambda x: _fu_mock,\n'
    '    UIDispatcher=lambda x: types.SimpleNamespace(\n'
    '        Notify=types.SimpleNamespace(RequestFileDir=lambda:None,RequestFile=lambda:None),\n'
    '        On={},\n'
    '        Show=types.SimpleNamespace(modal=True),\n'
    '        ExitLoop=lambda:None,\n'
    '        RunLoop=lambda:None\n'
    '    )\n'
    ')\n'
    'fu = _fu_mock\n'
)
code = _dv_mock + '\n' + code

# 移除原始 DaVinci import（已被 mock 替代）
code = re.sub(r'from fusionscript_loader import bmd.*\n', '', code)
code = re.sub(r'''fu = bmd\.scriptapp\(["']Fusion["']\).*\n''', '', code)

try:
    exec(compile(code, 'ui.py', 'exec'), {
        '__name__': '__main__',
        '__file__': os.path.join(PROJECT_ROOT, '交付自检工具', 'ui.py')
    })
    print('✅ ui.py 模块级代码通过')
except NameError as e:
    print(f'❌ NameError: {e}')
    sys.exit(1)
except ImportError as e:
    print(f'❌ ImportError: {e}')
    sys.exit(1)
except AssertionError as e:
    print(f'❌ 断言失败: {e}')
    sys.exit(1)
except Exception as e:
    err_type = type(e).__name__
    if err_type in ('AttributeError', 'TypeError') and any(
        kw in str(e) for kw in ('Resolve', 'project', 'timeline', 'media', 'clip', 'item',
                                'VGroup', 'HGroup', 'Label', 'Button', 'ComboBox',
                                'UIDispatcher', 'Notify', 'StyleSheet')
    ):
        print('✅ ui.py 模块级代码通过（DaVinci runtime error 为预期）')
    else:
        print(f'⚠ {err_type}: {e}')
        sys.exit(1)
