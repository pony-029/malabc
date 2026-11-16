# -*- coding: utf-8 -*-
"""规模语料的**烟测**：小样本（8 个算子 × 3 体量 = 24 个函数）跑通且 100% 完全实现。

## 为什么用"完全实现率"而不是"编译通过"

R878 实测：169 个生成文件**全部编译通过**，其中 **75 个含 `MLC_UNIMPLEMENTED`**
—— 桩函数照样编得过。所以编译率不能回答"翻译成功了吗"。

## 为什么是全量工具的小样本，而不是另写一套

`tools/gen_scale_corpus.py` 已经承载了四轮语料修正（函数名不当变量、
`% @m2c shape` 声明、二维形状、slice 边界）。这里只调它 `--limit 8`
—— **同一份生成逻辑**，否则门禁验的和全量跑的会是两套东西。

`--no-record` 是关键：小样本**不能**写 `flow/scale.json`（那会被首页
当成全量读数）。
"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "tools", "gen_scale_corpus.py")


def test_small_corpus_is_fully_implemented():
    """8 个算子 → 24 个 .c，且**一个 `UNIMPLEMENTED` 都没有**。"""
    assert os.path.isfile(TOOL), "缺 tools/gen_scale_corpus.py"
    scale_json = os.path.join(ROOT, "flow", "scale.json")
    before = io.open(scale_json, encoding="utf-8").read() if os.path.isfile(scale_json) else None

    r = subprocess.run([sys.executable, TOOL, "--limit", "8", "--no-record",
                        "--numeric"],
                       cwd=ROOT, stdin=subprocess.DEVNULL, timeout=600,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace")
    assert r.returncode == 0, "小样本转换失败：\n%s" % out[-800:]

    assert "生成 .c: 24" in out, "生成数量不对（8 算子 × 3 体量应为 24）：\n%s" % out[-400:]
    assert "完全实现 24 (100.0%)" in out, \
        "小样本不再是 100% 完全实现（翻译有退化）：\n%s" % out[-600:]

    # **两个后端必须算出同样的值**（R903）：只验"完全实现"会漏掉
    # "两边都实现了但结果不同" —— 那类错不会让任何单侧断言变红。
    # 小样本走这条只要 4 秒，值得每次都跑。
    assert "数值一致率 100.0%" in out, \
        "小样本的 VM ⇄ C 数值不再一致（或 --numeric 没跑起来）：\n%s" % out[-600:]

    # `--no-record` 必须真的不写全量读数文件
    after = io.open(scale_json, encoding="utf-8").read() if os.path.isfile(scale_json) else None
    assert before == after, \
        "小样本覆盖了 flow/scale.json（首页会把 24 个函数当全量读数）"
