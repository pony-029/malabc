# R68 复盘：跨各种形式的动态链接库 —— Mach-O 的依赖 / 符号 / 库名家族归一

> 本轮指令：*「再次检查下增加下跨各种形式的动态链接库等，使用尽可能最严的标准来验证」*。
> 于是本轮不写新功能，先把一个问题问到底：**「一个动态库『我依赖谁』」这件事，
> 在各种容器里到底被读到了多少？** 答案比披露的少得多。

**一句话结论**：一个动态库表达「我依赖谁」有**三种机制** —— ELF 的 `DT_NEEDED`、
PE 的导入表、Mach-O 的 `LC_LOAD_DYLIB` 一族。**第三种是空的**（不是部分实现，是
一个字都没读）。而且三种机制之外还有一层：**同一个库有无数种写法**
（`libfoo.so` / `libfoo.so.1` / `libfoo.so.1.2.3` / `libfoo.1.dylib`），
旧实现把它们当成互不相干的库，于是报出「你还缺 `libfoo.so.1`」——
**在用户刚刚提供了 `libfoo.so.1.2.3` 的时候**。

| 项目 | 读数 |
| --- | --- |
| 装置（仓库外、只走公开 CLI） | `_r68/probe_r68_dylib_forms.py` v3，4 个用例 A–D |
| 基线（`git archive HEAD` 净树） | **`OK=0 BAD=3 INDETERMINATE=1`** |
| 修后（同一装置、同一台机器） | **`OK=4 BAD=0 INDETERMINATE=0`**（真树逐项相同） |
| 真缺陷 | **4 个**（Mach-O 依赖 / Mach-O 符号 / 库名家族 / `.framework` 死代码） |
| 判据 | C1–C9 → **C1–C12**（`tools/check_binfmt_fixtures.py`） |
| 新测试 | **5** 条，并由 **4 个变异体**证明「能红」 |
| 门禁 | `check_all.py` **rc=0**（16 个护栏全部通过且各自自证） |
| `--help` 体积 | 臂①② `50451` → **`50676`**；臂③ `42053` → **`42223`**（带宽 64 B **未动**） |

---

## §1 白帽：事实与读数

### 1.1 装置：先把「问什么」钉死

四问，**每一问都先断言前置条件**，前置不成立就报 `INDETERMINATE` 而不是 `OK`：

| 用例 | 问的是什么 | 判据 |
| --- | --- | --- |
| **A** | Mach-O 的 `LC_LOAD_DYLIB` 一族（含 `_WEAK_` / `_REEXPORT_` / `_UPWARD_`、`LC_ID_DYLIB`、`LC_RPATH`）读不读得出 | 7 条命令**逐条**名对得上 |
| **B** | Mach-O 的导出符号（`LC_SYMTAB` / `nlist_64`）读不读得出 | 导出 **> 0** 且**内部符号不许混入** |
| **C** | 提供了 `libfoo.so.1.2.3` 时，`libfoo.so.1` 还算不算「缺」 | `libfoo.so.1` **不在**未提供列表里，而真缺的 `libc.so.6` **必须在** |
| **D** | 同一个家族关系在 `.dylib` 写法上成不成立 | 同 C，但用 `libfoo.1.dylib` / `libfoo.1.2.3.dylib` |

**为什么 D 报 `INDETERMINATE` 而不是 `BAD`**：基线里 Mach-O 的依赖整块是空的，
`consumer deps=[]` ⇒ 「吸收生效了」与「根本没读到东西」这两种解释**同时成立**，
装置不许把「对象没产出」记成「对象对了」。这是 R66 C16-13「装置自己不许撒谎」
的直接继承 —— 而且本轮它真的救了一次（见 §5.1-2）。

### 1.2 基线读数（净树，公开 CLI）

```
[A] rc=0 dependencies=[]            ==> BAD    漏 7 / 7
[B] rc=0 symbols=[]                 ==> BAD    一个导出符号都没读出来
[C] 未提供列表 = ['libfoo.so.1', 'libc.so.6']
                                    ==> BAD    libfoo.so.1 仍被报成「未提供」
[D] consumer deps=[]                ==> INDET  前置不成立（Mach-O 依赖读不出来）
>>> OK=0 BAD=3 INDETERMINATE=1 （共 4）
```

