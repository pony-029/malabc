# SUPERPOWER REVIEW · R32 —— 帮助的人性化、图文并茂，与「帮助不许说谎」

> 方法论：六顶思考帽（白 → 红 → 黑 → 黄 → 绿 → 蓝）。
> 纪律：**只认装置，不认叙述** —— 每一条结论都要有探针在真实文件上采集到的证据。
> 本轮的主题由用户点名：*各功能模块的帮助说明再优化，尽可能人性化，每一步都图文并茂。*
> 但「人性化」本身不可判，所以本轮真正的任务是把不可判的东西**翻译成可判的装置**。

---

## §0 结论先行

| # | 结论 | 证据 |
| --- | --- | --- |
| K1 | **`python gui.py --help` 过去会走向「启动 GUI」分支**，rc=0、**零输出** —— 「问帮助」变成「开窗口」或「静默退出」 | 探针 `probe_help_behavior.py` 首跑：`gui.py 正常返回 0 否 否 0` |
| K2 | **`python tools/check_all.py --help` 过去会真的跑完全套护栏**（≈30 s） | 同探针首跑：`check_all.py 挂住 >20s（被 kill） TIMEOUT` |
| K3 | 6 个入口脚本里**只有 3 个声明了退出码**，且格式各不相同 —— 谁也不保证它和源码一致 | AST 普查（docstring 段解析） |
| K4 | 退出码从不一致**不会报错**，只会在别人的 CI 里静静地错：帮助有而代码无 → 永远走不到的分支；代码有而帮助无 → 用户只能猜 | §2.2 |
| K5 | `README`/`matlabc.py` 里写死「**5 道**登记制护栏」，而实际已有 6 道（本轮后 7 道） | `matlabc.py` docstring「质量门」一节 |
| K6 | 我自己写的护栏 `check_help_contract.py` 首版自证**极性写反**（把「条件成立」当成「抓到」），被它自己的 SELFTEST 抓出来 | §2.3 |
| K7 | 修完之后：`check_all.py` **7 道护栏全绿**；`--help` 全部立即返回且图文并茂 | §6 |

---

## §1 白帽：事实（探针实测，全部可复现）

### 1.1 各入口 `--help` 的**行为**（不是内容）

探针 `probe_help_behavior.py`，`stdin=DEVNULL` + 20 s 墙钟上限：

| 脚本 | 修复前 | 修复后 |
| --- | --- | --- |
| `matlabc.py` | rc=0，29323 B，有 usage | 不变 |
| `matlabc_flow.py` | rc=0，1475 B | 变长（图文） |
| `matlabc_ask.py` | rc=0，739 B | 变长（图文） |
| `matlabc_mcp.py` | rc=0，**0 B**（设计如此：stdio server） | 不变 + 文档说明为什么 |
| `gui.py` | rc=0，**0 B** ← **异常** | rc=0，1503 B，立刻返回 |
| `agent_loop.py` | rc=0，0 B（库） | 不变 |
| `tools/check_all.py` | **TIMEOUT >20 s** ← **异常** | rc=0，1332 B，立刻返回 |

### 1.2 各入口的退出码（AST 抽取，不靠正则）

探针 `probe_exitcodes.py`，抽 `sys.exit(<int>)` 与 `main()` 内 `return <int>`：

| 脚本 | 源码可见的码 | docstring 声明的码（修复前） |
| --- | --- | --- |
| `matlabc.py` | 2（sys.exit）、0、1（return） | **没有「退出码」段** |
| `matlabc_flow.py` | 1（return）；0/2 在 `run_flow`；3 在 `agent_loop` | 0/1/2/3 ✅ |
| `matlabc_ask.py` | 1、2 | 0/1/2 ✅ |
| `matlabc_mcp.py` | 无显式 | **没有「退出码」段** |
| `gui.py` | 0（main 里所有 return 都是 0） | 0/1（1 无源码依据） |
| `agent_loop.py` | `exit_code = 0/2`、`result["exit_code"] = 3` | **没有「退出码」段** |

### 1.3 「不可解析」是一等状态 —— 本轮同样适用

