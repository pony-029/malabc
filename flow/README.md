# flow/ —— 全部流程图的普查、重绘与详解

这个目录是 **malabc 全部流程图的第二次生命**：把散落在 README 与 docs 里的 mermaid 块，
一只不少地找出来，逐字节导出，再用 **archify** 重绘成可交互的独立 HTML（**中英双语各一套**），
并给每一张图写一份**能落地核对**的详解。

## 目录导航

| 文件 / 目录 | 是什么 | 怎么来的 |
| --- | --- | --- |
| [`FLOW_REPORT.md`](FLOW_REPORT.md) | **主文档**：13 张图逐张详解 + 本轮实测到的环境事实 + 下一步建议 | 人工撰写，数字全部实测 |
| [`INDEX.md`](INDEX.md) | 21 个 mermaid 块 ↔ 13 张图的映射表（含行范围、图型、体积、节点数） | 脚本生成，只读 |
| [`FLOW_INDEX.json`](FLOW_INDEX.json) | 上表的机器可读版本 | 同上 |
| [`FLOW_CENSUS.json`](FLOW_CENSUS.json) | 普查结果：每个块的文件、行号、所在小节、图型、原始正文 | `_r45/census_flow.py` |
| [`source/`](source/) | 21 个 mermaid 块**逐字节导出**（含 CRLF 行尾，与源文档一致）+ `INDEX.md` | `_r45/scaffold_flow.py` + `_r45/normalize_flow_eol.py` |
| [`archify/`](archify/) | 13 套 `candidate.json`（英文可编辑源）+ 13 套 `candidate.zh-CN.json`（中文可编辑源）+ **26** 个渲染产物 `.html`（13 英文 + 13 中文） | `archify render` |
| [`diagrams/`](diagrams/) | **26 个独立 SVG**（13 张 × 中英两套）——README 里直接看得见的那一份 | `_r47/extract_svg.py`（从产物里取出，不是截图） |

## 一眼看懂：13 张图分别回答什么

| 图 | 图型 | 源锚点 | 它回答的问题 |
| --- | --- | --- | --- |
| `F01` | architecture | `README.md` L55–97 | 这个工具由哪几块能力组成？ |
| `F02` | architecture | `README.md` L117–138 | 一个名字为什么被判成 unresolved？三态各由什么证据支持？ |
| `F03` | workflow | `README.md` L195–206 | `--binary-attach` 到底省了什么？ |
| `F04` | architecture | `README.md` L261–295 | 单文件内核内部分了哪几层？输入输出各是什么？ |
| `F05` | architecture | `README.md` L338–348 | 「解析不到的调用」在哪里被判定？ |
| `F06` | workflow | `README.md` L400–407 | 修复闭环五步是什么？失败回哪一步？ |
| `F07` | workflow | `README.md` L447–454 | CI 退出码怎么算出来？ |
| `F08` | workflow | `README.md` L560–568 | 基线门为什么比集合不比个数？ |
| `F09` | lifecycle | `docs/SUPERPOWER_REVIEW_R30.md` L24–36 | 一轮方法论闭环怎么走？ |
| `F10` | workflow | `docs/SUPERPOWER_REVIEW_R30.md` L176–189 | 护栏怎么被登记进测试与 CI？ |
| `F11` | workflow | `docs/SUPERPOWER_REVIEW_R44.md` L182–200 | 唯一判定点收拢后，用什么挡住它再扩散？ |
| `F12` | architecture | `docs/analysis/ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT.md` L72–107 | 仓库真实分层是什么？循环依赖在哪？ |
| `F13` | lifecycle | `docs/analysis/ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT.md` L189–208 | 怎么保证不留下改了一半的树？ |

`README_CN.md` 的 8 张图与上表 F01–F08 **同构**（标签语言不同），不另编号。

## 怎么重新生成

