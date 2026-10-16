# -*- coding: utf-8 -*-
"""把仓内新建的文本文件转成纯 CRLF（`core.autocrlf=false` + `* -text` ⇒ blob 必须 CRLF）。

判据（转换前后各一遍）：
  ① 只有行尾变化：去掉 `\\r` 后两版**逐字节相同**；
  ② 转换后 `crlf == 总换行数`（bareLF == 0）；
  ③ 代码围栏的**序号奇偶配对**不变、且零长度代码块仍为 0（R104b ㊱ 的现成判据）。
"""
import io
import sys


def fence_stats(text):
    lines = text.split("\n")
    idx = [i + 1 for i, l in enumerate(lines) if l.strip().startswith("```")]
    empty = [idx[k] for k in range(0, len(idx) - 1, 2) if idx[k + 1] == idx[k] + 1]
    return len(idx), len(idx) % 2, empty


def main(argv):
    path = argv[0]
    raw = io.open(path, "rb").read()
    text = raw.decode("utf-8")
    if raw.count(b"\r\n"):
        print("已经是 CRLF（或有混用）：crlf=%d" % raw.count(b"\r\n"))
        return 0
    f_before = fence_stats(text)
    out = text.replace("\n", "\r\n").encode("utf-8")
    io.open(path, "wb").write(out)
    back = io.open(path, "rb").read()
    problems = []
    if back.replace(b"\r\n", b"").replace(b"\n", b"") != raw.replace(b"\n", b""):
        problems.append("去掉行尾后两版不同 ⇒ 不只是行尾变化")
    if back.count(b"\n") - back.count(b"\r\n") != 0:
        problems.append("转换后仍有 bareLF=%d" % (back.count(b"\n") - back.count(b"\r\n")))
    f_after = fence_stats(back.decode("utf-8"))
    if f_after != f_before:
        problems.append("围栏统计变了：%r -> %r" % (f_before, f_after))
    print("围栏（个数, 奇偶, 零长度块）= %r -> %r" % (f_before, f_after))
    print("字节 %d -> %d（%+d，应等于换行数 %d）"
          % (len(raw), len(back), len(back) - len(raw), raw.count(b"\n")))
    if problems:
        for x in problems:
            print("  - " + x)
        return 1
    print("CRLF 转换通过：只动行尾 + bareLF 0 + 围栏统计不变")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
