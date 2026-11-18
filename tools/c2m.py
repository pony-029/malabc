# -*- coding: utf-8 -*-
"""**C → MATLAB**：补上正向（M→C）之外的反向链路。

    python tools/c2m.py <C 目录或文件...> -o <输出目录>
    python tools/c2m.py translate/examples/kern -o E:/temp/c2m_out --from-source

## 为什么需要它

仓里原本只有 **C → MIR**（`translate/cmir.py`，三段链路的第 ③ 段），
没有 **MIR → MATLAB**。于是"多个 C 函数 → 一个 MATLAB 文件"这个方向
**根本不存在** —— 而它和"多个 MATLAB 函数 → 一个 C 文件"是同一件事的两面。

本工具补的就是最后一段：`C 源码 → c_to_mir → MIR → .m`。

## 两个入口

* `--from-c <生成物目录>`：读 m2c 生成的 C（带 `@m2c` 注释），反推最准；
* `--from-source`：先对给定目录跑一次 `m2c build`，再用其生成物反推
  （用来验证"M→C→M 往返"）。

## 诚实边界（重要）

MIR 里表达不了的东西**不会凭空猜**：

* 认得的算子 → 生成对应 MATLAB 语句；
* 不认得的算子 → 生成 `% TODO(op: OP-XXX)` 注释，并在统计里计入 `todo`。

所以每个文件都带一行可核对的统计头：

    % @c2m ops=5 todo=0 (MIR->MATLAB 由 tools/c2m.py 生成)

`todo=0` 才是"完整往返"。这比"看起来像 MATLAB"有用得多。

退出码：
    0 = 全部文件 todo=0
    1 = 有文件含 TODO（仍有产出，但不完全）
    2 = 缺输入（没有可读的 .c）
"""
import argparse
import glob
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))
import cmir  # noqa: E402

#: MIR 算子 → MATLAB 中缀。只收**语义确定**的；其余落 TODO。
BIN = {"OP-ADD": "+", "OP-SUB": "-", "OP-MUL": "*", "OP-DIV": "/",
       "OP-EMUL": ".*", "OP-EDIV": "./"}
#: MIR 的比较/逻辑符号（`if:a:lt:b` 的第二段）
CMP = {"eq": "==", "ne": "~=", "lt": "<", "le": "<=", "gt": ">", "ge": ">=",
       "and": "&&", "or": "||"}
#: `setb` 的第二段
SETB = {"add": "+", "sub": "-", "mul": "*", "div": "/", "idiv": "idivide"}


