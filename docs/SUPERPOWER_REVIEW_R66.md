# R66 复盘：把 C / Python / JS 三条语言验证摆到同一把尺子上

> 本轮靶子 = 用户指定：「再次检查下 C 语言以及 Python 语言的验证以及 JS 的验证，
> 使用尽可能最严的标准来验证」。
>
> R61 已经给 **C 前端**装上形态门（`tools/check_c_frontend_shapes.py`，F1–F6）；
> **Python / JS 前端自 P93 起就存在，却从未有过任何形态判据**，
> 也没有人量过它们到底认不认得最常见的写法。
> 本轮第一次把三条路径放进**同一台装置**，量出**两个真产品缺陷**、修掉、
> 再补上缺失的那个对手方（**第 16 道门**）。
>
> ⚠ 与 R63/R64/R65 不同，本轮**不是零产品变更轮**：`matlabc.py` 的
> Python / JS 定义识别被**重写**（+236 行），用户可观察行为有变化。

## §1 白帽：事实与读数

### §1.1 第一次同尺测量（装置 A：24 个形态，只走公开 CLI）

`_r66/probe_r66a_forms.py`（仓库外，LF）把三条路径放进**同一台装置**：
每个形态**单独一个目录、单独一次** `matlabc.py <dir> --lang X --json out.json`，
只问一件事 —— **这个该被认出来的函数，有没有出现在 `files[].functions[]` 里**。

基线（HEAD `43dce7f`）逐字读数：

```
>>> lang=py 漏掉的形态: 4 / 8
>>> lang=js 漏掉的形态: 8 / 10
>>> lang=c 漏掉的形态: 0 / 6
```

| 语言 | 形态数 | 漏 | 漏掉的是哪几个 |
| --- | --- | --- | --- |
| Python | 8 | **4** | `def one(): return 1`（单行体）· `async def afetch` · `def typed(a: int, b: str) -> bool:`（返回注解）· 参数表跨行 |
| JS | 10 | **8** | `async function` · `export function` · `export default function` · `function*` · 三种箭头（块体 / 表达式体 / `async`）· 对象方法简写 |
| **C（对照）** | 6 | **0** | —— |

**三条路径此前从未被放在同一把尺子上量过。** C 有 R61 的门守着，Python / JS 没有 ——
读数正好把这件事摊开：C 是 0，py / js 是 4 和 8。

### §1.2 第二台装置：值域与假阳性

装置 A 只问「在不在」，不问「对不对」。`_r66/probe_r66b_domain.py` 问第二层：
`params` 是否**逐字段**相等，以及**不该出现的名字**是否出现。

对 R66 之前的**干净工作树**（`git worktree` 拉 `43dce7f`）实跑：

| 项 | 基线 | 修后 |
| --- | --- | --- |
| 值域不符 | **7 / 8** | **0 / 8** |
| 假阳性 | 0 / 7 | 0 / 7 |

值域那 7 条错，分两类：

- **整条定义消失**（2 条）：`def typed(a: int, b: str = 'x') -> bool:` 与
  `def g(x=(1, 2), y=g2(3, 4)):` —— 函数表里**根本没有这两个名字**。
- **形参取值错**（5 条）：`function h(a, b = g(1, 2))` ⇒ `['a', 'b = g(1', '2']`；
  `def k(a, *, b)` ⇒ `['a', '*', 'b']`；`def p(a, /, b)` ⇒ `['a', '/', 'b']`
  （裸 `*` 与 `/` 这些**位置记号**被当成了形参名）。

> ⚠ 口径提醒：`_r66/probe_r66b.txt` 那一次（00:08）是**打完补丁 A 之后**跑的，
> 它显示 2 / 8 —— 那是「形态修了、括号还没修」的中间态。**真基线**是
> `probe_r66b_base.txt` 的 **7 / 8**。这个区别写在这里，免得后人对不上账。

### §1.3 根因：两条，都在同一处（基线 `matlabc.py:8516`）

基线实现（逐字）：

```python
_RE_PY_DEF = re.compile(r"^def\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*:\s*$")
_RE_JS_FN_DECL = re.compile(r"^function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{?")
_RE_JS_FN_ASSIGN = re.compile(r"^([A-Za-z_$][\w$]*)\s*=\s*(?:function\s*)?"
                              r"\(([^)]*)\)\s*(?:=>)?\s*\{?")
```

**D1「形态」—— 老正则把「函数头」当成「一整行」。** 三个后果，逐条对上读数：

