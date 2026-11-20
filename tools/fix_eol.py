# -*- coding: utf-8 -*-
"""按仓库约定统一行尾：**手写物 CRLF，生成物 LF**。

    python tools/fix_eol.py <文件...>      # 按约定逐个修正
    python tools/fix_eol.py --show         # 打印约定表与判定结果
    python tools/fix_eol.py --selftest     # 两向自证

## 为什么要收进仓库（R1024）

同一件行尾事故我犯了 **四次**：前三次是 `flow/bench_all.html`，第四次是
`flow/full_report.html`。每次都说"记住了"，下次照犯。

根因不在记忆，在**动作**：我提交前习惯性跑一个"把所有文件转 CRLF"的小脚本，
而它不区分对象。上一轮我把它改成按约定判断 —— 但它住在 `C:\\temp\\`，
**不在版本库里**：换台机器就没有，也不会被任何门看见、被任何人复用。

这一版把它搬进 `tools/`，于是它能被 `check_tool_selftests` 执行、
被 `check_tool_discoverability` 要求登记、被 code review 看见。

## 判据从哪来

`tools/check_eol_convention.py` 的 `CRLF_EXTS` / `LF_EXTS` —— **单一真源**。
本工具不自己维护第二张表：两处各写一份，迟早会不一致（RG5/RG4 那几轮
的教训都是"两份东西被当成一份"）。

退出码：
    0 = 全部符合约定（或已修正）
    1 = 有文件无法判断/读写出错
    2 = 读不到约定表（拒绝盲转）
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _tables():
    """从编码约定门读扩展名表（单一真源）。读不到就抛，绝不猜。"""
    import check_eol_convention as C
    return C.CRLF_EXTS, C.LF_EXTS


def want_eol(path, crlf_exts, lf_exts):
    """返回 'crlf' / 'lf' / None（None = 扩展名不在约定表，不处理）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in crlf_exts:
        return "crlf"
    if ext in lf_exts:
        return "lf"
    return None


def fix_one(path, crlf_exts, lf_exts):
    """按约定修正单个文件。返回 (状态, 说明)。"""
    want = want_eol(path, crlf_exts, lf_exts)
    if want is None:
        return "skip", "扩展名不在约定表，不处理"
    try:
        raw = io.open(path, "r", encoding="utf-8", newline="").read()
    except (IOError, OSError) as e:
        return "err", "读不到（%s）" % type(e).__name__
    if want == "crlf":
        fixed = raw.replace(u"\r\n", u"\n").replace(u"\n", u"\r\n")
    else:
        fixed = raw.replace(u"\r\n", u"\n")
    if fixed == raw:
        return "ok", "已是 %s" % want.upper()
    try:
        io.open(path, "w", encoding="utf-8", newline="").write(fixed)
    except (IOError, OSError) as e:
        return "err", "写入失败（%s）" % type(e).__name__
    return "fixed", "已转 %s" % want.upper()


def _selftest():
    """**两向自证**：手写物必须转 CRLF，生成物必须转 LF，不认识的不动。

    只验"能跑"不算自证 —— 一个把一切都转 CRLF 的实现也能通过那一项，
    而那正是我犯了四次的那个错。
    """
    import shutil
    import tempfile

    good = bad = 0
    try:
        crlf_exts, lf_exts = _tables()
    except Exception as e:                     # noqa: BLE001
        print("  [selftest] 读不到约定表：%s" % type(e).__name__)
        print('SELFTEST COUNTS {"bad": 1, "good": 0}')
        return 1

    d = tempfile.mkdtemp(prefix="fixeol_")
    try:
        # ① 手写物（.md）：LF 输入 -> CRLF 输出
        p = os.path.join(d, "a.md")
        io.open(p, "w", encoding="utf-8", newline="").write("x\ny\n")
        st, _ = fix_one(p, crlf_exts, lf_exts)
        body = io.open(p, "r", encoding="utf-8", newline="").read()
        if st == "fixed" and "\r\n" in body:
            good += 1
        else:
            bad += 1
            print("  [selftest] .md 未被转成 CRLF（状态 %s）" % st)

        # ② 生成物（.html）：CRLF 输入 -> LF 输出（这是四次事故的正题）
        p = os.path.join(d, "b.html")
        io.open(p, "w", encoding="utf-8", newline="").write("x\r\ny\r\n")
        st, _ = fix_one(p, crlf_exts, lf_exts)
        body = io.open(p, "r", encoding="utf-8", newline="").read()
        if st == "fixed" and "\r" not in body:
            good += 1
        else:
            bad += 1
            print("  [selftest] .html 未被转成 LF（状态 %s）" % st)

        # ③ 不认识的扩展名：必须原样不动
        p = os.path.join(d, "c.xyz")
        io.open(p, "w", encoding="utf-8", newline="").write("x\r\ny\r\n")
        st, _ = fix_one(p, crlf_exts, lf_exts)
        body = io.open(p, "r", encoding="utf-8", newline="").read()
        if st == "skip" and "\r\n" in body:
            good += 1
        else:
            bad += 1
            print("  [selftest] 未知扩展名被改动了（状态 %s）" % st)

        # ④ 已符合约定时不该重复写（幂等）
        p = os.path.join(d, "d.md")
        io.open(p, "w", encoding="utf-8", newline="").write("x\r\ny\r\n")
        st, _ = fix_one(p, crlf_exts, lf_exts)
        if st == "ok":
            good += 1
        else:
            bad += 1
            print("  [selftest] 已符合约定却仍报改动（状态 %s）" % st)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return _selftest()

    try:
        crlf_exts, lf_exts = _tables()
    except Exception as e:                     # noqa: BLE001
        print("fix_eol: 读不到编码约定（%s: %s）—— 拒绝盲转"
              % (type(e).__name__, e))
        return 2

    if not argv or "--show" in argv:
        print("手写物 -> CRLF：%s" % sorted(crlf_exts))
        print("生成物 -> LF  ：%s" % sorted(lf_exts))
        print("其它扩展名：不处理（避免猜错）")
        for p in [a for a in argv if not a.startswith("--")]:
            print("  %-40s -> %s" % (p, want_eol(p, crlf_exts, lf_exts) or "不处理"))
        return 0

    rc = 0
    for p in argv:
        st, msg = fix_one(p, crlf_exts, lf_exts)
        print("%-7s %-11s %s" % ("[%s]" % st.upper(), msg, p))
        if st == "err":
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
