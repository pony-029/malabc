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
import re
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


def _tally(alerts):
    by_rule = {}
    for a in alerts:
        by_rule[a.get("rule")] = by_rule.get(a.get("rule"), 0) + 1
    return by_rule, len(alerts)


def _memory_signature(by_rule):
    """由基线告警分布生成稳定签名（与 analyzer_memory.signature_of 一致）。"""
    return json.dumps(dict(sorted((k, int(v)) for k, v in (by_rule or {}).items())),
                      ensure_ascii=False, sort_keys=True)


def _now_iso():
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# P1-B：人工复核门 / 检查点出 Draft PR（可信安全出口）
# ---------------------------------------------------------------------------

def _run_git(directory, args):
    """运行 git 子命令，返回 (rc, out)。git 缺失/异常一律优雅降级。"""
    try:
        r = subprocess.run(["git"] + list(args), cwd=directory,
                           capture_output=True, text=True)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 127, "git 不可用"


def _run_gh(args):
    """运行 gh CLI，返回 (rc, out)。gh 缺失/异常优雅降级。"""
    try:
        r = subprocess.run(["gh"] + list(args), capture_output=True, text=True)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 127, "gh 不可用"


def _has_github_remote(directory):
    rc, out = _run_git(directory, ["remote", "get-url", "origin"])
    return rc == 0 and "github" in out.lower()


def _current_branch(directory):
    rc, out = _run_git(directory, ["rev-parse", "--abbrev-ref", "HEAD"])
    return out.strip() if rc == 0 else ""


def _clip(s, n=400):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + " ..."


def _first_url(s):
    m = re.search(r"https?://github\.com/\S+", s or "")
    return m.group(0) if m else None


def _write_temp_patch(patch_text):
    pf = tempfile.NamedTemporaryFile(prefix="agent_loop_rev_",
                                     suffix=".patch", delete=False,
                                     mode="w", encoding="utf-8")
    try:
        pf.write(patch_text)
        pf.close()
        return pf.name
    except (OSError, IOError):
        return None


def _review_md(result, candidate_patch, patch_path):
    r = result.get("result", {})
    base = result.get("baseline", {})
    lines = [
        "# matlabc 修复审查产物（待人工复核）",
        "",
        "- 生成时间：%s" % _now_iso(),
        "- 工程：%s" % result.get("project"),
        "- 模式：%s  git=%s  max_turns=%d"
        % (result.get("mode"), result.get("used_git"),
           result.get("max_turns")),
        "- 基线告警：%d  %s" % (base.get("total", 0), _fmt(base.get("by_rule", {}))),
        "- 终态告警：%d  %s  tier=%d"
        % (r.get("final_total"), _fmt(r.get("final_by_rule", {})), r.get("tier", -1)),
        "- 状态：%s" % ("PASS（已验证，待人工落地）"
                        if r.get("review_pending")
                        else "FAIL（未通过自证，已回退基线）"),
        "- 受影响文件：%s" % ", ".join(_patch_targets(candidate_patch)) or "(无)",
        "",
        "## 如何落地",
        "",
        "    git apply %s" % os.path.basename(patch_path),
        "",
        "或按下方 diff 手动修改。",
        "",
        "## 候选补丁",
        "",
        "```diff",
        candidate_patch.rstrip("\n"),
        "```",
    ]
    return "\n".join(lines) + "\n"


