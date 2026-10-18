# -*- coding: utf-8 -*-
"""版本号推进器：**每一位只走 0–9，满 10 进一位**。

规则
====

    patch 0..9          -> 0.7.3 -> 0.7.4
    patch 满 10         -> 0.7.9 -> 0.8.0
    minor 满 10         -> 0.9.9 -> 1.0.0

为什么要有这个脚本
------------------

在此之前版本号是**手改**的：每次发版都去 `package.json` 里把数字加一。
上一轮走到 `0.6.104` —— 补丁位三位数，版本号读起来像日期，也比较不了
"哪一版更新得多"。规则本身不复杂，但**靠人记必然走样**：
写 `0.6.105` 和写 `0.7.0` 在任何一道门里都看不出来。

所以把规则装进一个地方：

    python tools/bump_version.py            # 只打印下一版，不改文件
    python tools/bump_version.py --apply    # 真的写进 package.json
    python tools/bump_version.py --check    # 当前版本是否符合规则（不符则 rc=1）

`--check` 是给发布前用的：不符合规则时返回非零，
这样"忘了走规则"能在打包前被挡住，而不是靠发布后回看。
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PKG = os.path.join(ROOT, "vscode", "package.json")

MAX_DIGIT = 9          # 每一位的最大值：满 10 进一位


def parse(v):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", (v or "").strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def conforms(v):
    """每一位都应在 0..MAX_DIGIT 之内。"""
    t = parse(v)
    return bool(t) and all(0 <= x <= MAX_DIGIT for x in t)


def next_of(v):
    """按「满 10 进一位」推进。

    注意它同时负责**把不合规的旧版本收拢回规则内**：
    `0.6.104` 的 patch=104 已经越界，于是进到 `0.7.0` ——
    这正是切规则时要发生的事，不需要人工特殊处理。
    """
    t = parse(v)
    if t is None:
        raise ValueError("看不懂的版本号：%r" % (v,))
    major, minor, patch = t
    if patch < MAX_DIGIT:
        return "%d.%d.%d" % (major, minor, patch + 1)
    if minor < MAX_DIGIT:
        return "%d.%d.0" % (major, minor + 1)
    return "%d.0.0" % (major + 1)


def load():
    with io.open(PKG, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save(doc):
    with io.open(PKG, "w", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    doc = load()
    cur = str(doc.get("version") or "")
    nxt = next_of(cur)

    if "--check" in argv:
        if conforms(cur):
            print("bump_version: OK（%s 每位都在 0–%d 之内）" % (cur, MAX_DIGIT))
            return 0
        print("bump_version: FAIL（%s 有越界的位；下一个合规版本是 %s）"
              % (cur, nxt))
        return 1

    if "--apply" in argv:
        doc["version"] = nxt
        save(doc)
        print("bump_version: %s -> %s（已写入 package.json）" % (cur, nxt))
        print("           别忘了在 CHANGELOG 顶部补 ## %s" % nxt)
        return 0

    print("bump_version: 当前 %s -> 下一版 %s" % (cur, nxt))
    print("            要真的写入，加 --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
