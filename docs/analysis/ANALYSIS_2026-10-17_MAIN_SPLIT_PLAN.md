# 2026-10-17 · `main` 切分方案（P1）：三段边界与判据

> 上一轮（`ANALYSIS_2026-10-17_MATLABC_STRUCTURE.md`）测出 `main` 是 **2,020 行**的上帝函数。
> 本轮用 `ast` 把它拆到**顶层语句**粒度，找出三个自然出口的**行号边界**，
> 并写下每一步的判据。**本文只做测量与规划，不改 `matlabc.py`。**

---

## §0 一句话结论

`main` 有 **277 条顶层语句**，按职责已经**天然分成三段**，边界落在三处：

```
L32185 ──────────── L32846  cli_entry    662 行  130 条 argparse 语句 + 少量前置校验
L32847 ──────────── L33194  run_pipeline 348 行   16 条分析语句（收集→分发→解析→建模型）
L33195 ──────────── L34204  emit_outputs 1010 行  45 条渲染语句 + 86 条杂项/退出码
```

**边界不是猜的**：`args = ap.parse_args(argv)` 在 **L32837**，是第二段的入口；
`_emit_report_outputs(...)` 在 **L33195**，是第三段的入口。两者都是**唯一的、可 grep 的**分界点。

---

## §1 测量

| 项 | 读数 |
| --- | --- |
| `main` 起止 | L32185 – L34204（2,020 行） |
| 顶层语句 | 277 条 |
| argparse 类（`add_argument` / `parse_args` / `ArgumentParser`） | 130 条，集中在 L32216 – L32837 |
| analyze 类（`collect_files` / `parse_file` / `analyze_calls` / `build_analysis_model`） | 16 条，L32847 – L33194 |
| render 类（`render_*` / `_emit_*` / `_write_output` / `print`） | 45 条，L33195 – L34204 |
| 其它（时间、编码、配置、退出码） | 86 条，散布三段 |

**读数口径**：`ast` 遍历 `main.body` 的每个顶层语句，按其中出现的**函数名关键词**归类。
同一条语句可能同时含 analyze 与 render 调用，按"第一个命中"归一类，所以三类之和小于 277 是正常的。

---

## §2 三段各自做什么、依赖什么

### 2.1 `cli_entry`（L32185 – L32846，662 行）

**做什么**：读 `sys.argv` → 合并 config（`_extract_config_arg`）→ 建 `ArgumentParser`
→ 130 条 `add_argument` → `parse_args` → 少量前置校验（`root.is_dir()` 之类）。

**依赖**：`cfg`、`argv`、`ap`、`args`。

**为什么它必须单独成段**：`--help` 的全部文本由这 130 条语句决定，而
`check_help_contract` 的 **R5c 用「规范形逐字节」钉住它**（快照 50,094 字节）。
**这段的每一次措辞改动都有对手方**，独立成段后可以直接跑 `--help` 对比，而不必跑全量分析。

### 2.2 `run_pipeline`（L32847 – L33194，348 行）

**做什么**：
1. 二进制分析（`_run_binary_analysis`，L32847）
2. 收集文件（`collect_files`，L32972）
3. 语言分发（`_build_ext_model` / `build_c_model` / `collect_asm_files`，L32984 – L33014）
4. 逐文件解析（`parse_file` → `MatlabFile`，L33034）
5. 调用解析（`analyze_calls`，L33084）
6. 建模型（`build_analysis_model`，L33175）+ `doc_todos` + `dup_opts` + `checks_for_sarif`

**依赖**：`args` → 产出 `files`、`index`、`edges`、`model`、`c_model`、`checks_for_sarif`。

**为什么它是最容易切的一段**：它的输入只有 `args`，输出只有 6 个名字，
**没有 print、没有写盘、没有 exit**。切出来之后，`analyzer/` 的第一步就有了形状。

### 2.3 `emit_outputs`（L33195 – L34204，1,010 行）

**做什么**：45 条渲染语句，覆盖 JSON / SARIF / 站点 / 快照 / 补丁 / 各种 `--xxx-out`
+ 86 条杂项（时间、退出码、gate 判定）。

**依赖**：`args` + `run_pipeline` 的 6 个产出。

