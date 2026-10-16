#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""登记制护栏：C / Python / JavaScript / MATLAB 的**能力对等登记表**
（`docs/PARITY_MATLAB_C_PY.md`）必须与**实测**一致，且**两向**都响。

为什么需要这道门（R96 / Phase 1 / 槽 23）
========================================
最初的诉求是一句话：「C 与 Python 要达到 MATLAB 的效果 —— 共有的都适配、特有的
各自适配」。这句话在仓库里散成了十几处散文（`docs/matlabc_FEATURES.md` 的
「能力矩阵」、README 的段落、以及每轮复盘里的一句「XX 语言还没有 YY」），
而**没有任何一处**能回答「今天到底哪几格是空的、为什么空、那段散文还成立吗」。

本门把那句话变成**可核对的机器事实**：

  * `docs/PARITY_MATLAB_C_PY.md` 里有一张能力矩阵（人读）+ 一个 `<!-- PARITY v1 -->` 机器块；
  * 每个格子的「实测」由本门**现跑公开 CLI** 得到 —— 每语言在**合成夹具**上跑一次
    `--json --callgraph --browse`，按**文件隔离**读产物信号。
  * 实测**绝不**从登记表或源码字符串反推。反过来推的话，E2 永远不响，而
    「登记表说自己对了」是本仓栽过三次的空集 / 自指判据（R89 §4h-2、R95 装置两处）。

E1–E6（六个方向）
=================
  E1 **形状**：每个能力 4 个语言状态齐全、值域 `{yes,no,na}`、`evidence` 非空；
  E2 **两向对账**：登记 `yes` ⇔ 实测为真（登记未实现 ⇒ 红；实现未登记 ⇒ 红）；
  E3 **理由两向**：非 `yes` 的格必须写理由（>= 8 字符、非占位），
     `yes` 的格**不许**有理由（陈旧理由 ⇒ 红）；
  E4 **覆盖度两向**：本门的 `CAPABILITIES` 名单 ⇄ 块里的 `cap.<名>` 键集合；
  E5 **文档 ⇄ 机器块**，两半：人读表**逐格**一致（只改一处看不出来）；
     **并且**文档里从格子里算出来的字一律**现算再比** —— 合计行的
     `yes/no/na`、§3.3 缺口标题的格数、缺口表逐行求和、两份 README
     门表行里的记分牌。后半是 R101 补的：R99 把 `site_same_page_names`
     的 MATLAB 列从 `no` 改 `yes`，机器块与合计行改了，§3.3 标题
     （「16 格」）与它下面那张表（求和 15）**没跟着改**，而它们
     **一条判据都没有** ⇒ 同一份文档里同时挂着三个互相矛盾的数。
     这类数字的风险是**结构性**的（「改一处漏一处」），所以按结构堵：
     现算，不抄。
     ⚠ 为什么不新开一族编号：**`E7–E10` 已经留给槽 34**
     （`bin_parity_gate`，动态库能力对等并入 E 族，见
     `docs/EVOLVE_ROADMAP_360.md` 第 34 行）—— 抢编号会让那条槽的
     登记当场变错。判据签名因此仍是 `E1–E6`，那 8 处级联一处都不用动。
  E6 **未行使必须说出来**：夹具写不出来 / CLI 跑不起来 / 产物缺失 ⇒ 红，
     绝不静默当「对得上」；实测为空集也红（空集上「每格都对」恒真）。

⚠ `na` 不许用来掩盖「没实现」（本门最要紧的一条）
--------------------------------------------------
「不适用」与「还没做」在**产物**上长得一模一样，差别只在**语言形态**上。
所以本门把分辨力放在**门自己的探针名单**上：

  * 门里**有**该格的探针 ⇒ 该格只能填 `yes` / `no`；填 `na` ⇒ 红
    （**可测的能力不许被 `na` 吞掉** —— 这正是「用不适用掩盖没做」的形态）；
  * 门里**没有**该格的探针 ⇒ 该格才是 `na` 的候选，且理由必须说清
    「这个语言形态上为什么测不了」（例如 Python 没有汇编层）。

同一个道理的另一个方向：登记 `yes` / `no` 而门里**没有**探针 ⇒ 也红
（**无法核对的宣称不是宣称**）。

「加判据族、不加闸门」的第 6 个反例
----------------------------------
本门是**新闸门**（护栏 20 → 21，门 19 → 20），不是给既有门加判据族 —— 因为
「能力对等」此前**一格判据都没有**（缺口 > 0）。R85 的定论「缺口为 0 时加闸 =
churn」在这里不适用：这 64 个格子里有 16 个是 `no`，一个都不及格。

用法
====
    python tools/check_parity_registry.py            # 跑本门（默认）
    python tools/check_parity_registry.py --measure  # 只打印实测矩阵（人读用）
    python tools/check_parity_registry.py --selftest # 两向自证

退出码
======
  0 = E1–E6 全部通过
  1 = 登记表与实测不一致 / 形状不合 / 理由缺失或陈旧 / 夹具或 CLI 跑不起来
  2 = 缺输入（`docs/PARITY_MATLAB_C_PY.md` 不在，或机器块不可解析）
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROW_SIGNATURE = "E1–E6"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_REL = os.path.join("docs", "PARITY_MATLAB_C_PY.md")
BLOCK_OPEN = "<!-- PARITY v1 -->"
BLOCK_CLOSE = "<!-- /PARITY v1 -->"

CLI_REL = "matlabc.py"
CLI_TIMEOUT = 300          # 单语言一次夹具运行的上限（实测 ~0.5 s，留 600 倍余量）

LANGS = ("matlab", "c", "py", "js")
STATE_OK = ("yes", "no", "na")
MIN_REASON = 8             # 与 check_help_contract 的 N4 同一下限

# ---------------------------------------------------------------------------
# 门的分母：能力名单**写死在门里**，绝不从块里现推 ——
# 若由块推，「清单漏登记一个能力」就永远看不出来（R95 的 W7 同一条教训）。
# ---------------------------------------------------------------------------
CAPABILITIES = (
    "functions",
    "call_edges",
    "call_edges_cross_file",
    "call_edges_qualified",
    "call_edges_oneline_body",
    "deps_edges_json",
    "deps_site_page",
    "classes",
    "entities",
    "metrics_complexity",
    "unresolved_attribution",
    "callgraph_projection",
    "heuristics_channel",
    "asm_insights",
    "browse_site",
    "site_same_page_names",
)

# 每格的「怎么测的」（也进登记表的 `cap.<名>.evidence`，两处必须一致）。
EVIDENCE = {
    "functions": "`fn_basic`/`mintra` 里两个定义都出现在载荷 `files[].functions`",
    "call_edges": "`fn_basic`/`mintra` 至少一条非跨文件边进载荷 `edges`",
    "call_edges_cross_file": "callgraph 的 `cross_file.cross > 0`（MATLAB 走载荷 `edges[].cross_file`）",
    "call_edges_qualified": "`class_cls`/`Muse` 上至少一条边（属性 / 方法调用 `obj.m()`）",
    "call_edges_oneline_body": "`oneline` 上至少一条边（花括号单行函数体内的调用点）",
    "deps_edges_json": "载荷 `include_edges` 非空",
    "deps_site_page": "站点 `deps.html` 文本里出现依赖目标名",
    "classes": "载荷 `files[].classes` 非空",
    "entities": "载荷里出现实体 / 字段类键（`field_access` / `types` / `structs` …）",
    "metrics_complexity": "某个函数载荷 `complexity > 1`",
    "unresolved_attribution": "载荷 `unresolved` 非空（调了一个项目里不存在的名字）",
    "callgraph_projection": "`--callgraph` 产物存在且 `call_relations.edges_total` 是整数",
    "heuristics_channel": "载荷 `heuristics` 非空（无注释函数触发一条）",
    "asm_insights": "载荷出现 `asm` 键",
    "browse_site": "`--browse` 产出站点且含 HTML",
    "site_same_page_names": "站点同时有 `index.html` / `funcs.html` / `file/` / `dir/`",
}

