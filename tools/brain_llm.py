# -*- coding: utf-8 -*-
"""**大脑 ↔ 大模型：升级策略（escalation policy）**

    python tools/brain_llm.py ask    "给解析器加 varargin 展开"      # 本地判 + 打请求
    python tools/brain_llm.py ask    "…" --cmd "ollama run qwen"      # 真发出去
    python tools/brain_llm.py ingest reply.json                       # 校验后回写知识库
    python tools/brain_llm.py policy                                  # 打印当前策略

## 一、总体设计：三层，各管一段

    ┌─────────────────────────────────────────────────────────┐
    │ ① 大脑（本地/确定性/免费）                                │
    │   登记 · 检索 · 门禁 · 感知 · 成长 · 轮次收尾             │
    │   职责：**能自己判断的，绝不上行**                        │
    ├─────────────────────────────────────────────────────────┤
    │ ② 升级策略（本文件 escalate）                             │
    │   职责：把"拿不准"变成**可观测的信号**，而不是感觉         │
    ├─────────────────────────────────────────────────────────┤
    │ ③ 模型（外部/非确定/付费）                                │
    │   职责：只在 ② 判定 need=True 时被调用；产出必须带 witness │
    └─────────────────────────────────────────────────────────┘

## 二、"拿不准"的四个信号（都可观测、都可复算）

| 信号 | 判据 | 为什么它意味着"该问模型了" |
|---|---|---|
| **S1 无先例** | `advise` 最高分 < `MIN_SCORE` | 知识库里没有同类错 → 本地无经验可用 |
| **S2 复发** | `problems.jsonl` 里同名问题出现 ≥ `REPEAT_MIN` 次 | 有记录却仍复发 → 本地规则**没抓住真因** |
| **S3 无见证可挂** | 想登记但找不到"会变红的见证" | 说不清谁来拦 → 需要外部视角帮定位 |
| **S4 未归类** | 未映射 kind 不在 `KNOWN_KINDS` | 遇到没见过的错误形态 → 分类学本身要扩 |

四个信号**全部为假时不上行**。这条比任何"智能调度"都重要：
模型调用非确定、有成本，而绝大多数轮次本地就能判。

## 三、模型产出如何进入项目（不能直接改代码）

1. 模型回 **固定 JSON**（`findings[]`，每条含 `witness`）；
2. `ingest` 用 `os.path.exists` 校验 witness —— **不存在的直接拒收**，只落待办；
3. 通过的条目进 `flow/failures.json`，立刻受 `check_failures` 与 `check_brain_growth` 约束。

所以模型**没有写代码的权限**，它只能"提出带见证的假设"。
真正的修改仍由人或 agent 执行，并被同一套门拦住。

## 四、与 `brain_agent.py` 的分工

* `brain_agent.py`：**协议层**（pack/ask/fanout，怎么和模型说话）；
* `brain_llm.py`：**决策层**（什么时候该说话、说完怎么回写）。

两者共用同一个 `--cmd` 约定，换模型只换一条命令。

退出码：
    0 = 已判定（need 为真时会打印请求或已发出）
    1 = 拒收（模型的回复不符合 schema 或 witness 不成立）
    2 = 缺输入（知识库/参数缺失）
"""
import argparse
import io
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import brain  # noqa: E402

PROBLEMS = os.path.join(ROOT, "flow", "problems.jsonl")
REQDIR = os.path.join(ROOT, "flow", "llm-io")

#: S1 阈值：`advise` 的分数是词袋加权和，1.0 以下基本只是偶然命中一个词。
MIN_SCORE = 1.2
#: S2 阈值：同一个问题记录 >= 3 次，说明前两次的处置没生效。
REPEAT_MIN = 3
#: S4：已经被分类学覆盖的错误形态。出现新词就说明分类该扩了。
#:
#: **不能手抄**（R976 实测踩过）：我第一版手写了 10 个 kind，漏掉
#: `blockmarker`，于是 S4 恒为真 —— 升级策略**每次都触发**，
#: 等于把"拿不准才问模型"退化成"每次都问"。手抄的分类表必然与
#: `mir.py::_KIND_RULES` 不同步，所以这里**直接从源码读**。
_EXTRA_KINDS = ("other", "nested", "sideeffect", "blockmarker", "unmapped")


