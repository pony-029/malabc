# -*- coding: utf-8 -*-
"""站点**匹配口径** —— R82 Phase A 的「分母可信度」底座（R82b 下一轮建议 7/8/9）。

为什么要单独一个模块（R82b 黑帽 B5 实测）：分母可以被**两件事**悄悄换掉，
而全部门禁**全程绿** ——

  ① 匹配用**子串**：`signal_struct` 里的 `signal`、`signaling`、`forked` 全都
     算成并发站点。实测 `signal` 15,551 / `fork` 5,824，其中 **90% 是子串产物**。
  ② 「锁 / 信号量」被收进 `unknown`：**互斥同步 != 异步站点**，混在一起之后
     `unknown` 从「缺口」退化成**词频**。

两本账共用一个错口径时，**对账永远对得上** —— 实测内核树上双账 13.4 万全绿，
而分母早被换成了「并发相关词频」。所以本模块的立场是：

    只加「对账」不够，必须给**口径本身**配对手方。

落地形态就是**在同一段语料上并列报两种口径**：

    口径                  `signal` 命中     性质
    ─────────────────────────────────────────────────────────────
    子串 substring           15,551        结构性高估（前缀/后缀全进）
    词界 wordbound               ??        只认整词或驼峰（`hThread` ✓，`Threads` ✗）

**超集关系是一条断言**：任何语料上 `wordbound <= substring`。
两个通道描述同一概念的同一侧面时，「超集」是唯一**不依赖第三方**的事实
（R82b §4x-1：独立复算最怕的不是算错，是**独立复刻同一个错**）。两者之差
就是**子串口径的假阳性**，而且它是**可解释**的 —— 解释不了就是真问题。

匹配按 token 的**形状**分派，**不是一刀切词界**（修过头会把短语 token 打死）：

  · 纯标识符 `fork` / `pthread_create` / `await`   ⇒ 两侧标识符边界
  · 命名空间 `std::thread`                          ⇒ 逐段各套一次边界
  · 短语 `new Promise` / `.then(`                   ⇒ 字面量 + 词首边界
    （`.` 与空格本身就是边界；对它们套 `\\b` 会让**整个 token 失配**）

`unknown` 拆两桶（**只在词法层分**；`unified_graph.SITE_OUTCOMES` 一行不动）：

    unknown_async     异步候选（thread / task / future / promise / ...）
    sync_primitives   互斥同步（mutex / semaphore / spin_lock / cond_var / ...）

判据：两桶**并集 == 全部未识别命中**（划分；落不进任何一桶的必须被**报出来**，
不许静默丢 —— R82b §4y-6「缺席不能同时也是信号」）。

**已知边界（诚实记录，不假装覆盖）** —— 两条，**同一种形状**，都靠形状分不开：

  ① 全大写宏（`THREAD_CREATE`）两条分支都不认（小写分支要求严格词界、
     驼峰分支要求首段大写形态）。
  ② **`_` 包裹的小写词干**（`mutex_lock` / `pthread_mutex_lock` /
     `spin_lock_irqsave`）两条分支也都不认 —— 左边界 `(?<![A-Za-z0-9_])`
     被 `_` 挡住，又没有驼峰形态。⚠ 这一条**后果很重**：`mutex_lock()` 是
     内核 C 里最常见的写法，于是**同步桶在真实 C 语料上必然偏少**。

②为什么不能靠调严格形状修好：`__future__`（要排除）与 `pthread_mutex_lock`
（要收）形状**完全同类** —— 都是「词干被 `_` 包住」。任何纯形状规则要么放过
前者、要么漏掉后者。⇒ 下一轮的做法是**并列报第三条口径**（segment 口径：
按 `_` 切段、排除 dunder），让两者的**差**成为可解释的读数，而不是继续调形状
（R82b 定论：只加「对账」不够，必须给**口径本身**配对手方）。

本轮的边界已由 `_r82/probe_r83_caliber_source.py` **登记成断言**：将来修好
②会**变红**，从而强制同步更新本段。
"""
import re

