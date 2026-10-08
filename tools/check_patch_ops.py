# -*- coding: utf-8 -*-
"""登记制静态护栏：确定性补丁引擎的「编辑算子」唯一事实源（D-P0-1）。

背景（真实缺陷，已实测复现）：
    `_build_apply_patch` 生产侧曾发出遗留算子 "ins"，而渲染侧把它实现为
    `_new[_idx] = payload` —— **覆盖目标行**。其后果是 `<var> = [];`
    顶掉了原本的读取行，**整条源码语句被删除**（实测 `y = q + n;` 消失），
    而 verify 自证门只比对告警条数（1→0）仍然报 PASS。

本护栏把「修复点」变成可静态求值的判据，共三条：
    G1 生产侧发出的算子集合 ⊆ {del, ins_before}；显式禁止遗留 "ins"。
    G2 渲染侧对 `_new[_idx]` 的赋值只允许 `None`（del 标记），
      不得出现任何「覆盖为字符串/表达式」的形式。
    G3 渲染侧必须存在对未知算子的**显式失败**分支（raise），
       否则未知算子会被静默忽略或静默覆盖。

用法：
    python tools/check_patch_ops.py            # 检查仓库，0=干净 1=有违规 2=缺输入
    python tools/check_patch_ops.py --selftest # 两向自证
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys

PROD_RE = re.compile(
    r"_edits\.setdefault\([^)]*\)\.append\(\s*\(\s*[\"']([A-Za-z_]+)[\"']")
# 只匹配「以 _new[_idx] 为左值的赋值」，右值若是 None 则为合法的删除标记
OVERWRITE_RE = re.compile(r"^[ \t]*_new\[_idx\][ \t]*=[ \t]*([^\n=].*?)[ \t]*$",
                          re.M)
RAISE_RE = re.compile(r"\braise\s+\w*Error\b")
FUNC_RE = re.compile(r"^def _build_apply_patch\(", re.M)
NEXT_DEF_RE = re.compile(r"^def ", re.M)

ALLOWED_OPS = {"del", "ins_before"}


def extract_function(src: str, name: str) -> str:
    """截取模块级函数体（到下一个顶格 `def ` 为止）。找不到返回 ""。"""
    m = re.search(r"^def %s\(" % re.escape(name), src, re.M)
    if not m:
        return ""
    nxt = NEXT_DEF_RE.search(src, m.end())
    return src[m.start():nxt.start() if nxt else len(src)]


def audit_source(src: str) -> list[str]:
    """返回问题列表（空 = 干净）。纯函数，便于自证与夹具注入。"""
    probs: list[str] = []
    body = extract_function(src, "_build_apply_patch")
    if not body:
        return ["G0 找不到 _build_apply_patch（缺输入，不得视为通过）"]

    # G1 生产侧算子集合
    ops = set(PROD_RE.findall(body))
    if not ops:
        probs.append("G1 未解析出任何编辑算子生产点（缺输入，不得视为通过）")
    bad = sorted(ops - ALLOWED_OPS)
    if bad:
        probs.append("G1 生产侧发出未登记算子 %s（允许集 %s）；"
                     "遗留 'ins' 会被渲染成覆盖目标行并删除源码语句"
                     % (bad, sorted(ALLOWED_OPS)))

    # G2 _new[_idx] 覆盖语义
    for m in OVERWRITE_RE.finditer(body):
        # 去掉尾随注释再比对，否则 `_new[_idx] = None  # 标记删除` 会被误判为
        # 非 None 右值（本护栏首跑即被自己的 --selftest 抓到，见 4g 纪律）。
        rhs = m.group(1).split("#", 1)[0].strip()
        if rhs != "None":
            probs.append("G2 检测到覆盖式赋值 `_new[_idx] = %s`（只允许 None）"
                         % rhs[:60])

    # G3 未知算子必须显式失败
    if not RAISE_RE.search(body):
        probs.append("G3 渲染侧缺少对未知算子的显式失败分支（raise）——"
                     "未知算子会被静默处理")
    return probs


def _repo_source() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(os.path.dirname(here), "matlabc.py")
    if not os.path.exists(p):
        return ""
    return io.open(p, "r", encoding="utf-8", errors="replace").read()


def _selftest() -> int:
    src = _repo_source()
    if not src:
        print("SELFTEST 无法自证：找不到 matlabc.py")
        return 2
    bad_cases = 0
    good_cases = 0
    fails = []

    def expect(tag, text, want_problem):
        nonlocal bad_cases, good_cases
        got = audit_source(text)
        ok = bool(got) == want_problem
        label = "反例" if want_problem else "正例"
        print("  [%s] %-46s -> %s%s"
              % (label, tag, "抓到" if got else "放行",
                 "" if ok else "   *** 不符预期 ***"))
        if not ok:
            fails.append(tag)
        if want_problem:
            bad_cases += 1
        else:
            good_cases += 1

    # 正例：真实仓库源码必须干净
    expect("真实仓库源码", src, False)
    # 反例 1：生产侧发出遗留算子 "ins"
    expect("生产侧改用遗留算子 ins",
           src.replace('append(("ins_before", _ln, "%s = [];" % _vn))',
                       'append(("ins", _ln, "%s = [];" % _vn))'), True)
    # 反例 2：渲染侧恢复覆盖式赋值
    expect("渲染侧恢复 _new[_idx] = payload",
           src.replace("_new[_idx:_idx] = [\"%s%s\" % (_indent, _payload)]",
                       "_new[_idx] = \"%s%s\" % (_indent, _payload)"), True)
    # 反例 3：删掉显式失败分支
    expect("渲染侧删掉 else: raise",
           src.replace("raise ValueError(\n                    \"unsupported edit op",
                       "pass  # disabled\n                _ = (\n                    \"unsupported edit op"),
           True)

    print("SELFTEST COUNTS {\"bad\": %d, \"good\": %d}" % (bad_cases, good_cases))
    if fails:
        print("SELFTEST FAILED: %s" % fails)
        return 1
    print("SELFTEST PASSED")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="两向自证")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    src = _repo_source()
    if not src:
        print("check_patch_ops: 找不到 matlabc.py（缺输入 → 红）")
        return 2
    probs = audit_source(src)
    if probs:
        print("check_patch_ops: %d 项违规" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_patch_ops: OK（算子集合 ⊆ %s，无覆盖式赋值，未知算子显式失败）"
          % sorted(ALLOWED_OPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
