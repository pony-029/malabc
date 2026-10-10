# -*- coding: utf-8 -*-
"""登记制护栏：`tests/` 里那些**引用了从未提交的产物**、因而今天跑不起来的测试，
必须有一张**两向登记**，使「永久红」变成**有界、具名、只缩不长**的东西。

动因（R63；承接 R49 起的 C''''0/C13-0，**沿用十余轮、始终最高优先**）：
`tests/test_matlabc.py` 里有一整条前端审计线（R81–R149）以及打包/配置类测试，
它们被测的对象 —— `fe_audit.py`、`fe_dom_check.js`、
`.github/workflows/frontend-gate.yml`、`_fe_capability.json`、`setup.py`、
`analyzer_config.example.json` —— **在 git 全历史里从未提交过**（`git log --all`
为空，磁盘上也没有副本）。于是这批测试在**未改动基线**上就是红的。

这件事真正的危害不是"红了几条"，而是 **红变成了背景色**：

    * 51 条常红 ⇒ 下一条**真**回归淹在里面，没人看得见；
    * 历史文档一路把这批红记成「7 条」（R49–R53）到「25 条」（R53），
      **从来没有一次是量出来的**（R63 实测：单个过滤式 47 条红）。
      口径不对，数字就只是传说。

本门做三件事：
  ① 把「产物」登记成 **不做**（带理由），并**两向**核对；
  ② 把「引用它的测试」按**实测结果**三分登记（红 / 优雅跳过 / 其余绿），
     并**两向**核对（多一条没登记 ⇒ 红；登记了却对不上 ⇒ 也红）；
  ③ 顺手把 **类 A「路径漂移」** 的残留钉住：`os.path.join(<根>, "<文件名>")`
     的单段写法若指向一个**在根与 `docs/` 都不存在**的文件，也必须登记。

  它为什么不只是"把红记个账"：登记是**有反作用力**的 ——
  K2 要求登记过的产物**必须真的不存在**（哪天有人补上 `setup.py`，登记立刻变
  陈旧 ⇒ 红，逼你把那几条测试从登记里摘掉、看它们是否真绿）；
  K1 要求**扫描到的引用集合 == 登记集合**（新加一条依赖缺失产物的测试 ⇒ 红）。
  只写「已知红清单」而没有这两条，清单会慢慢变成垃圾桶。

一图看懂（谁在跟谁说话）：

    产物（从未提交）                引用它的测试（实测三分）
    ┌──────────────────┐            ┌────────────────────────┐
    │ MISSING_ARTIFACTS │◄── K1 ───►│ RED / SKIP / GREEN_REFS │
    └──────────────────┘  两向集合   └────────────────────────┘
             ▲                                    ▲
        K2 必须真的不存在                   K4 跳过必须真有 pytest.skip
             │                                    │
    ┌──────────────────┐            ┌────────────────────────┐
    │ 仓库工作区        │            │ tests/test_matlabc.py   │
    └──────────────────┘            └────────────────────────┘

判据（K1–K6，管辖范围互不重叠）：
    K1 覆盖    扫描「引用了已登记产物的测试」⇒ 必须**恰好**等于登记集合（两向）
    K2 真缺失  每个已登记产物在仓库里必须**不存在**（存在 ⇒ 登记陈旧 ⇒ 红）
    K3 理由具名 每条理由必须逐字含该产物的 basename（理由得是关于**这个**文件的）
    K4 跳过为真 每个登记为「优雅跳过」的测试，源码里必须真的有 `pytest.skip`
    K5 新缺口   `os.path.join(<根>, "<单段文件名>")` 指向的文件若在根与 docs/ 都
                不存在、且未登记 ⇒ 红（把「新长出来一个引用缺失产物的测试」也罩住）
    K6 缺输入   `tests/test_matlabc.py` 不存在 ⇒ 红（不是"没有可检查对象 ⇒ 放行"）

两向自证：好样本（一致的合成树）必须放行；7 个坏样本（K1 未登记 / K1 陈旧 /
K2 陈旧 / K3 理由无名字 / K4 伪装跳过 / K5 新缺口 / K6 缺输入）必须各被抓到。

用法：
    python tools/check_known_red.py             # 0=一致 1=有违规 2=缺输入
    python tools/check_known_red.py --selftest  # 两向自证

退出码：
    0 = 登记与事实两向一致（K1–K6 全绿）
    1 = 有违规（未登记 / 陈旧 / 理由不具名 / 伪装跳过 / 新缺口）
    2 = 缺输入（找不到 tests/test_matlabc.py）
"""
import argparse
import io
import os
import re
import shutil
import sys
import tempfile

# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族，
# 或本门独有的机制名）。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "K1–K6"

TESTS_REL = os.path.join("tests", "test_matlabc.py")

# ---------------------------------------------------------------------------
# 产物登记：在 git 全历史里**从未提交**、磁盘上也没有副本的东西。
# 每条的理由必须逐字含 basename（K3），且该文件必须真的不存在（K2）。
# ---------------------------------------------------------------------------
MISSING_ARTIFACTS = {
    "fe_audit.py":
        "`fe_audit.py`：R81–R149 的**前端审计器**（站点死链 / 无障碍 / SEO / "
        "预算 / 能力注册表 / 幂等写入 / 严格退出码…）：`git log --all` 为空、磁盘上无副本，"
        "但它有整整一条测试线在描述它的契约。做与不做是需要单独决策的一件事。",
    "fe_dom_check.js":
        "`fe_dom_check.js`：`fe_audit.py` 的 DOM 子检查（由 node 跑的 jsdom "
        "脚本）：同上，从未提交。",
    ".github/workflows/frontend-gate.yml":
        "`frontend-gate.yml`：把前端审计接进 CI 的工作流；从未提交；"
        "`test_p271_ci_gate_workflow_usable` "
        "要求它「实际可用」而不是一份写给别人看的示例。",
    "_fe_capability.json":
        "`_fe_capability.json`：`fe_audit.py` 的能力金样（golden），由 "
        "`fe_audit.py --capability-out=` "
        "生成，因而随审计器一起缺失。",
    "setup.py":
        "`setup.py`：打包入口；从未提交。它的契约已经由 `test_p54` / `test_p55` "
        "逐条写明"
        "（version == VERSION、`matlabc=matlabc:main`、`py_modules=[\"matlabc\"]`）"
        "—— 这是**补文件**就能拿回来的一类，不是「永远不做」。",
    "analyzer_config.example.json":
        "`analyzer_config.example.json`：示例配置文件；从未提交；`test_p54` / "
        "`test_p72` 要求它含 `reproducible` "
        "与 `incremental` 两个字段。",
}

# 负样本登记：**就该不存在**的文件（由测试断言"缺输入必须红"）。
NEGATIVE_FIXTURES = {
    "no_such_lib_xyz.so":
        "`test_r31_binary_cli_missing_file_is_red` 的负样本：它断言「`--binary` "
        "指向不存在的文件必须 rc=2」—— 所以 `no_such_lib_xyz.so` **就该不存在**，"
        "K2 对它同样成立（哪天有人在仓库里放了这个名字的文件，本门要红）。",
}

