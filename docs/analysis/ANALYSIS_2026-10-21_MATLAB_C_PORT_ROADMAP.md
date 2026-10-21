# ANALYSIS 2026-10-21：MATLAB → C 移植对接路线（三轮回顾 + 30 轮计划）

> 归档依据：用户长期偏好「深度分析 / 规划类工作必须归档并维护索引」。
> 本文覆盖：① 前两轮（插件 1.5.2、P0 移植地基）② 本轮（R9 真编译 + 双侧约束 JSON）
> ③ 后续 R10–R30 的可执行计划 ④ 自我复盘与下次建议。
> 关联提交：`c71c475`（1.5.2）、`791b70a`（P0 移植地基）、本轮提交（R433）。

---

## 0. 摘要与结论（TL;DR）

- **定位**：本仓已是「能同时读懂 MATLAB 和 C」的分析器；近三轮补上了「能把 MATLAB 的**有限算子**
  确定性映射到 C，并用 golden + 真编译证明」的最小闭环。
- **判断**：当前最大缺口已从「没有 C 落点」变成「**没有表达式级 AST / 类型形状事实**」——
  算子层只能覆盖单行赋值，控制流、切片、对象、多维广播仍未进入确定性段。
- **下一步**：R10–R14 扩算子与编译矩阵，R15–R17 补 MIR/类型事实与四条语义规则验证，
  R22 把 `--mixed` 升级为签名级桥接。

---

## 1. 方法与联动

| 技能 | 贡献维度 | 产出 |
| --- | --- | --- |
| `superpower` | 定界 / 盘点 / 差距根因 / 引领性结论 | 三轮定位与 30 轮优先级 |
| `brainstorming` | 发散 30 条 → 收敛评分矩阵 | 适配器、算子层、CI 编译矩阵入选；全自动 m2c 放弃 |
| `self-improvement` | GRAI/KPT 复盘 | 4 条“下次遇到 X 就做 Y”的规则 |
| `verification-before-completion` | 证据先行 | 所有“已通过”均附命令与读数 |

---

## 2. 三轮回顾

### 2.1 第一轮：插件 1.5.2（大纲 + site 级 HTML）

| 问题 | 根因 | 修复 |
| --- | --- | --- |
| 大纲“加载不出来” | PRMLT 的 demo 多为**脚本**，服务端透出内部伪符号 `<script>` 或 0 个 | 服务端 `_script_symbols()` 按 `%%` 分节；无分节用文件名占位；客户端兜底同形 |
| 插件只有单页报告 | `--html` 只回答“整体什么样” | 新增 `matlabc.generateSite`，调用 `--browse` 出多页站点 `.matlabc/site/index.html` |
| 仓库内调试找不到 `matlabc.py` | `context.extensionPath` 只在装好的 vsix 成立 | `findMatlabcPy()` 依次试 LSP 同目录/扩展根/仓库根/工作区 |

证据：`lsp_selftest --symbol 4/4`、`--doc 52/52`、`check_symbol_ranges OK`、
`node vscode/test_extension.js 8/8`、样例站点 29 个页面。

### 2.2 第二轮：P0 移植地基（`791b70a`）

| 交付 | 文件 | 状态 |
| --- | --- | --- |
| C ABI 契约 | `c_runtime/include/mlc.h` | ✅ |
| 最小运行时 | `c_runtime/src/mlc_runtime.c` | ✅ |
| 算子 C 落点 | `c_runtime/include/mlc_ops.h`、`src/mlc_ops.c` | ✅ add/sum/index；transpose/matmul 显式 `MLC_UNIMPLEMENTED` |
| 双侧适配器 | `translate/adapters.py`（ADP-1/2/3） | ✅ |
| MATLAB→算子→C | `translate/operators.py`（10 算子） | ✅ |
| 保真执行器 | `translate/fidelity.py` + `translate/golden/*.json`（5 个） | ✅ |
| 移植台账 | `port_ledger.json` + `translate/port_ledger.schema.json` | ✅ |
| 门禁 | `tools/check_translate_port.py`（TP1–TP4） | ✅ |