| 正则里的写法 | 排除了什么 | 对应读数 |
| --- | --- | --- |
| 没有 `(?:async\s+)?` 前缀 | 所有 `async def` / `async function` | P-async · J-async-decl |
| `\s*:\s*$`（冒号必须是**行末最后一个非空字符**） | 冒号后面还有内容的写法 → **单行体**、**返回注解** | P-oneliner · P-annotation |
| head 正则要求 `)` 与 `:` / `{` **同行** | 参数表跨行的写法 | P-multiline-params |
| head 只以 `function` / 裸标识符 `name =` 起手 | `export` · `export default` · `function*` · 箭头（`const f = (a) =>`） | J-export-\* · J-generator · J-arrow-\* |

**D2「括号平衡」—— 形参用 `\(([^)]*)\)` 取，而 `[^)]*` 不能含 `)`。**

```
def g(x=(1, 2), y=g2(3, 4)):   ⇒  匹配到第一个 ')' 就截止 ⇒ 整条定义**消失**
function h(a, b = g(1, 2)) {   ⇒  params 被切成 ['a', 'b = g(1', '2']
```

再加一条：形参用 `dm.group(2).split(",")` **裸切**，于是位置记号 `/` 与裸 `*`
被当成形参名。

**为什么 D2 比 D1 更值得先修**：D1 是「少认一种写法」（**漏**），
D2 是「把正确的写法认错」（**错**）—— 后者会把**不存在的形参名**送进未解析名字判定、
把**错误的形参个数**送进 IR。漏认只少报，认错会污染调用图。

### §1.4 修后复量（同一台装置 / 同一台机器 / 同一解释器）

| 读数 | 基线 `43dce7f` | 打完 A（形态） | 打完 B（括号平衡） |
| --- | --- | --- | --- |
| Python 形态漏 | 4 / 8 | 0 / 8 | **0 / 8** |
| JS 形态漏 | 8 / 10 | 1 / 10 | **1 / 10** |
| C 形态漏（对照） | 0 / 6 | 0 / 6 | **0 / 6** |
| 值域不符 | 7 / 8 | 2 / 8 | **0 / 8** |
| 假阳性 | 0 / 7 | 0 / 7 | **0 / 7** |

剩的那 **JS 1 / 10** 是 `greet(a) { }`（对象方法简写）—— **有意不识别**，理由见 §2，
并且由新门的 **G5** 正面钉住（认出来反而会让门红）。

### §1.5 一条必须说清的区分：漏认 ≠ 误认

两台装置都量出**假阳性 0 / 7**：这两条缺陷**只少认、不误认**。
而**过度识别**（over-recognition，即「不该认的却认了」）**基线就有**，
本轮**既没恶化、也没修**。`_r66/probe_r66c_overrecog.py` 用
`git worktree`（R66 之前的干净树）做对照，**量出**而非推断：

| 用例 | 基线 | 修后 |
| --- | --- | --- |
| 三引号字符串里独占一行的 `def ghost(a, b):` | **泄漏**（`ghost` 进了函数表） | **泄漏** |
| 块注释里独占一行的 `function ghost(a, b) {}` | **泄漏** | **泄漏** |
| 单行字符串里的 `def` / `//` 行注释里的 `function` | 不泄漏 | 不泄漏 |
| **合计** | **2 / 6** | **2 / 6** |

机理：扫描器**按行锚定**（定义必须落在行首）⇒ 单行字符串与 `//` 注释**天然免疫**；
而三引号字符串 / 块注释里独占一行的 `def` / `function` 会命中。
这条留在 §8 的 **C16-1**。

## §2 黑帽：这一版**不解决**什么（诚实列表）

1. **对象方法简写**（`const obj = { greet(a) { } }`）不识别 —— 它是**已披露边界**，
   新门 G5 正把它**钉住**（认出来会让门红）。想认它得先改 G5 的登记，是独立一轮。
2. **匿名 default**（`export default function (a) { }`）不识别 —— 同上，G5 钉住。
3. `module.exports.foo = function (a) { }` 不识别 —— 新 head 正则里
   `name = function` 要求 `name` 是**行首裸标识符**。
4. **过度识别未修**：docstring / 块注释里独占一行的定义会被当成真函数（§1.5）。
   修它需要**字符串与注释状态机**，不是括号平衡能覆盖的。
5. `ret` 字段仍是**常量**：Python 恒 `"None"`、JS 恒 `"void"` —— 没有任何装置核对它。
   本轮**没有**让它跟着 `-> bool` 走；那会把改动面从「定义识别」扩到「类型推断」。
6. `complexity` 仍只是关键词计数（`if` / `elif` / `for` / `while` / `and` / `or` /
   `try` / `except`），**不是** CFG —— 本轮不动。
7. 本轮只量了 **py / js / c 三条**；**`matlab` 路径（默认语言）不在射程内**，
   也没有形态门。这是本轮射程的边界，不是「matlab 没有缺陷」。
