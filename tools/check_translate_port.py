# -*- coding: utf-8 -*-
"""MATLAB → C 移植链路的总门（TP1–TP4）。

判据族：
    TP1  ABI 契约：`c_runtime/include/mlc.h` 必须有状态码/数组结构/所有权函数，
         且对外原型不得出现裸 `double *` / `float *`。
    TP2  适配器：ADP-1/2/3 可配对、可生成两侧胶水；坏 spec 必须被抓。
    TP3  算子：MATLAB 语句 → 算子 → C；每个算子有 sample/规则/C 落点；
         已声明夹具必须存在。
    TP4  保真 + 台账：golden 全部通过（Python 参考实现）；台账里
         `verified` 必须有夹具、`ported` 必须有 C 落点。

设计纪律：未验证的算子/规则是**一等状态**，门禁只保证「声明了就必须存在」，
不把「还没验证」本身判红；但 `verified` 的声明必须能被夹具兑现。

用法：
    python tools/check_translate_port.py
    python tools/check_translate_port.py --selftest

退出码：
    0  = TP1–TP4 全部通过
    1  = 有移植链路不合规（ABI/适配器/算子/保真/台账任一红）
    2  = 缺输入（找不到 c_runtime / translate / port_ledger.json）
"""
import argparse
import io
import json
import os
import re
import sys
import tempfile

#: P5 的对手方：本门在 README 质量门表那一行里声明的判据族。
ROW_SIGNATURE = "TP1–TP4"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import adapters, fidelity, operators  # noqa: E402

HEADER = os.path.join(ROOT, "c_runtime", "include", "mlc.h")
LEDGER = os.path.join(ROOT, "port_ledger.json")
SCHEMA = os.path.join(ROOT, "translate", "port_ledger.schema.json")

REQUIRED_TOKENS = (
    "MLC_OK", "MLC_ERR", "MLC_UNIMPLEMENTED", "MLC_MAX_DIMS",
    "mlc_array", "mlc_array_init", "mlc_array_free", "mlc_array_view",
    "mlc_array_require", "mlc_status", "owns_data",
)
FORBIDDEN_PUBLIC = re.compile(r"\b(?:double|float)\s*\*")
STATUSES = ("not_started", "ported_unverified", "verified", "deprecated")


def check_abi(path=None):
    """返回问题列表；空 = 干净。"""
    path = path or HEADER
    if not os.path.isfile(path):
        return ["TP1 缺 ABI 头文件：%s" % path]
    text = io.open(path, "r", encoding="utf-8", errors="replace").read()
    probs = []
    for tok in REQUIRED_TOKENS:
        if tok not in text:
            probs.append("TP1 头文件缺 %s" % tok)
    for line in text.splitlines():
        s = line.strip()
        if (s.endswith(";") and "(" in s and ")" in s
                and FORBIDDEN_PUBLIC.search(s)):
            probs.append("TP1 对外原型出现裸指针：%s" % s)
    return probs


def check_adapters():
    """ADP-1/2/3：配对、胶水、错误映射。"""
    probs = []
    m = [{"name": "mean", "n_args": 1, "dtype": "f64", "in_rank": 1,
          "c": "mlc_mean"}]
    c = [{"name": "mean", "n_args": 1, "dtype": "f64", "in_rank": 1,
          "c": "mlc_mean"}]
    probs.extend(adapters.adapter_problems(m))
    match = adapters.match_specs(m, c)
    if match["matched"] != ["mean"]:
        probs.append("TP2 同名同参未配对：%r" % (match,))
    # 反向：参数个数不同必须判不匹配，而不是静默通过
    bad = adapters.match_specs(m, [dict(c[0], n_args=2)])
    if not bad["mismatched"]:
        probs.append("TP2 参数个数不同未报不匹配")
    ms = adapters.matlab_adapter_source(m[0])
    cs = adapters.c_adapter_source(m[0])
    if "nargin" not in ms or "error(" not in ms:
        probs.append("TP2 MATLAB 胶水缺参数/错误校验")
    if "mlc_array_require" not in cs or "MLC_ERR" not in cs:
        probs.append("TP2 C 胶水缺类型校验/错误码")
    return probs


