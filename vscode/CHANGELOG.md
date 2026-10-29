# 更新日志

---

## 2.2.3

- **返回值形状推断**：`out_shape_for` 原来只看 `Stmt::Op`，于是
  `A = zeros(m,n)` / `A = f(x)` / `A = 3` 这类返回值一律「推断不出形状」。
  现按来源保守推断（`fill:` 维度确定 / `set:` 标量 1x1 / `call:` 取被调函数已标注的返回形状，
  没标注仍返回 None 不猜）。YALMIP 生成物 **TODO(ret)：148 → 0**
- 修重复声明：同一名字既被 Op 当暂存量、又被 `fill:` 当目标 → 声明两次
  （gcc `redeclaration of 'temp' with no linkage`）；暂存量收集改为跳过 fill 目标
- **未修（放行后暴露）**：更多函数真正发射后出现「同名既标量又数组」
  （`x2_list` conflicting types / `sqrList` redeclared），与 R487 的 `'d'` 同类 ——
  因此 YALMIP 全工程 gcc 仍不通过，**不把「TODO 归零」当成功**
- **声明唯一化**：`f.locals` 里的名字若已是形参/返回值/暂存量/fill 目标，
  不再生成 `int64_t <name> = 0;`（`mlc_array sqrList` 与 `int64_t sqrList` 冲突）；
  标量赋值的目标**不能是形参/返回值**（否则 `df = latest_df;` 把 int64_t 赋给
  `mlc_array *`）—— 改为如实降级成 `TODO(set)` 桩。
  **YALMIP 全工程 gcc 错误 4 -> 1**
- 未修：同一个名字被**两次 fill** 时仍声明两次（`redeclaration of 'ia'`，
  这是最后一个编译错误）
- **名字「一次定型」**：生成完函数体后统一修正 —— 一个名字一旦当过数组
  （`fill:`/`call:`/`op:` 的左值），就删掉它的 `var:<n>:i64`、并把
  `set:<n>:<数字>` 改成 `const:`（const 的语义正是"把 1x1 的值写进数组"）。
  这解决了 `ia` 同时是数组和 i64 标量的冲突 —— R487/R497/R498 三轮都在
  "某个来源上加守卫"，这次改成**按名字一次定型**
- fill 的目标若已在暂存量里，不再声明/初始化（避免第二条 `mlc_array ia;`）
- **结果：YALMIP 全工程（1204 函数 / 1104 个 .c）首次 `gcc -fsyntax-only` 通过**
- **但必须同时记：干净函数数仍是 0** —— "可编译"与"有函数能算"是两条完全不同的线，
  1204 个函数体里没有一个不含 `TODO`
- **无返回值函数（"过程"）走正常生成路径**：此前一律给
  `TODO(void): 无返回值的函数本版不生成实现` 的桩。去掉这个提前返回后，
  没有 ret 就没有输出参数，末尾统一 `return MLC_OK;`
- **干净函数数：0 → 3**（`scope_demo` / `local_a` / `local_b`）——
  这是「函数体不含任何 TODO」的第一个非零值；同时
  YALMIP 全工程 `gcc -fsyntax-only` 仍通过
- 说明：剩下 10 个 void 函数里只有 3 个真正变干净，另外 7 个还有别的阻塞 ——
  **不为凑数把它们算进来**
- **新增标量算子 `OP-NUMEL` / `OP-LENGTH`**（C / 算子表 / 发射器 / 解释器四层齐）：
  `if numel(v) < 3` 此前被降成 `op:OP-INDEX:__t1:numel:v` ——
  即"对名为 `numel` 的数组取第 v 个元素"，**能生成、能编译、结果全错**
  （与 R483 的 `isempty` 同一类误判）。语料增至 **24 个**（`countel: 4`）
- **YALMIP 的 `TODO(arg)` 4 → 2**；但干净函数数**仍是 3** ——
  析出的问题跑到下一层（`TODO(call)` 12 → 15：`numel`/`length` 被同工程同名函数遮蔽），
  **不拿"某一类 TODO 下降"当进展**
- YALMIP 全工程 `gcc -fsyntax-only` 仍通过；17 道门全绿
- **调用解析优先级：算子优先于同工程同名 `.m`**（上一轮第 1 项）。
  `find(x,2)` / `numel(v)` / `length(v)` 这些**内置**调用此前被解析成"调用同工程的
  `find.m`"，而算子签名是 1 个参数 -> `TODO(call): 参数个数不符`。
  现在顺序改为：算子表能认 -> 算子；否则同工程函数 -> `call:`；否则才是下标。
  YALMIP：算子语句 3525 → **3786**（+261），`TODO(call)` 15 → **12**
- 净效果如实记：**干净函数数仍是 3**，`TODO(shape)` 6 → 8（问题又下移了一层）
- 未做（时间不足，不半途实现）：让形状未知的返回值由**算子按结果形状运行时分配**
  ——这是打破 `TODO(ret)` 121 的唯一结构性办法，需要动 `mlc_binary_f64` 与发射器的
  ret 初始化；本轮只做了调研与方案
- **突破：形状未标注的返回值，由算子按结果形状「运行时分配」**
  1) C：`mlc_binary_f64` 在**输出为空**（numel 0）时，按广播结论就地 `init`
  2) 发射器：`ret` 形状推不出时不再整函数放弃，而是置空（`{0}`）继续发射
  3) **收窄**到四则运算（`OP-ADD/SUB/MUL/DIV`）—— 只有它们实现了"空输出自动分配"，
     否则会出现 `incompatible type` 编译错误（第一版放得太宽，当场被 gcc 拦住）
  - 结果：**干净函数 3 → 7**（其中 4 个靠运行时定形状）；`TODO(ret)` 121 → 111
- **诚实边界（必须一起读）**：这 4 个函数**未做运行期数值验证** ——
  生成的驱动对"无形状返回值"直接 `skipped (no shape)`，我试着加语料用例
  （`dynshape.m`：只标注 x 不标注 y）结果被驱动跳过，于是把用例**移除**了。
  因此本轮只能声称"编译通过且不含 TODO"，**不能声称"算得对"**。
- **运行时定形状闭环打通，并用真实数值验证**（上一轮欠的那步）
  1) `ret_is_dynamic` 认得「形状未标注 + 四则运算赋值」的返回值 ——
     否则驱动判 `skipped (no shape)`，这条路径**永远无法验证**
  2) 动态返回值分两种，不能一律跳过初始化：
     · alloc 型（`OP-MASK`/`OP-FIND`）算子自己 malloc，不预初始化
     · 四则运算型必须 `mlc_array_init(y, MLC_F64, 1, {0})`，否则 `numel` 读到垃圾
  3) 语料新增 `dynshape.m`（**只标注 x、不标注 y**）：`y = x + x`
     → 实测 **`dynshape: 2 4 6`**，由 Octave 真值确认并写回 `numeric.expected`
  - 语料 24 → **25**，25/25 与 Octave 一致；17 道门全绿
  - YALMIP：`gcc` 通过，干净函数 **7/1204**
- **「运行时定形状」从四则运算推广到归约与转置**（上一轮第 1 项）：
  · 归约（`sum`/`max`/`min`）：算子内部在输出为空时先按 1x1 分配
    —— 它们原本先取 `out->data`，空输出直接 `MLC_ERR`
  · 转置：按输入形状反转后补分配
  · 发射器：`ret_is_dynamic` / `dyn_ok` 的算子族同步扩展
- **两个用例都以真实数值验证**（只标注 `x`、故意不标注 `y`）：
  `dynshape: 2 4 6`（`y = x + x`）、`dynsum: 10`（`y = sum(x)`）
  → 语料 25 → **26**，26/26 与 Octave 一致；17 道门全绿
- 如实记：YALMIP 干净函数 **仍是 7**（归约/转置这条路在那边没有增量收益）
- **驱动支持「无形状注解」的函数**（上一轮第 1 项的前置）：
  YALMIP 全线没有 `% @m2c shape`，于是 161 个可转函数里能被驱动的几乎为 0，
  7 个干净函数也全不可驱动 —— **没有驱动就没有任何真实验证**。
  现在数组入参没有注解时按**默认形状 [4]** 驱动，并在输出里显式打印
  `k: assumed shape [4]`（不假装那是注解）
- **因此第一次真正跑到了那 7 个「干净」函数**：`leaf_fn` / `level1` /
  `helper_one` / `helper_two` 全部返回 `error`（MLC_ERR）
- **由此发现一个更根本的缺口**：`leaf_fn` 的 `v = 2*k` 失败 ——
  **标量×数组的广播**在二元算子路径上不成立（`__k1` 是 1x1，`k` 是 4x1）。
  这比"再多补几个语法"重要得多：`y = 2*x` 是 MATLAB 里最常见的写法之一。
- 状态：17 道门全绿；语料 26/26；YALMIP `gcc` 通过
- **本轮实测（无代码改动，只有结论）**：把「无注解入参」放开之后，
  YALMIP 生成物能跑完 1216 行输出，其中
  **数值行 0 条、`error` 5 条、其余全是 `skipped (reject:…)`** ——
  也就是说**没有任何一个函数真正产出过数值**。
- 已排除一个嫌疑：手写微测试直接调运行时（4x1 乘 1x1、输出为空）
  得到 `mul rc=0 / numel=4 / 2 4 6 8` —— **`mlc_op_mul` 与广播本身是对的**，
  问题在生成代码或驱动侧，尚未定位（下一个待查点）。
- 这条结论比任何计数都重要：**"能编译 + 不含 TODO"与"能算出数"之间，
  目前隔着整个可执行验证链**。
- **突破：YALMIP 里第一次有函数真正算出数值**
  ```
  leaf_fn:     2 4 6 8
  helper_one:  2 3 4 5
  helper_two:  2 4 6 8
  ```
  `error` 行数 5 → **0**。其中 `leaf_fn` 已用 Octave 交叉核对：
  Octave 同样是 `2 4 6 8`。
- **根因是驱动的一个参数错误**（与运行时、与生成代码都无关）：
  `mlc_array_init(&k, MLC_F64, **0**, {4})` —— ndim 取的是 `arr.shape.len()`
  （无注解时为空 → 0），而不是实际 `dims` 的长度。
  ndim=0 时 numel=0、`data=NULL`，于是**任何**调用都立刻 `MLC_ERR`。
  这也是上一轮"可驱动之后 0 个函数产出数值"的真因 ——
  当时我先怀疑广播，写了微测试才排除，最后定位到驱动这一行。
- 顺带修：`assumed shape` 的打印被推到了代码块外面（顺序错）
- **把「零注解」这条链上锁**（上一轮第 1 项）：新增
  `translate/examples/nouns/scale2x.m`（**不带任何 shape 注解**）与
  `tests/test_nounshaped.py`：断言驱动打印 `k: assumed shape [4]`，
  且数值为 `scale2x: 2 4 6 8`
  - **两向验证**：把驱动里 `dims.len()` 改回 `arr.shape.len()`（上轮的真 bug）
    → `1 failed`；还原 → `1 passed`
  - 同时接进 GX1（编译）与 GX2（运行），**发版时会自动跑**
- **YALMIP 可执行读数（第一次有意义的数字）**：1216 行输出里
  **有数值 3 个函数**（`leaf_fn` / `helper_one` / `helper_two`），`error` 0 个，
  其余仍是 `skipped (reject:…)`
  —— 这才是"真正可用的函数数"，比"干净 7 个"低，但它是**跑出来的**
- **新增 `tools/runnable_report.py`**（上一轮第 1 项）：端到端「可执行读数」
  转换 → 生成 → 编译 → 跑 → 按 **numeric / error / skipped_reject / skipped_shape**
  分类。此前这个数字靠手敲 PowerShell 过滤，**不可复现**
- **第一次拿到可复现的 YALMIP 读数**：

  | 类别 | 数量 | 含义 |
  |---|---|---|
  | **numeric** | **3** | 真正算出数值（唯一可用） |
  | error | 0 | 跑起来但失败 |
  | skipped_reject | 1043 | 整函数被拒（struct/cell/varargin） |
  | **skipped_shape** | **149** | 可转但不可驱动（返回值形状未知且不可动态推断） |

  即：下一个可攻的群体是这 **149** 个 —— 它们不是被 struct 挡住，而是"形状"挡住
- 工具自证 5 项；两处自伤 bug 当场修掉（`--selftest` 被参数校验拦截；
  清理逻辑一度会 `rmtree` **临时根目录**，被沙箱拦住后改为只删本次工作目录）
- **可执行读数第一次「账平」**：`numeric 3 + unimplemented 37 + error 0 +
  skipped_shape 121 + skipped_reject 1043 = 1204`（= 函数总数）
  - 修了两处口径错误：
    1) `runnable_report` **漏统计 `unimplemented`**（77 行从总数里悄悄消失，
       导致上一轮"可驱动 1167"这个分母是错的）
    2) `drivable()` 只看 MIR 里 `ret:` 声明的形状，而发射器**能**从
       `fill:`/`call:` 推断 —— 两者对齐后 `skipped_shape` 149 → 121
  - 顺带修驱动撞名：循环变量 `i` 与入参名 `i` 冲突（YALMIP 有 `function ...(i)`），
    改为 `m2c_ii`
- 如实记：**numeric 仍是 3** —— 放宽可驱动面没有直接变成"能算的数"
- **P0 预览版收尾**：`docs/RELEASE_PLAN.md` 与 `docs/KNOWN_LIMITS.md` 已链进
  中英两份 README 的「文档」小节（`check_readme_parity` 仍 OK）——
  文档不入索引 = 发布物找不到，等于没发
- **负结果（试验后回退，如实记）**：让 `TODO(shape)` 也走 dynshape
  （把"形状推不出的暂存量"置空后由算子分配）——
  实测 `unimplemented 37 → 33`，但 `error 0 → 4`，**numeric 仍是 3**。
  即：拿"如实拒绝（桩）"换成了"运行期 MLC_ERR"，没有收益，**已整体回退**，
  当前读数仍是 3 / 37 / 0 / 0 / 1043 / 121 = 1204。
  原因：这些暂存量往往要**作为输入**喂给下游算子，置空后下游拿到的是空数组，
  而不是"结果形状"—— dynshape 只对"直接被算子写满的输出"成立。
- **`v1.0.0-preview` 基线已钉住**（`docs/RELEASE_PLAN.md` 第八节 + 同名 git tag）：
  基线 commit、日期、R1–R6 现状、四条验证命令，以及一条自检
  ```bash
  python tools/check_all.py && python tools/runnable_report.py translate/examples/numeric
  ```
  两条都过 = 环境与本文数字可对齐；任一失败 = 先解决环境
- 明确写出这个预览版**承诺什么 / 不承诺什么**（不承诺：无注解形状推断、
  struct/cell/varargin、与 MATLAB 逐位一致）
- **`out_shape_for` 补认 `Stmt::Const`**（`d = 1` 这类：写的就是一个 1x1 值）：
  YALMIP 里有 18 处返回值是这么写的，此前一律判"形状推不出"。
  读数变化：`skipped_shape 121 → 111`、`unimplemented 37 → 47`、`error 0 → 0`、
  **`numeric 3 → 3`**。
  如实定性：这是**账目细化**（10 个函数从"不可驱动"挪进"可驱动但仍是桩"），
  **不是能力提升** —— 生成物一个字节没变，变的只是驱动愿不愿意调它们。
  之所以保留：`error` 没涨（与上一轮整类放宽不同），且桩里的 TODO 现在逐函数可见。
- 做法上的改变：不再"整类放宽"，改为**按"这个名字是怎么写出来的"逐个**处理
  （`const 18 / call2 32 / fill 11 / set 10 / OP-SETIDX 14 / 无写入 71`）
- **按"读一个具体函数"定位真阻塞**（方法改变：不再看聚合统计）。
  桩的分布：`call 11 / shape 12 / ret 9 / set 8 / arg 5 / call2 4 / if 3 / unmapped 1`。
  逐个读 `call` 类后发现：**它们全是内置库函数被同名 `.m` 遮蔽**——
  `size`(未映射 893 + 110 处调用) / `length` 254 / `reshape` 192 / `zeros` 225 / `find` 853。
  这才是"函数体是桩"的主因，而不是形状。
- **尝试新增 `OP-SIZE`（`size(A,2)` → 1x1）—— 未完成，已整体回退**。
  卡在两处发射器硬编码（都是"新增一个算子就要同步改的清单"）：
  1) 已知算子白名单（第 15 行）—— 漏了报 `OP-SIZE: 未知算子`
  2) 算子 → C 函数名映射（生成 `mlc_op_size` 而不是表里写的 `mlc_op_size_dim`）
  3) **字面量参数**（`size(A, 2)` 的 `2`）被当成变量名，生成 `_2` → 编译失败
  结论：加一个"带字面量参数的算子"不是四层改动，是**五层**（含参数降级为 `const:` 临时量）。
  下一轮应先做这个"字面量参数"通道，再重做 OP-SIZE。
- **`OP-SIZE` 落地**：`y = size(x, 2)` 端到端可用（语料 26 → **27**，实测 `ncols: 3`）。
  这是上一轮回退的那一项，这次把**五处**一次改全：
  1) C 实现 `mlc_op_size_dim(a, dim, out)`（结果恒 1x1）
  2) `translate/operators.py`：条目 + `_SIZE_LINE` 正则 + `C_IMPLEMENTED`
  3) 发射器 `C_IMPLEMENTED` 白名单（漏了会报 `OP-SIZE: 未知算子`）
  4) 发射器标量形状分支（漏了会出现 `WARN(shape)` 并按输入形状执行）
  5) 发射器专用分支：**字面量维度**照抄 `OP-INDEX` 的 `(int64_t){}` 写法
     —— 这一条是上轮失败的真因：通用 1 参路径会把 `2` 当成变量名生成 `_2`
- YALMIP 读数：算子语句 3786 → **3849**（+63），但
  `numeric 3 / 桩 47 / error 0 / 形状 111` **未变** —— 那些函数还有别的阻塞，
  不把"多了一个算子"当交付
- **`call2:` 传递性**：返回值由多返回调用写入时，若被调方对应返回也没形状，
  说明它会在运行期分配 —— 本函数因此也可以只置空。
  读数：`skipped_shape 111 → 103`、`unimplemented 47 → 55`、`error 0 → 0`、
  **`numeric 3 → 3`**。与 `const:`、`drivable` 两轮一样，是**账目细化**。
- **判断（写下来避免再走）**：这条杠杆已到头。连续三轮（`drivable` / `const` /
  `call2`）都只把函数从"不可驱动"挪到"可驱动但仍是桩"，`numeric` 一动不动。
  剩下的形状缺口里最大的一类是**分支赋值 71 处** —— 它不是工具不够强，
  而是**信息不在源码里**（`if/else` 各赋一次，静态拿不到唯一形状）。
  下一步该做的是**分支形状合并**或**注解引导**，而不是继续放宽判定。
- **先验证再动手，推翻了自己的计划**：上一轮判定"分支赋值 71 处"该做**分支形状合并**。
  动手前花 3 分钟核对，发现真因不是分支 ——
  那些返回值**根本没有写入语句**，因为赋值本身就没被映射：
  `properties = setfield(...)` / `tbasis = spalloc(...)` / `t basis = [A B]`（拼接）。
  ⇒ **分支合并会白做**，未开工即放弃。
- **让未映射语句始终可见**（本轮实际改动）：`/* unmapped: ... */` 此前只在
  "返回值形状失败"那条分支打印；返回值一旦走 dynshape，注释就消失，
  桩函数看起来像"只差一条形状"，掩盖真实原因。现在固定列在函数头。
  实测 `assertProperty` 的 C 头部直接显示
  `unmapped: properties = setfield(properties,checkfor,default);` —— 真因一目了然。
- 语料/读数：`numeric 3`、语料 27/27、官方全检 rc=0（本轮不动能力，只修可观测性）
- **按「真因」重新分类桩（1197 个含 UNIMPLEMENTED，其中非 reject 的 55 个）**：
  只有 **18 个**带 `unmapped` 记录，其余失败于形状/调用 —— **没有单一可修的大类**。
  这 18 个的形态是 `isa` / `try` / `for i=1:size(A,2)` / `spalloc` / `[A B]` 拼接，
  彼此不成簇。
- **更正上一轮的一个错误结论**：`docs/KNOWN_LIMITS.md` 3.1 原写"无写入 71 处 = 分支赋值"，
  核对样本后改为：**赋值语句本身未被映射**（`setfield`/`spalloc`/拼接），
  "形状推不出"只是**症状**。这正是本轮把 `/* unmapped: */` 移到函数头的原因。
- README 两份补 `OPERATOR_CHECKLIST.md` 链接（`check_readme_parity` OK）
- **`shape_suggest.py` 修正两处**（上一轮第 2 项）：
  1) 把 `reject` 判定抽成 `mir.reject_reason(f, srcfile)`，**唯一实现**，
     主流程与建议器共用 —— 否则四条规则又要写两遍
  2) 建议器**跳过被拒函数**：此前报"1807 个函数需要注解"，其中 1799 个是
     varargin/@方法/cell/struct，**一条也用不上**
- **这个工具的上限（本轮结论）**：过滤后剩 **192** 个真正需要注解的函数，
  但只有 **9 个**能靠函数体推出全部参数形状。
  原因不是启发式太少：**入参形状本来就不由函数体决定，而由调用方决定。**
  ⇒ 想把"带注解子集"做大，靠的不是更强的猜测器，而是
  **③ 语料/示例自带注解**（已在做：27 个用例全带注解）
  或 **④ 过程间推断**（按调用点汇总实参形状，工程量大）。
- 官方 check_all rc=0；语料 27/27；`numeric` 不变（本轮不动转换能力）
- **新增 `docs/FEATURE_MATRIX.md`**（上一轮第 2 项）：**20 条支持 + 10 条不支持**，
  每一条都挂**语料证据文件**与验证命令。例：
  `行切片 A(i,:)` → `numeric/row1.m`；`while 条件每轮重算` → `numeric/while2d.m`；
  `返回值不写形状注解` → `numeric/dynshape.m`。
  不支持项同时写明**为什么**（struct 需类型系统 / `global` 忽略会静默算错 / 拼接未做）
- **README 两份补「定位」**（上一轮第 1 项，P0 最后一件）：
  「转换**带形状注解的数值型 MATLAB 子集**，逐函数对应 C99，Octave 真值逐例核对（27/27）；
  **不**试图覆盖任意 MATLAB」，并链到 FEATURE_MATRIX / KNOWN_LIMITS。
  `check_readme_parity` 仍 OK；已核实 `[TP7] 27 个函数与 Octave 一致`
- 官方 check_all rc=0
- **解释器支持 `call2:`**（上一轮第 2 项）：多返回此前只有 C 侧验证。
  现在 `examples/multi` 的 **PA1 = 2 / PA2 = 0** —— 参考实现与生成的 C 都算过且一致。
  并加回归锁 `tests/test_multi_return.py::test_multi_return_is_parity_checked`
  （断言 `PA1 已对拍 2` 与 `PA2 未对拍 0`），否则这条覆盖会悄悄退化。
- **拼接 `[a b]` / `[a;b]`：评估后决定不做（架构性原因）**。
  实测 136 条在 52 个非被拒函数里，量足够大；但**语义依赖行/列方向**：
  `[a b]` 对行向量是横向拼接、对列向量是纵向，而本项目的 1-D 表示
  **已经丢掉了行/列区别**（`[n]` 既有可能是 1×n 也可能是 n×1）。
  在这种情况下实现拼接会**静默算错**，比"不支持"危险 —— 故不做，
  并记入 `KNOWN_LIMITS`（需要先解决行/列表示，才谈拼接）。
- 官方 check_all rc=0；语料 27/27
- **新增 `OP-COL`：`y = A(:, k)`**（与已有 `OP-ROW` 对称，五处流程 + 解释器）。
  语料 27 → **28**（`numeric/col1.m`：`A(:,2)`，实测 `col1: 2 5` 与 Octave 一致）。
  形状由入参第 1 维静态推出；入参无注解仍如实拒绝，不猜。
