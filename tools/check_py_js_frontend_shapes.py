#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""登记制护栏：Python / JS 前端的「函数定义形态」判据必须活在仓库里（R66 / R49 §9 第 6 条）。

动因（R49 §9 第 6 条原话：「探针可以放 `_r49/`，但任何**说得出什么会红**的断言必须进
`tools/` 或 `tests/`」；R61 已对 **C 前端**兑现，Python / JS 一直没兑现）：
  R49 之后 C 前端有 `tools/check_c_frontend_shapes.py`（F1–F6）守着形态；
  而 P93 起就存在的 **Python / JS 前端至今没有任何形态判据**。
  仓库外独立装置 `_r66/probe_r66a_forms.py` 实测（R66 修**前**）：
    * Python：8 个真实常见形态里 **4 个认不出来**
      （`def one(): return 1` / `async def` / `def f(a) -> bool:` / 参数表跨行）；
    * JS：10 个里 **8 个认不出来**
      （`async function` / `export function` / `export default function` /
        `function*` / 三种箭头函数）；
    * 对照：同一台装置量 C 前端 —— **6 个形态 0 漏**。
  第二台装置 `_r66/probe_r66b_domain.py` 量出**值域**缺陷：形参表里的嵌套括号
  （`x=(1, 2)` / `b = g(1, 2)`）会把参数截断，严重时**整个定义认不出来**
  （`def deep(x=(1, 2), y=g2(3, 4)):`）。
  R66 已把两处修掉（同装置复量：Python 0/8、JS 1/10、值域 0/8、假阳 0/7；
  剩的那 1 个是**有意披露不识别**的对象方法简写）。
  **修完就得有东西守着它**，否则下一轮就丢 —— 这正是 R61 对 C 前端做的事。

为什么走**公开 CLI 子进程**（不 `import matlabc`）：与 R54 / R55 / R61 同一条纪律 ——
  ① `tools/` 不 import 产品模块（宁可另写同义实现）；
  ② 公开 CLI（`--lang py|js --json`）才是用户真正看到的那一面：内部函数对了、
     组装错了（行号算错 / params 被截断），一样是缺陷。

判据（G1–G7；七条判据的**管辖范围互不重叠**，每条各有自己的突变体作独立证人）：
  G1 Python 四形态全覆盖：**单行体** `def one(): return 1` / **`async def`** /
     **返回注解** `def f(a) -> bool:` / **参数表跨行**。少任一种 ⇒ 红。
  G2 JS 七形态全覆盖：`async function` / `export function` / `export default
     function` / `function*` / **三种箭头**（带括号、单参裸标识符、`async`）。少任一 ⇒ 红。
  G3 形参**值域**逐字段相等：注解必须剥掉（`a: int` → `a`）、`*args` / `**kw`
     保留星号、`/` 与裸 `*` 记号丢弃、**默认值里的嵌套括号不切错**
     （`x=(1, 2)` / `b = g(1, 2)` —— 老正则 `\\(([^)]*)\\)` 在这里会截断）。
  G4 不假阳：Python 侧 `lambda` / 调用 / `if __name__`；JS 侧控制语句 / 调用 / 对象键。
  G5 已披露边界保持不识别：JS 的**对象方法简写** `greet(a) { }` 与**匿名**
     `export default function (a) { }` —— 本门 docstring 与两侧 README 都披露了，
     认出来等于**承诺与行为分叉**。另含 G5 的**正向半边**（neg 里的真函数必须认出来）：
     只写「必须不出现」的判据在「产品什么都不产出」时也成立 —— 那是**空断言**。
  G6 声明起点行号：跨行参数表的函数，`line` 必须等于**声明起点**那一行，不能是
     `{` / 参数表末行（G1 只查存在性、G3 只查值域 ⇒ 三条互不重叠）。
  G7 不**过度**识别：写在三引号字符串 / 块注释 / 模板串里、独占一行的
     `def ghost(a, b):` / `function ghostfn(a, b) {` **必须不被认出来** ——
     仓库外装置 `_r67/probe_r67_overrecog.py` 实测基线 **7/12 泄漏**，R67 修掉。

