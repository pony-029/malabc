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



# ===========================================================================
# v2：工程级关系模型（多个 MATLAB 功能 <-> 一个/多个 C 模块）
# ===========================================================================

V2_TOP = {"version", "matlab", "c", "targets", "modules", "operators",
          "constraints", "memory", "dtypes"}
V2_MODULE = {"id", "sources", "targets", "entry", "timing", "operators"}
V2_TIMING = {"period_ms", "deadline_ms", "entry_kind", "reentrant"}
V2_TARGET = {"abi", "allow_heap", "dtype", "max_stack_bytes", "memory"}
V2_MEM = {"strategy", "pool_bytes", "alignment", "max_array_bytes", "arrays"}
DTYPE_BYTES = {"f64": 8, "f32": 4, "int64": 8, "int32": 4, "int16": 2,
               "int8": 1, "q15": 2}
V2_DTYPES = {"default", "map", "fixed_point"}
V2_FIXED = {"format", "frac_bits", "round", "overflow"}
ROUND_MODES = ("nearest", "floor", "ceil", "trunc")
OVERFLOW_MODES = ("saturate", "wrap")
#: Q 格式 -> (位宽, 最大允许 frac_bits)
Q_WIDTH = {"Q7": 8, "Q15": 16, "Q31": 32}


def _req(obj, keys, where):
    for k in keys:
        if k not in obj:
            raise _bad("%s.%s" % (where, k) if where else k, "缺少必需项")


def load2(path):
    """读入并校验 v2 配置。未知键一律报错（与 v1 同一原则）。"""
    # 不能复用 v1 的 load()：它的键白名单里没有 virtual v2 的键，
    # 会在 v2 校验之前就把合法配置拒掉（本轮踩到）。
    if not os.path.isfile(path):
        raise _bad(path, "文件不存在")
    try:
        d = json.loads(io.open(path, encoding="utf-8").read())
    except ValueError as exc:
        raise _bad(path, "不是合法 JSON（%s）" % exc)
    if not isinstance(d, dict):
        raise _bad(path, "顶层必须是对象")
    if d.get("version") != 2:
        raise _bad("version", "load2 只接受 2（实际 %r）" % (d.get("version"),))
    _check_keys(d, V2_TOP, "")

    for k in ("targets", "modules"):
        if k not in d:
            raise _bad(k, "v2 必须声明 %s" % k)
    if not isinstance(d["modules"], list) or not d["modules"]:
        raise _bad("modules", "必须是非空数组")

    for name, t in (d.get("targets") or {}).items():
        if not isinstance(t, dict):
            raise _bad("targets.%s" % name, "必须是对象")
        _check_keys(t, V2_TARGET, "targets.%s" % name)
        if t.get("dtype") and t["dtype"] not in DTYPE_BYTES:
            raise _bad("targets.%s.dtype" % name,
                       "未知 dtype：%r" % (t["dtype"],))

    seen_ids = set()
    for i, m in enumerate(d["modules"]):
        w = "modules[%d]" % i
        if not isinstance(m, dict):
            raise _bad(w, "必须是对象")
        _check_keys(m, V2_MODULE, w)
        _req(m, ("id", "sources"), w)
        if m["id"] in seen_ids:
            raise _bad("%s.id" % w, "模块 id 重复：%s" % m["id"])
        seen_ids.add(m["id"])
        if not isinstance(m["sources"], list) or not m["sources"]:
            raise _bad("%s.sources" % w, "必须是**非空**数组（模块由哪些 MATLAB 功能拼成）")
        if "timing" in m:
            if not isinstance(m["timing"], dict):
                raise _bad("%s.timing" % w, "必须是对象")
            _check_keys(m["timing"], V2_TIMING, "%s.timing" % w)
        for t in m.get("targets") or []:
            if t not in (d.get("targets") or {}):
                raise _bad("%s.targets" % w, "引用了未声明的 target：%s" % t)
        if "operators" in m and not isinstance(m["operators"], dict):
            raise _bad("%s.operators" % w, "必须是对象（算子名 -> C 符号）")
    if "operators" in d and not isinstance(d["operators"], dict):
        raise _bad("operators", "必须是对象（算子名 -> C 符号）")
    _check_mem(d.get("memory"), "memory")
    _check_dtypes(d.get("dtypes"), "dtypes")
    for name, t in (d.get("targets") or {}).items():
        _check_mem(t.get("memory"), "targets.%s.memory" % name)
    return d


