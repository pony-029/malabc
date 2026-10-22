# -*- coding: utf-8 -*-
"""P0：`.mlcproj` + SQLite 项目符号库的单元判据。"""
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

import mlc_project  # noqa: E402


def _write(root, rel, text):
    path = os.path.join(root, rel.replace("/", os.sep))
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class TestMlcProject(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="mlc_test_")
        _write(self.root, "a.m", """function y = main(x)
y = helper(x) + 1;
end

function z = helper(x)
z = x * 2;
end
""")
        _write(self.root, "+pkg/Cls.m", """classdef Cls < handle
    properties
        value
    end
    methods
        function obj = Cls(v)
            obj.value = v;
        end
        function y = getValue(obj)
            y = obj.value;
        end
    end
end
""")
        _write(self.root, "sub/b.m", """function r = only()
r = 1;
end
""")
        _write(self.root, "build/ignored.m", """function x = nope()
x = 1;
end
""")
        mlc_project.init_project(self.root, name="demo")
        self.cfg = mlc_project.load_config(
            os.path.join(self.root, ".mlcproj"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _symbols(self):
        return mlc_project.query_symbols(self.cfg, limit=200)

    def _dotted(self):
        return set(r["dotted_name"] for r in self._symbols())

    def test_init_writes_config_and_db(self):
        self.assertTrue(os.path.isfile(os.path.join(self.root, ".mlcproj")))
        self.assertTrue(os.path.isfile(
            os.path.join(self.root, ".mlc", "project.db")))

    def test_init_refuses_overwrite(self):
        with self.assertRaises(ValueError):
            mlc_project.init_project(self.root, name="demo")

    def test_sync_indexes_symbols_and_excludes(self):
        s = mlc_project.sync_project(self.cfg)
        self.assertEqual(s["files"], 3)
        self.assertEqual(s["added"], 3)
        self.assertEqual(s["symbols"], 7)
        names = self._dotted()
        for want in ("main", "main.helper", "pkg.Cls", "pkg.Cls.value",
                     "pkg.Cls.Cls", "pkg.Cls.getValue", "only"):
            self.assertIn(want, names)
        self.assertNotIn("nope", names)

    def test_sync_is_idempotent(self):
        mlc_project.sync_project(self.cfg)
        s = mlc_project.sync_project(self.cfg)
        self.assertEqual(s["added"], 0)
        self.assertEqual(s["changed"], 0)
        self.assertEqual(s["removed"], 0)
        self.assertEqual(s["symbols"], 7)

    def test_incremental_change_and_delete(self):
        mlc_project.sync_project(self.cfg)
        _write(self.root, "a.m", """function y = main(x)
y = helper(x) + 1;
end

function z = helper(x)
z = x * 2;
end

function q = extra()
q = 3;
end
""")
        s = mlc_project.sync_project(self.cfg)
        self.assertEqual(s["changed"], 1)
        self.assertIn("main.extra", self._dotted())
        os.remove(os.path.join(self.root, "sub", "b.m"))
        s = mlc_project.sync_project(self.cfg)
        self.assertEqual(s["removed"], 1)
        self.assertNotIn("only", self._dotted())

    def test_dry_run_does_not_write(self):
        mlc_project.sync_project(self.cfg)
        _write(self.root, "dry.m", """function d = dry()
d = 1;
end
""")
        s = mlc_project.sync_project(self.cfg, dry_run=True)
        self.assertEqual(s["added"], 1)
        # 未提交，仍只有 3 个文件
        self.assertEqual(mlc_project.status_project(self.cfg)["files"], 3)
        s = mlc_project.sync_project(self.cfg)
        self.assertEqual(s["files"], 4)

    def test_at_class_directory(self):
        _write(self.root, "@Widget/get.m", """function v = get(obj)
v = 1;
end
""")
        mlc_project.sync_project(self.cfg)
        names = self._dotted()
        self.assertIn("Widget", names)
        self.assertIn("Widget.get", names)

    def test_import_siproj_text(self):
        _write(self.root, "src/x.m", """function x = x()
x = 1;
end
""")
        _write(self.root, "lib/y.m", """function y = y()
y = 2;
end
""")
        sip = os.path.join(self.root, "demo.siproj")
        _write(self.root, "demo.siproj", """; Source Insight project
File=src/x.m
File=lib
""")
        s = mlc_project.import_project(self.cfg, sip, write=True)
        self.assertGreaterEqual(s["resolved"], 2)
        cfg = mlc_project.load_config(os.path.join(self.root, ".mlcproj"))
        self.assertIn("src", cfg["source_dirs"])
        self.assertIn("lib", cfg["source_dirs"])
        mlc_project.sync_project(cfg)
        self.assertIn("x", self._dotted())
        self.assertIn("y", self._dotted())

    def test_import_master_file_list(self):
        _write(self.root, "src/x.m", """function x = x()
x = 1;
end
""")
        mfl = os.path.join(self.root, "files.mfl")
        _write(self.root, "files.mfl", """# master file list
src/x.m
""")
        s = mlc_project.import_project(self.cfg, mfl, write=False)
        self.assertFalse(s["written"])
        self.assertIn("src", s["source_dirs"])

    def test_import_rejects_binary(self):
        p = os.path.join(self.root, "bad.siproj")
        with open(p, "wb") as fh:
            fh.write(b"\x00\x01\x02")
        with self.assertRaises(ValueError):
            mlc_project.import_project(self.cfg, p, write=False)

    def test_status_reports_stale(self):
        mlc_project.sync_project(self.cfg)
        _write(self.root, "a.m", """function y = main(x)
y = 2;
end
""")
        s = mlc_project.status_project(self.cfg)
        self.assertGreaterEqual(s["stale"], 1)


if __name__ == "__main__":
    unittest.main()