# ── 边界 ────────────────────────────────────────────────────────────────
_B = r"(?<![A-Za-z0-9_])"      # 左边界：前面不是标识符字符
_E = r"(?![A-Za-z0-9_])"       # 右边界：后面不是标识符字符


# ── 形状分类 ────────────────────────────────────────────────────────────
def is_phrase(tok):
    """token 是「短语」而不是单个标识符 —— 含空格、含括号，或以 `.` 开头。

    这一类比什么都重要：把它们按标识符边界匹配会**全部失配**
    （`new Promise` 里没有「标识符边界」可言），那是把口径修过头。
    """
    return (" " in tok) or ("(" in tok) or tok.startswith(".")


def namespace_parts(tok):
    """token 里的**全部**标识符段。`std::thread` -> `('std', 'thread')`；
    `.then(` -> `('then',)`；`new Promise` -> `('new', 'Promise')`。"""
    return tuple(re.findall(r"[A-Za-z_]\w*", tok))


def ident_part(tok):
    """token 里**最后一个**标识符段（`std::thread` -> `thread`）。"""
    parts = namespace_parts(tok)
    return parts[-1] if parts else ""


# ── 两种口径 ────────────────────────────────────────────────────────────
def token_regex(tok):
    """词界口径下，一个 token 的正则片段。

    三种形状，三种边界（**不能一刀切**）：
      标识符 `fork`        ⇒ 两侧标识符边界
      命名空间 `std::thread` ⇒ 逐段各套一次边界（`::` 本身也是边界）
      短语 `new Promise`    ⇒ 词首左边界 + 原样
      **点开头** `.then(`    ⇒ 左边界只能是「前面不是 `.`」。
        它前面**天然**跟着一个对象（`p.then(cb)` / `promise.then(cb)`），
        所以套标识符左边界会**必然失配** —— 本轮新判据第一次开火就抓到了这个。
    """
    if is_phrase(tok):
        if tok.startswith("."):
            return r"(?<!\.)" + re.escape(tok)
        return _B + re.escape(tok)
    if "::" in tok:
        segs = [s for s in tok.split("::") if s]
        return "::".join(_B + re.escape(s) + _E for s in segs)
    return _B + re.escape(tok) + _E


def count_substring(text, tok):
    """**旧口径**：子串计数。保留它不是怀旧，是为了让两种口径**并列**。"""
    return text.count(tok)


def count_wordbound(text, tok):
    """**新口径**：词界计数（`pthread_create` 不再被 `x_pthread_create` 命中）。"""
    return len(re.findall(token_regex(tok), text))


def compare_calibers(text, tokens):
    """在**同一段**文本上并列报两种口径。

    返回 `{"substring": n, "wordbound": m, "delta": n-m, "per_token": {...}}`。
    `delta` 不是「误差」，它是**子串口径的假阳性**（前缀/后缀误收）。
    """
    per = {}
    sub = wb = 0
    for t in tokens:
        a = count_substring(text, t)
        b = count_wordbound(text, t)
        per[t] = {"substring": a, "wordbound": b}
        sub += a
        wb += b
    return {"substring": sub, "wordbound": wb, "delta": sub - wb, "per_token": per}


# ── 词干族（`unknown` 拆两桶的唯一事实源）────────────────────────────────
# 划分要求：任一词干**只能**属于一族。护栏 U8 断言两族不交 ——
# 若同一个词干同时出现在两族，`bucket_of` 的「同步族优先」会让结果依赖
# 遍历顺序，那是静默的取错（R82 §4m-3）。
ASYNC_STEMS = (
    "thread", "async", "task", "future", "promise", "await", "coroutine",
    "executor", "parfor", "parfeval", "callback", "worker", "spawn", "defer",
    "goroutine", "signal",
)
SYNC_STEMS = (
    "mutex", "semaphore", "spin_lock", "spinlock", "cond_var",
    "condition_variable", "rwlock", "critical_section", "lock",
)

BUCKET_ASYNC = "unknown_async"
BUCKET_SYNC = "sync_primitives"
HINT_BUCKETS = (BUCKET_ASYNC, BUCKET_SYNC)


