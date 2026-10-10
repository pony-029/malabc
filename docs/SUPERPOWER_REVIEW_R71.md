# R71 复盘：让「大多是 universal」的那一类二进制，第一次说出它依赖谁

> 本轮落地 R68 §8 的 **C18-1**（= R69 §7 / R70 §7 里一直挂在「高」的那一项）：
> **fat（universal）Mach-O 逐片解析**。
> 一句话结论：`flavour == "fat"` 在此之前只把切片清单写进 `notes` —— 依赖与符号
> 只在 thin 路径读，于是「这个 universal dylib 依赖谁」的答案**恒为空**；
> 本轮把每一片都当独立的 thin 文件读，并给这条能力配了判据 **C13**。

---

## §0 一图看懂：本轮的「缝」在哪

```
   真实 macOS 二进制大多是 universal（x86_64 + arm64 两片）
   ┌──────────────────────────────────────────────────────────┐
   │ fat 头 (0xCAFEBABE) + nfat_arch=2 + 两片 fat_arch        │
   ├──────────────────────────────────────────────────────────┤
   │  slice[0]  x86_64   ── 一个**完整**的 thin Mach-O         │
   │     LC_ID_DYLIB  libfat.dylib                            │
   │     LC_LOAD_DYLIB libSystem.B.dylib / libonly0.dylib      │
   │     LC_SYMTAB  _fa_export (导出) / _fa_priv (内部)        │
   ├──────────────────────────────────────────────────────────┤
   │  slice[1]  arm64    ── 另一个完整的 thin Mach-O           │
   │     LC_ID_DYLIB  libfat.dylib     ← 与 slice[0] **同名**  │
   │     LC_LOAD_DYLIB libSystem.B.dylib / @rpath/libonly1.dylib│
   │     LC_SYMTAB  _fb_export                                │
   └──────────────────────────────────────────────────────────┘
                    │
        R71 之前    │  只 for i in range(n): notes.append("slice[i] …")
                    ▼
        rep.flavour="fat"  rep.arch="fat(2)"  deps=[]  symbols=[]  sections=[]
                    │
        R71 起      │  每一片 → _SliceView（偏移换算）→ 复用 thin 解析器
                    ▼
        deps=4（去重、每条带 slice[0,1] 归属）symbols=2 段/节=8（偏移已重基）
```

**为什么这条缝值得一轮**：`docs/SUPERPOWER_REVIEW_R68.md` §1.2 的 D 用例（真实
Mach-O 依赖）之所以被卡住，根因就是「依赖读不出来」；而**真实文件大多是
universal** ⇒ 修好 thin 路径在真实世界里只覆盖了少数派。

---

## §1 白帽：装置与读数

### 1.1 装置（先断言前置条件，再判 OK）

`_r71/probe_r71_fat_macho.py`（仓库外、LF、**自带打包器**）：

* **不用被测对象当它自己的量具**：本脚本自带 `_thin()` / `_fat()` 两个打包器
  （只依赖 `struct`），切片布局、期望表全部由本脚本算；产品的 `macho.py` 只出现在
  **被测的那一侧**（`binfmt.parse`）；
* **前置 0**：打包器自洽（thin 魔数 / 依赖名 / 符号名真的在字节里）；
* **前置 1（关键）**：先造一个 **thin 对照件**（同打包器、同依赖同符号），断言产品
  把它读出来（3 依赖 / 1 导出）。thin 都读不出来 ⇒ 整轮 **`INDETERMINATE`**，
  **而不是**「fat 也坏了」；
* 两个**必须被点名**的反向样本：第 1 片换成垃圾（第 0 片必须照常解析 + 点名
  `slice[1]`）、两片都是垃圾（0 依赖 + 两条点名 note，不许崩）。

### 1.2 基线（改动之前）—— 三类读数分文件

| 文件 | 口径 | fat 侧 | thin 对照 |
| --- | --- | --- | --- |
| `ev_base_before_fix.txt` | 工作区（= 当时的 HEAD） | **FAT-BLIND**：0 依赖 / 0 符号 / 0 段 | 3 依赖 / 1 导出 ✅ |
| `ev_base_worktree_head.txt` | **`git worktree add --detach` 的 HEAD 树** | 逐字相同（FAT-BLIND） | 逐字相同 ✅ |
| `ev_mid_after_impl.txt` | 实现后（门未加） | **FAT-READY**：4 / 2 / 8 | ✅ |
| `ev_final_recheck.txt` | 全部改动定稿后复量 | **FAT-READY**：4 / 2 / 8 | ✅ |

