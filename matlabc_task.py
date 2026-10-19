#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matlabc task —— 把"改代码"变成**带验收条件、可回滚**的任务。

为什么要有这一层
================

工具能查（19 个 MCP 工具）、也能改（propose/apply/undo），但**"改"这件事
本身没有被验收**：改完对不对，靠人再看一遍。

而本仓已经有一套现成的"说不"的能力（33 道门 / 206 条判据）。这一层就是把它
接到写操作上：

    prepare   算清楚要改哪些位置，并把**验收条件**先列出来
    apply       原子写入（逐文件备份）
    validate    改完重新分析，与改前逐项对比
    rollback    验收不过就自己退回去

**关键差异**：验收条件在**动手之前**就写在屏幕上，而不是事后解释。

一个图看懂
==========

    prepare ──▶ [验收条件] ──▶ apply ──▶ validate ──▶ 通过
                   │                        │
                   └── 人可以先看 plan       └── 不过 ──▶ rollback（自动）

用法：
    python matlabc_task.py rename --dir myproj --old foo --new bar
    python matlabc_task.py rename --dir myproj --old foo --new bar --apply
    python matlabc_task.py rename --dir myproj --old foo --new bar --apply --json
    python matlabc_task.py --selftest

退出码：
    0  = 任务完成且验收通过（未加 --apply 时 = 计划已生成）
    1  = 验收不通过（已回滚），或任务被拒绝
    2  = 用法错误 / 目录不存在 / 名称非法
