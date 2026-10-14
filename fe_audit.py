# -*- coding: utf-8 -*-
"""前端产物自动审计（fe_audit）—— 为「自动化迭代修复」提供可判定成败的 Verify 命令。

设计目标：把「查看源码有问题 / 前端交互有问题」这类**主观描述**转化为**可机器判定**的
检查项，从而能驱动 loop 技能做「执行 → 验证 → 失败则重试」的自动迭代。

检查项：
  S1 JS 语法      —— 抽取每个页面内联 <script>，用 `node --check` 判定语法是否合法
  S2 内部链接     —— 相对 href 指向的本地文件是否存在（死链会让导航/跳转失效）
  S3 外部 CDN     —— 是否硬编码外部 CDN（内网环境必然加载失败，属阻塞级隐患）
  S4 锚点完整性   —— 本页 href="#xxx" 与跨页 b.html#frag 的锚点是否真实存在
                     （死锚/死链都会让跳转变"没反应"；跨页部分见 P-rev R72）
  S5 JS 运行时    —— 在 DOM stub 中执行内联脚本，捕获运行期异常
  S6 JS href      —— onclick="location=..." 之类动态跳转的目标文件是否真实存在
  S7 孤立页面     —— 未被任何页面链接到的产物（孤儿页是陈旧内容/手工残留的信号）
  S8 锚点与 id 协同 —— 页内 #frag 是否与静态 id/name 可解析（同 S4 语义的内页版）
  S9 a11y 基线    —— skip-link/表单 label/可访问性基本盘
  S10 硬编码导航  —— 页面间导航是否仍手写死链而非统一模板
  S11 真实 DOM    —— 依赖 jsdom 时执行全套交互接线校验（缺 jsdom 自动降级 WARN）
  S12 性能预算    —— 每页首屏 JS 字节数 / 脚本请求数是否超过预算（防交互变重）
                     默认 WARN；带 --enforce-budget 时超预算升级为 ERROR（CI 硬门禁）
  S13 重复 id     —— 页面内 id 重复（JS getElementById / #L 深链只认第一个，
                     重复即部分元素"存在但永远不可达"；见 P-rev R76）
  S14 HTML 结构   —— 标签配对/嵌套级结构校验（R77）：容器少闭合、<main> 嵌套、
                     地标重叠等浏览器会静默自我修复的结构性错位
  S15 产物-清单一致性 —— 站点含 manifest.json 时校验每页 sha256（R79）：
                     手工改动、半次生成、陈旧残留都会被抓出
  S16 质量快照一致性 —— 产物含 site-quality.json 时复核其规模事实
                     （页面数/资产数/总字节）与实况是否一致（R85/R86）：
                     清单与快照被**成对**改写、或快照陈旧自相矛盾时逐字段报错
  S17 一级标题    —— 每页须有且仅有一个非空 <h1>（标题层级；5 轮收尾改进 R1）
  S18 图片尺寸    —— <img> 须声明 width/height，避免布局抖动（CLS）；缺即 WARN
  S19 重复标题    —— 同站多页不得使用完全相同的 <title>（SEO 去重）；相同即 WARN
  S20 内联事件    —— HTML 属性式 onclick=/onload=…（CSP 不友好 / 难审计）：
                     现代前端应改用 addEventListener / 事件委托。先 WARN 记账
  S21 脚本延迟    —— <script src=…> 未带 defer/async 会阻塞解析、拖慢首屏；
                     应默认 defer（或 async）。先 WARN 记账
  S22 内联样式    —— 页面不得再发射内联 <style>（FE-6/FE-21 已外链到 page_css/）：
                     内联样式既无法被浏览器缓存、也难审计，现应趋于 0
  S23 图片替代文本 —— <img> 缺 alt 会让屏幕阅读器跳过或读出文件名；装饰图
                     应有 alt="" 或 aria-hidden。先 WARN 记账

审计器自身契约（P-rev R92/R93/R96/R97）：
  INT —— 内部错误专用伪检查（畸形 issue 归拢、审计过程写入未声明文件），不占 S 序号
  _fe_* 运行时产物豁免 —— 审计器落在被审计树内的自身文件（_fe_dom_check.json /
  _fe_perf_trend.csv / _fe_perf_report.html）不参与 S15/S16 对账与页面计数：
  生成器与审计器对 _fe_* 双向豁免，共享目录时互不污染（R92）；collect_html
  直接剔除 _fe_* 页面，跨轮页面计数不漂移（R94）。

用法：
  python fe_audit.py [源目录] [产物目录]
    --skip-generate   跳过重新生成，直接审计已有产物
    --json            输出 JSON（供程序消费）
    --out=FILE        同时把 JSON 摘要写盘留档（CI 可落产物；建议用 _fe_* 前缀名）
    --strict          仅有 WARN 时也以退出码 2 失败（渐进收敛的零警告路径）
    --warn-ok=S3,S12  --strict 下仍放行所列检查项的 WARN（白名单渐进收敛，R103）
    --min-pages=N     审计到少于 N 个页面即判 ERROR（默认 1；防生成器静默零产出致门禁假绿；0=关闭，R152）
    --list-checks     打印检查项注册表（代码+标题）后退出，不执行审计（R104）
    --samples=N       每个检查项的文本样例条数（默认 4；0=只计数不列样例，R109）
    --registry-json   输出机器可读能力清单（引擎/版本/检查注册表），不执行审计（R111）
    --version         仅打印引擎版本号后退出（R111）
    --capability-out=F  能力契约金样写盘（引擎+检查注册表，R113），不执行审计
    --verify-capability=F  对账能力金样，漂移则退出码 1（CI 能力演进守卫，R113）
    --explain=CODE    打印检查项速查语义后退出（R116）；未知检查项退出码 1
    --enforce-seo     S9（SEO/无障碍基线）告警升级为 ERROR（CI 硬门禁，默认随 --hard-gate 开启）
    --hard-gate       一键开齐四档门禁：strict + enforce-offline + enforce-budget + enforce-seo（R119）
    --elapsed-budget=ms  审计器自身耗时超预算即 PERF WARN（R117；负值=关闭）
    --delta=prev|cur  独立比较两份 --out 摘要（不审计），新增 ERROR 则退出码 1（R122）
    --against=FILE    审计时与历史 --out 摘要对比，差异块打印到 stderr（R125）
    --delta-out=FILE  与 --delta 同用：差异以结构化 JSON 落盘（新增/消失清单，R147）
    --tag=键=值        自定义上下文标签（可重复）进 JSON tags，CI 标注轮次/分支（R130）
    --top-pages=N     文本输出末尾追加「问题页面 Top N」榜（R129）
    --issues-json=F   把全量 issues 明细写盘留档（与摘要计数同源，R128）
    --page-json=F     把页面级明细（每页 errors/warns 分开）写盘留档（R128）
    --summary-line    输出单行 TSV 摘要（--json 时转 stderr 保 stdout 纯 JSON，R127）
    --archive=PREFIX  一次落 summary/issues/pages 三档留档包（R148）
    --config=FILE     阈值配置档（JSON；键见 THRESHOLD_META / --config-print，R133）
    --config-print    打印阈值注册表与四层优先序说明后退出（不审计，R133）
    --budget-table    文本模式打印每页首屏 JS 预算明细表（与 S12 同源，R135）
    --ignore-file=F   指定豁免文件（缺省自动发现 产物根/.fe_auditignore，R137）
    --show-ignored    把被豁免 issue 明细打印到 stderr（不污染 stdout，R140）
    --list-ignores    打印豁免文件解析结果后退出（不审计，R139）
    --schema-json     输出顶层键/issue 键清单自描述（下游零硬编码接入，R149）
    --selftest        跑纯引擎自检清单后退出（rc 0/1，不触碰目录，R143）
    --selftest-json   同上但输出机器可读报告（R144）
    --no-self         关闭每次审计前的启动静默自检（默认开启，失败即中止，R145/R146）
    --trend-json[=F]  把趋势 CSV 导出为确定性 JSON（--since=ISO 过滤；不审计，R150）
    --since=ISO       与 --trend-json 同用：只导出该时间之后的趋势记录（R150）
    --trend-dir=PATH  趋势 CSV 落盘目录（默认审计输出根；设为持久目录可使跨运行
                       体积增长被 check_perf_growth 抓到，R151）
    --ratchet         棘轮护栏：对已达清零的门禁（S2/S9/S15/S16/S20/S21/S22/S23）若计数
                       回涨高于历史最低值则升 ERROR，防后续重构悄悄回退（基线写 --ratchet-baseline，R146）
    --ratchet-baseline=PATH  棘轮基线文件路径（默认项目根 .fe_audit_ratchet.json，R146）
JSON 摘要含：schema（顶层键布局 breaking 版本）、rerun（一键复现命令，R114）、
hard_gate（R119）、page_stats（audited/with_error/with_warn，R123）、tags
（--tag 上下文，R130）；顶层键集合受 SUMMARY_KEYS 注册表执法（漂移即内部错误，
R127）；stdout 与 --out 均为 sort_keys 确定性字节序（R118）。
退出码：0=全部通过；1=存在 ERROR；2=仅有 WARN 且开启 --strict
"""
from __future__ import print_function

import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYZER = os.path.join(HERE, "matlabc.py")

# P-rev R102/R110/R111/R112/R114：引擎版本（写进 JSON 摘要与 --version/
# --registry-json，供下游识别审计器能力）；schema 版本单独计数，只表达 JSON
# 顶层键布局的 breaking 变化，与能力版本解耦。
ENGINE_VERSION = "1.16.0"
# R130：摘要新增顶层键 tags（自定义上下文）→ breaking 布局变化，schema 2 → 3。
# R127：此后任何顶层键增删都必须同步 SUMMARY_KEYS 与 SCHEMA_VERSION（自检执法）。
SCHEMA_VERSION = 3
# R-ratchet：棘轮护栏——对已达清零（历史最低 0）的门禁，若回涨则升 ERROR，防止后续
# 重构悄悄重新引入死链/内联处理器/无障碍缺陷（参考 wRA2A 清偿-棘轮机制）。--ratchet 开启。
RATCHET_CODES = ("S2", "S9", "S15", "S16", "S20", "S21", "S22", "S23")
# P-rev R104：检查项注册表（代码 -> 人类标题）。单一事实源：新检查必须先在此登记，
# 任何产出未登记代码的 issue 都会被归拢为 INT ERROR（杜绝未知代码流向下游）。
CHECK_REGISTRY = (
    ("S1", "JS 语法"),
    ("S2", "内部链接"),
    ("S3", "外部 CDN"),
    ("S4", "锚点完整性"),
    ("S5", "JS 运行时"),
    ("S6", "JS href"),
    ("S7", "孤立页面"),
    ("S8", "锚点与 id 协同"),
    ("S9", "a11y 基线"),
    ("S10", "硬编码导航"),
    ("S11", "真实 DOM"),
    ("S12", "性能预算"),
    ("S13", "重复 id"),
    ("S14", "HTML 结构"),
    ("S15", "产物-清单一致性"),
    ("S16", "质量快照一致性"),
    ("S17", "一级标题"),
    ("S18", "图片尺寸/CLS"),
    ("S19", "重复标题"),
    ("S20", "内联事件处理器"),
    ("S21", "外部脚本延迟"),
    ("S22", "内联样式"),
    ("S23", "图片替代文本"),
    ("GEN", "生成"),
    ("INT", "内部错误"),
    # R117：审计器自身的耗时预算（PERF=Performance）。不带入 S 系列，表示
    # 「审计器变慢了」而不是「站点有问题」——拖慢 CI 的检查器必须被看见。
    ("PERF", "审计器耗时预算"),
)
CHECK_IDS = frozenset(_c for _c, _t in CHECK_REGISTRY)

# P-rev R116：逐检查项速查说明（--explain=CODE 打印）。必须是 CHECK_IDS 的
# 全覆盖映射——测试会执法「每项检查都有说明」，防新检查忘了写语义文档。
CHECK_NOTES = {
    "S1": "用 node --check 校验每个内联/外链 JS 的语法，语法错误即 ERROR。",
    "S2": "站内链接/引用目标是否存在；断链、引用缺失本地资源会报错。",
    "S3": "外部 CDN/远程资源白名单核查；--enforce-offline 下任何外部引用升级为 ERROR。",
    "S4": "站内锚点（#id）目标完整性，含跨页锚点目标是否仍存在。",
    "S5": "用无头 DOM 执行页面脚本，捕获运行时抛错（jsdom 可用时）。",
    "S6": "JS 里写死的 href 目标是否存在（防脚本拼接出断链）。",
    "S7": "孤立页面：站点内存在但没有任何入口可达的 HTML。",
    "S8": "锚点与 id 协同：name/id 锚点寻址与页面实际标记的一致性。",
    "S9": "a11y 基线：img alt、可访问名称、基础无障碍结构抽查。",
    "S10": "硬编码导航：导航项数量/结构与页面实际 HTML 是否脱节。",
    "S11": "真实 DOM 渲染验证（jsdom），可抽样（--s11-limit=N，0=全量）。",
    "S12": "性能预算：JS 体积/请求数/内联体量上限（--js-budget 等可调）。",
    "S13": "重复 id：同页 id 必须唯一，保护深链与 getElementById 寻址键。",
    "S14": "HTML 结构配对与地标嵌套（防浏览器静默自我修复的结构错位）。",
    "S15": "产物-清单一致性：站点含 manifest.json 时做 sha256 对账。",
    "S16": "质量快照一致性：site-quality.json 语义复核（防成对改写失真）。",
    "S17": "一级标题：每页须有且仅有一个非空 <h1>（浏览页标题层级，5 轮收尾改进 R1）。",
    "S18": "图片尺寸：<img> 应声明 width/height（或其容器有尺寸），避免布局抖动（CLS）。缺尺寸即 WARN。",
    "S19": "重复标题：同一站点多个页面不应使用完全相同的 <title>（SEO 去重；完全相同即 WARN）。",
    "S20": "内联事件处理器：HTML 属性里的 onclick=/onload=/... 既不利于 CSP（内容安全策略），"
           "也让脚本与结构耦合、难以审计；现代前端应改用 addEventListener / 事件委托。"
           "先 WARN 记账、逐步清除，清零后再升 ERROR。",
    "S21": "外部脚本延迟：<script src=...> 未带 defer/async 会阻塞 HTML 解析、拖慢首屏；"
           "现代前端应默认 defer（或 async）。先 WARN 记账，确认全站 0 后升 ERROR。",
    "S22": "内联样式：FE-6 已将 BROWSE_CSS 外链化；FE-21 进一步把 9 个页面内联 <style> 块"
           "全部外链到 renderers/assets/page_css/*.css（仍保留 src/styles.css 基础样式）。"
           "运行时 JS 用 createElement('style') 注入的样式（源维条/浮层导航/行高亮/提示条）"
           "亦属同类反模式，须一并外链。内联样式无法被浏览器缓存、且难审计，应外链。"
           "现应趋于 0，若再出现则升 ERROR。",
    "S23": "图片替代文本：<img> 缺 alt 会让屏幕阅读器跳过或读出文件名；"
           "装饰图应有 alt=\"\" 或 aria-hidden。无障碍基线要求每张图都有 alt。"
           "先 WARN 记账，确认全站 0 后升 ERROR。",
    "GEN": "报告生成阶段结果（调用 matlabc 生成三类前端产物）。",
    "INT": "审计器内部契约错误（畸形 issue / 未登记检查项 / 审计期写文件执法）。",
    "PERF": "审计器自身耗时超 --elapsed-budget=ms 预算（WARN；是审计器变慢，非站点问题）。",
}

# P271：控制台编码兜底。
# Windows 中文环境的控制台多为 GBK，而审计结果里可能含 GBK 无法表示的字符
# （如读取外部文件经 errors='replace' 产生的 U+FFFD）。此时 print() 会抛
# UnicodeEncodeError 直接崩溃——表现为「--json 却没有任何输出、退出码 1」，
# 极易被误读成「审计发现了严重问题」。这里把 stdout/stderr 统一为 UTF-8 并
# 将无法编码的字符替换为 '?'，保证审计结果总能输出。
def _force_utf8_console():
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "buffer"):
            continue
        try:
            enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
            if enc in ("utf8", "utf_8", "utf-8"):
                continue
            setattr(sys, name, io.TextIOWrapper(
                stream.buffer, encoding="utf-8", errors="replace",
                line_buffering=True))
        except (ValueError, OSError, AttributeError):
            pass


_force_utf8_console()

# 允许出现的外部资源白名单（为空表示不允许任何外部依赖）
CDN_RE = re.compile(r"https?://[^\s\"'<>)]+")

INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                              re.S | re.I)
HREF_RE = re.compile(r'href\s*=\s*"([^"]*)"', re.I)
ID_RE = re.compile(r'\bid\s*=\s*"([^"]*)"', re.I)
# P-rev R72/R76：锚点/id 解析需要兼容单双引号两种写法。
ID_ATTR_RE = re.compile(r'\bid\s*=\s*["\']([^"\']+)["\']', re.I)
NAME_ATTR_RE = re.compile(r'<a\b[^>]*\bname\s*=\s*["\']([^"\']+)["\']', re.I)
# 动态代码段（<script>/<style> 内联体）里也可能出现 id="..." 的字符串字面量，
# 扫 id/锚点时先把它们挖空，只对真实 HTML 标记做判定，避免误报。
DYN_STRIP_RE = re.compile(r'<(script|style)\b[^>]*>.*?</\1\s*>', re.S | re.I)


# R94：批量 node 检查（S1 语法 / S5 运行时）的子进程上限。
# 与 S11 的 `--s11-timeout` 不同：那一条按页型采样、可慢到分钟级；
# 这一条只跑一批 `node --check` / 批处理脚本，正常在秒级。
# 没有它 = 挂住无上限（本仓已有真实挂死案例，见 tools/check_subprocess_hygiene.py S2）。
BATCH_TIMEOUT = 120


def _run(cmd, cwd=None, timeout=None):
    try:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, shell=False,
                             stdin=subprocess.DEVNULL)
        out, err = p.communicate(timeout=timeout)
        return p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        # R(收尾)5：子进程（如 jsdom 渲染）挂死时强制终止，避免审计无限挂起
        try:
            p.kill()
            p.communicate()
        except Exception:
            pass
        return 124, "", ("S11 超时：子进程在 %s 秒内未结束，已强制终止"
                         "（疑似页面 JS 死循环 / jsdom 挂死）" % timeout)
    except OSError as e:
        return 127, "", str(e)


# P-rev R26：审计生成的产物一律写入 outdir 下的独立子目录，避免污染交付站点。
# 此前 generate_reports 直接把 browse/、report.html、gs.html 写进 outdir；
# 当 outdir 恰为交付站点（如 _rev_site）时，会把站点页面数从 34 膨胀到 66，
# 且 S12 性能预算等检查会去审计这些「审计自己造出来的页面」，产生失真结论。
GEN_SUBDIR = "_fe_audit_gen"


