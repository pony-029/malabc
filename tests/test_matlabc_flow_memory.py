# -*- coding: utf-8 -*-
"""`matlabc_flow.apply_memory`：**按记忆抑制已知误报**。

这层的危险方向是"抑制得太多" —— 它一旦误抑制，真实告警就永远不再出现在
修复流程里，而且**没有任何现象**（报告变短了，看起来像"修好了"）。

所以四条判据里两条是反向的：不匹配的抑制项不能生效、坏记忆文件不能生效。
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

MEM_REL = os.path.join(".codebuddy", "analyzer", "memory.json")


def _project(mem=None):
    """造一个工程；`mem` 不为 None 时写入记忆文件（字符串按原样写）。"""
    tmp = os.environ.get("M2C_TMP")
    d = tempfile.mkdtemp(prefix="mem_",
                         dir=tmp if tmp and os.path.isdir(tmp) else None)
    if mem is not None:
        p = os.path.join(d, MEM_REL)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(mem)
    return d


ALERTS = [{"rule": "R1", "file": "a.m", "line": 3},
          {"rule": "R2", "file": "b.m", "line": 9}]


def test_no_memory_passes_everything_through():
    """没有记忆文件 → 原样返回、被抑制为空，**且不写盘**。"""
    import matlabc_flow as F

    d = _project()
    try:
        kept, dropped = F.apply_memory(d, ALERTS)
        assert len(kept) == 2, "无记忆却丢了告警：%r" % (kept,)
        assert dropped == [], "无记忆却声称抑制了：%r" % (dropped,)
        assert not os.path.exists(os.path.join(d, MEM_REL)), \
            "只读路径却创建了记忆文件"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_matching_suppression_is_dropped():
    """记忆里匹配的那条被抑制，其余保留，且被抑制清单里就是它。"""
    import matlabc_flow as F

    mem = ('{"suppressions": [{"rule": "R1", "file": "a.m", "line": 3}],'
           ' "learned_fixes": []}')
    d = _project(mem)
    try:
        kept, dropped = F.apply_memory(d, ALERTS)
        assert len(dropped) == 1, "匹配的抑制项没生效：%r" % (dropped,)
        assert dropped[0].get("rule") == "R1" and dropped[0].get("line") == 3, \
            "被抑制的不是那一条：%r" % (dropped[0],)
        assert len(kept) == 1 and kept[0].get("rule") == "R2", \
            "其余告警被一起丢了：%r" % (kept,)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_non_matching_suppression_suppresses_nothing():
    """**反向**：行号不同的抑制项不能生效（否则会误杀真实告警）。"""
    import matlabc_flow as F

    mem = ('{"suppressions": [{"rule": "R1", "file": "a.m", "line": 4}],'
           ' "learned_fixes": []}')
    d = _project(mem)
    try:
        kept, dropped = F.apply_memory(d, ALERTS)
        assert dropped == [], "行号不同的抑制项竟然生效：%r" % (dropped,)
        assert len(kept) == 2, "误抑制导致告警变少：%r" % (kept,)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_corrupt_memory_is_ignored_not_fatal():
    """**坏记忆文件**（非 JSON）→ 原样返回、不崩。

    这是有意的容错（`apply_memory` 用 `except Exception` 兜住整段）：
    记忆文件坏了不该让整个修复流程停摆。但代价是它**不会告诉你**记忆失效了，
    所以这条判据的名字要写清"被忽略"，而不是"正常"。
    """
    import matlabc_flow as F

    d = _project("{ 这不是 json")
    try:
        kept, dropped = F.apply_memory(d, ALERTS)
        assert len(kept) == 2 and dropped == [], \
            "坏记忆文件影响了结果（应原样放行）：%r/%r" % (kept, dropped)
    finally:
        shutil.rmtree(d, ignore_errors=True)
