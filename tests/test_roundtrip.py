# -*- coding: utf-8 -*-
"""**往返验证**：`.m → MIR → .m' → 跑数值`，与原函数真值比对。

## 为什么这条最重要

正向错译会编译不过或跑出怪值，很快暴露；**回译错了生成的是合法 MATLAB**：
语法完美、能跑、有输出，只是算的不是同一件事。唯一可信的验收是
**在目标语言里执行并比对数值**。

## 为什么逐个函数跑、且给短超时

第一版把整个目录交给一次 Octave（driver 里串起所有函数），结果**跑满 600 秒超时** ——
某个回译产物死循环（`while` 的条件变量被改坏之类），一个坏函数拖垮整批，
而且**看不出是哪一个**。逐函数 + 20 秒上限之后，坏的那个只影响自己，并被记为 `hang`。

`hang` 不算失败（它说明回译器在该形态上不保语义），但**计入分母并打出来** ——
不能让"跳过"悄悄把成功率抬高。
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import unmir as U            # noqa: E402
import tools.parity_report as PR             # noqa: E402
from translate import mir_eval               # noqa: E402

CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
TMPROOT = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"
PER_FN_TIMEOUT = 20          # 单个函数上限：死循环只赔 20 秒


def _mir_one(src, out):
    return subprocess.run([sys.executable, MIR_PY, src, "-o", out],
                          stdin=subprocess.DEVNULL, timeout=300,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _values(cli, funcs, addpath, workdir):
    """跑一个函数，返回值串；超时/失败返回标记。"""
    drv = os.path.join(workdir, "drv.m")
    io.open(drv, "w", encoding="utf-8", newline="\n").write(PR._driver(funcs))
    try:
        rc, out = PR._run([cli, "--no-gui", "--quiet", "--eval",
                           "addpath('%s'); run('%s')"
                           % (addpath.replace("\\", "/"), drv.replace("\\", "/"))],
                          cwd=workdir, timeout=PER_FN_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "hang"
    if rc != 0:
        return "error"
    got = PR._c_lines(out)
    f = funcs[0].name
    return got[f].split(": ", 1)[1].strip() if f in got else "missing"


def _norm(s):
    return " ".join((s or "").split())


@pytest.mark.skipif(PR._octave_cli() is None, reason="没有 Octave/MATLAB 参考实现")
def test_roundtrip_values_match():
    cli = PR._octave_cli()
    base = TMPROOT if os.path.isdir(TMPROOT) else None
    d = tempfile.mkdtemp(prefix="m2c_rt_", dir=base)
    back_dir = os.path.join(d, "back")
    mir_dir = os.path.join(d, "mir")
    work = os.path.join(d, "work")
    for p in (back_dir, mir_dir, work):
        os.makedirs(p, exist_ok=True)

    same, diff, skip, hang = [], [], [], []
    try:
        for fn in sorted(os.listdir(CORPUS)):
            if not fn.endswith(".m"):
                continue
            src = os.path.join(CORPUS, fn)
            mir = os.path.join(mir_dir, fn + ".mir")
            if _mir_one(src, mir).returncode != 0 or not os.path.isfile(mir):
                skip.append(fn)
                continue
            out_m = os.path.join(back_dir, fn)
            if U.convert(mir, out_m):
                skip.append(fn)              # 有算子回译不了：不算它的账
                os.remove(out_m)
                continue

            funcs = mir_eval.parse(io.open(mir, encoding="utf-8").read())
            if len(funcs) != 1 or funcs[0].unmapped:
                skip.append(fn)
                continue

            va = _values(cli, funcs, CORPUS, work)
            if va in ("hang", "error", "missing"):
                skip.append(fn)              # 原函数就跑不出来：不是回译的锅
                continue
            vb = _values(cli, funcs, back_dir, work)
            if vb == "hang":
                hang.append(fn)
            elif vb == "error" or vb == "missing":
                diff.append((fn, _norm(va), vb))
            elif _norm(va) == _norm(vb):
                same.append(fn)
            else:
                diff.append((fn, _norm(va), _norm(vb)))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    total = len(same) + len(diff) + len(hang)
    assert total > 0, "没有一个函数完成往返（整条链路断了）"
    print("往返一致 %d/%d ｜ 不一致 %d ｜ 超时 %d ｜ 跳过 %d"
          % (len(same), total, len(diff), len(hang), len(skip)))
    if diff or hang:
        print("  问题函数：%r" % ((diff[:4] + [(h, "hang") for h in hang[:4]]),))
    assert not diff, "往返数值不一致：%r" % (diff[:4],)
    assert not hang, "回译产物死循环（20s 超时）：%r" % (hang[:4],)
