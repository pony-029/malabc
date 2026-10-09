# SUPERPOWER_REVIEW R50 —— C 源文件扩展名：从「文档说共用」到「可证是同一张表」

> 本轮落地的是 R44 §8 C''''4 / R49 §8 C'''''9「把 `IR_LANG_OWNERS` 那一类
> **单一事实源**坐实」，边界收在 **C 源文件扩展名**。方法沿用本仓既有纪律：
> 先用**仓库外的独立装置**量影响面，再改代码，再加**反向判据**，
> 最后跑总门禁与相关家族，并**从远端 clone 回来**做对象级验证。

---

## §0 结论先行

`frontends/__init__.py` 的 docstring 一直写着 C 的扩展名「`collect_c_files` 与
`CFrontend.exts` **共用**」`matlabc.py::_C_SOURCE_EXTS`。R50 用独立装置一量：
**这句话是假的。**

| 口径 | 修前 | 修后 |
| --- | --- | --- |
| A 事实源 `_C_SOURCE_EXTS` | 8 类 | 8 类 |
| B 行为（真建目录真跑 `collect_c_files`） | 8 类，与 A 全等 | 8 类，与 A 全等 |
| C 前端声明 `CFrontend.exts` | **2 类**（缺 `.cc .cpp .cxx .hh .hpp .hxx`） | 8 类，与 A 全等 |
| `CFrontend.exts is _C_SOURCE_EXTS` | **False** | **True** |

修法只有一行（声明侧改为**引用**事实源，不复制），但它背后是一条可证伪的不变式；
本轮同时把这条不变式**做成了装置**（`check_ir_attribution.py` 的 C7'）。

---

## §1 白帽：事实清单（全部实测，可复现）

1. **装置**：`E:\matlabc\_r50\probe_ext_truth.py`（仓库外，LF，零依赖）。
   它刻意**不 import 任何 `tools/check_*`**（那就是被测对象），只 import 产品本身；
   三条口径各自独立测量：声明表 / 行为表（真在临时目录里为每个候选扩展名放一个文件、
   真调 `collect_c_files`，看它到底收了谁）/ 每个 `Frontend` 子类的 `.exts`。
2. **修前读数**（探针原始输出）：
   `A_count=8`、`B_count=8`、`EQ_behavior_vs_source=True`、
   `EQ_CFrontend_vs_source=False`、`E_CFrontend_exts_is_source=False`、
   `MISSING_in_CFrontend=[".cc",".cpp",".cxx",".hh",".hpp",".hxx"]`、
   `C_frontend_exts={"c":[".c",".h"],"js":[".js"],"matlab":[".m"],"py":[".py"]}`。
3. **修后读数**：同一探针 → `EQ_CFrontend_vs_source=True`、
   `E_CFrontend_exts_is_source=True`、`MISSING_in_CFrontend=[]`，
   而 `B`（行为）**一字未变**（8 类，仍与 A 全等）⇒ 行为保持。
4. **`.exts` 的读者**：全仓 grep（`\.exts\b`）在生产代码里**零读取点** ——
   它是一句**声明**。这恰恰是本轮的价值：声明与行为分叉时，只有行为侧有人看。
5. **同类隐患的边界**：`PyFrontend.exts=(".py",)` / `JsFrontend.exts=(".js",)` /
   `MatlabFrontend.exts=(".m",)` 与各自 `collect_files` 里内联的字符串**值相同**
   （单值、无分叉）；`BaseFrontend.exts=()`；`_C_HEADER_EXTS` 是**头文件子集**，
   经本轮断言确认 ⊆ `_C_SOURCE_EXTS`。故本轮范围**只收 C**，不为其它语言造第二事实源。
6. **既有装置的联动**：`tests/test_matlabc.py::test_r44_gate_call_sites_agree_with_return_arity`
   （「凡解包本门某函数返回值处，元组长度必须与该函数 return 一致」）**先红了一次** ——
   它如实抓住了 `scan_repo` 由 6 元组扩成 8 元组。它是对的，故本轮**同步**它的期望值。

