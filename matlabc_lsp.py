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
    sys.stderr.write("[lsp] %s\n" % msg)
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


def _save_cache(root, payload, result):
    """把「结构层 + 诊断」写盘。失败不算错（缓存是可选的）。"""
    try:
        files_src = getattr(result, "files", None) or []
        files = []
        for mf in files_src:
            fns = []
            for fn in (getattr(mf, "functions", None) or []):
                try:
                    sig = fn.signature()
                except Exception:
                    sig = getattr(fn, "name", "")
                # `call_sites` 也要存：它是「被哪几行调用」的唯一来源。
                # R232 第一版没存，于是**缓存命中后行号全变成 0** ——
                # 判据 `impact/call-lines-are-1based` 当场抓住。
                sites = []
                for st in (getattr(fn, "call_sites", None) or []):
                    try:
                        line = int(st[0])
                    except (IndexError, TypeError, ValueError):
                        continue
                    if len(st) >= 2 and isinstance(st[1], str):
                        # 已经是缓存形状 —— 原样保留，否则二次写缓存会清空。
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
                fns.append({
                    "name": getattr(fn, "name", ""),
                    "line": getattr(fn, "line", 0),
                    "complexity": getattr(fn, "complexity", 0),
                    "header": getattr(fn, "header", None) or {},
                    "sig": sig,
                    "call_sites": sites,
                    # R235：`_hover` 用它解释「本库没有这个函数，但它被当
                    # 调用记过」。**这是第四次因为缓存漏字段而「重启后哑」**
                    # （signature / call_sites / field_access / 现在这个）。
                    "external_calls": dict(getattr(fn, "external_calls", None) or {}),
                    "indirect_calls": dict(getattr(fn, "indirect_calls", None) or {}),
                })
            files.append({
                "rel": getattr(mf, "rel", "") or "",
                "header": getattr(mf, "header", None) or {},
                "functions": fns,
            })
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
        doc = {"v": 3, "complete": True, "stamp": stamp, "files": files,
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
    # **v=3**：R233 加了 `field_access`。v1 的缓存缺它，命中后结构体
    # 跳转会静默失效 —— 宁可让用户多等一次分析，也不给一份"看起来能用
    # 但某些功能是哑的"缓存。
    if not isinstance(doc, dict) or doc.get("v") != 3:
        _log("缓存 schema 不符（v=%r，需要 3），忽略" % (doc.get("v"),))
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
                o = NS(name=fn.get("name", ""), line=fn.get("line", 0),
                       complexity=fn.get("complexity", 0),
                       header=fn.get("header") or {})
                # `_hover` 调 `fn.signature()`；SimpleNamespace 没有方法，
                # 这里补一个，返回值就是缓存里存好的那串。
                o.signature = (lambda s: (lambda: s))(fn.get("sig", ""))
                # 缓存里的 `call_sites` 是 `[line, "rel:name"]`（内存版是
                # `[line, col, end, MatlabFunction]`）。`_impact` 两边都收。
                o.call_sites = [tuple(x) for x in (fn.get("call_sites") or [])]
                o.external_calls = dict(fn.get("external_calls") or {})
                o.indirect_calls = dict(fn.get("indirect_calls") or {})
                fns.append(o)
            files.append(NS(rel=f.get("rel", ""),
                            header=f.get("header") or {},
                            functions=fns))
        edges = [tuple(e) for e in (doc.get("edges") or [])]
        result = NS(files=files, edges=edges,
                    field_access=doc.get("field_access") or {})
        _log("缓存命中：%d 文件 / %d 边" % (len(files), len(edges)))
        return result, doc.get("payload") or {"heuristics": []}
    except Exception as exc:
        _log("缓存重建失败，忽略：%r" % (exc,))
        return None


def _run_json(root):
    """**进程内**跑分析，返回与 `--json` 同形的 `{"heuristics": [...]}`。

    为什么不再起子进程：CLI 全流程实测 **5.92s**（1300 个 .m），而
    `analyzer.api.analyze` 进程内只要 **0.73s** —— 差的 5.2 秒是
    `collect_files` 的 `os.walk`、JSON 序列化与进程启动，LSP 一样都用不上。

    仍然传 `no_checks=True`：诊断只需要 `doc_todos`，而 `_collect_checks`
    占 63%（未关时）。
    """
    # **先试磁盘缓存**：命中就跳过全部解析（第二次开同一项目从 35 秒到 0.2 秒）。
    # `stamp` 校验保证「改过任何一个 .m 就作废」，所以命中时结果与重算一致。
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


def _ident_at(lines, line0, char):
    """取 `line0` 行 `char` 位置上的最长标识符（`[A-Za-z0-9_]`）。"""
    if line0 < 0 or line0 >= len(lines):
        return None
    s = lines[line0]
    i = min(max(0, char), len(s))
    start, end = i, i
    while start > 0 and (s[start - 1].isalnum() or s[start - 1] == "_"):
        start -= 1
    while end < len(s) and (s[end].isalnum() or s[end] == "_"):
        end += 1
    if start == end:
        return None
    word = s[start:end]
    if not word or not (word[0].isalpha() or word[0] == "_"):
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
    result = _wait_result()
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
        first = sorted(writes, key=lambda r: (r[0], r[2] or 0))[0]
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
    if not hits:
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
    result = _wait_result()
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


def _hover(uri, pos):
    """`textDocument/hover`：光标处标识符 -> 函数的签名 / 描述 / 复杂度。

    数据全部来自 `MatlabFunction` 的现成字段，**不重新解析**：
    `signature()` / `header["description"]` / `complexity`。
    找不到时返回 `None`（LSP 里 `null` 表示"这里没有可悬停的信息"）。
    """
    result = _wait_result()
    if result is None:
        return None
    path = _uri_to_path(uri)
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except (IOError, OSError):
        return None
    name = _ident_at(lines, int(pos.get("line", 0)),
                     int(pos.get("character", 0)))
    if name is None:
        return None

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

    parts.append("")
    parts.append("复杂度 %s · 定义于 `%s:%d`"
                 % (getattr(f, "complexity", "?"), getattr(mf, "rel", ""),
                    getattr(f, "line", 0)))
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
    result = _wait_result()
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
    result = _wait_result()
    if result is None:
        return None

    # 名字 -> (rel, line)。同名函数多处定义时取第一个，并如实带上 `ambiguous` 数。
    where = {}
    meta = {}                # key -> {"complexity": n}
    for mf in (getattr(result, "files", None) or []):
        rel = getattr(mf, "rel", "") or ""
        for f in (getattr(mf, "functions", None) or []):
            nm = getattr(f, "name", "") or ""
            where.setdefault(nm, []).append(
                (rel, int(getattr(f, "line", 0) or 1)))
            meta["%s:%s" % (rel, nm)] = {
                "complexity": int(getattr(f, "complexity", 0) or 0)}
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

    def node_info(key, calls=None):
        rel, _, nm = key.rpartition(":")
        lines = where.get(nm) or []
        line = 0
        for r, ln in lines:
            if r == rel:
                line = ln
                break
        info = {"key": key, "name": nm, "rel": rel, "line": line,
                "complexity": (meta.get(key) or {}).get("complexity", 0),
                "call_lines": sorted(set(l for _c, l in (calls or [])) if calls
                                     else [])}
        return info

    start_keys = ["%s:%s" % (rel, name) for rel, _ln in where[name]]
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
        # 下游（R233）
        "down": [dict(node, level=i + 1)
                 for i, lv in enumerate(down_levels) for node in lv],
        "down_levels": len(down_levels),
        "down_total": len(d_seen - set(start_keys)),
        "down_truncated": down_truncated,
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


def _code_lens(uri):
    """每个函数头顶一条：`↑3 调用者 · ↓12 被调用 · 复杂度 11`。

    **官方 CodeLens 只显示 git 作者**，不显示调用关系。而这两组数字
    全在 `edges` 里，不需要重算。

    只返回**本文件**的函数 —— 打开一个文件时把所有 1665 个文件的
    函数都发过去没有意义。
    """
    result = _wait_result()
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
    result = _wait_result()
    root = _STATE.get("root")
    if result is None or not root:
        return []
    path = _uri_to_path(uri)
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        rel = os.path.basename(path)
    want = os.path.basename(rel).lower()

    out = []
    for mf in (getattr(result, "files", None) or []):
        if os.path.basename(getattr(mf, "rel", "") or "").lower() != want:
            continue
        for f in (getattr(mf, "functions", None) or []):
            name = getattr(f, "name", "") or ""
            if not name:
                continue
            start = max(0, int(getattr(f, "line", 1) or 1) - 1)
            end = getattr(f, "body_end", None)
            end0 = max(start, int(end) - 1) if end else start
            kind = (_SYMBOL_CLASS
                    if (getattr(f, "kind", "") or "") == "classdef"
                    else _SYMBOL_FUNCTION)
            out.append({
                "name": name,
                "kind": kind,
                "range": {"start": {"line": start, "character": 0},
                          "end": {"line": end0, "character": 0}},
                "selectionRange": {"start": {"line": start, "character": 0},
                                   "end": {"line": start,
                                           "character": len(name)}},
            })
    return out


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
                "serverInfo": {"name": "matlabc-lsp", "version": "0.1.0"},
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
        if root:
            # **作废缓存要在锁内，重算必须在锁外**。
            # R202 实测：把 `_run_json` 留在锁里，YALMIP（1665 文件、约 30s）
            # 一次保存就会把协议循环堵住半分钟，期间 `definition` 全部排队。
            with _STATE["lock"]:
                _STATE["payload"] = None
                _STATE["result"] = None
                _STATE["warming"] = False
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
