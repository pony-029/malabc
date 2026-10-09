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

两向自证：R1/R2/R3/R4 各配独立坏样本（必须红）与好样本（必须过），
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
    "tools/check_help_contract.py": {
        0: "全部一致",
        1: "发现不一致（R1/R1b/R2/R3/R4 任一红）",
        2: "缺输入（入口脚本缺失 / 解析不到 docstring）",
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
        0: "两侧结构对等",
        1: "发现不对等（P1/P2 任一红）",
        2: "缺输入（任一 README 不存在）",
    },
    "tools/check_subprocess_hygiene.py": {
        0: "子进程卫生全部合规",
        1: "有违规（捕获输出却继承 stdin / 缺 timeout / 未登记）",
        2: "缺输入",
    },
}

GUARD_SCRIPTS = tuple(sorted(GUARD_CONTRACT))

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
# 相对界的做法：记一份**已批准快照**，实测值相对快照的漂移不得超过 ±30%
# （并给 512 B 最小宽容，免得小文件被几个字符就判红）。两臂**取严**：
#   matlabc.py：64 KiB 绝对上界 vs 48593×1.3≈63 KiB 相对上界 ⇒ 相对界先起作用
#   matlabc_ask.py：16 KiB 绝对上界 vs 919×1.3≈1.2 KiB 相对上界 ⇒ 相对界先起作用
#
# 为什么用「已批准快照」而不是 C''8 原文的「上一 tag」：
# 本仓**至今没有任何 tag**（`git tag` 为空），那个基线根本不存在。
# 快照与 tag 的唯一差别是「谁批准」，而快照随时可用、而且在 diff 里看得见 ——
# 等本仓开始打 tag 时，这道门一行都不用改。
# 漂移超限时的正当做法**不是**放宽这两个数，而是同步更新快照
# （那是一次显式的、可评审的批准动作 —— 这正是棘轮的意义）。
HELP_BYTES_SNAPSHOT = {
    "matlabc.py": 48593,
    "matlabc_flow.py": 2075,
    "matlabc_ask.py": 919,
    "matlabc_mcp.py": 0,
    "gui.py": 2651,
}
HELP_DRIFT_MAX = 0.30
HELP_DRIFT_FLOOR = 512

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


def _run_safe_example(root, script, argv):
    """真跑一条登记的示例命令，返回 (rc, out_bytes) 或 (None, b"") 表示超时。

    纪律（与 check_subprocess_hygiene.py 的要求一致，这里是它的对手方）：
      * `stdin=DEVNULL`：绝不继承调用方的 stdin —— 本仓真发生过 stdio MCP
        server 在继承的 stdin 上等满 180s 的事故（R62-R31e）。
      * `timeout=RUN_TIMEOUT`：挂死必须变成红，而不是让门永远等着。
      * 捕获输出，因为要断言「rc 与字节数」这两个事实。
    """
    import subprocess
    p = os.path.join(root, script)
    try:
        r = subprocess.run([sys.executable, p] + list(argv), cwd=root,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=RUN_TIMEOUT)
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


def _r5_verdict(script, n_bytes, lo, hi, snapshot):
    """R5 的判定，抽成**纯函数**（自证不必起进程）。

    两条臂，**取严**：
      臂 A 绝对界：lo <= n_bytes <= hi
      臂 B 相对界：|n_bytes - snapshot| <= max(HELP_DRIFT_MAX*snapshot, FLOOR)
    返回问题字符串，或 None 表示通过。
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
    allow = max(int(HELP_DRIFT_MAX * snapshot), HELP_DRIFT_FLOOR)
    drift = n_bytes - snapshot
    if abs(drift) <= allow:
        return None
    how = "膨胀" if drift > 0 else "缩水"
    return ("R5 %s: --help %d 字节相对已批准快照 %d 漂移 %+d 字节（%s %.0f%%，"
            "允许 ±%d）—— 若是**合法增长**，请在同一个提交里把 "
            "HELP_BYTES_SNAPSHOT['%s'] 更新为 %d 并在提交信息里说明理由；"
            "不要放宽 HELP_DRIFT_MAX"
            % (script, n_bytes, snapshot, drift, how,
               100.0 * drift / snapshot if snapshot else 0.0, allow,
               script, n_bytes))


def audit(root, on_problem, cache=None):
    """对真实仓库施加 R1/R2/R3/R4；返回检查过的脚本数。

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

        # ---- R5：帮助体积棘轮（R33/C'8 立，R38/C''8 改成**两臂取严**） ----
        lo, hi = HELP_BYTES.get(script, (0, 0))
        if hi > 0:
            hk = script + "::--help"
            if hk not in cache:
                cache[hk] = _run_safe_example(root, script, ["--help"])
            _rc, _out = cache[hk]
            n_bytes = len(_out)
            if _rc is None:
                on_problem("R5 %s: `--help` 超时，拿不到体积" % script)
            else:
                msg = _r5_verdict(script, n_bytes, lo, hi,
                                  HELP_BYTES_SNAPSHOT.get(script))
                if msg:
                    on_problem(msg)
    return n


def audit_guards(root, on_problem):
    """R33（C'7）：对护栏脚本施加 R1（+反向+陈旧）与 R2。返回核对过的脚本数。"""
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
    return n


def on_problem_collector(bucket):
    def _cb(msg):
        bucket.append(msg)
    return _cb


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
    # 臂 B：相对快照。这条是 R38 新加的核心 —— 它必须在**绝对界毫无反应**时抓住。
    expect("坏样本：绝对界无反应但相对界抓到膨胀",
           _r5_verdict("x.py", 3000, 400, 16384, 1000) is not None, True)
    expect("坏样本：相对界抓到缩水（−50%，超出 512 B 宽容）",
           _r5_verdict("x.py", 1000, 400, 16384, 2000) is not None, True)
    # 好样本：漂移在允许范围内（含 512 B 最小宽容对小文件的保护）
    expect("好样本：漂移 +25% 放行（正处在允许内）",
           _r5_verdict("x.py", 1250, 400, 16384, 1000) is not None, False)
    expect("好样本：小文件 ±512 B 宽容生效",
           _r5_verdict("x.py", 1400, 400, 16384, 1000) is not None, False)
    expect("好样本：无快照 = 只有绝对界",
           _r5_verdict("x.py", 9999, 400, 16384, None) is not None, False)
    expect("好样本：(0,0) = 显式不设界（stdio server 放行）",
           _r5_verdict("x.py", 999999, 0, 0, 0) is not None, False)

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
        finally:
            GUARD_CONTRACT.clear()
            GUARD_CONTRACT.update(saved)
            globals()["GUARD_SCRIPTS"] = saved_scripts

    # ---- 真实仓库整体核对 ----
    root = repo_root()
    probs = []
    cache = {}
    n = audit(root, on_problem_collector(probs), cache=cache)
    ng = audit_guards(root, on_problem_collector(probs))
    print("  真实仓库：核对 %d 个入口脚本 + %d 个护栏脚本，发现 %d 项不一致"
          % (n, ng, len(probs)))
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
    if n == 0:
        print("check_help_contract: 一个入口脚本都没核对到（缺输入 → 红）")
        return 2
    if probs:
        print("check_help_contract: %d 项不一致" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_help_contract: OK（%d 个入口脚本 + %d 个护栏脚本的退出码在代码与"
          "帮助之间双向一致；入口帮助骨架齐备；%d 条示例命令已真跑且 rc=0）"
          % (n, ng, len(RUNNABLE)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