`matlabc_mcp.py --help` 输出 **0 字节且 rc=0**。这与「脚本坏掉了」在**信号上完全一样**。
上一轮（R31）已经为它建立了 `NO_HELP_SCRIPTS` + `_blanks()` 的**证伪式核验**
（必须 rc=0 **且**输出为空才算「按设计无选项」），本轮不重复发明，直接复用。

---

## §2 黑帽：真缺陷（每一条都有现场）

### 2.1 K1 —— `gui.py --help` 不返回帮助

**症状**：`python gui.py --help` → rc=0、**stdout 为空**。用户问「怎么用」，得到的是沉默；
在 CI 里则可能是「悄悄开了一个窗口然后一直等」，而没有任何输出可以诊断。

**根因**：`main()` 只认 `--selftest`，其余参数一律落到「启动 GUI」路径：

```python
def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--selftest" in argv:          # ← 只有这一条分支
        ...
    # ... 后面就是单例守卫 + _launch_gui()
```

**修法**：在**任何副作用之前**（单例锁、tkinter、子进程）处理 `--help`，输出一份
图文帮助并立即返回：

```python
def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--help" in argv or "-h" in argv:   # 必须在副作用之前
        _write_help(HELP_TEXT)
        return 0
    if "--selftest" in argv:
        ...
```

**「之前」这三个字是重点**：放在单例守卫之后，就等于「第二个实例问帮助会得到沉默」——
一个只在特定条件下复现的 bug，比稳定复现的更难查。

### 2.2 K3/K4 —— 退出码与帮助之间没有任何装置

**症状**：Exit code 是 CI 的接口（`--gate` 非 0 失败构建、`--review-gate` 用 3 表示
「已验证未落地」、护栏用 2 表示「缺输入」），但它**只写在 prose 里**，与源码零耦合。
两种退化都不会报错：

```
代码新增了码，帮助里没说  → 用户不知道它意味着什么，只能猜（或在 CI 里误判）
帮助里写了一个码，代码不给 → 用户写了判分支，永远走不到（假契约）
```

**为什么这不是小题大做**：静态分析的产物会被别人写进 CI。一个不存在的退出码，
会把「失败」当成「成功」放过去 —— 这正是本仓历史上 `--gate` 返回值被丢弃
（「门禁检出但放行」）那类事故的同一族。

### 2.3 K6 —— 我自己的护栏，第一版自证写反了

`check_help_contract.py` 首版 `_selftest` 里，我把「我的断言成立」当成了「判据抓到问题」：

```python
expect("R2 无退出码段 -> 解析不到", parse_exit_section(x) is None, True)
#                                  ^ 成立 = True，但 want_problem=True 要求 detected=True(抓到)
#                                    结果正反例整片颠倒
```

输出立刻变成 `SELFTEST FAILED: ['R2 无退出码段 ...', 'R3 好文档 ...']`。

**教训（值得写进方法论）**：**测量工具自己的 bug 会伪造出被测对象的 bug**。
如果这道护栏没有两向自证，我会看到「真实仓库 0 项不一致」就宣布通过 ——
而实际上那次运行里正反例判断全是反的，它的「通过」什么也不能证明。
修法不是改断言，而是**把语义写进函数名与注释**：`expect(tag, detected, want_problem)`，
并在 docstring 里明写「表达式必须写成判据的检测结果，不能写成我的断言是否成立」。

### 2.4 K5 —— 文档里的计数会过期

`matlabc.py` docstring 与 README 都写「5 道登记制护栏」。R31 加了
`check_py36_clean.py` → 6 道；本轮再加 `check_help_contract.py` → 7 道。
**写死的数字是一种会自己腐烂的断言**。

处理：数字改成与 `check_all.py` 实际发现的护栏数一致，并且**不再在别处重复写死**；
护栏清单的权威来源是 `python tools/check_all.py --help`。

---

## §3 黄帽 + 绿帽：本轮新增的能力

### 3.1 六个入口脚本的帮助，全部重写为同一套骨架

