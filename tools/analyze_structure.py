# -*- coding: utf-8 -*-
"""analyze_structure.py —— 单文件结构的**可重跑基线**（P0，不是护栏）。

为什么需要它
============
`docs/analysis/ANALYSIS_2026-10-17_MATLABC_STRUCTURE.md` 里的读数（706 函数、
p50=21、12 个函数 >200 行、治理 298 次 vs 产品 46 次）如果只存在于文档里，
下一轮重构就没有**前后对照基线**：「变好了」会退回主观感觉。

本工具把那次测量固化成命令，输出稳定 JSON，供每轮重构前后各跑一次。

测什么（**只测，不改**）
========================
    lines / functions / classes / fn_lines_total / ratio
    分位数 p50 p75 p90 p99 max
    >50 / >100 / >200 / >500 / >1000 的计数
    最长 20 个函数（行数 / 起始行 / 限定名）
    git：提交总数、首末日期、被改最多的 15 个文件

边界
----
* 不判定「好不好」——阈值与取舍留给读者；本工具只给读数。
* `end_lineno` 是 3.8+ 的字段；3.6.5 下退化为 `lineno`（行长全部记 1），
  **不会崩**，但读数不可比。输出里 `end_lineno_available` 明确写出来。

用法：
    python tools/analyze_structure.py                 # 人类可读摘要
    python tools/analyze_structure.py --json          # 稳定 JSON
    python tools/analyze_structure.py --file x.py     # 指定文件
    python tools/analyze_structure.py --no-git        # 跳过 git 统计
    python tools/analyze_structure.py --selftest      # 两向自证

退出码：
    0 = 正常
    1 = 自证失败
    2 = 缺输入（文件不在 / 解析失败）
"""
import argparse
import ast
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT = os.path.join(ROOT, "matlabc.py")
THRESHOLDS = (50, 100, 200, 500, 1000)


def _span(node, has_end):
    if has_end:
        return node.end_lineno - node.lineno + 1
    return 1


def measure_source(text):
    """对一段源码做结构测量；解析失败抛 ValueError。"""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError("解析失败：%s" % exc)

    has_end = hasattr(ast.FunctionDef, "end_lineno") or hasattr(
        ast, "FunctionDef") and "end_lineno" in getattr(
            ast.FunctionDef, "_fields", ())
    # 上面的推断不可靠；直接用第一个节点试探。
    probe = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            probe = n
            break
    has_end = bool(probe is not None and hasattr(probe, "end_lineno"))

    funcs = []
    classes = 0

    def walk(node, prefix=""):
        nonlocal classes
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append({
                    "lines": _span(ch, has_end),
                    "line": ch.lineno,
                    "name": prefix + ch.name,
                })
                walk(ch, prefix + ch.name + ".")
            elif isinstance(ch, ast.ClassDef):
                classes += 1
                walk(ch, ch.name + ".")
            else:
                walk(ch, prefix)

    walk(tree)
    sizes = sorted(f["lines"] for f in funcs) or [0]

    def pct(x):
        return sizes[max(0, min(len(sizes) - 1, int(len(sizes) * x) - 1))]

    total_fn = sum(sizes)
    lines = text.count("\n") + 1
    return {
        "lines": lines,
        "functions": len(funcs),
        "classes": classes,
        "fn_lines_total": total_fn,
        "fn_lines_ratio": round(1.0 * total_fn / lines, 4) if lines else 0.0,
        "p50": pct(0.50),
        "p75": pct(0.75),
        "p90": pct(0.90),
        "p99": pct(0.99),
        "max": sizes[-1],
        "over": dict((str(t), sum(1 for s in sizes if s > t)) for t in THRESHOLDS),
        "longest": sorted(funcs, key=lambda f: -f["lines"])[:20],
        "end_lineno_available": has_end,
    }


