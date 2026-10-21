# -*- coding: utf-8 -*-
"""给 01–13 的架构图节点补 `sources`（源码证据），并钉 revision。

口径：
    - `meta.repository` 指向本仓库，`revision` 取**写入时**的 HEAD（40 位）；
    - 每个节点最多 3 个 `sources`，只写工作区真实存在的文件；
    - `--check` 只验“每张图有 repository + 至少一个节点有 sources”，
      不要求 revision 等于当前 HEAD（提交后 HEAD 必然变化）。

写完还需要本机 archify 重渲染（见 REVIEW_CHECKLIST）：
    node archify.mjs render <type> candidates/<id>.json %TEMP%/<id>.html \
      --repo-root d:/work/malabc --quality showcase
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCH = os.path.join(ROOT, "docs", "architecture")
INDEX = os.path.join(ARCH, "FLOW_INDEX.json")
REPO_URL = "https://github.com/pony-029/malabc"

SRC = {
    "01-entry": {
        "bootn": ["matlabc_boot.py"], "parse": ["matlabc_help.py"],
        "dispatch": ["matlabc.py"], "analyze": ["matlabc.py"],
        "output": ["matlabc.py"], "other": ["matlabc.py"],
        "exitn": ["matlabc.py"],
    },
    "02-matlab-frontend": {
        "readf": ["matlabc.py"], "scrub": ["matlabc.py"],
        "logical": ["matlabc.py"],
        "parsef": ["matlabc.py", "frontends/matlab.py"],
        "modelf": ["matlabc.py"],
        "callsf": ["matlabc.py", "frontends/matlab.py"],
    },
    "03-multilang-ir": {
        "reg": ["matlabc.py"], "cf": ["frontends/ir.py", "matlabc.py"],
        "pf": ["frontends/ir.py"], "jf": ["frontends/ir.py"],
        "irn": ["frontends/ir.py"], "attr": ["frontends/ir.py"],
    },
    "04-analysis": {
        "cg": ["unified_graph.py"], "impact": ["matlabc.py"],
        "deps": ["matlabc.py"], "taint": ["matlabc.py"],
        "dims": ["matlabc.py"], "checks": ["matlabc.py"],
        "complex": ["matlabc.py"], "dups": ["matlabc.py"],
        "facts": ["facts.py"], "entity": ["entity_model.py"],
        "unified": ["unified_graph.py"],
    },
    "05-render": {
        "bm": ["renderers/__init__.py"], "md": ["renderers/report.py"],
        "html": ["renderers/report.py"], "browse": ["renderers/csite.py"],
        "json": ["matlabc.py"], "sarif": ["renderers/sarif.py"],
        "dox": ["renderers/report.py"], "patch": ["matlabc.py"],
    },
    "06-lsp": {
        "ext": ["vscode/extension.js"], "client": ["vscode/lspClient.js"],
        "server": ["matlabc_lsp.py"], "handlers": ["matlabc_lsp.py"],
        "analyzer": ["analyzer/api.py"], "cache": ["matlabc_lsp.py"],
        "ui": ["vscode/extension.js"],
    },
    "07-ai-mcp": {
        "mcp": ["matlabc_mcp.py"], "tools": ["matlabc_mcp.py"],
        "ask": ["matlabc_ask.py"], "ai": ["ai_cli.py"],
        "flow": ["matlabc_flow.py"], "memory": ["analyzer_memory.py"],
        "core": ["matlabc.py"],
    },
    "08-fix-loop": {
        "s": ["agent_loop.py", "matlabc_flow.py"],
        "q": ["agent_loop.py"], "l": ["agent_loop.py"],
        "fx": ["matlabc_flow.py"], "v": ["agent_loop.py"],
        "ap": ["agent_loop.py"], "fb": ["agent_loop.py"],
        "rv": ["agent_loop.py"], "clean": ["agent_loop.py"],
        "t2": ["agent_loop.py"], "ok": ["agent_loop.py"],
        "rg": ["matlabc_flow.py"],
    },
    "09-gates": {
        "all": ["tools/check_all.py"], "gate": ["tools/check_all.py"],
        "cache": ["tools/gate_cache.py"], "release": ["tools/release.py"],
        "ciy": [".github/workflows/ci.yml"],
        "manual": ["tools/lsp_selftest.py"], "exitn": ["matlabc.py"],
    },
    "10-porting": {
        "matlab": ["matlabc.py"], "ops": ["translate/operators.py"],
        "adp": ["translate/adapters.py"],
        "abi": ["c_runtime/include/mlc.h"],
        "cops": ["c_runtime/src/mlc_ops.c"],
        "fid": ["translate/fidelity.py"], "ledger": ["port_ledger.json"],
        "con": ["translate/contracts/matlab_c_constraints.json"],
        "gate": ["tools/check_translate_port.py"],
        "rt": ["c_runtime/include/mlc.h"],
    },
    "11-binary": {
        "attach": ["matlabc.py"], "pe": ["binfmt/pe.py"],
        "elf": ["binfmt/elf.py"], "macho": ["binfmt/macho.py"],
        "gpu": ["binfmt/gpu.py"], "resolve": ["binfmt/resolve.py"],
        "hops": ["binhops.py"], "out": ["binfmt/attribute.py"],
    },
    "12-dataflow": {
        "cfg": ["docs/matlabc_USAGE.md"], "src": ["matlabc.py"],
        "bin": ["binfmt/__init__.py"], "matlab": ["frontends/matlab.py"],
        "multi": ["frontends/ir.py"], "binfmt": ["binfmt/__init__.py"],
        "model": ["entity_model.py"], "graph": ["unified_graph.py"],
        "facts": ["facts.py"], "report": ["renderers/__init__.py"],
        "json": ["matlabc.py"], "lsp": ["matlabc_lsp.py"],
    },
    "13-sequence": {
        "editor": ["vscode/extension.js"],
        "client": ["vscode/lspClient.js"],
        "server": ["matlabc_lsp.py"], "analyzer": ["matlabc.py"],
        "cache": ["matlabc_lsp.py"], "fallback": ["vscode/extension.js"],
    },
}


def _head():
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, timeout=15)
    return (r.stdout or b"").decode("utf-8", "replace").strip()


def _git_exists(rev, path=None):
    spec = rev if path is None else "%s:%s" % (rev, path)
    r = subprocess.run(["git", "cat-file", "-e", spec], cwd=ROOT,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=15)
    return r.returncode == 0


def _nodes(cj):
    return (cj.get("components") or cj.get("nodes")
            or cj.get("participants") or cj.get("states") or [])


def _apply(iid, cj, sha):
    cj.setdefault("meta", {})["repository"] = {
        "url": REPO_URL, "provider": "github",
        "link_mode": "web", "revision": sha,
    }
    mapping = SRC.get(iid) or {}
    hit = 0
    for n in _nodes(cj):
        paths = [p for p in mapping.get(n.get("id"), [])
                 if os.path.isfile(os.path.join(ROOT, p))]
        if paths:
            n["sources"] = [{"path": p, "label": "main"}
                            for p in paths[:3]]
            hit += 1
    return hit


def main(argv=None):
    ap = argparse.ArgumentParser(description="给架构图补源码引用")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    with io.open(INDEX, "r", encoding="utf-8") as fh:
        items = json.load(fh).get("items") or []
    sha = _head()
    total = 0
    problems = []
    checked = 0
    for it in items:
        iid = it["id"]
        path = os.path.join(ARCH, it["candidate"])
        with io.open(path, "r", encoding="utf-8") as fh:
            cj = json.load(fh)
        if args.check:
            repo = (cj.get("meta") or {}).get("repository") or {}
            rev = repo.get("revision") or ""
            if not re.match(r"^[0-9a-fA-F]{40}$", rev):
                problems.append("%s revision 非法：%r" % (iid, rev))
            elif not _git_exists(rev):
                problems.append("%s revision 在 Git 中不存在：%s"
                                % (iid, rev))
            else:
                for n in _nodes(cj):
                    for src in n.get("sources") or []:
                        p = src.get("path")
                        if not p or not _git_exists(rev, p):
                            problems.append(
                                "%s 节点 %s 的 %r 在 %s 不存在"
                                % (iid, n.get("id"), p, rev[:7]))
            if iid in SRC and not repo:
                problems.append("%s 缺 repository" % iid)
            checked += 1
            continue
        if iid not in SRC:
            continue
        hit = _apply(iid, cj, sha)
        total += hit
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(cj, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("%-22s nodes_with_sources=%d" % (iid, hit))
    if args.check:
        if problems:
            for p in problems:
                print("  - %s" % p)
            return 1
        print("apply_arch_sources: OK（%d 张图的 revision 与 sources 在 Git 中存在）"
              % checked)
        return 0
    print("wrote 13 candidates；共 %d 个节点有源码引用（revision %s）"
          % (total, sha[:7]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
