# -*- coding: utf-8 -*-
"""五语言**并发原语表** —— R82/T1（异步调用链）的单一事实源骨架（R82-0-4）。

R82 白帽实测（§2.2）：今天全仓 `pthread` / `coroutine` / `parfeval` / `mexFunction`
命中 **0**，`async` 仅 9 处且**全是关键字跳过** ⇒ **一条异步边都没有**。
T1 要补的正是这个。本模块先立**表**，不立识别器 —— 识别（新词法）是 Phase A。

一图看懂（表里最关键的一条区分）：

    原语              结局          为什么
    ─────────────────────────────────────────────────────────────
    parfeval          async         发起 → 边向**回调**去
    pthread_create    async         发起 → 边向**线程函数**去
    asyncio.create_task  async       发起 → 边向**协程**去
    ─────────────────────────────────────────────────────────────
    await             join          **不是** async！它是**汇合**：
                                    它等一个已经存在的任务，本身不发起新的
                                    并行工作 ⇒ 若把它记成 async 边，
                                    「谁先谁后」的结论会**整体反向**
    pthread_join      join          同上
    .then(...)        callback      注册回调：边是 **callback**，不是 async
    ─────────────────────────────────────────────────────────────

所以本表把每种原语映射到**四种结局之一**：`async` / `join` / `callback` / `unknown`。
`join` 与 `callback` **不产出 async 边** —— 这条区分由护栏
`tools/check_unified_graph.py` 的 U2b 钉住（把 `await` 挪进 async ⇒ 红）。

**Phase 0 的性质**：只提供表与判据；`AsyncSite` 的**提取**在 Phase A 落地，
届时 `unified_graph` 的 `sites["async"]` / `sites["unknown"]` 才第一次非零。
"""

# 结局常量（与 unified_graph.SITE_OUTCOMES 对齐的那几个子集）
OUTCOME_ASYNC = "async"
OUTCOME_JOIN = "join"          # 汇合：**不**产出 async 边
OUTCOME_CALLBACK = "callback"  # 注册回调：产出 callback 边
OUTCOME_UNKNOWN = "unknown"    # 表里没有 ⇒ 诚实记 unknown，不猜

VALID_OUTCOMES = (OUTCOME_ASYNC, OUTCOME_JOIN, OUTCOME_CALLBACK, OUTCOME_UNKNOWN)

# 语言 -> ((原语 token, 结局, 备注), ...)
# token 一律用「源码里真的会出现的写法」；大小写敏感由各语言后端在 Phase A 处理。
PRIMITIVES = {
    "c": (
        ("pthread_create", OUTCOME_ASYNC, "发起线程；边指向第 3 个实参（线程函数）"),
        ("fork", OUTCOME_ASYNC, "发起进程；边指向 fork 之后的子进程入口"),
        ("pthread_join", OUTCOME_JOIN, "汇合：等待已在运行的线程，本身不发起"),
        ("signal", OUTCOME_CALLBACK, "注册信号处理器 ⇒ callback 边"),
    ),
    "cpp": (
        ("std::thread", OUTCOME_ASYNC, "构造即发起"),
        ("std::async", OUTCOME_ASYNC, "发起异步任务"),
        ("std::future", OUTCOME_JOIN, ".get() 是汇合点；future 本身不代表并发"),
        ("std::condition_variable", OUTCOME_CALLBACK, "通知/等待对 ⇒ callback 边"),
    ),
    "py": (
        ("asyncio.create_task", OUTCOME_ASYNC, "发起协程"),
        ("asyncio.ensure_future", OUTCOME_ASYNC, "发起协程（旧写法）"),
        ("await", OUTCOME_JOIN, "**汇合**，不是发起 —— 归到这里是关键区分"),
        ("loop.call_later", OUTCOME_CALLBACK, "定时回调"),
    ),
    "js": (
        ("new Promise", OUTCOME_ASYNC, "新建异步上下文"),
        (".then(", OUTCOME_CALLBACK, "注册回调 ⇒ callback 边"),
        ("addEventListener", OUTCOME_CALLBACK, "事件注册 ⇒ callback 边"),
        ("setTimeout", OUTCOME_CALLBACK, "定时回调"),
    ),
    "matlab": (
        ("parfeval", OUTCOME_ASYNC, "发起并行求值；结果走 Future/afterEach"),
        ("parfor", OUTCOME_ASYNC, "并行循环体"),
        ("batch", OUTCOME_ASYNC, "提交批处理作业"),
        ("timer", OUTCOME_CALLBACK, "定时器回调"),
    ),
}

# 语言清单（护栏 U2b 要求恰好这五种都有非空表）
LANGUAGES = ("c", "cpp", "py", "js", "matlab")


def lookup(lang, token):
    """返回该语言下 `token` 的结局，没有则 OUTCOME_UNKNOWN（**不猜**）。"""
    for tok, outcome, _note in PRIMITIVES.get(lang, ()):
        if tok == token:
            return outcome
    return OUTCOME_UNKNOWN


def async_tokens(lang=None):
    """产出 async 边的原语 token。`lang=None` 表示全部语言。"""
    out = []
    langs = [lang] if lang else list(PRIMITIVES)
    for lg in langs:
        for tok, outcome, _n in PRIMITIVES.get(lg, ()):
            if outcome == OUTCOME_ASYNC:
                out.append((lg, tok))
    return out


def join_tokens(lang=None):
    """**汇合**原语 —— 它们必须**不**产出 async 边（U2b 的反向前提）。"""
    out = []
    langs = [lang] if lang else list(PRIMITIVES)
    for lg in langs:
        for tok, outcome, _n in PRIMITIVES.get(lg, ()):
            if outcome == OUTCOME_JOIN:
                out.append((lg, tok))
    return out


def census():
    """语言 -> 原语条数（**派生量**）。另附结局直方图。"""
    per_lang = dict((lg, len(PRIMITIVES.get(lg, ()))) for lg in PRIMITIVES)
    by_outcome = {}
    for lg in PRIMITIVES:
        for _tok, outcome, _n in PRIMITIVES[lg]:
            by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
    return {"per_lang": per_lang, "by_outcome": by_outcome}


class AsyncSite(object):
    """一个并发/回调**候选站点**（Phase A 才由各语言后端产出）。

    字段刻意与 `unified_graph.SITE_OUTCOMES` 对齐：`outcome` 就是站点要记进
    哪个桶。Phase 0 不做提取，只定义形状，让 Phase A 不必临时改数据结构。
    """
    __slots__ = ("lang", "token", "file", "line", "callee", "outcome", "evidence")

    def __init__(self, lang, token, file_, line, callee, outcome, evidence=""):
        if outcome not in VALID_OUTCOMES:
            raise ValueError("未登记的并发结局 %r（允许 %s）"
                             % (outcome, list(VALID_OUTCOMES)))
        self.lang = lang
        self.token = token
        self.file = file_
        self.line = line
        self.callee = callee
        self.outcome = outcome
        self.evidence = evidence

    def to_dict(self):
        return {"lang": self.lang, "token": self.token, "file": self.file,
                "line": self.line, "callee": self.callee,
                "outcome": self.outcome, "evidence": self.evidence}
