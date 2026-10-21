# -*- coding: utf-8 -*-
"""MATLAB ↔ C 的**双侧适配器规则**（R432 / P0）。

问题：两边的函数名撞上了，不等于能对接 —— 参数个数、dtype、维度、
错误语义任何一处不一致，运行时才炸。本模块把「配对」变成一条可检查的规则：

    ADP-1  名字/参数个数一致（matlab:name/arity ⇄ c:symbol/arity）
    ADP-2  dtype/维度一致（matlab:double+shape ⇄ c:mlc_array）
    ADP-3  错误语义一致（matlab:MException ⇄ c:mlc_status 0/1/2）

两侧各生成一段**胶水**：
  * `matlab_adapter_source(spec)`：参数校验 + 转调原函数；
  * `c_adapter_source(spec)`：`mlc_array_require` + 转调算子/runtime。

默认姿态仍是「不可信」：只有 `match_specs()` 判为 matched 且 `verified_by`
非空的规则，才允许以「已支持」出现。
"""

#: 适配器规则（与 translate/rules.py 的语义规则并列，但单独成表：
#: 语义规则讲“怎么变”，适配器规则讲“怎么接”）。
ADAPTER_RULES = (
    {"id": "ADP-1",
     "from_": "matlab:name/arity", "to_": "c:symbol/arity",
     "note": "名字与参数个数必须精确一致；可变参数不进入自动配对",
     "verified_by": "tests/test_translate_port.py::test_adapter_match"},
    {"id": "ADP-2",
     "from_": "matlab:double+shape", "to_": "c:mlc_array",
     "note": "dtype 与 ndim 必须精确对应；形状在运行时校验",
     "verified_by": "tests/test_translate_port.py::test_adapter_emit"},
    {"id": "ADP-3",
     "from_": "matlab:MException", "to_": "c:mlc_status",
     "note": "错误一律映射到 0/1/2；不得用“返回值看起来对”掩盖失败",
     "verified_by": "tests/test_translate_port.py::test_adapter_errors"},
)

#: dtype 白名单（与 c_runtime/include/mlc.h 的 mlc_dtype 一一对应）。
DTYPES = ("f64", "f32", "i64", "i32", "u8", "bool")

#: 默认错误映射：MATLAB 侧的错误标识 → C 侧状态码。
DEFAULT_ERRORS = {
    "arity": "MLC_ERR",
    "dtype": "MLC_ERR",
    "shape": "MLC_ERR",
    "index": "MLC_ERR",
    "unimplemented": "MLC_UNIMPLEMENTED",
}


def adapter_rule_ids():
    """登记的全部适配器规则 ID（保持顺序、去重）。"""
    out = []
    for r in ADAPTER_RULES:
        if r["id"] not in out:
            out.append(r["id"])
    return tuple(out)


def verified_adapter_ids():
    """`verified_by` 非空的适配器规则（派生量，唯一口径）。"""
    return tuple(r["id"] for r in ADAPTER_RULES if r.get("verified_by"))


def normalise_spec(spec):
    """补齐默认值；缺 name/n_args 直接抛 ValueError（不许猜）。"""
    if not isinstance(spec, dict):
        raise ValueError("adapter spec 必须是 dict")
    name = spec.get("name")
    if not name:
        raise ValueError("adapter spec 缺 name")
    try:
        n_args = int(spec.get("n_args", 0))
    except (TypeError, ValueError):
        raise ValueError("adapter spec 的 n_args 必须是整数")
    dtype = spec.get("dtype", "f64")
    if dtype not in DTYPES:
        raise ValueError("未知 dtype: %r" % (dtype,))
    out = dict(spec)
    out["name"] = name
    out["n_args"] = n_args
    out["n_out"] = int(spec.get("n_out", 1))
    out["dtype"] = dtype
    out["in_rank"] = int(spec.get("in_rank", 1))
    out["out_rank"] = int(spec.get("out_rank", 1))
    out["matlab"] = spec.get("matlab", name)
    out["c"] = spec.get("c", "mlc_" + name)
    errors = dict(DEFAULT_ERRORS)
    errors.update(spec.get("errors") or {})
    out["errors"] = errors
    return out


def _signature_doc(spec):
    return "%s(%s) -> %s" % (spec["name"], ", ".join(
        ["in%d" % i for i in range(spec["n_args"])]), spec["dtype"])


