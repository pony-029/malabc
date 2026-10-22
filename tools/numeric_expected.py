# -*- coding: utf-8 -*-
"""numeric_expected.py —— 用 **Octave 真值** 生成/校验 `numeric.expected`。

## 为什么必须自动化

期望文件是人手抄的，就会漂移：改一条 `.m`、忘了改期望，门要么假绿要么假红。
而"真值"不需要人抄 —— 它应该由参考实现（Octave）算出来。

## 约定

- 输入构造与生成的 `main.c` **完全一致**：数组 `a[i]=i+1`（行主序）、标量 `2`
- 含未映射语句的函数（转不成 C 的）期望写 `unimplemented`
  —— 这锁住"不支持就如实说"，而不是留空让人猜

用法：
    python tools/numeric_expected.py --update     # 重算并写回
    python tools/numeric_expected.py             # 只核对，不写
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import mir_eval  # noqa: E402
import tools.parity_report as PR  # noqa: E402

SRC = os.path.join(ROOT, "translate", "examples", "numeric")
EXP = os.path.join(ROOT, "translate", "examples", "numeric.expected")


def compute(mir_path):
    """跑 Octave，返回 {函数名: "值串" 或 "unimplemented"}。"""
    cli = PR._octave_cli()
    if not cli:
        return None
    funcs = mir_eval.parse(io.open(mir_path, encoding="utf-8").read())
    d = tempfile.mkdtemp(prefix="num_exp_")
    drv = os.path.join(d, "driver_all.m")
    io.open(drv, "w", encoding="utf-8", newline="").write(PR._driver(funcs))
    rc, out = PR._run([cli, "--no-gui", "--quiet", "--eval",
                       "addpath('%s'); run('%s')"
                       % (SRC.replace("\\", "/"), drv.replace("\\", "/"))],
                      cwd=d, timeout=600)
    if rc != 0:
        return None
    got = PR._c_lines(out)
    rows = {}
    for f in funcs:
        if f.unmapped:
            rows[f.name] = "unimplemented"     # 转不了 -> 如实
        elif f.name in got:
            rows[f.name] = got[f.name].split(": ", 1)[1].strip()
        else:
            rows[f.name] = "unimplemented"
    return rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    mir = os.path.join(tempfile.gettempdir(), "numeric_expected.mir")
    import subprocess
    p = subprocess.run([sys.executable,
                        os.path.join(ROOT, "translate", "mir.py"), SRC,
                        "-o", mir], stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
    if p.returncode != 0:
        print("生成 MIR 失败：%s"
              % p.stdout.decode("utf-8", "replace").strip()[-160:])
        return 2
    rows = compute(mir)
    if rows is None:
        print("PA4 未跑（缺 Octave/MATLAB 或参考实现出错）")
        return 2

    lines = ["%s: %s" % (k, v) for k, v in sorted(rows.items())]
    text = "\r\n".join(lines) + "\r\n"
    if "--update" in argv:
        io.open(EXP, "w", encoding="utf-8", newline="").write(text)
        print("已写回 %d 行到 numeric.expected" % len(lines))
        return 0

    want = io.open(EXP, encoding="utf-8").read().replace("\r\n", "\n")
    if want.strip() == text.replace("\r\n", "\n").strip():
        print("numeric.expected 与 Octave 真值一致（%d 个函数）" % len(lines))
        return 0
    print("numeric.expected 已过期，请跑 --update：")
    for a, b in zip(want.splitlines(), text.splitlines()):
        if a.strip() != b.strip():
            print("   期望 %-28r 实际 %r" % (a, b))
            break
    return 1


if __name__ == "__main__":
    sys.exit(main())
