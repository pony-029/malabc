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

    ① git archive HEAD        导出**未改动树**到 `<work>/head-<时间戳>-<pid>`
                              （**唯一目录**，不是固定目录 —— 见下面的 ⚠）

    ⚠ 工作目录必须是**干净**的，而本机 safe-delete 守卫在对 200+ 项的目录
      做批量删除时会**直接终止进程**（不是抛异常，`try/except` 兜不住）。
      所以这里**从不删除旧目录**：每次开唯一目录。`_prepare_dir` 只用于小目录
      （tests/），并且「删不掉 -> 改名归档 -> 还不行就抛」，绝不带着脏目录继续
      —— 脏目录会让两侧比对结论**静默失真**，而那正是这道门存在的理由。
      副作用：work 目录会攒下历次导出树，请自行清理（它只占磁盘，不影响结论）。

    ⚠ 工作目录必须是**干净**的：删不掉旧目录时**改名归档**（不吞掉失败）。
      本机 safe-delete 守卫会拒绝批量删除 200+ 项的目录，而旧实现用
      `ignore_errors=True` 把它吞了 —— 那道门在本机**根本跑不起来**。
      实在既删不掉也改不了名就抛：绝不带着脏目录继续，否则比对结论静默失真。
    ② 复制**当前** tests/     同测试集 + 同解释器 ⇒ 只隔离「源码改动」这一个变量
    ③ 两侧都跑 pytest -q -k <过滤>（stdin 切断、带墙钟超时）
    ④ 按 nodeid **集合**比对

为什么默认不跑 --full：两侧各一次全量是分钟级。把分钟级的东西塞进 check_all 的
默认路径，所有人都会开始绕开 check_all —— 那时的实际覆盖率是 **0**，比慢更糟。
所以进 check_all 的是「机制自证 + 前置条件体检」，真基线由人显式触发。

    体检能证的：仓库可导出 HEAD（**含 `git worktree` 形态：`.git` 是文件**）、
                测试集在、git/pytest 可用、判定逻辑正反都灵
    体检不证的：**这一版相对上一版到底有没有回归** —— 那需要 --full

    ⚠ 「仓库」的判据见 `_is_git_repo()`：**两种形态都算** —— `.git` 是目录（普通仓库），
      或 `.git` 是首行 `gitdir:` 指向**存在目录**的文件（`git worktree`）。旧实现只认
      前者，于是在 worktree 里恒判「不是仓」、`check_all` 跑不完 ⇒ 用
      `git worktree add` 起的**对照组只能跑 pytest**、证不了门禁（R53 实测）。
      那是**测量工具自己**的缺陷，不是被测对象的。

退出码：0 = 通过（默认模式：机制+前置条件；--full：无回归）；1 = --full 发现回归，或机制自证失败；2 = 缺输入/环境不可用

用法：
  python tools/check_baseline.py
  python tools/check_baseline.py --selftest
  python tools/check_baseline.py --full [--filter "not r36"] [--work DIR]