# ---------------------------------------------------------------------------
# 夹具（合成、仓内生成、跑完即删）
# ---------------------------------------------------------------------------
FIXTURES = {
    "c": {
        "fn_basic.c": ("int c_helper(int v) {\n    return v + 1;\n}\n"
                       "int c_run(int x) {\n    return c_helper(x);\n}\n"),
        "oneline.c": "int c_oneline(int v) { return c_helper(v); }\n",
        "dep.h": "int bee(int v);\n",
        "dep.c": ('#include "dep.h"\n'
                  "int bee(int v) {\n    return v;\n}\n"),
        "call_dep.c": ('#include "dep.h"\n\n'
                       "int c_use(int x) {\n    return bee(x);\n}\n"),
        "ent.h": ("struct Pair { int a; int b; };\n"
                  "typedef struct Pair Pair;\n"
                  "enum Color { RED, GREEN };\n"),
        "metrics.c": ("int c_branchy(int x) {\n"
                      "    if (x > 0) {\n        return 1;\n    }\n"
                      "    if (x > 1) {\n        return 2;\n    }\n"
                      "    return 0;\n}\n"),
        "undoc.c": "int c_undoc(int v) {\n    return v;\n}\n",
        "unres.c": "int c_ext(int x) {\n    return c_nowhere(x);\n}\n",
    },
    "py": {
        "fn_basic.py": ("def p_helper(v):\n    return v + 1\n\n\n"
                        "def p_run(x):\n    return p_helper(x)\n"),
        "oneline.py": "def p_oneline(v): return p_helper(v)\n",
        "dep_mod.py": "def p_bee(v):\n    return v\n",
        "dep_from.py": ("from dep_mod import p_bee\n\n\n"
                        "def p_use(x):\n    return p_bee(x)\n"),
        "class_cls.py": ("class PHolder(object):\n"
                         "    def __init__(self, v):\n        self.v = v\n\n"
                         "    def get(self):\n        return self.v\n\n\n"
                         "def p_make(x):\n    h = PHolder(x)\n"
                         "    return h.get()\n"),
        "metrics.py": ("def p_branchy(x):\n    if x > 0:\n        return 1\n"
                       "    if x > 1:\n        return 2\n    return 0\n"),
        "undoc.py": "def p_undoc(v):\n    return v\n",
        "unres.py": "def p_ext(x):\n    return p_nowhere(x)\n",
    },
    "js": {
        "fn_basic.js": ("function j_helper(v) {\n    return v + 1;\n}\n"
                        "function j_run(x) {\n    return j_helper(x);\n}\n"),
        "oneline.js": ("function j_oneline(v) { return j_helper(v); }\n"
                       "function j_oneline2(v) { return j_helper(v); }\n"),
        "dep_mod.js": ("function j_bee(v) {\n    return v;\n}\n"
                       "export { j_bee };\n"),
        "dep_from.js": ("import { j_bee } from './dep_mod.js';\n\n"
                        "function j_use(x) {\n    return j_bee(x);\n}\n"),
        "class_cls.js": ("class JHolder {\n"
                         "    constructor(v) {\n        this.v = v;\n    }\n"
                         "    get() {\n        return this.v;\n    }\n}\n"
                         "function j_make(x) {\n"
                         "    var h = new JHolder(x);\n"
                         "    return h.get();\n}\n"),
        "metrics.js": ("function j_branchy(x) {\n    if (x > 0) {\n"
                       "        return 1;\n    }\n    if (x > 1) {\n"
                       "        return 2;\n    }\n    return 0;\n}\n"),
        "undoc.js": "function j_undoc(v) {\n    return v;\n}\n",
        "unres.js": "function j_ext(x) {\n    return j_nowhere(x);\n}\n",
    },
    "matlab": {
        "mb.m": "function y = mb(x)\n    y = x + 1;\nend\n",
        "ma.m": "function y = ma(x)\n    y = mb(x);\nend\n",
        "mintra.m": ("function y = mintra(x)\n    y = mhelper(x);\nend\n"
                     "function z = mhelper(v)\n    z = v + 1;\nend\n"),
        "MCls.m": ("classdef MCls\n    properties\n        v\n    end\n"
                   "    methods\n        function obj = MCls(v)\n"
                   "            obj.v = v;\n        end\n"
                   "        function r = get(obj)\n"
                   "            r = obj.v;\n        end\n    end\nend\n"),
        "Muse.m": ("function r = Muse(x)\n    o = MCls(x);\n"
                   "    r = o.get();\nend\n"),
        "Mmetrics.m": ("function r = Mmetrics(x)\n    if x > 0\n"
                       "        r = 1;\n    elseif x > 1\n        r = 2;\n"
                       "    else\n        r = 0;\n    end\nend\n"),
        "Mundoc.m": "function y = Mundoc(v)\n    y = v;\nend\n",
        "Munres.m": "function y = Munres(x)\n    y = mnowhere(x);\nend\n",
    },
}

# 各信号读哪个文件（夹具侧的自变量，一处写清）。
BASIC_FILE = {"c": "fn_basic.c", "py": "fn_basic.py", "js": "fn_basic.js",
              "matlab": "mintra.m"}
QUAL_FILE = {"c": "call_dep.c", "py": "class_cls.py", "js": "class_cls.js",
             "matlab": "Muse.m"}
ONELINE_FILE = {"c": "oneline.c", "py": "oneline.py", "js": "oneline.js"}
DEPS_TARGET = {"c": "dep.h", "py": "dep_mod", "js": "dep_mod"}
ENTITY_KEYS = ("entities", "structs", "enums", "typedefs", "field_access",
               "types")
CORE_PAGES = ("index.html", "funcs.html")

# ---------------------------------------------------------------------------
# 探针名单：`(能力, 语言)` 在册 ⇒ 该格**可测**，只能填 yes/no。
# 不在册 ⇒ 该格是 na 的候选，理由必须说清语言形态上为什么测不了。
# ---------------------------------------------------------------------------
PROBED = frozenset(
    [("functions", l) for l in LANGS]
    + [("call_edges", l) for l in LANGS]
    + [("call_edges_cross_file", l) for l in LANGS]
    + [("call_edges_qualified", l) for l in ("matlab", "py", "js")]
    + [("call_edges_oneline_body", l) for l in ("c", "py", "js")]
    + [("deps_edges_json", l) for l in ("c", "py", "js")]
    + [("deps_site_page", l) for l in ("c", "py", "js")]
    + [("classes", l) for l in ("matlab", "py", "js")]
    + [("entities", l) for l in LANGS]
    + [("metrics_complexity", l) for l in LANGS]
    + [("unresolved_attribution", l) for l in LANGS]
    + [("callgraph_projection", l) for l in LANGS]
    + [("heuristics_channel", l) for l in LANGS]
    + [("asm_insights", "c")]
    + [("browse_site", l) for l in LANGS]
    + [("site_same_page_names", l) for l in LANGS]
)


