# 创壹特供版 · Windows 打包指南

## 环境准备
1. 安装 **Python 3.11 或 3.12**（webview 不支持 ≥3.13）
2. 安装依赖：`pip install pywebview bottle pillow pyinstaller`
3. 下载 ffmpeg.exe 放到项目目录里

## 文件结构
把下面两个目录保持层级关系拷过去：
```
某个文件夹/
├── shared/              ← 共享模块
└── 批量命名工具_创壹特供版/
    ├── build_win.bat     ← 双击运行
    ├── renamer_web.py
    ├── app.js / app.css / renamer_web.html
    ├── _splice.py
    ├── app_icon.ico
    └── ffmpeg.exe        ← 放这里
```

## 打包
双击 `build_win.bat`，生成的 exe 会出现在桌面。
