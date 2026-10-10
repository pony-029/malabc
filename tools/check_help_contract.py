# -*- coding: utf-8 -*-
"""登记制护栏：入口脚本的「退出码契约」必须在**代码与帮助正文之间双向一致**。

动因（为什么退出码值得一道门）：
    本仓几乎所有自动化都靠退出码判断成败 —— CI 用 `--gate` 的非零码失败构建、
    `matlabc_flow --review-gate` 用 3 表示「已验证但未落地」、护栏用 2 表示
    「缺输入」。但退出码有一个隐蔽的退化方式：
        代码新增了一个码，帮助里没说  → 用户不知道这个码意味着什么，只能猜；
        帮助里写了一个码，代码不给   → 用户写了判分支，永远走不到（假契约）。
    两种都不会报错，只会在别人的 CI 里静静地错。

判据（三条，全部机械可查）：
    R1 「登记有依据」：EXIT_CONTRACT 里登记的每个码，必须在证据文件里以
        `return N` / `sys.exit(N)` / `exit_code = N` / `result["exit_code"] = N`
        之一真实出现。确实由解释器给出的（如「未捕获异常 → 1」）必须登记在
        NO_EVIDENCE 并写明原因 —— 这是**证伪式登记**，不是放行后门。
        **反向也要抓**：脚本里出现 `sys.exit(<字面量>)` 却没登记 → 红。
    R2 「帮助说全且不多说」：脚本模块 docstring 的「退出码」段解析出的码集合
        必须**等于**登记表的键集合。少写 → 红；多写 → 红。
    R3 「帮助有骨架」（棘轮）：docstring 必须含
        ① 用法/示例（且至少一条 `python <本脚本>` 的可复制命令行）
        ② 图示（≥3 行、每行 ≥3 个框线字符）
        ③ 「退出码」段且非空

  关于 R3 的诚实声明：它是**完整性棘轮**，不是质量判据。它只能防「帮助被无声
  缩水回六行」，**不能**保证写得好 —— 一份垃圾但含图、含示例、含退出码的帮助
  照样能过 R3。别把它当成「帮助质量已验证」。

    R4 「示例是契约，不是装饰」（R33 新增）：R3 只证明「文中出现过 python <脚本>」，
        这仍然允许一句**根本跑不通**的示例。R4 把至少一条示例变成**真的跑一遍**：
          a) 对每个入口脚本，在 RUNNABLE 里登记一条**无副作用**命令（只允许
             --help / --version / --selftest 这类不改盘的开关），真跑它，断言 rc==0；
             按设计「无输出」的（stdio MCP server）额外断言 bytes==0 —— 与
             check_doc_flags 的 NO_HELP_SCRIPTS 用同一条证伪式登记纪律。
          b) 该命令必须**原样出现在文档里**（`python <脚本> <命令>`），否则用户抄不到。
        为什么只跑「无副作用子集」：示例里还有 `matlabc.py ./proj --browse site/`
        这类会**真的写盘**的命令 —— 让护栏去跑它们，等于让检查本身产生副作用。
        宁可不跑，也不能跑错。

R5 「帮助体积棘轮」（**三臂**，R64/C13-9 重构）：`--help` 受
    ① **绝对界**（读得完 / 没缩水）
    ② **漂移带** `±HELP_DRIFT_BYTES`（对已批准快照，分辨率 **64 B**）
    ③ **规范形逐字节相等**（容差 **0**，分辨率 **1 字节**）
    三臂取严；合法增长要在同一提交里更新快照，不许放宽 `HELP_DRIFT_BYTES`。
    测量口径**钉死**（见 `HELP_MEASURE_COLUMNS`）：读数不再随调用方的终端宽度变。

    R5c（R64/C13-9）「可复现」：为什么必须有第三臂 —— 实测发现 `--help` 的字节数
    随两件**与被测对象无关**的事变（解释器 3.10/3.13 差 30 B；`COLUMNS=200`
    差 −4654 B），而旧容差 `max(30%×快照, 512)` 对 matlabc.py 是 **15,135 B**
    ⇒ 30 B 的漂移**整个被吞掉**。第三臂把 `--help` 折成**版本 + 宽度双无关**的
    规范形（`_canon_help`）再做**逐字节相等**断言 ⇒ 分辨率 15,135 B → **1 B**。
    诚实声明：规范形**看不见布局**（缩进、折行位置），布局由臂 ①② 兜。

R51（C''''2）「诚实的边界」逐字契约：`--help` 的「诚实的边界」小节里每一条
    bullet 必须被登记表 `BOUNDARY_CLAIMS` **恰好一条**认领（未登记 → 红；
    指向已不存在的边界 → 红；前缀不唯一 → 红），且登记项声明的 token 必须
    **逐字**出现在它认领的 bullet 里；带 `docs` 的登记还要求 `docs_must` 在
    README 两侧逐字出现（防「帮助说了、README 没说」这条新缝）。

两向自证：R1/R2/R3/R4/R5/R5c/R51 各配独立坏样本（必须红）与好样本（必须过），
并对真实仓库做一次整体核对。

退出码：
    0 = 全部一致
    1 = 发现不一致（R1/R2/R3 任一红）
    2 = 缺输入（入口脚本缺失 / 解析不到 docstring → 红）

用法：
    python tools/check_help_contract.py             # 0=一致 1=不一致 2=缺输入
    python tools/check_help_contract.py --selftest   # 两向自证
"""
import argparse
import ast
import io
import os
import re
import sys

# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族，
# 或本门独有的机制名）。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "B0–B5"

# ---------------------------------------------------------------------------
# 退出码契约的唯一事实源。每个码都要在 evidence 指的文件里有真实依据
# （见 R1），且必须与 docstring 的「退出码」段逐码一致（见 R2）。
# ---------------------------------------------------------------------------
CONTRACT = {
    "matlabc.py": {
        "codes": {
            0: "正常完成",
            1: "质量门禁未通过（--gate / --max-warnings / 契约问题 / 往返校验差异）",
            2: "参数或配置文件错误；或影响门禁失败（--operator-impact-gate-fail）",
        },
        "evidence": ("matlabc.py",),
    },
    "matlabc_flow.py": {
        "codes": {
            0: "正常完成（含「只产出补丁、未落盘」）",
            1: "步骤执行中出错",
            2: "未通过自证 / 前置条件不满足（已回退，产出人工检查点）",
            3: "已通过自证但 --review-gate 要求人工复核（未落地）",
        },
        "evidence": ("matlabc_flow.py", "agent_loop.py"),
    },
    "matlabc_ask.py": {
        "codes": {
            0: "正常（离线回显提示词也算成功）",
            1: "载入或生成报告失败",
            2: "参数不全（既没给 --dir 也没给 --json）",
        },
        "evidence": ("matlabc_ask.py",),
    },
    "matlabc_mcp.py": {
        "codes": {
            0: "从 stdin 收到 EOF，正常收工退出",
            1: "未捕获异常（由解释器给出）",
        },
        "evidence": (),
    },
    "gui.py": {
        "codes": {
            0: "正常（关窗 / --selftest 通过 / --help 打印完）",
            1: "启动期异常（极少数环境缺 tkinter；stderr 会给原因）",
        },
        "evidence": ("gui.py",),
    },
    "agent_loop.py": {
        "codes": {
            0: "自证通过（tier 0 完全干净 / tier 1 仍有残留但安全降级）",
            2: "未通过自证 → 已回退，产出人工检查点",
            3: "已通过自证但要求人工复核，未落地",
        },
        "evidence": ("agent_loop.py",),
        # agent_loop.py 是**库**（没有 CLI），示例只能挂在它的命令行入口上。
        # 这里显式声明「示例经由哪个脚本」，而不是给它开后门免检 ——
        # 免检会让 R3 在这一个文件上悄悄失效。
        "example_via": "matlabc_flow.py",
    },
}

# 确实由**解释器**给出的码（源码里找不到 return/sys.exit 依据），必须写明原因。
# 这不是放行后门：只有这里登记过的 (脚本, 码) 才允许缺依据。
NO_EVIDENCE = {
    ("matlabc_mcp.py", 0): "main() 正常返回到模块尾部，解释器以 0 退出（无显式 sys.exit）",
    ("matlabc_mcp.py", 1): "未捕获异常由解释器以 1 退出；本文件不捕获顶层异常",
    ("matlabc_ask.py", 0): "成功路径 return ai_cli.main(cli_argv)，0 由 ai_cli 给出",
    ("gui.py", 1): "tkinter 缺失等启动期异常未被捕获，由解释器以 1 退出；"
                   "main() 里所有 return 都是 0",
}

ENTRY_SCRIPTS = tuple(sorted(CONTRACT))

# ---------------------------------------------------------------------------
# R33（C'7）：把退出码契约推广到护栏脚本本身。
# 护栏被 CI 直接调用，它们的退出码同样是接口 —— 「0=干净 1=有违规 2=缺输入」
# 这句 prose 一旦与源码脱节，CI 就会把失败当成功放过去。
#
# 与入口脚本的差别（**故意不同，不是漏做**）：
#   * 护栏只施加 R1（登记有依据，含反向 + 陈旧检测）与 R2（帮助说全且不多说）；
#   * **不**做 R3/R4 —— R4 会真的去跑 `--selftest`，而 check_all 本来就会逐个跑，
#     在 check_help_contract 里再跑一遍是纯浪费（9 道 × 数秒）。
#     护栏的「示例能跑」由 check_all.py 的聚合运行来证明，职责不重复。
# ---------------------------------------------------------------------------
GUARD_CONTRACT = {
    "tools/check_all.py": {
        0: "全部护栏通过",
        1: "有护栏失败，或护栏缺自证",
        2: "找不到护栏（缺输入）",
    },
    "tools/check_baseline.py": {
        0: "通过（默认模式：前置条件 + 门自身两向自证；--full：无回归）",
        1: "门自身两向自证失败，或 --full 发现回归",
        2: "缺输入 / 环境不可用（非 git 仓库 / 无 git / 测试集不在）",
    },
    "tools/check_binfmt_fixtures.py": {
        0: "契约 C1–C6 全部通过",
        1: "发现违规",
        2: "缺输入 / 环境不可用（无法导入 binfmt）",
    },
    "tools/check_doc_flags.py": {
        0: "文档/帮助正文的开关全部真实存在",
        1: "有文档宣传了不存在的开关",
        2: "缺输入",
    },
    "tools/check_flow_diagrams.py": {
        0: "图的引用 / 文件 / 候选声明 / 交互产物 / FLOW_INDEX 索引 / SVG 自身形态，六条来源两两对齐且双向（D1–D12）",
        1: "发现不对齐（引用悬空 / 孤儿产物 / 中英缺对 / 语言串台 / 形态不自足 / 骨架分叉 / 索引过期 / 尺寸不自洽 / 字体漂移 / 语言没落到文本层）",
        2: "缺输入（缺文档 / 缺 flow/diagrams/ / 一个候选都找不到）",
    },
    "tools/check_help_contract.py": {
        0: "全部一致",
        1: "发现不一致（R1/R1b/R2/R3/R4/R5/R5c/R51 任一红）",
        2: "缺输入（入口脚本缺失 / 解析不到 docstring）",
    },
    "tools/check_import_graph.py": {
        0: "模块级 import 无环、登记两向一致、文档标记对称、借用清单两向一致（G1–G7）",
        1: "有违规（未登记环 / 陈旧登记 / 未登记动态 import / 未登记借用 / 陈旧借用登记 / 悬空借用 / 理由过短 / 文档标记不对称）",
        2: "缺输入（扫不到 .py / 缺 CONTRIBUTING.md）",
    },
    "tools/check_ir_attribution.py": {
        0: "唯一判定点 + 归因来源 + 语言登记 + 扩展名事实源四方一致（八条静态 + 十条纯函数判据）",
        1: "有违规（写点未登记/形状漂移/判定点出包/接线缺失/归因自算/谓词未登记）",
        2: "缺输入（找不到 frontends/ir.py 或 matlabc.py，或导不进 frontends 包）",
    },
    "tools/check_operator_impl.py": {
        0: "无幻影算子",
        1: "有幻影算子 / 缺原因",
        2: "缺输入（源文件或元表找不到）",
    },
    "tools/check_patch_ops.py": {
        0: "补丁算子集合合法",
        1: "有违规（发出 ins / 覆盖式赋值 / 未知算子被静默吞掉）",
        2: "缺输入",
    },
    "tools/check_py36_clean.py": {
        0: "本仓源码全部通过 3.6.5 语法门",
        1: "有源码违反 3.6.5 承诺",
        2: "缺输入",
    },
    "tools/check_readme_parity.py": {
        0: "两侧结构对等，且两侧质量门表 == tools/check_*.py 真实清单，"
           "表里每一行都含那道门自己声明的 ROW_SIGNATURE",
        1: "发现不对等 / 质量门表与真实护栏清单不符 / 表行缺本门签名"
           "（P1/P2/P4/P5 任一红）",
        2: "缺输入（任一 README 不存在）",
    },
    "tools/check_subprocess_hygiene.py": {
        0: "子进程卫生全部合规",
        1: "有违规（捕获输出却继承 stdin / 缺 timeout / 未登记）",
        2: "缺输入",
    },
    "tools/check_c_frontend_shapes.py": {
        0: "C 前端函数定义形态六条判据（F1–F6）全绿，且夹具完备性与棘轮全绿",
        1: "有违规（某条判据红 / 棘轮不符 / 夹具被改瘦）",
        2: "缺输入（找不到 matlabc.py / 公开 CLI 跑不起来 / JSON 不可解析）",
    },
    "tools/check_boundary_reverse.py": {
        0: "「诚实的边界」的每条否定式承诺都有反向判据，且公开 CLI 行为全绿（V1–V5）",
        1: "有违规（未认领 / 歧义 / 空断言 / 陈旧 / 棘轮不符 / 行为不符）",
        2: "缺输入（找不到 matlabc.py / 工具脚本，或公开 CLI 跑不起来）",
    },
    "tools/check_known_red.py": {
        0: "登记与事实两向一致（静态 K1–K6 + 实测 K7–K9：覆盖 / 真缺失 / 理由具名 / 跳过为真 / 新缺口 / 缺输入 / 红不红 / 绿不绿 / 跳不跳）",
        1: "有违规（未登记 / 陈旧 / 理由不具名 / 伪装跳过 / 新缺口）",
        2: "缺输入（找不到 tests/test_matlabc.py）",
    },
    "tools/check_py_js_frontend_shapes.py": {
        0: "Python / JS 前端函数定义形态六条判据（G1–G6）全绿，且夹具完备性与棘轮全绿",
        1: "有违规（某条判据红 / 棘轮不符 / 夹具被改瘦）",
        2: "缺输入（找不到 matlabc.py / 公开 CLI 跑不起来 / JSON 不可解析）",
    },
}

