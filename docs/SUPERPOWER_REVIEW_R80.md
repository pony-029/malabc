# R80 / C29-1 复盘 —— `--json-level`：三档 JSON

> 方法论：superpower 六顶思考帽（白 → 红 → 黑 → 黄 → 绿，蓝帽收束）。
> 每一项读数都来自**仓库外仪器**（`E:\matlabc\_r80\`），并且**在定稿后的代码上重测过一次**
> —— 中途 reshape 过载荷（见 §7-D1），旧读数一律作废重取。

## 0 一句话结论

R79 §9 的最高优先项 **C29-1** 已落地：JSON 由两档扩成**三档**
`--json-level=full|lite|summary`。整树级 C 语料由 GB 级降到 **MB 级**
（`drivers/net` 6,086 文件：253.05 MB → **931.8 KB**，-99.6%），
而「丢掉的明细有多少条」永远数得出来（顶层 `summary` 计数块 + **计数守恒**判据）。
既有的 `full` / `lite` 输出**顶层键序逐位不变**，只多插一行 `json_level`。

## 1 蓝帽：分析对象与目标

| 项 | 内容 |
| --- | --- |
| 对象 | `matlabc.py` 的 JSON 输出层（C 前端 `_run_c_only` + 扩展前端 `_run_ext_only`） |
| 目标 | 让整树级语料有一档**能传输、能 diff、能上云**的 JSON |
| 判据 | ① 明细粒度单调递降；② **计数守恒**；③ 旧键逐位不变；④ 两向自证 |
| 不做 | 不动 HTML 站点、不动 `--binary-attach` 归因语义、不动 `VERSION` |

## 2 白帽：先量字节构成（**不猜**）

R79 的反直觉发现是「`--no-annotations` 在 C 上只省 19%–49%」——
说明大头**不是注释**。所以本轮第一件事是把 JSON 逐层拆开量。

`lib`（651 文件，`--lang c --checks none`，共 19.31 MB）：

| 层级 | 键 | 字节 | 占比 |
| --- | --- | --- | --- |
| 顶层 | `files` | 8.16 MB | 42.2% |
| 顶层 | `unresolved` | 1.37 MB | 7.1% |
| 顶层 | `edges` | 1.23 MB | 6.4% |
| 顶层 | `include_edges` | 202.7 KB | 1.0% |
| `files[]` 内 | `comments` | 5.70 MB | 70.3% |
| `files[]` 内 | `functions` | 1.93 MB | 23.8% |
| `files[]` 内 | `asm` | 426.7 KB | 5.1% |

`security` **默认档**（`--checks all`，7.76 MB）里 `heuristics` 单键 **908.8 KB = 11.4%**。

**这三条量完，设计就没有自由度了**：`lite` 删掉的是最大的一块（注释），
但剩下的 `functions` / `edges` / `unresolved` / `heuristics` **互不重叠**，
必须一起处理 —— 这就是 `summary` 档的由来。
（取证仪：`_r80/measure_compose_r80.py`。）

## 3 设计：三档语义（明细粒度上的单调链）

| 档位 | 逐文件载荷 | 顶层明细键 | 顶层新增 | `json_level` | `annotations` |
| --- | --- | --- | --- | --- | --- |
| `full`（默认） | rel + includes + macros + functions + **comments + asm** | edges / include_edges / unresolved / heuristics | — | `"full"` | `true` |
| `lite` | rel + includes + macros + functions | 同上（**都还在**） | — | `"lite"` | `false` |
| `summary` | **rel + 5 个计数**（一行签名） | **全不写** | `summary` 计数块 + `heuristics_by_kind` | `"summary"` | `false` |

规则只有一条：`--no-annotations` 只会让结果**更瘦，永不更胖**。于是
`--json-level=full --no-annotations` ⇒ `lite`，而
`--json-level=summary --no-annotations` ⇒ 仍是 `summary`。

不认识的档位（配置文件可以把它写成任意字符串，而 argparse 的 `choices` 只管命令行）
**降级为 `full`** —— 宁可多给数据，也不要因为一个错别字把明细静默丢掉。

## 4 实现

| 位置 | 改动 |
| --- | --- |
| `_json_level(args)` | 新增。把两个开关归约成唯一档位；未知值降级为 `full` |
| `_annotations_on(args)` | 改为 `_json_level(args) == "full"` —— 让布尔与档位**同源**，不再各说各话 |
| `_c_file_payload(pf, level)` | `detail` 布尔 → `level` 三档；summary 输出 6 键签名 |
| `_ext_file_payload(pf, level)` | 同上；summary 把每条**明细数组**降级为 `n_<键名>`，丢掉两个直方图，标量与小字典照旧 |
| `_EXT_SUMMARY_DROP_KEYS` | 新增登记：`insn_hist` / `excluded_hist`（桶数被截过，本身不是信息） |
| `_c_summary_counts` / `_ext_summary_counts` | 新增：每语料一行计数块（判据是计数守恒） |
| `_heuristics_by_kind` | 新增：启发式明细 → 按规则的直方图（键排序，两次运行逐字节一致） |
| `_run_c_only` / `_run_ext_only` | 载荷按档分派；**两档各写一个完整字典字面量**（理由见 §7-D1） |
| argparse | 新增 `--json-level {full,lite,summary}`；`--no-annotations` 的 help 指向它 |

## 5 实测读数（reshape **之后**重测）

| 语料 | argv | 文件 | full | lite | summary | vs full | vs lite |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `lib` | `c --checks none` | 651 | 19.31 MB | 8.98 MB | **105.4 KB** | -99.5% | -98.9% |
| `security` | `c --checks none` | 258 | 6.63 MB | 4.81 MB | **43.5 KB** | -99.4% | -99.1% |
| `security` | `c (默认 --checks all)` | 258 | 7.76 MB | 5.95 MB | **51.7 KB** | -99.3% | -99.2% |
| `drivers/net` | `c --checks none` | 6,086 | 253.05 MB | 193.71 MB | **931.8 KB** | -99.6% | -99.5% |
| `(整树 .S)` | `asm (默认)` | 1,369 | 17.37 MB | 215.6 KB | **449.6 KB** | -97.5% | +108.6% |

关键三例：

* `lib`（651 文件）：19.31 MB → 8.98 MB（-98.9%）→ **105.4 KB**（-99.5%）；
* `drivers/net`（6,086 文件，占全 C 家族的 9.7%）：253.05 MB → 193.71 MB（-23.5%）→ **931.8 KB**（-99.6%）；
* 整树 `.S`（1,369 文件）：17.37 MB → 215.6 KB（-98.8%）→ 449.6 KB（**+108.6%**）。

> 外推（**明确标注为外推，不是实测**）：按 `drivers/net` 占全 C 家族 6,086 / 62,704
> 的比例线性外推，整树 C 的 JSON 约 full 2.5 GB / lite 1.9 GB /
> summary 9.4 MB。外推只在「文件间均匀」这个假设下成立，而实测已经**证伪**了均匀性
> （`lib` 的注释密度远高于 `drivers/net`），所以这三个数只能当**量级**看。

## 6 反直觉读数（本轮最值钱的三条）

**① C 侧 `lite` 只省 -23.5%，`summary` 才省 -99.6%。**
`drivers/net` 6,086 文件：`lite` 删掉全部注释与内联汇编明细，只省 23.5%；
真正的大头是 `functions` / `edges` / `unresolved`（`include_edges` 亦然），
而它们**不是注释**。R79 已经摸到这条边界，本轮把它量成了确定数。

**② 汇编侧 `summary` **大于** `lite`（+108.6%）。**
整树 `.S`：full 17.37 MB → lite 215.6 KB → summary 449.6 KB。
原因是 `lite` **已经**把行级明细数组删光了，`summary` 反而要**写回**每文件计数。
所以「三档单调变瘦」只在**明细粒度**上成立，**体积**上不成立 ——
这条我在第一版 docstring 里写错了，是**自己的实测量打了自己的脸**（见 §7-D2）。
它值得留在文档里：下一轮很可能有人想拿「三档单调变瘦」当不变量去断言。

**③ `heuristics` 在默认档本身就是一个大块（`security` 908.8 KB / 11.4%）。**
默认 `--checks all`，所以整树级 C 语料即便用 `lite` 也照样背着这份明细；
`summary` 把它压成 `heuristics_by_kind` 直方图（几条规则 → 几个数）。

## 7 缺陷与修复（四条，**都是我自己这一轮造的**）

| 编号 | 现场 | 根因 | 修法 |
| --- | --- | --- | --- |
| D1 | `check_ir_attribution` 报**两条** I1：`_run_c_only` / `_run_ext_only` 是未登记写点 | 我用了 `payload["unresolved"] = [...]` 这种**下标赋值**，而那道门按 `Assign(Subscript("unresolved"))` 收集写点 —— 它与「新建第二个 unresolved 容器」在 AST 上**无法区分**。那张表按独立实测只该有 **3** 处，第 4 处判红是**对的** | **改我的写法**：两档各写一个完整**字典字面量**（同一语义，形态是门已建模的那一种）。输出键序**逐位不变**（用 `object_pairs_hook` 核过）。**没有**放宽那道门的判据 |
| D2 | docstring 与 `--help` 里写着「三档单调变瘦」 | 这句在汇编档是**反的**（§6-②） | 改成可证伪的说法：「**明细粒度**单调递降（逐条记录 → 计数 → 无）；体积单调下降只在 C 侧成立」 |
| D3 | `patch_r80e.py` 的收尾核验**误伤自己的注释** | 判据写成 `'["unresolved"] = ' in text`，而我在同一文件里解释这个字符串时正好引用了它 | 收紧为只认**代码行**：`^\s*\w+\["unresolved"\]\s*=\s`（注释行以 `#` 起头，`#` 不是 `\w`） |
| D4 | `patch_r80d.py` 的收敛循环**永远收敛不了**，且把「门绿」读成「门红」 | ① 门读**磁盘**、我改**内存**，只写一次必然死循环；② `return p.returncode, p.communicate()[0]` 里 `returncode` 在 `communicate()` **之前**求值 ⇒ 恒为 `None` | ① 每轮**落盘**；② 先 `communicate()` 再取 `returncode` |