- 过程中依次踩到两处（都是"清单不全"，与 `OPERATOR_CHECKLIST.md` 记的一致）：
  1) 算子表 `rules` 为空元组 → 门报 `OP-COL 缺字段 rules`（要与 `OP-ROW` 一样写 `("IDX-1",)`）
  2) 发射器白名单/专用分支（字面量下标）必须同时加，否则 `_2 undeclared`
- 官方 check_all rc=0；`[TP7] 28 个函数与 Octave 一致`
- **`OP-COLRANGE`（`A(:,2:end)`）：实现完成、被门判出算错，整体回退**
  - 目标来自实测：非被拒函数里 `A(:, 字面量:end)` **8 处**（`A(:,2:end)` 是常见写法）
  - 实现到端到端（含 `end` → `-1` 哨兵、空输出按 `[rows,k]` 运行时分配），
    但 `numeric_expected` 对拍直接给出差异：
    **Octave `tailcols: 2 3 5 6` vs 我们 `2 3 3 4`**
  - 已 `git checkout` 回退（语料回到 28/28）。**没有留下一个"看着能跑"的错算子**
  - 下一步的定位线索：`OP-COL`（单列）与 Octave 一致、`mmul`（2-D 输出）也与真值一致，
    所以问题更像**我的区间循环里对 `strides[1]` / 输出排布的处理**，而不是 2-D 表示本身
- **用微测试定位 2-D 索引语义**（上一轮第 2 项的做法）：
  `mlc_array_init(f64, 2, {2,3})` 实测得到 **`strides=[3,1]`（行主序）**。
- **由此发现并修掉 `mlc_op_col` 的索引 bug**：原实现写 `i + (j-1)*strides[1]`，
  把 `strides[1]`（行内步长）当成列跨度；行主序下正确写法是
  `i*strides[0] + (j-1)*strides[1]`。
  微测试：`col(A,2)` 从 **`2 3`**（错）→ **`2 5`**（与 MATLAB 一致）。
- 如实记：语料 `col1` 在修复前后都是 `2 5`（`[TP7] 28/28` 不变）——
  说明**语料没有覆盖到这条错路径**。这本身是个缺口：`numeric` 里没有
  「行主序填充 + 取中间列」的组合，下一轮应补一条**单元级**断言
  （直接调 `mlc_op_col`，不经驱动）。
- 官方 check_all rc=0
- **`strides` 全量审查**（上一轮第 3 项）：`mlc_ops.c` 里 18 处 `strides[...]` 用法，
  只有 `mlc_op_col` 一处是错的；`row`/`slice`/`flatten`/`transpose`/`matmul` 都用了
  正确的 `i*strides[0] + j*strides[1]`。
- **新增 `tests/test_op_indexing_unit.py`**（第 1 项）：**单元级**断言，直接调 C 算子、
  不经驱动、用**行列不相等**的 2×3。判据统计：`col2 2 5`、`row2 4 5 6`。
  （端到端对拍曾让带 bug 的 `mlc_op_col` 通过 28/28 —— 因为方阵下错公式与对公式同解。）
- **`OP-COLRANGE` 重做成功**（第 2 项）：`y = A(:,2:end)`
  上次失败就是抄了错公式；改用 `i*strides[0] + (lo-1+j)*strides[1]` 后
  实测 **`tailcols: 2 3 5 6`**，与 Octave 完全一致。语料 28 → **29**（`[TP7] 29/29`）。
  附带：`is_int_literal` 允许前导负号（`-1` 是 `end` 的哨兵）。
- 官方 check_all rc=0
- **逐元素标量函数（`sqrt`/`abs`/`exp`/`log`）：实现完成、被两道门拦下，整体回退**
  - 动机来自实测：这 4 个此前都被解析成 **`OP-INDEX`**（"对名为 sqrt 的数组取下标"），
    与 R483 的 `isempty`、R501 的 `numel` 是同一类**静默误判**
  - 端到端已跑通：`rootabs: 1 1.414213562 1.732050808`（= √[1,2,3]）
  - 但两道门给出必须先解决的两件事：
    1) **TP5 自证过时**：`selftest` 里仍断言 "sqrt(x) 应如实进 unmapped" ——
       现在它成了算子，自证需要同步改（说明**新算子会与旧自证冲突**）
    2) **TP7 打印精度**：`1.4142135623730951`（Octave）vs `1.414213562`（我们）
       —— 数值相同，**驱动打印精度不足**；此前语料全是整数，从未暴露
  - 已整体回退（语料回到 29/29）。**没有留下一个"看着对但比不过真值"的算子**
  - 另外否决：`A(lo:hi, :)` 行区间 → 非被拒函数里仅 3 处且都是 `1:end-1` 这类表达式界，收益过低
- **逐元素族 4 → 12 个**（上一轮第 1 项）：新增
  `sin` / `cos` / `tan` / `floor` / `ceil` / `round` / `log2` / `log10`。
  共用 `mlc_unary_f64(a, out, code)`（形状必须与输入一致，不广播）；
  算子表自带 `rules`（上一轮被门拦过一次，这轮一次写对）。
  语料 30 → **31**（`trigfns`：`a = sin(x); y = floor(a*10);`，链式中间量也通过）。
- 顺带说明：`distsq`（`sqrt(abs(x)+1)`）**现在能过**的原因不是形状链有 bug，
  而是上一轮写成 `abs(x) + 1` 的**字面量加法走的是 `const:` 临时量**；
  本轮 `trigfns` 用 `a*10` 同样形态、通过 —— 说明二元兜底的 `bcast_shape` 是对的。
- 官方 check_all rc=0 ｜ `[TP7] 31/31 与 Octave 一致`
- **`cond`（118 条，条件右侧是调用）尝试失败并回退**：
  `_IF_RE` / `_WHILE_RE` 的右侧原先只允许裸名，把 `if size(A,1)~=size(A,2)` 挡住。
  放宽成 `name(...)` 后 —— `while_acc` / `while2d` **立刻退化成桩**
  （TP7 报 `while2d: 6` vs `unimplemented`），已 `git checkout` 回退，32/32 恢复。
  **结论**：`if` 与 `while` 共用同一份条件语法，改一处会同时影响循环条件；
  要做得先把两者的解析分开（或给 while 单独一组用例先压住）。
- 顺带记录：两参 `max/min` 经实测在**非被拒函数里 0 处**，不予实现（不做无收益的算子）。
- **给 `while` 补用例时，语料当场抓到一个真 bug**（比用例本身更值钱）：
  ```matlab
  y = y * i;        % y 是 1x1 返回值，i 是循环变量（i64）
  →  op:OP-MATMUL:y:y:i     ← 误升级成矩阵乘
  →  C: passing argument 2 of 'mlc_op_matmul' makes pointer from integer
  ```
  **`*` 升级成 `OP-MATMUL` 的条件没有排除标量** —— 而 MATLAB 里标量乘法永远是元素级。
  影响面：任何 `y = y * i` / `y = i * y` 的循环累乘都会产出**不可编译**的 C。
  本轮尝试在「形状已知后升级」那处加 `i64` 判据，**未生效**（真正的判定点不在该层），
  故连用例一起回退，语料回到 32/32。**这个 bug 已定位到 MIR 输出形态，下一轮直接查生成端。**
- `while` 的保护仍然薄（2 个用例）。加第 3 个（`while i < 4` 累乘）会撞上上面这个 bug，
  所以在修好它之前**无法**增加这层保护 —— 顺序应为「先修 bug，再加用例」。
- **`*` 误升 `OP-MATMUL` 的根因彻底定位（探针实测）**：
  ```
  [probe] oid='OP-MATMUL' code='y = y * i;' args=['y','i']
  ```
  即 `operators.parse_line("y = y * i;")` **在文本层就直接给了 `OP-MATMUL`** ——
  代码里"形状已知后再升级"的那段**从未参与**（这也是上轮补丁无效的原因）。
- **还缺一环**：把 `oid` 降级成 `OP-MUL` 后仍不行 —— `i` 是 **i64 变量**，
  而 `mlc_op_mul` 要 `const mlc_array *`。所以还需要一条
  **「标量变量 → 1×1 数组」的桥**（字面量走 `const:` 已有，变量没有）。
  两处一起改才算修好；本轮只做到第一步，**已整体回退**（语料 32/32）。
- 记下顺序：**先做标量桥 → 再降级 MATMUL → 再加 `whilelt` 用例**。
- **「标量变量 → 1×1 数组」桥落地**（上一轮第 1 项）：二元算子里若某一侧是
  i64 **变量**，先包一个 1×1 `mlc_array` 再传（字面量走 `const:` 已有，变量这条一直缺）。
- **`*` 误升 `OP-MATMUML` 修好**（第 2 项）：`*` 在文本层就是 `OP-MATMUL`；
  用 `scalar_names`（本文件已维护的标量集合）判一侧为标量时降级成 `OP-MUL`。
  —— 上一轮用 `f["types"]` 判失败，因为探针显示它是空 dict。
- **`whilelt` 用例落地**（第 3 项）：`while i < 4` 每轮重算累乘
  `y = y * i` —— 实测 **`whilelt: 6`**（1×2×3），语料 32 → **33**（TP7 33/33）。
  这条用例同时压住：循环条件语法、标量变量乘法、`while` 多轮重算。
- 官方 check_all rc=0
- **`cond`（118 条）向目标推进了两步，但第三步未完成，整体回退**：
  1) **只放宽 `_IF_RE`**（`while` 保持严格）—— 现在 `if size(A,1)~=size(A,2)` 能匹配；
     上一轮两处一起改才导致 `while` 退化
  2) **`_cond_side` 先问算子表** —— 它的原实现只处理取下标，遇到 `size(A,1)` 直接返回 None；
     现在会降成临时量：`op:OP-SIZE:__c1:A:1` + `op:OP-SIZE:__c2:A:2` + `if:__c1:ne:__c2`
  3) **但 C 侧算错**：Octave `condsize: 1`（2≠3），我们 `0`
     —— 条件比较拿到的是 **f64 数组**，而 if 的比较路径期望 **i64 标量**。
     已 `git checkout` 回退（语料 33/33）。
  **下一轮只差这一环**：给条件加「1×1 数组 → i64 标量」的取用（`.data[0]`）或让 if 支持 f64 比较。
- 另记：本轮我的补丁脚本连续两次因为**锚点文本猜错**而 assert 失败（`_IF_RE` 那两行），
  最后改用「按行号替换 + 先打印原始 repr」才成功 —— 猜文本不如读文本。
- **`cond`：把上一轮"只差一环"的那一环查清了 —— 不是类型问题**。
  重放两步（只放宽 `_IF_RE` + `_cond_side` 先问算子表）后，MIR 完全正确：
  ```
  op:OP-SIZE:__c1:A:1
  op:OP-SIZE:__c2:A:2
  if:__c1:ne:__c2
  const:y:1          ← 体在 MIR 里
  end
  ```
  生成的 C 条件也对：`if (((const double *)__c1.data)[0] != ((const double *)__c2.data)[0])`
  —— `value_expr` **本来就支持 1×1 数组**（读 `.data[0]`）。
  **但 `if` 体是空的，`const:y:1` 整条消失**（连 `y=1` 的赋值都没有），所以 `condsize: 0`。
  ⇒ 真卡点在**块体收集**（含两条新算子的 `if` 体被吞），不是比较语义。
  已整体回退（语料 33/33）。下一轮直接查 mir.rs 的 `if` 块解析 / mir.py 的 `blocks` 栈。
- 发布口径复核（本轮实测）：`numeric 3` ｜ `桩 55` ｜ `error 0` ｜ `形状 103` ｜ `拒绝 1043`
- **`cond` 的真正根因定位到一行（用手写 MIR 隔离证明）**：
  `rust/m2c/src/emit.rs:940-941`
  ```rust
  // const / fill 的值在函数开头就填好了，这里不再产出语句
  Stmt::Const { .. } | Stmt::Fill { .. } => {}
  ```
  `const:` / `fill:` 被**提升到函数序言**（hoist），语句位置一律丢弃。
  于是 `if` 体内的 `const:y:1` 整条消失 —— 与条件比较、与类型都无关。
  手写最小 MIR（`if:__c1:ne:__c2` + 体内 `const:y:1`）**同样丢体**，排除了 mir.py 一侧。
  正确修法：语句位置的 `Const` 要**真的发射赋值**（序言照旧保留默认值），
  但会改变生成物文本 → 需同时核对 TP5 的「源码行注释条数」等文本类判据。
  **本轮只做定位，未改代码**（时间不足以保证不改坏文本类判据）。
- 发布口径复核：`numeric 3` ｜ 桩 55 ｜ `error 0` ｜ 形状 103 ｜ 拒绝 1043 ｜ 语料 33/33
- **`cond` 修复已验证成功，但被 TP5 金文本挡住，整体回退（第四次）**：
  改动 = `emit.rs` 的 `Stmt::Const` 在**嵌套块内**真的发射赋值（顶层仍由序言负责，
  逐字节不变），索引是「同名 `const:` 出现多次」= 条件性重新赋值。
  实测：
  ```
  condsize: 1          ← 与 Octave 一致（size(A,1)=2 ≠ size(A,2)=3）
  [TP7] 数值语料：34/34 与 Octave 真值一致
  ```
  但 `check_all` 红在 `check_translate_port` 的 **TP5 金文本**（`demo_port` 夹具输出）——
  因为那几份期望文件编码的是**旧（错误）行为**：条件分支里的赋值此前被丢弃。
  TP5 **没有 `--update` 开关**，只能手工重录，时间不足 → 已 `git checkout` 回退（33/33）。
  **下一轮顺序**：先给 TP5 加“重录”能力（或手工更新三份 `*.expected`），再合入此修复。
- 这条修复的价值：`cond`（非被拒函数 118 条）+ 所有“分支里赋常量”的形态，
  是 numeric 从 3 往上走的直接路径之一。
- **给 TP5 金文本加 `--update` 重录通道**（上一轮第 1 项，已合入）：
  `python tools/check_translate_port.py --update` 重录 `demo_port.expected*`，
  并把每份的 **diff 打到屏幕上**（不静默改写）。
  这是上一轮把 cond 修复挡回去的那个缺口 —— 现在有了。
- **大规模测试当场抓到回归，修复因此仍不能合入**：
  合入 R548 的 cond 修复后跑 TP5，`pickbig` 从
  `pickbig: 2 / 30 / 6`（三种输入）退化为 **`pickbig: unimplemented`**。
  也就是说：让「嵌套块内的 `const` 真的发射赋值」这件事，
  与 `pickbig` 现有的 if 体语义**冲突**（它大概依赖旧行为或撞上了别的东西）。
  ⇒ 金文本已按备份还原、代码回退，语料 33/33 恢复。
  **下一轮先查 `pickbig`**：它是这个修复唯一的反例，也是唯一的线索。
- 顺带记：`--update` 第一次运行就证明了它的价值 —— 它把
  「期望 'pickbig: 2' -> 实得 'pickbig: unimplemented'」直接打了出来；
  若没有这行 diff，我会以为修复"通过了"。
- **`pickbig` 回归的根因找到并修好**（上一轮第 1 项）：**正则把数字排除了**。
  我为「允许条件右侧是调用」写成
  ```
  (?P<rhs>[A-Za-z_]\w*(?:\([^()]*\))?)$     ← 首字符必须是字母/下划线
  ```
  而原类是 `[A-Za-z_\w]+`（`\w` **含数字**）。于是 `if i > 1` 里的 `1` 不匹配 →
  整条条件退化为 `unmapped`，`pickbig` 变成桩。
  这解释了为什么"放宽"反而弄坏了东西：它同时**收窄**了字面量分支。
  修法：`[A-Za-z_\w]+(?:\([^()]*\))?`（保留原类，只追加可选的调用部分）。
- **`cond` 全套修复终于合入**：
  1) `_IF_RE` 右侧允许 `name(...)`（`while` 保持严格）
  2) `_cond_side` 先问算子表（`size(A,1)` 降成 `OP-SIZE` 临时量）
  3) `emit.rs`：嵌套块内的 `const:` 真的发射赋值（顶层仍由序言负责，逐字节不变）
  实测：`condsize: 1`（`size(A,1)=2 ≠ size(A,2)=3`）｜语料 33 → **34**（TP7 34/34）
  ｜TP5 三组金文本 + 批量夹具全部一致 ｜官方 `check_all` **rc=0**
- 过程记录：上一轮若不是 `--update` 打出 `pickbig: unimplemented` 这行 diff，
  我会把「放宽正则导致条件解析退化」当成一次成功合入。
- **`find(x)` 单参落地**（上一轮第 1 项之后的实测选点）：
  此前 `find(x)` 被判成 **OP-INDEX**（"对名为 `find` 的数组取下标"）——
  与 `isempty`/`numel`/`sqrt` 同一类**静默误判**。
  实现：复用既有 `OP-FIND`，`cmp=5`（`mlc_mask_test` 的 default 分支 = `v != k`）、`k=0`，
  **C 侧零改动**，长度数据相关走已有的 `mlc_op_find_alloc`。
  语料 34 → **35**（`findnz`，实测 `1 2 3 4`，与 Octave 一致）｜官方 `check_all` **rc=0**
- YALMIP 读数复核（本轮重跑）：`numeric 3 ｜ 桩 55 ｜ error 0 ｜ 形状 103 ｜ 拒绝 1043`
  —— `cond` 修复在该工程里**没有直接兑现**（那些函数还有别的阻塞）。
- 桩的「第一条 TODO」分布（本轮实测，1197 个含 UNIMPLEMENTED）：
  `reject 1043` ／ **`unmapped 89`** ／ **`call 18`**（绝大多数是 `find` 相关）／
  `shape 15` ／ `ret 9` ／ `set 9`（全局赋值，不做）／ `call2 6` ／ `if 5`
- **「内置名被当作下标」变成常驻判据**（上一轮第 2 项）：
  新增 `tests/test_no_shadowed_builtins.py`（3 条）：
  1) 语料扫描必须为 **0**（`scan_shadowed_builtins`）
  2) 后处理 `_drop_shadowed_indices` 把未声明的下标目标改写成 `# why:shadowed` + `unmapped`
  3) 已声明的数组取下标**不得误伤**（保留原语句）
  第一版我把它写成"临时造一个 `y = zzz(x)` 让扫描器抓到" —— **跑出来是 0**，
  因为后处理在扫描之前就已经把它改写了（流程自我修复了）。于是改为直接单元测后处理本身。
- YALMIP 复测（本轮）：`numeric 3 ｜ 桩 55 ｜ error 0 ｜ 形状 103 ｜ 拒绝 1043`
  —— 与上一轮一致：本轮与上轮的谓词/误判收口**没有让任何原本算对的函数失效**。
- 官方 `check_all` rc=0 ｜ 语料 37/37
- **`find(a == b)` 尝试失败并回退（语义错，不是编译错）**：
  动机来自实测：非 reject 的「只差一条 TODO」共 62 个，最大簇是 **`call` 15 个**，
  全是 `call:pos:find:T==t` —— 我们只支持 `find(x > 数字)`，右侧是**变量**时退化成 `call:`。
  本轮加了 `_FIND_VAR_RE` + 发射器放宽（k 可取自 `.data[0]`），MIR 正确产出
  `op:OP-FIND:y:a:4:b`，但**结果错**：
  ```
  Octave: findeq: 1 2 3 4        （a、b 全等 -> 4 个命中）
  我们  : findeq: 1              （把 b 当成标量，a[i] == b[0] 只命中 1 个）
  ```
  ⇒ `find(a == b)` 是**逐元素比较两个数组**，需要 `mlc_op_find_masked(a, b, cmp, out)`，
  不是"数组 vs 标量"。已整体回退（语料 37/37）。
- 记一个可复用的判断：**`find(x > k)` 与 `find(a == b)` 是两种算子**，
  前者右边是标量阈值，后者右边是等长数组 —— 签名相同但语义不同，不能共用同一实现。
- **`find(a == b)` 正确实现（新算子 `OP-FIND2`）** —— 上一轮语义做错的那一簇：
  `mlc_op_find_masked(a, b, cmp, out)` 逐元素比较**两个等长数组**（复用 `mlc_mask_test`），
  不等长直接 `MLC_ERR`（不猜）。与 `find(x > k)`（右侧标量阈值）明确分成两个算子。
  实测：`findeq: 1 2 3 4`（a、b 全等 → 4 个命中），与 Octave 一致。
  语料 37 → **38**（TP7 38/38）｜官方 `check_all` rc=0
- 这一簇的价值：非 reject 的「只差一条 TODO」共 62 个，其中 **`call` 15 个全是
  `call:pos:find:T==t` 这一形态** —— 本轮的算子直接对准它们。
- 过程记录（第 N 次同一类自伤）：算子表里 `"rules": ()` 空元组被门判「缺字段」，
  与 `OP-COL` 完全相同；内联 Python 的引号转义又一次把命令搞坏，改用脚本文件。
- **`findhash` / `findhashsorted` 的 `error` 定位到驱动侧**（上一轮第 1 项）：
  1) 先做**单函数微测试**：直接调 `m2c_findhash(T, t, dummy, &pos)`（含驱动同样的
     `pos` 预初始化），得到 `rc=0 numel=4`；单独调 `mlc_op_find_masked` 也得 `hits=4: 1 2 3 4`。
     ⇒ **生成代码与算子都是对的**。
  2) 再看驱动的参数构造，找到差别：
     ```c
     mlc_array_init(&T, MLC_F64, 1, (int64_t[]){4});          /* 有默认形状 */
     mlc_array_init(&t, MLC_F64, 0, (int64_t[]){});           /* ← ndim 0，空数组 */
     mlc_array_init(&dummy, MLC_F64, 0, (int64_t[]){});       /* ← 同上 */
     ```
     `t` / `dummy` 没拿到 `[4]` 的默认形状，于是 `find_masked` 因「两数组不等长」正确拒绝
     → 函数返回 `MLC_ERR` → 报 `error`。
  3) 所以这不是 `find(a==b)` 的缺陷，而是**驱动的"无注解入参默认形状"只对部分参数生效**。
     下一轮查：为什么 `T` 有、`t`/`dummy` 没有（疑似名字与驱动局部变量冲突，或某个过滤条件）。
- 本轮读数（如实）：`numeric 3 ｜ 桩 53 ｜ error 2 ｜ 形状 103 ｜ 拒绝 1043`
- **突破：驱动给「**所有**数组入参」默认形状 —— `numeric 3 → 4`**（多轮来首次上升）
  根因（R558 定位、本轮修复）：驱动只给 `arrays[0]` 假设 `[4]`，其余按**声明形状**构造，
  无注解时就是 `mlc_array_init(&t, MLC_F64, 0, {})` —— ndim 0、numel 0 的**空数组**。
  于是 `find(T == t)` 因两数组不等长被正确拒绝 → 函数报 error。
  修法：其余数组入参同样按「无注解 → `[4]`」构造，并**显式打印** `assumed shape [4]`。
  读数：
  ```
  numeric 3 → 4 ｜ error 2 → 0 ｜ unimplemented 53 → 54 ｜ 形状 103 ｜ 拒绝 1043   （合计 1204 ✓）
  ```
- 新增语料 `translate/examples/nouns/addtwo.m`（两入参）与
  `tests/test_multi_arg_driver.py`：断言两个入参都有 `assumed shape [4]`、结果 `2 4 6 8`。
  这条锁防的正是"只有第一个参数有默认形状"的回退。
- 官方 `check_all` rc=0 ｜ 语料 38/38
- **`find(x, n)` 落地（新算子 `OP-FIND3`）** —— 桩里 `call` 类最大的一簇
  （「find 要 1 个，实际 2 个」= `find(x,2)`）：
  `mlc_op_find_n(a, cmp, k, n, out)`：先按条件命中，再截断到**前 n 个**。
  实测 `findfirst: 1 2`（x=1..4 全非零，取前 2）｜语料 38 → **39**（TP7 39/39）｜`check_all` rc=0
- **审查驱动里「只取第一个」的写法**（上一轮第 1 项）：`project.rs` 里共 2 处 `arrays[0]`——
  1) 主驱动（已在上轮修好：其余数组入参也给默认形状）
  2) `--expect` 夹具驱动：用**声明形状**，`demo_port` 的参数全有注解，故是**潜在缺口而非现行 bug**
     （已记入下方风险，未改，避免动 TP5 金文本）
