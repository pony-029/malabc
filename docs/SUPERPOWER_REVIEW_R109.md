# R109 复盘：内核整树**演示** + MATLAB 三条「口径分裂」的**接线**

> 本轮用户显式要求（逐字）：「分析下 linux 内核的代码，演示下效果」，
> 并叠加长期指令「按照下一步建议实现保证每一次都是真正的实现」。
> 于是本轮做两件**互不冲突**的事：
>   ① **演示**：用**当前 HEAD** 的代码把整棵 Linux 内核重建成分页浏览站点
>      （R108 那次只重跑了读数，没重建站点）；
>   ② **建议项 1**：R108 §12 的优先级 1 —— MATLAB 侧三条「口径分裂」
>      （`metrics_complexity` / `unresolved_attribution` / `heuristics_channel`）
>      接到**载荷**上。
> 两件事的共同点是：**都只在最后收一次 59 分钟的整树重跑**（W2 纪律）。

---

## §0 一句话结论

**演示**：整树 **62,704** 个 C 文件 / **743,509** 函数 / **7,060,966** 调用边，
建出 **98,357** 个 HTML 页（**4.48 GB**），四类跳转实测可点
（调用图 SVG **内嵌 25 个 `<a>`**、跨文件、源码行锚点、规则页），**全站 `<script>` 计数 0**。
**接线**：`render_json` 里**两处**改动（共 +35 行）让对等表三格 MATLAB 列由
`no` 变 `yes`，记分牌 **53·7·8 → 56·4·8**，而 **7 格缺口只剩 JS 4 格**。
**零级联**：五个静态门当场复核全绿（含 `check_ir_attribution` 的「写点 3 处 =
判定点 1 + 消费点 2」**一个都没变**）。

---

## §1 为什么这两件事可以同轮（不是凑数，是判据逼出来的）

R108 §12 立过一条规矩：**改 `matlabc.py` 任何字节 ⇒ 必须与整树重跑同轮**，
因为 `check_kernel_snapshot` 的 W2 只比 `provenance.matlabc_sha256` /
`matlabc_bytes`，改一个字符它就红。本轮两件事**都要**动 `matlabc.py`：
  * 演示要「用当前代码建站点」——站点是 `matlabc.py --lang c --browse` 的产物；
  * 接线要改 `render_json`。
⇒ 合成一轮，只付一次 59 分钟。若拆开，第二次重跑要白跑。

⚠ **反过来也一样**：本轮**不**趁机改任何与这两件事无关的 `matlabc.py` 字节
（例如槽 26 的 `typedef` 目标类型）。判据的原则是「动它就要重跑」，
那就**只动值得付这次重跑的东西**。

---

## §2 白帽读数（全部现查源码 / 现跑 CLI，不引用记忆）

### 2.1 三条「口径分裂」的性质：**数据早就算好了，缺的是出口**

对等表 §3.2 自己写着这三条「不是缺口，是口径分裂」。逐条查实：

| 能力 | 数据在哪（查实） | 缺口到底是什么 |
| --- | --- | --- |
| `metrics_complexity` | `f.complexity` 由 `_compute_complexity(files)`（`matlabc.py:20239` 定义、`33053` **在 `render_json` 之前**调用）算出；站点 `complexity.html` 与 Markdown 报告在用 | `render_json` 的每函数字典里**没有** `complexity` 键 |
| `unresolved_attribution` | `frontends/matlab.py::unresolved_tuples`（`IR_LANG_OWNERS` 登记的**唯一产出点**）在产 `(名字, 行, rel)`；站点 `unresolved.html` 与终端诊断都在读它 | `render_json` 顶层**没有** `unresolved` 键 |
| `heuristics_channel` | `doc_todos` 已是 `render_json` 的入参（`model.doc_todos`），逐函数带 `missing` 列表 | 顶层**没有** `heuristics` 键；检查结果散在 `uninitialized` / `dead_code` / `p204_p223` 等各自键里 |

⇒ 三条都是**接线**，不是新分析。**一个判定点都没新增。**

### 2.2 门的信号**恰好**是这三句话（判据即需求）

读 `tools/check_parity_registry.py`（不猜）：
```python
def s_metrics_complexity(run):   # 某个函数载荷 complexity > 1
def s_unresolved_attribution(run):  # 载荷 unresolved 非空
def s_heuristics_channel(run):   # 载荷 heuristics 非空
```
且 `PROBED` 里 `("metrics_complexity", l)` / `("unresolved_attribution", l)` /
`("heuristics_channel", l)` 对 **`LANGS` 全四语言**在册 ⇒ 这三格**只能填
`yes`/`no`**，不许 `na`；`E2b` 是两向的：**实测为真而登记写 `no` 也红**。

### 2.3 夹具已备（这是「可测」的前提）

`FIXTURES["matlab"]` 里本来就躺着三个专用文件，本门「一文件只表达一件事」的纪律：
`Mmetrics.m`（`if/elseif/else` ⇒ 复杂度 > 1）、`Munres.m`（调 `mnowhere`）、
`Mundoc.m`（无头部注释）。⇒ 本轮**不需要动夹具**，也不需要动门的任何名单。

### 2.4 演示侧读数：**站点形态在 R81 之后变了**

`site_r81/` 的子站点只有 `index.html` / `c_report.html` / `file/` / `rule/`；
用**当前代码**重建的第一个目录（`block/`）是：
`index.html` / `funcs.html` / `deps.html` / **`dynlibs.html`** / `dir/` / `file/` /
`rule/` / `src/` / `c_report.html` —— 这正是 R99/R101 之后的对等形态。
**直接演示 R81 的旧站点会展示过时形态**，所以本轮重建而不复用。

实测（`site_r109/block/file/badblocks.c.html`，72,775 B）：
* 调用图 `<svg>` 12,894 B 内 **25 个 `<a>` / 25 个 `href`** ⇒ 图**逐节点可跳转**；
* 页面共 **363 个 `<a>`**：同文件函数（89）、跨文件（`genhd.c.html`）、
  源码行锚点（`../src/badblocks.c.html#L793`）、规则页（`../rule/c_uninit_pointer.html`）；
* `<script>` 计数 **0** ⇒ 站点自称的「零 JS / 断网可开」**实测成立**。

---

## §3 实现：`render_json` 里**两处**接线（共 +35 行）

补丁脚本 `_r109/patch_r109_matlab_payload.py`（走 `_patchlib`：锚点归一 LF 后
**恰 1 次**、输出侧 `ast.parse`、打印「old 有 / new 无」的删除行对账）。
**删除行为 0 行**（零附带删除）。

### 3.1 P1：每函数载荷补 `complexity`

```python
"line": f.line, "signature": f.signature(),
"complexity": int(getattr(f, "complexity", 1) or 1),   # 槽 29 / R109
"inputs": f.inputs, "outputs": f.outputs,
```
与 C/Py/JS 的**同名键同义**（int，缺省 1）—— `int(... or 1)` 这一写法与
`_collect_doc_todos` 里 `cx = int(getattr(f, "complexity", 1) or 1)` 逐字同形。

### 3.2 P2：顶层补 `unresolved` + `heuristics`（与 C/Py/JS **同键同形**）

