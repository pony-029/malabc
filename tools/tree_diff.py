# -*- coding: utf-8 -*-
"""tree_diff.py —— 比两个目录的文件集合与内容（可按正则忽略行）。

为什么需要它：P2 搬 `render_*` 时，判据是「`--browse` 站点逐字节不变」。
但站点里的 `index.html` 与 `manifest.json` 内嵌 `generated_at`（R132/R146 两次
被它误导），所以「逐字节」必须能忽略那一行。

用法：

    python tools/tree_diff.py dirA dirB --ignore-line "generated_at"

退出码：
    0 = 文件集合相同，且每个文件（忽略指定行后）内容相同
    1 = 有差异（缺文件 / 多文件 / 内容不同）
    2 = 缺输入（目录不存在）
"""
import argparse
import hashlib
import os
import re
import sys


def walk(root):
    """{相对路径(posix): 绝对路径}，跳过 __pycache__。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out[rel] = full
    return out


def digest(path, ignore_re):
    """文件内容摘要；若给了 ignore_re，先删掉匹配的行再算。"""
    with open(path, "rb") as fh:
        data = fh.read()
    if ignore_re is None:
        return hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return hashlib.sha256(data).hexdigest()
    kept = [ln for ln in text.splitlines(True) if not ignore_re.search(ln)]
    return hashlib.sha256("".join(kept).encode("utf-8")).hexdigest()


def compare(a_root, b_root, ignore_pattern=None, ignore_file=None):
    if not os.path.isdir(a_root) or not os.path.isdir(b_root):
        print("tree_diff: 缺输入（目录不存在）")
        return 2
    ignore_re = re.compile(ignore_pattern) if ignore_pattern else None
    file_re = re.compile(ignore_file) if ignore_file else None
    a, b = walk(a_root), walk(b_root)
    if file_re is not None:
        # `manifest.json` 记录每个页面的 sha256：`index.html` 的时间戳一变，
        # 它也跟着变（哈希链）。这类「产物清单」不参与内容比较。
        a = {k: v for k, v in a.items() if not file_re.search(k)}
        b = {k: v for k, v in b.items() if not file_re.search(k)}

    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    changed = []
    for rel in sorted(set(a) & set(b)):
        if digest(a[rel], ignore_re) != digest(b[rel], ignore_re):
            changed.append(rel)

    same = not (only_a or only_b or changed)
    print('{"same": %s, "only_in_a": %d, "only_in_b": %d, "changed": %d, '
          '"files": %d, "ignore": %r, "ignore_file": %r}'
          % ("true" if same else "false", len(only_a), len(only_b),
             len(changed), len(a), ignore_pattern, ignore_file))
    for rel in only_a[:5]:
        print("  only_a  " + rel)
    for rel in only_b[:5]:
        print("  only_b  " + rel)
    for rel in changed[:5]:
        print("  changed " + rel)
    return 0 if same else 1


def _selftest():
    import shutil
    import tempfile
    bad, good = 0, 0
    tmp = tempfile.mkdtemp(prefix="td-")

    def w(root, rel, text):
        p = os.path.join(root, rel.replace("/", os.sep))
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    a = os.path.join(tmp, "a")
    b = os.path.join(tmp, "b")
    c = os.path.join(tmp, "c")
    d = os.path.join(tmp, "d")
    w(a, "x.html", "<p>1</p>\n")
    w(b, "x.html", "<p>1</p>\n")
    w(c, "x.html", "<p>2</p>\n")
    w(d, "x.html", '<p>1</p>\n<div class="generated_at">T</div>\n')

    cases = [
        (a, b, None, 0, "完全相同"),
        (a, c, None, 1, "内容不同必须红"),
        (a, d, None, 1, "多了 generated_at 行、未忽略 -> 必须红"),
        (a, d, "generated_at", 0, "忽略该行后一致"),
    ]
    for p1, p2, pat, want, why in cases:
        got = compare(p1, p2, pat)
        if got == want:
            good += 1
        else:
            bad += 1
            print("  [selftest] %s：期望 rc=%d 实际 %d" % (why, want, got))

    e = os.path.join(tmp, "e")
    w(e, "x.html", "<p>1</p>\n")
    w(e, "y.html", "<p>2</p>\n")
    if compare(a, e, None) == 1:
        good += 1
    else:
        bad += 1
        print("  [selftest] 多一个文件必须红")

    if compare(os.path.join(tmp, "nope"), a, None) == 2:
        good += 1
    else:
        bad += 1
        print("  [selftest] 缺目录应 rc=2")

    shutil.rmtree(tmp, ignore_errors=True)
    return bad, good


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("a", nargs="?")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--ignore-line", default=None)
    ap.add_argument("--ignore-file", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", action="store_true")
    args = ap.parse_args(argv)

    if args.help:
        print(__doc__)
        return 0
    if args.selftest:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1
    if not args.a or not args.b:
        print("tree_diff: 需要两个目录")
        return 2
    return compare(args.a, args.b, args.ignore_line, args.ignore_file)


if __name__ == "__main__":
    sys.exit(main())
