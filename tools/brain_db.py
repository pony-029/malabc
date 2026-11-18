# -*- coding: utf-8 -*-
"""**问题记录向量库**：把失败/问题记录成可语义检索的向量，供 AI agent 驱动开发。

    python tools/brain_db.py build                 # 从 flow/failures.json 建索引
    python tools/brain_db.py add --title ... --text ...
    python tools/brain_db.py query "解析器把函数吞掉了"
    python tools/brain_db.py stats

## 为什么自己实现一个"向量库"

要的是三件事：**离线可跑、结果确定、零依赖**。
拿一个真 embedder（OpenAI/本地模型）是更好的语义质量，但它带来网络、密钥、
版本漂移三个变量 —— 而这块数据的用途是"驱动开发决策"，
**同一句话每次检索必须返回同一批记录**，否则没法复现、没法审计。

所以这里用 **哈希特征向量**（hashing trick）：

* 特征 = 英文词 + 中文 2-gram（与 `brain.py` 的分词一致）
* 维度固定 256，`md5` 决定落在哪一维（**不用内置 hash()**：它每次进程随机化，
  会让索引在不同次运行间不可比）
* 相似度 = 余弦

它等价于一个"没有训练过的 embedding 模型"，但**确定性、可解释**
（能说出"命中了哪些特征"）。接真模型时只替换 `embed()`，其余不动 ——
存储格式里留了 `dim` 与 `model` 字段，混用会被 `query` 拒绝。

## 存储

`flow/brain_vectors.json`：`{model, dim, items:{id:{vec, title, text, meta}}}`
—— 单文件、可 diff、可随仓库走；几万条以内完全够用（每条 256 个 float）。
"""
import argparse
import hashlib
import io
import json
import math
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "flow", "failures.json")
STORE = os.path.join(ROOT, "flow", "brain_vectors.json")

MODEL = "hash-256"      # 换 embedder 时改这里；混用会被拒绝
DIM = 256
STOP = set("""
的 了 是 在 和 与 或 都 也 就 而 及 对 从 到 把 被 让 给 用 一个 一种 这 那 它
the a an is are was were to of in on for and or not with by as at it this that
""".split())


def _features(text):
    """英文词（≥2 字符）+ 中文 2-gram。中文按 2-gram 是因为没有分词器时
    它比单字稳定、比整句泛化好。"""
    text = (text or "").lower()
    feats = [w for w in re.findall(r"[a-z_][a-z0-9_]{1,}", text) if w not in STOP]
    for seg in re.findall(r"[\u4e00-\u9fff]+", text):
        feats.extend(seg[i:i + 2] for i in range(max(1, len(seg) - 1)))
    return feats


def embed(text):
    """确定性 256 维向量（L2 归一化，便于余弦=点积）。"""
    v = [0.0] * DIM
    for f in _features(text):
        h = hashlib.md5(f.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % DIM
        sign = 1.0 if h[4] & 1 else -1.0
        v[idx] += sign
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def load_store():
    if not os.path.isfile(STORE):
        return {"model": MODEL, "dim": DIM, "items": {}}
    d = json.load(io.open(STORE, encoding="utf-8"))
    if d.get("model") != MODEL or d.get("dim") != DIM:
        # 换过 embedder 的旧索引不可比 —— 明确失败，不要静默混用
        raise SystemExit("索引的 model/dim 与当前不一致（%r/%r vs %r/%r）："
                         "请重建索引" % (d.get("model"), d.get("dim"), MODEL, DIM))
    return d


def save_store(d):
    d["updated"] = time.strftime("%Y-%m-%d %H:%M")
    io.open(STORE, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=1) + "\n")


def add(d, ident, title, text, meta=None):
    d["items"][ident] = {"vec": embed("%s %s" % (title, text)),
                         "title": title, "text": text,
                         "meta": meta or {}}
    return ident


def build(reg=REG):
    """从失败登记表建索引（一条记录 = 标题 + 现象 + 根因 + 规则）。"""
    d = {"model": MODEL, "dim": DIM, "items": {}}
    if os.path.isfile(reg):
        for e in json.load(io.open(reg, encoding="utf-8"))["entries"]:
            txt = " ".join(str(e.get(k) or "") for k in
                           ("symptom", "root_cause", "rule"))
            add(d, e["id"], e["title"], txt,
                {"witness": e.get("witness"), "status": e.get("status"),
                 "commit": e.get("commit", "")})
    # 顺带把"已知的开放问题"也入索引（harness 会往里写）
    extra = os.path.join(ROOT, "flow", "problems.jsonl")
    if os.path.isfile(extra):
        for ln in io.open(extra, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            add(d, r.get("id") or "P%03d" % (len(d["items"]) + 1),
                r.get("title", ""), r.get("text", ""), r.get("meta") or {})
    save_store(d)
    return len(d["items"])


def query(d, text, k=5):
    q = embed(text)
    scored = []
    for ident, it in d["items"].items():
        s = sum(a * b for a, b in zip(q, it["vec"]))
        if s > 0:
            scored.append((s, ident, it))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def main(argv=None):
    ap = argparse.ArgumentParser(description="问题记录向量库")
    ap.add_argument("cmd", choices=("build", "query", "add", "stats"))
    ap.add_argument("text", nargs="?", help="query 的检索语句")
    ap.add_argument("--id"), ap.add_argument("--title"), ap.add_argument("--body")
    ap.add_argument("-k", type=int, default=5)
    ns = ap.parse_args(argv)

    if ns.cmd == "build":
        n = build()
        print("brain_db: 索引 %d 条 -> %s（model=%s dim=%d）"
              % (n, os.path.relpath(STORE, ROOT), MODEL, DIM))
        return 0

    d = load_store()

    if ns.cmd == "stats":
        print("brain_db: %d 条（model=%s dim=%d，更新于 %s）"
              % (len(d["items"]), d["model"], d["dim"], d.get("updated", "?")))
        return 0

    if ns.cmd == "add":
        if not (ns.title and ns.body):
            print("add 需要 --title 与 --body", file=sys.stderr)
            return 2
        ident = ns.id or "P%03d" % (len(d["items"]) + 1)
        add(d, ident, ns.title, ns.body)
        save_store(d)
        print("brain_db: 已加入 %s" % ident)
        return 0

    hits = query(d, ns.text or "", ns.k)
    if not hits:
        print("（没有相关记录）")
        return 0
    print("按语义相关度 top-%d：" % len(hits))
    for s, ident, it in hits:
        print("  %.3f  %-6s %s" % (s, ident, it["title"]))
        m = it.get("meta") or {}
        if m.get("witness"):
            print("         见证 %s ｜ %s" % (m["witness"], m.get("status", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
