# -*- coding: utf-8 -*-
"""发布一条命令走完：版本号 → 打包 → 版本表 → 关键门。

为什么需要它
============

一次发布原本是五步手工：`bump_version --apply` → `build_vsix` → `make_release`
→ 安装 → 提交。**手工会漏**：上一轮我就漏了 install，包做好了却没装上，
直到最后一刻才发现。

这个工具把顺序固定下来，并在**任一步失败时停下**（不继续往下做半成品）。

用法：
    python tools/release.py                 # 干跑：只打印将要做什么
    python tools/release.py --apply         # 真的做：版本号 + 打包 + 版本表
    python tools/release.py --apply --install   # 顺带装到本机 VS Code
    python tools/release.py --apply --commit    # 顺带 git commit（不 push）
    python tools/release.py --apply --commit --push

退出码：
    0  = 全部成功（或干跑）
    1  = 某一步失败（已停在失败处）
    2  = 环境问题（git / code 命令不可用）
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 发布前必须绿的门（快、且都在几秒内）。`check_all` 太慢，留给 CI / 手工。
#: 单道门超过这个耗时就在发布日志里提醒（不判负）。
SLOW_MS = 5000

GATES = ("check_version_scheme", "check_eol_convention", "check_readme_parity",
         "check_py36_clean", "check_tool_discoverability", "check_help_contract",
         "check_js_balance", "check_tour", "check_subprocess_hygiene",
         "check_portability", "check_lsp_doc_parity",
         # 图上缺字形（方块）已经出现过三次，靠肉眼看截图不可靠
         "check_figure_glyphs",
         # 一道门写了却不进发版清单，等于只给自己看的笔记
         "check_release_gates",
         # 越界的符号行号会让大纲永远转圈
         "check_symbol_ranges",
         # 工具的自证需要有人执行，否则等于没写
         "check_tool_selftests",
         # 移植链路（MIR → C → 编译 → 跑数）是最活跃的子系统，
         # 只放在 CI 里跑的话，改它的人跑一次发版会看到"假全绿"
         "check_translate_port")


#: 明知且合理的慢门（值 = 理由）。有了它，⚠ 才只对"不该慢"的门亮 ——
#: 一个天天亮的警告，很快就没人看了。
SLOW_OK = {
    "check_translate_port": "要真编译并运行生成的 C 工程，6s 属于正常",
}


def run(cmd, cwd=ROOT, timeout=900):
    """跑一条命令，stdout/stderr 合并返回 (rc, 最后若干行)。"""
    try:
        p = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
    except OSError as exc:
        return 2, [u"无法启动：%r" % (exc,)]
    except subprocess.TimeoutExpired:
        return 1, [u"超时（%ds）" % timeout]
    text = p.stdout.decode("utf-8", "replace")
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    return p.returncode, lines[-4:]


def _children_cpu():
    """所有子进程累计 CPU 秒数（不含墙钟里的等待）。

    `resource` 只在 POSIX 有；Windows 上用 `os.times()` 的 children_* 兜底 ——
    这正是"并行省的是等待还是计算"要看的那两个数。
    """
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_CHILDREN)
        return r.ru_utime + r.ru_stime
    except (ImportError, AttributeError):
        pass
    try:
        t = os.times()
        return t.children_user + t.children_system
    except (AttributeError, OSError):
        return None


def show_trend():
    """打印各门最近若干次的中位/最大耗时 —— 只看总时长看不出是谁在变慢。"""
    path = os.path.join(ROOT, "releases", "gates-history.jsonl")
    try:
        rows = [json.loads(x) for x in
                io.open(path, encoding="utf-8").read().splitlines() if x.strip()]
    except (IOError, OSError, ValueError):
        print("还没有 releases/gates-history.jsonl（发一次版才会有）")
        return 1
    rows = rows[-20:]
    if not rows:
        print("历史为空")
        return 1
    per = {}
    for r in rows:
        for g, ms in (r.get("gates") or {}).items():
            if isinstance(ms, int):
                per.setdefault(g, []).append(ms)
    print("%-30s %6s %8s %8s %8s" % ("门", "次数", "中位ms", "最大ms", "最近ms"))
    for g in GATES:
        vals = per.get(g) or []
        if not vals:
            print("%-30s %6d %8s %8s %8s" % (g, 0, "-", "-", "-"))
            continue
        srt = sorted(vals)
        print("%-30s %6d %8d %8d %8d"
              % (g, len(vals), srt[len(srt) // 2], srt[-1], vals[-1]))
    tot = [r.get("total_ms") for r in rows if r.get("total_ms")]
    if tot:
        print("\n总时长：最近 %d 次 %s 秒"
              % (len(tot), " → ".join("%.1f" % (v / 1000.0) for v in tot[-6:])))
    hits = [r.get("hits") for r in rows if r.get("hits") is not None]
    if hits:
        print("增量命中：最近 %d 次 %s 道"
              % (len(hits), " → ".join(str(v) for v in hits[-6:])))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--apply", action="store_true", help="真的执行（默认只干跑）")
    ap.add_argument("--trend", action="store_true",
                    help="只看各门的历史耗时，不发版")
    ap.add_argument("--jobs", type=int, default=0,
                    help="并行的门数（0 = 默认 4）")
    ap.add_argument("--install", action="store_true", help="装到本机 VS Code")
    ap.add_argument("--commit", action="store_true", help="git add + commit")
    ap.add_argument("--push", action="store_true", help="git push（需要 --commit）")
    ap.add_argument("--message", default="", help="提交信息文件路径")
    ns = ap.parse_args(argv)

    py = sys.executable
    if getattr(ns, "trend", False):
        return show_trend()

    steps = [
        ("版本号 +1", [py, "tools/bump_version.py", "--apply"], True),
        ("打包 vsix", [py, "tools/build_vsix.py"], True),
        ("重建版本表", [py, "tools/make_release.py"], True),
    ]
    for name, cmd, _ in steps:
        print("[%s] %s" % ("RUN " if ns.apply else "DRY ", name))
    if not ns.apply:
        print("")
        print("干跑结束。真的发布加 --apply（可再加 --install / --commit / --push）。")
        return 0

    for name, cmd, _ in steps:
        rc, tail = run(cmd)
        if rc != 0:
            print("  [FAIL] %s" % name)
            for ln in tail:
                print("         | " + ln[:110])
            return 1
        print("  [OK  ] %s ｜ %s" % (name, tail[-1][:80] if tail else ""))

    # 版本号是发布的地基：它错，后面全错，所以先验
    bad = 0
    # **记录每道门最后一次真跑的时间**：一道门"存在但半年没跑"和"不存在"
    # 在效果上几乎一样，而现在没有任何地方能看出这一点。
    stamps = {}
    _stamp_path = os.path.join(ROOT, "releases", "gates-last-run.json")
    try:
        if os.path.isfile(_stamp_path):
            stamps = json.loads(io.open(_stamp_path, encoding="utf-8").read())
    except (IOError, OSError, ValueError):
        stamps = {}
    # **门之间互不依赖**，串行跑纯属浪费：15 道门里最慢的一道 4s，
    # 串行总时长就是它们的和。并行跑把这段压到"最慢那道 + 一点"。
    # 输出仍按 GATES 顺序打，日志读起来与串行一致。
    # **CPU 时间与墙钟是两件事**：并行把墙钟压下去，但 CPU 总量不变。
    # 两个数一起看，才知道"省的是等待"还是"省的是计算"。
    # **发版是快筛，CI 是全量**：真编译/真运行的门（如 check_translate_port）
    # 在发版时只做结构检查，CI 那边不设这个变量、仍然跑全量。
    # 这样既不牺牲发版速度，也不会出现"发版绿了但没验"的假象 —— 门会打印"未跑（快检）"。
    os.environ["MATLABC_GATE_FAST"] = "1"
    _cpu0 = _children_cpu()
    t_all = time.time()
    results = {}

    def _one(g):
        t0 = time.time()
        rc, tail = run([py, os.path.join("tools", g + ".py")])
        return g, rc, tail, int((time.time() - t0) * 1000)

    # 默认按机器来：写死 4 在强机上浪费、在弱机上过载。
    try:
        _cpu = len(os.sched_getaffinity(0))       # Linux 上更准
    except (AttributeError, OSError):
        _cpu = os.cpu_count() or 4
    _want = int(getattr(ns, "jobs", 0) or 0) or max(1, min(_cpu - 1, 8))
    workers = max(1, min(_want, len(GATES)))
    if workers == 1:
        for g in GATES:
            for item in [_one(g)]:
                results[item[0]] = item
                print("  [%s] %s ｜ %s" % ("OK  " if item[1] == 0 else "FAIL",
                                          g, (item[2][-1] if item[2] else "")[:70]))
    else:
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_one, g) for g in GATES]
            for fut in futs:
                g, rc, tail, ms = fut.result()
                results[g] = (g, rc, tail, ms)

    for g in GATES:
        g, rc, tail, ms = results[g]
        stamps[g] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "ms": ms,
                     "rc": rc}
        if rc != 0:
            bad += 1
            # **每行都带门名**：并行时多道门同时失败，读者要靠前缀分辨
            # 哪一行属于哪道门（串行时代靠"紧接着"就能判断，并行不行）。
            print("  [FAIL] %s ｜ %s" % (g, (tail[-1] if tail else "")[:90]))
            for ln in (tail or [])[-4:-1]:
                print("         %s | %s" % (g, ln[:100]))
    total_ms = int((time.time() - t_all) * 1000)
    cpu_note = u""
    # **并行收益**用「各门累计 / 墙钟」度量：这个在 Windows 也算得出来。
    # （`os.times()` 在 Windows 上不给子进程时间，`resource` 只有 POSIX —— 
    #  所以 CPU 只在能拿到时附带，不拿它当"收益"的唯一证据。）
    _sum_ms = sum(stamps[g]["ms"] for g in GATES)
    if workers > 1 and total_ms > 0:
        cpu_note = u"，各门累计 %.1fs → 墙钟 %.1fs（%.1f× 并行收益）" % (
            _sum_ms / 1000.0, total_ms / 1000.0,
            _sum_ms / float(total_ms))
    _cpu1 = _children_cpu()
    if _cpu0 is not None and _cpu1 is not None and (_cpu1 - _cpu0) > 0:
        cpu_note += u"，CPU %.1fs" % (_cpu1 - _cpu0)
    try:
        io.open(_stamp_path, "w", encoding="utf-8", newline="").write(
            json.dumps(stamps, ensure_ascii=False, indent=1) + u"\n")
    except (IOError, OSError):
        pass
    # 增量命中的门先数出来：历史行与汇总行都要用（顺序错了会 UnboundLocalError）。
    _hits = 0
    for g in GATES:
        _tail = results[g][2] or []
        if any(u"增量命中" in ln for ln in _tail):
            _hits += 1

    # **趋势要留**：单次耗时说明不了退化，只有和"它自己以前"比才行。
    _hist = os.path.join(ROOT, "releases", "gates-history.jsonl")
    try:
        line = json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "total_ms": total_ms,
                           "hits": _hits,
                           "gates": dict((g, stamps[g]["ms"]) for g in GATES)},
                          ensure_ascii=False)
        old_hist = []
        if os.path.isfile(_hist):
            old_hist = [x for x in io.open(_hist, encoding="utf-8")
                        .read().splitlines() if x.strip()]
        old_hist.append(line)
        io.open(_hist, "w", encoding="utf-8", newline="").write(
            u"\n".join(old_hist[-200:]) + u"\n")     # 只留最近 200 次
    except (IOError, OSError):
        pass
    # 有耗时数据就该看一眼：最慢的那几道决定了一次发布要等多久。
    _slow = sorted([(v.get("ms") or 0, k) for k, v in stamps.items()
                    if k in GATES], reverse=True)[:3]
    if _slow:
        # **并行下这个读数含排队**：8 路一起跑时，单门墙钟会被 CPU 争抢拉长
        # （实测同一道门串行 4.1s、8 路并行 5.6s）。所以并行时只作参考，
        # 不拿它触发"值得优化"的结论 —— 否则天天误报，警告很快就没人看。
        if workers > 1:
            print("  （最慢）" + " ｜ ".join(
                "%s %.1fs" % (k, ms / 1000.0) for ms, k in _slow) +
                u"（%d 路并行，含排队）" % workers)
        else:
            _flag = (u" ⚠" if (_slow[0][0] > SLOW_MS
                     and _slow[0][1] not in SLOW_OK) else u"")
            print("  （最慢）" + " ｜ ".join(
                "%s %.1fs" % (k, ms / 1000.0) for ms, k in _slow) + _flag)
            if _slow[0][0] > SLOW_MS and _slow[0][1] not in SLOW_OK:
                print("         超过 %dms 的门会让每次发布都多等这么久，值得优化"
                      % SLOW_MS)
            elif _slow[0][1] in SLOW_OK and _slow[0][0] > SLOW_MS:
                print("         （已知慢门：%s）" % SLOW_OK[_slow[0][1]])
    # 总时长走势：单次数字看不出"是不是越来越慢"，三个数就够了。
    try:
        _hrows = [json.loads(x) for x in
                  io.open(os.path.join(ROOT, "releases",
                                       "gates-history.jsonl"),
                          encoding="utf-8").read().splitlines() if x.strip()]
    except (IOError, OSError, ValueError):
        _hrows = []
    _tot = [r.get("total_ms") for r in _hrows[-4:] if r.get("total_ms")]
    if len(_tot) >= 2:
        print("  （趋势）最近 %d 次总时长: %s 秒"
              % (len(_tot), " → ".join("%.1f" % (v / 1000.0) for v in _tot)))
    # （_hits 已在写历史前算好）
    print("  [%s] %d 道关键门%s（%.1fs，%d 路并行%s%s）"
          % ("OK  " if not bad else "FAIL", len(GATES),
             "" if not bad else "，失败 %d" % bad,
             total_ms / 1000.0, workers,
             u"，%d 道增量命中" % _hits if _hits else u"", cpu_note))
    if bad:
        print("门没过就不该发版 —— 停在这里，包已经打好但先别推。")
        return 1

    if ns.install:
        vsix = [f for f in os.listdir(os.path.join(ROOT, "releases", "vsix"))
                if f.endswith(".vsix")]
        if not vsix:
            print("  [FAIL] releases/vsix 里没有包")
            return 1
        path = os.path.join(ROOT, "releases", "vsix", vsix[0])
        code = "code.cmd" if os.name == "nt" else "code"
        rc, tail = run([code, "--install-extension", path, "--force"])
        print("  [%s] 安装 %s" % ("OK  " if rc == 0 else "FAIL", vsix[0]))
        if rc != 0:
            for ln in tail:
                print("         | " + ln[:110])
            return 1

    if ns.commit:
        run(["git", "add", "-A"])
        if ns.message and os.path.isfile(ns.message):
            rc, tail = run(["git", "commit", "-F", ns.message])
        else:
            rc, tail = run(["git", "commit", "-m", "release"])
        print("  [%s] 提交" % ("OK  " if rc == 0 else "FAIL/无改动"))
        if ns.push:
            if not ns.commit:
                print("  --push 需要同时给 --commit")
                return 2
            env = dict(os.environ, GIT_SSH_COMMAND=(
                "ssh -o BatchMode=yes -o ConnectTimeout=20"))
            try:
                p = subprocess.run(["git", "push", "origin", "main"], cwd=ROOT,
                                   stdin=subprocess.DEVNULL, env=env,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=300)
                ok = p.returncode == 0
            except Exception:
                ok = False
            print("  [%s] 推送" % ("OK  " if ok else "FAIL"))
            if not ok:
                return 1

    print("")
    print("发布完成。别忘了：重载窗口 -> 试一遍「打开使用说明」与「打开使用导览」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