def check_operators():
    """算子目录 + 解析 + C 发射。"""
    probs = list(operators.operator_problems())
    for op in operators.OPERATORS:
        u = operators.parse_line(op["sample"])
        if u is None:
            probs.append("TP3 %s 的 sample 解析不到" % op["id"])
            continue
        src = operators.emit_c(u)
        if not src:
            probs.append("TP3 %s 的 C 发射为空" % op["id"])
            continue
        if src.count("{") != src.count("}"):
            probs.append("TP3 %s 的 C 发射花括号不配平" % op["id"])
        if "TODO" in src:
            probs.append("TP3 %s 的 C 发射留下 TODO" % op["id"])
    return probs


def check_fidelity():
    """golden 全通过；C 后端缺失只告警，不判负（必须可见）。"""
    ok, rep = fidelity.self_test()
    probs = []
    if not ok:
        for r in rep.get("failed") or []:
            probs.append("TP4 保真失败 %s：%s"
                         % (r.get("case"), r.get("detail")))
        if not rep.get("total"):
            probs.append("TP4 没有任何 golden 夹具")
    return probs, rep


def check_ledger(path=None):
    """台账两向校验。"""
    path = path or LEDGER
    if not os.path.isfile(path):
        return ["TP4 缺移植台账：%s" % path]
    if not os.path.isfile(SCHEMA):
        return ["TP4 缺台账 schema：%s" % SCHEMA]
    try:
        data = json.loads(io.open(path, "r", encoding="utf-8").read())
    except ValueError as e:
        return ["TP4 台账不是合法 JSON：%s" % e]
    probs = []
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return ["TP4 台账缺 entries 数组"]
    if not isinstance(data.get("version"), int) or data["version"] < 1:
        probs.append("TP4 台账 version 非法")
    known_ops = set(operators.operator_ids())
    seen = set()
    for e in data["entries"]:
        if not isinstance(e, dict):
            probs.append("TP4 台账条目不是对象")
            continue
        eid = e.get("id")
        if not eid:
            probs.append("TP4 台账条目缺 id")
            continue
        if eid in seen:
            probs.append("TP4 台账 id 重复：%s" % eid)
        seen.add(eid)
        if e.get("status") not in STATUSES:
            probs.append("TP4 %s 的 status 非法：%r" % (eid, e.get("status")))
        for opid in e.get("operators") or []:
            if opid not in known_ops:
                probs.append("TP4 %s 引用了未知算子 %s" % (eid, opid))
        golden = e.get("golden") or []
        for fn in golden:
            if not os.path.isfile(os.path.join(operators.GOLDEN_DIR, fn)):
                probs.append("TP4 %s 的夹具不存在：%s" % (eid, fn))
        if e.get("status") == "verified" and not golden:
            probs.append("TP4 %s 标 verified 却没有夹具" % eid)
        cpath = e.get("c") or ""
        if e.get("status") in ("ported_unverified", "verified"):
            if not cpath or not os.path.isfile(os.path.join(ROOT, cpath)):
                probs.append("TP4 %s 标 %s 却没有 C 落点：%s"
                             % (eid, e.get("status"), cpath))
    return probs


def run_checks():
    probs = []
    probs.extend(check_abi())
    probs.extend(check_adapters())
    probs.extend(check_operators())
    fp, rep = check_fidelity()
    probs.extend(fp)
    probs.extend(check_ledger())
    entries = []
    if os.path.isfile(LEDGER):
        try:
            entries = json.loads(
                io.open(LEDGER, "r", encoding="utf-8").read()).get(
                    "entries") or []
        except ValueError:
            entries = []
    stats = {
        "operators": operators.operator_census(),
        "rules_adapters": adapters.adapter_rule_ids(),
        "fidelity": {"total": rep.get("total"), "passed": rep.get("passed"),
                     "c_backend": rep.get("c_backend")},
        "ledger": entries,
    }
    return probs, stats


def _write(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)


