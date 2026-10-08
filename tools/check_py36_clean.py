# -*- coding: utf-8 -*-
"""登记制护栏：本仓库**自己的源码**必须通过本仓库**自己的** Python 3.6.5 兼容门。

动因（R62-R31f，**真缺陷，且已在上一轮被提交**）：
本仓在 CONTRIBUTING.md 与 README 里都承诺「严格兼容 Python 3.6.5，CI 用
`--check-py36` 兜底」，但实测 `python matlabc.py . --check-py36 --max-warnings 0`
在 HEAD 上就是 **rc=1**：
  * `tools/check_patch_ops.py` 用了 `list[str]`（Python **3.9** 语法）；
  * `tools/check_all.py` / `check_doc_flags.py` / `check_operator_impl.py` /
    `check_patch_ops.py` / `check_subprocess_hygiene.py` 五个文件都写了
    `from __future__ import annotations`（Python **3.7** 语法）。
更糟的是：当时的检查器**规则表里没有 `__future__ annotations` 这一条**，
所以它报「通过」—— 承诺与门之间有一道谁都看不见的缝。

本护栏把「承诺」变成一道真的门，且**两向自证**：
  * 好样本（合法 3.6 代码）必须放行；
  * 坏样本（`list[int]` / `from __future__ import annotations` / walrus / match）
    必须抓得到，而**不是**靠人工记得。

一图看懂（承诺 — 门 — 现实 三者之间的那道缝）：

    文档承诺：CONTRIBUTING.md / README「严格兼容 Python 3.6.5」
                    │
                    ▼  谁来执行？
        ┌───────────────────────────────────────────────┐
        │ matlabc.py --check-py36  （本仓自带的语法门）   │
        └───────────────────────────────────────────────┘
                    │  但规则表里有条**看不见的缝**：
                    │  5 个 tools/*.py 写了 from __future__ import annotations
                    │  （3.7 语法），规则表里却**没有这一条** ⇒ 报「通过」
                    ▼
        ┌───────────────────────────────────────────────┐
        │ check_py36_clean.py（本护栏）：拿本仓源码，     │
        │ 去喂本仓自己的门，rc 必须为 0                  │
        └───────────────────────────────────────────────┘
                    │
                    ├─ plain 模式：扫全仓 .py，rc=0 才算过
                    └─ --selftest：6 个坏样本必须各被抓到 + 1 个好样本必须放行

  它为什么不是形式主义：这条缝**真的存在过且已被提交**（HEAD 上
  `--check-py36 --max-warnings 0` 就是 rc=1），而修法同时包括
  「补规则表」+「改掉 5 个文件」—— 只做一半，门依然是假门。

用法：
    python tools/check_py36_clean.py             # 0=干净 1=有违规 2=缺输入
    python tools/check_py36_clean.py --selftest  # 两向自证
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

# 单次扫描的墙钟上限（本仓全量 42 个文件实测约 2s）。
SCAN_TIMEOUT = 600.0

# 坏样本：每一条都必须被本仓的 --check-py36 抓到。
BAD_SAMPLES = (
    ("generic_subscript", "def f() -> list[str]:\n    return []\n"),
    ("future_annotations", "from __future__ import annotations\n\n\nx = 1\n"),
    ("walrus", "if (n := 10) > 5:\n    pass\n"),
    ("posonly", "def f(a, /, b):\n    return a\n"),
    ("dataclass", "from dataclasses import dataclass\n\n\nx = 1\n"),
    ("match_stmt", "match x:\n    case 1:\n        pass\n"),
)

# 好样本：完全合法的 3.6.5 代码，必须放行。
GOOD_SAMPLE = '''# -*- coding: utf-8 -*-
"""3.6.5 兼容示例。"""
import os
from typing import List


def f(a, b=1):
    items = []  # type: List[str]
    for i in range(b):
        items.append(os.sep + str(i))
    return items


class K(object):
    def __init__(self, v):
        self.v = v
'''


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_gate(py, analyzer, target, timeout=SCAN_TIMEOUT):
    """跑本仓的 3.6 兼容门，返回 (rc, 输出文本)。

    子进程**必须**切 stdin + 带超时：本仓 `matlabc_mcp.py` 之类的 stdio 组件会
    在继承来的、永不 EOF 的 stdin 上永久阻塞（R62-R31e 实测教训）。
    """
    try:
        p = subprocess.Popen([py, analyzer, target, "--check-py36",
                              "--max-warnings", "0"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
    except OSError as e:
        return None, "启动失败：%s" % e
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        return None, "超时 >%.0fs（按红处理）" % timeout
    return p.returncode, out.decode("utf-8", "replace")


def _selftest(py, analyzer):
    """两向自证：坏样本逐条必须红，好样本必须绿。"""
    bad = good = 0
    fails = []
    tmp = tempfile.mkdtemp(prefix="py36_selftest_")
    try:
        # 好样本
        d_good = os.path.join(tmp, "good")
        os.makedirs(d_good)
        with io.open(os.path.join(d_good, "ok.py"), "w", encoding="utf-8") as fh:
            fh.write(GOOD_SAMPLE)
        rc, out = _run_gate(py, analyzer, d_good)
        if rc == 0:
            good += 1
            print("  [正例] 合法 3.6 代码            -> 放行")
        else:
            fails.append("good-sample")
            print("  [正例] 合法 3.6 代码            -> 误伤！rc=%s\n%s"
                  % (rc, out[:400]))
        # 坏样本（逐条单独扫，确保每条规则本身是有效的）
        for tag, src in BAD_SAMPLES:
            d_bad = os.path.join(tmp, "bad_" + tag)
            os.makedirs(d_bad)
            with io.open(os.path.join(d_bad, "bad.py"), "w",
                         encoding="utf-8") as fh:
                fh.write(src)
            rc, out = _run_gate(py, analyzer, d_bad)
            if rc == 1:
                bad += 1
                print("  [反例] %-22s -> 抓到" % tag)
            else:
                fails.append(tag)
                print("  [反例] %-22s -> 未被抓到！rc=%s\n%s"
                      % (tag, rc, out[:400]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    if fails:
        print("SELFTEST FAILED: %s" % fails)
        return 1
    print("SELFTEST PASSED")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--python", default=None,
                    help="用于跑门禁的解释器（默认同 sys.executable）")
    args = ap.parse_args(argv)
    py = args.python or sys.executable

    root = repo_root()
    analyzer = os.path.join(root, "matlabc.py")
    if not os.path.exists(analyzer):
        print("check_py36_clean: 找不到 matlabc.py（缺输入 → 红）")
        return 2

    if args.selftest:
        return _selftest(py, analyzer)

    rc, out = _run_gate(py, analyzer, root)
    if rc is None:
        print("check_py36_clean: %s（缺输入 → 红）" % out)
        return 2
    # 从输出里抠出统计行，便于人读
    m = re.search(r"统计：文件 (\d+) \| 问题 (\d+)（error (\d+) / warning (\d+)）",
                  out)
    n_files = m.group(1) if m else "?"
    n_err = m.group(3) if m else "?"
    if rc != 0:
        print("check_py36_clean: %d 个 .py 文件中有 %s 处 3.7+ 语法（rc=%s）"
              % (int(n_files) if n_files.isdigit() else -1, n_err, rc))
        for line in out.splitlines():
            if "[ERROR]" in line or "[WARN" in line:
                print("  " + line.strip())
        print("  提示：本仓承诺严格兼容 Python 3.6.5，"
              "CONTRIBUTING.md「代码风格」一节有禁用清单。")
        return 1
    print("check_py36_clean: OK（本仓 %s 个 .py 文件全部通过 3.6.5 语法兼容门）"
          % n_files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
