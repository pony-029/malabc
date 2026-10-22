# Source Insight 移植：总览与边界

> 上游分析：`docs/SourceInsight4UserGuide4092.pdf`（SI 4.0，436 页）。
> 总计划：`docs/SOURCEINSIGHT_PORT_PLAN.md`。
> 本目录（`docs/si/`）是 P0 规格文档；代码原型是 `tools/mlc_project.py`。

## 1. 目标

把 Source Insight 最有价值的行为移植到 matlabc：

1. **项目级符号库**：项目文件、文件清单、声明/引用、增量更新。
2. **导航**：定义、引用、调用者、被调用者、类层次。
3. **联动视图**：Project / Context / Relation。
4. **工程检索**：全文/正则、结果跳转（source link）。
5. **MATLAB 特化**：包/类点分名、局部函数、函数句柄、动态调用置信度。

## 2. 非目标

- 不复刻 Windows MDI/停靠/半透明面板。
- 不兼容 `.sip._*` / `.sip_sym` 二进制格式。
- 不实现完整 Source Insight 宏方言。
- 不移植安装、激活、许可、注册表、CHM。
- 不复制 SI 的图标、帮助文本、专有格式。

## 3. P0 已交付

| 交付 | 位置 |
| --- | --- |
| `.mlcproj` schema/加载/写入 | `tools/mlc_project.py` |
| SQLite schema：projects/files/symbols/refs/edges/conditions/bookmarks/snippets/workspaces | `tools/mlc_project.py` |
| `init` / `sync` / `status` / `symbols` CLI | `tools/mlc_project.py` |
| MATLAB 符号抽取（复用 `matlabc.MatlabFile`） | `tools/mlc_project.py` |
| 8 个单元测试 | `tests/test_mlc_project.py` |
| P0 规格 | `docs/si/00`–`04` |

## 4. P0 明确没做

- `refs` 已按词法标识符填充；完整作用域/类型解析仍属 P1。
- `edges` 已接 `matlabc.analyze_calls`，有 `call/builtin/external/dynamic/indirect` 与置信度；
  `eval`/动态字段仍标低置信度。
- 没有 FTS5/名称片段索引（字段/表已预留）。
- Context/Relation 已有 LSP 方法与 VS Code 面板；书签/片段目前是 CLI+SQLite，
  还没有 VS Code 面板。
- LSP 已支持 `workspace/symbol` 与 `didChange` overlay（350ms 防抖）；
  未保存 buffer 走临时文件解析，`didSave` 后回到磁盘。
- `.siproj`/MFL 只导入文件清单，不导入符号；符号全部重新解析。

## 5. 关键决策

1. **自有 schema，不逆向 SI 二进制**：符号库可重建，格式可迁移。
2. **SQLite 单文件**：stdlib、事务、WAL、可查询；不引入服务。
3. **per-file 增量**：mtime+size 快速路径，sha256 兜底；不再用全局最大 mtime。
4. **MATLAB 优先**：P0 只解析 `.m`；C/Py/JS 复用现有前端，后续接入。
5. **符号名用点分路径**：与 SI 的 `Class.member` 对齐，便于 Context/Relation。

## 6. 验收口径

```bash
python tools/mlc_project.py init --root /tmp/demo --name demo
python tools/mlc_project.py sync --root /tmp/demo
python tools/mlc_project.py status --root /tmp/demo
python tools/mlc_project.py symbols --root /tmp/demo --query Cls
python -m pytest -q tests/test_mlc_project.py
```

P0 通过标准：3 文件样例得到 7 个符号；`main.helper`、`pkg.Cls.getValue`
等点分名正确；第二次 sync 为 0 changed；删除文件后符号消失；dry-run 不写库。

真实样例：`tests/sample_m` 的 13 个 `.m` → **21 符号 / 21 边 / 43 引用**，
首次 sync **0.05 s**（本机）。

10 万行基准：100 个 `.m` / 100,000 行 → 首次 sync **1.68 s**，
工程搜索（命中 1 处）**0.046 s**。