- 另记：驱动里 `int64_t x = (got>0) ? vals[0] : 2` —— **所有 i64 入参共用 `vals[0]`**，
  多 i64 参数时值会重复；属已知简化，未改。
- **`for i = 1:length(F)` 落地** —— 非被拒函数里未映射 `for` 共 77 条，
  其中 **55 条**上界是 `length/numel/size` 调用。
  两处改动（与 `_cond_side` 同构）：
  1) `mir.py`：`for v = a : f(...)` 先把调用降成临时量，再按普通 `for` 发射
  2) `emit.rs`：`for` 的上界放宽到「已声明的 1×1 数组」（读 `.data[0]` 转 `int64_t`）
  实测：`forlen: 4`（`for i = 1:length(x)`，x 长 4）｜语料 39 → **40**（TP7 40/40）｜`check_all` rc=0
- **同一个错误又犯一次（第三次）**：新正则把下界写成 `[A-Za-z_]\w*`，
  于是 `1` 不匹配 → 整条 for 仍进 unmapped。R550（`_IF_RE` 的 rhs 排除数字）是同一种错误。
  已改为 `(\d+|[A-Za-z_]\w*)`。**「名字的字符类」不等于「任意 token」**。
- **第一次用第三方仪器检查 C 运行时**（此前仓库里一处都没有）。
  实测本机能力：
  ```
  -fsanitize=address  → 链接失败（MinGW 不带 libasan）
  -fsanitize=undefined/leak → 同上（无 libubsan/liblSan）
  cppcheck  [OK] 16.2 工具链附带      gcov [OK]      valgrind x      cl.exe [OK]（MSVC 2022，未接）
  ```
  ⇒ 本机可用的第三方仪器是 **cppcheck（静态）** 与 **gcov（覆盖率）**。
- **cppcheck 立刻抓到一处真缺陷**：
  ```c
  mlc_ops.c:70   int64_t idx[MLC_MAX_DIMS];        /* ndim == 0 时上面的 for 不执行 */
  mlc_ops.c:114  pa[mlc_bcast_offset(a, ndim, idx)]  /* 读未初始化 */
  ```
  `cppcheck: warning: Uninitialized variable: idx [uninitvar]`。
  当前之所以没炸，是因为 `mlc_bcast_offset` 在 `ndim == 0` 时不读 `idx` ——
  **"靠下游保证"的隐式安全**。已改为 `= {0}`，复跑后 **warning/error = 0**。
- **工具化尝试失败并回退**：写了 `tools/check_runtime_static.py`（含两向自证，植入缺陷能报出），
  但 `check_all` 会**自动把 tools/ 下的脚本识别为门**，于是要求登记契约与 README 对等，
  6 道门同时变红。**时间不足，已移除工具与 README 改动**，只保留那行真修复
  （`check_all` rc=0，语料 40/40）。
  **下一轮第一件事**：按 `docs/GATE_REGISTRATION.md` 正式登记这个门（含 `SELFTEST COUNTS` 行）。
- **第 41 道门上线：`check_runtime_static.py`（契约 RS1–RS2）** —— 第三方静态分析进发版门禁。
  * **RS1**：cppcheck 的 `warning` 必须为 0；**RS2**：`error` 必须为 0（`style` 不计）。
  * 自证 5 项（含"植入未初始化读必须被报出"），`SELFTEST COUNTS {"bad": 0, "good": 5}`。
  * 按 `docs/GATE_REGISTRATION.md` 一次登记 **七处**：门本体 / `release.py GATES` /
    `GUARD_CONTRACT` / 两份 README 质量门表 / `check_all.py` ASCII 树 / `MIN_GUARDS` /
    散文门数（`CONTRIBUTING.md` 3 处、`README_CN.md` 3 处、`README.md` 2 处、`matlabc_help.py` 1 处）。
  * `releases/gates-last-run.json` 的记录是**真跑一次**写进去的（rc/ms 取自子进程），不是手填。
- 登记过程中被门逐个挡下的四件事（都记在这里，下次少走）：
  1. `ROW_SIGNATURE` 不能带 `u""` 前缀 —— P5 认不出，报"没有声明签名"；
  2. docstring 必须有一段**「退出码」**（0/1 的语义），否则 G2 红；
  3. 用 Python 读改写 Markdown 会把换行转成 LF —— `check_eol_convention` 立刻红；
  4. `check_figure_glyphs` 禁行内 emoji 字形（界面字体无字形），CHANGELOG 里历史 emoji 已换成 `[OK]/[x]/[!]`。
- **第二个第三方仪器上岗：gcov 覆盖率基准**（新增 `docs/COVERAGE_BASELINE.md`）
  ```
  mlc_ops.c      行 56.98% / 688 行 ｜ 分支至少走一次 48.42% / 663 个
  mlc_runtime.c  行 51.09% /  92 行 ｜ 分支至少走一次 46.38% /  69 个
  ```
  **未覆盖的行几乎全是 `return MLC_ERR` 及其卫语句** —— 语料只喂合法输入，
  所以约 43% 的行一次都没跑过，而那正是泄漏最容易发生的地方（早期 return 跳过 free）。
  ⇒ 此前"零内存问题"的结论**只覆盖 happy path**。
- 两处踩坑（都写进文档了）：
  1. `gcov -b -c mlc_ops.c` 报 `cannot open notes file` —— `-o num.exe` 时对象名是
     `num-mlc_ops.gcno`，必须用**对象名**调用；
  2. `--coverage` 编译若在仓库根执行，`.gcno/.gcda` 会落在根目录 —— 必须在临时目录里编译。
- 官方 `check_all` rc=0 ｜ 语料 40/40
- **门从 RS1–RS2 扩到 RS1–RS3：覆盖率进了门禁**（上一轮第 1 项）
  * **RS3**：`--coverage` 编 `mlc_ops.c` + 跑 40 例语料 + gcov 量数，
    要求 **行 >= 56.9%**、**分支至少走一次 >= 48.3%**（实测 56.98 / 48.42）。
  * 阈值故意压在实测值之下 —— **它守的是"不比今天更差"，不是"已经够好"**。
  * 没有 gcc/gcov 时打印跳过原因，不假装通过。
  * 门本体耗时 ~1.6s（含一次转 MIR + 编译 + 运行 + gcov），对此前的 30s 全检可忽略。
- 同步签名四处（`GUARD_CONTRACT` / 两份 README 质量门表 / `check_all` ASCII 树），
  `releases/gates-last-run.json` 按**真跑一次**更新。
- 又一次被自己绊倒：用 Python 改写 Markdown/代码后换行退化为 LF，`check_eol_convention` 立刻红 ——
  这已是同类问题第三次，规则写在这里：**凡是 Python 读改写仓库文本文件，写完必须跑 `to_crlf`**。
- **剩余计划有了可校验的出处**：新增 `docs/PLAN_TRACKER.md` + `tests/test_plan_tracker.py`
  * 表里写的是**四组**：v1.0.0 的三个硬条件（C1–C3）、深度五项（D1–D5）、
    能力队列（A1–A6，每条带实测依据）、里程碑与剩余轮次（M1–M4）。
  * **它不是散文**：`test_plan_tracker.py` 的 5 条判据把文档数字钉在现实上 ——
    语料条数、覆盖率（真的编译+运行+gcov 后比对）、RS3 阈值、门数。
    现实变了而表没改 → 门红。
  * 已接进 **GX2**，默认 `check_all` 就会跑它（约 +3s）。
- 当前状态（写进表的第五节，逐轮更新）：
  ```
  check_all rc=0，41 道门 ｜ 语料 40/40 ｜ YALMIP numeric 4 / 桩 54 / error 0 / 形状 103 / 拒绝 1043
  覆盖率 mlc_ops.c 行 56.98%、分支至少走一次 48.42%
  ```
- 剩余轮次估计（**只在 C1 的分母 161 不变时成立**）：距离 v1.0.0 约 **13~16 轮**
  （M2 深度基线 2~3 轮 / M3 能力达标 8~10 轮 / M4 正式版 +3 轮）。
- **D4 泄漏专项：定位到 `mlc_array_init` 的 `memset`，实现后回退（负结果入库）**
  * 事实：`mlc_array_init` 一进来就 `memset(a, 0, sizeof(*a))` —— **旧 `data` 指针被直接抹掉**，
    重复 init 等于泄漏；而本机没有 ASan（MinGW 无 libasan），所以它此前**没有任何工具能看见**。
  * 试过并验证有效的部分：加 `magic` 字段 + 分配/释放计数后，探针实测
    ```
    修复前思路（仅计数）：alloc=0 free=1      ← 计数没生效，泄漏被掩盖
    修复后（magic + init 先 free）：alloc=1 free=1 balance=0   [OK]
    ```
  * **但整体回退**：`init` 语义变更（"重复 init 会释放旧缓冲"）让两条既有判据变红 ——
    `test_op_error_paths`（未初始化栈变量路径）与 TP5 的**生成物自测**。
    换句话说：**它不是加一个计数，而是改动运行时的核心语义**，需要一整轮把
    所有调用点（驱动预初始化 ret、`fill:`、dynshape 路径）逐个对齐。
  * 下一轮的做法（已想清）：先只加**计数器**（不改语义）→ 用探针**量出**当前有几处泄漏 →
    再逐点修调用方，而不是改 `init` 的语义。
- **D5 完成：`docs/MIR_SEMANTICS.md`（42 个算子逐条写清语义）**
  * 结构：数据模型（行主序不变量）→ **五条通用规则 G1–G5** → 8 个算子族逐条
    （dtype / 形状 / 所有权 / 错误 / 顺序）→ **「明确未定义」清单** → 文档如何被守住。
  * **「未定义」清单是这份文档最重要的部分**，它把两轮撞过的墙写成了条目：
    `init` 重复调用（D4 的 S2/S3）、别名（`y = x`）、`depth >= 3` 魔数、`global`、NaN/±0。
  * 判据 `tests/test_mir_semantics.py`（4 条，已接 GX2）：
    每个 opcode 必须出现在文档里（新增算子不写文档就红）/ 五小节齐备 /
    G1–G5 逐条在 / 「未定义」必须含 init 与别名。
  * 这份规范的直接用途：下一轮修 S2 泄漏时，先按 G1「init 是构造」去改**调用方**，
    不再去动 `init` 的实现 —— R568 就是因为没有这句话，改错了层。
- **`cond`（条件里带调用）真正落地** —— 语料 39 → **40**
  三轮定位、两轮回退之后，本轮在**当前基线**上一次通过：
  ```matlab
  if size(A, 1) ~= size(A, 2)      % A = 2x3
  → condsize: 1                    % 与 Octave 一致（TP7 40/40）
  ```
  MIR：`op:OP-SIZE:__c1:A:1` + `op:OP-SIZE:__c2:A:2` + `if:__c1:ne:__c2`（体内 `const:y:1` 真的发射）。
- **回看这三轮失败的价值**：R541 退在正则层、R543 退在"判定点不存在"、
  R545/R548 退在 C 侧与金文本。本轮之所以一次通过，是因为那三次把
  **`_IF_RE` 的数字字面量**、**`_cond_side` 问算子表**、**嵌套块 `const` 发射** 三件事都改对了
  —— 而它们分属三个不同的文件。
- 过程记录：我在本轮开头先**确认基线**（`git status` 干净、MIR 已正确），
  避免了第四次重放已合入的补丁 —— 前两轮各有一次"重放已完成改动"的空转。
- **新发现（P0，已定位未修）：YALMIP 现在编译不过**
  ```
  extras_monpowers_m.c:39: error: incompatible types when assigning to type
  'int64_t' from type 'mlc_array'
      temp = last_monoms;
  ```
  MIR 证据（`extras/monpowers.m`）：
  ```
  var:last_monoms:i64          ← 被分类成 **i64 标量**
  set:last_monoms:all_monoms   ← 但 all_monoms 是 f64 数组（ret）
  ```
  `last_monoms` 后来又被 `temp = last_monoms`（同为 i64 局部）接手，
  而 C 侧 `last_monoms` 实际是 `mlc_array` → 类型冲突。
  ⇒ **标量分类把"接受数组赋值的名字"判成了 i64**，产出不可编译的 C。
  这比"不支持"严重：它在生成期没有报错，而是在编译期炸在别处。
- 说明：本轮加入 `condsize` 后语料 40/40、`check_all` rc=0；
  但 YALMIP 的 `runnable_report` 因上述编译失败**跑不出读数**（与 R560 的 `numeric 4 / error 0` 相比是回归）。
  下一轮第一件事：修标量分类（凡被数组赋值的名字不得判 i64），恢复 YALMIP 可编译。
- **P0 修复第一步：`_fix_scalar_array_conflict` 原本是死代码**
  实测：该函数在 `mir.py` 里**只出现一次（def 那一行），没有任何调用点** ——
  所以「同一名字既当数组又当 i64 标量」的冲突从未被修正，
  `var:last_monoms:i64` 一直留着 → `int64_t temp = last_monoms;` → YALMIP 编译失败。
  * 新增 `_fix_scalar_conflicts_per_func`：按 `func:` 分块调用（名字是函数作用域，跨函数合并会误伤）
  * 另一处加固：`arg:` / `ret:` 加入数组名集合（形参与返回值永远是 `mlc_array`）
  * 结果：`monpowers` 的 MIR 里 `var:last_monoms:i64` / `var:temp:i64` **消失**，
    那条编译错误**不再出现**
- **但它只是把错误往前推了一格**：YALMIP 仍编译不过，新错误是
  ```
  extras_setdiff1d_m.c:39: error: redeclaration of 'ia' with no linkage
      36 |     mlc_array ia;
      39 |     mlc_array ia;      ← 同一声明出现两次
  ```
  即**序言对同一名字声明了两次**（`ia` 同时出现在两类声明集合里）。
  下一轮：给序言加"已声明就跳过"的守卫。
- 语料 40/40 ｜ 官方 `check_all` rc=0（本轮改动无回归）
- **P0 修复完成：YALMIP 重新可编译**（上一轮第 1 项）
  根因：序言有**三个**声明循环（`temps` / `consts` / `fills`），只在 `fills` 里做了
  「已在 temps 里就跳过」，`consts` 与另两者的交集无人处理 ——
  `ia` 同时落在两个集合里，于是 `mlc_array ia;` 出现两次 → `redeclaration of 'ia'`。
  * 修法：三个循环共享一个 `declared: HashSet<String>`，**同名只声明一次、只 init 一次**
    （`need_free` 也只在"本次新声明"时登记，避免多释放）
  * 读数恢复：`numeric 4 ｜ 桩 54 ｜ error 0 ｜ 形状 103 ｜ 拒绝 1043`（= R560 基线）
  * 语料 40/40 ｜ `check_all` rc=0
- 两处过程记录：
  1. 第一次改时锚点写成 `for (t, _, shape) in &temps`，实际是 `for (t, shape, unknown)`
     —— 好在写入前 assert 就失败，文件**未被部分修改**（脚本把写文件放在最后）。
  2. 这个 P0 存活了 3+ 轮，因为**没有任何门会去编译一个真实工程**；
     `check_all` 41 道门全绿的同时，YALMIP 整个编译不过。
- **「真实工程能编译」变成常驻判据**（上一轮第 1 项）
  `tests/test_external_project_compiles.py`（约 0.6s，已接 GX2）：
  取**真实出过错的两个文件**编译，而不是取好看的样本 ——
  * `extras/monpowers.m` —— 数组经 `set:` 传递（`last_monoms = all_monoms`）
  * `extras/setdiff1D.m` —— 同名同时进 `consts` / `fills`（重复声明）
  外部工程不在仓库里：目录缺失则**跳过并打印原因**，不假装通过。
- 过程中踩到自己最常犯的坑，并当场加了断言：
  样本里写成 `setdiff1d.m`（实际是 **`setdiff1D.m`**，大写 D）→ 找不到就
  **静默只测了 1 个文件**，而测试仍然是绿的。
  已改为「缺任何一个就红」：
  ```
  应有 2 个真实文件，实际找到 1 个 —— 文件名或路径变了
  ```
  这正是前几轮反复出现的「扫描面悄悄变小」。
- **`return`（提前退出）做到一半，回退**（上一轮第 2 项）
  * 规模实测：非被拒未映射 1021 条里 `control` **82 条全是 `return`**；
    相邻的 `strlit` **130 条是 `error(...)`** —— 两者同属"提前退出"，是同一个机制。
  * 打通的部分：`mir.rs` 加 `Stmt::Return`、解析 `return`/`return;`、
    `emit` 发 `goto m2c_cleanup;` —— 用**手写最小 MIR** 验证到：
    ```c
    goto m2c_cleanup;      ← 有了
    ```
  * **但标签没发出来**（`m2c_cleanup:` 缺失）：`terminated = true` 让函数尾部的
    「加标签 + 释放 + return st」整段被跳过 → 悬空 `goto` = 编译不过。
  * 时间不足，整体回退（`mir.rs` / `emit.rs` / `mir.py` 三处），语料 40/40 保持。
  * 下一轮的正确做法：**把标签放在 `emit_block` 之内、`terminated` 判断之外**，
    即先固定"清理段"这个结构，再接 `goto`；顺序反过来就会得到悬空跳转。
- 本轮另一个实测结论（供排队用）：非被拒未映射 1021 条的成因
  `slice2d 275（26.9%）｜ other 264（拼接）｜ strlit 130 ｜ cond 102 ｜ control 82 ｜ nested 82`，
  其中 `and/or` 复合条件只有 25 条 —— **不值得单独做**。
- **`return`（提前退出）落地 —— YALMIP `numeric 4 → 8`**（R578 回退后按新顺序重做）
  * 关键顺序（R578 失败的原因）：**先让清理段无条件存在，再接 `goto`**。
    `has_return` 为真时无条件产出 `m2c_cleanup:` + 释放临时量 + `return st;`；
    然后把 `Stmt::Return` 发成 `goto m2c_cleanup;`。
  * **两向验证**（手写最小 MIR）：有 `return` 时标签与 `goto` 同时存在且能编译；
    **无 `return` 时两者都不出现** —— 其余函数生成物逐字节不变。
  * 语料 40 → **41**（`earlyret`：`y=7; return` 之后不再执行 `y=3`，实测 `7`）
  * 大规模验收：
    ```
    YALMIP  numeric 4 → 8 ｜ 桩 54 → 49 ｜ error 0 ｜ 形状 103 ｜ 拒绝 1043
    ```
    一次改动吃掉了 5 个桩、让 4 个函数真正算出了数。
- `docs/PLAN_TRACKER.md` 的防腐蚀判据**当场报红**（语料 40→41 没同步），
  按它更新后恢复绿 —— 这条判据第一次真正拦住我。
- **`error('...')` 落地为 `fail`（MLC_ERR + 跳到清理段）** —— 与 `return` 共用同一个落点
  * 实测依据：非被拒未映射里 `strlit` 130 条几乎全是 `error('...')` ——
    它们是**守卫条款**（条件不满足就报错退出），此前整条被丢弃。
  * 三层改动：`mir.py`（`error(` → `fail`）｜ `mir.rs`（`Stmt::Fail`）｜
    `emit.rs`（`st = MLC_ERR; goto m2c_cleanup;`），并把「清理段存在条件」从
    `Return` 扩成 `Return | Fail`。
  * 两向验证（最小 MIR）：`fail` 时标签/错误码/跳转三者齐备且能编译；
    没有 `fail`/`return` 的函数**不出现标签**（其余生成物逐字节不变）。
  * 真实文件验证：`extras/adjoint.m` 的未映射从 6 → **5**，`error('Matrix must be square')`
    不再进 `unmapped`，而是 `fail`。
  * 读数：YALMIP 仍 `numeric 8 ｜ 桩 49`（那些函数还有别的未映射），
    但**语义忠实度提升了**：守卫条款从"被丢弃"变成"以错误码退出"。
  * 语料 41/41 ｜ `check_all` rc=0 ｜ `MIR_SEMANTICS.md` 增 3.10（控制流：return / fail）


## 2.2.2

- **返回值形状推断**：`out_shape_for` 原来只看 `Stmt::Op`，于是
  `A = zeros(m,n)` / `A = f(x)` / `A = 3` 这类返回值一律「推断不出形状」。
  现按来源保守推断（`fill:` 维度确定 / `set:` 标量 1x1 / `call:` 取被调函数已标注的返回形状，
  没标注仍返回 None 不猜）。YALMIP 生成物 **TODO(ret)：148 → 0**
- 修重复声明：同一名字既被 Op 当暂存量、又被 `fill:` 当目标 → 声明两次
  （gcc `redeclaration of 'temp' with no linkage`）；暂存量收集改为跳过 fill 目标
- **未修（放行后暴露）**：更多函数真正发射后出现「同名既标量又数组」
  （`x2_list` conflicting types / `sqrList` redeclared），与 R487 的 `'d'` 同类 ——
  因此 YALMIP 全工程 gcc 仍不通过，**不把「TODO 归零」当成功**

## 2.2.1

- 修「副作用调用旁注用了 `/* */`」——`/* */` 不是合法 MIR 语句，跨行 `disp('...')`
  会让整个工程报「不认识的构造」，1204 个函数全产不出；改成 `# dropped:` 后通过
- 关键测量：YALMIP 生成物里 **1204 个函数体没有一个干净**（0 个不含 `TODO`）；
  按种类：`reject` 1043 ／ **`ret` 148（推断不出返回值形状，需要标注）** ／
  `unmapped` 130 ／ 其余零星。结论：**"可做函数 137" 是虚荣指标**，
  绑定约束是**形状信息**，不是语句形态
- 实测排除两个方案：`global` 声明（丢弃会让回调读到局部 0，静默算错）；
  带括号条件 `if (a==b)`（全仓 5 处、可翻转 0 个）

## 2.2.0

- 副作用调用丢弃 + GX 提速（与 2.1.9 同一批改动，发版号自动进位时补本节）

## 2.1.8

- **纯输出/计时类调用直接丢弃**（`disp`/`fprintf`/`tic`/`toc`/`warning` …）：
  它们不产生数据，丢弃后语义只差"屏幕上没字"。**`error` 不丢** —— 它是控制流，
  丢掉会静默改变行为（仍然如实记 unmapped）。
  函数级验收：YALMIP 可做函数 **139 → 137**（`scope_demo` / `local_a` 正是只差
  `disp(x)` 的那两个），可做语句 1086 → 1076，未映射 27960 → 27680
- **GX 门提速 4.9s → 3.4s**：三个用例文件合并成**一次** pytest 启动，
  失败归因改由 `FAILED <file>::<test>` 行解析（不再"一次跑一个文件"）。
  两向验证过：让多返回断言失败 → 红且**正确归因到 GX2**；还原 → 绿
- 未做：`log2`/`find` 多输出内置（需要"多输出算子"，与 `call2` 是两套）；解释器 `call2:`

## 2.1.6

- **支持两个运算符的表达式**（按优先级选切分点 + 递归降级）：
  `y = B - X*X` 此前因为「右侧 `X*X` 不是原子」整条放弃；现在降成
  `__e1 = X*X; y = B - __e1`。
  同时修正一个潜在错算：原来的 `_EXPR_BIN` 按**第一个**运算符切，
  `a*b+c` 会被切成 `a * (b+c)` —— 优先级反了。
- **函数级验收（这才是主指标）**：YALMIP 可做函数 **141 → 139**（`mytestNEW`/`mytestOLD`
  正是只差这一条的那两个），可做语句 1102 → 1086，未映射 28051 → 27960
- 选活方式改了：不再按「语句出现频次」挑，而是按「这个函数只差几条、差的是哪条」挑
  （141 个可做函数里，阻塞条数分布：差 1 条 16 个 / 差 2 条 22 个 / 差 3 条 14 个）
- 下一批候选（差 1 条的其它形态，未做）：`disp`/`fprintf` 这类**副作用调用**（2 个函数）、
  `global` 声明（2 个）、`log2`/`find` 多输出内置（3 个）

## 2.1.5

- **多返回的验收数字（如实记，不好看）**：重跑 YALMIP 后
  未映射语句 **28687 → 28051**（−636）、可做语句 **1161 → 1102**（−59）、
  **可做函数 141 → 141（0 增长）**。
  多返回把 59 条语句变成可映射，但没有一个函数因此变绿 —— 用到它的函数都还有别的阻塞。
