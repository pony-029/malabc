# -*- coding: utf-8 -*-
"""matlabc flow —— AI 修复闭环编排器（P1）。

把 ai_config.schema.json 里「已声明但未驱动」的 flow.steps 真正串起来：
  review → fix → apply → verify → report

设计：
  * fix 步骤复用 matlabc 的【确定性】补丁引擎（--gen-apply-patch → 真实 git-apply
    补丁：未初始化 high / 死代码 / 形状不匹配 / 重复代码重构脚手架），安全且可自证。
  * apply 步骤默认【不落盘】（auto_apply=false），仅 --auto-apply 才进程内应用
    （严格语义校验，原子性，任一 hunk 不符即拒绝）。
  * verify 步骤：应用后重扫，以「各规则告警数不增加（且应减少）」为自证标准。
  * review 步骤：调用 ai_cli task=review（离线回显提示词，在线给审查意见）。

用法：
  matlabc flow ./myproj                         # 仅生成补丁 + 报告（不应用）
  matlabc flow ./myproj --auto-apply            # 应用确定性补丁并自证
  matlabc flow ./myproj --steps review,fix,report
  matlabc flow ./myproj --config ai_config.json --provider deepseek
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile

from matlabc_ask import normalize


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
    r = subprocess.run(cmd, stdout=subprocess.PIPE if quiet else None,
                       stderr=subprocess.STDOUT if quiet else None,
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
                    g = subprocess.run(["git", "apply", "--check", patch_file.name],
                                       cwd=directory, capture_output=True, text=True)
                    if g.returncode == 0:
                        subprocess.run(["git", "apply", patch_file.name],
                                       cwd=directory, check=True,
                                       capture_output=True, text=True)
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


def _loop_fix_source(directory, prefix, lang, provider):
    """环的修复源：0 轮用确定性补丁引擎（与 fix 步骤一致）；

    后续轮次若配置了 provider，可在此接入「带 feedback 的 LLM 修复」（待实现）；
    当前仅确定性引擎，重跑无新策略 → 返回 None 终止（不浪费轮次）。
    """
    def _src(attempt, feedback):
        if attempt == 0:
            p = gen_patch(directory, prefix, lang)
            return p or None
        return None
    return _src


def run_flow_loop(directory, config_path=None, max_turns=3, lang=None,
                  provider=None, agent_plan=None):
    """P0-1：受控自校验 Agent Loop（验证门控 + 回退重试 + 人工检查点）。

    区别于 run_flow 的线性单次管线：本函数把修复放进 agent_loop.run_fix_loop，
    应用后确定性重扫验证；未通过则回退并换策略重试，穷尽 max_turns 仍未通过则
    产出人工检查点（不自动提交，绝不无限循环）。

    agent_plan：若给定路径，额外把结构化闭环计划（每轮决策 + 终止原因 + 分层
    退出）写 JSON，供 AI Agent 程序化消费；传 "-" 则打印到 stdout。
    """
    # 惰性导入，避免与 agent_loop 的 `from matlabc_flow import ...` 形成循环依赖
    from agent_loop import run_fix_loop as _run_loop, summarize_loop

    print("=" * 64)
    print("[matlabc flow --auto-apply-loop] 工程：%s"
          % os.path.abspath(directory))
    print("[matlabc flow --auto-apply-loop] max_turns=%d" % max_turns)
    print("=" * 64)

    pf = tempfile.NamedTemporaryFile(prefix="mc_loop_patch_", delete=False)
    pf.close()
    fix_source = _loop_fix_source(directory, pf.name, lang, provider)
    state_path = None
    if agent_plan and agent_plan != "-":
        state_path = agent_plan
    result = _run_loop(directory, fix_source, max_turns=max_turns,
                       lang=lang, state_path=state_path,
                       project_root=os.path.abspath(directory))
    print(summarize_loop(result))
    # 注意：checkpoint / final_total 嵌套在 result["result"] 下
    _res = result.get("result", {})
    if _res.get("checkpoint"):
        cp = _res["checkpoint"]
        print("[checkpoint] %s" % cp["message"])
        print("[checkpoint] 候选补丁字节数：%s" % cp.get("candidate_patch_bytes"))
    else:
        print("[matlabc flow --auto-apply-loop] 终态告警：%d（已保留修复）"
              % _res.get("final_total", result.get("baseline", {}).get("total", 0)))

    # --agent-plan 落到 stdout（供 Agent 管道捕获）
    if agent_plan == "-":
        print("\n[agent plan JSON]\n" + json.dumps(result, ensure_ascii=False,
                                                   indent=2, sort_keys=True))

    # 0 = 接受并保留修复；2 = 未通过自证(已回退基线，供 CI 区分)
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
    ap.add_argument("--max-turns", type=int, default=3,
                    help="修复环最大尝试轮数（分层终止上限，默认 3）")
    ap.add_argument("--agent-plan", default=None, metavar="PATH",
                    help="把结构化闭环计划写 JSON：传路径写文件，传 - 打印到 stdout，"
                         "供 AI Agent 程序化消费（含每轮决策/终止原因/分层退出）")
    ap.add_argument("--memory", action="store_true",
                    help="启用项目记忆：按 .codebuddy/analyzer/memory.json 抑制已知误报")
    args = ap.parse_args(argv)

    if args.auto_apply_loop:
        try:
            return run_flow_loop(args.directory, config_path=args.config,
                                max_turns=args.max_turns, lang=args.lang,
                                provider=args.provider,
                                agent_plan=args.agent_plan)
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
