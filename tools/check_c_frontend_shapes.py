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

判据（F1–F7；七条判据的**管辖范围互不重叠**，每条各有自己的突变体作独立证人）：
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
  F7 调用关系的**有界投影**（`--callgraph` 系列；R86-3）：F1–F6 管的是「函数长什么样」，
     这一条管的是「函数之间什么关系」。六个半边，各有自己的突变体：
       F7a **两本账对账**：同一份产物里 `call_relations.edges_total` 必须==
           `--json` 载荷里 `edges` 的长度。两个独立容器数同一件事，对不上就是
           其中一本算错了（口径类缺陷：两边一起错时会永远自洽，所以必须**并列**）。
       F7b **环，两向**：`cg_cyc.c` 里 `hub ⇄ leaf` 必须被报成 1 个 size=2 的环；
           `cg_acy.c` 必须报 `cycles == []` 且 `cycles_computed` 为真
           （只断言「有环」会让「永远报空」也绿）。
       F7c **有界且诚恳**：`--callgraph-max-nodes 2` ⇒ 节点恰 2 个且
           `hit_node_cap` 为真；默认大上限 ⇒ 为假。且 `truncated.fan_in_shown`
           必须 == 实际给出的 `fan_in_top` 条数（数字与实物对账，不许说谎）。
       F7d **深度真的起作用**：`--callgraph-depth 1` 与 `2` 的节点集合必须不同
           （否则那个开关是个摆设，而摆设型开关没有任何东西会告诉你它是摆设）。
       F7e **未知扩展名不许静默降级**：`--callgraph x.txt` 必须**非零退出**，
           且**不得**产出该文件（静默改成 JSON 就是「没听懂却假装听懂」）。
       F7f **口径写成字面量**：`identity == "callee-name"`，`limitations` 至少 3 条
           且非空，其中必须有「同名合并 ⇒ 假阳性」这一条 —— 节点身份是**名字**不是
           **定义落点**，这是本投影最容易被人误读的地方。

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
    0 = F1–F7 全绿，且棘轮与夹具完备性全绿
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
ROW_SIGNATURE = "F1–F8"

# H3（R73）：越出签名族、但仍由本门发出的判据前缀。
ROW_EXTRA = "R1,R2"
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

# ---------------------------------------------------------------------------
# F7（R86-3）夹具：调用关系。**独立于 F1–F6 那一组** ——
# 刻意不复用 `FIXTURES`，因为 `EXPECTED_REAL_FUNCS` / `EXPECTED_FIXTURES` 是
# 钉死的棘轮：把调用关系样本混进同一批，会顺手把那两个数字改掉，于是
# 「F7 改动」与「F1–F6 覆盖缩水」在读数上分不开。两组各自跑、各自计数。
# ---------------------------------------------------------------------------
CG_CYC_C = (
    "static void helper(void) { }\n"        # 被 hub 调，自身不调
    "void leaf(void);\n"
    "void hub(void) { helper(); leaf(); }\n"
    "void leaf(void) { hub(); }\n"          # hub ⇄ leaf：唯一的 size=2 环
    "void top(void) { hub(); hub(); }\n"    # 扇入最高 = hub（3 次）
    "void side(void) { top(); }\n"          # 给 depth=2 提供第二层
)

CG_ACY_C = (
    "void bottom(void) { }\n"
    "void mid(void) { bottom(); }\n"
    "void top2(void) { mid(); }\n"          # 一条 3 级链，**无环**
)

CG_FIXTURES = (("cg_cyc.c", CG_CYC_C), ("cg_acy.c", CG_ACY_C))

# F7b 的期望环（手写，独立于产品）：成员集合必须恰是这两个
CG_WANT_CYCLE = ("hub", "leaf")

