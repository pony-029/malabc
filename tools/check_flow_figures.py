# -*- coding: utf-8 -*-
"""登记制护栏：`flow/index.html` ⇄ `flow/figures/` ⇄ `figures/*/candidate.json` 三向对齐。

为什么需要它（本轮实测）
------------------------
`flow/archify/` 那套体系由 `check_flow_diagrams.py`（D1–D12）守着，它的判据族
预设了「中英双版 + 独立 SVG + FLOW_INDEX.json」。2026-10-17 新增的 11 张单语交互图
如果放进 `flow/archify/`，会**真实地**打红 40 项（D3 缺配对、D4 缺 SVG、D8 无人引用、
D9 漏登记）—— 本轮第一步就是先看它红，再决定分类，而不是改门禁去迁就产物。

正确的分类是：单语交互图归 `flow/figures/`，既有双版体系原样保留。
但「归到别处」不等于「没有门」：本门就是 `figures/` 的对手方。

判据（每条都能单独打红）
------------------------
    FF1 索引必须落地：`flow/index.html` 里每个站内 `href` 都必须在磁盘上存在
       （`.html` / `.json` / `.md` 三类；`#` 锚点与 `http(s)` 不算站内）。
    FF2 产物必须被索引：`flow/figures/*/*.html` 每个文件都必须在 index.html 里出现。
       ← FF1 的反方向。只判单向的话，改名/重生成留下的旧图会永久躺着。
    FF3 候选必须推出产物：每个 `figures/*/candidate.json` 的 `meta.output`
       必须推出**恰好一个** `.html`，且该文件存在；反过来，每个 `.html`
       必须能由某个候选推出。locale 必须是 `zh-CN`（单语体系的口径）。
    FF4 编号必须唯一且不与既有冲突：index.html 里 `F\\d\\d` 徽章不得重复；
       编号 ≥ 14 的卡片数必须等于 `figures/` 目录数（一张图一个编号）。
    FF5 索引页必须自足：不含 `<script`、不含外部 `href="http`、含
       `prefers-color-scheme`（双主题）、含 `viewport`（移动端不被裁）。

两向自证（8 个反例 + 1 个好样本）
--------------------------------
FF1 悬空链接 / FF2 孤儿产物 / FF3 候选指向不存在 / FF3 产物无候选 /
FF4 编号重复 / FF4 编号数与目录数不等 / FF5 含脚本 / FF5 含外链或缺 viewport
—— 每一个都必须被抓到；干净样本必须放行。

用法：
    python tools/check_flow_figures.py             # 0=全绿 1=有不对齐 2=缺输入
    python tools/check_flow_figures.py --selftest   # 两向自证
    python tools/check_flow_figures.py --help       # 显示本帮助

退出码：
    0 = 三向对齐（索引无死链 / 产物无孤儿 / 候选能推出产物 / 编号唯一 / 索引页自足）
    1 = 发现不对齐（FF1–FF5 任一红）
    2 = 缺输入（找不到 flow/index.html 或 flow/figures/）
"""
import argparse
import ast
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROW_SIGNATURE = "FF1–FF7"

INDEX = "flow/index.html"
FIGURES = "flow/figures"
ID_RE = re.compile(r'<span class="id">(F\d\d)</span>')
HREF_RE = re.compile(r'href="([^"]+)"')
STATION_SUFFIX = (".html", ".json", ".md")


