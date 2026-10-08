# ANALYSIS 2026-10-08 · malabc README 双语化与 banner 视觉修正

> 归档依据：用户长期偏好 [88222452]——深度分析/文档治理类工作须归档到 `docs/analysis/`
> 并维护索引。本篇记录本轮"README 拆分为纯中/纯英双语 + banner 去斜去水印 + 文档链接修正"。

## ① 方法（工具 / 技能 / 取证层次）

- **工具**：Pillow（PIL）自绘 banner（可控、无外部模型、无水印）；Markdown 结构审计（逐节比对两个语言版本）。
- **技能**：superpower（现状盘点→根因→改进）+ brainstorming（视觉方案发散/收敛）。
- **取证层次**：README.md / README_CN.md 全文、docs/ 实际文件名清单、banner.jpg 像素内容、
  `.git/HEAD` 与 `.git/refs/heads/main` 直接读取（shell 被环境跳过时用文件读取代替）。

## ② 结论先行（状态表）

| 维度 | 修正前 | 修正后 | 判定 |
| --- | --- | --- | --- |
| README 语言 | 单文件**中英混排**（中文正文 + 英文 Overview 摘要） | `README.md` 纯英文 / `README_CN.md` 纯中文，逐节对应 | ✅ |
| banner 视觉 | 等距**倾斜**节点图（偏斜），含 "AI 生成 WORKBUDDY." 水印 | PIL 自绘**水平正视**布局，无文字、无水印 | ✅ |
| 图片宽度 | `width="100%"`（窄屏易拉伸错位） | 固定 `width="820"` | ✅ |
| 文档链接 | 指向不存在的 `docs/usage.md` 等（404） | 修正为真实文件 `docs/matlabc_USAGE.md` 等 | ✅ |

## ③ 证据

- README 引用 vs 实际：`docs/usage.md`→`docs/matlabc_USAGE.md`、`features.md`→`matlabc_FEATURES.md`、
  `json-schema.md`→`matlabc_JSON_SCHEMA.md`、`delivery-report.md`→`matlabc_DELIVERY_REPORT.md`。
- banner 自绘：1280×480，深蓝→青绿渐变 + 40px 网格 + 6 个圆角块水平排列 + 水平箭头；
  末两个块（红/琥珀）带柔和光晕标识风险热点；**零文字、零水印、无倾斜**。
- 版本锚点：本地 `main` 提交 `4b2653f`（上轮 MCP + 跑飞修复）；本轮文档改动在其之上。

## ④ 缺口清单（P0/P1/P2）

- **P0（本轮已落地）**：README 双语分离、banner 去斜去水印、文档链接修正。
- **P1**：`LICENSE_CN` 与 `LICENSE` 需再核对一句"英文正本优先"的表述是否双语一致。
- **P1**：README 中 CI badge 指向 `pony-029/malabc`，需确认组织/仓库名与远端一致。
- **P2**：为 banner 补一张暗色/亮色自适应版本（GitHub 主题切换）。

## ⑤ 建设性改进意见（可执行 + 优先级）

1. **立即（已落地）**：双语 README + 无斜无 watermark banner + 文档链接修正一并提交推送。
2. **近期**：加 `docs/README.md` 作为文档总入口，README 顶部只链一个 docs 索引，减少链接漂移。
3. **中期**：把 README 的"能力矩阵/命令速查"抽成 `docs/matlabc_CHEATSHEET.md`，两个语言版共享单一事实源。
4. **长期**：CI 增加"文档链接可达性"检查（扫描 README 内相对链接是否存在），防 404 回归。