---

## §2 黑帽：本轮抓到的问题（含一处自伤）

### 2.1 真缺陷：叙述与装置分叉（`CFrontend.exts` 2 类 vs 8 类）

- **它是什么**：一句 docstring 宣称的接线**在源码里不存在**。本仓对这类东西已有名字
  （「宣称没有装置」），但此前**没有任何装置**守着**这句话本身**。
- **为什么这是真缺陷而不是洁癖**：`exts` 是公开面（`BaseFrontend` 的类属性、
  第三方前端作者会照着抄），它**答错了「这个前端认哪些文件」**。
  一个只读 `exts` 的工具/文档，会以为 `matlabc --lang c` 不认 `.cpp`。
- **修法**：`exts = _C_SOURCE_EXTS`（同一对象，不是副本）。一行。

### 2.2 自伤：`dict(good, **{元组键: ...})` 是非法写法

新测试里我用了 `dict(good, **{("matlabc.py","Other"): ...})` —— `**` 要求字符串键，
运行时 `TypeError: keywords must be strings`。**被测试运行当场抓到**（不是 review 抓到的）。
修法：先 `copy` 再下标赋值。记在案：**「能跑」不是「写对」**。

### 2.3 未做（诚实记下）

- **判据条数仍未进棘轮**（R44 §8 C''''7 / R49 未做）：本轮 `check_ir_attribution.py`
  的静态判据由 7 → **8** 条，成功行会打印它，但**没有一条断言**阻止以后有人删掉 C7'
  而不改数字。本轮改的是**散文**（docstring / `GUARD_CONTRACT` 描述），
  这不是装置。留作下一轮候选。
- **`libc` / 真实语料上的影响面**：本轮未做大规模语料扫描 —— 因为 `exts`
  在生产代码里零读取点，影响面是**声明层**而非行为层；行为层由探针在合成目录上量。

---

## §3 黄帽 / 绿帽：收益与边界

**收益**

1. **一句话变成可证**：修前「共用」是宣称，修后是 `is` 同一对象的**事实**，
   且有 `tools/check_ir_attribution.py::C7'` 两向守着（未登记 / 陈旧登记 / 悬空引用 / 复制品）。
2. **反向判据真实存在**：把 `matlabc.py` 退回 HEAD 后，**两条新测试都红**，
   且门在真实仓库上直接打印
   `I7 matlabc.py::CFrontend 的 exts 是 literal 写法（('.c', '.h')）—— 必须是**引用**唯一的 '_C_SOURCE_EXTS'`。
3. **行为保持有证人**：探针 `B`（行为表）修前修后**一字未变**。
4. **顺手加固了返回值契约**：`scan_repo` 6 → 8 元组由既有断言守着（§1.6）。

**边界（不假装）**

- C7' 是**静态**判据：它证明「声明绑到了那张表上」，**不**证明那张表的内容是对的。
  内容正确性由 `test_r50_c_ext_truth_source_is_single` 的**行为口径**（真建目录）负责。
- 三条口径**互相独立、缺一留盲区**：只查声明会漏掉「复制成等长元组」；
  只查身份会漏掉「收集器自己改坏」；只查行为会漏掉「声明漂移恰好奇合」。
- **未引入任何新依赖 / 新门**：`MIN_GUARDS` 仍 11，散文里的「11 道护栏」**不变**
  （故本轮**不触碰** `HELP_BYTES_SNAPSHOT`，`matlabc.py` 的模块 docstring 未改）。

---

## §4 蓝帽：本轮建立的不变量

1. **C 源文件扩展名只有一个事实源**：`matlabc.py::_C_SOURCE_EXTS`；
   `collect_c_files` 与 `CFrontend.exts` 都**引用**它。
2. **引用必须是同一对象**：`CFrontend.exts is _C_SOURCE_EXTS`（副本不合格）。
3. **头文件表是源表子集**：`set(_C_HEADER_EXTS) ⊆ set(_C_SOURCE_EXTS)`。
4. **行为与声明必须同集合**：`{collect_c_files 收到的扩展名} == set(_C_SOURCE_EXTS)`。
5. **`exts` 声明只许是引用**：类级 `exts` 绑到登记的事实源名上；未登记的
   「含 C 扩展名的字面量元组」一律红（复制品没有对手方）。
6. **返回值元数契约**：解包本门返回值处，元组长度必须与 `return` 一致（既有断言，本轮 6 → 8 同步）。

---

## §5 轮次账本（R50 内）

| # | 动作 | 判据 / 产物 | 结果 |
| --- | --- | --- | --- |
| 1 | 读记忆 + R43/R44 §8 + R49 §8 | 选定 C''''4（扩展名事实源） | — |
| 2 | 独立装置量影响面 | `_r50/probe_ext_truth.py` | 声明 2 vs 事实源 8、`is` False、行为 8 |
| 3 | 改代码（6 文件 23 处锚点） | `_r50/patch_r50.py`（全或无 + ast + bare_lf） | 全部命中 |
| 4 | 加反向判据 | `tests/test_matlabc.py` 两条（`test_r50_*`） | 修前 2 failed → 修后 2 passed |
| 5 | 装置自证 | `check_ir_attribution.py --selftest` | `SELFTEST COUNTS {"bad": 0, "good": 24}` |
| 6 | 总门禁 | `tools/check_all.py` | **rc=0**，11 道护栏全部通过并各自自证 |
| 7 | 相关家族 | `pytest -k "r44 or r37 or r31 or r50"` | 16 passed / 431 deselected |
| 8 | 文档同步 | README.md / README_CN.md（§同步） | `check_readme_parity.py` 15 小节对等 |
| 9 | 提交 + 远端对象级验证 | （见 §6） | — |