def _known_kinds():
    """已知 kind = `_KIND_RULES` 的表项 ∪ `_unmapped_kind` 里的返回字面量。

    两个来源缺一不可（R976 第二次踩）：`call2` / `idx2` 不是规则表里的，
    而是分类函数**在兜底分支里返回**的 —— 只读表会漏掉它们，
    S4 照样恒真。
    """
    kinds = set(_EXTRA_KINDS)
    try:
        sys.path.insert(0, os.path.join(ROOT, "translate"))
        import mir as _mir
        for _name, _fn in getattr(_mir, "_KIND_RULES", ()):
            kinds.add(_name)
    except Exception:                      # noqa: BLE001
        pass
    try:
        _src = io.open(os.path.join(ROOT, "translate", "mir.py"),
                       encoding="utf-8", errors="replace").read()
        _i = _src.find("def _unmapped_kind")
        if _i > 0:
            _body = _src[_i:_i + 4000]
            for _m in re.finditer(r'return\s+"([a-z0-9_]+)"', _body):
                kinds.add(_m.group(1))
    except (IOError, OSError):
        pass
    return tuple(sorted(kinds))


KNOWN_KINDS = _known_kinds()


def _mir_produces(kind):
    """这个 kind 是不是 `mir.py` **自己会产出**的？

    判据：源码里存在 `"<kind>"` 这个字面量。
    比维护一张"已知 kind 清单"可靠 —— 清单一定会漏（R976 连漏两次：
    先漏 `blockmarker`，再漏 `call2`/`idx2`），而源码不会。
    """
    global _MIR_SRC
    try:
        _MIR_SRC
    except NameError:
        try:
            _MIR_SRC = io.open(os.path.join(ROOT, "translate", "mir.py"),
                               encoding="utf-8", errors="replace").read()
        except (IOError, OSError):
            _MIR_SRC = ""
    return ('"%s"' % kind) in _MIR_SRC or ("'%s'" % kind) in _MIR_SRC


