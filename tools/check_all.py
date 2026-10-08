# -*- coding: utf-8 -*-
"""一键跑完所有登记制静态护栏。

一图看懂：

    python tools/check_all.py
        │
        ├─▶ check_binfmt_fixtures.py      合成夹具 + 契约 C1..C6 + 两向自证
        ├─▶ check_doc_flags.py            文档/帮助里写的 CLI 开关必须真的存在
        ├─▶ check_operator_impl.py        算子元表里不得有「只声明不产出」的幻影
        ├─▶ check_patch_ops.py            补丁编辑算子唯一事实源（禁止覆盖式赋值）
        ├─▶ check_py36_clean.py           本仓源码必须通过本仓自己的 3.6.5 门
        └─▶ check_subprocess_hygiene.py   子进程必须切 stdin 且不会永久挂住
        │
        ├─ 每道护栏都要能跑通（rc=0）
        ├─ 每道护栏都要有 --selftest（两向自证：坏样本要红、好样本要过）
        └─ 每个子进程都 stdin=DEVNULL + 墙钟超时（挂死 → 判红，不让门永远等）
        │
        ▼
    0 = 全绿   1 = 有护栏失败或护栏缺自证   2 = 找不到护栏（缺输入 → 红）

为什么需要它：护栏分散成多个 `tools/check_*.py`，靠人记得逐个跑等于没有门。
本 runner 与 `tests/test_matlabc.py::test_r30_static_guards_all_clean` 是同一
判据的两个入口 —— 前者给 CI/人手，后者保证「新加的护栏会被自动收进测试」。

它自己也必须**能红**：`--selftest` 用临时目录造五个样本，
证明「坏护栏会被抓、好护栏会被放、缺自证的护栏会被抓、空目录会红、
**永不退出的护栏会被超时判红**」。
一个只会在好天气下变绿的 runner，本身也是一道假门；
一条会**永远挂住**的链比一道闸门更糟 —— 所以每个子进程都带 `stdin=DEVNULL`
与墙钟超时（见 `_run` 的注释：这是 R62-R31e 修掉的一个真缺陷）。

用法：
    python tools/check_all.py                 # 跑 tools/ 下全部护栏
    python tools/check_all.py --tools-dir D   # 指定护栏目录（自证/CI 复用）
    python tools/check_all.py --selftest      # 自证：双向验证本 runner
    python tools/check_all.py --help          # 显示本帮助（立即返回，不跑护栏）
"""
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

R_HANG_GUARD = """import time
print("check_hang: 我永远不退出", flush=True)
time.sleep(3600)
"""

# 单个护栏的墙钟上限。存在意义：**让挂死变成红，而不是让门永远等着**。
# 实测全部护栏各自 <2s，600s 是给未来重护栏留的量级余量。
GUARD_TIMEOUT = 600.0


def _write_help(text):
    """把帮助文本写到 stdout，强制 UTF-8（本仓文档里有中文与制表框字符）。

    被管道/CI 调用时 Python 会退回 locale 编码（中文 Windows 是 GBK）；
    与 matlabc.py / gui.py 的处理保持一致：先 reconfigure，失败再写 buffer。
    """
    for _s in (sys.stdout, sys.stderr):
        if _s is not None and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
        return True
    except Exception:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is None:
            return False
        try:
            buf.write(text.encode("utf-8", "replace"))
            buf.flush()
            return True
        except Exception:
            return False


def _run(py, argv, cwd=None, timeout=GUARD_TIMEOUT):
    """跑一个子进程，返回 (rc, 文本输出)；超时标记 rc=None（= 红）。

    ⚠ `stdin=subprocess.DEVNULL` 不是洁癖，是 R62-R31e 修掉的**真缺陷**：
    本仓 `matlabc_mcp.py` 是 stdio JSON-RPC server，`--help` 遇到一个继承来的、
    永不 EOF 的 stdin 就永久阻塞（实测 >30s；切断后 0.5s）。护栏会 spawn
    `*-.py --help`，stdin 一路继承到最里层，把整条链挂住（探针 probe_r26b_pipe）。

    ⚠ 旧实现用 `subprocess.run(stdout=PIPE)`，**没有 timeout**：
    只要有一个护栏不退出，`check_all.py`（以及 CI）就永远挂住。
    一条会挂死的链比一道闸门更糟 —— 所以超时在这里是**判红依据**，不是省事。
    """
    try:
        p = subprocess.Popen([py] + list(argv), cwd=cwd,
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
    except OSError as e:
        return None, "启动失败：%s" % e
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        return None, "超时 >%.0fs（护栏不退出 —— 按红处理）" % timeout


def run_guards(tools_dir, python_exe=None, timeout=GUARD_TIMEOUT):
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
        rc, sout = _run(py, [p], timeout=timeout)
        ok = rc == 0
        last = sout.strip().splitlines()[-1][:110] if sout.strip() else ""
        print("[%s] %-24s %s" % ("OK  " if ok else "FAIL", g, last))
        if not ok:
            bad.append(g if rc is not None else g + "(timeout)")
        # 每个护栏必须自带并能通过 --selftest，否则是一道可能永远绿的门
        s_rc, s_sout = _run(py, [p, "--selftest"], timeout=timeout)
        if s_rc != 0 or "SELFTEST COUNTS" not in s_sout:
            why = "挂死（超时）" if s_rc is None else "缺失或不通过"
            print("[FAIL] %-24s （--selftest %s）" % (g, why))
            bad.append(g + "(selftest)")
    return bad, guards


def main(argv):
    # --help 必须在**任何副作用之前**返回。早先它没有分支，于是
    # `python tools/check_all.py --help` 会真的把全套护栏跑一遍（≈30s）——
    # 对「问一句怎么用」的人来说是纯粹的意外，在 CI 里则是无谓的挂钟开销。
    if "--help" in argv or "-h" in argv:
        if not _write_help(__doc__):
            return 2
        return 0
    if "--selftest" in argv:
        bad, good = _selftest()
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if (bad == 0 and good >= 5) else 1

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

    五项断言缺一不可：
      ① 坏护栏（rc=1）         -> runner 必须返回 1
      ② 好护栏（rc=0 且有自证） -> runner 必须返回 0
      ③ 缺自证的护栏           -> runner 必须返回 1（否则「无自证」会被静默放行）
      ④ 空目录                 -> runner 必须返回 2（缺输入 → 红）
      ⑤ **永不退出的护栏**     -> runner 必须在超时后返回 1（R62-R31e 新增：
         一条会挂死的链比一道闸门更糟 —— 旧实现没有 timeout，一个不退出
         的护栏会让 check_all 和 CI 永远等下去。这里用 3s 超时把它变成红。）
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

        # ⑤ 永不退出的护栏（用 3s 超时把挂死变成红，而不是让自证自己也挂住）
        d5 = os.path.join(tmp, "d5")
        os.makedirs(d5)
        _mk(os.path.join(d5, "check_hang.py"), R_HANG_GUARD)
        b5, _g5 = run_guards(d5, timeout=3.0)
        if b5 and any("timeout" in x for x in b5):
            good += 1
        else:
            bad += 1
            print("  [selftest] 永不退出的护栏未被超时判红：%r" % (b5,))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad, good


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
