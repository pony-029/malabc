# -*- coding: utf-8 -*-
"""**自改进 harness**：跑检查 → 把失败入库 → 用向量库反查历史同类 → 给下一步。

    python tools/harness.py run                # 完整闭环（每组检查后立即归因）
    python tools/harness.py run --only mir     # 只跑某一组
    python tools/harness.py plan               # 只看"下一步做什么"（不跑检查）

## 它和"跑一遍测试"的区别

普通测试给的是**红/绿**；harness 给的是**"红了，而且历史上这类错犯过 N 次、
当时的规则是 X、见证是 Y"**。差别在于它把三件事串成一条链：

    失败 → 入库（可检索） → 反查历史 → 产出下一步建议

## 为什么失败要"入库"而不是只打印

打印出来的失败，下一次就被滚动掉了。入库之后：
* 同一个失败重复出现时，能算出"这是第几次"（重复本身就是信号）
* AI agent 可以按语义查到"这类问题以前怎么解决的"，而不是从头推理
* 入库记录带 `witness` —— 强制回答"下次谁拦它"

## 自改进的边界（重要）

harness **不自动改代码**。它只做"发现 → 归因 → 排序"，
把改动交给人和 agent —— 因为自动改代码的失败模式（改错地方、掩盖问题）
比它解决的问题更难发现。
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
PROBLEMS = os.path.join(ROOT, "flow", "problems.jsonl")
sys.path.insert(0, os.path.join(ROOT, "tools"))

#: 检查组：每组 = (名字, 命令)。命令返回非零即记为一次失败。
GROUPS = [
    ("失败登记", [PY, os.path.join(ROOT, "tools", "check_failures.py")]),
    ("解析切分", [PY, os.path.join(ROOT, "tools", "check_mir_split.py")]),
    ("编码约定", [PY, os.path.join(ROOT, "tools", "check_eol_convention.py")]),
    ("工具发现性", [PY, os.path.join(ROOT, "tools", "check_tool_discoverability.py")]),
]


def _run(cmd):
    try:
        r = subprocess.run(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=600)
        return r.returncode, r.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return -1, "超时（600s）"


def _append_problem(rec):
    io.open(PROBLEMS, "a", encoding="utf-8", newline="\n").write(
        json.dumps(rec, ensure_ascii=False) + "\n")


def _seen(title):
    """同一标题出现过几次 —— 重复次数是"该不该加自动判据"的最硬证据。"""
    n = 0
    if os.path.isfile(PROBLEMS):
        for ln in io.open(PROBLEMS, encoding="utf-8"):
            try:
                if json.loads(ln).get("title") == title:
                    n += 1
            except ValueError:
                continue
    return n


def run(only=None):
    rows = []
    for name, cmd in GROUPS:
        if only and only not in name:
            continue
        rc, out = _run(cmd)
        ok = rc == 0
        print("[harness] %-10s %s" % (name, "OK" if ok else "RED（rc=%d）" % rc))
        if ok:
            rows.append({"group": name, "ok": True})
            continue
        # 每条失败输出行都是一条"问题记录"
        detail = [ln.strip() for ln in out.splitlines()
                  if ln.strip().startswith("- ")]
        title = "%s 检查失败（%d 项）" % (name, len(detail) or 1)
        rec = {"id": "H%03d" % int(time.time() % 100000),
               "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               "group": name, "title": title,
               "text": " ".join(d[:160] for d in detail[:5]) or out[-300:],
               "meta": {"check": cmd[-1].split(os.sep)[-1], "rc": rc}}
        _append_problem(rec)
        rows.append({"group": name, "ok": False, "rec": rec,
                     "repeat": _seen(title)})
        for d in detail[:3]:
            print("           %s" % d[:110])
    return rows


def plan(rows=None):
    """把失败按"重复次数 + 语义近邻"排序，得到下一步。"""
    import brain_db as DB

    try:
        store = DB.load_store()
    except SystemExit:
        store = None
    if store is None or not store["items"]:
        n = DB.build()
        store = DB.load_store()

    todo = []
    for r in (rows or []):
        if r["ok"]:
            continue
        rec = r["rec"]
        hits = DB.query(store, rec["text"], 3)
        near = [it for _s, _i, it in hits if it["meta"].get("status") == "fixed"]
        repeat = r["repeat"]
        score = 100 * repeat + 10 * len(near)
        todo.append((score, rec["title"], repeat, near[:2]))
    todo.sort(key=lambda x: -x[0])

    print()
    if not todo:
        print("[plan] 没有失败 —— 但仍建议把「本轮新学到的东西」record 进大脑，"
              "否则知识库会停在上一轮")
        return 0
    print("[plan] 下一步（按'重复次数 + 是否有历史解法'排序）：")
    for score, title, repeat, near in todo:
        print("  [%3d] %s（历史上出现过 %d 次）" % (score, title, repeat))
        for it in near:
            print("        历史解法：%s —— %s" % (it["title"], it["text"][:80]))
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="自改进 harness")
    ap.add_argument("cmd", choices=("run", "plan"))
    ap.add_argument("--only", help="只跑名字含该子串的检查组")
    ns = ap.parse_args(argv)

    if ns.cmd == "plan":
        return plan()

    rows = run(ns.only)
    bad = [r for r in rows if not r["ok"]]
    if not bad:
        print("\n[harness] 全部检查通过（%d 组）" % len(rows))
        return 0
    return plan(rows)


if __name__ == "__main__":
    sys.exit(main())