# ---------------------------------------------------------------------------
# 引用登记（R63 实测三分；数字来自仓库外装置 `_r62/`，见 R63 复盘 §1）。
#   值 = 该测试引用到的产物元组（同一个测试引用两个产物时两个都写）。
# ---------------------------------------------------------------------------
RED_TESTS = {
    # 实测 47 条：引用了缺失产物 ⇒ 今天**失败**。
    "test_check_real_dom_empty_is_error": ("fe_dom_check.js",),
    "test_min_pages_guard": ("fe_audit.py",),
    "test_p271_ci_gate_workflow_usable":
        (".github/workflows/frontend-gate.yml", "fe_audit.py"),
    "test_p271_r4_callgraph_keyboard": ("fe_dom_check.js",),
    "test_p54_docs_consistency":
        ("analyzer_config.example.json", "setup.py"),
    "test_p55_packaging_entrypoints": ("setup.py",),
    "test_p72_incremental_stats_and_doc_sync": ("analyzer_config.example.json",),
    "test_r100_usage_doc_has_new_flags": ("fe_audit.py",),
    "test_r103_warn_ok_strict_progressive": ("fe_audit.py",),
    "test_r104_registry_enforcement_and_list_checks": ("fe_audit.py",),
    "test_r105_usage_doc_sync": ("fe_audit.py",),
    "test_r106_out_file_matches_stdout_summary": ("fe_audit.py",),
    "test_r109_samples_option": ("fe_audit.py",),
    "test_r110_elapsed_ms_in_summary": ("fe_audit.py",),
    "test_r111_capability_flags": ("fe_audit.py",),
    "test_r113_capability_golden": ("fe_audit.py",),
    "test_r114_rerun_field": ("fe_audit.py",),
    "test_r115_failed_files_listing": ("fe_audit.py",),
    "test_r116_explain_and_notes_completeness": ("fe_audit.py",),
    "test_r118_stdout_out_byte_identical": ("fe_audit.py",),
    "test_r120_schema_in_capability": ("fe_audit.py",),
    "test_r121_repo_capability_golden": ("_fe_capability.json", "fe_audit.py"),
    "test_r122_delta_comparator": ("fe_audit.py",),
    "test_r123_page_stats": ("fe_audit.py",),
    "test_r124_text_meta_line": ("fe_audit.py",),
    "test_r125_against_baseline": ("fe_audit.py",),
    "test_r126_registry_json_notes": ("fe_audit.py",),
    "test_r132_config_print": ("fe_audit.py",),
    "test_r139_list_ignores": ("fe_audit.py",),
    "test_r143_selftest_cli": ("fe_audit.py",),
    "test_r144_selftest_json": ("fe_audit.py",),
    "test_r149_schema_json": ("fe_audit.py",),
    "test_r81_doc_fact_sync": ("fe_audit.py",),
    "test_r85_r86_site_quality_gate": ("fe_audit.py",),
    "test_r87_audit_check_registry": ("fe_audit.py",),
    "test_r89_strict_exit_codes": ("fe_audit.py", "fe_dom_check.js"),
    "test_r92_fe_artifact_exemption": ("fe_audit.py", "fe_dom_check.js"),
    "test_r93_issue_contract_validation": ("fe_audit.py",),
    "test_r94_collect_html_excludes_audit_artifacts": ("fe_dom_check.js",),
    "test_r95_audit_idempotence": ("fe_audit.py",),
    "test_r96_audit_write_policing": ("fe_audit.py",),
    "test_r97_contract_doc_synced": ("fe_audit.py",),
    "test_r98_summary_self_describing": ("fe_audit.py",),
    "test_r99_out_file_archival": ("fe_audit.py",),
    "test_selftest_json_schema_stable": ("fe_audit.py",),
    "test_trend_dir_override": ("fe_audit.py",),
    "test_trend_panel_units_and_py36": ("fe_audit.py",),
}

SKIP_TESTS = {
    # 实测 8 条：引用了缺失产物，但自己**优雅跳过**（K4 要求源码里真有 pytest.skip）。
    "test_fe_dom_check_signals_empty": ("fe_dom_check.js",),
    "test_fe_dom_check_skips_huge_page": ("fe_dom_check.js",),
    "test_p271_fe_audit_gate_selfcheck": ("fe_audit.py",),
    "test_p271_fe_audit_hard_gate_clean": ("fe_audit.py",),
    "test_p271_fe_audit_ratchet_baseline": ("fe_audit.py",),
    "test_p271_real_dom_interaction_check": ("fe_dom_check.js",),
    "test_s11_full_coverage": ("fe_dom_check.js",),
    "test_s11_sampling_note_not_warn": ("fe_dom_check.js",),
}

