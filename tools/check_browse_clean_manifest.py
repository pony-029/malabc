# -*- coding: utf-8 -*-
"""R100：`--browse` 站点**清理清单 ⇄ 生成点**两向对账（判据族 M1–M3）。

起因（白帽事实，不是推测）：R99 的提交信息声称

    「`_clean_browse_dir` 顶层清单**两向都错**：多 `review.html`（幽灵）、
      少 `func_detail` / `unified` / `folder_impact` / `var_taint` /
      `ai_prompts` …… 另补基础层 4 个子目录 + 3 个顶层页」

而 `git log -L 30445,30482:matlabc.py` 显示该函数**自首次提交（`425f3e9`）
起一字未动** —— 幽灵 `review.html` 与 9 项遗漏一直留着。**声明 ≠ 实现**，
当时没有任何门看这一面（R82：门禁绿 = 恒等式成立 ≠ 覆盖度足够）。

判据（**自维持**：名单全部从代码现抽，本文件不写死任何一个页面名）：
  M1  清理清单 ⊇ 生成点   无遗漏 —— 少一项 ⇒ 换语料 / 换 `--lang` 后页面残留
  M2  清理清单 ⊆ 生成点   无幽灵 —— 多一项 ⇒ 每次都在删一个从不生成的文件
  M3  子目录清单两向一致（含 `src_subdir` 的**实参值**，如 `xref_src`）

为什么「生成点」按**字面量**抽取，而不是真跑一遍再对目录：条件生成的页
（`ai_prompts.html` 只在 `ai_mode != off` 时写、`binaries.html` 只在给了
二进制时写）在单次运行里看不见，按运行结果对账会把它们判成幽灵。本门要问
的是「**这个文件会不会被本工具生成**」，代码里的字面量就是它的充分证据。

退出码：0 = 两向一致；1 = 有差异；2 = 输入缺失（找不到目标文件或函数）。
"""
import io
import os
import re
import sys

# 判据族签名（机器可读；check_help_contract 的 H1/H2 按它核对，
# 本文件里散落的 C1/C2/M3 才不是「隐形判据」）。
ROW_SIGNATURE = "M1–M3"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MATLABC = os.path.join(ROOT, "matlabc.py")
CSITE = os.path.join(ROOT, "renderers", "csite.py")

_FUNC_RE = r"(?m)^def\s+%s\s*\("
_WL_RE = re.compile(r"(?s)for name in \((.*?)\):")
_SUB_RE = re.compile(r"(?s)for _sub in \((.*?)\):")
_STR_RE = re.compile(r'"([^"\n]+)"')
_SAFE_RE = re.compile(r'_safe_page\(outdir,\s*"([^"\n]+)"')
_OUTDIR_RE = re.compile(r'outdir\s*/\s*"([A-Za-z_][\w.-]*)"')
_EMIT_TOP_RE = re.compile(r'_emit\(u"([^"/\n]+)"')
_EMIT_SUB_RE = re.compile(r'_emit\(u"([A-Za-z_][\w.-]*)/')
_SUBDIR_ARG_RE = re.compile(r'src_subdir="([^"\n]+)"')


class Missing(Exception):
    pass


def _read(path):
    try:
        return io.open(path, "rb").read().decode("utf-8").replace("\r\n", "\n")
    except Exception as exc:
        raise Missing("读不到 %s：%s" % (path, exc))


def func_body(src, name):
    """顶层函数 `name` 的函数体（参数列表起 → 下一个列 0 的 def/class）。"""
    m = re.search(_FUNC_RE % re.escape(name), src)
    if m is None:
        raise Missing("找不到顶层函数 %s()" % name)
    tail = src[m.end():]
    m2 = re.search(r"(?m)^(?:def|class)\s", tail)
    return tail if m2 is None else tail[:m2.start()]


def _split(names):
    """含 `.` 的算**文件**，其余的算**子目录**。"""
    files = set(x for x in names if "." in x)
    dirs = set(x for x in names if "." not in x)
    return files, dirs


def extract_whitelist(src):
    """从 `_clean_browse_dir` 抽（顶层文件清单, 子目录清单）。"""
    body = func_body(src, "_clean_browse_dir")
    m = _WL_RE.search(body)
    if m is None:
        raise Missing("_clean_browse_dir 里找不到 `for name in (...)`")
    f, d = _split(_STR_RE.findall(m.group(1)))
    s = _SUB_RE.search(body)
    if s is None:
        raise Missing("_clean_browse_dir 里找不到 `for _sub in (...)`")
    _f2, d2 = _split(_STR_RE.findall(s.group(1)))
    return (f, d | d2)


