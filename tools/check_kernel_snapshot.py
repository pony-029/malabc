# -*- coding: utf-8 -*-
"""全树规模读数（跑次登记表）+ 分析流程登记的登记制护栏 —— 判据族 W1–W7。

它回答两个问题：
  1. **文档里那张「内核全树跑出来的数字」还成立吗？**
  2. **产出那张数字的流程有哪几站、该跑哪一代驱动？**（W6）

为什么需要它（四条，都是本仓已经踩过的形态）：
  * **会走进文档与提交信息的数字，必须有一个能在下次重算它的装置**（L67）。
    重跑内核要 ~13 分钟，不适合放进门禁 ⇒ 本门**不重跑**，它钉住的是
    「这个读数是**哪一份被测物**（`matlabc.py` 的 sha256）在**哪一棵语料**
    （指名子树）上产出的」。
  * **两个分母必须并列，且必须指名子树**（判据设计纪律 #8 / §4r-1）。
    「内核有多少文件」有两个**都对**的答案：C 族扩展名 62,704 与
    全部扩展名 63,051。写一个数就是挑一个迎合结论的口径 ⇒ W3 断言两个都在、
    都 > 0、且**互不相等**（把两者合成一个数即红）。
  * **汇总与明细必须对账**（§4x-1）：启发式的 `heuristics` 总数与按类别
    直方图之和是同一个量的两条路径，两边一起错时**对账发现不了**，
    所以这里用**恒等式**（`Σkinds == heuristics`），它不是调出来的阈值。
  * **「流程在哪里」曾经是一个没有对手方的问题**（L85）。这条流程只活在
    8 个脚本的 docstring 里，散在 `_kernel/`（R75–R81）与 `_r82/`（R84）
    两棵**仓外**树 ⇒ 没有任何一处能回答「有哪几站、该跑哪一代」，
    而盘上真躺着三代驱动，其中一代**再跑一次就会就地覆盖对照基线**。
    ⇒ W6 把站表搬进登记表，并用「**恰好一个 current 分析器**」与
    「**产物链拓扑**」两条判据钉住它 —— 站表可以随便列，链不会。

本门**不做识别**：不跑分析、不读源码、不解析二进制、不碰内核语料
（1.3 GB 语料与 13 分钟预算都不属于一道静态门）。它只回答：
「那张表与那条流程自称的那件事，今天还成立吗？」

为什么还要 W7（R95，**第五个形态**）：登记表里那张「运行产物（本表生成时逐个
现算）」表，**在生成之后没有任何判据再看它一眼** —— 生成器的 `--check` 在本仓
**零调用点**，而 `audit()` 与产物有关的判据只有 `provenance.*` 两行。实测后果：
`kernel_c_summary.json`(10-14 02:40) 与 `kernel_callgraph.json`(10-13 22:47)
来自**两个不同的构建**，表头却只钉一份 `provenance` ⇒ 一张表混了两趟读数，
谁也不报（与 R88 在 `AGG_r84.json` 合并逻辑里修过的是**同一个病换了载体**）。
W7 把「表 ⇄ 磁盘」这条对手方补上：产物字节数与 sha256 由**门自己现算**核对。
⚠ 产物在**仓外**（`_kernel/` 不在新克隆里）⇒ 磁盘上没有该产物时该条**未行使**
（与跨文档分母同一条口径），但**必须打印出来**，绝不静默当成「对得上」。

退出码：
    0  = W1–W7 全部通过
    1  = 发现违规
    2  = 缺输入（登记表不在 / 任一块缺失 / 格式不可解析 / `matlabc.py` 不在）
"""
import io
import os
import re
import sys

ROW_SIGNATURE = "W1–W7"

_here = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_here)

DOC = os.path.join("docs", "KERNEL_RUN.md")
MATLABC = "matlabc.py"
UNKNOWN_DOC = os.path.join("docs", "UNKNOWN_SITES.md")

BLOCK_OPEN = "<!-- KERNEL-RUN v1 -->"
BLOCK_CLOSE = "<!-- /KERNEL-RUN -->"

# 两侧 README 必须把内核读数的**唯一事实源**指出来。
# 为什么是一条判据而不是一句倡议：仓库里现在同时躺着两个**都对**的读数
# （R75 的 `661 s / 10.8 GB` 与 R81 的 `793.4 s / 13.1 GB`），差的是
# **cwd 约定**（`cwd=REPO` 时 `rel` 退化成 basename、`cwd=CORPUS` 时是真相对路径），
# 而**没有任何东西在看** —— 指针没有对手方时，它指空了也看不出来（L85）。
SNAPSHOT_POINTER = "KERNEL_RUN.md"
CLOCK_KEYS = ("peak_mb", "seconds")

# W7（R95）：登记表里**逐个现算**的**仓外**产物名单。
# 名字写在这里（门的分母）而**不**从块里现推 —— 块里那几条 `artifact.<名>.*`
# 是生成器写的，若门的名单也由块推出来，「生成器漏登记一份产物」就永远看不出来。
ARTIFACT_NAMES = ("kernel_c_summary.json", "kernel_asm_summary.json",
                  "kernel_callgraph.json")

# 每臂都必须出现的键（缺一个 ⇒ W1 红）。数字型键统一在 _num() 里转换。
ARM_KEYS = ("files", "lines", "funcs", "edges", "unresolved", "includes",
            "heuristics", "peak_mb", "seconds", "rc", "json_bytes")
ASM_KEYS = ("files", "lines", "rc", "seconds", "peak_mb", "json_bytes")

# 与时钟 / 资源相关 ⇒ **不参与** R81⇄R84 对照（§4c-1：单次墙钟不可裁决）

REQUIRED = (
    ["provenance.matlabc_sha256", "provenance.matlabc_bytes",
     "provenance.git_head", "provenance.cwd_convention",
     "corpus.path", "corpus.files_c_family", "corpus.files_all_ext",
     "corpus.bytes", "corpus.files_repo_plus_oss",
     "baseline.path", "baseline.sha256",
     "crossdoc.unknown_sites_files"]
    + ["arm_c." + k for k in ARM_KEYS]
    + ["arm_asm." + k for k in ASM_KEYS]
    + ["base_c." + k for k in ARM_KEYS]
    + ["base_asm." + k for k in ASM_KEYS]
)


# --------------------------------------------------------------- 解析
def parse_block(text, open_mark=None, close_mark=None, tag="W1"):
    """取块 -> (kv, problems)。kv 为 None 表示没取到。

    规则（每条都对应一次真事故）：
      * 开/闭标记各必须**恰好出现一次** —— 重号会让切片落错地方（§4z-15）。
      * 标记之间必须紧跟一个围栏块。
      * 数据行 `键 | 值`；`#` 开头或空行是注释。
      * **键不得重复** —— 重复会静默折叠成一个（L73 的多重集纪律）。

    `open_mark` / `close_mark` / `tag` 让**同一个解析器**同时服务两块（读数块与
    流程块）—— 两份实现必然分叉（§4x-5：一个量只许有一份实现）。
    """
    o = open_mark or BLOCK_OPEN
    c = close_mark or BLOCK_CLOSE
    probs = []
    if text.count(o) != 1:
        return None, ["%s 开标记 %r 出现 %d 次（要求恰好 1 次）"
                      % (tag, o, text.count(o))]
    if text.count(c) != 1:
        return None, ["%s 闭标记 %r 出现 %d 次（要求恰好 1 次）"
                      % (tag, c, text.count(c))]
    i = text.index(o) + len(o)
    j = text.index(c)
    if j < i:
        return None, ["%s 闭标记出现在开标记之前" % tag]
    body = text[i:j]
    m = re.search(r"```[^\n]*\n(.*?)```", body, re.S)
    if not m:
        return None, ["%s 开闭标记之间没有围栏块（必须用 ``` 围起来）" % tag]
    lines = m.group(1).split("\n")
    kv = {}
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if s.count("|") != 1:
            probs.append("%s 数据行必须恰好一个 `|` 分隔符：%r" % (tag, ln))
            continue
        k, v = s.split("|")
        k, v = k.strip(), v.strip()
        if not k:
            probs.append("%s 空键：%r" % (tag, ln))
            continue
        if k in kv:
            probs.append("%s 键 %r 重复（重复会静默折叠成一个 ⇒ 必须红）" % (tag, k))
            continue
        if v == "":
            probs.append("%s 键 %r 的值为空（缺值必须红；要表示「无」请写 `-`）"
                         % (tag, k))
            continue
        kv[k] = v
    if not kv:
        probs.append("%s 块里一行数据都没有" % tag)
        return None, probs
    return kv, probs


