# ANALYSIS 2026-10-08 · malabc 演进治理（superpower × brainstorming）

> 归档依据：用户长期偏好 [88222452]——深度分析/审计/协同检查类工作必须归档到 `docs/analysis/`
> 并维护索引。本篇为 malabc 项目下一阶段演进的系统性分析与方案收敛。

## ① 方法（工具 / 技能 / 取证层次）

- **技能**：`superpower`（系统级深度分析：定界→盘点→差距根因→引领性结论）+ `brainstorming`（发散→收敛：SCAMPER + 反头脑风暴 + 评分矩阵）。
- **取证层次**：
  - 代码事实：`matlabc.py`（单文件 29637 行、`VERSION="1.16.67"`、`--check-py36` 在 27991 行、CI 模板生成在 `ci-examples/`）。
  - 工程配置：`.gitignore`（缺 `.analyzer_*`/`dist_bin/`/`_build/`/`*.sarif`、已忽略 `__pycache__/`）、`MEMORY.md`、`docs/`（11 篇）。
  - 测试：`tests/test_matlabc.py`、`tests/test_eval_ai_fix.py`（pytest）、`tests/sample_m/*.m`（13 个）。
  - 历史探索：前期对 `renderers/`、`matlabc_ask.py`、`matlabc_flow.py`、`ai_cli.py` 的入口与产物盘点。

## ② 结论先行（状态表）

| 维度 | 状态 | 评分(1-5) |
| --- | --- | --- |
| 功能覆盖（多语言/结构/检查/修复闭环） | ✅ 局部领先 | 5 |
| 工程化- CI 启用 | 🔴 未启用（仅模板） | 2 |
| 工程化- 测试粒度 | 🔴 粗（核心单文件缺细粒度单测） | 2 |
| 可维护性（单文件 29k 行 + 反向 import） | 🟡 风险累积 | 3 |
| 生态/社区（CONTRIBUTING/英文/模板） | 🔴 缺失 | 2 |
| README 实拍图 | 🟡 仅 Mermaid | 3 |
| .gitignore 完整性 | 🟡 缺缓存/产物 | 3 |

**总体判断**：能力深度已超多数同类开源 MATLAB 工具，差距性质为**工程化与生态的结构性缺失**（非深度不足）。优先补齐"让工具被用、被信、被贡献"的底座。

## ③ 证据

- `ci-examples/` 含 `github_actions_*.yml` 等模板，但仓库根无 `.github/workflows/` → CI 从未真正启用（dogfooding 缺失）。
- `matlabc.py` 行 27991 `--check-py36` 已实现 3.6.5 语法门禁，可零成本复用为 CI 第一步。
- `tests/` 仅 2 个测试文件；核心 `matlabc.py` 单文件 29,637 行，缺分层单测。
- `renderers/` 渲染器被 `matlabc.py` 反向 `import`，存在环形耦合风险（可维护性维度）。
- `.gitignore` 未忽略 `.analyzer_*`（增量缓存）、`*.sarif`、`dist_bin/`、`_build/`，多次分析/打包易误入库。

## ④ 缺口清单（P0/P1/P2）

- **P0**：启用自身 CI（dogfooding）——将 `ci-examples/` 落地为 `.github/workflows/ci.yml`，跑 `matlabc` 分析自身 + `--check-py36` + 测试。
- **P0**：补全 `.gitignore`（`.analyzer_*`/`dist_bin/`/`_build/`/`*.sarif`/`.codebuddy/`）。
- **P1**：真实产物截图进 README（`tests/sample_m` → `--browse` HTML 截图，当前环境无浏览器，需人工/CI 截图）。
- **P1**：CONTRIBUTING + issue/PR 模板（社区底座）。
- **P1**：英文文档站（mkdocs）或补充 `README` 英文能力矩阵。
- **P2**：拆分 29k 行单文件为分层模块（替换 `renderers` 反向 import，价值高但风险/成本高）。
- **P2**：PyPI 发布 / GitHub Action 自动开修复 PR / PR 增量评论机器人 / benchmark 回归门禁 / 插件注册表。

## ⑤ 建设性改进意见（可执行 + 优先级）

1. **立即（已本批落地）**：A=创建 `.github/workflows/ci.yml`（3.6 门禁+测试+自身分析 artifact）；B=补全 `.gitignore`；D=新增 `CONTRIBUTING.md`；README 加 CI 徽章。
2. **近期**：用 `matlabc` 对 `tests/sample_m` 生成浏览站点并截图嵌入 README「效果示意」；补英文概览。
3. **中期**：单文件拆分 POC（先抽 `parse`/`analyze`/`render` 三层，保持 `renderers` 单向依赖）；加 `pytest` coverage 基线。
4. **长期**：`--gen-ci both` 已支持模板，进一步做 GitHub Action「自动开修复 PR」与 PR 增量评论机器人，把静态分析变成团队默认守门员。

> 收敛评分：A(价值5·可行5·成本2)、B(4·5·1)、D(3·5·2) 为 Top 落地项；F(单文件拆分 5·2·5) 列 P2。
