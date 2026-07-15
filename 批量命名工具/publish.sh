#!/bin/bash
# 批量命名工具 — 发布脚本 v3.7.15+
# 用法:
#   bash publish.sh quick     # 快修：splice → 注入桌面 app + py → 开箱即测（~5s）
#   bash publish.sh delta     # 增量：build → 验证 → version.json → push CDN（~30s）
#   bash publish.sh app       # 应用：PyInstaller → 桌面 app + DMG（~2min）
#   bash publish.sh all       # 全量：app + delta + DMG + push（~3min）
#   bash publish.sh patch     # 补丁：仅注入桌面自测补丁（~1s）
#   （无参数 = quick）
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WS="$(dirname "$SCRIPT_DIR")"
MODE="${1:-quick}"
VERSION=$(head -1 "$SCRIPT_DIR/app_table.js" | grep -o "3\.[0-9]*\.[0-9]*" || echo "??")
APP_SRC="$SCRIPT_DIR/dist/批量命名工具.app"
DESKTOP_APP="$HOME/Desktop/批量命名工具.app"
DESKTOP_HTML="$DESKTOP_APP/Contents/Resources/renamer_table.html"
DESKTOP_PY="$DESKTOP_APP/Contents/Resources/shared/app_core.py"

_ok()  { echo "  ✅ $1"; }
_warn(){ echo "  ⚠️  $1"; }
_fail(){ echo "  ❌ $1"; exit 1; }

# ═══════════════════════════════════════
# 预检（所有模式共用）
# ═══════════════════════════════════════
_precheck() {
  [ -d "$DESKTOP_APP" ] || _fail "桌面 app 不存在：$DESKTOP_APP（先跑 bash publish.sh app）"
  python3 -c "import py_compile; py_compile.compile('$WS/shared/app_core.py', doraise=True)" 2>&1 \
    || _fail "app_core.py 编译失败"
  node --check "$SCRIPT_DIR/app_table.js" 2>&1 \
    || _fail "app_table.js 语法错误"
  _ok "编译检查 v$VERSION"
}

# ═══════════════════════════════════════
_patch_desktop() {
  local use_workspace="${1:-0}"  # 0=用 dist（刚构建完）, 1=用 workspace（quick 模式）
  # 1) splice + 注入 HTML
  cd "$SCRIPT_DIR"
  python3 _splice.py table > /dev/null 2>&1 || _fail "_splice.py 失败"
  [ -s _build/renamer_table.html ] || _fail "splice 后的 HTML 为空"
  cp _build/renamer_table.html "$DESKTOP_HTML"
  # 2) 注入 app_core.py
  if [ "$use_workspace" = "1" ]; then
    cp "$WS/shared/app_core.py" "$DESKTOP_PY"
  elif [ -f "$APP_SRC/Contents/Resources/shared/app_core.py" ]; then
    cp "$APP_SRC/Contents/Resources/shared/app_core.py" "$DESKTOP_PY"
  else
    cp "$WS/shared/app_core.py" "$DESKTOP_PY"
  fi
  # 3) 自测补丁
  python3 -c "
html=open('$DESKTOP_HTML',encoding='utf-8').read()
html=html.replace('setTimeout(() => { if(!window.pywebview) _runSelfTest(); }, 2000);', '// self-test skipped (pywebview)')
open('$DESKTOP_HTML','w',encoding='utf-8').write(html)
"
  _ok "桌面已注入 v$VERSION"
}

# ═══════════════════════════════════════
_build_full() {
  cd "$SCRIPT_DIR"
  bash build.sh table
  cd "$WS"
}

# ═══════════════════════════════════════
_verify_delta() {
  DELTA_VER=$(unzip -p batch_renamer_update.zip version.txt)
  [ "$DELTA_VER" = "$VERSION" ] || _fail "delta version.txt=$DELTA_VER ≠ $VERSION"
  _ok "delta version.txt=$DELTA_VER"
}

# ═══════════════════════════════════════
_update_version_json() {
  SHA=$(shasum -a 256 batch_renamer_update.zip | cut -d' ' -f1)
  python3 -c "
import json
d=json.load(open('$WS/version.json'))
# Mac 是唯一源 — Win 自动同步所有字段
d['batch_renamer_mac']['version']='$VERSION'
d['batch_renamer_mac']['sha256']='$SHA'
for k in ['version','sha256','urls','notes','history']:
    d['batch_renamer_win'][k] = d['batch_renamer_mac'][k]
json.dump(d,open('$WS/version.json','w'),indent=2,ensure_ascii=False)
"
  _ok "version.json → v$VERSION SHA=$SHA (Mac→Win synced)"
}

