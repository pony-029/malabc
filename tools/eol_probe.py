# -*- coding: utf-8 -*-
"""eol_probe.py —— 行尾约定探测（**待升级为护栏**，当前不进 check_all）。

为什么需要它（R110 实测事故）
============================
R110 用 Python 脚本改 `matlabc.py` 一行文案，脚本写了 `newline="\\n"`，于是
**6 个文件从 CRLF 变成 LF**：

    matlabc.py                   | 68456 ++++++++++++++++-------------
    tools/check_help_contract.py |  5677 ++--
    README.md / README_CN.md / CONTRIBUTING.md / .gitignore
    8 files changed, 39596 insertions(+), 39572 deletions(-)

三行真实改动被放大成 6.8 万行 diff，评审看不见任何东西。发现方式是
`check_kernel_snapshot` 报 `bytes 1717722 → 1683494`，差额 34,228 恰好是行数。

**这道门就是那一类事故的对手方**：行尾不是风格问题，它决定 diff 是否可读、
决定 `--from-json` 的「重跑 == 仓库里那份文件」这个等式是否成立。

判据（EO1–EO3）
===============
    EO1 手写物必须是 CRLF：`.py` / `.md` / `.mmd` 与 `candidate*.json`
        不得出现**裸 LF**（前面不是 CR 的 LF）。
    EO2 生成物必须是 LF：`.html` / `.svg` 不得出现任何 CRLF。
        （archify 的 `serializeSvg()` 与 renderer 输出的是 LF 原始字节，
          "重跑 == 仓库里的文件"只有在不转换时才成立。）
    EO3 扫描面不得缩水：实际扫描的文本文件数必须 ≥ MIN_SCANNED。
        否则把 `os.walk` 的 skip 列表改宽就能让门永久变绿。

**不判**的东西（各有理由）
--------------------------
* `.json` 里只判 `candidate*.json`（手写源）；`*.delivery.json` 与
  `browser/*.json` 是 archify 的原始输出（LF），不是手写物。
* `.workbuddy/`、`.archify/`、`matlabc_browse/`、`_r*/` 是工具工作目录。
* 二级制文件不读。

用法：
    python tools/eol_probe.py            # 0=全部合规 1=有违规 2=缺输入
    python tools/eol_probe.py --selftest  # 两向自证
    python tools/eol_probe.py --help

退出码：
    0 = EO1–EO3 全部通过
    1 = 发现违规（裸 LF / CRLF / 扫描面缩水）
    2 = 缺输入（扫不到任何文本文件）
"""
import argparse
import os
import shutil
import sys
import tempfile

ROW_SIGNATURE = "EO1–EO3"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".workbuddy", ".archify",
             "matlabc_browse", "_kernel"}
CRLF_EXTS = {".py": True, ".md": True, ".mmd": True}
LF_EXTS = {".html": True, ".svg": True}

# 扫描面下界（R110 实测：85 个 .py + 95 个 .md + 39 个 .html + 26 个 .svg
# + 21 个 .mmd + 若干 candidate*.json ≈ 270）。取 200 留余量。
MIN_SCANNED = 200


def _classify(fn):
    """返回 ('crlf'|'lf'|None)。"""
    low = fn.lower()
    ext = os.path.splitext(low)[1]
    if ext in CRLF_EXTS:
        return "crlf"
    if ext in LF_EXTS:
        return "lf"
    if low.startswith("candidate") and ext == ".json":
        return "crlf"
    return None


def _walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith("_r")]
        for fn in filenames:
            yield os.path.join(dirpath, fn), fn


def scan(root, on_problem, min_scanned=None):
    """返回扫描到的合规目标数。"""
    min_scanned = MIN_SCANNED if min_scanned is None else min_scanned
    n = 0
    for path, fn in _walk(root):
        kind = _classify(fn)
        if kind is None:
            continue
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        n += 1
        crlf = data.count(b"\r\n")
        bare_lf = data.count(b"\n") - crlf
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if kind == "crlf" and bare_lf:
            on_problem("EO1 %s 有 %d 个裸 LF（手写物必须 CRLF）" % (rel, bare_lf))
        if kind == "lf" and crlf:
            on_problem("EO2 %s 有 %d 个 CRLF（生成物必须保留渲染器原始字节）"
                       % (rel, crlf))
    if n < min_scanned:
        on_problem("EO3 只扫到 %d 个文本文件（下界 %d）—— 扫描面缩水或仓库不完整"
                   % (n, min_scanned))
    return n


def _mk(root, rel, data):
    p = os.path.join(root, rel.replace("/", os.sep))
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(p, "wb") as fh:
        fh.write(data)


def _selftest():
    bad, good = 0, 0
    root = tempfile.mkdtemp(prefix="eol-probe-")
    try:
        _mk(root, "a.py", b"x = 1\r\ny = 2\r\n")
        _mk(root, "b.md", b"# t\r\n")
        _mk(root, "c.html", b"<html>\n</html>\n")
        _mk(root, "d/candidate.json", b'{"a": 1}\r\n')
        probs = []
        n = scan(root, probs.append, min_scanned=4)
        if not probs and n == 4:
            good += 1
        else:
            bad += 1
            print("  [selftest] 干净样本被误伤：%s n=%d" % (probs, n))

        _mk(root, "bad.py", b"x = 1\ny = 2\n")
        probs = []
        scan(root, probs.append, min_scanned=4)
        if any(p.startswith("EO1") and "bad.py" in p for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] EO1 裸 LF 未红")
        os.remove(os.path.join(root, "bad.py"))

        _mk(root, "bad.html", b"<html>\r\n</html>\r\n")
        probs = []
        scan(root, probs.append, min_scanned=4)
        if any(p.startswith("EO2") and "bad.html" in p for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] EO2 CRLF 未红")
        os.remove(os.path.join(root, "bad.html"))

        probs = []
        scan(root, probs.append, min_scanned=999)
        if any(p.startswith("EO3") for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] EO3 扫描面缩水未红")

        _mk(root, ".workbuddy/memory/x.md", b"a\nb\n")
        probs = []
        scan(root, probs.append, min_scanned=4)
        if not any("x.md" in p for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] 工具目录未被豁免")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return bad, good


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", action="store_true")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    if args.help:
        print(__doc__)
        return 0
    if args.selftest:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1

    root = args.root or ROOT
    probs = []
    n = scan(root, probs.append)
    for p in probs:
        print("  - " + p)
    if probs:
        print("eol_probe: %d 项不合规" % len(probs))
        return 1
    if n == 0:
        print("eol_probe: 缺输入（扫不到文本文件）")
        return 2
    print("eol_probe: OK（%d 个文本文件，%s 全绿；待升级为护栏）" % (n, ROW_SIGNATURE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
