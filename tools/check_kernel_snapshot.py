# -*- coding: utf-8 -*-
"""全树规模读数（跑次登记表）的登记制护栏 —— 判据族 W1–W5。

它回答的问题只有一个：**文档里那张「内核全树跑出来的数字」还成立吗？**

为什么需要它（三条，都是本仓已经踩过的形态）：
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

本门**不做识别**：不跑分析、不读源码、不解析二进制、不碰内核语料
（28 MB 语料与 13 分钟预算都不属于一道静态门）。它只回答：
「那张表自称的那件事，今天还成立吗？」

退出码：
    0  = W1–W5 全部通过
    1  = 发现违规
    2  = 缺输入（登记表不在 / 块缺失 / 格式不可解析 / `matlabc.py` 不在）
"""
import io
import os
import re
import sys

ROW_SIGNATURE = "W1–W5"

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
def parse_block(text):
    """取块 -> (kv, problems)。kv 为 None 表示没取到。

    规则（每条都对应一次真事故）：
      * 开/闭标记各必须**恰好出现一次** —— 重号会让切片落错地方（§4z-15）。
      * 标记之间必须紧跟一个围栏块。
      * 数据行 `键 | 值`；`#` 开头或空行是注释。
      * **键不得重复** —— 重复会静默折叠成一个（L73 的多重集纪律）。
    """
    probs = []
    if text.count(BLOCK_OPEN) != 1:
        return None, ["W1 开标记 %r 出现 %d 次（要求恰好 1 次）"
                      % (BLOCK_OPEN, text.count(BLOCK_OPEN))]
    if text.count(BLOCK_CLOSE) != 1:
        return None, ["W1 闭标记 %r 出现 %d 次（要求恰好 1 次）"
                      % (BLOCK_CLOSE, text.count(BLOCK_CLOSE))]
    i = text.index(BLOCK_OPEN) + len(BLOCK_OPEN)
    j = text.index(BLOCK_CLOSE)
    if j < i:
        return None, ["W1 闭标记出现在开标记之前"]
    body = text[i:j]
    m = re.search(r"```[^\n]*\n(.*?)```", body, re.S)
    if not m:
        return None, ["W1 开闭标记之间没有围栏块（必须用 ``` 围起来）"]
    lines = m.group(1).split("\n")
    kv = {}
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if s.count("|") != 1:
            probs.append("W1 数据行必须恰好一个 `|` 分隔符：%r" % ln)
            continue
        k, v = s.split("|")
        k, v = k.strip(), v.strip()
        if not k:
            probs.append("W1 空键：%r" % ln)
            continue
        if k in kv:
            probs.append("W1 键 %r 重复（重复会静默折叠成一个 ⇒ 必须红）" % k)
            continue
        if v == "":
            probs.append("W1 键 %r 的值为空（缺值必须红；要表示「无」请写 `-`）" % k)
            continue
        kv[k] = v
    if not kv:
        probs.append("W1 块里一行数据都没有")
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


# --------------------------------------------------------------- 判据
def audit(kv, doc_text, matlabc_sha=None, matlabc_bytes=None,
          unknown_doc_denominator=None, readmes=None):
    """返回 problems 列表（空 = 全过）。所有外部事实都可注入 ⇒ 可两向自证。

    `readmes` = {显示名: 文本}；为 None 表示「这一条未行使」（自证的多数用例）。
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
            if va != vb:
                probs.append(
                    "W5 %s: 本轮 %d != R81 基线 %d（差 %+d）—— `matlabc.py` 自 R81 起"
                    "只有纯文档改动，计数器本应逐位复现；不等说明解析**非确定**"
                    "（或分析逻辑真的变了，那就必须写出原因）" % (k, va, vb, va - vb))
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
            probs.append(
                "W5 启发式分解逐类不一致：%s 本轮 %s vs R81 基线 %s"
                "（总和相同也照样红 —— 只比总和会让「一好一坏顶替」静默通过）"
                % (name, ak.get(name), bk.get(name)))

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
    probs.extend(audit(kv, text, matlabc_sha=sha256_file(mc_p),
                       matlabc_bytes=os.path.getsize(mc_p),
                       unknown_doc_denominator=unk, readmes=readmes))

    if unk is None:
        print("  [跳过] docs/UNKNOWN_SITES.md 里抽不到「N 文件」分母 ⇒ 跨文档那一条未行使")
    for p in probs:
        print("  - " + p)
    if probs:
        print("check_kernel_snapshot: FAILED（%d 条；判据族 %s）"
              % (len(probs), ROW_SIGNATURE))
        return 1
    print("check_kernel_snapshot: OK（全树规模读数：出处+口径钉住 + 两档分母并列 + "
          "汇总↔明细恒等式 + 与 R81 基线逐位/逐类对照 + 唯一事实源指针；判据族 %s）"
          % ROW_SIGNATURE)
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