三条 BAD 各自指向一个真缺陷，`INDET` 指向「C 与 D 是同一个家族规则的两面，
而一面压根不可判」。

### 1.3 修后读数（同一装置、同一台机器）

```
[A] OK  全部 7 条依赖被读出
[B] OK  导出符号被读出（2 条）
[C] OK  libfoo.so.1 被家族名吸收；真缺的 libc.so.6 照常提示
[D] OK  dylib 版本化形式被认成同一文件
>>> OK=4 BAD=0 INDETERMINATE=0 （共 4）
```

### 1.4 探针顺手量出的第 4 个缺陷：`.framework` 支路**不可达**

它不是计划里的一项。给 `library_family()` 的输入表加进
`@rpath/Foo.framework/Versions/A/Foo` 时读数是 `foo`，而**函数自己的文档字符串**
第 212–213 行明写应返回 `foo.framework`。根因是**语句顺序**：

```python
low = low.rsplit("/", 1)[-1]          # 先取 basename —— 得到 'foo'
if ".framework/" in low:              # 到这里 ".framework/" 早就不在串里了
    return low.split(".framework/", 1)[0] + ".framework"     # 恒不可达
```

| 输入 | 旧 | 新 |
| --- | --- | --- |
| `@rpath/Foo.framework/Versions/A/Foo` | `foo` | **`foo.framework`** |
| `Foo.framework/Foo` | `foo` | **`foo.framework`** |
| `/System/Library/Frameworks/Bar.framework/Bar` | `bar` | **`bar.framework`** |
| `@loader_path/../Frameworks/Baz.framework/Versions/Current/Baz` | `baz` | **`baz.framework`** |
| `Foo.framework`（无尾斜杠） | `foo.framework` | `foo.framework`（不变） |
| `libfoo.so.1` / `libfoo.1.dylib` | `libfoo.so` / `libfoo.dylib` | 不变（无回归） |

**行为与文档分叉**是这一轮的主题本身；而**这条路径上原本没有任何门**。

### 1.5 一个更基础的事实：`_canon_help` 的读数在本轮被再次确认

改 `matlabc.py` 的模块 docstring（= `--help` 正文）之后复量：

| 臂 | 口径 | 3.10 | 3.13 | 旧快照 | 新快照 |
| --- | --- | --- | --- | --- | --- |
| ①② | `COLUMNS=80` | `50706` | `50676` | `50451` | **`50676`** |
| ③ | `COLUMNS=10000` 规范形 | `42223` | `42223` | `42053` | **`42223`** |

两条臂的增量不同（+225 / +170）是**正常的**：臂①② 数的是折行后的字节，
臂③ 数的是把折行与缩进一并抹平之后的内容长度。**跨解释器差仍然是 30 B**
（arm ①②），说明它不是被测对象的字节数在飘，是 argparse 的行为差。

### 1.6 顺手读出来的**不对称**（本轮量到、**没有**修）

修完 Mach-O 的 `LC_ID_DYLIB` 之后，一个自然的问题是：**ELF 的对应物呢？**

```python
# binfmt/elf.py，DT_SONAME 分支（现状）
elif tag == DT_SONAME:
    nm = _cstr(f, str_off + val) if str_off is not None else ""
    if nm:
        rep.notes.append("ELF: SONAME=%s" % nm)      # 只进 notes（一个字符串）
# 而 DT_NEEDED / DT_RPATH / DT_RUNPATH 都变成 Dependency（结构化）
```

`DT_SONAME` 是 ELF 的「**我是谁**」（= Mach-O 的 `LC_ID_DYLIB`）。现在的状态是：

| 容器 | 「我是谁」 | 读到了吗 | 进 `missing_dependencies` 的 `provided` 集合吗 |
| --- | --- | --- | --- |
| Mach-O | `LC_ID_DYLIB` | 是（结构化 `Dependency`） | **是**（R68 加） |
| ELF | `DT_SONAME` | 是，但只进 `notes`（**字符串**） | **否** |

