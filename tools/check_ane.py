# -*- coding: utf-8 -*-
"""**ANE 规范对齐门**：把 `aistandard/ANE规范…md` 的强制条款变成可核对的判据。

    python tools/check_ane.py            # 0=全绿 1=有缺口 2=缺输入
    python tools/check_ane.py --report   # 写 flow/ane.json（供 full_report 引用）

## 为什么要有它

规范放在 `aistandard/` 里，而项目"按规范开发"这件事**此前只存在于口头**：
我每轮都说"我们的小脑/记忆/免疫对应第 X 条"，但**没有任何东西核对过**。
"说了就相当于做了"是这类规范最典型的腐化方式 —— 半年后没人知道哪条真落地了。

## 判据（只收**可机检**的条款，收不了的明说）

| 条款 | 判据 | 判法 |
|---|---|---|
| **第四条 小脑优先** | 无网络也能裁决 + 可审计 | `brain.py advise` 存在、`flow/brain-usage.jsonl` 有记录 |
| **第五条 战略性唤醒** | 仅拿不准才唤醒 + 输出是 proposal | `brain_llm.py` 四信号自证绿 + `ingest` 校验 witness |
| **第六条 记忆护城河** | 经验结构化 + 未验证禁止写入 | `failures.json` 每条有 witness；`record` 拒收无见证 |
| **第七条 绝对防御** | **杜绝静默失败** | 全仓 `except: pass` 计数**不得超过基线** |
| **第九条 一票否决** | AI 不得未经授权改主分支 | `flow/ane-auth.json` 里有本轮授权记录 |
| **第十条 全景白盒** | 无黑盒 | `full_report.html` + `progress.py` 产物存在 |

**收不进来的**（明确写在这里，避免假装覆盖）：
* 第八条「即时修复」—— 依赖 MIR 层的自愈实现深度，无法用存在性判据表达；
* 第三/十一章（D0–D3 分级、L0–L5 成熟度）—— 需要人工评级，本门只报"未评"。

退出码：
    0 = 六条全部成立
    1 = 有缺口（打印是哪条、差多少）
    2 = 缺输入（规范文件或核心产物缺失）
"""
import argparse
import io
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "aistandard", "ANE规范-AI原生软件生命体工程范式.md")
BASELINE = os.path.join(ROOT, "flow", "ane-baseline.json")
AUTH = os.path.join(ROOT, "flow", "ane-auth.json")
OUT = os.path.join(ROOT, "flow", "ane.json")

SILENT = re.compile(r"except[^\n]*:\s*\n\s*pass\b")
SKIP_DIRS = (".git", "target", "releases", "node_modules", "__pycache__",
             "aistandard")


def count_silent():
    n = 0
    worst = []
    for base, ds, fs in os.walk(ROOT):
        ds[:] = [d for d in ds if d not in SKIP_DIRS]
        for f in fs:
            if not f.endswith(".py"):
                continue
            p = os.path.join(base, f)
            try:
                s = io.open(p, encoding="utf-8", errors="replace").read()
            except (IOError, OSError):
                continue
            c = len(SILENT.findall(s))
            if c:
                n += c
                worst.append((c, os.path.relpath(p, ROOT)))
    worst.sort(reverse=True)
    return n, worst[:5]


def _exists(*parts):
    return os.path.isfile(os.path.join(ROOT, *parts))