- **给多返回补语料与运行判据**：`translate/examples/multi/`（`twoout` 返回 `[lo,hi]`，
  `userange` 里 `[lo,hi] = twoout(x)` 后算极差）
  - `tests/test_generated_compiles.py` 增加 `examples/multi`（GX1 覆盖多返回）
  - 新增 `tests/test_multi_return.py`：跑生成物断言 `twoout: 1 | 4`、`userange: 3`
    —— 只做 `-fsyntax-only` 证明不了「两个值真的写进两个不同对象」
  - 并入 GX2，**不新增判据前缀**（避免再动那 7 处登记）
- 未做：解释器 `mir_eval` 还不解析 `call2:`；`size`/`find`/`unique` 多输出内置

## 2.1.4

- **多返回调用 `[a,b] = f(x)` 端到端可用**（上一轮第 1 项）：MIR 走 `call2:`
  - `mir.py` 降级 / `mir.rs` 解析与 `Stmt::Call2` / `emit.rs` 发射（校验返回值个数 == 左值个数）
  - `Func::declared()` 补上 `Call`/`Call2` 的左值 —— 原来只有 Op/Const/Fill/For，
    调用的输出一旦不是形参或返回值，就被判「不在作用域内」，整函数变 unimplemented
- **顺手修一个潜在越界**：`collect_temps` 里 `Stmt::Call` 的暂存量被硬编码成 `[1]`，
  被调函数返回 3 元素时会写越界（静默内存破坏）。现在按 callee 的 ret 形状分配
- 验证：`twoout` 返回 `[lo,hi]`，`userange` 里 `[lo,hi] = twoout(x)` 后算 `hi-lo`
  → 实测 `twoout: 1 | 4`、`userange: 3`；17 道门全绿
- 未做：解释器还没解析 `call2:`（只影响参考实现对拍，当前语料不含多返回）；
  YALMIP 尚未重跑做函数级验收

## 2.1.3

- **新增 `docs/GATE_REGISTRATION.md`**：把「新增一条门要动 7 处」的清单写死，
  含两处只有撞到才知道的细节（**H2b** 判据前缀必须出现在以它开头的字面量里；
  **H2e** `check_all.py` 文档串里的 ASCII 树也要补一行）。这份清单是两次红仓库换来的
- **README 首屏新增「转换覆盖率」口径**（中英同步）：YALMIP 1204 个函数里
  1043 被整函数拒绝、**可做 141**、1161 条未映射按原因归类。
  并写明「**语句映射率会系统性高估进度**」—— 函数是与门
- **两条实测结论（用来否决一个计划）**：
  · 纯别名 `y = x` 在 YALMIP 里 **0 处** —— 原本计划的 `OP-COPY` 对真实工程无收益，不做
  · 多返回 90 条里 **75 条调的是同工程函数**（`derivebounds` 11 / `fmincon_*` 11 …），
    所以多返回值得做，但要动 4 处 + 形状链，本轮时间不足以安全完成，**未开始**

## 2.1.2

- **把「生成物必须能编译」封成发版门**（上一轮撤回的那项，本轮按清单一次做完）：
  新增 `tools/check_generated_compiles.py`（**GX1–GX2**），登记进 `release.py` 的 `GATES`
  —— 发版门 16 道 → **17 道**
- **注册一条新门要动 7 处**（本轮实测，写清备查）：门本体 / `GATES` / `GUARD_CONTRACT` /
  两份 README 质量门表（表行须含签名）/ `check_all.py` 的 ASCII 树行
  （须含「契约 GX1..GX2」）/ 散文里的门数（CONTRIBUTING + 两份 README + `matlabc_help.py`）
- 两处只有撞到才知道的细节：
  - **H2b**：签名声明的判据前缀必须出现在**以它开头的字符串字面量**里 ——
    用 `"%s …" % ("GX1", …)` 这种拼接，静态门看不见，会被判「幽灵声明」
  - **H2e**：`check_all.py` 文档串里的 ASCII 树必须补一行，否则红

## 2.1.1

- **把「生成物必须能编译」封成护栏并登记进发版**：新增 `tools/check_generated_compiles.py`
  （GX1–GX2），加入 `release.py` 的 `GATES`。
  原因：那两条判据此前只活在 pytest 里，而**发版脚本跑的是 GATES 元组，不跑 pytest**
  —— 等于从未参与把关。现在发版门从 16 道变 **17 道**（墙钟 4.3s，仍在 5s 预算内）
- 顺带补齐登记联动三处：`GUARD_CONTRACT`（退出码契约）、`README_CN/README` 质量门表、
  本文件版本节

## 2.0.6

- **新增判据：生成的 C 必须能编译**（`tests/test_generated_compiles.py`）：
  对 `numeric` / `proj` / `demo_port.m` 三个示例各做一次「转换 → 生成 → `gcc -fsyntax-only`」。
  上两轮那个 `'d' redeclared` 能一路通过 16 道门（那些门只比数值、不编译整工程），
  只有人手动跑 gcc 才暴露 —— 现在它自己会红。两向：注入坏返回类型 → 3 failed；还原 → 3 passed
- **新增判据：丢弃返回值的调用不许退回 unmapped**（`tests/test_void_call.py`），
  顺带断言整工程可编译
- **它立刻抓到一个真 bug**：`y = x`（数组别名）在有 shape 注解时生成 `const:y:x` → MIR 非法。
  `const:` 现在只接受数字，非数字如实落到 unmapped（不猜）
- 未做：多返回 `[a,b]=f(x)`、README 首屏指标

## 2.0.5

- **修「形参被当标量」**（上一轮暴露的 `'d' redeclared`）：
  `function d = gcdfactor(A)` 里 `d = 1;` 触发了「首次 set 补声明」，于是生成
  `int64_t d = 0;` —— 与形参 `mlc_array *d` 撞名，**整个工程编译不过**。
  现在入参/返回值一律按数组处理（数字走 `const:`，且只认数字，`X = Y` 不会误入）
- **YALMIP 全工程重新可编译**：`gcc -fsyntax-only` 通过（1204 函数 / 1104 个 `.c`）
- 指标：未映射 28687 ｜ 算子 3239 ｜ 可做函数 141/1204（被拒 1043）
- 踩到的第二处：新分支把 `_ATOM` 当数字用，`X = Y` 生成 `const:X:Y` → MIR 非法
  （「只接受数字」的检查必须显式写，不能靠上游正则宽窄）

## 2.0.4

- **支持丢弃返回值的调用** `foo(a,b);`：造一个丢弃用临时量走 `call:` 通道。
  YALMIP 里 34 处，此前一律记 `unmapped（纯调用）`
- **修一个会让整份 MIR 不可解析的 bug**：条件降不下来时（如 `if size(Axplusb,2)>1`），
  块被 push 了却没有对应的 `if:` 行 → 后面的 `else` 成为孤行 →
  **整个工程生成失败**，而报错只指向“多余的 else”。现在发一条**恒假占位** `if:0:eq:1`
- **函数级主指标**（上一轮教训的落实）：YALMIP 可做函数 **144 → 141**、
  可做语句 1168 → 1161、未映射总数 28821 → **28687**
- 全函数级验收口径：可做函数 141 / 1204（被拒 1043）

**已知缺陷（本轮暴露，未修）**：`extras_gcdfactor` 生成物报
`'d' redeclared as different kind of symbol` —— 同一个名字既当标量又当数组声明。
这是被新能力“放行”后才暴露出来的，属于发射器的变量声明去重问题。

## 2.0.3

- **裸条件支持取反**：`if ~isempty(x)` / `if ~ok` → `if:<tmp>:eq:0`。
  上一轮只做了正形态，而 YALMIP 里 26 处 `isempty` **全是 `~isempty(...)`** —— 一条也没吃到
- 语料增至 **23 个函数**（`notempty: 1`：`~isempty(x)` 取首元素），与 Octave 真值一致
- **补上欠了三轮的验收：重跑 YALMIP 量化这三轮（裸条件 / isempty / 空数组 / 取反）的真实影响**

  | 指标 | 三轮前 | 现在 | 变化 |
  |---|---|---|---|
  | 未映射语句总数 | 33582 | **28821** | **−4761（−14.2%）** |
  | 可做语句（未拒函数内） | 1403 | **1168** | **−235（−16.8%）** |
  | 可做函数数 | 147 | **144** | **−3（几乎没动）** |
  | 算子语句 | 2443 | 3230 | +787 |

  **结论（比数字重要）**：语句级改善 17%，**函数级几乎没有改善**。
  因为一个函数要**全部语句**都映射才可转 —— **边际语句收益 ≠ 能力收益**。
  这也解释了为什么前几轮“补语法”总是感觉没进展。

- 剩余可做语句的形态：其他 64.1% ｜ 条件类 11.4%（`all`/`length`/`isempty`/`isequal`/`any`/`size`）｜
  多返回 7.7% ｜ `else` 孤立 4.2% ｜ `return` 3.9%

## 2.0.2

- **支持空数组 `A = []`**：降成 `fill:A:0:0`（numel 0）。运行时
  `mlc_array_init` 对 `n == 0` 本就正确处理（`data=NULL`、`owns_data=1`），
  与上一轮的 `isempty` 正好成对
- **MIR 形状校验放宽**：以前要求「必须为正」，把 0 堵死；现在只拒负数。
  这条校验在 `mir.rs` 里**有两处**（通用形状 / `fill`），两处一起改 —— 第一遍只改了
  一处，报错原样复现
- 语料增至 **22 个函数**（`emptychk: 1`：`A = []` + `if isempty(A)`），与 Octave 真值一致
- 未做：`return`（3.3%）、混合负载基准、用新能力重跑 YALMIP 量化收益

## 2.0.1

- **支持「裸条件」**：`if isempty(x)` / `if ok`（没有比较运算符）降成
  `if:<tmp>:ne:0` —— 与 MATLAB 的标量真值语义一致（非零/非空即真）。
  `while` 同样支持
- **新增算子 `OP-ISEMPTY`**：`isempty(x)` → 1x1 的 0/1（C / 发射器 / 算子表 / 解释器四层齐）
- **修一个误判**：`isempty(x)` 曾被当成「对名为 `isempty` 的数组取第 x 个元素」
  （`OP-INDEX:__t1:isempty:x`，能生成、能编译、**结果完全错**）。
  现在 `_index_operand` 单参分支**先问算子表**，与 `_lower_binary` 的做法统一
- 语料增至 **21 个函数**（`firstel: 1`，裸条件 + `if/else`），与 Octave 真值一致；
  对拍 PA1 21 / PA2 0 / PA3 0
- 未做：空数组 `A = []`、`return`、混合负载基准

## 2.0.0

**这一轮的正事是还一笔欠了八轮的债 —— 结论是：那笔债根本不该还。**

- **`dualize` 是被整函数拒绝的**（`reject:cell,struct`）。它的 431 条"未映射"
  永远不可达，却被 `unmapped_report` 连续八轮排在榜首。照着榜单干活等于往死路上走
- **修 `unmapped_report`**：默认**排除被拒函数**，并显式报出这个分母；
  `mir_eval` 之前根本没解析 `reject:`（字段缺失，过滤形同虚设）——两处一起补
- **修正后的真实分母**：YALMIP 1204 个函数 → 被拒 **1043** ／
  **可做 147（合计 1403 条未映射）**。榜首变成 `uniquesafe`（55 条），而不是 `dualize`
- **可做语句的形态**（决定下一步该补什么）：
  条件里带函数调用 **10.9%** ｜ `else` 孤立 6.1% ｜ 多返回 `[a,b]=` 6.4% ｜
  `elseif` 2.2% ｜ 空数组 `A=[]` 4.0% ｜ `return` 3.3%
  —— 最大的一项是**条件里带库函数**（`isempty`/`size` 等），那是**语义层**缺口，不是语法层
- `CONTRIBUTING.md` 加一条过程约束：**性能任务不得连续挤占功能任务**
  （本轮之前连续八轮被挤，欠账反而被写进了"下一步"却一直没做）

## 1.9.9

- **`mlc_op_matmul` 换 4x4 微内核**：300x300 从 6.6 ms 降到 **2.6 ms（2.4x）**，
  与非 BLAS 的差距从 **慢 10 倍** 收窄到 **慢约 4.5 倍**
  - 做法：16 个独立累加器 + 每次内层迭代装载 4+4 个元素、做 16 次乘加；
    行/列不足 4 的尾块退回标量 ikj
  - 正确性：`sum(y)` 指纹与 Octave 一致（5.473696433e+16），移植门全绿
- **把两次尝试并排写进报告 9.4 节**：分块（无效，瓶颈不是缓存）／微内核（有效，摊薄装载）。
  **这条短板没有消除，只是缩小** —— 要用矩阵乘请链外部 BLAS
- README 首屏的矩阵乘结论从「慢 ~10 倍」更新为「慢 ~4.5 倍」，并说明是微内核带来的
- 未做：`dualize` 逐行推进（连续第八轮）；混合负载基准

## 1.9.8

- **给 `mlc_op_matmul` 加缓存分块**（`BI/BJ/BK` + `restrict`）：**没有提升**
  （300x300：6.6 ms -> 6.9 ms，在噪声内），结果仍与 Octave 一致
  - 结论：瓶颈**不是缓存**，而是最内层的标量乘加 —— 不接 BLAS（或写 4x4 微内核），
    分块只是白费功夫。**这条负结果如实记录，不留"看起来优化过"的痕迹**
- **README 首屏新增「它快吗？」**（中英双份）：直接给出
  「循环快 ~90x ／ 归约持平 ／ 矩阵乘慢 ~10x」，并写明
  **不要把"翻译成 C 就会变快"当默认结论**
- 未做：`dualize` 逐行推进（连续第七轮）；4x4 微内核；混合负载基准

## 1.9.7

- **四个基准全部做到「结果一致 + 两边口径相同」**，并因此**推翻了一个错误结论**：
  | 用例 | C（进程内） | Octave（进程内） | 比值 | 谁赢 |
  |---|---|---|---|---|
  | `bench_loop` | 14.6 ms | 1337 ms | **91.6x** | C |
  | `bench_sum` | 0.100 ms | 0.084 ms | 0.8x | 持平 |
  | `bench_matmul` | 6.60 ms | 0.599 ms | **0.1x** | **Octave（BLAS）快 10 倍** |
  - 此前报的 `matmul 18–21x` 是**混口径**（C 进程内 vs Octave 含启动）；
    两边都进程内后，我们**慢 10 倍**
  - 诚实结论：**赢在"解释执行的循环"（91x），输在"库函数"（matmul 0.1x）**。
    把 MATLAB 逐行翻成 C **不会自动变快** —— 只有原文本身是"解释器吃亏"的写法才快
- 修一个 Octave 侧构造 bug：`reshape(1:n, [n])` 在 Octave 非法（需 ≥2 维），
  一维输入改用列向量 —— 这就是三例一直取不到值的真正原因
- **`CONTRIBUTING.md` 新增「基准判据」四条**：先算出再算快 / 两边同值 / 两边同口径 / 报区间

## 1.9.6

- **基准加「结果正确性」断言**：C 驱动与 Octave 驱动都输出 `VAL <sum(y)>` 指纹，
  两条路的值必须一致（相对误差 1e-9），否则 **拒绝报告耗时**。
  只查"有没有 unimplemented"不够 —— 桩可以返回 `MLC_OK`，也可以算错
- **修一个驱动 bug**：`% @m2c shape y ...` 是**返回值**，此前被当成入参构造并传入，
  Octave 报 `function called with too many inputs`。现在按 `function` 行区分入参/返回值
- 实测：`bench_matmul` **结果一致**（`sum(y) = 5.473696433e+16`，C 与 Octave 同一个值），
  耗时 6.40 ms → **21.8×**
- **缺口如实保留**：`bench_loop`/`bench_vec`/`bench_sum` 的 Octave 侧进程内驱动
  仍取不到值（只打印 C 侧指纹，**不做一致性判定**）—— 没有拿"没验证过"的数字当真

## 1.9.5

- **发现并修正一个错误的性能结论**：`bench_loop` 的 `y = y + x(i) * x(i);`
  是**三个操作数的嵌套式**，此前根本没有被降级 —— 生成的是 `return MLC_UNIMPLEMENTED` 桩。
  也就是说之前报的「C 10 ms vs Octave 157 ms（10–16×）」是拿**空实现**在比，**无效**
- **bench 增加硬校验**：先跑一遍生成物，若输出含 `unimplemented`/`skipped`
  就 **拒绝报告**（`PA5 拒绝报告：生成的 C 没有真正计算`）。
  原则：基准必须先「算得出」，再谈「算得快」
- **修形状推断**（同一根因的另一处）：通用二元分支（`OP-ADD` 等）仍用 `var_shape`，
  对临时量返回 None → `TODO(shape)` → 整个函数变 unimplemented。改用 `resolved_shape`
- 修正后实测（进程内口径）：`bench_loop` **15.65 ms → 12.8×**、
  `bench_matmul` **6.60 ms → 21.8×**；`bench_sum` 仍是 0.1 ms 级，
  该口径对它失真（已注明），`bench_vec` 的进程内驱动尚未产出

## 1.9.4

- **bench 增加「进程内口径」**（`--reps N`）：自己生成 C 驱动，构造一次输入、
  预热一次、再计时 N 次调用 —— 把**进程启动**和**输入构造**彻底移出计时窗口。
  实测 `bench_matmul` 纯计算 **6.35 ms**（整进程口径下是 40 ms，其中 ~30 ms 是构造与启动）
- **如实标注该口径的失真边界**：`bench_sum` 的 C 进程内是 **0.050 ms**，
  直接除 Octave 的 182 ms 会得到 **3636×** —— 这个数**没有意义**，
  因为分子是纯计算、分母里还含 Octave 自己的调用开销。**只对重负载可比**（矩阵乘 25.8×）
- **如实记缺口**：进程内驱动目前只覆盖部分用例（matmul 可用，loop/vec 未产出），
  不用整进程数字去填
- `E:\m2c\REPORT.md` 新增 9.1 节，把口径、失真边界、缺口一次写清

## 1.9.3

- **`mlc_op_matmul` 加 ikj 快路径**：紧凑行主序时最内层连续、可自动向量化；
  非连续视图仍走原来的 strided 兜底（正确性不变，移植门全绿）
- **基准增加「空载对照」**：同输入、只做一次逐元素加，用来扣掉「构造 2.2MB 输入 +
  分配 + 启动」。**只在输入形状完全一致时才扣**（否则扣掉的比被测还多）
- **修正一个测量错误**：`bench_matmul` 此前报 **3.2×**，因为把构造/分配开销算进了
  C 的耗时。扣掉空载后是 **18×**（C 12.0 ms ／ Octave 净 216 ms）
- 同时记清另三条**低估**：`bench_loop`/`bench_vec`/`bench_sum` 的 C 总计只有 ~10 ms，
  其中约 8 ms 是进程启动 —— 它们的比值（10–19×）是**下限**
- **未做**：`dualize` 逐行推进；bench 进发版门（噪声 ±50%，硬阈值只会误报）

## 1.9.2

- **性能基准扩到四类负载**（`translate/examples/bench/`）：循环热点、向量化、
  大数组归约、矩阵乘。实测（净算，对照 Octave）：
  `bench_loop` **10–16×** ｜ `bench_vec` **17×** ｜ `bench_sum` **19×** ｜
  `bench_matmul` **3.2×**
- **如实标出短板**：矩阵乘只有 3.2× —— Octave 走 BLAS，我们的 `mlc_op_matmul`
  是朴素三重循环。补 BLAS 后端之前，矩阵型负载不要指望赢
- **如实标出噪声**：同一用例重复三次，净算比值在 **9.8×–15.7×** 之间波动
  （Windows 调度 + Octave 抖动）。报告里给**区间**，不给单点
- **给出 MATLAB 基线的可复现脚本** `bench/matlab_baseline.m`（含预热、5 次取中位数）：
  本机没有 MATLAB，所以「相对 MATLAB」的比值**仍未测量**，脚本已备好
- `tools/bench.py` 支持**多参数 / 2-D 输入**（按 `% @m2c shape` 注解构造，
  与生成的 `main.c` 同规则：行主序 `a[i]=i+1`）
- `E:\m2c\REPORT.md` 新增第九节「性能」，把方法、区间、三条限制写死

## 1.9.1

- **首次给出性能数字**（此前一次也没测过）：新增 `tools/bench.py`，
  同一份 `.m` 分别用「生成的 C」与「Octave」跑，取多次最小值
  - `bench_loop`（200×1000 的取元素+乘+累加）：C **11.2 ms** ｜ Octave 净算 **661.8 ms**
    ｜ **≈59×**（含启动 111×）
  - `bench_vec`（向量化 `sum(x.*x)`）：**≈21×**（净）
  - 如实标注：Octave 是解释执行，**MATLAB 的 JIT 会缩小这个差距**；
    这里量的是「C 相对 Octave」，不是「相对 MATLAB」
- **异常路径判据**：`tests/test_runtime_bounds.py` —— 直接调 C 运行时，
  锁住 `mlc_op_index` / `row` / `slice` / `setidx` 的越界语义（必须 `MLC_ERR`，不静默截断）。
  两向：去掉 index 的越界判定 → 用例失败；还原 → 通过
- 基准用例放在 `translate/examples/bench/`，**不混进** `numeric/` 的 20 个正确性用例

## 1.9.0

- **`A(i,:)` 行切片**（新算子 `OP-ROW`）：按 `strides` 拷一行，不假设存储顺序；
  越界 `MLC_ERR`。语料增至 **20 个函数**（`row1: 3 4`）
- **解释器支持 `OP-SETIDX`**（先写用例 `tests/test_mir_eval_setidx.py`）：
  `apply_op` 是纯函数（没有 env/lhs），"就地写第 i 个元素"只能放在 `exec_block` ——
  上次我塞进 `apply_op`，方向就错了
- 解释器补 `OP-ROW`
- **对拍首次全绿：PA1 20 ／ PA2 0 ／ PA3 0** —— 20 个函数全部"参考实现与 C 都算过且一致"
- **未做**：越界/异常路径的语料用例、按 `unmapped_report` 榜单补 `dualize`

## 1.8.9

- **解释器正确支持 `break`**（上次补齐后又回退的那项，这次**先写用例**）：
  新增 `tests/test_mir_eval_break.py` 锁住最小语义（y 累加到 3 就退出），
  再改实现。踩到三个坑，每个都由用例当场抓出：
  1. 补丁插进了 `for` 分支（`if not exec_block(...)` 这个锚点在 for/while 各有一份）
  2. `break` 只阻止了**下一轮**，本轮剩余语句仍执行 → 结果 4（差一轮）
  3. 用例本身写错两次：无入参（`run_all` 不驱动零参函数）、用 `setb` 累加
     会把返回值变成标量（那不是真实形态）
- 对拍口径改善：PA1 **17 → 18**，PA2 **2 → 1**（只剩 `cumsum_loop`），PA3 **0**
  —— `while2d` 现在**参考实现与 C 都算 6**，与 Octave 真值一致
- **未做**：`cumsum_loop` 的解释器缺口（`OP-SETIDX`）、`A(i,:)` 行切片、
  按榜单补 `dualize`

## 1.8.8

- **尝试给解释器补 `break`，实测后发现是错的，已回退**（如实记）：
  补上之后 `while2d` 从"未对拍"变成**不一致** —— 解释器算 **12**，而 C 与 Octave
  都是 **6**。说明我的 break 在解释器里没被执行（循环多跑了一轮）。
  "不一致"比"未对拍"更危险（看起来像两边都跑过），按纪律**回退**
- 解释器补了 `OP-SETIDX`（这个是对的），但 `cumsum_loop` 仍判"未对拍"——
  参考实现对该算子仍有缺口，如实保留
- 当前对拍口径：PA1 **17** ／ PA2 **2**（`cumsum_loop`、`while2d`）／ PA3 **0**
- **未做**：`A(i,:)` 行切片（strided 新算子）、按榜单补 `dualize`

## 1.8.7