8. 新门的夹具是**纯合成**的：它证明「这 4 个夹具 + 6 条判据」是活的，
   **不证明**产品在真实大仓（`node_modules`、生成代码）上的表现。
9. `frontends/__init__.py` 的 `IR_LANG_OWNERS` 里只有 C 的
   `_C_SOURCE_EXTS` 有「单一事实源」那一条唯一性声明；新的 py / js 两个扫描器
   **没有**同等级的登记（见 §8 C16-5）。
10. **B 类永久红**（`setup.py` / `analyzer_config.example.json` / `fe_audit.py` 等 6 件）
    仍挂着 47 条红 —— 本轮**不碰**（需用户拍板，见 §8 C16-6）。

## §3 落地物（全部真实现，无占位符）

### §3.1 四个纯函数（可被 `--selftest` 两向驱动，不需要子进程）

| 函数 | 位置 | 职责 |
| --- | --- | --- |
| `_split_top_commas(raw)` | `matlabc.py:8554` | **深度感知**的逗号切分：`()` / `[]` / `{}` 里的逗号不算分隔符 |
| `_paren_span(s, open_idx)` | `matlabc.py:8714` | 从 `(` 找出**配平**的 `)`，返回 `(inner, close_idx)`；配不平返回 `(None, None)` |
| `_py_split_params(raw)` | `matlabc.py:8579` | 剥注解、剥 `=默认值`、丢 `/` 与裸 `*`、**保留** `*args` / `**kw` 的星号 |
| `_js_split_params(raw)` | `matlabc.py:8734` | JS 版：**保留**默认值原文（`b = g(1, 2)` 整段留下），只按顶层逗号切 |

> `_js_split_params` 保留默认值、`_py_split_params` 剥默认值 —— 这是**有意**的不对称：
> Python 侧的值域期望是形参**名字**，JS 侧的期望是形参**原文**。两侧都由 G3 钉住。

### §3.2 两个词法扫描器

| 扫描器 | 位置 | 做什么 |
| --- | --- | --- |
| `_scan_py_defs(text)` | `matlabc.py:8604` | 逐行找 `^\s*(?:async\s+)?def name(`，用 `_paren_span` 吃掉**跨行**的形参表，返回 `[{name, params, line, indent}]`；防御上限 40 行 |
| `_scan_js_defs(text)` | `matlabc.py:8739` | 四条 head 正则（decl / fn-assign / arrow-parens / arrow-bare），同样用 `_paren_span` 配平 |

四条 JS head 正则（`matlabc.py:8532–8543`）：`_RE_JS_HEAD_DECL`、`_RE_JS_HEAD_FNASSIGN`、
`_RE_JS_HEAD_ARROW_PARENS`、`_RE_JS_HEAD_ARROW_BARE`。
Python 侧：`_RE_PY_DEF_HEAD`（`8519`）取名字与 `(`，`_RE_PY_REST`（`8516`）取 `:` 之后的部分。

### §3.3 接线：`_defs_by_line`（预扫 + 按行查表）

`_parse_py_source` / `_parse_js_source` 现在都先 `_scan_*_defs(text)` 建一张
`{行号: [定义]}` 的表（`matlabc.py:8662` / `8802`），主循环走到那一行时**按行查表**。
这样「声明起点行号」天然正确 —— 跨行形参表的函数，`line` 是 `def` 那一行，
不是参数表末行、也不是 `{` 那一行。这是 **G6** 的对手方。

### §3.4 第 16 道门：`tools/check_py_js_frontend_shapes.py`

705 行 / 32,212 B；`ROW_SIGNATURE = "G1–G6"`。

结构与 `check_c_frontend_shapes.py` **逐条对齐**：纯合成夹具 + **公开 CLI 子进程** +
**每条判据各有自己的突变体** + 夹具完备性 + 棘轮。
为什么走子进程而不 `import matlabc`：与 R54 / R55 / R61 同一条纪律 ——
`tools/` 不 import 产品模块；公开 CLI（`--lang py|js --json`）才是用户真正看到的那一面。

| 判据 | 管辖范围（**互不重叠**） | 对手方（什么会红） |
| --- | --- | --- |
| G1 | Python 四形态**存在性** | `one` / `afetch` / `typed` / `wide` 少任一 |
| G2 | JS 七形态**存在性** | `fetchIt` / `exp` / `main2` / `gen` / `f` / `g` / `h` 少任一 |
| G3 | 形参**值域**逐字段相等 | `typed` / `wide` / `deep`（py）、`h2`（js）的 params 改一个字 |
| G4 | 不假阳 | py `lam` / `compute` / `if`；js `if` / `for` / `while` / `switch` / `foo` / `bar` / `obj` 出现即红 |
| G5 | 已披露边界保持不识别（`greet`）**+ 正向半边** | 边界被认出来 ⇒ 红；`neg.py` / `neg.js` 里的真函数消失 ⇒ 红 |
| G6 | 声明**起点行号** | 跨行形参表的 `line` 漂一行 ⇒ 红 |