```python
"unresolved": [{"callee": _n, "line": _ln, "file": _rel}
               for _n, _ln, _rel in f_matlab.unresolved_tuples(files)],
"heuristics": [
    {"file": _t.get("rel") or "", "line": _t.get("line") or 0,
     "func": _t.get("func") or "", "kind": "m_missing_doc",
     "msg": "函数缺少头部描述（description）", "level": "note"}
    for _t in ((doc_todos or {}).get("todos") or [])
    if "description" in (_t.get("missing") or [])
],
```

三个**设计决定**（每个都有对手方，不是口味）：

1. **为什么不写成 `data["unresolved"] = ...`**：`tools/check_ir_attribution.py`
   的写点判据收的正是 `Assign(Subscript("unresolved"))`（见 `matlabc.py:11501`
   那条长注释）。这里**不是判定点**，写成下标赋值会给出**假信号**
   （「又抄了一遍判定规则」）。用字典字面量的键 ⇒ 写点集合**一个都没变**
   —— 复跑该门实测仍是 **「写点 3 处 = 判定点 1 + 消费点 2」**。
2. **名字从哪来**：`f_matlab.unresolved_tuples` 是 `frontends/__init__.py::IR_LANG_OWNERS`
   登记的 MATLAB **唯一产出点**（R44 收敛的成果）。载荷、站点页、终端诊断
   读的是同一个函数 ⇒ **同源**不是靠约定，是靠构造。
3. **`heuristics` 的范围如实**：这条通道本轮只接上**有直接 C 对应物**的那一类
   规则（「函数缺头部描述」→ `m_missing_doc` ↔ C 的 `c_missing_doc`），
   因为它正是门的 `EVIDENCE` 写明的那条（「无注释函数触发一条」）。
   MATLAB 其余检查类别**仍留在各自键里、未并入**这条通道 ——
   这一格的意思是「这条通道存在、键名与条目形状对齐」，**不是**「所有规则都走它」。
   这条边界写进了对等表 §3.2 的显式警告段，不留暗示。

---

## §4 演示：整树站点重建（用户显式要求的「效果」）

### 4.1 跑法

派生脚本 `_kernel/site_r109.py`（复用 `_kernel/make_kernel_site.py`，
只换 `SITE` / `LOG` / 标题三处常量，锚点各命中 1 次否则整体不跑；
`--dry` 先验）。**按顶层目录分批**的理由在原作者注释里：整树单跑峰值
10.8 GB，站点渲染还要在模型之上再建反查索引，16 GB 机器有 OOM 风险。

命令（每批）：`matlabc.py <目录> --lang c --browse <站点目录> --checks all`，
**子进程 cwd = 被分析目录**（`_rel_of()` 按 cwd 算 rel，否则退化成 basename）。

### 4.2 落地页 `demo.html`（本轮新建）

`_r109/gen_demo_r109.py` 从**两份实测产物**直接生成，不手填任何数字：
`site_r109/site-index.json`（24 个顶层目录逐目录读数）+ `r84/AGG_r84.json`（两臂整树读数 + provenance）。
零外链、CSS 内联、**零 JS**，放在站点根 ⇒ 相对链接直接可点进任一子站点。
结构校验：用 `html.parser` 做标签平衡检查 ⇒ **未闭合 0 / 错配 0**。
⚠ 耗时列**如实标注**：本轮构建与其它任务同机并行，墙钟只能当量级看
（与文件/函数/边/页面/字节这些与负载无关的读数分开列）。

### 4.3 演示读数

见 §7（等整树重跑与站点构建双双收尾后填**最终**读数）。

---

## §5 闸门**先红后绿**（D4 纪律要的是「它曾经红过」的记录）

### 5.1 对等表门：实测三条，**恰好**三条

接线落盘后立刻复跑本门，**当场红 3 项、且只有 3 项**：

```
E2b `metrics_complexity/matlab` 登记 no，**实测为真** —— 实现未登记
E2b `unresolved_attribution/matlab` 登记 no，**实测为真** —— 实现未登记
E2b `heuristics_channel/matlab` 登记 no，**实测为真** —— 实现未登记
check_parity_registry: 3 项不合格（判据族 E1–E6）
```

这条读数本身就是**接线一次到位**的证据：`E2b` 只在「探针实测为真」时才响，
三条同时响 ⇒ 三个信号在真跑夹具上全部成立；而**没有第四条红** ⇒ 没有误伤
别的格（尤其是没把 `asm_insights` 那种 `na` 格搅进来）。

### 5.2 登记同步（4 个文件 / 14 块）

`_r109/patch_r109_docs.py`（Markdown 不能走 `ast` 自检 ⇒ 同纪律的 `TxtPatch`）：

| 文件 | 改了什么 |
| --- | --- |
| `docs/PARITY_MATLAB_C_PY.md` | §2 人读表 3 格 `no → yes`；**合计行** `68 格：yes 53·no 7` → `yes 56·no 4`；机器块 3 行 `matlab=no → yes` 并**删掉 3 条 `why.matlab`**（E3：`yes` 格不许留理由，陈旧理由 ⇒ 红）；§3.2 改写为「曾经的口径分裂：R109 已收到载荷上」+ 范围警告段；§3.3 缺口标题 `7 格 → 4 格` **并删掉 MATLAB 那一行**；§6 下一步表 + 结语 |
| `README.md` / `README_CN.md` | 记分牌 `53 \`yes\` · 7 \`no\`` → `56 \`yes\` · 4 \`no\``（**同行等长替换 ⇒ 两文件字节数不变**） |
| `docs/matlabc_JSON_SCHEMA.md` | §1 顶层字段补 `unresolved` / `heuristics` 两行；§4.2 函数元素补 `complexity` 一行 |

复跑本门：**`OK（能力 17 格 × 语言 4；在册探针 60 格；判据族 E1–E6）`**，
三格 MATLAB 实测全 `yes`。

### 5.3 零级联（五个静态门当场复核）

| 门 | 结果 | 关键读数 |
| --- | --- | --- |
| `check_py36_clean` | OK | 82 个 `.py` 全部过 3.6.5 语法门（新代码含推导式 / `getattr`，无新建语法） |
| `check_ir_attribution` | OK | **写点 3 处 = 判定点 1 + 消费点 2**（与改前**逐字相同**）；归因喂入点 4 处；语言登记 5 个 |
| `check_readme_parity` | OK | 15 个小节逐节对等；两侧质量门表各 21 行 == `tools/check_*.py` 真实清单 |
| `check_known_red` | OK | 0 个从未提交的产物；引用它们的测试三分在册 |
| `check_doc_flags` | OK | 9 份文档的命令行开关全部真实存在（含 6 个入口脚本的模块 docstring） |

### 5.4 内核快照门：**预期内**的红（顺序是设计出来的）

改 `matlabc.py` ⇒ `provenance.matlabc_sha256` / `matlabc_bytes` 对不上 ⇒
**W2 必红**，直到整树重跑 + `docs/KERNEL_RUN.md` 重生成。本轮**沿用 R108 的
处置**：先提交（让 provenance 的 `HEAD` 含被测物）、重跑、再提交读数文档，
**把这条红如实留在提交史上**，不藏、不靠 `--no-verify` 绕。

---

## §6 第二个独立量具：**自造夹具 + 自写断言**（不是把门跑一遍）

`_r109/probe_r109_payload.py`：临时目录里写两个文件，真跑公开 CLI，逐键核。

