#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""登记制护栏：「诚实的边界」里每条「不做」承诺，必须有能说「不」的判据。

动因（R55，**真缺陷，两条独立证据**，都来自仓库外装置 `E:\\matlabc\\_r55\\`）：
  1. `--help` 的「诚实的边界」是**产品对用户的书面承诺**。R51 已把它变成与
     `BOUNDARY_CLAIMS` 互为对手方的**逐字契约** —— 但 R51 只核对「这句话还在不在」，
     **从不核对这句话是否仍然成立**。R55 装置 `probe_p6.py` 在 7 种情形下量出：
     `语言：` 这条写着「扫到这些文件时它会打出 [warn]」，实际**只有当本次语言的
     源文件数为 0 时才 warn** —— `.c` 与 `.rs` **混放时 stderr 一行都没有**
     （E2/E3/E4 各 0 行）。而同一事实 README 两侧写的是对的
     （「而本次请求的语言一个源文件都没找到时」）⇒ **帮助与 README 分叉**。
  2. 「前端实现：」这条逐字承诺「仍**不识别** K&R 老式定义（`)` 后面不是 `{`）
     与返回函数指针的声明」。全仓扫描（`probe_p2.py` 的 A2 段）：`K&R`
     只作为**登记 token** 出现 1 次（就在 check_help_contract.py 里），
     `函数指针返回` **零次出现** ⇒ 这条承诺在仓库里**没有任何对手方**。

一句话：**承诺有人守着「在不在」，没人守着「还成不成立」。** 本门补的就是这一环。

判据（V1–V5，每条先说清「什么会红」）：
  V1 认领两向：`--help`「诚实的边界」里**每一条** bullet 都必须**恰好**被
     `REVERSE_CASES` 的一条认领，**或**在 `BOUNDARY_EXEMPT` 里登记
     （理由 ≥8 字符 + `where` 给「文件 + 逐字 token」）。
     两者都没有 ⇒ 红（边界没有对手方）；**又认领又豁免 ⇒ 也红**（歧义不许蒙对）。
     ⚠ R55 的第一版把准入条件写成「含 `不识别`/`不做`/`不跟踪`/`按兵不动`/
     `不保证`/`静默` 任一标记词」—— 于是 `* Mach-O：`（一句**状态声明**，
     一个标记词都没有）**整条不在网内**：它既没被认领也没被豁免，而棘轮只记
     「8 条边界 / 7 条否定式」，那个差值 **1** 谁也没去追（R55 §8 自己把它登记成
     C10-7）。R56 把准入条件**删掉**（口径改成「全部 bullet」），并给它补上豁免
     （对手方在 `check_binfmt_fixtures.py` 的 C8/C9）。标记词分类器 `is_negation`
     **保留但退居记录位**：它仍进 V5 棘轮，作用从「准入」变成「措辞漂移提醒」。
  V2 认领必须真实：认领的 head 必须是帮助正文某条 bullet 的**首行前缀**且唯一
     （两条 bullet 共用前缀 ⇒ 红）；`case["help_must"]` 的 token 必须**逐字**
     出现在它认领的那条 bullet 里；`case["docs"]` 声明的 (文件, token) 必须逐字存在
     —— 与 R51 的 B5「文档同源」是同一条纪律。
  V3 行为判据必须**两向**：每条 case 至少一条「必须出现」与一条「必须不出现」的
     期望。只有「不出现」的断言在「产品什么都不产出」时也成立 —— 那是**空断言**，
     它会在产品彻底坏掉时依然全绿。
  V4 陈旧：认领 / 豁免指向的 head 在帮助正文里找不到 ⇒ 红
     （与 `LAZY_CYCLES` / `BORROWED` 的「登记了却不存在 → 也红」同源）。
  V5 棘轮：bullet 总数、**被覆盖的** bullet 数、否定式 bullet 数、case 数四个
     下限**必须等于真实值** —— 删掉一整条边界、或删掉一整族判据而不改数字 ⇒ 红
     （覆盖不许静默缩水）。其中「被覆盖数 == bullet 数」是 R56 加的**独立证人**：
     它按**全部** bullet 数对手方（不经过任何准入条件），所以「某条边界失去
     对手方」这件事无论 V1 的循环怎么写都会红 —— 而那正是旧口径掩盖住的情形
     （旧口径下 Mach-O 既无对手方、又不参与判定，两条路都看不见它）。

为什么行为判据走**公开 CLI 子进程**而不是 `import matlabc`：
  ① 与 R54 立下的纪律一致（`tools/` 不 import 产品模块，宁可另写同义实现）；
  ② 公开 CLI 才是用户真正看到的那一面 —— 内部函数对了、CLI 组装错了，一样是缺陷。
  实测：一次运行 ≈0.5s（装置 `probe_p7.py`，五组共 ≈2.6s），够「秒级」。

一图看懂（承诺 ⇄ 判据 的两向）：

    --help「诚实的边界」              REVERSE_CASES / BOUNDARY_EXEMPT
    ┌──────────────────────────┐      ┌──────────────────────────────┐
    │ * 语言：…                 │◀ V1 ▶│ 语言： ⇒ 两个分支都跑 CLI      │
    │ * 前端实现：…             │◀ V1 ▶│ 前端实现：⇒ K&R/指针返回       │
    │ * 预处理：…               │◀ V1 ▶│ 预处理：⇒ #ifdef / #if 0       │
    │ * C++：…                  │◀ V1 ▶│ C++：⇒ 模板不得算作函数        │
    │ * 跨语言算子…「不做」…    │◀ V1 ▶│ ⇒ py_undefined_name 不产出     │
    │ * 动态库：…               │─ V2 ▶│ BOUNDARY_EXEMPT（where 逐字核对）│
    │ * GPU：…                  │─ V2 ▶│ BOUNDARY_EXEMPT（同上）         │
    │ * Mach-O：…（旧版漏掉）   │─ V2 ▶│ BOUNDARY_EXEMPT（R56 补）       │
    └──────────────────────────┘      └──────────────────────────────┘
              ▲                                    │
              └──────── V4 首行前缀唯一 ────────────┘

    R56 的关键差别：左侧**每一条**（不是「带否定词的每一条」）都必须落到右侧两个
    箱子之一。`* Mach-O：` 一个标记词都没有，旧版直接把它**跳过**了 —— 盲区不在
    「判据写错了」，而在「判据根本没看它」。

