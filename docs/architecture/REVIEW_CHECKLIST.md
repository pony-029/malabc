# 架构图评审清单

> 这张清单把“改一张图要过哪些门”从口口相传变成可执行步骤。
> 三道总闸：`check_architecture_docs.py`（AD1–AD9）、
> `export_arch_svg.py --check`（AD5 哈希）、
> `arch_compare.py`（base/head 版式差异）。

## 新增一张图

1. 写 `candidates/<id>.json`（`diagram_type` 必须是 architecture / workflow /
   lifecycle / dataflow / sequence 之一；`meta.output` 指向自己的 HTML）。
2. 校验并渲染（本机 archify）：

   ```bash
   node D:/work/rea/archify/archify/bin/archify.mjs validate <type> candidates/<id>.json --quality showcase
   node D:/work/rea/archify/archify/bin/archify.mjs render <type> candidates/<id>.json %TEMP%/<id>.html --quality showcase
   copy %TEMP%/<id>.html html/<id>.html
   ```

3. 登记 `FLOW_INDEX.json`（id/type/candidate/html/svg/title）。
4. 生成中文 SVG，写 `svg/MANIFEST.json`：

   ```bash
   python tools/export_arch_svg.py --all
   ```

5. 写英文 candidate（`en/candidates/<id>.json`，结构 id/边/计数必须与中文一致，
   **不得残留中文**，节点 label 必须命中 `GLOSSARY.md` 的规范译法），生成英文 SVG：

   ```bash
   python tools/build_arch_svg_en.py
   ```

6. 更新 `README.md` 表格与根 `README` / `README_CN.md` 的入口。
7. 跑门：

   ```bash
   python tools/check_architecture_docs.py
   python tools/export_arch_svg.py --check
   python tools/build_arch_svg_en.py --check
   python tools/build_module_graph.py --check
   python tools/build_ownership_table.py --check
   python tools/check_eol_convention.py
   ```

## 修改一张图

1. 先看版式差异：`python tools/arch_compare.py --id <id>`（delta HTML + receipt）。
2. 重渲染 HTML → `python tools/export_arch_svg.py --all` → 重导英文 SVG。
3. 若改了节点/连线 id，英文 candidate 必须同步；AD8 会抓 id/边/计数不一致。
4. 若只改文案，确认 AD6 的标签长度上限（标题 140 / 节点 48 / 连线 32 / 消息 36）。

## 删除一张图

1. 从 `FLOW_INDEX.json` 删条目。
2. 删 `candidates/<id>.json`、`html/<id>.html`、`svg/<id>.svg`、
   `en/candidates/<id>.json`、`en/svg/<id>.svg`。
3. `python tools/export_arch_svg.py --all` 重写 `svg/MANIFEST.json`。
4. 删 README / 根 README / `ARCHITECTURE_MAP.md` 里的入口；AD2 会抓“磁盘多出未登记文件”，
   AD3 会抓“README 还引用不存在的图”。

## 评审时问的 5 个问题

- [ ] 这张图只回答**一个问题**吗？标题能一句话说清吗？
- [ ] 每个节点都有 label 和（必要时）sublabel 吗？有没有空节点？
- [ ] 连线端点都在节点集合里吗？有没有“画了箭头但目标不存在”？
- [ ] sequence 的消息间距 ≥ 28、y ≥ 160 吗？段有没有越界？
- [ ] 英文版与中文版的 id/边/计数一致吗？英文版还有中文吗？
- [ ] 英文 label 命中了 `GLOSSARY.md` 的规范译法吗（AD9）？

## 责任人

- 模块 owner 见 `.github/CODEOWNERS`；AD7 会核对关键模块是否都有 `@` 开头的 owner。
- 架构文档本身归 `/docs/architecture/` 的 owner。

## 可选：提交前自动跑

```bash
python tools/install_git_hooks.py          # 接上 .githooks/pre-commit（只改本仓库配置）
python tools/install_git_hooks.py --check  # 只读检查是否接上
```

钩子只跑 5 道纯 Python 快跑门（AD / 归属表 / SVG 清单 / 英文 SVG / 模块图），
不需要 archify，也不会改工作区。