两类基线（工作区 / worktree）**逐字相同**这件事本身是读数：它排除了
「基线是改动过的树」这种可能。worktree 用完已 `git worktree remove`，
`git worktree list` 只剩主树。

### 1.3 修后逐项读数（`ev_final_recheck.txt`）

| 项 | 读数 |
| --- | --- |
| 依赖并集（按 (名字, kind) 去重） | **4** = `libfat.dylib`(id) + `libSystem.B.dylib` + `libonly0.dylib` + `@rpath/libonly1.dylib` |
| 去重后重复条目 | **0** |
| `detail` 里的切片归属 | 两条同名的 = `slice[0,1]`；两条独有的 = `slice[0]` / `slice[1]` |
| 导出符号 | **2**（`_fa_export` + `_fb_export`），内部 `_fa_priv` **不在**导出表 |
| 段/节 | **8** = 4 × 2 片，全部带 `slice[i]:` 前缀 |
| 偏移重基 | 每片**最小** `file_off` == 该片容器起点（48 / 9264） |
| 坏片（只有第 1 片是垃圾） | 第 0 片依赖照常读出 ✅ + `slice[1]` 被点名 ✅ |
| 坏片（两片都是垃圾） | 0 依赖 / 0 符号 + **2** 条点名 note（不许崩）✅ |

---

## §2 真实现：四条取舍（都写进了 `binfmt/macho.py` 的模块 docstring）

| 事项 | 做法 | 为什么（不这么做会怎样） |
| --- | --- | --- |
| 切片怎么读 | `_SliceView`：只做**偏移换算**的视图，`read` 被切片边界夹住 | 真实 universal 的单个切片常 > `MAX_CHUNK`（8 MiB）。整片读进内存要么爆，要么被上限截断 —— 而**被截断的切片会安静地少读符号表**（`_read_symtab` 按 symoff/stroff 在片内定位） |
| 片内偏移 | `section.file_off` **重基**为 `slice_off + s.file_off` | `gpu.py` 是拿 `file_off` 去**宿主文件**里读的。不重基 ⇒ 读到别的切片的字节（错得很安静，正是本仓最怕的那一类） |
| 同名片 | `_FatMerge` 按 (名字, kind) **去重**，切片下标进 `detail`（`slice[0,1] LC_LOAD_DYLIB`） | universal 的每一片都带**同一份** install name 与**同一批**外部符号；不去重会把依赖表与导出表按片数整倍膨胀，而 `missing_dependencies` 是逐条走的，重复会污染「未提供」的结论 |
| 段名 | 加 `slice[i]:` 前缀（两片的 `__TEXT` 会重名），并新增 `gpu.section_base_name()` 剥前缀 | GPU 段名提示表是按**精确**名查的 ⇒ 不打前缀分不开、打前缀又打瞎提示表；剥前缀的实现**只有一处**，`analyze()` 与 `_magic_fallback()` 都走它，免得两份慢慢分叉 |
| 读不懂的片 | 一律留下**带片号**的 note（魔数不对 / 越过文件末尾 / offset-size 非法 / 读取失败），其余片照常解析 | 静默丢片比报错更糟：报告会声称「这个库没有依赖」，而事实是**我们没读** |

**仍不做（诚实边界，已写进 docstring）**：反汇编、重定位、运行期符号绑定
（two-level namespace / dyld shared cache）；`fat_arch_64`（magic `0xCAFEBABF`，
32 字节 fat_arch）**不认** —— `sniff()` 只认 `0xCAFEBABE` 的 20 字节形态，
一个 `0xCAFEBABF` 文件会走「无法识别的容器类型」而不是被猜测。

---

## §3 两向判据：C13

`tools/check_binfmt_fixtures.py` 的**签名** `C1–C12` → **`C1–C13`**；夹具构造器拆成
`_build_macho_bytes()`（纯函数，返回字节）+ `_make_macho()`（写盘），于是
`_make_macho_fat()` 能按 spec 造出**完整**的 thin 切片，并能用 `raw={i: bytes}`
把某一片换成任意字节。切片表由夹具自己算并**返回**给判据当独立期望。