def _check_dtypes(dt, where):
    """DS1/DS2：数据格式与定标的取值必须合法。"""
    if dt is None:
        return
    if not isinstance(dt, dict):
        raise _bad(where, "必须是对象")
    _check_keys(dt, V2_DTYPES, where)
    if "default" in dt and dt["default"] not in DTYPE_BYTES:
        raise _bad("%s.default" % where,
                   "未知 dtype：%r（允许 %s）"
                   % (dt["default"], ", ".join(sorted(DTYPE_BYTES))))
    mp = dt.get("map")
    if mp is not None:
        if not isinstance(mp, dict):
            raise _bad("%s.map" % where, "必须是对象（MATLAB 类型 -> C dtype）")
        for k, v in mp.items():
            if v not in DTYPE_BYTES:
                raise _bad("%s.map.%s" % (where, k), "未知 C dtype：%r" % (v,))
    fx = dt.get("fixed_point")
    if fx is not None:
        if not isinstance(fx, dict):
            raise _bad("%s.fixed_point" % where, "必须是对象")
        _check_keys(fx, V2_FIXED, "%s.fixed_point" % where)
        fmt = fx.get("format")
        if fmt is not None and fmt not in Q_WIDTH:
            raise _bad("%s.fixed_point.format" % where,
                       "只支持 %s" % ", ".join(sorted(Q_WIDTH)))
        fb = fx.get("frac_bits")
        if fb is not None:
            if not isinstance(fb, int) or fb < 0:
                raise _bad("%s.fixed_point.frac_bits" % where, "必须是非负整数")
            if fmt and fb >= Q_WIDTH[fmt]:
                raise _bad("%s.fixed_point.frac_bits" % where,
                           "%d 不小于 %s 的位宽 %d" % (fb, fmt, Q_WIDTH[fmt]))
        if fx.get("round") and fx["round"] not in ROUND_MODES:
            raise _bad("%s.fixed_point.round" % where,
                       "只支持 %s" % ", ".join(ROUND_MODES))
        if fx.get("overflow") and fx["overflow"] not in OVERFLOW_MODES:
            raise _bad("%s.fixed_point.overflow" % where,
                       "只支持 %s" % ", ".join(OVERFLOW_MODES))


def _check_mem(mem, where):
    """校验 memory 段（顶层或某个 target 下）。"""
    if mem is None:
        return
    if not isinstance(mem, dict):
        raise _bad(where, "必须是对象")
    _check_keys(mem, V2_MEM, where)
    strat = mem.get("strategy")
    if strat is not None and strat not in ("static_pool", "heap", "stack"):
        raise _bad("%s.strategy" % where,
                   "只支持 static_pool / heap / stack（实际 %r）" % (strat,))
    for k in ("pool_bytes", "alignment", "max_array_bytes"):
        if k in mem and (not isinstance(mem[k], int) or mem[k] <= 0):
            raise _bad("%s.%s" % (where, k), "必须是正整数")
    arrs = mem.get("arrays")
    if arrs is not None:
        if not isinstance(arrs, list):
            raise _bad("%s.arrays" % where, "必须是数组")
        for i, a in enumerate(arrs):
            w = "%s.arrays[%d]" % (where, i)
            if not isinstance(a, dict):
                raise _bad(w, "必须是对象")
            _check_keys(a, {"name", "elements", "dtype"}, w)
            _req(a, ("name", "elements"), w)
            if a.get("dtype") and a["dtype"] not in DTYPE_BYTES:
                raise _bad("%s.dtype" % w, "未知 dtype：%r" % (a["dtype"],))