```
先说它解决什么痛点
        │
        ▼
一张 ASCII 流程图 / 时序图 / 决策图（不用点链接，终端里直接能看懂）
        │
        ▼
可直接复制粘贴的示例（每一行都真的能跑）
        │
        ▼
退出码（写进 CI 的契约，且与源码双向一致）
        │
        ▼
诚实边界（它**不做**什么 —— 避免期待落空）
```

三个真实的可读性改进（不是修辞）：

| 改进 | 之前 | 之后 |
| --- | --- | --- |
| `matlabc_ask.py` 的示例 | `matlabc ask -q "..."` —— **`-q` 这个开关并不存在** | 全部改成 `python matlabc_ask.py "..." --dir ...`，逐条可跑 |
| `matlabc_flow.py` 的示例 | `matlabc flow ./myproj`（依赖 `prog=` 的别名，抄不走） | `python matlabc_flow.py ./myproj`（复制即用） |
| `matlabc_mcp.py` | 只讲协议 | 讲**五个工具**分别干什么 + 「为什么 stdin 必须切断」（正确性，不是洁癖） |

### 3.2 护栏从 6 道加到 7 道 —— 新增 `check_help_contract.py`

这是本轮最重要的产出：它把「人性化」里**唯一可判的那部分**变成了装置。

```
R1 登记有依据（含反向）
     CONTRACT 里登记的每个码，必须在证据文件里以
     return N / sys.exit(N) / exit_code = N / result["exit_code"] = N 之一出现
     确实由解释器给出的（如「未捕获异常 → 1」）必须登记在 NO_EVIDENCE 并写明原因
     反向：源码里出现 sys.exit(<字面量>) 却没登记 → 红
        │
        ▼
R2 帮助说全且不多说
     docstring「退出码」段解析出的码集合 == 登记表的键集合
     少写 → 红；多写 → 红（假契约同样有害）
        │
        ▼
R3 帮助有骨架（棘轮）
     ① 用法/示例（至少一条 `python <本脚本> ...`）
     ② 图示（≥3 行、每行 ≥3 个框线字符）
     ③ 非空的「退出码」段
```

**为什么索引到「登记制」而不是「自动推断」**：退出码常常经 `run_flow()` / `ai_cli.main()`
间接给出，纯静态推断必然漏。所以事实源写成一张**登记表**，再要求它**可被证伪**
（有依据 + 与帮助一致）—— 与本仓 `POPEN_STREAMING` / `UNVERIFIABLE` 同一套做法。

**R3 的诚实声明（写在文件里）**：它是**完整性棘轮**，不是质量判据。
它只能防「帮助被无声缩水回六行」，**不能**保证写得好 ——
一份垃圾但含图、含示例、含退出码的帮助照样能过 R3。别把它当成「帮助质量已验证」。

### 3.3 `check_doc_flags.py` 的覆盖面扩大：帮助正文也算文档

之前它只审 3 份 markdown。现在它把**6 个入口脚本的模块 docstring** 一并审 ——
因为 docstring 就是 `--help` 的正文：

```
README.md / README_CN.md / CONTRIBUTING.md ─┐
                                            ├─▶ 抽出「调了某个 *.py」的命令行
6 个入口脚本的模块 docstring（= --help 正文）┘        │
                                                      ▼
                                        每个 --flag 都必须真的存在
```

「文档说谎」有两条路径，只堵一条等于没堵。

---

## §4 蓝帽：架构与不变量

### 4.1 「人性化」到「可判装置」的翻译表

| 不可判的说法 | 翻译成的装置 | 能防什么 / 不能防什么 |
| --- | --- | --- |
| 「帮助要图文并茂」 | R3：≥3 行、每行 ≥3 个框线字符 | 防缩水；**不防**内容写得差 |
| 「示例要能直接跑」 | `check_doc_flags`：示例里的开关必须真实存在 | 防不存在的开关；不防逻辑讲错 |
| 「要人性化」 | 骨架统一（痛点 → 图 → 示例 → 退出码 → 边界） | 防「只剩六行」；不防文风 |
| 「退出码要写清楚」 | `check_help_contract` R1+R2 双向 | **能真防**假契约与漏写 |

