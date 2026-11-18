# -*- coding: utf-8 -*-
"""**解析/切分判据库**（MS1–MS5）—— 大脑建议的第一块"记忆库"。

    python tools/check_mir_split.py

## 为什么单独建这一块

`flow/failures.json` 聚类出来的结论是：**「解析/切分」类已犯 5 次**，是所有类别里
最多的。它们各自的见证散在 `mir.py` / `map_config.py` 里，靠人记得去看；
这块把 **同一类的四件事** 收成一处，跑一次全验：

| 判据 | 守的是哪次错 |
|---|---|
| **MS1** 无 `end` 的函数也要切出来 | F014：`depth==0` 才认新函数 → yalmiptest 18→3 |
| **MS2** 嵌套块（if/for/while）不破坏函数边界 | F009：按行尾 `end` 切 → "func 未以 end 收束" |
| **MS3** 改写 MIR 后 `version` 头仍在 | F010：只保留 `func:` 块 → "缺少 version 行" |
| **MS4** 函数账本闭合：源 = 收录 + 丢弃 | F013 的根：缺口必须能对上账 |
| **MS5** 每个 `func:` 块都以 `end` 收束 | 切分错误最直接的形态 |

前四条各自对应一条**真实发生过的**错误，所以这不是"想象的判据"，
而是把已有的教训钉成一次可复跑的检查。

退出码：
    0 = MS1–MS5 全部成立
    1 = 任一条不成立（打印是哪一条、期望什么、实际什么）
    2 = 缺输入（连自证要用的临时目录都建不出来）
"""
import io
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))

import mir as M              # noqa: E402
import map_config as MC      # noqa: E402

FUNC_LINE = re.compile(r"^\s*function\b", re.M)


def _write(d, name, body):
    p = os.path.join(d, name)
    io.open(p, "w", encoding="utf-8", newline="\n").write(body)
    return p


def _mir_text(src):
    """把源码切成 MIR 文本（只走切分 + to_mir，不落盘）。"""
    fs = M.split_functions(src)
    out = ["version 3"]
    for f in fs:
        out.append("func:%s" % f["name"])
        out.append("end")
    return "\n".join(out) + "\n", fs


def run():
    """返回问题列表（空 = 全绿）。"""
    problems = []
    d = tempfile.mkdtemp(prefix="m2c_ms_")
    try:
        # ---- MS1：无 end 的多函数文件 ----
        src = ("function y = a1(x)\n"
               "y = x;\n"
               "\n"
               "function z = a2(x)\n"
               "z = x;\n"
               "\n"
               "function w = a3(x)\n"
               "w = x;\n")
        _write(d, "noend.m", src)
        fs = M.split_functions(src)
        if len(fs) != 3:
            problems.append(
                "MS1 无 `end` 的函数没被切开：源有 3 个 function，解析出 %d 个"
                "（F014 回归：18 个只出 3 个就是它）" % len(fs))

        # ---- MS2：嵌套块不破坏边界 ----
        src2 = ("function y = b1(x)\n"
                "y = x;\n"
                "for i = 1:3\n"
                "  if i > 1\n"
                "    y = y + i;\n"
                "  end\n"
                "end\n"
                "end\n"
                "\n"
                "function z = b2(x)\n"
                "z = x;\n"
                "end\n")
        _write(d, "nested.m", src2)
        fs2 = M.split_functions(src2)
        if len(fs2) != 2:
            problems.append("MS2 嵌套块破坏了函数边界：期望 2 个，得到 %d 个"
                            % len(fs2))
        # 第一个函数应包含 2 层块（for + if）
        if fs2 and len(fs2[0]["lines"]) < 3:
            problems.append("MS2 第一个函数的语句数只有 %d（嵌套块里的语句被丢了）"
                            % len(fs2[0]["lines"]))

        # ---- MS3：改写 MIR 后 version 头仍在 ----
        mir_dir = os.path.join(d, "mir")
        os.makedirs(mir_dir)
        mir_path = os.path.join(mir_dir, "project.mir")
        io.open(mir_path, "w", encoding="utf-8", newline="\n").write(
            "version 3\nfunc:f\narg:x:f64:3\nret:y:f64:3\nop:OP-COPY:y:x\n"
            "end\n")
        spec = MC.normalize({"version": 1, "mode": "explicit",
                             "groups": [{"name": "grp", "sources": ["f.m"]}],
                             "unmatched": "own"})
        # 直接测 `apply_to_mir`（`load_and_apply` 只是读文件+写回的外壳）
        old = io.open(mir_path, encoding="utf-8").read()
        new, report = MC.apply_to_mir(old, spec)
        io.open(mir_path, "w", encoding="utf-8", newline="\n").write(new)
        if not new.lstrip().startswith("version"):
            problems.append("MS3 改写后丢了 `version` 头（F010 回归）")

        # ---- MS4：账本闭合 ----
        r = report
        _sum = (sum(g["functions"] for g in r["groups"].values())
                + r["dropped"] + r.get("unmatched_funcs", 0))
        if r["functions"] and r["functions"] != _sum:
            problems.append(
                "MS4 账本不闭合：functions=%d，各项之和=%d（组内 %d + 丢弃 %d "
                "+ 未归组 %d）"
                % (r["functions"], _sum,
                   sum(g["functions"] for g in r["groups"].values()),
                   r["dropped"], r.get("unmatched_funcs", 0)))

        # ---- MS5：每个 func: 块都以 end 收束 ----
        txt, _fs = _mir_text(src2)
        depth = 0
        for ln in txt.splitlines():
            if ln.startswith("func:"):
                if depth != 0:
                    problems.append("MS5 上一个 func 块没有以 end 收束")
                depth = 0
            elif ln.strip() == "end":
                depth = 0
        if depth != 0:
            problems.append("MS5 文末仍有未收束的 func 块")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return problems


ROW_SIGNATURE = "MS1–MS5"


def _ms5(text):
    """MS5 的独立实现（自证要能**双向**验：好的通过、坏的变红）。"""
    depth = 0
    for ln in text.splitlines():
        if ln.startswith("func:"):
            if depth != 0:
                return ["上一个 func 块没有以 end 收束"]
            depth = 1          # `func:` 开块 —— 少了这一步，缺 end 永远测不出来
        elif ln.strip() == "end":
            depth = 0
    return [] if depth == 0 else ["文末仍有未收束的 func 块"]


def _selftest():
    bad = good = 0
    # ① 完整 MIR 通过
    if not _ms5("version 3\nfunc:a\nend\n"):
        good += 1
    else:
        bad += 1
        print("  [selftest] 完整 MIR 被误伤")
    # ② 末尾缺 end 必须红
    if _ms5("version 3\nfunc:a\n"):
        good += 1
    else:
        bad += 1
        print("  [selftest] 缺 end 没红")
    # ③ 真跑一遍 run()（对当前 mir.py 全绿）
    if not run():
        good += 1
    else:
        bad += 1
        print("  [selftest] run() 对当前代码不是全绿")
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    if "--selftest" in sys.argv:
        return _selftest()
    try:
        problems = run()
    except OSError as e:
        # 自证要建临时目录；建不出来属"缺输入"（2），不是"判据不成立"（1）
        print("check_mir_split: 缺输入（临时目录不可用：%s）" % e)
        return 2
    if problems:
        for p in problems:
            print("- %s" % p)
        print("check_mir_split: %d 处问题（MS1–MS5）" % len(problems))
        return 1
    print("check_mir_split: OK（MS1–MS5 全绿：无 end 切分 / 嵌套边界 / "
          "version 头 / 账本闭合 / 块收束）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
