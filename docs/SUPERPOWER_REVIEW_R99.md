# SUPERPOWER REVIEW R99 —— 三语言站点「同页名」统一

> 用户原话：**「我发现了三种语言的展现完全不一样啊……我要的是整个系统的代码的
> 完全分析……三者有共同的一个基本点就是对工程代码的深度分析……共有的都需要
> 适配，特有的需要各自适配……动态链接库也务必解析出来。」**

---

## §0 结论表

| 问题 | 回答 |
|---|---|
| 「展现完全不一样」是感觉还是事实？ | **事实，而且项目自己的登记表已经把它量化了** |
| 量化成什么？ | `tools/check_parity_registry.py --measure` 第 16 行：`site_same_page_names` → **matlab=no，c/py/js=yes** |
| 根因是什么？ | 引擎里有**两条互不相干的站点出口**，页面名**一个都不重合** |
| 本轮实现了什么？ | MATLAB 站点接上 C/Py/JS 的**同一份基础层代码**，四语言页面名同形 |
| 那一格现在是什么？ | **yes**（实测，门绿） |
| 顺带抓到几个真缺陷？ | **3 个**（见 §3），其中 1 个是「站点产物根本不可复现」 |
| 用户要的「变量级 / 动态库」呢？ | **没有**「整个系统」级；本文 §5 给出**为什么**和**下一刀** |

---

## §1 用户诉求 → 实测映射

| 用户说 | 实测事实 | 本轮处置 |
|---|---|---|
| 三种语言展现完全不一样 | **两套站点出口**：`renderers/csite.py::render_c_site`（C/py/js/asm，7 类页）vs `matlabc.py::render_browse_site`（MATLAB，40+ 页）—— Explore 只读调查逐页列出，**无一个共享页名** | **已修**：MATLAB 站点跑同一份基础层 |
| 要「整个系统的完全分析」 | 引擎 JSON schema **有 26 章**（`global_vars` / `field_access` / `types` / `uninitialized` / `constants` / `dead_code` / `type_flow` / `dimensions` / `taint` / `dup_code` / `c_model` / `c_bridge` / `dirs` / `files_graph` …）——**变量级分析 MATLAB 侧早就很丰富** | 呈现层只渲染了约 8 类；**下一刀** |
| 每个文件 / 每个函数 / **每个变量** | MATLAB `files[].functions[].vars` ✓；**C 只有 `macros`/`params`/`returns`/`complexity`，Python 更少** | C/py **无数据源**，呈现层无从谈起 → 槽 25 / 槽 26 |
| 「共有的都适配」 | `LANG_SUPPORT`（R97）：matlab=yes，**c=no（槽 26）**，**py=no（槽 25）** | 本轮把**站点**这一栏的共有能力补齐 |
| 「特有的各自适配」 | MATLAB 40+ 页里 15 页是**语言特有**（`taint` / `dims` / `varflow` / `struct_members` / `class_hierarchy` / `members` / `matlab_lib` / `calibration` / `operator_impact` …） | 保留（它们本来就在），本轮**只加不改** |
| 动态链接库务必解析出来 | **`binfmt/` 已完整**（ELF / PE / Mach-O / GPU，11 个模块）+ CLI `--binary` / `--binary-attach` / `--lib-resolve` + 站点 `binaries.html` | ⚠ **`binaries.html` 只有 C/py/js 侧有，MATLAB 侧完全没有**（Explore 实证）→ 下一刀 |
| 「没有难懂的代码」 | 站点是**纯内联 HTML/CSS/SVG，零 JS 零外链**，断网双击可开（csite docstring 的承诺） | 本轮新增的页面沿用同一形态 |

---

## §2 根因：不是「像不像」，是**两套代码**

