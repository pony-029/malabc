# 全树规模读数 + 分析流程 · 登记表

> **这不是判据，是一次登记的读数。** 由 `_r82/gen_kernel_run_doc.py` 从实测
> `AGG_r84.json` + 两遍文件系统扫描 + 流程站表生成；门
> `tools/check_kernel_snapshot.py`（判据族 **W1–W6**）钉住它：出处 + **口径**、
> 三档分母**并列**、汇总↔明细**恒等式**、与 R81 基线**逐位且逐类**对照、
> 唯一事实源指针与跨文档分母一致，以及**流程站表 / 恰一个 current 驱动 /
> 产物链拓扑 / 仓内落点存在**（W6）。

生成命令：`python _r82/gen_kernel_run_doc.py`（`--check` 只比对不写盘）。

## 0. 分析流程（这张表是从哪来的）

在这之前，「内核分析流程在哪」是一个**没有对手方**的问题（L85）：它只活在
8 个脚本的 docstring 里，散在 `_kernel/`（R75–R81）与 `_r82/`（R84）两棵
**仓外**树 —— **没有任何一处能回答「有哪几站、该跑哪一代」**。

代价是实测过的：盘上同时躺着**三代驱动**，其中 `rerun_kernel_r81.py` 的
`OUT` 写死 `r81/` 且按 label 合并 ⇒ **再跑一次就会就地覆盖对照基线**，
而这件事只写在那份脚本自己的 docstring 里。

口径三条，先说清楚，否则下表会读成两种意思：