**为什么 G5 必须有正向半边**：只写「必须不出现」的判据，在「产品什么都不产出」时
**也成立** —— 那是**空断言**。G4 天然受 G1 / G2 保护（否则整门早红了），
但 G5 的 neg 夹具里**只有 `real` 一个真函数**，必须显式要求它出现。

棘轮（`R1`）：`EXPECTED_CRITERIA = 6` · `EXPECTED_FIXTURES = 4` · `EXPECTED_G1 = 4` ·
`EXPECTED_G2 = 7` · `EXPECTED_BOUNDARY_TRAPS = 1` · `EXPECTED_PY_FUNCS = 10` ·
`EXPECTED_JS_FUNCS = 11`。
夹具完备性（`R2`）：每个陷阱名与每个形态标记必须**逐字**出现在夹具源码里 ——
挡住「夹具被悄悄改瘦」。

`--selftest`：1 个好样本 + **11 个坏样本**喂给**纯函数** `judge()`，
每个坏样本必须红在**它该红的**那条判据上，且**只**红那一条（`others == []`）；
另外自证夹具完备性两向、棘轮两向、坏 JSON 判为缺输入。

`judge()` 的 **G0** 是「形状自检」：`per` 不是 `{节点: 判据}` 的形状就直接红 ——
避免「判据自己坏了却报绿」。

### §3.5 护栏数级联 15 → 16

| 位置 | 改动 |
| --- | --- |
| `tools/check_all.py` | `MIN_GUARDS = 15 → 16` + 护栏清单图新增一行 |
| `tools/check_help_contract.py` | `GUARD_CONTRACT` 新增本门的 `{0,1,2}` 退出码契约 |
| `matlabc.py:111` | 帮助正文 `15 道登记制护栏` → `16 道` |
| `README.md` / `README_CN.md` | 质量门表新增本门一行（签名 `G1–G6` + 长散文）+ 散文数字 |
| `CONTRIBUTING.md` | 散文数字 + 本小节 |
| `tests/test_matlabc.py` | `MIN_GUARDS == 16` + 两条新测试 |

**这一轮的漏登记不是我先发现的** —— 是 R63 加的那道 **G0b** 当场抓到的：

```
check_help_contract: 1 项不一致
  - G0b tools/check_py_js_frontend_shapes.py 存在，但 GUARD_CONTRACT 没有登记它
        —— 它的退出码契约没有任何人在核对
```

紧接着它又抓出**四处散文数字**：

```
  - N1 matlabc.py:111 「15 道登记制护栏」说 15，真实护栏数是 16
  - N1 README.md:634 「15 gates」说 15，真实护栏数是 16
  - N1 README_CN.md:611 「15 道门」说 15，真实护栏数是 16
  - N1 CONTRIBUTING.md:23 「（15 道，」说 15，真实护栏数是 16
```

**R63 埋下的两颗雷，本轮各响了一次** —— 而且都是**自动**响的，没人去翻。

### §3.6 帮助体积：等长改写，快照不动

`matlabc.py:111` 那句 `15 道` → `16 道` 是**等长改写**（1 个字符换 1 个字符），
所以 `HELP_BYTES_SNAPSHOT` 与 `HELP_CANON_SNAPSHOT` **都不需要动**，
`HELP_DRIFT_BYTES = 64` 也**没有放宽**。实测（`COLUMNS=80`）：托管 3.13 ⇒ **50,451 B / 557 行**，系统 3.10 ⇒ **50,481 B / 558 行**；
`COLUMNS=10000` ⇒ 3.13 **44,995 B** / 3.10 **45,025 B**。两处差都是 **30 B** —— 与 R64 量出的
「3.10 多印一行 metavar」逐字对上，且落在 `HELP_DRIFT_BYTES = 64` 内：这正是那条带子存在的理由。

> 本轮**没有**动 `--help` 的**篇幅**，只动了一个字符 —— 这正是不动快照的**原因**，
> 不是「忘了动」。

### §3.7 真调用者：两条测试

- `test_r66_py_js_frontend_shapes_two_way`：
  ① 跑门（rc=0，成功行含 `G1–G6`）；
  ② 跑 `--selftest`（`bad == 0 and good >= 18`）；
  ③ **驱动纯函数 `judge()`** 做两向突变 —— 四个 Python 形态逐一改名 /
  七个 JS 形态逐一改名 / 三条 G3 值域突变（含 `h2` 的 `b = g(1, 2`）/
  两条 G4 假阳突变 / G5 边界突变 + 空 `neg.py` 突变 / G6 行号漂移 / 棘轮两向；
  ④ 再**端到端**跑一次公开 CLI，断言五个 Python 名与五个 JS 名被认出，
  且 `h2 == ["a", "b = g(1, 2)"]`。