### 3.1 判据拆成三个子判据（互不重叠）

| 子判据 | 钉什么 |
| --- | --- |
| `_c13_check_report` | 依赖（名字 + kind + **去重** + 切片下标点名）、导出（两片都要有、内部不许混入、不许重名）、段/节（数量 = 4 × 片数、都有 `slice[i]:` 前缀、**最小 `file_off` == 该片容器起点**、每条都落在本片区间内）、夹具自洽（切片起点必须是 thin 魔数，否则报「**是期望表自己错了**」而不是赖产品） |
| `_c13_check_broken_slice` | 第 1 片垃圾 ⇒ 第 0 片照样读出依赖与导出，且 notes 必须**点名** `slice[1]`；两片都垃圾 ⇒ 容器仍被认成 macho、0 依赖 0 符号、**两条**点名 note |
| `_c13_check_gpu_hint` | `section_base_name("slice[1]:__nv_fatbin") == "__nv_fatbin"`、无前缀的名字一个字节都不动、剥完查得到提示、fat 上真出 `detected_by="section_name"` 的 blob、且 `parseable=False` 的 blob 必须有 `reason`（C1 契约在 fat 路径上不许失守） |

**证人怎么选**（这是本判据的核心，不是随手挑的名字）：
`@rpath/libonly1.dylib` 与 `_fb_export` **只在第 1 片出现** —— 「只读首片」的实现
让它们**必然缺席**，而「两片都读」的实现必然看得见。反过来，
`libfat.dylib` / `libSystem.B.dylib` 两片都有，钉的是**去重不许把表冲胀**、
且归属下标**不许丢**。

### 3.2 两向：`--selftest` 与变异体

`--selftest` 从 `{"bad": 8, "good": 8}` 提到 **`{"bad": 11, "good": 10}`**
（新增 3 坏 + 2 好；文件里的下界棘轮同步提到 `11/10`，谁删一个样本立刻红）。
其中坏样本 17 是刻意设计成**红只有一条理由**的：那份「只读首片」的合成报告在
段表、偏移、kind、下标上**全部合规**，唯一缺的是「只在第 1 片」的那条依赖。

`_r71/mutate_r71.py`（**整棵工作区复制到 `_r71/mut`，不动真树**）注 6 个变异体：

| 变异体 | 期望 | 实测 |
| --- | --- | --- |
| m1 一片都不解析（恢复 R71 之前的行为） | 红 | `tests rc=1` · `gate rc=1` |
| m2 片内偏移**不重基** | 红 | `tests rc=1` · `gate rc=1` |
| m3 同名片**不去重** | 红 | `tests rc=1` · `gate rc=1` |
| m4 读不懂的片**静默跳过**（不留话） | 红 | `tests rc=1` · `gate rc=1` |
| m5 GPU 段名提示**不剥前缀** | 红 | `gate rc=1` |
| m6 段表丢前缀（两片的 `__TEXT` 混在一起） | 红 | `tests rc=1` · `gate rc=1` |

**6/6 全红、还原后全绿**（`CONTROL` 与 `RESTORE` 两次都 `3 passed` + `gate rc=0`）。

⚠ **「非 0 退出」不等于「判据生效」**（R68 的教训）：为此逐条抽取了失败信息，
确认红在**判据**上而不是 `ImportError`/`SyntaxError` 上（`ev_mutant_reasons_r71.txt`）：

```
m1 :: AssertionError: ('libfat.dylib', 'id_dylib', [])
m4 :: AssertionError: ['Mach-O: slice[0] LC_ID_DYLIB=libfat.dylib', …]   ← notes 里就是没有 slice[1] 的点名
m6 :: AssertionError: (0, ['__TEXT', '__TEXT,__text', '__TEXT', '__TEXT,__text'])
```

### 3.3 端到端（公开 CLI 那一侧）

`tests/test_matlabc.py` 新增 3 条：

