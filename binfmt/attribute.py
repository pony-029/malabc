"""把源码侧的「未解析调用」归因到二进制侧的证据。

这是 binfmt 在本项目里的**唯一目的**：
一个找不到定义的调用，今天只能进「未解析」一个桶 —— 桶里混着三种完全不同的东西，
处理方式也不同。有了二进制符号表，它就能被分开：

    源码里调用了 foo()，定义找不到
                  │
                  ▼  依次查（顺序即优先级）
    ┌──────────────────────────────────────────────────────────┐
    │ ① 提供的二进制里有导出符号 foo？                          │
    │      有 → library:<libname>      「这是某个动态库的函数」 │
    │ ② 是某个 GPU kernel 名（含 demangle 后匹配）？            │
    │      是 → gpu_kernel:<backend>   「这是 CUDA/HIP/Vulkan」 │
    │ ③ 都没有 → missing               「真的漏了」← 这才是缺陷 │
    └──────────────────────────────────────────────────────────┘

边界的纪律（**必须显式，不许猜**）：
本模块的归因只依赖**你显式提供的二进制文件**。没提供的库一律归为 missing，
不假设「它应该在系统某个 lib 里」。这避免了「假装知道」——一个假阳性会把真缺陷
洗白成「来自某个库」，比不归因更糟。
"""
import io
import json
import os

from .model import (
    ATTR_GPU_KERNEL, ATTR_LIBRARY, ATTR_MISSING,
    SYM_DYNAMIC, SYM_EXPORT, SYM_GPU_KERNEL,
)

# 与 C 侧常见调用约定前缀配合做一次「去修饰」尝试
_C_DECOR_PREFIXES = ("__imp_", "_imp__")


def _strip_decor(name):
    for p in _C_DECOR_PREFIXES:
        if name.startswith(p):
            return name[len(p):]
    return name


class SymbolIndex:
    """多个二进制报告的导出符号 / GPU kernel 可查询索引。"""

    def __init__(self):
        self.exports = {}            # name -> [origin]
        self.kernels = {}            # raw name -> [(origin, backend)]
        self.demangled = {}          # demangled -> [(origin, backend)]
        self.reports = []

    def add(self, rep):
        self.reports.append(rep)
        for s in rep.symbols:
            if s.kind in (SYM_EXPORT, SYM_DYNAMIC):
                self.exports.setdefault(s.name, []).append(rep.path)
            elif s.kind == SYM_GPU_KERNEL:
                self.kernels.setdefault(s.name, []).append((rep.path, s.backend))
                if s.demangled:
                    self.demangled.setdefault(s.demangled, []).append(
                        (rep.path, s.backend))
        return self

    def attribute(self, name):
        """归因一个名字。返回 dict（可序列化）。"""
        if not name:
            return {"name": name, "attribution": ATTR_MISSING,
                    "origins": [], "detail": "空名字"}
        cand = [name]
        stripped = _strip_decor(name)
        if stripped != name:
            cand.append(stripped)

        for c in cand:
            hit = self.exports.get(c)
            if hit:
                origins = sorted(set(hit))
                return {"name": name, "attribution": ATTR_LIBRARY,
                        "origins": origins,
                        "detail": "命中导出符号 %s" % c}

        for c in cand:
            hit = self.kernels.get(c) or self.demangled.get(c)
            if hit:
                origins = sorted(set(o for o, _ in hit))
                backends = sorted(set(b for _, b in hit if b))
                return {"name": name, "attribution": ATTR_GPU_KERNEL,
                        "origins": origins,
                        "detail": "命中 GPU kernel %s%s"
                                  % (c, (" backend=" + ",".join(backends))
                                     if backends else "")}

        return {"name": name, "attribution": ATTR_MISSING, "origins": [],
                "detail": "在已提供的 %d 个二进制里均未找到" % len(self.reports)}


def build_index(reports):
    idx = SymbolIndex()
    for r in reports:
        idx.add(r)
    return idx


def attribute_names(names, reports):
    return [build_index(reports).attribute(n) for n in names]


def conflicts(reports):
    """同一导出符号被多个二进制定义 —— 这是纯二进制侧就能发现的真问题。"""
    owner = {}
    for r in reports:
        for s in r.symbols:
            if s.kind == SYM_EXPORT:
                owner.setdefault(s.name, set()).add(r.path)
    return [{"name": k, "origins": sorted(v)}
            for k, v in sorted(owner.items()) if len(v) > 1]


def missing_dependencies(reports):
    """DT_NEEDED / Import 里引用了但没在本次提供的集合中出现的依赖名。

    注意语义：返回的是「你可能还想一起分析哪些库」，不是「这些库不存在」。
    """
    provided = set()
    for r in reports:
        provided.add(os.path.basename(r.path).lower())
    out = []
    for r in reports:
        for d in r.dependencies:
            base = os.path.basename(d.name).lower()
            if base and base not in provided:
                out.append({"from": r.path, "needs": d.name, "kind": d.kind})
    return out


def load_names_from(path):
    """从「名字列表」或「matlabc JSON 输出」里取待归因的名字。

    支持三种输入形态，按内容自动判别（不靠扩展名猜）：
      1) matlabc 的 --json 输出：{"unresolved": [{"callee": ...}, ...]} 或
         {"unresolved": [[name, line, file], ...]} 或 {"unresolved": ["name", ...]}
      2) C 前端的 model：{"c_model": {"unresolved": [...]}}（同样三种形态）
      3) 纯文本：每行一个名字，或逗号/空白分隔
    解析失败时抛 ValueError（不静默返回空列表 —— 空列表会被当成「没有未解析」）。
    """
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(text)
        except ValueError as e:
            raise ValueError("看起来像 JSON 但解析失败：%s" % e)
        names = _harvest_unresolved(data)
        if names is None:
            raise ValueError("JSON 里找不到 unresolved 字段；"
                             "请确认这是 matlabc --json 的输出")
        return names
    # 纯文本
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for part in line.replace(",", " ").split():
            if part:
                out.append(part)
    return out


def _harvest_unresolved(data):
    """在（可能嵌套一层 c_model 的）结构里找 unresolved，容忍三种元素形态。"""
    holders = []
    if isinstance(data, dict):
        holders.append(data)
        if isinstance(data.get("c_model"), dict):
            holders.append(data["c_model"])
        if isinstance(data.get("model"), dict):
            holders.append(data["model"])
    for h in holders:
        raw = h.get("unresolved")
        if raw is None:
            continue
        names = []
        for item in raw:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                nm = item.get("callee") or item.get("name")
                if nm:
                    names.append(nm)
            elif isinstance(item, (list, tuple)) and item:
                names.append(str(item[0]))
        return names
    return None


def render_attribution_table(rows, max_rows=60):
    L = ["%-34s %-22s %s" % ("name", "attribution", "origins / detail")]
    L.append("-" * 78)
    shown = 0
    stat = {}
    for r in rows:
        stat[r["attribution"]] = stat.get(r["attribution"], 0) + 1
        if shown >= max_rows:
            continue
        org = ", ".join(os.path.basename(o) for o in r["origins"]) or r["detail"]
        L.append("%-34s %-22s %s" % (r["name"][:34], r["attribution"], org[:60]))
        shown += 1
    if len(rows) > shown:
        L.append("... 另有 %d 行未显示" % (len(rows) - shown))
    L.append("-" * 78)
    L.append("attribution summary: " + "  ".join(
        "%s=%d" % kv for kv in sorted(stat.items())))
    return "\n".join(L)
