# -*- coding: utf-8 -*-
"""架构文档一致性门（AD1–AD4）。

判据族：
    AD1  索引形状：`FLOW_INDEX.json` 的 version/items/id/type/title 齐全且唯一。
    AD2  三向对账：索引条目 ⇄ `candidates/*.json` ⇄ `html/*.html` ⇄ `svg/*.svg`；
         候选的 `diagram_type` 必须等于登记的 type；SVG 必须是合法 XML；
         反向：磁盘上多出未登记的 candidate/html/svg 也算红。
    AD3  文档可发现：`docs/architecture/README.md` 必须引用每个 HTML；
         两份根 README 必须链接架构索引并嵌入总框架 SVG。
    AD4  候选自述：`meta.output` 必须指向自己的 HTML（防止复制模板忘改）。

为什么需要它：架构图是**生成物**，最容易出现的缺陷不是“画错”，而是
“改了 candidate 没重渲染 / 渲染了没登记 / 嵌了图但路径写错”——这三种
在 git diff 里都只是几行，靠人看不住。

退出码：
    0  = AD1–AD4 全绿
    1  = 有架构文档不一致
    2  = 缺输入（找不到 docs/architecture 或根 README）
"""
import argparse
import io
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

#: P5 的对手方：本门在 README 质量门表那一行里声明的判据族。
ROW_SIGNATURE = "AD1–AD4"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCH = os.path.join(ROOT, "docs", "architecture")
INDEX = os.path.join(ARCH, "FLOW_INDEX.json")
ARCH_README = os.path.join(ARCH, "README.md")
ROOT_READMES = (os.path.join(ROOT, "README.md"),
                os.path.join(ROOT, "README_CN.md"))
TYPES = ("architecture", "workflow", "lifecycle", "sequence", "dataflow")


def _load_json(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _read(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def check(index_path=None, arch_dir=None, arch_readme=None,
          root_readmes=None):
    """纯函数：返回问题列表；空 = 干净。参数可注入（自证用）。"""
    index_path = index_path or INDEX
    arch_dir = arch_dir or ARCH
    arch_readme = arch_readme or ARCH_README
    root_readmes = tuple(root_readmes or ROOT_READMES)
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

    if not os.path.isfile(arch_readme):
        probs.append("AD3 缺架构说明：%s" % arch_readme)
    else:
        txt = _read(arch_readme)
        for it in items:
            if it.get("html") and it["html"] not in txt:
                probs.append("AD3 架构 README 未引用 %s" % it["html"])

    for rp in root_readmes:
        if not os.path.isfile(rp):
            probs.append("AD3 缺根 README：%s" % rp)
            continue
        txt = _read(rp)
        if "docs/architecture/index.html" not in txt:
            probs.append("AD3 %s 未链接架构索引" % rp)
        if "docs/architecture/svg/00-overall.svg" not in txt:
            probs.append("AD3 %s 未嵌入总框架 SVG" % rp)
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
        _write(os.path.join(arch, "candidates", "00-overall.json"),
               json.dumps({"diagram_type": "architecture",
                           "meta": {"title": "x",
                                    "output": "html/00-overall.html"}}))
        _write(os.path.join(arch, "html", "00-overall.html"),
               "<html><body>ok</body></html>\n")
        _write(os.path.join(arch, "svg", "00-overall.svg"),
               '<?xml version="1.0" encoding="UTF-8"?>\n'
               '<svg xmlns="http://www.w3.org/2000/svg"'
               ' viewBox="0 0 10 10"></svg>\n')
        _write(os.path.join(arch, "README.md"),
               "[html/00-overall.html](html/00-overall.html)\n")
        _write(os.path.join(arch, "FLOW_INDEX.json"), json.dumps({
            "version": 1, "generated": "2026-10-21",
            "items": [{"id": "00-overall", "type": "architecture",
                       "candidate": "candidates/00-overall.json",
                       "html": "html/00-overall.html",
                       "title": "x"}]}))
        r_en = os.path.join(tmp, "README.md")
        r_cn = os.path.join(tmp, "README_CN.md")
        for rp in (r_en, r_cn):
            _write(rp, "![x](docs/architecture/svg/00-overall.svg)\n"
                       "[i](docs/architecture/index.html)\n")

        args = (os.path.join(arch, "FLOW_INDEX.json"), arch,
                os.path.join(arch, "README.md"), (r_en, r_cn))
        chk(not check(*args), "好样本被误伤")
        # 坏样本 1：candidate 不存在
        os.remove(os.path.join(arch, "candidates", "00-overall.json"))
        chk(bool(check(*args)), "缺 candidate 未判红")
        _write(os.path.join(arch, "candidates", "00-overall.json"),
               json.dumps({"diagram_type": "architecture",
                           "meta": {"title": "x",
                                    "output": "html/00-overall.html"}}))
        # 坏样本 2：diagram_type 不一致
        _write(os.path.join(arch, "candidates", "00-overall.json"),
               json.dumps({"diagram_type": "workflow",
                           "meta": {"title": "x",
                                    "output": "html/00-overall.html"}}))
        chk(bool(check(*args)), "type 不一致未判红")
        _write(os.path.join(arch, "candidates", "00-overall.json"),
               json.dumps({"diagram_type": "architecture",
                           "meta": {"title": "x",
                                    "output": "html/00-overall.html"}}))
        # 坏样本 3：SVG 不是 XML
        _write(os.path.join(arch, "svg", "00-overall.svg"), "not xml\n")
        chk(bool(check(*args)), "坏 SVG 未判红")
        _write(os.path.join(arch, "svg", "00-overall.svg"),
               '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"'
               ' viewBox="0 0 10 10"></svg>\n')
        # 坏样本 4：根 README 没嵌图
        _write(r_en, "[i](docs/architecture/index.html)\n")
        chk(bool(check(*args)), "根 README 缺图未判红")
        _write(r_en, "![x](docs/architecture/svg/00-overall.svg)\n"
                     "[i](docs/architecture/index.html)\n")
        # 坏样本 5：多出未登记文件
        _write(os.path.join(arch, "svg", "99-extra.svg"),
               '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"'
               ' viewBox="0 0 10 10"></svg>\n')
        chk(bool(check(*args)), "未登记 SVG 未判红")
        os.remove(os.path.join(arch, "svg", "99-extra.svg"))
        chk(not check(*args), "恢复后仍误伤")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad[0], good[0]))
    return 0 if (bad[0] == 0 and good[0] >= 7) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="架构文档一致性门（AD1–AD4）")
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
    print("check_architecture_docs: OK（AD1–AD4 全绿；"
          "索引 %d 条对账 candidate/html/svg；根 README 已嵌图）"
          % len(_load_json(INDEX).get("items") or []))
    return 0


if __name__ == "__main__":
    sys.exit(main())