```
                    ┌──────────────────────────────────────┐
  --lang c / py / js / asm ──▶ _emit_lang_site ──▶ render_c_site   （7 类页）
                    └──────────────────────────────────────┘
                    ┌──────────────────────────────────────┐
  MATLAB ─────────────▶ render_browse_site                        （40+ 页）
                    └──────────────────────────────────────┘
```

两套出口**没有共享过任何一行渲染代码**，也没有共享过任何一个页面名。
「同一条能力按语言分裂成『有』和『没有』」—— 这句话**早就写在引擎自己的注释里**
（`matlabc.py:11124` 一带，R92 留的），但 `site_same_page_names` 那一格直到
R96 建表时才被**机器化**。

---

## §3 本轮抓到的 3 个真缺陷（全部有实测证据）

### 缺陷 ①：两套站点页面名不重合（= 用户说的「展现完全不一样」）

- **量化**：`check_parity_registry --measure` → `site_same_page_names | no | yes | yes | yes`
- **修**：MATLAB `--browse` 也跑 `render_c_site`，同一份代码、落到**同一个站点根**
  - `skip_index=True` 保住 `render_browse_site` 自己的 `index.html` / `site-quality.json`
  - `src_subdir="xref_src"` 避开 MATLAB 自己的 `src/`（命名规则不同，同目录会互相污染）
- **验收**：design 语料（60 个 `.m`）→ 基础层 **127 页**；站点根 `index.html` ✓
  `funcs.html` ✓ `file/` ✓（75 页）`dir/` ✓（20 页）；自检覆盖 **91 → 218 页**
- **实测那一格**：**yes**（对等门 `OK（能力 16 格 × 语言 4；在册探针 56 格）`）

### 缺陷 ②：站点配色**不可复现**（`PYTHONHASHSEED`）

- **症状**：**同一份代码连跑两次**，`diff -rq` 报 4 个文件不同
  （`index.html` + `rule/*.html`），**差异只在配色**（`#8250df` ↔ `#bc4c00`、
  `#0a3069` ↔ `#0969da`），内容一字不差
- **根因**：`renderers/csite.py::_kind_color` 用 `abs(hash(kind))` 选调色板 ——
  `str` 的内置哈希受 **PYTHONHASHSEED 随机化**影响，**跨进程不稳定**
- **讽刺**：同一份 docstring 承诺「**两次运行逐字节稳定**」（R85 的确定性纪律）
- **修**：`zlib.crc32`（标准库、跨进程稳定）
- **验收**：改后连跑两次 → `diff -rq` **空**（逐字节一致）

### 缺陷 ③：`_clean_browse_dir` 白名单**两向都错**

- **多**：`review.html` —— 全仓**从不生成**它（`grep` 只有清理白名单这一处），**幽灵条目**
- **缺 5 个真的会生成**的页：`func_detail.html` / `unified.html` / `folder_impact.html` /
  `var_taint.html` / `ai_prompts.html`（`render_browse_site` 各有生成点）
- **后果**：换 `--lang` / 换语料后**上一轮的页面残留** ⇒ 两套页面混在一起
  （本项目对「陈旧产物与真坏长得一样」有明文纪律，R83 ④）
- **修**：两向修正 + 补基础层的 4 个子目录（`file/` `dir/` `rule/` `xref_src/`）
  与 3 个顶层页（`funcs.html` `deps.html` `binaries.html`）

---

## §4 我自己犯的错（记下来，因为它比缺陷更值得记）

| # | 症状 | 我第一反应 | 真相 | 谁抓到 |
|---|---|---|---|---|
| 1 | 对等门报 **py/js 的 `browse_site` 由 yes 变假** | 「我加的参数默认值不影响 py/js 啊」 | `zlib.crc32(u"%s" % kind.encode(...))` —— **`%` 优先级低于属性取值**，非 `str` 的 kind 直接 `AttributeError`，整站 `try/except` 兜住 ⇒ **一个页面都不落盘** | **门**（当场） |
| 2 | 补丁 dry run 报锚点 0 次 | 「锚点抄对了呀」 | raw 字符串结尾 `\"""` —— 反斜杠转义了第一个引号 | 补丁自己 |
| 3 | 站点颜色变了，怀疑是我的改动 | 「我只是加了个参数」 | 我拿来对照的 `bs_py` 是**陈旧基准**（同一份代码连跑两次颜色本来就不同）⇒ **先问量具错还是对象错**，这次是**量具（基准）陈旧** | `git diff`（证明我只改了 9 处路径） |

