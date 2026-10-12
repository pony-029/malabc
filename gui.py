# -*- coding: utf-8 -*-
"""MATLAB 分析器 · 图形界面启动器。

为什么要有它：matlabc 的命令行有几十个开关，第一次用的人不知道该勾哪几个。
GUI 把这些开关收敛成一张表单 —— 选目录、勾输出、选 AI 时机 —— 一键分析，
结束后自动在浏览器打开结果。**表单能做的事，命令行全能做**；GUI 只是入口。

它怎么跑：

    ┌────────────────┐   点「开始分析」   ┌──────────────────────┐
    │  表单（tkinter）│──────────────────▶│ build_cli_args(form) │  ← 纯函数，可单测
    │ 目录/输出/AI    │                   └──────────┬───────────┘
    └────────────────┘                              │ 拼成
            ▲                                       ▼
            │ 回填（从配置文件）            python matlabc.py <目录> --browse ...
            │                                       │
    ┌───────┴────────┐                   ┌──────────▼───────────┐
    │ 配置 JSON 文件  │                   │ 子进程（流式读输出）  │
    │ 存/取同一张表单 │                   │ 日志框实时滚动，不卡界面│
    └────────────────┘                   └──────────┬───────────┘
                                                    ▼
                                          分析完成后用系统原生方式打开结果
                                          （Windows startfile / macOS open / Linux xdg-open）

用法：
    python gui.py                 # 启动图形界面
    python gui.py --selftest      # 无界面自检：构造表单并校验 CLI 参数映射
    python gui.py --help          # 就是我，你现在看到的这些

设计要点（也是为什么它好改）：
  * build_cli_args(form) 是**纯函数**，负责「表单 → 命令行参数」的映射，
    不开窗口也能单测；GUI 只做收集与展示。所以 --selftest 能覆盖真正的风险点。
  * 配置 JSON 双向：`--config` 传给分析器当基础配置（CLI 显式参数优先），
    同时支持把当前表单另存为配置、或从配置回填表单，方便复用同一套参数。
  * 分析是**子进程 + 流式输出**，界面不会被长时间任务冻住；可随时点「停止」
    （按进程树终止，不留孤儿）。

退出码：
    0  = 正常（关窗、--selftest 通过、--help 打印完 都算）
    1  = 启动期异常（极少数环境缺 tkinter；stderr 会给原因）

诚实边界：
  * 需要系统自带 tkinter。极简发行版可能没装（Debian/Ubuntu 上装 python3-tk）。
  * 单例守卫：已经在跑时再开一个只会弹一句「已在运行」然后退出 —— 这是设计，
    不是启动失败（与分析器的「多实例」病根同类）。
  * 日志框显示的是**子进程原始输出**，不做美化。要结构化结果请看输出目录里的
    HTML / JSON / SARIF / Markdown。
"""
import json
import os
import sys
import subprocess
import tempfile

APP_TITLE = "matlabc"
APP_VERSION = "1.1.0"

# ---------------------------------------------------------------------------
# `--help` 文本。刻意放在模块级常量里、并在 main() 的**最前面**处理：
# 早先 `python gui.py --help` 会直接走到「启动 GUI」分支（或撞上单例守卫），
# 于是「问帮助」变成「开窗口」或「静默退出」—— 对命令行用户是纯粹的意外。
# 帮助必须在任何副作用（单例锁、tkinter、子进程）之前返回。
# ---------------------------------------------------------------------------
# R89：调用关系图的**节点身份口径**（三档）。GUI **不** import 分析器
# （1.6 MB 的模块不进界面进程），所以这几档字面量在这里重抄了一份 ——
# 重抄就有漂移风险，对手方在
# `tests/test_matlabc.py::test_r89_gui_callgraph_card`：断言这里的三档与
# `matlabc.py --callgraph-identity` 的 choices、以及 `callrel` 自己导出的
# 口径**三者两两相等**。默认档由 `build_cli_args` **刻意不下发**
# （留空 ⇒ 用 CLI 默认），这样「界面没动过」时命令行逐字与 R88 一致。
CALLGRAPH_IDENTITIES = ("definition-site-local", "definition-site",
                       "callee-name")
CALLGRAPH_IDENTITY_DEFAULT = CALLGRAPH_IDENTITIES[0]

HELP_TEXT = """\
matlabc GUI —— 把命令行开关收敛成一张表单，一键分析并打开结果。

用法：
    python gui.py                 # 启动图形界面
    python gui.py --selftest      # 无界面自检（校验「表单 -> 命令行参数」映射）
    python gui.py --help          # 显示本帮助

表单做什么（每一格都对应 matlabc.py 的真实参数）：

    ┌────────────────┬────────────────────────────────────────────┐
    │ 工程目录       │ 等价于 `python matlabc.py <目录>`            │
    │ 输出目录       │ 报告与站点落在哪                            │
    │ 静态检查       │ 勾选规则名，等价于 --checks uninit,taint     │
    │ 输出格式       │ 浏览站点 / HTML / JSON / SARIF / Markdown    │
    │ 可复现         │ 省略时间戳，便于 diff，等价于 --reproducible │
    │ 递归深度       │ 限制扫描深度；留空=不限                      │
    │ 调用图节点上限 │ 大工程防爆图，等价于 --max-nodes             │
    │ AI 引入时机    │ off / prompts / ask / auto，等价于 --ai-mode │
    │ 在线 AI        │ 等价于 --provider                            │
    │ 语言           │ auto / matlab / c / py / js，等价于 --lang   │
    │ CI 与增量      │ --git-diff / --gate / --max-warnings /       │
    │                │ --sarif-base（只分析本次变更、或按阈值卡口） │
    │ 二进制诊断     │ --lib-resolve / --lib-path /                 │
    │                │ --lib-max-nodes：库名→文件→递归分析依赖      │
    │                │ --binary-attach：额外点名库文件或库名        │
    │ 调用关系       │ --callgraph <文件> / --callgraph-focus       │
    │                │ --callgraph-depth / --callgraph-max-nodes    │
    │                │ --callgraph-identity <口径>                  │
    │                │ 格式 .json / .dot / .mmd                     │
    └────────────────┴────────────────────────────────────────────┘

二进制诊断（R86-2 · 移植 REA 的静态证据契约）：
    填上之后，分析器会把「代码里引用的库名字」（Makefile 的 -lfoo、
    CMakeLists 的 target_link_libraries、ELF 的 DT_NEEDED）解析成磁盘上的
    真实文件并逐个分析，再沿依赖逐层下钻。三态语义：resolved（唯一命中）/
    ambiguous（同名多份，不猜，但按候选自己的位数排除 32/64 位孪生）/
    not_found（未找到，并列列出搜索过的目录）。
      - 库引用解析深度：下钻层数，0=关（默认）。
      - 额外指定库：库名或路径（等价于 --binary-attach）；留空则由构建脚本推断。
      - 追加库搜索目录：追加，不替换平台默认目录（等价于 --lib-path）。
      - 一次最多解析文件数：达到上限的节点记 skipped，与 not_found 严格区分：
        「我没看」不等于「找不到」（等价于 --lib-max-nodes）。
    只看一个 .so/.dll、不跑源码分析：python matlabc.py --binary libfoo.so

调用关系（可选 · R86-3 投影 / R88 身份口径 / R89 解析阶梯）：
    等价开关：--callgraph / --callgraph-focus / --callgraph-depth /
              --callgraph-max-nodes / --callgraph-identity
    填一个输出文件，就把「谁调用谁」导出成**有界**投影：度数排行、递归环、
    跨文件计数、焦点邻域 —— 规模无关，输出恒为 KB 级（内核整树有 700 万条边，
    而 `--json-level summary` 的载荷**结构上不含**边，没有这一条就没有产物）。
      - 焦点函数：以它为根做双向 BFS（它调了谁、谁调了它）；留空取扇入最高的枢纽。
      - 深度 / 节点上限：撞上限置 truncated.hit_node_cap —— 「我没展开」不等于
        「没有关系」。
      - 身份口径：definition-site-local（默认，同文件 → 同翻译单元，只对 C 启用）/
        definition-site / callee-name（同名合并，环可能含假阳性）。换口径**一条边
        都不删**，逐档「判得出的 / 判不出的」计数在产物的 resolution 块里。
    只看一个函数的邻域：python matlabc.py <目录> --callgraph-focus foo --callgraph cg.json

配置文件（可加载/可另存）：把上面这张表单存成 JSON，下次直接回填。
    加载：界面「加载配置」→ 选 JSON → 表单被填好
    另存：界面「保存配置」→ 生成 JSON（即 matlabc.py 的 --config 格式）
    命令行：python matlabc.py <目录> --config my.json --browse

退出码：
    0  = 正常（关窗 / --selftest 通过 / --help 打印完）
    1  = 启动期异常（极少数环境缺 tkinter；stderr 会给原因）

提示：
  * 已经在运行时再启动一个，只会提示「已在运行」然后退出（单例守卫，设计如此）。
  * 分析在子进程里跑，日志框实时滚动，可随时「停止」，不会留孤儿进程。
  * 想要可复现的自动化，直接用命令行；GUI 面向手工探索。
"""


