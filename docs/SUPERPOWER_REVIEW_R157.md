# R157 复盘：行尾污染的根因是「读时归一」，不是「写时用错 newline」

> 前两次（R110 的 68,456 行、R132 的 4 个 candidate）我都归因到
> `newline="\n"`。这次终于定位到真正的机制——它发生在**读**这一侧。

---

## §0 一句话结论

```python
t = io.open(P, encoding="utf-8").read()      # ← universal newlines 在这里把 CRLF 变成 LF
io.open(P, "w", encoding="utf-8", newline="").write(t + add)
```

**写侧的 `newline=""` 是对的，读侧漏了。** 于是「只追加 33 行」的脚本把整个文件改写成了 LF。

---

## §1 三次事故的对照

| 次 | 轮 | 规模 | 怎么发现的 |
| --- | --- | --- | --- |
| 1 | R110 | 68,456 行 diff | `check_kernel_snapshot` 报「字节少了 34,228」——那时已经提交 |
| 2 | R132 | 4 个 `candidate.json` | `check_eol_convention` 的前身（探测脚本） |
| 3 | **R157** | **135 个裸 LF** | **EO1 在提交前抓到** |

**第三次是唯一一次在提交前拦下的。** 这正是 R117 把 `eol_probe` 升级成第 24 道门的价值。

---

## §2 两条硬规则（已写进 `CONTRIBUTING`）

| 规则 | 内容 | 后果 |
| --- | --- | --- |
| 写 | `io.open(path, "w", encoding="utf-8", newline="")` | 否则 `\n` 转成平台默认 |
| **读** | `io.open(path, "r", encoding="utf-8", newline="")` | 否则 CRLF 在**读取时**就被归一成 LF |

**第二条更危险**，因为脚本看起来只改了 33 行，`git diff --stat` 却显示 135 增 / 124 删。

---

## §3 P2 的精确分批

按「依赖是否全在 `renderers/html_kit.py`」划分：

| 批次 | 函数数 | 行数 |
| --- | --- | --- |
| 第一批（3 叶子，deps=0） | 3 | **94** |
| **第二批（deps 全在 kit）** | **6** | **474** |
| 合计可搬 | **9** | **568**（13% of 4,327） |

第二批：`render_compliance_page`(193) / `render_checks_page`(95) /
`render_operator_impact_page`(67) / `render_mermaid`(48) /
`render_ai_prompts_page`(38) / `render_dot`(33)。

**每个只有一个依赖，且那个依赖已经在 `html_kit` 里。**

剩余 36 个被挡住的归类：`_collect_*`（8）、`*_JS`（6）、`_build_*_data`（4）、
其它渲染（3）、重依赖 ≥10（6）。⇒ **下一个瓶颈是分析函数与前端常量，不是渲染本身。**

---

## §4 状态

```
check_eol_convention  OK（326 个文本文件）
check_py36_clean      OK（95 个 .py）
check_all             23/24（W2，探针 19:33:59 启动，已 20+ 分钟）
```

**探针的内存打到了 8,085 MB（峰值 8,190），CPU 951s —— 接近完成。**

---

## §5 下一步

1. 探针收口（连续第六轮挂着）。
2. P2 执行：先 3 个叶子，验判据，再 6 个。
3. `--checks default` 对照：若产物与 `all` 字节相同，以后内核读数可省 15 分钟。