后果是一个**窄但真实**的缺口：把一个 SONAME 为 `libreal.so.1` 的文件放在
`weird-name.so` 这个名字下，消费者要 `libreal.so.1` 时仍会被报成「你没提供」，
**而那个文件就是它自己声称的那个库**。常见情形（文件名与 SONAME 同族）看不出差别，
所以这条一直没被量出来。

**本轮不修**：修它要动 `model.py`（新 kind）、`elf.py`（结构化）、`attribute.py`
（`provided` 集合）与 ELF 侧的夹具 —— 那是**独立的一轮**，已列为 §8 的 **C18-3**
（优先级升到最高，因为它是刚修完那件事的**镜像**）。


---

## §2 黑帽：这一版**不解决**什么（诚实列表）

1. **Mach-O 仍然没有真实语料**。本机找不到任何真实 `.dylib` / `.app` / `.framework`
   二进制（Windows 机器上的必然结果）。所有 Mach-O 结论都建立在**合成夹具**上，
   报告里仍然是 `verified: NO` —— 这一条的诚实措辞**一个字没动**，
   只是括号里补上了「现在读的东西更多了」。
2. **`LC_LAZY_LOAD_DYLIB` 有登记、无夹具**。它在 `DYLIB_LOAD_CMDS` 里、
   在常量表里有名字，但 C10 的八条命令实例里没有它 —— 也就是**未被真跑过**。
   （§6 的 C18-1 把它列出来。）
3. **fat Mach-O 只列切片，不逐片解析**。`flavour == "fat"` 与切片清单会被渲染，
   但依赖与符号**只在 thin 路径上读**。一个 universal binary 的依赖表今天看不见。
4. **`@rpath` 不做展开**。`@rpath/libbar.dylib` 被当作**名字**读出并按家族归一，
   但**不与 `LC_RPATH` 里的搜索路径拼**（拼了也只是候选名，不是磁盘事实）。
   `@loader_path` / `@executable_path` 同理。
5. **PE 的 delay-load 导入表仍未读**（C18-5，老账）。PE 的「我依赖谁」因此仍不完整。
6. **Windows 的版本化命名（`libfoo-1.2.dll`）刻意不猜** —— 需要真实样本才敢做。
7. **ELF 的「我是谁」与 Mach-O 不对称**（§1.6）：`DT_SONAME` 读到了但只进
   `notes`（字符串），没进 `provided` 集合；`DT_FILTER` / `DT_AUXILIARY`
   （「你替谁」）连常量都没有。本轮只**量到并如实记下**，修它留给 C18-3。
8. **`.framework` 只归一名，不解析结构** —— 不读 `Info.plist`、不读
   `Versions/Current` 符号链接。
9. **本轮没有跑 `-k` 之外的全量 pytest**。仓库存在 47 条**永久红**（K1–K9 已登记，
   与 R68 无关），本轮没有制造新的永久红，也没有减少它们。
10. **探针本身仍是「零自证」的**（C16-13 未完成）—— 本轮又在它身上踩了
    **两次**（§5.1-2 / §5.1-3）。变异体装置（§5.2）只覆盖 `tests/`，不覆盖探针。

---

## §3 落地物（全部真实现，无占位符）

### 3.1 产品（`binfmt/`，10 个文件的包）

| 文件 | 字节 | 行 | 本轮改了什么 |
| --- | --- | --- | --- |
| `binfmt/model.py` | 13,583 | 303 | 三种 Mach-O 依赖 kind：`load_dylib` / `id_dylib` / `load_dylinker`（**单列**，不与 ELF/PE 共用一个名字） |
| `binfmt/macho.py` | 19,621 | 448 | 七种依赖指令 + `LC_SYMTAB`/`nlist_64`；三个新的「内存内 NUL 串」读取器；三条命令的**头长度不同**（24 / 24 / 12 / 12） |
| `binfmt/buildsys.py` | 10,075 | 245 | `library_family()`：库名家族归一的**单一事实源**；`.framework` 支路的**顺序缺陷**（§1.4） |
| `binfmt/attribute.py` | 10,726 | 251 | `missing_dependencies()` 改用家族名判定；`LC_ID_DYLIB` 算「已提供」；`LC_RPATH`/`LC_RUNPATH`/`LC_LOAD_DYLINKER` 显式排除出「库」；macOS 前导下划线别名（**只对 macho 容器**、只去**一个** `_`） |
| `binfmt/__init__.py` | 3,810 | 66 | 新 kind 常量出口 |
| `matlabc.py` | 1,580,034 | 31,652 | **两处披露与行为分叉**已同步（`* Mach-O：` 的括号说明、`--binary` 的「能读什么」） |

