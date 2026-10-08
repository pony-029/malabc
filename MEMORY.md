# MEMORY.md — malabc 项目记忆库

> 本文件由 pony-agent / matlabc 工作会话的 agent 持久记忆**无损迁移**而来，供在
> `D:\work\malabc` 继续演进时参考，保证上下文不丢失。
>
> 分区原则：
> - **通用用户偏好**：跨项目、长期有效（如 Python 版本约束、归档习惯）。
> - **matlabc / 本工程（pony-agent）记忆**：与 matlabc 引擎、pony-agent 工程直接相关。
> - **附录：Py3GPP 记忆（独立项目）**：属 `d:/code/py3gpp-master`（与 malabc 不同的仓库），
>   仅作完整索引保留，**未混入 malabc 主体**，避免污染；其原始记忆仍在 agent 知识库中不丢失。
>
> 每条记忆带原始 ID，便于回查。

---

## 一、通用用户偏好（跨项目，最高优先级）

### [39029573] Python 3.6.5 版本硬约束
- **约束**：用户环境固定使用 **Python 3.6.5**，绝不再次询问。
- **影响范围**：`matlabc.py` 及相关脚本必须兼容 3.6.5。
- **禁止使用的语法（3.7+ 才支持）**：
  - f-string 表达式内反斜杠转义（3.12 才放开）
  - 海象运算符 `:=`（3.8+）
  - f"{x=}" 调试语法（3.8+）
  - 仅位置参数 `/`（3.8+）
  - `match` 语句（3.10+）
  - 内置泛型下标 `list[int]`（3.9+，3.6 需用 `typing.List`）
  - `datetime.isoformat(timespec=)`（3.7+）→ 改用 `replace(microsecond=0).isoformat()`
  - `dict` 插入顺序保证（3.7+ 才保证，3.6 不可依赖）
- **拼接要求**：生成给浏览器的 JS 不受限；但 Python 端字符串拼接须 3.6 兼容
  （用 `%` 或 `.format`，勿在 f-string 内放反斜杠）。
- **matlabc 相关性**：★★★★★（matlabc.py 是 3.6.5 兼容核心，任何编辑都不能引入 3.7+ 语法）

### [88222452] 深度分析/审计必须归档（用户长期偏好）
- **要求**：后续每次「深度分析 / 审计 / 协同检查」类工作都必须归档。
- **归档位置**：`d:/code/py3gpp-master/docs/analysis/`（已建，含 `ANALYSIS_ARCHIVE_README.md` 索引）。
- **命名约定**：`docs/analysis/ANALYSIS_<日期YYYY-MM-DD>_<主题英文短名>.md`。
- **每篇归档至少含**：①审计方法（工具/技能/取证层次）②结论先行（评分/状态表）
  ③证据（文件路径+行号/命令+实测）④缺口清单（P0/P1/P2 分级）⑤建设性改进意见（可执行+优先级）。
- **动作**：做完此类分析后必须 (a)写归档文件 (b)更新 `ANALYSIS_ARCHIVE_README.md` 索引。
- **matlabc 相关性**：★★★（对 malabc 做深度审计时同样适用；归档目录可按 malabc 调整）

---

## 二、matlabc / 本工程（pony-agent）记忆

### [28316848] Skills 与代码实现一致性检查（pony-agent）
- 完成 Skills 与代码实现全面一致性检查。
- **P0 缺失**：①中央授时服务完全缺失；②逻辑时间戳会话 ID 机制未实现；③Git Hook 预时间戳申请缺失。
- **完成度**：Phase1 88%（良好）、Phase2 仅 44%（严重不足）、Phase3 50%（需改进）。
- **模块联动性**仅 35%，无法形成完整提交流程。
- **修复路线（4 阶段）**：P0 修复(1-2周) → P1 完善(2-3周) → P2 增强(3-4周) → 文档测试(1-2周)。

### [44465097] 5 个工具技能集成（pony-agent）
- 集成技能：skill-creator / document-skills / find-skill / code-simplifier / frontend-design（中文版）。
- 位置：`skills/skill-creator/`、`skills/document-skills/`、`skills/find-skill/`、`skills/code-simplifier/`、`skills/frontend-design/`。
- 建立联动：与核心技能（验证器框架、工作流引擎、会话管理等）及测试/WebUI 技能无缝集成。
- 测试 30 场景 100% 通过；搜索<100ms、文档生成<5s、代码分析<2s。

### [45053537] 综合优化实施（pony-agent）
- P0/P1 优化，新增 9 文件 4507 行：增强 LRU 缓存（TTL/定期清理）、增强 SSH 连接池、
  并行文件上传、增强错误处理（20+ 错误码）、命令别名系统（40+）、统一配置中心、
  优化数据库池、统一 SPA 架构（WebSocket + Chart.js）。
- 测试结果 10/10 阶段成功，系统达生产就绪。

### [49931423] 全流程端到端测试 Skill（pony-agent）
- 位置：`skills/end-to-end-full-flow-test/`，约 2340 行。
- 组件：一致性检查器（8 组件 100%）、数据流分析器（21 节点 30 边）、控制流分析器（4 路径）、
  API 测试器（14 API）、端到端运行器（5 场景 100%）。

### [52733048] 版本控制和自动化编译技能（pony-agent）
- 集成 5 技能：build-automation / version-control / deployment-automation / quality-assurance / continuous-integration。
- 覆盖 CI/CD 全流程：代码提交→版本控制→构建→测试→部署；API 20+，测试 50 场景 100%。
- 位置：`skills/build-automation/`、`skills/version-control/`、`skills/deployment-automation/`、`skills/quality-assurance/`、`skills/continuous-integration/`。