- **`while` 条件支持表达式**（修掉上一轮记录的那个语义陷阱）：
  条件需要降级时改写成 `while (1) { <降级>; if (<取反>) break; <body> }`，
  保证条件**每轮重算**。`while A(i,2) <= 4` 实测 **6**（= Octave 真值）
- **MIR 新增 `break` 语句**（`mir.rs` 枚举与解析 + `emit.rs` 发射）——
  没有它就无法表达"循环内提前退出"，而上面那个改写正需要它
- 语料增至 **19 个函数**，`while2d` 重新纳入并通过 Octave 真值核对

## 1.8.6

- **`if` / `while` 共用一套条件发射**（`_emit_cond`）：上一轮只升级了 `if`，
  于是 `while A(i,2) <= 4` 直接进 unmapped —— 又是"同一概念两份实现"
- **临时量计数器合并为一个**：条件用 `idx_counter`、循环体用 `n_tmp`，
  各自生成 `__j1` → C 里 `int64_t __j1` 重复定义（gcc: redefinition）
- **发现一个语义陷阱并如实记录**：`while` 的条件若需降级（如 2-D 下标），
  降级语句会被发射到循环**之前**，只求值一次 → 循环里用旧值，表现为死循环或越界。
  正确修法是让 MIR 支持"每轮重算的条件"；本轮时间不足，**未做半截**，
  相关用例（`while2d`）已从语料移除
- **未做**：`A(i,:)` 行切片（strided 新算子）、按 `unmapped_report` 榜单逐行补 `dualize`

## 1.8.5

- **条件里可用 2-D 下标**：`if A(i,2) > y` 现在可转。条件的一侧允许是
  **1×1 数组**（含 `OP-INDEX` 的临时量），发射层取 `((double*)x.data)[0]` 参与比较。
  语料增至 **18 个函数**（`colmax_loop: 6`，与 Octave 真值一致）
- **线性下标降级收敛为一处** `_lin_token`：单独赋值 / 表达式操作数 / 条件
  三个入口共用。此前同一段逻辑有三份拷贝，而"第二下标是数字"这个 bug
  在每份里各修了一次
- 修 `value_expr` 不认**临时量**（`var_dtype` 只记 args/rets/locals）：
  按"已声明但非 i64 → 1×1 数组"处理，未声明的仍如实放弃

## 1.8.4

- **2-D 下标可以出现在表达式里**：`y = y + A(i,2)` 现在降成
  线性下标临时量 + `OP-INDEX` + 二元运算。此前只支持"单独赋值"形态，
  而数值代码里最常见的写法恰恰是把它当操作数。语料增至 **17 个函数**
  （`colsum_loop: 12`，与 Octave 真值一致）
- 修 `scalar_expr` 不认**循环变量**：`setb:__j:i+__l` 里 `i` 是 `for` 变量，
  被判"操作数不是 i64 标量"→ 整函数不可转（与之前 OP-INDEX 同一个坑）
- 新增 **`tools/unmapped_report.py`**：按 `TODO(unmapped)` 条数给函数排行
  （YALMIP 实测：1204 函数中 1163 个有未映射，合计 33582 条；`dualize` 431 条居首）
- **未打通（如实记）**：`if A(i,2) > y` 这类**条件是 2-D 下标**的写法仍不支持；
  `A(i,:)` 行切片（strided）仍需新算子

## 1.8.3

- **发现并修复：`port-ci.yml` 是非法 YAML** —— 步骤名里多了个 `: `
  (`name: Generated project: cmake + ctest`)，GitHub 会直接判 "Invalid workflow file"。
  也就是说**这条 CI 从来没有真正跑过**，而本地门一直全绿
- 五份 workflow 统一在 workflow 级别固定 `PYTHONIOENCODING: utf-8` / `PYTHONUTF8: 1`：
  编码崩溃不该再伪装成被测失败
- 新增 `tests/test_workflows_yaml.py`：所有 workflow 必须可解析 + Python 步骤必须固定 UTF-8
  （两向验证：去掉引号 → 1 failed；还原 → 6 passed）
- 实测 YALMIP 生成物：1204 函数 / **`TODO(shape)` 0** / `TODO(unmapped)` 1343
  —— 说明"形状推不出"在真实工程里不是主要缺口，主要缺口仍是被拒函数
- **未打通（如实记）**：`y = y + A(i,2)`（2-D 下标出现在**表达式**里）尚未降级；
  目前 2-D 下标只支持"单独赋值"形态。`colmax_loop`/`colsum_loop` 因此未进语料

## 1.8.2

- **临时量形状可链式解析**：`resolved_shape` 现在能穿透 `fill:`（`z = zeros(1,3)`）、
  `FLATTEN`、`SLICE`、归约与 `INDEX`，带深度上限。`sum(A(:,2))` 因此可用：
  降成 FLATTEN → SLICE → SUM，实测 **12**（与 Octave 真值一致），语料增至 **16 个函数**
- **形状推不出来时显式失败**：此前 `out_shape` 为 None 会**默认按 `{1}` 分配**，
  运行期表现为"算子写越界/错值"，看起来像算子坏了。现在生成期直接
  `TODO(shape)` + `MLC_UNIMPLEMENTED`，并补齐函数结尾的 `}`
- **门的编码鲁棒性**（本轮真正的坑）：`_run` 未给子进程设 `PYTHONIOENCODING`，
  GBK 控制台编不出 `⇄`(U+21C4) 就抛 `UnicodeEncodeError` —— 门只看到"非零退出"，
  把**编码崩溃误判成对拍失败**。修法：`_run` 统一设 utf-8 + 打印问题项前做编码兜底
- **未做**：`A(i,:)` 行切片（strided，需新算子）

## 1.8.1

- **`while` 累积终于可转**（`while_acc: 10`）。根因是**两个"标量集合"**：
  `i = 1` 只加进 `scalar_names`，而 `i = i + 1` 的判定看的是 `scalars` ——
  于是 `i` 被当成数组，整函数不可转。两份合为一个集合
- **标量声明与赋值成对**：`set:i:1` 首次出现时补发 `var:i:i64`，
  否则发射器不知道它是 `int64_t` 还是 `mlc_array`
- **修 `y = 0` 重复 init**：返回值在函数入口已 init，const/fill 若再 init
  会把第一次分配丢掉（值对、所有权错）。现在只填值不重分配
- 数值语料 15 个函数，`while_acc` 重新纳入并核对通过
- **未打通（如实记）**：`sum(A(:,2))` 的降级 MIR 正确（FLATTEN+SLICE+SUM），
  但**临时量的形状推断**没接通 —— `__c2` 仍被 init 成 `{1}`，
  `mlc_op_slice` 长度校验失败。`col2sum` 因此仍不在语料内

## 1.8.0

- **TP8 扩到全量已实现清单**：`operators.C_IMPLEMENTED` ⇄ `emit.rs::C_IMPLEMENTED`
  交叉核对（16 个算子在册）。上轮正是漏改一份导致 `OP-SETIDX: 未知算子`，
  而当时没有门看得见。两向验证：删掉 Rust 侧一项 →
  `TP8 已实现算子清单不一致：只在算子表 ['OP-SETIDX'] ／ 只在 Rust 无`
- **TP7 增加"期望是否仍是真值"核对**：跑 `numeric_expected.py`，期望过期即判红 ——
  否则"C 与期望一致"可能只是两者一起错
- 归约内运算扩到 `+ - .* ./ *`（`max(x + 1)` 这类归一化开端），
  立即数自动转 `const` 临时量
- 数值语料扩到 **15 个函数**：新增 `for_acc`（for 累积）、`shiftmax`（立即数+归约），
  均通过 Octave 真值核对（`for_acc: 10`、`shiftmax: 5`）
- 修 `y = 0` 当 y 是**数组**时被当成非法标量赋值 → 现在发 `const`
- **已知缺口（未修，如实记）**：`while` 循环里的标量计数器 `i = 1` 会被声明成
  `mlc_array i;` 而触发 `TODO(set)` —— `while_acc` 因此从语料中移除；
  `sum(A(:,2))`（归约里套列切片）同样未支持

## 1.7.9

- **`y(i) = v` 数组元素赋值**（`OP-SETIDX`）：C 侧 `mlc_op_setidx`（1-based、就地写、
  越界 `MLC_ERR`）、发射器特例（目标数组就是 dst，不新分配）、MIR 降级
  （右值 `x(j)` 先取临时量、字面量转 `const`）
- **循环变量即为 i64**：`for i = 1:4  y(i) = x(i)  end` 此前被判成
  "索引 i 不是 i64 标量" → 整函数 unimplemented；现在放行
- 数值语料 **12/12 全部映射、未映射 0**，`cumsum_loop` 实测 `1 2 3 4`，
  期望由 `tools/numeric_expected.py --update` 用 **Octave 真值**写回
- `operators.parse_line` 认识 `y(i) = v`，算子表因此自洽（每个算子都有可解析 sample）

## 1.7.8

- **二维列切片 `A(:,j)`**：降成「`A(:)` 列优先展平 + 切片」，**不需要新算子**
  （FLATTEN 与 SLICE 各自已有 golden 锁着）。语料里 `colmean` 从
  `unimplemented` 变成 `1 3 5`，且 **Octave 与 C 双方确认**
- 新增工具 **`tools/numeric_expected.py`**：`numeric.expected` 由 **Octave 真值**
  生成/核对（`--update` 写回）。手抄期望迟早漂移，而"真值"不该由人抄 ——
  它一上线就发现 `colmean` 那条期望已过期
- 语料 L4 保持 **12/12 与 Octave 一致**（本轮新增了列切片这条路径）
- **未完成**（如实记）：`y(i) = ...` 数组元素赋值仍需新算子 + 发射器特殊形状，
  本轮时间不足，未动；语料也未扩到 25–30

## 1.7.7

- 新增**纯数值语料** `translate/examples/numeric/`（12 个函数）：reduction、
  动态长度（mask/find）、切片、转置、矩阵乘、列优先展平 —— 期望值由 **Octave 真值**
  生成（`numeric.expected`），不是由 C 跑出来的
- **首次拿到函数级 L4**：12 个函数 C 输出与 Octave 完全一致；
  两个函数（`colmean`/`cumsum_loop`）故意保留为 `unimplemented`，锁住"不支持就如实说"
- 修一个高频语法缺口：**`sum(a.*b)` 这类"归约套元素级"** 现在降级为两条语句
  （`__m = a.*b` 然后 `sum(__m)`）。内积/最小二乘/加权和全是这个形态
- 修一个**会产出非法 C** 的 bug：`y = zeros(1,4)` 当 `y` 是返回值时，
  原来会再声明一个同名局部变量（`gcc: 'y' redeclared`），并且把它塞进 free 列表
- TP7 增加数值语料场景（`[TP7] 数值语料：12 个函数与 Octave 真值一致`），
  两向验证：改错期望 → `TP7 数值语料与 Octave 真值不符：[('dotp: 31', 'dotp: 30')]`

## 1.7.6

- **`@类` 目录里的方法显式拒绝**（`reject:method`）：`@sdpvar/sort.m` 定义的是
  **方法分派**，不是对数组排序。此前它被生成成自由函数 `m2c_sort` ——
  与真正的 `sort` 撞名且语义完全不同，**能编译、结果错**
- **struct 整函数拒绝**（`reject:struct`）：C 侧没有字段访问表示，逐行记 unmapped
  会让人误以为"再补几条语句就行"
- 修一处**误判**：注释里的 `% 见 combine.m` 被当成字段访问，导致整个函数被判死刑
- 新增工具 **`tools/shape_suggest.py`**：从 `zeros/ones/字面量/下标上界` 建议
  `% @m2c shape`。实测 YALMIP：**1807 个函数需要注解，只有 9 个能自动推断** ——
  说明注解无法自动生成，只能由人给
- YALMIP 交付物更新：**1043/1204（86.6%）函数被显式拒绝**，
  161 个 `skipped (no shape)`；编译 + `ctest` 通过；`REPORT.md` 增加第八节
  （真实可转换面约 3–5 个函数，以及"继续投入该往哪走"的二选一）

## 1.7.5

- **按源文件拆分 `.c`**：MIR 新增 `# srcfile:`，`m2c` 一个 `.m` 生成一个 `.c`，
  `gen.c` 退化为只做 `#include` 的总装文件。真实工程实测：
  YALMIP **1104 个 `.c`**，`gen.c` 从 **2.1 MB → 46 KB**，整工程编译 **1.1s**
- TP7 增加拆分判据（3 个 `.m` 必须得到 3 个 `.c`，且 `gen.c` < 4KB）；
  **两向验证**：关掉拆分 → `TP7 应按源文件拆成 3 个 .c，实得 0`，`rc=1`
- YALMIP 工程按新格式**重新转换**并交付：`E:\m2c`（含 `yalmip.mir`、`REPORT.md`），
  `cmake` 构建 + `ctest` 通过；运行输出 1204 行，
  `642 skipped (no shape)` + `562 skipped (reject:cell/varargin)`
- 报告如实记录：语句级映射 **2.38%**，L3b/L4 均为 **0**（零注解导致无可驱动函数）

## 1.7.4

- **2-D 下标 `A(i,j)` 支持**：降成列优先线性下标（C 侧零改动，复用已验证的 OP-INDEX）。
  双字面量在生成期算成常量；含变量则用 `setb` 算出 `i+(j-1)*m`。
  演示 `pick2`/`pick2v` 实测 **5**，并由 **L4（Octave）确认** —— PA4 18 → **20**
- **RG5：发版墙钟预算**（>5s 判红）。§9 里那句"发版 ≤5s"从此是判据，不是散文
- **未映射归因细化**：`other` 从 33.4% 降到 **12.2%**（补 struct 赋值/字符串/复杂条件）
- **cell 整函数拒绝**：含 cell 的函数标 `reject:cell`（C 侧无对应表示，永远转不了）。
  YALMIP 实测 **562/1204（46.7%）函数被显式拒绝**（cell 322 + varargin 系列 240）
- 生成物对被拒函数如实写 `skipped (reject:cell)`，不再笼统说 `no shape`

## 1.7.3

- **双栏对照不再静默降级**：没有 `@m2c src` 时，状态栏明确提示
  「按函数体比例估算」，并抽成纯函数 `resolveSyncTarget` 供测试锁定（+4 条判据）
- **未映射语句带原因分类**（MIR 里 `# why:cell|struct|slice2d|control|…`），
  TP5 直接打印归因。YALMIP 实测：struct 21.1% / slice2d 16.4% / cell 11.8% /
  control 5.7% / 块标记 5.6% / 纯副作用 2.3% / other 33.4%
- **L4 只对"可对拍"的函数跑**：`need` 改为"解释器能算出结果"，
  没有对象时**短路**并如实说明 —— YALMIP 从 11.6s 降到 0.3s
- SI 移植线写进**预算与暂停条件**（发版 ≤5s；PA2 连续两轮不降即暂停该线）

## 1.7.2

- **L4 支持多文件工程**：`parity_report --octave --src <目录>` 递归拆函数、
  只落"驱动会调用"的那些，并**排除与内置同名的函数**（YALMIP 自带 `isnan.m`/
  `length.m`，进 addpath 会把 Octave 库自身搞坏，测的就不是我们的代码了）
- 首次对 YALMIP 全工程做 L4：**PA4 已对拍 0 / 未对拍 1204**（如实——没一个够格对拍）
- **`varargin` / `varargout` 显式拒绝**：MIR 新 `reject:` 标记，生成物只出桩并写明原因。
  此前它们被当成一个 `f64` 标量传递 —— **静默变义**，YALMIP 里 **240 个函数**中招
- **删掉 `--help` 输出缓存**（死代码）：实测清空后该文件从未被创建，而 `gate_cache`
  已覆盖同一批结果（冷 3.4s / 热 0.24s）。删掉 base64/原子写/裁剪约 60 行，
  冷启动不变 —— **能证明无用的缓存，不该留着**
- `translate/mir.py` 加 `--selftest`（4 条，正反两向）并接进移植门：
  `sqrt(x)` 不能被当成 `OP-INDEX`，`v(i)`/`v(2)` 必须是

## 1.7.1

- **L4 真值第一次跑起来**：装上 Octave 11.3 后，`parity_report --octave` 把
  **Octave 实跑 ⇄ 解释器**逐值比对 —— 演示工程 **PA4 18 已对拍 / 0 不一致**
  （此前四级证据里 L4 一直是 0 次）
- 移植门加 **TP11**（L4）：有参考实现就跑、没有就打印「PA4 未跑」——
  **第三种状态明确，不混进通过**
- 移植门加 **TP10**：解释器独立复算 **21 个夹具**的期望值（原来 golden 只被 C 验证，
  算子加了而解释器没跟上时无人看守）→ 21/21
- 修一处**语义误判**：`y = sqrt(x);` 曾被识别成 `OP-INDEX`（把函数名当成了下标变量）。
  现在「下标」必须是**已知标量**（i64 参数 / 标量赋值 / 循环变量），否则如实进 unmapped
- Octave 探测覆盖 winget 的默认安装位置（`%LOCALAPPDATA%\Programs\GNU Octave\...`）

## 1.7.0

- 新增 **C/MATLAB 双栏对照**：左 MATLAB、右 C，函数内按行位置跟随；
  优先使用 `m2c` 生成的 `/* @m2c src:N */` 源码行号，缺失时按函数体比例；从 MATLAB 或 C
  任一侧都能发起，映射复用 `matlabc/cbridge`，扩展不重复解析 C
- 双栏对照支持**持久化恢复**：关闭窗口后可从命令面板恢复上次左右文件与位置；
  `.m` 内容哈希与 C 里的 `@m2c source_sha256` 不一致时提示“C 可能过期”，
  防止 source map 指向旧行
- 新增 **MIR 参考解释器**（`translate/mir_eval.py`）：同一份 MIR 用 Python 解释执行，
  与"发射成 C 再编译运行"形成**两个独立执行器**，可以逐值对拍
- 新增工具 **`tools/parity_report.py`**：给出 `PA1 已对拍 / PA2 未对拍 / PA3 不一致`
  三级结论 —— **未对拍如实计数，绝不混进"通过"**
- 移植门加 **TP9**：发版时自动跑一次对拍（演示工程 18/19 对拍、0 不一致）
- 首次把"一致性"拆成四级证据（L1 形态 / L2 自证 / L3a 算子 / L3b 函数级 / L4 MATLAB 真值），
  并明确记录：**本机无 MATLAB/Octave，L4 零次**
- YALMIP 工程对拍结论：**PA1 0 / PA3 0 / PA2 1204** —— 没有任何函数被"两边都算过"

## 1.6.9

- **第一次拿真实工程跑**：YALMIP（1682 个 `.m` / 10.9 万行）→ 1204 个 C 函数，
  `gen.c` 能编译、能链接、`cmake` + `ctest` 通过；语句级映射率 **3.44%**（如实报告）
- 转换器为真实工程补的五处（都是"玩具工程碰不到"的形态）：
  - `--recursive` 递归子目录 + **跨目录重名函数去重**（YALMIP 有 568 个整文件重名）
  - **无返回值函数**（`procedure`）生成桩，而不是让整个工程生成失败
  - **C 关键字避让**（`auto`、`int` 都是合法 MATLAB 变量名）
  - **参数与返回值重名避让**（`function x = f(x)` → 输出改名 `x_out`）
  - **`call:` 的输出也要声明为局部数组**（真实代码里 `B = getbase(Y)` 到处都是）
  - 生成物内部符号统一 `m2c_rt_` 前缀（否则与 `m2c_fix` / `m2c_get` 这类函数名相撞）

## 1.6.8

- **目录级转换（工程级）**：`python translate/mir.py <目录> -o x.mir` 会把目录下所有
  `.m` 一起转换，函数名表取**整个工程** —— 跨文件调用不再被当成"未知名字"
- **TP7**：拿 `translate/examples/proj`（3 个 `.m`，`combine` 跨文件调用
  `addone`/`scale2`）走完整链路：目录转换 → 生成工程 → 编译 → 运行 → 数值对拍
- **TP8**：分配型算子清单的**三处一致性**（算子表 `dynamic` 标注 / Rust `DYNAMIC_OPS` /
  C 的 `*_alloc` 符号）。三处不同步是**静默**错误：算子表说动态、Rust 不知道，
  生成器就会预先 init 一个长度不对的数组
- 契约签名 `TP1–TP7` → **`TP1–TP8`**（五处同步：门签名 / OK 文案 / 契约 / ASCII 树 /
  两份 README）

## 1.6.7

- **动态形状推广到 `find`**：`find(x > 1)` 返回 **1-based 下标**，长度由命中数决定
  （`mlc_op_find_alloc`）。这是第二个动态算子 —— 说明"分配型算子"已经成类，不是特例
- 生成物自测先比**元素个数**再比数值：动态形状下「长度对但内容错」与「长度就错」
  要分开报，否则看到 FAIL 也不知道该查哪
- **TP6（所有权与错误路径）**进移植门：空输入、零命中、长度不符不写入、find 1-based、
  free 后 data 置空 —— 五条都在真编译真跑里验
- `main` 的**批量夹具**纳入 TP5（两个夹具一次跑，40 行逐行比对）—— 手验过的东西没人守
- 契约签名 `TP1–TP5` → **`TP1–TP6`**，同步了 GUARD_CONTRACT、ASCII 树与两份 README
  （这三处不同步就会被 H2a/H2d/P5 抓出来，且这次确实是它们抓的）

## 1.6.6

- **动态形状**：`x(x > 1)` 这类长度由数据决定的算子不再要求人声明形状 ——
  由 `mlc_op_mask_alloc` 按命中数分配，调用方释放。
  这是 ABI「算子只填数据、不重新分配」的**唯一例外**，已在头文件写明理由
- 同一份 `masked` 现在对三组输入都正确（`2 3` / `10 20 30` / `2 3`），
  此前换个输入就是 `error`
- 生成物自测支持**预期失败**断言（`unimplemented` / `error`），
  并补上「期望数值但调用失败 → 判红」—— 负面夹具此前被静默跳过，从没真正执行过
- **形状谎言检测**：声明形状与推断形状不一致时，生成物里留 WARN 注释 + 生成器告警
- `main` 支持**多个夹具文件**：`demo a.txt b.txt`（多于一个时打 `=== 路径` 分隔）
- 生成物自测 60 项（含状态断言）

## 1.6.5

- **逻辑索引** `x(x > 1)` 支持（`mlc_op_mask`）：只认 1-D 且“对自身按常量比较”。
  结果长度是**数据相关**的，所以形状必须声明；C 侧校验「命中数 == 声明长度」，
  不符返回 `MLC_ERR` —— 不截断、不补零
- **`A(:)` 列优先展平**支持（`mlc_op_flatten`）：这不是内存顺序，方阵上最容易看错
- 负面夹具改成**稳定的边界**（cell/struct，out of scope）—— 前几轮每实现一个算子
  就得把负面夹具搬家，那种测试会自我反转
- 台账加**陈旧检测**：`status=verified` 但备注仍写 `UNIMPLEMENTED` 直接判红
  （这轮原本靠人眼发现，现在由门抓）
- 生成物自测的失败信息带上**返回值名**（`pair.P` / `pair.Q`）
- 覆盖率 96.0%；台账 14 条全 verified

## 1.6.4

- **切片**支持：`x(1:2)` / `x(2:end)` 现在能生成（`mlc_op_slice`，1-based 闭区间）。
  2-D 的 `x(1:2)` 在 MATLAB 里是**线性索引**（列优先），语义不同，明确拒绝而不是猜
- 越界边界在**生成时**就拒绝（不截断 —— 截断会让错误静默通过）
- **多返回值 + 多数组**混合函数跑通：`[P,Q] = pair(A,B)` -> `22 28 49 64 | 2 4 6 8 10 12`
- 台账补 `op_slice`（12 条，全 verified），并修掉 `transpose`/`matmul` 的**陈旧备注**
  （它们早已真实现，备注还写着 UNIMPLEMENTED）
- 生成的工程自带 `.gitignore`（`build/`、`*.exe`、`*.o` 等）——用户很可能直接提交它
- TP5 覆盖率下界 0.9 → **0.95**（实际 95.5%，棘轮继续走）

## 1.6.3

