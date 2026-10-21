# -*- coding: utf-8 -*-
"""安装仓库内 Git 钩子（`core.hooksPath=.githooks`）。

为什么需要它：
    `.githooks/pre-commit` 只有被 Git 找到才会运行；而 `core.hooksPath`
    是**本地**仓库配置，不能随代码提交。本工具把“怎么接上”变成一条命令，
    并给出 `--check` 让 CI/新人能判断自己有没有接上。

注意：本工具只有在**你显式运行**时才会改 `core.hooksPath`；它不会在
`check_all` 或 CI 里偷偷改你的 Git 配置。

用法：
    python tools/install_git_hooks.py          # 接上
    python tools/install_git_hooks.py --check  # 只看有没有接上
    python tools/install_git_hooks.py --uninstall
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOOK = os.path.join(ROOT, ".githooks", "pre-commit")


def _git(args):
    r = subprocess.run(["git"] + args, cwd=ROOT, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=15)
    return r.returncode, (r.stdout or b"").decode("utf-8", "replace").strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="安装 .githooks/pre-commit")
    ap.add_argument("--check", action="store_true", help="只检查是否已接上")
    ap.add_argument("--uninstall", action="store_true", help="取消 hooksPath")
    args = ap.parse_args(argv)
    rc, cur = _git(["config", "--get", "core.hooksPath"])
    if args.check:
        if rc == 0 and cur == ".githooks":
            print("install_git_hooks: OK（core.hooksPath=.githooks）")
            return 0
        print("install_git_hooks: 未接上（当前 core.hooksPath=%r）" % cur)
        print("运行：python tools/install_git_hooks.py")
        return 1
    if args.uninstall:
        _git(["config", "--unset", "core.hooksPath"])
        print("已取消 core.hooksPath")
        return 0
    if not os.path.isfile(HOOK):
        print("缺钩子文件：%s" % HOOK)
        return 2
    rc, out = _git(["config", "core.hooksPath", ".githooks"])
    if rc != 0:
        print("设置失败：%s" % out)
        return 1
    print("已接上 core.hooksPath=.githooks；下次 commit 会跑架构快跑门。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
