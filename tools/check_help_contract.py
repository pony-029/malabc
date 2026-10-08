# -*- coding: utf-8 -*-
"""登记制护栏：入口脚本的「退出码契约」必须在**代码与帮助正文之间双向一致**。

动因（为什么退出码值得一道门）：
    本仓几乎所有自动化都靠退出码判断成败 —— CI 用 `--gate` 的非零码失败构建、
    `matlabc_flow --review-gate` 用 3 表示「已验证但未落地」、护栏用 2 表示
    「缺输入」。但退出码有一个隐蔽的退化方式：
        代码新增了一个码，帮助里没说  → 用户不知道这个码意味着什么，只能猜；
        帮助里写了一个码，代码不给   → 用户写了判分支，永远走不到（假契约）。
    两种都不会报错，只会在别人的 CI 里静静地错。

判据（三条，全部机械可查）：
    R1 「登记有依据」：EXIT_CONTRACT 里登记的每个码，必须在证据文件里以
        `return N` / `sys.exit(N)` / `exit_code = N` / `result["exit_code"] = N`
        之一真实出现。确实由解释器给出的（如「未捕获异常 → 1」）必须登记在
        NO_EVIDENCE 并写明原因 —— 这是**证伪式登记**，不是放行后门。
        **反向也要抓**：脚本里出现 `sys.exit(<字面量>)` 却没登记 → 红。
    R2 「帮助说全且不多说」：脚本模块 docstring 的「退出码」段解析出的码集合
        必须**等于**登记表的键集合。少写 → 红；多写 → 红。
    R3 「帮助有骨架」（棘轮）：docstring 必须含
        ① 用法/示例（且至少一条 `python <本脚本>` 的可复制命令行）
        ② 图示（≥3 行、每行 ≥3 个框线字符）
        ③ 「退出码」段且非空

  关于 R3 的诚实声明：它是**完整性棘轮**，不是质量判据。它只能防「帮助被无声
  缩水回六行」，**不能**保证写得好 —— 一份垃圾但含图、含示例、含退出码的帮助
  照样能过 R3。别把它当成「帮助质量已验证」。

两向自证：R1/R2/R3 各配独立坏样本（必须红）与好样本（必须过），
并对真实仓库做一次整体核对。

退出码：
    0 = 全部一致
    1 = 发现不一致（R1/R2/R3 任一红）
    2 = 缺输入（入口脚本缺失 / 解析不到 docstring → 红）

用法：
    python tools/check_help_contract.py             # 0=一致 1=不一致 2=缺输入
    python tools/check_help_contract.py --selftest   # 两向自证
"""
import argparse
import ast
import io
import os
import re
import sys

# ---------------------------------------------------------------------------
# 退出码契约的唯一事实源。每个码都要在 evidence 指的文件里有真实依据
# （见 R1），且必须与 docstring 的「退出码」段逐码一致（见 R2）。
# ---------------------------------------------------------------------------
CONTRACT = {
    "matlabc.py": {
        "codes": {
            0: "正常完成",
            1: "质量门禁未通过（--gate / --max-warnings / 契约问题 / 往返校验差异）",
            2: "参数或配置文件错误；或影响门禁失败（--operator-impact-gate-fail）",
        },
        "evidence": ("matlabc.py",),
    },
    "matlabc_flow.py": {
        "codes": {
            0: "正常完成（含「只产出补丁、未落盘」）",
            1: "步骤执行中出错",
            2: "未通过自证 / 前置条件不满足（已回退，产出人工检查点）",
            3: "已通过自证但 --review-gate 要求人工复核（未落地）",
        },
        "evidence": ("matlabc_flow.py", "agent_loop.py"),
    },
    "matlabc_ask.py": {
        "codes": {
            0: "正常（离线回显提示词也算成功）",
            1: "载入或生成报告失败",
            2: "参数不全（既没给 --dir 也没给 --json）",
        },
        "evidence": ("matlabc_ask.py",),
    },
    "matlabc_mcp.py": {
        "codes": {
            0: "从 stdin 收到 EOF，正常收工退出",
            1: "未捕获异常（由解释器给出）",
        },
        "evidence": (),
    },
    "gui.py": {
        "codes": {
            0: "正常（关窗 / --selftest 通过 / --help 打印完）",
            1: "启动期异常（极少数环境缺 tkinter；stderr 会给原因）",
        },
        "evidence": ("gui.py",),
    },
    "agent_loop.py": {
        "codes": {
            0: "自证通过（tier 0 完全干净 / tier 1 仍有残留但安全降级）",
            2: "未通过自证 → 已回退，产出人工检查点",
            3: "已通过自证但要求人工复核，未落地",
        },
        "evidence": ("agent_loop.py",),
        # agent_loop.py 是**库**（没有 CLI），示例只能挂在它的命令行入口上。
        # 这里显式声明「示例经由哪个脚本」，而不是给它开后门免检 ——
        # 免检会让 R3 在这一个文件上悄悄失效。
        "example_via": "matlabc_flow.py",
    },
}

