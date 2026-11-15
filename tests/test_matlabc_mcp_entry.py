# -*- coding: utf-8 -*-
"""`matlabc_mcp.py`（1942 行）：**工具表**的完整性。

MCP 的工具表就是"模型能看到什么"。它的三种失效都不报错：

* 某条缺 `handler` → `tools/call` 时崩，但 `tools/list` 一切正常（模型以为能用）；
* **重名** → `_BY_NAME = {t["name"]: t ...}` 会**静默去重**，后一个覆盖前一个，
  于是其中一个工具永远调不到，而列表里两个都"在"；
* `CORE_TOOLS`（`--tools core` 档位）里写了不存在的工具名 → 该档位静默少一个。

外加一条**文档与代码对账**：R865 发现注释和 `--help` 都写"核心 6 个"，
而 `CORE_TOOLS` 实际是 7 个 —— 手写数字只会安静地过期。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SRC = os.path.join(ROOT, "matlabc_mcp.py")


def test_every_tool_is_callable_and_described():
    """每条工具都要有 name/description/inputSchema/handler，且 handler 可调用。"""
    import matlabc_mcp as M

    assert len(M.TOOLS) >= 10, "工具表只有 %d 条（像被截断了）" % len(M.TOOLS)
    for t in M.TOOLS:
        for k in ("name", "description", "inputSchema", "handler"):
            assert k in t, "工具 %r 缺字段 %r" % (t.get("name"), k)
        assert callable(t["handler"]), "工具 %r 的 handler 不可调用" % (t["name"],)
        assert len((t.get("description") or "").strip()) >= 20, \
            "工具 %r 的描述太短（模型无法判断何时该调它）" % (t["name"],)


def test_tool_names_are_unique():
    """重名必须红 —— `_BY_NAME` 会静默去重，导致其中一个永远调不到。"""
    import matlabc_mcp as M

    names = [t["name"] for t in M.TOOLS]
    dup = sorted({n for n in names if names.count(n) > 1})
    assert not dup, "工具表里有重名（后一个会覆盖前一个）：%r" % dup


def test_core_tools_exist_in_table():
    """`--tools core` 档位里的名字必须都在工具表里，否则该档位静默少一个。"""
    import matlabc_mcp as M

    names = {t["name"] for t in M.TOOLS}
    missing = sorted(set(M.CORE_TOOLS) - names)
    assert not missing, "CORE_TOOLS 里有不存在的工具：%r" % missing
    assert len(M.CORE_TOOLS) >= 5, "core 档位只有 %d 个（太少）" % len(M.CORE_TOOLS)


def test_core_count_in_text_matches_code():
    """源码里写的「核心 N 个」必须等于 `len(CORE_TOOLS)`。

    这条守的是**文档与代码的对账**：R865 实测写成 6、实际 7。
    现在 `--help` 已改成由代码算，这条防止有人再手写一遍。
    """
    import matlabc_mcp as M

    src = io.open(SRC, encoding="utf-8", errors="replace").read()
    claims = [int(n) for n in re.findall(r"核心\s*(\d+)\s*个", src)]
    assert claims, "源码里找不到「核心 N 个」的说明（文案被删了？）"
    bad = [n for n in claims if n != len(M.CORE_TOOLS)]
    assert not bad, \
        "文案写 %r 个，实际 CORE_TOOLS 有 %d 个（改文案或改代码，别让它们各说各的）" % (
            bad, len(M.CORE_TOOLS))


def test_uri_and_rel_shapes():
    """`_uri` 给 `file:///` + 正斜杠；`_rel` 把仓库内路径变相对。"""
    import matlabc_mcp as M

    p = os.path.join(ROOT, "matlabc.py")
    uri = M._uri(p)
    assert uri.startswith("file:///"), "不是 file:/// URI：%r" % (uri,)
    assert "\\" not in uri, "URI 里有反斜杠（浏览器打不开）：%r" % (uri,)
    assert M._rel(p) == "matlabc.py", "_rel 没转成仓库相对路径：%r" % (M._rel(p),)