# ---------------------------------------------------------------------------
# F8（R87）夹具：GNU **属性说明符** `__attribute__((…))` 既不是定义、也不是调用。
# 与 F1–F6 / F7 两组**再分开放**（同一条理由：棘轮钉死在各自那一组上，
# 混在一起会让「F8 改动」与「别的覆盖缩水」在读数上分不开）。
#
# 夹具里四类**类型定义**与三类**真函数**必须同时在，否则判据会退化成空断言：
#   ① `typedef struct __attribute__((…)) {` …… 内核里真实存在的形态（7 处）
#   ② `struct __attribute__((…)) {`（**匿名**，属性紧贴 `{`）
#   ③ `union __attribute__((…)) {` / ④ `enum __attribute__((…)) {`
#   ⑤ 属性行**独占一行**、夹在声明与定义之间（`decl_then_attr`）
#   ⑥ 属性组**在真函数的声明行内**（`get_attribute`）—— 属性头泄漏
#   ⑦ 属性组内有**函数样参数**（`aligned(4)`，`aligned_fn`）—— 组内参数泄漏
# ⑦ 是探针实测才发现的**第三条**泄漏通道：`aligned(` 前面是空格，于是
# `_RE_C_CALL` 把它当调用，而 `aligned` 没有同名定义 ⇒ 直接抬高 `unresolved`。
# ---------------------------------------------------------------------------
ATTR_C = (
    "typedef struct __attribute__((packed, aligned(4))) {\n"      # 1
    "    unsigned int tf_a;\n"                                    # 2
    "} attr_rec_t;\n"                                             # 3
    "\n"                                                          # 4
    "struct __attribute__((packed)) {\n"                          # 5
    "    unsigned int tf_b;\n"                                    # 6
    "};\n"                                                        # 7
    "\n"                                                          # 8
    "union __attribute__((aligned(8))) {\n"                       # 9
    "    int tf_c;\n"                                             # 10
    "};\n"                                                        # 11
    "\n"                                                          # 12
    "enum __attribute__((packed)) {\n"                            # 13
    "    ATTR_D = 1,\n"                                           # 14
    "};\n"                                                        # 15
    "\n"                                                          # 16
    "void decl_then_attr(void *p);\n"                             # 17
    "__attribute__((weak,unused,section(\".text.attr_probe\")))\n"  # 18
    "void *decl_then_attr(void *p)\n"                             # 19
    "{\n"                                                         # 20
    "    return p;\n"                                             # 21
    "}\n"                                                         # 22
    "\n"                                                          # 23
    "static __attribute__((unused)) int get_attribute(void)\n"    # 24
    "{\n"                                                         # 25
    "    return 1;\n"                                             # 26
    "}\n"                                                         # 27
    "\n"                                                          # 28
    "static __attribute__((aligned(4))) int aligned_fn(void)\n"   # 29
    "{\n"                                                         # 30
    "    return 0;\n"                                             # 31
    "}\n"                                                         # 32
    "\n"                                                          # 33
    "void attr_caller(void)\n"                                    # 34
    "{\n"                                                         # 35
    "    (void)get_attribute();\n"                                # 36
    "    missing_extern();\n"                                     # 37
    "}\n"                                                         # 38
    # ⚠ R87g **防过度收窄**：无分号宏调用把 `decl_start` 钉在远处，其实参里的
    # `typedef`（括号深度 > 0）不得把后面的真函数一起吃掉。真实内核里踩到的
    # 两处分别是 `DEFINE_PROCESS_TYPE(typedef)` 与 `BTF_ID(typedef, S)`；
    # 这里保留「无分号 ID(...) 序列 + 实参 typedef」这个**形状**，宏体简化。
    "#define DPT(t) proc_##t##_type\n"                           # 39
    "DPT(typedef)\n"                                              # 40
    "static void process_subrange_type(void)\n"                   # 41
    "{\n"                                                         # 42
    "}\n"                                                         # 43
    "BTF_ID(typedef, S)\n"                                        # 44
    "static int\n"                                                # 45
    "__resolve_symbol(void)\n"                                    # 46
    "{\n"                                                         # 47
    "    return 0;\n"                                             # 48
    "}\n")                                                        # 49

ATTR_FIXTURES = (("attr.c", ATTR_C),)

# 手写期望（**独立于产品**）：这些名字必须**恰好**是函数表全体 —— 既排除
# `__attribute__`，也排除「靠整类不报把类型定义连真函数一起丢掉」。
# 后两个（`__resolve_symbol` / `process_subrange_type`）是 R87g 的**回归守卫**：
# 它们前面压着一串无分号宏调用，实参里恰好有 `typedef`。
ATTR_WANT_FUNCS = ("__resolve_symbol", "aligned_fn", "attr_caller",
                   "decl_then_attr", "get_attribute", "process_subrange_type")
# 夹具里唯一的真调用边（`attr_caller` 调它）
ATTR_WANT_EDGE = ("attr_caller", "get_attribute")
# ⚠ 别把上面那个元组的**长度**当边数：它是「一条边的两个端点」。
ATTR_WANT_N_EDGES = 1
# 夹具里唯一的**真**未解析调用；`aligned` / `__attribute__` 都不许出现在这里
ATTR_WANT_UNRESOLVED = ("missing_extern",)
# 已登记的「噪声」未解析读数：夹具里那两条**宏调用**（`DPT(...)` / `BTF_ID(...)`）。
# 词法前端不展开宏 ⇒ 宏调用与函数调用**同形**，必然落进 unresolved。这与属性
# 说明符泄漏是**两回事**，所以分开登记，并要求「噪声不多不少」：产品行为一旦
# 变了（宏被展开了、或又漏了别的东西）就报红，而不是被一个大数字吞掉。
ATTR_KNOWN_UNRESOLVED_NOISE = ("BTF_ID", "DPT")
# F8f：帮助/文档必须**显式声明**这条边界（「不做也不静默」的口径落到文档上）
ATTR_DOC = "docs/matlabc_FEATURES.md"
ATTR_DOC_MARKERS = ("__attribute__", "不是调用")

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
    ("F7", "调用关系的有界投影：两本账对账 / 环两向 / 有界且诚恳 / 深度有效 / 未知格式不降级 / 口径字面量"),
    ("F8", "属性说明符 `__attribute__`：类型定义不产函数 / 真函数不丢 / 组内参数不算调用 / 未解析两向 / 产物零出现 / 文档显式声明"),
)
CRITERIA_IDS = tuple(c[0] for c in CRITERIA)

