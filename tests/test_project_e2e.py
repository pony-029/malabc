# -*- coding: utf-8 -*-
"""工程级端到端：「MATLAB 工程 → C 工程」的**整条链路**。

## 为什么要有这个文件（而不是继续用三个函数的样本）

`tests/test_project_level.py` 用的是**平铺**的三文件工程（`proj`）。平铺会让所有
"跨边界"问题退化成"同层调用"——而真实 MATLAB 工程总有子目录：

```
src/lib/scale.m      ← 被 algo/ 调
src/lib/addc.m       ← 被 algo/ 调
src/algo/compute.m   ← 调 lib/，再被顶层调
src/top.m            ← 顶层
```

R805 之前，这个形状的工程能生成、能编译，但**第二个跳转的调用点会退化成
`TODO(call)`**（实参是上一条 `call` 的产出，`var_dtype` 判不出类型）。
平铺样本永远撞不到它 —— 因为它需要"调用链 ≥ 2 跳"且"跨文件"同时成立。

## 这条判据的四个口径

* **E2E1** 生成物必须自带编译单位清单（`src/sources.txt` 的 `[lib]/[app]/[test]`）——
  否则 `gcc src/*.c` 必然 `multiple definition`（`gen.c` 是 unity、两个 `main` 二选一）。
* **E2E2** 按清单编译必须成功（不猜文件列表）。
* **E2E3** 运行结果必须**没有** `unimplemented`（= 调用链真的打通了）。
* **E2E4** 四组数值必须与手算一致：`scale(v,2)=2 4 6`、`addc(t,1)=3 4 5`、
  `compute(a)=3 5 7`、`top(v)=3 5 7`。
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PM_PY = os.path.join(ROOT, "translate", "project_map.py")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
RT = os.path.join(ROOT, "c_runtime")
WORK = os.environ.get("M2C_TMP")


def _run(cmd, cwd=None, timeout=600):
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


#: 两个子目录 + 一条**两跳**调用链（top → compute → scale / addc）
FILES = {
    "lib/scale.m": ("function y = scale(x, k)\n% @m2c shape x 3\n"
                    "% @m2c shape y 3\n% @m2c i64 k\ny = x .* k;\nend\n"),
    "lib/addc.m": ("function y = addc(x, c)\n% @m2c shape x 3\n"
                   "% @m2c shape y 3\n% @m2c i64 c\ny = x + c;\nend\n"),
    "algo/compute.m": ("function y = compute(a)\n% @m2c shape a 3\n"
                       "% @m2c shape y 3\nt = scale(a, 2);\ny = addc(t, 1);\nend\n"),
    "top.m": ("function y = top(v)\n% @m2c shape v 3\n% @m2c shape y 3\n"
              "y = compute(v);\nend\n"),
}

CFG = {
    "version": 2,
    "matlab": {"root": "src", "recursive": True, "exclude": []},
    "c": {"root": "gen", "project": "e2e", "prefix": "m2c_",
          "runtime": "c_runtime"},
    "dtypes": {"default": "f64"},
    "targets": {"pc": {"abi": "host", "allow_heap": True, "dtype": "f64"}},
    "modules": [{"id": "lib", "sources": ["scale.m", "addc.m"]},
                {"id": "algo", "sources": ["compute.m", "top.m"]}],
}


@pytest.fixture(scope="module")
def built():
    """建工程 → `project_map --build`；返回 (目录, 生成根)。"""
    if not os.path.isfile(M2C):
        pytest.skip("m2c 未构建")
    if not os.path.isfile(PM_PY):
        pytest.skip("缺 project_map.py")

    d = tempfile.mkdtemp(prefix="e2e_", dir=WORK if WORK and os.path.isdir(WORK) else None)
    try:
        for rel, body in FILES.items():
            p = os.path.join(d, "src", rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            io.open(p, "w", encoding="utf-8", newline="\n").write(body)
        cfgp = os.path.join(d, "m2c.project.json")
        io.open(cfgp, "w", encoding="utf-8", newline="\n").write(
            json.dumps(CFG, ensure_ascii=False, indent=2))

        r = _run([sys.executable, PM_PY, cfgp, "--build"], cwd=d, timeout=900)
        assert r.returncode == 0, \
            "工程构建失败：\n%s" % r.stdout.decode("utf-8", "replace")[-800:]
        yield d, os.path.join(d, "gen")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _units(gen):
    """读 `src/sources.txt` 的分组；没有就返回 None（判据会红）。"""
    p = os.path.join(gen, "src", "sources.txt")
    if not os.path.isfile(p):
        return None
    groups, cur = {}, None
    for ln in io.open(p, encoding="utf-8", errors="replace"):
        t = ln.strip()
        if not t or t.startswith("#"):
            continue
        if t.startswith("[") and t.endswith("]"):
            cur = t[1:-1]
            groups[cur] = []
            continue
        groups.setdefault(cur or "misc", []).append(t)
    return groups


def test_e2e1_compile_units_are_declared(built):
    """E2E1：生成物必须自带编译单位清单。

    没有它，用户只能去读 CMakeLists 才知道该编哪些 `.c`；而 `gcc src/*.c`
    会撞上 `multiple definition`（`gen.c` 是 unity，分片又被它 `#include`）。
    """
    _d, gen = built
    g = _units(gen)
    assert g is not None, \
        "生成工程缺 `src/sources.txt` —— 用户无从知道该编译哪些文件"
    for k in ("lib", "app", "test"):
        assert g.get(k), "sources.txt 缺 `[%s]` 组：%r" % (k, g)
    assert any(u.endswith("gen.c") for u in g["lib"]), \
        "`[lib]` 里没有 unity 文件 gen.c：%r" % g["lib"]


def test_e2e5_readme_explains_build(built):
    """E2E5：工程 README 必须解释**不用 CMake 时怎么编**。

    只给 `sources.txt` 不够 —— 用户不会主动去找它，而 `gcc src/*.c` 是
    最自然的写法，会撞 `multiple definition`。README 要在他犯错之前说清两件事：
    `gen.c` 是 unity、`main.c` 与 `selftest.c` 二选一。
    """
    _d, gen = built
    p = os.path.join(gen, "README.md")
    assert os.path.isfile(p), "生成工程缺 README.md"
    txt = io.open(p, encoding="utf-8", errors="replace").read()
    assert "sources.txt" in txt, "README 没提 `src/sources.txt`（编译单位清单）"
    assert "unity" in txt.lower() or "#include" in txt, \
        "README 没说 `gen.c` 是 unity 文件（用户会去单独编 src/gen/*.c）"
    assert "selftest" in txt and "二选一" in txt, \
        "README 没警告 `main.c` 与 `selftest.c` 都有 main()（同时链接会炸）"


def test_e2e2_e2e4_build_run_and_values(built):
    """E2E2–E2E4：按清单编译 → 运行 → 无 unimplemented 且数值正确。"""
    cc = _cc()
    if cc is None:
        pytest.skip("没有 C 编译器")
    _d, gen = built
    g = _units(gen)
    assert g is not None, "缺 sources.txt（E2E1 会先红）"

    srcs = [os.path.join(gen, u) for u in g["lib"] + g["app"]
            if u.endswith(".c")]
    exe = os.path.join(_d, "e2e.exe" if os.name == "nt" else "e2e")
    cmd = ([cc, "-std=c99", "-O1",
            "-I", os.path.join(gen, "include"), "-I", os.path.join(RT, "include")]
           + srcs
           + [os.path.join(RT, "src", "mlc_runtime.c"),
              os.path.join(RT, "src", "mlc_ops.c"), "-o", exe])
    r = _run(cmd, timeout=600)
    assert r.returncode == 0, \
        "按 sources.txt 编译失败：\n%s" % r.stdout.decode("utf-8", "replace")[-800:]

    out = _run([exe], timeout=120).stdout.decode("utf-8", "replace")
    assert "unimplemented" not in out, \
        "工程里有函数未实现（两跳调用没打通？）：\n%s" % out[-400:]

    got = {}
    for ln in out.splitlines():
        if ":" in ln:
            k, _, v = ln.partition(":")
            got[k.strip()] = v.split()
    expect = {"scale": ["2", "4", "6"], "addc": ["3", "4", "5"],
              "compute": ["3", "5", "7"], "top": ["3", "5", "7"]}
    for k, want in expect.items():
        assert k in got, "运行输出里没有 %s：\n%s" % (k, out[-300:])
        assert got[k] == want, "%s 得 %r，期望 %r" % (k, got[k], want)
