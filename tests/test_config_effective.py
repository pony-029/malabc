# -*- coding: utf-8 -*-
"""P1 判据：**配置真的生效**（不是"有配置模型"就行）。

## 背景（R769 的误判）

上一轮我用 `grep "m2c.project.json"` 找"谁读配置"，只找到 `translate/project_map.py`
的一行文档注释和 `project.rs` 的注释，于是写下"配置没有接线到生成器"。

**这是错的。** 接线在 `project_map.run_build()` 里：它把
`build_flags()`（从配置推导）交给 `cflags_string()` 拼成
`--static-pool/--pool-align`，再调 `m2c build`。grep 文件名找不到它，
因为它根本不出现那个文件名 —— 它读的是**已解析的 cfg 对象**。

所以这条判据守的不是"有没有配置模型"，而是三件可验证的事：
    P1a `build_flags` 随 `memory.pool_bytes` 变化
    P1b 拼出的命令行里确实带 `--static-pool <新值>`
    P1c 仓库里读这份配置的代码只有**一处**（唯一 reader）
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "translate"))

import project_map as PM          # noqa: E402

CFG = os.path.join(ROOT, "translate", "examples", "m2c.project.json")


def _cfg(pool=None):
    cfg = PM.load2(CFG)
    if pool is not None:
        for t in (cfg.get("targets") or {}).values():
            mem = t.get("memory") or {}
            if mem.get("strategy") == "static_pool":
                mem["pool_bytes"] = pool
    return cfg


def test_flags_follow_config():
    """P1a：改配置里的 pool_bytes，推导出的 flags 必须跟着变。"""
    a = PM.build_flags(_cfg())
    b = PM.build_flags(_cfg(32768))
    assert a["static_pool"] != b["static_pool"], \
        "改 pool_bytes 没影响 build_flags（%r vs %r）" % (
            a["static_pool"], b["static_pool"])


def test_cmdline_carries_pool_flag():
    """P1b：拼出来的命令行必须**真的**带 `--static-pool`，且是新值。"""
    s = PM.cflags_string(PM.build_flags(_cfg(32768)), os.path.join(ROOT, "x"))
    assert "--static-pool" in s, "命令行里没有 --static-pool：%r" % s
    assert "32768" in s, "命令行里的池大小不是配置值：%r" % s


def test_pool_reaches_generated_c():
    """P1d（端到端）：两个不同 `pool_bytes` 各构建一次，`gen.c` 里的池大小必须跟着变。

    前面三条都是**纯函数**（flags / 命令行）。这条走完整链路：
    配置 → `run_build` → `mir.py` → `m2c build` → `gen.c`。
    只验"参数推导对"是不够的 —— 参数可能推导对了却没被用上。
    """
    import shutil
    import tempfile

    root = os.path.join(ROOT, "translate", "examples")
    outs = {}
    for pool in (65536, 32768):
        d = tempfile.mkdtemp(prefix="p1d_", dir=os.environ.get("M2C_TMP") or None)
        try:
            cfg = _cfg(pool)
            cfg["matlab"]["root"] = os.path.join(root, cfg["matlab"]["root"])
            rc, _cmds, out = PM.run_build(cfg, d, CFG)
            assert rc == 0, "构建失败（pool=%d）：%s" % (pool, out[-400:])
            gen = os.path.join(d, cfg["c"]["root"], "src", "gen.c")
            assert os.path.isfile(gen), "没找到 gen.c：%s" % gen
            outs[pool] = io.open(gen, encoding="utf-8", errors="replace").read()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    assert outs[65536] != outs[32768], "两个 pool 配置产出了**完全相同**的 gen.c"
    assert "65536" in outs[65536], "pool=65536 时 gen.c 里没有 65536"
    assert "32768" in outs[32768], "pool=32768 时 gen.c 里没有 32768"


def test_single_reader():
    """P1c：配置只能有**一个解析点**（`project_map.load2`）。

    ⚠ 口径要精确（R780 被自己抓过一次）：
      * **允许**：任何模块 `import project_map` 后调 `PM.load2(...)` —— 那是**用** API；
      * **禁止**：自己 `json.load` 一份 `m2c.project.json` —— 那是**第二个解析点**，
        校验、默认值、键白名单全都会分叉。
    所以判据是「出现了配置文件名，却**没有**经过 project_map」。
    """
    hits = []
    for base, _dirs, files in os.walk(ROOT):
        if any(x in base for x in (os.sep + ".git", "node_modules", os.sep + "target")):
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(base, f)
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            if rel.startswith("tests/") or rel.startswith("translate/project_map.py"):
                continue
            try:
                src = io.open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            # 只在"碰了配置文件"的文件里判；碰了就必须走 project_map
            if "m2c.project.json" not in src and "load2(" not in src:
                continue
            if "project_map" in src:
                continue                      # 走的是唯一解析点，合规
            hits.append(rel)
    assert not hits, \
        "这些地方自己解析了配置（绕过 project_map.load2）：%r" % hits[:5]