# ---------------------------------------------------------------------------
# 棘轮：全部是「事实的读数」，不是可调参数。覆盖不许静默缩水。
# ---------------------------------------------------------------------------
EXPECTED_CRITERIA = 8
EXPECTED_FIXTURES = 3
EXPECTED_CG_FIXTURES = 2
EXPECTED_ATTR_FIXTURES = 1
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


def judge_fixtures(fixtures=None, neg_c=None, shapes_c=None, sbraces_c=None,
                   cg_cyc=None, cg_acy=None, attr_c=None):
    """夹具完备性：每条陷阱必须在夹具源码里**逐字**出现。

    为什么这是必需的一环（R56 的自伤教训：**口径变一次，样本完备性就得跟着重算**）：
    判据是从夹具里读证据的。若夹具里那句 `if (x) { }` 被删掉，「不得出现 `if`」这
    条判据就退化成**空断言** —— 它永远绿，而且**没有任何东西会告诉你**。

    `cg_cyc` / `cg_acy` 是 R86-3 加的**可注入**参数：F7 的夹具完备性也要能被
    两向自证（传一份被抽掉环边的夹具，必须报红），否则它自己就是空断言。
    `attr_c` 同理（R87，F8）。
    """
    fixtures = FIXTURES if fixtures is None else fixtures
    neg = NEG_C if neg_c is None else neg_c
    shp = SHAPES_C if shapes_c is None else shapes_c
    sbr = SBRACES_C if sbraces_c is None else sbraces_c
    cgy = CG_CYC_C if cg_cyc is None else cg_cyc
    cga = CG_ACY_C if cg_acy is None else cg_acy
    atr = ATTR_C if attr_c is None else attr_c
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
    # F7 夹具完备性：没有这两句，F7b 的「两向」就只剩单向
    if "void leaf(void) { hub(); }" not in cgy:
        probs.append("R2 cg_cyc.c 里找不到 `hub ⇄ leaf` 的**反向**那条边 —— "
                     "F7b 的「必须报出环」变成空断言")
    if "void hub(void) { helper(); leaf(); }" not in cgy:
        probs.append("R2 cg_cyc.c 里找不到环的**正向**那条边")
    if len(cga.strip().splitlines()) != 3:
        probs.append("R2 cg_acy.c 的形状变了（应为 3 级无环链）—— "
                     "F7b 的「无环必须报空」需要一条确定的链作证")
    for rel, text in fixtures:
        if not text.strip():
            probs.append("R2 夹具 %s 是空的" % rel)
    # F8 夹具完备性：四类类型定义与三类真函数**都必须在**。
    # 少了任一侧，F8a/F8b 就退化成空断言（永远绿，且没人告诉你）。
    for marker, why in (
            ("typedef struct __attribute__((packed, aligned(4))) {",
             "F8a 的 typedef+struct 形态"),
            ("struct __attribute__((packed)) {\n",
             "F8a 的匿名 struct 形态"),
            ("union __attribute__((aligned(8))) {", "F8a 的 union 形态"),
            ("enum __attribute__((packed)) {", "F8a 的 enum 形态"),
            ("__attribute__((weak,unused,section", "F8 的「属性行独占一行」形态"),
            ("static __attribute__((unused)) int get_attribute(void)",
             "F8b 的「名字里带 attribute」对手方"),
            ("static __attribute__((aligned(4))) int aligned_fn(void)",
             "F8c 的「组内有函数样参数」形态"),
            ("missing_extern();", "F8d 的「真未解析调用」对手方"),
            ("DPT(typedef)", "F8b 的「无分号宏调用 + 实参 typedef」形态"
                             "（防过度收窄：不得吃掉后面的真函数）"),
            ("BTF_ID(typedef, S)", "F8b 的同族第二形态")):
        if marker not in atr:
            probs.append("R2 attr.c 里找不到 %s（`%s`）—— 那条判据变成空断言"
                         % (why, marker))
    return probs


