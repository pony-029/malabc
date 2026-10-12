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

判据（F1–F10；十条判据的**管辖范围互不重叠**，每条各有自己的突变体作独立证人）：
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
       F7b **环，两向**：`cg_cyc.c` 里 `hub ⇄ leaf` 必须被报成 1 个 size=2 的环
           （R88：比较的是**名字投影** —— 默认 `definition-site` 口径下成员渲染成
           `名字 @ 定义文件`；**落点本身由 F9e 守**，所以这不是放宽）；
           `cg_acy.c` 必须报 `cycles == []` 且 `cycles_computed` 为真
           （只断言「有环」会让「永远报空」也绿）。
       F7c **有界且诚恳**：`--callgraph-max-nodes 2` ⇒ 节点恰 2 个且
           `hit_node_cap` 为真；默认大上限 ⇒ 为假。且 `truncated.fan_in_shown`
           必须 == 实际给出的 `fan_in_top` 条数（数字与实物对账，不许说谎）。
       F7d **深度真的起作用**：`--callgraph-depth 1` 与 `2` 的节点集合必须不同
           （否则那个开关是个摆设，而摆设型开关没有任何东西会告诉你它是摆设）。
       F7e **未知扩展名不许静默降级**：`--callgraph x.txt` 必须**非零退出**，
           且**不得**产出该文件（静默改成 JSON 就是「没听懂却假装听懂」）。
       F7f **口径与它的局限必须一起写下来**（R88 建 / R89 扩到三个字面量）：
           `identity` 必须是声明的**三个**字面量之一；`limitations` 至少 3 条且
           非空，**并且必须说清**本口径自己的局限 —— 名字级必须明说「同名合并 ⇒
           环可能含假阳性」，定义落点必须明说「被调侧的歧义**判不出来**（不猜）
           ⇒ 经过它的环会**漏报**」，新口径（R89）还必须明说它的**规则**本身
           （同文件优先 / `include` 闭包）与「判不出来的部分照样不猜」。
           口径换了而局限没换 ⇒ 红（那是「把旧口径的免责声明贴在新口径上」）。
  F9 节点身份口径（R88）：F7f 管「口径与局限都写下来了」，这一族管口径**行为本身**。
     内核实测：名字级口径下 `cross_file.ambiguous` 占 72.9%，最大「调用环」有 37,775
     个成员 —— 那不是真环，是**同名合并**（同名 `static` 函数分处不同文件）造出来的。
     跨区域语料实测：最大环 1750 -> 36，而**边数一条不变**（68030 -> 68030）。
     五个半边，各有自己的坏样本：
       F9a **默认口径 = `definition-site`**（静默换口径 ⇒ 红）。
       F9b 老口径 `callee-name` **仍可显式选中**且如实回显；未知值**非零退出且不产
           文件**（静默退回默认 = 没听懂却假装听懂）；形状版本随键集合一起涨；
           焦点子图的 `focus_candidates` 在两口径下都在。
       F9c **反向**：两条口径的 `edges_total` 相等且都等于 `--json` 里的边数 ——
           拆节点**不许吃掉任何一条边**（这是 F9d 的对手方）。
       F9d **活性**：同名不同文件的夹具上最大环必须**塌**、节点数必须**更多**。
       F9e **惰性**：没有同名可拆的夹具上两口径必须**逐位相同**，且环成员必须
           **带落点**（否则同名不同文件的成员分不开）。

  F10 同文件 / 包含闭包**阶梯**（R89）：F9 管「换身份口径」，这一族管「同名多
     定义时按 C 的翻译单元可见性**判得出就判**」。R88 把这一整桶留成了 K_AMB 汇点，
     R89 收回可判定的那部分 —— 所以这一族必须同时给出**正向**（真环被收回）与
     **反向**（no-op / 只重分类 / 语言门）两边的证据：
       F10a **三口径边账**相等且等于载荷边数（加口径不许吃边）。
       F10b **活性且不越界**：同名不同文件夹具上新口径报出的环必须**更多**、
           每个环的成员必须**同文件**、最大环不许超过名字级。
       F10c **惰性**：无同名可消歧时与纯定义落点逐位相同（阶梯是 no-op）。
       F10d **只做重分类**：`resolution` 各档之和 == `edges_total`，且三口径的
           `unique`/`external` 逐位相同 —— 「救回数」的分母被钉住。
       F10e **语言门**：非 C 语料上 `applied=false` 且读数与纯定义落点逐位相同。

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
    0 = F1–F10 全绿，且棘轮与夹具完备性全绿
    1 = 有违规（某条判据红 / 棘轮不符 / 夹具被改瘦）
    2 = 缺输入（找不到 matlabc.py / 公开 CLI 跑不起来 / JSON 不可解析）

用法：
    python tools/check_c_frontend_shapes.py             # 0=全绿 1=违规 2=缺输入
    python tools/check_c_frontend_shapes.py --selftest   # 两向自证
    python tools/check_c_frontend_shapes.py --help       # 显示本帮助