def _selftest():
    good = 0
    bad = 0

    def chk(cond, msg):
        if cond:
            # 自证计数用可变容器（Python 3.6 的 nonlocal 在嵌套函数里可用，
            # 但这里保持与其它门一致的写法：用列表累计）。
            good_box[0] += 1
        else:
            bad_box[0] += 1
            print("  [FAIL] %s" % msg)

    good_box = [0]
    bad_box = [0]
    tmp = tempfile.mkdtemp(prefix="mlc_tp_")
    try:
        # ABI：坏样本必须红、真头文件必须绿
        bh = os.path.join(tmp, "bad.h")
        _write(bh, "#define X 1\n")
        chk(bool(check_abi(bh)), "ABI 坏样本未判红")
        chk(not check_abi(HEADER), "ABI 真头文件被误伤")

        # 适配器：负参数个数必须红
        chk(bool(adapters.adapter_problems([{"name": "x", "n_args": -1}])),
            "适配器坏样本未判红")
        chk(not adapters.adapter_problems(
            [{"name": "mean", "n_args": 1, "dtype": "f64", "in_rank": 1}]),
            "适配器好样本被误伤")

        # 算子：空规则/坏 sample 必须红
        bad_ops = [{"id": "OP-X", "matlab": "x", "c": "c", "kind": "k",
                    "rules": (), "sample": "y = x;", "verified_by": ""}]
        chk(bool(operators.operator_problems(bad_ops)), "算子坏样本未判红")
        chk(not operators.operator_problems(), "真算子目录被误伤")

        # 保真：错误期望必须红；真夹具必须绿
        gd = os.path.join(tmp, "golden")
        _write(os.path.join(gd, "bad.json"), json.dumps({
            "name": "bad", "operator": "OP-ADD", "rules": ["EXPAND-1"],
            "inputs": {"a": {"dtype": "f64", "shape": [1], "data": [1.0]},
                       "b": {"dtype": "f64", "shape": [1], "data": [1.0]}},
            "expected": {"dtype": "f64", "shape": [1], "data": [3.0]},
            "tol": {"abs": 1e-12, "rel": 1e-9}}))
        rep = fidelity.run_all(golden_dir=gd)
        chk(bool(rep.get("failed")), "保真坏样本未判红")
        ok, _ = fidelity.self_test()
        chk(ok, "真 golden 未全部通过")

        # 台账：verified 无夹具、C 落点不存在必须红
        bl = os.path.join(tmp, "ledger.json")
        _write(bl, json.dumps({"version": 1, "entries": [{
            "id": "x", "matlab": "m", "c": "nope.c", "status": "verified",
            "operators": ["OP-ADD"], "golden": []}]}))
        chk(bool(check_ledger(bl)), "台账坏样本未判红")
        chk(not check_ledger(LEDGER), "真台账被误伤")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    good = good_box[0]
    bad = bad_box[0]
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if (bad == 0 and good >= 9) else 1


def _missing_inputs():
    miss = []
    if not os.path.isfile(HEADER):
        miss.append(HEADER)
    if not os.path.isfile(LEDGER):
        miss.append(LEDGER)
    if not os.path.isdir(os.path.join(ROOT, "translate")):
        miss.append(os.path.join(ROOT, "translate"))
    if not os.path.isdir(os.path.join(ROOT, "c_runtime")):
        miss.append(os.path.join(ROOT, "c_runtime"))
    return miss


def main(argv=None):
    ap = argparse.ArgumentParser(description="MATLAB→C 移植链路总门（TP1–TP4）")
    ap.add_argument("--selftest", action="store_true", help="两向自证")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()

    miss = _missing_inputs()
    if miss:
        print("check_translate_port: 缺输入（%s）" % ", ".join(miss))
        return 2

    probs, stats = run_checks()
    print("  [统计] 算子 %d（已验证 %d / 未验证 %d）；适配器规则 %s"
          % (stats["operators"]["total"], stats["operators"]["verified"],
             stats["operators"]["unverified"],
             ", ".join(stats["rules_adapters"])))
    fb = stats["fidelity"]
    if fb["c_backend"] and fb["c_backend"].get("available"):
        print("  [C 后端] %s" % fb["c_backend"].get("compiler"))
    else:
        print("  [C 后端] 不可用（未找到 CC/gcc/clang/cc/cl）—— "
              "Python 参考实现已跑，C 编译验证待 CI")
    if probs:
        for p in probs:
            print("  - %s" % p)
        print("check_translate_port: %d 项不合规" % len(probs))
        return 1
    print("check_translate_port: OK（TP1–TP4 全绿；golden %d/%d；台账 %d 条）"
          % (stats["fidelity"]["passed"], stats["fidelity"]["total"],
             len(stats["ledger"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
