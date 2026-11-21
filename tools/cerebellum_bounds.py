# -*- coding: utf-8 -*-
"""**小脑硬边界机检**（ANE v0.9.0 第四章 4.4）。

    python tools/cerebellum_bounds.py
    python tools/cerebellum_bounds.py --json
    python tools/cerebellum_bounds.py --selftest

## 规范要求的三条硬边界

| 硬边界 | 规范原文要求 | 可机检的吗 |
|---|---|---|
| 离线可用 | 断网时靠本地规则完成 **≥80%** 的异常处理 | ✅ 能量：喂一批真实异常看多少不需要升级 |
| 可生长 | 新增能力只能通过**追加规则**，不能改判定 | ✅ 能量：比对规则集合只增不减 |
| 无推测 | 未命中时**必须**抛 UnknownSignal，禁止猜 | ✅ 已在 `ntp.py` 强制 |

前两条本工具负责，第三条由 `tools/ntp.py` 负责（它强制 `signal_type`
只能是 UNKNOWN/S1..S4 且 `tried_rules` 不能为空）。

## 离线可用率怎么量（口径写死）

对每个**真实存在的未映射类别**（来自 `operators.py` 与解析器能产出的 kind
全集，而不是我手编的清单）构造一次咨询：

* 若 `escalate()` 判定**不需升级** → 计为「小脑自决」；
* 若判定需升级 → 计为「必须上行」。

    离线可用率 = 小脑自决数 / 总咨询数

**为什么用真实 kind 而不是自造问题**：自造的问题一定会挑自己答得上来的。
用产出方的全集，才可能包含自己答不上来的。

## 可生长怎么量

比对 `translate/operators.py` 的算子 id 集合 与
`translate/hir_ops.py` 的映射 key 集合：与 `flow/cerebellum-rules-baseline.json`
里记录的基线相比，**只允许新增，不允许减少**。

减少意味着「一条旧规则被删了」——那可能是重构，也可能是误删；无论哪种，
都必须由人来确认并更新基线，而不是悄悄消失。

退出码：0=全部满足 1=自证失败或边界不满足 2=缺输入
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "translate"))

BASELINE = os.path.join(ROOT, "flow", "cerebellum-rules-baseline.json")

#: 规范要求的离线可用下限
OFFLINE_FLOOR = 0.80


def feature_distribution(mir_path):
    """**特征分布 + 口径对照**（R1070）。

    R1069 那次错误结论的根源是：我拿「含 >=1 项特征」的 386 条，
    去比「S5 判定 >=2 项」的实现，得出「漏判 3 倍」的假象。
    两个口径都真实，错在它们不是同一个东西的测量值。

    所以本函数**同时输出两个口径**，并在同一屏里写明 S5 用的是哪个，
    下次再想比较时，数字和口径就在一起。
    """
    if not mir_path or not os.path.isfile(mir_path):
        return None
    import re as _re
    cases = _sample_real_cases(mir_path, 100000)

    def feats(d):
        f = []
        if "{" in d:
            f.append("cell{}")
        if _re.search(r"\bend\b", d):
            f.append("end")
        if _re.search(r"\[[^\]]*;", d):
            f.append("拼接")
        dep = mx = 0
        for ch in d:
            if ch == "(":
                dep += 1
                mx = max(mx, dep)
            elif ch == ")":
                dep = max(0, dep - 1)
        if mx >= 2:
            f.append("嵌套>=2")
        return f

    n = len(cases)
    ge1 = sum(1 for _k, d in cases if len(feats(d)) >= 1)
    ge2 = sum(1 for _k, d in cases if len(feats(d)) >= 2)
    from collections import Counter
    kinds = Counter(k for k, d in cases if len(feats(d)) >= 2)
    return {"total": n, "ge1": ge1, "ge2": ge2,
            "ge1_rate": round(100.0 * ge1 / n, 1) if n else 0,
            "ge2_rate": round(100.0 * ge2 / n, 1) if n else 0,
            "kinds": kinds.most_common(6),
            "s5_uses": "ge2"}


def _real_kinds():
    """**产出方全集**：解析器实际会产出的未映射类别。

    不从文档抄，而是问产出方 —— `mir.py` 的 `_emit_unmapped` 里出现的字面量。
    抄清单必漏，这是本项目反复踩过的坑。
    """
    p = os.path.join(ROOT, "translate", "mir.py")
    s = io.open(p, encoding="utf-8", errors="replace").read()
    import re
    kinds = set()
    # 实际写法是 `unmapped_kinds[kind] += 1`，kind 由 _classify 决定；
    # 这里抓 `_unmapped` 分类函数里返回的字面量（形如 return "cell"）。
    for m in re.finditer(r'["\']([a-z][a-z0-9_\-]{1,24})["\']\s*#'
                         r'|return\s+["\']([a-z][a-z0-9_\-]{1,24})["\']', s):
        for g in m.groups():
            if g:
                kinds.add(g)
    # 再补：operators.py 的 kind 字段（已知类别全集的一部分）
    try:
        import operators as O
        for op in O.OPERATORS:
            if op.get("kind"):
                kinds.add(str(op["kind"]))
    except Exception:                          # noqa: BLE001
        # 故意忽略：见上方 try 的用途说明（AN4 要求不写裸 pass）
        ignored = True          # noqa: F841
    kinds.discard("func")
    # 补：hir_ops 的 value（OP-*）也应算可自决的已知类别
    return sorted(kinds)


def _sample_real_cases(mir_path, limit=60):
    """从**真实 MIR** 里抽未映射条目（原文 + why 类别）。

    R1059：上一轮是按 kind 自己造问题，于是 15/15 全自决、100% —— 那个数字
    不可信，因为自造的问题一定挑自己答得上来的。真实条目长得多、也脏得多
    （如 `x = x(~ isnan (x));`），才是该问的东西。
    """
    s = io.open(mir_path, encoding="utf-8", errors="replace").read()
    out = []
    why = None
    for ln in s.splitlines():
        if ln.startswith("# why:"):
            why = ln[6:].strip()
            continue
        if ln.startswith("unmapped:"):
            desc = ln[9:].strip()
            if desc:
                out.append((why or "other", desc))
            why = None
    # 均匀抽样，避免只取到文件开头（那里往往是同一类）
    if len(out) > limit:
        step = len(out) / float(limit)
        out = [out[int(i * step)] for i in range(limit)]
    return out


def measure_offline(mir_path=None, limit=60):
    """统计小脑自决比例。

    * 给了 `mir_path` -> 用**真实未映射条目**（推荐，见 R1059 的教训）；
    * 没给 -> 退化为按 kind 构造问题（会偏乐观，返回值里标 `basis`）。
    """
    import brain_llm as B
    if mir_path and os.path.isfile(mir_path):
        cases = _sample_real_cases(mir_path, limit)
        basis = "real"
    else:
        cases = [("kind", "解析出现未映射类别 %s，是否需要外部裁决？" % k)
                 for k in _real_kinds()]
        basis = "synthetic"
    if not cases:
        return None
    decidable, escalate = [], []
    for kind, desc in cases:
        query = "未映射（%s）：%s" % (kind, desc)
        try:
            dec = B.escalate(query)
        except Exception as e:                 # noqa: BLE001
            escalate.append((kind, "escalate 抛错：%s" % type(e).__name__))
            continue
        # **不能只看 escalate 字段**（R1059）：brain_llm.escalate 目前返回的
        # `escalate` 是 None（不是布尔），而 `reasons` 里可能已经明确写着
        # "复发：同名问题已记 7 次"。用 bool(None)=False 判"自决"会把
        # **该升级的当成不需要升级**——那会让离线率虚高到 100%。
        # 所以：任一条成立就算需要上行。
        if not isinstance(dec, dict):
            need = True
        else:
            need = bool(dec.get("escalate")) or bool(dec.get("reasons"))
        (escalate if need else decidable).append(
            (kind, (dec.get("why") or "；".join(dec.get("reasons") or []))
             if need else desc))
    total = len(cases)
    rate = float(len(decidable)) / total if total else 0.0
    return {"basis": basis, "total": total,
            "decidable": decidable, "escalate": escalate,
            "rate": round(rate, 4), "floor": OFFLINE_FLOOR,
            "pass": rate >= OFFLINE_FLOOR}


def measure_calibration(path):
    """用**人工判定过正确答案**的标定集检验判据。

    这是 R1062 的核心：上一轮 0% 与 100% 都不可信，因为它们只说明判据
    偏向一边，没有正确答案可比。只有标定集能回答「判据判对了没有」。
    """
    if not os.path.isfile(path):
        return None
    d = json.load(io.open(path, encoding="utf-8"))
    cases = d.get("cases") or []
    if not cases:
        return None
    import brain_llm as B
    rows = []
    hit = 0
    for c in cases:
        query = "未映射（%s）：%s" % (c.get("kind", "other"), c.get("text", ""))
        try:
            dec = B.escalate(query)
            need = (bool(dec.get("escalate")) or bool(dec.get("reasons"))
                    if isinstance(dec, dict) else True)
        except Exception:                      # noqa: BLE001
            need = True
        actual = "up" if need else "self"
        ok = actual == c.get("expect")
        if ok:
            hit += 1
        rows.append({"text": c.get("text", "")[:52], "expect": c.get("expect"),
                     "actual": actual, "ok": ok,
                     "why": c.get("why", "")[:40]})
    return {"path": path, "total": len(cases), "hit": hit,
            "rate": round(float(hit) / len(cases), 4), "rows": rows}


def _rule_sets():
    """当前规则集合：算子 id 与 hir 映射 key。"""
    import hir_ops
    import operators as O
    ops = set(op["id"] for op in O.OPERATORS)
    hir = set()
    for name in dir(hir_ops):
        v = getattr(hir_ops, name)
        if isinstance(v, dict):
            hir |= set(v.keys())
    return {"operator_ids": sorted(ops), "hir_keys": sorted(hir)}


def check_growable(baseline_path=BASELINE, write=False):
    """规则集合只允许新增。返回 dict。"""
    cur = _rule_sets()
    if not os.path.isfile(baseline_path):
        if write:
            io.open(baseline_path, "w", encoding="utf-8", newline="\n").write(
                json.dumps(cur, ensure_ascii=False, indent=1) + "\n")
            return {"ok": True, "created": True, "shrunk": []}
        return {"ok": False, "missing_baseline": True, "shrunk": []}
    try:
        base = json.load(io.open(baseline_path, encoding="utf-8"))
    except (IOError, OSError, ValueError) as e:
        return {"ok": False, "read_error": type(e).__name__, "shrunk": []}
    shrunk = []
    added = []
    for key in ("operator_ids", "hir_keys"):
        b = set(base.get(key) or [])
        c = set(cur.get(key) or [])
        lost = sorted(b - c)
        if lost:
            shrunk.append((key, lost))
        added.extend(sorted(c - b))
    if write and not shrunk:
        io.open(baseline_path, "w", encoding="utf-8", newline="\n").write(
            json.dumps(cur, ensure_ascii=False, indent=1) + "\n")
    return {"ok": not shrunk, "shrunk": shrunk, "added": len(added)}


def _selftest():
    """两向自证：满足下限要判过、低于下限要判不过、规则减少要判不过。"""
    good = bad = 0

    # 用假数据测判据本身（不依赖真实语料）
    def judge(dec, tot, floor=OFFLINE_FLOOR):
        return (float(dec) / tot if tot else 0.0) >= floor

    if judge(8, 10):
        good += 1
    else:
        bad += 1
        print("  [selftest] 80% 应达标")

    if not judge(7, 10):
        good += 1
    else:
        bad += 1
        print("  [selftest] 70% 不该达标")

    # 可生长：规则减少必须被抓
    import tempfile
    d = tempfile.mkdtemp(prefix="cb_")
    try:
        cur = _rule_sets()
        # 人为把基线造得比现在多一个，模拟"一条规则消失了"
        fake = {"operator_ids": sorted(set(cur["operator_ids"]) | {"OP-GHOST"}),
                "hir_keys": list(cur["hir_keys"])}
        p = os.path.join(d, "base.json")
        io.open(p, "w", encoding="utf-8").write(
            json.dumps(fake, ensure_ascii=False))
        r = check_growable(p)
        if not r["ok"] and r["shrunk"]:
            good += 1
        else:
            bad += 1
            print("  [selftest] 规则减少未被抓到：%r" % (r,))
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="小脑硬边界机检")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--update-baseline", action="store_true",
                    help="把当前规则集合写成新基线（仅在确认减少是合法重构时用）")
    ap.add_argument("--calibration",
                    default=os.path.join(ROOT, "flow",
                                         "cerebellum-calibration.json"),
                    help="人工标定集（判断判据本身对不对）")
    # **真实语料路径**（R1066）：不给时按"合成咨询"算，但那会得到 100%，
    # 与真实语料实测的 90% 相差 10 个点。R1065 就出现过"报告里是 90%、
    # 工具单独跑是 100%"的不一致——那种不一致不会报错，只会让人以为工具坏了。
    # 所以这里优先自动找已知真实 MIR，并在输出里明写用的是哪一份。
    ap.add_argument("--mir", help="真实 MIR 路径（不给则自动探测）")
    ns = ap.parse_args(argv)

    mir = ns.mir
    if not mir:
        for cand in ("E:/temp/matlabc/octgen/.m2c/project.mir",
                     "E:/temp/matlabc/oct_num/.m2c/project.mir"):
            if os.path.isfile(cand):
                mir = cand
                break

    if ns.selftest:
        return _selftest()

    # 先看标定集：它回答「判据判对了没有」，比总体百分比有意义
    cal = measure_calibration(ns.calibration)
    if cal:
        print("[标定集] %d 条 ｜ 判对 %d ｜ 准确率 %.0f%%"
              % (cal["total"], cal["hit"], cal["rate"] * 100))
        for row in cal["rows"]:
            print("  %s 期望%-4s 实得%-4s %s"
                  % ("✅" if row["ok"] else "❌", row["expect"],
                     row["actual"], row["text"]))

    off = measure_offline(mir, 200)
    grow = check_growable(write=ns.update_baseline)
    if off is None:
        print("cerebellum_bounds: 缺输入（取不到真实 kind 全集）")
        return 2

    r = {"offline": off, "growable": grow,
         "ok": bool(off["pass"] and grow["ok"])}
    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["ok"] else 1

    _basis = ("真实语料 %s" % os.path.basename(mir)
              if off.get("basis") == "real" else
              "**合成咨询（按 kind 构造，会偏乐观）**")
    print("[离线可用] 口径：%s" % _basis)
    print("  咨询 %d ｜ 小脑自决 %d ｜ 必须上行 %d ｜ 自决率 %.1f%%（下限 %.0f%%）"
          % (off["total"], len(off["decidable"]), len(off["escalate"]),
             off["rate"] * 100, off["floor"] * 100))
    if off["escalate"]:
        for k, why in off["escalate"][:5]:
            print("   上行：%-14s %s" % (k, why if isinstance(why, str) else ""))
    dist = feature_distribution(mir)
    if dist:
        print("[特征分布] 全量 %d 条" % dist["total"])
        print("  >=1 项：%d（%.1f%%）  ← 这是「含任一特征」，**不是** S5 的口径"
              % (dist["ge1"], dist["ge1_rate"]))
        print("  >=2 项：%d（%.1f%%）  ← **S5 实际用这个**"
              % (dist["ge2"], dist["ge2_rate"]))
        print("  >=2 项按类别：%s"
              % "、".join("%s %d" % (k, v) for k, v in dist["kinds"]))
    print("[可生长] 规则集合 %s"
          % ("只增不减 OK" if grow["ok"] else "**有减少**"))
    for key, lost in (grow.get("shrunk") or []):
        print("   %s 少了 %d 条：%s" % (key, len(lost), ",".join(lost[:6])))
    if grow.get("created"):
        print("   已创建基线 %s" % os.path.relpath(BASELINE, ROOT))
    print("[结论] %s" % ("两条硬边界均满足" if r["ok"] else "**未满足，见上**"))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
