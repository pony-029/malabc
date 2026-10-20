# -*- coding: utf-8 -*-
"""一键跑完所有登记制静态护栏。

一图看懂：

    python tools/check_all.py
        │
        ├─▶ check_baseline.py             公平基线：按 nodeid 集合比失败（--full 才真跑）
        ├─▶ check_binfmt_fixtures.py      合成夹具 + 契约 C1..C15 + 两向自证
        ├─▶ check_doc_flags.py            文档/帮助里写的 CLI 开关必须真的存在
        ├─▶ check_flow_diagrams.py        图的引用 ↔ 文件 ↔ 候选声明，两两对齐且双向
        ├─▶ check_help_contract.py        退出码在代码↔帮助双向一致；示例能真跑
        ├─▶ check_boundary_reverse.py     「诚实的边界」每条承诺都要有对手方（契约 V1..V6 + 两向自证）
        ├─▶ check_import_graph.py         模块级 import 必须无环；回边只能走登记过的惰性通道
        ├─▶ check_c_frontend_shapes.py    C 前端函数定义形态（四形态/指针返回/体界/行号）+ 调用关系有界投影（**节点身份=定义落点**，R88）+ **解析阶梯**（同文件优先 → `#include` 闭包三明治，`under` 唯一性按**解析目标数**判，R89/R89k）+ 属性说明符不是定义也不是调用，各有对手方
        ├─▶ check_py_js_frontend_shapes.py Python/JS 前端形态（单行/async/注解/跨行/箭头）各有对手方
        ├─▶ check_incremental_parity.py   增量重算必须与全量**逐项相同**（逐文件各测一次）
├─▶ check_ir_attribution.py       「解析不到的调用」只有一个判定点，归因吃的就是它
        ├─▶ check_operator_impl.py        算子元表里不得有「只声明不产出」的幻影
        ├─▶ check_patch_ops.py            补丁编辑算子唯一事实源（禁止覆盖式赋值）
        ├─▶ check_py36_clean.py           本仓源码必须通过本仓自己的 3.6.5 门
        ├─▶ check_flag_coverage.py        sweep_cli 的每个开关都必须被读到（功能加了要有判据）
        ├─▶ check_tool_discoverability.py tools/ 下每个非护栏工具都要在两侧 README 出现
        ├─▶ check_js_balance.py           vscode 下 JS 必须括号配平（这台机器没有 node）
        ├─▶ check_matlab_grammar.py       MATLAB 语法：转置不开启字符串、%{ 必须独占一行
        ├─▶ check_lsp_doc_parity.py       LSP 能力表 ⇄ 代码实现的 textDocument/* 双向一致
        ├─▶ check_readme_parity.py        中英 README 逐节结构对等
        ├─▶ check_known_red.py            「永久红」必须两向登记在册，红集只缩不长
        ├─▶ check_legal_parity.py        许可与署名双轨：MIT 正文 ⇄ 版权人 ⇄ 必究 ⇄ 徽章 ⇄ 版本
        ├─▶ check_unified_graph.py       统一图四条恒等式 + T1 图前提（含「注入一条边即破」）
        ├─▶ check_kernel_snapshot.py     全树规模读数 + 分析流程登记（契约 W1..W7）
        ├─▶ check_subprocess_hygiene.py   子进程必须切 stdin 且不会永久挂住
        ├─▶ check_parity_registry.py     能力对等登记表（16 能力 × 4 语言）必须与**实测**一致，两向（E1–E6）
        ├─▶ check_browse_clean_manifest.py  `--browse` 清理清单 ⇄ 代码生成点两向对账（M1–M3；起因为 R99「声明改了、diff 里没有」）
        ├─▶ check_flow_figures.py         `flow/index.html` ⇄ `flow/figures/` ⇄ 候选三向对齐 + 图不过期 + 回执同源（FF1–FF7；单语交互图的门）
        ├─▶ check_facts_replay.py         事实重放 == 报表计数 + 位置完备 + 种类封闭（FT1–FT3；facts 层的门）
        ├─▶ check_portability.py          运行时不得假设只有 Windows（契约 PF1..PF3）
        ├─▶ check_tour.py                 导览页：分帧引用 / 端点穿框 / 换行（契约 TR1..TR3）
        ├─▶ check_figure_glyphs.py       示意图的字形：缺字形画成方块 / 等宽行不许中文（契约 FG1..FG4）
        ├─▶ check_release_gates.py        发版门清单：写了没进 GATES 的门 / 陈旧豁免（契约 RG1..RG2）
        ├─▶ check_symbol_ranges.py        符号行号必须在文件内：越界会让大纲永远转圈（契约 SR1..SR2）
        ├─▶ check_version_scheme.py       版本号规则：每位 0–9，满 10 进位（契约 VS1..VS2）
        └─▶ check_eol_convention.py       行尾约定（EO1–EO3；手写物 CRLF / 生成物 LF / 扫描面下界）
        │
        ├─ 仓级闸门 [R106]：计划块 `action` 必须 ∈ 在册动作 ∪ `-`（在册动作由摘要文件**现算**，
        │                   `-` 必须写 `blocked_reason`，在册动作不许带理由 —— 环路的归因错与
        │                   「计划读数与实际不符」各有一个对手方）
        ├─ 仓级闸门 [R106/R107]：**全仓** `*.md`（跳过登记目录）的代码围栏结构
        │                   （零长度代码块 / 奇数围栏；下界 85 份 ⇒ 扫描面缩回也红）
        │
        ├─ 每道护栏都要能跑通（rc=0）
        ├─ 每道护栏都要有 --selftest（两向自证：坏样本要红、好样本要过）
        ├─ 门数不得少于 MIN_GUARDS（R33/C'9：删掉一道门也会变红）
        ├─ 每个子进程都 stdin=DEVNULL + 墙钟超时（挂死 → 判红，不让门永远等）
        └─ 显式 --with-tests 时**再跑整套 tests/**，与 docs/TEST_BASELINE.json 两向核对
           （**独立行使**：护栏红也照跑 —— 否则它会被别人的红整个挡住，
            而这种「静默失效」与没有这条判据只差一层错觉；R102 实测修掉）
        │
        ▼
    0 = 全绿   1 = 有护栏失败/缺自证/门数不足/**测试基线不合**/**仓级闸门红**
    2 = 找不到护栏（缺输入 → 红）

为什么需要它：护栏分散成多个 `tools/check_*.py`，靠人记得逐个跑等于没有门。
本 runner 与 `tests/test_matlabc.py::test_r30_static_guards_all_clean` 是同一
判据的两个入口 —— 前者给 CI/人手，后者保证「新加的护栏会被自动收进测试」。

它自己也必须**能红**：`--selftest` 用临时目录造样本，证明
「坏护栏会被抓、好护栏会被放、缺自证的护栏会被抓、空目录会红、
**永不退出的护栏会被超时判红**、**门数少于下限会被判红**」；
R106 起还包括两个仓级结构闸门的样本 —— **计划块**（动作拼错 / `-` 无理由 /
在册动作带理由 / 摘要 `actions` 为空 / 列数不足 / 找不到块）与**围栏结构**
（零长度代码块 / 奇数围栏 / 「关旧块+开新块」相邻必须放行），缺一个样本都算退化。
一个只会在好天气下变绿的 runner，本身也是一道假门；
一条会**永远挂住**的链比一道闸门更糟 —— 所以每个子进程都带 `stdin=DEVNULL`
与墙钟超时（见 `_run` 的注释：这是 R62-R31e 修掉的一个真缺陷）。

用法：
    python tools/check_all.py                 # 跑 tools/ 下全部护栏
    python tools/check_all.py --tools-dir D   # 指定护栏目录（自证/CI 复用）
    python tools/check_all.py --selftest      # 自证：双向验证本 runner
    python tools/check_all.py --with-tests    # 完整门禁：再跑全套 tests/ 并核对基线（≈35 分钟；
                                              #   与护栏判据独立结算，护栏红也照跑）
                                              #   ⚠ 必须用**录制基线时的那个解释器**跑 ——
                                              #   基线记的是版本串（现为 3.10.10）；换解释器会判红，
                                              #   那是「读数不可比」，不是测试退化
    python tools/check_all.py --help          # 显示本帮助（立即返回，不跑护栏）

退出码：
    0  = 全部护栏通过（且各自自证通过）；`--with-tests` 时还要求整套 tests/ 与基线一致
    1  = 有护栏失败，或护栏缺自证（`SELFTEST COUNTS` 行缺失 / 格式非法），或门数少于下限，或（`--with-tests` 时）整套 tests/ 与基线不符（红数变多/变少、通过数掉出容差、换解释器、取不到汇总行全部判红），或（`--with-tests` 时）余量侧信道坏（坏记录 / 有调用点却零记录），或**仓级结构闸门红**（计划块 `action` 不在册 / `-` 没写理由 / 在册动作带理由 / 文档出现零长度代码块或奇数围栏 / 闸门缺输入）；各条判据**独立结算**——任一条红都不挡住其余各条的读数
    2  = 找不到护栏（--tools-dir 下没有 check_*.py → 缺输入，红）
"""
import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

R_BAD_GUARD = """import sys
print("[FAIL] 样本护栏：故意失败")
sys.exit(1)
"""

R_GOOD_GUARD = """import sys
print("check_ok: OK")
if "--selftest" in sys.argv:
    print('SELFTEST COUNTS {"bad": 0, "good": 1}')
sys.exit(0)
"""

R_NO_SELFTEST_GUARD = """import sys
print("check_noself: OK")
sys.exit(0)
"""

R_HANG_GUARD = """import time
print("check_hang: 我永远不退出", flush=True)
time.sleep(3600)
"""

# 单个护栏的墙钟上限。存在意义：**让挂死变成红，而不是让门永远等着**。
# 实测全部护栏各自 <2s，600s 是给未来重护栏留的量级余量。
GUARD_TIMEOUT = 600.0

