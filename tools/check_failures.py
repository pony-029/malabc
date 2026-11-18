# -*- coding: utf-8 -*-
"""**失败登记机制**的门：每条错误必须带"见证"，否则只算故事不算机制。

    python tools/check_failures.py

## 为什么要这道门

这个项目里我反复犯同一类错（新工具没进 README 犯了两次、
`%` 格式化修了三次、`unmatched/unresolved` 撞名……）。
写进笔记没有用 —— 因为**没有东西会去读它**。

所以做成登记表 `flow/failures.json`，并由这道门逐条校验：

| 判据 | 拦什么 |
|---|---|
| **F1** 必填字段齐 | `id / title / symptom / root_cause / rule / witness / status` |
| **F2** id 唯一且形如 `F###` | 复制粘贴时会重复 |
| **F3** witness 必须存在 | 指向一个真文件（判据/工具）。**没有见证的错误不会被任何人拦住** |
| **F4** `status=fixed` 必须带 commit | 否则"修过"是自称的 |
| **F5** status 只能是 fixed / open | 免得出现"大概修了"这种状态 |

## witness 的含义（重要）

不是"相关文件"，而是**下次再犯时会红的那个东西** ——
一道判据（`tests/test_*.py`）、一个门（`tools/check_*.py`）、
或生成该错误的工具本身（`tools/gen_scale_corpus.py`）。

如果某条错误找不到这样的见证，说明它的**防复发措施还没做** ——
那就该在 `status` 里写 `open`，而不是编一个文件名。
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "flow", "failures.json")

REQUIRED = ("id", "title", "symptom", "root_cause", "rule", "witness", "status")
ID_RE = re.compile(r"^F\d{3}$")
STATUS = ("fixed", "open")


def audit(path=REG):
    """返回问题列表；空 = 通过。"""
    problems = []
    if not os.path.isfile(path):
        return ["缺 %s（失败登记表）" % os.path.relpath(path, ROOT)]
    try:
        d = json.load(io.open(path, encoding="utf-8"))
    except ValueError as e:
        return ["登记表不是合法 JSON：%s" % e]

    entries = d.get("entries")
    if not isinstance(entries, list) or not entries:
        return ["entries 缺失或为空"]

    seen = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            problems.append("entries[%d] 不是对象" % i)
            continue
        tag = e.get("id") or "entries[%d]" % i
        # F1
        for k in REQUIRED:
            if not (e.get(k) or "").strip():
                problems.append("%s 缺字段 %s" % (tag, k))
        # F2
        if not ID_RE.match(str(e.get("id") or "")):
            problems.append("%s 的 id 不是 F### 形式" % tag)
        if tag in seen:
            problems.append("%s 重复（复制粘贴时最容易出）" % tag)
        seen.add(tag)
        # F5
        st = e.get("status")
        if st not in STATUS:
            problems.append("%s 的 status 不是 %r 之一：%r" % (tag, STATUS, st))
        # F4
        if st == "fixed" and not (e.get("commit") or "").strip():
            problems.append("%s 标了 fixed 却没有 commit（'修过'是自称的）" % tag)
        # F3
        w = (e.get("witness") or "").strip()
        if w and not os.path.exists(os.path.join(ROOT, w)):
            problems.append("%s 的 witness 不存在：%s（没有见证 = 没做防复发）"
                            % (tag, w))
    return problems


#: 质量门表里那一行的签名（`check_readme_parity` 的 P5 要求声明它，
#: 否则"文档里的那一行"没有可逐字核对的对手方）
ROW_SIGNATURE = "FR1–FR5"


def _selftest():
    """自证：**正向能过、反向能红** —— 只验"干净样本通过"不算自证，
    因为一个永远返回 OK 的门也能通过那一项。"""
    bad = good = 0
    d = tempfile.mkdtemp(prefix="fail-probe-")
    try:
        def _mk(name, obj):
            p = os.path.join(d, name + ".json")
            io.open(p, "w", encoding="utf-8", newline="\n").write(
                json.dumps(obj, ensure_ascii=False))
            return p

        base = {"version": 1, "entries": [{
            "id": "F001", "title": "t", "symptom": "s", "root_cause": "r",
            "rule": "u", "witness": "tools/check_failures.py",
            "status": "fixed", "commit": "abc"}]}

        # ① 干净样本必须通过
        if not audit(_mk("ok", base)):
            good += 1
        else:
            bad += 1
            print("  [selftest] 干净样本被误伤")

        # ② witness 不存在必须红
        b2 = json.loads(json.dumps(base))
        b2["entries"][0]["witness"] = "tools/nope_not_here.py"
        if any("witness" in p for p in audit(_mk("badwit", b2))):
            good += 1
        else:
            bad += 1
            print("  [selftest] witness 不存在没红")

        # ③ fixed 无 commit 必须红
        b3 = json.loads(json.dumps(base))
        b3["entries"][0]["commit"] = ""
        if any("commit" in p for p in audit(_mk("badcm", b3))):
            good += 1
        else:
            bad += 1
            print("  [selftest] fixed 无 commit 没红")

        # ④ 重复 id 必须红
        b4 = json.loads(json.dumps(base))
        b4["entries"].append(dict(base["entries"][0]))
        if any("重复" in p for p in audit(_mk("dup", b4))):
            good += 1
        else:
            bad += 1
            print("  [selftest] 重复 id 没红")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    if argv and "--selftest" in argv or "--selftest" in sys.argv:
        return _selftest()
    problems = audit()
    if problems:
        for p in problems:
            print("- %s" % p)
        print("check_failures: %d 处问题" % len(problems))
        return 1
    d = json.load(io.open(REG, encoding="utf-8"))
    es = d["entries"]
    fixed = sum(1 for e in es if e["status"] == "fixed")
    print("check_failures: OK（%d 条登记，其中已修 %d / 未闭 %d；"
          "每条都有 witness）" % (len(es), fixed, len(es) - fixed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
