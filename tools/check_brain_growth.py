# -*- coding: utf-8 -*-
"""**大脑成长判据（BG1–BG5）**：让"记录"这件事不再依赖记性。

    python tools/check_brain_growth.py
    python tools/check_brain_growth.py --selftest

## 为什么需要这道门

`flow/failures.json` 是知识库，`brain.py growth` 能追加快照 —— 但**没有任何东西
会要求你去追加**。这个项目里"可选调用"的机制实际使用率曾是 0（R935 已踩过：
留痕写在 CLI 里，而真正的调用走函数）。

所以把它变成门：**没记快照就红、条数倒退就红、快照与知识库不一致就红。**

| 判据 | 拦什么 |
|---|---|
| **BG1** 快照文件存在且非空 | 换机器/清目录后悄悄失效 |
| **BG2** 条数单调不减 | 知识库被误删/回滚而无人发现 |
| **BG3** 最新快照 == 当前条数 | 加了条目却没记快照（机制空转） |
| **BG4** 咨询次数 > 0 | 知识库建了但**没人读过**（= 墓志铭） |
| **BG5** 见证覆盖率 100% | 有登记但没有"会变红的见证" |

BG3 是最关键的一条：它把"我加了 3 条错"和"机制记录了这次成长"绑在一起 ——
只做前者会被它抓住。

退出码：
    0 = BG1–BG5 全部成立
    1 = 成长机制失效（没记快照 / 条数倒退 / 快照落后 / 从未咨询 / 见证缺失）
    2 = 缺输入（flow/failures.json 或 flow/brain-growth.jsonl 不存在）
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "flow", "failures.json")
GROWTH = os.path.join(ROOT, "flow", "brain-growth.jsonl")
USAGE = os.path.join(ROOT, "flow", "brain-usage.jsonl")

ROW_SIGNATURE = "BG1–BG6"


def _snaps(path=GROWTH):
    out = []
    if not os.path.isfile(path):
        return out
    for ln in io.open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def _registry(path=REG):
    if not os.path.isfile(path):
        return []
    try:
        return json.load(io.open(path, encoding="utf-8"))["entries"]
    except (ValueError, KeyError, TypeError):
        return []


def _rel(p):
    """相对路径，**跨盘符时退回原路径**。

    `os.path.relpath` 在 Windows 上当两个路径不在同一盘（自证用 C:\\… 临时目录，
    而仓库在 E:）会抛 ValueError: path is on mount 'C:', start on mount 'E:'。
    门不该因为"报告一行路径"而崩掉。
    """
    try:
        return os.path.relpath(p, ROOT)
    except ValueError:
        return p


def audit(reg=REG, growth=GROWTH, usage=USAGE, check_senses=True):
    """返回问题列表；空 = 通过。路径可注入，便于自证。"""
    problems = []
    entries = _registry(reg)
    snaps = _snaps(growth)

    # BG1
    if not snaps:
        problems.append("BG1 没有成长快照（%s）—— 大脑没有被记录过"
                        % _rel(growth))
    # BG2
    for i in range(1, len(snaps)):
        if snaps[i].get("total", 0) < snaps[i - 1].get("total", 0):
            problems.append("BG2 条数倒退：第 %d 次快照 %s -> 第 %d 次 %s"
                            % (i, snaps[i - 1].get("total"), i + 1,
                               snaps[i].get("total")))
            break
    # BG3
    if snaps and entries:
        last = snaps[-1].get("total")
        if last != len(entries):
            problems.append(
                "BG3 快照与知识库不一致：最新快照 %s 条，而 failures.json 有 %d 条"
                " —— 加了条目却没记快照（机制空转）" % (last, len(entries)))
    # BG4
    n_usage = 0
    if os.path.isfile(usage):
        n_usage = sum(1 for ln in io.open(usage, encoding="utf-8") if ln.strip())
    # ⚠ 不用海象运算符：本仓承诺 Python 3.6.5（check_py36_clean 会红）
    snap_usage = snaps[-1].get("usage") if snaps else 0
    if snap_usage and n_usage and n_usage < snap_usage:
        problems.append("BG4 咨询次数倒退：快照记 %d 次，实际 %d 条"
                        % (snap_usage, n_usage))
    if n_usage == 0:
        problems.append("BG4 大脑从未被咨询过（%s 为空）—— 知识库没人读等于墓志铭"
                        % _rel(usage))
    # BG5
    missing = [e.get("id") for e in entries
               if not (e.get("witness") or "").strip()
               or not os.path.exists(os.path.join(
                   ROOT, (e.get("witness") or "").strip()))]
    if missing:
        problems.append("BG5 %d 条没有成立的见证：%r" % (len(missing), missing[:4]))
    # BG6：**感知不许比事实旧**。知识库管"以前踩过什么"，感知管"现在什么状态"；
    # 读数文件改过却没重跑 `brain senses`，小脑就会拿旧感觉做判断。
    if check_senses:
        try:
            sys.path.insert(0, os.path.join(ROOT, "tools"))
            import brain as _b
            stale = _b.stale_senses()
        except Exception as e:                   # noqa: BLE001
            stale = ["感知模块不可用：%s" % e]
        if stale:
            problems.append("BG6 " + stale[0])
    return problems


def _selftest():
    """**双向自证**：好样本通过、坏样本必须红（只验前者等于没验）。"""
    import tempfile

    bad = good = 0
    d = tempfile.mkdtemp(prefix="bg-probe-")
    try:
        reg = os.path.join(d, "f.json")
        gro = os.path.join(d, "g.jsonl")
        use = os.path.join(d, "u.jsonl")

        def _entry(i):
            return {"id": "F%03d" % i, "title": "t", "symptom": "s",
                    "root_cause": "r", "rule": "u",
                    "witness": "tools/check_brain_growth.py",
                    "status": "fixed", "commit": "x"}

        def _setup(n, snaps, usage_lines=1):
            io.open(reg, "w", encoding="utf-8", newline="\n").write(
                json.dumps({"version": 1,
                            "entries": [_entry(i + 1) for i in range(n)]}))
            io.open(gro, "w", encoding="utf-8", newline="\n").write(
                "".join(json.dumps(s) + "\n" for s in snaps))
            io.open(use, "w", encoding="utf-8", newline="\n").write(
                "".join("{}\n" for _ in range(usage_lines)))

        # ① 干净：3 条、两次快照递增、咨询 2 次
        _setup(3, [{"total": 2, "usage": 1}, {"total": 3, "usage": 2}], 2)
        probs = audit(reg, gro, use, check_senses=False)
        if not probs:
            good += 1
        else:
            bad += 1
            print("  [selftest] 干净样本被误伤：%r" % probs[:2])

        # ② 快照与知识库不一致 → BG3 必红
        _setup(3, [{"total": 2, "usage": 2}], 2)
        if any("BG3" in p for p in audit(reg, gro, use, check_senses=False)):
            good += 1
        else:
            bad += 1
            print("  [selftest] 快照落后没红")

        # ③ 条数倒退 → BG2 必红
        _setup(3, [{"total": 5, "usage": 1}, {"total": 3, "usage": 2}], 2)
        if any("BG2" in p for p in audit(reg, gro, use, check_senses=False)):
            good += 1
        else:
            bad += 1
            print("  [selftest] 条数倒退没红")

        # ④ 从未咨询 → BG4 必红
        _setup(3, [{"total": 3, "usage": 0}], 0)
        if any("BG4" in p for p in audit(reg, gro, use, check_senses=False)):
            good += 1
        else:
            bad += 1
            print("  [selftest] 零咨询没红")
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    if "--selftest" in sys.argv:
        return _selftest()
    # 缺输入（知识库/快照文件都不在）→ 2；机制失效 → 1
    if not os.path.isfile(REG) and not os.path.isfile(GROWTH):
        print("check_brain_growth: 缺输入（%s 与 %s 都不存在）" % (REG, GROWTH))
        return 2
    problems = audit()
    if problems:
        for p in problems:
            print("- %s" % p)
        print("check_brain_growth: %d 处问题（%s）" % (len(problems), ROW_SIGNATURE))
        return 1
    s = _snaps()[-1]
    print("check_brain_growth: OK（%s 全绿：%d 条、见证 100%%、咨询 %d 次、"
          "快照 %d 次）" % (ROW_SIGNATURE, s.get("total", 0), s.get("usage", 0),
                          len(_snaps())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
