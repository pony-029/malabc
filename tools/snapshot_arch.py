# -*- coding: utf-8 -*-
"""把某一版本的 14 张架构图冻结成快照（candidate/html/svg 三个哈希）。

为什么需要它：
    `svg/MANIFEST.json` 只回答“现在是不是最新”，回答不了“v1.16.72 时这
    张图长什么样”。发布后代码与图都会继续变，没有快照就无法回查。
    本工具按 `matlabc.py` 的 `VERSION` 归档：同一版本重跑会覆盖该版本条目，
    新版本追加一条。

用法：
    python tools/snapshot_arch.py --write
    python tools/snapshot_arch.py --check
    python tools/snapshot_arch.py --json
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCH = os.path.join(ROOT, "docs", "architecture")
INDEX = os.path.join(ARCH, "FLOW_INDEX.json")
MANIFEST = os.path.join(ARCH, "svg", "MANIFEST.json")
OUT = os.path.join(ARCH, "SNAPSHOTS.json")
MATLABC = os.path.join(ROOT, "matlabc.py")


def _version():
    text = io.open(MATLABC, "r", encoding="utf-8", errors="replace").read()
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)', text, re.M)
    return m.group(1) if m else "unknown"


def _commit():
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=15)
        return (r.stdout or b"").decode("utf-8", "replace").strip() or "-"
    except (OSError, subprocess.SubprocessError):
        return "-"


def _load(path, default):
    if not os.path.isfile(path):
        return default
    with io.open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _current_items():
    man = _load(MANIFEST, {})
    items = man.get("items") or {}
    out = {}
    for iid, rec in items.items():
        out[iid] = {
            "candidate_sha256": rec.get("candidate_sha256"),
            "html_sha256": rec.get("html_sha256"),
            "svg_sha256": rec.get("svg_sha256"),
        }
    return out


def _build(existing):
    ver = _version()
    snap = {
        "version": ver,
        "commit": _commit(),
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "items": _current_items(),
    }
    snaps = list((existing or {}).get("snapshots") or [])
    replaced = False
    for i, old in enumerate(snaps):
        if old.get("version") == ver:
            snaps[i] = snap
            replaced = True
            break
    if not replaced:
        snaps.append(snap)
    return {"version": 1, "snapshots": snaps}


def _snap(existing, ver):
    if ver == "current":
        return {"version": "current", "items": _current_items()}
    for s in reversed((existing or {}).get("snapshots") or []):
        if s.get("version") == ver:
            return s
    return None


def _diff(existing, v1, v2, as_json=False, fail_on_change=False):
    a, b = _snap(existing, v1), _snap(existing, v2)
    if not a or not b:
        print("找不到版本：%r / %r" % (v1, v2))
        return 2
    ai, bi = a.get("items") or {}, b.get("items") or {}
    added = sorted(set(bi) - set(ai))
    removed = sorted(set(ai) - set(bi))
    changed = []
    for iid in sorted(set(ai) & set(bi)):
        keys = [k for k in ("candidate_sha256", "html_sha256",
                            "svg_sha256")
                if (ai[iid] or {}).get(k) != (bi[iid] or {}).get(k)]
        if keys:
            changed.append({"id": iid, "keys": keys})
    result = {"base": v1, "head": v2, "added": added,
              "removed": removed, "changed": changed}
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("%s -> %s" % (v1, v2))
        for x in added:
            print("  + %s" % x)
        for x in removed:
            print("  - %s" % x)
        for x in changed:
            print("  ~ %s（%s）" % (x["id"], ", ".join(x["keys"])))
        if not (added or removed or changed):
            print("  0 changes")
    if fail_on_change and (added or removed or changed):
        return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="冻结架构图版本快照")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--diff", nargs=2, metavar=("V1", "V2"),
                    help="比较两个版本；V2 可用 current")
    ap.add_argument("--fail-on-change", action="store_true")
    args = ap.parse_args(argv)
    if not os.path.isfile(MANIFEST):
        print("缺 %s（先跑 export_arch_svg.py --all）" % MANIFEST)
        return 2
    existing = _load(OUT, {"version": 1, "snapshots": []})
    if args.diff:
        return _diff(existing, args.diff[0], args.diff[1], args.json,
                     args.fail_on_change)
    data = _build(existing)
    ver = _version()
    snap = [s for s in data["snapshots"] if s.get("version") == ver][0]
    if args.json:
        print(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.write:
        with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        print("wrote %s（version %s，%d 张图）"
              % (OUT, ver, len(snap["items"])))
        return 0
    # --check：只比哈希，不要求 commit 相同（PR/CI 的 HEAD 会变）
    cur = _current_items()
    if set(cur) != set(snap.get("items") or {}):
        print("SNAPSHOTS 条目集合与当前索引不一致：%r != %r"
              % (sorted(cur), sorted(snap.get("items") or {})))
        return 1
    bad = []
    for iid, rec in sorted(cur.items()):
        old = (snap.get("items") or {}).get(iid) or {}
        for key in ("candidate_sha256", "html_sha256", "svg_sha256"):
            if old.get(key) != rec.get(key):
                bad.append("%s 的 %s 已变" % (iid, key))
    if bad:
        for b in bad:
            print("  - %s" % b)
        print("SNAPSHOTS 已过期：python tools/snapshot_arch.py --write")
        return 1
    print("snapshot_arch: OK（version %s，%d 张图与当前清单一致）"
          % (ver, len(cur)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
