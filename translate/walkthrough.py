# -*- coding: utf-8 -*-
"""一条命令打印**完整转换过程**，每一步只给真实产物（可核对）。

    python tools/walkthrough.py <某个 .m>

五步：① 源 ② MIR ③ 生成的 C ④ 工程骨架 ⑤ 编译 + 运行。
与 `translate/report.py` 的区别：报告面向“多工程横向对比”，这里面向“单个函数纵向
逐层追下来”——演示和答疑时用这个，因为它把**中间态**也打出来了。

产物一律落在 `E:\\temp\\matlabc`（仓库约定：测试资料不放 C 盘）。
"""
import glob
import hashlib
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")


def _sha(p):
    return hashlib.sha256(io.open(p, "rb").read()).hexdigest()[:12]


#: 统一的子进程入口：**必须**给 stdin=DEVNULL 与 timeout。
#: 本仓有真实挂死案例（继承调用方句柄后读 stdin 永久阻塞）。
_RUN_TIMEOUT = 600


def _run(cmd):
    # 卫生门（S1/S2）要求这两个**字面出现**在这个调用里：
    # 早前用 setdefault 隐式传，检查器看不见 —— 而它挡的是真实挂死案例。
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=_RUN_TIMEOUT,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def main():
    if len(sys.argv) < 2:
        print("用法：python tools/walkthrough.py <x.m>")
        return 2
    src_path = os.path.abspath(sys.argv[1])
    if not os.path.isfile(src_path):
        print("找不到：%s" % src_path)
        return 2
    stem = os.path.splitext(os.path.basename(src_path))[0]
    d = os.path.join(WORK, "walk_" + stem)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    mir = os.path.join(d, stem + ".mir")
    gen = os.path.join(d, "gen")

    bar = "=" * 74
    print(bar)
    print("① 源（%s）" % os.path.basename(src_path))
    print(bar)
    src = io.open(src_path, encoding="utf-8").read().splitlines()
    for i, ln in enumerate(src, 1):
        print("%3d | %s" % (i, ln))
    print("  → %d 行，%d 字节，sha256=%s"
          % (len(src), os.path.getsize(src_path), _sha(src_path)))

    print("\n" + bar)
    print("② MIR")
    print(bar)
    r = _run([sys.executable, os.path.join(ROOT, "translate", "mir.py"), src_path, "-o", mir])
    print("  m2c-mir rc=%d  %s" % (r.returncode,
                                   r.stdout.decode("utf-8", "replace").strip()[:90]))
    if r.returncode != 0 or not os.path.isfile(mir):
        return 1
    text = io.open(mir, encoding="utf-8").read()
    lines = [l for l in text.splitlines() if l.strip()]
    for ln in lines:
        print("   " + ln[:96])
    print("  → 算子 %d 个 ｜ 未映射 %d 条"
          % (len([l for l in lines if l.startswith("op:")]), text.count("unmapped:")))

    print("\n" + bar)
    print("③ 生成的 C")
    print(bar)
    r = _run([M2C, "build", "--mir", mir, "--out", gen, "--name", stem])
    print("  m2c build rc=%d" % r.returncode)
    for dirpath, _dn, fns in os.walk(os.path.join(gen, "src")):
        for fn in sorted(fns):
            if not fn.endswith(".c") or fn == "main.c":
                continue
            p = os.path.join(dirpath, fn)
            body = io.open(p, encoding="utf-8", errors="replace").read()
            print("  --- %s（%d 字节）---" % (fn, len(body)))
            for ln in body.splitlines():
                s = ln.strip()
                if s and not s.startswith("/*") and "mlc_array_init" not in s:
                    print("   " + ln[:96])

    print("\n" + bar)
    print("④ 工程骨架")
    print(bar)
    for p in sorted(glob.glob(os.path.join(gen, "**", "*"), recursive=True)):
        if os.path.isfile(p):
            print("  %-28s %6d B"
                  % (os.path.relpath(p, gen).replace("\\", "/"), os.path.getsize(p)))

    print("\n" + bar)
    print("⑤ 编译 + 运行")
    print(bar)
    exe = os.path.join(d, stem + ".exe")
    cc = _run(["gcc", "-std=c99", "-O1",
               "-I", os.path.join(gen, "include"),
               "-I", os.path.join(ROOT, "c_runtime", "include"),
               os.path.join(gen, "src", "gen.c"), os.path.join(gen, "src", "main.c"),
               os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
               os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c"), "-o", exe, "-lm"])
    print("  gcc rc=%d" % cc.returncode)
    if cc.returncode != 0:
        print("  " + cc.stdout.decode("utf-8", "replace")[:400])
        return 1
    out = _run([exe])
    print("  运行输出: %s" % out.stdout.decode("utf-8", "replace").strip())
    print("  退出码  : %d" % out.returncode)
    print("\n产物目录: %s" % d)
    return 0 if out.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