夹具两文件，各有**分辨力**职责（这门/这用例的纪律：一次只表达一件事）：

| 文件 | 形态 | 期望 |
| --- | --- | --- |
| `Mbranch.m` | **有**完整头部注释（`描述/输入/输出/作者/版本`）+ `if/elseif/else` | `complexity > 1`；**不该**进 `heuristics` |
| `Mundoc.m` | **无**头部注释 + 调 `Mist`（项目里不存在） | 进 `heuristics`**且**进 `unresolved` |

实测输出（原文）：
```
① complexity       = {'Mbranch': 4, 'Mundoc': 1}
② unresolved       = [{'callee': 'mist', 'line': 1, 'file': 'Mundoc.m'}]
③ heuristics       = [{'file': 'Mundoc.m', 'line': 1, 'func': 'Mundoc',
                       'kind': 'm_missing_doc', 'msg': '函数缺少头部描述（description）',
                       'level': 'note'}]
VERDICT OK 三个键都成立
```
三个键的**形状**也逐个断言（`set(it) == {...}`）：`unresolved` 条目恰为
`{callee, line, file}`、`heuristics` 条目恰为 `{file, line, func, kind, msg, level}`
—— 与 C/Py/JS **逐位同形**是断言，不是印象。
**分辨力**：`Mbranch` 有完整描述、**不在** `heuristics` 的 `func` 集合里。

同一套断言随后固化成**仓内用例** `tests/test_matlabc.py::test_r109_matlab_payload_wiring`
（走 `--json` 公开 CLI，与门是**两个独立量具**：门读它自己的产物信号，本用例读
自己夹具的载荷）。单跑 `-k "r109 or r108"` ⇒ **4 passed, 512 deselected**。


## §7 演示的**验收**：把用户那句「图示可以跳转」变成可复核读数

用户的验收点是一句**自然语言**（「调用关系最好使用图来实现，并且图示可以跳转的」）。
一句话不是判据 —— 它能被「我觉得可以跳」满足，也能被「我挑了 3 页都 OK」满足。
所以本轮先造量具：`_r109/demo_verify_r109.py`，**4 条判据 + 两向自证**。

### §7.1 判据（每条都能被违反，所以每条都有内容）

| 码 | 形式 | 内容 |
|---|---|---|
| C1 | 站点级 | 任意页面 `<script>` 计数 **== 0**（站点自称「零 JS」） |
| C2 | 站点级 | 任意页面外链 `http(s)://` **== 0**（站点自称「断网可开」） |
| C3 | 条件式 | **若**某页渲染了 svg，**则**某 svg 内 `<a>` ≥ 1 |
| C4 | 条件式 | **`.c` 文件详情页**必须渲染出**可跳转**的调用图 |

`--sweep <顶层目录>` 模式对该子树下**全部**文件详情页统计 —— 比硬编码页表强：
硬编码页表只能证明「我挑的那几页 OK」。

### §7.2 三处**量具错**（全部靠「先测量后定契约」抓出来，不是靠想）

**㊱-1 初版把 C3 写成「每页最大 svg 必须有 `<a>`」⇒ 当场报 2 例：**

```
== block/dynlibs.html == 1918 B  svg 数 0  ⇒ ✘ 「图示可跳转」在本页不成立
== block/funcs.html   == 88057 B svg 数 0  ⇒ ✘ 同上
```

逐一看对象：`dynlibs.html` 报 **0 条库引用**是**正确读数** —— Linux 内核是
**freestanding** 的，源码里根本不出现 `dlopen` 的库名字面量；页面正文自己写明了
这个口径（「本语料没有出现任何库名字面量」）。`funcs.html` 是**函数索引页**。
两者按契约**就没有调用图** ⇒ **量具过强**，不是对象错。

**㊱-2 改成「所有 `file/*.html` 都必须有可跳转调用图」⇒ 在 `block/` 上报 5 例：**

```
· opal_proto.h.html  2147 B svg=0      · partitions__atari.h.html 2771 B svg=0
· partitions__efi.h.html 3062 B svg=0  · partitions__ldm.h.html   2801 B svg=0
· partitions__mac.h.html  2413 B svg=0
```

**全是 `.h`** —— 头文件没有函数体，本来就没有调用图。**量具又过强**。
最终形状：C4 只对 `**.c` 页**生效（`is_c_page()`）。

**㊱-3 自检样本自己写错**：两向自证里「good `.h` 页无调用图」的样本我写成了
`<svg><rect/></svg>`（**有 svg 但无链接**）⇒ C3 **正确地**报了红。
**这次是样本错、判据没错** —— 现实中 `.h` 页是**完全没有 svg**（扫描：90 页有 svg、
90 页可跳转、5 页无 svg 且全是 `.h`）。样本改成 `<html><h1>.h</h1>…</html>` 后 7/7 通过。

**㊱-4 生成器的自检期望值算错**：给 `gen_demo_r109.py` 加结构自检时，我把 `<tr>` 期望写成
「`目录数 + 2`」（表头 + 合计），实测 **32 != 26**。原因是页尾还有一张
**provenance 表 6 行**，我把它漏了。**是期望值错，不是生成器错。**
修法不只是改数字：改成从 `<tbody>` 里数（精确对应目录表，与 prov 表行数无关），
并加一条「`<a>` 数 == 目录数」—— 后者顺带把「某行丢了链接」也纳入判据。

**㊱-5 NEGCTRL 的样本自己写错（第二次同形）**：给上面那条自检做两向自证时，
「某行丢了链接」这条样本我只删了 `href`、**没删 `<a>` 标签** ⇒ `<a>` 计数不变 ⇒ 报绿。
输出里 `<a> 2` 一眼看出是样本没做到位。**样本错、判据没错。**

> **五次修正指向同一条纪律**：判据的形状必须由**对象**决定，不能由直觉决定；
> 而「对象长什么样」只能靠**先测量**得到。
> 五次里：2 次是**量具过强**（把列表页 / 头文件页当成「该有调用图的页」），
> 2 次是**样本没做到位**（自证因此测不到），1 次是**期望值漏项**。
> 共同点是 —— **错都在我写下的那个数字/那段样本上，而不是在对象上**；
> 若没有「先测量 / 先自证」这两步，这五次都会以「全绿」的形态悄悄过去。

### §7.2b 生成器自证 + 它的 NEGCTRL

`gen_demo_r109.py` 在写盘后**自证产物结构**（不产出一个坏页还不自知）：

```
自证：12185 B；目录表 <tr> 25（全页 <tr> 32）；<a> 24；<svg> 0；<script> 0；外链 0
   SELFTEST OK
```

其中判据是：标签配对（含未闭合栈）/ 目录表行数 / `<a>` 数 == 目录数 /
`<script>` == 0 / 外链 == 0。

**两向自证（NEGCTRL 6/6）**：

```
good：2 行 + 合计，每行一条链接            rc=0（期望 0）OK
bad ：未闭合 <table>                       rc=1（期望 1）OK
bad ：有 <script>                          rc=1（期望 1）OK
bad ：有外链                               rc=1（期望 1）OK
bad ：行数为 3 而期望 2                    rc=1（期望 1）OK
bad ：某行丢了链接                         rc=1（期望 1）OK
NEGCTRL OK（6/6 条方向正确）
```


### §7.3 两向自证（7/7）

