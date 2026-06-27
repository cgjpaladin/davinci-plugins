# stderr 回环 → RecursionError 诊断方法

## 症状

- 日志中出现大量 `maximum recursion depth exceeded`
- `Exception in thread Thread-N (process)` — 处理线程崩溃
- 某条错误消息重复 15+ 次后崩溃
- 崩溃前最后操作是任何触发了 `❌ ⚠ Error 失败` 消息的操作

## 根因模式

```
sys.stderr 被替换为 _UIStderr 对象
  └─ _UIStderr.write(msg) → 调用 _ui_write(msg) → _ui_write_direct(msg)
      └─ _ui_write_direct 内部: print(msg, file=sys.stderr) → 触发 _UIStderr.write  ← 回环!
```

## 三步排查法

### 1. grep 所有重定向点
```bash
grep -rn "sys.stderr\s*=" --include="*.py" AI去字幕/ shared/
```
找一个主入口文件（如 `ui_widgets.py`）的 `sys.stderr = _UIStderr()` 行。

### 2. grep 所有 `file=sys.stderr` 写入点
```bash
grep -rn "file=sys.stderr\|file=_sys.stderr" --include="*.py" AI去字幕/ shared/
```
逐条确认：这个写入点会触发 `_UIStderr.write` 吗？`_UIStderr.write` 会再调写入链吗？

### 3. 画调用图
```
任何错误 → log.fail(msg) → UILogger._write → _ui_write → _ui_write_direct
  → print(..., file=sys.stderr) ← 这是入口
    → _UIStderr.write(msg)
      → _ui_write(msg)           ← 又回到 _ui_write_direct!
        → print(..., file=sys.stderr)
          → ...  无限递归
```

## 标准修复

```python
# 文件最顶部，在任何 stderr 重定向前
import sys
_real_stderr = sys.stderr   # 保存真实 stderr

# 所有内部写 stderr 的地方
_real_stderr.write(msg + "\n")    # ✅ 直写真实 fd
# print(msg, file=sys.stderr)    # ❌ 会走 _UIStderr 回环
```

## 历史案例

- **2026-06-27 AI去字幕**: `_ui_write_direct` + `_event_log` + `StepLogger.fail/warn` 三处 `print(file=sys.stderr)` → OSS 超时/锁冲突/余额不足 全部触发 → 全公司 5 台机器崩溃
