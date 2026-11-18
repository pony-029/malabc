# -*- coding: utf-8 -*-
"""**轮次收尾**：一条命令完成「感知 + 成长 + 记本轮 + 打印脑状态三段」。

    python tools/round_close.py --goal "把 lo=i-w 修到 10/10" --result "未达成：范围缩到 27 行"

## 为什么要有它（用户第二次提醒我忘了）

前两轮的报告里我**没有写脑状态** —— 因为"记得写"这件事本身没有任何东西在守。
于是把收尾做成**一条命令**，再由门（`check_brain_growth` 的 BG7）检查
`flow/rounds.jsonl` 的**最后一条**是否与当前知识库一致：

* 不跑 `round_close` → 库变了而轮次记录没变 → BG7 红
* 跑了但没带 `--goal/--result` → BG7 红（"记了什么"必须能读出来）

## 落盘格式（每轮一行）

    {"ts":..., "goal":..., "result":..., "entries":19, "lessons_added":2,
     "brief": {"senses":..., "knowledge":..., "growth":...}}

`lessons_added` 允许为 0（有些轮次纯粹是诊断），但**必须显式写** ——
"这轮没学到东西"是一句结论，而"没写"不是。

退出码：
    0 = 已记录
    1 = 记了但有异议（如知识库条数倒退）
    2 = 缺输入（知识库不存在）
"""
import argparse
import io
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import brain  # noqa: E402

ROUNDS = os.path.join(ROOT, "flow", "rounds.jsonl")


def _last_total():
    """上一轮记录里的条数（用于算本轮新增了几条教训）。"""
    if not os.path.isfile(ROUNDS):
        return None
    last = None
    for ln in io.open(ROUNDS, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            last = json.loads(ln)
        except ValueError:
            continue
    return (last or {}).get("entries")


def close(goal, result, note=""):
    st = brain.senses(write=True)          # 感知先刷新
    cur, _prev, _delta = brain.growth()    # 再记快照
    total = cur["total"]
    prev = _last_total()
    added = None if prev is None else total - prev

    b = brain.brief(multi=True).splitlines()
    rec = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "goal": goal,
        "result": result,
        "entries": total,
        "lessons_added": added,
        "brief": {"senses": b[0] if len(b) > 0 else "",
                  "knowledge": b[1] if len(b) > 1 else "",
                  "growth": b[2] if len(b) > 2 else ""},
    }
    if note:
        rec["note"] = note
    io.open(ROUNDS, "a", encoding="utf-8", newline="\n").write(
        json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="轮次收尾：感知+成长+记录")
    ap.add_argument("--goal", required=True, help="本轮唯一目标")
    ap.add_argument("--result", required=True, help="达成/未达成，一句话")
    ap.add_argument("--note", default="")
    ns = ap.parse_args(argv)

    rec = close(ns.goal, ns.result, ns.note)
    print(rec["brief"]["senses"])
    print(rec["brief"]["knowledge"])
    print(rec["brief"]["growth"])
    print("[round] 已记录：%s ｜ 本轮新增教训 %s 条"
          % (rec["ts"], "首次" if rec["lessons_added"] is None
             else rec["lessons_added"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
