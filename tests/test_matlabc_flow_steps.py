# -*- coding: utf-8 -*-
"""`matlabc_flow.py` 的**告警归类**与**流程配置加载**。

`test_matlabc_flow_entry.py` 已经守了补丁安全（计数与保源判定），这里守另外两块：

* `_tally`：把告警列表压成「规则 → 条数」。它决定补丁生成器看到什么，
  而它的失真是**静默**的（少算一条规则，生成器就少修一类）；
* `load_flow_config`：找不到配置时**回退默认五步**（不抛）—— 这既是特性也是陷阱：
  用户以为加载了自己的配置，实际跑的是默认流程，而没有任何提示。
"""
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_STEPS = ["review", "fix", "apply", "verify", "report"]


def _tally_of(alerts):
    import matlabc_flow as F

    return F._tally(alerts)


def test_tally_counts_rules_and_total():
    """规则计数与总数必须一致（总数是下游判断"进步了没有"的唯一依据）。"""
    t, n = _tally_of([{"rule": "R1"}, {"rule": "R1"}, {"rule": "R2"}])
    assert t == {"R1": 2, "R2": 1}, "规则计数不对：%r" % (t,)
    assert n == 3, "总数不对：%r" % (n,)
    assert sum(t.values()) == n, "分项之和与总数不一致：%r vs %r" % (t, n)


def test_tally_empty_is_zero_not_crash():
    """**反向**：空输入给 `({}, 0)`，不能崩、也不能给出非零。"""
    t, n = _tally_of([])
    assert t == {} and n == 0, "空输入的返回不对：%r/%r" % (t, n)


def test_tally_distinguishes_empty_rule_from_missing_rule():
    """两种"没有规则名"的输入，行为**不同** —— 而差异是本项目想要的。

    * `{"rule": ""}`（键在、值为空）→ 落进 `''` 桶并计入总数；
    * `{}`（键都不在）→ **`KeyError`**，响亮失败。

    后者正是"不猜"的体现：与其静默归到一个桶里、让下游以为有一条规则叫空字符串，
    不如当场炸出来。判据把这两条都钉住，避免有人"顺手"改成 `a.get("rule", "")`
    —— 那会让格式错误的告警**悄悄混进统计**。
    """
    import pytest                       # noqa: PLC0415

    t, n = _tally_of([{"rule": "R1"}, {"rule": ""}])
    assert n == 2, "空字符串规则名把总数算少了：%r" % (n,)
    assert t.get("") == 1, "空字符串规则名没有成桶：%r" % (t,)

    with pytest.raises(KeyError):
        _tally_of([{}])                 # 缺键：必须炸，不能静默归桶


def test_config_missing_falls_back_to_default_silently():
    """配置文件不存在时**回退默认五步**（这是特性），且第二个返回值是 bool。"""
    import matlabc_flow as F

    tmp = os.environ.get("M2C_TMP")
    d = tempfile.mkdtemp(prefix="flowcfg_",
                         dir=tmp if tmp and os.path.isdir(tmp) else None)
    try:
        steps, from_file = F.load_flow_config(os.path.join(d, "nope.json"))
        assert steps == DEFAULT_STEPS, "缺配置时没回退默认五步：%r" % (steps,)
        assert from_file is False, "缺配置时却声称来自文件：%r" % (from_file,)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_config_with_unknown_keys_still_returns_steps():
    """配置文件存在时也要给出**列表**（不是 dict），否则下游 `for s in steps` 会跑键名。"""
    import matlabc_flow as F

    tmp = os.environ.get("M2C_TMP")
    d = tempfile.mkdtemp(prefix="flowcfg_",
                         dir=tmp if tmp and os.path.isdir(tmp) else None)
    try:
        p = os.path.join(d, "flow.json")
        io.open(p, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"prefix": "AI", "max_turns": 5}))
        steps, from_file = F.load_flow_config(p)
        assert isinstance(steps, list) and steps, "没给出步骤列表：%r" % (steps,)
        assert isinstance(from_file, bool)
    finally:
        shutil.rmtree(d, ignore_errors=True)
