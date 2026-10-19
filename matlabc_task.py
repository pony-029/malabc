#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matlabc task —— 把"改代码"变成**带验收条件、可回滚**的任务。

为什么要有这一层
================

工具能查（19 个 MCP 工具）、也能改（propose/apply/undo），但**"改"这件事
本身没有被验收**：改完对不对，靠人再看一遍。

而本仓已经有一套现成的"说不"的能力（33 道门 / 206 条判据）。这一层就是把它
接到写操作上：

    prepare   算清楚要改哪些位置，并把**验收条件**先列出来
    apply       原子写入（逐文件备份）
    validate    改完重新分析，与改前逐项对比
    rollback    验收不过就自己退回去

**关键差异**：验收条件在**动手之前**就写在屏幕上，而不是事后解释。

一个图看懂
==========

    prepare ──▶ [验收条件] ──▶ apply ──▶ validate ──▶ 通过
                   │                        │
                   └── 人可以先看 plan       └── 不过 ──▶ rollback（自动）

用法：
    python matlabc_task.py rename --dir myproj --old foo --new bar
    python matlabc_task.py rename --dir myproj --old foo --new bar --apply
    python matlabc_task.py rename-field --dir myproj --old val --new value --apply
    python matlabc_task.py extract --dir myproj --file a.m --lines 12-18 \
        --name part --in x,y --out z --apply
    python matlabc_task.py extract --dir myproj --file a.m --lines 12-18 \
        --name part --auto --apply      # 接口由工具推断（启发式，先看 dry-run）
    python matlabc_task.py undo --dir myproj            # 撤销上一次任务
    python matlabc_task.py undo --dir myproj --apply
    python matlabc_task.py --selftest

退出码：
    0  = 任务完成且验收通过（未加 --apply 时 = 计划已生成）
    1  = 验收不通过（已回滚），或任务被拒绝
    2  = 用法错误 / 目录不存在 / 名称非法
