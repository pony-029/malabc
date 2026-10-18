# -*- coding: utf-8 -*-
"""matlabc_lsp.py —— LSP 最小版。

第一版只做三件事：

    initialize            -> capabilities.textDocumentSync = 1（full 同步）
    textDocument/didOpen  -> **先返回**，再异步算（证明不阻塞协议循环）
    textDocument/publishDiagnostics -> 诊断与 `--json` 的 heuristics 同源

**唯一硬判据**（R137 文档 §3）：

    LSP 对某个 .m 文件发出的诊断
      == `matlabc.py <root> --json` 的 heuristics 里属于该文件的条目

它同时锁死三件事：stdout 没被 `print` 污染、行号没做二次偏移、诊断不是另算一遍。

两个约定（不许散落）：

- **行号 0-based 只在本文件转换**（`--json` 是 1-based）；
- **severity 映射只在本文件维护**（`level -> LSP severity`）。

用法：

    python matlabc_lsp.py            # 作为 LSP 服务（stdin/stdout 协议）

退出码：0 = 正常 EOF / `exit`；2 = 缺输入（找不到 matlabc.py）
"""
import io
import json
import os
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MATLABC = os.path.join(HERE, "matlabc.py")

#: `--json` 的 `level` -> LSP severity（1=Error 2=Warning 3=Information 4=Hint）
SEVERITY = {"error": 1, "warning": 2, "note": 3, "info": 3, "hint": 4}

_STATE = {"root": None, "payload": None, "result": None,
          "lock": threading.Lock()}


def _log(msg):
    sys.stderr.write("[matlabc] %s\n" % msg)
    sys.stderr.flush()


# --------------------------------------------------------------------------
# 协议分帧
# --------------------------------------------------------------------------
def _read_message(stream):
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        try:
            key, val = line.decode("ascii").split(":", 1)
        except ValueError:
            continue
        headers[key.strip().lower()] = val.strip()
    try:
        n = int(headers.get("content-length", "0") or 0)
    except ValueError:
        return None
    if n <= 0:
        return None
    body = stream.read(n)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        return None


def _write_message(stream, obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body))
    stream.write(body)
    stream.flush()


# --------------------------------------------------------------------------
# 分析：**只走 CLI**，不自己算（否则就是第二事实源）
# --------------------------------------------------------------------------
def _heuristics_from_result(result):
    """把 `PipelineResult` 的 `doc_todos` 压成与 `--json` 的 `heuristics`
    **同一形状**的列表。

    `--json` 里那条（`matlabc.py` 的 `render_json`）就是：

        {"file": rel, "line": line, "func": func,
         "kind": "m_missing_doc", "msg": "...", "level": "note"}
        for t in doc_todos["todos"] if "description" in t["missing"]

    这里逐字复刻同一个过滤条件与同一组字段 —— 两个来源必须是**同一批数据**，
    否则「诊断 == heuristics」这条判据就没意义了。
    """
    model = getattr(result, "model", None)
    todos = (getattr(model, "doc_todos", None) or {}).get("todos") or []
    out = []
    for t in todos:
        if "description" not in (t.get("missing") or []):
            continue
        out.append({
            "file": t.get("rel") or "",
            "line": t.get("line") or 0,
            "func": t.get("func") or "",
            "kind": "m_missing_doc",
            "msg": "函数缺少头部描述（description）",
            "level": "note",
        })
    return out


def _facts_from_result(result):
    """从 `result.facts` 派生诊断 —— **F3 之后它是唯一来源**。

    F1 时 facts 只含 `m_missing_doc`（`evidence="ast"`，5 条，与 `--json`
    的 `heuristics` 逐条相等）。F3 之后它还会含 `uninitialized` /
    `dead_code`（`evidence="check"`），所以 LSP 能发的不止一类 —— 而
    「诊断 ⊇ heuristics」这条超集关系**由构造保证**，不需要额外对账。

    形状映射：facts 的 `loc` / `payload` -> LSP 需要的
    `{file, line, func, kind, msg, level}`。
    """
    out = []
    for f in (getattr(result, "facts", None) or []):
        loc = f.get("loc") or {}
        pl = f.get("payload") or {}
        subject = f.get("subject") or ""
        out.append({
            "file": loc.get("file") or "",
            "line": int(loc.get("line") or 0),
            "func": subject.rsplit(":", 1)[-1] if ":" in subject else "",
            "kind": pl.get("rule_id") or "unknown",
            "msg": pl.get("msg") or "",
            "level": pl.get("level") or "note",
        })
    return out


def _cache_path(root):
    return os.path.join(root, ".matlabc_lsp_cache.json")


def _stamp(root):
    """所有 `.m` 的**最大 mtime** —— 任何一个文件改过，缓存就作废。

    **不能只看根目录的 mtime**：改的是子目录里的文件，根目录不变。
    **也不能只看文件数**：文件数不变而内容改了，是最常见的情况。
    """
    newest = 0.0
    try:
        for dirpath, dirnames, names in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for n in names:
                if n.endswith(".m"):
                    try:
                        st = os.stat(os.path.join(dirpath, n))
                        if st.st_mtime > newest:
                            newest = st.st_mtime
                    except OSError:
                        pass
    except OSError:
        return 0.0
    return newest


#: 缓存里每条**函数记录**必须保存的字段 —— **唯一清单**。
#:
#: R237：这是第五次动这块代码。前四次都是「新功能用到了新字段，忘了
#: 存进缓存」：`signature` → `call_sites` → `field_access` →
#: `external_calls`，症状永远是同一个 —— **冷启动对、重启后哑**。
#:
#: 根因不是某一次疏忽，而是**保存与恢复是两份手写清单**。现在两边都
#: 只读这一份；加字段就改这里一行。配套判据 `struct/cache-fn-keys`
#: 核对产物键集合与它逐字相同，漏改会红。
_CACHED_FN_FIELDS = ("name", "line", "complexity", "header", "sig",
                     "call_sites", "external_calls", "indirect_calls")

#: 从 JSON 恢复时必须转成整数的字段（`json` 只有 float）。
_INT_FN_FIELDS = ("line", "complexity")

#: 文件级字段清单（**一处构造**）。
#: 加字段只改这里一行 —— `_save_cache` 与 `_load_cache` 都从它推导。
#: R319 之前这里是两份手写清单，于是同一个洞漏了三次：
#:   R233 漏 `field_access` → 结构体跳转静默失效
#:   R294 漏 `lines`        → 大纲范围退化成一点
#:   R319 漏 `globals`      → 全局变量被当成局部变量
#: 每次都是「缓存重建的对象比真解析少几个字段」，且只有走到特定功能才暴露。
_CACHED_MF_FIELDS = ("rel", "header", "globals", "lines", "kind")


def _fn_to_cache(fn):
    """`MatlabFunction` -> 可 JSON 化的函数记录（键集合由清单决定）。"""
    try:
        sig = fn.signature()
    except Exception:
        sig = getattr(fn, "name", "")
    # `call_sites` 两种形状：内存版 `[line, col, end, MatlabFunction]`，
    # 缓存版 `[line, "rel:name"]`。已经是缓存形状就原样保留 —— 否则
    # 命中缓存后再写一次会把行号清空。
    sites = []
    for st in (getattr(fn, "call_sites", None) or []):
        try:
            line = int(st[0])
        except (IndexError, TypeError, ValueError):
            continue
        if len(st) >= 2 and isinstance(st[1], str):
            sites.append([line, st[1]])
            continue
        try:
            tgt = st[3]
        except (IndexError, TypeError):
            continue
        trel = getattr(getattr(tgt, "mfile", None), "rel", "") or ""
        tname = getattr(tgt, "name", "") or ""
        if tname:
            sites.append([line, "%s:%s" % (trel, tname)])

    out = {}
    for k in _CACHED_FN_FIELDS:
        if k == "sig":
            out[k] = sig
        elif k == "call_sites":
            out[k] = sites
        elif k == "header":
            v = getattr(fn, "header", None)
            out[k] = v if isinstance(v, dict) else {}
        elif k in ("external_calls", "indirect_calls"):
            v = getattr(fn, k, None)
            out[k] = dict(v) if isinstance(v, dict) else {}
        else:
            out[k] = getattr(fn, k, None)
    return out


def _cache_to_fn(d):
    """缓存记录 -> `SimpleNamespace`（键集合同样由清单决定）。"""
    from types import SimpleNamespace as NS
    o = NS()
    for k in _CACHED_FN_FIELDS:
        if k == "sig":
            # `_hover` 调 `fn.signature()`；这里补一个返回固定串的方法。
            # 两层 lambda 是为了把当前值钉住（循环变量延迟绑定）。
            o.signature = (lambda s: (lambda: s))(d.get("sig", "") or "")
        elif k == "call_sites":
            o.call_sites = [tuple(x) for x in (d.get("call_sites") or [])]
        elif k in ("external_calls", "indirect_calls"):
            v = d.get(k)
            setattr(o, k, dict(v) if isinstance(v, dict) else {})
        elif k == "header":
            v = d.get(k)
            setattr(o, k, v if isinstance(v, dict) else {})
        elif k in _INT_FN_FIELDS:
            try:
                setattr(o, k, int(d.get(k) or 0))
            except (TypeError, ValueError):
                setattr(o, k, 0)
        else:
            setattr(o, k, d.get(k))
    if not isinstance(getattr(o, "name", None), str):
        o.name = ""
    return o


def _save_cache(root, payload, result):
    """把「结构层 + 诊断」写盘。失败不算错（缓存是可选的）。"""
    try:
        files_src = getattr(result, "files", None) or []
        files = []
        for mf in files_src:
            fns = []
            for fn in (getattr(mf, "functions", None) or []):
                # **一处构造**：键集合由 `_CACHED_FN_FIELDS` 决定。
                fns.append(_fn_to_cache(fn))
            # **键集合由 `_CACHED_MF_FIELDS` 决定**（一处构造）。
            rec = {}
            for _k in _CACHED_MF_FIELDS:
                rec[_k] = getattr(mf, _k, None)
            # 归一化：JSON 没有元组/None 的语义，也不该把 None 写进去。
            rec["rel"] = rec["rel"] or ""
            rec["header"] = rec["header"] or {}
            rec["globals"] = list(rec["globals"] or [])
            rec["lines"] = int(rec["lines"] or 0)
            rec["kind"] = rec["kind"] or ""
            rec["functions"] = fns
            files.append(rec)
        edges = []
        for e in (getattr(result, "edges", None) or []):
            if isinstance(e, dict):
                edges.append([e.get("caller"), e.get("callee"),
                              bool(e.get("cross_file"))])
            elif isinstance(e, (list, tuple)) and len(e) >= 2:
                edges.append([e[0], e[1], bool(e[2]) if len(e) > 2 else False])
        # **每一步都留痕**：R209 在 YALMIP（1665 文件 / 20225 边）上
        # 连 `.tmp` 都没留下，而 `sample_m` 一次就成功 —— 唯一的差异是规模。
        # 没有这些日志，只能猜是「构造慢」「序列化失败」还是「replace 失败」。
        _log("缓存构造完成 %d 文件 / %d 边" % (len(files), len(edges)))
        stamp = _stamp(root)
        _log("缓存 stamp=%.0f" % stamp)
        # `complete` 是**必需字段**：R216 实测，一份 `payload` 为空的手工缓存
        # 被命中后，诊断永远是 0 条。而「0 条诊断」本身是合法结果
        # （比如 `sample_uninit` 的 heuristics 就是 0，但 facts 有 1 条），
        # 所以不能拿「payload 是否为空」判断缓存完整度 —— 必须在写的时候
        # 明确记下「这份缓存是完整跑完的」。
        # `field_access` 也必须存：结构体跳转全靠它（R201），而它同样
        # **只在 `render_json` 里构建**，缓存重建的对象上没有。
        # R233 实测：漏了它之后，缓存命中时 `s.name` 的跳转静默返回 `[]`。
        try:
            import matlabc as _M
            field_access = _M._collect_cross_file_fields(files_src)
        except Exception as exc:
            _log("缓存里的 field_access 构建失败：%r" % (exc,))
            field_access = {}
        doc = {"v": 4, "complete": True, "stamp": stamp, "files": files,
               "edges": edges, "payload": payload,
               "field_access": field_access}
        try:
            js = json.dumps(doc, ensure_ascii=False)
        except Exception as exc:
            _log("缓存序列化失败（形状不可序列化）：%r" % (exc,))
            return
        _log("缓存序列化 %.1f KB" % (len(js) / 1024.0))
        tmp = _cache_path(root) + ".tmp"
        with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(js)
        _log("缓存临时文件已写，准备 rename")
        os.replace(tmp, _cache_path(root))
        _log("缓存已写 %d 文件 / %d 边" % (len(files), len(edges)))
    except Exception as exc:
        _log("缓存写入失败（不影响使用）：%r" % (exc,))


