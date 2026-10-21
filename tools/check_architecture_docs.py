# -*- coding: utf-8 -*-
"""架构文档一致性门（AD1–AD8）。

判据族：
    AD1  索引形状：`FLOW_INDEX.json` 的 version/items/id/type/title 齐全且唯一。
    AD2  三向对账：索引条目 ⇄ `candidates/*.json` ⇄ `html/*.html` ⇄ `svg/*.svg`；
         候选的 `diagram_type` 必须等于登记的 type；SVG 必须是合法 XML；
         反向：磁盘上多出未登记的 candidate/html/svg 也算红。
    AD3  文档可发现：`docs/architecture/README.md` 必须引用每个 HTML；
         两份根 README 必须链接架构索引并嵌入总框架 SVG；
         根 README 里的**本地图片路径**必须真实存在（不是 404）。
    AD4  候选自述：`meta.output` 必须指向自己的 HTML（防止复制模板忘改）。
    AD5  陈旧：`svg/MANIFEST.json` 记录 candidate/html/svg 的 sha256；
         三者任一变了而 SVG/清单没重导 ⇒ 红。
    AD6  版式不变量（离线，不依赖 archify）：viewBox 为正、节点 id 唯一、
         连线/消息不引用未知节点、sequence 消息 y ≥ 160 且间距 ≥ 28、
         段/激活区间不越界、标签不过长。
    AD7  责任人：`.github/CODEOWNERS` 必须覆盖架构文档列出的关键模块，
         且每个 owner 都以 `@` 开头。
    AD8  中英一致：每张图必须有 `en/candidates/<id>.json`；两者的
         节点 id、连线端点、节点/连线/消息计数必须一致；英文版**不得残留中文**。

为什么需要它：架构图是**生成物**，最容易出现的缺陷不是“画错”，而是
“改了 candidate 没重渲染 / 渲染了没登记 / 嵌了图但路径写错”——这三种
在 git diff 里都只是几行，靠人看不住。

退出码：
    0  = AD1–AD8 全绿
    1  = 有架构文档不一致
    2  = 缺输入（找不到 docs/architecture 或根 README）
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

#: P5 的对手方：本门在 README 质量门表那一行里声明的判据族。
ROW_SIGNATURE = "AD1–AD8"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCH = os.path.join(ROOT, "docs", "architecture")
INDEX = os.path.join(ARCH, "FLOW_INDEX.json")
MANIFEST = os.path.join(ARCH, "svg", "MANIFEST.json")
ARCH_README = os.path.join(ARCH, "README.md")
CODEOWNERS = os.path.join(ROOT, ".github", "CODEOWNERS")
MODULE_DOC = os.path.join(ROOT, "docs", "ARCHITECTURE_MAP.md")
CHECKLIST = os.path.join(ARCH, "REVIEW_CHECKLIST.md")
ROOT_READMES = (os.path.join(ROOT, "README.md"),
                os.path.join(ROOT, "README_CN.md"))
TYPES = ("architecture", "workflow", "lifecycle", "sequence", "dataflow")
_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")


def _load_json(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _read(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _sha256(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as fh:
        while True:
            b = fh.read(65536)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _missing_images(txt, base_dir):
    """README 里的本地图片必须存在；http/data/anchor 一律跳过。"""
    probs = []
    for raw in _IMG_RE.findall(txt or ""):
        if raw.startswith(("http://", "https://", "data:", "mailto:", "#")):
            continue
        path = raw.strip("<>").split(" ")[0]
        if not path:
            continue
        full = (os.path.join(ROOT, path.lstrip("/"))
                if path.startswith("/") else os.path.join(base_dir, path))
        if not os.path.isfile(full):
            probs.append("AD3 图片不存在：%s" % raw)
    return probs


def _layout_problems(iid, typ, cj):
    """AD6：离线版式不变量（不依赖 archify，CI 里也能跑）。"""
    probs = []
    meta = cj.get("meta") or {}
    vb = meta.get("viewBox")
    vb_ok = (isinstance(vb, list) and len(vb) == 2
             and all(isinstance(x, (int, float)) and x > 0 for x in vb))
    if typ in ("sequence", "dataflow") and not vb_ok:
        probs.append("AD6 %s 缺正 viewBox" % iid)
        vb = None
    elif vb is not None and not vb_ok:
        probs.append("AD6 %s 的 viewBox 非法" % iid)
        vb = None
    if len(meta.get("title") or "") > 140:
        probs.append("AD6 %s 标题过长（> 140）" % iid)

    nodes = (cj.get("components") or cj.get("nodes")
             or cj.get("participants") or cj.get("states") or [])
    if not nodes:
        probs.append("AD6 %s 没有节点" % iid)
    ids = set()
    for n in nodes:
        nid = n.get("id")
        if not nid:
            probs.append("AD6 %s 节点缺 id" % iid)
            continue
        if nid in ids:
            probs.append("AD6 %s 节点 id 重复：%s" % (iid, nid))
        ids.add(nid)
        if len(n.get("label") or "") > 48:
            probs.append("AD6 %s 节点 %s 标签过长（> 48）" % (iid, nid))

    if typ == "dataflow":
        stages = cj.get("stages") or []
        if not stages:
            probs.append("AD6 %s 缺 stages" % iid)
        for n in nodes:
            st = n.get("stage")
            if not isinstance(st, int) or not (0 <= st < len(stages)):
                probs.append("AD6 %s 节点 %s 的 stage 越界：%r"
                             % (iid, n.get("id"), st))
            if not isinstance(n.get("row"), int) or n["row"] < 0:
                probs.append("AD6 %s 节点 %s 的 row 非法：%r"
                             % (iid, n.get("id"), n.get("row")))

    if typ == "sequence":
        parts = set(x.get("id") for x in nodes)
        ys = []
        for m in cj.get("messages") or []:
            if m.get("from") not in parts or m.get("to") not in parts:
                probs.append("AD6 %s 消息 %s 引用未知参与者"
                             % (iid, m.get("id")))
            y = m.get("y")
            if not isinstance(y, (int, float)):
                probs.append("AD6 %s 消息 %s 缺 y" % (iid, m.get("id")))
            else:
                ys.append(y)
            if len(m.get("label") or "") > 36:
                probs.append("AD6 %s 消息 %s 标签过长" % (iid, m.get("id")))
        if ys:
            if min(ys) < 160:
                probs.append("AD6 %s 消息 y < 160" % iid)
            for a, b in zip(ys, ys[1:]):
                if b - a < 28:
                    probs.append("AD6 %s 消息间距 < 28（%s）" % (iid, b - a))
                    break
        limit = (vb[1] - 20) if vb else 10 ** 9
        for seg in cj.get("segments") or []:
            if seg.get("from", 0) < 72 or seg.get("to", 0) > limit:
                probs.append("AD6 %s 段 %s 越界" % (iid, seg.get("label")))
        for act in cj.get("activations") or []:
            if act.get("from", 0) > act.get("to", 0):
                probs.append("AD6 %s 激活区间倒置" % iid)
    else:
        edges = (cj.get("connections") or cj.get("edges")
                 or cj.get("transitions") or cj.get("flows") or [])
        for e in edges:
            if e.get("from") not in ids or e.get("to") not in ids:
                probs.append("AD6 %s 连线 %s 引用未知节点"
                             % (iid, e.get("id")))
            if len(e.get("label") or "") > 32:
                probs.append("AD6 %s 连线 %s 标签过长" % (iid, e.get("id")))
    return probs


def _codeowners_problems(path):
    """AD7：CODEOWNERS 覆盖关键模块，owner 必须是 @ 开头。"""
    if not os.path.isfile(path):
        return ["AD7 缺 CODEOWNERS：%s" % path]
    probs = []
    rules = []
    for line in _read(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            probs.append("AD7 CODEOWNERS 行缺 owner：%s" % line)
            continue
        rules.append((parts[0], parts[1:]))
    if not rules:
        return probs + ["AD7 CODEOWNERS 没有规则"]
    key_paths = ("matlabc.py", "matlabc_boot.py", "matlabc_lsp.py",
                 "matlabc_mcp.py", "matlabc_flow.py", "agent_loop.py",
                 "frontends", "renderers", "vscode", "tools",
                 "translate", "c_runtime", "binfmt")
    for p in key_paths:
        hit = False
        for pat, owners in rules:
            base = pat.rstrip("/")
            if base.startswith("/"):
                base = base[1:]
            if base in ("*", "**"):
                hit = True
            elif (p == base or p.startswith(base + "/")
                  or base.startswith(p + "/")):
                hit = True
            if hit and not owners:
                hit = False
            if hit:
                break
        if not hit:
            probs.append("AD7 %s 没有 CODEOWNERS 负责人" % p)
    for pat, owners in rules:
        for o in owners:
            if not o.startswith("@"):
                probs.append("AD7 %s 的 owner 不是 @ 开头：%s" % (pat, o))
    return probs


def _structure(cj):
    nodes = (cj.get("components") or cj.get("nodes")
             or cj.get("participants") or cj.get("states") or [])
    edges = (cj.get("connections") or cj.get("edges")
             or cj.get("transitions") or cj.get("flows") or [])
    msgs = cj.get("messages") or []
    pairs = set()
    for e in edges:
        pairs.add((e.get("from"), e.get("to")))
    for m in msgs:
        pairs.add((m.get("from"), m.get("to")))
    return {
        "type": cj.get("diagram_type"),
        "ids": set(n.get("id") for n in nodes if n.get("id")),
        "pairs": pairs,
        "n_nodes": len(nodes),
        "n_edges": len(edges),
        "n_msgs": len(msgs),
    }


def _strings(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            _strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _strings(v, out)
    elif isinstance(obj, str):
        out.append(obj)


def _label_problems(iid, zh, en):
    """AD8：英文版与中文版结构一致，且不残留中文。"""
    probs = []
    a, b = _structure(zh), _structure(en)
    if a["type"] != b["type"]:
        probs.append("AD8 %s 的 diagram_type 不一致：%r != %r"
                     % (iid, a["type"], b["type"]))
    if a["ids"] != b["ids"]:
        probs.append("AD8 %s 节点 id 不一致：zh-en=%r en-zh=%r"
                     % (iid, sorted(a["ids"] - b["ids"]),
                        sorted(b["ids"] - a["ids"])))
    if a["pairs"] != b["pairs"]:
        probs.append("AD8 %s 连线端点不一致：zh-en=%r en-zh=%r"
                     % (iid, sorted(a["pairs"] - b["pairs"]),
                        sorted(b["pairs"] - a["pairs"])))
    for key, label in (("n_nodes", "节点"), ("n_edges", "连线"),
                       ("n_msgs", "消息")):
        if a[key] != b[key]:
            probs.append("AD8 %s 的%s数不一致：%d != %d"
                         % (iid, label, a[key], b[key]))
    strings = []
    _strings(en, strings)
    for s in strings:
        if re.search(r"[\u4e00-\u9fff]", s):
            probs.append("AD8 %s 英文版仍含中文：%s" % (iid, s[:40]))
            break
    for n in (en.get("components") or en.get("nodes")
              or en.get("participants") or en.get("states") or []):
        if not (n.get("label") or "").strip():
            probs.append("AD8 %s 节点 %s 英文 label 为空"
                         % (iid, n.get("id")))
    return probs


def check(index_path=None, arch_dir=None, arch_readme=None,
          root_readmes=None, manifest_path=None, codeowners_path=None,
          module_doc_path=None, checklist_path=None):
    """纯函数：返回问题列表；空 = 干净。参数可注入（自证用）。"""
    index_path = index_path or INDEX
    arch_dir = arch_dir or ARCH
    arch_readme = arch_readme or ARCH_README
    root_readmes = tuple(root_readmes or ROOT_READMES)
    manifest_path = manifest_path or os.path.join(
        arch_dir, "svg", "MANIFEST.json")
    codeowners_path = codeowners_path or CODEOWNERS
    module_doc_path = module_doc_path or MODULE_DOC
    checklist_path = checklist_path or CHECKLIST
    if not os.path.isfile(index_path):
        return ["AD1 缺索引：%s" % index_path]
    try:
        data = _load_json(index_path)
    except ValueError as e:
        return ["AD1 索引不是合法 JSON：%s" % e]
    if not isinstance(data, dict):
        return ["AD1 索引不是对象"]
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return ["AD1 索引缺非空 items 数组"]
    probs = []
    if not isinstance(data.get("version"), int) or data["version"] < 1:
        probs.append("AD1 version 非法")
    if not data.get("generated"):
        probs.append("AD1 缺 generated")

    seen = set()
    for it in items:
        if not isinstance(it, dict):
            probs.append("AD1 条目不是对象")
            continue
        iid = it.get("id")
        if not iid:
            probs.append("AD1 条目缺 id")
            continue
        if iid in seen:
            probs.append("AD1 id 重复：%s" % iid)
        seen.add(iid)
        typ = it.get("type")
        if typ not in TYPES:
            probs.append("AD1 %s 的 type 非法：%r" % (iid, typ))
        for k in ("candidate", "html", "title"):
            if not it.get(k):
                probs.append("AD1 %s 缺 %s" % (iid, k))

        cand = os.path.join(arch_dir, it.get("candidate") or "")
        html = os.path.join(arch_dir, it.get("html") or "")
        svg = os.path.join(arch_dir, "svg", iid + ".svg")
        if not os.path.isfile(cand):
            probs.append("AD2 %s 的 candidate 不存在：%s" % (iid, cand))
        else:
            try:
                cj = _load_json(cand)
            except ValueError as e:
                probs.append("AD2 %s 的 candidate 非法 JSON：%s" % (iid, e))
            else:
                if cj.get("diagram_type") != typ:
                    probs.append("AD2 %s 的 diagram_type=%r != %r"
                                 % (iid, cj.get("diagram_type"), typ))
                out = (cj.get("meta") or {}).get("output") or ""
                if iid not in out:
                    probs.append("AD4 %s 的 meta.output 未指向自身：%r"
                                 % (iid, out))
        if not os.path.isfile(html) or os.path.getsize(html) == 0:
            probs.append("AD2 %s 的 HTML 不存在/为空" % iid)
        if not os.path.isfile(svg):
            probs.append("AD2 %s 的 SVG 不存在：%s" % (iid, svg))
        else:
            s = _read(svg)
            if "<svg" not in s:
                probs.append("AD2 %s 的 SVG 缺 <svg>" % iid)
            try:
                ET.fromstring(s.encode("utf-8"))
            except ET.ParseError as e:
                probs.append("AD2 %s 的 SVG 不是合法 XML：%s" % (iid, e))

    for sub, ext in (("candidates", ".json"), ("html", ".html"),
                     ("svg", ".svg")):
        d = os.path.join(arch_dir, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(ext):
                continue
            if os.path.splitext(fn)[0] not in seen:
                probs.append("AD2 %s/%s 未登记进 FLOW_INDEX" % (sub, fn))

    # AD5：candidate / HTML / SVG 的 sha256 必须与 MANIFEST 一致。
    if not os.path.isfile(manifest_path):
        probs.append("AD5 缺哈希清单：%s" % manifest_path)
    else:
        try:
            man = _load_json(manifest_path)
        except ValueError as e:
            probs.append("AD5 清单不是合法 JSON：%s" % e)
            man = {}
        mrec = man.get("items") or {}
        for it in items:
            iid = it.get("id")
            if not iid:
                continue
            rec = mrec.get(iid)
            if not rec:
                probs.append("AD5 %s 未登记哈希" % iid)
                continue
            for label, path, key in (
                    ("candidate",
                     os.path.join(arch_dir, it.get("candidate") or ""),
                     "candidate_sha256"),
                    ("html", os.path.join(arch_dir, it.get("html") or ""),
                     "html_sha256"),
                    ("svg", os.path.join(arch_dir, "svg", iid + ".svg"),
                     "svg_sha256")):
                if os.path.isfile(path) and _sha256(path) != rec.get(key):
                    probs.append("AD5 %s 的 %s 已变，SVG 清单陈旧"
                                 % (iid, label))
        for iid in mrec:
            if iid not in seen:
                probs.append("AD5 清单多出未登记条目：%s" % iid)

    # AD6：离线版式不变量
    for it in items:
        iid = it.get("id")
        typ = it.get("type")
        cand = os.path.join(arch_dir, it.get("candidate") or "")
        if not iid or typ not in TYPES or not os.path.isfile(cand):
            continue
        try:
            cj = _load_json(cand)
        except ValueError:
            continue
        probs.extend(_layout_problems(iid, typ, cj))
        en_path = os.path.join(arch_dir, "en", "candidates", iid + ".json")
        if not os.path.isfile(en_path):
            probs.append("AD8 %s 缺英文 candidate：%s" % (iid, en_path))
        else:
            try:
                ej = _load_json(en_path)
            except ValueError as e:
                probs.append("AD8 %s 的英文 candidate 非法 JSON：%s"
                             % (iid, e))
            else:
                probs.extend(_label_problems(iid, cj, ej))
    # AD7：模块责任人
    probs.extend(_codeowners_problems(codeowners_path))

    if not os.path.isfile(arch_readme):
        probs.append("AD3 缺架构说明：%s" % arch_readme)
    else:
        txt = _read(arch_readme)
        for it in items:
            if it.get("html") and it["html"] not in txt:
                probs.append("AD3 架构 README 未引用 %s" % it["html"])
        probs.extend(_missing_images(txt, os.path.dirname(arch_readme)))

    for rp in root_readmes:
        if not os.path.isfile(rp):
            probs.append("AD3 缺根 README：%s" % rp)
            continue
        txt = _read(rp)
        if "docs/architecture/index.html" not in txt:
            probs.append("AD3 %s 未链接架构索引" % rp)
        base = os.path.basename(rp).lower()
        need = ("docs/architecture/en/svg/00-overall.svg"
                if base == "readme.md"
                else "docs/architecture/svg/00-overall.svg")
        if need not in txt:
            probs.append("AD3 %s 未嵌入总框架 SVG（%s）" % (rp, need))
        probs.extend(_missing_images(txt, os.path.dirname(rp)))

    if not os.path.isfile(module_doc_path):
        probs.append("AD3 缺模块图导览：%s" % module_doc_path)
    else:
        txt = _read(module_doc_path)
        for need in ("architecture/svg/00-overall.svg",
                     "architecture/svg/13-sequence.svg"):
            if need not in txt:
                probs.append("AD3 %s 未引用 %s" % (module_doc_path, need))
        probs.extend(_missing_images(txt, os.path.dirname(module_doc_path)))

    if not os.path.isfile(checklist_path):
        probs.append("AD3 缺评审清单：%s" % checklist_path)
    else:
        txt = _read(checklist_path)
        for need in ("FLOW_INDEX", "MANIFEST", "CODEOWNERS", "arch_compare"):
            if need not in txt:
                probs.append("AD3 评审清单未提到 %s" % need)

    # 索引页与模块边界图：搜索框/过滤片/14 张入口/模块图入口都必须在。
    for name, needles in (
            ("index.html", ('id="q"', "data-filter", "MODULE_GRAPH.md",
                            "html/13-sequence.html")),
            ("MODULE_GRAPH.md", ("graph LR", "core -->"))):
        path = os.path.join(arch_dir, name)
        if not os.path.isfile(path):
            probs.append("AD3 缺 %s" % path)
            continue
        txt = _read(path)
        for n in needles:
            if n not in txt:
                probs.append("AD3 %s 缺 %r" % (path, n))
    return probs


def _write(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _selftest():
    good = [0]
    bad = [0]

    def chk(cond, msg):
        if cond:
            good[0] += 1
        else:
            bad[0] += 1
            print("  [FAIL] %s" % msg)

    tmp = tempfile.mkdtemp(prefix="mlc_ad_")
    try:
        arch = os.path.join(tmp, "arch")
        cand = os.path.join(arch, "candidates", "00-overall.json")
        html = os.path.join(arch, "html", "00-overall.html")
        svg = os.path.join(arch, "svg", "00-overall.svg")
        man = os.path.join(arch, "svg", "MANIFEST.json")
        r_en = os.path.join(tmp, "README.md")
        r_cn = os.path.join(tmp, "README_CN.md")
        co = os.path.join(tmp, ".github", "CODEOWNERS")
        CAND = json.dumps({
            "diagram_type": "architecture",
            "meta": {"title": "x", "output": "html/00-overall.html",
                     "viewBox": [800, 600]},
            "components": [
                {"id": "a", "label": "A", "pos": [0, 0], "size": [10, 10]},
                {"id": "b", "label": "B", "pos": [100, 0], "size": [10, 10]}],
            "connections": [{"id": "ab", "from": "a", "to": "b"}]})
        SVG = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<svg xmlns="http://www.w3.org/2000/svg"'
               ' viewBox="0 0 10 10"></svg>\n')
        EN = json.dumps({
            "diagram_type": "architecture",
            "meta": {"title": "x", "viewBox": [800, 600], "locale": "en"},
            "components": [{"id": "a", "label": "A"},
                           {"id": "b", "label": "B"}],
            "connections": [{"id": "ab", "from": "a", "to": "b"}]})
        encand = os.path.join(arch, "en", "candidates", "00-overall.json")
        _write(encand, EN)
        _write(cand, CAND)
        _write(html, "<html><body>ok</body></html>\n")
        _write(svg, SVG)
        _write(os.path.join(arch, "README.md"),
               "[html/00-overall.html](html/00-overall.html)\n")
        _write(os.path.join(arch, "FLOW_INDEX.json"), json.dumps({
            "version": 1, "generated": "2026-10-21",
            "items": [{"id": "00-overall", "type": "architecture",
                       "candidate": "candidates/00-overall.json",
                       "html": "html/00-overall.html",
                       "title": "x"}]}))
        for ip in (os.path.join(tmp, "docs", "architecture", "en", "svg",
                                "00-overall.svg"),
                   os.path.join(tmp, "docs", "architecture", "svg",
                                "00-overall.svg"),
                   os.path.join(tmp, "docs", "architecture", "svg",
                                "13-sequence.svg")):
            _write(ip, '<?xml version="1.0"?>'
                       '<svg xmlns="http://www.w3.org/2000/svg"/>\n')
        module_doc = os.path.join(tmp, "docs", "ARCHITECTURE_MAP.md")
        _write(module_doc,
               "![x](architecture/svg/00-overall.svg)\n"
               "![y](architecture/svg/13-sequence.svg)\n")
        checklist = os.path.join(arch, "REVIEW_CHECKLIST.md")
        _write(checklist,
               "FLOW_INDEX MANIFEST CODEOWNERS arch_compare\n")
        index_html = os.path.join(arch, "index.html")
        _write(index_html,
               '<input id="q"><button data-filter="all"></button>\n'
               "[g](MODULE_GRAPH.md)\n[13](html/13-sequence.html)\n")
        module_graph = os.path.join(arch, "MODULE_GRAPH.md")
        _write(module_graph, "```mermaid\ngraph LR\n  core -->|1| x\n```\n")
        _write(r_en, "![x](docs/architecture/en/svg/00-overall.svg)\n"
                     "[i](docs/architecture/index.html)\n")
        _write(r_cn, "![x](docs/architecture/svg/00-overall.svg)\n"
                     "[i](docs/architecture/index.html)\n")
        _write(co, "\n".join("/%s @owner" % x for x in (
            "matlabc.py", "matlabc_boot.py", "matlabc_lsp.py",
            "matlabc_mcp.py", "matlabc_flow.py", "agent_loop.py",
            "frontends/", "renderers/", "vscode/", "tools/",
            "translate/", "c_runtime/", "binfmt/")) + "\n")

        def write_manifest():
            _write(man, json.dumps({"version": 1, "items": {"00-overall": {
                "candidate_sha256": _sha256(cand),
                "html_sha256": _sha256(html),
                "svg_sha256": _sha256(svg)}}}))

        write_manifest()
        args = (os.path.join(arch, "FLOW_INDEX.json"), arch,
                os.path.join(arch, "README.md"), (r_en, r_cn))
        kw = {"codeowners_path": co,
              "module_doc_path": module_doc,
              "checklist_path": checklist}
        chk(not check(*args, **kw), "好样本被误伤")
        # AD8：英文版残留中文 / 缺节点
        _write(encand, EN.replace('"label": "A"', '"label": "甲"'))
        chk(bool(check(*args, **kw)), "AD8 英文残留中文未判红")
        _write(encand, json.dumps({
            "diagram_type": "architecture",
            "meta": {"title": "x", "viewBox": [800, 600], "locale": "en"},
            "components": [{"id": "a", "label": "A"}],
            "connections": []}))
        chk(bool(check(*args, **kw)), "AD8 英文缺节点未判红")
        _write(encand, EN)
        # 坏样本 1：candidate 不存在
        os.remove(cand)
        chk(bool(check(*args, **kw)), "缺 candidate 未判红")
        _write(cand, CAND)
        write_manifest()
        # 坏样本 2：diagram_type 不一致
        _write(cand, json.dumps({"diagram_type": "workflow",
                                 "meta": {"title": "x",
                                          "output": "html/00-overall.html"}}))
        chk(bool(check(*args, **kw)), "type 不一致未判红")
        _write(cand, CAND)
        write_manifest()
        # 坏样本 3：SVG 不是 XML
        _write(svg, "not xml\n")
        chk(bool(check(*args, **kw)), "坏 SVG 未判红")
        _write(svg, SVG)
        write_manifest()
        # 坏样本 4：根 README 没嵌图
        _write(r_en, "[i](docs/architecture/index.html)\n")
        chk(bool(check(*args, **kw)), "根 README 缺图未判红")
        _write(r_en, "![x](docs/architecture/en/svg/00-overall.svg)\n"
                     "[i](docs/architecture/index.html)\n")
        # 坏样本 5：多出未登记文件
        _write(os.path.join(arch, "svg", "99-extra.svg"), SVG)
        chk(bool(check(*args, **kw)), "未登记 SVG 未判红")
        os.remove(os.path.join(arch, "svg", "99-extra.svg"))
        write_manifest()
        # 坏样本 6：candidate 变了但清单没重导（AD5）
        _write(cand, json.dumps({"diagram_type": "architecture",
                                 "meta": {"title": "changed",
                                          "output": "html/00-overall.html"}}))
        chk(bool(check(*args, **kw)), "candidate 变了清单未判红")
        _write(cand, CAND)
        write_manifest()
        # 坏样本 7：清单缺失
        os.remove(man)
        chk(bool(check(*args, **kw)), "缺清单未判红")
        write_manifest()
        # 坏样本 8：AD6 连线指向未知节点
        _write(cand, json.dumps({
            "diagram_type": "architecture",
            "meta": {"title": "x", "output": "html/00-overall.html",
                     "viewBox": [800, 600]},
            "components": [{"id": "a", "label": "A"}],
            "connections": [{"id": "ab", "from": "a", "to": "missing"}]}))
        chk(bool(check(*args, **kw)), "AD6 未知连线未判红")
        _write(cand, CAND)
        write_manifest()
        # AD6：sequence 间距与 y 下界
        bad_seq = {"meta": {"title": "s", "viewBox": [900, 700]},
                   "participants": [{"id": "a", "label": "A"},
                                    {"id": "b", "label": "B"}],
                   "messages": [
                       {"id": "m1", "from": "a", "to": "b", "y": 165,
                        "label": "one"},
                       {"id": "m2", "from": "b", "to": "a", "y": 190,
                        "label": "two"}]}
        good_seq = {"meta": {"title": "s", "viewBox": [900, 700]},
                    "participants": [{"id": "a", "label": "A"},
                                     {"id": "b", "label": "B"}],
                    "messages": [
                        {"id": "m1", "from": "a", "to": "b", "y": 165,
                         "label": "one"},
                        {"id": "m2", "from": "b", "to": "a", "y": 195,
                         "label": "two"}]}
        chk(bool(_layout_problems("s", "sequence", bad_seq)),
            "AD6 sequence 间距未判红")
        chk(not _layout_problems("s", "sequence", good_seq),
            "AD6 good sequence 被误伤")
        # 坏样本 9：AD7 缺 CODEOWNERS
        os.remove(co)
        chk(bool(check(*args, **kw)), "AD7 缺 CODEOWNERS 未判红")
        _write(co, "\n".join("/%s @owner" % x for x in (
            "matlabc.py", "matlabc_boot.py", "matlabc_lsp.py",
            "matlabc_mcp.py", "matlabc_flow.py", "agent_loop.py",
            "frontends/", "renderers/", "vscode/", "tools/",
            "translate/", "c_runtime/", "binfmt/")) + "\n")
        # 坏样本 10：AD3 本地图片 404
        _write(r_cn, "![x](docs/architecture/svg/missing.svg)\n"
                     "[i](docs/architecture/index.html)\n")
        chk(bool(check(*args, **kw)), "AD3 图片 404 未判红")
        _write(r_cn, "![x](docs/architecture/svg/00-overall.svg)\n"
                     "[i](docs/architecture/index.html)\n")
        # 坏样本 11：缺评审清单
        os.remove(checklist)
        chk(bool(check(*args, **kw)), "AD3 缺评审清单未判红")
        _write(checklist, "FLOW_INDEX MANIFEST CODEOWNERS arch_compare\n")
        # 坏样本 12：缺模块图导览
        os.remove(module_doc)
        chk(bool(check(*args, **kw)), "AD3 缺模块图导览未判红")
        _write(module_doc,
               "![x](architecture/svg/00-overall.svg)\n"
               "![y](architecture/svg/13-sequence.svg)\n")
        # 坏样本 13：索引页丢了搜索框
        _write(index_html, "[g](MODULE_GRAPH.md)\n[13](html/13-sequence.html)\n")
        chk(bool(check(*args, **kw)), "AD3 搜索框缺失未判红")
        _write(index_html,
               '<input id="q"><button data-filter="all"></button>\n'
               "[g](MODULE_GRAPH.md)\n[13](html/13-sequence.html)\n")
        chk(not check(*args, **kw), "恢复后仍误伤")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad[0], good[0]))
    return 0 if (bad[0] == 0 and good[0] >= 19) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="架构文档一致性门（AD1–AD8）")
    ap.add_argument("--selftest", action="store_true", help="两向自证")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not os.path.isdir(ARCH):
        print("check_architecture_docs: 缺输入（%s）" % ARCH)
        return 2
    for rp in ROOT_READMES:
        if not os.path.isfile(rp):
            print("check_architecture_docs: 缺输入（%s）" % rp)
            return 2
    probs = check()
    if probs:
        for p in probs:
            print("  - %s" % p)
        print("check_architecture_docs: %d 项不合规" % len(probs))
        return 1
    print("check_architecture_docs: OK（AD1–AD8 全绿；"
          "索引 %d 条对账 candidate/html/svg；根 README 已嵌图）"
          % len(_load_json(INDEX).get("items") or []))
    return 0


if __name__ == "__main__":
    sys.exit(main())
