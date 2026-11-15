# -*- coding: utf-8 -*-
"""`gui.py`（仓根）：表单 → 命令行的**映射**，以及路径 → `file://` URI。

这层坏了不会报错，只会"点按钮没反应"或"浏览器打开空白页"，很难从现象反推：

* `build_cli_args` 缺 `src` 必须**明确报错**，不能返回半成品参数
  （半成品会让 matlabc.py 在别处报一个无关的错）；
* `--json` 后面必须跟着报告路径，否则参数吞掉下一个选项；
* `--ai-mode off` 是默认 —— 不能悄悄联网；
* `config_to_form` 要把配置里的 **`dir` 映射成表单的 `src`**（键名不同！
  映射错了 GUI 会永远提示"请先选择工程目录"）；
* `pathlib_path_uri` 的空格必须编码成 `%20`，否则浏览器打不开带空格的路径。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FORM = {"src": r"E:\proj", "lang": "matlab", "out": r"E:\out",
        "json": True, "reproducible": True}


def test_build_cli_args_requires_src():
    """缺 `src` → `ValueError`，且消息说清是"工程目录"的问题。"""
    import pytest

    import gui as G

    with pytest.raises(ValueError) as ei:
        G.build_cli_args({"lang": "matlab"})
    assert "工程目录" in str(ei.value), \
        "报错没说清缺的是什么：%r" % (str(ei.value),)


def test_build_cli_args_core_flags():
    """`src` 必须是**第一个**参数；`--json` 后跟报告路径；默认 `--ai-mode off`。"""
    import gui as G

    args = G.build_cli_args(FORM)
    assert args[0] == FORM["src"], "第一个参数不是工程目录：%r" % (args[:2],)

    assert "--json" in args, "勾了 json 却没给 --json：%r" % (args,)
    i = args.index("--json")
    assert i + 1 < len(args) and args[i + 1].endswith(".json"), \
        "--json 后面没有跟报告路径（会吞掉下一个选项）：%r" % (args,)

    assert "--reproducible" in args, "勾了可复现却没传：%r" % (args,)
    assert "--ai-mode" in args and args[args.index("--ai-mode") + 1] == "off", \
        "默认没有关掉 AI（会悄悄联网）：%r" % (args,)
    assert "--lang" in args and args[args.index("--lang") + 1] == "matlab"


def test_config_to_form_maps_dir_to_src():
    """配置用 `dir`，表单用 `src` —— 映射错了 GUI 永远说"请先选择工程目录"。"""
    import gui as G

    form = G.config_to_form({"dir": r"E:\proj", "lang": "matlab"})
    assert form.get("src") == r"E:\proj", \
        "配置的 dir 没映射到表单的 src：%r" % (form,)
    for k in ("browse", "html", "json", "sarif", "reproducible", "lang"):
        assert k in form, "表单缺字段 %r（GUI 会 KeyError）：%r" % (k, sorted(form))


def test_path_uri_encodes_spaces():
    """路径 URI：`file:///` 前缀 + 空格编码成 `%20`。"""
    import gui as G

    uri = G.pathlib_path_uri(r"E:\temp\a b\c.html")
    assert uri.startswith("file:///"), "不是 file:/// URI：%r" % (uri,)
    assert "%20" in uri, "空格没编码（浏览器打不开带空格的路径）：%r" % (uri,)
    assert " " not in uri, "URI 里残留空格：%r" % (uri,)
