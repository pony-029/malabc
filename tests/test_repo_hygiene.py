# -*- coding: utf-8 -*-
"""仓库卫生棘轮：**不许往"模块旁边"写文件**。

## 为什么这条判据存在

R855 的真缺陷：`matlabc_task.py` 的失败分支把日志写到
`os.path.dirname(os.path.abspath(__file__))` —— 也就是**本仓库根目录**。

后果有三层，最轻的那层才是"工作区多个文件"：

1. 每次测试/试跑都在工作区留一个未跟踪文件；
2. 用户在自己的工程里**找不到**这条日志（它跑到工具仓库去了）；
3. 日志与它描述的对象分离，出问题时无从对照。

而这类代码**不会报错**，只有在"恰好走到失败分支"时才露一次面。

## 判据口径

用 AST 扫全部 `.py`：找到 `open(...)` / `io.open(...)` 且
**mode 含 w/a/x**、同时**路径表达式里出现 `__file__` 或本模块目录名**的调用。
只认写模式 —— 读 `__file__` 旁边的模板/资源是合法的（那种有一堆）。

豁免：本文件（判据正文里必然出现这些字样）。
"""
import ast
import io
import os
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 写模式的字符（`"r+"` 也算写，因为它可能改内容）
WRITE_MODES = set("wax+")

#: 允许的例外：`{相对路径: 理由}`。**当前为空** —— 新增必须写清为什么。
EXEMPT = {}


def _py_files():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "node_modules", "__pycache__", "target",
                                "releases", ".m2c")]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(base, f)


def _write_mode(call):
    """从 `open(path, mode, ...)` 里取 mode 字面量；取不到返回 ""。"""
    args = list(call.args) + [kw.value for kw in call.keywords
                              if kw.arg == "mode"]
    for node in args[1:]:
        if isinstance(node, ast.Str):
            return node.s
    return ""


