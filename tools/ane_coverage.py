# -*- coding: utf-8 -*-
"""**规范覆盖表**：ANE v0.9.0 的 44 章，本仓各有无判据。

    python tools/ane_coverage.py
    python tools/ane_coverage.py --json
    python tools/ane_coverage.py --selftest

## 为什么需要它

`check_ane.py` 只覆盖 6 条可机检条款，而规范有 **44 章、195 个三级小节**。
也就是说：**"本项目按规范开发"这句话，此前能拿出证据的不到 15%**，
而剩下的 85% 既没证据、也没人知道它是空白。

本表把「哪几章有判据、哪几章是空白」摆出来。**空白的价值不低于有判据的**——
因为不知道空白在哪，就会一直以为已经覆盖了。

## 判据口径

每章给三种状态：

| 状态 | 含义 |
|---|---|
| `COVERED` | 有专门的门在每次发版时核对 |
| `PARTIAL` | 部分条款可机检（如只覆盖了三条硬边界里的一条） |
| `NONE`    | 没有判据（空白） |

`evidence` 列是**可核对的路径**：脚本会检查它是否存在。路径不存在的条目
自动降级为 `NONE` —— 否则这张表本身就会骗人。

## 诚实边界

* 这张表是**我逐章判断**的，不是自动推导的；判断依据写在 `why` 里；
* 「有门」不等于「规范那一章的全部要求都做到了」，`PARTIAL` 就是在说这件事；
* 不统计条数百分比（那会给出虚假的完成度），只给状态分布。

退出码：0=已产出 1=自证失败 2=缺输入
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: (章号/简称, 状态, 证据路径, 判断理由)
#: 状态由**我这轮逐章读**得出，evidence 可被脚本核对。
CHAPTERS = [
    ("第零章 范式定位", "NONE", "", "问题陈述章，无强制条款"),
    ("第一章 核心公理", "PARTIAL", "tools/check_ane.py",
     "七条公理里，公理三（小脑优先）、四（记忆）、五（主权）、六（白盒）有门；"
     "公理一/二/七（动静二元、稳态第一）无判据"),
    ("第二章 七器官模型", "NONE", "",
     "器官划分是叙述性的，本仓没有按器官组织代码，也没有对应判据"),
    ("第三章 D0–D3 分级", "PARTIAL", "flow/ane-auth.json",
     "授权文件里记了 D0 不可变，但没有「改动是否越级」的机检"),
    ("第四章 小脑规范", "COVERED", "tools/check_cerebellum.py",
     "三条硬边界全部机检：CB1 离线率、CB2 可生长、CB4 无推测"),
    ("第五章 大脑与 NTP", "COVERED", "tools/ntp.py",
     "NTP 字段齐全与 ANE5 一致性由 CB3 核对；无推测由 CB4 核对"),
    ("第六章 记忆规范", "PARTIAL", "tools/brain.py",
     "经验有见证校验（AN3），但没有「记忆分温（热/温/冷/冻）落地」的判据"),
    ("第七章 免疫/双轨验证", "PARTIAL", "tools/check_generated_compiles.py",
     "GX2 的 519 条测试是其中一轨；「双轨交叉比对」本身没有判据"),
    ("第八章 自愈/统一语义层", "NONE", "",
     "本仓没有即时修复层"),
    ("第九章 人机协同/主权", "PARTIAL", "flow/ane-auth.json",
     "有授权记录（AN5），但没有「授权过期/越界」的机检"),
    ("第十章 进化飞轮", "NONE", "", "无判据"),
    ("第十一章 成熟度 L0–L5", "NONE", "",
     "本仓没有给自己评过成熟度等级"),
    ("第十二章 度量与反模式", "PARTIAL", "tools/progress.py",
     "有红黄绿完成度表；反模式清单未逐条核对"),
    ("第十三章 交互模式矩阵", "N/A", "", "不适用于单仓编译器项目：本仓是单智能体开发的 MATLAB→C 工具链，没有多智能体、多租户、生命体间通信或套件组合的形态。显式标 N/A 而非留作空白——空白会被误读成「还没做」。"),
    ("第十四章 交互原语", "N/A", "", "不适用于单仓编译器项目：本仓是单智能体开发的 MATLAB→C 工具链，没有多智能体、多租户、生命体间通信或套件组合的形态。显式标 N/A 而非留作空白——空白会被误读成「还没做」。"),
    ("第十五章 工具生态 MCP", "NONE", "", "本仓未接 MCP"),
    ("第十六章 多智能体协同", "N/A", "", "不适用于单仓编译器项目：本仓是单智能体开发的 MATLAB→C 工具链，没有多智能体、多租户、生命体间通信或套件组合的形态。显式标 N/A 而非留作空白——空白会被误读成「还没做」。"),
    ("第十七章 安全与信任边界", "NONE", "", "无 OWASP 对齐检查"),
    ("第十八章 成本治理", "PARTIAL", "tools/brain_llm.py",
     "四信号避免无效上行（省 Token），但没有成本预算的硬闸"),
    ("第十九章 传统工程的扬弃", "NONE", "", "叙述性"),
    ("第二十章 组织治理", "NONE", "", "组织层面，非代码可检"),
    ("第二十一章 失效安全与降级", "PARTIAL", "c_runtime/include/mlc.h",
     "MLC_UNIMPLEMENTED 是值层面的降级；但没有「降级比例」判据"),
    ("第二十二章 身份与可追溯", "NONE", "", "无命名空间判据"),
    ("第二十三章 人类因素", "N/A", "", "不适用于单仓编译器项目：本仓是单智能体开发的 MATLAB→C 工具链，没有多智能体、多租户、生命体间通信或套件组合的形态。显式标 N/A 而非留作空白——空白会被误读成「还没做」。"),
    ("第二十四章 多租户与记忆边界", "N/A", "", "不适用于单仓编译器项目：本仓是单智能体开发的 MATLAB→C 工具链，没有多智能体、多租户、生命体间通信或套件组合的形态。显式标 N/A 而非留作空白——空白会被误读成「还没做」。"),
    ("第二十五章 元规范", "NONE", "", "规范自身的治理，非本仓职责"),
    ("第二十六章 ANE-CONF 符合性", "PARTIAL", "tools/check_ane.py",
     "有 6 条机检，远未构成完整符合性评估"),
    ("第二十七章 迁移与采纳", "NONE", "", "叙述性"),
    ("第二十八章 可观测性", "PARTIAL", "tools/full_report.py",
     "有完整报告，但没有指标体系的定义"),
    ("第二十九章 演化系统测试", "PARTIAL", "tools/check_generated_compiles.py",
     "GX2 属此类；但没有「测试自身是否腐化」的判据（除 figures_refresh 那条）"),
    ("第三十章 适用边界", "NONE", "", "叙述性"),
    ("第三十一章 经济性", "NONE", "", "无成本度量"),
    ("第三十二章 发布形态", "NONE", "", "无受众视图"),
    ("第三十三章 信息分级与发布门禁", "NONE", "", "无判据"),
    ("第三十四章 规范即制品", "PARTIAL", "aistandard/ANE规范-AI原生软件生命体工程范式.md",
     "规范已入库（单一真源）；但没有「投影确定性」的校验"),
    ("第三十五章 多语言治理", "PARTIAL", "tools/check_readme_parity.py",
     "中英 README 结构一致有判据；其他制品未覆盖"),
    ("第三十六章 制品命名", "NONE", "", "无命名判据"),
    ("第三十七章 结构完整性与投影校验", "PARTIAL", "tools/check_eol_convention.py",
     "有行尾与结构约定；投影后校验未做"),
    ("第三十八章 IOP 生命体间通信", "N/A", "", "不适用于单仓编译器项目：本仓是单智能体开发的 MATLAB→C 工具链，没有多智能体、多租户、生命体间通信或套件组合的形态。显式标 N/A 而非留作空白——空白会被误读成「还没做」。"),
    ("第三十九章 套件与组合", "N/A", "", "不适用于单仓编译器项目：本仓是单智能体开发的 MATLAB→C 工具链，没有多智能体、多租户、生命体间通信或套件组合的形态。显式标 N/A 而非留作空白——空白会被误读成「还没做」。"),
    ("第四十章 向 AGI 演进", "NONE", "", "路线性"),
    ("第四十一章 沟通数据格式", "PARTIAL", "tools/ntp.py",
     "NTP 报文格式有判据；存储与联网策略未涉及"),
    ("第四十二章 规范性等级与必选清单", "NONE", "",
     "本仓没有把规范的「必选」条款抽成清单"),
    ("第四十三章 传统软件向生命体转换", "PARTIAL", "tools/validate_ntp.py",
     "转换台账（43.9/43.10）有校验器，但未接入门禁"),
]


def audit(chapters=None):
    rows = []
    for name, status, ev, why in (chapters if chapters is not None else CHAPTERS):
        exists = bool(ev) and os.path.exists(os.path.join(ROOT, ev))
        # 证据不存在则降级：否则这张表本身就在骗人。
        # `N/A` 不降级：它声明的是"本章不适用于本仓"，不需要证据文件。
        real = status if (status in ("NONE", "N/A") or exists) else "NONE"
        note = why
        if status != "NONE" and not exists:
            note = "证据路径不存在（%s），已降级为 NONE" % ev
        rows.append({"chapter": name, "status": real, "declared": status,
                     "evidence": ev, "evidence_ok": exists, "why": note})
    cnt = {}
    for r in rows:
        cnt[r["status"]] = cnt.get(r["status"], 0) + 1
    return rows, cnt


def _selftest():
    """两向自证：证据缺失必须降级为 NONE；状态分布必须能算出。"""
    good = bad = 0
    rows, cnt = audit()
    if len(rows) == len(CHAPTERS):
        good += 1
    else:
        bad += 1
        print("  [selftest] 行数与章节表不一致")

    # 降级能力：造一条假证据（用参数注入，不用 global）
    fake = [("假章", "COVERED", "tools/__no_such_file__.py", "测降级")]
    r2, _c2 = audit(fake)
    if r2[0]["status"] == "NONE" and not r2[0]["evidence_ok"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 证据缺失未降级：%r" % (r2[0],))

    if sum(cnt.values()) == len(rows):
        good += 1
    else:
        bad += 1
        print("  [selftest] 状态分布合计不等于行数")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="ANE 规范覆盖表")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()

    rows, cnt = audit()
    if ns.json:
        print(json.dumps({"counts": cnt, "rows": rows},
                         ensure_ascii=False, indent=1))
        return 0

    print("[ANE 覆盖] 44 章 ｜ COVERED %d ｜ PARTIAL %d ｜ NONE %d ｜ N/A %d"
          % (cnt.get("COVERED", 0), cnt.get("PARTIAL", 0),
             cnt.get("NONE", 0), cnt.get("N/A", 0)))
    print()
    for r in rows:
        mark = {"COVERED": "✅", "PARTIAL": "◐", "NONE": "✗",
                "N/A": "—"}.get(r["status"], "?")
        print("%s %-30s %s" % (mark, r["chapter"], r["why"][:52]))
    print()
    print("[结论] %d 章有专门判据，%d 章部分覆盖，%d 章空白 ——"
          "「全方位按规范」当前不成立，空白章节已逐条列出"
          % (cnt.get("COVERED", 0), cnt.get("PARTIAL", 0), cnt.get("NONE", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
