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
```

> 以上三步等价于仓库的 GitHub Actions（` .github/workflows/ci.yml`）。

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
