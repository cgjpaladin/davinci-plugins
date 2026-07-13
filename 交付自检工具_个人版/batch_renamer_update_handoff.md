# 批量命名工具 — 更新系统交接

> 小裁缝（交付自检分身）→ 批量命名分身。2026-07-13 因 `update_latest.zip` 同名冲突导致交付自检更新失效后整理。

---

## 问题

批量命名 `build.sh:106` 输出 `DELTA_ZIP` 到 `update_latest.zip`，跟交付自检的更新包同名，每次构建互相覆盖。

## 已完成的改动（交付自检侧）

| 变更 | 文件 |
|------|------|
| 改名 `delivery_checker_update.zip` | `build_personal.sh`、`update_config.py` |
| CDN/URL 同步更新 | `version.json` delivery_checker section |
| gitignore 白名单 | `.gitignore` |

## 你需要做的（批量命名侧）

### 1. 改名

批量命名的更新包建议改为 `batch_renamer_update.zip`：

```bash
# build.sh 改动
- DELTA_ZIP="$HOME/WorkBuddy/达芬奇插件工坊/update_latest.zip"
+ DELTA_ZIP="$HOME/WorkBuddy/达芬奇插件工坊/batch_renamer_update.zip"
```

### 2. 更新 URL

`version.json` → `batch_renamer_mac` section 的 URLs 指向新文件名。

### 3. 更新 updater 代码

批量命名自己的 `update_config.py` 中 `DOWNLOAD_URLS` 和 `UPDATE_FILE` 指向 `batch_renamer_update.zip`。

### 4. .gitignore

已完成—— `.gitignore` 已添加 `!batch_renamer_mac.zip` 和 `!batch_renamer_win.zip` 白名单。

---

## 未来新产品的通用规范

每加一个产品，遵循三个约定：

1. **唯一文件名**：`{product}_update.zip`（e.g. `subtitle_remover_update.zip`）
2. **独立 version.json section**：只改自己的 section，不动别人的
3. **白名单**：`.gitignore` 加 `!{product}_update.zip`

这样 N 个产品共用同一个 repo、同一个 `version.json`、同一个 CDN，互相不冲突。
