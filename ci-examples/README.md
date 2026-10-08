# CI 集成示例（P205-5）

演示如何把 `matlabc.py` 的 **P203 文件夹门禁 + P204 SARIF 报告** 接入 CI，
实现「按目录并行门禁 + SARIF 上传到安全面板」的开箱即用闭环。

## 文件

| 文件 | 用途 |
| --- | --- |
| `github-actions-static-analysis.yml` | GitHub Actions 工作流：发现目录 → 矩阵并行 `--gate` → 上传 SARIF 到 Code Scanning |
| `gitlab-ci-static-analysis.yml`     | GitLab CI：用 `parallel:matrix` 对多个模块并行门禁，SARIF 接入安全面板 |

## 快速接入

**GitHub Actions**：把 `github-actions-static-analysis.yml` 复制为 `.github/workflows/static-analysis.yml`，
把 `matlab_src` 改为你的源码根目录即可。

**GitLab CI**：把 `gitlab-ci-static-analysis.yml` 复制为 `.gitlab-ci.yml`（或 `include` 之），
在 `.gate_job` 下按需增删 `gate-module-*` 作业（每个对应一个待门禁目录）。

## 门禁参数说明

- `--gate-max-uninit-folder N`：每个目录允许的最大未初始化变量数；超过即门禁 FAIL。
- `--gate-folder-report FILE --gate-folder-report-format sarif`：门禁结果导出为 SARIF 2.1.0，
  含行级 `region.startLine` 定位（P205-3），可直接被 GitHub Code Scanning / GitLab 安全面板消费。
- `--max-nodes N`：限制统一画布节点数，保障 300+ 文件仓库仍可渲染（P203）。

## 行为约定

门禁 FAIL（未初始化变量超阈值）时进程**非零退出**，但 SARIF 文件**仍落盘并上传**，
确保开发者能在安全面板直接看到问题行，而非仅得到一个红色 CI 状态。
