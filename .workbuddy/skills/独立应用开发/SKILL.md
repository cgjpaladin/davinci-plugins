---
name: pywebview-dev
description: pywebview 独立桌面应用开发模板——Python 后端 + HTML/JS 前端 + bottle HTTP + PyInstaller 打包，跨平台 macOS / Windows。当裁缝老师要新建独立桌面应用时自动激活。
tools: Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch
model: inherit
agent_created: true
---

# pywebview 桌面应用开发

触发词：新建应用、桌面工具、打包 .app、打包 .exe、pywebview、独立应用、EXE、webview

HTML/CSS 做 UI + Python 做后端。达芬奇插件工坊的独立工具（批量命名工具、交付自检工具等）用此方案。

## 技术栈

- Python 3.11-3.12 + pywebview + bottle（webview Windows 端不支持 ≥3.13）
- HTML / CSS / JS 前端
- PyInstaller 打包（macOS .app / Windows .exe）
- WKWebView (macOS) / Edge WebView2 (Windows)

## 项目结构模板

```
项目名/
├── app.css          ← 所有样式
├── app.js           ← 所有 JS 逻辑
├── app.html         ← HTML 骨架（含 CSS/JS 占位符）
├── app.py           ← Python 后端 + API class + bottle + webview 启动
├── _splice.py       ← 拼接 CSS+JS+HTML → _build/
├── build.sh         ← 自动 commit → node check → 拼合 → PyInstaller → 桌面
├── build_win.bat    ← Windows 打包
├── app_icon.icns    ← macOS 图标
├── app_icon.ico     ← Windows 图标
└── shared/          ← 共用 Python 模块
```

## 外部文档

| 文档 | URL |
|------|-----|
| 官方指南 | https://pywebview.flowrl.com/guide |
| API 参考 | https://pywebview.flowrl.com/api |
| JS 桥接 | https://pywebview.flowrl.com/guide/interdomain |
| 打包指南 | https://pywebview.flowrl.com/guide/freezing |
| 拖放示例 | https://pywebview.flowrl.com/examples/drag_drop |
| py2app 配置 | https://github.com/r0x0r/pywebview/blob/master/examples/py2app_setup.py |

## create_window 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `title` | — | 窗口标题 |
| `url` | None | URL 或本地路径 |
| `html` | None | 直接 HTML 内容 |
| `js_api` | None | 暴露给 JS 的 Python 类实例 |
| `width/height` | 800/600 | 窗口尺寸 |
| `min_size` | (200,100) | 最小尺寸 |
| `background_color` | `#FFFFFF` | 页面加载前背景色（**设暗色防白闪**）|
| `text_select` | False | **启用以支持文本输入/选择** |
| `frameless` | False | 无边框 |
| `on_top` | False | 窗口置顶 |
| `confirm_close` | False | 关闭前确认 |

## JS↔Python 桥接

### JS 调用 Python

```javascript
// 轮询等待桥接就绪（pywebviewready 在 bottle HTTP 模式不可靠）
setInterval(() => {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.myMethod(args).then(result => {...});
  }
}, 300);
```

- `js_api` 传入的类所有公开方法自动暴露为 `pywebview.api.xxx()`
- 返回 Promise，Python 异常 reject 成 JS Error
- 运行在单独线程，**非线程安全**

### Python 调用 JS

```python
window.evaluate_js("document.title")      # 同步返回值
window.run_js("code")                     # 无返回值
```

### 拖放文件

macOS 和 Windows 都支持。**必须用 `pywebviewFullPath`**：

```javascript
document.addEventListener('drop', async e => {
  e.preventDefault();
  for (const f of e.dataTransfer.files) {
    const path = f.pywebviewFullPath;  // ← pywebview 注入的完整路径
    // f.path 和 f.name 在 macOS WKWebView 不可靠
  }
});
```

## build.sh 模板

