# 使用演示

`matlabc-tour.gif` —— 16 秒，四个场景，覆盖主要功能。

**怎么看**：双击文件，用系统图片查看器打开（Windows 照片、macOS 预览都支持 GIF 动画）。

> 扩展详情页里**不放图**：本地安装的扩展，详情页无法加载包内图片，
> 显示出来只有一个破图标。需要看图时直接打开本目录的文件。

---

## 四个场景分别在讲什么

| 场景 | 画面 | 对应功能 |
| --- | --- | --- |
| **1 大纲** | `Ctrl+Shift+O` 弹出函数列表，选中后跳到定义 | 快速看一个文件里有哪些函数 |
| **2 转到定义** | 光标停在 `callpop_solver` 上，`F12` 跳到它所在文件 | 函数 / 类方法 / 结构体成员都能跳 |
| **3 关系面板** | 光标停在函数名上，右侧出现「上游 / 下游」，展开后点任一跳转 | **核心交互**：不用离开代码就能看调用关系 |
| **4 热点排行** | 命令面板执行「热点函数排行」，按复杂度与调用者数排序，选中即跳 | 决定先读哪几个函数 |

---

## 还有两个没放进动图的功能

| 功能 | 怎么用 |
| --- | --- |
| **HTML 分析报告** | 命令面板 → `matlabc: 生成 HTML 分析报告`，浏览器自动打开 |
| **AI 助手接入** | 命令面板 → `matlabc: 生成 MCP 配置`，按提示写入配置文件 |

这两个是一次性动作，静态截图比动图更清楚，所以没有做进循环演示。

---

## 可逐帧播放的交互导览

`matlabc-tour.html` —— **双击打开**，8 步自动播放，也可以点任意模块跳到讲它的那一步。

| 文件 | 作用 |
| --- | --- |
| `matlabc-tour.architecture.json` | **唯一事实来源**：12 个模块、11 条连线、3 张说明卡 |
| `matlabc-tour.html` | 由上面那份 JSON 渲染出的可播放页面（11.9 KB，单文件、离线） |

**为什么不是 `archify render` 直接产出的**

JSON 用的是 archify 的 architecture 格式，`archify validate` 可以通过：

```
ok architecture ... (9 artifact checks; composition standard: 0 errors, 0 warnings)
```

但 `archify render` 在本机必定失败：

```
[output/target-hardlinked] Temporary output candidate has multiple hard-link names.
evidence: { "code": "candidate-hardlinked", "links": "2" }
```

原因是它的发布协议：写候选 → 建硬链接作为正式名（链接数 2）→ 回收暂存名
→ **校验链接数必须回到 1**。而本机的删除会进回收站（`fsutil hardlink list`
能看到链接被移进 `$RECYCLE.BIN`），**计数永远是 2**，校验永远不过。

这是环境差异，不是 JSON 写错。换一台删除不进回收站的机器，可以直接：

```
node D:/project/archify/archify/bin/archify.mjs render architecture \
     releases/demo/matlabc-tour.architecture.json releases/demo/matlabc-tour.html
```

**怎么重新生成页面**

```
python tools/make_tour_html.py
```

它读上面那份 JSON，输出的仍是同一个 HTML —— 改模块、改连线只改 JSON，
改讲解词改脚本里的 `STEPS`。

---

## 想重新生成

演示图是脚本逐帧绘制的，不是录屏：

```
python tools/make_tour_gif.py
```

改文案、改配色、加场景都只改脚本，不必重新录制。
