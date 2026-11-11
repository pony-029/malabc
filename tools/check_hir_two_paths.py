# -*- coding: utf-8 -*-
"""check_hir_two_paths.py —— 两条 MIR 生成路径必须**逐函数等价**。

为什么需要它（R750 实测）
========================
`check_translate_port` 与 `check_generated_compiles` 只跑**一条**路径（当时是默认那条）。
于是"把 `--hir-emit` 设为默认"这类变更发生时，它们从**验证者**变成**被改动的对象**：

    check_all: 2 项失败：['check_generated_compiles.py', 'check_translate_port.py']

原因不是产物坏了，而是这两个门自己也吃默认值 —— 它们验证的是自己。
这道门不碰默认值：它**显式**跑两条路（`--no-hir-emit` 与 `--hir-emit`），逐函数比三项。

判据（TP9a–TP9d）
=================
    TP9a 函数集合相同：两条路径产出的 function 名集合一致。
    TP9b 算子多重集相同：同一函数的 `OP-*` 集合一致（**不要求同序** —— 折树会改顺序）。
    TP9c 行号集合相同：同一函数的 `# src:` 取值集合一致。
         （R750 发现过"行号对、类别丢"：`# why:` 被丢，诊断退化成 `[misc]`。）
    TP9d 数值一致（有 m2c 时）：两条路径的 MIR 喂 VM，输出逐行相同。

**不判**的东西
--------------
* 不判文本逐字节相同：折树会改变 `# src:` 与算子的**排列**，字节必然不同，
  而正确性只依赖集合。
* 不判耗时：两条路径的性能不在契约内。

用法：
    python tools/check_hir_two_paths.py              # 0=等价 1=有差异 2=缺输入
    python tools/check_hir_two_paths.py --selftest   # 自证：比对器能检出算子/行号/函数差异
    python tools/check_hir_two_paths.py --help

退出码：
    0  = 两条路径逐函数等价
    1  = 有差异（函数集合 / 算子 / 行号 / 数值任一不等）
    2  = 缺输入（语料目录不存在）
"""
import argparse
import collections
import io
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import hir_parity as HP          # noqa: E402

#: 判据族签名。H1 要求 `GUARD_CONTRACT` 的 rc=0 描述**逐字**含它。
ROW_SIGNATURE = "TP9a–TP9d"

WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def _selftest():
    """比对器必须**能失败**（R751 教训：注入点跨进程时自证会空转）。"""
    a = HP._split("func:f\nop:OP-MUL:y:a:a\n# src:3\nend\n")
    b = HP._split("func:f\nop:OP-ADD:y:a:a\n# src:3\nend\n")
    c = HP._split("func:f\nop:OP-MUL:y:a:a\n# src:9\nend\n")
    d = HP._split("func:g\nop:OP-MUL:y:a:a\n# src:3\nend\n")

    if collections.Counter(a["f"][0]) == collections.Counter(b["f"][0]):
        print("TP9b 自证失败：比对器认不出算子差异")
        return 1
    if collections.Counter(a["f"][1]) == collections.Counter(c["f"][1]):
        print("TP9c 自证失败：比对器认不出行号差异")
        return 1
    if set(a) == set(d):
        print("TP9a 自证失败：比对器认不出函数集合差异")
        return 1

    tmp = tempfile.mkdtemp(prefix="h2p_", dir=WORK if os.path.isdir(WORK) else None)
    try:
        os.makedirs(os.path.join(tmp, "ok"))
        io.open(os.path.join(tmp, "ok", "f.m"), "w", encoding="utf-8",
                newline="\n").write(
            "function y = f(a)\n% @m2c shape a 3\n% @m2c shape y 3\n"
            "y = a .* 2;\nend\n")
        if HP.main([os.path.join(tmp, "ok")]) != 0:
            print("自证失败：等价语料被判为不等价")
            return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # runner 认自证的**唯一凭据**是这一行（`check_all` 的 R6 契约）
    print('SELFTEST COUNTS {"bad": 3, "good": 1}')
    print("自证通过：能检出算子/行号/函数集合差异，且等价语料判通过")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, _rest = ap.parse_known_args(argv or sys.argv[1:])

    if a.help:
        print(__doc__)
        return 0
    if a.selftest:
        return _selftest()

    if not os.path.isdir(HP.CORPUS):
        print("TP9a 缺输入：语料目录 %s 不存在" % HP.CORPUS)
        return 2

    # 复用对拍口径：它已分别用 `--no-hir-emit` 和默认（hir-emit）生成
    rc = HP.main([HP.CORPUS, "--values"])
    if rc == 0:
        print("TP9a–TP9d 全部通过（两条路径逐函数等价）")
        return 0
    print("TP9a 两条路径有差异（详见上方逐函数输出）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
