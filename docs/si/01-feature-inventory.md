# Source Insight 功能清单与移植状态

> 状态：✅ 已有 / 🟡 部分 / ❌ 缺失 / ➖ 非目标。
> 页码指 SI 4.0 User Guide（`docs/SourceInsight4UserGuide4092.pdf`）。
> 这是 P0 的追踪表；实现后把 ❌/🟡 改成 ✅，并在测试里留证据。

| ID | SI 功能 | 页码 | 优先级 | 当前 | 说明 |
| --- | --- | --- | --- | --- | --- |
| F01 | 项目主文件 `.siproj` | 40–44 | P0 | 🟡 | 自有 `.mlcproj`，不兼容二进制 |
| F02 | 源目录/规范化路径 | 41–42 | P0 | 🟡 | 现有目录扫描；P0 加 `source_dirs` |
| F03 | 添加/移除文件 | 45–46 | P0 | 🟡 | P0 `sync` 自动增删 |
| F04 | Master File List | 46–47 | P0 | ❌ | 文本清单，P1 |
| F05 | 项目文件列表 | 50 | P0 | ❌ | UI 层，P1 |
| F06 | 项目符号列表/分类 | 51–53 | P0 | 🟡 | P0 `symbols` CLI；UI 后置 |
| F07 | 文件类型注册表 | 72–73 | P0 | ✅ | `FRONTEND_REGISTRY` |
| F08 | 导入外部符号/导入库 | 55–57 | P1 | ❌ | C/C++/Java/.NET，P2 |
| F09 | Base/Common 项目 | 49,55 | P1 | ❌ | 解析顺序的一部分 |
| F10 | 只读/复制/重建项目 | 47–49 | P1 | ❌ | 可后置 |
| F11 | 项目工作区/布局 | 146–148 | P1 | ❌ | schema 预留 |
| F12 | 项目 Web 版 | 49 | P2 | 🟡 | `renderers/csite.py` |
| F13 | 内置语言 | 54 | P0 | 🟡 | MATLAB/C/Py/JS |
| F14 | 自定义语言 | 54 | P1 | ❌ | 语言注册扩展 |
| F15 | 点分符号名 | 55 | P0 | ✅ | `pkg.Cls.method` |
| F16 | 定义解析顺序 | 55 | P0 | 🟡 | P0 项目内；MATLAB path 待补 |
| F17 | 条件解析/Inactive Code | 60–63 | P1 | 🟡 | C 仅 `#if 0`；MATLAB 版本门后置 |
| F18 | Token Macros | 64–65 | P2 | ❌ | C 预处理器深水区 |
| F19 | 名称片段索引 | 66–67 | P1 | ❌ | camelCase 很适配 MATLAB |
| F20 | 增量符号同步 | 48 | P0 | ✅ | per-file mtime+size+sha256 |
| F21 | 引用索引 | 40,75 | P0 | ❌ | `refs` 表已建，未填 |
| F22 | Jump to Definition | 74 | P0 | ✅ | LSP definition |
| F23 | Jump to Caller | 74 | P0 | 🟡 | `impact`/`callrel`，缺命令 |
| F24 | Browser Mode | 74 | P1 | ❌ | 可映射 VS Code |
| F25 | Project Symbol List | 75 | P0 | 🟡 | P0 CLI；UI 后置 |
| F26 | 调用树/引用树 | 75 | P0 | 🟡 | `unified_graph`/`callrel` |
| F27 | Context Window | 75,90–92 | P0 | ❌ | 高价值，P1 |
| F28 | Relation Window（Outline/Graph） | 93–97 | P0 | 🟡 | VS Code/HTML 雏形 |
| F29 | 关系规则/调用图过滤/多窗口 | 96–97 | P1 | ❌ | P1 |
| F30 | 引用高亮 | 76 | P1 | ❌ | 语义 token 可扩展 |
| F31 | Project Report | 76 | P1 | 🟡 | `csite`/报告 |
| F32 | Smart Rename | 76 | P1 | ❌ | 需作用域判断 |
| F33 | 文件/目录比较 | 77,112–113 | P1 | 🟡 | 任务 diff |
| F34 | 当前文件/多文件/项目搜索 | 104–105 | P0 | ❌ | 最大缺口之一 |
| F35 | Search Results/source link | 106–108 | P0 | ❌ | 结果模型 |
| F36 | 正则/多行 | 109–111 | P0 | 🟡 | Python `re` 可复用 |
| F37 | 替换/重命名 | 105–106 | P1 | ❌ | 与 Smart Rename 合并 |
| F38 | Snippets | 98–100 | P1 | ❌ | 语言特定模板 |
| F39 | Clips | 101 | P1 | ❌ | 文本片段库 |
| F40 | Bookmarks | 102–103 | P1 | ❌ | schema 已有 |
| F41 | 选择历史前进/后退 | 114 | P1 | ❌ | UI/栈 |
| F42 | Outlining/折叠 | 121–123 | P1 | 🟡 | LSP documentSymbol |
| F43 | Code Beautifier | 123 | P2 | ❌ | 可接 formatter |
| F44 | HTML 生成 | 124 | P1 | ✅ | `csite` |
| F45 | 文件编码 | 125–128 | P0 | ✅ | BOM/GB18030 探测 |
| F46 | 文件缓冲/崩溃恢复 | 128–132 | P2 | ❌ | 自动保存/恢复 |
| F47 | 语法格式/引用高亮 | 78–89 | P1 | 🟡 | semantic tokens |
| F48 | 符号补全 | 54,151 | P1 | ❌ | LSP completion |
| F49 | Visual Themes | 144–145 | P2 | 🟡 | GUI 主题 |
| F50 | 命令行/批处理 | 132–135 | P0 | ✅ | 127 个 CLI 参数 |
| F51 | 用户命令 | 136 | P1 | ❌ | 命令注册表 |
| F52 | Custom Commands | 137 | P1 | ❌ | 外部工具 + source link |
| F53 | XML 配置/项目配置 | 138–143 | P1 | 🟡 | JSON 配置 |
| F54 | 宏语言 | 375–420 | P2 | ❌ | 建议 Python 插件 API |
| F55 | 宏事件处理器 | 421–426 | P2 | ❌ | 事件总线 |
| F56 | 源码管理（Git/ClearCase） | 68–71 | P2 | 🟡 | 只读 git |
| F57 | 性能调优 | 148–152 | P1 | 🟡 | 有瓶颈数据 |
| F58 | 面板/停靠/Toolbar | 26–38 | P2 | ❌ | 不照搬 Windows UI |

## 统计

- P0：F01–F07、F13、F15–F16、F20–F22、F25–F28、F34–F36、F45、F50（22 项）
- P1：F08–F11、F14、F17、F19、F23–F24、F29–F33、F37–F42、F44、F47–F48、F51–F53、F57（27 项）
- P2：F12、F18、F43、F46、F49、F54–F56、F58（9 项）

> “全部移植”若按 58 项算，P0 完成约 40%，P1 完成后约 80%；
> 剩余是 UI、宏、商业源码管理、专有格式等低 ROI 项。
