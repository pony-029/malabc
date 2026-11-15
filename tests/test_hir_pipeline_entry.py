# -*- coding: utf-8 -*-
"""**HIR 在主线里的位置**：它接管算子区，控制流仍由 `mir.py` 的行锚定解析产出。

## 为什么值得钉

R877/R878 我连着两轮往 `translate/mir.py` 里加控制流（`elseif`、`switch`），
而本仓有 HIR 层（P5「HIR 接管」）—— 很容易被问、也很容易被误判成"改错了层"。

实测的链路是：

    MATLAB 源码 --(mir.py 行锚定解析)--> MIR 文本 --(hir_gate + hir_emit)--> MIR --> m2c --> C

* `hir_emit` 只重写 **`op:` 算子区**（表达式树），把 `if:` / `else` / `end` /
  `for:` / `while` 这些**结构行原样透传**；
* 因此**控制流的解析只能在 `mir.py`**，HIR 不是它的替代品；
* 而 `project_map.run_build` 是**起 `mir.py` 子进程**，所以 `mir.py` 的
  `__main__` 一旦不再调 `hir_gate`/`hir_emit`，HIR 就**静默退出生产路径** ——
  这正是这条判据要防的事（`mir.py:2356` 的注释写着：此前 HIR 从未出现在生产路径上）。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR = os.path.join(ROOT, "translate", "mir.py")
PM = os.path.join(ROOT, "translate", "project_map.py")
if os.path.join(ROOT, "translate") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "translate"))


def _src(p):
    return io.open(p, encoding="utf-8", errors="replace").read()


def test_hir_emit_is_on_by_default():
    """`--hir-emit` 默认**开**（关掉它就等于 HIR 不在链上）。"""
    s = _src(MIR)
    assert re.search(r"set_defaults\(\s*hir_emit\s*=\s*True\s*\)", s), \
        "mir.py 的 --hir-emit 默认值不是 True（HIR 会静默退出生产路径）"


def test_main_runs_both_hir_gate_and_emit():
    """`__main__` 必须同时调用 `hir_gate`（校验）与 `hir_emit`（产出）。"""
    s = _src(MIR)
    assert "hir_gate(text)" in s, "mir.py 不再调用 hir_gate（契约校验消失）"
    # ⚠ 调用点在 `main()` 里，不在 `if __name__` 块（那里只有 sys.exit(main())）——
    # 第一版按 `__main__` 之后切片，断言直接红，属于我切错了位置。
    calls = len(re.findall(r"hir_emit\(text\)", s))
    assert calls >= 2, \
        "hir_emit 的调用点只有 %d 处（应在 main() 的两条分支里各一处）" % calls


def test_run_build_goes_through_mir_py():
    """生产路径（`run_build`）必须起 `mir.py` 子进程 —— 否则上面的开关都无意义。"""
    s = _src(PM)
    assert '"mir.py"' in s, "project_map 不再调用 mir.py（主线绕开了 MIR/HIR）"


def test_control_flow_passes_through_hir_emit():
    """**行为判据**：`switch` 降级出的 if 链经 `hir_emit` 后结构不变、算子不变。

    这是 R878 改动的直接守护：HIR 只重写算子区，结构行必须原样留下 ——
    否则控制流会在 HIR 那一步被吞掉，而生成物照样能编译。
    """
    import mir as M

    src = ("function y = sw(n)\n"
           "% @m2c shape n 1\n"
           "% @m2c shape y 1\n"
           "switch n\n  case 1\n    y = n;\n  otherwise\n    y = n;\nend\nend\n")
    text, _stats = M.to_mir(src)
    assert "if:" in text and "else" in text, "switch 没被降成 if 链：\n%s" % text[:300]

    before = sorted(re.findall(r"^op:(OP-[A-Z0-9]+):", text, re.M))
    out, _passed = M.hir_emit(text)
    after = sorted(re.findall(r"^op:(OP-[A-Z0-9]+):", out, re.M))
    assert before == after, "hir_emit 改了算子集合：%r → %r" % (before, after)
    for kw in ("if:", "else", "end"):
        assert kw in out, "hir_emit 把结构行 %r 吞掉了" % kw