| 测试 | 层次 |
| --- | --- |
| `test_r71_fat_macho_slices_are_parsed_end_to_end` | 走**公开 CLI**（`--binary … --binary-json`）拿依赖/符号，再用产品对象核切片归属、段表数量与**重基** |
| `test_r71_fat_broken_slice_is_named_not_swallowed` | 坏片点名 + 「两片都坏 ⇒ 0 依赖」 |
| `test_r71_binfmt_gate_c13_is_two_way` | 门的看守：签名在册、`GUARD_CONTRACT` 描述含签名（H1）、两侧 README 含签名（P5）、**纯函数两向**（盲报/半读必须红、真产品必须绿）、`--selftest` 下界 |

`_r71_fat()` 是**第三份**手写布局（产品一份、护栏夹具一份、测试一份）—— 三份只有
在对时才可能同时通过。测试里那两条「只读首片」「盲片」的合成报告是**自己拼的**，
不经过产品，因此纯函数判据的牙齿是独立可证的。

---

## §4 门禁（全绿才继续）

| 门 | 命令 | 读数 |
| --- | --- | --- |
| 聚合 | `python tools/check_all.py`（3.13） | **rc=0**（17 个护栏，各自 `--selftest` 双绿） |
| 本门 | `python tools/check_binfmt_fixtures.py` | **rc=0** · 成功行 `判据族 C1–C13` |
| 本门自证 | `… --selftest` | `{"bad": 11, "good": 10}` · rc=0 |
| 阅读对等 | `tools/check_readme_parity.py` | rc=0（P1/P2/P4/P5 全绿；两侧门表各 17 行） |
| 帮助契约 | `tools/check_help_contract.py` | rc=0（退出码契约 + G0b + 散文数字 + 体积三臂） |
| 永久红登记 | `tools/check_known_red.py` / `--selftest` | rc=0 · `{"bad": 12, "good": 2}` |
| 基线门 | `tools/check_baseline.py --selftest` | rc=0 · `{"bad": 12, "good": 19}` |
| 家族 pytest | `-k "r68 or r70 or r71"` | **9 passed** |
| 家族 pytest | `-k "r61 or r62 or r63 or r64 or r65 or r66 or r67"` | **14 passed** |

**帮助体积**：`matlabc.py` 的 docstring 改了「fat 切片清单」→「**fat 逐片解析**」——
刻意做**等长改写**（两个 4 字词），因此体积快照与规范形快照**都不动**，实测
3.13 **50676 B** / 3.10 **50706 B**，与 `HELP_BYTES_SNAPSHOT` 逐字相同，
规范形臂（容差 0）也过。`HELP_DRIFT_BYTES = 64` **未动**。

⚠ 本轮**没跑** `check_baseline --full`：按 R63 的判据 T1，**加了测试的轮次 `--full`
必然红**（nodeid 集合变了），这不是回归。加测试的同时改基线快照会把 T1 变成噪声。

---

## §5 提交与远端复核

| 提交 | 内容 |
| --- | --- |
| **`395a5c8`**（tree `270c3371`） | 主提交：`binfmt/macho.py` + `binfmt/gpu.py` + `tools/check_binfmt_fixtures.py` + `tools/check_all.py` + `tools/check_help_contract.py` + `tests/test_matlabc.py` + `matlabc.py` + 两侧 README + CONTRIBUTING（10 文件 / +837 −37） |
| （本文档） | `docs/SUPERPOWER_REVIEW_R71.md` |

推送：`9b4a79f..395a5c8  main -> main`（前台）。

远端复核 `_r71/verify_remote_r71.py`（**先写出来、再真跑，然后才引它的读数**；
脚本带一条**负控制**：改克隆里一个字节后，工作区 sha256 与 blob sha256 **必须不同**，
否则说明脚本根本没在看内容）：

```
[main-commit] CLONE rc=0
[main-commit] HEAD  local=395a5c848d8e38e089ad0a60dc80ebe985bdb5ab clone=(同)  OK
[main-commit] TREE  local=270c33714ea7c938306c21c674b04dddb6b01d38 clone=(同)  OK
[main-commit] PIN   expect=395a5c84…  head_is_it=True  head_descends_it=True
[main-commit] LS_TREE entries local=254 clone=254  OK
[main-commit] SHA256 三处核对 254/254 逐字相同，差异 0
[main-commit] clone check_all(3.13) rc=0
[main-commit] clone pytest -k r71 rc=0（3 passed, 476 deselected）
[main-commit] NEGCTRL 改一字节后 …必须不同=True
[main-commit] REMOTE_VERIFY OK
```

