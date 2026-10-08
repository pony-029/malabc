# -*- coding: utf-8 -*-
"""登记制护栏：子进程调用必须切断 stdin、并且不会永久挂住。

动因（R62-R31e，**真实缺陷**，两条独立证据）：
  1. `tools/check_doc_flags.py` 用 `subprocess.run(..., capture_output=True)`
     （stdout/stderr=PIPE、stdin **继承**）串行问 4 个脚本的 `--help`。
     实测（探针 `probe_r26b_pipe`，含重跑对照）：前 3 个脚本 0.5–0.8s 返回，
     第 4 个 `matlabc_mcp.py` —— 一个 stdio JSON-RPC server，设计上就读 stdin
     —— 在继承来的、永不 EOF 的管道上**永久阻塞**，等满它 180s 的内建超时。
     护栏总耗时 ≈ 181s，被外部 `timeout 90` 杀掉（rc=124），表现为「无缘无故
     地卡住」。切断 stdin 后同一份护栏 **3.4s** 跑完。
  2. `tools/check_all.py` 用 `subprocess.run(stdout=PIPE)` **且没有 timeout**：
     只要有一个护栏不退出，CI 就永远挂住 —— 一条会挂死的链比一道闸门更糟。

判据（只认装置，不认叙述）：
  S1 任何**捕获输出**（`capture_output=True` 或 `stdout/stderr=PIPE`）的调用，
     必须显式给出 `stdin=`（`DEVNULL` 或 `PIPE`），不许继承调用方的句柄；
  S2 用 `run/check_output/call/check_call` 且捕获输出的，必须给 `timeout=`；
  S3 `Popen` 捕获输出的无法静态证明超时（communicate 可能在别处），
     必须逐点登记在 `POPEN_STREAMING`（每条带理由）；
  S4 带 `**kwargs` 展开的调用，静态**看不见**它到底捕不捕获输出 ——
     这是已知盲区（本仓最关键的 MCP 点就在盲区里），必须登记在 `UNVERIFIABLE`；
     **两张登记表都两向核对**：代码里有而未登记 → 抓；登记了而代码里没有
     （陈旧条目）→ 也抓，否则陈旧登记会掩盖新增点；
  S5 `tests/` 单独计数并**打印**（不隐瞒），但不计入违规 —— 回归测试由 pytest
     驱动、stdin 由 pytest 管理，与运行时路径的风险不同类。

一图看懂（三种病，三种药）：

    调用点 ─┬─ capture_output / stdout=PIPE / stderr=PIPE ?
            │        └─ 否 → 不在判据内（如起浏览器，不读回输出）
            │        └─ 是 ↓
            ├─ ① 有没有 stdin= ?            没有 → S1 红
            │        （继承调用方句柄；stdio server 会永久阻塞）
            ├─ ② 是 run/call/check_* 且有没有 timeout= ?
            │       没有 → S2 红（挂住无上限）
            ├─ ③ 是 Popen ?  → S3：静态证不了超时 → 必须登记进 POPEN_STREAMING
            │       登记键 = "<相对路径>|<限定函数名>"，值 = 为什么可以没有
            └─ ④ 调用了 **kwargs ?  → S4：静态看不见 → 必须登记进 UNVERIFIABLE

    两张登记表都两向核对：
        代码里有、表里没有     → 红（新增点不许静默落地）
        表里有、代码里没有     → 红（陈旧登记会掩盖新增点）

  实测现状（具体条数由 plain 模式的总结行打印，**这里不写死**，免得文档先过期）：
  运行时捕获点全部切断 stdin；run 类全部带 timeout；Popen 捕获点与 **kwargs
  盲点全部登记；tests/ 另有若干点按设计不计入。

用法：
    python tools/check_subprocess_hygiene.py             # 0=干净 1=有违规 2=缺输入
    python tools/check_subprocess_hygiene.py --selftest  # 两向自证
"""
import argparse
import ast
import os
import sys

# 扫描范围：本仓**运行时** Python 文件所在的目录（不含 tests/）。
# 登记在这里 = 明确声明「我只看这些地方」，避免护栏边界悄悄漂移。
SCAN_DIRS = (".", "tools", "binfmt", "renderers")

