# TODO — 达芬奇插件工坊

> 2026-07-04

## 🔴 高优

- 🔴 **Windows 构建**：`build_win.bat` 未跑，`batch_renamer_win.zip` 缺失——当前只有 Mac 用户能收到更新
- 🔴 **发布验证**：跑一遍完整发布链 `build.sh → publish_release.sh --product batch_renamer` 确认 mac zip + version.json + CDN purge 全线通
- SMB 文件夹拖入性能：`_process_paths` 逐个 `os.stat` 150 次网络往返，需异步分批
- 图片缩略图同步阻塞 UI：PIL `Image.open` 在 SMB 上是全文件读取，需后台线程化

## 🟡 中优

- Windows 构建兼容测试（本轮全在 macOS，`build_win.bat` 未跑）
- 拖拽后窗口失焦 → ghost 行残留（加 `visibilitychange` / `blur` 清理）
- 产品页优化（另议）
- 更新下载速度优化（加国内 CDN 链路）

## 💭 低优

- 列表删除加入 undo 栈（目前只撤销文件操作）
- 归档中途退出保护（无事务，可能留半份文件）
- B站演示视频（等裁缝老师）
- FC 冷启动保活机制（已有子进程兜底）
- gif/webp 图片格式支持（创壹版已有 MEDIA_EXT 扩展）
