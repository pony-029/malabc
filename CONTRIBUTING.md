# 参与贡献（Contributing）

欢迎给 `malabc`（`matlabc` 引擎）提 Issue / PR。本文件说明本地开发、测试与提交约定。

## 环境

- **Python 3.6.5+**（工具自身严格兼容 3.6.5，CI 用 `--check-py36` 兜底校验）。
- **零第三方依赖**：只用标准库，无需 `pip install`（想用 `matlabc` 命令可 `pip install -e .`）。
- 可选：打包单文件可执行程序见 `build_dist.py` + `build_release.bat/.sh`。

## 本地验证三步

```bash
# 1) Python 3.6 语法兼容门禁（扫自身 *.py）
python matlabc.py . --check-py36 --max-warnings 0

# 2) 核心测试套件
python tests/test_matlabc.py

# 3) 对示例做静态分析，确认主流程无回归
python matlabc.py tests/sample_m -o demo.md --html demo.html --browse --offline

# 4) 登记制护栏（12 道，各自还会跑 --selftest；门数少于下限也会红）
python tools/check_all.py
```

> 以上等价于仓库的 GitHub Actions（`.github/workflows/ci.yml`）。
> 第 4 步**必须也能红**：任何一道护栏加进来却不带 `--selftest`，
> `check_all.py` 与 `test_r30_static_guards_all_clean` 都会判失败 ——
> 一道只会变绿的门等于没有门，一道会**永远挂住**的门比没有门更糟。
> 新增护栏时还要把 `check_all.py` 的 `MIN_GUARDS` 上限同步上调：删掉一道门
> （改名 / 移目录）后 rc 仍会是 0，**只有门数棘轮能抓住这件事**。

## 改动落盘的四条硬规则（都来自真实事故，不是假想）