- `test_r66_gate_registry_mentions_the_new_guard`：
  `MIN_GUARDS >= 16`、`GUARD_CONTRACT` 新条目 == `{0,1,2}`、
  `real_guard_count() == MIN_GUARDS`、两侧 README 都含本门名 **与** `G1–G6`。

两条测试**刻意不点名任何已登记产物** —— 避免撞 K1。
「在测试里点名一个已登记产物 = 一条登记义务」这条教训，R56 / R63 / R65 **三轮三次**踩过。

## §4 验证矩阵（数字全部来自定稿之后的最后一次回归）

| 项 | 命令 | 读数 |
| --- | --- | --- |
| 16 道护栏聚合 | `python tools/check_all.py` | **rc=0**（`16 个护栏，全部通过且各自自证；门数下限 16`） |
| 新门本体 | `python tools/check_py_js_frontend_shapes.py` | **rc=0**，成功行含 `G1–G6` |
| 新门两向自证 | `--selftest` | **`SELFTEST COUNTS {"bad": 0, "good": 24}`** |
| 退出码契约 + 散文数字 | `python tools/check_help_contract.py` | **rc=0**（`6 个入口脚本 + 17 个护栏脚本 + 4 个 CI 模板/示例`） |
| 散文数字两向自证 | `--selftest` | **rc=0** · `SELFTEST COUNTS {"bad": 40, "good": 37}` · `SELFTEST PASSED` |
| README 对等 | `python tools/check_readme_parity.py` | **rc=0**（`两侧质量门表各 16 行 == tools/check_*.py 的真实清单`） |
| 命令行开关 | `python tools/check_doc_flags.py` | **rc=0** |
| import 图 | `python tools/check_import_graph.py` | **rc=0**（模块级环 0；惰性环 1 已登记） |
| 帮助体积（臂①②） | `COLUMNS=80 … --help` | 3.13 ⇒ **50,451 B / 557 行** · 3.10 ⇒ **50,481 B / 558 行**（差 30 B 落在 ±64 B 带内） |
| 帮助规范形（臂③） | `COLUMNS=10000 … --help` | 3.13 ⇒ 44,995 B · 3.10 ⇒ 45,025 B；规范形逐字节等于 `HELP_CANON_SNAPSHOT`（容差 **0**） |
| 家族回归 | `pytest -q -k "r66 or r65 or r64 or r63 or r62 or r61 or p93 or r30b or p217g"` | **22 passed** · 445 deselected · 69.23 s · **0 failed** |
| 行尾 | 9 个改动/新增文件 | 全部 `bare_lf == 0`（`FILES_WITH_BARE_LF=0`） |
| 永久红登记 | `python tools/check_known_red.py` | **rc=0**（`红 47 / 优雅跳过 8 / 其余绿 4`；判据族 `K1–K9`） |
| 远端复核 | `_r66/verify_remote_r66.py` | 见 §4.1 |

### §4.1 定稿之后的完整读数（原文）

**① 16 道护栏聚合**（托管 3.13，零依赖 —— 顺带证明 `check_all` 不需要 pytest）：

```
check_all: OK（16 个护栏，全部通过且各自自证；门数下限 16）
```

`[OK  ]` 行 **16** 条，每条都是「主判据 + `--selftest`」双绿（本轮第一遍聚合时是
`check_all: 2 项失败：['check_help_contract.py', 'check_help_contract.py(selftest)']` ——
原因见 ⑧）。

**② 新门本体 + 两向自证**：

```
check_py_js_frontend_shapes: OK（4 个合成夹具 / 公开 CLI 认出 Python 10 个、JS 11 个函数 / G1–G6 全绿 + 夹具完备性 + 棘轮）
SELFTEST COUNTS {"bad": 0, "good": 24}
```

**③ 散文数字门**（`6 个入口脚本 + 17 个护栏脚本 + 4 个 CI 模板/示例`）：

```
check_help_contract: OK（… 4 份文档里的「N 道护栏」数字与事实一致 …；判据族 B0–B5）
SELFTEST COUNTS {"bad": 40, "good": 37}
SELFTEST PASSED
```

**④ README 双侧对等**：

```
check_readme_parity: OK（… 两侧质量门表各 16 行 == tools/check_*.py 的真实清单；
                        表行签名 P1/P2/P4/P5，16 道门的表行内容与那道门逐字对上）
```

**⑤ 帮助体积**（三臂，两种解释器各量一次）：