GUARD_SCRIPTS = tuple(sorted(GUARD_CONTRACT))

# ---------------------------------------------------------------------------
# R39（C''9）：把退出码契约推广到 ci-examples/。
#
# 为什么需要单独一档：`ci-examples/` 里的东西会被用户**直接复制走**
# （README 的原话就是「复制为 .github/workflows/…」）。模板一旦在退出码上说谎，
# 用户的流水线会长期静默失效 —— 而且**没有任何现有门看得见它**：
#   * check_doc_flags 只认 README / CONTRIBUTING / 6 个入口脚本的正文；
#   * check_help_contract 的 CONTRACT 只管入口脚本，GUARD_CONTRACT 只管护栏。
#
# 与那两档的差别（**故意不同，不是漏做**）：
#   * 判据仍是「登记有依据 + 反向 + 陈旧」，但对 shell 脚本用 `exit N` 而不是
#     Python 的 `return N` —— 语言都不同，硬套同一套正则只会得到假绿。
#   * 对「只断言非零、不点具体数字」的 YAML 模板，用**证伪式短语登记**：
#     模板里必须真的出现那句断言，而 matlabc.py 的退出契约里必须真的存在非零码。
#     两向成立才算过 —— 一旦 matlabc 改成永远 0，这条会红。
# ---------------------------------------------------------------------------
CI_PY_EXIT_CONTRACT = {
    "ci-examples/merge_sarif.py": {
        0: "合并成功且输出已落盘",
        1: "输入里找不到任何 SARIF 文件",
        2: "用法错误（参数不足 / --summary 缺路径）",
    },
}

CI_SH_EXIT_CONTRACT = {
    "ci-examples/pre-commit": {
        0: "没有可跑的检查，放行提交",
        1: "连仓库根目录都进不去",
    },
}

# 只断言「失败时非零退出」、不点具体数字的模板：登记它**必须包含的那句话**。
# 两向：改掉措辞 → 红（登记陈旧）；matlabc 不再有任何非零码 → 也红（前提失效）。
CI_RELIES_ON_NONZERO = {
    "ci-examples/github-actions-static-analysis.yml": "非零退出",
    "ci-examples/gitlab-ci-static-analysis.yml": "非零退出",
}

SH_EXIT_RE = re.compile(r"\bexit\s+(\d+)\b")


def _sh_exit_literals(src):
    """shell 脚本里的字面量退出码（`exit N`）。"""
    return set(int(x) for x in SH_EXIT_RE.findall(src or ""))


# ---------------------------------------------------------------------------
# R41：**散文里的数字**也要有人守。
#
# 起因：R40 是**手工**发现帮助里写着「7 道登记制护栏」而实际已是 9 道。
# 这类陈旧数字没有语法错误、不会让任何测试失败，只有一个人恰好读到才会被发现 ——
# 典型的「没人守就会烂」的东西。
#
# 判据：在**当前态**文档里，凡是 `N 道…护栏` / `N 道…门` / `N gates` 的写法，
# N 必须等于真实护栏数。
#
# 为什么用白名单而不是全仓扫描：`docs/SUPERPOWER_REVIEW_R*.md` 与
# `docs/analysis/**` 是**历史记录**，里面每一行的数字在写下的那一刻都是真的。
# 去"修正"它们是篡改历史。所以这里显式豁免，而不是把正则改松到"碰巧不命中"
# —— 后者会让判据失去检测力，而没人会注意到。
#
# 左边界 `(?<![\w.])` 不是多余的：`3.6.5 gate`、`P203 gate` 这类文本
# 会让 `(\d+)\s*gates?\b` 误命中"5 gate"（R41 实测就撞上了）。
DOC_NUMBER_CLAIM_FILES = (
    # 文件 → **期望至少出现几条**这类宣称。0 表示"允许没有"。
    # 为什么要求条数：不然删掉那句话就等于**静默取消覆盖**，而 rc 依然是 0。
    ("matlabc.py", 1),
    ("README.md", 1),
    ("README_CN.md", 1),
    ("CONTRIBUTING.md", 1),
)

# ── R42：**历史引用**的行内豁免标记 ─────────────────────────────────────────
#
# 起因：R41 的门一上线，**它立刻抓住了我自己刚写进 README 的那段话** —— 那段
# 解释「散文里的数字会烂」的文字，为了举例而引用了旧值（`7 gates`、`8 gates`）。
# 门是对的：那是**历史引用**，不是关于当前态的宣称。
#
# 两条路：
#   (a) 把正则改松，让它"碰巧不命中"这几句 —— 这正是上面那段注释明令禁止的：
#       判据会连带失去对真实违规的检测力，而且**没人会注意到**。
#   (b) 显式豁免：给该行一个行内标记，且标记**必须携带非空理由**。
# 取 (b)。标记是机器指令（Markdown 渲染后不可见），但它**出现在 diff 里**，
# 可以被 review —— 与仓库里 `NO_EVIDENCE` / `UNVERIFIABLE` 那套"证伪式登记"
# 是同一条纪律：允许豁免，但你必须把「为什么」写下来。
#
# 两条反向约束（缺了它，标记就退化成"永久静默关掉一行"）：
#   * 理由长度下限 NUM_EXEMPT_MIN_REASON：一个字符的理由不算理由（N4）。
#   * 陈旧标记要抓（N3）：标记所在行**本来就不会被判定为违规**时（那一行没有
#     数字、或数字本来就对），标记是多余的 —— 与「登记了而代码里没有 → 也抓」
#     是同一条纪律。
NUM_EXEMPT_RE = re.compile(
    r"<!--\s*guard-count\s*:\s*historical\s+(.+?)\s*-->")
NUM_EXEMPT_MIN_REASON = 8

GUARD_COUNT_PATTERNS = (
    re.compile(r"(?<![\w.])(\d+)\s*道[^\n]{0,12}?护栏"),
    re.compile(r"(?<![\w.])(\d+)\s*道[^\n]{0,6}?门"),
    re.compile(r"(?<![\w.])(\d+)\s*gates?\b"),
    re.compile(r"(?<![\w.])(\d+)\s*guard scripts?\b"),
    # 形态 5：数字在**括号里**、量词是「道」。
    # CONTRIBUTING.md 的写法：「登记制护栏（8 道，各自还会跑 --selftest；…）」——
    # 数字在「护栏」**之后**，上面四条都够不着。R41 首版就漏了这一处，
    # 是靠"把量词放宽再扫一遍"才发现的：**判据要按真实写法枚举，不能只写"最常见的那种"**。
    re.compile(r"[（(]\s*(\d+)\s*道[，,、]"),
)


def real_guard_count():
    """被 check_all 聚合的护栏数（= GUARD_SCRIPTS 去掉 runner 自己）。"""
    return len([s for s in GUARD_SCRIPTS
                if os.path.basename(s) != "check_all.py"])


def scan_doc_numbers(text, want):
    """核心纯函数：一次扫完一份文档，返回 dict。抽成纯函数是为了自证不必造文件。

    键：
      hits         : [(行号, 命中文本, 该文本写的数)] —— **未被豁免**的全部命中
                     （含数字正确的，调用方自己筛）
      exempt       : [(行号, 理由)] —— 生效的历史引用豁免
      marker_probs : [str] —— 标记**自身**的问题（理由太短 N4 / 陈旧标记 N3）
    """
    hits, exempt, probs = [], [], []
    for i, line in enumerate((text or "").split("\n"), 1):
        line_hits = []
        for rx in GUARD_COUNT_PATTERNS:
            for m in rx.finditer(line):
                line_hits.append((m.group(0).strip(), int(m.group(1))))
        mm = NUM_EXEMPT_RE.search(line)
        if mm is None:
            for hit, got in line_hits:
                hits.append((i, hit, got))
            continue
        reason = mm.group(1).strip()
        if len(reason) < NUM_EXEMPT_MIN_REASON:
            probs.append("N4 第 %d 行豁免标记的理由只有 %d 个字符（下限 %d）—— "
                         "一个字符就能永久关掉一行，等于静默取消覆盖"
                         % (i, len(reason), NUM_EXEMPT_MIN_REASON))
            # **理由不合格 = 标记不存在**：继续豁免会让「标记无效」与
            # 「标记生效」两种语义同时成立，读数就不可信了。
            for hit, got in line_hits:
                hits.append((i, hit, got))
            continue
        if not [h for h in line_hits if h[1] != want]:
            probs.append("N3 第 %d 行的豁免标记**是陈旧的**：这一行本来就不会被判"
                         "为违规（没有数字，或数字本来就对）—— 陈旧登记必须抓"
                         % i)
            continue          # 陈旧标记不生效；它唯一的信号就是上面这条
        exempt.append((i, reason))
    return {"hits": hits, "exempt": exempt, "marker_probs": probs}


def doc_number_problems(text, want):
    """纯函数：只含**与 want 不符**的（已扣掉生效的历史引用豁免）。"""
    return [(ln, hit, got)
            for ln, hit, got in scan_doc_numbers(text, want)["hits"]
            if got != want]


def num_exempt_problems(text, want):
    """纯函数：标记自身的问题（理由太短 / 陈旧标记）。"""
    return scan_doc_numbers(text, want)["marker_probs"]


