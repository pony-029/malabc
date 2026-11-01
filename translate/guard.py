# -*- coding: utf-8 -*-
"""翻译过程的**硬护栏**：不让任何输入把机器拖死。

## 为什么需要（真实反馈）

有用户在其他机器上跑这个转换器时**经常卡死**。卡死只有两类原因：
1. **无界的计算**（嵌套降级/块深度记账写成了不收敛的循环、或正则灾难回溯）；
2. **资源无上限**（超大文件、超深嵌套、超多语句，把内存/CPU 吃满）。

代码里"会不会停"是很难靠读代码证明的，但**"到时间一定死"是可以证明的**。
所以这里采取最粗但最可靠的一招：**墙钟看门狗 + 几条硬上限**。

## 三条上限

| 上限 | 默认 | 触发时的行为 |
|---|---|---|
| 每次运行的墙钟时间 | 120 s | 打印原因后**立即退出**（`os._exit(3)`，绕开任何卡住的栈） |
| 单个 `.m` 文件大小 | 4 MiB | 跳过并报错（不读进来） |
| 单函数语句数 | 20000 | 该函数判 `reject:too_many_stmts` |

这三条都是**宁可少转一个函数，也不让整台机器失去响应**。
"""
import os
import sys
import threading

DEFAULT_MAX_SECONDS = 120
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_STMTS_PER_FUNC = 20000
MAX_BLOCK_DEPTH = 64

_fired = [False]


def _bail(seconds):
    if _fired[0]:
        return
    _fired[0] = True
    sys.stderr.write(
        "\n[guard] 超过 %d 秒仍未结束 —— 已强制退出。\n"
        "        可能原因：某个输入的嵌套/正则回溯把 CPU 占满。\n"
        "        请把该输入单独跑：python translate/mir.py <file.m> -o out.mir\n"
        "        如需更长时间：--max-seconds <秒>\n" % seconds)
    sys.stderr.flush()
    os._exit(3)          # 绕开任何可能卡在循环里的栈


def start(max_seconds=None):
    """启动看门狗（守护线程，到点强制退出）。返回实际的秒数。"""
    secs = int(max_seconds or os.environ.get("M2C_MAX_SECONDS")
               or DEFAULT_MAX_SECONDS)
    t = threading.Timer(secs, _bail, args=(secs,))
    t.daemon = True
    t.start()
    return secs


def file_too_big(path):
    """单个文件是否超过大小上限（不读内容）。"""
    try:
        return os.path.getsize(path) > MAX_FILE_BYTES
    except OSError:
        return False
