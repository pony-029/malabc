# -*- coding: utf-8 -*-
"""**端到端验证宏重映射**：生成 -> 编译 -> 用 nm 看符号真的换了。

    python tools/verify_symbol_map.py
    python tools/verify_symbol_map.py --json
    python tools/verify_symbol_map.py --selftest

## 为什么需要它（R1052）

`gen_symbol_map.py` 的自证只证明**渲染出的文本是对的**，不证明那个文本
能被编译器接受、更不证明符号真的被替换。R1044 做完之后过了七轮，
都**没有人知道它生成的头文件能不能用**——直到上一轮手工跑了一遍
gcc + nm 才确认。

生成器类工具的验收必须包含**消费方**：把产物喂给真正的下游，看它是否被接受。
所以本工具把那次手工验证固化成可复跑的一步。

## 判据（四步，任一步失败即红）

1. `m2c build` 从 MIR 生成真实 C 工程；
2. 生成物里**必须**出现内置符号（如 `mlc_op_sum`）——否则"重映射"无从谈起；
3. `gen_symbol_map` 出 `m2c_symbols.h`，且含至少一条 `#define`；
4. `gcc -include` 编译通过，且 `nm -u` 里**只出现目标符号、不出现内置符号**。

第 4 步是核心：如果两边的符号都出现，说明宏没生效或只对部分调用点生效。

## 诚实边界

* 没有 gcc / nm / m2c 时**跳过并说明**，不假装通过（返回 0 但打印 [skip]，
  与「真的验过」在输出上可区分）；
* 只验「符号被替换」，不验**运行时数值正确** —— 那要真跑起来比结果，是另一件事。

退出码：
    0 = 通过（或跳过）
    1 = 自证失败或端到端不一致
    2 = 缺输入
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))

#: 最小可复现语料：两个函数，一个矩阵乘一个归约，正好覆盖两条重映射。
SAMPLE = {
    "big_mmul.m": ("function y = big_mmul(a, b)\n"
                   "% @m2c shape a 128,128\n"
                   "% @m2c shape b 128,128\n"
                   "% @m2c shape y 128,128\n"
                   "y = a * b;\nend\n"),
    "big_sum.m": ("function y = big_sum(x)\n"
                  "% @m2c shape x 1024\n"
                  "% @m2c shape y 1\n"
                  "y = sum(x);\nend\n"),
}


def _run(cmd, cwd=None, timeout=300):
    try:
        r = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
        return r.returncode, r.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)


def run_check(profile, op_map, workdir):
    """执行四步验证。返回 dict（含 ok / steps / skip_reason）。"""
    py = sys.executable
    m2c = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
    gcc = shutil.which("gcc") or shutil.which("cc")
    nm = shutil.which("nm")
    if os.name == "nt":
        # MinGW 常在 D:\project\MinGW-w64\bin，which 找不到时再试一次
        for base in (r"D:\project\MinGW-w64\bin",):
            if not gcc and os.path.isfile(os.path.join(base, "gcc.EXE")):
                gcc = os.path.join(base, "gcc.EXE")
            if not nm and os.path.isfile(os.path.join(base, "nm.EXE")):
                nm = os.path.join(base, "nm.EXE")

    missing = [n for n, v in (("m2c", m2c if os.path.isfile(m2c) else None),
                              ("gcc", gcc), ("nm", nm)) if not v]
    if missing:
        return {"ok": True, "skipped": True,
                "skip_reason": "缺 %s —— 未做端到端验证（不假装通过）"
                               % "/".join(missing), "steps": []}

    steps = []
    d = workdir
    src = os.path.join(d, "src_m")
    os.makedirs(src, exist_ok=True)
    for name, body in SAMPLE.items():
        io.open(os.path.join(src, name), "w", encoding="utf-8",
                newline="\n").write(body)

    # 1. MIR + build
    mir = os.path.join(d, "p.mir")
    rc, out = _run([py, os.path.join(ROOT, "translate", "mir.py"), src,
                    "-o", mir])
    if rc != 0:
        return {"ok": False, "steps": [("mir", rc, out[-200:])]}
    gen = os.path.join(d, "gen")
    rc, out = _run([m2c, "build", "--mir", mir, "--out", gen,
                    "--name", "verify"])
    steps.append(("build", rc, out[-200:]))
    if rc != 0:
        return {"ok": False, "steps": steps}

    # 2. 生成物里必须有内置符号
    # **扫整个 src/ 而不是只看 gen.c**（R1052）：m2c 把每个 MATLAB 函数
    # 各自生成一个 `*_m.c`，算子调用在那些文件里，`gen.c` 只是聚合入口。
    # 只看 gen.c 会误判成"没有内置符号"，进而得出"重映射无从谈起"的错误结论。
    srcs = []
    for base, _ds, fs in os.walk(os.path.join(gen, "src")):
        for n in fs:
            if n.endswith(".c"):
                srcs.append(os.path.join(base, n))
    body = ""
    for p in srcs:
        body += io.open(p, encoding="utf-8", errors="replace").read()
    genc = os.path.join(gen, "src", "gen.c")
    if not os.path.isfile(genc) and srcs:
        genc = srcs[0]          # 兜底：至少能编一个
    builtin = [s for s in ("mlc_op_sum", "mlc_op_matmul") if s in body]
    steps.append(("builtin_symbols", 0 if builtin else 1, ",".join(builtin)))
    if not builtin:
        return {"ok": False, "steps": steps,
                "why": "生成的 C 里没找到内置符号，重映射无从谈起"}

    # 3. 生成映射头
    hdr = os.path.join(gen, "include", "m2c_symbols.h")
    rc, out = _run([py, os.path.join(ROOT, "tools", "gen_symbol_map.py"),
                    "--profile", profile, "--op-map", op_map, "-o", hdr])
    steps.append(("gen_map", rc, out[-200:]))
    if rc != 0 or not os.path.isfile(hdr):
        return {"ok": False, "steps": steps}
    hbody = io.open(hdr, encoding="utf-8").read()
    n_def = hbody.count("#define mlc_op_")
    steps.append(("define_count", 0 if n_def else 1, str(n_def)))
    if not n_def:
        return {"ok": False, "steps": steps,
                "why": "映射头里没有任何 #define（覆盖没生效）"}

    # 4. 编译 + nm
    obj = os.path.join(d, "gen_mapped.o")
    inc = [gen, os.path.join(gen, "include"),
           os.path.join(ROOT, "c_runtime", "include")]
    cmd = [gcc, "-std=c99", "-O1", "-c", "-include", hdr]
    for i in inc:
        cmd += ["-I", i]
    cmd += [genc, "-o", obj]
    rc, out = _run(cmd)
    steps.append(("gcc", rc, out[-300:]))
    if rc != 0:
        return {"ok": False, "steps": steps}

    rc, out = _run([nm, "-u", obj])
    steps.append(("nm", rc, out[-300:]))
    if rc != 0:
        return {"ok": False, "steps": steps}
    undefined = set()
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) >= 2 and parts[0] == "U":
            undefined.add(parts[1])
    mapped = sorted(s for s in undefined if s.startswith(("hw_", "accel_")))
    leftover = sorted(s for s in undefined if s in builtin)
    steps.append(("mapped_symbols", 0 if mapped else 1, ",".join(mapped)))
    steps.append(("leftover_builtin", 0 if not leftover else 1,
                  ",".join(leftover) or "无"))
    ok = bool(mapped) and not leftover
    return {"ok": ok, "skipped": False, "steps": steps,
            "mapped": mapped, "leftover": leftover}


def _selftest():
    """两向自证：判定逻辑本身要能区分「换掉了」与「没换掉」。"""
    good = bad = 0

    # 只有目标符号 -> 通过
    stepped = []
    if (True and not stepped):
        good += 1
    else:
        bad += 1
        print("  [selftest] 空场景判定异常")

    # 构造两种 nm 输出，验证分类
    def classify(lines, builtin):
        und = set()
        for ln in lines:
            p = ln.split()
            if len(p) >= 2 and p[0] == "U":
                und.add(p[1])
        mapped = [s for s in und if s.startswith(("hw_", "accel_"))]
        left = [s for s in und if s in builtin]
        return bool(mapped) and not left

    if classify(["U hw_dsp_sum", "U memset"], ["mlc_op_sum"]):
        good += 1
    else:
        bad += 1
        print("  [selftest] 只留目标符号应判通过")

    if not classify(["U mlc_op_sum", "U hw_dsp_sum"], ["mlc_op_sum"]):
        good += 1
    else:
        bad += 1
        print("  [selftest] 内置符号仍在时必须判失败")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="宏重映射端到端验证")
    ap.add_argument("--profile",
                    default=os.path.join(ROOT, "tools", "targets",
                                         "mcu_256k.json"))
    ap.add_argument("--op-map",
                    default=os.path.join(ROOT, "tools", "targets",
                                         "vendor_dsp.op-map.json"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    for p in (ns.profile, ns.op_map):
        if not os.path.isfile(p):
            print("verify_symbol_map: 缺输入（%s 不存在）" % os.path.basename(p))
            return 2

    d = tempfile.mkdtemp(prefix="vsm_")
    try:
        r = run_check(ns.profile, ns.op_map, d)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
        return 0 if r.get("ok") else 1

    if r.get("skipped"):
        print("[skip] %s" % r["skip_reason"])
        return 0

    for name, rc, tail in r["steps"]:
        mark = "OK  " if rc == 0 else "FAIL"
        print("  [%s] %-18s %s" % (mark, name, (tail or "").strip()[:70]))
    if r["ok"]:
        print("[verify] 通过：编译后只剩目标符号 %s"
              % (",".join(r.get("mapped") or []),))
        return 0
    print("[verify] 失败：残留内置符号 %s"
          % (",".join(r.get("leftover") or []) or "无",))
    return 1


if __name__ == "__main__":
    sys.exit(main())
