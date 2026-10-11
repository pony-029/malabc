"""引用解析：把「代码里提到的库名」变成「磁盘上的文件 + 它的分析结果」。

R86-2 要解决的问题：

    分析一个工程时，代码**引用了**动态库 —— 构建脚本里的 `-lcurl`、
    ELF 的 `DT_NEEDED libz.so.1`、PE 导入表里的 `KERNEL32.dll`、
    Mach-O 的 `LC_LOAD_DYLIB @rpath/libx.dylib`。但 `--binary-attach`
    只认「你已经找到、并把路径写全」的文件。于是
    「只要代码里涉及的二进制都要被处理」这件事**第一次断在
    「名字 → 文件」这一步**，而且断得没有任何对手方：
    `attribute.missing_dependencies()` 只会说「你可能还想再传哪个库进来」。

本模块补的就是这一步，并把「补的过程」本身做成**可核查的证据**：

    refs（名字 + 出处 + 机制）                        ← 三个真实来源
      │
      ▼  ①候选名展开   ②在搜索目录里建索引   ③三趟匹配（精确→忽略大小写→家族）
    ┌────────────────────────────────────────────────────────────────┐
    │ resolved    恰好 1 个文件 → 解析它，并沿它自己的依赖继续下钻    │
    │ ambiguous  >1 个文件     → **不猜**，把全部候选列出来          │
    │ not_found   0 个文件     → 记下**搜过哪些目录**（这就是证据）  │
    │ skipped     受深度/节点上限约束 → 显式标记，不静默消失          │
    └────────────────────────────────────────────────────────────────┘

三条纪律（与 `attribute.py` 的归因三态是同一套）：

  * **不猜路径**。`buildsys.library_family` 的老话照旧：那里只做名字归一。
    本模块是 binfmt 里**唯一**允许碰磁盘去「找文件」的一层，正因为如此，
    它的每一次「没找到」都必须能说出「找过哪儿」——
    `searched` 因此是**必填字段**，不是可选装饰。
  * **不确定就报不确定**。两个目录下都有 `libfoo.so` ⇒ `ambiguous`，
    绝不按目录顺序取第一个（那会把一个假阳性洗成一条结论，比不解析更糟）。
  * **只往前走，不回头**。深度与节点数都有硬上限；一被截断就记在
    `truncated_by_depth` / `truncated_by_nodes` 里，**不静默**。

零依赖：只用标准库（os / sys / glob）。不执行任何文件。
"""
import glob
import os
import sys

from .buildsys import (RE_DYLIB_FAMILY, RE_SO_FAMILY, lib_flag_to_candidates,
                       library_family)
from .container import parse
from .model import (
    DEP_ID_DYLIB, DEP_IMPORT_MODULE, DEP_LOAD_DYLIB, DEP_LOAD_DYLINKER,
    DEP_NEEDED, DEP_RPATH, DEP_RUNPATH,
)

# ---- 解析三态 + skipped（与 attribute.py 的归因三态同一套值域） ----
RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not_found"
SKIPPED = "skipped"

# ---- 「谁在引用」的机制。三个来源各自独立，报告里**不合并** ----
REF_EXPLICIT = "explicit"          # 用户直接给的名字（不是路径）
REF_LINK_FLAG = "link_flag"        # 构建脚本里的 -lfoo
REF_NEEDED = "needed"              # ELF DT_NEEDED
REF_IMPORT_MODULE = "import_module"   # PE 导入表
REF_LOAD_DYLIB = "load_dylib"      # Mach-O LC_LOAD_DYLIB 一族

# 「这个依赖是**库**」的白名单 —— 与 attribute._NOT_A_LIBRARY 同一个判断，
# 只是那边是黑名单写法。搜索路径不是库，不能拿去解析。
LIBRARY_KINDS = (DEP_NEEDED, DEP_IMPORT_MODULE, DEP_LOAD_DYLIB,
                 REF_NEEDED, REF_IMPORT_MODULE, REF_LOAD_DYLIB)
