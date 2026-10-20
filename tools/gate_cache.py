# -*- coding: utf-8 -*-
"""门的"增量判定"公共件 —— 指纹与结果缓存。

为什么要有它
============
R429 先给 `check_py36_clean` 做了增量（3.9s → 0.18s），做法是"算指纹、
没变就复用通过结论"。这类逻辑一旦第二道门也要用，就该抽出来 ——
否则两份实现会在"哪些文件算进指纹"上慢慢分叉，而**分叉的后果是
某道门悄悄漏检，却仍然显示 OK**。

判据
----
指纹覆盖哪些文件由调用方给（`globs`），但**永远加上调用方脚本自身**：
检查器改了，结论必须重算。

安全约定（写死在这里，不留给调用方）
----------------------------------
* 只缓存 **rc == 0**（通过）。失败必须每次重算 —— 否则"改坏又改回"
  时旧结论会错位，而这正是最容易被忽略的一类假绿。
* 指纹里存 `cache_version`：本模块语义变了就整体作废。

用法：
    from gate_cache import fingerprint, load_hit, save_hit
    fp = fingerprint(REPO, ["*.py", "tools/*.py"], __file__)
    if load_hit(REPO, "py36", fp):
        print("…（增量命中，跳过重扫）")
        return 0
    ...
    save_hit(REPO, "py36", fp, {"files": n})
    return 0
"""
import hashlib
import io
import json
import os

CACHE_VERSION = 2
CACHE_PATH = os.path.join("releases", ".gate-cache.json")

#: 这些目录不参与指纹（生成物 / 缓存 / 依赖）。
SKIP_DIRS = {".git", "releases", "__pycache__", "node_modules", ".matlabc",
             ".archify", ".venv", "venv"}


def _expand(root, patterns):
    """把 glob 列表展开成绝对路径集合（不跨入 SKIP_DIRS）。"""
    import fnmatch
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for n in filenames:
            rel = os.path.relpath(os.path.join(dirpath, n), root)
            rel = rel.replace("\\", "/")
            for pat in patterns:
                if fnmatch.fnmatch(rel, pat):
                    out.append(rel)
                    break
    return sorted(set(out))


def fingerprint(root, patterns, own_file=None):
    """返回 (指纹, 文件数)。`own_file` 一般是调用方的 `__file__`。"""
    h = hashlib.sha256()
    h.update(("v%d|" % CACHE_VERSION).encode())
    for p in [own_file] if own_file else []:
        try:
            st = os.stat(p)
            h.update(b"|own|" + str(int(st.st_mtime_ns)).encode() +
                     b"|" + str(st.st_size).encode())
        except OSError:
            pass
    files = _expand(root, patterns)
    for rel in files:
        try:
            st = os.stat(os.path.join(root, rel))
        except OSError:
            continue
        h.update(("%s|%d|%d;" % (rel, int(st.st_mtime_ns), st.st_size))
                 .encode("utf-8"))
    return h.hexdigest(), len(files)


def _path(root):
    return os.path.join(root, CACHE_PATH)


def _read(root):
    try:
        return json.loads(io.open(_path(root), encoding="utf-8").read())
    except (IOError, OSError, ValueError):
        return {}


def load_hit(root, key, fp):
    """命中则返回缓存里的 info（dict），否则 None。"""
    data = _read(root)
    if data.get("v") != CACHE_VERSION:
        return None
    item = (data.get("items") or {}).get(key) or {}
    if item.get("fp") == fp and item.get("rc") == 0:
        return item
    return None


def save_hit(root, key, fp, info=None):
    """记录一次**通过**。失败永远不写。"""
    data = _read(root)
    if data.get("v") != CACHE_VERSION:
        data = {"v": CACHE_VERSION, "items": {}}
    data.setdefault("items", {})[key] = {
        "fp": fp, "rc": 0,
        "at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        "info": info or {},
    }
    try:
        p = _path(root)
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        io.open(p, "w", encoding="utf-8", newline="").write(
            json.dumps(data, ensure_ascii=False, indent=1) + u"\n")
    except (IOError, OSError):
        pass