"""
import argparse
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SKIP_DIRS = (".git", "__pycache__", "node_modules", ".matlabc_task",
             ".pytest_cache", "build", "dist")

IDENT = u"[A-Za-z_][A-Za-z0-9_]*"


def _iter_m_files(root):
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for n in sorted(names):
            if n.endswith(".m"):
                yield os.path.join(dirpath, n)


def _mask_noise(line):
    """把注释与字符串**遮成等长的空格**，位置不变。

    为什么不是"跳过整行"：一行里可能既有注释又有真代码；遮成等长空格后，
    正则匹配到的位置仍然对应原文位置，既不会误改注释，也不会错位。
    """
    out = []
    in_str = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_str:
            if ch == u"'":
                in_str = False
                out.append(ch)
            else:
                out.append(u" ")
            i += 1
            continue
        if ch == u"%":
            # 注释到行尾
            out.append(u" " * (n - i))
            break
        if ch == u"'":
            # 转置运算符 vs 字符串：前一个非空字符是标识符/)/]/} 时是转置
            prev = u""
            for k in range(i - 1, -1, -1):
                if line[k] not in u" \t":
                    prev = line[k]
                    break
            if prev and (prev.isalnum() or prev in u"_)]}.'"):
                out.append(ch)
                i += 1
                continue
            in_str = True
            out.append(u" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return u"".join(out)


def _pattern(name, kind):
    """`ident` 认独立标识符；`field` 只认**点后面的**名字（`s.old` / `s(1).old`）。

    为什么要分成两种：重命名**函数**时，`s.helper` 是字段访问，不是那个函数；
    重命名**字段**时，独立的 `helper` 变量跟这个字段无关。一套正则同时兼两件事，
    必然在其中一边误伤。
    """
    tail = re.escape(name) + u"(?![A-Za-z0-9_])"
    if kind == "field":
        return re.compile(u"(?<=\\.)" + tail)
    return re.compile(u"(?<![A-Za-z0-9_.])" + tail)


def find_sites(root, name, kind="ident"):
    """返回 [(abs_path, line_idx(0 基), col, line_text)]。col 一律指向名字首字符。"""
    pat = _pattern(name, kind)
    sites = []
    for path in _iter_m_files(root):
        try:
            text = io.open(path, "r", encoding="utf-8", errors="replace").read()
        except (IOError, OSError):
            continue
        for li, line in enumerate(text.splitlines()):
            masked = _mask_noise(line)
            for m in pat.finditer(masked):
                sites.append((path, li, m.start(), line))
    return sites


def _scan(root):
    """用分析器取一份"改前/改后"可比对的指纹。"""
    try:
        from analyzer.api import analyze
    except Exception:
        from matlabc import analyze          # 兼容旧的导入路径
    res = analyze(root, no_checks=True)
    files = getattr(res, "files", None) or []
    nfun = 0
    for mf in files:
        nfun += len(getattr(mf, "functions", None) or [])
    edges = getattr(res, "edges", None)
    if edges is None:
        edges = []
        for mf in files:
            for f in (getattr(mf, "functions", None) or []):
                edges.extend(getattr(f, "calls", None) or [])
    diags = getattr(res, "diagnostics", None)
    if diags is None:
        diags = getattr(res, "issues", None) or []
    return {"files": len(files), "functions": nfun,
            "edges": len(edges), "diagnostics": len(diags)}


def _apply_rename(sites, old, new, backup=None):
    """按文件分组改写；把 {path: 原文} 填进 `backup`（**由调用方持有**）。

    ⚠ 备份**必须由调用方传入**：第一版把它当返回值，于是中途抛异常时
    备份跟着栈一起没了 —— 已写入的文件既没恢复、也没人知道它被改过。
    写盘失败（只读文件）这条路径由 `rsi_scenarios` 的「回滚」场景守着。
    """
    if backup is None:
        backup = {}
    pat = re.compile(u"(?<![A-Za-z0-9_.])" + re.escape(old) +
                     u"(?![A-Za-z0-9_])")
    per_file = {}
    for path, li, col, _ln in sites:
        per_file.setdefault(path, set()).add((li, col))
    for path, marks in per_file.items():
        text = io.open(path, "r", encoding="utf-8", errors="replace").read()
        backup[path] = text
        lines = text.splitlines()
        for li, col in marks:
            line = lines[li]
            masked = _mask_noise(line)
            # 在遮罩后的文本上定位，再按同一位置改原文
            if masked[col:col + len(old)] != old:
                continue
            lines[li] = line[:col] + new + line[col + len(old):]
        io.open(path, "w", encoding="utf-8", newline="").write(
            u"\n".join(lines) + (u"\n" if text.endswith(u"\n") else u""))
    return backup


def _restore(backup):
    for path, text in (backup or {}).items():
        try:
            io.open(path, "w", encoding="utf-8", newline="").write(text)
        except (IOError, OSError):
            pass


def task_rename(root, old, new, apply_it=False, as_json=False,
                kind="ident"):
    """rename 任务：prepare -> 验收条件 -> apply -> validate（失败自动 rollback）。"""
    log = []
    def say(step, msg):
        log.append({"step": step, "msg": msg})

    if not os.path.isdir(root):
        say("error", u"目录不存在：%s" % root)
        return 2, log, {}
    if not re.match(u"^" + IDENT + u"$", old or u"") or \
            not re.match(u"^" + IDENT + u"$", new or u""):
        say("error", u"名称必须是合法标识符（old=%r new=%r）" % (old, new))
        return 2, log, {}
    if old == new:
        say("error", u"新旧名称相同")
        return 2, log, {}

    before = _scan(root)
    label = ((u"." + old) if kind == "field" else old)
    sites = find_sites(root, old, kind)
    files = sorted(set(s[0] for s in sites))
    say("prepare", u"扫描完成：%d 个 .m 文件，命中 %d 处（%d 个文件）"
        % (len(list(_iter_m_files(root))), len(sites), len(files)))
    if not sites:
        say("plan", u"没有找到 `%s` —— 任务结束（不写任何文件）" % label)
        return 1, log, {"before": before, "sites": 0}

    # **验收条件先写出来**：动手之前就固定判据，避免事后解释。
    # 第 1 条是这轮补的：只比计数抓不到"只改了一半" —— 旧名字还有残留时，
    # 函数数与边数都可能**恰好不变**。
    criteria = [
        u"代码里不再出现 `%s`（注释与字符串不算）" % label,
        u"函数总数与改前相同（改名不改函数的数量）",
        (u"调用边数与改前相同（字段改名不该改变调用图）" if kind == "field"
         else u"调用边数与改前相同（原来指向 `%s` 的边全部指向 `%s`）"
              % (old, new)),
        u"诊断数不增加（改名不该引入新问题）",
    ]
    say("plan", u"将把 %d 处 `%s` 改为 `%s`，涉及 %d 个文件"
        % (len(sites), label,
           (u"." + new) if kind == "field" else new, len(files)))
    for i, c in enumerate(criteria):
        say("criteria", u"%d) %s" % (i + 1, c))

    if not apply_it:
        say("dry-run", u"未加 --apply，没有写入任何文件")
        return 0, log, {"before": before, "sites": len(sites),
                        "files": len(files), "criteria": criteria}

    backup = {}
    try:
        _apply_rename(sites, old, new, backup)
        say("apply", u"已写入 %d 个文件（备份在内存，验收不过自动回滚）"
            % len(backup))
        after = _scan(root)
        left = len(find_sites(root, old, kind))
        ok_left = (left == 0)
        ok_fun = after["functions"] == before["functions"]
        ok_edge = after["edges"] == before["edges"]
        ok_diag = after["diagnostics"] <= before["diagnostics"]
        say("validate", u"残留 %d 处 ｜ 函数 %d→%d ｜ 调用边 %d→%d ｜ 诊断 %d→%d"
            % (left, before["functions"], after["functions"],
               before["edges"], after["edges"],
               before["diagnostics"], after["diagnostics"]))
        if ok_left and ok_fun and ok_edge and ok_diag:
            say("validate", u"验收通过（4/4）")
            return 0, log, {"before": before, "after": after,
                            "sites": len(sites), "files": len(files),
                            "criteria": criteria, "verdict": "pass"}
        # **不过就自己退回去** —— 留下一个坏状态比不改更糟
        _restore(backup)
        why = []
        if not ok_left:
            why.append(u"仍有 %d 处旧名字" % left)
        if not ok_fun:
            why.append(u"函数数变了")
        if not ok_edge:
            why.append(u"调用边数变了")
        if not ok_diag:
            why.append(u"诊断增加了")
        say("rollback", u"验收不通过（%s）—— 已逐字节恢复 %d 个文件"
            % (u"、".join(why), len(backup)))
        return 1, log, {"before": before, "sites": len(sites),
                        "criteria": criteria, "verdict": "rollback"}
    except Exception as exc:
        _restore(backup)
        say("rollback", u"异常 %r —— 已恢复" % (exc,))
        return 1, log, {"before": before, "verdict": "error"}


# ---------------------------------------------------------------------------
# 自证：一个真项目、一次成功改名、一次故意失败的回滚
# ---------------------------------------------------------------------------

GOOD_FILES = {
    "a.m": (u"function y = helper(x)\n"
            u"% 这里是注释，里面的 helper 不该被改\n"
            u"y = x + 1;\n"
            u"end\n"),
    "b.m": (u"function r = caller(v)\n"
            u"r = helper(v) + helper(v);\n"
            u"end\n"),
    "c.m": (u"function s = use_str()\n"
            u"s = 'helper';\n"
            u"end\n"),
}


def _make(files, d):
    for n, text in files.items():
        with io.open(os.path.join(d, n), "w", encoding="utf-8",
                     newline="") as fh:
            fh.write(text)


def selftest():
    import shutil
    import tempfile
    good = bad = 0

    def chk(cond, name, detail=""):
        if not cond:
            print("  [FAIL] %-46s %s" % (name, detail))
        return bool(cond)

    d = tempfile.mkdtemp(prefix="task_")
    try:
        _make(GOOD_FILES, d)
        sites = find_sites(d, "helper")
        # 注释里的 helper、字符串里的 'helper' 都不该命中
        if chk(len(sites) == 3, u"自证：只命中 3 处（定义 + 2 次调用）",
               u"实际 %d 处" % (len(sites),)):
            good += 1
        else:
            bad += 1

        rc, log, info = task_rename(d, "helper", "assist", apply_it=False)
        if chk(rc == 0 and info.get("sites") == 3,
               u"自证：dry-run 给出计划", u"rc=%r" % (rc,)):
            good += 1
        else:
            bad += 1
        raw = io.open(os.path.join(d, "a.m"), encoding="utf-8").read()
        if chk("helper" in raw, u"自证：dry-run 没有写盘"):
            good += 1
        else:
            bad += 1

        rc, log, info = task_rename(d, "helper", "assist", apply_it=True)
        if chk(rc == 0 and info.get("verdict") == "pass",
               u"自证：改名后 4 条验收全过",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
        a = io.open(os.path.join(d, "a.m"), encoding="utf-8").read()
        c = io.open(os.path.join(d, "c.m"), encoding="utf-8").read()
        if chk("assist" in a and u"% 这里是注释" in a,
               u"自证：定义被改，注释原样保留"):
            good += 1
        else:
            bad += 1
        if chk(u"'helper'" in c, u"自证：字符串里的名字没被误改"):
            good += 1
        else:
            bad += 1

        # --- 回滚之一：**只改了一半**（旧名字仍有残留）-------------------
        # 直接替换 `_apply_rename` 模拟"只处理第一个文件"。
        _mod = sys.modules[__name__]
        orig_apply = _mod._apply_rename

        def _partial(ss, old, new, backup=None):
            by = {}
            for s in ss:
                by.setdefault(s[0], []).append(s)
            first = sorted(by)[0]
            # 备份必须继续往调用方传，否则这个桩测的是"签名不匹配"，
            # 而不是"只改了一半"。
            return orig_apply(by[first], old, new, backup)

        _mod._apply_rename = _partial
        try:
            snap = dict((p, io.open(p, encoding="utf-8").read())
                        for p in [os.path.join(d, "b.m")])
            rc, log, info = task_rename(d, "assist", "helper2", apply_it=True)
        finally:
            _mod._apply_rename = orig_apply
        if chk(rc == 1 and info.get("verdict") == "rollback",
               u"自证：残留旧名字 → 判为不通过并回滚",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
        now = io.open(os.path.join(d, "b.m"), encoding="utf-8").read()
        if chk(now == snap[os.path.join(d, "b.m")],
               u"自证：回滚后文件逐字节等于改前"):
            good += 1
        else:
            bad += 1

        # --- 回滚之二：**分析器说函数数变了** -----------------------------
        calls = {"n": 0}
        real_scan = _mod._scan

        def _bad_scan(root):
            calls["n"] += 1
            base = real_scan(root)
            if calls["n"] == 2:
                base = dict(base)
                base["functions"] = base["functions"] + 1
            return base

        _mod._scan = _bad_scan
        try:
            # 用 `assist`（上一次成功后仍存在）—— 上一次回滚已经把
            # `helper2` 抹掉了，拿它试会得到"没有命中"，测不到这里想测的东西。
            rc, log, info = task_rename(d, "assist", "helper3", apply_it=True)
        finally:
            _mod._scan = real_scan
        if chk(rc == 1 and info.get("verdict") == "rollback",
               u"自证：函数数变了 → 判为不通过并回滚",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # ---- rename-field：只动 `.field`，不动同名变量，不动字符串 -------------
    d2 = tempfile.mkdtemp(prefix="taskf_")
    try:
        _make({
            "f1.m": (u"function y = f1()\n"
                     u"s.old = 1;\n"
                     u"old = 2;\n"
                     u"y = s.old;\n"
                     u"end\n"),
            "f2.m": (u"function r = f2(t)\n"
                     u"r = t.old + 1;\n"
                     u"end\n"),
            "f3.m": (u"function q = f3()\n"
                     u"q = 's.old';\n"
                     u"end\n"),
        }, d2)
        fsites = find_sites(d2, "old", kind="field")
        if chk(len(fsites) == 3, u"自证 field：只命中 3 处 `.old`",
               u"实际 %d 处" % (len(fsites),)):
            good += 1
        else:
            bad += 1
        rc, log, info = task_rename(d2, "old", "renamed", apply_it=True,
                                    kind="field")
        f1 = io.open(os.path.join(d2, "f1.m"), encoding="utf-8").read()
        f3 = io.open(os.path.join(d2, "f3.m"), encoding="utf-8").read()
        if chk(rc == 0 and info.get("verdict") == "pass",
               u"自证 field：逐条验收通过",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
        if chk(u"s.renamed" in f1 and u"\nold = 2;" in f1,
               u"自证 field：字段改名，同名变量不动"):
            good += 1
        else:
            bad += 1
        if chk(u"'s.old'" in f3, u"自证 field：字符串里的 `.old` 不动"):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d2, ignore_errors=True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    sub = ap.add_subparsers(dest="cmd")
    rp = sub.add_parser("rename")
    rp.add_argument("--dir", default=".")
    rp.add_argument("--old", required=True)
    rp.add_argument("--new", required=True)
    rp.add_argument("--apply", action="store_true")
    rp.add_argument("--json", action="store_true")
    fp = sub.add_parser("rename-field")
    fp.add_argument("--dir", default=".")
    fp.add_argument("--old", required=True)
    fp.add_argument("--new", required=True)
    fp.add_argument("--apply", action="store_true")
    fp.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    if args.help or (not args.selftest and not args.cmd):
        sys.stdout.write(__doc__)
        return 0
    if args.selftest:
        return selftest()

    if args.cmd in ("rename", "rename-field"):
        rc, log, info = task_rename(os.path.abspath(args.dir), args.old,
                                    args.new, args.apply, args.json,
                                    kind=("field" if args.cmd == "rename-field"
                                          else "ident"))
        if args.json:
            print(json.dumps({"ok": rc == 0, "log": log, "info": info},
                             ensure_ascii=False, indent=2))
        else:
            for row in log:
                print("[%-9s] %s" % (row["step"], row["msg"]))
        return rc
    sys.stdout.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