- **最后一个 UNIMPLEMENTED 算子也没了**：`mlc_op_transpose` 实现 2-D f64 转置，
  新夹具 `[2,3] -> [3,2]`（golden 14 → 15、C 13 → 15）
- 台账首次达到 **11/11 verified**（此前 `transpose` / `matmul` 一直是 `not_started`）
- `.m` 里的 `x'`（共轭转置）现在也能识别 —— 此前只认 `x.'`，真实代码几乎都写前者，
  于是一律掉进 unmapped
- 负面夹具换成**切片** `x(1:2)`（转置已实现，原来的 `fancy` 不再是边界）
- 生成物多一份 **`fixture.example.txt`**：按参数名给好了值，复制改名就能跑
- `--help` 缓存加上限（24 条）与按时间的清理：派生产物也要有生命周期

## 1.6.2

- 生成的 `main` 与自测支持**多个数组入参**：矩阵乘这类 2 参数函数终于能被驱动
  （此前只有 golden 覆盖，MIR 主流程跑不到它）
- 矩阵乘进了演示链路：`mm(A,B)` -> `mm: 22 28 49 64`，三组夹具都对齐
- `check_translate_port` **自带自证**（`--selftest`，5 条）：比对逻辑必须
  "一致时过、不一致/少行/空输出/缺文件时红" —— 否则门可能永远绿而看不出来
- `--help` 输出缓存**重做并落地**：bytes 存 base64、**原子写**、读写异常一律当未命中。
  上一版因为直接 json 序列化 bytes 而崩、还把缓存截成 0 字节，已回退；
  这次实测坏缓存下门照常通过并自愈（3.45s 冷 / 2.87s 命中）
- 生成物 README 补"怎么找到 c_runtime"的可执行片段（find / PowerShell / 环境变量）

## 1.6.1

- **矩阵乘真实现**：`mlc_op_matmul` 支持 2-D f64（此前是 `MLC_UNIMPLEMENTED`），
  新夹具 `[2,3] × [3,2]`（golden 13 → 14、C 12 → 13）
- `.m` 里的 `*` 现在按**形状**区分：两个操作数都是 2-D 且内维匹配 → 矩阵乘，
  写 `.*` → 元素级。内维不匹配在**生成时**就拒绝，不留给运行时
- 生成的工程多一份 **README.md**：怎么 cmake、`MLC_RUNTIME` 怎么传、ctest 怎么跑、
  夹具文件怎么写、哪些文件是生成物
- 负面夹具：`fancy` 现在可驱动但不返回数值 —— 期望里要求它是 `unimplemented`，
  用来验证"该拒的确实拒了"（此前只验证"该算的算对了"）
- 顺带修：fidelity 的 matmul 参考实现假设 `data` 是嵌套列表，而夹具早就是扁平的 ——
  一旦有夹具就会错，只因一直没夹具才没暴露

## 1.6.0

- **多维常量**：`zeros(1,3)` / `ones(2,3)` 现在能生成（MIR `fill:` 带真实形状，
  与标量 `const:` 区分）—— 真实工程的初值多是矩阵
- 生成的工程在 CI 里跑 **真实 `cmake + ctest`**（此前只 `gcc` 编译单文件）
- 发版历史新增 `detail`：记录移植门的**覆盖率与是否快检** ——
  否则“变快”分不清是快检还是真优化
- `check_help_contract` 冷启动 **5.1s → 3.3s**：AST 按源码内容缓存
  （同一份源码被 5 个判据各解析一遍，实测 208 次 `ast.parse` 降到几十次）
- 修两处会产出错代码/错数字的问题：`sum(z)` 在表达式降级里被当成**下标**；
  `ops` 计数漏算降级产生的算子（覆盖率因此偏低）

## 1.5.9

- **立即数参与数组运算**：`r = v * 2` 会被降成 `const:__k1:2` + `OP-MUL`
  （MATLAB 里标量就是 1×1 数组；算子签名只认 `mlc_array`，所以给它一个实体）
- 生成的 `CMakeLists.txt` 会**自动探测** mlc 运行时（`-DMLC_RUNTIME` > 环境变量 >
  常见相对位置），探测不到才报错，并给出可直接照抄的修复命令
- `check_translate_port` 支持 **`--fast`**：发版走快检（0.3s，不编译不运行），
  CI 仍跑全量（7.4s）；快检时输出**如实写「C 未跑（快检）」**，不是「0/11 通过」
- TP5 覆盖率下界 0.8 → **0.9**（棘轮：实际已 90.9%）
- 修 `r = v * 2` 被误判成**标量赋值**：`setb` 只能用于 `i64` 左值，
  否则生成的 C 里会出现 `mlc_array = ...` 这类非法算式

## 1.5.8

- **数组累加**能生成了：`r = r + v(1)` 会被降级成"取元素 + 相加"两条语句
  （MIR 没有嵌套表达式，硬塞进去等于把求值顺序藏进发射器）
- 函数调用加了**签名校验**：参数个数、`i64` 与数组的类型不符都会被拒绝并写明原因
- 生成物自带的自测支持**多组夹具**（`--case 夹具=期望` 可重复）：
  `ctest` 现在跑 3 组输入 × 10 个函数 = **30 项**，包含 `if` 的 else 分支
- `check_translate_port` **进了发版清单**（第 16 道门）——移植链路已是最活跃的子系统，
  只放在 CI 里跑，改它的人跑一次发版会看到"假全绿"
- 慢门 [!] 加了**带理由的白名单**（`SLOW_OK`）：`check_translate_port` 要真编译并
  运行生成的 C 工程，6s 属于正常 —— 否则警告天天亮，很快就没人看
- 修了 `check_release_gates` 的**失败路径崩溃**：`problems` 早已是字符串，
  还在按元组解包 —— 只在"真有问题时"触发，用 traceback 顶替了报告

## 1.5.7

- MIR 支持**标量赋值**（`i = 1`、`i = i - 1`）与 **`setb`** 整数二元运算；
  于是 `while` 真的能跑起来（`lastpick` 递减下标后取第一个元素）
- MIR 支持**同文件函数调用**：`s = sumall(v)` 生成 `m2c_sumall(v, s)`，
  并校验"被调函数确实在本文件里"
- 生成的工程**自带 C 自测**（`src/selftest.c` + `enable_testing()`）：
  期望值在构建时嵌入，`ctest` 一条命令就能验，不需要 Python
- TP5 多报**算子分布**与**函数间调用数**（`OP-ADD×3、OP-INDEX×3、OP-SUM×3`）
- 修了一个会**静默丢代码**的解析 bug：`.m` 的函数体在第一个 `end` 就被截断，
  于是 `while`/`if` 之后的语句整段消失

## 1.5.6

- MIR 改成**语句树**：`for` / `if` / `while` 可以任意嵌套
  （此前是三个平铺列表，"这条语句属于哪个块"只能靠下标猜）
- MIR 新增 **`while`**；`.m` 侧的 `while i < 3` 会照同一套条件语法识别。
  样例故意不含 while —— 本版没有标量赋值语句，真写进去会变成死循环
- 生成的 `main` 改为**夹具文件驱动**（按参数名给值，`x = 10 20 30`），
  不再靠"参数按位置排"这种隐式约定
- TP5 多报一行**确定性覆盖率**（`8/9 = 88.9%`），并设下界 80%（只许升）
- 新增 3D 广播夹具 `[2,1,3] + [1,4,1]`（golden 12 → 13，C 10 → 11）
- TP5 运行生成程序带 60s 超时：生成物若有死循环，门判红而不是陪着等

## 1.5.5

- **真广播**：`[2,3] + [3]`、`[3,1] + [1,4]` 这类按尾维对齐的隐式扩展现在能算了
  （C 运行时、Python 参考实现、Rust 形状推断**同一套规则**），并新增 2D 广播夹具
- MIR 支持 **`if/else`**（只收标量与整数的六种比较，其余进 unmapped）
- MIR 支持**多返回值**：`function [y, s] = f(x)` 生成两个输出参数，main 打印时用 `|` 分隔
- 生成的 `main` 改为 **argv 驱动**：`demo 10 20 30 3` 会把值填进数组与下标，
  每个函数各自独立消费参数（不足则退化为 `a[i]=i+1`）
- TP5 现在跑**三组输入**（默认 / `10 20 30 3` / `1 2 3 1`），
  第三组专门覆盖 `if` 的 **else** 分支

## 1.5.4

- 生成的 C 工程**真的能跑出正确数值**了：`addone: 2 4 6` / `pick: 2` / `sumall: 6`
  —— 此前只验到"能编译"，而 `mlc.h` 要求调用方先初始化 `out` 的 dtype/形状，
  发射器没做，跑起来是垃圾值
- MIR 支持**形状**（`arg:x:f64:3`）与 **`for` 循环**（`for:i:1:3`），
  `.m` 侧用 `% @m2c shape x 3` 显式标注（不猜形状）
- `OP-INDEX` 支持**立即数下标**（`v(3)`），此前只支持变量下标
- 生成的 `main.c` 真正接线：按 `a[i] = i+1` 构造输入、调用每个函数并打印结果
- TP5 从"能编译"扩到**能跑对**：编译 → 链接 → 运行 → 与
  `translate/examples/demo_port.expected` 逐行比对（改错一个数字立刻红）

## 1.5.3

- 新增 **Rust 移植发射器** `rust/m2c`（纯 std、零依赖）：MIR → C 工程
  （`.h` + `gen.c` + `CMakeLists.txt` + `main.c` 骨架），同一 MIR 两次发射逐字节一致
- 新增 `translate/mir.py`：`.m` → MIR，**复用既有算子表**（不重复定义算子）
- 移植门扩到 **TP1–TP5**：多验一条"整条链路产出的 C 真能被 gcc 接受"
  （此前只验算子级调用，没有任何东西证明生成物是合法 C）
- `OP-INDEX` 支持**变量下标**（`v(i)`，此前只认 `v(2)`）
- ADR-009 落档：**Rust 只负责"把 MATLAB 变成 C"这台机器，交付物仍是 C**

## 1.5.2

- **大纲修复（脚本）**：脚本文件没有 `function` 时，不再显示内部伪符号
  `<script>` 或空白；改为按 `%%` 分节列出，无分节时显示文件名本身。
  服务端（`matlabc_lsp.py` 的 `_script_symbols`）与客户端兜底保持同一形态。
- **新增 site 级 HTML 文档**：命令 **`matlabc: 生成工程站点（site 级 HTML 文档）`**，
  调用 `matlabc.py --browse` 输出多页站点到 `.matlabc/site/index.html`
  （源码页 / 函数详情 / 调用图 / 目录与规则索引），可点击跳转、可分享。
- 修复仓库内调试时找不到 `matlabc.py`：三个报告/站点命令统一走
  `findMatlabcPy()`，依次尝试 LSP 同目录、扩展根、仓库根与工作区。
- `vscode/test_extension.js` 的 mock 补全 `extensionPath` 与常用 vscode API，
  测试重新可用（8 条断言）。

## 1.5.1

- 新增命令 **`matlabc: 生成工程 HTML 报告`**：一条命令出整份报告（调用图内嵌），
  写到 `.matlabc/report.html`，完成后可直接在浏览器打开 —— 以前只能去命令行敲
  `python matlabc.py <dir> --html out.html`
- 另外两道门也接上增量判定（`check_subprocess_hygiene` 2.6s、`check_figure_glyphs` 1.1s），
  命中后各自只要 0.2s 左右
- `gate_cache` 自带 7 条自证（无关文件不影响指纹 / 相关文件必失效 / 失败不缓存），
  并纳入发版必跑清单
- `--trend` 多一列**增量命中数**；发版历史每次也记下来
- CONTRIBUTING 补一条：改 JSON 用文件脚本，别用 `-c` 内联（引号会被 shell 吃掉）

## 1.5.0

- 增量判定抽成公共件 **`tools/gate_cache.py`**，`check_help_contract` 也接上了：
  最慢那道门 **6.2s → 0.36s**（指纹覆盖入口脚本、门脚本、文档与配置）
- 发版日志的汇总行多说两件事：**几道门增量命中**、**并行收益**
  （`5.7s，8 路并行，13 道增量命中，各门累计 13.2s → 墙钟 5.7s（2.3× 收益）`）。
  用「各门累计 ÷ 墙钟」而不是 CPU 时间 —— 后者在 Windows 上取不到，
  而一个只在部分平台有值的指标，迟早会被误读
- 新增 **`python tools/release.py --trend`**：列出每道门最近 20 次的中位/最大/最近耗时

## 1.4.9

- `check_py36_clean` 支持**增量**：整仓 `.py` 的指纹（含检查器自身）没变时
  复用上次的"通过"结论，3.9s → **0.18s**；只缓存通过，失败每次重算
- 发版日志多一行**总时长走势**（最近几次 `13.5 → 4.9 秒`），退化一眼可见
- 并行跑门时，失败详情**每行带门名前缀** —— 多道门同时红时不至于分不清
- `--jobs` 默认按 CPU 核数（上限 8），不再写死 4
- `releases/.py36-cache.json` 是本地缓存，已加入 `.gitignore`

## 1.4.8

- **发版时 15 道门并行跑**：串行 13.5s → 并行 4.8s（输出仍按原顺序打印，
  汇总行会写明用了几路）
- 门耗时开始**留趋势**（`releases/gates-history.jsonl`）：某道门比自己历史中位数
  慢 1.5 倍以上会被点名 —— 单次数字看不出退化，趋势能
- `patch_text --plan` 支持 `"optional": true`：这类补丁失败只记录，不算整批失败
- 状态栏的缓存统计多了**平均耗时**（命中不代表快，得看时间）

## 1.4.7

- 最慢的门**从 5.3s 降到 4.2s**：`check_help_contract` 的 `--help` 改成**并发预取**，
  并给 `_docstring` 加了按 (路径, mtime, 大小) 的缓存（同一文件原来被解析十几次）
- 发布日志里，冠军门超过 5 秒会标 **[!]** 并提示「值得优化」
- `patch_text --plan` 支持 **`--fail-fast`**（默认继续跑完，出错即停可选）
- 状态栏的缓存计数改为**本次启动累计**，重扫时归零 —— 只增不减的数字说明不了任何事

## 1.4.6

- 状态栏菜单多一项 **大纲缓存：命中 / 旧版失效 / 无缓存**，点一下清空并重扫 ——
  缓存行为从"只在导出日志里"变成"抬头就能看"
- 关系面板的**根节点**也能右键「跳到定义处」了（子节点早有，根没有，
  最上面那行等于点不动）
- `patch_text --plan` 的输出改成**表格**（`# / 文件 / 命中 / 结果`），
  批量改十几个文件时能一眼扫完
- 发布日志多一行**最慢的三道门**（耗时数据本来就有，一直没被看）

## 1.4.5

- 关系面板**下游**也能展开「共 N 处调用」了（与上游对齐）：
  服务端现在给出该被调用者的**全部**调用点，而不是只留最小行号
- `tools/patch_text.py` 支持 **`--dry-run`**：批量改之前先看每处命中几次
- 判据 RG3 增加**过期提示**：某道门超过 30 天没跑过会提醒（只提示、不判负 ——
  逼着人为凑一次发布是更坏的结果）
- `releases/gates-last-run.json` 明确**入库**并在 CONTRIBUTING 说明理由与代价

## 1.4.4

- 关系面板**下游也带代码片段**了（`被调用 f · line 12 · y = f(x);`），
  与上游一致 —— 只有一侧带片段，信息量就不一样
- 大纲缓存有了**可观测计数**（命中 / 旧版失效 / 无缓存），导出日志里带一行
- `tools/patch_text.py` 支持 **`--plan` 批量补丁**（一个 JSON 改多处），
  并修掉一个真缺陷：锚点没做换行归一，CRLF 文件配 LF 锚点必然「没命中」
- 新增判据 **RG3**：每道门都要在 `releases/gates-last-run.json` 里有跑过的记录 ——
  「存在但半年没跑」与「不存在」在效果上一样

## 1.4.3

- 大纲用到缓存/本地扫描时，状态栏会**说一句**（`大纲 … 改用同版本缓存`），
  30 秒最多一次 —— 之前只写日志，用户不知道自己在看哪来的结果
- 关系面板「共 N 处调用」的子项现在**带那一行代码片段**
  （`调用处 line 12 · y = f(x);`），不必点进去才知道是不是要找的
- `matlabc: 导出日志` 超过 512 KB 自动压成 `.log.gz` —— 纯文本动辄几 MB，
  作为附件常被邮件网关拒
- 新增一道门 **`check_tool_selftests`**：声明 `SELFTEST = True` 的工具，
  每次发版都真跑一遍（工具的自证也得有人执行）

## 1.4.2

- 大纲**缓存只认同一版本**：文档刚改过时不再拿旧符号顶上去 ——
  「过期的正确结果」会让跳转落在错地方，比空白更误导
- 关系面板「共 N 处调用」现在**可以展开**：每一处调用行都是一个可点的子项
  （只报数字等于告诉用户"还有两处，自己找"）
- `matlabc: 导出日志` 末尾附上**服务端 stderr 最近 50 行** ——
  Python 的崩溃现场在那里，扩展日志里只有"请求失败"

## 1.4.1

- 大纲多了一层**缓存兜底**：服务端这次给不出（超时/未就绪）时，先用上次的结果，
  不再退回「只有 function 行」的本地扫描（那会把类和嵌套函数全丢掉）
- 新增命令 **`matlabc: 重新扫描大纲`**：清缓存重扫一次，报出符号数与耗时
- **`matlabc: 导出日志`** 现在开头带环境信息：扩展版本、VS Code 版本、系统、
  `pythonPath`、LSP 连接状态、工作区、`.m` 文件数 —— 报障时不必再问一遍
- 关系面板同一函数**从多行调用**时，行尾标「共 N 处调用」
- 判据从 SR1–SR2 扩到 **SR1–SR3**：`mfile.lines` 本身必须等于真实行数
  （它就是上一轮越界的源头；只查函数等于只查症状）

## 1.4.0

- 关系面板每行现在同时写清**两个位置**：左键去调用处，右键 **「跳到定义处」**
  （行尾写着「定义 N」，想看定义不必再按 F12 找一遍）
- **修大纲一直转圈的根因**：`mfile.lines` 在文件以换行结尾时比真实行数多 1，
  于是 EOF 处结束的函数得到越界行号，编辑器**拒收整批符号** ——
  之前客户端钳制只是兜底，这次修在源头
- 大纲日志区分「请求超时」与「服务端返回 0 个」，并在兜底占位里写明原因
- 新增命令 **`matlabc: 导出日志`**：把日志存到指定位置，报障时直接发
- 新增一道门 **`check_symbol_ranges`**：对着真实语料检查每个符号的起止行是否越界

## 1.3.9

- 修**跳转位置**：关系面板里「调用者」那一行显示的是 `line 8`（调用处），
  点下去却跳到函数定义处（`line 23`）—— 现在**点的就是显示的那一行**
- 「被调用」同样修：点它跳到「我这里调用它的那一行」，而不是它的定义处
- 修**大纲一直转圈**：越界/不合法的符号范围会让编辑器拒收整批符号，
  表现为「正在加载…」永远不停；现在行号钳制在文档内，兜底扫描也保证
  选区落在范围内

## 1.3.8

- 改动记录视图最上面多一行 **「回滚原因：调用边数变了（1 次）」** ——
  把本会话最常踩的坑直接摆出来（以前只在命令行与 AI 那边能看到）
- 「偏慢」的判据变成可配：`matlabc.slowTaskFactor`（默认 2 倍）与
  `matlabc.slowTaskMinMs`（默认 200ms）
- 新增 `matlabc_task.py baseline --save`：记住每类任务「平时多快」，
  之后 `stats` 会列出比基线慢一倍以上的类型
- `tools/new_gate.py` 生成的骨架自带**两向自证**（好样本过 / `__bad__` 必红），
  不再是恒真占位

## 1.3.7

- `stats` 接进 MCP（第 **23** 个工具）：AI 也能回答「这类改动通常多快」「这次为什么没成」
- 统计里多了**回滚原因排行**（哪条验收判据最常让人失败）
- 改动记录可**按耗时排序**，明显偏慢的那次带 `watch` 图标标「偏慢」——
  判据是「超过**同类**中位数的 2 倍」，不是全局阈值
- `tools/new_gate.py` 生成后会**跑一次骨架自检**（主检查 + 自证），
  生成完立刻知道它能不能跑起来

## 1.3.6

- 回滚记录现在带**原因**：点那一行就能看到「调用边数变了」这类结论 ——
  以前只知道"回滚过"，不知道为什么
- 视图标题显示本会话汇总：**「本次会话 3 成功 / 1 回滚」**
- 记录视图的耗时有了第二个用处：`matlabc_task.py stats` 按任务类型给出
  次数 / 回滚数 / 平均 / 中位 / 最大耗时，可以做基线
- `tools/new_gate.py` 新增 `--fix-counts`：连散文里的「N 道门」一起改
  （只改 ≥20 的数字 —— 试跑时它差点把「8 gates」也改成 36）

## 1.3.5

- 改动记录每行显示**耗时**与**结果**：`✓ 0.4s` / `× 回滚 0.1s`
- **没改成的那次也留痕**：验收不过时任务会自动回滚，但现在会记一条「回滚」——
  「我刚才那次到底成没成」终于有地方可查（回滚记录不提供撤销）
- 撤销确认里文件较多时，多一个 **「全部打开 diff」**（不再受设置项截断）
- 字形检查扩到 README 与更新日志（技术记号按「渲染端回退」登记理由）
- 新增 `tools/new_gate.py`：生成新门骨架，并自动登记到必须出现的那五处

## 1.3.4

- 改动记录里**同一文件的多次改动会折成一个可展开节点**（`solver.m  3 次`）——
  一次重构常常连着改同一个文件，平铺时看到的是好几行很像的记录
- 新增设置 **`matlabc.undoDiffLimit`**（默认 8，1–40）：撤销前最多打开几个并排 diff
- 字形检查扩到**手册正文**（FG4）：`⇢` 换成 `→`；`✓ [!] ✗` 属于引用界面真实文本，
  进带理由的允许清单（登记了却已不在文中同样算红）
- 新增一道门 **`check_release_gates`**：`check_*.py` 要么在发版清单里，
  要么带理由豁免 —— 此前"写了却从没在发布时跑过"是唯一静默的漏洞

## 1.3.3

- 改动记录支持**按文件过滤**：`matlabc: 按文件过滤改动记录`，标题会写成
  「改动记录（3/12）· 只看 solver」，一眼看出是过滤后的结果；另有清除命令
- 撤销确认里写清「共 N 个文件、已打开前 M 个 diff」—— 文件多时不再让人
  以为只动了一个
- 字形检查扩到导览页（FG3）：顺带抓出页面里的 `⏸` 在部分平台会变方块，
  已换成纯文字
- CONTRIBUTING 新增「新增一道门要同时改的六处」，每处都写明不改的症状

## 1.3.2

- 改动记录每行显示**动了哪些文件**（多于两个时显示「等 N 个」）—— 只写类型与时间，
  多文件工程里根本分不清是哪次
- 「更早」按天折叠（`2026-10-19 · 3 次`）
- 新增命令 **`matlabc: 按 id 撤销改动`**：手上有 id 时直接撤（会读剪贴板并校验格式）
- 新增一道门 **`check_figure_glyphs`**：图上要画的字必须在字体里有字形 ——
  「中文/符号渲染成方块」这套图已经出现过三次，靠肉眼看截图不可靠

## 1.3.1

- 改动记录视图分两组：**本次会话** / **更早**（后者默认收起）——
  50 条平铺时，最常看的"刚才那几次"反而最难找
- 每一行有**右键菜单**：撤销这一次改动 / 查看这一次改了什么（只看不动）/ 复制记录 id
- 撤销确认的 diff 顶部多了 **「取消」**，不用切回弹窗或关标签页
- 使用说明 7.3 补记录视图的示意图与右键菜单说明；命令 16 → 19

## 1.3.0

- 并排 diff **顶部多一行「确认撤销这次改动」**：看完直接点，不必切回弹窗
- 「查看这段提交」改成**可点列表**：选中某次提交就打开它的改动
- 侧栏新增 **改动记录** 视图：每次改代码一行（类型 / 时间 / 文件数 / 是否已撤销），
  点还处于可撤销的那一行即可撤销
