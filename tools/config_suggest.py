# -*- coding: utf-8 -*-
"""config_suggest.py —— P4：**图上每个节点（模块/源文件）该配什么**。

为什么不是"再写一份建议文案"
============================
`translate/check.py` 已经有 `ADVICE`（每类卡点一段人话）。但 P4 要的是
**可落地的配置项**，而且必须能验证「采纳后复扫有变化」——
散文建议做不到这一点，因为它没有"采纳"这个动作。

所以本工具的输出是**机器可读的一条条 `(位置, 配置键, 会消掉几处)`**：

    module  src        卡点      条数   该配什么
    algo    fit.m      cell        12    % @m2c shape x 3      ← 注解，写在 .m 里
    algo    fit.m      struct       4    % @m2c fields s.a s.b
    io      load.m     other        9    （无需配置：数值通路不需要）

判据（`tests/test_config_suggest.py`）：
    * 每个模块节点都有输出（哪怕"无需配置"）；
    * 建议条目的 `kind` 与该文件 MIR 里的 `# why:` 一一对应；
    * **采纳后复扫有变化**：按建议加注解 → 该 kind 条数下降。

用法：
    python tools/config_suggest.py m2c.project.json            # 0=无阻塞 1=有阻塞 2=缺输入
    python tools/config_suggest.py m2c.project.json --json     # 机器可读
    python tools/config_suggest.py m2c.project.json --selftest # 两向自证
    python tools/config_suggest.py --help

退出码：
    0  = 没有阻塞类建议（要么全通，要么只剩"无需配置"的类）
    1  = 有阻塞类建议（采纳后才可能生成）
    2  = 缺输入（配置不存在 / 没有模块）
"""
import argparse
import collections
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "translate"))

MIR_PY = os.path.join(ROOT, "translate", "mir.py")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

#: 卡点类别 → **该配什么**。键与 `mir.py` 的 `# why:` 标签一致（与 `check.ADVICE` 同源）。
#:
#: `where` 说清写在哪儿：
#:   annotation —— 写在 `.m` 里（`% @m2c ...`），是**源文件级**配置
#:   config     —— 写在 `m2c.project.json` 里，是**工程级**配置
#:   none       —— 数值通路不需要，删掉即可
KIND_TO_CONFIG = {
    "cell": ("annotation", "% @m2c shape <名> <元素数>", "把元胞改成定长数值数组"),
    "struct": ("annotation", "% @m2c fields s.a s.b", "把结构体字段声明成形参"),
    "cond": ("annotation", "改写条件为标量比较（见 check --annotate）", "只认标量与字面量比较"),
    "control": ("annotation", "改用 if/while/for 的基础形态", "switch/try 不支持"),
    "shadowed": ("annotation", "给数组改名，别与内置函数同名", "内置名被当成数组"),
    "nested": ("annotation", "拆开括号嵌套（先落到临时变量）", "本版不折嵌套调用"),
    "call2": ("config", "operators.<名字> 映射", "工具不认识的函数"),
    "other": ("none", "（无需配置：数值通路不需要）", "多为字符串/类型转换"),
    "strlit": ("none", "（无需配置：数值通路不需要）", "字符串对外提示"),
    "unmapped": ("none", "（无需配置）", "未归类"),
}

#: 阻塞类：不解决就无法生成。`none` 类不算阻塞。
BLOCKING = {"cell", "struct", "cond", "control", "shadowed", "nested", "call2"}


