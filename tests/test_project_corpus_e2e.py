# -*- coding: utf-8 -*-
"""真实语料工程级端到端：`translate/examples/numeric`（58 个 .m）当**一个工程**跑通。

## 与 `test_project_e2e.py` 的分工

* `test_project_e2e.py`：**形状**判据 —— 多目录、两跳调用、编译单位清单。
* 本文件：**规模**判据 —— 用一个真工程（58 个函数、`m2c.project.json` 配置）
  走完整链路，确认"没有一个函数掉队"。

两跳调用在 4 文件样本上能验形状，但验不出"58 个函数里有没有几个悄悄退了"；
反过来，语料工程大部分是平铺的，验不出跨目录。所以**两个都要有**。

## 判据

* **CE1** `run_build` 成功，且产物里有 `budget.json` 与 `src/sources.txt`。
* **CE2** 按 `sources.txt` 的 `[lib]+[app]` 编译成功（不猜文件）。
* **CE3** 运行输出 **unimplemented 为 0**（任何函数掉队都会在这里现形）。
* **CE4** 抽三个不同形态的值（归约 / 循环 / 列和）与手算值对齐。
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "translate"))

M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
RT = os.path.join(ROOT, "c_runtime")
CFG = os.path.join(ROOT, "translate", "examples", "m2c.project.json")
WORK = os.environ.get("M2C_TMP")


def _run(cmd, cwd=None, timeout=900):
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


@pytest.fixture(scope="module")
def corpus():
    """构建语料工程并编译运行；返回 (输出文本, 生成根)。"""
    if not os.path.isfile(M2C):
        pytest.skip("m2c 未构建")
    if not os.path.isfile(CFG):
        pytest.skip("缺 m2c.project.json")
    cc = shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        pytest.skip("没有 C 编译器")

    import project_map as PM

    d = tempfile.mkdtemp(prefix="ce_", dir=WORK if WORK and os.path.isdir(WORK)
                         else None)
    try:
        cfg = PM.load2(CFG)
        cfg["matlab"]["root"] = os.path.join(os.path.dirname(CFG),
                                             cfg["matlab"]["root"])
        rc, _log, out = PM.run_build(cfg, d, CFG)
        assert rc == 0, "语料工程构建失败：\n%s" % out[-800:]
        gen = os.path.join(d, cfg["c"]["root"])

        # CE1
        assert os.path.isfile(os.path.join(gen, "budget.json")), "缺 budget.json"
        sp = os.path.join(gen, "src", "sources.txt")
        assert os.path.isfile(sp), "缺 src/sources.txt（不知道该编哪些文件）"

        groups, cur = {}, None
        for ln in io.open(sp, encoding="utf-8", errors="replace"):
            t = ln.strip()
            if not t or t.startswith("#"):
                continue
            if t.startswith("[") and t.endswith("]"):
                cur = t[1:-1]
                groups[cur] = []
                continue
            groups.setdefault(cur or "misc", []).append(t)
        srcs = [os.path.join(gen, u) for u in
                (groups.get("lib") or []) + (groups.get("app") or [])
                if u.endswith(".c")]
        assert srcs, "sources.txt 里没有可编译的 .c：%r" % groups

        # CE2
        exe = os.path.join(d, "ce.exe" if os.name == "nt" else "ce")
        r = _run([cc, "-std=c99", "-O1",
                  "-I", os.path.join(gen, "include"),
                  "-I", os.path.join(RT, "include")] + srcs +
                 [os.path.join(RT, "src", "mlc_runtime.c"),
                  os.path.join(RT, "src", "mlc_ops.c"), "-o", exe], timeout=900)
        assert r.returncode == 0, \
            "按清单编译失败：\n%s" % r.stdout.decode("utf-8", "replace")[-800:]

        outp = _run([exe], timeout=180).stdout.decode("utf-8", "replace")
        yield outp, gen
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_ce3_no_unimplemented(corpus):
    """CE3：任何函数掉队都会以 `unimplemented` 出现在输出里。"""
    out, _gen = corpus
    bad = [l.strip() for l in out.splitlines() if "unimplemented" in l]
    assert not bad, "%d 个函数未实现：%r" % (len(bad), bad[:5])


def test_ce4_spot_values(corpus):
    """CE4：三个不同形态各抽一个，数值必须与手算一致。"""
    out, _gen = corpus
    got = {}
    for ln in out.splitlines():
        if ":" in ln:
            k, _, v = ln.partition(":")
            got[k.strip()] = " ".join(v.split())
    expect = {
        "above": "3 4 5",        # 谓词/筛选
        "colmax_loop": "6",      # 显式循环 + 下标
        "col2sum": "12",         # 二维列求和
    }
    for k, want in expect.items():
        assert k in got, "输出里没有 %s：%r" % (k, sorted(got)[:8])
        assert got[k] == want, "%s 得 %r，期望 %r" % (k, got[k], want)
