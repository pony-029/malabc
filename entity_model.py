# -*- coding: utf-8 -*-
"""entity_model.py —— 语言无关的**实体（Entity）契约**。

为什么这个模块存在
==================
「C 与 Python 要达到 MATLAB 的效果」这条任务里，**实体层**是三家的共同根：
MATLAB 有 `classdef`（类 / 属性 / 方法 / 事件 / 枚举），C 有 struct / union /
enum / typedef / 全局变量，Python 有 class / 方法 / 字段。三家的**字段名各不相同**
（MATLAB 写 `superclass` / `superclasses`，C 没有，Python 写 `bases`）。如果让
各自的轮次自由命名，槽 25（Python `ast` 前端）与槽 26（C 实体层）会长出
**两套互不相认的模型**，`docs/PARITY_MATLAB_C_PY.md` 的 `entities` 一行也就永远
只有 MATLAB 一个 `yes`。

所以本模块**先立契约**：把「一个实体最少要说清什么」冻成常量，再给每个语言一个
**适配器**，把该语言的原生形态归一化到契约上。

契约（本模块即唯一事实源）
==========================
实体字段 `ENTITY_FIELDS`：`kind` / `name` / `file` / `line` / `members` / `bases`
成员字段 `MEMBER_FIELDS`：`name` / `kind` / `type` / `line`

- `kind` 只能取自 `ENTITY_KINDS`；成员 `kind` 只能取自 `MEMBER_KINDS`。
- **字段集必须完全一致**：多一个字段也算违约 —— 契约要的正是「三语言同形」，
  多出来的键就是三家开始分叉的地方。
- 未知信息写**约定哨兵**（`type=""`、`line=0`、无文件上下文 `file=""`），
  不许省略键、不许写 `None` ——「我没读到」要能跟「确实没有」分开。
- **空集天然合规**：某语言还没实体层时返回 `[]`，`conformance_problems([])` 为空；
  但那种语言在 `LANG_SUPPORT` 里**必须**是 `no` 且**必须**写出非空理由。

边界（本模块**不做**的事）
==========================
本模块自己**不 import 引擎**（`tests/test_entity_contract.py` 的 C5 用 AST
断言只许 import `sys`）：它是纯契约 + 适配器，接线由产品侧做。

⚠ R97 立契约时这里写着「本模块**不接线进 `matlabc.py` 的产物**」—— 那句话从
**R101 / 槽 25** 起**失效**：Python 适配器已经接上产物（`_run_ext_only` 的载荷
里有 `entities` 键，且逐项等于 `py_entities(payload["files"])`，守它的是
`tests/test_entity_contract.py` 的 **C6**）。**失效的散文比缺的散文危险** ——
留着它，下一个人会据此以为「改了适配器也不会动任何读数」。

C 侧仍未接线（`LANG_SUPPORT["c"]` 是 `no` 且写着理由，槽 26）；MATLAB 侧
一直有数据源，本轮起与 Python 由**同一份判据**核对。

用法
====
    import entity_model as em
    probs = em.conformance_problems(em.matlab_entities(payload["files"]))
    probs += em.support_problems()

命令行（用于自证，不依赖引擎）：
    python entity_model.py --selftest     # 两向自证；0=通过 1=有反例失败
    python entity_model.py --help         # 本帮助
"""
import sys

CONTRACT_VERSION = 1

# 语言分母：**只看这三家**（js 不在本契约的「三语言」内；它是 C/Py 的孪生前端，
# 何时并入由后续轮次裁决，不在本轮的假设里）。
LANGS = ("matlab", "c", "py")

# COMMON 实体种类：三语言都必须以同一 `kind` 名报出。
ENTITY_KINDS = ("class", "struct", "union", "enum", "typedef", "global")

# 成员种类。`property` 与 `field` 分开是刻意的：MATLAB 的 `properties` 块
# 与 C 的结构体字段、Python 的类属性在三家的语义并不相同，但**形状相同**，
# 契约管形状，语义由各自语言的判据负责。
MEMBER_KINDS = ("field", "property", "method", "event", "enumerator", "constant")

ENTITY_FIELDS = ("kind", "name", "file", "line", "members", "bases")
MEMBER_FIELDS = ("name", "kind", "type", "line")

# `no` 的理由下限（字符）。与 R96 的 E3「非 yes 必写理由」同源：空理由等于没登记。
_MIN_REASON = 8


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _is_str(x):
    return isinstance(x, str)


def blank_entity(kind, name, file="", line=0, members=None, bases=None):
    """造一个契约形状的实体（缺的字段一律走哨兵，不留 `None`）。"""
    return {"kind": kind, "name": name, "file": file, "line": line,
            "members": list(members or []), "bases": list(bases or [])}