def _problems():
    if not os.path.isfile(PROBLEMS):
        return []
    out = []
    for ln in io.open(PROBLEMS, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def escalate(query, extra_signals=None, problems=None, entries=None, kinds=None):
    """判定"要不要上行"。返回 dict（need / reasons / signals / payload）。

    **纯函数式判定**：不读网络、不改文件，给同样输入必得同样输出 ——
    这样它才能被自证、被复算、被审计。

    三个数据源可注入（`problems` / `entries` / `kinds`），只为止自证用：
    自证要能构造"必然触发"与"必然不触发"两种样本，而读真实文件做不到。
    """
    hits = brain.advise(query, k=5, log=False)
    top = max([s for s, _e in hits], default=0.0)

    # S1 无先例
    s1 = top < MIN_SCORE

    # S2 复发：同名问题在 problems.jsonl 里出现多次
    rep = {}
    for p in (problems if problems is not None else _problems()):
        t = (p.get("title") or "").strip()
        if t:
            rep[t] = rep.get(t, 0) + 1
    worst = max(rep.values()) if rep else 0
    s2 = worst >= REPEAT_MIN

    # S3 无见证可挂：库里存在"想记却记不住"的信号 —— 用 open 条目近似
    if entries is None:
        entries = brain.load()["entries"]
    open_items = [e for e in entries if e.get("status") == "open"]
    s3 = len(open_items) > 0

    # S4 未归类：最近一次未映射统计里出现已知集合之外的 kind
    if kinds is None:
        un = {}
        p = os.path.join(ROOT, "flow", "unmapped.json")
        if os.path.isfile(p):
            try:
                un = json.load(io.open(p, encoding="utf-8")).get("kinds") or {}
            except ValueError:
                un = {}
    else:
        un = kinds
    unknown = [k for k in un if not _mir_produces(k)]
    s4 = bool(unknown)

    sig = {"S1_top_score": round(top, 2), "S1_no_precedent": s1,
           "S2_repeat_max": worst, "S2_recurs": s2,
           "S3_open_items": len(open_items), "S3_no_witness": s3,
           "S4_unknown_kinds": unknown, "S4_unclassified": s4}
    if extra_signals:
        sig.update(extra_signals)

    reasons = []
    if s1:
        reasons.append("无先例：知识库最高分 %.2f < %.2f，本地没有同类经验"
                       % (top, MIN_SCORE))
    if s2:
        reasons.append("复发：同名问题已记 %d 次（阈值 %d），本地规则没抓住真因"
                       % (worst, REPEAT_MIN))
    if s3:
        reasons.append("有 %d 条未闭合条目 —— 想登记却挂不上见证" % len(open_items))
    if s4:
        reasons.append("未归类错误形态：%r（分类学要扩）" % (unknown[:4],))

    payload = None
    if reasons:
        payload = {
            "query": query,
            "why_escalated": reasons,
            "local_evidence": [{"id": e["id"], "title": e["title"],
                                "rule": e.get("rule", ""),
                                "witness": e.get("witness", "")}
                               for _s, e in hits[:3]],
            "constraints": [
                "每条 finding 必须给出**仓库里真实存在**的 witness 路径",
                "不要提'加测试/提高覆盖率'这类没有落点的话",
                "如果这是本仓已有的设计约束（如静态池、C 不能重载），请明确指出而非当作缺陷",
            ],
            "reply_schema": {"findings": [{
                "title": "", "symptom": "", "root_cause": "",
                "rule": "", "witness": "", "severity": "high|medium|low"}]},
        }
    return {"need": bool(reasons), "reasons": reasons, "signals": sig,
            "payload": payload}


#: **ANE 第五条要求的极简协议**（R996）。
#:
#: 原文：「上下文必须压缩至极简，仅传递**特征向量与错误码**，以极低 Token
#: 消耗换取高级智能辅助。」
#:
#: 改造前每次请求 1434 字节的自然语言（含解释、约束、JSON schema 全文）；
#: 现在请求体只含四行：错误码 / 特征向量 / 任务短语 / 命中条目 id。
#: **约束与回复 schema 不随请求变化，因此移到 `SYSTEM.md` 一次性下发** ——
#: 这才是"极简"的正解：不是删掉约束，而是让不变的东西不重复发送。
ANE5_SYSTEM = """# 系统提示（一次性配置，不随请求重复发送）

你在协助一个 MATLAB→C 编译器做**问题归因**。请求体是 ANE-5 极简格式：

    q=  任务短语（<60 字）
    E=  触发升级的错误码，逗号分隔：S1 无先例 / S2 复发 / S3 无见证 / S4 未归类
    V=  特征向量（竖线分隔）：S1 得分 | S2 重复次数 | S3 未闭条目数 | S4 未知类别数
    K=  命中的历史条目 id（可空），复用它们，别重复发明

只输出 JSON：
{"findings":[{"title":"","symptom":"","root_cause":"","rule":"","witness":"","severity":"high|medium|low"}]}

硬约束：
1. 每条 finding 的 `witness` 必须是仓库内**真实存在**的路径，否则会被拒收；
2. 不要提"加测试/提高覆盖率"这类没有落点的话；
3. 如果是本仓既有的设计约束（静态池、C 不能重载、C 无字符串类型），
   请明确指出而非当作缺陷。
"""


def _render_ane5(dec):
    """把判定结果压成 ANE-5 极简请求体（目标 < 200 字节）。

    只保留**模型无法自己算出**的东西：错误码、特征向量、任务短语、命中 id。
    约束与 schema 在 `SYSTEM.md`，不重复发送。
    """
    s = dec["signals"]
    codes = []
    if s["S1_no_precedent"]:
        codes.append("S1")
    if s["S2_recurs"]:
        codes.append("S2")
    if s["S3_no_witness"]:
        codes.append("S3")
    if s["S4_unclassified"]:
        codes.append("S4")
    vec = "%s|%d|%d|%d" % (s["S1_top_score"], s["S2_repeat_max"],
                           s["S3_open_items"], len(s["S4_unknown_kinds"]))
    p = dec["payload"]
    q = (p.get("query") or "").replace("\n", " ")[:60]
    ids = ",".join(e["id"] for e in (p.get("local_evidence") or [])[:3])
    return "ANE5\nq=%s\nE=%s\nV=%s\nK=%s\n" % (q, ",".join(codes), vec, ids)


def _render(payload):
    """把 payload 渲染成给模型看的纯文本。"""
    lines = ["你在协助一个 MATLAB→C 编译器项目做**问题归因**。",
             "任务：%s" % payload["query"], "",
             "为什么这次要问你（本地大脑判不出来）："]
    lines += ["- " + r for r in payload["why_escalated"]]
    if payload["local_evidence"]:
        lines += ["", "本地已有的相近经验（能复用就复用，别重复发明）："]
        for e in payload["local_evidence"]:
            lines.append("- [%s] %s" % (e["id"], e["title"]))
            lines.append("    规则：%s" % e["rule"])
            lines.append("    见证：%s" % e["witness"])
    lines += ["", "约束："] + ["- " + c for c in payload["constraints"]]
    lines += ["", "只输出 JSON：",
              json.dumps(payload["reply_schema"], ensure_ascii=False, indent=2)]
    return "\n".join(lines)


def ask(query, cmds, timeout=300):
    """先本地判定；need 为真才发（或打印）请求。"""
    dec = escalate(query)
    print("[policy] 需要上行：%s" % ("是" if dec["need"] else "否"))
    print("[policy] 信号：S1=%.2f S2=%d S3=%d S4=%s"
          % (dec["signals"]["S1_top_score"], dec["signals"]["S2_repeat_max"],
             dec["signals"]["S3_open_items"],
             dec["signals"]["S4_unknown_kinds"] or "无"))
    for r in dec["reasons"]:
        print("[policy]   - " + r)
    if not dec["need"]:
        print("[policy] 本地就能判，不消耗模型调用")
        return 0, dec

    # **ANE 第五条**：请求体只含错误码 + 特征向量（< 200 字节）；
    # 不变的约束与 schema 落在 SYSTEM.md，一次性下发、不重复计费。
    prompt = _render_ane5(dec)
    os.makedirs(REQDIR, exist_ok=True)
    sys_md = os.path.join(REQDIR, "SYSTEM.md")
    if not os.path.isfile(sys_md):
        io.open(sys_md, "w", encoding="utf-8", newline="\n").write(ANE5_SYSTEM)
        print("[policy] 系统提示 -> %s（一次性）" % os.path.relpath(sys_md, ROOT))
    _n = len(prompt.encode("utf-8"))
    if _n > 200:
        # 只警告不阻断：压缩不到位是**协议问题**，不该让本次请求失败
        print("[policy] ⚠ 请求体 %d 字节 > 200（ANE 第五条目标）" % _n)
    # **文件名要唯一**（R976）：只到秒的时间戳会让连续两次 ask 互相覆盖
    # （实测两次调用落在同一秒，第二个请求把第一个冲掉了）。
    stamp = "%s-%d" % (time.strftime("%Y%m%d-%H%M%S"), os.getpid())
    ipath = os.path.join(REQDIR, "req-%s.txt" % stamp)
    io.open(ipath, "w", encoding="utf-8", newline="\n").write(prompt)
    print("[policy] 请求 -> %s（%d 字节）" % (os.path.relpath(ipath, ROOT),
                                             len(prompt)))
    if not cmds:
        print("[policy] 未给 --cmd，只生成请求（把上面那个文件喂给任意模型即可）")
        return 0, dec

    import subprocess
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, shell=True, input=prompt.encode("utf-8"),
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=timeout, cwd=ROOT)
            raw = r.stdout.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            raw = "<超时>"
        rpath = os.path.join(REQDIR, "reply-%s.txt" % stamp)
        io.open(rpath, "w", encoding="utf-8", newline="\n").write(raw)
        print("[policy] 回复 -> %s（%d 字节，下一步用 ingest 验收）"
              % (os.path.relpath(rpath, ROOT), len(raw)))
    return 0, dec


