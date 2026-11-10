# -*- coding: utf-8 -*-
"""`--hir-emit` 必须保住**两类元数据注释**：`# src:` 与 `# why:`。

## 为什么这条单独存在

R750 切默认时抓到过一次真实回归：

    行号全对（第 156/157/143/144 行一致）
    但类别退化了：[cell] → [misc]，[cond] → [misc]，[shadowed] → [misc]

原因是 `hir_emit` 只保留了 `# src:`，把 `# why:` 丢了 —— 而 `check` 靠 `# why:`
把卡点分成 cell / cond / shadowed / strlit 等类别。**行号还在，诊断已经不可行动。**

之前只有"行号覆盖率"一条判据（`test_hir_srcline`），它对这个回归完全无感。
"""
import io
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def _gen(extra, name, src_dir=None):
    out = os.path.join(WORK, name)
    r = subprocess.run([sys.executable, MIR_PY, src_dir or CORPUS] + extra + ["-o", out],
                       stdin=subprocess.DEVNULL, timeout=300,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-300:]
    return io.open(out, encoding="utf-8").read()


#: 需要一段**会产生 `# why:`** 的语料 —— 纯数值语料全是可映射语句，
#: 一个 `# why:` 都不会有（第一版就是这么误判的：n_base=0，判据自己失效）。
_UNSUPPORTED = u"""function y = hasunmapped(a)
% @m2c shape a 3
% @m2c shape y 3
y = a;
q = undefined_helper(a);
r = a + q;
y = r(1);
end
"""


@pytest.fixture(scope="module")
def texts():
    """在**含 `# why:` 的临时语料**上取两条路径的 MIR 文本。"""
    import shutil
    import tempfile

    d = tempfile.mkdtemp(prefix="meta_", dir=WORK if os.path.isdir(WORK) else None)
    try:
        src = os.path.join(d, "src")
        os.makedirs(src)
        io.open(os.path.join(src, "plain.m"), "w", encoding="utf-8",
                newline="\n").write("function y = plain(a)\n% @m2c shape a 3\n"
                                    "% @m2c shape y 3\ny = a .* 2;\nend\n")
        io.open(os.path.join(src, "hasunmapped.m"), "w", encoding="utf-8",
                newline="\n").write(_UNSUPPORTED)
        # 基准必须**显式**关掉 HIR 产出（默认可能已开启）
        yield (_gen(["--no-hir-emit"], "meta_base.mir", src),
               _gen(["--hir-emit"], "meta_he.mir", src))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_src_lines_preserved(texts):
    base, he = texts
    assert base.count("# src:") > 0
    assert he.count("# src:") == base.count("# src:"), \
        "行号丢失：%d → %d" % (base.count("# src:"), he.count("# src:"))


def test_why_lines_preserved(texts):
    """`# why:` 是卡点类别标签 —— 丢了它，诊断全退化成 `[misc]`。"""
    base, he = texts
    n_base = base.count("# why:")
    n_he = he.count("# why:")
    assert n_base > 0, "语料里没有 # why 行？（判据失效）"
    assert n_he == n_base, \
        "卡点类别标签丢失：%d → %d（诊断会退化成 [misc]）" % (n_base, n_he)
