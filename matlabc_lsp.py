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
        files = []
        for mf in (getattr(result, "files", None) or []):
            fns = []
            for fn in (getattr(mf, "functions", None) or []):
                try:
                    sig = fn.signature()
                except Exception:
                    sig = getattr(fn, "name", "")
                fns.append({
                    "name": getattr(fn, "name", ""),
                    "line": getattr(fn, "line", 0),
                    "complexity": getattr(fn, "complexity", 0),
                    "header": getattr(fn, "header", None) or {},
                    "sig": sig,
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
        doc = {"v": 1, "stamp": stamp, "files": files,
               "edges": edges, "payload": payload}
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
    if not isinstance(doc, dict) or doc.get("v") != 1:
        _log("缓存 schema 不符（v=%r），忽略" % (doc.get("v"),))
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
                fns.append(o)
            files.append(NS(rel=f.get("rel", ""),
                            header=f.get("header") or {},
                            functions=fns))
        edges = [tuple(e) for e in (doc.get("edges") or [])]
        result = NS(files=files, edges=edges)
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

    `field_access` **只在 `render_json` 里构建**（`matlabc.py` 的 L14133），
    所以 `analyze()` 的 `result` 上没有它。LSP 走的是 `analyze`，
    因此必须在这里自己调一次 `_collect_cross_file_fields`。

    缓存挂在 `_STATE` 上：一次 `didOpen` 只付一次代价。
    """
    idx = _STATE.get("field_index")
    if idx is not None:
        return idx
    try:
        import matlabc as _M
        idx = _M._collect_cross_file_fields(
            getattr(result, "files", None) or [])
    except Exception as exc:                  # 字段索引失败不许影响跳转
        _log("_field_index 失败：%r" % (exc,))
        idx = {}
    _STATE["field_index"] = idx
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
        payload = _run_json(root)
    finally:
        with _STATE["lock"]:
            _STATE["warming"] = False

    with _STATE["lock"]:
        if _STATE["payload"] is None:
            _STATE["payload"] = payload
    _log("预热完成 %s -> %.1fs，%d 条诊断"
         % (root, time.time() - t0,
            len((payload or {}).get("heuristics") or [])))


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
        return None
    mf, f = hit

    try:
        sig = f.signature()
    except Exception:
        sig = "function %s" % name
    desc = (getattr(f, "header", None) or {}).get("description") or ""
    parts = ["```matlab", str(sig), "```"]
    if desc:
        parts.append("")
        parts.append(str(desc))
    parts.append("")
    parts.append("复杂度 %s · 定义于 `%s:%d`"
                 % (getattr(f, "complexity", "?"), getattr(mf, "rel", ""),
                    getattr(f, "line", 0)))
    return {"contents": {"kind": "markdown", "value": "\n".join(parts)}}


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
