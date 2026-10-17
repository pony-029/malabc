# R152 复盘：0 对 0 不算验证，所以给 F2 补了一条非空语料

> 上一轮我得出结论「`checks_for_sarif` 与 `--json` 的三类数字一致」，
> 依据是两边都是 0。**这个依据是无效的**——本轮补了分母，结论从
> 「必须做」变成「可以不做」。

---

## §0 一句话结论

F2 是**性能优化**，不是口径修复：

- 不做 F2 不会产出错数据（非空语料实测两边一致：1/1、1/1、0/0）
- 做 F2 省的是「62,704 个文件上再跑一遍 `_detect_*`」

顺带**又修正一处**：`_collect_checks` 里确实有 `shape_mismatch`（上一轮键名表写反了）。

---

## §1 那条无效的验证

第一次对比用的是 `tests/sample_m`：

```
uninitialized    checks=0    json=0
dead_code        checks=0    json=0
...
```

**0 对 0 只能说明「这个语料没有告警」，不能说明「两个来源口径相同」。**
两个都返回空列表的实现，在空语料上永远相等。

---

## §2 补分母：构造非空语料

```matlab
function y = x(a)
% 反例语料：b 未初始化就被读
y = a + b;
if false
    z = 1;
end
end
```

实测（`C:\temp\f2probe`）：

| key | checks | json | same |
| --- | --- | --- | --- |
| `uninitialized` | 1 | 1 | **YES** |
| `dead_code` | 1 | 1 | **YES** |
| `type_mismatch` | 0 | 0 | YES |
| `dup_code` | 0 | 0 | YES |
| `shape_mismatch` | 0 | 0 | YES |

**有非零项了**，所以「一致」这个结论才第一次有了证据。

---

## §3 定性变了，判据也变了

| | 原以为 | 实测后 |
| --- | --- | --- |
| F2 性质 | 修口径分裂（严重） | **性能优化**（可选） |
| 优先级 | 高 | **低于 P2（渲染外迁）** |
| 判据重点 | 让数字变对 | **改完一个数都不许变** |
| 风险 | 改错会产出错数据 | 改错会**破坏**已经一致的一致性 |

**最后一行是关键**：既然现在是对的，F2 唯一的失败模式就是「改坏它」。

---

## §4 第三处修正：`shape_mismatch` 一直在 `_collect_checks` 里

上一轮的键名对照表写：

> `shape_mismatch` | ❌（`_collect_checks` 没有） | ✅（`render_json` 独有） | **不能复用**

实测：

```python
sorted(checks) = ['dead_code', 'dup_code', 'shape_mismatch',
                  'suppressed', 'type_mismatch', 'uninitialized']
```

**它就在里面。** 所以三类**全部**可复用，`render_json` 里那三行遍历可以整段删掉。

---

## §5 F2 的最终形态

| # | 改动 | 行号 |
| --- | --- | --- |
| ① | `render_json` 加 `checks=None`，三个键优先读它 | L14229、L14295、L14300、L14310 |
| ② | `render_xml` 加 `checks=None` + 透传 | L19701、L19706 |
| ③ | `emit_outputs` 传 `checks_for_sarif` | L33248 |

**不碰 `run_pipeline`，不新增计算。**

---

## §6 状态

```
check_eol_convention  OK（324 个文本文件）
check_all             23/24（W2，探针 19:33:59 启动，已 14 分钟）
```

---

## §7 下一步

1. 探针收口（连续第五轮挂着）。
2. **P2 优先于 F2**：搬 `render_*` 的收益（4,327 行）大于省一次遍历。
3. 如果探针一直很慢，测一次 `--checks default` 与 `--checks all` 的产物是否字节相同
   —— 若相同，以后内核读数可以用 default 跑，长期省时间。
