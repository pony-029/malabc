# -*- coding: utf-8 -*-
"""agent_loop —— 受控自校验 Agent Loop（P0：matlabc_flow 自主修复闭环核心）。

把「修复 → 应用 → 验证 → 回退」放进一个带门控与终止条件的自主循环：

  * 修复源(fix_source)：callable(attempt, feedback) -> patch_text | None
      - attempt：第几轮（从 0 起）；feedback：上一轮验证失败的原因摘要。
      - 返回 unified diff 文本；返回 None 表示已无新策略 → 循环终止。
  * 验证门控(verifier)：应用后确定性重扫，要求「各规则告警数不增加（安全）」
        且「总量下降（有进展）」，二者皆满足才接受本轮修复。
  * 回退：验证不通过则按 git apply -R（有 git）或进程内快照（无 git）回滚，
        工作副本回到基线，绝不留下半截改动。
  * 终止条件：accepted（收敛）| max_turns 用尽 | 修复源返回 None（无策略）。
  * 分层退出(tier)：
      - 0：接受且终态 0 告警（完全干净）；
      - 1：接受但仍有残留告警（安全降级，部分改善）；
      - 2：未通过自证 → 产出人工检查点（绝不自动提交 / 无限循环）。
"""
from __future__ import absolute_import, division, print_function

import io
import json
import os
import subprocess
import tempfile


def _is_git_repo(directory):
    return os.path.isdir(os.path.join(directory, ".git"))


def _patch_targets(patch_text):
    """解析 unified diff 的 --- a/.. 行，返回受影响文件的相对路径列表。"""
    targets = []
    for line in (patch_text or "").split("\n"):
        if line.startswith("--- "):
            a = line[4:].strip()
            if a == "/dev/null":
                continue
            rel = a[2:] if a.startswith("a/") else a
            if rel:
                targets.append(rel)
    return targets


def _apply_with_git(patch_text, directory):
    """git apply（容忍行号 fuzz）；成功返回 True，否则 False（不改动工作副本）。"""
    pf = tempfile.NamedTemporaryFile(
        prefix="agent_loop_", suffix=".git.patch", delete=False,
        mode="w", encoding="utf-8")
    try:
        pf.write(patch_text)
        pf.close()
        chk = subprocess.run(["git", "apply", "--check", pf.name],
                             cwd=directory, capture_output=True, text=True)
        if chk.returncode != 0:
            return False
        ap = subprocess.run(["git", "apply", pf.name], cwd=directory,
                            capture_output=True, text=True)
        return ap.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        try:
            os.remove(pf.name)
        except OSError:
            pass


def _revert_with_git(patch_text, directory):
    pf = tempfile.NamedTemporaryFile(
        prefix="agent_loop_rev_", suffix=".git.patch", delete=False,
        mode="w", encoding="utf-8")
    try:
        pf.write(patch_text)
        pf.close()
        subprocess.run(["git", "apply", "-R", pf.name], cwd=directory,
                       capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError):
        pass
    finally:
        try:
            os.remove(pf.name)
        except OSError:
            pass


def _apply_internal(patch_text, directory):
    """无 git 时进程内严格校验应用，返回快照（用于回退）。"""
    import matlabc
    snapshot = {}
    for rel in _patch_targets(patch_text):
        p = os.path.join(directory, rel)
        if os.path.exists(p):
            with io.open(p, "rb") as fh:
                snapshot[rel] = fh.read()
    matlabc._apply_unified_patch_text(patch_text, directory)
    return snapshot


def _revert_internal(snapshot, directory):
    for rel, data in snapshot.items():
        p = os.path.join(directory, rel)
        with io.open(p, "wb") as fh:
            fh.write(data)


def _delta(by_before, by_after):
    return {r: by_after.get(r, 0) - by_before.get(r, 0)
            for r in set(by_before) | set(by_after)}


def _strategy_name(fix_source):
    return getattr(fix_source, "__name__", "fix_source") or "fix_source"


