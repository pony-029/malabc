# -*- coding: utf-8 -*-
"""`check`：**只诊断、不生成代码**。回答"这个函数能不能转，卡在哪一行，怎么改"。

## 为什么需要它（设计文档 docs/DESIGN_TOPLEVEL.md 阶段 1）

工具在自建语料上 58/58，但在真实大库上几乎为零。此前的唯一反馈是
`unmapped: ...` 这样的内部行 —— 用户看不出**是自己的写法问题，还是工具不支持**。

本命令把 MIR 里的归因变成人能读的三件事：

    第 12 行  [struct]  opt.x = 1;
              → 把结构体字段拆成显式变量传入

## 关键设计（来自 L2 测量）

一个函数要能转，必须补齐它身上出现的**全部**卡点类别。
所以诊断除了逐行列出，还会算出：**"先修哪一类，能一次消掉最多处"** ——
这直接对应"离能转还差多远"，比"共多少条未映射"有用得多。

## 用法

    python translate/check.py <x.m> [--json]

退出码：0 = 可以生成；1 = 有阻塞；2 = 输入/环境问题。
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(HERE, "mir.py")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

#: 每类卡点 → 给用户的**可行动**建议。键与 mir.py 的 `# why:` 标签一致。
ADVICE = {
    "struct": "结构体用法。把字段拆成显式变量/形参传入（本工具不做 struct 类型建模）",
    "cell": "元胞数组。改成定长数值数组，或把元素拆成独立变量",
    "call2": "调用了工具不认识的函数。换成已支持的算子，或自己展开成逐元素运算",
    "other": "未归类的语句。多为字符串/类型转换（char/num2str/class 等），数值代码里通常不需要",
    "strlit": "字符串字面量相关（对外提示、拼接、regexp 等）。数值通路不需要，删掉即可",
    "cond": "if/while 的条件含未支持的形态（`&&`/`||`、调用、结构体字段）",
    "control": "控制流形态未支持（switch/case、try/catch、break/continue 等）",
    "shadowed": "与内置函数重名，工具无法判断该调谁。改个变量名即可",
    "idx2": "二维下标但形状未知。给变量加 `% @m2c shape r,c` 注解",
    "nested": "表达式里嵌套调用。先拆成独立语句再算",
    "blockmarker": "块标记（else/otherwise）找不到所属块，通常是上一行 if 没被识别",
    "misc": "其它",
}


def _run(cmd):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=300,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def parse_mir(text):
    """从 MIR 提取：函数名、算子数、签名拒绝、逐条未映射（含源码行号与类别）。"""
    funcs, ops, rejects, bad = 0, 0, [], []
    cur_src, why = 0, "misc"
    cur_func = None
    #: 每个函数的形参 —— 注解建议只对**形参**成立（局部 struct 会另行处理）
    args_of = {}
    for raw in text.splitlines():
        ln = raw.rstrip("\n")
        if ln.startswith("func:"):
            funcs += 1
            cur_func = ln[5:].strip()
            args_of.setdefault(cur_func, [])
            cur_src, why = 0, "misc"
        elif ln.startswith("arg:") and cur_func:
            args_of[cur_func].append(ln.split(":")[1].strip())
        elif ln.startswith("# src:"):
            try:
                cur_src = int(ln[6:].strip())
            except ValueError:
                cur_src = 0
        elif ln.startswith("# why:"):
            why = ln[6:].strip()
        elif ln.startswith("op:"):
            ops += 1
        elif ln.startswith("reject:"):
            for r in ln[7:].split(","):
                if r.strip():
                    rejects.append(r.strip())
        elif ln.startswith("unmapped:"):
            bad.append({"line": cur_src, "kind": why,
                        "text": ln[9:].strip(), "func": cur_func})
            why = "misc"
    return funcs, ops, rejects, bad, args_of


def diagnose(path):
    """返回一个诊断结果字典。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    d = WORK if os.path.isdir(WORK) else tempfile.gettempdir()
    os.makedirs(d, exist_ok=True)
    mir = os.path.join(d, "chk_" + stem + ".mir")
    # `M2C_MIR_ARGS` 允许切到另一条 MIR 生成路径（如 `--hir-emit`），
    # 用于**对拍诊断**：两条路径的诊断必须逐字一致，否则"行号/类别"就会随默认值漂移。
    # 默认空 —— 与直接调用 `mir.py` 的行为完全相同。
    _extra = (os.environ.get("M2C_MIR_ARGS") or "").split()
    r = _run([sys.executable, MIR_PY, path, "-o", mir] + _extra)
    if r.returncode != 0 or not os.path.isfile(mir):
        msg = r.stdout.decode("utf-8", "replace")
        kind = "no_function" if ("没有识别到 function" in msg
                                 or "没有识别到函数" in msg) else "parse_error"
        return {"file": path, "status": kind, "detail": msg.strip()[-300:]}
    text = io.open(mir, encoding="utf-8").read()
    funcs, ops, rejects, bad, args_of = parse_mir(text)

    by_kind = {}
    for b in bad:
        by_kind.setdefault(b["kind"], []).append(b)
    # 「先修哪一类」：消掉它就能让函数离可转最近 —— 按"该类涉及的函数数"排，
    # 相同时按条数排（与 docs/DESIGN_TOPLEVEL.md 的 L2 判据一致）
    rank = sorted(by_kind.items(),
                  key=lambda kv: (-len({b["func"] for b in kv[1]}), -len(kv[1])))

    sources = {}
    try:
        lines = io.open(path, encoding="utf-8", errors="replace").read().splitlines()
        for i, s in enumerate(lines, 1):
            sources[i] = s.strip()
    except OSError:
        pass

    return {
        "file": path,
        "status": "ok" if (not bad and not rejects) else "blocked",
        "funcs": funcs, "ops": ops,
        "rejects": rejects, "blockers": bad,
        "by_kind": {k: len(v) for k, v in by_kind.items()},
        "rank": [(k, len(v), len({b["func"] for b in v})) for k, v in rank],
        "sources": sources,
        "annotations": suggest_fields(bad, args_of),
    }


