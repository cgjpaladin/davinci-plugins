# TODO

## 🔴 待做

- **P1a**: UI 文字从 FIELD_CONFIG 驱动 — inspector HTML 动态生成，标签/placeholder 不再硬编码
- **测试**: 完整流程：拖入→全选填字段→切换方法→Enter 逐字段→批量重命名→撤销

## 🟡 后续

- shared/naming.py 拆分 (build/parse/check/folder 四类职责分离)
- 自动检查结果在文件列表有更明显标注
- Windows 部署适配


## 🔵 流程优化（来自 2026-05-14 复盘）

- **冒烟测试脚本**: Python 自动化测试核心流程（拖入→填→重命名→撤销）
- **错误弹窗**: Python/JS 异常 → toast 告警，不沉默
- **浏览器 preview 增强**: mock 可拖入本地文件，和真实 API 行为一致
- **diff 预览**: build 前自动 git diff --stat 供审阅
- **活文档**: 改架构决策后立刻更新技能文件，不拖到 session 结束