**为什么它最大却不能先切**：它有 45 条语句**共享 `model` 的派生值**
（`_ml_callgraph_model(edges)`、`_binattr`、`_operator_impact`、`_oi_md`、`_sm_md`…），
这些派生值彼此有依赖顺序。先切它，等于把一条 1,010 行的依赖链整体搬家，判据会一起爆。

---

## §3 切分步骤（四步，每步都能回退）

| 步 | 动作 | 判据（必须能红） |
| --- | --- | --- |
| **S1** | 只把 `cli_entry` 抽成 `def cli_entry(argv=None) -> argparse.Namespace`，`main` 变成 `args = cli_entry(argv)` + 原样保留其余 | `--help` **逐字节**等于快照（R5c 的规范形 50,094 B）；`main` 行数 −662 |
| **S2** | 把 `run_pipeline` 抽成 `def run_pipeline(args) -> PipelineResult`（一个 `namedtuple`/`dataclass`，6 个字段） | `--json` 的 `--fingerprint` 不变；`--browse` 站点目录指纹不变；`main` 行数 −348 |
| **S3** | 把 `emit_outputs` 抽成 `def emit_outputs(args, result) -> int`（返回退出码） | 同上三条 + `--sarif` 逐字节不变；`main` < 200 行 |
| **S4** | 把 `main` 收缩为 3 行调用 + `sys.exit`；`cli_entry` 搬进 `cli.py` | `python matlabc.py --help` 与四类产物全部不变；`check_help_contract` 的 R5c 仍绿 |

**S1 与 S2 之间必须提交一次**：S1 只动 argparse，判据是纯文本（`--help`）；
S2 动的是数据流，判据是 `--fingerprint`。两者混在一个提交里，红了分不清是谁。

---

## §4 三个必须提前处理的风险

### 风险 1：局部变量闭包

`emit_outputs` 里有大量**互相引用**的局部变量（`_binattr` / `_oi_md` / `_ml_callgraph_model(edges)`）。
抽函数时如果逐个传参，签名会有 15+ 个参数。

**做法**：先定义 `PipelineResult`（6 个字段：`files/index/edges/model/c_model/checks_for_sarif`），
再用一个 `EmitContext`（`args` + `result` + 3 个派生缓存）作为第二参数。
**不要**用 `global` 或模块级变量代替——那会让 LSP 的多文档并发直接串。

### 风险 2：early return 与 `sys.exit`

`main` 里有大量 `if args.xxx: ... return/exit`（L32944 `if not root.is_dir(): print; return`）。
切段时必须把这些**变成返回值**（`RunResult(exit_code=2, reason=...)`），而不是让子函数自己 exit。
否则 `emit_outputs` 会在中途杀掉进程，`--json` 都写不出来。

**判据**：在 `run_pipeline` 里 grep 不到 `sys.exit` / `return 2` 这类"自杀"语句。

### 风险 3：时间与输出顺序

`t_start = time.time()` 在 L32186，最后要报耗时；`print` 与 `_write_output` 交错。
切段后**输出顺序可能变**（例如 `_emit_report_outputs` 内部先 print 再写盘）。

**判据**：`--browse` 的站点目录指纹 + `--json` 指纹 + `--sarif` 逐字节，
三者的输出**顺序**由现有 `renderers/snapshot.py` 的指纹直接覆盖。

---

## §5 本轮的边界：只做测量，不动代码

本文的所有数字都可以用一条命令复现：

```
python tools/analyze_structure.py            # 706 函数 / p50=21 / 12 个 >200 行
python C:\temp\main_calls.py                 # main 的 277 条顶层语句与三段边界
```

**为什么不在本轮直接切**：切任何一段都要改 `matlabc.py`，而它的 sha256 被
`check_kernel_snapshot` 的 W2 钉死 —— 一次改动需要一次 **1,233 秒**的整树重跑
（见 `CONTRIBUTING.md` 第 5 条硬规则）。所以正确顺序是：**先把方案与判据写死，再一次改动收口。**

---

## §6 下一步（按顺序）

1. **S1：抽 `cli_entry`**。这是三段里唯一"改了不会影响分析"的一段，判据是纯文本 `--help`。
2. **S2：抽 `run_pipeline`**，同时定义 `PipelineResult`。判据是 `--fingerprint`。
3. **S3：抽 `emit_outputs`**，返回退出码。判据是三类产物指纹 + `main < 200 行`。
4. 全部完成后，`analyzer/` 的边界就自然出现：`run_pipeline` 就是它的 `api.analyze_project`。