def audit_doc_numbers(root, on_problem):
    """R41/R42：核对当前态文档里的「N 道护栏」类数字。

    返回 (核对过的文件数, 生效的历史引用豁免条数)。
    """
    want = real_guard_count()
    n = 0
    n_exempt = 0
    for rel, min_claims in DOC_NUMBER_CLAIM_FILES:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            on_problem("N0 %s 不存在（缺输入 → 红）" % rel)
            continue
        try:
            with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as e:
            on_problem("N0 %s 读不到（%s）" % (rel, e))
            continue
        n += 1
        sc = scan_doc_numbers(text, want)
        n_exempt += len(sc["exempt"])
        for line, hit, got in doc_number_problems(text, want):
            on_problem("N1 %s:%d 「%s」说 %d，真实护栏数是 %d —— "
                       "散文里的数字没人守就会烂（R41 起因：帮助里曾写 7、实际 9）"
                       % (rel, line, hit, got, want))
        for p in sc["marker_probs"]:
            on_problem("%s %s" % (rel, p))
        # min_claims 只数**未被豁免**的命中：否则把覆盖挪进一条豁免标记里，
        # 就等价于静默取消覆盖（与 N2 要防的是同一件事）。
        if len(sc["hits"]) < min_claims:
            on_problem("N2 %s: 期望至少有 %d 处**未被豁免**的「N 道护栏」类宣称，"
                       "实际 %d 处 —— 覆盖被静默取消了（rc 依然是 0，所以必须抓）"
                       % (rel, min_claims, len(sc["hits"])))
    return n, n_exempt

# R4 的唯一事实源：每个被示例指向的脚本，登记一条**无副作用**命令。
# 元组形态：(argv 列表, 是否按设计无输出)。
#   * 只允许 --help / --version / --selftest 这类不改盘的开关；
#   * expect_blank=True 表示「rc=0 且零输出是设计如此」（stdio MCP server），
#     与 check_doc_flags 的 NO_HELP_SCRIPTS 是同一套证伪式登记：它必须能证明
#     自己真的是空的，而不是「恰好没输出就放过」。
RUNNABLE = {
    "matlabc.py": (["--version"], False),
    "matlabc_flow.py": (["--help"], False),
    "matlabc_ask.py": (["--help"], False),
    "matlabc_mcp.py": (["--help"], True),
    "gui.py": (["--selftest"], False),
}

# R5（R33/C'8）：帮助文本**体积棘轮**（上下界都要管）。
# 为什么两个方向都要管：
#   * 下界：防「帮助被无声缩水回六行」（R3 只是结构棘轮，能靠格式骗过；
#     体积下界是最后一道物理约束）。
#   * 上界：`--help` 是终端里读的。超过某个量级，用户根本不会读 ——
#     那时内容应改放 docs/matlabc_USAGE.md，而不是继续堆在 --help 里。
# 为什么界是这些数（**写清楚理由，不是调出来的**）：
#   * 下界 400 B：一个 usage + 一段说明 + 退出码段的最小体量；
#     低于它几乎必然是「只剩 argparse 自动 usage」。
#   * matlabc.py 上界 64 KiB ≈ 800 行，是终端交互阅读的上限；它是旗舰入口、
#     docstring 即 epilog，因此单独给一个更宽的界。
#   * 其余入口上界 16 KiB：辅助入口，超过它说明该拆到独立文档。
HELP_BYTES = {
    "matlabc.py": (400, 64 * 1024),
    "matlabc_flow.py": (400, 16 * 1024),
    "matlabc_ask.py": (400, 16 * 1024),
    "matlabc_mcp.py": (0, 0),          # stdio server：按设计零输出，不设界
    "gui.py": (400, 16 * 1024),
}

# R38/C''8：体积棘轮的**第二臂 —— 相对界**。
#
# 只有绝对界是不够的，而且是**两头不够**：
#   * 对辅助入口（matlabc_ask.py 实测 919 B、上界 16 KiB）等于没设界 ——
#     它可以悄悄胖 8 倍而 rc 依然是 0。
#   * 对旗舰入口又太紧：合法地加三个功能就可能顶到 64 KiB，于是界要么被随手
#     放宽（等于取消），要么逼着把帮助拆走（可读性反而变差）。
#
# 相对界的做法：记一份**已批准快照**，实测值相对快照的漂移不得超过
# ±HELP_DRIFT_BYTES。为什么是**绝对字节带**而不是百分比：百分比带的分辨率
# 随快照大小变（30% × 50451 = 15135 B），于是「一个自称精确的棘轮，分辨率
# 比它记录的数字粗 500 倍」—— 这正是 R63 §7.8 量出、R64 修掉的那件事。
#   matlabc.py：64 KiB 绝对上界 vs 50451±64 B ⇒ 漂移带先起作用
#   matlabc_ask.py：16 KiB 绝对上界 vs 919±64 B ⇒ 漂移带先起作用
# 三条臂的分工与账见下面的 HELP_DRIFT_BYTES 一节。
#
# 为什么用「已批准快照」而不是 C''8 原文的「上一 tag」：
# 本仓**至今没有任何 tag**（`git tag` 为空），那个基线根本不存在。
# 快照与 tag 的唯一差别是「谁批准」，而快照随时可用、而且在 diff 里看得见 ——
# 等本仓开始打 tag 时，这道门一行都不用改。
# 漂移超限时的正当做法**不是**放宽这两个数，而是同步更新快照
# （那是一次显式的、可评审的批准动作 —— 这正是棘轮的意义）。
HELP_BYTES_SNAPSHOT = {
    "matlabc.py": 50451,
    "matlabc_flow.py": 2075,
    "matlabc_ask.py": 919,
    "matlabc_mcp.py": 0,
    "gui.py": 2651,
}
# R64/C13-9：棘轮的**分辨率必须说得出数**，而且读数必须**可复现**。
#
# 实测（R63 §7.8 首次量出、R64 量准，见 docs/SUPERPOWER_REVIEW_R64.md §1）：
# 同一个 `matlabc.py` 的 `--help` 字节数随两件**与被测对象无关**的事变：
#   * 解释器：3.10 -> 50481 / 3.13 -> 50451（差 30 B）
#   * 终端宽度：3.10 下 COLUMNS=200 -> 45827（差 −4654 B）
# 而旧容差 max(30% × 50451, 512) = **15135 B** ⇒ 30 B 的漂移整个被吞掉。
#
# R64 的三条修正：
#   ① **钉死测量口径**：跑 `--help` 时固定 COLUMNS（HELP_MEASURE_COLUMNS）。
#      这一条修的是**真 bug** —— 修复前从 200 列的终端跑这道门，结论与 80 列不同。
#   ② **容差改成说得出分辨率的绝对字节带** HELP_DRIFT_BYTES。
#      为什么是 64：实测**唯一**的跨解释器差是 matlabc.py 的 30 B（argparse 3.10
#      会把 metavar 同时印在短选项上、3.13 起不印，正好多一行 30 B），
#      64 = 2 倍余量。分辨率因此从 15135 B 提到 **64 B**（236 倍）。
#   ③ **再加一条精确臂**（见 _canon_help / HELP_CANON_SNAPSHOT）：在同一份帮助的
#      **规范形**上做**逐字节相等**断言，容差 0 ⇒ 分辨率 **1 字节**。
HELP_DRIFT_BYTES = 64

# 臂 ①② 的测量宽度：80 列（终端里真读得到的口径）。**必须钉死** ——
# 子进程里的 argparse 会读 `COLUMNS`（shutil.get_terminal_size 优先看它，
# 与是不是 tty 无关），不钉就随调用方终端宽度变，见上面的 ①。
HELP_MEASURE_COLUMNS = 80

# 臂 ③ 的测量宽度：宽到**不再折行**（实测 500 列起规范形已稳定，取 10000 留余量）。
HELP_CANON_COLUMNS = 10000

# 臂 ③ 的已批准快照：`_canon_help(<script> --help @ HELP_CANON_COLUMNS)` 的字节数。
# 这些数是**规范化之后**的读数，与解释器、终端宽度**都无关**
# （实测 {3.10, 3.13} × {500, 4000, 10000} 共 6 个读数逐字节相同），
# 因此可以用**容差 0** 断言 —— 分辨率 1 字节。
# 注意 matlabc_mcp.py 也在册：它的 HELP_BYTES 界是 (0, 0)（按设计零输出），
# 但「内容必须一直是空的」是一条真断言，不该因为「没设体积界」而漏掉。
HELP_CANON_SNAPSHOT = {
    "matlabc.py": 42053,
    "matlabc_flow.py": 1701,
    "matlabc_ask.py": 756,
    "matlabc_mcp.py": 0,
    "gui.py": 2290,
}

# 真跑示例的墙钟上限。实测这些命令都是 0.2–1.0s 返回（探针 probe_safe_flags），
# 60s 有 ~100 倍余量；上限的意义是「让挂死变成红，而不是让门永远等着」。
RUN_TIMEOUT = 60.0

DIAGRAM_CHARS = set("┌└├│─┐┘┤┬┴┼▲▼◀▶╔╚╠║╗╝╣")
EXIT_HEADING = re.compile(r"退出码")
EXIT_LINE = re.compile(r"^\s*(\d+)\s*[=:：]")
INLINE_CODE_RE = re.compile(r"(\d+)\s*[=:：]")
EXAMPLE_RE_TMPL = r"python\s+%s\b"


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _docstring(path):
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError:
        return None, None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src, None
    return src, ast.get_docstring(tree, clean=False)


def _is_sep_line(s):
    """是不是「分隔线」（如 ───── 或 =====），用于跨过标题与正文之间的装饰。"""
    body = s.replace(" ", "")
    return bool(body) and len(body) >= 4 and \
        all(ch in "─-=~—" for ch in body)


# ── R51（C''''2）：**「诚实的边界」逐字契约** ────────────────────────────────
#
# 动因：`--help` 的「诚实的边界」小节是**产品对用户的书面承诺** —— 它列出的每一条
# 都是「这件事我不做」。这类承诺有一个隐蔽的腐烂方式：**没有任何装置守着它本身**，
# 于是下一轮改代码时某条边界会被悄悄挪走。R50 的 `.exts` 就是同一形态：一句
# docstring 宣称的接线在源码里不存在，而此前没有任何装置守着**那句话**。
#
# R51 把这一节变成**逐字契约**：登记表与帮助正文互为对手方，谁掉队谁红。
#
# 为什么用它而不是「帮助里必须出现某几个字符串」：后者只查一条、且新增边界
# 不会被发现（覆盖可以静默缩水，与 R41 的 N2 是同一件事）。
#
# 诚实声明（不假装）：
#   * B1–B3 保证的是「登记表与帮助互为对手方」，**不保证 bullet 的内容正确**
#     —— 一句错话照样能过；内容的正确性靠 review 与 B3 里显式列出的 token。
#   * `head` 前缀必须唯一：两条 bullet 共用一个前缀时 B2 直接报歧义（不许蒙对）。
BOUNDARY_SECTION = "诚实的边界"
BOUNDARY_MIN_REASON = 8

# 运行期绑定这条边界点名的**替代装置**（单一事实源）：
# 帮助正文与两侧 README 都必须**逐字**出现它们（B3 / B5）。
# 为什么非要点名替代手段：只写「不跟踪运行期绑定」等于把一个死胡同交给用户；
# 写下 `ltrace` / `strace -e openat` / `LD_DEBUG=bindings` 才是**可执行的**边界。
RUNTIME_BINDING_TOOLS = ("ltrace", "strace -e openat", "LD_DEBUG=bindings")