def judge_ratchet(n_funcs):
    """棘轮：登记值必须**等于**真实值（删掉一整个家族而不改数字 ⇒ 红）。"""
    probs = []
    for tag, got, want in (("判据条数", len(CRITERIA), EXPECTED_CRITERIA),
                           ("夹具数", len(FIXTURES), EXPECTED_FIXTURES),
                           ("调用关系夹具数", len(CG_FIXTURES),
                            EXPECTED_CG_FIXTURES),
                           ("属性夹具数", len(ATTR_FIXTURES),
                            EXPECTED_ATTR_FIXTURES),
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
# F7：调用关系的有界投影（R86-3）
# ---------------------------------------------------------------------------
def judge_callrel(obs):
    """F7 的**纯函数**判据。`obs` 由 `scan_callrel` 从公开 CLI 产物里取出来。

    读的是「产物说了什么」，不是「代码里写了什么」—— 这样每一条都能被一个
    只改产物的突变体点亮（例如把 `hit_node_cap` 恒置 False）。
    """
    probs = []
    if not isinstance(obs, dict):
        return ["F7 判据载体不是字典（scan_callrel 的返回值坏了）"]

    # F7a 两本账对账：两个独立容器数同一件事
    ne = obs.get("n_edges_json")
    et = obs.get("edges_total")
    if ne is None or et is None:
        probs.append("F7a 拿不到两本账（--json 的 edges / call_relations.edges_total）")
    elif ne != et:
        probs.append("F7a 两本账对不上：--json 的 edges=%s，"
                     "call_relations.edges_total=%s" % (ne, et))

    # F7b 环，两向
    cyc = obs.get("cycles_cyc")
    mem = []
    if isinstance(cyc, list):
        for c in cyc:
            if isinstance(c, dict) and c.get("size") == 2:
                mem.append(tuple(sorted(c.get("members") or [])))
    if not mem:
        probs.append("F7b 有环夹具里找不到 size=2 的环（读到的 cycles=%r）" % (cyc,))
    elif tuple(sorted(CG_WANT_CYCLE)) not in mem:
        probs.append("F7b 报出的 size=2 环是 %r，期望里没有 %r"
                     % (mem, tuple(sorted(CG_WANT_CYCLE))))
    if obs.get("cycles_acy") != []:
        probs.append("F7b 无环夹具必须报 cycles == []，读到 %r"
                     % (obs.get("cycles_acy"),))
    if obs.get("computed_acy") is not True:
        probs.append("F7b 无环夹具的 cycles_computed 必须为真（空结果与"
                     "「没算」是两回事），读到 %r" % (obs.get("computed_acy"),))

    # F7c 有界且诚恳
    if obs.get("nodes_cap") != 2:
        probs.append("F7c --callgraph-max-nodes 2 时节点数应为 2，读到 %r"
                     % (obs.get("nodes_cap"),))
    if obs.get("cap_hit_cap") is not True:
        probs.append("F7c 触到上限却没标 hit_node_cap=True（读到 %r）—— "
                     "这是「把截断说成全量」的入口" % (obs.get("cap_hit_cap"),))
    if obs.get("cap_hit_default") is not False:
        probs.append("F7c 未触上限却标了 hit_node_cap=True（读到 %r）"
                     % (obs.get("cap_hit_default"),))
    shown = obs.get("fan_in_shown")
    tlen = obs.get("fan_in_top_len")
    if shown is None or tlen is None or shown != tlen:
        probs.append("F7c truncated.fan_in_shown=%r 与实际给出的 %r 条不符"
                     % (shown, tlen))

    # F7d 深度真的起作用
    d1 = obs.get("depth1_nodes")
    d2 = obs.get("depth2_nodes")
    if d1 is None or d2 is None:
        probs.append("F7d 拿不到两个深度的节点集合")
    elif set(d1) == set(d2):
        probs.append("F7d depth=1 与 depth=2 的节点集合相同（%r）—— "
                     "那个开关是个摆设" % (sorted(set(d1)),))
    elif not set(d1) < set(d2):
        probs.append("F7d depth=2 的节点不是 depth=1 的**超集**：%r vs %r"
                     % (sorted(set(d1)), sorted(set(d2))))

    # F7e 未知扩展名不许静默降级
    if obs.get("bad_rc") in (0, None):
        probs.append("F7e 未知扩展名（.txt）居然退出了 %r —— 静默降级"
                     % (obs.get("bad_rc"),))
    if obs.get("bad_exists"):
        probs.append("F7e 未知扩展名居然还是写出了文件 —— 不许静默改成 JSON")

    # F7f 口径写成字面量
    if obs.get("identity") != "callee-name":
        probs.append("F7f identity 必须是字面量 'callee-name'，读到 %r"
                     % (obs.get("identity"),))
    lim = obs.get("limitations")
    if not isinstance(lim, list) or len(lim) < 3 or not all(lim):
        probs.append("F7f limitations 必须至少 3 条且非空，读到 %r" % (lim,))
    elif not any("假阳性" in str(x) for x in lim):
        probs.append("F7f 必须明说「同名合并 ⇒ 环可能含假阳性」—— "
                     "这是本投影最容易被误读的地方")
    return probs


def judge_attr(obs):
    """F8（R87）的**纯函数**判据：属性说明符既不是定义、也不是调用。

    同样「读产物说了什么」，不读代码里写了什么 —— 每一条都能被一个只改
    产物的突变体点亮。
    """
    probs = []
    if not isinstance(obs, dict):
        return ["F8 判据载体不是字典（scan_attr 的返回值坏了）"]

    names = obs.get("names")
    # F8a 类型定义不产函数
    if names is None:
        probs.append("F8a 拿不到函数名表（--json 载荷坏了）")
    elif "__attribute__" in names:
        probs.append("F8a `typedef struct __attribute__((…)) {` 被当成了函数"
                     "定义 —— 实得名字表 %r" % (sorted(names),))
    # F8b 真函数一个不丢（含名字里带 attribute 的、含属性组内参数的）
    if names is not None and sorted(names) != sorted(ATTR_WANT_FUNCS):
        probs.append("F8b 真函数集合应当恰为 %r，实得 %r"
                     % (sorted(ATTR_WANT_FUNCS), sorted(names)))

    # F8c 属性组内**任何**名字都不许算调用
    calls = obs.get("calls")
    if not isinstance(calls, dict):
        probs.append("F8c 拿不到每个函数的调用表")
    else:
        bad = sorted(set(
            c for cs in calls.values() for c in cs
            if c in ("__attribute__", "__attribute", "aligned")))
        if bad:
            probs.append("F8c 属性说明符/组内参数被算成了调用：%r —— "
                         "`aligned(4)` 这类参数在正则层与调用同形，只能整组屏蔽"
                         % (bad,))

    # F8d 未解析：属性泄漏一条不许有、真对手方一条不许少、噪声必须被登记、
    # 两本账必须互相对上（**不写死数字** ⇒ 断言自维持）
    un = obs.get("unresolved")
    ut = obs.get("unresolved_total")
    if un is None or ut is None:
        probs.append("F8d 拿不到未解析读数的两本账")
    else:
        us = set(un)
        leak = sorted(n for n in us
                      if n in ("__attribute__", "__attribute", "aligned"))
        if leak:
            probs.append("F8d 属性说明符/组内参数泄漏进了未解析：%r —— "
                         "假的（属性泄漏）与真的（外部函数）必须能分开" % (leak,))
        for w in ATTR_WANT_UNRESOLVED:
            if w not in us:
                probs.append("F8d %r 这条**真**未解析调用丢了（对手方消失）"
                             % (w,))
        noise = sorted(us - set(ATTR_WANT_UNRESOLVED))
        if noise != sorted(ATTR_KNOWN_UNRESOLVED_NOISE):
            probs.append("F8d 未登记的未解析读数 %r（登记的是 %r）—— "
                         "宏调用未展开是已知边界，但**变化必须被看见**"
                         % (noise, sorted(ATTR_KNOWN_UNRESOLVED_NOISE)))
        if ut != len(un):
            probs.append("F8d 两本账对不上：投影计数 %r vs 明细 %d 条"
                         % (ut, len(un)))

    # F8e 产物级：图／投影正文里**一个字**都不许出现（交付物而非代码）
    for key, want, why in (("cg_text_attr", 0, "`__attribute__`"),
                           ("cg_text_aligned", 0, "属性组内参数 `aligned`")):
        got = obs.get(key)
        if got is None:
            probs.append("F8e 拿不到 %s 在产物正文里的出现次数" % why)
        elif got != want:
            probs.append("F8e 调用关系产物正文里出现了 %d 次 %s —— "
                         "这是用户直接看到的东西" % (got, why))
    ne, et = obs.get("n_edges_json"), obs.get("edges_total")
    if ne != ATTR_WANT_N_EDGES or et != ATTR_WANT_N_EDGES:
        probs.append("F8e 边数应当恰为 %d（夹具里只有一条真边），"
                     "实得 --json=%r / call_relations=%r"
                     % (ATTR_WANT_N_EDGES, ne, et))

    # F8f 边界必须被**显式声明**（判据在文档里，不是代码里）
    miss = obs.get("doc_missing")
    if miss is None:
        probs.append("F8f 拿不到文档检查结果")
    elif miss:
        probs.append("F8f %s 里缺少边界声明 %r —— 「不做也不静默」这条口径"
                     "要求边界落在文档上" % (ATTR_DOC, list(miss)))
    return probs


def scan_callrel(root, python_exe):
    """建两组调用关系夹具 → 跑公开 CLI → 取产物 → 交给 `judge_callrel`。

    返回 ``(probs, n_runs)``；``probs is None`` 表示**缺输入**。
    """
    base = tempfile.mkdtemp(prefix="r86cg_")
    try:
        cyc_dir = os.path.join(base, "cyc")
        acy_dir = os.path.join(base, "acy")
        os.makedirs(cyc_dir)
        os.makedirs(acy_dir)
        for d, fx in ((cyc_dir, (CG_FIXTURES[0],)), (acy_dir, (CG_FIXTURES[1],))):
            for rel, text in fx:
                with io.open(os.path.join(d, rel), "w", encoding="utf-8",
                             newline="") as fh:
                    fh.write(text)

        def run(work, extra):
            argv = [python_exe, "matlabc.py", work, "--lang", "c",
                    "--checks", "none"] + list(extra)
            p = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=CLI_TIMEOUT)
            return p.returncode

        def load(path):
            if not os.path.isfile(path):
                return None
            with io.open(path, "rb") as fh:
                try:
                    return json.loads(fh.read().decode("utf-8", "replace"))
                except ValueError:
                    return None

        j_cyc = os.path.join(base, "cyc.json")
        c_cyc = os.path.join(base, "cyc_cg.json")
        if run(cyc_dir, ["--json", j_cyc, "--callgraph", c_cyc]) != 0:
            return None, 0
        pay_j = load(j_cyc)
        pay_c = load(c_cyc)
        if not isinstance(pay_j, dict) or not isinstance(pay_c, dict):
            return None, 0
        rel = pay_c.get("call_relations")
        if not isinstance(rel, dict):
            return None, 0

        d1 = os.path.join(base, "d1.json")
        d2 = os.path.join(base, "d2.json")
        cap = os.path.join(base, "cap.json")
        for path, dep in ((d1, "1"), (d2, "2")):
            if run(cyc_dir, ["--callgraph", path, "--callgraph-focus", "hub",
                             "--callgraph-depth", dep]) != 0:
                return None, 0
        if run(cyc_dir, ["--callgraph", cap, "--callgraph-focus", "hub",
                         "--callgraph-depth", "9",
                         "--callgraph-max-nodes", "2"]) != 0:
            return None, 0

        a_j = os.path.join(base, "acy.json")
        a_c = os.path.join(base, "acy_cg.json")
        if run(acy_dir, ["--json", a_j, "--callgraph", a_c]) != 0:
            return None, 0
        pay_a = load(a_c)
        if not isinstance(pay_a, dict):
            return None, 0

        bad = os.path.join(base, "bad.txt")
        bad_rc = run(cyc_dir, ["--callgraph", bad])

        def nodes_of(p):
            sub = (p or {}).get("focus_subgraph") or {}
            return sorted(n.get("name") for n in (sub.get("nodes") or []))

        def sub_of(p):
            return (p or {}).get("focus_subgraph") or {}

        obs = {
            "n_edges_json": len(pay_j.get("edges") or []),
            "edges_total": rel.get("edges_total"),
            "identity": rel.get("identity"),
            "limitations": rel.get("limitations"),
            "cycles_cyc": rel.get("cycles"),
            "cycles_acy": ((pay_a.get("call_relations") or {}).get("cycles")),
            "computed_acy": ((pay_a.get("call_relations") or {})
                             .get("cycles_computed")),
            "cap_hit_default": (sub_of(pay_c).get("truncated") or {})
                               .get("hit_node_cap"),
            "fan_in_shown": (rel.get("truncated") or {}).get("fan_in_shown"),
            "fan_in_top_len": len(rel.get("fan_in_top") or []),
            "depth1_nodes": nodes_of(load(d1)),
            "depth2_nodes": nodes_of(load(d2)),
            "nodes_cap": len((sub_of(load(cap)).get("nodes") or [])),
            "cap_hit_cap": (sub_of(load(cap)).get("truncated") or {})
                           .get("hit_node_cap"),
            "bad_rc": bad_rc,
            "bad_exists": os.path.exists(bad),
        }
        return judge_callrel(obs), 6
    finally:
        shutil.rmtree(base, ignore_errors=True)


