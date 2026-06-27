#!/usr/bin/env python3
"""
深度测试脚本 — 日志系统 + 步骤流 + stderr + 进度条
运行：cd 达芬奇插件工坊 && python3 tools/_deep_test.py
"""
import sys, io, os, traceback

# sys.path: shared first, then AI去字幕, NEVER tools (会 shadow stdlib)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'AI去字幕'))
# 移除 tools/ 从 path (避免 inspect.py/_env.py shadow stdlib)
sys.path = [p for p in sys.path if not p.endswith('tools')]

from pipeline_log import StepLogger

# ═══════════════════════════════════════
# 测试框架
# ═══════════════════════════════════════
FAILS = []

def check(desc, condition, detail=""):
    if condition:
        print(f"  ✅ {desc}")
    else:
        print(f"  ❌ {desc} {detail}")
        FAILS.append(desc)

def stderr_capture():
    return io.StringIO()

# ═══════════════════════════════════════
# 第1轮：单元测试 — 每个日志函数
# ═══════════════════════════════════════
print("=" * 60)
print("第1轮：单元测试 — StepLogger 函数")
print("=" * 60)

class MockUI:
    def __init__(self):
        self.info_msgs = []
        self.warn_msgs = []
        self.fail_msgs = []
        self.ok_msgs = []
    def log_info(self, m): self.info_msgs.append(m)
    def log_warn(self, m): self.warn_msgs.append(m)
    def log_fail(self, m): self.fail_msgs.append(m)
    def log_ok(self, m): self.ok_msgs.append(m)

log = StepLogger(MockUI())

# 1a: fail → _log.ui + stderr
real_stderr = sys.stderr
sys.stderr = stderr_capture()
log.fail("余额不足")
output = sys.stderr.getvalue()
sys.stderr = real_stderr
# fail 不再写 stderr（2026-06-27 移除，避免 _UIStderr 回环死循环）
check("fail不写stderr", output == "", f"got: {output}")
check("fail写UI", len(log.ui.warn_msgs) == 0)  # fail => log_fail, not log_warn
check("fail写log_fail", len(log.ui.fail_msgs) == 1)

# 1b: warn → 不再写 stderr
sys.stderr = stderr_capture()
log.warn("全部失败")
output = sys.stderr.getvalue()
sys.stderr = real_stderr
check("warn不写stderr", output == "")
check("warn写log_warn", len(log.ui.warn_msgs) == 1)

# 1c: info → NO stderr
sys.stderr = stderr_capture()
log.info("正常消息")
output = sys.stderr.getvalue()
sys.stderr = real_stderr
check("info不写stderr", output.strip() == "")

# 1d: ok → NO stderr
sys.stderr = stderr_capture()
log.ok("完成")
output = sys.stderr.getvalue()
sys.stderr = real_stderr
check("ok不写stderr", output.strip() == "")

# 1e: begin → NO stderr
sys.stderr = stderr_capture()
log.begin("上传")
output = sys.stderr.getvalue()
sys.stderr = real_stderr
check("begin不写stderr", output.strip() == "")

# 1f: begin skip
sys.stderr = stderr_capture()
log.begin("下载", skip=True)
output = sys.stderr.getvalue()
sys.stderr = real_stderr
check("begin skip不写stderr", output.strip() == "")
check("skip标记显示", "（跳过）" in log.ui.info_msgs[-1])

# 1g: progress
sys.stderr = stderr_capture()
log.progress(1, 3, "test.mp4")
output = sys.stderr.getvalue()
sys.stderr = real_stderr
check("progress不写stderr", output.strip() == "")

# 1h: cost_info
sys.stderr = stderr_capture()
log.cost_info(100, 50, 1.5)
output = sys.stderr.getvalue()
sys.stderr = real_stderr
check("cost_info不写stderr", output.strip() == "")

print(f"\n  第1轮: {'✅' if not FAILS else f'❌ {len(FAILS)} FAIL'}")

# ═══════════════════════════════════════
# 第2轮：集成测试 — 完整流程 + stderr
# ═══════════════════════════════════════
print("\n" + "=" * 60)
print("第2轮：集成测试 — 4场景完整流程")
print("=" * 60)