# ---------------------------------------------------------------------------
# 夹具运行与信号
#
# 「先问量具错还是对象错」在这里的具体形态：**夹具必须一次只表达一件事**。
# 本文件第一版把三种调用形态塞进同一个文件，于是「JS 没有调用边」这个结论
# 其实是夹具写错（单行函数体 + 定义行自己 `continue` 的前端规则）——
# 现在每种形态各有专属文件，信号只在那个文件的范围内读。
# ---------------------------------------------------------------------------
def _write_fixtures(root):
    dirs = {}
    for lang in LANGS:
        d = os.path.join(root, lang)
        os.makedirs(d)
        for name, body in sorted(FIXTURES[lang].items()):
            with io.open(os.path.join(d, name), "w", encoding="utf-8",
                         newline="\n") as fh:
                fh.write(body)
        dirs[lang] = d
    return dirs


def _safe_rm(path):
    """尽力删掉临时目录；**失败不许影响判定**。

    宿主可能注入 `safe-delete` shim：它在 `shutil.rmtree` 删 > 50 个文件时抛
    `SystemExit`（BaseException，不是 Exception），而站点产物恰好能过 50 个。
    清理是附带动作，不是判据 —— 捕 BaseException 并把话说出来。
    """
    try:
        shutil.rmtree(path)
    except BaseException as exc:                      # noqa: BLE001
        sys.stderr.write("[note] 临时目录未清理（%s）：%r\n" % (path, exc))


def run_fixture(lang, dirpath, python_exe=None, cli=None):
    """跑一次公开 CLI，带回产物。返回 run dict（`err` 非空 ⇒ 该语言未行使）。"""
    py = python_exe or sys.executable
    cli = cli or os.path.join(REPO_ROOT, CLI_REL)
    base = os.path.dirname(dirpath)
    out_json = os.path.join(base, "%s_load.json" % lang)
    cg = os.path.join(base, "%s_cg.json" % lang)
    site = os.path.join(base, "%s_site" % lang)
    run = {"lang": lang, "rc": None, "json": None, "cg": None, "pages": [],
           "deps_html": "", "err": None}
    argv = [py, cli, dirpath, "--lang", lang, "--json", out_json,
            "--json-level", "full", "--callgraph", cg, "--browse", site]
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, timeout=CLI_TIMEOUT)
        run["rc"] = proc.returncode
    except Exception as exc:                          # noqa: BLE001
        run["err"] = "公开 CLI 起不来：%r" % (exc,)
        return run
    if run["rc"] != 0:
        run["err"] = "公开 CLI rc=%s（夹具跑不起来 ⇒ 这几种能力的实测未行使）" \
            % run["rc"]
        return run
    if not os.path.isfile(out_json):
        run["err"] = "没有落载荷 JSON"
        return run
    try:
        with io.open(out_json, "rb") as fh:
            run["json"] = json.loads(fh.read().decode("utf-8"))
    except Exception as exc:                          # noqa: BLE001
        run["err"] = "载荷 JSON 解析不了：%r" % (exc,)
        return run
    if os.path.isfile(cg):
        try:
            with io.open(cg, "rb") as fh:
                run["cg"] = json.loads(fh.read().decode("utf-8"))
        except Exception:                             # noqa: BLE001
            run["cg"] = None
    if os.path.isdir(site):
        for walk_root, _dirs, files in os.walk(site):
            for name in files:
                rel = os.path.relpath(os.path.join(walk_root, name), site)
                run["pages"].append(rel.replace("\\", "/"))
        deps = os.path.join(site, "deps.html")
        if os.path.isfile(deps):
            with io.open(deps, "r", encoding="utf-8", errors="replace") as fh:
                run["deps_html"] = fh.read()
    return run


def _files(run):
    return dict((f.get("rel"), f)
                for f in ((run["json"] or {}).get("files") or []))


def _edges(run):
    return (run["json"] or {}).get("edges") or []


def _edge_file(edge):
    """一条边的**调用者所在文件**。

    ⚠ C / Py / JS 的边自带 `file` 键，而 **MATLAB 的边没有** —— 它把文件写在
    `caller` 里（`Muse.m:Muse`）。第一版信号只读 `e["file"]`，于是 MATLAB 的
    每一格都被判成 False（而当时看起来「像是个发现」）。归一化放在这里，
    一处说清两种形态 —— 「先问量具错还是对象错」的第四次应验。
    """
    if edge.get("file"):
        return edge["file"]
    caller = edge.get("caller") or ""
    if ":" in caller:
        return caller.split(":", 1)[0]
    return ""


def _cfun(run):
    return ((run["cg"] or {}).get("call_relations") or {})


# ---- 每个信号一个函数：输入 run，输出 bool ----
def s_functions(run):
    f = _files(run).get(BASIC_FILE[run["lang"]])
    return len((f or {}).get("functions") or []) >= 2


def s_call_edges(run):
    rel = BASIC_FILE[run["lang"]]
    return any(_edge_file(e) == rel and not e.get("cross_file")
               for e in _edges(run))


def s_call_edges_cross_file(run):
    if run["lang"] == "matlab":
        return any(e.get("cross_file") for e in _edges(run))
    return int((_cfun(run).get("cross_file") or {}).get("cross") or 0) > 0


def s_call_edges_qualified(run):
    rel = QUAL_FILE[run["lang"]]
    return any(_edge_file(e) == rel for e in _edges(run))


def s_call_edges_oneline_body(run):
    rel = ONELINE_FILE[run["lang"]]
    return any(_edge_file(e) == rel for e in _edges(run))


def s_deps_edges_json(run):
    return len((run["json"] or {}).get("include_edges") or []) > 0


def s_deps_site_page(run):
    return DEPS_TARGET[run["lang"]] in (run["deps_html"] or "")


def s_classes(run):
    for f in (run["json"] or {}).get("files") or []:
        if f.get("classes"):
            return True
    return False


def _nonempty_entity(v):
    """「内容非空」：非空 `list` / 非空 `dict` 才算。

    ⚠ 标量**不算**（`entities: "none"` / `types: 3`）—— 它既不是通道也不是
    数据；旧口径下这种值连「键存在」都不满足，新口径下同样不算，两边一致。
    """
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return False


def s_entities(run):
    """R106 / 槽 42：实体通道 —— **内容非空**才算有。

    为什么要升格（R102 §7-7）：旧口径是「`ENTITY_KEYS` 任一**出现**即真」，
    于是 `{"entities": []}` 这种**空壳键**同样能把该语言刷成 `yes` ——
    而 R101 自己就写下过「js 写 `"entities": []` 等于宣称一条不存在的通道」。
    空壳键与真实现在**读数上分不开**，这正是旧口径的漏洞。

    ⚠ 与 `matlabc.py::_ext_entity_entries` 的「有键 / 无键」语义**不冲突** ——
    两层回答的是**两个不同的问题**：
      * 那一层：载荷里**有没有这条通道**（js / asm 没有实体层 ⇒ 一个键都不写，
        所以写空数组才是撒谎）⇒ 「有键 = 有通道」在那个问题下是**对的**；
      * 本层：这条通道**本次吐没吐出东西**。py 的 `entities` 键永远在，但
        「读到 0 个类」与「读到 3 个类」在**能力对等**这个问题上不是一件事 ——
        而夹具里**确实有** class / struct ⇒ 真实现**必然**给出非空。
    要求「非空」不会把「有通道、本次为空」误判成「没有通道」：那个区分由
    那一层负责，本层只回答「本次有没有真数据」。
    """
    payload = run["json"] or {}
    for k in ENTITY_KEYS:
        if _nonempty_entity(payload.get(k)):
            return True
    for f in payload.get("files") or []:
        if not isinstance(f, dict):
            continue
        for k in ENTITY_KEYS:
            if _nonempty_entity(f.get(k)):
                return True
    return False