def blank_member(name, kind, type="", line=0):
    """造一个契约形状的成员。"""
    return {"name": name, "kind": kind, "type": type, "line": line}


def member_problems(m, where=u"成员"):
    probs = []
    if not isinstance(m, dict):
        return [u"%s不是 dict，而是 %s" % (where, type(m).__name__)]
    missing = [k for k in MEMBER_FIELDS if k not in m]
    if missing:
        probs.append(u"%s缺字段 %s" % (where, missing))
    extra = sorted(set(m) - set(MEMBER_FIELDS))
    if extra:
        probs.append(u"%s有契约外字段 %s（同形契约要求字段集完全一致）" % (where, extra))
    if not _is_str(m.get("name")) or not m.get("name"):
        probs.append(u"%s的 `name` 必须是非空字符串，拿到 %r" % (where, m.get("name")))
    if m.get("kind") not in MEMBER_KINDS:
        probs.append(u"%s的 `kind`=%r 不在 %s"
                     % (where, m.get("kind"), list(MEMBER_KINDS)))
    if not _is_str(m.get("type")):
        probs.append(u"%s的 `type` 必须是字符串（未知写空串），拿到 %r"
                     % (where, m.get("type")))
    if not _is_int(m.get("line")) or m.get("line") < 0:
        probs.append(u"%s的 `line` 必须是非负整数（未知写 0），拿到 %r"
                     % (where, m.get("line")))
    return probs


def entity_problems(e, where=u"实体"):
    probs = []
    if not isinstance(e, dict):
        return [u"%s不是 dict，而是 %s" % (where, type(e).__name__)]
    missing = [k for k in ENTITY_FIELDS if k not in e]
    if missing:
        probs.append(u"%s缺字段 %s" % (where, missing))
    extra = sorted(set(e) - set(ENTITY_FIELDS))
    if extra:
        probs.append(u"%s有契约外字段 %s（同形契约要求字段集完全一致）" % (where, extra))
    tag = u"%s(%r)" % (where, e.get("name"))
    if e.get("kind") not in ENTITY_KINDS:
        probs.append(u"%s 的 `kind`=%r 不在 %s"
                     % (tag, e.get("kind"), list(ENTITY_KINDS)))
    if not _is_str(e.get("name")) or not e.get("name"):
        probs.append(u"%s 的 `name` 必须是非空字符串，拿到 %r" % (where, e.get("name")))
    if not _is_str(e.get("file")):
        probs.append(u"%s 的 `file` 必须是字符串（无文件上下文写空串），拿到 %r"
                     % (tag, e.get("file")))
    if not _is_int(e.get("line")) or e.get("line") < 0:
        probs.append(u"%s 的 `line` 必须是非负整数（未知写 0），拿到 %r"
                     % (tag, e.get("line")))
    members = e.get("members")
    if not isinstance(members, list):
        probs.append(u"%s 的 `members` 必须是 list，拿到 %s"
                     % (tag, type(members).__name__))
    else:
        for i, m in enumerate(members):
            probs.extend(member_problems(m, u"%s 的第 %d 个成员" % (tag, i)))
    bases = e.get("bases")
    if not isinstance(bases, list) or any(not _is_str(b) for b in bases):
        probs.append(u"%s 的 `bases` 必须是字符串 list，拿到 %r" % (tag, bases))
    return probs


def conformance_problems(entities):
    """逐实体查契约。**空集返回空列表**（还没实现该语言时的合法输入）。"""
    if not isinstance(entities, list):
        return [u"entities 必须是 list，拿到 %s" % type(entities).__name__]
    probs = []
    for i, e in enumerate(entities):
        probs.extend(entity_problems(e, u"第 %d 个实体" % i))
    return probs


# ---------------------------------------------------------------------------
# MATLAB 适配器：只**读**既有键，不改动它们。
# 真实形态（R97 实测，夹具 `classdef Shape < handle`）：
#   {"name": "Shape", "line": 2, "superclass": "handle",
#    "properties": ["Area", "Name"], "methods": ["Shape", "getArea"],
#    "events": ["Changed"], "enumerations": ["Circle"]}
# ⚠ `properties` / `methods` / `events` / `enumerations` 在这一层**只有名字**，
#   所以成员的 `type` / `line` 只能是哨兵 —— 不许臆造。
# ⚠ 只有单个 `superclass` 时没有 `superclasses` 键（两者都要认）。
# ---------------------------------------------------------------------------
_MATLAB_MEMBER_BLOCKS = (
    ("properties", "property"),
    ("methods", "method"),
    ("events", "event"),
    ("enumerations", "enumerator"),
)