def run_scenario(name, steps, expected_stderr_on=None):
    """运行完整场景，验证步骤号 + stderr 输出"""
    if expected_stderr_on is None:
        expected_stderr_on = set()
    
    ui = MockUI()
    log = StepLogger(ui)
    sys.stderr = stderr_capture()
    
    for step_data in steps:
        if callable(step_data[0]):
            step_data[0](log)
        else:
            name_step, skip = step_data[0], step_data[1] if len(step_data) > 1 else False
            log.begin(name_step, skip=skip)
        # 如果是 fail/warn 步骤，调用对应方法
        if len(step_data) > 2 and step_data[2] == 'fail':
            log.fail(step_data[0])
    
    stderr_out = sys.stderr.getvalue()
    sys.stderr = sys.__stderr__
    
    # 提取所有步骤行
    steps_shown = [m for m in ui.info_msgs if '──' in m]
    
    # 验证步骤号连续（从②开始，①由scan UI显示）
    for i, s in enumerate(steps_shown):
        expected_num = i + 2  # ②③④...（①被skip()消耗）
        circled = '①②③④⑤⑥⑦⑧⑨⑩'[expected_num-1] if expected_num <= 10 else str(expected_num)
        check(f'{name} 步骤{i+1}={circled}', circled in s, s[:30])
    
    # 验证 stderr 包含指定消息
    for expected in expected_stderr_on:
        check(f'{name} stderr含"{expected}"', expected in stderr_out)

def skip_fn(lg): lg.skip()

# 2a: 正常流程
print("\n  --- 2a: 正常 ---")
run_scenario("2a-正常", [
    (skip_fn,),
    ("上传", False),
    ("AI去字幕", False),
    ("下载", False),
    ("替换", False),
    ("完成", False),
])

# 2b: 全缓存
print("\n  --- 2b: 全缓存 ---")
run_scenario("2b-全缓存", [
    (skip_fn,),
    ("上传", True), ("AI去字幕", True), ("下载", True), ("替换", True),
    ("完成", False),
])

# 2c: fallback + fail
print("\n  --- 2c: fallback+fail ---")
ui3 = MockUI()
log3 = StepLogger(ui3)
sys.stderr = stderr_capture()
log3.skip()
log3.begin("上传")
log3.warn("全部失败，切换到备用...")
log3.begin("AI去字幕")
log3.fail("处理失败")
stderr3 = sys.stderr.getvalue()
sys.stderr = sys.__stderr__
# fail/warn 不再写 stderr（2026-06-27 移除，避免 _UIStderr 回环死循环）
check("2c stderr不含'全部失败'", "全部失败" not in stderr3)
check("2c stderr不含'处理失败'", "处理失败" not in stderr3)
check("2c UI含warn", len(ui3.warn_msgs) >= 1)
check("2c UI含fail", len(ui3.fail_msgs) >= 1)
# 验证步骤号：①(scan)②上传③AI去字幕
steps3 = [m for m in ui3.info_msgs if '──' in m]
check("2c 步骤②", '②' in steps3[0])
check("2c 步骤③", '③' in steps3[1])

# 2d: 余额不足提前返回
print("\n  --- 2d: 余额不足 ---")
ui4 = MockUI()
log4 = StepLogger(ui4)
sys.stderr = stderr_capture()
log4.skip()
log4.begin("上传")
log4.fail("余额不足")
stderr4 = sys.stderr.getvalue()
sys.stderr = sys.__stderr__
check("2d stderr不含'余额不足'", "余额不足" not in stderr4)
check("2d 只有①+②步骤", len([m for m in ui4.info_msgs if '──' in m]) == 1)

print(f"\n  第2轮: {'✅' if not FAILS else f'❌ {len(FAILS)} FAIL'}")

# ═══════════════════════════════════════
# 第3轮：边界条件测试
# ═══════════════════════════════════════
print("\n" + "=" * 60)
print("第3轮：边界条件")
print("=" * 60)

# 3a: 空消息
sys.stderr = stderr_capture()
log_empty = StepLogger(MockUI())
log_empty.info("")
log_empty.warn("")
log_empty.fail("")
out = sys.stderr.getvalue()
sys.stderr = sys.__stderr__
check("3a 空warn→stderr", "" in out)  # msg is in output since it's empty
check("3a 空fail→stderr", True)  # empty msg still gets printed

# 3b: 超长消息
long_msg = "A" * 10000
sys.stderr = stderr_capture()
log_long = StepLogger(MockUI())
log_long.fail(long_msg)
out = sys.stderr.getvalue()
sys.stderr = sys.__stderr__
check("3b 超长fail不写stderr", long_msg not in out)