GREEN_REFS = {
    # 实测 4 条：引用了登记产物、但跑起来**是绿的**。
    # 前 3 条是**真引用**（不依赖它 / 早退 / 断言它不存在）；
    # 第 4 条（R63）是**散文提及** —— `scan_refs` 按 basename 扫全文、**含 docstring**，
    # 所以「在测试文档里点名一个已登记产物」本身就等于一条登记义务。这不是 bug，
    # 是本门「宁可多登记一条，也不少登记」的**代价**，而 R63 亲自踩了一脚：
    # 新写的 docstring 里提到登记表里的那个构建脚本，主路径当场 K1 红。
    # 处置**不是**禁止散文点名（那会让文档变哑），而是把它登记在册、让它看得见。
    "test_r101_reference_site_clean_gate": ("fe_audit.py",),
    "test_syntax_color_tokens": ("fe_audit.py",),
    "test_r31_binary_cli_missing_file_is_red": ("no_such_lib_xyz.so",),
    "test_r63_read_doc_resolves_root_then_docs_two_way": ("setup.py",),
}

# K5 的扫描：只认「`os.path.join(<根>, "<单段文件名>")`」这一种写法。
JOIN_ROOT_RE = re.compile(
    r"os\.path\.join\(\s*(?:ROOT|here|analyzer_dir|_REPO)\s*,"
    r"\s*\"([A-Za-z0-9_.\-]+\.[A-Za-z0-9_]+)\"\s*\)")
TEST_DEF_RE = re.compile(r"^def (test_[A-Za-z0-9_]+)", re.M)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    with io.open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def test_spans(text):
    """返回 [(起始偏移, 结束偏移, 测试名)]，按测试函数切分源码。"""
    hits = [(m.start(), m.group(1)) for m in TEST_DEF_RE.finditer(text)]
    spans = []
    for i, (off, name) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        spans.append((off, end, name))
    return spans


def scan_refs(text, artifacts):
    """{产物: {引用它的测试名}}。

    ⚠ 按 **basename** 扫（`.github/workflows/frontend-gate.yml` 取
    `frontend-gate.yml`），避免路径分隔符在正手里变成转义问题；
    也**不**排除注释/docstring —— 提到它就算引用（宁可多登记一条，
    也不少登记；多出来的那条走 GREEN_REFS）。
    """
    spans = test_spans(text)
    out = {}
    for art in artifacts:
        base = art.split("/")[-1]
        found = set()
        for m in re.finditer(re.escape(base), text):
            for a, b, name in spans:
                if a <= m.start() < b:
                    found.add(name)
                    break
        out[art] = found
    return out


def registered_for(regs, art):
    """登记里所有「引用到 art」的测试名（跨三个桶）。"""
    out = set()
    for reg in regs:
        for name, arts in reg.items():
            if art in arts:
                out.add(name)
    return out


