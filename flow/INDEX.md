# flow/INDEX —— 21 个 mermaid 块 → 13 张图 × 中英两版

> 本文件由 `_r45/gen_flow_index.py` 生成，**只读**：所有链接与体积都取自实际文件。
> 21 个块里有 8 对是 EN/CN 镜像（内容同构、标签语言不同），映射后是 **13 张不同的图**；
> 每张图都用 archify 渲染成**英文版**（`candidate.json`）与**中文版**（`candidate.zh-CN.json`，
> 中文版的查看器外壳取自 archify 内置 `zh-CN` 目录，作者侧文字为中文）。

| 图 | 源文档 | 行范围 | 源图型 | archify 图型 | 交互产物 | 它回答的问题 |
| --- | --- | --- | --- | --- | --- | --- |
| `F01` | `README.md` | L55–97 | `architecture` | `architecture` | [f01-capabilities.html](archify/architecture-malabc-capabilities-20261009-2215/f01-capabilities.html) | 这个工具由哪几块能力组成？ |
| `F01` | `README_CN.md` | L49–91 | `architecture` | `architecture` | [f01-capabilities.html](archify/architecture-malabc-capabilities-20261009-2215/f01-capabilities.html) | 这个工具由哪几块能力组成？ |
| `F02` | `README.md` | L117–138 | `workflow` | `architecture` | [f02-binary-attribution.html](archify/architecture-binary-attribution-20261009-2340/f02-binary-attribution.html) | 一个名字为什么被判成 unresolved？三态归因各由什么证据支持？ |
| `F02` | `README_CN.md` | L110–131 | `workflow` | `architecture` | [f02-binary-attribution.html](archify/architecture-binary-attribution-20261009-2340/f02-binary-attribution.html) | 一个名字为什么被判成 unresolved？三态归因各由什么证据支持？ |
| `F03` | `README.md` | L195–206 | `workflow` | `workflow` | [f03-binary-attach.html](archify/workflow-binary-attach-20261009-2310/f03-binary-attach.html) | 一条命令怎么代替原来的两条？ |
| `F03` | `README_CN.md` | L184–195 | `workflow` | `workflow` | [f03-binary-attach.html](archify/workflow-binary-attach-20261009-2310/f03-binary-attach.html) | 一条命令怎么代替原来的两条？ |
| `F04` | `README.md` | L261–295 | `workflow` | `architecture` | [f04-layers.html](archify/architecture-malabc-layers-20261009-2340/f04-layers.html) | 单文件内核内部到底分了哪几层？输入与输出各是什么？ |
| `F04` | `README_CN.md` | L247–281 | `workflow` | `architecture` | [f04-layers.html](archify/architecture-malabc-layers-20261009-2340/f04-layers.html) | 单文件内核内部到底分了哪几层？输入与输出各是什么？ |
| `F05` | `README.md` | L338–348 | `workflow` | `architecture` | [f05-decision-point.html](archify/architecture-single-decision-point-20261009-2340/f05-decision-point.html) | 「解析不到的调用」是在哪里被判定的？ |
| `F05` | `README_CN.md` | L324–334 | `workflow` | `architecture` | [f05-decision-point.html](archify/architecture-single-decision-point-20261009-2340/f05-decision-point.html) | 「解析不到的调用」是在哪里被判定的？ |
| `F06` | `README.md` | L400–407 | `workflow` | `workflow` | [f06-fix-loop.html](archify/workflow-fix-loop-20261009-2310/f06-fix-loop.html) | 修复闭环的五个步骤是什么？失败回哪一步？ |
| `F06` | `README_CN.md` | L385–392 | `workflow` | `workflow` | [f06-fix-loop.html](archify/workflow-fix-loop-20261009-2310/f06-fix-loop.html) | 修复闭环的五个步骤是什么？失败回哪一步？ |
| `F07` | `README.md` | L447–454 | `workflow` | `workflow` | [f07-ci-gate.html](archify/workflow-ci-gate-20261009-2310/f07-ci-gate.html) | CI 里退出码是怎么算出来的？0 和 1 分别代表什么？ |
| `F07` | `README_CN.md` | L431–438 | `workflow` | `workflow` | [f07-ci-gate.html](archify/workflow-ci-gate-20261009-2310/f07-ci-gate.html) | CI 里退出码是怎么算出来的？0 和 1 分别代表什么？ |
| `F08` | `README.md` | L560–568 | `workflow` | `workflow` | [f08-baseline-nodeids.html](archify/workflow-baseline-nodeids-20261009-2310/f08-baseline-nodeids.html) | 基线门为什么比集合而不是比个数？ |
| `F08` | `README_CN.md` | L543–551 | `workflow` | `workflow` | [f08-baseline-nodeids.html](archify/workflow-baseline-nodeids-20261009-2310/f08-baseline-nodeids.html) | 基线门为什么比集合而不是比个数？ |
| `F09` | `docs/SUPERPOWER_REVIEW_R30.md` | L24–36 | `workflow` | `lifecycle` | [f09-superpower-loop.html](archify/lifecycle-superpower-loop-20261009-2340/f09-superpower-loop.html) | 一轮方法论闭环怎么走？探针不通过时回哪一步？ |
| `F10` | `docs/SUPERPOWER_REVIEW_R30.md` | L176–189 | `workflow` | `workflow` | [f10-guard-registry.html](archify/workflow-guard-registry-20261009-2340/f10-guard-registry.html) | 护栏是怎么被「登记」进测试与 CI 的？ |
| `F11` | `docs/SUPERPOWER_REVIEW_R44.md` | L182–200 | `workflow` | `workflow` | [f11-ir-attribution.html](archify/workflow-ir-attribution-20261009-2340/f11-ir-attribution.html) | 唯一判定点收拢后，用什么判据挡住它再次扩散？ |
| `F12` | `docs/analysis/ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT.md` | L72–107 | `workflow` | `architecture` | [f12-audit-layers.html](archify/architecture-audit-layers-20261009-2340/f12-audit-layers.html) | 仓库的真实分层结构是什么（含那条循环依赖）？ |
| `F13` | `docs/analysis/ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT.md` | L189–208 | `workflow` | `lifecycle` | [f13-agent-loop.html](archify/lifecycle-agent-loop-20261009-2340/f13-agent-loop.html) | agent_loop.py 的状态机怎么保证「不会留下改了一半的树」？ |

