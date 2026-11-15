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
