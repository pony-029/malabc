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

一图看懂（文档与代码之间的那道缝，就是本题）：

    README.md / CONTRIBUTING.md
    以及各入口脚本自己的模块 docstring（= --help 的正文）
            │
            │ 抽出每条「调了某个 *.py」的命令行
            ▼
    ┌──────────────────────────────────────────────────────────┐
    │  python matlabc.py myproj/ --checks all --browse         │
    └──────────────────────────────────────────────────────────┘
            │                                   ▲
            │ 逐个 --flag 去问                   │ 拿不到 --help
            ▼                                   │ 且未登记
    ┌──────────────────────────────┐            │
    │  <脚本> --help               │────────────┘  ⇒ 缺输入 → 红
    │  （stdin=DEVNULL + 超时）     │
    └──────────────────────────────┘
            │
      ┌─────┴─────┐
      │ flag 在？  │
      └─────┬─────┘
        在   │   不在
        ✓    │    ✗ → 红：文档写了不存在的开关
             ▼
      （NO_HELP_SCRIPTS 里的脚本：不得出现任何 --flag）

  实测案例：README 曾写 `--check tainted_sink`，而 matlabc 的 `--check` 是
  **歧义前缀**（同时匹配 --checks / --check-py36 / --check-py36-files），
  真跑会 `error: ambiguous option`。这类失真靠 review 看不出来。

用法：
    python tools/check_doc_flags.py             # 0=干净 1=有说谎 2=缺输入
    python tools/check_doc_flags.py --selftest  # 两向自证

退出码：
    0  = 文档/帮助正文里的命令行开关全部真实存在
    1  = 有文档宣传了不存在的开关（或把不存在的脚本当入口）
    2  = 缺输入（解析不到任何被审文档 / 关键脚本缺失 → 红）