### 2.3 第三轮（本轮）：R9 真编译 + 双侧约束 + 归档

| 交付 | 文件 | 状态 |
| --- | --- | --- |
| 双侧约束 JSON | `translate/contracts/matlab_c_constraints.json` | ✅ 机器可读 |
| TP1b 约束对账 | `tools/check_translate_port.py::check_constraints` | ✅ 与 `mlc.h`/`rules`/`adapters` 双向核对 |
| C 编译器发现 | `translate/fidelity.py::find_c_compiler` 支持 `ziglang` | ✅ `python -m ziglang cc` |
| `--require-c` | 无编译器判红（CI 用） | ✅ |
| `--sync-ledger --write` | 按 C 结果升级台账 | ✅ add/sum/index → `verified` |
| CI 编译矩阵 | `.github/workflows/port-ci.yml`（ubuntu + windows） | ✅ |
| 本轮归档 | 本文件 | ✅ |

**本轮实测读数**

```
check_translate_port: OK（TP1–TP4 全绿；golden 5/5；C 3/3；台账 5 条）
SELFTEST COUNTS {"bad": 0, "good": 13}
pytest tests/test_translate_port.py: 18 passed
台账：m2c.op_add verified / m2c.op_sum verified / m2c.op_index verified
      m2c.op_transpose not_started / m2c.op_matmul not_started
```

> 诚实边界：`transpose` / `matmul` 的 C 落点仍返回 `MLC_UNIMPLEMENTED`，
> 台账保持 `not_started`；Python 参考实现已通过，但**不冒充 C 已验证**。

---

## 3. 双方约束（机器可读）

JSON：`translate/contracts/matlab_c_constraints.json`（由 TP1b 与代码双向核对）。

| 维度 | MATLAB 侧 | C 侧 |
| --- | --- | --- |
| 索引基准 | 1-based | 0-based（`mlc_op_index` 唯一做 `-1`） |
| 内存序 | 列主序 | 行主序（`strides` 以元素为单位） |
| 默认数值类型 | double | `MLC_F64`（对外禁止裸 `double*`） |
| 隐式扩展 | 自动广播 | 显式广播（`mlc_op_add` 仅标量/同形） |
| 整数溢出 | 非 UB 语义 | UB，必须显式防护 |
| 错误模型 | `MException` | `mlc_status`：0=OK / 1=ERR / 2=UNIMPLEMENTED |
| 可变参数 | `varargin/varargout` | ABI 边界禁止 |
| 空值 | `[]` | `numel==0, data==NULL` |
| 逻辑索引 | 支持 | 不直接支持（需显式掩码） |
| 所有权 | copy-on-write | `owns_data` / view 不拥有 |

规则映射：`IDX-1`、`ORDER-1`、`EXPAND-1`、`INT-1`；适配规则：`ADP-1`、`ADP-2`、`ADP-3`。

---

## 4. 架构总图

```
MATLAB 参考实现（语义唯一事实源）
        │ ① 语义事实：AST + shape/dtype + 调用图
        ▼
   MIR / 事实库（translate/mir.py + translate/facts.py）      ← R15/R16
        │ ② 规则映射：IDX-1 / ORDER-1 / EXPAND-1 / INT-1
        ▼
   算子目录（translate/operators.py，10 个）
        │ ③ C 发射 + 适配器胶水（ADP-1/2/3）
        ▼
   C 落点（c_runtime/*，已有 add/sum/index）
        │ ④ golden + 真编译（translate/fidelity.py，zig/gcc/clang）
        ▼
   移植台账 + 门禁（port_ledger.json + TP1–TP4 + CI 矩阵）
```

---

## 5. 30 轮计划（R1–R9 已完成，R10–R30 排程）