> D1 值得单说：它是本轮唯一一次「门禁红**而且红得对**」的现场。
> 我没有去动那道门，而是动了我的写法 ——
> 改判据会让「写点恰好 3 处」这句实测结论失效，那是**削弱装置**，不是修缺陷。

## 8 验证矩阵

| 判据 | 结果 |
| --- | --- |
| 三档形状（键在与不在 / `json_level` 自报 / 每文件签名恰好 6 键） | 5 条 R80 测试全绿 |
| **计数守恒**（summary 的每个数 == full 明细长度，含**逐文件**逐项） | 全绿，并带**防空转**断言（`functions==3` / `edges>=2` / `comments>=2` / `asm_statements==1`） |
| **向后兼容** | 与基线克隆（R79 = `c2bfb0d`）逐键对照：旧键值**全等**，新增键**恰好只有** `json_level`；顶层键序只多插一行 |
| 纯函数九种输入（含 `bogus` / `""` / `None` / 缺属性） | 全绿 |
| 两向变异 | **6 变异体：注入即红、还原即绿；NEGCTRL 一对：保持绿** |
| 全量 FAILED 集合差 | 基线 123 / 当前 123，**新增 0 / 消失 0** |
| 门禁 `tools/check_all.py` | check_all: OK（17 个护栏，全部通过且各自自证；门数下限 17） |
| 帮助体积棘轮 | `--help` 合法增长 51371 → 52418（+1047 B）、规范形 42736 → 43560（+824 B）；同一提交里更新快照，**没有**放宽 `HELP_DRIFT_BYTES` |
| 行尾纪律 | 本轮所有改动文件 `bare_lf == 0` |