def matlab_entities(files):
    """把 MATLAB 载荷的**每文件字典**归一化成契约实体。"""
    out = []
    for mf in files or []:
        if not isinstance(mf, dict):
            continue
        rel = mf.get("rel") or ""
        for cls in mf.get("classes") or []:
            if not isinstance(cls, dict):
                continue
            members = []
            for key, kind in _MATLAB_MEMBER_BLOCKS:
                for nm in cls.get(key) or []:
                    members.append(blank_member(u"%s" % nm, kind))
            bases = cls.get("superclasses")
            if not bases:
                single = cls.get("superclass")
                bases = [single] if single else []
            line = cls.get("line")
            out.append(blank_entity(
                "class", u"%s" % (cls.get("name") or ""), rel,
                line if _is_int(line) and line >= 0 else 0,
                members, [u"%s" % b for b in bases]))
        for g in mf.get("globals") or []:
            out.append(blank_entity("global", u"%s" % g, rel, 0))
    return out


# ---------------------------------------------------------------------------
# Python 适配器（R101 / 槽 25）：只**读** `pyast_frontend` 的原生形态，不改它。
# 真实形态（`pyast_frontend._class_page`，R101 实测）：
#   {"name": "K", "line": 4, "bases": ["object"],
#    "decorators": [...], "methods": ["__init__", "get"],
#    "attributes": [{"name": "x", "line": 5, "annotation": "int",
#                     "scope": "class"},
#                    {"name": "v", "line": 8, "annotation": "",
#                     "scope": "instance"}]}
# ⚠ `methods` 这一层**只有名字**（参数与行号在 `functions` 列表里），所以
#   `method` / `property` 成员的 `line` 只能是哨兵 0 —— 不许臆造。
# ⚠ 属性的 `line` 与 `annotation` 是**真读数**（`pyast_frontend` 给得出），
#   所以这两个字段**不**走哨兵 —— 契约允许真值，那就给真值。
# ⚠ 装饰器在文件级 `functions[]` 上（不在 `classes[]` 上），所以 `@property`
#   的判定要按**方法名**去 `functions` 里查它的 `decorators`。
# ---------------------------------------------------------------------------
def _is_property(decorators):
    """`@property` 一类：装饰器文本的**尾段**等于 `property`。

    尾段比较是为了同时认 `property` 与 `functools.cached_property` 之外那些
    写成 `x.property` 的形态；非字符串（词法页面读不到装饰器）一律返回 False，
    **不猜**。
    """
    for d in (decorators or []):
        if not _is_str(d):
            continue
        if d.split(".")[-1].strip() == "property":
            return True
    return False


def py_entities(files):
    """把 Python 载荷的**每文件字典**归一化成契约实体。

    读的是 `pyast_frontend` 的原生键（`classes` / `globals`）；页面缺这些键
    （例如 `ast` 拒收后降级到词法层的文件）时按空处理 —— 那正是
    `limitations` 要说清的事，不是本适配器的职责。
    """
    out = []
    for mf in files or []:
        if not isinstance(mf, dict):
            continue
        rel = mf.get("rel") or ""
        deco = {}
        for fn in (mf.get("functions") or []):
            if isinstance(fn, dict):
                deco[fn.get("name")] = fn.get("decorators")
        for cls in mf.get("classes") or []:
            if not isinstance(cls, dict):
                continue
            members = []
            for mname in (cls.get("methods") or []):
                members.append(blank_member(
                    u"%s" % mname,
                    "property" if _is_property(deco.get(mname)) else "method"))
            for a in (cls.get("attributes") or []):
                if not isinstance(a, dict):
                    continue
                ln = a.get("line")
                members.append(blank_member(
                    u"%s" % (a.get("name") or ""), "field",
                    u"%s" % (a.get("annotation") or ""),
                    ln if _is_int(ln) and ln >= 0 else 0))
            line = cls.get("line")
            out.append(blank_entity(
                "class", u"%s" % (cls.get("name") or ""), rel,
                line if _is_int(line) and line >= 0 else 0,
                members, [u"%s" % b for b in (cls.get("bases") or [])]))
        for g in mf.get("globals") or []:
            out.append(blank_entity("global", u"%s" % g, rel, 0))
    return out