> ⚠ 本文档钉的是**祖先哈希**（主提交 `395a5c8` / tree `270c3371`），不是「当前
> HEAD」—— 本文档所在的那一次提交一落，后者的说法当场变假话（R68 真的发生过）。
> 对**最终 HEAD** 的第二次真跑读数见文末「附 1」。

---

## §6 本轮改动的文件清单

| 文件 | 改动 |
| --- | --- |
| `binfmt/macho.py` | 新增 `_SliceView` / `_FatMerge` / `_parse_fat_slice`；重写 `_parse_fat` 为逐片解析；模块 docstring 补 R71 的四条取舍与仍不做的两件事 |
| `binfmt/gpu.py` | 新增 `section_base_name()`（剥 `slice[i]:` 前缀，一处实现）；`analyze()` 与 `_magic_fallback()` 的段名查表都走它 |
| `tools/check_binfmt_fixtures.py` | 拆出 `_build_macho_bytes`；`_make_macho_fat` 支持 `slice_specs` / `raw`；新增判据 **C13**（三个子判据）+ `FAT_SLICE_SPECS` / `FAT_EXPECT_*` 期望表；`--selftest` 加 3 坏 + 2 好并把下界提到 11/10；`ROW_SIGNATURE` → `C1–C13`；docstring / 成功行同步 |
| `tools/check_help_contract.py` | `GUARD_CONTRACT` 里本门 `rc=0` 描述 `C1–C12` → `C1–C13`（H1 的对手方） |
| `tools/check_all.py` | ASCII 树「契约 C1..C12」→ `C1..C13`；补 R71 历史注释（**没有加门**，门数仍 16/17） |
| `tests/test_matlabc.py` | `_r68_macho` 加 `cputype` 形参；新增 `_r71_fat` / `_r71_slice_bytes` 与 3 条 `test_r71_*`；R68 那条测试的签名常量升到 `C1–C13` |
| `matlabc.py` | 帮助里「fat 切片清单」→「fat 逐片解析」（**等长**，快照不动） |
| `README.md` / `README_CN.md` | 本门那一行**同行**补 R71 说明 + 签名升到 `C1–C13`；R70 那句「事实是 `C1–C12`」加「当时 / at the time」限定 |
| `CONTRIBUTING.md` | 新增 R71 小节（四条取舍表 + 判据拆解 + 变异体读数 + 顺带量到未修的一条） |
| `docs/SUPERPOWER_REVIEW_R71.md` | 本文档 |
| （仓库外）`_r71/` | 探针 / 变异体驱动 / 远端复核脚本 / 五份证据文本（LF，**不入库**） |

---

## §7 本轮的自伤（写下来，别让下一个会话重踩）

1. **「第一次就全绿」的测试是可疑的** —— 3 条 `test_r71_*` 首跑全绿，所以我
   按纪律去注变异体：**6/6 全红**之后才承认它们有牙齿。若跳过这一步，m1（恢复
   旧行为）这种「看起来还在工作」的变异体就会被漏过去。
2. **夹具没写完，门当场抓了三条** —— `FAT_SLICE_SPECS` 首版漏了 `symtab=`，
   门的头一次运行就报「fat 里读不出导出符号 `_fa_export`」。这不是设计的毛病，
   是**夹具没写完**；但值得记的是：**是门先说话，不是我先看出来**。
3. **手写多行字面量又踩一次**：两个 `dict(...)` 的 `dep_cmds=[…])` 写成 `])`
   ⇒ 提前关掉 `dict(` ⇒ `SyntaxError: unmatched ')'`。与 R65/R68 同一个坑。
4. **追加判据时把上一段的收尾 `return findings` 复制成了两条**（死代码）——
   是「读完再改」才发现的，`ast.parse` 不会报死代码。
5. **探针首版引用了未定义的 `p_bad2`**（NameError），而且「两片都坏」的样本是从
   完整 fat 字节里截头再拼垃圾 ⇒ 表里的 offset 指向文件外 ⇒ 整个文件被判成
   「无法识别的容器类型」——**测的根本不是我要测的东西**。教训：反向样本的
   **自洽性必须与正向样本一样先断言**（现在探针里 `neg_garbage_all` 会打印
   `container` 与 `n_named_notes`，就是为了防这个）。
