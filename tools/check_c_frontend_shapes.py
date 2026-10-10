#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""登记制护栏：C 前端「函数定义形态」的判据必须活在仓库里（R61 / R49 §8 C'''''1）。

动因（R49 §9 第 6 条原话：「探针可以放 `_r49/`，但任何**说得出什么会红**的断言
必须进 `tools/` 或 `tests/`」）：
  R49 把 C 前端的函数定义识别从**行锚定正则** `_RE_C_FUNC` 换成**词法 + 括号配平**
  扫描 `_scan_c_definitions`，并在仓库外写了三台装置（`_r49/measure_c_frontend.py` /
  `verify_final.py` / `live_residual.py`）证明「活代码真漏 0 / 假阳性 0 / 行号漂移 0」。
  但那批判据**至今只活在仓库外**。仓库外独立装置 `_r61/probe_c_shapes.py` 实测（修前）：
    * `tools/check_c_frontend_shapes.py` **不存在**；
    * 14 个 `tools/check_*.py` 里只有 `check_boundary_reverse.py` 间接触碰 C 函数表，
      而且它只看「名字 / 行号」，**不看形态、不看函数体边界**；
    * 产品的 `_scan_c_definitions_selftest()` 在**产品里零调用点**（只有一条测试调它）
      —— 也就是说，`check_all.py` 跑完 13 道门之后，没有任何一道能对 C 前端形态说「不」。
  ⇒ 下一轮就会丢。本门把那批判据固化进仓库：秒级、纯合成夹具、不联网、不建 GUI。

为什么走**公开 CLI 子进程**（不 `import matlabc`）：
  ① 与 R54 / R55 同一条纪律 —— `tools/` 不 import 产品模块（宁可另写同义实现）；
  ② 公开 CLI（`--lang c --json`）才是用户真正看到的那一面：内部函数对了、
     组装错了（行号算错 / body_end 没落进 JSON），一样是缺陷。

判据（F1–F6；六条判据的**管辖范围互不重叠**，每条各有自己的突变体作独立证人）：
  F1 四形态全覆盖：`shapes.c` 里 P1 同行 / P2 Allman（花括号换行）/
     P3 返回类型独占一行（GNU）/ P4 参数表跨行 四个定义必须**全部被认出**。
     删掉任一种形态的支持（退回 R49 之前的行锚定行为）⇒ 红。
  F2 指针返回类型紧贴函数名：`int *pi(int)` 必须被认出，且 `ret` 逐字为 `int *`。
     这是 R49 用对照装置**顺手量出来的第二处老缺陷**（旧正则的
     `[A-Za-z0-9_ \\t\\*]*?[ \\t]+` 要求名字前必须是空白，于是 `char *dup(` 整类不可见）。
     `ret` 被抹平 / 该函数消失 ⇒ 红。
  F3 参数 / 返回类型值域：`shapes.c` 里**已出现**的四个形态函数，其
     `params` / `ret` 必须逐字段等于手写期望（P4 的跨行参数表必须恰好切成 2 段，
     不能是 1 段 —— 那是旧实现的退化形态 —— 也不能是 3 段）。任一不符即红。
  F4 函数体边界（字符串花括号不干扰）：`sbraces.c` 里 `fputs ("{", fp)` /
     `fputs ("}", fp)` 不得把函数体边界带偏 —— `body_end` 必须等于**配对 `}`** 的行。
     把 `end_line` 退回**行计数**（R49 §2.2 的真缺陷）⇒ 红。
  F5 声明起点行号：三个夹具里**已出现**的每个函数，`line` 必须等于手写期望。
     P3 是三行结构（类型 / 名字 / `{`），行号取**声明起点**；`sbraces.c` 的第二个
     函数行号同时是「字符串花括号不会把行计数带偏」的第二次作证。行号漂移
     （R49 §2.3 的第三处缺陷）⇒ 红。
  F6 不假阳 + 已披露的不识别边界保持不识别：`neg.c` 里必须认出唯一的真函数
     `real_fn`（**正向**半边），且**不得**出现控制语句（`if`/`while`/`for`/`switch`）、
     调用（`foo`）、宏（`M`）、初值（`y`），以及帮助正文**已披露**为不识别的两类：
     K&R 老式定义（`kr_old`）与返回函数指针（`sig`）。
     只写「必须不出现」的判据在「产品什么都不产出」时也成立 —— 那是**空断言**；
     这里的正向半边就是它的对手方。

