# 新增一条门：要动 7 处（实测定稿）

本仓为防止「门写了却没人跑 / 文档说了却对不上」，围绕 `tools/check_*.py` 建立了
一组互相咬合的约束。**加一条新门 = 改七处**，而且其中两处只有撞到才会知道。

> 这份清单是 R489（撤回）+ R490（完成）两次实测换来的。R489 只找到 6 处就变红，
> 于是整体撤回；R490 按这份清单**一次改完**，只剩两处语义细节要修。

## 七处

| # | 位置 | 要求 |
|---|---|---|
| 1 | `tools/check_<name>.py` | 门本体；必须有 `ROW_SIGNATURE`（形如 `XX1–XX2`） |
| 2 | `tools/release.py` 的 `GATES` | 登记进发版清单（否则发版不跑它） |
| 3 | `tools/check_help_contract.py` 的 `GUARD_CONTRACT` | 退出码契约；**描述里必须逐字含 `ROW_SIGNATURE`** |
| 4 | `README_CN.md` 质量门表 | 一行；**该行必须含签名**（P5 会核对） |
| 5 | `README.md` 质量门表 | 同上（两侧行数必须一致，P4 会核对） |
| 6 | `tools/check_all.py` 文档串里的 ASCII 树 | 一行 `├─▶ check_x.py  说明（契约 XX1..XX2）`；**漏行会红（H2e）** |
| 7 | 散文里的门数 | `CONTRIBUTING.md` / 两份 README / `matlabc_help.py` 里「N 道门」要同步 |

## 两处只有撞到才知道的细节

### H2b：判据前缀必须出现在**以它开头**的字符串字面量里

```python
# ❌ 静态门看不见：前缀是独立字面量 + 拼接
probs.append("%s %s" % ("GX1", why))

# ✅ 字面量本身以判据前缀开头
CHECKS = (("GX1", ..., "GX1 示例工程转出的 C 编译不过"),)
```

否则 `check_help_contract` 报「幽灵声明」：声明了 `GX1` 却在源码里发不出。

### H2e：`check_all.py` 的 ASCII 树也要补

树在 `tools/check_all.py` 的**模块 docstring** 里（不是 README）。行形如：

```
        ├─▶ check_generated_compiles.py  生成的 C 必须能编译 + 丢弃调用不退回 unmapped（契约 GX1..GX2）
```

注意签名用 `..`（两个点），不是 `–`。

## 一次做完的脚本骨架

```python
# 七处各一个 edit()，每处都用「已存在就不改」的幂等写法
edit("tools/release.py", g, "GATES 登记")
edit("tools/check_help_contract.py", hc, "GUARD_CONTRACT")
edit("README_CN.md", mk_row(cn=True), "质量门表")
edit("README.md", mk_row(cn=False), "质量门表")
edit("tools/check_all.py", tree, "ASCII 树")
for rel in ("CONTRIBUTING.md", "README.md", "README_CN.md", "matlabc_help.py"):
    edit(rel, count, "散文门数")
```

按顺序改、每步幂等，跑 `check_help_contract` / `check_readme_parity` / `check_release_gates`
三门即可定位剩余问题；全绿后再 `release.py --apply`。

## 已验证的一次完整实例

`tools/check_generated_compiles.py`（GX1–GX2，17 道发版门里的第 17 道）——
登记后 `check_help_contract: OK`、`check_readme_parity: OK`、17 道门全绿。