```bash
#!/bin/bash
set -e; cd "$(dirname "$0")"

git diff --stat -- . 2>/dev/null || true
git diff --quiet && git diff --cached --quiet || git add -A && git commit -m "build: $(date '+%H:%M')"

node --check app.js || { echo "❌ JS 语法错误"; exit 1; }
[ -f test_smoke.py ] && python3 test_smoke.py || true

rm -rf build dist *.spec _build; mkdir -p _build
python3 _splice.py      # 拼接 → _build/app.html

# 用系统 Python（有 PyInstaller，无沙箱）
SYSPY=/path/to/system/python3
$SYSPY -m PyInstaller \
  --onedir --windowed --name "应用名" --icon app_icon.icns \
  --add-data "_build/app.html:." --add-data "../shared:shared" \
  --collect-data webview --collect-data bottle \
  --hidden-import webview --hidden-import bottle \
  --noconfirm app.py

# macOS 用 ditto 替换桌面 app（避免 cp -R 嵌套 + SIP 权限问题）
rm -rf ~/Desktop/应用名.app
ditto dist/应用名.app ~/Desktop/应用名.app

# 验证 CSS/JS 嵌入
BUNDLE=~/Desktop/应用名.app/Contents/Resources/app.html
if python3 -c "h=open('$BUNDLE').read();assert ':root' in h and 'function' in h"; then
  echo "✅ CSS+JS 验证通过"
else
  echo "❌ 打包异常：CSS/JS 未嵌入"; exit 1
fi
```

## app.py 模板

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class AppAPI:
    """所有 public 方法自动暴露给 JS 作为 pywebview.api.xxx()"""
    def echo(self, msg):
        return {"received": msg}

if __name__ == "__main__":
    import threading, socket, webview, time
    from bottle import route, run, static_file

    BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

    @route('/')
    def index():
        return static_file('app.html', root=BASE_DIR)

    # 随机端口 ← 避免冲突
    sock = socket.socket(); sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]; sock.close()
    threading.Thread(target=lambda: run(host='127.0.0.1', port=port, quiet=True), daemon=True).start()

    # 等服务器就绪
    import urllib.request
    for _ in range(20):
        try: urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=0.5); break
        except: time.sleep(0.1)

    api = AppAPI()
    webview.create_window('应用名', f'http://127.0.0.1:{port}', js_api=api,
                          width=1100, height=720, min_size=(800,500),
                          background_color='#151515', text_select=True)
    webview.start()
```

## JS 模板

```javascript
// 全局错误 → toast
window.onerror=function(m,s,l,c,e){call('debug_log','JS错误: '+m+' @ '+s+':'+l);return false};

function call(m,...a){
  try{return window.pywebview?.api[m](...a)||mock(m,...a)}
  catch(e){toast('API错误: '+m);return null}
}

function mock(m,...a){
  return new Promise(r=>{
    switch(m){
      case'get_config':r({version:'1.0'});break;
      default:r({});
    }
  });
}

function toast(m){/* 轻量吐司实现 */}

// ═══ init — 轮询等待 pywebview 桥接 ═══
function _tryStart(){
  if(window.pywebview?.api){
    window.pywebview.api.echo('hello').then(init).catch(init);
  }
}
setInterval(_tryStart,300);

async function init(){
  const cfg=await call('get_config');
  // 用 cfg 初始化 UI...
}
```

## 常见坑

### macOS WKWebView 沙箱
`file://` URL 无法注入 JS 桥接。**必须用 bottle HTTP 服务器**。

### JS 语法错误 = 全脚本沉默
`const x; ... const x;` → 整个 `<script>` 不执行
→ `node --check app.js` 必须进 build.sh

### 打包后日志路径
不能写 `.app` 包内目录。用 `/tmp/` 或 `~/Library/Logs/`。

### PyInstaller --add-data
`--add-data "src:dst"` 中 dst 是 target **目录**，不是文件名。
要重命名 → 源文件名先改好。Windows 分隔符用 `;`。
打包后 `sys._MEIPASS` 指向 `Contents/Resources/`，用此路径读写资源文件。

### select 的 readonly 无效
`el.readOnly` 只对 `<input>` 有效。`<select>` 要用 `el.disabled`。

### 浏览器预览用 mock API
`call()` 检测 `window.pywebview?.api`，不存在走 mock。
→ mock 的 get_config 必须和 Python 同步。

### 桥接就绪时机
`window.pywebviewready` 在 bottle HTTP 模式下可能不触发。**用轮询**检测。

### 文件对话框
用 `window.create_file_dialog()` 而非 JS `<input type="file">`。

### Windows 适配
- ffmpeg 路径不能写死 `/opt/homebrew/bin/`；打包用 `--add-binary ffmpeg.exe:.`
- Python 必须 3.11-3.12（webview 不支持 ≥3.13）
- PyInstaller 加 `--hidden-import webview.platforms.edgechromium`（Win10+ 默认后端）
- Edge WebView2 在 Win10 20H2+ 和 Win11 系统自带（不打包浏览器引擎 → .exe 约 15MB）。旧版 Win10（~15% 存量）需先安装 WebView2 Runtime。

