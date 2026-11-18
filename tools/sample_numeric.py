# -*- coding: utf-8 -*-
"""从一棵真实工程树里**只抽数值函数**，供三段链路/规模实测使用。

    python tools/sample_numeric.py E:/temp/matlabc/yalmip -o E:/temp/matlabc/yalm_num --need 30

## 为什么需要它（R967）

上一轮直接把 yalmip 的函数文件抽 30 个送进三段链路，得到 **① 0/30**。
核到源文件才发现：抽到的全是**算子重载桩**——

    function varargout = acos(varargin)
    switch class(varargin{1})
        case 'sdpvar'
            varargout{1} = InstantiateElementWise(mfilename,varargin{:});
        case 'char'
            operator = CreateBasicOperator('decreasing','callback');

这类函数**不是数值计算**，而是给符号求解器用的元数据描述符，**本质上不该翻译成 C**。
拿它们做分母，得到的 0/30 是"目标不匹配"，不是"能力缺失"——
而一个错误的读数比没有读数更糟：它会让人去支持 cell/struct（那些桩永远用不到）。

## 判据（可核对的排除规则）

一个 .m 被当作**数值函数**，需同时满足：

| 条件 | 理由 |
|---|---|
| 首行是 `function`，且 `varargout` **不是**唯一返回 | 可变参数返回一律是分派桩 |
| 不含 `switch class(` | 按类型分派 = 桩 |
| 不含 `InstantiateElementWise` / `CreateBasicOperator` | YALMIP 专属构造器 |
| 不含 `@sdpvar` / `@char` 这类 case 标签 | 同上 |
| 至少有一个算术/归约记号（`+ - * / sum`） | 确保它真的在算数 |

排除数量与理由都会打印出来，**不做静默过滤**。

退出码：
    0 = 抽到 >= need 个
    1 = 不足 need 个（有多少给多少）
    2 = 缺输入（目录不存在）
"""
import argparse
import io
import os
import re
import shutil
import sys

STUB_MARKS = ("switch class(", "InstantiateElementWise", "CreateBasicOperator",
              "@sdpvar", "class(varargin{1})")


def is_numeric(src):
    """返回 (是否数值函数, 排除理由或空)。"""
    # **必须先跳过注释/空行**（R968）：Octave 的函数文件普遍以 `## 标题` 或
    # `% 说明` 开头，而 `function` 在第 20~60 行。原来要求首行就是 function，
    # 于是整个 Octave statistics 包 777 个文件被误判成「非函数文件」。
    lines = src.splitlines()
    body_start = 0
    for i, ln in enumerate(lines):
        t = ln.strip()
        if not t or t.startswith("%") or t.startswith("#"):
            continue
        body_start = i
        break
    head = "\n".join(lines[body_start:]).lstrip()
    if not head.startswith("function"):
        return False, "非函数文件"
    first = head.splitlines()[0]
    if "varargout" in first and "=" in first:
        return False, "可变参数返回（分派桩）"
    for mk in STUB_MARKS:
        if mk in src:
            return False, "含 %s（重载桩特征）" % mk
    if "classdef" in head[:200]:
        return False, "classdef"
    body = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("%"))
    if not re.search(r"[+\-*/]|\b(sum|max|min|mean|prod|numel|length)\b", body):
        return False, "没有算术记号（可能是纯分派）"
    return True, ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="只抽数值函数")
    ap.add_argument("src")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--need", type=int, default=30)
    ns = ap.parse_args(argv)

    if not os.path.isdir(ns.src):
        print("sample_numeric: 缺输入（目录不存在）")
        return 2
    if os.path.isdir(ns.out):
        shutil.rmtree(ns.out, ignore_errors=True)
    os.makedirs(ns.out)

    picked, why = [], {}
    for base, dirs, files in os.walk(ns.src):
        for f in sorted(files):
            if not f.endswith(".m"):
                continue
            p = os.path.join(base, f)
            try:
                s = io.open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            ok, reason = is_numeric(s)
            if not ok:
                why[reason] = why.get(reason, 0) + 1
                continue
            picked.append((f, p))
            if len(picked) >= ns.need:
                break
        if len(picked) >= ns.need:
            break

    seen = {}
    for f, p in picked:
        name = f
        if name in seen:
            name = "%s_%s" % (os.path.basename(os.path.dirname(p)).replace("@", ""), f)
        seen[name] = p
        shutil.copyfile(p, os.path.join(ns.out, name))

    print("抽出 %d 个数值函数 -> %s" % (len(seen), ns.out))
    print("排除统计（不作静默过滤）：")
    for k, v in sorted(why.items(), key=lambda x: -x[1]):
        print("   %-28s %d" % (k, v))
    return 0 if len(seen) >= ns.need else 1


if __name__ == "__main__":
    sys.exit(main())
