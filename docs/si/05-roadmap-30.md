# 30 轮实施路线（P0 起）

> 状态：✅ 已完成 / ⏳ 待做。每轮都必须有可运行产物或可执行判据，不做“只有文档”的轮次。

| 轮 | 交付 | 验收 | 状态 |
| --- | --- | --- | --- |
| R01 | SI 功能清单 F01–F58 | 每项有页码/优先级/状态 | ✅ |
| R02 | `.mlcproj` schema | `init` 可创建、可加载 | ✅ |
| R03 | SQLite schema（9 表） | `sqlite3` 建库/外键/索引 | ✅ |
| R04 | `init` CLI | 重复 init 拒绝，`--force` 可覆盖 | ✅ |
| R05 | 文件扫描/include/exclude | 排除 `build/.git/.mlc` | ✅ |
| R06 | per-file 指纹 | mtime+size 快速路径，sha256 兜底 | ✅ |
| R07 | MATLAB 函数/局部函数 | `main`/`main.helper` 入库 | ✅ |
| R08 | 类/方法/属性 | `pkg.Cls.getValue` 等 | ✅ |
| R09 | `+pkg` / `@Class` 点分名 | 两种目录都正确 | ✅ |
| R10 | 增量 sync | 二次 sync 0 changed；改/删只动相关文件 | ✅ |
| R11 | `status` / `symbols` | 文件/符号/陈旧数/查询 | ✅ |
| R12 | 8 个单测 + 门禁 | `pytest` 8/8；py36/行尾/README | ✅ |
| R13 | `.siproj` / MFL 导入器 | 只导入文件清单，不读符号库 | ✅ |
| R14 | `refs` 表填充 | 标识符引用可查 | ✅ |
| R15 | 调用边（AST） | `calls` 填 `edges`，跨文件解析 | ✅ |
| R16 | 置信度模型 | call/method/handle/dynamic 分级 | ✅ |
| R17 | LSP `workspace/symbol` | VS Code 全局符号 | ✅ |
| R18 | LSP `didChange` debounce | 编辑期增量，不全量重算 | ✅ |
| R19 | Context API + 面板 | 签名/帮助头/属性/基类 | ✅ |
| R20 | Relation API + 面板 | Contains/Calls/Callers/References | ✅ |
| R21 | 工程搜索（regex/多行） | 100k LOC <1s | ✅ |
| R22 | 搜索结果 + source link | 点击跳转 | ✅ |
| R23 | 名称片段 / FTS5 | `getVal` 命中 `getValue` | ✅（fragment 表；FTS5 可选） |
| R24 | Bookmarks/Snippets | 持久化/项目级 | ✅（CLI+SQLite；面板后置） |
| R25 | Outlining/Compare | 折叠范围、文件/目录 diff | ⏳ |
| R26 | Layouts/Workspaces/Themes | 面板状态可恢复 | ⏳ |
| R27 | Custom Commands | `%f`、source link 解析 | ⏳ |
| R28 | 插件 API + 事件总线 | 示例插件 + 事件触发 | ⏳ |
| R29 | 100 万行性能基准 | 首次/增量/查询预算 | ⏳ |
| R30 | 追踪表收口 | F01–F58 → 代码 → 测试 | ⏳ |

## 下一轮（R13）建议

先做 `.siproj` / Master File List 导入器，因为它能验证“项目模型”不是自嗨：

1. 解析 `.siproj` 的文件清单/源目录；
2. 生成/合并 `.mlcproj` 的 `source_dirs`/`include`；
3. 不导入符号，全部重新解析；
4. 用 SI 示例项目或自造 MFL 做 golden；
5. 失败时明确报“不支持该 SI 版本”，不猜二进制。