BOUNDARY_CLAIMS = (
    {
        "head": "语言：",
        "help_must": ("没有前端", "[warn]"),
        "reason": "扫到不支持的语言必须点名文件并打 warn，不能静默返回 0 结果",
    },
    {
        "head": "C++：",
        "help_must": ("按 C 子集解析", "不保证"),
        "reason": "cpp 是 c 的别名，模板/类/命名空间/重载是已披露的降级而非 bug",
    },
    {
        "head": "前端实现：",
        "help_must": ("行锚定正则", "不识别", "K&R"),
        "reason": "前端仍是行锚定正则（C 已升级为词法配平），必须写明不识别的那两类",
    },
    {
        "head": "预处理：",
        "help_must": ("#if 0", "按兵不动"),
        "reason": "只做字面量 #if 0 感知；不猜宏是否定义，否则会把活代码当死代码",
    },
    {
        "head": "动态库：",
        # 这条是本轮（C''''2）真正补的内容：帮助原本只写「不解析运行期绑定」，
        # **没有点名任何替代装置**，实测三个 token 在帮助与两侧 README 里都是 0 次。
        "help_must": ("不跟踪运行期绑定", "dlopen", "LoadLibrary", "dlsym",
                      "LD_PRELOAD") + RUNTIME_BINDING_TOOLS,
        "docs_must": RUNTIME_BINDING_TOOLS,
        "docs": ("README.md", "README_CN.md"),
        "reason": "运行期绑定零覆盖，必须点名可替代的外部装置，否则用户以为它能查",
    },
    {
        "head": "GPU：",
        "help_must": (".text._Z", "不静默给 0"),
        "reason": "PTX 提不出 kernel 名时必须写原因，不能静默给 0 个 kernel",
    },
    {
        "head": "Mach-O：",
        "help_must": ("合成夹具", "verified: NO"),
        "reason": "有夹具无真实语料，两条轴必须分开写，不许把夹具当实测",
    },
    {
        "head": "**跨语言算子有一个是「不做」的**：",
        "help_must": ("_UNIMPLEMENTED_KINDS", "pyflakes"),
        "reason": "「不做」的算子必须说明理由并点名真正能做它的旁路工具",
    },
)


def parse_boundary_bullets(doc):
    """切出帮助正文「诚实的边界」小节里的 bullets。

    返回 [(head, full_text)]；找不到小节返回 None（= 缺输入）。
    切法：定位标题行 → 越过其后第一条分隔线 → 收集到**下一条分隔线**为止；
    形如 `  * xxx` 的行是新 bullet，其余非空行是它的续行（本仓的排版约定）。

    ⚠ 这里只认「首行」定 bullet —— 续行缩进不参与判定。判据不依赖缩进宽度，
    因为缩进一变就会让判据自己变成噪声源（与本仓 D5 的教训同源）。
    """
    if not doc:
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


def boundary_verdict(doc, claims):
    """R51 的判定，抽成**纯函数**（自证不必起进程、不必造文件）。

    返回 (问题列表, 核对过的 bullet 数)。问题为空 = 通过。
    问题串一律以 B0–B4 开头，便于外部只按前缀判断。
    """
    probs = []
    bullets = parse_boundary_bullets(doc)
    if bullets is None:
        return (["B0 帮助正文里找不到「%s」小节 —— 缺输入 → 红"
                 % BOUNDARY_SECTION], 0)
    heads = [h for h, _ in bullets]
    texts = dict(bullets)

    # B4 先查：理由不合格的登记**不参与认领判定**。否则「无效登记」与「未登记」
    # 两种语义会同时成立，读数就不可信了 —— 与 R42 的 N4 同一条纪律。
    usable = []
    for c in claims:
        reason = (c.get("reason") or "").strip()
        if len(reason) < BOUNDARY_MIN_REASON:
            probs.append("B4 登记项 head=%r 的理由只有 %d 个字符（下限 %d）—— "
                         "少于下限的登记不生效（否则一个字符就能永久关掉一条边界）"
                         % (c.get("head"), len(reason), BOUNDARY_MIN_REASON))
            continue
        usable.append(c)

    # B2：每条登记项必须认领到**恰好一条** bullet（0 = 陈旧；>1 = 前缀不唯一）。
    claimed = {}
    for c in usable:
        head = c.get("head") or ""
        hit = [h for h in heads if h.startswith(head)]
        if len(hit) == 0:
            probs.append("B2 登记项 head=%r 在小节里认领不到任何 bullet —— "
                         "陈旧登记必须抓（边界已被挪走或改写）" % head)
        elif len(hit) > 1:
            probs.append("B2 登记项 head=%r 同时认领到 %d 条 bullet —— "
                         "前缀不唯一，登记表失去判定力" % (head, len(hit)))
        else:
            claimed[hit[0]] = c

    # B1：小节里每条 bullet 都必须被认领（新增边界不许悄悄溜进来）。
    for h in heads:
        if h not in claimed:
            probs.append("B1 小节里的 bullet %r **未被登记** —— 新增一条「不做的"
                         "边界」必须同时写下理由并进登记表，否则下一轮它会被挪走"
                         % h[:40])

    # B3：登记项声明的 token 必须逐字出现在它认领的 bullet 全文里。
    for h in sorted(claimed):
        text = texts.get(h, h)
        for tok in claimed[h].get("help_must") or ():
            if tok not in text:
                probs.append("B3 bullet %r 里逐字找不到 `%s` —— 帮助正文把这条"
                             "边界的**内容**改写掉了（登记表说它还在）"
                             % (h[:24], tok))
    return probs, len(bullets)


def boundary_doc_problems(root, claims):
    """B5：带 `docs` 的登记项，其 `docs_must` 必须在所列文档里逐字出现。

    返回 (问题列表, 核对过的文档数)。这是「帮助说了、README 没说」这条缝的对手方。
    """
    probs = []
    n = 0
    seen = set()
    for c in claims:
        rels = c.get("docs") or ()
        toks = c.get("docs_must") or ()
        if not rels or not toks:
            continue
        for rel in rels:
            if rel in seen:
                continue          # 同一份文档只读一次、只计一次
            seen.add(rel)
            p = os.path.join(root, rel)
            if not os.path.exists(p):
                probs.append("B5 文档 %s 不存在（缺输入 → 红）" % rel)
                continue
            try:
                with io.open(p, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError as e:
                probs.append("B5 文档 %s 读不到（%s）" % (rel, e))
                continue
            n += 1
            for tok in toks:
                if tok not in text:
                    probs.append("B5 %s 里逐字找不到 `%s` —— 帮助正文讲了运行期"
                                 "绑定的替代装置，而文档没讲，读者看到的就不是"
                                 "同一件事" % (rel, tok))
    return probs, n


def audit_boundary(root, on_problem, claims=None):
    """对真实仓库施加 R51；返回 (bullet 数, B5 核对过的文档数)。"""
    claims = BOUNDARY_CLAIMS if claims is None else claims
    path = os.path.join(root, "matlabc.py")
    if not os.path.exists(path):
        on_problem("B0 matlabc.py 不存在（缺输入 → 红）")
        return (0, 0)
    _src, doc = _docstring(path)
    if doc is None:
        on_problem("B0 matlabc.py 解析不到模块 docstring（缺输入 → 红）")
        return (0, 0)
    probs, nb = boundary_verdict(doc, claims)
    for p in probs:
        on_problem(p)
    dprobs, nd = boundary_doc_problems(root, claims)
    for p in dprobs:
        on_problem(p)
    return (nb, nd)

def parse_exit_section(doc):
    """从 docstring 解析「退出码」段的码集合；解析不到返回 None。

    支持两种**同样合法**的排版（本仓两种都在用，不能只认一种）：
        A) 多行式：
               退出码：
                   0  = 好
                   1  = 也不好
        B) 内联式（标题与码同一行、用 `;`/`；` 分隔）：
               退出码：0 = 通过；1 = 有违规；2 = 缺输入
    """
    if not doc:
        return None
    lines = doc.split("\n")
    for i, ln in enumerate(lines):
        if not EXIT_HEADING.search(ln):
            continue
        # ---- B) 内联式：标题行本身带码 ----
        inline = INLINE_CODE_RE.findall(ln)
        if inline:
            return set(int(x) for x in inline)
        # ---- A) 多行式 ----
        codes = set()
        for sub in lines[i + 1:]:
            m = EXIT_LINE.match(sub)
            if m:
                codes.add(int(m.group(1)))
                continue
            if codes:
                break           # 码已收集完，遇到第一行不是码的就收工
            s = sub.strip()
            if not s:
                continue        # 标题与码之间允许空行
            if _is_sep_line(s):
                continue        # 也不允许「分隔线」把分段切断（matlabc.py 的样式）
            break               # 别的正文 → 这一段其实没有退出码
        if codes:
            return codes
    return None


def has_diagram(doc, min_lines=3, min_chars=3):
    """≥min_lines 行、每行 ≥min_chars 个框线字符（一个字 1 个字符）。"""
    if not doc:
        return False
    n = 0
    for ln in doc.split("\n"):
        if sum(1 for ch in ln if ch in DIAGRAM_CHARS) >= min_chars:
            n += 1
    return n >= min_lines


def has_example(doc, script):
    if not doc:
        return False
    return re.search(EXAMPLE_RE_TMPL % re.escape(script), doc) is not None


def _code_has_evidence(src, code):
    """源码里是否存在这个码的退出依据（四种写法）。

    注意 `(?![.\\d])`：它挡住 `return 0.0` / `sys.exit(20)` 这类**看起来像**
    但含义完全不同的写法。R1b 首跑就在这里抓到过本函数自身的 bug ——
    `\\breturn\\s+0\\b` 会在 `return 0.0` 上命中（`0` 与 `.` 之间就是词边界），
    于是一个返回浮点数的函数被当成了「退出码 0 的依据」。
    这正是「测量工具自身的 bug 会伪造出被测对象的 bug」的又一例。
    """
    if not src:
        return False
    tail = r"(?![.\d])"
    pats = (
        r"\breturn\s+%d" % code + tail,
        r"\bsys\.exit\(\s*%d\s*\)" % code,
        r"\bexit_code\s*=\s*%d" % code + tail,
        r"\[\s*[\"']exit_code[\"']\s*\]\s*=\s*%d" % code + tail,
    )
    for p in pats:
        if re.search(p, src):
            return True
    return False


def _run_safe_example(root, script, argv, env_extra=None):
    """真跑一条登记的示例命令，返回 (rc, out_bytes) 或 (None, b"") 表示超时。

    纪律（与 check_subprocess_hygiene.py 的要求一致，这里是它的对手方）：
      * `stdin=DEVNULL`：绝不继承调用方的 stdin —— 本仓真发生过 stdio MCP
        server 在继承的 stdin 上等满 180s 的事故（R62-R31e）。
      * `timeout=RUN_TIMEOUT`：挂死必须变成红，而不是让门永远等着。
      * 捕获输出，因为要断言「rc 与字节数」这两个事实。
      * `env_extra`（R64/C13-9）：在**继承来的**环境之上追加/覆盖几个变量。
        R5 用它钉死 `COLUMNS` —— 不钉的话，子进程里的 argparse 会去读
        `COLUMNS`（`shutil.get_terminal_size` 优先看它，与是不是 tty 无关），
        于是这道门的结论会随**调用方终端有多宽**变（实测差 −4654 B）。
    """
    import subprocess
    p = os.path.join(root, script)
    env = None
    if env_extra:
        env = dict(os.environ)
        env.update(env_extra)
    try:
        r = subprocess.run([sys.executable, p] + list(argv), cwd=root,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=RUN_TIMEOUT,
                           env=env)
    except subprocess.TimeoutExpired:
        return None, b""
    except OSError as e:
        return -1, str(e).encode("utf-8", "replace")
    return r.returncode, r.stdout or b""


def _literal_sys_exits(src):
    """源码里所有 `sys.exit(<整数字面量>)` 的码集合。"""
    out = set()
    if not src:
        return out
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if not (isinstance(f, ast.Attribute) and f.attr == "exit"
                and isinstance(f.value, ast.Name) and f.value.id == "sys"):
            continue
        if len(n.args) != 1:
            continue
        a = n.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, int) \
                and not isinstance(a.value, bool):
            out.add(a.value)
    return out


