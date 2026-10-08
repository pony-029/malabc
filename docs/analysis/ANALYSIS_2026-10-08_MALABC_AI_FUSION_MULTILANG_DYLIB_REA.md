# ANALYSIS · matlabc × AI Agent 融合方向 / 六语言分析深度 / 动态库 / rea 融合

> **方法**：`superpowers`（六顶思考帽，蓝→白→红→黑→黄→绿→蓝）+ `brainstorming`（苏格拉底式追问收敛）
> **日期**：2026-10-08
> **范围**：① AI Agent 融合方向 ② C/C++/Python/Rust/JS/TS 六语言分析深度方案
> ③ 动态链接库（DLL/.so/.dylib/FFI）分析方案 ④ `morluto/rea` 深度融合方案与分阶段计划
> **纪律声明**：本文所有结论分「**实测**（有命令与输出）」与「**推断**（标注）」，不把声称当事实。

---

## 0. 蓝帽 · 分析对象与目标

| 项 | 内容 |
| --- | --- |
| 分析对象 | `E:\matlabc\malabc`（源码静态分析 + 确定性修复 + AI 融合层）及其与 AI Agent 的结合方向 |
| 对标对象 | `E:\matlabc\rea`（`morluto/rea`，已全量克隆） |
| 目标 | 给出可执行融合路线，覆盖：六语言分析深度方案 / 动态库分析方案 / rea 深度融合方案 |
| 产出 | 本报告 + 4 张可视化图 |
| 验收基线 | 每条结论可回溯到「文件:行号」或「实测命令输出」 |

---

## 1. 白帽 · 事实与数据（全部实测）

### 1.1 两仓库规模对照

| 维度 | matlabc | rea | 比值 |
| --- | ---: | ---: | ---: |
| 语言 | Python 3.6+ | TypeScript (ESM) | — |
| 代码行数 | **55,484** | **278,316** | 5.02× |
| 文件数 | 26 | 1,609 | 61.9× |
| src 部分 | 33,461 行 / 9 文件（含 29,637 行单文件内核） | 210,770 行 / 1,226 文件 | — |
| tests 部分 | 15,918 行 / 5 文件 | 66,845 行 / 365 文件 | — |
| 运行时依赖 | **0（纯标准库）** | **32** | — |
| 许可证 | — | MIT（npm `rea-agents` 6.0.0） | — |
| 对外能力面 | CLI + MCP（自研 server） | **139 MCP 工具 / 12 族 / 26 provider / 94 CLI 命令** | — |

### 1.2 matlabc 的语言前端真实深度（实测）