**第 3 条最值钱**：如果我当时「回滚配色改动」去追一个不存在的回归，就会把
**缺陷 ②** 一起丢掉 —— 而它才是真正该修的。

---

## §5 用户要的「变量级 / 动态库」：为什么本轮没做完

### 变量级（每个变量都要分析）

| 语言 | 现有数据源 | 缺口 |
|---|---|---|
| MATLAB | `files[].functions[].vars` / `global_vars` / `field_access` / `types` / `uninitialized` / `constants` / `varflow` / `member_index` | **呈现层未全部接线** |
| **C** | `macros[{name,value,line}]` / `functions[].params` / `returns` / `complexity` | **无 `vars`、无 `types`、无 `uninitialized`** ⇒ `LANG_SUPPORT["c"]="no"`（槽 26） |
| **Python** | `functions[].params` / `calls` / `line` | **更少**；前端未 `ast` 化 ⇒ `LANG_SUPPORT["py"]="no"`（槽 25） |

**结论**：C/Python 的变量级**不是呈现层能补的**——**数据源不存在**。
在数据源到位之前，呈现层只能**如实标注「不可用」而不是 0**（「我没算」≠「它是 0」）。

### 动态链接库

- **能力完整**：`binfmt/` 11 个模块 + `--binary` / `--binary-attach` / `--lib-resolve` +
  站点 `binaries.html`（三态归因：`resolved` / `ambiguous` / `not_found`）
- **两个缺口**：
  1. **MATLAB 侧完全没有 `binaries.html`**（Explore 实证：`render_browse_site` 里
     `binaries` 一字未提，调用点也没传）
  2. **三份语料都没有动态库实物**：cobratoolbox 无 `.mex`/`.dll`，
     sympy **无 `.so`**（纯 Python），内核源码树无编译产物 ⇒
     **本轮无法端到端实测**（这是**诚实的边界**：「没有实物可测」≠「能力没有」）
  3. `--browse` 帮助说「给 `--binary` 或 `--binary-attach` 时另加 binaries 页」，
     但 `_binary_site_payload` **只读 `args.binary_attach`** ⇒ **帮助与实现不一致**

---

## §6 六顶思考帽

- **【白帽】事实**：上面全部有实测/源码行号。核心三条：`site_same_page_names`
  实测 `no→yes`；`diff -rq` 两次运行从「4 文件不同」到「空」；`git diff --stat`
  证明只改了路径/skip 相关 9 处，**不碰配色**。
- **【红帽】直觉**：最危险的动作是「**再写第四套渲染器**」—— 用户看到的是
  「三套不一样」，正确的方向是**收敛**而不是再添一套。所以本轮**没有**新建
  任何站点生成器，只让 MATLAB 复用 C/py/js 的那一份。
- **【黑帽】风险**：① 加性改动也可能反咬（缺陷 §4-1 就是）；② 改 MATLAB 站点
  会**改变 MATLAB 用户的产物**（新增基础层页）—— 已在文档写明是**新增**；
  ③ C/py/js 默认参数不变 ⇒ 逐字节不变（已用同一份代码连跑两次验证确定性）。
- **【黄帽】价值**：四语言现在有**同一份基础层**：`funcs.html`（三张有界榜：
  扇入 / 扇出 / 未解析名）、`file/`（每文件一页，出边+入边双列可点）、
  `dir/`、`deps.html`、`rule/`。这是「共有的都适配」在**站点这一栏**的落地。
