"""
core.py + pricing.py 纯函数单元测试
不依赖达芬奇，零外部依赖（仅 Python 标准库 unittest），可直接运行：
    python3 AI去字幕/tests/test_core.py

测试覆盖：
  - extract_ep        — EP编号提取
  - build_output_path — 输出路径构建 + 版本递增
  - sanitize_filename — 文件名安全化
  - normalize_for_match — Unicode变体折叠
  - post_check        — 输出文件验证
  - estimate_cost     — 计费估算（无痕AI + 鬼手）
  - point_to_yuan     — 积分→人民币转换
"""
import os
import sys
import tempfile
import unittest

# 路径注入：让测试能 import shared/ 下的模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'shared'))

from core import (
    extract_ep, build_output_path,
    sanitize_filename, normalize_for_match, post_check,
    TaskRecord,
)
from pricing import estimate_cost, point_to_yuan


class TestExtractEp(unittest.TestCase):
    def test_standard_ep(self):
        self.assertEqual(extract_ep("EP01_g1_01_v01.mp4"), "EP01")
        self.assertEqual(extract_ep("EP123_素材.mp4"), "EP123")
        self.assertEqual(extract_ep("EP99.mp4"), "EP99")

    def test_no_ep_prefix(self):
        self.assertEqual(extract_ep("clip_without_ep.mp4"), "EP00")
        self.assertEqual(extract_ep("video.mp4"), "EP00")

    def test_empty_string(self):
        self.assertEqual(extract_ep(""), "EP00")

    def test_ep_lowercase(self):
        # 只匹配大写 EP，小写不匹配
        self.assertEqual(extract_ep("ep01_video.mp4"), "EP00")


class TestBuildOutputPath(unittest.TestCase):
    def test_basic_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            full, ep, subdir, name = build_output_path("EP03_test.mp4", tmp, "")
            self.assertEqual(ep, "EP03")
            self.assertEqual(subdir, "")
            self.assertIn("去字幕", name)
            self.assertTrue(name.endswith(".mp4"))
            self.assertTrue(os.path.isdir(os.path.dirname(full)))

    def test_version_increment(self):
        """当前版本不包含版本号递增，每次都生成相同的干净文件名"""
        with tempfile.TemporaryDirectory() as tmp:
            full1, _, _, name1 = build_output_path("EP03_test.mp4", tmp, "")
            self.assertIn("去字幕", name1)
            self.assertTrue(name1.endswith(".mp4"))
            # 创建文件后再次调用，文件名相同（当前无版本递增逻辑）
            with open(full1, "w") as f:
                f.write("fake")
            full2, _, _, name2 = build_output_path("EP03_test.mp4", tmp, "")
            self.assertEqual(name1, name2)

    def test_no_ep_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, ep, _, _ = build_output_path("video.mp4", tmp, "")
            self.assertEqual(ep, "EP00")

    def test_already_cleaned_name(self):
        """文件名已含 _去字幕 后缀，应正确处理"""
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, name = build_output_path("EP05_test_去字幕.mp4", tmp, "")
            self.assertNotIn("去字幕_去字幕", name)  # 不应重复


class TestSanitizeFilename(unittest.TestCase):
    def test_control_characters_removed(self):
        self.assertNotIn("\x00", sanitize_filename("test\x00.mp4"))
        self.assertNotIn("\x1f", sanitize_filename("test\x1f.mp4"))

    def test_path_separators_replaced(self):
        self.assertNotIn("/", sanitize_filename("a/b.mp4"))
        self.assertEqual(sanitize_filename("a/b.mp4"), "a&b.mp4")
        self.assertNotIn("\\", sanitize_filename("a\\b.mp4"))

    def test_fullwidth_punctuation(self):
        result = sanitize_filename("test：file.mp4")
        self.assertIn("：", result)   # 全角冒号保留（安全形式）
        self.assertNotIn(":", result)  # ASCII冒号被替换

    def test_trailing_cleanup(self):
        self.assertEqual(sanitize_filename("test .mp4"), "test .mp4")   # 内部空格保留
        self.assertEqual(sanitize_filename("test.mp4. "), "test.mp4")   # 尾部空格+点清除
        self.assertEqual(sanitize_filename("test.mp4 ."), "test.mp4")   # 尾部空格+点

    def test_question_mark_replaced(self):
        result = sanitize_filename("test?.mp4")
        self.assertNotIn("?", result)

    def test_asterisk_replaced(self):
        result = sanitize_filename("test*.mp4")
        self.assertNotIn("*", result)


