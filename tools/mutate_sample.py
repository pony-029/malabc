# -*- coding: utf-8 -*-
"""变异抽样：把实现**改坏一处**，看判据会不会红。

为什么需要它
============

一套判据最危险的状态不是「红」，而是「**永远绿**」—— 它和没有判据等价，
但看起来更让人放心。而「加了判据」这件事本身无法证明它有效：

    def test():
        assert field_refs("x")["writes"] == writes      # 看起来对
        # 但若把实现里的 writes 换成 reads，这条仍然过？

所以抽样做**变异测试**：复制一份被测文件，把某处的语义改坏，
再跑对应判据组。**判据红了才算数**；没红说明它挡不住这种退化。

覆盖范围（R361 从 3 条扩到 10 条）
---------------------------------

    LSP 侧 7 条：字段读写拆分 / 字段基名 / 跨语言未解析 / 反向模式 /
                 C 内部下一跳 / 多层深度 / 防环 / mex 文件名 / 开关
    MCP 侧 3 条：impact 的未解析相减 / changed 的自环 / explain 的跨语言段 /
                 诊断落盘缓存的失效

三条纪律
--------

1. **绝不改仓库里的文件**：改的是副本，跑完即弃。
2. 每个变异都要**断言替换真的发生了**（否则样本没改动，判据当然不红）。
3. 判据红还不够，**要红在对应的那条**（按判据 id 找），
   否则可能只是别处先崩了 —— 那说明不了这一条有效。

用法：
    python tools/mutate_sample.py
    python tools/mutate_sample.py --only 字段      # 只跑名字含「字段」的

退出码：
    0  = 每个变异都被对应判据抓到
    1  = 有变异"存活"（判据没红，或红在别的判据上）
    2  = 缺输入（找不到判据脚本或被测文件）
"""
import argparse
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SELFTEST = os.path.join(HERE, "lsp_selftest.py")

#: 被测文件与「副本落点 + 环境变量」的对应关系。
#: 副本必须放在**仓库根目录**（换个文件名），不能放临时目录：
#: 被测文件启动时要 `import analyzer` / `import matlabc`，而子进程的
#: sys.path[0] 是**脚本所在目录** —— 放临时目录就 import 不到，服务端起不来。
TARGETS = {
    "lsp": ("matlabc_lsp.py", "_mut_matlabc_lsp.py", "MALABC_LSP"),
    "mcp": ("matlabc_mcp.py", "_mut_matlabc_mcp.py", "MALABC_MCP"),
}

#: (名字, 目标, 原文, 改坏成, 组, 期望红的判据 id 片段)
MUTATIONS = [
    # ---- LSP ----
    ("字段读写不再区分", "lsp",
     'writes = norm(ent.get("writes"))',
     'writes = norm(ent.get("reads"))',
     "--doc", "doc/field-refs-split"),
    ("字段基名恒为空", "lsp",
     '"bases": bases}',
     '"bases": []}',
     "--doc", "doc/field-refs-bases"),
    ("跨语言不再报告未解析", "lsp",
     '"unresolved": sorted(still),',
     '"unresolved": [],',
     "--doc", "doc/cbridge-lists-unresolved"),
    ("反向查询失效", "lsp",
     "if not found_matlab and name and name.lower() in idx:",
     "if not found_matlab and False:",
     "--doc", "doc/cbridge-reverse-mode"),
    ("C 内部下一跳丢失", "lsp",
     '_C_INDEX["model"] = model',
     '_C_INDEX["model"] = None',
     "--doc", "doc/cbridge-c-internal-call"),
    ("C 内部只展开一层", "lsp",
     "if _dep > 3:",
     "if _dep > 1:",
     "--doc", "doc/cbridge-c-multilevel"),
    ("互递归不再截断", "lsp",
     "if _cn in _seen:",
     "if False:",
     "--doc", "doc/cbridge-c-no-cycle"),
    ("mex 文件名匹配失效", "lsp",
     "for h in bidx.get(nm.lower(), []):",
     "for h in []:",
     "--doc", "doc/cbridge-mex-by-filename"),
    ("跨语言开关被忽略", "lsp",
     'if not _STATE.get("cross_lang", True):',
     "if False:",
     "--doc", "doc/cross-lang-switch-off"),
    # ---- MCP ----
    # ⚠ 这两条长得很像：impact 用 `bridged`，explain 用 `_found`。
    # 第一版只写了 `_found` 那条却命名成 impact —— 变异确实红了，
    # 但红在 explain 上，impact 的判据压根没被验过。
    ("impact 未解析不再相减", "mcp",
     'names = [n for n in (info.get("unresolved_names") or [])\n'
     '                 if n not in bridged]',
     'names = list(info.get("unresolved_names") or [])',
     "--doc", "mcp/impact-unresolved-excludes-bridged"),
    ("explain 未解析不再相减", "mcp",
     'names = [n for n in (info.get("unresolved_names") or [])\n'
     '                 if n not in _found]',
     'names = list(info.get("unresolved_names") or [])',
     "--doc", "mcp/explain-unresolved-excludes-bridged"),
    ("changed 把自环当来路", "mcp",
     'if len(ch) == 1 and ch[0].get("name") == nm:',
     "if False:",
     "--doc", "mcp/changed-no-self-echo"),
    ("explain 不带跨语言", "mcp",
     'if bridged:\n        out.append("")\n        out.append("## 跨语言")',
     'if False:\n        out.append("")\n        out.append("## 跨语言")',
     "--doc", "mcp/explain-includes-cbridge"),
    # 第 2 版：锁住「错误信息指向原因」这两处（R363）。
    ("找不到文件不回显路径", "mcp",
     'return _err("找不到文件：%s" % (raw or "（未给 path）"))\n'
     '    syms = L._document_symbols(_uri(path))',
     'return _err("找不到文件：%s" % path)\n'
     '    syms = L._document_symbols(_uri(path))',
     "--doc", "mcp/outline-echoes-path"),
    ("空名字不再报错", "mcp",
     '    if not name:\n'
     '        return _err("name 不能为空：请给一个函数名")\n'
     '    info = L._impact(name)\n'
     '    if info is None:\n'
     '        return _text("`%s` 不是本工程里的函数（或还没有分析到它）。" % name)',
     '    if False:\n'
     '        return _err("name 不能为空：请给一个函数名")\n'
     '    info = L._impact(name)\n'
     '    if info is None:\n'
     '        return _text("`%s` 不是本工程里的函数（或还没有分析到它）。" % name)',
     "--doc", "mcp/impact-empty-name"),
    ("诊断缓存永不失效", "mcp",
     'if (abs(float(doc.get("stamp") or 0) - float(stamp)) < 1e-6',
     "if (True",
     "--mcp", "mcp/payload-cache-invalidated"),
]


