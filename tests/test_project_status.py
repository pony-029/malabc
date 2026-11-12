# -*- coding: utf-8 -*-
"""整体状态判据：**计划阶段的完成必须有证据，且证据必须真的在跑**。

## 这条判据守的是"完成度"这个词的分母

一个阶段被称"完成"，通常靠三样东西之一：
    a) 文档里写了「已完成」          → 会过期，且没人核对
    b) 有个测试文件                  → 可能存在但**没人跑**（本项目踩过：15 个孤儿测试）
    c) 判据存在 **且** 已被门引用     → 这才是可验证的完成

所以这里只认 (c)：`tools/project_status.py` 给出的每个阶段都必须 `done`，
而 `done` 的定义是「证据文件存在 **且** 出现在 GX2 清单里」。

## 为什么不顺带断言"图都是现行的"

`flow/figures` 下 20 张图当前**全部滞后**（落后 >10 个提交）。把它断言成零
会逼着每次改代码都重渲染全部图 —— 那是另一个成本量级的事。这里只断言
**数字是诚实的**（张数 == 磁盘目录数、三档之和 == 张数），滞后本身由
`flow/catalog.html` 展示给人看。
"""
import io
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import project_status as PS       # noqa: E402


@pytest.fixture(scope="module")
def status():
    return PS.build()


def test_every_phase_has_running_evidence(status):
    """每个计划阶段都必须：证据文件存在 + 已接入 GX2。"""
    bad = []
    for p in status["phases"]:
        if p["status"] != "done":
            bad.append("%s（缺 %s / 未接线 %s）"
                       % (p["id"], p["missing"], p["not_gated"]))
    assert not bad, "阶段完成度不可判定：%s" % bad


def test_phase_evidence_files_really_registered(status):
    """证据文件必须真的是 `tests/` 下的文件（防止写个名字充数）。"""
    for p in status["phases"]:
        for e in p["evidence"]:
            assert os.path.isfile(os.path.join(ROOT, e)), "%s 的证据不存在：%s" % (
                p["id"], e)
            assert re.match(r"^tests/test_[a-z0-9_]+\.py$", e), \
                "证据必须是 tests/ 下的用例文件：%r" % e


def test_figure_counts_are_honest(status):
    """图张数与三档之和必须对得上磁盘（数字可以难看，但不能说谎）。"""
    f = status["figures"]
    base = os.path.join(ROOT, "flow", "figures")
    if not os.path.isdir(base):
        pytest.skip("没有 flow/figures")
    on_disk = len([d for d in os.listdir(base)
                   if os.path.isdir(os.path.join(base, d))])
    assert f["count"] == on_disk, \
        "统计到 %d 张，磁盘上 %d 张" % (f["count"], on_disk)
    s = (f["current"] + f["recent"] + f["stale"] + f["unknown"]
         + f.get("historical", 0))
    assert s == f["count"], "各档之和 %d != 张数 %d" % (s, f["count"])


def test_gx2_list_is_nonempty(status):
    """GX2 清单非空 —— 否则"已接线"这个判定会在空集上恒真。"""
    assert status["gx2_tests"] >= 50, \
        "GX2 只引用了 %d 个测试文件（判据可能被清空）" % status["gx2_tests"]


#: 主干图（读者建立"系统长什么样"全靠这几张）。
MAIN_FIGURES = {
    "architecture-system-whole-20261109": "F37 系统全貌",
    "architecture-module-trace-20261109": "F38 模块×交互×追踪点",
    "architecture-engineering-platform-20261108": "F30 五层总览",
}

#: 允许多少提交的滞后。**这不是"新鲜度"，是"腐烂线"**：
#: 每次提交都重渲染不现实（一次 20~40s），但落后几十个提交的图会开始说谎。
MAX_LAG = 40