```
COLUMNS=80     3.13  bytes=50451  lines=557
COLUMNS=80     3.10  bytes=50481  lines=558
COLUMNS=10000  3.13  bytes=44995  lines=326
COLUMNS=10000  3.10  bytes=45025  lines=327
has 16 道登记制护栏: True
has 15 道登记制护栏: False
```

**⑥ 家族回归**（系统 3.10 / pytest 9.0.1）：

```
22 passed, 445 deselected in 69.23s (0:01:09)
```

**⑦ 行尾**：9 个文件 `FILES_WITH_BARE_LF=0`。

**⑧ 本轮的红与绿** —— 本轮**真红过两次**，都真、都当场修掉：

| 红的判据 | 说的是什么 | 处置 |
| --- | --- | --- |
| `check_help_contract` 的 **G0b** | 「`tools/check_py_js_frontend_shapes.py` 存在，但 `GUARD_CONTRACT` 没有登记它 —— 它的退出码契约没有任何人在核对」 | 补登记（`{0,1,2}`） |
| `check_help_contract` 的 **N1** | 「`CONTRIBUTING.md:415`『17 道门』说 17，真实护栏数是 16」 | 改成「第 16 道门」（§5.1-6） |

（`test_s9_missing_lang_is_error` 的 `ModuleNotFoundError: fe_audit` 是 R63 起就登记的
**B 类永久红**，不在本轮 `-k` 集合内，也不是本轮引入 —— 见 §2-10 / C16-6。）

## §5 轮次账本

| 轮 | 靶子 | 交付 |
| --- | --- | --- |
| R61 | C 前端形态没有对手方 | 第 14 道门 `check_c_frontend_shapes.py`（F1–F6）+ P4 换成「事实」 |
| R63 | 「永久红」是传说 | 第 15 道门 `check_known_red.py`（K1–K6）+ `_read_doc` + G0b + 基线 T1 |
| R64 | 帮助体积棘轮不可复现 | 三臂重构（钉死口径 / 绝对字节带 / 规范形容差 0） |
| R65 | 「实测」没有量具 | `--measure` + K7–K9 + 纯函数自证 + 一条四层测试 |
| **R66** | **py / js 语言验证从没被量过** | **py/js 定义识别重写（形态 + 括号平衡）+ 第 16 道门（G1–G6）+ 护栏数级联 15→16** |

### §5.1 本轮的自伤（都被抓、都已处置）

1. **补丁脚本里手工拼装多行字符串字面量** ⇒ `SyntaxError: invalid syntax.
   Perhaps you forgot a comma?` —— 与 R65 一模一样的坑（当时烧了两轮）。
   **处置**：整份补丁改成**原始三引号块 + `_crlf()` 归一器**，绝不手工拼接标点。
2. **补丁 B 造出重复的 `def` 行**（`def _parse_py_source` 与 `def _parse_js_source`
   各多出一条）⇒ `AST FAIL: expected an indented block after function definition`。
   **处置**：把「以 `return defs` 结尾」的那一片从新增块里摘掉、补回丢失的空行分隔。
   教训：**切片插入时，插入块的边界必须与它要替换的边界互相补足**。
3. **把 `probe_r66b.txt`（2/8）当成了基线**，而它其实是「打完 A 之后」的中间态。
   **处置**：本轮**补做**了真正的基线对照（`git worktree` 拉 `43dce7f`），
   拿到 **7 / 8**，并在 §1.2 把这个口径差别**写在明处**。
   —— 这是本轮的**第二次自伤**：**中间态读数容易被误当成基线**，
   因为文件名不会告诉你它是第几步跑的。以后三类读数（基线 / 中间态 / 复量）
   必须在文件名里就分开。
4. **`env={'COLUMNS':'80','PATH':''}` 把解释器打崩**（`Fatal Python error:
   _Py_HashRandomization_Init`）。**处置**：改 `env = dict(os.environ)` 后再改 `COLUMNS`。
5. **反例里差点点名已登记产物**（K1 的登记义务）—— 在写 §3.7 的两条测试时
   提前避开了，**没有**真的红一次。这条记下来是因为它**差点**发生。
6. **我把「17 个护栏脚本」当成了「17 道门」** ⇒ 在 `CONTRIBUTING.md` 里写下「这就是第 17 道门」，
   当场被 **N1** 抓住：

   ```
   - N1 CONTRIBUTING.md:415 「17 道门」说 17，真实护栏数是 16
   ```

   **处置**：四处表述改成「第 16 道门」。这里有**两个都合法、但不同**的数：

   | 数 | 定义 | 出现的场合 |
   | --- | --- | --- |
   | **16 道门** | `real_guard_count()` = `tools/check_*.py` **去掉 runner**（`check_all.py`） | README 质量门表的行数；**散文里的数字该用这个** |
   | **17 个护栏脚本** | 上面 16 道 **加上** `check_all.py` 自己（它也要有退出码契约） | `check_help_contract` 成功行里的数 |

   两个数**都对**，混用就错。**这道门区分得比我清楚** —— 它只抓「道门」，不碰「护栏脚本」。
   这也是本轮唯一一次**真红**（其余四处 N1 是修级联时按顺序红的）。

