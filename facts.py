# -*- coding: utf-8 -*-
"""facts.py —— 把「报表」拆成**位置级事实**，并能从事实**重放**出报表的计数。

为什么需要它
============
`--json` 顶层是**预聚合的报表**（`files` / `edges` / `unresolved` / `heuristics`），
它服务「人读」与「CI 比集合」；但 IDE 要按位置查（第 12 行那个符号是什么）、
Agent 要按条件筛（confidence 低且 kind=call 的前 20 条）、runtime 要 supersede
某一条推断 —— 这三种查询都**不能**从报表直接答。

所以本模块给出**同源的第二形态**：同一次分析，既能投影成报表，也能拆成事实。
判据只有一条，但它是恒等式：

    replay_counts(facts_from_payload(p)) == expected_counts(p)

即「事实不是另算一遍，而是同一批读数的另一种排版」。任何一边多一条、
少一条，都会当场不等。

边界（本模块**不做**的事）
==========================
* 不读源码、不跑分析、不 import 引擎 —— 只吃 `--json` 的载荷。
* 不发明字段：事实的每个 payload 都来自报表里**已有**的键。
* 不给「置信度」打分：那是 `heuristics` 的 `level`，本模块只搬运。

字段契约
========
    Fact = {kind, loc:{file,line}, subject, payload}
    kind ∈ FACT_KINDS

`call` 事实的 `loc` 由 **caller 的定义位置**推出（边本身不带行号，
这是 `callrel.py` 已经写明的口径）；推不出时 `line=0` 但 `file` 必须非空。
"""
import sys

FACT_KINDS = ("file", "function", "call", "unresolved", "issue")


def _split_ref(ref):
    """`a.m:foo` -> ("a.m", "foo")；无冒号时 file 为空。"""
    if not isinstance(ref, str):
        return "", ""
    i = ref.rfind(":")
    if i < 0:
        return "", ref
    return ref[:i], ref[i + 1:]


def facts_from_payload(payload):
    """报表 -> 事实列表。顺序固定：files -> functions -> edges -> unresolved -> issues。"""
    payload = payload or {}
    facts = []
    fn_line = {}

    for f in payload.get("files") or []:
        rel = f.get("rel") or ""
        facts.append({
            "kind": "file",
            "loc": {"file": rel, "line": 0},
            "subject": rel,
            "payload": {"lang": f.get("kind") or ""},
        })
        for fn in f.get("functions") or []:
            name = fn.get("name") or ""
            line = fn.get("line") or 0
            fn_line[(rel, name)] = line
            facts.append({
                "kind": "function",
                "loc": {"file": rel, "line": line},
                "subject": name,
                "payload": {
                    "complexity": fn.get("complexity") or 0,
                    "calls": len(fn.get("calls") or []),
                },
            })

    for e in payload.get("edges") or []:
        caller = e.get("caller") or ""
        rel, name = _split_ref(caller)
        facts.append({
            "kind": "call",
            "loc": {"file": rel, "line": fn_line.get((rel, name), 0)},
            "subject": caller,
            "payload": {
                "callee": e.get("callee") or "",
                "cross_file": bool(e.get("cross_file")),
            },
        })

    for u in payload.get("unresolved") or []:
        facts.append({
            "kind": "unresolved",
            "loc": {"file": u.get("file") or "", "line": u.get("line") or 0},
            "subject": u.get("callee") or "",
            "payload": {},
        })

    for h in payload.get("heuristics") or []:
        facts.append({
            "kind": "issue",
            "loc": {"file": h.get("file") or "", "line": h.get("line") or 0},
            "subject": h.get("kind") or "",
            "payload": {
                "level": h.get("level") or "",
                "msg": h.get("msg") or "",
                "func": h.get("func") or "",
            },
        })

    return facts


def replay_counts(facts):
    """事实 -> 与报表同名同义的计数。"""
    files = set()
    n_fn = n_call = n_unres = n_issue = 0
    for f in facts or []:
        k = f.get("kind")
        if k == "file":
            files.add(f["loc"]["file"])
        elif k == "function":
            n_fn += 1
        elif k == "call":
            n_call += 1
        elif k == "unresolved":
            n_unres += 1
        elif k == "issue":
            n_issue += 1
    return {
        "files": len(files),
        "functions": n_fn,
        "edges": n_call,
        "unresolved": n_unres,
        "heuristics": n_issue,
    }


