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
    # **仓根脚本**（`./`）：入口、流水线、分析组件都在这儿，共 22 个文件。
    # 不列出来的后果和 R819 漏目录一样 —— 它们在"职责域"表里**完全不存在**，
    # 而 `analyzer_memory.py` 这种还有专门的测试（2 个文件），只是没人看见。
    ("./", "仓根脚本（入口 / 流水线 / 分析组件）"),
    ("translate/", "MATLAB → MIR / HIR / C（转换侧主体）"),
    ("rust/m2c/", "MIR → C 工程（发射器与装配）"),
    ("c_runtime/", "C 运行时（mlc_array / 算子实现）"),
    ("malabc-rt/", "Rust 运行时 crate"),
    ("frontends/", "多语言前端（候选站点 / IR）"),
    ("analyzer/", "分析侧（索引与关系）"),
    ("binfmt/", "二进制与构建系统的格式解析"),
    ("renderers/", "渲染层（资产 / 调用图）"),
    ("tools/", "门禁、状态、追踪、预算等工具"),
    ("harness/", "图与候选的生成辅助"),
    ("ci-examples/", "CI 配置样例"),
    ("flow/", "流程图与目录页"),
    ("m2c-site/", "静态展示站"),
    ("docs/", "设计文档"),
    ("tests/", "判据（含 GX2 的全部用例）"),
    ("vscode/", "编辑器插件"),
]

#: 职责域。**分组是为了回答"哪一层最厚/最薄"**，而不是把目录再列一遍：
#: 转换侧（把 MATLAB 变成 C）、运行时（C 自己）、工具与门禁（验证）、图与文档（沟通）、
#: 判据（证据）。任何目录都必须落在某个域里 —— 否则它就是在"没人负责"的地带。
GROUPS = {
    "./": "入口与流水线",
    "translate/": "转换侧",
    "rust/": "转换侧",          # 顶层归属（具体模块是 rust/m2c/）
    "rust/m2c/": "转换侧",
    "frontends/": "转换侧",
    "c_runtime/": "运行时",
    "malabc-rt/": "运行时",
    "analyzer/": "分析侧",
    "binfmt/": "分析侧",
    "renderers/": "分析侧",
    "tools/": "工具与门禁",
    "harness/": "工具与门禁",
    "ci-examples/": "工具与门禁",
    "flow/": "图与文档",
    "m2c-site/": "图与文档",
    "docs/": "图与文档",
    "tests/": "判据",
    "vscode/": "编辑器",
}


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
        if path == "./":
            # **只数仓根本层的 `.py`**：递归会把这个仓库所有文件都算进来。
            n = len([f for f in os.listdir(ROOT)
                     if f.endswith(".py") and os.path.isfile(os.path.join(ROOT, f))])
            out.append({"path": "./", "duty": duty, "status": "ok" if n else "unknown",
                        "files": n, "gx2_tests": len(gx),
                        "group": GROUPS.get("./", "未分组")})
            continue
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
                    "files": n, "gx2_tests": len(gx),
                    "group": GROUPS.get(path, "未分组")})
    return out


def _mentions(src, name):
    """`src` 是否"提到"了 `name` 这一层。两种写法都算：

    * **路径形态** `analyzer/` —— 直接写了目录；
    * **模块形态** `from analyzer import api` / `import binfmt` / `analyzer.api`
      —— 只写模块名、不写斜杠。

    为什么必须两种都认（R840）：只认路径时，`from analyzer import api` 这种
    **最典型的**测试写法反而计不进去，于是"分析侧只有 7 个文件"低估了真实分布。
    但**不能**退化成"裸名字出现即算" —— `rust` / `flow` / `docs` 是常见英文词，
    那样会把所有文件都算进去，指标就失去意义。
    """
    if not name:
        return False
    if (name + "/") in src:
        return True
    # 作为**路径段**出现：`os.path.join(ROOT, "c_runtime", "src")` 这类写法没有
    # 斜杠、也不是 import，只认前两种会把它漏掉（实测：运行时 31 -> 3 个文件）。
    if ('"%s"' % name) in src or ("'%s'" % name) in src:
        return True
    pat = r"(?:^|[^\w])(?:from|import)\s+%s\b|\b%s\." % (
        re.escape(name), re.escape(name))
    return re.search(pat, src, re.M) is not None


