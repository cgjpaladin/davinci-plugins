#!/bin/bash
# dev.sh — 改完代码一键验证（本地跑，不用达芬奇菜单）
# 用法: ./dev.sh
set -e

# ── 1. 语法检查 ──
echo "═══ 1. 语法编译 ═══"
SMB="/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕"
FAIL=0
for f in ui_external.py core.py config.py pricing.py remove_watermark.py logger.py ops_logger.py watermark_state.py adapters/__init__.py adapters/wuhenai_v2.py; do
    if python3 -m py_compile "$f" 2>/dev/null; then
        echo "  ✅ $f"
    else
        echo "  ❌ $f"
        FAIL=1
    fi
done
[ $FAIL -ne 0 ] && echo "❌ 语法错误，先修" && exit 1

# ── 2. 同步到 SMB ──
echo ""
echo "═══ 2. 同步到 SMB ═══"
bash sync.sh

# ── 3. diff 确认 ──
echo ""
echo "═══ 3. diff 检查 ═══"
for f in ui_external.py core.py config.py pricing.py adapters/wuhenai_v2.py adapters/__init__.py; do
    if [ -f "$f" ] && [ -f "$SMB/$f" ]; then
        if diff "$f" "$SMB/$f" > /dev/null 2>&1; then
            echo "  ✅ $f"
        else
            echo "  ❌ $f (本地≠SMB)"
        fi
    fi
done

# ── 4. UI 日志 ──
echo ""
echo "═══ 4. UI 日志（最近 10 行）═══"
LOG=$(find /var/folders -name "ai_subtitle_ui.log" -mmin -30 2>/dev/null | head -1)
if [ -n "$LOG" ]; then
    tail -10 "$LOG" 2>/dev/null | grep -v "^===" || echo "  （空或只有启动行）"
else
    echo "  （无最近日志）"
fi

# ── 5. 达芬奇状态 ──
echo ""
echo "═══ 5. 达芬奇状态 ═══"
python3 -c "
import sys, os
os.environ['RESOLVE_SCRIPT_API'] = '/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting'
sys.path.append('/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules')
import DaVinciResolveScript as bmd
r = bmd.scriptapp('Resolve')
if not r:
    print('  Resolve 未启动')
    exit()
print(f'  版本: {r.GetVersionString()}')
p = r.GetProjectManager().GetCurrentProject()
if not p:
    print('  项目: 未打开')
    exit()
tl = p.GetCurrentTimeline()
print(f'  项目: {p.GetName()}')
print(f'  时间线: {tl.GetName() if tl else \"无\"}')
io = tl.GetMarkInOut() if tl else {}
if io and io.get('video',{}).get('in',0) > 0:
    vi = io['video']
    print(f'  IO: {vi[\"in\"]}→{vi[\"out\"]} ({(vi[\"out\"]-vi[\"in\"])} 帧)')
else:
    print('  IO: 未设置')
if tl:
    orange = 0
    for t in range(1, tl.GetTrackCount('video')+1):
        items = tl.GetItemListInTrack('video', t) or []
        for item in items:
            if io and io.get('video',{}).get('in',0) <= item.GetStart() <= io['video']['out']:
                if item.GetClipColor() == 'Orange' and item.GetClipEnabled():
                    orange += 1
    print(f'  IO内橙色片段: {orange} 个')
" 2>&1
echo ""
echo "✅ dev.sh 完成"