def _mentions_file_var(node):
    """路径表达式里是否出现 `__file__`（或由此派生的 HERE/here 等名字）。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in ("__file__", "HERE", "here",
                                                    "self_dir", "_here"):
            return True
    return False


def _violations(path):
    try:
        src = io.open(path, encoding="utf-8", errors="replace").read()
        # 有些源文件含 `\$` / `\m` 这类非法转义，`ast.parse` 会逐条发
        # DeprecationWarning —— 那是**被扫文件**的属性，与本判据无关，
        # 但会把 pytest 输出刷满，于是这里就地压掉。
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(src)
    except (OSError, SyntaxError, ValueError):
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "id", None) or getattr(fn, "attr", None)
        if name != "open" or not node.args:
            continue
        mode = _write_mode(node)
        if not mode or not (set(mode) & WRITE_MODES):
            continue
        if _mentions_file_var(node.args[0]):
            out.append((getattr(node, "lineno", 0), mode))
    return out


def test_no_writes_next_to_module():
    """任何 `.py` 都不许在 `__file__` 旁边开写模式的文件。"""
    bad = []
    for p in _py_files():
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        if rel in EXEMPT or rel == "tests/test_repo_hygiene.py":
            continue
        for line, mode in _violations(p):
            bad.append("%s:%d（mode=%r）" % (rel, line, mode))
    assert not bad, (
        "这些地方往「模块旁边」写文件（会污染本仓库工作区，且日志/产物会跑到"
        "用户工程之外）：\n  " + "\n  ".join(bad[:10]) +
        "\n  修法：把目标路径改成**被操作的项目内**（如 root/.matlabc/…）")


#: JS 侧会「写东西」的调用名。`mkdirSync` 也算：它会造出目录。
JS_WRITE_FNS = (
    "writeFileSync", "appendFileSync", "createWriteStream",
    "mkdirSync", "renameSync", "unlinkSync", "rmSync", "copyFileSync",
)


def _js_files():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "node_modules", "__pycache__", "target",
                                "releases", ".m2c")]
        for f in files:
            if f.endswith(".js"):
                yield os.path.join(base, f)


def _js_violations(path):
    """JS 里「写操作 + 路径含 `__dirname`」的行号。"""
    try:
        lines = io.open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return []
    out = []
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("//"):
            continue
        if not any(fn in ln for fn in JS_WRITE_FNS):
            continue
        if "__dirname" in ln:
            out.append(i)
    return out


#: 必须被 `.gitignore` 覆盖的产物形态。`{模式: 为什么`}
#: —— 每条都对应过真实事故或有明确的生成路径，不是"看着像垃圾"。
MUST_IGNORE = {
    "__pycache__/": "Python 字节码缓存（每次导入都会生成）",
    "*.pyc": "字节码文件",
    "*.log": "运行日志（matlabc_task.log 曾因此污染工作区）",
    "*.sarif": "分析报告产物",
    ".matlabc/": "任务历史与日志（工具在工作区内写的那一支）",
}


def test_gitignore_covers_known_artifacts():
    """`.gitignore` 必须覆盖已知的产生产物 —— 否则一次跑动就脏了工作区。"""
    p = os.path.join(ROOT, ".gitignore")
    assert os.path.isfile(p), "仓库根没有 .gitignore"
    lines = set(ln.strip() for ln in
                io.open(p, encoding="utf-8").read().splitlines())
    missing = [k for k in MUST_IGNORE if k not in lines]
    assert not missing, (
        "`.gitignore` 缺这些形态（各自的理由见 MUST_IGNORE）：%r" % missing)


def test_no_generated_artifacts_are_tracked():
    """**反向审计**：`git ls-files` 里不许出现产物类文件。

    被**跟踪**的产物比未跟踪的更糟：它会被每个人的 checkout 复制一份，
    而且 `git status` 永远干净 —— 于是没人再想起它。
    """
    import subprocess

    r = subprocess.run(["git", "ls-files"], cwd=ROOT, stdin=subprocess.DEVNULL,
                       timeout=120, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL)
    if r.returncode != 0:
        import pytest
        pytest.skip("不是 git 仓库（或 git 不可用）")
    tracked = r.stdout.decode("utf-8", "replace").splitlines()
    pats = (".log", ".tmp", ".pyc", "__pycache__", ".sarif")
    bad = [f for f in tracked if f.endswith(pats) or "__pycache__" in f]
    assert not bad, "这些产物被 git 跟踪了（应删除并加入 .gitignore）：%r" % bad[:8]


def test_no_js_writes_next_to_dirname():
    """`.js` 同样不许往 `__dirname` 旁边写 —— 编辑器侧会往仓库里漏日志。

    实测现状是干净的：`extension.js` 的日志用 `os.tmpdir()`，
    `test_*.js` 里的 `__dirname` 只用于**读**语料。这条棘轮守的是"以后别变"。
    """
    bad = []
    for p in _js_files():
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        if rel in EXEMPT:
            continue
        for line in _js_violations(p):
            bad.append("%s:%d" % (rel, line))
    assert not bad, (
        "这些 JS 往「模块旁边」写文件（会污染仓库工作区）：\n  " +
        "\n  ".join(bad[:10]) +
        "\n  修法：目标路径改用 `os.tmpdir()` 或用户工程内的目录")


def test_js_ratchet_has_teeth():
    """**牙齿**：造一段 `writeFileSync(path.join(__dirname, …))` 必须被抓。"""
    import tempfile

    src = (
        "const fs = require('fs');\n"
        "const path = require('path');\n"
        "fs.writeFileSync(path.join(__dirname, 'x.log'), 'x');\n"
        "// fs.writeFileSync(path.join(__dirname, 'ok.log'), 'x');\n"
    )
    d = tempfile.mkdtemp(prefix="hygjs_")
    p = os.path.join(d, "bad.js")
    try:
        io.open(p, "w", encoding="utf-8", newline="\n").write(src)
        hits = _js_violations(p)
        assert hits == [3], "只有第 3 行该被抓（第 4 行是注释），实得 %r" % (hits,)
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_ratchet_has_teeth():
    """**牙齿**：造一段真会写 `__file__` 旁边的代码，检查器必须认出来。"""
    import tempfile

    src = (
        "import io, os\n"
        "def f():\n"
        "    io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),\n"
        "                         'x.log'), 'a', encoding='utf-8').write('x')\n"
    )
    d = tempfile.mkdtemp(prefix="hyg_")
    p = os.path.join(d, "bad.py")
    try:
        io.open(p, "w", encoding="utf-8", newline="\n").write(src)
        assert _violations(p), "写模式 + __file__ 的调用竟然没被抓到"
        # 反向：改成读模式就不该被抓（否则会误伤一堆合法的资源读取）
        io.open(p, "w", encoding="utf-8", newline="\n").write(
            src.replace("'a', encoding", "'r', encoding"))
        assert not _violations(p), "读模式被误判成写（会逼人加无谓豁免）"
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