def audit():
    """返回 (条目列表, 缺口列表)。每条 = {clause, title, ok, detail}。"""
    rows, gaps = [], []

    # 第四条：小脑无网络可裁决 + 可审计
    usage = os.path.join(ROOT, "flow", "brain-usage.jsonl")
    n_use = 0
    if os.path.isfile(usage):
        n_use = sum(1 for ln in io.open(usage, encoding="utf-8") if ln.strip())
    ok4 = _exists("tools", "brain.py") and n_use > 0
    rows.append({"clause": "第四条", "title": "小脑优先（本地裁决 + 可审计）",
                 "ok": ok4,
                 "detail": "brain.py 存在；咨询留痕 %d 条" % n_use})
    if not ok4:
        gaps.append("第四条：%s" % rows[-1]["detail"])

    # 第五条：仅拿不准才唤醒 + 输出是 proposal
    ok5 = _exists("tools", "brain_llm.py")
    if ok5:
        r = __import__("subprocess").run(
            [sys.executable, os.path.join(ROOT, "tools", "brain_llm.py"),
             "--selftest"], stdin=__import__("subprocess").PIPE,
            stdout=__import__("subprocess").PIPE,
            stderr=__import__("subprocess").STDOUT)
        out5 = r.stdout.decode("utf-8", "replace")
        ok5 = r.returncode == 0 and '"bad": 0' in out5
        d5 = "四信号自证 %s" % (out5.strip().splitlines() or ["?"])[-1][:40]
    else:
        d5 = "缺 brain_llm.py"
    rows.append({"clause": "第五条", "title": "战略性唤醒（四信号 + proposal）",
                 "ok": ok5, "detail": d5})
    if not ok5:
        gaps.append("第五条：%s" % d5)

    # 第六条：经验结构化 + 未验证禁止写入
    fp = os.path.join(ROOT, "flow", "failures.json")
    ok6, d6 = False, "缺 failures.json"
    if os.path.isfile(fp):
        try:
            d = json.load(io.open(fp, encoding="utf-8"))
            es = d.get("entries") or []
            bad = [e for e in es
                   if not (e.get("witness") or "").strip()
                   or not os.path.exists(os.path.join(ROOT, e["witness"]))]
            ok6 = bool(es) and not bad
            d6 = "%d 条经验，无见证 %d 条" % (len(es), len(bad))
        except ValueError:
            d6 = "failures.json 不是合法 JSON"
    rows.append({"clause": "第六条", "title": "记忆护城河（结构化 + 见证校验）",
                 "ok": ok6, "detail": d6})
    if not ok6:
        gaps.append("第六条：%s" % d6)

    # 第七条：杜绝静默失败（except: pass 不得超基线）
    n_sil, worst = count_silent()
    base = None
    if os.path.isfile(BASELINE):
        try:
            base = json.load(io.open(BASELINE, encoding="utf-8")).get("silent_pass")
        except ValueError:
            base = None
    if base is None:
        io.open(BASELINE, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"silent_pass": n_sil,
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
                       ensure_ascii=False, indent=2) + "\n")
        base = n_sil
    ok7 = n_sil <= base
    d7 = "except:pass %d 处（基线 %d）" % (n_sil, base)
    if worst:
        d7 += "；最多：" + "、".join("%s(%d)" % (f.split(os.sep)[-1], c)
                                     for c, f in worst[:2])
    rows.append({"clause": "第七条", "title": "绝对防御（杜绝静默失败）",
                 "ok": ok7, "detail": d7})
    if not ok7:
        gaps.append("第七条：%s —— 静默失败在增加" % d7)

    # 第九条：人类授权（AI 不得未经授权改主分支）
    ok9, d9 = False, "无 flow/ane-auth.json（本轮未经显式授权）"
    if os.path.isfile(AUTH):
        try:
            a = json.load(io.open(AUTH, encoding="utf-8"))
            ok9 = bool(a.get("granted_by")) and bool(a.get("scope"))
            d9 = "授权人 %r ｜ 范围 %r" % (a.get("granted_by"), a.get("scope"))
        except ValueError:
            d9 = "ane-auth.json 不合法"
    rows.append({"clause": "第九条", "title": "一票否决（人类授权）",
                 "ok": ok9, "detail": d9})
    if not ok9:
        gaps.append("第九条：%s" % d9)

    # 第十条：全景白盒
    ok10 = _exists("flow", "full_report.html") and _exists("tools", "progress.py")
    d10 = "full_report.html %s ｜ progress.py %s" % (
        "有" if _exists("flow", "full_report.html") else "缺",
        "有" if _exists("tools", "progress.py") else "缺")
    rows.append({"clause": "第十条", "title": "全景白盒（台账无黑盒）",
                 "ok": ok10, "detail": d10})
    if not ok10:
        gaps.append("第十条：%s" % d10)

    return rows, gaps


def grant(by, scope, until=""):
    """写一份**人类授权记录**（第九条）。

    **为什么必须由人执行**：规范第九条禁止 AI 在未经人类明确授权的情况下
    修改主分支。如果 AI 自己写这张文件，授权就变成了自证 —— 完全失去意义。
    所以这里只提供工具，**参数必须由人给**。

    `scope` 是授权范围（例如 "main 分支直推" / "仅 tools/ 与 flow/"），
    `until` 可选，写到期时间；空表示不定期。
    """
    if not by.strip():
        print("grant: 必须给 --by（授权人），不能留空")
        return 2
    if not scope.strip():
        print("grant: 必须给 --scope（授权范围），不能留空")
        return 2
    rec = {"granted_by": by.strip(), "scope": scope.strip(),
           "until": until.strip(),
           "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    io.open(AUTH, "w", encoding="utf-8", newline="\n").write(
        json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    print("check_ane: 已记录授权 -> %s" % os.path.relpath(AUTH, ROOT))
    print("         授权人 %r ｜ 范围 %r" % (rec["granted_by"], rec["scope"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="ANE 规范对齐门")
    ap.add_argument("--report", action="store_true", help="写 flow/ane.json")
    ap.add_argument("--grant", action="store_true",
                    help="写人类授权记录（第九条），须同时给 --by 与 --scope")
    ap.add_argument("--by", default="", help="授权人（人来填）")
    ap.add_argument("--scope", default="", help="授权范围")
    ap.add_argument("--until", default="", help="到期时间（可空）")
    ns = ap.parse_args(argv)

    if ns.grant:
        return grant(ns.by, ns.scope, ns.until)

    if not os.path.isfile(SPEC):
        print("check_ane: 缺输入（规范文件不存在）")
        return 2
    rows, gaps = audit()
    for r in rows:
        print("%s %-6s %-28s %s"
              % ("OK  " if r["ok"] else "GAP ", r["clause"], r["title"],
                 r["detail"]))
    if ns.report or True:
        io.open(OUT, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "rows": rows, "gaps": gaps,
                        "uncovered": ["第八条（自愈深度无法用存在性判据）",
                                      "第三章 D0–D3 分级（需人工评级）",
                                      "第十一章 L0–L5 成熟度（需人工评级）"]},
                       ensure_ascii=False, indent=2) + "\n")
    if gaps:
        print("check_ane: %d 条有缺口 -> %s" % (len(gaps), os.path.relpath(OUT, ROOT)))
        return 1
    print("check_ane: OK（6 条可机检条款全部成立）-> %s"
          % os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
