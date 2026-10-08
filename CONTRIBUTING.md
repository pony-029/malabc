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

# 4) 登记制护栏（5 道，各自还会跑 --selftest）
python tools/check_all.py
```

> 以上等价于仓库的 GitHub Actions（`.github/workflows/ci.yml`）。
> 第 4 步**必须也能红**：任何一道护栏加进来却不带 `--selftest`，
> `check_all.py` 与 `test_r30_static_guards_all_clean` 都会判失败 ——
> 一道只会变绿的门等于没有门，一道会**永远挂住**的门比没有门更糟。

## 改动落盘的三条硬规则（都来自真实事故，不是假想）

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

> **关于测量的第四条：测量工具自身的 bug 会伪造出被测对象的 bug。**
> 真实案例：探针里一个未标注的 `limit=5` 截断，把「扫描到 348 个」误报成「只有 5 个」，
> 差点让一次误读被写进结论。**当新结论与上一次不同时，先重跑对照，再下判断。**

## 提交约定

- 提交信息建议 `类型: 简述`，类型如 `feat` / `fix` / `docs` / `refactor` / `test` / `ci`。
- **LICENSE**：英文 `LICENSE` 为唯一法律效力文本，中文 `LICENSE_CN` 仅为译本，改动版权人请同步两文件。
- 增量/分析缓存（`.analyzer_*`、`*.sarif`、`dist_bin/`、`_build/`）已被 `.gitignore` 忽略，勿手提交。

## 代码风格

- 不引入第三方依赖；新增 Python 代码须 3.6.5 兼容（禁用 walrus / `match` / 仅位置参数 / 内置泛型下标 `list[int]` 等 3.7+ 语法）。
- 渲染器在 `renderers/` 下独立成文件，避免与 `matlabc.py` 反向 `import` 形成环形依赖。
- 新增静态检查 / 渲染能力请在 `docs/matlabc_FEATURES.md` 与 `docs/matlabc_USAGE.md` 同步更新。

## 深度分析归档

涉及「审计 / 协同检查 / 深度分析」类工作的结论，请归档到 `docs/analysis/`，
并维护 `docs/analysis/ANALYSIS_ARCHIVE_README.md` 索引（方法 / 结论 / 证据 / 缺口 / 改进）。
