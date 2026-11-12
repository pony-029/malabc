# -*- coding: utf-8 -*-
"""figures_refresh.py —— 把 `flow/figures` 下的图**按当前 HEAD 重渲染**。

为什么要有它（而不是留在某个临时脚本里）
========================================
图的状态是"它声明的 revision"与 HEAD 的距离。R783 实测：20 张图**全部**滞后，
而重渲染这件事此前只存在于我的一次性脚本里 —— 换个人、换一轮就没了。

## 三条硬规则（都是踩过的）

1. **revision 必须跟着真实渲染走**。只改 JSON 里的 revision 而不重渲染，
   等于让图声称"我反映当前代码"—— 那比过期更糟（过期至少诚实）。
2. **写 `candidate.json` 必须用 CRLF**。仓库对它有 EO1 约束；用 `newline=""`
   会写出裸 LF，触发 EOL 门（R785 实测：10 个文件、2822 行 diff）。
3. **历史图跳过**。`meta.status == "historical"` 的用旧 schema，重渲染必然失败
   （`schema/required`），它们不是欠账。

用法：
    python tools/figures_refresh.py                 # 刷新所有 lag>0 的图
    python tools/figures_refresh.py --only f38      # 只刷目录名含 f38 的
    python tools/figures_refresh.py --dry-run       # 只列出会刷新哪些
    python tools/figures_refresh.py --selftest      # 两向自证（不需要 node）
    python tools/figures_refresh.py --help

退出码：
    0  = 全部需要刷新的都刷新成功（或无需要刷新的）
    1  = 有图刷新失败（逐个列出原因）
    2  = 缺输入（没有 node / 没有 flow/figures）
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIGS = os.path.join(ROOT, "flow", "figures")
CLI = os.environ.get("ARCHIFY_CLI") or r"D:\project\archify\archify\bin\archify.mjs"
WORK = os.environ.get("M2C_TMP") or tempfile.gettempdir()


def _run(cmd, cwd=None, timeout=900):
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def head():
    r = _run(["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=60)
    return r.stdout.decode("utf-8", "replace").strip()


def plan(head_rev):
    """返回 (todo, skip)：todo 是需要刷新的 [(目录, html 名)]，skip 是跳过的 [(目录, 原因)]。"""
    todo, skip = [], []
    if not os.path.isdir(FIGS):
        return todo, skip
    for d in sorted(os.listdir(FIGS)):
        dpath = os.path.join(FIGS, d)
        cand = os.path.join(dpath, "candidate.json")
        if not os.path.isfile(cand):
            skip.append((d, "无 candidate.json"))
            continue
        try:
            c = json.load(io.open(cand, encoding="utf-8"))
        except (ValueError, OSError) as exc:
            skip.append((d, "candidate 读不了：%s" % exc))
            continue
        meta = c.get("meta") or {}
        if (meta.get("status") or "") == "historical":
            skip.append((d, "historical（登记为历史，不随代码重渲染）"))
            continue
        rev = ((meta.get("repository") or {}).get("revision") or "").strip()
        if rev == head_rev:
            skip.append((d, "已是现行"))
            continue
        htmls = [f for f in os.listdir(dpath) if f.endswith(".html")]
        if not htmls:
            skip.append((d, "无 .html"))
            continue
        todo.append((d, htmls[0]))
    return todo, skip


def refresh(d, target):
    """渲染一张图并写回。返回 (ok, 原因)。"""
    dpath = os.path.join(FIGS, d)
    cand = os.path.join(dpath, "candidate.json")
    c = json.load(io.open(cand, encoding="utf-8"))
    c.setdefault("meta", {}).setdefault("repository", {})["revision"] = head()

    work = tempfile.mkdtemp(prefix="fig_", dir=WORK)
    try:
        io.open(os.path.join(work, "candidate.json"), "w", encoding="utf-8",
                newline="\n").write(json.dumps(c, ensure_ascii=False, indent=2))
        r = _run(["node", CLI, "finalize", "architecture", "candidate.json",
                  "out.html", "--quality", "showcase", "--json",
                  "--repo-root", ROOT], cwd=work)
        try:
            j = json.loads(r.stdout.decode("utf-8", "replace"))
        except ValueError:
            return False, "非 JSON 输出：" + r.stdout.decode("utf-8", "replace")[-120:]
        if not j.get("ok"):
            bad = [(x.get("code"), (x.get("message") or "")[:60])
                   for x in (j.get("diagnostics") or [])][:2]
            return False, str(bad)
        src = os.path.join(work, "out.html")
        if not os.path.isfile(src):
            return False, "没有产出 html"
        shutil.copy2(src, os.path.join(dpath, target))
        for ext in (".delivery.json", ".browser-check.json"):
            s = os.path.join(work, "out" + ext)
            if os.path.isfile(s):
                shutil.copy2(s, os.path.join(dpath,
                                             os.path.splitext(target)[0] + ext))
        # 规则 2：CRLF 写回（EO1）
        io.open(cand, "w", encoding="utf-8", newline="").write(
            json.dumps(c, ensure_ascii=False, indent=2).replace("\n", "\r\n") + "\r\n")
        return True, ""
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _selftest():
    """两向自证（**不需要 node**）：plan 能区分"该刷/不该刷"，且历史图被跳过。"""
    tmp = tempfile.mkdtemp(prefix="fr_", dir=WORK)
    global FIGS
    saved = FIGS
    try:
        FIGS = tmp
        H = "a" * 40
        mk = {
            "cur": {"revision": H, "status": None},
            "old": {"revision": "b" * 40, "status": None},
            "hist": {"revision": "c" * 40, "status": "historical"},
        }
        for name, spec in mk.items():
            d = os.path.join(tmp, name)
            os.makedirs(d)
            io.open(os.path.join(d, "x.html"), "w", encoding="utf-8").write("<html>")
            cand = {"meta": {"repository": {"revision": spec["revision"]}}}
            if spec["status"]:
                cand["meta"]["status"] = spec["status"]
            io.open(os.path.join(d, "candidate.json"), "w",
                    encoding="utf-8").write(json.dumps(cand))

        todo, skip = plan(H)
        names = [t[0] for t in todo]
        why = dict(skip)
        if names != ["old"]:
            print("自证失败：应只刷新 old，实得 %r" % names)
            return 1
        if "hist" not in why or "historical" not in why["hist"]:
            print("自证失败：历史图没被跳过（%r）" % why.get("hist"))
            return 1
        if "cur" not in why or "现行" not in why["cur"]:
            print("自证失败：已现行的图没被跳过（%r）" % why.get("cur"))
            return 1
        print('SELFTEST COUNTS {"bad": 2, "good": 1}')
        print("自证通过：该刷的刷、现行跳过、历史跳过")
        return 0
    finally:
        FIGS = saved
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--only", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", action="store_true")
    a, _rest = ap.parse_known_args(argv or sys.argv[1:])

    if a.help:
        print(__doc__)
        return 0
    if a.selftest:
        return _selftest()

    if not os.path.isdir(FIGS):
        print("缺输入：%s 不存在" % FIGS)
        return 2
    if not a.dry_run and not os.path.isfile(CLI):
        print("缺输入：找不到 archify（%s）；可用 ARCHIFY_CLI 指定" % CLI)
        return 2

    h = head()
    todo, skip = plan(h)
    if a.only:
        todo = [t for t in todo if a.only in t[0]]

    if a.dry_run:
        print("HEAD %s ｜ 需要刷新 %d 张" % (h[:12], len(todo)))
        for d, _t in todo:
            print("   刷 %s" % d)
        for d, why in skip:
            if "history" in why or "historical" in why:
                continue
            print("   跳过 %-46s %s" % (d, why))
        return 0

    if not todo:
        print("全部现行（无需刷新）；跳过 %d 张（含历史）" % len(skip))
        return 0

    ok, bad = 0, []
    for d, target in todo:
        good, why = refresh(d, target)
        if good:
            ok += 1
            print("  ✓ %s" % d)
        else:
            bad.append((d, why))
            print("  ✗ %-46s %s" % (d, why[:110]))

    print("\n刷新成功 %d ｜ 失败 %d ｜ 跳过 %d" % (ok, len(bad), len(skip)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