def measure_main(text):
    """把 `main` 拆到**顶层语句**粒度，给出三段边界（P1 的验收尺）。

    边界不是猜的：`parse_args(...)` 那一行是 cli_entry 的出口，
    `_emit_report_outputs(...)` 那一行是 emit_outputs 的入口。
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    main = None
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == "main":
            main = n
            break
    if main is None:
        return None
    lines = text.splitlines()
    end = getattr(main, "end_lineno", main.lineno)
    groups = {"argparse": 0, "analyze": 0, "render": 0, "other": 0}
    parse_args_line = None
    emit_line = None
    first_analyze = None
    for st in main.body:
        s = st.lineno
        names = []
        for c in ast.walk(st):
            if isinstance(c, ast.Call):
                if isinstance(c.func, ast.Name):
                    names.append(c.func.id)
                elif isinstance(c.func, ast.Attribute):
                    names.append(c.func.attr)
        joined = " ".join(names)
        if "parse_args" in joined and parse_args_line is None:
            parse_args_line = s
        if "_emit_report_outputs" in joined and emit_line is None:
            emit_line = s
        if "add_argument" in joined or "parse_args" in joined or "ArgumentParser" in joined:
            kind = "argparse"
        elif any(k in joined for k in ("render", "write", "dump", "print", "emit", "summar")):
            kind = "render"
        elif any(k in joined for k in ("parse", "analy", "scan", "check", "collect", "build")):
            kind = "analyze"
        else:
            kind = "other"
        groups[kind] += 1
        # cli_entry 的终点取「parse_args 之后的第一条分析语句」：
        # parse_args 与它之间的 9 行是前置校验（root.is_dir / binary 参数），
        # 归 cli_entry 更贴职责（它们不产出任何模型数据）。
        if kind == "analyze" and parse_args_line and s > parse_args_line and first_analyze is None:
            first_analyze = s
    # S1 之后 `parse_args` 已移出 main ⇒ 三段退化成两段（pre_emit + emit_outputs）；
    # S2b 完成后本工具会自动回到三段。**判据不该因为重构而失效**，所以两种形状都认。
    segs = {}
    split = first_analyze or (parse_args_line + 1 if parse_args_line else None)
    if emit_line and main.lineno < emit_line <= end:
        segs["emit_outputs"] = [emit_line, end, end - emit_line + 1]
        if split and main.lineno < split < emit_line:
            segs["pre_pipeline"] = [main.lineno, split - 1, split - main.lineno]
            segs["run_pipeline"] = [split, emit_line - 1, emit_line - split]
        else:
            segs["pre_emit"] = [main.lineno, emit_line - 1, emit_line - main.lineno]
    return {
        "start": main.lineno,
        "end": end,
        "lines": end - main.lineno + 1,
        "stmts": len(main.body),
        "groups": groups,
        "parse_args_line": parse_args_line,
        "first_analyze_line": first_analyze,
        "emit_line": emit_line,
        "segments": segs,
        "first_line": (lines[main.lineno - 1].strip()[:70]
                       if main.lineno - 1 < len(lines) else ""),
    }


def _walk_names(node):
    """收集 node 下的名字，**跳过嵌套函数 / lambda 的内部**（只记它们的定义名）。

    不跳的话，嵌套函数自己的参数会被当成本层的自由变量（实测：`run_pipeline`
    里的局部函数 `lookup(name)` 导致 `name` 被误报）。
    """
    loads, stores = set(), set()
    for ch in ast.iter_child_nodes(node):
        if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stores.add(ch.name)
            continue
        if isinstance(ch, ast.Lambda):
            continue
        if isinstance(ch, ast.Name):
            if isinstance(ch.ctx, ast.Load):
                loads.add(ch.id)
            else:
                stores.add(ch.id)
            continue
        l2, s2 = _walk_names(ch)
        loads |= l2
        stores |= s2
    return loads, stores


def measure_free(text, func_name):
    """某个函数的**自由变量**：既不是局部、也不是模块级、也不是 builtin。

    切函数时用它一次算清跨边界变量 —— 比逐个 `NameError` 试错快十倍，而且穷尽。
    """
    import builtins
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    fn = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name:
            fn = n
            break
    if fn is None:
        return None
    local = set(a.arg for a in fn.args.args)
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            local.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                local.add(a.asname or a.name.split(".")[0])
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                            ast.ClassDef)) and n is not fn:
            local.add(n.name)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            local.add(n.name)
        elif isinstance(n, ast.comprehension):
            for t in ast.walk(n.target):
                if isinstance(t, ast.Name):
                    local.add(t.id)
        elif isinstance(n, ast.Lambda):
            for a in n.args.args:
                local.add(a.arg)

    loads, _stores = _walk_names(fn)

    globs = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            globs.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    globs.add(t.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                globs.add(a.asname or a.name.split(".")[0])

    bi = set(dir(builtins))
    return sorted(x for x in loads
                  if x not in local and x not in globs and x not in bi)


def measure_git(root):
    """提交史读数；取不到 git 时返回 {"available": False}。"""
    def run(args):
        try:
            out = subprocess.run(
                ["git", "-C", root] + args,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        return out.stdout.decode("utf-8", "replace")

    total = run(["rev-list", "--count", "HEAD"])
    if total is None:
        return {"available": False}
    first = run(["log", "--reverse", "--format=%ad", "--date=short"])
    last = run(["log", "-1", "--format=%ad", "--date=short"])
    names = run(["log", "--name-only", "--format="])
    counts = {}
    for line in (names or "").splitlines():
        line = line.strip()
        if line:
            counts[line] = counts.get(line, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
    return {
        "available": True,
        "commits": int(total.strip() or 0),
        "first_date": (first or "").splitlines()[0] if first else "",
        "last_date": (last or "").strip(),
        "top_files": [{"file": k, "count": v} for k, v in top],
    }


def _selftest():
    bad, good = 0, 0
    src = (
        "def a():\n"
        "    return 1\n"
        "\n"
        "class K:\n"
        "    def m(self):\n"
        "        return 2\n"
        "\n"
        "def big():\n" + "    x = 1\n" * 12
    )
    m = measure_source(src)
    if m["functions"] == 3 and m["classes"] == 1:
        good += 1
    else:
        bad += 1
        print("  [selftest] 函数/类计数不对：%s" % m)
    if m["max"] >= 13:
        good += 1
    else:
        bad += 1
        print("  [selftest] 最长函数行数不对：%d" % m["max"])
    if m["over"]["1000"] == 0 and m["over"]["200"] == 0:
        good += 1
    else:
        bad += 1
        print("  [selftest] 阈值计数不对")
    try:
        measure_source("def broken(:\n")
        bad += 1
        print("  [selftest] 语法错误未被报出")
    except ValueError:
        good += 1
    src2 = (
        "def main(argv=None):\n"
        "    ap = argparse.ArgumentParser()\n"
        "    ap.add_argument('x')\n"
        "    args = ap.parse_args(argv)\n"
        "    files = collect_files(args)\n"
        "    model = build_model(files)\n"
        "    _emit_report_outputs(args, model)\n"
        "    return 0\n"
    )
    ms = measure_main(src2)
    if (ms and ms["stmts"] == 7 and ms["parse_args_line"] == 4
            and ms["first_analyze_line"] == 5 and ms["emit_line"] == 7):
        good += 1
    else:
        bad += 1
        print("  [selftest] main 切分边界不对：%s" % (ms,))
    if ms and [ms["segments"][k][2] for k in ("pre_pipeline", "run_pipeline", "emit_outputs")] == [4, 2, 2]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 三段行数不对：%s" % (ms and ms.get("segments"),))

    src3 = (
        "G = 1\n"
        "def f(a):\n"
        "    b = a + 1\n"
        "    return b + G + missing_thing + len(a)\n"
    )
    fv = measure_free(src3, "f")
    if fv == ["missing_thing"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 自由变量算错（G 是模块级、len 是 builtin、a/b 是局部）：%s"
              % (fv,))

    # 真实文件必须能跑通（缺文件时这一条不成立，但也不该判红成「工具坏了」）
    if os.path.isfile(DEFAULT):
        real = measure_source(io.open(DEFAULT, "r", encoding="utf-8",
                                      errors="replace").read())
        if real["functions"] > 100 and real["lines"] > 1000:
            good += 1
        else:
            bad += 1
            print("  [selftest] 真实文件读数异常：%s" % {k: real[k] for k in ("lines", "functions")})
    return bad, good


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--file", default=DEFAULT)
    ap.add_argument("--no-git", action="store_true")
    ap.add_argument("--main", action="store_true")
    ap.add_argument("--free", default=None, metavar="FUNC")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", action="store_true")
    args = ap.parse_args(argv)

    if args.help:
        print(__doc__)
        return 0
    if args.selftest:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1

    path = args.file
    if not os.path.isfile(path):
        print("analyze_structure: 缺输入（%s 不存在）" % path)
        return 2
    text = io.open(path, "r", encoding="utf-8", errors="replace").read()
    try:
        m = measure_source(text)
    except ValueError as exc:
        print("analyze_structure: %s" % exc)
        return 2

    if args.free:
        fv = measure_free(text, args.free)
        if fv is None:
            print("analyze_structure: 找不到函数 %s" % args.free)
            return 2
        if args.json:
            print(json.dumps({"func": args.free, "free": fv},
                             ensure_ascii=False, indent=2))
            return 0
        print("free(%s) = %s" % (args.free, fv if fv else "[]（无跨界变量）"))
        return 0

    if args.main:
        ms = measure_main(text)
        if not ms:
            print("analyze_structure: 找不到 main 函数")
            return 2
        if args.json:
            print(json.dumps(ms, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        print("main            L%d..L%d（%d 行 / %d 条顶层语句）"
              % (ms["start"], ms["end"], ms["lines"], ms["stmts"]))
        print("boundaries      parse_args=L%s  _emit_report_outputs=L%s"
              % (ms["parse_args_line"], ms["emit_line"]))
        print("groups          " + "  ".join("%s:%d" % (k, ms["groups"][k])
                                              for k in sorted(ms["groups"])))
        for name in ("pre_pipeline", "run_pipeline", "pre_emit", "emit_outputs"):
            seg = ms["segments"].get(name)
            if seg:
                print("  %-13s L%-6d..L%-6d  %4d 行" % (name, seg[0], seg[1], seg[2]))
        return 0

    m["file"] = os.path.basename(path)
    if not args.no_git:
        m["git"] = measure_git(ROOT)

    if args.json:
        print(json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    print("file            %s" % m["file"])
    print("lines           %d" % m["lines"])
    print("functions       %d（类 %d）" % (m["functions"], m["classes"]))
    print("fn_lines        %d（%.1f%%）" % (m["fn_lines_total"], 100 * m["fn_lines_ratio"]))
    print("percentiles     p50=%d p75=%d p90=%d p99=%d max=%d"
          % (m["p50"], m["p75"], m["p90"], m["p99"], m["max"]))
    print("over            " + "  ".join("%s:%d" % (k, m["over"][k])
                                          for k in sorted(m["over"], key=int)))
    print("longest:")
    for f in m["longest"][:10]:
        print("  %5d  L%-6d %s" % (f["lines"], f["line"], f["name"]))
    g = m.get("git") or {}
    if g.get("available"):
        print("git             %d commits（%s → %s）"
              % (g["commits"], g["first_date"], g["last_date"]))
        print("top files:      " + ", ".join("%s:%d" % (x["file"], x["count"])
                                             for x in g["top_files"][:6]))
    else:
        print("git             不可用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