### [70866909] 全系统测试方案（pony-agent）
- 位置：`skills/full-system-test/`，覆盖 9 核心模块：消息校验 / 编译校验 / 冲突检查 /
  上板测试 / 状态查询 / 会话管理 / 数据库 / 分布式系统 / Git Hook。
- 7 测试阶段、23 用例、通过率 100%，支持 JSON/Markdown/HTML 报告。

### [81899382] 全系统测试方案扩展（pony-agent）
- 扩展：状态查询（CLI 8 + Web API 4 + Web 2）、边界（增强 16）、并发（增强 16）、
  异常（7）、性能（14）。总计 87 用例 100% 通过，约 5500 行。
- 性能：验证响应<10ms，吞吐>1000 ops/sec，100+ 并发无冲突。

---

## 三、matlabc 引擎关键事实（由代码/文档提炼，供演进参考）

> 以下非 agent 记忆条目，而是从已移植的 matlabc 代码与 `docs/` 提炼的「必须知道的工程事实」，
> 防止后续演进踩坑。

1. **入口与模块**：
   - `matlabc.py`（~1.4MB）—— 核心静态分析器，CLI + 可视化报告；`main(argv)` 为统一入口。
   - `matlabc_boot.py` —— 双击启动 GUI / `ask` / `flow` 子命令分发；imports `gui`、`matlabc_ask`、`matlabc_flow`、`matlabc`。
   - `matlabc_ask.py` —— 基于分析报告的问答式代码理解（BM25 + 意图识别，零依赖）。
   - `matlabc_flow.py` —— AI 修复闭环编排器（review→fix→apply→verify→report），复用 `matlabc_ask.normalize`。
2. **硬依赖**：`matlabc.py` 强依赖 `renderers/` 包（assets/report/snapshot/callgraph/sarif/metrics/unresolved/hotspot/creport/_shared），
   且 `renderers/*` 反向 `from matlabc import ...`。二者须成对存在，缺一不可运行。
3. **确定性补丁引擎**（`matlabc.py` 内 `_build_apply_patch`）：支持 `uninitialized`(high) /
   `dead_code` / （`--dup-exec-patch` 的）`dup_code`；形状不匹配为保守 reshape（检测+门禁，未计入硬指标）。
4. **测试**：`tests/test_matlabc.py`（零依赖、兼容 3.6.5），运行 `python tests/test_matlabc.py`；
   依赖 `tests/sample_m/`（真实 MATLAB 夹具）与 `ci-examples/merge_sarif.py`。
5. **质量评测闭环**（pony-agent 内 `tests/eval_ai_fix.py`）：度量「门禁 + 告警对账 + 确定性补丁引擎」，
   指标含 fix_success_rate / bad_fix_caught_rate / alarm_net_reduction / auto_fix_engine_ok / ai_provider_smoke。
   （已随首版后补迁移进 malabc：`tests/eval_ai_fix.py` + `tests/test_eval_ai_fix.py` + `tests/sample_ai_eval/`（clean_a.m / clean_b.m 基线夹具）+ 根 `ai_cli.py`（provider 冒烟在线路径依赖，仅标准库、自包含）。在 malabc 中 `python -m pytest tests/test_eval_ai_fix.py` 已验证通过。）
6. **CI 参考**：`ci-examples/` 含 GitHub Actions（static-analysis / sarif-merge / incremental / frontend-gate）、
   GitLab CI、`pre-commit`、`merge_sarif.py`（SARIF 聚合）。

---

## 四、附录：Py3GPP 记忆索引（独立项目，未移植）

> 以下记忆归属于**独立仓库 `d:/code/py3gpp-master`**（5G NR Python 实现），与 malabc 无代码关系。
> 为「无损」保留完整索引；其原始记忆仍在 agent 知识库中，未丢失。在 malabc 会话中可忽略本段。

- [32684250] Py3GPP R19 type2_advanced P74-P93 真实链路接入（共享 plan 真实 LDPC 译码，8 测绿）。
- [37351937] Py3GPP wRA2A 一致性门禁「套件6.0批」：清偿 40 处豁免、新增门禁#22/#23，CI 231 passed。
- [38336254] Py3GPP R19 物理层增强：PUSCH/PUCCH/PRACH/SRS + PDCCH/CSI-RS，64 端口 MIMO，AI/ML 优化，R19 符合度 90%+。
- [65468040] Py3GPP R19 type2_advanced P54-P73 决策层（28 测绿，含真实译码 P54/P68）。
- [74512198] Py3GPP P7 真实 OFDM 波形级 + 反馈开销建模 + MU-MIMO 块对角 ZF。
- [79917973] Py3GPP R19 type2_advanced P76-P92 决策层补充（12 轮全绿）。
- [60983908] Py3GPP Phase 10 完成，98% 完成度，PDSCH 层映射 + 极化码速率匹配。
- [86573282] Py3GPP P6 频率选择性 + OFDM 子载波级 Type II 预编码闭环（修复 4 个根因）。
- [89131094] Py3GPP R19 Type II P8-P33 决策层 + 生产化加固（62 用例）。
- [94516324] Py3GPP R19 Type II P34-P53 二十轮生产化加固（42 用例 2.1s 全绿）。

---

*迁移生成说明：本文件由 agent 工作记忆转录，旨在让 `D:\work\malabc` 成为可独立演进、上下文不丢失的工程。
任何对 matlabc 引擎的修改，请先回看本文件「二/三」节与 `docs/` 下的 `matlabc_*.md`。*