def _write_help(text):
    """把帮助文本写到 stdout，强制 UTF-8。

    被管道/CI 调用时 Python 会退回 locale 编码（中文 Windows 是 GBK），
    与 matlabc.py 的处理保持一致：先 reconfigure，失败再退回写 buffer。
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


def build_cli_args(form):
    """把表单字典映射为 matlabc.py 的命令行参数列表（纯函数，可单测）。

    form 字段（全部可选，缺省走合理默认）：
        src          工程根目录（可空：此时必须提供 config，由配置里的 dir 指定）
        out          输出目录（默认 <src>/_ma_site）
        checks       启用的静态检查名列表（默认全部）
        browse       bool 生成交互浏览站点
        html         bool 生成 HTML 报告
        json         bool 输出 JSON
        sarif        bool 输出 SARIF
        md           bool 输出 Markdown
        reproducible bool 可复现（省略时间戳）
        depth        int  递归深度（None=不限制）
        max_nodes    int  调用图最大节点（None=不限制）
        ai_mode      str  off/prompts/ask/auto
        provider     str  在线 AI provider（ask/auto 时用）
        lang         str  auto/matlab/c/py/js（默认 auto=自动识别）
        config       str  基础配置 JSON 路径（可选；CLI 显式参数优先于配置）
        git_diff     bool 仅分析 git 变更文件（PR 增量）
        git_diff_base str  git-diff 的对比基准（留空=HEAD）
        gate         bool 质量门禁（超阈值退出码非 0）
        gate_baseline str 门禁基线文件（留空=.debt_trend.json）
        max_warnings int  最大告警数阈值（None=不限制）
        sarif_base   str  基线 SARIF 文件（启用增量、仅保留新增告警）
        binary_attach str  额外点名要分析的库（库名或路径，逗号分隔）
        lib_resolve  int  库引用解析下钻层数（None=不传；0=显式关闭）
        lib_path     str  追加库搜索目录（逗号分隔；追加而非替换）
        lib_max_nodes int 引用解析一次最多分析几个文件（None=不传）
        callgraph    str  导出调用关系的有界投影（.json/.dot/.mmd；留空=不导出）
        callgraph_focus str  焦点子图的根函数名（留空=扇入最高的枢纽）
        callgraph_depth int  焦点子图展开层数（None=不传，用 CLI 默认）
        callgraph_max_nodes int  焦点子图节点上限（None=不传，用 CLI 默认）
        callgraph_identity str  节点身份口径（三档；**默认档不下发**）
    """
    args = []
    config = form.get("config")
    src = form.get("src") or ""
    if not src and not config:
        raise ValueError("请先选择工程目录，或加载一个包含 dir 的配置 JSON")
    if src:
        args.append(src)
    if config:
        args += ["--config", config]
    out = form.get("out") or (os.path.join(src, "_ma_site") if src else "")
    # 修复「站点跑到意料之外目录」：配置里 browse 常是相对路径（如 "site"），而分析器
    # 以子进程 cwd 解析相对路径，导致站点落到工程目录而非用户预期位置，用户以为
    # 「没生成」。这里基于工程目录把相对输出路径解析为绝对路径，消除歧义。
    if out and not os.path.isabs(out) and src:
        out = os.path.join(src, out)
    # 统一分隔符为「正斜杠」：避免 "C:/a\b" 混合路径（Windows 下易被误解析）。
    if out:
        out = out.replace("\\", "/")
    if form.get("browse") is not False and out:
        args += ["--browse", out]
    if form.get("html") and out:
        # --html 需要「文件路径」而非目录，否则会被当作目录名创建。
        target = out if out.lower().endswith((".html", ".htm")) else os.path.join(out, "report.html")
        args += ["--html", target.replace("\\", "/")]
    if form.get("json") and out:
        args += ["--json", os.path.join(out, "report.json").replace("\\", "/")]
    if form.get("sarif") and out:
        # 坑位修复：--sarif 需要「文件路径」参数，不能裸传开关（否则 argparse 报
        # "argument --sarif: expected one argument"）。
        target = out if out.lower().endswith(".sarif") else os.path.join(out, "result.sarif")
        args += ["--sarif", target.replace("\\", "/")]
    if form.get("md") and out:
        # 修复：并不存在 --markdown 开关；Markdown 报告由 -o/--output 指定文件路径生成。
        target = out if out.lower().endswith(".md") else os.path.join(out, "report.md")
        args += ["-o", target.replace("\\", "/")]
    if form.get("reproducible"):
        args += ["--reproducible"]
    checks = form.get("checks")
    if checks:
        args += ["--checks", ",".join(checks)]
    if form.get("depth") is not None:
        args += ["--depth", str(form["depth"])]
    if form.get("max_nodes") is not None:
        args += ["--max-nodes", str(form["max_nodes"])]
    ai_mode = form.get("ai_mode", "off")
    args += ["--ai-mode", ai_mode]
    if ai_mode in ("ask", "auto") and form.get("provider"):
        # provider 通过环境变量传给主流程（auto 用 MA_AI_PROVIDER；ask 在交互时再取）
        os.environ["MA_AI_PROVIDER"] = form["provider"]
    lang = form.get("lang")
    if lang and lang != "auto":
        args += ["--lang", lang]
    # ---- CI 与增量 ----
    # --git-diff 为可选值参数：给了基准就带基准，否则裸传（默认 HEAD）。
    if form.get("git_diff"):
        base = (form.get("git_diff_base") or "").strip()
        args += ["--git-diff", base] if base else ["--git-diff"]
    # --gate 同为可选值参数：给了基线就带基线，否则裸传（默认 .debt_trend.json）。
    if form.get("gate"):
        base = (form.get("gate_baseline") or "").strip()
        args += ["--gate", base] if base else ["--gate"]
    if form.get("max_warnings") is not None:
        args += ["--max-warnings", str(form["max_warnings"])]
    if form.get("sarif_base"):
        args += ["--sarif-base", form["sarif_base"]]
    # ---- 二进制诊断 / 库引用解析（R86-2）----
    # 这一段是「代码里涉及的二进制都要被处理」的界面入口：深度 0=关，
    # 其余三格只在用户真填了才进命令行 —— 保持命令行精简，也保证默认行为逐字不变。
    if form.get("binary_attach"):
        args += ["--binary-attach", form["binary_attach"]]
    if form.get("lib_resolve") is not None:
        args += ["--lib-resolve", str(form["lib_resolve"])]
    lib_path = (form.get("lib_path") or "").strip()
    if lib_path:
        args += ["--lib-path", lib_path.replace("\\", "/")]
    if form.get("lib_max_nodes") is not None:
        args += ["--lib-max-nodes", str(form["lib_max_nodes"])]
    # ---- 调用关系（有界投影 R86-3 / 身份口径 R88 / 解析阶梯 R89）----
    # 三段递进：没填输出文件时**一个参数都不下发**（默认行为逐字不变）；
    # 填了才把焦点 / 深度 / 节点上限一起带上（它们只在 --callgraph 存在时
    # 才有意义）；身份口径的**默认档刻意不下发** —— 让「界面没动过」的命令
    # 行与 R88 逐字相同。
    cg = (form.get("callgraph") or "").strip()
    if cg:
        args += ["--callgraph", cg.replace("\\", "/")]
        focus = (form.get("callgraph_focus") or "").strip()
        if focus:
            args += ["--callgraph-focus", focus]
        if form.get("callgraph_depth") is not None:
            args += ["--callgraph-depth", str(form["callgraph_depth"])]
        if form.get("callgraph_max_nodes") is not None:
            args += ["--callgraph-max-nodes", str(form["callgraph_max_nodes"])]
        ident = (form.get("callgraph_identity") or "").strip()
        if ident and ident != CALLGRAPH_IDENTITY_DEFAULT:
            args += ["--callgraph-identity", ident]
    return args


def load_config_file(path):
    """读取 JSON 配置文件，返回 dict（纯函数，可单测）。

    容错：文件不存在 / 非法 JSON / 顶层非对象都会抛 ValueError 并给出中文提示。
    """
    if not path:
        raise ValueError("配置路径为空")
    if not os.path.isfile(path):
        raise ValueError("配置文件不存在：%s" % path)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        raise ValueError("配置 JSON 解析失败：%s" % e)
    except OSError as e:
        raise ValueError("无法读取配置文件：%s" % e)
    if not isinstance(data, dict):
        raise ValueError("配置文件顶层必须是 JSON 对象 {}")
    return data


def config_to_form(cfg):
    """把配置字典转换为表单可用的字段（纯函数，可单测）。

    仅回填本 GUI 支持的字段；未知字段忽略（仍会原样通过 --config 交给分析器）。
    """
    form = {}
    if not isinstance(cfg, dict):
        return form
    if cfg.get("dir"):
        form["src"] = str(cfg["dir"])
    browse = cfg.get("browse")
    if browse:
        form["out"] = str(browse)
    # 修复：原实现只从配置里取了 browse 的「路径」写入 out，却从未回填「交互式浏览
    # 站点」复选框状态，导致加载配置后界面上该复选框可能显示为未勾选（与实际配置
    # 不符），用户误以为不会生成站点。此处显式回填，保证界面与配置一致。
    form["browse"] = bool(browse) if browse is not None else True
    form["html"] = bool(cfg.get("html"))
    form["json"] = bool(cfg.get("json"))
    form["sarif"] = bool(cfg.get("sarif"))
    form["reproducible"] = bool(cfg.get("reproducible"))
    if cfg.get("lang"):
        form["lang"] = str(cfg["lang"])
    checks = cfg.get("checks")
    if checks and checks != "all":
        if isinstance(checks, (list, tuple)):
            form["checks"] = [str(c) for c in checks]
        else:
            form["checks"] = [c.strip() for c in str(checks).split(",") if c.strip()]
    ai = cfg.get("ai") or {}
    if isinstance(ai, dict) and ai.get("default_provider"):
        form["provider"] = str(ai["default_provider"])
    # 其余分析器配置字段：加载时一并回填界面（CLI 显式参数仍优先于这些）
    if cfg.get("ai_mode"):
        form["ai_mode"] = str(cfg["ai_mode"])
    if cfg.get("depth") is not None and cfg["depth"] != "":
        form["depth"] = str(cfg["depth"])
    if cfg.get("max_nodes") is not None and cfg["max_nodes"] != "":
        form["max_nodes"] = str(cfg["max_nodes"])
    # CI 与增量相关字段（与 CLI 的配置键同名，可从 JSON 回填界面）
    if cfg.get("git_diff"):
        form["git_diff"] = True
        base = cfg.get("git_diff_base")
        if base and base is not True:
            form["git_diff_base"] = str(base)
    if cfg.get("gate"):
        form["gate"] = True
        gbase = cfg.get("gate_baseline")
        if gbase:
            form["gate_baseline"] = str(gbase)
    if cfg.get("max_warnings") is not None and cfg["max_warnings"] != "":
        form["max_warnings"] = str(cfg["max_warnings"])
    if cfg.get("sarif_base"):
        form["sarif_base"] = str(cfg["sarif_base"])
    # R86-2：二进制诊断四格（与 CLI 的配置键同名，可从 JSON 回填界面）。
    # 少了这一段的后果是**沉默的**：配置里写了 lib_resolve，界面却显示空白，
    # 用户以为没生效 —— 与分析器实际行为不符（回填与真正下发是两件事，必须都做）。
    if cfg.get("binary_attach"):
        form["binary_attach"] = str(cfg["binary_attach"])
    if cfg.get("lib_resolve") is not None and cfg["lib_resolve"] != "":
        form["lib_resolve"] = str(cfg["lib_resolve"])
    if cfg.get("lib_path"):
        form["lib_path"] = str(cfg["lib_path"])
    if cfg.get("lib_max_nodes") is not None and cfg["lib_max_nodes"] != "":
        form["lib_max_nodes"] = str(cfg["lib_max_nodes"])
    # R89：调用关系五格（同上 —— 回填与真正下发是**两件事**，缺一样就会
    # 出现「配置里写了、界面却是空白」的沉默故障：用户以为没生效）。
    if cfg.get("callgraph"):
        form["callgraph"] = str(cfg["callgraph"])
    if cfg.get("callgraph_focus"):
        form["callgraph_focus"] = str(cfg["callgraph_focus"])
    if cfg.get("callgraph_depth") is not None and cfg["callgraph_depth"] != "":
        form["callgraph_depth"] = str(cfg["callgraph_depth"])
    if (cfg.get("callgraph_max_nodes") is not None
            and cfg["callgraph_max_nodes"] != ""):
        form["callgraph_max_nodes"] = str(cfg["callgraph_max_nodes"])
    if cfg.get("callgraph_identity"):
        form["callgraph_identity"] = str(cfg["callgraph_identity"])
    return form


def analyzer_target():
    """返回要调用的分析器目标：开发态为 matlabc.py；冻结态为同目录的 matlabc 可执行文件。"""
    here = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        exe = "matlabc.exe" if sys.platform.startswith("win") else "matlabc"
        return os.path.join(os.path.dirname(sys.executable), exe)
    return os.path.join(here, "matlabc.py")


class RunGate(object):
    """分析任务的重入闸门：保证同一时刻只有一个分析在跑。

    为什么不用按钮的 disabled 状态做闸门：控件禁用发生在 ``_set_running`` 的
    try/except 内，一旦按钮因主题切换被重建或引用失效，禁用会**静默失败**，
    此时用户连点「开始分析」就会并发启动多个 matlabc 进程——它们同写一个站点
    目录（还互相 ``_clean_browse_dir`` 删产物）、各自弹一次「完成」对话框，
    表现为「反复弹窗」。闸门用独立布尔标记，与控制件状态解耦，任何路径都可靠。
    """

    def __init__(self):
        self._busy = False

    def acquire(self):
        """尝试占用；已在运行则返回 False（调用方据此忽略本次点击）。"""
        if self._busy:
            return False
        self._busy = True
        return True

    def release(self):
        self._busy = False

    @property
    def busy(self):
        return self._busy


def ensure_single_instance(lock_path=None):
    """保证同时只有一个 GUI 主进程（与 RunGate 防止多个分析进程同属一类「多实例」病根）。

    机制：在临时目录写锁文件记录本进程 PID，配合进程存活探测判断「是否已有实例在跑」。
    跨平台、无外部依赖；进程崩溃残留的锁文件在 PID 已死亡时会被覆盖，不会永久误杀。
    返回 True 表示本进程是唯一的，False 表示已有实例在运行。
    """
    lock = lock_path or os.path.join(tempfile.gettempdir(), "matlabc_gui.lock")
    mypid = os.getpid()
    if os.path.exists(lock):
        try:
            with open(lock, "r", encoding="utf-8") as fh:
                oldpid = int(fh.read().strip())
            if _pid_alive(oldpid):
                return False
        except (OSError, ValueError):
            pass  # 锁文件损坏：当作无主，覆盖
    try:
        with open(lock, "w", encoding="utf-8") as fh:
            fh.write(str(mypid))
    except OSError:
        pass
    return True


def _pid_alive(pid):
    """跨平台判断进程是否存活（不依赖 psutil）。"""
    if sys.platform.startswith("win"):
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(0x1000, 0, pid)
        if not h:
            return False
        # 0 = 已退出（信号态）；非 0（WAIT_TIMEOUT=258） = 仍在运行
        rc = kernel32.WaitForSingleObject(h, 0)
        kernel32.CloseHandle(h)
        return rc != 0
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def open_output(path):
    """用系统默认方式打开结果（目录或文件）。"""
    if not path or not os.path.exists(path):
        return False
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.call(["open", path])
    else:
        subprocess.call(["xdg-open", path])
    return True


def open_in_browser(html_path):
    """用默认浏览器打开本地 HTML。

    Windows 上同样 os.startfile 即可，但显式走 webbrowser 更贴合「打开站点」的
    语义，避免用户看到的是资源管理器窗口而误以为「站点打不开」。
    返回 True 表示已发起打开。
    """
    if not html_path or not os.path.exists(html_path):
        return False
    if sys.platform.startswith("win"):
        try:
            os.startfile(html_path)
            return True
        except OSError:
            pass
    try:
        import webbrowser
        return webbrowser.open(pathlib_path_uri(html_path))
    except Exception:
        return False


def pathlib_path_uri(p):
    """把本地绝对路径转为规范的 file:// URL（正确的正斜杠与百分号转义）。"""
    import pathlib
    try:
        return pathlib.Path(os.path.abspath(p)).as_uri()
    except ValueError:
        # 极少数非本地驱动器场景，退回手拼并统一分隔符
        return "file:///" + os.path.abspath(p).replace("\\", "/")


