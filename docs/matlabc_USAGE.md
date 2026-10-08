# matlabc 使用说明（v1.16.62）

> 配套特性说明见 [`matlabc_FEATURES.md`](matlabc_FEATURES.md)。
> 纯 Python、零第三方依赖；默认**离线优先**（产物不含外部 CDN 引用）。

---

## 1. 安装与运行

```bash
# 直接运行（推荐，零安装）
python matlabc.py <参数>

# 或安装为命令（可选，仅开发/源码环境）
pip install -e .        # 注册 console_scripts: matlabc
matlabc <参数>    # 无参数=图形界面；带参数=命令行分析器
```

环境要求：Python 3.6+（工具自身严格兼容 3.6.5，见 `--check-py36`）。

查看版本：`python matlabc.py --version`

---

## 2. 最小快速开始

```bash
# 1) 控制台报告（默认）
python matlabc.py my_matlab_project/

# 2) 生成可交互浏览站点（推荐）
python matlabc.py my_matlab_project/ -o report.html --browse

# 3) CI 静态分析（SARIF + 退出码门禁）
python matlabc.py my_matlab_project/ --checks all --sarif report.sarif \
    --max-warnings 0 --reproducible

# 4) 问答式代码理解（AI 驱动，P0 检索/grounding 底座）
#    离线（无密钥）回显提示词；配置 provider 后给出中文回答
matlabc ask "main 被谁调用" --dir my_matlab_project/
matlabc ask "哪里风险最高" --json report.json --provider deepseek
matlabc ask "helper 是做什么的" --dir my_matlab_project/ --lang matlab
```

---

## 2.1 `matlabc ask` —— 问答式代码理解

基于静态分析结果的**自然语言问答**（零依赖、复用 `ai_cli`，离线优先）。它先把
`matlabc` 的分析报告归一化为「函数文档 + 调用图 + 告警/优先级」三类可检索对象，
再用 BM25 检索 + 意图识别（谁调用 X / X 调用谁 / 风险热点 / 解释 X）组装提示词交给大模型。

```bash
# 直接对工程目录问答（自动跑一次分析生成临时报告）
matlabc ask "main 被谁调用" --dir ./myproj
matlabc ask "哪里风险最高"   --dir ./myproj --lang c

# 复用已有报告（matlabc --json 产出），更快
matlabc ask "helper 是做什么的" --json report.json

# 在线回答（需配置 provider / 环境变量密钥，如 DEEPSEEK_API_KEY）
matlabc ask "这个工程的入口函数有哪些" --dir ./myproj --provider deepseek

# 把 AI 回答写入文件
matlabc ask "哪些函数最该补注释" --dir ./myproj --output answer.md
```

> 说明：**离线模式**下不调用任何模型，只把「检索到的真实上下文 + 问题」回显为可粘贴提示词；
> 配置 `ai_cli` 支持的 provider（deepseek/qwen/ernie/zhipu/… 含中文别名）后，直接返回中文回答。
> 调用图依赖 `matlabc` 自身的调用解析质量——当静态分析未捕获某条调用时，图查询会优雅提示
> 「未被项目内其他函数调用」。

---

## 2.2 `matlabc flow` —— AI 修复闭环编排器（P1）

把 `ai_config.json` 里「已声明但未驱动」的 `flow.steps` 真正串起来：
`review → fix → apply → verify → report`。

```bash
# 默认仅产出确定性补丁 + 报告，不改动任何文件（auto_apply=false）
matlabc flow ./myproj

# 应用确定性补丁并自证（重扫后各规则告警数不增加即通过）
matlabc flow ./myproj --auto-apply

# 只跑部分步骤 / 指定语言 / 让 review 步骤调 AI
matlabc flow ./myproj --steps review,fix,report --lang c --provider deepseek
matlabc flow ./myproj --config ai_config.json
```