6. **变异体驱动首版用 CRLF 文件配 `\n` 锚点** ⇒ 锚点必然 0 命中。改成
   「读进来归一成 LF、写回 `newline="\r\n"`」，并在锚点命中数 != 1 时整体不写盘。
7. **全仓替换把一句历史陈述改成了假话**：`README` 里 `C1–C12 → C1–C13` 的全局
   替换顺手改了 R70 那句「事实是 `C1–C12`」，而那是**当时**的事实。发现后加
   「当时 / at the time」限定还原 —— 这与「钉祖先哈希、别钉当前 HEAD」是
   **同一类错误**：把历史读数的现在值写进历史句子。

8. **`Write` 写出来的是 LF，而受控文件必须是 CRLF** —— 本文档第一次落盘时是
   **纯 LF**（`CR=0 / LF=322`），是 `docs/` 下 **44 份 `.md` 里唯一的一份
   LF 文件**（其余 43 份、含全部 25 份 `SUPERPOWER_REVIEW_R*.md`，都是 CRLF），
   而同轮新增的 `binfmt/macho.py` / `tools/*.py` / `tests/*.py` 因为是在
   **已有文件**上改，被原有 CRLF 带着走，**没有**暴露这个坑 —— 只有**新建**
   文件才会踩到。`tools/check_all.py` 跑出来是 **rc=0**：**没有任何判据**看得见
   它，这正好**实证**了登记在案的 C16-14「**无门禁**管受控**源**文件的 LF 例外」。
   处置：`_r71/normalize_r71_doc.py`（仓库外、LF、两阶段）先断言当前确为纯 LF，
   再写回 CRLF，写后断言 `CR == LF`、`bare_lf == 0`。
   **教训**：仓库内**新建**文件之后，`bare_lf == 0` 这一步**必须自己查**；
   门不会替你查，因为**这一族例外至今没有门**。

---

## §8 下一次建设性意见（接在 R70 §7 之后）

| 编号 | 内容 | 动因（本轮读数） | 优先级 |
| --- | --- | --- | --- |
| **C20-1** | **签名 ⇄ 它实际发出的判据前缀**：给每道护栏一个「前缀集合」的机器可读声明，核 `ROW_SIGNATURE` 是否**恰好**等于它 | 本轮又添一例：C13 由三个子判据发出，签名写 `C1–C13` **正确**，但**没有任何门**能证明这一点 —— H1 只证明「描述含签名」，不证明「签名 == 实际前缀集合」（R70 §7 的原话：存在缺口 `V6`、`B6–B9`） | **最高** |
| **C20-2** | **探针自己两向自证**（C16-13）：每台探针加一个「必须红」的坏样本，`_rNN/verify_*` 先对「故意改一字节」的克隆断言**必须报不同** | 本轮**遵守了**（探针有 thin 对照 + 两个反向样本；`verify_remote_r71.py` 有 `NEGCTRL`），但**仍是人肉纪律**：没有任何装置要求下一轮的探针也这么做。可行的落点：把探针骨架做成 `tools/` 里的模板 + 一条「骨架必须含坏样本」的自检 | **最高** |
| **C21-1** | 把 `tools/check_all.py` 的 **ASCII 树**（「契约 C1..C1N」）纳入门管辖 | 它是**同一处**「只写不读」的散文：R70 只手工改过一次，本轮又是我手工改的；它现在写着 `C1..C13` 而**没有任何门看得见**（属 C20-1 同族，但更小、更容易先做） | **高** |
| **C18-3** | `DT_SONAME` 进 `provided` 集合（与 Mach-O 的 `LC_ID_DYLIB` 对称）；顺带读 `DT_FILTER` / `DT_AUXILIARY` | R68 §1.6 的**不对称**仍未修：文件名与 SONAME 不同族的库会被误报「未提供」 | 高 |
| **C18-4** | fat 上的 `@rpath` / `@loader_path` **候选名展开** | 本轮的 `@rpath/libonly1.dylib` 已经**读进依赖表**了，但没有任何一侧把它展开成候选文件 —— 归因仍停在「名字」这一层 | 高 |
| **C21-2** | C13 的期望表（`FAT_EXPECT_DEPS`）与夹具规格（`FAT_SLICE_SPECS`）目前靠**人肉同步**；可加一条纯函数判据：从 spec 反推期望并比对 | 本轮实测：漏写 `symtab=` 时门抓到了，但**漏写一条 `dep_cmds`** 时期望表也跟着不写的话就谁也看不出来 | 中 |
| **C19-3** | 「文档陈旧」类缺陷做成通检：`L5` 只盯了 `version` 徽章；同类还有 README 的 `--help` 体积数字、门表行数、测试条数 | 本轮又手改了两处（README 签名、check_all 树）—— 都是人肉 | 中 |
| **C18-8** | 轮次账本里的每个数字**都能重跑**：`_rNN/verify_*.py` 先写、再跑、然后才引 | 本轮**遵守**（`_r71/verify_remote_r71.py` 见 §5；探针见 §1） | 中 |
| **C18-5 / C18-6 / C18-7 / C18-9** | PE delay-load 导入表 / `LC_LAZY_LOAD_DYLIB` **有登记无夹具** / Windows 版本化命名（**先拿真实样本**）/ `.framework` 结构级解析 | R68 §8 的旧项，本轮未动 | 中 |
| **C16-2** | 「形态集合」做成登记制（py/js/c 形态 + 库名输入），加「表不许缩水」棘轮 | R68 §7-6 | 中 |
| **C16-6** | **B 类决策**（6 件产物：实现还是永久登记为「不做」）—— **要用户拍板** | 47 条永久红 | 待决策 |