"""
import io
import os
import re
import shutil
import subprocess
import sys
import time

# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族，
# 或本门独有的机制名）。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "P1–P4/T1"

# H3（R73）：越出签名族、但仍由本门发出的判据前缀。
ROW_EXTRA = "B2,B3"
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

def _is_git_repo(root):
    """`root` 是不是 git 仓库 —— **两种形态**都算。

    ① 普通仓库 / 子模块：`.git` 是**目录**。
    ② `git worktree add` 出来的工作树：`.git` 是**文件**，首行 `gitdir: <路径>`
       指向真正的 git 目录（主仓 `.git/worktrees/<name>`）。

    ⚠ 旧实现只认 ①（`os.path.isdir(root/.git)`）：worktree 里 P1 恒红、
      `check_all` 跑不完（R53 实测）——那是**测量工具自己**的缺陷。

    ⚠ `gitdir:` 指向的目标**必须真的存在且是目录**：只看到 `gitdir:` 字样就放行，
      等于把「是不是仓」换成「像不像仓」，会把**损坏的**工作树也算成仓。

    ⚠ 与 `agent_loop.py::_is_git_repo` 是**两份实现**（tools 不 import 产品模块），
      但 `tests/test_matlabc.py::test_r54_git_repo_detection_*` 强制二者**逐例一致**。
    """
    dot = os.path.join(root, ".git")
    if os.path.isdir(dot):
        return True
    if not os.path.isfile(dot):
        return False
    try:
        with io.open(dot, "r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except (OSError, IOError):
        return False
    first = first.strip()
    if not first.startswith("gitdir:"):
        return False
    target = first[len("gitdir:"):].strip()
    if not target:
        return False
    if not os.path.isabs(target):
        target = os.path.join(root, target)
    return os.path.isdir(target)


def _git(repo, argv, timeout=120):
    return subprocess.run(["git"] + list(argv), cwd=repo,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout)


def check_prerequisites(root, on_problem):
    """默认模式能真做的体检（不跑测试）。返回体检项数。"""
    n = 0
    n += 1
    if not _is_git_repo(root):
        on_problem("P1 %s 不是 git 仓库（`.git` 既不是目录，也不是首行 `gitdir:` "
                   "指向存在目录的文件）：无法导出 HEAD（基线的前提）" % root)
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

def _prepare_dir(dest, remove=None, rename=None, note=None):
    """把 dest 变成一个**空目录**；做不到就抛异常。

    ⚠ 本机有 safe-delete 守卫（阈值 50 项/轮）：一棵 `git archive` 导出树有 200+ 项，
      `shutil.rmtree` 会被**拒绝**。旧实现写的是
      `shutil.rmtree(dest, ignore_errors=True)` —— 它把这个失败**吞掉**，
      紧接着 `os.makedirs` 撞 `FileExistsError`，死在一个离真因很远的地方，
      而且这道门在本机**完全不可用**（R43 实测：rc=1，只打出 [1/4] 一行）。
    ⇒ 两件事都改掉：
      ① 删不掉就**改名归档**（不触发任何删除语义，旧目录还留在磁盘上可复查）；
      ② 绝不用 ignore_errors 吞掉"清理失败" —— 清不掉就抛，
         **绝不带着脏目录继续**：脏目录会让「基线」混进上一次的文件，
         两侧比对结论会**静默失真**，而那正是这道门存在的理由。

    `remove` / `rename` 可注入，是为了让自证能**真的**制造"删不掉"这个场景，
    而不是靠假装。
    """
    if os.path.isdir(dest):
        try:
            (remove or shutil.rmtree)(dest)
        except OSError:
            pass
        if os.path.isdir(dest):
            stamp = time.strftime("%Y%m%d-%H%M%S")
            alt = dest + "_old_" + stamp
            n = 1
            while os.path.exists(alt):
                alt = dest + "_old_" + stamp + "_%d" % n
                n += 1
            try:
                (rename or os.rename)(dest, alt)
            except OSError as e:
                raise RuntimeError(
                    "%s 既删不掉也改不了名（%s）：不能带着脏目录继续 —— "
                    "脏目录会让基线比对静默失真" % (dest, e))
            if os.path.isdir(dest):
                # 改名**调用没报错、目录却还在** —— 这种"假装成功"的清理器
                # 比报错更危险：旧实现的病根就是它。所以再验一次。
                raise RuntimeError(
                    "%s 清理失败：改名调用没报错但目录还在 —— 不能带着脏目录"
                    "继续（基线比对会静默失真）" % dest)
            (note or print)(
                "      [note] %s 删不掉（本机 safe-delete 会拦大目录），"
                "改名归档 -> %s" % (dest, os.path.basename(alt)))
    os.makedirs(dest)
    return dest


def _unique_dir(work, base):
    """在 work 下开一个**唯一**空目录并返回它。

    为什么不复用固定目录再删掉：本机的 safe-delete 守卫（阈值 50 项/轮）在对一棵
    200+ 项的导出树 `shutil.rmtree` 时**直接终止进程** —— 不是抛 OSError，
    所以 `try/except` **兜不住**（R43 实测：`--full` 打完 `[1/4]` 就没了，rc=1）。
    唯一目录从根上不需要任何删除动作。
    """
    os.makedirs(work, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    cand = os.path.join(work, "%s-%s-%d" % (base, stamp, os.getpid()))
    n = 1
    while os.path.exists(cand):
        cand = os.path.join(work, "%s-%s-%d_%d" % (base, stamp, os.getpid(), n))
        n += 1
    os.makedirs(cand)
    return cand


def export_head(repo, work):
    """git archive HEAD -> work 下的**唯一**空目录；返回该目录。工作区不被触碰。

    ⚠ 这里**不删除任何已有目录**，见 `_unique_dir` 的注释：本机守卫会直接终止
      进程，而不是抛异常。
    """
    dest = _unique_dir(work, "head")
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
    # tests/ 很小（远低于守卫阈值），所以这里可以安全地"清空后重建"。
    # 为什么不能简单 copytree：copytree 要求 dst 不存在，而"叠在导出树的旧
    # 测试集上"会让「同测试集」这个前提失效、比对结论直接作废。
    _prepare_dir(dst)
    for name in sorted(os.listdir(src)):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)


def run_suite(cwd, kfilter, py, timeout=3600):
    argv = [py, "-m", "pytest", SUITE, "-q"]
    if kfilter:
        argv += ["-k", kfilter]
    r = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", "replace")


# ── R43：baseline 的**已登记环境噪声** ───────────────────────────────────────
#
# `git archive HEAD` 的导出树**不是 git 仓库**。凡是要读 `.git` 的门，在 before
# 侧必然多红一次 —— 那是**环境差异**，不是回归。R43 实测它精确地落在：
#
#     tests/test_matlabc.py::test_r30_static_guards_all_clean
#
# （该测试会在树内跑 `tools/check_all.py`，其中 `check_baseline.py` 默认模式的
#   前置条件 P1 需要 `.git`，于是返回 2。）
#
# 为什么必须**写下来**而不是"心里知道"：它会安静地混进 `fixed` 读数，
# 从而**掩盖同一个 nodeid 上真实的修复**（"修好了"和"环境不同"长得一模一样）。
# 所以按本仓一贯的登记制处理，并且双向核对：
#
#     已登记 + 这次出现了    -> 放行（打印原因）
#     未登记 + 这次出现了    -> 红（B2：新噪声必须解释）
#     已登记 + 这次没出现    -> 红（B3：陈旧登记 —— 原因已消失，登记是假的）
#
# 第三条不是洁癖：如果有人把 P1 改成"只在 --full 下要求 .git"，这条登记就立刻
# 过期，B3 会把它顶出来，逼着维护者删掉它 —— 而不是让一条假解释永远躺着。
KNOWN_BASELINE_NOISE = {
    "tests/test_matlabc.py::test_r30_static_guards_all_clean":
        "导出树不是 git 仓库 ⇒ 树内 check_baseline.py 的前置条件 P1（需要 .git）"
        "必然红一次；只出现在 before 侧，属环境差异而非回归",
    # R63 实测补登：下面这条与上一条**同根同源**，只是 R62 加它时没有跑过
    # `--full`，所以直到 R63 才第一次露面。它把**每一道**护栏都 spawn 一遍，
    # 其中 `check_baseline.py` 默认模式需要 `.git`（导出树没有）⇒ before 侧必然红。
    # 这是**永久**噪声：before 侧永远是 `git archive` 导出树 ⇒ 下一轮它仍然出现
    # ⇒ 这条登记**不会**变陈旧。（反例见 T1：本轮新增/改动的测试**不能**这样登记。）
    "tests/test_matlabc.py::test_r62_gate_row_signatures_two_way":
        "该测试会 spawn **每一道**护栏，其中 check_baseline.py 默认模式的前置"
        "条件 P1（需要 .git）在导出树里必然红 ⇒ 只出现在 before 侧；"
        "与 test_r30 那条同根同源，属环境差异而非回归",
}


# ── T1（R63）：本轮**新增或改动过**的测试 ─────────────────────────────────
#
# `--full` 的前提是「**同测试集**」——`copy_current_tests` 把**当前** `tests/`
# 覆盖进导出树，而导出树里的 `tools/` 还是**上一个提交**的。于是必然出现一类
# 既不是「修复」也不是「环境噪声」的 before 侧失败：
#
#     测试断言了**本轮新增的产品事实**（新护栏存在 / 门数变成 15 / 新门能跑通），
#     而导出树里的产品还是旧的 ⇒ before 侧红、after 侧绿。
#
# 这一类的正确处置**既不是** B2（登记）**也不是**静默：
#   * 登记它 ⇒ 提交之后导出树就带上产品了 ⇒ 下一轮它不再出现在 fixed 里
#     ⇒ **当场变成陈旧登记（B3）**。也就是说「登记」在这里是**错的**。
#   * 静默 ⇒ 就分不清「本轮改动的测试」与「真被修好的测试」。
# 所以单列一类 T1，并把它们**打印**出来（信息性，不判红）。
#
# 口径：只比**测试函数自己的源码片段**（按行首 `def test_` 切分，与
# `check_known_red.py` 的 `test_spans` 同一套切法），不比行号、不比空白。
_TEST_DEF_RE = re.compile(r"^def (test_[A-Za-z0-9_]+)", re.M)


def test_sources(text):
    """{测试函数名: 源码片段}。"""
    hits = [(m.start(), m.group(1)) for m in _TEST_DEF_RE.finditer(text)]
    out = {}
    for i, (off, name) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        out[name] = text[off:end]
    return out


def new_or_changed_tests(head_text, cur_text):
    """本轮**新增或改动过**的测试 nodeid（`tests/test_matlabc.py::name`）。

    两个字符串都必须是**未做换行翻译**的原文（读时 `newline=""`）：否则
    CRLF 被静默翻成 LF，两侧的「不同」就变成假阳性。
    """
    h = test_sources(head_text)
    c = test_sources(cur_text)
    prefix = SUITE.replace(os.sep, "/") + "::"
    return set(prefix + n for n, src in c.items()
               if n not in h or h[n] != src)


def classify_fixed(fixed, registered=None, new_or_changed=None):
    """把 fixed 拆成 (已解释, 未解释, 陈旧登记)。纯函数，便于自证。

    `new_or_changed`（T1）里的 nodeid 不算「未解释」——理由见上面 T1 的说明。
    """
    reg = KNOWN_BASELINE_NOISE if registered is None else registered
    tr = frozenset() if new_or_changed is None else frozenset(new_or_changed)
    explained = [x for x in fixed if x in reg]
    unexplained = [x for x in fixed if x not in reg and x not in tr]
    stale = sorted(k for k in reg if k not in fixed)
    return explained, unexplained, stale


def transition_fixed(fixed, registered=None, new_or_changed=None):
    """T1：本轮新增/改动过的测试里 before 侧红、after 侧绿的那些（信息性）。"""
    reg = KNOWN_BASELINE_NOISE if registered is None else registered
    tr = frozenset() if new_or_changed is None else frozenset(new_or_changed)
    return [x for x in fixed if x not in reg and x in tr]


def run_full(repo, work, kfilter, py, on_problem):
    """真基线：导出 HEAD -> 复制当前测试集 -> 两侧跑 -> 比集合。"""
    print("[1/4] git archive HEAD -> %s\\head-*（唯一目录，不删旧目录）" % work)
    head_tree = export_head(repo, work)
    print("      -> %s" % head_tree)
    # T1（R63）：**复制之前**先留一份 HEAD 自己的 `tests/` —— 否则「哪些测试属于
    # 本轮（新增或改动）」这个事实会被 `copy_current_tests` 覆盖掉，而它正是 T1
    # 唯一需要的输入。两侧都按 `newline=""` 读，保证 CRLF 不被静默翻译。
    with io.open(os.path.join(head_tree, SUITE), "r", encoding="utf-8",
                 errors="replace", newline="") as fh:
        head_tests_text = fh.read()
    with io.open(os.path.join(repo, SUITE), "r", encoding="utf-8",
                 errors="replace", newline="") as fh:
        cur_tests_text = fh.read()
    noc = new_or_changed_tests(head_tests_text, cur_tests_text)
    print("      T1 输入：本轮新增/改动的测试 %d 个" % len(noc))
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
        print("  不再失败 %d 个（前 %d -> 后 %d）"
              % (len(res["fixed"]), res["n_before"], res["n_after"]))
    explained, unexplained, stale = classify_fixed(
        res["fixed"], new_or_changed=noc)
    trans = transition_fixed(res["fixed"], new_or_changed=noc)
    for x in explained:
        print("  [已登记的环境噪声] %s\n      %s" % (x, KNOWN_BASELINE_NOISE[x]))
    for x in trans:
        print("  [过渡 T1] %s\n      本轮**新增或改动过**的测试：它在 before 侧"
              "失败是「同测试集 + 旧产品」的**构造性**结果 —— 既不是修复，也不是"
              "环境噪声，而且**不该登记**（提交后导出树就带上产品了，登记会在下一轮"
              "立刻变陈旧）。故只作信息性列出，不判红" % x)
    for x in unexplained:
        on_problem("B2 %s 不再失败，却没有登记原因 —— **新噪声必须解释**："
                   "它可能掩盖同一 nodeid 上真实的修复，也可能说明两侧环境不同"
                   "（例如导出树不是 git 仓库）。注意：**本轮新增/改动过**的测试"
                   "走 T1，不会落到这里" % x)
    for x in stale:
        on_problem("B3 登记了「%s」但这次它没有出现 —— **陈旧登记**：原因已经"
                   "消失，说明这条登记是假的（或环境变了），必须删掉或改写" % x)
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

    # ---- R43：fixed 的**已登记环境噪声**（纯函数） ----
    # 这条钉住的是"修好了"与"环境不同"长得一模一样的那个盲点。
    e, u, s = classify_fixed([], {})
    _expect("R43 好样本：fixed 为空 -> 无未解释、无陈旧登记",
            bool(u or s), False, tally)
    e, u, s = classify_fixed(["x::t"], {"x::t": "原因"})
    _expect("R43 好样本：已登记的噪声出现 -> 解释掉，不报",
            bool(u or s), False, tally)
    e, u, s = classify_fixed(["x::t", "y::t"], {"x::t": "原因"})
    _expect("R43 坏样本：未登记的 fixed 条目 -> 必须报（抓到）",
            bool(u), True, tally)
    e, u, s = classify_fixed([], {"x::t": "原因"})
    _expect("R43 坏样本：登记了却没出现 -> 陈旧登记，必须报（抓到）",
            bool(s), True, tally)

    # ---- T1（R63）：本轮**新增或改动过**的测试（纯函数） ----
    _ht = "def test_a():\n    pass\n\ndef test_b():\n    return 1\n"
    _ct = ("def test_a():\n    pass\n\ndef test_b():\n    return 2\n\n"
           "def test_c():\n    return 3\n")
    _noc = new_or_changed_tests(_ht, _ct)
    _p = SUITE.replace(os.sep, "/") + "::"
    _expect("T1 好样本：没改动的 test_a 不算本轮改动",
            (_p + "test_a") in _noc, False, tally)
    _expect("T1 好样本：改过的 test_b 被认出",
            (_p + "test_b") not in _noc, False, tally)
    _expect("T1 好样本：新加的 test_c 被认出",
            (_p + "test_c") not in _noc, False, tally)
    _e, _u, _s = classify_fixed(["n::t"], {}, new_or_changed=set(["n::t"]))
    _expect("T1 好样本：本轮改动过的测试不再算「未解释」", bool(_u), False, tally)
    _e, _u, _s = classify_fixed(["n::t"], {}, new_or_changed=set(["z::t"]))
    _expect("T1 坏样本：不在本轮改动集合里的照样算「未解释」（抓到）",
            bool(_u), True, tally)
    _expect("T1 好样本：transition_fixed 把它单列（信息性，不判红）",
            transition_fixed(["n::t"], {}, set(["n::t"])) != ["n::t"], False, tally)
    _expect("T1 好样本：已登记的优先按「已解释」，不再进 T1",
            bool(transition_fixed(["n::t"], {"n::t": "原因"}, set(["n::t"]))),
            False, tally)

    # ---- R54：`_is_git_repo` 必须接受 **worktree 形态**（`.git` 是文件） ----
    #
    # 旧判据 `os.path.isdir(root/.git)` 在 `git worktree add` 出来的树里恒判否
    # ⇒ P1 红 ⇒ check_all 跑不完 ⇒ 用 worktree 起的**对照组只能跑 pytest**
    # （R53 实测）。这是**测量工具自己**的缺陷。下面是它的两向判据。
    #
    # 约定：`detected` = 判据认为「有问题」；这里「有问题」= **不是仓** = `not _is_git_repo`。
    import tempfile as _tf54
    with _tf54.TemporaryDirectory() as _td54:
        def _n54(name):
            d = os.path.join(_td54, name)
            os.makedirs(d)
            return d

        def _w54(d, text):
            fh = io.open(os.path.join(d, ".git"), "w")
            try:
                fh.write(text)
            finally:
                fh.close()

        # 好样本①：`.git` 是目录（普通仓库 / 子模块）
        _p = _n54("plain")
        os.makedirs(os.path.join(_p, ".git"))
        _expect("R54 好样本：`.git` 是目录 -> 是仓",
                not _is_git_repo(_p), False, tally)

        # 好样本②：`.git` 是文件，`gitdir:` **相对**指向存在的目录（worktree 形态）
        _w = _n54("wt_rel")
        os.makedirs(os.path.join(_td54, "store_rel"))
        _w54(_w, "gitdir: ../store_rel" + chr(10))
        _expect("R54 好样本：`.git` 文件 + gitdir 相对指向存在目录 -> 是仓",
                not _is_git_repo(_w), False, tally)

        # 好样本③：`.git` 是文件，`gitdir:` **绝对**路径指向存在的目录
        _a = _n54("wt_abs")
        _store = os.path.join(_td54, "store_abs")
        os.makedirs(_store)
        _w54(_a, "gitdir: " + _store + chr(10))
        _expect("R54 好样本：`.git` 文件 + gitdir 绝对指向存在目录 -> 是仓",
                not _is_git_repo(_a), False, tally)

        # 坏样本①：没有 `.git`
        _expect("R54 坏样本：没有 `.git` -> 不是仓",
                not _is_git_repo(_n54("none")), True, tally)

        # 坏样本②：`.git` 指向**不存在**的目录（损坏的 worktree）—— 不许当仓
        _d = _n54("wt_dangling")
        _w54(_d, "gitdir: " + os.path.join(_td54, "nope") + chr(10))
        _expect("R54 坏样本：gitdir 指向不存在目录 -> 不是仓（不许把『像仓』当仓）",
                not _is_git_repo(_d), True, tally)

        # 坏样本③：`.git` 是文件但没有 `gitdir:` 前缀
        _b = _n54("wt_badline")
        _w54(_b, "not a gitdir line" + chr(10))
        _expect("R54 坏样本：`.git` 文件无 gitdir: 前缀 -> 不是仓",
                not _is_git_repo(_b), True, tally)

        # 坏样本④：`gitdir:` 后为空
        _e = _n54("wt_empty")
        _w54(_e, "gitdir:" + chr(10))
        _expect("R54 坏样本：gitdir: 后为空 -> 不是仓",
                not _is_git_repo(_e), True, tally)
    # 真实仓库的登记必须**确实是被解释掉的那一条**（否则登记名写错也看不出来）
    _expect("R43 好样本：真实登记键指向 test_r30 那条",
            not any("test_r30_static_guards_all_clean" in k
                    for k in KNOWN_BASELINE_NOISE), False, tally)

    # ---- R43：工作目录的清理 —— 删不掉必须**显式拒绝**，不许吞掉 ----
    # 之所以放进自证：这道门的结论质量完全依赖"导出树是干净的"这个前提，
    # 而这个前提在本机（safe-delete 会拦 200+ 项的目录）**曾经是假的**。
    #
    # 约定提醒（这个套路第 4 次写反了，所以再写一遍）：
    #   `detected` = **判据报了问题**。对 `_prepare_dir` 而言"报问题"就是**抛异常**。
    #   所以：好样本（该安静地清干净）= want_problem False；坏样本（该抛）= True。
    def _refuse(_p):
        raise OSError("simulated safe-delete refusal")

    def _ren_refuse(_a, _b):
        raise OSError("simulated rename refusal")

    def _lie(_p, _q=None):
        """假装成功：不删、不改名、也不报错。旧实现的病根。"""
        return None

    def _raised(fn, *a, **kw):
        """判据：调用抛异常 = True（= 判据认为有问题，这里"有问题"= 拒绝继续）。"""
        try:
            fn(*a, **kw)
        except Exception:                       # noqa: BLE001 - 故意兜住
            return True
        return False

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        # 好样本：目录不存在 -> 建出空目录
        d1 = os.path.join(td, "d1")
        _prepare_dir(d1)
        _expect("R43 好样本：目录不存在 -> 建出空目录",
                _raised(_prepare_dir, d1) or not (
                    os.path.isdir(d1) and os.listdir(d1) == []), False, tally)

        # 好样本：已存在且可删 -> 清空重建
        d2 = os.path.join(td, "d2")
        os.makedirs(d2)
        io.open(os.path.join(d2, "stale.txt"), "w").write("x")
        _prepare_dir(d2)
        _expect("R43 好样本：可删目录 -> 清空后重建",
                _raised(_prepare_dir, d2) or not (
                    os.path.isdir(d2) and os.listdir(d2) == []), False, tally)

        # 好样本：删不掉（模拟守卫拒绝）-> 改名归档 + 留旁证 + 目标为空，且**不得抛**
        d3 = os.path.join(td, "d3")
        os.makedirs(d3)
        io.open(os.path.join(d3, "stale.txt"), "w").write("x")
        notes = []
        raised3 = _raised(_prepare_dir, d3, remove=_refuse, note=notes.append)
        _expect("R43 好样本：删不掉 -> 改名归档（不抛、留旁证、目标为空）",
                raised3 or not notes or not (
                    os.path.isdir(d3) and os.listdir(d3) == []), False, tally)

        # 坏样本：既删不掉也改不了名 -> **必须抛**（绝不带脏目录继续）
        d4 = os.path.join(td, "d4")
        os.makedirs(d4)
        _expect("R43 坏样本：既删不掉也改不了名 -> 必须抛",
                _raised(_prepare_dir, d4, remove=_refuse, rename=_ren_refuse),
                True, tally)

        # 坏样本：清理器**假装成功**（不删、不改名、也不报错）-> 必须仍然抛。
        # 这条直接钉住旧实现的病根：ignore_errors=True + 假装清干净 ⇒ 带着脏目录
        # 往下走，两侧比对结论**静默失真**（而那正是这道门存在的理由）。
        d5 = os.path.join(td, "d5")
        os.makedirs(d5)
        io.open(os.path.join(d5, "stale.txt"), "w").write("x")
        _expect("R43 坏样本：清理器假装成功却继续往下走 -> 必须抛",
                _raised(_prepare_dir, d5, remove=_lie, rename=_lie), True, tally)

        # 好样本：拒绝时**报错必须点名目录**（报错离真因太远 = 把问题推给下一个人）
        # ⚠ d6 必须**先存在**：目录不存在时 `_prepare_dir` 直接建目录、根本不会走到
        #   拒绝分支，这条样本就变成空的（第一版就是这么写的，被自己抓出来）。
        d6 = os.path.join(td, "d6")
        os.makedirs(d6)
        msg = ""
        try:
            _prepare_dir(d6, remove=_refuse, rename=_ren_refuse)
        except RuntimeError as e:
            msg = str(e)
        _expect("R43 好样本：拒绝时报错点名目录",
                not ("d6" in msg and len(msg) >= 20), False, tally)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (tally[0], tally[1]))
    return 0 if (tally[0] >= 11 and tally[1] >= 12) else 1


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
        print("check_baseline: OK（--full：按 nodeid 集合比对两侧，无回归；"
              "判据族 %s）" % ROW_SIGNATURE)
        return 0

    print("check_baseline: OK（前置条件 %d 项 + 判定逻辑两向自证 %s；"
          "完整基线请显式跑 --full —— 它会真跑两侧全量，分钟级；判据族 %s）"
          % (n, tally, ROW_SIGNATURE))
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