- **fix**：复用 `matlabc` 的确定性补丁引擎（`--gen-apply-patch`：未初始化 high / 死代码 /
  形状不匹配 / 重复重构脚手架），安全、可验证、不丢数据。
- **apply**：默认不落盘；`--auto-apply` 时优先 `git apply`，无 git 则退回进程内严格语义校验
  （任一 hunk 与工作副本不符即拒绝，原子性）。
- **verify**：应用后重扫，以「各规则告警数不增加（且应减少）」为自证标准。
- **review**：调用 `ai_cli task=review`（离线回显提示词，在线给审查意见）。

> 注：本机需 `git` 才能走 `git apply`；无 git 时自动退回进程内严格校验（同样安全）。

---

## 3. 配置参数总表（按功能分组）

> 约定：`action="store_true"` 表示开关（出现即 True）；`nargs="?"` 表示可选值（出现无参时用方括号默认值）；`metavar` 给出取值示例。CLI 显式参数始终优先于配置文件（`--config`）。

### 3.1 输入与范围

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `dir` | 路径 | 当前目录 | 待分析目录 / 文件（位置参数，可省略 `--dir`） |
| `--dir` | 路径 | — | 同上（显式写法） |
| `--no-recursive` | 开关 | 关 | 仅分析 `dir` 顶层，不递归子目录 |
| `--no-default-filter` | 开关 | 关 | 关闭默认文件过滤（默认只收 `.m/.c/.py/.js` 相关） |
| `--exclude` | 逗号列表 | 无 | 排除路径模式（如 `tests/,third_party/`） |
| `--encoding` | 编码名 | `utf-8` | 源文件读取编码（含 `cp1252` 等自动回退） |
| `--lang` | `matlab`/`c`/`py`/`js` | `matlab` | 指定单一语言前端 |
| `--mixed` | 开关 | 关 | MATLAB + C 混合（MEX 跨语言桥接） |
| `--c-strict` | 开关 | 关 | C 前端严格模式 |
| `--py-dir` | 路径 | 无 | Python 子项目目录（混合分析） |

### 3.2 报告与图产物

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `-o, --output` | 文件 | 无 | Markdown 报告输出路径（不指定则打印控制台） |
| `--html` | 文件 | 无 | 生成单文件 HTML 报告 |
| `--mermaid` | 文件 | 无 | 导出调用图 Mermaid 文本 |
| `--mermaid-cdn` | `auto`/`on`/`off` | `auto` | Mermaid 图渲染：auto=离线则用静态文本、联网时用 CDN |
| `--dot` | 文件 | 无 | 导出 Graphviz DOT |
| `--title` | 字符串 | MATLAB 代码结构分析报告 | 报告标题 |
| `--offline` | 开关 | 关 | 离线优先：产物零外部 CDN 引用，公式 / Mermaid 回退静态展示 |
| `--file-graph` | 文件 | 无 | 文件依赖图 HTML |
| `--folder-graph` | 文件 | 无 | 文件夹依赖图 HTML |
| `--combined-graph` | 文件 | 无 | 文件 + 文件夹 + 调用统一图 HTML |
| `--max-nodes` | 整数 | 无 | `__CG__` 统一调用图节点硬上限（大仓渲染保护，超出按 folder>file>function>variable 截断） |
| `--max-graph-files` | 整数 | 无 | 文件图文件数上限 |

### 3.3 交互浏览站点

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--browse` | 文件 | 无 | 生成可点击跳转的浏览站点（纯内联、零 WebSocket） |
| `--watch` | 开关 | 关 | 守护模式：文件内容变更（SHA-256 签名）自动重分析重生成 |

### 3.4 结构化输出与可复现

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--json` | 文件 | 无 | 导出结构化 JSON（全量模型 + 告警 + 指标） |
| `--xml` | 文件 | 无 | 导出 XML 报告 |
| `--export-doxygen-xml` | 文件 | 无 | 导出 Doxygen 兼容 XML（接入 doxygen 生态） |
| `--reproducible` | 开关 | 关 | JSON 省略时间戳，两次输出逐字节一致（CI 比对） |
| `--from-json` | 文件 | 无 | 由 `--json` 快照重建站点 / 报告（不重跑分析） |
| `--fingerprint` | 文件 | 无 | 计算并写入内容指纹（整体 + 逐文件 + 告警组 SHA-256） |
| `--verify` | 文件 | 无 | 校验现有产物指纹一致性（防篡改） |