```
  [OK] good .c 页有可跳转调用图             问题=0（期望 0）
  [OK] good 索引页 2 svg 里 1 个有链接      问题=0（期望 0）
  [OK] good .h 页完全无 svg                 问题=0（期望 0）
  [OK] bad  有 <script>                     问题=1（期望 1）码='C1'
  [OK] bad  有外链                          问题=1（期望 1）码='C2'
  [OK] bad  有 svg 但整页 0 链接            问题=1（期望 1）码='C3'
  [OK] bad  .c 页 svg 无 <a>                问题=2（期望 2）码='C3C4'
SELFTEST OK（7/7 条方向正确）
```

前 3 条防**过强**（该绿的必须绿），后 4 条防**过弱**（该红的必须红）。
一个只会在真站点上「全绿」的判据，和没有判据是一回事。

### §7.4 `block/` 子树实测读数（全量，非抽样）

```
扫描 site_r109\block\file 下文件详情页 95 份
  其中 `.c` 详情页 74 份（C4 的作用范围）
  含 svg 的页 90 / 95
  **调用图内可跳转**的页 90 / 95
  调用图内 <a> 合计 1955（href 1955）；平均 20.6 条/页
  C1 违例页（有 <script>）0；C2 违例页（有外链）0
  C4 违例页（`.c` 详情页无可跳转调用图）0 / 74
  C3 证据：有 svg 的页 90 == 可跳转的页 90 ? 是 ⇒ 本站 svg 唯一用途就是调用图
  VERDICT OK
```

⚠ **C3 的前提不是假设，是读数**：`有 svg 的页数 == svg 内可跳转的页数` 这个**等值**
就是「本站 svg 唯一用途是调用图」的证据。一旦不等（出现装饰性 svg），C3 的前提就变了，
扫描会**报红要求重新裁定**，而不是默默放过 —— 这正是 ㉜（绿灯读数必须机器可读）的执行。

单页更细的分类（`block/file/badblocks.c.html`）：

```
   文件 72775 B；<svg> 数 1；最大含链接 svg 13052 B / <a> 25 / href 25
   全页 <a> 363 / href 364；分类 同页锚点=1, 源码行=237, 规则页=26, 跨文件=93, 跨目录=7
   <script> 0；外链 http(s) 0
```

⇒ 「可跳转」的落点确凿在**调用图 svg 内部**（25 个 `<a>`），不只在页面导航里；
href 覆盖 **4 类目标**：同文件源码行 237、规则页 26、跨文件 93、跨目录 7。

### §7.5 站点级读数（24 个顶层目录全部渲染完）

构建日志（逐目录 rc + 秒数，**全部 rc=0**）：

```
TOTAL 2628.5s  dirs=24 ok=24
  drivers 1700.4s | arch 283.2s | tools 175.2s | sound 128.9s | fs 114.8s
  net 77.8s | include 56.5s | kernel 27.8s | lib 15.0s | mm 10.7s | …
```

`site-index.json` 聚合（**零手填**，脚本从 JSON 现算）：

| 量 | 值 |
|---|---|
| 目录数 | 24（`rc != 0` 的：**0**） |
| 文件 | **62,704** |
| 函数 | **743,509** |
| 调用边（目录内，见下注） | 2,427,130 |
| HTML 页 | **98,356** |
| HTML 字节 | **4,478,865,235**（≈4.48 GB） |
| 规则种类 | 168 |
| 告警 | 1,282,228 |
| 孤儿告警 | 0 |
| 构建秒数 | 2628.5 |

⚠ **注（不混口径）**：`site-index.json` 的 `edges` 是**逐目录**统计后求和，
而 R84 整树 `kernel_c_summary.json` 的调用边是 **7,060,966**（整树口径）。
两者**分母不同**，不是同一个量 —— 拿出来并排写就是 R104 ㉝那种错（比值的两操作数必须同量纲）。
本表只报 `site-index` 自己的口径。

**独立量具复核**（盘上遍历，不让 `site-index.json` 自证）：

```
独立量具：html 页 98357 / 总字节 4478961760 / css 117 / js 0 / 其它 25
对照：     html 页 98356 / 总字节 4478865235
差：       页数 +1      字节 +96525
```

**差异必须被解释掉**（R87/R90/R107 的教训），现查根目录：

```
根目录下的文件（不属于任何目录行）：
   browse.css       81334 B
   index.html        8918 B
   site-index.json   6273 B
   合计             96525 B
```

⇒ `96525 = 81334 + 8918 + 6273` **恰等于字节差**；页数差 `+1` **恰是根 `index.html`**。
即：`site-index.json` 的聚合**只覆盖 24 个目录行**、**不含根文件**。
两个差异被**完整**解释掉 ⇒ 独立量具与自报读数一致，**不是**「有一个我还没查的偏差」。

**全站 `js` 文件数 = 0** ⇒ 「零 JS / 断网可开」在 4.48 GB / 9.8 万页的规模上成立。

### §7.6 全站扫描：C1 / C2 的**最强形状**（不抽样、不挑页）

`--sitewide` 遍历**每一页**（不是挑几页举例）：

```
全站扫描：98357 页 / 4469422536 B
  C1 有 <script> 的页 0
  C2 有外链的页 0
  VERDICT OK
```

⇒ 「零 JS / 断网可开」在 **98,357 页 / 4.47 GB** 上是**全量**读数，不是抽样结论。

**按扩展名分解（把两个字节数之间的差解释掉）**：

| 类别 | 字节 | 个数 |
|---|---|---|
| html | 4,469,422,536 | 98,357 |
| css | 9,516,078 | 117 |
| **js** | **0** | **0** |
| 其它 | 23,146 | 25 |
| 总计 | 4,478,961,760 | — |

⚠ 全站扫描报的是 `4,469,422,536`（**只统计 `.html`**），而 §7.5 的盘上遍历报
`4,478,961,760`（**所有文件**）。两者差 `9,539,224 = 9,516,078 + 0 + 23,146`
—— **恰等于**非 HTML 部分（css + js + 其它）⇒ 差异被完整解释掉，两个量具一致。

**多位置复核**（根落地页 / 大目录子站 / 大目录详情页，均 `VERDICT OK`）：

| 页 | 字节 | `<svg>` | 图内 `<a>` | 全页 `<a>` | `<script>` | 外链 |
|---|---|---|---|---|---|---|
| `index.html`（根） | 8,918 | 0 | — | 25（24 个顶层目录 + 1 跳转） | 0 | 0 |
| `drivers/index.html` | 422,371 | 3 | 20 | 2,252 | 0 | 0 |
| `drivers/file/accel__amdxdna__aie2_ctx.c.html` | 113,645 | 1 | **29** | 564 | 0 | 0 |

### §7.7 一处**真发现**（不是量具错）：零可解析边的页面，图内只画外部节点

`rust/` 子站扫描曾报 **C4 违例 6 / 57**，逐页看过后分成两类：

| 页 | 函数 | 出边 | 入边 | 未解析调用 | 图 | 裁定 |
|---|---|---|---|---|---|---|
| `exports.c`、`helpers__slab.c`、`helpers__vmalloc.c`、`helpers__helpers.c`、`helpers__build_assert.c` | **0** | 0 | 0 | 0 | 无 | **正确**（无函数定义） |
| `helpers__atomic.c`（174,528 B） | **170** | 0 | 0 | **170** | 有 4,926 B svg，**`<a>` = 0** | **真发现**（见下） |