# R33/C'9：**门数棘轮**。只断言 rc=0 是不够的 —— 一个护栏被误删（或改名、
# 或移动目录）之后，剩下的门依然全绿，rc 依然是 0，于是「门少了」这件事
# 静默通过。这里登记「本仓自带护栏的下界」，删掉任何一道都会立刻变红。
# 数字含义：截至 R44，tools/ 下有 10 道 check_*.py（不含本 runner）。
# R36 新增 check_baseline.py（C''7：把公平基线做成可重跑的门），故 8 → 9。
# R44 新增 check_ir_attribution.py（C'''1：把「解析不到的调用只有一个判定点、
# 且归因吃到的是它」钉成全仓集合判据），故 9 → 10。
# R47 新增 check_flow_diagrams.py（把 README 里嵌的图 ↔ flow/diagrams/ 的文件 ↔
# candidate*.json 的声明 ↔ 交互产物 ↔ FLOW_INDEX.json 索引 ↔ SVG 自身形态（尺寸/字体/语言）
# 六条来源钉成 D1–D12、
# 每对双向），故 10 → 11。
# R52 新增 check_import_graph.py（把 renderers ↔ matlabc 的 **import 期回边**打断：
# 借用改走 renderers/_late.py 的惰性代理；此后「模块级 import 图无环」由 G1 钉住，
# 惰性环与动态 import 走登记 + 两向核对），故 11 → 12。
# R55 新增 check_boundary_reverse.py（把「诚实的边界」里的承诺接上一台能说「不」的
# 判据：承诺 ⇄ 判据 两向核对 + 公开 CLI 行为判据 + 棘轮），故 12 → 13。
# R56 没有加门，只把那道门的 V1 准入条件从「含否定标记词」放宽为「**每一条**
# bullet」，并补上覆盖数棘轮 —— 于是 `* Mach-O：` 那种一个标记词都没有的
# **状态声明**也不再能整条溜过去（R55 §8 C10-7）。门数不变，仍是 13。
# 新增护栏时**必须**同步上调这个数字 —— 这正是棘轮的作用。
# R61 新增 check_c_frontend_shapes.py（R49 §8 C'''''1：把 C 前端的
# 「函数定义形态」判据从仓库外 `_r49/` 固化进仓库 —— 四形态 / 指针返回类型 /
# 值域 / 字符串花括号不干扰体界 / 声明起点行号 / 不假阳且已披露边界保持不识别，
# 六条判据互不重叠、各有突变体；另加夹具完备性与五个棘轮），故 13 → 14。
# R63 新增 check_known_red.py（C13-0：把 tests/ 里「引用了从未提交的产物」
# 因而常红的那批测试做成**两向登记** —— 产物必须真的不存在（K2）、扫描到的
# 引用集合必须恰好等于登记集合（K1）、理由必须具名（K3）、「优雅跳过」必须
# 源码里真有 pytest.skip（K4）、单段 os.path.join 指向的新缺口也要登记（K5），
# 另登记一个负样本。至此「红变成背景色、真红没人看见」第一次有了对手方），
# 故 14 → 15。
# R66 新增 check_py_js_frontend_shapes.py（R64 §8 C14-1 之外的一条：R66 实测
# Python / JS 前端 8+10 个真实形态里漏 4+8 个，且形参表里的嵌套括号会被
# `\(([^)]*)\)` 截断；修完之后把判据固化进仓库 —— G1–G6 六条互不重叠、
# 各有突变体，另加夹具完备性与棘轮），故 15 → 16。
# R67 没有加门：给 `check_py_js_frontend_shapes.py` 补了判据 G7（不**过度**识别 —— 字符串 / 注释 / 模板串里
# 独占一行的定义必须不被认出），并给 py / js 扫描器（`_scan_py_defs` / `_scan_js_defs`）
# 加了字符串 / 注释状态机（`_py_code_mask` / `_js_code_mask`）。基线与复量见
# `docs/SUPERPOWER_REVIEW_R67.md`。门数不变，仍是 16。
# R68 没有加门：把 Mach-O 的依赖指令 / 符号表与库名家族归一接上，
# 判据族 C1–C9 → C1–C12。门数不变，仍是 16。
# R69 新增 check_legal_parity.py（许可从「MIT」改成「**双轨**：代码 MIT +
# 品牌必究」，而此前**没有任何门看过 LICENSE 的正文** —— GitHub 的
# licensee 靠正文识别，一句「顺手润色」就能把 README 上那枚 license-MIT
# 徽章变成假话；本轮还量出 README 双侧的版本徽章写 1.16.71 而
# VERSION 已是 1.16.72。L1–L7 七条互不重叠、各有突变体），故 16 → 17。
# R71 没有加门：给 `check_binfmt_fixtures.py` 补判据族 C13（fat/universal Mach-O
# **逐片**解析 —— 依赖/符号/段表都要从每一片读、同名片去重且点名、片内偏移重基、
# 读不懂的片必须被点名、GPU 段名提示不被 `slice[i]:` 前缀打瞎），
# 判据族 C1–C12 → C1–C13。门数不变，仍是 16。
# R86-2 也没有加门：给 `check_binfmt_fixtures.py` 补判据族 C14/C15
# （C14 引用解析：库名 → 磁盘文件 → 沿依赖逐层下钻；三态 + 环必须终止 + 上限触发必须是
# skipped 而不是 not_found + not_found 必带 searched + 32/64 位孪生按**候选自己的位数**
# 消歧且排除项留在 rejected + 同位数两份必须 ambiguous；
# C15 PE 缓解措施为 observed 档、与 ELF 的 inferred **并存**、None≠False、
# PE 无 RELRO/exec-stack 一律置 null、LOAD_CONFIG 声明大小不够时**拒绝越界读**），
# 判据族 C1–C13 → C1–C15。门数不变，仍是 19。
# R82 新增 check_unified_graph.py（R82 Phase 0 / R82-0-3）。它是 Phase 0 的**唯一产物**：
# 先把「统一图」的四条恒等式与 T1 的图前提立起来，因为 T1–T4 都要往同一张图上加东西
# （T1 加边种类、T2 加跳、T3 加算子对齐、T4 加规则节点）—— 模型晚定稿就要拆两遍。
# 判据族 U1–U8，其中 U3 是 R82-0-2 验收判据「**注入一条边即破**」的**执行版**；
# R82-0b 起另含 U2b（20 条映射逐条比期望表）/ U6（站点先行，构造期拒绝）/
# U7（互转规则的验证分母）—— 三者都为了同一件事：**判据不许退化成恒真式**
# （把一句注释变成一条真跑的探针）。R82b 补 U8（站点**匹配口径**：子串 vs 词界
# **并列**读数，并断言两者真的不同）—— 口径被悄悄换掉时全部门禁可以全程绿，
# 所以「只加对账不够，必须给口径本身配对手方」。故 17 → 18。
# R84 新增 check_kernel_snapshot.py（R84 / 判据族 W1–W5）。起因是一个**只读不校**的
# 三方事实：README 里散着 R75 的 `661 s / 10.8 GB`，`docs/KERNEL_RUN.md` 里是 R81 的
# `793.4 s / 13.1 GB`，**两个都不是错的**，差的是子进程 cwd 约定（`cwd=REPO` 时 `rel`
# 退化成 basename、`cwd=CORPUS` 时是真相对路径）——「两个都对的读数」没有任何东西在看。
# 全树重跑要 ~13 分钟，不适合放进门禁 ⇒ 本门**不重跑**，只钉「那张表自称的那件事今天
# 还成立吗」：出处 + **口径**钉住（W2）、两档分母并列且**不许合一**（W3）、汇总↔明细
# **恒等式**（W4）、与 R81 基线在**与时钟无关**的键上逐位**且逐类**对照（W5）、
# 唯一事实源指针 + 跨文档分母一致。故 18 → 19。
# R85 给同一道门补 W6（**流程登记**，不新增护栏脚本）：这条流程此前只活在 8 个脚本的
# docstring 里、散在 `_kernel/`（R75–R81）与 `_r82/`（R84）两棵**仓外**树 ——
# **没有任何一处能回答「有哪几站、该跑哪一代」**，而盘上真躺着三代驱动，其中
# `rerun_kernel_r81.py` 再跑一次就会**就地覆盖对照基线**（L85：指针没有对手方）。
# ⇒ 站表 + 「恰好一个 current 分析器」+ **产物链拓扑**（每站 in ⊆ 前序 out）
# + 站数分母 + 仓内落点存在性。**不加闸门数**（缺口为 0 时加闸 = churn），
# 只提高既有判据的分辨率。
# R96 / Phase 1 / 槽 23：19 → 20。加的是**新闸门**（不是给既有门加判据族）——
# 「能力对等」此前**一格判据都没有**（64 个格子里 16 个 `no`，缺口 > 0），
# 正是 R85 那句「缺口为 0 时加闸 = churn」**不**适用的一类。
# 全部 25 个 `check_*.py` = 24 道门 + 本 runner。
# R-图1：新增 check_flow_figures.py（FF1–FF7，单语交互图 ⇄ index.html），故 21 → 22。
# R-事实1：新增 check_facts_replay.py（FT1–FT3，事实重放 == 报表），故 22 → 23。
# R-行尾1：新增 check_eol_convention.py（EO1–EO3，CRLF/LF 约定），故 23 → 24。
MIN_GUARDS = 33


def _write_help(text):
    """把帮助文本写到 stdout，强制 UTF-8（本仓文档里有中文与制表框字符）。

    被管道/CI 调用时 Python 会退回 locale 编码（中文 Windows 是 GBK）；
    与 matlabc.py / gui.py 的处理保持一致：先 reconfigure，失败再写 buffer。
    """
    for _s in (sys.stdout, sys.stderr):
        if _s is not None and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
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
        try:
            buf.write(text.encode("utf-8", "replace"))
            buf.flush()
            return True
        except Exception:
            return False


