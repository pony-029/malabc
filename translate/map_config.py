# -*- coding: utf-8 -*-
"""**工程级映射配置**：MATLAB 文件 → C 文件的分组规则（可由 JSON 指定）。

## 为什么需要它

流水线默认**按源文件切**：一个 `.m` 对应一个 `.c`。但真实工程里这个关系是
可以任意组合的：

* 多个 `.m` 合成一个 `.c`（按模块归并，如 `@sdpvar/` 下的十几个文件）
* 一个 `.m` 拆成多个 `.c`（暂不支持，见下）

默认规则只是"最省事的那一种"，不是唯一正确的。所以这里把分组**外置成配置**，
一共三种来源：

| mode | 谁决定 | 适用 |
|---|---|---|
| `explicit` | 人写的 JSON（**已知映射**） | 重构过、约定明确的工程 |
| `ai` | `tools/map_suggest.py` 按语义分析产出 JSON，人再确认 | 陌生工程，先给建议 |
| `auto` | 不配置，退回默认（一文件一 `.c`） | 只想先跑通 |

## 配置格式

```json
{
  "version": 1,
  "mode": "explicit",
  "groups": [
    {"name": "numeric_core", "sources": ["scores.m", "pair.m"]},
    {"name": "misc",         "sources": ["solo.m"]}
  ],
  "unmatched": "own"
}
```

`name` 是**目标模块名**，产出的翻译单元是 `<name>_m.c`（与 Rust 侧
`c_file_stem()` 的命名保持一致：源名里的 `.` 换成 `_`）。

`unmatched`：没被任何 group 覆盖的源文件怎么办 ——
`own`（默认，各自成文件）/ `drop`（不产出，**但会计入报告**）。

## 实现方式

不改 C 生成器，而是**改写 MIR 里的 `# srcfile:` 标注** —— 生成器本来就按它
切翻译单元（`rust/m2c/src/project.rs` 的 `split` 分支）。这样：

* 分组逻辑只有一处（本文件），C 侧不需要知道"有配置"这件事
* MIR 是纯文本，分组结果可以直接 diff 审查
"""
import io
import json
import os

VERSION = 1
MODES = ("explicit", "ai", "auto")


class MapError(Exception):
    """配置本身不合法（不是"映射效果不好"，是"这份 JSON 用不了"）。"""


def load(path):
    """读并校验配置。返回规范化后的 dict。"""
    if not os.path.isfile(path):
        raise MapError("找不到映射配置：%s" % path)
    try:
        d = json.load(io.open(path, encoding="utf-8"))
    except ValueError as e:
        raise MapError("映射配置不是合法 JSON：%s" % e)
    return normalize(d)


def normalize(d):
    """校验 + 补默认值。字段少了给默认，字段错了直接报 —— 不猜。"""
    if not isinstance(d, dict):
        raise MapError("映射配置顶层必须是对象")
    ver = d.get("version", VERSION)
    if ver != VERSION:
        raise MapError("不支持的 version=%r（本工具只认 %d）" % (ver, VERSION))
    mode = d.get("mode", "explicit")
    if mode not in MODES:
        raise MapError("mode 只能是 %r，收到 %r" % (MODES, mode))
    groups = d.get("groups") or []
    if not isinstance(groups, list):
        raise MapError("groups 必须是数组")
    seen_src, seen_name, out = {}, set(), []
    for i, g in enumerate(groups):
        if not isinstance(g, dict):
            raise MapError("groups[%d] 必须是对象" % i)
        name = (g.get("name") or "").strip()
        srcs = g.get("sources") or []
        if not name:
            raise MapError("groups[%d] 缺 name" % i)
        if "/" in name or "\\" in name:
            raise MapError("groups[%d].name 不能带路径分隔符：%r" % (i, name))
        if not srcs:
            raise MapError("groups[%d]（%s）的 sources 为空" % (i, name))
        if name in seen_name:
            # 同名两组会产出**同一个** .c 文件，后一组覆盖前一组 —— 静默丢函数
            raise MapError("groups 里有重名 name：%r（会互相覆盖）" % name)
        seen_name.add(name)
        for s in srcs:
            key = os.path.basename(str(s))
            if key in seen_src:
                # 一个源文件属于两组：它只会进其中一个，另一个少函数
                raise MapError("源文件 %r 同时出现在 %r 与 %r 组"
                               % (key, seen_src[key], name))
            seen_src[key] = name
        out.append({"name": name, "sources": [os.path.basename(str(s))
                                              for s in srcs]})
    unmatched = d.get("unmatched", "own")
    if unmatched not in ("own", "drop"):
        raise MapError("unmatched 只能是 'own' / 'drop'，收到 %r" % (unmatched,))
    return {"version": VERSION, "mode": mode, "groups": out,
            "unmatched": unmatched}


