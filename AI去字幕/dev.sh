#!/bin/bash
# dev.sh — 改完代码一键验证（本地跑，不用达芬奇菜单）
# 用法: ./dev.sh
set -e

# ── 0. pre-commit 检查 ──
echo "═══ 0. pre-commit ═══"
bash ../tools/pre-commit.sh

# ── 1. 语法检查 ──
echo ""
echo "═══ 1. 语法编译 ═══"
SMB="/Volumes/MYJC/06_Software/达芬奇脚本/AI去字幕"
FAIL=0
for f in ui_external.py stable_ui.py ui_widgets.py ui_pipeline.py core.py config.py pricing.py remove_subtitle.py logger.py ops_logger.py subtitle_state.py adapters/__init__.py adapters/wuhenai_v2.py adapters/ghostcut.py; do
    if python3 -m py_compile "$f" 2>/dev/null; then
        echo "  ✅ $f"
    else
        echo "  ❌ $f"
        FAIL=1
    fi
done
[ $FAIL -ne 0 ] && echo "❌ 语法错误，先修" && exit 1

# ── 2. pre_flight 检查（轻量 → 智能升级）──
echo ""
echo "═══ 2. pre_flight ═══"

# 检测 core.py 是否有改动（本地 vs SMB）
CORE_CHANGED=0
if [ -f "$SMB/core.py" ] && ! diff core.py "$SMB/core.py" > /dev/null 2>&1; then
    CORE_CHANGED=1
elif [ ! -f "$SMB/core.py" ]; then
    CORE_CHANGED=1  # 首次部署也算改动
fi

# 2a. 轻量检查（永远跑，零 API 消耗）
echo "  轻量: 导入链..."
python3 -c "
import sys, os
sys.path.insert(0, '.')
for m in ['config','pricing','logger','subtitle_state','ops_logger','adapters']:
    __import__(m)
    print(f'    ✅ {m}')
" 2>&1 || { echo "  ❌ 导入链失败，先修"; exit 1; }

# 2b. 如果 core.py 有改动 → 自动升级为完整 pre_flight
if [ $CORE_CHANGED -eq 1 ]; then
    echo ""
    echo "  ⚠️  core.py 有改动 → 自动升级完整 pre_flight（含余额查询）"
    echo "  ─────────────────────────────────"
    if [ -f "$SMB/tests/pre_flight.py" ]; then
        python3 "$SMB/tests/pre_flight.py" || { echo ""; echo "❌ pre_flight 未通过，先修再部署"; exit 1; }
    else
        echo "  ⚠️  SMB 上无 tests/pre_flight.py，跳过（需先 sync）"
    fi
else
    echo "  ✅ core.py 无变动，跳过完整 pre_flight"
    echo "  💡 如果需要强制完整检查: python3 tests/pre_flight.py"
fi

# ── 3. 同步到 SMB ──
echo ""
echo "═══ 3. 同步到 SMB ═══"
bash sync.sh

# ── 4. 灰度状态 ──
echo ""
echo "═══ 4. 灰度发布 ═══"
GRAY_CFG="$SMB/gray.json"
if [ -f "$GRAY_CFG" ]; then
    python3 -c "
import json, os
cfg = json.load(open('$GRAY_CFG'))
targets = cfg.get('targets', [])
print(f'  灰度版本: {cfg[\"version\"]}')
print(f'  灰度机器: {targets if targets else \"(无 — 全员稳定版)\"}')
if targets:
    gray_dir = os.path.join(os.path.dirname('$SMB'), cfg['gray_dir'])
    print(f'  灰度目录: {\"✅ 存在\" if os.path.isdir(gray_dir) else \"❌ 不存在: \" + gray_dir}')
" 2>/dev/null
else
    echo "  gray.json 不存在"
fi

# ── 5. diff 确认 ──
echo ""
echo "═══ 5. diff 检查 ═══"
for f in ui_external.py stable_ui.py ui_widgets.py ui_pipeline.py core.py config.py pricing.py adapters/wuhenai_v2.py adapters/ghostcut.py adapters/__init__.py; do
    if [ -f "$f" ] && [ -f "$SMB/$f" ]; then
        if diff "$f" "$SMB/$f" > /dev/null 2>&1; then
            echo "  ✅ $f"
        else
            echo "  ❌ $f (本地≠SMB)"
        fi
    fi
done

# ── 6. UI 日志 ──
echo ""
echo "═══ 6. UI 日志（最近 10 行）═══"
LOG=$(find /var/folders -name "ai_subtitle_ui.log" -mmin -30 2>/dev/null | head -1)
if [ -n "$LOG" ]; then
    tail -10 "$LOG" 2>/dev/null | grep -v "^===" || echo "  （空或只有启动行）"
else
    echo "  （无最近日志）"
fi

# ── 7. 达芬奇状态 ──
echo ""
echo "═══ 7. 达芬奇状态 ═══"
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
