# -*- coding: utf-8 -*-
"""登记制护栏：README 里的图、`flow/diagrams/` 里的文件、`candidate*.json` 里的声明 —— 三者必须对得上。

动因（R47）
-----------
本轮把 13 张流程图从「只有可交互 HTML」变成「README 里直接看得见」：每个产物 HTML
都取出一份**独立 SVG**，落 `flow/diagrams/`，再嵌进两份 README。这件事有一个很典型的
退化方式：**图上写着，文件没了**（或反过来），而两边都不报错。

三种真实退化，全都不产生任何错误：
    README 里 `![](flow/diagrams/f07-ci-gate.svg)`，文件被改名/删掉  → 页面上一块裂图
    `flow/diagrams/` 里躺着一张没人引用的旧图                     → 静默堆积，且它可能已经过时
    只补了英文没补中文（或反过来）                                → 一侧读者看不到这张图
靠人记得核，等于没有核 —— R32 对双语 README 已经吃过这个亏（`check_readme_parity`）。

判据（只认装置，不认叙述）
--------------------------
六条来源两两对齐，且**每一对都双向**：

    D1 引用必须落地：四个文档里出现的每个 `flow/diagrams/*.svg`，都必须在磁盘上存在。
    D2 文件必须被用：`flow/diagrams/` 下的每个文件，都必须在某个文档里被提到过。← D1 的反向
    D3 中英必须成对：`X.svg` 有则 `X.zh-CN.svg` 必须也有，反之亦然。← 两个方向分别判
    D4 名字必须派生：每个 `candidate*.json` 的 `meta.output` 必须推出**恰好一个**文件名，
       该文件必须存在；反过来，磁盘上的每个文件都必须能由某个候选推出来。← 反向
       并且 `meta.locale` 与文件名后缀必须一致（`zh-CN` ↔ `.zh-CN`），
       否则「哪张是中文版」这件事就只剩约定、没有装置。
    D5 形态必须自足：每个 SVG 以 `<?xml` 开头；恰好一个 `<svg`；
       不含 `<script` / `<foreignObject` / `<image`，也不含**外部引用**
       （`url(...)` / `href=` / `src=` 后面跟 `http(s)://`）—— 独立打开时加载不到；
       含 `prefers-color-scheme`（双主题）与 `rect.c-bg-rect { fill: var(--bg); }`（自带背景）；
       **不含 CRLF** —— 它是渲染器的原始字节，这样「重跑渲染 == 仓库里的文件」才是可验证的等式。
    D6 中英必须同骨架：同一张图的两版，`data-node-id` 集合必须完全相同。
       这是 R46「清空字符串后结构逐键逐序相同」那条不变式在**产物**上的延续 ——
       中文版是从英文版复制、只换字符串生成的，几何一旦分叉，图就会对不上。
    D7 语言不得串台：`README.md` 只能引英文版，`README_CN.md` 只能引中文版，
       且两侧引用的**图的集合**必须相同（一侧多一张图 = 另一侧读者少一张图）。
    D8 交互产物也要对得上：README 里的图是**点得开**的，凡是引用了的
       `flow/archify/*.html` 必须存在；反过来，`flow/archify/` 下的每个 HTML
       也必须被某个文档引用。一条悬空的链接和一块裂图一样糟。← 两个方向分别判
    D9 索引必须与磁盘两向对齐：`flow/FLOW_INDEX.json` 是这套东西的**索引**，
       它登记了每个产物的路径**和体积**。所以判两件事：
         (a) 索引里登记的每个 `diagrams/*.svg` / `archify/*.html` 都在磁盘上，
             且声明的字节数与 `os.path.getsize` 相等（体积漂了 = 产物变了而索引没跟）；
         (b) 磁盘上的每个 SVG / HTML 都被索引登记过 —— 反过来漏登记也是坏索引。
       索引自己缺失或不是合法 JSON 同样算红。← 两个方向分别判
    D10 尺寸必须自洽：根 `<svg>` 标签的 `viewBox` 必须等于**同一标签自己**的
       `style` 里的 `width: Wpx; height: Hpx`，且四个数都是有限正数。
       独立 SVG 的 width/height **就是**它的渲染尺寸；两者分叉 ⇒ 缩放静默变形。
       （R47 三臂比对里第②个陷阱就是这么现形的：缩放不钉 1:1 时，
       `getComputedTextLength` 差 0.09–0.17px。）
    D11 内联字体必须是**同一套子集**：每个文件恰好 6 段 `@font-face`、
       6 段 `unicode-range`、6 个 `data:font/woff2`；**6 段 `src` 的 base64
       在 26 个文件之间逐字节相同**（同一套字体管线不该产出第二种结果 ——
       某一个文件漂了，就说明它被别的工具重新生成过，而渲染会跟着变）；
       且字体负载（base64 字符数合计）占文件字节比必须落在 (40%, 80%)。
       实测 51.6%–61.0%、每文件 88,366 字符、26 份完全相同。
    D12 语言必须落到文本层：英文版**一个中文字都不许有**；中文版必须**至少有一个**
       中文字（实测 154–615）。D6 只比骨架、D7 只比链接，都看不见「译文没落进产物」。
       并且内联 `unicode-range` 的并集**不得覆盖 CJK 基本区**（U+4E00–U+9FFF）：
       CJK 由宿主 fallback 渲染，内联进来会让每张图涨好几 MB。

为什么 D2/D4 的反方向不能省
    只判「引用了的要存在」，删掉文件必然红；但**多出来的文件是绿的** ——
    于是改名/重生成之后留下的旧文件会永久躺着，而没有任何东西会说它已经没人用了。
    登记表两向核对是本仓的既定纪律（子进程 / 退出码 / 护栏 / 帮助 / CI / 散文数字 / 基线）。

两向自证：28 个反例（引用悬空、孤儿文件、缺中/缺英、语言串台、两侧图集不等、
脚本/外链/CRLF/缺主题/缺背景、节点数漂移、候选名对不上、交互产物悬空/没人引用、
索引缺失/漏登记关键字段/体积漂移/多登记一条、viewBox 与 style 不一致、
字体少一段/字体被改一个字节、英文版混入中文/中文版丢了中文/字体子集盖了 CJK）必须全部抓到；
干净样本必须放行；最后对**真实仓库**再整体核对一次。

首轮自证就在这里抓到了我自己写的一条错判据：D5 原本写「含 `http://` 即红」，
结果 `xmlns="http://www.w3.org/2000/svg"` 会命中 —— **对每一张真图都判红**。
**一条永远变红的判据和一条永远不变红的判据一样没用**，所以只抓 `url(`/`href=`/`src=` 后面的外部地址。

R48 加 D10–D12 时，同一种错又踩了两回（都是**装置自己的 bug**，不是被检对象）：
  * D12 一度把 `unicode-range` 聚合成 `(min,max)` 再判交叠，而它是**若干不相交区间的并**
    —— 聚合把中间的空洞也算了进去，`U+0460-052F … U+FE2E-FE2F` 被判成「盖住了 CJK」，
    **对每一张真图都判红**（真实仓库实测 78 项）。改成**逐 token** 判才消掉。
  * 样本字体一度按每个文件自己的骨架长度反推填充长度，样本之间 `src` 就互不相同，
    D11 的「跨文件逐字节相同」去误伤了干净样本。真实产物共用同一串字节，样本也必须共用。
**每加一条判据，都要先问：它在干净样本上是绿的吗、在被污染的样本上是红的吗。**

用法：
    python tools/check_flow_diagrams.py             # 0=全部对齐 1=有不对齐 2=缺输入
    python tools/check_flow_diagrams.py --selftest   # 两向自证
    python tools/check_flow_diagrams.py --help       # 显示本帮助

退出码：
    0 = 六条来源两两对齐（含索引与 SVG 自身形态）
    1 = 发现不对齐（D1..D12 任一红）
    2 = 缺输入（缺文档 / 缺 flow/diagrams/ / 一个候选都找不到 → 红）
"""
import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile

