# -*- coding: utf-8 -*-
"""R103 变异体：新用例 `test_r103_plan_objective_digest_matches_ledger` 的两向自证。

三个实验（每个都 `try/finally` 逐字节还原）：

  A. 改**计划表**里第 rn0 轮的 objective（追加一个汉字）⇒ 必须**红**；
  B. 改**摘要文件**里第 rn0 轮的指纹（首字符换掉）⇒ 必须**红**；
  C. 把摘要里 `rounds` 改成空映射 ⇒ 必须**红**（空集先断言非空，R99 ④）。

还原判据：**逐字节 sha256 相等**（不是「看起来一样」）。
`rn0` 从摘要文件里**现算**（取最小轮号），不写死 —— 否则换轮次就失效。
"""
from __future__ import print_function

import hashlib
import io
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = r"C:\Program Files\Python310\python.exe"
PLAN = os.path.join(REPO, "docs", "EVOLVE_ROADMAP_360.md")
DIG = os.path.join(REPO, "docs", "PLAN_LEDGER_DIGEST.json")
NODE = "tests/test_matlabc.py::test_r103_plan_objective_digest_matches_ledger"


def sha(path):
    with io.open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def read_b(path):
    with io.open(path, "rb") as fh:
        return fh.read()


def run_test():
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    p = subprocess.Popen([PY, "-m", "pytest", NODE, "-q", "-rf", "--tb=line"],
                         cwd=REPO, env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = p.communicate(timeout=900)
    text = out.decode("utf-8", "replace")
    first = ""
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("FAILED ") or s.startswith("ERROR "):
            first = s
            break
    tail = [l for l in text.strip().splitlines() if "passed" in l or "failed" in l]
    return p.returncode, (tail[-1] if tail else ""), first


def main():
    if not os.path.isfile(DIG):
        print("[FAIL] 摘要文件不存在：%s（先跑 gen_plan_ledger_digest.py）" % DIG)
        return 2
    dig = json.loads(read_b(DIG).decode("utf-8"))
    rounds = list(dig["rounds"])
    if not rounds:
        print("[FAIL] 摘要 rounds 为空 —— 空集先断言非空")
        return 2
    rn0 = min(int(k) for k in rounds)
    print("rn0 = %d（摘要共 %d 轮）" % (rn0, len(rounds)))

    plan_b0, dig_b0 = read_b(PLAN), read_b(DIG)
    h_plan0, h_dig0 = sha(PLAN), sha(DIG)
    plan_t = plan_b0.decode("utf-8").replace("\r\n", "\n")
    results = []
    try:
        rc, tail, first = run_test()
        print("\n[base    ] rc=%d  %s" % (rc, tail))
        if rc != 0:
            print("[FAIL] 基线就不绿，后续注入无意义：%s" % first)
            return 2

        # ── A：改计划表的 objective ───────────────────────────────────
        lines = plan_t.split("\n")
        hit = [i for i, ln in enumerate(lines)
               if ln.split("|")[0].strip() == str(rn0) and ln.count("|") == 5]
        if len(hit) != 1:
            print("[FAIL] 第 %d 轮那行定位到 %d 处" % (rn0, len(hit)))
            return 2
        cols = lines[hit[0]].split("|")
        cols[4] = cols[4] + u"改"
        lines[hit[0]] = "|".join(cols)
        mut = "\n".join(lines).replace("\n", "\r\n").encode("utf-8")
        with io.open(PLAN, "wb") as fh:
            fh.write(mut)
        print("\n[A inject] 第 %d 轮 objective 尾部加一个汉字；字节 %d -> %d"
              % (rn0, len(plan_b0), len(mut)))
        rc, tail, first = run_test()
        print("[A inject] rc=%d  %s" % (rc, tail))
        print("[A inject] %s" % (first or "(无 FAILED 行)"))
        results.append(("A", rc != 0))
    finally:
        with io.open(PLAN, "wb") as fh:
            fh.write(plan_b0)
        ok_plan = sha(PLAN) == h_plan0
        print("[restore ] 计划表 sha256 还原=%s" % ok_plan)
        results.append(("restore_plan", ok_plan))

    try:
        # ── B：改摘要的指纹 ──────────────────────────────────────────
        d = json.loads(dig_b0.decode("utf-8"))
        old = d["rounds"][str(rn0)]
        d["rounds"][str(rn0)] = ("f" if old[0] != "f" else "e") + old[1:]
        mut = (json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True)
               + "\n").replace("\n", "\r\n").encode("utf-8")
        with io.open(DIG, "wb") as fh:
            fh.write(mut)
        print("\n[B inject] 摘要第 %d 轮指纹首字符改掉；字节 %d -> %d"
              % (rn0, len(dig_b0), len(mut)))
        rc, tail, first = run_test()
        print("[B inject] rc=%d  %s" % (rc, tail))
        print("[B inject] %s" % (first or "(无 FAILED 行)"))
        results.append(("B", rc != 0))
    finally:
        with io.open(DIG, "wb") as fh:
            fh.write(dig_b0)
        ok_dig = sha(DIG) == h_dig0
        print("[restore ] 摘要 sha256 还原=%s" % ok_dig)
        results.append(("restore_dig", ok_dig))

    try:
        # ── C：摘要 rounds 置空 ─────────────────────────────────────
        d = json.loads(dig_b0.decode("utf-8"))
        d["rounds"] = {}
        mut = (json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True)
               + "\n").replace("\n", "\r\n").encode("utf-8")
        with io.open(DIG, "wb") as fh:
            fh.write(mut)
        print("\n[C inject] 摘要 rounds 置空")
        rc, tail, first = run_test()
        print("[C inject] rc=%d  %s" % (rc, tail))
        print("[C inject] %s" % (first or "(无 FAILED 行)"))
        results.append(("C", rc != 0))
    finally:
        with io.open(DIG, "wb") as fh:
            fh.write(dig_b0)
        print("[restore ] 摘要 sha256 还原=%s" % (sha(DIG) == h_dig0))
        results.append(("restore_dig2", sha(DIG) == h_dig0))

    # 收尾：还原后必须复绿
    rc, tail, first = run_test()
    print("\n[final  ] rc=%d  %s" % (rc, tail))
    results.append(("final_green", rc == 0))

    print("\n=== 汇总 ===")
    bad = 0
    for k, ok in results:
        print("  %-14s %s" % (k, "OK" if ok else "FAIL"))
        bad += 0 if ok else 1
    print("→ %s" % ("注入即红 / 还原即绿 / 逐字节还原 全过" if bad == 0
                    else "%d 项不符" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