## 9 诚实边界（本轮**没有**解决的）

| 项 | 说明 |
| --- | --- |
| `summary` 不是"智能裁剪" | 它是**形态**档：不做任何重要性判断，`functions` 明细只剩计数（Top-N 见 §10 的 C30-4） |
| 外推数只是量级 | §5 的整树 C 外推建立在"文件间均匀"上，而实测已**证伪**均匀性 |
| 汇编侧 summary 更大 | §6-② —— 有意为之；**不要**把它当 bug 去"优化"掉计数 |
| HTML 站点未接档 | `--browse` 的分页站点与 JSON 档位**无关**（它自己按文件分页，本来就是 KB 级） |
| `--json-level` 的配置面 | 走 `cfg.get("json_level", ...)`，但 `analyzer_config.example.json` 至今未入库（C16-6 旧账） |
| 语义验证 | 依旧不做（本仓零依赖 + Py3.6.5 用不了 libclang，R77/R78 已登记） |

## 10 下一轮建议（C30）

| 编号 | 优先级 | 内容 | 依据（本轮实测） |
| --- | --- | --- | --- |
| **C30-1** | 最高 | **方言 / 异语言分类显式化**：`.lds.S` → `kind="lds"`；m68k 点号省略指令 → 归数据；ARM `@` → 注释 | R79 §9 的 C29-2 仍未做，而它现在**有量化依据**：`excluded_hist` 头部 `@` 907 / `}` 772 / `{` 334 /（`short`+`long`）3,528 |
| **C30-2** | 高 | **C-2 源码视图** `renderers/sview.py`（数据层已就绪：注释 + 内联汇编都在模型里） | R77 §9 的 C-2；R78/R79/R80 已把数据备齐 |
| **C30-3** | 高 | **C-3 译文层**（术语词典 + 内容寻址缓存 + 可插拔后端） | `comment_stats` 已量化：内核 m68k `\|` 注释 6,477 条也是文档 |
| **C30-4** | 中 | `summary` 档加 `--summary-top=N`：把 `edges` / `unresolved` 的 **Top-N** 也带上 | 本轮把明细全丢了；但"最多的 N 条调用边"往往正是人要看的那几行 |
| **C30-5** | 中 | 段栈：`.pushsection` / `.popsection` / `.previous` | 段状态机的已知缺口（R79 遗留） |
| **C30-6** | 中 | 汇编具名操作数 `%[name]` → `%N` 回填；`_asm_file_model` 的 `rel` 仍是 basename | R78 遗留（C28-5 / C28-6） |