# S3：`Popen` + 捕获输出、但不带 timeout 的合法点（每条必须有理由）。
# 键 = "<相对路径>|<最内层函数名>"，值 = 为什么这里可以没有 timeout。
POPEN_STREAMING = {
    "gui.py|_launch_gui.run":
        "长跑流式分析进程（GUI 里 `_launch_gui` 内的闭包 `run`）：stdout 由 "
        "readline 循环消费，由用户点「停止」终止；加超时会把「大工程分析得久」"
        "误判成失败。已设 stdin=DEVNULL。",
    "tools/check_all.py|_run":
        "Popen 之后紧跟 communicate(timeout=GUARD_TIMEOUT)，超时判红；"
        "已设 stdin=DEVNULL。",
    "tools/check_py36_clean.py|_run_gate":
        "Popen 之后紧跟 communicate(timeout=SCAN_TIMEOUT=600)，超时则 kill + "
        "p.wait() 并返回 None（调用方按红处理）；已设 stdin=DEVNULL。"
        "这里 stdin 尤其关键：被它驱动的 `matlabc.py` 会去 import 本仓的 stdio "
        "组件，继承 stdin 就可能重演 R62-R31e 的挂死。",
}

# S4：`**kwargs` 间接传参的调用点 —— 静态看不到 stdout/stdin 到底是什么，
# 属于**已知盲区**，必须逐点登记，否则「看不见」会被当成「没问题」。
UNVERIFIABLE = {
    "matlabc_mcp.py|_run":
        "参数由 kwargs 字典间接传入（stdout=PIPE / stderr=STDOUT / "
        "stdin=DEVNULL 都在 dict 里）。已就近逐行核实：Popen 后紧跟 "
        "communicate(timeout=600)，超时则 _kill_tree + communicate(timeout=30)。"
        "**关键约束**：本进程 stdin 上跑的是 MCP JSON-RPC 协议，子进程若继承会"
        "偷走协议字节，故必须 stdin=DEVNULL（这不是洁癖，是正确性）。",
    "gui.py|_launch_gui.run":
        "除显式 stdout/stderr=PIPE 外还展开 `**_spawn`（Windows 下有 "
        "creationflags 等）。已就近核实：stdin=DEVNULL；长跑流式、由用户停止，"
        "见 POPEN_STREAMING 同名条目。",
}

CAPTURE_FUNCS = {"run", "check_output", "call", "check_call", "Popen"}


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _iter_py_files(root):
    seen = set()
    for d in SCAN_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames
                           if x not in (".git", "__pycache__", ".workbuddy",
                                        "docs", "tests", "node_modules")]
            for fn in sorted(filenames):
                if not fn.endswith(".py"):
                    continue
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, root).replace("\\", "/")
                if rel in seen:
                    continue
                seen.add(rel)
                yield rel, p


def _iter_test_files(root):
    base = os.path.join(root, "tests")
    if not os.path.isdir(base):
        return
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [x for x in dirnames if x not in ("__pycache__",)]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                p = os.path.join(dirpath, fn)
                yield os.path.relpath(p, root).replace("\\", "/"), p


def _enclosing_name(tree):
    """返回 {行号: **限定**函数名（`外层.内层`）}，用于登记键。

    两条都要：① 取最内层 —— `ast.walk` 是 BFS，外层先被访问到，用
    `setdefault` 会把嵌套闭包（如 gui.py 里 `_launch_gui` 内的 `run`）
    误归属给外层；② 保留外层前缀 —— 只写 `run` 这种通用名，登记键
    无法自解释，读表的人不知道在说哪一处。
    """
    spans = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans.append((getattr(n, "lineno", 0),
                          getattr(n, "end_lineno", n.lineno), n.name))
    chains = {}
    for ln in range(1, max((e for _s, e, _n in spans), default=0) + 1):
        names = sorted(((s, n) for s, e, n in spans if s <= ln <= e))
        if names:
            chains[ln] = ".".join(n for _s, n in names)
    return chains


def _kw(call):
    return {k.arg: k.value for k in call.keywords if k.arg}


def _has_kwargs_unpack(call):
    """调用里是否出现 `**xxx`（静态看不到展开后的键）。"""
    return any(k.arg is None for k in call.keywords)


def _captures_ast(kw):
    v = kw.get("capture_output")
    if isinstance(v, ast.Constant) and v.value is True:
        return True
    for k in ("stdout", "stderr"):
        node = kw.get(k)
        if node is not None and "PIPE" in ast.unparse(node):
            return True
    return False


def _has_ast(kw, name):
    return name in kw


