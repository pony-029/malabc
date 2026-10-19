# -*- coding: utf-8 -*-
"""本地 CI：在**干净克隆**里跑与流水线相同的几层检查。

为什么需要它
============

`.github/workflows/ci.yml` 跑在云端，反馈链路是「推 → 等 → 看日志」。
而本项目有一条更隐蔽的风险：**本地工作副本不等于 CI 的环境**——
工作副本里有未入库的产物、历史缓存、临时改动。

所以这个工具做一件事：把仓库**克隆到一个独立目录**（默认 `E:\\ci\\matlabc`），
在那个副本里跑同一组命令。**它测的是「已提交的代码能不能从零跑起来」。**

⚠ 一条必须记住的语义：**沙箱只包含已提交的内容**。
你改了但没提交的东西，它看不见 —— 那不是缺陷，正是 CI 的定义。

用法：
    python tools/ci_local.py                      # 同步 + 跑全部
    python tools/ci_local.py --no-sync            # 不重新同步，只跑
    python tools/ci_local.py --only gates,judge   # 只跑某几层
    python tools/ci_local.py --list               # 看有哪些层

退出码：
    0  = 全部通过
    1  = 有层失败
    2  = 环境问题（git 不可用 / 同步失败）
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 默认沙箱位置。用户指定在 E 盘；其他平台落到家目录。
DEFAULT_WORK = (r"E:\ci\matlabc" if os.name == "nt"
                else os.path.expanduser("~/ci/matlabc"))

#: 层名 -> (命令, 说明)
LAYERS = [
    ("gates", [sys.executable, "tools/check_all.py", "--quiet"],
     u"33 道静态门（每道自带两向自证）"),
    ("suite", [sys.executable, "tests/test_matlabc.py"],
     u"核心回归套件"),
    ("judge", [sys.executable, "tools/lsp_selftest.py", "--all"],
     u"LSP / MCP 行为判据"),
    ("scenarios", [sys.executable, "tools/rsi_scenarios.py"],
     u"端到端场景（两个协议）"),
    ("mutate", [sys.executable, "tools/mutate_sample.py"],
     u"变异抽样（证明判据会红）"),
]


def _run(cmd, cwd, timeout=1800):
    """跑一条命令，返回 (rc, 最后几行)。**输出走临时文件**，不用管道排空。"""
    log = os.path.join(tempfile.gettempdir(),
                       "ci_local_%d.txt" % os.getpid())
    t0 = time.time()
    with io.open(log, "wb") as fh:
        try:
            rc = subprocess.call(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                                 stdout=fh, stderr=subprocess.STDOUT,
                                 timeout=timeout,
                                 env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        except subprocess.TimeoutExpired:
            rc = -9
        except OSError as exc:
            return 2, [u"无法启动：%r" % (exc,)], 0.0
    lines = []
    try:
        text = io.open(log, "r", encoding="utf-8", errors="replace").read()
        lines = [x.strip() for x in text.splitlines() if x.strip()]
    except Exception:
        pass
    finally:
        try:
            os.remove(log)
        except OSError:
            pass
    return rc, lines[-6:], time.time() - t0


def _git(args, cwd):
    try:
        p = subprocess.run(["git"] + args, cwd=cwd, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=600)
        return p.returncode, p.stdout.decode("utf-8", "replace")
    except Exception as exc:
        return 2, repr(exc)


def sync(work):
    """把工作副本克隆/更新到沙箱。返回 (ok, 说明)。"""
    if not os.path.isdir(os.path.join(work, ".git")):
        if os.path.isdir(work) and os.listdir(work):
            return False, u"%s 非空且不是 git 仓库 —— 请换目录或手工清理" % work
        parent = os.path.dirname(work)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        rc, out = _git(["clone", "--quiet", ROOT, work], ROOT)
        if rc != 0:
            return False, u"clone 失败：%s" % out.strip()[:160]
        return True, u"已从 %s 克隆到 %s" % (ROOT, work)

    rc, out = _git(["fetch", "--quiet", "origin"], work)
    if rc != 0:
        return False, u"fetch 失败：%s" % out.strip()[:160]
    # 沙箱是一次性副本：**硬重置**到远端分支，任何残留改动都丢掉。
    for br in ("origin/main", "origin/master"):
        rc, out = _git(["reset", "--hard", br], work)
        if rc == 0:
            return True, u"已重置到 %s" % br
    return False, u"reset 失败（没有 origin/main？）"


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--workdir", default=DEFAULT_WORK)
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    if args.help:
        sys.stdout.write(__doc__)
        return 0
    if args.list:
        for name, _, desc in LAYERS:
            print("%-10s %s" % (name, desc))
        return 0

    work = os.path.abspath(args.workdir)
    if not args.no_sync:
        ok, msg = sync(work)
        print("ci_local: " + msg)
        if not ok:
            return 2
    elif not os.path.isdir(os.path.join(work, ".git")):
        print("ci_local: --no-sync 但 %s 不是 git 仓库" % work)
        return 2

    rc0, head, _ = _git(["log", "-1", "--oneline"], work)
    print("ci_local: 沙箱 HEAD = %s" % (head.strip() if rc0 == 0 else "?"))
    print("")

    want = [s.strip() for s in args.only.split(",") if s.strip()]
    picked = [x for x in LAYERS if not want or x[0] in want]
    bad = 0
    for name, cmd, desc in picked:
        rc, tail, dt = _run(cmd, work)
        mark = "PASS" if rc == 0 else "FAIL"
        print("  [%s] %-10s %5.1fs  %s" % (mark, name, dt, desc))
        if rc != 0:
            bad += 1
            for ln in tail[-4:]:
                print("         | " + ln[:110])
    print("")
    print("ci_local: %d 层，失败 %d%s"
          % (len(picked), bad, "" if not bad else " —— 与云端会红的是同一处"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
