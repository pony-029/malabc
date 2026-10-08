# -*- coding: utf-8 -*-
"""P0-2 评测闭环的 CI 门禁测试：断言关键指标全绿（离线、零依赖）。

扩面要求（本测试强制）：
  · 必须覆盖真实 MATLAB 语料场景（uninit_real，门禁在 tests/sample_m 非空语料上验证）；
  · 必须覆盖多缺陷类（至少含 dead_code 这类确定性引擎可修类）；
  · 关键质量指标必须全绿，任一不达标即失败，CI 拦截回归。
"""
import os
import sys
import io
import json
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import eval_ai_fix  # noqa: E402


class TestAiFixEval(unittest.TestCase):
    def test_eval_metrics_green(self):
        m = eval_ai_fix.run_eval()
        cases = {d.get("case") for d in m["details"]}
        # 扩面强制：真实语料场景 + 死代码类必须参与评测
        self.assertIn("uninit_real", cases,
                      "P0-2 扩面：必须包含真实 sample_m 语料门禁场景")
        self.assertIn("dead_code_toy", cases,
                      "P0-2 扩面：必须覆盖 dead_code 这类确定性可修缺陷类")
        # 若死代码被检测到，则确定性引擎必须端到端删除它（强约束，非空泛）
        dc = next((d for d in m["details"] if d.get("case") == "dead_code_toy"), None)
        if dc and dc.get("result") == "OK":
            self.assertEqual(dc.get("engine_fixed"), True,
                             "dead_code 必须被确定性引擎端到端删除")
        # 关键指标必须全绿；任一不达标即失败，CI 拦截回归
        self.assertEqual(m["fix_success_rate"], 1.0,
                         "好补丁必须恢复基线（门禁放行 + 对账正确）")
        self.assertEqual(m["bad_fix_caught_rate"], 1.0,
                         "坏补丁必须被门禁捕获（'告警不增'壁垒不可削弱）")
        self.assertEqual(m["auto_fix_engine_ok"], True,
                         "确定性引擎必须端到端修掉注入缺陷")
        self.assertGreaterEqual(m["alarm_net_reduction"], 1.0,
                                "好补丁应完全消除注入缺陷告警")

    def test_provider_smoke_default_skipped(self):
        # 无 provider 环境变量时，冒烟应优雅跳过（不报错、不影响门禁）
        m = eval_ai_fix.run_eval()
        self.assertIn("SKIPPED", str(m["ai_provider_smoke"]))


if __name__ == "__main__":
    m = eval_ai_fix.run_eval()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "eval_ai_fix_report.json")
    with io.open(out, "w", encoding="utf-8") as fh:
        json.dump(m, fh, ensure_ascii=False, indent=2)
    print(json.dumps(m, ensure_ascii=False, indent=2))