---

## §6 验证矩阵

| 面 | 装置 | 判据 | 读数 |
| --- | --- | --- | --- |
| 事实源口径 | `_r50/probe_ext_truth.py` | A == B == C、`is` 为真 | 8 / 8 / 8，缺 0、`is` True |
| 行为保持 | 同探针 | 修前修后 `B` 逐项相同 | 8 类，未变 |
| 反向判据（红） | 退回 `HEAD:matlabc.py` 后跑 `-k r50` | 两条都必须红 | 2 failed；门打印 `I7 ... literal 写法` |
| 反向判据（绿） | 恢复后跑 `-k r50` | 两条都必须绿 | 2 passed |
| 门自证 | `check_ir_attribution.py --selftest` | 坏样本必红、好样本必过 | `{"bad": 0, "good": 24}` |
| 静态判据条数 | 成功行 | 8 条静态 + 10 纯函数 + 9 语言 + 4 扩展名 | 见成功行 |
| 总门禁 | `tools/check_all.py` | rc=0 且 11 道各自自证 | rc=0 |
| 家族 | `pytest -k "r44 or r37 or r31 or r50"` | 全绿 | 16 passed |
| 远端 | 从 GitHub clone 回来 | 对象级 sha256 比对 | 见提交信息 |

---

## §7 探针清单（仓库外，**不进 git**）

| 文件 | 用途 |
| --- | --- |
| `_r50/probe_ext_truth.py` | 独立装置：三条口径量「扩展名事实源」 |
| `_r50/patch_r50.py` | 6 文件 23 处锚点补丁（全或无 + ast + bare_lf） |
| `_r50/patch_r50_tests.py` | 新增两条 R50 测试 |
| `_r50/patch_r50_fix.py` | 修自伤①：`dict(**{元组键})` → copy + 下标 |
| `_r50/patch_r50_tests3.py` | 修自伤②：`scan_repo` 6 → 8 元组，同步既有 arity 断言 |

