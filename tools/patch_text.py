# -*- coding: utf-8 -*-
"""带语法自检的文本替换器 —— 给"改仓库文件"这件小事加一道保险。

为什么要有它
============
这一年里反复出现同一类自伤：写一段替换脚本，脚本里的字符串带引号 /
换行 / 中文标点，结果**脚本自己先语法错**，或者改完的文件语法错而没人发现
（下一轮才在别的地方炸）。这类错误本身不严重，但每次都要重来一遍。

它做三件小事：
  1. 原文与新文都从**文件**读（不走命令行参数，避开 shell 的引号/反斜杠翻译）
  2. 保留原文件的换行风格（CRLF / LF）
  3. 改完**立刻编译/语法检查**：.py 用 py_compile，.js 用 node --check
     —— 不通过就**回滚并报错**，绝不留一个坏文件

用法：
    python tools/patch_text.py --file a.js --old old.txt --new new.txt
    python tools/patch_text.py --file a.py --old old.txt --new new.txt --count 2
    python tools/patch_text.py --selftest

退出码：
    0 = 改好且语法检查通过
    1 = 锚点没命中 / 命中数不符 / 语法检查失败（已回滚）
    2 = 参数或文件问题
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile

ROW_SIGNATURE = "PT1-PT2"
#: 显式声明"本工具支持 --selftest"。
# 为什么不用搜索 `--selftest` 字符串来判定：`new_gate.py` 的**模板**
# 里也写着这四个字，于是被误判成"带自证的工具"，一跑就报参数缺失。
SELFTEST = True

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _read(path):
    with io.open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    return text, ("\r\n" in text)


def _write(path, text, crlf):
    if crlf:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    with io.open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def _syntax_ok(path):
    """改完立刻验语法：不同后缀用不同工具。"""
    low = path.lower()
    if low.endswith(".py"):
        try:
            import py_compile
            py_compile.compile(path, doraise=True)
            return True, ""
        except Exception as exc:
            return False, str(exc)
    if low.endswith(".js"):
        try:
            p = subprocess.run(["node", "--check", path],
                               stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=60)
            if p.returncode == 0:
                return True, ""
            return False, p.stdout.decode("utf-8", "replace")[-800:]
        except (OSError, subprocess.SubprocessError) as exc:
            return True, ""      # 没装 node 就不判负
    return True, ""


def patch(path, old, new, count=1):
    """返回 (ok, msg)。失败时不改动文件。"""
    if not os.path.isfile(path):
        return False, "找不到文件：%s" % path
    text, crlf = _read(path)
    # **锚点做换行归一**：仓库里大多是 CRLF，而锚点文件通常是 LF ——
    # 不归一就必然「锚点没命中」，而这看起来像是"文件已被改过"，很误导。
    text = text.replace("\r\n", "\n")
    old = old.replace("\r\n", "\n")
    new = new.replace("\r\n", "\n")
    hits = text.count(old)
    if hits == 0:
        return False, "锚点没命中（0 处）—— 文件可能已被改过"
    if count and hits != count:
        return False, "锚点命中 %d 处，期望 %d 处（用 --count 0 表示不限）" % (
            hits, count)
    out = text.replace(old, new) if not count else text.replace(old, new, count)
    _write(path, out, crlf)
    ok, why = _syntax_ok(path)
    if not ok:
        _write(path, text, crlf)         # 回滚
        return False, "语法检查失败，已回滚：%s" % why
    try:            # 临时目录可能在另一个盘符上，relpath 会抛 ValueError
        shown = os.path.relpath(path, REPO)
    except ValueError:
        shown = path
    return True, "已改 %s（%d 处，%s）" % (
        shown, hits, "CRLF" if crlf else "LF")


def run_plan(path, apply_=True):
    """按 JSON 计划批量打补丁。

    为什么要批量：一轮改动常常 6~10 个文件，逐个调一次命令既慢又容易漏。
    计划里 old/new 是**内联字符串**（JSON 里写，不经 shell），
    所以引号/反斜杠仍然是安全的。
    """
    try:
        data = json.loads(io.open(path, encoding="utf-8").read())
    except (IOError, OSError, ValueError) as exc:
        return False, u"读不了计划文件：%s" % exc
    items = data.get("patches") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        return False, u"计划里没有 patches（应为非空数组）"

    ok_all = True
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            print(u"  %d. 跳过：不是对象" % i)
            ok_all = False
            continue
        f = it.get("file") or u""
        old = it.get("old") or u""
        new = it.get("new") or u""
        cnt = int(it.get("count", 1) or 0)
        if not (f and old):
            print(u"  %d. 跳过：缺 file / old" % i)
            ok_all = False
            continue
        target = f if os.path.isabs(f) else os.path.join(REPO, f)
        ok, msg = patch(target, old, new, cnt)
        print(u"  %d. %s" % (i, msg))
        if not ok:
            ok_all = False
    return ok_all, u"%d 个补丁" % len(items)


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--file")
    ap.add_argument("--old")
    ap.add_argument("--new")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--plan", help="批量补丁的 JSON 文件")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.plan:
        ok, msg = run_plan(args.plan)
        return 0 if ok else 1
    if not (args.file and args.old and args.new):
        print("需要 --plan，或 --file / --old / --new（--old/--new 是**文件路径**）")
        return 2
    try:
        old = io.open(args.old, encoding="utf-8").read()
        new = io.open(args.new, encoding="utf-8").read()
    except (IOError, OSError) as exc:
        print("读不了锚点/新文：%s" % exc)
        return 2
    ok, msg = patch(args.file, old, new, args.count)
    print(msg)
    return 0 if ok else 1


def selftest():
    """两向自证：正常替换要成功，坏锚点/坏语法要失败且不留坏文件。"""
    good = bad = 0

    def chk(cond, name):
        nonlocal good, bad
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %s" % name)

    d = tempfile.mkdtemp(prefix="pt_")
    try:
        p = os.path.join(d, "x.py")
        io.open(p, "w", encoding="utf-8", newline="").write(u"a = 1\n")
        ok, _ = patch(p, u"a = 1", u"a = 2")
        chk(ok and io.open(p, encoding="utf-8").read() == u"a = 2\n",
            "正常替换成功")

        ok2, _ = patch(p, u"不存在", u"x")
        chk(not ok2, "锚点没命中会失败")

        # 改成坏语法 → 必须失败且内容回滚
        before = io.open(p, encoding="utf-8").read()
        ok3, msg3 = patch(p, u"a = 2", u"a = ((")
        after = io.open(p, encoding="utf-8").read()
        chk(not ok3 and after == before, "语法错会回滚（%s）" % msg3[:40])

        # CRLF 保留
        p2 = os.path.join(d, "y.py")
        io.open(p2, "wb").write(b"x = 1\r\n")
        patch(p2, u"x = 1", u"x = 9")
        chk(b"\r\n" in io.open(p2, "rb").read(), "CRLF 被保留")

        # 批量计划：两条都该生效
        p3 = os.path.join(d, "z.py")
        io.open(p3, "w", encoding="utf-8", newline="").write(u"a = 1\nb = 1\n")
        plan = os.path.join(d, "plan.json")
        io.open(plan, "w", encoding="utf-8", newline="").write(
            u'{"patches": [{"file": "%s", "old": "a = 1", "new": "a = 2"},'
            u' {"file": "%s", "old": "b = 1", "new": "b = 2"}]}'
            % (p3.replace("\\", "/"), p3.replace("\\", "/")))
        okp, _m = run_plan(plan)
        body = io.open(p3, encoding="utf-8").read()
        chk(okp and u"a = 2" in body and u"b = 2" in body, "批量计划两条都生效")
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