def ingest(path):
    """校验并回写。**witness 不成立一律拒收**（模型没有写库的权限）。"""
    import brain_agent

    raw = io.open(path, encoding="utf-8", errors="replace").read()
    data = brain_agent._parse(raw)
    if data is None:
        print("[ingest] 拒收：回复里找不到 JSON（要求模型只输出 JSON）")
        return 1
    findings = data.get("findings") or []
    if not isinstance(findings, list):
        print("[ingest] 拒收：findings 必须是数组")
        return 1

    ok_n = pend_n = 0
    for f in findings:
        w = (f.get("witness") or "").strip()
        if w and os.path.exists(os.path.join(ROOT, w)):
            e, _err = brain.record(f.get("title", ""), f.get("symptom", ""),
                                   f.get("root_cause", ""), f.get("rule", ""),
                                   w, status="fixed", commit="llm")
            if e:
                ok_n += 1
                continue
        io.open(PROBLEMS, "a", encoding="utf-8", newline="\n").write(
            json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "title": f.get("title", ""),
                        "text": "%s / %s" % (f.get("symptom", ""),
                                             f.get("root_cause", "")),
                        "meta": {"from": "llm", "witness": w}},
                       ensure_ascii=False) + "\n")
        pend_n += 1
    if ok_n:
        brain.growth()
    print("[ingest] 入库 %d 条（带真见证）；拒收为待办 %d 条" % (ok_n, pend_n))
    return 0