# ---------------------------------------------------------------------------
# 两向登记表：`yes` 必须有可用适配器且**不留理由**；`no` 必须**没有**适配器
# 且写出理由。任一边越界都红 —— 与 R96 的 E2/E3 同一套纪律。
# ---------------------------------------------------------------------------
LANG_SUPPORT = {
    "matlab": {"status": "yes", "adapter": matlab_entities, "reason": ""},
    "c": {"status": "no", "adapter": None,
          "reason": u"C 实体层（struct/union/enum/typedef/全局变量）尚未实现"
                    u"（槽 26 c_entity_layer）"},
    "py": {"status": "yes", "adapter": py_entities, "reason": ""},
}


def support_problems(support=None):
    """两向查登记表（分母是 `LANGS`，不写死行数）。"""
    if support is None:
        support = LANG_SUPPORT
    probs = []
    for lang in LANGS:
        if lang not in support:
            probs.append(u"登记表缺语言 `%s`（分母是 %s）" % (lang, list(LANGS)))
            continue
        rec = support[lang]
        if not isinstance(rec, dict):
            probs.append(u"%s 的登记不是 dict" % lang)
            continue
        st = rec.get("status")
        if st not in ("yes", "no"):
            probs.append(u"%s 的 `status`=%r 只能是 yes / no" % (lang, st))
            continue
        ad = rec.get("adapter")
        reason = rec.get("reason") or ""
        if st == "yes":
            if not callable(ad):
                probs.append(u"%s 登记 yes 但没有可用适配器（yes 不许空转）" % lang)
            if reason:
                probs.append(u"%s 登记 yes 却留着理由 %r（陈旧理由，删掉）"
                             % (lang, reason))
        else:
            if ad is not None:
                probs.append(u"%s 登记 no 却带着适配器（no 不许偷偷实现）" % lang)
            if len(reason) < _MIN_REASON:
                probs.append(u"%s 登记 no 但理由只有 %d 个字符（下限 %d）"
                             % (lang, len(reason), _MIN_REASON))
    extra = sorted(set(support) - set(LANGS))
    if extra:
        probs.append(u"登记表有契约外语言 %s" % extra)
    return probs