### 3.5 静态检查

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--checks` | `none`/`basic`/`all` 或逗号列表 | `basic` | 启用检查集（如 `uninitialized,dead_code`） |
| `--min-confidence` | `low`/`medium`/`high` | `low` | 静态检查最低置信度（影响 uninit 计数与门禁） |
| 抑制注释（源码内） | 见下表 | — | 就地抑制告警（C3 四档） |

**告警抑制注释语法（写进源码注释，不影响运行）：**

| 档位 | 写法（MATLAB 行注释） | 作用 |
| --- | --- | --- |
| 文件级 | `% analyzer:ignore uninitialized` | 该文件所有 uninitialized |
| 名称级 | `% analyzer:ignore type_mismatch myVar -- 历史兼容` | 仅 `myVar` 的 type_mismatch（可附原因） |
| 行级 | `% analyzer:ignore-next-line shape_mismatch` | 仅下一行 |
| 区间级（P214） | `% analyzer:disable uninitialized` … `% analyzer:enable uninitialized` | 区间内所有行（不含两端） |

> 区间级缺省 `<check>` = 全部检查；未闭合的 `disable` 视为抑制到文件末尾；嵌套按最近匹配闭合。

### 3.6 质量门禁 / CI

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--max-warnings` | 整数 | 0 | 全局告警阈值，超过则退出码非 0 |
| `--max-warnings-by-rule` | `rule:阈值` 逗号列表 | 无 | 按规则独立阈值（如 `uninitialized:0,dead_code:5`） |
| `--gate-file` | 文件 | 无 | 声明式门禁矩阵（taint_gates / rule_gates / max_warnings 合并） |
| `--taint-gate` | `sink:实参位` 逗号列表 | 无 | 污点参数位门禁（如 `fprintf:2,system:*`） |
| `--sarif` | 文件 | 无 | 导出 SARIF 2.1.0（GitHub / GitLab 代码扫描） |
| `--sarif-base` | 文件 | 无 | SARIF 基线（持久化到 `.analyzer_sarif_baseline.json`） |
| `--sarif-diff` | 文件 | 无 | 仅输出相对基线的新增 / 已修复项 |
| `--fail-on-diff` | 开关 | 关 | 存在新增告警时退出码非 0 |
| `--diff` | 两文件 | 无 | 两 `--json` 快照间的全维度差异（控制台） |
| `--diff-html` | 两文件 | 无 | 双栏并排差异 HTML（左基线 / 右当前） |
| `--gen-ci` | `github`/`gitlab`/`both` | 无 | 一键生成 CI 配置模板 |

### 3.7 增量与 git 集成

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--incremental` | 开关 | 关 | 基于内容签名缓存未变文件，仅重分析变更 |
| `--incr-cache` | 文件 | 无 | 增量缓存路径（默认 `.analyzer_incr_cache.json`） |
| `--incr-report` | 文件 | 无 | 导出增量分析报告 |
| `--incr-format` | `json`/`sarif` | `json` | 增量报告格式 |
| `--git-diff` | 可选 BASE | `HEAD` | 仅分析 `git diff --name-only [BASE]` 涉及的 `.m` 文件 |
| `--git-diff-staged` | 开关 | 关 | 使用暂存区（`git diff --cached`）作为变更集（pre-commit） |

### 3.8 污点 / 算子影响（P85+）

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--operator-impact` | 文件 | 无 | 算子影响分析：列出调用该文件的"上层算子"（目录聚合） |
| `--operator-impact-file` | 文件 | 无 | 单文件算子影响（文件级明细） |
| `--operator-impact-echo` | 开关 | 关 | 控制台打印算子影响概览 |

