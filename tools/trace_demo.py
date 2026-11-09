# -*- coding: utf-8 -*-
"""把一条真实链路**逐步记录下来**，输出 JSONL（每行一步，可回放、可对账）。

## 为什么要它

现在"某一步做了什么"只能靠读代码或看终端输出 —— **没有任何逐步证据**。
出问题时只能看到首尾两个数（MIR 有多少 op、运行输出是什么），中间八步是黑箱。

## 记录什么（每步一行）

    step       序号（S1..Sn）
    module     哪一层（front / hir / mir / emit / build / run / vm / verify）
    kind       control（谁触发）| data（传了什么）
    action     人读的一句话
    in_digest  输入摘要（sha256 前 12 位；文件或字符串）
    out_digest 输出摘要
    status     ok | fail | skip
    ms         耗时
    detail     结构化细节（算子数 / 未映射数 / 返回值 …）

**摘要是关键**：它让"这一步的输入是哪一份"变成可核对的事实，
而不是"我记得我传的是那个文件"。
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
CMIR_PY = os.path.join(ROOT, "translate", "cmir.py")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
RT_INC = os.path.join(ROOT, "c_runtime", "include")
RT_SRC = [os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
          os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c")]
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def sha(text, n=12):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:n]


def shafile(p):
    return sha(io.open(p, encoding="utf-8", errors="replace").read())


class Trace:
    def __init__(self):
        self.rows = []
        self.n = 0

    def step(self, module, kind, action, in_d, out_d, status="ok", ms=0, **detail):
        self.n += 1
        rec = {"step": "S%d" % self.n, "module": module, "kind": kind,
               "action": action, "in": in_d, "out": out_d,
               "status": status, "ms": int(ms), "detail": detail}
        self.rows.append(rec)
        print("  %-3s %-7s %-5s %-38s %s" % (rec["step"], module, kind, action[:38], status))
        return rec

    def dump(self, path):
        io.open(path, "w", encoding="utf-8", newline="\n").write(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in self.rows) + "\n")


def run(cmd, timeout=300):
    """唯一子进程入口：切断 stdin + 必带 timeout。

    **不要加 `**kw`** —— 一旦透传任意关键字，静态检查就看不见超时与 stdin，
    会被判成"盲区"（S4）并要求登记。
    """
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def main():
    ap = argparse.ArgumentParser(description="逐步追踪一条真实链路")
    ap.add_argument("source", help="一个 .m 文件")
    ap.add_argument("-o", "--out", default=os.path.join(WORK, "trace.jsonl"))
    a = ap.parse_args()

    src = os.path.abspath(a.source)
    t = Trace()
    d = os.path.join(WORK, "tracedemo")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)

    # S1 读源码
    t0 = time.time()
    text = io.open(src, encoding="utf-8", errors="replace").read()
    t.step("front", "data", "读源码 %s" % os.path.basename(src),
           "-", sha(text), ms=(time.time() - t0) * 1000, lines=len(text.splitlines()))

    # S2 MIR
    t0 = time.time()
    mir = os.path.join(d, "f.mir")
    r = run([sys.executable, MIR_PY, src, "-o", mir])
    if r.returncode != 0 or not os.path.isfile(mir):
        t.step("mir", "control", "mir.py 生成 MIR", sha(text), "-", "fail",
               (time.time() - t0) * 1000)
        t.dump(a.out)
        return 1
    mt = io.open(mir, encoding="utf-8").read()
    ops = [l.split(":")[1] for l in mt.splitlines() if l.startswith("op:")]
    t.step("mir", "control", "MATLAB → MIR", sha(text), sha(mt),
           ms=(time.time() - t0) * 1000, ops=len(ops), unmapped=mt.count("\nunmapped:"))

    # S3 HIR 身份往返
    t0 = time.time()
    sys.path.insert(0, ROOT)
    from translate import hir as H                      # noqa: E402
    body = [l for l in mt.splitlines() if l.strip() and not l.startswith(
        ("#", "version", "func:", "arg:", "ret:"))]
    while body and body[-1].strip() == "end":
        body.pop()
    hb, mapped = H.mir_to_hir("\n".join(body))
    same = None
    if mapped:
        back = H.hir_to_mir(H.hir_wrap("f", [], [], hb))
        ob = [l.split(":")[1] for l in back.split("\n") if l.startswith("op:")]
        import collections
        same = collections.Counter(ops) == collections.Counter(ob)
    # **主产物语义**：这一步吃 MIR、吐的还是 MIR（HIR 是中间的语义视图，不改产物），
    # 所以 `out` 与 `in` 相同 —— 否则链路检查会把"没换产物"误判成断链。
    t.step("hir", "data", "MIR → HIR → MIR 恒等", sha(mt), sha(mt),
           "ok" if (same is not False) else "fail",
           (time.time() - t0) * 1000, mapped=mapped, identical=same)

    # S4 工程装配
    t0 = time.time()
    g = os.path.join(d, "gen")
    r = run([M2C, "build", "--mir", mir, "--out", g, "--name", "f"])
    files = sum(len(fs) for _dp, _dn, fs in os.walk(g)) if os.path.isdir(g) else 0
    genc = os.path.join(g, "src", "gen.c")
    genc_sha = shafile(genc) if os.path.isfile(genc) else "-"
    t.step("emit", "control", "m2c build 生成 C 工程", sha(mt), genc_sha,
           "ok" if r.returncode == 0 else "fail",
           (time.time() - t0) * 1000, files=files)

    # S5 gcc
    t0 = time.time()
    cc = shutil.which("gcc") or shutil.which("clang")
    exe = os.path.join(g, "f.exe" if os.name == "nt" else "f")
    r = run([cc, "-std=c99", "-O1", "-I", os.path.join(g, "include"),
             "-I", RT_INC, os.path.join(g, "src", "gen.c"),
             os.path.join(g, "src", "main.c")] + RT_SRC + ["-o", exe], timeout=600)
    t.step("build", "control", "gcc 编译", genc_sha, "exe",
           "ok" if r.returncode == 0 else "fail", (time.time() - t0) * 1000,
           rc=r.returncode)

    # S6 运行 C
    t0 = time.time()
    out_c = run([exe]).stdout.decode("utf-8", "replace").strip()
    vals = [l.split(":", 1)[1].strip() for l in out_c.splitlines() if ":" in l]
    t.step("run", "data", "C 可执行运行", "exe", sha(out_c),
           ms=(time.time() - t0) * 1000, values=" | ".join(vals)[:60])

    # S7 VM
    t0 = time.time()
    r = run([M2C, "run", "--mir", mir])
    out_vm = r.stdout.decode("utf-8", "replace").strip()
    vals2 = [l.split(":", 1)[1].strip() for l in out_vm.splitlines() if ":" in l]
    t.step("vm", "data", "Rust VM 执行同一份 MIR", sha(mt), sha(out_vm),
           ms=(time.time() - t0) * 1000, values=" | ".join(vals2)[:60])

    # S8 对账
    t.step("verify", "control", "C 与 VM 数值一致",
           sha(out_c), sha(out_vm),
           "ok" if " ".join(vals) == " ".join(vals2) else "fail",
           0, c=" | ".join(vals)[:40], vm=" | ".join(vals2)[:40])

    # S9 回推
    t0 = time.time()
    bmir = os.path.join(d, "back.mir")
    r = run([sys.executable, CMIR_PY, os.path.join(g, "src", "gen.c"),
             "-o", bmir, "--name", "f"])
    t.step("cmir", "data", "C → MIR 反推", genc_sha,
           shafile(bmir) if os.path.isfile(bmir) else "-",
           "ok" if (r.returncode == 0 and os.path.isfile(bmir)) else "fail",
           (time.time() - t0) * 1000)

    t.dump(a.out)
    ok = sum(1 for r in t.rows if r["status"] == "ok")
    print("\n共 %d 步 ｜ ok %d ｜ 已写出 %s" % (len(t.rows), ok, a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
