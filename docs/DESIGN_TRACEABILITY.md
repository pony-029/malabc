# 可追踪性设计：每一步都能被看见

> 目标：任何一步（模块内、模块间）都留下**可回放、可对账**的记录，
> 而不是只有首尾两个数。

## 一、问题：现在只能看首尾

跑一次 `snr.m`，今天能看到的只有：

```
MIR: 7 个 op / 0 未映射
运行输出: y: 0
```

中间八步（HIR 往返、工程装配、gcc、C 运行、VM、对账、反推）全是黑箱。
出问题时**无法回答**：这一步的输入是哪一份？上一步输出真的进了这一步吗？

## 二、事件模型（一步一行 JSONL）

```json
{"step":"S2","module":"mir","kind":"control","action":"MATLAB → MIR",
 "in":"a1b2c3d4e5f6","out":"9f8e7d6c5b4a","status":"ok","ms":43,
 "detail":{"ops":7,"unmapped":0}}
```

| 字段 | 含义 | 为什么必须有 |
|---|---|---|
| `step` | 序号 S1..Sn | 顺序即因果；跳号说明某步被跳过 |
| `module` | 哪一层（front/hir/mir/emit/build/run/vm/verify/cmir） | 定位到模块，而非"某处" |
| `kind` | `control`（谁触发）\| `data`（传了什么） | **控制流与数据流分开记** |
| `action` | 人读一句话 | 日志要能直接贴进 issue |
| `in` / `out` | 输入/输出的 sha256 前 12 位 | **让"传的是哪一份"可核对** |
| `status` | ok / fail / skip | 三态，不是二态（skip 不能被当成 ok） |
| `ms` | 耗时 | 定位退化 |
| `detail` | 结构化细节 | 便于机器断言，不用解析句子 |

### 为什么摘要比"文件名"重要

文件名说了不算 —— 同一路径在不同时刻是不同内容。**摘要让"这一步吃的是哪一份"成为可核对的事实**，
并且能把上下游串起来：`S2.out == S3.in` 就是一条可机器判定的链路完整性判据。

## 三、三级粒度

| 级 | 粒度 | 现状 | 用途 |
|---|---|---|---|
| **L1 运行级** | 一次命令 → 一个 jsonl | ✅ 已实现（`tools/trace_demo.py`） | 复现一次失败 |
| **L2 模块级** | 每个模块进出各一条 | ✅ 已实现（9 步） | 定位是哪一层出问题 |
| **L3 语句级** | 每条 MIR 语句 | 部分（MIR 自带 `# src:N`） | 定位到源码行 |

## 四、怎么用

```bash
python tools/trace_demo.py translate/examples/numeric/snr.m -o snr.jsonl
python tools/trace_view.py snr.jsonl -o snr.html      # 静态页，无脚本无外链
```

实测（`snr.m`）：

```
S1 front  data    读源码 snr.m                ok
S2 mir    control MATLAB → MIR               ok   ops=7
S3 hir    data    MIR → HIR → MIR 恒等        ok   identical=True
S4 emit   control m2c build 生成 C 工程        ok   files=12
S5 build  control gcc 编译                    ok
S6 run    data    C 可执行运行                 ok
S7 vm     data    Rust VM 执行同一份 MIR       ok
S8 verify control C 与 VM 数值一致             ok
S9 cmir   data    C → MIR 反推                ok
```

## 五、与既有产物的关系（不另起一套）

| 既有 | 在追踪里的位置 |
|---|---|
| MIR 的 `# src:N` / `# why:K` | L3 语句级的现成来源，直接嵌进 `detail` |
| `facts.py` 的事实层 | 追踪记录**事实**，分析侧消费事实，两者同一口径 |
| `flow/` 图集 | 图回答"应该怎么走"，追踪回答"这次实际怎么走" |
| 门禁 41 门 | 门回答"是否合规"，追踪回答"哪一步不合规" |

## 六、三条硬规则

1. **不许只记成功**：`fail` 与 `skip` 必须单独成行，且带原因 —— 否则"没跑"和"跑对了"看起来一样。
2. **摘要必须来自**内容本身**，不能来自文件名或时间戳。
3. **追踪不得改变行为**：`--trace` 关闭时零开销（本次实现是独立采集脚本，未侵入主链）。

## 七、下一步（增量，不改现有链）

| 序 | 事项 | 判据 |
|---|---|---|
| 1 | 把 tracer 接进 `roundtrip.py` / `m2c build`（`--trace` 开关） | 关闭时输出逐字节不变 |
| 2 | 链路完整性判据：`S(n).out == S(n+1).in` 全成立 | 任一断链即红 |
| 3 | 追踪页进 `flow/traces/`，目录页可发现 | flow_catalog 列出 |
| 4 | L3：每条 MIR 语句一行（含 `# src`） | 能回答"第 12 行发生了什么" |