def _load_cache(root):
    """读缓存；**任何异常都当作没有缓存**（截断的 JSON / 旧 schema / 无权限）。"""
    p = _cache_path(root)
    if not os.path.isfile(p):
        return None
    try:
        with io.open(p, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception as exc:
        _log("缓存不可读，忽略：%r" % (exc,))
        return None
    # **v=4**：R319 补了 `globals` / `lines` / `kind`。v3 的缓存缺它们，
    # 命中后全局变量会被当成局部变量、大纲 range 退化。
    # 宁可让用户多等一次分析，也不给一份"看起来能用但某些功能是哑的"缓存。
    if not isinstance(doc, dict) or doc.get("v") != 4:
        _log("缓存 schema 不符（v=%r，需要 4），忽略" % (doc.get("v"),))
        return None
    if doc.get("complete") is not True:
        # 没有 `complete: true` 的是**旧缓存或半成品**（R216 之前写的全部如此）。
        # 认它们的后果是诊断永远为空，而用户看不出为什么。
        _log("缓存不完整（缺 complete 标记），忽略并重算")
        return None
    try:
        cur = _stamp(root)
        if abs(float(doc.get("stamp") or 0) - cur) > 1e-6:
            _log("缓存已过期（stamp %.0f -> %.0f）" % (doc.get("stamp") or 0, cur))
            return None
    except Exception:
        return None
    try:
        from types import SimpleNamespace as NS
        files = []
        for f in doc.get("files") or []:
            fns = []
            for fn in f.get("functions") or []:
                # **一处恢复**：键集合同样由 `_CACHED_FN_FIELDS` 决定。
                # 以前这里和 `_save_cache` 是两份手写清单，于是四次漏字段。
                fns.append(_cache_to_fn(fn))
            # **键集合同样由 `_CACHED_MF_FIELDS` 决定**（一处构造）。
            kw = {}
            for _k in _CACHED_MF_FIELDS:
                kw[_k] = f.get(_k)
            kw["rel"] = kw["rel"] or ""
            kw["header"] = kw["header"] or {}
            kw["globals"] = list(kw["globals"] or [])
            kw["lines"] = int(kw["lines"] or 0)
            kw["kind"] = kw["kind"] or ""
            files.append(NS(functions=fns, **kw))
        edges = [tuple(e) for e in (doc.get("edges") or [])]
        result = NS(files=files, edges=edges,
                    field_access=doc.get("field_access") or {})
        _log("缓存命中：%d 文件 / %d 边" % (len(files), len(edges)))
        return result, doc.get("payload") or {"heuristics": []}
    except Exception as exc:
        _log("缓存重建失败，忽略：%r" % (exc,))
        return None


def _is_live_result(res):
    """这个结果里的函数对象是不是**活的**（真解析产物，而非缓存重建的替身）。

    R268：`analyze(prev=, changed=)` 会原样复用 `prev` 里的对象。而缓存
    重建出来的 `SimpleNamespace` 只带少数几个字段（R233 就因此让结构体
    跳转静默失效）。**拿替身当 `prev` 会产出降级结果**，所以必须先问一句：
    这些对象身上有 `body_start` 吗？有才是活的。
    """
    for mf in (getattr(res, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            return hasattr(f, "body_start")
    return False


def _run_json(root, prev=None, changed=None):
    """**进程内**跑分析，返回与 `--json` 同形的 `{"heuristics": [...]}`。

    为什么不再起子进程：CLI 全流程实测 **5.92s**（1300 个 .m），而
    `analyzer.api.analyze` 进程内只要 **0.73s** —— 差的 5.2 秒是
    `collect_files` 的 `os.walk`、JSON 序列化与进程启动，LSP 一样都用不上。

    仍然传 `no_checks=True`：诊断只需要 `doc_todos`，而 `_collect_checks`
    占 63%（未关时）。
    """
    # **先试磁盘缓存**：命中就跳过全部解析（第二次开同一项目从 35 秒到 0.2 秒）。
    # 但**给了 `prev` 就不读缓存** —— 那是增量路径，复用的是内存里的活对象，
    # 混进磁盘替身会把两条路径的语义搅在一起（`_is_live_result` 守的就是这件事）。
    # `stamp` 校验保证「改过任何一个 .m 就作废」，所以命中时结果与重算一致。
    if prev is None:
        hit = _load_cache(root)
        if hit is not None:
            result0, payload0 = hit
            _STATE["result"] = result0
            return payload0

    try:
        from analyzer.api import analyze
    except ImportError as exc:
        _log("无法 import analyzer.api：%s" % exc)
        return None
    try:
        # **不能传 `no_checks=True`**：F3 之后 facts 里那两类告警
        # （`c_uninit_read` / `m_dead_code`）正是由 `_collect_checks` 产的，
        # 关掉它等于把 F3 刚扩的东西全部丢掉 —— 实测 `--uninit` 会一直红。
        # 代价是首次分析慢一些（1300 个 .m：0.73s -> 2.18s），仍在可用区间。
        if prev is not None and changed:
            # 增量：只重解析 `changed` 里的文件，其余沿用活对象。
            # 一致性由第 30 道门守着（`check_incremental_parity`：
            # 逐文件各测一次，files 与 edges 必须与全量逐项相同）。
            result = analyze(root, prev=prev, changed=changed)
        else:
            result = analyze(root)
    except Exception as exc:                  # 分析失败不能让服务挂掉
        _log("analyze 失败：%r" % (exc,))
        return None
    # 留住整个 `PipelineResult`：`definition` 要用 `files[].functions[]`
    # 的 `(name, line)`，而 `heuristics` 只够发诊断。
    _STATE["result"] = result
    # F3：改读 `facts`。它现在（F1 之后）与 `heuristics` 逐条相等，所以
    # 「诊断 == heuristics」那条旧判据仍然成立；等 facts 扩了两类，
    # 关系自动变成「⊇」——两者都是构造保证的，不需要两处对账。
    payload = {"heuristics": _facts_from_result(result)}
    _save_cache(root, payload, result)
    return payload


def _field_written_on_left(root, cand, base, field):
    """`base.field` 是否出现在该行的 `=` **左侧**（即真的在这里被赋值）。

    R306：`field_index` 的写入点里混着读取行 —— `a.ub = a.lb + 1;` 的
    `a.lb` 也被记进去了。判据只看行号就分不出"写"和"读"，于是跳转会
    落在读取处。这里读一次该行，做最朴素的判断。

    读不到文件就返回 False（让调用方退回按行号取第一条，不因此报错）。
    """
    try:
        rel, _fn, ln = cand[0], cand[1], cand[2]
        if not rel or not ln:
            return False
        path = os.path.join(root, rel.replace("/", os.sep))
        line = io.open(path, "r", encoding="utf-8",
                       errors="replace").read().splitlines()[int(ln) - 1]
    except (IOError, OSError, IndexError, TypeError, ValueError):
        return False
    code = line.split("%", 1)[0] if "%" in line else line
    if "=" not in code:
        return False
    left = code.split("=", 1)[0]
    return ("%s.%s" % (base, field)) in left


def _base_ident(lines, line0, ch):
    """`model.lb` 里光标在 `lb` 上 -> 返回 `model`（基名）。

    R305：字段写入点带基名，判断时必须用上 —— 否则同名不同对象的字段
    会混成一个池子（实测 `lb` 有 1301 个写入点）。

    只取**紧邻的那个点**前面一段；`a.b.c` 取 `b`（`c` 是 b 的字段），
    与 MATLAB 的 `a.b.c` 语义一致。找不到返回 None。

    字符判定**只认 ASCII**：`isalnum()` 会把中文也当地名（R272 的教训）。
    """
    if not (0 <= line0 < len(lines)):
        return None
    ln = lines[line0]
    i = ch - 1
    if i < 0 or i >= len(ln) or ln[i] != ".":
        return None
    j = i - 1
    while j >= 0:
        c = ln[j]
        if c == "_" or ("0" <= c <= "9") or ("a" <= c <= "z") \
                or ("A" <= c <= "Z"):
            j -= 1
        else:
            break
    base = ln[j + 1:i]
    if not base or "0" <= base[0] <= "9":
        return None
    return base


def _ident_at(lines, line0, char):
    """取 `line0` 行 `char` 位置上的最长标识符（`[A-Za-z0-9_]`）。"""
    if line0 < 0 or line0 >= len(lines):
        return None
    s = lines[line0]
    i = min(max(0, char), len(s))
    start, end = i, i
    # **只认 ASCII 标识符**（R272）。`str.isalnum()` 对中文返回 True，
    # 于是悬停中文注释里的词会被当成名字，再去查函数必然查不到，
    # 最后输出「`反例语料` 不是函数」—— 一句正确但毫无意义的话。
    # MATLAB 的标识符是 `[A-Za-z0-9_]`，范围本来就该这么窄。
    def _ok(c):
        return (("a" <= c <= "z") or ("A" <= c <= "Z")
                or ("0" <= c <= "9") or c == "_")
    while start > 0 and _ok(s[start - 1]):
        start -= 1
    while end < len(s) and _ok(s[end]):
        end += 1
    if start == end:
        return None
    word = s[start:end]
    if not word:
        return None
    # 首字符不能是数字（`2x` 不是标识符）
    if not (("a" <= word[0] <= "z") or ("A" <= word[0] <= "Z")
            or word[0] == "_"):
        return None
    return word


def _wait_result(timeout=90.0):
    """等首次分析完成，再返回结果。

    `didOpen` 是**异步**的（后台线程跑 `_run_json`），而 F12 可能比它先到。
    原来每个读请求都直接读 `_STATE["result"]`，此时是 None 就直接
    返回 `[]` —— 在大工作区上（`E:\matlabc`，首次分析 10s+）用户会看到
    「未找到定义」，而实际上分析还在跑（R196 日志：F12 在 8 秒后返回 0 个位置）。

    改成等待。阻塞的是这一个请求，换回来的是**正确结果**而不是空。
    """
    import time as _t
    deadline = _t.time() + timeout
    while _t.time() < deadline:
        r = _STATE.get("result")
        if r is not None:
            return r
        _t.sleep(0.02)
    _log("_wait_result 超时 %.0fs，返回 None" % timeout)
    return None


def _field_index(result):
    """跨文件字段索引（惰性、只算一次）。

    两条来源，**顺序不能反**：

      ① `_STATE["field_index"]` —— 本进程已经算过
      ② `result.field_access` —— 缓存命中时由 `_load_cache` 挂上去的
      ③ 现场算 —— 只有真正跑过 `analyze` 的完整结果才算得动

    ⚠ 缓存重建的 `SimpleNamespace` **没有 `kind` / `source_lines`**，
    所以 ③ 在那条路径上会 `AttributeError`。R233 实测：结构体跳转
    因此静默返回 `[]` —— 用户看到的是「这个字段没有定义」，而不是
    「缓存里缺了字段索引」。

    `field_access` **只在 `render_json` 里构建**（`matlabc.py` 的 L14133），
    所以 `analyze()` 的 `result` 上没有它 —— 这就是为什么 ③ 必须自己
    调一次 `_collect_cross_file_fields`。

    缓存挂在 `_STATE` 上：一次 `didOpen` 只付一次代价。
    """
    # **按 result 对象身份校验**，而不是「有就返回」。
    # R235 实测：保存之后 `_STATE["result"]` 换成了新对象，而 field_index
    # 还是旧的 —— 于是新增/删除的字段永远看不见，`didSave` 也治不好它。
    # 在 5 个赋值点各加一行清理的写法，漏一处就复发；这里一次解决。
    idx = _STATE.get("field_index")
    if idx is not None and _STATE.get("field_index_for") is result:
        return idx
    # 缓存命中时 `_load_cache` 已经把索引挂在 `result` 上了。
    cached = getattr(result, "field_access", None)
    if isinstance(cached, dict) and cached:
        _STATE["field_index"] = cached
        _STATE["field_index_for"] = result
        return cached
    try:
        import matlabc as _M
        idx = _M._collect_cross_file_fields(
            getattr(result, "files", None) or [])
    except Exception as exc:                  # 字段索引失败不许影响跳转
        _log("_field_index 失败：%r" % (exc,))
        idx = {}
    _STATE["field_index"] = idx
    _STATE["field_index_for"] = result
    return idx


def _definition(uri, pos):
    """`textDocument/definition`：光标处标识符 -> 它的定义位置。

    判据（写在 `vscode/README.md` 里）：

        `a.m:3` 的 `b`  -> `a.m:6`（同文件，行号 0-based 5）
        `a.m:13` 的 `d` -> `d.m:1`（跨文件，行号 0-based 0）
        注释上          -> `[]`（不许假装跳转）

    **查找顺序是同文件优先**：同名函数可能定义在多个文件里，
    最近的那个是"按确定性回答"，不是"猜"。
    """
    result = _wait_result(timeout=2.0)
    root = _STATE.get("root")
    if result is None or not root:
        return []
    path = _uri_to_path(uri)
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except (IOError, OSError):
        return []
    line0 = int(pos.get("line", 0))
    ch = int(pos.get("character", 0))
    name = _ident_at(lines, line0, ch)
    if name is None:
        return []

    # ---- R306：**注释里的名字不跳转** ----------------------------------
    # `_ident_at` 只看字符，分不清这是代码还是注释；于是文档注释里写到
    # `b.lb` 或 `foo(...)` 时按 F12 会跳到别处 —— 一个「看起来成功了」的
    # 错误跳转。函数名早就有这条判据（注释上 -> []），字段与变量没有。
    # 取舍：`'100%'` 这类字符串里的 `%` 会被当注释起点而漏跳一次，
    # 这比「跳到错的地方」好。
    if 0 <= line0 < len(lines):
        _pct = lines[line0].find("%")
        if _pct >= 0 and ch >= _pct:
            return []

    # ---- R201：`s.FIELD` 的跳转 ---------------------------------------
    # 光标前一个字符是 `.` ⇒ 这是字段访问，不是函数名。
    # 查 `field_access` 的**第一个写入点**（按文件、行排序）作为定义。
    #
    # 官方 IDE 做不到：它没有跨文件的字段解析，只能文本搜索 `.FIELD`，
    # 那会把 `S.FIELD`、`x.FIELD`、注释里的 `.FIELD` 混在一起。
    is_field = False
    if 0 <= line0 < len(lines):
        _ln = lines[line0]
        if 0 < ch <= len(_ln) and _ln[ch - 1] == ".":
            is_field = True
    if is_field:
        fa = _field_index(result)
        ent = fa.get(name) or {}
        writes = ent.get("writes") or []
        if not writes:
            return []
        # ---- R305：**先认基名** ----------------------------------------
        # 写入点里带基名（`model.lb` 的 `model`），但之前完全没用：
        # 实测 `lb` 在 YALMIP 里有 1301 个写入点，`model.lb` / `pRed.lb` /
        # `s.lb` 全混在一起，取排序第一 = 随便挑一个，等于没回答。
        # 同一基名的写入点才是「这个对象上的这个字段」。
        base = _base_ident(lines, line0, ch)
        same = [w for w in writes if base and len(w) > 3 and w[3] == base]
        pool = sorted((same or writes), key=lambda r: (r[0], r[2] or 0))
        # **优先取「写在等号左边」的那一处**（R306）。
        # `field_index` 的 writes 里混着读取行（实测：`a.ub = a.lb + 1;`
        # 里的 `a.lb` 也被记成写入点），只按行号取第一条会落在读取处。
        # 只在同基名的前若干个候选里找，不做全池 IO。
        first = None
        for _cand in pool[:40]:
            if _field_written_on_left(root, _cand, base, name):
                first = _cand
                break
        if first is None:
            first = pool[0]
        rel_f, ln1 = first[0], first[2] or 1
        target = os.path.join(root, rel_f.replace("/", os.sep))
        return [{
            "uri": "file:///" + target.replace("\\", "/").lstrip("/"),
            "range": {"start": {"line": max(0, int(ln1) - 1), "character": 0},
                      "end": {"line": max(0, int(ln1) - 1),
                              "character": len(name)}},
        }]

    # ---- R228：结构体**变量本身**的跳转 --------------------------------
    # 光标在 `s` 上、且紧跟一个 `.` ⇒ 用户问的是「这个 s 是哪来的」，
    # 不是「这个字段在哪定义」。
    #
    # `analyze` 不记录变量定义（`field_access` 记的是**字段**，不是变量），
    # 所以这里现场扫本文件：第一个 `s = ...` 或 `s.field = ...`。
    # 后者也收，因为 MATLAB 里结构体可以**靠字段赋值隐式创建**，
    # 没有显式的 `s = struct()`。
    if 0 <= line0 < len(lines):
        _ln = lines[line0]
        end_ch = ch + len(name)
        if end_ch < len(_ln) and _ln[end_ch] == ".":
            pat = re.compile(r"^\s*%s\s*[.=]" % re.escape(name))
            for i, ln in enumerate(lines):
                # 注释里的不算（`%` 之后整段丢弃；字符串里的 `%` 会让
                # 这条判断偏保守，最坏是漏一个候选，不会指错位置）
                code = ln.split("%", 1)[0] if "%" in ln else ln
                if pat.match(code):
                    col = code.index(name) if name in code else 0
                    return [{
                        "uri": "file:///" + path.replace("\\", "/").lstrip("/"),
                        "range": {"start": {"line": i, "character": col},
                                  "end": {"line": i,
                                          "character": col + len(name)}},
                    }]
            return []

    hits = []
    for mf in (getattr(result, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            if getattr(f, "name", None) == name:
                hits.append((getattr(mf, "rel", "") or "",
                             getattr(f, "line", 1)))
    # ---- R305：全局变量先认 `global` 声明 ------------------------------
    # MATLAB 里 global 名字的出处是 `global X` 那一行，而不是它某次赋值。
    # 之前在 expandmodel.m 里按 F12 会跳到第 45 行的赋值，而声明在第 9 行。
    # 先本文件、再全库（其他文件也可能声明同名 global）。
    _gpat = re.compile(r"^\s*global\b[^\n]*\b%s\b" % re.escape(name))
    for _i, _ln in enumerate(lines):
        _code = _ln.split("%", 1)[0] if "%" in _ln else _ln
        if _gpat.match(_code):
            _col = _code.find(name)
            return [{
                "uri": "file:///" + path.replace("\\", "/").lstrip("/"),
                "range": {"start": {"line": _i, "character": max(0, _col)},
                          "end": {"line": _i,
                                  "character": max(0, _col) + len(name)}},
            }]
    for _mf in (getattr(result, "files", None) or []):
        if name not in (getattr(_mf, "globals", None) or []):
            continue
        _rel = getattr(_mf, "rel", "") or ""
        if _rel == rel:                      # 本文件已查过
            continue
        _p = os.path.join(root, _rel.replace("/", os.sep))
        try:
            _other = io.open(_p, "r", encoding="utf-8",
                             errors="replace").read().splitlines()
        except (IOError, OSError):
            continue
        for _i, _ln in enumerate(_other):
            _code = _ln.split("%", 1)[0] if "%" in _ln else _ln
            if _gpat.match(_code):
                return [{
                    "uri": "file:///" + _p.replace("\\", "/").lstrip("/"),
                    "range": {"start": {"line": _i, "character": 0},
                              "end": {"line": _i, "character": len(name)}},
                }]

    if not hits:
        # ---- R300：变量 / 局部名的「声明」 ------------------------------
        # MATLAB 没有声明语句，`x = ...` 就是它成立的地方（HTML 报告里
        # 也是这么找的）。函数查不到时再退一步找本文的首次赋值 ——
        # 比「按 F12 什么都不发生」有用得多。
        # 只在本文件里找：跨文件的变量没有意义（MATLAB 的变量是函数级的）。
        _pat = re.compile(r"^\s*(?:\[[^\]]*\]\s*=\s*)?"
                          r"%s\s*(?:\([^)]*\))?\s*=" % re.escape(name))
        for _i, _ln in enumerate(lines):
            _code = _ln.split("%", 1)[0] if "%" in _ln else _ln
            if _pat.match(_code):
                _col = _code.find(name)
                return [{
                    "uri": "file:///" + path.replace("\\", "/").lstrip("/"),
                    "range": {"start": {"line": _i,
                                        "character": max(0, _col)},
                              "end": {"line": _i,
                                      "character": max(0, _col) + len(name)}},
                }]
        return []

    want = os.path.basename(path).lower()
    same = [h for h in hits if os.path.basename(h[0]).lower() == want]
    rel, line1 = (same or hits)[0]
    line0 = max(0, int(line1 or 1) - 1)       # ← 唯一的 1-based -> 0-based
    target = os.path.join(root, rel.replace("/", os.sep))
    return [{
        "uri": "file:///" + target.replace("\\", "/").lstrip("/"),
        "range": {"start": {"line": line0, "character": 0},
                  "end": {"line": line0, "character": len(name)}},
    }]


def _uri_to_path(uri):
    """`file:///E:/a/b.m` -> `E:/a/b.m`。"""
    p = uri or ""
    if p.startswith("file:///"):
        p = p[8:]
    elif p.startswith("file://"):
        p = p[7:]
    from urllib.parse import unquote
    p = unquote(p)
    if os.name == "nt" and len(p) > 2 and p[0] == "/" and p[2] == ":":
        p = p[1:]
    return p.replace("/", os.sep)


def _warm():
    """后台预热：`initialize` 一到就开始分析，**不等 `didOpen`**。

    这是 Source Insight 的做法 —— **导入项目即建索引**，用户点开文件时
    结果已经在了，而不是等第一次 F12 才现算。

    原来只在 `didOpen` 里分析，所以首次跳转要等：
      - `E:\\matlabc` 这种大工作区 10 秒以上（R196 用户实测的「未找到定义」）
      - 1665 文件的 YALMIP 约 4 秒

    幂等：`payload` 已存在就直接返回（`didOpen` 之后会再调一次，那次是空转）。
    """
    root = _STATE.get("root")
    if not root:
        return
    with _STATE["lock"]:
        if _STATE["payload"] is not None:
            return

    # **必须区分「已就绪」与「正在跑」**：只检查 `payload is None` 时，
    # `initialize` 的预热和 `didOpen` 的 `_later` 会**同时**跑一遍 analyze。
    # 实测 YALMIP（1665 文件）：单次约 30s，双跑就变成 60s+，
    # 而 `_wait_result` 等 90s 会超时 —— 用户看到「未找到定义」。
    with _STATE["lock"]:
        if _STATE.get("warming"):
            return
        _STATE["warming"] = True

    t0 = time.time()
    _log("预热开始 %s" % root)
    try:
        # **缓存命中就不分层**：读盘 0.2 秒，再拆两步毫无意义。
        hit = _load_cache(root)
        if hit is not None:
            result0, payload0 = hit
            with _STATE["lock"]:
                _STATE["result"] = result0
                _STATE["payload"] = payload0
            _log("预热完成（缓存）%s -> %.1fs" % (root, time.time() - t0))
            return

        # ---- ① 结构层：`no_checks=True` ------------------------------
        # 实测（S0）：它产出的 `files` / `functions` / `edges` 与全量**逐项相同**，
        # 只是 `facts` 为空 —— 而 F12 / 引用 / 悬停 / 大纲**只需要结构**。
        # 所以先把它交出去，用户 12 秒就能跳转，而不是等 35 秒。
        if _STATE.get("result") is None:
            t_struct = time.time()
            try:
                from analyzer.api import analyze as _analyze
                struct = _analyze(root, no_checks=True)
            except Exception as exc:
                _log("结构层失败（退回单层预热）：%r" % (exc,))
                struct = None
            if struct is not None:
                with _STATE["lock"]:
                    if _STATE.get("result") is None:
                        _STATE["result"] = struct
                _log("结构层就绪 %.1fs（F12/悬停/大纲 现在可用）"
                     % (time.time() - t_struct))

        # ---- ② 诊断层：全量（含 `_collect_checks`）-------------------
        payload = _run_json(root)
        with _STATE["lock"]:
            if _STATE["payload"] is None:
                _STATE["payload"] = payload
        _log("预热完成 %s -> %.1fs，%d 条诊断"
             % (root, time.time() - t0,
                len((payload or {}).get("heuristics") or [])))
    finally:
        with _STATE["lock"]:
            _STATE["warming"] = False


def _diagnostics_for(uri):
    """从缓存的 payload 里取出**该文件**的诊断。

    过滤依据：`heuristics[].file` 与 uri 的相对路径（或 basename）相等。
    `--json` 的 `file` 是相对 root 的 posix 路径。
    """
    payload = _STATE.get("payload")
    root = _STATE.get("root")
    if not payload or not root:
        return []
    path = _uri_to_path(uri)
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        rel = os.path.basename(path)
    base = os.path.basename(rel)

    out = []
    for h in payload.get("heuristics") or []:
        hf = (h.get("file") or "").replace("\\", "/")
        if hf != rel and os.path.basename(hf) != base:
            continue
        line1 = int(h.get("line") or 1)
        line0 = max(0, line1 - 1)               # ← 唯一的 1-based -> 0-based
        out.append({
            "range": {"start": {"line": line0, "character": 0},
                      "end": {"line": line0, "character": 1}},
            "severity": SEVERITY.get((h.get("level") or "note").lower(), 3),
            "code": h.get("kind") or "heuristic",
            "source": "matlabc",
            "message": h.get("msg") or "",
        })
    return out


def _references(uri, pos, include_decl):
    """`textDocument/references`：**函数级**引用（不是行级）。

    语义边界如实：`analyze` 的 `edges` 是 `(caller, callee, ambiguous)` 三元组，
    **不带行号**。所以这里给的是「哪个函数调用了它」，落点是那个调用者的
    **定义行**，不是调用发生的那一行。要行级引用，得先让 `edges` 带 `line`。

    `includeDeclaration=True` 时把光标所在函数自己的定义也加进去。
    """
    result = _wait_result(timeout=2.0)
    root = _STATE.get("root")
    if result is None or not root:
        return []
    path = _uri_to_path(uri)
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except (IOError, OSError):
        return []
    name = _ident_at(lines, int(pos.get("line", 0)),
                     int(pos.get("character", 0)))
    if name is None:
        return []
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        rel = os.path.basename(path)
    # ---- R309：全局变量的跨文件引用 ------------------------------------
    # 函数级的 `edges` 里没有全局变量，所以走到这里会返回空 —— 而用户要的
    # 恰恰是「这个 G_CFG 在哪些文件里出现」。
    # 只扫**声明过它的文件**：MATLAB 里不 `global` 声明就用不了它，
    # 所以这个范围既正确又便宜（YALMIP 1676 文件里只有 45 个带 global）。
    if any(name in (getattr(_mf, "globals", None) or [])
           for _mf in (getattr(result, "files", None) or [])):
        _hit = re.compile(r"\b%s\b" % re.escape(name))
        _gout = []
        for _mf in (getattr(result, "files", None) or []):
            if name not in (getattr(_mf, "globals", None) or []):
                continue
            _mrel = getattr(_mf, "rel", "") or ""
            _p = os.path.join(root, _mrel.replace("/", os.sep))
            try:
                _ls = io.open(_p, "r", encoding="utf-8",
                              errors="replace").read().splitlines()
            except (IOError, OSError):
                continue
            for _i, _ln in enumerate(_ls):
                _code = _ln.split("%", 1)[0] if "%" in _ln else _ln
                if not _hit.search(_code):
                    continue
                _col = _code.find(name)
                # **分三类**（R311）：全局变量只有一个「定义」（赋值），
                # 其余文件里的 `global X` 只是**声明**（多个），还有纯读取的
                # 使用点。混在一起会让人以为它被定义了好几次。
                if re.match(r"^\s*global\b", _code):
                    _kind = "declare"
                elif "=" in _code and _code.index("=") > _col:
                    _kind = "define"
                else:
                    _kind = "use"
                _gout.append({
                    "kind": _kind,
                    "uri": "file:///" + _p.replace("\\", "/").lstrip("/"),
                    "range": {"start": {"line": _i,
                                        "character": max(0, _col)},
                              "end": {"line": _i,
                                      "character": max(0, _col) + len(name)}},
                })
        return _gout

    target = "%s:%s" % (rel, name)

    keys = []
    if include_decl:
        keys.append(target)
    for e in (getattr(result, "edges", None) or []):
        if len(e) >= 2 and e[1] == target:
            keys.append(e[0])

    fn_by_key = {}
    for mf in (getattr(result, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            fn_by_key["%s:%s" % (getattr(mf, "rel", ""),
                                 getattr(f, "name", ""))] = f

    out = []
    for key in keys:
        if ":" not in key:
            continue
        krel, kname = key.rsplit(":", 1)
        fn = fn_by_key.get(key)
        line0 = max(0, int(getattr(fn, "line", 1) or 1) - 1)
        tgt = os.path.join(root, krel.replace("/", os.sep))
        out.append({
            "uri": "file:///" + tgt.replace("\\", "/").lstrip("/"),
            "range": {"start": {"line": line0, "character": 0},
                      "end": {"line": line0, "character": len(kname)}},
        })
    return out


#: 内置函数词典（`data/builtin_zh.json`）。惰性加载，只读一次。
_BUILTIN_DOC = None

#: 说明语言：`both`（默认，中文在前）/ `zh` / `en`。
#: 由扩展通过环境变量传入 —— LSP 是子进程，读不到 VSCode 的设置。
_DOC_LANG = os.environ.get("MATLABC_DOC_LANG", "both")


def _builtin_doc(name):
    """查内置函数的中英说明；查不到返回 `None`。"""
    global _BUILTIN_DOC
    if _BUILTIN_DOC is None:
        here = os.path.dirname(os.path.abspath(__file__))
        # 两个位置都要试：
        #   ① `<here>/data/…`           —— 打包后（`extension/data/`）
        #   ② `<here>/vscode/data/…`    —— 仓库内（`matlabc_lsp.py` 在仓库根，
        #                                  词典在 `vscode/data/`）
        cands = [
            os.path.join(here, "data", "builtin_zh.json"),
            os.path.join(here, "vscode", "data", "builtin_zh.json"),
        ]
        _BUILTIN_DOC = {}
        for path in cands:
            if not os.path.isfile(path):
                continue
            try:
                with io.open(path, "r", encoding="utf-8") as fh:
                    _BUILTIN_DOC = json.load(fh)
                _log("内置词典已加载：%s（%d 条）" % (path, len(_BUILTIN_DOC)))
                break
            except Exception as exc:
                _log("内置词典读取失败（%s）：%r" % (path, exc))
        if not _BUILTIN_DOC:
            _log("内置词典不存在，试过：%r" % (cands,))
    return _BUILTIN_DOC.get(name)


def _format_builtin(name, doc):
    """中文优先，同时保留英文 —— 两个都要，因为 MATLAB 的文档生态是英文的。"""
    zh = (doc.get("zh") or "").strip()
    en = (doc.get("en") or "").strip()
    parts = ["```matlab", "%s(...)" % name, "```", ""]
    if _DOC_LANG in ("both", "zh") and zh:
        parts.append("**%s**" % zh)
    if _DOC_LANG == "both" and zh and en:
        parts.append("")
    if _DOC_LANG in ("both", "en") and en:
        parts.append("_%s_" % en)
    parts.append("")
    parts.append("MATLAB 内置函数 · 用户未重写")
    return "\n".join(parts)


#: C 源文件函数索引的缓存。键是工程根，`result` 一变就作废。
#: `model` 保留完整 C 模型（含 edges），用于回答「这个 C 函数又调了谁」。
_C_INDEX = {"key": None, "idx": None, "nfiles": 0, "model": None}

#: 二进制（mex / dll / so）索引缓存：名字 -> [{rel, kind}]
_BIN_INDEX = {"key": None, "idx": None, "nfiles": 0}

#: PE 导出表缓存：绝对路径 -> (mtime, [导出名小写])
_PE_CACHE = {}

#: 视为「可调用二进制」的扩展名。mex 的入口名 = 文件名（去掉 mex* 后缀）。
_BIN_EXTS = (".mexw64", ".mexa64", ".mexmaci64", ".mexw32",
             ".dll", ".so", ".dylib")


def _pe_exports(path):
    """读 PE 的导出符号名（只读名字，不碰机器码）。

    为什么值得做：`calllib('mylib','foo')` 的 `foo` 在 MATLAB 侧永远是
    「未解析」，于是调用链在这里断掉。而「`foo` 确实是 mylib.dll 导出的」
    这个事实，足以让断点变成一个**有名字的出口**，而不是一处空白。

    返回小写名字集合；解析失败返回空集（不抛异常 —— 坏文件不该拖垮请求）。
    """
    try:
        st = os.stat(path)
    except OSError:
        return set()
    hit = _PE_CACHE.get(path)
    if hit and hit[0] == st.st_mtime:
        return hit[1]
    names = set()
    try:
        data = io.open(path, "rb").read()
    except Exception:
        _PE_CACHE[path] = (st.st_mtime, names)
        return names
    try:
        if len(data) < 0x40 or data[:2] != b"MZ":
            raise ValueError("not pe")
        import struct
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
            raise ValueError("no pe sig")
        coff = e_lfanew + 4
        nsec = struct.unpack_from("<H", data, coff + 2)[0]
        opt_size = struct.unpack_from("<H", data, coff + 16)[0]
        opt = coff + 20
        magic = struct.unpack_from("<H", data, opt)[0]
        # 数据目录在可选头里的偏移：PE32 = 96，PE32+ = 112
        dd = opt + (96 if magic == 0x10B else 112)
        exp_rva, exp_size = struct.unpack_from("<II", data, dd)
        if not exp_rva or not exp_size:
            raise ValueError("no export dir")

        # 节表：把 RVA 换成文件偏移
        sec = opt + opt_size
        sections = []
        for k in range(nsec):
            base = sec + k * 40
            vsize = struct.unpack_from("<I", data, base + 8)[0]
            vaddr = struct.unpack_from("<I", data, base + 12)[0]
            raw_size = struct.unpack_from("<I", data, base + 16)[0]
            raw_ptr = struct.unpack_from("<I", data, base + 20)[0]
            sections.append((vaddr, max(vsize, raw_size), raw_ptr))

        def off_of(rva):
            for vaddr, size, raw in sections:
                if vaddr <= rva < vaddr + size:
                    return raw + (rva - vaddr)
            return None

        ed = off_of(exp_rva)
        if ed is None:
            raise ValueError("export dir unmapped")
        n_names = struct.unpack_from("<I", data, ed + 24)[0]
        arr = struct.unpack_from("<I", data, ed + 32)[0]
        arr_off = off_of(arr)
        if arr_off is None or n_names > 20000:
            raise ValueError("bad name table")
        for i in range(n_names):
            nrva = struct.unpack_from("<I", data, arr_off + i * 4)[0]
            noff = off_of(nrva)
            if noff is None:
                continue
            end = data.find(b"\0", noff)
            if end < 0 or end - noff > 512:
                continue
            nm = data[noff:end].decode("ascii", "replace").strip()
            if nm:
                names.add(nm.lower())
    except Exception:
        names = set()
    _PE_CACHE[path] = (st.st_mtime, names)
    return names


def _rea_status():
    """报告 rea（`morluto/rea`）是否可用 —— **只探测，不调用**。

    为什么只探测：rea 是 Node 22+ 的 MCP 服务，走的是「matlabc 作 MCP 客户端
    去调它」的协议级联邦（见 docs/analysis/ANALYSIS_2026-10-08 §10.1 通道①）。
    在它真的握手成功之前，**任何「已接入 rea」的说法都是假的**。

    所以这里只回答两件事：能不能跑起来；不能的话卡在哪。
    """
    out = {"available": False, "node": None, "rea": None, "reason": "",
           # **能跑 ≠ 能干活**（R345）。rea 的 `inspect-binary-layout` 实测只吃
           # Linux x64 ELF：对 `kernel32.dll` 直接返回 capability_unavailable。
           # 不写这一条，`available: true` 会让人以为 Windows DLL 也有更深结论。
           "binary_scope": "linux-elf",
           "binary_scope_note":
               u"rea 的二进制布局分析仅支持 Linux x64（实测对 kernel32.dll "
               u"返回 capability_unavailable）"}
    try:
        import shutil as _sh
        node = _sh.which("node")
        rea = _sh.which("rea")
    except Exception:
        node, rea = None, None

    # PATH 可能还没刷新（刚装完 Node 的进程仍看不到它）。补两个常见位置，
    # 否则「刚装好却报不可用」会被当成装失败。
    def _fallback(paths):
        for p in paths:
            if os.path.isfile(p):
                return p
        return None

    if not node:
        node = _fallback([r"C:\Program Files\nodejs\node.exe",
                          os.path.expanduser(
                              r"~\AppData\Local\Programs\nodejs\node.exe")])
    if not rea:
        rea = _fallback([
            os.path.expanduser(r"~\AppData\Roaming\npm\rea.cmd"),
            os.path.expanduser(r"~\AppData\Roaming\npm\rea"),
        ])

    out["node"] = node
    out["rea"] = rea
    if not node:
        out["reason"] = u"node 不在 PATH（rea 需要 Node 22+）"
    elif not rea:
        out["reason"] = u"rea 未安装（npm i -g rea-agents）"
    else:
        out["available"] = True
    return out


def _bin_index(root):
    """工程内的 mex / dll / so：名字 -> [{rel, kind}]。

    **名字就是入口**：MATLAB 调用 `foo` 时，同目录的 `foo.mexw64` 提供它 ——
    不需要解析任何机器码就能把这一环接上。dll 则是给 `calllib` 用的。
    """
    key = os.path.abspath(root or "")
    if _BIN_INDEX["key"] == key and _BIN_INDEX["idx"] is not None:
        return _BIN_INDEX["idx"]
    idx, n = {}, 0
    try:
        for dirpath, dirnames, filenames in os.walk(key):
            dirnames[:] = [d for d in dirnames if d not in _C_SKIP_DIRS]
            for fn in filenames:
                low = fn.lower()
                if not low.endswith(_BIN_EXTS):
                    continue
                for ext in _BIN_EXTS:
                    if low.endswith(ext):
                        base = fn[:-len(ext)]
                        break
                else:
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn),
                                      key).replace(os.sep, "/")
                idx.setdefault(base.lower(), []).append({"rel": rel, "kind": ext})
                n += 1
            if n >= 300:
                break
    except (IOError, OSError):
        pass
    _BIN_INDEX["key"] = key
    _BIN_INDEX["idx"] = idx
    _BIN_INDEX["nfiles"] = n
    _log("二进制索引：%d 个文件" % n)
    return idx

#: 扫描 C 源时跳过的目录：这些地方的 .c 不是工程代码，扫进来只会拖慢。
_C_SKIP_DIRS = (".git", ".matlabc", "node_modules", "build", "cmake-build-debug")


def _c_index(root):
    """C 源文件的「函数名 → (相对路径, 行号)」索引。

    为什么只做这一层：`mex`/`calllib` 导致的「链条断了」，缺的不是 C 的
    表达式语义，而是**一个能连上去的落点** —— 名字对上、行号可跳，
    链路就从「未解析」变成「进入 C 层，从这里进去」。

    复用 `matlabc.build_c_model`（项目已有的 C 前端），不另写一套解析：
    同一个 .c 文件被两套正则解析，迟早给出两个答案。
    """
    key = os.path.abspath(root or "")
    if _C_INDEX["key"] == key and _C_INDEX["idx"] is not None:
        return _C_INDEX["idx"]

    idx = {}
    files = []
    try:
        for dirpath, dirnames, filenames in os.walk(key):
            dirnames[:] = [d for d in dirnames if d not in _C_SKIP_DIRS]
            for fn in filenames:
                low = fn.lower()
                if low.endswith(".c") or low.endswith(".cpp") or low.endswith(".cc"):
                    files.append(os.path.join(dirpath, fn))
            if len(files) >= 200:       # 上限：宁可少桥接几个，也别卡住整个请求
                break
    except (IOError, OSError):
        files = []

    # **必须先初始化**：没有 C 文件的工程会跳过下面的 if，
    # 而缓存写入要读 `model` —— 否则 UnboundLocalError（R346 当场踩到）。
    model = None
    if files:
        try:
            import matlabc as _M
            model = _M.build_c_model(sorted(files)[:200], key)
        except Exception as exc:
            _log("C 索引失败：%r" % (exc,))
            model = None
        for low, hits in ((model or {}).get("func_index") or {}).items():
            for h in hits:
                try:
                    rel = (h.get("file") or {}).get("rel") or ""
                    fn = h.get("func") or {}
                    idx.setdefault(low, []).append({
                        "name": fn.get("name") or low,
                        "rel": rel,
                        "line": int(fn.get("line") or 0),
                    })
                except Exception:
                    continue

    _C_INDEX["key"] = key
    _C_INDEX["idx"] = idx
    _C_INDEX["nfiles"] = len(files)
    # 保留完整模型：`edges` 用来回答「这个 C 函数又调了谁」——
    # 只留名字和行号的话，链路到了 C 入口就又断一次，等于只接了一半。
    _C_INDEX["model"] = model
    _log("C 索引：%d 个文件 / %d 个函数 / %d 条边"
         % (len(files), len(idx), len((model or {}).get("edges") or [])))
    return idx


def _c_bridge(name):
    """MATLAB 函数 → C 函数的桥接（按**未解析调用名**匹配）。

    返回 `{"available": bool, "reason": str, "items": [...]}`。
    `available=False` 的两种原因必须分开：没有 C 文件 vs 索引还没建好 ——
    否则界面只能猜，而猜出来的「没有桥接」和「还没算」长得一样。
    """
    # **开关先判**（R345）：跨语言分析要扫 C 源、读 PE 导出表，在几万个文件
    # 的工程上是实打实的 IO。默认开着（没有 C/二进制时它自己会立刻返回空，
    # 成本接近零），但必须能关。
    # ⚠ 顺序：**必须在 `pending` 之前**。否则用户关掉开关后，界面会先看到
    # 「分析中…」，等分析完了才说「已关闭」—— 那个等待毫无意义。
    if not _STATE.get("cross_lang", True):
        return {"available": False, "reason": "disabled", "items": [],
                "rea": _rea_status()}

    result = _STATE.get("result")
    if result is None:
        return {"available": False, "reason": "pending", "items": [],
                "rea": _rea_status()}

    root = _STATE.get("root") or ""
    idx = _c_index(root)
    # **二进制也算一层**（R343）：只有 .mexw64 / .dll、没有 .c 的工程很常见
    # （正是「预编译工具箱」那种）。第一版在这里只看 C 索引，于是这类工程
    # 直接被判成「没有可桥接的东西」—— 而 mex 的名字本来就写在文件名上。
    bidx = _bin_index(root)
    if not idx and not bidx:
        return {"available": False, "reason": "no_sources", "items": [],
                "scanned": 0, "rea": _rea_status()}

    items, matched = [], set()
    all_ext = set()
    for mf in (getattr(result, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            if getattr(f, "name", "") != name:
                continue
            for cname, cnt in (getattr(f, "external_calls", None) or {}).items():
                all_ext.add(cname)
                for h in idx.get(cname.lower(), []):
                    # C 内部的下一跳（R346）：只接住 C 入口而不往下走，
                    # 等于把「链断了」的问题往后挪了一层。
                    # ⚠ 边的形状是 **4 元组** `(caller, callee, line, rel)`，
                    # 而 `build_c_model` 的 docstring 写的是 3 元组 ——
                    # 我按 docstring 写了解包，当场 ValueError，还把整个
                    # 关系面板打挂。这里改为按位取 + 整体兜底：
                    # **新增一个字段，绝不能成为打挂主视图的理由。**
                    _down = []
                    try:
                        _cm = _C_INDEX.get("model") or {}
                        _by_caller = {}
                        for _e in (_cm.get("edges") or []):
                            try:
                                _by_caller.setdefault(_e[0], []).append(
                                    (_e[1], int(_e[2] or 0)))
                            except (IndexError, TypeError, ValueError):
                                continue
                        # **BFS 展开 3 层**（R347）：只展开一层等于「到 C 入口
                        # 再往下看一眼就停」—— 真实调用链常常是 A→B→C。
                        # `_seen` 防环：C 里互递归并不罕见，没有它就会转圈。
                        _seen = set([h["name"]])
                        _q = [(h["name"], 1)]
                        while _q and len(_down) < 30:
                            _cur, _dep = _q.pop(0)
                            if _dep > 3:
                                break
                            for _cn, _cl in _by_caller.get(_cur, []):
                                if _cn in _seen:
                                    continue
                                _seen.add(_cn)
                                _down.append({"name": _cn, "line": _cl,
                                              "depth": _dep})
                                _q.append((_cn, _dep + 1))
                    except Exception:
                        _down = []
                    items.append({"matlab": name,
                                  "mfile": getattr(mf, "rel", "") or "",
                                  "callee": cname,
                                  "count": int(cnt),
                                  "c_name": h["name"],
                                  "c_rel": h["rel"],
                                  "c_line": h["line"],
                                  "c_down": _down,
                                  # **证据来源**（R344）：读者必须能分清
                                  # 「内置 PE/C 解析得到的」与「外部工具给的」。
                                  # 没有来源标注的结论，事后无从复核。
                                  "source": "c-source"})
                    matched.add(cname)
    # 同一 (C 位置) 去重：一个 MATLAB 函数可能多处调用同一个 C 函数
    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: (x["c_rel"], x["c_line"])):
        k = (it["c_rel"], it["c_line"], it["c_name"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    # ---- 二进制层（R343）----------------------------------------------
    # mex 的入口名就是文件名：`foo.mexw64` 提供 `foo`，不需要解析机器码。
    # 这一层能把「未解析」缩小到真正的未知（工具箱 / 动态调用）。
    bins = []
    still = set(all_ext) - matched
    for nm in sorted(still):
        for h in bidx.get(nm.lower(), []):
            bins.append({"matlab": name, "callee": nm,
                         "rel": h["rel"], "kind": h["kind"].lstrip("."),
                         "entry": nm, "source": "mex-filename"})
            still.discard(nm)
            break

    # `calllib('lib','fn')`：库名与函数名都在字面量里，可以直接核对
    # 「这个函数确实是这个库导出的」——这是二进制能给的最强保证。
    calllib = []
    for mf in (getattr(result, "files", None) or []):
        if getattr(mf, "rel", "") and not any(
                getattr(f, "name", "") == name
                for f in (getattr(mf, "functions", None) or [])):
            continue
        p = os.path.join(root, (getattr(mf, "rel", "") or "").replace("/", os.sep))
        try:
            text = io.open(p, "r", encoding="utf-8", errors="replace").read()
        except (IOError, OSError):
            continue
        for m in re.finditer(r"calllib\s*\(\s*'([^']+)'\s*,\s*'([^']+)'", text):
            lib, fn = m.group(1), m.group(2)
            libhits = bidx.get(lib.lower(), [])
            if not libhits:
                calllib.append({"lib": lib, "fn": fn, "rel": None,
                                "exported": None, "source": "library-missing"})
                continue
            librel = libhits[0]["rel"]
            exports = set()
            if librel.lower().endswith((".dll", ".so", ".dylib")):
                exports = _pe_exports(os.path.join(root,
                                                   librel.replace("/", os.sep)))
            calllib.append({"lib": lib, "fn": fn, "rel": librel,
                            "exported": (fn.lower() in exports) if exports else None,
                            "source": "pe-export" if exports else "filename-only"})

    # **仍连不上的**要单独列出来（R342）：它们可能是 mex 二进制、
    # 工具箱函数、或动态调用 —— 与「已经桥接到 C 源」是两回事。
    # 第一版把 `matched` 当成了全体，于是这一栏永远是空的（当场验证发现）。
    return {"available": True, "items": uniq,
            "scanned": _C_INDEX.get("nfiles") or 0,
            "binaries": bins,
            "calllib": calllib,
            "bin_scanned": _BIN_INDEX.get("nfiles") or 0,
            "unresolved": sorted(still),
            "external_total": len(all_ext),
            # 外部二进制工具是否可用。**true 才代表真的能调**；
            # false 时附原因，读者不必猜「为什么没有更深的证据」。
            "rea": _rea_status()}


def _field_refs(name):
    """结构体字段的**跨文件读写位置**（`matlabc/field`）。

    为什么单独一个方法：`_references` 返回的是 `Location[]`，语义是「谁引用了
    这个名字」，而字段真正要回答的是「谁在**写**它、谁在**读**它、挂在哪些
    基名上」。塞进 `references` 会把这两种问题混成一个列表 —— 截图里
    `options.coneprog` 被当成局部变量显示，就是这么来的。

    返回 `None` 表示这个名字不是字段（调用方据此回落到变量分支）。
    """
    result = _STATE.get("result")
    if result is None:
        return None
    try:
        idx = _field_index(result)
    except Exception:
        return None
    ent = (idx or {}).get(name)
    if not ent:
        return None

    def norm(rows):
        out = []
        for r in (rows or []):
            r = list(r or []) + ["", "", 0, "?"]
            line = int(r[2] or 0)
            out.append({"rel": r[0] or "", "func": r[1] or "",
                        "line": line, "base": r[3] or "?"})
        out.sort(key=lambda x: (x["rel"], x["line"]))
        return out

    writes = norm(ent.get("writes"))
    reads = norm(ent.get("reads"))
    if not writes and not reads:
        return None
    bases = sorted(set(x["base"] for x in (writes + reads)))
    return {"writes": writes, "reads": reads, "bases": bases}


def _hover(uri, pos):
    """`textDocument/hover`：光标处标识符 -> 函数的签名 / 描述 / 复杂度。

    数据全部来自 `MatlabFunction` 的现成字段，**不重新解析**：
    `signature()` / `header["description"]` / `complexity`。
    找不到时返回 `None`（LSP 里 `null` 表示"这里没有可悬停的信息"）。
    """
    result = _wait_result(timeout=2.0)
    if result is None:
        return None
    path = _uri_to_path(uri)
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except (IOError, OSError):
        return None
    _cur_line = int(pos.get("line", 0))
    name = _ident_at(lines, _cur_line, int(pos.get("character", 0)))
    if name is None:
        return None

    # ---- R271：先问「它是不是**当前函数的参数**」----------------------
    # 参数名不是函数，以前会一路落到「本库内没有名为 x 的函数」那条分支 ——
    # 而它明明就写在眼前这个函数的签名里。**那不是“查不到”，是“问错了”。**
    # 位置保证：只有光标所在文件的、光标之上最近的那个 function 才算数，
    # 所以不会把别处的同名参数认成这里的。
    _root = _STATE.get("root")
    _rel = None
    if _root:
        try:
            _rel = os.path.relpath(path, _root).replace("\\", "/")
        except (ValueError, OSError):
            _rel = None
    if _rel:
        _owner = None
        for _mf in (getattr(result, "files", None) or []):
            if (getattr(_mf, "rel", "") or "") != _rel:
                continue
            for _f in (getattr(_mf, "functions", None) or []):
                if int(getattr(_f, "line", 0) or 0) - 1 <= _cur_line:
                    if _owner is None or int(_f.line) > int(_owner.line):
                        _owner = _f
            break
        if _owner is not None and getattr(_owner, "name", "") != name:
            _pn, _pt, _pc = _param_names(_owner, limit=99)
            if name in _pn:
                _i = _pn.index(name)
                _ty = _pt[_i] if _i < len(_pt) else ""
                _body = ["**参数** `%s`" % name]
                if _ty:
                    _body.append("")
                    _body.append("类型 `%s`" % _ty)
                _body.append("")
                _body.append("属于 `%s`（`%s:%d`）"
                             % (getattr(_owner, "name", ""), _rel,
                                int(getattr(_owner, "line", 0) or 1)))
                _body.append("")
                _body.append("参数 %d 个%s"
                             % (_pc, "" if _ty else "（头部注释里没有类型说明）"))
                return {"contents": {"kind": "markdown",
                                     "value": "\n".join(_body)}}

    hit = None
    for mf in (getattr(result, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            if getattr(f, "name", None) == name:
                hit = (mf, f)
                break
        if hit:
            break
    if hit is None:
        # **内置函数**：用户没重写它，就查中英词典（R213）。
        # 「重写的函数除外」是这条分支的位置保证的 —— `files[]` 永远优先，
        # 只有没被用户定义过的名字才会落到这里。
        doc = _builtin_doc(name)
        if doc:
            return {"contents": {"kind": "markdown",
                                 "value": _format_builtin(name, doc)}}

        # ---- R235：找不到定义时**必须解释**，不许沉默 ----------------
        #
        # 用户报的现象：`lb(1)` 看着像调用、CodeLens 上也有数字，F12 却
        # 什么都没发生。实测 YALMIP：
        #   `lb` 不是函数、不是内置，而是**结构体字段**（全库 4601 次读写）
        #   `external_calls` 共 24582 次，`ub`/`x0`/`dim`/`solver` 全是字段
        #
        # **跳不过去是对的**（它本来就没有定义），**沉默是错的** ——
        # 用户会以为是扩展坏了。
        fa = _field_index(result)
        ent = fa.get(name)
        if isinstance(ent, dict):
            w = ent.get("writes") or []
            rd = ent.get("reads") or []
            out = ["```matlab", "%s（结构体字段）" % name, "```", "",
                   "**这是字段，不是函数。** `%s(...)` 是字段取值，"
                   "没有独立定义可跳。" % name, "",
                   "全库：写入 %d 处 · 读取 %d 处" % (len(w), len(rd))]
            if w:
                first = sorted(w, key=lambda x: (x[0], x[2] or 0))[0]
                out.append("")
                out.append("首次写入：`%s:%s` —— 那是它事实上的定义点"
                           % (first[0], first[2]))
            return {"contents": {"kind": "markdown", "value": "\n".join(out)}}

        # 第二类：出现在**当前函数**的 `external_calls` 里 —— 被当成调用
        # 记过，但本库没有定义（toolbox 函数，或者同样是变量索引）。
        row = int(pos.get("line", 0)) + 1
        try:
            rel_here = os.path.relpath(path, _STATE.get("root") or "").replace("\\", "/")
        except ValueError:
            rel_here = ""
        fn_here = None
        for mf2 in (getattr(result, "files", None) or []):
            if (getattr(mf2, "rel", "") or "") != rel_here:
                continue
            for f2 in (getattr(mf2, "functions", None) or []):
                ln2 = int(getattr(f2, "line", 0) or 0)
                if 0 < ln2 <= row and (fn_here is None or ln2 > int(
                        getattr(fn_here, "line", 0) or 0)):
                    fn_here = f2
        if fn_here is not None:
            ext = getattr(fn_here, "external_calls", None) or {}
            if isinstance(ext, dict) and name in ext:
                return {"contents": {"kind": "markdown", "value": "\n".join([
                    "```matlab", "%s(...)" % name, "```", "",
                    "**本库内没有名为 `%s` 的函数。**" % name, "",
                    "它出现在 `%s` 的外部调用表里（%d 次）—— 通常是 "
                    "toolbox 函数，或者是变量/字段被当成了调用。"
                    % (getattr(fn_here, "name", "?"), ext.get(name) or 1),
                ])}}

        # ---- R272：到这里还什么都不说，是最差的选择 --------------------
        # 它既不是函数、不是内置、不是字段、不是参数，也不在外部调用表里。
        # 以前这里 `return None` —— 界面一片安静，用户分不清是
        # **自己拼错了**、**还是扩展坏了**。
        #
        # 现在至少把「它可能是什么」说清楚：在本函数体里被赋值 ⇒ 局部变量
        # （或循环变量）；连赋值都没有 ⇒ 老实说「不认识这个名字」。
        # **不猜它是函数，也不假装知道它的类型。**
        if fn_here is not None:
            _start = int(getattr(fn_here, "line", 0) or 1)
            _starts = sorted(int(getattr(f3, "line", 0) or 0)
                             for f3 in (getattr(mf2, "functions", None) or []))
            _next = None
            for _ln3 in _starts:
                if _ln3 > _start:
                    _next = _ln3
                    break
            _end = (_next - 1) if _next else len(lines)
            _pat_set = re.compile(r"^\s*%s\s*(?:\([^)]*\))?\s*="
                                  % re.escape(name))
            _pat_for = re.compile(r"^\s*for\s+%s\s*=" % re.escape(name))
            _hits = []
            _is_for = False
            for _i in range(max(0, _start - 1), min(_end, len(lines))):
                _code = lines[_i].split("%", 1)[0]
                if _pat_for.match(_code):
                    _is_for = True
                    _hits.append(_i + 1)
                elif _pat_set.match(_code):
                    _hits.append(_i + 1)
            _who = getattr(fn_here, "name", "?")
            if _hits:
                _kind = "循环变量" if _is_for else "局部变量"
                return {"contents": {"kind": "markdown", "value": "\n".join([
                    "```matlab", name, "```", "",
                    "**`%s` 不是函数**，它是 `%s` 里的**%s**。"
                    % (name, _who, _kind), "",
                    "在 `%s`（`%s:%d`）里被赋值 %d 次，首次在第 %d 行 —— "
                    "作用范围只在这个函数里，没有可跳转的独立定义。"
                    % (_who, rel_here or "本文件", _start, len(_hits),
                       _hits[0]),
                ])}}
            return {"contents": {"kind": "markdown", "value": "\n".join([
                "```matlab", name, "```", "",
                "**`%s` 不是函数。**" % name, "",
                "本库内没有同名函数，它也不是参数或结构体字段，"
                "在 `%s` 里也没有被赋值过。"
                % _who, "",
                "可能是拼写错误，或者它来自别的作用域（eval / 嵌套函数 / "
                "未入库的文件）。",
            ])}}
        return None
    mf, f = hit

    try:
        sig = f.signature()
    except Exception:
        sig = "function %s" % name
    hdr = getattr(f, "header", None) or {}
    desc = hdr.get("description") or ""
    parts = ["```matlab", str(sig), "```"]
    if desc:
        parts.append("")
        parts.append(str(desc))

    # ---- 参数表（R231）-------------------------------------------------
    # 老代码里大量函数在头部注释写了 `% Input:` 表格，解析器**早就
    # 把它们结构化成了 `header["inputs"]`（`[[名, 类型, 说明], ...]`），
    # 但悬停从来没显示过 —— 算了却不用。
    # 只在**存在**时显示，没有就什么都不加（不能让每个函数都拖一张空表）。
    for title, key in (("输入", "inputs"), ("输出", "outputs")):
        rows = hdr.get(key) or []
        if not rows:
            continue
        parts.append("")
        parts.append("**%s**" % title)
        parts.append("")
        parts.append("| 参数 | 类型 | 说明 |")
        parts.append("| --- | --- | --- |")
        for row in rows:
            cells = list(row) + ["", "", ""]
            parts.append("| `%s` | %s | %s |"
                         % (cells[0], cells[1] or "—", cells[2] or ""))

    # R244：把「有多少调用跳不动」也说出来。
    # CodeLens 有了（R236）、关系图有了（R243），**悬停还没有** ——
    # 而悬停是用户看一个陌生函数时最先碰到的地方。
    un = _unresolved_count(f)
    if un:
        parts.append("")
        parts.append("另有 **%d 处调用无法定位**（字段取值 / toolbox / "
                     "函数句柄）—— 那些 `foo(...)` 按 F12 不会有结果。" % un)

    parts.append("")
    parts.append("复杂度 %s · 定义于 `%s:%d`"
                 % (getattr(f, "complexity", "?"), getattr(mf, "rel", ""),
                    getattr(mf, "line", 0)))
    return {"contents": {"kind": "markdown", "value": "\n".join(parts)}}


def _edge_counts(result):
    """`{"caller": n, "callee": n}` 两张计数表，键是 `rel:name`。

    `result.edges` 在内存里是 **tuple**（`(caller, callee, cross_file)`），
    只有 `render_json` 才转成 dict —— 两种都要收（R200 踩过一次）。
    """
    callers, callees = {}, {}
    for e in (getattr(result, "edges", None) or []):
        if isinstance(e, dict):
            c, d = e.get("caller"), e.get("callee")
        elif isinstance(e, (list, tuple)) and len(e) >= 2:
            c, d = e[0], e[1]
        else:
            continue
        if not c or not d:
            continue
        callees[c] = callees.get(c, 0) + 1
        callers[d] = callers.get(d, 0) + 1
    return callers, callees


#: 语义高亮的 token 类型。**顺序即编号**，扩展侧要照抄。
_SEMANTIC_TYPES = ["variable", "function", "property", "parameter"]
#: `declaration` = 定义处；`defaultLibrary` = MATLAB 内置；`static` = 全局变量。
_SEMANTIC_MODS = ["declaration", "defaultLibrary", "static"]

_SEM_TYPE_IDX = {t: i for i, t in enumerate(_SEMANTIC_TYPES)}
_SEM_MOD_BIT = {m: 1 << i for i, m in enumerate(_SEMANTIC_MODS)}


def _semantic_tokens(uri):
    """语义高亮：只标**确定**的五类，宁可不标也不标错。

    官方 TextMate 是**正则**，它分不清这五类：

        x = 1;         局部变量
        global G;      全局变量
        s.field = 1;   结构体字段
        numel(x)       MATLAB 内置
        myfunc(x)      用户函数

    而这五类的数据全在结果里（`globals` / `field_access` /
    `builtin_calls` / `files[].functions`）。**这是官方结构上做不到的事**：
    它没有解析器，只能按词法猜。

    保守策略（对应判据 T4）：
      - 只标函数**定义行**上的那个名字
      - 只标**确实在** `builtin_calls` 里的调用
      - 只标**确实在** `field_access` 里的字段
      - 只标 `globals` 里声明过的名字
    认不出来的标识符**一律不标**（留着 TextMate 的默认色）。
    """
    result = _wait_result(timeout=2.0)
    if result is None:
        return {"data": []}
    path = _uri_to_path(uri)
    root = _STATE.get("root") or ""
    try:
        rel = os.path.relpath(path, root).replace("\\", "/")
    except Exception:
        return {"data": []}
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except (IOError, OSError):
        return {"data": []}

    # ---- 收集本文件相关的名字集合 ----
    my_funcs = {}                      # name -> 定义行（1-based）
    all_funcs = set()
    builtins = set()
    globals_decl = set()
    for mf in (getattr(result, "files", None) or []):
        mrel = getattr(mf, "rel", "") or ""
        for g in (getattr(mf, "globals", None) or []):
            if mrel == rel:
                globals_decl.add(str(g))
        for f in (getattr(mf, "functions", None) or []):
            nm = getattr(f, "name", "") or ""
            if nm:
                all_funcs.add(nm)
                if mrel == rel:
                    my_funcs.setdefault(nm, int(getattr(f, "line", 0) or 1))
            bc = getattr(f, "builtin_calls", None) or {}
            if isinstance(bc, dict):
                builtins.update(bc.keys())

    fields = set()
    fa = getattr(result, "field_access", None)
    if isinstance(fa, dict):
        fields = set(fa.keys())

    # ---- 参数与局部变量：按**函数体范围**建作用域 ----
    # R219：上一轮参数一律不标，理由是「不敢猜」。但参数列表在语法上是
    # **确定的**：`function [z] = f(a, b, c)` 括号里那些就是参数。
    # 局部变量只在「赋值左侧」才确定，所以只收那些。
    #
    # 关键：**一旦确定，就在该函数体内的所有出现处都标**。
    # 只标定义处不标引用处，正是用户上一轮抱怨的「同类东西两种颜色」。
    scopes = []          # [(start_line0, end_line0, params:set, locals:set)]
    # 函数名在**签名行范围**内都算 declaration。多行签名时函数名可能
    # 落在第 2 行（`function [a,b] = ...` / `    multi(...)`），
    # 而 `my_funcs[nm]` 只记第 1 行 ---- R220 留下的缺口：
    # `multi` 因此拿不到 declaration 修饰，和单行的 `single` 不一致。
    decl_span = {}       # name -> (start0, end0_of_signature)
    # 输入参数：`function ... (a, b, c)`；输出参数：`function y = ...` 或
    # `function [z, w] = ...`。**两者都是签名的一部分**，都该标 `parameter`
    # —— R219 第一版只抓括号内的输入，于是 `function y = a(x)` 的 `y`
    # 因为函数体里有 `y = ...` 被误标成 `variable`。
    fn_in = re.compile(r"^\s*function\b.*?\(([^)]*)\)")
    fn_out = re.compile(r"^\s*function\s+(\[[^\]]*\]|\w+)\s*=")
    for nm, ln in list(my_funcs.items()):
        idx0 = max(0, ln - 1)
        # **多行签名**：MATLAB 用 `...` 续行。
        #     function [alpha, beta] = ...
        #         multi(first, second, ...
        #               third)
        # R219 只看 `lines[idx0]`，于是 `multi` 的参数一个都没认出来
        # （实测：`tests/sample_sig/multi.m` 只标出了单行那个函数）。
        # 判据是「行尾有 `...` 就继续拼」，比数括号深度更贴近语言规则。
        chunk = []
        j = idx0
        while j < len(lines) and j < idx0 + 20:
            raw = lines[j]
            cont = raw.rstrip().endswith("...")
            chunk.append(re.sub(r"\.\.\.\s*$", "", raw))
            j += 1
            if not cont:
                break
        head = " ".join(chunk)
        decl_span[nm] = (idx0, max(idx0, j - 1))
        params = set()
        m = fn_in.search(head)
        if m:
            for part in m.group(1).split(","):
                p = part.strip().split("=")[0].strip()
                if re.match(r"^[A-Za-z_]\w*$", p):
                    params.add(p)
        mo = fn_out.search(head)
        if mo:
            raw = mo.group(1).strip()
            if raw.startswith("["):
                raw = raw.strip("[]")
            for part in raw.split(","):
                p = part.strip()
                if re.match(r"^[A-Za-z_]\w*$", p):
                    params.add(p)
        # 函数体范围：从这个 function 行到下一个 function 行（或文件尾）
        end0 = len(lines) - 1
        for nm2, ln2 in my_funcs.items():
            if ln2 > ln:
                end0 = min(end0, ln2 - 2)
        locals_ = set()
        for j in range(idx0, min(end0 + 1, len(lines))):
            lm = re.match(r"^\s*([A-Za-z_]\w*)\s*=", lines[j])
            if lm:
                locals_.add(lm.group(1))
        if params or locals_:
            scopes.append((idx0, end0, params, locals_ - params))

    # ---- 逐行扫描，产出 (line, char, len, typeIdx, modMask) ----
    toks = []
    ident_rx = re.compile(r"[A-Za-z_]\w*")
    for i, text in enumerate(lines):
        # 注释行与注释尾一律跳过（和语法层保持一致，不改注释里的字）
        code_end = len(text)
        pct = text.find("%")
        if pct >= 0:
            # 粗略：`%` 之后不再标。字符串里出现 `%` 的情况极少，
            # 且最坏后果是"少标几个"，不会标错。
            code_end = pct
        if code_end <= 0:
            continue
        code = text[:code_end]
        for m in ident_rx.finditer(code):
            word = m.group(0)
            start, end = m.start(), m.end()
            prev = code[start - 1] if start > 0 else ""
            if prev == "." and word in fields:
                toks.append((i, start, len(word),
                             _SEM_TYPE_IDX["property"], 0))
                continue
            span = decl_span.get(word)
            if span is not None and span[0] <= i <= span[1]:
                toks.append((i, start, len(word),
                             _SEM_TYPE_IDX["function"],
                             _SEM_MOD_BIT["declaration"]))
                continue
            if word in builtins and (end >= len(code) or code[end:end + 1] == "("
                                     or code[end:end + 1] == " "):
                toks.append((i, start, len(word),
                             _SEM_TYPE_IDX["function"],
                             _SEM_MOD_BIT["defaultLibrary"]))
                continue
            if word in globals_decl:
                toks.append((i, start, len(word),
                             _SEM_TYPE_IDX["variable"],
                             _SEM_MOD_BIT["static"]))
                continue
            if word in all_funcs:
                toks.append((i, start, len(word),
                             _SEM_TYPE_IDX["function"], 0))
                continue
            # 参数优先于局部变量（同名时它本来就是参数）
            hit_scope = None
            for (s0, e0, ps, ls) in scopes:
                if s0 <= i <= e0:
                    if word in ps:
                        hit_scope = "parameter"
                        break
                    if word in ls:
                        hit_scope = "variable"
            if hit_scope == "parameter":
                toks.append((i, start, len(word),
                             _SEM_TYPE_IDX["parameter"], 0))
                continue
            if hit_scope == "variable":
                toks.append((i, start, len(word),
                             _SEM_TYPE_IDX["variable"], 0))
                continue
    # ---- 编码成 LSP 的 delta 数组 ----
    toks.sort(key=lambda t: (t[0], t[1]))
    data = []
    prev_line = 0
    prev_char = 0
    for line, char, length, tidx, mods in toks:
        d_line = line - prev_line
        d_char = char - prev_char if d_line == 0 else char
        data.extend([d_line, d_char, length, tidx, mods])
        prev_line, prev_char = line, char
    return {"data": data}


def _impact(name, depth=30, down_depth=3):
    """反向可达集：谁调用了 `name`；**外加正向一层：它调用了谁**。

    和 CLI 的 `--impact` 是同一套算法（BFS + `seen` 防环），
    区别只是这里的节点带 `(rel, line)`，**扩展侧可以直接跳过去**。

    返回 `None` 表示找不到这个名字（不是"没有调用者"）。
    """
    result = _wait_result(timeout=2.0)
    if result is None:
        # **分析还没完成**（R307）。这里不能返回 None —— 那是「查无此名」，
        # 界面会显示成「没有这个函数」。用一个显式的 pending 让客户端知道
        # 「稍后还有」，它几秒后自己重试。
        # 首次全库分析实测 70 秒（C:\Temp\yalmip，1676 文件），期间若让请求
        # 排队，界面就是一片空白且没有解释。
        return {"pending": True}

    # 名字 -> (rel, line)。同名函数多处定义时取第一个，并如实带上 `ambiguous` 数。
    where = {}
    meta = {}                # key -> {"complexity": n}
    for mf in (getattr(result, "files", None) or []):
        rel = getattr(mf, "rel", "") or ""
        for f in (getattr(mf, "functions", None) or []):
            nm = getattr(f, "name", "") or ""
            where.setdefault(nm, []).append(
                (rel, int(getattr(f, "line", 0) or 1)))
            # **只存便宜字段**（R307）。这里原来对**全库每个函数**算
            # `_param_names`（含 `signature()` 解析）与 `_unresolved_*`
            # （三次字典遍历）——YALMIP 约 2 万函数，实测 **67.9 秒**，
            # 关系视图因而不可能及时返回。真正输出到界面上的节点只有几十个，
            # 所以改成用到时才算（`node_info` 里有 `_node_extra` 缓存）。
            meta["%s:%s" % (rel, nm)] = {
                "complexity": int(getattr(f, "complexity", 0) or 0),
                "fn": f}
    if name not in where:
        return None

    # 反向图**带调用行号**：`edges` 只有 `(caller, callee)`，没有行号；
    # 而 `call_sites` 每个元素是 `[line, col, end, callee_obj]` ——
    # 有了它，才能回答「这个函数是被哪几行调用的」（R232）。
    rev = {}                 # callee_key -> [(caller_key, line), ...]
    fwd = {}                 # caller_key -> [(callee_key, line), ...]
    for mf in (getattr(result, "files", None) or []):
        rel0 = getattr(mf, "rel", "") or ""
        for f0 in (getattr(mf, "functions", None) or []):
            caller_key = "%s:%s" % (rel0, getattr(f0, "name", "") or "")
            for site in (getattr(f0, "call_sites", None) or []):
                # 两种形状：内存版 `[line, col, end, MatlabFunction]`，
                # 缓存版 `[line, "rel:name"]`。两种都要认 —— 否则
                # 「缓存命中后行号丢失」会让调用链退化成没有行号。
                try:
                    line = int(site[0])
                except (IndexError, TypeError, ValueError):
                    continue
                if len(site) >= 2 and isinstance(site[1], str):
                    trel, _, tname = site[1].rpartition(":")
                else:
                    try:
                        tgt = site[3]
                    except (IndexError, TypeError):
                        continue
                    trel = getattr(getattr(tgt, "mfile", None), "rel", "") or ""
                    tname = getattr(tgt, "name", "") or ""
                if not tname:
                    continue
                callee_key = "%s:%s" % (trel, tname)
                rev.setdefault(callee_key, []).append((caller_key, line))
                fwd.setdefault(caller_key, []).append((callee_key, line))
    # `edges` 里可能有 `call_sites` 覆盖不到的边（例如跨语言），补上
    # —— 没有行号的边仍然要进图，否则会漏掉调用者。
    for e in (getattr(result, "edges", None) or []):
        if isinstance(e, dict):
            c, d = e.get("caller"), e.get("callee")
        elif isinstance(e, (list, tuple)) and len(e) >= 2:
            c, d = e[0], e[1]
        else:
            continue
        if not c or not d:
            continue
        lst = rev.setdefault(d, [])
        if not any(x[0] == c for x in lst):
            lst.append((c, 0))
        lst2 = fwd.setdefault(c, [])
        if not any(x[0] == d for x in lst2):
            lst2.append((d, 0))

    _node_extra = {}          # key -> 昂贵的附加字段（只对真正输出的节点算）

    def node_info(key, calls=None):
        rel, _, nm = key.rpartition(":")
        lines = where.get(nm) or []
        line = 0
        for r, ln in lines:
            if r == rel:
                line = ln
                break
        # **调用点必须带它所在的文件**（R256）。`call_lines` 是「调用发生在
        # 哪一行」，而那些行在**调用者**的文件里 —— 首版把所有行号都挂到
        # 节点自己的 `rel` 上，于是跨文件时点那个数字会打开**错误的文件**
        # （实测 `a` 的 [5,8,9,12] 里 5 属于 switch_case.m，其余属于 a.m）。
        sites = {}
        for ck, ln in (calls or []):
            try:
                ln = int(ln)
            except (TypeError, ValueError):
                continue
            if ln <= 0:
                continue
            crel, _, _cname = ck.rpartition(":")
            sites[(crel, ln)] = {"rel": crel, "line": ln}
        _m = meta.get(key) or {}
        _xf = _node_extra.get(key)
        if _xf is None:
            _fn = _m.get("fn")
            if _fn is None:
                _xf = {"unresolved": 0, "unresolved_names": [],
                       "unresolved_names_total": 0,
                       "params": [], "param_types": [], "params_total": 0}
            else:
                _pn, _pty, _pc = _param_names(_fn)
                _xf = {
                    "unresolved": _unresolved_count(_fn),
                    "unresolved_names": _unresolved_names(_fn),
                    "unresolved_names_total": _unresolved_name_count(_fn),
                    "params": _pn,
                    "param_types": _pty,
                    "params_total": _pc,
                }
            _node_extra[key] = _xf
        info = {"key": key, "name": nm, "rel": rel, "line": line,
                "complexity": _m.get("complexity", 0),
                "unresolved": _xf["unresolved"],
                "unresolved_names": _xf["unresolved_names"],
                "unresolved_names_total": _xf["unresolved_names_total"],
                "params": _xf["params"],
                "param_types": _xf["param_types"],
                "params_total": _xf["params_total"],
                # **入口是服务端的事实，不是客户端的猜测**（R261）。
                # 客户端原来靠「`call_sites` 为空」推断入口，而
                # `call_sites` 会过滤掉行号 0 的条目 —— 那些由 `edges`
                # 补进来、没有行号的调用者会被当成“不存在”，
                # 于是一个**有调用者**的函数会被标成入口。
                "is_entry": not rev.get(key),
                "call_sites": [sites[k] for k in sorted(sites)]}
        return info

    start_keys = ["%s:%s" % (rel, name) for rel, _ln in where[name]]

    # ---- 链式视图（R287）：从入口一路到目标，**每条路径一行** --------
    # 分层的树适合「看层级」，但不适合「看一条完整的来路」：Source Insight
    # 那种读法是「这个函数是被谁、经由谁调到的」，一句话读完。
    # 深度与条数都要封顶，否则一个热点函数的路径数会爆炸。
    _chains = []

    def _walk(key, path, edges):
        if len(_chains) >= 30 or len(path) > 10:
            return
        # **按调用者去重**：`rev` 里同一个调用者有几个调用点就有几条，
        # 不去重的话同一条链会被重复输出多次（实测 3 次）。
        # 去重时保留**最小行号** —— 它就是 SI 那种「引用发生在第几行」。
        callers = {}
        for ck, ln in (rev.get(key) or ()):
            try:
                ln = int(ln)
            except (TypeError, ValueError):
                ln = 0
            if ck not in callers or (ln and ln < callers[ck]):
                callers[ck] = ln
        if not callers:
            chain = list(reversed(path))            # 入口 -> ... -> 目标
            line_of = {}
            for _a, _b, _ln in edges:
                line_of[(_a, _b)] = _ln
            # `call_line[i]` = chain[i] 调用 chain[i+1] 的那一行；
            # 最后一跳（目标自己）没有出边，记 None。
            clines = [line_of.get((chain[i], chain[i + 1]))
                      for i in range(len(chain) - 1)] + [None]
            if chain not in [c for c, _l in _chains]:
                _chains.append((chain, clines))
            return
        for ck in sorted(callers):
            if ck in path:                          # 防环
                continue
            _walk(ck, path + [ck], edges + [(ck, key, callers[ck])])

    for _sk in start_keys:
        _walk(_sk, [_sk], [])
    seen = set(start_keys)
    layer = list(start_keys)
    levels = []
    # **一直向上走到入口**，不再固定 3 层：用户要的是"直到最顶一层"。
    # 上限 30 只是防病态图（真正的深度由「没有调用者」自然终止）。
    for _ in range(max(1, int(depth))):
        nxt = []
        for k in layer:
            for c, _ln in rev.get(k, []):
                if c not in seen:
                    seen.add(c)
                    nxt.append(c)
        if not nxt:
            break
        levels.append([node_info(k, rev.get(k)) for k in sorted(nxt)])
        layer = nxt

    # ---- 下游：它调用了谁（R233）------------------------------------
    # 关系图原来只画上游。而 CodeLens 上明明写着 `↓12 被调用` ——
    # 那个数字点开却什么都没有，等于把「能看」变成一个「不能查的数」。
    # 数据是同一份 `call_sites`，只是这次走正向。
    d_seen = set(start_keys)
    d_layer = list(start_keys)
    down_levels = []
    down_truncated = False
    limit = max(1, int(down_depth))
    for i in range(limit):
        nxt = []
        for k in d_layer:
            for c, _ln in fwd.get(k, []):
                if c not in d_seen:
                    d_seen.add(c)
                    nxt.append(c)
        if not nxt:
            break
        down_levels.append([node_info(k) for k in sorted(nxt)])
        d_layer = nxt
        if i == limit - 1 and any(fwd.get(k) for k in d_layer):
            # 还有下一层但到了上限 —— 如实说「被截断」，
            # 而不是让用户以为这就是全部。
            down_truncated = True

    entries = [k for k in seen if not rev.get(k)]
    # `others`：第 2 层及以上的节点，带 `level`（1 起算）。
    # R227：QuickPick 原来只列直接调用者，而分层早就算出来了 ——
    # 用户点开只看到第一层，会以为"就这几个"。分层信息不该被丢掉。
    others = []
    for li, lv in enumerate(levels[1:], start=2):
        for node in lv:
            # **整份带上**，只加一个 `level`。
            # R232 第一版手挑了四个字段，于是 `call_lines` 在 `others`
            # 里丢了 —— 只有第 1 层能显示"被哪几行调用"，更深层不能，
            # 又是一种「同类不一致」。
            others.append(dict(node, level=li))
    return {
        "target": name,
        "definitions": [{"rel": r, "line": ln} for r, ln in where[name]],
        "ambiguous": max(0, len(where[name]) - 1),
        "direct": levels[0] if levels else [],
        "others": others,
        "levels": len(levels),
        "total": len(seen) - len(start_keys),
        "entries": len(entries),
        # 链式视图（R287）：每条 = 一条从入口到目标的完整路径
        # 每个节点带 `call_line`：**它调用下一跳发生在第几行**（R304）。
        # 这正是 Source Insight 里 `1. line 286` 的那个行号 —— 引用处，
        # 不是定义处。最后一跳（目标自己）没有出边，为 None。
        "chains": [[dict(node_info(k), call_line=ln)
                    for k, ln in zip(ch, clines)]
                   for ch, clines in _chains],
        # 下游（R233）
        "down": [dict(node, level=i + 1)
                 for i, lv in enumerate(down_levels) for node in lv],
        "down_levels": len(down_levels),
        "down_total": len(d_seen - set(start_keys)),
        "down_truncated": down_truncated,
        # 目标自身有多少次调用解析不到（R243）。它在 `edges` 里没有边，
        # 所以既不会出现在上游也不会出现在下游 —— **不报就等于说它
        # 什么都不调用**，而事实相反。
        # **目标节点的附加字段也必须走懒计算**（R307）：`meta` 现在只存
        # complexity 与函数对象，直接 `.get("unresolved")` 会全变成 0/[]。
        "unresolved": node_info(start_keys[0])["unresolved"],
        "unresolved_names": node_info(start_keys[0])["unresolved_names"],
        "unresolved_names_total":
            node_info(start_keys[0])["unresolved_names_total"],
        "params": node_info(start_keys[0])["params"],
        "param_types": node_info(start_keys[0])["param_types"],
        "params_total": node_info(start_keys[0])["params_total"],
        # 目标自己是不是入口（没人调它）—— 关系图用来把根节点标成“源头”。
        "is_entry": not rev.get(start_keys[0]),
    }


def _unresolved_count(f):
    """这个函数体里有多少次调用**解析不到定义**（external + indirect）。

    它们不在 `edges` 里，所以 `↓N` 从来不算它们 —— 而用户按 F12 恰恰是
    在这些上失败。数字必须一起报，否则「3」会被当成分母。
    """
    n = 0
    for key in ("external_calls", "indirect_calls"):
        d = getattr(f, key, None) or {}
        if not isinstance(d, dict):
            continue
        for v in d.values():
            n += v if isinstance(v, int) else 1
    return n


def _param_names(f, limit=4):
    """输入参数名 `(names, total)`，来自 `header["inputs"]`。

    R260：`header["inputs"]` 是 `[[名, 类型, 说明], ...]`，R231 起悬停已经在
    用它渲染参数表 —— **而关系图只显示“复杂度 11”，看不出这个函数要几个
    参数、叫什么**。同一份数据，两个出口只用了其中一个。

    返回 `(前 limit 个名字, 对应类型, 总数)`。总数单独给，展示层才能说
    「还有几个」；类型与名字**等长对齐**，取不到就是空串。

    R263：类型来自 `header["inputs"]` 的第二列；**签名回退时没有类型**，
    所以那条路径上类型是空串 —— 不是「类型未知就瞎猜」，而是如实留空，
    展示层只在有类型时渲染 `x:double`。
    """
    rows = ((getattr(f, "header", None) or {}).get("inputs") or [])
    names, types = [], []
    for row in rows:
        try:
            nm = str(row[0]).strip()
        except (IndexError, TypeError):
            continue
        if not nm:
            continue
        ty = ""
        try:
            ty = str(row[1]).strip()
        except (IndexError, TypeError):
            pass
        names.append(nm)
        types.append(ty)
    if not names:
        # **回退到签名**。`header["inputs"]` 只在头部写了 `% Input:` 表格时
        # 才有内容，而老代码里绝大多数函数**没写** —— 只靠它，这个功能对
        # 大部分函数等于没做（R260 实测：`many_calls.m` 三个函数的 inputs
        # 全是 `[]`）。
        try:
            sig = f.signature() or ""
        except Exception:
            sig = ""
        i, j = sig.find("("), sig.rfind(")")
        if 0 <= i < j:
            for part in sig[i + 1:j].split(","):
                nm = part.strip().split("=")[0].strip()
                if nm and nm != "~":       # `~` 是“忽略这个参数”
                    names.append(nm)
                    types.append("")       # 签名里没有类型，如实留空
    return names[:limit], types[:limit], len(names)


def _unresolved_tally(f):
    """解析不到的名字 -> 次数（`external_calls` 与 `indirect_calls` 合并）。"""
    tally = {}
    for key in ("external_calls", "indirect_calls"):
        d = getattr(f, key, None) or {}
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            tally[k] = tally.get(k, 0) + (v if isinstance(v, int) else 1)
    return tally


def _unresolved_names(f, limit=5):
    """解析不到的名字，按出现次数从多到少，最多 `limit` 个。

    R255：只报「另有 14 处未解析」是个**只有分子没有内容**的数字 ——
    用户无法据此做任何事。名字我们本来就有（`external_calls` 的键），
    把它们说出来，才知道该去查 `sedumi` 还是去查一个字段。

    R257：`limit` 会**截断**，而截断如果不报，就变成另一种撒谎 ——
    用户看到 5 个名字会以为只有 5 个。所以调用方还要拿
    `_unresolved_name_count()`，把「一共几个」和「这里列了几个」分开说。
    """
    tally = _unresolved_tally(f)
    return [k for k, _n in sorted(tally.items(),
                                  key=lambda kv: (-kv[1], kv[0]))][:limit]


def _unresolved_name_count(f):
    """**不同名字**的总数（不受 `_unresolved_names` 的 `limit` 影响）。"""
    return len(_unresolved_tally(f))


def _heat(limit=15, prefix=None):
    """热点排行：`复杂度 × (1 + 直接调用者数)`，从高到低。

    `prefix` 按**相对路径前缀**过滤（例如 `solver/` 或 `a.m`）。
    只看某个目录时，跨模块的分数没有可比性 —— 一个 20 行的求解器函数
    和一个 5 行的接口函数放在一张榜上，读者只会被大文件吸走注意力。

    为什么是这两项的乘积：

      - **复杂度高** ＝ 读起来难、改起来容易出错
      - **调用者多** ＝ 改它波及面大

    两项都高才算真热点。只复杂但没人调用（死代码或工具函数），
    或者被到处调用但只有一行（比如一个封装），都不该排在最前面。

    数据全部来自已经算好的 `result`，**不重解析、不改分析器**：
    `complexity` 是现成字段，调用者从 `call_sites` 反向累加。
    """
    result = _wait_result(timeout=2.0)
    if result is None:
        return None
    fn_meta = {}                 # key -> (rel, line, complexity)
    rev = {}                     # key -> set(caller_key)
    fwd = {}                     # key -> set(callee_key)
    for mf in (getattr(result, "files", None) or []):
        rel = getattr(mf, "rel", "") or ""
        for f in (getattr(mf, "functions", None) or []):
            nm = getattr(f, "name", "") or ""
            key = "%s:%s" % (rel, nm)
            fn_meta[key] = (rel, int(getattr(f, "line", 0) or 1),
                            int(getattr(f, "complexity", 0) or 0))
            for site in (getattr(f, "call_sites", None) or []):
                # 两种形状：内存版 [line, col, end, obj]，缓存版 [line, "rel:name"]
                if len(site) >= 2 and isinstance(site[1], str):
                    tkey = site[1]
                else:
                    try:
                        tgt = site[3]
                    except (IndexError, TypeError):
                        continue
                    tkey = "%s:%s" % (
                        getattr(getattr(tgt, "mfile", None), "rel", "") or "",
                        getattr(tgt, "name", "") or "")
                if not tkey or tkey.endswith(":"):
                    continue
                rev.setdefault(tkey, set()).add(key)
                fwd.setdefault(key, set()).add(tkey)

    rows = []
    for key, (rel, line, cx) in fn_meta.items():
        if prefix and not rel.startswith(prefix):
            continue
        callers = len(rev.get(key) or ())
        callees = len(fwd.get(key) or ())
        rows.append({
            "rel": rel,
            "name": key.rpartition(":")[2],
            "line": line,
            "complexity": cx,
            "callers": callers,
            "callees": callees,
            "score": cx * (1 + callers),
        })
    rows.sort(key=lambda r: (-r["score"], -r["complexity"], r["rel"], r["name"]))
    return rows[:max(1, int(limit))]


def _code_lens(uri):
    """每个函数头顶一条：`↑3 调用者 · ↓12 被调用 · 复杂度 11`。

    **官方 CodeLens 只显示 git 作者**，不显示调用关系。而这两组数字
    全在 `edges` 里，不需要重算。

    只返回**本文件**的函数 —— 打开一个文件时把所有 1665 个文件的
    函数都发过去没有意义。
    """
    result = _wait_result(timeout=2.0)
    if result is None:
        return []
    path = _uri_to_path(uri)
    root = _STATE.get("root") or ""
    try:
        rel = os.path.relpath(path, root).replace("\\", "/")
    except Exception:
        return []
    callers, callees = _edge_counts(result)
    out = []
    for mf in (getattr(result, "files", None) or []):
        if (getattr(mf, "rel", "") or "") != rel:
            continue
        for f in (getattr(mf, "functions", None) or []):
            name = getattr(f, "name", "") or ""
            key = "%s:%s" % (rel, name)
            ln = int(getattr(f, "line", 0) or 1)
            out.append({
                "range": {"start": {"line": max(0, ln - 1), "character": 0},
                          "end": {"line": max(0, ln - 1), "character": 0}},
                "data": {
                    "name": name,
                    "callers": callers.get(key, 0),
                    "callees": callees.get(key, 0),
                    # `callees` 只数 `edges`（库内、可跳）。函数体里还有
                    # 一堆 `foo(...)` 是解析不到的 —— 实测 YALMIP 有
                    # 24582 次 external + 528 次 indirect，比 edges 还多。
                    # **只报 3 会让这个数字看起来是全部**，而用户按 F12
                    # 在那 17 个上一定是「找不到」。所以要一并报出来。
                    "unresolved": _unresolved_count(f),
                    "complexity": getattr(f, "complexity", 0),
                },
            })
    return out


#: LSP `SymbolKind.Function` = 12
_SYMBOL_FUNCTION = 12
#: LSP `SymbolKind.Class` = 5
_SYMBOL_CLASS = 5


def _document_symbols(uri):
    """`textDocument/documentSymbol`：该文件的函数列表（大纲 / 符号面板）。

    数据来自 `MatlabFunction.name` / `.line` / `.body_end` / `.kind`，
    **不重新解析**。`kind == "classdef"` 的映射成 Class，其余映射成 Function。

    `range` 覆盖函数体（`line..body_end`），`selectionRange` 只覆盖名字那一行——
    LSP 要求后者**必须**落在前者内部，否则 VSCode 会拒绝整批符号。
    """
    # **不等待分析完成**（R284）：大纲有单文件兜底，等 90 秒只会让编辑器
    # 那边先超时，最后仍然是空 —— 而且用户要等过一次才知道是空的。
    result = _STATE.get("result")
    root = _STATE.get("root")
    if not root:
        return []
    path = _uri_to_path(uri)
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        rel = os.path.basename(path)
    want = os.path.basename(rel).lower()

    def _build(fns, file_lines):
        """把函数列表转成 LSP 符号数组。

        `range` 覆盖函数体，`selectionRange` 只覆盖名字那一行 —— 后者必须
        落在前者内部，否则 VSCode 会**整批拒绝**，大纲一片空白。

        `body_end` 缺失时（缓存重建的对象没有这个字段）不能退化成单行：
        退化的后果是「点了大纲里的函数却只选中一行」。改用下一个函数的
        起始行往前一行，最后一个函数用文件行数兜底。
        """
        starts = sorted(int(getattr(x, "line", 1) or 1) for x in fns)
        out2 = []
        for f in fns:
            name = getattr(f, "name", "") or ""
            if not name:
                continue
            start = max(0, int(getattr(f, "line", 1) or 1) - 1)
            end = getattr(f, "body_end", None)
            if end:
                end0 = max(start, int(end) - 1)
            else:
                nxt = None
                for s0 in starts:
                    if s0 - 1 > start:
                        nxt = s0 - 1
                        break
                end0 = (nxt - 1) if nxt is not None else max(
                    start, (file_lines or start + 1) - 1)
            end0 = max(start, end0)
            # **range 必须真的包住函数名**（R294）。缓存重建的对象没有
            # `lines`、函数没有 `body_end`，于是 end0 会退化成 start，
            # range 变成 (0,0)-(0,0) 而 selectionRange 是 (0,0)-(0,9) ——
            # VS Code 直接抛 `selectionRange must be contained in fullRange`，
            # **整批符号被拒绝**，大纲一片空白。
            # 这个 bug 只在缓存命中时出现，实时解析一切正常 ——
            # 所以干净的测试环境永远复现不了（实测 C:\Temp\yalmip 缓存）。
            end_char = len(name) if end0 <= start else 0
            kind = (_SYMBOL_CLASS
                    if (getattr(f, "kind", "") or "") == "classdef"
                    else _SYMBOL_FUNCTION)
            out2.append({
                "name": name,
                "kind": kind,
                "range": {"start": {"line": start, "character": 0},
                          "end": {"line": end0, "character": end_char}},
                "selectionRange": {"start": {"line": start, "character": 0},
                                   "end": {"line": start,
                                           "character": len(name)}},
            })
        return out2

    for mf in (getattr(result, "files", None) or []):
        if os.path.basename(getattr(mf, "rel", "") or "").lower() != want:
            continue
        out = _build((getattr(mf, "functions", None) or []),
                     getattr(mf, "lines", 0))
        if out:
            return out

    # ---- R284：分析里没有这个文件时，**就地解析这一个文件** ------------
    # 大纲请求只在打开文件时发一次；若此刻分析尚未覆盖该文件（首次打开大工程、
    # 或文件在分析范围之外），返回空之后**不会自动重来** —— 用户看到的就是
    # 「在文档 xxx.m 中找不到符号」，而且会一直空着。
    # 单文件解析是毫秒级的，比「解释为什么没有」有用得多。
    try:
        import matlabc as _M
        _mf = _M.MatlabFile(path, rel)
        _M.parse_file(_mf)
        return _build(getattr(_mf, "functions", None) or [],
                      getattr(_mf, "lines", 0))
    except Exception as exc:
        _log("documentSymbol 兜底解析失败：%r" % (exc,))
        return []


# --------------------------------------------------------------------------
# 协议处理
# --------------------------------------------------------------------------
def handle(msg, out):
    method = msg.get("method")
    mid = msg.get("id")

    if method == "initialize":
        params = msg.get("params") or {}
        root_uri = params.get("rootUri") or ""
        if not root_uri:
            folders = params.get("workspaceFolders") or []
            if folders:
                root_uri = folders[0].get("uri") or ""
        root = _uri_to_path(root_uri) if root_uri else ""
        _STATE["root"] = root if root and os.path.isdir(root) else None
        # **跨语言开关**（R345）：客户端通过 `initializationOptions.crossLanguage`
        # 传进来。扫 C 源、读 PE 导出表在超大工程上是实打实的 IO，
        # 用户应当能关掉它 —— 关掉后桥接会明确回 `disabled`，而不是空结果。
        _init = params.get("initializationOptions") or {}
        if "crossLanguage" in _init:
            _STATE["cross_lang"] = bool(_init.get("crossLanguage"))
        _write_message(out, {
            "jsonrpc": "2.0", "id": mid,
            "result": {
                "capabilities": {
                    "textDocumentSync": 1,
                    # 手写客户端不会自动转 provider，这里声明只是让协议
                    # 自洽；`vscode/extension.js` 里仍需自己 register。
                    "documentSymbolProvider": True,
                    # R218：语义高亮。**legend 的顺序就是 tokenType 的编号**，
                    # 扩展侧必须用同一份数组构造 `SemanticTokensLegend`，
                    # 否则颜色会整体错位（而且不会报错，只会「颜色莫名其妙」）。
                    "semanticTokensProvider": {
                        "legend": {
                            "tokenTypes": list(_SEMANTIC_TYPES),
                            "tokenModifiers": list(_SEMANTIC_MODS),
                        },
                        "full": True,
                    },
                },
                "serverInfo": {"name": "matlabc", "version": "0.1.0"},
            },
        })
        _log("initialize root=%r" % (_STATE["root"],))
        # **立刻开始预热**，不等用户打开文件。这是 Source Insight 的行为：
        # 项目一导入就建索引，用户点开时结果已就绪。
        threading.Thread(target=_warm, daemon=True).start()
        return True

    if method == "shutdown":
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": None})
        return True

    if method == "exit":
        return False

    if method == "textDocument/didOpen":
        uri = ((msg.get("params") or {}).get("textDocument") or {}).get("uri", "")
        # **先返回空诊断**，证明协议循环没被分析阻塞
        _write_message(out, {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": uri, "diagnostics": []},
        })

        def _later():
            # 复用 `_warm`（幂等）：`initialize` 已经预热时它立刻返回，
            # 否则这里补一次。**不要复制一份分析逻辑** —— 两份迟早会分叉。
            _warm()
            # `_warm` 在「别处正在预热」时**立即返回**，此时 `payload`
            # 还是 None。不等的话 `_diagnostics_for` 只能给出 0 条
            # —— R202 实测 `--save` / `--uninit` 就是这样从绿变红的。
            deadline = time.time() + 120.0
            while time.time() < deadline and _STATE.get("payload") is None:
                time.sleep(0.02)
            diags = _diagnostics_for(uri)
            _write_message(out, {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": {"uri": uri, "diagnostics": diags},
            })
            _log("didOpen %s -> %d 条" % (os.path.basename(uri), len(diags)))

        threading.Thread(target=_later, daemon=True).start()
        return True

    if method == "textDocument/definition":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        pos = params.get("position") or {}
        locs = _definition(uri, pos)
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": locs})
        _log("definition %s:%s -> %d"
             % (os.path.basename(_uri_to_path(uri)), pos.get("line"),
                len(locs)))
        return True

    if method == "textDocument/references":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        pos = params.get("position") or {}
        ctx = params.get("context") or {}
        locs = _references(uri, pos, bool(ctx.get("includeDeclaration")))
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": locs})
        _log("references %s:%s -> %d"
             % (os.path.basename(_uri_to_path(uri)), pos.get("line"),
                len(locs)))
        return True

    if method == "textDocument/hover":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        pos = params.get("position") or {}
        info = _hover(uri, pos)
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": info})
        _log("hover %s:%s -> %s"
             % (os.path.basename(_uri_to_path(uri)), pos.get("line"),
                "hit" if info else "none"))
        return True

    if method == "textDocument/documentSymbol":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        syms = _document_symbols(uri)
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": syms})
        _log("documentSymbol %s -> %d"
             % (os.path.basename(_uri_to_path(uri)), len(syms)))
        return True

    if method == "matlabc/impact":
        # 自定义方法（协议允许 `x/` 之外的私有前缀）。CodeLens 点击时用。
        params = msg.get("params") or {}
        name = params.get("name") or ""
        # `down_depth`：下游层数。默认 3 —— 往上要一直到入口，是因为
        # 「谁影响我」必须穷尽；往下不穷尽，因为叶子可能几百个。
        try:
            dd = int(params.get("down_depth") or 3)
        except (TypeError, ValueError):
            dd = 3
        info = _impact(name, down_depth=max(1, min(dd, 10)))
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": info})
        _log("impact %s -> %s" % (name, "none" if info is None
                                  else "%d 个调用者" % info["total"]))
        return True

    if method == "matlabc/cbridge":
        # 跨语言桥接：MATLAB 里调不到的名字，若在工程内的 C 源里定义了，
        # 就把链路接过去（否则调用链在 mex 边界断掉）。
        params = msg.get("params") or {}
        rows = _c_bridge(params.get("name") or "")
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": rows})
        _log("cbridge %s -> %s" % (params.get("name"),
                                   ("%d 处" % len(rows.get("items") or []))
                                   if rows.get("available")
                                   else rows.get("reason")))
        return True

    if method == "matlabc/field":
        # 结构体字段的读写位置。返回 None 表示「不是字段」——
        # 客户端据此回落到变量分支，两种语义不混。
        params = msg.get("params") or {}
        rows = _field_refs(params.get("name") or "")
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": rows})
        _log("field -> %s" % (("none" if rows is None
                               else "%d 写 / %d 读" % (len(rows["writes"]),
                                                       len(rows["reads"]))),))
        return True

    if method == "matlabc/heat":
        # 热点排行：给「先看哪几个函数」一个可执行答案。
        params = msg.get("params") or {}
        try:
            _lim = int(params.get("limit") or 15)
        except (TypeError, ValueError):
            _lim = 15
        _prefix = params.get("dir") or None
        rows = _heat(max(1, min(_lim, 200)), prefix=_prefix)
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": rows})
        _log("heat -> %s" % (("none" if rows is None
                              else "%d 行" % len(rows)),))
        return True

    if method == "textDocument/semanticTokens/full":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        toks = _semantic_tokens(uri)
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": toks})
        _log("semanticTokens %s -> %d 个 token"
             % (os.path.basename(_uri_to_path(uri)),
                len(toks.get("data") or []) // 5))
        return True

    if method == "textDocument/codeLens":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        lenses = _code_lens(uri)
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": lenses})
        _log("codeLens %s -> %d"
             % (os.path.basename(_uri_to_path(uri)), len(lenses)))
        return True

    if method == "textDocument/didSave":
        # R153：`didOpen` 只在 `payload is None` 时算一次，所以保存之后
        # 必须**显式作废**缓存，否则诊断永远是打开那一刻的旧结果。
        # 这是 LSP 从"能看"到"能用"的分界：慢是等一会儿，旧是错。
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        root = _STATE.get("root")
        # 保存的是哪个文件 —— 增量重算需要它。取不到就退回全量。
        rel = None
        if root:
            try:
                rel = os.path.relpath(_uri_to_path(uri), root)
                rel = rel.replace("\\", "/")
            except Exception:
                rel = None
        if root:
            # **作废缓存要在锁内，重算必须在锁外**。
            # R202 实测：把 `_run_json` 留在锁里，YALMIP（1665 文件、约 30s）
            # 一次保存就会把协议循环堵住半分钟，期间 `definition` 全部排队。
            # **保存时只重算变化的文件**（R268）。
            # 前提是当前结果里的对象是「活的」（真解析产物）—— 缓存重建的
            # 替身不能当 `prev`。任何一步不合适就退回全量，**兜底优先于快**。
            prev_files = None
            changed = None
            old = _STATE.get("result")
            if old is not None and rel and _is_live_result(old):
                prev_files = getattr(old, "files", None)
                changed = {rel}
            with _STATE["lock"]:
                _STATE["payload"] = None
                _STATE["result"] = None
                _STATE["warming"] = False
            try:
                if prev_files is not None:
                    _STATE["payload"] = _run_json(root, prev=prev_files,
                                                  changed=changed)
                else:
                    _STATE["payload"] = _run_json(root)
            except Exception as exc:
                _log("增量重算失败，退回全量：%r" % (exc,))
                _STATE["payload"] = _run_json(root)
        diags = _diagnostics_for(uri)
        _write_message(out, {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": uri, "diagnostics": diags},
        })
        _log("didSave %s -> %d 条（已重算）"
             % (os.path.basename(_uri_to_path(uri)), len(diags)))
        return True

    if method == "textDocument/didClose":
        return True

    if mid is not None:
        # R167：未实现的方法按 LSP 规范回 **-32601 MethodNotFound**。
        # 原来回的是 `result: null` —— 那让客户端以为「方法存在，只是没结果」，
        # 而且掩盖了「这个能力根本没实现」这件事。实测 `workspace/symbol`
        # 收到的正是 `{"id":9,"result":null}`。
        _write_message(out, {
            "jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601,
                      "message": "Method not found: %s" % method},
        })
    return True


def main():
    if not os.path.isfile(MATLABC):
        _log("缺输入：找不到 %s" % MATLABC)
        return 2
    _log("start")
    inp = sys.stdin.buffer
    out = sys.stdout.buffer
    while True:
        msg = _read_message(inp)
        if msg is None:
            break
        try:
            if not handle(msg, out):
                break
        except Exception as exc:               # 单帧出错不能让服务挂掉
            _log("handle error: %r" % (exc,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