## §6 探针清单（`E:\matlabc\_r66\`，仓库外，LF）

| 文件 | 作用 | 关键读数 |
| --- | --- | --- |
| `probe_r66a_forms.py` / `.txt` | 24 个形态 × 公开 CLI（基线） | py **4/8** · js **8/10** · c **0/6** |
| `probe_r66a_after.txt` | ↑ 修后复量 | py **0/8** · js **1/10** · c **0/6** |
| `probe_r66b_domain.py` / `_base.txt` | 值域 + 假阳性（**真基线**，走 `base_tree`） | 值域 **7/8** · 假阳 **0/7** |
| `probe_r66b.txt` | ↑ 的**中间态**（打完 A 之后） | 值域 2/8 |
| `probe_r66b_after.txt` | ↑ 修后复量 | 值域 **0/8** · 假阳 **0/7** |
| `probe_r66c_overrecog.py` / `.txt` / `_base.txt` | **过度识别**两向（docstring / 注释 / 字符串） | 基线 **2/6** → 修后 **2/6**（未恶化、未修） |
| `base_tree/` | `git worktree` 拉出的 R66 之前干净树 | 供 ↑ 做对照 |
| `patch_r66a.py` | 改 py/js 定义识别**形态** | 两阶段全或无 |
| `patch_r66b.py` | 加 `_paren_span` + 两个扫描器**括号平衡** | 同上 |
| `patch_r66c.py` | `GUARD_CONTRACT` + `MIN_GUARDS 15→16` + 清单图 | 同上 |
| `patch_r66d.py` | 四处散文数字 + 两侧 README 表行 + 测试棘轮 | 同上 |
| `patch_r66e.py` | 两条新测试 | 同上 |
| `to_crlf.py` | LF → CRLF 归一器（含 `ast.parse` + bare_lf 断言） | —— |

## §7 盲区（诚实列表）

1. 新门只守**合成夹具**；真实大仓（`node_modules`、生成代码、`babel` 转译产物）
   的表现**没有被量过**。
2. `ret` / `complexity` **没有对手方**（§2-5 / §2-6）。
3. **过度识别没有对手方**（§1.5）—— 新门的 G4 只管「该不出现的没出现」，
   管的是**老实现也守得住**的那些名字（`lambda` / 控制语句 / 对象键），
   **不覆盖** docstring 里的假定义。
4. `matlab` 路径（默认语言）**不在射程内**（§2-7）。
5. 三条路径的**形态集合是我挑的**（py 8 / js 10 / c 6）—— 「最严」在这里的含义是
   「我挑的这 24 个形态必须全对」，**不是**「穷尽了所有形态」。
   形态集合本身**没有**登记制对手方（谁来保证它不缩水？）。
6. `judge()` 的 G0 只查 `per` 的**形状**，不查它是不是「跑到了产品」——
   若某天 `scan()` 返回空 dict 而形状正确，G1 / G2 会红（有 G1/G2 兜底），
   但 G4 的「不假阳」会是**空断言通行**。这是**有意的**：G4 的空转由 G1/G2/G5 正向半边堵。
7. 冒烟级：`_scan_py_defs` 的 40 行防御上限是**拍出来的**（不是量出来的）——
   超长形参表（>40 行）的行为没有被量过。
8. 本轮的**两端对照只有 1 台解释器**（系统 3.10 跑 pytest、托管 3.13 跑 CLI）：
   CLI 侧只用 3.13 量过；py / js 前端在 3.10 上的读数**没有单独测**。
9. `check_known_red.py` 的 **B 类 6 件产物**仍在登记表里（§2-10）—— 本轮无决策。

## §8 下一次建设性意见（接在 R65 §8 之后）

