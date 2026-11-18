# -*- coding: utf-8 -*-
"""**小脑 ↔ 大模型**：把知识库打包成 agent 可吃的上下文，并把回答收回库里。

    python tools/brain_agent.py pack "给解析器加 elseif 支持"      # 打印上下文包
    python tools/brain_agent.py ask  "…" --cmd "ollama run qwen"   # 真的发出去
    python tools/brain_agent.py ingest reply.json                  # 把回答入库
    python tools/brain_agent.py fanout "…" --cmd "a" --cmd "b"      # 多 agent 对照

## 为什么是"协议"而不是"接一个模型"

接死一个厂商 = 把自己绑在它的接口、密钥、限流上。这里反过来：
**只定义两端的格式**，中间那条命令由用户给：

    brain_agent ask --cmd "<任意命令，从 stdin 读 prompt、向 stdout 写回复>"

于是 `ollama run qwen`、`claude -p`、`curl` 包一层、公司的内部 CLI —— 同一份代码
都能用；换模型只换那一条命令，**不改一行 Python**。

## 三个往返（这才是"小脑"该干的）

1. **pack**：任务 + 历史同类错（规则/见证）+ 待查问题 → 一段结构化上下文。
   重点是**给见证**：让 agent 知道"这个问题以前是被哪条判据拦住的"，
   否则它只能凭空建议。
2. **ask**：把 pack 的结果喂给任意模型，要求它回**固定 JSON**。
3. **ingest**：校验回复 → 入库。**这一步才是"自我进化"**：
   模型提的发现变成登记条目，下次 `advise` 就能检索到它。

## 自我进化的边界（重要）

`ingest` **只接受带 witness 的条目**，而且 witness 必须指向仓库里真实存在的文件。
模型最爱给的是一句漂亮话（"建议增加测试覆盖"），那东西进了库只会稀释知识。
所以：没有见证的发现 → 落到 `flow/problems.jsonl` 当**待办**，不进知识库。

## 多 agent 对照（`fanout`）

同一个 prompt 发给 N 条命令，把各自回复里**互不重叠**的发现并排列出 ——
分歧处往往才是真正值得人看的地方。
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

PROBLEMS = os.path.join(ROOT, "flow", "problems.jsonl")
REQDIR = os.path.join(ROOT, "flow", "agent-io")

#: 要求模型返回的格式。**固定成 JSON**，否则 ingest 没法自动化。
REPLY_SCHEMA = {
    "findings": [{
        "title": "一句话标题",
        "symptom": "看到什么现象",
        "root_cause": "真正的原因",
        "rule": "下次怎么避免（一句可执行的话）",
        "witness": "tools/check_xxx.py 或 tests/test_xxx.py（必须真实存在）",
        "severity": "high|medium|low",
    }],
    "notes": "可选：不适合入库的观察",
}


def pack(task, k=6):
    """打包上下文：任务 + 历史同类错 + 回复格式。"""
    import brain

    hits = brain.advise(task, k=k, log=False)
    d = brain.load()
    open_items = [e for e in d["entries"] if e.get("status") != "fixed"]
    return {
        "task": task,
        "repo": os.path.basename(ROOT),
        "constraints": [
            "只提出**能落到见证**的发现：witness 必须是仓库里真实存在的文件路径",
            "不要建议'加测试'这类没有具体落点的话",
            "每条 rule 要能在下次重犯时被某条判据拦住",
        ],
        "past_same_class": [{
            "id": e["id"], "title": e["title"],
            "symptom": e["symptom"], "root_cause": e["root_cause"],
            "rule": e["rule"], "witness": e["witness"],
        } for _s, e in hits],
        "open_items": [{"id": e["id"], "title": e["title"]} for e in open_items],
        "reply_schema": REPLY_SCHEMA,
    }


def render_prompt(ctx):
    """把上下文渲染成给模型的纯文本（模型不看 JSON 也能做事）。"""
    lines = ["你在协助一个 MATLAB→C 编译器项目做**问题归因**。",
             "任务：%s" % ctx["task"], "", "约束："]
    lines += ["- " + c for c in ctx["constraints"]]
    if ctx["past_same_class"]:
        lines += ["", "历史上同类错误（优先复用它们的规则，不要重复发明）："]
        for e in ctx["past_same_class"]:
            lines.append("- [%s] %s" % (e["id"], e["title"]))
            lines.append("    现象：%s" % e["symptom"])
            lines.append("    根因：%s" % e["root_cause"])
            lines.append("    规则：%s" % e["rule"])
            lines.append("    见证：%s" % e["witness"])
    if ctx["open_items"]:
        lines += ["", "尚未闭合的条目："]
        lines += ["- [%s] %s" % (e["id"], e["title"]) for e in ctx["open_items"]]
    lines += ["", "只输出 JSON，结构如下：",
              json.dumps(ctx["reply_schema"], ensure_ascii=False, indent=2)]
    return "\n".join(lines)


def ask(task, cmds, timeout=300):
    """把 prompt 发给每条命令，返回 [(cmd, 原文, 解析结果或 None)]。"""
    ctx = pack(task)
    prompt = render_prompt(ctx)
    os.makedirs(REQDIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    ipath = os.path.join(REQDIR, "req-%s.txt" % stamp)
    io.open(ipath, "w", encoding="utf-8", newline="\n").write(prompt)

    out = []
    for cmd in cmds:
        try:
            # 用 `input=` 喂 prompt：它同时把 stdin 设成 PIPE（不会继承父进程的
            # stdin —— 否则某些 CLI 会等键盘输入而挂死，S1 明确要求）。
            r = subprocess.run(cmd, shell=True, input=prompt.encode("utf-8"),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=timeout, cwd=ROOT)
            raw = r.stdout.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            raw = "<超时>"
        out.append((cmd, raw, _parse(raw)))
    return ipath, out


def _parse(raw):
    """从模型回复里抠出 JSON（前后可能包着解释文字）。"""
    i, j = raw.find("{"), raw.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(raw[i:j + 1])
    except ValueError:
        return None


def ingest(path):
    """把 agent 回复入库。**只收带合法 witness 的条目**，其余落待办。"""
    import brain

    raw = io.open(path, encoding="utf-8", errors="replace").read()
    data = _parse(raw)
    if data is None:
        return 2, "回复里找不到 JSON（要求模型只输出 JSON）"
    findings = data.get("findings") or []
    if not isinstance(findings, list):
        return 2, "findings 必须是数组"

    accepted, pending = 0, 0
    for f in findings:
        w = (f.get("witness") or "").strip()
        ok = bool(w) and os.path.exists(os.path.join(ROOT, w))
        if ok:
            e, err = brain.record(f.get("title", ""), f.get("symptom", ""),
                                  f.get("root_cause", ""), f.get("rule", ""),
                                  w, status="fixed", commit="agent")
            if e:
                accepted += 1
                continue
        # 没有见证 → 待办，不进知识库（模型最爱给漂亮话，那会稀释知识）
        io.open(PROBLEMS, "a", encoding="utf-8", newline="\n").write(
            json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "title": f.get("title", ""),
                        "text": "%s / %s" % (f.get("symptom", ""),
                                             f.get("root_cause", "")),
                        "meta": {"from": "agent", "witness": w,
                                 "severity": f.get("severity", "")}},
                       ensure_ascii=False) + "\n")
        pending += 1
    if accepted:
        brain.growth()
    return 0, ("入库 %d 条（带见证）；待办 %d 条（无见证，已落 "
               "flow/problems.jsonl）" % (accepted, pending))


def main(argv=None):
    ap = argparse.ArgumentParser(description="小脑 ↔ 大模型：打包/发问/收回")
    ap.add_argument("cmd", choices=("pack", "ask", "ingest", "fanout"))
    ap.add_argument("text", nargs="?", help="任务描述 / 待 ingest 的文件")
    ap.add_argument("--cmd", action="append", dest="cmds", metavar="SHELL",
                    help="一条从 stdin 读 prompt、向 stdout 写回复的命令（可重复）")
    ap.add_argument("-k", type=int, default=6)
    ns = ap.parse_args(argv)

    if ns.cmd == "pack":
        ctx = pack(ns.text or "", ns.k)
        print(render_prompt(ctx))
        print("\n--- 上下文（JSON） ---")
        print(json.dumps(ctx, ensure_ascii=False, indent=2)[:1200])
        return 0

    if ns.cmd == "ingest":
        if not ns.text:
            print("需要回复文件路径", file=sys.stderr)
            return 2
        rc, msg = ingest(ns.text)
        print("[agent] " + msg)
        return rc

    if not ns.cmds:
        print("需要 --cmd（未给则只生成 prompt，不发问）")
        ipath, _ = ask(ns.text or "", [])
        print("prompt 已写：%s" % ipath)
        return 0

    ipath, results = ask(ns.text or "", ns.cmds)
    print("[agent] prompt -> %s" % ipath)
    for cmd, raw, parsed in results:
        n = len((parsed or {}).get("findings") or [])
        print("  %-40s %s（%d 条发现）"
              % (cmd[:40], "JSON OK" if parsed else "回复不是 JSON", n))

    if ns.cmd == "fanout" and len(results) > 1:
        # 多 agent 对照：并排列出各自**独有**的发现 —— 分歧处才值得人看
        sets = [set((f.get("title") or "") for f in (p or {}).get("findings") or [])
                for _c, _r, p in results]
        print("\n[fanout] 各 agent 独有的发现：")
        for i, (_c, _r, _p) in enumerate(results):
            others = set().union(*[s for j, s in enumerate(sets) if j != i]) if len(sets) > 1 else set()
            only = sets[i] - others
            print("  #%d 独有 %d 条：%r" % (i + 1, len(only), sorted(only)[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
