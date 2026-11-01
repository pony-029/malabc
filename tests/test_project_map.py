# -*- coding: utf-8 -*-
"""**MATLAB 工程 ↔ C 工程** 映射配置的判据。

锁住三条硬规则（`translate/project_map.py` 的文档头）：
1. 未知配置项必须报错 —— 拼错的键被静默忽略是最难查的一类问题；
2. `mapping` 的键必须是 `matlab.root` 下的真实路径；
3. 两个 MATLAB 源不能映射到同一个 C 输出。
另外验证：目录级映射、exclude、真实示例工程能展开。
"""
import io
import json
import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import project_map as PM  # noqa: E402


def _write(d, name, obj):
    p = os.path.join(d, name)
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False))
    return p


def _cfg(**over):
    d = {"version": 1,
         "matlab": {"root": "m", "recursive": True, "exclude": []},
         "c": {"root": "g", "project": "p", "prefix": "m2c_", "runtime": "rt"},
         "mapping": {},
         "defaults": {"shape": 4, "dtype": "f64", "max_seconds": 120}}
    for k, v in over.items():
        d[k] = v
    return d


def test_unknown_key_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        p = _write(d, "a.json", _cfg(mapping_typo={}))
        with pytest.raises(PM.ConfigError):
            PM.load(p)


def test_missing_version_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        c = _cfg()
        del c["version"]
        p = _write(d, "a.json", c)
        with pytest.raises(PM.ConfigError):
            PM.load(p)


def test_dir_mapping_and_extension():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m", "sub"))
        for n in ("a.m", "sub/b.m"):
            io.open(os.path.join(d, "m", n), "w").write(u"function y = f(x)\n")
        p = _write(d, "a.json", _cfg(mapping={"m": "g/src"}))
        res = PM.plan(PM.load(p), d)
        got = {e["matlab"].replace("\\", "/"): e["c"] for e in res["entries"]}
        assert got["m/a.m"] == "g/src/a.c"
        assert got["m/sub/b.m"] == "g/src/sub/b.c"
        assert not res["problems"]


def test_two_sources_same_output_is_a_problem():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m", "x"))
        os.makedirs(os.path.join(d, "m", "y"))
        for n in ("x/f.m", "y/f.m"):
            io.open(os.path.join(d, "m", n), "w").write(u"function y = f(x)\n")
        # 两个目录都映射到同一个 C 目录 -> f.c 冲突
        p = _write(d, "a.json", _cfg(mapping={"m/x": "g/one",
                                              "m/y": "g/two"}))
        res = PM.plan(PM.load(p), d)
        # 换个真正会撞的配置：两个目录映射到同一输出目录
        p2 = _write(d, "b.json", _cfg(mapping={"m/x": "g/same",
                                               "m/y": "g/same"}))
        res2 = PM.plan(PM.load(p2), d)
        assert not res["problems"]
        assert any("同一 C 输出" in x for x in res2["problems"]), res2["problems"]


def test_mapping_key_outside_root_is_a_problem():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = f(x)\n")
        p = _write(d, "a.json", _cfg(mapping={"elsewhere": "g"}))
        res = PM.plan(PM.load(p), d)
        assert any("不在 matlab.root" in x for x in res["problems"])


def test_exclude_pattern():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m", "test"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = f(x)\n")
        io.open(os.path.join(d, "m", "test", "b.m"), "w").write(u"function y = f(x)\n")
        c = _cfg()
        c["matlab"]["exclude"] = ["**/test/**"]
        p = _write(d, "a.json", c)
        res = PM.plan(PM.load(p), d)
        names = [e["matlab"].replace("\\", "/") for e in res["entries"]]
        assert "m/a.m" in names
        assert not [n for n in names if "/test/" in n], names


def test_real_example_config_expands():
    """真实示例：`translate/examples/m2c.project.json` 必须能展开整个语料目录。"""
    p = os.path.join(ROOT, "translate", "examples", "m2c.project.json")
    if not os.path.isfile(p):
        pytest.skip("示例配置不存在")
    cfg = PM.load(p)
    res = PM.plan(cfg, os.path.dirname(os.path.abspath(p)))
    assert not res["problems"], res["problems"]
    assert len(res["entries"]) >= 40, len(res["entries"])
    assert all(e["c"].endswith(".c") for e in res["entries"])