"""
import argparse
import ast
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
ROW_SIGNATURE = "F1–F10"

# H3（R73）：越出签名族、但仍由本门发出的判据前缀。
ROW_EXTRA = "R1,R2"
# 公开 CLI 的墙钟上限。实测一次 ≈0.5s，300s 是给「机器正忙」留的量级余量；
# 它的意义是「让挂死变成红，而不是让门永远等着」。
CLI_TIMEOUT = 300.0

# F7f 要核的**口径字面量**（与 `callrel.py` 的常量同义；这里写成自己的字面量，
# 因为 `tools/` 不 import 产品模块 —— 宁可另写同义实现，R54/R55 的纪律）。
# 写成元组而不是集合：报错时要按声明顺序印出来。
IDENTITY_NAME_LIT = "callee-name"
IDENTITY_DEFSITE_LIT = "definition-site"
# R89：默认口径。它比定义落点多一条**推导**（同名多定义时按 C 的翻译单元可见性
# 判两级：同文件优先 → #include 闭包三明治）。这里写成自己的字面量、不 import
# 产品模块 —— `tools/` 不 import 产品的纪律（R54/R55）。
IDENTITY_LOCAL_LIT = "definition-site-local"
DECLARED_IDENTITIES = (IDENTITY_NAME_LIT, IDENTITY_DEFSITE_LIT, IDENTITY_LOCAL_LIT)

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

# ---------------------------------------------------------------------------
# F9（R88）夹具：**同名不同文件**的 `static` 函数 —— 名字级口径会把它们合并成
# 一个节点，于是两份文件之间凭空长出一个跨文件环。
#
# 为什么这个小夹具能把两种口径**分开**（手推，独立于产品）：
#   名级：调用点 4 个，但 `h(...)` 在 func_index 里有**两份定义** ⇒ 每个 h 调用点
#         各扇出 2 条边（a→h ×2、b→h ×2），再加 h→a、h→b ⇒ **边 6 条**
#         ⇒ 节点 {a,h,b} 全在一个 SCC 里 ⇒ 最大环 3
#         ⚠ 「4」与「6」的差**是实测出来的**：`_r82/append_rounds_r88.py` 现跑夹具读到
#         名字级 `edges_total=6`。手推若只数「调用点」就会漏掉**扇出** —— 这正是
#         F7a/F9c 要并列两本账（载荷 `edges` 长度 vs `call_relations.edges_total`）
#         的理由：口径错时两边一起错，只有并列才看得见。
#   落点：h 有两份定义（dup_a.c / dup_b.c）⇒ **被调侧**判不出是哪一份 ⇒ K_AMB 汇点
#         ⇒ K_DEF(a.c,h)→K_DEF(a.c,a)→K_AMB(h)；K_DEF(b.c,h)→K_DEF(b.c,b)→K_AMB(h)
#         ⇒ 一个环都没有 ⇒ 最大环 0，而节点数 5 > 3（拆开了）
#   ⇒ F9d 的两个半边（**环必须塌** + **节点必须更多**）各有实物。
#   而 F9e 用上面已有的 cg_cyc.c 当**惰性**对照（那里没有同名不同文件 ⇒ 必须逐位相同）。
# 少了任一侧，两条判据里就有一条变成空断言（永远绿且没人告诉你）。
# ---------------------------------------------------------------------------
CG_DUP_FIXTURES = (
    ("cg_dup_a.c",
     "static void a(void) { h(); }\n"
     "static void h(void) { a(); }\n"),
    ("cg_dup_b.c",
     "static void b(void) { h(); }\n"
     "static void h(void) { b(); }\n"),
)

# ---------------------------------------------------------------------------
# F10（R89）夹具：**Python** 语料 —— 语言门的对手方。
#
# 为什么必须有这一档：R89 的阶梯只在 C 上启用（理由见 `_limitations_local`：
# C 的可见性由翻译单元决定，可判定；Python 的模块绑定能在运行时被 import 改掉）。
# 若有人把门拆了（阶梯对 Python 也生效），这份夹具上会同 dup 夹具一样长出
# **两个同文件环** ⇒ F10e 的「逐位相同」当场红。
# 没有这一档，F10e 就只能在 C 语料上自说自话（空断言）。
#
# 手推（独立于产品）：`h` 在 p_a.py / p_b.py 各一份定义 ⇒ 每个调用点扇出 2 条边
# ⇒ 4 条边；被调侧判不出 ⇒ K_AMB 汇点 ⇒ 环 0 个、节点 3 个（a@a、b@b、h@汇点）。
# ---------------------------------------------------------------------------
CG_PY_FIXTURES = (
    ("cg_py_a.py", "def h():\n    pass\n\n\ndef a():\n    h()\n"),
    ("cg_py_b.py", "def h():\n    pass\n\n\ndef b():\n    h()\n"),
)

# ---------------------------------------------------------------------------
# F10（R89）夹具 ③④：**第二级**（翻译单元）的对手方。
#
# 为什么必须有：`dup` 夹具只行使 rung 1（同文件）。少了这两档，「rung 2 存在」
# 与「rung 2 只对翻译单元根成立」两条声明就**只活在仓库外**（`_r89/` 的探针）
# —— 那正是 R49 的教训：证据在仓外 ⇒ 回归时没有任何东西能说「不」。
# 实测（`_r89/probe_local_scope.py` 的 inc/hdr 两组，102 条断言）：
#   inc 默认口径 include=2 / edges_total=2；纯定义落点 include=0、ambiguous=2。
#   hdr 默认口径 include=0、ambiguous=2、header_callers=2（**自报**没判）。
# ---------------------------------------------------------------------------
CG_INC_FIXTURES = (
    ("t1/m.c", '#include "k.h"\nint m(void) { return h(); }\n'),
    ("t1/k.h", "int h(void) { return 1; }\n"),
    ("t2/k2.h", "int h(void) { return 2; }\n"),
)
# ⚠ R89（由量具 `_r89/measure_incx.py` 逼出来的**一行开关**）：
# `api.h` **必须自己带一个 include**。否则：把 `.h` 也塞进
# `TU_ROOT_EXTS` 会让闭包退化成 `{api.h}` ⇒ 候选 0 份 ⇒ 仍然
# ambiguous ⇒ **门全绿**。加上这一行，同一处注入就变成
# 「候选 0→1、include 0→2」⇒ F10g 当场红。
# 实测（本行加入前后读数**逐位相同**）：include=0 / ambiguous=2 /
# header_callers=2 —— 只加了「可行使性」，没改任何结论。
CG_HDR_FIXTURES = (
    ("t1/api.h", '#include "k.h"\nint api(void) { return h(); }\n'),
    ("t1/k.h", "int h(void) { return 1; }\n"),
    ("t2/k2.h", "int h(void) { return 2; }\n"),
)

# ---------------------------------------------------------------------------
# F10（R89）夹具 ⑤：**三明治**的对手方 —— basename 撞车的**假**包含。
#
# 为什么非有这一档不可（`_r89/measure_incx.py` 预登记实测）：
#   现有的 `inc` 夹具头名 `k.h` 在语料里 basename **唯一** ⇒
#   `under == over` ⇒ 判据松成 `if vu or vo:`（拿**过近似**当真 TU）
#   在它上面读数**完全相同** ⇒ 那条错报此前没有任何对手方。
#   这里 `k.h` 出现在两处 ⇒ `under` 排除它、`over` 并入它 ⇒
#   真 TU 夹在中间、两侧给不出同一份 ⇒ **必须判不出**。
# 实测：默认口径 include=0 / ambiguous=2（== edges_total）/ capped=0；
#       纯定义落点与之一致（它本来就不做作用域推理）。
# ---------------------------------------------------------------------------
CG_INCX_FIXTURES = (
    ("t1/m.c", '#include "k.h"\nint m(void) { return h(); }\n'),
    ("t1/k.h", "int h(void) { return 1; }\n"),
    ("t2/k.h", "int h(void) { return 2; }\n"),
)

# ---------------------------------------------------------------------------
# F10l（R90）：**`rel` 的基准** = 被分析**根**，不是调用者的 cwd。
#
# 为什么非有这一档不可：「`matlabc._rel_of()` 相对当前工作目录算」这个缺陷，
# 现有夹具**没有一个能完整测出来**。R90 实测了两件事，两件都要写下来：
#   ① 把 `_rel_of` 改成根相对之后，本门**真跑**的全部读数**逐位不变**；
#   ② 但变异体 M14 的第一版（只把基准换成 cwd、**不**恢复「`..` ⇒ basename」
#      那条塌陷）在**没有**本档时红在 **F10b** —— 因为 dup 夹具的文件就在语料
#      **根**上，basename 恰好**等于**根相对，两种形态在它上面同形；F10b 的覆盖
#      半边是拿**夹具 rel 名**与产物 rel 比字符串，所以它只对**第三种**形态
#      （`../../…`，即「只换基准、不塌陷」的半拉子注入）敏感。
#      ⇒ 只有本档（同 basename、落在**两个目录**里）能直接测出**塌陷**。
# ⚠ 「判据没有分辨力」与「注入不忠实」是两件事：M14 的第一版看起来像前者，
#   实际是后者。所以注释不能写成「一个也测不出来」。
#
# 这一档 `d1/x.c` 与 `d2/x.c` **同 basename**、各定义一份 `dup`：
#   * `rel` 按**被分析根**算 ⇒ 两个文件是 `d1/x.c` / `d2/x.c` ⇒ `dup` 的两份
#     定义各落在**调用者自己的文件**里 ⇒ 同文件优先（rung 1）判得出 ⇒
#     4 条边**全部** `same_file`、`ambiguous = 0`、节点 4 个。
#   * `rel` 按**调用者的 cwd** 算（门自己就是 `cwd=仓库` + 绝对临时目录的形态）
#     ⇒ 两个文件都塌成 `x.c` ⇒ `dup` 的两份定义挤进同一个 `rel` ⇒ rung 1
#     的「恰一份」不成立、rung 2 又没有 include 可走 ⇒ 4 条边**全部**留歧义、
#     节点 3 个（多出一个汇点）。
# ⚠ 两种形态下 `edges_total` **都是 4** —— 只看边数的判据一条也看不见它。
# ⚠ 手推（独立于产品）：2 文件 / 4 函数 / 2 个调用点各命中 2 份定义 ⇒ 扇出后 4 条边。
# ---------------------------------------------------------------------------
CG_DUPX_FIXTURES = (
    ("d1/x.c", "static int dup(void) { return 1; }\n"
               "int e1(void) { return dup(); }\n"),
    ("d2/x.c", "static int dup(void) { return 2; }\n"
               "int e2(void) { return dup(); }\n"),
)

# ---------------------------------------------------------------------------
# F10j（R89j）：第二级的**代价**不变量 —— 「每个调用者文件只该算两次闭包」。
#
# 为什么必须**多于 8 个**调用者文件：`CLOSURE_CACHE = 8`。R89 的第一版写的是
# `if len(cache) < CLOSURE_CACHE:`，也就是「只记最早 8 个起点、之后**再也不写**」
# —— 缓存永远停在头部那 8 个文件上，第 9 个起点的闭包**每条边都重算**。
# ⚠ 单文件夹具（inc / hdr / incx）**看不出**这个退化：缓存初始为空 ⇒ 第一条边
# 就写进去了，同文件的后续边照样命中。必须凑够 > 8 个**不同**的调用者文件。
#
# 12 个 `.c`（每个两条同名调用边）+ 一份共享头。**R89k 之后**这份夹具同时钉
# 两件事：
#
#   (1) **代价不变量**（F10j）：`rung2_files == 12`、
#       `closure_computed == 2 × rung2_files`（每个文件各算 under/over 一次）。
#       旧写法（满了不写）：前 8 个文件各 2 次 = 16，后 4 个文件的每条边都
#       重算 = 32 ⇒ **48 ≠ 24**，F10j 当场红。
#
#   (2) **`under` 的唯一性口径**（F10k）：`k.h` 被 12 个文件包含，但**只解析
#       到一个目标文件** ⇒ `under` 必须保留它 ⇒ 48 条歧义边**全部**落进
#       `include`。R89k 之前 `include_graphs()` 数的是 include **行数**
#       （`by_base["k.h"] = 12 ≠ 1`）⇒ 整条被丢出 `under` ⇒
#       `include=0 / ambiguous=48`。
#
# ⚠ 这个缺口曾经写在这份注释里当「已知且保守」，并在 F10j 里**刻意不钉**
# （怕钉住弱行为、让下一轮的正确改进变成假红）。真语料上的对账把那个判断
# **推翻**了：欠近似不是「更安全」，而是把这一级的能力砍成 **0**
# （独立量具在 CROSS 档测出 2034 条，引擎一条也判不出来）。
# ---------------------------------------------------------------------------
CG_MULTI_ROOTS = tuple("t1/m%02d.c" % i for i in range(1, 13))

# `under` 图的唯一性口径名（**独立抄一份**：门要能在 `callrel.py` 被改坏时
# 独立证伪它，两处一起改就失去分辨率）。
UNDER_BASIS_WANT = "unique-basename-target"
CG_MULTI_FIXTURES = (
    tuple((rel, '#include "k.h"\nint %s(void) { int a = h(); int b = h();'
                ' return a + b; }\n'
                % os.path.splitext(os.path.basename(rel))[0])
          for rel in CG_MULTI_ROOTS)
    + (("t1/k.h", "int h(void) { return 1; }\n"),
       ("t2/k2.h", "int h(void) { return 2; }\n")))

# F7b 的期望环（手写，独立于产品）：成员集合必须恰是这两个。
CG_WANT_CYCLE = ("hub", "leaf")


def _cycle_names(members):
    """把环成员投影成**名字**（`名字 @ 定义文件` ⇒ `名字`）。

    ⚠ R88：默认口径 `definition-site` 下成员带**落点**（`hub @ cg_cyc.c`）。
    F7b 问的是「哪两个函数成环」，所以只比名字；**落点由 F9e 单独守**
    （那里断言定义落点报出的封环成员必须**带**落点）。这条投影因此有它自己的
    对手方 —— 不是「看不见就当成没有」。
    """
    out = []
    for m in members:
        s = str(m)
        out.append(s.split(" @ ", 1)[0] if " @ " in s else s)
    return out

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
    ("F9", "节点身份口径：默认定义落点 / 老口径可选且非法值报错 / 两口径边账相同 / 同名不同文件处环必须塌（活性）/ 无同名可拆处逐位相同（惰性）且成员带落点"),
    ("F10", "同文件/包含闭包阶梯：三口径边账相等 / 真环被收回且环内同文件且不超过名字级 / 无同名可消歧处逐位相同 / 只做重分类（计数和==边数且 unique+external 不变）/ 非 C 语言上语言门生效 / 第二级的代价不变量（closure_computed == 2×rung2_files，缓存不许退化成重算）/ `under` 图的唯一性口径（按**解析目标数**判、不按 include **行数**，共享头必须判得出来且口径要自报）"),
)
CRITERIA_IDS = tuple(c[0] for c in CRITERIA)

# ---------------------------------------------------------------------------
# 棘轮：全部是「事实的读数」，不是可调参数。覆盖不许静默缩水。
# ---------------------------------------------------------------------------
EXPECTED_CRITERIA = 10
EXPECTED_FIXTURES = 3
EXPECTED_CG_FIXTURES = 2
EXPECTED_DUP_FIXTURES = 2
EXPECTED_PY_FIXTURES = 2        # R89：语言门的语料（两文件同名定义）
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
                   cg_cyc=None, cg_acy=None, attr_c=None, cg_dup=None,
                   cg_py=None):
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
    dup = CG_DUP_FIXTURES if cg_dup is None else cg_dup
    pyf = CG_PY_FIXTURES if cg_py is None else cg_py
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
    # F9 夹具完备性：四条边**逐条**必须在（少一条，F9d 的「环必须塌」就变成
    # 另一件事 —— 它可能只是因为没有环可塌而绿，那是空断言）。
    dtxt = "".join(text for _rel, text in dup)
    for marker, why in (
            ("static void h(void) {", "被调侧那份同名定义"),
            ("static void a(void) { h(); }", "环的正向边 a→h"),
            ("static void h(void) { a(); }", "环的反向边 h→a"),
            ("static void b(void) { h(); }", "第二份文件里的 a→h 同形边"),
            ("static void h(void) { b(); }", "第二份文件里的 h→b")):
        if marker not in dtxt:
            probs.append("R2 重复定义夹具里找不到 %s（`%s`）—— F9d 的「同名不同"
                         "文件 ⇒ 环必须塌」变成空断言" % (why, marker))
    if dtxt.count("static void h(void) {") != 2:
        probs.append("R2 重复定义夹具里 `static void h(void) {` 出现 %d 次"
                     "（要求恰 2 次）—— 少了就没有「同名不同文件」这个前提"
                     % dtxt.count("static void h(void) {"))
    # F10 夹具完备性：两份文件里**各自**必须有 `h` 的定义 + 一个调用点。
    # 少任一侧，「同名不同文件」这个前提就不成立 ⇒ F10b/F10e 退化成空断言。
    ptxt = dict(pyf)
    for rel, fn in (("cg_py_a.py", "def a():\n    h()\n"),
                    ("cg_py_b.py", "def b():\n    h()\n")):
        t = ptxt.get(rel)
        if t is None:
            probs.append("R2 Python 夹具缺 %s —— F10e 的语言门没有对手方" % rel)
            continue
        if "def h():\n" not in t:
            probs.append("R2 Python 夹具 %s 里没有 `def h():` —— 没有同名定义就"
                         "谈不上「同名不同文件」" % rel)
        if fn not in t:
            probs.append("R2 Python 夹具 %s 里没有调用点（%r）—— 阶梯没有边可判"
                         % (rel, fn.strip()))
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
                           ("重复定义夹具数", len(CG_DUP_FIXTURES),
                            EXPECTED_DUP_FIXTURES),
                           ("Python 夹具数", len(CG_PY_FIXTURES),
                            EXPECTED_PY_FIXTURES),
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

    # F7b 环，两向（R88：比较**名字投影**，见 `_cycle_names`）
    cyc = obs.get("cycles_cyc")
    mem = []
    if isinstance(cyc, list):
        for c in cyc:
            if isinstance(c, dict) and c.get("size") == 2:
                mem.append(tuple(sorted(_cycle_names(c.get("members") or []))))
    if not mem:
        probs.append("F7b 有环夹具里找不到 size=2 的环（读到的 cycles=%r）" % (cyc,))
    elif tuple(sorted(CG_WANT_CYCLE)) not in mem:
        probs.append("F7b 报出的 size=2 环（名字投影）是 %r，期望里没有 %r"
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

    # F7f 口径与它的局限必须**一起**写下来（R88：口径换了，局限也得换）
    ident = obs.get("identity")
    lim = obs.get("limitations")
    if ident not in DECLARED_IDENTITIES:
        probs.append("F7f identity 必须是声明的两个字面量之一 %r，读到 %r"
                     % (list(DECLARED_IDENTITIES), ident))
    if not isinstance(lim, list) or len(lim) < 3 or not all(lim):
        probs.append("F7f limitations 必须至少 3 条且非空，读到 %r" % (lim,))
    else:
        _ltxt = " ".join(str(x) for x in lim)
        if ident == IDENTITY_NAME_LIT and "假阳性" not in _ltxt:
            probs.append("F7f 名字级口径必须明说「同名合并 ⇒ 调用环可能含假阳性」"
                         "—— 这是它最容易被误读的地方")
        elif ident in (IDENTITY_DEFSITE_LIT, IDENTITY_LOCAL_LIT):
            if "不猜" not in _ltxt:
                probs.append("F7f %s 口径必须明说「判不出来的部分**不猜**」"
                             "—— 否则读者会以为同名多定义也消歧了" % ident)
            if "漏" not in _ltxt:
                probs.append("F7f %s 口径必须明说它**会漏**（K_AMB 是汇点 ⇒"
                             "经过同名多定义的环不再被报出）—— 只报好处不报代价"
                             % ident)
            if ident == IDENTITY_LOCAL_LIT:
                # R89：新口径多了一条**推导**。它必须自己说清规则与它的作用域，
                # 否则读者分不出它与 definition-site 的差别（而那正是它的全部内容）。
                if "同文件" not in _ltxt:
                    probs.append("F7f 新口径必须明说它的规则（**同文件优先**）"
                                 "—— 不然它与 definition-site 看起来一模一样")
                if "include" not in _ltxt and "翻译单元" not in _ltxt:
                    probs.append("F7f 新口径必须明说第二级（`include` 闭包 / "
                                 "翻译单元可见性）—— 只报一级等于只报一半规则")
    return probs


def _res_sum(res):
    """`resolution` 各档之和（**现算**，不写死档名以外的任何东西）。"""
    if not isinstance(res, dict):
        return None
    out = 0
    for v in res.values():
        if not isinstance(v, int):
            return None
        out += v
    return out


def _cycle_members(cyc):
    """一个环 -> 成员名字表。**两种形状都要收**（这是本轮踩过的坑）：

      产物 `callrel.strongly_connected` 交出来的是 ``[{"size": k,
      "members": [名, ...]}, ...]``，而 `_cycle_members_all()` 与自证夹具
      交出来的**已经是 members 本身**（``[[名, ...], ...]``）。
    只按 dict 解会在自证里崩成 `AttributeError: 'list' object has no
    attribute 'get'` —— 而**门与自证共用这个函数**，所以两向都要能跑。
    """
    if isinstance(cyc, dict):
        return cyc.get("members") or []
    if isinstance(cyc, (list, tuple)):
        return list(cyc)
    return []


def _same_file_cycles(cycles):
    """每个环的成员落点集合：返回 ``[set(rel), ...]``（无落点的成员记 ""）。

    F10b 要问的是「这个环是不是**同一个文件内部**的真递归」，所以必须把
    `名字 @ 落点` 里的落点取出来按环分组 —— 只数环的个数区分不了
    「两个同文件真环」与「一个真环 + 一条跨文件假边」。
    """
    out = []
    for c in cycles or []:
        rels = set()
        for m in _cycle_members(c):
            s = str(m)
            rels.add(s.split(" @ ", 1)[1] if " @ " in s else "")
        out.append(rels)
    return out


def judge_local(obs):
    """F10（R89）的**纯函数**判据：同文件 / 包含闭包**阶梯**。

    与 F9 的分工：F9 管「身份口径换没换、换了会不会吃边」；F10 管**阶梯本身**
    —— 它判得出什么、判不出什么、在哪些语料上根本不该启用。
    五个半边各有自己的坏样本（自证里逐条点名），互不重叠：

      F10a 三口径（default / 纯定义落点 / 名字级）的 `edges_total` 全相等且等于
           `--json` 载荷边数。**加口径不许吃边**（F9c 的两口径版）。
      F10b **活性 + 覆盖**：同名不同文件夹具上，新口径报出的环必须**多于**纯定义落点，
           每个环的成员必须落在**同一个文件**里，环的落点互不相同，
           并且**环成员落点集合的并集必须覆盖夹具里的每一个文件**（覆盖不是形状：
           「盲算给第一份定义」也会留下一个**同文件**的环，形状判据对它无感）；
           同时最大环**不许超过**名字级（每个落点节点映到恰好一个名字 ⇒
           细化只能让环变小或不变）。三个半边缺一不可：只断言「环变多」可以
           由「把调用点全算给第一份定义」刷出来（那会凑出跨文件边）。
      F10c **惰性**：没有同名可消歧的夹具上，新口径与纯定义落点必须**逐位相同**
           （biggest / nodes / edges）—— 没东西可判时阶梯必须是 no-op。
      F10d **只做重分类**：`resolution` 各档之和 == `edges_total`（三口径都要），
           且 `unique` / `external` 在三口径下逐位相同 —— 阶梯动的只能是
           `same_file`/`include` 与 `ambiguous` 的分配。**分母被钉住**，
           「救回了多少」这个数才不是任人打扮的。
      F10e **语言门**：非 C 语料上 `applied=false` / `rungs=[]`，且读数与纯定义
           落点逐位相同。近似冒充结论会造出假环。
      F10f **第二级活性**：定义在**被包含的头文件**里时，默认口径必须把全部边落进
           `include`（对照：纯定义落点全留 `ambiguous`）。判据是**恒等式**
           `include == edges_total`，不是手抄数字 —— 顺手当了「夹具被掏空」的对手方。
      F10g **第二级的作用域边界**：调用点落在**头文件**里时 `include` 必须为 0、
           判不出的全部留在 `ambiguous`，且产物自报 `header_callers > 0`
           （「我没判」不能装成「判不出来」）；同时断言 `applied=true`，
           否则这一条测的是「什么都没发生」而不是边界。
      F10h **三明治**：basename 撞车（`incx`）时**过近似不许冒充真 TU**
           —— `include` 必须为 0、判不出的必须全留在 `ambiguous`，
           **且** `closure_capped` 必须为 0（截断路径与三明治失败路径
           读数**逐位相同** ⇒ 不给这一条配对，一个「闭包永远超限」的
           坏实现会把前两条一起满足），**且**对照半边 `inc` 的
           `include` 必须为正（否则前两条会被「它从来不判」刷绿）。
           五个半边互不重叠，各有自己的坏样本。
      F10i **两级不许互相冒充**（由变异体 M3 逼出来的门洞）：`same_file`
           与 `include` 是对「**为什么**判得出来」的两种不同断言 ——
           把「同一个文件」记成「同一个翻译单元」就是在产物里写下
           **错误的原因**，而本轮全部结论都按这两档分桶。判据是关系式：
           `dup` 上 `include == 0` 且 `same_file == pure.ambiguous`，
           `inc` 上反过来（与 F10f 互为对手方），外加「对照半边不许为 0」。
      F10j：第二级的**代价** —— `closure_computed == 2 × rung2_files`（外加
            「12 个调用者文件都走到了第二级」与「五档之和 == 边数」两条对照）。
            这条判的是**没有读数会变的那种错**：缓存退化（重算）产出的
            集合完全一样，所以任何正确性判据都抓不到它（R89j 实测：
            内核整树 `--callgraph` 61.4 分钟没跑完，而**所有读数一个都没变**）。
      F10k **`under` 的唯一性口径**（R89k）：判据是「**共享头必须判得出来**」
           —— multi 夹具里 12 个 `.c` 共享**一份** `k.h`，48 条歧义边必须
           **全部**落进 `include`，且产物要自报口径（`local_scope.under_basis`）。
           ⚠ 这条不是设计出来的，是**账本的对账装置**在真语料上红出来的：
           独立量具说 `include=2034`、引擎报 **0**。根因是 `include_graphs()`
           按 include **行数**判唯一性 ⇒ 被 ≥2 处包含的头（内核里**最常见**的
           形状，如 `kernel.h` / `list.h`）整条被丢出 `under` ⇒ 三明治在
           主战场上**恒失败**。
           ⚠ F10j 曾**刻意不钉**这个数（当时的理由是「欠近似是保守方向、钉住
           会让下一轮的正确改进变成假红」）。真语料上的对账把那个判断**推翻**：
           欠近似不是「更安全」，而是把这一级的能力砍成 **0**。
           对照半边（basename 撞车 ⇒ **必须**判不出来）由 F10h 持有 ——
           两侧分开住，一条判据只问一件事。
      F10l **`rel` 的基准 = 被分析根**（R90）：`dupx` 夹具让 `d1/x.c` 与
           `d2/x.c` **同 basename**、各定义一份 `dup`。`rel` 若按**调用者的
           cwd** 算，两个文件塌成同一个 `x.c` ⇒ 两份定义挤进同一个 rel ⇒
           同文件优先判不出来（`same_file=0 / ambiguous=4`）；按**被分析根**
           算则两份定义各在调用者自己的文件里 ⇒ 全部 `same_file`。
           三条断言 + 两条完备性：
             ① 同名不同目录**不许被合并**（`same_file` == 边数、`ambiguous` == 0）
             ② **对照半边**：纯定义落点不做作用域推理 ⇒ 同样这些边本应**全部**
                留歧义（证明①不是「0 == 0」刷绿的）
             ③ **直接测形态**：产物自报的 `rel`（`fan_in_top` / `fan_out_top`
                的 `file`）必须等于**夹具自己的**相对路径表 —— 这一条不看任何
                派生读数
             ④ ③ 所依赖的两张表是**有界投影** ⇒ 先断言 `shown == total`，
                否则③可能只看到一部分却「碰巧」相等
             ⑤ **不许静默**：`_rel_of` / `build_c_model` / `_build_ext_model`
                的 `root` 形参**不许有默认值** —— 有默认值就等于留了一条静默的
                cwd 回退（这条是 **AST** 判据：读真实形参默认值，不是文本搜索）
    """
    probs = []
    if not isinstance(obs, dict):
        return ["F10 判据载体不是字典（scan_identity 的返回值坏了）"]

    # ---- F10a 三口径边账 ----
    e = (obs.get("dup_edges_default"), obs.get("dup_edges_pure"),
         obs.get("dup_edges_legacy"), obs.get("dup_n_edges_json"))
    if None in e or len(set(e)) != 1:
        probs.append("F10a 三口径的边账必须全相等且等于载荷里的边数，读到 "
                     "default=%r pure=%r legacy=%r 载荷=%r" % e)

    # ---- F10b 活性 + 不越界 ----
    cd, cp = (obs.get("dup_cycles_default") or []), (obs.get("dup_cycles_pure") or [])
    if len(cd) <= len(cp):
        probs.append("F10b 同名不同文件夹具上新口径报出的环必须**多于**纯定义落点"
                     "（%d vs %d）—— 阶梯没把真环收回来" % (len(cd), len(cp)))
    rl = _same_file_cycles(cd)
    bad = [sorted(r) for r in rl if len(r) != 1]
    if cd and bad:
        probs.append("F10b 新口径报出的环里有**跨文件**的成员集合（%r）—— "
                     "那不是「同文件优先」，是把调用点盲算给了某一份定义" % bad)
    if len(set(frozenset(r) for r in rl)) != len(rl):
        probs.append("F10b 新口径报出的环里有**落点相同**的两个环（%r）—— "
                     "同一个文件里不该被拆成两个同名环" % rl)
    # ---- F10b 的**覆盖**半边（R89 由变异体 M3 逼出来）----
    # 上面三条只问**形状**（环变多 / 不跨文件 / 落点不重复）。形状能骗：
    # 把 rung1 从「同文件里**恰一份**」松成「**盲算给第一份定义**」，
    # 两个环会掉成一个 —— 而那一个仍然在同文件里 ⇒ 三条形状判据全绿。
    # 缺的那条是**覆盖**：每个含同名调用点的文件，都必须由**它自己文件里
    # 的那一份**把环收回来。期望值来自夹具（`CG_DUP_FIXTURES` 的文件名表）。
    exp = obs.get("dup_fixture_rels")
    if not isinstance(exp, list) or not exp:
        probs.append("F10b 拿不到夹具文件表（dup_fixture_rels）—— "
                     "覆盖半边会退化成空断言，读到 %r" % (exp,))
    else:
        covered = set(f for r in rl for f in r)
        miss = sorted(set(exp) - covered)
        if miss:
            probs.append("F10b 有调用者文件没被收回来 %r —— 环只覆盖了 %r，"
                         "而夹具里每个文件各有一份同名定义。缺这几个说明"
                         "调用点被**算给了别处**（盲算给某一份是不猜的反面）"
                         % (miss, sorted(covered)))
    bd, bp, bl = (obs.get("dup_big_default"), obs.get("dup_big_pure"),
                  obs.get("dup_big_legacy"))
    if None in (bd, bp, bl) or bd > bl:
        probs.append("F10b 新口径的最大环 %r **超过**名字级 %r —— 细化只能让环变小"
                     "或不变，出现这个方向说明节点身份漏了「名字」这一层"
                     % (bd, bl))

    # ---- F10c 惰性 ----
    for tag, k in (("最大环", "big"), ("节点数", "nodes"), ("边数", "edges")):
        a, b = obs.get("inert_%s_default" % k), obs.get("inert_%s_pure" % k)
        if a != b:
            probs.append("F10c 没有同名可消歧的夹具上，新口径与纯定义落点的%s"
                         "必须逐位相同，读到 %r / %r（阶梯无中生有）"
                         % (tag, a, b))

    # ---- F10d 只做重分类 ----
    for tag, key in (("default", "dup_res_default"), ("pure", "dup_res_pure"),
                     ("legacy", "dup_res_legacy")):
        res = obs.get(key)
        s = _res_sum(res)
        if s is None:
            probs.append("F10d %s 口径没有 resolution 块（或不是整数计数）—— "
                         "「救回了多少」必须有分母，读到 %r" % (tag, res))
        elif s != obs.get("dup_edges_default"):
            probs.append("F10d %s 口径 resolution 各档之和 %d != edges_total %r"
                         "（逐档计数与总数必须自洽）"
                         % (tag, s, obs.get("dup_edges_default")))
    rd, rp = obs.get("dup_res_default") or {}, obs.get("dup_res_pure") or {}
    for k in ("unique", "external"):
        if rd.get(k) != rp.get(k):
            probs.append("F10d 三口径下 %r 必须逐位相同（阶梯只许在 "
                         "same_file/include 与 ambiguous 之间重新分配），"
                         "读到 %r / %r" % (k, rd.get(k), rp.get(k)))

    # ---- F10e 语言门 ----
    sc = obs.get("py_scope_default")
    if not isinstance(sc, dict):
        probs.append("F10e Python 语料上产物必须自报 local_scope，读到 %r" % (sc,))
    else:
        if sc.get("applied"):
            probs.append("F10e Python 语料上阶梯**不许**启用（applied=%r）—— "
                         "Python 的模块绑定能在运行时被改掉，「同名同文件」是近似"
                         % (sc.get("applied"),))
        if sc.get("rungs"):
            probs.append("F10e Python 语料上 rungs 必须为空，读到 %r"
                         % (sc.get("rungs"),))
    for tag, k in (("最大环", "big"), ("节点数", "nodes"), ("边数", "edges")):
        a, b = obs.get("py_%s_default" % k), obs.get("py_%s_pure" % k)
        if a != b:
            probs.append("F10e Python 语料上新口径与纯定义落点的%s必须逐位相同，"
                         "读到 %r / %r（语言门没生效 ⇒ 近似冒充了结论）"
                         % (tag, a, b))
    # ---- F10f 第二级（翻译单元）**活性** ----
    # 判据写成**恒等式**（include == edges_total）而不是手抄的数字：
    # 数字会在夹具改动时静默变错，恒等式不会；而且它同时是「夹具没被掏空」
    # 的对手方（谁把 m.c 里的 `#include` 删了，include 立刻归零 ⇒ 红）。
    
    ie, ird, irp = (obs.get("inc_edges_default"), obs.get("inc_res_default"),
                    obs.get("inc_res_pure"))
    if not isinstance(ie, int) or not isinstance(ird, dict) \
            or not isinstance(irp, dict):
        probs.append("F10f 拿不到 inc 夹具（翻译单元那一级）的读数 —— "
                     "第二级会整片退化成空断言，读到 %r / %r"
                     % (irp, ird))
    else:
        if ird.get("include") != ie:
            probs.append("F10f 定义在被包含的头文件里时，默认口径必须把"
                         "**全部** %r 条边落进 include，读到 %r"
                         % (ie, ird.get("include")))
        if ird.get("same_file"):
            probs.append("F10f 定义不在调用者文件里 ⇒ same_file 必须为 0，"
                         "读到 %r" % (ird.get("same_file"),))
        if ird.get("ambiguous"):
            probs.append("F10f 同翻译单元里**恰一份**候选可见 ⇒ 不该留"
                         "歧义，读到 ambiguous=%r" % (ird.get("ambiguous"),))
        if irp.get("include"):
            probs.append("F10f 纯定义落点**不做**作用域推理 ⇒ include 必须"
                         "为 0，读到 %r" % (irp.get("include"),))
        if irp.get("ambiguous") != ie:
            probs.append("F10f 纯定义落点下这些边必须全部留在 ambiguous，"
                         "读到 %r（对照失效 ⇒ F10f 的前半是空断言）"
                         % (irp.get("ambiguous"),))
    
    # ---- F10g 第二级的**作用域边界**：调用点落在头文件里 ⇒ rung 2 不适用 ----
    # TU 由「谁包含这个头」决定，头文件自己的 include 闭包只是那个 TU 的
    # **一部分** ⇒ 在头文件里下「唯一可见」的结论是**错报**的方向。
    he, hrd, hsc = (obs.get("hdr_edges_default"), obs.get("hdr_res_default"),
                    obs.get("hdr_scope_default"))
    if not isinstance(he, int) or not isinstance(hrd, dict) \
            or not isinstance(hsc, dict):
        probs.append("F10g 拿不到 hdr 夹具（头文件调用点）的读数 —— "
                     "作用域边界会退化成空断言，读到 %r / %r" % (hsc, hrd))
    else:
        if not hsc.get("applied"):
            probs.append("F10g hdr 夹具上阶梯竟然没启用（applied=%r）—— "
                         "那样这一条测的不是边界，是「什么都没发生」"
                         % (hsc.get("applied"),))
        if hrd.get("include"):
            probs.append("F10g 调用点在**头文件**里 ⇒ rung 2 不适用 ⇒ include"
                         "必须为 0，读到 %r —— 头文件的 TU 由包含者决定，"
                         "在这里下结论是错报的方向"
                         % (hrd.get("include"),))
        if hrd.get("ambiguous") != he:
            probs.append("F10g 判不出的必须**全部**留在 ambiguous %r，读到 %r"
                         % (he, hrd.get("ambiguous")))
        hc = hsc.get("header_callers")
        if not isinstance(hc, int) or hc <= 0:
            probs.append("F10g 产物必须**自报** header_callers > 0（「我没判」"
                         "不能装成「判不出来」），读到 %r" % (hc,))

    # ---- F10h 三明治：**过近似不许冒充真 TU** ----
    # 判据的对手方是**两份夹具的对照**，不是任何手抄数字：
    #   inc  （被包含的头 basename 唯一）⇒ include == edges_total（判得出）
    #   incx （同名 basename 落在别处）  ⇒ include == 0 且 ambiguous == edges
    # 把三明治松成 `if vu or vo:`（只看过近似）会让 incx 误判成
    # include == edges_total ⇒ 这一条当场红。只留 inc 一份夹具的话，
    # 那次注入会让**两道门全绿** —— 这就是它必须存在的原因。
    xe, xrd, xrp = (obs.get("incx_edges_default"),
                    obs.get("incx_res_default"),
                    obs.get("incx_res_pure"))
    ia = obs.get("inc_res_default") or {}
    if not isinstance(xe, int) or not isinstance(xrd, dict) \
            or not isinstance(xrp, dict):
        probs.append("F10h 拿不到 incx 夹具（三明治）的读数 —— "
                     "「假包含不许抬成判得出」这一半会退化成空断言，"
                     "读到 %r / %r" % (xrp, xrd))
    else:
        if xrd.get("include"):
            probs.append("F10h 同名 basename 的**假**包含被判成了可见 ⇒ "
                         "include=%r —— 过近似（over）冒充了真 TU，"
                         "这是**错报**的方向" % (xrd.get("include"),))
        if xrd.get("same_file"):
            probs.append("F10h incx 夹具里定义不在调用者文件中 ⇒ "
                         "same_file 必须为 0，读到 %r"
                         % (xrd.get("same_file"),))
        if xrd.get("ambiguous") != xe:
            probs.append("F10h 三明治判不出时，全部 %r 条边必须留在 "
                         "ambiguous，读到 %r"
                         % (xe, xrd.get("ambiguous")))
        if xrp.get("include") or xrp.get("ambiguous") != xe:
            probs.append("F10h 纯定义落点不做作用域推理 ⇒ incx 上 "
                         "include 必须 0 且 ambiguous 必须 %r，读到 %r"
                         % (xe, xrp))
        if not isinstance(ia.get("include"), int) or ia.get("include") == 0:
            probs.append("F10h **对照半边**失效：inc 夹具上 include=%r"
                         "（本应为正）—— 那样「incx 上 include 为 0」"
                         "就只是「它从来不判」，前两条会被刷绿"
                         % (ia.get("include"),))
        xsc = obs.get("incx_scope_default")
        if not isinstance(xsc, dict):
            probs.append("F10h incx 夹具上产物必须自报 local_scope，"
                         "读到 %r" % (xsc,))
        else:
            if not xsc.get("applied"):
                probs.append("F10h incx 夹具上阶梯没启用（%r）—— "
                             "这一条测的会是「什么都没发生」"
                             % (xsc.get("applied"),))
            capped = xsc.get("closure_capped")
            if not isinstance(capped, int) or capped != 0:
                probs.append("F10h incx 上 closure_capped=%r（必须为 0）"
                             "—— **截断**与**三明治失败**产出的读数是"
                             "同一份，不给这条配对，一个「闭包永远"
                             "超限」的坏实现会把 h1/h2 一起满足"
                             % (capped,))

    # ---- F10j 第二级的**代价**：缓存必须真的缓存（R89j）----
    # 「每个调用者文件只算两次闭包」—— 退化时集合一样、只有次数不一样
    # ⇒ 这条判据是**唯一**能看见它的东西。
    me = obs.get("multi_edges_default")
    mrd = obs.get("multi_res_default")
    msc = obs.get("multi_scope_default")
    if not isinstance(me, int) or not isinstance(mrd, dict) \
            or not isinstance(msc, dict):
        probs.append("F10j 拿不到 multi 夹具（>8 个调用者文件）的读数 —— "
                     "缓存退化会退化成空断言，读到 %r / %r" % (msc, mrd))
    else:
        nf = msc.get("rung2_files")
        nc = msc.get("closure_computed")
        if not isinstance(nf, int) or nf != len(CG_MULTI_ROOTS):
            probs.append("F10j multi 夹具上走进第二级的调用者文件数必须是 %d，"
                         "读到 %r（读不到 ⇒ 代价不变量无从谈起）"
                         % (len(CG_MULTI_ROOTS), nf))
        elif not isinstance(nc, int) or nc != 2 * nf:
            probs.append("F10j **闭包缓存退化成重算**：closure_computed=%r，"
                         "而「每个文件只算两次（under+over）」要求 %d —— "
                         "多出来的部分是同一份闭包被反复重算（R89j 之前内核整树"
                         "这一步 61.4 分钟没跑完，而所有读数一个都没变）"
                         % (nc, 2 * nf))
        # 对照半边：夹具读数自洽（五档之和 == 边数）。**不**断言 include 是多少
        # —— 欠近似把共享头排除在外是**已知且保守**的行为，钉住它等于禁止下一轮
        # 把这个口径改强（R83 ④：陈旧的红与真坏长得一样）。
        tot = sum(v for v in mrd.values() if isinstance(v, int))
        if tot != me:
            probs.append("F10j multi 夹具上五档之和 %r != 边数 %r —— 读到的产物"
                         "本身不自洽，代价不变量也没有意义" % (tot, me))
        if not (msc.get("closure_visits") or 0):
            probs.append("F10j closure_visits 为 0 —— 代价计数器是死的"
                         "（整条 F10j 会变成空断言）")

    # ---- F10k `under` 图的**唯一性口径**（R89k，由账本的对账装置逼出来）----
    # 判据来由见 §judge_local 的 docstring：真语料上「量具 2034 / 引擎 0」。
    # 这条夹具的 `k.h` 被 12 个文件包含却**只有一个解析目标** ⇒ 三明治必须成立。
    # ⚠ 守卫 `isinstance(...)` 是**有意的**：读不到夹具时由 F10j 的
    # 「拿不到 multi 夹具」那条报红 —— 一条判据只负责一件事（否则同一个
    # 坏样本会让两条判据一起红，`red_loc` 判定「红在别处 = 失败」）。
    if isinstance(msc, dict):
        if msc.get("under_basis") != UNDER_BASIS_WANT:
            probs.append(
                "F10k `under` 的唯一性口径没有被登记、或登记成了别的东西："
                "读到 %r（要求 %r）。不登记口径就只能靠读代码猜 —— 而这一轮"
                "的错误恰恰是**口径**错（按 include 行数而不是按解析目标数）"
                % (msc.get("under_basis"), UNDER_BASIS_WANT))
    if isinstance(mrd, dict) and isinstance(me, int):
        if mrd.get("include") != me or mrd.get("ambiguous"):
            probs.append(
                "F10k 共享头在 12 个调用者文件之间的第二级必须**全部**判得出来："
                "include=%r（要求 %r = 边数）、ambiguous=%r（要求 0）。"
                "按 include 行数判唯一性会把 k.h 整条丢出 under 图，读数正是"
                " include=0 / ambiguous=48"
                % (mrd.get("include"), me, mrd.get("ambiguous")))

    # ---- F10i **两级不许互相冒充**：救回来的是**哪一级** ----
    # 这一条不是设计出来的，是变异体 M3（把 rung1 关成 `if False:`）
    # 逼出来的**门洞**：dup 夹具里没有 include（`under = {}`、不是 None）
    # ⇒ 关掉 rung1 之后流程落到 rung2，闭包 `{调用者自己}` 里恰好一份候选
    # ⇒ 判成 `include`。节点键仍是 `K_DEF + rel + name` ⇒ **图逐位没变**
    # （edges / cycles / biggest / 覆盖全不动），只有**标签**从 `same_file`
    # 变成 `include` —— 而当时没有任何判据看标签，门 rc=0 全绿。
    # 标签是**原因**：「同一个文件」与「同一个翻译单元（包含进来的头）」
    # 是两种不同的断言，把前者记成后者就是在产物里写下一个错误的原因，
    # 而本轮所有下游结论（残余分类、下一轮的同 TU 消歧）都按这两档分桶。
    dd, pp = obs.get("dup_res_default"), obs.get("dup_res_pure")
    ix = obs.get("inc_res_default") or {}
    if not isinstance(dd, dict) or not isinstance(pp, dict):
        probs.append("F10i 拿不到 dup 夹具的两口径 resolution —— "
                     "「哪一级救回的」会退化成空断言，读到 %r / %r"
                     % (dd, pp))
    else:
        if dd.get("include"):
            probs.append("F10i dup 语料里**没有 include**（`under` 是空字典、"
                         "不是 None），却被判成 include=%r —— 两级在互相"
                         "冒充：rung2 把「同一个文件」记成了「同一个"
                         "翻译单元」" % (dd.get("include"),))
        if dd.get("same_file") != pp.get("ambiguous"):
            probs.append("F10i dup 上救回的全部必须来自 rung1：same_file=%r"
                         "应等于纯定义落点的 ambiguous=%r（差额说明有边被"
                         "记到了另一级）"
                         % (dd.get("same_file"), pp.get("ambiguous")))
        if not pp.get("ambiguous"):
            probs.append("F10i **对照半边**失效：纯定义落点上没有歧义可救"
                         "（%r）⇒ 上面两条会被 0 == 0 刷绿"
                         % (pp.get("ambiguous"),))
        if not ix.get("include"):
            probs.append("F10i **对照半边**失效：inc 夹具上 include=%r"
                         "（本应为正）⇒ 「dup 上 include 为 0」就只是"
                         "「它从来不判这一级」" % (ix.get("include"),))
        if ix.get("same_file"):
            probs.append("F10i inc 夹具上定义不在调用者文件里 ⇒ same_file"
                         "必须为 0（rung1 不许冒充 rung2），读到 %r"
                         % (ix.get("same_file"),))

    # ---- F10l `rel` 的**基准** = 被分析根（R90，由「同一份语料两种调用形态」
    #      的装置逼出来）----
    # 判据来由见 §judge_local 的 docstring。⚠ 守卫 `isinstance` 是**有意的**：
    # 读不到夹具时由这一条自己的第一支报红，不让别的 F10x 一起红
    # （`red_loc` 判定「红在别处 = 失败」）。
    dxe = obs.get("dupx_edges_default")
    dxr = obs.get("dupx_res_default")
    dxp = obs.get("dupx_res_pure")
    if not isinstance(dxe, int) or not isinstance(dxr, dict) \
            or not isinstance(dxp, dict):
        probs.append("F10l 拿不到 dupx 夹具（同名不同目录）的读数 —— "
                     "`rel` 的基准会退化成空断言，读到 %r / %r" % (dxp, dxr))
    else:
        if dxr.get("same_file") != dxe:
            probs.append("F10l 同名不同目录的两份定义被**合并**了：`rel` 应相对"
                         "**被分析根**，退回「相对 cwd」就只剩 basename ⇒ "
                         "同文件优先判不出来 ⇒ same_file 应为 %r（= 边数），"
                         "读到 %r" % (dxe, dxr.get("same_file")))
        if dxr.get("ambiguous"):
            probs.append("F10l dupx 夹具上留下了 %r 条歧义边 —— 两份定义各在"
                         "调用者自己的文件里，本该一条都不留"
                         % (dxr.get("ambiguous"),))
        if dxp.get("ambiguous") != dxe:
            probs.append("F10l **对照半边**失效：纯定义落点不做作用域推理 ⇒ "
                         "同样这些边本应**全部**留歧义（%r 条），读到 %r —— "
                         "夹具丧失了可歧义性，上一条会被 0 == 0 刷绿"
                         % (dxe, dxp.get("ambiguous")))
        want_files = sorted(set(p for p, _t in CG_DUPX_FIXTURES))
        seen_files = obs.get("dupx_files_seen")
        if not isinstance(seen_files, list) or seen_files != want_files:
            probs.append("F10l 产物自报的文件不是**根相对**形态：期望 %r，"
                         "读到 %r —— 退回 cwd 相对时两个文件会塌成同名 basename"
                         % (want_files, seen_files))
    if obs.get("dupx_proj_whole") is not True:
        probs.append("F10l dupx 夹具的 fan_in/fan_out 有界投影被截断（%r）⇒ "
                     "上面那条形态判据看到的文件集可能不完整"
                     % (obs.get("dupx_proj_whole"),))
    rd = obs.get("rel_root_param_defaults")
    _nd_want = ("_rel_of", "build_c_model", "_build_ext_model")
    if not isinstance(rd, dict):
        probs.append("F10l 拿不到 `root` 形参默认值的 AST 读数（%r）—— "
                     "「不许静默」这半边会退化成空断言" % (rd,))
    else:
        bad_nd = [k for k in _nd_want if rd.get(k) != "NODEFAULT"]
        if bad_nd:
            probs.append("F10l %s 的 `root` **带了默认值**（读到 %r）—— "
                         "有默认值就等于留了一条**静默**的 cwd 回退：漏传根时"
                         "产物会悄悄变回 cwd 相对"
                         % (", ".join(bad_nd),
                            dict((k, rd.get(k)) for k in _nd_want)))
    return probs


def judge_identity(obs):
    """F9（R88）的**纯函数**判据：节点身份口径（definition-site ⇄ callee-name）。

    与 F7f 的分工：F7f 管「口径与它的局限**都写下来了**」，这一族管口径**行为本身**。
    五个半边各有自己的坏样本（自证里逐条点名），互不重叠：

      F9a **默认口径必须是 `definition-site` 这个字面量** —— 口径被静默换掉是
          R83 说的那类「所有读数一起错且都自洽」的缺陷，必须有一个对手方。
      F9b 老口径**仍可显式选中**并如实回显（不许删），**未知值必须非零退出且
          不产出文件**（静默退回默认就是「没听懂却假装听懂」）；形状版本号必须
          跟着口径一起涨（键集合变了 ⇒ 下游按它判兼容）；焦点子图的
          `focus_candidates` 在两口径下都必须存在（定义落点下一个名字可以映到
          多个节点 ⇒ 这个键是**必须**的）。
      F9c **反向**：两条口径的 `edges_total` 必须相等，且都等于 `--json` 载荷里
          `edges` 的长度 —— 拆节点**不许吃掉任何一条边**。这一条是 F9d 的对手方：
          只断言「环塌了」可以由「整类不报」刷出来。
      F9d **活性**：同名不同文件的夹具上，定义落点的最大环必须**小于**名字级，
          且节点数**更多**（真把同名拆开了）。
      F9e **惰性**：没有同名不同文件的夹具上，两条口径的最大环与节点数必须
          **逐位相同**，且定义落点报出的环成员必须**带落点**（可区分）——
          没有东西可拆时口径不许无中生有，拆开时又必须让人分得清。
    """
    probs = []
    if not isinstance(obs, dict):
        return ["F9 判据载体不是字典（scan_identity 的返回值坏了）"]

    if obs.get("id_default") != IDENTITY_LOCAL_LIT:
        probs.append("F9a 默认节点身份必须是字面量 %r（R89 起 —— 口径被静默换掉"
                     "是这类缺陷里最难发现的一种），读到 %r"
                     % (IDENTITY_LOCAL_LIT, obs.get("id_default")))
    if obs.get("id_legacy") != "callee-name":
        probs.append("F9b `--callgraph-identity callee-name` 必须仍被支持并如实"
                     "回显，读到 %r" % (obs.get("id_legacy"),))
    if obs.get("bad_id_rc") in (0, None):
        probs.append("F9b 未知口径值竟然退出了 %r —— 静默退回默认口径"
                     % (obs.get("bad_id_rc"),))
    if obs.get("bad_id_exists"):
        probs.append("F9b 未知口径值还是写出了文件")
    ver = obs.get("cg_version")
    if not isinstance(ver, int) or ver < 2:
        probs.append("F9b 形状版本必须是 >= 2 的整数（键集合变了 ⇒ 版本要涨），"
                     "读到 %r" % (ver,))
    for _k in ("default_focus_candidates", "legacy_focus_candidates"):
        if not isinstance(obs.get(_k), int):
            probs.append("F9b 焦点子图的候选数键 %s 必须在（定义落点下一个名字可以"
                         "映到多个节点），读到 %r" % (_k, obs.get(_k)))
    ed, el, ej = (obs.get("dup_edges_default"), obs.get("dup_edges_legacy"),
                  obs.get("dup_n_edges_json"))
    if None in (ed, el, ej) or not (ed == el == ej):
        probs.append("F9c 两条口径的边账必须相等且都等于载荷里的边数，读到 "
                     "默认=%r 老口径=%r 载荷=%r" % (ed, el, ej))
    bd, bl = obs.get("dup_big_default"), obs.get("dup_big_legacy")
    nd, nl = obs.get("dup_nodes_default"), obs.get("dup_nodes_legacy")
    if bd is None or bl is None or not bd < bl:
        probs.append("F9d 同名不同文件的夹具上，定义落点的最大环必须**小于**"
                     "名字级，读到 %r / %r（环塌不下来 ⇒ 这条口径没起作用）"
                     % (bd, bl))
    if nd is None or nl is None or not nd > nl:
        probs.append("F9d 同名不同文件的夹具上，定义落点的节点数必须**更多**"
                     "（拆开了），读到 %r / %r" % (nd, nl))
    if (obs.get("inert_big_default") != obs.get("inert_big_legacy")
            or obs.get("inert_nodes_default") != obs.get("inert_nodes_legacy")):
        probs.append("F9e 没有同名不同文件的夹具上，两条口径必须**逐位相同**，"
                     "读到 最大环 %r/%r、节点 %r/%r"
                     % (obs.get("inert_big_default"), obs.get("inert_big_legacy"),
                        obs.get("inert_nodes_default"),
                        obs.get("inert_nodes_legacy")))
    imem = obs.get("inert_cycle_members")
    if not isinstance(imem, list) or not imem:
        probs.append("F9e 拿不到定义落点报出的环成员，读到 %r" % (imem,))
    elif not all(" @ " in str(m) for m in imem):
        probs.append("F9e 定义落点报出的环成员必须**带落点**（否则同名不同文件的"
                     "两个成员分不开），读到 %r" % (imem,))
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


def _files_seen(pay):
    """产物自报的**文件**集合（`fan_in_top` / `fan_out_top` 两项的 `file`）。

    这两张表是**有界投影** ⇒ 完整性由 `_proj_whole` 另行断言，不能默认
    「看到的就是全部」（R86-3 的口径：截断必须显式）。
    空/缺的 `file`（`K_AMB` 汇点不指落点）**不并入** —— 它是「没落点」，
    不是「落点是空字符串」。
    """
    cr = (pay or {}).get("call_relations") or {}
    out = set()
    for key in ("fan_in_top", "fan_out_top"):
        for it in (cr.get(key) or []):
            f = it.get("file")
            if f:
                out.add(f)
    return sorted(out)


def _proj_whole(pay):
    """`fan_in` / `fan_out` 两张表是否**未被截断**（`shown == total`，现算）。"""
    cr = (pay or {}).get("call_relations") or {}
    t = cr.get("truncated") or {}
    try:
        return (int(t.get("fan_in_shown")) == int(t.get("fan_in_total"))
                and int(t.get("fan_out_shown")) == int(t.get("fan_out_total")))
    except (TypeError, ValueError):
        return False


def _root_param_defaults(path):
    """`matlabc.py` 里三个组装函数的 `root` 形参**有没有默认值**（AST 现读）。

    R90 的设计决定是「`root` **没有默认值**」—— 有默认值就等于留了一条
    **静默**的 cwd 回退（漏传根时产物悄悄变成 cwd 相对）。这是**结构化**判据：
    读的是 AST 里真实的形参默认值，不是源码文本里有没有某个字符串。

    返回 `{函数名: "NODEFAULT" | "DEFAULT" | "MISSING"}`。
    """
    want = ("_rel_of", "build_c_model", "_build_ext_model")
    out = dict((w, "MISSING") for w in want)
    try:
        with io.open(path, "rb") as fh:
            tree = ast.parse(fh.read().decode("utf-8", "replace"))
    except (IOError, OSError, SyntaxError, ValueError):
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in want:
            continue
        args = list(node.args.args)
        if not any(a.arg == "root" for a in args):
            out[node.name] = "MISSING"
            continue
        ndef = len(node.args.defaults)
        tail = args[len(args) - ndef:] if ndef else []
        out[node.name] = ("DEFAULT" if any(a.arg == "root" for a in tail)
                          else "NODEFAULT")
    return out


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


def _cycle_members_all(pay):
    """产物 → 每个环的成员表（F10b 要比「环多不多、成员同不同文件」）。"""
    cs = ((pay or {}).get("call_relations") or {}).get("cycles") or []
    return [list(c.get("members") or []) for c in cs]


def scan_identity(root, python_exe):
    """F9 的**载体**：跑公开 CLI，把「节点身份口径」这一族量出来。

    七个夹具目录、十六趟 CLI（各有理由，缺一趟就有半边没被量到）：
      dup  × 默认           ⇒ 默认口径是什么（F9a）+ 阶梯活性（F10b/F10d）
      dup  × definition-site ⇒ **纯**定义落点基线（F10a/F10b/F10d 的对照）
      dup  × callee-name    ⇒ 老口径还在不在（F9b）
      dup  × 未知值          ⇒ 会不会静默降级（F9b）
      cyc  × 默认 / 纯 / 老  ⇒ 惰性对照（F9e/F10c）：没有同名可拆时不许动
      py   × 默认 / 纯       ⇒ 语言门（F10e）：非 C 语料上阶梯必须整体失效
      inc  × 默认 / 纯       ⇒ 第二级活性（F10f）：基名唯一 ⇒ 判得出
      hdr  × 默认 / 纯       ⇒ TU 边界（F10g）：调用点在头文件里 ⇒ 不判
      incx × 默认 / 纯       ⇒ 三明治（F10h）：基名撞车 ⇒ 也不许判
      multi× 默认            ⇒ **代价不变量**（F10j）：>8 个调用者文件才测得出
                                缓存退化（每个文件只该算两次闭包）；
                                同一趟也是 `under` **唯一性口径**（F10k）的载体：
                                12 个文件共享**一个** `k.h` ⇒ 必须全判得出来
      dupx × 默认 / 纯       ⇒ `rel` 的**基准**（F10l）：同 basename 落在两个
                                目录里 —— 退回 cwd 相对就塌成一个文件

    返回 ``(probs, n_runs)``；``probs is None`` = **缺输入**
    （不许把「跑不起来」当成「没问题」）。
    """
    base = tempfile.mkdtemp(prefix="r88id_")
    try:
        dup = os.path.join(base, "dup")
        cyc = os.path.join(base, "cyc")
        pyd = os.path.join(base, "py")
        incd = os.path.join(base, "inc")
        hdrd = os.path.join(base, "hdr")
        incxd = os.path.join(base, "incx")
        multid = os.path.join(base, "multi")
        dupxd = os.path.join(base, "dupx")
        os.makedirs(dup)
        os.makedirs(cyc)
        os.makedirs(pyd)

        def put(base_dir, fixtures):
            """按 rel 路径落盘（rel 里可以带子目录 —— inc/hdr 夹具需要）。"""
            for rel, text in fixtures:
                p = os.path.join(base_dir, rel.replace("/", os.sep))
                d = os.path.dirname(p)
                if d and not os.path.isdir(d):
                    os.makedirs(d)
                with io.open(p, "w", encoding="utf-8", newline="") as fh:
                    fh.write(text)

        put(incd, CG_INC_FIXTURES)
        put(hdrd, CG_HDR_FIXTURES)
        put(incxd, CG_INCX_FIXTURES)
        put(multid, CG_MULTI_FIXTURES)
        put(dupxd, CG_DUPX_FIXTURES)
        for rel, text in CG_DUP_FIXTURES:
            with io.open(os.path.join(dup, rel), "w", encoding="utf-8",
                         newline="") as fh:
                fh.write(text)
        rel0, txt0 = CG_FIXTURES[0]
        with io.open(os.path.join(cyc, rel0), "w", encoding="utf-8",
                     newline="") as fh:
            fh.write(txt0)
        for rel, text in CG_PY_FIXTURES:
            with io.open(os.path.join(pyd, rel), "w", encoding="utf-8",
                         newline="") as fh:
                fh.write(text)

        def run(work, extra, lang="c"):
            argv = [python_exe, "matlabc.py", work, "--lang", lang,
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

        def one(work, tag, extra, lang="c"):
            j = os.path.join(base, "%s.j.json" % tag)
            c = os.path.join(base, "%s.c.json" % tag)
            if run(work, ["--json", j, "--callgraph", c] + list(extra),
                   lang=lang) != 0:
                return None, None
            return load(j), load(c)

        _jd, c_def = one(dup, "dup_def", [])
        _jp, c_pure = one(dup, "dup_pure",
                          ["--callgraph-identity", "definition-site"])
        _jl, c_leg = one(dup, "dup_leg", ["--callgraph-identity", "callee-name"])
        _ji, c_inert_def = one(cyc, "inert_def", [])
        _jn, c_inert_pure = one(cyc, "inert_pure",
                                ["--callgraph-identity", "definition-site"])
        _jn2, c_inert_leg = one(cyc, "inert_leg",
                                ["--callgraph-identity", "callee-name"])
        _jy, c_py_def = one(pyd, "py_def", [], lang="py")
        _jy2, c_py_pure = one(pyd, "py_pure",
                              ["--callgraph-identity", "definition-site"],
                              lang="py")
        _jinc, c_inc_def = one(incd, "inc_def", [])
        _jinc2, c_inc_pure = one(
            incd, "inc_pure", ["--callgraph-identity", "definition-site"])
        _jhdr, c_hdr_def = one(hdrd, "hdr_def", [])
        _jhdr2, c_hdr_pure = one(
            hdrd, "hdr_pure", ["--callgraph-identity", "definition-site"])
        _jincx, c_incx_def = one(incxd, "incx_def", [])
        _jincx2, c_incx_pure = one(
            incxd, "incx_pure",
            ["--callgraph-identity", "definition-site"])
        _jmul, c_multi_def = one(multid, "multi_def", [])
        _jdx, c_dupx_def = one(dupxd, "dupx_def", [])
        _jdx2, c_dupx_pure = one(
            dupxd, "dupx_pure",
            ["--callgraph-identity", "definition-site"])
        if not all(isinstance(x, dict) for x in
                   (c_def, c_pure, c_leg, c_inert_def, c_inert_pure,
                    c_inert_leg, c_py_def, c_py_pure, c_inc_def, c_inc_pure,
                    c_hdr_def, c_hdr_pure, c_incx_def, c_incx_pure,
                    c_multi_def, c_dupx_def, c_dupx_pure)):
            return None, 0
        bad = os.path.join(base, "bad_id.json")
        bad_rc = run(dup, ["--callgraph", bad, "--callgraph-identity", "nope"])

        def rel_of(pay):
            return (pay or {}).get("call_relations") or {}

        def big(pay):
            return (rel_of(pay).get("cycle_stats") or {}).get("biggest")

        def cyc_members(pay):
            cs = rel_of(pay).get("cycles") or []
            return list(cs[0].get("members") or []) if cs else []

        def focus_cands(pay):
            return ((pay or {}).get("focus_subgraph") or {}).get(
                "focus_candidates")

        obs = {
            "id_default": rel_of(c_def).get("identity"),
            "id_legacy": rel_of(c_leg).get("identity"),
            "cg_version": rel_of(c_def).get("version"),
            # ---- F10（R89）----
            "dup_edges_pure": rel_of(c_pure).get("edges_total"),
            "dup_res_default": rel_of(c_def).get("resolution"),
            "dup_res_pure": rel_of(c_pure).get("resolution"),
            "dup_res_legacy": rel_of(c_leg).get("resolution"),
            "dup_cycles_default": _cycle_members_all(c_def),
            # F10b 的**覆盖**半边：期望值来自**夹具自己**（文件名表），
            # 不是手抄的数字 —— 「每个含同名调用点的文件都要被收回来」。
            "dup_fixture_rels": [p for p, _t in CG_DUP_FIXTURES],
            "dup_cycles_pure": _cycle_members_all(c_pure),
            "inert_big_pure": big(c_inert_pure),
            "inert_nodes_pure": rel_of(c_inert_pure).get("nodes_total"),
            "inert_edges_pure": rel_of(c_inert_pure).get("edges_total"),
            "inert_edges_default": rel_of(c_inert_def).get("edges_total"),
            "py_scope_default": ((c_py_def or {}).get("call_relations") or {}
                                 ).get("local_scope"),
            "py_scope_pure": ((c_py_pure or {}).get("call_relations") or {}
                              ).get("local_scope"),
            "py_big_default": big(c_py_def),
            "py_big_pure": big(c_py_pure),
            "py_nodes_default": rel_of(c_py_def).get("nodes_total"),
            "py_nodes_pure": rel_of(c_py_pure).get("nodes_total"),
            "py_edges_default": rel_of(c_py_def).get("edges_total"),
            "py_edges_pure": rel_of(c_py_pure).get("edges_total"),
            # ---- F10f/F10g（R89）：两级阶梯的**第二级** ----
            "inc_edges_default": rel_of(c_inc_def).get("edges_total"),
            "inc_res_default": rel_of(c_inc_def).get("resolution"),
            "inc_res_pure": rel_of(c_inc_pure).get("resolution"),
            "inc_scope_default": (rel_of(c_inc_def)).get("local_scope"),
            "hdr_edges_default": rel_of(c_hdr_def).get("edges_total"),
            "hdr_res_default": rel_of(c_hdr_def).get("resolution"),
            "hdr_res_pure": rel_of(c_hdr_pure).get("resolution"),
            "hdr_scope_default": (rel_of(c_hdr_def)).get("local_scope"),
            # ---- F10h（R89）：三明治 —— basename 撞车的假包含 ----
            "incx_edges_default": rel_of(c_incx_def).get("edges_total"),
            "incx_res_default": rel_of(c_incx_def).get("resolution"),
            "incx_res_pure": rel_of(c_incx_pure).get("resolution"),
            "incx_scope_default": (rel_of(c_incx_def)).get("local_scope"),
            # ---- F10j（R89j）：第二级的代价（缓存不许退化成重算）----
            "multi_edges_default": rel_of(c_multi_def).get("edges_total"),
            "multi_res_default": rel_of(c_multi_def).get("resolution"),
            "multi_scope_default": (rel_of(c_multi_def)).get("local_scope"),
            # ---- F10l（R90）：`rel` 的基准 = 被分析根 ----
            "dupx_edges_default": rel_of(c_dupx_def).get("edges_total"),
            "dupx_res_default": rel_of(c_dupx_def).get("resolution"),
            "dupx_res_pure": rel_of(c_dupx_pure).get("resolution"),
            "dupx_files_seen": _files_seen(c_dupx_def),
            "dupx_proj_whole": _proj_whole(c_dupx_def),
            "rel_root_param_defaults": _root_param_defaults(
                os.path.join(root, "matlabc.py")),
            "dup_big_pure": big(c_pure),
            "dup_nodes_pure": rel_of(c_pure).get("nodes_total"),
            "dup_n_edges_json_pure": len((_jp or {}).get("edges") or []),
            "bad_id_rc": bad_rc,
            "bad_id_exists": os.path.exists(bad),
            "dup_edges_default": rel_of(c_def).get("edges_total"),
            "dup_edges_legacy": rel_of(c_leg).get("edges_total"),
            "dup_n_edges_json": len((_jd or {}).get("edges") or []),
            "dup_big_default": big(c_def),
            "dup_big_legacy": big(c_leg),
            "dup_nodes_default": rel_of(c_def).get("nodes_total"),
            "dup_nodes_legacy": rel_of(c_leg).get("nodes_total"),
            "inert_big_default": big(c_inert_def),
            "inert_big_legacy": big(c_inert_leg),
            "inert_nodes_default": rel_of(c_inert_def).get("nodes_total"),
            "inert_nodes_legacy": rel_of(c_inert_leg).get("nodes_total"),
            "inert_cycle_members": cyc_members(c_inert_def),
            "default_focus_candidates": focus_cands(c_def),
            "legacy_focus_candidates": focus_cands(c_leg),
        }
        return judge_identity(obs) + judge_local(obs), 15
    finally:
        shutil.rmtree(base, ignore_errors=True)


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

    try:
        id_probs, _n_id = scan_identity(root, sys.executable)
    except (OSError, subprocess.SubprocessError) as e:
        print("check_c_frontend_shapes: 身份口径夹具的公开 CLI 跑不起来：%s"
              "（缺输入 → 红）" % e)
        return 2
    if id_probs is None:
        print("check_c_frontend_shapes: 身份口径没有产出可解析的 JSON"
              "（--callgraph 是 F9 的载体 → 缺输入）")
        return 2

    probs = (list(probs) + judge_fixtures() + judge_ratchet(n_funcs)
             + cg_probs + at_probs + id_probs)
    if probs:
        for p in probs:
            print("check_c_frontend_shapes: " + p)
        print("check_c_frontend_shapes: %d 项违规" % len(probs))
        return 1
    print("check_c_frontend_shapes: OK（%d 个形态夹具 + %d 个调用关系夹具 + "
          "%d 个重复定义夹具 + %d 个 Python 夹具 + %d 个阶梯夹具 + "
          "%d 个属性夹具 / 公开 CLI 认出 %d 个函数 / %s 全绿 + "
          "夹具完备性 + 棘轮）"
          % (len(FIXTURES), len(CG_FIXTURES), len(CG_DUP_FIXTURES),
             len(CG_PY_FIXTURES),
             (len(CG_INC_FIXTURES) + len(CG_HDR_FIXTURES)
              + len(CG_INCX_FIXTURES) + len(CG_MULTI_FIXTURES)
              + len(CG_DUPX_FIXTURES)),
             len(ATTR_FIXTURES), n_funcs, ROW_SIGNATURE))
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
            "identity": "definition-site",
            "limitations": ["甲：被调侧歧义判不出来 ⇒ 不猜（K_AMB 是汇点）",
                            "乙：真环也可能**漏**，上界 = 指向 K_AMB 的边数",
                            "丙：unresolved 不在图里；截断是显式的"],
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
            ("F7f 冒出未声明的口径字面量", {"identity": "name"}),
            ("F7f 口径与它的局限分家（老口径配着新口径的局限）",
             {"identity": "callee-name"}),
            ("F7f limitations 缩水到 2 条", {"limitations": ["甲", "乙"]}),
            ("F7f 没明说本口径的局限",
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

    # ---- F9：节点身份口径（R88；同样吃纯 dict） ----
    def _obs_id():
        """好观测：F9 五条子判据必须**全部**在这份观测上绿。

        数字取的是**真实夹具的手推值**（见 `CG_DUP_FIXTURES` 的注释）：
        名级 4 边 ⇒ SCC 3；落点 5 节点 ⇒ 0 环；惰性对照 cyc 两口径都是 2 环 / 3 节点。
        """
        return {"id_default": "definition-site-local",
                "id_legacy": "callee-name",
                "cg_version": 3, "bad_id_rc": 1, "bad_id_exists": False,
                # R89：数字换成**真实夹具的实测值**（旧版写 4 条边，而夹具实际
                # 是 6 —— 被调侧两份定义 ⇒ 每个调用点扇出 2 条；`_obs_id` 只被
                # F9c 用来比三个数彼此相等，所以 4 一直「绿」，但它是错的读数。
                # 自证夹具同样不许撒谎。）
                "dup_edges_default": 6, "dup_edges_legacy": 6,
                "dup_n_edges_json": 6,
                "dup_big_default": 2, "dup_big_legacy": 3,
                "dup_nodes_default": 4, "dup_nodes_legacy": 3,
                "inert_big_default": 2, "inert_big_legacy": 2,
                "inert_nodes_default": 3, "inert_nodes_legacy": 3,
                "inert_cycle_members": ["hub @ cg_cyc.c", "leaf @ cg_cyc.c"],
                "default_focus_candidates": 1, "legacy_focus_candidates": 1}

    def red_id(tag, obs, want):
        probs = judge_identity(obs)
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

    green("好样本：F9 观测五条子判据全绿", judge_identity(_obs_id()))
    for tag, patch in (
            ("F9a 默认口径被悄悄换成老口径", {"id_default": "callee-name"}),
            ("F9b 老口径被删（不再可选）", {"id_legacy": "definition-site"}),
            ("F9b 未知口径值静默退回默认（rc=0）", {"bad_id_rc": 0}),
            ("F9b 未知口径值还是写出了文件", {"bad_id_exists": True}),
            ("F9b 形状版本没跟着口径一起涨", {"cg_version": 1}),
            ("F9b 候选数这个键在老口径下没了",
             {"legacy_focus_candidates": None}),
            ("F9c 拆节点吃掉了边", {"dup_edges_default": 3}),
            ("F9c 载荷那边少一条（两本账对不上）", {"dup_n_edges_json": 5}),
            ("F9c 三口径里有一支吃了边（R89 扩到三口径）",
             {"dup_edges_legacy": 5}),
            ("F9d 同名不同文件处环没塌", {"dup_big_default": 3}),
            ("F9d 同名不同文件没被拆开（节点数没涨）",
             {"dup_nodes_default": 3}),
            ("F9e 没有同名可拆时口径无中生有", {"inert_big_default": 9}),
            ("F9e 没有同名可拆时节点数变了", {"inert_nodes_default": 4}),
            ("F9e 环成员没带落点（同名分不开）",
             {"inert_cycle_members": ["hub", "leaf"]}),
    ):
        d = _obs_id()
        d.update(patch)
        red_id("坏样本 %s" % tag, d, "F9")
    for letter in ("F9a", "F9b", "F9c", "F9d", "F9e"):
        if letter not in witnessed_sub:
            bad[0] += 1
            print("  [selftest] F9 的子判据 %s 没有自己的坏样本（子覆盖静默缩水）"
                  % letter)

    # ---- F10：同文件 / 包含闭包阶梯（R89；同样吃纯 dict）----
    def _obs_loc():
        """好观测：F10 五条子判据必须**全部**在这份观测上绿。

        数字取**真实夹具的手推值**（`CG_DUP_FIXTURES`：6 条边 / 新口径 2 个
        同文件 2 环 / 纯定义落点 0 环 5 节点 / 名字级 1 个 3 环；
        `CG_PY_FIXTURES`：4 条边、0 环、3 节点）。
        """
        return {
            "dup_edges_default": 6, "dup_edges_pure": 6,
            "dup_edges_legacy": 6, "dup_n_edges_json": 6,
            "dup_cycles_default": [["a @ cg_dup_a.c", "h @ cg_dup_a.c"],
                                   ["b @ cg_dup_b.c", "h @ cg_dup_b.c"]],
            "dup_cycles_pure": [],
            "dup_fixture_rels": ["cg_dup_a.c", "cg_dup_b.c"],
            "dup_big_default": 2, "dup_big_pure": 0, "dup_big_legacy": 3,
            "dup_nodes_default": 4, "dup_nodes_pure": 5,
            "dup_res_default": {"unique": 2, "same_file": 4, "include": 0,
                                "ambiguous": 0, "external": 0},
            "dup_res_pure": {"unique": 2, "same_file": 0, "include": 0,
                             "ambiguous": 4, "external": 0},
            "dup_res_legacy": {"unique": 2, "same_file": 0, "include": 0,
                               "ambiguous": 4, "external": 0},
            "inert_big_default": 2, "inert_big_pure": 2,
            "inert_nodes_default": 3, "inert_nodes_pure": 3,
            "inert_edges_default": 6, "inert_edges_pure": 6,
            "py_scope_default": {"applied": False, "lang": "py", "rungs": []},
            "inc_edges_default": 2,
            "inc_res_default": {"unique": 0, "same_file": 0, "include": 2,
                                "ambiguous": 0, "external": 0},
            "inc_res_pure": {"unique": 0, "same_file": 0, "include": 0,
                             "ambiguous": 2, "external": 0},
            "inc_scope_default": {"applied": True, "lang": "c",
                                  "rungs": ["same-file", "include-closure"]},
            "hdr_edges_default": 2,
            "hdr_res_default": {"unique": 0, "same_file": 0, "include": 0,
                                "ambiguous": 2, "external": 0},
            "hdr_res_pure": {"unique": 0, "same_file": 0, "include": 0,
                             "ambiguous": 2, "external": 0},
            "hdr_scope_default": {"applied": True, "lang": "c",
                                  "rungs": ["same-file", "include-closure"],
                                  "header_callers": 2},
            "incx_edges_default": 2,
            "incx_res_default": {"unique": 0, "same_file": 0,
                                 "include": 0, "ambiguous": 2,
                                 "external": 0},
            "incx_res_pure": {"unique": 0, "same_file": 0,
                              "include": 0, "ambiguous": 2,
                              "external": 0},
            "incx_scope_default": {"applied": True, "lang": "c",
                                   "rungs": ["same-file",
                                             "include-closure"],
                                   "closure_capped": 0,
                                   "header_callers": 0},
            # ---- F10j/F10k：代价不变量 + `under` 唯一性口径（好样本 = **实测**
            #      读数：12 个调用者文件各算 2 次闭包；共享头 k.h 只有**一个**
            #      解析目标 ⇒ 三明治成立 ⇒ 48 条歧义边全部落进 include）----
            "multi_edges_default": 48,
            "multi_res_default": {"unique": 0, "same_file": 0, "include": 48,
                                  "ambiguous": 0, "external": 0},
            "multi_scope_default": {"applied": True, "lang": "c",
                                    "rungs": ["same-file", "include-closure"],
                                    "under_basis": "unique-basename-target",
                                    "rung2_files": 12, "closure_computed": 24,
                                    "closure_visits": 72,
                                    "closure_capped": 0, "header_callers": 0},
            "py_big_default": 0, "py_big_pure": 0,
            "py_nodes_default": 3, "py_nodes_pure": 3,
            "py_edges_default": 4, "py_edges_pure": 4,
            # ---- F10l（R90）：dupx 夹具的**手推**值 ——
            #      4 条边（2 个调用点各命中 2 份定义 ⇒ 扇出）、两份定义各在
            #      调用者自己的文件里 ⇒ 全部 same_file；纯定义落点下全部歧义。
            "dupx_edges_default": 4,
            "dupx_res_default": {"unique": 0, "same_file": 4, "include": 0,
                                 "ambiguous": 0, "external": 0},
            "dupx_res_pure": {"unique": 0, "same_file": 0, "include": 0,
                              "ambiguous": 4, "external": 0},
            "dupx_files_seen": ["d1/x.c", "d2/x.c"],
            "dupx_proj_whole": True,
            "rel_root_param_defaults": {"_rel_of": "NODEFAULT",
                                        "build_c_model": "NODEFAULT",
                                        "_build_ext_model": "NODEFAULT"},
        }

    def red_loc(tag, obs, want):
        probs = judge_local(obs)
        hit = [p for p in probs if p.startswith(want)]
        others = [p for p in probs
                  if p[:3] in CRITERIA_IDS and not p.startswith(want)]
        for p in hit:
            witnessed_sub.add(p[:4])
        if not hit:
            bad[0] += 1
            print("  [selftest] %s 未被 %s 抓到（实得 %r）" % (tag, want, probs))
        elif others:
            bad[0] += 1
            print("  [selftest] %s 红在了别的判据上：%r" % (tag, others))
        else:
            good[0] += 1
            witnessed.add(want)

    green("好样本：F10 观测全部子判据全绿", judge_local(_obs_loc()))
    for tag, patch in (
            ("F10a 新口径吃了边（边账不等）", {"dup_edges_default": 5}),
            ("F10a 载荷那边与三口径对不上", {"dup_n_edges_json": 7}),
            ("F10b 阶梯没把真环收回来", {"dup_cycles_default": []}),
            ("F10b 环里出现跨文件成员（盲算给某一份定义）",
             {"dup_cycles_default": [["a @ cg_dup_a.c", "h @ cg_dup_b.c"]]}),
            ("F10b 同一个文件被拆成两个同名环",
             {"dup_cycles_default": [["a @ cg_dup_a.c", "h @ cg_dup_a.c"],
                                     ["a @ cg_dup_a.c", "h @ cg_dup_a.c"]]}),
            ("F10b 新口径造出了比名字级更大的环", {"dup_big_default": 4}),
            # ⚠ 这一条是**覆盖**半边唯一的证人：环仍然同文件、不重复、也比
            # 名字级小 —— 三条形状判据全绿，只有「有个文件没被收回来」能抓它。
            ("F10b 有调用者文件的环没被收回来（盲算给了别处）",
             {"dup_cycles_default": [["a @ cg_dup_a.c", "h @ cg_dup_a.c"]]}),
            ("F10b 拿不到夹具文件表（覆盖半边会变空断言）",
             {"dup_fixture_rels": None}),
            ("F10c 无同名可消歧处阶梯无中生有", {"inert_big_default": 9}),
            ("F10c 无同名可消歧处节点数变了", {"inert_nodes_default": 4}),
            ("F10c 无同名可消歧处边数变了", {"inert_edges_default": 5}),
            ("F10d resolution 各档之和与边数不符",
             {"dup_res_default": {"unique": 2, "same_file": 3, "include": 0,
                                  "ambiguous": 0, "external": 0}}),
            ("F10d 阶梯动了不该动的档（unique 变了）",
             {"dup_res_default": {"unique": 3, "same_file": 3, "include": 0,
                                  "ambiguous": 0, "external": 0}}),
            ("F10d resolution 块整个没了", {"dup_res_pure": None}),
            ("F10e 非 C 语料上阶梯竟然启用了",
             {"py_scope_default": {"applied": True, "lang": "py",
                                   "rungs": ["same-file"]}}),
            ("F10e 非 C 语料上台阶非空（语言门被绕过）",
             {"py_scope_default": {"applied": False, "lang": "py",
                                   "rungs": ["include-closure"]}}),
            ("F10e 非 C 语料上读数真的变了", {"py_big_default": 2}),
            ("F10e 产物没有自报 local_scope", {"py_scope_default": None}),
            # ---- F10f：第二级（翻译单元）活性 ----
            ("F10f 第二级没生效（定义在被包含的头里却判不出）",
             {"inc_res_default": {"unique": 0, "same_file": 0, "include": 0,
                                  "ambiguous": 2, "external": 0}}),
            ("F10f 把定义算成了「同文件」",
             {"inc_res_default": {"unique": 0, "same_file": 2, "include": 0,
                                  "ambiguous": 0, "external": 0}}),
            ("F10f 纯定义落点上也动了作用域（对照失效）",
             {"inc_res_pure": {"unique": 0, "same_file": 0, "include": 2,
                               "ambiguous": 0, "external": 0}}),
            ("F10f 拿不到 inc 夹具读数（第二级变空断言）",
             {"inc_res_default": None}),
            # ---- F10g：第二级的作用域边界 ----
            ("F10g 头文件里的调用点也走了第二级（错报方向）",
             {"hdr_res_default": {"unique": 0, "same_file": 0, "include": 2,
                                  "ambiguous": 0, "external": 0}}),
            ("F10g 判不出的没留在 ambiguous",
             {"hdr_res_default": {"unique": 0, "same_file": 0, "include": 0,
                                  "ambiguous": 0, "external": 0}}),
            ("F10g 产物没自报 header_callers（「我没判」装成「判不出来」）",
             {"hdr_scope_default": {"applied": True, "lang": "c",
                                    "rungs": ["same-file"],
                                    "header_callers": 0}}),
            ("F10g hdr 夹具上阶梯根本没启用（边界判据变空断言）",
             {"hdr_scope_default": {"applied": False, "lang": "c",
                                    "rungs": [], "header_callers": 2}}),
            # ---- F10h：三明治（过近似不许冒充真 TU）----
            ("F10h 假包含被当成了可见（过近似冒充真 TU）",
             {"incx_res_default": {"unique": 0, "same_file": 0,
                                   "include": 2, "ambiguous": 0,
                                   "external": 0}}),
            ("F10h 判不出的没全留在 ambiguous",
             {"incx_res_default": {"unique": 0, "same_file": 0,
                                   "include": 0, "ambiguous": 0,
                                   "external": 2}}),
            ("F10h incx 上定义被算成了「同文件」",
             {"incx_res_default": {"unique": 0, "same_file": 2,
                                   "include": 0, "ambiguous": 0,
                                   "external": 0}}),
            ("F10h 纯定义落点在 incx 上也动了作用域（对照失效）",
             {"incx_res_pure": {"unique": 0, "same_file": 0,
                                "include": 2, "ambiguous": 0,
                                "external": 0}}),
            ("F10h 拿不到 incx 夹具读数（三明治变空断言）",
             {"incx_res_default": None}),
            ("F10h 对照半边失效（inc 上 include 归零 ⇒ 前两条可被刷绿）",
             {"inc_res_default": {"unique": 0, "same_file": 0,
                                  "include": 0, "ambiguous": 2,
                                  "external": 0}}),
            ("F10h 截断冒充了三明治（closure_capped 不为 0）",
             {"incx_scope_default": {"applied": True, "lang": "c",
                                     "rungs": ["same-file",
                                               "include-closure"],
                                     "closure_capped": 1,
                                     "header_callers": 0}}),
            ("F10h incx 上阶梯根本没启用（测的是什么都没发生）",
             {"incx_scope_default": {"applied": False, "lang": "c",
                                     "rungs": [],
                                     "closure_capped": 0,
                                     "header_callers": 0}}),
            # ---- F10i：两级不许互相冒充（M3 逼出来的门洞）----
            ("F10i rung2 把「同文件」记成了「同翻译单元」",
             {"dup_res_default": {"unique": 2, "same_file": 0,
                                  "include": 4, "ambiguous": 0,
                                  "external": 0}}),
            ("F10i 救回的边没有全部来自 rung1（差额落到别处）",
             {"dup_res_default": {"unique": 2, "same_file": 3,
                                  "include": 1, "ambiguous": 0,
                                  "external": 0}}),
            ("F10i 对照半边失效（纯定义落点上没有歧义可救）",
             {"dup_res_pure": {"unique": 6, "same_file": 0,
                               "include": 0, "ambiguous": 0,
                               "external": 0}}),
            ("F10i 对照半边失效（inc 上 include 归零）",
             {"inc_res_default": {"unique": 0, "same_file": 0,
                                  "include": 0, "ambiguous": 2,
                                  "external": 0}}),
            ("F10i rung1 冒充 rung2（inc 上记成同文件）",
             {"inc_res_default": {"unique": 0, "same_file": 2,
                                  "include": 0, "ambiguous": 0,
                                  "external": 0}}),
            # ---- F10j：第二级的代价（缓存必须真的缓存）----
            ("F10j 闭包缓存退化成重算（每个文件算的次数 > 2）",
             {"multi_scope_default": {"applied": True, "lang": "c",
                                      "rungs": ["same-file",
                                                "include-closure"],
                                      "under_basis": "unique-basename-target",
                                      "rung2_files": 12,
                                      "closure_computed": 48,
                                      "closure_visits": 120,
                                      "closure_capped": 0,
                                      "header_callers": 0}}),
            ("F10j 代价计数器是死的（visits 恒 0 ⇒ 判据变空断言）",
             {"multi_scope_default": {"applied": True, "lang": "c",
                                      "rungs": ["same-file",
                                                "include-closure"],
                                      "under_basis": "unique-basename-target",
                                      "rung2_files": 12,
                                      "closure_computed": 24,
                                      "closure_visits": 0,
                                      "closure_capped": 0,
                                      "header_callers": 0}}),
            ("F10j 阶梯根本没走到第二级（尝试是空的 ⇒ 代价不变量无从谈起）",
             {"multi_scope_default": {"applied": True, "lang": "c",
                                      "rungs": ["same-file",
                                                "include-closure"],
                                      "under_basis": "unique-basename-target",
                                      "rung2_files": 0,
                                      "closure_computed": 0,
                                      "closure_visits": 0,
                                      "closure_capped": 0,
                                      "header_callers": 0}}),
            ("F10j 夹具读数本身不自洽（五档之和 != 边数）",
             {"multi_res_default": {"unique": 2, "same_file": 0, "include": 48,
                                    "ambiguous": 0, "external": 0}}),
            ("F10j 拿不到 multi 夹具读数（缓存退化变空断言）",
             {"multi_scope_default": None}),
            ("F10i 拿不到 dup 夹具的两口径 resolution",
             {"dup_res_pure": None}),
            # ---- F10k：`under` 的唯一性口径（R89k）----
            ("F10k 共享头被按 include 行数丢掉（第二级在主战场上恒判不出）",
             {"multi_res_default": {"unique": 0, "same_file": 0, "include": 0,
                                    "ambiguous": 48, "external": 0}}),
            ("F10k 口径没被登记（只能靠读代码猜）",
             {"multi_scope_default": {"applied": True, "lang": "c",
                                      "rungs": ["same-file",
                                                "include-closure"],
                                      "rung2_files": 12,
                                      "closure_computed": 24,
                                      "closure_visits": 72,
                                      "closure_capped": 0,
                                      "header_callers": 0}}),
            ("F10k 口径登记成了别的值（登记本身不再是空话）",
             {"multi_scope_default": {"applied": True, "lang": "c",
                                      "rungs": ["same-file",
                                                "include-closure"],
                                      "under_basis": "include-row-count",
                                      "rung2_files": 12,
                                      "closure_computed": 24,
                                      "closure_visits": 72,
                                      "closure_capped": 0,
                                      "header_callers": 0}}),
            # ---- F10l：`rel` 的基准 = 被分析根（R90）----
            ("F10l 同名不同目录被合并（rel 退回 cwd 相对）",
             {"dupx_res_default": {"unique": 0, "same_file": 0, "include": 0,
                                   "ambiguous": 4, "external": 0}}),
            ("F10l 产物自报的文件塌成同名 basename",
             {"dupx_files_seen": ["x.c"]}),
            ("F10l 有界投影被截断 ⇒ 形态判据看到的文件集不完整",
             {"dupx_proj_whole": False}),
            ("F10l 拿不到 dupx 夹具读数（rel 基准变空断言）",
             {"dupx_res_default": None}),
            ("F10l 对照半边失效（纯定义落点上也不歧义）",
             {"dupx_res_pure": {"unique": 4, "same_file": 0, "include": 0,
                                "ambiguous": 0, "external": 0}}),
            ("F10l `root` 带了默认值（静默的 cwd 回退又回来了）",
             {"rel_root_param_defaults": {"_rel_of": "DEFAULT",
                                          "build_c_model": "NODEFAULT",
                                          "_build_ext_model": "NODEFAULT"}}),
            ("F10l `root` 形参整个不见了（组装器不再接受根）",
             {"rel_root_param_defaults": {"_rel_of": "NODEFAULT",
                                          "build_c_model": "MISSING",
                                          "_build_ext_model": "NODEFAULT"}}),
            ("F10l 拿不到 `root` 形参读数（「不许静默」变空断言）",
             {"rel_root_param_defaults": None}),
    ):
        d = _obs_loc()
        d.update(patch)
        red_loc("坏样本 %s" % tag, d, "F10")
    for letter in ("F10a", "F10b", "F10c", "F10d", "F10e", "F10f", "F10g",
                   "F10h", "F10i", "F10j", "F10k", "F10l"):
        if letter not in witnessed_sub:
            bad[0] += 1
            print("  [selftest] F10 的子判据 %s 没有自己的坏样本（子覆盖静默缩水）"
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
    if judge_fixtures(cg_dup=(("cg_dup_a.c", "static void a(void) { h(); }\n"),
                              ("cg_dup_b.c", "static void h(void) { b(); }\n"))):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] 重复定义夹具被抽掉「同名两份定义」后 R2 不报红"
              "（F9d 的『环必须塌』退化成空断言）")
    if judge_fixtures(cg_py=(("cg_py_a.py", "def a():\n    h()\n"),
                             ("cg_py_b.py", "def b():\n    h()\n"))):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] Python 夹具被抽掉「同名定义」后 R2 不报红"
              "（F10e 的语言门退化成空断言）")
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