退出码：
    0 = 承诺 ⇄ 判据 全部对齐，且行为判据全绿
    1 = 有违规（未认领 / 歧义 / 空断言 / 陈旧 / 棘轮不符 / 行为不符）
    2 = 缺输入（找不到 matlabc.py / 工具脚本，或公开 CLI 跑不起来）

用法：
    python tools/check_boundary_reverse.py             # 0=对齐 1=违规 2=缺输入
    python tools/check_boundary_reverse.py --selftest   # 两向自证
"""
import argparse
import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族，
# 或本门独有的机制名）。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "V1–V5"

# ---------------------------------------------------------------------------
# 常量：全部是「事实的读数」，不是可调参数。
# 三个棘轮（V5）与真实值**必须相等** —— 改一条边界就要同步改一次这里，
# 这正是棘轮的作用（与 check_all.py 的 MIN_GUARDS 同源）。
# ---------------------------------------------------------------------------
BOUNDARY_SECTION = "诚实的边界"
NEGATION_MARKERS = ("不识别", "不做", "不跟踪", "按兵不动", "不保证", "静默")
MIN_REASON = 8
CLI_TIMEOUT = 300.0

# 真实读数（R56 重新定标；help 正文 8 条边界，其中 7 条带否定标记词，
# 8 条**全部**有对手方 —— 3 条豁免 + 5 条 case 认领）
EXPECTED_BOUNDARY_BULLETS = 8
EXPECTED_COVERED_BULLETS = 8
# 标记词分类器的读数。R56 起它**不参与 V1 准入**，只作为「措辞漂移提醒」：
# 若谁把这 7 条里的否定词改写掉，这个数字会变 ⇒ 红，逼人回头确认
# 「那条承诺还算不算否定式承诺」——而不是让口径在无人察觉处漂移。
EXPECTED_NEGATION_BULLETS = 7

SEP_CHARS = set("─-=~—")


# ---------------------------------------------------------------------------
# 行为判据的夹具（纯合成，秒级，不联网，不建 GUI）
#
# ⚠ 每条 case 的两向是**硬要求**（V3）：
#   * `expect_funcs` 里空列表 = 「必须不出现」；非空列表 = 「必须出现（且恰好这些）」；
#   * `stderr_must` = 「必须出现」；`stderr_must_not` = 「必须不出现」。
#   只有「必须不出现」的 case 会在产品整体坏掉时依然全绿，所以不许出现。
# ---------------------------------------------------------------------------
REVERSE_CASES = (
    # ----------------------------------------------------------------- 1/5
    {
        "id": "c-frontend-shapes",
        "claim": "前端实现：",
        "why": "帮助逐字承诺「仍不识别 K&R 老式定义（`)` 后面不是 `{`）与返回"
               "函数指针的声明」，而 R49 的成果是「跨行签名必须识别」——"
               "两头都要有人守着。R55 实测：`函数指针返回` 在全仓**零次出现**，"
               "`K&R` 只作为登记 token 出现 —— 这条承诺此前没有任何对手方。",
        "help_must": ("不识别", "K&R"),
        "runs": (
            {
                "args": ("--lang", "c"),
                "files": {
                    # 反向：三类「承诺不识别」的写法
                    "r55_knr.c":
                        "int r55_knr(a, b)\nint a;\nint b;\n"
                        "{\n  return a + b;\n}\n",
                    "r55_fnptr_ret.c":
                        "int (*r55_fnptr_ret(int a))(void)\n{\n  return 0;\n}\n",
                    "r55_macro_sig.c":
                        "#define SIG int r55_macro_sig(int a)\n"
                        "SIG { return a; }\n",
                    # 正对照：P1–P4 四形态必须识别（否则「不报」是废断言）
                    "r55_ok_p1.c":
                        "int r55_ok_p1(int a, int b) { return a + b; }\n",
                    "r55_ok_p2.c": "int r55_ok_p2(int a)\n{\n  return a;\n}\n",
                    "r55_ok_p3.c": "int\nr55_ok_p3(int a)\n{\n  return a;\n}\n",
                    "r55_ok_p4.c":
                        "void r55_ok_p4(int a,\n               int b)\n{\n}\n",
                    # 正对照②：**指针返回值**（`int *f(...)`）必须识别 ——
                    # 承诺说的「不识别返回函数指针」只指 `(*f(...))` 那种声明，
                    # 不是「凡带 `*` 的返回类型都不认」。这条防的是一刀切。
                    "r55_ok_ptr.c": "int *r55_ok_ptr(int a) { return 0; }\n",
                },
                "expect_funcs": {
                    "r55_knr.c": [],
                    "r55_fnptr_ret.c": [],
                    "r55_macro_sig.c": [],
                    "r55_ok_p1.c": ["r55_ok_p1"],
                    "r55_ok_p2.c": ["r55_ok_p2"],
                    "r55_ok_p3.c": ["r55_ok_p3"],
                    "r55_ok_p4.c": ["r55_ok_p4"],
                    "r55_ok_ptr.c": ["r55_ok_ptr"],
                },
                "expect_line": {
                    "r55_ok_p1.c": {"r55_ok_p1": 1},
                    "r55_ok_p2.c": {"r55_ok_p2": 1},
                    "r55_ok_p3.c": {"r55_ok_p3": 1},
                    "r55_ok_p4.c": {"r55_ok_p4": 1},
                    "r55_ok_ptr.c": {"r55_ok_ptr": 1},
                },
                "stderr_must_not": ("[warn]", "Traceback"),
            },
        ),
    },
    # ----------------------------------------------------------------- 2/5
    {
        "id": "preprocessing-boundary",
        "claim": "预处理：",
        "why": "帮助逐字承诺三件事：① 只做**字面量 `#if 0`** 感知；② `#if 0 … #else` "
               "的 else 分支是活代码；③ 行号保持不变；④ `#ifdef X` / "
               "`#if defined(X)` **按兵不动**。四条此前都只写在正文里，"
               "没有任何判据钉住 —— 本 case 把它们逐条变成期望。",
        "help_must": ("#if 0", "按兵不动"),
        "runs": (
            {
                "args": ("--lang", "c"),
                "files": {
                    # 按兵不动：不知道宏是否定义时**不许**把代码当死代码丢掉
                    "r55_ifdef_body.c":
                        "#ifdef NEVER_DEFINED\n"
                        "int r55_lost(int a) { return a; }\n#endif\n",
                    # 字面量 #if 0：死分支不分析；else 分支是活代码
                    "r55_if0_else.c":
                        "#if 0\nint r55_dead(int a) { return a; }\n#else\n"
                        "int r55_alive(int a) { return a; }\n#endif\n",
                    # 行号不变：`#if 0` 块之后的函数，行号必须仍是源文件真实行
                    "r55_if0_then_live.c":
                        "#if 0\nint r55_d1(int a) { return a; }\n#endif\n"
                        "int r55_live(int a) { return a; }\n",
                    # 已披露的近似：写在多行字符串里、恰好独占一行的 `#if 0`
                    # **会被误判成指令**（帮助原文：「所有「按行」工具的同一处近似」）。
                    # 这条是**冻结已知近似**，不是认可它：谁把它修好了，
                    # 这条期望会红，提醒同步帮助正文里的那句声明。
                    "r55_if0_in_str.c":
                        "const char *s =\n\"#if 0\\n\"\n"
                        "\"int r55_hidden(int a) { return a; }\\n\"\n"
                        "\"#endif\\n\";\n"
                        "int r55_real(int a) { return a; }\n",
                },
                "expect_funcs": {
                    "r55_ifdef_body.c": ["r55_lost"],
                    "r55_if0_else.c": ["r55_alive"],
                    "r55_if0_then_live.c": ["r55_live"],
                    "r55_if0_in_str.c": ["r55_real"],
                },
                "expect_line": {
                    "r55_ifdef_body.c": {"r55_lost": 2},
                    "r55_if0_else.c": {"r55_alive": 4},
                    "r55_if0_then_live.c": {"r55_live": 4},
                    "r55_if0_in_str.c": {"r55_real": 5},
                },
                "stderr_must_not": ("Traceback",),
            },
        ),
    },
    # ----------------------------------------------------------------- 3/5
    {
        "id": "unsupported-language-warn",
        "claim": "语言：",
        "why": "帮助原文写「扫到这些文件时它会打出 [warn]」——**无条件**；而实测只在"
               "「本次语言的源文件数为 0」时才 warn，混放时安静跳过。README 两侧"
               "写的却是窄口径 ⇒ 三处口径分叉。本 case 把**两个分支都钉住**，"
               "并要求帮助与两侧 README 都写清「混放时安静跳过」这件事。",
        "help_must": ("没有前端", "[warn]", "安静跳过"),
        "docs": (("README.md", "skipped silently"),
                 ("README_CN.md", "安静跳过")),
        "runs": (
            {
                # 分支 A：混放 ⇒ 被安静跳过（**必须不出现** warn，且本次语言照常分析）
                "args": ("--lang", "c"),
                "files": {
                    "ok.c": "int f(void) { return 0; }\n",
                    "thing.rs": "fn main() {}\n",
                },
                "expect_funcs": {"ok.c": ["f"]},
                "stderr_must_not": ("[warn]",),
            },
            {
                # 分支 B：本次语言的源文件数为 0 ⇒ 必须点名语言与文件
                "args": ("--lang", "c"),
                "files": {"thing.rs": "fn main() {}\n"},
                "stderr_must": ("[warn]", "Rust", "thing.rs"),
                "stderr_must_not": ("Traceback",),
            },
        ),
    },
    # ----------------------------------------------------------------- 4/5
    {
        "id": "cpp-language-alias-degrade",
        "claim": "C++：",
        "why": "帮助逐字承诺「`--lang cpp` 是 `--lang c` 的**别名**，按 C 子集解析。"
               "模板、类、命名空间、重载**不保证**识别 —— 这是已披露的降级，"
               "不是 bug」。判据：模板类的成员函数**不得**被当成 C 函数；"
               "同一文件里的纯 C 写法必须照常识别（正对照）。",
        "help_must": ("别名", "不保证"),
        "runs": (
            {
                "args": ("--lang", "cpp"),
                "files": {
                    "r55_mix.cpp":
                        "template <typename T>\nclass Box {\npublic:\n"
                        "  T get() const { return v; }\n  T v;\n};\n"
                        "int plain_cpp(int a, int b) { return a + b; }\n",
                },
                "expect_funcs": {"r55_mix.cpp": ["plain_cpp"]},
                "expect_line": {"r55_mix.cpp": {"plain_cpp": 7}},
                "stderr_must_not": ("Traceback",),
            },
        ),
    },
    # ----------------------------------------------------------------- 5/5
    {
        "id": "py-undefined-name-not-produced",
        "claim": "**跨语言算子有一个是「不做」的**：",
        "why": "帮助逐字承诺 `py_undefined_name` 是**「不做」**的（不是「漏了」），"
               "并点名 `pyflakes` / `ruff --select F821`。判据：给一段**真有未定义名**"
               "的 Python，产出里不得出现该算子 —— 否则那句「不做」就成了谎话；"
               "同时函数本身必须照常识别（正对照，防「什么都不产出」的空断言）。",
        "help_must": ("_UNIMPLEMENTED_KINDS", "pyflakes"),
        "runs": (
            {
                "args": ("--lang", "py"),
                "files": {
                    "r55_u.py":
                        "def f(x):\n    return totally_undefined_name(x)\n",
                },
                "expect_funcs": {"r55_u.py": ["f"]},
                "json_must_not": ("py_undefined_name",),
                "stderr_must_not": ("Traceback",),
            },
        ),
    },
)

# ---------------------------------------------------------------------------
# 豁免登记（证伪式，不是放行后门）：这三条边界的对手方**不在本门里**。
# 每条必须给出 ① 理由（≥8 字符） ② `where` = (相对路径, 逐字 token)，
# 且那个文件里必须**真的**有那个 token（V4 核对）—— 写错就红。
#
# ⚠ R55 里它叫 `NEGATION_EXEMPT`（只管否定式承诺）。R56 起 V1 的口径是
# 「全部 bullet」，这个名字就**说谎了**，故改名 `BOUNDARY_EXEMPT`。
# ---------------------------------------------------------------------------
BOUNDARY_EXEMPT = {
    "动态库：": {
        "why": "这条承诺的是「帮助与两侧 README 必须逐字点名三个运行期替代装置」——"
               "它本身就是一条**文本层**契约，对手方是 R51 的 B3/B5，"
               "本门再加一条行为判据只会重复，不会增加独立证据。",
        "where": ("tools/check_help_contract.py", "RUNTIME_BINDING_TOOLS"),
    },
    "GPU：": {
        "why": "「PTX 路径基本提不出 kernel 名、提不到时必须写明原因」的对手方"
               "是 check_binfmt_fixtures.py 的 C7（PTX `.entry <名>(` 必须后随"
               "左括号）与 C8（未验证必须传播进报告），它们用**合成夹具**"
               "直接喂 binfmt 解析器，比走 CLI 更贴近失效点。",
        "where": ("tools/check_binfmt_fixtures.py", ".entry <ident>("),
    },
    "Mach-O：": {
        "why": "这条是**状态声明**（「解析器已实现 + 有合成夹具，但无真实语料，"
               "所以报告里仍是 verified: NO」），措辞里一个否定标记词都没有 ——"
               "R55 的第一版正因为只看标记词而**整条跳过**了它（R55 §8 C10-7）。"
               "它的行为对手方不在本门：`check_binfmt_fixtures.py` 的 C8 用合成"
               "夹具直接断言「Mach-O 的未验证状态必须传播成 verified=False 并"
               "渲染进报告正文」，C9 断言合成夹具必须真解析出段/节与 fat 切片 ——"
               "那比走 CLI 更贴近失效点，本门再加一条只会重复。",
        "where": ("tools/check_binfmt_fixtures.py", "verified=False"),
    },
}

MIN_REVERSE_CASES = 5
MIN_NEGATION_CLAIMS = 5


# ---------------------------------------------------------------------------
# 读取与解析（纯静态，不 import 产品）
# ---------------------------------------------------------------------------
def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_text(root, rel):
    """按**字节**读再解码 —— `io.open(p, "r")` 是 universal-newlines，
    会静默把 CRLF 翻成 LF，读数就与仓库真实字节不一致了（R53 的教训）。"""
    with io.open(os.path.join(root, rel), "rb") as fh:
        return fh.read().decode("utf-8", "replace").replace("\r\n", "\n")


def module_docstring(src):
    """取模块 docstring 的**原文**（`clean=False`）—— 不做 dedent，
    免得行首缩进在解析前后变了样（bullet 是靠首行前缀认领的）。"""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    return ast.get_docstring(tree, clean=False)


def _is_sep_line(line):
    body = line.strip()
    if len(body) < 3:
        return False
    return all(ch in SEP_CHARS for ch in body)


def parse_boundary_bullets(doc):
    """切出帮助正文「诚实的边界」小节里的 bullets -> [(head, full_text)]。

    找不到小节返回 None（= 缺输入）。
    切法：定位标题行 → 越过其后第一条分隔线 → 收集到**下一条分隔线**为止；
    `  * xxx` 开头的是新 bullet，其余非空行是它的续行。

    ⚠ 本仓**独立**实现了同一个解析（R51 的那份在 check_help_contract.py 里）。
    两份不共享代码是**故意的**：共享会让两边一起漂移而没人发现；不共享则由
    `EXPECTED_BOUNDARY_BULLETS` 这条棘轮在任一份漂移时立刻变红。
    """
    if doc is None:
        return None
    lines = doc.split("\n")
    start = None
    for i, ln in enumerate(lines):
        if BOUNDARY_SECTION in ln:
            start = i
            break
    if start is None:
        return None
    j = start + 1
    while j < len(lines) and not _is_sep_line(lines[j]):
        j += 1
    k = j + 1
    while k < len(lines) and not _is_sep_line(lines[k]):
        k += 1
    out = []
    for ln in lines[j + 1:k]:
        if ln.lstrip().startswith("* "):
            out.append([ln.lstrip()[2:].rstrip(), []])
        elif out and ln.strip():
            out[-1][1].append(ln.rstrip())
    return [(h, "\n".join([h] + body)) for h, body in out]


def is_negation(text):
    """这条 bullet 是不是在承诺「某件事我不做」。"""
    return any(m in (text or "") for m in NEGATION_MARKERS)


# ---------------------------------------------------------------------------
# V1 / V2 / V4：认领两向 + 认领必须真实（纯函数，便于自证）
# ---------------------------------------------------------------------------
def _unique_prefix_owner(head, bullet_heads):
    """`head` 是哪些 bullet 的**首行前缀**。恰好 1 个才算认领成功。"""
    return [h for h in bullet_heads if h.startswith(head)]


def judge_registry(bullet_texts, bullet_heads, cases, exempts,
                   read_text_fn=None, root=None):
    """返回 [问题字符串...]。纯函数：`read_text_fn(root, rel)` 只在查 `docs`/`where`
    时被调用（自证时传 None 即可跳过文件核对）。"""
    probs = []

    claims = {}          # head -> [case_id, ...]
    for c in cases:
        claims.setdefault(c.get("claim"), []).append(c.get("id"))

    # ---- V2：认领必须唯一命中一条 bullet 的**首行前缀** ----
    for c in cases:
        head = c.get("claim")
        owners = _unique_prefix_owner(head, bullet_heads)
        if len(owners) == 0:
            probs.append("V2 case「%s」认领的 head「%s」在帮助正文里找不到"
                         "（陈旧认领 —— 登记了却不存在也要红）"
                         % (c.get("id"), head))
        elif len(owners) > 1:
            probs.append("V2 case「%s」的 head「%s」同时是 %d 条 bullet 的前缀"
                         "（歧义不许蒙对）：%r"
                         % (c.get("id"), head, len(owners), owners))
        else:
            full = None
            for h, t in zip(bullet_heads, bullet_texts):
                if h == owners[0]:
                    full = t
                    break
            for tok in (c.get("help_must") or ()):
                if tok not in (full or ""):
                    probs.append("V2 case「%s」声明了 token「%s」，"
                                 "但它认领的 bullet 里没有（逐字核对）"
                                 % (c.get("id"), tok))

    # ---- V2（续）：`case["docs"]` 的文档同源逐字核对 ----------------
    # 与 R51 的 B5 同一条纪律：帮助说了、README 没说 ⇒ 也是一条缝。
    # ⚠ 这条判据**第一版漏了**：docstring 里写了、代码里没有实现。
    # 在真实仓库上完全看不出来（README 两侧已被改对，有没有这条都绿）——
    # 是在**对照组**里发现门只报了 1 条违规（没报 README 两侧）才露出来的。
    # 所以它同时是一条自证样本（见 `_selftest` 的「坏样本 V2 docs」）。
    if read_text_fn is not None and root is not None:
        for c in cases:
            for item in (c.get("docs") or ()):
                if len(item) != 2:
                    probs.append("V2 case「%s」的 docs 项必须是 (文件, 逐字 token)"
                                 % (c.get("id"),))
                    continue
                rel, tok = item
                try:
                    dtxt = read_text_fn(root, rel)
                except (OSError, IOError):
                    probs.append("V2 case「%s」声明的 docs 文件读不到：%s"
                                 % (c.get("id"), rel))
                    continue
                if tok not in dtxt:
                    probs.append("V2 case「%s」声明的 docs token「%s」在 %s 里"
                                 "找不到（逐字核对 —— 与 R51 的 B5「文档同源」"
                                 "同一条纪律）" % (c.get("id"), tok, rel))

    for head, spec in sorted(exempts.items()):
        owners = _unique_prefix_owner(head, bullet_heads)
        if len(owners) == 0:
            probs.append("V4 豁免登记「%s」指向的 bullet 在帮助正文里找不到（陈旧）"
                         % head)
        elif len(owners) > 1:
            probs.append("V4 豁免登记「%s」的 head 歧义：同时是 %d 条 bullet 的前缀"
                         % (head, len(owners)))
        if len((spec.get("why") or "")) < MIN_REASON:
            probs.append("V4 豁免登记「%s」的理由只有 %d 个字符（下限 %d）——"
                         "一个字符的豁免等于静默取消覆盖"
                         % (head, len(spec.get("why") or ""), MIN_REASON))
        if read_text_fn is not None and root is not None:
            where = spec.get("where") or ()
            if len(where) != 2:
                probs.append("V4 豁免登记「%s」的 where 必须是 (文件, 逐字 token)" % head)
            else:
                rel, tok = where
                try:
                    txt = read_text_fn(root, rel)
                except (OSError, IOError):
                    probs.append("V4 豁免登记「%s」的 where 文件读不到：%s" % (head, rel))
                    txt = None
                if txt is not None and tok not in txt:
                    probs.append("V4 豁免登记「%s」的 where token 在 %s 里找不到"
                                 "（逐字核对）：%r" % (head, rel, tok))

    # ---- V1：**每一条** bullet 必须被**恰好一个**对手方认领或豁免 ----
    # ⚠ R56 删掉的那两行（`if not is_negation(full): continue`）就是 C10-7 的
    # 现场：它让「不带否定词的边界」完全不参与判定。删掉它之后，新增一条
    # 措辞任意的边界 bullet、却既不认领也不豁免 ⇒ 立刻红。
    for head, full in zip(bullet_heads, bullet_texts):
        owner_cases = [cid for (hl, ids) in claims.items()
                       for cid in ids if head.startswith(hl or "\x00")]
        exempted = [h for h in exempts if head.startswith(h)]
        if owner_cases and exempted:
            probs.append("V1 bullet「%s」**既被 case 认领又被豁免**（%r / %r）——"
                         "歧义：两种语义同时成立时读数不可信"
                         % (head, owner_cases, exempted))
        elif not owner_cases and not exempted:
            probs.append("V1 bullet「%s」是一条边界 bullet（措辞含不含否定词都"
                         "一样，R56 起不再按标记词网罗），却既没有反向判据、也没有"
                         "豁免登记 —— 边界没有对手方（R55 起因：`语言：` 曾无条件"
                         "承诺 warn，实测只在 0 源文件时才成立；R56 补的另一半："
                         "`Mach-O：` 因为不带否定词而**整条被跳过**）" % head)
        elif len(owner_cases) > 1:
            probs.append("V1 bullet「%s」被 %d 条 case 同时认领（%r）—— 认领必须唯一"
                         % (head, len(owner_cases), owner_cases))
    return probs


# ---------------------------------------------------------------------------
# V3 / V5：空断言判据 + 棘轮（纯函数）
# ---------------------------------------------------------------------------
def judge_case_shape(cases):
    probs = []
    seen = set()
    for c in cases:
        cid = c.get("id")
        if not cid:
            probs.append("V3 有 case 没有 id")
            continue
        if cid in seen:
            probs.append("V3 case id 重复：%s" % cid)
        seen.add(cid)
        if len((c.get("why") or "")) < MIN_REASON:
            probs.append("V3 case「%s」的理由只有 %d 个字符（下限 %d）——"
                         "说不出「什么会红」的判据不算判据"
                         % (cid, len(c.get("why") or ""), MIN_REASON))
        runs = c.get("runs") or ()
        if not runs:
            probs.append("V3 case「%s」一条 run 都没有 —— 那不是行为判据" % cid)
            continue
        pos = 0
        neg = 0
        for r in runs:
            for _rel, names in (r.get("expect_funcs") or {}).items():
                if names:
                    pos += 1
                else:
                    neg += 1
            if r.get("expect_line"):
                pos += 1
            pos += len(r.get("stderr_must") or ())
            pos += len(r.get("stdout_must") or ())
            pos += len(r.get("json_must") or ())
            neg += len(r.get("stderr_must_not") or ())
            neg += len(r.get("json_must_not") or ())
        if pos < 1:
            probs.append("V3 case「%s」**没有任何「必须出现」的期望** —— "
                         "在「产品什么都不产出」时它也全绿，是空断言" % cid)
        if neg < 1:
            probs.append("V3 case「%s」**没有任何「必须不出现」的期望** —— "
                         "那是正对照，不是边界判据" % cid)
    return probs


def judge_ratchet(n_bullets, n_negation, n_covered, n_cases):
    probs = []
    if n_bullets != EXPECTED_BOUNDARY_BULLETS:
        probs.append("V5 帮助正文「诚实的边界」有 %d 条 bullet，棘轮记的是 %d —— "
                     "要么你真的增删了一条边界（同步常量），要么解析器漂移了"
                     % (n_bullets, EXPECTED_BOUNDARY_BULLETS))
    if n_covered != EXPECTED_COVERED_BULLETS:
        probs.append("V5 有对手方的 bullet 是 %d 条，棘轮记的是 %d —— "
                     "覆盖数不许静默缩水。这个数字按**全部** bullet 数"
                     "（不经过 V1 的任何准入条件），所以它是「每一条边界都要有"
                     "对手方」的独立证人：旧口径下 `Mach-O：` 失去对手方时，"
                     "V1 与棘轮**两条路都看不见它**（R56 补的就是这个）"
                     % (n_covered, EXPECTED_COVERED_BULLETS))
    if n_negation != EXPECTED_NEGATION_BULLETS:
        probs.append("V5 否定式承诺有 %d 条，棘轮记的是 %d —— 这个数字 R56 起"
                     "不参与 V1 准入，只作措辞漂移提醒；改了措辞就必须来改它"
                     % (n_negation, EXPECTED_NEGATION_BULLETS))
    if n_cases != MIN_REVERSE_CASES:
        probs.append("V5 反向判据有 %d 条 case，棘轮记的是 %d —— "
                     "删掉一整族判据而不改数字必须红" % (n_cases, MIN_REVERSE_CASES))
    n_claims = len([1 for c in REVERSE_CASES
                    if c.get("claim") not in BOUNDARY_EXEMPT])
    if n_claims < MIN_NEGATION_CLAIMS:
        probs.append("V5 认领了 %d 条否定式承诺，下限是 %d"
                     % (n_claims, MIN_NEGATION_CLAIMS))
    return probs


# ---------------------------------------------------------------------------
# 行为判据：走公开 CLI 子进程
# ---------------------------------------------------------------------------
def run_cli(root, python_exe, files, args, tmpdir):
    """把夹具写成文件，跑一次公开 CLI，返回 (rc, stdout, stderr, json_text)。

    `stdin=DEVNULL` 与 `timeout=` 不是洁癖：本仓 check_subprocess_hygiene.py
    的 S1/S2 就是判这个的（继承 stdin 会让 stdio server 永久阻塞）。
    """
    for rel, src in files.items():
        p = os.path.join(tmpdir, rel)
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(src)
    out_json = os.path.join(tmpdir, "r55_out.json")
    argv = [python_exe, "matlabc.py", tmpdir] + list(args) + [
        "--json", out_json, "--max-warnings", "999"]
    p = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=CLI_TIMEOUT)
    so = p.stdout.decode("utf-8", "replace")
    se = p.stderr.decode("utf-8", "replace")
    jt = ""
    if os.path.isfile(out_json):
        with io.open(out_json, "rb") as fh:
            jt = fh.read().decode("utf-8", "replace")
    return p.returncode, so, se, jt


def funcs_by_rel(json_text):
    """从 JSON 里取 {相对文件基名: [(名字, 行号), ...]}。

    ⚠ 口径只看**基名**：临时目录名每次不同，用绝对路径当键会自己制造噪声。
    夹具的文件名因此必须是**全仓唯一**的前缀（本门统一用 `r55_` / `ok.c`）。
    """
    try:
        payload = json.loads(json_text)
    except ValueError:
        return None
    per = {}
    for f in (payload.get("files") or []):
        if not isinstance(f, dict):
            continue
        rel = str(f.get("rel") or f.get("path") or "?")
        nm = os.path.basename(rel.replace("\\", "/"))
        per[nm] = [(fn.get("name"), fn.get("line"))
                   for fn in (f.get("functions") or []) if isinstance(fn, dict)]
    return per


def check_run(root, python_exe, cid, run, tmpdir):
    """跑一条 run 并把期望逐项核对；返回 [问题...]。"""
    probs = []
    try:
        rc, so, se, jt = run_cli(root, python_exe, run.get("files") or {},
                                 run.get("args") or (), tmpdir)
    except (OSError, subprocess.SubprocessError) as e:
        return ["V6 case「%s」公开 CLI 跑不起来：%s（缺输入）" % (cid, e)]
    except Exception as e:                     # noqa: BLE001 —— 超时也算缺输入
        return ["V6 case「%s」公开 CLI 异常：%r（缺输入）" % (cid, e)]

    allow_rc = run.get("expect_rc") or (0,)
    if rc not in allow_rc:
        probs.append("V6 case「%s」rc=%s，期望 %r；stderr 尾部：%s"
                     % (cid, rc, allow_rc, se.strip()[-300:]))

    per = funcs_by_rel(jt)
    if per is None:
        probs.append("V6 case「%s」没有产出可解析的 JSON（--json 是判据的载体）" % cid)
        per = {}

    for rel, want in sorted((run.get("expect_funcs") or {}).items()):
        nm = os.path.basename(rel)
        got_names = [x[0] for x in per.get(nm, [])]
        if got_names != list(want):
            probs.append("V6 case「%s」%s 的函数表实测 %r，期望 %r —— "
                         "「不出现」的期望靠这里作证，写错就等于判据失效"
                         % (cid, rel, got_names, list(want)))

    for rel, lines in sorted((run.get("expect_line") or {}).items()):
        nm = os.path.basename(rel)
        got = dict(per.get(nm, []))
        for fname, ln in sorted(lines.items()):
            if got.get(fname) != ln:
                probs.append("V6 case「%s」%s 里 %s 的行号实测 %r，期望 %d "
                             "（行号是承诺的一部分：「行号保持不变」）"
                             % (cid, rel, fname, got.get(fname), ln))

    for tok in (run.get("stderr_must") or ()):
        if tok not in se:
            probs.append("V6 case「%s」stderr 里没有逐字出现 %r（实测：%r）"
                         % (cid, tok, se.strip()[-300:]))
    for tok in (run.get("stderr_must_not") or ()):
        if tok in se:
            probs.append("V6 case「%s」stderr 里**不该**出现 %r（实测：%r）"
                         % (cid, tok, se.strip()[-300:]))
    for tok in (run.get("stdout_must") or ()):
        if tok not in so:
            probs.append("V6 case「%s」stdout 里没有逐字出现 %r" % (cid, tok))
    for tok in (run.get("json_must") or ()):
        if tok not in jt:
            probs.append("V6 case「%s」JSON 里没有逐字出现 %r" % (cid, tok))
    for tok in (run.get("json_must_not") or ()):
        if tok in jt:
            probs.append("V6 case「%s」JSON 里**不该**出现 %r —— "
                         "「不做」的算子若真产出了，这句承诺就是谎话" % (cid, tok))
    return probs


def check_all_cases(root, python_exe):
    probs = []
    for c in REVERSE_CASES:
        tmp = tempfile.mkdtemp(prefix="r55gate_")
        try:
            for i, run in enumerate(c.get("runs") or ()):
                sub = os.path.join(tmp, "run%d" % i)
                os.makedirs(sub)
                probs += check_run(root, python_exe, c.get("id"), run, sub)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return probs


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


def scan(root):
    """读帮助正文与两侧 README。返回 dict；缺文件时为 None。"""
    help_path = os.path.join(root, "matlabc.py")
    if not os.path.exists(help_path):
        return None
    doc = module_docstring(read_text(root, "matlabc.py"))
    bullets = parse_boundary_bullets(doc)
    if bullets is None:
        return {"bullets": None, "heads": [], "texts": []}
    return {"bullets": bullets,
            "heads": [h for h, _t in bullets],
            "texts": [t for _h, t in bullets]}


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
    sc = scan(root)
    if sc is None:
        print("check_boundary_reverse: 找不到 matlabc.py（缺输入 → 红）：%s" % root)
        return 2
    if sc["bullets"] is None:
        print("check_boundary_reverse: 帮助正文里找不到「%s」小节（缺输入 → 红）"
              % BOUNDARY_SECTION)
        return 2

    heads, texts = sc["heads"], sc["texts"]
    claim_heads = [c.get("claim") or "\x00" for c in REVERSE_CASES]
    covered = len([1 for h in heads
                   if any(h.startswith(k) for k in claim_heads)
                   or any(h.startswith(k) for k in BOUNDARY_EXEMPT)])
    probs = []
    probs += judge_ratchet(len(heads), len([1 for t in texts if is_negation(t)]),
                           covered, len(REVERSE_CASES))
    probs += judge_case_shape(REVERSE_CASES)
    probs += judge_registry(texts, heads, REVERSE_CASES, BOUNDARY_EXEMPT,
                            read_text_fn=read_text, root=root)
    probs += check_all_cases(root, sys.executable)

    if probs:
        for p in probs:
            print("check_boundary_reverse: " + p)
        print("check_boundary_reverse: %d 项违规" % len(probs))
        return 1

    n_neg = len([1 for t in texts if is_negation(t)])
    print("check_boundary_reverse: OK（帮助正文 %d 条边界，其中带否定词 %d 条；"
          "**全部 %d 条**都有对手方：%d 条 case 认领 + %d 条豁免登记（where 逐字"
          "核对）；行为判据 %d 组公开 CLI 全绿；%s 全绿）"
          % (len(heads), n_neg, covered,
             len([1 for c in REVERSE_CASES
                  if c["claim"] not in BOUNDARY_EXEMPT]),
             len(BOUNDARY_EXEMPT),
             sum(len(c.get("runs") or ()) for c in REVERSE_CASES),
             ROW_SIGNATURE))
    return 0


# ---------------------------------------------------------------------------
# 两向自证：坏样本必须红在**指定**判据上，好样本必须全绿
# ---------------------------------------------------------------------------
_DOC_GOOD = (
    "────────────────\n"
    "诚实的边界\n"
    "────────────────\n"
    "\n"
    "  * 甲：这里**不识别**某物，请用 `other`。\n"
    "  * 乙：这里**按兵不动**。\n"
    "  * 丙：这里只有一条普通说明，没有任何否定词。\n"
    "\n"
)

_DOC_MISSING_SECTION = "没有这一节\n"


def _selftest():
    """`bad` 数的是**本装置自己的失误**：坏样本没红、或红在了别的判据上。"""
    bad = [0]
    good = [0]

    def red(tag, fn, want):
        probs = fn()
        hit = [p for p in probs if p.startswith(want)]
        if hit:
            good[0] += 1
        else:
            bad[0] += 1
            print("  [selftest] %s 未被 %s 抓到（实得 %r）" % (tag, want, probs))

    def green(tag, fn):
        probs = fn()
        if not probs:
            good[0] += 1
        else:
            bad[0] += 1
            print("  [selftest] %s 被误伤：%r" % (tag, probs))

    GOOD_CASES = (
        {"id": "c1", "claim": "甲：", "why": "这条理由足够长，说得清什么会红",
         "runs": ({"expect_funcs": {"a.c": ["f"]},
                   "stderr_must_not": ("[warn]",)},)},
        {"id": "c2", "claim": "乙：", "why": "这条理由同样足够长，说得清会红什么",
         "runs": ({"expect_funcs": {"b.c": []},
                   "stderr_must": ("[warn]",)},)},
    )

    def _judge(doc, cases=None, exempts=None, reader=None):
        b = parse_boundary_bullets(doc)
        if b is None:
            return ["（解析不到小节）"]
        heads = [h for h, _t in b]
        texts = [t for _h, t in b]
        return judge_registry(texts, heads,
                              cases if cases is not None else GOOD_CASES,
                              exempts if exempts is not None else {},
                              read_text_fn=reader, root=("R" if reader else None))

    # ---- 好样本：三条 bullet **每一条**都落到两个箱子之一 ----
    # 丙：**刻意不带任何否定标记词**、也刻意用豁免登记（而不是 case）——
    # 这条好样本本身就是 R56 那条新口径的证人：旧版（只认标记词）下它也会绿，
    # 但绿的理由是「丙根本不在网内」；新版下它绿的理由是「丙被豁免了」。
    # ⚠ where 必须指向 `_fake_docs` 里真有的文件与 token —— 挂上 reader 之后
    # 它会被逐字核对；占位串 `("x", "y")` 当场 KeyError（补丁 2 的自伤）。
    _EX_C = {"丙：": {"why": "这条理由足够长，说明丙的对手方不在本门",
                      "where": ("README.md", "no such phrase")}}
    green("好样本：三条 bullet 都有对手方",
          lambda: _judge(_DOC_GOOD, exempts=_EX_C))

    # ---- 坏样本 V1：一条 bullet 没人认领（否定式） ----
    red("坏样本 V1 未认领", lambda: _judge(_DOC_GOOD, cases=(GOOD_CASES[0],),
                                          exempts=_EX_C),
        "V1")

    # ---- 坏样本 V1（R56 新增）：**无标记词**的 bullet 没人认领 -------------
    # 这条就是 C10-7 的反例：旧版会**静默放行**（它是 R56 修的那个盲区）。
    red("坏样本 V1 无标记词的 bullet 被漏掉",
        lambda: _judge(_DOC_GOOD, cases=(GOOD_CASES[0], GOOD_CASES[1])),
        "V1")

    # ---- 坏样本 V1：同时被认领又被豁免（歧义） ----
    red("坏样本 V1 歧义（又认领又豁免）",
        lambda: _judge(_DOC_GOOD, exempts={
            "甲：": {"why": "这条理由足够长，但它与 case 同时存在",
                    "where": ("x", "y")}}),
        "V1")

    # ---- 坏样本 V2：认领的 head 在帮助正文里不存在（陈旧） ----
    red("坏样本 V2 陈旧认领",
        lambda: _judge(_DOC_GOOD,
                       cases=(GOOD_CASES[0], GOOD_CASES[1],
                              {"id": "c9", "claim": "丁：",
                               "why": "这条理由足够长但 head 不存在",
                               "runs": ({"expect_funcs": {"z": ["q"]}},)})),
        "V2")

    # ---- 坏样本 V2：help_must 的 token 不在被认领的 bullet 里 ----
    red("坏样本 V2 help_must 逐字不符",
        lambda: _judge(_DOC_GOOD, cases=(
            GOOD_CASES[1],
            {"id": "c1", "claim": "甲：", "why": "这条理由足够长但 token 写错了",
             "help_must": ("根本不存在的词",),
             "runs": ({"expect_funcs": {"a": ["f"]}},)})),
        "V2")

    # ---- 坏样本 V2：`docs` 声明的 token 在文档里找不到（文档同源）----
    # 这条是**补的**：门的 docstring 早就承诺了它，代码却漏了（见 §自伤）。
    _fake_docs = {"README.md": "no such phrase here\n"}

    def _fake_read(_root, rel):
        return _fake_docs[rel]

    red("坏样本 V2 docs 逐字不符",
        lambda: _judge(_DOC_GOOD, cases=(
            GOOD_CASES[1],
            {"id": "c1", "claim": "甲：",
             "why": "这条理由足够长但 docs 里的 token 写错了",
             "docs": (("README.md", "skipped silently"),),
             "runs": ({"expect_funcs": {"a": ["f"]}},)}),
                       reader=_fake_read),
        "V2")
    green("好样本 V2 docs 逐字相符",
          lambda: _judge(_DOC_GOOD, cases=(
              GOOD_CASES[1],
              {"id": "c1", "claim": "甲：",
               "why": "这条理由足够长且 docs 里的 token 真的存在",
               "docs": (("README.md", "no such phrase"),),
               "runs": ({"expect_funcs": {"a": ["f"]}},)}),
                        exempts=_EX_C, reader=_fake_read))

    # ---- 坏样本 V4：豁免指向不存在的 bullet ----
    red("坏样本 V4 陈旧豁免",
        lambda: _judge(_DOC_GOOD,
                       exempts={"戊：": {"why": "这条理由足够长但指向不存在",
                                        "where": ("x", "y")}}),
        "V4")

    # ---- 坏样本 V4：豁免理由过短（不足 8 字符 ⇒ 不生效） ----
    red("坏样本 V4 豁免理由过短",
        lambda: _judge(_DOC_GOOD, cases=(GOOD_CASES[0], GOOD_CASES[1]),
                       exempts={"甲：": {"why": "短", "where": ("x", "y")}}),
        "V4")

    # ---- 缺输入：解析不到「诚实的边界」小节 ----
    red("坏样本：解析不到小节",
        lambda: ["（解析不到小节）"] if parse_boundary_bullets(
            _DOC_MISSING_SECTION) is None else [],
        "（解析不到小节）")

    # ---- V3：空断言（只有「必须不出现」）必须红 ----
    red("坏样本 V3 空断言（只否不正）",
        lambda: judge_case_shape((
            {"id": "c1", "claim": "甲：", "why": "这条理由足够长但只有否定期望",
             "runs": ({"expect_funcs": {"a.c": []}},)},)),
        "V3")
    # ---- V3：只有正向、没有反向 ⇒ 那是正对照，不是边界判据 ----
    red("坏样本 V3 只有正对照",
        lambda: judge_case_shape((
            {"id": "c1", "claim": "甲：", "why": "这条理由足够长但只有正向期望",
             "runs": ({"expect_funcs": {"a.c": ["f"]}},)},)),
        "V3")
    # ---- V3：理由过短 ----
    red("坏样本 V3 理由过短",
        lambda: judge_case_shape((
            {"id": "c1", "claim": "甲：", "why": "短",
             "runs": ({"expect_funcs": {"a.c": ["f"]},
                       "stderr_must_not": ("x",)},)},)),
        "V3")
    green("好样本 V3 两向齐全",
          lambda: judge_case_shape(GOOD_CASES))

    # ---- V5：三个棘轮各自要能红 ----
    red("坏样本 V5 bullet 数不符",
        lambda: judge_ratchet(EXPECTED_BOUNDARY_BULLETS - 1,
                              EXPECTED_NEGATION_BULLETS, EXPECTED_COVERED_BULLETS,
                              MIN_REVERSE_CASES), "V5")
    red("坏样本 V5 覆盖数缩水（= 某条 bullet 失去对手方）",
        lambda: judge_ratchet(EXPECTED_BOUNDARY_BULLETS,
                              EXPECTED_NEGATION_BULLETS, EXPECTED_COVERED_BULLETS - 1,
                              MIN_REVERSE_CASES), "V5")
    red("坏样本 V5 否定式 bullet 数不符",
        lambda: judge_ratchet(EXPECTED_BOUNDARY_BULLETS,
                              EXPECTED_NEGATION_BULLETS - 1, EXPECTED_COVERED_BULLETS,
                              MIN_REVERSE_CASES), "V5")
    red("坏样本 V5 case 数不符",
        lambda: judge_ratchet(EXPECTED_BOUNDARY_BULLETS,
                              EXPECTED_NEGATION_BULLETS, EXPECTED_COVERED_BULLETS,
                              MIN_REVERSE_CASES - 1), "V5")
    green("好样本 V5 棘轮相等",
          lambda: judge_ratchet(EXPECTED_BOUNDARY_BULLETS,
                                EXPECTED_NEGATION_BULLETS, EXPECTED_COVERED_BULLETS,
                                MIN_REVERSE_CASES))

    # ---- 行为层：JSON 解析失败 / 期望不符要红 ----
    red("坏样本 V6 JSON 不可解析",
        lambda: ["V6 x"] if funcs_by_rel("not json") is None else [], "V6")
    red("坏样本 V6 期望不符",
        lambda: (["V6 x"] if [x[0] for x in (funcs_by_rel(
            '{"files":[{"rel":"a.c","functions":[{"name":"g","line":1}]}]}'
        ) or {}).get("a.c", [])] != ["f"] else []), "V6")
    green("好样本 V6 期望相符",
          lambda: [] if [x[0] for x in (funcs_by_rel(
              '{"files":[{"rel":"a.c","functions":[{"name":"f","line":1}]}]}'
          ) or {}).get("a.c", [])] == ["f"] else ["V6 x"])

    return bad[0], good[0]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