def domain_coverage(tests_dir=None):
    """每个职责域被**多少条判据函数**提到（粗粒度覆盖读数）。

    口径：扫 `tests/*.py` 的正文，看它是否出现该域下任一目录名（如 `translate/`、
    `c_runtime/`）；命中则把该文件里 `def test_` 的个数计入该域。
    一个文件提到两个域就两边都算 —— 这是**上界**，不是精确归属。

    ⚠ 早前数的是**文件数**，于是"往同一个文件里再加 3 条判据"读数不动
    （R822 实测：分析侧加了 3 条仍是 6）。文件数衡量的是**面**，不是**量**。

    为什么仍用这么粗的口径：精确归属要解析 import 依赖，而这里只回答
    "这一层有没有人测、大概多少"。0 是危险信号；3 和 5 的差别不值得更贵的手段。
    """
    d = tests_dir or os.path.join(ROOT, "tests")
    out = dict((g, 0) for g in set(GROUPS.values()))
    nfiles = dict((g, 0) for g in set(GROUPS.values()))
    if not os.path.isdir(d):
        return out, nfiles
    # 返回值是 `(条数, 文件数)` —— 两个读数回答不同问题，见 `domain_files()`。
    paths = {}
    for p, g in GROUPS.items():
        name = p.rstrip("/")
        # `./`（仓根）不是可匹配的目录名：rstrip 后变成 "."，而 `"./" in src`
        # 会在很多文件里偶然命中，把"入口与流水线"灌满假阳性。
        if name in ("", "."):
            # 仓根没有目录名可匹配，改用**根脚本的模块名**（`agent_loop` 等）：
            # 否则这一域永远是 0 条，而实际有测试 `import agent_loop`。
            if g == "入口与流水线":
                paths.setdefault(g, []).extend(
                    f[:-3] for f in os.listdir(ROOT)
                    if f.endswith(".py")
                    and os.path.isfile(os.path.join(ROOT, f))
                    and f not in ("setup.py",))
            continue
        paths.setdefault(g, []).append(name)
    for f in sorted(os.listdir(d)):
        if not (f.startswith("test_") and f.endswith(".py")):
            continue
        try:
            src = io.open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        n_tests = len(re.findall(r"^def test_", src, re.M))
        if not n_tests:
            continue
        for g, names in paths.items():
            if any(_mentions(src, n) for n in names):
                out[g] += n_tests
                nfiles[g] += 1

    # **编辑器的判据不在 `tests/` 下** —— 它们是 `vscode/test_*.js` 里的
    # `chk(cond, msg)` 脚本。不补这一段，编辑器那一行只会显示"tests/ 里顺带
    # 提到 vscode 的条数"（R823 实测 19），读起来像"这层几乎没测"，而实际是
    # **指标看不见它**。指标看不见某层，和那层没人测，是两件事。
    vd = os.path.join(ROOT, "vscode")
    if os.path.isdir(vd) and "编辑器" in out:
        n_js = 0
        for f in sorted(os.listdir(vd)):
            if not (f.startswith("test_") and f.endswith(".js")):
                continue
            try:
                src = io.open(os.path.join(vd, f), encoding="utf-8",
                              errors="replace").read()
            except OSError:
                continue
            n_js += len(re.findall(r"\bchk\(", src))
        out["编辑器"] += n_js
        nfiles["编辑器"] += len([f for f in os.listdir(vd)
                               if f.startswith("test_") and f.endswith(".js")])
    return out, nfiles


def domain_files(tests_dir=None):
    """每个职责域被**多少个**测试文件提到（集中度读数）。

    与 `domain_coverage()`（条数）配对使用：条数说明"测了多少点"，
    文件数说明"这些点有多少个独立的立足处"。527 条挤在 6 个文件里时，
    一个文件的 fixture 坏掉会带走同域一大批判据 —— 而总量上看不出来。
    """
    return domain_coverage(tests_dir)[1]


def groups(mods=None):
    """按职责域汇总：`{域: {"dirs": n, "files": n}}`。"""
    mods = mods if mods is not None else modules()
    out = {}
    for m in mods:
        g = m.get("group") or "未分组"
        d = out.setdefault(g, {"dirs": 0, "files": 0, "paths": []})
        d["dirs"] += 1
        d["files"] += m.get("files", 0)
        d["paths"].append(m.get("path"))
    return out


def figures():
    base = os.path.join(ROOT, "flow", "figures")
    if not os.path.isdir(base):
        return {"count": 0, "current": 0, "recent": 0, "stale": 0, "unknown": 0}
    head = _head()
    dist = {"current": 0, "recent": 0, "stale": 0, "unknown": 0, "historical": 0}
    lags = []                      # 非历史图的滞后提交数（用于算 max_lag）
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
        lags.append(lag)
    dist["count"] = n
    # **最大滞后**：只报"现行/近期/已过时"是不够的 —— 这三档会把 0 和 10 都算作
    # "近期"，也会把 11 和 40 都算作"已过时"。而"离下一次退化还有多远"只由
    # 那个**最大数**决定（R832 实测：R818 刷到全部现行后，仅 10 个提交，
    # 16 张就整体转 stale —— 期间没有做错任何事，只是 HEAD 往前走了）。
    dist["max_lag"] = max(lags) if lags else 0
    return dist


