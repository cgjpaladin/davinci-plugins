# TODO — 达芬奇插件工坊

> 2026-07-06

## 交付自检工具

| # | 条目 | 难度 | 说明 |
|:--:|------|:--:|------|
| 1 | CDN 更新速度 | 低优 | jsdelivr 国内偏慢，需加 OSS 链路 |
| 2 | FC 冷启动保活 | 低优 | 已有子进程兜底，非紧急 |

## 批量命名工具

| # | 条目 | 难度 | 说明 |
|:--:|------|:--:|------|
| 3 | ✅ 归档中断保护 | 两阶段——Phase 1 全写 `.tmp` → Phase 2 批量 `shutil.move`。崩溃只留 `.tmp`，下次启动清理 |
| 4 | ✅ 全部 undo | `_localUndos` 统一三种 JS 操作（remove/edit/methodChange）+ `_undoSnap` + Python undo。Ctrl+Z 全覆盖 |
| 5 | DMG 打包 | 脚本 | `macos-dmg-dist` skill |
| 6 | Windows 构建 | 脚本 | 跑 `build_win.bat` |
| 7 | 发布链验证 | 脚本 | 5+6 → publish_release → CDN |
| 8 | SMB 拖入性能 | 架构 | 批量 stat + PIL 全文件读 → 异步 |
| 9 | 产品页优化 | 低优 | 另议 |
| 10 | B站演示视频 | 低优 | 等裁缝老师 |
