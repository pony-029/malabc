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


def test_single_project_config_file():
    """**只允许一个** `m2c.project.json`：不许出现 `m2c.project.v2.json` 这类后缀。

    配置版本靠文件里的 `version` 字段区分，不靠文件名 ——
    多个文件名会让"当前生效的是哪一份"变成猜谜。
    """
    ex = os.path.join(ROOT, "translate", "examples")
    files = [f for f in os.listdir(ex) if f.startswith("m2c.project")]
    assert files == ["m2c.project.json"], files


def test_real_example_config_expands():
    """真实示例：`translate/examples/m2c.project.json` 必须是 v2 且校验通过。"""
    p = os.path.join(ROOT, "translate", "examples", "m2c.project.json")
    cfg = PM.load2(p)
    assert cfg["version"] == 2
    base = os.path.dirname(os.path.abspath(p))
    facts, err = PM.scan_facts(base, cfg)
    if err:
        pytest.skip(err)
    res = PM.check_v2(cfg, base, facts["ops"], facts["shapes"],
                      facts["recursive"], facts["op_counts"], facts["dtypes"])
    assert not res["problems"], res["problems"]
    assert facts["ops"], "应当扫出算子"


def test_ds1_unknown_dtype_rejected():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = a(x)\n")
        bad = _v2()
        bad["dtypes"] = {"default": "half_pumpkin"}
        p = _write(d, "c.json", bad)
        with pytest.raises(PM.ConfigError):
            PM.load2(p)


def test_ds2_fixed_point_bounds():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = a(x)\n")
        bad = _v2()
        bad["dtypes"] = {"default": "q15",
                         "fixed_point": {"format": "Q15", "frac_bits": 16}}
        p = _write(d, "c.json", bad)
        with pytest.raises(PM.ConfigError):
            PM.load2(p)
        bad["dtypes"]["fixed_point"] = {"format": "Q15", "frac_bits": 15,
                                        "overflow": "explode"}
        p2 = _write(d, "c2.json", bad)
        with pytest.raises(PM.ConfigError):
            PM.load2(p2)


def test_ds4_default_dtype_vs_source():
    """动静对账：默认 dtype 与源码实测不同，且未声明转换 -> 报错。"""
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = a(x)\n")
        cfg = _v2()
        cfg["dtypes"] = {"default": "f32"}
        res = PM.check_v2(cfg, d, src_dtypes={"x": "f64"})
        assert any("DS4" in x for x in res["problems"]), res["problems"]
        # 声明了定标 -> 降级为 warning
        cfg["dtypes"]["fixed_point"] = {"format": "Q15", "frac_bits": 15}
        res2 = PM.check_v2(cfg, d, src_dtypes={"x": "f64"})
        assert not any("DS4" in x for x in res2["problems"]), res2["problems"]
        assert any("DS4" in x for x in res2["warnings"]), res2["warnings"]



# ---------------------------------------------------------------------------
# v2：工程级关系模型（多对多 + 算子替换 + 嵌入式时序 + 动静对账）
# ---------------------------------------------------------------------------

def _v2(**over):
    d = {"version": 2,
         "matlab": {"root": "m", "recursive": True, "exclude": []},
         "c": {"root": "g", "project": "p", "prefix": "m2c_", "runtime": "rt"},
         "targets": {"pc": {"abi": "host", "allow_heap": True, "dtype": "f64"},
                     "mcu": {"abi": "arm", "allow_heap": False, "dtype": "f32"}},
         "modules": [{"id": "mod", "targets": ["pc"], "sources": ["a"]}],
         "operators": {}, "constraints": {}}
    d.update(over)
    return d


def test_v2_load_accepts_and_rejects_unknown():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = a(x)\n")
        p = _write(d, "v2.json", _v2())
        assert PM.load2(p)["version"] == 2
        bad = _v2()
        bad["modules"][0]["typo_key"] = 1
        p2 = _write(d, "bad.json", bad)
        with pytest.raises(PM.ConfigError):
            PM.load2(p2)


def test_v2_sources_must_be_non_empty():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = a(x)\n")
        p = _write(d, "v2.json", _v2(modules=[{"id": "mod", "sources": []}]))
        with pytest.raises(PM.ConfigError):
            PM.load2(p)


