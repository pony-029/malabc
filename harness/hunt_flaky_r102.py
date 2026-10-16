# -*- coding: utf-8 -*-
"""R102b：受控的 flaky 追捕装置（仓外，不动仓库）。

背景（两次实测、同一棵已提交的树 `e139daf`）：

    run1  `(0, 534, 4)`
    run3  `(2, 532, 4)`

总数**恒 534**、红数不同 ⇒ 至少两支用例非确定。要裁定「量具错还是对象错」，
第一步必须**拿到名字**（run4 的全量跑在拿）；第二步是把候选逐条**重复跑**，
看它是否真的抖。

本装置做第二件事，并且可以**施加受控负载**（`--load N`）——
用来**检验**「宿主负载把墙钟阈值顶爆」这个假设，而不是把它当成结论。

纪律：
  * 空集先断言非空：pytest 收集不到用例时 rc=4，**必须当错误**，
    不许把「一条都没跑」读成「全过」（R99 ④）。
  * 每个 nodeid 先断言**它真的存在于测试文件里**（拼错 = 假绿）。
  * 报告里同时给 rc / 耗时 / 首条 FAILED，缺一不可（R98 ⑮）。
"""
from __future__ import print_function

import io
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = r"C:\Program Files\Python310\python.exe"
TESTFILE = os.path.join(REPO, "tests", "test_matlabc.py")

# 候选：全部是「墙钟阈值」或「跨进程确定性」家族。
CANDIDATES = [
    # 墙钟阈值家族（绝对秒数）
    ("test_p77_incremental_perf_benchmark", "墙钟：首次全量 < 75ms/页（R102 已归一）"),
    ("test_c22_stress_test", "墙钟：30 文件 < 60s（绝对）"),
    ("test_c25_large_project", "墙钟：300 文件 < 180s（绝对）"),
    ("test_c28_uninit_performance", "墙钟：巨函数 5s（绝对，纯进程内）"),
    ("test_p210_benchmark", "墙钟：--benchmark-timeout 180（参数进工具）"),
    ("test_r31_doc_flags_guard_returns_promptly", "墙钟：护栏 < 60s（绝对）"),
    ("test_r31_stdio_server_help_needs_devnull_stdin", "墙钟：--help < 30s（绝对）"),
    # 跨进程确定性家族（对 PYTHONHASHSEED 敏感）
    ("test_p51_reproducible_outputs", "双 seed 逐字节全产物（P51）"),
    ("test_data_layer_reproducibility", "双 seed 数据层（R52）"),
    ("test_r30_reproducible_site_is_byte_identical_across_hashseed",
     "双 seed 站点逐字节（R30；R99 ⑲ 的 hash() 配色正主）"),
    ("test_r83_deterministic_double_run", "同 seed 双跑逐字节（R83）"),
    # ── R103 补入：由 `_r103/derive_candidates.py` 从测试文件**推导**出来的
    # （R102b 的 11 条是人工挑的，独立覆盖度自检发现它不完整）。
    # 分级尺度：高 = P1 绝对墙钟断言 或 P2 隐式超时 <= 30s。
    ("test_p150_watch_and_incrjson_and_taint_svg", "隐式超时 3s（watch 增量重建）"),
    ("test_p161_watch_gate", "隐式超时 5s（watch 门）"),
    ("test_run_timeout_kills_hung_process", "隐式超时 0.3s（**故意**要超时 ⇒ 预期稳定）"),
    ("test_r110_elapsed_ms_in_summary", "P1 但形态是 >= 0（良性，证据说话）"),
    ("test_r32_entry_help_returns_promptly_without_side_effects", "隐式超时 60s（中档）"),
    ("test_r33_guard_exit_code_contract_and_help_volume_ratchet", "隐式超时 60s（中档）"),
    # 排除：隐式超时 120s 的那批（test_r32_help_contract / test_r34 / test_r37 /
    # test_r89）—— 已实测的同类（r31 护栏 5.5s vs 60s）余量 >= 10x，120s 档 >= 20x，
    # 纳入只会稀释追捕的分辨力。**这是显式排除，不是遗漏。**
]


def read_text(path):
    with io.open(path, "rb") as fh:
        return fh.read().decode("utf-8", "replace")


def existing_defs():
    t = read_text(TESTFILE)
    return set(re.findall(r"^def (test_\w+)", t, re.M))


def burners(n):
    """起 n 个纯 CPU 占用进程（受控负载），返回 Popen 列表。"""
    procs = []
    for _ in range(n):
        procs.append(subprocess.Popen(
            [PY, "-c", "while True: pass"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL))
    return procs


def kill(procs):
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass
    for p in procs:
        try:
            p.wait(timeout=10)
        except Exception:
            pass


def run_one(nodeid):
    """跑一条用例，返回 (rc, 秒, 首条FAILED或'')。"""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    t0 = time.time()
    try:
        p = subprocess.Popen([PY, "-m", "pytest", nodeid, "-q", "-rf", "--tb=no"],
                             cwd=REPO, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as exc:
        return (None, 0.0, "起不来：%s" % exc)
    try:
        out, _ = p.communicate(timeout=1800)
    except subprocess.TimeoutExpired:
        p.kill()
        return (None, time.time() - t0, "超 1800s 未退出")
    dt = time.time() - t0
    text = out.decode("utf-8", "replace")
    first = ""
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("FAILED ") or s.startswith("ERROR "):
            first = s
            break
    return (p.returncode, dt, first)


def main(argv):
    repeat = 3
    load = 0
    only = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--repeat":
            repeat = int(argv[i + 1]); i += 2
        elif a == "--load":
            load = int(argv[i + 1]); i += 2
        elif a == "--only":
            only.append(argv[i + 1]); i += 2
        else:
            print("未知参数 %s" % a); return 2
    defs = existing_defs()
    cands = [c for c in CANDIDATES
             if not only or any(o in c[0] for o in only)]
    if not cands:
        print("[FAIL] 候选集为空 —— 先断言输入非空（R99 ④）")
        return 2
    missing = [n for n, _w in cands if n not in defs]
    if missing:
        print("[FAIL] 候选里有不存在的用例（拼错=假绿）：%s" % missing)
        return 2
    print("候选 %d 条 × 重复 %d 次；受控负载 %d 个纯 CPU 进程" % (len(cands), repeat, load))
    print("-" * 78)
    procs = burners(load) if load else []
    tally = []
    try:
        for name, why in cands:
            node = "tests/test_matlabc.py::%s" % name
            res = []
            for k in range(repeat):
                rc, dt, first = run_one(node)
                res.append((rc, dt, first))
                print("  %-46s #%d rc=%-5s %7.2fs %s"
                      % (name, k + 1, rc, dt, first[:40]))
            oks = sum(1 for r in res if r[0] == 0)
            bad = [r for r in res if r[0] != 0]
            if bad:
                tally.append((name, oks, repeat, bad[0]))
            print("  => %-44s %d/%d 绿  %s"
                  % (name, oks, repeat, "← 抖！" if bad and oks else ""))
    finally:
        kill(procs)
    print("-" * 78)
    if not tally:
        print("结论：候选全部 %d/%d 绿 ⇒ 本轮未复现抖动（不等于不存在，见报告）" % (repeat, repeat))
    else:
        print("结论：%d 条候选出现过红：" % len(tally))
        for name, oks, n, first in tally:
            print("  - %s  %d/%d 绿；首条红：%s" % (name, oks, n, first[:90]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
