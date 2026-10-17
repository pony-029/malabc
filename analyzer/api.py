# -*- coding: utf-8 -*-
"""analyzer/api.py —— 可被 import 的分析入口。

为什么需要它：LSP / MCP / 未来的插件都要在**同一进程内**多次调用分析，而
`matlabc.main` 会 `argparse`、`print`、`sys.exit`。本模块只做一件事：造出
`run_pipeline` 需要的参数对象，然后调它。

三条约束（都有对手方）：
- **不 argparse、不 sys.exit、不 print** —— LSP 的 stdout 是协议通道；
- **延迟 import `matlabc`** —— 本模块被 import 时不该拖入 34K 行模块级代码；
- **返回 `PipelineResult`，不返回报表** —— 报表是有损投影。

关于默认值：`run_pipeline` 的直接依赖只有 10 个 `args` 属性，但它调用的
`_build_dup_opts` 等间接依赖了 30+ 个。手工列默认值必漏，所以这里直接用
`cli_entry([])` 取 argparse 的**全部** 127 个默认值，再覆盖调用方给的。

副作用（必须知道）：`cli_entry` 会把 `sys.stdout/stderr` 重配成 UTF-8
（`matlabc.py` 的既有行为）。对 LSP 无害——协议写 `sys.stdout.buffer`——
但调用方若依赖原编码，需自行保存恢复。

用法：

    from analyzer.api import analyze, counts
    r = analyze("tests/sample_m")
    counts(r)        # {'files': 13, 'functions': 19, 'edges': 9, ...}
"""
from pathlib import Path


def _namespace(**kw):
    """用 argparse 的默认值造 `Namespace`，再覆盖调用方给的参数。

    未知参数直接 `TypeError` —— 静默忽略会让调用方以为自己配置生效了，
    这与本项目「不撒谎」相冲突。
    """
    import matlabc as M
    ns, _ap = M.cli_entry([])
    for key, val in kw.items():
        if not hasattr(ns, key):
            raise TypeError("未知参数：%s（`matlabc.py` 没有这个开关）" % key)
        setattr(ns, key, val)
    return ns


def analyze(root, **kw):
    """分析一个目录，返回 `PipelineResult`（不写盘、不打印、不退出）。

    抛 `ValueError` 表示目录不存在；其余异常原样向上抛（调用方负责呈现）。
    """
    import matlabc as M
    ns = _namespace(**kw)
    root_p = Path(str(root))
    if not root_p.is_dir():
        raise ValueError("目录不存在：%s" % root_p)
    paths = M.collect_files(root_p, recursive=not ns.no_recursive,
                            exclude=list(ns.exclude or ()))
    return M.run_pipeline(ns, root_p, paths)


def counts(result):
    """`PipelineResult` 上**真实存在**的四个计数。

    只有这四项能在这一层给：`files` / `functions` / `edges` / `checks`。
    `--json` 里的 `heuristics` 与 `unresolved` **不在这一层** —— 它们是
    `emit_outputs` 派生报表时才出现的东西；要在这里拿到，得先有事实层。

    这里不猜、不用 0 冒充：缺的就是不在。`checks` 对应
    `result.checks_for_sarif`（实测 6 条），它不是 `heuristics` 的别名。
    """
    return {
        "files": len(result.files),
        "functions": sum(len(getattr(mf, "functions", []) or [])
                         for mf in result.files),
        "edges": len(result.edges),
        "checks": len(getattr(result, "checks_for_sarif", None) or []),
    }