# ---------------------------------------------------------------------------
# 自证：每个判据都要有**反例**（只跑正例等于没测）。
# ---------------------------------------------------------------------------
def _selftest():
    state = {"good": 0, "bad": 0, "fail": []}

    def expect(name, probs, want_red):
        ok = bool(probs) if want_red else (not probs)
        if ok:
            state["bad" if want_red else "good"] += 1
        else:
            state["fail"].append(name)

    good_e = blank_entity("class", "Shape", "Shape.m", 2,
                          [blank_member("Area", "property"),
                           blank_member("getArea", "method")], ["handle"])
    expect("clean entity", entity_problems(good_e), False)
    expect("empty set conforms", conformance_problems([]), False)
    expect("shipped table clean", support_problems(), False)

    no_bases = dict(good_e)
    del no_bases["bases"]
    expect("missing field", entity_problems(no_bases), True)

    extra = dict(good_e)
    extra["superclass"] = "handle"
    expect("extra field", entity_problems(extra), True)

    bad_kind = dict(good_e)
    bad_kind["kind"] = "banana"
    expect("bad entity kind", entity_problems(bad_kind), True)

    bad_member = dict(good_e)
    bad_member["members"] = [blank_member("x", "banana")]
    expect("bad member kind", entity_problems(bad_member), True)

    none_type = dict(good_e)
    none_type["members"] = [{"name": "x", "kind": "field", "type": None, "line": 0}]
    expect("None sentinel rejected", entity_problems(none_type), True)

    bad_bases = dict(good_e)
    bad_bases["bases"] = "handle"
    expect("bases must be list", entity_problems(bad_bases), True)

    expect("non-list rejected", conformance_problems(good_e), True)

    # 登记表反例
    s1 = {"matlab": {"status": "yes", "adapter": matlab_entities, "reason": ""},
          "c": {"status": "no", "adapter": None, "reason": u""},
          "py": {"status": "no", "adapter": None, "reason": u"x"}}
    expect("no with short reason", support_problems(s1), True)

    s2 = {"matlab": {"status": "yes", "adapter": None, "reason": ""},
          "c": {"status": "no", "adapter": None, "reason": u"理由足够长的说明文字"},
          "py": {"status": "no", "adapter": None, "reason": u"理由足够长的说明文字"}}
    expect("yes without adapter", support_problems(s2), True)

    s3 = {"matlab": {"status": "yes", "adapter": matlab_entities, "reason": u"陈旧说明"},
          "c": {"status": "no", "adapter": None, "reason": u"理由足够长的说明文字"},
          "py": {"status": "no", "adapter": None, "reason": u"理由足够长的说明文字"}}
    expect("stale reason on yes", support_problems(s3), True)

    s4 = {"matlab": {"status": "yes", "adapter": matlab_entities, "reason": ""},
          "c": {"status": "no", "adapter": matlab_entities, "reason": u"理由足够长"},
          "py": {"status": "no", "adapter": None, "reason": u"理由足够长的说明文字"}}
    expect("no carrying adapter", support_problems(s4), True)

    s5 = {"matlab": {"status": "yes", "adapter": matlab_entities, "reason": ""},
          "c": {"status": "no", "adapter": None, "reason": u"理由足够长的说明文字"},
          "py": {"status": "no", "adapter": None, "reason": u"理由足够长的说明文字"},
          "js": {"status": "no", "adapter": None, "reason": u"理由足够长的说明文字"}}
    expect("extra language", support_problems(s5), True)

    s6 = {"matlab": {"status": "yes", "adapter": matlab_entities, "reason": ""},
          "c": {"status": "no", "adapter": None, "reason": u"理由足够长的说明文字"}}
    expect("missing language", support_problems(s6), True)

    # 适配器：真实形态（单个 superclass）必须归一化
    fx = [{"rel": "Shape.m", "classes": [
        {"name": "Shape", "line": 2, "superclass": "handle",
         "properties": ["Area"], "methods": ["getArea"],
         "events": [], "enumerations": []}], "globals": ["gA"]}]
    ents = matlab_entities(fx)
    expect("matlab adapter conforms", conformance_problems(ents), False)
    expect("matlab adapter shape(1 class + 1 global)", None if len(ents) == 2 else ["n"], False)
    expect("matlab bases from single superclass", None if ents[0]["bases"] == ["handle"] else ["n"], False)
    expect("matlab member kinds", None if sorted(m["kind"] for m in ents[0]["members"])
           == ["method", "property"] else ["n"], False)

    # R101 / 槽 25：Python 适配器。装饰器在**文件级 functions[]** 上，
    # `@property` 的判定要按方法名回查它 —— 这里就把那个接线测出来。
    pyfx = [{"rel": "k.py",
             "functions": [{"name": "__init__", "decorators": []},
                           {"name": "get", "decorators": ["property"]}],
             "classes": [{"name": "K", "line": 4,
                          "bases": ["object"], "decorators": [],
                          "methods": ["__init__", "get"],
                          "attributes": [
                              {"name": "x", "line": 5,
                               "annotation": "int", "scope": "class"},
                              {"name": "v", "line": 8,
                               "annotation": "", "scope": "instance"}]}],
             "globals": ["CONST"]}]
    pents = py_entities(pyfx)
    expect("py adapter conforms", conformance_problems(pents), False)
    expect("py adapter shape(1 class + 1 global)",
           None if len(pents) == 2 else ["n"], False)
    expect("py bases from bases list",
           None if pents[0]["bases"] == ["object"] else ["n"], False)
    expect("py member kinds", None if sorted(
        (m["kind"], m["name"]) for m in pents[0]["members"])
        == [("field", "v"), ("field", "x"), ("method", "__init__"),
            ("property", "get")] else ["n"], False)
    # 属性是真读数：annotation 与 line 都必须**不**走哨兵
    expect("py member line/type are real", None if any(
        m["name"] == "x" and m["line"] == 5 and m["type"] == "int"
        for m in pents[0]["members"]) else ["n"], False)
    # method 只有名字 ⇒ line 必须是哨兵（不许臆造）
    expect("py method line is sentinel", None if all(
        m["line"] == 0 for m in pents[0]["members"]
        if m["kind"] in ("method", "property")) else ["n"], False)
    expect("py global entity",
           None if pents[1]["kind"] == "global" else ["n"], False)
    # 反例（容忍而非崩溃）：畸形成员被跳过，空集依然合规
    expect("py malformed tolerated", conformance_problems(py_entities(
        [{"rel": "z.py", "classes": [{"name": "Z", "line": 1,
                                          "attributes": [None],
                                          "methods": ["m"]}],
          "globals": []}])), False)
    # 非 dict 页面 / 非 dict 类也被跳过
    expect("py non-dict tolerated", conformance_problems(
        py_entities([None, 7, {"rel": "q.py", "classes": [3]}])), False)

    print("SELFTEST COUNTS {\"bad\": %d, \"good\": %d}"
          % (state["bad"], state["good"]))
    if state["fail"]:
        print("FAILED: %s" % ", ".join(state["fail"]))
        return 1
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--selftest" in argv:
        return _selftest()
    print("usage: python entity_model.py [--selftest | --help]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