---

## §8 C'''''0–C''''' 下一次建设性意见（接在 R49 §8 之后）

排序原则不变：**优先「已有装置但没接上线」与「已有承诺但没装置」**，
每条先说清「**什么会红**」。

**C''''''0（阻塞项，沿用 R49）补 `fe_audit.py` 与 `.github/workflows/frontend-gate.yml`，
或把 7 条测试显式登记为「不做」。** `tests/` 至今有 **7 条永久红**；「守护永远是红的」
与「守护没人跑」是同一种病。对手方：登记了却其实已存在 → 红；存在却仍登记为缺失 → 也红。

**C''''''1 把本轮「三条口径」推广成一张**语言扩展名总表**。**
现在只有 C 有「引用 + 三口径」的装置，Py/JS/MATLAB 仍是内联字符串（值恰好一致）。
落点：抽 `_LANG_SOURCE_EXTS = {"c": _C_SOURCE_EXTS, "py": (".py",), ...}` 只读表，
各前端 `exts` 与各 `collect_files` 都引用它。**对手方**：任一语言的
`exts` 与行为表不等 → 红（把 C7' 从「一张表」升级为「一个字典 + 每语言一对」）。
理由是 §1.5 已量出：**值相同 ≠ 单一事实源**。

**C''''''2 让「判据条数」进棘轮（R44 C''''7 / 未做）。**
本轮静态判据 7 → 8，只写进了成功行与散文。落点：把
`check_ir_attribution.py` 的静态判据条数做成只许增的快照；删掉 C7' → 红。
**对手方**：删 C7' 必须红。

**C''''''3 `tools/check_import_graph.py`：打断 `renderers` ↔ `matlabc` 循环依赖（沿用 R44 C''''3 / R49 C'''''8）。**
现在仍靠「模块尾部 import」规避。**对手方**：人为加回边必须红；例外登记两向核对。

**C''''''4 运行期绑定边界显式化（沿用 R44 C''''2 / R49 C'''''7）。**
全仓至今无 `dlopen` / `LoadLibrary` / `dlsym` / `LD_PRELOAD`。落点：`--help` 的
「诚实的边界」逐字写上「不跟踪运行期绑定」并点名 `ltrace` / `strace -e openat` /
`LD_DEBUG=bindings`。**对手方**：`check_doc_flags` 的「逐字出现」机制扩一条断言。

**C''''''5 把 R49 的独立装置固化进仓库（沿用 R49 C'''''1）。**
`tools/check_c_frontend_shapes.py`：四种形态 + 字符串花括号 + 不假阳，秒级、纯合成夹具。

**C''''''6 让「本轮无回归」成为产物（沿用 R44 C''''6）：`baseline_report.json`。**

---

## §9 明确拒绝做的事（避免下一轮走回头路）

1. **不为「统一」而给 Py/JS/MATLAB 现造第二事实源。** 本轮 §1.5 已量出它们的值一致；
   在**没有分叉**时先建表，只会新增一处需要同步的地方（C''''''1 是**有装置**地做这件事，
   不是本轮顺手做）。
2. **不把 C7' 写成「import matlabc 再比 set」。** 那会把这道秒级静态门拖进
   「分钟级 ⇒ 没人愿意跑」的区间（R37/R44 同一条纪律）；行为口径交给 `tests/`。
3. **不用源码文本当判据。** 本轮 C7' 只认 AST 事实（`ast.Name` / 模块层赋值名），
   `exts` 的注释里写着什么**不影响判定** —— 与 C4 同一条纪律。
4. **不为让某条判据通过而放宽它。** `test_r44_gate_call_sites_agree_with_return_arity`
   红起来时，正确反应是**同步期望值并在注释里说明**，不是删掉它。
5. **本轮不碰 `flow/diagrams`**（R45–R48 已完成、暂不推进）。