过度识别（G7）：`_scan_py_defs` 只做括号配平，于是**文档字符串里独占一行的
  `def pseudo():` 会被当成真函数**。R66 只把它披露在这里、**不给判据**；R67 给
  py / js 两个扫描器加了字符串 / 注释状态机，并**补上判据 G7** —— 夹具里字符串 /
  注释内的 `def ghost(a, b):` 与 `function ghostfn(a, b) {` **必须不被认出来**。
  改产品却漏改这段披露，就等于**承诺与行为分叉**。

两向自证（`--selftest`）：1 个好样本 + 15 个坏样本喂给**纯函数** `judge()`，
每个坏样本必须红在**它该红的**那条判据上，且**只**红那一条（`others == []`）；
另外还自证：夹具完备性判据 `R2` 两向、棘轮 `R1` 两向、坏 JSON 被判为缺输入。

一图看懂：

    合成夹具（2 个 .py + 2 个 .js，纯手写）        公开 CLI（--lang py|js --json）
    ┌────────────────────────┐                  ┌──────────────────────────────┐
    │ shapes.py  单行/async/ │── G1/G3/G6 ─────▶│ files[].functions[]          │
    │            注解/跨行/嵌套│                 │  {name, params, line, ...}   │
    │            默认值嵌套括号│                 │                              │
    │ neg.py     lambda/调用/ │── G4/G5/G7 ─────▶│                              │
    │            if __name__  │                 │                              │
    │ shapes.js  七形态 /     │── G2/G3/G6 ─────▶│                              │
    │            默认值嵌套括号│                 │                              │
    │ neg.js     控制/调用/   │── G4/G5/G7 ─────▶│                              │
    │            方法简写/匿名 │                 │                              │
    └────────────────────────┘                  └──────────────────────────────┘
              ▲                                              │
              └──── 手写期望 WANT（独立于产品）──────────────┘

退出码：
    0 = G1–G7 全绿，且棘轮与夹具完备性全绿
    1 = 有违规（某条判据红 / 棘轮不符 / 夹具被改瘦）
    2 = 缺输入（找不到 matlabc.py / 公开 CLI 跑不起来 / JSON 不可解析）

用法：
    python tools/check_py_js_frontend_shapes.py             # 0=全绿 1=违规 2=缺输入
    python tools/check_py_js_frontend_shapes.py --selftest   # 两向自证
    python tools/check_py_js_frontend_shapes.py --help       # 显示本帮助
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族）。
# 它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
# R67：签名带 `(py/js)` 限定 —— `check_import_graph.py` 已经占用 `G1–G7`，
# 两道门共用同一个签名时 P5 无法区分（它会直接报红）。判据族仍是 G1–G7。
ROW_SIGNATURE = "G1–G7 (py/js)"

# H3（R73）：越出签名族、但仍由本门发出的判据前缀。
ROW_EXTRA = "R1,R2"
# 公开 CLI 的墙钟上限。实测一次 ≈0.5s，300s 是给「机器正忙」留的量级余量；
# 它的意义是「让挂死变成红，而不是让门永远等着」。
CLI_TIMEOUT = 300.0

# ---------------------------------------------------------------------------
# 夹具：纯合成，不联网、不建 GUI、不读仓库里任何 .py / .js
# ---------------------------------------------------------------------------
SHAPES_PY = (
    "def plain(a, b):\n"                     # 基线：老实现也认
    "    return a + b\n"
    "\n"
    "def one(): return 1\n"                  # G1-a：单行体
    "\n"
    "async def afetch(url):\n"               # G1-b：async
    "    return url\n"
    "\n"
    "def typed(a: int, b: str = \"x\") -> bool:\n"   # G1-c：返回注解 + 参数注解
    "    return True\n"
    "\n"
    "def wide(a,\n"                          # G1-d：参数表跨行
    "         b,\n"
    "         c):\n"
    "    return a\n"
    "\n"
    "def outer():\n"                         # 嵌套（老实现也认）
    "    def inner():\n"
    "        return 1\n"
    "    return inner\n"
    "\n"
    "class C:\n"                             # 类方法（老实现也认）
    "    def m(self):\n"
    "        return 1\n"
    "\n"
    "def deep(x=(1, 2), y=g2(3, 4)):\n"      # G3：默认值里的嵌套括号
    "    return x\n")

