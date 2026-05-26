# 创壹特供版 · TODO

## v1.0 已完成
- [x] EP/SC/SH/TK/desc/type/author/V/status 9 字段命名系统
- [x] type 根据文件扩展名自动判定 (AIPIC/AIVID)
- [x] desc 仅 AIPIC 可填，AIVID 灰掉
- [x] 多镜 SH [+] 追加按钮，`/` 串联
- [x] TK 按 EP+SC+SH+V 分组自动递增
- [x] 图片缩略图 (Pillow + EXIF 自变换)
- [x] 描述只保留中英文数字
- [x] 状态不能为空，必须 OK/KP/NG
- [x] 所有字段齐全才能重命名
- [x] macOS + Windows 构建脚本

## 远期规划
- [ ] Windows 实际打包测试
- [ ] 批量添加文件夹支持（连同子文件夹递归）
- [ ] 自定义命名分隔符