# 确实由**解释器**给出的码（源码里找不到 return/sys.exit 依据），必须写明原因。
# 这不是放行后门：只有这里登记过的 (脚本, 码) 才允许缺依据。
NO_EVIDENCE = {
    ("matlabc_mcp.py", 0): "main() 正常返回到模块尾部，解释器以 0 退出（无显式 sys.exit）",
    ("matlabc_mcp.py", 1): "未捕获异常由解释器以 1 退出；本文件不捕获顶层异常",
    ("matlabc_ask.py", 0): "成功路径 return ai_cli.main(cli_argv)，0 由 ai_cli 给出",
    ("gui.py", 1): "tkinter 缺失等启动期异常未被捕获，由解释器以 1 退出；"
                   "main() 里所有 return 都是 0",
}

ENTRY_SCRIPTS = tuple(sorted(CONTRACT))

DIAGRAM_CHARS = set("┌└├│─┐┘┤┬┴┼▲▼◀▶╔╚╠║╗╝╣")
EXIT_HEADING = re.compile(r"退出码")
EXIT_LINE = re.compile(r"^\s*(\d+)\s*[=:：]")
EXAMPLE_RE_TMPL = r"python\s+%s\b"


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _docstring(path):
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError:
        return None, None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src, None
    return src, ast.get_docstring(tree, clean=False)


def _is_sep_line(s):
    """是不是「分隔线」（如 ───── 或 =====），用于跨过标题与正文之间的装饰。"""
    body = s.replace(" ", "")
    return bool(body) and len(body) >= 4 and \
        all(ch in "─-=~—" for ch in body)


def parse_exit_section(doc):
    """从 docstring 解析「退出码」段的码集合；解析不到返回 None。"""
    if not doc:
        return None
    lines = doc.split("\n")
    for i, ln in enumerate(lines):
        if not EXIT_HEADING.search(ln):
            continue
        codes = set()
        for sub in lines[i + 1:]:
            m = EXIT_LINE.match(sub)
            if m:
                codes.add(int(m.group(1)))
                continue
            if codes:
                break           # 码已收集完，遇到第一行不是码的就收工
            s = sub.strip()
            if not s:
                continue        # 标题与码之间允许空行
            if _is_sep_line(s):
                continue        # 也不允许「分隔线」把分段切断（matlabc.py 的样式）
            break               # 别的正文 → 这一段其实没有退出码
        if codes:
            return codes
    return None


def has_diagram(doc, min_lines=3, min_chars=3):
    """≥min_lines 行、每行 ≥min_chars 个框线字符（一个字 1 个字符）。"""
    if not doc:
        return False
    n = 0
    for ln in doc.split("\n"):
        if sum(1 for ch in ln if ch in DIAGRAM_CHARS) >= min_chars:
            n += 1
    return n >= min_lines


def has_example(doc, script):
    if not doc:
        return False
    return re.search(EXAMPLE_RE_TMPL % re.escape(script), doc) is not None


def _code_has_evidence(src, code):
    """源码里是否存在这个码的退出依据（四种写法）。"""
    if not src:
        return False
    pats = (
        r"\breturn\s+%d\b" % code,
        r"\bsys\.exit\(\s*%d\s*\)" % code,
        r"\bexit_code\s*=\s*%d\b" % code,
        r"\[\s*[\"']exit_code[\"']\s*\]\s*=\s*%d\b" % code,
    )
    for p in pats:
        if re.search(p, src):
            return True
    return False