def sha256_file(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ival(kv, key):
    """静默取值（失败返回 None）—— 用于**重复消费**同一个键的判据，
    避免 `_num` 二次 append 出重复的违规行。"""
    try:
        return int(kv[key])
    except (KeyError, ValueError):
        return None


def _num(kv, key, probs, integer=True):
    """数值键转换。转换失败 ⇒ 红（不许静默当 0）。"""
    if key not in kv:
        return None
    raw = kv[key]
    if raw == "-":
        probs.append("W1 键 %r 是占位 `-`，但它是必需数值键" % key)
        return None
    try:
        return int(raw) if integer else float(raw)
    except ValueError:
        probs.append("W1 键 %r 的值 %r 不是%s"
                     % (key, raw, "整数" if integer else "数"))
        return None


def _delta_verdict(declared, key, va, vb, tail=""):
    """W5 的「已声明变化」裁决。返回 problems 列表（可能为空）。

    R87 起，W5 不再无条件要求「与 R81 逐位全等」—— 门自己的措辞早就留了出口：
    「或分析逻辑真的变了，那就必须写出原因」。出口落在登记表的 KERNEL-DELTA 块。

    ⚠ 出口必须**三向**都有对手方，否则它只是把「逐位全等」换成一张通行证：
      * 两侧相等却仍被登记 ⇒ **陈旧登记**（变化已不存在，登记该撤）
      * 两侧不等却没登记   ⇒ **未登记**（必须写出原因）
      * 登记了但数字或原因对不上 ⇒ 登记与实测不符 / 空原因
    """
    probs = []
    d = declared.get(key) if declared else None
    try:
        diff = "%+d" % (va - vb)
    except TypeError:
        diff = "n/a"
    if va == vb:
        if d is not None:
            probs.append(
                "W5 %s 被登记成「已声明变化」，但两侧都是 %s —— **陈旧登记**"
                "（变化已不存在，登记必须一起撤；否则这张表会退化成"
                "「永远可以解释任何差异」的通行证）%s" % (key, va, tail))
        return probs
    if d is None:
        probs.append(
            "W5 %s: 本轮 %s != R81 基线 %s（差 %s）—— **未登记**。"
            "`matlabc.py` 自 R81 起若只有纯文档改动，计数器本应逐位复现，"
            "不等说明解析**非确定**；若分析逻辑**真的**变了，就必须在 %s 的"
            " `%s` 块里写下原因（键 `%s.base`/`%s.cur`/`%s.reason`）%s"
            % (key, va, vb, diff, DOC, DELTA_OPEN, key, key, key, tail))
        return probs
    db, dc, rn = d.get("base"), d.get("cur"), d.get("reason")
    dbn, dcn = _ival(d, "base"), _ival(d, "cur")
    if dbn is None or dcn is None:
        probs.append("W5 %s 登记的 base/cur 不是整数：%r / %r" % (key, db, dc))
    elif dbn != vb or dcn != va:
        probs.append("W5 %s 登记的是 %s→%s，实测 %s→%s —— 登记与实测不符"
                     "（数字现算，不许手抄）%s" % (key, db, dc, vb, va, tail))
    if not (rn or "").strip():
        probs.append("W5 %s 变了（%s→%s）但 `%s.reason` 是空的 —— "
                     "「写出原因」是这条的出口，空原因等于没写%s"
                     % (key, vb, va, key, tail))
    return probs


# --------------------------------------------------------------- 判据
def audit(kv, doc_text, matlabc_sha=None, matlabc_bytes=None,
          unknown_doc_denominator=None, readmes=None, declared=None,
          artifacts=None):
    """返回 problems 列表（空 = 全过）。所有外部事实都可注入 ⇒ 可两向自证。

    `readmes` = {显示名: 文本}；为 None 表示「这一条未行使」（自证的多数用例）。
    `declared` = {读数键: {"base":…, "cur":…, "reason":…}}（R87）；为 None 时
    W5 退化为原始的「逐位全等」判据 —— 即「这一条未行使」。
    `artifacts` = {产物名: {"bytes": int, "sha256": 前 16 位}}（R95/W7）。
    **不存在的产物不进字典**（= 该条未行使）；为 None 时 W7 整体未行使。
    """
    probs = []

    # ---- W1 键完备 ----
    missing = [k for k in REQUIRED if k not in kv]
    if missing:
        probs.append("W1 缺必需键 %d 个：%s" % (len(missing), ", ".join(missing)))
    # 两档分母键必须存在（单独点名，便于定位）
    for k in ("corpus.files_c_family", "corpus.files_all_ext"):
        if k not in kv:
            probs.append("W3 缺分母键 %r" % k)

    # 直方图键（arm_c.kind.*）—— 至少要有一个，否则恒等式是空集上恒真
    kinds = [k for k in kv if k.startswith("arm_c.kind.")]
    base_kinds = [k for k in kv if k.startswith("base_c.kind.")]
    if not kinds:
        probs.append("W4 arm_c.kind.* 一个都没有 —— 空集上 `Σkinds == heuristics` 恒真"
                     "（§4h-2：反例不能是空集）")
    if not base_kinds:
        probs.append("W5 base_c.kind.* 一个都没有 —— 基线直方图缺失则无法逐类对照")

    # ---- W2 出处钉住 ----
    if "provenance.matlabc_sha256" in kv and matlabc_sha is not None:
        if kv["provenance.matlabc_sha256"] != matlabc_sha:
            probs.append(
                "W2 读数陈旧：登记表记的 matlabc.py sha256=%s，当前=%s"
                "（先重跑 `python _r82/probe_kernel_r84.py --arms c asm`，"
                "再用实测值改本表；只改表不改跑 = 把一个没跑过的数写成跑过的）"
                % (kv["provenance.matlabc_sha256"][:16], matlabc_sha[:16]))
    if "provenance.matlabc_bytes" in kv and matlabc_bytes is not None:
        nb = _num(kv, "provenance.matlabc_bytes", probs)
        if nb is not None and nb != matlabc_bytes:
            probs.append("W2 provenance.matlabc_bytes=%d，当前 matlabc.py=%d"
                         % (nb, matlabc_bytes))

    # W2 出处三件套（sha256 / 字节数 / HEAD）之外还必须有**口径**：
    # 同一个分析器、同一棵树，仅换子进程 cwd 约定就会产出两个**都对**的读数
    # （R75 的 `661 s / 10.8 GB`（cwd=REPO）与 R81 的 `793.4 s / 13.1 GB`（cwd=CORPUS）），
    # 差异来自 `rel` 由 basename 变成真相对路径。只钉 sha256 与语料路径**分辨不出**这两者，
    # 所以约定本身也必须落表（L85：没有对手方的指针，指空了也看不出来）。
    cwd_conv = kv.get("provenance.cwd_convention", "")
    if not cwd_conv or cwd_conv == "-":
        probs.append("W2 provenance.cwd_convention 为空/占位 —— "
                     "缺口径的读数与另一口径的读数长得一模一样，无法分辨"
                     "（须写出子进程的工作目录约定，如 `cwd=corpus`）")

    corpus = kv.get("corpus.path", "")
    if not corpus:
        probs.append("W3 corpus.path 为空 —— 分母不许不指名")
    else:
        if "linux-" not in corpus or "corpus" not in corpus.replace("\\", "/"):
            probs.append("W3 corpus.path=%r 没有指到**具名子树**"
                         "（须形如 ...\\corpus\\linux-<版本>；"
                         "按工作区顶层目录数出来的分母是混口径）" % corpus)

    # ---- W3 两档分母并列，且不许合一 ----
    fam = _num(kv, "corpus.files_c_family", probs)
    alx = _num(kv, "corpus.files_all_ext", probs)
    if fam is not None and fam <= 0:
        probs.append("W3 corpus.files_c_family=%d 必须 > 0" % fam)
    if alx is not None and alx <= 0:
        probs.append("W3 corpus.files_all_ext=%d 必须 > 0" % alx)
    if fam is not None and alx is not None and fam == alx:
        probs.append("W3 两个分母相等（%d）—— C 族扩展名与全部扩展名不可能同值；"
                     "相等说明有一个口径被悄悄换掉了" % fam)
    if fam is not None and alx is not None and fam > alx:
        probs.append("W3 C 前端分母 %d > 另一档分母 %d —— 两档各有独立口径"
                     "（扩展名集合不同，**不是**子集关系），出现这个方向说明"
                     "其中一档被换成了另一个集合；请把两档的口径都重新现算"
                     % (fam, alx))
    # 第三档分母：**本仓 + 对标 OSS**（与内核是**不同语料**）。
    # 三档并列的意义：任何一处只写一个数，读者就会拿错语料的分母去解释读数；
    # 第三档若与内核某一档同值，说明有一档是被**复制**出来的而不是各自数出来的。
    ros = _num(kv, "corpus.files_repo_plus_oss", probs)
    if ros is not None and ros <= 0:
        probs.append("W3 corpus.files_repo_plus_oss=%d 必须 > 0" % ros)
    if ros is not None and fam is not None and alx is not None and ros in (fam, alx):
        probs.append("W3 corpus.files_repo_plus_oss=%d 与内核分母同值 —— "
                     "两者是**不同语料**，同值说明有一档被复制而非各自数出" % ros)

    # ---- W4 恒等式 ----
    af = _num(kv, "arm_c.files", probs)
    if af is not None and fam is not None and af != fam:
        probs.append("W4 C 前端实际分析文件数 %d != 分母 %d"
                     "（两者必须相等：这正是「分母是不是真的被分析了」）" % (af, fam))
    ah = _num(kv, "arm_c.heuristics", probs)
    if kinds and ah is not None:
        s = 0
        ok = True
        for k in kinds:
            v = _num(kv, k, probs)
            if v is None:
                ok = False
            else:
                s += v
        if ok and s != ah:
            probs.append("W4 Σarm_c.kind.* = %d != arm_c.heuristics = %d（差 %+d）"
                         " —— 汇总与明细是同一条对账的两半" % (s, ah, ah - s))
    for key in ("arm_c.rc", "arm_asm.rc"):
        v = _num(kv, key, probs)
        if v is not None and v != 0:
            probs.append("W4 %s=%d —— 全树跑必须 rc=0（非零说明没跑完/崩了）"
                         % (key, v))
    for key in ("arm_c.json_bytes", "arm_asm.json_bytes", "arm_c.funcs",
                "arm_c.edges", "arm_c.lines", "arm_asm.files"):
        v = _num(kv, key, probs)
        if v is not None and v <= 0:
            probs.append("W4 %s=%d 必须 > 0（0 常见于「什么都没分析却很快」）"
                         % (key, v))

    # ---- W5 与基线在「与时钟无关的计数器」上逐位相同 + 跨文档分母一致 ----
    for arm in ("c", "asm"):
        keys = ARM_KEYS if arm == "c" else ASM_KEYS
        for k in keys:
            if k in CLOCK_KEYS:
                continue
            a, b = ("arm_%s.%s" % (arm, k)), ("base_%s.%s" % (arm, k))
            if a not in kv or b not in kv:
                continue
            va, vb = _num(kv, a, probs), _num(kv, b, probs)
            if va is None or vb is None:
                continue
            probs.extend(_delta_verdict(declared, "arm_%s.%s" % (arm, k),
                                        va, vb))
    if base_kinds and "base_c.heuristics" in kv:
        bh = _ival(kv, "base_c.heuristics")
        if bh is not None:
            vals = [_ival(kv, k) for k in base_kinds]
            if all(v is not None for v in vals) and sum(vals) != bh:
                probs.append("W5 Σbase_c.kind.* = %d != base_c.heuristics = %d"
                             % (sum(vals), bh))

    # W5 分解必须**逐类**对照，不能只比总和：
    # 「+1 / −1」这种一好一坏顶替会让总和不变，只比总和时它是**静默**的（§4q-1）。
    # 这一条由本门自己的自证抓出来 —— 第一版只比总和，那条反例没红。
    ak = dict((k[len("arm_c.kind."):], _ival(kv, k)) for k in kinds)
    bk = dict((k[len("base_c.kind."):], _ival(kv, k)) for k in base_kinds)
    for name in sorted(set(ak) | set(bk)):
        if ak.get(name) != bk.get(name):
            probs.extend(_delta_verdict(
                declared, "arm_c.kind.%s" % name, ak.get(name), bk.get(name),
                tail="（总和相同也照样红 —— 只比总和会让「一好一坏顶替」"
                     "静默通过）"))

    if unknown_doc_denominator is not None:
        v = _num(kv, "crossdoc.unknown_sites_files", probs)
        if v is not None and v != unknown_doc_denominator:
            probs.append(
                "W5 跨文档分母不一致：本表 %d，docs/UNKNOWN_SITES.md 记 %d"
                "（同一个量两条路径，必须一起改）"
                % (v, unknown_doc_denominator))

    # W5 跨文档：两侧 README 都必须把全树读数的**唯一事实源**指出来。
    # 反过来的形态本仓已实测过 —— README 里散着 R75 的 `661 s / 10.8 GB`，
    # 登记表里是 R81 的 `793.4 s / 13.1 GB`，两个都**不是错的**，
    # 但读者无法知道该信哪一个；指针缺失时这是**静默**的（L85）。
    if readmes is not None:
        for label in sorted(readmes):
            if SNAPSHOT_POINTER not in readmes[label]:
                probs.append(
                    "W5 %s 没有指向 %s —— 缺少唯一事实源指针时，"
                    "两个都对的读数无法分辨；请在 README 里补上指向该登记表的一行"
                    % (label, SNAPSHOT_POINTER))

    # KERNEL-DELTA 的**幽灵登记**：登记了本轮根本不存在的读数（键名拼错，或该
    # 读数已从块里消失）⇒ 红。缺登记由上面的循环判（「未登记」）。
    #
    # ⚠ `live` 必须用「块里真实存在的 `arm_*` 键」来算，**不能**拿 `ARM_KEYS` 现拼：
    # 直方图键（`arm_c.kind.*`）不在 `ARM_KEYS` 里，第一版用 `ARM_KEYS` 拼，
    # 结果把**每一个**直方图登记都判成了幽灵 —— 门当场报「登记了本轮不存在的读数」
    # 三条（其中两条其实存在）。**判据自己的口径也要有对手方。**
    if declared:
        live = set()
        for _k in kv:
            if not (_k.startswith("arm_c.") or _k.startswith("arm_asm.")):
                continue
            if _k.rsplit(".", 1)[-1] in CLOCK_KEYS:
                continue
            live.add(_k)
        ghost = sorted(set(declared) - live)
        if ghost:
            probs.append("W5 KERNEL-DELTA 登记了本轮不存在的读数 %r —— "
                         "幽灵登记（键名拼错，或该读数已不在块里）" % (ghost,))

    # ---- W7：产物**现算**核对（R95）----
    # 见模块 docstring 的第五个形态。四条纪律：
    #   * 空集必须红（反例不能是空集，§4h-2）；
    #   * 「表写 `-`」与「磁盘没有」是**两个相反的方向**，都要有对手方；
    #   * 缺产物 ⇒ 该条**未行使**（产物在仓外，新克隆里没有 `_kernel/`），
    #     但调用方**必须说出来**，绝不静默当成「对得上」；
    #   * 键名拼错（`sha1` / `size`）是一类**静默失效**，必须单独点名 ——
    #     否则那条核对会因为「根本没这条键」而永远不跑。
    a_keys = [k for k in kv if k.startswith("artifact.")]
    a_core = [k for k in a_keys if k.rsplit(".", 1)[-1] in ("bytes", "sha256")]
    a_odd = [k for k in a_keys if k != "artifact.dir" and k not in a_core]
    if a_odd:
        probs.append("W7 artifact.* 里有未登记字段 %r —— 只认 `.dir` / `.bytes` / "
                     "`.sha256`（拼错的键会让那一份产物的核对照样静默失效）"
                     % (sorted(a_odd)[:4],))
    if not a_core:
        probs.append("W7 一份产物的 bytes/sha256 都没有 —— 空集上 `现算 == 表` "
                     "恒真（反例不能是空集）")
    else:
        a_names = sorted(set(k[len("artifact."):].rsplit(".", 1)[0]
                             for k in a_core))
        if not (kv.get("artifact.dir") or "").strip():
            probs.append("W7 缺 `artifact.dir` —— 产物路径无处可寻，"
                         "下面每一份的现算核对都会静默失效")
        for nm in a_names:
            kb = kv.get("artifact.%s.bytes" % nm)
            ks = kv.get("artifact.%s.sha256" % nm)
            if (kb is None) != (ks is None):
                probs.append("W7 产物 %s 的 bytes/sha256 必须**成对**出现（缺 %s）"
                             % (nm, "bytes" if kb is None else "sha256"))
                continue
            if (kb == "-") != (ks == "-"):
                probs.append("W7 产物 %s 的「不在」必须**两列同时**写 `-`"
                             "（现为 bytes=%r / sha256=%r）" % (nm, kb, ks))
                continue
            disk = (artifacts or {}).get(nm)
            if ks == "-":
                if disk is not None:
                    probs.append("W7 表说产物 %s「不在」（`-`），磁盘上却有一份"
                                 "（%d B）—— 表被手改，或产物被补上而没重生成表"
                                 % (nm, disk.get("bytes", -1)))
                continue
            if disk is None:
                continue          # 未行使：仓外产物不在本机（main() 会打印出来）
            nb = _num(kv, "artifact.%s.bytes" % nm, probs)
            if nb is not None and nb != disk.get("bytes"):
                probs.append("W7 产物 %s 字节数不符：表 %d，磁盘现算 %s —— "
                             "产物在表生成之后被替换（或表被手改）"
                             % (nm, nb, disk.get("bytes")))
            if ks != disk.get("sha256"):
                probs.append("W7 产物 %s sha256 不符：表 %s，磁盘现算 %s"
                             % (nm, ks[:16], str(disk.get("sha256"))[:16]))
    return probs


# --------------------------------------------------------------- 跨文档分母
# 为什么要**两条**路径：清单正文里第一处「N 个文件」会随小节顺序变，
# 而「扫描覆盖了多少文件」是**语义明确的**那一档。所以优先取语义行，
# 其余情况退回通用写法 —— 两条路径都取不到时返回 None（调用方**说出来**），
# 绝不静默返回 0（0 会让跨文档对账在空分母上恒真，§4h-2）。
_RE_SEEN = re.compile(
    r"扫描文件\s*seen\s*/\s*scanned\s*/\s*skipped\s*\|\s*(\d[\d,]*)")
_RE_ANY_FILE = re.compile(r"(\d[\d,]*)\s*(?:个)?\s*文件")


def denominator_from_text(text):
    """从清单正文取分母；取不到 ⇒ None。"""
    m = _RE_SEEN.search(text or "") or _RE_ANY_FILE.search(text or "")
    return int(m.group(1).replace(",", "")) if m else None


def _unknown_doc_denominator(path):
    """跨文档分母：从 UNKNOWN_SITES.md 抽「这一遍扫描覆盖了多少文件」。"""
    if not os.path.isfile(path):
        return None
    return denominator_from_text(io.open(path, encoding="utf-8",
                                         errors="replace").read())


# --------------------------------------------------------------- 流程登记（W6）
# 为什么「流程」也值得一条判据：它此前只活在 8 个脚本的 docstring 里，散在
# `_kernel/`（R75–R81）与 `_r82/`（R84）两棵**仓外**树 ⇒「有哪几站、该跑哪一代」
# **没有任何对手方**（L85）。实测代价：盘上同时躺着三代驱动，其中一代再跑一次
# 就会**就地覆盖对照基线**。
PIPELINE_OPEN = "<!-- KERNEL-PIPELINE v1 -->"
PIPELINE_CLOSE = "<!-- /KERNEL-PIPELINE -->"
# R87：第三个块 —— 「与 R81 的**已声明变化**」。W5 的原始断言是「逐位全等」，
# 而门自己的措辞早就留了出口：「或分析逻辑真的变了，那就必须写出原因」。
# 这个块就是那个「原因」的唯一事实源；格式与另外两块一致（`键 | 值`，
# 值内不许出现 `|`），所以**同一个解析器**（parse_block）照样服务它：
#     arm_c.funcs.base    | 743518
#     arm_c.funcs.cur     | 743509
#     arm_c.funcs.reason  | C 前端修掉 GNU 属性说明符缺陷族：7 处假定义…
DELTA_OPEN = "<!-- KERNEL-DELTA v1 -->"
DELTA_CLOSE = "<!-- /KERNEL-DELTA -->"
PIPELINE_DOC = os.path.join("docs", "KERNEL_RUN.md")

# 闭集的意义不是分类癖：**开放集合上，拼错的 role 会被当成一个新类型静静收下**
# （同 §4z-11 的归一撞车）。闭集让它当场红。
# `probe` = **独立口径的探针**（量的是**另一件事**，不与主读数竞争同一个产物）：
# 把它混进 `analyze`，W6b「恰好一个 current 分析器」就会被它顶掉 ——
# 而它并不是「另一个可以替代当前驱动的选择」，是「另一条并行的量」。
# 角色分不开，「该跑哪个」这条判据就只是一句好听话。
PIPELINE_ROLES = ("source", "analyze", "probe", "derive", "present",
                  "register", "gate")
PIPELINE_STATUS = ("current", "superseded", "auxiliary")
PIPELINE_FIELDS = ("path", "role", "in", "out", "status")
STATION_RE = re.compile(r"^pipeline\.station\.(\d+)$")


def _pfields(val):
    """`path=X;role=Y` -> (fields, malformed, duplicated)。

    三条都要报出来：缺 `=`、键重复（重复会静默折叠 ⇒ 与「只写了一个」逐字相同）。
    """
    fields, mal, dup = {}, [], []
    for part in (val or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            mal.append(part)
            continue
        k, _eq, v = part.partition("=")
        k, v = k.strip(), v.strip()
        if k in fields:
            dup.append(k)
        fields[k] = v
    return fields, mal, dup


def _tokens(v):
    """`corpus,baseline-r81` -> ['corpus','baseline-r81']；`-` / 空 -> []。"""
    if not v or v == "-":
        return []
    return [t.strip() for t in v.split(",") if t.strip()]


def audit_pipeline(pkv, repo_root=None):
    """返回 (problems, info)。所有外部事实（仓库根）可注入 ⇒ 可两向自证。"""
    probs = []
    if pkv is None:
        return ["W6 流程块不可解析（缺输入 ⇒ 红）"], {}

    keys = sorted(k for k in pkv if STATION_RE.match(k))
    if not keys:
        probs.append("W6a 一个 `pipeline.station.NN` 都没有 —— "
                     "空集上「每站都合法」恒真（§4h-2：反例不能是空集）")
    stations = []
    for k in keys:
        f, mal, dup = _pfields(pkv[k])
        for bad in mal:
            probs.append("W6a %s 里 %r 缺 `=`（字段是 `键=值`，用 `;` 分隔）"
                         % (k, bad))
        for d in dup:
            probs.append("W6a %s 里字段 %r 重复（重复会静默折叠成一个 ⇒ 必须红）"
                         % (k, d))
        for fld in PIPELINE_FIELDS:
            v = f.get(fld)
            if v in (None, "") or (v == "-" and fld not in ("in", "out")):
                probs.append("W6a %s 缺字段 %r（每站必须有 %s；只有 in/out 允许 `-`）"
                             % (k, fld, "/".join(PIPELINE_FIELDS)))
        if f.get("role") and f["role"] not in PIPELINE_ROLES:
            probs.append("W6a %s role=%r 不在闭集 %s"
                         % (k, f["role"], list(PIPELINE_ROLES)))
        if f.get("status") and f["status"] not in PIPELINE_STATUS:
            probs.append("W6a %s status=%r 不在闭集 %s"
                         % (k, f["status"], list(PIPELINE_STATUS)))
        needs_why = ((f.get("status") and f["status"] != "current")
                     or f.get("role") == "probe")
        if needs_why and not f.get("why"):
            probs.append("W6a %s（role=%s status=%s）没写 why —— 退役/辅助站不写理由，"
                         "下一个人不知道它还能不能用；`probe` 不写理由，读者分不清"
                         "它是「另一条并行的量」还是「被误分类的第二个主驱动」"
                         % (k, f.get("role"), f.get("status")))
        stations.append((int(STATION_RE.match(k).group(1)), k, f))
    stations.sort(key=lambda t: t[0])

    # ---- W6d 分母自证：分母必须等于明细（偏小的分母比不报更坏，§4v-1）----
    st = _ival(pkv, "pipeline.stations")
    if st is None:
        probs.append("W6d 缺 pipeline.stations（站数分母）—— 没有分母就无法自证覆盖")
    elif st != len(stations):
        probs.append("W6d pipeline.stations=%d 但块里实际有 %d 站 —— "
                     "分母与明细必须相等（不等时读者只会信分母）" % (st, len(stations)))

    # ---- W6b 恰好一个 current 分析器（「该跑哪个」的对手方）----
    cur = [(k, f) for (_n, k, f) in stations
           if f.get("role") == "analyze" and f.get("status") == "current"]
    if len(cur) != 1:
        probs.append("W6b `role=analyze` 且 `status=current` 的站有 %d 个（要求恰好 1 个）"
                     " —— 0 个 ⇒ 流程没有分析器；2 个以上 ⇒ 没人知道该跑哪一代"
                     % len(cur))
    else:
        want = pkv.get("pipeline.analyze_current")
        got = os.path.splitext(os.path.basename(cur[0][1].get("path", "")))[0]
        if not want:
            probs.append("W6b 缺 pipeline.analyze_current —— 当前驱动必须被点名")
        elif want != got:
            probs.append("W6b pipeline.analyze_current=%r 与那唯一 current 分析器 "
                         "%r 不符" % (want, got))

    # ---- W6c 产物链拓扑：每站的 in 必须已被**前序**站的 out 产出 ----
    produced, broken = set(), []
    for (_n, k, f) in stations:
        for t in _tokens(f.get("in")):
            if t not in produced:
                broken.append((k, t))
        produced.update(_tokens(f.get("out")))
    for k, t in broken:
        probs.append("W6c %s 的输入 %r 没有任何前序站产出它 —— 这条流程是**断的**"
                     "（站表可以随便列，链不会）" % (k, t))
    declared = pkv.get("pipeline.chain_ok")
    if not broken and declared != "1":
        probs.append("W6c 链重算后是通的，但 pipeline.chain_ok=%r ≠ 1 —— "
                     "声明必须被它所在的正文支持（否则读的人只会信声明）" % declared)
    if broken and declared == "1":
        probs.append("W6c pipeline.chain_ok=1，但重算发现 %d 处断链" % len(broken))

    # ---- W6e 仓内落点必须存在（仓外刻意「只计数、不裁决」，理由见 docstring）----
    arts = _tokens(pkv.get("pipeline.repo_artifacts"))
    if not arts:
        probs.append("W6e pipeline.repo_artifacts 为空集 —— "
                     "空集上「每个落点都存在」恒真（§4h-2）；"
                     "而它同时是「仓内可裁决面」的全部，空集等于这一族没行使")
    else:
        root = repo_root or _ROOT
        miss = [a for a in arts if not os.path.exists(os.path.join(root, a))]
        if miss:
            probs.append("W6e 仓内落点缺失 %d/%d：%s —— "
                         "站表里有一站是**幻影**（L85：指针指空了看不出来）"
                         % (len(miss), len(arts), ", ".join(miss)))

    outside = [k for (_n, k, f) in stations
               if re.match(r"^[A-Za-z]:[\\/]", f.get("path", ""))]
    info = {"stations": len(stations), "outside_repo": len(outside),
            "artifacts": len(arts), "broken": len(broken),
            "current": (cur[0][1].get("path") if len(cur) == 1 else None)}
    return probs, info


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    doc_p = os.path.join(_ROOT, DOC)
    mc_p = os.path.join(_ROOT, MATLABC)
    unk_p = os.path.join(_ROOT, UNKNOWN_DOC)

    probs = []
    if not os.path.isfile(doc_p):
        print("check_kernel_snapshot: 缺输入 —— 登记表不在 %s ⇒ 红" % DOC)
        return 2
    if not os.path.isfile(mc_p):
        print("check_kernel_snapshot: 缺输入 —— %s 不在 ⇒ 红" % MATLABC)
        return 2

    text = io.open(doc_p, encoding="utf-8", errors="replace").read()
    kv, parse_probs = parse_block(text)
    probs.extend(parse_probs)
    if kv is None:
        for p in probs:
            print("  - " + p)
        print("check_kernel_snapshot: FAILED（块不可解析）")
        return 2

    unk = _unknown_doc_denominator(unk_p)
    # 两侧 README 原文都要读进来（缺文件 ⇒ 空串 ⇒ W5 自然红）。
    readmes = {}
    for _name in ("README.md", "README_CN.md"):
        _p = os.path.join(_ROOT, _name)
        readmes[_name] = (io.open(_p, encoding="utf-8", errors="replace").read()
                          if os.path.isfile(_p) else "")
    # ---- 第三块：与 R81 的「已声明变化」（R87）----
    # 缺块 ⇒ 红（与流程块同一个口径：登记表是生成器产出的，生成器一定会写这块；
    # 不在说明有人手删或生成器坏了，绝不当作「没有变化」而静默放宽 W5）。
    declared, dprobs = parse_block(text, DELTA_OPEN, DELTA_CLOSE, tag="W5d")
    probs.extend(dprobs)
    declared_map = None
    if declared:
        declared_map = {}
        for _k, _v in declared.items():
            if _k.endswith(".reason"):
                declared_map.setdefault(_k[:-len(".reason")], {})["reason"] = _v
            elif _k.endswith(".base") or _k.endswith(".cur"):
                _b, _, _f = _k.rpartition(".")
                declared_map.setdefault(_b, {})[_f] = _v
            else:
                probs.append("W5d KERNEL-DELTA 键 %r 既不是 `.base`/`.cur` 也不是 "
                             "`.reason`" % (_k,))
    # ---- W7：仓外产物由门**自己现算**核对（缺产物 ⇒ 该条未行使，但要说出来）----
    artifacts = {}
    _adir = (kv.get("artifact.dir") or "").strip()
    if _adir and _adir != "-":
        for _nm in ARTIFACT_NAMES:
            _ap = os.path.join(_adir, _nm)
            if os.path.isfile(_ap):
                artifacts[_nm] = {"bytes": os.path.getsize(_ap),
                                  "sha256": sha256_file(_ap)[:16]}
    if artifacts:
        print("  产物现算核对：%d 份（%s）"
              % (len(artifacts), ", ".join(sorted(artifacts))))
    else:
        print("  [跳过] W7 现算核对未行使 —— 本机没有仓外产物"
              "（artifact.dir=%s）" % (_adir or "(缺)"))

    probs.extend(audit(kv, text, matlabc_sha=sha256_file(mc_p),
                       matlabc_bytes=os.path.getsize(mc_p),
                       unknown_doc_denominator=unk, readmes=readmes,
                       declared=declared_map, artifacts=artifacts))

    # ---- W6：流程块（**同一个文件里的第二个围栏块**）----
    # 「缺输入必须能红」：流程块不在 ⇒ rc=2，绝不当成「没有流程要核」而静默放行。
    pkv, pprobs = parse_block(text, PIPELINE_OPEN, PIPELINE_CLOSE, tag="W6")
    if pkv is None:
        print("check_kernel_snapshot: 缺输入 —— 流程块 %s 不在 %s ⇒ 红"
              % (PIPELINE_OPEN, PIPELINE_DOC))
        for p in pprobs:
            print("  - " + p)
        return 2
    probs.extend(pprobs)
    p6, pinfo = audit_pipeline(pkv, repo_root=_ROOT)
    probs.extend(p6)

    if unk is None:
        print("  [跳过] docs/UNKNOWN_SITES.md 里抽不到「N 文件」分母 ⇒ 跨文档那一条未行使")
    if pinfo:
        print("  流程读数：%d 站（其中仓外 %d 个 —— 存在性**刻意不裁决**，"
              "新克隆里没有 `_kernel/`）；仓内落点 %d 个；当前驱动 %s"
              % (pinfo["stations"], pinfo["outside_repo"], pinfo["artifacts"],
                 pinfo["current"] or "?"))
        if pinfo["outside_repo"] == 0:
            print("  [注意] 站表里一个仓外路径都没有 —— 若这是真的，"
                  "请复核「仓外不裁决」这条口径是否还需要")
    for p in probs:
        print("  - " + p)
    if probs:
        print("check_kernel_snapshot: FAILED（%d 条；判据族 %s）"
              % (len(probs), ROW_SIGNATURE))
        return 1
    print("check_kernel_snapshot: OK（全树规模读数：出处+口径钉住 + 两档分母并列 + "
          "汇总↔明细恒等式 + 与 R81 基线逐位/逐类对照（R87：差异必须登记、"
          "写明原因，陈旧登记与幽灵登记同样红）+ 唯一事实源指针；"
          "流程登记：站表形状 + 恰一个 current 驱动 + 产物链拓扑 + 仓内落点存在；"
          "产物现算核对（R95：表 ⇄ 磁盘，缺产物即未行使 + 空集必红）；"
          "判据族 %s）" % ROW_SIGNATURE)
    return 0


# --------------------------------------------------------------- 自证
def _mkdoc(over=None):
    """造一份**最小但合法**的块。只用于 --selftest，绝不写盘。"""
    kv = {
        "provenance.matlabc_sha256": "a" * 64,
        "provenance.matlabc_bytes": "100",
        "provenance.git_head": "deadbeef",
        "provenance.cwd_convention": "cwd=corpus",
        "corpus.path": r"E:\x\corpus\linux-9.9.9",
        "corpus.files_c_family": "10",
        "corpus.files_all_ext": "12",
        "corpus.bytes": "1000",
        "corpus.files_repo_plus_oss": "3",
        "baseline.path": r"E:\x\r81\AGG_r81.json",
        "baseline.sha256": "b" * 64,
        "crossdoc.unknown_sites_files": "3",
        # R95/W7：产物条目（`artifact.dir` + 每份产物的 bytes/sha256）。
        # 自证里多数用例把 `artifacts` 留成 None ⇒ W7 未行使；专项用例注入磁盘侧。
        "artifact.dir": r"E:\x\_kernel\r84",
        "artifact.kernel_c_summary.json.bytes": "11355506",
        "artifact.kernel_c_summary.json.sha256": "c" * 16,
        "artifact.kernel_asm_summary.json.bytes": "486229",
        "artifact.kernel_asm_summary.json.sha256": "d" * 16,
        "artifact.kernel_callgraph.json.bytes": "4358990",
        "artifact.kernel_callgraph.json.sha256": "e" * 16,
        "arm_c.kind.alpha": "7",
        "arm_c.kind.beta": "3",
        "base_c.kind.alpha": "7",
        "base_c.kind.beta": "3",
    }
    for pre in ("arm_c.", "base_c."):
        for k, v in (("files", 10), ("lines", 100), ("funcs", 20), ("edges", 30),
                     ("unresolved", 5), ("includes", 40), ("heuristics", 10),
                     ("peak_mb", 1.0), ("seconds", 2.0), ("rc", 0),
                     ("json_bytes", 500)):
            kv.setdefault(pre + k, str(v))
    for pre in ("arm_asm.", "base_asm."):
        for k, v in (("files", 10), ("lines", 100), ("rc", 0),
                     ("seconds", 2.0), ("peak_mb", 1.0), ("json_bytes", 500)):
            kv.setdefault(pre + k, str(v))
    if over:
        for k, v in over.items():
            if v is None:
                del kv[k]
            else:
                kv[k] = v
    rows = "\n".join("%s | %s" % (k, kv[k]) for k in sorted(kv))
    return "%s\n```text\n%s\n```\n%s\n" % (BLOCK_OPEN, rows, BLOCK_CLOSE)


def _selftest():
    bad = good = 0
    fails = []

    def expect(name, problems, want_red):
        nonlocal bad, good
        is_red = bool(problems)
        if is_red == want_red:
            if want_red:
                bad += 1
            else:
                good += 1
            print("  [%s] %s -> %s" % ("反例" if want_red else "正例", name,
                                       "抓到" if want_red else "放行"))
        else:
            fails.append(name)
            print("  [!!] %s -> %s" % (name, "应为红却放行" if want_red else "应为绿却红"))
            if problems:
                for p in problems[:2]:
                    print("        " + p)

    # 正例：最小合法块必须放行
    text = _mkdoc()
    kv, pp = parse_block(text)
    expect("W1 最小合法块", pp + (audit(kv, text, "a" * 64, 100, 3) if kv else []),
           False)

    # 反例 W1：缺块 / 重号 / 键重复 / 空值 / 分隔符数量错
    for name, t in (
        ("W1 没有块", "正文里没有块\n"),
        ("W1 开标记重号", text + BLOCK_OPEN + "\n"),
        ("W1 键重复", _mkdoc().replace("corpus.bytes | 1000",
                                       "corpus.bytes | 1000\ncorpus.bytes | 999")),
        ("W1 值为空", _mkdoc().replace("corpus.bytes | 1000", "corpus.bytes | ")),
        ("W1 分隔符两个", _mkdoc().replace("corpus.bytes | 1000",
                                           "corpus.bytes | 1 | 0")),
    ):
        kv2, pp2 = parse_block(t)
        expect(name, pp2 if kv2 is None else pp2 + audit(kv2, t, "a" * 64, 100, 3),
               True)

    # 反例 W1：缺必需键（只删一个）
    kv2, pp2 = parse_block(_mkdoc())
    kv2.pop("arm_c.kind.beta")
    expect("W1 缺一个必需键（arm_c.kind.beta）",
           pp2 + audit(kv2, text, "a" * 64, 100, 3), True)

    # 反例 W2：sha 不一致（陈旧）
    kv2, _ = parse_block(text)
    expect("W2 sha256 陈旧", audit(kv2, text, "c" * 64, 100, 3), True)

    # 反例 W2：字节数不一致
    kv2, _ = parse_block(text)
    expect("W2 matlabc_bytes 不一致", audit(kv2, text, "a" * 64, 101, 3), True)

    # 反例 W3：分母合一 / 反向 / 不指名子树
    kv2, _ = parse_block(_mkdoc({"corpus.files_all_ext": "10"}))
    expect("W3 两个分母相等（口径被换掉）", audit(kv2, text, "a" * 64, 100, 3), True)
    kv2, _ = parse_block(_mkdoc({"corpus.files_c_family": "13"}))
    expect("W3 两档分母方向异常（C 前端 > 另一档）",
           audit(kv2, text, "a" * 64, 100, 3), True)
    kv2, _ = parse_block(_mkdoc({"corpus.path": r"E:\matlabc\_kernel"}))
    expect("W3 分母不指名子树（混口径目录）",
           audit(kv2, text, "a" * 64, 100, 3), True)

    # 反例 W4：直方图之和与汇总不等
    kv2, _ = parse_block(_mkdoc({"arm_c.kind.alpha": "9"}))
    expect("W4 Σkinds != heuristics（求和本身被破坏）",
           audit(kv2, text, "a" * 64, 100, 3), True)
    # 反例 W4/W5：+1 / −1 顶替 —— **总和不变**，只有逐类对照才抓得到
    kv2, _ = parse_block(_mkdoc({"arm_c.kind.alpha": "8", "arm_c.kind.beta": "2"}))
    expect("W5 一好一坏顶替（总和不变、分解变了）",
           audit(kv2, text, "a" * 64, 100, 3), True)
    # 正例 W5：分解逐类相同 ⇒ 必须放行
    kv2, _ = parse_block(_mkdoc())
    expect("W5 分解逐类相同", audit(kv2, text, "a" * 64, 100, 3), False)
    # 反例 W4：空直方图（恒等式在空集上恒真）
    kv2, _ = parse_block(_mkdoc({"arm_c.kind.alpha": None,
                                 "arm_c.kind.beta": None}))
    expect("W4 直方图为空集（反例不能是空集）",
           audit(kv2, text, "a" * 64, 100, 3), True)
    # 反例 W4：rc 非零 / 计数为 0
    kv2, _ = parse_block(_mkdoc({"arm_c.rc": "1"}))
    expect("W4 rc != 0", audit(kv2, text, "a" * 64, 100, 3), True)
    kv2, _ = parse_block(_mkdoc({"arm_c.json_bytes": "0"}))
    expect("W4 json_bytes = 0", audit(kv2, text, "a" * 64, 100, 3), True)

    # 反例 W5：与基线不同（非确定）
    kv2, _ = parse_block(_mkdoc({"arm_c.funcs": "21"}))
    expect("W5 计数器与 R81 基线不等", audit(kv2, text, "a" * 64, 100, 3), True)
    # 正例 W5：只有时钟类字段不同 ⇒ **必须放行**（不可裁决，不许红）
    kv2, _ = parse_block(_mkdoc({"arm_c.seconds": "999.0", "arm_c.peak_mb": "9.9"}))
    expect("W5 仅时钟类字段不同（不可裁决 ⇒ 必须放行）",
           audit(kv2, text, "a" * 64, 100, 3), False)
    # 反例 W5：跨文档分母不一致
    kv2, _ = parse_block(_mkdoc({"crossdoc.unknown_sites_files": "9"}))
    expect("W5 跨文档分母不一致", audit(kv2, text, "a" * 64, 100, 3), True)
    # 正例 W5：跨文档那一条未行使（分母抽不出）时不许红
    kv2, _ = parse_block(text)
    expect("W5 跨文档未行使（None ⇒ 不判）",
           audit(kv2, text, "a" * 64, 100, None), False)

    # 分母抽取（跨文档对账的另一半）：两条路径 + 取不到不猜
    def _den(t, want):
        got = denominator_from_text(t)
        return [] if got == want else ["分母抽取得到 %r，期望 %r" % (got, want)]
    expect("分母抽取：优先取语义行（扫描文件 340）",
           _den("| 扫描文件 seen / scanned / skipped | 340 / 340 / 0 |", 340), False)
    expect("分母抽取：退回首处「N 个文件」（91）",
           _den("语料子树 `repo` | 91 个文件 |", 91), False)
    expect("分母抽取：带千分位（1,315）",
           _den("| 扫描文件 seen / scanned / skipped | 1,315 / 1,315 / 0 |", 1315),
           False)
    expect("分母抽取：取不到 ⇒ 不猜（None）",
           _den("正文里一个分母都没有", None), False)

    # 反例 W3：第三档分母与内核分母同值（被复制而非各自数出）
    kv2, _ = parse_block(_mkdoc({"corpus.files_repo_plus_oss": "10"}))
    expect("W3 第三档分母与内核分母同值",
           audit(kv2, text, "a" * 64, 100, 3), True)
    kv2, _ = parse_block(_mkdoc({"corpus.files_repo_plus_oss": "0"}))
    expect("W3 第三档分母为 0", audit(kv2, text, "a" * 64, 100, 3), True)
    # 正例 W3：三档互不相同
    kv2, _ = parse_block(_mkdoc())
    expect("W3 三档分母互不相同", audit(kv2, text, "a" * 64, 100, 3), False)

    # 反例 W2：cwd 口径缺失 / 占位 —— 两个都对的读数无法分辨
    kv2, _ = parse_block(_mkdoc({"provenance.cwd_convention": "-"}))
    expect("W2 cwd 口径为占位 `-`（读数无法分辨）",
           audit(kv2, text, "a" * 64, 100, 3), True)
    kv2, _ = parse_block(_mkdoc({"provenance.cwd_convention": None}))
    expect("W2 cwd 口径整键缺失",
           audit(kv2, text, "a" * 64, 100, 3), True)
    # 正例 W2：口径已写明 ⇒ 放行
    kv2, _ = parse_block(_mkdoc())
    expect("W2 cwd 口径已写明", audit(kv2, text, "a" * 64, 100, 3), False)

    # 反例 W5：某一侧 README 不指向唯一事实源
    kv2, _ = parse_block(text)
    expect("W5 README_CN.md 未指向 KERNEL_RUN.md",
           audit(kv2, text, "a" * 64, 100, 3,
                 readmes={"README.md": "见 docs/KERNEL_RUN.md",
                          "README_CN.md": "没有指针"}), True)
    # 反例 W5：README 缺文件（空串）也要红
    kv2, _ = parse_block(text)
    expect("W5 README 缺失（空串）也要红",
           audit(kv2, text, "a" * 64, 100, 3,
                 readmes={"README.md": "见 docs/KERNEL_RUN.md",
                          "README_CN.md": ""}), True)
    # 正例 W5：两侧都指向 ⇒ 放行
    kv2, _ = parse_block(text)
    expect("W5 两侧 README 都指向 KERNEL_RUN.md",
           audit(kv2, text, "a" * 64, 100, 3,
                 readmes={"README.md": "见 docs/KERNEL_RUN.md",
                          "README_CN.md": "见 docs/KERNEL_RUN.md"}), False)
    # 正例 W5：readmes 未注入（None）时该条不判 ⇒ 不许红
    kv2, _ = parse_block(text)
    expect("W5 README 指针未行使（None ⇒ 不判）",
           audit(kv2, text, "a" * 64, 100, 3, readmes=None), False)

    # ======================= W6 流程登记 =======================
    # 夹具：最小的**合法**站表 —— 1 源站 + 1 退役分析器 + 1 当前分析器 + 1 终点门。
    # 刻意含一个退役站：它是 W6a「非 current 必须写 why」那一条的**正例**半边。
    def _mkpipe(stations=None, extra=None, drop=()):
        st = stations if stations is not None else [
            ("01", "path=X:/a/fetch.py;role=source;in=-;out=corpus;status=current"),
            ("02", "path=X:/a/old.py;role=analyze;in=corpus;out=old-j;"
                   "status=superseded;why=理由"),
            ("03", "path=X:/a/new.py;role=analyze;in=corpus,old-j;out=agg;"
                   "status=current"),
            ("04", "path=tools/check_kernel_snapshot.py;role=gate;in=agg;out=-;"
                   "status=current"),
        ]
        kv = dict(("pipeline.station." + n, v) for n, v in st)
        kv["pipeline.stations"] = str(len(st))
        kv["pipeline.analyze_current"] = "new"
        kv["pipeline.chain_ok"] = "1"
        kv["pipeline.repo_artifacts"] = "matlabc.py"
        for k, v in (extra or {}).items():
            if v is None:
                kv.pop(k, None)
            else:
                kv[k] = v
        for k in drop:
            kv.pop(k, None)
        rows = "\n".join("%s | %s" % (k, kv[k]) for k in sorted(kv))
        return "%s\n```text\n%s\n```\n%s\n" % (PIPELINE_OPEN, rows, PIPELINE_CLOSE)

    def _p6(t):
        k, pp = parse_block(t, PIPELINE_OPEN, PIPELINE_CLOSE, tag="W6")
        if k is None:
            return pp
        return pp + audit_pipeline(k, repo_root=_ROOT)[0]

    # 正例：最小合法站表必须放行
    expect("W6 最小合法站表（含退役站 + 恰一个 current 驱动）", _p6(_mkpipe()), False)

    # 反例 W6a：形状（字段缺失 / 闭集外的 role/status / 退役无 why / 空站表）
    expect("W6a 某站缺 role 字段",
           _p6(_mkpipe(stations=[("01", "path=X:/a/f.py;in=-;out=corpus;"
                                        "status=current")])), True)
    expect("W6a role 不在闭集",
           _p6(_mkpipe(stations=[("01", "path=X:/a/f.py;role=magic;in=-;"
                                        "out=corpus;status=current")])), True)
    expect("W6a status 不在闭集",
           _p6(_mkpipe(stations=[("01", "path=X:/a/f.py;role=source;in=-;"
                                        "out=corpus;status=maybe")])), True)
    expect("W6a 非 current 站没写 why",
           _p6(_mkpipe(stations=[("01", "path=X:/a/o.py;role=analyze;in=-;"
                                        "out=x;status=superseded")])), True)
    expect("W6a 字段缺 `=`（不是 `键=值`）",
           _p6(_mkpipe(stations=[("01", "path=X:/a/f.py;role=source;in=-;"
                                        "out=corpus;status=current;oops")])), True)
    expect("W6a 字段重复（会静默折叠成一个）",
           _p6(_mkpipe(stations=[("01", "path=X:/a/f.py;role=source;role=analyze;"
                                        "in=-;out=corpus;status=current")])), True)
    _k, _pp = parse_block(_mkpipe(), PIPELINE_OPEN, PIPELINE_CLOSE, tag="W6")
    for _kk in [_x for _x in _k if STATION_RE.match(_x)]:
        _k.pop(_kk)
    expect("W6a 站表是空集（反例不能是空集 ⇒ 必须红）",
           _pp + audit_pipeline(_k, repo_root=_ROOT)[0], True)
    # 反例/正例 W6a：`probe` 角色必须写 why —— 否则它与「被误分类的第二个主驱动」
    # 在**读数上完全分不开**（这正是本轮真撞到的形态：`chunks` 一开始被标成 analyze）。
    expect("W6a role=probe 却没写 why",
           _p6(_mkpipe(stations=[
               ("01", "path=X:/a/f.py;role=source;in=-;out=corpus;status=current"),
               ("02", "path=X:/a/p.py;role=probe;in=corpus;out=probe-j;"
                      "status=current"),
               ("03", "path=X:/a/new.py;role=analyze;in=corpus;out=agg;"
                      "status=current")],
               extra={"pipeline.stations": "3",
                      "pipeline.analyze_current": "new"})), True)
    expect("W6a role=probe 写了 why（且不占 current 分析器名额）",
           _p6(_mkpipe(stations=[
               ("01", "path=X:/a/f.py;role=source;in=-;out=corpus;status=current"),
               ("02", "path=X:/a/p.py;role=probe;in=corpus;out=probe-j;"
                      "status=current;why=独立口径"),
               ("03", "path=X:/a/new.py;role=analyze;in=corpus;out=agg;"
                      "status=current")],
               extra={"pipeline.stations": "3",
                      "pipeline.analyze_current": "new"})), False)

    # 反例 W6b：恰好一个 current 分析器（0 个 / 2 个 / 点名不符）
    expect("W6b 两个 current 分析器（没人知道该跑哪个）",
           _p6(_mkpipe(extra={
               "pipeline.station.05": "path=X:/a/new2.py;role=analyze;in=agg;"
                                      "out=agg2;status=current",
               "pipeline.stations": "5"})), True)
    expect("W6b 零个 current 分析器（流程没有分析器）",
           _p6(_mkpipe(extra={
               "pipeline.station.03": "path=X:/a/new.py;role=analyze;"
                                      "in=corpus,old-j;out=agg;"
                                      "status=superseded;why=也退役了"})), True)
    expect("W6b pipeline.analyze_current 与那唯一站不符",
           _p6(_mkpipe(extra={"pipeline.analyze_current": "someoneelse"})), True)

    # 反例 W6c：产物链拓扑（断链 / 顺序反了 / 声明与正文分家）
    expect("W6c 输入没有任何前序站产出（链是断的）",
           _p6(_mkpipe(stations=[
               ("01", "path=X:/a/f.py;role=source;in=-;out=corpus;status=current"),
               ("02", "path=X:/a/n.py;role=analyze;in=corpus,mystery;out=agg;"
                      "status=current")],
               extra={"pipeline.stations": "2",
                      "pipeline.analyze_current": "n"})), True)
    expect("W6c 顺序反了（第 1 站引用了后序站的产物）",
           _p6(_mkpipe(stations=[
               ("01", "path=X:/a/user.py;role=analyze;in=corpus;out=agg;"
                      "status=current"),
               ("02", "path=X:/a/f.py;role=source;in=-;out=corpus;"
                      "status=current")],
               extra={"pipeline.stations": "2",
                      "pipeline.analyze_current": "user"})), True)
    expect("W6c 链其实通，但 chain_ok 声明成 0",
           _p6(_mkpipe(extra={"pipeline.chain_ok": "0"})), True)
    expect("W6c 链是断的，但 chain_ok 声明成 1（声明与正文分家）",
           _p6(_mkpipe(stations=[
               ("01", "path=X:/a/n.py;role=analyze;in=ghost;out=agg;"
                      "status=current")],
               extra={"pipeline.stations": "1",
                      "pipeline.analyze_current": "n"})), True)

    # 反例 W6d：站数分母必须等于明细
    expect("W6d 分母比明细大（读者只会信分母）",
           _p6(_mkpipe(extra={"pipeline.stations": "9"})), True)
    expect("W6d 分母整键缺失",
           _p6(_mkpipe(drop=("pipeline.stations",))), True)
    expect("W6d 分母比明细小（会把站点漏出覆盖之外）",
           _p6(_mkpipe(extra={"pipeline.stations": "2"})), True)

    # 反例 W6e：仓内落点必须存在（空集 / 指向不存在的文件）
    expect("W6e 仓内落点为空集（恒真）",
           _p6(_mkpipe(extra={"pipeline.repo_artifacts": "-"})), True)
    expect("W6e 仓内落点不存在（站表里有一站是幻影）",
           _p6(_mkpipe(extra={"pipeline.repo_artifacts":
                              "matlabc.py,docs/NO_SUCH_FILE_R85.md"})), True)
    # 正例 W6e：多个仓内落点都真实存在 ⇒ 放行（覆盖整个群体，不是「至少一个」）
    expect("W6e 两个仓内落点都存在",
           _p6(_mkpipe(extra={"pipeline.repo_artifacts":
                              "matlabc.py,tools/check_kernel_snapshot.py"})), False)

    # ---- R87：W5 的「已声明变化」出口**三向都有对手方**（否则它只是把
    # 「逐位全等」换成一张「永远可以解释任何差异」的通行证）----
    _ok = {"base": "20", "cur": "19", "reason": "分析逻辑真的变了（探针可复现）"}
    expect("W5d 不等 + 已登记（数字对得上、原因非空）",
           _delta_verdict({"arm_c.funcs": _ok}, "arm_c.funcs", 19, 20), False)
    expect("W5d 相等 + 未登记（原本的判据）",
           _delta_verdict({}, "arm_c.funcs", 20, 20), False)
    expect("W5d 不等却未登记",
           _delta_verdict({}, "arm_c.funcs", 19, 20), True)
    expect("W5d 相等却仍被登记（陈旧登记）",
           _delta_verdict({"arm_c.funcs": _ok}, "arm_c.funcs", 20, 20), True)
    expect("W5d 登记数字与实测不符",
           _delta_verdict({"arm_c.funcs": {"base": "20", "cur": "18",
                                           "reason": "x"}},
                          "arm_c.funcs", 19, 20), True)
    expect("W5d 变了但原因栏是空的",
           _delta_verdict({"arm_c.funcs": {"base": "20", "cur": "19",
                                           "reason": "   "}},
                          "arm_c.funcs", 19, 20), True)
    expect("W5d 登记的 base/cur 不是整数（幽灵登记落盘的样子）",
           _delta_verdict({"arm_c.funcs": {"reason": "x"}},
                          "arm_c.funcs", 19, 20), True)
    expect("W5d 块未行使时退回逐位全等（不等 ⇒ 红）",
           _delta_verdict(None, "arm_c.funcs", 19, 20), True)
    expect("W5d 逐类出现 None（本轮有 / 基线无）也不许崩",
           _delta_verdict({}, "arm_c.kind.x", 3, None), True)

    # 反例 W6：流程块缺失（缺输入必须能红，不许静默当成「没有流程要核」）
    expect("W6 流程块整块缺失", _p6("正文里没有流程块\n"), True)

    # ---- R95/W7：产物现算核对**六个方向**都要有对手方 ----
    _disk = {"kernel_c_summary.json": {"bytes": 11355506, "sha256": "c" * 16},
             "kernel_asm_summary.json": {"bytes": 486229, "sha256": "d" * 16},
             "kernel_callgraph.json": {"bytes": 4358990, "sha256": "e" * 16}}
    kv2, _ = parse_block(text)
    expect("W7 表与磁盘逐份一致", audit(kv2, text, "a" * 64, 100, 3,
                                    artifacts=_disk), False)
    kv2, _ = parse_block(text)
    expect("W7 产物不在本机（该条未行使，不许静默当对得上）",
           audit(kv2, text, "a" * 64, 100, 3, artifacts={}), False)
    kv2, _ = parse_block(_mkdoc({"artifact.kernel_c_summary.json.bytes": "1"}))
    expect("W7 字节数与磁盘不符（产物被换过）",
           audit(kv2, text, "a" * 64, 100, 3, artifacts=_disk), True)
    kv2, _ = parse_block(_mkdoc({"artifact.kernel_callgraph.json.sha256":
                                 "f" * 16}))
    expect("W7 sha256 与磁盘不符",
           audit(kv2, text, "a" * 64, 100, 3, artifacts=_disk), True)
    kv2, _ = parse_block(_mkdoc({"artifact.kernel_c_summary.json.bytes": "-",
                                 "artifact.kernel_c_summary.json.sha256": "-"}))
    expect("W7 表说不在、磁盘却有一份（表被手改）",
           audit(kv2, text, "a" * 64, 100, 3, artifacts=_disk), True)
    kv2, _ = parse_block(_mkdoc({"artifact.kernel_asm_summary.json.sha256": None}))
    expect("W7 bytes/sha256 只登记一半",
           audit(kv2, text, "a" * 64, 100, 3, artifacts=_disk), True)
    kv2, _ = parse_block(_mkdoc({"artifact.kernel_asm_summary.json.bytes": "-"}))
    expect("W7 「不在」只写了一列",
           audit(kv2, text, "a" * 64, 100, 3, artifacts=_disk), True)
    kv2, _ = parse_block(_mkdoc({"artifact.kernel_c_summary.json.sha1": "x"}))
    expect("W7 未登记字段（键名拼错 ⇒ 那条核对永远不跑）",
           audit(kv2, text, "a" * 64, 100, 3, artifacts=_disk), True)
    _allkeys = list(parse_block(_mkdoc())[0])
    kv2, _ = parse_block(_mkdoc(dict((k, None) for k in _allkeys
                                     if k.startswith("artifact."))))
    expect("W7 产物条目为空集（恒真）",
           audit(kv2, text, "a" * 64, 100, 3, artifacts=_disk), True)
    kv2, _ = parse_block(_mkdoc(dict(
        (k, None) for k in _allkeys
        if k.startswith("artifact.") and k.endswith((".bytes", ".sha256")))))
    expect("W7 只写了 artifact.dir（没有一份产物）",
           audit(kv2, text, "a" * 64, 100, 3, artifacts=_disk), True)
    kv2, _ = parse_block(_mkdoc({"artifact.dir": None}))
    expect("W7 缺 artifact.dir（路径无处可寻）",
           audit(kv2, text, "a" * 64, 100, 3, artifacts=_disk), True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    if fails:
        print("SELFTEST FAILED: %s" % fails)
        return 1
    print("SELFTEST PASSED")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    sys.exit(main())
