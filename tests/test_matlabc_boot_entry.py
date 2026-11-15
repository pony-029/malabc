# -*- coding: utf-8 -*-
"""`matlabc_boot.py`：**子命令路由表**。

它自己不做任何事，只按参数决定把控制权交给谁。错法很安静：
`ask` 没被识别 → 掉进默认分析器 → 用户看到的是分析报告而不是答案，
而退出码仍是 0，看起来"跑成功了"。

所以判据逐条钉分流，并用**替身模块**（`sys.modules` 注入）验证：
不真的启动 GUI、不真的跑分析器，只验"交给了谁、转发了几参"。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _Stub(object):
    """假的子模块：记录 `main(argv)` 收到的参数，返回预设码。"""

    def __init__(self, name, ret=0):
        import types
        self.name = name
        self.ret = ret
        self.calls = []
        mod = types.ModuleType(name)

        def main(argv=None):
            self.calls.append(list(argv if argv is not None else []))
            return ret

        mod.main = main
        self.mod = mod


def _route(argv, stubs):
    """在注入替身的前提下跑 `matlabc_boot.main`，结束后还原 `sys.modules`。"""
    import matlabc_boot as B

    saved = {}
    for name, st in stubs.items():
        saved[name] = sys.modules.get(name)
        sys.modules[name] = st.mod
    try:
        return B.main(argv)
    finally:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


def test_ask_subcommand_routes_and_forwards_rest():
    """`ask …` → `matlabc_ask.main(其余参数)`，且返回值透传。"""
    st = _Stub("matlabc_ask", ret=7)
    rc = _route(["ask", "为什么形状不匹配"], {"matlabc_ask": st})
    assert rc == 7, "返回值没透传：%r" % (rc,)
    assert st.calls == [["为什么形状不匹配"]], \
        "参数没正确转发给 ask（应去掉子命令名）：%r" % (st.calls,)


def test_flow_subcommand_routes():
    """`flow …` → `matlabc_flow.main(其余参数)`。"""
    st = _Stub("matlabc_flow", ret=3)
    rc = _route(["flow", "--apply"], {"matlabc_flow": st})
    assert rc == 3 and st.calls == [["--apply"]], \
        "flow 分流不对：rc=%r calls=%r" % (rc, st.calls)


def test_no_args_opens_gui():
    """**无参数 = 双击** → 启动 GUI（传空列表）。"""
    st = _Stub("gui", ret=0)
    rc = _route([], {"gui": st})
    assert rc == 0 and st.calls == [[]], \
        "无参数没走 GUI：rc=%r calls=%r" % (rc, st.calls)


def test_selftest_goes_to_gui_with_flag():
    """`--selftest` → `gui.main(["--selftest"])`（CI 用的无界面自检）。"""
    st = _Stub("gui", ret=0)
    rc = _route(["--selftest"], {"gui": st})
    assert rc == 0 and st.calls == [["--selftest"]], \
        "--selftest 没走 GUI 自检：rc=%r calls=%r" % (rc, st.calls)


def test_other_args_fall_through_to_analyzer():
    """其余参数 → 命令行分析器，**原样**转发（不吞参数）。"""
    st = _Stub("matlabc", ret=5)
    rc = _route(["E:\\proj", "--json", "out.json"], {"matlabc": st})
    assert rc == 5, "返回值没透传：%r" % (rc,)
    assert st.calls == [["E:\\proj", "--json", "out.json"]], \
        "参数被改写/吞掉了：%r" % (st.calls,)