def audit(root, missing, negative, red, skip, green, on_problem):
    """施加 K1–K6。返回统计 dict。"""
    tests_path = os.path.join(root, TESTS_REL)
    if not os.path.exists(tests_path):
        on_problem("K6 缺输入：找不到 %s（不是「没有可检查对象 ⇒ 放行」）"
                   % TESTS_REL)
        return {"artifacts": 0, "red": 0, "skip": 0, "green": 0}

    text = _read(tests_path)
    artifacts = list(missing) + list(negative)
    refs = scan_refs(text, artifacts)
    regs = (red, skip, green)

    # ---- K1 覆盖（两向集合）----
    for art in artifacts:
        scanned = refs.get(art, set())
        claimed = registered_for(regs, art)
        for extra in sorted(scanned - claimed):
            on_problem("K1 %s 被 `%s` 引用了，但它没有登记 —— 新长出来的红"
                       "必须登记（否则它会变成背景色）" % (art, extra))
        for stale in sorted(claimed - scanned):
            on_problem("K1 %s 的登记里写着 `%s` 引用它，但扫描扫不到 —— "
                       "登记陈旧（测试改名/删掉/不再引用都要同步）"
                       % (art, stale))

    # ---- K2 真缺失（两向）----
    for art in artifacts:
        if os.path.exists(os.path.join(root, *art.split("/"))):
            on_problem("K2 %s 其实**存在** —— 登记陈旧：该把它挪出登记表，"
                       "并把相关测试从「已知红」里摘掉" % art)

    # ---- K3 理由具名 ----
    for art, reason in list(missing.items()) + list(negative.items()):
        if art.split("/")[-1] not in reason:
            on_problem("K3 %s 的理由里没有出现它的 basename —— "
                       "理由必须是在说**这个**文件" % art)

    # ---- K4 跳过为真 ----
    spans = dict((n, text[a:b]) for a, b, n in test_spans(text))
    for name in skip:
        if name not in spans:
            continue        # 名字不存在由 K1 的「陈旧」分支负责
        if "pytest.skip" not in spans[name]:
            on_problem("K4 `%s` 登记为「优雅跳过」，但它的源码里没有 "
                       "`pytest.skip` —— 把真红伪装成跳过是不允许的" % name)

    # ---- K5 新缺口（单段 os.path.join 写法）----
    for m in JOIN_ROOT_RE.finditer(text):
        rel = m.group(1)
        cands = [os.path.join(root, rel), os.path.join(root, "docs", rel)]
        if any(os.path.exists(c) for c in cands):
            continue
        if rel in missing or rel in negative:
            continue
        on_problem("K5 `os.path.join(<根>, \"%s\")` 指向一个在根与 docs/ 都"
                   "不存在的文件，而它不在登记表里 —— 这是一条**新的**"
                   "永久红（K1 只罩已登记产物，K5 罩新长出来的）"
                   % rel)

    return {"artifacts": len(artifacts), "red": len(red), "skip": len(skip),
            "green": len(green)}


# ---------------------------------------------------------------------------
# 两向自证
# ---------------------------------------------------------------------------
_GOOD_TEST = '''# -*- coding: utf-8 -*-
import os
import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))


def test_uses_missing():
    p = os.path.join(ROOT, "missing_art.py")
    raise SystemExit(p)


def test_skips_missing():
    p = os.path.join(ROOT, "missing_art.py")
    if not os.path.exists(p):
        pytest.skip("missing_art.py 不存在，跳过")


def test_mentions_missing():
    """这里只是在注释里提到 missing_art.py。"""
    return None


def test_negative_fixture():
    p = os.path.join(ROOT, "nope_xyz.so")
    raise SystemExit(p)
'''

_GOOD_MISSING = {"missing_art.py": "合成缺失产物 missing_art.py（理由含 basename）"}
_GOOD_NEGATIVE = {"nope_xyz.so": "负样本 nope_xyz.so：它就该不存在"}
_GOOD_RED = {"test_uses_missing": ("missing_art.py",)}
_GOOD_SKIP = {"test_skips_missing": ("missing_art.py",)}
_GOOD_GREEN = {
    "test_mentions_missing": ("missing_art.py",),
    "test_negative_fixture": ("nope_xyz.so",),
}


def _mkbase(tmp):
    root = os.path.join(tmp, "root")
    os.makedirs(os.path.join(root, "tests"))
    with io.open(os.path.join(root, TESTS_REL), "w",
                 encoding="utf-8", newline="") as fh:
        fh.write(_GOOD_TEST.replace("\n", "\r\n"))
    return root


def _clone(base, tmp, tag):
    dst = os.path.join(tmp, "bad_" + tag)
    shutil.copytree(base, dst)
    return dst


def _run(root, missing, negative, red, skip, green):
    probs = []
    st = audit(root, missing, negative, red, skip, green, probs.append)
    return probs, st