def _literal_sys_exits(src):
    """源码里所有 `sys.exit(<整数字面量>)` 的码集合。"""
    out = set()
    if not src:
        return out
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if not (isinstance(f, ast.Attribute) and f.attr == "exit"
                and isinstance(f.value, ast.Name) and f.value.id == "sys"):
            continue
        if len(n.args) != 1:
            continue
        a = n.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, int) \
                and not isinstance(a.value, bool):
            out.add(a.value)
    return out


def audit(root, on_problem):
    """对真实仓库施加 R1/R2/R3；返回检查过的脚本数。"""
    n = 0
    for script in ENTRY_SCRIPTS:
        spec = CONTRACT[script]
        path = os.path.join(root, script)
        if not os.path.exists(path):
            on_problem("R0 %s 不存在（缺输入 → 红）" % script)
            continue
        src, doc = _docstring(path)
        if doc is None:
            on_problem("R0 %s 解析不到模块 docstring（缺输入 → 红）" % script)
            continue
        n += 1

        # ---- R1：登记有依据（含反向） ----
        for code in sorted(spec["codes"]):
            ok = False
            for ev in spec.get("evidence") or ():
                evp = os.path.join(root, ev)
                if not os.path.exists(evp):
                    on_problem("R1 %s: 证据文件 %s 不存在（缺输入 → 红）"
                               % (script, ev))
                    continue
                evsrc, _ = _docstring(evp)
                if _code_has_evidence(evsrc, code):
                    ok = True
                    break
            if not ok and (script, code) in NO_EVIDENCE:
                ok = True
            if not ok:
                on_problem("R1 %s: 登记了退出码 %d，但证据文件 %s 里找不到任何依据"
                           "（return %d / sys.exit(%d) / exit_code = %d）—— "
                           "凭空登记的退出码会让用户写出永远走不到的分支"
                           % (script, code, list(spec.get("evidence") or ()),
                              code, code, code))
        registered = set(spec["codes"])
        for code in sorted(_literal_sys_exits(src) - registered):
            on_problem("R1 %s: 源码里有 sys.exit(%d)，但 EXIT_CONTRACT 没登记它 —— "
                       "新增退出码必须同步登记并写进帮助" % (script, code))

        # ---- R2：帮助说全且不多说 ----
        declared = parse_exit_section(doc)
        if declared is None:
            on_problem("R2 %s: docstring 里解析不到非空的「退出码」段" % script)
        elif declared != registered:
            missing = sorted(registered - declared)
            extra = sorted(declared - registered)
            on_problem("R2 %s: 帮助与登记表不一致（少写 %s / 多写 %s）"
                       % (script, missing or "无", extra or "无"))

        # ---- R3：帮助有骨架（棘轮） ----
        ex_via = spec.get("example_via") or script
        if not has_example(doc, ex_via):
            on_problem("R3 %s: docstring 里没有一条 `python %s ...` 的可复制示例"
                       % (script, ex_via))
        if not has_diagram(doc):
            on_problem("R3 %s: docstring 里没有图示（需要 ≥3 行、每行 ≥3 个框线字符）"
                       % script)
    return n


def on_problem_collector(bucket):
    def _cb(msg):
        bucket.append(msg)
    return _cb