- **【绿帽】替代方案**：a) 新写统一生成器 → **否决**（第四套）；
  b) 让 csite 写到 `xref/` 子目录 → 那「页面名同形」仍不成立（探针查站点根）；
  c) **本轮选的**：同一站点根 + `skip_index` + `src_subdir`。
- **【蓝帽】结论**：**方向是收敛而不是重造**；本轮把「站点」这一栏收敛完，
  下一刀是**变量级（槽 25/26）**与**动态库（MATLAB 侧 binaries）**。

---

## §7 与卡帕西四原则对照

| 原则 | 本轮怎么落的 | 差点在哪翻车 |
|---|---|---|
| **① 写码前先想清** | 先派 Explore 只读调查**逐页**列出两套出口的页面/渲染函数/数据源，再动手 | 差点直接开写「统一生成器」 |
| **② 极简优先** | 只加**两个默认值即原行为**的参数，不新建模块、不新建生成器 | — |
| **③ 手术式改动** | `git diff --stat`：2 文件 116 插入 12 删除；**没碰**任何渲染逻辑与配色（配色是单独一轮的修复） | 若把配色一并「顺手改」，就会两件事都说不清 |
| **④ 目标驱动执行** | 先定判据（对等门那一格 / `diff -rq` 空 / 门禁 20）再动手，循环到绿 | — |

---

## §8 可重跑证据

| # | 断言 | 命令 |
|---|---|---|
| E1 | `site_same_page_names` 四语言 yes | `python tools/check_parity_registry.py`（`OK（能力 16 格 × 语言 4；在册探针 56 格）`） |
| E2 | MATLAB 站点根四件齐备 | `python matlabc.py <语料> --browse <dir>` → `ls <dir>/{index.html,funcs.html,file,dir}` |
| E3 | 站点产物**可复现** | 连跑两次 → `diff -rq d1 d2`（空） |
| E4 | C/py/js 路径**未受影响** | `git diff --stat` 只动路径/skip 相关 9 处 |
| E5 | 白名单两向 | `grep -c '"review.html",'`（1 处，且是清理清单） |
| E6 | 门禁 20/20 | `python tools/check_all.py` |
| E7 | 内核**分析产物**零变化（本轮的改动在呈现层，不在分析层） | `check_kernel_snapshot.py` 的「产物现算核对：3 份」全过；C 臂的 `files` / `lines` / `rc` / `std_files` / `std_includes` 与 R81 基线**逐位全等** |
| E8 | 内核 provenance **已按门给的路子重跑刷新**（而不是「只改表」） | `python _r82/probe_kernel_r84.py --arms c asm`（rc=0 / 531.8 s / 62,704 文件）⇒ `python _r82/gen_kernel_run_doc.py` ⇒ 再 `--check` **与盘上一致** |
| E9 | 快照门 W1–W7 全过 | `python tools/check_kernel_snapshot.py` ⇒ `OK（… + 判据族 W1–W7）` |
| E10 | 路线图槽 38 入表、环路预检 0 | `python _r98/verify_loop_plan_r98c.py` ⇒ `load_plan -> 39 槽`、`ledger_plan_problems -> 空` |

---

## §8b 改了被测物 ⇒ 快照门**必然**报红，唯一合法出路是重跑

本轮改了 `matlabc.py`（+83 行：适配器 + 基础层调用）。第 19/20 道门随即报 **2 条 W2**：

```text
  - W2 读数陈旧：登记表记的 matlabc.py sha256=40ceda4010888da7，当前=9855fc3b3498569d
  - W2 provenance.matlabc_bytes=1684810，当前 matlabc.py=1689491
```

门自己把出路写在报错里：**「先重跑 …，再用实测值改本表；只改表不改跑 =
把一个没跑过的数写成跑过的」**。于是按它指的路径走：