def _selftest():
    bad = 0
    good = 0
    fails = []
    tmp = tempfile.mkdtemp(prefix="knownred_selftest_")
    try:
        base = _mkbase(tmp)

        # ---- 好样本必须放行 ----
        probs, _st = _run(base, _GOOD_MISSING, _GOOD_NEGATIVE, _GOOD_RED,
                          _GOOD_SKIP, _GOOD_GREEN)
        if not probs:
            good += 1
            print("  [正例] 一致的合成树                -> 放行")
        else:
            fails.append("good-sample")
            print("  [正例] 一致的合成树                -> 误伤！%s" % probs[:3])

        def badcase(tag, mut, missing=None, negative=None, red=None,
                    skip=None, green=None):
            r = _clone(base, tmp, tag)
            mut(r)
            p, _ = _run(r,
                        _GOOD_MISSING if missing is None else missing,
                        _GOOD_NEGATIVE if negative is None else negative,
                        _GOOD_RED if red is None else red,
                        _GOOD_SKIP if skip is None else skip,
                        _GOOD_GREEN if green is None else green)
            return p

        cases = []

        # K1 未登记
        def _m1(r):
            p = os.path.join(r, TESTS_REL)
            t = _read(p)
            t += ("\r\n\r\ndef test_brand_new():\r\n"
                  "    p = os.path.join(ROOT, \"missing_art.py\")\r\n"
                  "    return p\r\n")
            with io.open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(t)
        cases.append(("K1-unregistered", _m1, {}))

        # K1 陈旧（登记的测试不再引用）
        g2 = dict(_GOOD_GREEN)
        g2.pop("test_mentions_missing")
        cases.append(("K1-stale", lambda r: None, {"green": g2}))

        # K2 陈旧（产物被补上了）
        def _m3(r):
            with io.open(os.path.join(r, "missing_art.py"), "w",
                         encoding="utf-8", newline="") as fh:
                fh.write("# now exists\n")
        cases.append(("K2-stale", _m3, {}))

        # K3 理由不具名
        cases.append(("K3-unnamed-reason", lambda r: None,
                      {"missing": {"missing_art.py": "某个合成产物"}}))

        # K4 伪装跳过
        def _m5(r):
            p = os.path.join(r, TESTS_REL)
            t = _read(p)
            t = t.replace("        pytest.skip(\"missing_art.py 不存在，跳过\")",
                          "        pass  # 假装跳过")
            with io.open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(t)
        cases.append(("K4-fake-skip", _m5, {}))

        # K5 新缺口
        def _m6(r):
            p = os.path.join(r, TESTS_REL)
            t = _read(p)
            t += ("\r\n\r\ndef test_new_hole():\r\n"
                  "    p = os.path.join(ROOT, \"brand_new_missing.json\")\r\n"
                  "    return p\r\n")
            with io.open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(t)
        cases.append(("K5-new-hole", _m6, {}))

        # K6 缺输入
        def _m7(r):
            os.remove(os.path.join(r, TESTS_REL))
        cases.append(("K6-no-input", _m7, {}))

        for tag, mut, kw in cases:
            p = badcase(tag, mut, **kw)
            if p:
                bad += 1
                print("  [反例] %-20s -> 抓到（%s）" % (tag, p[0][:72]))
            else:
                fails.append(tag)
                print("  [反例] %-20s -> **未被抓到**！" % tag)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    if fails:
        print("SELFTEST FAILED: %s" % fails)
        return 1
    print("SELFTEST PASSED")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    root = repo_root()
    probs = []
    st = audit(root, MISSING_ARTIFACTS, NEGATIVE_FIXTURES, RED_TESTS,
               SKIP_TESTS, GREEN_REFS, probs.append)
    if st["artifacts"] == 0:
        return 2
    if probs:
        print("check_known_red: %d 项不一致" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_known_red: OK（%d 个从未提交的产物 + %d 个负样本登记为「不做」；"
          "引用它们的测试按实测三分在册：红 %d / 优雅跳过 %d / 其余绿 %d；"
          "判据族 %s）"
          % (len(MISSING_ARTIFACTS), len(NEGATIVE_FIXTURES), st["red"],
             st["skip"], st["green"], ROW_SIGNATURE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
