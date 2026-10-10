#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""登记制护栏：许可与署名的「双轨」必须两向对上（L1–L7）。

动因（R69）：本仓的许可在 R69 从「MIT」改成「**双轨**」——
**代码是 MIT，名称与品牌不是**。这件事有三条隐蔽的腐烂方式，而此前
**没有任何门看得见它们**：

  ① MIT 正文被「顺手润色」掉一句 —— GitHub 的 licensee 靠**正文**识别许可。
     识别一旦失败，README 上那枚 `license-MIT` 徽章就变成一句假话，而
     **没有任何现有门核过 LICENSE 的正文**：`check_readme_parity` 只核两份
     README，`check_doc_flags` 只核 CLI 开关，`check_help_contract` 只管退出码
     与散文数字。R69 的探针用例 A1 就是为了把这条**量出来**才写的。
  ② 版权人只改一侧 —— `LICENSE` 与 `LICENSE_CN` 描述的是**同一份**授权，
     只改一半时两份文件互相矛盾，而两份文件**都还在**、rc 依然是 0。
  ③ 版本徽章陈旧 —— R69 量出 README 双侧写 `1.16.71` 而 `matlabc.py` 的
     `VERSION` 已经是 `1.16.72`。这是**已经发生过的真缺陷**，不是假想；
     此前这条约定完全靠人记得。

判据族 **L1–L7**（只认装置，不认叙述）：

    L1 MIT 正文逐字保留：`LICENSE` 首行必须是 `MIT License`，且四段标记
       （授予段 / 保留声明段 / 免责段 / 末句）逐字在场。这是**双轨模型的前提**：
       代码侧若不再是 MIT，「双轨」就无从谈起。
    L2 版权人单一事实源：`LICENSE` 与 `LICENSE_CN` 的版权行归一（全角→半角、
       抹掉空白）后必须**相等**，且都以登记的 `COPYRIGHT_HOLDER` 开头。
    L3 品牌必究条款在场：`LICENSE` 与 `LICENSE_CN` 必须**同时**含两处语言的规范
       标记（`侵权必究` / `ALL RIGHTS RESERVED`）；`README.md` / `README_CN.md` /
       `CONTRIBUTING.md` 每处至少含其一。理由：只把双轨写进许可正文、而读者入口
       （README）不提，等于**承诺与可见性分叉**。
    L4 双侧徽章集合一致 + 代码侧仍是 MIT：两侧 README 的 shields.io 徽章 URL
       集合必须**逐条相等**（任一侧加删徽章而另一侧没跟 ⇒ 红），且 `license`
       徽章的值必须是 `MIT`（双轨模型下代码侧不变）。
    L5 版本徽章 == `matlabc.py` 的 `VERSION`：两侧 README 的 `version` 徽章
       必须逐字等于源码常量。这条对应上面量出的真陈旧 ③。
    L6 `LICENSE_CN` 与 `LICENSE` 的编号小节集合相等且非空：两份描述同一份授权，
       附录只改一侧 ⇒ 红。
    L7 双轨必须在 README 的许可证节里可见：两侧 README 的 `## License` /
       `## 许可证` 小节必须同时含 `MIT`、规范标记与登记署名。

为什么用「登记值 ⇄ 文件内容」而不是「文件里必须出现某几个字符串」：后者只查
一条，且**新增**的东西不会被发现（覆盖可以静默缩水，与 R4 的老账同源）。

两向自证：坏样本（MIT 正文缺段 / 版权人不一致 / 必究标记缺失 / 徽章集合分叉 /
版本徽章陈旧 / 编号小节不等 / 许可证节缺双轨 / 代码侧许可徽章被改）必须抓得到；
好样本必须放行；并对**真实仓库**做一次整体核对。

用法：
    python tools/check_legal_parity.py              # 0=对上 1=发现违规 2=缺输入
    python tools/check_legal_parity.py --selftest   # 两向自证
    python tools/check_legal_parity.py --help       # 显示本帮助（立即返回）

退出码：
    0 = 全部对上（L1–L7 无违规）
    1 = 发现违规（L1–L7 任一红）
    2 = 缺输入（任一在册文件不存在或读不到，或读不到 matlabc.py 的 VERSION）
