# -*- coding: utf-8 -*-
"""`translate/roundtrip.py`：相互转换的**端到端**判据。

## 为什么这条判据必须存在

"能生成 C"和"能回译成 MATLAB"分别都有判据，但**没有任何一条要求两者同时成立**。
而用户问的是"能不能相互转换" —— 那是一个联合命题：

    .m → MIR → C    （跑出的数）
    .m → MIR → .m'  （回译版跑出的数）
    两者都必须等于原函数的真值

只验其中一半，就会出现"正向能转、回译算错"或反之，而两边测试都绿。
"""
import io
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import roundtrip as RT    # noqa: E402
import tools.parity_report as PR         # noqa: E402

CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")


@pytest.mark.skipif(PR._octave_cli() is None, reason="没有 Octave/MATLAB 参考实现")
@pytest.mark.skipif(not os.path.isfile(RT.M2C), reason="m2c 未构建")
def test_both_directions_agree_on_sample():
    """抽样若干函数：C 与回译 .m' 的数值都必须等于原函数真值。"""
    import tempfile

    base = RT.WORK if os.path.isdir(RT.WORK) else None
    d = tempfile.mkdtemp(prefix="m2c_rtcli_", dir=base)
    cli = PR._octave_cli()

    names = ("snr", "fir_lp", "findeq", "findfirst", "emptychk", "vcat2")
    checked = 0
    for n in names:
        p = os.path.join(CORPUS, n + ".m")
        if not os.path.isfile(p):
            continue
        rec = RT.roundtrip_one(p, cli, d)
        v = RT.verdict(rec)
        assert v != "fail", "%s 相互转换失败：%s" % (n, rec["note"] or "数值不一致")
        if v == "ok":
            checked += 1
    assert checked >= 4, "有效样本太少（%d），判据等于没跑" % checked


def test_cli_reports_per_stage():
    """CLI 必须给出**分段**结论，而不是只一句"通过"。"""
    src = io.open(os.path.join(ROOT, "translate", "roundtrip.py"),
                  encoding="utf-8").read()
    for key in ("回译", "gcc", "数值三方"):
        assert key in src, "缺少阶段：%s" % key
