# -*- coding: utf-8 -*-
"""R97 / 槽 24：语言无关 **Entity 契约**的契约测试。

为什么另起一个文件而不塞进 test_matlabc.py
==========================================
本测试要**真跑一次引擎**（subprocess）再拿真产物喂契约适配器；它验的是
`entity_model.py` 这个新模块的对外承诺，与 `test_matlabc.py` 的
「单引擎行为」不是一回事。R97 起它独立成文件，后续槽 25 / 槽 26 接上
C / Python 适配器时**只改这里**。

判据（每条都要有对手方）
========================
  C1 契约常量自洽：字段集 / 种类集非空且无重复，`CONTRACT_VERSION` 是正整数。
  C2 MATLAB 适配器对**真产物**归一化后**完全合规**（`conformance_problems` 为空），
     且与引擎报告的类名 / 行号 / 基类 / 成员种类**逐项相等**。
  C3 **反例必须红**：缺字段 / 多字段 / 非法 kind / `None` 哨兵 一律报问题。
  C4 **空集天然合规**，但语言登记表**两向**：`yes` 要适配器且不留理由，
     `no` 要理由且不带适配器 —— 且这份表对全部 `LANGS` 给全，缺一个就红。
  C5 纯库不变式：`entity_model` **不得 import 引擎**（它是纯契约，不是分析器的一部分）
     ⇒ 这是本轮「**不改既有读数**」在模块层的可执行证据。
  C6 Python 适配器对**真产物**归一化后合规，且载荷里的 `entities` 键
     **逐项等于** `py_entities(payload["files"])`（`--json-level full`）；
     另核 `ast` 拒收时**降级必须可见**（`parser`=lexical + `limitations`
     非空 + `classes` 是空数组而不是缺键）。
  C7 C 适配器对**真产物**归一化后合规、与引擎读数逐项相等，且**注释里的类型
     定义不被误报**（分辨力）；登记表同步为 `yes`。
"""
import ast
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import entity_model as em  # noqa: E402

ANALYZER = os.path.join(ROOT, "matlabc.py")
CONTRACT_SRC = os.path.join(ROOT, "entity_model.py")

# 夹具：一个带 属性/方法/事件/枚举 + 单继承 的 classdef，外加一个 global。
FIXTURE_M = u"""% Shape base class
classdef Shape < handle
    properties
        Area
        Name
    end
    methods
        function obj = Shape(n)
            obj.Name = n;
        end
        function a = getArea(obj)
            a = obj.Area;
        end
    end
    events
        Changed
    end
    enumeration
        Circle, Square
    end
end
"""


