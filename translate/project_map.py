# -*- coding: utf-8 -*-
"""**MATLAB 工程 ↔ C 工程** 的映射关系配置。

## 为什么需要单独一层

现在「转换一个工程」只知道两件事：源路径、输出路径。于是：

* 一个大工程里哪些目录要转、哪些要跳过（`test/`、`+pkg/`、`@class/`）—— 只能靠人记；
* 生成物放哪、叫什么、前缀是什么 —— 只能命令行现打；
* **MATLAB 目录 ↔ C 模块** 的对应关系（一个目录一个 `.c`？还是一个函数一个？）—— 完全没表达。

于是同一个工程每次转换的参数都可能不同，**结果不可复现**。这一层就是把那些参数
变成**一个文件**，并且能被校验。

## 配置文件（`m2c.project.json`）

```json
{
  "version": 1,
  "matlab": {
    "root": "matlab",
    "recursive": true,
    "exclude": ["**/test/**", "**/+*/**", "**/@*/**"]
  },
  "c": {
    "root": "gen",
    "project": "myproj",
    "prefix": "m2c_",
    "runtime": "c_runtime"
  },
  "mapping": {
    "matlab/solvers": "gen/solvers",
    "matlab/dsp/filter.m": "gen/dsp/filter.c"
  },
  "defaults": { "shape": 4, "dtype": "f64", "max_seconds": 120 }
}
```

## 三条硬规则（宁可报错，不猜测）

1. **未知键必须报错** —— 拼错的配置项会被静默忽略，那是最难查的一类问题；
2. **`mapping` 的键必须是 `matlab.root` 下的真实路径** —— 否则说明配置和工程已经脱节；
3. **两个 MATLAB 源不能映射到同一个 C 输出** —— 否则后写的覆盖先写的，且不会有任何提示。

## 用法

    python translate/project_map.py m2c.project.json            # 打印映射计划
    python translate/project_map.py m2c.project.json --json     # 机器可读
"""
import io
import json
import os
import sys

SCHEMA_KEYS = {
    "version": set(),
    "matlab": {"root", "recursive", "exclude"},
    "c": {"root", "project", "prefix", "runtime"},
    "mapping": None,          # 任意「MATLAB 路径 -> C 路径」
    "defaults": {"shape", "dtype", "max_seconds"},
}

REQUIRED = ("version", "matlab", "c")


class ConfigError(Exception):
    """配置不合规（未知键 / 缺必需键 / 类型不对）。"""


def _bad(path, msg):
    return ConfigError("%s：%s" % (path, msg))


def _check_keys(obj, allowed, where):
    if allowed is None:
        return
    for k in obj:
        if k not in allowed:
            raise _bad("%s.%s" % (where, k),
                       "未知配置项（允许：%s）" % ", ".join(sorted(allowed)))


def load(path):
    """读入并**校验**配置；任何不合规都抛 ConfigError（不猜）。"""
    if not os.path.isfile(path):
        raise _bad(path, "文件不存在")
    try:
        d = json.loads(io.open(path, encoding="utf-8").read())
    except ValueError as exc:
        raise _bad(path, "不是合法 JSON（%s）" % exc)
    if not isinstance(d, dict):
        raise _bad(path, "顶层必须是对象")

    _check_keys(d, set(SCHEMA_KEYS), "")
    for k in REQUIRED:
        if k not in d:
            raise _bad(k, "缺少必需项（%s）" % ", ".join(REQUIRED))
    if d.get("version") != 1:
        raise _bad("version", "只支持 1（实际 %r）" % (d.get("version"),))

    for sec in ("matlab", "c"):
        if not isinstance(d[sec], dict):
            raise _bad(sec, "必须是对象")
        _check_keys(d[sec], SCHEMA_KEYS[sec], sec)
    if "root" not in d["matlab"]:
        raise _bad("matlab.root", "缺少必需项")
    if "root" not in d["c"]:
        raise _bad("c.root", "缺少必需项")

    if "defaults" in d:
        if not isinstance(d["defaults"], dict):
            raise _bad("defaults", "必须是对象")
        _check_keys(d["defaults"], SCHEMA_KEYS["defaults"], "defaults")
    if "mapping" in d and not isinstance(d["mapping"], dict):
        raise _bad("mapping", "必须是对象（MATLAB 路径 -> C 路径）")
    return d


