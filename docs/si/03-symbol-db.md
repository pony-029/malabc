# SQLite 符号数据库（P0）

## 1. 表

```sql
projects(id, name, root, config_json, created_at, updated_at)
files(id, project_id, path, lang, mtime_ns, size, sha256,
      parse_status, parse_error, indexed_at)
symbols(id, file_id, name, dotted_name, kind, line, col, end_line,
        scope_id, signature, type_name, flags)
refs(id, symbol_id, file_id, line, col, kind, context)
edges(id, src_symbol_id, dst_symbol_id, callee_name, kind, line,
      confidence, weight, file_id)
conditions(project_id, name, value)
bookmarks(project_id, file_id, line, col, note)
snippets(project_id, name, lang, body)
workspaces(project_id, name, state_json)
```

索引：`symbols(name)`、`symbols(dotted_name)`、`symbols(kind)`、
`edges(src_symbol_id)`、`edges(dst_symbol_id)`；`files(project_id,path)` 唯一。

## 2. 符号种类

| kind | 含义 | MATLAB 来源 |
| --- | --- | --- |
| `class` | 类 | `classdef` / `@Class` 目录 |
| `property` | 属性 | `properties` 块 |
| `method` | 方法 | `methods` 块 / `@Class` 目录函数 |
| `constructor` | 构造函数 | 方法名 == 类名 |
| `function` | 主函数 | `function` 顶部 |
| `local_function` | 局部函数 | 同文件后续 `function` |
| `script` | 脚本 | 无 function 的 `.m` |
| `event` | 事件 | `events` 块 |
| `enumeration` | 枚举 | `enumeration` 块 |

## 3. 点分名规则

| MATLAB 形态 | dotted_name |
| --- | --- |
| `+pkg/foo.m` | `pkg.foo` |
| `+pkg/Cls.m` 的类 | `pkg.Cls` |
| `pkg.Cls` 的属性 `value` | `pkg.Cls.value` |
| `pkg.Cls` 的方法 `getValue` | `pkg.Cls.getValue` |
| `a.m` 的 `main` 与局部 `helper` | `main`、`main.helper` |
| `@Widget/get.m` | `Widget`、`Widget.get` |

> `main.helper` 是**文件内作用域**的表达，不代表 MATLAB 全局名。
> 查询时可用 `name`（`helper`）或 `dotted_name`（`main.helper`）。

## 4. 引用与边

- `refs`：P0 只建表；P1 由调用点/标识符引用填充。
- `edges`：`kind` 为 `call / external / dynamic / indirect`；
  `confidence` 表示静态可判定程度；`dst_symbol_id` 为空表示未解析。
- 当前 `matlabc.parse_file` 只产出函数/类结构，`fn.calls` 在后续分析阶段才填充，
  所以 P0 的 `edges` 通常为 0；P1 接入 `unified_graph`/调用分析后填。

## 5. 增量生命周期

```
files.sha256 变化
  → DELETE files 行（级联 symbols/refs/edges）
  → INSERT 新 files 行
  → parse_file → INSERT symbols
  → P1：INSERT refs/edges
```

- 单文件一个事务边界；整次 sync 最后统一 commit。
- 删除文件时，其他文件指向它的 `edges.dst_symbol_id` 由 `ON DELETE SET NULL` 置空，
  保留 `callee_name` 供 P1 重新解析。
- `meta.last_sync` 记录最近一次成功同步时间。

## 6. 查询示例

```sql
-- 所有类
SELECT dotted_name, path, line FROM symbols s
JOIN files f ON s.file_id=f.id WHERE s.kind='class';

-- 某类的成员
SELECT dotted_name, kind, line FROM symbols
WHERE dotted_name LIKE 'pkg.Cls.%' ORDER BY line;

-- 未解析调用（P1 有数据后）
SELECT callee_name, COUNT(*) FROM edges
WHERE dst_symbol_id IS NULL GROUP BY callee_name;
```

## 7. 为什么不用 SI 的符号文件

- 无公开 schema，无法保证跨版本。
- 二进制格式不可 diff、不可 code review。
- 重新解析源码可以保证“符号库与当前代码一致”，避免导入陈旧符号。
