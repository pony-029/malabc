# -*- coding: utf-8 -*-
"""**测试用例筛选器**：从大批 .m 里挑出"适合转换测试"的那批。

    python tools/pick_cases.py --root E:/temp/matlabc --out flow/testcases.json
    python tools/pick_cases.py --selftest

## 为什么需要它

前几轮我把整个仓库直接丢进转换工具，得到 0/25、0/20 这类数字。
但那些"失败"里混着大量**根本不该被转换**的文件：

* `plot` / `figure` / `disp` —— 可视化与输出，嵌入式 C 不涉及
* `fopen` / `save` / `load` —— 文件 I/O
* `classdef` —— 类定义，本仓前端不支持（也不打算支持）
* `guide` / `uicontrol` —— GUI
* 只有脚本没有 function —— 无入参出参，不可调用

把它们算进分母，**通过率永远是 0，而且 0 里看不出任何可改进的信息**。
先筛掉，剩下的才反映"前端能力"。

## 判据（全部可机检，写死在 REJECT）

一条 .m 被**拒收**，只要满足任一：

| 判据 | 理由 |
|---|---|
| 含 `classdef` | 类定义不在转换目标内 |
| 含 GUI 调用 | 无对应 C 语义 |
| 含文件 I/O | 嵌入式目标不涉及 |
| 含可视化调用 | 同上 |
| 没有 `function` 关键字 | 脚本，无入参出参 |
| 解析后算子数 = 0 | 进了 MIR 但没有可转换内容 |

**不收"部分合格"**：只要触发一条就拒。这样剩下的每一个都能独立解释。

退出码：0=已产出 1=自检失败 2=缺输入
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))

#: 拒收规则：(名字, 正则, 理由)
REJECT = [
    ("classdef", re.compile(r"^\s*classdef\b", re.M),
     "类定义不在转换目标内"),
    ("gui", re.compile(r"\b(guide|uicontrol|uifigure|appdesigner)\b"),
     "GUI 无 C 语义"),
    ("io", re.compile(r"\b(fopen|fclose|fread|fwrite|save|load|"
                      r"readtable|writetable|xlsread|xlswrite)\s*\("),
     "文件 I/O 不在嵌入式目标内"),
    ("plot", re.compile(r"\b(plot|figure|subplot|hist|bar|surf|mesh|"
                        r"imagesc|axis|legend|xlabel|ylabel|title)\s*\("),
     "可视化调用"),
    ("print", re.compile(r"\b(disp|fprintf|printf|input|keyboard)\s*\("),
     "终端输出/交互"),
    ("eval", re.compile(r"\beval\s*\(|\bevalin\s*\(|\bevalc\s*\("),
     "eval 家族无静态语义"),
    ("spmd", re.compile(r"\b(parfor|spmd|gpuArray)\b"),
     "并行/GPU 不在目标内"),
]

FUNC_RE = re.compile(r"^\s*function\b", re.M)


def classify(text):
    """返回 (ok, reason)。ok=False 时 reason 是第一条命中的拒收理由。

    **先判具体原因、再判"是不是脚本"**（R1119）。反过来会让
    `classdef A; end` 被报成 script_only——它确实没有 function，
    但真正的理由是"类定义不支持"，而那个理由才有改进价值。
    """
    for name, rx, why in REJECT:
        if rx.search(text):
            return False, "%s:%s" % (name, why)
    if not FUNC_RE.search(text):
        return False, "script_only"
    return True, ""


def scan(root, min_ops=1):
    import mir as M
    picked, rejected = [], {}
    files = []
    for base, dirs, fns in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d not in {".git", "target", "__pycache__", ".m2c"}]
        for fn in sorted(fns):
            if fn.endswith(".m"):
                files.append(os.path.join(base, fn))
    files.sort()

    n_parse_fail = 0
    for p in files:
        try:
            text = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        ok, why = classify(text)
        if not ok:
            rejected[why] = rejected.get(why, 0) + 1
            continue
        try:
            _t, st = M.to_mir(text)
        except Exception as e:                  # noqa: BLE001
            n_parse_fail += 1
            rejected["parse:" + type(e).__name__] = \
                rejected.get("parse:" + type(e).__name__, 0) + 1
            continue
        ops = st.get("ops") or 0
        if ops < min_ops:
            rejected["no_ops"] = rejected.get("no_ops", 0) + 1
            continue
        un = st.get("unmapped") or 0
        picked.append({
            "path": os.path.relpath(p, root).replace("\\", "/"),
            "ops": ops,
            "unmapped": un,
            "rate": round(1.0 - float(un) / (un + ops), 4) if (un + ops) else 0.0,
        })
    return {"scanned": len(files), "picked": picked,
            "rejected": dict(sorted(rejected.items(),
                                    key=lambda x: -x[1])),
            "parse_fail": n_parse_fail}


def _selftest():
    """两向自证：该收的收、该拒的拒，且拒收理由要能说出来。"""
    good = bad = 0
    body = "function y = f(x)\n  y = x + 1;\nend\n"

    ok, _ = classify(body)
    if ok:
        good += 1
    else:
        bad += 1
        print("  [selftest] 纯函数被误拒")

    cases = [
        ("classdef A\nend\n", "classdef"),
        ("function f()\n  plot(1,2);\nend\n", "plot"),
        ("function f()\n  fid = fopen('a');\nend\n", "io"),
        ("function f()\n  disp(1);\nend\n", "print"),
        ("x = 1;\n", "script"),        # 脚本，无 function（reason 是 script_only）
    ]
    for text, kw in cases:
        ok2, why = classify(text)
        if not ok2 and kw in why:
            good += 1
        else:
            bad += 1
            print("  [selftest] 未按预期拒收 %r -> %r" % (kw, why))

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="测试用例筛选")
    ap.add_argument("--root", default=r"E:\temp\matlabc")
    ap.add_argument("--out", default=os.path.join(ROOT, "flow",
                                                 "testcases.json"))
    ap.add_argument("--min-ops", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not os.path.isdir(ns.root):
        print("pick_cases: 缺输入（%s 不存在）" % ns.root)
        return 2

    r = scan(ns.root, ns.min_ops)
    r["root"] = ns.root
    r["picked_count"] = len(r["picked"])
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(r, ensure_ascii=False, indent=1) + "\n")

    rej = sum(r["rejected"].values())
    print("[筛选] 扫描 %d ｜ **收下 %d** ｜ 拒收 %d"
          % (r["scanned"], len(r["picked"]), rej))
    print("  拒收原因（前 8）：")
    for k, v in list(r["rejected"].items())[:8]:
        print("    %-28s %d" % (k, v))
    ok = [p for p in r["picked"] if p["rate"] >= 0.9]
    print("  收下的 %d 个里，降级率 >=90%% 的有 %d 个"
          % (len(r["picked"]), len(ok)))
    print("[out] %s" % os.path.relpath(ns.out, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
