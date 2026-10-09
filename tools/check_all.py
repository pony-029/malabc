# -*- coding: utf-8 -*-
"""一键跑完所有登记制静态护栏。

一图看懂：

    python tools/check_all.py
        │
        ├─▶ check_baseline.py             公平基线：按 nodeid 集合比失败（--full 才真跑）
        ├─▶ check_binfmt_fixtures.py      合成夹具 + 契约 C1..C9 + 两向自证
        ├─▶ check_doc_flags.py            文档/帮助里写的 CLI 开关必须真的存在
        ├─▶ check_flow_diagrams.py        图的引用 ↔ 文件 ↔ 候选声明，两两对齐且双向
        ├─▶ check_help_contract.py        退出码在代码↔帮助双向一致；示例能真跑
        ├─▶ check_ir_attribution.py       「解析不到的调用」只有一个判定点，归因吃的就是它
        ├─▶ check_operator_impl.py        算子元表里不得有「只声明不产出」的幻影
        ├─▶ check_patch_ops.py            补丁编辑算子唯一事实源（禁止覆盖式赋值）
        ├─▶ check_py36_clean.py           本仓源码必须通过本仓自己的 3.6.5 门
        ├─▶ check_readme_parity.py        中英 README 逐节结构对等
        └─▶ check_subprocess_hygiene.py   子进程必须切 stdin 且不会永久挂住
        │
        ├─ 每道护栏都要能跑通（rc=0）
        ├─ 每道护栏都要有 --selftest（两向自证：坏样本要红、好样本要过）
        ├─ 门数不得少于 MIN_GUARDS（R33/C'9：删掉一道门也会变红）
        └─ 每个子进程都 stdin=DEVNULL + 墙钟超时（挂死 → 判红，不让门永远等）
        │
        ▼
    0 = 全绿   1 = 有护栏失败/缺自证/门数不足   2 = 找不到护栏（缺输入 → 红）

为什么需要它：护栏分散成多个 `tools/check_*.py`，靠人记得逐个跑等于没有门。
本 runner 与 `tests/test_matlabc.py::test_r30_static_guards_all_clean` 是同一
判据的两个入口 —— 前者给 CI/人手，后者保证「新加的护栏会被自动收进测试」。

它自己也必须**能红**：`--selftest` 用临时目录造样本，证明
「坏护栏会被抓、好护栏会被放、缺自证的护栏会被抓、空目录会红、
**永不退出的护栏会被超时判红**、**门数少于下限会被判红**」。
一个只会在好天气下变绿的 runner，本身也是一道假门；
一条会**永远挂住**的链比一道闸门更糟 —— 所以每个子进程都带 `stdin=DEVNULL`
与墙钟超时（见 `_run` 的注释：这是 R62-R31e 修掉的一个真缺陷）。

用法：
    python tools/check_all.py                 # 跑 tools/ 下全部护栏
    python tools/check_all.py --tools-dir D   # 指定护栏目录（自证/CI 复用）
    python tools/check_all.py --selftest      # 自证：双向验证本 runner
    python tools/check_all.py --help          # 显示本帮助（立即返回，不跑护栏）

退出码：
    0  = 全部护栏通过（且各自自证通过）
    1  = 有护栏失败，或护栏缺自证（`SELFTEST COUNTS` 行缺失 / 格式非法）
    2  = 找不到护栏（--tools-dir 下没有 check_*.py → 缺输入，红）
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

# R33/C'9：**门数棘轮**。只断言 rc=0 是不够的 —— 一个护栏被误删（或改名、
# 或移动目录）之后，剩下的门依然全绿，rc 依然是 0，于是「门少了」这件事
# 静默通过。这里登记「本仓自带护栏的下界」，删掉任何一道都会立刻变红。
# 数字含义：截至 R44，tools/ 下有 10 道 check_*.py（不含本 runner）。
# R36 新增 check_baseline.py（C''7：把公平基线做成可重跑的门），故 8 → 9。
# R44 新增 check_ir_attribution.py（C'''1：把「解析不到的调用只有一个判定点、
# 且归因吃到的是它」钉成全仓集合判据），故 9 → 10。
# R47 新增 check_flow_diagrams.py（把 README 里嵌的图 ↔ flow/diagrams/ 的文件 ↔
# candidate*.json 的声明 ↔ 交互产物 ↔ FLOW_INDEX.json 索引 ↔ SVG 自身形态（尺寸/字体/语言）
# 六条来源钉成 D1–D12、
# 每对双向），故 10 → 11。
# 新增护栏时**必须**同步上调这个数字 —— 这正是棘轮的作用。
MIN_GUARDS = 11


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


def _guard_count_problem(n_found, minimum, is_own_dir):
    """R33/C'9 的判定抽成纯函数（好让自证能直接测它）。

    返回问题字符串，或 None 表示通过。
    `is_own_dir=False`（显式 --tools-dir 指向别处）时不施加下限 —— 那是复用场景。
    """
    if not is_own_dir:
        return None
    if n_found < minimum:
        return ("只找到 %d 道护栏，少于登记下限 %d —— 有护栏被删/改名/移走"
                "（rc 仍为 0 但门少了）" % (n_found, minimum))
    return None


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
        # 这里的 good 数的是**自证断言条数**（9 条），与 MIN_GUARDS（护栏道数）
        # 是两件事 —— 别把它们调成同一个变量。
        return 0 if (bad == 0 and good >= 9) else 1

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
    # R33/C'9：门数棘轮 —— 只有当跑的是本仓自己的 tools/ 时才要求下限。
    # 显式 --tools-dir 指向别处（自证/嵌入式复用）时不施加，否则会误伤。
    if os.path.abspath(tools_dir) == os.path.dirname(os.path.abspath(__file__)):
        prob = _guard_count_problem(len(guards), MIN_GUARDS, True)
        if prob:
            print("check_all: " + prob)
            return 1
    print("check_all: OK（%d 个护栏，全部通过且各自自证；门数下限 %d）"
          % (len(guards), MIN_GUARDS))
    return 0


def _selftest():
    """双向自证：既造坏样本（必须红），也造好样本（必须绿）。

    七项断言缺一不可：
      ① 坏护栏（rc=1）         -> runner 必须返回 1
      ② 好护栏（rc=0 且有自证） -> runner 必须返回 0
      ③ 缺自证的护栏           -> runner 必须返回 1（否则「无自证」会被静默放行）
      ④ 空目录                 -> runner 必须返回 2（缺输入 → 红）
      ⑤ **永不退出的护栏**     -> runner 必须在超时后返回 1（R62-R31e 新增：
         一条会挂死的链比一道闸门更糟 —— 旧实现没有 timeout，一个不退出
         的护栏会让 check_all 和 CI 永远等下去。这里用 3s 超时把它变成红。）
      ⑥ 门数棘轮（R33/C'9，R37 改成从 MIN_GUARDS 派生）-> 少于下限要红、
         达到下限放行、外部目录不施加下限
      ⑦ MIN_GUARDS 必须等于本目录真实护栏数（R37）—— 只测「函数在给定数字下
         对不对」不够，还要保证**那个数字本身**没被落下
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

        # ⑥ 门数棘轮（R33/C'9）：少于下限必须变红；达到/超过则放行。
        # 注意这是纯函数判定，不依赖真实目录 —— 否则自证会被「当前有几道门」绑死。
        # R37：样本里的数字改成**从 MIN_GUARDS 派生**，而不是写死 8 ——
        # 否则 MIN_GUARDS 调到 20 时，自证还在测 8，棘轮会悄悄失效。
        if _guard_count_problem(MIN_GUARDS - 1, MIN_GUARDS, True) is not None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 门数不足未被判红（C'9 棘轮失效）")
        if _guard_count_problem(MIN_GUARDS, MIN_GUARDS, True) is None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 门数达下限被误伤（C'9 误报）")
        if _guard_count_problem(1, MIN_GUARDS, False) is None:
            good += 1
        else:
            bad += 1
            print("  [selftest] 外部 --tools-dir 被误施加下限（C'9 过严）")

        # ⑦ MIN_GUARDS 必须等于**本目录真实的护栏数**（R37）。
        # 这是棘轮的另一半：只测「函数在给定数字下对不对」不够，
        # 还要保证**那个数字本身**没被落下 —— 加了一道门却忘了上调，
        # 棘轮就等于不存在，而 rc 依然是 0。
        _here = os.path.dirname(os.path.abspath(__file__))
        _me = os.path.basename(os.path.abspath(__file__))
        _real = len([f for f in os.listdir(_here)
                     if f.startswith("check_") and f.endswith(".py")
                     and f != _me])
        if MIN_GUARDS == _real:
            good += 1
        else:
            bad += 1
            print("  [selftest] MIN_GUARDS=%d 与本目录真实护栏数 %d 不一致 —— "
                  "加门/删门后必须同步这个数字" % (MIN_GUARDS, _real))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad, good


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