def _run(py, argv, cwd=None, timeout=GUARD_TIMEOUT):
    """跑一个子进程，返回 (rc, 文本输出)；超时标记 rc=None（= 红）。

    ⚠ `stdin=subprocess.DEVNULL` 不是洁癖，是 R62-R31e 修掉的**真缺陷**：
    本仓 `matlabc_mcp.py` 是 stdio JSON-RPC server，`--help` 遇到一个继承来的、
    永不 EOF 的 stdin 就永久阻塞（实测 >30s；切断后 0.5s）。护栏会 spawn
    `*-.py --help`，stdin 一路继承到最里层，把整条链挂住（探针 probe_r26b_pipe）。

    ⚠ 旧实现用 `subprocess.run(stdout=PIPE)`，**没有 timeout**：
    只要有一个护栏不退出，`check_all.py`（以及 CI）就永远挂住。
    一条会挂死的链比一道闸门更糟 —— 所以超时在这里是**判红依据**，不是省事。
    """
    try:
        p = subprocess.Popen([py] + list(argv), cwd=cwd,
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
    except OSError as e:
        return None, "启动失败：%s" % e
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        p.kill()
        # R106：超时**必须带上证据** —— 以前只报「挂死（超时）」，既不说跑了
        #   多久、也不说它已经打出了什么 ⇒ 那是本门自己的**归因盲区**
        #   （R102 ㉙ 同族：红数没有名字）。实测动因：2026-10-16 的
        #   `--with-tests` 第二轮里 `check_ir_attribution.py(selftest)`
        #   报「挂死（超时）」，而同一命令空载单跑 5 次全部 rc=0 / ≈1 s ⇒
        #   从门给出的读数**分不出**「真挂」与「环境把 600s 吃完了」。
        #   ⚠ 证据**不能**从 `TimeoutExpired.output` 取：实测在 3.10.10 与
        #   3.13.14 上它**都是 `None`**（见 `_r106/probe_timeout_evidence.py`）
        #   ⇒ 只能 kill 之后**再 communicate 一次**。
        try:
            _rest, _ = p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            _rest = b""
        _lines = [ln for ln in (_rest or b"").decode("utf-8", "replace"
                                             ).splitlines() if ln.strip()]
        _tail = "\n".join(_lines[-6:]) if _lines else "（一行都没打）"
        return None, ("超时 >%.0fs（护栏不退出 —— 按红处理）；"
                      "它已经打出来的最后 %d 行：\n%s"
                      % (timeout, min(6, len(_lines)), _tail))


def run_guards(tools_dir, python_exe=None, timeout=GUARD_TIMEOUT):
    """跑目录下全部 check_*.py（不含本文件）；返回 (bad 列表, 护栏名列表)。"""
    py = python_exe or sys.executable
    if not os.path.isdir(tools_dir):
        print("check_all: 护栏目录不存在：%s（缺输入 → 红）" % tools_dir)
        return None, []
    me = os.path.basename(os.path.abspath(__file__))
    guards = sorted(f for f in os.listdir(tools_dir)
                    if f.startswith("check_") and f.endswith(".py")
                    and f != me)
    if not guards:
        print("check_all: 未找到任何 tools/check_*.py（缺输入 → 红）")
        return None, []
    bad = []
    for g in guards:
        p = os.path.join(tools_dir, g)
        rc, sout = _run(py, [p], timeout=timeout)
        ok = rc == 0
        last = sout.strip().splitlines()[-1][:110] if sout.strip() else ""
        print("[%s] %-24s %s" % ("OK  " if ok else "FAIL", g, last))
        if not ok:
            bad.append(g if rc is not None else g + "(timeout)")
        # 每个护栏必须自带并能通过 --selftest，否则是一道可能永远绿的门。
        #
        # **报错必须说清缺什么**（R240）。原文案只写「缺失或不通过」，
        # 而实际有两个独立条件：退出码 0，**以及输出里有 `SELFTEST COUNTS`
        # 这一行**。R240 有两道门（新加的 JS 门和 grammar 门）恰好只打了
        # 自家标签的 JSON、没打这一行 —— 单跑绿、进 runner 红，而报错
        # 让人以为是判据不过，白找半天。
        s_rc, s_sout = _run(py, [p, "--selftest"], timeout=timeout)
        has_counts = "SELFTEST COUNTS" in s_sout
        if s_rc is None:
            print("[FAIL] %-24s （--selftest 挂死：%ds 内没退出）"
                  % (g, timeout))
            bad.append(g + "(selftest)")
        elif s_rc != 0:
            print("[FAIL] %-24s （--selftest 退出码 %d，判据不过）"
                  % (g, s_rc))
            bad.append(g + "(selftest)")
        elif not has_counts:
            print("[FAIL] %-24s （--selftest 没输出 `SELFTEST COUNTS {...}` "
                  "—— 这是 runner 认自证的唯一凭据）" % (g,))
            bad.append(g + "(selftest)")
    return bad, guards


def _guard_count_problem(n_found, minimum, is_own_dir):
    """R33/C'9 的判定抽成纯函数（好让自证能直接测它）。

    返回问题字符串，或 None 表示通过。
    `is_own_dir=False`（显式 --tools-dir 指向别处）时不施加下限 —— 那是复用场景。
    """
    if not is_own_dir:
        return None
    if n_found < minimum:
        return ("只找到 %d 道护栏，少于登记下限 %d —— 有护栏被删/改名/移走"
                "（rc 仍为 0 但门少了）" % (n_found, minimum))
    return None


# [R102] 完整门禁的墙钟上限：整套 tests/ 实测 ≈35 分钟（含两个 8 分钟的浏览用例）。
TEST_TIMEOUT = 5400.0
# [R102] 与基线比对用的**解释器版本串**（如 3.10.10）。用版本而不是路径：
#   真正会让收集数/跳过数变的是解释器版本；路径是机器相关的，写进基线等于
#   把机器信息提交进仓库，还会把「换台机器、同一个 3.10」误判成测试退化。
PYVER = "%d.%d.%d" % sys.version_info[:3]
# [R102] 测试基线文件（相对仓库根）。它是「测试红数」的唯一事实源，两向核对。
TEST_BASELINE_PATH = os.path.join("docs", "TEST_BASELINE.json")


# ── [R106] 仓级结构闸门（闸门，**不是**护栏脚本 ⇒ 不进 `MIN_GUARDS`）───────
#
# 它们守的是**本仓文档与计划自身**的结构，而不是某个模块的行为：
#   ① 计划块（`docs/EVOLVE_ROADMAP_360.md` 的 `# ROUNDS:PLAN v1`）的 `action`
#      必须 ∈ 在册动作 ∪ `-`；`-` 必须写 `blocked_reason`；在册动作不许带理由。
#   ② **全仓** `*.md` 的代码围栏结构（零长度代码块 / 奇数围栏；跳过登记目录）。
#
# 为什么在 runner 里、为什么不放 `tests/`：见本文件顶部本轮的注记
# （零级联 + 「排不上队的判据与没有判据只差一层错觉」）。
# ⚠ 本节**不许**出现以判据前缀开头的字符串字面量（理由见顶部注记 1）。
PLAN_FILE = os.path.join("docs", "EVOLVE_ROADMAP_360.md")
PLAN_ACTIONS_FILE = os.path.join("docs", "PLAN_LEDGER_DIGEST.json")
PLAN_COLS = 6
# 待扫文档的下界（与 `tests/test_matlabc.py::test_r104b_docs_markdown_fence_structure`
# 同一条口径）：分母失效时「0 处异常」是恒真判据（R99 ④）。
# R107：扫描面从「`docs/*.md` + 根部 `*.md`」扩到**全仓**（实测 88 份，此前漏扫 13 份）
# ⇒ 下界随之上抬到 85：**谁把扫描面偷偷缩回 75 份，当场红** —— 扩面本身也要有对手方。
FENCE_MIN_DOCS = 85
# 不扫的目录（按目录名，闭集）。扩面前**先测过**：那 13 份此前漏扫的文件逐个喂给
# 本门的判据，**0 份脏**（`_r107/probe_fence_all.py`）—— 所以扩面不会误伤。
FENCE_SKIP_DIRS = frozenset((".git", "__pycache__", "node_modules", ".workbuddy",
                             ".pytest_cache", "dist_bin", "_build"))


def plan_block_rows(text):
    """从 `# ROUNDS:PLAN v1` 块取数据行 ⇒ `(问题列表, [行字典])`。

    形状口径与 `_r82/evolve_loop.py::load_plan` **同一条**（恰 6 列 / 首列是轮号 /
    块以 ``` 闭合 / 空行与 `#` 开头的注释跳过 / `-` 就是「无」）。

    为什么要在这里写第二份：runner 在**仓内**，不能 import 仓外脚本
    （R102 §6.3 的病根正是「仓内可判」退化成「只有仓外能判」）。
    两份口径漂移会被对方当场抓住：列数一变，环路 `load_plan` 返回 `None`
    （整块不可信、`return 2`），而这里报「列数 ≠ 6」—— 两边同时红。
    """
    lines = text.replace("\r\n", "\n").split("\n")
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^#\s*ROUNDS:PLAN\s+v\d+\b", ln.strip()):
            start = i
            break
    if start is None:
        return ["找不到 `# ROUNDS:PLAN v<N>` 块（缺输入 → 红）"], []
    rows, seen, probs = [], set(), []
    for i in range(start + 1, len(lines)):
        s = lines[i].strip()
        if s.startswith("```"):
            break
        if not s or s.startswith("#"):
            continue
        cells = [c.strip() for c in s.split("|")]
        if len(cells) != PLAN_COLS:
            probs.append("第 %d 行列数 = %d（要求恰 %d）"
                         % (i + 1, len(cells), PLAN_COLS))
            continue
        if not re.match(r"^\d+$", cells[0]):
            probs.append("第 %d 行首列不是轮号" % (i + 1))
            continue
        rn = int(cells[0])
        if rn in seen:
            probs.append("轮号重复：%d" % rn)
            continue
        seen.add(rn)
        rows.append({"round": rn, "action": cells[3],
                     "blocked_reason": cells[5]})
    if not rows:
        probs.append("计划块取不到任何数据行 —— 空集会让判据恒真（R99 ④）")
    return probs, rows


def plan_gate_problems(plan_text, digest):
    """计划块 ⇄ 在册动作 ⇄ `blocked_reason` ⇒ 问题列表（空 = 过）。

    纯函数（不碰文件系统）⇒ 自证可以直接喂文本。

    ⚠ **口径的来处（R106 实测）**：本判据的原版（R105 §8 写的
    「`action ⊆ ACTIONS ∪ {'-'}`」）装上后真树**红 27 项**。逐条归因后确认那
    27 行是**合法形态**——槽名当 `action`（人工轮），台账里 `accepted`——真正
    缺的是「**为什么它不是环路动作**」那一格。所以判据按 R105 §8 自己的原话
    收敛成两支：**在册**（环路会真的跑它）与**不在册但说出理由**。

    * `action` 在册 ⇒ `blocked_reason` 必须是 `-`：那一格环路**不读**
      （`run_loop` 只在动作缺失时取它）⇒ 留着理由会让读者以为这条停了，
      而它会照跑（**计划读数与实际不符**）。
    * `action` 不在册（含 `-`）⇒ `blocked_reason` 必须写出理由：否则
      「人工轮」与「拼错的动作名」在读数上**分不开**。
    * `action` 是空串 ⇒ 红：既不是动作也不是 `-`，环路会**静默**记 `blocked`。

    ⚠ **诚实的边界**：本判据抓不住**拼错的动作名** —— 它落在「不在册」那一支，
    只会被要求写理由。要抓住它必须给两个命名空间一个**显式标记**
    （如人工轮写 `slot:<名字>`），那时「裸名字」才等价于错（下一槽的设计题）。
    """
    probs, rows = plan_block_rows(plan_text)
    if probs:
        return ["计划块坏形状：%s" % probs]
    if not isinstance(digest, dict):
        return ["动作摘要不是 JSON 对象（缺输入 → 红）"]
    acts = digest.get("actions")
    if not isinstance(acts, list) or not acts:
        return ["动作摘要里没有非空的 `actions` —— 空集先断言非空（R99 ④）；"
                "它由 `_r103/gen_plan_ledger_digest.py` 从环路 `ACTIONS` 现算"]
    known = set(a for a in acts if isinstance(a, str))
    bad = []
    for r in rows:
        act, why = r["action"], r["blocked_reason"]
        rn = r["round"]
        if act == "":
            bad.append("第 %d 行：`action` 是空串 —— 既不是环路动作也不是 `-`，"
                       "环路会静默记 `blocked`（要「无」就写 `-`）" % rn)
            continue
        if act in known:
            if why and why != "-":
                bad.append("第 %d 行：`action` %r 在册（环路会**真的跑它**），"
                           "却带着 `blocked_reason` —— 那一格环路不读，"
                           "读者却以为这条停了（计划读数与实际不符）"
                           % (rn, act))
            continue
        # 不在册（含 `-`）：必须说出「为什么它不是环路动作」。
        if not why or why == "-":
            bad.append("第 %d 行：`action` %r **不是环路动作**，却没写 "
                       "`blocked_reason` —— 人工轮与「拼错的动作名」在读数上"
                       "分不开（不在册 ⇒ 写理由）" % (rn, act))
    return bad


def plan_gate_from_disk(root):
    """读盘上的计划块与动作摘要 ⇒ 问题列表。缺输入一律红（绝不退回旧副本）。"""
    miss = [p for p in (PLAN_FILE, PLAN_ACTIONS_FILE)
            if not os.path.isfile(os.path.join(root, p))]
    if miss:
        return ["缺输入（缺输入 → 红）：%s" % miss]
    pp = os.path.join(root, PLAN_FILE)
    dp = os.path.join(root, PLAN_ACTIONS_FILE)
    try:
        with io.open(pp, encoding="utf-8") as fh:
            plan_text = fh.read()
        with io.open(dp, encoding="utf-8") as fh:
            digest = json.load(fh)
    except (OSError, ValueError) as exc:
        return ["计划块 / 动作摘要读不了：%s" % exc]
    _probs, rows = plan_block_rows(plan_text)
    acts = digest.get("actions") if isinstance(digest, dict) else None
    bad = plan_gate_problems(plan_text, digest)
    # 绿灯也要报读数（R103 ㉜：通过时什么都不打印 ⇒ 余量/口径可以悄悄翻面）。
    print("check_all: 计划块闸门：数据行 %d / 在册动作 %d 个 / 违规 %d 项"
          "（源 %s + %s）"
          % (len(rows), len(acts) if isinstance(acts, list) else -1,
             len(bad), PLAN_FILE.replace("\\", "/"),
             PLAN_ACTIONS_FILE.replace("\\", "/")))
    return bad


def md_fence_problems(text):
    """Markdown 代码围栏结构的纯判据 ⇒ `(问题列表, 围栏数)`。

    本函数是本条判据的**唯一实现**：`tests/test_matlabc.py::_md_fence_problems`
    自 R106 起转调这里（同一份判据有两份实现必然漂移，而漂移的判据不是判据）。
    两条判据：

    * **零长度代码块**：按出现顺序两两配对（第 1 个是开、第 2 个是关…），某一
      对的两行**紧邻**即空块 —— 紧随其后的内容被挤到围栏**外**，再后面的内容
      被下一对围栏吞进去（表格不再渲染）。
    * **围栏总数必须为偶数**：否则文件末尾整段被吞进代码块。

    ⚠ 「相邻围栏」**不都是**缺陷：「关旧块 + 开新块」也相邻（正常）⇒ 必须按
    **序号奇偶**分开/关，不能只看相邻。R104b 实测：缺陷躺在**已推送**的提交里，
    而**围栏总数仍是偶数** ⇒ 只看奇偶的判据看不见它（所以两条都判）。
    """
    lines = text.replace("\r\n", "\n").split("\n")
    idx = [i + 1 for i, ln in enumerate(lines) if ln.strip().startswith("```")]
    problems = []
    for k in range(0, len(idx) - 1, 2):
        if idx[k + 1] == idx[k] + 1:
            problems.append("第 %d 行是零长度代码块（围栏紧邻）" % idx[k])
    if len(idx) % 2:
        problems.append("围栏总数 %d 为奇数 ⇒ 末尾内容被吞进代码块" % len(idx))
    return problems, len(idx)


def _fence_docs(root):
    """待扫文档 = 仓库里**全部** `*.md`（跳过 `FENCE_SKIP_DIRS` 里的目录）。

    ⚠ R107 之前这里是「`docs/*.md` + 仓库根部 `*.md`」—— 实测**漏扫 13 份**
    （`harness/README.md` / `flow/*.md` / `docs/analysis/*.md` /
    `ci-examples/README.md`）。漏扫的代价不是假红，是**假绿**：那些文档的围栏
    坏掉时，本门照样打印「违规 0 项」（R104b 的同族 —— 围栏缺陷不报错，只是
    读起来不对，而围栏总数仍是偶数时连奇偶判据也看不见）。
    扩面前**先测**：13 份逐个喂给 `md_fence_problems`，**0 份脏**。
    """
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in FENCE_SKIP_DIRS]
        for f in fn:
            if f.endswith(".md"):
                out.append(os.path.join(dp, f))
    return sorted(out)