#: `X.f` —— 结构体字段访问
_DOT = re.compile(r"([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)")
#: `X.f{...}` —— 元胞字段：那不是"一组标量"，声明成形参语义会错
_CELL_FIELD = re.compile(r"([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*\{")


def suggest_fields(bad, args_of):
    """从阻塞语句里**建议** `% @m2c fields s.f` 注解。

    只对**形参**成立（局部 struct 由 mir.py 自行展开，不需要注解）；
    `s.f{...}`（元胞字段）不建议 —— 它不是"一组标量"，强行声明会改变语义。

    返回 [(函数名, 注解行列表, 跳过原因或空串)]。
    """
    per_func = {}
    for b in bad:
        fn = b["func"]
        if not fn:
            continue
        entry = per_func.setdefault(fn, {"fields": set(), "cell": set(), "args": args_of.get(fn, [])})
        for host, fld in _DOT.findall(b["text"]):
            if host in entry["args"]:
                entry["fields"].add((host, fld))
        for host, fld in _CELL_FIELD.findall(b["text"]):
            entry["cell"].add((host, fld))

    out = []
    for fn, e in per_func.items():
        cellf = set(e["cell"])
        usable = sorted(f for f in e["fields"] if f not in cellf)
        if not usable:
            continue
        lines = ["%% @m2c fields %s.%s" % (h, f) for h, f in usable]
        note = ""
        if cellf:
            note = "%d 个元胞字段（%s）未声明：语义不同" % (
                len(cellf), ", ".join("%s.%s" % t for t in sorted(cellf)[:2]))
        out.append((fn, lines, note))
    return out


#: 语句级卡点里**属于本工具边界**（不是"写法要改"）的类别。
#: 判据：这类语句即便改了写法也仍是同一件事 —— 只能不做。
_BOUNDARY_KINDS = {"strlit"}
#: 签名级拒绝的**改写动作**（用户可以照做）。
_SIG_FIX = {
    "cell": "把元胞形参改成定长数值参数（或拆成多个形参）",
    "struct": "把结构体形参改成显式字段参数（或加 `% @m2c fields s.a` 声明）",
    "varargin": "把可变参数改成显式形参",
    "varargout": "把可变输出改成显式返回值",
}


def _verdict(res):
    """把"不能生成"分成**该动什么**的一句话。

    实测（jsonlab + export_fig，98 个失败）：绝大多数卡在**签名层**
    （`cell,struct` 59 ／ `varargin,cell,struct` 46 ／ `struct` 36 …）。
    那时用户最想知道的是：改签名值不值得 —— 所以要把"改完还剩多少"一起给出。
    """
    by_kind = res.get("by_kind") or {}
    boundary = sum(v for k, v in by_kind.items() if k in _BOUNDARY_KINDS)
    fixable = sum(by_kind.values()) - boundary
    rej = sorted(set(res.get("rejects") or []))

    if rej:
        acts = "；".join(_SIG_FIX.get(r, r) for r in rej)
        tail = ("改完还剩 %d 条语句级卡点（其中 %d 条属于本工具边界，改了也不支持）"
                % (fixable + boundary, boundary)) if (fixable + boundary) else "改完即可生成"
        return "**先改签名** —— %s。%s。" % (acts, tail)
    if fixable:
        return ("**改写法** —— 有 %d 条语句在支持范围外但可改写（见下方逐行）；"
                "另有 %d 条属于本工具边界。" % (fixable, boundary))
    return ("**超出边界** —— 阻塞全部属于本工具不支持的语言特性（如字符串字面量），"
            "改写法也无法转换。")


