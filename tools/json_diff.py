# -*- coding: utf-8 -*-
"""json_diff.py —— 比两份 JSON 在**忽略指定键**后是否完全一致。

为什么需要它：本项目的核心判据是「改动前后输出不变」，但 `--json` 里有
`generated_at` 时间戳，`--browse` 的 `manifest.json` 也有。R146 的 F1 就被它
误判成「变了」——字节数相同（62005）、sha 不同，第一处差异在第 62 字节。

用法：

    python tools/json_diff.py a.json b.json --ignore generated_at
    python tools/json_diff.py a.json b.json --ignore generated_at --ignore heuristics

退出码：
    0 = 忽略指定键后完全一致
    1 = 仍有差异（会打印第一处差异的路径）
    2 = 缺输入（文件不存在 / 不是合法 JSON）
"""
import argparse
import json
import os
import sys


def canon(path, ignore):
    """去掉 ignore 里的顶层键，再以 sort_keys 序列化。"""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    for key in ignore:
        if isinstance(data, dict):
            data.pop(key, None)
    return json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2)


def first_diff(a, b):
    """返回第一处差异所在的键路径（粗粒度：顶层键），找不到返回 None。"""
    try:
        da = json.loads(a)
        db = json.loads(b)
    except ValueError:
        return None
    if not isinstance(da, dict) or not isinstance(db, dict):
        return None
    ka, kb = set(da), set(db)
    if ka != kb:
        only_a, only_b = sorted(ka - kb), sorted(kb - ka)
        return "keys only_in_a=%r only_in_b=%r" % (only_a, only_b)
    for k in sorted(ka):
        if da[k] != db[k]:
            return k
    return None


def compare(p1, p2, ignore):
    a, b = canon(p1, ignore), canon(p2, ignore)
    if a == b:
        print('IDENTICAL {"ignored": %r, "canon_bytes": %d}'
              % (list(ignore), len(a.encode("utf-8"))))
        return 0
    key = first_diff(a, b)
    print('DIFFERENT {"ignored": %r, "first_diff": %r}' % (list(ignore), key))
    return 1


def _selftest():
    import tempfile
    bad, good = 0, 0
    tmp = tempfile.mkdtemp(prefix="jd-")

    def w(name, obj):
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)
        return p

    base = {"generated_at": "T1", "files": [1, 2], "heuristics": [1]}
    same = dict(base)
    tdiff = dict(base, generated_at="T2")
    hdiff = dict(base, generated_at="T1", heuristics=[1, 2])
    fdiff = dict(base, generated_at="T1", files=[1, 2, 3])

    p_base = w("base.json", base)
    p_same = w("same.json", same)
    p_t = w("t.json", tdiff)
    p_h = w("h.json", hdiff)
    p_f = w("f.json", fdiff)

    cases = [
        (p_base, p_same, (), 0, "完全相同的两份"),
        (p_base, p_t, ("generated_at",), 0, "只差时间戳且已忽略"),
        (p_base, p_t, (), 1, "只差时间戳但未忽略 -> 必须红"),
        (p_base, p_h, ("generated_at", "heuristics"), 0, "忽略 heuristics 后一致"),
        (p_base, p_f, ("generated_at",), 1, "其它键变了 -> 必须红"),
    ]
    for p1, p2, ign, want, why in cases:
        got = compare(p1, p2, ign)
        if got == want:
            good += 1
        else:
            bad += 1
            print("  [selftest] %s：期望 rc=%d 实际 %d" % (why, want, got))

    try:
        compare(os.path.join(tmp, "nope.json"), p_base, ())
    except (IOError, OSError, ValueError):
        good += 1
    else:
        bad += 1
        print("  [selftest] 缺文件应抛异常")

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return bad, good


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("a", nargs="?")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--ignore", action="append", default=[])
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
        print("json_diff: 需要两个 JSON 路径")
        return 2
    for p in (args.a, args.b):
        if not os.path.isfile(p):
            print("json_diff: 缺输入（%s）" % p)
            return 2
    try:
        return compare(args.a, args.b, args.ignore)
    except ValueError as exc:
        print("json_diff: 不是合法 JSON（%s）" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