EN = "README.md"
CN = "README_CN.md"
DOCS = (EN, CN, "flow/README.md", "flow/FLOW_REPORT.md")
DIAGRAM_DIR = "flow/diagrams"
ARCHIFY_DIR = "flow/archify"

# 只认这个形状的路径。用「出现」而不是「markdown 图片语法」来判：
# 一个写坏的 `![](...)`、一段 HTML、甚至一句散文里提到的不存在文件，
# 都应该被抓到 —— 判据宽进严出，比只认一种写法更难绕过。
REF_RE = re.compile(r"flow/diagrams/([A-Za-z0-9._-]+\.svg)")
# 交互产物（可点开的那 26 个 HTML）。README 里的图是**点得开**的 ——
# 一条悬空的链接和一块裂图一样糟，所以引用方向也要判。
HTML_REF_RE = re.compile(r"flow/archify/([A-Za-z0-9._/-]+\.html)")
NODE_RE = re.compile(r'data-node-id="([^"]*)"')

ZH_SUFFIX = ".zh-CN.svg"
FORBIDDEN = ("<script", "<foreignObject", "<image")
# ⚠ 判据不能写成「含 http://」—— 那样 `xmlns="http://www.w3.org/2000/svg"` 会命中，
# 等于对**每一张真图**判红。首轮自证就是这么抓到我自己的（干净样本被误伤 4 条）。
# 要抓的是**外部引用**：url(...)/href=/src= 后面跟 http(s)。
EXTERNAL_RE = re.compile(r"""(?:url\(|href=|src=)\s*["']?\s*https?://""")
BG_RULE = "rect.c-bg-rect { fill: var(--bg); }"

# D10：独立 SVG 的**渲染尺寸**。viewBox 必须等于同一标签自己 style 里的 width/height。
ROOT_TAG_RE = re.compile(r"<svg\b[^>]*>")
VIEWBOX_RE = re.compile(r'viewBox\s*=\s*"([^"]*)"')
STYLE_WH_RE = re.compile(r"width\s*:\s*([0-9.]+)px\s*;\s*height\s*:\s*([0-9.]+)px")

# D11：内联字体。同一套字体管线 ⇒ 26 个文件的子集必须是**同一串字节**。
FONTFACE_RE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)
FONT_SRC_RE = re.compile(r"url\(([^)]*)\)")
FONT_FACES = 6
# 带子下界防「字体被抹掉」、上界防「有人把 CJK 也内联进来」。实测 51.6%–61.0%，
# 两侧各留 ≥10 个百分点 —— 宽到不会误伤，又窄到能抓住结构性变化。
FONT_RATIO_LO, FONT_RATIO_HI = 0.40, 0.80

# D12：语言落到文本层；内联字体子集不得盖住 CJK 基本区。
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
URANGE_RE = re.compile(r"unicode-range\s*:\s*([^;]+)")
CJK_LO, CJK_HI = 0x4E00, 0x9FFF