def render(res):
    out = []
    name = os.path.basename(res["file"])
    if res["status"] == "no_function":
        out.append("%s → 跳过：该文件没有顶层 function（脚本或纯文档）" % name)
        return "\n".join(out)
    if res["status"] == "parse_error":
        out.append("%s → 源解析失败：%s" % (name, res.get("detail", "")[-160:]))
        return "\n".join(out)

    if res["status"] == "ok":
        out.append("%s → **可以生成 C**（函数 %d ｜ 算子 %d ｜ 0 阻塞）"
                   % (name, res["funcs"], res["ops"]))
        out.append("  下一步：`python tools/walkthrough.py %s` 看完整转换过程" % res["file"])
        return "\n".join(out)

    out.append("%s → **不能生成**（函数 %d ｜ 算子 %d ｜ 未映射 %d ｜ 签名拒绝 %d 类）"
               % (name, res["funcs"], res["ops"], len(res["blockers"]),
                  len(res["rejects"])))

    # 【结论】先给一句可执行的判断，再给明细 —— 明细很长，而人只想先知道"该动哪"
    out.append("")
    out.append("【结论】" + _verdict(res))

    if res["rejects"]:
        out.append("")
        out.append("【签名级】整个函数被拒（语句层都没开始）")
        # 同一文件里每个函数各有一条 reject，去重并按出现次数展示
        cnt = {}
        for r in res["rejects"]:
            cnt[r] = cnt.get(r, 0) + 1
        for r, n in sorted(cnt.items(), key=lambda kv: -kv[1]):
            hint = {"varargin": "把可变参数改成显式形参",
                    "varargout": "把可变输出改成显式返回值",
                    "cell": "元胞形参改成数值数组",
                    "struct": "结构体形参改成显式数值参数"}.get(r, "见 docs 的边界说明")
            times = ("（%d 个函数）" % n) if n > 1 else ""
            out.append("  - %-10s%s → %s" % (r, times, hint))

    out.append("")
    out.append("【语句级】按源码行：")
    shown = 0
    for b in sorted(res["blockers"], key=lambda x: (x["line"], x["kind"])):
        if b["line"] <= 0:
            continue
        if shown >= 12:
            out.append("  … 另有 %d 处（用 --json 看全部）"
                       % (len(res["blockers"]) - shown))
            break
        src = res["sources"].get(b["line"], "")
        out.append("  第 %-4d 行 [%-10s] %s" % (b["line"], b["kind"], src[:60]))
        shown += 1
    no_line = [b for b in res["blockers"] if b["line"] <= 0]
    if no_line:
        out.append("  （另有 %d 处没有行号信息：多为函数体外的语句）" % len(no_line))

    anns = res.get("annotations") or []
    if anns:
        out.append("")
        out.append("【可以加的注解】声明这些形参是「一组标量」，即可把它们展开成独立形参：")
        for fn, lines, note in anns[:3]:
            out.append("  function %s：" % fn)
            for ln in lines[:6]:
                out.append("      " + ln)
            if len(lines) > 6:
                out.append("      … 另有 %d 行" % (len(lines) - 6))
            if note:
                out.append("      注意：%s" % note)
        out.append("  用法：把上面几行贴在对应 function 行之后，重跑即可。")

    out.append("")
    out.append("【先修哪里】按「消掉它能让多少函数更接近可转」排序：")
    for kind, cnt, nfn in res["rank"][:4]:
        out.append("  %-12s %4d 处 / 影响 %d 个函数  → %s"
                   % (kind, cnt, nfn, ADVICE.get(kind, ADVICE["misc"])))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="诊断一个 .m 能不能转成 C（不生成代码）")
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true", help="输出机器可读结果")
    ap.add_argument("--annotate", nargs="?", const="-", default=None,
                    metavar="OUT.m",
                    help="把建议的 `%% @m2c fields` 注解写进一个副本"
                         "（不给文件名则打印到标准输出）")
    a = ap.parse_args()
    if not os.path.isfile(a.path):
        print("找不到文件：%s" % a.path)
        return 2
    res = diagnose(a.path)

    if a.annotate is not None:
        anns = res.get("annotations") or []
        if not anns:
            print("这个文件不需要 struct 注解（没有「形参 struct」形态的阻塞）")
            return 0
        block = []
        for fn, lines, _note in anns:
            block.extend(lines)
        if a.annotate == "-":
            print("\n".join(block))
            return 0
        # 写副本：在每个 function 行后插入对应注解
        src = io.open(a.path, encoding="utf-8", errors="replace").read().split("\n")
        by_fn = {fn: lines for fn, lines, _n in anns}
        out_lines, cur = [], None
        for ln in src:
            out_lines.append(ln)
            st = ln.lstrip()
            if st.startswith("function"):
                m = re.search(r"=\s*([A-Za-z_]\w*)\s*\(|function\s+([A-Za-z_]\w*)\s*\(", st)
                cur = (m.group(1) or m.group(2)) if m else None
                if cur in by_fn:
                    out_lines.extend(by_fn[cur])
        io.open(a.annotate, "w", encoding="utf-8", newline="\n").write("\n".join(out_lines))
        print("已写出带注解的副本：%s（%d 行注解）" % (a.annotate, len(block)))
        return 0
    if a.json:
        res.pop("sources", None)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(render(res))
    return 0 if res["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