def test_main_figures_do_not_rot():
    """主干图不得落后超过 `MAX_LAG` 个提交。

    为什么用"腐烂线"而不是"必须现行"：图的价值是**给人建立地图**，
    而地图在落后十几个提交时仍然基本正确；落后几十个提交则开始指错地方。
    判据卡在后者 —— 它拦的是"放着不管"，不是"没跟到最新一次提交"。

    修法只有一条：`python tools/figures_refresh.py --only <目录名>`。
    """
    base = os.path.join(ROOT, "flow", "figures")
    if not os.path.isdir(base):
        pytest.skip("没有 flow/figures")
    head = PS._head()
    if not head:
        pytest.skip("取不到 HEAD")
    rot = []
    for d, title in MAIN_FIGURES.items():
        p = os.path.join(base, d, "candidate.json")
        if not os.path.isfile(p):
            rot.append((title, d, "目录不存在"))
            continue
        c = json.load(io.open(p, encoding="utf-8"))
        meta = c.get("meta") or {}
        rev = ((meta.get("repository") or {}).get("revision") or "").strip()
        if not rev:
            rot.append((title, d, "没有 revision"))
            continue
        r = subprocess.run(["git", "rev-list", "--count", "%s..%s" % (rev, head)],
                           cwd=ROOT, stdin=subprocess.DEVNULL, timeout=60,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            lag = int(r.stdout.decode().strip())
        except ValueError:
            rot.append((title, d, "算不出 lag"))
            continue
        if lag > MAX_LAG:
            rot.append((title, d, "落后 %d 个提交（上限 %d）" % (lag, MAX_LAG)))
    assert not rot, (
        "主干图已腐烂，请重渲染：\n  " +
        "\n  ".join("%s (%s)：%s" % t for t in rot) +
        "\n  修法：python tools/figures_refresh.py --only <目录名>")


def test_every_top_dir_has_a_group():
    """每个**顶层目录**都必须落在某个职责域里。

    分组表是人写的，人写的清单只会被追加、很少被审 —— 新目录很容易落进
    "未分组"，而它一旦出现，就意味着有一层代码**没人负责**（既不属于转换，
    也不属于运行时/工具/判据）。这条判据把这个缺口变成红灯。

    豁免只允许：`docs/`（纯文档）、`vscode/`（编辑器插件）、`.git` 等点目录。
    """
    # 只豁免"不是本项目代码"的目录（构建产物、缓存、空目录）。
    # `docs/`、`vscode/` **不豁免** —— 它们也是本项目的一部分，必须归属某个域。
    EXEMPT = {"releases", "node_modules", "flow_out", "__pycache__", "dlow"}
    groups = PS.GROUPS
    known = {p.rstrip("/") for p in groups}
    missing = []
    for d in sorted(os.listdir(ROOT)):
        if d.startswith(".") or d in EXEMPT:
            continue
        full = os.path.join(ROOT, d)
        if not os.path.isdir(full):
            continue
        if d not in known:
            missing.append(d)
    assert not missing, \
        "这些顶层目录没有归属职责域（在 tools/project_status.py 的 GROUPS 里补）：%r" % missing


def test_figure_gate_counts_match_reality():
    """图上写的「门禁 N 门」必须等于真实门数。

    这类数字**不会被任何东西自动纠正**（渲染器只校验宽度，不校验事实），
    所以它只会安静地过期：R816 实测，42 道门时 F38 上还写着 41。
    现在 `figures_refresh` 会在渲染前同步它，这条判据保证**没重渲染也不会漂**。

    口径与 `check_all` 的 `MIN_GUARDS` 一致：**排除 runner 自身**。
    """
    tools_dir = os.path.join(ROOT, "tools")
    real = len([f for f in os.listdir(tools_dir)
                if f.startswith("check_") and f.endswith(".py")
                and f != "check_all.py"])
    base = os.path.join(ROOT, "flow", "figures")
    if not os.path.isdir(base):
        pytest.skip("没有 flow/figures")

    bad = []
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d, "candidate.json")
        if not os.path.isfile(p):
            continue
        txt = io.open(p, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"门禁\s*(\d+)\s*门", txt):
            if int(m.group(1)) != real:
                bad.append((d, int(m.group(1))))
    assert not bad, \
        "这些图上的门数过期（真实 %d 门）：%r —— 跑 tools/figures_refresh.py 重渲染" % (
            real, bad[:5])


def test_historical_figures_are_registered_with_reason():
    """历史图必须**带理由**，且**不能被标成现行**（两向）。

    * 有 `meta.status == "historical"` 却没有理由 ⇒ 红（免检要写清为什么）；
    * 标了 historical 却已经是现行（revision == HEAD）⇒ 陈旧登记 ⇒ 红
      （它其实能刷新，不该挂在历史档里）。

    这条守的是登记制最容易烂掉的方式：**只加不减**。
    """
    base = os.path.join(ROOT, "flow", "figures")
    if not os.path.isdir(base):
        pytest.skip("没有 flow/figures")
    head = PS._head()
    missing_reason, stale_mark = [], []
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d, "candidate.json")
        if not os.path.isfile(p):
            continue
        c = json.load(io.open(p, encoding="utf-8"))
        meta = c.get("meta") or {}
        if (meta.get("status") or "") != "historical":
            continue
        if len((meta.get("historical_reason") or "").strip()) < 12:
            missing_reason.append(d)
        rev = ((meta.get("repository") or {}).get("revision") or "").strip()
        if rev and head and rev == head:
            stale_mark.append(d)
    assert not missing_reason, "历史图缺理由（或太短）：%r" % missing_reason[:5]
    assert not stale_mark, \
        "这些图标了 historical 但已是现行 —— 应摘掉标记：%r" % stale_mark[:5]