def expected_counts(payload):
    """报表自己声明的计数。"""
    payload = payload or {}
    files = payload.get("files") or []
    return {
        "files": len(files),
        "functions": sum(len(f.get("functions") or []) for f in files),
        "edges": len(payload.get("edges") or []),
        "unresolved": len(payload.get("unresolved") or []),
        "heuristics": len(payload.get("heuristics") or []),
    }


def position_problems(facts):
    """除 `file` 外，每条事实都必须落在某个文件里（否则「按位置查」无从谈起）。"""
    probs = []
    for i, f in enumerate(facts or []):
        if f.get("kind") == "file":
            continue
        if not (f.get("loc") or {}).get("file"):
            probs.append("第 %d 条 %s 事实没有 loc.file（subject=%r）"
                         % (i, f.get("kind"), f.get("subject")))
    return probs


def contract_problems(payload):
    """重放 == 报表，且每条事实都有位置。返回问题清单（空=一致）。"""
    facts = facts_from_payload(payload)
    got = replay_counts(facts)
    want = expected_counts(payload)
    probs = []
    for k in sorted(want):
        if got.get(k) != want.get(k):
            probs.append("%s: 事实重放=%r，报表=%r" % (k, got.get(k), want.get(k)))
    probs.extend(position_problems(facts))
    return probs


def _selftest():
    bad, good = 0, 0
    payload = {
        "files": [{"rel": "a.m", "kind": "script", "functions": [
            {"name": "a", "line": 1, "complexity": 2, "calls": ["b"]},
            {"name": "b", "line": 9, "complexity": 1, "calls": []},
        ]}],
        "edges": [{"caller": "a.m:a", "callee": "a.m:b", "cross_file": False}],
        "unresolved": [{"callee": "scale", "line": 3, "file": "a.m"}],
        "heuristics": [{"file": "a.m", "line": 4, "kind": "unused",
                        "level": "low", "msg": "x", "func": "a"}],
    }
    if not contract_problems(payload):
        good += 1
    else:
        bad += 1
        print("  [selftest] 干净载荷被误伤")

    facts = facts_from_payload(payload)
    if len(facts) == 6:
        good += 1
    else:
        bad += 1
        print("  [selftest] 事实条数不对：%d" % len(facts))

    if replay_counts(facts) != expected_counts(payload):
        bad += 1
        print("  [selftest] 重放与期望本应相等")
    else:
        good += 1

    dropped = facts[:-1]
    if replay_counts(dropped) != expected_counts(payload):
        good += 1
    else:
        bad += 1
        print("  [selftest] 删一条事实未被发现（判据恒真）")

    broken = [{"kind": "call", "loc": {"file": "", "line": 0}, "subject": "x", "payload": {}}]
    if position_problems(broken):
        good += 1
    else:
        bad += 1
        print("  [selftest] 无位置事实未被发现")

    return bad, good


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1
    if "--help" in argv or not argv:
        print(__doc__)
        return 0
    if "--from" in argv and "--out" in argv:
        # 把 `--json` 的载荷转成 facts 文件；**顺带自证**：重放必须等于报表。
        # 这一步是 LSP / MCP 的入口：它们读 facts，不再读 MB 级报表。
        import io
        import json
        src = argv[argv.index("--from") + 1]
        dst = argv[argv.index("--out") + 1]
        with io.open(src, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        facts = facts_from_payload(payload)
        with io.open(dst, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(facts, fh, ensure_ascii=False, indent=2)
        got = replay_counts(facts)
        want = expected_counts(payload)
        print("facts: %d 条 -> %s" % (len(facts), dst))
        print("replay: %s" % json.dumps(got, sort_keys=True))
        if got != want:
            print("replay 与报表不等：%s" % json.dumps(want, sort_keys=True))
            return 1
        return 0
    print("facts.py: 用 --from <payload.json> --out <facts.json>；或 --selftest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
