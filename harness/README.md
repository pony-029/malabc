# `harness/` —— **不是判据**，是追捕装置

`tools/` 里只有 `check_*.py`，而且有三道门在管那份清单（`check_all.py` 的
`MIN_GUARDS`、`check_help_contract.py` 的 G0b、`check_readme_parity.py` 的 P4/P5）。
把「不是门」的东西放进去，会让那三条判据在语义上说谎 —— 所以它们在这里。

| 文件 | 干什么 | 入库轮 |
| --- | --- | --- |
| `hunt_flaky_r102.py` | 追逃逸用例：同一条用例重复跑 + 可施加受控负载，报阈值余量 | R106（源自 R102） |
| `derive_candidates.py` | **推导**（不是人工挑）非确定候选：分级提名 P1/P2/P3 | R106（源自 R103） |
| `mutate_r103.py` | 对计划块 / 台账摘要做变异对照（注入即红、还原即绿） | R106（源自 R103） |
| `ensure_crlf.py` | 读 / 转仓内文件为 CRLF 并核账（`bareLF` 必须为 0） | R106（源自 R102） |
| `to_crlf_r105.py` | 转 CRLF 的**强判据**版：行尾之外逐字节相同 + 围栏奇偶配对不变 | R106（源自 R105） |

## 入库时改了什么（只有一处）

仓外的绝对路径换成了**仓内相对**，各**恰 1 处**：

```
REPO = r"E:\matlabc\malabc"                 ->  REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\matlabc\_r102")     ->  sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

其余**一个字符没动**（代码、注释、docstring 全部原样）。行尾一律 CRLF（仓内 blob 全 CRLF）。

## ⚠ 本目录的已知边界

* 这些脚本**不在**任何门里 —— 它们**不会**被 `tools/check_all.py` 跑到，
  也**不在** `GUARD_CONTRACT` 的登记里。这是**设计**（它们不是判据），
  但也意味着「它们坏了没人知道」⇒ 用之前先看它自己打出的读数。
* **还没入库的链**（下一轮的子项，依赖已查清）：
  `evolve_loop.py`（`REPO` / `LEDGER` 两个硬编码常量在 L37/L38）+
  `gen_plan_ledger_digest.py`（L25 的 `sys.path.insert`、L28 的 `REPO`）+
  **台账 `_r82/rounds.jsonl`**。台账入库会牵动 `docs/EVOLVE_ROADMAP_360.md` 的
  12 处散文引用与 `check_all.py` 的一句提示，必须单独一轮、单独验证。