def analyze_source(rel, src, on_problem):
    """对一份源码施加 S1/S2；返回捕获点列表 [(行号, 函数, 最内层名)]。

    `**kwargs` 展开的点无法静态判断捕获与否 —— 这类点**向外汇报**
    （blind 列表），由调用方要求登记，而不是当作干净放行。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        on_problem("%s: 语法错误，无法施加判据：%s" % (rel, e))
        return [], []
    owner = _enclosing_name(tree)
    sites = []
    blind = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                and f.value.id == "subprocess" and f.attr in CAPTURE_FUNCS):
            continue
        kw = _kw(n)
        who = owner.get(n.lineno, "<module>")
        unpack = _has_kwargs_unpack(n)
        capture = _captures_ast(kw)
        if not capture and not unpack:
            continue                      # 静态可见、且不捕获输出 -> 不在判据内
        if capture:
            sites.append((n.lineno, f.attr, who))
        if unpack:
            blind.append((n.lineno, f.attr, who))
        if not capture:
            continue                      # 只能靠盲区登记，下面的判据无从施加
        if not _has_ast(kw, "stdin"):     # S1
            on_problem("%s:%d subprocess.%s 捕获输出但未设 stdin="
                       "（会继承调用方句柄；本仓已有真实挂死案例）"
                       % (rel, n.lineno, f.attr))
        if f.attr != "Popen" and not _has_ast(kw, "timeout"):   # S2
            on_problem("%s:%d subprocess.%s 捕获输出但未设 timeout= "
                       "（挂住无上限）" % (rel, n.lineno, f.attr))
    return sites, blind


def scan(root):
    """返回 (problems, runtime_sites, test_sites, popen_keys, blind_keys)。"""
    problems = []
    runtime_sites = []
    test_sites = []
    popen_keys = set()
    blind_keys = set()
    for rel, path in _iter_py_files(root):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError as e:
            problems.append("%s: 读不到：%s" % (rel, e))
            continue
        sites, blind = analyze_source(rel, src, problems.append)
        for ln, func, who in sites:
            runtime_sites.append((rel, ln, func))
            if func == "Popen":
                popen_keys.add("%s|%s" % (rel, who))
        for _ln, _func, who in blind:
            blind_keys.add("%s|%s" % (rel, who))
    for rel, path in _iter_test_files(root):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError:
            continue
        sites, _blind = analyze_source(rel, src, lambda _m: None)
        for ln, func, who in sites:
            test_sites.append((rel, ln, func))
    return problems, runtime_sites, test_sites, popen_keys, blind_keys


def check_registry(keys, registry, tag, on_problem):
    """登记表两向核对：代码里有而未登记 → 抓；登记了但代码里没有 → 也抓。"""
    for k in sorted(keys):
        if k not in registry:
            on_problem("%s: 未登记：%s" % (tag, k))
    for k in sorted(registry):
        if k not in keys:
            on_problem("%s: 登记表里的 %s 已不在代码中（陈旧登记会掩盖新增点）"
                       % (tag, k))


def _selftest():
    """两向自证：坏样本必须红、好样本必须过；并对真实仓库做一致性核对。"""
    bad = good = 0
    fails = []

    def expect(tag, src, want_problem):
        nonlocal bad, good
        got = []
        analyze_source("sel.py", src, got.append)
        n = len(got[0]) if got else 0
        ok = (n > 0) == want_problem
        print("  [%s] %-46s -> %s%s"
              % ("反例" if want_problem else "正例", tag,
                 "抓到" if n else "放行", "" if ok else "   *** 不符预期 ***"))
        if not ok:
            fails.append(tag)
        if want_problem:
            bad += 1
        else:
            good += 1

    def expect_blind(tag, src, want):
        """盲区（`**kwargs`）必须被**报出来**，而不是当干净放行。"""
        nonlocal bad, good
        probs = []
        _sites, blind = analyze_source("sel.py", src, probs.append)
        ok = bool(blind) == want
        print("  [%s] %-46s -> %s%s"
              % ("反例" if want else "正例", tag,
                 "已报出盲区" if blind else "无盲区",
                 "" if ok else "   *** 不符预期 ***"))
        if not ok:
            fails.append(tag)
        if want:
            bad += 1
        else:
            good += 1

    # 反例 1：就是本轮修掉的那个真实缺陷（捕获输出 + 继承 stdin + 无 timeout）
    expect("捕获输出 + 继承 stdin + 无 timeout",
           "import subprocess\n"
           "def f(p):\n"
           "    return subprocess.run([p, '--help'], capture_output=True)\n",
           True)
    # 反例 2：切了 stdin 但没 timeout
    expect("切了 stdin、仍无 timeout",
           "import subprocess\n"
           "def f(p):\n"
           "    return subprocess.run([p], stdout=subprocess.PIPE,\n"
           "                          stdin=subprocess.DEVNULL)\n",
           True)
    # 反例 3：有 timeout 但继承 stdin
    expect("有 timeout、仍继承 stdin",
           "import subprocess\n"
           "def f(p):\n"
           "    return subprocess.run([p], stdout=subprocess.PIPE, timeout=10)\n",
           True)
    # 正例 1：两条都满足
    expect("stdin=DEVNULL + timeout（正确写法）",
           "import subprocess\n"
           "def f(p):\n"
           "    return subprocess.run([p], stdout=subprocess.PIPE,\n"
           "                          stdin=subprocess.DEVNULL, timeout=10)\n",
           False)
    # 正例 2：不捕获输出 -> 不在判据内（如 open/xdg-open 起浏览器）
    expect("不捕获输出（不在判据内）",
           "import subprocess\n"
           "def f(p):\n"
           "    subprocess.call(['open', p])\n",
           False)
    # 反例 4：stderr 单独 PIPE 也算捕获
    expect("仅 stderr=PIPE 也算捕获",
           "import subprocess\n"
           "def f(p):\n"
           "    return subprocess.run([p], stderr=subprocess.PIPE, timeout=5)\n",
           True)
    # 反例 5：`**kwargs` 盲区必须被报出（否则最关键的 MCP 点会隐形）
    expect_blind("**kwargs 间接传参（静态不可见）必须报盲区",
                 "import subprocess\n"
                 "def f(p, **kw):\n"
                 "    return subprocess.Popen([p], **kw)\n", True)
    expect_blind("无 kwargs -> 无盲区",
                 "import subprocess\n"
                 "def f(p):\n"
                 "    return subprocess.run([p], stdout=subprocess.PIPE,\n"
                 "                          stdin=subprocess.DEVNULL, timeout=5)\n",
                 False)

    # S3/S4 登记表两向
    def expect_reg(tag, keys, registry, want):
        got = []
        check_registry(keys, registry, "S3", got.append)
        ok = bool(got) == want
        print("  [%s] %-46s -> %s%s"
              % ("反例" if want else "正例", tag,
                 "抓到" if got else "放行", "" if ok else "   *** 不符预期 ***"))
        nonlocal bad, good
        if not ok:
            fails.append(tag)
        if want:
            bad += 1
        else:
            good += 1

    expect_reg("S3: 未登记的 Popen 捕获点", {"a.py|f"}, {}, True)
    expect_reg("S3: 已登记 + 齐全", {"a.py|f"}, {"a.py|f": "理由"}, False)
    expect_reg("S3: 陈旧登记（代码里已无此点）", set(), {"a.py|f": "理由"}, True)

    # 真实仓库核对：两张登记表都必须与代码一致
    root = repo_root()
    problems, r_sites, t_sites, popen_keys, blind_keys = scan(root)
    reg_problems = []
    check_registry(popen_keys, POPEN_STREAMING, "S3 Popen", reg_problems.append)
    check_registry(blind_keys, UNVERIFIABLE, "S4 盲区", reg_problems.append)
    print("  真实仓库：运行时捕获点 %d、tests 捕获点 %d；"
          "Popen 登记点 %d、盲区登记点 %d"
          % (len(r_sites), len(t_sites), len(popen_keys), len(blind_keys)))
    if problems or reg_problems:
        fails.append("真实仓库")
        print("  *** 真实仓库有 %d 项违规（S1/S2=%d, S3/S4=%d）***"
              % (len(problems) + len(reg_problems), len(problems),
                 len(reg_problems)))

    print("SELFTEST COUNTS {\"bad\": %d, \"good\": %d}" % (bad, good))
    if fails:
        print("SELFTEST FAILED: %s" % fails)
        return 1
    print("SELFTEST PASSED")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()

    root = repo_root()
    if not os.path.isdir(os.path.join(root, "tools")):
        print("check_subprocess_hygiene: 找不到 tools/（缺输入 → 红）")
        return 2
    problems, r_sites, t_sites, popen_keys, blind_keys = scan(root)
    check_registry(popen_keys, POPEN_STREAMING, "S3 Popen 未登记", problems.append)
    check_registry(blind_keys, UNVERIFIABLE, "S4 盲区未登记", problems.append)
    if problems:
        print("check_subprocess_hygiene: %d 项违规" % len(problems))
        for p in problems:
            print("  - " + p)
        return 1
    print("check_subprocess_hygiene: OK（运行时捕获点 %d 全部切断 stdin；"
          "run 类全部带 timeout；Popen 捕获点 %d、**kwargs 盲区 %d 全部登记；"
          "tests/ 另有 %d 点按设计不计入）"
          % (len(r_sites), len(popen_keys), len(blind_keys), len(t_sites)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
