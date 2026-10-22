# -*- coding: utf-8 -*-
"""`.mlcproj` + SQLite 项目符号库（Source Insight 移植 P0 原型）。

这个工具只做四件事：
    init    创建 `.mlcproj` 与 `.mlc/project.db`
    sync    扫描源文件，按 per-file 指纹增量解析 MATLAB 符号
    status  报告文件/符号/边数量与陈旧文件
    symbols 查询符号（名称/点分名/种类/文件）

它**不是** Source Insight 的二进制格式兼容层：
    SI 的 `.sip._*` / `.sip_sym` 没有公开 schema；本工具只导入文件清单，
    重新解析源码，建立自己的 SQLite 符号库。

用法：
    python tools/mlc_project.py init --root . --name demo
    python tools/mlc_project.py sync --root .
    python tools/mlc_project.py status --root .
    python tools/mlc_project.py symbols --root . --query main
"""
import argparse
import fnmatch
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import matlabc  # noqa: E402

CONFIG_NAME = ".mlcproj"
DATA_DIR = ".mlc"
DB_NAME = "project.db"
SCHEMA_VERSION = 1
SKIP_DIRS = (".git", ".mlc", "__pycache__", "node_modules", "build",
             "dist", ".venv", "venv")

DEFAULT_EXCLUDE = (".git/**", ".mlc/**", "build/**", "dist/**",
                   "node_modules/**", "__pycache__/**", ".venv/**",
                   "venv/**")
DEFAULT_INCLUDE = ("**/*.m",)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm_rel(path):
    p = path.replace(os.sep, "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _match_any(rel, patterns):
    for pat in patterns or ():
        pat = pat.replace("\\", "/")
        if fnmatch.fnmatch(rel, pat):
            return True
        if pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:]):
            return True
    return False


def _load_json(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path, data):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")


def find_project(start=None):
    cur = os.path.abspath(start or os.getcwd())
    if os.path.isfile(cur):
        cur = os.path.dirname(cur)
    while True:
        cand = os.path.join(cur, CONFIG_NAME)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def load_config(project_path):
    project_path = os.path.abspath(project_path)
    cfg = _load_json(project_path)
    if cfg.get("schema") != SCHEMA_VERSION:
        raise ValueError("不支持的 schema：%r" % (cfg.get("schema"),))
    if not cfg.get("name"):
        raise ValueError("项目缺 name")
    base = os.path.dirname(project_path)
    root = cfg.get("root") or "."
    if not os.path.isabs(root):
        root = os.path.normpath(os.path.join(base, root))
    cfg["_project_path"] = project_path
    cfg["_root"] = root
    cfg["_db"] = os.path.join(base, DATA_DIR, DB_NAME)
    cfg.setdefault("source_dirs", ["."])
    cfg.setdefault("include", list(DEFAULT_INCLUDE))
    cfg.setdefault("exclude", list(DEFAULT_EXCLUDE))
    return cfg


def _connect(db_path):
    if not os.path.isdir(os.path.dirname(db_path)):
        os.makedirs(os.path.dirname(db_path))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  root TEXT NOT NULL,
  config_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  lang TEXT NOT NULL DEFAULT 'matlab',
  mtime_ns INTEGER NOT NULL,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  parse_status TEXT NOT NULL DEFAULT 'ok',
  parse_error TEXT NOT NULL DEFAULT '',
  indexed_at TEXT NOT NULL,
  UNIQUE(project_id, path)
);
CREATE TABLE IF NOT EXISTS symbols (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  dotted_name TEXT NOT NULL,
  kind TEXT NOT NULL,
  line INTEGER NOT NULL,
  col INTEGER NOT NULL DEFAULT 1,
  end_line INTEGER,
  scope_id INTEGER REFERENCES symbols(id) ON DELETE SET NULL,
  signature TEXT NOT NULL DEFAULT '',
  type_name TEXT NOT NULL DEFAULT '',
  flags TEXT NOT NULL DEFAULT '',
  resolution TEXT NOT NULL DEFAULT 'project',
  UNIQUE(file_id, kind, dotted_name, line)
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_dotted ON symbols(dotted_name);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE TABLE IF NOT EXISTS refs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
  file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  line INTEGER NOT NULL,
  col INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL DEFAULT 'ref',
  context TEXT NOT NULL DEFAULT '',
  confidence REAL NOT NULL DEFAULT 1.0
);
CREATE TABLE IF NOT EXISTS edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  src_symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
  dst_symbol_id INTEGER REFERENCES symbols(id) ON DELETE SET NULL,
  callee_name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'call',
  line INTEGER NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 1.0,
  weight INTEGER NOT NULL DEFAULT 1,
  file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_symbol_id);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_symbol_id);
