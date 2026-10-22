# Source Insight 哪些好处可以直接借鉴给 MATLAB 解析

> 结论：SI 的**项目级符号库、点分名、Context/Relation、名称片段、增量同步**几乎可以原样借鉴；
> 但**条件解析、宏、Windows UI、二进制符号格式**不能照搬，要换成 MATLAB 的语义。

## 1. 直接可借鉴（高价值）

### 1.1 项目级符号库 + 增量同步

MATLAB 工程常见形态是“一个目录 + 大量 `.m` + 若干 `+pkg`/`@class`”，
且函数名可能跨文件重复。SI 的做法正是：

- 文件加入项目才进符号库；
- 保存/外部变更后只重解析该文件；
- 符号库持久化，重启不丢。

MATLAB 映射：

- 每个 `.m` 一个 `files` 行，per-file `mtime+size+sha256`；
- 只重解析 changed 文件；
- `main`/`local`/`class`/`method`/`property` 全部入 `symbols`；
- 删除文件时级联删除符号。

这是 P0 已落地的部分，也是收益最大的一层。

### 1.2 点分符号名

SI 把 `Class.member` 存成 dotted path。MATLAB 天然有：

- `+pkg/func.m` → `pkg.func`
- `+pkg/Cls.m` → `pkg.Cls`
- 类成员 → `pkg.Cls.method` / `pkg.Cls.prop`
- `@Widget/get.m` → `Widget.get`
- 同文件局部函数 → `main.helper`（文件内作用域）

这让 Context/Relation 能明确回答“这个 `get` 是哪个类的 `get`”，
而不是只按裸名匹配。

### 1.3 定义解析顺序

SI 的顺序是：当前项目 → 项目导入库 → 全局导入库 → 项目符号路径 → Base 项目。
MATLAB 的对应物是：

1. 当前项目内（优先同文件/同包/同类）；
2. 项目配置的 MATLAB path / 工具箱目录；
3. 内置函数/工具箱；
4. 未解析（`unresolved`）。

建议在符号上存 `resolution`：

| 值 | 含义 |
| --- | --- |
| `project` | 项目内符号，置信度最高 |
| `path` | 配置的 MATLAB path 命中 |
| `builtin` | 内置/工具箱 |
| `external` | 项目外、未建索引 |
| `dynamic` | `feval`/`eval`/函数句柄等 |
| `unresolved` | 不知道 |

**不要**把“名字存在”当成“解析成功”；MATLAB 的 path 优先级/遮蔽很常见。

### 1.4 Context Window

SI 的 Context 是“光标处标识符的声明/基类型/引用预览”。MATLAB 可直接做：

- 函数签名：`function [a,b] = f(x, y)`；
- 帮助头：H1 行 + 参数/返回值说明（现有 `_parse_header_comments` 可复用）；
- 类属性：类型、默认值、`GetAccess`；
- 基类：`superclasses` / `handle`；
- 变量：局部赋值/参数推断（只做有证据的推断）。

这是 MATLAB 用户感知最强的一层：**不打开文件就能看函数怎么用**。

### 1.5 Relation Window

SI 的 `Contains / Calls / Calls+Callers / References` 可直接映射：

- `Contains`：类 → 方法/属性；
- `Calls`：函数 → 被调函数；
- `Calls+Callers`：双向；
- `References`：标识符引用（P1 引用索引）。

MATLAB 的特殊性：

- `obj.method()` 是方法调用，不是普通函数；
- `@func` / `str2func` / `feval` 是间接调用；
- `eval` / `assignin` / `load` 是动态的，静态分析只能标 `dynamic`；
- MEX/内置函数没有源码，标 `builtin/external`。

建议每条边带 `confidence`：
`1.0` 直接调用、`0.5` 方法/句柄、`0.2` 动态、`0.0` 未解析。

### 1.6 名称片段匹配

SI 把 `CreateWindow` 索引为 `Create` + `Window`。MATLAB 命名大量 camelCase
（`getValue`、`setProperty`、`parseInputs`），名称片段非常合适：

- 输入 `getVal` 命中 `getValue`；
- 输入 `setProp` 命中 `setProperty`；
- 支持乱序：`ValGet` 也能命中。

