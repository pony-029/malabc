# 用户手册（本目录）

面向**使用者**的文档都放这里，一个目录管完：

| 文件 | 是什么 | 怎么来的 |
| --- | --- | --- |
| `USER_GUIDE.md` | **源文件**：安装、每个功能怎么用、常见问题 | 手写（唯一一份） |
| `matlabc-guide.pdf` | 同一份手册的 PDF，8 页，图印在页面上，适合转发 | `python tools/make_guide_pdf.py` |
| `figures/*.png` | 4 张示意图（关系面板 / CodeLens / 命令面板 / 热点排行） | `python tools/make_guide_figures.py` |

## 改手册的流程

```bash
# 1. 改文字：直接编辑 USER_GUIDE.md
# 2. 改了图或改了命令条数：重画
python tools/make_guide_figures.py
# 3. 重排 PDF（图与页数不对会返回非零，不许"看起来生成了"就交付）
python tools/make_guide_pdf.py
```

## 它们怎么进到扩展里

`tools/build_vsix.py` 按下面的映射打包，**包内保持相对结构**，
所以手册里的 `figures/x.png` 在安装后仍然能找到图：

```
releases/docs/USER_GUIDE.md      → extension/USER_GUIDE.md
releases/docs/figures/*.png      → extension/figures/*.png
releases/docs/matlabc-guide.pdf  → extension/USER_GUIDE.pdf
```

装好之后在编辑器里执行 **`matlabc: 打开使用说明`**（Markdown）
或 **`matlabc: 打开使用说明（PDF）`** 即可。

> 为什么图是"画"的而不是截屏：截图会随主题、字号、系统字体漂移，
> 而说明书需要跨版本看起来一样；截图里还常带着作者自己的工程路径。
> 每张图下方都标了「示意图」，不冒充截图。