# ---------------------------------------------------------------------------
# 主题
# ---------------------------------------------------------------------------
# 调色板：浅色 / 深色两套，供 ttk 样式与 tk 原生控件（标题、日志框）统一取色。
PALETTES = {
    "light": {
        "bg": "#f4f6f9", "card": "#ffffff", "fg": "#1f2328", "muted": "#5b6470",
        "accent": "#2563eb", "accent_fg": "#ffffff", "border": "#d8dee6",
        "entry": "#ffffff", "log_bg": "#ffffff", "log_fg": "#1f2328",
    },
    "dark": {
        "bg": "#1b1d21", "card": "#24262b", "fg": "#e6e6e6", "muted": "#9aa4b2",
        "accent": "#3b82f6", "accent_fg": "#ffffff", "border": "#33363c",
        "entry": "#2c2f35", "log_bg": "#141518", "log_fg": "#d7dde5",
    },
}


def _apply_theme(root, style, widgets, default_theme, theme):
    """零依赖主题切换（浅色 / 深色），纯 ttk 样式 + 原生控件配色。

    所有配置都包在 try 中：任一平台不支持的样式键都不会导致 GUI 启动失败。
    widgets 为需要额外着色的原生控件集合，如 {"log": Text, "title": Label}。
    """
    pal = PALETTES.get(theme, PALETTES["light"])
    try:
        style.theme_use("clam")
    except Exception:
        pass
    bg, card, fg = pal["bg"], pal["card"], pal["fg"]
    for name in (".", "TFrame", "TLabel", "TCheckbutton", "TRadiobutton",
                 "TButton", "TCombobox", "TNotebook", "TEntry",
                 "TLabelframe", "TLabelframe.Label"):
        try:
            style.configure(name, background=bg, foreground=fg)
        except Exception:
            pass

    # 卡片：白/深灰底的容器与分组框
    try:
        style.configure("Card.TFrame", background=card)
        style.configure("Card.TLabel", background=card, foreground=fg)
        style.configure("CardMuted.TLabel", background=card, foreground=pal["muted"])
    except Exception:
        pass
    # 分组框：用边框色 + 卡片底色
    try:
        style.configure("TLabelframe", background=card, bordercolor=pal["border"],
                        relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=card, foreground=pal["accent"])
    except Exception:
        pass
    # 输入框
    try:
        style.configure("TEntry", fieldbackground=pal["entry"], foreground=fg,
                        insertcolor=fg, bordercolor=pal["border"], lightcolor=card,
                        darkcolor=card, borderwidth=1, relief="solid", padding=4)
    except Exception:
        pass
    # 按钮：主按钮（强调色）/ 次按钮
    try:
        style.configure("TButton", background=pal["entry"], foreground=fg,
                        bordercolor=pal["border"], focuscolor=pal["accent"],
                        padding=(10, 6), relief="flat")
        style.map("TButton",
                  background=[("active", pal["accent"]), ("pressed", pal["accent"])],
                  foreground=[("active", pal["accent_fg"]), ("pressed", pal["accent_fg"])])
        style.configure("Accent.TButton", background=pal["accent"], foreground=pal["accent_fg"],
                        bordercolor=pal["accent"], focuscolor=pal["accent"],
                        padding=(14, 7), relief="flat",
                        font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton",
                  background=[("active", pal["accent"]), ("pressed", pal["border"])])
    except Exception:
        pass
    # 下拉与复选框
    try:
        style.configure("TCheckbutton", background=card, foreground=fg)
        style.map("TCheckbutton", background=[("active", card)])
        style.configure("TCombobox", fieldbackground=pal["entry"], foreground=fg,
                        background=pal["entry"], arrowcolor=fg)
        style.map("TCombobox",
                  fieldbackground=[("readonly", pal["entry"])],
                  foreground=[("readonly", fg)])
    except Exception:
        pass

    try:
        root.configure(background=bg)
    except Exception:
        pass
    log = widgets.get("log")
    if log is not None:
        try:
            log.configure(background=pal["log_bg"], foreground=pal["log_fg"],
                          insertbackground=pal["log_fg"], selectbackground=pal["accent"])
        except Exception:
            pass
    title = widgets.get("title")
    if title is not None:
        try:
            title.configure(background=bg, foreground=pal["accent"])
        except Exception:
            pass
    band = widgets.get("band")
    if band is not None:
        try:
            band.configure(background=card)
        except Exception:
            pass


