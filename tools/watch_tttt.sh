#!/bin/bash
# watch_tttt.sh — 实时监控 TTTTT 的插件日志
# 用法: bash tools/watch_tttt.sh
# Ctrl+C 退出

echo "🔍 实时监控 TTTTT ⏐ Ctrl+C 退出"
echo ""

ssh qingdao "tail -200 -f '/Users/ttttt/.workbuddy/logs/交付自检工具/ui_TTTTTdeMacBook-Pro.local_2026-06-01.log'" 2>/dev/null