为什么 `neg.c` 的「已披露边界」不单开一条判据：它与「不假阳」在实现上是**同一个
  集合比较**（`neg.c` 的名字集合必须恰为 `{real_fn}`）。硬拆两条会让同一个突变体
  同时点亮两条 ⇒「每条判据各有独立证人」这条纪律失效。这里把「已披露边界」做成
  F6 内部的登记表 `BOUNDARY_TRAPS`，并要求**每个 trap 名各有自己的突变体** ——
  覆盖度由自证算出来，不由拆条凑出来。

两向自证（`--selftest`）：1 个好样本 + 9 个坏样本喂给**纯函数** `judge()`，
每个坏样本必须红在**它该红的**那条判据上，且**只**红那一条（`others == []`）；
另外还自证：夹具完备性判据 `R2` 两向、棘轮 `R1` 两向、坏 JSON 被判为缺输入、
「每条判据都有突变体」这件事本身也要成立。

一图看懂：

    合成夹具（3 个 .c，纯手写）           公开 CLI（--lang c --json）
    ┌──────────────────────┐            ┌────────────────────────────┐
    │ shapes.c  P1 P2 P3 P4│── F1/F2/F3▶│ files[].functions[]         │
    │           + int *pi  │            │  {name, ret, params, line,  │
    │ sbraces.c 字符串花括号│── F4/F5 ──▶│   body_start, body_end}     │
    │ neg.c 真函数+陷阱+K&R│── F5/F6 ──▶│                             │
    └──────────────────────┘            └────────────────────────────┘
              ▲                                      │
              └──── 手写期望 WANT（独立于产品）────────┘

退出码：
    0 = F1–F6 全绿，且棘轮与夹具完备性全绿
    1 = 有违规（某条判据红 / 棘轮不符 / 夹具被改瘦）
    2 = 缺输入（找不到 matlabc.py / 公开 CLI 跑不起来 / JSON 不可解析）

用法：
    python tools/check_c_frontend_shapes.py             # 0=全绿 1=违规 2=缺输入
    python tools/check_c_frontend_shapes.py --selftest   # 两向自证
    python tools/check_c_frontend_shapes.py --help       # 显示本帮助
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族，
# 或本门独有的机制名）。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "F1–F6"

# 公开 CLI 的墙钟上限。实测一次 ≈0.5s，300s 是给「机器正忙」留的量级余量；
# 它的意义是「让挂死变成红，而不是让门永远等着」。
CLI_TIMEOUT = 300.0

# ---------------------------------------------------------------------------
# 夹具：纯合成，不联网、不建 GUI、不读仓库里任何 .c
# ---------------------------------------------------------------------------
SHAPES_C = (
    "int p1_add(int a, int b) { return a + b; }\n"    # P1：全在一行
    "int p2_mul(int a, int b)\n"                      # P2：Allman（`{` 换行）
    "{\n"
    "    return a * b;\n"
    "}\n"
    "int\n"                                           # P3：返回类型独占一行（GNU）
    "p3_sub(int a, int b)\n"
    "{\n"
    "    return a - b;\n"
    "}\n"
    "void p4_many(int a,\n"                           # P4：参数表跨行
    "             int b)\n"
    "{\n"
    "}\n"
    "int *pi(int a) { return 0; }\n")                 # 指针返回类型紧贴函数名