`helpers__atomic.c.html` 的 svg 逐个 class 数下来是：

```
cs-gext 40   （外部节点 ≤ 全是在本文件里解析不出来的名字）
cs-glbl 40   （标签）
cs-graph 1 / cs-gedge 1
内部节点（cs-gnode）0
```

而 svg 自己写的 `<desc>` 是：**「确定性力导向布局；节点可点击跳到源码行。
实线为已解析的调用边，虚线连向未解析的外部名字。」**

⇒ 该页 170 个函数**一个节点都没画**，画的全是外部名字；而外部名字**没有本文件的源码行**，
所以 0 个可点链接。**图内一个函数节点都点不到**，与该 svg 自己声明的契约不符。

**这不是「大文件」的普遍现象**（对照实验，函数 ≥ 50 的页）：

| 目录 | 函数 ≥ 50 的页 | 其中有可跳转调用图的页 |
|---|---|---|
| `block` | 15 | **15 / 15** |
| `fs` | 187 | **187 / 187** |
| `lib` | 18 | **18 / 18** |
| `rust` | 1 | **0 / 1** |

⇒ 分界线**不是函数数量**，而是「**可解析边 = 0**」（该文件 170 个调用全是外部未解析）。

**顺带第二处（同页）**：40 个标签被截断成**同一个字符串** `atomic6…`
（40 个不同名字 → 1 个去重结果）⇒ 图上**分辨不出**哪个是哪个。

**处置（按纪律）**：**不擅自改 `matlabc.py`** —— 改它必须配一次整树重跑。
两条都作为 **R110 候选**记入 §12：① 零可解析边时仍应画出**本文件函数节点**（可点到源码行）；
② 标签截断需保分辨力（例如尾缀区分或悬停全名）。
本轮把 C3′/C4′ 修正为**由页面自己的读数决定**，并把这类页**逐条列在扫描输出里**
（`有 svg 但无链接的页 N（须逐条解释）`）—— 既不误报，也不掩盖。


## §8 整树重跑：为什么必须同轮，以及**两层**对账

### §8.1 为什么必须同轮（判据逼出来的，不是省事）

`tools/check_kernel_snapshot.py` 的 **W2** 只做一件事：把
`provenance.matlabc_sha256` / `matlabc_bytes` 与**盘上现算**对比。
所以——

> **改 `matlabc.py` 任何字节 ⇒ W2 必红，直到整树重跑 + `docs/KERNEL_RUN.md` 重生成。**

本轮改了 MATLAB 载荷（`1,714,907 → 1,717,722 B`）⇒ 重跑不是选项。
处置沿用 R108：**先提交再重跑**（让 `provenance.git_head` 含被测物），
把这条红如实留在提交史上，**不藏、不靠 `--no-verify` 绕**。

### §8.2 重跑口径：**第一遍就是错的**（脏树启动）

第一次启动时我**没检查工作树是否干净**。日志第一行是：

```
provenance: matlabc=69bed231… HEAD=951dacd3…
```

`HEAD = 951dacd`（R108 的提交）**不含**被测物 —— 因为被测物那时还在**工作树**里没提交。
⇒ 这一跑产出的 provenance 会把「一个未被任何提交记录的 matlabc.py」记成「与 HEAD 一致」，
等于把 R106 那条边界原样退回。**当场 `TaskStop`**（只跑了 1m15s，几乎零成本）。

改为：**先提交 A（`c7abc01`）→ 核对 `git show HEAD:matlabc.py` 与盘上 sha 逐位相同
（`69bed231b013bb13…`）→ 再重启**。新日志：

```
[07:11:14] provenance: matlabc=69bed231b013bb13 (1717722 B) HEAD=c7abc014de0e5a32720fd69e87c773313d62a600
```

⇒ 干净树 + HEAD 含被测物，两条都成立。

### §8.3 重跑前的字节快照（「不变」这句话的**前提**）

重跑会**先删**旧产物（这是它的既有行为）。所以「逐字节不变」这个主张**必须**建立在
**重跑前**量到的 sha 上，否则拿到的可能是「同一个文件自己比自己」——一个恒真结论。

本轮做法：重跑前把四份在册产物复制到 `_r109/prev_artifacts/`，并写 `prerun_sha.txt`。
**现算复核**（4/4 逐位相同）：

```
9a6bd04c… *kernel_c_summary.json
dff83833… *kernel_asm_summary.json
c4260966… *kernel_callgraph.json
01377624… *AGG_r84.json
```

**并且排除了恒真解释**：07:14 我列过 `_kernel/r84/`，当时该目录**只有 `.log`、
没有任何 `.json`**（`kernel_c_summary.json` / `kernel_callgraph.json` / `AGG_r84.json`
都不在）⇒ 现在盘上的 JSON 是**本次新写**的，不是旧文件残留。

### §8.4 ⓪ 分辨力自证：**② 的断言对象里不含归属字段**

`diff_agg_r109.py` 在跑对账前先做一层**分辨力**检查（实测，非推断）：

```
  [old] kernel_c_summary.json   matlabc=0 git_head=0  纯分析产物 ✔
  [old] kernel_asm_summary.json matlabc=0 git_head=0  纯分析产物 ✔
  [old] kernel_callgraph.json   matlabc=0 git_head=0  纯分析产物 ✔
  [old] AGG_r84.json            matlabc=17 git_head=3  （归属在这里）
⓪ OK：② 有分辨力
```

含义分两半，**缺一不可**：

* ②「三份产物 sha 逐字节全同」**有分辨力** —— 它们不含归属字段，
  所以这条断言**只能**因**真实读数**变化而失败。（反例：若产物里含 `matlabc_sha256`，
  改了 `matlabc.py` 就必然失败 ⇒ 断言恒假，不能当判据用。）
* ①「差异集合非空」**不是恒真** —— 归属字段集中在 `AGG_r84.json`，本轮 `matlabc.py`
  变了 ⇒ `AGG` 必然有差异。

### §8.5 读数 ①（第一项）：C 臂产物 sha256 **逐位全同**

```
新（本次重跑，07:27 落盘） 9a6bd04cfd6c7341666f67095f3c52be0811ea2222718d75c89d261ab63477e9
旧（重跑前归档）           9a6bd04cfd6c7341666f67095f3c52be0811ea2222718d75c89d261ab63477e9
字节数                     11,355,506 B（两侧相同）
```

⚠ **写入时序容易误读**：`_kernel/r84/kernel_c_summary.log` 第 1 行就是
`[OK] JSON 已写入` ⇒ JSON **先落盘**，之后同一个进程还要做算子影响分析并构建调用图
（`--callgraph`）。所以「任务还在跑」与「JSON 已是成品」**不矛盾**，
**不能**把「任务未结束」当作「读数不可用」，也不能反过来当作「已完成」。

### §8.6 结果：两层同绿

**① 逐字段 diff（`AGG_r84.json`，11 处，全部落在归属/时钟）**