NON_LIBRARY_KINDS = (DEP_RPATH, DEP_RUNPATH, DEP_LOAD_DYLINKER, DEP_ID_DYLIB)

# 硬上限：搜索面不得被病态输入放大
MAX_DIRS = 64
MAX_DIR_ENTRIES = 20000
MAX_CANDIDATES = 16
DEFAULT_MAX_NODES = 64
DEFAULT_MAX_DEPTH = 2

# matched_by 的取值。三趟**有序**匹配，先中先赢，且把是哪一趟写进结果 ——
# 「忽略大小写」这一趟只在 Windows 语义下才成立，所以它必须可被看见。
MATCH_EXACT = "exact"
MATCH_EXACT_CI = "exact_ci"
MATCH_FAMILY = "family"
MATCH_PATH = "path"

# 歧义一旦超过这个规模就**不再尝试消歧** —— 逐个读头部是有代价的，
# 而歧义集合本来就不该大（同名不同文件的库通常是一对 32/64 位孪生）。
MAX_DISAMBIGUATE = 8

_MULTIARCH_GLOBS = ("/*-linux-gnu*", "/*-linux-musl*")


def platform_defaults(platform="auto"):
    """平台默认的库搜索目录。**只返回真实存在的目录**（os.path.isdir 过滤）。

    ⚠ 允许显式指定 `platform`，因为被解析的是**目标二进制的平台**，不是本机。
      在一台 Windows 上分析一棵 Linux 树的产物时，「当前平台是 Windows」
      这句话与本次解析毫无关系 —— 硬按 `sys.platform` 取默认值会把
      `searched` 填成一串在这台机器上毫无意义的路径。
      取值 `"none"` 表示**不要任何平台默认目录**（只用 `--lib-path` 给的），
      这样同一次解析在任何机器上给同一答案 —— 需要确定性的护栏用它。
    """
    if platform == "auto" or not platform:
        if sys.platform.startswith("win"):
            platform = "windows"
        elif sys.platform == "darwin":
            platform = "macos"
        else:
            platform = "linux"
    out = []
    if platform == "none":
        # R86-2：**刻意**不给任何平台默认目录。存在的理由是「确定性」——
        # 一道必须在任何机器上都给同一答案的护栏（或回归测试），
        # 不能因为开发机上恰好有 /usr/lib/libz.so 而改变结论。
        # 这不是「关掉功能」：`--lib-path` 给的目录照样生效。
        return []
    if platform == "windows":
        root = os.environ.get("SystemRoot") or r"C:\Windows"
        out += [os.path.join(root, "System32"), os.path.join(root, "SysWOW64"),
                root]
    elif platform == "macos":
        out += ["/usr/lib", "/usr/local/lib", "/opt/homebrew/lib",
                "/System/Library/Frameworks", "/Library/Frameworks"]
    else:
        out += ["/lib", "/lib64", "/usr/lib", "/usr/lib64", "/usr/local/lib",
                "/usr/libexec", "/usr/local/lib64"]
        for pat in _MULTIARCH_GLOBS:
            try:
                out += sorted(glob.glob("/usr/lib" + pat))
            except OSError:
                pass
    seen, uniq = set(), []
    for d in out:
        d = os.path.normpath(d)
        if d in seen:
            continue
        seen.add(d)
        try:
            if os.path.isdir(d):
                uniq.append(d)
        except OSError:
            continue
    return uniq