def _is_stale_no_evidence(srcs, code):
    """R1b 的判定抽成纯函数：给定证据源码列表，这个码是否**已经**有依据了。

    有依据 → 该 NO_EVIDENCE 条目已过期（返回 True）。
    无依据 → 登记仍然合理（返回 False）。
    """
    for s in srcs:
        if _code_has_evidence(s, code):
            return True
    return False


def _r4_verdict(script, target, argv, rc, out, expect_blank):
    """R4 的判定，抽成**纯函数**（好让自证能直接测它，而不必真的起进程）。

    返回问题字符串，或 None 表示通过。
    注意 expect_blank 的两种语义（这是本函数唯一容易写反的地方）：
        expect_blank=False → rc 必须 0 **且**必须有输出（有输出才证明它真的做了事）
        expect_blank=True  → rc 必须 0 **且**必须零输出（stdio server 的设计如此）
    """
    cmd = "python %s %s" % (target, " ".join(argv))
    if rc is None:
        return ("R4 %s: `%s` 在 %.0fs 内没有返回 —— 帮助里写的示例命令自己挂死了"
                % (script, cmd, RUN_TIMEOUT))
    if rc != 0:
        return "R4 %s: `%s` 返回 rc=%s（示例必须 rc=0）" % (script, cmd, rc)
    if expect_blank and out:
        return ("R4 %s: `%s` 本该按设计零输出，却输出了 %d 字节"
                % (script, cmd, len(out)))
    if (not expect_blank) and not out:
        return ("R4 %s: `%s` rc=0 但零输出 —— "
                "「问帮助得到沉默」与坏掉在信号上无法区分" % (script, cmd))
    return None


# argparse 3.10 会把 metavar 同时印在短选项上（多一行 `  -o OUTPUT, --output OUTPUT`），
# 3.13 起不再印 —— 这是两个解释器之间**唯一**的渲染差异（实测，见审查文档 §1）。
# 规则必须**窄**：两个 metavar 逐字相同（反向引用 \3）才算，免得误伤正文。
_CANON_DEDUP_RE = re.compile(rb"(?m)^(  )-(\w) (\S+), (--[\w\-]+) \3(\r?)$")
_CANON_WS_RE = re.compile(rb"[ \t\r\n]+")


def _canon_help(raw):
    """把 `--help` 的原始字节折成**版本 + 宽度双无关**的规范形。

    两步（纯文本操作，不 import argparse、不起进程）：
      ① 去掉 argparse 3.10 的 metavar 重复（见 _CANON_DEDUP_RE）；
      ② 把所有空白串（含 CR/LF）折叠成一个空格 —— 这一条同时抹掉「折行」与
         「帮助是换行到下一行、还是接在同一行」两种**布局**差。
    剩下的只有**内容**：实测 {3.10, 3.13} × {500, 4000, 10000} = 6 个读数
    逐字节相同（见 docs/SUPERPOWER_REVIEW_R64.md §1）。

    诚实声明：规范形**看不见布局**（缩进、折行位置改了它不知道）——
    布局由臂 ①② 的绝对界与字节带兜。本条只守内容，且分辨率是 1 字节。
    """
    t = _CANON_DEDUP_RE.sub(rb"\1-\2, \4 \3\5", raw)
    return _CANON_WS_RE.sub(b" ", t).strip()


def _r5_verdict(script, n_bytes, lo, hi, snapshot):
    """R5 臂 ①② 的判定，抽成**纯函数**（自证不必起进程）。

    两条臂，**取严**（R64/C13-9 起 `allow` 是绝对字节带）：
      臂 A 绝对界：lo <= n_bytes <= hi
      臂 B 漂移带：|n_bytes - snapshot| <= HELP_DRIFT_BYTES
    返回问题字符串，或 None 表示通过。

    ⚠ 分辨率 = HELP_DRIFT_BYTES（64 B）。旧实现用 max(30% × 快照, 512)，
    对 matlabc.py 是 15135 B —— 即 30 B 的漂移整个被吞掉。收紧是**故意的**：
    两条旧「好样本」（+250 B / +400 B）在新带下**必须**变红。
    """
    if hi <= 0:
        return None            # (0, 0) = 显式「不设界」（stdio server 按设计零输出）
    if n_bytes < lo:
        return ("R5 %s: --help 只有 %d 字节（绝对下界 %d）—— 帮助被无声缩水了"
                % (script, n_bytes, lo))
    if n_bytes > hi:
        return ("R5 %s: --help 已达 %d 字节（绝对上界 %d）—— 终端里读不完，"
                "应拆分到 docs/ 独立文档" % (script, n_bytes, hi))
    if snapshot is None:
        return None
    allow = HELP_DRIFT_BYTES
    drift = n_bytes - snapshot
    if abs(drift) <= allow:
        return None
    how = "膨胀" if drift > 0 else "缩水"
    return ("R5 %s: --help %d 字节相对已批准快照 %d 漂移 %+d 字节（%s；"
            "本臂分辨率 ±%d B）—— 若是**合法增长**，请在同一个提交里把 "
            "HELP_BYTES_SNAPSHOT['%s'] 更新为 %d 并在提交信息里说明理由；"
            "不要放宽 HELP_DRIFT_BYTES"
            % (script, n_bytes, snapshot, drift, how, allow,
               script, n_bytes))


def _r5c_verdict(script, canon_bytes, canon_snapshot):
    """R5c（臂 ③）的判定，纯函数：规范形**逐字节相等**（容差 0 ⇒ 1 字节）。

    为什么容差写 0 而不是一个小数字：规范形已经与解释器、终端宽度**都无关**
    （见 _canon_help 的实测），剩下的差异只可能来自**内容改动**。
    返回问题字符串，或 None 表示通过。
    """
    if canon_snapshot is None:
        return None
    if canon_bytes == canon_snapshot:
        return None
    return ("R5c %s: `--help` 的**规范形**变了（%d 字节，快照 %d，差 %+d）—— "
            "规范形与解释器、终端宽度都无关，所以这就是一次真实的内容改动；"
            "若为**合法**改动，请在同一提交里把 HELP_CANON_SNAPSHOT['%s'] "
            "更新为 %d 并在提交信息里说明理由"
            % (script, canon_bytes, canon_snapshot,
               canon_bytes - canon_snapshot, script, canon_bytes))


def audit(root, on_problem, cache=None):
    """对真实仓库施加 R1/R2/R3/R4/R5/R5c；返回检查过的脚本数。

    cache: {script: (rc, out)} 的运行结果缓存 —— 多个入口可能共用同一条示例
    （如 agent_loop 的示例挂在 matlabc_flow.py 上），只跑一次即可。
    传 None 时内部自建。
    """
    if cache is None:
        cache = {}
    n = 0
    for script in ENTRY_SCRIPTS:
        spec = CONTRACT[script]
        path = os.path.join(root, script)
        if not os.path.exists(path):
            on_problem("R0 %s 不存在（缺输入 → 红）" % script)
            continue
        src, doc = _docstring(path)
        if doc is None:
            on_problem("R0 %s 解析不到模块 docstring（缺输入 → 红）" % script)
            continue
        n += 1

        # ---- R1：登记有依据（含反向） ----
        for code in sorted(spec["codes"]):
            ok = False
            for ev in spec.get("evidence") or ():
                evp = os.path.join(root, ev)
                if not os.path.exists(evp):
                    on_problem("R1 %s: 证据文件 %s 不存在（缺输入 → 红）"
                               % (script, ev))
                    continue
                evsrc, _ = _docstring(evp)
                if _code_has_evidence(evsrc, code):
                    ok = True
                    break
            if not ok and (script, code) in NO_EVIDENCE:
                ok = True
            if not ok:
                on_problem("R1 %s: 登记了退出码 %d，但证据文件 %s 里找不到任何依据"
                           "（return %d / sys.exit(%d) / exit_code = %d）—— "
                           "凭空登记的退出码会让用户写出永远走不到的分支"
                           % (script, code, list(spec.get("evidence") or ()),
                              code, code, code))
        registered = set(spec["codes"])
        for code in sorted(_literal_sys_exits(src) - registered):
            on_problem("R1 %s: 源码里有 sys.exit(%d)，但 EXIT_CONTRACT 没登记它 —— "
                       "新增退出码必须同步登记并写进帮助" % (script, code))

        # ---- R1b：陈旧登记检测（R33 新增，C'6） ----
        # NO_EVIDENCE 是「暂时找不到依据」的登记。若后来源码里**补上了**依据，
        # 这条登记就过期了 —— 过期登记会掩盖「它其实有依据」这一事实，
        # 与本仓 POPEN_STREAMING / UNVERIFIABLE 的「陈旧也抓」是同一条纪律。
        for (ev_script, ev_code), _reason in sorted(NO_EVIDENCE.items()):
            if ev_script != script:
                continue
            evsrcs = []
            for ev in spec.get("evidence") or ():
                evp = os.path.join(root, ev)
                if os.path.exists(evp):
                    evsrc, _ = _docstring(evp)
                    evsrcs.append(evsrc)
            if _is_stale_no_evidence(evsrcs, ev_code):
                on_problem("R1b %s: NO_EVIDENCE 登记了退出码 %d（当初无依据），"
                           "但现在证据文件里已有依据 —— 陈旧登记必须删除"
                           % (script, ev_code))

        # ---- R2：帮助说全且不多说 ----
        declared = parse_exit_section(doc)
        if declared is None:
            on_problem("R2 %s: docstring 里解析不到非空的「退出码」段" % script)
        elif declared != registered:
            missing = sorted(registered - declared)
            extra = sorted(declared - registered)
            on_problem("R2 %s: 帮助与登记表不一致（少写 %s / 多写 %s）"
                       % (script, missing or "无", extra or "无"))

        # ---- R3：帮助有骨架（棘轮） ----
        ex_via = spec.get("example_via") or script
        if not has_example(doc, ex_via):
            on_problem("R3 %s: docstring 里没有一条 `python %s ...` 的可复制示例"
                       % (script, ex_via))
        if not has_diagram(doc):
            on_problem("R3 %s: docstring 里没有图示（需要 ≥3 行、每行 ≥3 个框线字符）"
                       % script)

        # ---- R4：示例是契约（R33 新增） ----
        # 只有登记在 RUNNABLE 里的脚本才能真跑；它随 example_via 走（agent_loop 是库）。
        target = ex_via
        if target not in RUNNABLE:
            on_problem("R4 %s: 示例脚本 %s 没有登记「可真跑」命令"
                       "（RUNNABLE 缺项 → 无法证明示例能跑）" % (script, target))
        else:
            argv, expect_blank = RUNNABLE[target]
            if target not in cache:
                cache[target] = _run_safe_example(root, target, argv)
            rc, out = cache[target]
            problem = _r4_verdict(script, target, argv, rc, out, expect_blank)
            if problem:
                on_problem(problem)
            # 光能跑还不够：这条命令必须**原样出现在文档里**，否则用户抄不到，
            # 它就成了只有护栏知道、而没人能用的内部约定。
            literal = "python %s %s" % (target, " ".join(argv))
            if literal not in doc:
                on_problem("R4 %s: 已验证可跑的 `%s` 没有原样出现在文档里 —— "
                           "能跑但抄不到，等于没写" % (script, literal))

        # ---- R5：帮助体积棘轮（R33/C'8 立，R38/C''8 加相对臂，R64/C13-9 三臂） ----
        # 臂 ①② 走**钉死 80 列**的读数（终端里真读得到），臂 ③ 走**钉死 10000 列**
        # 的读数（宽到不再折行 ⇒ 规范形只与内容有关）。
        # 两条读数用**不同缓存键**：键里若不写测量口径，两条臂会互相污染
        # —— 这正是 R64 顺手堵掉的一个隐患（旧键 `script + "::--help"` 不区分口径）。
        lo, hi = HELP_BYTES.get(script, (0, 0))
        if hi > 0:
            hk = "%s::--help@C%d" % (script, HELP_MEASURE_COLUMNS)
            if hk not in cache:
                cache[hk] = _run_safe_example(
                    root, script, ["--help"],
                    env_extra={"COLUMNS": str(HELP_MEASURE_COLUMNS)})
            _rc, _out = cache[hk]
            n_bytes = len(_out)
            if _rc is None:
                on_problem("R5 %s: `--help` 超时，拿不到体积" % script)
            else:
                msg = _r5_verdict(script, n_bytes, lo, hi,
                                  HELP_BYTES_SNAPSHOT.get(script))
                if msg:
                    on_problem(msg)
        # 臂 ③：规范形逐字节相等（R64/C13-9）。对**每一个**在册的入口都查，
        # 包括 HELP_BYTES 显式不设界的那一个（stdio server）—— 它也有内容可守。
        if script in HELP_CANON_SNAPSHOT:
            ck = "%s::--help@C%d" % (script, HELP_CANON_COLUMNS)
            if ck not in cache:
                cache[ck] = _run_safe_example(
                    root, script, ["--help"],
                    env_extra={"COLUMNS": str(HELP_CANON_COLUMNS)})
            _rc2, _out2 = cache[ck]
            if _rc2 is None:
                on_problem("R5c %s: `--help` 超时，拿不到规范形" % script)
            else:
                msg = _r5c_verdict(script, len(_canon_help(_out2)),
                                   HELP_CANON_SNAPSHOT[script])
                if msg:
                    on_problem(msg)
    return n