### Windows 图标缓存
exe 换图标后 Windows 可能显示旧图标——缓存分两层：
- `%LocalAppData%\Microsoft\Windows\Explorer\iconcache_*.db`（真正生效）
- `IconCache.db`（Win7 遗留，删了没用）

修复：`taskkill /f /im explorer.exe` → 删 `iconcache_*` → `start explorer.exe`。
终极技巧：部署时 `copy → _tmp.exe → move → 目标名`，新路径绕过旧缓存。

### WKWebView 双火 drop 事件
macOS 上 `DOMEventHandler.events.drop` 会触发两次。**不加防抖**——根因在数据层：
→ 类级变量（`_seen_fp = set()` on class body）跨批泄漏 → 第二次处理看到指纹全在 → 判重
→ 修复：`seen_fp = set()` 放方法体内作局部变量，每批独立

### Python API 类变量 = 跨批泄漏源
类体上定义的 `set()` / `list()` 对**整个 webview session** 持久。
绝不用类变量做批内状态——任何随方法调用残留的属性都是隐患。
→ 局部变量或 `__init__` 明确管理生命周期

### 退出码
`webview.start()` 阻塞直到窗口关闭。清理代码放 `start()` 之后。

### 目录扫描无上限
`os.walk()` 遍历大目录时加计数上限（如 `len(seen) >= 200: break`），防性能退化。

### 裸 `except:` 吞异常
`except: pass` 会吞 `KeyboardInterrupt` 和 `SystemExit`。生产代码最低用 `except Exception`，文件操作用 `except OSError`。

## 关联技能

- 批量命名工具开发：本 skill 的首个实战项目
- Impeccable：前端设计
- 达芬奇插件发布管理：公司内部 SMB 部署

## 快速预览（不用 build）

改完 CSS/JS 后跑 `python3 _splice.py` 拼接，浏览器打开 `_build/app.html` 预览。
mock API 自动生效（浏览器里 `window.pywebview` 不存在 → 走 mock）。
确认没问题后再跑 `build.sh` 打包。

## 版本管理 & 自更新（推荐模式）

对外分发（非 SMB 环境）用 OSS + JSON 版本检查：

```
app.py 启动 → GET https://bucket.oss-cn-xxx.aliyuncs.com/version.json
            → 比对 APP_VERSION → 旧了：弹窗提示下载
            → build.sh 最后一步自动上传 ZIP + 更新 JSON
```

自替换（v3.2 计划）：下载 ZIP → SHA256 校验 → 旧文件夹改名 `.old` → 新文件夹移入 → updater 脚本启动新版 → 删 `.old`。跨平台通用逻辑 + 平台差异两行（ditto/xcopy）。

## 视频/图片播放（Blob URL 模式）

不要用 bottle 静态文件或 `file://` URL——WKWebView 安全策略拦截。用 JS API 直传二进制：

```
Python: get_media_data(path) → open(path,'rb') → base64 → return {data, mime}
JS:     await call('get_media_data', path) → atob → Uint8Array → Blob → URL.createObjectURL → <video>.src
```

关键约束：
- `<video playsinline webkit-playsinline>`（WKWebView 不然全屏才渲染）
- CSS 不设 `display:none` 在基础选择器（JS 管显隐）
- `video.removeAttribute('controls')` + 自定义控制栏
- `closeReview` / `navReview` 时 `URL.revokeObjectURL(url)`
- 事件监听器用引用存储 → remove 后再 add 防堆积

## 原生保存对话框

```python
def save_file(self, data, default_name):
    import base64
    result = _window.create_file_dialog(
        webview.SAVE_DIALOG, save_filename=default_name,
        file_types=("Excel 文件 (*.xlsx)",),
    )
    if result:
        with open(result, "wb") as f:
            f.write(base64.b64decode(data))
    return {"ok": bool(result), "path": result or ""}
```

## 打包外部二进制

| 要点 | 说明 |
|------|------|
| 打包 | `--add-binary "/path/to/binary:."` |
| 运行时发现 | 优先 `os.path.join(sys._MEIPASS, 'binary')`，找不到降级 `shutil.which` |
| 典型场景 | ffmpeg/ffprobe 打包进 app，解决用户没装的问题 |
| macOS Gatekeeper | `codesign --force --deep --sign - app.app` 去除隔离标记 |
