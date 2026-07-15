"""冒烟测试 — 创壹特供版核心流程自动化验证"""
import os, sys, tempfile, shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from naming_createone import build_filename, FIELD_CONFIG, parse_filename, FILENAME_RE, ext_to_type

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
check("含 shot", "shot" in keys)
check("含 tk", "tk" in keys)
check("含 desc", "desc" in keys)
check("含 type", "type" in keys)
check("含 author", "author" in keys)
check("含 ver", "ver" in keys)
check("含 status", "status" in keys)

# ═══ 2. ext_to_type ═══
print("\n2. ext_to_type")
check(".mp4 → AIVID", ext_to_type(".mp4") == "AIVID")
check(".mov → AIVID", ext_to_type(".mov") == "AIVID")
check(".png → AIPIC", ext_to_type(".png") == "AIPIC")
check(".jpg → AIPIC", ext_to_type(".jpg") == "AIPIC")
check(".unknown → ''", ext_to_type(".xyz") == "")

# ═══ 3. build_filename ═══
print("\n3. build_filename")
fields = {"ep":"01","sc":"01","shot":"01","tk":"01","desc":"测试描述","type":"AIPIC","author":"张三","ver":"01","status":"OK"}
result = build_filename(fields)
check("包含 EP01", "EP01" in result)
check("包含 SC01", "SC01" in result)
check("包含 SH01", "SH01" in result)
check("包含 TK01", "TK01" in result)
check("包含 AIPIC", "AIPIC" in result)
check("包含 V01", "V01" in result)
check("包含 OK", "OK" in result)
print(f"   输出: {result}")

# ═══ 4. 多镜 build ═══
print("\n4. 多镜 build")
fields2 = {"ep":"01","sc":"01","shot":"01-02-03","tk":"01","desc":"","type":"AIVID","author":"李四","ver":"02","status":"KP"}
result2 = build_filename(fields2)
check("多镜 SH01-02-03", "SH01-02-03" in result2)
print(f"   输出: {result2}")

# ═══ 5. 命名 ↔ 解析 ═══
print("\n5. 命名 ↔ 解析")
tmpdir = tempfile.mkdtemp()
name = result + ".mp4"
path = os.path.join(tmpdir, name)
open(path, 'w').close()
parsed = parse_filename(path)
check("解析成功", parsed is not None)
if parsed:
    check("ep 一致", parsed.get("ep") == "01")
    check("type 一致", parsed.get("type") == "AIPIC")
    check("author 一致", parsed.get("author") == "张三")
shutil.rmtree(tmpdir)

# ═══ 6. 正则匹配 ═══
print("\n6. 正则匹配")
check("FILENAME_RE 单镜匹配", FILENAME_RE.match(name) is not None)
name_multi = result2 + ".mp4"
check("FILENAME_RE 多镜匹配", FILENAME_RE.match(name_multi) is not None)

# ═══ 结果 ═══
print(f"\n{'='*30}")
print(f"  通过: {passed}  失败: {failed}")
print(f"{'='*30}")
if failed:
    print("❌ 冒烟测试失败")
    sys.exit(1)
else:
    print("✅ 冒烟测试通过")