def _under(path, root):
    p = os.path.normpath(path).replace("\\", "/").lower()
    r = os.path.normpath(root).replace("\\", "/").lower().rstrip("/")
    return p == r or p.startswith(r + "/")


def _excluded(rel, patterns):
    """极简 glob：只支持 `**/x/**` 与 `**/x/*` 这类前缀/包含匹配。"""
    rel = rel.replace("\\", "/").lower()
    for pat in patterns or ():
        p = pat.replace("\\", "/").lower()
        core = p.replace("**/", "").replace("/**", "").replace("*", "")
        if core and core in rel:
            return True
    return False


def plan(cfg, base=None):
    """把配置展开成**逐个文件的映射清单**。

    返回 `{"entries": [...], "skipped": [...], "problems": [...]}`；
    `problems` 非空表示配置与工程脱节（调用方应报错，而不是继续构建）。
    """
    base = base or os.getcwd()
    mroot = os.path.join(base, cfg["matlab"]["root"])
    croot = os.path.join(base, cfg["c"]["root"])
    recursive = bool(cfg["matlab"].get("recursive", True))
    exclude = cfg["matlab"].get("exclude") or []
    mapping = cfg.get("mapping") or {}
    cext = ".c"

    problems, skipped, files = [], [], []
    for k in mapping:
        if not _under(os.path.join(base, k), mroot):
            problems.append("mapping 的键 %r 不在 matlab.root(%s) 下"
                            % (k, cfg["matlab"]["root"]))

    if not os.path.isdir(mroot):
        problems.append("matlab.root 不存在：%s" % mroot)

    if os.path.isdir(mroot):
        walk = os.walk(mroot) if recursive else [(mroot, [], os.listdir(mroot))]
        for dp, _dn, fn in walk:
            for f in sorted(fn):
                if not f.lower().endswith(".m"):
                    continue
                full = os.path.join(dp, f)
                rel_matlab = os.path.relpath(full, base).replace("\\", "/")
                rel_in_root = os.path.relpath(full, mroot).replace("\\", "/")
                if _excluded(rel_in_root, exclude):
                    skipped.append((rel_matlab, "exclude"))
                    continue
                files.append((rel_matlab, rel_in_root, full))

    # 目录级映射优先，其次文件级精确映射，最后按默认规则
    entries, seen_c = [], {}
    for rel_matlab, rel_in_root, full in files:
        out = None
        for k in sorted(mapping, key=len, reverse=True):
            kk = os.path.join(base, k)
            if os.path.isfile(kk) and os.path.normpath(kk) == os.path.normpath(full):
                out = mapping[k]
                break
            if os.path.isdir(kk) and _under(full, kk):
                sub = os.path.relpath(full, kk).replace("\\", "/")
                out = os.path.join(mapping[k], sub).replace("\\", "/")
                break
        if out is None:
            out = os.path.join(cfg["c"]["root"], rel_in_root).replace("\\", "/")
        if not out.lower().endswith(cext):
            out = out[:-2] + cext if out.lower().endswith(".m") else out + cext
        key = out.lower()
        if key in seen_c:
            problems.append("两个 MATLAB 源映射到同一 C 输出：%s <- %s 与 %s"
                            % (out, seen_c[key], rel_matlab))
            continue
        seen_c[key] = rel_matlab
        entries.append({"matlab": rel_matlab, "c": out})

    return {"entries": entries, "skipped": skipped, "problems": problems,
            "roots": {"matlab": mroot, "c": croot}}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cfg_path = argv[0]
    as_json = "--json" in argv
    try:
        cfg = load(cfg_path)
    except ConfigError as exc:
        print("配置不合规：%s" % exc)
        return 2
    res = plan(cfg, os.path.dirname(os.path.abspath(cfg_path)))
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 1 if res["problems"] else 0
    print("MATLAB 根：%s" % res["roots"]["matlab"])
    print("C    根：%s" % res["roots"]["c"])
    print("映射 %d 个文件，跳过 %d 个" % (len(res["entries"]), len(res["skipped"])))
    for e in res["entries"][:40]:
        print("  %-42s -> %s" % (e["matlab"], e["c"]))
    if len(res["entries"]) > 40:
        print("  ...（其余 %d 个）" % (len(res["entries"]) - 40))
    for s, why in res["skipped"][:10]:
        print("  [skip] %-38s %s" % (s, why))
    for p in res["problems"]:
        print("[problem] %s" % p)
    return 1 if res["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
