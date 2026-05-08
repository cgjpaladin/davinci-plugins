# 工具目录

> 开发/测试/调试工具。文件名即功能提示，下为分类速查。

## 达芬奇调试
| 工具 | 用途 |
|------|------|
| dvr.py | 远程达芬奇 API helper |
| dvr-connect.sh | 达芬奇外联一键连接 |
| show_timeline.py | 打印时间线 IO 内所有片段（颜色/变速/标记等）|
| show_project.py | 打印项目设置（分辨率/色彩科学/渲染）|
| show_mediapool.py | 打印媒体池结构（文件夹/素材/代理状态）|

## 插件开发
| 工具 | 用途 |
|------|------|
| collab_test.py | PostgreSQL 协作模式远程测试框架 |
| state-audit.py | subtitle_state.json 一致性检查 |
| undo-verify.py | 撤销链路验证 |
| pre-commit.sh | pre-commit 检查钩子（dev.sh 调用）|

## 部署/运维
| 工具 | 用途 |
|------|------|
| deploy.py | 批量部署辅助 |
| check.py | 部署后完整性检查 |
| logs.py | SMB 操作日志查看 |

## 单次/实验脚本
| 工具 | 用途 |
|------|------|
| _env.py, _wsl.py | 环境/论坛爬取工具 |
| inspect.py | 对象探查 |
| new.py, runner.py | 新功能原型/测试运行器 |
| try.py | 临时测试（用完可删）|

## 达芬奇个人脚本（本机专用，不上 SMB）
| 脚本 | 来源 | 用途 |
|------|------|------|
| filenameGenerator.py | 张来吃 | 文件名生成器：读取项目/渲染参数自动拼规范文件名 |
