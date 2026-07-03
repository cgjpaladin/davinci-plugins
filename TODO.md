# TODO — 达芬奇插件工坊

> 2026-07-04 | 按难度排序，从 5 分钟到架构级

## 代码修复（由浅入深）

| # | 条目 | 难度 | 怎么修 |
|---|------|:--:|------|
| 1 | ✅ **拖拽 ghost 残留** | `_finishDrag` 设 `_dragIdx=-1` + blur/Escape 监听 → 防 double-run 损数据 |
| 2 | ✅ **图片格式扩充** | PIL 实测：gif/webp/tga/psd 可开。`SUPPORTED_EXT` + `mime_map` ×2 + `PIL._webp` |
| 3 | **归档中断保护** | 20 分钟 | `shutil.copy2(src, dst/name.tmp)` → 全部完成 → `os.rename(.tmp, name)`。下次归档前清残`.tmp` |
| 4 | **列表删除 undo** | 30 分钟 | `removeSelected` push `{action:'remove', rows:[…], indices:[…]}` 到 undo 栈，Ctrl+Z 还原 |

## 部署/架构

| # | 条目 | 难度 | 怎么修 |
|---|------|:--:|------|
| 5 | **DMG 打包** | 脚本 | `macos-dmg-dist` skill — codesign 重签 + quarantine 清除 + DMG 创建。全公司 20 台分发 |
| 6 | **Windows 构建** | 脚本 | 跑 `build_win.bat`，产出 `batch_renamer_win.zip` |
| 7 | **发布链验证** | 脚本 | `build.sh → DMG(5) → Win构建(6) → publish_release.sh → version.json → CDN` |
| 8 | **SMB 拖入性能** | 架构 | `_process_paths` 逐个 stat 150 次网络往返 + `generate_thumbnails` PIL 全文件读 → 后台线程/分批/懒加载 |

## 低优

| # | 条目 | 说明 |
|---|------|------|
| 9 | CDN 更新速度 | jsdelivr 国内偏慢，需加 OSS 链路 |
| 10 | FC 冷启动保活 | 已有子进程兜底 |