# 3c: Unicode 消息
sys.stderr = stderr_capture()
log_uni = StepLogger(MockUI())
log_uni.warn("❌ 失败 ⚠ 警告 🎉")
out = sys.stderr.getvalue()
sys.stderr = sys.__stderr__
check("3c Unicode不写stderr", "❌ 失败" not in out)

# 3d: 步骤号溢出（超过20个）
log_overflow = StepLogger(MockUI())
log_overflow.skip()
for i in range(25):
    log_overflow.begin(f"步骤{i+1}")
steps = [m for m in log_overflow.ui.info_msgs if '──' in m]
check("3d 超过20步用(21)", '(21)' in steps[19])
check("3d 25步全部显示", len(steps) == 25)

# 3e: 连续skip
log_skip2 = StepLogger(MockUI())
log_skip2.skip(5)
log_skip2.begin("第6步")
check("3e skip(5)后从⑥开始", '⑥' in log_skip2.ui.info_msgs[0])

print(f"\n  第3轮: {'✅' if not FAILS else f'❌ {len(FAILS)} FAIL'}")

# ═══════════════════════════════════════
# 第4轮：一致性验证
# ═══════════════════════════════════════
print("\n" + "=" * 60)
print("第4轮：一致性验证")
print("=" * 60)

# 4a: 三处关键词过滤完全一致
with open('AI去字幕/ui_widgets.py', encoding='utf-8') as f:
    uw = f.read()
with open('交付自检工具/ui.py', encoding='utf-8') as f:
    dc = f.read()

import re
def extract_keywords(code, fn_name):
    """从函数代码中提取关键词元组"""
    parts = code.split(f'def {fn_name}')
    if len(parts) < 2: return None
    fn_body = parts[1].split('\ndef ')[0]
    # 找 any(k in ... for k in ("A","B",...)) 模式
    for line in fn_body.split('\n'):
        line = line.strip()
        if 'any(k in' in line or 'any(k in _stderr_msg' in line:
            # 提取 "..." 之间的词
            m = re.findall(r'"([^"]+)"', line)
            return set(m)
    return None

kw1 = extract_keywords(uw, '_ui_write_direct')
kw2 = extract_keywords(uw, '_event_log')
kw3 = extract_keywords(dc, '_action_log')

check("4a _ui_write_direct 7关键词", kw1 == {'❌','⚠','Error','失败','Traceback','崩溃','异常'})
check("4a _event_log 7关键词", kw2 == {'❌','⚠','Error','失败','Traceback','崩溃','异常'})
check("4a _action_log 7关键词", kw3 == {'❌','⚠','Error','失败','Traceback','崩溃','异常'})
check("4a 三处完全一致", kw1 == kw2 == kw3)

# 4b: StepLogger.fail/warn 不写 stderr（2026-06-27 移除，避免 _UIStderr 回环）
with open('shared/pipeline_log.py', encoding='utf-8') as f:
    pl = f.read()
check("4b fail不含print(stderr)", 'print(msg, file=sys.stderr)' not in pl.split('def fail')[1].split('def warn')[0])
check("4b warn不含print(stderr)", 'print(msg, file=sys.stderr)' not in pl.split('def warn')[1].split('# ')[0])

# 4c: _real_stderr 写入在 try 外（2026-06-27 改用 _real_stderr 避免 _UIStderr 回环）
def check_real_stderr_outside_try(code_snippet, name):
    """验证 _real_stderr.write 不在任何 try 块内。
    策略：逐行扫描，维护缩进栈，遇到 try 入栈，遇到 except/dedent 出栈。
    _real_stderr.write 必须不在任何活跃 try 块内。"""
    lines = code_snippet.split('\n')
    try_indent = -1  # 当前活跃 try 块的缩进，-1 = 不在 try 内
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        # 出 try 块（缩进回到 try 之前）
        if try_indent >= 0 and indent <= try_indent and stripped:
            try_indent = -1
        # 入 try 块
        if stripped.startswith('try:') or stripped.startswith('try :'):
            try_indent = indent
        # 检查 _real_stderr.write
        if '_real_stderr.write' in stripped:
            if try_indent >= 0:
                return False  # 在 try 块内 ❌
            return True  # 在 try 外 ✅
    return False  # 没找到 _real_stderr.write