"""
import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile

# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族，
# 或本门独有的机制名）。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "NO_HELP_SCRIPTS"

SCRIPTS = ("matlabc.py", "matlabc_flow.py", "matlabc_ask.py", "matlabc_mcp.py",
           "gui.py")
# 子进程 `--help` 的墙钟上限。实测（探针 probe_r26b / probe_help_behavior）五个
# 脚本在 `stdin=DEVNULL` 下都是 0.5–0.8s 返回，60s 有约 75 倍余量；
# 这个上限存在的意义是「让挂死变成红，而不是让门永远等着」。
HELP_TIMEOUT = 60.0
# 按设计没有 CLI 选项的脚本（stdio MCP server：读 stdin 的 JSON-RPC，
# 收到 EOF 即退出，故 `--help` 不产生 usage）。这里的「登记」是显式的，
# 而不是把「拿不到 --help」一律当通过 —— 后者会把护栏变成永远绿的门。
NO_HELP_SCRIPTS = {"matlabc_mcp.py"}
DOC_FILES = ("README.md", "README_CN.md", "CONTRIBUTING.md")
# 入口脚本的**模块 docstring 就是它 `--help` 的正文**，因此同样受判据约束：
# 「文档说谎」有两条路径 —— ① README 说谎、② 帮助正文说谎 —— 必须一起堵。
# agent_loop.py 是库（无 CLI），但它 docstring 里的示例命令行仍可能写错开关，
# 所以也纳入（它引用的 matlabc_flow.py 是 SCRIPTS 成员，可被真实核验）。
SELF_DOCS = ("matlabc.py", "matlabc_flow.py", "matlabc_ask.py",
             "matlabc_mcp.py", "gui.py", "agent_loop.py")
FLAG_RE = re.compile(r"--[A-Za-z][A-Za-z0-9-]*")


def repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _help_options(script_path):
    """跑 `<script> --help`，返回它自称支持的选项集合；拿不到 usage 返回 None。

    ⚠ 本函数是 R62-R31e 修掉的一个**真缺陷**的现场，三条纪律缺一不可：

    1. `stdin=subprocess.DEVNULL`。实测（探针 probe_r26b_pipe，含重跑对照）：
       - `matlabc.py / matlabc_flow.py / matlabc_ask.py --help` 三种 stdin 形态
         都是 0.5–0.8s 返回，**不受影响**；
       - **`matlabc_mcp.py --help` 在 stdin 继承时 >30s 不返回**，切断 stdin
         后 0.5s 返回 —— 它是 stdio JSON-RPC server，设计上就要读 stdin，
         拿到一个永不 EOF 的管道就永久阻塞。
       旧实现用 `subprocess.run(capture_output=True)`（stdout/stderr=PIPE、
       stdin 继承）**且按 `SCRIPTS` 顺序串行**，前 3 个各 0.7s、第 4 个等满
       它的 180s 内建超时 ⇒ 护栏实测约 181s，被外部 `timeout 90` 杀掉
       （rc=124）—— 表现就是「看不见的原因地卡住」，而它其实**没有**在
       打印 OK 之后卡住（那是我第一次的误读：stdout 缓冲造成的顺序错觉）。
    2. **不收 PIPE，改写临时文件**。子进程若 fork/Popen 出孙进程并让它继承
       管道写端，`communicate()` 会等不到 EOF 而永久阻塞 —— 连 `timeout`
       都救不了，因为 Windows 分支 kill 之后还会再 drain 一次。写文件没有
       这个耦合面。
    3. 超时后 `kill()` + `wait()` 收尸，不让任何进程泄漏到下一个检查项；
       `HELP_TIMEOUT` 从 180s 降到 60s（实测 0.8s，约 75 倍余量）。

    失败一律返回 None（= 缺输入），由调用方决定是红还是「已登记无选项」。
    """
    tmp = tempfile.TemporaryFile()
    try:
        try:
            p = subprocess.Popen([sys.executable, script_path, "--help"],
                                 stdin=subprocess.DEVNULL, stdout=tmp,
                                 stderr=subprocess.STDOUT)
        except OSError:
            return None
        try:
            p.wait(timeout=HELP_TIMEOUT)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            return None
        tmp.seek(0)
        text = tmp.read().decode("utf-8", "replace")
    finally:
        tmp.close()
    if "usage:" not in text and "--help" not in text:
        return None
    opts = set(FLAG_RE.findall(text))
    return opts or None


def _blanks(script_path):
    """`<script> --help` 是否「明确地什么都不声明」（rc=0 且输出为空）。

    `NO_HELP_SCRIPTS` 是一张**登记表**，登记必须能被证伪，否则它就成了
    「脚本坏掉了也照样洗白」的后门。判据：登记的脚本必须 rc=0 **且**输出为空
    —— 真·stdio server 的特征；若它其实有 usage（登记错了）或直接报错退出
    （坏掉了），都不许继续当「无选项」放行。
    """
    tmp = tempfile.TemporaryFile()
    try:
        try:
            p = subprocess.Popen([sys.executable, script_path, "--help"],
                                 stdin=subprocess.DEVNULL, stdout=tmp,
                                 stderr=subprocess.STDOUT)
        except OSError:
            return False
        try:
            p.wait(timeout=HELP_TIMEOUT)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            return False
        tmp.seek(0)
        return p.returncode == 0 and tmp.read() == b""
    finally:
        tmp.close()


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


def _read_module_docstring(path):
    """读回一个 .py 的模块级 docstring；读不到返回 None。

    用 `ast.get_docstring` 而不是正则：本仓 docstring 里含制表框字符、反引号、
    以及 `--flag` 字面量，正则极易被转义与编码坑到（这类自伤在 R31 已发生过两次）。
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError:
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    return ast.get_docstring(tree, clean=False)


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


def _load_script_opts(root, scripts=SCRIPTS, notes=None):
    """返回 {script: set(opts)}；拿不到且未登记的脚本**不出现在键里**（= 缺输入）。

    `NO_HELP_SCRIPTS` 里的脚本必须通过 `_blanks()` 证伪式核验（rc=0 且输出为空）
    才算「按设计无选项」；核验不过就当缺输入（不出现在键里 → 红）。
    `notes` 收集给用户看的原因，让红的时候能知道**为什么**红。
    """
    opts = {}
    for s in scripts:
        p = os.path.join(root, s)
        if not os.path.exists(p):
            continue
        got = _help_options(p)
        if got is not None:
            opts[s] = got
        elif s in NO_HELP_SCRIPTS:
            if _blanks(p):
                opts[s] = set()
            elif notes is not None:
                notes.append(
                    "%s 登记在 NO_HELP_SCRIPTS，但它的 --help 既不是「rc=0 且无输出」"
                    "（stdio server 特征）也不是一个可解析的 usage —— 登记失效" % s)
    return opts


