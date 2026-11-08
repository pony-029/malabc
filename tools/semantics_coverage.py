# -*- coding: utf-8 -*-
"""**MATLAB 语义完备性核查**：真实代码里出现了哪些语义，本工具支持到哪一档。

## 为什么需要它

"能转多少个函数"只回答"结果"，不回答"还差什么"。这份表把**语言的语义面**
逐项摆出来：出现频次、涉及函数数、支持档位（full / partial / none）。

支持档位是**人工判据**（写在本文件里，可审），出现频次是**实测**。
两者分开写，是为了让"我说支持"和"它真的出现"都不能单独成立。

用法：
    python tools/semantics_coverage.py <目录...> [-o out.json]
"""
import argparse
import collections
import io
import json
import os
import re
import sys

#: (键, 说明, 正则, 支持档位, 备注)
#:
#: 档位口径：
#:   full    —— 有算子/语句且进了语料，数值与 Octave 一致
#:   partial —— 只支持某种受限形态（如 struct 只支持"只经 .field 的局部量"）
#:   none    —— 明确不做（边界），或仅能识别但不能生成
FEATURES = [
    ("arith", "逐元素/标量算术（+ - * / .* ./）",
     r"(?<![=<>~])[+\-*/]{1,2}(?![=])", "full", "OP-ADD/SUB/MUL/DIV"),
    ("power", "幂运算（.^ ^）",
     r"\.\^|\^", "none", "未实现"),
    ("compare", "比较（== ~= < <= > >=）",
     r"==|~=|<=|>=|<(?![-=])|>(?![=])", "full", "OP-MASK/FIND 的比较码"),
    ("logic_elem", "逐元素逻辑（& | ~）",
     r"[^&]\&[^&]|[^|]\|[^|]|(?<![~])~(?![=])", "partial", "仅条件中的 ~= 与少数形态"),
    ("logic_short", "短路逻辑（&& ||）",
     r"&&|\|\|", "none", "条件里未支持"),
    ("colon_range", "范围（a:b / a:s:b）",
     r"\b\w+\s*:\s*[\w(]+\s*(?::\s*[\w(]+)?", "partial", "OP-SLICE / COLRANGE 的受限形态"),
    ("index_paren", "下标（A(i) / A(i,j)）",
     r"[A-Za-z_]\w*\s*\([^)]*\)", "full", "OP-INDEX/IDX2/SLICE"),
    ("index_cell", "元胞下标（c{i}）",
     r"[A-Za-z_]\w*\s*\{", "none", "元胞容器不做"),
    ("cell_ctor", "元胞构造（cell(...) / {..}）",
     r"\bcell\s*\(|\{\s*[^}]*\}", "none", "元胞容器不做"),
    ("struct_field", "结构体字段（s.f）",
     r"[A-Za-z_]\w*\s*\.\s*[A-Za-z_]\w*", "partial",
     "局部 + 只经 .field 可无损展开；参数 struct 需 `% @m2c fields` 声明"),
    ("string_lit", "字符串字面量（'..' / \"..\"）",
     r"(?<![\w\)\]\}.'])'(?:[^']|'')*'", "none", "**本工具最大边界**（真实库 89% 涉及）"),
    ("string_fn", "字符串函数（sprintf/num2str/strcmp）",
     r"\b(sprintf|num2str|str2num|strcmp|strrep|regexp|regexprep)\s*\(", "none", "同上"),
    ("func_handle", "函数句柄（@f / @(x) ...）",
     r"@\s*\(|@\s*[A-Za-z_]\w*", "none", "无闭包/回调模型"),
    ("varargin", "可变入参（varargin）",
     r"\bvarargin\b", "none", "签名级拒绝"),
    ("varargout", "可变出参（varargout）",
     r"\bvarargout\b", "none", "签名级拒绝"),
    ("nargchk", "参数个数（nargin/nargout）",
     r"\b(nargin|nargout)\b", "partial", "只作为普通变量，无语义"),
    ("try_catch", "异常处理（try/catch）",
     r"\btry\b|\bcatch\b", "none", "C 侧无异常模型"),
    ("switch", "分支（switch/case/otherwise）",
     r"\bswitch\b", "partial", "降为占位块（恒假 if），不执行分支"),
    ("loop", "循环（for/while/break）",
     r"\b(for|while)\b", "full", "for/while/break 全支持"),
    ("cond_if", "条件（if/elseif/else）",
     r"\bif\b", "full", "单比较条件；复合条件不支持"),
    ("global", "全局/持久（global/persistent）",
     r"\b(global|persistent)\b", "none", "无全局状态模型"),
    ("oop", "面向对象（classdef/methods/properties）",
     r"\bclassdef\b|\bmethods\b|\bproperties\b", "none", "不做"),
    ("eval", "动态执行（eval/feval）",
     r"\b(eval|evalin|feval)\s*\(", "none", "静态翻译无法处理"),
    ("multi_out", "多返回值（[a,b]=f(x)）",
     r"\[\s*[A-Za-z_]\w*\s*,\s*[^\]]*\]\s*=", "partial", "仅部分内建（find 2/3 出）"),
]

LEVEL_LABEL = {"full": "支持", "partial": "部分", "none": "不支持"}


def scan(dirs):
    stat = collections.OrderedDict(
        (k, {"desc": d, "level": lv, "note": n, "files": 0, "hits": 0})
        for k, d, _r, lv, n in FEATURES)
    pats = [(k, re.compile(r, re.M)) for k, _d, r, _lv, _n in FEATURES]
    nfiles = 0
    for src in dirs:
        if not os.path.isdir(src):
            continue
        for dp, _dn, fns in os.walk(src):
            if os.sep + ".git" in dp:
                continue
            for fn in fns:
                if not fn.endswith(".m"):
                    continue
                nfiles += 1
                try:
                    txt = io.open(os.path.join(dp, fn), encoding="utf-8",
                                  errors="replace").read()
                except OSError:
                    continue
                for k, rx in pats:
                    c = len(rx.findall(txt))
                    if c:
                        stat[k]["files"] += 1
                        stat[k]["hits"] += c
    return nfiles, stat


def main():
    ap = argparse.ArgumentParser(description="MATLAB 语义完备性核查")
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    nfiles, stat = scan(a.dirs)
    print("扫描 %d 个 .m 文件\n" % nfiles)
    print("%-12s %-28s %-6s %8s %8s" % ("语义", "说明", "档位", "函数数", "出现"))
    for k, v in stat.items():
        print("%-12s %-28s %-6s %8d %8d"
              % (k, v["desc"][:28], LEVEL_LABEL[v["level"]], v["files"], v["hits"]))

    miss = [k for k, v in stat.items() if v["level"] == "none" and v["files"] > 0]
    part = [k for k, v in stat.items() if v["level"] == "partial" and v["files"] > 0]
    print("\n出现但不支持：%d 类 —— %s" % (len(miss), ", ".join(miss)))
    print("出现但只部分支持：%d 类 —— %s" % (len(part), ", ".join(part)))

    if a.out:
        io.open(a.out, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"files": nfiles, "features": stat},
                       ensure_ascii=False, indent=2) + "\n")
        print("已写出 %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