**仍未完成的旧项**：C15-1…C15-8 · C13-4/C13-5/C13-7/C13-8 · C16-2/C16-3…C16-14 ·
C17-1/C17-2 · C18-1（**本轮完成**）/C18-4…C18-9 · C19-3/C19-4/C19-5 ·
C20-1（**R70 提出，仍未做**）/C20-2（**= C16-13，本轮遵守但未入装置**）/C20-3 ·
R44 §8 的 `C''''2` 与 `C''''4`。

---

## §9 明确拒绝做的事（避免下一轮走回头路）

1. **不为「让数字好看」而改判据**：C13 的存在理由是**真实 macOS 二进制大多是
   universal**，不是为了让某个计数从 0 走到 8。
2. **不把段名做成「只在 fat 上特殊」的字符串拼接**：剥前缀的实现只有一处
   （`gpu.section_base_name`），任何「fat 走一套、thin 走一套」的分叉都是下一轮的
   分叉源。
3. **不顺手实现 `fat_arch_64`**：没有真实样本，写了就是猜；本轮把它写成
   **显式披露的边界**（`0xCAFEBABF` 不认），而不是默默不认。
4. **不动 `mit` 正文 / `VERSION` / `flow/diagrams` / 行尾策略**；**不引新依赖**
   （离线、零依赖、3.6.5）：`_SliceView` 只用标准库的 `seek/read`。
5. **不放宽 `HELP_DRIFT_BYTES`**：帮助正文的改动是**等长**的，所以两处快照都没动。
6. **不把「读不懂的片」也算成解析成功**：一个片读不懂就是**没读**，必须在
   notes 里点名；「没产出」不等于「对了」（R68 起立的纪律）。

---

## 附 1：对**最终 HEAD** 的第二次真跑（同一脚本 `_r71/verify_remote_r71.py`）

本文档落盘后，对**最终 HEAD** 再跑一次 —— `89693f4` / tree `4e764118` /
`LS_TREE 255/255`（比主提交多 1 条，就是本文档）/ `SHA256 255/255 差异 0` /
clone `check_all`(3.13) rc=0 / clone `pytest -k r71` rc=0 / `NEGCTRL 必须不同=True` /
`REMOTE_VERIFY OK`。

所以 §5 那一段钉的是**主提交** `395a5c8`（254 条，它是最终 HEAD 的**祖先**），
本段钉的是**最终 HEAD**（255 条）—— 两段读数**都永远为真**，这正是「钉祖先哈希、
别钉当前 HEAD」的意义。⚠ 注意 `89693f4` 这个数字在本文件被**第三次**触碰（下面的
补记提交）之后也会变旧，所以它只被当作「当时跑过的那一次」记录，**不要**在任何
后续轮次里引用它当「当前 HEAD」。
