# -*- coding: utf-8 -*-
"""matlabc flow —— AI 修复闭环编排器：把「改代码」变成一条可自证、可回退的流水线。

它解决三个痛点：
  1. 改完**不知道好没好** —— 每一步都有机器判据，不靠感觉；
  2. 改坏**不知道坏在哪** —— 未通过就回退到基线，绝不留半截改动；
  3. AI 改的代码**没人敢合** —— 落盘前先过「语句保持不变量」门，删了源码就拒绝应用。

一条流水线，五个站点（默认依次全走）：

    ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
    │ review  │──▶│   fix   │──▶│  apply  │──▶│ verify  │──▶│ report  │
    │ AI 审查 │   │ 生成补丁│   │ 应用补丁│   │ 重扫自证│   │ 汇总结论│
    └─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘
         │             │             │             │
         │             │             │             └─ 各规则告警数不得增加，且总量应下降
         │             │             └─ 默认「不落盘」；--auto-apply 才真应用
         │             └─ 只做确定性修复：未初始化 high / 死代码 /
         │                形状不匹配 / 重复代码重构脚手架
         └─ 离线回显提示词，在线给中文审查意见

安全底线（为什么可以放心让它动你的代码）：
  确定性补丁引擎只允许两种编辑算子 —— `del`（删行）与 `ins_before`（在某行前插入）。
  由此推出一条恒等式：**补丁删除的行数 == 报告里 dead_code 的条数**。
  一旦不等（历史上「插入」曾被实现成「覆盖目标行」，会悄悄吞掉源码语句），
  门就在**落盘之前**判红并拒绝应用，详情见本文件的 check_patch_preserves_source。

最小可跑示例（可直接复制）：
    python matlabc_flow.py ./myproj                       # 只出补丁与报告，不动你的代码
    python matlabc_flow.py ./myproj --dry-run             # 同上；配置里写了 auto_apply 也不落地
    python matlabc_flow.py ./myproj --auto-apply          # 真应用，并立刻重扫自证
    python matlabc_flow.py ./myproj --steps review,fix,report
    python matlabc_flow.py ./myproj --lang c --provider deepseek
    python matlabc_flow.py ./myproj --config ai_config.json --memory

进阶：让它自己迭代到收敛：
    python matlabc_flow.py ./myproj --auto-apply-loop --max-turns 3
    python matlabc_flow.py ./myproj --auto-apply-loop --review-gate
    python matlabc_flow.py ./myproj --auto-apply-loop --draft-pr
    python matlabc_flow.py ./myproj --auto-apply-loop --agent-plan -

  --auto-apply-loop 与 --auto-apply 的区别：前者是「修复→应用→验证→回退」的循环，
  带验证门控与回退重试；后者是线性单次管线。

退出码（写进 CI 的契约）：
    0  = 正常完成（含「只产出补丁、未落盘」）
    1  = 步骤执行中出错（stderr 会打 `[matlabc flow] 失败：...`）
    2  = 未通过自证 / 前置条件不满足 → 已回退，产出人工检查点（绝不自动提交）
    3  = 已通过自证，但 --review-gate 要求人工复核 → 未落地（产出审查产物给你看）

诚实边界：
  * fix 只做确定性修复。需要理解语义的改动（重命名、抽函数）它不做，只给草稿。
  * 闭环用 git 回退（无 git 时退回进程内快照）。**工作副本必须干净**，
    否则回退会把你的未提交改动一起带走。
  * review 步骤是否真出意见取决于 AI 配置；离线时只回显提示词，不会假装审查过。
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile

from matlabc_ask import normalize


# --------------------------------------------------------------------------
# D-P0-1 护栏：确定性补丁的「语句保持不变量」
#
# 设计契约（见 matlabc._build_apply_patch docstring）：「安全、可验证、不丢数据」。
# 由此可推出一个**恒等式**：
#     补丁删除的行数 == 报告里 dead_code 的条数
# 因为唯一被允许的删除来源就是 dead_code（其余动作用 ins_before 纯插入）。
# 历史上「插入」曾被实现为「覆盖目标行」，于是删除行数 = dead + 插入数，
# 而 verify 门只比对告警条数（1 → 0）仍然报 PASS —— 源码语句被删而无人知。
# 本装置把那句恒等式变成可求值判据，使自证门**能够说「不」**。
# --------------------------------------------------------------------------
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def patch_edit_counts(patch_text):
    """解析 unified diff，返回 (removed, added, hunks)。

    按 `@@ -a,b +c,d @@` 声明的行数逐个消费 hunk 主体，因此
    `--- a/f` / `+++ b/f` 文件头、`\\ No newline`、以及 hunk 之外的非 diff
    文本（dup_code 重构脚手架）都不会被误计。
    """
    removed = added = hunks = 0
    expect_old = expect_new = 0
    for raw in (patch_text or "").splitlines():
        m = _HUNK_RE.match(raw)
        if m:
            hunks += 1
            expect_old = int(m.group(2) or 1)
            expect_new = int(m.group(4) or 1)
            continue
        if expect_old <= 0 and expect_new <= 0:
            continue                       # hunk 之外
        if raw.startswith("\\"):           # \ No newline at end of file
            continue
        if raw.startswith("+"):
            added += 1
            expect_new -= 1
        elif raw.startswith("-"):
            removed += 1
            expect_old -= 1
        else:                              # ' ' 上下文行
            expect_old -= 1
            expect_new -= 1
    return removed, added, hunks


def check_patch_preserves_source(patch_text, before_alerts):
    """确定性补丁安全不变量。返回 (ok, detail)。

    ok=False 表示**不得应用**：补丁会删除报告未声明的源码语句。
    判定必须发生在落盘**之前**（本函数是纯函数，不碰文件系统）。
    """
    removed, added, hunks = patch_edit_counts(patch_text)
    allowed = sum(1 for a in (before_alerts or [])
                  if isinstance(a, dict) and a.get("rule") == "dead_code")
    detail = {"removed": removed, "added": added, "hunks": hunks,
              "allowed_removals": allowed}
    if (patch_text or "").strip() and hunks == 0:
        return False, dict(detail,
                           reason="补丁非空却解析不出任何 hunk（无法自证 → 拒绝应用）")
    if removed != allowed:
        return False, dict(detail, reason=(
            "语句保持不变量被破坏：补丁删除 %d 行，而报告只声明 %d 条 dead_code"
            "（多删的 %d 行 = 源码语句被『覆盖式插入』吞掉）"
            % (removed, allowed, removed - allowed)))
    return True, detail


def _here():
    return os.path.dirname(os.path.abspath(__file__))


def _analyzer_target():
    if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
        return [sys.executable]
    return [sys.executable, os.path.join(_here(), "matlabc.py")]


def _run(cmd, quiet=True):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # R62-R31e 子进程卫生：切 stdin + 墙钟超时（子进程是本仓 matlabc.py）。
    r = subprocess.run(cmd, stdout=subprocess.PIPE if quiet else None,
                       stderr=subprocess.STDOUT if quiet else None,
                       stdin=subprocess.DEVNULL, timeout=900,
                       universal_newlines=True, encoding="utf-8", errors="replace",
                       env=env)
    return r


def analyze(directory, lang=None):
    """跑一次分析，返回报告 JSON 路径。"""
    tmp = tempfile.NamedTemporaryFile(prefix="mc_flow_", suffix=".json", delete=False)
    tmp.close()
    cmd = _analyzer_target() + [directory, "--json", tmp.name, "--ai-mode", "off"]
    if lang:
        cmd += ["--lang", lang]
    r = _run(cmd)
    if r.returncode != 0:
        sys.stderr.write("[matlabc flow] 分析失败（rc=%d）：\n%s\n"
                         % (r.returncode, (r.stdout or "")[:800]))
        raise RuntimeError("分析子进程失败")
    return tmp.name


def count_alerts(report_path):
    rep = json.load(io.open(report_path, "r", encoding="utf-8-sig"))
    _, _, alerts, _, _, _ = normalize(rep)
    by_rule = {}
    for a in alerts:
        by_rule[a["rule"]] = by_rule.get(a["rule"], 0) + 1
    return by_rule, len(alerts)


def load_alerts(report_path):
    """返回报告里的原始告警列表（供记忆抑制逐条过滤，保留 rel/line 等元数据）。"""
    rep = json.load(io.open(report_path, "r", encoding="utf-8-sig"))
    _, _, alerts, _, _, _ = normalize(rep)
    return alerts


def apply_memory(project_root, alerts):
    """若工程有记忆文件，则过滤掉已知误报；返回 (保留, 被抑制)。

    无记忆文件则原样返回（默认不影响既有行为）。
    """
    p = os.path.join(project_root, ".codebuddy", "analyzer", "memory.json")
    if not os.path.exists(p):
        return list(alerts), []
    try:
        import analyzer_memory as am
        mem = am.load_memory(project_root)
        return am.suppress_alerts(alerts, mem)
    except Exception:
        return list(alerts), []


def _tally(alerts):
    by_rule = {}
    for a in alerts:
        by_rule[a["rule"]] = by_rule.get(a["rule"], 0) + 1
    return by_rule, len(alerts)


def gen_patch(directory, prefix, lang=None):
    """生成确定性补丁，返回补丁文本（无则空串）。"""
    cmd = _analyzer_target() + [directory, "--gen-apply-patch", prefix, "--ai-mode", "off"]
    if lang:
        cmd += ["--lang", lang]
    _run(cmd)
    patch_path = prefix + ".git.patch"
    if os.path.exists(patch_path):
        return io.open(patch_path, "r", encoding="utf-8").read()
    return ""


def load_flow_config(config_path):
    steps = ["review", "fix", "apply", "verify", "report"]
    auto_apply = False
    if config_path and os.path.exists(config_path):
        try:
            cfg = json.load(io.open(config_path, "r", encoding="utf-8-sig"))
            flow = cfg.get("flow") or {}
            if flow.get("steps"):
                steps = list(flow["steps"])
            auto_apply = bool(flow.get("auto_apply", False))
        except Exception as e:
            sys.stderr.write("[matlabc flow] 读取配置失败，用默认：%s\n" % e)
    return steps, auto_apply


def run_flow(directory, config_path=None, auto_apply=False, dry_run=False,
             steps=None, lang=None, provider=None, use_memory=False):
    steps, cfg_auto = load_flow_config(config_path)
    if steps:
        steps = [s.strip().lower() for s in steps]
    else:
        steps = ["review", "fix", "apply", "verify", "report"]
    do_apply = auto_apply or (cfg_auto and not dry_run)
    if dry_run:
        do_apply = False

    print("=" * 64)
    print("[matlabc flow] 工程：%s" % os.path.abspath(directory))
    print("[matlabc flow] 步骤：%s" % " → ".join(steps))
    print("[matlabc flow] auto_apply=%s（--auto-apply 强制开，--dry-run 强制关）"
          % do_apply)
    print("=" * 64)

    rep_before = analyze(directory, lang)
    by_before, total_before = count_alerts(rep_before)
    _before_alerts = load_alerts(rep_before)
    supp_before = 0
    if use_memory:
        kept, supp = apply_memory(directory, load_alerts(rep_before))
        by_before, total_before = _tally(kept)
        supp_before = len(supp)
    print("[snapshot] 修复前告警：共 %d 条  %s"
          % (total_before, _fmt_rules(by_before)))
    if use_memory and supp_before:
        print("[snapshot] 已按项目记忆抑制 %d 条已知误报" % supp_before)

    patch_text = ""
    applied = False
    touched = []
    by_after, total_after = by_before, total_before

    for step in steps:
        if step == "review":
            print("\n--- step: review（AI 审查，离线回显提示词）---")
            import ai_cli
            cli_argv = ["--prompt-file", rep_before, "--task", "review"]
            if provider:
                cli_argv += ["--provider", provider]
            ai_cli.main(cli_argv)
        elif step == "fix":
            print("\n--- step: fix（确定性补丁引擎）---")
            pf = tempfile.NamedTemporaryFile(prefix="mc_flow_patch_", delete=False)
            pf.close()
            patch_text = gen_patch(directory, pf.name, lang)
            if patch_text:
                print("[fix] 已生成确定性补丁 %d 字节" % len(patch_text.encode("utf-8")))
            else:
                print("[fix] 无确定性可自动修复项（未初始化 high / 死代码 / "
                      "形状不匹配 / 重复重构），详见 --gen-pr 草稿。")
        elif step == "apply":
            print("\n--- step: apply（git apply 优先，回退严格进程内校验）---")
            if patch_text:
                _safe, _det = check_patch_preserves_source(patch_text,
                                                           _before_alerts)
                print("[apply] 语句保持不变量：删除 %s 行 / 新增 %s 行（hunk %s），"
                      "报告声明允许删除 %s 行 → %s"
                      % (_det.get("removed"), _det.get("added"), _det.get("hunks"),
                         _det.get("allowed_removals"),
                         "通过" if _safe else "不通过"))
                if not _safe:
                    print("[apply] 拒绝应用（未改动任何文件）：%s" % _det.get("reason"))
                    return 2
            if patch_text and do_apply:
                import matlabc
                # 优先 git apply（与 --gen-apply-patch「git apply 适用」设计一致，
                # 容忍 hunk 行号 fuzz）；无 git 时退回进程内严格校验。
                patch_file = tempfile.NamedTemporaryFile(
                    prefix="mc_flow_apply_", suffix=".git.patch",
                    delete=False, mode="w", encoding="utf-8")
                patch_file.write(patch_text)
                patch_file.close()
                try:
                    # R62-R31e：git 子进程同样切 stdin + 超时。
                    g = subprocess.run(["git", "apply", "--check", patch_file.name],
                                       cwd=directory, capture_output=True, text=True,
                                       stdin=subprocess.DEVNULL, timeout=60)
                    if g.returncode == 0:
                        subprocess.run(["git", "apply", patch_file.name],
                                       cwd=directory, check=True,
                                       capture_output=True, text=True,
                                       stdin=subprocess.DEVNULL, timeout=60)
                        applied = True
                        print("[apply] 已通过 git apply 应用补丁。")
                    else:
                        raise ValueError(g.stderr.strip() or "git apply --check 失败")
                except (OSError, ValueError, subprocess.CalledProcessError) as e:
                    # 回退：进程内严格校验应用（任一 hunk 不符即拒绝）
                    try:
                        touched = matlabc._apply_unified_patch_text(
                            patch_text, directory)
                        applied = True
                        print("[apply] 已通过进程内严格校验应用，改动 %d 文件：%s"
                              % (len(touched), ", ".join(touched)))
                    except ValueError as e2:
                        print("[apply] 应用被拒绝（补丁与工作副本不符，未改动任何文件）：%s"
                              % e2)
            else:
                print("[apply] 未应用（auto_apply=%s）：补丁仅产出，"
                      "使用 --auto-apply 才会落盘。" % do_apply)
        elif step == "verify":
            print("\n--- step: verify（重扫自证）---")
            if applied:
                rep_after = analyze(directory, lang)
                by_after, total_after = count_alerts(rep_after)
                delta = {r: by_after.get(r, 0) - by_before.get(r, 0)
                         for r in set(by_before) | set(by_after)}
                ok = all(v <= 0 for v in delta.values())
                print("[verify] 修复后告警：共 %d 条  %s"
                      % (total_after, _fmt_rules(by_after)))
                print("[verify] 各规则增量：%s" % _fmt_rules(delta))
                print("[verify] 自证结果：%s（无新增告警且总量%s）"
                      % ("通过(PASS)" if ok else "不通过(FAIL)",
                         "下降" if total_after < total_before else
                         "未下降" if total_after == total_before else "上升"))
            else:
                print("[verify] 跳过（未应用补丁）。")
        elif step == "report":
            print("\n--- step: report（结论）---")
            print("  修复前告警：%d  %s" % (total_before, _fmt_rules(by_before)))
            print("  修复后告警：%d  %s" % (total_after, _fmt_rules(by_after)))
            print("  应用补丁：%s" % ("是" if applied else "否（仅产出）"))
            print("  自证标准：重扫后各规则告警数不增加。")
            if use_memory and supp_before:
                print("  项目记忆：已抑制 %d 条已知误报（不计入上述统计）"
                      % supp_before)
        else:
            print("\n[warn] 未知步骤跳过：%s" % step)

    print("\n" + "=" * 64)
    print("[matlabc flow] 完成。")
    print("=" * 64)
    return 0


def _feedback_suffix(feedback):
    """把验证反馈渲染成追加到 LLM 提示词的引导（含被拒补丁 + 具体拒绝原因）。"""
    fb = feedback or {}
    by = fb.get("by_after") or {}
    delta = fb.get("delta") or {}
    parts = ["# 修复反馈（上一轮自证结果）"]
    reason = fb.get("reason")
    detail = fb.get("detail")
    if reason == "apply_failed":
        parts.append("上一轮补丁应用失败（无法安全落盘）：%s" % (detail or ""))
    elif reason == "apply_rejected":
        parts.append("上一轮补丁被工作副本拒绝（hunk 上下文不匹配 / 无法应用）：%s"
                     % (detail or ""))
    elif reason == "verification_failed":
        parts.append("上一轮补丁应用后自证未通过：")
        if not fb.get("no_new_alerts"):
            bad = {k: v for k, v in delta.items() if v > 0}
            parts.append("  · 新增 / 上升告警：%s" % (_fmt_rules(bad) if bad else "无"))
        if not fb.get("progress"):
            parts.append("  · 告警总量未下降（基线 %s → 终态 %s）"
                         % (fb.get("total_before"), fb.get("total_after")))
        if by:
            parts.append("  · 终态各规则：%s" % _fmt_rules(by))
    else:
        parts.append("上一轮终态告警 %d 条，各规则：%s"
                     % (fb.get("total_after", 0), _fmt_rules(by)))
    rejected = fb.get("rejected_patch")
    if rejected:
        parts.append("\n# 上一轮被拒补丁（请勿重复同样错误，针对上述问题修正）\n"
                     "```diff\n%s\n```" % rejected)
    parts.append("\n请仅针对「仍未消除（或被新增）」的告警生成最小化 unified diff 修复，"
                 "不要改动无关代码；用 ```diff ... ``` 包裹输出。")
    return "\n".join(parts)


def gen_llm_patch(directory, feedback, provider, lang=None, config_path=None):
    """用 LLM 针对「验证后剩余 / 新增告警」生成修复补丁（unified diff）。

    反馈驱动：把上一轮验证的剩余告警 / 增量事实追加进提示词，引导模型聚焦。
    离线或无密钥（provider 降级 offline）时返回 None，不浪费轮次。
    始终对当前工作副本重扫得到最新报告，保证 LLM 看到的是回退后的真实状态。
    """
    try:
        import ai_cli
    except ImportError:
        return None
    ai_cfg = ai_cli.load_ai_config(config_path) if config_path else {}
    prov, eff_name, warn = ai_cli.resolve_provider_auto(provider, ai_cfg)
    if eff_name == "offline":
        sys.stderr.write("[matlabc flow] LLM 修复降级 offline（无可用密钥），跳过本轮。\n")
        return None
    if warn:
        sys.stderr.write("[matlabc flow] %s\n" % warn)

    # 始终基于当前工作副本重扫，得到最新告警事实（回退后 = 基线）
    report_path = None
    try:
        report_path = analyze(directory, lang)
    except Exception:
        report_path = None
    if not report_path and isinstance(feedback, dict):
        report_path = feedback.get("report_path")
    if not report_path:
        return None

    analysis = ai_cli.load_analysis(report_path)
    tp = ai_cli.task_params("fix", ai_cfg)
    system, user = ai_cli.build_messages(analysis, "fix", tp)
    if isinstance(feedback, dict):
        user = user + "\n\n" + _feedback_suffix(feedback)
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    try:
        resp = prov.complete(messages, model=tp.get("model"),
                             max_tokens=tp.get("max_tokens") or 2048,
                             temperature=(tp.get("temperature")
                                          if tp.get("temperature") is not None
                                          else 0.2))
    except RuntimeError as e:
        sys.stderr.write("[matlabc flow] LLM 调用失败：%s\n" % e)
        return None
    return ai_cli.parse_unified_diff(resp) or None


def _loop_fix_source(directory, prefix, lang, provider, config_path=None):
    """环的修复源（多策略 + 反馈驱动 LLM 迭代）：

      * 0 轮：先试确定性补丁引擎（与 fix 步骤一致）；
          若确定性无解且配置了 provider，则直接走 LLM（不浪费一轮）。
      * 后续轮次：确定性已用尽，靠「带 feedback 的 LLM 修复」在 max_turns
          内自主迭代；无 provider 则返回 None 终止（不浪费轮次）。
    """
    def _src(attempt, feedback):
        if attempt == 0:
            p = gen_patch(directory, prefix, lang)
            if p:
                return p
            if provider:
                return gen_llm_patch(directory, feedback, provider, lang, config_path)
            return None
        if provider:
            return gen_llm_patch(directory, feedback, provider, lang, config_path)
        return None
    return _src


def run_flow_loop(directory, config_path=None, max_turns=3, lang=None,
                  provider=None, agent_plan=None, use_memory=False,
                  review_gate=False, review_dir=None, draft_pr=False):
    """P0-1：受控自校验 Agent Loop（验证门控 + 回退重试 + 人工检查点 + 跨运行记忆 + 复核门）。

    区别于 run_flow 的线性单次管线：本函数把修复放进 agent_loop.run_fix_loop，
    应用后确定性重扫验证；未通过则回退并换策略重试，穷尽 max_turns 仍未通过则
    产出人工检查点（不自动提交，绝不无限循环）。

    use_memory：开启项目记忆（.codebuddy/analyzer/memory.json）——分析时抑制已知误报，
        且闭环收敛后把已验证修复记入 learned_fixes，下次同分布告警可被检索复用。
    review_gate（--review-gate）：验证通过后不自动落地，回退工作副本并改出审查产物，
        交人工复核后再落地（exit 3 = 已验证但待复核）。
    draft_pr（--draft-pr）：tier-2 检查点 / 复核产物额外尝试经 gh 开 Draft PR；
        gh 缺失或非 GitHub 远程时优雅降级为本地产物。
    agent_plan：若给定路径，额外把结构化闭环计划（每轮决策 + 终止原因 + 分层
        退出 + 记忆状态 + 复核状态）写 JSON，供 AI Agent 程序化消费；传 "-" 则打印到 stdout。
    """
    # 惰性导入，避免与 agent_loop 的 `from matlabc_flow import ...` 形成循环依赖
    from agent_loop import run_fix_loop as _run_loop, summarize_loop

    print("=" * 64)
    print("[matlabc flow --auto-apply-loop] 工程：%s"
          % os.path.abspath(directory))
    print("[matlabc flow --auto-apply-loop] max_turns=%d  use_memory=%s  "
          "review_gate=%s  draft_pr=%s"
          % (max_turns, use_memory, review_gate, draft_pr))
    print("=" * 64)

    pf = tempfile.NamedTemporaryFile(prefix="mc_loop_patch_", delete=False)
    pf.close()
    fix_source = _loop_fix_source(directory, pf.name, lang, provider, config_path)
    state_path = None
    if agent_plan and agent_plan != "-":
        state_path = agent_plan
    result = _run_loop(directory, fix_source, max_turns=max_turns,
                       lang=lang, state_path=state_path,
                       project_root=os.path.abspath(directory),
                       use_memory=use_memory,
                       review_gate=review_gate, review_dir=review_dir,
                       draft_pr=draft_pr)
    print(summarize_loop(result))
    # 注意：checkpoint / final_total 嵌套在 result["result"] 下
    _res = result.get("result", {})
    if _res.get("checkpoint"):
        cp = _res["checkpoint"]
        print("[checkpoint] %s" % cp["message"])
        print("[checkpoint] 候选补丁字节数：%s" % cp.get("candidate_patch_bytes"))
        art = cp.get("artifact") or {}
        if art.get("patch_path"):
            print("[checkpoint] 审查产物：%s" % art["patch_path"])
        dpr = cp.get("draft_pr")
        if dpr:
            print("[Draft PR] %s：%s" % (dpr.get("ok"), dpr.get("message")))
    elif _res.get("review_pending"):
        print("[matlabc flow --auto-apply-loop] 终态告警：%d（已验证，待人工复核）"
              % _res.get("final_total", result.get("baseline", {}).get("total", 0)))
    else:
        print("[matlabc flow --auto-apply-loop] 终态告警：%d（已保留修复）"
              % _res.get("final_total", result.get("baseline", {}).get("total", 0)))
    if use_memory:
        if _res.get("learned_fix_available"):
            print("[记忆] 检测到与当前基线同分布的「已学习修复」，可复用历史补丁。")
        if _res.get("learned_fix_recorded"):
            print("[记忆] 已把本次已验证修复记入项目记忆（learned_fixes）。")

    # --agent-plan 落到 stdout（供 Agent 管道捕获）
    if agent_plan == "-":
        print("\n[agent plan JSON]\n" + json.dumps(result, ensure_ascii=False,
                                                   indent=2, sort_keys=True))

    # 0 = 接受并保留修复；2 = 未通过自证(已回退基线)；3 = 已验证但待人工复核(未落地)
    return result.get("exit_code", 0 if _res.get("accepted") else 2)


def _fmt_rules(d):
    if not d:
        return "{}"
    return "{" + ", ".join("%s:%s" % (k, v) for k, v in sorted(d.items())) + "}"


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="matlabc flow",
        description="AI 修复闭环编排器（review→fix→apply→verify→report）。")
    ap.add_argument("directory", help="待分析/修复的工程目录")
    ap.add_argument("--config", default=None, help="ai_config.json 路径（读 flow 字段）")
    ap.add_argument("--auto-apply", action="store_true",
                    help="应用确定性补丁（默认不落盘，仅产出）")
    ap.add_argument("--dry-run", action="store_true",
                    help="即便配置 auto_apply，也不应用补丁")
    ap.add_argument("--steps", default=None,
                    help="覆盖步骤，逗号分隔，如 review,fix,report")
    ap.add_argument("--lang", default=None, help="透传 --lang（matlab/c/py/js）")
    ap.add_argument("--provider", default=None, help="review 步骤的 AI 供应商")
    ap.add_argument("--auto-apply-loop", action="store_true",
                    help="受控自校验修复环（验证门控+回退重试+人工检查点），"
                         "区别于 --auto-apply 的线性单次管线")
    ap.add_argument("--review-gate", action="store_true",
                    help="仅与 --auto-apply-loop 联用：验证通过后不自动落地，"
                         "回退工作副本并改出审查产物（patch+json+md），交人工复核后再落地（exit 3）")
    ap.add_argument("--draft-pr", action="store_true",
                    help="仅与 --auto-apply-loop 联用：tier-2 检查点/复核产物额外尝试经 gh 开 Draft PR；"
                         "gh 缺失或非 GitHub 远程时优雅降级为本地产物")
    ap.add_argument("--max-turns", type=int, default=3,
                    help="修复环最大尝试轮数（分层终止上限，默认 3）")
    ap.add_argument("--agent-plan", default=None, metavar="PATH",
                    help="把结构化闭环计划写 JSON：传路径写文件，传 - 打印到 stdout，"
                         "供 AI Agent 程序化消费（含每轮决策/终止原因/分层退出）")
    ap.add_argument("--memory", action="store_true",
                    help="启用项目记忆（.codebuddy/analyzer/memory.json）：分析时抑制已知误报，"
                         "且闭环收敛后把已验证修复记入 learned_fixes，下次同分布告警可复用")
    args = ap.parse_args(argv)

    if args.auto_apply_loop:
        try:
            return run_flow_loop(args.directory, config_path=args.config,
                                max_turns=args.max_turns, lang=args.lang,
                                provider=args.provider,
                                agent_plan=args.agent_plan,
                                use_memory=args.memory,
                                review_gate=args.review_gate,
                                draft_pr=args.draft_pr)
        except Exception as e:
            sys.stderr.write("[matlabc flow --auto-apply-loop] 失败：%s\n" % e)
            return 1

    steps = args.steps.split(",") if args.steps else None
    try:
        return run_flow(args.directory, config_path=args.config,
                        auto_apply=args.auto_apply, dry_run=args.dry_run,
                        steps=steps, lang=args.lang, provider=args.provider,
                        use_memory=args.memory)
    except Exception as e:
        sys.stderr.write("[matlabc flow] 失败：%s\n" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
