# -*- coding: utf-8 -*-
"""`docs/PROJECT_MAP.md` 的「产物样例」必须与**真实生成物**一致。

文档里的代码块最容易腐烂：改了发射器，没人记得回去改文档。
这里用最直接的办法 —— **重新生成一遍**，断言文档里的每一行都真的出现在产物里。

两向：
1. 文档里的关键行 → 必须能在新生成的产物中找到（否则文档过期）；
2. 生成的产物里那几行 → 必须仍在文档中（否则文档漏写了）。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
PM = os.path.join(ROOT, "translate", "project_map.py")
DOC = os.path.join(ROOT, "docs", "PROJECT_MAP.md")

SRC = u"""function y = acc(x)
% @m2c shape x 4
% @m2c shape y 1
y = sum(x);
end
"""

#: 文档里承诺的、必须出现在产物中的行
WANT_F64 = [
    "st = mlc_op_sum(&x, y);",
]
WANT_Q15 = [
    "if (mlc_op_q15_from_f64(&x, &x) != MLC_OK) { return MLC_ERR; }",
    "st = mlc_op_q15_sum(&x, y);",
    "if (mlc_op_q15_to_f64(y, y) != MLC_OK) { st = MLC_ERR; }",
]
WANT_GEN_C = [
    "static double m2c_pool_buf[(4096 + 8 - 1) / 8];",
    "(void)mlc_pool_configure(m2c_pool_buf, 4096, 8);",
]
WANT_MANIFEST = [
    '#define M2C_ACCUM_PERIOD_MS 1',
    '#define M2C_MEM_POOL_BYTES 4096',
    '#define M2C_USES_OP_SUM 1',
]


def _build(fixed):
    d = tempfile.mkdtemp(prefix="m2c_doc_")
    src = os.path.join(d, "m")
    os.makedirs(src)
    io.open(os.path.join(src, "acc.m"), "w", encoding="utf-8").write(SRC)
    cfg = {"version": 2,
           "matlab": {"root": "m", "recursive": False, "exclude": []},
           "c": {"root": "gen", "project": "demo", "prefix": "m2c_",
                 "runtime": "c_runtime"},
           "targets": {"mcu": {"abi": "arm", "allow_heap": False,
                               "dtype": "q15" if fixed else "f64",
                               "memory": {"strategy": "static_pool",
                                          "pool_bytes": 4096, "alignment": 8}}},
           "modules": [{"id": "accum", "targets": ["mcu"], "sources": ["acc"],
                        "entry": "acc",
                        "timing": {"period_ms": 1, "deadline_ms": 0.8,
                                   "entry_kind": "isr"}}],
           "operators": {}, "constraints": {"forbid_heap": ["mcu"]}}
    if fixed:
        cfg["dtypes"] = {"default": "q15",
                         "fixed_point": {"format": "Q15", "frac_bits": 15,
                                         "round": "nearest", "overflow": "saturate"}}
    p = os.path.join(d, "m2c.project.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False))
    r = subprocess.run([sys.executable, PM, p, "--build"], cwd=d,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]
    return d


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
def test_doc_samples_match_generated_output():
    doc = io.open(DOC, encoding="utf-8").read()
    d_f64 = _build(False)
    d_q15 = _build(True)
    try:
        def read(p):
            return io.open(p, encoding="utf-8", errors="replace").read()

        fn64 = read(os.path.join(d_f64, "gen", "src", "gen", "acc_m.c"))
        fn15 = read(os.path.join(d_q15, "gen", "src", "gen", "acc_m.c"))
        genc = read(os.path.join(d_q15, "gen", "src", "gen.c"))

        man = os.path.join(d_q15, "m.h")
        subprocess.run([sys.executable, PM,
                        os.path.join(d_q15, "m2c.project.json"),
                        "--emit-manifest", man], cwd=d_q15,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
        man_txt = read(man)

        for line in WANT_F64:
            assert line in fn64, "产物里没有：%s" % line
            assert line in doc, "文档过期（产物有、文档没写）：%s" % line
        for line in WANT_Q15:
            assert line in fn15, "定点产物里没有：%s" % line
            assert line in doc, "文档过期：%s" % line
        for line in WANT_GEN_C:
            assert line in genc, "gen.c 里没有：%s" % line
            assert line in doc, "文档过期：%s" % line
        for line in WANT_MANIFEST:
            assert line in man_txt, "manifest 里没有：%s" % line
            assert line in doc, "文档过期：%s" % line
    finally:
        shutil.rmtree(d_f64, ignore_errors=True)
        shutil.rmtree(d_q15, ignore_errors=True)
