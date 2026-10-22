# -*- coding: utf-8 -*-
"""R17/R18：workspace/symbol 与 didChange overlay 的单元判据。"""
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import matlabc_lsp  # noqa: E402
from analyzer.api import analyze  # noqa: E402


class TestWorkspaceSymbols(unittest.TestCase):
    def test_query_returns_class_method_property(self):
        root = tempfile.mkdtemp(prefix="lsp_sym_")
        try:
            matlabc_lsp._STATE["root"] = root
            fn = SimpleNamespace(name="main", kind="main", line=1,
                                 qualified="main", class_name=None)
            cls = SimpleNamespace(name="Cls", line=1,
                                  properties=[("value", 2)])
            method = SimpleNamespace(name="getValue", kind="method", line=3,
                                     qualified="Cls.getValue",
                                     class_name="Cls")
            mf = SimpleNamespace(rel="a.m", path=os.path.join(root, "a.m"),
                                 functions=[fn, method], classes=[cls])
            res = SimpleNamespace(files=[mf])
            got = matlabc_lsp._workspace_symbols("getval", res)
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0]["name"], "getValue")
            self.assertEqual(got[0]["kind"], matlabc_lsp._SYMBOL_METHOD)
            self.assertTrue(got[0]["location"]["uri"].endswith("/a.m"))
            got2 = matlabc_lsp._workspace_symbols("", res)
            names = set(x["name"] for x in got2)
            self.assertIn("main", names)
            self.assertIn("Cls", names)
            self.assertIn("value", names)
        finally:
            matlabc_lsp._STATE["root"] = None
            shutil.rmtree(root, ignore_errors=True)


class TestOverlay(unittest.TestCase):
    def test_unsaved_buffer_changes_symbols(self):
        root = tempfile.mkdtemp(prefix="lsp_overlay_")
        try:
            path = os.path.join(root, "a.m")
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write("function y = oldfn()\ny = 1;\nend\n")
            base = analyze(root)
            self.assertEqual([f.name for f in base.files[0].functions],
                             ["oldfn"])
            new = analyze(root, prev=base.files, changed={"a.m"},
                          overlay={"a.m": "function y = newfn()\ny = 2;\nend\n"})
            self.assertEqual([f.name for f in new.files[0].functions],
                             ["newfn"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestDidChange(unittest.TestCase):
    def test_debounced_overlay_updates_result(self):
        root = tempfile.mkdtemp(prefix="lsp_change_")
        path = os.path.join(root, "a.m")
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("function y = oldfn()\ny = 1;\nend\n")
        base = analyze(root)
        saved = dict(matlabc_lsp._STATE)
        try:
            matlabc_lsp._cancel_change_timer()
            matlabc_lsp._STATE.update({
                "root": root, "result": base,
                "payload": {"heuristics": []},
                "overlay": {}, "docs": {},
                "change_seq": 0, "change_timer": None,
            })
            uri = matlabc_lsp._path_to_uri(path)
            out = io.BytesIO()
            ok = matlabc_lsp.handle({
                "jsonrpc": "2.0",
                "method": "textDocument/didChange",
                "params": {
                    "textDocument": {"uri": uri},
                    "contentChanges": [{
                        "text": "function y = newfn()\ny = 2;\nend\n"
                    }],
                },
            }, out)
            self.assertTrue(ok)
            deadline = time.time() + 8.0
            names = []
            while time.time() < deadline:
                res = matlabc_lsp._STATE.get("result")
                if res is not None and res.files:
                    names = [f.name for f in res.files[0].functions]
                    if names == ["newfn"]:
                        break
                time.sleep(0.05)
            self.assertEqual(names, ["newfn"])
            deadline = time.time() + 3.0
            while time.time() < deadline and b"publishDiagnostics" not in out.getvalue():
                time.sleep(0.05)
            self.assertIn(b"publishDiagnostics", out.getvalue())
        finally:
            matlabc_lsp._cancel_change_timer()
            matlabc_lsp._STATE.clear()
            matlabc_lsp._STATE.update(saved)
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