def _run_matlab_fixture():
    """真跑一次引擎，返回载荷里的每文件字典列表。"""
    tmp = tempfile.mkdtemp(prefix="r97_ent_")
    src = os.path.join(tmp, "fx")
    os.mkdir(src)
    with open(os.path.join(src, "Shape.m"), "wb") as fh:
        fh.write(FIXTURE_M.replace("\n", "\r\n").encode("utf-8"))
    out = os.path.join(tmp, "out.json")
    proc = subprocess.run([sys.executable, ANALYZER, src, "--lang", "matlab",
                           "--checks", "all", "--json-level", "full",
                           "--json", out],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.returncode == 0, \
        "引擎跑夹具失败：rc=%s\n%s" % (proc.returncode,
                                   proc.stderr.decode("utf-8", "replace")[-800:])
    with open(out, "rb") as fh:
        payload = json.loads(fh.read().decode("utf-8"))
    return payload


# R106 / C7 夹具：一份**头文件**（类型定义都在这儿）+ 一份**引用它**的 .c。
# 最后一行是**反例**：注释里写一个类型定义 —— 它**不许**变成实体。
FIXTURE_C = u"""struct Pair { int a; int b; };
enum Color { RED, GREEN };
typedef struct Pair Pair;
/* struct Ghost { int x; }; */
"""

FIXTURE_C_USE = u"""#include "ent.h"
int main(void) { return 0; }
"""


def _run_c_fixture():
    """真跑一次引擎（`--lang c`），返回**整份载荷**。

    ⚠ 为什么连 `.c` 一起写：只放 `.h` 时 C 臂的文件集**可能**是空集，
    那时「载荷里没有实体」是恒真的假绿（R99 ④ 那一族）。两份文件都在，
    `include_edges` 也顺带被行使。
    """
    tmp = tempfile.mkdtemp(prefix="r106_entc_")
    src = os.path.join(tmp, "fx")
    os.mkdir(src)
    for name, text in (("ent.h", FIXTURE_C), ("use.c", FIXTURE_C_USE)):
        with open(os.path.join(src, name), "wb") as fh:
            fh.write(text.replace("\n", "\r\n").encode("utf-8"))
    out = os.path.join(tmp, "out.json")
    proc = subprocess.run([sys.executable, ANALYZER, src, "--lang", "c",
                           "--json-level", "full", "--json", out],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.returncode == 0, \
        "引擎跑 C 夹具失败：rc=%s\n%s" % (
            proc.returncode, proc.stderr.decode("utf-8", "replace")[-800:])
    with open(out, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def test_r97_contract_constants_selfconsistent():
    """C1：常量集非空、无重复；版本是正整数。"""
    assert isinstance(em.CONTRACT_VERSION, int) and em.CONTRACT_VERSION > 0
    for name in ("LANGS", "ENTITY_KINDS", "MEMBER_KINDS",
                 "ENTITY_FIELDS", "MEMBER_FIELDS"):
        seq = getattr(em, name)
        assert isinstance(seq, tuple) and seq, "%s 必须是非空 tuple" % name
        assert len(set(seq)) == len(seq), "%s 有重复项" % name
    assert set(em.LANGS) == set(em.LANG_SUPPORT), \
        "LANG_SUPPORT 的语言集必须与 LANGS 完全一致"


def test_r97_matlab_adapter_matches_real_payload():
    """C2：适配器对**真产物**归一化后合规，且与引擎读数逐项相等。"""
    payload = _run_matlab_fixture()
    files = payload.get("files")
    assert isinstance(files, list) and files, "载荷必须有 files"

    # 引擎原始读数（独立取，不经过适配器）
    raw_classes = [c for mf in files for c in (mf.get("classes") or [])]
    assert len(raw_classes) == 1, "夹具应恰好解析出 1 个类，实得 %d" % len(raw_classes)
    raw = raw_classes[0]

    ents = em.matlab_entities(files)
    probs = em.conformance_problems(ents)
    assert not probs, "MATLAB 适配器产物不合契约：\n  " + "\n  ".join(probs)

    cls_ents = [e for e in ents if e["kind"] == "class"]
    assert len(cls_ents) == 1, "应恰有 1 个 class 实体"
    ce = cls_ents[0]
    assert ce["name"] == raw["name"] == "Shape"
    assert ce["line"] == raw["line"]
    assert ce["file"] == files[0]["rel"]
    # 单 superclass 形态必须被认到（没有 `superclasses` 键）
    assert ce["bases"] == ["handle"], "基类应从单个 superclass 归一化，实得 %r" % ce["bases"]
    got = sorted((m["kind"], m["name"]) for m in ce["members"])
    want = sorted([("property", "Area"), ("property", "Name"),
                   ("method", "Shape"), ("method", "getArea"),
                   ("event", "Changed"), ("enumerator", "Circle")])
    assert got == want, "成员集不符：\n got = %r\n want = %r" % (got, want)
    # 未知信息走哨兵
    for m in ce["members"]:
        assert m["type"] == "" and m["line"] == 0, \
            "该层只有名字，type/line 必须是哨兵：%r" % m


def test_r106_c_adapter_matches_real_payload():
    """C7：C 适配器接**真产物** —— 合规、逐项等于引擎读数、**注释不误报**。

    R106 / 槽 26 把 C 从 `no` 改成 `yes`；这一条是那次改动的**对手方**：
    没有它，`LANG_SUPPORT["c"]` 的 `yes` 只被 `callable` 核过 ——
    而「它是函数」与「它真能归一化真产物」是两件事（本仓：宣称不是证据）。
    """
    payload = _run_c_fixture()
    files = payload.get("files")
    assert isinstance(files, list) and files, "载荷必须有 files"

    # ① 独立读数：引擎报了什么（不经过适配器）
    hdrs = [mf for mf in files if mf["rel"].endswith("ent.h")]
    assert len(hdrs) == 1, "应恰有 1 个 ent.h，实得 %r" % [m["rel"] for m in files]
    h = hdrs[0]
    assert [s["name"] for s in (h.get("structs") or [])] == ["Pair"], h.get("structs")
    assert [e["name"] for e in (h.get("enums") or [])] == ["Color"], h.get("enums")
    assert [t["name"] for t in (h.get("typedefs") or [])] == ["Pair"], h.get("typedefs")
    assert (h.get("unions") or []) == [], h.get("unions")

    # ② 契约：适配器对同一份 files 的输出必须合规
    ents = em.c_entities(files)
    probs = em.conformance_problems(ents)
    assert not probs, "C 适配器产物不合契约：\n  " + "\n  ".join(probs)

    # ③ 逐项核对（期望表独立于适配器的实现）
    kinds = sorted((e["kind"], e["name"]) for e in ents)
    assert kinds == [("enum", "Color"), ("struct", "Pair"),
                     ("typedef", "Pair")], kinds
    st = [e for e in ents if e["kind"] == "struct"][0]
    assert st["file"] == "ent.h" and st["line"] == 1, st
    assert [(m["kind"], m["name"], m["type"]) for m in st["members"]] == \
        [("field", "a", "int"), ("field", "b", "int")], st["members"]
    en = [e for e in ents if e["kind"] == "enum"][0]
    assert [m["name"] for m in en["members"]] == ["RED", "GREEN"], en["members"]
    assert all(m["kind"] == "enumerator" for m in en["members"]), en["members"]

    # ④ 分辨力：注释里的 `struct Ghost` **不许**变成实体
    assert "Ghost" not in [e["name"] for e in ents], \
        "注释里的类型定义被误报成实体：%r" % ents

    # ⑤ 登记表必须与实现同轮改（陈旧登记与幽灵登记同样红）
    assert em.LANG_SUPPORT["c"]["status"] == "yes", \
        "适配器接上产物后，登记表必须同时改成 yes"
    assert em.support_problems() == [], em.support_problems()


def test_r97_adapter_is_pure():
    """C2b：适配器不得就地改写输入（纯函数）。"""
    fx = [{"rel": "a.m", "classes": [{"name": "A", "line": 1, "superclass": "B",
                                      "properties": ["p"], "methods": [],
                                      "events": [], "enumerations": []}],
           "globals": []}]
    before = json.dumps(fx, sort_keys=True, ensure_ascii=False)
    ents = em.matlab_entities(fx)
    after = json.dumps(fx, sort_keys=True, ensure_ascii=False)
    assert before == after, "适配器改写了输入载荷"
    assert em.conformance_problems(ents) == []


def test_r97_negatives_must_go_red():
    """C3：反例必须红 —— 缺字段 / 多字段 / 非法 kind / None 哨兵。"""
    base = em.blank_entity("class", "A", "a.m", 1,
                           [em.blank_member("p", "property")], ["B"])
    assert em.entity_problems(base) == [], "基准样本本应合规"

    def red(mutate, why):
        e = json.loads(json.dumps(base))
        mutate(e)
        assert em.entity_problems(e), "反例未变红：%s" % why

    red(lambda e: e.pop("bases"), "缺字段")
    red(lambda e: e.update({"superclass": "B"}), "多字段")
    red(lambda e: e.update({"kind": "banana"}), "非法实体 kind")
    red(lambda e: e.update({"name": ""}), "空名")
    red(lambda e: e.update({"line": -1}), "负行号")
    red(lambda e: e.update({"members": [{"name": "x", "kind": "field",
                                         "type": None, "line": 0}]}), "None 哨兵")
    red(lambda e: e.update({"members": [em.blank_member("x", "banana")]}), "非法成员 kind")
    red(lambda e: e.update({"bases": "B"}), "bases 不是 list")


def test_r97_support_table_is_two_way():
    """C4：登记表两向 + 分母齐全 + 空集合规。"""
    assert em.support_problems() == [], \
        "出厂登记表必须自洽：%r" % (em.support_problems(),)
    assert em.conformance_problems([]) == [], "空集天然合规（还没实现该语言）"

    for lang in em.LANGS:
        rec = em.LANG_SUPPORT[lang]
        if rec["status"] == "yes":
            assert callable(rec["adapter"]), "%s=yes 必须有适配器" % lang
            assert not rec["reason"], "%s=yes 不许留理由" % lang
        else:
            assert rec["adapter"] is None, "%s=no 不许带适配器" % lang
            assert len(rec["reason"]) >= em._MIN_REASON, \
                "%s=no 的理由太短" % lang

    # 两向反例
    s = json.loads(json.dumps(
        {k: {"status": v["status"], "reason": v["reason"]}
         for k, v in em.LANG_SUPPORT.items()}))
    s["matlab"]["status"] = "no"
    s["matlab"]["reason"] = ""
    assert em.support_problems(s), "`no` 写空理由必须红（登记不许空转）"


def test_r97_entity_model_is_a_pure_library():
    """C5：模块不得 import 引擎 —— 「不改既有读数」在模块层的可执行证据。"""
    with open(CONTRACT_SRC, "rb") as fh:
        src = fh.read().decode("utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    assert imported <= {"sys"}, \
        "entity_model 必须是纯库（只许 sys），实得 %r" % sorted(imported)
    assert "matlabc" not in imported and "callrel" not in imported, \
        "契约模块不得反向依赖引擎"


# ---------------------------------------------------------------------------
# R101 / 槽 25：Python 适配器接上真产物
# ---------------------------------------------------------------------------
FIXTURE_PY = u'''"演示模块。"
import os

CONST = 1


class K(object):
    x = 5

    def __init__(self, v):
        self.v = v

    @property
    def get(self):
        return self.v


def helper(a):
    return a + 1
'''

# 语法上就跑不起来 ⇒ `ast` 拒收 ⇒ 必须**降级到词法层并把降级写出来**。
FIXTURE_PY_BROKEN = u"def broken(:\n    pass\n"


def _run_py_fixture(name, body):
    """真跑一次引擎（`--lang py --json-level full`），返回载荷。"""
    tmp = tempfile.mkdtemp(prefix="r101_ent_")
    src = os.path.join(tmp, "fx")
    os.mkdir(src)
    with open(os.path.join(src, name), "wb") as fh:
        fh.write(body.replace("\n", "\r\n").encode("utf-8"))
    out = os.path.join(tmp, "out.json")
    proc = subprocess.run([sys.executable, ANALYZER, src, "--lang", "py",
                           "--json-level", "full", "--json", out],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, \
        "引擎跑 py 夹具失败：rc=%s\n%s" % (
            proc.returncode, proc.stderr.decode("utf-8", "replace")[-800:])
    with open(out, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def test_r101_py_adapter_matches_real_payload():
    """C6：Python 适配器接真产物 —— 载荷 `entities` 逐项等于适配器输出。

    ⚠ 只在 `--json-level full` 下成立：`summary` 档把明细数组降级成
    `n_<键>` 计数，`classes` / `globals` 那时已经不在每文件字典里了。
    """
    payload = _run_py_fixture("k.py", FIXTURE_PY)
    files = payload["files"]

    # ① 独立读数：直接看引擎报了什么（不经过适配器）
    raw_classes = [c for mf in files for c in (mf.get("classes") or [])]
    assert len(raw_classes) == 1, "夹具应恰有 1 个类，实得 %d" % len(raw_classes)
    assert raw_classes[0]["name"] == "K"
    assert raw_classes[0]["line"] == 7, raw_classes[0]["line"]
    assert raw_classes[0]["bases"] == ["object"], raw_classes[0]["bases"]
    assert raw_classes[0]["methods"] == ["__init__", "get"], \
        raw_classes[0]["methods"]
    assert "CONST" in (files[0].get("globals") or []), files[0].get("globals")

    # ② 契约：载荷里的 entities **逐项等于**适配器对同一份 files 的输出
    assert "entities" in payload, \
        "Python 载荷必须带 entities 键（有通道、本次可能为空）"
    assert payload["entities"] == em.py_entities(files), \
        "载荷 entities 与 py_entities(files) 不一致 —— 实体层长了第二处事实源"
    assert em.conformance_problems(payload["entities"]) == []

    # ③ 逐项核对（期望表独立于适配器的实现）
    cls = [e for e in payload["entities"] if e["kind"] == "class"]
    gbl = [e for e in payload["entities"] if e["kind"] == "global"]
    assert len(cls) == 1 and len(gbl) == 1, payload["entities"]
    assert cls[0]["name"] == "K" and cls[0]["line"] == 7
    assert cls[0]["file"] == files[0]["rel"]
    assert cls[0]["bases"] == ["object"]
    got = [(m["kind"], m["name"], m["line"], m["type"])
           for m in cls[0]["members"]]
    want = [("method", "__init__", 0, ""),      # 只有名字 ⇒ 行号是哨兵
            ("property", "get", 0, ""),         # `@property` 按方法名回查到
            ("field", "x", 8, ""),              # 真行号，不许走哨兵
            ("field", "v", 11, "")]             # 实例属性（self.v）
    assert got == want, "成员不符：\n got = %r\n want = %r" % (got, want)
    assert gbl[0]["name"] == "CONST" and gbl[0]["line"] == 0
    assert em.LANG_SUPPORT["py"]["status"] == "yes", \
        "适配器接上产物后，登记表必须同时改成 yes"


def test_r101_py_degrade_is_written_into_limitations():
    """C6b：`ast` 拒收时**降级必须可见** —— parser=lexical + limitations 非空。

    「我没读到」与「确实没有」必须长得不一样：只静默降级的话，下游会把
    「词法读不出类」当成「这个文件没有类」。
    """
    payload = _run_py_fixture("bad.py", FIXTURE_PY_BROKEN)
    page = payload["files"][0]
    assert page.get("parser") == "lexical", page.get("parser")
    lims = page.get("limitations") or []
    assert lims and all(isinstance(s, str) and s.strip() for s in lims), lims
    assert page.get("classes") == [], \
        "降级页面的 classes 应是空数组（而不是缺键）"