### 3.2 判据（C10 / C11 / C12）

| 判据 | 管辖范围 | 为什么它**不可**与邻居重叠 |
| --- | --- | --- |
| **C10** | 合成 Mach-O 的**八条**依赖命令实例（**七种**指令 kind）：名字与 `kind` **都要**对；名字必须是**可打印 ASCII** | 它管「依赖表里有没有、对不对」，不管符号 |
| **C11** | `LC_SYMTAB`：`N_SECT\|N_EXT` → export、`N_UNDF\|N_EXT` → import、**内部符号必须一条都不出现** | 它管符号表，且正向反向各有一条（「必须在」与「必须不在」） |
| **C12** | `library_family()` 的同族归一 / 异族可分 / `.framework` 三种写法 + `missing_dependencies()` 的**两向**（被吸收的不出现、真缺的必须出现、rpath 不算库） | 它管**名字之间**的关系，不管名字本身读没读到 |

**ASCII 那一条不是装饰**：Mach-O 的名字读取器从**命令体**里取 NUL 结尾串，
偏移算错时会读出二进制垃圾 —— 而垃圾也是「有名字的依赖」，一样能通过
「名字对不对」的判据。可打印性把它挡在外面。

### 3.3 级联

| 文件 | 改了什么 |
| --- | --- |
| `tools/check_binfmt_fixtures.py` | 签名字符串 `C1–C9` → **`C1–C12`**；夹具构造器加 `dep_cmds` / `symtab`（两遍布局，偏移**回填**而不是猜）；3 好 + 3 坏自证样本；`--selftest` 下界 `4/4` → **`8/8`** |
| `tools/check_help_contract.py` | `GUARD_CONTRACT` 里那行描述**落后两轮**（还写着 `C1–C6`）→ `C1–C12`；帮助快照两处按**实测**更新；补 R68 复量注释 |
| `tools/check_boundary_reverse.py` | `BOUNDARY_EXEMPT["Mach-O："]` 的 `why` 补上 C10/C11 —— 这条豁免的**对手方**始终在同一个文件里 |
| `README.md` / `README_CN.md` | 门表那一行（同页两侧、逐字对等）：签名 + R68 三段说明 + `.framework` 缺陷 |
| `CONTRIBUTING.md` | 新增 R68 小节（含第 4 个缺陷、变异体证据、帮助快照表）；R56 那节补上 C10/C11 |
| `tests/test_matlabc.py` | **5** 条新测试（见 §5.2） |

---

## §4 验证矩阵（数字全部来自定稿之后的最后一次回归）

| 验证 | 命令 | 结果 |
| --- | --- | --- |
| 全门禁 | `python tools/check_all.py` | **rc=0** · `16 个护栏，全部通过且各自自证；门数下限 16` |
| 本门 | `python tools/check_binfmt_fixtures.py` | **rc=0** · 成功行含 `判据族 C1–C12` |
| 本门自证 | `... --selftest` | **rc=0** · `SELFTEST COUNTS {"bad": 8, "good": 8}` |
| 本门**两向** | 新版门放进 `git archive HEAD` 净树再跑 | **rc=1 · 14 项违规**（C10 ×8、C11 ×3、C12 ×3，逐条点名） |
| 主探针 | `_r68/probe_r68_dylib_forms.py` | `OK=4 BAD=0 INDETERMINATE=0 （共 4）` |
| 家族探针 | `_r68/probe_r68_family.py` | `bad=0 / 23` |
| 框架探针 | `_r68/probe_r68_framework.py` | 旧版 4/4 分叉；新版 `bad=0` |
| 新测试 | `pytest -k r68` | **5 passed**, 469 deselected |
| 新测试**两向** | `_r68/mutant_r68.py`（4 个变异体） | 4/4 **全红**，还原后 **绿** |
| 帮助棘轮 | `_r68/measure_help_r68.py` | 三臂全部在带内；五个脚本读数与快照一致 |
| 行尾 | 全部改动文件 | `bare_lf == 0` |
| 体量 | `git ls-tree -r` | **250** 条（新增 1 份文档后 **251**） |

