# -*- coding: utf-8 -*-
"""对拍门：MIR 解释器（Python）⇄ 生成的 C 程序。

## 这个工具回答的问题

"MATLAB 与 C 两边实现一致吗？" —— 在**没有 MATLAB/Octave** 的机器上，
唯一诚实的答法是：造一个**独立于 C 的第二个执行器**，让它和 C 跑同一份 MIR。

    .m ──mir.py──▶ MIR ──解释执行（Python）──▶ 参考输出
                        └──m2c──▶ C ──gcc──▶ 实际输出

两者语义实现完全不同：一个是 Python 循环，一个是 C 代码。它们一致，
只能说明"发射器 + 运行时"这一层没走样；**仍不等于 MATLAB 语义正确**。
所以本门把结论分三级写清楚，绝不把"未验证"混进"通过"。

## 三级结论

| 级别 | 含义 |
|---|---|
| **V**（已对拍） | 解释器与 C 都能算，且逐值一致 |
| **U**（未对拍） | 解释器放弃（含 unmapped 语句 / 无形状入参）—— **不知道** |
| **X**（不一致） | 两边都能算但结果不同 —— **一定是错** |

只有 X 会让门变红。U 会被**如实计数并打印**，不会被当成通过。

退出码：
    0  = 没有 PA3（可能仍有 PA2 未对拍，数字会如实显示）
    1  = 存在 PA3 不一致（两边都能算但结果不同）
    2  = 缺输入（MIR 不存在 / 找不到 C 编译器 / 生成或编译失败）
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import mir_eval  # noqa: E402

M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
GCC_CANDIDATES = [r"D:\project\MinGW-w64\bin\gcc.exe", "gcc", "cc", "clang"]


def _run(cmd, cwd=None, timeout=900):
    p = subprocess.run(cmd, cwd=cwd or ROOT, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def _cc():
    for c in GCC_CANDIDATES:
        if os.path.isfile(c) or shutil.which(c):
            return c
    return None


def _interp_lines(funcs):
    """解释执行 -> {函数名: 行文本 或 None}。"""
    res = mir_eval.run_all(funcs)
    out = {}
    for f in funcs:
        outs = res.get(f.name)
        if outs is None:
            out[f.name] = None
            continue
        parts = [" ".join("%.10g" % v for v in a.data) for a in outs]
        out[f.name] = "%s: %s" % (f.name, " | ".join(parts))
    return out


def _c_lines(text):
    """C 程序输出 -> {函数名: 行文本}（含 unimplemented / skipped）。"""
    out = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ":" not in ln:
            continue
        name = ln.split(":", 1)[0]
        out[name] = ln
    return out


def check(mir_path, expect_path=None, keep=False):
    """返回 (probs, stats)。probs 只装**真不一致**。"""
    probs = []
    text = io.open(mir_path, encoding="utf-8").read()
    funcs = mir_eval.parse(text)
    ref = _interp_lines(funcs)

    d = tempfile.mkdtemp(prefix="m2c_parity_")
    rc, out = _run([M2C, "build", "--mir", mir_path, "--out", d, "--name", "parity"])
    if rc != 0:
        return ["PARITY 生成工程失败：%s" % (out.strip().splitlines()[:2],)], {}

    cc = _cc()
    if not cc:
        return ["PARITY 没有可用 C 编译器"], {}
    rt = os.path.join(ROOT, "c_runtime")
    exe = os.path.join(d, "parity.exe" if os.name == "nt" else "parity")
    rc, out = _run([cc, "-std=c99", "-O1", "-I", os.path.join(d, "include"),
                    "-I", os.path.join(rt, "include"),
                    os.path.join(d, "src", "gen.c"),
                    os.path.join(d, "src", "main.c"),
                    os.path.join(rt, "src", "mlc_runtime.c"),
                    os.path.join(rt, "src", "mlc_ops.c"), "-o", exe])
    if rc != 0:
        return ["PARITY 编译失败：%s" % (out.strip().splitlines()[:2],)], {}

    rc, out = _run([exe], timeout=300)
    if rc != 0:
        return ["PARITY 运行失败（rc=%s）" % (rc,)], {}
    got = _c_lines(out)

    v = u = x = 0
    detail = []
    for f in funcs:
        ref_line = ref.get(f.name)
        got_line = got.get(f.name, "")
        if ref_line is None:
            u += 1
            detail.append(("U", f.name, "-", got_line))
            continue
        if got_line == ref_line:
            v += 1
        else:
            x += 1
            detail.append(("X", f.name, ref_line, got_line))

    for tag, name, want, have in detail:
        if tag == "X":
            probs.append("PARITY 不一致 %s：参考[%s] 实际[%s]"
                         % (name, want[:70], have[:70]))

    stats = {"verified": v, "unverified": u, "mismatch": x,
             "total": len(funcs), "dir": d}
    if not keep:
        shutil.rmtree(d, ignore_errors=True)
        stats["dir"] = None
    return probs, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="MIR 解释器 ⇄ C 对拍")
    ap.add_argument("--mir", required=True, help="MIR 文件路径")
    ap.add_argument("--show-unverified", type=int, default=5,
                    help="打印多少个未对拍的函数名")
    args = ap.parse_args(argv)

    probs, stats = check(args.mir)
    if not stats:
        for p in probs:
            print("  - " + p)
        return 2                     # 缺输入 / 工具故障

    # 三个前缀各自单独成行：静态判据要能在源码里"看得见"
    print("PA1 已对拍 %d" % stats["verified"])
    print("PA2 未对拍 %d（原因：含 unmapped 语句或无形状入参）"
          % stats["unverified"])
    if stats["mismatch"]:
        print("PA3 不一致 %d" % stats["mismatch"])
    print("对拍合计 %d 个函数" % stats["total"])
    if stats["unverified"]:
        names = [d[1] for d in _detail_unverified(args.mir, args.show_unverified)]
        if names:
            print("  未对拍示例：%s（原因：含 unmapped 语句或无形状入参）"
                  % "、".join(names))
    for p in probs:
        print("  - " + p)
    if probs:
        return 1                     # PA3：两边都能算但结果不同
    return 0                         # 无 PA3


def _detail_unverified(mir_path, limit):
    text = io.open(mir_path, encoding="utf-8").read()
    funcs = mir_eval.parse(text)
    ref = _interp_lines(funcs)
    return [("U", f.name, "", "") for f in funcs if ref.get(f.name) is None][:limit]


if __name__ == "__main__":
    sys.exit(main())