def scan_operators(base, cfg, python=None, mir_py=None):
    """**动态侧**：从真实源码扫出用到的算子（OP-* id）。

    用 `translate/mir.py` 跑一遍配置的 `matlab.root`，再从 MIR 文本里收集 `op:OP-XXX`。
    这一步是"动"的来源 —— 配置对不对，要由源码说话。
    """
    import subprocess
    import sys
    import tempfile

    python = python or sys.executable
    mir_py = mir_py or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "mir.py")
    root = os.path.join(base, cfg["matlab"]["root"])
    if not os.path.isdir(root):
        return set(), "matlab.root 不存在：%s" % root
    d = tempfile.mkdtemp(prefix="m2c_scan_")
    out = os.path.join(d, "p.mir")
    cmd = [python, mir_py, root, "-o", out]
    if cfg["matlab"].get("recursive", True):
        cmd.insert(3, "--recursive")
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    if r.returncode != 0 or not os.path.isfile(out):
        return set(), "扫描失败：%s" % r.stdout.decode("utf-8", "replace")[-300:]
    used = set()
    for ln in io.open(out, encoding="utf-8", errors="replace"):
        if ln.startswith("op:"):
            parts = ln.split(":")
            if len(parts) >= 2:
                used.add(parts[1].strip())
    return used, ""


def scan_facts(base, cfg, python=None, mir_py=None):
    """**动态侧**：从 MIR 里取算子集合、数组形状、自调用、每函数算子数。

    返回 `(facts, err)`；`facts` 含 `ops / shapes / recursive / op_counts`。
    """
    import collections
    import subprocess
    import sys
    import tempfile

    python = python or sys.executable
    mir_py = mir_py or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "mir.py")
    root = os.path.join(base, cfg["matlab"]["root"])
    if not os.path.isdir(root):
        return None, "matlab.root 不存在：%s" % root
    d = tempfile.mkdtemp(prefix="m2c_scan_")
    out = os.path.join(d, "p.mir")
    cmd = [python, mir_py, root, "-o", out]
    if cfg["matlab"].get("recursive", True):
        cmd.insert(3, "--recursive")
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    if r.returncode != 0 or not os.path.isfile(out):
        return None, "扫描失败：%s" % r.stdout.decode("utf-8", "replace")[-300:]

    ops, shapes, dts = set(), {}, {}
    recursive, op_counts = set(), {}
    cur = None
    for ln in io.open(out, encoding="utf-8", errors="replace"):
        ln = ln.rstrip("\n")
        if ln.startswith("func:"):
            cur = ln[5:].strip()
            op_counts[cur] = 0
        elif ln.startswith("op:"):
            parts = ln.split(":")
            if len(parts) >= 2:
                ops.add(parts[1].strip())
            if cur:
                op_counts[cur] += 1
        elif ln.startswith("call:"):
            parts = ln.split(":")
            if len(parts) >= 3 and cur and parts[2].strip() == cur:
                recursive.add(cur)
            if cur:
                op_counts[cur] += 1
        elif ln.startswith("arg:") or ln.startswith("ret:") or ln.startswith("var:"):
            parts = ln.split(":")
            if len(parts) >= 3 and parts[2].strip():
                dts[parts[1].strip()] = parts[2].strip()
            if len(parts) >= 4:
                dims = [x for x in parts[3].split(",") if x.strip().isdigit()]
                if dims:
                    n = 1
                    for x in dims:
                        n *= int(x)
                    shapes[parts[1].strip()] = n
    return {"ops": ops, "shapes": shapes, "recursive": recursive,
            "op_counts": op_counts, "dtypes": dts}, ""


def _ops_table():
    """算子表：id -> matlab 名（用于把配置里的 `sum` 解析成 `OP-SUM`）。"""
    try:
        from . import operators as O
    except (ImportError, ValueError):
        import operators as O
    tbl = {}
    for row in getattr(O, "OPERATORS", []):
        mid = row.get("id")
        if mid:
            tbl[mid] = mid
    return tbl


