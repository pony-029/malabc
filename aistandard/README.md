# aistandard —— ANE 规范原件与本仓的落地映射

本目录存放**外部规范原件**，不是本仓生成的产物：

| 文件 | 说明 |
|---|---|
| `ANE规范-AI原生软件生命体工程范式.md` | v0.5.0 正式发布版（13 章，约 102 KB） |
| `ANE规范-AI原生软件生命体工程范式.html` | 同一份规范的发布版渲染（约 121 KB） |

两处的行尾/编码由**发布方**决定，本仓不改写 —— `tools/check_eol_convention.py`
的 `SKIP_DIRS` 里登记了 `aistandard`，否则它带的 1475 个 CRLF 会把编码门顶红。

## 为什么必须入库

`tools/check_ane.py` 读这份 `.md` 作为**唯一真源**。它此前只在工作区、未纳入版本库，
于是换一台机器 clone 下来，那道门会直接报「缺输入（规范文件不存在）」——
**门在，但守的东西不在**。R1000 把它 `git add` 进来，这个洞才闭合。

## 条款 → 机检判据的映射

规范里能机检的是**六条**，全部落在 `tools/check_ane.py`，产物 `flow/ane.json`，
并接进 `tools/harness.py` 的第 7 组（每轮自动跑）。

| 条款 | 判据 ID | 判法 |
|---|---|---|
| 第四条 小脑优先 | `AN1` | `tools/brain.py` 存在 + `flow/brain-usage.jsonl` 有咨询留痕（可审计） |
| 第五条 战略性唤醒 | `AN2` | `tools/brain_llm.py --selftest` 双向通过 + 请求体 ≤ 200 字节（特征向量 + 错误码） |
| 第六条 记忆护城河 | `AN3` | `flow/failures.json` 每条经验都有**真实存在**的 witness |
| 第七条 绝对防御 | `AN4` | 全仓 `except: pass` 计数 ≤ `flow/ane-baseline.json` 的基线（只降不升） |
| 第九条 一票否决 | `AN5` | 存在 `flow/ane-auth.json`（`granted_by` + `scope`，**必须由人写**） |
| 第十条 全景白盒 | `AN6` | `flow/full_report.html` 与 `tools/progress.py` 产物齐备 |

## 明确**未**纳入机检的条款（不假装覆盖）

写在 `flow/ane.json` 的 `uncovered` 字段里，避免"看不见就当做到了"：

* **第八条 即时修复** —— 取决于 MIR 层自愈的实现深度，无法用"产物是否存在"表达；
* **第三章 D0–D3 确定性分级** —— 需人工评级；
* **第十一章 L0–L5 成熟度** —— 需人工评级。

这三项要变成判据，得先能写出"可复算的量化口径"，否则只会退化成一句口号。

## 维护约定

* **不要**手改这两个原件（它们是发布版）；需要新版就整份替换；
* 修改条款映射时，`aistandard/README.md`（本文件）与
  `tools/check_ane.py` 的 `ROW_SIGNATURE`（`AN1–AN6`）必须同步 ——
  后者有 `check_readme_parity` / `check_help_contract` 在守。