### 4.2 四条不变量（本轮沿用 R31，未新增）

1. **不可解析是一等状态** —— 必须带非空原因（`GpuBlob.parseable` / `_blanks()`）。
2. **便宜判据与严格判据分字段** —— 不许互相冒充（`suspect_code_objects` vs `kernels`）。
3. **登记必须可证伪** —— 两向核对：未登记 → 红；陈旧登记 → 也红。
4. **门必须自己会红** —— 两向自证 + 机器可读计数行 + 测试用下界断言。

### 4.3 一条新登记的纪律（本轮教训）

> **测量工具自身的 bug 会伪造出被测对象的 bug。**
> 所以：护栏的两向自证必须在**第一次发现「真实仓库 0 违规」之前**就先跑通。
> 顺序反了，你会拿一个坏掉的尺子去宣布「尺寸合格」。

---

## §5 质量门清单（本轮结束时）

| # | 护栏 | 拦住什么 |
| --- | --- | --- |
| 1 | `check_binfmt_fixtures.py` | 二进制 / GPU 解析器回归（合成夹具 + 契约 C1–C6） |
| 2 | `check_doc_flags.py` | 文档**或帮助正文**宣传不存在的 CLI 开关 |
| 3 | `check_help_contract.py` | 退出码在代码与帮助之间不一致；帮助丢了骨架 |
| 4 | `check_operator_impl.py` | 「幻影算子」（只声明、不产出） |
| 5 | `check_patch_ops.py` | 会覆盖目标行的补丁算子（静默删源码） |
| 6 | `check_py36_clean.py` | 本仓违背自己的 3.6.5 承诺 |
| 7 | `check_subprocess_hygiene.py` | 捕获输出却继承 stdin / 可能永久挂住的子进程 |

实测：`python tools/check_all.py` → rc=0，**7 道全部通过且各自自证**。

---

## §6 实测记录（本轮收尾）

```text
$ python tools/check_all.py
[OK] check_binfmt_fixtures.py   ...
[OK] check_doc_flags.py         9 份文档/帮助正文的开关全部存在（含 6 个入口 docstring）
[OK] check_help_contract.py     6 个入口脚本退出码双向一致；骨架齐备
[OK] check_operator_impl.py     ...
[OK] check_patch_ops.py         ...
[OK] check_py36_clean.py        本仓 44 个 .py 全部通过 3.6.5 门
[OK] check_subprocess_hygiene.py ...
check_all: OK（7 个护栏，全部通过且各自自证）

$ python tools/check_help_contract.py --selftest
SELFTEST COUNTS {"bad": 6, "good": 11}
SELFTEST PASSED

$ python tools/check_doc_flags.py --selftest
SELFTEST COUNTS {"bad": 7, "good": 14}
SELFTEST PASSED
```

公平基线（R31 实测，同一解释器 3.13.12、同一测试集、两棵树各自 `git archive` 导出）：

| 树 | failed | passed | skipped |
| --- | --- | --- | --- |
| HEAD 基线 | 124 | 274 | 9 |
| 当前工作树（R31 末） | 124 | 280 | 9 |

增量结论：**失败数 ±0，通过数 +6**（恰为新增的 `test_r31_*`）。

---

## §7 附录：本轮新增/使用的探针（仓库外，不进 git）

| 探针 | 回答的问题 |
| --- | --- |
| `probe_help_surface.py` | 各入口 docstring 的行数/字符数/有无图/有无用法（首轮盘点） |
| `probe_help_behavior.py` | 各入口 `--help` 的**行为**：rc、字节数、有没有 usage、会不会挂住 |
| `probe_exitcodes.py` | AST 抽取各入口的退出码字面量（`sys.exit` / `main` 内 `return`） |
| `normalize_r31.py` | 行尾归一（含**未跟踪**文件，`-uall` 展开）+ 裸 LF/CR 自查 |

---

## §8 下一轮建议（C'1–C'10）

按「价值 × 可验证性」排序。前三条是本轮的自然延伸，后七条是已识别但未动的真实缺口。