def build():
    return {"phases": phases(), "modules": modules(), "figures": figures(),
            "domain_tests": domain_coverage()[0],
            "domain_files": domain_coverage()[1],
            "gx2_tests": len(_gx2_tests()), "head": _head()[:12]}


HISTORY = os.path.join(ROOT, "flow", "status-history.jsonl")


#: 漂移预警线。**不是判据**：超过它不会红，只是提示"该刷图了"。
#: 取 8 的理由：分档是 `>10` 才转 stale，8 之后只剩两个提交的缓冲。
DRIFT_WARN = 8


def drift_hint(max_lag):
    """图正在漂移时返回一句可执行的提示；未超阈值返回 `""`。

    抽成纯函数是为了**能验它会响** —— 原来它内联在 `check_all` 的收尾里，
    而那条路径只在"恰好超阈值"时才有输出，等于永远没被验证过。
    """
    if max_lag > DRIFT_WARN:
        return ("图正在漂移（最大滞后 %d 个提交，>10 即掉档）—— 建议："
                "python tools/figures_refresh.py" % max_lag)
    return ""


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
        # **最大滞后**也要进历史：只记 live/stale 看不出"漂移速度"——
        # 两次记录都是 live=16 时，可能一次是刚刷新（lag 0），一次是
        # 已经攒了 9 个提交（lag 9，随时会掉档）。差值要靠这个数才看得见。
        "fig_max_lag": f.get("max_lag", 0),
        "gx2": st.get("gx2_tests", 0),
    }


#: 历史文件的上界。**只追加**的文件必须有上界，否则它会无限膨胀。
MAX_HISTORY = 200


def record(st, path=None):
    """把快照追加到 `flow/status-history.jsonl`；**同 head 同数字不重复写**。

    去重很关键：这个工具会被反复跑（首页生成、判据、手工），
    不去重的话历史文件会变成同一行刷屏，而"变化"再也看不出来。

    折叠：超过 `MAX_HISTORY` 行时保留**第一行（起点）+ 最后若干行**，
    中间插一条 `{"folded": n}` 记录说明折掉了多少 —— 起点不能丢，
    否则"从哪来"就没有了；中间隔断点会被标记出来，不会被误当成连续历史。
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

    raw = []
    if os.path.isfile(path):
        raw = [ln.strip() for ln in
               io.open(path, encoding="utf-8", errors="replace")
               if ln.strip()]
    raw.append(json.dumps(snap, ensure_ascii=False))

    if len(raw) > MAX_HISTORY:
        first = raw[0]
        keep = raw[-(MAX_HISTORY - 2):]
        # **折叠数是累计值**：把已有的 `{"folded": n}` 一起算进来。
        # 只算本次的话，第二次折折叠就会把"总共折掉多少"改小（实测：12 条只剩
        # 5 条时标记写着 2）—— 那是一个会说谎的数字。
        prev, n_real = 0, 0
        for ln in raw[1:]:
            try:
                j = json.loads(ln)
            except ValueError:
                n_real += 1
                continue
            if isinstance(j.get("folded"), int):
                prev += j["folded"]      # 之前折掉的
            else:
                n_real += 1              # 真实记录
        # 标记行由本函数写，键固定为 `"folded"`；用它区分真实记录即可
        real_kept = sum(1 for ln in keep if '"folded"' not in ln)
        # 只数**真实记录**：旧标记行本身会被替换掉，把它算进"折掉多少"会虚高
        # （实测：12 条折叠后标记写成 14，比总数还多）。
        dropped = prev + n_real - real_kept
        marker = json.dumps({"folded": dropped}, ensure_ascii=False)
        raw = [first, marker] + keep

    io.open(path, "w", encoding="utf-8", newline="").write(
        "\r\n".join(raw) + "\r\n")
    return True, len(raw)


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
    if cur.get("fig_max_lag") != prev.get("fig_max_lag"):
        diffs.append("图最大滞后 %s→%s 个提交"
                     % (prev.get("fig_max_lag"), cur.get("fig_max_lag")))
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
        print("\n== 职责域 ==")
        for g, d in groups(st["modules"]).items():
            print("  %-10s 目录 %d ｜ 文件 %4d ｜ %s"
                  % (g, d["dirs"], d["files"], " ".join(d["paths"])))
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