"""
import io
import os
import re
import shutil
import sys
import tempfile

# R69：「质量门表」里本门那一行的**判据族名**。必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "L1–L7"

# 登记的版权人（**单一事实源**）。两处许可文件的版权行都必须归一后与它一致。
# 归一：全角括号 → 半角、抹掉全部空白（中文排版用全角括号才是对的，
# 而英文用半角 —— 这里比的是「同一个人」，不是「同一串字节」）。
COPYRIGHT_HOLDER = "\u51af\u78ca (Feng Lei)"      # 冯磊 (Feng Lei)

# 「品牌必究」的规范标记：两处语言各一。中/英许可正文必须**同时**含两条。
MARKER_CN = "\u4fb5\u6743\u5fc5\u7a76"            # 侵权必究
MARKER_EN = "ALL RIGHTS RESERVED"
MARKERS = (MARKER_CN, MARKER_EN)

# 双轨模型里**必须**逐字保留、且必须有对手方的 MIT 正文标记。
# 四段对应：授予段 / 保留声明段 / 免责段 / 末句（"OUT OF OR IN CONNECTION…"）。
MIT_FIRST_LINE = "MIT License"
MIT_MARKERS = (
    "Permission is hereby granted, free of charge, to any person obtaining a copy",
    "The above copyright notice and this permission notice shall be included in all",
    'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR',
    "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE",
)

# 在册文件（缺任一 => 缺输入 => 红，而不是「没有可检查的对象 => 放行」）。
RESERVED_FILES = ("LICENSE", "LICENSE_CN", "README.md", "README_CN.md",
                  "CONTRIBUTING.md")

BADGE_URL_RE = re.compile(r"https://img\.shields\.io/badge/[^)\s]+")
LIC_BADGE_RE = re.compile(
    r"https://img\.shields\.io/badge/license-([A-Za-z0-9._%+-]+?)-[A-Za-z0-9]{3,20}\)")
VER_BADGE_RE = re.compile(
    r"https://img\.shields\.io/badge/version-([A-Za-z0-9._%+-]+?)-[A-Za-z0-9]{3,20}\)")
VER_CONST_RE = re.compile(r'^VERSION\s*=\s*"([^"]+)"', re.M)
NUM_SECTION_RE = re.compile(r"^\s*(\d{1,2})\.\s+\S", re.M)
OWNER_LINE_RE_EN = re.compile(r"^Copyright \(c\) \d{4}\s+(.+)$", re.M)
OWNER_LINE_RE_CN = re.compile(r"^\u7248\u6743\u6240\u6709 \(c\) \d{4}\s+(.+)$", re.M)

LICENSE_SECTION_EN = "## License"
LICENSE_SECTION_CN = "## \u8bb8\u53ef\u8bc1"
SECTION_SPAN = 2600          # 许可证节的取样窗口（够覆盖这一段，且不越到别节）


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    with io.open(path, "rb") as fh:
        return fh.read().decode("utf-8", "replace")


def norm_owner(s):
    """版权人归一：全角→半角 + 抹掉全部空白。"""
    if s is None:
        return ""
    for a, b in (("\uff08", "("), ("\uff09", ")"), ("\u3000", " "),
                 ("\u2014", "-"), ("\uff0d", "-")):
        s = s.replace(a, b)
    return "".join(s.split())


def badge_urls(text):
    """两侧 README 的 shields.io 徽章 URL 集合（逐条比，不看 alt 文案）。"""
    return sorted(set(BADGE_URL_RE.findall(text or "")))


def version_const(root):
    p = os.path.join(root, "matlabc.py")
    if not os.path.isfile(p):
        return None
    m = VER_CONST_RE.search(_read(p))
    return m.group(1) if m else None


def license_section(text, head):
    if text is None:
        return None
    i = text.find(head)
    return None if i < 0 else text[i:i + SECTION_SPAN]


def audit(root, on_problem):
    """施加 L1–L7；返回核对过的文件数（0 => 缺输入，调用方按红处理）。"""
    texts = {}
    for rel in RESERVED_FILES:
        p = os.path.join(root, rel)
        if not os.path.isfile(p):
            on_problem("L0 %s 不存在（缺输入 → 红）" % rel)
            continue
        try:
            texts[rel] = _read(p)
        except OSError as e:
            on_problem("L0 %s 读不到（%s）" % (rel, e))
    ver = version_const(root)
    if ver is None:
        on_problem("L0 matlabc.py 不存在或读不到 VERSION 常量（缺输入 → 红）")
    if len(texts) != len(RESERVED_FILES) or ver is None:
        return len(texts)

    lic = texts["LICENSE"]
    lic_cn = texts["LICENSE_CN"]
    en = texts["README.md"]
    cn = texts["README_CN.md"]
    contrib = texts["CONTRIBUTING.md"]

    # ── L1 MIT 正文逐字保留（双轨模型的**前提**）─────────────────────────
    first = lic.split("\n", 1)[0].strip()
    if first != MIT_FIRST_LINE:
        on_problem("L1 LICENSE 首行是 %r，不是 %r —— 首行是 licensee 的第一判据"
                   % (first, MIT_FIRST_LINE))
    miss = [m for m in MIT_MARKERS if m not in lic]
    if miss:
        on_problem("L1 LICENSE 的 MIT 正文缺 %d 段标记：%r —— 双轨模型里"
                   "**代码侧**必须仍是 MIT，正文一个字都不能动"
                   % (len(miss), [m[:46] for m in miss]))

    # ── L2 版权人单一事实源（两份许可文件 ⇄ 登记值）──────────────────────
    #
    # ⚠ 口径（本门首次真跑当场修的一处自伤）：**不能拿整行去比**。两份版权行
    # 在「人名」之后本来就不同 —— EN 写成 `冯磊 (Feng Lei) — malabc / matlabc — <url>`，
    # CN 写成 `冯磊（Feng Lei）（malabc / matlabc —— <url>）`。比整行 ⇒ 恒红。
    # 正确的对手方是「**这个人是谁**」：每一条版权行归一后都必须以登记署名开头。
    # 这条同时覆盖「只改了一侧」：被改的那一行会断开前缀，另一条不会。
    o_en_all = OWNER_LINE_RE_EN.findall(lic)
    o_cn_all = OWNER_LINE_RE_CN.findall(lic_cn)
    want = norm_owner(COPYRIGHT_HOLDER)
    for label, got in (("LICENSE", o_en_all), ("LICENSE_CN", o_cn_all)):
        if not got:
            on_problem("L2 %s 里找不到 `Copyright (c) <年> <人>` 行（缺输入 → 红）"
                       % label)
            continue
        for raw in got:
            if not norm_owner(raw).startswith(want):
                on_problem("L2 %s 的版权人 %r 与登记值 %r 不符 —— 两份许可描述的是"
                           "**同一份**授权，版权行必须一致" % (label, raw[:40], want))

    # ── L3 品牌必究条款在场（两处许可同时含两条标记；读者入口各含其一）──
    for label, doc in (("LICENSE", lic), ("LICENSE_CN", lic_cn)):
        for mk in MARKERS:
            if mk not in doc:
                on_problem("L3 %s 缺规范标记 %r —— 「双轨」若只写在对话里、"
                           "没写进许可正文，读仓库的人看不到" % (label, mk))
    for label, doc in (("README.md", en), ("README_CN.md", cn),
                       ("CONTRIBUTING.md", contrib)):
        if not [m for m in MARKERS if m in doc]:
            on_problem("L3 %s 一个必究标记都没有（%r 至少要有其一）—— 读者入口"
                       "不提，等于承诺与可见性分叉" % (label, list(MARKERS)))

    # ── L4 双侧徽章集合一致；且**代码侧**仍是 MIT ────────────────────────
    bu_en, bu_cn = badge_urls(en), badge_urls(cn)
    if not bu_en:
        on_problem("L4 README.md 里一枚 shields.io 徽章都没有（缺输入 → 红）")
    only_en = [u for u in bu_en if u not in bu_cn]
    only_cn = [u for u in bu_cn if u not in bu_en]
    if only_en or only_cn:
        on_problem("L4 两侧徽章集合不一致：仅 EN 有 %r / 仅 CN 有 %r —— "
                   "任一侧加删徽章而另一侧没跟，读者看到的是两份不同的说明"
                   % ([u.rsplit("/", 1)[-1] for u in only_en],
                      [u.rsplit("/", 1)[-1] for u in only_cn]))
    for label, doc in (("README.md", en), ("README_CN.md", cn)):
        m = LIC_BADGE_RE.search(doc)
        if m is None:
            on_problem("L4 %s 找不到 license 徽章（`badge/license-<值>-<色>`）" % label)
        elif m.group(1) != "MIT":
            on_problem("L4 %s 的 license 徽章写的是 %r，不是 MIT —— 双轨模型里"
                       "**代码侧**仍是 MIT；徽章与许可正文互为对手方"
                       % (label, m.group(1)))

    # ── L5 版本徽章 == matlabc.py 的 VERSION（真陈旧，见 docstring ③）────
    for label, doc in (("README.md", en), ("README_CN.md", cn)):
        m = VER_BADGE_RE.search(doc)
        if m is None:
            on_problem("L5 %s 找不到 version 徽章（`badge/version-<值>-<色>`）" % label)
        elif m.group(1) != ver:
            on_problem("L5 %s 的 version 徽章是 %r，而 matlabc.py 的 VERSION 是 %r"
                       " —— 文档比源码旧（R69 量出的真缺陷，此前无人管）"
                       % (label, m.group(1), ver))

    # ── L6 两份许可的编号小节集合相等且非空 ──────────────────────────────
    s_en = [int(x) for x in NUM_SECTION_RE.findall(lic)]
    s_cn = [int(x) for x in NUM_SECTION_RE.findall(lic_cn)]
    if not s_en or not s_cn:
        on_problem("L6 两份许可里至少有一份解析不到编号小节（缺输入 → 红）："
                   "EN=%r CN=%r" % (s_en, s_cn))
    elif s_en != s_cn:
        on_problem("L6 LICENSE 与 LICENSE_CN 的编号小节不等：EN=%r CN=%r —— "
                   "两份描述同一份授权，附录只改一侧就会互相矛盾"
                   % (s_en, s_cn))

    # ── L7 双轨必须在 README 的许可证节里可见 ────────────────────────────
    for label, doc, head in (("README.md", en, LICENSE_SECTION_EN),
                             ("README_CN.md", cn, LICENSE_SECTION_CN)):
        sec = license_section(doc, head)
        if sec is None:
            on_problem("L7 %s 找不到许可证章节 %r" % (label, head))
            continue
        if "MIT" not in sec:
            on_problem("L7 %s 的许可证节里没提 MIT（代码侧）" % label)
        if not [m for m in MARKERS if m in sec]:
            on_problem("L7 %s 的许可证节里没有必究标记（品牌侧）—— "
                       "只把双轨写进 LICENSE、README 不提，读者仍会以为「MIT，随便用」"
                       % label)
        if norm_owner(COPYRIGHT_HOLDER) not in norm_owner(sec):
            on_problem("L7 %s 的许可证节里没有登记署名 %r"
                       % (label, COPYRIGHT_HOLDER))
    return len(texts)


def on_problem_collector(bucket):
    def _cb(msg):
        bucket.append(msg)
    return _cb


# ---------------------------------------------------------------------------
# 两向自证：好样本必须放行、坏样本必须抓得到。
# 约定（与 check_help_contract / check_readme_parity 相同）：expect 的第一个
# 布尔是「这道门认为有问题」——也就是它会变红的那个值。
# ---------------------------------------------------------------------------
_FIX_VER = "9.9.9"


def _good_files():
    """一份**全部对上**的合成仓库（六份文件 + matlabc.py）。"""
    badge = ("![License](https://img.shields.io/badge/license-MIT-green)\n"
             "![Branding](https://img.shields.io/badge/name%20%26%20branding"
             "all%20rights%20reserved-critical)\n"
             "![Version](https://img.shields.io/badge/version-" + _FIX_VER
             + "-informational)\n")
    lic = ("MIT License\n\n"
           "Copyright (c) 2026 " + COPYRIGHT_HOLDER + " \u2014 demo\n\n"
           + MIT_MARKERS[0] + "\nof this software and associated documentation files.\n\n"
           + MIT_MARKERS[1] + "\ncopies or substantial portions of the Software.\n\n"
           + MIT_MARKERS[2] + "\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES.\n\n"
           + MIT_MARKERS[3] + "\nSOFTWARE.\n\n"
           "1. SCOPE\n   x\n\n2. DEPS\n   x\n\n3. CORPORA\n   x\n\n"
           "4. UPSTREAM\n   x\n\n5. WARRANTY\n   x\n\n"
           "6. NAME, BRANDING AND ATTRIBUTION \u2014 " + MARKER_EN + "\n"
           "   " + MARKER_CN + "\n")
    lic_cn = ("MIT \u8bb8\u53ef\u8bc1\n\n"
              "\u7248\u6743\u6240\u6709 (c) 2026 " + COPYRIGHT_HOLDER + "\n\n"
              + MARKER_CN + " / " + MARKER_EN + "\n\n"
              "1. \u8303\u56f4\n   x\n\n2. \u4f9d\u8d56\n   x\n\n"
              "3. \u8bed\u6599\n   x\n\n4. \u4e0a\u6e38\n   x\n\n"
              "5. \u62c5\u4fdd\n   x\n\n6. \u54c1\u724c\n   x\n")
    en = ("# demo\n\n" + badge + "\n"
          "## License\n\nDual-track: MIT for the code. " + MARKER_EN + "\n"
          "Author: " + COPYRIGHT_HOLDER + "\n")
    cn = ("# \u6f14\u793a\n\n" + badge + "\n"
          "## \u8bb8\u53ef\u8bc1\n\n\u53cc\u8f68\uff1a\u4ee3\u7801\u662f MIT\u3002"
          + MARKER_CN + "\n\u4f5c\u8005\uff1a" + COPYRIGHT_HOLDER + "\n")
    contrib = ("# Contributing\n\n- LICENSE: MIT for code, " + MARKER_CN
               + " for the name. Author: " + COPYRIGHT_HOLDER + "\n")
    return {"LICENSE": lic, "LICENSE_CN": lic_cn, "README.md": en,
            "README_CN.md": cn, "CONTRIBUTING.md": contrib,
            "matlabc.py": 'VERSION = "%s"\n' % _FIX_VER}


def _mk_repo(parent, mut=None):
    files = _good_files()
    if mut is not None:
        mut(files)
    root = tempfile.mkdtemp(dir=parent)
    for rel, body in sorted(files.items()):
        with io.open(os.path.join(root, rel), "wb") as fh:
            fh.write(body.replace("\n", "\r\n").encode("utf-8"))
    return root


def _problems(root):
    b = []
    audit(root, on_problem_collector(b))
    return b


def _selftest():
    bad = good = 0
    fails = []

    tmp = tempfile.mkdtemp(prefix="legal_parity_selftest_")
    try:
        n_bad = n_good = 0

        def case(tag, mut, want_problem):
            root = _mk_repo(tmp, mut)
            probs = _problems(root)
            ok = (bool(probs) == bool(want_problem))
            print("  [%s] %-56s -> %s%s"
                  % ("\u53cd\u4f8b" if want_problem else "\u6b63\u4f8b", tag,
                     "\u6293\u5230" if probs else "\u653e\u884c",
                     "" if ok else "   *** \u4e0d\u7b26\u9884\u671f ***"))
            if not ok:
                fails.append(tag)
            return 1 if want_problem else 0, 1 if not want_problem else 0

        a, b = case("L1/L2/L3/L4/L5/L6/L7 \u5168\u5bf9\u7684\u597d\u6837\u672c",
                    None, False)
        n_bad += a
        n_good += b

        def drop_mit(f):
            f["LICENSE"] = f["LICENSE"].replace(MIT_MARKERS[2] + "\n", "", 1)

        a, b = case("L1 MIT \u6b63\u6587\u88ab\u5220\u4e86\u4e00\u6bb5", drop_mit, True)
        n_bad += a
        n_good += b

        def bump_owner(f):
            f["LICENSE_CN"] = f["LICENSE_CN"].replace(
                COPYRIGHT_HOLDER, "someone else", 1)

        a, b = case("L2 \u4e24\u4efd\u8bb8\u53ef\u7684\u7248\u6743\u4eba\u4e0d\u4e00\u81f4",
                    bump_owner, True)
        n_bad += a
        n_good += b

        def strip_markers(f):
            f["README.md"] = f["README.md"].replace(MARKER_EN, "reserved")

        a, b = case("L3 \u8bfb\u8005\u5165\u53e3\u7f3a\u5fc5\u7a76\u6807\u8bb0",
                    strip_markers, True)
        n_bad += a
        n_good += b

        def extra_badge(f):
            f["README_CN.md"] = f["README_CN.md"].replace(
                "# \u6f14\u793a\n\n",
                "# \u6f14\u793a\n\n"
                "![Extra](https://img.shields.io/badge/extra-yes-blue)\n", 1)

        a, b = case("L4 \u4e00\u4fa7\u591a\u4e86\u4e00\u679a\u5fbd\u7ae0\u3001\u53e6\u4e00\u4fa7\u6ca1\u8ddf",
                    extra_badge, True)
        n_bad += a
        n_good += b

        def wrong_license_badge(f):
            f["README.md"] = f["README.md"].replace("badge/license-MIT-green",
                                                    "badge/license-Apache--2.0-red")

        a, b = case("L4 \u4ee3\u7801\u4fa7\u8bb8\u53ef\u5fbd\u7ae0\u88ab\u6539\u6210\u975e MIT",
                    wrong_license_badge, True)
        n_bad += a
        n_good += b

        def stale_version(f):
            f["matlabc.py"] = 'VERSION = "9.9.10"\n'

        a, b = case("L5 \u7248\u672c\u5fbd\u7ae0\u6bd4\u6e90\u7801\u65e7\uff08R69 \u7684\u771f\u7f3a\u9677\uff09",
                    stale_version, True)
        n_bad += a
        n_good += b

        def drop_section(f):
            f["LICENSE_CN"] = f["LICENSE_CN"].replace("6. \u54c1\u724c\n   x\n", "")

        a, b = case("L6 \u4e00\u4fa7\u5220\u4e86\u7b2c 6 \u8282", drop_section, True)
        n_bad += a
        n_good += b

        def strip_section(f):
            f["README_CN.md"] = f["README_CN.md"].replace(MARKER_CN, "\u4fdd\u7559")

        a, b = case("L7 \u8bb8\u53ef\u8bc1\u8282\u91cc\u770b\u4e0d\u5230\u53cc\u8f68",
                    strip_section, True)
        n_bad += a
        n_good += b

        # 真实仓库整体核对：这一条是「好样本」的第二类 —— 合成夹具能过不代表
        # 真仓库能过，两者必须分开数。
        real = repo_root()
        if os.path.isdir(os.path.join(real, "tools")):
            probs = _problems(real)
            ok = not probs
            print("  [%s] %-56s -> %s%s"
                  % ("\u6b63\u4f8b", "\u771f\u5b9e\u4ed3\u5e93\u6574\u4f53\u6838\u5bf9",
                     "\u6293\u5230" if probs else "\u653e\u884c",
                     "" if ok else "   *** \u4e0d\u7b26\u9884\u671f ***"))
            if ok:
                n_good += 1
            else:
                fails.append("\u771f\u5b9e\u4ed3\u5e93\u6574\u4f53\u6838\u5bf9")
                for p in probs[:5]:
                    print("        " + p)
        else:
            n_good += 1
            print("  [\u6b63\u4f8b] %-56s -> \u8df3\u8fc7\uff08\u627e\u4e0d\u5230 tools/\uff09"
                  % "\u771f\u5b9e\u4ed3\u5e93\u6574\u4f53\u6838\u5bf9")

        bad, good = n_bad, n_good
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("  \u4e0d\u7b26\u9884\u671f\u7684\u7528\u4f8b\uff1a%r" % (fails,))
    return bad, good


def main(argv):
    if "--help" in argv or "-h" in argv:
        sys.stdout.write(__doc__)
        return 0
    if "--selftest" in argv:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if (bad == 8 and good == 2) else 1

    root = repo_root()
    probs = []
    n = audit(root, on_problem_collector(probs))
    if n != len(RESERVED_FILES):
        print("check_legal_parity: \u7f3a\u8f93\u5165\uff08\u53ea\u8bfb\u5230 %d/%d \u4efd\u5728\u518c\u6587\u4ef6\uff09"
              % (n, len(RESERVED_FILES)))
        return 2
    for p in probs:
        print("[FAIL] " + p)
    if probs:
        print("check_legal_parity: %d \u9879\u8fdd\u89c4" % len(probs))
        return 1
    print("check_legal_parity: OK\uff08\u8bb8\u53ef\u4e0e\u7f72\u540d\u53cc\u8f68\u5bf9\u4e0a\uff1a"
          "MIT \u6b63\u6587\u9010\u5b57\u4fdd\u7559 + \u7248\u6743\u4eba\u5355\u4e00\u4e8b\u5b9e\u6e90 "
          "+ \u5fc5\u7a76\u6761\u6b3e\u5728\u573a + \u53cc\u4fa7\u5fbd\u7ae0\u4e00\u81f4 + "
          "\u7248\u672c\u5fbd\u7ae0==VERSION + \u4e24\u4efd\u8bb8\u53ef\u5c0f\u8282\u5bf9\u7b49 + "
          "\u8bb8\u53ef\u8bc1\u8282\u53ef\u89c1\uff1b\u5224\u636e\u65cf %s\uff09" % ROW_SIGNATURE)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