def docs_fence_gate(root):
    """扫本仓 markdown 的围栏结构 ⇒ 问题列表。范围**现算并断言非空**（R99 ④）。"""
    files = _fence_docs(root)
    if len(files) < FENCE_MIN_DOCS:
        return ["待扫文档过少（%d 份 < 下界 %d）—— 分母失效时「0 处异常」是"
                "恒真判据（R99 ④）" % (len(files), FENCE_MIN_DOCS)]
    bad, n_fences = [], 0
    for path in files:
        try:
            with io.open(path, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
        except OSError as exc:
            bad.append("%s: 读不了（%s）"
                       % (os.path.relpath(path, root).replace("\\", "/"), exc))
            continue
        probs, n = md_fence_problems(txt)
        n_fences += n
        for pr in probs:
            bad.append("%s: %s"
                       % (os.path.relpath(path, root).replace("\\", "/"), pr))
    print("check_all: 文档围栏闸门：扫 %d 份文档 / 围栏 %d 个 / 违规 %d 项"
          "（全仓 *.md，跳过 %d 个登记目录；下界 %d 份）"
          % (len(files), n_fences, len(bad), len(FENCE_SKIP_DIRS),
             FENCE_MIN_DOCS))
    return bad


def parse_pytest_summary(text):
    """从 pytest 输出里取 (failed, passed, skipped)。

    取**最后**一个含 ` passed` 的行（汇总行恒在末行；早期进度行也会出现
    `passed`，取首会读错）。缺 `failed` / `skipped` 段 ⇒ 按 0 计（pytest 全绿时
    就是这么打的）。**取不到任何汇总行 ⇒ 返回 None**（缺输入 → 红，不许猜 0）。
    """
    got = None
    for ln in text.splitlines():
        m = re.search(r"(\d+) passed", ln)
        if not m:
            continue
        mf = re.search(r"(\d+) failed", ln)
        ms = re.search(r"(\d+) skipped", ln)
        got = (int(mf.group(1)) if mf else 0, int(m.group(1)),
               int(ms.group(1)) if ms else 0)
    return got


def failed_nodeids(text, limit=20):
    """从 pytest `-rf` 短摘要里取失败条目（`FAILED tests/…::test_x - …`）。

    为什么必须有它：门只报「2 failed」时，读者**没有入口**去裁定
    「量具错还是对象错」—— 失败清单本该是归因的起点，却在 `_run_tests`
    捕获后被整个丢掉了（R98 ⑮ 在门自己身上复现）。

    返回去重后的行；超过 `limit` 条时补一行汇总（**截断必须说出来**，
    否则「列出的就是全部」又是新误读）。**取不到就返回 []**：
    本函数只做展示，判红由 `test_baseline_problem` 负责。
    """
    seen = []
    for ln in text.splitlines():
        s = ln.strip()
        if (s.startswith("FAILED ") or s.startswith("ERROR ")) and s not in seen:
            seen.append(s)
    extra = len(seen) - limit
    if extra > 0:
        return seen[:limit] + ["……另有 %d 条未列出（摘要被截断）" % extra]
    return seen


# [R104] 性能余量**侧信道**：`tests/test_matlabc.py::_emit_perf_margin` 把
#   「实测 / 上限 / 余量」写成一行 JSON，路径由本门通过环境变量传进去。
#
# 为什么必须有它（R103 ㉜）：性能门**通过时什么都不打印** ⇒ 余量可以悄悄翻面
#   （R103 实测：`p77` 仅 1.72×、`c28` 1.38–1.47×，而抖动那次恰好翻 2 条）。
# 路径**由门自己新建**（跑 pytest 前建临时文件、跑完读它）⇒ 不可能读到陈旧读数；
# 不设环境变量时测试侧一个字节都不写。
PERF_MARGIN_ENV = "MALABC_PERF_MARGIN_LOG"
PERF_MARGIN_SRC = os.path.join("tests", "test_matlabc.py")


def parse_perf_margins(text):
    """解析余量侧信道 JSONL ⇒ (records, problems)。纯函数，自证直接测它。

    `records` 按余量**升序**（最紧的在前）；`problems` 是坏行 / 坏字段说明。
    **空文本不算问题**：空集由 `perf_margin_problem` 结合调用点数判
    （R95/R99 ④：集合判据必须先断言输入非空）。
    """
    records, problems = [], []
    for i, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if not s:
            continue
        try:
            rec = json.loads(s)
        except ValueError as exc:
            problems.append("第 %d 行不是 JSON：%s" % (i, exc))
            continue
        if not isinstance(rec, dict):
            problems.append("第 %d 行不是对象" % i)
            continue
        miss = [k for k in ("node", "measured", "limit", "ratio", "unit",
                            "kind")
                if k not in rec]
        if miss:
            problems.append("第 %d 行缺字段 %s" % (i, miss))
            continue
        if rec["kind"] not in ("budget", "tolerance"):
            problems.append("第 %d 行 kind 不是 budget/tolerance：%r"
                            % (i, rec["kind"]))
            continue
        if not (isinstance(rec["measured"], (int, float))
                and isinstance(rec["limit"], (int, float))
                and not isinstance(rec["measured"], bool)
                and not isinstance(rec["limit"], bool)):
            problems.append("第 %d 行 measured/limit 不是数字" % i)
            continue
        if rec["measured"] <= 0 or rec["limit"] <= 0:
            problems.append("第 %d 行 measured/limit 必须 > 0（否则余量算不出来）" % i)
            continue
        records.append(rec)
    records.sort(key=lambda r: r["ratio"])
    return records, problems


def count_perf_margin_callsites(src):
    """源内 `_emit_perf_margin(...)` **调用点**数 —— 分母**从被测量的源现算**。

    ⚠ 分母不许手写（R90 ①：量具的尺度要写进量具；㉛：候选集要能推导）。
    定义行（`def _emit_perf_margin`）与注释行不计。
    """
    n = 0
    for ln in src.splitlines():
        s = ln.strip()
        if s.startswith("def ") or s.startswith("#"):
            continue
        if "_emit_perf_margin(" in s:
            n += 1
    return n


PERF_MARGIN_CALLEE = "_emit_perf_margin"
# 跳过行格式**实测**（本机 Python310 + pytest；Windows 上路径带反斜杠，行号是
# `pytest.skip(...)` **调用点**那一行，不是 def 行）：
#     SKIPPED [1] tests\test_matlabc.py:12199: 无 node，跳过硬门禁全绿校验
# ⇒ 文件名与行号之间是「最后一个 `.py` 后的 `:数字:`」，用非贪婪配 `(.+?):(\d+):`。
_SKIP_LINE_RE = re.compile(r"^SKIPPED\s+\[\d+\]\s+(.+?):(\d+):")


def _ast_str_const(node):
    """取字符串字面量的值 —— 同时兼容 py3.6/3.7 与 py3.8+。

    ⚠ 本仓要求 Py3.6.5 兼容 ⇒ 不许只写 `isinstance(node, ast.Constant)`：
    3.6/3.7 上字符串字面量的节点类型是 `ast.Str`（值在 `.s`），那样写在那边
    **一个都取不到** —— 而「取不到」在本判据里的方向是**恒真**（空集）。
    取值顺序先 `.value`（3.8+）后 `.s`（3.6/3.7）：反过来的话，3.8–3.13 上
    访问 `.s` 会发 DeprecationWarning（本仓有用例在 `-W error` 形态下跑，会被误伤）。
    """
    v = getattr(node, "value", None)
    if isinstance(v, str):
        return v
    v = getattr(node, "s", None)
    return v if isinstance(v, str) else None


def perf_margin_nodes(src):
    """从**源码字面量**推导余量节点名 ⇒ `(nodes, spans)`，纯函数。

    `nodes` = {节点名: 宿主测试函数名}（键已排序）；`spans` =
    [(起行, 止行, 函数名), …]，用来把 pytest 报的 `文件:行号` 映射回宿主 ——
    起行**含装饰器行**（`pytest.mark.skipif` 这一类跳过报的是装饰器那一行）。
    源码解析不了 ⇒ `(None, None)`：**缺输入 → 红**，绝不静默退化成空集。

    为什么必须从源码推导（R90 ① / R103 ㉛）：候选集若人工挑，漏一个就永远不红
    —— 而「漏掉的那个」正是 R103 实测里余量悄悄翻面的那两条。节点名与函数名
    都**现读现算**，本函数里不写死任何一个。
    """
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return None, None
    nodes, spans = {}, []
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        _start = min([fn.lineno] + [d.lineno for d in fn.decorator_list])
        spans.append((_start, getattr(fn, "end_lineno", None) or fn.lineno,
                      fn.name))
        for sub in ast.walk(fn):
            if not isinstance(sub, ast.Call) or not sub.args:
                continue
            if getattr(sub.func, "id", None) != PERF_MARGIN_CALLEE:
                continue
            lit = _ast_str_const(sub.args[0])
            if lit is not None:
                nodes.setdefault(lit, fn.name)
    return dict((k, nodes[k]) for k in sorted(nodes)), spans


def parse_skipped_hosts(text, spans):
    """从 pytest `-rs` 摘要行抽「被跳过的宿主测试名」 ⇒ `(hosts, problems)`。

    只认 `PERF_MARGIN_SRC` 那一个文件的跳过行（别的测试文件的跳过与本判据无关）。
    行号落在任何函数的 `[起, 止]` 之外 ⇒ 记进 `problems`（**不许静默丢弃**：
    静默丢弃正是「缺记录被读成读数没接上」的成因）。空文本 ⇒ 空集且无问题
    ——「这一跑没有跳过」是合法状态，不是缺输入。
    """
    want = PERF_MARGIN_SRC.replace("\\", "/")
    hosts, problems = set(), []
    for ln in text.splitlines():
        m = _SKIP_LINE_RE.match(ln.strip())
        if not m:
            continue
        if m.group(1).replace("\\", "/") != want:
            continue
        try:
            no = int(m.group(2))
        except ValueError:
            problems.append("跳过行号读不出整数：%s" % ln.strip()[:120])
            continue
        hit = [nm for (a, b, nm) in spans if a <= no <= b]
        if len(hit) == 1:
            hosts.add(hit[0])
        else:
            problems.append("跳过行 %d 落在 %d 个测试函数里（应恰 1 个）—— %s"
                            % (no, len(hit), ln.strip()[:120]))
    return hosts, problems


def perf_margin_problem(records, problems, callsites, expected=None,
                        skipped=None):
    """余量侧信道的判据。返回问题串（空 = 过）。纯函数，自证直接测它。

    ⚠ 强度只许升（R102 ㉖），每条都对应一种**静默失效**：
      * 源内 0 个调用点 ⇒ 红：机制被删空，判据恒真（空集 ④）；
      * 坏记录 ⇒ 红：畸形行不许被当成「没有这条」（陈旧的红与真坏长得一样，R83 ④）；
      * 有调用点却 0 条记录 ⇒ 红：**这正是 ㉜ 要防的那一种** —— 绿灯读数没接上，
        余量又会悄悄翻面，而 rc 依然是 0；
      * [R107] `expected` 由**源码字面量**推导 ⇒ **逐个**节点都要有记录，除非它的
        宿主测试**这一跑真的被跳过**（`skipped`）—— 否则「本机没装 node」与
        「读数没接上」在读数上长得一模一样（`expected=None` = 读不出源码 ⇒ 红）；
      * [R107] 记录里的节点名必须都在源码里：**陈旧登记也红**（登记表两向的同一半）；
      * [R107] 文本口径的调用点数必须等于 AST 口径的节点数 —— 同一个量两个都对却
        不同的答案时，至少有一个在说谎（R99 ④：空集 / 分母先自证）。
    """
    if callsites <= 0:
        return ("%s 里一个 `_emit_perf_margin(` 调用点都没有 —— 余量侧信道是空集，"
                "判据会恒真（R95/R99 ④：先断言输入非空）" % PERF_MARGIN_SRC)
    if problems:
        return "性能余量侧信道有坏记录：%s" % problems[0]
    if not records:
        return ("性能余量侧信道**一条记录都没有**（源内 %d 个调用点）—— "
                "绿灯读数没接上，余量又会悄悄翻面（R103 ㉜）" % callsites)
    if not [r for r in records if r.get("kind") == "budget"]:
        return ("余量侧信道里**一条预算门记录都没有**（只有宽限断言）—— "
                "「有记录」被宽限记录单独满足 ⇒ 判据退化成空判据")
    if expected is None:
        return ("读不出 %s 里的 `_emit_perf_margin` 节点名（源码解析不了 ⇒ "
                "缺输入 → 红）：少了这一环，「每个绿灯读数都接上了」就无从判定"
                % PERF_MARGIN_SRC)
    if len(expected) != callsites:
        return ("`_emit_perf_margin` 的**两个口径不一致**：文本数出 %d 个调用点，"
                "AST 从字面量推出 %d 个节点名 —— 同一个量两个都对却不同的答案，"
                "至少有一个在说谎（R99 ④）" % (callsites, len(expected)))
    have = set(r["node"] for r in records)
    _skip = set(skipped or ())
    miss = sorted(n for n in expected
                  if n not in have and expected[n] not in _skip)
    if miss:
        return ("余量侧信道缺 %d 个节点的记录：%s（源码共 %d 个节点）—— "
                "它们的宿主测试**没有**被跳过，所以不是「本机没装 node」那种"
                "合法缺失，而是绿灯读数没接上（R103 ㉜）"
                % (len(miss), miss, len(expected)))
    stale = sorted(n for n in have if n not in expected)
    if stale:
        return ("余量侧信道里有 %d 个**不在源码里**的节点名：%s —— "
                "记录与源码不是同一份（陈旧登记 / 读到了旧源）"
                % (len(stale), stale))
    return None


def format_perf_margin_lines(records, callsites, nodes=None):
    """把余量按**最紧在前**排成可读行：绿灯也要报「实测 / 上限 / 余量」。

    `nodes` 给了（源码推导出的节点名全集）就**一并报覆盖度** —— 只报「有多少条
    记录」看不出「有没有哪个节点一条都没接上」，而后者才是 ㉜ 要防的那一种。
    """
    out = []
    for r in records:
        tag = "" if r.get("kind") == "budget" else "  [宽限断言]"
        out.append("check_all:   %-40s 实测 %9.3f%s  上限 %9.3f%s  余量 %5.2fx%s"
                   % (r["node"], r["measured"], r["unit"],
                      r["limit"], r["unit"], r["ratio"], tag))
    _nb = len([r for r in records if r.get("kind") == "budget"])
    _last = ("check_all:   余量记录 %d 条（预算 %d / 宽限 %d）/ 源内调用点 %d 处"
             % (len(records), _nb, len(records) - _nb, callsites))
    if nodes is not None:
        _last += "；源码节点覆盖 %d/%d" % (
            len(set(r["node"] for r in records) & set(nodes)), len(nodes))
    _last += "（按余量升序，最紧在前；`[宽限断言]` 的比值本来就该≈1.0）"
    out.append(_last)
    return out


def test_baseline_problem(got, baseline, python_ver=None):
    """两向核对测试结果与基线。返回问题串（空 = 过）。纯函数，自证直接测它。"""
    if got is None:
        return ("测不到 pytest 汇总行（缺输入 → 红）—— 不许当成 0 failed "
                "（那会把「根本没跑起来」读成「全绿」）")
    failed, passed, _skipped = got
    base_failed = baseline.get("failed")
    base_passed = baseline.get("passed")
    if base_failed is None or base_passed is None:
        return "基线缺 failed/passed 两键（缺输入 → 红）"
    base_py = baseline.get("python_version")
    if python_ver and base_py and python_ver != base_py:
        return ("解释器版本与基线不一致（实测 %s / 基线 %s）—— 换了运行环境 ⇒ "
                "读数不可比，必须重录基线，而不是把差异读成测试退化；"
                "本门用**当前解释器**跑 pytest（`sys.executable`），所以"
                "`--with-tests` 请用录制基线时的那个解释器（%s）来跑"
                % (python_ver, base_py, base_py))
    if failed > base_failed:
        return ("测试红数变多（%d > 基线 %d）—— 新红没有任何门在看，"
                "先逐条归因（量具错还是对象错），再修或改表" % (failed, base_failed))
    if failed < base_failed:
        return ("测试红数变少（%d < 基线 %d）—— 有人修好了：请来改 "
                "%s 并把「哪一轮修的」写进 why" % (failed, base_failed,
                                                 TEST_BASELINE_PATH))
    tol = baseline.get("passed_tolerance", 5)
    if passed < base_passed - tol:
        return ("通过数变少（%d < 基线 %d - 容差 %d）—— 测试被删或被跳过"
                % (passed, base_passed, tol))
    return None


def _run_tests(root, py, timeout, margin_log=None):
    """跑整套 pytest，返回 (rc, 输出文本)；起不来/挂死返回 (None, "")。"""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)      # tests/ 要求 PYTHONPATH 不生效（显式不设）
    # [R104] 余量侧信道路径**由门给**（门自己新建的临时文件）⇒ 不可能陈旧。
    if margin_log:
        env[PERF_MARGIN_ENV] = margin_log
    else:
        env.pop(PERF_MARGIN_ENV, None)
    # [R107] 加 `-rs`：跳过条目必须带**行号** —— 没有它，「本机没装 node 所以这条
    #   读数缺席」与「读数根本没接上」在输出里长得一模一样（都只是少一条记录）。
    cmd = [py, "-m", "pytest", "tests/", "-q", "-rf", "-rs", "--tb=no"]
    try:
        p = subprocess.Popen(cmd, cwd=root, env=env,
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
    except OSError as exc:
        print("check_all: 起不来 pytest（%s）：%s" % (py, exc))
        return None, ""
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        return None, ""
    return p.returncode, out.decode("utf-8", "replace")


def tests_gate_problem(tools_dir, python_exe=None, timeout=TEST_TIMEOUT):
    """完整门禁：缺输入/缺基线/结果不合，一律返回问题串。"""
    root = os.path.dirname(os.path.abspath(tools_dir))
    bp = os.path.join(root, TEST_BASELINE_PATH)
    if not os.path.isfile(bp):
        return "缺测试基线文件 %s（缺输入 → 红）" % TEST_BASELINE_PATH
    try:
        with io.open(bp, encoding="utf-8") as fh:
            baseline = json.load(fh)
    except (ValueError, OSError) as exc:
        return "测试基线读不了或不是 JSON：%s" % exc
    py = python_exe or sys.executable
    # [R104] 侧信道临时文件：**每次跑 pytest 前新建**（无陈旧读数），跑完删。
    _mdir = tempfile.mkdtemp(prefix="malabc_perf_")
    _mlog = os.path.join(_mdir, "margins.jsonl")
    try:
        rc, text = _run_tests(root, py, timeout, margin_log=_mlog)
        _mtext = ""
        if os.path.isfile(_mlog):
            with io.open(_mlog, encoding="utf-8") as fh:
                _mtext = fh.read()
        _src = ""
        _sp = os.path.join(root, PERF_MARGIN_SRC)
        if os.path.isfile(_sp):
            with io.open(_sp, encoding="utf-8") as fh:
                _src = fh.read()
    finally:
        shutil.rmtree(_mdir, ignore_errors=True)
    if rc is None:
        return "pytest 超过 %.0fs 未退出（挂死 → 红）" % timeout
    print("check_all: pytest 退出码 %d" % rc)
    _got = parse_pytest_summary(text)
    # 实测汇总**必须**打出来：基线里的数字只能来自实测，不许靠猜。
    print("check_all: 实测汇总 (failed, passed, skipped) = %s" % (_got,))
    # R102b：红数必须带名字 —— 只报计数等于把归因的起点丢掉。
    for _ln in failed_nodeids(text):
        print("check_all:   %s" % _ln)
    # [R104] 余量**在变红之前**就要可见：按最紧在前打表（㉜）。
    _cs = count_perf_margin_callsites(_src)
    _recs, _mprobs = parse_perf_margins(_mtext)
    # [R107] 节点名**从源码字面量推导**（㉛：候选集要能推导，不能人工挑），并把
    #   pytest `-rs` 报出的**被跳过行号**映射回宿主测试 ⇒ 让「本机没装 node」
    #   与「读数没接上」分得开（此前两者在读数上是同一件事）。
    _exp, _spans = perf_margin_nodes(_src)
    _skhosts, _skprobs = parse_skipped_hosts(text, _spans or [])
    _sknodes = set(n for n, h in (_exp or {}).items() if h in _skhosts)
    for _ln in format_perf_margin_lines(_recs, _cs, _exp):
        print(_ln)
    # 三条判据**各自独立结算**（R102 ㉔：一条红不许挡住另一条的读数）。
    _probs = []
    _pb = test_baseline_problem(_got, baseline, python_ver=PYVER)
    if _pb:
        _probs.append(_pb)
    _pm = perf_margin_problem(_recs, _mprobs, _cs, expected=_exp,
                              skipped=_sknodes)
    if _pm:
        _probs.append(_pm)
    if _skprobs:
        _probs.append("余量侧信道：pytest `-rs` 的跳过行解析有 %d 条告警 —— %s"
                      % (len(_skprobs), _skprobs[0]))
    return "；".join(_probs) if _probs else None


def main(argv):
    # --help 必须在**任何副作用之前**返回。早先它没有分支，于是
    # `python tools/check_all.py --help` 会真的把全套护栏跑一遍（≈30s）——
    # 对「问一句怎么用」的人来说是纯粹的意外，在 CI 里则是无谓的挂钟开销。
    if "--help" in argv or "-h" in argv:
        if not _write_help(__doc__):
            return 2
        return 0
    if "--selftest" in argv:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        # 这里的 good 数的是**自证断言条数**（R107 **实测** 45 条 —— R106 是 37，
        # 本轮「余量判据」那一节新增 8 条；写补丁时手数过 34、35 两次，两次都被
        # 实跑当场抓住：**读数只认实测**），与 MIN_GUARDS（护栏道数）是两件事 ——
        # 别把它们调成同一个变量。
        # ⚠ 下界只许升（R102 ㉖）：它就是「样本被删掉」的对手方。
        return 0 if (bad == 0 and good >= 45) else 1

    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if "--tools-dir" in argv:
        i = argv.index("--tools-dir")
        if i + 1 >= len(argv):
            print("check_all: --tools-dir 需要一个路径（缺输入 → 红）")
            return 2
        tools_dir = argv[i + 1]

    bad, guards = run_guards(tools_dir)
    if bad is None:
        return 2
    # 本仓自己的 tools/ —— 门数棘轮与测试门都只在这种情况下才施加
    # （显式 --tools-dir 指向别处 = 自证/嵌入式复用，不该被本仓的规矩误伤）。
    _local = os.path.abspath(tools_dir) == os.path.dirname(
        os.path.abspath(__file__))

    # R33/C'9：门数棘轮 —— 只有当跑的是本仓自己的 tools/ 时才要求下限。
    _guard_prob = _guard_count_problem(len(guards), MIN_GUARDS,
                                       True) if _local else None

    # [R106] 仓级结构闸门（各条判据**独立结算**：任一条红都不挡住其余各条的读数）。
    _root = os.path.dirname(os.path.abspath(tools_dir))
    _plan_prob = plan_gate_from_disk(_root) if _local else None
    _doc_prob = docs_fence_gate(_root) if _local else None

    # [R102] 完整门禁（显式 --with-tests）：再跑整套 tests/ 并核对基线。
    #
    # ⚠ **两条判据必须各自独立行使**（R102 修的第二个结构性缺陷）：
    #   本函数原先在「任一护栏红」时**立刻 `return 1`**，于是测试门**整个走不到**
    #   —— 只要有一道护栏红，「测试红数」就又失去了对手方。而一条会「在别人红的
    #   时候静默失效」的判据，与没有这条判据只差一层错觉：它看起来在守，其实没守。
    #   代价是护栏红时也会真跑一遍整套 tests/（≈35 分钟）—— 但那正是 --with-tests
    #   这个显式开关的语义：**要么不跑，要么就给出汇总**。
    _tests_prob = None
    if "--with-tests" in argv and _local:
        _tests_prob = tests_gate_problem(tools_dir)

    if bad:
        print("check_all: %d 项失败：%s" % (len(bad), bad))
    if _guard_prob:
        print("check_all: " + _guard_prob)
    if _plan_prob:
        print("check_all: 计划块闸门：%d 项违规：" % len(_plan_prob))
        for _p in _plan_prob:
            print("check_all:   - " + _p)
    if _doc_prob:
        print("check_all: 文档围栏闸门：%d 项违规：" % len(_doc_prob))
        for _p in _doc_prob:
            print("check_all:   - " + _p)
    if _tests_prob:
        print("check_all: " + _tests_prob)
    elif "--with-tests" in argv and _local:
        # ⚠ R102 实测又抓到一次同一形状：这段原先排在
        #   `return 1` **之后**，于是「别的护栏红」时读者只看到汇总数字、
        #   **看不到裁决** —— 把「判了且通过」与「根本没判」混成一个信号。
        #   与上面 `_tests_prob` 独立行使是同一条纪律的另一半：
        #   **正反两面都要能独立看见**。
        print("check_all: 测试基线一致（%s）" % TEST_BASELINE_PATH)
    if bad or _guard_prob or _tests_prob or _plan_prob or _doc_prob:
        return 1
    print("check_all: OK（%d 个护栏，全部通过且各自自证；门数下限 %d）"
          % (len(guards), MIN_GUARDS))
    # R152：LSP 的判据**不在** runner 里 —— 它要起子进程 + 跑分析，放进来会把
    # 24 道门从 2 分钟拖到 3 分钟。所以这里**只提示、不执行**：
    # 让「忘了跑」变得可见，而不是让门变慢。
    print("[提示] LSP 判据未纳入本 runner；改动 matlabc_lsp.py 或 vscode/ 后请手工跑：")
    print("       python tools/lsp_selftest.py   （11 条：诊断 / 定义 / 引用）")
    print("       node vscode/test_extension.js  （5 条：注册了哪些 provider）")
    print("       node vscode/test_client.js     （6 条：以真实 LSP 为对端）")
    # R363：全场景与变异抽样同样"重"（各起 20+ 个子进程），不进门列表；
    # 但**必须出现在提示里** —— 一次都没被提到过的检查，等于不存在。
    print("       python tools/rsi_scenarios.py  （58 个全场景，只走公开协议）")
    print("       python tools/mutate_sample.py  （16 个变异：验证判据会红）")
    print("       加 --with-scenarios 可让本 runner 顺手跑一遍全场景（约 1 分钟）")

    # `--with-scenarios`：显式要求才跑。**失败要能影响退出码**，
    # 否则「跑了但红了照样 rc=0」比不跑更糟。
    if "--with-scenarios" in argv:
        _here = os.path.dirname(os.path.abspath(__file__))
        _scrc, _scout = _run(sys.executable,
                             [os.path.join(_here, "rsi_scenarios.py")],
                             timeout=900)
        _sc_last = [x.strip() for x in (_scout or "").splitlines() if x.strip()]
        print("check_all: 全场景 %s（%s）"
              % ("通过" if _scrc == 0 else "失败",
                 (_sc_last[-1] if _sc_last else "")[:80]))
        if _scrc != 0:
            return 1
    return 0


def _selftest():
    """双向自证：既造坏样本（必须红），也造好样本（必须绿）。

    七项断言缺一不可：
      ① 坏护栏（rc=1）         -> runner 必须返回 1
      ② 好护栏（rc=0 且有自证） -> runner 必须返回 0
      ③ 缺自证的护栏           -> runner 必须返回 1（否则「无自证」会被静默放行）
      ④ 空目录                 -> runner 必须返回 2（缺输入 → 红）
      ⑤ **永不退出的护栏**     -> runner 必须在超时后返回 1（R62-R31e 新增：
         一条会挂死的链比一道闸门更糟 —— 旧实现没有 timeout，一个不退出
         的护栏会让 check_all 和 CI 永远等下去。这里用 3s 超时把它变成红。）
      ⑥ 门数棘轮（R33/C'9，R37 改成从 MIN_GUARDS 派生）-> 少于下限要红、
         达到下限放行、外部目录不施加下限
      ⑦ MIN_GUARDS 必须等于本目录真实护栏数（R37）—— 只测「函数在给定数字下
         对不对」不够，还要保证**那个数字本身**没被落下
      ⑧ [R102] 测试基线两向核对（纯函数，不跑 pytest）：红数变多 / 变少 /
         通过数掉下容差 / 换了解释器 / 取不到汇总行，**五种都必须红**；
         再加上解析器本身的三个样本
      ⑨ [R104] 性能余量侧信道（纯函数，不跑 pytest）：坏行 / measured≤0 /
         缺字段 / 有调用点却零记录**都必须红**，好样本必须过；调用点分母
         不许把定义行与注释行算进去
    """
    bad = good = 0
    tmp = tempfile.mkdtemp(prefix="chk_all_selftest_")
    try:
        def _mk(name, text):
            p = os.path.join(tmp, name)
            with io.open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
            return p

        # ① 坏护栏
        d1 = os.path.join(tmp, "d1")
        os.makedirs(d1)
        _mk(os.path.join(d1, "check_bad.py"), R_BAD_GUARD)
        b1, _g1 = run_guards(d1)
        if b1:
            good += 1
        else:
            bad += 1
            print("  [selftest] 坏护栏未被 runner 抓到")

        # ② 好护栏
        d2 = os.path.join(tmp, "d2")
        os.makedirs(d2)
        _mk(os.path.join(d2, "check_good.py"), R_GOOD_GUARD)
        b2, g2 = run_guards(d2)
        if b2 == [] and g2 == ["check_good.py"]:
            good += 1
        else:
            bad += 1
            print("  [selftest] 好护栏被误伤：bad=%r guards=%r" % (b2, g2))

        # ③ 缺自证的护栏
        d3 = os.path.join(tmp, "d3")
        os.makedirs(d3)
        _mk(os.path.join(d3, "check_noself.py"), R_NO_SELFTEST_GUARD)
        b3, _g3 = run_guards(d3)
        if b3:
            good += 1
        else:
            bad += 1
            print("  [selftest] 缺自证的护栏被静默放行")

        # ④ 空目录
        d4 = os.path.join(tmp, "d4")
        os.makedirs(d4)
        b4, _g4 = run_guards(d4)
        if b4 is None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 空目录未变红：%r" % (b4,))

        # ⑤ 永不退出的护栏（用 3s 超时把挂死变成红，而不是让自证自己也挂住）
        d5 = os.path.join(tmp, "d5")
        os.makedirs(d5)
        _mk(os.path.join(d5, "check_hang.py"), R_HANG_GUARD)
        b5, _g5 = run_guards(d5, timeout=3.0)
        if b5 and any("timeout" in x for x in b5):
            good += 1
        else:
            bad += 1
            print("  [selftest] 永不退出的护栏未被超时判红：%r" % (b5,))

        # ⑥ 门数棘轮（R33/C'9）：少于下限必须变红；达到/超过则放行。
        # 注意这是纯函数判定，不依赖真实目录 —— 否则自证会被「当前有几道门」绑死。
        # R37：样本里的数字改成**从 MIN_GUARDS 派生**，而不是写死 8 ——
        # 否则 MIN_GUARDS 调到 20 时，自证还在测 8，棘轮会悄悄失效。
        if _guard_count_problem(MIN_GUARDS - 1, MIN_GUARDS, True) is not None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 门数不足未被判红（C'9 棘轮失效）")
        if _guard_count_problem(MIN_GUARDS, MIN_GUARDS, True) is None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 门数达下限被误伤（C'9 误报）")
        if _guard_count_problem(1, MIN_GUARDS, False) is None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 外部 --tools-dir 被误施加下限（C'9 过严）")

        # ⑦ MIN_GUARDS 必须等于**本目录真实的护栏数**（R37）。
        # 这是棘轮的另一半：只测「函数在给定数字下对不对」不够，
        # 还要保证**那个数字本身**没被落下 —— 加了一道门却忘了上调，
        # 棘轮就等于不存在，而 rc 依然是 0。
        _here = os.path.dirname(os.path.abspath(__file__))
        _me = os.path.basename(os.path.abspath(__file__))
        _real = len([f for f in os.listdir(_here)
                     if f.startswith("check_") and f.endswith(".py")
                     and f != _me])
        if MIN_GUARDS == _real:
            good += 1
        else:
            bad += 1
            print("  [selftest] MIN_GUARDS=%d 与本目录真实护栏数 %d 不一致 —— "
                  "加门/删门后必须同步这个数字" % (MIN_GUARDS, _real))

        # ⑧ [R102] 测试基线两向核对（纯函数：不跑 pytest，毫秒级）。
        _base = {"failed": 0, "passed": 513, "skipped": 4,
                 "python_version": "3.10.10", "passed_tolerance": 5}
        _base2 = {"failed": 2, "passed": 500, "skipped": 4,
                  "python_version": "3.10.10"}
        _cases = (
            (_base, (0, 513, 4), "3.10.10", False, "全等应放行"),
            (_base, (1, 513, 4), "3.10.10", True, "红数变多"),
            (_base, (0, 400, 4), "3.10.10", True, "通过数掉下容差"),
            (_base, (0, 513, 4), "3.13.12", True, "换了解释器"),
            (_base2, (0, 500, 4), "3.10.10", True, "红数变少(修好没改表)"),
            (_base, None, "3.10.10", True, "取不到汇总行"),
        )
        for _b, _got, _py, _want_bad, _why in _cases:
            _p = test_baseline_problem(_got, _b, python_ver=_py)
            if bool(_p) == _want_bad:
                good += 1
            else:
                bad += 1
                print("  [selftest] 基线核对样本「%s」判反：%r" % (_why, _p))
        if (parse_pytest_summary("1 failed, 20 passed, 3 skipped in 5s")
                == (1, 20, 3)
                and parse_pytest_summary("20 passed in 5s") == (0, 20, 0)
                and parse_pytest_summary("no summary here") is None):
            good += 1
        else:
            bad += 1
            print("  [selftest] parse_pytest_summary 解析不对")

        # ⑨ [R104/R107] 性能余量侧信道：坏的八种 + 好的一种 + 分母四向。
        _okl = ('{"kind": "budget", "limit": 5.0, "measured": 3.5, '
                '"node": "c28", '
                '"ratio": 1.4285714285714286, "unit": "s"}')
        _r9, _p9 = parse_perf_margins(_okl + "\n")
        if len(_r9) == 1 and not _p9 and \
                abs(_r9[0]["ratio"] - 5.0 / 3.5) < 1e-9:
            good += 1
        else:
            bad += 1
            print("  [selftest] 余量解析器读不出好行：%r / %r" % (_r9, _p9))
        # ⚠ R107：坏样本必须把 `expected` 一起给**对** —— 否则它们会因为
        #   「推导不出节点名 ⇒ 缺输入」那条新分支而变红：**红了，但红错了理由**。
        #   R91 的「子串包含让负向判据假绿」是同一类事故（判据响了，响的不是被测的那件事）。
        _e1 = {"c28": "test_c28_uninit_performance"}
        _e2 = {"c28": "test_c28_uninit_performance",
               "c22": "test_c22_stress_test"}
        _cases9 = (
            (_okl + "\n{不是 JSON\n", 1, _e1, "坏行"),
            ('{"kind": "budget", "limit": 5.0, "measured": 0, '
             '"node": "c28", "ratio": 0, "unit": "s"}\n', 1, _e1, "measured<=0"),
            ('{"kind": "budget", "limit": 5.0, "node": "c28"}\n', 1, _e1,
             "缺字段"),
            ("", 1, _e1, "有调用点却零记录"),
            ('{"kind": "weird", "limit": 5.0, "measured": 1.0, '
             '"node": "c28", "ratio": 5.0, "unit": "s"}\n', 1, _e1, "kind 非法"),
            ('{"kind": "tolerance", "limit": 5.0, "measured": 1.0, '
             '"node": "c28", "ratio": 5.0, "unit": "s"}\n', 1, _e1,
             "只有宽限记录 ⇒ 没有预算门记录"),
            (_okl + "\n", 2, _e2, "有节点一条记录都没有，且宿主没被跳过"),
            (_okl + "\n", 1, _e2, "两个口径不一致（文本 1 / AST 2）"),
        )
        for _t9, _c9, _e9, _w9 in _cases9:
            _rr, _pp = parse_perf_margins(_t9)
            if perf_margin_problem(_rr, _pp, _c9, expected=_e9):
                good += 1
            else:
                bad += 1
                print("  [selftest] 余量判据样本「%s」没判红" % _w9)
        # R107：**陈旧登记**（记录里有、源码里没有的节点名）也要红 ——
        # 「未登记 ⇒ 红」的另一面就是「陈旧登记 ⇒ 也红」。
        _rr, _pp = parse_perf_margins(
            _okl + "\n" + '{"kind": "budget", "limit": 5.0, "measured": 1.0, '
            '"node": "c99", "ratio": 5.0, "unit": "s"}\n')
        if perf_margin_problem(_rr, _pp, 1, expected=_e1):
            good += 1
        else:
            bad += 1
            print("  [selftest] 余量判据没抓住「记录里的节点名不在源码里」")
        # R107：**感知 skipped** 的正向 —— 缺的那条记录，其宿主这一跑真被跳过了
        _rr, _pp = parse_perf_margins(_okl + "\n")
        if perf_margin_problem(_rr, _pp, 2, expected=_e2,
                               skipped=["test_c22_stress_test"]) is None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 余量判据把「宿主被跳过导致的缺记录」误判成红")
        # R107：推导不出节点名（源码解析不了）⇒ 红，不许退化成弱判据
        if perf_margin_problem(_r9, [], 1) is not None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 余量判据在「读不出节点名」时竟然放行")
        if perf_margin_problem(_r9, [], 1, expected=_e1) is None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 余量判据把好样本判红了")
        if count_perf_margin_callsites("x\n    _emit_perf_margin(1, 2, 3)\n"
                                       "def _emit_perf_margin(n, m, l):\n") == 1 \
                and count_perf_margin_callsites("# _emit_perf_margin(\n") == 0:
            good += 1
        else:
            bad += 1
            print("  [selftest] 调用点分母算错（定义行/注释行不该计）")
        # [R107] AST 口径的节点名推导：**与文本口径各自独立**，且两向都要自证。
        _nsrc = ("def test_a():\n"
                 "    _emit_perf_margin(\"n_one\", 1.0, 2.0)\n"
                 "    _emit_perf_margin('n_two', 1.0, 2.0)\n"
                 "def test_b():\n"
                 "    _emit_perf_margin(\n"
                 "        \"n_three\", 1.0, 2.0)\n"
                 "    _emit_perf_margin(NAME, 1.0, 2.0)\n"
                 "# _emit_perf_margin(\"n_comment\", 1, 2)\n"
                 "def _emit_perf_margin(node, m, l):\n"
                 "    return None\n")
        _n9, _sp9 = perf_margin_nodes(_nsrc)
        if _n9 == {"n_one": "test_a", "n_three": "test_b", "n_two": "test_a"} \
                and len(_sp9) == 3:
            good += 1
        else:
            bad += 1
            print("  [selftest] AST 节点推导不对：%r / %r" % (_n9, _sp9))
        if perf_margin_nodes("def f(:\n") == (None, None):
            good += 1
        else:
            bad += 1
            print("  [selftest] 源码解析不了时未返回 (None, None)（缺输入 → 红）")
        # 跳过行 → 宿主：样本按**实测形状**构造（反斜杠路径；行号 = skip 调用行）
        _sk, _skp = parse_skipped_hosts(
            "SKIPPED [1] tests\\test_matlabc.py:3: 无 node，跳过\n"
            "SKIPPED [1] tests\\test_matlabc.py:99: 落不到任何函数里\n"
            "SKIPPED [1] tests\\other_file.py:1: 别的文件，与本判据无关\n"
            "1 failed, 2 passed, 1 skipped in 1s\n", _sp9)
        if _sk == {"test_a"} and len(_skp) == 1:
            good += 1
        else:
            bad += 1
            print("  [selftest] 跳过行映射不对：%r / %r" % (_sk, _skp))
        # ⑩ [R106] 仓级结构闸门（纯函数，不读盘）：计划块三条判据（+ 两条缺输入）
        #    与围栏两条判据 —— 坏样本必须红、好样本必须绿，否则「0 违规」可能
        #    只是恒真。样本一律**构造**，不读真文件（真文件由本轮的 ✓ 行来证）。
        _plangood = ("# ROUNDS:PLAN v1\n"
                     "0 | 0 | base | act_alpha | 目标甲 | -\n"
                     "1 | A  | t1   | -         | 目标乙 | 还没落地\n"
                     "```\n")
        _actsok = {"actions": ["act_alpha", "act_beta"]}
        _plancases = (
            (_plangood, _actsok, False, "好计划块"),
            (_plangood.replace("act_alpha", "act_alph"), _actsok, True,
             "不在册又没写理由（拼错的动作名即落在此支）"),
            (_plangood.replace("目标乙 | 还没落地", "目标乙 | -"), _actsok, True,
             "`-` 却没写理由"),
            (_plangood.replace("act_alpha | 目标甲 | -",
                               "act_alpha | 目标甲 | 有理由"), _actsok, True,
             "在册动作带着理由"),
            (_plangood.replace("act_alpha | 目标甲 | -",
                               "act_slot_x | 目标甲 | 非环路动作：手工完成"),
             _actsok, False, "非环路动作 + 写了理由（27 行的形态）"),
            (_plangood.replace("act_alpha", ""), _actsok, True, "action 是空串"),
            (_plangood, {"actions": []}, True, "摘要 actions 为空"),
            (_plangood.replace(" | 目标甲 | -", ""), _actsok, True,
             "列数不足 6"),
            ("没有计划头\n", _actsok, True, "找不到计划块"),
        )
        for _pt, _dg, _want, _w in _plancases:
            if bool(plan_gate_problems(_pt, _dg)) == _want:
                good += 1
            else:
                bad += 1
                print("  [selftest] 计划块闸门样本「%s」判反" % _w)
        _fgood = "A\n```\nx\n```\n```\ny\n```\nB\n"   # 关旧块+开新块相邻：正常
        _fencecases = (
            (_fgood, False, "好围栏（相邻但分属两对）"),
            ("A\n```\n```\nX\n```\nY\n```\n", True, "零长度代码块"),
            ("A\n```\nX\n", True, "奇数围栏"),
        )
        for _ft, _want, _w in _fencecases:
            if bool(md_fence_problems(_ft)[0]) == _want:
                good += 1
            else:
                bad += 1
                print("  [selftest] 围栏判据样本「%s」判反" % _w)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad, good


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