# D9：索引。它的路径一律**相对 flow/**（`diagrams/x.svg`、`archify/d/x.html`），
# 与 INDEX.md 里的相对链接同源，所以在这里只加一层 `flow/` 前缀。
INDEX = "flow/FLOW_INDEX.json"
INDEX_KEYS = (("svg", "svg_bytes"), ("zh_svg", "zh_svg_bytes"),
              ("html", "html_bytes"), ("zh_html", "zh_html_bytes"))


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_text(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def read_bytes(path):
    with io.open(path, "rb") as fh:
        return fh.read()


# ----------------------------------------------------------- 六条来源的读入器

def doc_references(root):
    """返回 (refs, html_refs, missing_docs)。

    refs      : {文档: [独立 SVG 文件名...]}
    html_refs : {文档: [交互产物相对路径...]}（一律带 `flow/archify/` 前缀）
    """
    refs, html_refs, missing = {}, {}, []
    for rel in DOCS:
        p = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.exists(p):
            missing.append(rel)
            continue
        text = read_text(p)
        refs[rel] = REF_RE.findall(text)
        html_refs[rel] = ["flow/archify/" + m for m in HTML_REF_RE.findall(text)]
    return refs, html_refs, missing


def artifact_htmls(root):
    """`flow/archify/**/*.html` 全清单（相对仓库根，正斜杠）。"""
    base = os.path.join(root, ARCHIFY_DIR.replace("/", os.sep))
    out = []
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in filenames:
            if fn.endswith(".html"):
                abs_p = os.path.join(dirpath, fn)
                rel = os.path.relpath(abs_p, root).replace(os.sep, "/")
                out.append(rel)
    return sorted(out)


def candidate_declarations(root):
    """返回 (declared, bad)：{文件名: (候选相对路径, locale)} 与「推不出名字」的候选。"""
    base = os.path.join(root, ARCHIFY_DIR.replace("/", os.sep))
    declared, bad = {}, []
    if not os.path.isdir(base):
        return declared, bad
    for dirname in sorted(os.listdir(base)):
        d = os.path.join(base, dirname)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn != "candidate.json" and not (fn.startswith("candidate.") and fn.endswith(".json")):
                continue
            cpath = os.path.join(d, fn)
            rel = ARCHIFY_DIR + "/" + dirname + "/" + fn
            try:
                cand = json.loads(read_text(cpath))
            except ValueError as exc:
                bad.append("%s 不是合法 JSON（%s）" % (rel, exc))
                continue
            meta = cand.get("meta") or {}
            out = meta.get("output")
            locale = meta.get("locale")
            if not isinstance(out, str) or not out.endswith(".html"):
                bad.append("%s 的 meta.output 不是 .html：%r" % (rel, out))
                continue
            name = os.path.basename(out)[:-len(".html")] + ".svg"
            if name in declared:
                bad.append("%s 与 %s 推出同一个文件名 %s" % (rel, declared[name][0], name))
                continue
            declared[name] = (rel, locale)
    return declared, bad


def disk_files(root):
    d = os.path.join(root, DIAGRAM_DIR.replace("/", os.sep))
    if not os.path.isdir(d):
        return None
    return sorted(f for f in os.listdir(d) if f.endswith(".svg"))


def index_entries(root):
    """读 `flow/FLOW_INDEX.json`，返回 (svg 文件名集, html 相对路径集, 问题列表)。

    索引是「索引」—— 它和磁盘对不上就是坏索引，而且**两边都可能错**：
    漏登记（磁盘有、索引没有）和登记了不存在的东西（索引有、磁盘没有）都一样糟。
    体积一并判：产物体积变了而索引没跟，说明索引已经过期。
    """
    p = os.path.join(root, INDEX.replace("/", os.sep))
    if not os.path.isfile(p):
        return None, None, ["D9 缺索引 %s（无法核对产物清单）" % INDEX]
    try:
        recs = json.loads(read_text(p))
    except ValueError as exc:
        return None, None, ["D9 %s 不是合法 JSON（%s）" % (INDEX, exc)]
    if not isinstance(recs, list):
        return None, None, ["D9 %s 顶层不是数组" % INDEX]

    svg_names, html_paths, bad = set(), set(), []
    for i, rec in enumerate(recs):
        if not isinstance(rec, dict):
            bad.append("D9 %s[%d] 不是对象" % (INDEX, i))
            continue
        for key, bkey in INDEX_KEYS:
            rel = rec.get(key)
            if not isinstance(rel, str) or not rel:
                bad.append("D9 %s[%d] 缺字段 %s" % (INDEX, i, key))
                continue
            full = os.path.join(root, "flow", rel.replace("/", os.sep))
            if not os.path.isfile(full):
                bad.append("D9 %s[%d].%s 指向 %s，磁盘上没有" % (INDEX, i, key, rel))
                continue
            want, got = rec.get(bkey), os.path.getsize(full)
            if want != got:
                bad.append("D9 %s[%d].%s 声明 %r 字节，磁盘上是 %d（索引过期）"
                           % (INDEX, i, bkey, want, got))
            if key in ("svg", "zh_svg"):
                svg_names.add(os.path.basename(rel))
            else:
                html_paths.add("flow/" + rel)
    return svg_names, html_paths, bad


# ---------------------------------------------------------------- 判据

def urange_hits_cjk(seg, lo_bound, hi_bound):
    """这段 `unicode-range` 是否与 [lo_bound, hi_bound] **相交**。

    ⚠ **必须逐 token 判，不能聚合成 (min,max)** —— `unicode-range` 是**若干不相交
    区间的并**，聚合出来的跨度会把中间的空洞也算进去。R48 首轮自证就栽在这上面：
    `U+0460-052F, …, U+FE2E-FE2F` 聚合后是 0x0460–0xFE2F，**数值上盖住了** U+4E00–U+9FFF，
    于是对**每一张真图**都判红（真实仓库 78 项假红）。
    和 R47 的 D5 是同一类错误：**一条永远变红的判据和一条永远不变红的判据一样没用**。

    返回 True/False；解析不动返回 None。
    """
    for tok in seg.split(","):
        m = re.match(r"^U\+([0-9A-Fa-f]{1,6})(?:-([0-9A-Fa-f]{1,6}))?$", tok.strip())
        if not m:
            return None
        a = int(m.group(1), 16)
        b = int(m.group(2), 16) if m.group(2) else a
        if not (b < lo_bound or a > hi_bound):
            return True
    return False


def audit(root, on_problem):
    """施加 D1..D12。返回 (引用条数, 文件数, 候选数)，供调用方判断「缺输入」。"""
    refs, html_refs, missing_docs = doc_references(root)
    for rel in missing_docs:
        on_problem("D0 文档不存在：%s（缺输入 → 红）" % rel)
    if missing_docs:
        return 0, 0, 0

    files = disk_files(root)
    if files is None:
        on_problem("D0 找不到 %s（缺输入 → 红）" % DIAGRAM_DIR)
        return 0, 0, 0
    declared, bad_cand = candidate_declarations(root)
    for msg in bad_cand:
        on_problem("D4 " + msg)
    if not declared and not files:
        on_problem("D0 既没有候选也没有产物（缺输入 → 红）")
        return 0, 0, 0

    fileset = set(files)
    n_refs = 0

    # ---- D1：引用的必须存在
    for rel in DOCS:
        for name in refs.get(rel, []):
            n_refs += 1
            if name not in fileset:
                on_problem("D1 %s 引用了不存在的图：%s" % (rel, name))

    # ---- D2：存在的必须被引用（D1 的反方向）
    mentioned = set()
    for rel in DOCS:
        mentioned.update(refs.get(rel, []))
    for name in files:
        if name not in mentioned:
            on_problem("D2 %s 没有任何文档引用它（孤儿产物）" % name)

    # ---- D3：中英成对，两个方向分别判
    for name in files:
        if name.endswith(ZH_SUFFIX):
            twin = name[:-len(ZH_SUFFIX)] + ".svg"
        else:
            twin = name[:-len(".svg")] + ZH_SUFFIX
        if twin not in fileset:
            on_problem("D3 %s 缺少配对版 %s（中英必须成对）" % (name, twin))

    # ---- D4：名字必须由候选派生（正反两个方向）+ locale 后缀必须自洽
    for name, (rel, locale) in sorted(declared.items()):
        if name not in fileset:
            on_problem("D4 %s 声明产出 %s，但该文件不存在" % (rel, name))
        is_zh = name.endswith(ZH_SUFFIX)
        if is_zh != (locale == "zh-CN"):
            on_problem("D4 %s 的 meta.locale=%r 与文件名 %s 对不上" % (rel, locale, name))
    for name in files:
        if name not in declared:
            on_problem("D4 %s 推不出对应的候选（没有 candidate*.json 声明它）" % name)

    # ---- D5：形态必须自足（静态可判，不建浏览器）
    for name in files:
        raw = read_bytes(os.path.join(root, DIAGRAM_DIR.replace("/", os.sep), name))
        text = raw.decode("utf-8", "replace")
        if not text.startswith("<?xml"):
            on_problem("D5 %s 没有 XML 声明（编码会被下游猜错）" % name)
        if text.count("<svg") != 1:
            on_problem("D5 %s 里 <svg 出现 %d 次，期望恰好 1 次" % (name, text.count("<svg")))
        for bad in FORBIDDEN:
            if bad in text:
                on_problem("D5 %s 含 %r（独立打开时加载不到 / 会被宿主剥掉）" % (name, bad))
        m_ext = EXTERNAL_RE.search(text)
        if m_ext:
            on_problem("D5 %s 含外部引用 %r（独立打开时加载不到）" % (name, m_ext.group(0)))
        if "prefers-color-scheme" not in text:
            on_problem("D5 %s 没有 prefers-color-scheme 分支（双主题不成立）" % name)
        if BG_RULE not in text:
            on_problem("D5 %s 没有 %r（脱离宿主后没有背景）" % (name, BG_RULE))
        if b"\r\n" in raw:
            on_problem("D5 %s 是 CRLF —— 生成物必须保留渲染器原始字节（LF）" % name)

    # ---- D6：同一张图的两版必须同骨架
    for name in files:
        if name.endswith(ZH_SUFFIX):
            continue
        zh = name[:-len(".svg")] + ZH_SUFFIX
        if zh not in fileset:
            continue
        a = sorted(NODE_RE.findall(read_text(
            os.path.join(root, DIAGRAM_DIR.replace("/", os.sep), name))))
        b = sorted(NODE_RE.findall(read_text(
            os.path.join(root, DIAGRAM_DIR.replace("/", os.sep), zh))))
        if a != b:
            on_problem("D6 %s 与 %s 的 data-node-id 集合不同（%d vs %d；骨架分叉了）"
                       % (name, zh, len(a), len(b)))

    # ---- D7：语言不得串台，且两侧引用的图集必须相同
    def stems(rel, want_zh):
        out = set()
        for name in refs.get(rel, []):
            is_zh = name.endswith(ZH_SUFFIX)
            if is_zh != want_zh:
                on_problem("D7 %s 引用了%s版：%s"
                           % (rel, "中文" if is_zh else "英文", name))
                continue
            out.add(name[:-len(ZH_SUFFIX)] if is_zh else name[:-len(".svg")])
        return out

    en_set = stems(EN, False)
    cn_set = stems(CN, True)
    for only_en in sorted(en_set - cn_set):
        on_problem("D7 %s 有 %s，%s 缺这张（一侧读者看不到）" % (EN, only_en, CN))
    for only_cn in sorted(cn_set - en_set):
        on_problem("D7 %s 有 %s，%s 缺这张（一侧读者看不到）" % (CN, only_cn, EN))

    # ---- D8：交互产物（可点开的那 26 个 HTML）两个方向都要对
    htmls = artifact_htmls(root)
    html_set = set(htmls)
    mentioned_html = set()
    for rel in DOCS:
        for hp in html_refs.get(rel, []):
            mentioned_html.add(hp)
            if hp not in html_set:
                on_problem("D8 %s 引用了不存在的交互产物：%s" % (rel, hp))
    for hp in htmls:
        if hp not in mentioned_html:
            on_problem("D8 %s 没有被任何文档引用（点了也到不了）" % hp)

    # ---- D9：索引必须与磁盘两向对齐（路径 + 体积）
    idx_svgs, idx_htmls, idx_bad = index_entries(root)
    for msg in idx_bad:
        on_problem(msg)
    if idx_svgs is not None:
        for name in sorted(fileset - idx_svgs):
            on_problem("D9 %s 在磁盘上，但 %s 里查不到它（漏登记）" % (name, INDEX))
        for name in sorted(idx_svgs - fileset):
            on_problem("D9 %s 登记了 %s，磁盘上没有（索引指着空气）" % (INDEX, name))
        for hp in sorted(html_set - idx_htmls):
            on_problem("D9 %s 在磁盘上，但 %s 里查不到它（漏登记）" % (hp, INDEX))
        for hp in sorted(idx_htmls - html_set):
            on_problem("D9 %s 登记了 %s，磁盘上没有（索引指着空气）" % (INDEX, hp))

    # ---- D10：尺寸必须自洽（viewBox == 同一标签自己 style 的 width/height）
    for name in files:
        text = read_text(os.path.join(root, DIAGRAM_DIR.replace("/", os.sep), name))
        mtag = ROOT_TAG_RE.search(text)
        if not mtag:
            on_problem("D10 %s 找不到根 <svg> 标签" % name)
            continue
        tag = mtag.group(0)
        mvb = VIEWBOX_RE.search(tag)
        mwh = STYLE_WH_RE.search(tag)
        if not mvb or not mwh:
            on_problem("D10 %s 根标签缺 viewBox 或缺 style 里的 width/height" % name)
            continue
        try:
            nums = [float(x) for x in mvb.group(1).replace(",", " ").split()]
        except ValueError:
            nums = []
        if len(nums) != 4:
            on_problem("D10 %s 的 viewBox 不是 4 个数：%r" % (name, mvb.group(1)))
            continue
        w, h = float(mwh.group(1)), float(mwh.group(2))
        if not (nums[2] > 0 and nums[3] > 0 and w > 0 and h > 0):
            on_problem("D10 %s 的尺寸不是正数（viewBox=%r style=%gx%g）"
                       % (name, mvb.group(1), w, h))
            continue
        if nums[2] != w or nums[3] != h:
            on_problem("D10 %s 的 viewBox %gx%g 与 style %gx%g 不一致 —— 缩放会静默变形"
                       % (name, nums[2], nums[3], w, h))

    # ---- D11：内联字体必须是同一套子集，且负载占比在带内
    font_ref = None
    font_ref_name = None
    for name in files:
        raw = read_bytes(os.path.join(root, DIAGRAM_DIR.replace("/", os.sep), name))
        text = raw.decode("utf-8", "replace")
        faces = FONTFACE_RE.findall(text)
        if len(faces) != FONT_FACES:
            on_problem("D11 %s 有 %d 段 @font-face，期望 %d 段"
                       % (name, len(faces), FONT_FACES))
        n_ur = len(URANGE_RE.findall(text))
        if n_ur != FONT_FACES:
            on_problem("D11 %s 有 %d 段 unicode-range，期望 %d 段"
                       % (name, n_ur, FONT_FACES))
        n_woff = text.count("data:font/woff2")
        if n_woff != FONT_FACES:
            on_problem("D11 %s 有 %d 个 data:font/woff2，期望 %d 个"
                       % (name, n_woff, FONT_FACES))
        srcs = [FONT_SRC_RE.search(b).group(1) for b in faces if FONT_SRC_RE.search(b)]
        payload = sum(len(s) for s in srcs)
        ratio = (payload / len(raw)) if raw else 0.0
        if not (FONT_RATIO_LO <= ratio <= FONT_RATIO_HI):
            on_problem("D11 %s 的字体负载占比 %.1f%% 掉出 (%.0f%%, %.0f%%) —— 内联字体漂了"
                       % (name, ratio * 100, FONT_RATIO_LO * 100, FONT_RATIO_HI * 100))
        if font_ref is None:
            font_ref, font_ref_name = srcs, name
        elif srcs != font_ref:
            on_problem("D11 %s 的内联字体子集与 %s 不同（同一套字体管线不该有第二种结果）"
                       % (name, font_ref_name))

    # ---- D12：语言必须落到文本层；字体子集不得盖住 CJK
    for name in files:
        text = read_text(os.path.join(root, DIAGRAM_DIR.replace("/", os.sep), name))
        n_cjk = len(CJK_RE.findall(text))
        if name.endswith(ZH_SUFFIX):
            if n_cjk == 0:
                on_problem("D12 %s 一个中文字都没有 —— 译文没落进产物（或只剩英文）" % name)
        elif n_cjk != 0:
            on_problem("D12 %s 是英文版却含 %d 个中文字（语言串台到文本层）" % (name, n_cjk))
        for seg in URANGE_RE.findall(text):
            hit = urange_hits_cjk(seg, CJK_LO, CJK_HI)
            if hit is None:
                on_problem("D12 %s 的 unicode-range 解析不动：%r" % (name, seg.strip()[:60]))
                continue
            if hit:
                on_problem("D12 %s 的 unicode-range 盖住了 CJK 基本区（%s）—— "
                           "中文应由宿主 fallback 渲染，内联会让体积暴涨"
                           % (name, seg.strip()[:60]))

    return n_refs, len(files), len(declared)


def on_problem_collector(bucket):
    def _cb(msg):
        bucket.append(msg)
    return _cb


# ---------------------------------------------------------------- 自证

FIXTURE_FONT_FACES = 6
FIXTURE_FONT_RATIO = 0.55
FONT_PRE = "data:font/woff2;base64,"
THEME_LINE = "@media (prefers-color-scheme: light) { :root, svg { --bg: #fff; } }\n"
_FIXTURE_PAD = None


def _face(i, pad):
    return ("@font-face { font-family: 'JB%d'; font-style: normal; "
            "src: url(%s%s) format('woff2'); "
            "unicode-range: U+0000-00FF; }\n" % (i, FONT_PRE, "A" * pad))


def _assemble(node_ids, theme, bg, fonts, extra, label, w, h, sw, sh):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %g %g" '
            'style="width: %gpx; height: %gpx;"><style>\n' % (w, h, sw, sh)
            + theme + bg + fonts + '</style>' + extra
            + '<text data-node-id="title">%s</text>' % label
            + '<rect class="c-bg-rect" x="0" y="0" width="%g" height="%g"/>' % (w, h)
            + "".join('<g data-node-id="%s"/>' % n for n in node_ids)
            + '</svg>\n')