NEG_PY = (
    "lam = lambda x: x + 1\n"                # 假阳陷阱：lambda 不是 def
    "def real():\n"                          # 唯一的真函数（G5 正向半边）
    "    \"\"\"Real.\n"                     # G7：三引号字符串从这里开始
    "\n"
    "    def ghost(a, b):\n"                 # G7：字符串里的假定义，必须**不**被认出
    "        return a\n"
    "    \"\"\"\n"                             # G7：三引号字符串在这里结束
    "    return compute(1)\n"                # 假阳陷阱：调用名不是函数
    "if __name__ == \"__main__\":\n"          # 假阳陷阱：控制语句
    "    pass\n")

SHAPES_JS = (
    "function add(a, b) {\n"                 # 基线
    "  return a + b;\n"
    "}\n"
    "\n"
    "async function fetchIt(url) {\n"        # G2-a：async function
    "  return url;\n"
    "}\n"
    "\n"
    "export function exp(a) {\n"             # G2-b：export function
    "  return a;\n"
    "}\n"
    "\n"
    "export default function main2(a) {\n"   # G2-c：export default function
    "  return a;\n"
    "}\n"
    "\n"
    "function* gen(a) {\n"                   # G2-d：生成器
    "  yield a;\n"
    "}\n"
    "\n"
    "const f = (a) => {\n"                   # G2-e：箭头（块体）
    "  return a;\n"
    "};\n"
    "\n"
    "const g = (a) => a + 1;\n"              # G2-e'：箭头（表达式体）
    "\n"
    "const h = async (a) => {\n"             # G2-f：async 箭头
    "  return a;\n"
    "};\n"
    "\n"
    "foo = function (a) {\n"                 # 裸标识符赋值（老实现也认）
    "  return a;\n"
    "};\n"
    "\n"
    "function h2(a, b = g2(1, 2)) {\n"       # G3：默认值里的嵌套括号
    "  return a;\n"
    "}\n")

NEG_JS = (
    "if (x) { }\n"                           # 假阳陷阱：控制语句
    "for (;;) { }\n"
    "while (y) { }\n"
    "switch (z) { }\n"
    "\n"
    "function real() {\n"                    # 唯一的真函数（G5 正向半边）
    "  foo(bar);\n"                          # 假阳陷阱：调用名不是函数
    "}\n"
    "\n"
    "const obj = {\n"                        # 假阳陷阱：对象键
    "  greet(a) {\n"                         # G5 已披露边界：方法简写
    "    return a;\n"
    "  }\n"
    "};\n"
    "\n"
    "export default function (a) {\n"        # G5 已披露边界：匿名 default
    "  return a;\n"
    "}\n"
    "\n"
    "/*\n"                                   # G7：块注释从这里开始
    "function ghostfn(a, b) {\n"             # G7：注释里的假定义，必须**不**被认出
    "  return a;\n"
    "}\n"
    "const ghostarrow = (a) => {\n"          # G7：注释里的箭头假定义
    "  return a;\n"
    "};\n"
    "*/\n")

FIXTURES = (("shapes.py", SHAPES_PY),
            ("neg.py", NEG_PY),
            ("shapes.js", SHAPES_JS),
            ("neg.js", NEG_JS))

