# -*- coding: utf-8 -*-
"""**相互转换**：一条命令跑完 `MATLAB → MIR → {C, MATLAB'} → 数值比对`。

## 这条命令回答的问题

工具此前的能力散在四个模块里（`mir` / `m2c` / `cmir` / `unmir`），
但没有人能从一条命令看出"**它到底能不能把这段 MATLAB 转出去、再转回来、且算得一样**"。

本命令把两件事同时验证：

| 方向 | 路径 | 判据 |
|---|---|---|
| MATLAB → C | `.m → MIR → gen.c → gcc → 运行` | 跑出的数与参考值一致 |
| C → MATLAB | `.m → MIR → .m'`（回译） | 回译版算出的数与参考值一致 |

两个方向都过，才叫"可相互转换"。

## 用法

    python translate/roundtrip.py <x.m|目录> [--all]

退出码：0 = 全部通过；1 = 有函数未通过；2 = 环境问题（缺 m2c/gcc/Octave）。
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from translate import unmir as U            # noqa: E402
from translate import mir_eval               # noqa: E402
import tools.parity_report as PR             # noqa: E402
import tools.numeric_expected as NE          # noqa: E402

MIR_PY = os.path.join(HERE, "mir.py")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
RT = os.path.join(ROOT, "c_runtime")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def _run(cmd, timeout=300, cwd=None):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=timeout, cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _norm(s):
    return " ".join((s or "").split())


def _values(cli, funcs, addpath, workdir, timeout):
    """用 Octave 跑一个函数，返回值串或标记。"""
    drv = os.path.join(workdir, "drv.m")
    io.open(drv, "w", encoding="utf-8", newline="\n").write(PR._driver(funcs))
    try:
        rc, out = PR._run([cli, "--no-gui", "--quiet", "--eval",
                           "addpath('%s'); run('%s')"
                           % (addpath.replace("\\", "/"), drv.replace("\\", "/"))],
                          cwd=workdir, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "hang"
    if rc != 0:
        return "error"
    got = PR._c_lines(out)
    f = funcs[0].name
    return got[f].split(": ", 1)[1].strip() if f in got else "missing"


def _arg_shapes(mir_path):
    """从 MIR 的 `arg:` 行取形参形状 → `"x=4;y=2,3"`（供 `--shape` 覆盖）。

    回译出的 `.m'` 往往没有 `% @m2c shape` 注解；不覆盖的话两侧**输入不同形**，
    会被误判成"回译算错"（实测 5 个函数因此假红）。
    """
    if not os.path.isfile(mir_path):
        return ""
    out = []
    for ln in io.open(mir_path, encoding="utf-8", errors="replace"):
        if not ln.startswith("arg:"):
            continue
        p = ln.strip().split(":")
        if len(p) < 3:
            continue
        name, dims = p[1], p[-1]
        if dims.replace(",", "").isdigit():
            out.append("%s=%s" % (name, dims))
    return ";".join(out)


def _vm_values(mir_path, shape_override=""):
    """用 Rust VM 算 MIR 的数值。VM 说"不支持/未实现"时返回 None（**不猜**）。

    这是自证的首选路径：R696 起 VM 在语料上与 Octave 58/58 一致，
    且不用起解释器进程，快一个数量级。
    """
    if not os.path.isfile(mir_path):
        return None
    cmd = [M2C, "run", "--mir", mir_path]
    if shape_override:
        cmd += ["--shape", shape_override]
    r = _run(cmd, timeout=60)
    out = r.stdout.decode("utf-8", "replace").strip()
    if ("不支持" in out) or ("未实现" in out) or ("error（" in out) or ("skip（" in out):
        return None
    parts = [ln.split(":", 1)[1].strip() for ln in out.splitlines() if ":" in ln]
    if not parts:
        return None
    return " | ".join(parts) if len(parts) > 1 else parts[0]


def roundtrip_one(path, cli, d):
    """跑单个文件的四段链路，返回记录。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    rec = {"name": stem, "src": path, "mir": "skip", "to_c": "skip",
           "to_m": "skip", "ref": "", "c_out": "", "m_out": "", "note": ""}

    mir = os.path.join(d, stem + ".mir")
    r = _run([sys.executable, MIR_PY, path, "-o", mir])
    if r.returncode != 0 or not os.path.isfile(mir):
        rec["note"] = "源解析失败"
        return rec
    text = io.open(mir, encoding="utf-8").read()
    if "unmapped:" in text:
        rec["note"] = "%d 条未映射" % text.count("unmapped:")
        return rec
    funcs = mir_eval.parse(text)
    if len(funcs) != 1 or funcs[0].unmapped:
        rec["note"] = "多函数或含未映射"
        return rec
    rec["mir"] = "ok"

    # ---- ① 回译：MIR → .m' ----
    back_dir = os.path.join(d, "back")
    os.makedirs(back_dir, exist_ok=True)
    out_m = os.path.join(back_dir, stem + ".m")
    if U.convert(mir, out_m):
        rec["to_m"] = "fail"
        rec["note"] = "回译遇到未支持算子"
    else:
        rec["to_m"] = "ok"

    # ---- ② 正向：MIR → C → 编译 → 运行 ----
    gen = os.path.join(d, "g_" + stem)
    r = _run([M2C, "build", "--mir", mir, "--out", gen, "--name", stem])
    cpath = None
    for dp, _dn, fns in os.walk(os.path.join(gen, "src")):
        for f in fns:
            if f.endswith(".c") and f not in ("main.c", "selftest.c"):
                cpath = os.path.join(dp, f)
                break
        if cpath:
            break
    if not cpath:
        rec["to_c"] = "fail"
        rec["note"] = "m2c build 失败"
    else:
        exe = os.path.join(d, stem + ".exe")
        cc = _run(["gcc", "-std=c99", "-O1",
                   "-I", os.path.join(gen, "include"), "-I", os.path.join(RT, "include"),
                   cpath, os.path.join(gen, "src", "main.c"),
                   os.path.join(RT, "src", "mlc_runtime.c"),
                   os.path.join(RT, "src", "mlc_ops.c"), "-o", exe, "-lm"], timeout=180)
        if cc.returncode != 0:
            rec["to_c"] = "fail"
            rec["note"] = "gcc 编译失败"
        else:
            run = _run([exe], timeout=30)
            rec["c_out"] = run.stdout.decode("utf-8", "replace").strip()[:120]
            rec["to_c"] = "ok" if run.returncode == 0 and rec["c_out"] else "fail"

    # ---- ③ 数值三方差：参考（原 .m） / 回译 .m' / C ----
    # **优先用 VM 自证**（R696 起覆盖全语料）：不依赖 Octave，也快得多。
    # 只有 VM 明确说"不支持"时才回退到 Octave —— 且回退要**如实记录**，
    # 否则"有没有 Octave"会静默改变判据的强度。
    src_dir = os.path.dirname(os.path.abspath(path))
    work = os.path.join(d, "work")
    os.makedirs(work, exist_ok=True)

    shapes = _arg_shapes(mir)
    ref = _vm_values(mir, shapes)
    if ref is None and cli is not None:
        ref = _values(cli, funcs, src_dir, work, 20)
        rec["oracle"] = "octave"
    elif ref is not None:
        rec["oracle"] = "vm"
    if ref is None:
        rec["note"] = rec["note"] or "无可用 oracle（VM 不支持且缺 Octave）"
        return rec
    rec["ref"] = ref

    if rec["to_m"] == "ok":
        back_mir = os.path.join(d, stem + "_back.mir")
        if os.path.isfile(out_m):
            _run([sys.executable, MIR_PY, out_m, "-o", back_mir])
        v = _vm_values(back_mir, shapes) if os.path.isfile(back_mir) else None
        if v is None and cli is not None:
            v = _values(cli, funcs, back_dir, work, 20)
        rec["m_out"] = v or ""
    return rec