CREATE TABLE IF NOT EXISTS conditions (
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY(project_id, name)
);
CREATE TABLE IF NOT EXISTS bookmarks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
  line INTEGER NOT NULL,
  col INTEGER NOT NULL DEFAULT 1,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS snippets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  lang TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL,
  UNIQUE(project_id, name, lang)
);
CREATE TABLE IF NOT EXISTS workspaces (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  state_json TEXT NOT NULL,
  UNIQUE(project_id, name)
);
"""


def _ensure_column(conn, table, column, decl):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)]
    if column not in cols:
        conn.execute("ALTER TABLE %s ADD COLUMN %s %s"
                     % (table, column, decl))


def init_db(conn):
    conn.executescript(SCHEMA)
    # P0 建的库没有这些列；迁移是幂等 ALTER，不丢数据。
    _ensure_column(conn, "symbols", "resolution",
                   "TEXT NOT NULL DEFAULT 'project'")
    _ensure_column(conn, "refs", "confidence",
                   "REAL NOT NULL DEFAULT 1.0")
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema', ?)",
                 (str(SCHEMA_VERSION),))
    conn.commit()


def _upsert_project(conn, cfg):
    now = _now()
    row = conn.execute("SELECT id FROM projects WHERE name=?",
                       (cfg["name"],)).fetchone()
    public = dict((k, v) for k, v in cfg.items() if not k.startswith("_"))
    payload = json.dumps(public, ensure_ascii=False, sort_keys=True)
    if row:
        conn.execute("UPDATE projects SET root=?, config_json=?, updated_at=? "
                     "WHERE id=?", (cfg["_root"], payload, now, row["id"]))
        return row["id"]
    cur = conn.execute("INSERT INTO projects(name, root, config_json, "
                       "created_at, updated_at) VALUES(?,?,?,?,?)",
                       (cfg["name"], cfg["_root"], payload, now, now))
    return cur.lastrowid


def init_project(root=".", name=None, source_dirs=None, include=None,
                 exclude=None, force=False):
    root = os.path.abspath(root)
    project_path = os.path.join(root, CONFIG_NAME)
    if os.path.exists(project_path) and not force:
        raise ValueError("%s 已存在（用 --force 覆盖）" % project_path)
    if not os.path.isdir(root):
        raise ValueError("root 不存在：%s" % root)
    cfg = {
        "schema": SCHEMA_VERSION,
        "name": name or os.path.basename(root.rstrip(os.sep)) or "project",
        "root": ".",
        "source_dirs": list(source_dirs or ["."]),
        "include": list(include or DEFAULT_INCLUDE),
        "exclude": list(exclude or DEFAULT_EXCLUDE),
        "file_types": {".m": "matlab"},
        "conditions": {},
        "settings": {"name_fragments": True, "index_references": True},
    }
    _write_json(project_path, cfg)
    conn = _connect(os.path.join(root, DATA_DIR, DB_NAME))
    try:
        init_db(conn)
        cfg2 = load_config(project_path)
        _upsert_project(conn, cfg2)
        conn.commit()
    finally:
        conn.close()
    return project_path


def _iter_source_files(cfg):
    root = cfg["_root"]
    source_dirs = cfg.get("source_dirs") or ["."]
    include = cfg.get("include") or list(DEFAULT_INCLUDE)
    exclude = cfg.get("exclude") or list(DEFAULT_EXCLUDE)
    seen = set()
    out = []
    for sd in source_dirs:
        base = sd if os.path.isabs(sd) else os.path.join(root, sd)
        base = os.path.normpath(base)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            keep = []
            for d in sorted(dirnames):
                if d in SKIP_DIRS:
                    continue
                try:
                    rel_dir = _norm_rel(os.path.relpath(
                        os.path.join(dirpath, d), root))
                except ValueError:
                    raise ValueError("source_dir 与 root 不在同一盘：%s" % base)
                if not _match_any(rel_dir + "/", exclude):
                    keep.append(d)
            dirnames[:] = keep
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                try:
                    rel = _norm_rel(os.path.relpath(full, root))
                except ValueError:
                    raise ValueError("source_dir 与 root 不在同一盘：%s" % base)
                if rel in seen:
                    continue
                if exclude and _match_any(rel, exclude):
                    continue
                if include and not _match_any(rel, include):
                    continue
                seen.add(rel)
                out.append((rel, full))
    return sorted(out, key=lambda x: x[0])


def _db_files(conn, project_id):
    rows = conn.execute(
        "SELECT id, path, mtime_ns, size, sha256 FROM files "
        "WHERE project_id=? ORDER BY path", (project_id,)).fetchall()
    return dict((r["path"], r) for r in rows)


def _changes(cfg, conn, project_id, full=False):
    scanned = _iter_source_files(cfg)
    old = _db_files(conn, project_id)
    added, changed, unchanged = [], [], []
    for rel, full_path in scanned:
        try:
            st = os.stat(full_path)
        except OSError:
            continue
        rec = old.get(rel)
        if rec is None:
            added.append(rel)
        elif full:
            changed.append(rel)
        elif rec["mtime_ns"] != st.st_mtime_ns or rec["size"] != st.st_size:
            if rec["sha256"] != _sha256(full_path):
                changed.append(rel)
            else:
                unchanged.append(rel)
        else:
            unchanged.append(rel)
    removed = sorted(set(old) - set(rel for rel, _ in scanned))
    return scanned, added, changed, removed, unchanged


def _package_parts(rel):
    parts = rel.split("/")[:-1]
    pkg = []
    for p in parts:
        if p.startswith("+"):
            pkg.append(p[1:])
    return pkg


def _class_dir(rel):
    """旧式 `@Class/foo.m` 目录；返回 Class，否则空串。"""
    for p in rel.split("/")[:-1]:
        if p.startswith("@") and len(p) > 1:
            return p[1:]
    return ""


def _dotted(parts, name):
    return ".".join([p for p in list(parts) + [name] if p])


def _sig(fn):
    outs = getattr(fn, "outputs", None) or []
    ins = getattr(fn, "inputs", None) or []
    lhs = ""
    if outs:
        lhs = ", ".join(str(x) for x in outs) + " = "
    return "function %s%s(%s)" % (lhs, getattr(fn, "name", ""),
                                  ", ".join(str(x) for x in ins))


def _insert_symbol(conn, file_id, name, dotted, kind, line, scope_id=None,
                   signature="", type_name="", flags="", end_line=None,
                   resolution="project"):
    cur = conn.execute(
        "INSERT OR IGNORE INTO symbols(file_id, name, dotted_name, kind, "
        "line, col, end_line, scope_id, signature, type_name, flags, "
        "resolution) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (file_id, name, dotted, kind, int(line), 1, end_line, scope_id,
         signature, type_name, flags, resolution))
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute(
        "SELECT id FROM symbols WHERE file_id=? AND kind=? AND dotted_name=? "
        "AND line=?", (file_id, kind, dotted, int(line))).fetchone()
    return row["id"] if row else None


def _insert_file_symbols(conn, file_id, rel, mf):
    """把 MATLAB 文件解析结果写入 symbols；返回 (function symbol 列表)。"""
    pkg = _package_parts(rel)
    class_dir = _class_dir(rel)
    class_ids = {}
    func_rows = []
    for cls in getattr(mf, "classes", None) or []:
        cname = getattr(cls, "name", "") or ""
        if not cname:
            continue
        cd = _dotted(pkg, cname)
        cid = _insert_symbol(conn, file_id, cname, cd, "class",
                             getattr(cls, "line", 1) or 1,
                             signature="classdef %s" % cname,
                             type_name="class")
        class_ids[cname] = cid
        for prop in getattr(cls, "properties", None) or []:
            pname, pline = (prop if isinstance(prop, tuple)
                            else (getattr(prop, "name", ""),
                                  getattr(prop, "line", 1)))
            if pname:
                _insert_symbol(conn, file_id, pname,
                               _dotted(pkg + [cname], pname), "property",
                               pline or 1, scope_id=cid, type_name="property")
        for ev in getattr(cls, "events", None) or []:
            ename, eline = (ev if isinstance(ev, tuple)
                            else (getattr(ev, "name", ""),
                                  getattr(ev, "line", 1)))
            if ename:
                _insert_symbol(conn, file_id, ename,
                               _dotted(pkg + [cname], ename), "event",
                               eline or 1, scope_id=cid)
        for en in getattr(cls, "enumerations", None) or []:
            nname, nline = (en if isinstance(en, tuple)
                            else (getattr(en, "name", ""),
                                  getattr(en, "line", 1)))
            if nname:
                _insert_symbol(conn, file_id, nname,
                               _dotted(pkg + [cname], nname), "enumeration",
                               nline or 1, scope_id=cid)
    if class_dir and class_dir not in class_ids:
        cd = _dotted(pkg, class_dir)
        class_ids[class_dir] = _insert_symbol(
            conn, file_id, class_dir, cd, "class", 1,
            signature="classdef %s" % class_dir, type_name="class")
    # 主函数名用于局部函数的点分前缀
    funcs = list(getattr(mf, "functions", None) or [])
    main_name = ""
    for fn in funcs:
        if getattr(fn, "kind", "") == "main":
            main_name = getattr(fn, "name", "") or ""
            break
    for fn in funcs:
        name = getattr(fn, "name", "") or ""
        if not name:
            continue
        line = getattr(fn, "line", 1) or 1
        cname = getattr(fn, "class_name", None) or class_dir or None
        if cname:
            cd = _dotted(pkg, cname)
            cid = class_ids.get(cname)
            if cid is None:
                cid = _insert_symbol(conn, file_id, cname, cd, "class",
                                     line, signature="classdef %s" % cname)
                class_ids[cname] = cid
            kind = ("constructor" if name == cname
                    else "method")
            dotted = _dotted(pkg + [cname], name)
            sid = _insert_symbol(conn, file_id, name, dotted, kind, line,
                                 scope_id=cid, signature=_sig(fn),
                                 type_name="method")
        elif getattr(fn, "kind", "") == "main":
            dotted = _dotted(pkg, name)
            sid = _insert_symbol(conn, file_id, name, dotted, "function",
                                 line, signature=_sig(fn))
            main_name = name
        elif getattr(fn, "kind", "") == "script":
            dotted = _dotted(pkg, name)
            sid = _insert_symbol(conn, file_id, name, dotted, "script",
                                 line, signature=_sig(fn))
        else:
            dotted = _dotted(pkg + [main_name or "<file>"], name)
            sid = _insert_symbol(conn, file_id, name, dotted,
                                 "local_function", line, signature=_sig(fn))
        if sid:
            func_rows.append((sid, fn))
    return func_rows


class _TargetFile(object):
    def __init__(self, rel):
        self.rel = rel


class _CallTarget(object):
    """给 matlabc.analyze_calls 用的轻量目标（只依赖它读取的属性）。"""

    def __init__(self, symbol_id, name, dotted, class_name, line, rel):
        self.symbol_id = symbol_id
        self.name = name
        self.qualified = dotted
        self.class_name = class_name
        self.line = line
        self.mfile = _TargetFile(rel)


def _call_index(conn, project_id):
    rows = conn.execute(
        "SELECT s.id, s.name, s.dotted_name, s.kind, s.line, s.scope_id, "
        "f.path FROM symbols s JOIN files f ON s.file_id=f.id "
        "WHERE f.project_id=?", (project_id,)).fetchall()
    class_names = {}
    for r in rows:
        if r["kind"] == "class":
            class_names[r["id"]] = r["dotted_name"].split(".")[-1]
    short, qualified = {}, {}
    for r in rows:
        if r["kind"] not in ("function", "local_function", "method",
                             "constructor", "script"):
            continue
        cname = class_names.get(r["scope_id"], "")
        t = _CallTarget(r["id"], r["name"], r["dotted_name"], cname,
                        r["line"], r["path"])
        short.setdefault(r["name"].lower(), []).append(t)
        qualified.setdefault(r["dotted_name"].lower(), []).append(t)
        if cname:
            qualified.setdefault((cname + "." + r["name"]).lower(),
                                 []).append(t)
    return short, qualified


def _ref_index(conn, project_id):
    idx = {}
    for r in conn.execute(
            "SELECT s.id, s.name, s.line FROM symbols s JOIN files f "
            "ON s.file_id=f.id WHERE f.project_id=?", (project_id,)):
        idx.setdefault(r["name"].lower(), []).append((r["id"], r["line"]))
    return idx


def _call_line(fn, target):
    for site in getattr(fn, "call_sites", None) or ():
        try:
            if len(site) >= 4 and site[3] is target:
                return int(site[0])
        except (TypeError, ValueError):
            continue
    return int(getattr(fn, "line", 1) or 1)


def _insert_edges(conn, file_id, func_rows, short_index):
    seen = set()

    def add(sid, callee, kind, confidence, dst=None, line=1, weight=1):
        key = (sid, callee.lower(), kind, dst)
        if not callee or key in seen:
            return
        seen.add(key)
        conn.execute(
            "INSERT INTO edges(src_symbol_id, dst_symbol_id, callee_name, "
            "kind, line, confidence, weight, file_id) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (sid, dst, callee, kind, line, confidence, weight, file_id))

    for sid, fn in func_rows:
        # 项目内直接调用：analyze_calls 已解析为具体对象
        for target in getattr(fn, "calls", None) or ():
            add(sid, getattr(target, "name", "") or "?",
                "call", 1.0, getattr(target, "symbol_id", None),
                _call_line(fn, target))
        for kind, conf, attr in (
                ("builtin", 0.90, "builtin_calls"),
                ("external", 0.35, "external_calls"),
                ("dynamic", 0.15, "dynamic_calls"),
                ("indirect", 0.25, "indirect_calls")):
            counter = getattr(fn, attr, None) or {}
            for callee, weight in counter.items():
                dst = None
                # external 名字如果已经在符号库出现，补一个目标，但降置信度
                cands = short_index.get(str(callee).lower()) or []
                if kind == "external" and cands:
                    dst = cands[0].symbol_id
                    conf = 0.55
                add(sid, str(callee), kind, conf, dst,
                    int(getattr(fn, "line", 1) or 1), int(weight or 1))


def _insert_refs(conn, file_id, mf, ref_index):
    lines = getattr(mf, "source_lines", None) or []
    scrubbed = getattr(mf, "scrubbed_lines", None) or lines
    local = {}
    for r in conn.execute("SELECT id, name, line FROM symbols WHERE file_id=?",
                          (file_id,)):
        local.setdefault(r["name"].lower(), []).append((r["id"], r["line"]))
    for lineno, line in enumerate(scrubbed, start=1):
        for m in re.finditer(r"[A-Za-z_]\w*", line):
            name = m.group(0)
            cands = local.get(name.lower()) or ref_index.get(name.lower()) or []
            if not cands:
                continue
            sid, sline = cands[0]
            kind = "definition" if lineno == sline else "reference"
            context = (lines[lineno - 1] if lineno <= len(lines) else "")[:200]
            conn.execute(
                "INSERT INTO refs(symbol_id, file_id, line, col, kind, "
                "context, confidence) VALUES(?,?,?,?,?,?,?)",
                (sid, file_id, lineno, m.start() + 1, kind, context,
                 1.0 if len(cands) == 1 else 0.8))


def _delete_file(conn, file_id):
    conn.execute("DELETE FROM files WHERE id=?", (file_id,))


def sync_project(cfg, full=False, dry_run=False):
    conn = _connect(cfg["_db"])
    try:
        init_db(conn)
        project_id = _upsert_project(conn, cfg)
        scanned, added, changed, removed, unchanged = _changes(
            cfg, conn, project_id, full=full)
        summary = {"added": len(added), "changed": len(changed),
                   "removed": len(removed), "unchanged": len(unchanged),
                   "files": len(scanned), "symbols": 0, "edges": 0}
        if dry_run:
            conn.rollback()
            return summary
        # 删除消失文件
        old = _db_files(conn, project_id)
        for rel in removed:
            _delete_file(conn, old[rel]["id"])
        # 删除并重建 changed/added
        pending = []
        for rel in added + changed:
            full_path = os.path.join(cfg["_root"], rel.replace("/", os.sep))
            rec = old.get(rel)
            if rec is not None:
                _delete_file(conn, rec["id"])
            try:
                st = os.stat(full_path)
                sha = _sha256(full_path)
            except OSError as exc:
                summary.setdefault("errors", []).append("%s: %s" % (rel, exc))
                continue
            cur = conn.execute(
                "INSERT INTO files(project_id, path, lang, mtime_ns, size, "
                "sha256, parse_status, indexed_at) VALUES(?,?,?,?,?,?,?,?)",
                (project_id, rel, "matlab", st.st_mtime_ns, st.st_size, sha,
                 "ok", _now()))
            file_id = cur.lastrowid
            mf = matlabc.MatlabFile(matlabc.Path(full_path), rel)
            try:
                matlabc.parse_file(mf)
                status = "ok" if not mf.parse_errors else "error"
                conn.execute("UPDATE files SET parse_status=?, parse_error=? "
                             "WHERE id=?",
                             (status, "; ".join(mf.parse_errors), file_id))
                pending.append((file_id, rel, mf))
            except Exception as exc:  # noqa: BLE001 - 单文件失败不拖垮全项目
                conn.execute("UPDATE files SET parse_status='error', "
                             "parse_error=? WHERE id=?", (str(exc), file_id))
        # 先插符号；再用全库符号做调用解析（含未改文件的目标）
        pending_edges = []
        for file_id, rel, mf in pending:
            func_rows = _insert_file_symbols(conn, file_id, rel, mf)
            pending_edges.append((file_id, mf, func_rows))
        short, qualified = _call_index(conn, project_id)
        ref_index = _ref_index(conn, project_id)
        for file_id, mf, func_rows in pending_edges:
            try:
                matlabc.analyze_calls(mf, short, qualified)
            except Exception as exc:  # noqa: BLE001 - 单文件调用分析失败不拖垮全项目
                conn.execute("UPDATE files SET parse_status='error', "
                             "parse_error=? WHERE id=?",
                             ("call analysis: %s" % exc, file_id))
            conn.execute("DELETE FROM edges WHERE file_id=?", (file_id,))
            conn.execute("DELETE FROM refs WHERE file_id=?", (file_id,))
            _insert_edges(conn, file_id, func_rows, short)
            _insert_refs(conn, file_id, mf, ref_index)
        for name, value in (cfg.get("conditions") or {}).items():
            conn.execute("INSERT OR REPLACE INTO conditions(project_id, name, "
                         "value) VALUES(?,?,?)",
                         (project_id, name, str(value)))
        conn.execute("INSERT OR REPLACE INTO meta(key, value) "
                     "VALUES('last_sync', ?)", (_now(),))
        conn.commit()
        summary["symbols"] = conn.execute(
            "SELECT COUNT(*) AS n FROM symbols s JOIN files f "
            "ON s.file_id=f.id WHERE f.project_id=?",
            (project_id,)).fetchone()["n"]
        summary["edges"] = conn.execute(
            "SELECT COUNT(*) AS n FROM edges e JOIN files f "
            "ON e.file_id=f.id WHERE f.project_id=?",
            (project_id,)).fetchone()["n"]
        summary["refs"] = conn.execute(
            "SELECT COUNT(*) AS n FROM refs r JOIN files f "
            "ON r.file_id=f.id WHERE f.project_id=?",
            (project_id,)).fetchone()["n"]
        return summary
    finally:
        conn.close()


def status_project(cfg):
    conn = _connect(cfg["_db"])
    try:
        init_db(conn)
        project_id = _upsert_project(conn, cfg)
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM files WHERE project_id=?",
            (project_id,)).fetchone()["n"]
        syms = conn.execute(
            "SELECT COUNT(*) AS n FROM symbols s JOIN files f "
            "ON s.file_id=f.id WHERE f.project_id=?",
            (project_id,)).fetchone()["n"]
        edges = conn.execute(
            "SELECT COUNT(*) AS n FROM edges e JOIN files f "
            "ON e.file_id=f.id WHERE f.project_id=?",
            (project_id,)).fetchone()["n"]
        refs = conn.execute(
            "SELECT COUNT(*) AS n FROM refs r JOIN files f "
            "ON r.file_id=f.id WHERE f.project_id=?",
            (project_id,)).fetchone()["n"]
        last = conn.execute(
            "SELECT value FROM meta WHERE key='last_sync'").fetchone()
        scanned, added, changed, removed, unchanged = _changes(
            cfg, conn, project_id, full=False)
        return {"project": cfg["name"], "root": cfg["_root"],
                "db": cfg["_db"], "files": rows, "symbols": syms,
                "edges": edges, "refs": refs,
                "stale": len(added) + len(changed),
                "removed": len(removed),
                "last_sync": last["value"] if last else ""}
    finally:
        conn.close()


def query_symbols(cfg, query="", kind="", file_like="", limit=200):
    conn = _connect(cfg["_db"])
    try:
        init_db(conn)
        sql = ("SELECT s.name, s.dotted_name, s.kind, s.line, s.signature, "
               "s.resolution, f.path FROM symbols s "
               "JOIN files f ON s.file_id=f.id ")
        where, args = [], []
        if query:
            where.append("(lower(s.name) LIKE ? OR lower(s.dotted_name) LIKE ?)")
            q = "%%%s%%" % query.lower()
            args.extend([q, q])
        if kind:
            where.append("s.kind=?")
            args.append(kind)
        if file_like:
            where.append("lower(f.path) LIKE ?")
            args.append("%%%s%%" % file_like.lower())
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY f.path, s.line LIMIT ?"
        args.append(int(limit))
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def query_refs(cfg, name="", limit=200):
    conn = _connect(cfg["_db"])
    try:
        init_db(conn)
        sql = ("SELECT s.name, s.dotted_name, r.line, r.col, r.kind, "
               "r.context, r.confidence, f.path FROM refs r "
               "JOIN symbols s ON r.symbol_id=s.id "
               "JOIN files f ON r.file_id=f.id ")
        where, args = [], []
        if name:
            where.append("(lower(s.name) LIKE ? OR lower(s.dotted_name) LIKE ?)")
            q = "%%%s%%" % name.lower()
            args.extend([q, q])
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY f.path, r.line, r.col LIMIT ?"
        args.append(int(limit))
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def query_edges(cfg, name="", kind="", limit=200):
    conn = _connect(cfg["_db"])
    try:
        init_db(conn)
        sql = ("SELECT src.name AS src, dst.name AS dst, e.callee_name, "
               "e.kind, e.line, e.confidence, e.weight, f.path "
               "FROM edges e JOIN symbols src ON e.src_symbol_id=src.id "
               "LEFT JOIN symbols dst ON e.dst_symbol_id=dst.id "
               "JOIN files f ON e.file_id=f.id ")
        where, args = [], []
        if name:
            where.append("(lower(src.name) LIKE ? OR "
                         "lower(e.callee_name) LIKE ?)")
            q = "%%%s%%" % name.lower()
            args.extend([q, q])
        if kind:
            where.append("e.kind=?")
            args.append(kind)
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY f.path, e.line LIMIT ?"
        args.append(int(limit))
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def _decode_text(path):
    raw = open(path, "rb").read()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass
    if b"\x00" in raw[:4096]:
        raise ValueError("二进制文件/不支持的 SI 格式：%s" % path)
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法解码：%s" % path)


def _xml_paths(text):
    if "<" not in text or ">" not in text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    out = []
    for el in root.iter():
        for key in ("path", "file", "filename", "name"):
            val = el.attrib.get(key)
            if val and (os.sep in val or "/" in val
                        or os.path.splitext(val)[1]):
                out.append(val)
        tag = str(el.tag).lower()
        if tag in ("file", "path", "folder", "directory") and el.text:
            val = el.text.strip()
            if val:
                out.append(val)
    return out


def _line_paths(text):
    out = []
    for line in text.splitlines():
        ln = line.strip().strip("\ufeff")
        if not ln or ln.startswith((";", "#", "//")):
            continue
        ln = re.sub(r"^(?:file|path|include|folder|directory)\s*=\s*",
                    "", ln, flags=re.I)
        ln = ln.strip().strip('"\'')
        if not ln or "<" in ln or ">" in ln:
            continue
        bare = re.match(r"^[A-Za-z0-9_.+@-]+$", ln) is not None
        if os.path.isabs(ln) or "/" in ln or "\\" in ln or bare:
            out.append(ln)
    return out


def _rel_safe(root, path):
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        raise ValueError("导入路径与 root 不在同一盘：%s" % path)
    rel = rel.replace(os.sep, "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel or "."


def import_project(cfg, source, write=False):
    """导入 `.siproj` / Master File List 的**文件清单**，不导入符号。"""
    source = os.path.abspath(source)
    if not os.path.isfile(source):
        raise ValueError("找不到导入文件：%s" % source)
    text = _decode_text(source)
    cands = _xml_paths(text) + _line_paths(text)
    seen = set()
    resolved = []
    base_dirs = (os.path.dirname(source), cfg["_root"])
    for cand in cands:
        cand = cand.strip().strip('"\'')
        if not cand or cand in seen:
            continue
        seen.add(cand)
        for base in base_dirs:
            p = cand if os.path.isabs(cand) else os.path.join(base, cand)
            p = os.path.abspath(p)
            if os.path.exists(p):
                resolved.append(p)
                break
    if not resolved:
        raise ValueError("没有找到任何存在的路径（候选 %d 条）" % len(seen))
    source_dirs = list(cfg.get("source_dirs") or ["."])
    include = list(cfg.get("include") or list(DEFAULT_INCLUDE))
    ext_map = cfg.get("file_types") or {".m": "matlab"}
    for p in resolved:
        if os.path.isdir(p):
            source_dirs.append(_rel_safe(cfg["_root"], p))
        else:
            source_dirs.append(_rel_safe(cfg["_root"], os.path.dirname(p)))
            ext = os.path.splitext(p)[1].lower()
            if ext in ext_map:
                include.append("**/*" + ext)
    # 去重并保持稳定顺序
    source_dirs = sorted(set(source_dirs))
    include = sorted(set(include))
    cfg["source_dirs"] = source_dirs
    cfg["include"] = include
    if write:
        public = dict((k, v) for k, v in cfg.items() if not k.startswith("_"))
        _write_json(cfg["_project_path"], public)
    return {"source": source, "candidates": len(seen),
            "resolved": len(resolved), "source_dirs": source_dirs,
            "include": include, "written": bool(write)}


def _print_summary(s):
    print("files=%(files)d added=%(added)d changed=%(changed)d "
          "removed=%(removed)d unchanged=%(unchanged)d "
          "symbols=%(symbols)d edges=%(edges)d refs=%(refs)d" % s)


def main(argv=None):
    ap = argparse.ArgumentParser(description=".mlcproj + SQLite 项目符号库")
    ap.add_argument("--project", help=".mlcproj 路径（默认向上查找）")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="创建项目")
    p.add_argument("--root", default=".")
    p.add_argument("--name")
    p.add_argument("--source-dir", action="append", dest="source_dirs")
    p.add_argument("--include", action="append")
    p.add_argument("--exclude", action="append")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("sync", help="增量同步符号")
    p.add_argument("--root", default=".")
    p.add_argument("--full", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("status", help="项目状态")
    p.add_argument("--root", default=".")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("symbols", help="查询符号")
    p.add_argument("--root", default=".")
    p.add_argument("--query", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--file", dest="file_like", default="")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("edges", help="查询调用/关系边")
    p.add_argument("--root", default=".")
    p.add_argument("--name", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("refs", help="查询符号引用")
    p.add_argument("--root", default=".")
    p.add_argument("--name", default="")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("import", help="导入 .siproj / Master File List")
    p.add_argument("--from", dest="source", required=True)
    p.add_argument("--root", default=".")
    p.add_argument("--write", action="store_true")
    p.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 2
    try:
        if args.cmd == "init":
            path = init_project(args.root, name=args.name,
                                source_dirs=args.source_dirs,
                                include=args.include, exclude=args.exclude,
                                force=args.force)
            print("created %s" % path)
            return 0
        project_path = args.project or find_project(
            getattr(args, "root", ".") or ".")
        if not project_path:
            print("找不到 .mlcproj；先运行 init")
            return 2
        cfg = load_config(project_path)
        if args.cmd == "import":
            s = import_project(cfg, args.source, write=args.write)
            if args.json:
                print(json.dumps(s, ensure_ascii=False, indent=2))
            else:
                print("resolved=%d source_dirs=%s include=%s written=%s"
                      % (s["resolved"], s["source_dirs"], s["include"],
                         s["written"]))
            return 0
        if args.cmd == "sync":
            s = sync_project(cfg, full=args.full, dry_run=args.dry_run)
            if args.json:
                print(json.dumps(s, ensure_ascii=False, indent=2))
            else:
                _print_summary(s)
            return 0
        if args.cmd == "edges":
            rows = query_edges(cfg, name=args.name, kind=args.kind,
                               limit=args.limit)
            if args.json:
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            else:
                for r in rows:
                    print("%-20s -> %-20s %-9s %.2f %s:%d"
                          % (r["src"], r["dst"] or r["callee_name"],
                             r["kind"], r["confidence"], r["path"],
                             r["line"]))
            return 0
        if args.cmd == "refs":
            rows = query_refs(cfg, name=args.name, limit=args.limit)
            if args.json:
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            else:
                for r in rows:
                    print("%-22s %-11s %s:%d:%d  %s"
                          % (r["name"], r["kind"], r["path"], r["line"],
                             r["col"], r["context"].strip()))
            return 0
        if args.cmd == "status":
            s = status_project(cfg)
            if args.json:
                print(json.dumps(s, ensure_ascii=False, indent=2))
            else:
                print("project=%(project)s files=%(files)d symbols=%(symbols)d "
                      "edges=%(edges)d refs=%(refs)d stale=%(stale)d "
                      "removed=%(removed)d" % s)
            return 0
        if args.cmd == "symbols":
            rows = query_symbols(cfg, query=args.query, kind=args.kind,
                                 file_like=args.file_like, limit=args.limit)
            if args.json:
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            else:
                for r in rows:
                    print("%-42s %-14s %s:%d  %s"
                          % (r["dotted_name"], r["kind"], r["path"],
                             r["line"], r["signature"]))
            return 0
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        print("mlc_project: %s" % exc)
        return 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
