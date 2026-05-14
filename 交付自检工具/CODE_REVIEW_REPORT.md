# 部署代码审查报告

审查日期: 2026-05-14
审查人: CodeBuddy Code
审查范围: config.py / launcher.py / fusionscript_loader.py / launcher_router.py / dicts/*

---

## 严重程度定义
- **P0**: 阻断 — 部署前必须修复，否则使用者无法运行或产生严重后果
- **P1**: 高 — 大概率导致运行失败，部署前强烈建议修复
- **P2**: 中 — 特定场景下失败，建议修复
- **P3**: 低 — 不影响运行，但影响可维护性或最佳实践

---

## 1. config.py — 2 个问题

**文件**: `/Users/bryan/WorkBuddy/达芬奇插件工坊/交付自检工具/config.py`

### P0-1【第7行】`__channel__ = "dev"` 未切生产频道
```python
__channel__ = "dev"
```
`version_string()` 返回 `"2.0.13-dev"`，所有用户都看到 dev 后缀，造成困惑。
**修复**: 改为 `__channel__ = ""`

### P1-2【第13-16行】SMB 路径硬编码，与 launcher 的 deploy.json 机制不一致
```python
SMB_MOUNT = "/Volumes/MYJC"
SMB_SCRIPTS = _os.path.join(SMB_MOUNT, "06_Software", "达芬奇脚本")
SMB_PLUGIN = _os.path.join(SMB_SCRIPTS, "交付自检工具")
```
这些常量与 launcher.py 中通过 deploy.json 动态读取的路径是两套独立体系。若 SMB 挂载点变更，只改 deploy.json 不够，这里也要改。
**修复**: 统一从 deploy.json 或环境变量读取，或确保这些常量在 config.py 中确实被使用时与实际部署路径一致。

---

## 2. launcher.py — 7 个问题

**文件**: `/Users/bryan/WorkBuddy/达芬奇插件工坊/交付自检工具/launcher.py`

### P0-3【第5-7行】Python 解释器路径硬编码为 3.13
```python
_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if not os.path.exists(_PYTHON):
    _PYTHON = "/usr/bin/python3"
```
- 目标机器可能是 3.11/3.12，第一路径不存在会回退到系统自带 Python 3.9
- `/usr/bin/python3` 依赖 Xcode CLT，若未安装也不存在
**修复**: 使用 `shutil.which("python3")` 自动查找，或从环境变量读取

### P0-4【第89行】`subprocess.Popen` 无错误处理
```python
subprocess.Popen([_PYTHON, _UI_SCRIPT], env=_env)
```
- 返回的 Popen 对象未保存、未 .wait()、无返回码检查
- UI 进程若秒崩，用户看到"什么都没发生"
- 无 stdout/stderr 捕获
**修复**: 至少保存 Popen 对象并做 0.5 秒后 poll() 检查，记录非正常退出

### P0-5【第24-29行】deploy.json 缺失 — 本机此文件不存在
```
$ cat ~/达芬奇插件工坊/deploy.json  =>  No such file or directory
```
_deploy = {} → 所有路径使用默认值。若目标环境默认值不匹配，全部路由失败。
**修复**: 随部署包附带 deploy.json 模板；dry-run 中增加对 deploy.json 存在性的检查

### P1-6【第11-13行】`_HERE` fallback 路径假设特定安装位置
```python
except NameError:
    _HERE = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/达芬奇插件工坊"
```
**修复**: 改为从环境变量读取或给出明确错误而非猜测路径

### P1-7【第61-85行】dry-run 自检覆盖面不足
当前仅检查: Python >= 3.9、路由模式、ui.py 存在、python 二进制存在、config 模块导入。
**缺失**: SMB 挂载可访问性、fusionscript.so 存在性、核心 shared/ 模块导入(如 log_writer)、字典文件存在性
**修复**: 扩充检查项列表

### P2-8【第32行】shared 路径无条件插入 sys.path，无存在性验证
```python
sys.path.insert(0, os.path.join(_HERE, '..', 'shared'))
```
**修复**: insert 前检查 `os.path.isdir()`

### P2-9【第80行】dry-run 错误信息截断为 60 字符
```python
result.stderr.strip()[:60]
```
可能丢失关键错误信息。
**修复**: 扩大到 200 字符或记录完整日志

---

## 3. fusionscript_loader.py — 4 个问题

**文件**: `/Users/bryan/WorkBuddy/达芬奇插件工坊/shared/fusionscript_loader.py`

### P0-10【第20行】模块级 SO 加载，无异常处理
```python
bmd = _load_dynamic("fusionscript", _FUSION_SO)
```
- 在 import 时立即执行。若 fusionscript.so 不存在，任何 `from fusionscript_loader import bmd` 都抛 ImportError
- 连 `--dry-run` 都会触发崩溃
**修复**: 改为延迟加载 (lazy init)，在函数中加载并缓存:
```python
_bmd = None
def get_bmd():
    global _bmd
    if _bmd is None:
        if not os.path.exists(_FUSION_SO):
            raise FileNotFoundError(f"未找到 fusionscript.so: {_FUSION_SO}")
        _bmd = _load_dynamic("fusionscript", _FUSION_SO)
    return _bmd
```

### P0-11【第11-13行】`importlib.machinery.ExtensionFileLoader` 已弃用
Python 3.12 标记为 deprecated，3.14 移除。
**修复**: 改用 `importlib.util.spec_from_file_location` + `importlib.util.module_from_spec` 新 API

### P1-12【第18行】fusionscript.so 路径硬编码，无变体兼容
```python
_FUSION_SO = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
```
- 不兼容 DaVinci Resolve Studio.app
- 无 Windows 支持 (.dll vs .so)
**修复**: 使用候选路径列表搜索

### P2-13【第16行】路径修改缺少注释说明
```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```
用途不明确。
**修复**: 添加注释说明为什么需要这一行

---

## 4. launcher_router.py — 5 个问题

**文件**: `/Users/bryan/WorkBuddy/达芬奇插件工坊/shared/launcher_router.py`

### P0-14【第24-29行】deploy.json 缺失 — 同 launcher.py P0-5

### P1-15【第52-57行】gray.json 容错过于静默
```python
try:
    with open(_gray_file) as f:
        gray = json.load(f)
    if _host in gray.get("gray", []):
        _code_dir = os.path.join(_SMB_BASE, "gray")
except Exception:
    pass
```
- 除 FileNotFoundError 外的其他异常 (JSONDecodeError, PermissionError) 也静默吞掉
- 生产环境中 gray.json 损坏时将无任何提示地回退到稳定版（可能是期望行为，但建议至少记录日志）
**修复**: 对非 FileNotFoundError 异常记录 warning 日志

### P1-16【第48行】Dev 机的 shared 路径优先于产品代码目录
Dev 机在第48行先插入 dev shared 目录，第59行再插入 dev code 目录。这导致 shared 模块覆盖产品本地修改。
**修复**: 明确这是否为设计意图，添加注释

### P2-17【第63-86行】dry-run 仅检查 config 和 ui_module
未检查 shared/ 下的依赖模块。
**修复**: 扩充检查项

### P3-18 无 `__version__` 字段
声称"部署后永不更新"，但无版本标识，无法审计。
**修复**: 添加 `__version__` 常量

---

## 5. dicts/ — 6 个问题

**目录**: `/Users/bryan/WorkBuddy/达芬奇插件工坊/交付自检工具/dicts/`

| 文件 | 行数 | 编码 | 状态 |
|------|------|------|------|
| bad_char_ranges.txt | 32 | UTF-8 | 正常 |
| censor_bw.txt | 1620 | ASCII (base64) | 正常 |
| censor_bw_sms.txt | 2330 | ASCII (base64) | 正常 |
| censor_cn.txt | 4975 | UTF-8 | 有政治敏感内容 |
| censor_cn.txt.bak_20260510 | ~4391 | UTF-8 | **应删除**的备份文件 |
| censor_en.txt | 2725 | UTF-8 | 正常 |
| censor_nrta.txt | 1 | UTF-8 | **空占位文件** |
| 短剧违禁词表.csv | 7 | CSV | 数据异常 |

### P0-19 政治敏感内容风险
`censor_cn.txt` (4975行) 包含大量政治敏感词（领导人姓名变体、64相关、台独/藏独、法轮功等）。
虽然用途是内容过滤黑名单，但文件本身携带这些关键词即构成分发风险。
**修复**: 评估法律合规性，必要时加密存储

### P1-20【censor_nrta.txt 空占位】
仅含一行 `（待填充）`。广电总局关键词过滤功能完全未实现。
**修复**: 填空或明确标注功能未启用

### P1-21【censor_cn.txt.bak_20260510 备份文件不应部署】
与当前版本差 583 行（当前版更新）。增加冗余和敏感内容暴露面。
**修复**: 部署前删除此文件

### P2-22【censor_bw.txt / censor_bw_sms.txt base64 编码】
消费代码必须支持运行时 base64 解码。若解码逻辑缺失，黑名单静默失效。
**修复**: 验证消费代码确实有 base64 解码步骤

### P2-23【短剧违禁词表.csv 数据异常】
- 第7行 `你妈` 被放在"白名单"列，显然错误
- 只有 6 条数据记录，数据量过少
**修复**: 审查 CSV 数据准确性

### P3-24 文件编码不一致
ASCII (base64) 与 UTF-8 混用。
**修复**: 确保消费代码统一使用 UTF-8 打开所有文件

---

## 总结

| 严重度 | 数量 | 关键项 |
|--------|------|--------|
| P0 阻断 | 8 | channel=dev, Popen无检错, deploy.json缺失, SO加载无异常处理, 弃用API, 敏感内容风险, 空字典文件, 备份文件 |
| P1 高 | 8 | SMB路径不一致, _HERE回退硬编码, dry-run覆盖不全, gray.json静默, 路径优先顺序, fusionscript.so单一路径, 敏感内容, NRTA字典空 |
| P2 中 | 9 | sys.path无验证, 错误截断, 路径注释缺失, dry-run覆盖, 无版本标识, base64解码依赖, CSV数据异常, 编码不一致, 文档字符串 |
| P3 低 | 2 | 无__name__保护, 无__version__ |

**部署建议**: 修复所有 P0 和 P1 项后再部署。P2 项视时间窗口决定。
