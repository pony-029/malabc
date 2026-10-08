# -*- coding: utf-8 -*-
"""一键跑完所有登记制静态护栏。

返回值：0=全绿；1=有护栏失败/护栏缺自证；2=找不到护栏（缺输入 → 红）。

为什么需要它：护栏分散成多个 `tools/check_*.py`，靠人记得逐个跑等于没有门。
本 runner 与 `tests/test_matlabc.py::test_r30_static_guards_all_clean` 是同一
判据的两个入口 —— 前者给 CI/人手，后者保证「新加的护栏会被自动收进测试」。

它自己也必须**能红**：`--selftest` 用临时目录造四个样本，
证明「坏护栏会被抓、好护栏会被放、缺自证的护栏会被抓、空目录会红」。
一个只会在好天气下变绿的 runner，本身也是一道假门。

用法：
    python tools/check_all.py                 # 跑 tools/ 下全部护栏
    python tools/check_all.py --tools-dir D   # 指定护栏目录（自证/CI 复用）
    python tools/check_all.py --selftest      # 自证：双向验证本 runner
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile

R_BAD_GUARD = """import sys
print("[FAIL] 样本护栏：故意失败")
sys.exit(1)
"""

R_GOOD_GUARD = """import sys
print("check_ok: OK")
if "--selftest" in sys.argv:
    print('SELFTEST COUNTS {"bad": 0, "good": 1}')
sys.exit(0)
"""

R_NO_SELFTEST_GUARD = """import sys
print("check_noself: OK")
sys.exit(0)
"""


def run_guards(tools_dir, python_exe=None):
    """跑目录下全部 check_*.py（不含本文件）；返回 (bad 列表, 护栏名列表)。"""
    py = python_exe or sys.executable
    if not os.path.isdir(tools_dir):
        print("check_all: 护栏目录不存在：%s（缺输入 → 红）" % tools_dir)
        return None, []
    me = os.path.basename(os.path.abspath(__file__))
    guards = sorted(f for f in os.listdir(tools_dir)
                    if f.startswith("check_") and f.endswith(".py")
                    and f != me)
    if not guards:
        print("check_all: 未找到任何 tools/check_*.py（缺输入 → 红）")
        return None, []
    bad = []
    for g in guards:
        p = os.path.join(tools_dir, g)
        r = subprocess.run([py, p], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
        ok = r.returncode == 0
        sout = r.stdout.decode("utf-8", "replace")
        last = sout.strip().splitlines()[-1][:110] if sout.strip() else ""
        print("[%s] %-24s %s" % ("OK  " if ok else "FAIL", g, last))
        if not ok:
            bad.append(g)
        # 每个护栏必须自带并能通过 --selftest，否则是一道可能永远绿的门
        s = subprocess.run([py, p, "--selftest"], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
        s_sout = s.stdout.decode("utf-8", "replace")
        if s.returncode != 0 or "SELFTEST COUNTS" not in s_sout:
            print("[FAIL] %-24s （--selftest 缺失或不通过）" % g)
            bad.append(g + "(selftest)")
    return bad, guards


def main(argv):
    if "--selftest" in argv:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if (bad == 0 and good >= 4) else 1

    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if "--tools-dir" in argv:
        i = argv.index("--tools-dir")
        if i + 1 >= len(argv):
            print("check_all: --tools-dir 需要一个路径（缺输入 → 红）")
            return 2
        tools_dir = argv[i + 1]

    bad, guards = run_guards(tools_dir)
    if bad is None:
        return 2
    if bad:
        print("check_all: %d 项失败：%s" % (len(bad), bad))
        return 1
    print("check_all: OK（%d 个护栏，全部通过且各自自证）" % len(guards))
    return 0


def _selftest():
    """双向自证：既造坏样本（必须红），也造好样本（必须绿）。

    四项断言缺一不可：
      ① 坏护栏（rc=1）         -> runner 必须返回 1
      ② 好护栏（rc=0 且有自证） -> runner 必须返回 0
      ③ 缺自证的护栏           -> runner 必须返回 1（否则「无自证」会被静默放行）
      ④ 空目录                 -> runner 必须返回 2（缺输入 → 红）
    """
    bad = good = 0
    tmp = tempfile.mkdtemp(prefix="chk_all_selftest_")
    try:
        def _mk(name, text):
            p = os.path.join(tmp, name)
            with io.open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
            return p

        # ① 坏护栏
        d1 = os.path.join(tmp, "d1")
        os.makedirs(d1)
        _mk(os.path.join(d1, "check_bad.py"), R_BAD_GUARD)
        b1, _g1 = run_guards(d1)
        if b1:
            good += 1
        else:
            bad += 1
            print("  [selftest] 坏护栏未被 runner 抓到")

        # ② 好护栏
        d2 = os.path.join(tmp, "d2")
        os.makedirs(d2)
        _mk(os.path.join(d2, "check_good.py"), R_GOOD_GUARD)
        b2, g2 = run_guards(d2)
        if b2 == [] and g2 == ["check_good.py"]:
            good += 1
        else:
            bad += 1
            print("  [selftest] 好护栏被误伤：bad=%r guards=%r" % (b2, g2))

        # ③ 缺自证的护栏
        d3 = os.path.join(tmp, "d3")
        os.makedirs(d3)
        _mk(os.path.join(d3, "check_noself.py"), R_NO_SELFTEST_GUARD)
        b3, _g3 = run_guards(d3)
        if b3:
            good += 1
        else:
            bad += 1
            print("  [selftest] 缺自证的护栏被静默放行")

        # ④ 空目录
        d4 = os.path.join(tmp, "d4")
        os.makedirs(d4)
        b4, _g4 = run_guards(d4)
        if b4 is None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 空目录未变红：%r" % (b4,))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad, good


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