def build_search_dirs(extra=None, platform="auto"):
    """返回 `(dirs, notes)`。extra 里的目录**按给定顺序排在默认目录之前** ——
    「我指给你看的地方」优先于「系统默认」，这是用户的显式意图。"""
    notes = []
    out = []
    for d in (extra or []):
        d = os.path.normpath(str(d))
        if not d:
            continue
        if not os.path.isdir(d):
            notes.append("resolve: --lib-path 里的 %s 不是目录，已跳过"
                         "（**不静默**：它会出现在 searched 之外）" % d)
            continue
        if d not in out:
            out.append(d)
    defaults = platform_defaults(platform)
    for d in defaults:
        if d not in out:
            out.append(d)
    if len(out) > MAX_DIRS:
        notes.append("resolve: 搜索目录数 %d 超上限 %d，只保留前 %d 个"
                     % (len(out), MAX_DIRS, MAX_DIRS))
        out = out[:MAX_DIRS]
    if not out:
        notes.append("resolve: 没有可搜索的目录（平台默认目录都不存在，"
                     "且未给 --lib-path）—— 此时一切解析只能是 not_found")
    return out, notes


class DirIndex(object):
    """一个目录的**一次** listdir 快照。

    为什么建索引而不是对每个候选名 os.path.exists：一个 not_found 的库要试
    MAX_CANDIDATES 个名字 × 每个搜索目录，逐个 exists 会把文件系统打爆；
    而且「目录里到底有什么」这个事实**只该读一次**，否则同一个目录在两次
    查询之间变了，报告就会自相矛盾。
    """

    __slots__ = ("root", "entries", "error")

    def __init__(self, root):
        self.root = root
        self.entries = []
        self.error = ""
        try:
            names = sorted(os.listdir(root))
        except OSError as e:
            self.error = "%s: %s" % (type(e).__name__, e)
            return
        n = 0
        for nm in names:
            if n >= MAX_DIR_ENTRIES:
                self.error = "条目数超上限 %d，已截断" % MAX_DIR_ENTRIES
                break
            p = os.path.join(root, nm)
            try:
                if os.path.isfile(p):
                    self.entries.append(nm)
                    n += 1
            except OSError:
                continue

    def find(self, pred):
        return [os.path.join(self.root, nm) for nm in self.entries if pred(nm)]