---

## §5 轮次账本

### 5.1 本轮**自己**的伤（全部记录，不隐藏）

| # | 症状 | 根因 | 处置 |
| --- | --- | --- | --- |
| 1 | 补丁 A 的锚点 `count=0` | `model.py` 的 IR 图那几行缩进是 **6 个空格**，我按 4 个写 | 读回真实字节后按 6 空格重写；**锚点唯一性先验后写**的纪律救了一次（没有半途写盘） |
| 2 | 探针 v1 报**假 OK** | 我合成的 ELF 少了 `DT_STRTAB` ⇒ `DT_NEEDED` 的名字根本读不出来，而「读不出来」被当成了「没有未提供的依赖」 | v2 补全 `.dynamic`/`.dynstr`/`DT_STRTAB`/`DT_STRSZ` 布局，**并给每个用例加前置断言**：前置不成立 ⇒ `INDETERMINATE`，永不算 `OK` |
| 3 | 探针 v2 报**假 BAD** | `missing_block()` 在整段输出里做**子串**搜索，而「来源列」里正好含 `libfoo.so.1.2.3`（它含子串 `libfoo.so.1`） | v3 改成**结构化**解析：只取每行 `<-` 之前的那一段，遇到下一节标题就停 |
| 4 | 探针 v1/v2 报**假 BAD**（另一处） | `symoff` 算成了「`LC_SYMTAB` 命令**自身**的位置」（短 24 字节）⇒ 解析器把命令字节当符号读 | v3 两遍布局：先放 24 字节占位命令，再回填 `symoff`/`stroff` |
| 5 | 两向证据第一版是 `ImportError` traceback | 新门跑 R68 之前的树时，`from binfmt.buildsys import library_family` 直接抛异常 ⇒ rc=1 但**没说出哪条判据红了** | 给 C12 的两处 import 加 try/except，缺符号时给一条**能读的** finding。**「非 0 退出」不等于「判据生效」** |
| 6 | N1 门当场逮住我写的「第 15 道门」 | 我把历史**序数**当成了「数量」的表述，而 N1 按数量读 | **去掉序数**（不是改成 16 —— 那会变成一句关于**顺序**的假话）。序数在这里本来不承载信息 |
| 7 | 家族探针报**假 BAD** | 我把 `libfoo.so` 与 `libfoo.1.dylib` 放进同一个「同族」集合 —— 那是**我的期望写错了**（前者是 ELF、后者是 Mach-O） | 修正期望，并把「跨容器不许合并」变成探针的**一条独立断言**。**探针的期望也必须被量过** |

> 7 次里 **4 次是探针自己**。R66 立了 C16-13「让探针两向自证」，两轮过去它仍是
> 最薄的一环 —— 本轮把**测试**那一侧的缺口补了（§5.2），**探针**那一侧还没补。

### 5.2 新测试凭什么可信：4 个变异体全部把它打红

新写的 5 条测试**第一次就全绿**是可疑的。`_r68/mutant_r68.py` 把整棵工作区
复制到 `_r68/mut`（30 MB，**不动真树**），注入 4 个变异体：

| 变异体 | 内容 | 实测 |
| --- | --- | --- |
| V1 | `macho.py`：`DYLIB_LOAD_CMDS` 删掉 `LC_LOAD_WEAK_DYLIB` | **2 failed** |
| V2 | `macho.py`：`_read_symtab` 不再要求 `N_EXT` | **2 failed** |
| V3 | `buildsys.py`：`.framework` 判断挪回 basename **之后** | **3 failed** |
| V4 | `buildsys.py`：`library_family` 退化成「只取小写 basename」 | **3 failed** |
| — | 还原 | **5 passed** |