| 差异路径 | 旧 → 新 | 类 |
|---|---|---|
| `provenance.git_head` | `b778fe64…` → `c7abc014…` | 归属 |
| `provenance.matlabc_bytes` | 1714907 → 1717722 | 归属 |
| `provenance.matlabc_sha256` | `fa5ced62…` → `69bed231…` | 归属 |
| `results[0].git_head` | `b778fe64…` → `c7abc014…` | 归属 |
| `results[0].matlabc_sha256` | `fa5ced62…` → `69bed231…` | 归属 |
| `results[0].peak_mb` | 150.4 → 149.0 | 时钟/资源 |
| `results[0].seconds` | 3.4 → 3.6 | 时钟 |
| `results[1].git_head` | `b778fe64…` → `c7abc014…` | 归属 |
| `results[1].matlabc_sha256` | `fa5ced62…` → `69bed231…` | 归属 |
| `results[1].peak_mb` | 11094.7 → 11089.6 | 时钟/资源 |
| `results[1].seconds` | 3526.6 → 2239.2 | 时钟 |

⇒ **读数叶子一处未变**（`std_funcs` / `std_edges` / `std_unresolved` /
`std_heuristics` / `json_bytes` / `files` / `funcs` / `edges` … 全都不在差异里）。

**② 三份产物 sha256（字节级）**

| 产物 | sha256（前 8） | 字节数 | 判定 |
|---|---|---|---|
| `kernel_c_summary.json` | `9a6bd04c` | 11,355,506 | **IDENTICAL** |
| `kernel_asm_summary.json` | `dff83833` | 486,229 | **IDENTICAL** |
| `kernel_callgraph.json` | `c4260966` | 4,358,990 | **IDENTICAL** |

**两层是互补的**，缺一不可：
① 只看「叶子名」，看不见「同一叶子名下的值被悄悄改掉却没产生新叶子」；
② 是字节级，看得见。两层同时成立，才是「**改动范围与 `c/asm` 臂不相交**」的实测证据。

⚠ **与 R108 那条结论性质不同**，别说成同一个：
R108 改的是 `matlabc.py` 的**用户可见文案**（惰性 ⇒ 产物不变 = 「文案对产物惰性」）；
R109 改的是 `matlabc.py` 的 **MATLAB 载荷**（在 `--lang matlab` 路径上）
⇒ 产物不变的原因是「**改动所在分支与 C/asm 臂不相交**」。
两者都能预言「产物不变」，但**机理不同** —— 把 R108 的理由套到 R109 上就是错的解释。

### §8.7 重跑读数与耗时口径

```
[07:11:14] provenance: matlabc=69bed231b013bb13 (1717722 B) HEAD=c7abc014de0e5a32720fd69e87c773313d62a600
[07:51:50] done kernel_c_summary:  rc=0 2239.2s peak=11089.6MB files=62704 funcs=743509 json=11355506B
[07:52:04] done kernel_asm_summary: rc=0    3.6s peak=  149.0MB                  json=486229B
[07:52:04] AGG written -> ...\AGG_r84.json
```

⚠ **同臂两次墙钟差 1.57 倍**（R108 的 `3526.6 s` → 本轮 `2239.2 s`），
与项目既有记录一致（⚠ 同臂相邻两次可差 3 倍）⇒ **只记读数，不归因版本**
（本轮改的是 MATLAB 载荷，不在 C 臂路径上，**没有理由**让它变快）。
`peak_mb` 11094.7 → 11089.6 同理，属读数抖动。


## §9 测试与基线：先**推算**再**实跑**

### §9.1 为什么这事有对手方

`tools/check_all.py` 的聚合**结构性地只跑 `tools/` 下的护栏、不跑 `tests/`**
（R102 的发现：整套 `tests/` 从 R99 起红着 23 条而**没有任何门看得见**）。
R102 补了对手方：`--with-tests` + `docs/TEST_BASELINE.json`。
本轮给 `tests/` 加了 1 条用例 ⇒ `passed` 的**下界**必须跟着抬 —— 这是纯级联。

### §9.2 AST 现数（**跑之前**的推算，不是跑完再补数字）

`_r109/probe_tests_ast_r109.py` 数 `tests/` 下所有 `def test_*`：

```
   test_agent_loop.py                         15
   test_analyzer_memory.py                     6
   test_entity_contract.py                     9
   test_eval_ai_fix.py                         2
   test_matlabc.py                           516
   <TOTAL>                                   548

test_matlabc.py 用例数 = 516
跨文件重名用例 = 0
本轮新增 test_r109_matlab_payload_wiring 命中 = 1

推算：R108 passed=543；本轮 AST 新增 1 条 ⇒ 预测 passed=544（下界，容差 5 不放宽）
VERDICT OK
```

⚠ **口径是「增量」不是「绝对值」**：AST 数（516/548）与 pytest 的 `passed`（543）
**不是同一个量**（收集口径、参数化、跳过各不同）⇒ 本探针只断言
**「`passed` 的差值 == AST 函数的差值」**（R107/R108 两次实测都对上）。
不去猜绝对值，就不会把口径差误读成回归。


### §9.3 实跑：**先红、归因、再修**（本轮唯一一次「对象错」）

修复**前**那一次 `--with-tests` 的实测读数（`_r109/check_all_with_tests_r109.log`，
**首两行 + 末两行**；中间 23 行是余量读数，见 §7 末尾）：

```
check_all: pytest 退出码 1
check_all: 实测汇总 (failed, passed, skipped) = (1, 543, 4)
  …（23 行余量记录）…
check_all: 测试红数变多（1 > 基线 0）—— 新红没有任何门在看，先逐条归因（量具错还是对象错），再修或改表
EXIT=1
```

⇒ **总数 548 = 543 + 1 + 4，与 §9.2 的 AST 总数逐字对上**；门按设计把它抓了出来
（这正是 R102 补这条判据的用途 —— R99–R102 那 23 条红**没有任何门看得见**）。

归因链（每一步都是读数，不是推测）：

1. **门报的 `failed_nodeids` 名单为空** —— `_run_tests` 用 `--tb=no`，
   `FAILED ` 行在这份输出里丢失（这是**观测量本身的缺口**，见 §12 ⑫）。
2. 改跑 `pytest -q --tb=short` 定位收集序号：`..............................F`
   ⇒ 第 **31** 个。`--collect-only` 显示第 31 个是 **旧用例**
   `tests/test_eval_ai_fix.py::TestAiFixEval::test_eval_metrics_green`
   —— **不是**本轮新加的那条（新条在 `test_matlabc.py`，收集序里靠后）。
3. 断言原文：`AssertionError: False != True : dead_code 必须被确定性引擎端到端删除`
   ⇒ `auto_fix_engine_ok=False`，即 `_scan` 的**告警总数**回不到基线。
4. **worktree 隔离实验（决定性）**：`git worktree add /e/matlabc/_r109/wt_r108 951dacd`
   （该树的 `matlabc.py = fa5ced62…`，即 R108 树），**同解释器、同一条用例** ⇒ **2 passed**。
   ⇒ 同一条用例在 R108 树绿、在 R109 树红，**变量只有 `matlabc.py`** ⇒ 定性为
   **我引入的「对象错」**（不是量具错、不是历史 flaky）。
5. 两个诊断探针取实测：`base_total` 由 `0/0/0/0` 变成 **`2/2/5/2`**；
   `probe_eval_alerts_r109.py` 显示增量 **100% 是 `heuristic` / `level=note`**。
6. 查 C 侧 `heuristics` 契约（**不是**凭记忆）：条目键集合
   `{file, func, kind, level, line, msg}`、`c_missing_doc` 的 `level="note"`
   —— 与我接进载荷的形状**逐字同形** ⇒ **接线本身合规**。