def extract_produced(src_m, src_c):
    """从两个渲染器的代码抽（会生成的顶层文件, 会生成的子目录）。"""
    mbody = func_body(src_m, "render_browse_site")
    names = set(_SAFE_RE.findall(mbody))
    names |= set(_OUTDIR_RE.findall(mbody))
    cbody = func_body(src_c, "render_c_site")
    names |= set(_EMIT_TOP_RE.findall(cbody))
    dirs = set(x for x in _EMIT_SUB_RE.findall(cbody))
    dirs |= set(_SUBDIR_ARG_RE.findall(src_m))
    f, d = _split(names)
    return (f, d | dirs)


def reconcile(wl_files, wl_dirs, pr_files, pr_dirs):
    """两向对账；返回问题字符串列表（空 = 通过）。

    ⚠ **空集先断言**：任何一边为空都不许当成「一致」—— 「集合为空」与
    「集合相等」是两回事（R95 ④ / R99 亲身再犯过）。
    """
    probs = []
    if not wl_files or not pr_files:
        probs.append("M0 空集输入：清理清单 %d 项 / 生成点 %d 项 —— "
                     "空集不许当一致（先修抽取器或目标文件）"
                     % (len(wl_files), len(pr_files)))
        return probs
    miss = sorted(pr_files - wl_files)
    ghost = sorted(wl_files - pr_files)
    if miss:
        probs.append("M1 清理清单**漏**了 %d 个真会生成的文件（换语料后会残留）：%s"
                     % (len(miss), ", ".join(miss)))
    if ghost:
        probs.append("M2 清理清单里有 %d 个**幽灵**（代码里从没有生成点）：%s"
                     % (len(ghost), ", ".join(ghost)))
    dm = sorted(pr_dirs - wl_dirs)
    dg = sorted(wl_dirs - pr_dirs)
    if dm:
        probs.append("M3 子目录**漏**了 %d 个：%s" % (len(dm), ", ".join(dm)))
    if dg:
        probs.append("M3 子目录有 %d 个**幽灵**：%s" % (len(dg), ", ".join(dg)))
    return probs


# ---------------------------------------------------------------------------
# 自证（合成样本，注入式：每个坏样本都必须被 reconcile 抓出来）
# ---------------------------------------------------------------------------
SAMPLES = (
    # (清理清单文件, 清理清单目录, 生成点文件, 生成点子目录, 期望有问题?)
    ({"a.html"}, set(), {"a.html"}, set(), False),
    ({"a.html", "b.html"}, {"x"}, {"a.html", "b.html"}, {"x"}, False),
    ({"a.html"}, set(), {"a.html", "b.html"}, set(), True),      # M1 遗漏
    ({"a.html", "c.html"}, set(), {"a.html"}, set(), True),      # M2 幽灵
    (set(), set(), {"a.html"}, set(), True),                     # M0 空集
    ({"a.html"}, set(), set(), set(), True),                     # M0 空集
    ({"a.html"}, {"x"}, {"a.html"}, {"x", "y"}, True),           # M3 目录遗漏
    ({"a.html"}, {"x", "z"}, {"a.html"}, {"x"}, True),           # M3 目录幽灵
)


def selftest():
    bad = good = 0
    for (wl_f, wl_d, pr_f, pr_d, want_bad) in SAMPLES:
        got = bool(reconcile(wl_f, wl_d, pr_f, pr_d))
        if got == want_bad:
            good += 1
        else:
            bad += 1
            print("  [selftest] 样本 %r: 期望有问题=%s，实际=%s"
                  % ((sorted(wl_f), sorted(pr_f)), want_bad, got))
    # 抽取器本身也要自证：真文件必须能读出**非空**名单
    try:
        wf, wd = extract_whitelist(_read(MATLABC))
        pf, pd = extract_produced(_read(MATLABC), _read(CSITE))
        for nm, s in (("清理文件", wf), ("清理目录", wd),
                      ("生成文件", pf), ("生成目录", pd)):
            if s:
                good += 1
            else:
                bad += 1
                print("  [selftest] 抽取器从真文件读出空的 %s" % nm)
    except Missing as exc:
        bad += 1
        print("  [selftest] 抽取器失败：%s" % exc)
    return bad, good


def main(argv):
    if "--selftest" in argv:
        bad, good = selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1
    if "--help" in argv or "-h" in argv:
        sys.stdout.write(__doc__)
        return 0
    try:
        wf, wd = extract_whitelist(_read(MATLABC))
        pf, pd = extract_produced(_read(MATLABC), _read(CSITE))
    except Missing as exc:
        print("[FAIL] 输入缺失：%s" % exc)
        return 2
    probs = reconcile(wf, wd, pf, pd)
    print("清理清单：%d 个顶层文件 / %d 个子目录" % (len(wf), len(wd)))
    print("代码生成点：%d 个顶层文件 / %d 个子目录" % (len(pf), len(pd)))
    for p in probs:
        print("[FAIL] " + p)
    if probs:
        return 1
    print("[OK] 清理清单与生成点两向一致（M1–M3）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
