# 创壹特供版 · Windows 打包指南 v1.1

## 环境准备
1. 安装 **Python 3.11**（webview 不支持 ≥3.12）
2. 安装依赖：`pip install pywebview bottle pillow pyinstaller openpyxl`
3. 下载 ffmpeg.exe，放到 `批量命名工具_创壹特供版/` 目录

## 文件结构
解压 zip 后保持层级不变：
```
某个文件夹/
└── 批量命名工具_创壹特供版/
    ├── build_win.bat           ← 双击运行
    ├── renamer_web.py
    ├── naming_createone.py     ← 创壹专用命名规则
    ├── naming_checks.py        ← 文件质量检测
    ├── app.js / app.css / renamer_web.html
    ├── _splice.py
    ├── version_info.txt        ← exe 元数据（splice 自动生成，改 APP_VERSION 即可）
    ├── app_icon.ico
    └── ffmpeg.exe              ← 放这里
```

## 打包
双击 `build_win.bat`，桌面生成 `批量命名工具-创壹特供版-v1.1.exe`（单文件）。

## 360 误报处理
PyInstaller 打包的程序 360 会报毒（HEUR/QVM 启发式误报）。已做最大努力：
- `--version-file` 写入公司名/产品名
- `--clean` 清除构建缓存
- `--strip` 去除调试符号
- `--noupx` 禁用 UPX 压缩
- `--onefile` 单文件输出

**如果还拦**，让用户：右键 360 托盘 → 设置 → 文件白名单 → 添加 exe 所在文件夹。

## 测试
打包完成后，拖几个 mp4 和 png 进去验证：
- 视频自动判定为 AIVID，描述列显示"视频无需描述"
- 图片自动判定为 AIPIC，可填描述
- SH 列双击弹出多镜号 [+][-] 编辑器
- 选中多行 → 编辑一列 → 全部联动
- 重命名后文件保留在列表中，可继续改继续重命名
- Ctrl+Z 撤销上一步重命名