def s_metrics_complexity(run):
    for f in (run["json"] or {}).get("files") or []:
        for fn in f.get("functions") or []:
            try:
                if float(fn.get("complexity") or 0) > 1:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def s_unresolved_attribution(run):
    return len((run["json"] or {}).get("unresolved") or []) > 0


def s_callgraph_projection(run):
    if run["cg"] is None:
        return False
    return isinstance(_cfun(run).get("edges_total"), int)


def s_heuristics_channel(run):
    return len((run["json"] or {}).get("heuristics") or []) > 0


def s_asm_insights(run):
    return "asm" in (run["json"] or {})


def s_browse_site(run):
    return any(p.endswith(".html") for p in run["pages"])


def s_site_same_page_names(run):
    pages = run["pages"]
    if not all(p in pages for p in CORE_PAGES):
        return False
    if not any(p.startswith("file/") for p in pages):
        return False
    return any(p.startswith("dir/") for p in pages)


SIGNALS = {
    "functions": s_functions,
    "call_edges": s_call_edges,
    "call_edges_cross_file": s_call_edges_cross_file,
    "call_edges_qualified": s_call_edges_qualified,
    "call_edges_oneline_body": s_call_edges_oneline_body,
    "deps_edges_json": s_deps_edges_json,
    "deps_site_page": s_deps_site_page,
    "classes": s_classes,
    "entities": s_entities,
    "metrics_complexity": s_metrics_complexity,
    "unresolved_attribution": s_unresolved_attribution,
    "callgraph_projection": s_callgraph_projection,
    "heuristics_channel": s_heuristics_channel,
    "asm_insights": s_asm_insights,
    "browse_site": s_browse_site,
    "site_same_page_names": s_site_same_page_names,
}


def measure(python_exe=None):
    """跑四语言夹具，返回 (measured, exercise_probs)。

    measured：`{能力: {语言: bool}}` —— **只含在册的探针格**。
    """
    probs = []
    measured = {}
    base = tempfile.mkdtemp(prefix="parity_r96_")
    try:
        dirs = _write_fixtures(base)
        runs = {}
        for lang in LANGS:
            runs[lang] = run_fixture(lang, dirs[lang], python_exe=python_exe)
            if runs[lang]["err"]:
                probs.append("E6 %s：%s" % (lang, runs[lang]["err"]))
        for cap, lang in sorted(PROBED):
            cell = measured.setdefault(cap, {})
            run = runs.get(lang)
            if run is None or run["err"]:
                continue
            cell[lang] = bool(SIGNALS[cap](run))
        if not measured:
            probs.append("E6 实测为空集 —— 空集上「每格都对」恒真，本门必须有话可说")
        for cap, lang in sorted(PROBED):
            if lang not in measured.get(cap, {}):
                probs.append("E6 在册探针 %s/%s 没有实测值 —— 未行使不许静默"
                             % (cap, lang))
    finally:
        _safe_rm(base)
    return measured, probs