def check_v2(cfg, base, used_ops=None, shape_hits=None,
             recursive_fns=None, op_counts=None, src_dtypes=None):
    """M1–M4 / T1–T4。返回 `{"problems": [...], "warnings": [...]}`。"""
    problems, warnings = [], []
    probs = problems.append
    tbl = _ops_table()

    # ---- 模块关系 ----
    owner = {}
    for m in cfg["modules"]:
        for src in m["sources"]:
            owner.setdefault(src, []).append(m["id"])

    # M4：同一 MATLAB 功能被多个模块引用（未声明共享）
    for src, mods in owner.items():
        if len(mods) > 1 and not str(src).startswith("shared:"):
            probs("M4 函数 %r 被多个模块引用（%s）—— 会生成多份；"
                  "确实要复用请写成 \"shared:%s\"" % (src, ", ".join(mods), src))

    # M1：sources 必须真实存在（用 matlab.root 下是否有同名 .m 判定）
    mroot = os.path.join(base, cfg["matlab"]["root"])
    stems = set()
    if os.path.isdir(mroot):
        for dp, _dn, fn in os.walk(mroot):
            for f in fn:
                if f.lower().endswith(".m"):
                    stems.add(os.path.splitext(f)[0])
    for src in owner:
        name = str(src).split(".")[-1].replace("shared:", "")
        if stems and name not in stems:
            probs("M1 模块引用的函数 %r 在 %s 下找不到对应 .m"
                  % (src, cfg["matlab"]["root"]))

    # ---- 算子替换：M2 / M3 ----
    overrides = dict(cfg.get("operators") or {})
    for m in cfg["modules"]:
        for k, v in (m.get("operators") or {}).items():
            overrides.setdefault(k, v)
    over_ids = set()
    for k in overrides:
        if k in tbl:
            over_ids.add(k)
        else:
            hit = [i for i, _ in tbl.items() if i == "OP-" + k.upper()]
            if hit:
                over_ids.add(hit[0])
            else:
                warnings.append("算子替换 %r 无法对应到任何算子 id（可能拼错）" % k)

    if used_ops is not None:
        # M2：配置替换了、但源码里根本没用到
        for oid in sorted(over_ids - set(used_ops)):
            warnings.append("M2 算子 %s 在配置里被替换，但源码中未使用（多余配置）" % oid)
        # M3：源码用到、但既不是内置实现也没被替换
        # 内置实现 = 算子表里的全部 id（不另写一份清单）
        builtin = set(tbl.keys())

        unknown = sorted(set(used_ops) - builtin - over_ids)
        for oid in unknown[:12]:
            probs("M3 源码用到算子 %s，但既无内置实现也无目标覆盖" % oid)

    # ---- 时序：T1–T4 ----
    targets = cfg.get("targets") or {}
    for m in cfg["modules"]:
        tm = m.get("timing") or {}
        per, dl = tm.get("period_ms"), tm.get("deadline_ms")
        if per is not None and dl is not None and dl > per:
            probs("T1 模块 %s：deadline(%s) > period(%s)" % (m["id"], dl, per))
        if tm.get("entry_kind") == "isr":
            for t in (m.get("targets") or []):
                if (targets.get(t) or {}).get("allow_heap") is not False:
                    probs("T2 模块 %s 是中断入口，但 target %s 未禁止堆分配"
                          % (m["id"], t))
    forbid = ((cfg.get("constraints") or {}).get("forbid_heap") or [])
    for m in cfg["modules"]:
        for t in (m.get("targets") or []):
            if t in forbid and (targets.get(t) or {}).get("allow_heap") is not False:
                probs("T2 target %s 在 forbid_heap 里，但 allow_heap 不是 false" % t)

    # ---- 内存模型：MM1–MM5 ----
    def mem_of(target_name):
        t = (targets.get(target_name) or {}).get("memory")
        return t if t is not None else (cfg.get("memory") or {})

    seen_mem = set()
    for m in cfg["modules"]:
        for tname in (m.get("targets") or [None]):
            key = (m["id"], tname)
            if key in seen_mem:
                continue
            seen_mem.add(key)
            mem = mem_of(tname)
            if not mem:
                continue
            strat = mem.get("strategy")
            if strat == "static_pool":
                tgt = targets.get(tname) or {}
                if tgt.get("allow_heap") is not False:
                    probs("MM1 target %s 用 static_pool，但 allow_heap 不是 false"
                          % tname)
                align = mem.get("alignment")
                pool = mem.get("pool_bytes")
                if align and pool and pool % align:
                    probs("MM2 pool_bytes(%d) 不是 alignment(%d) 的整数倍"
                          % (pool, align))
                arrs = mem.get("arrays") or []
                mx = mem.get("max_array_bytes")
                dt = (tgt.get("dtype") or "f64")
                total = 0
                for a in arrs:
                    ab = a["elements"] * DTYPE_BYTES.get(
                        a.get("dtype") or dt, DTYPE_BYTES.get(dt, 8))
                    total += ab
                    if mx and ab > mx:
                        probs("MM3 数组 %s 占 %d 字节 > max_array_bytes(%d)"
                              % (a["name"], ab, mx))
                if pool and total > pool:
                    probs("MM4 声明数组共 %d 字节 > pool_bytes(%d)" % (total, pool))

    # MM5：声明数组的 elements 与源码实测形状（动静对账）
    if shape_hits:
        # 内存段可能挂在 target 下（嵌入式常见），必须全部扫到
        _mems = [cfg.get("memory") or {}]
        _mems += [t.get("memory") or {} for t in (cfg.get("targets") or {}).values()]
        _arrs = []
        for _m in _mems:
            _arrs.extend(_m.get("arrays") or [])
        for a in _arrs:
            nm = a["name"]
            if nm in shape_hits and shape_hits[nm] != a["elements"]:
                probs("MM5 数组 %s 声明 %d 个元素，源码实测 %d"
                      % (nm, a["elements"], shape_hits[nm]))

    # ---- 数据格式 DS4：默认 dtype 与源码实测对账 ----
    dts_cfg = cfg.get("dtypes") or {}
    if dts_cfg and src_dtypes:
        want = dts_cfg.get("default")
        actual = set(src_dtypes.values())
        fx = dts_cfg.get("fixed_point") or {}
        if want and actual and want not in actual:
            # 有定标或 map 才算"声明了转换"，否则就是配置与源码脱节
            if not fx and not (dts_cfg.get("map")):
                probs("DS4 配置默认 dtype 是 %s，但源码实测是 %s；"
                      "若是有意转换请声明 fixed_point 或 map"
                      % (want, "/".join(sorted(actual))))
            else:
                warnings.append("DS4 默认 dtype %s 与源码 %s 不同（已声明转换）"
                                % (want, "/".join(sorted(actual))))
        for oid_target, t in (cfg.get("targets") or {}).items():
            td = t.get("dtype")
            if td and actual and td not in actual and not fx:
                warnings.append("DS4 target %s 的 dtype %s 与源码 %s 不同，且无定标声明"
                                % (oid_target, td, "/".join(sorted(actual))))

    # ---- 递归禁令 R1 ----
    cons = cfg.get("constraints") or {}
    if cons.get("no_recursion") and recursive_fns:
        for fn in sorted(recursive_fns)[:8]:
            probs("R1 禁止递归，但 %s 有自调用" % fn)

    # R2：入口算子数上限
    moe = cons.get("max_ops_per_entry")
    if moe and op_counts:
        for m in cfg["modules"]:
            e = m.get("entry")
            if e and op_counts.get(e, 0) > moe:
                probs("R2 入口 %s 有 %d 个算子 > max_ops_per_entry(%d)"
                      % (e, op_counts[e], moe))

    return {"problems": problems, "warnings": warnings}


