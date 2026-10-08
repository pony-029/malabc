# ANALYSIS 归档索引（malabc）

> 本目录归档「深度分析 / 审计 / 协同检查」类工作的结论。命名约定：
> `ANALYSIS_<YYYY-MM-DD>_<主题英文短名>.md`。
> 每篇至少含：①方法 ②结论先行 ③证据 ④缺口(P0/P1/P2) ⑤建设性改进意见。
> 依据：用户长期偏好 [88222452]（深度分析必须归档并维护索引）。

| 日期 | 主题 | 文件 | 结论摘要 |
| --- | --- | --- | --- |
| 2026-10-08 | **superpower 32 轮：帮助的人性化/图文并茂 + 「帮助不许说谎」装置化** | [SUPERPOWER_REVIEW_R32.md](../SUPERPOWER_REVIEW_R32.md) | 把「人性化」里唯一可判的部分翻译成装置。修 **2 处真缺陷**：① `python gui.py --help` 过去会走「启动 GUI」分支 —— rc=0 且**零输出**（问帮助得到沉默；单例守卫在前还会让它变成「第二个实例问帮助永远沉默」），改为在**任何副作用之前**返回一份图文帮助；② `python tools/check_all.py --help` 过去会真的跑完全套护栏（≈30s），现立即返回。**新增第 7 道护栏 `check_help_contract.py`**：R1 退出码登记必须在证据文件里有依据（含**反向**：源码里 `sys.exit(N)` 未登记即红）、R2 帮助声明的码集合必须**等于**登记表（少写红、多写也红）、R3 帮助骨架棘轮（示例 + 图示 + 退出码段）；`NO_EVIDENCE` 显式登记「由解释器给出的码」（如缺 tkinter → 1）。同时把 `check_doc_flags.py` 的覆盖面从 3 份 markdown 扩大到**6 个入口脚本的模块 docstring**（docstring 就是 `--help` 正文）——「文档说谎」有两条路径，只堵一条等于没堵。修正文档里写死的过期计数（5→7 道门）。**自我证伪一次**：新护栏首版 `_selftest` 把「条件成立」当成「判据抓到」，正反例整片颠倒，被它自己的 SELFTEST 抓出 —— 沉淀为纪律「测量工具自身的 bug 会伪造出被测对象的 bug，两向自证必须先跑通再宣布通过」 |
| 2026-10-08 | **superpower 31 轮：二进制/GPU 接入 + 子进程卫生（R1–R30）** | [SUPERPOWER_REVIEW_R31.md](../SUPERPOWER_REVIEW_R31.md) | 新增 `binfmt/` 包（PE/ELF/Mach-O + CUDA fatbin·cubin / AMD HSA code object / Vulkan SPIR-V）与 4 个 CLI 开关，把「源码侧有调用解析不出来」补成「这个名字归谁」（library / gpu_kernel / missing 三态）。修 **3 类真缺陷**：① 文档开关护栏因 `subprocess.run(capture_output=True)` **继承 stdin**、撞上 stdio MCP server 而等满 180s 内建超时（实测 **181s → 3.4s**，且我第一版因果结论被自己的重跑对照推翻）；② `check_all.py` 子进程**无 timeout**，一个不退出的护栏会让 CI 永远挂；③ `matlabc_mcp.py::_run` 的子进程继承 **MCP JSON-RPC stdin**（会偷协议字节）。全仓 AST 普查 52 个调用点、修 14 处，新增登记制护栏 `check_subprocess_hygiene.py`（含 `**kwargs` 静态盲区登记）。公平基线：HEAD **124 失败 / 274 通过 / 9 跳过** |
| 2026-10-08 | **二进制文件分析与本项目的链接（含 CUDA/AMD 算子）** | [ANALYSIS_2026-10-08_BINARY_GPU_INTEGRATION.md](ANALYSIS_2026-10-08_BINARY_GPU_INTEGRATION.md) | 六顶思考帽审计：全仓对二进制分析**零覆盖**（`\bELF\b`/`dlopen`/`cubin`/`fatbin`/`PTX`/`spirv` 全 0 命中；先前的 `.so`「117 处」是 `.sort` 类子串误报）。实测三家厂商的容器与魔数：**PE 段名 8 字节硬截断**（`.nv_fatbin`→`.nv_fatb`、`.hip_fatbin`→`.hip_fat`，只认完整拼写会在每个 Windows 二进制上报「零 GPU 内容」）；**cubin 不是标准 ELF**（`e_type=0x8000`、`e_shoff` 落 `0xCAFE…` 哨兵）；**CUDA kernel 名的真实来源是 cubin 的 `.text._Z…` 节名表**（实测 cuBLAS 171 / cuBLASLt 59 个，100% 可 demangle），而 **PTX 路径基本提不出名字**（347 个 `.entry ` 命中只剩 1–2 个真 entry）。确立「便宜判据 vs 严格判据分字段命名」「不可解析是一等状态」两条不变量 |
| 2026-10-08 | **superpower × 循环工程 30 轮修复（R1–R30）** | [SUPERPOWER_REVIEW_R30.md](../SUPERPOWER_REVIEW_R30.md) | 用「六帽 → C1–C10 → 逐条真落地 → 隔离探针 → 登记制护栏」闭环推进 30 轮：公平基线（同解释器、同测试集）**128 失败 / 278 通过 / 9 跳过** → 终态修复 11 项真缺陷（含 P0 补丁引擎「插入被实现成覆盖」致删源码、`collect_c_files(recursive=False)` 因 str↔Path 比较**恒返回空**、8 个跨语言安全算子「只在元表登记、无任何产出点」、未支持语言静默 0 结果、`--reproducible` 未兑现、补丁 hunk 多一个空上下文行致 `git apply` 必拒）；把 7 个幻影算子实装为真检测（各带正/负对照探针），第 8 个（`py_undefined_name`）显式登记为不实现并写明理由；新增 3 道可自证护栏 + 15 个回归测试 + 1 个一键总入口 |
| 2026-10-08 | **AI Agent 融合方向 / 六语言深度 / 动态库 / rea 融合**（superpower 六顶思考帽 × brainstorming） | [ANALYSIS_2026-10-08_MALABC_AI_FUSION_MULTILANG_DYLIB_REA.md](ANALYSIS_2026-10-08_MALABC_AI_FUSION_MULTILANG_DYLIB_REA.md) | 实测六语言前端真实深度：**C++/Rust 完全不可见（0 文件 0 函数）、TS 硬报错**，C/Py/JS 均为行锚定正则；**8 个「安全类」算子只在元数据表里、无实现**（含 `py_eval_usage`/`c_double_free`/`js_prototype_pollution`），且测试用手工伪造输入"通过"；**动态库与构建系统感知 0 命中**。对标 `morluto/rea`（27.8 万行 TS / 139 MCP 工具 / 工业级 dyld 解析）。选定路线 **D 先修地基 → B 前端外挂化（统一 IR）→ C rea MCP 联邦**，拒绝「原地正则扩语言」与「绑定 rea」 |
| 2026-10-08 | **仓库全量深度审计（克隆 + 实测取证）** | [ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT.md](ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT.md) | 「能力 5 分 / 工程 1.5 分」撕裂：引擎与 AI 闭环为真实现（无占位符），但**迁移不完整**——`fe_audit.py` 等 9 类产物缺失致 **129 测试失败 / CI 必红**；**P0 确定性补丁把「插入」写成「覆盖」→ 删语句且自证 PASS**；MCP `gen_patch` 参数错 + 失败报成功；`--reproducible` 未兑现；README 首命令实测报错 |
| 2026-10-08 | README 双语化与 banner 视觉修正 | [ANALYSIS_2026-10-08_MALABC_DOCS_BILINGUAL_BANNER.md](ANALYSIS_2026-10-08_MALABC_DOCS_BILINGUAL_BANNER.md) | 单文件中英混排→纯英/纯中双语；banner 去等距倾斜与 AI 水印（PIL 自绘水平正视）；修正 4 处 404 文档链接 |
| 2026-10-08 | malabc 与 AI Agent 深度融合（superpower×brainstorming） | [ANALYSIS_2026-10-08_MALABC_AI_AGENT_FUSION.md](ANALYSIS_2026-10-08_MALABC_AI_AGENT_FUSION.md) | 最大缺口=无标准协议暴露；落地 stdlib MCP server(matlabc_mcp.py) 让 agent 即插即用；附孤儿进程跑飞根因与进程树回收修复 |
| 2026-10-08 | malabc 演进治理（superpower×brainstorming） | [ANALYSIS_2026-10-08_MALABC_EVOLUTION_GOVERNANCE.md](ANALYSIS_2026-10-08_MALABC_EVOLUTION_GOVERNANCE.md) | 能力局部领先，差距在"工程化+生态"结构性缺失；Top 落地=启用自身 CI + 补 .gitignore + CONTRIBUTING |

## 使用约定

- 新增归档后，**在此表追加一行**（保持按日期倒序）。
- 涉及代码改动的可执行结论，请同步 PR 并在提交信息引用本归档文件名。
- 索引只列"已落地/已审计"的条目；规划中但未执行的内容勿入表，避免误导。