# ---------------------------------------------------------------------------
# 机器块解析（镜像第 19 道门 W1–W7 的口径：围栏块 + `键 | 值`）
# ---------------------------------------------------------------------------
def parse_block(text, open_tag=BLOCK_OPEN, close_tag=BLOCK_CLOSE,
                tag="PARITY"):
    """返回 (kv, probs)。开/闭标记各**恰好一次**；块内 `键 | 值`（恰好一个 `|`）。"""
    probs = []
    if (text or "").count(open_tag) != 1:
        probs.append("E1 %s 起标记出现 %d 次（要求恰好 1 次）"
                     % (tag, (text or "").count(open_tag)))
        return None, probs
    if (text or "").count(close_tag) != 1:
        probs.append("E1 %s 止标记出现 %d 次（要求恰好 1 次）"
                     % (tag, (text or "").count(close_tag)))
        return None, probs
    body = text.split(open_tag, 1)[1].split(close_tag, 1)[0]
    kv = {}
    for i, raw in enumerate(body.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        if line.count("|") != 1:
            probs.append("E1 %s 块第 %d 行 `|` 出现 %d 次（要求恰好 1 次）：%r"
                         % (tag, i, line.count("|"), line[:70]))
            continue
        key, val = line.split("|", 1)
        key, val = key.strip(), val.strip()
        if not key:
            probs.append("E1 %s 块第 %d 行键为空" % (tag, i))
            continue
        if key in kv:
            probs.append("E1 %s 块键重复：%s" % (tag, key))
            continue
        if not val:
            probs.append("E1 %s 块键 %s 的值为空（要表示「无」写 `-`）"
                         % (tag, key))
            continue
        kv[key] = val
    if not kv:
        probs.append("E1 %s 块是空集 —— 空块上「每个键都对」恒真" % tag)
        return None, probs
    return kv, probs


CAP_KEY_RE = re.compile(r"^cap\.([a-z0-9_]+)$")
WHY_KEY_RE = re.compile(r"^cap\.([a-z0-9_]+)\.why\.([a-z0-9]+)$")
EVID_KEY_RE = re.compile(r"^cap\.([a-z0-9_]+)\.evidence$")


def states_from_block(kv, langs, caps):
    """把 `cap.<名> = matlab=yes c=yes ...` 拆成 {能力: {语言: 状态}}。"""
    out = {}
    for cap in caps:
        val = kv.get("cap.%s" % cap)
        if val is None:
            continue
        cell = {}
        for tok in re.split(r"[\s,]+", val.strip()):
            if not tok:
                continue
            if "=" not in tok:
                cell[tok] = None
                continue
            key, v = tok.split("=", 1)
            cell[key.strip()] = v.strip()
        out[cap] = cell
    return out


def why_from_block(kv, langs, caps):
    out = {}
    for key, val in kv.items():
        m = WHY_KEY_RE.match(key)
        if m:
            out[(m.group(1), m.group(2))] = val
    return out


def shape_problems(kv, langs, caps):
    """E1：形状。返回问题串列表（空 = 过）。"""
    probs = []
    states = states_from_block(kv, langs, caps)
    for cap in caps:
        if cap not in states:
            probs.append("E1 块里没有 `cap.%s` —— 门的分母里有这一格" % cap)
            continue
        cell = states[cap]
        for lang in langs:
            if lang not in cell:
                probs.append("E1 `cap.%s` 缺 %s 这一格" % (cap, lang))
                continue
            if cell[lang] not in STATE_OK:
                probs.append("E1 `cap.%s` 的 %s=%r 不在 %s 里"
                             % (cap, lang, cell[lang], list(STATE_OK)))
        for lang in cell:
            if lang not in langs:
                probs.append("E1 `cap.%s` 多了 %s 这一格（语言名单外）"
                             % (cap, lang))
        if not (kv.get("cap.%s.evidence" % cap) or "").strip():
            probs.append("E1 `cap.%s.evidence` 缺失或为空 —— "
                         "没有「怎么测的」的格子，谁都不知道它凭什么" % cap)
    return probs


def reason_problems(kv, langs, caps):
    """E3：理由两向。非 yes 必须有理由；yes **不许**有理由。"""
    probs = []
    states = states_from_block(kv, langs, caps)
    for cap in caps:
        cell = states.get(cap) or {}
        for lang in langs:
            state = cell.get(lang)
            if state is None:
                continue
            key = "cap.%s.why.%s" % (cap, lang)
            why = kv.get(key)
            if state == "yes":
                if why is not None:
                    probs.append("E3 `%s` 是陈旧理由：这一格登记 %s=yes，"
                                 "理由却还留着（%r）" % (key, lang, why[:40]))
                continue
            if why is None:
                probs.append("E3 `%s` 缺失：登记 %s=%s 却没说为什么"
                             % (key, lang, state))
                continue
            if len(why.strip()) < MIN_REASON or why.strip() == "-":
                probs.append("E3 `%s` 的理由只有 %d 个字符（下限 %d）或就是占位符"
                             " —— 一个字符就能把「没实现」说成「不适用」"
                             % (key, len(why.strip()), MIN_REASON))
    return probs


def coverage_problems(kv, langs, caps):
    """E4：门的分母 ⇄ 块里的 `cap.<名>` 键集合，两向。"""
    probs = []
    declared = set()
    for key in kv:
        m = CAP_KEY_RE.match(key)
        if m:
            declared.add(m.group(1))
    for miss in sorted(set(caps) - declared):
        probs.append("E4 门的分母里有 `%s`，块里没有 —— 能力清单少登记一格" % miss)
    for extra in sorted(declared - set(caps)):
        probs.append("E4 块里登记了 `%s`，门的分母里没有 —— "
                     "陈旧登记，或这个名字根本没人在测" % extra)
    return probs


def reconcile_problems(kv, langs, caps, measured, probed):
    """E2：登记 ⇄ 实测，两向；并拦住「用 na 掩盖没实现」。"""
    probs = []
    states = states_from_block(kv, langs, caps)
    for cap in caps:
        cell = states.get(cap) or {}
        for lang in langs:
            state = cell.get(lang)
            if state is None or state not in STATE_OK:
                continue
            key = (cap, lang)
            if key not in probed:
                if state != "na":
                    probs.append("E2 `%s/%s` 登记 %s，但门里**没有**这一格的探针"
                                 " —— 无法核对的宣称不是宣称（要么补探针，"
                                 "要么改成 na 并把语言形态的理由写清）"
                                 % (cap, lang, state))
                continue
            if state == "na":
                probs.append("E2c `%s/%s` 登记 na，但门里**有**这一格的探针"
                             " —— 可测的能力不许被 na 吞掉（这不是「不适用」，"
                             "是你还没做）" % (cap, lang))
                continue
            got = (measured.get(cap) or {}).get(lang)
            if got is None:
                probs.append("E2 `%s/%s` 登记 %s，但没有实测值 —— "
                             "未行使不许当通过" % (cap, lang, state))
                continue
            want = (state == "yes")
            if want and not got:
                probs.append("E2a `%s/%s` 登记 yes，**实测为假** "
                             "（证据口径：%s）—— 登记未实现"
                             % (cap, lang, EVIDENCE.get(cap, "?")))
            elif not want and got:
                probs.append("E2b `%s/%s` 登记 no，**实测为真** —— 实现未登记"
                             "（能力已经有了，表还在说没有）" % (cap, lang))
    return probs


TABLE_ROW_RE = re.compile(r"^\|\s*`?([a-z0-9_]+)`?\s*\|")

# 表头里语言列可能写全名（`Python` / `JavaScript`）—— 不按别名归一的话，
# 列序一变就会「拿 JS 的格去比 Python 的格」，而这种错**看起来完全正常**。
LANG_ALIAS = {"python": "py", "javascript": "js", "js": "js", "py": "py",
              "matlab": "matlab", "c": "c"}


def table_cells(doc_text, langs):
    """人读表：`| 能力 | MATLAB | C | Python | JS | ...` ⇒ {能力: {语言: 状态}}。"""
    lines = (doc_text or "").split("\n")
    head = None
    out = {}
    for ln in lines:
        if head is None:
            cells = [c.strip().strip("`") for c in ln.strip().strip("|")
                     .split("|")]
            if len(cells) >= 1 + len(langs) and cells[0] in ("能力", "capability"):
                head = [LANG_ALIAS.get(c.lower(), c.lower()) for c in cells]
            continue
        m = TABLE_ROW_RE.match(ln.strip())
        if not m:
            if ln.strip().startswith("|"):
                continue
            head = None
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 1 + len(langs):
            continue
        name = m.group(1)
        row = {}
        for i, lang in enumerate(langs):
            try:
                col = head.index(lang)
            except ValueError:
                col = i + 1
            if col < len(cells):
                row[lang] = cells[col].strip().lower()
        out[name] = row
    return out


def human_table_problems(doc_text, langs, caps, kv, readmes=None):
    """E5：**文档 ⇄ 机器块**，两向。

    两半：
      * 前半（R96 立）：人读表**逐格**与机器块一致；
      * 后半（R101 补）：文档里**从格子里算出来的字**（合计行 /
        §3.3 缺口标题 / 缺口表求和 / 两份 README 的记分牌）必须等于
        **现算**出来的。R99 漏更过这三处中的全部三处而无人察觉 ——
        因为那时它们一条判据都没有。

    `readmes`：`[(文件名, 正文或 None)]`；`None` = 文件不在（与「在但
    没那句话」分开报）。不传就只有文档自身的几处。
    """
    probs = []
    # 派生数字**先算**：下面 `if not rows` 会早退，而「表整个不在」时
    # 合计行 / 缺口标题 / README 记分牌照样该被核。
    probs += derived_number_problems(doc_text, langs, caps, kv,
                                     readmes=readmes)
    rows = table_cells(doc_text, langs)
    if not rows:
        probs.append("E5 人读表一格都没解析出来 —— 表不在，或表头不是 "
                     "`| 能力 | MATLAB | C | Python | JS |`")
        return probs
    for miss in sorted(set(caps) - set(rows)):
        probs.append("E5 人读表没有 `%s` 这一行 —— 机器块里有" % miss)
    for extra in sorted(set(rows) - set(caps)):
        probs.append("E5 人读表有 `%s` 这一行，门的分母里没有" % extra)
    states = states_from_block(kv, langs, caps)
    for cap in caps:
        if cap not in rows:
            continue
        for lang in langs:
            a = (rows[cap] or {}).get(lang)
            b = (states.get(cap) or {}).get(lang)
            if a is None or b is None:
                continue
            if a != b:
                probs.append("E5 `%s`/`%s`：人读表写 %r，机器块写 %r —— "
                             "改一处漏一处，两边必须逐格一致"
                             % (cap, lang, a, b))
    return probs


# ---------------------------------------------------------------------------
# E5 的后半（R101）：文档里**派生出来的数字**（不是格子，是从格子算出来的字）
#
# 起因是一次**实测**：R99 把 `site_same_page_names` 的 MATLAB 列从 `no` 改成
# `yes`，机器块与合计行都改了，但 §3.3 的标题（「真实的缺口：16 格」）和它下面
# 那张表的求和（15）没跟着改 —— 而那两处**从此没有任何判据**：E5 的前半只比
# 人读表 ⇄ 机器块**逐格**，散文里的合计不在它的视野里。于是同一份文档里躺着
# 三个互相矛盾的数。
# 「改一处漏一处」是这类数字的**结构性**风险，所以要按结构来堵：
# 凡是从格子里算出来的数，一律**现算再比**，而不是再抄一遍。
# ---------------------------------------------------------------------------
TOTALS_RE = re.compile(
    r"合计\s*(\d+)\s*格[：:]\s*`yes`\s*(\d+)\s*·\s*`no`\s*(\d+)"
    r"\s*·\s*`na`\s*(\d+)")
GAP_HEAD_RE = re.compile(r"真实的缺口[：:]\s*(\d+)\s*格")
GAP_ROW_RE = re.compile(r"^\|\s*[^|]+?\s*\|\s*(\d+)\s*\|")
SCOREBOARD_RE = re.compile(
    r"(\d+)\s*`yes`\s*·\s*(\d+)\s*`no`\s*·\s*(\d+)\s*`na`")


def _readmes(root):
    """两份 README 的正文（`None` = 文件不在，与「在但没那句话」分开报）。

    为什么要读它们：记分牌那句话也出现在 README 的门表行里，**那里的数错了
    没有任何别的判据会看见** —— R96 写下的 `40 yes / 16 no / 8 na` 就这么
    一路躺到 R101。
    """
    out = []
    for name in ("README.md", "README_CN.md"):
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            out.append((name, None))
            continue
        with io.open(p, "r", encoding="utf-8", errors="replace") as fh:
            out.append((name, fh.read()))
    return out


def _block_counts(langs, caps, kv):
    """从**机器块**一格一格地数出 `(总格数, yes, no, na)`。"""
    states = states_from_block(kv, langs, caps)
    cnt = {"yes": 0, "no": 0, "na": 0}
    for cap in caps:
        cell = states.get(cap) or {}
        for lang in langs:
            st = cell.get(lang)
            if st in cnt:
                cnt[st] += 1
    return len(caps) * len(langs), cnt["yes"], cnt["no"], cnt["na"]


def _gap_row_sum(text):
    """§3.3 那张「缺口 / 格数 / 形态 / 去向」表里**格数列**的求和。

    只认 `| ... | <整数> | ... |` 形态的行：表头（第 2 列是 `格数`）与分隔行
    （第 2 列是 `---`）自然被跳过，别的表（第 2 列是 `yes` / 动作名）也一样。
    返回 `(求和, 解析到的行数)` —— **行数要一起返回**：解析到 0 行时求和恒为 0，
    那是个空集判据（R99 的教训），调用方必须能看见。
    """
    total = 0
    seen = 0
    for ln in (text or "").split("\n"):
        m = GAP_ROW_RE.match(ln.strip())
        if m:
            total += int(m.group(1))
            seen += 1
    return total, seen


def derived_number_problems(doc_text, langs, caps, kv, readmes=None):
    """E5 后半四小条：文档里从格子里算出来的数字，必须等于**现算**出来的。"""
    probs = []
    total, yes, no, na = _block_counts(langs, caps, kv)

    hits = TOTALS_RE.findall(doc_text or "")
    if len(hits) != 1:
        probs.append("E5a 合计行出现 %d 次（要求恰好 1 次；形态「合计 N 格："
                     "`yes` A · `no` B · `na` C」）—— 这一行是从格子里算出来的，"
                     "数不出来就说明它没了" % len(hits))
    else:
        got = tuple(int(x) for x in hits[0])
        if got != (total, yes, no, na):
            probs.append("E5a 合计行写 %s，机器块数出来是 %s（总 / yes / no / na）"
                         " —— 改一处漏一处，两边必须相等"
                         % (got, (total, yes, no, na)))

    hits = GAP_HEAD_RE.findall(doc_text or "")
    if len(hits) != 1:
        probs.append("E5b 缺口标题出现 %d 次（要求恰好 1 次；形态「真实的缺口："
                     "N 格」）" % len(hits))
    elif int(hits[0]) != no:
        probs.append("E5b 缺口标题写 %s 格，机器块里 `no` 有 %d 格 —— "
                     "标题说的就是缺口数，而缺口数就是 `no` 的格数"
                     % (hits[0], no))

    s, seen = _gap_row_sum(doc_text)
    if seen == 0:
        probs.append("E5c §3.3 缺口表一行都没解析出来 —— 表不在，或第二列不是"
                     "整数（解析到 0 行时求和恒为 0，空集上「相等」没有意义，"
                     "所以这里必须红）")
    elif s != no:
        probs.append("E5c 缺口表的格数列求和 = %d（%d 行），机器块里 `no` 有 %d 格"
                     " —— 逐行加起来必须等于缺口总数" % (s, seen, no))

    for name, txt in (readmes or []):
        if txt is None:
            probs.append("E5d %s 不在 —— 记分牌那句话就写在它里面，文件没了"
                         "这条判据就失效" % name)
            continue
        hits = SCOREBOARD_RE.findall(txt)
        if not hits:
            probs.append("E5d %s 里没有记分牌句（三个数 + yes/no/na 三个标签"
                         "那种）—— 这枚记分牌最显眼的出口删掉了就是"
                         "「静默退出」：要么补回来，要么把这条判据一起删" % name)
            continue
        for h in hits:
            if tuple(int(x) for x in h) != (yes, no, na):
                probs.append("E5d %s 的记分牌写 %s，机器块数出来是 %s —— "
                             "README 上的数错了没有任何别的判据会看见"
                             % (name, tuple(int(x) for x in h), (yes, no, na)))
    return probs


def _load_doc(root):
    path = os.path.join(root, DOC_REL)
    if not os.path.isfile(path):
        return None, None
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read(), path


def audit(root, python_exe=None):
    """跑全套判据；返回 `(probs, measured, fatal)`。

    `fatal=True` 只留给**缺输入**（登记表不在 / 机器块不可解析）—— 那两件事
    不是「有人把表写错了」，而是「要核的东西根本不在」，退出码必须是 2 而不是 1。
    """
    text, path = _load_doc(root)
    if text is None:
        return ["E6 缺输入：%s 不在（⇒ 登记表本体都没有）" % DOC_REL], {}, True
    kv, probs = parse_block(text)
    if kv is None:
        return list(probs), {}, True
    measured, ex = measure(python_exe=python_exe)
    probs = list(probs) + list(ex)
    probs += shape_problems(kv, LANGS, CAPABILITIES)
    probs += coverage_problems(kv, LANGS, CAPABILITIES)
    probs += reason_problems(kv, LANGS, CAPABILITIES)
    probs += reconcile_problems(kv, LANGS, CAPABILITIES, measured, PROBED)
    probs += human_table_problems(text, LANGS, CAPABILITIES, kv,
                                  readmes=_readmes(root))
    return probs, measured, False


def render_matrix(measured):
    out = ["%-26s %s" % ("capability", "  ".join("%-7s" % l for l in LANGS))]
    for cap in CAPABILITIES:
        row = []
        for lang in LANGS:
            if (cap, lang) not in PROBED:
                row.append("-")
            else:
                row.append("yes" if (measured.get(cap) or {}).get(lang)
                           else "no")
        out.append("%-26s %s" % (cap, "  ".join("%-7s" % c for c in row)))
    return "\n".join(out)


def main(argv):
    if "--help" in argv or "-h" in argv:
        sys.stdout.write(__doc__)
        return 0
    if "--selftest" in argv:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if (bad == 0 and good > 0) else 1
    if "--measure" in argv:
        measured, ex = measure()
        print(render_matrix(measured))
        for p in ex:
            print(p)
        return 0 if not ex else 1

    root = REPO_ROOT
    probs, measured, fatal = audit(root)
    if probs:
        for p in probs:
            print(p)
        print("check_parity_registry: %d 项不合格（判据族 %s）"
              % (len(probs), ROW_SIGNATURE))
        return 2 if fatal else 1
    print(render_matrix(measured))
    print("check_parity_registry: OK（能力 %d 格 × 语言 %d；在册探针 %d 格；"
          "判据族 %s）" % (len(CAPABILITIES), len(LANGS), len(PROBED),
                           ROW_SIGNATURE))
    return 0


# ---------------------------------------------------------------------------
# 两向自证：**坏样本要红、好样本要过**，六个方向各两向。
# 与产品跑同一批纯函数 —— 不另写一份「自证专用」判定逻辑。
# ---------------------------------------------------------------------------
def _kv(states, whys=None, evid=True, caps=CAPABILITIES):
    kv = {}
    whys = whys or {}
    for cap in caps:
        cell = states.get(cap) or {}
        kv["cap.%s" % cap] = " ".join("%s=%s" % (l, cell.get(l, "yes"))
                                      for l in LANGS)
        if evid:
            kv["cap.%s.evidence" % cap] = EVIDENCE.get(cap) or "夹具信号"
    for (cap, lang), val in whys.items():
        kv["cap.%s.why.%s" % (cap, lang)] = val
    return kv


def _all_yes(nas=(), nos=()):
    st = {}
    for cap in CAPABILITIES:
        cell = {}
        for lang in LANGS:
            if (cap, lang) in nas:
                cell[lang] = "na"
            elif (cap, lang) in nos:
                cell[lang] = "no"
            else:
                cell[lang] = "yes"
        st[cap] = cell
    return st


def _why_for(states, text="该格因语言形态而测不了（自证样本）"):
    out = {}
    for cap, cell in states.items():
        for lang, state in cell.items():
            if state != "yes":
                out[(cap, lang)] = text
    return out


def _doc_text(states):
    lines = ["# t", "| 能力 | MATLAB | C | Python | JS |", "| --- | --- | --- | --- | --- |"]
    for cap in CAPABILITIES:
        cell = states.get(cap) or {}
        lines.append("| `%s` | %s |" % (cap, " | ".join(
            cell.get(l, "yes") for l in LANGS)))
    # R101 / E5 后半：样本也得带**派生数字**（合计行 + 缺口标题 + 缺口表），
    # 否则「好样本」在 E5 后半上必红 —— 而那不是样本坏，是样本不完整。
    cnt = {"yes": 0, "no": 0, "na": 0}
    for cap in CAPABILITIES:
        for l in LANGS:
            cnt[(states.get(cap) or {}).get(l, "yes")] += 1
    lines.append("**合计 %d 格：`yes` %d · `no` %d · `na` %d。**"
                 % (len(CAPABILITIES) * len(LANGS),
                    cnt["yes"], cnt["no"], cnt["na"]))
    lines.append("### 3.3 真实的缺口：%d 格，按可修性排序" % cnt["no"])
    lines.append("| 缺口 | 格数 | 形态 | 去向 |")
    lines.append("| --- | --- | --- | --- |")
    for cap in CAPABILITIES:
        for l in LANGS:
            if (states.get(cap) or {}).get(l, "yes") == "no":
                lines.append("| `%s` | 1 | 样本形态 | 待办 |" % cap)
    lines.append(BLOCK_OPEN)
    kv = _kv(states, _why_for(states))
    for k in sorted(kv):
        lines.append("%s | %s" % (k, kv[k]))
    lines.append(BLOCK_CLOSE)
    return "\n".join(lines) + "\n"


def _measured_for(states, probed=PROBED):
    m = {}
    for cap, lang in probed:
        st = (states.get(cap) or {}).get(lang)
        if st in ("yes", "no"):
            m.setdefault(cap, {})[lang] = (st == "yes")
    return m


def _rm(y, n, a):
    """造一份「两份 README 都写着正确记分牌」的文本（E5d 的正样本）。"""
    body = "**%d `yes` · %d `no` · %d `na`**" % (y, n, a)
    return [("README.md", "Today's scoreboard: " + body),
            ("README_CN.md", "今天的记分牌：" + body)]


def _selftest():
    bad = good = 0

    def expect(name, probs, want_red):
        nonlocal bad, good
        if bool(probs) == bool(want_red):
            good += 1
        else:
            bad += 1
            print("[selftest] FAIL %s：期望%s，实际 %s"
                  % (name, "红" if want_red else "绿",
                     (probs or ["(无问题)"])[0][:90]))

    # ---- 正样本：状态与真实测量一致（na 的格子写了理由且不在册探针） ----
    nas = (("asm_insights", "matlab"), ("asm_insights", "py"),
           ("asm_insights", "js"), ("call_edges_qualified", "c"),
           ("call_edges_oneline_body", "matlab"),
           ("deps_edges_json", "matlab"), ("deps_site_page", "matlab"),
           ("classes", "c"))
    nos = (("classes", "py"), ("classes", "js"),
           ("entities", "c"), ("entities", "py"), ("entities", "js"),
           ("call_edges_qualified", "py"), ("call_edges_qualified", "js"),
           ("call_edges_oneline_body", "py"),
           ("call_edges_oneline_body", "js"),
           ("deps_edges_json", "py"), ("deps_edges_json", "js"),
           ("unresolved_attribution", "matlab"),
           ("callgraph_projection", "matlab"),
           ("heuristics_channel", "matlab"),
           ("site_same_page_names", "matlab"))
    st = _all_yes(nas=nas, nos=nos)
    ok_kv = _kv(st, _why_for(st))
    ok_txt = _doc_text(st)
    expect("E1 好样本（形状）", shape_problems(ok_kv, LANGS, CAPABILITIES),
           False)
    expect("E3 好样本（理由两向）",
           reason_problems(ok_kv, LANGS, CAPABILITIES), False)
    expect("E4 好样本（覆盖度）",
           coverage_problems(ok_kv, LANGS, CAPABILITIES), False)
    expect("E5 好样本（人读表）",
           human_table_problems(ok_txt, LANGS, CAPABILITIES, ok_kv), False)
    expect("E2 好样本（登记 ⇄ 实测）",
           reconcile_problems(ok_kv, LANGS, CAPABILITIES,
                              _measured_for(st), PROBED), False)

    # ---- E1 坏样本 ----
    kv = dict(ok_kv)
    del kv["cap.functions"]
    expect("E1 少一格能力", shape_problems(kv, LANGS, CAPABILITIES), True)
    kv = dict(ok_kv)
    kv["cap.classes"] = "matlab=yes c=yes py=yes"
    expect("E1 少一个语言", shape_problems(kv, LANGS, CAPABILITIES), True)
    kv = dict(ok_kv)
    kv["cap.classes"] = "matlab=yes c=yes py=mebbe js=yes"
    expect("E1 值域外", shape_problems(kv, LANGS, CAPABILITIES), True)
    kv = dict(ok_kv)
    del kv["cap.classes.evidence"]
    expect("E1 缺 evidence", shape_problems(kv, LANGS, CAPABILITIES), True)

    # ---- E2 坏样本 ----
    st2 = _all_yes(nas=nas, nos=nos)
    st2["classes"]["py"] = "no"
    kv2 = _kv(st2, _why_for(st2))
    m2 = _measured_for(st2)
    m2["classes"]["py"] = True          # 实测为真、登记 no
    expect("E2b 实现未登记",
           reconcile_problems(kv2, LANGS, CAPABILITIES, m2, PROBED), True)
    st3 = _all_yes(nas=nas, nos=nos)
    m3 = _measured_for(st3)
    m3["functions"]["py"] = False       # 实测为假、登记 yes
    expect("E2a 登记未实现",
           reconcile_problems(ok_kv, LANGS, CAPABILITIES, m3, PROBED), True)
    st4 = _all_yes(nas=nas, nos=nos)
    st4["functions"]["py"] = "na"
    kv4 = _kv(st4, _why_for(st4))
    expect("E2c 用 na 吞掉可测的格",
           reconcile_problems(kv4, LANGS, CAPABILITIES,
                              _measured_for(st4), PROBED), True)
    st5 = _all_yes(nas=nas, nos=nos)
    st5["call_edges_qualified"]["c"] = "yes"
    kv5 = _kv(st5, _why_for(st5))
    expect("E2 宣称不可核（门里没探针）",
           reconcile_problems(kv5, LANGS, CAPABILITIES,
                              _measured_for(st5), PROBED), True)
    st6 = _all_yes(nas=nas, nos=nos)
    kv6 = _kv(st6, _why_for(st6))
    expect("E2 在册探针没有实测值",
           reconcile_problems(kv6, LANGS, CAPABILITIES,
                              {"functions": {"py": True}}, PROBED), True)

    # ---- E3 坏样本 ----
    st7 = _all_yes(nas=nas, nos=nos)
    kv7 = _kv(st7, _why_for(st7))
    del kv7["cap.classes.why.py"]
    expect("E3 非 yes 缺理由", reason_problems(kv7, LANGS, CAPABILITIES), True)
    kv8 = _kv(st7, _why_for(st7))
    kv8["cap.classes.why.py"] = "短"
    expect("E3 理由过短", reason_problems(kv8, LANGS, CAPABILITIES), True)
    kv9 = _kv(st7, _why_for(st7))
    kv9["cap.functions.why.py"] = "这一格是 yes，理由却还在，属于陈旧登记"
    expect("E3 陈旧理由（yes 不该有理由）",
           reason_problems(kv9, LANGS, CAPABILITIES), True)

    # ---- E4 坏样本 ----
    kv10 = dict(ok_kv)
    kv10["cap.newthing"] = "matlab=yes c=yes py=yes js=yes"
    expect("E4 门的分母里没有它", coverage_problems(kv10, LANGS,
                                                CAPABILITIES), True)
    kv11 = dict(ok_kv)
    del kv11["cap.entities"]
    expect("E4 块里少登记一格",
           coverage_problems(kv11, LANGS, CAPABILITIES), True)

    # ---- E5 坏样本 ----
    txt = _doc_text(st).replace("| `classes` | yes | na | no | no |",
                                "| `classes` | yes | na | yes | no |")
    expect("E5 人读表与块不一致",
           human_table_problems(txt, LANGS, CAPABILITIES, ok_kv), True)
    expect("E5 人读表整个不在",
           human_table_problems("没有表", LANGS, CAPABILITIES, ok_kv), True)

    # ---- E5 后半：派生数字（R101） ----
    y, n, a = _block_counts(LANGS, CAPABILITIES, ok_kv)[1:]
    expect("E5 后半好样本（合计行 / 缺口标题 / 缺口表 / 两份 README）",
           human_table_problems(ok_txt, LANGS, CAPABILITIES, ok_kv,
                                _rm(y, n, a)), False)
    expect("E5 后半 readmes 不传则不报 README",
           human_table_problems(ok_txt, LANGS, CAPABILITIES, ok_kv),
           False)
    _bt = ok_txt.replace("`yes` %d · `no` %d" % (y, n),
                         "`yes` %d · `no` %d" % (y - 1, n + 1))
    expect("E5a 合计行与块不一致",
           derived_number_problems(_bt, LANGS, CAPABILITIES, ok_kv,
                                   _rm(y, n, a)), True)
    expect("E5a 合计行整个不在",
           derived_number_problems("没有合计行", LANGS, CAPABILITIES,
                                   ok_kv, _rm(y, n, a)), True)
    _bt = ok_txt.replace("真实的缺口：%d 格" % n,
                         "真实的缺口：%d 格" % (n + 1))
    expect("E5b 缺口标题与块不一致",
           derived_number_problems(_bt, LANGS, CAPABILITIES, ok_kv,
                                   _rm(y, n, a)), True)
    _bt = ok_txt.replace("| 1 | 样本形态", "| 2 | 样本形态", 1)
    expect("E5c 缺口表求和与块不一致",
           derived_number_problems(_bt, LANGS, CAPABILITIES, ok_kv,
                                   _rm(y, n, a)), True)
    expect("E5d README 记分牌与块不一致",
           derived_number_problems(ok_txt, LANGS, CAPABILITIES, ok_kv,
                                   _rm(y - 1, n + 1, a)), True)
    expect("E5d README 里没有记分牌句",
           derived_number_problems(ok_txt, LANGS, CAPABILITIES, ok_kv,
                                   [("README.md", "无"),
                                    ("README_CN.md", "无")]), True)
    expect("E5d README 不在",
           derived_number_problems(ok_txt, LANGS, CAPABILITIES, ok_kv,
                                   [("README.md", None),
                                    ("README_CN.md", None)]), True)

    # ---- R106 / 槽 42：实体通道的**分辨力**（旧口径的漏洞就在这一向）----
    # ⚠ 不能用「当场红」自证：实测四语言在两条口径下**取值完全相同**
    #   （matlab / py 本就有真数据，c / js 本就没有键）⇒ 升格不改任何一格。
    #   能证的是**分辨力**：空壳样本旧口径放行、新口径抓住。
    def _ent_probs(payload):
        _run = {"lang": "c", "json": payload, "pages": [], "cg": None,
                "deps_html": ""}
        return [] if s_entities(_run) else ["no"]

    expect("entity 空壳键（entities: []）不构成通道",
           _ent_probs({"entities": []}), True)
    expect("entity 空 dict（structs: {}）不构成通道",
           _ent_probs({"structs": {}}), True)
    expect("entity 标量（types: \"x\"）不构成通道",
           _ent_probs({"types": "x"}), True)
    expect("entity 每文件里的空壳键也不构成通道",
           _ent_probs({"files": [{"rel": "a.c", "structs": []}]}), True)
    expect("entity 真数据（顶层非空 dict）构成通道",
           _ent_probs({"field_access": {"v": {}}}), False)
    expect("entity 真数据（每文件非空 list）构成通道",
           _ent_probs({"files": [{"rel": "a.c", "structs": [
               {"name": "Pair", "line": 1, "fields": []}]}]}), False)

    # ---- 块解析坏样本 ----
    kv12, p12 = parse_block("no block here")
    expect("E1 块起止标记各缺一次", p12, True)
    kv13, p13 = parse_block(BLOCK_OPEN + "\n函数 | 值\n" + BLOCK_CLOSE)
    expect("E1 块只有一个键（仍算过）", p13, False)
    kv14, p14 = parse_block(BLOCK_OPEN + "\n\n" + BLOCK_CLOSE)
    expect("E1 空块必红", p14, True)
    kv15, p15 = parse_block(BLOCK_OPEN + "\na | b | c\n" + BLOCK_CLOSE)
    expect("E1 行里两个竖线", p15, True)

    # ---- E6 坏样本 ----
    _, _, fatal = audit(os.path.join(tempfile.gettempdir(),
                                     "no_such_repo_r96"))
    expect("E6 缺输入（文档不在 ⇒ fatal ⇒ rc=2 而不是 1）", [fatal], True)
    return bad, good


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
