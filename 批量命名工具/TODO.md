# TODO

> 原更新于 2026-05-25。v3.8.0（2026-07-16）已覆盖以下紧急项：石家庄部署/Windows构建/DMG打包/CDN发布链。
> 剩余远期项仍有效，待排期。

## 🔴 紧急（v3.8.0 已解决）

- [ ] **石家庄部署**：桌面部署包拷 U 盘 → 到那边跑 test_smoke.py → 确认依赖装好 → 教用户用
- [ ] **Windows 机器环境确认**：装 Python 3.12+ + pywebview + bottle + PyInstaller + ffmpeg → `build_win.bat table`

## 🟡 下一版本 (v3.1)

- [ ] **阿里云 OSS bucket**：建 `renamer-dist` → 公开读 → 写入 `renamer_version.json`
- [ ] **版本检查 Core**：`renamer_web.py` 加 `check_update()` → GET OSS JSON → 比对 APP_VERSION → 旧了弹窗提醒 → 失败静默
- [ ] **build.sh 自动上传**：打包后自动 zip + 上传 OSS + 更新 version.json
- [ ] **批量命名工具开发 skill 补全**：加 FIELD_CONFIG 数据结构示例 + 新字段端到端 checklist + `_splice.py` 嵌入机制说明

## 💭 远期

- [ ] **自更新 v3.2**：下载 ZIP → SHA256 校验 → .old 原子替换 → updater 脚本 → 跨平台
- [ ] **AI去字幕 Windows 适配**：`platform_config.py` 抽离 macOS 硬编码（Python 路径/pgrep/chflags）
- [ ] **交付自检 CHECKS 文档**：版本号 2.0.30 已同步，补充新增检查项注册说明
- [ ] **Apple Developer 签名**：$99/年 → 去掉 Gatekeeper 弹窗（商业发布前做）
- [ ] **旧 daily log 蒸馏**：30 天以上的逐日日志提炼到 MEMORY.md
- [ ] **批量命名工具 / .gitignore**：确认 `deploy.json` 安全（已在 `~/达芬奇插件工坊/` 外部）

---

*更新于 2026-05-25 01:30*
