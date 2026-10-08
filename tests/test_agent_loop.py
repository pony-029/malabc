# -*- coding: utf-8 -*-
"""P0：受控自校验 Agent Loop 的单元门禁测试（离线、零 subprocess）。

通过 monkeypatch 掉 analyze / count_alerts / 补丁落盘，聚焦验证四类核心契约：
  · 收敛(accept)：修复后总量下降且各规则不增 → tier 1 / exit 0；
  · 已干净(already_clean)：基线 0 告警 → 直接收敛 tier 0 / exit 0；
  · 无策略(no_strategy)：修复源返回 None → 产出检查点 tier 2 / exit 2；
  · 回退(revert)：验证不通过必须回退基线，且不保留半截改动。
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import agent_loop  # noqa: E402
import matlabc_flow  # noqa: E402


def _install_mocks(baseline_by, baseline_total, after_by, after_total):
    """替换 analyze/count_alerts 与补丁落盘，避免 subprocess 与真实文件改动。"""
    matlabc_flow.analyze = lambda d, lang=None: "/tmp/_fake_report.json"
    state = {"idx": 0}

    def fake_count(path):
        if state["idx"] == 0:
            state["idx"] = 1
            return dict(baseline_by), baseline_total
        return dict(after_by), after_total

    matlabc_flow.count_alerts = fake_count
    # 不触碰真实文件：应用视为成功，回退为空操作
    agent_loop._apply_with_git = lambda p, d: True
    agent_loop._revert_with_git = lambda p, d: None
    agent_loop._apply_internal = lambda p, d: {}
    agent_loop._revert_internal = lambda snap, d: None
    return state


class TestAgentLoop(unittest.TestCase):
    def test_converge_accepts_and_reduces(self):
        _install_mocks({"uninit": 5}, 5, {"uninit": 2}, 2)
        calls = {"n": 0}

        def fix_source(attempt, feedback):
            calls["n"] += 1
            if attempt == 0:
                return "--- a/x.m\n+++ b/x.m\n@@ -1 +1 @@\n- old\n+ new\n"
            return None

        res = agent_loop.run_fix_loop("/tmp/fake_proj", fix_source, max_turns=3)
        self.assertTrue(res["result"]["accepted"])
        self.assertEqual(res["result"]["tier"], 1)
        self.assertEqual(res["result"]["final_total"], 2)
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["termination"]["reason"], "converged")
        self.assertTrue(res["result"]["checkpoint"] is None)

    def test_already_clean(self):
        _install_mocks({}, 0, {}, 0)

        def fix_source(attempt, feedback):
            return "--- a/x.m\n+++ b/x.m\n@@ -1 +1 @@\n- old\n+ new\n"

        res = agent_loop.run_fix_loop("/tmp/fake_proj", fix_source, max_turns=3)
        self.assertTrue(res["result"]["accepted"])
        self.assertEqual(res["result"]["tier"], 0)
        self.assertEqual(res["termination"]["reason"], "already_clean")
        self.assertEqual(res["exit_code"], 0)

    def test_no_strategy_produces_checkpoint(self):
        _install_mocks({"uninit": 5}, 5, {"uninit": 5}, 5)

        def fix_source(attempt, feedback):
            return None  # 无确定性可修复项

        res = agent_loop.run_fix_loop("/tmp/fake_proj", fix_source, max_turns=3)
        self.assertFalse(res["result"]["accepted"])
        self.assertEqual(res["result"]["tier"], 2)
        self.assertEqual(res["termination"]["reason"], "no_strategy")
        self.assertEqual(res["exit_code"], 2)
        cp = res["result"]["checkpoint"]
        self.assertIsNotNone(cp)
        self.assertEqual(cp["has_candidate"], False)

    def test_revert_on_new_alert(self):
        # 修复后总量反而上升 → 验证不通过，必须回退并终止（不保留半截改动）
        _install_mocks({"uninit": 3}, 3, {"uninit": 4}, 4)
        applied = {"ok": False}

        def fix_source(attempt, feedback):
            if attempt == 0:
                return "--- a/x.m\n+++ b/x.m\n@@ -1 +1 @@\n- old\n+ new\n"
            return None

        # 记录是否被调用（noop 应用路径），重点验证回退后不 accepted
        res = agent_loop.run_fix_loop("/tmp/fake_proj", fix_source, max_turns=3)
        self.assertFalse(res["result"]["accepted"])
        self.assertEqual(res["termination"]["reason"], "no_strategy")
        self.assertEqual(res["result"]["final_total"], 3)  # 回到基线
        # 验证轮次记录了 revert 判定
        self.assertEqual(res["turns"][0]["verdict"], "revert")

    def test_max_turns_exhausted(self):
        # 每轮都产生「安全但无进展」补丁（总量不变）→ 穷尽 max_turns
        _install_mocks({"uninit": 3}, 3, {"uninit": 3}, 3)

        def fix_source(attempt, feedback):
            return "--- a/x.m\n+++ b/x.m\n@@ -1 +1 @@\n- old\n+ new\n"

        res = agent_loop.run_fix_loop("/tmp/fake_proj", fix_source, max_turns=2)
        self.assertFalse(res["result"]["accepted"])
        self.assertEqual(res["termination"]["reason"], "max_turns")
        self.assertEqual(res["termination"]["turns_used"], 2)
        self.assertEqual(len(res["turns"]), 2)

    def test_deterministic_empty_falls_back_to_llm(self):
        # P0+：确定性引擎无解（返回空）→ 首轮直接走 LLM，且 LLM 补丁使总量下降 → 收敛
        _install_mocks({"uninit": 5}, 5, {"uninit": 2}, 2)
        calls = {"llm": 0}
        matlabc_flow.gen_patch = lambda d, prefix, lang=None: ""  # 确定性无解

        def fake_llm(directory, feedback, provider, lang=None, config_path=None):
            calls["llm"] += 1
            return "--- a/x.m\n+++ b/x.m\n@@ -1 +1 @@\n- old\n+ new\n"

        matlabc_flow.gen_llm_patch = fake_llm
        fix_source = matlabc_flow._loop_fix_source(
            "/tmp/fake_proj", "/tmp/fp", None, "deepseek", None)
        res = agent_loop.run_fix_loop("/tmp/fake_proj", fix_source, max_turns=3)
        self.assertEqual(calls["llm"], 1)  # LLM 仅被调用一次即收敛
        self.assertTrue(res["result"]["accepted"])
        self.assertEqual(res["termination"]["reason"], "converged")

    def test_llm_iterates_across_attempts(self):
        # P0+：LLM 首轮补丁验证失败（告警反增）→ 回退 → 次轮 LLM 再生成并收敛
        matlabc_flow.analyze = lambda d, lang=None: "/tmp/_fake_report.json"
        seq = [({"uninit": 5}, 5), ({"uninit": 7}, 7), ({"uninit": 2}, 2)]
        it = {"i": 0}

        def fake_count(path):
            by, tot = seq[min(it["i"], len(seq) - 1)]
            it["i"] += 1
            return by, tot

        matlabc_flow.count_alerts = fake_count
        agent_loop._apply_with_git = lambda p, d: True
        agent_loop._revert_with_git = lambda p, d: None
        agent_loop._apply_internal = lambda p, d: {}
        agent_loop._revert_internal = lambda s, d: None
        matlabc_flow.gen_patch = lambda d, prefix, lang=None: ""
        state = {"n": 0}

        def fake_llm(directory, feedback, provider, lang=None, config_path=None):
            state["n"] += 1
            return "--- a/x.m\n+++ b/x.m\n@@ -1 +1 @@\n- old\n+ new\n"

        matlabc_flow.gen_llm_patch = fake_llm
        fix_source = matlabc_flow._loop_fix_source(
            "/tmp/fake_proj", "/tmp/fp", None, "deepseek", None)
        res = agent_loop.run_fix_loop("/tmp/fake_proj", fix_source, max_turns=3)
        self.assertGreaterEqual(state["n"], 2)  # LLM 至少被调用两次（反馈驱动迭代）
        self.assertTrue(res["result"]["accepted"])
        self.assertEqual(res["termination"]["reason"], "converged")
        self.assertEqual(res["turns"][0]["verdict"], "revert")
        self.assertEqual(res["turns"][1]["verdict"], "accept")

    def test_feedback_injects_rejected_patch_on_apply_rejected(self):
        # P1-A：首轮 LLM 补丁被应用拒绝 → 反馈含被拒补丁 + 原因 → 次轮 LLM 收到
        matlabc_flow.analyze = lambda d, lang=None: "/tmp/_fake_report.json"
        seq = [({"uninit": 5}, 5), ({"uninit": 5}, 5), ({"uninit": 2}, 2)]
        it = {"i": 0}

        def fake_count(path):
            by, tot = seq[min(it["i"], len(seq) - 1)]
            it["i"] += 1
            return by, tot

        matlabc_flow.count_alerts = fake_count
        agent_loop._is_git_repo = lambda d: True  # 走 git apply 路径以触发 apply_rejected
        agent_loop._apply_with_git = lambda p, d: False  # 始终拒绝应用
        agent_loop._revert_with_git = lambda p, d: None
        agent_loop._apply_internal = lambda p, d: {}
        agent_loop._revert_internal = lambda s, d: None
        matlabc_flow.gen_patch = lambda d, prefix, lang=None: ""
        captured = {"calls": []}

        def fake_llm(directory, feedback, provider, lang=None, config_path=None):
            captured["calls"].append(feedback)
            return "--- a/x.m\n+++ b/x.m\n@@ -1 +1 @@\n- old\n+ new\n"

        matlabc_flow.gen_llm_patch = fake_llm
        fix_source = matlabc_flow._loop_fix_source(
            "/tmp/fp2", "/tmp/fp", None, "deepseek", None)
        agent_loop.run_fix_loop("/tmp/fake_proj", fix_source, max_turns=3)
        self.assertGreaterEqual(len(captured["calls"]), 2)
        fb = captured["calls"][1]  # 第二次 LLM 调用应携带首轮被拒反馈
        self.assertEqual(fb["reason"], "apply_rejected")
        self.assertIn("rejected_patch", fb)
        self.assertTrue(fb["rejected_patch"])  # 被拒补丁全文被回灌

    def test_feedback_on_verify_failure_injects_reason_and_patch(self):
        # P1-A：验证失败（告警反增）回退 → 反馈含 verification_failed + 被拒补丁
        _install_mocks({"uninit": 5}, 5, {"uninit": 7}, 7)
        agent_loop._apply_with_git = lambda p, d: True
        agent_loop._revert_with_git = lambda p, d: None
        agent_loop._apply_internal = lambda p, d: {}
        agent_loop._revert_internal = lambda s, d: None
        matlabc_flow.gen_patch = lambda d, prefix, lang=None: ""
        captured = {"calls": []}

        def fake_llm(directory, feedback, provider, lang=None, config_path=None):
            captured["calls"].append(feedback)
            return "--- a/x.m\n+++ b/x.m\n@@ -1 +1 @@\n- old\n+ new\n"

        matlabc_flow.gen_llm_patch = fake_llm
        fix_source = matlabc_flow._loop_fix_source(
            "/tmp/fp3", "/tmp/fp", None, "deepseek", None)
        agent_loop.run_fix_loop("/tmp/fake_proj", fix_source, max_turns=2)
        self.assertGreaterEqual(len(captured["calls"]), 2)
        fb = captured["calls"][1]
        self.assertEqual(fb["reason"], "verification_failed")
        self.assertFalse(fb["no_new_alerts"])
        self.assertIn("rejected_patch", fb)

    def test_memory_records_and_looks_up(self):
        # P1-C：闭环收敛后把已验证修复记入 learned_fixes；且能检索到预置的同分布修复
        import analyzer_memory as am
        import tempfile

        proj = tempfile.mkdtemp()
        _install_mocks({"uninit": 3}, 3, {"uninit": 1}, 1)  # 3 → 1 收敛
        sig = am.signature_of({"uninit": 3})
        am.record_learned_fix(proj, {"signature": sig, "ts": "2020"})  # 预置历史修复
        res = agent_loop.run_fix_loop(
            proj,
            lambda a, f: "--- a/x.m\n+++ b/x.m\n@@ -1 +1 @@\n- old\n+ new\n",
            max_turns=3, project_root=proj, use_memory=True)
        self.assertTrue(res["result"]["accepted"])
        self.assertTrue(res["result"]["learned_fix_available"])  # 预置命中
        self.assertTrue(res["result"]["learned_fix_recorded"])  # 收敛后记录
        # 同签名去重：预置 + 本次记录仍只算 1 条
        self.assertEqual(am.learned_fix_count(proj), 1)
        self.assertIsNotNone(am.lookup_learned_fix(proj, sig))

    def test_memory_off_by_default(self):
        # 不开 use_memory 时不应触碰项目记忆
        import analyzer_memory as am
        import tempfile

        proj = tempfile.mkdtemp()
        _install_mocks({"uninit": 3}, 3, {"uninit": 1}, 1)
        res = agent_loop.run_fix_loop(
            proj,
            lambda a, f: "--- a/x.m\n+++ b/x.m\n@@ -1 +1 @@\n- old\n+ new\n",
            max_turns=3, project_root=proj, use_memory=False)
        self.assertTrue(res["result"]["accepted"])
        self.assertFalse(res["result"]["learned_fix_recorded"])
        self.assertEqual(am.learned_fix_count(proj), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
