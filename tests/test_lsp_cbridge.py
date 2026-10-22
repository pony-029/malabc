# -*- coding: utf-8 -*-
"""C/MATLAB 双栏对照所依赖的 `matlabc/cbridge` 契约。

扩展只消费这个响应，不自己解析 C；所以这里钉住两件事：
  * 正向：MATLAB 函数里未解析的调用 -> C 文件 + 行号；
  * 反向：C 函数 -> 调用它的 MATLAB 函数。
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import lsp_selftest as L  # noqa: E402


class TestCBridge(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cbridge_")
        with io.open(os.path.join(self.root, "a.m"), "w",
                     encoding="utf-8", newline="") as fh:
            fh.write("function y = a(x)\ny = mycfun(x);\nend\n")
        with io.open(os.path.join(self.root, "mycfun.c"), "w",
                     encoding="utf-8", newline="") as fh:
            fh.write("double mycfun(double x) { return x + 1; }\n")
        self.client = L.Client()

    def tearDown(self):
        try:
            self.client.close()
        finally:
            shutil.rmtree(self.root, ignore_errors=True)

    def _ask(self, name, rid):
        self.client.send({"jsonrpc": "2.0", "id": rid,
                          "method": "matlabc/cbridge",
                          "params": {"name": name}})
        return (self.client.recv() or {}).get("result") or {}

    def test_forward_matlab_to_c(self):
        self.client.init(self.root)
        self.client.open(os.path.join(self.root, "a.m"))
        r = self._ask("a", 7)
        items = r.get("items") or []
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["callee"], "mycfun")
        self.assertEqual(items[0]["c_rel"], "mycfun.c")
        self.assertEqual(items[0]["c_line"], 1)

    def test_reverse_c_to_matlab(self):
        self.client.init(self.root)
        self.client.open(os.path.join(self.root, "a.m"))
        r = self._ask("mycfun", 8)
        self.assertEqual(r.get("mode"), "c-function")
        callers = r.get("matlab_callers") or []
        self.assertEqual(len(callers), 1)
        self.assertEqual(callers[0]["matlab"], "a")
        self.assertEqual(callers[0]["mfile"], "a.m")


if __name__ == "__main__":
    unittest.main()
