#!/bin/bash
# ── replace_all 防线：提交前强制运行预检 ──
# 任何一步失败 → 提交被拦截 → 必须先修再交
# 安装：cp .git/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

cd "$(git rev-parse --show-toplevel)"
bash 批量命名工具/_precommit_check.sh