# 手写期望 —— **独立于产品**（不是跑产品得到的结果），也不来自任何 tools/ 装置。
WANT = {
    "shapes.py": {
        "plain":  {"params": ["a", "b"], "line": 1},
        "one":    {"params": [], "line": 4},
        "afetch": {"params": ["url"], "line": 6},
        "typed":  {"params": ["a", "b"], "line": 9},
        "wide":   {"params": ["a", "b", "c"], "line": 12},
        "outer":  {"params": [], "line": 17},
        "inner":  {"params": [], "line": 18},
        "m":      {"params": ["self"], "line": 23},
        "deep":   {"params": ["x", "y"], "line": 26},
    },
    "neg.py": {
        "real":   {"params": [], "line": 2},
    },
    "shapes.js": {
        "add":     {"params": ["a", "b"], "line": 1},
        "fetchIt": {"params": ["url"], "line": 5},
        "exp":     {"params": ["a"], "line": 9},
        "main2":   {"params": ["a"], "line": 13},
        "gen":     {"params": ["a"], "line": 17},
        "f":       {"params": ["a"], "line": 21},
        "g":       {"params": ["a"], "line": 25},
        "h":       {"params": ["a"], "line": 27},
        "foo":     {"params": ["a"], "line": 31},
        "h2":      {"params": ["a", "b = g2(1, 2)"], "line": 35},
    },
    "neg.js": {
        "real":    {"params": [], "line": 6},
    },
}

# G1 的全部职责：这四个名字必须都在（值域归 G3、行号归 G6）
G1_NAMES_PY = ("one", "afetch", "typed", "wide")
# G2 的全部职责：这七个名字必须都在
G2_NAMES_JS = ("fetchIt", "exp", "main2", "gen", "f", "g", "h")
# G3 的职责：这些函数的 params 必须逐字段等于 WANT
G3_NAMES_PY = ("typed", "wide", "deep")
G3_NAMES_JS = ("h2",)
# G4 的假阳陷阱（**必须不出现**）
FP_TRAPS_PY = ("lam", "compute", "if")
FP_TRAPS_JS = ("if", "for", "while", "switch", "foo", "bar", "obj")
# G5 的已披露边界（**必须不出现**；正向半边 = 每个 neg 里的真函数必须出现）
BOUNDARY_TRAPS_JS = ("greet",)
# G7 的过度识别陷阱（**必须不出现**）：写在三引号字符串 / 块注释里、独占一行的定义。
OVER_RECOG_PY = ("ghost",)
OVER_RECOG_JS = ("ghostfn", "ghostarrow")

CRITERIA = (
    ("G1", "Python 四形态全覆盖（单行体 / async / 返回注解 / 参数表跨行）"),
    ("G2", "JS 七形态全覆盖（async / export / export default / 生成器 / 三种箭头）"),
    ("G3", "形参值域逐字段相等（注解剥离 / 星号保留 / 嵌套括号不切错）"),
    ("G4", "不假阳（lambda / 调用 / 控制语句 / 对象键）"),
    ("G5", "已披露边界保持不识别（方法简写 / 匿名 default），且 neg 里的真函数必须认出来"),
    ("G6", "声明起点行号逐字段相等"),
    ("G7", "不**过度**识别（三引号字符串 / 块注释 / 模板串里独占一行的定义必须不被认出）"),
)
CRITERIA_IDS = tuple(c[0] for c in CRITERIA)

# ---------------------------------------------------------------------------
# 棘轮：全部是「事实的读数」，不是可调参数。覆盖不许静默缩水。
# ---------------------------------------------------------------------------
EXPECTED_CRITERIA = 7
EXPECTED_FIXTURES = 4
EXPECTED_G1 = 4
EXPECTED_G2 = 7
EXPECTED_BOUNDARY_TRAPS = 1
EXPECTED_OVER_RECOG_PY = 1
EXPECTED_OVER_RECOG_JS = 2
EXPECTED_PY_FUNCS = 10           # 9（shapes.py）+ 1（neg.py）；ghost **不**计入
EXPECTED_JS_FUNCS = 11           # 10（shapes.js）+ 1（neg.js）；ghostfn/ghostarrow **不**计入


