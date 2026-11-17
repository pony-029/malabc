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
#: 只收**真正拿标量当下标**的算子。`OP-INDEX` 也在此列：它的样本是 `x(2)`，
#: 用 n=1 的尺寸会越界（C 侧 MLC_ERR、VM 报"下标越界"）—— 那是样本非法。
#: 注意 `OP-SETIDX` 也在此列：它的样本是 `y(2) = 3`，用 n=1 的尺寸会让
#: **写**越界（C 侧 MLC_ERR、VM 按 0 撑开到 2 格）—— 那是样本非法。
#: R897 漏了 `OP-INDEX`、R908 又漏了 `OP-SETIDX`：同一个类的错误犯了两次，
#: 所以这里按"样本里出现数字下标"逐条核对，而不是凭印象挑。
INDEXY = {"OP-INDEX", "OP-IDX2", "OP-IDX3", "OP-SLICE", "OP-MASK",
          "OP-SETIDX", "OP-SETIDX2", "OP-SETIDX3", "OP-SETSLICE"}
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
        elif op_id in ("OP-VCAT", "OP-TRANSPOSE"):
            # `[a; b]` 与 `x.'` 的结果是**二维**，入参也跟着按行向量声明；
            # 而 `OP-HCAT` **不在其列** —— 它的 C 实现只认一维（见上）。
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
    # `mlc_op_hcat` 明确**只做一维**（`a->ndim != 1 → MLC_ERR`，注释写着
    # "2-D 的 `[a b]` 是按列拼，与这里不是一件事"）—— 所以它**不能**给二维
    # 声明，否则必错。R893 我曾把它改成 `1,6`，反而把它弄坏了。
    #
    # ⚠ **未解的产品缺陷**（R894 定位，待修）：即使按一维声明 `y 6`，生成物仍是
    #     /* WARN(shape): y 声明 [6] 与推断 [3] 不一致，按推断执行 */
    #     mlc_array_init(y, MLC_F64, 1, (int64_t[]){3});
    # 而 `emit.rs` 里 OP-HCAT 的推断写的是 `x[0] + y[0]`（= 6），不该得出 3。
    # 也就是说：**显式注解被"推断"覆盖**，而那个推断在拼接这一格上错了。
    # 结果 `mlc_op_hcat` 看到 `numel(out)=3 != sh=6` → MLC_ERR（C 侧 error 的成因）。
    # 修这里之前，`op_hcat_*` 的三个 C 侧 error 会一直在。
    y_shape2 = {"OP-VCAT": "2,%d" % n,
                "OP-TRANSPOSE": "%d,1" % n, "OP-COLRANGE": "2,1",
                # `A(i,j)=v` 改的是**入参**，样本本身从不给返回变量赋值 ——
                # 于是函数返回一个从未写过的 `y`，两侧都没意义可比
                # （实测：C 侧 error、VM 干脆不打印 → 3 个函数"从未被比较"）。
                # 补一句 `y = A;` 才是真实写法：写完再返回。
                "OP-SETIDX2": "2,2"}.get(op_id)
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
    # `y(2) = 3` 这类样本**没有入参**，而 C 驱动的构造器需要"输入形状"才能建出
    # 被写的数组 —— 于是它打印 `skipped (no shape)`，这 6 个函数从未被比较过
    # （R905 实测：仅 VM 3 个 + 仅 C 3 个）。补一行初始化让目标先有形状，
    # 这也是真实 MATLAB 代码的写法（先用 zeros 建数组再按下标写）。
    if op_id == "OP-SETIDX2":
        body = "%s\n  y = A;" % body
    # ⚠ 试过给 `y(2)=3` 补一行 `y = zeros(1,4)` 让驱动能构造目标（R905）：
    # 效果是"未比对"从 6 降到 3，但立刻多出 3 个 C 侧 error（`setidx2` 的
    # 语义与 zeros 建出来的目标对不上），净收益为负，已回退。
    # 要让这 6 个真正进入比对，得改**驱动构造器**（按返回变量生成初值），
    # 而不是在语料里假装它已经初始化过。
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


