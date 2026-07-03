# TODO — 达芬奇插件工坊

> 2026-07-04

## 🔴 高优

- SMB 文件夹拖入性能：`_process_paths` 逐个 `os.stat` + `os.path.isfile` + `open().read(4KB)` 50 文件 ≈ 150 次网络往返。异步分批或指纹缓存可减 I/O
- 图片缩略图生成同步阻塞 UI：PIL `Image.open` 在 SMB 上是全文件读取，需后台线程化或延迟加载

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