实现：`name_fragments(fragment, symbol_id)` 表，或 FTS5 trigram。
P0 只预留 schema，P1 落索引。

### 1.7 搜索 / source link / Project Report

SI 的“Search Results + source link”可直接用于 MATLAB：

- 搜索结果 `file:line: text` 可点击跳转；
- `checkcode`/`mlint` 输出可解析成 source link；
- Project Report 输出函数清单、未解析调用、类层次、文件统计。

现有 `renderers/csite.py` 已能生成 HTML 站点，P1 加“搜索结果页”即可。

### 1.8 类层次与 Snippets

- 类层次：MATLAB `classdef Cls < Base`、`handle`、抽象方法；
- Snippets：function/classdef/properties/methods 模板，按语言/项目保存；
- 这些是低风险、高感知的 P1 功能。

## 2. 不能照搬、要改写

### 2.1 条件解析

SI 用 `#if/#ifdef` + 条件变量 + Inactive Code。MATLAB 没有预处理器，但有：

- `if false` / `if 0` 的死分支；
- `%{ ... %}` 块注释；
- `ver('...')` / `isMATLABReleaseOlderThan` / `exist` 的版本/工具箱分支；
- `isempty`/`nargin` 等运行时分支。

建议：

- **不执行** MATLAB 代码来判断条件；
- 把 `ver`/版本/工具箱条件作为项目 `conditions` 配置；
- 无法判定的分支标 `inactive-unknown`，不要假装解析成功；
- 块注释内的代码不进符号库（与 SI 的 Inactive Code 同思路）。

### 2.2 宏/Token Macro

MATLAB 没有 C 预处理器宏。不要引入“Token Macro”概念；
真正需要的是：

- 变量/函数句柄的类型与指向；
- `arguments` 块的类型/默认值；
- `metaclass`/`properties` 动态属性（标 dynamic）。

### 2.3 二进制符号格式

SI 的 `.sip._*`/`.sip_sym` 不公开。MATLAB 侧应使用 SQLite + 可重建；
需要互操作时只导入 `.siproj` 的文件清单，重新解析。

### 2.4 Windows UI / 宏方言

MATLAB 用户更常用 VS Code / MATLAB 编辑器。UI 应优先做 VS Code 面板，
而不是复刻 SI 的停靠窗口；宏应做 Python 插件 API，而不是 SI 宏解释器。

## 3. MATLAB 特有的“坑”

| 坑 | 影响 | 处理 |
| --- | --- | --- |
| `eval` / `evalin` / `assignin` | 静态不可知 | 标 `dynamic`，不猜 |
| `feval` / `str2func` / 函数句柄 | 间接调用 | 能解析字面量就解析，否则 `indirect` |
| `load` / `save` / `mat` | 变量类型未知 | 标 unknown |
| `exist` / `which` / path 遮蔽 | 同名多义 | 记录 resolution 顺序 |
| `+pkg` / `@class` / `private/` | 作用域复杂 | 点分名 + 作用域链 |
| `classdef` 多文件 | 类成员分散 | 按 `class_name` 合并 |
| BOM/GBK 编码 | 解析失败 | `utf-8-sig`/`gb18030` 探测 |
| `%{ %}` 块注释 | 伪代码进符号库 | 先 scrub 再解析 |

## 4. 建议的借鉴顺序（MATLAB）

1. **项目 + 符号库 + per-file 增量**（P0，已做）
2. **点分名 + 类/局部函数/属性**（P0，已做）
3. **Context：签名/帮助头/属性/基类**（P1）
4. **Relation：调用/被调/方法/句柄，带 confidence**（P1）
5. **名称片段 + 工程搜索 + source link**（P1）
6. **类层次 + Snippets + Project Report**（P1/P2）
7. **版本/工具箱条件解析**（P2，最后做）
8. **插件/事件 API**（P2）

> 一句话：**SI 的“项目 + 符号库 + 联动视图”是 MATLAB 解析最值得抄的；
> SI 的“预处理器/宏/Windows UI/二进制格式”不要抄。**
