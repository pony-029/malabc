# -*- coding: utf-8 -*-
"""HIR 是否**真的在主链上** —— 这是"融合度"的唯一硬判据。

## 为什么需要这条

在 R734 之前，`hir.py` 只被 `tests/` 与 `tools/hir_links_report.py` 调用，
而 `translate/mir.py`（唯一的生产入口）里**一次都没提到 hir**。
也就是说：图上写着 `MATLAB → HIR → MIR`，代码里却是 `MATLAB → MIR`，HIR 只是旁路校验。

现在 `mir.py --via-hir` 会在每次生成后强制走一遍 `MIR → HIR → MIR`，
算子多重集不等即退出码 1。这条判据守两件事：

1. **接管率**：语料里有多少函数真的能走 HIR（不能悄悄退化成 0）；
2. **恒等率**：接管之后必须**每个都恒等**（不能"接了但改了内容"）。
"""
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def _run_via_hir():
    out = os.path.join(WORK, "via_hir.mir")
    r = subprocess.run([sys.executable, MIR_PY, CORPUS, "--via-hir", "-o", out],
                       stdin=subprocess.DEVNULL, timeout=300,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def test_via_hir_passes_on_corpus():
    """`mir.py --via-hir` 必须在语料上通过（退出码 0，无失配）。"""
    rc, out = _run_via_hir()
    assert rc == 0, "HIR 校验失败：%s" % out[-500:]
    assert "失配" not in out, out[-500:]


def test_via_hir_really_participates():
    """接管率不能悄悄掉到 0 —— 否则"通过"是假的。

    语料里 57 个函数带算子（1 个是空函数）。要求至少 50 个能走 HIR：
    剩下的是含 `OP-FIND2/FIND3` 等尚无 HIR 名的算子，属已知缺口。
    """
    rc, out = _run_via_hir()
    m = re.search(r"\[hir\] 接管 (\d+)/(\d+)（恒等 (\d+)）", out)
    assert m, "没看到 [hir] 汇总行：%s" % out[-400:]
    mapped, total, same = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # R741 起补全了 `search.find2/find3` 的 HIR 名，接管率应为 **100%**。
    # 早前是 `>= 50`（留了两个已知缺口）；现在收紧到"一个都不能少"，
    # 否则将来新增算子缺名时会悄悄退回 55。
    assert mapped == total, "接管率不足：%d/%d（有新算子缺 HIR 名？）" % (mapped, total)
    assert same == mapped, "接管了但不恒等：same=%d mapped=%d" % (same, mapped)


def test_default_path_has_no_hir_side_effect():
    """不加 `--via-hir` 时，输出里不该出现 [hir] 行（默认零额外开销）。"""
    out_path = os.path.join(WORK, "no_hir.mir")
    r = subprocess.run([sys.executable, MIR_PY, CORPUS, "-o", out_path],
                       stdin=subprocess.DEVNULL, timeout=300,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace")
    assert r.returncode == 0, out[-300:]
    assert "[hir]" not in out, "默认路径不应触发 HIR 校验"


def test_status_snapshot_is_fresh():
    """`flow/hir_status.json`（首页数字的来源）必须与**当前实跑**一致。

    没有这条，首页会显示一个曾经正确的数字 —— 那比不显示更糟：
    读者会以为它反映的是现在的代码。
    """
    import io as _io
    import json
    import re as _re
    p = os.path.join(ROOT, "flow", "hir_status.json")
    assert os.path.isfile(p), "缺 flow/hir_status.json（跑 tools/hir_status.py）"
    old = json.load(_io.open(p, encoding="utf-8"))
    rc, out = _run_via_hir()
    m = _re.search(r"\[hir\] 接管 (\d+)/(\d+)（恒等 (\d+)）", out)
    assert m, out[-300:]
    now = {"mapped": int(m.group(1)), "total": int(m.group(2)),
           "identical": int(m.group(3))}
    assert all(old.get(k) == now[k] for k in now), \
        "快照过期：文件 %r vs 实跑 %r" % (old, now)
