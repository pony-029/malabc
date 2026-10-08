# -*- coding: utf-8 -*-
"""
P0-2 离线 AI 修复质量评测闭环（零依赖、纯离线、不触碰"重扫自证"壁垒）。

度量 pony-agent 自己掌控的「可证明补丁闭环」质量 —— 即：给定注入缺陷与补丁，
重扫门禁能否 (a) 正确放行好补丁并精确对账告警数，(b) 拦截引入新缺陷的坏补丁，
(c) 端到端驱动真实确定性补丁引擎把缺陷真正修掉。

不依赖任何外部模型：离线即可运行，度量的是「门禁 + 告警对账 + 确定性补丁引擎」
这三件 pony-agent 自身拥有的能力。这正是"AI 修复质量"在离线环境下的可度量地基。

扩面（相较初版）：
  · 多缺陷类：未初始化(uninit) / 死代码(dead_code) / 形状不匹配(shape_mismatch)，
    其中 uninit 与 dead_code 是确定性引擎可自动修复类（引擎端到端验证），
    shape_mismatch 作为"检测+门禁"测量类（引擎保守 reshape 修复尚未计入硬指标）。
  · 真实语料：uninit_real 场景把注入缺陷放进真实 MATLAB 工程 tests/sample_m，
    在"非空、含真实告警（含 dup_code）"的真实代码上验证门禁对账正确。
  · ai_provider_smoke：配置 provider 环境变量时，真实连通一次 provider 并真实跑一轮
    受控环，结果计入指标；离线（无 provider 环境变量）时为 SKIPPED。

产出：tests/eval_ai_fix_report.json（指标）+ 控制台摘要。

指标：
  fix_success_rate    好补丁恢复基线率（门禁放行 + 对账正确）
  bad_fix_caught_rate 坏补丁被门禁捕获率（"告警不增"壁垒不被削弱）
  alarm_net_reduction 好补丁相对"注入后"的告警净减（1.0 = 注入缺陷被完全消除）
  auto_fix_engine_ok  确定性引擎端到端是否真的修掉注入缺陷（仅计 engine_fixable 类）
  ai_provider_smoke   （可选）真实 provider 接入冒烟 + 真实跑环，离线时为 SKIPPED
"""
import os
import sys
import io
import json
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from matlabc_flow import analyze, gen_patch, count_alerts  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_ai_eval")
SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_m")

# 注入缺陷：未初始化变量（确定性引擎可修，confidence=high）
INJECT_BUG = (
    "function y = buggy(a)\n"
    " y = z + a;\n"
    "end\n"
)
# 注入缺陷：死代码（return 之后不可达行，确定性引擎可删除）
DEAD_BUG = (
    "function y = deadf(a)\n"
    " y = a + 1;\n"
    " return;\n"
    " z = y * 2;   % 不可达死代码\n"
    "end\n"
)
# 注入缺陷：形状不匹配（+/- 同 numel，确定性引擎可保守 reshape；仅测检测+门禁）
SHAPE_BUG = (
    "function y = sm(a,b)\n"
    " A = ones(2,2);\n"
    " B = ones(1,4);\n"
    " C = A + B;   % 维度不匹配（numel 相等，引擎可 reshape）\n"
    " y = C;\n"
    "end\n"
)

# 坏补丁用的"新引入缺陷"文件内容（与 INJECT_BUG 同类，制造"修动作反而引入新缺陷"）
BAD_NEW_BUG = INJECT_BUG


def _scan(directory):
    """返回 (by_rule, total)，复用 matlabc_flow.analyze + count_alerts。"""
    report = analyze(directory, "matlab")
    return count_alerts(report)


def _copy_base(dst, kind):
    base = FIXTURE if kind == "toy" else SAMPLE
    if os.path.isdir(base):
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(base, dst)
    else:
        os.makedirs(dst)


