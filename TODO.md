# TODO — 达芬奇插件工坊

## 🔴 紧急

- 部署 license 云函数（SCF/CloudBase）+ 设 `WB_LICENSE_URL`
- 建激活码生成工具（INSERT keys 表，格式 XXXX-XXXX-XXXX）
- tttt 恢复正常 expire_time（三份 credential 文件还原）
- 服务端补 `deactivate` 路由（`cloud/license_server.py` ROUTES 缺失）

## 🟡 重要

- 补 `deactivate` 成功后清除旧路径 license.dat 的逻辑
- 下载链路监控：记录每次下载耗时 + 选择的链路 → 评估 ghproxy vs GitHub 直连

## 💭 远期

- 激活码管理后台（Web 页面：生成/查询/吊销）
- 购买流程自动化（微信支付 → 自动发货激活码）