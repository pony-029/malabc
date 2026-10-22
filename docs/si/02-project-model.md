# `.mlcproj` 项目模型（P0）

## 1. 为什么不用 `.siproj`

Source Insight 4 的主项目文件是 `Name.siproj`，符号数据在 `Name.sip._*` 内部文件。
这些格式没有公开 schema，且随版本变化。移植时**只导入文件清单/源目录，重新解析源码**，
不读取 `.sip._*` / `.sip_sym`。

## 2. 文件布局

```
my_project/
  .mlcproj                 # 可读 JSON，进版本库
  .mlc/
    project.db             # SQLite 符号库，可重建，通常不进版本库
    cache/                 # 预留
    backup/                # 预留
  src/...
```

## 3. `.mlcproj` 字段

```json
{
  "schema": 1,
  "name": "my_project",
  "root": ".",
  "source_dirs": ["src", "include"],
  "include": ["**/*.m", "**/*.c", "**/*.h"],
  "exclude": [".git/**", ".mlc/**", "build/**", "node_modules/**"],
  "file_types": {".m": "matlab", ".c": "c", ".h": "c"},
  "conditions": {"DEBUG": 1, "PLATFORM": "win32"},
  "settings": {"name_fragments": true, "index_references": true}
}
```

| 字段 | 含义 | 约定 |
| --- | --- | --- |
| `schema` | 配置版本 | 当前 1；不兼容必须拒绝 |
| `name` | 项目名 | 在 `projects` 表唯一 |
| `root` | 源根，相对 `.mlcproj` | 解析为绝对路径 |
| `source_dirs` | 扫描起点，可多个 | 相对 root |
| `include` | 包含 glob | 默认 `**/*.m` |
| `exclude` | 排除 glob | 默认 `.git/.mlc/build/...` |
| `file_types` | 扩展名 → 语言 | P0 只用 `.m` |
| `conditions` | 条件解析变量 | P1 使用 |
| `settings` | 名称片段/引用等开关 | P1 使用 |

## 4. CLI

```bash
# 创建项目（.mlcproj + .mlc/project.db）
python tools/mlc_project.py init --root . --name demo

# 增量同步；--full 强制重解析；--dry-run 只报告
python tools/mlc_project.py sync --root .
python tools/mlc_project.py sync --root . --full
python tools/mlc_project.py sync --root . --dry-run --json

# 状态（文件/符号/边/陈旧数）
python tools/mlc_project.py status --root .

# 查询符号
python tools/mlc_project.py symbols --root . --query Cls
python tools/mlc_project.py symbols --root . --kind class --json
```

## 5. 同步语义

1. 按 `source_dirs/include/exclude` 扫描，得到 `rel -> abs`。
2. 用 `mtime_ns + size` 快速判断；变化时算 `sha256`。
3. 新增/变化文件：删除旧行（级联符号/边）→ 重新解析 → 插入符号。
4. 删除文件：删除 `files` 行，级联符号。
5. 一次事务提交；单文件解析失败只标 `parse_status=error`，不拖垮全项目。
6. 不写全局 mtime；每个文件独立判定。

## 6. 导入 Source Insight（已实现）

```bash
# 先看会改什么（不写）
python tools/mlc_project.py import --root . --from demo.siproj

# 写回 .mlcproj
python tools/mlc_project.py import --root . --from demo.siproj --write
```

规则：

- `.siproj` / MFL / 文本：按行提取路径；XML 中提取 `path/file/name` 属性。
- 只导入**文件清单/源目录**，符号全部由本工具重新解析。
- 目录 → `source_dirs`；文件 → 父目录 + 对应扩展的 `include`。
- 二进制（含 NUL/UTF-16 无法识别）明确报错，不猜。
- 跨盘路径明确报错，不静默跳过。

## 7. P0 限制

- 只解析 `.m`；其他语言走现有前端，P1 接入。
- `source_dirs` 必须与项目 root 在同一盘；跨盘会明确报错，不做静默跳过。
- 不支持 `.siproj` 导入（P1）。
- `edges` 表已建，但 `matlabc.parse_file` 阶段 `fn.calls` 为空，P1 接入调用分析。
- 不自动 watch；当前是显式 `sync`（P1 加后台/文件监听）。
