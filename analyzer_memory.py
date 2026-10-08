# -*- coding: utf-8 -*-
"""analyzer_memory —— matlabc 的跨运行项目记忆（P1-C）。

把「已验证修复 / 已知误报」持久化到工程本地 `.codebuddy/analyzer/memory.json`，
让自主修复闭环「越用越聪明」：

  * suppressions：人工标注的已知误报（rule/rel/line 签名），分析时过滤，避免反复打扰。
  * learned_fixes：闭环收敛（accept）后自动记录的已验证修复，按基线告警分布签名索引；
    下次同分布告警出现时可被检索复用，减少重复扫描与试错。

设计原则：
  * 纯标准库、零依赖；文件缺失/损坏一律优雅降级（返回空记忆，不影响既有行为）。
  * 写入带锁友好（单次原子 write + 目录预建）；learned_fixes 限长（默认 200），防止无限膨胀。
  * 绝不自动抑制告警（suppressions 须显式添加），避免掩盖真实缺陷。
"""
from __future__ import absolute_import, division, print_function

import io
import json
import os
import time

MEMORY_REL = os.path.join(".codebuddy", "analyzer", "memory.json")
MAX_LEARNED = 200


def memory_file(project_root):
    return os.path.join(project_root, MEMORY_REL)


def load_memory(project_root):
    """读取记忆；无文件/损坏则返回空记忆（含 suppressions/learned_fixes 默认键）。"""
    p = memory_file(project_root)
    if not os.path.exists(p):
        return {"suppressions": [], "learned_fixes": []}
    try:
        with io.open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {"suppressions": [], "learned_fixes": []}
        data.setdefault("suppressions", [])
        data.setdefault("learned_fixes", [])
        return data
    except (ValueError, OSError, TypeError):
        return {"suppressions": [], "learned_fixes": []}


def save_memory(project_root, mem):
    """原子写回记忆文件；成功返回 True。"""
    p = memory_file(project_root)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump(mem, fh, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, p)
        return True
    except (OSError, TypeError):
        return False


def _alert_key(a):
    return (a.get("rule"), a.get("rel") or a.get("file"), a.get("line"))


def suppress_alerts(alerts, mem):
    """按 suppressions 过滤已知误报；返回 (保留, 被抑制)。"""
    blocked = set()
    for s in (mem.get("suppressions") or []):
        blocked.add((s.get("rule"), s.get("rel") or s.get("file"), s.get("line")))
    kept, dropped = [], []
    for a in alerts:
        if _alert_key(a) in blocked:
            dropped.append(a)
        else:
            kept.append(a)
    return kept, dropped


def add_suppression(project_root, rule, rel, line):
    """显式登记一条已知误报（人工标注）。返回是否新增。"""
    mem = load_memory(project_root)
    supp = mem.setdefault("suppressions", [])
    key = (rule, rel, line)
    if key in [(s.get("rule"), s.get("rel") or s.get("file"), s.get("line"))
              for s in supp]:
        return False
    supp.append({"rule": rule, "rel": rel, "line": line,
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    save_memory(project_root, mem)
    return True


def signature_of(by_rule):
    """由基线告警分布（rule→count）生成稳定签名，用于 learned_fix 索引。"""
    return json.dumps(dict(sorted((k, int(v)) for k, v in (by_rule or {}).items())),
                      ensure_ascii=False, sort_keys=True)


def lookup_learned_fix(project_root, signature):
    """按基线签名检索已学习修复；命中返回最新一条记录，否则 None。"""
    mem = load_memory(project_root)
    best = None
    for f in (mem.get("learned_fixes") or []):
        if f.get("signature") == signature:
            # 同签名可能有多条历史，取最新 ts
            if best is None or f.get("ts", "") >= best.get("ts", ""):
                best = f
    return best


def record_learned_fix(project_root, record):
    """持久化一条已验证修复（闭环收敛后调用）。同签名去重，仅保留最新；限长。"""
    if not isinstance(record, dict) or not record.get("signature"):
        return False
    mem = load_memory(project_root)
    fixes = mem.setdefault("learned_fixes", [])
    sig = record["signature"]
    fixes[:] = [f for f in fixes if f.get("signature") != sig]
    fixes.append(record)
    mem["learned_fixes"] = fixes[-MAX_LEARNED:]
    return save_memory(project_root, mem)


def learned_fix_count(project_root):
    return len(load_memory(project_root).get("learned_fixes") or [])


def suppression_count(project_root):
    return len(load_memory(project_root).get("suppressions") or [])