def _launch_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("%s %s" % (APP_TITLE, APP_VERSION))
    root.geometry("880x760")
    root.minsize(760, 620)
    root.resizable(True, True)
    style = ttk.Style()
    _default_theme = style.theme_use()

    # 把 GUI 里任何未捕获异常（含 mainloop 回调中的）显式弹窗，避免冻结态静默崩溃。
    def _report_exc(exc, val, tb):
        import traceback as _tb
        text = "".join(_tb.format_exception(exc, val, tb))
        try:
            messagebox.showerror("运行出错", text)
        except Exception:
            pass
    root.report_callback_exception = _report_exc

    form = {
        "src": tk.StringVar(),
        "out": tk.StringVar(),
        "config": tk.StringVar(),
        "browse": tk.BooleanVar(value=True),
        "html": tk.BooleanVar(value=False),
        "json": tk.BooleanVar(value=False),
        "sarif": tk.BooleanVar(value=False),
        "md": tk.BooleanVar(value=False),
        "reproducible": tk.BooleanVar(value=False),
        "ai_mode": tk.StringVar(value="off"),
        "provider": tk.StringVar(),
        "lang": tk.StringVar(value="auto"),
        "theme": tk.StringVar(value="light"),
        "checks": tk.StringVar(value=""),
        "depth": tk.StringVar(value=""),
        "max_nodes": tk.StringVar(value=""),
        # CI 与增量
        "git_diff": tk.BooleanVar(value=False),
        "git_diff_base": tk.StringVar(value=""),
        "gate": tk.BooleanVar(value=False),
        "gate_baseline": tk.StringVar(value=""),
        "max_warnings": tk.StringVar(value=""),
        "sarif_base": tk.StringVar(value=""),
        "binary_attach": tk.StringVar(value=""),
        "lib_resolve": tk.StringVar(value=""),
        "lib_path": tk.StringVar(value=""),
        "lib_max_nodes": tk.StringVar(value=""),
        # R89：调用关系五格
        "callgraph": tk.StringVar(value=""),
        "callgraph_focus": tk.StringVar(value=""),
        "callgraph_depth": tk.StringVar(value=""),
        "callgraph_max_nodes": tk.StringVar(value=""),
        "callgraph_identity": tk.StringVar(value=CALLGRAPH_IDENTITY_DEFAULT),
    }

    def collect():
        return {
            "src": form["src"].get(),
            "out": form["out"].get(),
            "config": form["config"].get(),
            "browse": form["browse"].get(),
            "html": form["html"].get(),
            "json": form["json"].get(),
            "sarif": form["sarif"].get(),
            "md": form["md"].get(),
            "reproducible": form["reproducible"].get(),
            "ai_mode": form["ai_mode"].get(),
            "provider": form["provider"].get(),
            "lang": form["lang"].get(),
            "checks": [c.strip() for c in form["checks"].get().split(",") if c.strip()] or None,
            "depth": int(form["depth"].get()) if form["depth"].get().strip() else None,
            "max_nodes": int(form["max_nodes"].get()) if form["max_nodes"].get().strip() else None,
            "git_diff": form["git_diff"].get(),
            "git_diff_base": form["git_diff_base"].get().strip(),
            "gate": form["gate"].get(),
            "gate_baseline": form["gate_baseline"].get().strip(),
            "max_warnings": int(form["max_warnings"].get()) if form["max_warnings"].get().strip() else None,
            "sarif_base": form["sarif_base"].get().strip(),
            "binary_attach": form["binary_attach"].get().strip(),
            "lib_resolve": int(form["lib_resolve"].get()) if form["lib_resolve"].get().strip() else None,
            "lib_path": form["lib_path"].get().strip(),
            "lib_max_nodes": int(form["lib_max_nodes"].get()) if form["lib_max_nodes"].get().strip() else None,
            "callgraph": form["callgraph"].get().strip(),
            "callgraph_focus": form["callgraph_focus"].get().strip(),
            "callgraph_depth": int(form["callgraph_depth"].get())
            if form["callgraph_depth"].get().strip() else None,
            "callgraph_max_nodes": int(form["callgraph_max_nodes"].get())
            if form["callgraph_max_nodes"].get().strip() else None,
            "callgraph_identity": form["callgraph_identity"].get().strip(),
        }

    def apply_form(values):
        """把部分表单值回填到界面（用于加载配置）。"""
        if "src" in values:
            form["src"].set(values["src"])
        if "out" in values:
            form["out"].set(values["out"])
        # 修复：原实现遗漏 browse/md 两个复选框的回填，加载配置后界面状态与配置不一致
        # （表现为「配置里写了 browse，界面却没勾选」，用户误判不会生成站点）。
        for key in ("browse", "html", "json", "sarif", "md", "reproducible"):
            if key in values:
                form[key].set(bool(values[key]))
        for key in ("lang", "provider", "ai_mode", "depth", "max_nodes",
                    "lib_resolve", "lib_max_nodes"):
            if key in values:
                form[key].set(values[key])
        if "checks" in values:
            form["checks"].set(",".join(values["checks"]))
        for key in ("git_diff", "gate"):
            if key in values:
                form[key].set(bool(values[key]))
        for key in ("git_diff_base", "gate_baseline", "max_warnings", "sarif_base",
                    "lib_path", "binary_attach"):
            if key in values and values[key] is not None:
                form[key].set(str(values[key]))
        # R89：调用关系五格（键名与 CLI 的配置键同名 ⇒ 可直接从 JSON 回填）
        for key in ("callgraph", "callgraph_focus", "callgraph_depth",
                    "callgraph_max_nodes", "callgraph_identity"):
            if key in values and values[key] is not None:
                form[key].set(str(values[key]))

    def pick_src():
        d = filedialog.askdirectory(title="选择 MATLAB 工程根目录")
        if d:
            form["src"].set(d)
            if not form["out"].get():
                form["out"].set(os.path.join(d, "_ma_site"))

    def pick_out():
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            form["out"].set(d)

    def pick_config():
        p = filedialog.askopenfilename(
            title="选择配置 JSON", filetypes=[("JSON 配置", "*.json"), ("全部文件", "*.*")])
        if not p:
            return
        try:
            cfg = load_config_file(p)
        except ValueError as e:
            messagebox.showerror("配置加载失败", str(e))
            return
        form["config"].set(p)
        apply_form(config_to_form(cfg))
        status.set("已加载配置：%s" % os.path.basename(p))

    def clear_config():
        form["config"].set("")
        status.set("已取消配置（仅使用界面参数）")

    def save_config():
        """把当前表单另存为配置 JSON（含 dir/output/browse 等分析器可识别字段）。"""
        p = filedialog.asksaveasfilename(
            title="保存配置 JSON", defaultextension=".json",
            initialfile="analyzer_config.json",
            filetypes=[("JSON 配置", "*.json"), ("全部文件", "*.*")])
        if not p:
            return
        f = collect()
        out = f["out"] or (os.path.join(f["src"], "_ma_site") if f["src"] else None)
        cfg = {"_comment": "由 MATLAB 分析器 GUI 生成；命令行显式参数优先于本文件。"}
        if f["src"]:
            cfg["dir"] = f["src"]
        if out:
            cfg["browse"] = out
            if f["html"]:
                cfg["html"] = out
            if f["json"]:
                cfg["json"] = os.path.join(out, "report.json")
        cfg["reproducible"] = f["reproducible"]
        cfg["lang"] = f["lang"]
        if f["checks"]:
            cfg["checks"] = f["checks"]
        if f["sarif"]:
            cfg["sarif"] = os.path.join(out, "result.sarif") if out else "result.sarif"
        # CI 与增量：只写入用户实际开启的项，保持配置精简
        if f["git_diff"]:
            cfg["git_diff"] = f["git_diff_base"] or True
        if f["gate"]:
            cfg["gate"] = f["gate_baseline"] or True
        if f["max_warnings"] is not None:
            cfg["max_warnings"] = f["max_warnings"]
        if f["sarif_base"]:
            cfg["sarif_base"] = f["sarif_base"]
        # R86-2：二进制诊断 —— 只写用户实际填了的项，保持配置精简
        if f["binary_attach"]:
            cfg["binary_attach"] = f["binary_attach"]
        if f["lib_resolve"] is not None:
            cfg["lib_resolve"] = f["lib_resolve"]
        if f["lib_path"]:
            cfg["lib_path"] = f["lib_path"]
        if f["lib_max_nodes"] is not None:
            cfg["lib_max_nodes"] = f["lib_max_nodes"]
        # R89：调用关系 —— 只写用户实际填了的项，保持配置精简；身份口径的
        # 默认档不写（写了也是同一个默认，只会让配置多一行噪声）。
        if f["callgraph"]:
            cfg["callgraph"] = f["callgraph"]
        if f["callgraph_focus"]:
            cfg["callgraph_focus"] = f["callgraph_focus"]
        if f["callgraph_depth"] is not None:
            cfg["callgraph_depth"] = f["callgraph_depth"]
        if f["callgraph_max_nodes"] is not None:
            cfg["callgraph_max_nodes"] = f["callgraph_max_nodes"]
        if (f["callgraph_identity"]
                and f["callgraph_identity"] != CALLGRAPH_IDENTITY_DEFAULT):
            cfg["callgraph_identity"] = f["callgraph_identity"]
        if f["ai_mode"] in ("ask", "auto") and f["provider"]:
            cfg["ai"] = {"default_provider": f["provider"]}
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, ensure_ascii=False, indent=2)
        except OSError as e:
            messagebox.showerror("保存失败", "无法写入配置：%s" % e)
            return
        form["config"].set(p)
        status.set("已保存配置：%s" % os.path.basename(p))

    _gate = RunGate()

    def run():
        # 重入闸门：与控制件状态解耦，杜绝连点并发启动多个分析器（详见 RunGate 注释）。
        if not _gate.acquire():
            status.set("已有分析在进行中，请等待结束…")
            return
        run._proc = None
        run._aborted = False
        try:
            cli_args = build_cli_args(collect())
        except Exception as e:
            _gate.release()
            import traceback as _tb
            messagebox.showerror("输入有误", "%s\n\n%s" % (e, "".join(_tb.format_exception_only(type(e), e))))
            return
        _setrun = getattr(run, "_set_running", None)
        if _setrun:
            _setrun(True)
        log.configure(state="normal")
        log.delete("1.0", tk.END)
        log.configure(state="disabled")
        status.set("分析中…")
        # 进度条初始化 + 阶段标记映射（分析器无逐阶段进度，用已知结尾标记跳进）
        try:
            prog.configure(value=0, mode="determinate")
            prog_pct.set("0%")
        except Exception:
            pass

        def _set_prog(v):
            v = max(0, min(100, int(v)))
            try:
                prog.configure(value=v)
                prog_pct.set("%d%%" % v)
            except Exception:
                pass

        _PHASES = [
            ("[INFO] 基线", 15),
            ("指纹文件已写入", 25),
            ("===== 摘要", 82),
            ("交互式源码浏览站点已生成", 88),
            ("HTML 报告生成", 92),
            ("SARIF", 95),
            ("Markdown", 95),
            ("测试骨架已生成", 90),
            ("Doxygen 兼容 XML 已导出", 90),
        ]

        def _bump(text):
            try:
                cur = int(prog.cget("value"))
            except Exception:
                cur = 0
            target = cur
            for key, pct in _PHASES:
                if key in text:
                    target = max(target, pct)
            if target > cur:
                _set_prog(target)
        try:
            frozen = getattr(sys, "frozen", False)
            target = analyzer_target()
            workdir = form["src"].get() or None
            if not workdir and form["config"].get():
                workdir = os.path.dirname(form["config"].get())
            cmd = ([target] if frozen else [sys.executable, target]) + cli_args
            # 把实际执行命令回显到日志首行：一旦参数没按预期传递（例如 --browse 丢失
            # 导致站点不生成），用户与开发者都能从日志立刻看出，无需再靠猜。
            _argv_preview = " ".join(
                ('"%s"' % a) if (" " in a) else a for a in cmd)
            try:
                log.configure(state="normal")
                log.insert(tk.END, "$ " + _argv_preview + "\n")
                log.configure(state="disabled")
            except Exception:
                pass
            _spawn = {}
            if sys.platform == "win32":
                # 冻结态下被调用的 matlabc 是控制台程序；抑制其弹出的独立控制台窗口，
                # 输出改由本 GUI 的日志框承接。
                _spawn["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            # 中文 Windows 默认文本编码是 GBK；分析器输出 UTF-8（含中文日志），
            # 必须两端统一为 UTF-8，否则 readline 会抛 UnicodeDecodeError 导致界面崩溃。
            _env = dict(os.environ)
            _env["PYTHONUTF8"] = "1"
            _env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                # R62-R31e：切 stdin。分析器由 GUI 启动，不该看到 GUI 的输入句柄；
                # 这里**故意不给 timeout** —— 它是长跑流式进程，由用户点「停止」终止，
                # 加超时会把「大工程分析得久」误判成失败。（护栏对此有显式登记）
                stdin=subprocess.DEVNULL,
                universal_newlines=True, encoding="utf-8", errors="replace",
                bufsize=1, cwd=workdir, env=_env, **_spawn)
            run._proc = proc
        except Exception as e:
            import traceback as _tb
            _gate.release()               # 释放重入闸门
            status.set("启动失败")
            if _setrun:
                _setrun(False)
            messagebox.showerror("启动失败", "无法运行分析器：%s" % e)
            try:
                log.configure(state="normal")
                log.insert(tk.END, "".join(_tb.format_exception_only(type(e), e)))
                log.configure(state="disabled")
            except Exception:
                pass
            return

        # 性能修复：原实现每读到一行就 configure/insert/see，且 readline 在 Tk 主线程
        # 上执行——分析器输出上千行时会把主线程占满，界面明显卡顿甚至假死。
        # 改为：后台线程负责读管道（不阻塞 UI），主线程按固定节拍批量刷新。
        import threading as _th
        _lock = _th.Lock()
        _buf = []
        _state = {"done": False, "rc": None, "last": 0.0}
        MAX_LINES = 4000          # 日志框最多保留的行数（超出丢弃最旧，避免无限增长拖慢渲染）
        FLUSH_MS = 100            # 刷新节拍：最多每秒 10 次，每次一次性插入整批

        def _reader():
            try:
                for ln in iter(proc.stdout.readline, ""):
                    with _lock:
                        _buf.append(ln)
            except Exception as e:
                with _lock:
                    _buf.append("[GUI] 读取输出失败：%r\n" % (e,))
            finally:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
                with _lock:
                    _state["done"] = True
                    _state["rc"] = proc.wait()

        def _flush():
            with _lock:
                batch = "".join(_buf)
                _buf.clear()
                done = _state["done"]
                rc = _state["rc"]
            if batch:
                log.configure(state="normal")
                log.insert(tk.END, batch)
                # 行数超限时裁剪头部，保持控件轻量（截断点对齐到行，避免残留半行）
                try:
                    total = int(log.index("end-1c").split(".")[0])
                    if total > MAX_LINES:
                        log.delete("1.0", "%d.0" % (total - MAX_LINES + 1))
                except Exception:
                    pass
                log.configure(state="disabled")
                log.see(tk.END)
                _bump(batch)
            if done:
                _set_prog(100)
                _gate.release()           # 分析结束释放重入闸门，允许再次点击
                _setrun = getattr(run, "_set_running", None)
                if _setrun:
                    _setrun(False)
                if getattr(run, "_aborted", False):
                    status.set("已中止 ✕")
                    messagebox.showinfo("已中止", "分析已被用户中止。已生成的部分结果可能不完整。")
                elif rc == 0:
                    status.set("完成 ✓")
                    messagebox.showinfo("完成", "分析结束。可在输出目录打开结果。")
                else:
                    status.set("结束（退出码 %s）" % rc)
                    messagebox.showwarning("结束", "分析器以退出码 %s 结束，请查看日志。" % rc)
                return
            else:
                # 爬行增长：未结束且未命中阶段标记时缓慢推进，给用户实时反馈（封顶 90%）
                try:
                    if int(prog.cget("value")) < 90:
                        _set_prog(min(90, int(prog.cget("value")) + 2))
                except Exception:
                    pass
            root.after(FLUSH_MS, _flush)

        _th.Thread(target=_reader, daemon=True).start()
        root.after(FLUSH_MS, _flush)

    def stop():
        """用户主动中止：终止正在运行的分析子进程。

        直接 terminate 子进程（Windows 下 TerminateProcess 立即生效）；置
        _aborted 标记，由 _flush 在子进程退出后统一收尾（释放闸门、恢复按钮、
        提示「已中止」），避免在此直接操作 UI 造成竞态。
        """
        p = getattr(run, "_proc", None)
        if p is not None and p.poll() is None:
            run._aborted = True
            status.set("正在中止…")
            try:
                p.terminate()
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        else:
            status.set("当前没有正在运行的分析")

    def open_result():
        out = form["out"].get().strip()
        if not out and form["src"].get():
            out = os.path.join(form["src"].get(), "_ma_site")
        if not out:
            messagebox.showwarning("未找到结果", "尚未设置输出目录，请先运行一次分析。")
            return
        index = os.path.join(out, "index.html")
        # 站点存在则优先用浏览器打开入口页（比打开目录更符合「打开站点」的预期）
        if os.path.exists(index):
            if not open_in_browser(index):
                messagebox.showwarning("打开失败", "无法打开站点：%s" % index)
            return
        # 没有站点时退回打开输出目录（若目录也不存在则明确提示）
        if os.path.isdir(out):
            open_output(out)
        else:
            messagebox.showwarning(
                "未找到结果",
                "未找到站点入口：%s\n\n请确认已勾选「交互式浏览站点」并成功完成一次分析。" % index)

    def on_theme(*_):
        _apply_theme(root, style, natives, _default_theme, form["theme"].get())

    # ---- 布局：顶部标题栏 + 卡片式主体 + 底部操作/日志 ----
    natives = {"log": None, "title": None, "band": None}

    banner = tk.Frame(root)
    banner.pack(fill="x")
    natives["band"] = banner
    title = tk.Label(banner, text=APP_TITLE, font=("Segoe UI", 15, "bold"))
    title.pack(side="left", padx=14, pady=10)
    natives["title"] = title
    tk.Label(banner, text="MATLAB 工程静态分析 · 一键生成浏览站点",
             font=("Segoe UI", 9)).pack(side="left", pady=12)
    ttk.OptionMenu(banner, form["theme"], "light", "light", "dark",
                   command=on_theme).pack(side="right", padx=14)
    ttk.Label(banner, text="主题").pack(side="right")

    body = ttk.Frame(root)
    body.pack(fill="both", expand=True, padx=12, pady=(4, 0))
    body.columnconfigure(0, weight=1)

    # 工程卡片
    proj = ttk.LabelFrame(body, text="工程")
    proj.grid(row=0, column=0, sticky="we", pady=5)
    proj.columnconfigure(1, weight=1)
    ttk.Label(proj, text="工程目录").grid(row=0, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(proj, textvariable=form["src"]).grid(row=0, column=1, sticky="we", pady=6)
    ttk.Button(proj, text="浏览…", command=pick_src).grid(row=0, column=2, padx=6)
    ttk.Label(proj, text="输出目录").grid(row=1, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(proj, textvariable=form["out"]).grid(row=1, column=1, sticky="we", pady=6)
    ttk.Button(proj, text="浏览…", command=pick_out).grid(row=1, column=2, padx=6)
    ttk.Label(proj, text="留空=在工程目录下自动生成 _ma_site（也可从配置 JSON 读取）",
              style="CardMuted.TLabel").grid(row=2, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 6))

    # 配置卡片（新增：加载/保存 JSON）
    cfgbox = ttk.LabelFrame(body, text="配置 JSON（可选 · 命令行参数优先）")
    cfgbox.grid(row=1, column=0, sticky="we", pady=5)
    cfgbox.columnconfigure(1, weight=1)
    ttk.Entry(cfgbox, textvariable=form["config"]).grid(row=0, column=1, sticky="we", padx=8, pady=6)
    ttk.Button(cfgbox, text="加载…", command=pick_config).grid(row=0, column=2, padx=3)
    ttk.Button(cfgbox, text="保存当前为…", command=save_config).grid(row=0, column=3, padx=3)
    ttk.Button(cfgbox, text="清除", command=clear_config).grid(row=0, column=4, padx=(3, 8))
    ttk.Label(cfgbox, text="可加载预先配置好的 JSON（示例：analyzer_config.example.json）",
              style="CardMuted.TLabel").grid(row=1, column=1, columnspan=4, sticky="w", padx=8, pady=(0, 6))

    # 输出选项卡片
    outbox = ttk.LabelFrame(body, text="输出内容")
    outbox.grid(row=2, column=0, sticky="we", pady=5)
    for i, (key, txt) in enumerate([
            ("browse", "交互式浏览站点（推荐）"), ("html", "HTML 报告"),
            ("json", "JSON 数据"), ("sarif", "SARIF（CI 集成）"),
            ("md", "Markdown 报告"), ("reproducible", "可复现（去时间戳）")]):
        ttk.Checkbutton(outbox, text=txt, variable=form[key]).grid(
            row=i // 3, column=i % 3, sticky="w", padx=8, pady=4)
    ttk.Label(outbox, text="推荐勾选「交互式浏览站点」；其余按需要选择，选得越少速度越快",
              style="CardMuted.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(2, 4))

    # AI 卡片
    aibox = ttk.LabelFrame(body, text="AI 引入时机（P225-F）")
    aibox.grid(row=3, column=0, sticky="we", pady=5)
    ttk.Label(aibox, text="时机").grid(row=0, column=0, sticky="w", padx=8, pady=6)
    ttk.OptionMenu(aibox, form["ai_mode"], "off",
                   "off", "prompts", "ask", "auto").grid(row=0, column=1, sticky="w")
    ttk.Label(aibox, text="在线 Provider").grid(row=0, column=2, sticky="w", padx=8)
    ttk.Entry(aibox, textvariable=form["provider"], width=18).grid(row=0, column=3, sticky="w")
    ttk.Label(aibox, text="时机：off=原样输出 / prompts=输出可粘贴提示词 / ask=结束询问 / auto=自动（需在线密钥）",
              style="CardMuted.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 2))
    ttk.Label(aibox, text="在线 Provider：离线分析无需填写；ask/auto 时填 online 提供商（如 openai），密钥从环境变量读取",
              style="CardMuted.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 6))

    # 高级卡片
    adv = ttk.LabelFrame(body, text="高级（可选）")
    adv.grid(row=4, column=0, sticky="we", pady=5)
    adv.columnconfigure(3, weight=1)
    ttk.Label(adv, text="递归深度").grid(row=0, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(adv, textvariable=form["depth"], width=8).grid(row=0, column=1, sticky="w")
    ttk.Label(adv, text="调用图最大节点").grid(row=0, column=2, sticky="w", padx=8)
    ttk.Entry(adv, textvariable=form["max_nodes"], width=8).grid(row=0, column=3, sticky="w")
    ttk.Label(adv, text="语言").grid(row=1, column=0, sticky="w", padx=8, pady=6)
    ttk.OptionMenu(adv, form["lang"], "auto", "auto", "matlab", "c", "py", "js").grid(row=1, column=1, sticky="w")
    ttk.Label(adv, text="检查项（逗号分隔，留空=全部）").grid(row=1, column=2, sticky="w", padx=8)
    ttk.Entry(adv, textvariable=form["checks"]).grid(row=1, column=3, sticky="we", padx=(0, 8))
    ttk.Label(adv, text="深度/节点留空=不限制；语言 auto=按扩展名识别；检查项如 uninit,taint（留空=全部）",
              style="CardMuted.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 6))

    # CI 与增量卡片（P0 增强：把 CLI 的 CI 能力搬到界面，勾选即用）
    cibox = ttk.LabelFrame(body, text="CI 与增量（可选 · 面向流水线）")
    cibox.grid(row=6, column=0, sticky="we", pady=5)
    cibox.columnconfigure(1, weight=1)
    cibox.columnconfigure(3, weight=1)
    ttk.Checkbutton(cibox, text="仅分析 git 变更文件（PR 增量）",
                    variable=form["git_diff"]).grid(row=0, column=0, sticky="w", padx=8, pady=4)
    ttk.Label(cibox, text="对比基准").grid(row=0, column=1, sticky="w", padx=8)
    ttk.Entry(cibox, textvariable=form["git_diff_base"], width=14).grid(row=0, column=2, sticky="w")
    ttk.Label(cibox, text="默认 HEAD（留空即比较工作树与 HEAD）",
              style="CardMuted.TLabel").grid(row=0, column=3, sticky="w", padx=8)
    ttk.Checkbutton(cibox, text="质量门禁（告警/债务超阈值退出码非 0）",
                    variable=form["gate"]).grid(row=1, column=0, sticky="w", padx=8, pady=4)
    ttk.Label(cibox, text="门禁基线").grid(row=1, column=1, sticky="w", padx=8)
    ttk.Entry(cibox, textvariable=form["gate_baseline"], width=14).grid(row=1, column=2, sticky="w")
    ttk.Label(cibox, text="默认 .debt_trend.json（不存在则以本次为首基线并放行）",
              style="CardMuted.TLabel").grid(row=1, column=3, sticky="w", padx=8)
    ttk.Label(cibox, text="最大告警数").grid(row=2, column=0, sticky="w", padx=8, pady=4)
    ttk.Entry(cibox, textvariable=form["max_warnings"], width=8).grid(row=2, column=1, sticky="w")
    ttk.Label(cibox, text="基线 SARIF（增量，仅保留新增告警）").grid(row=2, column=2, sticky="w", padx=8)
    ttk.Entry(cibox, textvariable=form["sarif_base"], width=16).grid(row=2, column=3, sticky="we", padx=(0, 8))
    ttk.Label(cibox, text="说明：勾选「质量门禁」后，若告警/债务超过阈值，程序退出码为 1，便于 CI 判定失败；"
                          "「仅分析 git 变更」需在 git 仓库内运行。",
              style="CardMuted.TLabel", wraplength=760, justify="left").grid(
        row=3, column=0, columnspan=4, sticky="w", padx=8, pady=(2, 6))

    # 二进制诊断卡片（R86-2：把 REA 的「码里涉及的库都要被处理」搬进界面）
    binbox = ttk.LabelFrame(body, text="二进制诊断 / 库引用解析（R86-2）")
    binbox.grid(row=5, column=0, sticky="we", pady=5)
    binbox.columnconfigure(3, weight=1)
    ttk.Label(binbox, text="额外指定库（库名或路径，逗号分隔）").grid(row=0, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(binbox, textvariable=form["binary_attach"]).grid(row=0, column=1, columnspan=3, sticky="we", padx=(0, 8))
    ttk.Label(binbox, text="库引用解析深度").grid(row=1, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(binbox, textvariable=form["lib_resolve"], width=8).grid(row=1, column=1, sticky="w")
    ttk.Label(binbox, text="一次最多解析文件数").grid(row=1, column=2, sticky="w", padx=8)
    ttk.Entry(binbox, textvariable=form["lib_max_nodes"], width=8).grid(row=1, column=3, sticky="w")
    ttk.Label(binbox, text="追加库搜索目录（逗号分隔）").grid(row=2, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(binbox, textvariable=form["lib_path"]).grid(row=2, column=1, columnspan=3, sticky="we", padx=(0, 8))
    ttk.Label(binbox, text="留空=不做库解析。深度 0=关。「追加目录」是**追加**，平台默认目录仍会搜。三态：唯一命中 / 同名多份（不猜，按位数排除 32/64 位孪生）/ 未找到（并列列出搜过的目录）；「上限内没轮到」的节点记 skipped，与 not_found 严格区分。",
              style="CardMuted.TLabel", wraplength=760, justify="left").grid(
        row=3, column=0, columnspan=4, sticky="w", padx=8, pady=(2, 6))
    # 调用关系卡片（R89：CLI 有 --callgraph 系列、GUI 一格都没有 = 新的不对等）
    cgbox = ttk.LabelFrame(body, text="调用关系（有界投影 · 可选）")
    cgbox.grid(row=7, column=0, sticky="we", pady=5)
    cgbox.columnconfigure(3, weight=1)
    ttk.Label(cgbox, text="导出文件（留空=不导出）").grid(
        row=0, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(cgbox, textvariable=form["callgraph"]).grid(
        row=0, column=1, columnspan=3, sticky="we", padx=(0, 8))
    ttk.Label(cgbox, text="焦点函数（留空=枢纽）").grid(
        row=1, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(cgbox, textvariable=form["callgraph_focus"], width=18).grid(
        row=1, column=1, sticky="w")
    ttk.Label(cgbox, text="展开深度").grid(row=1, column=2, sticky="w", padx=8)
    ttk.Entry(cgbox, textvariable=form["callgraph_depth"], width=8).grid(
        row=1, column=3, sticky="w")
    ttk.Label(cgbox, text="节点上限").grid(row=2, column=0, sticky="w", padx=8, pady=6)
    ttk.Entry(cgbox, textvariable=form["callgraph_max_nodes"], width=8).grid(
        row=2, column=1, sticky="w")
    ttk.Label(cgbox, text="节点身份口径").grid(row=2, column=2, sticky="w", padx=8)
    ttk.OptionMenu(cgbox, form["callgraph_identity"], CALLGRAPH_IDENTITY_DEFAULT,
                   *CALLGRAPH_IDENTITIES).grid(row=2, column=3, sticky="w")
    ttk.Label(cgbox, text="留空=不导出。导出的是**有界**投影（度数排行 / 递归环 / 跨文件计数 / 焦点邻域），规模无关、输出恒为 KB 级。身份口径三档：definition-site-local（默认，同文件 → 同翻译单元，只对 C 启用）/ definition-site / callee-name（同名合并，环可能含假阳性）；换口径**一条边都不删**，逐档「判得出的 / 判不出的」计数在产物的 resolution 块里。",
              style="CardMuted.TLabel", wraplength=760, justify="left").grid(
        row=3, column=0, columnspan=4, sticky="w", padx=8, pady=(2, 6))
    # 底部：操作按钮 + 状态 + 日志
    actions = ttk.Frame(root)
    actions.pack(fill="x", padx=12, pady=(8, 2))
    _run_btn = ttk.Button(actions, text="开始分析", style="Accent.TButton", command=run)
    _run_btn.pack(side="left")
    _open_btn = ttk.Button(actions, text="打开结果", command=open_result)
    _open_btn.pack(side="left", padx=8)
    _stop_btn = ttk.Button(actions, text="中止", command=stop, state="disabled")
    _stop_btn.pack(side="left", padx=8)
    status = tk.StringVar(value="就绪")
    ttk.Label(actions, textvariable=status).pack(side="right")

    # 进度条：分析器运行期间没有逐阶段进度标记，故采用「爬行增长 + 阶段跳进 + 完成置满」
    # 的组合，既给用户实时反馈（消除「假死感」），又不会虚假宣称完成。
    prog_frame = ttk.Frame(root)
    prog_frame.pack(fill="x", padx=12, pady=(0, 2))
    prog = ttk.Progressbar(prog_frame, mode="determinate", maximum=100, value=0)
    prog.pack(side="left", fill="x", expand=True)
    prog_pct = tk.StringVar(value="")
    ttk.Label(prog_frame, textvariable=prog_pct, width=8, anchor="e").pack(side="right", padx=(6, 0))

    # 运行期间禁用按钮，避免重复点击并发启动多个分析器（卡顿/资源竞争的常见来源）
    def _set_running(on):
        try:
            _run_btn.configure(state=("disabled" if on else "normal"))
        except Exception:
            pass
        try:
            _stop_btn.configure(state=("disabled" if not on else "normal"))
        except Exception:
            pass
    run._set_running = _set_running

    log = tk.Text(root, height=12, state="disabled", relief="flat", borderwidth=0,
                  font=("Consolas", 9) if sys.platform == "win32" else ("Menlo", 9))
    log.pack(fill="both", expand=True, padx=12, pady=(4, 12))
    natives["log"] = log

    _apply_theme(root, style, natives, _default_theme, form["theme"].get())
    root.mainloop()


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    # --help 必须在**任何副作用之前**返回：早先它会一路走到「启动 GUI」，
    # 对命令行用户来说「问帮助却弹窗」是纯粹的意外（且 CI 里会挂住）。
    if "--help" in argv or "-h" in argv:
        _write_help(HELP_TEXT)
        return 0
    if "--selftest" in argv:
        # 无界面自检：构造一份表单并校验 CLI 映射
        sample = {
            "src": "C:/proj", "out": "C:/proj/_ma_site",
            "browse": True, "html": True, "json": True, "sarif": True, "md": False,
            "reproducible": True, "checks": ["uninit", "taint"], "depth": 3,
            "max_nodes": 5000, "ai_mode": "prompts", "provider": "", "lang": "c",
        }
        args = build_cli_args(sample)
        assert args[0] == "C:/proj"
        assert "--browse" in args and "C:/proj/_ma_site" in args

        def _val(flag, where=None):
            """取 where（默认 args）中 flag 后紧跟的取值；裸开关/未出现则返回 None。"""
            seq = args if where is None else where
            if flag not in seq:
                return None
            i = seq.index(flag)
            return seq[i + 1] if i + 1 < len(seq) and not seq[i + 1].startswith("--") else None

        # 回归断言：需要「文件路径」的选项必须带值，否则 exe 会报
        # "argument --sarif: expected one argument"（P0 缺陷的守护）。
        for flag in ("--sarif", "--html", "--json", "--browse"):
            assert flag in args, "缺少 %s" % flag
            assert _val(flag), "%s 必须带参数值（缺值会导致 argparse 报错）" % flag
        assert _val("--sarif").endswith(".sarif"), _val("--sarif")
        assert _val("--html").endswith(".html"), _val("--html")
        assert _val("--json").endswith(".json"), _val("--json")
        # 纯开关（无值）选项
        if "--reproducible" in args:
            assert _val("--reproducible") is None, "--reproducible 不应带值"
        assert "--checks" in args and "uninit,taint" in args
        assert "--ai-mode" in args and "prompts" in args
        assert "--lang" in args and "c" in args
        # CI 与增量：门禁/增量裸传（可选值参数）与带值两种形态都要正确。
        ci_sample = dict(sample)
        ci_sample.update({"git_diff": True, "git_diff_base": "",
                          "gate": True, "gate_baseline": "",
                          "max_warnings": 5, "sarif_base": "base.sarif"})
        ci_args = build_cli_args(ci_sample)
        assert "--git-diff" in ci_args and _val("--git-diff", ci_args) is None
        assert "--gate" in ci_args and _val("--gate", ci_args) is None
        assert _val("--max-warnings", ci_args) == "5", ci_args
        assert _val("--sarif-base", ci_args) == "base.sarif", ci_args
        ci2 = dict(sample)
        ci2.update({"git_diff": True, "git_diff_base": "main", "gate": True,
                    "gate_baseline": "b.json"})
        ci2_args = build_cli_args(ci2)
        assert _val("--git-diff", ci2_args) == "main", ci2_args
        assert _val("--gate", ci2_args) == "b.json", ci2_args
        assert "--git-diff" not in args and "--gate" not in args
        # Markdown 复选框：应生成 -o 且指向 .md 文件（并不存在 --markdown 开关）。
        md_sample = dict(sample)
        md_sample["md"] = True
        md_args = build_cli_args(md_sample)
        assert "-o" in md_args, md_args
        assert md_args[md_args.index("-o") + 1].endswith(".md"), md_args
        assert "--markdown" not in md_args
        # 仅配置文件（无 src）时也应可用
        c_args = build_cli_args({"config": "cfg.json", "browse": False})
        assert c_args == ["--config", "cfg.json", "--ai-mode", "off"], c_args
        # 既无 src 又无 config 时必须报错
        try:
            build_cli_args({"src": "", "config": ""})
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
        # 配置 → 表单回填
        f = config_to_form({"dir": "D:/p", "browse": "site", "html": "site/x.html",
                            "lang": "matlab", "checks": "uninit,taint"})
        assert f["src"] == "D:/p" and f["out"] == "site" and f["html"] is True
        assert f["lang"] == "matlab" and f["checks"] == ["uninit", "taint"], f
        # 本地文件 → file:// URL 必须使用正斜杠（Windows 反斜杠会让浏览器打不开）
        uri = pathlib_path_uri("C:/tmp/a b/index.html")
        assert uri.startswith("file:///"), uri
        assert "\\" not in uri, uri
        assert " " not in uri, uri  # 空格应被转义为 %20
        # 打开不存在的文件必须安全返回 False，不得抛异常
        assert open_in_browser("C:/definitely/not/exist_zzz.html") is False
        assert open_output("") is False
        # R86-2：二进制诊断四格 -> --binary-attach / --lib-resolve / --lib-path /
        # --lib-max-nodes。三件事都要钉：填了必须原样进命令行；没填必须**一个都不出现**
        # （否则默认行为被界面悄悄改掉）；深度 0 要**显式写 0**（语义是「关」，
        # 不是「缺省」—— 两者在报告里分得开）。
        bin_sample = dict(sample)
        bin_sample.update({"binary_attach": "libfoo.so,kernel32.dll",
                           "lib_resolve": 2, "lib_path": "D:/libs,D:/more",
                           "lib_max_nodes": 128})
        bin_args = build_cli_args(bin_sample)
        assert _val("--binary-attach", bin_args) == "libfoo.so,kernel32.dll", bin_args
        assert _val("--lib-resolve", bin_args) == "2", bin_args
        assert _val("--lib-path", bin_args) == "D:/libs,D:/more", bin_args
        assert _val("--lib-max-nodes", bin_args) == "128", bin_args
        for _f in ("--binary-attach", "--lib-resolve", "--lib-path",
                   "--lib-max-nodes"):
            assert _f not in args, (_f, args)
        zb = build_cli_args({"src": "C:/p", "lib_resolve": 0})
        assert _val("--lib-resolve", zb) == "0", zb
        # 反斜杠统一成正斜杠：Windows 下 "C:/a\b" 这种混合分隔符易被误解析
        wb = build_cli_args({"src": "C:/p", "lib_path": "D:\\libs"})
        assert _val("--lib-path", wb) == "D:/libs", wb
        # 往返那一半：配置 JSON -> 表单。只测「表单 -> 命令行」会漏掉
        # 「加载了配置但界面空白」这类沉默故障（与分析器行为不符，却不报错）。
        g = config_to_form({"dir": "C:/p", "binary_attach": "libfoo.so",
                            "lib_resolve": 2, "lib_path": "D:/libs",
                            "lib_max_nodes": 128})
        assert g["binary_attach"] == "libfoo.so", g
        assert g["lib_resolve"] == "2", g
        assert g["lib_path"] == "D:/libs", g
        assert g["lib_max_nodes"] == "128", g
        g0 = config_to_form({"dir": "C:/p", "lib_resolve": 0})
        assert g0["lib_resolve"] == "0", g0
        assert "lib_max_nodes" not in config_to_form({"dir": "C:/p"}), "未填不该造出键"
        # R89：调用关系五格 -> --callgraph / --callgraph-focus / --callgraph-depth /
        # --callgraph-max-nodes / --callgraph-identity。与二进制那一组同一纪律：
        # ① 没填输出文件时**一个参数都不出现**（默认行为不许被界面偷偷改掉）；
        # ② 填了必须原样进命令行；③ 身份口径的**默认档刻意不下发**（这样
        # 「界面没动过」的命令行与 R88 逐字相同），非默认档必须显式下发。
        for _f in ("--callgraph", "--callgraph-focus", "--callgraph-depth",
                   "--callgraph-max-nodes", "--callgraph-identity"):
            assert _f not in args, (_f, args)
        # 只填焦点/深度而没填输出文件 ⇒ 仍然一个都不下发（三者脱离图没有意义）
        q1 = build_cli_args({"src": "C:/p", "callgraph_focus": "foo",
                             "callgraph_depth": 3})
        assert "--callgraph" not in q1 and "--callgraph-focus" not in q1, q1
        cg_sample = dict(sample)
        cg_sample.update({"callgraph": "D:\\cg\\g.json",
                          "callgraph_focus": "hub", "callgraph_depth": 3,
                          "callgraph_max_nodes": 300,
                          "callgraph_identity": "callee-name"})
        cg_args = build_cli_args(cg_sample)
        assert _val("--callgraph", cg_args) == "D:/cg/g.json", cg_args
        assert _val("--callgraph-focus", cg_args) == "hub", cg_args
        assert _val("--callgraph-depth", cg_args) == "3", cg_args
        assert _val("--callgraph-max-nodes", cg_args) == "300", cg_args
        assert _val("--callgraph-identity", cg_args) == "callee-name", cg_args
        # 默认档不下发；显式给了默认档也不下发（两者等价，命令行更短）
        for _ident in ("", CALLGRAPH_IDENTITY_DEFAULT):
            q2 = build_cli_args({"src": "C:/p", "callgraph": "g.json",
                                 "callgraph_identity": _ident})
            assert "--callgraph-identity" not in q2, (_ident, q2)
            assert _val("--callgraph", q2) == "g.json", q2
        # 三档必须在册（少一档 ⇒ 要么有档选不出来，要么打错字静默变成默认）
        assert CALLGRAPH_IDENTITIES == ("definition-site-local",
                                        "definition-site",
                                        "callee-name"), CALLGRAPH_IDENTITIES
        # 配置往返那一半：只测「表单 -> 命令行」会漏掉「加载了配置但界面空白」
        gc = config_to_form({"dir": "C:/p", "callgraph": "D:/cg/g.json",
                             "callgraph_focus": "hub", "callgraph_depth": 3,
                             "callgraph_max_nodes": 300,
                             "callgraph_identity": "definition-site"})
        assert gc["callgraph"] == "D:/cg/g.json", gc
        assert gc["callgraph_focus"] == "hub", gc
        assert gc["callgraph_depth"] == "3", gc
        assert gc["callgraph_max_nodes"] == "300", gc
        assert gc["callgraph_identity"] == "definition-site", gc
        assert "callgraph" not in config_to_form({"dir": "C:/p"}), \
            "未填不该造出键"
        print("GUI selftest OK:", " ".join(args))
        return 0
    # 单例守卫：防止重复双击启动多个 GUI 主进程（与 RunGate 同类「多实例」病根）。
    if not ensure_single_instance():
        try:
            _r = tk.Tk()
            _r.withdraw()
            tk.messagebox.showwarning("已在运行", "MATLAB 分析器已在运行中，请勿重复打开。")
        except Exception:
            pass
        return 0
    _launch_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