- 使用说明补「撤销没通过时是什么样」，并说明记录视图

## 1.2.9

- 撤销预览改用编辑器**自带的并排 diff**（左＝当前文件，右＝撤销后），
  可以直接逐行看差异、折叠上下文 —— 不再是纯文本
- 确认框多了「查看这段提交」：列出任务之后仓库新增的提交，方便对照
- 使用说明 7.1 补流程图；7.2 说明并排视图与提交对照

## 1.2.8

- 撤销现在**先给 diff**：执行前把"将被改掉的（红）/ 将恢复的（绿）"摆出来，
  确认后才动手 —— 只报"将恢复 N 个文件"不足以下决定
- 「撤销上一次改动」也进了**状态栏菜单**（点右下角 `✓ matlabc` 就能看到）
- 任务记录里存下当时的 git 提交；若仓库已往前走，撤销时会**提醒一句**（不阻止）
- 使用说明 7.2 配上撤销确认的示意图

## 1.2.7

- 新增命令 **`matlabc: 撤销上一次改动`**：改代码这件事终于有了编辑器里的入口 ——
  先告诉你会恢复几个文件，确认后才撤；有冲突就拒绝并说明原因
- 撤销后的验收**不再只报数字**：不通过时会说明差在哪、可能是什么原因
  （文件不完整 / 调用点没恢复 / 与当前工程不匹配），并提示可退回 git
- 撤销记录改为**压缩存储**（实测约占原文件的 9%），50 条上限更耐用；
  旧记录仍然可读
- 使用说明新增第 7 节「改代码有验收、也可以撤销」

## 1.2.6

- 任务记录**有上限了**：`.matlabc/tasks/` 最多保留 50 条，每次记完自动裁剪，
  而且**先删已撤销的** —— 只有删光仍超限时才会动"还能撤"的记录
- 新增 `matlabc_task.py prune --keep N [--apply]`：需要时手动收一次

## 1.2.5

- AI 助手的 `matlabc_task_undo` 现在支持 **`list`**（看过都做过什么）与
  **`batch`**（一次撤掉整批）—— 与命令行同一套语义，工具数仍是 22

## 1.2.4

- 撤销之后**自动验收**：重新分析并要求结构回到任务前（函数数 / 调用边 / 诊断），
  不达标就把「撤销」本身也退回去 —— 不会留下一个"撤了一半又不对"的工程
- 任务记录里现在保存任务前的结构快照，作为撤销的验收标准

## 1.2.3

- `undo --batch`：**整批一次撤完**。`batch` 本来就是一个事务，撤销也该是一次
- 整批撤销是**原子**的：先在内存里把 N 步倒推成"最终应有的状态"，全部校验通过才落盘；
  任何一个文件有冲突就整批不动（此前逐条撤，第 2 条冲突时第 1 条已经写回去了）

## 1.2.2

- `undo` 支持 **`--list`**（看过都做过什么）与 **`--id`**（撤指定的那一次）：
  多步任务现在能按记录逐条撤回，而不是只能撤最近一次
- 乱序撤销会被拒绝：撤较早那条、而较新的任务也改过同一个文件时，
  工具明确说"会覆盖任务之后的改动"，而不是悄悄盖掉

## 1.2.1

- `undo` 接进 MCP（第 **22** 个工具）：AI 助手现在也能「改完反悔」。
  默认只算不写（先看会撤哪些文件、有没有冲突），确认后再真撤；
  返回里带 `verdict`（`plan` / `undone` / `conflict` / `nothing`）

## 1.2.0

- 任务层新增 **`undo`**：撤销**上一次**任务。失败的任务本来就会自动回滚，
  这条是给「成功了但想反悔」用的 —— 以前只能靠 git，而刚跑完任务时通常还没提交
- 撤销前会校验每个被改文件**在任务之后没被编辑过**；有改动就拒绝并列出是哪个文件，
  而不是静默覆盖
- 任务记录落在工程内的 `.matlabc/tasks/`（可随时删掉，删了就失去撤销能力）

## 1.1.9

- 使用导览从 8 步扩到 **10 步**，补上两件这一年最该讲的事：
  **⑦ 让 AI 真的去改（带验收、可回滚）**、**⑩ 出问题时怎么办**（状态栏 → 重启 → 日志）
- 文档里「8 步动画」的旧说法与示意图一并改为 10 步

## 1.1.8

- 重启服务后**自动重推已打开的文档**：不用再手动关掉重开文件，诊断与关系立刻回来
- 修「查看日志」指错路径（原来指向扩展目录下的 `matlabc.log`，那个文件不存在，
  于是这条命令永远只会说"还没有日志"）
- 日志超过 1MB 自动滚动一份 `.1`，长期使用不会无限增长
- 手册 FAQ 补「扩展好像没在工作，怎么查」三步：看状态栏 → 重启服务 → 查看日志

## 1.1.7

- 状态栏点一下变成**菜单**：重新启动服务 / 更换 Python 解释器 / 打开使用说明 / 查看日志
- 新增两条命令：**`matlabc: 重新启动服务`**（索引卡住、刚改过设置时用，
  只重启分析服务，**不重开窗口、不丢未保存的编辑**）、**`matlabc: 查看日志`**
- 命令数 11 → 13

## 1.1.6

- 新增**状态栏**：`✓ matlabc`（就绪，悬停可看用的哪个 Python 与版本）／
  `[!] matlabc`（版本过低、启动失败，悬停给出原因）—— 点一下即可更换解释器。
  扩展出问题时，用户终于有东西可看、可点
- 选 Python 时会**把上次用过的排到最前面**并标注「上次用的」

## 1.1.5

- 选 Python 时，候选会**真跑一次**：用该解释器解析本扩展的服务端源码。
  版本够但环境坏了（缺标准库 / 装残了）会标成「无法运行本扩展」并拒绝选用
  —— 此前这种情况要等启动后崩掉才发现

## 1.1.4

- **认版本**：探测改成扫目录（能扫到任意 `Python3.x`，不再写死 3.6~3.13），
  列表里标出每个候选的版本；选了 2.7 / 3.5 这类过老的版本会**直接提示版本过低**
  （要求 3.6+，推荐 3.10+），而不是让它以语法错误崩在后台
- 启动前也会验一次版本：太旧的 Python 给的是「版本过低」，不是一串看不懂的报错

## 1.1.3

- `matlabc: 选择 Python 解释器` 现在会**先自动探测**本机常见安装位置
  （官方安装器 / conda / 微软商店 / Homebrew / pyenv），列出并标上版本；
  列表里没有就点「手动选择」
- 起因：很多人的 Python 装了但不在 PATH 里（安装器的 "Add to PATH" 默认不勾），
  让他们"去设置里填绝对路径"等于让他们自己翻磁盘

## 1.1.2

- 装好之后会说一句：这个版本第一次成功启动时弹「matlabc 已就绪」，
  带「打开使用说明」「看导览」两个按钮（每版只弹一次）
- **Python 起不来时立刻给可操作提示**：原来要等 15 秒超时才报一句
  「启动失败：timeout」，现在 7 毫秒就知道是 ENOENT，提示里直接给
  「选择 Python 解释器」「打开使用说明」两个按钮
- 手册新增两节：**装好之后会看到什么**、**设置 Python 路径**（两种方式 + 说明
  默认值 `python` 不是错误）

## 1.1.1

- 多步任务的步骤之间可以**互相引用**：`${prev.new}` / `${1.new}`，
  不用手抄上一步改出来的名字
- 引用在**动手之前**整批解析完：写错引用不会有任何文件被改
  （第一版是边跑边解析，第 2 步写错时第 1 步已经落盘了）

## 1.1.0

- 多步任务现在**命令行也能用**：`matlabc_task.py batch --steps plan.json`，
  计划同样在副本上推演、执行同样整批回滚
- 批量逻辑只保留一份（MCP 侧改为调用同一实现），避免两处语义漂移

## 1.0.9

- AI 改代码支持**多步任务**：一次传一串步骤（改名 → 提函数 → 搬文件），
  按顺序执行；**任一步失败就回滚整批**，不会留下"改了一半"的工程
- 多步的"计划"是在**副本上推演**出来的：链式第二步依赖第一步的结果，
  逐步 dry-run 会误报失败
- 新增 3 个端到端场景（批量执行 / 批量回滚 / 批量计划），全场景 72 → 75

## 1.0.8

- 手册第 6 节重写：**MCP 怎么配**（命令生成 → 各客户端配置文件位置 → 重启 → 怎么验证
  接上了）与**六个常见用法**（摸清工程 / 看影响面 / 为什么跳不过去 / 先要计划 /
  回归清单 / 让它真的去改）
- 修一个真 bug：生成 MCP 配置时读的是 `cfg.get('python')`，那个键不存在 ——
  用户设了 `matlabc.pythonPath` 也读不到，生成的配置永远是 `python`

## 1.0.7

- 使用说明开头新增两节：**它解决什么问题**（接手陌生工程时卡住的四件事）、
  **支持什么**（诊断 / 跳转 / 关系面板 / 影响面 / 跨语言 / 热点 / 报告 / AI 接入，逐条说明）
- 运行环境单独成一节：VS Code 1.60+、Python 3.6+、Windows / Linux / macOS 同一个包
- PDF 同步重排（10 页）

## 1.0.6

- 新增命令 **`matlabc: 选择 Python 解释器`**：挑一个 `python.exe`，**当场试启动**，
  能起来才写进设置，然后提示重载窗口 —— 不用再手填路径
- 设置项 `matlabc.pythonPath` 的说明写清了这个入口与填写示例
- 修一处自救缺口：以前「找不到 matlabc_lsp.py」会直接中断启动，导致
  「打开使用说明」「选择 Python 解释器」这些命令**根本不存在**；现在起不来时也能用

## 1.0.5

- 手册「找不到 Python」的解决办法改成**在插件设置里配置**（`Ctrl+,` → 搜 `matlabc`
  → 填 `matlabc.pythonPath` → 重载），不再让人去跑命令行
- 安装后的设置一节补了同样四步，照着做即可

## 1.0.4

- 手册开头去掉一段关于"本手册讲什么"的自我说明，直接从"你需要什么"开始

## 1.0.3

- 用户文档统一收进 **`releases/docs/`**：手册源文件、PDF、4 张示意图同目录，
  另附一份该目录的说明（改手册流程 + 打包映射）
- 包内保持相对结构（`extension/USER_GUIDE.md` + `extension/figures/`），
  手册里的 `figures/x.png` 安装后仍然能找到图

## 1.0.2

- 新增 **使用说明 PDF**（8 页，4 张示意图直接印在页面上）：命令
  `matlabc: 打开使用说明（PDF）`，打开就是最终排版，也适合转发
- 手册与扩展页同步写上 PDF 入口；命令数 9 → 10

## 1.0.1

- **手册和示意图现在有入口了**：扩展页顶部新增「文档在哪」，直接指向
  `USER_GUIDE.md` 与 `media/guide/`；根目录两份 README 的快速开始也加了指引
- 起因：手册与 4 张图早就打在包里，但 README 一处都没引用 —— 文件存在、
  用户找不到，等于没有
- 新增一条门：扩展页必须能链到用户手册，否则红

## 1.0.0

- 使用说明补 **4 张示意图**：CodeLens 与跳转、关系面板、命令面板、热点排行
  （按真实界面绘制，不是屏幕截图 —— 截图会随主题/字号/机器漂移，还常带着作者
  自己的工程路径；图由脚本生成，可随时重跑）
- 手册里每张图都注明「示意图」，不冒充截图

## 0.9.9

- 使用说明补上**任务级改代码**（重命名 / 提函数 / 搬函数）：每一步都在动笔之前
  把验收条件列出来，改完逐条核对，不过就自动回滚；也说明了它的边界
  （管结构不管业务语义、自动推断是启发式）
- 说明开头补「你需要什么」：VS Code 1.60+、Python 3.6+、不需要装 MATLAB
- 常见问题补两条：改坏了怎么办、怎么自己复核

## 0.9.8

- 任务层新增 **`move`**：把整个函数搬到独立文件（定义搬走、调用点保留），
  验收 = 工程函数总数不变 / 诊断不增加 / 定义真的迁移了
- 目标必须叫 `<name>.m`——换个名字它就变成文件内私有子函数，**所有调用点会静默失效**，
  所以这一条在动手之前就被拒

## 0.9.7

- `extract` 支持 **`--to`**：把选中的一段提到**独立文件**（不再只能做同文件局部函数）；
  新文件先写、原文件后改，回滚时新文件一并删除；目标已存在则拒绝覆盖
- MCP 的两个任务工具同步支持该参数

## 0.9.6

- 任务层接进 MCP：AI 助手现在能调用 **`matlabc_task_plan`**（只读，先给计划和验收
  条件）与 **`matlabc_task_apply`**（写入 → 重新分析 → 逐条核对 → 不过自动回滚）
- 此前 AI 只能自己拼 propose/apply —— 那套只保证"文本出现过"，不保证改完语义还对
- 工具数 19 → 21

## 0.9.5

- `extract` 支持 **`--auto`**：自动推断要传哪些参数、返回什么（先读后写算输入，
  块尾给函数返回值赋值也算输出）；dry-run 会先把 `in=… | out=…` 打出来
- 推断是启发式的，所以它**明说是推断**，并且仍然要过三道验收才会落盘

## 0.9.4

- 仓库里**只保留最新一个**离线安装包：clone 下来就能直接装，不必先跑打包；
  旧版本从更新日志里查，需要时重新产出（此前一个包都不入库）

## 0.9.3

- 新增**用户使用说明**（随扩展分发，命令 `matlabc: 打开使用说明`）：只讲
  怎么装、每个功能在哪、看到什么、出问题怎么办
- 顺手补齐：README 命令表只列了 5 个，实际有 9 个（预览关系图 ×2、
  查看名字的关系、打开使用说明 此前都没写）

## 0.9.2

- 任务层第三项 **`extract`**：把一段代码提成独立函数（`--lines` + `--in/--out`），
  验收 = 函数数 +1 / 诊断不增加 / `function`-`end` 仍配平；不过就自动回滚
- 接口**由调用方显式给出**，不猜：猜错的提取比不提更糟（自动推断是下一步）
- 重名会在动手之前被拒（不产生半成品）

## 0.9.1

- 任务层新增 **`rename-field`**：只改 `.field`，同名的独立变量与字符串里的
  `.field` 原样保留（这是 MATLAB 里最容易改漏的一类）
- 两条 rename 现在共用一套判据框架：改名之前先把验收条件列出来，写完逐条核对，
  不过就逐字节回滚

## 0.9.0

- 新增第 5 个入口 **`matlabc_task.py`：把「改代码」变成任务**
  —— `rename` 会先算清要改哪些位置、**把验收条件先列出来**，写完后重新分析
  逐条核对（旧名字归零 / 函数数不变 / 调用边数不变 / 诊断不增加）；
  任一条不过或写盘失败，**自动逐字节回滚**
- 改名只动代码，注释与字符串里的同名文本保持原样
- 这一层是"把已有的自证能力接到写操作上"：判据在动手之前就固定，而不是事后解释

## 0.8.3

- 修 `ci_local.py` 的一处解包错误（`_git` 返回两个值，却按三个解包）——
  工具首次运行就崩，正是它自己要防的那类问题
- 实测沙箱四层耗时：静态门 88s / 判据 6s / 场景 10s / 变异 16s

## 0.8.2

- CI 收敛为 **Windows 单平台**：没有 Linux 机器时，ubuntu 的红灯没人能复现，
  最终只会被忽略；恢复只要换成矩阵一行
- 新增 **`tools/ci_local.py`**：在 `E:\ci\matlabc` 的干净克隆里跑同一条流水线
- 修掉一个真缺陷：`python tests/test_matlabc.py` 在**任何平台**都会
  `ModuleNotFoundError`（脚本目录进了 sys.path、仓库根没进），
  而 CI 一直在跑这条必然失败的命令

## 0.8.1

- CI 增加 **Windows** 作业：此前只有 ubuntu 在跑，而项目声称两边都能用 ——
  现在 Windows 侧会重放静态门、行为判据、端到端场景与变异抽样
- 两平台断言前先验证「干净克隆能跑通」：本地全绿不证明 CI 全绿

## 0.8.0

- 修正 README 末尾一处**被转义吃掉的文本**（`python tools/...` 变成了 `\tools/...`，
  `analyze` 变成 `\x07nalyze`），以及一句**已经过时的陈述**（说增量校验是红的，
  而它早已全绿）
- 两份 README 的结尾改为「本仓如何自证」，列出四条可复现的命令

## 0.7.9

- **支持在 Linux / macOS 上部署**：同一个安装包两边通用；`calllib` 的导出表
  核对不再只认 Windows 的 PE —— 现在按**文件头**分派，ELF（`.so`）也能读
- Node / rea 的兜底查找补上 POSIX 路径（此前只有 `C:\...`，Linux 上会误报"未安装"）
- 新增一道门守这条边界：运行时代码里的 Windows 绝对路径必须成对登记，
  Windows 专属 API 一律不许出现

## 0.7.8

- 新增**覆盖度量**：按真实调用点统计每个 MCP 工具的测试情况，立刻查出
  `definition` 与 `references` 两个工具**从未被任何测试调用过**（按名字搜是 19/19）
- 补上这两个场景（60 个全场景），现在零覆盖工具数为 0
- 使用说明补一条常见问题：为什么有的函数看不到「跨语言」那一组

## 0.7.7

- 使用说明补上**跨语言桥接**与**反向查询**（此前六轮做的能力，文档里一个字都没有）
- 补 3 条判据锁住「错误信息要指向原因」：找不到文件时回显路径、空函数名直接报错、
  越界路径明确拒绝；并补 2 条变异证明这些判据会红
- `check_all --with-scenarios`：总闸可顺手跑一遍全场景（58 个），失败会影响退出码

## 0.7.6

- 新增**全场景探针**（58 个场景）：只通过公开协议驱动真实进程，覆盖 LSP 与
  MCP 的正常路径、异常路径、极端输入、写操作事务，以及 120 文件 / 5000 函数
  这类规模场景。十轮迭代把 22 个失败全部消化，并把每轮失败固化成新场景
- 修正两处**错误信息不指向原因**：文件找不到时回显用户给的路径（此前是空串）、
  函数名为空时直接说「name 不能为空」（此前是「`` 不是本工程里的函数」）

## 0.7.5

- 变异抽样从 3 处扩到 **14 处**（覆盖 MCP 工具与诊断缓存），并借此发现
  一条**空判据**：防环判据用的是无环语料，把防环关掉它照样绿
- 修正该语料（加入互递归），现在关掉防环会让判据变红

## 0.7.4

- 新增**变异抽样**：故意把实现改坏一处，验证对应判据真的会红
  （永远不会红的判据与没有判据等价，而它看起来更让人放心）
- 顺带修掉分析文档里一条**前提写错**的改进项（判据其实不依赖本地语料）

## 0.7.3

- 修掉三处**测试基建**的陈欠（都不影响功能，但会让门失效）：
  `--help` 零输出后选项表读不到、跨语言桥接的查表谓词未登记、
  子进程登记里有已删除的函数 —— 并给 MCP 自检加了看门狗

## 0.7.2

- 关系面板会**记住展开的分组**（光标移开再回来不会收起，同一工作区跨会话保留）
- 测试资产补上「可数、可验」的入口：判据清单现在能一次列全（200 条、无重名），
  新增的两道门也补齐了自证与退出码契约

## 0.7.1

- 关系面板会**记住你展开的分组**：光标移到别处再移回来，之前点开的
  「上游」「被调用」不会又被收起（同一工作区内跨会话也保留）

## 0.7.0

- **版本号规则改为「每一位只走 0–9，满 10 进一位」**：`0.7.9` 之后是
  `0.8.0`，`0.9.9` 之后是 `1.0.0`。此前补丁位可以一直加，已经积累到
  `0.6.104`，读起来像日期，也不方便判断哪一版更新得多
- 新增 `tools/bump_version.py`：算下一版 / 写入 / 校验，不再手改数字
- 新增一道门，守这条规则：版本位越界、或升了版本却忘了更新版本表，都会红

## 0.6.104

- 「函数速览」也会指出**跨语言落点**：它调的哪些东西在 C 源 / 二进制里，
  C 侧再往下还有几层。至此影响面、变更影响、速览三个入口口径一致

## 0.6.103

- 「我改了这几个文件，谁需要回归」现在会**一并列出跨语言落点**：哪些函数调的是
  C 源 / mex 里的东西，C 侧一改它们都要重验（这批通常没有 MATLAB 上游，最易漏）
- 修正：没有 MATLAB 调用者时，此前会把「它 → 它」当成来路，报成「波及 1 个函数」

## 0.6.102

- 使用导览里那个「CodeLens」改为 **matlabc CodeLens**，并标注「本扩展提供」——
  否则读者会以为它是 VS Code 自带或别的插件
- 模块上的 `tag`（本扩展提供 / 离线 / 给 AI 用）此前只在数据里、页面上看不到，现在画出来了

## 0.6.101

- AI 助手查「影响面」时会**一并给出跨语言落点**：解析不到的调用落在哪个
  C 源文件、第几行，再往下还调了谁；已找到落点的不再重复列进「仍未定位」

## 0.6.100

- 使用导览：连线改为**从方框边缘接出**（此前穿过方框、压住标题），
  每一步补上**具体功能**（快捷键、命令名、参数），不再只有一句概述

## 0.6.99

- 新增命令 **`matlabc: 打开使用导览`**：8 步动画讲清每个功能在哪，
  不用再去翻文档；导览随包分发，离线可用

## 0.6.98

- 新增**可逐帧播放的模块导览**（`releases/demo/matlabc-tour.html`）：
  8 步依次高亮相关模块并说明这一步在做什么，可点模块跳转、可暂停
- 导览的内容以 archify 的 architecture JSON 描述，渲染器由仓库脚本生成

## 0.6.97

- 跨语言查询支持**反向**：给一个 C 函数名，回答「哪些 MATLAB 函数在调用它、
  C 内部又是谁调它」——改 C 代码前最想知道的就是这个
  （此前只能正向：从 MATLAB 函数看它调了哪些 C）

## 0.6.96

- 跨语言的 C 内部链路现在**展开三层**（此前只有一层），并用箭头标出层数；
  互递归（C 里并不罕见）会在已访问处截断，不会转圈

## 0.6.95

- 跨语言桥接**继续往下走一层**：MATLAB 调用落到 C 函数后，关系面板会展开
  这个 C 函数内部又调了谁（可点，带 C 文件行号）——此前只到 C 入口就停住，
  等于把「链断了」的问题往后挪了一层

## 0.6.94

- 新增开关 **`matlabc.crossLanguage`**（默认开）：关掉后不再扫描 C 源与
  mex/DLL 导出表，关系面板也不会为跨语言这件事做任何 IO
- 关掉时明确显示「已关闭」，而不是给一个空结果让人以为工程里没有桥接
- rea 探测改为**连能覆盖什么一起报告**：它已可运行，但实测只支持 Linux ELF，
  对 Windows DLL 不提供能力

## 0.6.93

- 跨语言证据现在**标注来源**：C 源定义 / mex 文件名匹配 / 库导出表核对，
  三者强度不同，读者能分清哪条是实测、哪条是推断
- 外部二进制工具（rea）是否可用会如实报告；不可用时写明卡在哪
  （本机未装 Node，因此当前所有二进制结论仅来自内置解析）

## 0.6.92

- 跨语言桥接补上**二进制层**：同目录的 `foo.mexw64` 就是 `foo` 的实现
  （入口名写在文件名上，无需解析机器码）；`calllib('lib','fn')` 会去核对
  该库的**导出表**，明确告诉你是 ✓ 已导出还是 ✗ 库里没有
- 只有 mex / dll、没有 C 源的工程现在也能桥接（此前会被判成「没有可桥接的东西」）

## 0.6.91

- 新增**跨语言桥接**：MATLAB 里解析不到的调用，若工程内的 C 源（`.c/.cpp`）
  有同名定义，关系面板会多一组「⇢ 跨语言（C/MEX）」，可直接跳到 C 文件的行