def camel(stem):
    """`spin_lock` -> `SpinLock`；`condition_variable` -> `ConditionVariable`。"""
    return "".join(p[:1].upper() + p[1:] for p in stem.split("_") if p)


def stem_regex(stems):
    """一个词干族 -> 匹配器。

    两条分支，缺一不可（各自守一半的失败模式）：

      ① 全小写整词：**两侧**都要标识符边界
         ⇒ `threads` 不命中（右边是 `s`）、`__future__` 不命中（左边是 `_`）
      ② 驼峰：`CamelCase` 形态，**不要左边界**，只要求后面不是小写字母
         ⇒ `hThread` 命中、`foo_myThread` 命中（左边界会给它判死）、
            而 `Threads` 不命中（`Thread` 后面是 `s`）

    ② 为什么**不能**要左边界：驼峰词的左边**天然**是字母或 `_`
    （`myThread` 里 `Thread` 前面是 `y`）。要了左边界就会漏掉
    **所有**前缀型驼峰 —— 那是把口径修成另一个错。
    """
    if not stems:
        return re.compile(r"(?!x)x")          # 永不匹配（空族要有定义）
    lower = "|".join(sorted(stems, key=len, reverse=True))
    camelp = "|".join(sorted((camel(s) for s in stems), key=len, reverse=True))
    return re.compile(
        "(?:" + _B + "(?:" + lower + ")" + _E + ")"
        + "|"
        + "(?:" + "(?:" + camelp + ")" + r"(?=[A-Z_]|[^A-Za-z0-9_]|$))"
    )


def hint_regex():
    """**全部**词干的匹配器 —— `unknown` 候选的入口。"""
    return stem_regex(tuple(ASYNC_STEMS) + tuple(SYNC_STEMS))


def bucket_of(word, sync_re=None, async_re=None):
    """一个命中词落进哪一桶。**同步族优先** —— `pthread_mutex_lock` 同时含
    `mutex` 与 `lock`，它是**同步**原语，不是异步站点。都不命中 ⇒ None。"""
    sr = sync_re if sync_re is not None else stem_regex(SYNC_STEMS)
    ar = async_re if async_re is not None else stem_regex(ASYNC_STEMS)
    if sr.search(word):
        return BUCKET_SYNC
    if ar.search(word):
        return BUCKET_ASYNC
    return None


def split_hints(hits, sync_re=None, async_re=None):
    """把 `{词: 计数}` 拆成两桶。

    返回 `(buckets, unclassified)`：
      buckets       `{BUCKET_ASYNC: {...}, BUCKET_SYNC: {...}}`
      unclassified  落不进任何桶的词 —— **划分必须完备**，不许静默丢。
                    它是「分桶把数丢了」的唯一可见信号。
    """
    buckets = dict((b, {}) for b in HINT_BUCKETS)
    unclassified = []
    for w, n in hits.items():
        b = bucket_of(w, sync_re, async_re)
        if b is None:
            unclassified.append(w)
        else:
            buckets[b][w] = buckets[b].get(w, 0) + n
    return buckets, unclassified


def bucket_totals(buckets):
    """每桶总数（派生量）。两桶之和就是「未识别命中」的总量。"""
    return dict((b, sum(buckets.get(b, {}).values())) for b in HINT_BUCKETS)


def known_stems_by_lang(primitives):
    """已登记原语 -> 该语言下的**标识符段**集合。

    为什么不能拿「整 token 相等」判「已登记」：`std::thread` 登记在 cpp，
    而源码里出现的是裸 `thread` ⇒ 整 token 比较会把它**误报成缺口**
    （R82b 建议 7 的同一族：口径决定了会不会假报）。

    **按语言**比较：c 的表里没有裸 `thread`，所以 c 文件里的 `thread`
    仍然是 `unknown_async` —— 这是**诚实的**，不是漏。
    """
    out = {}
    for lang, rows in primitives.items():
        s = set()
        for tok, _o, _n in rows:
            s.add(tok)
            for p in namespace_parts(tok):
                s.add(p)
        out[lang] = s
    return out
