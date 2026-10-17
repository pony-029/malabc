# R111 复盘：facts 往返入口 + 一次「杀父留子」的进程泄漏

> 本轮用户提示（逐字）：「matlabc.py 的开发流程是有一些记录文件的，你可以查找下」。
> 于是先做一件事：**把仓里既有的记录体系读一遍**，再决定这一轮做什么。
> 结论是：R109 §1 早就立了一条我上一轮违反了三次的规矩（改 `matlabc.py` 任何字节
> ⇒ 必须与整树重跑同轮）。本轮因此**不碰 `matlabc.py`**，只做不付重跑成本的推进。

---

## §0 一句话结论

**找到的记录体系**：`docs/SUPERPOWER_REVIEW_R30–R109.md` 共 **56 份**（每轮一份，
固定形状：白帽读数 / 判据 / 变化量 / 未完成 / 下一步），加
`docs/EVOLVE_ROADMAP_360.md`（360 轮台账）与 `docs/PLAN_LEDGER_DIGEST.json`
（`check_all` 的「计划块闸门」读它）。
**本轮落地**：`facts.py` 从「只有纯函数」变成**可用的往返入口**
（`--from <payload.json> --out <facts.json>`），实测 48 条事实、五类计数重放一致。
**本轮事故**：我杀探针父进程时**没杀子进程**，留下一个 **5.9 GB 孤儿**跑了 50 分钟，
与第二个探针抢资源 —— 两者都变慢，这才是「探针迟迟不落盘」的真因。
**未完成**：`check_kernel_snapshot` 的 W2 仍在等整树重跑（`PID 22440`）。

---

## §1 找到的记录体系：它决定了「一轮该做什么」

| 文件 | 数量 / 形态 | 它约束什么 |
| --- | --- | --- |
| `docs/SUPERPOWER_REVIEW_R*.md` | 56 份（R30–R109） | 每轮必须留一份复盘，含**读数**与**变化量** |
| `docs/EVOLVE_ROADMAP_360.md` | 360 轮台账 | `check_all` 的「计划块闸门」解析它；`action` 必须 ∈ 在册动作 |
| `docs/PLAN_LEDGER_DIGEST.json` | 3.15 KB | 上表的机器可读摘要，门「现算」核对 |

**R109 §1 的原文**（逐字）：

> 改 `matlabc.py` 任何字节 ⇒ 必须与整树重跑同轮，因为 `check_kernel_snapshot` 的 W2
> 只比 `provenance.matlabc_sha256` / `matlabc_bytes`，改一个字符它就红。
> ⚠ 反过来也一样：本轮**不**趁机改任何与这两件事无关的 `matlabc.py` 字节。

R110 我为了「门数散文」把 `matlabc.py:121` 从 21 改成 22、再改成 23，**改了三次、
一次都没重跑**。代价是可测的：第一次探针作废，第二次探针至今未落盘，`check_all` 停在 22/23。

---

## §2 事故：`Stop-Process -Id 20896` 只杀了父，没杀子

现象：第二次探针（`PID 22440`）启动 45 分钟仍无产物，而记录里同类重跑是 11 分钟。

排查（`Get-CimInstance Win32_Process`）：

```
PID 29436  父 20896（第一次探针，已被我 Stop-Process）
           CPU 570s   Mem 5.9 GB   matlabc.py . --lang c --checks all ...
PID 30532  父 22440（第二次探针）
           CPU 441s   Mem 2.5 GB   matlabc.py . --lang c --checks all ...
```

**两个 matlabc 同时在跑 62,704 个文件的全量检查**，互相抢 CPU 与内存。
杀掉孤儿 29436 后，30532 独占资源继续跑（CPU 从 441s 继续增长）。

判据层面这条怎么表述：`check_subprocess_hygiene.py` 管的是「stdin 必须切断 +
必须有 timeout」，**不管「父进程被终止后子进程是否存活」**。这是它的一条真实盲区：
用 `Popen` 起的长跑任务，父被杀后子会继续持有文件与内存，而任何门都不会说话。

本轮不做（它需要动 `check_subprocess_hygiene.py` 的判据族，会牵动 `ROW_SIGNATURE`
与 README 表行）；**记在这里**，作为下一步的一条候选。

---

## §3 本轮落地：`facts.py` 的往返入口

改动只有 `main()`（+21 行），不碰引擎：

```
python facts.py --from <payload.json> --out <facts.json>
```

实测（`tests/sample_m`）：

```
facts: 48 条 -> C:\temp\sample_facts.json
replay: {"edges": 9, "files": 13, "functions": 19, "heuristics": 5, "unresolved": 2}
```

输出同时**自证**：`replay != expected` 时返回 1。这条入口的意义是：
LSP / MCP 以后读 `facts.json`（KB 级），不再读 MB 级报表 —— 这正是 R110 §4
说的「事实层的价值在反向接线」。

---

## §4 当前状态

```
check_flow_diagrams  OK（26 / 26 / 26，D1–D12）
check_flow_figures   OK（11 / 50 / 11，FF1–FF7）
check_facts_replay   OK（FT1–FT3）
check_help_contract  OK（24 个护栏脚本）
check_readme_parity  OK（两侧各 23 行）
eol_probe            OK（302 个文本文件，EO1–EO3；未注册）
facts.py --from/--out 可用（48 条事实，重放一致）
check_all            22/23（W2 等整树重跑）
```

---

## §5 下一步（按优先级）

1. **收口 W2**：探针落盘后，把 `docs/KERNEL_RUN.md` 的
   `provenance.matlabc_sha256` 改成新值（`matlabc_bytes` 已是 1717722，不用动），
   再跑 `check_all` ⇒ 期望 **23/23**。
2. **门数散文移出 `matlabc.py`**（R110 §6 已立）：`matlabc.py` 只写「全部登记制护栏」，
   数字留 README。这样加门不再绑死一次整树重跑。
3. **`eol_probe.py` 升级为护栏**（门数 24），必须排在第 2 条之后。
4. **「杀父留子」补进 `check_subprocess_hygiene.py`**：`Popen` 长跑任务的登记项
   必须写明「父被终止时子进程如何收尾」；两向核对（登记了却已用 `terminate` 管理 ⇒ 陈旧）。