def _apply_unified(directory, patch_text):
    """最小 unified-diff 应用器（单文件单 hunk，零依赖；仅用于受控夹具）。

    取补丁中所有 '+' 与上下文(' ') 行重建文件内容，丢弃 '-' 行。
    对"插入/删除单文件整体行"类补丁（本评测场景）精确成立。
    """
    fname = None
    new_lines = []
    in_hunk = False
    for ln in patch_text.splitlines():
        if ln.startswith("+++ "):
            fname = ln[4:].strip()
            if fname.startswith("b/"):
                fname = fname[2:]
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if ln.startswith("@@"):
            continue
        if ln.startswith("+"):
            new_lines.append(ln[1:])
        elif ln.startswith("-"):
            pass
        elif ln.startswith(" "):
            new_lines.append(ln[1:])
    if not fname:
        return False
    with io.open(os.path.join(directory, fname), "w", encoding="utf-8") as fh:
        fh.write("\n".join(new_lines) + "\n")
    return True


# 缺陷场景注册表：每类经历 注入→门禁(好补丁)→壁垒(坏补丁)→(可选)引擎 全生命周期
SCENARIOS = [
    dict(id="uninit_toy", base="toy", inject_file="buggy.m",
         inject_text=INJECT_BUG, engine_fixable=True),
    dict(id="dead_code_toy", base="toy", inject_file="deadf.m",
         inject_text=DEAD_BUG, engine_fixable=True),
    dict(id="uninit_real", base="real", inject_file="pony_inj_uninit.m",
         inject_text=INJECT_BUG, engine_fixable=False),
    dict(id="shape_mismatch_toy", base="toy", inject_file="sm.m",
         inject_text=SHAPE_BUG, engine_fixable=False),
]


def _run_scenario(spec, work):
    """对单个缺陷类跑全生命周期，返回该场景的指标细节。"""
    d = os.path.join(work, spec["id"])
    _copy_base(d, spec["base"])
    base_by, base_total = _scan(d)

    # 注入缺陷
    inj_path = os.path.join(d, spec["inject_file"])
    with io.open(inj_path, "w", encoding="utf-8") as fh:
        fh.write(spec["inject_text"])
    inj_by, inj_total = _scan(d)
    delta = inj_total - base_total

    detail = {
        "case": spec["id"],
        "base_total": base_total,
        "injected_delta": delta,
        "engine_fixable": spec["engine_fixable"],
    }
    # 自校准：若注入未触发检测（delta<=0），记为 INJECTION_NO_OP，绝不误判通过
    if delta <= 0:
        detail["result"] = "INJECTION_NO_OP"
        detail["hint"] = "注入缺陷未被检测，需调整夹具；本场景不计入通过率。"
        return detail

    # ---- 好补丁（门禁层）：删除注入文件，应回到基线 ----
    os.remove(inj_path)
    good_by, good_total = _scan(d)
    good_restores = (good_total == base_total)
    detail["good_restores"] = good_restores
    detail["good_post_total"] = good_total

    # ---- 坏补丁（壁垒层）：删注入文件，但新增一个未初始化缺陷文件 ----
    bad_new = os.path.join(d, "bad_%s.m" % spec["id"])
    with io.open(bad_new, "w", encoding="utf-8") as fh:
        fh.write(BAD_NEW_BUG)
    bad_by, bad_total = _scan(d)
    bad_caught = (bad_total > base_total)
    detail["bad_caught"] = bad_caught
    detail["bad_post_total"] = bad_total

    # ---- 端到端：真实确定性引擎（仅 engine_fixable 类）----
    detail["engine_fixed"] = None
    if spec["engine_fixable"]:
        eng = os.path.join(work, spec["id"] + "_eng")
        _copy_base(eng, spec["base"])
        with io.open(os.path.join(eng, spec["inject_file"]), "w", encoding="utf-8") as fh:
            fh.write(spec["inject_text"])
        patch_txt = gen_patch(eng, os.path.join(eng, "ap"), "matlab")
        engine_fixed = False
        if patch_txt and patch_txt.strip():
            if _apply_unified(eng, patch_txt):
                eb, et = _scan(eng)
                engine_fixed = (et == base_total)
        detail["engine_fixed"] = engine_fixed
        detail["patch_bytes"] = len(patch_txt or "")

    detail["result"] = "OK"
    return detail