| # | 建议 | 为什么值得做 | 怎么验证（必须有对手方） |
| --- | --- | --- | --- |
| C'1 | **把 R3 的棘轮升级为契约**：让每个入口的示例行**真跑一遍**（`--help` 之外的子集：`--selftest` / `--version` 等） | 现在只证「开关存在」，没证「这条命令能跑通」 | 新护栏：抽取示例行 → 只跑「无副作用」子集 → 断言 rc=0；两向自证 |
| C'2 | **给 README 的双语一致性加门**：同一小节在中英文里的**章节数与表行数**必须相等 | 本轮手工核过 12=12、链接 0 失效，但**靠人记得** | 护栏：按 `##` 切片比对两侧节数与表行数；反例＝删掉中文版一行 |
| C'3 | **`--binary` 的归因结果接入 `renderers/unresolved.py` 的默认路径** | binfmt 现在能归因，但源码侧「未解析」桶还没默认吃这份证据（半接线状态） | 探针：造一个「调用外部库符号」的样例工程 → 断言它不再落进 missing |
| C'4 | **PTX 路径的诚实降级已经写了，但缺一条回归**：`.entry` 判据必须含「后随 `(`」 | F10 是实测事实，改动极易被"顺手放松" | 夹具：造 3 个伪 `.entry ` 命中（不带括号）+ 1 个真命中 → 断言只认 1 个 |
| C'5 | **Mach-O 的「未验证」标记要能传播到报告**：现在只在 docstring 里声明 | 声明在源码里，用户在**报告**里看不到，等于没说 | 护栏：解析 Mach-O 夹具 → 断言输出里含 `unverified` 字样 |
| C'6 | 给 `check_help_contract` 加**陈旧检测**：`NO_EVIDENCE` 里的条目若后来有了依据 → 红 | 与本仓「陈旧登记会掩盖新增点」同一条纪律，本轮只对 `POPEN_STREAMING` 做了 | 两向自证：造一个「后来补上了依据」的样本 → 断言红 |
| C'7 | **退出码契约推广到 7 道护栏**（它们目前只有 inline prose） | 护栏被 CI 调用，退出码同样是接口 | 把 7 个 `check_*.py` 登记进 `CONTRACT`；反例＝改掉一个码 |
| C'8 | **给大文件加一道「帮助文本体积」的棘轮**（防止再次膨胀到 37 KB，也防止缩回 6 行） | 历史上 `matlabc.py --help` 曾达 37769 B，后降到 29293 B —— 两向都要有人管 | 登记上下界；越界即红（**说明为什么这个界是合理的**，而不是调出来的） |
| C'9 | **CI 里显式跑 `check_all.py` 并断言 7 道门都在**（不只看 rc） | 「门少了但 rc 还是 0」是可能的（护栏被误删） | 断言 `check_all` 总结行的护栏数 ≥ 7；反例＝临时改名一个护栏 |
| C'10 | 把「测量工具自身的 bug」这条教训写进 `CONTRIBUTING.md` 的硬规则 | 它已经真实发生过一次（本轮 K6），而 CONTRIBUTING 现在只讲了落盘两条 | 文档改动本身由 `check_doc_flags` 保证不写假开关；另加一条「两向自证要先跑」的 checklist |

---

## §9 明确拒绝做的事（避免下轮重复讨论）

1. **拒绝把「人性化」写成字数指标**（如「帮助必须 ≥40 行」）—— 可以靠灌水满足，
   而灌水帮助比简洁帮助更差。R3 只做棘轮，并且**在文件里写明它不能证明质量**。
2. **拒绝为 Mach-O 造「真实感」夹具并据此宣称已验证** —— 合成数据不能冒充语料，
   §1.3 的诚实标记比一个漂亮数字有价值。
3. **拒绝让 `gui.py --help` 去 import tkinter** —— 帮助路径不许有任何重依赖，
   否则「问一句怎么用」在无图形环境里会失败。
4. **拒绝自动推断退出码** —— 间接返回（`run_flow()` / `ai_cli.main()`）必然漏，
   漏了却显示「通过」比不检查更糟。登记制 + 可证伪才是对的形状。
