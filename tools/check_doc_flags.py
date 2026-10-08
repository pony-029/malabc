# -*- coding: utf-8 -*-
"""登记制护栏：文档里写的 CLI 开关必须**真的存在**（能力清单不能撒谎）。

动因（真实缺陷）：README 快速开始写着 `--check tainted_sink`，而 matlabc 的
`--check` 是**歧义前缀**（同时匹配 --checks / --check-py36 / --check-py36-files），
实测 `error: ambiguous option`。文档里此类失真靠 review 看不出来 —— 必须有一个
**可执行的对手方**：拿文档里的命令行去问 CLI 自己到底认不认。

判据（只认装置，不认叙述）：
  * 逐行取文档中「调用了某个 *.py 脚本」的命令行（shell 续行 `\\` 已拼接）；
  * 该行上出现的每个 `--flag` 必须是**那个脚本** `--help` 输出里真实存在的选项；
  * `--help` 拿不到 **且**该脚本未登记在 NO_HELP_SCRIPTS → 缺输入 → 红；
  * 登记在 NO_HELP_SCRIPTS 的脚本按设计没有 CLI 选项 ⇒ 判据变成
    「该行不得出现**任何** --flag」（而不是「无从判断」）。

用法：
    python tools/check_doc_flags.py             # 0=干净 1=有说谎 2=缺输入
    python tools/check_doc_flags.py --selftest  # 两向自证
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

SCRIPTS = ("matlabc.py", "matlabc_flow.py", "matlabc_ask.py", "matlabc_mcp.py")
# 按设计没有 CLI 选项的脚本（stdio MCP server：读 stdin 的 JSON-RPC，
# 收到 EOF 即退出，故 `--help` 不产生 usage）。这里的「登记」是显式的，
# 而不是把「拿不到 --help」一律当通过 —— 后者会把护栏变成永远绿的门。
NO_HELP_SCRIPTS = {"matlabc_mcp.py"}
DOC_FILES = ("README.md", "README_CN.md", "CONTRIBUTING.md")
FLAG_RE = re.compile(r"--[A-Za-z][A-Za-z0-9-]*")


def repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _help_options(script_path):
    """跑 `<script> --help`，返回它自称支持的选项集合；拿不到 usage 返回 None。"""
    try:
        r = subprocess.run([sys.executable, script_path, "--help"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (r.stdout or "") + (r.stderr or "")
    if "usage:" not in text and "--help" not in text:
        return None
    opts = set(FLAG_RE.findall(text))
    return opts or None


def iter_doc_lines(text):
    """把 shell 续行拼成完整命令行；跳过空行与纯注释行。"""
    buf = ""
    for raw in text.split("\n"):
        s = raw.rstrip()
        if not s.strip():
            if buf:
                yield buf
                buf = ""
            continue
        if s.lstrip().startswith("#"):
            continue
        if s.endswith("\\"):
            buf += s[:-1] + " "
            continue
        buf += s
        yield buf
        buf = ""
    if buf:
        yield buf


def audit_doc(text, script_opts, doc_name="<doc>"):
    """返回问题列表；script_opts: {script_name: set(options)}（set() 表示无选项）。"""
    probs = []
    for line in iter_doc_lines(text):
        for script in SCRIPTS:
            if script not in line:
                continue
            if script not in script_opts:
                probs.append("%s: 无法取得 %s 的 --help 选项（缺输入 → 红）"
                             % (doc_name, script))
                continue
            known = script_opts[script]
            for flag in sorted(set(FLAG_RE.findall(line))):
                if flag == "--help":
                    continue
                if flag not in known:
                    extra = ("（%s 按设计无 CLI 选项）" % script) if not known else ""
                    probs.append(
                        "%s: `%s` 不在 %s 的选项表里%s —— 文档写了不存在的开关\n"
                        "      %s" % (doc_name, flag, script, extra, line.strip()[:110]))
    return probs


def _load_script_opts(root, scripts=SCRIPTS):
    """返回 {script: set(opts)}；拿不到且未登记的脚本**不出现在键里**（= 缺输入）。"""
    opts = {}
    for s in scripts:
        p = os.path.join(root, s)
        if not os.path.exists(p):
            continue
        got = _help_options(p)
        if got is not None:
            opts[s] = got
        elif s in NO_HELP_SCRIPTS:
            opts[s] = set()
    return opts


def _selftest():
    root = repo_root()
    opts = _load_script_opts(root)
    missing = [s for s in SCRIPTS if s not in opts]
    bad_cases = good_cases = 0
    fails = []
    if missing:
        print("SELFTEST 无法自证：拿不到 %s 的 --help 且未登记" % missing)
        return 2

    def expect(tag, text, want_problem):
        nonlocal bad_cases, good_cases
        got = audit_doc(text, opts, tag)
        ok = bool(got) == want_problem
        print("  [%s] %-40s -> %s%s"
              % ("反例" if want_problem else "正例", tag,
                 "抓到" if got else "放行",
                 "" if ok else "   *** 不符预期 ***"))
        if not ok:
            fails.append(tag)
        if want_problem:
            bad_cases += 1
        else:
            good_cases += 1

    # 正例：真实文档必须干净
    for d in DOC_FILES:
        p = os.path.join(root, d)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                expect(d, fh.read(), False)
    # 反例 1：文档写了不存在的开关（就是本轮修掉的那个真实缺陷）
    expect("--check tainted_sink（历史真实缺陷）",
           "python matlabc.py myproj/ --check tainted_sink\n", True)
    # 反例 2：凭空发明的开关
    expect("凭空发明 --totally-made-up",
           "python matlabc.py myproj/ --totally-made-up\n", True)
    # 反例 3：续行拼接后仍要能抓到
    expect("shell 续行中的说谎开关",
           "python matlabc.py myproj/ --checks all \\\n    --no-such-flag\n", True)
    # 反例 4：无 CLI 选项的脚本被写上 flag
    expect("matlabc_mcp.py 被写上 --server",
           "python matlabc_mcp.py --server\n", True)
    # 正例：合法命令行（含续行）必须放行
    expect("合法命令行",
           "python matlabc.py myproj/ -o r.md --html r.html --browse \\\n"
           "    --offline --checks all --sarif r.sarif\n", False)
    # 正例：别的工具的 --check 不应被误伤（该行不含我们的脚本名）
    expect("git apply --check（非本工具）",
           "git -C repo apply --check patch.diff\n", False)
    # 正例：MCP server 的裸启动行（无 flag）必须放行
    expect("matlabc_mcp.py 裸启动",
           "python matlabc_mcp.py\n", False)

    print("SELFTEST COUNTS {\"bad\": %d, \"good\": %d}" % (bad_cases, good_cases))
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
    opts = _load_script_opts(root)
    missing = [s for s in SCRIPTS if s not in opts]
    if missing:
        print("check_doc_flags: 拿不到脚本 --help 且未登记：%s（缺输入 → 红）"
              % missing)
        return 2
    probs = []
    scanned = 0
    for d in DOC_FILES:
        p = os.path.join(root, d)
        if not os.path.exists(p):
            probs.append("%s: 文档不存在（缺输入 → 红）" % d)
            continue
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        scanned += 1
        probs += audit_doc(txt, opts, d)
    if probs:
        print("check_doc_flags: %d 项违规" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_doc_flags: OK（%d 份文档的命令行开关全部存在于对应脚本的 --help）"
          % scanned)
    return 0


if __name__ == "__main__":
    sys.exit(main())