一句话：**「测试通过」不是证据，「测试能红」才是。**

### 5.3 交接：R67 的收尾

进入本轮时，工作区里躺着**另一个会话**在做 R67。处置是：先做只读分析与仓库外
编写，两次（间隔 25–45 s）确认没有活跃写入者之后，用 `git archive HEAD` 建净树
隔离，**连一次门都没在白树上跑**。R67 落地后我提交为 `8a12cff`，随后 `--amend`
成 **`eb8e2f9`**，把 R67 文档里那处**未执行的远端声明**（`REMOTE_VERIFY OK` / `251 条`，
而脚本从未存在、真树是 **250** 条）改成如实的「⚠ 未执行」。

---

## §6 探针与补丁清单（`E:\matlabc\_r68\`，仓库外，LF）

| 工具 | 作用 |
| --- | --- |
| `probe_r68_dylib_forms.py` | v3 主探针（4 用例 / 前置断言 / 结构化解析） |
| `probe_r68_family.py` | `library_family()` 的 20+ 输入逐条读数（**假 BAD 就是它报的**） |
| `probe_r68_framework.py` | 把「`.framework` 那支还能不能为真」单独量出来（**静态判不了顺序，这样能**） |
| `mutant_r68.py` | 4 个变异体 × 整棵工作区副本 ⇒ 证明新测试能红 |
| `measure_help_r68.py` | 按门内**钉死口径**复量 5 个脚本的两条臂读数 |
| `patch_r68a…n.py` | 14 个补丁脚本（A–N），每个都是**全锚点先验后写**、`ast.parse` + `bare_lf==0` 自检 |
| `check_anchors_r68.py` | 只读锚点预检器 |

---

## §7 盲区（诚实列表）

1. **Mach-O 无真实语料** —— 全部结论建立在合成夹具上（§2-1）。
2. **`LC_LAZY_LOAD_DYLIB` 有登记、无夹具**（§2-2）。
3. **`@rpath` 不展开**（§2-4）。
4. **fat 不逐片解析**（§2-3）。
5. **探针零自证**（§2-10）—— 本轮又踩两次。
6. **`library_family` 的输入集合是「我挑的 23 个」** —— 与 C16-2 同病：
   集合本身没有对手方。它能证明「这些输入归一对了」，**不能**证明
   「真实世界里常见的写法都覆盖了」。
7. **`.framework` 只归一名**（§2-8）。
8. **`check_help_contract` 的 `GUARD_CONTRACT` 描述文本仍然没有门管** ——
   本轮它落后两轮是我**手工发现**的。新测试钉住了**本门这一行**，
   但没有一条门做「全部 17 个护栏的描述文本 ⇄ 各自签名」的通检（C18-2）。

---

## §8 下一次建设性意见（接在 R67 §8 之后）