def _selftest():
    """两向自证：R1/R2/R3 各配独立坏样本与好样本，并对真实仓库整体核对。

    约定（**容易写反，所以写在这里**）：
        expect(tag, detected, want_problem)
          detected     = 判据认为「有问题」——也就是这道门会变红的那个布尔值
          want_problem = 我们希望它是反例(True)还是正例(False)
        两者一致才算这条自证通过。表达式必须写成「判据的检测结果」，
        不能写成「我的断言是否成立」，否则正反例会整片颠倒
        —— 首版就是这么错的，SELFTEST 立刻把它抓了出来。
    """
    bad = good = 0
    fails = []

    def expect(tag, detected, want_problem):
        nonlocal bad, good
        ok = (bool(detected) == bool(want_problem))
        print("  [%s] %-52s -> %s%s"
              % ("反例" if want_problem else "正例", tag,
                 "抓到" if detected else "放行",
                 "" if ok else "   *** 不符预期 ***"))
        if not ok:
            fails.append(tag)
        if want_problem:
            bad += 1
        else:
            good += 1

    # ---- R2：退出码段的解析 ----
    # 下面每个 detected_* 都是「判据会不会报问题」本身，不是「我的断言成不成立」。
    doc_ok = ("用法：\n    python x.py a\n\n退出码：\n"
              "    0  = 好\n    1  = 也不好\n\n边界：\n")
    expect("R2 正常退出码段解析出 {0,1}",
           parse_exit_section(doc_ok) != {0, 1}, False)
    expect("R2 完全没有退出码段",
           parse_exit_section("用法：\n    x\n") is None, True)
    expect("R2 空退出码段",
           parse_exit_section("退出码：\n\n用法：\n") is None, True)
    expect("R2 标题与码之间有分隔线（matlabc.py 的样式）",
           parse_exit_section("退出码\n──────\n  0  = a\n  2  = b\n\n正文\n")
           != {0, 2}, False)

    # ---- R1：依据识别（四种写法都要认，且不许把 20 认成 2） ----
    expect("R1 认 return 2",
           not _code_has_evidence("def f():\n    return 2\n", 2), False)
    expect("R1 认 sys.exit(2)",
           not _code_has_evidence("sys.exit(2)\n", 2), False)
    expect("R1 认 exit_code = 2",
           not _code_has_evidence("exit_code = 2\n", 2), False)
    expect('R1 认 result["exit_code"] = 3',
           not _code_has_evidence('result["exit_code"] = 3\n', 3), False)
    expect("R1 不把 return 20 误认成 return 2",
           _code_has_evidence("def f():\n    return 20\n", 2), False)
    expect("R1 不把 sys.exit(21) 误认成 2",
           _code_has_evidence("sys.exit(21)\n", 2), False)
    expect("R1 反向：未登记的 sys.exit(7) 必须被判为问题",
           bool(_literal_sys_exits("import sys\nsys.exit(7)\n") - {2}), True)
    expect("R1 不把 sys.exit(rc) 当字面量（无害）",
           bool(_literal_sys_exits("import sys\nsys.exit(rc)\n") - {2}), False)

    # ---- R3：骨架识别 ----
    # 注意：图示要求「≥3 行、每行 ≥3 个框线字符」，中段那行只有两个角标是不够的。
    good_doc = ("用法：\n    python x.py a --b\n\n"
                "    ┌──────┐\n    │ 一步 │────\n    └──────┘\n\n"
                "退出码：\n    0  = 好\n")

    def skeleton_problem(doc):
        return (not has_example(doc, "x.py") or not has_diagram(doc)
                or parse_exit_section(doc) is None)

    expect("R3 好文档（示例+图示+退出码）", skeleton_problem(good_doc), False)
    expect("R3 缺示例（裸 python，无脚本名）",
           skeleton_problem("用法：\n    python\n\n退出码：\n    0  = a\n"), True)
    expect("R3 缺图示（只有一行框线）",
           skeleton_problem("用法：\n    python x.py a\n\n    ┌──────┐\n\n"
                            "退出码：\n    0  = a\n"), True)
    expect("R3 图示不足（每行框线字符 <3）",
           skeleton_problem("用法：\n    python x.py a\n\n"
                            "    ┌─┐\n    │ │\n    └─┘\n\n退出码：\n    0  = a\n"),
           True)

    # ---- 真实仓库整体核对 ----
    root = repo_root()
    probs = []
    n = audit(root, on_problem_collector(probs))
    print("  真实仓库：核对 %d 个入口脚本，发现 %d 项不一致"
          % (n, len(probs)))
    for p in probs[:12]:
        print("      " + p)
    if len(probs) > 12:
        print("      ...（还有 %d 项）" % (len(probs) - 12))
    if probs:
        fails.append("真实仓库")
        bad += 1
    else:
        good += 1

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
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
        print("check_help_contract: 找不到 tools/（缺输入 → 红）")
        return 2
    probs = []
    n = audit(root, on_problem_collector(probs))
    if n == 0:
        print("check_help_contract: 一个入口脚本都没核对到（缺输入 → 红）")
        return 2
    if probs:
        print("check_help_contract: %d 项不一致" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_help_contract: OK（%d 个入口脚本的退出码在代码与帮助之间双向一致；"
          "帮助骨架：示例 + 图示 + 退出码 均具备）" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
