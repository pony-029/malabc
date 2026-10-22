# -*- coding: utf-8 -*-
"""MATLAB → C 移植链路的总门（TP1–TP9）。

判据族：
    TP1  ABI 契约：`c_runtime/include/mlc.h` 必须有状态码/数组结构/所有权函数，
         且对外原型不得出现裸 `double *` / `float *`。
    TP1b 双侧约束：`translate/contracts/matlab_c_constraints.json` 必须与
         `mlc.h` / `translate.rules` / `translate.adapters` 双向一致。
    TP2  适配器：ADP-1/2/3 可配对、可生成两侧胶水；坏 spec 必须被抓。
    TP3  算子：MATLAB 语句 → 算子 → C；每个算子有 sample/规则/C 落点；
         已声明夹具必须存在。
    TP4  保真 + 台账：golden 全部通过（Python 参考实现 + 可选 C 编译执行）；
         台账里 `verified` 必须有夹具、`ported` 必须有 C 落点。

设计纪律：未验证的算子/规则是**一等状态**，门禁只保证「声明了就必须存在」，
不把「还没验证」本身判红；但 `verified` 的声明必须能被夹具兑现。

用法：
    python tools/check_translate_port.py
    python tools/check_translate_port.py --require-c      # CI：没有 C 编译器判红
    python tools/check_translate_port.py --sync-ledger    # 按 C 结果同步台账
    python tools/check_translate_port.py --sync-ledger --write
    python tools/check_translate_port.py --selftest

退出码：
    0  = TP1–TP9 全部通过
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
ROW_SIGNATURE = "TP1–TP9"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import adapters, fidelity, operators  # noqa: E402
import translate.rules as rules_mod  # noqa: E402

HEADER = os.path.join(ROOT, "c_runtime", "include", "mlc.h")
LEDGER = os.path.join(ROOT, "port_ledger.json")
SCHEMA = os.path.join(ROOT, "translate", "port_ledger.schema.json")
CONSTRAINTS = os.path.join(ROOT, "translate", "contracts",
                           "matlab_c_constraints.json")

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


def check_constraints(path=None):
    """TP1b：双侧约束 JSON ⇄ mlc.h / translate.rules / translate.adapters。"""
    path = path or CONSTRAINTS
    if not os.path.isfile(path):
        return ["TP1b 缺双侧约束 JSON：%s" % path]
    try:
        data = json.loads(io.open(path, "r", encoding="utf-8").read())
    except ValueError as e:
        return ["TP1b 双侧约束不是合法 JSON：%s" % e]
    probs = []
    m = data.get("matlab") or {}
    c = data.get("c") or {}
    abi = data.get("abi") or {}
    if m.get("index_base") != 1:
        probs.append("TP1b matlab.index_base 必须是 1")
    if c.get("index_base") != 0:
        probs.append("TP1b c.index_base 必须是 0")
    if m.get("memory_order") == c.get("memory_order"):
        probs.append("TP1b 两侧 memory_order 不应相同（列主序 vs 行主序）")
    if m.get("implicit_expansion") == c.get("implicit_expansion"):
        probs.append("TP1b 两侧 implicit_expansion 不应相同")
    if m.get("error_model") == c.get("error_model"):
        probs.append("TP1b 两侧 error_model 不应相同（MException vs mlc_status）")

    header = ""
    if os.path.isfile(HEADER):
        header = io.open(HEADER, "r", encoding="utf-8",
                         errors="replace").read()
    mm = re.search(r"#define\s+MLC_MAX_DIMS\s+(\d+)", header)
    if not mm:
        probs.append("TP1b mlc.h 里找不到 MLC_MAX_DIMS")
    elif int(mm.group(1)) != abi.get("max_dims"):
        probs.append("TP1b abi.max_dims=%r 与 MLC_MAX_DIMS=%s 不一致"
                     % (abi.get("max_dims"), mm.group(1)))
    for name, code in (abi.get("status_codes") or {}).items():
        if not re.search(r"\b%s\s*=\s*%d\b" % (name, int(code)), header):
            probs.append("TP1b 状态码 %s=%s 与 mlc.h 不一致" % (name, code))
    if list(abi.get("dtypes") or []) != list(adapters.DTYPES):
        probs.append("TP1b abi.dtypes 与 adapters.DTYPES 不一致")
    forbidden = abi.get("forbidden_public_types") or []
    for t in ("double*", "float*"):
        if t not in forbidden:
            probs.append("TP1b forbidden_public_types 缺 %s" % t)

    tc = data.get("toolchain") or {}
    if not tc.get("preferred_windows"):
        probs.append("TP1b toolchain.preferred_windows 缺失")

    rule_ids = [r.get("id") for r in (data.get("rules") or [])]
    if rule_ids != list(rules_mod.rule_ids()):
        probs.append("TP1b rules 与 translate.rules 不一致：%r != %r"
                     % (rule_ids, list(rules_mod.rule_ids())))
    adp_ids = [a.get("id") for a in (data.get("adapters") or [])]
    if adp_ids != list(adapters.adapter_rule_ids()):
        probs.append("TP1b adapters 与 translate.adapters 不一致：%r != %r"
                     % (adp_ids, list(adapters.adapter_rule_ids())))
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


#: TP6 的 C 源：分配型算子的所有权与错误路径。
#: 为什么单独测：golden 只比数值，而这些是"不崩、不漏、不静默"的约束。
_OWNERSHIP_C = r"""
#include <stdio.h>
#include <string.h>
#include "mlc.h"
#include "mlc_ops.h"

