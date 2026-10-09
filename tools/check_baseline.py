#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""公平基线门：把「这次改动有没有让测试变差」做成**可重跑、按集合比对**的判定。

为什么需要它 —— 本仓的测试集**本来就不全绿**（历史遗留一百多个 failed）。
在一个既不绿又不断改的工作流里，「多少个失败」这个数字**证明不了任何事**：

    改动前 124 failed        改成 123 failed
    可能 ① 修好一个           也可能 ② 修好两个又弄坏一个
    比个数分不出来 —— 只有比 **nodeid 集合** 才能。
        after - before = 回归（新出现的失败）      ← 唯一算「变差」的
        before - after = 不再失败（修好/被改名/被 skip）

这会直接影响判断标准：**个数相等而集合不同，同样是回归。**

一条命令给出结论（只有 --full 才真跑测试）：

    python tools/check_baseline.py             # 前置条件体检 + 判定逻辑两向自证（秒级）
    python tools/check_baseline.py --selftest  # 只做两向自证（check_all.py 走这条）
    python tools/check_baseline.py --full      # 真基线：两侧各跑一次全量（数分钟）

--full 做的事（与手工流程逐字一致，所以两者结果可比）：

    ① git archive HEAD        导出**未改动树**到仓库外（不碰工作区）
    ② 复制**当前** tests/     同测试集 + 同解释器 ⇒ 只隔离「源码改动」这一个变量
    ③ 两侧都跑 pytest -q -k <过滤>（stdin 切断、带墙钟超时）
    ④ 按 nodeid **集合**比对

为什么默认不跑 --full：两侧各一次全量是分钟级。把分钟级的东西塞进 check_all 的
默认路径，所有人都会开始绕开 check_all —— 那时的实际覆盖率是 **0**，比慢更糟。
所以进 check_all 的是「机制自证 + 前置条件体检」，真基线由人显式触发。

    体检能证的：仓库可导出 HEAD、测试集在、git/pytest 可用、判定逻辑正反都灵
    体检不证的：**这一版相对上一版到底有没有回归** —— 那需要 --full

退出码：0 = 通过（默认模式：机制+前置条件；--full：无回归）；1 = --full 发现回归，或机制自证失败；2 = 缺输入/环境不可用

用法：
  python tools/check_baseline.py
  python tools/check_baseline.py --selftest
  python tools/check_baseline.py --full [--filter "not r36"] [--work DIR]