def emit_manifest(cfg, path, used_ops=None):
    """把关系固化成 C 头（嵌入式侧编译期可见）。"""
    L = ["/* 由 translate/project_map.py 生成 —— 勿手改 */",
         "#ifndef M2C_MANIFEST_H", "#define M2C_MANIFEST_H", ""]
    L.append("#define M2C_PROJECT \"%s\"" % cfg["c"].get("project", "?"))
    L.append("#define M2C_MODULE_COUNT %d" % len(cfg["modules"]))
    L.append("")
    for i, m in enumerate(cfg["modules"]):
        mid = m["id"].upper()
        L.append("/* 模块 %s：由 %d 个 MATLAB 功能拼成 */" % (m["id"], len(m["sources"])))
        L.append("#define M2C_%s_SOURCES %d" % (mid, len(m["sources"])))
        tm = m.get("timing") or {}
        if "period_ms" in tm:
            L.append("#define M2C_%s_PERIOD_MS %g" % (mid, tm["period_ms"]))
        if "deadline_ms" in tm:
            L.append("#define M2C_%s_DEADLINE_MS %g" % (mid, tm["deadline_ms"]))
        if tm.get("entry_kind"):
            L.append("#define M2C_%s_ENTRY_KIND \"%s\"" % (mid, tm["entry_kind"]))
        for j, src in enumerate(m["sources"]):
            L.append("#define M2C_%s_SRC%d \"%s\"" % (mid, j, src))
        L.append("")
    mem = cfg.get("memory") or {}
    for tname, t in (cfg.get("targets") or {}).items():
        if t.get("memory"):
            mem = t["memory"]
            break
    if mem:
        L.append("/* 内存模型（嵌入式） */")
        if mem.get("strategy"):
            L.append("#define M2C_MEM_STRATEGY \"%s\"" % mem["strategy"])
        if mem.get("pool_bytes"):
            L.append("#define M2C_MEM_POOL_BYTES %d" % mem["pool_bytes"])
        if mem.get("alignment"):
            L.append("#define M2C_MEM_ALIGNMENT %d" % mem["alignment"])
        for i, a in enumerate(mem.get("arrays") or []):
            L.append("#define M2C_MEM_ARR%d_NAME \"%s\"" % (i, a["name"]))
            L.append("#define M2C_MEM_ARR%d_ELEMS %d" % (i, a["elements"]))
        L.append("")

    over = dict(cfg.get("operators") or {})
    for m in cfg["modules"]:
        over.update(m.get("operators") or {})
    if over:
        L.append("/* 算子替换 */")
        for k, v in sorted(over.items()):
            L.append("#define M2C_OP_%s %s" % (k.upper().replace("-", "_"), v))
        L.append("")
    if used_ops:
        L.append("/* 实际用到的算子（由源码扫描得出） */")
        for oid in sorted(used_ops):
            L.append("#define M2C_USES_%s 1" % oid.replace("-", "_"))
        L.append("")
    L.append("#endif")
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    return path