def test_history_is_bounded_and_parsable():
    """历史文件：**每行可解析** + **行数有上界** + 折叠点要说明折了多少。

    只追加的文件没有上界就会无限膨胀；而膨胀之后没人会读它 ——
    于是"变化"这一列重新变回不可用，与不记录没有区别。
    """
    p = PS.HISTORY
    if not os.path.isfile(p):
        pytest.skip("还没有历史文件（先跑一次 --record）")
    raw = [ln.strip() for ln in io.open(p, encoding="utf-8", errors="replace")
           if ln.strip()]
    assert raw, "历史文件是空的"
    assert len(raw) <= PS.MAX_HISTORY, \
        "历史 %d 行超过上界 %d" % (len(raw), PS.MAX_HISTORY)

    bad, folded = [], []
    for i, ln in enumerate(raw, 1):
        try:
            j = json.loads(ln)
        except ValueError:
            bad.append((i, ln[:60]))
            continue
        if "folded" in j:
            folded.append(j["folded"])
            if not isinstance(j["folded"], int) or j["folded"] < 1:
                bad.append((i, "折叠标记的值不是正整数：%r" % j["folded"]))
    assert not bad, "历史文件有坏行：%r" % bad[:3]
    assert len(folded) <= 1, "折叠标记出现了 %d 次（应最多一次）" % len(folded)


def test_record_is_idempotent_for_same_snapshot():
    """同一个快照重复记录**不应**增加行数（否则历史会被刷屏）。"""
    p = PS.HISTORY
    if not os.path.isfile(p):
        pytest.skip("还没有历史文件")
    st = PS.build()
    before = len([l for l in io.open(p, encoding="utf-8") if l.strip()])
    added, after = PS.record(st, p)
    added2, after2 = PS.record(st, p)
    now = len([l for l in io.open(p, encoding="utf-8") if l.strip()])
    assert after2 == after, "第二次记录改变了行数：%d -> %d" % (after, after2)
    assert now in (before, before + 1), "行数异常：before=%d now=%d" % (before, now)
    assert not (added and added2), "同一快照被记了两次"


def test_fold_arithmetic_is_truthful():
    """折叠标记必须等于「总记录数 − 保留的真实记录数」（在临时文件上验）。

    这个数字很容易写错，而且错得很隐蔽：第一版把**被替换掉的旧标记行**也
    算进"折掉多少"，于是 12 条记录折叠后标记写成 14（比总数还多）。
    一个会说谎的计数，比不计数更糟 —— 读者会拿它当依据。
    """
    import tempfile

    tmp_root = os.environ.get("M2C_TMP")
    d = tempfile.mkdtemp(prefix="hist_",
                         dir=tmp_root if tmp_root and os.path.isdir(tmp_root) else None)
    old_max = PS.MAX_HISTORY
    try:
        PS.MAX_HISTORY = 5
        p = os.path.join(d, "h.jsonl")
        n = 30
        for i in range(n):
            PS.record({"head": "h%02d" % i, "phases": [], "figures": {},
                       "gx2_tests": i}, p)
        lines = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
        assert len(lines) <= 5, "折叠后仍超上界：%d 行" % len(lines)
        real = [l for l in lines if "folded" not in l]
        folded = [l["folded"] for l in lines if "folded" in l]
        assert len(folded) == 1, "折叠标记应恰好一个：%r" % folded
        assert folded[0] == n - len(real), \
            "折叠数不实：标记 %d，实际折掉 %d" % (folded[0], n - len(real))
        assert lines[0].get("head") == "h00", "首行（起点）不能丢"
        assert lines[-1].get("head") == "h%02d" % (n - 1), "末行必须是最新记录"
    finally:
        PS.MAX_HISTORY = old_max
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_rot_criterion_has_teeth():
    """**判据自己要有牙齿**：把 `MAX_LAG` 压到 0 必须让它红。

    没有这条，`test_main_figures_do_not_rot` 可能因为"恰好没有明显过期"而
    永远绿 —— 而它到底会不会在过期时报警，没人验证过。
    """
    import test_project_status as _self
    old = _self.MAX_LAG
    try:
        _self.MAX_LAG = 0
        with pytest.raises(AssertionError):
            _self.test_main_figures_do_not_rot()
    finally:
        _self.MAX_LAG = old