- 连 C 源也没有的名字会单独列出，并说明「来自 mex 二进制 / 工具箱」——
  不再和「没有更多调用者」混为一谈
- AI 助手也新增了同名能力（`matlabc_cbridge`）

## 0.6.90

- 修正：多函数文件里，「声明」取的是**全文件第一个赋值**，可能落在别的函数里
  （局部函数看不到主函数的工作区，那是另一个变量）。现在按**光标所在的函数**
  找声明；本函数内没有赋值时明说「同名变量在 xxx 第 N 行」
- 悬停提示与侧栏用同一套规则，不再出现「悬停说第 3 行、侧栏说本函数没有」

## 0.6.89

- 关系面板按**函数**分组显示同名变量：同一函数内合并（MATLAB 没有块级作用域），
  跨函数时分开并标注「同名但不同变量」

## 0.6.88

- 修正：**结构体字段被当成局部变量显示**。现在光标停在 `options.coneprog`
  这样的字段上时，关系面板会显示它在哪些位置被**写入**、哪些位置被**读取**，
  以及挂在几个基名上，而不是「本文没有赋值」

## 0.6.87

- 离线安装包的版本表改为**自动生成**：版本、摘要、大小、日期分别取自
  扩展清单、更新日志与包文件，不再手工补行（此前漏过版本）

## 0.6.86

- AI 助手启动时**复用编辑器已经做过的分析结果**，不再把同一份工程重算一遍
  （大工程从十几秒降到几十毫秒）

## 0.6.85

- AI 助手的「工程体检」结果现在会**保存到本地**：第一次较慢，
  之后（包括重启编辑器后）秒回；工程改动后自动重算，不会拿旧结论冒充新的

## 0.6.84

- 统一去掉名字里的 `lsp`：安装包文件名改为 `matlabc-<版本号>.vsix`，
  日志前缀与服务端自报身份也一并用 `matlabc`
  （更早的更新日志里出现的旧名是当时的事实，保留不改）

## 0.6.83

- AI 助手现在可以**一次改多个文件**，并且是事务性的：
  任何一个文件不合法，整批都不写；写到一半失败会自动回滚

## 0.6.82

- 详情页不再放图片（本地安装的扩展加载不了包内图，显示为破图标），
  改为在 `releases/demo/` 提供**四个场景的演示动图**，双击即可播放
- 演示覆盖：大纲、转到定义、关系面板、热点排行

## 0.6.81

- 修正：页面上的动图此前显示为破图标 —— 安装包缺少图片类型声明，
  已补齐，动图现在能正常播放
- 新增 `releases/` 目录记录每个可交付的离线版本（版本、日期、大小、变化）

## 0.6.80

- 页面改写为**纯用户视角**：只讲功能与操作，去掉实现细节与代码片段
- 移除页面里的动图引用 —— 离线安装的扩展详情页不解析包内相对路径，
  显示出来是一个破图标，不如用文字讲清交互
- 新增「第一次使用，建议按这个顺序」「常见问题」两节

## 0.6.79

- MCP 新增 **`matlabc_help`**：列出当前可用的工具与推荐问法。
  本地小模型不必再靠猜——它能自己问「你会什么」
- `help` 只推荐**当前档位真的有的**工具：`--tools core` 下不会再教你用写工具
- `core` 档从 6 个工具扩到 7 个（加入 `help` 本身）

## 0.6.78

- 页面新增**逐帧演示动图**：光标停在一个名字上 → 侧栏显示上下游 → 点击跳转
- 页面新增 **MCP 工具接口**一节：11 个只读工具 + 3 个写工具，各自回答什么问题
- 页面新增**内网无模型 API 时**的说明：哪些能力不需要模型
- 页面补充两个命令：生成 HTML 分析报告、生成 MCP 配置

## 0.6.77

- MCP 首次具备**写能力**，但拆成三步、每步都有护栏：
  `matlabc_propose_edit`（只算 diff，不落盘）→ `matlabc_apply_edit`
  （显式带 editId 才写，写前自动备份）→ `matlabc_undo_edit`（从备份恢复）
- 三条硬约束：只改工程目录内的文件；`oldText` 必须**恰好出现一次**；
  写入前再校验一次（防止确认期间文件被改）

## 0.6.76

- 新增 **「生成 HTML 分析报告」**：一键在工作区 `.matlabc/report.html` 生成
  完整报告并在浏览器打开（此前只能在命令行里加 `--html`）
- 新增 **「生成 MCP 配置」**：自动填好 python 路径、脚本路径与工程根，
  可直接写入 `.vscode/mcp.json`（VS Code 内置 MCP），或复制成
  `mcpServers` 格式给 Claude / Cursor 等其他客户端

## 0.6.75

- MCP 新增 **`matlabc_changed`**：给几个改动过的文件，回答「谁需要先回归」，
  按波及面排序，并给出示例来路。比拿两个快照做结构 diff 更贴近
  「刚改完代码」这个场景

## 0.6.74

- MCP 新增 **`matlabc_explain`**：一次给出函数速览——角色（入口/中间层/叶子）、
  改动风险等级与理由、从哪看起。比 `impact` 更适合「我要改这个函数」的开场，
  因为它给的是结论而不是原始列表
- 风险规则把**复杂度**单独计入：没人调用但很复杂的入口同样判为中风险

## 0.6.73

- MCP 新增 **`matlabc_diagnostics`**：按类别列出工程诊断（未初始化、未使用等），
  按严重度排序，可按文件过滤。它是**慢工具**（首次需完整检查，约 1 分钟），
  description 里明写了代价
- MCP 工具支持**相对路径**（`a.m` 按工程根解析），不再要求绝对路径

## 0.6.72

- MCP 增补两项 HTML 报告里最常用的能力：**结构体字段跨文件读写溯源**
  （按基名分组，并提示「同名不同结构体」）、**工程规模概览**
- 影响面在没有调用者时不再输出只有它自己的「来路」

## 0.6.71

- 关系视图里函数的顶层位置此前恒显示 `line 1`（取错了字段），已修正
- 新增 **MCP 服务**（`matlabc_mcp.py`）：把大纲 / 影响面 / 热点 / 定义 /
  引用 / 搜索六项能力暴露给任意 AI Agent，复用同一套分析结果

## 0.6.70

- 缓存字段改为**一处定义**：保存与读取都从同一份清单推导，
  避免再出现「某个字段没存、命中后某个功能静默失效」
- 新增判据：缓存产物里的字段集合必须与清单逐字相同

## 0.6.69

- 修正：快速移动光标时，**先发出的查询会覆盖后发出的结果**（表现为「点了全局
  变量，界面还停在刚才的局部变量上」）
- 修正：**局部变量不再挂着「全库关系 · 待分析完成」** —— 它本来就没有跨文件
  引用，之前被误判成「还没算完」，永远等不到

## 0.6.68

- 修正（根因）：磁盘缓存里没有 `globals` / `lines` / `kind` 三个字段，
  缓存命中后**全局变量查不到跨文件引用**（被当成局部变量）、大纲范围退化
- 缓存版本升到 4，旧缓存会自动重算一次（首次打开稍慢，之后正常）

## 0.6.67

- 修正：光标停在**行首或整行选中**时，查引用用的是 `global` 这个关键字而不是
  变量名，导致引用恒为空、侧栏一直停在「分析中…」
- 现在请求一律使用**标识符的起始列**，而不是光标所在列

## 0.6.66

- 修正：**全局变量被当成局部变量显示**。客户端只等 1.5 秒，而服务端在
  分析未完成时要等满 2 秒才返回 —— 请求必然超时、结果恒为空，
  于是「跨文件」这一事实永远取不到
- 现在等待放宽到 5 秒；并且当引用结果**少于本文出现次数**时，不再判定为
  局部变量，而是标「分析中…」并在几秒后自动补全

## 0.6.65

- 服务端还没算完时，侧栏明确显示「全库关系 · 待分析完成」，不再静默缺失
- 日志里带上服务端进度（「预热开始 / 结构层就绪 / 预热完成」），
  能看出它卡在哪一步

## 0.6.64

- **分析未完成时不再什么都不给**：服务端还在建索引时，照样显示本文的
  「声明 / 本文出现」（这部分不需要服务端），并在标题标注「分析中…」，
  3 秒后自动补上全库关系
- 光标停在注释里的词上不再触发关系计算（日志里出现过 `declare`、`function`）

## 0.6.63

- 修正：**打开文件后侧栏一直是空的** —— 只监听「光标移动」不够，
  打开文件时光标本来就在原处、没有选择变化事件。现在切换文件、
  激活扩展时也会算一次

## 0.6.62

- 关系视图的**每个出口都打日志**（触发 / doc 无效 / 无标识符 / 去重 / 本文无出现 /
  成功 / 异常），空白到底停在哪一步可以直接看出来
- 修正：点 CodeLens 时焦点可能在侧栏上，`activeTextEditor` 为空导致算不出关系 ——
  改为回退到最近一次有效的 MATLAB 文档

## 0.6.61

- 关系视图整段加了兜底与日志：`关系 G_CFG -> 组=N 全局=true refs=5 files=2`
  或 `关系 G_CFG 失败：…`
  （空白有三种原因——未触发 / 抛异常 / 组为空，界面上长得一样，只能靠日志区分）

## 0.6.60

- 修正：侧栏在全局变量上**整个空白**（作用域写错，运行时报 ReferenceError）
- 全局变量按语义分成三组：**定义（唯一赋值处）/ 声明（各文件的 `global X`）/ 使用（读取）**
  —— 全局变量只有一个定义，多个文件里的是声明，混在一起会让人以为被定义了好几次

## 0.6.59

- 全局变量在侧栏里**单独成组**：顶层直接标「全局变量 · N 个文件」，
  不再和局部变量一样只写「（变量）」
- 「全库出现」提到声明之后，按文件分组、每项可点
- 局部变量行为不变

## 0.6.58

- 关系视图：**全局变量列出全库出现位置**（按文件分组，可点），
  不再只显示当前文件 —— 它本来就在多个文件里共享
- 只扫「声明过这个 global 的文件」：没声明就用不了它，范围既正确又便宜

## 0.6.57

- 关系视图：变量/字段在**本文没有声明**时，会去问一次服务端，
  若产地**在别的文件**，直接列出「在其他文件：cfg_build.m 第 N 行」并可点
  （此前只说「本文没有赋值」，等于没回答）

## 0.6.56

- **修正根因**：首次全库分析实测 70 秒（1676 文件），期间所有请求都在排队，
  界面只能干等。现在读请求最多等 2 秒，未就绪就返回「分析进行中」，
  侧栏**每 3 秒自动重试**并明确显示状态
- `impact` 不再为全库每个函数预算参数与未解析名（原来 68 秒，现 0.5 秒），
  改为只对真正显示出来的节点按需计算

## 0.6.55

- 修正：打开大工程时大纲一直「正在加载」、关系视图空白 ——
  请求没有上限，服务端忙时界面会无限等
- 现在：大纲 800ms、关系/悬停 1200ms 超时，超时立刻改用本地结果
  （大纲扫本文、关系给声明与出现位置），**界面不再卡在等待上**

## 0.6.54

- **注释里的名字不再跳转**：此前在文档注释里写到 `b.lb`、`foo(...)` 后按 F12
  会跳到别处 —— 一个「看起来成功了」的错误跳转
- **结构体成员优先落在「等号左边」**：写入点里混着读取行
  （`a.ub = a.lb + 1;` 的 `a.lb` 也被记进去），按行号取第一条会落在读取处

## 0.6.53

- **全局变量**：F12 现在跳 `global X` 那一行（声明处）。此前跳到某次赋值
  （实测 YALMIP 的 `LUbounds`：声明在第 9 行，却跳到第 45 行）
- **结构体成员**：按**基名**优先，`model.lb` 只找 `model` 上的 `lb`。
  此前同名字段混成一个池子（实测 `lb` 有 1301 个写入点），等于随便挑一个
- 基名只在紧邻的那一层取，`a.b.c` 认 `b`，与 MATLAB 语义一致

## 0.6.52

- 关系视图每一跳显示**调用发生的那一行**（不再只是函数定义行），与
  Source Insight 的 `1. line 286` 语义一致
- 同一条链只保留最小调用行，去重后仍指向真实位置；目标自己不带调用行

## 0.6.51

- 关系视图按 Source Insight 简化：
  - **只显示「函数名 + 行号」**，不再铺绝对/相对路径（同文件只写 `line 286`）
  - 调用者改为**由近及远**的树：紧邻的调用者在最上面，逐层向上到入口，
    同一入口的多条路径自动合流
  - 「链」这一层去掉，层级从四层降到两层
  - 「横向查看」移到最后（它是补充，不该占第一行）

## 0.6.50

- 侧栏关系视图按 Source Insight 的 Relation 窗口重排：
  **顶层符号 → 每条来路 → 逐跳（编号 + 函数名 + 位置）**
- 去掉全部图标：codicon 在部分主题下会渲染成乱码（函数名前的 `@*`），
  改用文字符号 `←` `→` `⌗` `⇥`，可读性不再依赖字体

## 0.6.49

- 侧栏关系视图加上**语义图标**：函数、变量、调用链、调用方向各一种，扫一眼能分辨类型
- **调用链逐跳展开**：每一跳是一个函数名 + 所在位置，不再是一行挤在一起的长字符串；
  链标签写明「入口 → … → 我」及跳数，一直追到最顶层入口
- 侧栏顶部新增 **「横向查看（箭头关系）」**，在右侧打开横向图；该面板不抢焦点，
  编辑器的大纲不受影响

## 0.6.48

- 修正：侧栏里变量的行号显示的是**光标行**，不是它**声明的那一行**（与代码对不上）
- 侧栏把「调用者」与「调用链」**合并**：有链就只给链，每条链可展开逐跳查看，
  每一跳可点；没有链（说明是入口）才退回调用者列表
- **变量也能「转到定义」**：按 F12 跳到本文的首次赋值（MATLAB 没有声明语句，
  `x = ...` 就是它成立的地方）

## 0.6.47

- 侧栏关系视图：**顶层就是当前名字本身**，视图标题显示「关系：xos1」
  （此前标题是写死的，看不出来在看谁）
- 箭头标明调用方向：`← 谁调我` / `→ 我调谁`，与 Source Insight 的读法一致

## 0.6.46

- **点 CodeLens / 右键查看关系，全部改为更新侧栏**，不再打开任何标签页
  （标签页会抢焦点，把大纲挤走 —— 这就是「大纲不见了」的真正来源）
- 侧栏内容随光标自动更新；点过的函数会「钉住」，光标一动恢复跟随

## 0.6.45

- **新增侧栏「matlabc 关系」视图**（资源管理器下方），按 Source Insight 的做法：
  - **不抢编辑器焦点** → 大纲不再消失（文档标签页式的面板会抢）
  - **跟随光标自动更新** → 不需要先点“查看完整关系”
  - 函数给「↑ 调用者 / ↓ 被调用 / 链」三组，变量给「声明 / 本文出现」
  - 每一项都能点，直接跳到 `文件:行`

## 0.6.44

- **悬停即见关系**：鼠标停在一个名字上，函数显示「↑N 调用者 · ↓M 被调用」与前三个
  调用点，变量显示「声明在第几行 / 本文出现几处」；点悬停里的链接可打开完整面板
- 修正：打开关系面板后**大纲变空** —— 面板不再抢焦点（`preserveFocus`），
  编辑器保持激活，大纲照常显示

## 0.6.43

- 新增**「查看名字的关系」**（右键菜单 / 命令面板）：
  - 光标在**函数**上 → 打开调用关系图（上下游 + 调用链）
  - 光标在**变量/字段**上 → 显示**声明（首次赋值）**与本文全部出现位置，逐条可点
- 这是 Source Insight 关系窗口的读法：一个入口，按身份给两种答案

## 0.6.42

- **修正（根因）：大纲在缓存命中后永远为空** —— 缓存重建的对象缺 `lines`，
  范围退化成零点，编辑器判定 `selectionRange` 越界并**拒收整批符号**。
  现在范围至少覆盖函数名；客户端也加了兜底，不再因一个符号不合法而全丢

## 0.6.41

- 每个 provider 的注册各自兜底：**任何一步注册失败都不再连累后面的**
  （激活自上而下执行，中间抛错会让后面的注册全部不发生，而前面的照常工作
  —— 症状看起来就像「只有大纲坏了」）
- 激活结束时往输出频道写一行 `activate 完成：… 均已注册`，用来定位

## 0.6.40

- 修正：大纲在某些文件上始终为空。原因不是解析，而是**上一版的重试把
  provider 拖过了编辑器的超时** —— 现在只问一次、立刻返回；
  服务端没答上来时立刻改用本地扫描，不再等待

## 0.6.39

- 调用关系图支持**横向 / 纵向两种看法**，图内一键切换：
  - **纵向（按层）**：谁影响我、我要改哪些 —— 看层级与范围
  - **横向（按链）**：`入口 ← … ← 目标 → …` —— 看一条路怎么走
- 新增命令 `matlabc: 预览调用关系图（横向）`

## 0.6.38

- 大纲在「服务端为空且本地也扫不到函数」时，**显示一行说明**而不是空白，
  并提示把输出频道的日志发回 —— 空大纲无法与「工具坏了」区分
- 本地扫描兼容 `function [a,b] = name(...)`、`function name(...)` 两种写法

## 0.6.37

- 新增**同一文件内的出现位置高亮**：光标停在一个名字上，本文里所有同名处一起标出
  （Source Insight 式读法；纯本地扫描，不依赖分析结果）

## 0.6.36

- 修正：大纲在某些文件上始终为空 —— 现在服务端给不出符号时，**就地扫描当前文件**，
  大纲保证有内容
- 保留控制台日志：`大纲 xxx.m -> N 个符号` / `服务端为空，本地扫描得到 N 个`

## 0.6.35

- 调用关系图新增**链式视图**：从入口到目标，一条路径一行（Source Insight 式读法）
- 修正：大纲在请求过早（服务端尚未就绪）时会一直为空 —— 现在会重试几次
- 修正：同一调用者有多个调用点时，调用链会被重复输出多次

## 0.6.34

- 大纲在 `@类目录` 下的方法文件（例如 `@sdpvar/round.m`）也能正常显示
- 新增判据：路径含 `@`、URI 走百分号编码时，大纲同样要出符号

> 装好新版本后需要**重载窗口**（或点扩展页上的「重新启动扩展」），
> 否则编辑器仍在跑旧的分析进程，看到的还是修复前的行为。

## 0.6.33

- 更新日志去掉开头那句说明文字

## 0.6.32

- 修正：首次打开大工程时，**大纲显示「找不到符号」并一直空着**
  —— 现在即使分析尚未完成，也会就地解析当前文件，大纲立即可用
- 大纲不再等待分析完成（此前会卡到超时再返回空）
- 大纲里每个函数覆盖**整个函数体**，不再退化成一行

## 0.6.31

- 热点排行支持**按目录过滤**：新增命令「热点函数排行（当前目录）」，
  跨模块的分数没有可比性，同一目录内才有意义
- 列表末尾新增**复制为 Markdown**，可直接贴进评审文档
- 过滤不到结果时明确提示「该目录下没有可排行的函数」，与「分析尚未完成」区分开

## 0.6.30

- 新增**热点函数排行**：按「复杂度 ×（1 + 调用者数）」排序，命令面板可调用，
  选中即跳转到定义
- 复杂度高说明难读，调用者多说明波及面大，两项相乘才是值得先看的地方

## 0.6.29

- 发布者用名字 `冯磊`：标题为 `matlabc`，副行显示 `冯磊`，标识符为 `冯磊.matlabc`
- 已知代价：标识符里含中文姓名，将来若发布到扩展市场需换成 ASCII 账号

## 0.6.28

- 发布者改为账号标识 `pony-029`，扩展标识相应变为 `pony-029.matlabc`；
  **标识符里不再出现作者姓名**（人名不适合当机器标识，与通行做法一致）
- 标题恢复为 `matlabc | 冯磊`，作者依旧显示在标题行

## 0.6.27

- 扩展标识由 `matlabc-lsp` 改为 `matlabc`
- 页面改为正式产品表述，新增「与常见方案的区别」，突出：结构体成员与变量导航、
  调用链追溯至入口、无法解析时给出归因、增量刷新与全量结果一致
- 简介改为一句产品定位

## 0.6.26

- **品牌名统一为 `matlabc`**（此前误写为 malabc）
- 页头：标题行是 `matlabc`，下面一行是 `冯磊`
- 命令 ID 同步为 `matlabc.*`
- [!] 扩展标识随之变为 `冯磊.matlabc-lsp`；升级后请卸载旧的 `malabc.matlabc-lsp`，
  否则两个扩展会同时启动各自的服务器

## 0.6.25

- 标题改为 `matlabc | 冯磊`
- 新增扩展图标：三个节点构成的调用树，橙色表示当前函数
- 页尾那句「名称与品牌」的说明改短，去掉容易触发红线的英文引用

## 0.6.24

- 页头标题带上作者：`matlabc MATLAB LSP — 冯磊`
- 页面底部补充版权信息
- 正文去掉重复的作者行（作者已在页头，不必占两处）

## 0.6.23

- **扩展详情页改版**：改成「只讲功能」，并补上作者信息
- 新增本更新日志页

## 0.6.22

- 页面不再罗列实现细节（依赖、文件名、打包方式）
- 补上作者：冯磊（Feng Lei）
- 新增「找不到函数时它会怎么解释」「调用关系图怎么读」两节

## 0.6.21

- 悬停到**不是函数的标识符**时，不再一片空白：
  字段 / 外部函数 / 参数 / 局部变量 / 完全未知，五种情况各自说明
- 悬停中文文本不再被当成函数名（之前会显示「`某段中文` 不是函数」）

## 0.6.20

- 悬停到**函数参数**上，显示它是参数、类型是什么、属于哪个函数
- 没有类型说明的参数会如实写「头部注释里没有类型说明」

## 0.6.19

- 修正：删除一个 `.m` 文件后再保存其它文件，调用关系里不会残留指向已删除文件的连线

## 0.6.18

- **保存即刷新**：只重新分析改动的那一个文件，大工程上也是瞬间
- 分析结果与全量分析逐项一致（有判据守着）

## 0.6.17

- 调用关系图底部说明：调用点那串数字数的是**语句**，一行里多次调用算一处

## 0.6.16

- 帮助文本与实际功能同步

## 0.6.15

- 修正：增量分析时被调用函数的文件名可能丢失，导致同一条调用出现两个版本

## 0.6.14

- 调用关系图节点显示**参数类型**（有类型时），没有类型就不显示占位符

## 0.6.13

- 调用关系图新增**入口**标记与**源头**标记
- 修正：有调用者但没记录行号的函数，不再被误标成入口

## 0.6.12

- 调用关系图节点显示**参数列表**
- 参数信息优先取头部注释的参数表，没有再退回函数签名

## 0.6.11

- 上游「调用自 …」超过 6 处时折叠，并写明还剩几处

## 0.6.10

- 未解析的名字列表超过 5 个时，写明「等 N 个」

## 0.6.9

- 修正：调用点归属到**调用者**的文件，跨文件跳转不再跳错文件

## 0.6.8

- 调用关系图列出**解析不到的名字**，不再只给一个数字

## 0.6.7

- 支持**结构体成员** `s.field` 的跳转

## 0.6.6

- 点 CodeLens 打开**旁侧调用关系图**：上游分层、每层带行号

## 0.6.5

- 调用者列表显示**第 2 层及以上**，不再只列直接调用者

## 0.6.4

- 悬停显示**参数表**（来自函数头注释的 `% Input:` / `% Output:`）

## 0.6.3

- 点击**结构体变量** `s` 跳到它第一次被赋值的位置

## 0.6.2

- 关系图每层最多列 20 个节点，超出写明还剩多少

## 0.6.1

- 关系图新增**下游**（它调用谁）与节点复杂度

## 0.6.0

- 调用链一路向上追到入口，每个节点带行号，**点一下直达**
- 同一函数被多处调用时，列出每一处

## 0.5.x 及更早

- 诊断、转到定义、查找引用、悬停、大纲、CodeLens 调用计数、语义高亮、
  保存即刷新、后台预热、磁盘缓存、文件图标与语法高亮