def verdict(rec):
    """唯一判据：三方的数值必须一致（参考 / 回译 / C）。"""
    if rec["mir"] != "ok":
        return "skip"
    if rec["to_m"] != "ok" or rec["to_c"] != "ok":
        return "fail"
    ref, m_out, c_out = rec["ref"], rec["m_out"], rec["c_out"]
    if ref in ("hang", "error", "missing"):
        return "skip"                       # 原函数本身跑不出来，不算回译/发射的账
    # C 的输出形如 `stem: 1 2 3`，与 Octave 的 `1 2 3` 比
    c_vals = c_out.split(":", 1)[1].strip() if ":" in c_out else c_out
    if _norm(ref) != _norm(m_out) or _norm(ref) != _norm(c_vals):
        return "fail"
    return "ok"


def main():
    ap = argparse.ArgumentParser(description="相互转换：MATLAB → MIR → {C, MATLAB'} 并比数值")
    ap.add_argument("path")
    ap.add_argument("--all", action="store_true", help="目录下所有 .m 逐个跑并汇总")
    a = ap.parse_args()

    if not os.path.isfile(M2C):
        print("缺 m2c：cd rust/m2c && cargo build --release")
        return 2
    cli = PR._octave_cli()
    if cli is None:
        print("提示：没找到 Octave/MATLAB —— 只能验“能生成”，无法验“算得一样”")

    if os.path.isfile(a.path):
        files = [a.path]
    else:
        files = sorted(os.path.join(a.path, f) for f in os.listdir(a.path)
                       if f.endswith(".m"))
    if not files:
        print("没有 .m")
        return 2

    base = WORK if os.path.isdir(WORK) else None
    d = tempfile.mkdtemp(prefix="m2c_rt_", dir=base)
    recs = []
    for i, f in enumerate(files, 1):
        sys.stdout.write("\r[%d/%d] %-28s" % (i, len(files), os.path.basename(f)))
        sys.stdout.flush()
        recs.append(roundtrip_one(f, cli, d))
    sys.stdout.write("\n")

    ok = [r for r in recs if verdict(r) == "ok"]
    bad = [r for r in recs if verdict(r) == "fail"]
    skip = [r for r in recs if verdict(r) == "skip"]

    print("\n%-22s %-8s %-8s %-8s %s" % ("函数", "→ C", "→ MATLAB'", "数值三方", "参考 / C"))
    for r in recs:
        v = verdict(r)
        mark = {"ok": "✓", "fail": "✗", "skip": "-"}[v]
        c_vals = r["c_out"].split(":", 1)[1].strip() if ":" in r["c_out"] else r["c_out"]
        print("%-22s %-8s %-8s %-8s %s" % (
            r["name"][:22], r["to_c"], r["to_m"], mark,
            (r["ref"] + " / " + c_vals)[:36] if r["ref"] else r["note"][:36]))

    total = len(ok) + len(bad)
    print("\n相互转换通过 %d/%d ｜ 失败 %d ｜ 跳过 %d"
          % (len(ok), total, len(bad), len(skip)))
    if bad:
        for r in bad[:5]:
            print("   ✗ %s：%s" % (r["name"], r["note"] or "数值不一致"))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
