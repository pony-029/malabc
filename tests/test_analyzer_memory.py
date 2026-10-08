# -*- coding: utf-8 -*-
"""analyzer_memory 单元测试：跨运行记忆（误报抑制 + learned_fixes 缓存）。"""
import os
import tempfile
import unittest

import analyzer_memory as am


class TestAnalyzerMemory(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_load_empty_when_no_file(self):
        m = am.load_memory(self.root)
        self.assertEqual(m["suppressions"], [])
        self.assertEqual(m["learned_fixes"], [])

    def test_suppress_alerts(self):
        mem = {"suppressions": [{"rule": "uninit", "rel": "a.m", "line": 10}],
               "learned_fixes": []}
        alerts = [
            {"rule": "uninit", "rel": "a.m", "line": 10, "msg": "x"},
            {"rule": "uninit", "rel": "a.m", "line": 20, "msg": "y"},
        ]
        kept, dropped = am.suppress_alerts(alerts, mem)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped[0]["line"], 10)

    def test_add_suppression_dedup(self):
        self.assertTrue(am.add_suppression(self.root, "uninit", "a.m", 10))
        self.assertFalse(am.add_suppression(self.root, "uninit", "a.m", 10))  # 重复
        self.assertEqual(am.suppression_count(self.root), 1)

    def test_record_and_lookup_learned_fix(self):
        sig = am.signature_of({"uninit": 3})
        rec = {"signature": sig, "baseline_by_rule": {"uninit": 3},
               "files": ["a.m"], "patch_bytes": 10, "rule_reduction": 3,
               "ts": "2026-01-01T00:00:00Z"}
        self.assertTrue(am.record_learned_fix(self.root, rec))
        found = am.lookup_learned_fix(self.root, sig)
        self.assertIsNotNone(found)
        self.assertEqual(found["rule_reduction"], 3)
        self.assertEqual(am.learned_fix_count(self.root), 1)

    def test_record_dedup_same_signature(self):
        sig = am.signature_of({"uninit": 3})
        am.record_learned_fix(self.root, {"signature": sig, "ts": "t1"})
        am.record_learned_fix(self.root, {"signature": sig, "ts": "t2"})
        # 同签名去重，仅保留最新
        self.assertEqual(am.learned_fix_count(self.root), 1)
        self.assertEqual(am.lookup_learned_fix(self.root, sig)["ts"], "t2")

    def test_lookup_miss_returns_none(self):
        self.assertIsNone(am.lookup_learned_fix(self.root, '{"uninit": 99}'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