SBRACES_C = (
    'void a(void)\n'
    '{\n'
    '  fputs ("{", fp);\n'
    '}\n'
    'void b(void)\n'
    '{\n'
    '  fputs ("}", fp);\n'
    '}\n')

NEG_C = (
    "#define M(x) { x; }\n"          # 宏：不得算函数
    "int y = f(1);\n"                # 初值里的调用：不得算函数
    "void real_fn(void)\n"           # 唯一的真函数
    "{\n"
    "  if (x) { }\n"                 # 控制语句：不得算函数
    "  while (y) { }\n"
    "  for (;;) { }\n"
    "  switch (z) { }\n"
    "  foo(bar) ;\n"                 # 语句级调用：不得算函数
    "}\n"
    "int kr_old(a, b)\n"             # K&R 老式定义：帮助正文已披露**不识别**
    "int a;\n"
    "int b;\n"
    "{\n"
    "  return a + b;\n"
    "}\n"
    "void (*sig(int s))(int)\n"      # 返回函数指针：帮助正文已披露**不识别**
    "{\n"
    "}\n")

FIXTURES = (("shapes.c", SHAPES_C),
            ("sbraces.c", SBRACES_C),
            ("neg.c", NEG_C))

# 手写期望 —— **独立于产品**（不是跑产品得到的结果），也不来自任何 tools/ 装置。
# 值 = (ret, params, line, body_start, body_end)
WANT = {
    "shapes.c": {
        "p1_add": ("int", ["int a", "int b"], 1, 1, 1),
        "p2_mul": ("int", ["int a", "int b"], 2, 3, 5),
        "p3_sub": ("int", ["int a", "int b"], 6, 8, 10),
        "p4_many": ("void", ["int a", "int b"], 11, 13, 14),
        "pi": ("int *", ["int a"], 15, 15, 15),
    },
    "sbraces.c": {
        "a": ("void", ["void"], 1, 2, 4),
        "b": ("void", ["void"], 5, 6, 8),
    },
    "neg.c": {
        "real_fn": ("void", ["void"], 3, 4, 10),
    },
}

# F1 的全部职责：这四个名字必须都在（值域归 F3）
SHAPE_NAMES = ("p1_add", "p2_mul", "p3_sub", "p4_many")
# F2 只管这一个（R49 顺手量出的第二处老缺陷的现场）
POINTER_FN = "pi"
# F6 的两族陷阱：假阳陷阱 + 帮助正文已披露为「不识别」的两类
FALSE_POSITIVE_TRAPS = ("M", "y", "if", "while", "for", "switch", "foo")
BOUNDARY_TRAPS = ("kr_old", "sig")

CRITERIA = (
    ("F1", "四形态全覆盖（P1 同行 / P2 Allman / P3 返回类型独占一行 / P4 参数表跨行）"),
    ("F2", "指针返回类型紧贴函数名必须被认出，且 ret 逐字为 `int *`"),
    ("F3", "参数表 / 返回类型值域逐字段相等"),
    ("F4", "函数体边界（字符串字面量里的花括号不得干扰 body_end）"),
    ("F5", "声明起点行号逐字段相等"),
    ("F6", "不假阳（控制语句 / 调用 / 宏 / 初值），且已披露的 K&R / 返回函数指针保持不识别"),
)
CRITERIA_IDS = tuple(c[0] for c in CRITERIA)

# ---------------------------------------------------------------------------
# 棘轮：全部是「事实的读数」，不是可调参数。覆盖不许静默缩水。
# ---------------------------------------------------------------------------
EXPECTED_CRITERIA = 6
EXPECTED_FIXTURES = 3
EXPECTED_SHAPE_NAMES = 4
EXPECTED_BOUNDARY_TRAPS = 2
EXPECTED_REAL_FUNCS = 8          # 5（shapes）+ 2（sbraces）+ 1（neg）