合计 **21** 条映射、**13** 张不同的图，每张图都有**英文与中文两版**（共 26 个交互 HTML）。

| 语种 | 图数 | HTML 合计（按图去重） |
| --- | --- | --- |
| 英文 `locale: en` | 13 | 9854186 字节 |
| 中文 `locale: zh-CN` | 13 | 9845424 字节 |
| **合计** | **26** | **19699610** 字节** |

## 逐图明细（节点 / 连线 / 说明卡数量，均取自 candidate.json）

| 图 | 节点 | 连线 | 说明卡 | 英文 candidate | 中文 candidate | 中文交互产物 | 导出源码 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `F01` | 8 | 7 | 7 | [`candidate.json`](archify/architecture-malabc-capabilities-20261009-2215/candidate.json) | [`candidate.zh-CN.json`](archify/architecture-malabc-capabilities-20261009-2215/candidate.zh-CN.json) | [f01-capabilities.zh-CN.html](archify/architecture-malabc-capabilities-20261009-2215/f01-capabilities.zh-CN.html) | [`README__01.mmd`](source/README__01.mmd) |
| `F02` | 9 | 10 | 3 | [`candidate.json`](archify/architecture-binary-attribution-20261009-2340/candidate.json) | [`candidate.zh-CN.json`](archify/architecture-binary-attribution-20261009-2340/candidate.zh-CN.json) | [f02-binary-attribution.zh-CN.html](archify/architecture-binary-attribution-20261009-2340/f02-binary-attribution.zh-CN.html) | [`README__02.mmd`](source/README__02.mmd) |
| `F03` | 5 | 3 | 2 | [`candidate.json`](archify/workflow-binary-attach-20261009-2310/candidate.json) | [`candidate.zh-CN.json`](archify/workflow-binary-attach-20261009-2310/candidate.zh-CN.json) | [f03-binary-attach.zh-CN.html](archify/workflow-binary-attach-20261009-2310/f03-binary-attach.zh-CN.html) | [`README__03.mmd`](source/README__03.mmd) |
| `F04` | 10 | 9 | 3 | [`candidate.json`](archify/architecture-malabc-layers-20261009-2340/candidate.json) | [`candidate.zh-CN.json`](archify/architecture-malabc-layers-20261009-2340/candidate.zh-CN.json) | [f04-layers.zh-CN.html](archify/architecture-malabc-layers-20261009-2340/f04-layers.zh-CN.html) | [`README__04.mmd`](source/README__04.mmd) |
| `F05` | 9 | 8 | 3 | [`candidate.json`](archify/architecture-single-decision-point-20261009-2340/candidate.json) | [`candidate.zh-CN.json`](archify/architecture-single-decision-point-20261009-2340/candidate.zh-CN.json) | [f05-decision-point.zh-CN.html](archify/architecture-single-decision-point-20261009-2340/f05-decision-point.zh-CN.html) | [`README__05.mmd`](source/README__05.mmd) |
| `F06` | 6 | 5 | 2 | [`candidate.json`](archify/workflow-fix-loop-20261009-2310/candidate.json) | [`candidate.zh-CN.json`](archify/workflow-fix-loop-20261009-2310/candidate.zh-CN.json) | [f06-fix-loop.zh-CN.html](archify/workflow-fix-loop-20261009-2310/f06-fix-loop.zh-CN.html) | [`README__06.mmd`](source/README__06.mmd) |
| `F07` | 6 | 5 | 2 | [`candidate.json`](archify/workflow-ci-gate-20261009-2310/candidate.json) | [`candidate.zh-CN.json`](archify/workflow-ci-gate-20261009-2310/candidate.zh-CN.json) | [f07-ci-gate.zh-CN.html](archify/workflow-ci-gate-20261009-2310/f07-ci-gate.zh-CN.html) | [`README__07.mmd`](source/README__07.mmd) |
| `F08` | 7 | 6 | 2 | [`candidate.json`](archify/workflow-baseline-nodeids-20261009-2310/candidate.json) | [`candidate.zh-CN.json`](archify/workflow-baseline-nodeids-20261009-2310/candidate.zh-CN.json) | [f08-baseline-nodeids.zh-CN.html](archify/workflow-baseline-nodeids-20261009-2310/f08-baseline-nodeids.zh-CN.html) | [`README__08.mmd`](source/README__08.mmd) |
| `F09` | 6 | 7 | 3 | [`candidate.json`](archify/lifecycle-superpower-loop-20261009-2340/candidate.json) | [`candidate.zh-CN.json`](archify/lifecycle-superpower-loop-20261009-2340/candidate.zh-CN.json) | [f09-superpower-loop.zh-CN.html](archify/lifecycle-superpower-loop-20261009-2340/f09-superpower-loop.zh-CN.html) | [`docs__SUPERPOWER_REVIEW_R30__01.mmd`](source/docs__SUPERPOWER_REVIEW_R30__01.mmd) |
| `F10` | 6 | 5 | 3 | [`candidate.json`](archify/workflow-guard-registry-20261009-2340/candidate.json) | [`candidate.zh-CN.json`](archify/workflow-guard-registry-20261009-2340/candidate.zh-CN.json) | [f10-guard-registry.zh-CN.html](archify/workflow-guard-registry-20261009-2340/f10-guard-registry.zh-CN.html) | [`docs__SUPERPOWER_REVIEW_R30__02.mmd`](source/docs__SUPERPOWER_REVIEW_R30__02.mmd) |
| `F11` | 6 | 5 | 3 | [`candidate.json`](archify/workflow-ir-attribution-20261009-2340/candidate.json) | [`candidate.zh-CN.json`](archify/workflow-ir-attribution-20261009-2340/candidate.zh-CN.json) | [f11-ir-attribution.zh-CN.html](archify/workflow-ir-attribution-20261009-2340/f11-ir-attribution.zh-CN.html) | [`docs__SUPERPOWER_REVIEW_R44__01.mmd`](source/docs__SUPERPOWER_REVIEW_R44__01.mmd) |
| `F12` | 16 | 20 | 3 | [`candidate.json`](archify/architecture-audit-layers-20261009-2340/candidate.json) | [`candidate.zh-CN.json`](archify/architecture-audit-layers-20261009-2340/candidate.zh-CN.json) | [f12-audit-layers.zh-CN.html](archify/architecture-audit-layers-20261009-2340/f12-audit-layers.zh-CN.html) | [`docs__analysis__ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT__01.mmd`](source/docs__analysis__ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT__01.mmd) |
| `F13` | 13 | 14 | 3 | [`candidate.json`](archify/lifecycle-agent-loop-20261009-2340/candidate.json) | [`candidate.zh-CN.json`](archify/lifecycle-agent-loop-20261009-2340/candidate.zh-CN.json) | [f13-agent-loop.zh-CN.html](archify/lifecycle-agent-loop-20261009-2340/f13-agent-loop.zh-CN.html) | [`docs__analysis__ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT__02.mmd`](source/docs__analysis__ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT__02.mmd) |