def numeric_compare(base, gen_root):
    """**按函数名**对齐 VM 与编译产物，返回 (一致率, 统计 dict) 或 None。

    为什么不能按行号比：C 驱动会跳过/报错某些函数（`skipped (no shape)`），
    而 VM 全跑 —— 两边的行不是同一批对象，按行号对齐从第一个差异起就全错位
    （R889 实测只得到 24.5% 的假读数）。

    为什么按**数值**比而不是字符串：VM 用最短往返表示（`0.5403023058681398`）、
    C 用 `%.17g`（`0.54030230586813977`），同一个数会被判成不同 ——
    R890 实测：字符串口径 79.1%，数值口径 89.5%，差的 16 个全是格式。
    """
    m2c = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
    mir = os.path.join(base, "build", ".m2c", "project.mir")
    if not (os.path.isfile(m2c) and os.path.isfile(mir)):
        return None
    g = os.path.join(gen_root, "src")
    inc = os.path.join(gen_root, "include")
    rt = os.path.join(ROOT, "c_runtime", "src")
    exe = os.path.join(base, "numapp.exe")
    cc = subprocess.run(["gcc", "-std=c99", "-O1", "-o", exe,
                         os.path.join(g, "gen.c"), os.path.join(g, "main.c"),
                         os.path.join(rt, "mlc_runtime.c"),
                         os.path.join(rt, "mlc_ops.c"),
                         "-I", inc, "-I", os.path.join(ROOT, "c_runtime", "include")],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=900)
    if cc.returncode != 0:
        return None

    vm = subprocess.run([m2c, "run", "--tag-func", "--mir", mir],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=900).stdout.decode(
                            "utf-8", "replace")
    run = subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=600).stdout.decode(
                             "utf-8", "replace")

    def parse(txt):
        out = {}
        for ln in txt.splitlines():
            m = re.match(r"^\s*([A-Za-z_]\w*):\s*(.*)$", ln)
            if not m:
                continue
            name, val = m.group(1), m.group(2).strip()
            if name == "n" or "assumed" in val or "skipped" in val:
                continue
            out.setdefault(name, val)
        return out

    A, B = parse(vm), parse(run)
    _bad_names = []          # 真不同的函数名（R909：只报计数等于没报）
    _cerr_names = []         # C 侧 error 的函数名

    # **空结果的打印约定不同**（R905 实测）：
    # * C 驱动：`printf("名字:")` 后无元素 → 输出一行 `名字:`（值串为空）
    # * VM：`if !s.is_empty() { println! }` —— **空结果干脆不打印**
    # 于是 `find` 无命中、`setdiff` 无差集这类函数在一侧"消失"，
    # 被误记成"未参与比对"。它们其实**两边都算出了空**，应当算一致。
    #
    # 归一：某一侧缺失、而另一侧的值是空串 → 视为双方都是空结果。
    empty_ok = 0
    for nm in sorted(set(A) ^ set(B)):
        present = A.get(nm) if nm in A else B.get(nm)
        if (present or "").strip() == "":
            empty_ok += 1
            A.setdefault(nm, "")
            B.setdefault(nm, "")

    common = sorted(set(A) & set(B))
    same = fmt = bad = cerr = 0
    for n in common:
        if B[n].startswith("error"):
            cerr += 1
            _cerr_names.append(n)
            continue
        try:
            a = [float(x) for x in A[n].replace(",", " ").split()]
            b = [float(x) for x in B[n].replace(",", " ").split()]
        except ValueError:
            if A[n] == B[n]:
                same += 1
            else:
                bad += 1
                _bad_names.append(n)
            continue
        if len(a) != len(b):
            bad += 1
            _bad_names.append(n)
        elif all(abs(x - y) <= 1e-9 * max(1.0, abs(y)) for x, y in zip(a, b)):
            if A[n] == B[n]:
                same += 1
            else:
                fmt += 1          # 数值相同、仅打印精度差
        else:
            bad += 1
            _bad_names.append(n)
    total = len(common)
    rate = 100.0 * (same + fmt) / total if total else 0.0
    # **没被比到的函数也要数出来**（R904）。`100%` 只是在"两边都输出了"的
    # 交集上成立；若某一侧压根没打印，那个函数就**从未被比较过** ——
    # 不把这件事报出来，读数会显得比实际更强。
    only_vm = sorted(set(A) - set(B))
    only_c = sorted(set(B) - set(A))
    return rate, {"common": total, "identical": same, "fmt_only": fmt,
                  "mismatch": bad, "c_error": cerr,
                  "empty_both": empty_ok,
                  # 名字比计数有用：只知道"有 2 个不同"没法开工（R909）
                  "mismatch_names": _bad_names[:8],
                  "c_error_names": _cerr_names[:8],
                  "only_vm": len(only_vm), "only_c": len(only_c),
                  "only_vm_names": only_vm[:5], "only_c_names": only_c[:5]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="规模语料：MATLAB → C 完全实现率")
    ap.add_argument("--keep", action="store_true", help="保留产物目录")
    ap.add_argument("--out", metavar="DIR", help="产物目录（默认临时目录）")
    ap.add_argument("--limit", type=int, metavar="N", default=0,
                    help="只取前 N 个算子（给门禁用的小样本，0=全部）")
    ap.add_argument("--no-record", action="store_true",
                    help="不写 flow/scale.json（小样本不该冒充全量读数）")
    ap.add_argument("--numeric", action="store_true",
                    help="额外跑「VM vs 编译产物」的**按名数值比对**（需要 gcc，约 1 分钟）")
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

    num = None
    if ns.numeric:
        # `gen` 是 `<root>/src/gen`（.c 所在），而 `numeric_compare` 要的是
        # `<root>`（下面有 `src/` 与 `include/`）—— 这里少上溯一级就会
        # 找不到 `gen.c` / `main.c`，表现为"缺 m2c / 编译失败"（R901 实测）。
        gen_root = os.path.dirname(os.path.dirname(gen))
        got = numeric_compare(base, gen_root)
        if got is None:
            print("[numeric] 跳过：缺 m2c / project.mir / gcc 编译失败")
        else:
            rate, st = got
            num = st
            print("[numeric] 按名比对 %d 个函数 ｜ **数值一致率 %.1f%%**"
                  " ｜ 字面同 %d ｜ 仅格式差 %d ｜ 真不同 %d ｜ C 侧 error %d"
                  % (st["common"], rate, st["identical"], st["fmt_only"],
                     st["mismatch"], st["c_error"]))
            if st.get("empty_both"):
                print("  （其中 %d 个两边都是**空结果**：C 打印 `名字:`、VM 不打印空行 —— "
                      "已按一致处理）" % st["empty_both"])
            if st.get("only_vm") or st.get("only_c"):
                print("  ⚠ 未参与比对：仅 VM 有 %d 个 %r ｜ 仅 C 有 %d 个 %r"
                      "（这些函数**从未被比较过**，一致率不含它们）"
                      % (st.get("only_vm", 0), st.get("only_vm_names"),
                         st.get("only_c", 0), st.get("only_c_names")))
            num["rate"] = round(rate, 1)

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
                        # 两个后端的一致性也是读数的一部分（R899 入仓）：
                        # 只看"完全实现"会漏掉"两边算得不一样"这件事。
                        "numeric": num,
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