### 3.9 文档 / 技术债

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--init-header` | 开关 | 关 | 生成文件头注释模板（含函数用途 / 作者 / 日期占位） |
| `--todo-export` | 文件 | 无 | 导出注释标签聚合（TODO/BUG/DEPRECATED…） |
| `--todo-base` | 文件 | 无 | 注释标签基线（趋势比对） |
| `--debt` | 开关 | 关 | 技术债聚合报告（复杂度 / 扇入 / 告警密度 / 同名歧义排序） |
| `--trend` | 文件 | 无 | 生成指标趋势 Sparkline（零依赖） |
| `--gate` | 文件 | 无 | 技术债门禁快照（配合下方 `--gate-*` 阈值） |
| `--gate-max-debt` | 整数 | 无 | 总体技术债上限 |
| `--gate-max-delta` | 整数 | 无 | 相对基线新增技术债上限 |
| `--gate-max-uninit` | 整数 | 无 | 未初始化告警上限 |
| `--gate-max-uninit-folder` | 整数 | 无 | 单文件夹未初始化上限 |
| `--gate-max-debt-folder` | 整数 | 无 | 单文件夹技术债上限 |
| `--gate-folder-report` | 文件 | 无 | 按文件夹门禁每目录明细 JSON（CI 矩阵并行判定） |
| `--gate-folder-report-format` | `json`/`sarif` | `json` | 上述明细格式 |
| `--ai-prompts` | 文件 | 无 | 把分析结论汇为可粘贴离线 AI 工具的结构化审查提示词 |

### 3.10 重复代码 / PR 闭环（P215+）

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--fail-on-dup` | 开关 | 关 | 检测到高相似度重复代码则退出码非 0 |
| `--dup-fail-gate` | `type:阈值` 逗号列表 | 无 | 重复门禁（total_cap / new_cap / ratio） |
| `--dup-baseline` | 文件 | 无 | 重复指纹基线（组织级复用） |
| `--dup-diff` | 文件 | 无 | 相对基线的重复新增 / 消除 |
| `--dup-trend-svg` | 文件 | 无 | 重复率趋势 SVG |
| `--dup-org-baseline` | 文件 | 无 | 组织级指纹库（跨仓库去重） |
| `--dup-emit-patch` | 文件 | 无 | 生成完整重构补丁（含调用方改写） |
| `--dup-verify-patch` | 文件 | 无 | 自证验证补丁（可应用 / 重复减少 / 无新告警 / 调用边不丢） |
| `--dup-verify-equiv` | 文件 | 无 | 语义等价性报告 |
| `--gen-pr` | 文件 | 无 | 聚合静态问题为 PR 描述草稿 + 补丁骨架 |
| `--gen-apply-patch` | 文件 | 无 | 确定性可修复项生成真实 unified diff（git apply 适用） |
| `--gen-tests-risk` | 文件 | 无 | 基于高风险点生成 pytest / unittest 测试桩骨架 |

### 3.11 跨语言 / 语法门禁

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--check-py36` | 开关 / 文件列表 | 关 | Python 3.6 语法兼容门禁（扫描 `--dir` 或 `--check-py36-files`） |
| `--check-py36-files` | 逗号列表 | 无 | 指定待检 `.py` 文件（配合 `--check-py36`） |

### 3.12 性能 / 大仓基准

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--benchmark` | 可选 N | 无 | 合成 N 个 `.m`（默认 300）跑完整分析 + unified.html 并计时 |
| `--benchmark-out` | 文件 | stdout | 基准结果 JSON 输出 |
| `--benchmark-timeout` | 秒 | `60.0` | 基准构建时延上限（超出则判定失败） |