# ---------------------------------------------------------------------------
# 纯函数判据（不碰文件系统与子进程 —— 自证可以直接喂合成结果）
# ---------------------------------------------------------------------------
def judge(per):
    """六条判据的实现。

    per = {夹具基名: {函数名: (params, line)}}
    返回问题列表；每条以判据 id（`G1`…`G6`）+ 空格开头。
    """
    if not isinstance(per, dict):
        return ["G0 判据载体不是字典（parse_shapes 的返回值坏了）"]

    py = per.get("shapes.py") or {}
    ngpy = per.get("neg.py") or {}
    js = per.get("shapes.js") or {}
    ngjs = per.get("neg.js") or {}
    probs = []

    # ---- G1 Python 四形态全覆盖（只看**存在性**；值域归 G3、行号归 G6） ----
    miss = [n for n in G1_NAMES_PY if n not in py]
    if miss:
        probs.append("G1 shapes.py 漏掉形态函数 %r —— Python 形态支持退化了"
                     % (miss,))

    # ---- G2 JS 七形态全覆盖（同上，只看存在性） ----
    miss = [n for n in G2_NAMES_JS if n not in js]
    if miss:
        probs.append("G2 shapes.js 漏掉形态函数 %r —— JS 形态支持退化了"
                     % (miss,))

    # ---- G3 形参值域（只对**已出现**的判；存在性归 G1/G2） ----
    for rel, names in (("shapes.py", G3_NAMES_PY), ("shapes.js", G3_NAMES_JS)):
        got = per.get(rel) or {}
        for fn in names:
            if fn not in got:
                continue
            w = WANT[rel][fn]["params"]
            g = list(got[fn]["params"] or [])
            if g != w:
                probs.append("G3 %s:%s 的 params 实测 %r，期望 %r"
                             % (rel, fn, g, w))

    # ---- G4 不假阳 ----
    for rel, traps in (("neg.py", FP_TRAPS_PY), ("neg.js", FP_TRAPS_JS)):
        got = per.get(rel) or {}
        leak = [n for n in traps if n in got]
        if leak:
            probs.append("G4 %s 把 %r 当成函数（lambda / 调用 / 控制语句 / 对象键假阳）"
                         % (rel, leak))

    # ---- G5 已披露边界 + 正向半边 ----
    for rel in ("neg.py", "neg.js"):
        got = per.get(rel) or {}
        for fn in sorted(WANT[rel]):
            if fn not in got:
                probs.append("G5 %s 漏掉真函数 %s —— 只断言「不出现」是空断言，"
                             "这里就是它的正向对手方" % (rel, fn))
    bd = [n for n in BOUNDARY_TRAPS_JS if n in ngjs]
    if bd:
        probs.append("G5 neg.js 竟认出 %r —— 本门 docstring 已披露这两类**不识别**，"
                     "认出来等于承诺与行为分叉" % (bd,))

    # ---- G7 不**过度**识别：字符串 / 注释 / 模板串里独占一行的定义必须不被认出 ----
    for rel, names in (("neg.py", OVER_RECOG_PY), ("neg.js", OVER_RECOG_JS)):
        got = per.get(rel) or {}
        leak = [n for n in names if n in got]
        if leak:
            probs.append("G7 %s 把字符串 / 注释里的 %r 当成真函数（过度识别）"
                         % (rel, leak))

    # ---- G6 声明起点行号（三个夹具里**已出现**的函数；存在性归 G1/G2/G5） ----
    for rel in ("shapes.py", "shapes.js"):
        got = per.get(rel) or {}
        for fn in sorted(WANT[rel]):
            if fn not in got:
                continue
            if got[fn]["line"] != WANT[rel][fn]["line"]:
                probs.append("G6 %s:%s 的 line 实测 %r，期望 %d"
                             % (rel, fn, got[fn]["line"], WANT[rel][fn]["line"]))
    return probs


