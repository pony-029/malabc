# -*- coding: utf-8 -*-
"""R102 通用小工具：把仓内文件转成 CRLF 并核账（仓内 blob 全 CRLF）。

用法：python ensure_crlf.py <path> [...]
输出：bytes / CRLF 行数 / 裸 LF 数（裸 LF 必须为 0）。
"""
import io
import sys


def main(argv):
    if not argv:
        print("用法：python ensure_crlf.py <path> [...]")
        return 2
    bad = 0
    for p in argv:
        with io.open(p, "rb") as fh:
            raw = fh.read()
        crlf = raw.count(b"\r\n")
        bare = raw.count(b"\n") - crlf
        if bare:
            text = raw.decode("utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
            with io.open(p, "wb") as fh:
                fh.write(text.encode("utf-8"))
            raw2 = io.open(p, "rb").read()
            print("%-46s %d -> %d B  CRLF=%d bareLF=%d  （已转）"
                  % (p, len(raw), len(raw2), raw2.count(b"\r\n"),
                     raw2.count(b"\n") - raw2.count(b"\r\n")))
        else:
            print("%-46s %8d B  CRLF=%-5d bareLF=0  OK"
                  % (p, len(raw), crlf))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