def run_mutation(name, target, old, new, group, expect_id):
    """复制副本 -> 改坏 -> 跑判据组 -> 判定。返回 (ok, detail)。"""
    src_name, dst_name, env_key = TARGETS[target]
    src_path = os.path.join(ROOT, src_name)
    dst = os.path.join(ROOT, dst_name)
    other = "MALABC_MCP" if env_key == "MALABC_LSP" else "MALABC_LSP"
    try:
        src = io.open(src_path, "r", encoding="utf-8").read()
        if old not in src:
            return False, "变异未应用：原文在 %s 里找不到（样本过期）" % src_name
        io.open(dst, "w", encoding="utf-8", newline="").write(
            src.replace(old, new, 1))

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env[env_key] = dst
        env.pop(other, None)
        log = os.path.join(tempfile.gettempdir(), "mut_out_%d.txt" % os.getpid())
        with io.open(log, "w", encoding="utf-8") as fh:
            try:
                subprocess.run([sys.executable, SELFTEST, group],
                               cwd=ROOT, stdin=subprocess.DEVNULL,
                               stdout=fh, stderr=subprocess.STDOUT,
                               env=env, timeout=300)
            except subprocess.TimeoutExpired:
                return False, "判据组超时（300s）"
        out = io.open(log, "r", encoding="utf-8", errors="replace").read()
        if "FAIL" not in out:
            return False, "变异存活：判据全绿，说明它挡不住这种退化"
        hit = [ln for ln in out.splitlines()
               if "FAIL" in ln and expect_id in ln]
        if not hit:
            first = [ln for ln in out.splitlines() if "FAIL" in ln][:1]
            return False, "红了，但不是 %s（先红的是：%s）" % (
                expect_id, (first[0].strip() if first else "?"))
        return True, hit[0].strip()[:88]
    finally:
        try:
            os.remove(dst)
        except OSError:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--only", default="")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    if args.help:
        sys.stdout.write(__doc__)
        return 0
    if not os.path.isfile(SELFTEST):
        print("mutate_sample: 缺输入（%s）" % SELFTEST)
        return 2

    picked = [m for m in MUTATIONS if not args.only or args.only in m[0]]
    if not picked:
        print("mutate_sample: --only 没匹配到任何样本")
        return 2

    bad = 0
    for name, target, old, new, group, expect in picked:
        ok, detail = run_mutation(name, target, old, new, group, expect)
        print("  [%s] %-18s %s" % ("抓到" if ok else "存活", name, detail))
        if not ok:
            bad += 1
    print("mutate_sample: %d 个变异，抓到 %d 个%s"
          % (len(picked), len(picked) - bad,
             "" if not bad else "，**%d 个存活**" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