# ---------------------------------------------------------------------------
# 纯函数判据（不碰文件系统与子进程 —— 自证可以直接喂合成结果）
# ---------------------------------------------------------------------------
def judge(per):
    """六条判据的实现。

    per = {夹具基名: {函数名: (ret, params, line, body_start, body_end)}}
    返回问题列表；每条以判据 id（`F1`…`F6`）+ 空格开头。
    """
    if not isinstance(per, dict):
        return ["F0 判据载体不是字典（parse_shapes 的返回值坏了）"]

    sh = per.get("shapes.c") or {}
    sb = per.get("sbraces.c") or {}
    ng = per.get("neg.c") or {}
    probs = []

    # ---- F1 四形态全覆盖（只看**存在性**；值域归 F3 ⇒ 两条判据不重叠） ----
    missing = [n for n in SHAPE_NAMES if n not in sh]
    if missing:
        probs.append("F1 shapes.c 漏掉形态函数 %r —— 跨行签名支持退化了"
                     % (missing,))

    # ---- F2 指针返回类型（只看 `pi` 的存在 + ret 原文） ----
    if POINTER_FN not in sh:
        probs.append("F2 shapes.c 漏掉 %s（指针返回类型紧贴函数名，"
                     "旧正则整类看不见）" % POINTER_FN)
    elif (sh[POINTER_FN][0] or "") != "int *":
        probs.append("F2 shapes.c:%s 的 ret 实测 %r，期望 'int *'"
                     % (POINTER_FN, sh[POINTER_FN][0]))

    # ---- F3 值域（params / ret；只对**已出现**的形态函数判，存在性归 F1） ----
    for fn in SHAPE_NAMES:
        if fn not in sh:
            continue
        w = WANT["shapes.c"][fn]
        got = (sh[fn][0], list(sh[fn][1] or []))
        if got != (w[0], w[1]):
            probs.append("F3 shapes.c:%s 的 (ret, params) 实测 %r，期望 %r"
                         % (fn, got, (w[0], w[1])))

    # ---- F4 体界（sbraces.c 的两处 `fputs`；存在性也归 F4 —— 它只有这一个夹具） ----
    for fn in sorted(WANT["sbraces.c"]):
        w = WANT["sbraces.c"][fn]
        if fn not in sb:
            probs.append("F4 sbraces.c 漏掉 %s（字符串里的花括号把它吞掉了？）"
                         % fn)
        elif sb[fn][4] != w[4]:
            probs.append("F4 sbraces.c:%s 的 body_end 实测 %r，期望 %d —— "
                         "行计数对字符串字面量里的花括号失明"
                         % (fn, sb[fn][4], w[4]))

    # ---- F5 行号（三个夹具里**已出现**的函数；存在性归 F1/F4/F6） ----
    for rel in sorted(WANT):
        got = per.get(rel) or {}
        for fn in sorted(WANT[rel]):
            if fn not in got:
                continue
            if got[fn][2] != WANT[rel][fn][2]:
                probs.append("F5 %s:%s 的 line 实测 %r，期望 %d"
                             % (rel, fn, got[fn][2], WANT[rel][fn][2]))

    # ---- F6 不假阳 + 已披露边界（正 + 负两半，缺了正半边就是空断言） ----
    for fn in sorted(WANT["neg.c"]):
        if fn not in ng:
            probs.append("F6 neg.c 漏掉真函数 %s —— 只断言「不出现」是空断言，"
                         "这里就是它的正向对手方" % fn)
    fp = [n for n in FALSE_POSITIVE_TRAPS if n in ng]
    if fp:
        probs.append("F6 neg.c 把 %r 当成函数（控制语句 / 调用 / 宏 / 初值假阳）"
                     % (fp,))
    bd = [n for n in BOUNDARY_TRAPS if n in ng]
    if bd:
        probs.append("F6 neg.c 竟认出 %r —— 帮助正文已披露这两类**不识别**，"
                     "认出来等于承诺与行为分叉" % (bd,))
    return probs


