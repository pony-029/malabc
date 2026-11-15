# -*- coding: utf-8 -*-
"""**主线入口**：MATLAB 工程 → C 工程。

    python matlabc_toc.py 我的工程/ -o 出目录/

## 为什么是独立脚本，而不是 `matlabc.py --to-c`

`matlabc.py` **被一份 19 分钟的测量按 sha256 计量**（`docs/KERNEL_RUN.md` 的
provenance）。任何字节改动都会让那份读数作废 —— 这正是当初把帮助正文搬到
`matlabc_help.py` 的原因（见那个文件的 docstring）。

R874 我把 `--to-c` 直接加进了 `matlabc.py`，于是：

* `check_help_contract` 报 `--help` 漂移 +349/+300（合法增长，但没记账）；
* `check_kernel_snapshot` 报 **W2 读数陈旧**（sha 变了）；
* 修复要么重跑 19 分钟测量，要么把改动搬走。

搬走更对：**被计量的文件要保持稳定，新功能放进自己的入口**。

## 用法

    python matlabc_toc.py <源目录> [-o 产物目录] [--config 工程配置]

产物目录默认 `<源目录>/_m2c_build`；配置默认
`translate/examples/m2c.project.json`（dtypes/targets/prefix 全部沿用）。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CFG = os.path.join(HERE, "translate", "examples", "m2c.project.json")


def run_to_c(src_dir, out_dir=None, cfg_path=None):
    """执行转换，返回退出码。逻辑与 R874 里那份一致，只是搬到了本文件。"""
    src = os.path.abspath(src_dir)
    if not os.path.isdir(src):
        print("--to-c：不是目录：%s" % src, file=sys.stderr)
        return 2
    out = os.path.abspath(out_dir or os.path.join(src, "_m2c_build"))
    cfgs = os.path.abspath(cfg_path or DEFAULT_CFG)
    if not os.path.isfile(cfgs):
        print("--to-c：找不到工程配置：%s" % cfgs, file=sys.stderr)
        return 2
    tr = os.path.join(HERE, "translate")
    if tr not in sys.path:
        sys.path.insert(0, tr)
    try:
        import project_map as PM            # noqa: PLC0415
    except ImportError as e:
        print("--to-c：无法加载转换器（translate/project_map.py）：%s" % e,
              file=sys.stderr)
        return 2

    cfg = PM.load2(cfgs)
    # 用户目录覆盖配置里的相对 root —— 这是本入口存在的全部意义：
    # 同一套 dtypes/targets，作用在不同的 .m 树上。
    cfg["matlab"]["root"] = src
    print("[to-c] 源：%s" % src, flush=True)
    print("[to-c] 出：%s" % out, flush=True)
    rc, _log, text = PM.run_build(cfg, out, cfgs)
    if text:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    gen = os.path.join(out, cfg["c"]["root"])
    if rc != 0:
        print("[to-c] 失败（rc=%d）。产物目录：%s" % (rc, gen), file=sys.stderr)
        return rc or 1
    sp = os.path.join(gen, "src", "sources.txt")
    print("[to-c] 完成。C 工程：%s" % gen)
    print("[to-c] 源清单：%s" % sp if os.path.isfile(sp) else "[to-c] 未生成源清单")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="matlabc_toc",
        description="主线：把 MATLAB 工程转换成 C 工程（不再做结构分析）")
    ap.add_argument("src", help="MATLAB 工程根目录")
    ap.add_argument("-o", "--output", metavar="DIR",
                    help="产物目录（默认 <src>/_m2c_build）")
    ap.add_argument("--config", metavar="FILE",
                    help="工程配置（默认 translate/examples/m2c.project.json）")
    ns = ap.parse_args(argv)
    return run_to_c(ns.src, ns.output, ns.config)


if __name__ == "__main__":
    sys.exit(main())