class TestNormalizeForMatch(unittest.TestCase):
    def test_fullwidth_to_ascii(self):
        self.assertEqual(normalize_for_match("test：file"), "test:file")

    def test_curly_quotes(self):
        self.assertEqual(normalize_for_match("\u201ctest\u201d"), '"test"')

    def test_dashes(self):
        self.assertEqual(normalize_for_match("a\u2014b"), "a-b")

    def test_case_insensitive(self):
        self.assertEqual(normalize_for_match("ABC"), "abc")
        self.assertEqual(normalize_for_match("AbCd"), "abcd")

    def test_whitespace_normalized(self):
        result = normalize_for_match("a   b")
        self.assertEqual(result, "a b")

    def test_brackets_stripped_spaces(self):
        result = normalize_for_match("a ( b )")
        self.assertEqual(result, "a(b)")


class TestPostCheck(unittest.TestCase):
    def test_empty_list(self):
        result = post_check([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["ok"], 0)
        self.assertEqual(result["fail"], 0)

    def test_all_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            f1 = os.path.join(tmp, "ok1.mp4")
            f2 = os.path.join(tmp, "ok2.mp4")
            with open(f1, "w") as f:
                f.write("x" * 200_000)  # 200KB
            with open(f2, "w") as f:
                f.write("x" * 500_000)  # 500KB
            result = post_check([f1, f2])
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["ok"], 2)
            self.assertEqual(result["fail"], 0)

    def test_file_not_exist(self):
        result = post_check(["/nonexistent/path/file.mp4"])
        self.assertEqual(result["fail"], 1)
        self.assertEqual(result["problems"][0]["file"], "file.mp4")
        self.assertIn("文件不存在", result["problems"][0]["issues"])

    def test_zero_byte_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "empty.mp4")
            with open(f, "w") as fh:
                pass  # 0字节
            result = post_check([f])
            self.assertEqual(result["fail"], 1)
            self.assertIn("零字节文件", result["problems"][0]["issues"])

    def test_too_small_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "small.mp4")
            with open(f, "w") as fh:
                fh.write("x")  # 1字节 < 100KB
            result = post_check([f])
            self.assertEqual(result["fail"], 1)
            self.assertTrue(any("文件过小" in i for i in result["problems"][0]["issues"]))

    def test_mixed_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            f_ok = os.path.join(tmp, "good.mp4")
            f_bad = os.path.join(tmp, "bad.mp4")
            with open(f_ok, "w") as f:
                f.write("x" * 200_000)
            result = post_check([f_ok, f_bad])  # f_bad 不存在
            self.assertEqual(result["ok"], 1)
            self.assertEqual(result["fail"], 1)


class TestEstimateCost(unittest.TestCase):
    def setUp(self):
        class FakeMP:
            pass
        self.tasks = [
            TaskRecord(mp_item=FakeMP(), name="a", path="/tmp/a.mp4", kwargs={}, duration=3),
            TaskRecord(mp_item=FakeMP(), name="b", path="/tmp/b.mp4", kwargs={}, duration=30),
            TaskRecord(mp_item=FakeMP(), name="c", path="/tmp/c.mp4", kwargs={}, duration=0.5),
        ]

    def test_wuhenai_pro_box(self):
        """无痕AI sel_area: 1积分/秒，向上取整"""
        secs, pts, uc, yuan = estimate_cost(self.tasks, "pro_box")
        self.assertEqual(uc, 1)
        self.assertEqual(secs, 34)  # ceil(3)+ceil(30)+ceil(0.5) = 3+30+1
        self.assertEqual(pts, 34)
        self.assertEqual(yuan, round(34 * 0.0091, 2))

    def test_ghostcut_basic(self):
        """鬼手: 按30秒单位计费"""
        secs, pts, uc, yuan = estimate_cost(self.tasks, "basic", provider="ghostcut")
        self.assertEqual(uc, 1)
        self.assertEqual(secs, 3)  # ceil(3/30)=1 + ceil(30/30)=1 + ceil(0.5/30)=1
        self.assertEqual(pts, 3)
        self.assertEqual(yuan, round(3 * 0.19, 2))

    def test_empty_tasks(self):
        secs, pts, uc, yuan = estimate_cost([], "pro_box")
        self.assertEqual(secs, 0)
        self.assertEqual(pts, 0)
        self.assertEqual(yuan, 0.0)

    def test_single_task_rounding(self):
        """验证计费单位取整方向：1.1秒 → 2秒计费"""
        class FakeMP:
            pass
        tasks = [TaskRecord(mp_item=FakeMP(), name="x", path="/tmp/x.mp4", kwargs={}, duration=1.1)]
        secs, pts, _, _ = estimate_cost(tasks, "pro_box")
        self.assertEqual(secs, 2)  # ceil(1.1) = 2，不是 1
        self.assertEqual(pts, 2)


class TestPointToYuan(unittest.TestCase):
    def test_wuhenai(self):
        self.assertEqual(point_to_yuan(1000, "wuhenai"), 9.1)  # 1000*0.0091

    def test_ghostcut(self):
        self.assertEqual(point_to_yuan(1000, "ghostcut"), 190.0)  # 1000*0.19

    def test_zero_points(self):
        self.assertEqual(point_to_yuan(0, "wuhenai"), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