def audit_guards(root, on_problem):
    """R33（C'7）+ R63（G0b）：对护栏脚本施加 R1（+反向+陈旧）与 R2，
    并核对「存在 ⇄ 登记」。返回核对过的脚本数。"""
    n = 0
    for script in GUARD_SCRIPTS:
        registered = set(GUARD_CONTRACT[script])
        path = os.path.join(root, script)
        if not os.path.exists(path):
            on_problem("G0 %s 不存在（缺输入 → 红）" % script)
            continue
        src, doc = _docstring(path)
        if doc is None:
            on_problem("G0 %s 解析不到模块 docstring（缺输入 → 红）" % script)
            continue
        n += 1
        # R1：登记的每个码都要在源码里有依据
        for code in sorted(registered):
            if not _code_has_evidence(src, code):
                on_problem("G1 %s: 登记了退出码 %d，但源码里找不到依据"
                           "（return %d / sys.exit(%d)）" % (script, code, code, code))
        # R1 反向：源码里出现 sys.exit(<字面量>) 却没登记
        for code in sorted(_literal_sys_exits(src) - registered):
            on_problem("G1 %s: 源码里有 sys.exit(%d)，但 GUARD_CONTRACT 没登记它"
                       % (script, code))
        # R2：docstring 的「退出码」段必须等于登记表
        declared = parse_exit_section(doc)
        if declared is None:
            on_problem("G2 %s: docstring 里解析不到非空的「退出码」段" % script)
        elif declared != registered:
            on_problem("G2 %s: 帮助与登记表不一致（少写 %s / 多写 %s）"
                       % (script, sorted(registered - declared) or "无",
                          sorted(declared - registered) or "无"))
    # G0b（R63）：`tools/` 下每一个 `check_*.py` 都必须被 GUARD_CONTRACT 登记。
    # G0 管「登记了却不存在」；这一条管**反方向** —— 存在却没登记。
    # 没有它，新加一道护栏时可以**完全跳过退出码契约**而 rc 依然是 0：
    # R63 加 `check_known_red.py` 时实测「磁盘上有、登记表里没有」没有任何门报警。
    tdir = os.path.join(root, "tools")
    if os.path.isdir(tdir):
        on_disk = set("tools/" + f for f in os.listdir(tdir)
                      if f.startswith("check_") and f.endswith(".py"))
        for orphan in sorted(on_disk - set(GUARD_SCRIPTS)):
            on_problem("G0b %s 存在，但 GUARD_CONTRACT 没有登记它 —— "
                       "它的退出码契约没有任何人在核对" % orphan)
    return n


def on_problem_collector(bucket):
    def _cb(msg):
        bucket.append(msg)
    return _cb


def audit_ci_examples(root, on_problem, matlabc_codes):
    """R39（C''9）：ci-examples/ 的退出码契约。返回核对过的文件数。

    matlabc_codes = matlabc.py 的登记退出码集合（用于校验「非零退出」这个前提）。
    """
    n = 0
    for script, registered in sorted(CI_PY_EXIT_CONTRACT.items()):
        registered = set(registered)
        path = os.path.join(root, script)
        if not os.path.exists(path):
            on_problem("C0 %s 不存在（缺输入 → 红）" % script)
            continue
        src, doc = _docstring(path)
        if doc is None:
            on_problem("C0 %s 解析不到模块 docstring（缺输入 → 红）" % script)
            continue
        n += 1
        for code in sorted(registered):
            if not _code_has_evidence(src, code):
                on_problem("C1 %s: 登记了退出码 %d，但源码里找不到依据"
                           "（return %d / sys.exit(%d)）" % (script, code, code, code))
        for code in sorted(_literal_sys_exits(src) - registered):
            on_problem("C1 %s: 源码里有 sys.exit(%d)，但 CI_PY_EXIT_CONTRACT 没登记它"
                       % (script, code))
        declared = parse_exit_section(doc)
        if declared is None:
            on_problem("C2 %s: docstring 里解析不到非空的「退出码」段 —— "
                       "被复制进用户 CI 的脚本必须写清退出码" % script)
        elif declared != registered:
            on_problem("C2 %s: 帮助与登记表不一致（少写 %s / 多写 %s）"
                       % (script, sorted(registered - declared) or "无",
                          sorted(declared - registered) or "无"))

    for script, registered in sorted(CI_SH_EXIT_CONTRACT.items()):
        registered = set(registered)
        path = os.path.join(root, script)
        if not os.path.exists(path):
            on_problem("C0 %s 不存在（缺输入 → 红）" % script)
            continue
        try:
            with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError as e:
            on_problem("C0 %s 读不到（%s）" % (script, e))
            continue
        n += 1
        # shell 侧用 `exit N`，不是 Python 的 return —— 语言不同，判据必须不同
        for code in sorted(registered):
            if code not in _sh_exit_literals(src):
                on_problem("C1 %s: 登记了退出码 %d，但文件里没有 `exit %d`"
                           % (script, code, code))
        for code in sorted(_sh_exit_literals(src) - registered):
            on_problem("C1 %s: 文件里有 `exit %d`，但 CI_SH_EXIT_CONTRACT 没登记它"
                       % (script, code))

    for script, phrase in sorted(CI_RELIES_ON_NONZERO.items()):
        path = os.path.join(root, script)
        if not os.path.exists(path):
            on_problem("C0 %s 不存在（缺输入 → 红）" % script)
            continue
        n += 1
        try:
            with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError as e:
            on_problem("C0 %s 读不到（%s）" % (script, e))
            continue
        # 两向之一：模板必须真的还写着那句断言（陈旧的登记也要抓）
        if phrase not in src:
            on_problem("C3 %s: 登记它断言「%s」，但文件里已经没有这句话 —— "
                       "要么把话加回去，要么更新 CI_RELIES_ON_NONZERO"
                       % (script, phrase))
        # 两向之二：它的前提必须仍成立 —— matlabc.py 的退出契约里要有非零码
        if not [c for c in matlabc_codes if c != 0]:
            on_problem("C3 %s: 它断言「门禁 FAIL 会%s」，但 matlabc.py 的退出契约里"
                       "**没有任何非零码** —— 模板在说谎" % (script, phrase))
    return n