def _selftest():
    """**双向自证**：每个信号既要能"必然触发"，也要有"必然不触发"的基线。

    只验"会触发"是不够的 —— 一个恒真的策略和没有策略在行为上一样
    （R976 就踩过：S4 恒真，导致每次都"拿不准"）。
    """
    bad = good = 0
    _hit = "给报告加一个统计列"          # 知识库里有先例（S1 应为假）
    _miss = "zzz_qwerty_不存在的词组"     # 无先例（S1 应为真）
    _clean_entries = [{"id": "X1", "title": "t", "rule": "r",
                       "witness": "tools/brain.py", "status": "fixed"}]

    # ① 基线：四个信号全假 -> 不上行
    d = escalate(_hit, problems=[], entries=_clean_entries, kinds={})
    if not d["need"] and not any(d["signals"][k] for k in
                                 ("S1_no_precedent", "S2_recurs",
                                  "S3_no_witness", "S4_unclassified")):
        good += 1
    else:
        bad += 1
        print("  [selftest] 基线（全假）却判了上行：%r" % (d["reasons"],))

    # ② S1：无先例必须触发
    d = escalate(_miss, problems=[], entries=_clean_entries, kinds={})
    if d["need"] and d["signals"]["S1_no_precedent"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] S1 无先例没触发")

    # ③ S2：同名问题 3 次必须触发
    d = escalate(_hit, problems=[{"title": "同名"}] * REPEAT_MIN,
                 entries=_clean_entries, kinds={})
    if d["need"] and d["signals"]["S2_recurs"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] S2 复发没触发")

    # ④ S3：有未闭条目必须触发
    _open = [{"id": "X2", "title": "未闭", "rule": "r",
              "witness": "tools/brain.py", "status": "open"}]
    d = escalate(_hit, problems=[], entries=_open, kinds={})
    if d["need"] and d["signals"]["S3_no_witness"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] S3 无见证没触发")

    # ⑤ S4：未知 kind 必须触发；已知 kind 必须**不**触发（这是 R976 的教训）
    d = escalate(_hit, problems=[], entries=_clean_entries,
                 kinds={"made_up_kind": 1})
    ok1 = d["need"] and d["signals"]["S4_unclassified"]
    d2 = escalate(_hit, problems=[], entries=_clean_entries,
                  kinds={"cell": 10, "call2": 3, "other": 5})
    ok2 = not d2["signals"]["S4_unclassified"]
    if ok1 and ok2:
        good += 1
    else:
        bad += 1
        print("  [selftest] S4 双向不成立（未知 %s / 已知 %s）" % (ok1, ok2))

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    # `--selftest` 要在 argparse 之前拦：它以下划线开头，放进 choices 会
    # 被当成选项而不是子命令（本仓 runner 认的正是 `--selftest` 这个拼写）。
    if "--selftest" in sys.argv:
        return _selftest()

    ap = argparse.ArgumentParser(description="大脑 ↔ 大模型：升级策略")
    ap.add_argument("cmd", choices=("ask", "ingest", "policy"))
    ap.add_argument("text", nargs="?")
    ap.add_argument("--cmd", action="append", dest="cmds", metavar="SHELL")
    ns = ap.parse_args(argv)

    if ns.cmd == "policy":
        print("升级策略（四信号，全假则不上行）：")
        print("  S1 无先例    advise 最高分 < %.2f" % MIN_SCORE)
        print("  S2 复发      同名问题在 problems.jsonl 出现 >= %d 次" % REPEAT_MIN)
        print("  S3 无见证    存在未闭合条目（想记却挂不上见证）")
        print("  S4 未归类    unmapped kind 不在 %r" % (KNOWN_KINDS,))
        return 0

    if ns.cmd == "ingest":
        if not ns.text:
            print("需要回复文件路径", file=sys.stderr)
            return 2
        return ingest(ns.text)

    if not ns.text:
        print("需要任务描述", file=sys.stderr)
        return 2
    rc, _dec = ask(ns.text, ns.cmds)
    return rc


if __name__ == "__main__":
    sys.exit(main())