def judge_fixtures(fixtures=None, neg_py=None, neg_js=None,
                   shapes_py=None, shapes_js=None):
    """夹具完备性：每条陷阱 / 每个形态标记必须在夹具源码里**逐字**出现。

    为什么这是必需的一环（R56 的自伤教训：**口径变一次，样本完备性就得跟着重算**）：
    判据是从夹具里读证据的。若夹具里那句 `if (x) { }` 被删掉，「不得出现 `if`」
    这条判据就退化成**空断言** —— 它永远绿，而且**没有任何东西会告诉你**。
    """
    fixtures = FIXTURES if fixtures is None else fixtures
    npy = NEG_PY if neg_py is None else neg_py
    njs = NEG_JS if neg_js is None else neg_js
    spy = SHAPES_PY if shapes_py is None else shapes_py
    sjs = SHAPES_JS if shapes_js is None else shapes_js
    probs = []
    for name in FP_TRAPS_PY:
        if name not in npy:
            probs.append("R2 neg.py 夹具里找不到陷阱 %r —— 那条判据变成空断言"
                         % name)
    for name in FP_TRAPS_JS + BOUNDARY_TRAPS_JS:
        if name not in njs:
            probs.append("R2 neg.js 夹具里找不到陷阱 %r —— 那条判据变成空断言"
                         % name)
    # 四种 py 形态必须真的以那种形态写在夹具里
    for marker, why in (("def one(): return 1\n", "单行体"),
                        ("async def afetch(", "async"),
                        ('def typed(a: int, b: str = "x") -> bool:', "返回注解"),
                        ("def wide(a,\n", "参数表跨行"),
                        ("def deep(x=(1, 2), y=g2(3, 4)):", "默认值嵌套括号")):
        if marker not in spy:
            probs.append("R2 shapes.py 缺形态标记 %r（%s）" % (marker, why))
    # 七种 js 形态同上
    for marker, why in (("async function fetchIt(", "async function"),
                        ("export function exp(", "export function"),
                        ("export default function main2(", "export default"),
                        ("function* gen(", "生成器"),
                        ("const f = (a) => {", "箭头（块体）"),
                        ("const g = (a) => a + 1;", "箭头（表达式体）"),
                        ("const h = async (a) => {", "async 箭头"),
                        ("function h2(a, b = g2(1, 2)) {", "默认值嵌套括号")):
        if marker not in sjs:
            probs.append("R2 shapes.js 缺形态标记 %r（%s）" % (marker, why))
    # G7 的陷阱必须真的以「字符串 / 注释里」的形态写进夹具
    if "def ghost(a, b):" not in npy:
        probs.append("R2 neg.py 夹具里找不到字符串内的假定义 'def ghost(a, b):'"
                     " —— G7 变成空断言")
    if "function ghostfn(a, b) {" not in njs:
        probs.append("R2 neg.js 夹具里找不到注释内的假定义"
                     " 'function ghostfn(a, b) {' —— G7 变成空断言")
    for rel, text in fixtures:
        if not text.strip():
            probs.append("R2 夹具 %s 是空的" % rel)
    return probs


