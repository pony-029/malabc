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
         "check_tool_selftests")


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


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--apply", action="store_true", help="真的执行（默认只干跑）")
    ap.add_argument("--jobs", type=int, default=0,
                    help="并行的门数（0 = 默认 4）")
    ap.add_argument("--install", action="store_true", help="装到本机 VS Code")
    ap.add_argument("--commit", action="store_true", help="git add + commit")
    ap.add_argument("--push", action="store_true", help="git push（需要 --commit）")
    ap.add_argument("--message", default="", help="提交信息文件路径")
    ns = ap.parse_args(argv)

    py = sys.executable
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
    t_all = time.time()
    results = {}

    def _one(g):
        t0 = time.time()
        rc, tail = run([py, os.path.join("tools", g + ".py")])
        return g, rc, tail, int((time.time() - t0) * 1000)

    workers = max(1, min(int(getattr(ns, "jobs", 0) or 0) or 4, len(GATES)))
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
            print("  [FAIL] %s ｜ %s" % (g, (tail[-1] if tail else "")[:90]))
    total_ms = int((time.time() - t_all) * 1000)
    try:
        io.open(_stamp_path, "w", encoding="utf-8", newline="").write(
            json.dumps(stamps, ensure_ascii=False, indent=1) + u"\n")
    except (IOError, OSError):
        pass
    # **趋势要留**：单次耗时说明不了退化，只有和"它自己以前"比才行。
    _hist = os.path.join(ROOT, "releases", "gates-history.jsonl")
    try:
        line = json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "total_ms": total_ms,
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
        _flag = u" ⚠" if _slow[0][0] > SLOW_MS else u""
        print("  （最慢）" + " ｜ ".join(
            "%s %.1fs" % (k, ms / 1000.0) for ms, k in _slow) + _flag)
        if _slow[0][0] > SLOW_MS:
            print("         超过 %dms 的门会让每次发布都多等这么久，值得优化"
                  % SLOW_MS)
    print("  [%s] %d 道关键门%s（%.1fs，%d 路并行）"
          % ("OK  " if not bad else "FAIL", len(GATES),
             "" if not bad else "，失败 %d" % bad,
             total_ms / 1000.0, workers))
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