def scan_attr(root, python_exe):
    """建 F8 夹具 → 跑公开 CLI（`--json` + `--callgraph`）→ 交给 `judge_attr`。

    返回 ``(probs, n_runs)``；``probs is None`` 表示**缺输入**。
    文档声明（F8f）也在这里读 —— 它和夹具一样是判据的**载体**：
    载体读不到就是缺输入，不能算「没问题」。
    """
    base = tempfile.mkdtemp(prefix="r87attr_")
    try:
        src = os.path.join(base, "src")
        os.makedirs(src)
        for rel, text in ATTR_FIXTURES:
            with io.open(os.path.join(src, rel), "w", encoding="utf-8",
                         newline="") as fh:
                fh.write(text)
        j = os.path.join(base, "attr.json")
        c = os.path.join(base, "attr_cg.json")
        argv = [python_exe, "matlabc.py", src, "--lang", "c",
                "--checks", "none", "--json", j, "--callgraph", c]
        p = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=CLI_TIMEOUT)
        if p.returncode != 0:
            return None, 0
        pay_j = _load_json(j)
        pay_c = _load_json(c)
        if not isinstance(pay_j, dict) or not isinstance(pay_c, dict):
            return None, 0

        dpath = os.path.join(root, ATTR_DOC)
        if not os.path.isfile(dpath):
            return None, 0
        with io.open(dpath, "rb") as fh:
            dtext = fh.read().decode("utf-8", "replace")
        with io.open(c, "rb") as fh:
            raw = fh.read().decode("utf-8", "replace")

        names = []
        calls = {}
        for pf in (pay_j.get("files") or []):
            for fn in (pf.get("functions") or []):
                names.append(fn.get("name"))
                calls[fn.get("name")] = [x[0] for x in (fn.get("calls") or [])
                                         if x]
        rel = pay_c.get("call_relations") or {}
        obs = {
            "names": names,
            "calls": calls,
            "unresolved": [u.get("callee")
                           for u in (pay_j.get("unresolved") or [])],
            "unresolved_total": rel.get("unresolved_total"),
            "n_edges_json": len(pay_j.get("edges") or []),
            "edges_total": rel.get("edges_total"),
            "cg_text_attr": raw.count("__attribute__"),
            "cg_text_aligned": raw.count("aligned"),
            "doc_missing": [m for m in ATTR_DOC_MARKERS if m not in dtext],
        }
        return judge_attr(obs), 2
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _load_json(path):
    """读 JSON；坏输入返回 None（**不许**把「读不到」当成「没问题」）。"""
    if not os.path.isfile(path):
        return None
    with io.open(path, "rb") as fh:
        try:
            return json.loads(fh.read().decode("utf-8", "replace"))
        except ValueError:
            return None


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

    try:
        cg_probs, _n_runs = scan_callrel(root, sys.executable)
    except (OSError, subprocess.SubprocessError) as e:
        print("check_c_frontend_shapes: 调用关系夹具的公开 CLI 跑不起来：%s"
              "（缺输入 → 红）" % e)
        return 2
    if cg_probs is None:
        print("check_c_frontend_shapes: 调用关系投影没有产出可解析的 JSON"
              "（--callgraph 是 F7 的载体 → 缺输入）")
        return 2

    try:
        at_probs, _n_attr = scan_attr(root, sys.executable)
    except (OSError, subprocess.SubprocessError) as e:
        print("check_c_frontend_shapes: 属性夹具的公开 CLI 跑不起来：%s"
              "（缺输入 → 红）" % e)
        return 2
    if at_probs is None:
        print("check_c_frontend_shapes: 属性夹具/文档声明没产出可解析的载体"
              "（--json / --callgraph / %s 都是 F8 的载体 → 缺输入）" % ATTR_DOC)
        return 2

    probs = (list(probs) + judge_fixtures() + judge_ratchet(n_funcs)
             + cg_probs + at_probs)
    if probs:
        for p in probs:
            print("check_c_frontend_shapes: " + p)
        print("check_c_frontend_shapes: %d 项违规" % len(probs))
        return 1
    print("check_c_frontend_shapes: OK（%d 个形态夹具 + %d 个调用关系夹具 + "
          "%d 个属性夹具 / 公开 CLI 认出 %d 个函数 / %s 全绿 + 夹具完备性 + 棘轮）"
          % (len(FIXTURES), len(CG_FIXTURES), len(ATTR_FIXTURES), n_funcs,
             ROW_SIGNATURE))
    return 0