def judge_fixtures(fixtures=None, neg_c=None, shapes_c=None, sbraces_c=None):
    """夹具完备性：每条陷阱必须在夹具源码里**逐字**出现。

    为什么这是必需的一环（R56 的自伤教训：**口径变一次，样本完备性就得跟着重算**）：
    判据是从夹具里读证据的。若夹具里那句 `if (x) { }` 被删掉，「不得出现 `if`」这
    条判据就退化成**空断言** —— 它永远绿，而且**没有任何东西会告诉你**。
    """
    fixtures = FIXTURES if fixtures is None else fixtures
    neg = NEG_C if neg_c is None else neg_c
    shp = SHAPES_C if shapes_c is None else shapes_c
    sbr = SBRACES_C if sbraces_c is None else sbraces_c
    probs = []
    for name in FALSE_POSITIVE_TRAPS + BOUNDARY_TRAPS:
        if name not in neg:
            probs.append("R2 neg.c 夹具里找不到陷阱 %r —— 那条判据变成空断言"
                         % name)
    # 四种形态必须真的以那种形态写在夹具里（P2 的 `{` 在下一行、P3 的类型独占一行…）
    for marker in ("int p2_mul(int a, int b)\n{\n",
                   "int\np3_sub(int a, int b)\n{\n",
                   "void p4_many(int a,\n"):
        if marker not in shp:
            probs.append("R2 shapes.c 缺形态标记 %r" % marker)
    if "int *pi(int a)" not in shp:
        probs.append("R2 shapes.c 缺「指针返回类型紧贴函数名」样本")
    if 'fputs ("{",' not in sbr or 'fputs ("}",' not in sbr:
        probs.append("R2 sbraces.c 缺字符串花括号样本")
    for rel, text in fixtures:
        if not text.strip():
            probs.append("R2 夹具 %s 是空的" % rel)
    return probs


def judge_ratchet(n_funcs):
    """棘轮：登记值必须**等于**真实值（删掉一整个家族而不改数字 ⇒ 红）。"""
    probs = []
    for tag, got, want in (("判据条数", len(CRITERIA), EXPECTED_CRITERIA),
                           ("夹具数", len(FIXTURES), EXPECTED_FIXTURES),
                           ("形态名数", len(SHAPE_NAMES), EXPECTED_SHAPE_NAMES),
                           ("已披露边界陷阱数", len(BOUNDARY_TRAPS),
                            EXPECTED_BOUNDARY_TRAPS),
                           ("真实仓库认出的函数数", n_funcs,
                            EXPECTED_REAL_FUNCS)):
        if got != want:
            probs.append("R1 %s 实测 %d，棘轮记的是 %d —— 覆盖不许静默缩水"
                         % (tag, got, want))
    return probs


# ---------------------------------------------------------------------------
# 公开 CLI
# ---------------------------------------------------------------------------
def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_shapes(json_text):
    """把 `--json` 产物转成 {基名: {函数名: (ret, params, line, body_start, body_end)}}。

    坏 JSON 返回 None（⇒ 调用方按**缺输入**处理，不是「没问题」）。
    """
    try:
        payload = json.loads(json_text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    per = {}
    for f in (payload.get("files") or []):
        if not isinstance(f, dict):
            continue
        rel = str(f.get("rel") or f.get("path") or "?")
        base = os.path.basename(rel.replace("\\", "/"))
        d = {}
        for fn in (f.get("functions") or []):
            if not isinstance(fn, dict):
                continue
            d[fn.get("name")] = (fn.get("ret"), fn.get("params"),
                                 fn.get("line"), fn.get("body_start"),
                                 fn.get("body_end"))
        per[base] = d
    return per


def scan(root, python_exe):
    """建夹具 → 跑一次公开 CLI → 判六条判据。

    返回 (probs, n_funcs)；probs 为 None 表示**缺输入**（跑不起来 / JSON 坏）。
    """
    base = tempfile.mkdtemp(prefix="r61gate_")
    try:
        src = os.path.join(base, "src")
        os.makedirs(src)
        for rel, text in FIXTURES:
            with io.open(os.path.join(src, rel), "w", encoding="utf-8",
                         newline="") as fh:
                fh.write(text)
        # 产物落在 base（**src 之外**）：否则第二次跑就会把自己的产物当语料扫进去
        out_json = os.path.join(base, "shapes_out.json")
        argv = [python_exe, "matlabc.py", src, "--lang", "c",
                "--json", out_json, "--max-warnings", "999"]
        p = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=CLI_TIMEOUT)
        if p.returncode != 0:
            return None, 0
        if not os.path.isfile(out_json):
            return None, 0
        with io.open(out_json, "rb") as fh:
            jt = fh.read().decode("utf-8", "replace")
        per = parse_shapes(jt)
        if per is None:
            return None, 0
        n = sum(len(d) for d in per.values())
        return judge(per), n
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _write_help(text):
    for s in (sys.stdout, sys.stderr):
        if s is not None and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
        return True
    except Exception:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is None:
            return False
        buf.write(text.encode("utf-8", "replace"))
        buf.flush()
        return True