def matlab_adapter_source(spec):
    """生成 MATLAB 侧胶水：参数/类型校验 + 转调原函数。"""
    s = normalise_spec(spec)
    lines = [
        "function varargout = %s_adapter(varargin)" % s["name"],
        "%% 由 translate.adapters 生成（ADP-1/2/3）；不要手改。",
        "if nargin ~= %d" % s["n_args"],
        "    error('matlabc:adapter:arity', "
        "'%s_adapter expects %d input(s), got %%d', nargin);"
        % (s["name"], s["n_args"]),
        "end",
    ]
    for i in range(s["n_args"]):
        lines.append("in%d = varargin{%d};" % (i + 1, i + 1))
        if s["dtype"] == "f64":
            lines.append(
                "if ~isa(in%d, 'double')" % (i + 1))
            lines.append(
                "    error('matlabc:adapter:dtype', "
                "'%s_adapter expects double');" % s["name"])
            lines.append("end")
    args = ", ".join("in%d" % (i + 1) for i in range(s["n_args"]))
    lines.append("[varargout{1:nargout}] = %s(%s);" % (s["matlab"], args))
    lines.append("end")
    return "\n".join(lines) + "\n"


def c_adapter_source(spec):
    """生成 C 侧胶水：`mlc_array_require` + 错误码返回。"""
    s = normalise_spec(spec)
    cname = s["c"]
    dtype = "MLC_" + s["dtype"].upper()
    lines = [
        "/* 由 translate.adapters 生成（ADP-1/2/3）；不要手改。 */",
        '/* signature: %s */' % _signature_doc(s),
        "mlc_status %s_adapter(const mlc_array *in, int32_t n_in," % cname,
        "                        mlc_array *out)",
        "{",
        "    mlc_status st;",
        "    if (in == NULL || out == NULL) {",
        "        return MLC_ERR;",
        "    }",
    ]
    if s["n_args"] != 1:
        lines += [
            "    if (n_in != %d) {" % s["n_args"],
            "        return MLC_ERR;",
            "    }",
        ]
    else:
        lines += [
            "    if (n_in != 1) {",
            "        return MLC_ERR;",
            "    }",
        ]
    if s["n_args"] > 1:
        lines += [
            "    for (int32_t i = 0; i < n_in; ++i) {",
            "        st = mlc_array_require(&in[i], %s, %d);"
            % (dtype, s["in_rank"]),
            "        if (st != MLC_OK) {",
            "            return st;",
            "        }",
            "    }",
            "    return %s(in, out);" % cname,
        ]
    else:
        lines += [
            "    st = mlc_array_require(&in[0], %s, %d);"
            % (dtype, s["in_rank"]),
            "    if (st != MLC_OK) {",
            "        return st;",
            "    }",
            "    return %s(&in[0], out);" % cname,
        ]
    lines += ["}"]
    return "\n".join(lines) + "\n"


def match_specs(matlab_specs, c_specs):
    """按 ADP-1/2/3 配对；返回 matched / 未配对 / 不匹配（含原因）。"""
    m = {}
    c = {}
    for raw in matlab_specs:
        s = normalise_spec(raw)
        m[s["name"]] = s
    for raw in c_specs:
        s = normalise_spec(raw)
        c[s["name"]] = s

    matched = []
    mismatched = []
    for name in sorted(set(m) & set(c)):
        a, b = m[name], c[name]
        reasons = []
        if a["n_args"] != b["n_args"]:
            reasons.append("ADP-1 arity %d != %d"
                           % (a["n_args"], b["n_args"]))
        if a["dtype"] != b["dtype"]:
            reasons.append("ADP-2 dtype %s != %s"
                           % (a["dtype"], b["dtype"]))
        if a["in_rank"] != b["in_rank"]:
            reasons.append("ADP-2 rank %d != %d"
                           % (a["in_rank"], b["in_rank"]))
        if reasons:
            mismatched.append({"name": name, "reasons": reasons})
        else:
            matched.append(name)
    return {
        "matched": matched,
        "unmatched_matlab": sorted(set(m) - set(c)),
        "unmatched_c": sorted(set(c) - set(m)),
        "mismatched": mismatched,
    }


def adapter_problems(specs):
    """纯函数：检查一组 spec 是否满足 ADP-1/2/3。空 = 干净。"""
    probs = []
    seen = {}
    for raw in specs:
        try:
            s = normalise_spec(raw)
        except ValueError as e:
            probs.append("ADP-1 非法 spec：%s" % e)
            continue
        name = s["name"]
        if name in seen:
            probs.append("ADP-1 重复的适配器：%s" % name)
        seen[name] = s
        if s["n_args"] < 0:
            probs.append("ADP-1 %s 的 n_args 为负" % name)
        if s["in_rank"] < 0 or s["out_rank"] < 0:
            probs.append("ADP-2 %s 的 rank 为负" % name)
        for key in ("arity", "dtype", "shape", "unimplemented"):
            if key not in s["errors"]:
                probs.append("ADP-3 %s 缺错误映射 %s" % (name, key))
    return probs
