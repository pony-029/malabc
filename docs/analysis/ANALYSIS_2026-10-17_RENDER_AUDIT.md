# 2026-10-17 · 渲染层审计：45 个 `render_*`、4,327 行，以及一个被推翻的假设

> 上一轮我写：「`emit_outputs` 调 5 个 `render_*`（1,777 行），而 `renderers/csite.py`
> 已有 1,749 行，**两处都能生成 HTML**，搬之前要先定谁是唯一出口。」
>
> 本轮按建议去“定出口”，量完发现：**这个前提是错的**。

---

## §0 一句话结论

`matlabc.py` 里有 **45 个 `render_*`、合计 4,327 行**（占全文 34,308 行的 **12.6%**），
而 `renderers/csite.py` 只有 **一个** 渲染入口 `render_c_site`——它服务 **C 前端**。
**两者不重叠，也不共享底层工具**（`csite.py` 自包含 `_esc/_num/_bar_svg/_graph_svg`，
`matlabc.py` 里没有同名函数）。

⇒ P2 的真实目标**不是“合并重复”**，而是 **“把 MATLAB 侧的 4,327 行搬出单文件”**。
上一轮那句“两处都能生成 HTML”必须撤回。

---

## §1 测量

| 项 | 读数 |
| --- | --- |
| `matlabc.py` 中 `render_*` 函数数 | **45** |
| 这些函数体总行数 | **4,327**（12.6% of 34,308） |
| `renderers/csite.py` 的渲染入口 | 1 个：`render_c_site` |
| `csite.py` 私有工具 | `_esc/_num/_flat/_clip/_force_layout/_graph_svg/_bar_svg/_donut_svg/_legend_html/_head/_cards/_read_lines/_write_text` |
| `matlabc.py` 中同名工具 | **0**（名称交集为空） |

### 最大的五个

| 行数 | 函数 | 性质 |
| --- | --- | --- |
| 573 | `render_source_page` | 单文件源码页 |
| 540 | `render_browse_site` | 分页站点总入口 |
| 279 | `render_browse_index` | 站点首页 |
| 240 | `render_markdown_report` | Markdown 报告 |
| 240 | `render_json` | **JSON 契约出口** |

---

## §2 为什么“重叠”这个判断错了

上一轮我把两件事混成了一件：

| 我原以为 | 实际 |
| --- | --- |
| `matlabc.py` 与 `csite.py` 都生成“分页站点”⇒ 重复 | `render_browse_site` 生成 **MATLAB** 站点；`render_c_site` 生成 **C** 站点。两种语言的页面集合不同（C 侧有 `binaries/dynlibs/attribution`，M 侧有 `file/*/class/complexity`） |
| 两者共享 HTML 工具 ⇒ 可以合并 | 名称交集为空；`csite.py` 的 `_esc/_bar_svg` 是它自己的，`matlabc.py` 用的是另一套写法 |

**教训**：「都叫 render」不等于「重复」。判据必须是**输出集合的交集**，不是函数名的相似度。

---

## §3 P2 的真实收益与代价

### 收益（可量化）

- `matlabc.py`：34,308 → 约 **29,981** 行（−12.6%）
- `render_json`（240 行）独立成文件 ⇒ **JSON 契约有了自己的边界**，改契约不再碰产品代码
- 45 个函数里 20 个是“单页”（`render_taint_page` / `render_todo_page` / `render_scaling_page`…），可以按主题分文件

### 代价（真实存在）

| 风险 | 说明 |
| --- | --- |
| 循环 import | `renderers/*` **不许**在模块级 `from matlabc import ...`（`check_import_graph` 的 G1 会红）；借用要走 `renderers/_late.py` |
| 45 个函数的隐式依赖 | 它们大量读 `model.xxx` / `files[].yyy`，属性名在 `matlabc.py` 里定义；搬走后要靠 `_late` 惰性引用 |
| 判据成本 | 每次搬都要跑站点指纹 + `--json` 指纹 + 一次整树重跑（775 秒） |

---

## §4 搬运顺序（按“独立度”排，不是按行数）

| 批 | 内容 | 为什么先搬 | 判据 |
| --- | --- | --- | --- |
| **B1** | `render_json` + `render_xml` + `render_markdown_report`（约 750 行） | **纯函数**：输入 `files/edges/stats/root`，输出字符串；无站点、无资源 | `--json` 逐字节不变 |
| **B2** | 20 个“单页”（`render_taint_page` / `render_todo_page` / `render_scaling_page` / `render_ai_prompts_page` …） | 每个只依赖一个 model 切片，互不调用 | `--browse` 站点对应页逐字节不变 |
| **B3** | `render_source_page` / `render_browse_site` / `render_browse_index`（1,392 行） | 它们互相调用、共享导航与资源；最后搬 | 整个 `--browse` 目录指纹不变 |

**B1 是最划算的第一步**：750 行、纯函数、判据是逐字节相等（不需要跑整树）。

---

## §5 与 P1 的关系

P1 已经让 `emit_outputs`（1,010 行）成为**唯一调用渲染的地方**——这正是 P2 能安全进行的前提：
搬走一个 `render_*`，只需改 `emit_outputs` 里的一处调用，那是 1,010 行里的 1 行，而不是散落各处。

---

## §6 下一步

1. **B1：搬 `render_json` / `render_xml` / `render_markdown_report` 到 `renderers/matlab_contract.py`**，
   判据 `--json` 逐字节 + `--xml` 逐字节。
2. B2：按主题把 20 个单页分到 `renderers/matlab_pages.py`。
3. B3：站点三个大函数搬到 `renderers/matlab_site.py`。
4. 每批一次提交、一次整树重跑（`matlabc.py` 字节会变）。