| 轮 | 交付 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| R1 | `mlc.h` ABI 契约 | 头文件结构 + 禁止裸指针 | ✅ |
| R2 | `mlc_runtime.c` | 形状/步长/所有权/错误码 | ✅ |
| R3 | `mlc_ops.c` add/sum/index | 结构检查通过 | ✅ |
| R4 | 双侧适配器 ADP-1/2/3 | 配对 + 两侧胶水 | ✅ |
| R5 | MATLAB→算子→C（10 算子） | sample 全部可识别 | ✅ |
| R6 | fidelity + 5 golden | Python 5/5 | ✅ |
| R7 | 台账 + schema | 5 条、状态合法 | ✅ |
| R8 | TP1–TP4 门 + 单测 | 18 测 + 自证 13 条 | ✅ |
| R9 | 真编译（zig）+ `--require-c` + 台账同步 | C 3/3，台账升级 verified | ✅ |
| R10 | 双侧约束 JSON + TP1b | 与 `mlc.h`/rules/adapters 双向一致 | ✅ |
| R11 | CI 编译矩阵（ubuntu/windows） | `--require-c` 两平台绿 | ✅（工作流已落，待远端跑） |
| R12 | SUB/MUL/DIV/MEAN/MAX 的 C 落点 | 每算子 ≥1 golden | ⏳ |
| R13 | 多维广播（EXPAND-1） | 2D/行/列/标量夹具 | ⏳ |
| R14 | transpose/matmul C 实现 | 去掉 `MLC_UNIMPLEMENTED` | ⏳ |
| R15 | 切片 `x(i:j)` / `end` | IDX-1 边界夹具 | ⏳ |
| R16 | MIR 表达式 IR | assign/call/index/binary/control | ⏳ |
| R17 | shape/dtype 事实接入维度引擎 | 事实可枚举、可回放 | ⏳ |
| R18 | 四条语义规则 `verified_by` | `verification_census verified=4` | ⏳ |
| R19 | INT-1 溢出语义（i32/i64） | 溢出夹具 + 不返回错值 | ⏳ |
| R20 | 错误映射表 | 每个对外函数声明错误行为 | ⏳ |
| R21 | 所有权/别名测试 | ASan/Valgrind（CI） | ⏳ |
| R22 | 自动生成台账条目 | 台账 ⇄ 函数清单双向 | ⏳ |
| R23 | `--mixed` 签名级桥接 | 参数/类型/返回不匹配报警 | ⏳ |
| R24 | M/C 漂移报告 | 模块 drift = 0 | ⏳ |
| R25 | 影子双跑（录制回放） | 同输入同输出 | ⏳ |
| R26 | 性能预算 | 每模块 ≤ 预算 | ⏳ |
| R27 | 内存预算 | 峰值 ≤ 预算 | ⏳ |
| R28 | CI 矩阵 + sanitizers | 三编译器全绿 | ⏳ |
| R29 | 移植看板/趋势 | 覆盖率/保真率/规则率可查 | ⏳ |
| R30 | 首个完整纵向切片 | 1 模块 3 函数端到端 verified | ⏳ |

---

## 6. 指标与门禁

| 指标 | 定义 | 目标 |
| --- | --- | --- |
| 移植覆盖率 | `verified / in_scope` | 逐阶段递增（棘轮） |
| 保真率 | golden 通过 / 总数 | 100% |
| C 编译通过率 | C 用例 ok / 已实现算子用例 | 100% |
| 规则验证率 | `verified_by` 非空 / 被使用规则 | 100% |
| 漂移数 | 统一图中 M/C 不一致函数对 | 0 |
| 性能/内存 | C / 预算 | ≤ 1.0 |

门禁：TP1（ABI）/ TP1b（双侧约束）/ TP2（适配器）/ TP3（算子）/ TP4（保真+台账），
CI 用 `--require-c` 禁止“没编译器也算绿”。

---

## 7. 风险与回退

| 风险 | 对策 |
| --- | --- |
| 浮点不逐位相等 | 每函数声明 abs/rel/ULP；先对整数/逻辑/索引做 100% 精确 |
| 列主序/1-based | IDX-1/ORDER-1 + 属性测试 |
| 整数溢出 UB | INT-1 + 显式防护 + 溢出夹具 |
| 无编译器环境 | `--require-c` 在 CI 判红；本地显式 `skipped` 并记录原因 |
| 台账虚报 | `verified` 必须有 golden；C 未过只能 `ported_unverified` |
| 范围失控 | 台账 + 棘轮 + 每阶段只做纵向切片 |