def run_fix_loop(directory, fix_source, max_turns=3, lang=None,
                 state_path=None, project_root=None):
    """受控自校验修复环。返回结构化结果 dict（含 turns / termination / result）。

    接口约定（供 matlabc_flow.run_flow_loop 调用）：
      fix_source(attempt, feedback) -> patch_text | None
    结果 dict 关键键：accepted / final_total / result.tier / result.checkpoint /
                       termination.reason / exit_code。
    """
    from matlabc_flow import analyze, count_alerts

    use_git = _is_git_repo(directory)
    baseline_path = analyze(directory, lang)
    by_before, total_before = count_alerts(baseline_path)

    turns = []
    accepted = False
    final_total = total_before
    final_by = dict(by_before)
    feedback = ""
    last_candidate = None
    termination = None

    # 基线已干净：直接收敛，无需任何轮次
    if total_before == 0:
        accepted = True
        termination = {"reason": "already_clean", "turns_used": 0}
    else:
        for attempt in range(max_turns):
            patch = fix_source(attempt, feedback)
            if patch is None:
                termination = {"reason": "no_strategy", "turns_used": attempt}
                break
            last_candidate = patch
            patch_bytes = len(patch.encode("utf-8"))
            snapshot = None
            applied_ok = False
            try:
                if use_git:
                    applied_ok = _apply_with_git(patch, directory)
                else:
                    snapshot = _apply_internal(patch, directory)
                    applied_ok = True
            except Exception as e:  # noqa: BLE001 - 应用异常当作本轮失败，继续回退
                turns.append({
                    "attempt": attempt, "strategy": _strategy_name(fix_source),
                    "patch_bytes": patch_bytes, "applied": False,
                    "verdict": "apply_failed",
                    "feedback": "apply_failed: %s" % e,
                })
                feedback = "apply_failed: %s" % e
                continue

            if not applied_ok:
                turns.append({
                    "attempt": attempt, "strategy": _strategy_name(fix_source),
                    "patch_bytes": patch_bytes, "applied": False,
                    "verdict": "apply_rejected",
                    "feedback": "patch_not_applicable_to_working_tree",
                })
                feedback = "patch_not_applicable_to_working_tree"
                continue

            # 验证：应用后确定性重扫
            rep_after = analyze(directory, lang)
            by_after, total_after = count_alerts(rep_after)
            d = _delta(by_before, by_after)
            no_new = all(v <= 0 for v in d.values())
            progress = total_after < total_before
            ok = no_new and progress
            turns.append({
                "attempt": attempt, "strategy": _strategy_name(fix_source),
                "patch_bytes": patch_bytes, "applied": True,
                "verified": {
                    "total": total_after, "by_rule": by_after, "delta": d,
                    "no_new_alerts": no_new, "progress": progress,
                },
                "verdict": "accept" if ok else "revert",
            })
            if ok:
                accepted = True
                final_total = total_after
                final_by = dict(by_after)
                termination = {"reason": "converged", "turns_used": attempt + 1}
                break
            # 回退到基线（验证不通过，绝不保留半截改动）
            if use_git:
                _revert_with_git(patch, directory)
            else:
                _revert_internal(snapshot, directory)
            feedback = ("verification_failed: no_new=%s progress=%s delta=%s"
                        % (no_new, progress, d))

        if termination is None:
            termination = {"reason": "max_turns", "turns_used": max_turns}

    if accepted:
        tier = 0 if final_total == 0 else 1
        checkpoint = None
        exit_code = 0
    else:
        tier = 2
        checkpoint = {
            "message": ("未通过自证（%s）：修复后仍有新增 / 未减少告警，"
                         "已回退基线，请人工复核候选补丁。"
                         % termination["reason"]),
            "candidate_patch_bytes": (len(last_candidate.encode("utf-8"))
                                      if last_candidate else 0),
            "has_candidate": last_candidate is not None,
        }
        exit_code = 2

    result = {
        "tool": "matlabc_flow",
        "mode": "autonomous_agent_loop",
        "project": os.path.abspath(directory),
        "project_root": (os.path.abspath(project_root)
                         if project_root else os.path.abspath(directory)),
        "lang": lang,
        "max_turns": max_turns,
        "used_git": use_git,
        "baseline": {"total": total_before, "by_rule": by_before},
        "turns": turns,
        "termination": termination,
        "result": {
            "accepted": accepted,
            "final_total": final_total,
            "final_by_rule": final_by,
            "tier": tier,
            "checkpoint": checkpoint,
        },
        "exit_code": exit_code,
    }
    if state_path:
        try:
            with io.open(state_path, "w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False, indent=2, sort_keys=True)
        except (IOError, OSError, TypeError):
            pass
    return result


def summarize_loop(result):
    """把结构化结果渲染成人类可读摘要（供命令行展示）。"""
    lines = []
    r = result.get("result", {})
    term = result.get("termination", {})
    base = result.get("baseline", {})
    lines.append("=" * 64)
    lines.append("[agent loop] 项目：%s" % result.get("project"))
    lines.append("[agent loop] 模式：%s（git=%s, max_turns=%d）"
                 % (result.get("mode"), result.get("used_git"),
                    result.get("max_turns")))
    lines.append("[agent loop] 基线告警：%d  %s"
                 % (base.get("total", 0), _fmt(base.get("by_rule", {}))))
    lines.append("-" * 64)
    for t in result.get("turns", []):
        v = t.get("verified")
        if v:
            lines.append(
                "  turn %d [%s] 补丁 %d 字节 → 终态 %d 告警 "
                "(no_new=%s, progress=%s) => %s"
                % (t.get("attempt"), t.get("strategy"), t.get("patch_bytes"),
                   v.get("total"), v.get("no_new_alerts"),
                   v.get("progress"), t.get("verdict")))
        else:
            lines.append(
                "  turn %d [%s] 补丁 %d 字节 => %s（%s）"
                % (t.get("attempt"), t.get("strategy"), t.get("patch_bytes"),
                   t.get("verdict"), t.get("feedback")))
    lines.append("-" * 64)
    lines.append("[agent loop] 终止：%s（用了 %s 轮）"
                 % (term.get("reason"), term.get("turns_used")))
    lines.append("[agent loop] 终态告警：%d  tier=%d  %s"
                 % (r.get("final_total"), r.get("tier", -1),
                    _fmt(r.get("final_by_rule", {}))))
    if r.get("accepted"):
        lines.append("[agent loop] 自证：通过(PASS)，修复已保留。")
    else:
        cp = r.get("checkpoint") or {}
        lines.append("[agent loop] 自证：不通过(FAIL)，已回退基线。")
        if cp.get("message"):
            lines.append("[checkpoint] %s" % cp["message"])
    lines.append("=" * 64)
    return "\n".join(lines)


def _fmt(d):
    if not d:
        return "{}"
    return "{" + ", ".join("%s:%s" % (k, v) for k, v in sorted(d.items())) + "}"