# ═══════════════════════════════════════
_build_dmg() {
  [ -d "$APP_SRC" ] || _fail "dist/ 不存在，先跑 bash publish.sh app"
  codesign --force --deep --sign - "$APP_SRC" 2>/dev/null
  DMG_TMP="$(mktemp -d)"
  cat > "$DMG_TMP/首次打开请看这里.txt" << 'TXT'
如果双击 app 弹出"无法打开"或"已损坏"：
  系统设置 → 隐私与安全性 → 滑到最底部
  → 找到"批量命名工具" → 点"仍要打开"
  → 输电脑密码确认
只做一次，以后直接双击 app 即可。
TXT
  cp -R "$APP_SRC" "$DMG_TMP/"
  ln -s /Applications "$DMG_TMP/Applications" 2>/dev/null
  DMG_OUT="$HOME/Desktop/批量命名工具_v${VERSION}.dmg"
  rm -f "$DMG_OUT"
  hdiutil create -volname "批量命名工具" -srcfolder "$DMG_TMP" -ov -format UDZO "$DMG_OUT" 2>&1 | grep created
  rm -rf "$DMG_TMP"
  _ok "DMG: $DMG_OUT"
}

# ═══════════════════════════════════════
_push_cdn() {
  if ! git -C "$WS" diff --quiet; then
    git -C "$WS" add batch_renamer_update.zip version.json
    git -C "$WS" commit -m "v$VERSION — release" --no-verify
  fi
  git -C "$WS" push origin main 2>&1 | tail -1
  _ok "已推送到 GitHub"

  # CDN 验证
  sleep 3
  CDN_VER=$(curl -sf --max-time 10 "https://raw.githubusercontent.com/cgjpaladin/davinci-plugins/main/version.json" 2>/dev/null \
    | python3 -c "import json,sys;print(json.load(sys.stdin)['batch_renamer_mac']['version'])" 2>/dev/null || echo "?")
  curl -sf --max-time 10 -o /tmp/_cdn_delta.zip \
    "https://raw.githubusercontent.com/cgjpaladin/davinci-plugins/main/batch_renamer_update.zip" 2>/dev/null
  CDN_DELTA_VER=$(unzip -p /tmp/_cdn_delta.zip version.txt 2>/dev/null || echo "?"); rm -f /tmp/_cdn_delta.zip
  [ "$CDN_VER" = "$VERSION" ] && _ok "CDN version.json=v$CDN_VER" || _warn "CDN version.json=$CDN_VER（期望 $VERSION，可能缓存滞后）"
  [ "$CDN_DELTA_VER" = "$VERSION" ] && _ok "CDN delta.txt=v$CDN_DELTA_VER" || _warn "CDN delta.txt=$CDN_DELTA_VER（期望 $VERSION，可能缓存滞后）"
}

# ═══════════════════════════════════════
# 主流程
# ═══════════════════════════════════════
echo "📦 v$VERSION — $MODE"
_precheck

case "$MODE" in
  quick)
    _patch_desktop 1
    echo ""
    echo "✅ 桌面已更新（源码直注），双击 ~/Desktop/批量命名工具.app 测试"
    ;;
  patch)
    python3 -c "
html=open('$DESKTOP_HTML',encoding='utf-8').read()
html=html.replace('setTimeout(() => { if(!window.pywebview) _runSelfTest(); }, 2000);', '// self-test skipped (pywebview)')
open('$DESKTOP_HTML','w',encoding='utf-8').write(html)
" && _ok "自测补丁已注入"
    ;;
  delta)
    _build_full
    _verify_delta
    _update_version_json
    _push_cdn
    _patch_desktop
    echo ""
    echo "✅ Delta 已推送，桌面已同步"
    echo "   CDN: batch_renamer_update.zip → Mac/Win 皆可用"
    ;;
  app)
    _build_full
    _patch_desktop
    _build_dmg
    echo ""
    echo "✅ App + DMG 就绪"
    echo "   app : $DESKTOP_APP"
    echo "   DMG : ~/Desktop/批量命名工具_v${VERSION}.dmg"
    ;;
  all)
    _build_full
    _verify_delta
    _update_version_json
    _patch_desktop
    _build_dmg
    _push_cdn
    echo ""
    echo "════════════════════════════════════"
    echo "  v$VERSION 全量发布完成"
    echo "════════════════════════════════════"
    echo "  app : $DESKTOP_APP"
    echo "  DMG : ~/Desktop/批量命名工具_v${VERSION}.dmg"
    echo "  Δ   : batch_renamer_update.zip（CDN）"
    ;;
  *)
    echo "用法: bash publish.sh {quick|patch|delta|app|all}"
    exit 1
    ;;
esac