def judge_ratchet(n_py, n_js):
    """棘轮：登记值必须**等于**真实值（删掉一整个家族而不改数字 ⇒ 红）。"""
    probs = []
    for tag, got, want in (("判据条数", len(CRITERIA), EXPECTED_CRITERIA),
                           ("夹具数", len(FIXTURES), EXPECTED_FIXTURES),
                           ("G1 形态名数", len(G1_NAMES_PY), EXPECTED_G1),
                           ("G2 形态名数", len(G2_NAMES_JS), EXPECTED_G2),
                           ("已披露边界陷阱数", len(BOUNDARY_TRAPS_JS),
                            EXPECTED_BOUNDARY_TRAPS),
                           ("过度识别陷阱数（py）", len(OVER_RECOG_PY),
                            EXPECTED_OVER_RECOG_PY),
                           ("过度识别陷阱数（js）", len(OVER_RECOG_JS),
                            EXPECTED_OVER_RECOG_JS),
                           ("Python 认出函数数", n_py, EXPECTED_PY_FUNCS),
                           ("JS 认出函数数", n_js, EXPECTED_JS_FUNCS)):
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
    """把 `--json` 产物转成 {基名: {函数名: (params, line)}}。

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
            d[fn.get("name")] = {"params": fn.get("params"),
                                 "line": fn.get("line")}
        per[base] = d
    return per


def scan(root, python_exe):
    """建夹具 → 跑两次公开 CLI（py / js）→ 合并读数。

    返回 (per, n_py, n_js)；per 为 None 表示**缺输入**（跑不起来 / JSON 坏）。
    """
    base = tempfile.mkdtemp(prefix="r66gate_")
    try:
        src = os.path.join(base, "src")
        os.makedirs(src)
        for rel, text in FIXTURES:
            with io.open(os.path.join(src, rel), "w", encoding="utf-8",
                         newline="") as fh:
                fh.write(text)
        # 产物落在 base（**src 之外**）：否则第二次跑就会把自己的产物当语料扫进去
        per = {}
        counts = {}
        for lang in ("py", "js"):
            out_json = os.path.join(base, "out_%s.json" % lang)
            argv = [python_exe, "matlabc.py", src, "--lang", lang,
                    "--json", out_json, "--max-warnings", "999"]
            p = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=CLI_TIMEOUT)
            if p.returncode != 0:
                return None, 0, 0
            if not os.path.isfile(out_json):
                return None, 0, 0
            with io.open(out_json, "rb") as fh:
                jt = fh.read().decode("utf-8", "replace")
            d = parse_shapes(jt)
            if d is None:
                return None, 0, 0
            per.update(d)
            counts[lang] = sum(len(v) for v in d.values())
        return per, counts.get("py", 0), counts.get("js", 0)
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
        print("check_py_js_frontend_shapes: 找不到 matlabc.py（缺输入 → 红）：%s" % root)
        return 2
    try:
        per, n_py, n_js = scan(root, sys.executable)
    except (OSError, subprocess.SubprocessError) as e:
        print("check_py_js_frontend_shapes: 公开 CLI 跑不起来：%s（缺输入 → 红）" % e)
        return 2
    if per is None:
        print("check_py_js_frontend_shapes: 公开 CLI 没产出可解析的 JSON"
              "（--json 是判据的载体 → 缺输入）")
        return 2

    probs = list(judge(per)) + judge_fixtures() + judge_ratchet(n_py, n_js)
    if probs:
        for p in probs:
            print("check_py_js_frontend_shapes: " + p)
        print("check_py_js_frontend_shapes: %d 项违规" % len(probs))
        return 1
    print("check_py_js_frontend_shapes: OK（%d 个合成夹具 / 公开 CLI 认出 Python %d 个、"
          "JS %d 个函数 / %s 全绿 + 夹具完备性 + 棘轮）"
          % (len(FIXTURES), n_py, n_js, ROW_SIGNATURE))
    return 0


# ---------------------------------------------------------------------------
# 两向自证：坏样本必须红在**指定**判据上，好样本必须全绿
# ---------------------------------------------------------------------------
def _selftest():
    """`bad` 数的是**本装置自己的失误**：坏样本没红、或红在了别的判据上。"""
    bad = [0]
    good = [0]
    witnessed = set()

    def _mk(sp=None, np_=None, sj=None, nj=None):
        return {"shapes.py": dict(WANT["shapes.py"] if sp is None else sp),
                "neg.py": dict(WANT["neg.py"] if np_ is None else np_),
                "shapes.js": dict(WANT["shapes.js"] if sj is None else sj),
                "neg.js": dict(WANT["neg.js"] if nj is None else nj)}

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

    # ---- G1：抽掉「参数表跨行」那一个（正是 R66 之前的退化形态） ----
    d = _mk()
    d["shapes.py"].pop("wide")
    red("坏样本 G1 抽掉参数表跨行", d, "G1")

    # ---- G1'：抽掉 async ----
    d = _mk()
    d["shapes.py"].pop("afetch")
    red("坏样本 G1 抽掉 async def", d, "G1")

    # ---- G2：抽掉生成器 ----
    d = _mk()
    d["shapes.js"].pop("gen")
    red("坏样本 G2 抽掉生成器", d, "G2")

    # ---- G2'：抽掉 async 箭头 ----
    d = _mk()
    d["shapes.js"].pop("h")
    red("坏样本 G2 抽掉 async 箭头", d, "G2")

    # ---- G3：注解没剥掉（老实现的真实行为：`a: int` 被当成名字） ----
    d = _mk()
    d["shapes.py"]["typed"] = {"params": ["a: int", "b: str"], "line": 9}
    red("坏样本 G3 注解没剥掉", d, "G3")

    # ---- G3'：默认值里的嵌套括号把参数切错（退回 `raw.split(",")` 的退化形态） ----
    d = _mk()
    d["shapes.py"]["deep"] = {"params": ["x=(1", "2)", "y=g2(3", "4)"], "line": 26}
    red("坏样本 G3 Python 默认值被括号切碎", d, "G3")
    d = _mk()
    d["shapes.js"]["h2"] = {"params": ["a", "b = g2(1, 2"], "line": 35}
    red("坏样本 G3 JS 默认值被括号截断", d, "G3")

    # ---- G4：Python 侧假阳 ----
    d = _mk()
    d["neg.py"]["lam"] = {"params": [], "line": 1}
    red("坏样本 G4 Python lambda 假阳", d, "G4")

    # ---- G4'：JS 侧假阳 ----
    d = _mk()
    d["neg.js"]["switch"] = {"params": [], "line": 4}
    red("坏样本 G4 JS 控制语句假阳", d, "G4")

    # ---- G5：已披露边界被认出来 ----
    for fn in BOUNDARY_TRAPS_JS:
        d = _mk()
        d["neg.js"][fn] = {"params": ["a"], "line": 11}
        red("坏样本 G5 已披露边界 %s 被认出" % fn, d, "G5")

    # ---- G5'：neg 什么都产出不了 ⇒ 正向半边必须红（空断言的对手方） ----
    red("坏样本 G5 负半边空断言（neg.py 全空）", _mk(np_={}), "G5")

    # ---- G7：过度识别 —— 字符串 / 注释里的假定义被认出来 ----
    for rel, names in (("neg.py", OVER_RECOG_PY), ("neg.js", OVER_RECOG_JS)):
        for fn in names:
            d = _mk()
            d[rel][fn] = {"params": ["a"], "line": 5}
            red("坏样本 G7 过度识别 %s:%s" % (rel, fn), d, "G7")

    # ---- G6：行号漂移（跨行参数表少算一行） ----
    d = _mk()
    d["shapes.py"]["wide"] = {"params": ["a", "b", "c"], "line": 13}
    red("坏样本 G6 行号漂移", d, "G6")

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
    if judge_fixtures(neg_py="x = 1\n"):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] neg.py 陷阱被删掉后 R2 不报红（判据退化成空断言）")
    if judge_fixtures(neg_js="function real() { }\n"):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] neg.js 陷阱被删掉后 R2 不报红")
    if judge_fixtures(shapes_py="def f(): pass\n"):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] shapes.py 形态标记被删掉后 R2 不报红")
    if judge_fixtures(shapes_js="function f() { }\n"):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] shapes.js 形态标记被删掉后 R2 不报红")
    if judge_fixtures(fixtures=(("empty.py", "  \n"),)):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] 空夹具 R2 不报红")
    if judge_fixtures(neg_py=NEG_PY.replace("def ghost(a, b):", "x = 1")):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] neg.py 的过度识别陷阱被删掉后 R2 不报红")
    if judge_fixtures(neg_js=NEG_JS.replace("function ghostfn(a, b) {",
                                            "function z() {")):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] neg.js 的过度识别陷阱被删掉后 R2 不报红")

    # ---- ④ 棘轮 R1 两向：正确读数不报红，缩水读数必须报红 ----
    green("好样本：棘轮在正确读数上全绿",
          judge_ratchet(EXPECTED_PY_FUNCS, EXPECTED_JS_FUNCS))
    if judge_ratchet(EXPECTED_PY_FUNCS - 1, EXPECTED_JS_FUNCS):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] 棘轮在 Python 缩水读数上不报红")
    if judge_ratchet(EXPECTED_PY_FUNCS, EXPECTED_JS_FUNCS - 1):
        good[0] += 1
    else:
        bad[0] += 1
        print("  [selftest] 棘轮在 JS 缩水读数上不报红")

    return bad[0], good[0]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