另有两件**需要拍板**的旧账（R78 起就提，仍未决）：
**C16-6**（`fe_audit.py` 等 6 件「从未提交的产物」——补齐还是永久登记为「不做」；
其中 `setup.py` / `analyzer_config.example.json` 属于「补文件就能拿回」的一类）；
以及 `flow/` 图册（archify）上次更新停在 10-10。

## 11 复现命令

```bash
PY="C:/Program Files/Python310/python.exe"

# 门禁（17 道，含各自自证）
$PY tools/check_all.py

# R80 单测（选择器要排除名字里含 r80 的永久红 site_e2e）
$PY -m pytest tests/test_matlabc.py -q --no-header -p no:cacheprovider \
    -k "(r80 and not site_e2e) or (r79 and not site_e2e)"

# 冒烟 + 兼容性 + 计数守恒（40+ 项）
$PY E:/matlabc/_r80/smoke_r80.py

# 两向变异（只动副本）
$PY E:/matlabc/_r80/mutate_r80.py

# 三档体积实测
$PY E:/matlabc/_r80/measure_r80.py

# 字节构成取证（本轮的设计依据）
$PY E:/matlabc/_r80/measure_compose_r80.py security lib

# 全量 FAILED 集合对照（基线 = R79 的 clone，**带 .git**）
$PY E:/matlabc/_r80/testdiff_r80.py
```

## 附录 A：本轮改动的文件

| 文件 | 改动 |
| --- | --- |
| `matlabc.py` | 新增 `_json_level` / `_c_summary_counts` / `_ext_summary_counts` / `_heuristics_by_kind` / `_EXT_SUMMARY_DROP_KEYS`；`_annotations_on` 改为**档位派生**；`_c_file_payload` / `_ext_file_payload` 由 `detail` 布尔改为 `level` 三档；`_run_c_only` / `_run_ext_only` 按档分派（**完整字典字面量**，见 §7-D1）；argparse 新增 `--json-level`。现 32690 行 / 1628828 字节 |
| `tests/test_matlabc.py` | 5 条 R80 测试（三档形状 / 计数守恒 + 防空转 / 未知档位降级 / 汇编签名 / 可发现性）。现 20967 行 / 1088048 字节 |
| `README.md` / `README_CN.md` | **同行内追加** R80 段（双语对等，行数不变） |
| `tools/check_help_contract.py` | 两处快照：51371 → 52418 / 42736 → 43560 |
| `docs/SUPERPOWER_REVIEW_R80.md` | 本文件 |

> 仓库外仪器（`_r80/`，**不入库**）：`patch_r80*.py`（全或无补丁）、
> `measure_compose_r80.py`（字节构成）、`measure_r80.py`（三档体积）、
> `smoke_r80.py`（冒烟/兼容/守恒）、`mutate_r80.py`（两向变异）、
> `testdiff_r80.py`（FAILED 集合差）、`write_r80_doc.py`（本文件生成器）、
> `base_clone/`（R79 基线 clone）、`mut_r80/`（变异副本）。
