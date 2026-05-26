# 创壹特供版 · TODO

## v1.0 已完成 (表格版)
- [x] EP/SC/SH/TK/desc/type/author/V/status 9 字段命名系统
- [x] 表格视图：双击单元格内联编辑，Enter 提交 / Escape 取消
- [x] SH 多镜编辑器：双击 → 内联 [+][-] 面板
- [x] type 根据文件扩展名自动判定 (AIPIC/AIVID)，列只读
- [x] desc 仅 AIPIC 可编辑，AIVID 灰掉（不可双击）
- [x] desc 实时过滤：只保留中英文数字
- [x] TK 按 EP+SC+SH+V 分组自动递增
- [x] 图片缩略图 (Pillow + EXIF 自变换)
- [x] 状态不能为空，必须 OK/KP/NG
- [x] 所有必填字段齐全才能重命名
- [x] 无归档按钮、无目标路径输入
- [x] Python 冒烟测试 29/29 ✅
- [x] macOS + Windows 构建脚本
- [x] 原版代码零改动

## 远期规划
- [ ] Windows 实际打包+运行测试
- [ ] 多文件批量编辑 SH（当前多选编辑 SH 不适用多镜逻辑）