"""
import argparse
import io
import base64
import hashlib
import json
import os
import time
import zlib
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SKIP_DIRS = (".git", "__pycache__", "node_modules", ".matlabc_task",
             ".pytest_cache", "build", "dist")

IDENT = u"[A-Za-z_][A-Za-z0-9_]*"


def _iter_m_files(root):
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for n in sorted(names):
            if n.endswith(".m"):
                yield os.path.join(dirpath, n)


def _mask_noise(line):
    """把注释与字符串**遮成等长的空格**，位置不变。

    为什么不是"跳过整行"：一行里可能既有注释又有真代码；遮成等长空格后，
    正则匹配到的位置仍然对应原文位置，既不会误改注释，也不会错位。
    """
    out = []
    in_str = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_str:
            if ch == u"'":
                in_str = False
                out.append(ch)
            else:
                out.append(u" ")
            i += 1
            continue
        if ch == u"%":
            # 注释到行尾
            out.append(u" " * (n - i))
            break
        if ch == u"'":
            # 转置运算符 vs 字符串：前一个非空字符是标识符/)/]/} 时是转置
            prev = u""
            for k in range(i - 1, -1, -1):
                if line[k] not in u" \t":
                    prev = line[k]
                    break
            if prev and (prev.isalnum() or prev in u"_)]}.'"):
                out.append(ch)
                i += 1
                continue
            in_str = True
            out.append(u" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return u"".join(out)


def _pattern(name, kind):
    """`ident` 认独立标识符；`field` 只认**点后面的**名字（`s.old` / `s(1).old`）。

    为什么要分成两种：重命名**函数**时，`s.helper` 是字段访问，不是那个函数；
    重命名**字段**时，独立的 `helper` 变量跟这个字段无关。一套正则同时兼两件事，
    必然在其中一边误伤。
    """
    tail = re.escape(name) + u"(?![A-Za-z0-9_])"
    if kind == "field":
        return re.compile(u"(?<=\\.)" + tail)
    return re.compile(u"(?<![A-Za-z0-9_.])" + tail)


def find_sites(root, name, kind="ident"):
    """返回 [(abs_path, line_idx(0 基), col, line_text)]。col 一律指向名字首字符。"""
    pat = _pattern(name, kind)
    sites = []
    for path in _iter_m_files(root):
        try:
            text = io.open(path, "r", encoding="utf-8", errors="replace").read()
        except (IOError, OSError):
            continue
        for li, line in enumerate(text.splitlines()):
            masked = _mask_noise(line)
            for m in pat.finditer(masked):
                sites.append((path, li, m.start(), line))
    return sites


def _scan(root):
    """用分析器取一份"改前/改后"可比对的指纹。"""
    try:
        from analyzer.api import analyze
    except Exception:
        from matlabc import analyze          # 兼容旧的导入路径
    res = analyze(root, no_checks=True)
    files = getattr(res, "files", None) or []
    nfun = 0
    for mf in files:
        nfun += len(getattr(mf, "functions", None) or [])
    edges = getattr(res, "edges", None)
    if edges is None:
        edges = []
        for mf in files:
            for f in (getattr(mf, "functions", None) or []):
                edges.extend(getattr(f, "calls", None) or [])
    diags = getattr(res, "diagnostics", None)
    if diags is None:
        diags = getattr(res, "issues", None) or []
    return {"files": len(files), "functions": nfun,
            "edges": len(edges), "diagnostics": len(diags)}


def _apply_rename(sites, old, new, backup=None):
    """按文件分组改写；把 {path: 原文} 填进 `backup`（**由调用方持有**）。

    ⚠ 备份**必须由调用方传入**：第一版把它当返回值，于是中途抛异常时
    备份跟着栈一起没了 —— 已写入的文件既没恢复、也没人知道它被改过。
    写盘失败（只读文件）这条路径由 `rsi_scenarios` 的「回滚」场景守着。
    """
    if backup is None:
        backup = {}
    pat = re.compile(u"(?<![A-Za-z0-9_.])" + re.escape(old) +
                     u"(?![A-Za-z0-9_])")
    per_file = {}
    for path, li, col, _ln in sites:
        per_file.setdefault(path, set()).add((li, col))
    for path, marks in per_file.items():
        text = io.open(path, "r", encoding="utf-8", errors="replace").read()
        backup[path] = text
        lines = text.splitlines()
        for li, col in marks:
            line = lines[li]
            masked = _mask_noise(line)
            # 在遮罩后的文本上定位，再按同一位置改原文
            if masked[col:col + len(old)] != old:
                continue
            lines[li] = line[:col] + new + line[col + len(old):]
        io.open(path, "w", encoding="utf-8", newline="").write(
            u"\n".join(lines) + (u"\n" if text.endswith(u"\n") else u""))
    return backup


def _restore(backup):
    for path, text in (backup or {}).items():
        try:
            io.open(path, "w", encoding="utf-8", newline="").write(text)
        except (IOError, OSError):
            pass


#: 任务记录目录（相对工程根）。每次**成功**的任务在这里落一条 JSON：
#: 改前的原文、改后的哈希。`undo` 靠它把工程倒回去。
HISTORY_DIR = os.path.join(".matlabc", "tasks")
#: 当前批量任务的编号。由 `task_batch` 在动手前设置，
#: 单步任务留空 —— 撤销时靠它把一批当成一次。
_CURRENT_BATCH = u""


def _pack_text(text):
    """把原文压成 base64(zlib)，记录文件体积能小一大截。

    为什么不用 diff：撤销需要的是**原文本身**；用 diff 就得写一个可靠的
    反向 patch 应用器，而那段代码一旦有偏差，撤销会静默产出错误的文件 ——
    比"记录占地方"严重得多。压缩没有这个风险，收益也已经够（实测 -70%）。
    """
    try:
        return base64.b64encode(zlib.compress(text.encode("utf-8"), 9)).decode("ascii")
    except Exception:
        return u""


def _unpack_text(rec_file):
    """兼容两种记录：新的 `before_z`（压缩）与旧的 `before`（明文）。"""
    if rec_file.get("before_z"):
        try:
            return zlib.decompress(
                base64.b64decode(rec_file["before_z"].encode("ascii"))
            ).decode("utf-8")
        except Exception:
            return None
    return rec_file.get("before")


def _git_head(root):
    """当前 HEAD（拿不到就返回空串）。

    为什么记它：撤销时如果仓库已经往前走了，说明"现在的代码"和"当初那次任务"
    之间还夹着别人的提交 —— 用户判断该不该撤时需要知道这一点。
    """
    try:
        import subprocess
        p = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=root, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=10)
        if p.returncode == 0:
            return p.stdout.decode("utf-8", "replace").strip()
    except Exception:
        pass
    return u""


def _sha_of(path):
    try:
        return hashlib.sha256(io.open(path, "rb").read()).hexdigest()
    except (IOError, OSError):
        return u""


def record_task(root, kind, params, backup, created=None, scan=None,
                verdict="pass", elapsed_ms=0, reason=u""):
    """记一条任务。**只在验收通过之后调用** —— 失败的任务已经自己回滚了，
    再记一条只会让 undo 撤销一个并不存在的变化。
    """
    try:
        d = os.path.join(root, HISTORY_DIR)
        if not os.path.isdir(d):
            os.makedirs(d)
        now = time.time()
        # ⚠ 括号不能省：`"%03d" % int(now * 1000) % 1000` 会被解析成
        # `("%03d" % int(now*1000)) % 1000` —— 先格式化再对字符串取模，
        # 抛 TypeError，而它被下面的 except 吞掉，于是"任务成功但记不上账"。
        # 第一版就是这样：撤销时报"没有可撤销的记录"，看起来像功能没实现。
        rid = (time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) +
               "-%03d" % (int(now * 1000) % 1000))
        rec = {
            "id": rid,
            "kind": kind,
            "params": params,
            "when": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "undone": (verdict != "pass"),
            "batch": _CURRENT_BATCH or u"",
            "git_head": _git_head(root),
            #: pass = 改动已生效；rollback = 没改成、已自动回退（这种记录只作历史，
            #: 不再提供 undo —— 它没有"改前"状态可退）
            "verdict": verdict,
            "elapsed_ms": int(elapsed_ms or 0),
            #: 失败原因（只在 verdict=rollback 时有值）："函数数变了、诊断增加了"
            "reason": reason or u"",
            # 任务**之前**的结构（函数数 / 调用边 / 诊断数）。
            # 撤销时拿它当验收标准：把文件恢复原样之后，结构也必须回到这里。
            "scan": ({k: (scan or {}).get(k) for k in
                      ("functions", "edges", "diagnostics")}
                     if scan else {}),
            "files": [{"path": os.path.relpath(p, root),
                       "before_z": _pack_text(t),
                       "after": _sha_of(p)}
                      for p, t in sorted(backup.items())],
            "created": [{"path": os.path.relpath(c, root),
                         "after": _sha_of(c)}
                        for c in (created or []) if os.path.isfile(c)],
        }
        io.open(os.path.join(d, rid + ".json"), "w",
                encoding="utf-8", newline="").write(
            json.dumps(rec, ensure_ascii=False, indent=1) + u"\n")
        # 写完顺手裁一下：控制在 MAX_RECORDS 以内，先删已撤销的
        prune_tasks(root, MAX_RECORDS, apply_it=True)
        return rid
    except Exception as exc:
        # 记不上不该让任务**失败**（任务是主体），但必须**说出来** ——
        # 第一版这里静默返回空串，用户以为能 undo，真去撤时才发现没记录。
        io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "matlabc_task.log"), "a",
                encoding="utf-8").write(
            u"record_task 失败：%r\n" % (exc,))
        return u""


def _latest_record(root):
    d = os.path.join(root, HISTORY_DIR)
    if not os.path.isdir(d):
        return None
    names = sorted(n for n in os.listdir(d) if n.endswith(".json"))
    for n in reversed(names):
        path = os.path.join(d, n)
        try:
            rec = json.loads(io.open(path, encoding="utf-8").read())
        except Exception:
            continue
        if not rec.get("undone"):
            rec["_file"] = path
            return rec
    return None


#: 任务记录保留条数上限。撤销只需要最近若干条，而记录是**只增不减**的 ——
#: 不设上限，` .matlabc/tasks/` 会随使用一直长下去。
MAX_RECORDS = 50


def prune_tasks(root, keep=MAX_RECORDS, apply_it=False):
    """把记录裁到 `keep` 条：**先删已撤销的，再删最旧的**。

    为什么先删已撤销的：那些记录已经用不上了（它们的目标状态已被回退），
    而保留它们只是占地方。只有当已撤销的删光仍超限时，才动"还能撤"的记录 ——
    那意味着用户会失去对最旧那几次操作的撤销能力，所以调用方要把这个数字报出来。
    """
    d = os.path.join(root, HISTORY_DIR)
    if not os.path.isdir(d):
        return {"total": 0, "removed_undone": 0, "removed_live": 0, "kept": 0}
    names = sorted(n for n in os.listdir(d) if n.endswith(".json"))
    total = len(names)
    over = total - keep
    if over <= 0:
        return {"total": total, "removed_undone": 0, "removed_live": 0,
                "kept": total}

    undone, live = [], []
    for n in names:
        path = os.path.join(d, n)
        try:
            rec = json.loads(io.open(path, encoding="utf-8").read())
            (undone if rec.get("undone") else live).append(path)
        except Exception:
            undone.append(path)      # 读不出来的当作可删

    victims = undone[:over]
    rest = over - len(victims)
    removed_undone = len(victims)
    removed_live = 0
    if rest > 0:
        victims += live[:rest]
        removed_live = min(rest, len(live))

    if apply_it:
        for path in victims:
            try:
                os.remove(path)
            except OSError:
                pass
    return {"total": total, "removed_undone": removed_undone,
            "removed_live": removed_live,
            "kept": total - len(victims)}


def list_tasks(root):
    """按时间列出任务记录（新的在前）。

    为什么要有：`undo` 默认只撤最近一次，而**多步任务**是一串记录 ——
    想撤到第三步之前，得先看见有哪些、哪个是哪个。
    """
    d = os.path.join(root, HISTORY_DIR)
    if not os.path.isdir(d):
        return []
    out = []
    for n in sorted((x for x in os.listdir(d) if x.endswith(".json")),
                    reverse=True):
        try:
            rec = json.loads(io.open(os.path.join(d, n),
                                     encoding="utf-8").read())
        except Exception:
            continue
        out.append({
            "id": rec.get("id") or n[:-5],
            "kind": rec.get("kind") or "?",
            "when": rec.get("when") or "",
            "undone": bool(rec.get("undone")),
            "files": len(rec.get("files") or []),
            "created": len(rec.get("created") or []),
            "params": rec.get("params") or {},
            "batch": rec.get("batch") or u"",
            "verdict": rec.get("verdict") or u"",
            "elapsed_ms": rec.get("elapsed_ms") or 0,
            "reason": rec.get("reason") or u"",
        })
    return out


def _load_record(root, rid):
    d = os.path.join(root, HISTORY_DIR)
    path = os.path.join(d, str(rid) + ".json")
    if not os.path.isfile(path):
        return None
    try:
        rec = json.loads(io.open(path, encoding="utf-8").read())
    except Exception:
        return None
    rec["_file"] = path
    return rec


def _sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _plan_undo(root, recs):
    """按记录**从新到旧**推演，返回 (writes, deletes, conflicts)。

    为什么不逐条直接写：整批撤销要么全成、要么全不动。
    逐条写的话，第 2 条冲突时第 1 条已经落盘 —— 用户得到一个"撤了一半"的工程，
    而这比不撤更难收拾。
    """
    state = {}     # path -> 虚拟内容
    gone = set()   # 虚拟已删除
    conflicts = []

    def current(p):
        if p in state:
            return state[p]
        if p in gone:
            return None
        try:
            return io.open(p, encoding="utf-8").read()
        except (IOError, OSError):
            return None

    for rec in recs:
        for f in rec.get("files") or []:
            p = os.path.join(root, f["path"])
            t = current(p)
            if t is None:
                conflicts.append(f["path"] + u"（已不存在）")
                continue
            if _sha_text(t) != f.get("after"):
                conflicts.append(f["path"] + u"（任务之后被改过）")
                continue
            text_before = _unpack_text(f)
            if text_before is None:
                conflicts.append(f["path"] + u"（记录已损坏，无法还原原文）")
                continue
            state[p] = text_before
            gone.discard(p)
        for c in rec.get("created") or []:
            p = os.path.join(root, c["path"])
            t = current(p)
            if t is not None and _sha_text(t) != c.get("after"):
                conflicts.append(c["path"] + u"（新建文件之后被改过）")
                continue
            state.pop(p, None)
            gone.add(p)
    return state, sorted(gone), conflicts


def task_stats(root):
    """按任务类型聚合记录：次数、耗时、回滚率。

    为什么需要：单条记录的耗时只说明那一次快不快；**同一类任务的典型耗时**
    才是能拿来做基线的东西（"改名通常 100ms 内，这次 800ms 就该看一眼"）。
    """
    rows = list_tasks(root)
    agg = {}
    for r in rows:
        kind = r.get("kind") or "?"
        a = agg.setdefault(kind, {"kind": kind, "n": 0, "rollback": 0,
                                  "ms": []})
        a["n"] += 1
        if r.get("verdict") == "rollback":
            a["rollback"] += 1
        ms = r.get("elapsed_ms") or 0
        if ms:
            a["ms"].append(ms)

    out = []
    for a in agg.values():
        ms = sorted(a["ms"])
        n = len(ms)
        avg = int(sum(ms) / n) if n else 0
        p50 = ms[n // 2] if n else 0
        out.append({"kind": a["kind"], "count": a["n"],
                    "rollback": a["rollback"],
                    "avg_ms": avg, "p50_ms": p50,
                    "max_ms": ms[-1] if n else 0})
    out.sort(key=lambda r: (-r["count"], r["kind"]))
    return out


def rollback_reasons(root):
    """回滚原因分类：哪条判据最常让人失败。

    单看"回滚了几次"没用；**按原因聚合**才指出最容易踩的那个坑
    （例如"调用边数变了"通常意味着改名撞了已有函数）。
    """
    tally = {}
    for r in list_tasks(root):
        if r.get("verdict") != "rollback":
            continue
        reason = (r.get("reason") or u"（未记录原因）").strip()
        # 一个原因字符串可能是 "函数数变了、诊断增加了" —— 拆开分别计数
        for part in [p.strip() for p in reason.split(u"、") if p.strip()]:
            tally[part] = tally.get(part, 0) + 1
    rows = [{"reason": k, "count": v} for k, v in tally.items()]
    rows.sort(key=lambda x: (-x["count"], x["reason"]))
    return rows


def task_undo(root, apply_it=False, rec_id=None, whole_batch=False,
               show_diff=False):
    """撤销任务。

    默认只撤**最近一次**；`whole_batch=True` 时把最近那一批（batch）整批撤掉，
    因为 `batch` 本身就是一个事务 —— 撤销也该是一次。

    为什么需要它：任务失败会自动回滚，但**成功之后想反悔**只能靠 git ——
    而 git 只保护已提交的状态，用户刚跑完任务时通常还没提交。
    """
    log = []

    def say(step, msg):
        log.append({"step": step, "msg": msg})

    if not os.path.isdir(root):
        say("error", u"目录不存在：%s" % root)
        return 2, log, {}

    recs = []
    if rec_id:
        rec = _load_record(root, rec_id)
        if not rec:
            say("undo", u"找不到任务记录：%s" % rec_id)
            return 1, log, {"verdict": "nothing"}
        if rec.get("undone"):
            say("undo", u"这条任务已经撤销过：%s" % rec_id)
            return 1, log, {"verdict": "nothing"}
        recs = [rec]
    else:
        head = _latest_record(root)
        if not head:
            say("undo", u"没有可撤销的任务记录（%s）" % HISTORY_DIR)
            return 1, log, {"verdict": "nothing"}
        bid = (head.get("batch") or u"") if whole_batch else u""
        if bid:
            # 同批的全部记录，按时间从新到旧
            rows = list_tasks(root)
            order = [r["id"] for r in rows if not r["undone"]]
            for rid in order:
                r = _load_record(root, rid)
                if r and (r.get("batch") or u"") == bid:
                    recs.append(r)
            recs = recs or [head]
        else:
            recs = [head]

    say("undo", u"目标：%s" % u"、".join(r.get("id") or "?" for r in recs))
    for r in recs:
        say("undo", u"  · %s %s %s" % (r.get("kind"), r.get("when", ""),
                                       r.get("id")))

    writes, deletes, conflicts = _plan_undo(root, recs)
    if conflicts:
        say("undo", u"拒绝撤销 —— 撤销会覆盖任务之后的改动：")
        for one in conflicts:
            say("undo", u"  · " + one)
        say("undo", u"确认要丢弃这些改动，可以先用 git 存一下再重试")
        return 1, log, {"verdict": "conflict", "conflicts": conflicts}

    if not apply_it:
        say("plan", u"将恢复 %d 个文件、删除 %d 个新建文件（未写盘）"
            % (len(writes), len(deletes)))
        if show_diff:
            import difflib
            for p in sorted(writes):
                try:
                    old = io.open(p, encoding="utf-8").read()
                except (IOError, OSError):
                    continue
                rel = os.path.relpath(p, root)
                diff = difflib.unified_diff(
                    old.splitlines(), writes[p].splitlines(),
                    fromfile=u"当前 %s" % rel,
                    tofile=u"撤销后 %s" % rel, lineterm=u"")
                chunk = list(diff)
                if not chunk:
                    say("diff", u"%s：内容相同（不会改动）" % rel)
                    continue
                say("diff", u"%s：" % rel)
                for ln in chunk[:120]:
                    log.append({"step": "diff", "msg": ln})
                if len(chunk) > 120:
                    log.append({"step": "diff",
                                "msg": u"…（还有 %d 行）" % (len(chunk) - 120)})
        # 记录时的 HEAD 与现在不同 -> 提醒一句（不阻止）
        heads = set((r.get("git_head") or u"") for r in recs)
        cur_head = _git_head(root)
        if any(heads) and cur_head and cur_head not in heads:
            say("undo", u"注意：任务之后仓库有新提交（记录时 %s，现在 %s）"
                % (u", ".join(sorted(h for h in heads if h)) or u"?", cur_head))
        info = {"verdict": "plan",
                "ids": [r.get("id") for r in recs],
                # 界面上要显示"会恢复几个文件" —— 不返回就只能显示 0
                "files": len(writes), "deleted": len(deletes)}
        if show_diff:
            # 编辑器要开**原生 diff 视图**（左：现在，右：撤销后），
            # 它需要"撤销后的内容"本身 —— 只有 diff 文本是画不出并排视图的。
            info["previews"] = [
                {"path": os.path.relpath(p, root), "before": writes[p]}
                for p in sorted(writes)]
        return 0, log, info

    # 撤销也要**可回退**：万一恢复之后结构不对，得能退回"撤销前"。
    pre = {}
    for p in list(writes) + list(deletes):
        try:
            pre[p] = io.open(p, encoding="utf-8").read()
        except (IOError, OSError):
            pre[p] = None

    for p, text in writes.items():
        io.open(p, "w", encoding="utf-8", newline="").write(text)
    removed = 0
    for p in deletes:
        try:
            os.remove(p)
            removed += 1
        except OSError:
            pass

    # **撤销后验收**：结构必须回到"任务之前"的样子。
    # 目标取自这一批里**最早**那条记录的 scan（recs 是从新到旧）。
    target = (recs[-1].get("scan") or {}) if recs else {}
    now = _scan(root)
    bad = []
    if target.get("functions") is not None:
        if now["functions"] != target["functions"]:
            bad.append(u"函数数 %d（应为 %d）"
                       % (now["functions"], target["functions"]))
        if now["edges"] != target["edges"]:
            bad.append(u"调用边 %d（应为 %d）" % (now["edges"], target["edges"]))
        if now["diagnostics"] > target["diagnostics"]:
            bad.append(u"诊断 %d（不应超过 %d）"
                       % (now["diagnostics"], target["diagnostics"]))
    if bad:
        # **说清楚差在哪、可能是什么原因** —— 只报数字等于让用户自己猜。
        say("validate", u"撤销后验收不通过：")
        for one in bad:
            say("validate", u"  · " + one)
        hint = []
        if target.get("functions") is not None \
                and now["functions"] < target["functions"]:
            hint.append(u"文件恢复不完整（像是少了函数定义）")
        elif target.get("functions") is not None \
                and now["functions"] > target["functions"]:
            hint.append(u"文件里多了函数（可能恢复到了错误的历史版本）")
        if target.get("edges") is not None and now["edges"] < target["edges"]:
            hint.append(u"调用关系变少（可能有调用点没恢复）")
        if target.get("diagnostics") is not None \
                and now["diagnostics"] > target["diagnostics"]:
            hint.append(u"出现新的诊断（恢复出的代码与当前工程不匹配）")
        if hint:
            say("validate", u"可能的原因：" + u"；".join(hint))
        say("validate", u"若确需强行回到任务前，可用 git 检出对应提交")
        # 退回撤销前的状态：留着"撤了一半又不对"的工程比不撤更糟
        for p, text in pre.items():
            if text is None:
                try:
                    os.remove(p)
                except OSError:
                    pass
            else:
                io.open(p, "w", encoding="utf-8", newline="").write(text)
        say("validate", u"撤销后验收不通过：%s" % u"、".join(bad))
        say("validate", u"已退回撤销前的状态（工程未变）")
        return 1, log, {"verdict": "verify_failed", "issues": bad}
    if target:
        say("validate", u"结构回到任务前：函数 %d ｜ 调用边 %d ｜ 诊断 %d"
            % (now["functions"], now["edges"], now["diagnostics"]))
        say("validate", u"撤销验收通过（3/3）")

    for r in recs:
        r["undone"] = True
        try:
            io.open(r["_file"], "w", encoding="utf-8", newline="").write(
                json.dumps(dict((k, v) for k, v in r.items()
                                if not k.startswith("_")),
                           ensure_ascii=False, indent=1) + u"\n")
        except Exception:
            pass

    say("undo", u"已恢复 %d 个文件，删除 %d 个新建文件（%d 个任务）"
        % (len(writes), removed, len(recs)))
    after = _scan(root)
    say("validate", u"撤销后：函数 %d ｜ 诊断 %d"
        % (after["functions"], after["diagnostics"]))
    return 0, log, {"verdict": "undone",
                    "ids": [r.get("id") for r in recs], "after": after,
                    "files": len(writes), "deleted": removed}



def task_rename(root, old, new, apply_it=False, as_json=False,
                kind="ident"):
    """rename 任务：prepare -> 验收条件 -> apply -> validate（失败自动 rollback）。"""
    log = []
    t0 = time.time()
    def say(step, msg):
        log.append({"step": step, "msg": msg})

    if not os.path.isdir(root):
        say("error", u"目录不存在：%s" % root)
        return 2, log, {}
    if not re.match(u"^" + IDENT + u"$", old or u"") or \
            not re.match(u"^" + IDENT + u"$", new or u""):
        say("error", u"名称必须是合法标识符（old=%r new=%r）" % (old, new))
        return 2, log, {}
    if old == new:
        say("error", u"新旧名称相同")
        return 2, log, {}

    before = _scan(root)
    label = ((u"." + old) if kind == "field" else old)
    sites = find_sites(root, old, kind)
    files = sorted(set(s[0] for s in sites))
    say("prepare", u"扫描完成：%d 个 .m 文件，命中 %d 处（%d 个文件）"
        % (len(list(_iter_m_files(root))), len(sites), len(files)))
    if not sites:
        say("plan", u"没有找到 `%s` —— 任务结束（不写任何文件）" % label)
        return 1, log, {"before": before, "sites": 0}

    # **验收条件先写出来**：动手之前就固定判据，避免事后解释。
    # 第 1 条是这轮补的：只比计数抓不到"只改了一半" —— 旧名字还有残留时，
    # 函数数与边数都可能**恰好不变**。
    criteria = [
        u"代码里不再出现 `%s`（注释与字符串不算）" % label,
        u"函数总数与改前相同（改名不改函数的数量）",
        (u"调用边数与改前相同（字段改名不该改变调用图）" if kind == "field"
         else u"调用边数与改前相同（原来指向 `%s` 的边全部指向 `%s`）"
              % (old, new)),
        u"诊断数不增加（改名不该引入新问题）",
    ]
    say("plan", u"将把 %d 处 `%s` 改为 `%s`，涉及 %d 个文件"
        % (len(sites), label,
           (u"." + new) if kind == "field" else new, len(files)))
    for i, c in enumerate(criteria):
        say("criteria", u"%d) %s" % (i + 1, c))

    if not apply_it:
        say("dry-run", u"未加 --apply，没有写入任何文件")
        return 0, log, {"before": before, "sites": len(sites),
                        "files": len(files), "criteria": criteria}

    backup = {}
    try:
        _apply_rename(sites, old, new, backup)
        say("apply", u"已写入 %d 个文件（备份在内存，验收不过自动回滚）"
            % len(backup))
        after = _scan(root)
        left = len(find_sites(root, old, kind))
        ok_left = (left == 0)
        ok_fun = after["functions"] == before["functions"]
        ok_edge = after["edges"] == before["edges"]
        ok_diag = after["diagnostics"] <= before["diagnostics"]
        say("validate", u"残留 %d 处 ｜ 函数 %d→%d ｜ 调用边 %d→%d ｜ 诊断 %d→%d"
            % (left, before["functions"], after["functions"],
               before["edges"], after["edges"],
               before["diagnostics"], after["diagnostics"]))
        if ok_left and ok_fun and ok_edge and ok_diag:
            say("validate", u"验收通过（4/4）")
            _rid = record_task(root, ("rename-field" if kind == "field"
                                      else "rename"),
                               {"old": old, "new": new}, backup,
                               scan=before,
                               elapsed_ms=(time.time() - t0) * 1000)
            if _rid:
                say("record", u"已记入 %s（可 undo）" % HISTORY_DIR)
            else:
                say("record", u"未能写任务记录 —— 本次无法 undo")
            return 0, log, {"before": before, "after": after,
                            "sites": len(sites), "files": len(files),
                            "criteria": criteria, "verdict": "pass"}
        # **不过就自己退回去** —— 留下一个坏状态比不改更糟
        _restore(backup)
        why = []
        if not ok_left:
            why.append(u"仍有 %d 处旧名字" % left)
        if not ok_fun:
            why.append(u"函数数变了")
        if not ok_edge:
            why.append(u"调用边数变了")
        if not ok_diag:
            why.append(u"诊断增加了")
        say("rollback", u"验收不通过（%s）—— 已逐字节恢复 %d 个文件"
            % (u"、".join(why), len(backup)))
        # 失败也要留痕，而且**连原因一起** —— 只记"回滚过"回答不了"为什么"。
        record_task(root, u"rollback", {"old": old, "new": new}, {},
                    verdict="rollback", reason=u"、".join(why),
                    elapsed_ms=(time.time() - t0) * 1000)
        return 1, log, {"before": before, "sites": len(sites),
                        "criteria": criteria, "verdict": "rollback"}
    except Exception as exc:
        # 注意：这里**没有** `created` —— 改名不新建文件。
        # （加 `--to` 时我把它一起插进来了，回滚路径直接 NameError；
        #  场景「任务 rename 回滚」当场抓到，否则只有真出异常时才会暴露。）
        _restore(backup)
        say("rollback", u"异常 %r —— 已恢复" % (exc,))
        return 1, log, {"before": before, "verdict": "error"}



def _split_list(text):
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def _existing_functions(root):
    """工程里已有的函数名集合 —— 用来在**动手前**拒绝重名。"""
    try:
        from analyzer.api import analyze
    except Exception:
        from matlabc import analyze
    res = analyze(root, no_checks=True)
    names = set()
    for mf in (getattr(res, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            nm = getattr(f, "name", "") or ""
            if nm:
                names.add(nm)
    return names



#: MATLAB 关键字：不是变量，推断时必须排除。
MATLAB_KEYWORDS = set([
    u"function", u"end", u"if", u"else", u"elseif", u"for", u"while",
    u"switch", u"case", u"otherwise", u"try", u"catch", u"return",
    u"break", u"continue", u"global", u"persistent", u"classdef",
    u"methods", u"properties", u"events", u"parfor", u"spmd",
])

_RE_ASSIGN = re.compile(u"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)")
_RE_ASSIGN_MULTI = re.compile(u"^\s*\[([^\]]*)\]\s*=")
_RE_IDENT = re.compile(u"(?<![A-Za-z0-9_.])([A-Za-z_][A-Za-z0-9_]*)")


def _assigned_in(line):
    """这一行**赋值给**了哪些名字（`y = ...` 或 `[a, b] = ...`）。"""
    masked = _mask_noise(line)
    m = _RE_ASSIGN_MULTI.match(masked)
    if m:
        return set(x.strip() for x in m.group(1).split(u",") if x.strip())
    m = _RE_ASSIGN.match(masked)
    return set([m.group(1)]) if m else set()


def _used_in(line):
    """这一行**读**了哪些名字（排除关键字、排除点后面的字段名）。"""
    masked = _mask_noise(line)
    out = set()
    for m in _RE_IDENT.finditer(masked):
        nm = m.group(1)
        if nm in MATLAB_KEYWORDS:
            continue
        # 点后面的名字是字段，不是变量
        prev = masked[:m.start()].rstrip()
        if prev.endswith(u"."):
            continue
        out.add(nm)
    return out


def _function_outputs(lines, start):
    """向上找最近的 `function` 行，取出它的输出变量名。

    为什么需要：块尾那句 `y = b;` 之后往往就是 `end` —— 按"之后是否还被用到"
    判断，`y` 会被漏掉，而它恰恰是**这个函数要返回的东西**。
    """
    for i in range(start - 2, -1, -1):
        st = _mask_noise(lines[i]).strip()
        if not st.startswith(u"function"):
            continue
        rest = st[len(u"function"):].strip()
        if u"=" not in rest:
            return []
        left = rest.split(u"=", 1)[0].strip()
        if left.startswith(u"["):
            left = left.strip(u"[]")
        return [x.strip() for x in left.split(u",") if x.strip()]
    return []


def infer_interface(text, start, end):
    """推断提取块的输入/输出。**启发式**，不是数据流分析。

    输入 = 块里**先读后写**（或只读）、且在块之前出现过的名字（含函数参数）
    输出 = 块里赋值、且（块之后还被用到 **或** 它是本函数的返回值）

    规则写在这里，是为了让人能判断它什么时候会猜错：循环里跨迭代的变量、
    通过 `eval`/`assignin` 间接读写的名字，它都看不出来。
    """
    lines = text.splitlines()
    block = lines[start - 1:end]
    before = u"\n".join(lines[:start - 1])
    after = u"\n".join(lines[end:])

    defined_before = set()
    for ln in before.splitlines():
        defined_before |= _assigned_in(ln)
        defined_before |= set(m.group(1) for m in _RE_IDENT.finditer(
            _mask_noise(ln)))

    order_u, first_use, first_asg = [], {}, {}
    assigned_block = set()
    order_a = []
    for i, ln in enumerate(block):
        for nm in _used_in(ln):
            if nm not in first_use:
                first_use[nm] = i
                order_u.append(nm)
        for nm in _assigned_in(ln):
            if nm not in first_asg:
                first_asg[nm] = i
                order_a.append(nm)
            assigned_block.add(nm)

    used_after = _used_in(after)
    fn_outs = _function_outputs(lines, start)

    ins = [n for n in order_u
           if n in defined_before
           and first_use.get(n, 10 ** 9) < first_asg.get(n, 10 ** 9)]
    outs = [n for n in order_a
            if n in used_after or n in fn_outs]
    return ins, outs


def task_extract(root, rel, start, end, name, ins, outs,
                 apply_it=False, auto=False, to=None):
    """extract 任务：把 `rel` 的第 start..end 行提成一个新函数。

    **接口由调用方显式给出**（`--in` / `--out`）。自动推断输入输出需要数据流，
    那是下一步；这一版宁可要求人写清楚，也不假装猜得准 —— 猜错的提取比不提更糟。
    """
    log = []
    t0 = time.time()

    def say(step, msg):
        log.append({"step": step, "msg": msg})

    if not os.path.isdir(root):
        say("error", u"目录不存在：%s" % root)
        return 2, log, {}
    path = rel if os.path.isabs(rel) else os.path.join(root, rel)
    if not os.path.isfile(path):
        say("error", u"文件不存在：%s" % path)
        return 2, log, {}
    if not re.match(u"^" + IDENT + u"$", name or u""):
        say("error", u"新函数名不合法：%r" % (name,))
        return 2, log, {}
    if name in _existing_functions(root):
        say("error", u"工程里已有同名函数 `%s` —— 换个名字" % name)
        return 1, log, {}

    text = io.open(path, "r", encoding="utf-8", errors="replace").read()
    lines = text.splitlines()
    if not (1 <= start <= end <= len(lines)):
        say("error", u"行号越界：%d-%d（共 %d 行）" % (start, end, len(lines)))
        return 2, log, {}
    block = lines[start - 1:end]
    for ln in block:
        st = ln.strip()
        if st.startswith(u"function") or st == u"end":
            say("error", u"选区里含 `function`/`end` —— 本版只提纯语句块")
            return 1, log, {}
    if not u"".join(block).strip():
        say("error", u"选区是空的")
        return 1, log, {}

    if auto and not (ins or outs):
        ins, outs = infer_interface(text, start, end)
        say("infer", u"自动推断：in=%s ｜ out=%s（启发式，请先看 dry-run）"
            % (u",".join(ins) or u"无", u",".join(outs) or u"无"))
        if not ins and not outs:
            say("infer", u"没能推断出接口 —— 请显式给 --in/--out")

    indent = block[0][:len(block[0]) - len(block[0].lstrip())]
    lhs = u""
    if len(outs) == 1:
        lhs = outs[0] + u" = "
    elif len(outs) > 1:
        rhs = u", ".join(outs)
        lhs = u"[" + rhs + u"] = "
    call_line = indent + lhs + name + u"(" + u", ".join(ins) + u");"

    sig = (u"function " + lhs.strip().rstrip(u"= ").strip() + u" = " + name
           if False else None)
    # 函数签名：有输出用 `function [a, b] = name(...)`，无输出用 `function name(...)`
    if outs:
        sig_outs = (outs[0] if len(outs) == 1
                    else u"[" + u", ".join(outs) + u"]")
        head = u"function %s = %s(%s)" % (sig_outs, name, u", ".join(ins))
    else:
        head = u"function %s(%s)" % (name, u", ".join(ins))

    before = _scan(root)
    tgt = None
    if to:
        tgt = to if os.path.isabs(to) else os.path.join(root, to)
        if not tgt.endswith(u".m"):
            say("error", u"--to 必须是 .m 文件：%s" % to)
            return 2, log, {}
        if not os.path.abspath(tgt).startswith(os.path.abspath(root)):
            say("error", u"--to 必须落在工程目录内：%s" % to)
            return 2, log, {}
        if os.path.exists(tgt):
            # **不覆盖已有文件**：那是另一个函数，静默覆盖等于删代码。
            say("error", u"目标文件已存在，拒绝覆盖：%s" % to)
            return 1, log, {}

    say("prepare", u"%s 第 %d-%d 行（%d 行）→ 新函数 `%s`%s"
        % (os.path.basename(path), start, end, len(block), name,
           (u"（写到 %s）" % os.path.basename(tgt)) if tgt else u"（同文件局部函数）"))
    if tgt:
        criteria = [
            u"工程函数总数 +1",
            u"诊断数不增加",
            u"新文件只含一个函数，且名字就是 `%s`" % name,
        ]
    else:
        criteria = [
            u"函数总数 +1（多出一个函数）",
            u"诊断数不增加（提取不该引入新问题）",
            u"文本里 `function` 与 `end` 各 +1（结构配平）",
        ]
    for i, c in enumerate(criteria):
        say("criteria", u"%d) %s" % (i + 1, c))
    say("plan", u"替换为：`%s`" % call_line.strip())
    if not apply_it:
        say("dry-run", u"未加 --apply，没有写入任何文件")
        return 0, log, {"before": before, "criteria": criteria}

    backup = {path: text}
    created = []
    try:
        new_lines = (lines[:start - 1] + [call_line] + lines[end:])
        body = u"\n".join(new_lines).rstrip(u"\n") + u"\n"
        fn_body = head + u"\n" + u"\n".join(block) + u"\nend\n"
        if tgt:
            # **先写新文件、再改原文件**：反过来的话，新文件写失败时原文件
            # 已经被改成了调用一个还不存在的函数。
            io.open(tgt, "w", encoding="utf-8", newline="").write(fn_body)
            created.append(tgt)
            io.open(path, "w", encoding="utf-8", newline="").write(body)
            say("apply", u"已新建 %s，并把 %s 的 %d 行换成调用"
                % (os.path.basename(tgt), os.path.basename(path), len(block)))
        else:
            body = body.rstrip(u"\n") + u"\n\n" + fn_body
            io.open(path, "w", encoding="utf-8", newline="").write(body)
            say("apply", u"已写入 %s（备份在内存）" % os.path.basename(path))

        after = _scan(root)
        now = io.open(path, "r", encoding="utf-8").read()
        ok_fun = after["functions"] == before["functions"] + 1
        ok_diag = after["diagnostics"] <= before["diagnostics"]
        if tgt:
            ok_txt = (fn_body.count(u"function") == 1
                      and len(re.findall(r"(?m)^\s*end\s*$", fn_body)) == 1
                      and call_line.strip() in now)
        else:
            ok_txt = (now.count(u"function") == text.count(u"function") + 1
                      and len(re.findall(r"(?m)^\s*end\s*$", now))
                      == len(re.findall(r"(?m)^\s*end\s*$", text)) + 1)
        say("validate", u"函数 %d→%d ｜ 诊断 %d→%d ｜ function/end 配平 %s"
            % (before["functions"], after["functions"],
               before["diagnostics"], after["diagnostics"],
               u"是" if ok_txt else u"否"))
        if ok_fun and ok_diag and ok_txt:
            say("validate", u"验收通过（3/3）")
            _rid = record_task(root, "extract",
                               {"file": rel, "name": name,
                                "lines": "%d-%d" % (start, end)},
                               backup, created, scan=before,
                               elapsed_ms=(time.time() - t0) * 1000)
            if _rid:
                say("record", u"已记入 %s（可 undo）" % HISTORY_DIR)
            else:
                say("record", u"未能写任务记录 —— 本次无法 undo")
            return 0, log, {"before": before, "after": after,
                            "criteria": criteria, "verdict": "pass"}
        _restore(backup)
        for _c in created:
            try:
                os.remove(_c)      # 新建的文件也必须撤掉，否则留下半成品
            except OSError:
                pass
        why = []
        if not ok_fun:
            why.append(u"函数数没 +1")
        if not ok_diag:
            why.append(u"诊断增加了")
        if not ok_txt:
            why.append(u"function/end 不配平")
        say("rollback", u"验收不通过（%s）—— 已恢复原文件" % u"、".join(why))
        return 1, log, {"before": before, "criteria": criteria,
                        "verdict": "rollback"}
    except Exception as exc:
        _restore(backup)
        for _c in created:
            try:
                os.remove(_c)
            except OSError:
                pass
        say("rollback", u"异常 %r —— 已恢复" % (exc,))
        return 1, log, {"verdict": "error"}



def _function_name_of(line):
    """从一行 `function ...` 里取出**函数名**；不是函数行返回 None。

    为什么不写一条正则直接匹配"带名字的 function 行"：
    `function y = helper(x)` / `function helper(x)` / `function [a,b] = helper(x)`
    三种形态，再叠加 `\b` / `[^\n]*?` 的交互，非常容易写出"外部测着对、
    放进函数里就不匹配"的模式（我就踩了一次）。拆开做，每一步都能单独验。
    """
    st = line.strip()
    if not st.startswith(u"function"):
        return None
    rest = st[len(u"function"):]
    head = rest.split(u"(", 1)[0]
    if u"=" in head:
        head = head.split(u"=", 1)[1]
    m = re.match(u"\s*([A-Za-z_][A-Za-z0-9_]*)", head)
    return m.group(1) if m else None


def _function_block(lines, name):
    """定位 `name` 这个函数的**整块**（0 基，含首尾）。

    两种写法都要认：有 `end` 的，到同缩进的 `end`；**省略 `end`** 的，
    到下一个同缩进的 `function` 或文件末尾。
    认错的后果是把下一个函数一起搬走 —— 而文件仍然合法、仍然能跑。
    """
    start = None
    for i, ln in enumerate(lines):
        if _function_name_of(ln) == name:
            start = i
            break
    if start is None:
        return None

    indent = lines[start][:len(lines[start]) - len(lines[start].lstrip())]
    end = None
    for j in range(start + 1, len(lines)):
        st = lines[j].strip()
        # 「同缩进」= 去掉基准缩进后**不以空白开头**。
        # 第一版写成 `not line[len(indent):len(indent)+1].strip()`，缩进为空时
        # 取到的是行首那个字母，永远判 False —— 于是 main 的块一路延伸到了
        # 文件末尾（把后面的 helper 也含进去）。
        rest = lines[j][len(indent):]
        at_same_indent = (lines[j].startswith(indent)
                          and not rest.startswith(u" ")
                          and not rest.startswith(u"\t"))
        if st == u"end" and at_same_indent:
            end = j
            break
        if st.startswith(u"function") and at_same_indent:
            end = j - 1
            break
    if end is None:
        end = len(lines) - 1
    while end > start and not lines[end].strip():
        end -= 1
    return (start, end)



def task_move(root, rel, name, to, apply_it=False):
    """move 任务：把 `rel` 里的函数 `name` 整块搬到 `to`（同工程）。"""
    log = []
    t0 = time.time()

    def say(step, msg):
        log.append({"step": step, "msg": msg})

    if not os.path.isdir(root):
        say("error", u"目录不存在：%s" % root)
        return 2, log, {}
    src = rel if os.path.isabs(rel) else os.path.join(root, rel)
    dst = to if os.path.isabs(to) else os.path.join(root, to)
    if not os.path.isfile(src):
        say("error", u"源文件不存在：%s" % rel)
        return 2, log, {}
    if not dst.endswith(u".m"):
        say("error", u"目标必须是 .m 文件：%s" % to)
        return 2, log, {}
    if os.path.abspath(src) == os.path.abspath(dst):
        say("error", u"源与目标相同 —— 同文件内调整顺序不在本任务范围内")
        return 1, log, {}

    text = io.open(src, "r", encoding="utf-8", errors="replace").read()
    lines = text.splitlines()
    blk = _function_block(lines, name)
    if blk is None:
        say("error", u"%s 里没有找到函数 `%s`" % (rel, name))
        return 1, log, {}
    s0, e0 = blk
    block = lines[s0:e0 + 1]

    before = _scan(root)
    say("prepare", u"%s 第 %d-%d 行（%d 行）→ 搬到 %s"
        % (rel, s0 + 1, e0 + 1, len(block), to))
    criteria = [
        u"工程函数总数不变（搬动不增减函数）",
        u"诊断数不增加",
        u"源文件里不再定义 `%s`，目标文件里出现" % name,
        u"目标文件名为 `%s.m`（否则调用点会失效）" % name,
    ]
    for i, c in enumerate(criteria):
        say("criteria", u"%d) %s" % (i + 1, c))

    # **MATLAB 的语义约束**：函数搬到别的文件后，只有**文件名与函数名相同**
    # 时才能被外部调用；而且原文件里的调用点仍然写 `helper(...)` ——
    # 搬到 `util.m` 里就变成"文件内私有子函数"，调用点会**静默失效**
    # （分析器报 unresolved，运行时报 undefined，而那时已经改完了）。
    base = os.path.splitext(os.path.basename(dst))[0]
    if base != name:
        say("error", u"目标文件名必须与函数名相同（%s.m），否则调用点会失效"
            % name)
        return 1, log, {}
    if os.path.isfile(dst):
        say("error", u"目标文件已存在，拒绝覆盖：%s" % to)
        return 1, log, {}

    dst_text = u""

    if not apply_it:
        say("dry-run", u"未加 --apply，没有写入任何文件")
        return 0, log, {"before": before, "criteria": criteria}

    backup = {src: text}
    created = []
    if os.path.isfile(dst):
        backup[dst] = dst_text
    try:
        # 先写目标、再改源：反过来的话，源被删掉而目标写失败 → 函数丢了
        # 空文件不要分隔符 —— 否则新文件第一行是空行（`function` 不在第一行，
        # 不影响运行，但看起来像谁手滑删了东西）。
        sep = u"" if not dst_text else (
            u"\n" if dst_text.endswith(u"\n") else u"\n\n")
        io.open(dst, "w", encoding="utf-8", newline="").write(
            dst_text + sep + u"\n".join(block) + u"\n")
        if dst not in backup:
            created.append(dst)
        rest = lines[:s0] + lines[e0 + 1:]
        # 搬走后留下的连续空行压成一个
        out = []
        for ln in rest:
            if not ln.strip() and out and not out[-1].strip():
                continue
            out.append(ln)
        io.open(src, "w", encoding="utf-8", newline="").write(
            u"\n".join(out).rstrip(u"\n") + u"\n")
        say("apply", u"已写入 %s，并从 %s 删除定义" % (to, rel))

        after = _scan(root)
        src_now = io.open(src, "r", encoding="utf-8").read()
        dst_now = io.open(dst, "r", encoding="utf-8").read()
        ok_fun = after["functions"] == before["functions"]
        ok_diag = after["diagnostics"] <= before["diagnostics"]
        # 用同一个函数名解析器判断"定义在不在"，而不是另写一族正则：
        # 上一版这里又写了一条 `function\b[^\n]*?\b" + name`，
        # 与 `_function_block` 里那条同源，于是同一个坑踩了两次。
        def _defines(txt):
            return any(_function_name_of(ln) == name
                       for ln in txt.splitlines())
        ok_txt = (not _defines(src_now)) and _defines(dst_now)
        say("validate", u"函数 %d→%d ｜ 诊断 %d→%d ｜ 定义已迁移 %s"
            % (before["functions"], after["functions"],
               before["diagnostics"], after["diagnostics"],
               u"是" if ok_txt else u"否"))
        if ok_fun and ok_diag and ok_txt:
            say("validate", u"验收通过（3/3）")
            _rid = record_task(root, "move",
                               {"file": rel, "name": name, "to": to},
                               backup, created, scan=before,
                               elapsed_ms=(time.time() - t0) * 1000)
            if _rid:
                say("record", u"已记入 %s（可 undo）" % HISTORY_DIR)
            else:
                say("record", u"未能写任务记录 —— 本次无法 undo")
            return 0, log, {"before": before, "after": after,
                            "criteria": criteria, "verdict": "pass"}
        _restore(backup)
        for _c in created:
            try:
                os.remove(_c)
            except OSError:
                pass
        why = []
        if not ok_fun:
            why.append(u"函数数变了")
        if not ok_diag:
            why.append(u"诊断增加了")
        if not ok_txt:
            why.append(u"定义没搬干净")
        say("rollback", u"验收不通过（%s）—— 已恢复" % u"、".join(why))
        return 1, log, {"before": before, "criteria": criteria,
                        "verdict": "rollback"}
    except Exception as exc:
        _restore(backup)
        for _c in created:
            try:
                os.remove(_c)
            except OSError:
                pass
        say("rollback", u"异常 %r —— 已恢复" % (exc,))
        return 1, log, {"verdict": "error"}



# ---------------------------------------------------------------------------
# 批量任务（R390）：一次跑一串步骤，任一步失败整批回滚。
#
# 为什么放在这里而不是只放在 MCP 侧：真实重构很少只有一步。若批量只对 Agent
# 开放，人就得自己一步步敲，而那正是最容易留下"改了一半"的用法。
# ---------------------------------------------------------------------------

def _snapshot(root):
    """{path: 原文}，只收 .m。"""
    snap = {}
    for p in _iter_m_files(root):
        try:
            snap[p] = io.open(p, "r", encoding="utf-8",
                              errors="replace").read()
        except (IOError, OSError):
            continue
    return snap


def _restore_all(root, snap):
    """按快照恢复；**快照里没有的 .m 要删掉**（那是新提取出来的）。"""
    for p in _iter_m_files(root):
        if p not in snap:
            try:
                os.remove(p)
            except OSError:
                pass
    for p, text in snap.items():
        try:
            io.open(p, "w", encoding="utf-8", newline="").write(text)
        except (IOError, OSError):
            pass


def _run_step(root, step, apply_it):
    """按 step 里的 task 分派。返回 (rc, log)。"""
    task = (step.get("task") or "").strip()
    if task in ("rename", "rename-field"):
        rc, log, _info = task_rename(
            root, (step.get("old") or "").strip(),
            (step.get("new") or "").strip(), apply_it=apply_it,
            kind=("field" if task == "rename-field" else "ident"))
        return rc, log
    if task == "move":
        rc, log, _info = task_move(
            root, (step.get("file") or "").strip(),
            (step.get("name") or "").strip(),
            (step.get("to") or "").strip(), apply_it=apply_it)
        return rc, log
    if task == "extract":
        rng = (step.get("lines") or "").strip()
        rel = (step.get("file") or "").strip()
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", rng)
        if not rel or not m:
            return 2, [{"step": "error",
                        "msg": u"extract 需要 file 与 lines（形如 12-18）"}]
        rc, log, _info = task_extract(
            root, rel, int(m.group(1)), int(m.group(2)),
            (step.get("name") or "").strip(),
            _split_list(step.get("in")), _split_list(step.get("out")),
            apply_it=apply_it, auto=bool(step.get("auto")),
            to=((step.get("to") or "").strip() or None))
        return rc, log
    return 2, [{"step": "error",
                "msg": u"task 只支持 rename / rename-field / extract / move"}]



#: 可被后续步骤引用的字段（都是"参数"，不是执行结果 —— 参数在跑之前就已知，
#: 引用它们不需要解析输出，也就不会因为某步的解析差异而错位）。
REF_KEYS = ("old", "new", "name", "file", "to")

_RE_REF = re.compile(u"\$\{(\d+|prev)\.([a-z_]+)\}")


def resolve_step_refs(step, prior):
    """把 `${1.new}` / `${prev.new}` 换成前面步骤的**参数值**。

    为什么只允许引用参数：引用"执行结果"需要每个任务都返回结构化产出，
    而现在的返回是给人看的日志。参数在动手前就确定，替换是确定的 —— 这也让
    "整批推演"与"真执行"用同一套替换逻辑（副本推演时结果本来就不同）。
    """
    out = {}
    for k, v in step.items():
        if not isinstance(v, str):
            out[k] = v
            continue

        def sub(m):
            idx, key = m.group(1), m.group(2)
            if key not in REF_KEYS:
                raise ValueError(u"引用里的字段只能是 %s，收到 `%s`"
                                 % (u" / ".join(REF_KEYS), key))
            if idx == u"prev":
                if not prior:
                    raise ValueError(u"`${prev.%s}` 用在了第 1 步" % key)
                src = prior[-1]
                label = u"上一步"
            else:
                n = int(idx)
                if n < 1 or n > len(prior):
                    raise ValueError(u"`${%s.%s}` 指向第 %s 步，但此前只跑了 %d 步"
                                     % (idx, key, idx, len(prior)))
                src = prior[n - 1]
                label = u"第 %s 步" % idx
            if key not in src or src[key] in (None, u""):
                raise ValueError(u"%s没有 `%s` 可引用" % (label, key))
            return str(src[key])

        out[k] = _RE_REF.sub(sub, v)
    return out


def resolve_all_steps(steps):
    """**动手之前**把整批的引用一次解析完。返回 (resolved, err)。

    为什么不能在循环里边跑边解析：第 2 步引用写错时，第 1 步已经落盘了 ——
    于是"引用错误"这种纯参数问题也会留下改了一半的工程。
    引用只依赖前面步骤的**参数**，所以在开始写盘之前就能全部算完。
    """
    resolved = []
    for i, st in enumerate(steps):
        if not isinstance(st, dict):
            return None, u"第 %d 步不是对象" % (i + 1)
        try:
            resolved.append(resolve_step_refs(st, resolved))
        except ValueError as exc:
            return None, u"第 %d 步引用无效：%s" % (i + 1, exc)
    return resolved, None


def task_batch(root, steps, apply_it=False):
    """多步事务。返回 (rc, log)，log 里每步前有一条分隔行。"""
    log = []

    def say(step, msg):
        log.append({"step": step, "msg": msg})

    if not os.path.isdir(root):
        say("error", u"目录不存在：%s" % root)
        return 2, log
    if not isinstance(steps, (list, tuple)) or not steps:
        say("error", u"steps 必须是非空数组")
        return 2, log

    resolved, ref_err = resolve_all_steps(steps)
    if ref_err:
        # 一个字节都还没写 —— 引用错误是**参数**错误，不该产生任何副作用。
        say("error", ref_err)
        return 2, log

    if not apply_it:
        # **在副本上推演**：链式第二步依赖第一步的结果，逐步 dry-run 必然误报。
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp(prefix="batch_plan_")
        try:
            for p in _iter_m_files(root):
                rel = os.path.relpath(p, root)
                dst = os.path.join(tmp, rel)
                d = os.path.dirname(dst)
                if d and not os.path.isdir(d):
                    os.makedirs(d)
                shutil.copyfile(p, dst)
            rows = []
            for i, st2 in enumerate(resolved):
                rc, one = _run_step(tmp, st2, True)
                rows.append((i + 1, st2.get("task") or "?", rc, one))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        ok = all(r[2] == 0 for r in rows)
        say("plan", u"批量计划：%d 步，在**副本**上按顺序推演（工程未被修改）"
                    u"—— %s" % (len(rows), u"全部可执行" if ok else u"有步骤会失败"))
        for i, task, rc, one in rows:
            say("step", u"── 第 %d 步：%s %s" % (i, task, u"✓" if rc == 0 else u"✗"))
            log.extend(one)
        return (0 if ok else 1), log

    snap = _snapshot(root)
    done = 0
    #: 给这一批编个号：整批撤销靠它把 N 条记录认成一次。
    global _CURRENT_BATCH
    _CURRENT_BATCH = u"b" + time.strftime("%Y%m%d-%H%M%S")
    for i, st in enumerate(resolved):
        rc, one = _run_step(root, st, True)
        done = i + 1
        if rc != 0:
            _restore_all(root, snap)
            say("step", u"── 第 %d 步：%s ✗" % (i + 1, st.get("task") or "?"))
            log.extend(one)
            say("rollback", u"批量任务在第 %d 步失败，**已回滚全部 %d 步**"
                            u"（工程恢复到动手前）" % (i + 1, done))
            _CURRENT_BATCH = u""
            return 1, log
        say("step", u"── 第 %d 步：%s ✓" % (i + 1, st.get("task") or "?"))
        log.extend(one)
    say("validate", u"批量任务：%d 步全部通过" % len(steps))
    _CURRENT_BATCH = u""
    return 0, log


# ---------------------------------------------------------------------------
# 自证：一个真项目、一次成功改名、一次故意失败的回滚
# ---------------------------------------------------------------------------

GOOD_FILES = {
    "a.m": (u"function y = helper(x)\n"
            u"% 这里是注释，里面的 helper 不该被改\n"
            u"y = x + 1;\n"
            u"end\n"),
    "b.m": (u"function r = caller(v)\n"
            u"r = helper(v) + helper(v);\n"
            u"end\n"),
    "c.m": (u"function s = use_str()\n"
            u"s = 'helper';\n"
            u"end\n"),
}


def _make(files, d):
    for n, text in files.items():
        with io.open(os.path.join(d, n), "w", encoding="utf-8",
                     newline="") as fh:
            fh.write(text)


def selftest():
    import shutil
    import tempfile
    good = bad = 0

    def chk(cond, name, detail=""):
        if not cond:
            print("  [FAIL] %-46s %s" % (name, detail))
        return bool(cond)

    d = tempfile.mkdtemp(prefix="task_")
    try:
        _make(GOOD_FILES, d)
        sites = find_sites(d, "helper")
        # 注释里的 helper、字符串里的 'helper' 都不该命中
        if chk(len(sites) == 3, u"自证：只命中 3 处（定义 + 2 次调用）",
               u"实际 %d 处" % (len(sites),)):
            good += 1
        else:
            bad += 1

        rc, log, info = task_rename(d, "helper", "assist", apply_it=False)
        if chk(rc == 0 and info.get("sites") == 3,
               u"自证：dry-run 给出计划", u"rc=%r" % (rc,)):
            good += 1
        else:
            bad += 1
        raw = io.open(os.path.join(d, "a.m"), encoding="utf-8").read()
        if chk("helper" in raw, u"自证：dry-run 没有写盘"):
            good += 1
        else:
            bad += 1

        rc, log, info = task_rename(d, "helper", "assist", apply_it=True)
        if chk(rc == 0 and info.get("verdict") == "pass",
               u"自证：改名后 4 条验收全过",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
        a = io.open(os.path.join(d, "a.m"), encoding="utf-8").read()
        c = io.open(os.path.join(d, "c.m"), encoding="utf-8").read()
        if chk("assist" in a and u"% 这里是注释" in a,
               u"自证：定义被改，注释原样保留"):
            good += 1
        else:
            bad += 1
        if chk(u"'helper'" in c, u"自证：字符串里的名字没被误改"):
            good += 1
        else:
            bad += 1

        # --- 回滚之一：**只改了一半**（旧名字仍有残留）-------------------
        # 直接替换 `_apply_rename` 模拟"只处理第一个文件"。
        _mod = sys.modules[__name__]
        orig_apply = _mod._apply_rename

        def _partial(ss, old, new, backup=None):
            by = {}
            for s in ss:
                by.setdefault(s[0], []).append(s)
            first = sorted(by)[0]
            # 备份必须继续往调用方传，否则这个桩测的是"签名不匹配"，
            # 而不是"只改了一半"。
            return orig_apply(by[first], old, new, backup)

        _mod._apply_rename = _partial
        try:
            snap = dict((p, io.open(p, encoding="utf-8").read())
                        for p in [os.path.join(d, "b.m")])
            rc, log, info = task_rename(d, "assist", "helper2", apply_it=True)
        finally:
            _mod._apply_rename = orig_apply
        if chk(rc == 1 and info.get("verdict") == "rollback",
               u"自证：残留旧名字 → 判为不通过并回滚",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
        now = io.open(os.path.join(d, "b.m"), encoding="utf-8").read()
        if chk(now == snap[os.path.join(d, "b.m")],
               u"自证：回滚后文件逐字节等于改前"):
            good += 1
        else:
            bad += 1

        # --- 回滚之二：**分析器说函数数变了** -----------------------------
        calls = {"n": 0}
        real_scan = _mod._scan

        def _bad_scan(root):
            calls["n"] += 1
            base = real_scan(root)
            if calls["n"] == 2:
                base = dict(base)
                base["functions"] = base["functions"] + 1
            return base

        _mod._scan = _bad_scan
        try:
            # 用 `assist`（上一次成功后仍存在）—— 上一次回滚已经把
            # `helper2` 抹掉了，拿它试会得到"没有命中"，测不到这里想测的东西。
            rc, log, info = task_rename(d, "assist", "helper3", apply_it=True)
        finally:
            _mod._scan = real_scan
        if chk(rc == 1 and info.get("verdict") == "rollback",
               u"自证：函数数变了 → 判为不通过并回滚",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # ---- rename-field：只动 `.field`，不动同名变量，不动字符串 -------------
    d2 = tempfile.mkdtemp(prefix="taskf_")
    try:
        _make({
            "f1.m": (u"function y = f1()\n"
                     u"s.old = 1;\n"
                     u"old = 2;\n"
                     u"y = s.old;\n"
                     u"end\n"),
            "f2.m": (u"function r = f2(t)\n"
                     u"r = t.old + 1;\n"
                     u"end\n"),
            "f3.m": (u"function q = f3()\n"
                     u"q = 's.old';\n"
                     u"end\n"),
        }, d2)
        fsites = find_sites(d2, "old", kind="field")
        if chk(len(fsites) == 3, u"自证 field：只命中 3 处 `.old`",
               u"实际 %d 处" % (len(fsites),)):
            good += 1
        else:
            bad += 1
        rc, log, info = task_rename(d2, "old", "renamed", apply_it=True,
                                    kind="field")
        f1 = io.open(os.path.join(d2, "f1.m"), encoding="utf-8").read()
        f3 = io.open(os.path.join(d2, "f3.m"), encoding="utf-8").read()
        if chk(rc == 0 and info.get("verdict") == "pass",
               u"自证 field：逐条验收通过",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
        if chk(u"s.renamed" in f1 and u"\nold = 2;" in f1,
               u"自证 field：字段改名，同名变量不动"):
            good += 1
        else:
            bad += 1
        if chk(u"'s.old'" in f3, u"自证 field：字符串里的 `.old` 不动"):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d2, ignore_errors=True)

    # ---- extract：提成函数 -------------------------------------------------
    d3 = tempfile.mkdtemp(prefix="taskx_")
    try:
        src = (u"function y = mx(x)\n"
               u"  a = x + 1;\n"
               u"  b = a * 2;\n"
               u"  y = b;\n"
               u"end\n")
        _make({"mx.m": src}, d3)
        rc, log, info = task_extract(d3, "mx.m", 3, 4, "part",
                                     ["a"], ["y"], apply_it=False)
        now = io.open(os.path.join(d3, "mx.m"), encoding="utf-8").read()
        if chk(rc == 0 and now == src, u"自证 extract：dry-run 不写盘"):
            good += 1
        else:
            bad += 1
        rc, log, info = task_extract(d3, "mx.m", 3, 4, "part",
                                     ["a"], ["y"], apply_it=True)
        now = io.open(os.path.join(d3, "mx.m"), encoding="utf-8").read()
        ok = (rc == 0 and info.get("verdict") == "pass"
              and u"y = part(a);" in now
              and u"function y = part(a)" in now)
        if chk(ok, u"自证 extract：提取后调用点与新函数都在",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
        rc, log, info = task_extract(d3, "mx.m", 1, 2, "part",
                                     ["a"], ["y"], apply_it=False)
        if chk(rc == 1, u"自证 extract：重名在动手前被拒", u"rc=%r" % (rc,)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d3, ignore_errors=True)

    # ---- extract --auto：接口推断 -----------------------------------------
    d4 = tempfile.mkdtemp(prefix="taska_")
    try:
        src = (u"function y = ax(x)\n"
               u"  a = x + 1;\n"
               u"  b = a * 2;\n"
               u"  y = b;\n"
               u"end\n")
        _make({"ax.m": src}, d4)
        ins, outs = infer_interface(src, 3, 4)
        if chk(ins == ["a"] and outs == ["y"],
               u"自证 auto：推断 in=a out=y", u"实际 %r/%r" % (ins, outs)):
            good += 1
        else:
            bad += 1
        rc, log, info = task_extract(d4, "ax.m", 3, 4, "part", [], [],
                                     apply_it=True, auto=True)
        now = io.open(os.path.join(d4, "ax.m"), encoding="utf-8").read()
        ok = (rc == 0 and info.get("verdict") == "pass"
              and u"y = part(a);" in now)
        if chk(ok, u"自证 auto：推断结果直接可用",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d4, ignore_errors=True)

    # ---- extract --to：提到新文件 -----------------------------------------
    d5 = tempfile.mkdtemp(prefix="taskt_")
    try:
        src = (u"function y = tx(x)\n"
               u"  a = x + 1;\n"
               u"  b = a * 2;\n"
               u"  y = b;\n"
               u"end\n")
        _make({"tx.m": src}, d5)
        rc, log, info = task_extract(d5, "tx.m", 3, 4, "part",
                                     ["a"], ["y"], apply_it=True,
                                     to="part.m")
        p = os.path.join(d5, "part.m")
        ok = (rc == 0 and info.get("verdict") == "pass"
              and os.path.isfile(p))
        now = io.open(p, encoding="utf-8").read() if os.path.isfile(p) else u""
        ok = ok and (u"function y = part(a)" in now)
        if chk(ok, u"自证 --to：新文件已建且签名正确",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
        # 目标文件已存在时必须拒绝（不覆盖别人的函数）
        rc2, log2, info2 = task_extract(d5, "tx.m", 2, 2, "part2",
                                        ["x"], ["a"], apply_it=True,
                                        to="part.m")
        if chk(rc2 == 1 and u"拒绝覆盖" in u"".join(r["msg"] for r in log2),
               u"自证 --to：已存在则拒绝覆盖", u"rc=%r" % (rc2,)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d5, ignore_errors=True)

    # ---- move：跨文件搬函数 -----------------------------------------------
    d6 = tempfile.mkdtemp(prefix="taskm_")
    try:
        src = (u"function y = main2(x)\n"
               u"  y = helper2(x);\n"
               u"end\n"
               u"\n"
               u"function z = helper2(v)\n"
               u"  z = v * 2;\n"
               u"end\n")
        _make({"m2.m": src}, d6)
        lines = src.splitlines()
        # **块定位**：空缩进时"同缩进"判断最容易写错（第一版把 main2 的块
        # 一路延伸到了文件末尾，会把 helper2 一起搬走）。
        b1 = _function_block(lines, u"main2")
        b2 = _function_block(lines, u"helper2")
        if chk(b1 == (0, 2) and b2 == (4, 6),
               u"自证 move：两个函数的块边界正确", u"%r / %r" % (b1, b2)):
            good += 1
        else:
            bad += 1
        rc, log, info = task_move(d6, "m2.m", "helper2", "helper2.m",
                                  apply_it=True)
        a = io.open(os.path.join(d6, "m2.m"), encoding="utf-8").read()
        b = io.open(os.path.join(d6, "helper2.m"), encoding="utf-8").read()
        # 搬走的是**定义**，调用点必须留着 —— 第一版写成"名字不出现"，
        # 于是正确的实现被判成失败（`y = helper2(x);` 还在原文件里）。
        ok = (rc == 0 and info.get("verdict") == "pass"
              and _function_block(a.splitlines(), u"helper2") is None
              and u"y = helper2(x);" in a
              and b.startswith(u"function z = helper2"))
        if chk(ok, u"自证 move：定义搬走且新文件首行是 function",
               u"rc=%r verdict=%r" % (rc, info.get("verdict"))):
            good += 1
        else:
            bad += 1
        # 目标文件名与函数名不同 → 调用点会失效，必须拒绝
        rc2, log2, _ = task_move(d6, "m2.m", "main2", "util.m",
                                 apply_it=False)
        if chk(rc2 == 1, u"自证 move：目标名不匹配则拒绝", u"rc=%r" % (rc2,)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d6, ignore_errors=True)

    # ---- batch：多步事务 -------------------------------------------------
    d7 = tempfile.mkdtemp(prefix="taskb_")
    try:
        _make({"p1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n"),
               "p2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n")}, d7)
        steps = [{"task": "rename", "old": "aa", "new": "cc"},
                 {"task": "rename", "old": "cc", "new": "dd"}]
        rc, log = task_batch(d7, steps, apply_it=False)
        untouched = u"aa" in io.open(os.path.join(d7, "p1.m"),
                                     encoding="utf-8").read()
        if chk(rc == 0 and untouched,
               u"自证 batch：计划在副本上推演，工程不动",
               u"rc=%r 未改=%s" % (rc, untouched)):
            good += 1
        else:
            bad += 1
        rc, log = task_batch(d7, steps, apply_it=True)
        now = io.open(os.path.join(d7, "p1.m"), encoding="utf-8").read()
        if chk(rc == 0 and u"dd" in now,
               u"自证 batch：两步都生效", u"rc=%r" % (rc,)):
            good += 1
        else:
            bad += 1
        # 第二步撞名 -> 整批回滚（第一步也要退回去）
        snap = io.open(os.path.join(d7, "p1.m"), encoding="utf-8").read()
        bad_steps = [{"task": "rename", "old": "dd", "new": "ee"},
                     {"task": "rename", "old": "ee", "new": "bb"}]
        rc2, log2 = task_batch(d7, bad_steps, apply_it=True)
        back = io.open(os.path.join(d7, "p1.m"), encoding="utf-8").read()
        if chk(rc2 == 1 and back == snap,
               u"自证 batch：失败整批回滚", u"rc=%r 复原=%s" % (rc2, back == snap)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d7, ignore_errors=True)

    # ---- batch 引用：${n.new} / ${prev.new} / 越界不动文件 -----------------
    d8 = tempfile.mkdtemp(prefix="taskr_")
    try:
        _make({"r1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n"),
               "r2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n")}, d8)
        rc, log = task_batch(d8, [
            {"task": "rename", "old": "aa", "new": "cc"},
            {"task": "rename", "old": "${prev.new}", "new": "dd"}],
            apply_it=True)
        now = io.open(os.path.join(d8, "r1.m"), encoding="utf-8").read()
        if chk(rc == 0 and u"dd" in now,
               u"自证 引用：${prev.new} 串起来", u"rc=%r" % (rc,)):
            good += 1
        else:
            bad += 1
        # 越界引用：**一个字节都不能改**
        snap = now
        rc2, log2 = task_batch(d8, [
            {"task": "rename", "old": "dd", "new": "ee"},
            {"task": "rename", "old": "${9.new}", "new": "ff"}],
            apply_it=True)
        back = io.open(os.path.join(d8, "r1.m"), encoding="utf-8").read()
        msg = u"".join(r["msg"] for r in log2)
        if chk(rc2 == 2 and back == snap and u"引用无效" in msg,
               u"自证 引用：越界时不动任何文件", u"rc=%r 复原=%s" % (rc2, back == snap)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d8, ignore_errors=True)

    # ---- undo：成功之后能反悔 -------------------------------------------
    d9 = tempfile.mkdtemp(prefix="tasku_")
    try:
        _make({"u1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n"),
               "u2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n")}, d9)
        orig1 = io.open(os.path.join(d9, "u1.m"), encoding="utf-8").read()
        rc, log, info = task_rename(d9, "aa", "cc", apply_it=True)
        changed = io.open(os.path.join(d9, "u1.m"), encoding="utf-8").read()
        rc2, log2, info2 = task_undo(d9, apply_it=True)
        back = io.open(os.path.join(d9, "u1.m"), encoding="utf-8").read()
        if chk(rc == 0 and u"cc" in changed and rc2 == 0 and back == orig1,
               u"自证 undo：改完能原样撤回",
               u"rc=%r/%r 复原=%s" % (rc, rc2, back == orig1)):
            good += 1
        else:
            bad += 1
        # 任务之后又改过文件 -> 必须拒绝（否则会覆盖那些改动）
        rc, log, info = task_rename(d9, "aa", "dd", apply_it=True)
        with io.open(os.path.join(d9, "u1.m"), "a", encoding="utf-8") as fh:
            fh.write(u"% 手工改的一行\n")
        tail_before = io.open(os.path.join(d9, "u1.m"), encoding="utf-8").read()
        rc3, log3, info3 = task_undo(d9, apply_it=True)
        tail_after = io.open(os.path.join(d9, "u1.m"), encoding="utf-8").read()
        msgs = u"".join(r["msg"] for r in log3)
        if chk(rc3 == 1 and info3.get("verdict") == "conflict"
               and tail_before == tail_after and u"被改过" in msgs,
               u"自证 undo：任务后改过文件则拒绝",
               u"rc=%r verdict=%r" % (rc3, info3.get("verdict"))):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d9, ignore_errors=True)

    # ---- undo 列表与按 id 撤销 -------------------------------------------
    d10 = tempfile.mkdtemp(prefix="taskl_")
    try:
        _make({"v1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n")}, d10)
        orig = io.open(os.path.join(d10, "v1.m"), encoding="utf-8").read()
        task_rename(d10, "aa", "bb", apply_it=True)
        task_rename(d10, "bb", "cc", apply_it=True)
        rows = list_tasks(d10)
        if chk(len(rows) == 2 and rows[0]["kind"] == "rename",
               u"自证 undo --list：两条记录，新的在前",
               u"rows=%r" % ([r["kind"] for r in rows],)):
            good += 1
        else:
            bad += 1
        # 乱序撤销（先撤较早那条）必须被拒 —— 否则会盖掉后一步的改动
        rc_x, log_x, info_x = task_undo(d10, apply_it=True,
                                        rec_id=rows[1]["id"])
        if chk(rc_x == 1 and info_x.get("verdict") == "conflict",
               u"自证 undo --id：乱序撤销被拒",
               u"rc=%r verdict=%r" % (rc_x, info_x.get("verdict"))):
            good += 1
        else:
            bad += 1
        # 按 id 倒序撤两次 -> 回到最初
        rc_a, _la, _ia = task_undo(d10, apply_it=True, rec_id=rows[0]["id"])
        rc_b, _lb, _ib = task_undo(d10, apply_it=True, rec_id=rows[1]["id"])
        back = io.open(os.path.join(d10, "v1.m"), encoding="utf-8").read()
        if chk(rc_a == 0 and rc_b == 0 and back == orig,
               u"自证 undo --id：倒序撤干净",
               u"rc=%r/%r 复原=%s" % (rc_a, rc_b, back == orig)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d10, ignore_errors=True)

    # ---- 整批撤销：一批要么全撤、要么全不动 -----------------------------
    d11 = tempfile.mkdtemp(prefix="taskb2_")
    try:
        _make({"w1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n"),
               "w2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n")}, d11)
        o1 = io.open(os.path.join(d11, "w1.m"), encoding="utf-8").read()
        o2 = io.open(os.path.join(d11, "w2.m"), encoding="utf-8").read()
        rc, _lg = task_batch(d11, [
            {"task": "rename", "old": "aa", "new": "cc"},
            {"task": "rename", "old": "bb", "new": "dd"}], apply_it=True)
        rc_u, log_u, info_u = task_undo(d11, apply_it=True, whole_batch=True)
        b1 = io.open(os.path.join(d11, "w1.m"), encoding="utf-8").read()
        b2 = io.open(os.path.join(d11, "w2.m"), encoding="utf-8").read()
        if chk(rc == 0 and rc_u == 0 and b1 == o1 and b2 == o2,
               u"自证 整批撤销：两个文件都回到原样",
               u"rc=%r/%r 复原=%s/%s" % (rc, rc_u, b1 == o1, b2 == o2)):
            good += 1
        else:
            bad += 1

        # 一个文件被改过 -> 整批拒绝，**另一个文件也不能动**
        _make({"w1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n"),
               "w2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n")}, d11)
        task_batch(d11, [{"task": "rename", "old": "aa", "new": "cc"},
                         {"task": "rename", "old": "bb", "new": "dd"}],
                   apply_it=True)
        with io.open(os.path.join(d11, "w1.m"), "a", encoding="utf-8") as fh:
            fh.write(u"% 手工改的\n")
        s1 = io.open(os.path.join(d11, "w1.m"), encoding="utf-8").read()
        s2 = io.open(os.path.join(d11, "w2.m"), encoding="utf-8").read()
        rc_c, _lc, info_c = task_undo(d11, apply_it=True, whole_batch=True)
        n1 = io.open(os.path.join(d11, "w1.m"), encoding="utf-8").read()
        n2 = io.open(os.path.join(d11, "w2.m"), encoding="utf-8").read()
        if chk(rc_c == 1 and info_c.get("verdict") == "conflict"
               and n1 == s1 and n2 == s2,
               u"自证 整批撤销：一个冲突则整批不动",
               u"rc=%r 未动=%s/%s" % (rc_c, n1 == s1, n2 == s2)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d11, ignore_errors=True)

    # ---- 撤销后的验收：结构必须回到任务前 -------------------------------
    d12 = tempfile.mkdtemp(prefix="taskv_")
    try:
        _make({"x1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n"),
               "x2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n")}, d12)
        task_rename(d12, "aa", "cc", apply_it=True)
        rc_v, log_v, info_v = task_undo(d12, apply_it=True)
        msgs = u"".join(r["msg"] for r in log_v)
        if chk(rc_v == 0 and u"撤销验收通过（3/3）" in msgs,
               u"自证 撤销验收：结构回到任务前",
               u"rc=%r msg=%r" % (rc_v, msgs[-40:])):
            good += 1
        else:
            bad += 1

        # 把记录里的目标改坏 -> 必须判不通过，并**退回撤销前的状态**
        task_rename(d12, "aa", "dd", apply_it=True)
        recs = [n for n in os.listdir(os.path.join(d12, HISTORY_DIR))
                if n.endswith(".json")]
        target = os.path.join(d12, HISTORY_DIR, sorted(recs)[-1])
        data = json.loads(io.open(target, encoding="utf-8").read())
        data["scan"] = {"functions": 99, "edges": 99, "diagnostics": 0}
        io.open(target, "w", encoding="utf-8", newline="").write(
            json.dumps(data, ensure_ascii=False, indent=1))
        before_v = io.open(os.path.join(d12, "x1.m"), encoding="utf-8").read()
        rc_w, log_w, info_w = task_undo(d12, apply_it=True)
        after_v = io.open(os.path.join(d12, "x1.m"), encoding="utf-8").read()
        _msgs_w = u"".join(r["msg"] for r in log_w)
        if chk(rc_w == 1 and info_w.get("verdict") == "verify_failed"
               and before_v == after_v and u"可能的原因" in _msgs_w,
               u"自证 撤销验收：不通过则退回撤销前（并说明原因）",
               u"rc=%r verdict=%r" % (rc_w, info_w.get("verdict"))):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d12, ignore_errors=True)

    # ---- 记录裁剪：先删已撤销的 -----------------------------------------
    d13 = tempfile.mkdtemp(prefix="taskp_")
    try:
        hd = os.path.join(d13, HISTORY_DIR)
        if not os.path.isdir(hd):
            os.makedirs(hd)

        def _fake(i, undone):
            rid = "20261020-0000%02d-000" % i
            io.open(os.path.join(hd, rid + ".json"), "w",
                    encoding="utf-8", newline="").write(json.dumps({
                        "id": rid, "kind": "rename", "when": "x",
                        "undone": undone, "files": [], "created": [],
                        "params": {}, "batch": "", "scan": {}}))

        for i in range(30):
            _fake(i, i < 10)          # 前 10 条已撤销
        info = prune_tasks(d13, 25, apply_it=True)
        left = len(os.listdir(hd))
        if chk(info["removed_undone"] == 5 and info["removed_live"] == 0
               and left == 25,
               u"自证 prune：先删已撤销的，不动还能撤的",
               u"info=%r left=%d" % (info, left)):
            good += 1
        else:
            bad += 1

        # 已撤销的删光仍超限 -> 只能删最旧的"能撤"记录，且要报出数量
        for n in list(os.listdir(hd)):
            os.remove(os.path.join(hd, n))
        for i in range(30):
            _fake(i, False)
        info2 = prune_tasks(d13, 25, apply_it=False)
        if chk(info2["removed_live"] == 5
               and len(os.listdir(hd)) == 30,
               u"自证 prune：计划不删文件、且报出会丢掉的撤销能力",
               u"info=%r" % (info2,)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d13, ignore_errors=True)

    # ---- 记录里的原文：压缩存、能原样取回 -------------------------------
    d14 = tempfile.mkdtemp(prefix="taskz_")
    try:
        _make({"z1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n")}, d14)
        orig = io.open(os.path.join(d14, "z1.m"), encoding="utf-8").read()
        task_rename(d14, "aa", "bb", apply_it=True)
        hd = os.path.join(d14, HISTORY_DIR)
        name = sorted(os.listdir(hd))[-1]
        rec = json.loads(io.open(os.path.join(hd, name),
                                 encoding="utf-8").read())
        f = (rec.get("files") or [{}])[0]
        packed_ok = ("before_z" in f) and ("before" not in f)
        back = _unpack_text(f)
        if chk(packed_ok and back == orig,
               u"自证 记录：原文压缩存、取回一致",
               u"packed=%s 一致=%s" % (packed_ok, back == orig)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d14, ignore_errors=True)

    # ---- 撤销前的 diff 预览 ---------------------------------------------
    d15 = tempfile.mkdtemp(prefix="taskd_")
    try:
        _make({"d1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n")}, d15)
        task_rename(d15, "aa", "bb", apply_it=True)
        rc_d, log_d, info_d = task_undo(d15, apply_it=False, show_diff=True)
        text_d = u"\n".join(r["msg"] for r in log_d if r["step"] == "diff")
        ok_d = (rc_d == 0 and u"-function y = bb(x)" in text_d
                and u"+function y = aa(x)" in text_d)
        if chk(ok_d, u"自证 diff：撤销前能看到将被改回的内容",
               u"rc=%r 片段=%r" % (rc_d, text_d[:60])):
            good += 1
        else:
            bad += 1
        # 记录里带了 git head 字段（拿不到时为空串，键必须在）
        hd = os.path.join(d15, HISTORY_DIR)
        rec = json.loads(io.open(os.path.join(hd, sorted(os.listdir(hd))[-1]),
                                 encoding="utf-8").read())
        if chk("git_head" in rec, u"自证 记录：带 git_head 字段"):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d15, ignore_errors=True)

    # ---- diff 预览要带"撤销后的内容"（编辑器并排视图靠它）-----------------
    d16 = tempfile.mkdtemp(prefix="taskpv_")
    try:
        _make({"p1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n")}, d16)
        task_rename(d16, "aa", "bb", apply_it=True)
        rc_p, _lp, info_p = task_undo(d16, apply_it=False, show_diff=True)
        pvs = (info_p or {}).get("previews") or []
        ok_p = (rc_p == 0 and len(pvs) == 1
                and u"aa" in pvs[0].get("before", "")
                and pvs[0].get("path"))
        if chk(ok_p, u"自证 diff 预览：带撤销后的内容（可直接开并排视图）",
               u"previews=%r" % (pvs[:1],)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d16, ignore_errors=True)

    # ---- 回滚留痕要带原因；stats 要能按类型聚合 -------------------------
    d17 = tempfile.mkdtemp(prefix="tasks_")
    try:
        _make({"s1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n"),
               "s2.m": (u"function r = run(v)\n  r = aa(v);\nend\n")}, d17)
        # 一次成功
        task_rename(d17, "aa", "bb", apply_it=True)
        # 一次必然验收失败：改名成已存在的 run（调用边会变）
        _make({"s1.m": (u"function y = bb(x)\n  y = x + 1;\nend\n"),
               "s2.m": (u"function r = run(v)\n  r = bb(v);\nend\n")}, d17)
        rc_rb, _l, _i = task_rename(d17, "bb", "run", apply_it=True)

        rows = list_tasks(d17)
        kinds = set(r["kind"] for r in rows)
        rb = [r for r in rows if r.get("verdict") == "rollback"]
        if chk(rc_rb == 1 and rb and rb[0].get("reason"),
               u"自证 回滚记录：留下原因",
               u"rc=%r reasons=%r" % (rc_rb, [r.get("reason") for r in rb])):
            good += 1
        else:
            bad += 1

        stats = task_stats(d17)
        by = dict((r["kind"], r) for r in stats)
        ok_s = (u"rename" in by and by[u"rename"]["count"] >= 1
                and by[u"rename"]["p50_ms"] > 0)
        if chk(ok_s, u"自证 stats：按类型聚合出次数与中位耗时",
               u"stats=%r" % (stats[:2],)):
            good += 1
        else:
            bad += 1
    finally:
        shutil.rmtree(d17, ignore_errors=True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    sub = ap.add_subparsers(dest="cmd")
    rp = sub.add_parser("rename")
    rp.add_argument("--dir", default=".")
    rp.add_argument("--old", required=True)
    rp.add_argument("--new", required=True)
    rp.add_argument("--apply", action="store_true")
    rp.add_argument("--json", action="store_true")
    st = sub.add_parser("stats")
    st.add_argument("--dir", default=".")
    st.add_argument("--json", action="store_true")
    pp = sub.add_parser("prune")
    pp.add_argument("--dir", default=".")
    pp.add_argument("--keep", type=int, default=MAX_RECORDS)
    pp.add_argument("--apply", action="store_true")
    pp.add_argument("--json", action="store_true")
    up = sub.add_parser("undo")
    up.add_argument("--dir", default=".")
    up.add_argument("--list", action="store_true",
                    help="列出任务记录（新的在前）")
    up.add_argument("--id", default="", help="撤销指定的那一次")
    up.add_argument("--batch", action="store_true",
                    help="撤销最近一整批（batch 是一个事务）")
    up.add_argument("--diff", action="store_true",
                    help="计划模式下列出将要发生的改动（unified diff）")
    up.add_argument("--apply", action="store_true")
    up.add_argument("--json", action="store_true")
    bp = sub.add_parser("batch")
    bp.add_argument("--dir", default=".")
    bp.add_argument("--steps", required=True,
                    help="步骤文件（JSON：数组，或 {\"steps\": [...]}）")
    bp.add_argument("--apply", action="store_true")
    bp.add_argument("--json", action="store_true")
    mp = sub.add_parser("move")
    mp.add_argument("--dir", default=".")
    mp.add_argument("--file", required=True)
    mp.add_argument("--name", required=True)
    mp.add_argument("--to", required=True)
    mp.add_argument("--apply", action="store_true")
    mp.add_argument("--json", action="store_true")
    ep = sub.add_parser("extract")
    ep.add_argument("--dir", default=".")
    ep.add_argument("--file", required=True)
    ep.add_argument("--lines", required=True)
    ep.add_argument("--name", required=True)
    ep.add_argument("--in", dest="ins", default="")
    ep.add_argument("--out", dest="outs", default="")
    ep.add_argument("--auto", action="store_true")
    ep.add_argument("--to", default="")
    ep.add_argument("--apply", action="store_true")
    ep.add_argument("--json", action="store_true")
    fp = sub.add_parser("rename-field")
    fp.add_argument("--dir", default=".")
    fp.add_argument("--old", required=True)
    fp.add_argument("--new", required=True)
    fp.add_argument("--apply", action="store_true")
    fp.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    if args.help or (not args.selftest and not args.cmd):
        sys.stdout.write(__doc__)
        return 0
    if args.selftest:
        return selftest()

    if args.cmd == "stats":
        _rows = task_stats(os.path.abspath(args.dir))
        if args.json:
            print(json.dumps({"ok": True, "stats": _rows,
                              "rollback_reasons":
                                  rollback_reasons(os.path.abspath(args.dir))},
                             ensure_ascii=False, indent=2))
        elif not _rows:
            print("还没有任务记录（%s）" % HISTORY_DIR)
        else:
            print("%-14s %5s %8s %8s %8s %8s"
                  % ("类型", "次数", "回滚", "平均ms", "中位ms", "最大ms"))
            for r in _rows:
                print("%-14s %5d %8d %8d %8d %8d"
                      % (r["kind"], r["count"], r["rollback"],
                         r["avg_ms"], r["p50_ms"], r["max_ms"]))
            _rr = rollback_reasons(os.path.abspath(args.dir))
            if _rr:
                print("")
                print("回滚原因：")
                for r in _rr:
                    print("  %-22s %d 次" % (r["reason"], r["count"]))
        return 0

    if args.cmd == "prune":
        rc_info = prune_tasks(os.path.abspath(args.dir), args.keep,
                              apply_it=args.apply)
        if args.json:
            print(json.dumps(rc_info, ensure_ascii=False, indent=2))
        else:
            print("记录共 %d 条，上限 %d ｜ 将删：已撤销 %d、仍可撤销 %d ｜ 保留 %d"
                  % (rc_info["total"], args.keep,
                     rc_info["removed_undone"], rc_info["removed_live"],
                     rc_info["kept"]))
            if not args.apply and (rc_info["removed_undone"]
                                   or rc_info["removed_live"]):
                print("（未加 --apply，没有删任何文件）")
        return 0

    if args.cmd == "undo":
        _root = os.path.abspath(args.dir)
        if args.list:
            rows = list_tasks(_root)
            if args.json:
                print(json.dumps({"ok": True, "tasks": rows},
                                 ensure_ascii=False, indent=2))
            elif not rows:
                print("没有任务记录（%s）" % HISTORY_DIR)
            else:
                for r in rows:
                    print("%-18s %-13s %s  %s  文件%d/新建%d"
                          % (r["id"], r["kind"], r["when"],
                             u"已撤销" if r["undone"] else u"可撤销",
                             r["files"], r["created"]))
            return 0
        rc, log, info = task_undo(_root, apply_it=args.apply,
                                  rec_id=(args.id or None),
                                  whole_batch=bool(args.batch),
                                  show_diff=bool(args.diff))
        if args.json:
            print(json.dumps({"ok": rc == 0, "log": log,
                              "info": info},
                             ensure_ascii=False, indent=2))
        else:
            for row in log:
                print("[%-9s] %s" % (row["step"], row["msg"]))
        return rc

    if args.cmd == "batch":
        raw = io.open(args.steps, "r", encoding="utf-8").read()
        data = json.loads(raw)
        steps = data.get("steps") if isinstance(data, dict) else data
        rc, log = task_batch(os.path.abspath(args.dir), steps or [],
                             apply_it=args.apply)
        if args.json:
            print(json.dumps({"ok": rc == 0, "log": log},
                             ensure_ascii=False, indent=2))
        else:
            for row in log:
                print("[%-9s] %s" % (row["step"], row["msg"]))
        return rc

    if args.cmd == "move":
        rc, log, info = task_move(os.path.abspath(args.dir), args.file,
                                  args.name, args.to, args.apply)
        if args.json:
            print(json.dumps({"ok": rc == 0, "log": log, "info": info},
                             ensure_ascii=False, indent=2))
        else:
            for row in log:
                print("[%-9s] %s" % (row["step"], row["msg"]))
        return rc

    if args.cmd == "extract":
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", args.lines or u"")
        if not m:
            print("--lines 需要形如 12-18")
            return 2
        rc, log, info = task_extract(os.path.abspath(args.dir), args.file,
                                     int(m.group(1)), int(m.group(2)),
                                     args.name, _split_list(args.ins),
                                     _split_list(args.outs), args.apply,
                                     auto=args.auto,
                                     to=(args.to or None))
        if args.json:
            print(json.dumps({"ok": rc == 0, "log": log, "info": info},
                             ensure_ascii=False, indent=2))
        else:
            for row in log:
                print("[%-9s] %s" % (row["step"], row["msg"]))
        return rc

    if args.cmd in ("rename", "rename-field"):
        rc, log, info = task_rename(os.path.abspath(args.dir), args.old,
                                    args.new, args.apply, args.json,
                                    kind=("field" if args.cmd == "rename-field"
                                          else "ident"))
        if args.json:
            print(json.dumps({"ok": rc == 0, "log": log, "info": info},
                             ensure_ascii=False, indent=2))
        else:
            for row in log:
                print("[%-9s] %s" % (row["step"], row["msg"]))
        return rc
    sys.stdout.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