7. ⇒ 结论：错的不是接线，是**度量口径** —— 旧判据用「告警**总数**回到基线」判引擎是否修好，
   而 `note` 级文档提示是**新接线的正常副产物**，既**不该修**、也**修不了**。

**外科式修**（`tests/eval_ai_fix.py`，只碰必须碰的）：

```python
DOC_NOTE_LEVEL = "note"

def _scan(directory):
    '''返回 (by_rule, total, defect_total)。…（含实测理由：R109 接线让基线 0→2/2/5/2，全是 heuristic/note）'''
    report = analyze(directory, "matlab")
    by_rule, total = count_alerts(report)
    alerts = load_alerts(report)
    defect = sum(1 for a in alerts if (a.get("level") or "") != DOC_NOTE_LEVEL)
    return by_rule, total, defect

        # 只让「引擎是否修好」用**缺陷级**口径（原先用总数，被 note 级提示污染）：
        engine_fixed = (edef == base_defect)
```

`good_restores` / `bad_caught` / 通过率**仍用全部告警**（口径未削弱，反而更严）。

**同时抬强度**（R104 ㉖「修量具时判据强度只许升」）—— `tests/test_eval_ai_fix.py`
加两条断言，防「空集上恒真」：

```python
self.assertEqual(m["baseline_defect_total"], 0,
    "干净玩具基线不应有**缺陷级**告警（`note` 级文档提示可以有）")
for d in m["details"]:
    if d.get("result") == "INJECTION_NO_OP":
        continue
    self.assertGreaterEqual(d["injected_defect_delta"], 1,
        "注入必须产生**缺陷级**告警，否则 engine_fixed 测的是空集（%s：injected_defect_delta=%r）"
        % (d.get("case"), d.get("injected_defect_delta")))
```

单跑该用例：`2 passed in 18.98s`；探针复核 `auto_fix_engine_ok=True`、
`fix_success_rate 1.0` / `bad_fix_caught_rate 1.0` / `alarm_net_reduction 1.0`。

**修复后整轮 `--with-tests` 实测**（`_r109/check_all_with_tests_r109b.log`）：

```
check_all: pytest 退出码 0
check_all: 实测汇总 (failed, passed, skipped) = (0, 544, 4)
check_all: 测试基线一致（docs\TEST_BASELINE.json）
check_all: OK（21 个护栏，全部通过且各自自证；门数下限 21）
```

（进程退出码 **0**；上面 4 行是 `check_all_with_tests_r109b.log` 的**末 4 行**，
逐字照抄 —— 含 Windows 反斜杠路径。）

⇒ 与 §9.2 的推算**差值 == AST 函数的差值**（+1，543→544）逐字对上；
`failed` 回到 0、`skipped` 仍 4（R102 记的「4 条取决于本机是否装 node/jsdom」）。
`passed` 的下界据此由 543 抬到 **544** —— 抬下界只会让「通过数变少」更早报红，是**收紧**。


## §10 我自己的错（本轮全部，逐条）

本轮共 **8 处「我自己写下的东西是错的」**：

| # | 错在哪 | 性质 | 怎么发现 | 处置 |
|---|---|---|---|---|
| 1 | 重跑**在脏工作树上**启动 | 口径 | 日志第一行 `HEAD=951dacd3…` 不含被测物 | 当场 `TaskStop`（只损失 1m15s）→ 先提交 `c7abc01` → 重启 |
| 2 | `_patchlib` 的「new 已存在」守卫**误伤子串锚点** | 工具 | 补丁中止并打印「已打过」 | 把上一行写进 `old`/`new` 当上下文 ⇒ `new` 不再被任何行独占 |
| 3 | 探针断言 `unresolved` 名字恰为 `Mist`（实测 `mist`） | 量具 | 探针自报不符 | 断言改 `{'mist'}` + 注明「解析器折叠小写，非接线偏差」 |
| 4 | `gen_demo_r109.py` 的 `out_path` 没接上写盘 | 接线 | 覆盖参数不生效 | 三处一并改（`grep` 确认无残留常量） |
| 5 | `demo_verify` 的 C3/C4 两版**过强** + 一次样本错 | 量具 | 一跑就报 `dynlibs.html` / 5 个 `.h` | 见 §7.2 ㊱-1/2/3（改由对象决定形状） |
| 6 | 生成器自检的 `<tr>` 期望值**漏了 prov 表 6 行** | 期望值 | 自检 32 != 26 | 改成从 `<tbody>` 里数（不再受页尾改动影响） |
| 7 | NEGCTRL 样本只删 `href` 没删 `<a>`；C3/C4 仍未由页面读数决定 | 样本 + 量具 | NEGCTRL 6/6 报出一例方向不符 | 修样本；C3′/C4′ 改为读页面的**函数/出边/入边**卡片 |
| 8 | `tests/eval_ai_fix.py` 的 `engine_fixed` 用**告警总数**回基线判引擎是否修好，被新接线的 `note` 级提示污染 | **对象错** | `--with-tests` 门自己报「测试红数变多（1 > 基线 0）」 | 见 §9.3：worktree 隔离实验定性 ⇒ `_scan` 增 `defect_total`、只让 `engine_fixed` 用缺陷级 + 加严两条用例 |

**统计与结论**：8 处里 **5 处是「量具 / 样本 / 期望值」**、**2 处是「口径 / 接线」**、
**1 处是「对象错」**（第 8 项）。前 7 处**没有一处**证明被测物错；
第 8 处是**唯一一次**被测侧被证伪 —— 而它正是被**门自己**抓出来的（不是人肉发现），
这恰好说明「`--with-tests` + 测试基线」这条判据在**第一次遇到真回归时就起作用了**。

> ⚠ 第 8 项的教训值得单列：**接线对了，度量口径也会错**。
> 新接线带进来的 `note` 级提示是**正常输出**，但旧口径把它当成了「没修好」。
> 如果本轮没有 worktree 隔离实验，很容易把结论写成「接线有问题」而**改错地方**（去弱化接线）。
> 判别式：**先证明「变量只有被测物」**，再决定改被测物还是改量具。

> 这再次印证项目那条纪律：**先问「量具错还是对象错」，再决定改谁**。
> 本轮 7 次判定**全部**落在量具侧；若少了「先测量 / 先自证」这两步，
> 第 5、6、7 条都会以**全绿**的形态静静过去（判据恒真而不自知）。

⚠ 记法沿用项目既有累计口径（R107 时记到 34；本轮第 3 条即当时编号的「第 35 次」）。
本表按**本轮**用 1–7 重新编号，避免与历史编号打架。


## §11 诚实边界（本轮**没有**做到 / 不能声称的）

1. **站点规模与 R81 不可直接对比**：R99/R101 之后站点形态变了
   （多了 `funcs.html` / `deps.html` / `dir/` / `src/`），页数 62,920 → **98,356**。
   所以本轮**不写**「页数增长 x%」这类话 —— 分母不是同一个东西。
2. **`edges` 两套口径不并排**：`site-index.json` 的 `edges`（逐目录求和 = 2,427,130）
   ≠ 整树 `kernel_c_summary.json` 的调用边（**7,060,966**）。本报告只在各自处出现，
   不做比值。