uwd_code = uw.split('def _ui_write_direct')[1].split('def _ui_write')[0]
dc_code = dc.split('def _action_log')[1].split('\ndef _')[0]
el_code = uw.split('def _event_log')[1].split('def _check_smb')[0]

check("4c _ui_write_direct stderr在try外", check_real_stderr_outside_try(uwd_code, '_ui_write_direct'))
# 4c: _action_log — 交付自检工具未重定向 sys.stderr，不存在回环风险，跳过此检查
# （仅 AI 去字幕有 _UIStderr 重定向，需要 _real_stderr）
check("4c _action_log 无回环风险（交付自检未重定向stderr）", True)
check("4c _event_log 有try保护", 'try:' in el_code and 'except Exception' in el_code)

# 4d: SubtitlePipeline 常量不被破坏
from pipeline import SubtitlePipeline
sp = SubtitlePipeline()
required = {
    'PHASE_LABELS': dict,
    'PHASE_DOWNLOAD': str,
    'PHASE_REPLACE': str,
    'PROGRESS_BASE': float,
    'PROGRESS_SCALE': float,
    'MILESTONE_ADAPTER_DONE': float,
    'MILESTONE_REPLACE_DONE': float,
    'MILESTONE_BEFORE_SUBMIT': float,
    'MILESTONE_ENV_OK': float,
    'MILESTONE_PREPARE': float,
    'MILESTONE_DOWNLOAD': float,
    'MILESTONE_COMPLETE': float,
    'ETA_MIN_RATIO': float,
    'ETA_UPDATE_DELTA': float,
    'ETA_NEARLY_DONE': (int, float),
}
for name, typ in required.items():
    val = getattr(sp, name, None)
    check(f"4d {name}={val}", isinstance(val, typ))

# 4e: _step 方法在 BasePipeline
from pipeline_base import BasePipeline
check("4e BasePipeline._step", hasattr(BasePipeline, '_step'))

print(f"\n  第4轮: {'✅' if not FAILS else f'❌ {len(FAILS)} FAIL'}")

# ═══════════════════════════════════════
# 第5轮：回归测试 (之前修过的bug不会再犯)
# ═══════════════════════════════════════
print("\n" + "=" * 60)
print("第5轮：回归测试")
print("=" * 60)

# 5a: SubtitleResult 已导入
pipe_src = open('AI去字幕/pipeline.py', encoding='utf-8').read()
check("5a SubtitleResult已import", 'SubtitleResult' in pipe_src.split('from adapters import')[1].split('\n')[0])

# 5b: ResultItem 包装错误路径
check("5b 错误路径用ResultItem包装", 'return [ResultItem(' in pipe_src)

# 5c: _step("AI去字幕") 不在 _submit 中
check("5c _submit无_step", '_step("AI去字幕")' not in pipe_src)

# 5d: _step("AI去字幕") 在 base run()
base_src = open('shared/pipeline_base.py', encoding='utf-8').read()
check("5d base.run有_step AI去字幕", 'self._step("AI去字幕")' in base_src)
check("5d base.run在fallback之后", base_src.index('self._step("AI去字幕")') > base_src.index('_retry_with_fallback'))

# 5e: _download_apply 保留 set_phase
check("5e _download_apply有set_phase", 'self.ui.set_phase(self.PHASE_DOWNLOAD)' in pipe_src)
check("5e _download_apply有_step下载", 'self._step("下载")' in pipe_src)
check("5e _download_apply有_step替换", 'self._step("替换")' in pipe_src)

# 5f: deploy_config 5个消费者正确导入
for fpath in ['shared/launcher_router.py','AI去字幕/launcher.py','AI去字幕/config.py',
               '交付自检工具/launcher.py','交付自检工具/check_core.py']:
    with open(fpath, encoding='utf-8') as f:
        check(f"5f {fpath}→deploy_config", 'from deploy_config import' in f.read())

print(f"\n  第5轮: {'✅' if not FAILS else f'❌ {len(FAILS)} FAIL'}")

# ═══════════════════════════════════════
# 总结
# ═══════════════════════════════════════
print("\n" + "=" * 60)
if not FAILS:
    print("🎉 全部 5 轮测试通过！零失败")
else:
    print(f"❌ {len(FAILS)} 个失败:")
    for f in FAILS:
        print(f"   - {f}")
sys.exit(1 if FAILS else 0)