def _fixture_pad():
    """按目标占比反推 base64 填充长度；**全局只算一次、所有样本共用**。

    为什么必须共用：真实产物的 6 段 `src` 在 26 个文件里是**同一串字节**。
    若按每个样本自己的骨架长度算 pad，样本之间字体就互不相同，
    D11 的「跨文件逐字节相同」会去误伤干净样本（首轮自证实测：f02-b 被判与 f01-a 不同）。
    """
    global _FIXTURE_PAD
    if _FIXTURE_PAD is None:
        ref = _assemble(["n1", "n2"], THEME_LINE, BG_RULE + "\n",
                        "".join(_face(i, 0) for i in range(FIXTURE_FONT_FACES)),
                        "", "Title", 10, 10, 10, 10)
        n = FIXTURE_FONT_FACES
        _FIXTURE_PAD = max(8, int(
            (FIXTURE_FONT_RATIO * len(ref) - n * len(FONT_PRE))
            / (n * (1 - FIXTURE_FONT_RATIO))))
    return _FIXTURE_PAD


def _svg(node_ids, extra="", crlf=False, drop_theme=False, drop_bg=False,
         cjk=False, vb=(10, 10), style_wh=None):
    """造一张**形态完整**的样本 SVG。

    必须完整：D10 看 viewBox/style、D11 数 6 段字体、D12 数中文字。
    样本缺了这些，「干净样本」就会因为判据而红 —— 那是自检装置自身的 bug。
    """
    w, h = vb
    sw, sh = style_wh if style_wh else (w, h)
    theme = "" if drop_theme else THEME_LINE
    bg = "" if drop_bg else BG_RULE + "\n"
    fonts = "".join(_face(i, _fixture_pad()) for i in range(FIXTURE_FONT_FACES))
    label = "中文标题" if cjk else "Title"
    text = _assemble(node_ids, theme, bg, fonts, extra, label, w, h, sw, sh)
    if crlf:
        return text.replace("\n", "\r\n")
    return text