1. **探针与一次性脚本一律放仓库外**（例如 `E:\matlabc\_r31\`）。
   它们不进 git 工作区，也不会被误当成产品代码。

2. **落盘任何代码块之前，先写成纯文本文件并用 `ast.parse` 自检**，通过后再写入。
   **禁止**用 shell 内联字符串（`python -c "..."`）传递含**反引号**或**转义序列**
   （`\n` / `\x90` / `\{`）的内容 —— shell 会先做命令替换与转义解释：
   - 反引号被当作**命令替换**执行 ⇒ 文档里的 `` `--help` ``、`` `matlabc_mcp.py` `` 直接消失；
   - `\x90` 被当作 Unicode 转义 ⇒ 落盘成 U+0090 的 UTF-8 编码（字节 `C2 90`），
     含非 ASCII 字面量的 `bytes` 随即被 `ast` 拒绝。

3. **读写往返必须显式指定换行模式。** 本仓 blob 全为 **CRLF**：
   `open(p, encoding="utf-8")` 读入会把 CRLF 归一成 LF，若再以 `newline=""` 写出，
   **整份文件的行尾都会被改写**，git diff 表现为「全文件重写」，真实改动被淹没。
   改完必须自查 `bare_LF == 0`，并用 `git diff --numstat` 确认只有预期的增删行数。

4. **测量工具自身的 bug 会伪造出被测对象的 bug —— 所以两向自证必须「先跑通，
   再宣布通过」。** 顺序反了，你会拿一把坏掉的尺子去宣布「尺寸合格」。
   已真实发生过两次：
   - 探针里一个未标注的 `limit=5` 截断，把「扫描到 348 个」误报成「只有 5 个」；
   - `check_help_contract.py` 的 R1 依据正则 `\breturn\s+0\b` 会在 `return 0.0`
     上命中（`0` 与 `.` 之间就是词边界），于是一个**返回浮点数的函数**被当成了
     「退出码 0 的依据」——它被同文件的 R1b（陈旧登记检测）抓了出来。

   落到 checklist：
   - [ ] 任何新护栏**先**跑 `--selftest`，确认坏样本真的变红、好样本真的放行，
         且打印了 `SELFTEST COUNTS {"bad": N, "good": M}`；
   - [ ] 再跑 plain 模式，最后才把「真实仓库 0 违规」当作结论；
   - [ ] 自证断言写的是**判据的检测结果**，不是「我的断言成立」——两者极易写反；
   - [ ] 新结论与上一次不同时，先重跑对照，再下判断。

## 提交约定

- 提交信息建议 `类型: 简述`，类型如 `feat` / `fix` / `docs` / `refactor` / `test` / `ci`。
- **LICENSE**：英文 `LICENSE` 为唯一法律效力文本，中文 `LICENSE_CN` 仅为译本，改动版权人请同步两文件。
- 增量/分析缓存（`.analyzer_*`、`*.sarif`、`dist_bin/`、`_build/`）已被 `.gitignore` 忽略，勿手提交。

## 代码风格

- 不引入第三方依赖；新增 Python 代码须 3.6.5 兼容（禁用 walrus / `match` / 仅位置参数 / 内置泛型下标 `list[int]` 等 3.7+ 语法）。
- 渲染器在 `renderers/` 下独立成文件；**不要在模块级反向 `import` `matlabc`** ——
  借用请走 `renderers/_late.py` 的惰性代理（见下面「import 图纪律」一节）。
- 新增静态检查 / 渲染能力请在 `docs/matlabc_FEATURES.md` 与 `docs/matlabc_USAGE.md` 同步更新。

## import 图纪律：模块级 import 必须无环（R52）

`tools/check_import_graph.py` 用 `ast` 建两张图，进 CI、也进 `check_all.py`：

| 图 | 边怎么算 | 判据 |
| --- | --- | --- |
| **import 期图** | 只算**模块级**的 `import` / `from ... import` | **必须无环**（G1）；模块级自环直接红（G4） |
| **全图** | 再加上写在函数体里的**惰性** import | 允许成环，但必须登记（G2） |

三条不可协商的后果：

1. **`renderers/` 不许在模块级 `from matlabc import ...`。** 要借用 matlabc 的符号，
   请走 `renderers/_late.py` 的惰性代理：`from renderers._late import late as _mL`，
   然后写成 `_mL.名字`。R52 复盘：模块级回边会造出一份「**部分初始化的对方**」契约 ——
   「被借用的名字必须已经定义在再导出点之前」—— 而这份契约**没有任何对手方**，
   谁把它挪到后面去，两个方向都不会报错。
2. **指向本仓模块的动态 import**（`importlib.import_module` / `__import__`）必须登记。
   它绕开 import 图，是最容易被忽视的一条回边。
3. 登记**两向核对**：未登记 → 红；登记了却已不成环、或那个动态调用已经不在了 → 也红。

登记项必须在**本节**留一个标记（机器读；Markdown 渲染后不可见）。
标记的 id 只允许字母、数字与 `.` `_` `-`，所以文档里可以安全地写示例形态：

    <!-- import-cycle: <id> -->   ← 这一行是**示例**，不会被当成真标记

当前登记表（改代码前先看这里）：

| id | 类型 | 位置 | 为什么允许 |
| --- | --- | --- | --- |
| `agent-loop-matlabc-flow` | 惰性环 | `agent_loop` 与 `matlabc_flow` 互指 | 两条边都写在**函数体**里，import 期不发生 <!-- import-cycle: agent-loop-matlabc-flow --> |
| `late-matlabc` | 动态 import | `renderers/_late.py` → `matlabc` | R52 起 renderers 借用 matlabc 的**唯一**通道 <!-- import-cycle: late-matlabc --> |
| `tests-frontends` | 动态 import | `tests/test_matlabc.py` → `frontends` | 测试按仓库根动态导入、随后立刻撤掉 `sys.path`，避免依赖「运行目录恰好是仓库根」 <!-- import-cycle: tests-frontends --> |

> 这一节的价值是：把一份**隐式**时序契约换成一张**显式**的表。
> 表里每一条都有对手方 —— 边没了 → 陈旧登记报红；来了新边 → 未登记报红。

## 深度分析归档

涉及「审计 / 协同检查 / 深度分析」类工作的结论，请归档到 `docs/analysis/`，
并维护 `docs/analysis/ANALYSIS_ARCHIVE_README.md` 索引（方法 / 结论 / 证据 / 缺口 / 改进）。