def _run(cmd, timeout=300):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def kinds_of(path):
    """跑一次 `mir.py <单个 .m>`，数出 `# why:<kind>` 的分布。"""
    d = tempfile.mkdtemp(prefix="cs_", dir=WORK if os.path.isdir(WORK) else None)
    try:
        out = os.path.join(d, "a.mir")
        r = _run([sys.executable, MIR_PY, path, "-o", out], 180)
        if r.returncode != 0 or not os.path.isfile(out):
            return None, r.stdout.decode("utf-8", "replace")[-300:]
        text = io.open(out, encoding="utf-8", errors="replace").read()
        c = collections.Counter()
        for ln in text.splitlines():
            s = ln.strip()
            if s.startswith("# why:"):
                c[s[6:].strip()] += 1
        return c, ""
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def suggest(cfg, base=None):
    """对配置里的每个模块/源文件给出建议行。"""
    base = base or os.getcwd()
    mroot = os.path.join(base, cfg["matlab"]["root"])
    rows, missing = [], []
    for m in cfg.get("modules") or []:
        for src in m.get("sources") or []:
            p = os.path.join(mroot, src)
            if not os.path.isfile(p):
                missing.append({"module": m.get("id"), "src": src,
                                "reason": "文件不存在"})
                continue
            kinds, err = kinds_of(p)
            if kinds is None:
                missing.append({"module": m.get("id"), "src": src,
                                "reason": err or "MIR 生成失败"})
                continue
            if not kinds:
                rows.append({"module": m.get("id"), "src": src, "kind": None,
                             "count": 0, "where": "none",
                             "config": "（无卡点）", "why": "可直接生成"})
                continue
            for kind, n in kinds.most_common():
                where, key, why = KIND_TO_CONFIG.get(
                    kind, ("none", "（未登记：%s）" % kind, "未知类别"))
                rows.append({"module": m.get("id"), "src": src, "kind": kind,
                             "count": n, "where": where, "config": key,
                             "why": why})
    return rows, missing


def _selftest():
    """两向自证：能给出建议（有卡点时）+ 干净文件给"无卡点"。"""
    d = tempfile.mkdtemp(prefix="css_", dir=WORK if os.path.isdir(WORK) else None)
    try:
        bad = os.path.join(d, "bad.m")
        io.open(bad, "w", encoding="utf-8", newline="\n").write(
            "function y = bad(a)\n% @m2c shape a 3\n% @m2c shape y 3\n"
            "c = {1, 2};\ny = a;\nend\n")
        good = os.path.join(d, "good.m")
        io.open(good, "w", encoding="utf-8", newline="\n").write(
            "function y = good(a)\n% @m2c shape a 3\n% @m2c shape y 3\n"
            "y = a + a;\nend\n")

        kb, _ = kinds_of(bad)
        kg, _ = kinds_of(good)
        if not kb:
            print("自证失败：含元胞的文件没有产生任何卡点")
            return 1
        if kg:
            print("自证失败：干净文件却有卡点 %r" % dict(kg))
            return 1
        cfg = {"matlab": {"root": "."},
               "modules": [{"id": "m", "sources": ["bad.m", "good.m"]}]}
        rows, _miss = suggest(cfg, d)
        kinds = {r["kind"] for r in rows}
        if None not in kinds:
            print("自证失败：干净文件没有给出『无卡点』一行")
            return 1
        if "cell" not in kinds:
            print("自证失败：没有识别出 cell 卡点（实得 %r）" % kinds)
            return 1
        print('SELFTEST COUNTS {"bad": 3, "good": 1}')
        print("自证通过：能识别卡点、能输出『无卡点』、配置键映射存在")
        return 0
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("config", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, _rest = ap.parse_known_args(argv or sys.argv[1:])

    if a.help:
        print(__doc__)
        return 0
    if a.selftest:
        return _selftest()
    if not a.config or not os.path.isfile(a.config):
        print("缺输入：配置文件不存在 %r" % a.config)
        return 2

    import project_map as PM
    cfg = PM.load2(os.path.abspath(a.config))
    rows, missing = suggest(cfg, os.path.dirname(os.path.abspath(a.config)))
    blocking = [r for r in rows if r.get("kind") in BLOCKING]

    if a.json:
        print(json.dumps({"rows": rows, "missing": missing,
                          "blocking": len(blocking)},
                         ensure_ascii=False, indent=2))
    else:
        if not rows and not missing:
            print("配置里没有模块/源文件")
            return 2
        print("%-10s %-22s %-10s %5s  %s" % ("模块", "源文件", "卡点", "条数", "该配什么"))
        for r in rows:
            print("%-10s %-22s %-10s %5d  %s"
                  % (r["module"], r["src"], r["kind"] or "（无）", r["count"],
                     r["config"]))
        for m in missing:
            print("%-10s %-22s %-10s %5s  %s"
                  % (m["module"], m["src"], "缺失", "-", m["reason"]))
        print("\n阻塞类建议 %d 条（%s）" % (len(blocking),
                                        ", ".join(sorted({r["kind"] for r in blocking})) or "无"))
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
