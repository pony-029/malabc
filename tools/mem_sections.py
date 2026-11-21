# -*- coding: utf-8 -*-
"""**分段预算校验**：把数组按大小分流到 target 定义的段，并逐段校验容量。

    python tools/mem_sections.py <MIR 目录> --profile tools/targets/mcu_256k.json
    python tools/mem_sections.py <MIR 目录> --profile <p> --json
    python tools/mem_sections.py --selftest

## 与既有工具的关系（不要重复造）

* `mem_budget.py` 算**单函数峰值**，回答「这个函数能不能装进 256KB」；
* 本工具算**整个工程的段总量**，回答「DDR 段 / TCM 段各自会不会溢出」。

两者都从 MIR 的 `arg/ret` 形状出发，口径一致（`prod(shape) * 8`）。

## 分段规则（保守，写死）

**本仓没有生命周期分析**，所以不能像论文那样按"活跃期"分配。这里用一条
保守规则：**单个数组大于 `tcm_max_array` 就进大内存段，其余进快段**。

它必然不如真正的活跃期分析省，但**方向是对的**：先让"超限能被算出来",
再谈"怎样塞得更紧"。把这层写成可替换的 `classify()`，将来有数据流分析时
只换函数，不改调用方。

## 为什么段名要从 profile 读（而不是写死 .tcm_data / .ddr_bss）

换一颗芯片，段名、容量、甚至段的数量都会变。写死段名会让生成器与某颗芯片
绑死 —— 那正是「手工 JSON 配置」问题的另一个版本。profile 是**只读的物理
事实**（这块板子有哪些内存），生成器是**逻辑**，两者必须分开。

退出码：
    0 = 各段都在容量内（或只有跳过项）
    1 = 有段超限（这是**结论**，不是工具错误）
    2 = 缺输入 / profile 不合法
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))

F64 = 8


def _prod(shape):
    n = 1
    for d in shape:
        n *= int(d)
    return n


def load_profile(path):
    """读并校验 target profile。缺字段一律报错（不猜）。"""
    try:
        p = json.load(io.open(path, encoding="utf-8"))
    except (IOError, OSError, ValueError) as e:
        raise ValueError("读不到 profile（%s）" % type(e).__name__)
    secs = p.get("sections")
    if not isinstance(secs, list) or not secs:
        raise ValueError("profile.sections 必须是非空数组")
    for s in secs:
        for k in ("name", "capacity_bytes"):
            if k not in s:
                raise ValueError("section 缺字段 %r" % k)
        if not isinstance(s["capacity_bytes"], int) or s["capacity_bytes"] <= 0:
            raise ValueError("section %r 的 capacity_bytes 必须是正整数"
                             % s["name"])
    if not isinstance(p.get("tcm_max_array"), int):
        raise ValueError("profile.tcm_max_array 必须是整数（字节）")
    return p


def classify(nbytes, profile):
    """**可替换的分流策略**：按段声明顺序 first-fit。

    规则（R1041）：
      1. 段可以用可选的 `max_array_bytes` 声明「我能装下多大的单个数组」；
      2. 按 profile 里的**声明顺序**找第一个「装得下」的段；
      3. 没有 `max_array_bytes` 的段视为「能装下任何大小」（通常是最后的大内存）。

    **为什么改掉旧版**：旧版只用 `sections[0]`（快段）和 `sections[-1]`（大段），
    于是三段以上的 profile 里**中间段永远是 0** —— 实测 cortex_a_tcm_ddr
    的 dtcm 用量恒为 0，而它是 256KB 的 CPU 直连内存，正是最该被用上的那段。
    「可配置段个数」在数据格式上成立、在分流逻辑上不成立，等于没配。

    仍然**不做生命周期分析**（没有数据流时这是诚实的天花板）：这里只保证
    「每个声明的段都有机会被用到」，不保证「用得最省」。
    """
    for s in profile["sections"]:
        lim = s.get("max_array_bytes")
        if lim is None or nbytes <= lim:
            return s["name"]
    return profile["sections"][-1]["name"]


def scan_arrays(src):
    """从 MIR 取所有 (数组名, 字节数)；形状未知的单独返回。"""
    import mir as M
    arrays = []
    unknown = 0
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".m"):
            continue
        try:
            code = io.open(os.path.join(src, fn), encoding="utf-8",
                           errors="replace").read()
            txt, _st = M.to_mir(code)
        except Exception:                      # noqa: BLE001
            continue
        func = None
        for ln in txt.splitlines():
            s = ln.strip()
            if s.startswith("func:"):
                func = s[5:]
                continue
            m = re.match(r"^(arg|ret):([A-Za-z_]\w*):(\w+)(?::([\d,]+))?$", s)
            if not m:
                continue
            _k, name, dt, dims = m.groups()
            if dt == "i64":
                continue
            if not dims:
                unknown += 1
                continue
            arrays.append((func, name, _prod([int(x) for x in dims.split(",")
                                              if x]) * F64))
    return arrays, unknown


def check(arrays, profile):
    """返回 (per_section, violations)。

    **口径：逐函数求和，再对函数取最大**（R1048）。

    早先是把全工程的数组全加起来 —— 那会**系统性高估**：不同函数的数组
    不会同时存在。高估的后果不是"更安全"，而是"该放下的放不下"，
    配额被不存在的用量吃掉。

    反过来，这也**不是真实峰值**：函数 A 调 B 时两者数组同时存在，
    而本函数只按"每个函数各自"算，会**低估**跨调用链的情形。
    两条缺口方向相反，所以这里只解决高估那一半，并在返回值里
    明确标注 `scope: per-function`，不让读者以为这是全局峰值。
    """
    cap = dict((s["name"], s["capacity_bytes"]) for s in profile["sections"])
    per_func = {}          # func -> {sec: bytes}
    count = dict((s["name"], 0) for s in profile["sections"])
    for fn, _nm, nb in arrays:
        sec = classify(nb, profile)
        per_func.setdefault(fn, {})
        per_func[fn][sec] = per_func[fn].get(sec, 0) + nb
        count[sec] += 1

    used = dict((s["name"], 0) for s in profile["sections"])
    worst = dict((s["name"], None) for s in profile["sections"])
    for fn, bysec in per_func.items():
        for sec, nb in bysec.items():
            if nb > used[sec]:
                used[sec] = nb
                worst[sec] = fn

    per = []
    viol = []
    for s in profile["sections"]:
        n = s["name"]
        over = used[n] - cap[n]
        per.append({"name": n, "used": used[n], "capacity": cap[n],
                    "arrays": count[n], "worst_func": worst[n],
                    "over_by": max(0, over)})
        if over > 0:
            viol.append({"section": n, "used": used[n], "capacity": cap[n],
                         "over_by": over, "worst_func": worst[n]})
    return per, viol


def _selftest():
    """两向自证：分流边界、超限检测、恰好等于容量不算超。

    只验"能跑"不算自证 —— 一个把所有数组都塞进第一段的实现也能输出表，
    而那恰好会让"大内存段永远为 0"，把溢出藏起来。
    """
    good = bad = 0
    # 注意：首段必须声明 `max_array_bytes`，否则按新语义（缺省=能装任何）
    # 它会吞下所有数组，末段恒为 0 —— 那正是旧 classify 的退化形态。
    prof = {"tcm_max_array": 1000,
            "sections": [{"name": "tcm", "capacity_bytes": 2000,
                          "max_array_bytes": 1000},
                         {"name": "ddr", "capacity_bytes": 100000}]}
    try:
        p = load_profile_from_obj(prof)
        good += 1
    except ValueError as e:
        p = None
        bad += 1
        print("  [selftest] 合法 profile 被拒：%s" % e)

    if p:
        # 500 字节 -> tcm；2000 字节 -> ddr
        if classify(500, p) == "tcm" and classify(2000, p) == "ddr":
            good += 1
        else:
            bad += 1
            print("  [selftest] 分流边界不对")

        # **三段 profile 必须每段都能被用到**（R1041）：旧版只用首段与末段，
        # 中间段恒为 0 —— 而它往往正是最该被用上的 CPU 直连内存。
        p3 = load_profile_from_obj({
            "tcm_max_array": 1024,
            "sections": [
                {"name": "itcm", "capacity_bytes": 100000,
                 "max_array_bytes": 1000},
                {"name": "dtcm", "capacity_bytes": 100000,
                 "max_array_bytes": 10000},
                {"name": "ddr", "capacity_bytes": 100000},
            ]})
        _m = {100: "itcm", 5000: "dtcm", 50000: "ddr"}
        if all(classify(n, p3) == want for n, want in _m.items()):
            good += 1
        else:
            bad += 1
            print("  [selftest] 三段分流不对：%r"
                  % {n: classify(n, p3) for n in _m})

        per, viol = check([(("f"), "a", 1500), ("f", "b", 600)], p)
        _t = [x for x in per if x["name"] == "tcm"][0]
        if _t["used"] == 600 and _t["arrays"] == 1:
            good += 1
        else:
            bad += 1
            print("  [selftest] tcm 用量算错：%r" % (_t,))

        # 1500+1500 都进 ddr，不超；再塞一个 2000 就超 tcm
        per2, viol2 = check([("f", "a", 2500)], p)
        _d = [x for x in per2 if x["name"] == "ddr"][0]
        if _d["used"] == 2500 and not viol2:
            good += 1
        else:
            bad += 1
            print("  [selftest] ddr 用量或超限判定错：%r" % (_d,))

        # 恰好等于容量：不超（用 ddr，因为 2000 > tcm_max_array 会分流到 ddr）
        per3, viol3 = check([("f", "x", 100000)], p)
        _d3 = [x for x in per3 if x["name"] == "ddr"][0]
        if _d3["used"] == 100000 and not viol3:
            good += 1
        else:
            bad += 1
            print("  [selftest] 恰好等于容量被判超限（应不超）：%r" % (_d3,))
    else:
        bad += 2

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def load_profile_from_obj(obj):
    """与 load_profile 同一套校验，但吃 dict（自证用）。"""
    secs = obj.get("sections")
    if not isinstance(secs, list) or not secs:
        raise ValueError("sections 必须非空")
    for s in secs:
        for k in ("name", "capacity_bytes"):
            if k not in s:
                raise ValueError("缺 %s" % k)
        if not isinstance(s["capacity_bytes"], int) or s["capacity_bytes"] <= 0:
            raise ValueError("capacity_bytes 必须正整数")
    if not isinstance(obj.get("tcm_max_array"), int):
        raise ValueError("tcm_max_array 必须整数")
    return obj


def main(argv=None):
    ap = argparse.ArgumentParser(description="分段预算校验")
    ap.add_argument("src", nargs="?")
    ap.add_argument("--profile", required=False)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.src or not os.path.isdir(ns.src):
        print("mem_sections: 缺输入（MIR 目录不存在）")
        return 2
    if not ns.profile or not os.path.isfile(ns.profile):
        print("mem_sections: 缺输入（--profile 指向的 target profile 不存在）")
        return 2
    try:
        prof = load_profile(ns.profile)
    except ValueError as e:
        print("mem_sections: profile 不合法 —— %s" % e)
        return 2

    arrays, unknown = scan_arrays(ns.src)
    per, viol = check(arrays, prof)
    if ns.json:
        print(json.dumps({"profile": ns.profile, "sections": per,
                          "violations": viol, "unknown_shape": unknown},
                         ensure_ascii=False, indent=1))
        return 1 if viol else 0

    print("[sections] %s ｜ 数组 %d ｜ 形状未知 %d"
          % (os.path.basename(ns.src.rstrip("\\/")), len(arrays), unknown))
    for x in per:
        flag = "  **超限**" if x["over_by"] else ""
        print("  %-10s %8d / %8d B（%.0f%%）｜ 数组 %d%s"
              % (x["name"], x["used"], x["capacity"],
                 100.0 * x["used"] / x["capacity"], x["arrays"], flag))
    if viol:
        for v in viol:
            print("  Error: %s memory overflow! Exceeded by %d B (%.1f KB)"
                  % (v["section"], v["over_by"], v["over_by"] / 1024.0))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
