"""冒烟测试 — 核心流程自动化验证"""
import os, sys, tempfile, shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.naming import build_filename, FIELD_CONFIG, parse_filename, FILENAME_RE
from shared.naming_checks import check_zero_byte, check_double_ext

passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        failed += 1

# ═══ 1. FIELD_CONFIG 完整性 ═══
print("\n1. FIELD_CONFIG")
check("至少 8 个字段", len(FIELD_CONFIG) >= 8)
keys = [f["key"] for f in FIELD_CONFIG]
check("含 ep", "ep" in keys)
check("含 sc", "sc" in keys)
check("含 gr", "gr" in keys)
check("含 desc", "desc" in keys)
check("含 author", "author" in keys)
check("含 method", "method" in keys)
check("含 ver", "ver" in keys)
check("含 status", "status" in keys)

# ═══ 2. build_filename ═══
print("\n2. build_filename")
fields = {"ep":"01","sc":"02","gr":"03","tk":"01","desc":"全能分镜","author":"张谭","method":"智能分镜版","ver":"01","status":"OK"}
result = build_filename(fields)
check("包含 Ep01", "Ep01" in result)
check("包含 method 字段", "智能分镜版" in result)
check("包含 author 字段", "张谭" in result)
check("包含 status", "OK" in result)
check("不包含 'unnamed'", "unnamed" not in result)
print(f"   输出: {result}")

# ═══ 3. 命名格式 ↔ 解析互逆 ═══
print("\n3. 命名 ↔ 解析")

import tempfile
tmpdir = tempfile.mkdtemp()
name = result + ".mp4"
path = os.path.join(tmpdir, name)
open(path, 'w').close()
parsed = parse_filename(path)
check("解析成功", parsed is not None)
if parsed:
    check("ep 一致", parsed.get("ep") == "01")
    check("method 一致", parsed.get("method") == "智能分镜版")
    check("author 一致", parsed.get("author") == "张谭")
shutil.rmtree(tmpdir)

# ═══ 4. 命名正则 ↔ 格式一致 ═══
print("\n4. 正则匹配")

check("FILENAME_RE 匹配", FILENAME_RE.match(name) is not None)

# ═══ 5. 检查函数 ═══
print("\n5. 检查函数")
from shared.naming import check_zero_byte, check_double_ext
zero_path = os.path.join(tempfile.mkdtemp(), "zero.mp4")
open(zero_path, 'w').close()
check("零字节检测", check_zero_byte(zero_path))
check("双扩展名检测", check_double_ext("test.mp4.mp4"))
check("正常扩展名不报警", not check_double_ext("test.mp4"))
shutil.rmtree(os.path.dirname(zero_path))

# ═══ 结果 ═══
print(f"\n{'='*30}")
print(f"  通过: {passed}  失败: {failed}")
print(f"{'='*30}")
if failed:
    print("❌ 冒烟测试失败")
    sys.exit(1)
else:
    print("✅ 冒烟测试通过")
