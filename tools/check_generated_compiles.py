# -*- coding: utf-8 -*-
"""check_generated_compiles —— 生成的 C 必须能编译；丢弃调用不许退回 unmapped。

为什么单独成门：这两条判据此前只活在 pytest 里，而**发版脚本跑的是 GATES 元组
（check_* 清单），不跑 pytest** —— 等于从未参与发版把关。

判据（签名 GX1–GX2）：
    GX1  示例工程（numeric / proj / demo_port.m）转出的 C 通过 `-fsyntax-only`
    GX2  丢弃返回值的调用降成 `call:` 而不是 `unmapped:`（且整工程可编译）

用法：
    python tools/check_generated_compiles.py
    python tools/check_generated_compiles.py --selftest

退出码：
    0  = 两条判据全绿
    1  = 有不合规
    2  = 缺依赖（没有 C 编译器 / 没有 pytest）
"""
import argparse
import os
import shutil
import queue
import threading
import time
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROW_SIGNATURE = "GX1–GX2"

def _cc():
    return shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")


#: 判据前缀 ⇄ 用例文件（每条判据都要真的能把前缀**发出来**，见 H2b）
CHECKS = (
    ("GX1", os.path.join("tests", "test_generated_compiles.py"),
     "GX1 示例工程（numeric / proj / demo_port.m）转出的 C 编译不过"),
    ("GX2", (os.path.join("tests", "test_void_call.py"),
             os.path.join("tests", "test_multi_return.py"),
             os.path.join("tests", "test_nounshaped.py"),
             os.path.join("tests", "test_numeric_expected_guard.py"),
             os.path.join("tests", "test_op_error_paths.py"),
             os.path.join("tests", "test_plan_tracker.py"),
             # 工程级（P0）：3 函数互调 -> C 工程 -> gcc -> 运行数值
             os.path.join("tests", "test_project_level.py"),
             # P1：配置真的生效（build_flags/cflags_string/唯一 reader）
             os.path.join("tests", "test_config_effective.py"),
             # P2：预算在生成期算出来、落进 budget.json、超限即失败
             os.path.join("tests", "test_budget.py"),
             os.path.join("tests", "test_contract_stub.py"),
             # P3：配置 c.external_calls 决定工程外调用是否进契约块
             os.path.join("tests", "test_config_external_calls.py"),
             # P6：无 Octave 也成立的多路对账（位模式哈希 + 反推算子序列）
             os.path.join("tests", "test_four_way_no_octave.py"),
             # P4：每个模块给出"该配什么"，且采纳后复扫有变化
             os.path.join("tests", "test_config_suggest.py"),
             # 工程级端到端：多目录 + 两跳调用 -> C 工程 -> gcc -> 数值
             os.path.join("tests", "test_project_e2e.py"),
             # 规模判据：58 函数语料工程 -> C 工程 -> gcc -> 0 unimplemented
             os.path.join("tests", "test_project_corpus_e2e.py"),
             # VM 层：call/call2 链接（手写 MIR，不依赖编译器）
             os.path.join("tests", "test_vm_calls.py"),
             # 分析侧：analyzer 计数口径 / 缺目录抛错 / binfmt 符号冲突
             os.path.join("tests", "test_analysis_layer.py"),
             # 渲染层：零 JS / 跨进程确定性 / 截断不崩
             os.path.join("tests", "test_renderers.py"),
             # 元数交叉校验：生成器的 op 实参个数 vs C 原型形参个数
             os.path.join("tests", "test_op_arity.py"),
             os.path.join("tests", "test_binfmt_buildsys.py"),
             os.path.join("tests", "test_binfmt_resolve.py"),
             os.path.join("tests", "test_binfmt_missing_deps.py"),
             os.path.join("tests", "test_renderers_assets.py"),
             os.path.join("tests", "test_site_matching_entry.py"),
             os.path.join("tests", "test_concurrency_entry.py"),
             os.path.join("tests", "test_unified_graph_entry.py"),
             os.path.join("tests", "test_facts_entry.py"),
             os.path.join("tests", "test_callrel_entry.py"),
             os.path.join("tests", "test_binhops_entry.py"),
             os.path.join("tests", "test_entity_model_entry.py"),
             # 长任务门自身的单实例锁（R846）
             os.path.join("tests", "test_single_instance.py"),
             os.path.join("tests", "test_pyast_frontend_entry.py"),
             os.path.join("tests", "test_agent_loop_entry.py"),
             # 整体状态：每个阶段的"完成"必须有在跑的证据
             os.path.join("tests", "test_project_status.py"),
             os.path.join("tests", "test_rt_balance.py"),
             os.path.join("tests", "test_mir_semantics.py"),
             os.path.join("tests", "test_no_duplicate_decls.py"),
             os.path.join("tests", "test_project_map.py"),
             os.path.join("tests", "test_rs3_exclusion.py"),
             os.path.join("tests", "test_doc_samples.py"),
             os.path.join("tests", "test_static_pool.py"),
             os.path.join("tests", "test_project_build.py"),
             os.path.join("tests", "test_mm6_stack.py"),
             os.path.join("tests", "test_q15_ops.py"),
             os.path.join("tests", "test_hcat_empty.py"),
             os.path.join("tests", "test_report_player.py"),
             os.path.join("tests", "test_report_site.py"),
             os.path.join("tests", "test_report_status.py"),
             os.path.join("tests", "test_roundtrip.py"),
             os.path.join("tests", "test_roundtrip_cli.py"),
             os.path.join("tests", "test_block_balance.py"),
             os.path.join("tests", "test_check_command.py"),
             os.path.join("tests", "test_check_annotate.py"),
             os.path.join("tests", "test_struct_out.py"),
             os.path.join("tests", "test_hir_ops.py"),
             os.path.join("tests", "test_hir_parse.py"),
             os.path.join("tests", "test_vm_run.py"),
             os.path.join("tests", "test_backparse.py"),
             os.path.join("tests", "test_roundtrip_vm.py"),
             os.path.join("tests", "test_hir_links.py"),
             os.path.join("tests", "test_check_verdict.py"),
             os.path.join("tests", "test_hir_pipeline.py"),
             os.path.join("tests", "test_hir_emit.py"),
             os.path.join("tests", "test_hir_scalar_pos.py"),
             os.path.join("tests", "test_hir_srcline.py"),
             os.path.join("tests", "test_hir_parity.py"),
             os.path.join("tests", "test_hir_meta_lines.py"),
             os.path.join("tests", "test_check_diag_two_paths.py"),
             # 26 个判据（逐算子发射 / 动态临时量 / BOM），此前不在任何门里
             os.path.join("tests", "test_translate_port.py"),
             os.path.join("tests", "test_agent_loop.py"),
             os.path.join("tests", "test_analyzer_memory.py"),
             os.path.join("tests", "test_entity_contract.py"),
             os.path.join("tests", "test_feature_matrix.py"),
             os.path.join("tests", "test_mir_eval_break.py"),
             os.path.join("tests", "test_mir_eval_setidx.py"),
             os.path.join("tests", "test_mlc_lsp.py"),
             os.path.join("tests", "test_mlc_project.py"),
             os.path.join("tests", "test_multi_arg_driver.py"),
             os.path.join("tests", "test_no_shadowed_builtins.py"),
             os.path.join("tests", "test_op_indexing_unit.py"),
             os.path.join("tests", "test_runnable_report.py"),
             os.path.join("tests", "test_runtime_bounds.py"),
             os.path.join("tests", "test_vm_differential.py"),
             os.path.join("tests", "test_workflows_yaml.py"),
             os.path.join("tests", "test_trace_chain.py"),
             os.path.join("tests", "test_vm_ops.py"),
             os.path.join("tests", "test_numeric_truth.py"),
             os.path.join("tests", "test_three_links.py"),
             os.path.join("tests", "test_vsix_sourceless.py"),
             os.path.join("tests", "test_drop_sideeffect.py"),
             os.path.join("tests", "test_q15_end_to_end.py"),
             os.path.join("tests", "test_external_project_compiles.py"),
             os.path.join("tests", "test_fuzz_ops_smoke.py"),
             os.path.join("tests", "test_runnable_report_empty.py"),
             os.path.join("tests", "test_return_path_frees_temps.py")),
     "GX2 丢弃返回值的调用退回 unmapped，或多返回值算错/编译不过"),
)