def _main_v2(cfg_path, argv, as_json):
    """v2 的入口：静态校验 + 动态扫算子 + 可选 manifest。"""
    base = os.path.dirname(os.path.abspath(cfg_path))
    try:
        cfg = load2(cfg_path)
    except ConfigError as exc:
        print("配置不合规：%s" % exc)
        return 2

    facts, err = scan_facts(base, cfg)
    if err:
        print("[warn] %s（跳过 M2/M3/MM5/R1 对账）" % err)
        facts = None
    used = facts["ops"] if facts else None
    res = check_v2(cfg, base, used,
                   shape_hits=facts["shapes"] if facts else None,
                   recursive_fns=facts["recursive"] if facts else None,
                   op_counts=facts["op_counts"] if facts else None,
                   src_dtypes=facts["dtypes"] if facts else None)

    if as_json:
        print(json.dumps({"used_operators": sorted(used) if used else None,
                          "problems": res["problems"],
                          "warnings": res["warnings"]},
                         ensure_ascii=False, indent=1))
    else:
        print("工程：%s ｜ 模块 %d 个 ｜ target %d 个"
              % (cfg["c"].get("project", "?"), len(cfg["modules"]),
                 len(cfg.get("targets") or {})))
        for m in cfg["modules"]:
            tm = m.get("timing") or {}
            print("  [%s] <- %s%s"
                  % (m["id"], " + ".join(m["sources"]),
                     ("   period=%sms deadline=%sms entry=%s"
                      % (tm.get("period_ms"), tm.get("deadline_ms"),
                         tm.get("entry_kind"))) if tm else ""))
        if used is not None:
            print("  源码实际用到算子 %d 个" % len(used))
        for w in res["warnings"]:
            print("[warn] %s" % w)
        for p in res["problems"]:
            print("[problem] %s" % p)

    if "--emit-manifest" in argv:
        i = argv.index("--emit-manifest")
        out = argv[i + 1] if len(argv) > i + 1 else "m2c_manifest.h"
        emit_manifest(cfg, out, used)
        print("manifest 已写出：%s" % out)

    return 1 if res["problems"] else 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cfg_path = argv[0]
    as_json = "--json" in argv
    try:
        raw = json.loads(io.open(cfg_path, encoding="utf-8").read())
    except (ValueError, IOError) as exc:
        print("配置不合规：%s" % exc)
        return 2
    if raw.get("version") == 2:
        return _main_v2(cfg_path, argv, as_json)
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