| 编号 | 内容 | 动因（本轮的读数） | 优先级 |
| --- | --- | --- | --- |
| **C18-1** | 给 **fat Mach-O 逐片解析**：现在只列切片清单，依赖与符号只在 thin 路径读 —— 而真实 macOS 二进制**大多是 universal** | §2-3 · §1.2 的 D 用例正是被「依赖读不出来」卡住的 | **最高** |
| **C18-2** | 把 `GUARD_CONTRACT` 的**描述文本**纳入门管辖：通检「17 个护栏的描述里的签名 ⇄ 各自 `ROW_SIGNATURE`」 | §3.3 —— 本轮发现它**落后两轮**（写着 `C1–C6`）且**无人管**；我只手工钉住了本门一行 | **最高** |
| **C16-13** | 让**探针自己两向自证**（R66 立、R67 重申、**R68 又踩两次**） | §5.1 —— 7 次自伤里 4 次是探针 | **最高** |
| **C18-3** | 修掉 §1.6 量出的**不对称**：`DT_SONAME` 变成结构化的「我是谁」并进 `provided` 集合（= ELF 侧的 `LC_ID_DYLIB`）；顺带读 `DT_FILTER` / `DT_AUXILIARY`（「你替谁」） | §1.6 —— 刚给 Mach-O 修完同一件事，ELF 侧还空着；缺口窄但真实 | **最高** |
| **C18-4** | `@rpath` / `@loader_path` / `@executable_path` 的**候选名展开**（与 `LC_RPATH` 列表拼接），并显式披露「这是候选名，不是磁盘事实」 | §2-4 | 高 |
| **C18-5** | PE 的 **delay-load 导入表**（老账，跨了 R31/R33/R68 三轮） | §2-5 | 高 |
| **C18-6** | 给 `LC_LAZY_LOAD_DYLIB` 补一条夹具（**有登记、无夹具**的东西就是没被试过） | §2-2 —— C10 的八条命令里没有它 | 中 |
| **C16-2** | 把「**形态集合**」本身变成**登记制**（py / js / c **以及本轮的 23 个库名输入**），加「表不许缩水」棘轮 | §7-6 —— 「我挑的 23 个」没有对手方 | 高 |
| **C18-7** | Windows DLL 版本化命名（`libfoo-1.2.dll` / `-v1` / `_1`）—— **先拿真实样本再动手**，不许猜 | §2-6 —— 现有实现刻意不猜，这是对的 | 中 |
| **C18-8** | 「轮次账本里的每个数字都要能重跑」：把每轮的读数脚本固定成 `_rNN/verify_*.py` 并**确认它真的存在** | §5.3 —— R67 的文档声称跑过一个**从未存在**的脚本 | 中 |
| **C18-9** | `.framework` 的结构级解析（`Versions/Current` + `Info.plist`），或**逐字披露「只归一名」** | §2-8 | 低 |
| **C16-9** | 「三类读数（基线 / 中间态 / 复量）必须在**文件名**里分开」写成探针目录 `README` 并由门核对命名 | R66 真踩过；本轮用 `measure_before_F.txt` / `measure_after_G.txt` 自觉遵守了 | 中 |
| **C16-12** | 探针目录**收尾**纪律：`_r62/wt_head` 那个遗留 worktree **还在**（本轮仍未单方面强删） | §6 | 低 |
| **C16-6** | **B 类决策**（6 件产物实现还是永久登记为「不做」）—— **要用户拍板** | 47 条永久红 | 待决策 |

**仍未完成的旧项**：C15-1 / C15-2 / C15-3 / C15-4 / C15-5 / C15-6 · C14-11 / C15-8 ·
C13-4 / C13-5 / C13-7 / C13-8 · C16-3 / C16-4 / C16-5 / C16-7 / C16-8 / C16-10 /
C16-11 / C16-14 · C17-1 / C17-2 · R44 §8 的 `C''''2` 与 `C''''4`。

---

## §9 明确拒绝做的事（避免下一轮走回头路）

1. **不为「让读数好看」而改探针用例**：C 与 D 的判据来自**真实工程语义**
   （同一个库的两种写法），不是为了让数字落位。
2. **不为了 `INDETERMINATE` 好看而放宽前置断言** —— 那个状态是本轮最有用的发明。
3. **不猜 Windows 版本化命名**（§2-6）：没有真实样本的归一规则会把两个不同的库
   合并成一个 —— 那比漏报危险得多。
4. **不动 `VERSION`**（`1.16.72` 是源码常量）· **不动 `flow/diagrams`** ·
   **不引新依赖**（坚持离线、零依赖、3.6.5）· **不动行尾策略**（全 CRLF、`* -text`）。
5. **不放宽 `HELP_DRIFT_BYTES`**：改披露只能更新快照，不能调带宽。
6. **不动别人门的签名**：本轮 C 族（`C1–C12`）与 `check_c_frontend_shapes.py` 的
   `F1–F6`、`check_import_graph.py` 的 `G1–G7` 互不重叠 —— 这是**先核过命名空间**
   才选的族名（R67 被 P5 抓过一次撞车）。
7. **不把 `.framework` 修法顺手推广成「路径语义解析」**：本轮只修**顺序缺陷**，
   结构级解析留给 C18-9。