| 编号 | 内容 | 动因（本轮的读数） | 优先级 |
| --- | --- | --- | --- |
| **C16-1** | 给 py / js 扫描器加**字符串与注释状态机**，杀掉过度识别（docstring / 块注释里独占一行的 `def` / `function` 被当成真函数），并在新门里加一条判据钉住 | §1.5 实测 **2/6 泄漏**，基线就有、本轮未修 | **最高** |
| **C16-2** | 把「形态集合」本身变成**登记制**：py / js / c 三张形态表进仓库，加一条「表不许缩水」的棘轮（现在是硬编码常量，只在**新门**里） | §7-5 —— 「我挑的 24 个形态」没有对手方 | **最高** |
| **C16-3** | 让 `ret` 有对手方：Python 的 `-> bool` 与 JS 的 TS 注解（若将来支持）要么**真的解析**，要么在帮助里**逐字披露**「恒为 `None` / `void`」 | §2-5 —— 一个字段永远返常量却没人守 | 高 |
| **C16-4** | `collect_files` 的**排除表**：JS 侧会把 `node_modules` 走一遍（只跳隐藏目录） | §7-1 —— 真实大仓没量过 | 高 |
| **C16-5** | 给 `_scan_py_defs` / `_scan_js_defs` 补 `IR_LANG_OWNERS` 级的**登记**（现在只有 C 的 `_C_SOURCE_EXTS` 有唯一性声明） | §2-9 | 中 |
| **C16-6** | **B 类决策**（承接 C15-7，需用户拍板）：实现 `setup.py` / `analyzer_config.example.json`，还是把那 6 件永久登记为「不做」 | §2-10 —— 47 条红里 37 条挂在 `fe_audit.py` 一条上 | 高（要决策） |
| **C16-7** | `matlab` 路径的形态门（默认语言反而**没有**门） | §2-7 —— 三轮都只守 py/js/c | 中 |
| **C16-8** | `_js_heuristic_checks` 的 `js_global_var` 把任意裸 `name = …` 当全局变量 —— 需要一条形态判据 | 与本轮 D1 同源（都是「把行当成语义」） | 中 |
| **C16-9** | 「三类读数（基线 / 中间态 / 复量）必须在**文件名**里分开」写成探针目录的 `README`，并由一条门核对命名 | §5.1-3 —— 本轮真的把中间态当成了基线 | 中 |
| **C16-10** | `.workbuddy/` 仍不在 `.gitignore`（`git status` 里一直是 `??`），且**记忆文件不在任何门管辖内**（承接 C15-8） | 每一轮都要手工绕开它 | 中 |
| **C16-11** | 把「**16 道门** vs **17 个护栏脚本**」这两个**都合法**的口径写进 `CONTRIBUTING.md` 的门禁小节（现在只出现在成功行与报错文案里） | §5.1-6 —— 本轮真的混用过一次，是这道门替我分清的 | 低 |
| **C16-12** | 探针目录**收尾**纪律：每轮结束必须移除临时 `git worktree`，并加一条门核对 `git worktree list` 只剩主树 | 本轮 `git worktree list` 里躺着 **R61 / R62 两个遗留树**；R61 的已清干净，**R62 的还带着 311 行过期草稿**（`tests/test_matlabc.py` +83 / `tools/check_readme_parity.py` +235），且 `git worktree remove` **正当地拒绝**删除（不带 `--force`）—— 我没有单方面强删 | 中 |

**仍未完成的旧项**：C15-1（`check_all --measure` 选修臂）· C15-2 / C14-2（README 表行的
47 / 8 / 4 没有门的对手方）· C15-3（全量对照选修臂）· C15-4 · C15-5 · C15-6 ·
C14-11 / C15-8（记忆文件卫生门）· C13-4 / C13-5 / C13-7 / C13-8 ·
R44 §8 的 `C''''2`（`ltrace` / `strace -e openat` / `LD_DEBUG=bindings`）与
`C''''4`（`IR_LANG_OWNERS` 作为单一事实源）。

## §9 明确拒绝做的事（避免下一轮走回头路）

1. **不把「对象方法简写」和「匿名 default」偷偷认出来** —— 它们已被披露为不识别，
   而 G5 正钉着这一点。要认就先改 G5 的登记、并在两侧 README 与帮助里同步披露
   （**承诺与行为不许分叉**）。
2. **不为了让形态读数好看而把探针的形态集合改小** —— §7-5 说的就是这个诱惑。
   要动形态集合，先按 C16-2 把它变成登记制。
3. **不在这一轮顺手做「类型推断」**（让 `ret` 跟着 `-> bool` 走）：那会把
   「定义识别」的改动面扩成「类型系统」，是一个完整的独立轮次。
4. **不用「多认几个」来掩盖**：本轮所有修改都有**两向**对手方（
   「漏认会红」+「不该认的认了也会红」），没有一条是单向放行。
5. **不动 `VERSION`**（`1.16.72` 是源码常量）· **不动 `flow/diagrams`** ·
   **不引新依赖**（坚持离线、零依赖、3.6.5）· **不动行尾策略**（全 CRLF、`* -text`）。
6. **不把新门的夹具换成仓库里真实文件** —— 那会让门随产品一起漂，
   失去「独立期望」的意义（`WANT` 是**手写**的，不从任何 `tools/` 装置生成）。
7. **不跳过 G0b / N1 这两颗雷的修复**：它们**自动**响了两次，正是本轮级联
   没有漏项的原因；把它们的管辖范围改松就等于把这件事重新变回人工。