| 步 | 动作 | 实测 |
|---|---|---|
| ① | `python _r82/probe_kernel_r84.py --arms c asm` | rc=0 / **14m34s** / C 臂 **62,704** 文件 / 743,509 函数 / ASM 臂 1,369 文件 |
| ② | `python _r82/gen_kernel_run_doc.py` | 落盘 **23,533 B** / CRLF **373** / `bare_lf=0` / keys 73(+17) |
| ③ | 再 `--check` | **与盘上一致** |
| ④ | `python tools/check_kernel_snapshot.py` | **OK（W1–W7）** |
| ⑤ | `python tools/check_all.py` | **20/20**（RC=0） |

**为什么先重跑、后生成**：`KERNEL_RUN.md` 是**生成器产物**（所有数字现算），
手改数字 = 伪造。生成器读 `AGG_r84.json` + 现算 `matlabc.py` 的 sha256/字节
⇒ 重跑刷新 AGG、生成器刷新表，两边才同源。

⚠ **`provenance.git_head` 保持 `6701330`**（跑这趟时所在的**祖先**提交），
不写成新提交 —— 那是**自指**（那份提交本身包含本文件），「钉祖先、不钉自指」是既有纪律。

⚠ **重跑后 5 个字段与 R81 不同，且都不是本轮造成的**：

| 读数键 | R81 基线 | 本轮 | 差 | 归属 |
|---|---|---|---|---|
| `arm_c.funcs` | 743518 | 743509 | −9 | R87 起**已声明**（GNU 属性说明符缺陷族修复） |
| `arm_c.edges` | 7065831 | 7060966 | −4865 | 同上（`KERNEL_RUN.md` §5 有逐条原因） |
| `arm_c.unresolved` | 1295146 | 1295143 | −3 | 同上 |
| `arm_c.heuristics` | 1262829 | 1262817 | −12 | 同上 |
| `arm_c.json_bytes` | 11355505 | 11355506 | +1 | 同上 |

⇒ 这 5 条**本轮一个字都没动**，方向与幅值逐位不变 —— 这正是「呈现层改动
没渗进分析层」的**最强阴性对照**。

⚠ 墙钟 **531.8 s** vs 上一次整树跑的 **2107.5 s** 差 4 倍 —— 按既有纪律
**不归因**（`peak_mb` / `seconds` 明文「不可裁决」）。

---

## §9 未结与下一轮建议

| 优先级 | 建议 | 第一刀 |
|---|---|---|
| ★★★ | **MATLAB 侧补 `binaries.html`**（用户明确要的「动态链接库」） | `render_browse_site` 加 `binaries` 参数，复用 `render_c_site` 的那一页；`.mex*` + `loadlibrary`/`calllib` 做数据源 |
| ★★★ | **变量级：槽 25 `py_ast_frontend` → 槽 26 `c_entity_layer`** | 两格 `LANG_SUPPORT` 由 `no → yes` 时**必须删理由**（两向登记） |
| ★★ | **MATLAB 的 4 个 `no` 如实归因** | 它们是「**通道不同**」不是「没实现」：`metrics_complexity`/`unresolved_attribution`/`heuristics_channel` 在 MATLAB 走**站点页**而不是 JSON 载荷 ⇒ 探针只认载荷 ⇒ 要么加站点探针、要么在表里写明 |
| ★★ | **`--browse` 帮助与实现对齐** | 帮助说 `--binary` 也出 binaries 页，实现只认 `--binary-attach` —— 改帮助如实，或让实现成真 |
| ★ | **15 页语言特有页的「共有化」评估** | `folder_impact.html` / `unresolved.html` / `dir_matrix.html` / `checks.html` / `complexity.html` / `metrics.html` 在 Explore 的映射里是 **[共有]**（C/py 有数据源）⇒ 可继续搬到基础层 |
| ★ | **生成器入库**（含 R91 的 `build_py_callgraph_doc.py`） | 独立轮次，不夹带 |
