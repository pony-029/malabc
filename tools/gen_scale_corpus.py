# -*- coding: utf-8 -*-
"""生成**规模语料**并跑一遍主线转换，输出「完全实现率」。

    python tools/gen_scale_corpus.py            # 生成 + 转换 + 统计
    python tools/gen_scale_corpus.py --keep     # 保留生成目录便于观察

## 它回答什么问题

「MATLAB → C 到底能转多少」—— 而**不能用编译通过率回答**：残缺的函数体
仍然是一段合法的 C，照样编得过。真正的读数是「生成物里还有没有
`MLC_UNIMPLEMENTED` / `TODO(...)`」。

## 语料的写法（三条，全是踩出来的）

1. **形状用 `% @m2c shape` 注释声明**（`arguments` 块在转换路径还不被支持）；
2. **二维对象声明两维**（`A(i,j)` 降线性下标要用 `rows = shape[0]`）；
3. **函数名不能当变量**：`y = abs(x)` 里的 `abs` 是函数；只有内建名算函数，
   其余（`A`/`a`/`x`）是变量 —— 否则会生成 `abs = [1]; y = abs(x);`。

## 为什么放进仓库

R879–R882 这四轮里，同样的语料我改了四次（函数名、`arguments`、一维、
二维），每次都在临时目录里 —— 于是**每轮都要重写一遍，且入口改名
（`matlabc.py --to-c` → `matlabc_toc.py`）时它静默失效**（rc=2）。
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))

import operators as O      # noqa: E402

TOC = os.path.join(ROOT, "matlabc_toc.py")

#: 拿标量当下标的算子：它们的 a/b 是下标，不是向量
INDEXY = {"OP-IDX2", "OP-IDX3", "OP-SLICE", "OP-MASK", "OP-SETIDX2",
          "OP-SETIDX3", "OP-SETSLICE"}
#: 名字本身就是标量的（循环变量、维度、阈值）
SCALARS = {"i", "j", "k", "n", "dim", "k2", "v", "s", "m"}
#: `x(a:b)` 的边界：用 1..3，所以 `x` 至少要有 3 个元素，否则边界越界
SLICEY = {"OP-SLICE", "OP-SETSLICE", "OP-MASK"}

BUILTINS = {
    "abs", "sqrt", "exp", "log", "log10", "sin", "cos", "tan", "floor",
    "ceil", "round", "mod", "rem", "min", "max", "sum", "prod", "mean",
    "median", "std", "var", "numel", "size", "length", "ndims", "find",
    "zeros", "ones", "eye", "cat", "sort", "any", "all", "reshape",
    "transpose", "dot", "cross", "norm", "inv", "det", "diag", "trace",
    "cumsum", "cumprod", "diff", "repmat", "horzcat", "vertcat",
    "squeeze", "permute", "isempty", "isnan", "isinf", "sign", "power",
}


def varnames(sample):
    """样本里的变量名 —— 只有**内建函数名**才被排除。"""
    out = []
    for m in re.finditer(r"\b([A-Za-z]\w*)\b(\s*\()?", sample):
        nm, call = m.group(1), m.group(2)
        if nm in ("y", "end"):
            continue
        if call and nm in BUILTINS:
            continue
        if nm not in out:
            out.append(nm)
    return out


def is_scalar(nm, op_id):
    return nm in SCALARS or (op_id in INDEXY and nm in ("a", "b", "i", "j"))


#: 会**改变结果长度**的算子：返回元素的个数不等于 n。
#:
#: * 拼接：`[a b]` / `[a; b]` 各取 n 个 → 2n；
#: * 集合运算 / 查找：结果 ≤ n（按 n 声明不会越界）；
#: * 标量结果：`size(x,dim)`、`x(2)` 都只给一个数；
#: * 列切片：`A(:,2:end)` 在 A 是 2×2 时取第 2 列 → 2 个元素。
Y_LEN = {"OP-HCAT": lambda n: 2 * n, "OP-VCAT": lambda n: 2 * n,
         "OP-CAT": lambda n: 2 * n, "OP-SETDIFF": lambda n: n,
         "OP-FIND": lambda n: n, "OP-FIND2": lambda n: n, "OP-FIND3": lambda n: n,
         "OP-INDEX": lambda n: 1, "OP-SIZE": lambda n: 1,
         "OP-COLRANGE": lambda n: 2}


def retname(sample):
    """样本里的**被赋值变量**就是函数的返回变量（`i = find(...)` 返回的是 `i`）。

    早前一律按 `y` 声明形状：`find` 这类样本的返回变量是 `i`，
    于是形状注解落在了一个不存在的 `y` 上，而 `i` 没有形状 → C 侧报错。
    """
    m = re.match(r"^\s*([A-Za-z]\w*)\s*=", sample)
    return m.group(1) if m else "y"


def make_func(op_id, sample, n, idx):
    name = "%s_%d_%d" % (op_id.lower().replace("-", "_"), n, idx)
    vs = varnames(sample)
    ann = []
    for v in vs:
        if is_scalar(v, op_id):
            continue
        if v.isupper():
            ann.append("%% @m2c shape %s 2,2" % v)      # 二维对象
        elif op_id in ("OP-HCAT", "OP-VCAT", "OP-TRANSPOSE"):
            # 这三类要求入参是**二维**：`mlc_op_hcat` 读 `a->rows`，
            # 一维数组的 rows/cols 语义与它不符（实测 C 侧 error）。
            ann.append("%% @m2c shape %s 1,%d" % (v, n))
        elif op_id in SLICEY and n < 3:
            ann.append("%% @m2c shape %s 3" % v)        # 边界 1:2 需要 3 个元素
        else:
            ann.append("%% @m2c shape %s %d" % (v, n))
    # 结果长度按算子族给（见 `Y_LEN`）—— 拼接是 2n、标量是 1、集合类 ≤ n。
    y_dim = Y_LEN.get(op_id, lambda k: max(k, 3 if op_id in SLICEY else k))(n)
    # 这几类的结果是**二维**的（拼接/转置/整列切片），声明成一维会让目标数组
    # 装不下（`mlc_array_init(y, 1, {6})` 之后再写 rows=1,cols=6 → MLC_ERR）。
    # R893 实测：`op_hcat_*/op_transpose_*/op_colrange_*` 的 C 侧 error 就是这个。
    y_shape2 = {"OP-HCAT": "1,%d" % (2 * n), "OP-VCAT": "2,%d" % n,
                "OP-TRANSPOSE": "%d,1" % n, "OP-COLRANGE": "2,1"}.get(op_id)
    # **把 lhs 统一改写成 `y`**：`find` 的样本是 `i = find(...)`，而 `i` 会被
    # 发射器当成"循环变量/i64 标量"（`is_loop_var`），于是返回变量 `i` 被按
    # 整型指针传，gcc 报 `incompatible type for argument 4 of mlc_op_find_alloc`。
    # 改名字不影响语义（`y = find(x>1)` 与 `i = find(x>1)` 等价），
    # 但避开了这条名字启发式。
    rn = retname(sample)
    body = sample.strip()
    if rn != "y":
        body = re.sub(r"^\s*%s\s*=" % re.escape(rn), "y =", body)
        rn = "y"
    if rn not in vs:                     # 返回变量同时也是形参时（`function x = f(x)`）不重复声明
        ann.append("%% @m2c shape %s %s" % (rn, y_shape2 or y_dim))
    return ("function %s = %s(%s)\n%s\n  %s\nend\n"
            % (rn, name, ", ".join(vs), "\n".join(ann), body))


def _head():
    """当前提交号（取不到就给空串 —— 读数比提交号重要）。"""
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                           stdin=subprocess.DEVNULL, timeout=60,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return r.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def generate(out_dir, limit=0):
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    made = 0
    ops = O.OPERATORS[:limit] if limit else O.OPERATORS
    for op in ops:
        sample = (op.get("sample") or "").strip()
        if not sample:
            continue
        # 下标类算子的样本里写着固定下标（`x(2)` / `a:b`），n=1 会让它越界
        # —— 那是**样本非法**，不是运行时缺陷（VM 报「下标越界：2 / 1」）。
        sizes = (2, 3, 7) if op["id"] in (INDEXY | SLICEY) else (1, 3, 7)
        for idx, n in enumerate(sizes):
            p = os.path.join(out_dir, "%s_%d_%d.m" % (
                op["id"].lower().replace("-", "_"), n, idx))
            io.open(p, "w", encoding="utf-8", newline="\n").write(
                make_func(op["id"], sample, n, idx))
            made += 1
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(description="规模语料：MATLAB → C 完全实现率")
    ap.add_argument("--keep", action="store_true", help="保留产物目录")
    ap.add_argument("--out", metavar="DIR", help="产物目录（默认临时目录）")
    ap.add_argument("--limit", type=int, metavar="N", default=0,
                    help="只取前 N 个算子（给门禁用的小样本，0=全部）")
    ap.add_argument("--no-record", action="store_true",
                    help="不写 flow/scale.json（小样本不该冒充全量读数）")
    ns = ap.parse_args(argv)

    base = ns.out or tempfile.mkdtemp(prefix="m2c_scale_")
    src_dir = os.path.join(base, "src_m")
    build = os.path.join(base, "build")
    made = generate(src_dir, limit=ns.limit)
    print("生成 .m 文件: %d" % made)

    if not os.path.isfile(TOC):
        print("缺主线入口：%s" % TOC, file=sys.stderr)
        return 2
    r = subprocess.run([sys.executable, TOC, src_dir, "-o", build],
                       cwd=ROOT, stdin=subprocess.DEVNULL, timeout=3600,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        print("转换失败 rc=%d：\n%s" % (
            r.returncode, r.stdout.decode("utf-8", "replace")[-600:]),
            file=sys.stderr)
        return r.returncode

    gen = os.path.join(build, "build", "gen", "src", "gen")
    cs = sorted(f for f in os.listdir(gen)) if os.path.isdir(gen) else []
    bad = []
    for f in cs:
        s = io.open(os.path.join(gen, f), encoding="utf-8",
                    errors="replace").read()
        if "MLC_UNIMPLEMENTED" in s:
            bad.append(f)
    ok = len(cs) - len(bad)
    print("生成 .c: %d ｜ **完全实现 %d (%.1f%%)** ｜ 残缺 %d"
          % (len(cs), ok, 100.0 * ok / max(1, len(cs)), len(bad)))

    if ns.no_record:
        print("（--no-record：不写 flow/scale.json）")
        if not ns.keep:
            shutil.rmtree(base, ignore_errors=True)
        return 0 if not bad else 1

    # 落盘读数：`project_status.build()` 会读它，进状态历史。
    # 带 `head` 是为了让"这个数是哪个提交量的"永远可查 —— 否则它和
    # 那些会自然过期的指标一样，看起来成立、实际早已对不上代码。
    try:
        import json
        import time
        rel = os.path.join(ROOT, "flow", "scale.json")
        io.open(rel, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"total": len(cs), "full": ok,
                        "rate": round(100.0 * ok / max(1, len(cs)), 1),
                        "bad": len(bad),
                        "head": _head()[:12],
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
                       ensure_ascii=False, indent=2) + "\n")
        print("读数已写入 flow/scale.json")
    except OSError as e:
        print("写 flow/scale.json 失败：%s" % e, file=sys.stderr)
    for f in bad[:6]:
        why = ""
        s = io.open(os.path.join(gen, f), encoding="utf-8", errors="replace").read()
        m = re.search(r"TODO\([a-z]+\): (.{0,60})", s)
        if m:
            why = m.group(1).strip()
        print("   ✗ %-28s %s" % (f, why))
    if not ns.keep:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