static int fails = 0;
#define CHECK(cond, msg) do { \
    if (!(cond)) { printf("FAIL %s\\n", msg); fails = 1; } \
} while (0)

int main(void) {
    double buf[4] = {1.0, 2.0, 3.0, 4.0};
    int64_t sh[1] = {4};
    mlc_array x;
    mlc_array out;
    mlc_status st;

    if (mlc_array_init(&x, MLC_F64, 1, sh) != MLC_OK) return 1;
    memcpy(x.data, buf, sizeof(buf));

    /* 1) 空输入：必须 MLC_ERR，不能崩 */
    st = mlc_op_mask_alloc(NULL, 0, 2.0, &out);
    CHECK(st == MLC_ERR, "mask_alloc(NULL) 应返回 MLC_ERR");

    /* 2) 零命中：长度 0，仍然由算子分配，可正常 free */
    memset(&out, 0, sizeof(out));
    st = mlc_op_mask_alloc(&x, 0, 100.0, &out);
    CHECK(st == MLC_OK, "零命中应成功");
    CHECK(mlc_array_numel(&out) == 0, "零命中长度应为 0");
    CHECK(out.owns_data != 0, "分配型输出必须 owns_data");
    mlc_array_free(&out);
    CHECK(out.data == NULL, "free 后 data 必须置空");

    /* 3) 非分配版本：out 长度不符 -> MLC_ERR，且不改数据 */
    {
        int64_t bad_sh[1] = {3};
        double before[3] = {-1.0, -1.0, -1.0};
        mlc_array bad;
        if (mlc_array_init(&bad, MLC_F64, 1, bad_sh) != MLC_OK) return 1;
        memcpy(bad.data, before, sizeof(before));
        st = mlc_op_mask(&x, 0, 2.0, &bad);   /* 命中 2 个，out 是 3 */
        CHECK(st == MLC_ERR, "长度不符必须 MLC_ERR");
        CHECK(((double *)bad.data)[0] == -1.0, "失败时不得写入 out");
        mlc_array_free(&bad);
    }

    /* 4) find：1-based 下标 */
    memset(&out, 0, sizeof(out));
    st = mlc_op_find_alloc(&x, 0, 2.0, &out);
    CHECK(st == MLC_OK, "find_alloc 应成功");
    CHECK(mlc_array_numel(&out) == 2, "find 命中数应为 2");
    if (mlc_array_numel(&out) == 2) {
        CHECK(((double *)out.data)[0] == 3.0, "find 首个下标应为 3（1-based）");
        CHECK(((double *)out.data)[1] == 4.0, "find 次个下标应为 4");
    }
    mlc_array_free(&out);

    mlc_array_free(&x);
    if (fails) { printf("OWNERSHIP FAILED\\n"); return 1; }
    printf("ownership ok\\n");
    return 0;
}
"""


def check_ownership(fast=None):
    """TP6：真编译真跑所有权/错误路径测试。"""
    fast = FAST if fast is None else fast
    if fast:
        return []
    cc = fidelity.find_c_compiler()
    if not cc:
        return []
    d = tempfile.mkdtemp(prefix="m2c_own_")
    src = os.path.join(d, "own.c")
    exe = os.path.join(d, "own.exe" if os.name == "nt" else "own")
    io.open(src, "w", encoding="utf-8", newline="").write(_OWNERSHIP_C)
    rt = os.path.join(ROOT, "c_runtime")
    cmd = list(cc) + ["-std=c99", "-O1", "-I", os.path.join(rt, "include"),
                      src,
                      os.path.join(rt, "src", "mlc_runtime.c"),
                      os.path.join(rt, "src", "mlc_ops.c"), "-o", exe]
    rc, out = _run(cmd)
    if rc != 0:
        return ["TP6 所有权测试编译失败：%s" % (out.strip().splitlines()[:2],)]
    rc, out = _run([exe], timeout=60)
    if rc != 0:
        bad = [ln for ln in out.splitlines() if ln.startswith("FAIL")]
        return ["TP6 所有权测试未通过：%s" % (bad[:3] or out.strip()[:120],)]
    print("  [TP6] 所有权/错误路径：通过（空输入、零命中、长度不符、find 1-based）")
    return []


def check_project_dir(fast=None):
    """TP7：目录级转换。

    真实的 MATLAB 工程是**一堆 .m 互相调用**，单文件转换看不出这个问题 ——
    跨文件调用会被当成"未知名字"而拒绝，而门一直是绿的。
    """
    fast = FAST if fast is None else fast
    probs = []
    src_dir = os.path.join(ROOT, "translate", "examples", "proj")
    exp = os.path.join(ROOT, "translate", "examples", "proj.expected")
    if not os.path.isdir(src_dir) or not os.path.isfile(exp):
        return ["TP7 缺样例工程（translate/examples/proj）"]

    d = tempfile.mkdtemp(prefix="m2c_proj_")
    mir = os.path.join(d, "proj.mir")
    rc, out = _run([sys.executable, os.path.join("translate", "mir.py"),
                    src_dir, "-o", mir])
    if rc != 0:
        return ["TP7 目录转换失败：%s" % (out.strip().splitlines()[:2],)]

    text = io.open(mir, encoding="utf-8").read()
    n_func = text.count("\nfunc:") + (1 if text.startswith("func:") else 0)
    if n_func != 3:
        probs.append("TP7 目录里 3 个 .m 应产出 3 个函数，实得 %d" % n_func)
    if "call:y:addone:x" not in text:
        probs.append("TP7 跨文件调用没被解析（addone 在另一个 .m 里）")

    if fast:
        print("  [TP7] 目录转换：%d 个函数（快检，跳过编译）" % n_func)
        return probs

    gen = os.path.join(d, "gen")
    rc, out = _run([M2C_BIN, "build", "--mir", mir, "--out", gen,
                    "--name", "proj", "--expect", exp])
    if rc != 0:
        probs.append("TP7 生成工程失败：%s" % (out.strip().splitlines()[:2],))
        return probs

    cc = fidelity.find_c_compiler()
    if not cc:
        probs.append("TP7 没有可用 C 编译器")
        return probs
    rt = os.path.join(ROOT, "c_runtime")
    exe = os.path.join(gen, "proj.exe" if os.name == "nt" else "proj")
    base = list(cc) if isinstance(cc, (list, tuple)) else [cc]
    rc, out = _run(base + ["-std=c99", "-O1",
                           "-I", os.path.join(gen, "include"),
                           "-I", os.path.join(rt, "include"),
                           os.path.join(gen, "src", "gen.c"),
                           os.path.join(gen, "src", "main.c"),
                           os.path.join(rt, "src", "mlc_runtime.c"),
                           os.path.join(rt, "src", "mlc_ops.c"), "-o", exe])
    if rc != 0:
        probs.append("TP7 工程编译失败：%s" % (out.strip().splitlines()[:2],))
        return probs

    rc, out = _run([exe], timeout=60)
    if rc != 0:
        probs.append("TP7 工程运行失败（rc=%s）：%s"
                     % (rc, out.strip().splitlines()[:2]))
        return probs
    bad = compare_outputs([ln.strip() for ln in out.strip().splitlines()],
                          exp, "工程级")
    if bad:
        probs.append(bad)
    else:
        print("  [TP7] 多文件工程：3 个 .m -> 3 个函数，跨文件调用，数值一致")
    return probs


def check_dynamic_consistency():
    """分配型算子清单的三份副本必须一致。

    同一件事现在写在三处：算子表（dynamic 标注）、Rust（DYNAMIC_OPS）、
    C（`*_alloc` 符号）。三处不同步的后果是**静默的**：
    算子表说动态、Rust 不知道 -> 生成器预先 init 一个长度不对的数组。
    """
    probs = []
    mine = operators.dynamic_ops()

    rust = set()
    rs = os.path.join(ROOT, "rust", "m2c", "src", "emit.rs")
    if os.path.isfile(rs):
        txt = io.open(rs, encoding="utf-8").read()
        m = re.search(r"DYNAMIC_OPS:\s*&\[&str\]\s*=\s*&\[(.*?)\]", txt, re.S)
        if m:
            rust = set(re.findall(r'"(OP-[A-Z0-9]+)"', m.group(1)))
        else:
            probs.append("TP8 在 emit.rs 里找不到 DYNAMIC_OPS 清单")
    else:
        probs.append("TP8 找不到 rust/m2c/src/emit.rs")

    cpaths = [os.path.join(ROOT, "c_runtime", "include", "mlc_ops.h")]
    calls = set()
    for p in cpaths:
        if os.path.isfile(p):
            txt = io.open(p, encoding="utf-8").read()
            calls = set(re.findall(r"mlc_op_([a-z0-9_]+)_alloc\s*\(", txt))
    # C 侧符号名 -> 算子 ID 映射靠算子表里的 c 字段
    from_c = set()
    for o in operators.OPERATORS:
        name = (o.get("c") or "")
        short = name[len("mlc_op_"):] if name.startswith("mlc_op_") else name
        short = short.replace("_alloc", "")
        if short in calls:
            from_c.add(o["id"])

    if mine != rust:
        probs.append("TP8 分配型算子不一致：算子表 %s vs Rust %s"
                     % (sorted(mine), sorted(rust)))
    if mine != from_c:
        probs.append("TP8 分配型算子不一致：算子表 %s vs C 的 *_alloc %s"
                     % (sorted(mine), sorted(from_c)))
    if not probs:
        print("  [TP8] 分配型算子三处一致：%s" % "、".join(sorted(mine)))
    return probs


def _parity_verified(out):
    m = re.search(r"PA1 已对拍 (\d+)", out or "")
    return int(m.group(1)) if m else 0


def check_parity_demo(fast=None):
    """TP9：同一份 MIR，Python 解释执行 vs C 编译执行，逐值对拍。

    为什么单列一项：golden 验的是**算子**，自测验的是"我声明的期望值"，
    都没有验"发射出来的 C 与 MIR 的语义是否一致"。这一项才验那件事。
    """
    fast = FAST if fast is None else fast
    if fast:
        return []
    d = tempfile.mkdtemp(prefix="m2c_par_")
    mir = os.path.join(d, "d.mir")
    rc, out = _run([sys.executable, os.path.join("translate", "mir.py"),
                    os.path.join("translate", "examples", "demo_port.m"),
                    "-o", mir])
    if rc != 0:
        return ["TP9 生成 MIR 失败：%s" % (out.strip().splitlines()[:2],)]
    rc, out = _run([sys.executable, os.path.join("tools", "parity_report.py"),
                    "--mir", mir])
    tail = [ln for ln in out.strip().splitlines()
            if ln.startswith("PA1 ") or ln.startswith("PA2 ")
            or ln.startswith("对拍合计")]
    if rc != 0:
        return ["TP9 对拍未通过：%s" % (tail[:1] or out.strip()[-160:],)]
    verified = _parity_verified(out)
    if verified < 1:
        return ["TP9 没有任何函数完成对拍（PA1=0）；"
                "未对拍不能当通过：%s" % (tail[:2] or out.strip()[-160:],)]
    if tail:
        print("  [TP9] " + " / ".join(x.strip() for x in tail))
    return []


def check_ledger_stale(path=None):
    """台账里 status=verified 但备注还写着 UNIMPLEMENTED —— 备注比代码落后。

    这轮是靠人眼发现的（transpose/matmul 早已实现，备注仍写"返回
    MLC_UNIMPLEMENTED"）。**能让门抓的，就不要靠人眼。**
    """
    path = path or LEDGER
    probs = []
    if not os.path.isfile(path):
        return probs
    try:
        data = json.loads(io.open(path, encoding="utf-8").read())
    except (IOError, OSError, ValueError):
        return probs
    for e in data.get("entries") or []:
        status = (e.get("status") or "").lower()
        note = e.get("notes") or ""
        if status in ("verified", "done") and "UNIMPLEMENTED" in note.upper():
            probs.append("TP2 台账陈旧：%s 状态 %s，备注仍称 UNIMPLEMENTED"
                         % (e.get("id"), status))
    return probs


def check_fidelity(require_c=False, fast=None):
    fast = FAST if fast is None else fast
    """golden 全通过（Python + 可选 C）；`--require-c` 时无编译器判红。"""
    # 快检不跑 C（11 个 golden 各编译一次是这道门的主要耗时）
    rep = fidelity.run_all(with_c=not fast)
    probs = []
    if not rep.get("total"):
        probs.append("TP4 没有任何 golden 夹具")
    if rep.get("passed") != rep.get("total"):
        for r in rep.get("failed") or []:
            probs.append("TP4 保真失败 %s：%s"
                         % (r.get("case"), r.get("detail")))
    cc = rep.get("c_backend") or {}
    if require_c and not cc.get("available"):
        probs.append("TP4 --require-c：没有可用 C 编译器")
    # 快检没跑 C：`c` 是空字典，不能据此判失败（"没测"不等于"不通过"）
    if cc.get("available") and not fast:
        for r in rep.get("results") or []:
            op = r.get("operator")
            if op not in operators.C_IMPLEMENTED:
                continue
            cr = r.get("c") or {}
            if cr.get("status") != "ok":
                probs.append("TP4 C 后端未通过 %s（%s）：%r"
                             % (r.get("case"), op, cr))
    return probs, rep


def sync_ledger(rep, path=None, write=False):
    """按 C 后端结果同步台账：C 通过 ⇒ verified；有 C 落点但未过 ⇒ ported_unverified。"""
    path = path or LEDGER
    if not os.path.isfile(path):
        return []
    data = json.loads(io.open(path, "r", encoding="utf-8").read())
    c_ok = {}
    for r in rep.get("results") or []:
        c_ok[r.get("operator")] = (
            (r.get("c") or {}).get("status") == "ok")
    changes = []
    for e in data.get("entries") or []:
        ops = e.get("operators") or []
        if not ops:
            continue
        if all(c_ok.get(o) for o in ops):
            new = "verified"
        elif any(o in operators.C_IMPLEMENTED for o in ops):
            new = "ported_unverified"
        else:
            new = "not_started"
        if new != e.get("status"):
            changes.append((e.get("id"), e.get("status"), new))
            e["status"] = new
    if write and changes:
        # 台账是手写配置（仓库约定 CRLF），写回时保持 CRLF，避免整文件 diff。
        _write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n",
               newline="\r\n")
    return changes


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


M2C_DIR = os.path.join(ROOT, "rust", "m2c")
M2C_BIN = os.path.join(M2C_DIR, "target", "release",
                       "m2c.exe" if os.name == "nt" else "m2c")
MIR_EXAMPLE = os.path.join(ROOT, "translate", "examples", "demo_port.m")
#: 样例的确定性覆盖率下界（只许升）。它挡住"多写 unmapped 让它变绿"这条路。
#: 已经到 90.9%，下界跟上（棘轮：只许升）
#: 声明本工具自带自证，check_tool_selftests 会在发版时真跑
SELFTEST = True

MIN_M2C_COVERAGE = 0.9

#: 快检：跳过一切"真编译/真运行"（发版快筛用；CI 永远跑全量）。
#: 用环境变量而不是只能在命令行传参，是为了让 release.py 一行就能打开。
FAST = os.environ.get("MATLABC_GATE_FAST") == "1"


def _run(cmd, cwd=None, timeout=300):
    import subprocess
    try:
        p = subprocess.run(cmd, cwd=cwd or ROOT, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def build_m2c():
    """按需编译 Rust 发射器。返回 (可用?, 说明)。"""
    if not os.path.isfile(os.path.join(M2C_DIR, "Cargo.toml")):
        return False, "没有 rust/m2c（本版未启用 MIR 发射器）"
    newest_src = 0
    for dp, dn, fn in os.walk(os.path.join(M2C_DIR, "src")):
        for f in fn:
            newest_src = max(newest_src, os.path.getmtime(os.path.join(dp, f)))
    if os.path.isfile(M2C_BIN) and os.path.getmtime(M2C_BIN) >= newest_src:
        return True, "已是最新"
    rc, out = _run(["cargo", "build", "--release"], cwd=M2C_DIR)
    if rc is None:
        return False, "没有 cargo（跳过 TP5，不算绿）"
    if rc != 0:
        return False, "cargo build 失败：%s" % out.strip().splitlines()[-1:]
    return True, "刚编译"


def compare_outputs(got, exp_path, tag):
    """把"程序输出"与"期望文件"逐行比对；一致返回 None，否则返回问题串。

    抽成函数是为了能**两向自证**：只验证"一致时通过"是不够的 ——
    如果比对逻辑永远返回 None，门会永远绿，而它看起来完全正常。
    """
    try:
        exp = [ln.strip() for ln in
               io.open(exp_path, encoding="utf-8").read().splitlines()
               if ln.strip()]
    except (IOError, OSError) as exc:
        return "TP5 读不到期望文件 %s：%s" % (exp_path, exc)
    if got != exp:
        return ("TP5 输出与期望不符（%s）：\n  期望 %r\n  实得 %r"
                % (tag, exp, got))
    return None


def check_m2c(require_c=False, fast=None):
    fast = FAST if fast is None else fast
    """TP5：MIR 生成 → C 发射 → gcc 语法编译 → 两次发射逐字节一致。

    为什么要有它：TP1–TP9 证明的是"算子→C 的调用能编译能跑"，
    但**没有任何东西**证明"整条链路（.m → MIR → C 工程）产出的是合法 C"。
    """
    probs = []
    ok, why = build_m2c()
    if not ok:
        print("  [TP5] 跳过：%s" % why)
        if require_c:
            probs.append("TP5 缺 Rust 发射器（--require-c 下判红）：%s" % why)
        return probs, {"available": False, "why": why}

    # 1) .m → MIR（Python 侧，复用算子表 = 单一事实源）
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "translate"))
    from translate import mir as mir_mod  # noqa: E402

    src = io.open(MIR_EXAMPLE, "r", encoding="utf-8").read()
    mir_text, st = mir_mod.to_mir(src)
    if not st["functions"]:
        probs.append("TP5 样例没有解析出函数")
        return probs, {"available": True, "why": "无函数"}
    if not st["ops"]:
        probs.append("TP5 样例没有映射出任何算子")

    # 2) MIR → 两遍 C（确定性）
    import tempfile
    outs = []
    for _ in range(2):
        d = tempfile.mkdtemp(prefix="m2c_")
        p = os.path.join(d, "in.mir")
        io.open(p, "w", encoding="utf-8", newline="").write(mir_text)
        exp_default = os.path.join(ROOT, "translate", "examples",
                                   "demo_port.expected")
        ex = os.path.join(ROOT, "translate", "examples")
        # 三组夹具都编进生成物自测：拿工程单独走的人，跑 ctest 就能覆盖
        # 默认 / x=10 20 30 i=3 / i=1（else 分支）这三种输入。
        cases = [
            "%s=%s" % (os.path.join(ex, "demo_port.fixture"),
                       os.path.join(ex, "demo_port.expected.args")),
            "%s=%s" % (os.path.join(ex, "demo_port.fixture.else"),
                       os.path.join(ex, "demo_port.expected.else")),
        ]
        cmd = [M2C_BIN, "build", "--mir", p, "--out", d,
               "--name", "demo", "--expect", exp_default]
        for c in cases:
            cmd.extend(["--case", c])
        rc, out = _run(cmd)
        if rc != 0:
            probs.append("TP5 发射失败：%s"
                         % (out.strip().splitlines()[-1:] or rc))
            return probs, {"available": True, "why": "发射失败"}
        gen = io.open(os.path.join(d, "src", "gen.c"), "rb").read()
        outs.append(gen)
    if outs[0] != outs[1]:
        probs.append("TP5 两次发射结果不一致（不满足确定性）")

    if fast:
        print("  [TP5] 快检：跳过 C 编译与运行（发版快筛；CI 跑全量）")
        total = st["ops"] + st["unmapped"]
        cov = (float(st["ops"]) / total) if total else 0.0
        if cov < MIN_M2C_COVERAGE:
            probs.append("TP5 确定性覆盖率 %.1f%% 低于下界 %.0f%%"
                         % (cov * 100.0, MIN_M2C_COVERAGE * 100.0))
        return probs, {"available": True, "why": why, "functions": st["functions"],
                       "ops": st["ops"], "unmapped": st["unmapped"],
                       "coverage": round(cov, 4), "compiled": False,
                       "fast": True}

    # 3) 生成的 C 必须能被真编译器接受
    inc = os.path.join(d, "include")
    rt_inc = os.path.join(ROOT, "c_runtime", "include")
    gen_c = os.path.join(d, "src", "gen.c")
    cc = None
    try:
        from translate import fidelity  # noqa: E402
        cc = fidelity.find_c_compiler()
    except Exception:  # noqa: BLE001 - 找不到就当没有
        cc = None
    if cc:
        # `find_c_compiler()` 可能返回 str，也可能返回 ["zig", "cc"] ——
        # 拼命令前统一成 list，否则 subprocess 会拿到一个 list 当可执行名。
        base = list(cc) if isinstance(cc, (list, tuple)) else [cc]
        rc, out = _run(base + ["-std=c99", "-fsyntax-only",
                               "-I", inc, "-I", rt_inc, gen_c])
        if rc != 0:
            probs.append("TP5 生成的 C 编译失败：%s"
                         % (out.strip().splitlines()[:2],))
        else:
            # **光能编译不够**：还要跑出与 MATLAB 语义一致的数值。
            # 期望值由人写在 .expected 里（golden 纪律：人声明、机器核对）。
            exe = os.path.join(d, "demo.exe" if os.name == "nt" else "demo")
            src_main = os.path.join(d, "src", "main.c")
            rt = os.path.join(ROOT, "c_runtime", "src")
            rc, out = _run(base + [
                "-std=c99", "-O1", "-I", inc, "-I", rt_inc,
                gen_c, src_main,
                os.path.join(rt, "mlc_runtime.c"),
                os.path.join(rt, "mlc_ops.c"), "-o", exe])
            if rc != 0:
                probs.append("TP5 生成工程链接失败：%s"
                             % (out.strip().splitlines()[:2],))
            else:
                # **两组输入**：默认（a[i]=i+1）与 argv（10 20 30 3）。
                # 只跑默认值的话，"输入从哪来"这条链路根本没被验证过。
                # 输入走**夹具文件**（按参数名给值）：argv 只能表达"一串数"，
                # 说不清哪个数属于哪个参数；而 x / v / i 是三个不同的名字。
                # 第三组让 i=1，覆盖 `if i > 1` 的 **else** 分支。
                ex_dir = os.path.join(ROOT, "translate", "examples")
                cases = [
                    ([], "demo_port.expected"),
                    ([os.path.join(ex_dir, "demo_port.fixture")],
                     "demo_port.expected.args"),
                    ([os.path.join(ex_dir, "demo_port.fixture.else")],
                     "demo_port.expected.else"),
                ]
                for extra, exp_name in cases:
                    # 60s 上限：生成物万一有死循环（例如 while 的循环变量没变），
                    # 门要**判红**，而不是陪着它一起等。
                    rc, out = _run([exe] + extra, timeout=60)
                    tag = "默认" if not extra else os.path.basename(extra[0])
                    if rc != 0:
                        probs.append("TP5 生成程序退出码 %s（%s）：%s"
                                     % (rc, tag, out.strip().splitlines()[:2]))
                        continue
                    got = [ln.strip() for ln in out.strip().splitlines()]
                    exp_path = os.path.join(ROOT, "translate", "examples",
                                            exp_name)
                    bad = compare_outputs(got, exp_path, tag)
                    if bad:
                        probs.append(bad)
                    else:
                        print("  [TP5] %s 输入：%d 行与期望一致"
                              % (tag, len(got)))

                # 批量：两个夹具一次跑完，输出用 `=== 路径` 分隔。
                # 这条只在本地手验过 —— 手验的东西没人守，迟早会坏。
                fx1 = os.path.join(ex_dir, "demo_port.fixture")
                fx2 = os.path.join(ex_dir, "demo_port.fixture.else")
                rc, out = _run([exe, fx1, fx2], timeout=60)
                if rc != 0:
                    probs.append("TP5 批量夹具退出码 %s" % (rc,))
                else:
                    got = [ln.strip() for ln in out.strip().splitlines()]
                    want = ["=== %s" % fx1]
                    for nm in ("demo_port.expected.args",
                               "demo_port.expected.else"):
                        want += [ln.strip() for ln in
                                 io.open(os.path.join(ex_dir, nm),
                                         encoding="utf-8").read().splitlines()
                                 if ln.strip()]
                        if nm == "demo_port.expected.args":
                            want.append("=== %s" % fx2)
                    if got != want:
                        probs.append("TP5 批量夹具输出不符：\n  期望 %r\n  实得 %r"
                                     % (want[:4], got[:4]))
                    else:
                        print("  [TP5] 批量夹具：%d 行与期望一致" % len(got))

                # 生成物**自带**自测（src/selftest.c）：拿这个工程单独走的人，
                # 不装 Python 也能回答"这堆生成代码算得对不对"。
                st_src = os.path.join(d, "src", "selftest.c")
                if os.path.isfile(st_src):
                    st_exe = os.path.join(d, "selftest" if os.name != "nt"
                                          else "selftest.exe")
                    rc, out = _run(base + [
                        "-std=c99", "-O1", "-I", inc, "-I", rt_inc,
                        gen_c, st_src,
                        os.path.join(rt, "mlc_runtime.c"),
                        os.path.join(rt, "mlc_ops.c"), "-o", st_exe])
                    if rc != 0:
                        probs.append("TP5 生成物自测编译失败：%s"
                                     % (out.strip().splitlines()[:2],))
                    else:
                        rc, out = _run([st_exe], timeout=60)
                        if rc != 0:
                            probs.append("TP5 生成物自测未通过：%s"
                                         % (" | ".join(out.strip().splitlines()[:3]),))
                        else:
                            print("  [TP5] 生成物自带自测：%d 项全过"
                                  % len([l for l in out.splitlines()
                                         if l.startswith("ok")]))
    else:
        print(u"  [TP5] 没有 C 编译器：只验了「可发射 + 确定性」，"
              u"没验「可编译」")

    total = st["ops"] + st["unmapped"]
    cov = (float(st["ops"]) / total) if total else 0.0
    if cov < MIN_M2C_COVERAGE:
        probs.append(
            "TP5 确定性覆盖率 %.1f%% 低于下界 %.0f%%（%d 条映射 / %d 条未映射）"
            % (cov * 100.0, MIN_M2C_COVERAGE * 100.0, st["ops"], st["unmapped"]))
    else:
        print("  [TP5] 覆盖：%d/%d = %.1f%%（未映射 %d）"
              % (st["ops"], total, cov * 100.0, st["unmapped"]))
        per = st.get("per_op") or {}
        if per:
            top = sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))
            print("  [TP5] 算子分布：%s"
                  % "、".join("%s×%d" % (k, v) for k, v in top[:6]))
        if st.get("calls"):
            print("  [TP5] 函数间调用：%d 处" % st["calls"])

    return probs, {"available": True, "why": why, "functions": st["functions"],
                   "ops": st["ops"], "unmapped": st["unmapped"],
                   "coverage": round(cov, 4),
                   "compiled": bool(cc)}


def run_checks(require_c=False):
    probs = []
    probs.extend(check_abi())
    probs.extend(check_constraints())
    probs.extend(check_adapters())
    probs.extend(check_operators())
    fp, rep = check_fidelity(require_c=require_c, fast=FAST)
    probs.extend(fp)
    probs.extend(check_ledger_stale())
    probs.extend(check_ownership())
    probs.extend(check_dynamic_consistency())
    probs.extend(check_project_dir())
    probs.extend(check_parity_demo())
    m2c_probs, m2c_stats = check_m2c(require_c=require_c, fast=FAST)
    probs.extend(m2c_probs)
    probs.extend(check_ledger())
    entries = []
    if os.path.isfile(LEDGER):
        try:
            entries = json.loads(
                io.open(LEDGER, "r", encoding="utf-8").read()).get(
                    "entries") or []
        except ValueError:
            entries = []
    c_res = [r for r in (rep.get("results") or [])
             if r.get("operator") in operators.C_IMPLEMENTED]
    c_ok = sum(1 for r in c_res
               if (r.get("c") or {}).get("status") == "ok")
    stats = {
        "operators": operators.operator_census(),
        "rules_adapters": adapters.adapter_rule_ids(),
        "fidelity": {"total": rep.get("total"), "passed": rep.get("passed"),
                     "c_backend": rep.get("c_backend")},
        "fidelity_report": rep,
        "c_ok": c_ok,
        "c_total": len(c_res),
        "ledger": entries,
        "m2c": m2c_stats,
    }
    return probs, stats


def _write(path, text, newline="\n"):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    io.open(path, "w", encoding="utf-8", newline=newline).write(text)


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

        # 双侧约束：坏样本必须红、真 JSON 必须绿
        bc = os.path.join(tmp, "constraints.json")
        _write(bc, json.dumps({
            "matlab": {"index_base": 0},
            "c": {"index_base": 0},
            "abi": {"max_dims": 99},
            "rules": [], "adapters": []}))
        chk(bool(check_constraints(bc)), "约束坏样本未判红")
        chk(not check_constraints(), "真约束被误伤")

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

        # C 后端：有编译器就必须全部通过；没有则显式跳过（不假装）
        repc = fidelity.run_all(with_c=True)
        cc = repc.get("c_backend") or {}
        if cc.get("available"):
            all_ok = True
            for r in repc.get("results") or []:
                if r.get("operator") not in operators.C_IMPLEMENTED:
                    continue
                if (r.get("c") or {}).get("status") != "ok":
                    all_ok = False
            chk(all_ok, "C 后端有用例未通过")
        else:
            chk(True, "C 后端不可用（跳过编译，行为已显式记录）")

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
    return 0 if (bad == 0 and good >= 13) else 1


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


def _dump_stats(stats):
    """把机器可读的统计写到 `MATLABC_GATE_STATS` 目录（供发版历史记录）。

    为什么不用解析 stdout：日志文案会随排版变，而历史数据是要长期比的 ——
    一旦某次改了措辞，趋势就断了。
    """
    out_dir = os.environ.get("MATLABC_GATE_STATS")
    if not out_dir:
        return
    m = stats.get("m2c") or {}
    payload = {
        "fast": bool(m.get("fast")),
        "coverage": m.get("coverage"),
        "ops": m.get("ops"),
        "unmapped": m.get("unmapped"),
        "functions": m.get("functions"),
        "golden": stats.get("fidelity", {}).get("passed"),
        "golden_total": stats.get("fidelity", {}).get("total"),
    }
    try:
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        io.open(os.path.join(out_dir, "check_translate_port.json"), "w",
                encoding="utf-8", newline="").write(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except (IOError, OSError):
        pass


def _selftest():
    """两向自证：一致必须过、不一致必须红、缺文件必须红。"""
    import tempfile
    good = 0
    bad = 0

    def chk(cond, name):
        nonlocal good, bad
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %s" % name)

    d = tempfile.mkdtemp(prefix="tp5_st_")
    exp = os.path.join(d, "e.txt")
    io.open(exp, "w", encoding="utf-8", newline="").write("a: 1\nb: 2\n")
    chk(compare_outputs(["a: 1", "b: 2"], exp, "t") is None, "一致时应通过")
    chk(compare_outputs(["a: 1", "b: 3"], exp, "t") is not None, "不一致时必须红")
    chk(compare_outputs(["a: 1"], exp, "t") is not None, "少一行必须红")
    chk(compare_outputs([], exp, "t") is not None, "空输出必须红")
    chk(compare_outputs(["a: 1"], os.path.join(d, "nope.txt"), "t") is not None,
        "缺期望文件必须红")
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="MATLAB→C 移植链路总门（TP1–TP9）")
    ap.add_argument("--selftest", action="store_true", help="两向自证")
    ap.add_argument("--fast", action="store_true",
                    help="跳过 C 编译与运行（发版快筛）")
    ap.add_argument("--require-c", action="store_true",
                    help="没有可用 C 编译器时判红（CI 用）")
    ap.add_argument("--sync-ledger", action="store_true",
                    help="按 C 后端结果同步台账状态")
    ap.add_argument("--write", action="store_true",
                    help="与 --sync-ledger 联用：真正写回台账")
    args = ap.parse_args(argv)
    global FAST
    if getattr(args, "fast", False):
        FAST = True
    if args.selftest:
        return _selftest()

    miss = _missing_inputs()
    if miss:
        print("check_translate_port: 缺输入（%s）" % ", ".join(miss))
        return 2

    probs, stats = run_checks(require_c=args.require_c)
    _m = stats.get("m2c") or {}
    if _m.get("available"):
        print("  [TP5] MIR 链路：函数 %d / 算子 %d / 未映射 %d / 编译 %s"
              % (_m.get("functions"), _m.get("ops"), _m.get("unmapped"),
                 "通过" if _m.get("compiled") else "未验（无编译器）"))
    print("  [统计] 算子 %d（已验证 %d / 未验证 %d）；适配器规则 %s"
          % (stats["operators"]["total"], stats["operators"]["verified"],
             stats["operators"]["unverified"],
             ", ".join(stats["rules_adapters"])))
    fb = stats["fidelity"]
    if fb["c_backend"] and fb["c_backend"].get("available"):
        if FAST:
            print("  [C 后端] %s；C 用例未跑（快检）"
                  % (fb["c_backend"].get("compiler"),))
        else:
            print("  [C 后端] %s；C 用例 %d/%d 通过"
                  % (fb["c_backend"].get("compiler"), stats["c_ok"],
                     stats["c_total"]))
    else:
        print("  [C 后端] 不可用（未找到 CC/gcc/clang/cc/cl）—— "
              "Python 参考实现已跑，C 编译验证待 CI")
    if args.sync_ledger:
        changes = sync_ledger(stats["fidelity_report"], write=args.write)
        for cid, old, new in changes:
            print("  [台账] %s: %s -> %s%s"
                  % (cid, old, new, "" if args.write else "（未写回，加 --write）"))
        if not changes:
            print("  [台账] 状态已与 C 后端一致")
    if probs:
        for p in probs:
            print("  - %s" % p)
        print("check_translate_port: %d 项不合规" % len(probs))
        return 1
    _mm = stats.get("m2c") or {}
    _dump_stats(stats)
    print("check_translate_port: OK（TP1–TP9 全绿；golden %d/%d；C %s；"
          "台账 %d 条；MIR 函数 %s / 算子 %s / 未映射 %s / 编译 %s）"
          % (stats["fidelity"]["passed"], stats["fidelity"]["total"],
             ("未跑（快检）" if FAST
              else "%d/%d" % (stats["c_ok"], stats["c_total"])),
             len(stats["ledger"]),
             _mm.get("functions", "-"), _mm.get("ops", "-"),
             _mm.get("unmapped", "-"),
             "通过" if _mm.get("compiled") else "未验"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