# ---------------------------------------------------------------------------
# 两向自证：坏样本必须红在**指定**判据上，好样本必须全绿
# ---------------------------------------------------------------------------
def _selftest():
    """`bad` 数的是**本装置自己的失误**：坏样本没红、或红在了别的判据上。"""
    bad = [0]
    good = [0]
    witnessed = set()
    witnessed_sub = set()

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

    # ---- F7：调用关系的有界投影（吃的是一个纯 dict，与文件系统无关） ----
    def _obs():
        """好观测：F7 六条子判据必须**全部**在这份观测上绿。"""
        return {
            "n_edges_json": 6, "edges_total": 6,
            "identity": "callee-name",
            "limitations": ["甲：同名合并 ⇒ 调用环可能含**假阳性**",
                            "乙：unresolved 不在图里",
                            "丙：截断是显式的"],
            "cycles_cyc": [{"size": 2, "members": ["hub", "leaf"]}],
            "cycles_acy": [], "computed_acy": True,
            "cap_hit_default": False, "fan_in_shown": 4, "fan_in_top_len": 4,
            "depth1_nodes": ["hub", "leaf"],
            "depth2_nodes": ["hub", "leaf", "helper"],
            "nodes_cap": 2, "cap_hit_cap": True,
            "bad_rc": 1, "bad_exists": False,
        }

    def red_cg(tag, obs, want):
        probs = judge_callrel(obs)
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

    green("好样本：F7 观测六条子判据全绿", judge_callrel(_obs()))

    for tag, patch in (
            ("F7a 两本账对不上（edges 少一条）", {"n_edges_json": 5}),
            ("F7b 有环夹具里环整类消失", {"cycles_cyc": []}),
            ("F7b 有环夹具报错了环的成员",
             {"cycles_cyc": [{"size": 2, "members": ["hub", "side"]}]}),
            ("F7b 无环夹具却报出环",
             {"cycles_acy": [{"size": 3, "members": ["a", "b", "c"]}]}),
            ("F7b 无环夹具把「没算」说成「没有」（computed=False）",
             {"computed_acy": False}),
            ("F7c 节点数越界（上限 2 却给 3 个）", {"nodes_cap": 3}),
            ("F7c 触上限却没标 hit_node_cap", {"cap_hit_cap": False}),
            ("F7c 未触上限却标了 hit_node_cap", {"cap_hit_default": True}),
            ("F7c truncated 的 shown 与实物不符", {"fan_in_shown": 9}),
            ("F7d depth 开关是摆设（1 与 2 同集合）",
             {"depth2_nodes": ["hub", "leaf"]}),
            ("F7d depth=2 不是 depth=1 的超集",
             {"depth1_nodes": ["hub", "leaf"], "depth2_nodes": ["hub", "other"]}),
            ("F7e 未知扩展名静默降级（rc=0）", {"bad_rc": 0}),
            ("F7e 未知扩展名还是写出了文件", {"bad_exists": True}),
            ("F7f 身份口径被悄悄换掉", {"identity": "definition-site"}),
            ("F7f limitations 缩水到 2 条", {"limitations": ["甲", "乙"]}),
            ("F7f 没明说「同名合并 ⇒ 假阳性」",
             {"limitations": ["甲：不跟踪运行期绑定", "乙：不展开运行期", "丙：有上限"]}),
    ):
        d = _obs()
        d.update(patch)
        red_cg("坏样本 %s" % tag, d, "F7")

    # ---- F8：属性说明符既不是定义、也不是调用（同样吃纯 dict） ----
    def _obs_attr():
        """好观测：F8 六条子判据必须**全部**在这份观测上绿。"""
        return {
            "names": list(ATTR_WANT_FUNCS),
            "calls": {"decl_then_attr": [], "get_attribute": [],
                      "aligned_fn": [],
                      "attr_caller": ["get_attribute", "missing_extern"]},
            "unresolved": (list(ATTR_KNOWN_UNRESOLVED_NOISE)
                           + list(ATTR_WANT_UNRESOLVED)),
            "unresolved_total": (len(ATTR_WANT_UNRESOLVED)
                                 + len(ATTR_KNOWN_UNRESOLVED_NOISE)),
            "n_edges_json": ATTR_WANT_N_EDGES,
            "edges_total": ATTR_WANT_N_EDGES,
            "cg_text_attr": 0, "cg_text_aligned": 0,
            "doc_missing": [],
        }

    def red_at(tag, obs, want):
        """坏样本必须红在 `want` 上，且不红在**别的判据族**上。

        ⚠ 粒度是**族**：F8a/F8b 读的是同一份 `names`，改它必然同时点亮两条，
        要求逐条互斥会造出一个永远失败的自证装置（量具自伤，不是对象错）。
        """
        probs = judge_attr(obs)
        hit = [p for p in probs if p.startswith(want)]
        others = [p for p in probs
                  if p[:2] in CRITERIA_IDS and not p.startswith(want)]
        for p in hit:
            witnessed_sub.add(p[:3])
        if not hit:
            bad[0] += 1
            print("  [selftest] %s 未被 %s 抓到（实得 %r）" % (tag, want, probs))
        elif others:
            bad[0] += 1
            print("  [selftest] %s 红在了别的判据上：%r" % (tag, others))
        else:
            good[0] += 1
            witnessed.add(want)

    green("好样本：F8 观测六条子判据全绿", judge_attr(_obs_attr()))

    for tag, patch in (
            ("F8a 类型定义产出了假函数",
             {"names": ["__attribute__"] + list(ATTR_WANT_FUNCS)}),
            ("F8b 真函数被整类丢掉（只剩两个）",
             {"names": ["get_attribute", "attr_caller"]}),
            ("F8b 过度收窄：宏实参里的 typedef 吃掉两个真函数",
             {"names": [n for n in ATTR_WANT_FUNCS
                        if n not in ("__resolve_symbol",
                                     "process_subrange_type")]}),
            ("F8c 属性头被算成调用",
             {"calls": {"decl_then_attr": [], "aligned_fn": [],
                        "get_attribute": ["__attribute__"],
                        "attr_caller": ["get_attribute", "missing_extern"]}}),
            ("F8c 组内参数被算成调用",
             {"calls": {"decl_then_attr": [], "get_attribute": [],
                        "aligned_fn": ["aligned"],
                        "attr_caller": ["get_attribute", "missing_extern"]}}),
            ("F8d 属性泄漏进了未解析",
             {"unresolved": ["missing_extern", "aligned"]}),
            ("F8d 两本账对不上（载荷说 1，投影说 0）",
             {"unresolved_total": 0}),
            ("F8d 未登记的噪声跑进了未解析",
             {"unresolved": ["BTF_ID", "DPT", "missing_extern",
                             "unknown_macro"],
              "unresolved_total": 4}),
            ("F8e 产物正文里出现属性名", {"cg_text_attr": 3}),
            ("F8e 产物正文里出现组内参数名", {"cg_text_aligned": 1}),
            ("F8e 边数被算多（假边进了图）", {"edges_total": 3}),
            ("F8f 文档没声明这条边界", {"doc_missing": ["不是调用"]}),
    ):
        d = _obs_attr()
        d.update(patch)
        red_at("坏样本 %s" % tag, d, "F8")

    for letter in ("F8a", "F8b", "F8c", "F8d", "F8e", "F8f"):
        if letter not in witnessed_sub:
            bad[0] += 1
            print("  [selftest] F8 的子判据 %s 没有自己的坏样本（子覆盖静默缩水）"
                  % letter)

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
    # F7 夹具完备性**两向**：抽掉环的反向边 / 把无环链改短 ⇒ 各自必须报红
    if judge_fixtures(cg_cyc="void hub(void) { helper(); leaf(); }\n"):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] cg_cyc.c 被抽掉环的反向边后 R2 不报红"
              "（F7b 的「必须报出环」退化成空断言）")
    if judge_fixtures(cg_acy="void a(void) { }\n"):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] cg_acy.c 的形状被改后 R2 不报红")
    # F8 夹具完备性**两向**：抽掉类型定义 / 抽掉真未解析对手方 ⇒ 各自必须报红
    if judge_fixtures(attr_c=ATTR_C.replace(
            "typedef struct __attribute__((packed, aligned(4))) {\n", "")):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] attr.c 被抽掉 `typedef struct __attribute__` 后"
              " R2 不报红（F8a 的「类型定义不产函数」退化成空断言）")
    if judge_fixtures(attr_c=ATTR_C.replace("missing_extern();\n", "")):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] attr.c 被抽掉真未解析调用后 R2 不报红"
              "（F8d 的对手方消失）")
    if judge_fixtures(attr_c=ATTR_C.replace(
            "static __attribute__((aligned(4))) int aligned_fn(void)", "")):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] attr.c 被抽掉「组内有函数样参数」形态后 R2 不报红")
    if judge_fixtures(attr_c=ATTR_C.replace("DPT(typedef)\n", "")):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] attr.c 被抽掉「宏实参 typedef」形态后 R2 不报红"
              "（F8b 的防过度收窄对手方消失）")

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