def read_text(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# 图「描述」的是这些源码；只改文档/门禁的提交不算让图过期。
#
# 只盯 `matlabc.py` 是**实测取舍**：把 `frontends/` `renderers/` `binfmt/` `facts.py`
# 都放进来时，一次「新增 facts.py」就让 11 张图全红 —— 而图里那条「事实层」
# 本来就已经画成计划节点，新增文件并不改变图的拓扑。
# 判据必须能长期绿，否则它会被删掉；而 `matlabc.py` 用**结构指纹**（不是内容 sha）
# 比较，改一行 docstring 不算过期。
WATCH_PATHS = ("matlabc.py",)


def _git(root, *args):
    try:
        out = subprocess.run(
            ["git", "-C", root] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


def changed_since(root, old_rev, head, paths):
    """old_rev..head 之间改过的、且落在 paths 里的文件；取不到返回 None。"""
    out = _git(root, "diff", "--name-only", old_rev + ".." + head, "--", *paths)
    if out is None:
        return None
    return [x for x in out.splitlines() if x.strip()]


def structure_fingerprint(text):
    """`matlabc.py` 的**结构指纹**：排序后的「函数名:起始行」集合的 sha256。

    为什么不用内容 sha：改一行 docstring 会让内容 sha 变，但图描述的**结构**
    一点没变；用内容 sha 判「图过期」等于要求每次改文案都重画 11 张图。
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    sigs = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sigs.append("%s:%d" % (n.name, n.lineno))
    return hashlib.sha256("\n".join(sorted(sigs)).encode("utf-8")).hexdigest()


def structural_drift(root, old_rev, head):
    """两个提交之间 `matlabc.py` 的结构是否变了；取不到返回 None。"""
    old = _git(root, "show", old_rev + ":matlabc.py")
    new = _git(root, "show", head + ":matlabc.py")
    if old is None or new is None:
        return None
    a = structure_fingerprint(old)
    b = structure_fingerprint(new)
    if a is None or b is None:
        return None
    return a != b


def watch_problem(rev, head, changed, drift=None):
    """FF6 的纯函数部分（可单测）。None=绿，否则返回问题串。

    首版把「rev != HEAD」直接判红，实测**任何提交**都会让 11 张图全红 ——
    那种门会被删掉，等于没有。所以拆成四层：
      ① 格式必须是 40 位十六进制；
      ② rev == HEAD ⇒ 绿；
      ③ 只改了 `matlabc.py` ⇒ 比**结构指纹**，结构没变就绿（改文案不算过期）；
      ④ 改了其它图相关文件（frontends/ renderers/ binfmt/ facts.py）⇒ 红。
    """
    if not rev:
        return "没有 meta.repository.revision（无法判断是否过期）"
    if not re.match(r"^[0-9a-f]{40}$", str(rev).lower()):
        return "revision=%r 不是 40 位十六进制" % (str(rev)[:16],)
    if str(rev).lower() == head:
        return None
    if changed is None:
        return None          # 拿不到 diff ⇒ 未行使（调用方打印）
    others = [p for p in changed if p != "matlabc.py"]
    if others:
        return ("绑定的 revision=%s 与 HEAD=%s 之间改过 %d 个图相关文件（%s）—— "
                "图已过期，重跑 archify deliver"
                % (str(rev)[:12], head[:12], len(others), ", ".join(others[:3])))
    if "matlabc.py" in changed and drift is not False:
        return ("绑定的 revision=%s 与 HEAD=%s 之间 matlabc.py 的**结构**变了"
                "（结构指纹不等）—— 图已过期，重跑 archify deliver"
                % (str(rev)[:12], head[:12]))
    return None


def git_head(root):
    """当前 HEAD；取不到返回 None（= FF6 未行使，绝不静默当绿）。"""
    try:
        out = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    h = out.stdout.decode("utf-8", "replace").strip().lower()
    return h if re.match(r"^[0-9a-f]{40}$", h) else None


def index_refs(text):
    """站内链接（去掉锚点与绝对 URL），返回原样字符串集合。"""
    out = set()
    for h in HREF_RE.findall(text):
        if h.startswith("#") or h.startswith("http://") or h.startswith("https://"):
            continue
        if not h.endswith(STATION_SUFFIX):
            continue
        out.add(h)
    return out


def figure_dirs(root):
    d = os.path.join(root, FIGURES.replace("/", os.sep))
    if not os.path.isdir(d):
        return None
    return sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)))


def figure_htmls(root):
    base = os.path.join(root, FIGURES.replace("/", os.sep))
    out = []
    for dirname in figure_dirs(root) or []:
        d = os.path.join(base, dirname)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".html"):
                # 与 index_refs 同口径：**相对 flow/**（`figures/...`），
                # 不是相对仓库根（`flow/figures/...`）。首版差了这一层，
                # 于是 FF2 把每一个产物都判成孤儿 —— 装置自己的错，先修装置。
                out.append("figures/" + dirname + "/" + fn)
    return out


def _collect_sources(obj, out):
    """递归收集任意层级的 `sources[].path`。

    五种图型的节点字段不同（architecture=`components`、workflow/dataflow=`nodes`、
    sequence=`participants`、lifecycle=`states`），所以不能按字段名取。
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "sources" and isinstance(v, list):
                for s in v:
                    if isinstance(s, dict) and isinstance(s.get("path"), str) and s["path"]:
                        out.append(s["path"])
            else:
                _collect_sources(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _collect_sources(x, out)


def candidate_outputs(root):
    """({html_rel: candidate_rel}, {html_rel: revision}, {html_rel: [src]}, 问题)。"""
    base = os.path.join(root, FIGURES.replace("/", os.sep))
    outs, revs, srcs, bad = {}, {}, {}, []
    for dirname in figure_dirs(root) or []:
        d = os.path.join(base, dirname)
        cand_names = [f for f in sorted(os.listdir(d))
                      if f == "candidate.json"
                      or (f.startswith("candidate.") and f.endswith(".json"))]
        if not cand_names:
            bad.append("%s 没有 candidate.json" % dirname)
            continue
        for cn in cand_names:
            rel = os.path.join(FIGURES, dirname, cn).replace(os.sep, "/")
            try:
                rec = json.loads(read_text(os.path.join(d, cn)))
            except ValueError as exc:
                bad.append("%s 不是合法 JSON（%s）" % (rel, exc))
                continue
            meta = rec.get("meta") or {}
            out = meta.get("output")
            if not isinstance(out, str) or not out.endswith(".html"):
                bad.append("%s 的 meta.output 不是 .html：%r" % (rel, out))
                continue
            if meta.get("locale") != "zh-CN":
                bad.append("%s 的 meta.locale 不是 zh-CN：%r" % (rel, meta.get("locale")))
            html_rel = "figures/" + dirname + "/" + os.path.basename(out)
            if html_rel in outs:
                bad.append("%s 与 %s 推出同一个产物 %s" % (outs[html_rel], rel, html_rel))
            outs[html_rel] = rel
            revs[html_rel] = (meta.get("repository") or {}).get("revision")
            paths = []
            _collect_sources(rec, paths)
            srcs[html_rel] = paths
    return outs, revs, srcs, bad


def audit(root, on_problem, head=None):
    ipath = os.path.join(root, INDEX.replace("/", os.sep))
    if not os.path.isfile(ipath):
        on_problem("FF0 缺索引 %s（缺输入 → 红）" % INDEX)
        return 0, 0, 0
    if figure_dirs(root) is None:
        on_problem("FF0 缺目录 %s（缺输入 → 红）" % FIGURES)
        return 0, 0, 0

    text = read_text(ipath)
    refs = index_refs(text)
    flow_root = os.path.join(root, "flow")

    # FF1：索引里的站内链接必须落地
    for rel in sorted(refs):
        full = os.path.join(flow_root, rel.replace("/", os.sep))
        if not os.path.isfile(full):
            on_problem("FF1 %s 引用了不存在的 %s" % (INDEX, rel))

    # FF2：figures 下每个产物必须被索引
    htmls = figure_htmls(root)
    for rel in htmls:
        if rel not in refs:
            on_problem("FF2 %s 没有被 %s 引用（孤儿产物）" % (rel, INDEX))

    # FF3：候选 ⇄ 产物 两向
    outs, revs, srcs, bad = candidate_outputs(root)
    for msg in bad:
        on_problem("FF3 " + msg)
    for rel in sorted(outs):
        # rel 相对 flow/，与 index_refs 同口径 ⇒ 要拼 flow_root，不是 root。
        if not os.path.isfile(os.path.join(flow_root, rel.replace("/", os.sep))):
            on_problem("FF3 %s 声明产出 %s，但该文件不存在" % (outs[rel], rel))
    for rel in htmls:
        if rel not in outs:
            on_problem("FF3 %s 推不出对应的候选（没有 candidate 声明它）" % rel)

    # FF6：图不得「因为没变的东西而过期」，也不得「因为变了的东西而装作没过期」。
    # 判据分三层（首版写成「rev != HEAD 即红」，实测任何提交都会让 11 张图全红 ——
    # 那种门会被删掉，等于没有）：
    #   ① revision 必须是 40 位十六进制；
    #   ② rev == HEAD ⇒ 绿；
    #   ③ rev != HEAD ⇒ 只有**图所描述的源码**（WATCH_PATHS）在 rev..HEAD 之间
    #      被改过才红；只改了文档/门禁的提交不算过期。
    # 判据口径（R119 调整）：**图引用的源码还在**才是「过期」的硬判据。
    # 首版用「结构指纹」，在重构期误伤率 100% —— S1 只是把 main 拆成 cli_entry，
    # 图的拓扑一点没变，却会让 11 张图全红。结构漂移降为提示，不判红。
    if head is None:
        print("  [跳过] FF6 未行使 —— 取不到 git HEAD")
    else:
        for rel in sorted(revs):
            rev = revs[rel]
            prob = watch_problem(rev, head, None)
            if prob:
                on_problem("FF6 %s %s" % (rel, prob))
                continue
            missing = [p for p in srcs.get(rel, ())
                       if not os.path.isfile(os.path.join(root, p.replace("/", os.sep)))]
            for p in missing[:3]:
                on_problem("FF6 %s 引用的源码 %s 不存在 —— 图已过期，重跑 archify deliver"
                           % (rel, p))
            if rev and str(rev).lower() != head:
                if structural_drift(root, str(rev).lower(), head):
                    print("  [提示] FF6 %s 绑定的 revision 落后、matlabc.py 结构已变 —— "
                          "建议重画（不判红）" % rel)

    # FF7：交付回执必须与产物同源 —— artifact.sha256 / bytes 等于磁盘现算。
    for rel in htmls:
        dpath = os.path.join(flow_root, rel[:-len(".html")] + ".delivery.json")
        if not os.path.isfile(dpath):
            on_problem("FF7 %s 缺交付回执 %s（无法证明它由候选渲染而来）"
                       % (rel, os.path.basename(dpath)))
            continue
        try:
            rec = json.loads(read_text(dpath))
        except ValueError as exc:
            on_problem("FF7 %s 不是合法 JSON（%s）" % (dpath, exc))
            continue
        art = rec.get("artifact") or {}
        want_s, want_b = art.get("sha256"), art.get("bytes")
        full = os.path.join(flow_root, rel)
        got_b = os.path.getsize(full)
        got_s = sha256_file(full)
        if want_b != got_b:
            on_problem("FF7 %s 回执记 %r 字节，磁盘 %d（产物被替换过）"
                       % (rel, want_b, got_b))
        if want_s != got_s:
            on_problem("FF7 %s 回执 sha256 与磁盘不一致（产物被替换过）" % rel)

    # FF4：编号唯一 + 数量对齐
    ids = ID_RE.findall(text)
    seen, dup = set(), []
    for i in ids:
        if i in seen:
            dup.append(i)
        seen.add(i)
    for i in sorted(set(dup)):
        on_problem("FF4 %s 里编号 %s 重复出现" % (INDEX, i))
    new_ids = [i for i in ids if int(i[1:]) >= 14]
    n_dirs = len(figure_dirs(root) or [])
    if len(new_ids) != n_dirs:
        on_problem("FF4 编号 ≥14 的卡片 %d 个，但 figures/ 下有 %d 个目录"
                   % (len(new_ids), n_dirs))

    # FF5：索引页自足
    if "<script" in text.lower():
        on_problem("FF5 %s 含 <script（应零 JS）" % INDEX)
    if re.search(r'href="https?://', text):
        on_problem("FF5 %s 含外部链接（断网打不开）" % INDEX)
    if "prefers-color-scheme" not in text:
        on_problem("FF5 %s 没有 prefers-color-scheme（无暗色）" % INDEX)
    if "viewport" not in text:
        on_problem("FF5 %s 没有 viewport（移动端会被裁）" % INDEX)

    return len(htmls), len(refs), len(outs)


# ---------------------------------------------------------------- 自证
GOOD_INDEX = u"""<!doctype html><html><head>
<meta name="viewport" content="width=device-width">
<style>@media (prefers-color-scheme: dark){body{background:#000}}</style>
</head><body>
<a href="figures/d1/f14-a.html">a</a>
<span class="id">F14</span>
</body></html>
"""


def _mk(root, rel, text):
    p = os.path.join(root, rel.replace("/", os.sep))
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


HEAD = "a" * 40


def _cand(name, locale="zh-CN", rev=HEAD):
    meta = {"output": name, "locale": locale}
    if rev is not None:
        meta["repository"] = {"url": "x", "revision": rev}
    return json.dumps({"meta": meta})


def _delivery(root, rel, sha=None, size=None):
    full = os.path.join(root, "flow", rel.replace("/", os.sep))
    art = {"sha256": sha or sha256_file(full),
           "bytes": size if size is not None else os.path.getsize(full)}
    _mk(root, "flow/" + rel[:-len(".html")] + ".delivery.json",
        json.dumps({"schemaVersion": 1, "artifact": art}))


def _selftest():
    bad, good = 0, 0
    root = tempfile.mkdtemp(prefix="flow-figures-")
    try:
        _mk(root, "flow/index.html", GOOD_INDEX)
        _mk(root, "flow/figures/d1/f14-a.html", "<html></html>\n")
        _mk(root, "flow/figures/d1/candidate.json", _cand("f14-a.html"))
        _delivery(root, "figures/d1/f14-a.html")
        probs = []
        audit(root, probs.append, head=HEAD)
        if not probs:
            good += 1
        else:
            bad += 1
            print("  [selftest] 干净样本被误伤：%s" % probs)

        # FF1 悬空
        _mk(root, "flow/index.html", GOOD_INDEX.replace("f14-a.html", "nope.html"))
        probs = []
        audit(root, probs.append, head=HEAD)
        if any(p.startswith("FF1") for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] FF1 悬空链接未红")

        # FF2 孤儿
        _mk(root, "flow/index.html", GOOD_INDEX.replace('<a href="figures/d1/f14-a.html">a</a>', ""))
        probs = []
        audit(root, probs.append, head=HEAD)
        if any(p.startswith("FF2") for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] FF2 孤儿产物未红")

        # FF3 候选指向不存在
        _mk(root, "flow/index.html", GOOD_INDEX)
        _mk(root, "flow/figures/d1/candidate.json", _cand("missing.html"))
        probs = []
        audit(root, probs.append, head=HEAD)
        if any(p.startswith("FF3") for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] FF3 候选指向不存在未红")

        # FF3 产物无候选
        _mk(root, "flow/figures/d1/candidate.json", _cand("f14-a.html"))
        _mk(root, "flow/figures/d1/extra.html", "<html></html>\n")
        probs = []
        audit(root, probs.append, head=HEAD)
        if any(p.startswith("FF3") and "extra" in p for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] FF3 产物无候选未红")
        os.remove(os.path.join(root, "flow", "figures", "d1", "extra.html"))

        # FF4 编号重复
        dup = GOOD_INDEX.replace("</body>", '<span class="id">F14</span></body>')
        _mk(root, "flow/index.html", dup)
        probs = []
        audit(root, probs.append, head=HEAD)
        if any(p.startswith("FF4") and "重复" in p for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] FF4 编号重复未红")

        # FF4 编号数与目录数不等（先把索引恢复成单 F14，否则上一条用例的重复
        # 编号会让 len(new_ids)=2 与 n_dirs=2 恰好相等 —— 状态污染会把判据测成恒真）
        _mk(root, "flow/index.html", GOOD_INDEX)
        _mk(root, "flow/figures/d2/f15-b.html", "<html></html>\n")
        _mk(root, "flow/figures/d2/candidate.json", _cand("f15-b.html"))
        probs = []
        audit(root, probs.append, head=HEAD)
        if any(p.startswith("FF4") and "目录" in p for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] FF4 编号数与目录数不等未红")
        shutil.rmtree(os.path.join(root, "flow", "figures", "d2"))

        # FF6 图过期：纯函数四层（格式 / 相等 / 结构指纹 / 其它图相关文件）
        cases = [
            (None, HEAD, None, None, True),                    # 缺 revision
            ("zz" * 20, HEAD, None, None, True),               # 非 hex
            (HEAD, HEAD, None, None, False),                   # 相等
            ("b" * 40, HEAD, [], None, False),                 # 只改文档
            ("b" * 40, HEAD, ["matlabc.py"], False, False),    # 改了但结构没变
            ("b" * 40, HEAD, ["matlabc.py"], True, True),      # 结构变了
            ("b" * 40, HEAD, ["renderers/csite.py"], None, True),  # 其它图相关文件
        ]
        for rev, hd, ch, dr, want_bad in cases:
            got = watch_problem(rev, hd, ch, dr)
            if bool(got) == want_bad:
                good += 1
            else:
                bad += 1
                print("  [selftest] watch_problem(%r,%r,%r,%r) -> %r"
                      % (rev, hd, ch, dr, got))

        # FF7 回执与产物不一致（sha256 被改成别的值）
        _delivery(root, "figures/d1/f14-a.html", sha="0" * 64)
        probs = []
        audit(root, probs.append, head=HEAD)
        if any(p.startswith("FF7") for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] FF7 回执不一致未红")
        _delivery(root, "figures/d1/f14-a.html")

        # FF5 含脚本
        _mk(root, "flow/index.html", GOOD_INDEX.replace("</body>", "<script>x</script></body>"))
        probs = []
        audit(root, probs.append, head=HEAD)
        if any(p.startswith("FF5") and "script" in p for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] FF5 含脚本未红")

        # FF5 外链 / 缺 viewport（两件各算一条）
        _mk(root, "flow/index.html",
            GOOD_INDEX.replace("</body>", '<a href="https://x.test/a">x</a></body>'))
        probs = []
        audit(root, probs.append, head=HEAD)
        if any(p.startswith("FF5") and "外部链接" in p for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] FF5 外链未红")

        _mk(root, "flow/index.html", GOOD_INDEX.replace('<meta name="viewport" content="width=device-width">', ""))
        probs = []
        audit(root, probs.append, head=HEAD)
        if any(p.startswith("FF5") and "viewport" in p for p in probs):
            good += 1
        else:
            bad += 1
            print("  [selftest] FF5 缺 viewport 未红")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return bad, good


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", action="store_true")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    if args.help:
        print(__doc__)
        return 0
    if args.selftest:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    probs = []
    n_html, n_refs, n_cand = audit(root, probs.append, head=git_head(root))
    if n_html == 0:
        print("check_flow_figures: 缺输入（没有 figures 产物）")
        return 2
    for p in probs:
        print("  - " + p)
    if probs:
        print("check_flow_figures: %d 项不对齐" % len(probs))
        return 1
    print("check_flow_figures: OK（产物 %d 个 / 索引引用 %d 条 / 候选 %d 个，%s 全绿）"
          % (n_html, n_refs, n_cand, ROW_SIGNATURE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