def _iter_audited_docs(root):
    """产出 (显示名, 文本)：先 3 份 markdown，再 6 个入口脚本的模块 docstring。

    入口脚本单独列出来是有意义的：它们的 docstring 就是用户敲 `--help` 看到的
    全部正文。README 说谎和帮助正文说谎是同一种病，不能只治一个。
    """
    out = []
    for d in DOC_FILES:
        p = os.path.join(root, d)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                out.append((d, fh.read()))
    for s in SELF_DOCS:
        p = os.path.join(root, s)
        doc = _read_module_docstring(p)
        if doc is not None:
            out.append(("%s::__doc__" % s, doc))
    return out


def _selftest():
    root = repo_root()
    notes = []
    opts = _load_script_opts(root, notes=notes)
    missing = [s for s in SCRIPTS if s not in opts]
    bad_cases = good_cases = 0
    fails = []
    if missing:
        print("SELFTEST 无法自证：拿不到 %s 的 --help 且未登记" % missing)
        for n in notes:
            print("  - " + n)
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

    # 正例：真实文档与真实帮助正文必须干净
    for name, text in _iter_audited_docs(root):
        expect(name, text, False)
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
    # 反例 5：**帮助正文**说谎。这是本轮新增的覆盖面 ——
    # 入口脚本 docstring 就是 `--help` 正文，它与 README 说谎是同一种病。
    expect("帮助正文里的假开关（docstring 场景）",
           "用法：\n    python matlabc.py myproj --definitely-not-a-flag\n", True)
    # 正例：帮助正文里的真开关
    expect("帮助正文里的真开关（docstring 场景）",
           "用法：\n    python matlabc.py myproj --checks all --browse\n", False)

    # 登记表必须可证伪：`_blanks()` 要能把「真·无输出」与「有 usage」分开。
    # 这是 R62-R31e 新增的门 —— 没有它，NO_HELP_SCRIPTS 就是洗白后门。
    tmp = tempfile.mkdtemp(prefix="cdflag_selftest_")
    try:
        def _mk(name, text):
            p = os.path.join(tmp, name)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
            return p

        quiet = _mk("quiet.py", "import sys\nsys.exit(0)\n")
        loud = _mk("loud.py",
                   "import sys\nprint('usage: loud.py [-h]')\nsys.exit(0)\n")
        broke = _mk("broke.py", "import sys\nsys.exit(3)\n")
        for tag, path, want in (("登记核验：rc=0 且无输出 → 可登记", quiet, True),
                                ("登记核验：有 usage → 不可登记", loud, False),
                                ("登记核验：非 0 退出 → 不可登记", broke, False)):
            got = _blanks(path)
            ok = got == want
            print("  [%s] %-40s -> %s%s"
                  % ("正例" if want else "反例", tag, got,
                     "" if ok else "   *** 不符预期 ***"))
            if not ok:
                fails.append(tag)
            if want:
                good_cases += 1
            else:
                bad_cases += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

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
    notes = []
    opts = _load_script_opts(root, notes=notes)
    missing = [s for s in SCRIPTS if s not in opts]
    if missing:
        print("check_doc_flags: 拿不到脚本 --help 且未登记：%s（缺输入 → 红）"
              % missing)
        for n in notes:
            print("  - " + n)
        return 2
    for n in notes:
        print("check_doc_flags: 注意 —— " + n)
    probs = []
    scanned = 0
    for name, txt in _iter_audited_docs(root):
        scanned += 1
        probs += audit_doc(txt, opts, name)
    # 缺输入要显式报：三份 markdown 一份都不能少
    for d in DOC_FILES:
        if not os.path.exists(os.path.join(root, d)):
            probs.append("%s: 文档不存在（缺输入 → 红）" % d)
    if probs:
        print("check_doc_flags: %d 项违规" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_doc_flags: OK（%d 份文档/帮助正文的命令行开关全部存在于对应脚本的 --help；"
          "含 %d 个入口脚本的模块 docstring；判据 %s）"
          % (scanned, len(SELF_DOCS), ROW_SIGNATURE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