def generate_reports(src, outdir, offline=False):
    """生成三种前端产物：--browse / --html / --global-state

    产物落在 outdir/_fe_audit_gen/ 下（与交付内容隔离），返回实际生成根目录，
    供后续 collect_html 精准扫描，不再误扫交付站点里的其它内容。
    """
    gen_root = os.path.join(outdir, GEN_SUBDIR)
    if os.path.isdir(gen_root):
        shutil.rmtree(gen_root, ignore_errors=True)
    os.makedirs(gen_root)
    results = {}
    offline_flag = ["--offline"] if offline else []
    cmds = [
        ("browse", [sys.executable, ANALYZER, src, "--browse",
                    os.path.join(gen_root, "browse")] + offline_flag),
        ("html", [sys.executable, ANALYZER, src, "--html",
                  os.path.join(gen_root, "report.html")] + offline_flag),
        ("global_state", [sys.executable, ANALYZER, src, "--global-state",
                          os.path.join(gen_root, "gs.html")] + offline_flag),
    ]
    for name, cmd in cmds:
        rc, out, err = _run(cmd, cwd=HERE)
        results[name] = {"rc": rc, "stderr": err[-400:] if err else ""}
    # R14：消除 report.html / gs.html 的样式表死链（S2）。
    # fe_audit 将 browse/html/global-state 分目录生成：browse 落在 gen_root/browse，
    # 而 report.html / gs.html 直接落在 gen_root。matlabc 的 CSS 写入以 browse
    # 目录为基准，因此 report.css / search.css / src/styles.css 在 gen_root 层级悬空。
    # 这里把 browse 产物中已生成的同名样式表复制到 gen_root 层级，使三产物的 <link> 均可解析。
    # 注意：只复制到 gen_root（不回写到 browse/），以免污染 browse 资产清单触发 S16。
    try:
        _browse_dir = os.path.join(gen_root, "browse")

        def _copy_css(rel):
            _src = os.path.join(_browse_dir, rel)
            _dst = os.path.join(gen_root, rel)
            if os.path.isfile(_src) and not os.path.isfile(_dst):
                _d = os.path.dirname(_dst)
                if _d and not os.path.isdir(_d):
                    os.makedirs(_d)
                with io.open(_src, "r", encoding="utf-8") as _rf:
                    _data = _rf.read()
                with io.open(_dst, "w", encoding="utf-8") as _wf:
                    _wf.write(_data)

        _copy_css("report.css")
        _copy_css("search.css")
        _copy_css(os.path.join("src", "styles.css"))
    except Exception as _e:  # pragma: no cover - 防御性兜底，不阻塞审计
        sys.stderr.write("[generate_reports] WARN: 补齐 CSS 失败：%s\n" % _e)
    # 返回生成根目录：审计只应覆盖「本次生成的产物」，而不是整个 outdir
    return results, gen_root


def collect_html(outdir):
    pages = []
    for root, _dirs, files in os.walk(outdir):
        for fn in files:
            # P-rev R94：_fe_* 是审计器自身运行时产物（趋势面板等），不计入页面
            if fn.startswith("_fe_"):
                continue
            if fn.lower().endswith((".html", ".htm")):
                pages.append(os.path.join(root, fn))
    return sorted(pages)