def test_v2_m4_same_function_in_two_modules():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        for n in ("a", "b"):
            io.open(os.path.join(d, "m", n + ".m"), "w").write(u"function y = f(x)\n")
        mods = [{"id": "m1", "sources": ["a"]}, {"id": "m2", "sources": ["a"]}]
        res = PM.check_v2(_v2(modules=mods), d, used_ops=None)
        assert any("M4" in x for x in res["problems"]), res["problems"]
        # 声明 shared 后不再报
        mods = [{"id": "m1", "sources": ["shared:a"]},
                {"id": "m2", "sources": ["shared:a"]}]
        res2 = PM.check_v2(_v2(modules=mods), d, used_ops=None)
        assert not any("M4" in x for x in res2["problems"]), res2["problems"]


def test_v2_m1_missing_source():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = a(x)\n")
        mods = [{"id": "m1", "sources": ["does_not_exist"]}]
        res = PM.check_v2(_v2(modules=mods), d, used_ops=None)
        assert any("M1" in x for x in res["problems"]), res["problems"]


def test_v2_t1_deadline_after_period():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = a(x)\n")
        mods = [{"id": "m1", "targets": ["pc"], "sources": ["a"],
                 "timing": {"period_ms": 1, "deadline_ms": 2}}]
        res = PM.check_v2(_v2(modules=mods), d, used_ops=None)
        assert any("T1" in x for x in res["problems"]), res["problems"]


def test_v2_t2_isr_needs_no_heap_target():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = a(x)\n")
        mods = [{"id": "m1", "targets": ["pc"], "sources": ["a"],
                 "timing": {"entry_kind": "isr"}}]
        res = PM.check_v2(_v2(modules=mods), d, used_ops=None)
        assert any("T2" in x for x in res["problems"]), res["problems"]
        mods[0]["targets"] = ["mcu"]        # mcu 禁止堆分配
        res2 = PM.check_v2(_v2(modules=mods), d, used_ops=None)
        assert not any("T2" in x for x in res2["problems"]), res2["problems"]


def test_v2_dynamic_operator_reconciliation():
    """动静结合：M2（配了没用）/ M3（用了没配）都要报。"""
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "m"))
        io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = a(x)\n")
        cfg = _v2(modules=[{"id": "m1", "sources": ["a"],
                            "operators": {"sum": "vendor_sum"}}])
        # 源码实际用到 OP-ADD，没用 OP-SUM
        res = PM.check_v2(cfg, d, used_ops={"OP-ADD", "OP-MAGIC"})
        assert any("M2" in x for x in res["warnings"]), res["warnings"]
        assert any("M3" in x for x in res["problems"]), res["problems"]


def test_v2_manifest_contains_timing_and_sources():
    with tempfile.TemporaryDirectory() as d:
        mods = [{"id": "filt", "targets": ["mcu"], "sources": ["a", "b"],
                 "timing": {"period_ms": 1, "deadline_ms": 0.5,
                            "entry_kind": "isr"}}]
        cfg = _v2(modules=mods)
        out = os.path.join(d, "m2c_manifest.h")
        PM.emit_manifest(cfg, out, used_ops={"OP-ADD"})
        t = io.open(out, encoding="utf-8").read()
        assert 'M2C_FILT_SRC0 "a"' in t
        assert "M2C_FILT_PERIOD_MS 1" in t
        assert '"isr"' in t
        assert "M2C_USES_OP_ADD" in t


# ---------------------------------------------------------------------------
# v2 内存模型：嵌入式没有充足的堆，内存必须**声明式**
# ---------------------------------------------------------------------------

def _mem_cfg(mem, allow_heap=False, dtype="f32", extra=None):
    d = _v2()
    d["targets"]["mcu"] = {"abi": "arm", "allow_heap": allow_heap, "dtype": dtype,
                           "memory": mem}
    d["modules"] = [{"id": "m1", "targets": ["mcu"], "sources": ["a"]}]
    if extra:
        d.update(extra)
    return d


def _mk_src(d):
    os.makedirs(os.path.join(d, "m"), exist_ok=True)
    io.open(os.path.join(d, "m", "a.m"), "w").write(u"function y = a(x)\n")