回退：任何函数保真失败 → 状态回退到 `ported_unverified`；CI 红灯优先于进度。

---

## 8. 自我复盘（GRAI / KPT）

**Goal**：完成 P0 地基 + 适配器 + 算子 + 真编译 + 约束 JSON + 归档。
**Result**：R1–R11 全部落地；`check_translate_port` 全绿（C 3/3）；18 测通过；
`check_all` 仅剩 2 项既有失败（`check_figure_glyphs` 本机字形、`check_kernel_snapshot` 上游快照）。

**根因（5 Whys）**
1. 为什么之前 C 没真跑？本机无系统编译器 → **ziglang 提供离线 `zig cc`**，已接入。
2. 为什么门禁加一项会连累 6 处？门禁体系是“登记制” → 同步 MIN_GUARDS/CI_ONLY/README/CONTRIBUTING/help/GUARD_CONTRACT。
3. 为什么台账可能虚报？状态与证据脱钩 → **`--sync-ledger` 只按 C 结果升级**。
4. 为什么约束会漂移？口头约定没有对手方 → **JSON + TP1b 双向核对**。
5. 为什么每次都要重述计划？计划只存在于对话 → **本归档 + 索引**。

**沉淀规则（下次直接照做）**
1. 下次加 C 落点：先写 golden，再写 C，最后 `--sync-ledger`；未过只能 `ported_unverified`。
2. 下次加门：同步 6 处登记，再跑 `check_help_contract + check_readme_parity + check_release_gates`。
3. 下次改约束：先改 JSON，再跑 TP1b；**不要只改代码不改约束**。
4. 下次碰编译：本地无编译器就用 `ziglang`，CI 用 `--require-c`，禁止“跳过即绿”。

**KPT**
- Keep：单一事实源（mlc.h / operators / golden / ledger）+ 登记制门禁。
- Problem：仍无 MIR/类型事实；transpose/matmul 仍是诚实边界。
- Try：R12–R14 扩算子，R16–R18 补 MIR 与规则验证。

---

## 9. 下一次建设性意见

1. **R12（最高优先）**：把 SUB/MUL/DIV/MEAN/MAX 的 C 落点补齐，让“元素级四则 + 归约”形成完整最小集。
2. **R16–R18（结构性）**：MIR + shape/dtype 事实 + 四条规则 `verified_by`，这是从“单行算子”走向“真实函数体”的分水岭。
3. **R23（对接质量）**：`--mixed` 从“名字撞名”升级为“签名/参数/返回”契约，直接降低两边漂移。
4. **两个既有红门单独处理**：`check_figure_glyphs` 的 FG4 依赖本机字体；`check_kernel_snapshot` 需按仓库纪律重跑仓外探针后再更新快照，**不要手改数字**。

---

## 10. 证据索引

| 命令 | 读数 |
| --- | --- |
| `python tools/check_translate_port.py` | `OK（TP1–TP4 全绿；golden 5/5；C 3/3；台账 5 条）` |
| `python tools/check_translate_port.py --selftest` | `SELFTEST COUNTS {"bad": 0, "good": 13}` |
| `python -m pytest tests/test_translate_port.py -q` | `18 passed` |
| `python tools/check_translate_port.py --sync-ledger --write` | add/sum/index → `verified` |
| `python tools/check_help_contract.py` | OK |
| `python tools/check_readme_parity.py` | OK（38 道门表行） |
| `python tools/check_version_scheme.py` | OK（1.5.2） |
| `python tools/check_eol_convention.py` | OK（393 文本文件） |
| `python tools/check_py36_clean.py` | OK（135 个 .py） |
| `python tools/check_all.py --quiet` | 2 项既有失败（见 §8） |