> 实测方法：生成 6 语言样例（`E:\matlabc\_analysis\langprobe\`），分别以工具支持的 `--lang` 解析。

| 语言 | 声称 | 实测结果 | 判定 |
| --- | --- | --- | --- |
| MALAB | 完整 | def-use / 污点 / 维度抽象解释 / 不可达 | ✅ 真 |
| C | 支持 | 1 文件 / 4 函数 / **8 条正则启发式** | 🟡 L1.5 |
| **C++** | 未声称 | **0 文件 / 0 函数 / 0 检测** | ❌ **完全不可见** |
| Python | 支持 | 1 文件 / 5 函数 / **4 条正则启发式** | 🟡 L1.5 |
| JavaScript | 支持 | 1 文件 / 3 函数（**类方法未抽取**）/ 4 条启发式 | 🟡 L1.5 |
| **TypeScript** | 未声称 | **rc=1 硬报错：未找到任何 js 文件** | ❌ **不支持** |
| **Rust** | 未声称 | **0 文件 / 0 函数 / 0 检测** | ❌ **完全不可见** |

**根因（代码级定位）**：

| 缺陷 | 位置 | 事实 |
| --- | --- | --- |
| C++ 不可见 | `matlabc.py:6856` | `collect_c_files` 只收 `endswith((".c", ".h"))`，`.cpp/.cc/.cxx/.hpp` 全被丢弃 |
| TS 不可见 | JS 收集器 | 只收集 `.js`，`.ts/.tsx` 被忽略 → 空集 → rc=1 |
| 函数定义漏识 | `matlabc.py:6835` `_RE_C_FUNC` | 正则要求 `) {` 与函数名**同一行**；`{` 换行的常见 C 风格 → 漏识 |
| 无预处理感知 | `_RE_C_MACRO` 只计数 | `#if 0` 内的代码仍被分析（假阳风险） |
| JS 类方法漏抽 | `matlabc.py:7467` `_RE_JS_FN_DECL/_ASSIGN` | 仅认 `function name()` 与 `name = function()`，`class X { m() {} }` 全部漏掉 |
| 语言分派极窄 | `matlabc.py:27953` | `choices=("matlab", "c", "py", "js")` —— 硬编码 4 种 |

### 1.3 「声明 › 实现」的算子膨胀（实测，重要）

`_CROSS_LANG_KIND_META`（`matlabc.py:22161-22172`）声明 10 个跨语言算子。逐条比对「是否有产出点」：

| 算子 | 声明 | 有实现？ | 证据 |
| --- | --- | --- | --- |
| `py_unused_import` | ✅ | ✅ | `matlabc.py:7582` |
| `py_dup_params` | — | ✅ | `matlabc.py:7560` |
| `py_too_many_params` | — | ✅ | `matlabc.py:7551` |
| `py_missing_doc` | — | ✅ | `matlabc.py:7570` |
| `c_use_after_free` | ✅ | ✅ | `matlabc.py:7185` |
| `c_uninit_pointer` | — | ✅ | `matlabc.py:7155` |
| `c_array_oob` | — | ✅ | `matlabc.py:7171` |
| `c_missing_return` | — | ✅ | `matlabc.py:7195` |
| `c_unused_static` / `c_missing_guard` / `c_too_many_params` / `c_missing_doc` | — | ✅ | `matlabc.py:7107~7137` |
| `js_global_var` / `js_unused_import` / `js_too_many_params` / `js_missing_doc` | — | ✅ | `matlabc.py:7611~7649` |
| **`py_undefined_name`** | ✅ | **❌ 无** | 全仓仅 1 次出现（元数据表） |
| **`py_eval_usage`** | ✅ | **❌ 无** | 同上 |
| **`py_sql_injection`** | ✅ | **❌ 无** | 同上 |
| **`c_buffer_overflow`** | ✅ | **❌ 无** | 同上 |
| **`c_double_free`** | ✅ | **❌ 无** | 同上 |
| **`js_dangerous_call`** | ✅ | **❌ 无** | 同上 |
| **`js_unused_var`** | ✅ | **❌ 无** | 同上 |
| **`js_prototype_pollution`** | ✅ | **❌ 无** | 同上 |

**实测反证**：Python 样例含 `eval(user_input)` / `os.system("echo "+user_input)` / SQL 字符串拼接 → **一条未检出**；JS 样例含 `eval(code)` → **未检出**。

**测试为何"通过"**：`test_matlabc.py:1351` 直接喂**手工伪造**的 `{"kind": "py_eval_usage", ...}` 给 level 推导函数——**测的是元数据表本身，不是检测能力**。

### 1.4 已有误报（实测）

| 输入 | 期望 | 实际 | 性质 |
| --- | --- | --- | --- |
| `import os` + `os.system("echo "+x)` | `os` 已使用 | 报 **`py_unused_import`**：`os` 未使用 | ❌ 假阳（调用抽取未把 `os.system(...)` 记为对 `os` 的使用） |

### 1.5 完全空白的两项能力（实测 0 命中）

| 能力 | 检索面 | 命中 |
| --- | --- | --- |
| **动态库分析** | `dlopen` / `LoadLibrary` / `GetProcAddress` / `dlsym` / `LD_PRELOAD` / `.dll` / `.so` / `.dylib` | **0**（唯一含 "dynamic" 的是 MATLAB `eval/feval` 的动态**执行**，非动态**链接**） |
| **构建系统感知** | `Makefile` / `CMakeLists` / `pkg-config` / `meson` / `bazel` / `cargo.toml` / `LDFLAGS` / `-l<lib>` | **0** |

> 注：matlabc 有 `_match_c_bridge`（`matlabc.py:7885`），但它是 **MATLAB 外部调用名 ↔ C 函数名的字符串巧合匹配**，不含声明/ABI 语义。

### 1.6 rea 的动态库与语言能力（实测文件级）

| 能力 | 关键文件 | 事实 |
| --- | --- | --- |
| **Mach-O dyld 加载路径静态解析** | `src/domain/apple/dylibResolution.ts` | 支持 5 种加载命令（`LC_LOAD_DYLIB` / `LOAD_WEAK` / `REEXPORT` / `LAZY` / `UPWARD`）；展开 `@rpath/` `@loader_path/` `@executable_path/`；按 dyld4 dependents-first 顺序遍历；候选 outcome **九态**；解析状态 `resolved/conditional/unresolved/undetermined` |
| dyld 路径展开 | `src/domain/apple/dyldPaths.ts` | 逐段解析、符号链接安全（逃逸即标 `escapes-target`） |
| Mach-O 头部解析 | `src/artifacts/apple/MachoLoadCommandReader.ts` | `file_type` / `install_name` / `rpaths` / `dyld_environment` / `code_signature_present` |
| 完整性校验 | `src/artifacts/apple/DylibResolutionReader.ts` | 解析前后比对 `dev:ino:size:mtime:ctime` + 分块 sha256，**变即失败** |
| 发现项推导 | `src/domain/apple/dylibResolutionFindings.ts` | `required-load-unresolved` / `weak-load-unresolved` / `lazy-load-unresolved` / `earlier-rpath-candidate-absent` / `dyld-environment-present` |
| ELF | `pwntools-elf` provider | `inspect_binary_layout` / `inspect_recorded_crash` |
| PE / .NET | `src/dotnet/ManagedPeReader.ts` / `ManagedMetadataHeaps.ts` / `ManagedNativeBoundaryInspector.ts` | **自研 PE + CIL 元数据读取**，含**原生依赖声明** |
| **JS 语义分析（IR 级）** | `src/domain/javascript/javascriptSemanticIr.ts`(17.5KB) / `javascriptSemanticGraph.ts`(19KB) / `javascriptSemanticDataEffects.ts`(15.6KB) / `javascriptSemanticValues.ts`(18KB) / `javascriptSemanticProjection.ts`(22KB) | **真 IR + 数据效果 + 图查询**，非正则 |
| JS AST | `@babel/parser` 8.0.4 + `javascriptAstFingerprint.ts` | 真 AST + 指纹 |
| source→bundle 对比 | `sourceToBundleComparison.ts` + `@jridgewell/trace-mapping` | source map 解码 |
| 运行时观测 | `LldbCallTracer.ts` / V8 Inspector / CDP / Playwright / mitmproxy | 真实运行时证据 |
| 工程纪律 | `verify:module-boundaries` / `knip`（死代码）/ `jscpd`（重复）/ `scan:todos` / 96 个 `verify:*` 脚本 | 工业级 |

**rea 的 provider 生态（26 个）**：`ghidra` / `hopper` / `ida` / `binwalk` / `unblob` / `jadx` / `wakaru` / `evmole` / `native-macos` / `pwntools-elf` / `rea-dotnet-static` / `rea-cdp-browser` / `rea-playwright-*` / `rea-v8-inspector` / … 与 12 个客户端适配（Claude Code / Codex / Cursor / Gemini CLI / VS Code / …）。

### 1.7 缺什么数据（白帽必须诚实标注的缺口）

1. matlabc 在**真实大工程**（用户所称 991 文件）上各语言前端的**召回率**——本轮只用构造样例，未做大工程基线。
2. rea 在 **Windows DLL** 的实测——其 `docs/roadmap.md` 明确写 Windows P0 是「非托管、**非 DLL**」，故 **DLL 原生分析在 rea 亦属未验证区**。
3. matlabc 的**目标用户画像**（纯 MATLAB 用户 vs 多语言用户）未定义 → 直接决定 C++/Rust 的优先级。

---

## 2. 红帽 · 直觉与情绪（不伪装成事实）

| 对象 | 直觉 | 说明 |
| --- | --- | --- |
| matlabc 的 AI 层 | **可信、有料** | `agent_loop` / `flow` / `ask` / `mcp` 均为真实现；上一轮审计已核实 MCP 协议 5/5 正确 |
| matlabc 的多语言层 | **不安** | 宣传面（4 语言徽章、44 算子目录）显著大于实现面（C 8 条正则、Py 4 条、JS 4 条、C++/Rust/TS 为零、8 个算子无实现） |
| rea | **敬畏 + 距离感** | 工程纪律高一个数量级；但它是**另一条赛道**（无源码逆向），且依赖哲学完全相反 |
| 「融合」这件事 | **有诱惑也有警觉** | 诱：rea 的 dylib/IR/PE reader 正是 matlabc 最缺的；警：把 rea 变硬依赖会杀死 matlabc 的三条护城河（零依赖 / 离线 / Python 3.6） |

---

## 3. 黑帽 · 风险与最坏情况

| # | 风险 | 具体化 | 严重度 |
| --- | --- | --- | --- |
| R1 | **方向错配** | matlabc 卖点是「零依赖 / 无需 MATLAB / 离线 / 3.6 兼容」；rea 需要 Node 22+、32 依赖、本机 Hopper/Ghidra。硬绑 → 卖点死亡 | **P0** |
| R2 | **能力膨胀复刻** | 已存在 8 个「声明但无实现」的安全算子；若再按「再加 4 种语言」扩张，会把同一错误放大 4 倍，并把 29.6k 行单文件内核推向 40k+ | **P0** |
| R3 | **正则前端的天花板不可越** | C++ 模板/命名空间/重载、Rust 生命周期/宏/trait、TS 类型系统，行锚定正则**原理上做不到**；硬做产出大量假阳/假阴，**毒化确定性修复的信任基础** | **P0** |
| R4 | **最坏情况** | matlabc 沦为「什么语言都声称支持、什么都浅」的工具；同时三条护城河同时失守；而 P0-1 补丁缺陷（插入被实现为覆盖 → 删源码语句且自证 PASS）仍在 → **给会删代码的引擎加更多语言 = 放大风险** | **P0** |
| R5 | **安全边界扩大** | rea 明确声明「**不是沙箱**」；通过它读用户工程里的 `.so/.dll` = 把攻击面从「纯文本解析」扩大到「解析器漏洞 + 本地工具链执行」 | P1 |
| R6 | **许可与归属** | rea 是 MIT，设计可借鉴；但 `bridge/ghidra` 是 159KB Java、`third_party/*` 是带各自许可的子模块（jadx/binwalk/unblob/nativeaot/wakaru）→ **不可整体搬运**，只能设计借鉴 + 契约对齐 | P1 |
| R7 | **Windows 盲区** | rea 的 Windows P0 明确排除 DLL；即「接 rea」也**不能**立刻拿到 Windows DLL 分析能力 | P1 |
| R8 | **验证纪律缺失** | matlabc 已有测试大面积失败（上轮实测 129 失败 / 277 通过）；rea 有 96 个 `verify:*` + 9 个测试项目 + knip/jscpd。差距在「证据纪律」而非「努力程度」 | P1 |

---

## 4. 黄帽 · 价值与最佳情况

| # | 价值 | 为什么成立 |
| --- | --- | --- |
| V1 | **数学上最优的互补** | matlabc = **源码语义**（def-use / 污点 / 维度抽象解释）；rea = **二进制真相**（dylib 依赖 / 符号表 / 运行时调用）。二者交叉验证的结论，**任一单独工具都得不出** |
| V2 | **六语言方案可复用现有地基** | 已有 `_build_ext_model`（统一语言无关模型）+ `_apply_unified_gates`（统一门禁）+ 统一 SARIF/JSON 输出 —— **加语言是「填前端」不是「重构内核」** |
| V3 | **TS 是六者中性价比最高** | TS ≈ JS 前端 + 类型层。类型层能支撑**确定性、可验证**的检查（`implements` 完整性、字面量联合穷举），而不是模糊启发式 |
| V4 | **Python 可零依赖升级到真 AST** | Python 标准库自带 `ast` 模块 —— **升级不破坏零依赖护城河**，且 `ast` + `feature_version=(3,6)` 可与既有 `--check-py36` 门禁协同 |
| V5 | **rea 的 JS/IR 栈是「已验证的架构模板」** | `javascriptSemanticIr.ts` + `javascriptSemanticDataEffects.ts` 证明「JS 也能做 IR 级数据流」→ matlabc 的 JS/TS 升级**有现成参照，不必自己摸索** |
| V6 | **rea 本身就是 MCP server → 融合接口已存在** | **零代码侵入**：matlabc 作 MCP 客户端调用 rea 的 `inspect_macho` / `trace_dylib_loading` / `inspect_binary_layout` 即可获得动态库事实 |
| V7 | **rea 的证据纪律可直接修复 matlabc 的 P0-1** | rea 的 `coverage.status: complete\|partial` + `limitations[]` + `outcome: undetermined` 是一套「**宁可说未知，不假称完成**」的纪律。把它移植到自证门，可让「删了语句却报 PASS」变成「**拒绝应用 + 列出未知**」 |
| V8 | **二进制导出证据可保护确定性修复** | 「内部无调用」≠「可删除」。若导出表有该符号，就应**禁止自动删函数**——这直接命中 P0-1 的伤害面 |

---

## 5. 绿帽 · 替代方案（5 条路）

| 方案 | 内容 | 优 | 劣 |
| --- | --- | --- | --- |
| **A 原地扩语言** | 在 `matlabc.py` 内把 C 前端升级真 AST，补 C++/Rust/TS | 无新架构 | 内核从 29.6k 膨胀到 40k+；正则做不到 C++/Rust；违背「拒绝占位符」 |
| **B 外挂前端** | 新建 `frontends/` + 统一 IR，内核只消费 IR | 内核不膨胀、语言可缺席、可分期 | 需先定义 IR 契约 |
| **C MCP 联邦** | 不自己实现二进制/重语言，作**编排者**调用外部（clangd / rust-analyzer / tsserver / rea） | 零依赖不破、能力立即到位 | 引入运行期外部依赖（须可缺席 + 降级） |
| **D 先修地基再扩** | 先修 P0-1 与 8 个空算子/误报，再按 TS→C++→Rust 扩 | 满足「真实实现」硬要求 | 短期看不到「新语言」 |
| **E 绑定 rea 做双向验证产品** | 直接围绕 rea 建「源码↔二进制一致性」产品 | 差异化强 | 放弃 matlabc 定位与护城河 |

---

## 6. 蓝帽 · 综合结论

**矛盾点（必须显式记录，不用乐观抵消）**：
- 矛盾 1：用户要「扩到 6 语言」（诉求）↔ 当前前端是正则、地基不牢（事实）
- 矛盾 2：融合 rea 价值极高（V1/V5/V6/V7）↔ 会破坏零依赖/离线/3.6 三条护城河（R1）

**综合判断：采纳 D → B → C 的组合，拒绝 A 与 E。**

| 决定 | 理由 |
| --- | --- |
| ✅ **D 先修地基** | P0-1（补丁把插入实现为覆盖、删源码语句且自证 PASS）、8 个空算子、`py_unused_import` 误报——不修这些，「加语言」只是把风险乘 4 |
| ✅ **B 前端外挂化** | 内核停止膨胀；C++/Rust/TS 各自独立、可按需缺席；符合「每一步真实现」 |
| ✅ **C MCP 联邦** | 动态库/二进制能力**运行期可选**获取（rea 已有 139 工具）；无 rea 时优雅降级为「未知」而非报错 |
| ❌ **拒绝 A** | 正则推到 C++/Rust/TS 必然做不到真，直接违反用户「拒绝任何形式占位符代码」的硬要求 |
| ❌ **拒绝 E** | 把产品押在 rea 上 = 放弃 matlabc 自身定位 |
| ❌ **明确不做** | 完整 C++/Rust 类型系统自研；移植 rea 的 TS 源码；replay/沙箱执行（rea 已退役该方向） |

---

## 7. 头脑风暴 · 苏格拉底式追问与收敛

```
原始意图：
  让 matlabc 支持 C/C++/Python/Rust/JS/TS 的深度分析，能分析动态链接库，并与 rea 深度融合。

追问过程（关键 Q&A）：
Q1 澄清 —— 「深度分析」具体指什么？
A1  必须可分级，否则「深度」是空词 → 定义 L0~L4 能力阶梯（见 §8）。

Q2 溯源 —— 为什么需要 C++ / Rust / TS？
A2  用户工程是混合栈（MATLAB + MEX C + Python + JS，将来 Rust/TS）；
    真实痛点是【跨语言边界的调用与数据流不可见】，而非「多认几个后缀」。

Q3 假设挑战 —— 如果「每个语言都自己做真 AST」这个前提不成立（人力/时间/维护）呢？
A3  那就必须走外挂 + 联邦；因为行锚定正则**原理上**做不到 C++/Rust/TS。

Q4 边界 —— 什么场景不适用？
A4  需要完整类型系统推导的场景（C++ 模板实例化、Rust trait 解析、TS 泛型推断）。
    轻量静态工具**不应承诺**，而应显式标「未知」。

Q5 替代 —— 还有别的办法达到「看懂多语言工程」吗？
A5  用现成语言服务器的协议输出（clangd / rust-analyzer / tsserver / pyright），
    而不是自己写解析器 → 这就是方案 C 的核心。

Q6 代价 —— 接 rea 的代价是什么？
A6  部署复杂度（Node 22 + 本机 Hopper/Ghidra）+ 安全面扩大 + 与零依赖冲突
    → 必须做成【可选、可缺席、有降级、默认关闭】。

候选方案（≥2）：A 原地扩 / B 外挂前端 / C MCP 联邦 / D 先修地基 / E 绑定 rea

选定方案 + 理由：
  D（先修地基）→ B（前端外挂 + 统一 IR）→ C（MCP 联邦取二进制事实）
  理由：唯一同时满足 ① 用户「真实实现、不留占位」的硬要求
        ② 不破坏 matlabc 零依赖 / 离线 / Python 3.6 三条护城河
        ③ 每一步都能立刻验收（D 有最小复现；B 有语言阶梯；C 有 MCP 握手与降级）
```

---

## 8. 六语言分析深度方案（L0–L4 阶梯 + 逐语言落地）

### 8.1 通用能力阶梯（所有语言共用同一把尺）

| 级别 | 名称 | 产出物 | 验收方式 |
| --- | --- | --- | --- |
| **L0** | 识别 | 文件收集、语言判定、编码/BOM、**构建系统探测** | 清单与文件系统一致 |
| **L1** | 结构 | 文件/类/函数/方法/字段；导入导出；符号表；头↔实现映射 | 与 `grep` 计数一致 |
| **L2** | 语义 | AST/IR、类型标注、作用域、宏/泛型（近似）、**CFG** | 对黄金样例逐条断言 |
| **L3** | 跨过程 | 调用图（含间接/虚函数/函数指针）、def-use、数据流、污点 | 与 `ctags`/语言服务器对照 |
| **L4** | 证据级 | FFI/ABI 边界、动态库依赖、**与二进制交叉验证**、置信度与「未知」显式标注 | 交叉验证矩阵可复现 |

### 8.2 逐语言现状 → 目标 → 关键动作

#### C —— 现状 L1.5（正则），目标 L2 + L3

| 动作 | 细节 | 依据 |
| --- | --- | --- |
| ① 扩后缀 | `collect_c_files` 增 `.cc/.cpp/.cxx/.c++/.C`（当前仅 `.c/.h`，`matlabc.py:6856`） | 实测 C++ 0 文件 |
| ② 预处理 | 实现**最小条件编译求值**（`-D` 集合 + `#if`/`#ifdef`/`#elif`），至少**跳过 `#if 0` 块** | 当前 `#if 0` 内代码也会被分析 → 假阳 |
| ③ 多行签名 | 允许 `{` 不在同行、支持 K&R 风格 | `_RE_C_FUNC` 要求 `) {` 同行（`matlabc.py:6835`） |
| ④ 函数指针/回调 | 建 `{变量: 签名}` 映射 → 图上的**间接调用边** | **复用 P225 已验证的「构造赋值扫描」方法论** |
| ⑤ 构建系统 | 解析 Makefile/CMakeLists 的 `-l/-L/-I/-D` → **动态库直接依赖的初始输入** | 当前 0 命中（§1.5） |

> **验收**：真实 C 工程函数识别率 ≥99%；经函数指针的调用边有量化召回基线；`#if 0` 不再产生告警。

#### C++ —— 现状 L0（完全不可见），目标 L1 + L2（受限），**明确不承诺模板实例化**

| 动作 | 细节 |
| --- | --- |
| ① 收集 | `.cpp/.cc/.cxx/.hpp/.hxx/.ipp/.tpp` |
| ② 命名空间 | `namespace` → 限定名 `ns::Class::method`；**复用 MATLAB 的 `qualified_index` + `prefer_class` 消歧方法论**（P225 系列已验证） |
| ③ 类/继承/虚函数 | `class/struct` → 成员表 + 基类链；虚方法标注 → **虚调用点**（多目标边） |
| ④ `extern "C"` | → **MEX / FFI 入口清单**；与既有 `--mixed` 结合，把「名字巧合匹配」升级为「**声明匹配 + ABI 契约**」 |
| ⑤ 模板 | 仅**声明级**（记录模板名与参数），明确不做实例化 |

> **验收**：类方法识别、继承链、虚调用点、`extern "C"` ABI 入口清单。

#### Python —— 现状 L1.5（正则，含假阳），目标 L2 真 AST + L3

| 动作 | 细节 |
| --- | --- |
| ① **换用标准库 `ast`** | **零依赖仍然成立**（`ast` 是标准库）；函数/类/装饰器/导入/调用全部精确，杜绝行锚定遗漏 |
| ② 修假阳 | `py_unused_import` 改为按 `ast.Name`/`ast.Attribute` **使用计数**，而非「调用名集合」 |
| ③ 兑现 3 个空算子 | `py_eval_usage`（`ast.Call` → `eval/exec`）、`py_sql_injection`（`%`/f-string/`+` 拼进 execute 参数）、`py_undefined_name`（模块级 Name 收集 + 内建表） |
| ④ L3 | 跨函数调用图 + 参数/返回传播（`ast` 足够） |
| ⑤ 协同 | 与 `--check-py36` 协同：`ast.parse(..., feature_version=(3,6))` |

> **验收**：3 个空算子全部有**真实现 + 用真实源码（非伪造输入）的单测**；假阳归零。

#### Rust —— 现状 L0，目标 L1 + L2（受限），**明确不承诺 trait 解析与生命周期**

| 动作 | 细节 |
| --- | --- |
| ① 收集 + `Cargo.toml` | 解析 `[dependencies]` → **依赖图的第一来源**（现代「动态链接」的对应物） |
| ② 结构 | `mod/fn/struct/enum/impl/trait` + 可见性（`pub`） |
| ③ **`unsafe` 块** | 安全审计高价值信号（逐块标注 + 上下文） |
| ④ FFI | `extern "C"` / `#[no_mangle]` / `#[repr(C)]` → **导出符号清单**（与二进制交叉验证的锚点） |
| ⑤ CFG | `match` / `if let` / `loop` → CFG 骨架 |

> **验收**：`impl` 方法归属、`pub` 导出清单、`unsafe` 热点清单、FFI 导出符号。

#### JavaScript —— 现状 L1.5（类方法漏抽），目标 L2 IR 级 + L3

| 动作 | 细节 |
| --- | --- |
| ① 类/对象方法 | `class X { m() {} }`、`{ m() {} }`、`x.m = () => {}`（当前**全部漏抽**） |
| ② 模块系统 | ESM/CJS 双向 + **动态 `import()`**；`package.json` 的 `exports` **条件解析**（rea 已证明这是真问题） |
| ③ 兑现 3 个空算子 | `js_dangerous_call`（`eval`/`Function`/`innerHTML` 赋值）、`js_prototype_pollution`（`__proto__`/`constructor.prototype` 赋值路径）、`js_unused_var` |
| ④ L2 数据流 | **直接采用 rea 的架构**（值 → 数据效果 → 图，见 `javascriptSemanticIr.ts` / `javascriptSemanticDataEffects.ts`），matlabc 侧做轻量版 |

> **验收**：类方法抽取正确；3 个空算子真实现；动态 `import()` 边；成员路径深度受控。

#### TypeScript —— 现状 L0（硬报错），目标 L1 + L2 类型层（受限）。**六者中性价比最高**

| 动作 | 细节 |
| --- | --- |
| ① 收集 | `.ts/.tsx/.mts/.cts` + `tsconfig.json`（`paths`/`extends`/`strict`） |
| ② **类型层提取**（不追求完整类型检查） | `interface`/`type`/`enum`/泛型参数/`readonly`/`?`/联合与交叉 → **类型契约清单** |
| ③ 类型驱动的**确定性**检查 | 从 `interface` 得「必须实现的成员」→ 检 `implements` 完整性；从字面量联合得「穷举 switch 检查」。**这是确定性可验证的，不是模糊启发式** |
| ④ `.d.ts` | → **对外 API/ABI 契约**（与 DLL「导出表」概念对齐） |
| ⑤ 其他 | 装饰器、`abstract` 类、`import type` |

> **验收**：类型契约清单、`implements` 完整性检出、`.d.ts` 契约导出。

### 8.3 建议优先级（按「单位投入产出 × 用户真实需求」）

| 序 | 语言 | 理由 |
| ---: | --- | --- |
| 1 | **TypeScript** | 复用 JS 前端 + 类型层；产出确定性检查；用户栈新增需求明确 |
| 2 | **Python** | 标准库 `ast` 即可真 AST，**零依赖不破**；顺带修假阳 + 兑现 3 个空算子 |
| 3 | **C++** | MEX/FFI 边界是 MATLAB 用户的真实痛点；复用 P225 消歧方法论 |
| 4 | **JavaScript（IR 升级）** | 有 rea 的架构模板；兑现 3 个空算子 |
| 5 | **Rust** | 新栈，需求真实但当前占比可能低；FFI 导出与二进制交叉验证价值高 |
| 6 | **C（预处理 + 函数指针）** | 增量打磨，风险最低，随时可做 |

---

## 9. 动态链接库（DLL/.so/.dylib/FFI）深度分析方案

> matlabc 此项 **完全空白**（§1.5 实测 0 命中）；rea 此项 **最成熟**（§1.6）。

### 9.1 先定义坐标系 —— 否则「分析 DLL」是个空命题

动态库分析应覆盖 **5 类事实**：

| 类 | 名称 | 载体 | 可读性 |
| --- | --- | --- | --- |
| ① | **链接期依赖（静态可见）** | `-l<lib>` / `#pragma comment(lib)` / `build.rs` / `Cargo.toml` / `package.json` | 源码可读 ✅ |
| ② | **加载期依赖（二进制可读）** | Mach-O `LC_LOAD_DYLIB*` / ELF `DT_NEEDED` / PE Import Table | 需二进制 |
| ③ | **导出/导入符号** | Mach-O 导出 trie / ELF `.dynsym` / PE Export Table | 需二进制 |
| ④ | **运行时解析（动态）** | `dlopen`/`dlsym`、`LoadLibrary`/`GetProcAddress`、`LD_PRELOAD`、`@rpath` 解析、`node-gyp`/`cgo`/`PyO3`/`napi` | 部分源码可读 |
| ⑤ | **FFI 边界契约** | 调用约定、参数类型映射、字符串所有权、`extern "C"` 面 | 源码可读 ✅ |

### 9.2 matlabc 侧可独立做的（零依赖）—— 「源码侧动态库表面」

| 检测项 | 载体 | 输出 |
| --- | --- | --- |
| `dlopen/dlsym/dlclose` 调用点 | C/C++ | 动态加载节点，**目标未知 → L4 未知** |
| `LoadLibrary/GetProcAddress` | C/C++ (Win) | 同上 + 字符串字面量目标提取 |
| `LD_PRELOAD` / `DYLD_INSERT_LIBRARIES` | 构建脚本 / CI / env | **劫持风险**告警 |
| `extern "C"` 块 | C++ | FFI 导出契约（名字不 mangling） |
| `#[no_mangle]` + `#[repr(C)]` | Rust | FFI 导出契约 |
| `__attribute__((visibility("default")))` | C/C++ | 显式导出 |
| `node-gyp` / `binding.gyp` / `napi` | JS | 原生扩展边界 |
| `cgo`（`import "C"`）、`PyO3`/`cffi`/`ctypes` | Go/Python | FFI 边界 |
| Makefile/CMake 的 `-l/-L`、`Cargo.toml [dependencies]`、`package.json` deps | 构建系统 | **直接依赖图** |
| 字符串常量中的 `*.so`/`*.dll`/`*.dylib` | C/C++/JS | 运行期目标线索 |

> **产出**：`dynamic_surface.json` —— 上述事实的归一化清单，每条带 `{file, line, kind, confidence, unknown_reason?}`。

### 9.3 与 rea 联邦获取「二进制侧真相」（可选、可缺席、优雅降级）

matlabc 作 **MCP 客户端**调用 rea 已有工具：

| rea 工具 | 得到的事实 |
| --- | --- |
| `inspect_macho` | `file_type` / `install_name` / `rpaths` / `dyld_environment` / 代码签名 |
| `trace_dylib_loading` | **dyld 加载路径解析**（含 `@rpath` 展开、九态候选 outcome、`resolution.status`） |
| `inspect_binary_layout`（pwntools-elf） | ELF 布局 / 动态节 |
| `inspect_managed_native_boundaries` | PE 原生依赖声明 |
| `demangle_swift` / `inspect_signature` | ABI / 签名 |

> ⚠️ **诚实边界**：rea 的 `docs/roadmap.md` 明确说 Windows P0 是「非托管、**非 DLL**」→ **接 rea 也不能立刻拿到 Windows DLL 分析**（见 R7）。

### 9.4 交叉验证矩阵 —— 这是融合的核心价值所在

| matlabc（源码侧） | rea（二进制侧） | 合并结论 | 等级 |
| --- | --- | --- | --- |
| Makefile 有 `-lmylib` | `.so` 有 `DT_NEEDED libmylib.so` | 依赖确认 | ✅ 一致 |
| 声明 `extern "C" int api_foo(...)` | 导出表有 `api_foo` | ABI 契约一致 | ✅ 一致 |
| 声明 `extern "C" int api_bar(...)` | 导出表**无** `api_bar` | **ABI 违约** | 🔴 高危 |
| **无** `-l` 记录 | `.so` 有 `DT_NEEDED libfoo.so` | **构建脚本漏声明** | 🔴 高危 |
| `helper()` 内部无调用 | 导出表**有** `helper` | **对外 ABI，禁止自动删** | 🟠 保护修复 |
| `dlopen(user_input)` | — | **不可判定** | ⬜ 显式 unknown |

**最后两行是本次分析的关键洞察**：
- 「内部未调用」**不等于**「可删除」。一旦有二进制导出证据，就应**禁止确定性修复自动删函数**。
- 这恰好**命中 P0-1 的伤害面**（补丁删掉整条语句却自证 PASS）——动态库分析不只是新功能，还是**修复引擎的安全护栏**。

### 9.5 落地阶梯

| 阶段 | 依赖 | 内容 | 验收 |
| --- | --- | --- | --- |
| **D0** | 零依赖，可立即做 | 构建系统解析 + FFI 关键字扫描 + 字符串字面量线索 → `dynamic_surface.json` | 清单产出，与人工核对一致 |
| **D1** | 零依赖 | `dlopen`/`LoadLibrary` 调用图节点 + `unresolved` 页展示「动态加载，目标未知」 | 图上可见；不误报为「缺失调用」 |
| **D2** | 需 rea（可选） | MCP 联邦 → 交叉验证矩阵 → `cross_check.json` | 无 rea 时**降级不报错**；6 类结论可复现 |

---

## 10. rea 深度融合方案与计划

### 10.1 融合的 5 条通道（按侵入度从低到高）

| 通道 | 侵入度 | 内容 | 推荐 |
| --- | --- | --- | --- |
| **① 协议级** | **零侵入** | matlabc 作 MCP **客户端**调 rea 的 139 工具 | ⭐ **首选** |
| **② 契约级** | 低 | 把 rea 的 zod → JSON Schema 输出契约作为 matlabc 证据模型的参照，实现「同一事实双来源可对比」 | ⭐ 推荐 |
| **③ 证伪级** | 低 | 借 rea 的 `coverage.status: complete\|partial` + `limitations[]` + `outcome: undetermined` **纪律**，重塑 matlabc 自证门 | ⭐ 推荐（直接修 P0-1） |
| **④ 架构级** | 中 | 借 rea 的 provider 中立契约 + 容器/内核边界 + `verify:*` 真实验证通道，重整 matlabc 模块边界（解 `renderers`↔`matlabc` 循环依赖） | ⭕ 中期 |
| **⑤ 代码级** | **高** | 移植 rea 的 TS 源码 | ❌ **不推荐**（语言栈不同、依赖哲学相反、破坏零依赖卖点） |

### 10.2 分阶段计划（6 阶段，每阶段有验收）

#### P0 · 地基（阻断性，先做）
- 修 `matlabc.py:12537` 的 `"ins"` 覆盖语义 → **真正插入**（复用已正确实现的 `"ins_before"` 切片逻辑）
- 自证门升级：加 **AST/语句保持校验**（语句数、函数签名、控制流关键字**不得减少**）+ 借 rea 的 unknowns 纪律
- 8 个空算子：**要么实现（Py/JS 用 `ast`/Babel 可达）要么从算子目录下架**（消除声明膨胀）
- 修 `py_unused_import` 假阳
- **验收**：此前「删语句」的最小复现变为「**拒绝应用 + 列出未知**」；算子目录与实现 **1:1 对齐**

#### P1 · 语言前端外挂化（架构）
- 新建 `frontends/`：`base.py`（统一 IR 契约）+ `c/` `cpp/` `py/` `js/` `ts/` `rust/`
- 内核 `matlabc.py` **只消费 IR**，不再内嵌具体语言正则
- **验收**：新增语言**不改内核**；内核行数不增长

#### P2 · TS + Python 打样（性价比最高两项）
- TS：类型契约 + `implements` 完整性 + `.d.ts` 导出契约
- Python：`ast` 化 + 3 个空算子真实现 + def-use
- **验收**：真实工程实测；误报率下降有量化

#### P3 · 动态库表面（零依赖）
- D0 + D1：构建系统 `-l/-L`、`Cargo.toml`、`package.json`、FFI 关键字、`dlopen/LoadLibrary` 图节点
- **验收**：`dynamic_surface.json` 产出；`dlopen` 目标不明时进 `unresolved` 而非静默

#### P4 · rea MCP 联邦（可选能力，优雅降级）
- 加 `--binary-evidence` 开关：**检测到 rea MCP 才启用**，否则输出「未提供二进制证据」
- 实现 §9.4 交叉验证矩阵 → `cross_check.json` + 高危差异（ABI 违约 / 构建漏声明）
- **验收**：MCP 握手成功；**无 rea 时不报错只降级**；矩阵 6 类结论可复现

#### P5 · 纪律迁移（长期治理）
- 借 rea 的 `verify:*` 思路，把 matlabc 护栏脚本化（已有 `tools/check_*` 雏形）
- 解 `renderers` ↔ `matlabc` 循环依赖（参照 rea 的 `verify:module-boundaries`）
- **验收**：循环依赖归零；死代码 / 重复代码有报告

### 10.3 明确不做（防止跑偏）

| 不做 | 理由 |
| --- | --- |
| 把 rea 变成构建期/运行期**必需**依赖 | 破坏零依赖 / 离线 / 3.6 三条护城河（R1） |
| 移植 rea 的 TS 源码 | 语言栈不同、依赖哲学相反（⑤ 通道） |
| 自研完整 C++/Rust 类型系统 | 原理上超出轻量静态工具的合理承诺边界（R3） |
| 做 replay / 沙箱执行 | rea 已在 `roadmap.md` 中**退役**该方向（PR #555 / #572） |

---

## 11. 一句话结论

> **matlabc 不缺「连大模型的能力」，也不缺「再认几种后缀的勇气」；它缺的是三样东西：**
> **① 一个不再删源码的修复引擎（P0-1）；**
> **② 一套把语言前端从 29.6k 行内核里拆出来的 IR 契约（B）；**
> **③ 一条在不破坏零依赖前提下拿到二进制真相的通道（C = rea MCP 联邦）。**
>
> **六语言里先把 TS 与 Python 做真（性价比最高，且都不破坏零依赖）；动态库先做「源码侧表面」（D0/D1），再谈联邦交叉验证（D2）；rea 只走「协议级 + 契约级 + 证伪级」三条低侵入通道，绝不搬运它的代码。**

---

## 12. 证据索引（可复现命令）

```bash
# 语言分派（只有 4 种）
grep -n 'add_argument("--lang"' malabc/matlabc.py            # L27953 → matlab/c/py/js

# C++ 不可见的根因
sed -n '6852,6864p' malabc/matlabc.py                        # 只收 .c/.h

# 8 个「声明但无实现」的算子（仅出现在元数据表）
grep -rn "py_eval_usage\|c_double_free\|js_prototype_pollution" malabc/

# 六语言实测（本报告所用样例与结果）
python _analysis/langprobe/make_samples.py

# 动态库 / 构建系统：0 命中
grep -rn "dlopen\|LoadLibrary\|dlsym\|LD_PRELOAD\|\.dylib" malabc/
grep -rn "Makefile\|CMakeLists\|cargo.toml\|LDFLAGS" malabc/

# rea 的 dylib 解析引擎
cat rea/src/domain/apple/dylibResolution.ts
cat rea/src/artifacts/apple/DylibResolutionReader.ts

# rea 的 JS IR 级语义分析（架构模板）
ls rea/src/domain/javascript/javascriptSemantic*.ts
```

> 注：`rea` 的克隆命令为 `git clone git@github.com:morluto/rea.git`（SSH 通道，本机 HTTPS:443 被墙）。