def _write(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _resync_index(root):
    """把样本索引里声明的体积按磁盘重算（只重算体积，路径一条不动）。

    为什么必须做：`_fixture` 的索引体积是**实测**的（不实测，就等于把「索引对不对」
    从判据里删掉）。于是**任何**改写 SVG 的退化都会顺手让 D9 的体积判据变红 ——
    那样 D10/D11/D12 永远拿不到「独立证人」（R44 的纪律：变异必须由**它该抓的那条**
    判据抓到）。索引类退化不重算，它就是要坏。
    """
    p = os.path.join(root, INDEX)
    if not os.path.exists(p):
        return
    recs = json.loads(read_text(p))
    for r in recs:
        for key, bkey in (("svg", "svg_bytes"), ("zh_svg", "zh_svg_bytes"),
                          ("html", "html_bytes"), ("zh_html", "zh_html_bytes")):
            rel = r.get(key)
            if not rel:
                continue
            f = os.path.join(root, "flow", rel)
            if os.path.exists(f):
                r[bkey] = os.path.getsize(f)
    _write(p, json.dumps(recs, ensure_ascii=False, indent=2) + "\n")


def _fixture(root):
    """造一棵**干净**的样本树：2 张图 × 2 语言 + 4 个候选。"""
    P = {
        "f01-a.svg": ("d1/candidate.json", "archify/d1/f01-a.html", "en", ["n1", "n2"]),
        "f01-a.zh-CN.svg": ("d2/candidate.zh-CN.json", "archify/d2/f01-a.zh-CN.html", "zh-CN", ["n1", "n2"]),
        "f02-b.svg": ("d3/candidate.json", "archify/d3/f02-b.html", "en", ["m1", "m2", "m3"]),
        "f02-b.zh-CN.svg": ("d4/candidate.zh-CN.json", "archify/d4/f02-b.zh-CN.html", "zh-CN", ["m1", "m2", "m3"]),
    }
    for name, (crel, out, locale, nodes) in P.items():
        _write(os.path.join(root, DIAGRAM_DIR, name),
               _svg(nodes, cjk=name.endswith(ZH_SUFFIX)))
        _write(os.path.join(root, ARCHIFY_DIR, crel),
               json.dumps({"meta": {"output": out, "locale": locale}}, ensure_ascii=False))
        # 交互产物本体。D8 的两个方向都要数它 —— 样本里不造出来，
        # 「干净样本」就会因为「有 HTML 没人引用」而被误伤。
        _write(os.path.join(root, "flow", out), "<html></html>\n")
    _write(os.path.join(root, EN),
           "# T\n\n[![a](flow/diagrams/f01-a.svg)](flow/archify/d1/f01-a.html)\n\n"
           "[![b](flow/diagrams/f02-b.svg)](flow/archify/d3/f02-b.html)\n")
    _write(os.path.join(root, CN),
           "# 标题\n\n[![甲](flow/diagrams/f01-a.zh-CN.svg)](flow/archify/d2/f01-a.zh-CN.html)\n\n"
           "[![乙](flow/diagrams/f02-b.zh-CN.svg)](flow/archify/d4/f02-b.zh-CN.html)\n")
    _write(os.path.join(root, "flow", "README.md"),
           "# flow\n\n[![a](flow/diagrams/f01-a.svg)](flow/archify/d1/f01-a.html)\n")
    _write(os.path.join(root, "flow", "FLOW_REPORT.md"),
           "# 报告\n\n[![乙](flow/diagrams/f02-b.zh-CN.svg)]"
           "(flow/archify/d4/f02-b.zh-CN.html)\n")
    # 索引。D9 要求它和磁盘两向对齐，所以样本里的路径与体积**必须实测**，
    # 不能手写一个数 —— 手写就等于把「索引对不对」这件事从判据里删掉了。
    recs = []
    for stem, en_html, zh_html in (
            ("f01-a", "archify/d1/f01-a.html", "archify/d2/f01-a.zh-CN.html"),
            ("f02-b", "archify/d3/f02-b.html", "archify/d4/f02-b.zh-CN.html")):
        recs.append({
            "fid": stem[:3].upper(),
            "export": stem + ".mmd",
            "svg": "diagrams/%s.svg" % stem,
            "svg_bytes": os.path.getsize(os.path.join(root, DIAGRAM_DIR, stem + ".svg")),
            "zh_svg": "diagrams/%s.zh-CN.svg" % stem,
            "zh_svg_bytes": os.path.getsize(
                os.path.join(root, DIAGRAM_DIR, stem + ".zh-CN.svg")),
            "html": en_html,
            "html_bytes": os.path.getsize(os.path.join(root, "flow", en_html)),
            "zh_html": zh_html,
            "zh_html_bytes": os.path.getsize(os.path.join(root, "flow", zh_html)),
        })
    _write(os.path.join(root, INDEX),
           json.dumps(recs, ensure_ascii=False, indent=2) + "\n")
    return P


def _damage(root, kind):
    """施加一个退化，返回是否成功施加（施加不上就必须算红，否则自证是假的）。"""
    D = os.path.join(root, DIAGRAM_DIR)
    p = lambda n: os.path.join(D, n)  # noqa: E731
    if kind == "ref-missing":
        _write(os.path.join(root, EN),
               read_text(os.path.join(root, EN)) + "\n![x](flow/diagrams/f99-ghost.svg)\n")
    elif kind == "orphan-file":
        _write(p("f03-c.svg"), _svg(["z1"]))
    elif kind == "unreferenced":
        _write(p("f03-c.svg"), _svg(["z1"]))
        _write(p("f03-c.zh-CN.svg"), _svg(["z1"], cjk=True))
        _write(os.path.join(root, ARCHIFY_DIR, "d5", "candidate.json"),
               json.dumps({"meta": {"output": "archify/d5/f03-c.html", "locale": "en"}}))
        _write(os.path.join(root, ARCHIFY_DIR, "d5", "candidate.zh-CN.json"),
               json.dumps({"meta": {"output": "archify/d5/f03-c.zh-CN.html", "locale": "zh-CN"}}))
        _write(os.path.join(root, "flow", "archify", "d5", "f03-c.html"), "<html></html>\n")
        _write(os.path.join(root, "flow", "archify", "d5", "f03-c.zh-CN.html"), "<html></html>\n")
    elif kind == "html-ref-missing":
        _write(os.path.join(root, EN),
               read_text(os.path.join(root, EN)) +
               "\n[![x](flow/diagrams/f01-a.svg)](flow/archify/d9/nope.html)\n")
    elif kind == "html-orphan":
        _write(os.path.join(root, "flow", "archify", "d1", "f01-a.extra.html"), "<html></html>\n")
    elif kind == "pair-missing-zh":
        os.remove(p("f01-a.zh-CN.svg"))
        _write(os.path.join(root, CN), "# 标题\n\n![乙](flow/diagrams/f02-b.zh-CN.svg)\n")
    elif kind == "pair-missing-en":
        os.remove(p("f02-b.svg"))
        _write(os.path.join(root, EN), "# T\n\n![a](flow/diagrams/f01-a.svg)\n")
    elif kind == "locale-swap":
        _write(os.path.join(root, CN), "# 标题\n\n![甲](flow/diagrams/f01-a.svg)\n\n"
                                       "![乙](flow/diagrams/f02-b.zh-CN.svg)\n")
    elif kind == "doc-set-mismatch":
        _write(os.path.join(root, EN), "# T\n\n![a](flow/diagrams/f01-a.svg)\n")
    elif kind == "script-in-svg":
        _write(p("f01-a.svg"), _svg(["n1", "n2"], extra="<script>x</script>"))
    elif kind == "external-url":
        _write(p("f01-a.svg"), _svg(["n1", "n2"], extra='<image href="https://x/y.png"/>'))
    elif kind == "crlf":
        _write(p("f01-a.svg"), _svg(["n1", "n2"], crlf=True))
    elif kind == "drop-theme":
        _write(p("f01-a.svg"), _svg(["n1", "n2"], drop_theme=True))
    elif kind == "drop-bg":
        _write(p("f01-a.svg"), _svg(["n1", "n2"], drop_bg=True))
    elif kind == "node-drift":
        _write(p("f02-b.zh-CN.svg"), _svg(["m1", "m2"], cjk=True))
    elif kind == "bad-candidate-name":
        _write(os.path.join(root, ARCHIFY_DIR, "d1", "candidate.json"),
               json.dumps({"meta": {"output": "archify/d1/zzz.html", "locale": "en"}}))
    elif kind == "bad-locale-suffix":
        _write(os.path.join(root, ARCHIFY_DIR, "d1", "candidate.json"),
               json.dumps({"meta": {"output": "archify/d1/f01-a.html", "locale": "zh-CN"}}))
    elif kind == "missing-doc":
        os.remove(os.path.join(root, "flow", "README.md"))
    elif kind == "index-missing":
        os.remove(os.path.join(root, INDEX))
    elif kind == "index-drop-field":
        recs = json.loads(read_text(os.path.join(root, INDEX)))
        del recs[0]["svg"]
        _write(os.path.join(root, INDEX),
               json.dumps(recs, ensure_ascii=False, indent=2) + "\n")
    elif kind == "index-bytes-drift":
        recs = json.loads(read_text(os.path.join(root, INDEX)))
        recs[1]["svg_bytes"] = recs[1]["svg_bytes"] + 1
        _write(os.path.join(root, INDEX),
               json.dumps(recs, ensure_ascii=False, indent=2) + "\n")
    elif kind == "index-ghost-entry":
        recs = json.loads(read_text(os.path.join(root, INDEX)))
        ghost = dict(recs[0])
        ghost["svg"] = "diagrams/f99-ghost.svg"
        ghost["zh_svg"] = "diagrams/f99-ghost.zh-CN.svg"
        recs.append(ghost)
        _write(os.path.join(root, INDEX),
               json.dumps(recs, ensure_ascii=False, indent=2) + "\n")
    elif kind == "viewbox-mismatch":
        _write(p("f01-a.svg"), _svg(["n1", "n2"], style_wh=(10, 9)))
    elif kind == "font-drift":
        t = read_text(p("f02-b.zh-CN.svg"))
        i = t.find("@font-face")
        j = t.find("@font-face", i + 1)
        _write(p("f02-b.zh-CN.svg"), t[:i] + t[j:])
    elif kind == "font-variant":
        t = read_text(p("f01-a.svg"))
        k = t.find("base64,")
        t = t[:k + 7] + ("B" if t[k + 7] == "A" else "A") + t[k + 8:]
        _write(p("f01-a.svg"), t)
    elif kind == "cjk-in-en":
        _write(p("f01-a.svg"), _svg(["n1", "n2"], cjk=True))
    elif kind == "cjk-lost-in-zh":
        _write(p("f01-a.zh-CN.svg"),
               read_text(p("f01-a.zh-CN.svg")).replace("中文标题", "Title"))
    elif kind == "cjk-subset-inlined":
        _write(p("f01-a.svg"), read_text(p("f01-a.svg")).replace(
            "unicode-range: U+0000-00FF;", "unicode-range: U+4E00-9FFF;", 1))
    else:
        return False
    if not kind.startswith("index-"):
        # 只把**体积**同步回来；索引类退化不碰，它坏得就是索引本身。
        _resync_index(root)
    return True


BAD_KINDS = ("ref-missing", "orphan-file", "unreferenced", "pair-missing-zh",
             "pair-missing-en", "locale-swap", "doc-set-mismatch", "script-in-svg",
             "external-url", "crlf", "drop-theme", "drop-bg", "node-drift",
             "bad-candidate-name", "bad-locale-suffix", "missing-doc",
             "html-ref-missing", "html-orphan",
             "index-missing", "index-drop-field", "index-bytes-drift",
             "index-ghost-entry",
             "viewbox-mismatch", "font-drift", "font-variant",
             "cjk-in-en", "cjk-lost-in-zh", "cjk-subset-inlined")

# 「这条判据有没有独立证人」—— R44 的纪律：变异必须**由它该抓的那条判据**抓到，
# 被别的判据顺手抓走 ⇒ 该判据其实没被证明。索引类归 D9，形态类各归各的 D。
WITNESS = {
    "viewbox-mismatch": "D10",
    "font-drift": "D11",
    "font-variant": "D11",
    "cjk-in-en": "D12",
    "cjk-lost-in-zh": "D12",
    "cjk-subset-inlined": "D12",
}


def _selftest():
    """两向自证：坏样本必须红、好样本必须过。

    expect 的第一个布尔是「判据认为有问题」—— 也就是这道门会变红的那个值。
    """
    bad = good = 0
    fails = []

    def expect(tag, detected, want_problem):
        ok = (bool(detected) == bool(want_problem))
        print("  [%s] %-46s -> %s%s"
              % ("反例" if want_problem else "正例", tag,
                 "抓到" if detected else "放行",
                 "" if ok else "   *** 不符预期 ***"))
        if not ok:
            fails.append(tag)

    def run(root):
        probs = []
        counts = audit(root, on_problem_collector(probs))
        return probs, counts

    tmp = tempfile.mkdtemp(prefix="chk_flow_")
    try:
        # 正例：干净样本必须一条问题都没有
        clean = os.path.join(tmp, "clean")
        _fixture(clean)
        probs, counts = run(clean)
        n_refs, n_files, n_cand = counts
        good += 1
        if probs:
            bad += 1
            fails.append("clean")
            print("  [反例] 干净样本被误伤 -> %d 条：%s" % (len(probs), probs[:3]))
        else:
            print("  [正例] %-46s -> 放行（引用 %d 条 / 文件 %d 个 / 候选 %d 个）"
                  % ("干净样本一条问题都没有", n_refs, n_files, n_cand))

        # 正例：判据必须真的把三路计数都数进去了（否则「全绿」可能只是因为什么都没看）
        good += 1
        if n_refs >= 4 and n_files == 4 and n_cand == 4:
            print("  [正例] %-46s -> 放行" % "三路计数都被数到（≥4/4/4）")
        else:
            bad += 1
            fails.append("counts")
            print("  [反例] 条数不对：refs=%d files=%d cands=%d" % (n_refs, n_files, n_cand))

        # 正例：文档串里写的反例数必须等于真实反例数。
        # 「散文里的数字是宣称」—— 加/删一个反例却忘了改文档串，这条会红。
        good += 1
        m = re.search(r"(\d+) 个反例", __doc__ or "")
        if m and int(m.group(1)) == len(BAD_KINDS):
            print("  [正例] %-46s -> 放行（%d 个）"
                  % ("文档串里的反例数 == 真实反例数", len(BAD_KINDS)))
        else:
            bad += 1
            fails.append("docstring-case-count")
            print("  [反例] 文档串写 %r，真实 %d 个反例"
                  % (m.group(1) if m else None, len(BAD_KINDS)))

        # 反例：逐个退化都必须被抓到
        for kind in BAD_KINDS:
            case = os.path.join(tmp, kind)
            _fixture(case)
            if not _damage(case, kind):
                bad += 1
                fails.append(kind + "(施加失败)")
                print("  [反例] %-46s -> *** 退化施加不上，自证无效 ***" % kind)
                continue
            probs, _ = run(case)
            want = len(probs) > 0
            if want:
                bad += 1
                # 索引类退化要求 **D9 自己是证人**：若被 D2/D8 顺手抓到，
                # D9 就没有独立证人（R44 的教训：变异被别的判据抓走 = 该判据未被证明）。
                wit = ""
                want_tag = "D9" if kind.startswith("index-") else WITNESS.get(kind)
                if want_tag:
                    only = [pr for pr in probs if pr.startswith(want_tag)]
                    if len(only) == len(probs):
                        wit = "  ← %s 独立作证" % want_tag
                    else:
                        wit = "  *** %s 不是唯一证人：%s ***" % (want_tag, probs[:2],)
                        fails.append(kind + "(%s 无独立证人)" % want_tag)
                print("  [反例] %-46s -> 抓到（%d 条：%s）%s"
                      % (kind, len(probs), probs[0][:60], wit))
            else:
                good += 1
                fails.append(kind)
                print("  [反例] %-46s -> *** 漏了 ***" % kind)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 最后：对**真实仓库**整体核对一次。
    # 只测「纯函数在合成样本上对不对」是不够的 —— 合成样本可以永远绿，
    # 而真实仓库已经烂了。这一条把自证和现状钉在一起。
    root = repo_root()
    if not os.path.isdir(os.path.join(root, DIAGRAM_DIR.replace("/", os.sep))):
        print("  真实仓库：没有 %s（先跑提取脚本）" % DIAGRAM_DIR)
        fails.append("真实仓库缺产物目录")
        bad += 1
    else:
        b = []
        n_refs, n_files, n_cand = audit(root, on_problem_collector(b))
        print("  真实仓库：引用 %d 条 / 产物 %d 个 / 候选 %d 个，发现 %d 项不对齐"
              % (n_refs, n_files, n_cand, len(b)))
        for p in b[:10]:
            print("      " + p)
        if b:
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
    probs = []
    n_refs, n_files, n_cand = audit(root, on_problem_collector(probs))
    if n_files == 0 and n_cand == 0:
        print("check_flow_diagrams: 缺输入 —— 没找到产物或候选（红）")
        return 2
    if probs:
        print("check_flow_diagrams: %d 项不对齐" % len(probs))
        for p in probs[:40]:
            print("  - " + p)
        if len(probs) > 40:
            print("  ...（还有 %d 条）" % (len(probs) - 40))
        return 1
    print("check_flow_diagrams: OK（引用 %d 条 / 产物 %d 个 / 候选 %d 个，"
          "D1–D12 全绿）" % (n_refs, n_files, n_cand))
    return 0


if __name__ == "__main__":
    sys.exit(main())