```bash
# 普查 + 导出（仓库外脚本，只读仓库）
python E:/matlabc/_r45/census_flow.py
python E:/matlabc/_r45/scaffold_flow.py
python E:/matlabc/_r45/gen_flow_index.py      # 生成 INDEX.md / FLOW_INDEX.json

# 重绘一张（以 F01 为例）
cd /e/matlabc/malabc/flow
node E:/matlabc/_r45/archify-probe/bin/archify.mjs render architecture \
  archify/architecture-malabc-capabilities-20261009-2215/candidate.json \
  archify/architecture-malabc-capabilities-20261009-2215/f01-capabilities.html \
  --quality showcase

# 取独立 SVG：把 26 个产物里那张图取出来（仓库外脚本，只动临时副本）
python E:/matlabc/_r47/extract_svg.py

# 验证：把「产物自己的渲染路径」与「独立 SVG 的渲染路径」放进同一文档逐元素比
python E:/matlabc/_r47/verify_svg.py --ref-theme light

# 中文版：先生成中文候选（结构不变式在这里断言），再渲染 26 张图（含逐字节复验）
python E:/matlabc/_r45/make_zh_candidates.py
python E:/matlabc/_r45/render_zh.py
```

## 六条使用纪律

1. **改图只能改 `candidate.json`，不要手改 `.html`** —— HTML 是渲染产物。
2. **改了源文档的 mermaid，必须重新导出 `source/*.mmd`**，否则两边静默分叉。
   理想情况下这一步应该由 CI 检查（见 `FLOW_REPORT.md` §16 第 1 条）。
3. **`archify finalize` 在本机不可用**（本机 Node 无法 spawn 子进程，`EBUSY`）；
   本目录的产物全部由 **`archify render`** 产出（进程内布局校验 + 落盘，rc 全 0）。
   细节与原因见 `FLOW_REPORT.md` §14。
4. **行尾分两类**：`.html` 是生成物，按渲染器原始字节（LF）入库 ——
   这样「重跑 `render` == 仓库里的文件」是可验证的等式；`.md` / `.json` / `.mmd`
   是手写物，按仓库约定归一 CRLF。`_r45/normalize_flow_eol.py` 同时对两类做断言。
5. **中英两版必须同骨架**：中文候选由 `make_zh_candidates.py` **从英文候选复制、只换字符串**得到，
   并断言「清空所有字符串后两份文件结构逐键逐序完全相同」。所以改了英文的几何或节点后，
   中文侧的 `candidate.zh-CN.json` 必须**重新生成**，不要手改 —— 否则骨架会静默分叉。
   locale 必须写 **`zh-CN`**：archify 的内置目录只有 `en` 与 `zh-CN`，写成 `zh` 会被
   **静默回退**成英文查看器外壳（`i18n/locale-fallback`）。

6. **README 里嵌的是 `flow/diagrams/` 里的独立 SVG，不是截图**。它们由
   `_r47/extract_svg.py` 调 **archify 自己的** `serializeSvg()` 取出（只是把闭包里的函数
   临时暴露给临时副本，产物 HTML 与 archify 原仓库都是零改动）。所以**重新渲染 HTML 之后
   必须重新取 SVG**，否则两边会静默分叉。`tools/check_flow_diagrams.py` 会把
   「README 里的引用 ↔ `diagrams/` 里的文件 ↔ `candidate*.json` 里的声明」两两对齐，
   中英成对、骨架同构、形态自足（无外链 / 有双主题 / 自带背景 / 保留 LF）都在这道门里；
   `flow/FLOW_INDEX.json` 也在这道门里 —— 索引漏登记、或登记的体积与磁盘不符，一样红。

## 与 `D:\project\archify` 的关系

本目录**没有修改** archify 原仓库。为了绕过本机「删除 = 移到回收站」导致
硬链接发布失败的问题，仅在**仓库外的临时副本** `E:\matlabc\_r45\archify-probe\`
上打了一个最小 host-compat 补丁（同卷 `renameSync` 发布 + 放宽「恰好 1 个链接名」的上界）。
补丁内容与理由记在 `FLOW_REPORT.md` §14.2。