def test_mm1_static_pool_needs_no_heap():
    with tempfile.TemporaryDirectory() as d:
        _mk_src(d)
        mem = {"strategy": "static_pool", "pool_bytes": 1024, "alignment": 8}
        bad = PM.check_v2(_mem_cfg(mem, allow_heap=True), d)
        assert any("MM1" in x for x in bad["problems"]), bad["problems"]
        ok = PM.check_v2(_mem_cfg(mem, allow_heap=False), d)
        assert not any("MM1" in x for x in ok["problems"]), ok["problems"]


def test_mm2_pool_must_align():
    with tempfile.TemporaryDirectory() as d:
        _mk_src(d)
        mem = {"strategy": "static_pool", "pool_bytes": 1001, "alignment": 8}
        res = PM.check_v2(_mem_cfg(mem), d)
        assert any("MM2" in x for x in res["problems"]), res["problems"]


def test_mm3_single_array_limit():
    with tempfile.TemporaryDirectory() as d:
        _mk_src(d)
        mem = {"strategy": "static_pool", "pool_bytes": 65536, "alignment": 8,
               "max_array_bytes": 128,
               "arrays": [{"name": "big", "elements": 1024, "dtype": "f32"}]}
        res = PM.check_v2(_mem_cfg(mem), d)
        assert any("MM3" in x for x in res["problems"]), res["problems"]


def test_mm4_pool_capacity():
    with tempfile.TemporaryDirectory() as d:
        _mk_src(d)
        mem = {"strategy": "static_pool", "pool_bytes": 64, "alignment": 8,
               "arrays": [{"name": "x", "elements": 100, "dtype": "f32"}]}
        res = PM.check_v2(_mem_cfg(mem), d)
        assert any("MM4" in x for x in res["problems"]), res["problems"]


def test_mm5_declared_vs_measured():
    """动静对账：声明的元素数必须与源码实测一致。"""
    with tempfile.TemporaryDirectory() as d:
        _mk_src(d)
        mem = {"strategy": "static_pool", "pool_bytes": 65536, "alignment": 8,
               "arrays": [{"name": "buf", "elements": 256, "dtype": "f32"}]}
        cfg = _mem_cfg(mem)
        ok = PM.check_v2(cfg, d, shape_hits={"buf": 256})
        assert not any("MM5" in x for x in ok["problems"]), ok["problems"]
        bad = PM.check_v2(cfg, d, shape_hits={"buf": 128})
        assert any("MM5" in x for x in bad["problems"]), bad["problems"]


def test_r1_no_recursion():
    with tempfile.TemporaryDirectory() as d:
        _mk_src(d)
        cfg = _mem_cfg({})
        cfg["constraints"] = {"no_recursion": True}
        res = PM.check_v2(cfg, d, recursive_fns={"a"})
        assert any("R1" in x for x in res["problems"]), res["problems"]
        res2 = PM.check_v2(cfg, d, recursive_fns=set())
        assert not any("R1" in x for x in res2["problems"]), res2["problems"]


def test_r2_ops_per_entry():
    with tempfile.TemporaryDirectory() as d:
        _mk_src(d)
        cfg = _mem_cfg({})
        cfg["modules"] = [{"id": "m1", "targets": ["mcu"], "sources": ["a"],
                           "entry": "a"}]
        cfg["constraints"] = {"max_ops_per_entry": 3}
        res = PM.check_v2(cfg, d, op_counts={"a": 9})
        assert any("R2" in x for x in res["problems"]), res["problems"]


def test_manifest_contains_memory():
    with tempfile.TemporaryDirectory() as d:
        mem = {"strategy": "static_pool", "pool_bytes": 4096, "alignment": 8,
               "arrays": [{"name": "buf", "elements": 64, "dtype": "f32"}]}
        cfg = _mem_cfg(mem)
        out = os.path.join(d, "m.h")
        PM.emit_manifest(cfg, out, used_ops={"OP-ADD"})
        t = io.open(out, encoding="utf-8").read()
        assert "M2C_MEM_STRATEGY" in t and "static_pool" in t
        assert "M2C_MEM_POOL_BYTES 4096" in t
        assert 'M2C_MEM_ARR0_NAME "buf"' in t