"""
import os
import re
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

# 只认**行首**的 FAILED / ERROR。为什么必须锚定行首：
# pytest 的汇总段落与进度行里也会出现 failed/passed 这些词
# （例如 "1 failed, 2 passed in 1.2s"），行内任意位置匹配会把它们当 nodeid 捞出来。
FAILED_RE = re.compile(r"^FAILED\s+(\S+)", re.M)
ERROR_RE = re.compile(r"^ERROR\s+(\S+)", re.M)

SUITE = os.path.join("tests", "test_matlabc.py")
DEFAULT_FILTER = "not r33"


def parse_failed(text):
    """从 pytest 输出里抽出失败/出错的 **nodeid 集合**。

    `ERROR tests/a.py`（收集期错误，没有 ::）也要算 —— 它同样意味着「没通过」。
    """
    out = set()
    for rx in (FAILED_RE, ERROR_RE):
        for m in rx.finditer(text):
            out.add(m.group(1))
    return out


def compare_failure_sets(before, after):
    """按**集合**比对两侧失败 nodeid。返回 dict（regressions/fixed/common）。

    纪律：只有 regressions 非空才算回归；个数相等而集合不同**同样是回归**。
    """
    b = set(before)
    a = set(after)
    return {
        "regressions": sorted(a - b),
        "fixed": sorted(b - a),
        "common": sorted(a & b),
        "n_before": len(b),
        "n_after": len(a),
    }


def baseline_problems(before, after, on_problem):
    """把比对结果翻译成「问题」列表；无回归时返回空。"""
    res = compare_failure_sets(before, after)
    if res["regressions"]:
        head = res["regressions"][:8]
        on_problem(
            "基线回归：%d 个 nodeid 新失败（前 %d / 后 %d，共同 %d）\n      %s"
            % (len(res["regressions"]), res["n_before"], res["n_after"],
               len(res["common"]), "\n      ".join(head)))
    return res


# ---------------------------------------------------------------- 前置条件

def _git(repo, argv, timeout=120):
    return subprocess.run(["git"] + list(argv), cwd=repo,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout)


def check_prerequisites(root, on_problem):
    """默认模式能真做的体检（不跑测试）。返回体检项数。"""
    n = 0
    n += 1
    if not os.path.isdir(os.path.join(root, ".git")):
        on_problem("P1 %s 不是 git 仓库：无法导出 HEAD（基线的前提）" % root)
    n += 1
    try:
        r = _git(root, ["rev-parse", "HEAD^{tree}"])
        if r.returncode != 0:
            on_problem("P2 git rev-parse HEAD^{tree} 失败：%s"
                       % r.stdout.decode("utf-8", "replace").strip()[:200])
    except (OSError, subprocess.TimeoutExpired) as e:
        on_problem("P2 无法调用 git（%s）：--full 会失败" % type(e).__name__)
    n += 1
    if not os.path.isfile(os.path.join(root, SUITE)):
        on_problem("P3 测试集不存在：%s（基线无从比对）" % SUITE)
    n += 1
    if not os.path.isdir(os.path.join(root, "tests")):
        on_problem("P4 tests/ 目录不存在：无法把当前测试集复制进导出树")
    return n


# ---------------------------------------------------------------- --full

def export_head(repo, dest):
    """git archive HEAD -> dest。工作区**不被触碰**。"""
    if os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    tar = dest.rstrip("\\/") + ".tar"
    _git(repo, ["archive", "--format=tar", "HEAD", "-o", tar], timeout=600)
    r = subprocess.run(["tar", "-xf", tar, "-C", dest],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("解包 HEAD 失败：%s"
                           % r.stdout.decode("utf-8", "replace")[-300:])
    return dest


def copy_current_tests(repo, tree):
    """把**当前** tests/ 覆盖进导出树 —— 同测试集才能只隔离源码改动。"""
    src = os.path.join(repo, "tests")
    dst = os.path.join(tree, "tests")
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)


def run_suite(cwd, kfilter, py, timeout=3600):
    argv = [py, "-m", "pytest", SUITE, "-q"]
    if kfilter:
        argv += ["-k", kfilter]
    r = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def run_full(repo, work, kfilter, py, on_problem):
    """真基线：导出 HEAD -> 复制当前测试集 -> 两侧跑 -> 比集合。"""
    head_tree = os.path.join(work, "head")
    print("[1/4] git archive HEAD -> %s" % head_tree)
    export_head(repo, head_tree)
    print("[2/4] 把当前 %s 复制进导出树（同测试集）" % SUITE)
    copy_current_tests(repo, head_tree)

    nhead = count_tests(os.path.join(head_tree, SUITE))
    nwork = count_tests(os.path.join(repo, SUITE))
    print("      测试函数数：HEAD 树 %d / 当前树 %d" % (nhead, nwork))
    if nhead != nwork:
        # 「同测试集」是这套比对的**前提**；前提不成立 ⇒ 结论无效 ⇒ 缺输入(2)，
        # 不是「发现回归」(1)。用异常把它抬到 main 的正确分类里去。
        raise RuntimeError(
            "两侧测试集不同（%d vs %d）：「同测试集」这个前提不成立，结论无效"
            % (nhead, nwork))

    print("[3/4] 跑 HEAD 树（-k %r）…" % kfilter)
    _, out_head = run_suite(head_tree, kfilter, py)
    print("[4/4] 跑当前树（-k %r）…" % kfilter)
    _, out_work = run_suite(repo, kfilter, py)

    fb = parse_failed(out_head)
    fa = parse_failed(out_work)
    res = baseline_problems(fb, fa, on_problem)
    print('BASELINE COUNTS {"regressions": %d, "fixed": %d, "common": %d}'
          % (len(res["regressions"]), len(res["fixed"]), len(res["common"])))
    if res["fixed"]:
        print("  修好/不再失败 %d 个（前 %d -> 后 %d）：%s"
              % (len(res["fixed"]), res["n_before"], res["n_after"],
                 ", ".join(res["fixed"][:5])))
    return res


def count_tests(path):
    """数一数测试文件里有多少个 test_ 函数（用于验证「两侧同一测试集」）。"""
    try:
        import ast
        with open(path, "rb") as fh:
            tree = ast.parse(fh.read())
    except Exception:
        return -1
    return sum(1 for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"))


# ---------------------------------------------------------------- 自证

def _expect(tag, detected, want_problem, tally):
    """detected=判据认为「有问题」；want_problem=我们期望它认为有问题。

    两向都必须成立：坏样本要能红（want=True 且 detected=True），
    好样本不能误伤（want=False 且 detected=False）。
    """
    if detected == want_problem:
        tally[0 if want_problem else 1] += 1
        return True
    print("  [selftest] %s 未按预期（detected=%s want_problem=%s）"
          % (tag, detected, want_problem))
    return False


def selftest():
    """两向自证：坏样本要能红、好样本要能过。

    打印机器可读行：SELFTEST COUNTS {"bad": N, "good": M}
    """
    tally = [0, 0]   # [bad, good]

    # 坏样本1：新出现一个失败 -> 必须报回归
    b = []
    baseline_problems(["a::t1"], ["a::t1", "a::t2"], b.append)
    _expect("坏样本1(新增失败)", bool(b), True, tally)

    # 坏样本2：**个数相同、集合不同** -> 必须报回归。
    # 这是这道门存在的理由：比个数的实现会在这里说「没变」。
    b = []
    baseline_problems(["a::t1", "a::t2"], ["a::t1", "a::t3"], b.append)
    _expect("坏样本2(同数异集)", bool(b), True, tally)

    # 坏样本3：收集期 ERROR 也必须算「没通过」
    b = []
    baseline_problems([], ["tests/a.py"], b.append)
    _expect("坏样本3(收集期ERROR)", bool(b), True, tally)

    # 好样本1：两侧完全相同 -> 不得报回归
    b = []
    r = baseline_problems(["a::t1", "a::t2"], ["a::t1", "a::t2"], b.append)
    _expect("好样本1(完全相同)", bool(b), False, tally)
    # ⚠ 这里曾经写成 `r["common"] == 2` —— common 是**列表**不是数，恒为 True，
    # 于是这条断言永远不会红。第一次跑自证时被它自己打出来了：
    # 又一个「测量工具自身的 bug」。所以这里显式写 len()。
    if len(r["common"]) != 2:
        print("  [selftest] 好样本1 的 common 计数不对：%r" % r)

    # 好样本2：只修好、没弄坏 -> 不得报回归（fixed 非空是**好消息**）
    b = []
    r = baseline_problems(["a::t1", "a::t2"], ["a::t1"], b.append)
    _expect("好样本2(只修好)", bool(b), False, tally)
    if r["fixed"] != ["a::t2"]:
        print("  [selftest] 好样本2 的 fixed 不对：%r" % r)

    # 门自身完整性：parse_failed 必须**只认行首**。
    # 它一旦错了，这道门给出的每一个结论都是废的 —— 所以它自己也要被查。
    txt = ("tests/test_x.py .F.\n"
           "=========================== short test summary info "
           "===========================\n"
           "FAILED tests/test_x.py::test_a - AssertionError: boom\n"
           "ERROR tests/test_y.py\n"
           "1 failed, 1 error, 2 passed, 1 skipped in 1.20s\n"
           "2 failed in 0.10s\n")
    got = parse_failed(txt)
    want = {"tests/test_x.py::test_a", "tests/test_y.py"}
    if got == want:
        tally[1] += 1
    else:
        print("  [selftest] 坏样本4 未触发 —— parse_failed 结果不对："
              "得到 %r，期望 %r（门自身失效）" % (sorted(got), sorted(want)))

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (tally[0], tally[1]))
    return 0 if (tally[0] >= 3 and tally[1] >= 3) else 1


# ---------------------------------------------------------------- main

def _write_help(text):
    for s in (sys.stdout, sys.stderr):
        if s is not None and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
        return True
    except Exception:
        return False


def _arg(argv, name, default=None):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
    return default


def main(argv):
    if "--help" in argv or "-h" in argv:
        if not _write_help(__doc__):
            return 2
        return 0
    if "--selftest" in argv:
        return selftest()

    root = _arg(argv, "--root", _ROOT)
    kfilter = _arg(argv, "--filter", DEFAULT_FILTER)
    work = _arg(argv, "--work",
                os.path.join(os.path.dirname(os.path.normpath(root)),
                             "_baseline_cb"))

    # 前置条件不具备 = **缺输入**（rc=2），不是「发现违规」（rc=1）。
    # 为什么分得这么细：`check_all.py --tools-dir <别处>` 的复用场景里，
    # 对方目录很可能不是 git 仓库 —— 那不是「基线回归」，不该报成红。
    missing = []
    n = check_prerequisites(root, missing.append)
    if missing:
        print("check_baseline: 缺输入 —— 基线跑不起来（%d 项）" % len(missing))
        for p in missing:
            print("  - %s" % p)
        return 2

    # 门**自身**的两向自证必须先过：一个不自证的门是「可能永远绿的门」。
    self_problems = []
    tally = selftest_probe(self_problems)
    if self_problems:
        print("check_baseline: FAIL —— 门自身的两向自证没通过（%d 项）"
              % len(self_problems))
        for p in self_problems:
            print("  - %s" % p)
        return 1

    if "--full" in argv:
        regressions = []
        try:
            run_full(root, work, kfilter, sys.executable, regressions.append)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
            print("check_baseline: 缺输入 —— %s: %s" % (type(e).__name__, e))
            return 2
        if regressions:
            print("check_baseline: FAIL（--full 发现 %d 项）" % len(regressions))
            for p in regressions:
                print("  - %s" % p)
            return 1
        print("check_baseline: OK（--full：按 nodeid 集合比对两侧，无回归）")
        return 0

    print("check_baseline: OK（前置条件 %d 项 + 判定逻辑两向自证 %s；"
          "完整基线请显式跑 --full —— 它会真跑两侧全量，分钟级）" % (n, tally))
    return 0


def selftest_probe(sink):
    """复用 selftest 的计数，但不打印（默认模式里的机制自证）。"""
    import io
    real = sys.stdout
    buf = io.StringIO()
    try:
        sys.stdout = buf
        rc = selftest()
    finally:
        sys.stdout = real
    text = buf.getvalue()
    m = re.search(r"SELFTEST COUNTS (\{.*\})", text)
    if rc != 0 or m is None:
        sink.append("内部两向自证未通过：%s" % text.strip()[-200:])
        return "未通过"
    return m.group(1)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
