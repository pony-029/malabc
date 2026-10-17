# -*- coding: utf-8 -*-
"""登记制护栏：`facts.py` 的事实必须**重放**出 `--json` 的计数（FT1–FT3）。

为什么需要它
------------
`facts.py` 声称「同一批读数，另一种排版」。这句话如果没有对手方，它就只是
一段自述 —— 加一条事实、少一条事实、把 `kind` 拼错，三种都不会有人说话。

本门用**真语料**（`tests/sample_m`）跑一次公开 CLI，把载荷交给 facts 层，
再要求「重放 == 报表」。判据：

    FT1 重放恒等式：`replay_counts(facts_from_payload(p)) == expected_counts(p)`
        五类计数（files / functions / edges / unresolved / heuristics）逐项相等。
    FT2 位置完备：除 `file` 外，每条事实的 `loc.file` 必须非空
        （IDE 的「按位置查」与 Agent 的「按文件筛」都以它为前提）。
    FT3 种类封闭：事实的 `kind` 必须全在 `FACT_KINDS` 内 ——
        拼错的 kind 会被重放**静默漏计**，这是最容易发生的一种腐烂。

两向自证
--------
干净载荷放行；删一条事实、缺 loc.file、kind 拼错、报表计数被改 —— 四种都必须红。

用法：
    python tools/check_facts_replay.py             # 0=全绿 1=不一致 2=缺输入
    python tools/check_facts_replay.py --selftest   # 两向自证
    python tools/check_facts_replay.py --help       # 显示本帮助

退出码：
    0 = FT1–FT3 全部通过
    1 = 发现不一致（重放≠报表 / 事实无位置 / kind 越界）
    2 = 缺输入（找不到 facts.py / matlabc.py / 语料，或 CLI 跑不起来）
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile

ROW_SIGNATURE = "FT1–FT3"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLE = os.path.join("tests", "sample_m")


def _load_facts():
    sys.path.insert(0, ROOT)
    import facts  # noqa: E402
    return facts


def run_cli(root, out_path):
    """跑一次公开 CLI，返回 (returncode, stderr 摘要)。子进程切断 stdin + 超时。"""
    py = sys.executable
    cmd = [py, os.path.join(root, "matlabc.py"),
           os.path.join(root, SAMPLE), "--json", out_path]
    try:
        proc = subprocess.run(
            cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, str(exc)
    return proc.returncode, proc.stderr.decode("utf-8", "replace")[-400:]


def audit(root, on_problem):
    facts = _load_facts()
    if not os.path.isfile(os.path.join(root, "facts.py")):
        on_problem("FT0 缺 facts.py（缺输入 → 红）")
        return 0
    if not os.path.isdir(os.path.join(root, SAMPLE)):
        on_problem("FT0 缺语料 %s（缺输入 → 红）" % SAMPLE)
        return 0

    tmp = tempfile.mkdtemp(prefix="facts-replay-")
    try:
        out = os.path.join(tmp, "payload.json")
        rc, err = run_cli(root, out)
        if rc != 0 or not os.path.isfile(out):
            on_problem("FT0 CLI 跑不起来（rc=%r）：%s" % (rc, err))
            return 0
        with io.open(out, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    finally:
        try:
            for fn in os.listdir(tmp):
                os.remove(os.path.join(tmp, fn))
            os.rmdir(tmp)
        except OSError:
            pass

    got = facts.replay_counts(facts.facts_from_payload(payload))
    want = facts.expected_counts(payload)
    n = 0
    for k in sorted(want):
        n += 1
        if got.get(k) != want.get(k):
            on_problem("FT1 %s：事实重放=%r，报表=%r" % (k, got.get(k), want.get(k)))

    probs = facts.position_problems(facts.facts_from_payload(payload))
    for p in probs:
        on_problem("FT2 " + p)

    for f in facts.facts_from_payload(payload):
        if f.get("kind") not in facts.FACT_KINDS:
            on_problem("FT3 kind=%r 不在 FACT_KINDS 内（重放会静默漏计）"
                       % (f.get("kind"),))
    return n


def _selftest():
    bad, good = 0, 0
    facts = _load_facts()

    payload = {
        "files": [{"rel": "a.m", "kind": "script",
                   "functions": [{"name": "a", "line": 1, "complexity": 1, "calls": []}]}],
        "edges": [{"caller": "a.m:a", "callee": "a.m:b", "cross_file": False}],
        "unresolved": [{"callee": "scale", "line": 3, "file": "a.m"}],
        "heuristics": [{"file": "a.m", "line": 4, "kind": "unused",
                        "level": "low", "msg": "x", "func": "a"}],
    }
    if not facts.contract_problems(payload):
        good += 1
    else:
        bad += 1
        print("  [selftest] 干净载荷被误伤")

    f0 = facts.facts_from_payload(payload)
    if len(f0) == 5 and facts.replay_counts(f0) == facts.expected_counts(payload):
        good += 1
    else:
        bad += 1
        print("  [selftest] 事实条数/重放不对")

    if facts.replay_counts(f0[:-1]) != facts.expected_counts(payload):
        good += 1
    else:
        bad += 1
        print("  [selftest] 删一条事实未被发现")

    if facts.position_problems([{"kind": "call", "loc": {"file": "", "line": 0},
                                 "subject": "x", "payload": {}}]):
        good += 1
    else:
        bad += 1
        print("  [selftest] 无位置事实未被发现")

    # 反例必须真的落在「事实的 kind」上 —— 改 payload 里 heuristics[0].kind
    # 不会改变事实种类（issue 事实的 kind 恒为 issue），那是一个测不到的假样本。
    f1 = facts.facts_from_payload(payload) + [
        {"kind": "typo", "loc": {"file": "a.m", "line": 1},
         "subject": "x", "payload": {}}]
    if any(x.get("kind") not in facts.FACT_KINDS for x in f1):
        good += 1
    else:
        bad += 1
        print("  [selftest] kind 越界未被发现")

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
    n = audit(root, probs.append)
    for p in probs:
        print("  - " + p)
    if probs:
        print("check_facts_replay: %d 项不一致" % len(probs))
        return 1
    if n == 0:
        print("check_facts_replay: 缺输入（没有可比的计数）")
        return 2
    print("check_facts_replay: OK（%d 类计数重放一致 + 位置完备 + 种类封闭，%s 全绿）"
          % (n, ROW_SIGNATURE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