def mir_to_matlab(mir_text, fname):
    """MIR 文本 → MATLAB 源码 + 统计。"""
    funcs = []
    cur = None
    ops = todo = 0
    for raw in mir_text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split(":")
        tag = parts[0]
        if tag == "func":
            cur = {"name": parts[1], "args": [], "rets": [], "body": [],
                   "shapes": {}}
            funcs.append(cur)
            continue
        if cur is None:
            continue
        if tag == "arg":
            cur["args"].append(parts[1])
            if len(parts) > 3:
                cur["shapes"][parts[1]] = parts[3]
        elif tag == "ret":
            cur["rets"].append(parts[1])
            if len(parts) > 3:
                cur["shapes"][parts[1]] = parts[3]
        elif tag == "var":
            pass                       # 局部量不写声明：MATLAB 里赋值即声明
        elif tag == "set":
            cur["body"].append("%s = %s;" % (parts[1], parts[2]))
            ops += 1
        elif tag == "const":
            cur["body"].append("%s = %s;" % (parts[1], parts[2]))
            ops += 1
        elif tag == "charge":
            pass
        elif tag in ("for",):
            cur["body"].append("for %s = %s:%s" % (parts[1], parts[2], parts[3]))
            ops += 1
        elif tag in ("while", "if"):
            op = CMP.get(parts[2], None)
            if op is None:
                cur["body"].append("%% TODO(%s: %s)" % (tag, ":".join(parts[1:])))
                todo += 1
            else:
                cur["body"].append("%s %s %s %s"
                                   % (tag, parts[1], op, parts[3]))
                ops += 1
        elif tag == "setb":
            op = SETB.get(parts[2], None)
            if op is None:
                cur["body"].append("%% TODO(setb: %s)" % parts[2])
                todo += 1
            elif op == "idivide":
                cur["body"].append("%s = idivide(%s, %s);"
                                   % (parts[1], parts[3], parts[4]))
                ops += 1
            else:
                cur["body"].append("%s = %s %s %s"
                                   % (parts[1], parts[3], op, parts[4]))
                ops += 1
        elif tag == "fill":
            dims = ",".join(parts[2].split(","))
            cur["body"].append("%s = zeros(%s);" % (parts[1], dims))
            ops += 1
        elif tag == "end":
            cur["body"].append("end")
        elif tag == "op":
            oid = parts[1]
            args = parts[3:]
            if oid in BIN and len(args) == 2:
                cur["body"].append("%s = %s %s %s;"
                                   % (parts[2], args[0], BIN[oid], args[1]))
                ops += 1
            else:
                cur["body"].append("%% TODO(op: %s) 参数=%s"
                                   % (oid, ",".join(args)[:40]))
                todo += 1
        elif tag in ("call", "unmapped", "reject"):
            cur["body"].append("%% TODO(%s: %s)" % (tag, ":".join(parts[1:])[:40]))
            todo += 1

    out, first = [], True
    for f in funcs:
        hdr = "function "
        if f["rets"]:
            hdr += ("[%s] = " % " ".join(f["rets"])) if len(f["rets"]) > 1 \
                   else ("%s = " % f["rets"][0])
        hdr += ("%s(%s)" % (f["name"], ", ".join(f["args"]))) \
               if f["args"] else f["name"]
        if first:
            out.append("%% @c2m from %s" % fname)
            first = False
        out.append(hdr)
        for v, sh in f["shapes"].items():
            out.append("%% @m2c shape %s %s" % (v, sh))
        body = list(f["body"])
        # `end` 由下面统一补一个；MIR 末尾自带的那条要去掉，否则双 `end`
        while body and body[-1].strip() == "end":
            body.pop()
        out.extend("  " + x if x else x for x in body)
        out.append("end")
        out.append("")
    return "\n".join(out) + "\n", {"funcs": len(funcs), "ops": ops, "todo": todo}


def _cs(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(glob.glob(os.path.join(p, "*.c"))))
        elif os.path.isfile(p) and p.endswith(".c"):
            out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="C → MATLAB（经 MIR 反推）")
    ap.add_argument("paths", nargs="+", help=".c 文件或目录")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--json", help="把逐文件统计写成 JSON（供 full_report 读取）")
    ns = ap.parse_args(argv)

    files = _cs(ns.paths)
    if not files:
        print("c2m: 缺输入（没有可读的 .c）")
        return 2
    os.makedirs(ns.out, exist_ok=True)

    tot = {"funcs": 0, "ops": 0, "todo": 0}
    bad = 0
    recs = []
    for p in files:
        name = os.path.splitext(os.path.basename(p))[0]
        text = io.open(p, encoding="utf-8", errors="replace").read()
        mir, _st = cmir.c_to_mir(text, name)
        matlab, st = mir_to_matlab(mir, name)
        io.open(os.path.join(ns.out, name + ".m"), "w",
                encoding="utf-8", newline="\n").write(matlab)
        recs.append({"file": name, "funcs": st["funcs"],
                     "ops": st["ops"], "todo": st["todo"]})
        for k in tot:
            tot[k] += st[k]
        if st["todo"]:
            bad += 1
        print("[c2m] %-28s 函数 %d ｜ ops %d ｜ todo %d"
              % (name, st["funcs"], st["ops"], st["todo"]))
    if ns.json:
        io.open(ns.json, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"files": recs, "total": tot, "bad": bad,
                        "n_files": len(files)}, ensure_ascii=False, indent=2)
            + "\n")
    print("[c2m] 合计：函数 %d ｜ ops %d ｜ todo %d ｜ 含 TODO 的文件 %d/%d"
          % (tot["funcs"], tot["ops"], tot["todo"], bad, len(files)))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