### 3.13 全局状态 / 其他

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--global-state` | 文件 | 无 | 跨文件全局 / persistent 共享状态图（暴露隐式共享变量） |
| `--config` | 文件 | 无 | 从 JSON 配置文件读取参数（CLI 显式优先） |
| `--version` | 开关 | — | 打印版本号并退出 |

---

## 4. 配置文件 `analyzer_config.json`

CLI 与配置文件**键名一致**（配置文件用蛇形/短横线均可，CLI 显式值覆盖配置）。最小示例（对照 `analyzer_config.example.json`）：

```json
{
  "dir": "src/",
  "output": "report.md",
  "html": "report.html",
  "browse": "browse.html",
  "offline": true,
  "max_nodes": 1500,
  "checks": "all",
  "min_confidence": "medium",
  "max_warnings": 0,
  "sarif": "report.sarif",
  "reproducible": true,
  "taint_gate": "fprintf:2,system:*",
  "max_warnings_by_rule": "uninitialized:0,dead_code:5",
  "exclude": "tests/,third_party/",
  "debt": true,
  "incremental": true
}
```

> 配置文件不支持纯开关的"False 覆盖"（开关缺失即默认关）；需要"显式关"时请改用 CLI 传参或在配置中置对应值由代码判定。

---

## 5. 常用组合示例

```bash
# 一次性全量审计（离线、可复现、零告警门禁）
python matlabc.py src/ -o audit.md --html audit.html --browse \
    --offline --checks all --max-warnings 0 --reproducible

# PR 增量审查（仅 diff 范围 + SARIF 增量门禁）
python matlabc.py src/ --git-diff HEAD --sarif pr.sarif \
    --sarif-base pr_base.sarif --sarif-diff pr_delta.sarif --fail-on-diff

# 技术债门禁（CI 趋势）
python matlabc.py src/ --debt --gate gate.json \
    --gate-max-debt 100 --gate-max-uninit 0 --gate-max-delta 10

# 重复代码治理（检测 + 自证补丁）
python matlabc.py src/ --fail-on-dup --dup-baseline org.json \
    --dup-emit-patch refactor.patch --dup-verify-patch verify.json

# 修复闭环（生成可应用补丁 + 测试桩）
python matlabc.py src/ --gen-apply-patch fix.patch --gen-tests-risk tests_stub.py
```

---

## 6. 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功（未触发任何门禁阈值） |
| `1` | 门禁未通过（告警超阈值 / 污点违例 / 重复代码 / diff 新增 / 语法问题等） |
| `2` | 用法 / 参数错误 |
| `3` | 输入目录 / 文件不存在或解析失败 |

> 在 CI 中直接用退出码驱动流水线；配合 `--sarif` 还能在代码扫描面板展示。

---

## 7. CI 一键接入

```bash
# 自动生成 GitHub / GitLab 流水线模板（已串接 json+sarif+diff+门禁+可复现）
python matlabc.py src/ --gen-ci both
```

生成的模板等价于：

```yaml
# .github/workflows/matlabc.yml（示例）
- run: python matlabc.py src/
        --json analysis.json
        --sarif report.sarif
        --sarif-base .analyzer_sarif_baseline.json
        --sarif-diff delta.sarif
        --fail-on-diff
        --max-warnings 0
        --reproducible
```

---

## 8. 抑制注释快速参考（贴进源码即可生效）

```matlab
% analyzer:ignore uninitialized                 % 整文件忽略未初始化
% analyzer:ignore type_mismatch x -- 历史遗留     % 仅变量 x 的类型不一致，附原因
% analyzer:ignore-next-line shape_mismatch        % 仅下一行忽略维度不匹配
% analyzer:disable uninitialized                  % ↓ 区间开始（块内全部忽略）
y = a + b;
z = c * d;
% analyzer:enable uninitialized                   % ↑ 区间结束
```