3. **「零 JS」的准确含义**：只证明**没有 `<script>` 标签**（98,357 页全量），
   **不**声称「与 JS 无关的一切都为零」。
4. **asm 臂不是整树**：1,369 个 `.S/.s` 文件、381,729 行 —— 它是独立语料，
   不要与 C 臂的 62,704 文件并排当「两臂覆盖同一棵树」。
5. **MATLAB 三格转绿的范围**：只覆盖对等表 §3.2 记的三处「口径分裂」
   （`metrics_complexity` / `unresolved_attribution` / `heuristics_channel`）。
   7 格缺口 → **4 格**，剩下 **4 格全是 JS**，**未**收。
6. **MATLAB `heuristics` 只接了**一类规则（`m_missing_doc`，即有直接 C 对应物的那一类）。
   MATLAB 前端另有其它启发式**未**进载荷 —— §3.2 的范围警告段已写明。
7. **§7.7 那处真发现未修**：只做了**精确定性**（零可解析边 ⇒ 图内只画外部节点；
   40 个标签塌成同一个 `atomic6…`）。修它要动 `matlabc.py` ⇒ 必须配一次整树重跑 ⇒ 留给 R110。
8. **C3′/C4′ 的全量覆盖**：C1/C2 做到了**全量**（98,357 页）；C3′/C4′ 目前是
   **逐子站全量**（`block` 95 页、`rust` 59 页）+ 跨 4 个目录的对照集（函数 ≥ 50 共 221 页）。
   **没有**对全部 98,357 页做 C3′/C4′ 扫描。
9. **测试 `passed` 的 @P@ 已由实跑落地**（§9.3：`(0, @P@, @S@)`）；§9.2 的「544」只是
   **跑前推算**（AST 增量口径），它只用来证「差值 == AST 差值」，**不作为绝对值依据**。
10. **远端回证**：本节写作时尚未执行（见 §9.3 之后的收尾）。
11. **`--sweepall` 未跑**：它为「全量 C3′/C4′」准备，本轮时间预算内是否执行见 §7 末尾补记。


## §12 R110 的建设性意见（按性价比排序）

**① MATLAB 的三格 `no` 已收；下一优先是 JS 4 格（计划表槽 28）。**
`classes` / `entities`（**缺 C8 实体契约测试**）/ `call_edges_qualified` /
`call_edges_oneline_body`。JS 4 格 + 已收的 3 格 = 原本 7 格缺口。
⚠ 它与「改 `matlabc.py`」必须**合轮**（改一个字节 ⇒ W2 必红 ⇒ 必须配整树重跑，
59 分钟级）；**不动 `matlabc.py` 的事应当单独成轮**。

**② 台账与驱动**整体**入库**（单独一轮，**不动 `matlabc.py`**）：
`_r82/evolve_loop.py` + `gen_plan_ledger_digest.py` + `_r82/rounds.jsonl` +
`gen_kernel_run_doc.py` + `probe_kernel_r84.py`。
依赖已实测：`docs/EVOLVE_ROADMAP_360.md`（**12 处**）+ `tools/check_all.py:421`（**判据正文**）
+ `harness/README.md` + `harness/*.py` + `tests/`（**7 处**）。

**③ 紧跟 ② 同轮**修计划表槽 **25**（R101 已落地）/ 槽 **26**（R106 已落地）的
「待手工落地」**陈旧登记**：改这两行 ⇒ round 3/4 指纹变 ⇒ digest 必须重生成，
而生成器正是 ② 要入库的那个 —— **顺序不能反**。

**④ 给「计划表 ⇄ 对等表已落地记号」加一道判据**：本轮从对等表 §6 找到**第二例**同形陈旧行
（「画布对等（槽 29）」早已 `yes`，表里却是未加删除线的旧说法）。
同一形状在一轮里出现两次 ⇒ 值得做成常开判据，而不是靠人记得。

**⑤ 把「两个独立口径必须交叉」做成常开判据**（R104 ㉞）：
本轮又做出**一个实例**（⓪ 分辨力自证 + ①② 两层对账），但仍是「我记得要写」而非「判据要求」。

**⑥ ⑤ 的具体化 —— 把本轮的演示量具入库**：
`demo_verify_r109.py`（C1–C4′ + `--sitewide` + `--sweepall` + `--links`）、
`gen_demo_r109.py`（含产物自证 + NEGCTRL）、`diff_agg_r109.py`（两层对账）。
它们目前**全在仓外**，下一轮就看不见了。

**⑦ `.c` 页零可解析边时，图内应画出本文件函数节点**（§7.7 真发现）：
现在 170 个函数一个节点都不画，与 svg 自己的 `<desc>`
（「节点可点击跳到源码行」）不符。修它 ⇒ 与 ① 合轮（同一次重跑）。

**⑧ 图内标签截断需保分辨力**（§7.7 第二处）：
40 个不同名字 → 同一个 `atomic6…`。截断策略应保证**去重后仍可区分**
（尾缀/序号/悬停全名）。同样可与 ① 合轮。

**⑨ 补 R100 那笔缺的 +602 记账**（`HELP_BYTES_SNAPSHOT`）。

**⑩ `renderers/report.py` 标题/描述不同源**：`--title` 改得动标题、改不动
`<meta description>`。⚠ 已裁定**不是**「语言无关却写死语言名」类缺陷
（`--lang c/py/js/asm` 在 `matlabc.py:32978` 就 `return` ⇒ 专属路径），
所以它是**独立的一条**，别与 R108 那类混。

**⑪ `matlabc_ask.normalize` 的 `rule`/`rel` 与载荷的 `kind`/`file` 不同源**：
`normalize`（`matlabc_ask.py`）读 `h.get("rule")` / `h.get("rel")`，
而本轮接进载荷的键是 `kind` / `file`（与 C 侧逐字同形）⇒ 落到 alerts 里
`rule` 恒为 `"heuristic"`、`rel` 恒为空。**这不是接线错**（载荷按契约写），
而是**消费侧读了一个不存在的键** —— 同一份数据两个键名，属「口径分裂」的同形复发。
处置二选一：让 `normalize` 兼容 `kind`/`file`（消费侧改，**不动 `matlabc.py`** ⇒ 可单独成轮），
或统一键名（**要动 `matlabc.py`** ⇒ 必须与整树重跑合轮）。

**⑫ `failed_nodeids` 名单在真回归时是空的**（§9.3 第 1 步）：
实测那次失败的输出里，`check_all:   `（三空格）前缀的行**一共 23 条、全部是余量记录**，
**没有一条是 nodeid** ⇒ 门想给的「红数**带名字**」在**唯一一次真回归**上恰好没产出。
（`failed_nodeids` 本身有 8 个两向样本自证 ⇒ **不是函数错**，是**喂给它的文本里没有**。）
疑点是 `_run_tests` 的 `pytest -q -rf -rs --tb=no`：`--tb=no` 与 `-rf` 摘要的交互
可能把 `FAILED ` 行一起吞掉 —— 但**先观测再定修法**（量一次 `--tb=no` vs `--tb=short`
各自输出里 `FAILED ` 的条数），**不要凭印象改**。本条属「**判据的观测量缺口**」，
与 R106「红数没名字＝归因盲区」同形但更隐蔽：字段**存在**、函数**有自证**，
只是**真实运行时不产出**。


