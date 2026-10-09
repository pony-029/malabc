# flow/source —— mermaid 块的逐字导出

> 由 `_r45/census_flow.py` + `_r45/scaffold_flow.py` 生成。**内容与仓库文档逐字节一致（含 CRLF 行尾）**
> —— 这一点由 `_r45/normalize_flow_eol.py` 逐条断言：每个导出都必须等于
> 「源文档里那个块的行区间按 CRLF 拼回去」。不要在这里改图 —— 改图要改回源文档，再重新导出。

| 导出文件 | 源文档 | 行范围 | 图型 | 所在小节 |
| --- | --- | --- | --- | --- |
| `README__01.mmd` | `README.md` | L55–97 | `architecture` | malabc > Core Capabilities |
| `README__02.mmd` | `README.md` | L117–138 | `workflow` | malabc > Core Capabilities > Binary & GPU Analysis (`--binary`) |
| `README__03.mmd` | `README.md` | L195–206 | `workflow` | Machine-readable, for wiring into your own pipeline > One command instead of two: `--binary-attach` |
| `README__04.mmd` | `README.md` | L261–295 | `workflow` | One command: analyse myproj, then attribute its unresolved calls against libblas.so > Architecture |
| `README__05.mmd` | `README.md` | L338–348 | `workflow` | One command: analyse myproj, then attribute its unresolved calls against libblas.so > Architecture |
| `README__06.mmd` | `README.md` | L400–407 | `workflow` | (3) CI static analysis (SARIF + exit-code gate) > The Four Entry Points > 3. `flow` — AI Fix Loop |
| `README__07.mmd` | `README.md` | L447–454 | `workflow` | (3) CI static analysis (SARIF + exit-code gate) > CI Quality Gate |
| `README__08.mmd` | `README.md` | L560–568 | `workflow` | Q&A code understanding (offline => echoes a paste-ready prompt) > Quality Gates (self-verifying) |
| `README_CN__01.mmd` | `README_CN.md` | L49–91 | `architecture` | malabc > 核心能力 |
| `README_CN__02.mmd` | `README_CN.md` | L110–131 | `workflow` | malabc > 核心能力 > 二进制与 GPU 分析（`--binary`） |
| `README_CN__03.mmd` | `README_CN.md` | L184–195 | `workflow` | 机器可读，便于接进你自己的流水线 > 一条命令代替两条：`--binary-attach` |
| `README_CN__04.mmd` | `README_CN.md` | L247–281 | `workflow` | 一条命令：分析 myproj，再把它的未解析调用拿去 libblas.so 里对账 > 架构 |
| `README_CN__05.mmd` | `README_CN.md` | L324–334 | `workflow` | 一条命令：分析 myproj，再把它的未解析调用拿去 libblas.so 里对账 > 架构 |
| `README_CN__06.mmd` | `README_CN.md` | L385–392 | `workflow` | (3) CI 静态分析（SARIF + 退出码门禁） > 四个入口 > 3. `flow` —— AI 修复闭环 |
| `README_CN__07.mmd` | `README_CN.md` | L431–438 | `workflow` | (3) CI 静态分析（SARIF + 退出码门禁） > CI 质量门禁 |
| `README_CN__08.mmd` | `README_CN.md` | L543–551 | `workflow` | 问答式代码理解（离线 => 回显可直接粘贴的提示词） > 自验证质量门（Quality Gates） |
| `docs__SUPERPOWER_REVIEW_R30__01.mmd` | `docs/SUPERPOWER_REVIEW_R30.md` | L24–36 | `workflow` | superpower × 循环工程 · malabc 30 轮修复复盘（R1–R30） > 1. 方法：把「凭感觉改」换成「闭环 + 证据」 |
| `docs__SUPERPOWER_REVIEW_R30__02.mmd` | `docs/SUPERPOWER_REVIEW_R30.md` | L176–189 | `workflow` | superpower × 循环工程 · malabc 30 轮修复复盘（R1–R30） > 6. 登记制护栏（全部可自证） |
| `docs__SUPERPOWER_REVIEW_R44__01.mmd` | `docs/SUPERPOWER_REVIEW_R44.md` | L182–200 | `workflow` | SUPERPOWER_REVIEW_R44 —— 唯一判定点 · 五份复制变一份 · 反向判据照出前向盲区 · 行为保持 > §3 黄帽 / 绿帽：C'''1 落地表 |
| `docs__analysis__ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT__01.mmd` | `docs/analysis/ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT.md` | L72–107 | `workflow` | ANALYSIS 2026-10-08 · malabc 仓库全量深度审计（代码拉取 + 实测取证） > ④ 架构解剖 > 4.1 分层结构（实测还原，非文档抄录） |
| `docs__analysis__ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT__02.mmd` | `docs/analysis/ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT.md` | L189–208 | `workflow` | ANALYSIS 2026-10-08 · malabc 仓库全量深度审计（代码拉取 + 实测取证） > ⑥ AI / Agent 融合层审计 > 6.2 `agent_loop.py`（620 行）—— 真实受控闭环（**本仓最高质量模块**） |

合计 **21** 个 mermaid 块。