def main(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--help", "-h", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns, _rest = ap.parse_known_args(argv)

    if ns.help:
        _write_help(__doc__)
        return 0
    if ns.selftest:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1

    root = repo_root()
    if not os.path.isfile(os.path.join(root, "matlabc.py")):
        print("check_c_frontend_shapes: 找不到 matlabc.py（缺输入 → 红）：%s" % root)
        return 2
    try:
        probs, n_funcs = scan(root, sys.executable)
    except (OSError, subprocess.SubprocessError) as e:
        print("check_c_frontend_shapes: 公开 CLI 跑不起来：%s（缺输入 → 红）" % e)
        return 2
    if probs is None:
        print("check_c_frontend_shapes: 公开 CLI 没产出可解析的 JSON"
              "（--json 是判据的载体 → 缺输入）")
        return 2

    probs = list(probs) + judge_fixtures() + judge_ratchet(n_funcs)
    if probs:
        for p in probs:
            print("check_c_frontend_shapes: " + p)
        print("check_c_frontend_shapes: %d 项违规" % len(probs))
        return 1
    print("check_c_frontend_shapes: OK（%d 个合成夹具 / 公开 CLI 认出 %d 个函数 / "
          "%s 全绿 + 夹具完备性 + 棘轮）"
          % (len(FIXTURES), n_funcs, ROW_SIGNATURE))
    return 0


# ---------------------------------------------------------------------------
# 两向自证：坏样本必须红在**指定**判据上，好样本必须全绿
# ---------------------------------------------------------------------------
def _selftest():
    """`bad` 数的是**本装置自己的失误**：坏样本没红、或红在了别的判据上。"""
    bad = [0]
    good = [0]
    witnessed = set()

    def _mk(sh=None, sb=None, ng=None):
        return {"shapes.c": dict(WANT["shapes.c"] if sh is None else sh),
                "sbraces.c": dict(WANT["sbraces.c"] if sb is None else sb),
                "neg.c": dict(WANT["neg.c"] if ng is None else ng)}

    def red(tag, per, want):
        """坏样本必须红在 `want` 上，且**不**红在任何别的判据上。"""
        probs = judge(per)
        hit = [p for p in probs if p.startswith(want)]
        others = [p for p in probs
                  if p[:2] in CRITERIA_IDS and not p.startswith(want)]
        if not hit:
            bad[0] += 1
            print("  [selftest] %s 未被 %s 抓到（实得 %r）" % (tag, want, probs))
        elif others:
            bad[0] += 1
            print("  [selftest] %s 红在了别的判据上：%r" % (tag, others))
        else:
            good[0] += 1
            witnessed.add(want)

    def green(tag, probs):
        if not probs:
            good[0] += 1
        else:
            bad[0] += 1
            print("  [selftest] %s 被误伤：%r" % (tag, probs))

    # ---- 好样本：手写期望本身必须全绿 ----
    green("好样本：手写期望六条判据全绿", judge(_mk()))

    # ---- F1：抽掉 P3（返回类型独占一行）—— 正是 R49 之前的行锚定行为 ----
    d = _mk()
    d["shapes.c"].pop("p3_sub")
    red("坏样本 F1 抽掉 P3", d, "F1")

    # ---- F2：指针返回类型的 ret 被抹平 ----
    d = _mk()
    d["shapes.c"]["pi"] = ("int", ["int a"], 15, 15, 15)
    red("坏样本 F2 指针返回类型 ret 被抹平", d, "F2")

    # ---- F2'：该函数整个消失（旧正则整类看不见） ----
    d = _mk()
    d["shapes.c"].pop("pi")
    red("坏样本 F2 指针返回类型整类看不见", d, "F2")

    # ---- F3：P4 的跨行参数表被切成 1 段（旧 `raw.split(",")` 退化形态） ----
    d = _mk()
    d["shapes.c"]["p4_many"] = ("void", ["int a int b"], 11, 13, 14)
    red("坏样本 F3 参数表只切出 1 段", d, "F3")

    # ---- F4：body_end 退回行计数（字符串里的 `{` 把它带偏） ----
    d = _mk()
    d["sbraces.c"]["a"] = ("void", ["void"], 1, 2, 8)
    red("坏样本 F4 body_end 退回行计数", d, "F4")

    # ---- F5：行号漂移（P3 的声明起点少算一行） ----
    d = _mk()
    d["shapes.c"]["p3_sub"] = ("int", ["int a", "int b"], 7, 8, 10)
    red("坏样本 F5 行号漂移", d, "F5")

    # ---- F6-a：控制语句假阳 ----
    d = _mk()
    d["neg.c"]["if"] = ("int", ["x"], 5, 5, 5)
    red("坏样本 F6 控制语句假阳", d, "F6")

    # ---- F6-b：已披露为「不识别」的两类**各自**要有独立证人 ----
    for fn in BOUNDARY_TRAPS:
        d = _mk()
        d["neg.c"][fn] = ("int", ["a", "b"], 11, 13, 15)
        red("坏样本 F6 已披露边界 %s 被认出" % fn, d, "F6")

    # ---- F6-c：neg.c 什么都不产出 ⇒ 正向半边必须红（空断言的对手方） ----
    red("坏样本 F6 负半边空断言（neg.c 全空）", _mk(ng={}), "F6")

    # ---- ① 每条判据都必须被至少一个坏样本点名（覆盖不许静默缩水） ----
    if witnessed == set(CRITERIA_IDS):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] 判据 %r 没有自己的坏样本（覆盖静默缩水）"
              % (sorted(set(CRITERIA_IDS) - witnessed),))

    # ---- ② 载体坏了：坏 JSON 必须被判成缺输入，而不是「没问题」 ----
    if (parse_shapes("{ not json") is None and parse_shapes("[]") is None
            and parse_shapes('{"files": []}') == {}):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] 坏 JSON 竟然被解析出来了")

    # ---- ③ 夹具完备性判据 R2 两向 ----
    green("好样本：夹具完备性全绿", judge_fixtures())
    if judge_fixtures(neg_c="int x;\n"):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] 陷阱被从夹具里删掉后 R2 不报红（判据退化成空断言）")
    if judge_fixtures(shapes_c="int f(void) { return 0; }\n"):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] 形态标记被删掉后 R2 不报红")
    if judge_fixtures(fixtures=(("empty.c", "  \n"),)):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] 空夹具 R2 不报红")

    # ---- ④ 棘轮 R1 两向：正确读数不报红，缩水读数必须报红 ----
    green("好样本：棘轮在正确读数上全绿", judge_ratchet(EXPECTED_REAL_FUNCS))
    if judge_ratchet(EXPECTED_REAL_FUNCS - 1):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] 棘轮在缩水读数上不报红")

    return bad[0], good[0]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