def candidate_names(name):
    """把一个引用名展开成**候选文件名**列表（保持顺序，去重）。

    两支**必须分开**，判据是「名字本身是不是一个库文件名」：

        libfoo.so.1 / KERNEL32.dll / libz.dylib   ← 已经是文件名
            ⇒ 只补一个「去版本后缀的规范名」（SONAME 惯例：libfoo.so.1 ← libfoo.so）
        blas / cublas / m                     ← 是 `-l` 简名
            ⇒ 走 lib_flag_to_candidates 的四条拼法（libX.so / X.dll / …）

    为什么必须分：对**已经是文件名**的名字再套一遍拼法，会产出
    `libfoo.so.1.so` 这种噪音候选。它不会「找不到」（照样会去比），
    但会把报告的候选串拉长、把歧义读出搞浑 —— 而歧义读数是这条链上
    唯一会**阻止**解析的判据，不能让噪音去碰它。
    """
    out = []
    base = str(name or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    if base:
        out.append(base)
    fam = library_family(base) if base else ""
    if base and looks_like_library_filename(base):
        if fam and fam != base:
            out.append(fam)
    else:
        for c in lib_flag_to_candidates(base):
            if c not in out:
                out.append(c)
        if fam and fam not in out:
            out.append(fam)
    if len(out) > MAX_CANDIDATES:
        out = out[:MAX_CANDIDATES]
    return out


def looks_like_library_filename(name):
    """名字本身**已经**是库文件名（而不是 `-l` 简名）。

    判据只有两个来源：`buildsys` 的 .so / .dylib 家族正则，以及 PE 模块扩展名。
    **不硬套模板** —— 认不出就说不像（宁可多试几个候选，也不把两个不同的库
    合并成一个）。
    """
    low = str(name or "").strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not low:
        return False
    if RE_SO_FAMILY.match(low) or RE_DYLIB_FAMILY.match(low):
        return True
    return low.endswith(LIB_EXTS)


# PE / 其它容器的模块扩展名（与 pe.MODULE_EXTS 同口径，此处独立列出是因为
# resolve 要处理的是**引用名**，来源可能是构建脚本，不属于某个容器）
LIB_EXTS = (".dll", ".exe", ".sys", ".drv", ".ocx", ".cpl", ".pyd", ".lib")


def _looks_like_path(name):
    return "/" in name or "\\" in name


def resolve(name, indexes, base_dir=None, extra_paths=None, want_bits=None):
    """把一个引用名解析到磁盘文件。返回 dict（可序列化）。

    `extra_paths` 是「直接给路径」的候选（绝对路径 / 相对 base_dir 的路径），
    它们在搜索目录**之前**被检查 —— 用户既然写了路径，就按路径办。
    `want_bits` 是**引用方自己的位数**（解析不到时给 None）：它只用于歧义消解，
    见 `disambiguate_by_bits`。
    """
    res = {
        "name": name,
        "status": NOT_FOUND,
        "path": "",
        "real_path": "",
        "matched_by": "",
        "candidates": candidate_names(name),
        "searched": [ix.root for ix in indexes],
        "hits": [],
        "rejected": [],
        "detail": "",
    }
    # ---- ① 直接给路径的形态 ----
    direct = []
    for p in (extra_paths or []):
        if not p:
            continue
        if not os.path.isabs(p) and base_dir:
            p = os.path.join(base_dir, p)
        direct.append(os.path.normpath(p))
    if os.path.isabs(str(name)):
        direct.append(os.path.normpath(str(name)))
    elif _looks_like_path(str(name)) and base_dir:
        direct.append(os.path.normpath(os.path.join(base_dir, str(name))))
    hits = []
    for p in direct:
        try:
            if os.path.isfile(p):
                hits.append(p)
        except OSError:
            continue
    if hits:
        return _finish(res, hits, MATCH_PATH, "路径形态的引用直接命中",
                       want_bits)
    if _looks_like_path(str(name)) and not base_dir:
        res["detail"] = ("引用里含路径分隔符，但该引用没有出处目录可作基准 —— "
                         "**不猜**相对谁")
        return res

    # ---- ② 三趟有序匹配：精确 → 忽略大小写 → 家族 ----
    cands = res["candidates"]
    passes = (
        (MATCH_EXACT, lambda nm, _c=set(cands): nm in _c),
        (MATCH_EXACT_CI,
         lambda nm, _c=set(c.lower() for c in cands): nm.lower() in _c),
    )
    for tag, pred in passes:
        hits = []
        for ix in indexes:
            hits += ix.find(pred)
        if hits:
            return _finish(res, hits, tag,
                           "按%s在 %d 个目录里匹配候选名 %s"
                           % (tag, len(indexes), "/".join(cands[:4])),
                           want_bits)
    fam = library_family(name)
    if fam:
        hits = []
        for ix in indexes:
            hits += ix.find(lambda nm, _f=fam: library_family(nm) == _f)
        if hits:
            return _finish(res, hits, MATCH_FAMILY,
                           "按家族名 %s 匹配（SO 的 .so.N / dylib 的 .N.dylib "
                           "等版本后缀归一后相同）" % fam, want_bits)
    res["detail"] = ("在 %d 个搜索目录里，候选名 %s 与家族名 %s 均无匹配"
                     % (len(indexes), "/".join(cands[:4]), fam or "?"))
    return res


def _container_bits(path):
    """廉价地读一个候选文件自己的**位数**。读不出返回 None（**不猜**）。

    这不是启发式：位数是候选文件**自己的头部**声明的事实，读它与读文件大小
    没有区别。正因为它可观测，才能拿来当**消歧判据**。
    """
    try:
        rep = parse(path, scan_cap=0, with_gpu=False)
    except Exception:
        return None
    bits = getattr(rep, "bits", 0)
    return bits or None


def disambiguate_by_bits(uniq, want_bits):
    """用「候选文件自己的位数」在歧义集合里做一次**可观测的**消歧。

    真实语料（装机实测）：`C:\\Windows\\System32\\kernel32.dll` 与
    `C:\\Windows\\SysWOW64\\kernel32.dll` **同名、不同文件、不同位数**。
    Windows 加载器按映像位数选其中之一 —— 那不是猜，是**规则**。
    这里把同一条规则实现成：留下位数与请求方相同的候选。

    三条边界（否则它就退化成猜）：
      * `want_bits` 未知 ⇒ **不消歧**，原样返回；
      * 候选数 > `MAX_DISAMBIGUATE` ⇒ 不消歧（代价失控时宁可说不知道）；
      * 排除后**一份不剩** ⇒ 不消歧（那是「一个都对不上」，不是「分不清」）。
    ⚠ 排除后**剩多于 1 份**时**仍然要返回被缩小的集合** —— 这不是猜：
      被排除的每一份都已**证明**与请求方位数不同，把它们留在候选里
      等于让一条已判定的假信息继续参与裁决（R86-2 探针的自维持断言
      当场抓到过这一条：3 份候选里明明排掉了 1 份 32 位，却整体退回了歧义）。
    返回 `(kept, rejected)`：rejected 里带每个候选自己的位数，
    于是「为什么被排除」永远能复述。
    """
    if not want_bits or len(uniq) < 2 or len(uniq) > MAX_DISAMBIGUATE:
        return uniq, []
    kept, rejected = [], []
    for path, rp in uniq:
        b = _container_bits(path)
        (kept if b == want_bits else rejected).append((path, rp, b))
    if not kept:
        return uniq, []
    return kept, rejected


def _finish(res, hits, matched_by, detail, want_bits=None):
    uniq, seen = [], set()
    for h in hits:
        try:
            rp = os.path.realpath(h)
        except OSError:
            rp = h
        if rp in seen:
            continue
        seen.add(rp)
        uniq.append((h, rp))
    dis = ""
    if len(uniq) > 1:
        orig_n = len(uniq)
        kept, rejected = disambiguate_by_bits(uniq, want_bits)
        if rejected:
            res["rejected"] = [{"path": p, "bits": b} for p, _rp, b in rejected]
            uniq = [(p, rp) for p, rp, _b in kept]
            dis = ("；同名 %d 份，按**候选自己的位数**=%s 排除 %d 份（%s），"
                   % (orig_n, want_bits, len(rejected),
                      ", ".join("%s(%s位)" % (p, b) for p, _rp, b in rejected))
                   + ("恰剩 1 份 ⇒ 可定"
                      if len(uniq) == 1 else
                      "仍剩 %d 份位数**相同**、判据分不开" % len(uniq)))
    if len(uniq) == 1:
        p, rp = uniq[0]
        res.update(status=RESOLVED, path=p, real_path=rp,
                   matched_by=matched_by, detail=detail + dis)
        return res
    # >1 个**不同的真实文件** ⇒ ambiguous，**不猜**
    res.update(status=AMBIGUOUS, matched_by=matched_by, hits=[p for p, _ in uniq])
    res["detail"] = ("%s，但命中 %d 个**不同的**文件 —— 不猜，全部列出%s"
                     % (detail, len(uniq), dis))
    return res


class ResolveReport(object):
    """一次引用解析的全部产物：节点 + 边 + 没找到的 + 上限记账。"""

    def __init__(self, search_dirs=None, depth=0, max_nodes=0):
        self.search_dirs = list(search_dirs or [])
        self.notes = []
        self.nodes = []            # 每个节点一个 dict（含出处 requested_by）
        self.edges = []            # {"from","to","kind","name"}
        self.not_found = []        # 与节点同形的子集（方便 CLI/JQ 直接取）
        self.ambiguous = []
        self.truncated_by_depth = []
        self.truncated_by_nodes = []
        self.limits = {"depth": depth, "max_nodes": max_nodes}
        self.reports = []          # 真的解析出来的 BinaryReport（给归因索引用）

    def stats(self):
        s = {}
        for n in self.nodes:
            s[n["status"]] = s.get(n["status"], 0) + 1
        return s

    def by_real_path(self, rp):
        for n in self.nodes:
            if n.get("real_path") and n["real_path"] == rp:
                return n
        return None

    def to_dict(self):
        return {
            "search_dirs": list(self.search_dirs),
            "limits": dict(self.limits),
            "stats": self.stats(),
            "nodes": self.nodes,
            "edges": self.edges,
            "not_found": self.not_found,
            "ambiguous": self.ambiguous,
            "truncated_by_depth": self.truncated_by_depth,
            "truncated_by_nodes": self.truncated_by_nodes,
            "notes": self.notes,
        }


def _ref(name, kind, origin="", base_dir=None):
    return {"name": name, "kind": kind, "origin": origin, "base_dir": base_dir}


def resolve_graph(refs, extra_paths=None, platform="auto", depth=DEFAULT_MAX_DEPTH,
                   max_nodes=DEFAULT_MAX_NODES, scan_cap=None, lib_paths=None):
    """从若干引用出发，解析磁盘文件并沿依赖**逐层**下钻。

    `refs` 里每项是 dict：{name, kind, origin 可选, base_dir 可选}。
    `lib_paths` 是**额外的搜索目录**（CLI 的 `--lib-path`），排在平台默认目录之前。
    返回 `ResolveReport`。

    深度语义（写清楚，因为「深度 1」有歧义）：
        depth=0  ⇒ **只解析种子本身**，不下钻（等于「把给定的名字变成文件」）
        depth=1  ⇒ 再往下走一级（种子依赖的库）
        以此类推；`depth` 是**下钻的层数**，不是节点总层数。
    """
    rep = ResolveReport(depth=depth, max_nodes=max_nodes)
    dirs, notes = build_search_dirs(lib_paths, platform)
    rep.search_dirs = dirs
    rep.notes += notes
    indexes = [DirIndex(d) for d in dirs]
    for ix in indexes:
        if ix.error:
            rep.notes.append("resolve: 读取 %s 失败或截断 —— %s" % (ix.root, ix.error))

    if depth < 0:
        depth = 0
    max_nodes = max(1, int(max_nodes or DEFAULT_MAX_NODES))

    # level 里每项：(ref, depth_of_ref, parent_node_index_or_None)
    level = []
    for r in refs:
        if isinstance(r, str):
            level.append((_ref(r, REF_EXPLICIT), 0, None))
        else:
            d = dict(r)
            d.setdefault("kind", REF_EXPLICIT)
            d.setdefault("origin", "")
            d.setdefault("base_dir", None)
            level.append((d, 0, None))

    # 「按名字」的解析缓存：同一层里同一个名字不重复解析。
    # ⚠ 键里必须带 `want_bits` —— 同一个 `kernel32.dll` 被一个 32 位和一个
    #   64 位二进制同时引用时，**消歧结果不同**，缓存键少了它就会把第一个
    #   调用者的答案错给第二个（这正是「两本账共用一个错口径」的微观版本）。
    cache = {}
    bits_of = {}          # real_path -> 该文件自己的位数（消歧时要用）
    cur_depth = 0
    while level and cur_depth <= depth:
        nxt = []
        for ref, d_of_ref, parent in level:
            wb = bits_of.get(parent) if parent else None
            key = (ref["kind"], ref["name"], ref.get("base_dir") or "", wb)
            got = cache.get(key)
            if got is None:
                got = resolve(ref["name"], indexes,
                              base_dir=ref.get("base_dir"),
                              extra_paths=(extra_paths if d_of_ref == 0
                                           else None),
                              want_bits=wb)
                cache[key] = got
            got = dict(got)
            node = {
                "name": ref["name"], "kind": ref["kind"], "origin": ref.get("origin") or "",
                "depth": d_of_ref, "status": got["status"],
                "path": got["path"], "real_path": got["real_path"],
                "matched_by": got["matched_by"], "detail": got["detail"],
                "candidates": got["candidates"], "hits": got["hits"],
                "rejected": got.get("rejected") or [],
                "searched": got["searched"],
                "requested_by": [],
            }
            if parent is not None:
                node["requested_by"].append(
                    {"from": parent, "kind": ref["kind"], "name": ref["name"]})

            if got["status"] == AMBIGUOUS:
                rep.ambiguous.append({"name": ref["name"], "kind": ref["kind"],
                                      "hits": got["hits"], "detail": got["detail"],
                                      "rejected": got.get("rejected") or []})
                rep.nodes.append(node)
                rep.edges.append({"from": parent, "to": "", "to_name": ref["name"],
                                  "kind": ref["kind"], "name": ref["name"],
                                  "status": AMBIGUOUS})
                continue
            if got["status"] != RESOLVED:
                rep.not_found.append({"name": ref["name"], "kind": ref["kind"],
                                      "searched": got["searched"],
                                      "candidates": got["candidates"],
                                      "detail": got["detail"]})
                rep.nodes.append(node)
                rep.edges.append({"from": parent, "to": "", "to_name": ref["name"],
                                  "kind": ref["kind"], "name": ref["name"],
                                  "status": NOT_FOUND})
                continue

            known = rep.by_real_path(got["real_path"])
            if known is not None:
                # 已经解析过（含**环**）：接一条边，不重复解析、不重复计数
                known.setdefault("requested_by", []).append(
                    {"from": parent, "kind": ref["kind"], "name": ref["name"]})
                rep.edges.append({"from": parent, "to": known["real_path"],
                                  "to_name": known["name"],
                                  "kind": ref["kind"], "name": ref["name"],
                                  "status": RESOLVED})
                continue

            if len(rep.reports) >= max_nodes:
                node["status"] = SKIPPED
                node["detail"] = ("达到节点上限 %d，未解析（**不是** not_found）"
                                  % max_nodes)
                rep.truncated_by_nodes.append({"name": ref["name"],
                                               "kind": ref["kind"]})
                rep.nodes.append(node)
                rep.edges.append({"from": parent, "to": "", "to_name": ref["name"],
                                  "kind": ref["kind"], "name": ref["name"],
                                  "status": SKIPPED})
                continue

            try:
                br = parse(got["path"], scan_cap=scan_cap)
            except OSError as e:
                node["status"] = NOT_FOUND
                node["detail"] = "文件存在但读取失败：%s" % e
                rep.nodes.append(node)
                rep.not_found.append({"name": ref["name"], "kind": ref["kind"],
                                      "searched": got["searched"],
                                      "candidates": got["candidates"],
                                      "detail": node["detail"]})
                continue
            rep.reports.append(br)
            rep.nodes.append(node)
            node["container"] = br.container
            node["arch"] = br.arch
            node["bits"] = br.bits
            node["flavour"] = br.flavour
            node["n_symbols"] = len(br.symbols)
            node["n_deps"] = len(br.dependencies)
            node["n_segments"] = len(getattr(br, "segments", []) or [])
            node["mitigations"] = getattr(br, "mitigations", {}) or {}
            node["notes"] = list(br.notes)
            node["path"] = got["path"]
            bits_of[got["real_path"]] = br.bits
            if parent is not None:
                rep.edges.append({"from": parent, "to": got["real_path"],
                                  "kind": ref["kind"], "name": ref["name"],
                                  "status": RESOLVED})

            # ---- 下钻：只跟「是库」的那些依赖 ----
            for d in br.dependencies:
                if d.kind in NON_LIBRARY_KINDS:
                    continue
                if d.kind not in LIBRARY_KINDS:
                    continue
                if d_of_ref + 1 > depth:
                    rep.truncated_by_depth.append(
                        {"name": d.name, "kind": d.kind,
                         "requested_by": got["real_path"]})
                    continue
                nxt.append((_ref(d.name, d.kind, got["path"],
                                 os.path.dirname(got["path"])),
                            d_of_ref + 1, got["real_path"]))
        # 去重：同一层里 (kind,name,base_dir) 只留一份（边已在 requested_by 里）
        uniq, seen = [], set()
        for item in nxt:
            r = item[0]
            k = (r["kind"], r["name"], r.get("base_dir") or "")
            if k in seen:
                continue
            seen.add(k)
            uniq.append(item)
        level = uniq
        cur_depth += 1
        if cur_depth > depth and level:
            for r, _d, _p in level:
                rep.truncated_by_depth.append({"name": r["name"],
                                               "kind": r["kind"],
                                               "requested_by": ""})
            level = []
    return rep


def render_resolution_table(rep, max_rows=40):
    """把解析结果渲染成终端表。**必须**把 searched 与 truncated 打出来 ——
    只说「没找到」而不说「找过哪儿」，用户没有任何办法反驳或纠正它。"""
    L = []
    st = rep.stats()
    L.append("引用解析：%d 个节点  %s"
             % (len(rep.nodes),
                "  ".join("%s=%d" % kv for kv in sorted(st.items())) or "(空)"))
    L.append("搜索目录（%d）：%s"
             % (len(rep.search_dirs), ", ".join(rep.search_dirs) or "(无)"))
    L.append("limits：depth=%s  max_nodes=%s"
             % (rep.limits.get("depth"), rep.limits.get("max_nodes")))
    L.append("-" * 78)
    L.append("%-10s %-14s %-30s %s" % ("status", "kind", "name", "path / detail"))
    shown = 0
    for n in rep.nodes:
        if shown >= max_rows:
            L.append("... 另有 %d 个节点未显示" % (len(rep.nodes) - shown))
            break
        right = n["path"] or n["detail"]
        L.append("%-10s %-14s %-30s %s"
                 % (n["status"], n["kind"], str(n["name"])[:30], right[:70]))
        shown += 1
    if rep.not_found:
        L.append("-" * 78)
        L.append("未找到（%d）—— 下面每一条都列出**找过的目录**，"
                 "便于你判断是「真没有」还是「没找对地方」：" % len(rep.not_found))
        for nf in rep.not_found[:max_rows]:
            L.append("  %-30s %s" % (str(nf["name"])[:30], nf["detail"][:70]))
            for d in nf["searched"][:8]:
                L.append("      搜过: %s" % d)
            if len(nf["searched"]) > 8:
                L.append("      ... 另有 %d 个目录" % (len(nf["searched"]) - 8))
    if rep.ambiguous:
        L.append("-" * 78)
        L.append("有歧义（%d）—— 同名不同文件，**不猜**：" % len(rep.ambiguous))
        for am in rep.ambiguous[:max_rows]:
            L.append("  %s" % str(am["name"])[:40])
            for h in am["hits"][:8]:
                L.append("      %s" % h)
    if rep.truncated_by_depth:
        L.append("-" * 78)
        L.append("因深度上限未展开（%d）：%s"
                 % (len(rep.truncated_by_depth),
                    ", ".join(sorted(set(t["name"] for t in
                                         rep.truncated_by_depth))[:10])))
    if rep.truncated_by_nodes:
        L.append("因节点上限未解析（%d）：%s"
                 % (len(rep.truncated_by_nodes),
                    ", ".join(sorted(set(t["name"] for t in
                                         rep.truncated_by_nodes))[:10])))
    if rep.notes:
        L.append("-" * 78)
        for n in rep.notes:
            L.append("  - %s" % n)
    return "\n".join(L)
