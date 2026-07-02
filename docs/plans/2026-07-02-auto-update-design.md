# 批量命名工具 — 自动更新设计（v2）

> 日期: 2026-07-02 | 用户群: 外部用户（石家庄及各城市分公司）

## 用户流程

```
启动 → 后台查版本（静默，5s 后）
  ↓ 有新版本
状态栏 🟢 v3.6.3 可用 [点击更新]
  ↓ 点击
弹框：版本对比 + 更新日志 + [取消] [下载更新]
  ↓ 下载中
进度条 ⬇ [████░░░░░░░░░░░░░░░░] 45% 24.8/55MB
  ↓ 完成
按钮变 [立即重启]    ← 用户自己决定何时重启
  ↓ 点击
→ 写更新脚本 → detach 起脚本 → app 退出
→ 脚本 sleep 2 → 替换旧文件 → 启动新版
→ 新版打开，用户看到新版
```

## 文件清单

| 文件 | 操作 | 内容 |
|------|:--:|------|
| `version.json` | 改 | 加 `batch_renamer` 条目 |
| `shared/updater.py` | 改 | 加 `download_update()` 含多链路回退 + 进度回调 + SHA256 |
| `shared/update_config.py` | 改 | 加 `RENAMER_UPDATE_FILENAME` |
| `批量命名工具/renamer_web.py` | 改 | 启动查更新 + API + 脚本生成 + detach 起脚本 |
| `批量命名工具/app_table.js` | 改 | UI 通知/进度/对话框 |
| `批量命名工具/app_table.css` | 改 | 状态栏更新样式 + 进度条 |
| `批量命名工具/renamer_table.html` | 改 | 状态栏 `<span id="updateStatus">` |
| `批量命名工具/build.sh` | 改 | 产出 `renamer_update.zip` + SHA256 |
| `批量命名工具/build_win.bat` | 改 | 同上 Windows 版 |

## 任务列表

### T1 — version.json 加条目

```json
"batch_renamer": {
  "version": "3.6.2",
  "urls": [...],
  "sha256": null,
  "notes": "## v3.6.2\n\n...",
  "history": [...]
}
```

### T2 — updater.py 加 download_update()

```python
def download_update(product, save_dir, progress_callback=None):
    """下载更新包到 save_dir/renamer_update.zip。
    progress_callback(downloaded_bytes, total_bytes)
    返回 (save_path, sha256_hex)
    """
```

- 多链路回退同 `check()`
- 每条链路超时 60s
- 文件 < 1000 字节视为无效
- SHA256 校验引用 version.json

### T3 — renamer_web.py 更新入口

启动:
```python
import shared.updater as updater
updater.check_async("batch_renamer", APP_VERSION,
    on_update_found=lambda ver, url, notes: _window.evaluate_js(f"onUpdateFound('{ver}', `{notes}`)"))
```

API:
- `check_update()` → `{update_available, latest, notes}`
- `trigger_update()` → 下载zip → 解压 → 写脚本 → `return {"ready": True}`
- `apply_update()` → 起脚本 detach → `sys.exit(0)`
- `get_update_progress()` → `{downloaded, total, done}`

脚本模板（Mac）:
```bash
#!/bin/bash
sleep 2
rm -rf "旧.app"
mv "/tmp/renamer_update/新.app" "旧.app"
open "旧.app"
rm -- "$0"
```

脚本模板（Win）:
```cmd
@echo off
timeout /t 2 /nobreak >nul
taskkill /f /im "旧.exe" 2>nul
move /y "新.exe" "旧.exe"
start "" "旧.exe"
del "%~f0"
```

管理员权限（Mac，仅 `/Applications`）:
```python
osascript -e 'do shell script "rm -rf ... && mv ... && open ..." with administrator privileges'
```

### T4 — app_table.js UI

- `onUpdateFound(ver, notes)` → 状态栏变 `🟢 vX 可用 [更新]`
- 点击 `[更新]` → `showUpdateDialog(ver, notes)` 弹框
- 弹框: 标题 + 版本对比 + 更新日志 + [取消] [下载更新]
- 下载中: 按钮变进度条 `⬇ [████░░░░] 45%`
- 完成: 按钮变 `[立即重启]` + 说明文字"准备好后点击重启"
- 点击立即重启: `call('apply_update')` → 窗口关闭

### T5 — CSS 样式

- `#updateStatus` 状态栏标签
- `.update-dialog` 对话框
- `.update-progress` 进度条

### T6 — renamer_table.html

- 状态栏加 `<span id="updateStatus">v</span>`
- JS `init()` 时注入版本号

### T7 — build.sh 更新包产出

```bash
cd dist
zip -rq ../renamer_update.zip "批量命名工具-表格版.app"
shasum -a 256 renamer_update.zip > renamer_update.sha256
```

### T8 — build_win.bat 同上

```cmd
powershell Compress-Archive -Path "dist\*.exe" -DestinationPath "renamer_update.zip"
certutil -hashfile renamer_update.zip SHA256 > renamer_update.sha256
```

## 边界条件全表

| 场景 | 处理 |
|------|------|
| 网络不可达 | 静默，不弹任何东西 |
| 版本号含 `-dev` | 不检查更新 |
| 下载中用户关闭 app | 不碍事，temp 文件下次启动清理 |
| 下载中断（网络切换） | 下次启动重试，不弹错误 |
| SHA256 校验失败 | 删除下载文件，静默，下次重试 |
| 下载文件 < 1000 字节 | 视为无效链路，试下一条 |
| app 在 `/Applications/` | osascript 弹管理员授权框 |
| app 在桌面/Downloads | 直接 bash 替换，不弹框 |
| app 在只读位置（DMG 里） | toast "请先将 App 拖入 Applications 再更新" |
| 更新脚本执行失败 | 旧版还在原位置，下次启动重新查 |
| 用户点了更新后把弹框关了 | 下载继续后台跑，完成后再打开 app 时识别到已下载 |
| jsDelivr 超 50MB | 自动 fallback 到 ghproxy / GitHub 直连 |
| Windows 用户没有管理员 | 桌面/Downloads 路径不需要，否则弹 UAC |
| 更新脚本被 macOS Gatekeeper 拦截 | 脚本是系统生成的不带 quarantine 标记，不存在 |
| 同时有 Mac 和 Win 用户 | version.json 用同一套，下载 URL 区分平台 |