def check_js_syntax(pages):
    """S1：内联脚本块语法检查（**单进程批处理**）。

    原先每个脚本块各启动一次 `node --check`，在 200+ 页站点上是数百次进程启动，
    实测占审计总耗时绝大部分。现改为：把所有块落盘 → 一个 node 进程内用
    vm.Script 逐个编译 → 一次性取回失败清单。语义与 `node --check` 一致
    （只编译不执行）。批处理器不可用时自动退回逐个检查，保证结果不缺失。
    """
    issues = []
    node = shutil.which("node")
    if not node:
        return [{"level": "WARN", "check": "S1", "file": "-",
                 "msg": "未找到 node，跳过 JS 语法检查"}]
    batcher = os.path.join(HERE, "fe_js_syntax.js")
    tmpdir = tempfile.mkdtemp(prefix="feaudit_")
    try:
        # 先把所有块落盘，并记录 id → (页面, 块序号) 以便归因
        items, meta = [], []
        for page in pages:
            try:
                html = io.open(page, "r", encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for idx, body in enumerate(INLINE_SCRIPT_RE.findall(html)):
                if not body.strip():
                    continue
                blk_id = len(items)
                js = os.path.join(tmpdir, "blk_%d.js" % blk_id)
                with io.open(js, "w", encoding="utf-8") as fh:
                    fh.write(body)
                items.append({"id": blk_id, "path": js})
                meta.append((page, idx))
        if not items:
            return issues

        fails = None
        if os.path.exists(batcher):
            manifest = os.path.join(tmpdir, "manifest.json")
            with io.open(manifest, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(items))
            # stdin/stdout 用二进制管道 + 手工解码：避免 Windows 控制台
            # 编码（GBK）导致子进程输出中的非 GBK 字符让解析失败。
            try:
                pr = subprocess.run([node, batcher, manifest],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    stdin=subprocess.DEVNULL,
                                    timeout=BATCH_TIMEOUT)
                raw = pr.stdout.decode("utf-8", "replace")
                if raw.strip():
                    fails = json.loads(raw).get("fails")
            except (ValueError, OSError) as e:
                issues.append({"level": "WARN", "check": "S1", "file": "-",
                               "msg": "批量语法检查异常，退回逐个检查：%s" % e})
                fails = None

        if fails is None:
            # 退回逐个检查（批处理器缺失或异常），保证检查不被静默跳过
            for it in items:
                rc, _o, err = _run([node, "--check", it["path"]])
                if rc != 0:
                    fails = fails or []
                    fails.append({"id": it["id"], "msg": err.strip()[:300]})

        for f in (fails or []):
            try:
                page, idx = meta[f["id"]]
            except (IndexError, KeyError, TypeError):
                continue
            issues.append({
                "level": "ERROR", "check": "S1", "file": page,
                "msg": "内联脚本 #%d 语法错误：%s" % (idx, f.get("msg", ""))})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return issues


def _strip_scripts(html):
    """移除 script/style 块：其中的 JS 字符串拼接（如 'x.html?g='+gid）
    不是真实 href，必须排除，否则 S2 会产生大量误报。"""
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
    return html


# XML 命名空间不是网络请求（如 SVG 的 xmlns），不应算外部依赖
NS_WHITELIST = ("http://www.w3.org/", "https://www.w3.org/")


def check_links_and_cdn(outdir, pages):
    """S2 内部链接 + S3 外部 CDN + S4 锚点"""
    issues = []
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        base = os.path.dirname(page)
        html = _strip_scripts(raw)
        ids = set(ID_RE.findall(html))
        for href in HREF_RE.findall(html):
            if not href or href.startswith("#"):
                continue
            # S3 外部 CDN
            if href.startswith(("http://", "https://", "//")):
                if not href.startswith(NS_WHITELIST):
                    issues.append({"level": "WARN", "check": "S3", "file": page,
                                   "msg": "引用外部资源（离线不可用）：%s" % href})
                continue
            if href.startswith(("mailto:", "javascript:", "data:")):
                continue
            # S4 锚点
            if "#" in href:
                path_part, _, frag = href.partition("#")
            else:
                path_part, frag = href, None
            # 查询串（如 ?g=20）不是文件路径的一部分，判存在性前必须剥离
            if "?" in path_part:
                path_part = path_part.split("?", 1)[0]
            # S2 文件存在性
            if path_part:
                target = os.path.normpath(os.path.join(base, path_part))
                if not os.path.exists(target):
                    issues.append({"level": "ERROR", "check": "S2", "file": page,
                                   "msg": "死链：%s -> %s" % (href, target)})
                    continue
            if frag:
                # 锚点可能指向目标页（跨页锚点），这里只判同页锚点
                if (not path_part) and frag and frag not in ids:
                    issues.append({"level": "ERROR", "check": "S4", "file": page,
                                   "msg": "锚点不存在：#%s" % frag})
        # S3：内联脚本里的外链（如动态注入 CDN）
        for body in INLINE_SCRIPT_RE.findall(raw):
            for url in CDN_RE.findall(body):
                if url.startswith(NS_WHITELIST):
                    continue
                issues.append({"level": "WARN", "check": "S3", "file": page,
                               "msg": "脚本内引用外部 CDN：%s" % url})
    return issues


DOM_STUB = r"""
// 最小 DOM stub：让前端内联脚本可在 Node 中「跑一遍」，捕获运行期异常。
var __errors = [];
function __mkEl(tag){
  var el = {
    tagName:(tag||'div').toUpperCase(), style:{}, dataset:{}, children:[], childNodes:[],
    className:'', id:'', value:'', textContent:'', innerHTML:'', href:'', src:'',
    checked:false, disabled:false, scrollTop:0, scrollLeft:0, offsetWidth:800, offsetHeight:600,
    clientWidth:800, clientHeight:600, attributes:{},
    classList:{ add:function(){}, remove:function(){}, toggle:function(){}, contains:function(){return false;} },
    setAttribute:function(k,v){ this.attributes[k]=v; if(k==='id'){this.id=v;} },
    getAttribute:function(k){ return this.attributes[k]!==undefined?this.attributes[k]:null; },
    removeAttribute:function(k){ delete this.attributes[k]; },
    hasAttribute:function(k){ return this.attributes[k]!==undefined; },
    appendChild:function(c){ this.children.push(c); return c; },
    removeChild:function(c){ return c; }, insertBefore:function(c){ return c; },
    addEventListener:function(){}, removeEventListener:function(){},
    querySelector:function(){ return null; }, querySelectorAll:function(){ return []; },
    getElementsByTagName:function(){ return []; }, getElementsByClassName:function(){ return []; },
    closest:function(){ return null; }, contains:function(){ return false; },
    focus:function(){}, blur:function(){}, click:function(){}, scrollIntoView:function(){},
    getBoundingClientRect:function(){ return {left:0,top:0,width:800,height:600,right:800,bottom:600}; },
    getContext:function(){ return null; },
    setProperty:function(){}, getPropertyValue:function(){ return ''; },
    insertAdjacentHTML:function(){}, remove:function(){}, cloneNode:function(){ return __mkEl(tag); },
    matches:function(){ return false; }, animate:function(){ return {finished:Promise.resolve()}; }
  };
  return el;
}
var __doc = {
  _byId:{}, head:__mkEl('head'), body:__mkEl('body'),
  documentElement:__mkEl('html'), title:'', readyState:'complete',
  createElement:function(t){ return __mkEl(t); },
  createElementNS:function(ns,t){ return __mkEl(t); },
  createTextNode:function(t){ return {nodeValue:t, textContent:t}; },
  createDocumentFragment:function(){ return __mkEl('fragment'); },
  // P271：未知 id 返回一个（缓存的）桩元素，而不是 null。
  // 理由：本 stub 不解析 HTML，页面里真实存在的元素（如 <div id="fd-root">）
  // 在 stub 中查不到；若返回 null，`el.innerHTML = ...` 就会抛异常，
  // 产出**由 stub 能力不足导致的假故障**（真实浏览器里该元素存在，S11/jsdom 可佐证）。
  // 这样改之后，S5 报出的才是真正的 JS 错误（未定义变量/函数、类型错误等）。
  getElementById:function(id){
    if(!this._byId[id]) this._byId[id] = __mkEl('div');
    return this._byId[id];
  },
  querySelector:function(){ return null; }, querySelectorAll:function(){ return []; },
  getElementsByTagName:function(){ return []; }, getElementsByClassName:function(){ return []; },
  addEventListener:function(){}, removeEventListener:function(){},
  execCommand:function(){ return true; },
  createRange:function(){ return {selectNodeContents:function(){}, getBoundingClientRect:function(){return {};}}; }
};
var window = {
  document:__doc, navigator:{userAgent:'node', clipboard:null, language:'zh-CN'},
  location:{ href:'http://localhost/test.html', hash:'', search:'', pathname:'/test.html',
             protocol:'http:', host:'localhost', origin:'http://localhost',
             assign:function(){}, replace:function(){}, reload:function(){} },
  history:{ pushState:function(){}, replaceState:function(){}, back:function(){}, forward:function(){} },
  localStorage:{ _s:{}, getItem:function(k){ return this._s[k]===undefined?null:this._s[k]; },
                 setItem:function(k,v){ this._s[k]=String(v); }, removeItem:function(k){ delete this._s[k]; },
                 clear:function(){ this._s={}; } },
  sessionStorage:{ _s:{}, getItem:function(k){ return null; }, setItem:function(){}, removeItem:function(){}, clear:function(){} },
  matchMedia:function(){ return {matches:false, addListener:function(){}, addEventListener:function(){}}; },
  requestAnimationFrame:function(f){ return 0; }, cancelAnimationFrame:function(){},
  setTimeout:function(){ return 0; }, clearTimeout:function(){},
  setInterval:function(){ return 0; }, clearInterval:function(){},
  addEventListener:function(){}, removeEventListener:function(){},
  getComputedStyle:function(){ return {getPropertyValue:function(){ return ''; }}; },
  alert:function(){}, confirm:function(){ return true; }, prompt:function(){ return ''; },
  open:function(){ return null; }, print:function(){}, scrollTo:function(){},
  innerWidth:1200, innerHeight:800, devicePixelRatio:1, pageXOffset:0, pageYOffset:0,
  performance:{ now:function(){ return 0; } }, console:console,
  fetch:function(){ return Promise.reject(new Error('no network')); }
};
var document = __doc;
var navigator = window.navigator;
var location = window.location;
var history = window.history;
var localStorage = window.localStorage;
var sessionStorage = window.sessionStorage;
var screen = { width:1200, height:800 };
var alert = window.alert, confirm = window.confirm, prompt = window.prompt;
var setTimeout = window.setTimeout, clearTimeout = window.clearTimeout;
var setInterval = window.setInterval, clearInterval = window.clearInterval;
var requestAnimationFrame = window.requestAnimationFrame;
var getComputedStyle = window.getComputedStyle;
var fetch = window.fetch;
var Image = function(){ return __mkEl('img'); };
var XMLHttpRequest = function(){
  this.open=function(){}; this.send=function(){}; this.setRequestHeader=function(){};
  this.addEventListener=function(){}; this.readyState=4; this.status=0;
};
process.on('uncaughtException', function(e){ __errors.push(String(e && e.message || e)); });
"""


def check_js_runtime(pages):
    """S5：DOM stub 中执行内联脚本，捕获运行期异常（**单进程批处理**）。

    原先每页各启动一次 node 进程，218 页站点上约 43s 几乎全是进程启动开销。
    现改为单进程 + 每页一个 vm 上下文：既省掉进程开销，又**保持页间隔离**——
    若简单拼接，页 A 里 `window.__GS_LOADED__ = true` 会让页 B 的脚本提前 return，
    从而漏掉页 B 的真实错误（假阴性比慢危险得多）。
    批处理器不可用时自动退回逐页检查，保证结果不缺失。
    """
    issues = []
    node = shutil.which("node")
    if not node:
        return [{"level": "WARN", "check": "S5", "file": "-",
                 "msg": "未找到 node，跳过运行时检查"}]
    batcher = os.path.join(HERE, "fe_js_runtime.js")

    def _page_script(html, with_emit):
        parts = [DOM_STUB]
        if with_emit:
            # R94：emit 必须注册在**页面脚本之前**。DOM_STUB 里的
            # process.on('uncaughtException') 会吞掉异常，但「吞掉」≠「恢复执行」——
            # 异常点之后的任何代码都不会再跑。此前把 console.log 写在末尾，
            # 于是页面一抛错就永远打印不到 __errors（表现为 rc=0 且零输出），
            # 逐页回退路径 100% 漏检、S5 形同虚设。改挂 exit 钩子并前置注册。
            parts.append("\nprocess.on('exit', function(){ "
                         "console.log('__AUDIT_ERR__' + JSON.stringify(__errors)); });\n")
        for b in (b for b in INLINE_SCRIPT_RE.findall(html) if b.strip()):
            parts.append("\n// ---- block ----\n")
            parts.append(b)
        return "".join(parts)

    tmpdir = tempfile.mkdtemp(prefix="feaudit_")
    try:
        items, meta = [], []
        for page in pages:
            try:
                html = io.open(page, "r", encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            # 没有任何内联脚本的页面无需跑
            if not [b for b in INLINE_SCRIPT_RE.findall(html) if b.strip()]:
                continue
            pid = len(items)
            js = os.path.join(tmpdir, "run_%d.js" % pid)
            with io.open(js, "w", encoding="utf-8") as fh:
                fh.write(_page_script(html, with_emit=False))
            items.append({"id": pid, "path": js})
            meta.append(page)
        if not items:
            return issues

        fails = None
        if os.path.exists(batcher):
            manifest = os.path.join(tmpdir, "manifest.json")
            with io.open(manifest, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(items))
            try:
                pr = subprocess.run([node, batcher, manifest],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    stdin=subprocess.DEVNULL,
                                    timeout=BATCH_TIMEOUT)
                raw = pr.stdout.decode("utf-8", "replace")
                if raw.strip():
                    fails = json.loads(raw).get("fails")
            except (ValueError, OSError) as e:
                issues.append({"level": "WARN", "check": "S5", "file": "-",
                               "msg": "批量运行时检查异常，退回逐页检查：%s" % e})
                fails = None

        if fails is None:
            # 退回逐页（批处理器缺失/异常时），结果不静默丢失
            for it in items:
                page = meta[it["id"]]
                try:
                    html = io.open(page, "r", encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                js = os.path.join(tmpdir, "fb_%d.js" % it["id"])
                with io.open(js, "w", encoding="utf-8") as fh:
                    fh.write(_page_script(html, with_emit=True))
                rc, out, err = _run([node, js])
                if "__AUDIT_ERR__" in out:
                    try:
                        errs = json.loads(
                            out.split("__AUDIT_ERR__", 1)[1].strip().splitlines()[0])
                    except (ValueError, IndexError):
                        errs = ["<解析失败>"]
                elif rc != 0:
                    errs = ["执行失败(rc=%d)：%s" % (rc, (err or "")[:300])]
                else:
                    errs = []
                if errs:
                    fails = fails or []
                    fails.append({"id": it["id"], "errors": errs[:5]})

        for f in (fails or []):
            try:
                page = meta[f["id"]]
            except (IndexError, KeyError, TypeError):
                continue
            for e in (f.get("errors") or [])[:5]:
                issues.append({"level": "ERROR", "check": "S5", "file": page,
                               "msg": "运行时异常：%s" % e})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return issues


def check_js_hrefs(pages):
    """S8：脚本字符串里的链接（此前完全没有被检查的一类死链）。

    大量链接是 JS 动态拼出来的（如 `'<a href="func_detail.html?g='+gid+'">'`）。
    这些链接同样会让「点击无反应」，但只扫 HTML 的 href 提取不到。
    这里只校验**可静态解析**的字面量（不含字符串拼接），避免误报。
    """
    issues = []
    js_href_re = re.compile(r'href\s*=\s*[\\]?"([^"\\]*)')
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        base = os.path.dirname(page)
        seen = set()
        for body in INLINE_SCRIPT_RE.findall(raw):
            for href in js_href_re.findall(body):
                if not href or href in seen:
                    continue
                seen.add(href)
                if href.startswith(("http://", "https://", "#", "javascript:", "data:")):
                    continue
                # 含拼接的动态 href 无法静态判定，跳过
                if "'+" in href or "\"+" in href or "+" in href:
                    continue
                path_part = href.split("#", 1)[0].split("?", 1)[0]
                if not path_part:
                    continue
                target = os.path.normpath(os.path.join(base, path_part))
                if not os.path.exists(target):
                    issues.append({"level": "ERROR", "check": "S8", "file": page,
                                   "msg": "JS 内死链：%s -> %s" % (href, target)})
    return issues


def _collect_external_js(page, raw, _cache={}):
    """汇总页面 `<script src=...>` 指向的**本地**脚本内容（P-rev R27）。

    站点把大模块外链化后，很多函数不再内联在页面里。S6 若只看内联脚本，
    会把这些函数误判为「未定义」。这里按相对路径解析出本地 js 文件内容并缓存
    （同一批 js 会被成百上千个页面引用，不缓存会重复读盘）。
    """
    base = os.path.dirname(page)
    parts = []
    for src in SRC_SCRIPT_RE.findall(raw):
        if src.startswith(("http://", "https://", "//")):
            continue
        path_part = src.split("#", 1)[0].split("?", 1)[0]
        if not path_part:
            continue
        target = os.path.normcase(os.path.normpath(os.path.join(base, path_part)))
        if target in _cache:
            parts.append(_cache[target])
            continue
        try:
            txt = io.open(target, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            txt = ""
        _cache[target] = txt
        parts.append(txt)
    return "\n".join(parts)


def check_interaction_wiring(pages):
    """S6：交互接线检查（零依赖，直接命中「点了没反应」类缺陷）。

    两类最常见的交互失效：
      · onclick / href="javascript:" 里调用的函数，页面里**根本没有定义**；
      · JS 里 getElementById('x') / querySelector('#x') 的 'x' **在页面中不存在**。
    两者都会静默失效（按钮点了没反应），且语法检查发现不了。
    """
    issues = []
    onclick_re = re.compile(r'\bon(?:click|change|input|submit)\s*=\s*"([^"]*)"', re.I)
    js_call_re = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
    getel_re = re.compile(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)")
    qsel_re = re.compile(r"querySelector(?:All)?\(\s*['\"]#([A-Za-z_][\w-]*)['\"]")
    fn_def_re = re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*\(")
    fn_var_re = re.compile(r"(?:var|let|const|window)\s*\.?\s*([A-Za-z_$][\w$]*)\s*=\s*function")
    # P-rev R27：window.xxx = ... 形式的全局导出（外链模块对外暴露函数的常见写法）
    win_assign_re = re.compile(r"window\s*\.\s*([A-Za-z_$][\w$]*)\s*=")
    BUILTINS = set("""if for while switch catch return typeof function alert confirm prompt
        parseInt parseFloat isNaN String Number Boolean Array Object JSON Math Date RegExp
        encodeURIComponent decodeURIComponent setTimeout clearTimeout setInterval clearInterval
        requestAnimationFrame require console window document location history localStorage
        fetch Promise Error Map Set eval super this new delete void in of instanceof
        """.split())
    # DOM / 宿主方法：onclick 里常见，不是用户自定义函数，不能算「未定义」
    DOM_METHODS = set("""getElementById querySelector querySelectorAll getElementsByTagName
        getElementsByClassName closest contains appendChild removeChild insertBefore setAttribute
        getAttribute removeAttribute hasAttribute addEventListener removeEventListener preventDefault
        stopPropagation focus blur click scrollIntoView toggle add remove join split slice indexOf
        push pop map filter forEach trim replace toLowerCase toUpperCase toString valueOf
        """.split())
    BUILTINS |= DOM_METHODS

    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        html = _strip_scripts(raw)
        scripts = "\n".join(INLINE_SCRIPT_RE.findall(raw))
        # P-rev R27：函数定义**也要算上外链脚本**。站点把大模块外链化（如
        # src/_localcg.js 63KB）后，内联 onclick 里调用的 cgFindPath() 等函数
        # 定义在外部文件里；若只扫内联脚本，S6 会把它误报为「未定义函数」。
        # 注意：id 扫描仍只看内联脚本，避免外部脚本里的 id 引入新的误报。
        ext_js = _collect_external_js(page, raw)
        defined = (set(fn_def_re.findall(scripts)) | set(fn_var_re.findall(scripts))
                   | set(fn_def_re.findall(ext_js)) | set(fn_var_re.findall(ext_js))
                   | set(win_assign_re.findall(ext_js)))
        ids = set(ID_RE.findall(html))

        # 1) 内联事件处理器里调用的函数是否已定义
        for handler in onclick_re.findall(html):
            for callee in js_call_re.findall(handler):
                if callee in BUILTINS or callee in defined:
                    continue
                issues.append({
                    "level": "ERROR", "check": "S6", "file": page,
                    "msg": "事件处理器调用了未定义函数 %s()：「%s」" % (callee, handler[:80])})

        # 2) JS 里引用的元素 id 是否存在。
        #    注意：大量元素是 JS 动态创建（id 只出现在脚本字符串里），
        #    因此只要该 id 字面量在整页任意位置出现过，就认为存在，避免误报。
        for eid in set(getel_re.findall(scripts)) | set(qsel_re.findall(scripts)):
            if eid in ids:
                continue
            # 以 - / _ 结尾的是拼接前缀（如 'dup-row-' + i），不是真实 id
            if eid.endswith("-") or eid.endswith("_"):
                continue
            if (('"%s"' % eid) in raw or ("'%s'" % eid) in raw
                    or ('id=\\"%s\\"' % eid) in raw or ("id='%s'" % eid) in raw):
                continue        # 动态创建
            issues.append({
                "level": "ERROR", "check": "S6", "file": page,
                "msg": "JS 引用了不存在的元素 id：#%s" % eid})
    return issues


# 用户直接打开、无需被链接的入口页
ENTRY_PAGES = ("index.html", "report.html", "gs.html", "unified.html")


def check_orphan_pages(outdir, pages):
    """S7：孤儿页面 —— 没有任何其它页面链接到它。

    这类页面虽然生成了，但用户在 UI 里**点不到**（只能手敲路径），
    属于典型的可用性缺陷：功能做了，却没人能找到。
    """
    issues = []
    referenced = set()
    for page in pages:
        try:
            html = _strip_scripts(io.open(page, "r", encoding="utf-8",
                                          errors="replace").read())
        except OSError:
            continue
        base = os.path.dirname(page)
        for href in HREF_RE.findall(html):
            if not href or href.startswith(("#", "http", "mailto:", "javascript:", "data:")):
                continue
            path_part = href.split("#", 1)[0].split("?", 1)[0]
            if not path_part:
                continue
            try:
                referenced.add(os.path.normcase(os.path.normpath(
                    os.path.join(base, path_part))))
            except (ValueError, OSError):
                pass
    for page in pages:
        name = os.path.basename(page)
        if name in ENTRY_PAGES:
            continue
        if os.path.normcase(os.path.normpath(page)) in referenced:
            continue
        issues.append({"level": "WARN", "check": "S7", "file": page,
                       "msg": "孤儿页面：没有任何页面链接到它（UI 中无法到达）"})
    return issues


# P-rev：S20 内联事件处理器守卫——HTML 属性里的 onclick=/onload=/... 既不利于
# CSP（内容安全策略），也让「脚本与结构」耦合、难以审计；现代前端应改用
# addEventListener / 事件委托。先 WARN 记账、逐步清除，清零后再升 ERROR。
INLINE_HANDLER_RE = re.compile(
    r'\b(on(?:click|dblclick|mousedown|mouseup|mousemove|mouseover|mouseout|mouseenter|'
    r'mouseleave|keydown|keypress|keyup|change|input|submit|reset|focus|blur|load|error|'
    r'resize|scroll|contextmenu|wheel|touchstart|touchend|touchmove|drag|drop|dragover|'
    r'hashchange|DOMContentLoaded|pageshow|pagehide|beforeunload|unload)\s*=)',
    re.IGNORECASE)

def check_inline_handlers(pages):
    """S20：内联事件处理器（onclick= 等 HTML 属性）守卫。"""
    issues = []
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        # 仅查 HTML 标签属性（跳过 <script> 内的合法 JS 赋值如 b.onclick=function）。
        html = _strip_scripts(raw)
        for m in INLINE_HANDLER_RE.finditer(html):
            issues.append({"level": "WARN", "check": "S20", "file": page,
                           "msg": "内联事件处理器：%s" % m.group(0)[:40]})
    return issues

# P-rev：S21 外部脚本延迟门禁——<script src=...> 未带 defer/async 会阻塞 HTML 解析、
# 拖慢首屏；现代前端应默认 defer（或 async）。先 WARN 记账，确认全站 0 后升 ERROR。
def check_external_script_defer(pages):
    """S21：外部脚本缺少 defer/async（解析阻塞）守卫。"""
    issues = []
    for page in pages:
        try:
            html = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in re.finditer(r"<script\b([^>]*)>", html, re.I):
            _attrs = m.group(1)
            if "src" not in _attrs:
                continue
            if "defer" not in _attrs and "async" not in _attrs:
                issues.append({"level": "WARN", "check": "S21", "file": page,
                               "msg": "外部脚本缺少 defer/async：%s" % m.group(0)[:60]})
    return issues

def _collect_linked_css(page, html):
    """收集页面样式（内联 <style> + 外链样式表），用于 a11y 检查。

    CSS 已外链化（FE-6）后 :focus 等不在 HTML 内联，故需同时扫描外链样式表；
    报告页等可能仍内联 CSS，故也收集 <style> 内容。
    """
    _css = []
    for m in re.finditer(r"<style\b[^>]*>(.*?)</style>", html, re.I | re.S):
        _css.append(m.group(1))
    _base = os.path.dirname(page)
    for m in re.finditer(r'<link\b[^>]*rel="stylesheet"[^>]*href="([^"]+)"', html, re.I):
        _href = m.group(1)
        if _href.startswith(("http://", "https://", "//", "data:")):
            continue
        _p = os.path.normpath(os.path.join(_base, _href))
        try:
            _css.append(io.open(_p, "r", encoding="utf-8", errors="replace").read())
        except OSError:
            pass
    return "\n".join(_css)

# P-rev：S22 内联样式门禁——FE-6 已将 BROWSE_CSS 外链化，FE-21 又把 9 个页面内联 <style> 块
# 全部外链到 renderers/assets/page_css/*.css。内联样式无法被浏览器缓存、且难审计，应外链。
# 现应趋于 0（生成产物中不再有 <style> 块），若再出现则升 ERROR。
# 覆盖两类：①静态 HTML 的 <style>...</style>；②运行时 JS 用 document.createElement('style')
# 注入的样式（FE-21 同类的内联反模式，静态 <style> 正则抓不到，须单独匹配）。
INLINE_STYLE_RE = re.compile(r"<style\b[^>]*>", re.I)
# 运行时由 JS 注入的 <style> 块（FE-21 外链化时应一并消除）
JS_INLINE_STYLE_RE = re.compile(r"createElement\(\s*['\"]style['\"]\s*\)", re.I)

def check_inline_style(pages):
    """S22：内联 <style> 块（应外链，便于缓存与审计）守卫。
    覆盖：①静态 HTML 的 <style>...</style>；②运行时 JS createElement('style') 注入。"""
    issues = []
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in INLINE_STYLE_RE.finditer(raw):
            issues.append({"level": "WARN", "check": "S22", "file": page,
                           "msg": "内联 <style> 块（静态）：%s" % m.group(0)[:40]})
        for m in JS_INLINE_STYLE_RE.finditer(raw):
            issues.append({"level": "WARN", "check": "S22", "file": page,
                           "msg": "内联 <style> 块（JS 运行时注入）：%s" % m.group(0)[:40]})
    return issues

# P-rev：S23 图片替代文本门禁——<img> 缺 alt 会让屏幕阅读器跳过或读出文件名，
# 装饰图应有 alt="" 或 aria-hidden。无障碍基线要求每张图都有 alt。先 WARN 记账。
IMG_RE = re.compile(r"<img\b[^>]*>", re.I)

def check_img_alt(pages):
    """S23：<img> 缺少 alt 属性（无障碍替代文本）守卫。"""
    issues = []
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in IMG_RE.finditer(raw):
            _tag = m.group(0)
            if "alt=" not in _tag and "aria-hidden" not in _tag:
                issues.append({"level": "WARN", "check": "S23", "file": page,
                               "msg": "<img> 缺少 alt：%s" % _tag[:50]})
    return issues

def check_a11y_baseline(pages):
    """S9：无障碍基线 —— lang / skip-link 锚点 / <main> 语义地标。

    这是 P271 R5 修复前的**审计盲区**：此前只做子串匹配（`'skip-link' in html`），
    而 BROWSE_CSS 里含 `.skip-link{...}` 规则文本，会让所有页面误判为「已具备」。
    必须校验**真实锚点元素**，否则屏幕阅读器/键盘用户实际上无路可走。
    """
    issues = []
    for page in pages:
        try:
            html = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        _linked_css = _collect_linked_css(page, html)
        name = os.path.basename(page)
        if "lang=" not in html:
            issues.append({"level": "ERROR", "check": "S9", "file": page,
                           "msg": "缺少 lang 属性（屏幕阅读器无法选择正确语音）"})
        # R6：收紧——要求带区域子标签的 BCP47（zh-CN 而非裸 zh / zh-Hans）。
        # 裸语言标签会让屏幕阅读器仍可能选错区域口音；标记 WARN 倒逼修正，
        # 且对后续迭代形成「区域具体化」的护栏。
        _m_lang = re.search(r'lang="([^"]*)"', html)
        if _m_lang and _m_lang.group(1) in ("zh", "en", "zh-Hans", "zh-Hant"):
            issues.append({"level": "WARN", "check": "S9", "file": page,
                           "msg": "lang 属性缺少区域子标签（%s），建议用 zh-CN 等具体区域"
                           % _m_lang.group(1)})
        # 真实锚点元素（兼容单/双引号），不能只匹配 CSS 文本
        if ('class="skip-link"' not in html and "class='skip-link'" not in html):
            issues.append({"level": "ERROR", "check": "S9", "file": page,
                           "msg": "缺少 skip-link 锚点元素（键盘用户无法跳到主内容）"})
        elif ":focus" not in html and "skip-link:focus" not in _linked_css:
            issues.append({"level": "WARN", "check": "S9", "file": page,
                           "msg": "skip-link 未见 :focus 显现样式，聚焦后可能仍不可见"})
        if "<main" not in html:
            issues.append({"level": "ERROR", "check": "S9", "file": page,
                           "msg": "缺少 <main> 语义地标（无主内容区域）"})
        # 关键：校验 skip-link 的**实际跳转目标**存在（不能靠 `id="main` 这种字符串猜测，
        # gs.html 用的是 id="gs-main"，同样合法）。
        m = re.search(r'class="skip-link"\s+href="#([^"]+)"', html)
        if m:
            target = m.group(1)
            if ('id="%s"' % target) not in html:
                issues.append({"level": "ERROR", "check": "S9", "file": page,
                               "msg": "skip-link 的目标 #%s 不存在（跳了等于没跳）" % target})
        elif "<main" in html:
            issues.append({"level": "WARN", "check": "S9", "file": page,
                           "msg": "skip-link 未指向具体锚点，无法校验跳转目标"})
        # R10：落实 CHECK_NOTES 声称的 img-alt 检查（此前 S9 只查结构，漏了 alt）。
        # 先剔除 <script> 块，避免 JS 模板字符串里的 `<img` 误判；再扫描真实图片。
        _body = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
        for _img in re.findall(r"<img\b[^>]*>", _body, re.I):
            if not re.search(r"\balt=", _img, re.I):
                issues.append({"level": "WARN", "check": "S9", "file": page,
                               "msg": "图片缺少 alt 属性（屏幕阅读器无法描述内容）"})
                break
        # R11：图片性能基线——首屏外图片应声明 loading="lazy"（WARN 级，不阻断）。
        for _img in re.findall(r"<img\b[^>]*>", _body, re.I):
            if not re.search(r"\bloading=", _img, re.I):
                issues.append({"level": "WARN", "check": "S9", "file": page,
                               "msg": "图片未声明 loading 属性（建议首屏外图片加 loading=\"lazy\"）"})
                break
        # R-收尾：SEO/结构基线补强（沿用 S9「a11y/SEO 基线」定位，不新增检查码/能力金样）。
        if not re.search(r'<meta[^>]+name=["\']description', _body, re.I):
            issues.append({"level": "WARN", "check": "S9", "file": page,
                           "msg": "缺少 meta description（SEO/可访问性基线缺失）"})
        if not re.search(r'property=["\']og:', _body, re.I):
            issues.append({"level": "WARN", "check": "S9", "file": page,
                           "msg": "缺少 Open Graph 社交分享元信息"})
        for _th in re.findall(r"<th\b[^>]*>", _body, re.I):
            if not re.search(r"\bscope=", _th, re.I):
                issues.append({"level": "WARN", "check": "S9", "file": page,
                               "msg": "数据表 <th> 缺少 scope 属性（屏幕阅读器无法朗读表头归属）"})
                break
        # 仅「无 aria-label、无 title、且无可见文本」才算真正无名的图标按钮：
        # 按钮的可见文本本身就是合法的 accessible name（WAI-ARIA），
        # 早先只看 aria-label/title 会把 <button>重新布局</button> 之类误报。
        for _bm in re.finditer(r"<button\b[^>]*>(.*?)</button>", _body, re.S | re.I):
            _btag = _bm.group(0)
            if (re.search(r"\baria-label=", _btag, re.I)
                    or re.search(r"\btitle=", _btag, re.I)):
                continue
            if re.sub(r"<[^>]+>", "", _bm.group(1)).strip():
                continue
            issues.append({"level": "WARN", "check": "S9", "file": page,
                           "msg": "纯图标按钮无可见文本且缺 aria-label/title（屏幕阅读器读到空按钮）"})
            break
        if not re.search(r'<meta[^>]+name=["\']viewport', _body, re.I):
            issues.append({"level": "WARN", "check": "S9", "file": page,
                           "msg": "缺少 viewport meta（移动端布局不可用）"})
    return issues


# 形如 location.href = 'func_detail.html?g=' + it.g —— 在 browse/src/ 子目录页会解析成
# src/func_detail.html，是 P269/P271 反复出现的同一类死链。正确写法是加上 SITE_REL 前缀。
HARDCODED_NAV_RE = re.compile(
    r"location(?:\.href)?\s*=\s*['\"]([A-Za-z0-9_./-]+\.html)")
# 允许的动态前缀变量（表示已按页面深度计算过）
SAFE_PREFIX_RE = re.compile(r"^[A-Za-z_$][\w$.]*\s*\+")


def check_hardcoded_nav(pages):
    """S10：JS 内硬编码页面路径 —— 子目录页会解析成死链。

    典型缺陷：`window.location.href = 'func_detail.html?g=' + it.g;`
    在 browse/src/foo.m.html 上会解析为 browse/src/func_detail.html（不存在）。
    正确写法是拼接 SITE_REL / __CG_SITE_REL__ 前缀。
    """
    issues = []
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for body in INLINE_SCRIPT_RE.findall(raw):
            for m in HARDCODED_NAV_RE.finditer(body):
                # 取赋值号后到字面量之间的一小段，判断是否已有动态前缀
                head_start = max(0, m.start() - 40)
                head = body[head_start:m.start(1)]
                if SAFE_PREFIX_RE.search(head.strip()):
                    continue        # 已带 SITE_REL 之类的前缀变量
                issues.append({
                    "level": "ERROR", "check": "S10", "file": page,
                    "msg": "JS 跳转硬编码页面路径 '%s'（子目录页会解析成死链，"
                           "应拼接 SITE_REL 前缀）" % m.group(1)})
    return issues


def _opt_str(args, prefix, default=None):
    """解析形如 --xxx=值 的字符串选项，缺失时返回默认值（P-rev R98）。"""
    for a in args:
        if a.startswith(prefix):
            return a[len(prefix):]
    return default


def _opt_int(args, prefix, default):
    """解析形如 --xxx=123 的整数选项，缺失或非法时返回默认值。"""
    for a in args:
        if a.startswith(prefix):
            try:
                return int(a[len(prefix):])
            except ValueError:
                return default
    return default


def _count_by_check(items):
    """按检查项聚合 ERROR/WARN 条数（R102：JSON 与文本两种输出共用同一聚合）。"""
    out = {}
    for it in items:
        ck = it.get("check")
        if ck not in out:
            out[ck] = {"ERROR": 0, "WARN": 0}
        lv = it.get("level")
        if lv in ("ERROR", "WARN"):
            out[ck][lv] += 1
    return out


def _apply_ratchet(by_check, baseline_path):
    """棘轮护栏：对 RATCHET_CODES 中已达清零的门禁，若计数回涨到高于历史最低值则追加
    ERROR（check=INT，与「未登记检查项 / 未声明产物」同属内部错误）。返回新增 issue 列表。

    基线（各门禁历史最小计数）持久化到 baseline_path：首次运行仅建立基线、不升级；之后
    仅当某门禁计数高于历史最低值时才报回归，确保「清零成果」不可被悄然回退（棘轮只进不退）。
    基线文件写在 HERE（项目根），不落入审计产物树，故不会触发 R96「未声明产物」自检。
    """
    cur = {c: by_check.get(c, {}).get("ERROR", 0)
           + by_check.get(c, {}).get("WARN", 0) for c in RATCHET_CODES}
    base = {}
    if os.path.isfile(baseline_path):
        try:
            with open(baseline_path, "r", encoding="utf-8") as _f:
                base = json.load(_f)
        except (ValueError, OSError):
            base = {}
    added = []
    for c in RATCHET_CODES:
        now = cur[c]
        prev = base.get(c)
        if prev is None or now < prev:
            base[c] = now
        elif now > prev:
            added.append({
                "level": "ERROR", "check": "INT", "file": "",
                "msg": "[棘轮护栏] 门禁 %s 回涨：当前 %d > 历史最低 %d"
                       % (c, now, prev)})
    try:
        with open(baseline_path, "w", encoding="utf-8") as _f:
            json.dump(base, _f, ensure_ascii=False, sort_keys=True, indent=2)
    except OSError:
        pass
    return added


def _parse_warn_ok(args):
    """解析 --warn-ok=S3,S12（逗号分隔的检查代码集合，R103）。"""
    raw = _opt_str(args, "--warn-ok=", "")
    out = set()
    for tok in raw.split(","):
        tok = tok.strip().upper()
        if tok:
            out.add(tok)
    return out


# 性能预算：首屏 JS 体积（字节）与请求数上限。交互越堆越多，必须有人盯住体积，
# 否则「革命性交互」会变成「革命性卡顿」。默认 250KB / 20 个脚本请求。
SRC_SCRIPT_RE = re.compile(r'<script\b[^>]*\bsrc\s*=\s*"([^"]*)"', re.I)

# P-rev R35：按需加载脚本。这些文件由 _search-lazy.js 等桩在首次交互时才注入，
# 不属于首屏关键路径，S12 计算首屏字节时应跳过（否则会把「已从首屏移除」的
# 38KB 仍算进首屏，掩盖懒加载的真实收益）。约定：任何懒加载目标都登记在此。
LAZY_SCRIPTS = frozenset({"_search.js"})


# P-rev R113：能力契约金样。--capability-out=FILE 落盘，--verify-capability=FILE
# 对账——CI 把 FILE 当 golden，一旦审计器检查注册表漂移（增删改检查项）就失败，
# 把「能力演进」变成显式的快照更新动作，防止能力悄悄回退或意外新增。
def _capability_contract():
    """能力契约 = 引擎标识 + JSON schema 版本 + 检查注册表（R113/R120）。"""
    return {
        "engine": "fe_audit",
        "schema": SCHEMA_VERSION,
        "checks": [{"code": _c, "title": _t} for _c, _t in CHECK_REGISTRY],
    }


def _write_capability(path):
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(_capability_contract(), fh, ensure_ascii=False,
                  sort_keys=True, indent=1)


def _check_capability(path):
    """校验能力金样。返回 (ok, reason)；diff 会列出现缺项便于定位漂移来源。"""
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError) as e:
        return False, "无法读取金样：%s" % e
    if saved.get("engine") != "fe_audit":
        return False, "engine 不匹配：%r（金样可能来自别的工具）" % saved.get("engine")
    if saved.get("schema") != SCHEMA_VERSION:
        return False, "schema 漂移：金样 v%r vs 当前 v%d（JSON 顶层键布局可能已变，需 --capability-out 刷新金样）" % (
            saved.get("schema"), SCHEMA_VERSION)
    want = [(_c, _t) for _c, _t in CHECK_REGISTRY]
    got = [(_c.get("code"), _c.get("title")) for _c in saved.get("checks", [])]
    if got == want:
        return True, "一致（%d 项检查）" % len(want)
    lost = [(_c, _t) for (_c, _t) in want if (_c, _t) not in got]
    added = [(_c, _t) for (_c, _t) in got if (_c, _t) not in want]
    parts = []
    if added:
        parts.append("金样多出 %s" % added)
    if lost:
        parts.append("注册表新增 %s" % lost)
    return False, "；".join(parts)


# P-rev R122/R125：差异比较核心。R118 之后摘要已是确定性字节序，issues 全序稳定，
# 因此「两轮审计差异」只需比较 (file, check, msg) 三元组集合——新出现/消失即真差异。
def _load_summary_file(path):
    """读取一份 fe_audit 摘要 JSON。返回 (ok, data_or_err)。"""
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        return False, "无法读取摘要：%s" % e
    if not isinstance(data, dict) or "errors" not in data or "warns" not in data:
        return False, "%s 不是 fe_audit 摘要（缺 errors/warns 数组）" % path
    return True, data


def _issue_key_set(items):
    """把一份 issues 数组压成 (file, check, msg) 键集——确定性 diff 的基元。"""
    return set((i.get("file", ""), i.get("check", ""), i.get("msg", ""))
               for i in items)


def _diff_levels(cur_items, prev_items):
    """返回 (新增键列表, 消失键列表)，均按键排序、确定性强。"""
    cur = _issue_key_set(cur_items)
    prev = _issue_key_set(prev_items)
    return sorted(cur - prev), sorted(prev - cur)


def _emit_diff(stream, header, prev_ver, cur_ver, prev_errors, cur_errors,
               prev_warns, cur_warns):
    """把两轮 issues 差异块打印到指定流（R122 用 stdout；R125 用 stderr 以
    不污染 --json 的 stdout）。header 区分比较场景，便于日志定位。"""
    ae, le = _diff_levels(cur_errors, prev_errors)
    aw, lw = _diff_levels(cur_warns, prev_warns)
    print("=" * 60, file=stream)
    print("%s：%s → %s" % (header, prev_ver, cur_ver), file=stream)
    print("ERROR：%d → %d（新增 %d / 消失 %d）" % (
        len(prev_errors), len(cur_errors), len(ae), len(le)), file=stream)
    print("WARN ：%d → %d（新增 %d / 消失 %d）" % (
        len(prev_warns), len(cur_warns), len(aw), len(lw)), file=stream)
    for _label, _items in (("新增 ERROR", ae), ("消失 ERROR", le),
                           ("新增 WARN", aw), ("消失 WARN", lw)):
        if _items:
            print("%s：" % _label, file=stream)
            for _f, _c, _m in _items:
                print("  - %s | %s | %s" % (_f, _c, _m[:150]), file=stream)
    return len(ae)


# =============================================================================
# R127-R151：机器通道 / 阈值治理 / 豁免 / 自检 —— 引擎契约自证的纯函数基元。
# 全部为「不触碰目录、不调用外部工具」的确定性实现；默认不改变任何输出，
# 仅在对应显式开关出现时才介入审计主流程。
# =============================================================================

# R127：摘要顶层键注册表。摘要 dict 的键集合必须与它完全一致——引擎输出前逐键
# 核对，漂移按内部错误告警并把退出码拉到 >=1。新增/删除顶层键属于 breaking 变化，
# 必须同时改 SCHEMA_VERSION（自检执法，防「悄悄加键、下游解析器不知情」）。
SUMMARY_KEYS = frozenset({
    "blocking_warn_count", "by_check", "elapsed_ms", "engine",
    "engine_version", "error_count", "errors", "hard_gate", "mode",
    "page_stats", "pages", "rerun", "schema", "strict", "tags",
    "warn_count", "warn_ok", "warns",
})

# R131：issue 字段注册表——每条 issue 只允许出现这四个键。
ISSUE_KEYS = frozenset({"level", "check", "file", "msg"})

# R132：阈值配置注册表（单一事实源）。每项 = (说明, CLI 开关, 环境变量, 内置默认)。
# CLI > --config=FILE > 环境变量 > 内置默认 的四层取值都以此表为准。
THRESHOLD_META = {
    "js_budget": ("S12 外链 JS 预算（字节）", "--js-budget=",
                  "FE_AUDIT_JS_BUDGET", 150000),
    "inline_budget": ("S12 内联 JS 预算（字节）", "--inline-budget=",
                      "FE_AUDIT_INLINE_BUDGET", 40000),
    "req_budget": ("S12 脚本请求数预算", "--req-budget=",
                   "FE_AUDIT_REQ_BUDGET", 20),
    "growth_pct": ("趋势增长告警阈值（%，R61/R69）", "--growth-pct=",
                   None, 20),
    "s11_limit": ("S11 真实 DOM 抽样条数（0=全量）", "--s11-limit=",
                  None, 12),
    "s11_timeout": ("S11 真实 DOM 检查超时（秒；0=不限）", "--s11-timeout=",
                    None, 120),
    "samples": ("文本样例条数（0=只计数）", "--samples=", None, 4),
    "elapsed_budget_ms": ("审计器耗时预算（ms；负值=关闭）", "--elapsed-budget=",
                          None, None),
}

# R(收尾)：已知自包含单文件产物——按设计必须内联全部资源，豁免 S12 绝对性能预算。
_S12_SELF_CONTAINED_DEFAULT = ("report.html", "gs.html")

# R137：豁免文件命名与行数上限（防误写巨型规则文件拖慢启动）。
IGNORE_FILE_NAME = ".fe_auditignore"
IGNORE_LINE_MAX = 500


def _parse_tags(args):
    """R130：解析可重复的 --tag=键=值（键限字母数字._-）。返回 (tags, bad)。"""
    tags = {}
    bad = []
    for _a in args:
        if _a.startswith("--tag="):
            _raw = _a[len("--tag="):]
            if "=" not in _raw:
                bad.append(_raw)
                continue
            _k, _v = _raw.split("=", 1)
            if not _k or not all(_c.isalnum() or _c in "_.-" for _c in _k):
                bad.append(_raw)
                continue
            tags[_k] = _v
    return tags, bad


def _summary_line(summary, rc):
    """R127：单行 TSV 摘要——CI 面板/监控一行吞下全部关键量（等宽、确定性）。"""
    _ps = summary.get("page_stats") or {}
    return "\t".join(str(_) for _ in [
        "fe_audit", summary.get("engine_version", "?"),
        summary.get("schema", "?"), summary.get("mode", "?"), rc,
        summary.get("pages", 0), _ps.get("with_error", 0),
        _ps.get("with_warn", 0), summary.get("error_count", 0),
        summary.get("warn_count", 0), summary.get("blocking_warn_count", 0),
        summary.get("elapsed_ms", 0)])


def _issue_export(summary):
    """R128：issues 明细独立档（errors 在前、warns 在后，沿用确定性全序）。"""
    return {
        "engine": "fe_audit",
        "engine_version": summary.get("engine_version"),
        "schema": summary.get("schema"),
        "issue_keys": sorted(ISSUE_KEYS),
        "error_count": len(summary.get("errors", [])),
        "warn_count": len(summary.get("warns", [])),
        "issues": (list(summary.get("errors", []))
                   + list(summary.get("warns", []))),
    }


def _page_issue_rows(pages, errors, warns):
    """(file, ERROR 数, WARN 数) 列表，ERROR/WARN 降序、file 字典序——
    Top 页面榜与页面导出共用同一排序。"""
    _em, _wm = {}, {}
    for _it in errors:
        _em[_it.get("file", "")] = _em.get(_it.get("file", ""), 0) + 1
    for _it in warns:
        _wm[_it.get("file", "")] = _wm.get(_it.get("file", ""), 0) + 1
    _rows = [(_p, _em.get(_p, 0), _wm.get(_p, 0)) for _p in pages]
    _rows.sort(key=lambda _r: (-_r[1], -_r[2], _r[0]))
    return _rows


def _pages_export(pages, errors, warns):
    """R128：页面级明细档——每页 errors/warns 分开列，页面全量入档。"""
    _by = {}
    for _p in pages:
        _by[_p] = {"file": _p, "errors": [], "warns": []}
    for _it in errors:
        _b = _by.get(_it.get("file", ""))
        if _b is not None:
            _b["errors"].append({"check": _it.get("check", ""),
                                 "msg": _it.get("msg", "")})
    for _it in warns:
        _b = _by.get(_it.get("file", ""))
        if _b is not None:
            _b["warns"].append({"check": _it.get("check", ""),
                                "msg": _it.get("msg", "")})
    _page_list = [_by[_p] for _p in pages]
    return {
        "engine": "fe_audit", "engine_version": ENGINE_VERSION,
        "schema": SCHEMA_VERSION,
        "page_stats": {"audited": len(pages),
                       "with_error": sum(1 for _p in _page_list if _p["errors"]),
                       "with_warn": sum(1 for _p in _page_list if _p["warns"])},
        "pages": _page_list,
    }


_PAGE_JS_CACHE = {}


def _measure_page_js(page):
    """R135：单页首屏 JS 度量——S12 与 --budget-table 共用同一实现，防两处漂移。
    返回 (内联字节, 外链字节, 请求数)；读取失败返回 None。
    R(收尾)10：按 (路径, mtime, size) 缓存结果，避免同页在 S12 与 --budget-table
    间重复读盘/正则，规模站点可显著降开销。"""
    _key = os.path.abspath(page)
    try:
        _st = os.stat(page)
        _ck = (_key, _st.st_mtime, _st.st_size)
    except OSError:
        _ck = (_key, None, None)
    if _ck in _PAGE_JS_CACHE:
        return _PAGE_JS_CACHE[_ck]
    try:
        _html = io.open(page, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        _PAGE_JS_CACHE[_ck] = None
        return None
    _base = os.path.dirname(page)
    _inline, _ext, _reqs = 0, 0, 0
    for _body in INLINE_SCRIPT_RE.findall(_html):
        if _body.strip():
            _inline += len(_body.encode("utf-8"))
            _reqs += 1
    _seen = set()
    for _src in SRC_SCRIPT_RE.findall(_html):
        if _src.startswith(("http://", "https://", "//")):
            continue
        _target = os.path.normpath(os.path.join(_base, _src.split("#", 1)[0].split("?", 1)[0]))
        # P-rev R35：懒加载脚本不属于首屏，跳过（不计数、不计体积）
        if os.path.basename(_target) in LAZY_SCRIPTS:
            continue
        _k2 = os.path.normcase(_target)
        if os.path.exists(_target) and _k2 not in _seen:
            _seen.add(_k2)
            try:
                _ext += os.path.getsize(_target)
            except OSError:
                pass
        _reqs += 1
    _res = (_inline, _ext, _reqs)
    _PAGE_JS_CACHE[_ck] = _res
    return _res


def _load_config_file(path):
    """R133：读取阈值配置 JSON。返回 (cfg, err)——err 非空则配置不可用。
    键必须已登记于 THRESHOLD_META；未知键/类型非法只告警并忽略该项，
    不让一份小错配置拖垮整次审计。"""
    if not os.path.exists(path):
        return {}, "文件不存在：%s" % path
    try:
        with io.open(path, "r", encoding="utf-8") as fh:
            _data = json.load(fh)
    except (OSError, ValueError) as e:
        return {}, "解析失败：%s" % e
    if not isinstance(_data, dict):
        return {}, "顶层必须是 JSON 对象"
    _cfg = {}
    for _k, _v in _data.items():
        if _k not in THRESHOLD_META:
            print("配置键未登记：%s（忽略；合法键见 --config-print）" % _k,
                  file=sys.stderr)
            continue
        if _v is None:
            continue
        if not isinstance(_v, int) or isinstance(_v, bool):
            print("配置键 %s 需为整数，实际 %r（忽略）" % (_k, _v),
                  file=sys.stderr)
            continue
        if _v < 0 and _k != "elapsed_budget_ms":
            print("配置键 %s 不允许负值（忽略）" % _k, file=sys.stderr)
            continue
        _cfg[_k] = _v
    return _cfg, ""


def _resolve_metric(args, cfg, key):
    """R134：阈值四层取值：CLI > --config=FILE > 环境变量 > 内置默认。"""
    _meta = THRESHOLD_META[key]
    _v = _opt_int(args, _meta[1], None)
    if _v is not None:
        return _v
    if cfg is not None and key in cfg:
        return cfg[key]
    if _meta[2]:
        _raw = os.environ.get(_meta[2])
        if _raw is not None:
            try:
                return int(_raw)
            except (ValueError, TypeError):
                pass  # 环境变量非法时静默回退默认（不因脏 env 崩审计）
    return _meta[3]


def _resolve_self_contained(cfg):
    """R(收尾)：解析 S12 自包含单文件页白名单（basename 集合）。
    默认豁免 report.html / gs.html；可用 --config 的 s12_self_contained
    （列表）或环境变量 FE_AUDIT_S12_SELF_CONTAINED（逗号分隔）覆盖。
    环境变量键「存在即视为覆盖」：设为空串表示显式取消豁免（空集合）。"""
    if cfg is not None and "s12_self_contained" in cfg:
        raw = cfg["s12_self_contained"]
    elif "FE_AUDIT_S12_SELF_CONTAINED" in os.environ:
        raw = os.environ["FE_AUDIT_S12_SELF_CONTAINED"].split(",")
    else:
        raw = None
    if raw:
        return set(os.path.basename(str(x).strip())
                   for x in raw if x and str(x).strip())
    return set(_S12_SELF_CONTAINED_DEFAULT)


def _load_ignore_file(path):
    """R137：读取豁免文件。语法：每行 `CODE|文件子串|msg子串`，三段均可留空
    = 通配；# 开头为注释；空行忽略。返回 (ok, rules, err)。不存在视作空规则。"""
    if not os.path.exists(path):
        return True, [], ""
    try:
        _lines = io.open(path, "r", encoding="utf-8",
                         errors="replace").read().splitlines()
    except OSError as e:
        return False, [], str(e)
    if len(_lines) > IGNORE_LINE_MAX:
        print("豁免文件超过 %d 行上限，多余行忽略" % IGNORE_LINE_MAX,
              file=sys.stderr)
        _lines = _lines[:IGNORE_LINE_MAX]
    _rules = []
    for _ln in _lines:
        _ln = _ln.strip()
        if not _ln or _ln.startswith("#"):
            continue
        if _ln.count("|") < 2:
            _code = _ln.upper()
            _rules.append((_code, "", ""))  # 兼容单段 `CODE`（整类豁免）
            continue
        _code, _fr, _mr = [_p.strip() for _p in _ln.split("|", 2)]
        _rules.append((_code.upper(), _fr, _mr))
    return True, _rules, ""


def _ignored_by(issue, rules):
    """R138：一条 issue 是否被任一豁免规则命中（三段各自子串匹配，空=通配）。"""
    _f = issue.get("file", "") or ""
    _c = issue.get("check", "") or ""
    _m = issue.get("msg", "") or ""
    for _code, _fr, _mr in rules:
        if _code and _c != _code:
            continue
        if _fr and _fr not in _f:
            continue
        if _mr and _mr not in _m:
            continue
        return True
    return False


def _delta_payload(prev_d, cur_d):
    """R147：--delta-out 结构化差异档——新增/消失清单机器可消费。"""
    _ae, _le = _diff_levels(cur_d.get("errors", []), prev_d.get("errors", []))
    _aw, _lw = _diff_levels(cur_d.get("warns", []), prev_d.get("warns", []))

    def _fmt(keys):
        return [{"file": _f, "check": _c, "msg": _m} for _f, _c, _m in keys]

    return {
        "engine": "fe_audit", "engine_version": ENGINE_VERSION,
        "schema": SCHEMA_VERSION,
        "prev_engine_version": prev_d.get("engine_version", "?"),
        "cur_engine_version": cur_d.get("engine_version", "?"),
        "added_error_count": len(_ae), "lost_error_count": len(_le),
        "added_warn_count": len(_aw), "lost_warn_count": len(_lw),
        "added_errors": _fmt(_ae), "lost_errors": _fmt(_le),
        "added_warns": _fmt(_aw), "lost_warns": _fmt(_lw),
    }


def _schema_manifest():
    """R149：--schema-json —— 顶层键/issue 键清单自描述，下游零硬编码接入。"""
    return {
        "engine": "fe_audit", "engine_version": ENGINE_VERSION,
        "schema": SCHEMA_VERSION,
        "summary_keys": sorted(SUMMARY_KEYS),
        "issue_keys": sorted(ISSUE_KEYS),
    }


def _selftest_checks():
    """R142：纯引擎自检清单（不触碰目录、不调外部工具）。返回 [(name, ok, why)]。"""
    import re as _re
    _codes = [c for c, _t in CHECK_REGISTRY]
    _missing_notes = sorted(set(_codes) - set(CHECK_NOTES))
    _extra_notes = sorted(set(CHECK_NOTES) - set(_codes))
    _core = {"engine", "schema", "engine_version", "error_count",
             "warn_count", "errors", "warns"}
    _meta_bad = [k for k, v in THRESHOLD_META.items()
                 if len(v) != 4 or not str(v[1]).startswith("--")]
    _ae, _le = _diff_levels([], [])
    _items = [
        ("registry_unique", len(_codes) == len(set(_codes)),
         "%d 项代码注册" % len(_codes)),
        ("notes_coverage", not _missing_notes,
         ("漏注释 %s" % _missing_notes) if _missing_notes else "CHECK_NOTES 全覆盖"),
        ("notes_no_extra", not _extra_notes,
         ("多余注释 %s" % _extra_notes) if _extra_notes else "无越界注释"),
        ("summary_core_keys", _core.issubset(SUMMARY_KEYS),
         "%d 个核心键齐备" % len(_core)),
        ("issue_key_set", ISSUE_KEYS == frozenset({"level", "check", "file", "msg"}),
         "issue 四键固定"),
        ("threshold_meta", not _meta_bad,
         ("异常 %s" % _meta_bad) if _meta_bad else "%d 项阈值注册" % len(THRESHOLD_META)),
        ("version_ok",
         bool(_re.match(r"^\d+\.\d+\.\d+$", ENGINE_VERSION))
         and isinstance(SCHEMA_VERSION, int) and SCHEMA_VERSION > 0,
         "%s（schema %d）" % (ENGINE_VERSION, SCHEMA_VERSION)),
        ("diff_identity", not _ae and not _le, "空集差异恒为零"),
    ]
    return _items


def _selftest_report_json():
    """R144：--selftest-json 机器可读自检报告。"""
    _items = _selftest_checks()
    return {
        "engine": "fe_audit", "engine_version": ENGINE_VERSION,
        "schema": SCHEMA_VERSION,
        "ok": all(_ok for _n, _ok, _w in _items),
        "checks": [{"name": _n, "ok": _ok, "why": _w}
                   for _n, _ok, _w in _items],
    }


def _write_json_file(path, obj):
    """确定性 JSON 落盘（sort_keys + ensure_ascii=False + indent=2）。"""
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, sort_keys=True, indent=2)


def _trend_series_json(audit_root, since=None):
    """R150：把 _fe_perf_trend.csv 导出为按页面归组的确定性 JSON（--since 过滤）。"""
    import csv
    _path = os.path.join(audit_root, "_fe_perf_trend.csv")
    if not os.path.exists(_path):
        return {"engine": "fe_audit", "present": False, "pages": {}}
    _pages = {}
    try:
        with io.open(_path, "r", encoding="utf-8") as fh:
            for _row in csv.DictReader(fh):
                _ts = (_row.get("timestamp") or "").strip()
                if since and _ts < since:
                    continue
                _pg = (_row.get("page") or "").strip()
                if not _pg:
                    continue
                try:
                    _inl = int(_row.get("inline_js", 0) or 0)
                except (ValueError, TypeError):
                    _inl = 0
                try:
                    _ext = int(_row.get("ext_js", 0) or 0)
                except (ValueError, TypeError):
                    _ext = 0
                _pages.setdefault(_pg, []).append(
                    {"timestamp": _ts, "inline_js": _inl, "ext_js": _ext})
    except (OSError, csv.Error):
        return {"engine": "fe_audit", "present": False,
                "error": "趋势文件读取失败", "pages": {}}
    for _pg in _pages:
        _pages[_pg] = sorted(_pages[_pg], key=lambda _r: _r["timestamp"])
    return {"engine": "fe_audit", "present": True,
            "page_count": len(_pages), "since": since,
            "pages": {_pg: _pages[_pg] for _pg in sorted(_pages)}}


def check_perf_budget(outdir, pages, js_budget=None, req_budget=None,
                      inline_budget=None, self_contained=None, trend_dir=None):
    """S12：首屏性能预算 —— 区分「重复内联」与「可缓存外链」的 JS 字节。

    这是 R27 之后的关键修正：原先把内联与外链字节混在一起算，导致把大模块
    外链化（63KB × 12 页 的重复 → 1 份可缓存文件）之后，指标**纹丝不动**，
    无法体现真实收益。两者性质完全不同：

      · 内联（inline）：每个页面各带一份，N 个页面就是 N 份重复下载，且无法
        被浏览器单独缓存 —— 这是真正的「浪费」，应重点盯防；
      · 外链（external）：同一份文件全站共用一个 URL，首屏之后全部命中缓存。

    因此预算分两档：内联默认 40KB（重复成本高，卡紧），外链默认 150KB。
    """
    if js_budget is None:
        # 外链：可缓存，第一次访问后基本免费，预算较宽松
        js_budget = int(os.environ.get("FE_AUDIT_JS_BUDGET", "150000"))
    if inline_budget is None:
        # 内联：每页重复，是主要浪费源，卡紧以倒逼外链化
        inline_budget = int(os.environ.get("FE_AUDIT_INLINE_BUDGET", "40000"))
    if req_budget is None:
        req_budget = int(os.environ.get("FE_AUDIT_REQ_BUDGET", "20"))
    issues = []
    for page in pages:
        # 自包含单文件页（report.html / gs.html 等）按设计必须内联全部资源，
        # 故豁免 S12 绝对预算——否则 --enforce-budget 硬门禁对这类站点恒失败。
        # 其体积异常爬升仍由 check_perf_growth（R61）独立盯防。
        if self_contained and os.path.basename(page) in self_contained:
            continue
        # R135：体积/请求数度量统一走 _measure_page_js，与 --budget-table 同源。
        _m = _measure_page_js(page)
        if _m is None:
            continue
        inline_js, ext_js, reqs = _m
        if inline_js > inline_budget:
            issues.append({"level": "WARN", "check": "S12", "file": page,
                           "msg": "内联 JS %dKB 超过预算 %dKB（每页重复携带且无法缓存，建议外链成共享文件）"
                           % (inline_js // 1024, inline_budget // 1024)})
        if ext_js > js_budget:
            issues.append({"level": "WARN", "check": "S12", "file": page,
                           "msg": "外链 JS %dKB 超过预算 %dKB（可缓存，但首屏仍需下载）"
                           % (ext_js // 1024, js_budget // 1024)})
        if reqs > req_budget:
            issues.append({"level": "WARN", "check": "S12", "file": page,
                           "msg": "脚本请求数 %d 超过预算 %d（建议合并/按需加载）" % (reqs, req_budget)})
        # P-rev R56：记录本页首屏体积到趋势文件，供持续追踪「是否随迭代缓慢爬升」
        _record_trend(page, inline_js, ext_js, trend_dir=trend_dir, audit_dir=outdir)
    return issues


# P-rev R56：性能趋势记录。把每页「内联 JS / 外链 JS」体积按次追加到
# outdir/_fe_perf_trend.csv（时间戳、页面、两档体积）。单次审计只看是否超阈值，
# 趋势文件则能暴露「体积随迭代缓慢爬升」这类阈值永远抓不到的退化。
_TREND_HEADER = "timestamp,page,inline_js,ext_js\n"


def _record_trend(page, inline_js, ext_js, trend_dir=None, audit_dir=None):
    try:
        import datetime
        # 趋势 csv 写到「站点根」——即审计输出根（audit_dir），使所有页面（含 src/、
        # dirs/、src/dup/ 等嵌套子目录）的体积都汇总进同一份 csv，供 check_perf_growth /
        # build_trend_panel 统一读取。旧逻辑按页面所在目录推算 site_root，会把 csv 散落
        # 在多个子目录，且增长统计只覆盖局部（R(收尾)修正）。
        # --trend-dir 可把 csv 落到持久目录（如 CI 提交的基线目录），使跨运行增长可被抓到。
        if trend_dir:
            site_root = trend_dir
        elif audit_dir:
            site_root = audit_dir
        else:
            page_dir = os.path.dirname(page)
            site_root = os.path.dirname(page_dir) if os.path.basename(page_dir) == "src" else page_dir
        try:
            os.makedirs(site_root, exist_ok=True)
        except OSError:
            pass
        trend_path = os.path.join(site_root, "_fe_perf_trend.csv")
        stamp = datetime.datetime.now().replace(microsecond=0).isoformat()
        rel = os.path.relpath(page, site_root).replace("\\", "/")
        # P-rev R62：同一「时间窗口」内同一页面只保留最新一条，避免同一次审计
        # 因多次运行（如 --skip-generate 后再次审计）重复追加，稀释增长统计。
        # 这里用「同一天」作为窗口：同一天内重复审计视为同一次快照，覆盖旧值。
        day = stamp[:10]
        rows = []
        if os.path.exists(trend_path):
            with io.open(trend_path, "r", encoding="utf-8") as fh:
                rows = fh.read().splitlines()
        header = rows[0] if rows and rows[0].startswith("timestamp") else _TREND_HEADER.rstrip("\n")
        body = []
        replaced = False
        for r in rows[1:]:
            parts = r.split(",")
            if len(parts) >= 4 and parts[1] == rel and parts[0][:10] == day:
                if not replaced:
                    body.append("%s,%s,%d,%d" % (stamp, rel, inline_js, ext_js))
                    replaced = True
                # 同一天同页面的旧记录丢弃（覆盖）
            else:
                body.append(r)
        if not replaced:
            body.append("%s,%s,%d,%d" % (stamp, rel, inline_js, ext_js))
        with io.open(trend_path, "w", encoding="utf-8") as fh:
            fh.write(header + "\n" + "\n".join(body) + "\n")
    except OSError:
        pass  # 趋势记录失败不应影响审计本身


# P-rev R61/R69：趋势增长告警。读取站点根的 _fe_perf_trend.csv，对每个页面比较
# 「首次记录 vs 最近记录」与「上次 vs 最近（环比）」两种增长，任一超过阈值即 WARN。
# 首末增长抓「随迭代缓慢爬升」，环比抓「最近一次提交突然变大」；阈值可经
# --growth-pct=N 配置（默认 20%）。趋势按天去重（R62），故文件行序即时间序。
def check_perf_growth(audit_root, growth_pct=20, trend_dir=None):
    import csv
    trend_path = os.path.join(trend_dir, "_fe_perf_trend.csv") if trend_dir \
        else os.path.join(audit_root, "_fe_perf_trend.csv")
    if not os.path.exists(trend_path):
        return []  # 首次运行尚无趋势数据，跳过
    series = {}   # page -> [inline_js, ...]（按审计时间先后）
    try:
        with io.open(trend_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                page = row.get("page", "")
                try:
                    inline = int(row.get("inline_js", 0))
                except (ValueError, TypeError):
                    inline = 0
                series.setdefault(page, []).append(inline)
    except (OSError, csv.Error):
        return []
    issues = []
    for page, vals in series.items():
        if len(vals) < 2 or vals[0] <= 0:
            continue  # 仅一条记录无法比较；首次为 0 无从算增长
        first, last = vals[0], vals[-1]
        overall = (last - first) / float(first) * 100.0
        if overall > growth_pct:
            issues.append({"level": "WARN", "check": "S12", "file": page,
                           "msg": "内联 JS 较首次记录增长 %.0f%%（%d→%d 字节，共 %d 次记录），"
                                  "疑似交互模块随迭代变重，建议外链化"
                                  % (overall, first, last, len(vals))})
            continue
        # P-rev R69：环比——最近两次记录间单步跳升 > 阈值，首末看不出但最近一次
        # 提交已把页面变大（如本次迭代塞入大段内联 JS）。
        prev = vals[-2]
        if prev > 0:
            spike = (last - prev) / float(prev) * 100.0
            if spike > growth_pct:
                issues.append({"level": "WARN", "check": "S12", "file": page,
                               "msg": "内联 JS 最近一次环比跳升 %.0f%%（%d→%d 字节），"
                                      "疑似本次新增模块过重，建议拆分外链"
                                      % (spike, prev, last)})
    return issues


# P-rev R63：内联 SVG 折线图。画「内联体积最大」的前 8 页的随记录序号变化的曲线，
# 让「爬升斜率」一眼可见。横轴=记录序号（时间推进），纵轴=内联 JS 字节。
def _trend_svg(series, top_n=8, width=920, height=240):
    if not series:
        return ""
    # 取内联体积最大（最近值）的前 top_n 页
    ranked = sorted(series.items(), key=lambda kv: kv[1][-1][1], reverse=True)[:top_n]
    all_inl = [p[1] for _, pts in series.items() for p in pts]
    max_inl = max(all_inl) if all_inl else 1
    max_n = max(len(pts) for pts in series.values()) if series else 1
    pad_l, pad_r, pad_t, pad_b = 48, 12, 12, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    palette = ["#d73a49", "#005cc5", "#1a7f37", "#8250df", "#9a6700",
               "#0086b3", "#b35900", "#6f42c1"]
    lines = []
    legend = []
    for i, (page, pts) in enumerate(ranked):
        color = palette[i % len(palette)]
        coords = []
        for j, (ts, inline, ext) in enumerate(pts):
            x = pad_l + (plot_w * j / float(max(max_n - 1, 1)))
            y = pad_t + plot_h * (1.0 - inline / float(max_inl))
            coords.append("%.1f,%.1f" % (x, y))
        if len(coords) == 1:
            coords.append(coords[0])
        lines.append('<polyline fill="none" stroke="%s" stroke-width="2" '
                     'points="%s"/>' % (color, " ".join(coords)))
        legend.append('<span style="color:%s">■ %s</span>' % (color, page.split("/")[-1]))
    # 网格线
    grid = ""
    for g in range(5):
        gy = pad_t + plot_h * g / 4.0
        grid += ('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" '
                 'stroke="#eaecef" stroke-width="1"/>'
                 % (pad_l, gy, width - pad_r, gy))
    y_axis = ""
    for g in range(5):
        gy = pad_t + plot_h * g / 4.0
        val = int(max_inl * (1.0 - g / 4.0)) // 1024
        y_axis += ('<text x="%d" y="%.1f" font-size="10" fill="#57606a" '
                   'text-anchor="end">%dK</text>' % (pad_l - 4, gy + 3, val))
    svg = ('<svg width="%d" height="%d" viewBox="0 0 %d %d" '
           'xmlns="http://www.w3.org/2000/svg">'
           '<rect width="100%%" height="100%%" fill="#fafbfc"/>'
           '%s%s%s'
           '<text x="%d" y="%d" font-size="10" fill="#57606a" text-anchor="middle">'
           '记录序号（时间推进 →）</text>'
           '</svg>'
           % (width, height, width, height, grid, y_axis, "".join(lines),
              pad_l + plot_w / 2, height - 6))
    legend_html = ('<div style="font-size:12px;display:flex;flex-wrap:wrap;gap:10px;">%s</div>'
                   % "".join(legend))
    return svg + legend_html


def _fmt_kb(n, signed=False):
    """P-rev R74：把内联 JS 字节数格式化为 KB 字符串（1 KB = 1024 B），
    signed=True 时带 +/- 前缀（用于"变化"列）。趋势面板表格统一用它，
    从源头杜绝"表头写 KB、单元格塞字节数"的单位错位。
    """
    kb = n / 1024.0
    return ("%+.1f" % kb) if signed else ("%.1f" % kb)


# P-rev R72：S4 增强——跨页锚点死锚检测。S2 只保证 href 目标文件存在；
# 基础 S4 只查同页 "#frag"。补上「文件在、锚点没了」的第三种断链：
# a.html#x 指向的 b.html 仍存在但已无 id="x"，深链跳转照样静默落空。
# 目标页没有任何可静态解析的锚点（锚点纯 JS 生成）时跳过，避免误报。
def check_cross_page_anchors(pages):
    issues = []
    id_cache = {}   # target 绝对路径 -> 锚点集合；None=不可判定
    skip_prefix = ("#", "http://", "https://", "//", "mailto:",
                   "javascript:", "data:")
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8",
                          errors="replace").read()
        except OSError:
            continue
        markup = DYN_STRIP_RE.sub(" ", raw)
        base = os.path.dirname(page)
        for href in HREF_RE.findall(markup):
            h = href.strip()
            if not h or h.startswith(skip_prefix) or "#" not in h:
                continue
            path_part, frag = h.split("#", 1)
            if not path_part or not frag:
                continue
            path_part = path_part.split("?", 1)[0]
            if not path_part or path_part.startswith(skip_prefix):
                continue
            target = os.path.normpath(os.path.join(base, path_part))
            if (not target.lower().endswith(".html")) or not os.path.exists(target):
                continue  # 非 HTML 无锚点概念；文件缺失已由 S2 报
            if target not in id_cache:
                id_cache[target] = None
                try:
                    t_raw = io.open(target, "r", encoding="utf-8",
                                    errors="replace").read()
                except OSError:
                    continue
                t_markup = DYN_STRIP_RE.sub(" ", t_raw)
                ids = (set(ID_ATTR_RE.findall(t_markup))
                       | set(NAME_ATTR_RE.findall(t_markup)))
                if ids:   # 无任何静态锚点 → 不可判定，放过
                    id_cache[target] = ids
            ids = id_cache[target]
            if ids is not None and frag not in ids:
                issues.append({"level": "ERROR", "check": "S4", "file": page,
                               "msg": "跨页死锚：%s#%s（目标页存在但无该锚点）"
                                      % (os.path.basename(target), frag)})
    return issues


# P-rev R76：S13 重复 id 守卫。id 是 JS getElementById、#L 行深链、跨页锚点的
# 寻址键；页面里 id 重复时浏览器只认第一个，其余元素"存在但永远不可达"，
# 且行为依赖文档顺序、日常浏览根本看不出来——只能在生成/审计期用静态扫挡下。
def check_duplicate_ids(pages):
    issues = []
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8",
                          errors="replace").read()
        except OSError:
            continue
        seen = {}
        for mid in ID_ATTR_RE.findall(DYN_STRIP_RE.sub(" ", raw)):
            seen[mid] = seen.get(mid, 0) + 1
        dups = sorted(k for k, c in seen.items() if c > 1)
        if not dups:
            continue
        shown = ", ".join("%s(×%d)" % (k, seen[k]) for k in dups[:6])
        if len(dups) > 6:
            shown += " 等 %d 个" % len(dups)
        issues.append({"level": "ERROR", "check": "S13", "file": page,
                       "msg": "重复 id（深链/JS 只取首个，余者不可达）：" + shown})
    return issues


# P-rev R77：S14 HTML 结构配对 + 地标嵌套检查。R76 的 S13 只抓「id 唯一」；
# 若页面里两个 <main> 用了不同 id，S9/S13 都不会报——而浏览器对未闭合容器、
# <main> 嵌套 <main> 这类结构错误是「静默自我修复」的：标签配对时把后续整块
# 内容吞进错误的父容器，深链 / 折叠 / 布局随之错位，却毫无异常提示。这类缺陷
# 日常肉眼看不见，只能靠生成期结构校验挡下。
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_HTML_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>", re.I)
# script/style/textarea 为「原文区」：内部可能含 "<div>" 等字符串字面量，先整体挖空
_HTML_RAWTEXT_RE = re.compile(r"<(script|style|textarea)\b[^>]*>.*?</\1\s*>",
                              re.S | re.I)
_HTML_TAGSTART_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9:_-]*")
_HTML_VOID_TAGS = set("area base br col embed hr img input link meta "
                      "param source track wbr".split())
# 可省略闭合标签：显式闭合缺失可被浏览器容忍，不判结构错误
_HTML_OPTIONAL_END = set("li dt dd p td th tr option thead tbody tfoot "
                         "colgroup".split())
# 只对结构关键容器做严格配对（span/code 之类细粒度标签不计，避免噪音）
_HTML_TRACKED = set(
    "html head body div section article aside main header footer nav "
    "table thead tbody tfoot tr td th ul ol li dl dt dd details summary "
    "form figure figcaption blockquote pre h1 h2 h3 h4 h5 h6 fieldset "
    "legend select svg g".split())
_HTML_LANDMARKS = set("main header footer nav".split())


def check_html_structure(pages):
    """S14：轻量 tag-stack 结构校验（py3.6 无外部依赖）。

    每页先挖空原文区与注释，再对剩余标记做引号感知的标签配对；只对结构关键
    容器严格配对，并守护地标语义——<main> 至多一个、地标不得自嵌套。
    """
    issues = []
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8",
                          errors="replace").read()
        except OSError:
            continue
        # R(收尾)4：挖空原文区/注释时保留换行，使行号能对应原始文件
        # （旧实现用 raw.count('\n') 但 pos 取自 markup，两者长度不同 → 行号失真）。
        def _blank(m):
            return re.sub(r"[^\n]", " ", m.group(0))

        markup = _HTML_DOCTYPE_RE.sub(
            "", _HTML_COMMENT_RE.sub(_blank, _HTML_RAWTEXT_RE.sub(_blank, raw)))
        stack = []          # [(name, line)]
        main_count = 0
        probs = []

        def _line_of(pos):
            return markup.count("\n", 0, pos) + 1

        i, n = 0, len(markup)
        while i < n:
            m = _HTML_TAGSTART_RE.search(markup, i)
            if not m:
                break
            tag = m.group(0)
            is_close = tag.startswith("</")
            name = tag[2:].strip().lower() if is_close else tag[1:].strip().lower()
            if not name:
                i = m.end()
                continue
            # 引号感知地找本标签收尾 '>'（属性值里可能含 '>'）
            j = m.end()
            in_q = None
            while j < n:
                c = markup[j]
                if in_q:
                    if c == in_q:
                        in_q = None
                elif c in "\"'":
                    in_q = c
                elif c == ">":
                    break
                j += 1
            tail = markup[m.start():j + 1]
            self_close = tail.rstrip().endswith("/>")
            pos = m.start()
            if is_close:
                if name in _HTML_VOID_TAGS:
                    i = j + 1
                    continue
                idx = None
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k][0] == name:
                        idx = k
                        break
                if idx is None:
                    if name in _HTML_TRACKED:
                        probs.append((_line_of(pos),
                                      "多余闭合 </%s>（栈中无对应 <%s>）"
                                      % (name, name)))
                else:
                    for k in range(len(stack) - 1, idx, -1):
                        oname, oline = stack[k]
                        if oname not in _HTML_OPTIONAL_END:
                            probs.append((oline,
                                          "<%s> 在 </%s> 前未闭合（被隐式吞并）"
                                          % (oname, name)))
                    del stack[idx:]
            else:
                if name in _HTML_VOID_TAGS or self_close:
                    i = j + 1
                    continue
                if name == "main":
                    main_count += 1
                    if main_count > 1:
                        probs.append((_line_of(pos),
                                      "同一文档出现多个 <main>（语义要求至多一个）"))
                if name in _HTML_LANDMARKS and any(s[0] == name for s in stack):
                    probs.append((_line_of(pos),
                                  "<%s> 自嵌套（<%s> 内再开 <%s>）"
                                  % (name, name, name)))
                if name in _HTML_TRACKED:
                    stack.append((name, _line_of(pos)))
            i = j + 1
        for oname, oline in stack:
            if oname not in _HTML_OPTIONAL_END:
                probs.append((oline, "<%s> 未闭合（文档结束仍在栈中）" % oname))
        seen = set()
        uniq = []
        for ln, msg in probs:
            key = (ln, msg)
            if key not in seen:
                seen.add(key)
                uniq.append(key)
        uniq.sort()
        if uniq:
            top = "; ".join("L%d: %s" % (ln, msg) for ln, msg in uniq[:3])
            if len(uniq) > 3:
                top += " 等 %d 处" % len(uniq)
            issues.append({"level": "ERROR", "check": "S14", "file": page,
                           "msg": "结构配对/地标异常：" + top})
    return issues


# 5轮收尾改进 R1：S17 一级标题语义——每页须有且仅有一个非空 <h1>。
# S14 只做标签配对（保证 </h1> 不缺），不回答「页面主题标题是否缺失/重复」；
# 阅读器以 h1 作为页面级主题，缺失时只能把 h2/h3 强行提升，会破坏站点大纲。
def check_img_dims(pages):
    """S18：图片尺寸声明——<img> 缺 width/height 会引起布局抖动（CLS）。"""
    issues = []
    img_re = re.compile(r"<img\b[^>]*>", re.I)
    # 仅识别数值尺寸（忽略 %/auto，因无法据此预估高度）；script/style 内文本先剔除
    dim_re = re.compile(r"(?:width|height)\s*=\s*[\"']?\s*\d+", re.I)
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        markup = _HTML_RAWTEXT_RE.sub("", raw)
        for m in img_re.findall(markup):
            if dim_re.search(m):
                continue
            issues.append({"level": "WARN", "check": "S18", "file": page,
                           "msg": "图片缺少 width/height 尺寸声明（易引发布局抖动 CLS）："
                                  + m[:80]})
    return issues


def check_duplicate_titles(pages):
    """S19：重复 <title>——同一站点多个页面使用完全相同的标题损害 SEO/可寻址性。"""
    issues = []
    title_re = re.compile(r"<title\b[^>]*>(.*?)</title>", re.S | re.I)
    seen = {}
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        markup = _HTML_RAWTEXT_RE.sub("", raw)
        m = title_re.search(markup)
        if not m:
            continue
        title = m.group(1).strip()
        if not title:
            continue
        seen.setdefault(title, []).append(page)
    for title, locs in seen.items():
        if len(locs) > 1:
            issues.append({"level": "WARN", "check": "S19",
                           "file": "; ".join(os.path.basename(x) for x in locs),
                           "msg": "重复 <title>（共 %d 页）：%s" % (len(locs), title[:80])})
    return issues


def check_h1_hierarchy(pages):
    """S17：一级标题语义——每个页面须有且仅有一个非空 <h1>。"""
    issues = []
    h1_re = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.S | re.I)
    strip_re = re.compile(r"<[^>]+>")
    for page in pages:
        try:
            raw = io.open(page, "r", encoding="utf-8",
                          errors="replace").read()
        except OSError:
            continue
        matches = h1_re.findall(raw)
        if not matches:
            issues.append({"level": "ERROR", "check": "S17", "file": page,
                           "msg": "页面没有 <h1>（缺少页面级主题标题）"})
            continue
        if len(matches) > 1:
            issues.append({"level": "ERROR", "check": "S17", "file": page,
                           "msg": "页面出现 %d 个 <h1>（大纲应只有一个一级标题）"
                           % len(matches)})
            continue
        text = strip_re.sub("", matches[0])
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        if not re.sub(r"\s+", "", text):
            issues.append({"level": "ERROR", "check": "S17", "file": page,
                           "msg": "<h1> 内无可见文本（对阅读器无意义）"})
    return issues


# P-rev R79：S15 产物-清单一致性。生成器每次 --browse 把每页 sha256 写进
# manifest.json（见 matlabc.py 的 _write_site_manifest）。审计据此判定：
# ① 清单内文件缺失 / 哈希不匹配 → 产物被手工改动、或混入了半次生成的旧页，ERROR；
# ② 清单外出现页面级文件 → 陈旧残留或清单过旧，WARN。
# 不含 manifest.json 的目录（如单文件 report.html 产物）不参与，静默跳过。
def check_manifest_consistency(audit_root):
    issues = []
    if not os.path.isdir(audit_root):
        return issues
    for root, _dirs, fnames in os.walk(audit_root):
        if "manifest.json" not in fnames:
            continue
        mpath = os.path.join(root, "manifest.json")
        try:
            with io.open(mpath, "r", encoding="utf-8") as fh:
                man = json.load(fh)
        except (ValueError, OSError) as e:
            issues.append({"level": "ERROR", "check": "S15", "file": mpath,
                           "msg": "manifest.json 无法解析：" + str(e)})
            continue
        declared = man.get("pages")
        if not isinstance(declared, dict):
            issues.append({"level": "ERROR", "check": "S15", "file": mpath,
                           "msg": "manifest.json 缺少 pages 映射（字段结构不符）"})
            continue
        for rel, sha in sorted(declared.items()):
            # R(收尾)16：清单路径统一按 / 归一化，兼容 Windows 反斜杠分隔符
            rel = rel.replace("\\", "/").strip("/")
            fp = os.path.join(root, *rel.split("/"))
            # R(收尾)12：清单路径净化——拒绝 .. 越界，避免基于清单内容读取/校验
            # 审计目录之外的任意文件（S15 会据此 sha 外部文件，造成信息泄露/误判）。
            if os.path.relpath(os.path.abspath(fp),
                               os.path.abspath(root)).startswith(".."):
                issues.append({"level": "ERROR", "check": "S15", "file": rel,
                               "msg": "清单路径越界（含 .. 尝试逃出审计目录）：" + rel})
                continue
            if not os.path.exists(fp):
                issues.append({"level": "ERROR", "check": "S15", "file": fp,
                               "msg": "清单内文件缺失：" + rel})
                continue
            try:
                with io.open(fp, "rb") as fh:
                    cur = hashlib.sha256(fh.read()).hexdigest()
            except OSError as e:
                issues.append({"level": "ERROR", "check": "S15", "file": fp,
                               "msg": "无法读取校验：" + str(e)})
                continue
            if cur != sha:
                issues.append({"level": "ERROR", "check": "S15", "file": fp,
                               "msg": "产物与清单不一致（%s 被改动或为半次生成的旧页）"
                                      % rel})
        real = set()
        for r2, _d2, fs2 in os.walk(root):
            for fn2 in fs2:
                if fn2 == "manifest.json":
                    continue
                rel2 = os.path.relpath(os.path.join(r2, fn2), root).replace(os.sep, "/")
                real.add(rel2)
        for rel2 in sorted(real - set(declared)):
            # P-rev R92：_fe_* 为审计器自身运行时产物（_fe_dom_check.json /
            # _fe_perf_trend.csv），不视作「未登记交付物」——否则在已审计目录上
            # 二次审计必然误报 WARN（审计自己留下的文件）。
            if os.path.basename(rel2).startswith("_fe_"):
                continue
            fp2 = os.path.join(root, *rel2.split("/"))
            if os.path.basename(fp2).endswith((".html", ".htm", ".json",
                                               ".js", ".css", ".svg")):
                issues.append({"level": "WARN", "check": "S15", "file": fp2,
                               "msg": "产物未登记于清单：%s（陈旧残留或清单过旧）"
                                      % rel2})
    return issues


def check_quality_snapshot(audit_root):
    """P-rev R86：S16 质量快照一致性。

    site-quality.json 与 manifest.json 是一对「成对可信」的指纹文件：S15 保证每个文件
    sha 与清单一致，但若攻击/事故把**两个文件一起**改写（先改快照、再同步更新清单里的
    快照 sha），S15 会完全失效。S16 从快照**语义**下手：页面数 / 源码页数 / 资产数 /
    总字节都可直接从产物目录重新推导，与快照字段不一致即逐字段报错——伪造者必须
    同时维持两套计数与真实文件一一对应才可能蒙混过关。
    """
    issues = []
    if not os.path.isdir(audit_root):
        return issues
    for root, _dirs, fnames in os.walk(audit_root):
        if "site-quality.json" not in fnames:
            continue
        qpath = os.path.join(root, "site-quality.json")
        try:
            with io.open(qpath, "r", encoding="utf-8") as fh:
                q = json.load(fh)
        except (ValueError, OSError) as e:
            issues.append({"level": "ERROR", "check": "S16", "file": qpath,
                           "msg": "site-quality.json 无法解析：" + str(e)})
            continue
        real = {"html": 0, "source": 0, "assets": 0, "total_bytes": 0}
        for r2, _d2, fs2 in os.walk(root):
            for fn2 in fs2:
                if fn2 in ("manifest.json", "site-quality.json"):
                    continue
                if fn2.startswith("_fe_"):
                    # P-rev R92：审计器自身运行时产物不计入快照对账（等价于
                    # 生成器写快照时对它们的豁免），避免二次审计假 ERROR。
                    continue
                if fn2.endswith((".html", ".htm")):
                    real["html"] += 1
                if fn2.endswith(".m.html"):
                    real["source"] += 1
                if fn2.endswith((".js", ".json", ".css", ".svg")):
                    real["assets"] += 1
                try:
                    real["total_bytes"] += os.path.getsize(os.path.join(r2, fn2))
                except OSError:
                    pass
        qpages = q.get("pages")
        if not isinstance(qpages, dict):
            issues.append({"level": "ERROR", "check": "S16", "file": qpath,
                           "msg": "site-quality.json 缺少 pages 映射"})
            continue
        checks = [
            ("html_pages", real["html"], qpages.get("html")),
            ("source_pages", real["source"], qpages.get("source")),
            ("assets", real["assets"], q.get("assets")),
            ("total_bytes", real["total_bytes"], q.get("total_bytes")),
        ]
        for field, actual, snap in checks:
            if snap is None or snap != actual:
                issues.append({
                    "level": "ERROR", "check": "S16", "file": qpath,
                    "msg": "site-quality.json 与实况不一致：%s=期望%d/实际%d（快照陈旧或"
                           "与 manifest 被成对改写）" % (field, snap, actual)})
    return issues


# P-rev R57：趋势可视化面板。把 _fe_perf_trend.csv 渲染成一个自包含 HTML（内联 SVG
# 折线图 + 每页体积表），让「首屏是否随迭代变重」一眼可见，无需手工翻 CSV。
def build_trend_panel(audit_root, trend_dir=None):
    import csv
    import datetime
    trend_path = os.path.join(trend_dir, "_fe_perf_trend.csv") if trend_dir \
        else os.path.join(audit_root, "_fe_perf_trend.csv")
    if not os.path.exists(trend_path):
        return None
    series = {}  # page -> [(ts, inline, ext)]
    try:
        with io.open(trend_path, "r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                page = row.get("page", "")
                try:
                    inline = int(row.get("inline_js", 0))
                    ext = int(row.get("ext_js", 0))
                except (ValueError, TypeError):
                    continue
                series.setdefault(page, []).append((row.get("timestamp", ""), inline, ext))
    except (OSError, csv.Error):
        return None
    rows_html = []
    for page, pts in sorted(series.items()):
        first_inl = pts[0][1]
        last_inl = pts[-1][1]
        delta = last_inl - first_inl
        pct = (delta / float(first_inl) * 100.0) if first_inl else 0
        color = "#cf222e" if pct > 20 else ("#9a6700" if pct > 0 else "#1a7f37")
        # R(收尾)11：环比跳升标记——相邻两次审计间若出现 >50% 骤增，显式打 ⚠，
        # 让「某次提交把首屏体积瞬间撑大」一眼可见（单点突刺比缓慢爬升更可疑）。
        spike = ""
        for i in range(1, len(pts)):
            prev = pts[i - 1][1]
            cur = pts[i][1]
            if prev and abs(cur - prev) / float(prev) > 0.5:
                spike = " ⚠"
                break
        # P-rev R74：列值统一走 _fmt_kb 显示为 KB，并补"记录数"列——
        # 记录次数即该页被审计的次数，一眼能看出趋势可信度（1-2 条仅供参考）。
        rows_html.append(
            "<tr><td>%s%s</td><td>%d</td><td>%s KB</td><td>%s KB</td>"
            "<td style=\"color:%s\">%s KB (%+.0f%%)</td></tr>"
            % (page, spike, len(pts), _fmt_kb(first_inl), _fmt_kb(last_inl),
               color, _fmt_kb(delta, signed=True), pct))
    # P-rev R63：SVG 折线图——每页一条「内联体积随时间」的折线，横轴为记录序号，
    # 纵轴为内联 JS 字节；爬升斜率一眼可见。只画内联体积最多、最值得盯的前 8 页。
    chart_svg = _trend_svg(series)
    html = ("<!DOCTYPE html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
            "<title>前端体积趋势</title><style>"
            "body{font-family:system-ui,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#1f2328;}"
            "table{border-collapse:collapse;width:100%%;margin-top:12px;}"
            "th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #eaecef;font-size:13px;}"
            "th{background:#f6f8fa;}"
            "h1{font-size:20px;}.muted{color:#57606a;font-size:12px;}"
            "svg{display:block;margin:12px 0;border:1px solid #eaecef;border-radius:8px;background:#fafbfc;}"
            "</style></head><body><h1>前端体积趋势</h1>"
            "<p class=\"muted\">数据源 _fe_perf_trend.csv · 生成于 %s · 共 %d 个页面</p>"
            "%s"
            "<table><thead><tr><th>页面</th><th>记录数</th><th>首次内联</th>"
            "<th>最近内联</th><th>变化</th></tr></thead><tbody>%s</tbody></table>"
            "</body></html>"
            % (datetime.datetime.now().replace(microsecond=0).isoformat(),
               len(series), chart_svg, "".join(rows_html)))
    out_path = os.path.join(audit_root, "_fe_perf_report.html")
    with io.open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path


def check_real_dom(outdir, limit=None, timeout=None):
    """S11：真实 DOM（jsdom）交互验证 —— 可选增强检查。

    S5 用的是手写 DOM stub，只能捕获「脚本一跑就抛异常」；真实交互
    （主题切换是否持久化、命令面板能否打开并产出可跳转结果、#L 深链是否真高亮、
    skip-link 是否指向存在的元素）必须靠真实 DOM 才能验证。
    jsdom 缺失时降级为一条 stderr 提示（不参与门禁判定）—— 环境缺失不是站点缺陷，
    否则「没装 jsdom」会让 --strict 永远红。

    limit：最多检查多少页。jsdom 加载一页是秒级开销，200+ 页站点全量会到分钟级；
    而交互缺陷通常**按页型聚集**（同一模板生成的页面行为一致），故默认按页型采样
    （见 fe_dom_check.js 的 samplePages）。需要全量时传 limit=0。
    """
    if limit is None:
        limit = 12
    script = os.path.join(HERE, "fe_dom_check.js")
    node = shutil.which("node")
    if not node or not os.path.exists(script):
        return [{"level": "WARN", "check": "S11", "file": "-",
                 "msg": "未安装 node/缺少 fe_dom_check.js，跳过真实 DOM 检查"}]
    out_json = os.path.join(outdir, "_fe_dom_check.json")
    cmd = [node, script, outdir, "--out=" + out_json]
    if limit:
        cmd.append("--limit=%d" % limit)
    # R(收尾)5：超时护栏——jsdom 渲染挂死时强制终止，避免审计无限挂起
    rc, out, err = _run(cmd, timeout=timeout)
    if rc == 124:
        return [{"level": "ERROR", "check": "S11", "file": "-",
                 "msg": "真实 DOM 检查超时（--s11-timeout=%s）：疑似页面 JS 死循环或 jsdom 挂死"
                        % timeout}]
    if not os.path.exists(out_json):
        return [{"level": "WARN", "check": "S11", "file": "-",
                 "msg": "真实 DOM 检查未产出结果：%s" % ((err or out)[-200:])}]
    try:
        with io.open(out_json, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError) as e:
        return [{"level": "WARN", "check": "S11", "file": "-",
                 "msg": "真实 DOM 结果解析失败：%s" % e}]
    # R(收尾)6 / R94：roots 下无任何 HTML ⇒ **配置错误**（审计指向了错误的目录），
    # 与「有没有 jsdom」无关：这件事不需要真实 DOM 就能判定，fe_dom_check.js 也已在
    # 缺 jsdom 的早退分支里照样探过并回报 empty。
    # 所以该检查必须**排在 skipped 之前** —— 否则「没装 jsdom + 目录指错」会退化成
    # 一条 stderr 提示，门禁假绿。这正是本节要防的东西。
    if data.get("empty"):
        return [{"level": "ERROR", "check": "S11", "file": "-",
                 "msg": "未发现任何 HTML 页面（roots 下无 .html），真实 DOM 检查失效，门禁会假绿"}]
    if data.get("skipped"):
        # R94：jsdom 缺失是**环境**属性，不是站点缺陷。原实现产一条 WARN ⇒ 在
        # --strict 下把 rc 抬到非 0，等于「没装 jsdom 就永远过不了硬门禁」——
        # 与本节 docstring「不影响门禁判定」自相矛盾。改为与下方采样提示同款：
        # 打到 stderr（不污染 --json 的 stdout），不参与 ERROR/WARN 计数。
        print("S11 真实 DOM：未安装 jsdom（npm i jsdom），跳过真实 DOM 交互检查",
              file=sys.stderr)
        return []
    # 采样覆盖度仅作信息提示（打到 stderr，不污染 --json 的 stdout），
    # 让 S11 在「无真实 DOM 缺陷」时于 --strict 下可真正变绿。
    _sampled = data.get("sampled")
    _total = data.get("total")
    if isinstance(_sampled, int) and isinstance(_total, int) and _sampled < _total:
        print("S11 真实 DOM：按页型采样 %d/%d 页（全量请 --s11-limit=0）"
              % (_sampled, _total), file=sys.stderr)
    out_issues = []
    for it in data.get("issues", []):
        out_issues.append({
            "level": it.get("level", "WARN"), "check": "S11",
            "file": it.get("file", "-"), "msg": it.get("msg", "")})
    return out_issues


def main(argv):
    args = [a for a in argv[1:]]
    src = None
    outdir = None
    skip_gen = "--skip-generate" in args
    as_json = "--json" in args
    # R119：--hard-gate —— 「参考站就绪」三档门禁一键开齐：strict（零 WARN 退出码
    # 纪律）+ offline（零外部引用）+ budget（满足性能预算）。CI 一行进硬门禁。
    hard_gate = "--hard-gate" in args
    strict = "--strict" in args or hard_gate
    offline = "--offline" in args
    # --offline 是更强的标准：要求产物中**零**外部引用，S3 的 WARN 升级为 ERROR
    enforce_offline = "--enforce-offline" in args or hard_gate
    # R21：--enforce-budget 要求满足性能预算，S12 的 WARN 升级为 ERROR
    enforce_budget = "--enforce-budget" in args or hard_gate
    # 收尾改进：--enforce-seo —— S9（SEO/无障碍基线）告警升级为错误。
    # 前提：站点已做到 S9 零告警（description/OG/viewport/表头 scope/可访问名齐备），
    # 此时把护栏抬高到「可强制」，防止后续迭代悄悄退化（Loop 第14步：把验证器拧紧到可信）。
    enforce_seo = "--enforce-seo" in args or hard_gate
    # R-ratchet：棘轮护栏（默认关；--ratchet 开启，--ratchet-baseline=PATH 指定基线文件）。
    ratchet = "--ratchet" in args
    ratchet_baseline = _opt_str(args, "--ratchet-baseline=",
                               os.path.join(HERE, ".fe_audit_ratchet.json"))
    pos = [a for a in args if not a.startswith("--")]
    src = pos[0] if len(pos) > 0 else os.path.join(HERE, "tests", "sample_m")
    outdir = pos[1] if len(pos) > 1 else os.path.join(HERE, "_fe_out")

    # R104：--list-checks 打印检查项注册表后退出，不触碰任何目录。
    if "--list-checks" in args:
        for _code, _title in CHECK_REGISTRY:
            print("%s  %s" % (_code, _title))
        return 0

    # R111：--registry-json / --version —— 机器可消费能力自描述，同样不触碰任何目录。
    # （CI 侧可用 --registry-json 探测当前审计器版本与可用检查项，再决定参数组合。）
    # R120：能力清单纳入 schema 契约——下游升级审计器时若 schema 变化，无需逐个核对。
    # R126：每项附 note 速查说明——下游文档/帮助页直接消费，不再依赖人工维护的旁本。
    if "--registry-json" in args:
        print(json.dumps({
            "engine": "fe_audit",
            "engine_version": ENGINE_VERSION,
            "schema": SCHEMA_VERSION,
            "checks": [{"code": _code, "title": _title,
                        "note": CHECK_NOTES.get(_code, "")}
                       for _code, _title in CHECK_REGISTRY],
        }, ensure_ascii=False, indent=2))
        return 0
    if "--version" in args:
        print(ENGINE_VERSION)
        return 0

    # R149：--schema-json —— 摘要顶层键/issue 键清单自描述（下游零硬编码接入）。
    if "--schema-json" in args:
        print(json.dumps(_schema_manifest(), ensure_ascii=False, indent=2))
        return 0

    # R143/R144：--selftest / --selftest-json —— 纯引擎自检（不触碰目录）。
    if "--selftest" in args or "--selftest-json" in args:
        _report = _selftest_report_json()
        if "--selftest-json" in args:
            print(json.dumps(_report, ensure_ascii=False, indent=2))
        else:
            for _c in _report["checks"]:
                print("[%s] %s：%s" % (
                    "PASS" if _c["ok"] else "FAIL", _c["name"], _c["why"]))
            print("自检：%s（%d/%d 通过）" % (
                "全部通过" if _report["ok"] else "存在失败",
                sum(1 for _c in _report["checks"] if _c["ok"]),
                len(_report["checks"])))
        return 0 if _report["ok"] else 1

    # R133：--config-print —— 阈值配置注册表（默认值/CLI/env/说明）静态导出。
    if "--config-print" in args:
        print("阈值配置注册表（key ｜ 说明 ｜ CLI ｜ 环境变量 ｜ 内置默认）")
        for _k in sorted(THRESHOLD_META):
            _desc, _cli, _env, _dflt = THRESHOLD_META[_k]
            print("  %-18s ｜ %s ｜ %s ｜ %s ｜ %s" % (
                _k, _desc, _cli, _env or "-", _dflt if _dflt is not None else "（未设）"))
        print("生效优先级：CLI 参数 > --config=FILE > 环境变量 > 内置默认")
        return 0

    # R139：--list-ignores —— 打印豁免文件解析结果后退出（不审计、不改目录）。
    if "--list-ignores" in args:
        _igp = _opt_str(args, "--ignore-file=", None)
        if _igp is None:
            _igp = os.path.join(outdir, IGNORE_FILE_NAME)
        _ok_r, _rules, _err_r = _load_ignore_file(_igp)
        if not _ok_r:
            print("豁免文件不可读：%s" % _err_r, file=sys.stderr)
            return 1
        print("豁免文件：%s（%d 条规则）" % (_igp, len(_rules)))
        for _code, _fr, _mr in _rules:
            print("  %s ｜ %s ｜ %s" % (
                _code or "（通配）", _fr or "（通配）", _mr or "（通配）"))
        return 0

    # R150：--trend-json[=FILE] —— 趋势数据确定性导出（--since=ISO 过滤），只读 csv。
    _tj_path = _opt_str(args, "--trend-json=", None)
    if "--trend-json" in args or _tj_path:
        _tj = _trend_series_json(
            outdir, since=_opt_str(args, "--since=", None))
        if _tj_path:
            try:
                _write_json_file(_tj_path, _tj)
            except OSError as e:
                print("无法写 --trend-json：%s" % e, file=sys.stderr)
                return 1
            print("趋势导出已写入：%s" % _tj_path, file=sys.stderr)
        else:
            print(json.dumps(_tj, ensure_ascii=False, indent=2))
        return 0

    # R145：启动静默自检——每次审计前置跑纯引擎清单；失败即中止（--no-self 关闭）。
    # 引擎「把自己当被审对象」：注册表/注释/键契约漂移一律先亮相，再谈审计结果。
    if "--no-self" not in args:
        _fails = [_r for _r in _selftest_checks() if not _r[1]]
        if _fails:
            for _n, _ok, _w in _fails:
                print("启动自检失败：%s：%s" % (_n, _w), file=sys.stderr)
            print("引擎自检未通过，中止本次审计（可加 --no-self 强制继续）",
                  file=sys.stderr)
            return 1

    # R122：--delta=prev.json|cur.json —— 独立差异比较器（不执行审计）。配合 R118 的
    # 确定性摘要：CI 留档两轮 --out 后直接比较，新增 ERROR 即退出码 1（防回归门禁）。
    _delta = _opt_str(args, "--delta=", None)
    if _delta:
        if "|" not in _delta:
            print("--delta 需要两个摘要路径，用 | 分隔（例：--delta=prev.json|cur.json）",
                  file=sys.stderr)
            return 1
        _dprev, _dcur = _delta.split("|", 1)
        _ok_p, _prev_d = _load_summary_file(_dprev)
        if not _ok_p:
            print(_prev_d, file=sys.stderr)
            return 1
        _ok_c, _cur_d = _load_summary_file(_dcur)
        if not _ok_c:
            print(_cur_d, file=sys.stderr)
            return 1
        _added = _emit_diff(
            sys.stdout, "摘要差异",
            _prev_d.get("engine_version", "?"),
            _cur_d.get("engine_version", "?"),
            _prev_d.get("errors", []), _cur_d.get("errors", []),
            _prev_d.get("warns", []), _cur_d.get("warns", []))
        # R147：--delta-out=FILE —— 差异以结构化 JSON 落盘（新增/消失清单可机器消费）。
        _delta_out = _opt_str(args, "--delta-out=", None)
        if _delta_out:
            try:
                _write_json_file(_delta_out, _delta_payload(_prev_d, _cur_d))
                print("差异档已写入：%s" % _delta_out, file=sys.stderr)
            except OSError as e:
                print("无法写 --delta-out：%s" % e, file=sys.stderr)
        return 1 if _added else 0

    # R113：能力契约金样（写盘 / 对账）。均不触碰审计树，供 CI 独立调用。
    _cap_out = _opt_str(args, "--capability-out=", None)
    if _cap_out:
        try:
            _write_capability(_cap_out)
        except OSError as e:
            print("无法写 --capability-out：%s" % e, file=sys.stderr)
            return 1
        print("能力契约已写入：%s（%d 项检查）" % (
            _cap_out, len(CHECK_REGISTRY)), file=sys.stderr)
    _cap_chk = _opt_str(args, "--verify-capability=", None)
    if _cap_chk:
        _ok, _why = _check_capability(_cap_chk)
        print("%s：%s" % ("能力契约" if _ok else "能力契约漂移", _why),
              file=sys.stderr)
        return 0 if _ok else 1
    if _cap_out:
        return 0

    # R116：--explain=CODE —— 打印某检查项的速查语义后退出（CI 接入者手册入口）。
    _explain = _opt_str(args, "--explain=", None)
    if _explain:
        if _explain not in CHECK_NOTES:
            print("未知检查项：%s" % _explain, file=sys.stderr)
            return 1
        _title = dict(CHECK_REGISTRY).get(_explain, "")
        print("%s  %s" % (_explain, _title))
        print("  " + CHECK_NOTES[_explain])
        return 0

    # R130：--tag=键=值 自定义上下文（可重复）——只进 JSON tags，供 CI 标注
    # 轮次/分支/环境；不参与任何判定，默认空 dict（键排序确定性）。
    tags, _bad_tags = _parse_tags(args)
    for _bt in _bad_tags:
        print("警告：忽略非法 --tag：%s（需 键=值，键限字母数字._-）" % _bt,
              file=sys.stderr)

    # R133：--config=FILE —— 阈值配置档。解析失败/非法键只告警并回退，不让
    # 小错配置拖垮整次审计；cfg 随后被 _resolve_metric 按四层优先序读取。
    cfg = {}
    _cfg_path = _opt_str(args, "--config=", None)
    if _cfg_path:
        _cfg_load, _cfg_err = _load_config_file(_cfg_path)
        if _cfg_err:
            print("--config=%s 不可用：%s（按内置默认继续）" % (_cfg_path, _cfg_err),
                  file=sys.stderr)
        else:
            cfg = _cfg_load

    # R103：--warn-ok=S3,S12 放行集合。--strict 下这些检查项的 WARN 不再触发退出码 2
    # （用于「明知某类噪音仍想保住整体零警告」的渐进收敛，而不是一刀切关掉 --strict）。
    warn_ok = _parse_warn_ok(args)
    for _code in warn_ok:
        if _code not in CHECK_IDS:
            print("警告：--warn-ok 含未登记检查项 %s（将被忽略）" % _code,
                  file=sys.stderr)

    # R109：--samples=N —— 文本输出里每个检查项附带的样例条数（0=只计数不列样例）。
    # R134：数值类阈值统一走四层取值（CLI > --config > 环境变量 > 默认）。
    samples_n = _resolve_metric(args, cfg, "samples")
    if samples_n is None or samples_n < 0:
        samples_n = 0

    # R117：--elapsed-budget=ms —— 审计器自身耗时预算（负值视为关闭）。
    _elapsed_budget = _resolve_metric(args, cfg, "elapsed_budget_ms")
    if _elapsed_budget is not None and _elapsed_budget < 0:
        _elapsed_budget = None

    # R110：本轮耗时（生成 + 审计）进入摘要，供 CI 监控审计器自身性能退化。
    _t0 = time.time()

    gen = {}
    # P-rev R26：--skip-generate 时审计 outdir 整体（既有产物）；
    # 否则只审计本次落在该隔离子目录里的产物，避免误扫交付站点内容。
    audit_root = outdir
    if not skip_gen:
        gen, audit_root = generate_reports(src, outdir, offline=offline)

    pages = collect_html(audit_root)
    issues = []
    # R(收尾)1：空产物假绿守卫——若审计到 0 个页面（生成器静默零产出 / 站点无可识别
    # html），所有 check 空转、S15/S16 因无清单跳过，门禁会假绿。--min-pages 默认 1，
    # 0 页直接报 ERROR 阻断；负值/0 视为关闭该守卫。
    _min_pages = _opt_int(args, "--min-pages=", 1)
    if _min_pages < 0:
        _min_pages = 0
    if _min_pages and len(pages) < _min_pages:
        issues.append({"level": "ERROR", "check": "INT", "file": audit_root,
                       "msg": "未审计到任何页面（生成器可能零产出；期望 >=%d，实得 %d）"
                              % (_min_pages, len(pages))})
    # P-rev R96：审计过程写文件执法——运行前快照审计树，结束时任何新增且非
    # _fe_* 的文件都会以 INT ERROR 亮相（审计器必须先自证洁净，S15/S16 才可信）。
    _base_snap = set()
    for _r0, _d0, _fs0 in os.walk(audit_root):
        for _f0 in _fs0:
            _base_snap.add(os.path.join(_r0, _f0))

    # R137：豁免文件——--ignore-file=FILE 指定；否则自动发现 audit_root/.fe_auditignore。
    # 缺省零规则（行为与既往完全一致）；规则只在既有目录显式/自动存在时才介入。
    _ig_path = _opt_str(args, "--ignore-file=", None)
    if _ig_path is None:
        _ig_auto = os.path.join(audit_root, IGNORE_FILE_NAME)
        if os.path.exists(_ig_auto):
            _ig_path = _ig_auto
    ignore_rules = []
    if _ig_path:
        _ok_ig, ignore_rules, _ig_err = _load_ignore_file(_ig_path)
        if not _ok_ig:
            print("豁免文件读取失败：%s（按无豁免继续）" % _ig_err, file=sys.stderr)
            ignore_rules = []
        elif ignore_rules:
            print("豁免生效：%s（%d 条规则）" % (_ig_path, len(ignore_rules)),
                  file=sys.stderr)

    for gname, gres in gen.items():
        if gres.get("rc") not in (0, None):
            issues.append({"level": "ERROR", "check": "GEN", "file": gname,
                           "msg": "生成失败 rc=%s：%s" % (gres.get("rc"), gres.get("stderr", ""))})
    issues += check_js_syntax(pages)
    issues += check_links_and_cdn(outdir, pages)
    issues += check_js_runtime(pages)
    issues += check_interaction_wiring(pages)
    issues += check_orphan_pages(audit_root, pages)
    issues += check_js_hrefs(pages)
    issues += check_a11y_baseline(pages)
    issues += check_inline_handlers(pages)
    issues += check_external_script_defer(pages)
    issues += check_inline_style(pages)
    issues += check_img_alt(pages)
    issues += check_hardcoded_nav(pages)
    # P-rev R72：S4 增强——跨页锚点死锚（目标文件在、目标锚点已删）
    issues += check_cross_page_anchors(pages)
    # P-rev R76：S13 重复 id 守卫（深链 / getElementById 寻址键唯一性）
    issues += check_duplicate_ids(pages)
    # P-rev R77：S14 结构配对/地标嵌套守卫（浏览器静默自我修复的结构错位）
    issues += check_html_structure(pages)
    # P-rev R79：S15 产物-清单一致性（站点含 manifest.json 时做 sha256 对账）
    issues += check_manifest_consistency(audit_root)
    # P-rev R86：S16 质量快照一致性（site-quality.json 语义复核，防成对改写）
    issues += check_quality_snapshot(audit_root)
    # 5轮收尾改进 R1：S17 一级标题语义（每页恰好一个非空 h1）
    issues += check_h1_hierarchy(pages)
    # R(收尾)6：S18 图片尺寸/CLS——缺 width/height 声明会引起布局抖动
    issues += check_img_dims(pages)
    # R(收尾)7：S19 重复 <title>——跨页面相同标题损害 SEO/可寻址性
    issues += check_duplicate_titles(pages)
    # S11 依赖 jsdom，缺失时降级为 WARN；可用时提供真实交互验证。
    # 默认按页型采样（--s11-limit），全量用 --s11-limit=0。
    s11_limit = 0 if "--s11-full" in args else _resolve_metric(args, cfg, "s11_limit")
    # R(收尾)5：S11 超时护栏（0=不限），防止 jsdom 渲染挂死拖垮整轮审计
    _s11_to = _resolve_metric(args, cfg, "s11_timeout")
    s11_timeout = None if not _s11_to else _s11_to
    issues += check_real_dom(audit_root, limit=s11_limit, timeout=s11_timeout)
    # S12：性能预算（默认 150KB JS / 20 请求）。
    # R134：--js-budget/--req-budget/--inline-budget 与 --config 四层解析；
    # 解析出的生效值同时供 --budget-table 标注（同源，杜绝两处默认不一致）。
    _eff_js_budget = _resolve_metric(args, cfg, "js_budget")
    _eff_inline_budget = _resolve_metric(args, cfg, "inline_budget")
    _eff_req_budget = _resolve_metric(args, cfg, "req_budget")
    _trend_dir = _opt_str(args, "--trend-dir=", None)
    issues += check_perf_budget(
        audit_root, pages,
        js_budget=_eff_js_budget,
        req_budget=_eff_req_budget,
        inline_budget=_eff_inline_budget,
        self_contained=_resolve_self_contained(cfg),
        trend_dir=_trend_dir)
    # P-rev R61：趋势增长告警——对比上次审计，任一页面内联 JS 增长超过 20% 即 WARN。
    # 单次阈值抓「突然超限」，这里抓「每轮偷偷变重」的缓慢退化。
    # P-rev R69/R134：增长阈值可配 --growth-pct=N（默认 20%）
    issues += check_perf_growth(
        audit_root, growth_pct=_resolve_metric(args, cfg, "growth_pct"),
        trend_dir=_trend_dir)
    # P-rev R57：--trend-report 生成可视化面板（_fe_perf_report.html）
    if "--trend-report" in args:
        panel = build_trend_panel(audit_root, trend_dir=_trend_dir)
        if panel:
            print("趋势面板已生成：%s" % panel)

    # P-rev R93：检查输出契约校验。任何畸形 issue（缺 check/level/msg、级别非法、
    # 非 dict）一律归拢为 INT ERROR——打印聚合（by_check/汇总）绝不允许因一条脏
    # issue 而崩溃；INT 是审计器内部错误，不带入 S 系列登记。
    _clean = []
    for _it in issues:
        if (isinstance(_it, dict)
                and isinstance(_it.get("check"), str) and _it["check"]
                and _it.get("level") in ("ERROR", "WARN")
                and isinstance(_it.get("msg"), str)):
            _clean.append(_it)
        else:
            _clean.append({"level": "ERROR", "check": "INT", "file": "",
                           "msg": "审计器内部契约错误：" + repr(_it)[:120]})
    issues = _clean

    # R104：注册表执法——任何未在 CHECK_REGISTRY 登记的检查代码一律归拢为 INT ERROR。
    # 防止「新检查忘了登记」导致下游（by_check 面板 / --warn-ok 白名单）静默误读。
    issues = [
        it if it["check"] in CHECK_IDS
        else {"level": "ERROR", "check": "INT", "file": it.get("file", ""),
              "msg": "未登记检查项 %s：%s" % (it["check"], it.get("msg", ""))[:120]}
        for it in issues
    ]

    # --enforce-offline：要求产物零外部引用，S3 告警升级为错误
    if enforce_offline:
        for i in issues:
            if i["check"] == "S3" and i["level"] == "WARN":
                i["level"] = "ERROR"
                i["msg"] = "[offline 违规] " + i["msg"]
    # 收尾改进：S9（SEO/无障碍基线）在 --enforce-seo / --hard-gate 下升级为错误。
    if enforce_seo:
        for i in issues:
            if i["check"] == "S9" and i["level"] == "WARN":
                i["level"] = "ERROR"
                i["msg"] = "[SEO/无障碍基线] " + i["msg"]
    # R21：--enforce-budget 要求产物满足性能预算，S12 告警升级为错误（CI 硬性卡住变重）
    # R66：趋势增长告警（R61）同样升级为 ERROR，让 CI 同时卡「突然超限」与「缓慢变重」。
    if enforce_budget:
        for i in issues:
            if i["check"] == "S12" and i["level"] == "WARN":
                i["level"] = "ERROR"
                # 区分两类：增长告警带「增长」字样，预算告警带「预算」字样
                prefix = "[体积增长]" if "增长" in i["msg"] else "[超出性能预算] "
                i["msg"] = prefix + i["msg"]
    # P-rev R96：运行结束核对审计树——新增的非 _fe_* 文件一律 INT ERROR
    _now_snap = set()
    for _r0, _d0, _fs0 in os.walk(audit_root):
        for _f0 in _fs0:
            _now_snap.add(os.path.join(_r0, _f0))
    for _new in sorted(_now_snap - _base_snap):
        if not os.path.basename(_new).startswith("_fe_"):
            issues.append({"level": "ERROR", "check": "INT", "file": _new,
                           "msg": "审计过程写入了未声明产物：" +
                                  os.path.basename(_new)})
    # R110/R117：本轮耗时（生成+审计）在此一次性结算——既要进摘要，也要在排序前
    # 参与 PERF 预算判定与 by_check 统计。排除 elapsed_ms 后其余字段仍是确定性输出。
    _elapsed_ms = int((time.time() - _t0) * 1000)
    if _elapsed_budget is not None and _elapsed_ms > _elapsed_budget:
        issues.append({"level": "WARN", "check": "PERF", "file": "",
                       "msg": "本轮耗时 %d ms 超预算 %d ms" % (
                           _elapsed_ms, _elapsed_budget)})

    # R138：豁免应用——排序/计数前滤除命中 .fe_auditignore 的 issue，使 errors /
    # warns / by_check / page_stats / --against 差异全部基于「豁免后」同一集合，
    # 语义一处定义、处处一致。--show-ignored 把被豁免明细打到 stderr（不污染 stdout）。
    if ignore_rules:
        _kept, _ignored = [], []
        for _it in issues:
            if _ignored_by(_it, ignore_rules):
                _ignored.append(_it)
            else:
                _kept.append(_it)
        if _ignored:
            if "--show-ignored" in args:
                for _it in _ignored:
                    print("已豁免：%s | %s | %s" % (
                        _it.get("file", ""), _it.get("check", ""),
                        _it.get("msg", "")), file=sys.stderr)
            print("豁免生效：%d 条 issue 已豁免" % len(_ignored), file=sys.stderr)
        issues = _kept

    # R107：确定性排序——(级别, 文件, 检查项, 消息) 全序，使同一棵树在任何运行 /
    # 任何 OS（os.walk 顺序不定）都产出逐字节一致的 issue 序列，CI 可直接对
    # JSON/文本做新旧差异比对，也消除 R96 追加 INT 与各检查间序的偶然性。
    issues.sort(key=lambda i: (
        0 if i.get("level") == "ERROR" else 1,
        i.get("file", ""), i.get("check", ""), i.get("msg", "")))
    # R-ratchet：棘轮护栏——对已清零门禁，若回涨则追加 ERROR（check=INT），防止悄悄退化。
    # 必须在 errors/warms 拆分前注入，使回归项计入 error_count 与 by_check。
    if ratchet:
        _bc = _count_by_check(issues)
        _ratchet_added = _apply_ratchet(_bc, ratchet_baseline)
        if _ratchet_added:
            issues.extend(_ratchet_added)
            issues.sort(key=lambda i: (
                0 if i.get("level") == "ERROR" else 1,
                i.get("file", ""), i.get("check", ""), i.get("msg", "")))
    errors = [i for i in issues if i["level"] == "ERROR"]
    warns = [i for i in issues if i["level"] == "WARN"]
    # R103：--strict 下仅「非白名单」WARN 触发退出码 2。白名单项照常展示，只是不再
    # 阻断（CI 可借此保住 strict 的零噪音纪律，同时容忍已知且已被登记放行的类别）。
    blocking_warns = [w for w in warns if w["check"] not in warn_ok]

    # R123：页面级统计——含 ERROR/WARN 的独立页面数。
    # R94 修：判据从「file 非空」收紧为「file **必须真的在 pages 里**」。
    #   原实现只挡空串，而工具级失败用 "-"（S1/S5/S11，不属于任何页）——
    #   "-" 是真值 ⇒ 被当成一个页 ⇒ 本摘要与 _pages_export 的 page_stats
    #   在「S11 降级 WARN / S1 / S5」时给出两个**都对不上**的数字
    #   （实测 2 vs 1，test_r128 因此红）。
    #   改后两侧同为「按 pages 归并」，结构上不可能再分叉。
    _page_set = set(pages)
    _err_pages = sorted(set(_i["file"] for _i in errors
                            if _i.get("file") in _page_set))
    _warn_pages = sorted(set(_i["file"] for _i in warns
                             if _i.get("file") in _page_set))
    page_stats = {"audited": len(pages), "with_error": len(_err_pages),
                  "with_warn": len(_warn_pages)}

    # R125：--against=FILE —— 本轮与历史摘要（此前 --out 留档）对比。差异块打到
    # stderr：不污染 --json 的 stdout，也保持文本模式与无基线运行逐字节一致。
    _against = _opt_str(args, "--against=", None)
    if _against:
        _ok_a, _prev_a = _load_summary_file(_against)
        if not _ok_a:
            print("--against：%s（忽略，继续审计）" % _prev_a, file=sys.stderr)
        else:
            _emit_diff(sys.stderr, "基线对比（--against）",
                       _prev_a.get("engine_version", "?"), ENGINE_VERSION,
                       _prev_a.get("errors", []), errors,
                       _prev_a.get("warns", []), warns)

    summary = {
        "engine": "fe_audit",  # P-rev R98：JSON 摘要自述引擎，防跨工具误读
        # R112：schema 版本只随「顶层键布局的 breaking 变化」递增，下游据此决定
        # 是否需要迁移解析器（engine_version 变不代表 JSON 结构变）。
        "schema": SCHEMA_VERSION,
        # R102：引擎版本 + 按检查项聚合——JSON 与文本输出共享同一份聚合语义，
        # 下游（CI 面板/趋势）无需再从 errors/warns 裸数组自行重算。
        "engine_version": ENGINE_VERSION,
        # R114：一键复现命令——错误日志/留档 JSON 里自带当时的确切调用，
        # 排障时复制粘贴即可复跑（args 不含机密路径，序列化确定）。
        "rerun": "fe_audit.py " + " ".join(shlex.quote(_a) for _a in args),
        "mode": "generate" if not skip_gen else "audit-only",
        "strict": strict,
        "hard_gate": hard_gate,  # R119：三档门禁是否一键开齐（下游审计记录可回溯门禁口径）
        "warn_ok": sorted(warn_ok),
        # R130：--tag=键=值 自定义上下文（CI 标注轮次/分支等，默认空 dict）。
        "tags": tags,
        "pages": len(pages),
        # R123：页面级统计（audited=审计页面数，with_error/with_warn=受影响页面数）。
        "page_stats": page_stats,
        "by_check": _count_by_check(issues),
        "error_count": len(errors),
        "warn_count": len(warns),
        "blocking_warn_count": len(blocking_warns),
        "elapsed_ms": _elapsed_ms,
        "errors": errors,
        "warns": warns,
    }

    # R127：摘要顶层键注册表执法——键集合漂移（开发期加键忘登记等）即内部错误：
    # 打 stderr 告警并把退出码抬到 >=1，让「悄悄破坏下游解析契约」先于结果暴露。
    _miss = sorted(SUMMARY_KEYS - set(summary))
    _extra = sorted(set(summary) - SUMMARY_KEYS)
    if _miss or _extra:
        print("INT：摘要顶层键漂移（多出 %s / 缺少 %s）——需同步 SUMMARY_KEYS 与 "
              "SCHEMA_VERSION" % (_extra, _miss), file=sys.stderr)

    if as_json:
        # R118：stdout 与 --out 落盘统一 sort_keys + indent=2——同一摘要的两条输出
        # 渠道逐字节同序（仅 stdout 末尾多一个换行），CI 全文 diff 不再有假阳性。
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print("=" * 70)
        print("前端产物审计：%d 个页面" % len(pages))
        print("=" * 70)
        # R124：版本与门禁口径元信息行——日志/留档一眼可溯源「这轮是谁、按什么档位审的」。
        _meta = ["fe_audit %s" % ENGINE_VERSION,
                 "schema %d" % SCHEMA_VERSION,
                 "模式 %s" % ("generate" if not skip_gen else "audit-only")]
        if hard_gate:
            _meta.append("硬门禁")
        else:
            if strict:
                _meta.append("--strict")
            if enforce_offline:
                _meta.append("--enforce-offline")
            if enforce_budget:
                _meta.append("--enforce-budget")
            if enforce_seo:
                _meta.append("--enforce-seo")
        # R136：--config 生效时在 meta 行标注配置文件名（日志可溯源阈值口径）。
        if _cfg_path:
            _meta.append("config %s" % os.path.basename(_cfg_path))
        print("｜ ".join(_meta))
        # 按检查项聚合（与 JSON 的 by_check 同源，均由 _count_by_check 计数；
        # 文本附样例便于人工扫读，条数由 --samples=N 控制，默认 4，0=只计数）
        by_check = _count_by_check(issues)
        for ck in sorted(by_check):
            d = by_check[ck]
            print("[%s] ERROR=%d WARN=%d" % (ck, d["ERROR"], d["WARN"]))
            if samples_n > 0:
                for s in [i for i in issues if i["check"] == ck][:samples_n]:
                    print("    · %s | %s" % (os.path.basename(s["file"]),
                                             s["msg"][:150]))
        print("-" * 70)
        # R115：有 ERROR 时额外列出失败文件（去重、排序），便于一眼看出哪些页面挂了。
        if errors:
            print("失败文件（%d 个文件 / %d 条 ERROR）：" % (
                len(set(_i["file"] for _i in errors)), len(errors)))
            for _f in sorted(set(_i["file"] for _i in errors)):
                print("  - %s" % _f)
        # R123：页面级统计行（与 JSON page_stats 同源）。
        print("页面统计：共 %d 页 ｜ 含 ERROR %d 页 ｜ 含 WARN %d 页" % (
            len(pages), len(_err_pages), len(_warn_pages)))
        print("合计：ERROR %d ｜ WARN %d" % (len(errors), len(warns)))
        if warn_ok:
            print("（--warn-ok 放行 %d 条：%s）" % (
                len(warns) - len(blocking_warns), ",".join(sorted(warn_ok))))
        if tags:
            print("tags：%s" % "  ".join("%s=%s" % (_k, _v)
                                        for _k, _v in sorted(tags.items())))
        # R129：--top-pages=N —— 问题最集中的 N 个页面榜（ERROR 降序，再 WARN）。
        _top_n = _opt_int(args, "--top-pages=", 0)
        if _top_n > 0 and (errors or warns):
            print("问题页面 Top %d（按 ERROR 降序，再 WARN）：" % _top_n)
            for _f, _e, _w in _page_issue_rows(pages, errors, warns)[:_top_n]:
                if _e or _w:
                    print("  - %s ｜ ERROR %d ｜ WARN %d" % (_f, _e, _w))
        # R135：--budget-table —— 每页首屏 JS 明细（与 S12 同源度量，超预算标 *）。
        if "--budget-table" in args:
            print("性能预算明细（内联/外链/请求数，超出当前生效预算标 *）：")
            print("  页面 ｜ 内联KB ｜ 外链KB ｜ 请求数 ｜ 判定")
            for _p in pages:
                _m = _measure_page_js(_p)
                if _m is None:
                    continue
                _ik, _ek, _rq = _m
                _ov = []
                if _ik > _eff_inline_budget:
                    _ov.append("内联")
                if _ek > _eff_js_budget:
                    _ov.append("外链")
                if _rq > _eff_req_budget:
                    _ov.append("请求数")
                print("  %s ｜ %.1f ｜ %.1f ｜ %d ｜ %s" % (
                    os.path.relpath(_p, audit_root).replace("\\", "/"),
                    _ik / 1024.0, _ek / 1024.0, _rq,
                    "*" + "+".join(_ov) if _ov else "OK"))
        print("耗时：%d ms" % _elapsed_ms)

    rc = 1 if errors else (2 if strict and blocking_warns else 0)
    # R127：顶层键漂移属内部错误——即使没有普通 ERROR 也把退出码抬到 1。
    if _miss or _extra:
        rc = max(rc, 1)
    # P-rev R98/R99：--out=FILE 把 JSON 摘要写盘留档。写在退出码计算之后、
    # R96 写文件执法快照之外——既不影响本轮的洁净判定，也允许下一次审计
    # 把上次的 _fe_* 摘要当作普通既有文件（新文件增量判定天然忽略它）。
    out_path = _opt_str(args, "--out=", None)
    if out_path:
        try:
            with io.open(out_path, "w", encoding="utf-8") as fh:
                # R118：与 stdout 同款 sort_keys + indent=2（见上），渠道间逐字节同序。
                json.dump(summary, fh, ensure_ascii=False,
                          sort_keys=True, indent=2)
        except OSError as e:
            print("无法写 --out 文件：%s" % e, file=sys.stderr)

    # R128：--issues-json / --page-json —— 明细留档（确定性 sort_keys），
    # 与 --out 同规则：写盘发生在退出码与 R96 快照核对之后，不影响洁净判定。
    _issues_out = _opt_str(args, "--issues-json=", None)
    if _issues_out:
        try:
            _write_json_file(_issues_out, _issue_export(summary))
            print("issues 明细已写入：%s" % _issues_out, file=sys.stderr)
        except OSError as e:
            print("无法写 --issues-json：%s" % e, file=sys.stderr)
    _page_out = _opt_str(args, "--page-json=", None)
    if _page_out:
        try:
            _write_json_file(_page_out, _pages_export(pages, errors, warns))
            print("页面明细已写入：%s" % _page_out, file=sys.stderr)
        except OSError as e:
            print("无法写 --page-json：%s" % e, file=sys.stderr)

    # R127：--summary-line —— 单行 TSV 摘要（CI 面板/监控一行吞全部关键量）。
    # 与 --json 同用时改走 stderr，避免污染 stdout 的纯 JSON。
    if "--summary-line" in args:
        _line = _summary_line(summary, rc)
        if as_json:
            print(_line, file=sys.stderr)
        else:
            print(_line)

    # R148：--archive=PREFIX —— 一次落三档（summary/issues/pages）留档包。
    _arch = _opt_str(args, "--archive=", None)
    if _arch:
        _arch_pages = _pages_export(pages, errors, warns)
        for _suffix, _obj in (("-summary.json", summary),
                              ("-issues.json", _issue_export(summary)),
                              ("-pages.json", _arch_pages)):
            _path = _arch + _suffix
            try:
                _write_json_file(_path, _obj)
                print("归档已写：%s" % _path, file=sys.stderr)
            except OSError as e:
                print("无法写归档 %s：%s" % (_path, e), file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
