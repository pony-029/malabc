# R164 复盘：`except: pass` 藏了一个死缓存

> `_detect_dup_code` 的缓存写了、读了、也有 `try/except` 保护 —— 唯独从来没生效过。
> 它和 R162 的 `compliance.html` 是同一个模式：**`pass` 把「功能没生效」
> 伪装成「什么都没发生」**。

---

## §0 一句话结论

```python
cached = getattr(files, "_dup_code_cache", None)   # 永远是 None
...
try:
    files._dup_code_cache = out                    # 永远 AttributeError
except Exception:
    pass                                            # 永远被吞
```

`files` 是 **list**。**list 不能挂属性。** 三层都写对了，但因为第一层的
前提（能挂属性）是错的，整条缓存链是死的。

---

## §1 为什么之前没发现

| 路径 | `_detect_dup_code` 调用次数 |
| --- | --- |
| `analyze()`（我的 profile 一直跑这条） | **1 次** |
| **CLI `--json`**（真实用户走这条） | **2 次** |

我历次 profile 都是 `analyze('big_m')`，只看到一个调用点，
于是「缓存不命中」的症状被完美掩盖 —— **单次调用根本不需要缓存**。

**这是「用简化路径做 profile」的代价**：它便宜，但它看不见只在完整路径上出现的浪费。

---

## §2 修法：`is` 而不是 `id()`

```python
_DUP_CACHE = {"files": None, "result": None}

if _DUP_CACHE["files"] is files and _DUP_CACHE["result"] is not None:
    return _DUP_CACHE["result"]
```

| 方式 | 问题 |
| --- | --- |
| `id(files)` 做 key | 对象释放后 id 会被复用 ⇒ **可能返回别人的结果**（静默错） |
| **`is` 比较** | 不会误命中；代价是持有一份 list 引用 |

**「持有一份引用」在这里是可接受的**：一次 `run_pipeline` 只有一份 `files`，
进程退出即释放。**而 id 复用的错误是静默的、跨对象的** —— 那不可接受。

---

## §3 一条判断 `except: pass` 是否有毒的准则

> **它包住的那行，如果失败了，功能还完整吗？**

| 位置 | 失败后功能完整吗 | 有毒？ |
| --- | --- | --- |
| `files._dup_code_cache = out` | **不完整**（缓存永久失效） | **有毒** |
| `compliance.html` 的生成（R162） | **不完整**（整页消失） | **有毒** |
| `pickle.dump(cache)` | 完整（只是下次慢一点） | 无毒 |
| 逐文件解析的 `except`（少一条记录） | 完整（那条本来就不该产出） | 无毒 |

**这条准则比「所有 pass 都加日志」更实用** —— 后者会让正常运行时刷屏。

---

## §4 修完之后的新瓶颈

CLI 路径（1300 个 `.m`，17.2 秒）profile：

| 函数 | 累计 | 占比 |
| --- | --- | --- |
| `emit_outputs` | 12.93s | 75% |
| **`json.encoder._iterencode`** | **5.48s** | **32%** |
| `render_json` | 4.55s | 26% |
| `run_pipeline` | 3.95s | 23% |

`_detect_dup_code` 已跌出前 10。

**新瓶颈是 JSON 序列化** —— 1300 文件的全量 JSON，`indent=2` 逐层递归。
**这不是算法问题，是数据量 × 格式化开销。**

---

## §5 下一步

1. 量 `indent=None` 能省多少（**在探针之外的时间做**，它要跑分析）
2. 若省 ≥ 20%，加 `--json-compact` 开关（默认行为不变）
3. `_DUP_CACHE` 的并发前提要写进注释：LSP 多线程下靠 `_STATE["lock"]`
   串行化首次分析，所以目前安全
