#!/bin/bash
# dvr-connect.sh — 达芬奇外联脚本一键连接
# 用法: source dvr-connect.sh ; python3 -c "..."

export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
export PYTHONPATH="$RESOLVE_SCRIPT_API/Modules:$PYTHONPATH"

PY=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3

if [ ! -f "$PY" ]; then
    echo "❌ Python 3.13 未找到: $PY"
    return 1
fi

# 测试连接
$PY -c "
import DaVinciResolveScript as bmd
r = bmd.scriptapp('Resolve')
if r:
    print('✅ 达芬奇已连接:', r.GetVersionString())
else:
    print('❌ 达芬奇未运行或外联未启用')
    exit(1)
" && echo "✅ 就绪，可直接用 python3 调 DaVinci" || echo "❌ 连接失败"