def _run_provider_smoke(work):
    """配置 provider 时，真实连通一次 provider 并真实跑一轮受控环；否则 SKIPPED。"""
    name = os.environ.get("MATLABC_AI_PROVIDER")
    key = os.environ.get("OPENAI_API_KEY")
    if not (name or key):
        return "SKIPPED(no provider env)"
    try:
        import time
        import ai_cli
        from matlabc_flow import run_flow_loop

        prov_name = name or "openai"
        prov, resolved, warn = ai_cli.resolve_provider(prov_name, {}, env=os.environ)
        t0 = time.time()
        reachable = False
        err = None
        resp = None
        try:
            resp = prov.complete([
                {"role": "system", "content": "你是连通性探针，只回复 OK。"},
                {"role": "user", "content": "reply OK"},
            ], max_tokens=8, temperature=0.0)
            reachable = bool(resp and resp.strip())
        except Exception as _e:
            err = str(_e)
        latency = round(time.time() - t0, 3)

        # 真实跑一轮受控环（确定性引擎修复；验证 provider 上下文下环仍可端到端收敛）
        proj = os.path.join(work, "provider_smoke")
        _copy_base(proj, "toy")
        with io.open(os.path.join(proj, "buggy.m"), "w", encoding="utf-8") as fh:
            fh.write(INJECT_BUG)
        rc = run_flow_loop(proj, max_turns=2, lang="matlab", provider=prov)
        return {
            "status": "RUN",
            "provider": resolved or prov_name,
            "reachable": reachable,
            "latency_s": latency,
            "loop_rc": rc,
            "error": err,
        }
    except Exception as _e:
        return {"status": "RUN_ERROR", "error": str(_e)}


def run_eval():
    metrics = {
        "baseline_total": None,
        "fix_success_rate": None,
        "bad_fix_caught_rate": None,
        "alarm_net_reduction": None,
        "auto_fix_engine_ok": None,
        "ai_provider_smoke": "SKIPPED(no provider env)",
        "scenarios": 0,
        "details": [],
    }
    work = tempfile.mkdtemp(prefix="eval_ai_fix_")

    # 干净玩具基线（预期 0 告警）
    base_by, base_total = _scan(FIXTURE)
    metrics["baseline_total"] = base_total

    details = []
    for spec in SCENARIOS:
        details.append(_run_scenario(spec, work))
    metrics["details"] = details
    metrics["scenarios"] = len([d for d in details if d.get("result") != "INJECTION_NO_OP"])

    # 聚合（仅计"被检测"的有效场景，INJECTION_NO_OP 不计入通过率）
    valid = [d for d in details if d.get("result") != "INJECTION_NO_OP"]
    if valid:
        metrics["fix_success_rate"] = sum(
            1 for d in valid if d.get("good_restores")) / float(len(valid))
        metrics["bad_fix_caught_rate"] = sum(
            1 for d in valid if d.get("bad_caught")) / float(len(valid))
        metrics["alarm_net_reduction"] = sum(
            (d["injected_delta"] - (d["good_post_total"] - d["base_total"]))
            / float(max(1, d["injected_delta"]))
            for d in valid) / float(len(valid))
    else:
        metrics["fix_success_rate"] = 0.0
        metrics["bad_fix_caught_rate"] = 0.0
        metrics["alarm_net_reduction"] = 0.0

    eng_scenarios = [d for d in valid if d.get("engine_fixable")]
    metrics["auto_fix_engine_ok"] = all(
        d.get("engine_fixed") is True for d in eng_scenarios) if eng_scenarios else False

    # AI provider 冒烟（配置环境变量时真实跑；否则跳过）
    metrics["ai_provider_smoke"] = _run_provider_smoke(work)

    shutil.rmtree(work, ignore_errors=True)
    return metrics


if __name__ == "__main__":
    m = run_eval()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "eval_ai_fix_report.json")
    with io.open(out, "w", encoding="utf-8") as fh:
        json.dump(m, fh, ensure_ascii=False, indent=2)
    print("=== P0-2 离线 AI 修复质量评测（扩面：多类 + 真实语料 + provider 冒烟）===")
    print(json.dumps(m, ensure_ascii=False, indent=2))
    # 退出码：关键指标必须全绿，否则非零（便于 CI 门禁）
    ok = (m["fix_success_rate"] == 1.0 and m["bad_fix_caught_rate"] == 1.0
          and m["auto_fix_engine_ok"] is True)
    sys.exit(0 if ok else 1)