def _selftest():
    """两向自证：R1/R2/R3 各配独立坏样本与好样本，并对真实仓库整体核对。

    约定（**容易写反，所以写在这里**）：
        expect(tag, detected, want_problem)
          detected     = 判据认为「有问题」——也就是这道门会变红的那个布尔值
          want_problem = 我们希望它是反例(True)还是正例(False)
        两者一致才算这条自证通过。表达式必须写成「判据的检测结果」，
        不能写成「我的断言是否成立」，否则正反例会整片颠倒
        —— 首版就是这么错的，SELFTEST 立刻把它抓了出来。
    """
    bad = good = 0
    fails = []

    def expect(tag, detected, want_problem):
        nonlocal bad, good
        ok = (bool(detected) == bool(want_problem))
        print("  [%s] %-52s -> %s%s"
              % ("反例" if want_problem else "正例", tag,
                 "抓到" if detected else "放行",
                 "" if ok else "   *** 不符预期 ***"))
        if not ok:
            fails.append(tag)
        if want_problem:
            bad += 1
        else:
            good += 1

    # ---- R2：退出码段的解析 ----
    # 下面每个 detected_* 都是「判据会不会报问题」本身，不是「我的断言成不成立」。
    doc_ok = ("用法：\n    python x.py a\n\n退出码：\n"
              "    0  = 好\n    1  = 也不好\n\n边界：\n")
    expect("R2 正常退出码段解析出 {0,1}",
           parse_exit_section(doc_ok) != {0, 1}, False)
    expect("R2 完全没有退出码段",
           parse_exit_section("用法：\n    x\n") is None, True)
    expect("R2 空退出码段",
           parse_exit_section("退出码：\n\n用法：\n") is None, True)
    expect("R2 标题与码之间有分隔线（matlabc.py 的样式）",
           parse_exit_section("退出码\n──────\n  0  = a\n  2  = b\n\n正文\n")
           != {0, 2}, False)

    # ---- R1：依据识别（四种写法都要认，且不许把 20 认成 2） ----
    expect("R1 认 return 2",
           not _code_has_evidence("def f():\n    return 2\n", 2), False)
    expect("R1 认 sys.exit(2)",
           not _code_has_evidence("sys.exit(2)\n", 2), False)
    expect("R1 认 exit_code = 2",
           not _code_has_evidence("exit_code = 2\n", 2), False)
    expect('R1 认 result["exit_code"] = 3',
           not _code_has_evidence('result["exit_code"] = 3\n', 3), False)
    expect("R1 不把 return 20 误认成 return 2",
           _code_has_evidence("def f():\n    return 20\n", 2), False)
    expect("R1 不把 sys.exit(21) 误认成 2",
           _code_has_evidence("sys.exit(21)\n", 2), False)
    # 下面两条是 R1b 首跑抓出的真实工具 bug 的回归锚点：
    # `\breturn\s+0\b` 会在 `return 0.0` 上命中（词边界在 `0` 与 `.` 之间）。
    expect("R1 不把 return 0.0 当成退出码 0 的依据",
           _code_has_evidence("def f():\n    return 0.0\n", 0), False)
    expect("R1 不把 return 0.5 当成退出码 0 的依据",
           _code_has_evidence("return 0.5\n", 0), False)
    expect("R1 认真正的 return 0",
           not _code_has_evidence("def f():\n    return 0\n", 0), False)
    expect("R1 反向：未登记的 sys.exit(7) 必须被判为问题",
           bool(_literal_sys_exits("import sys\nsys.exit(7)\n") - {2}), True)
    expect("R1 不把 sys.exit(rc) 当字面量（无害）",
           bool(_literal_sys_exits("import sys\nsys.exit(rc)\n") - {2}), False)

    # ---- R1b：陈旧 NO_EVIDENCE 检测（表达式就是判据本身：True=已过期=有问题） ----
    expect("R1b 依据仍未补上（登记合理，放行）",
           _is_stale_no_evidence(["def f():\n    return None\n"], 0), False)
    expect("R1b 依据后来补上了（陈旧登记，抓到）",
           _is_stale_no_evidence(["def f():\n    return 0\n"], 0), True)
    expect("R1b 依据在第二个证据文件里补上（陈旧登记，抓到）",
           _is_stale_no_evidence(["x = 1\n", "sys.exit(0)\n"], 0), True)
    expect("R1b 只有 return 0.0（不是依据，放行）",
           _is_stale_no_evidence(["def f():\n    return 0.0\n"], 0), False)

    # ---- R3：骨架识别 ----
    # 注意：图示要求「≥3 行、每行 ≥3 个框线字符」，中段那行只有两个角标是不够的。
    good_doc = ("用法：\n    python x.py a --b\n\n"
                "    ┌──────┐\n    │ 一步 │────\n    └──────┘\n\n"
                "退出码：\n    0  = 好\n")

    def skeleton_problem(doc):
        return (not has_example(doc, "x.py") or not has_diagram(doc)
                or parse_exit_section(doc) is None)

    expect("R3 好文档（示例+图示+退出码）", skeleton_problem(good_doc), False)
    expect("R3 缺示例（裸 python，无脚本名）",
           skeleton_problem("用法：\n    python\n\n退出码：\n    0  = a\n"), True)
    expect("R3 缺图示（只有一行框线）",
           skeleton_problem("用法：\n    python x.py a\n\n    ┌──────┐\n\n"
                            "退出码：\n    0  = a\n"), True)
    expect("R3 图示不足（每行框线字符 <3）",
           skeleton_problem("用法：\n    python x.py a\n\n"
                            "    ┌─┐\n    │ │\n    └─┘\n\n退出码：\n    0  = a\n"),
           True)

    # ---- R4：示例可真跑（判定用纯函数测；真起进程的只有一条真实性样本） ----
    expect("R4 正例 rc=0 + 有输出（放行）",
           _r4_verdict("x.py", "x.py", ["--help"], 0, b"usage: x", False) is not None,
           False)
    expect("R4 反例 rc=2（抓到）",
           _r4_verdict("x.py", "x.py", ["--help"], 2, b"usage", False) is not None,
           True)
    expect("R4 反例 rc=0 但零输出（抓到）",
           _r4_verdict("x.py", "x.py", ["--help"], 0, b"", False) is not None,
           True)
    expect("R4 反例 永不退出 rc=None（抓到）",
           _r4_verdict("x.py", "x.py", ["--help"], None, b"", False) is not None,
           True)
    expect("R4 正例 按设计零输出（expect_blank，放行）",
           _r4_verdict("x.py", "x.py", ["--help"], 0, b"", True) is not None,
           False)
    expect("R4 反例 按设计零输出却输出了（抓到）",
           _r4_verdict("x.py", "x.py", ["--help"], 0, b"oops", True) is not None,
           True)

    # 真实性样本：真起一次子进程，证明 _run_safe_example 在真实环境下也守纪律
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        ok_py = os.path.join(td, "ok_script.py")
        with io.open(ok_py, "w", encoding="utf-8") as fh:
            fh.write("import sys\nprint('usage: ok')\nsys.exit(0)\n")
        rc_ok, out_ok = _run_safe_example(td, "ok_script.py", ["--help"])
        expect("R4 真实子进程 rc=0 且有输出（放行）",
               _r4_verdict("ok", "ok_script.py", ["--help"], rc_ok, out_ok, False)
               is not None, False)

        loop_py = os.path.join(td, "loop_script.py")
        with io.open(loop_py, "w", encoding="utf-8") as fh:
            fh.write("import time\ntime.sleep(3600)\n")
        global RUN_TIMEOUT
        saved = RUN_TIMEOUT
        RUN_TIMEOUT = 2.0
        rc_to, out_to = _run_safe_example(td, "loop_script.py", ["--help"])
        RUN_TIMEOUT = saved
        expect("R4 真实子进程 永不退出 → 超时判红",
               _r4_verdict("loop", "loop_script.py", ["--help"], rc_to, out_to,
                           False) is not None, True)

    # ---- R5：帮助体积棘轮（两臂取严；纯函数判定，不起进程） ----
    # 臂 A：绝对界
    expect("R5 正常体积（放行）",
           _r5_verdict("x.py", 5000, 400, 16384, None) is not None, False)
    expect("R5 低于绝对下界（抓到）",
           _r5_verdict("x.py", 100, 400, 16384, None) is not None, True)
    expect("R5 高于绝对上界（抓到）",
           _r5_verdict("x.py", 99999, 400, 16384, None) is not None, True)
    # 臂 B：漂移带。这条是 R38 新加的核心 —— 它必须在**绝对界毫无反应**时抓住。
    expect("坏样本：绝对界无反应但漂移带抓到膨胀",
           _r5_verdict("x.py", 3000, 400, 16384, 1000) is not None, True)
    expect("坏样本：漂移带抓到缩水",
           _r5_verdict("x.py", 1000, 400, 16384, 2000) is not None, True)
    # R64/C13-9：容差从 max(30%, 512) 换成**绝对字节带** HELP_DRIFT_BYTES。
    # 下面两条在旧带下是**正例**，在新带下必须变**反例** —— 这就是「分辨率提高」
    # 被自证抓到的那一刻（旧带对 matlabc.py 是 15135 B）。
    expect("坏样本：+250 B（旧 ±30% 会放行）现在必须抓到",
           _r5_verdict("x.py", 1250, 400, 16384, 1000) is not None, True)
    expect("坏样本：+400 B（旧 512 B 宽容会放行）现在必须抓到",
           _r5_verdict("x.py", 1400, 400, 16384, 1000) is not None, True)
    expect("好样本：恰好 +HELP_DRIFT_BYTES（带边界，放行）",
           _r5_verdict("x.py", 1000 + HELP_DRIFT_BYTES, 400, 16384, 1000)
           is not None, False)
    expect("坏样本：+HELP_DRIFT_BYTES+1（越界 1 字节，抓到）",
           _r5_verdict("x.py", 1001 + HELP_DRIFT_BYTES, 400, 16384, 1000)
           is not None, True)
    expect("好样本：无快照 = 只有绝对界",
           _r5_verdict("x.py", 9999, 400, 16384, None) is not None, False)
    expect("好样本：(0,0) = 显式不设界（stdio server 放行）",
           _r5_verdict("x.py", 999999, 0, 0, 0) is not None, False)

    # ---- R5c：规范形（容差 0，分辨率 1 字节） ----
    # _H310 / _H313 是**同一件事**的两种 argparse 渲染（3.10 会多印一行 metavar）。
    _H310 = (b"  -o OUTPUT, --output OUTPUT\r\n"
             b"                        output path\r\n")
    _H313 = b"  -o, --output OUTPUT   output path\r\n"
    expect("R5c 好样本：3.10 与 3.13 的两种渲染折成同一个规范形",
           _canon_help(_H310) != _canon_help(_H313), False)
    expect("R5c 好样本：同一个规范形两次相等（放行）",
           _r5c_verdict("x.py", len(_canon_help(_H313)),
                        len(_canon_help(_H313))) is not None, False)
    expect("R5c 坏样本：内容差 1 字节必须抓到",
           _r5c_verdict("x.py", len(_canon_help(_H313)) + 1,
                        len(_canon_help(_H313))) is not None, True)
    expect("R5c 好样本：无快照 = 不判",
           _r5c_verdict("x.py", 123, None) is not None, False)
    expect("R5c 好样本：折行位置不同 ⇒ 规范形相同（布局不算内容）",
           _canon_help(b"aaa bbb\r\nccc ddd\r\n")
           != _canon_help(b"aaa bbb ccc ddd\r\n"), False)

    # ---- R64/C13-9：钉死 COLUMNS 的前后两向实测（真起子进程，不靠读代码） ----
    import tempfile as _tf64
    with _tf64.TemporaryDirectory() as _wtd:
        with io.open(os.path.join(_wtd, "w.py"), "w", encoding="utf-8") as _fh:
            _fh.write("import os\n"
                      "print('C=' + os.environ.get('COLUMNS', 'unset'))\n")
        _saved_cols = os.environ.get("COLUMNS")
        os.environ["COLUMNS"] = "200"
        try:
            _rc_l, _leak = _run_safe_example(_wtd, "w.py", [])
            _rc_p, _pin = _run_safe_example(
                _wtd, "w.py", [], env_extra={"COLUMNS": "80"})
        finally:
            if _saved_cols is None:
                os.environ.pop("COLUMNS", None)
            else:
                os.environ["COLUMNS"] = _saved_cols
    # 反例：不钉 env 时调用方的 COLUMNS **真的会漏**进子进程（差异是实的）
    expect("R64 反例：不钉 env 时子进程继承了调用方的 COLUMNS（漏是真的）",
           b"C=200" in _leak, True)
    # 正例：钉了 env_extra 之后子进程只看得到钉死值 ⇒ 判据「钉死没生效」为 False。
    # 注意方向：expect 的第二个参数是**判据的检测结果**，不是「我的断言成立」
    # —— 首版写成 `b"C=80" in _pin`，于是它报「抓到」而期望「放行」，自证当场变红。
    expect("R64 正例：钉 env_extra 后子进程看到的是钉死值",
           b"C=80" not in _pin, False)

    # ---- C'7：护栏退出码契约（真实仓库核对已覆盖；再补一条纯函数反例） ----
    import tempfile as _tf
    with _tf.TemporaryDirectory() as gtd:
        gdir = os.path.join(gtd, "tools")
        os.makedirs(gdir)
        # 好样本：登记 {0,1,2}，源码有依据，帮助声明齐全
        with io.open(os.path.join(gdir, "check_ok.py"), "w", encoding="utf-8") as fh:
            fh.write('"""x\n\n退出码：\n    0 = a\n    1 = b\n    2 = c\n"""\n'
                     "import sys\n"
                     "def main():\n    return 0\n"
                     "sys.exit(main())\n")
        # 坏样本：帮助声明 {0,1,2} 但源码里根本没有 return 1/2 的依据
        with io.open(os.path.join(gdir, "check_bad.py"), "w", encoding="utf-8") as fh:
            fh.write('"""x\n\n退出码：\n    0 = a\n    1 = b\n    2 = c\n"""\n'
                     "import sys\n"
                     "def main():\n    return 0\n"
                     "sys.exit(main())\n")
        # 用临时登记表核对（不改动全局 GUARD_CONTRACT）
        saved = dict(GUARD_CONTRACT)
        saved_scripts = GUARD_SCRIPTS
        try:
            GUARD_CONTRACT.clear()
            GUARD_CONTRACT.update({
                "tools/check_ok.py": {0: "a", 1: "b", 2: "c"},
                "tools/check_bad.py": {0: "a", 1: "b", 2: "c"},
            })
            globals()["GUARD_SCRIPTS"] = tuple(sorted(GUARD_CONTRACT))
            gb = []
            audit_guards(gtd, on_problem_collector(gb))
            # check_bad 缺 1/2 的依据 → 一定有问题；check_ok 也有同样问题（缺 1/2），
            # 所以这里断言的是「判据确实能对'缺依据'报问题」，而不是只报 0 个。
            expect("C'7 护栏缺退出码依据（抓到）",
                   any("check_bad.py" in x and "找不到依据" in x for x in gb), True)
            # R63/G0b：磁盘上**存在却没登记**的护栏也必须被抓到
            with io.open(os.path.join(gdir, "check_orphan.py"), "w",
                         encoding="utf-8") as fh:
                fh.write('"""x\n\n退出码：\n    0 = a\n"""\n'
                         "import sys\n"
                         "def main():\n    return 0\n"
                         "sys.exit(main())\n")
            gb2 = []
            audit_guards(gtd, on_problem_collector(gb2))
            expect("R63 G0b 存在却未登记的护栏（抓到）",
                   any("check_orphan.py" in x and "没有登记它" in x
                       for x in gb2), True)
        finally:
            GUARD_CONTRACT.clear()
            GUARD_CONTRACT.update(saved)
            globals()["GUARD_SCRIPTS"] = saved_scripts

    # ---- R39（C''9）：ci-examples 退出码契约（纯函数 + 临时文件，不起进程） ----
    with _tf.TemporaryDirectory() as ctd:
        cdir = os.path.join(ctd, "ci-examples")
        os.makedirs(cdir)
        # 好样本：Python 侧有依据 + 帮助声明齐全；shell 侧 `exit N` 齐全
        with io.open(os.path.join(cdir, "ok.py"), "w", encoding="utf-8") as fh:
            fh.write('"""x\n\n退出码：0 = a；1 = b\n"""\n'
                     "def main():\n    return 0\n"
                     "def main2():\n    return 1\n")
        with io.open(os.path.join(cdir, "ok.sh"), "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\ncd /x || exit 1\nexit 0\n")
        # 坏样本：帮助声明 {0,1,2}，源码只 return 0（缺 1/2 依据）；
        # 且 shell 里出现 `exit 7` 却没登记
        with io.open(os.path.join(cdir, "bad.py"), "w", encoding="utf-8") as fh:
            fh.write('"""x\n\n退出码：0 = a；1 = b；2 = c\n"""\n'
                     "def main():\n    return 0\n")
        with io.open(os.path.join(cdir, "bad.sh"), "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\nexit 0\nexit 7\n")

        saved_py = dict(CI_PY_EXIT_CONTRACT)
        saved_sh = dict(CI_SH_EXIT_CONTRACT)
        saved_nz = dict(CI_RELIES_ON_NONZERO)
        try:
            CI_PY_EXIT_CONTRACT.clear()
            CI_PY_EXIT_CONTRACT.update({
                "ci-examples/ok.py": {0: "a", 1: "b"},
                "ci-examples/bad.py": {0: "a", 1: "b", 2: "c"},
            })
            CI_SH_EXIT_CONTRACT.clear()
            CI_SH_EXIT_CONTRACT.update({
                "ci-examples/ok.sh": {0: "a", 1: "b"},
                "ci-examples/bad.sh": {0: "a"},
            })
            CI_RELIES_ON_NONZERO.clear()
            cb = []
            audit_ci_examples(ctd, on_problem_collector(cb), {0, 1, 2})
            expect("C''9 坏样本：Python 侧缺依据（抓到）",
                   any("bad.py" in x and "找不到依据" in x for x in cb), True)
            expect("C''9 坏样本：shell 侧未登记的 `exit 7`（抓到）",
                   any("bad.sh" in x and "没登记" in x for x in cb), True)
            expect("C''9 好样本：登记齐全不得误伤",
                   any("ok.py" in x or "ok.sh" in x for x in cb), False)

            # 前提失效：matlabc 退出契约里没有非零码 → 「非零退出」这句话就是谎言
            CI_RELIES_ON_NONZERO.clear()
            CI_RELIES_ON_NONZERO.update({"ci-examples/ok.py": "非零退出"})
            with io.open(os.path.join(cdir, "ok.py"), "a", encoding="utf-8") as fh:
                fh.write("# 门禁 FAIL 会非零退出\n")
            cb2 = []
            audit_ci_examples(ctd, on_problem_collector(cb2), {0})
            expect("C''9 坏样本：模板断言非零退出但 matlabc 只有 0（抓到）",
                   any("没有任何非零码" in x for x in cb2), True)
            cb3 = []
            audit_ci_examples(ctd, on_problem_collector(cb3), {0, 1})
            expect("C''9 好样本：matlabc 有非零码则放行",
                   any("没有任何非零码" in x for x in cb3), False)
            # 陈旧登记：模板里已经没有那句话了
            CI_RELIES_ON_NONZERO.clear()
            CI_RELIES_ON_NONZERO.update({"ci-examples/bad.py": "非零退出"})
            cb4 = []
            audit_ci_examples(ctd, on_problem_collector(cb4), {0, 1})
            expect("C''9 坏样本：模板已改口而登记未更新（抓到）",
                   any("已经没有这句话" in x for x in cb4), True)
        finally:
            CI_PY_EXIT_CONTRACT.clear()
            CI_PY_EXIT_CONTRACT.update(saved_py)
            CI_SH_EXIT_CONTRACT.clear()
            CI_SH_EXIT_CONTRACT.update(saved_sh)
            CI_RELIES_ON_NONZERO.clear()
            CI_RELIES_ON_NONZERO.update(saved_nz)

    # ---- R41：散文里的数字（纯函数，不起进程、不读文件） ----
    expect("R41 坏样本：写 7 而实际 9（抓到）",
           bool(doc_number_problems("一次跑完 7 道登记制护栏", 9)), True)
    expect("R41 坏样本：英文 8 gates 而实际 9（抓到）",
           bool(doc_number_problems("# what each of the 8 gates stops", 9)), True)
    expect("R41 好样本：数字正确（放行）",
           bool(doc_number_problems("一次跑完 9 道登记制护栏", 9)), False)
    # 左边界：`3.6.5 gate` / `P203 gate` 必须**不**被当成宣称
    expect("R41 好样本：3.6.5 gate 不是宣称（放行）",
           bool(doc_number_problems("feeds sources to its own 3.6.5 gate", 9)), False)
    expect("R41 好样本：P203 gate 不是宣称（放行）",
           bool(doc_number_problems("the P203 gate writes SARIF", 9)), False)

    # ---- R42：历史引用的行内豁免标记（纯函数） ----
    # 场景就是 R41 上线后立刻发生的真实情况：解释该规则的散文里引用了旧值。
    _hist = ("4. 散文里的数字也是宣称。旧帮助曾写 7 道护栏。"
             "<!-- guard-count:historical R41 举例引用旧值 -->")
    expect("R42 好样本：带理由的历史引用被豁免（放行）",
           bool(doc_number_problems(_hist, 9)), False)
    expect("R42 好样本：豁免不算作陈旧标记（放行）",
           bool(num_exempt_problems(_hist, 9)), False)
    expect("R42 坏样本：同一行**不带**标记就必须抓到",
           bool(doc_number_problems(_hist.split("<!--")[0], 9)), True)
    # 反向约束一：理由太短 → 抓（否则一个字符就能永久关掉一行）
    expect("R42 坏样本：豁免理由只有 1 个字符（抓到）",
           any("N4" in x for x in num_exempt_problems(
               "旧帮助曾写 7 道护栏 <!-- guard-count:historical x -->", 9)), True)
    expect("R42 好样本：理由正好达到下限（放行）",
           bool(num_exempt_problems(
               "旧帮助曾写 7 道护栏 <!-- guard-count:historical 01234567 -->", 9)),
           False)
    # 反向约束二：陈旧标记 → 抓（那一行本来就不违规）
    # ⚠ 样本的理由必须**达到长度下限**，否则会先触发 N4、N3 根本没机会跑
    #   —— 首版样本写的是「历史引用」（4 字符），自证立刻把它抓了出来。
    _r = "R42 举例引用旧值"
    expect("R42 坏样本：标记挂在一行没有数字的话上（陈旧，抓到）",
           any("N3" in x for x in num_exempt_problems(
               "这段没有数字 <!-- guard-count:historical " + _r + " -->", 9)),
           True)
    expect("R42 坏样本：标记挂在数字本来就对的行上（陈旧，抓到）",
           any("N3" in x for x in num_exempt_problems(
               "一次跑完 9 道护栏 <!-- guard-count:historical " + _r + " -->",
               9)), True)
    # 豁免标记必须**同行**生效：上一行的标记救不了下一行的错数字
    # （这里也必须用合格长度的理由，否则测到的是 N4 而不是"同行"语义）
    expect("R42 坏样本：标记在上一行，下一行的错数字照样抓到",
           bool(doc_number_problems(
               "<!-- guard-count:historical " + _r + " -->\n旧帮助曾写 7 道护栏",
               9)), True)

    # ---- R51：诚实的边界逐字契约（纯函数；真实正文既作正例、又作登记对象） ----
    _bd = _docstring(os.path.join(repo_root(), "matlabc.py"))[1]
    expect("R51 好样本：真实帮助正文与登记表互为对手方（放行）",
           bool(boundary_verdict(_bd, BOUNDARY_CLAIMS)[0]), False)
    expect("R51 坏样本：动态库那条被抹掉 `ltrace`（B3 抓到）",
           any(x.startswith("B3") for x in
               boundary_verdict(_bd.replace("ltrace", "LTRACE"),
                                BOUNDARY_CLAIMS)[0]), True)
    expect("R51 坏样本：小节里多出一条未登记的边界（B1 抓到）",
           any(x.startswith("B1") for x in boundary_verdict(
               _bd.replace("  * GPU：CUDA", "  * 新边界：不做\n  * GPU：CUDA", 1),
               BOUNDARY_CLAIMS)[0]), True)
    expect("R51 坏样本：登记了一条已不存在的边界（B2 抓到）",
           any(x.startswith("B2") for x in boundary_verdict(
               _bd, tuple(BOUNDARY_CLAIMS) + (
                   {"head": "早已删除的边界：", "help_must": (),
                    "reason": "用来测陈旧登记必须被抓出来"},))[0]), True)
    expect("R51 坏样本：理由只有 1 个字符（B4 抓到）",
           any(x.startswith("B4") for x in boundary_verdict(
               _bd, tuple({"head": c["head"], "help_must": c["help_must"],
                           "reason": "短"} for c in BOUNDARY_CLAIMS))[0]), True)
    expect("R51 坏样本：帮助里没有「诚实的边界」小节（B0 抓到）",
           any(x.startswith("B0") for x in
               boundary_verdict("# 没有这一节\n", BOUNDARY_CLAIMS)[0]), True)

    # ---- 真实仓库整体核对 ----
    root = repo_root()
    probs = []
    cache = {}
    n = audit(root, on_problem_collector(probs), cache=cache)
    ng = audit_guards(root, on_problem_collector(probs))
    nc = audit_ci_examples(root, on_problem_collector(probs),
                           set(CONTRACT.get("matlabc.py", {}).get("codes", {})))
    nd, n_ex = audit_doc_numbers(root, on_problem_collector(probs))
    nb, nbd = audit_boundary(root, on_problem_collector(probs))
    print("  真实仓库：核对 %d 个入口脚本 + %d 个护栏脚本 + %d 个 CI 模板/示例"
          " + %d 份文档数字（其中 %d 处为显式豁免的历史引用）+ %d 条边界承诺"
          "（%d 份文档同源核对），发现 %d 项不一致"
          % (n, ng, nc, nd, n_ex, nb, nbd, len(probs)))
    for p in probs[:12]:
        print("      " + p)
    if len(probs) > 12:
        print("      ...（还有 %d 项）" % (len(probs) - 12))
    if probs:
        fails.append("真实仓库")
        bad += 1
    else:
        good += 1

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    if fails:
        print("SELFTEST FAILED: %s" % fails)
        return 1
    print("SELFTEST PASSED")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()

    root = repo_root()
    if not os.path.isdir(os.path.join(root, "tools")):
        print("check_help_contract: 找不到 tools/（缺输入 → 红）")
        return 2
    probs = []
    n = audit(root, on_problem_collector(probs), cache={})
    ng = audit_guards(root, on_problem_collector(probs))
    nc = audit_ci_examples(root, on_problem_collector(probs),
                           set(CONTRACT.get("matlabc.py", {}).get("codes", {})))
    nd, n_ex = audit_doc_numbers(root, on_problem_collector(probs))
    nb, nbd = audit_boundary(root, on_problem_collector(probs))
    if n == 0:
        print("check_help_contract: 一个入口脚本都没核对到（缺输入 → 红）")
        return 2
    if nb == 0:
        print("check_help_contract: 帮助正文里找不到「诚实的边界」小节"
              "（缺输入 → 红）")
        return 2
    if probs:
        print("check_help_contract: %d 项不一致" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_help_contract: OK（%d 个入口脚本 + %d 个护栏脚本 + %d 个 CI 模板/示例"
          "的退出码在代码与帮助之间双向一致；%d 份文档里的「N 道护栏」数字与事实"
          "一致（其中 %d 处为带理由的显式历史引用豁免，理由过短或陈旧的标记也会"
          "被反向抓出）；入口帮助骨架齐备；%d 条示例命令已真跑且 rc=0；"
          "「诚实的边界」%d 条承诺与登记表逐字互为对手方（%d 份文档同源核对）；"
          "帮助体积三臂（绝对界 / 漂移带 ±%d B / 规范形容差 0）在钉死 %d / %d 列下"
          "实测；判据族 %s）"
          % (n, ng, nc, nd, n_ex, len(RUNNABLE), nb, nbd,
             HELP_DRIFT_BYTES, HELP_MEASURE_COLUMNS, HELP_CANON_COLUMNS,
             ROW_SIGNATURE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