def write_review_artifact(project_root, result, candidate_patch, review_dir=None):
    """把候选修复物化为可人工复核的产物（patch + json + md）。

    默认落在 <project_root>/.codebuddy/analyzer/review/，离线可用；
    返回 {ok, patch_path, json_path, md_path, review_dir} 或 {ok:False, reason}。"""
    if not candidate_patch:
        return {"ok": False, "reason": "no_candidate_patch"}
    root = project_root or "."
    rdir = review_dir or os.path.join(root, ".codebuddy", "analyzer", "review")
    try:
        os.makedirs(rdir, exist_ok=True)
    except OSError:
        return {"ok": False, "reason": "mkdir_failed"}
    ts = _now_iso().replace(":", "-")
    base = os.path.join(rdir, "REVIEW_" + ts)
    patch_path, json_path, md_path = base + ".patch", base + ".json", base + ".md"
    try:
        with io.open(patch_path, "w", encoding="utf-8") as fh:
            fh.write(candidate_patch)
        meta = {
            "tool": "matlabc_flow",
            "ts": _now_iso(),
            "project": result.get("project"),
            "baseline": result.get("baseline"),
            "termination": result.get("termination"),
            "result": result.get("result"),
            "files": _patch_targets(candidate_patch),
            "patch_path": patch_path,
        }
        with io.open(json_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
        with io.open(md_path, "w", encoding="utf-8") as fh:
            fh.write(_review_md(result, candidate_patch, patch_path))
        return {"ok": True, "patch_path": patch_path, "json_path": json_path,
                "md_path": md_path, "review_dir": rdir}
    except (IOError, OSError, TypeError):
        return {"ok": False, "reason": "write_failed"}


def publish_draft_pr(directory, patch_text, title, body, base="main"):
    """尝试用 gh 把候选补丁开成 Draft PR（可信安全出口）。

    流程：建临时分支 → apply 补丁 → 提交 → 推送 → gh pr create --draft。
    任何一步失败（gh 缺失 / 非 GitHub 远程 / 网络 / 权限）都优雅降级，
    返回 (ok, message)；成功返回 (True, pr_url)。失败时尽力回退分支状态。"""
    rc, _ = _run_gh(["--version"])
    if rc != 0:
        return (False, "gh CLI 不可用（已保留本地审查产物）。")
    if not _has_github_remote(directory):
        return (False, "当前仓库无 GitHub 远程（已保留本地审查产物）。")
    ts = _now_iso().replace(":", "-")
    branch = "matlabc/review-" + ts
    orig = _current_branch(directory)
    pf = _write_temp_patch(patch_text)
    success = False
    try:
        rc, out = _run_git(directory, ["checkout", "-b", branch])
        if rc != 0:
            return (False, "创建分支失败：%s" % _clip(out))
        if pf:
            rc, out = _run_git(directory, ["apply", pf])
        else:
            rc, out = 1, "写临时补丁失败"
        if rc != 0:
            return (False, "应用补丁失败：%s" % _clip(out))
        rc, out = _run_git(directory, ["add", "-A"])
        if rc != 0:
            return (False, "git add 失败：%s" % _clip(out))
        rc, out = _run_git(directory, ["commit", "-m", title])
        if rc != 0:
            return (False, "提交失败：%s" % _clip(out))
        rc, out = _run_git(directory, ["push", "-u", "origin", branch])
        if rc != 0:
            return (False, "推送失败：%s" % _clip(out))
        rc, out = _run_gh(["pr", "create", "--draft", "--title", title,
                           "--body", body, "--base", base])
        if rc != 0:
            return (False, "gh pr create 失败：%s" % _clip(out))
        success = True
        return (True, _first_url(out) or "(见 GitHub)")
    except Exception as e:  # noqa: BLE001 - 任何异常都降级为本地产物
        return (False, "Draft PR 异常：%s" % e)
    finally:
        if pf and os.path.exists(pf):
            try:
                os.remove(pf)
            except OSError:
                pass
        if not success:  # 仅失败时清理临时分支，避免污染工作区
            try:
                if orig:
                    _run_git(directory, ["checkout", orig])
                _run_git(directory, ["branch", "-D", branch])
            except Exception:
                pass


def run_fix_loop(directory, fix_source, max_turns=3, lang=None,
                 state_path=None, project_root=None, use_memory=False,
                 review_gate=False, review_dir=None, draft_pr=False):
    """受控自校验修复环。返回结构化结果 dict（含 turns / termination / result）。

    接口约定（供 matlabc_flow.run_flow_loop 调用）：
      fix_source(attempt, feedback) -> patch_text | None
    结果 dict 关键键：accepted / final_total / result.tier / result.checkpoint /
                       termination.reason / exit_code。
    """
    from matlabc_flow import analyze, count_alerts, load_alerts, apply_memory

    use_git = _is_git_repo(directory)
    root = project_root or directory
    baseline_path = analyze(directory, lang)
    by_before, total_before = count_alerts(baseline_path)

    # 跨运行记忆：分析时抑制已知误报（仅影响基线计数，绝不自动抑制真实缺陷）
    learned_available = False
    if use_memory:
        try:
            kept, _supp = apply_memory(root, load_alerts(baseline_path))
            by_before, total_before = _tally(kept)
        except Exception:
            pass
        try:
            import analyzer_memory as am
            learned_available = am.lookup_learned_fix(
                root, _memory_signature(by_before)) is not None
        except Exception:
            learned_available = False

    turns = []
    accepted = False
    final_total = total_before
    final_by = dict(by_before)
    feedback = ""
    last_candidate = None
    termination = None
    learned_recorded = False
    needs_review = False
    last_accepted_patch = None

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
                # 结构化反馈（含被拒补丁与具体原因），供 LLM 下一轮修正
                feedback = {
                    "reason": "apply_failed",
                    "detail": "apply_failed: %s" % e,
                    "rejected_patch": patch,
                }
                continue

            if not applied_ok:
                turns.append({
                    "attempt": attempt, "strategy": _strategy_name(fix_source),
                    "patch_bytes": patch_bytes, "applied": False,
                    "verdict": "apply_rejected",
                    "feedback": "patch_not_applicable_to_working_tree",
                })
                feedback = {
                    "reason": "apply_rejected",
                    "detail": "patch_not_applicable_to_working_tree",
                    "rejected_patch": patch,
                }
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
                # 人工复核门：验证通过但按 --dry-run 要求不自动落地，回退工作副本，
                # 改为出审查产物，交人工复核后再落地（可信安全出口）。
                if review_gate:
                    if use_git:
                        _revert_with_git(patch, directory)
                    else:
                        _revert_internal(snapshot, directory)
                    last_accepted_patch = patch
                    needs_review = True
                    break
                # 跨运行记忆：把已验证修复记入项目记忆，供后续同分布告警复用
                if use_memory:
                    try:
                        import analyzer_memory as am
                        am.record_learned_fix(root, {
                            "signature": _memory_signature(by_before),
                            "baseline_by_rule": by_before,
                            "files": _patch_targets(patch),
                            "patch_bytes": patch_bytes,
                            "rule_reduction": total_before - total_after,
                            "ts": _now_iso(),
                        })
                        learned_recorded = True
                    except Exception:
                        learned_recorded = False
                break
            # 回退到基线（验证不通过，绝不保留半截改动）
            if use_git:
                _revert_with_git(patch, directory)
            else:
                _revert_internal(snapshot, directory)
            # 结构化反馈（含被拒补丁与具体拒绝原因），供 LLM 下一轮聚焦修正
            feedback = {
                "reason": "verification_failed",
                "no_new_alerts": no_new,
                "progress": progress,
                "delta": d,
                "total_before": total_before,
                "total_after": total_after,
                "by_after": by_after,
                "report_path": rep_after,
                "rejected_patch": patch,
            }

        if termination is None:
            termination = {"reason": "max_turns", "turns_used": max_turns}

    if accepted:
        tier = 0 if final_total == 0 else 1
        exit_code = 0
    else:
        tier = 2
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
            "checkpoint": None,
            "learned_fix_available": learned_available,
            "learned_fix_recorded": learned_recorded,
            "review_pending": needs_review,
        },
        "exit_code": exit_code,
    }

    # P1-B：人工复核门 / 检查点出审查产物（+ 可选 Draft PR）
    candidate = last_accepted_patch if needs_review else last_candidate
    if (needs_review or tier == 2) and candidate:
        art = write_review_artifact(root, result, candidate, review_dir)
        cp = {
            "candidate_patch_bytes": len(candidate.encode("utf-8")),
            "has_candidate": True,
            "artifact": art,
        }
        if needs_review:
            cp["message"] = ("已通过自证，但按 --dry-run 人工复核门要求暂不落地，"
                             "请人工复核后手动应用审查产物（%s）。"
                             % (art.get("patch_path") or "本地"))
            result["result"]["review_pending"] = True
            result["exit_code"] = 3  # 3 = 已验证但待人工复核（未落地）
        else:
            cp["message"] = ("未通过自证（%s）：修复后仍有新增 / 未减少告警，"
                             "已回退基线，请人工复核候选补丁（%s）。"
                             % (termination["reason"],
                                art.get("patch_path") or "本地"))
        if draft_pr:
            title = "matlabc 自动修复候选（待复核）"
            body = _review_md(result, candidate, art.get("patch_path") or "REVIEW.patch")
            ok, msg = publish_draft_pr(directory, candidate, title, body)
            cp["draft_pr"] = {"ok": ok, "message": msg}
        result["result"]["checkpoint"] = cp
    elif tier == 2:
        result["result"]["checkpoint"] = {
            "message": ("未通过自证（%s）：无可用候选补丁（修复源无策略或轮次用尽），"
                        "请人工介入。" % termination["reason"]),
            "candidate_patch_bytes": 0,
            "has_candidate": False,
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
        if r.get("review_pending"):
            lines.append("[agent loop] 自证：通过(PASS)，但按人工复核门未落地（exit 3）。")
        else:
            lines.append("[agent loop] 自证：通过(PASS)，修复已保留。")
    else:
        cp = r.get("checkpoint") or {}
        lines.append("[agent loop] 自证：不通过(FAIL)，已回退基线。")
        if cp.get("message"):
            lines.append("[checkpoint] %s" % cp["message"])
    if r.get("review_pending") or (r.get("checkpoint") or {}).get("has_candidate"):
        cp = r.get("checkpoint") or {}
        art = cp.get("artifact") or {}
        if art.get("patch_path"):
            lines.append("[审查产物] %s" % art["patch_path"])
        dpr = cp.get("draft_pr")
        if dpr:
            lines.append("[Draft PR] %s：%s" % (dpr.get("ok"), dpr.get("message")))
    if r.get("learned_fix_available"):
        lines.append("[记忆] 当前基线存在同分布的「已学习修复」，可复用历史补丁。")
    if r.get("learned_fix_recorded"):
        lines.append("[记忆] 已把本次已验证修复记入项目记忆（learned_fixes）。")
    lines.append("=" * 64)
    return "\n".join(lines)


def _fmt(d):
    if not d:
        return "{}"
    return "{" + ", ".join("%s:%s" % (k, v) for k, v in sorted(d.items())) + "}"