#: **慢档**用例：跑 VM / 全语料编译 / 反推 / 端到端，合计约占 80% 用时。
#: 本地迭代默认跳过它们（约 40s 出结论），官方全检仍跑全部
#: （`check_all` 会设 `M2C_FULL_GATES=1`，或手工 `--full`）。
SLOW_PAT = ("test_vm_", "test_roundtrip_vm", "test_translate_port",
            "test_hir_links", "test_runtime_bounds", "test_multi_arg_driver",
            "test_three_links", "test_backparse")


def _is_slow(path):
    base = os.path.basename(path)
    return any(base.startswith(p) for p in SLOW_PAT)


def lock_path():
    """锁文件位置：**机器本地临时目录**（不进仓库、不跨用户共享）。"""
    import tempfile
    return os.path.join(tempfile.gettempdir(), "m2c-gx2.lock")


def pid_alive(pid):
    """进程是否还活着。**跨平台**：Windows 走 OpenProcess，其余走 `kill(pid, 0)`。"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True          # 存在但没权限发信号
    except OSError:
        return False
    return True


def read_lock(path=None):
    """读锁内容（坏锁当成没有）；返回 dict 或 None。"""
    import json
    p = path or lock_path()
    if not os.path.isfile(p):
        return None
    try:
        import io as _io
        return json.load(_io.open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return None


def acquire_lock(path=None, force=False):
    """尝试取锁，返回 `(ok, 原因)`。

    ## 为什么需要

    R845 实测：连续几轮我都以为 GX2 "跑得慢"，实际上是**上一轮的实例从未退出**，
    两个 6 分钟的任务在互相抢 CPU —— 越重试越慢，且永远不会自己变好。
    等待只能解决"算得慢"，解决不了"两个在抢"。

    ## 语义

    * 锁里的 pid **还活着**且不是自己 → 拒绝（并说出是谁、什么时候开始的）；
    * 锁里的 pid **已死**（上次被 kill / 崩溃）→ 直接接管，不要求手工删；
    * `force=True` → 无视占用强行接管（给"确认它卡死"的场景留出口）。
    """
    import json
    import time as _time
    p = path or lock_path()
    info = read_lock(p)
    if info and not force:
        other = info.get("pid")
        if other and int(other) != os.getpid() and pid_alive(other):
            return False, ("已有实例在跑（pid %s，开始于 %s）"
                           % (other, info.get("ts", "?")))
    try:
        import io as _io
        _io.open(p, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"pid": os.getpid(),
                        "ts": _time.strftime("%Y-%m-%d %H:%M:%S")}))
    except OSError:
        return True, ""          # 写不了锁不该挡住检查本身
    return True, ""


def release_lock(path=None):
    """释放锁（pid 不是自己就不动 —— 避免误删别人的锁）。"""
    p = path or lock_path()
    info = read_lock(p)
    if info and int(info.get("pid") or 0) not in (0, os.getpid()):
        return
    try:
        os.remove(p)
    except OSError:
        pass


def _run_all(full=True):
    """跑用例文件；返回 (ok, tail, out)。`full=False` 时跳过慢档。"""
    files = []
    for _, f, _ in CHECKS:
        files.extend(f if isinstance(f, (list, tuple)) else [f])
    if not full:
        kept = [f for f in files if not _is_slow(f)]
        skipped = len(files) - len(kept)
        print("  [快档] 跳过 %d 个慢用例文件（加 --full 或设 M2C_FULL_GATES=1 跑全量）"
              % skipped)
        files = kept
    cmd = [sys.executable, "-m", "pytest"] + list(files) + [
        "-q", "--tb=no", "-rf", "-p", "no:cacheprovider"]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    # **流式读取**（R825）：`subprocess.run(capture_output)` 会把 pytest 的输出
    # 全缓冲到进程结束才吐 —— 于是外部看到的是"6 分钟 0 字节"，无法判断
    # 是在跑、卡住、还是已经死了（实测连续三轮因此拿不到结论）。
    # 改成 Popen 逐行读、逐行打印（同时累积全文供判定），进度从此可见。
    print("  [pytest] %d 个用例文件，开始…" % len(files), flush=True)
    chunks = []
    p = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         env=env)
    # **看门狗**：`readline` 自己**没有超时** —— 子进程若静默挂住，逐行读会
    # 永远等下去。所以把读取放到后台线程、主线程按 deadline 取队列：
    # 到点就 kill 并报错。这不是"登记一下风险"，是把它真的兜住。
    deadline = time.time() + 900
    q = queue.Queue()

    def _pump():
        for raw in iter(p.stdout.readline, b""):
            q.put(raw)
        q.put(None)                     # EOF 哨兵

    t = threading.Thread(target=_pump, daemon=True)
    t.start()
    timed_out = False
    while True:
        left = deadline - time.time()
        if left <= 0:
            timed_out = True
            p.kill()
            break
        try:
            raw = q.get(timeout=min(left, 5))
        except queue.Empty:
            if p.poll() is not None and not t.is_alive():
                break
            continue
        if raw is None:
            break
        line = raw.decode("utf-8", "replace").rstrip()
        chunks.append(line)
        if line.strip():
            print("  | " + line[:160], flush=True)
    p.stdout.close()
    try:
        p.wait(timeout=30)
    except subprocess.TimeoutExpired:
        p.kill()
        timed_out = True
    if timed_out:
        chunks.append("**[超时] 900 秒未跑完，已 kill**")
    out = "\n".join(chunks)
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    tail = lines[-1] if lines else ""
    return p.returncode == 0, tail, out


def _attribute(out):
    """从 `FAILED tests/x.py::test_y` 行归因到判据前缀。"""
    probs = []
    hit_files = {}
    for ln in out.splitlines():
        if not ln.startswith("FAILED "):
            continue
        path = ln[7:].split("::")[0].strip().replace("/", os.sep)
        hit_files[path] = hit_files.get(path, 0) + 1
    for prefix, f, why in CHECKS:
        files = f if isinstance(f, (list, tuple)) else [f]
        n = sum(hit_files.get(x, 0) for x in files)
        if n:
            probs.append("%s —— %s（%d 个用例失败）" % (why, "见下", n))
    if not probs:
        # 收集期就炸了（不是某个用例失败）：归到第一条判据
        probs.append("%s —— 用例收集/启动失败，见上方输出" % CHECKS[0][2])
    return probs


def selftest():
    bad = good = 0

    def chk(cond, name, detail=""):
        nonlocal bad, good
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %-42s %s" % (name, detail))
        return bool(cond)

    _files = []
    for _, f, _ in CHECKS:
        _files.extend(f if isinstance(f, (list, tuple)) else [f])
    chk(len(_files) >= 3, "至少覆盖 3 个用例文件", len(_files))
    chk(all(os.path.isfile(os.path.join(ROOT, f)) for f in _files),
        "用例文件都存在")
    chk(isinstance(ROW_SIGNATURE, str) and "–" in ROW_SIGNATURE, "签名形如 X1–X2")
    chk([c[0] for c in CHECKS] == ["GX1", "GX2"], "GX1/GX2 都有对应用例")
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return bad, good


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", action="store_true")
    # 默认**完整**（官方口径）；本地想快就 `--fast`，或显式 `--full`。
    # `check_all` 会设 M2C_FULL_GATES=1，保证官方跑的是全量。
    ap.add_argument("--fast", action="store_true", help="跳过慢档用例（本地迭代用）")
    ap.add_argument("--full", action="store_true", help="跑全部用例（默认）")
    ap.add_argument("--force", action="store_true",
                    help="无视已有实例强行启动（仅用于确认旧实例已卡死）")
    args = ap.parse_args(argv)
    full = not args.fast or args.full
    if os.environ.get("M2C_FULL_GATES") == "1":
        full = True

    if args.help:
        print(__doc__)
        return 0
    if args.selftest:
        bad, _ = selftest()
        return 0 if bad == 0 else 1

    if not _cc():
        print("check_generated_compiles: 缺 C 编译器（GX1 无法执行）")
        return 2
    try:
        import pytest  # noqa: F401
    except ImportError:
        print("check_generated_compiles: 缺 pytest（GX1/GX2 无法执行）")
        return 2

    # **单实例**：两个实例并行只会互相拖慢，而且看起来都像"跑不完"（R845 实测）。
    _ok, _why = acquire_lock(force=args.force)
    if not _ok:
        print("check_generated_compiles: 拒绝启动 —— %s" % _why)
        print("  同一时刻只允许一个实例；确认旧实例已卡死时可用 --force。")
        return 3
    try:
        return _main_body(full)
    finally:
        release_lock()


def _main_body(full):
    """真正的执行体（锁由 `main` 负责获取/释放）。"""
    ok, tail, out = _run_all(full=full)
    probs = [] if ok else _attribute(out)
    for p in probs:
        print("  - " + p)
    if probs:
        print(out[-1200:])
        print("check_generated_compiles: %d 项不合规（%s）"
              % (len(probs), ROW_SIGNATURE))
        return 1
    print("check_generated_compiles: OK（%s 全绿：编译判据 + 丢弃调用判据）"
          % ROW_SIGNATURE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