1. **仓外路径的存在性本门不裁决。** 站表里绝大多数脚本在
   `E:\matlabc\_kernel\` —— 那**不在本仓里**，新克隆里根本不存在。
   把它们判成红，就会造出一道**只在开发机上绿**的门（L59 的镜像）。
   所以存在性判据只落在仓内落点上（W6e），仓外站数只做**读数**。
2. **`status` 是闭集**（`current` / `superseded` / `auxiliary`），非 `current`
   的站**必须写 `why`** —— 退役理由不写下来，下一个人就得把这条死路重走一遍。
3. **链不是「列出来」而是「接得上」**：每一站的 `in` 必须出现在**某个前序站的
   `out`** 里。这是「流程」这两个字唯一可实测的含义 —— 站表可以随便列，链不会（W6c）。

| # | 站 | 角色 | 输入 | 产物 | 状态 |
|---|---|---|---|---|---|
| 01 | `fetch` | source | `-` | `corpus,inventory` | current |
| 02 | `analyze_r75` | analyze | `corpus` | `agg-toplevel` | superseded（cwd=REPO ⇒ rel 退化成 basename，与 R81/R84 的口径不可比） |
| 03 | `analyze_r81` | analyze | `corpus` | `baseline-r81` | superseded（OUT 写死 r81/ 且按 label 合并 ⇒ 再跑会就地覆盖对照基线（基线是对照的另一半）） |
| 04 | `probe_r84` | analyze | `corpus,baseline-r81` | `agg-r84` | current |
| 05 | `chunks` | probe | `corpus` | `kernel-chunks` | current（独立口径：并发站点词法（不是主读数）；分块可续跑，喂 UNKNOWN_SITES 的 unknown/join 分母） |
| 06 | `site_r75` | present | `corpus` | `site-index` | superseded（R75 版；site/ 只作对照保留） |
| 07 | `site_r81` | present | `corpus` | `site-index-r81` | current |
| 08 | `ui_r75` | present | `agg-toplevel` | `ui-html` | superseded（读 R75 的 agg-toplevel（口径已退役）） |
| 09 | `report_r81` | present | `baseline-r81,site-index-r81,inventory` | `report-html` | current |
| 10 | `ab` | derive | `corpus` | `-` | auxiliary（一次性归因实验（隔离 版本 / cwd / JSON 三变量），无持久产物） |
| 11 | `determinism` | derive | `site-index,site-index-r81` | `determinism-json` | current |
| 12 | `gen_doc` | register | `agg-r84,baseline-r81,inventory` | `KERNEL_RUN.md` | current |
| 13 | `gate` | gate | `KERNEL_RUN.md` | `-` | current |

脚本落点（可执行文件所在处；仓内站为仓库相对路径）：

```text
01 fetch        E:\matlabc\_kernel\fetch_kernel_local.py current
02 analyze_r75  E:\matlabc\_kernel\analyze_kernel.py superseded
03 analyze_r81  E:\matlabc\_kernel\rerun_kernel_r81.py superseded
04 probe_r84    E:\matlabc\_r82\probe_kernel_r84.py current
05 chunks       E:\matlabc\_r82\probe_kernel_chunks.py current
06 site_r75     E:\matlabc\_kernel\make_kernel_site.py superseded
07 site_r81     E:\matlabc\_kernel\site_r81.py current
08 ui_r75       E:\matlabc\_kernel\make_kernel_ui.py superseded
09 report_r81   E:\matlabc\_kernel\make_r81_report.py current
10 ab           E:\matlabc\_kernel\ab_r81.py   auxiliary
11 determinism  E:\matlabc\_kernel\check_site_determinism_r81.py current
12 gen_doc      E:\matlabc\_r82\gen_kernel_run_doc.py current
13 gate         tools/check_kernel_snapshot.py current
```

**当前驱动** = `probe_kernel_r84` —— 13 站里唯一 `role=analyze` 且 `status=current` 的那个。
W6b 断言它**恰好一个**：0 个 ⇒ 流程没有分析器；2 个以上 ⇒ 没人知道该跑哪个。

产物链（W6c）在本表生成时**重算过一次**：全部 13 站的 `in` 都接得上。

仓内落点（W6e 逐个断言存在，共 4 个）：`docs/KERNEL_RUN.md`、`tools/check_kernel_snapshot.py`、`README.md`、`README_CN.md`

<!-- KERNEL-PIPELINE v1 -->
```text
pipeline.analyze_current | probe_kernel_r84
pipeline.chain_ok | 1
pipeline.repo_artifacts | docs/KERNEL_RUN.md,tools/check_kernel_snapshot.py,README.md,README_CN.md
pipeline.station.01 | path=E:\matlabc\_kernel\fetch_kernel_local.py;role=source;in=-;out=corpus,inventory;status=current
pipeline.station.02 | path=E:\matlabc\_kernel\analyze_kernel.py;role=analyze;in=corpus;out=agg-toplevel;status=superseded;why=cwd=REPO ⇒ rel 退化成 basename，与 R81/R84 的口径不可比
pipeline.station.03 | path=E:\matlabc\_kernel\rerun_kernel_r81.py;role=analyze;in=corpus;out=baseline-r81;status=superseded;why=OUT 写死 r81/ 且按 label 合并 ⇒ 再跑会就地覆盖对照基线（基线是对照的另一半）
pipeline.station.04 | path=E:\matlabc\_r82\probe_kernel_r84.py;role=analyze;in=corpus,baseline-r81;out=agg-r84;status=current
pipeline.station.05 | path=E:\matlabc\_r82\probe_kernel_chunks.py;role=probe;in=corpus;out=kernel-chunks;status=current;why=独立口径：并发站点词法（不是主读数）；分块可续跑，喂 UNKNOWN_SITES 的 unknown/join 分母
pipeline.station.06 | path=E:\matlabc\_kernel\make_kernel_site.py;role=present;in=corpus;out=site-index;status=superseded;why=R75 版；site/ 只作对照保留
pipeline.station.07 | path=E:\matlabc\_kernel\site_r81.py;role=present;in=corpus;out=site-index-r81;status=current
pipeline.station.08 | path=E:\matlabc\_kernel\make_kernel_ui.py;role=present;in=agg-toplevel;out=ui-html;status=superseded;why=读 R75 的 agg-toplevel（口径已退役）
pipeline.station.09 | path=E:\matlabc\_kernel\make_r81_report.py;role=present;in=baseline-r81,site-index-r81,inventory;out=report-html;status=current
pipeline.station.10 | path=E:\matlabc\_kernel\ab_r81.py;role=derive;in=corpus;out=-;status=auxiliary;why=一次性归因实验（隔离 版本 / cwd / JSON 三变量），无持久产物
pipeline.station.11 | path=E:\matlabc\_kernel\check_site_determinism_r81.py;role=derive;in=site-index,site-index-r81;out=determinism-json;status=current
pipeline.station.12 | path=E:\matlabc\_r82\gen_kernel_run_doc.py;role=register;in=agg-r84,baseline-r81,inventory;out=KERNEL_RUN.md;status=current
pipeline.station.13 | path=tools/check_kernel_snapshot.py;role=gate;in=KERNEL_RUN.md;out=-;status=current
pipeline.stations | 13
```
<!-- /KERNEL-PIPELINE -->

## 1. 为什么这张表需要一台能说「不」的装置

重跑整棵内核要 **~13 分钟 / 13 GB 内存**，不适合放进门禁。于是存在一个
**只写不校**的三方事实：README 里散着一个读数、登记表里躺着另一个、
提交信息里引用第三个 —— 而没有任何东西在核对它们是不是同一份被测物。

本仓已经因此**同时在档三个都对却不一致的读数**，差别**不在分析器**，
而在**子进程的工作目录约定**：

| 读数 | 来源 | 口径 |
|---|---|---|
| `661 s / 10.8 GB` | R75（`_kernel/analyze_kernel.py`） | `cwd=REPO` ⇒ 记录到的路径退化成 basename |
| `793.4 s / 13.1 GB` | R81（`_kernel/rerun_kernel_r81.py`） | `cwd=CORPUS` ⇒ 真相对路径 |
| `526.3 s / 12.5 GB` | R84（本轮，`_r82/probe_kernel_r84.py`） | `cwd=CORPUS`（与 R81 同口径） |

三者**都不是错的** —— 错的是「把它们混着引用而不写出口径」。
所以本表第一件要登记的东西不是数字，是**口径**（`provenance.cwd_convention`），
W2 会对它做非空断言。

## 2. 三档分母（**必须并列，且必须指名子树**）

| 档 | 读数 | 口径（扩展名集合 **不同**，不是子集关系） |
|---|---|---|
| 内核 · C 前端分析的 | 62704 | `.c .h .cc .cpp .cxx .hpp .hh .hxx`（`probe_kernel_r84.CEXT`） |
| 内核 · 既有词法口径的源码 | 63051 | `.c .cc .cpp .cu .cuh .cxx .h .js .m .mjs .py`（单一事实源在 `probe_kernel_chunks.EXT`） |
| 本仓 + 对标 OSS | 340 | `docs/UNKNOWN_SITES.md` 那一档（不含内核） |

⚠ 第一档是**跑这次分析时** C 前端真正吃进去的文件数（`.hpp/.hh/.hxx` 在册，`.py/.js/.cu` 不在）；第二档是仓库**既有的**词法口径（`.py/.js/.m/.cu/.cuh` 在册，`.s` 不在）。两个集合**互有出入**，谁大谁小是**经验事实** —— 这条路走错过一次：
生成器第一版自己定义了「全部扩展名 = 树里所有文件」，算出 **92,190**，与仓库既有的 **63,051** 差了 `.rst/.txt/Makefile/…` 这些非源码文件。**这正是一个量两份实现的典型下场**，已改为直接复用既有装置的常量。

⚠ **分母必须指名子树**：`E:\matlabc\_kernel` 顶层**不是**内核树 —— 它混着
本项目克隆（`clone/`、`mut*/`、`r81/`）与生成物（`site_fs/`）。按它数出来的
分母是**混口径**。上面三档各自指名了自己的语料；两个内核档**禁止合并**
（W3：合并即红），因为「内核有多少文件」本来就有两个都对的问题。

## 3. 分臂读数（含与 R81 基线的逐字段对照）

| 字段 | R84 C 臂 | R81 C 臂 | 同/异 | R84 ASM 臂 | R81 ASM 臂 | 同/异 |
|---|---|---|---|---|---|---|
| `files` | 62704 | 62704 | ✅ | | | |
| `lines` | 36155901 | 36155901 | ✅ | | | |
| `funcs` | 743518 | 743518 | ✅ | | | |
| `edges` | 7065831 | 7065831 | ✅ | | | |
| `unresolved` | 1295146 | 1295146 | ✅ | | | |
| `includes` | 3762589 | 3762589 | ✅ | | | |
| `heuristics` | 1262829 | 1262829 | ✅ | | | |
| `json_bytes` | 11355505 | 11355505 | ✅ | | | |
| `rc` | 0 | 0 | ✅ | | | |
| `peak_mb` | 12765.8 | 13136.5 | 不可裁决 | 136.6 | 128.3 | 不可裁决 |
| `seconds` | 526.3 | 793.4 | 不可裁决 | 2.7 | 2.4 | 不可裁决 |

汇编臂（`--lang asm`）的规模：**1369** 文件 / **381729** 行。

⚠ `peak_mb` / `seconds` **不参与** R81⇄R84 对照 —— 同一台机上相邻两次
可以差数倍（墙钟受同机负载影响），单次读数不可裁决（§4c-1）。
W5 只比**与时钟无关**的计数器，且**逐类**比对启发式分解：
「+1 / −1」这种一好一坏顶替会让总数不变，**只比总数时它是静默的**。

## 4. 启发式分解（逐类，必须与汇总恒等）

| 类别 | R84 | R81 |
|---|---|---|
| `c_array_oob` | 636 | 636 |
| `c_buffer_overflow` | 1230 | 1230 |
| `c_double_free` | 305 | 305 |
| `c_missing_doc` | 560718 | 560718 |
| `c_missing_guard` | 2029 | 2029 |
| `c_missing_return` | 1070 | 1070 |
| `c_too_many_params` | 7789 | 7789 |
| `c_uninit_pointer` | 458329 | 458329 |
| `c_unused_static` | 230066 | 230066 |
| `c_use_after_free` | 657 | 657 |
| **合计** | **1262829** | **1262829** |

恒等式 `Σ类别 == heuristics` 是**真计数**，不是调出来的阈值（W4）。

## 5. 出处与跨文档

| 项 | 值 |
|---|---|
| 被测物 `matlabc.py` sha256 | `f414e2524b0e5f21065aafe78e02c99bec2323d1b9ea361eb65b9f712c40efac` |
| 被测物字节数 | 1629120 |
| 生成时 HEAD | `70b8a65634abf21ad0cfd7f3b0ce495b060eadb0` |
| 基线 `AGG_r81.json` sha256 | `c6ba4cab681edd521cd674126a80b3716ff56a479de6d3463cab4a31b6e19374` |
| 跨文档 | `docs/UNKNOWN_SITES.md` 那档分母 = 340（本表同值） |

## 6. 复现

```bash
python _r82/probe_kernel_r84.py --provenance   # 只读：打印指纹，不写盘
python _r82/probe_kernel_r84.py --arms c asm   # 真跑（~13 min / ~13 GB）
python _r82/gen_kernel_run_doc.py              # 重生成本表
python tools/check_kernel_snapshot.py          # 门（W1–W6）
```

## 7. 两块的分工

本文件里有**两个围栏块**，各自用一对 HTML 注释标记包着：一个登记**读数**
（跑出来的数），另一个登记**结构**（有哪几站、谁产出谁）。分开的理由很实际：
合成的块里没人分得清「哪些键归哪一条判据管」，而门的 W6 只读 `pipeline.*`。

⚠ **标记本身不得在正文里重复出现** —— 门的解析器要求每个标记**恰好一次**
（重号会让切片落错地方，§4z-15）。本节因此刻意**不写出标记的字面量**：
第一版把两个标记原样写进这一节，门**当场**报「闭标记出现 2 次」——
这道判据第一次开火，抓的是它自己的文档。

<!-- KERNEL-RUN v1 -->
```text
arm_asm.files | 1369
arm_asm.json_bytes | 486229
arm_asm.lines | 381729
arm_asm.peak_mb | 136.6
arm_asm.rc | 0
arm_asm.seconds | 2.7
arm_c.edges | 7065831
arm_c.files | 62704
arm_c.funcs | 743518
arm_c.heuristics | 1262829
arm_c.includes | 3762589
arm_c.json_bytes | 11355505
arm_c.kind.c_array_oob | 636
arm_c.kind.c_buffer_overflow | 1230
arm_c.kind.c_double_free | 305
arm_c.kind.c_missing_doc | 560718
arm_c.kind.c_missing_guard | 2029
arm_c.kind.c_missing_return | 1070
arm_c.kind.c_too_many_params | 7789
arm_c.kind.c_uninit_pointer | 458329
arm_c.kind.c_unused_static | 230066
arm_c.kind.c_use_after_free | 657
arm_c.lines | 36155901
arm_c.peak_mb | 12765.8
arm_c.rc | 0
arm_c.seconds | 526.3
arm_c.unresolved | 1295146
base_asm.files | 1369
base_asm.json_bytes | 486229
base_asm.lines | 381729
base_asm.peak_mb | 128.3
base_asm.rc | 0
base_asm.seconds | 2.4
base_c.edges | 7065831
base_c.files | 62704
base_c.funcs | 743518
base_c.heuristics | 1262829
base_c.includes | 3762589
base_c.json_bytes | 11355505
base_c.kind.c_array_oob | 636
base_c.kind.c_buffer_overflow | 1230
base_c.kind.c_double_free | 305
base_c.kind.c_missing_doc | 560718
base_c.kind.c_missing_guard | 2029
base_c.kind.c_missing_return | 1070
base_c.kind.c_too_many_params | 7789
base_c.kind.c_uninit_pointer | 458329
base_c.kind.c_unused_static | 230066
base_c.kind.c_use_after_free | 657
base_c.lines | 36155901
base_c.peak_mb | 13136.5
base_c.rc | 0
base_c.seconds | 793.4
base_c.unresolved | 1295146
baseline.path | E:\matlabc\_kernel\r81\AGG_r81.json
baseline.sha256 | c6ba4cab681edd521cd674126a80b3716ff56a479de6d3463cab4a31b6e19374
corpus.bytes | 1379765499
corpus.files_all_ext | 63051
corpus.files_c_family | 62704
corpus.files_repo_plus_oss | 340
corpus.path | E:\matlabc\_kernel\corpus\linux-6.19.14
crossdoc.unknown_sites_files | 340
provenance.cwd_convention | cwd=corpus (target=.)
provenance.git_head | 70b8a65634abf21ad0cfd7f3b0ce495b060eadb0
provenance.matlabc_bytes | 1629120
provenance.matlabc_sha256 | f414e2524b0e5f21065aafe78e02c99bec2323d1b9ea361eb65b9f712c40efac
```
<!-- /KERNEL-RUN -->