def _split_blocks(text):
    """把 MIR 切成 (函数块全文) 列表 —— 以 `func:` 行起、`end` 行止。

    只做**结构性**切分，不解析语义：本模块的任务是改标注，不是理解程序。
    """
    blocks, cur, pre = [], [], []
    for ln in text.splitlines(True):
        if ln.startswith("func:"):
            if cur:
                blocks.append("".join(cur))
            cur = [ln]
        elif cur:
            cur.append(ln)
        else:
            # **第一个 `func:` 之前的内容是 MIR 头**（`version N`）——
            # 丢掉它会让整份 MIR 变成"缺少 version 行"（R919 实测）。
            pre.append(ln)
    # ⚠ **只在 `func:` 处切**。不能见 `end` 就收 —— MIR 里 `if`/`for`/`while`
    # 也用 `end` 收尾，按 `end` 切会把一个函数切成几段（R919 实测：
    # 生成物报「func 未以 end 收束」，因为后半段被当成了独立块）。
    if cur:
        blocks.append("".join(cur))
    return "".join(pre), blocks


def _srcfile_of(block):
    for ln in block.splitlines():
        if ln.startswith("# srcfile:"):
            return ln[len("# srcfile:"):].strip()
    return ""


def _retag(block, new_src):
    """把块里的 `# srcfile:` 换成 new_src（没有就补一条）。"""
    out, done = [], False
    for ln in block.splitlines(True):
        if ln.startswith("# srcfile:"):
            if not done:
                out.append("# srcfile:%s\n" % new_src)
                done = True
            continue
        if ln.rstrip() == "end" and not done:
            out.append("# srcfile:%s\n" % new_src)
            done = True
        out.append(ln)
    return "".join(out)


def apply_to_mir(text, spec):
    """按分组改写 MIR 的 `# srcfile:`。返回 (新文本, 报告)。

    报告字段：`groups`（每组收到的源文件与实际函数数）、`unmatched`（各自成文件
    的源文件名）、`dropped`（被丢弃的函数数）。
    """
    by_src = {}
    for g in spec["groups"]:
        for s in g["sources"]:
            by_src[s] = g["name"]

    out, report = [], {"groups": {}, "unmatched": [], "dropped": 0,
                       "functions": 0}
    for g in spec["groups"]:
        report["groups"][g["name"]] = {"sources": list(g["sources"]),
                                       "functions": 0}

    drop = spec.get("unmatched") == "drop"
    drop_only_if_grouped = drop and bool(spec["groups"])

    pre, blocks = _split_blocks(text)
    out.append(pre)          # MIR 头（`version N`）必须原样保留
    for block in blocks:
        src = os.path.basename(_srcfile_of(block))
        target = by_src.get(src)
        if target:
            out.append(_retag(block, target))
            report["groups"][target]["functions"] += 1
            report["functions"] += 1
        elif drop_only_if_grouped:
            # 没被任何组覆盖：`unmatched=drop` 时不产出，但要**计数**，
            # 否则"函数变少了"这件事在报告里看不见。
            report["dropped"] += 1
            report["functions"] += 1
        else:
            out.append(block)
            if src and src not in report["unmatched"]:
                report["unmatched"].append(src)
            report["functions"] += 1
    return "".join(out), report


def load_and_apply(mir_path, spec_path):
    """就地改写 MIR 文件（`run_build` 在 mir.py 之后、m2c 之前调用它）。"""
    spec = load(spec_path)
    text = io.open(mir_path, encoding="utf-8").read()
    new, report = apply_to_mir(text, spec)
    io.open(mir_path, "w", encoding="utf-8", newline="").write(new)
    return spec, report
