# GitHub 国内更新分发坑位汇总

> 从零开始搭一套面向中国用户的自动更新系统，踩过的所有坑。

## 域名问题

| 域名 | 国内可达 | 用途 | 限制 |
|------|:--:|------|------|
| `raw.githubusercontent.com` | ❌ | raw 文件 | DNS 污染 |
| `api.github.com` | ✅ | API 查询 / 文件内容 | 返回 base64，需解码 |
| `github.com/releases/...` | ❌ | Release 下载 | 部分墙 |
| `cdn.jsdelivr.net` | ✅ | CDN（网宿节点） | 24h 缓存延迟 |
| `purge.jsdelivr.net` | ✅ | CDN 缓存刷新 | 手动调用 |
| `gh-proxy.net` | ⚠️ | GitHub 代理 | 不稳定 |
| `mirror.ghproxy.com` | ⚠️ | GitHub 代理 | 有时超时 |

## 文件名编码

**铁律：全链路 ASCII。**

| 环节 | 坑 | 修法 |
|------|------|------|
| zip 内文件名 | 中文名解压后乱码 | 改成 `install_update.command` |
| zip 根目录名 | 同 | `davinci_plugin_update/` |
| URL 中的文件名 | `urlopen` 只认 ASCII | `urlparse + quote(path, safe='/')` |
| GitHub Release 文件名 | 中文 → `_.zip` | 上传时用英文名 |
| `.env` 注释 | 中文注释 → 编码错误 | 不要中文注释 |
| Python 进程间 | `subprocess.run` text | 显式 `encoding='utf-8'` |

## osascript 陷阱

```bash
# ❌ 错误：do shell script 默认 /bin/sh，不读 shebang
do shell script "/path/to/install_update.command --update"

# ✅ 正确：显式 /bin/bash
do shell script "/bin/bash /path/to/install_update.command --update"
```

## Python 导入路径

达芬奇的 Python 环境不是标准包结构：
```python
# ❌ 相对导入在达芬奇下失效
from .update_config import ...

# ✅ 用绝对导入
from update_config import ...
```

## CDN 缓存

jsDelivr 默认缓存 24 小时。发版后立即调用：
```bash
curl -s "https://purge.jsdelivr.net/gh/OWNER/REPO@main/version.json"
curl -s "https://purge.jsdelivr.net/gh/OWNER/REPO@main/update_latest.zip"
```

## GitHub API base64 解码

```python
# API 返回 {"content": "base64...", "encoding": "base64"}
import base64, json
data = json.loads(response)
zip_bytes = base64.b64decode(data["content"])
```

## 文件权限

`osascript do shell script with administrator privileges` 以 root 运行，生成的文件归属 root。必须：
```bash
chown -R $USER "$INSTALL_DIR"
```
注意 `$(whoami)` 在 root 下返回 root，要用 `$USER`。
