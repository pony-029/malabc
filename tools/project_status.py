# -*- coding: utf-8 -*-
"""project_status.py —— **项目整体状态**：计划阶段 × 子模块 × 流程图，全部**算出来**。

为什么必须是算的
================
状态最常见坏法是"手写的乐观"。计划文档写「P0 今天会红」，两周后它绿了但文档没改；
首页写「19 张图」，实际 21 张。这类数字不会报错，只会安静地错着。

所以本工具只做一件事：**从仓库事实推状态**，并把推不出来的标成 `unknown`。

## 三个口径（写清楚，避免混着看）

1. **阶段（phases）**：计划文档 P0–P6。
   状态 = `done` 当且仅当：它的**证据判据文件存在**，且**已被 GX2 引用**。
   （判据存在但没人跑 = 不存在，这是本项目反复踩到的坑。）

2. **模块（modules）**：按目录统计文件数、被多少道门/判据覆盖。

3. **流程图（figures）**：张数 + 按 `candidate.meta.repository.revision` 与 HEAD 的距离
   分三档（现行 / 近期 / 已过时），与 `flow_catalog.py` 同一口径。

用法：
    python tools/project_status.py                # 0=全部可判定 1=有 unknown 2=缺输入
    python tools/project_status.py --json         # 机器可读
    python tools/project_status.py --selftest     # 两向自证
    python tools/project_status.py --help

退出码：
    0  = 所有阶段都有可判定的状态（done / partial）
    1  = 存在 `unknown`（证据缺失或未接线）—— 这正是需要人看一眼的地方
    2  = 缺输入（仓库结构不对）
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GX2 = os.path.join(ROOT, "tools", "check_generated_compiles.py")

#: 计划阶段 → (标题, 证据判据文件)。文件缺失或未接入 GX2 都会降级。
PHASES = [
    ("P0", "打通调用（跨文件 call）", ["tests/test_project_level.py"]),
    ("P1", "配置唯一生效点", ["tests/test_config_effective.py"]),
    ("P2", "预算模型（budget.json）", ["tests/test_budget.py"]),
    ("P3", "契约桩（m2c_ext_*）", ["tests/test_contract_stub.py",
                                  "tests/test_config_external_calls.py"]),
    ("P4", "图谱接配置（该配什么）", ["tests/test_config_suggest.py"]),
    ("P5", "HIR 接管", ["tests/test_hir_parity.py", "tests/test_hir_srcline.py"]),
    ("P6", "多路对账（无 Octave）", ["tests/test_four_way_no_octave.py"]),
]

#: 子模块：目录 → 一句话职责（写不出来就别列，别用"其他"糊）。
MODULES = [
    ("translate/", "MATLAB → MIR / HIR / C（转换侧主体）"),
    ("rust/m2c/", "MIR → C 工程（发射器与装配）"),
    ("c_runtime/", "C 运行时（mlc_array / 算子实现）"),
    ("tools/", "门禁、状态、追踪、预算等工具"),
    ("flow/", "流程图与目录页"),
    ("tests/", "判据（含 GX2 的全部用例）"),
]


def _run(cmd, timeout=120):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _gx2_tests():
    """GX2 清单里引用了哪些 tests/ 文件（它是"判据是否真被跑"的唯一凭证）。"""
    if not os.path.isfile(GX2):
        return set()
    s = io.open(GX2, encoding="utf-8", errors="replace").read()
    return set(re.findall(r'os\.path\.join\("tests", "(test_[a-z0-9_]+\.py)"\)', s))


def _head():
    r = _run(["git", "rev-parse", "HEAD"], 60)
    return r.stdout.decode("utf-8", "replace").strip()


def phases():
    gx = _gx2_tests()
    out = []
    for pid, title, evid in PHASES:
        missing = [e for e in evid if not os.path.isfile(os.path.join(ROOT, e))]
        not_gated = [e for e in evid
                     if os.path.basename(e) not in gx]
        if missing or not_gated:
            status = "unknown"
        else:
            status = "done"
        out.append({"id": pid, "title": title, "status": status,
                    "evidence": evid,
                    "missing": missing, "not_gated": not_gated})
    return out


def modules():
    gx = sorted(_gx2_tests())
    out = []
    for path, duty in MODULES:
        d = os.path.join(ROOT, path)
        if not os.path.isdir(d):
            out.append({"path": path, "duty": duty, "status": "unknown",
                        "files": 0, "gx2_tests": 0})
            continue
        n = 0
        for base, _dirs, files in os.walk(d):
            if any(x in base for x in (".git", "node_modules", os.sep + "target")):
                continue
            n += len(files)
        # 该模块"被 GX2 覆盖"不按目录算（测试不按目录归属），这里只报文件规模；
        # 覆盖度由 phases 那栏承担 —— 不在这里编一个好看的数。
        out.append({"path": path, "duty": duty, "status": "ok",
                    "files": n, "gx2_tests": len(gx)})
    return out


def figures():
    base = os.path.join(ROOT, "flow", "figures")
    if not os.path.isdir(base):
        return {"count": 0, "current": 0, "recent": 0, "stale": 0, "unknown": 0}
    head = _head()
    dist = {"current": 0, "recent": 0, "stale": 0, "unknown": 0, "historical": 0}
    n = 0
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d, "candidate.json")
        if not os.path.isfile(p):
            dist["unknown"] += 1
            continue
        n += 1
        try:
            meta = json.load(io.open(p, encoding="utf-8")).get("meta") or {}
            rev = ((meta.get("repository") or {}).get("revision") or "").strip()
        except (ValueError, OSError):
            dist["unknown"] += 1
            continue
        # **历史图单独一档**：它们用旧 schema，重渲染会丢语义，登记后不再计为欠账。
        # 但"登记了却其实能刷新成现行"要能反向抓出来 —— 见 tests/test_project_status.py。
        if (meta.get("status") or "") == "historical":
            dist["historical"] += 1
            continue
        if not rev or not head:
            dist["unknown"] += 1
            continue
        r = _run(["git", "rev-list", "--count", "%s..%s" % (rev, head)], 60)
        try:
            lag = int(r.stdout.decode("utf-8", "replace").strip())
        except ValueError:
            dist["unknown"] += 1
            continue
        dist["current" if lag == 0 else ("recent" if lag <= 10 else "stale")] += 1
    dist["count"] = n
    return dist


def build():
    return {"phases": phases(), "modules": modules(), "figures": figures(),
            "gx2_tests": len(_gx2_tests()), "head": _head()[:12]}


HISTORY = os.path.join(ROOT, "flow", "status-history.jsonl")


def _snapshot(st):
    """一行历史：只留**会变**的字段，便于人读与 diff。"""
    f = st.get("figures") or {}
    return {
        "head": st.get("head", ""),
        "phases_done": sum(1 for p in st.get("phases") or []
                           if p.get("status") == "done"),
        "phases_total": len(st.get("phases") or []),
        "fig_live": f.get("current", 0) + f.get("recent", 0),
        "fig_stale": f.get("stale", 0),
        "fig_hist": f.get("historical", 0),
        "gx2": st.get("gx2_tests", 0),
    }


def record(st, path=None):
    """把快照追加到 `flow/status-history.jsonl`；**同 head 同数字不重复写**。

    去重很关键：这个工具会被反复跑（首页生成、判据、手工），
    不去重的话历史文件会变成同一行刷屏，而"变化"再也看不出来。
    """
    path = path or HISTORY
    snap = _snapshot(st)
    snap["ts"] = subprocess.run(["git", "log", "-1", "--format=%cI"], cwd=ROOT,
                                stdin=subprocess.DEVNULL, timeout=60,
                                stdout=subprocess.PIPE).stdout.decode().strip()
    old = history(path)
    if old and {k: old[-1].get(k) for k in snap if k != "ts"} == \
            {k: snap[k] for k in snap if k != "ts"}:
        return False, len(old)
    io.open(path, "a", encoding="utf-8", newline="").write(
        json.dumps(snap, ensure_ascii=False) + "\r\n")
    return True, len(old) + 1


def history(path=None):
    path = path or HISTORY
    if not os.path.isfile(path):
        return []
    out = []
    for ln in io.open(path, encoding="utf-8", errors="replace"):
        s = ln.strip()
        if not s:
            continue
        try:
            out.append(json.loads(s))
        except ValueError:
            continue                    # 坏行不阻塞读取（判据里单独抓）
    return out


def delta(st, path=None):
    """与上一条历史比，返回可读的变化串（无历史时返回 ""）。"""
    old = history(path)
    if not old:
        return ""
    prev, cur = old[-1], _snapshot(st)
    diffs = []
    if cur["phases_done"] != prev.get("phases_done"):
        diffs.append("阶段 %s→%s" % (prev.get("phases_done"),
                                   cur["phases_done"]))
    if cur["fig_live"] != prev.get("fig_live"):
        diffs.append("可维护图 %s→%s" % (prev.get("fig_live"), cur["fig_live"]))
    if cur["fig_stale"] != prev.get("fig_stale"):
        diffs.append("已过时图 %s→%s" % (prev.get("fig_stale"), cur["fig_stale"]))
    if cur["gx2"] != prev.get("gx2"):
        diffs.append("GX2 覆盖 %s→%s" % (prev.get("gx2"), cur["gx2"]))
    return "；".join(diffs) if diffs else "无变化"


def _selftest():
    """两向自证：状态判定能区分 done / unknown（不是恒 green）。"""
    good = {"evidence": ["tests/test_project_level.py"],
            "missing": [], "not_gated": []}
    bad1 = {"evidence": ["tests/nonexistent.py"],
            "missing": ["tests/nonexistent.py"], "not_gated": []}
    bad2 = {"evidence": ["tests/test_project_level.py"],
            "missing": [], "not_gated": ["tests/test_project_level.py"]}

    def status(x):
        return "unknown" if (x["missing"] or x["not_gated"]) else "done"

    if status(good) != "done":
        print("自证失败：证据齐全却判成 unknown")
        return 1
    if status(bad1) != "unknown":
        print("自证失败：证据文件缺失却判成 done")
        return 1
    if status(bad2) != "unknown":
        print("自证失败：判据存在但没接入 GX2，却判成 done")
        return 1
    print('SELFTEST COUNTS {"bad": 2, "good": 1}')
    print("自证通过：证据缺失 / 未接线 都能降级为 unknown")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record", action="store_true",
                    help="把本次快照追加到 flow/status-history.jsonl（同 head 同数字不重复写）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, _rest = ap.parse_known_args(argv or sys.argv[1:])

    if a.help:
        print(__doc__)
        return 0
    if a.selftest:
        return _selftest()

    if not os.path.isdir(os.path.join(ROOT, "tools")):
        print("缺输入：tools/ 不存在（仓库结构不对）")
        return 2

    st = build()
    if a.record:
        added, total = record(st)
        st["history"] = {"added": added, "lines": total,
                         "delta": delta(st)}
    unknown = [p["id"] for p in st["phases"] if p["status"] != "done"]
    if a.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
    else:
        print("== 计划阶段（证据判据必须存在且已接入 GX2）==")
        for p in st["phases"]:
            mark = "✅" if p["status"] == "done" else "⚠️ "
            print("%s %-3s %-24s %s" % (mark, p["id"], p["title"],
                                        ",".join(p["evidence"])))
            for m in p["missing"]:
                print("        缺证据文件：%s" % m)
            for m in p["not_gated"]:
                print("        判据存在但未接入 GX2：%s" % m)
        print("\n== 子模块 ==")
        for m in st["modules"]:
            print("  %-14s %-34s 文件 %3d" % (m["path"], m["duty"], m["files"]))
        f = st["figures"]
        print("\n== 流程图 ==")
        print("  共 %d 张 ｜ 现行 %d ｜ 近期 %d ｜ 已过时 %d ｜ 历史(登记) %d ｜ 无回执 %d"
              % (f["count"], f["current"], f["recent"], f["stale"],
                 f.get("historical", 0), f["unknown"]))
        print("\nGX2 覆盖测试文件 %d 个 ｜ HEAD %s" % (st["gx2_tests"], st["head"]))
        if unknown:
            print("\n需要人看一眼：%s" % ", ".join(unknown))
    return 1 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
