# -*- coding: utf-8 -*-
"""R432：MATLAB → C 移植链路（ABI / 适配器 / 算子 / 保真 / 台账）的单元判据。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

from translate import adapters, fidelity, mir, operators  # noqa: E402
import check_translate_port as gate  # noqa: E402


class TestAbi(unittest.TestCase):
    def test_header_contract(self):
        path = os.path.join(ROOT, "c_runtime", "include", "mlc.h")
        self.assertTrue(os.path.isfile(path))
        text = open(path, "r", encoding="utf-8").read()
        for tok in ("MLC_OK", "MLC_ERR", "MLC_UNIMPLEMENTED",
                    "mlc_array", "mlc_array_init", "mlc_array_free",
                    "mlc_array_view", "mlc_array_require", "owns_data"):
            self.assertIn(tok, text)
        self.assertEqual(gate.check_abi(path), [])

    def test_ops_header_exists(self):
        path = os.path.join(ROOT, "c_runtime", "include", "mlc_ops.h")
        self.assertTrue(os.path.isfile(path))
        text = open(path, "r", encoding="utf-8").read()
        for tok in ("mlc_op_add", "mlc_op_sum", "mlc_op_index",
                    "mlc_op_transpose", "mlc_op_matmul"):
            self.assertIn(tok, text)


class TestAdapters(unittest.TestCase):
    def test_adapter_match(self):
        m = [{"name": "mean", "n_args": 1, "dtype": "f64", "in_rank": 1}]
        c = [{"name": "mean", "n_args": 1, "dtype": "f64", "in_rank": 1}]
        res = adapters.match_specs(m, c)
        self.assertEqual(res["matched"], ["mean"])
        self.assertEqual(res["mismatched"], [])

    def test_adapter_arity_mismatch(self):
        m = [{"name": "mean", "n_args": 1}]
        c = [{"name": "mean", "n_args": 2}]
        res = adapters.match_specs(m, c)
        self.assertEqual(res["matched"], [])
        self.assertTrue(res["mismatched"])
        self.assertIn("ADP-1", res["mismatched"][0]["reasons"][0])

    def test_adapter_emit(self):
        spec = {"name": "mean", "n_args": 1, "dtype": "f64", "in_rank": 1}
        ms = adapters.matlab_adapter_source(spec)
        cs = adapters.c_adapter_source(spec)
        self.assertIn("nargin", ms)
        self.assertIn("error(", ms)
        self.assertIn("mlc_array_require", cs)
        self.assertIn("MLC_ERR", cs)

    def test_adapter_errors(self):
        spec = {"name": "mean", "n_args": 1}
        s = adapters.normalise_spec(spec)
        for key in ("arity", "dtype", "shape", "unimplemented"):
            self.assertIn(key, s["errors"])
        self.assertEqual(adapters.adapter_problems([spec]), [])


class TestOperators(unittest.TestCase):
    def test_every_sample_parses_to_itself(self):
        for op in operators.OPERATORS:
            u = operators.parse_line(op["sample"])
            self.assertIsNotNone(u, op["id"])
            self.assertEqual(u["operator"], op["id"])
        self.assertEqual(operators.operator_problems(), [])

    def test_index_is_zero_based_in_c(self):
        u = operators.parse_line("y = x(2);")
        src = operators.emit_c(u)
        self.assertIn("mlc_op_index(&x, 2, &y)", src)
        self.assertIn("if (st != MLC_OK)", src)

    def test_mul_and_matmul_are_distinct(self):
        u = operators.parse_line("y = A * B;")
        src = operators.emit_c(u)
        self.assertIn("mlc_op_matmul", src)
        v = operators.parse_line("y = A .* B;")
        self.assertIn("mlc_op_mul", operators.emit_c(v))
        self.assertNotIn("mlc_op_matmul", operators.emit_c(v))

    def test_unmapped_not_guessed(self):
        res = operators.to_operators("y = foo(a, b, c);\n")
        self.assertEqual(res["uses"], [])
        self.assertEqual(len(res["unmapped"]), 1)

    def test_min_is_not_max(self):
        # 回归：`min(x)` 以前被映射成 OP-MAX（同一归约），会静默算错。
        u = operators.parse_line("y = min(x);")
        self.assertEqual(u["operator"], "OP-MIN")

    def test_new_ops_emit(self):
        cases = (
            ("y = a - b;", "OP-SUB", "mlc_op_sub"),
            ("y = a .* b;", "OP-MUL", "mlc_op_mul"),
            ("y = a ./ b;", "OP-DIV", "mlc_op_div"),
            ("y = mean(x);", "OP-MEAN", "mlc_op_mean"),
            ("y = max(x);", "OP-MAX", "mlc_op_max"),
            ("y = min(x);", "OP-MIN", "mlc_op_min"),
        )
        for line, op, cname in cases:
            u = operators.parse_line(line)
            self.assertEqual(u["operator"], op)
            src = operators.emit_c(u)
            self.assertIn(cname, src)
            self.assertIn("if (st != MLC_OK)", src)

    def test_census(self):
        c = operators.operator_census()
        self.assertEqual(c["total"], len(operators.OPERATORS))
        self.assertEqual(c["verified"] + c["unverified"], c["total"])
        self.assertGreaterEqual(c["verified"], 9)


class TestFidelity(unittest.TestCase):
    def test_golden_all_pass(self):
        ok, rep = fidelity.self_test()
        self.assertTrue(ok, rep.get("failed"))
        self.assertGreaterEqual(rep["total"], 11)

    def test_detects_mismatch(self):
        tmp = tempfile.mkdtemp(prefix="mlc_fid_bad_")
        try:
            case = {
                "name": "bad", "operator": "OP-ADD", "rules": ["EXPAND-1"],
                "inputs": {"a": {"dtype": "f64", "shape": [1],
                                 "data": [1.0]},
                           "b": {"dtype": "f64", "shape": [1],
                                 "data": [1.0]}},
                "expected": {"dtype": "f64", "shape": [1], "data": [3.0]},
                "tol": {"abs": 1e-12, "rel": 1e-9},
            }
            with open(os.path.join(tmp, "bad.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(case, fh)
            rep = fidelity.run_all(golden_dir=tmp)
            self.assertEqual(rep["passed"], 0)
            self.assertEqual(len(rep["failed"]), 1)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_c_program_balanced(self):
        case = fidelity.load_case(os.path.join(
            operators.GOLDEN_DIR, "op_add_broadcast.json"))
        src = fidelity.emit_c_program(case)
        self.assertIn('#include "mlc.h"', src)
        self.assertEqual(src.count("{"), src.count("}"))


class TestSourceHandling(unittest.TestCase):
    def test_mir_keeps_source_line(self):
        text = mir.to_mir(
            "function y = f(x)\n% @m2c shape x 3\n"
            "% @m2c shape y 3\ny = x + x;\nend\n")[0]
        self.assertIn("# src:4", text)
        self.assertIn("op:OP-ADD:y:x:x", text)

    def test_lowered_binary_keeps_line_per_op(self):
        text = mir.to_mir(
            "function r = f(v)\n% @m2c shape v 3\n"
            "% @m2c shape r 3\nr = v + v(1);\nend\n")[0]
        self.assertEqual(text.count("# src:4"), 2)
        self.assertIn("op:OP-INDEX:", text)
        self.assertIn("op:OP-ADD:", text)

    def test_bom_source_is_read(self):
        tmp = tempfile.mkdtemp(prefix="mlc_bom_")
        try:
            src = os.path.join(tmp, "bom.m")
            out = os.path.join(tmp, "bom.mir")
            with open(src, "wb") as fh:
                fh.write(b"\xef\xbb\xbffunction y = bom()\ny = 1;\nend\n")
            self.assertEqual(mir.main([src, "-o", out]), 0)
            self.assertIn("func:bom", open(out, encoding="utf-8").read())
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dynamic_temp_has_no_preinit(self):
        exe = os.path.join(ROOT, "rust", "m2c", "target", "release",
                           "m2c.exe" if os.name == "nt" else "m2c")
        if not os.path.isfile(exe):
            self.skipTest("m2c not built")
        tmp = tempfile.mkdtemp(prefix="mlc_mask_")
        try:
            src = os.path.join(tmp, "mask.mir")
            with open(src, "w", encoding="utf-8", newline="") as fh:
                fh.write("version 3\nfunc:mask\narg:v:f64:3\nret:s:f64:1\n"
                         "op:OP-MASK:z:v:0:1\nop:OP-SUM:s:z\nend\n")
            out = os.path.join(tmp, "out")
            r = subprocess.run([exe, "build", "--mir", src, "--out", out,
                                "--name", "mk"], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout.decode("utf-8", "replace"))
            c = open(os.path.join(out, "src", "gen.c"), encoding="utf-8").read()
            self.assertIn("mlc_array z;", c)
            self.assertNotIn("mlc_array_init(&z", c)
            self.assertIn("mlc_op_mask_alloc(&v", c)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestLedger(unittest.TestCase):
    def test_real_ledger_clean(self):
        path = os.path.join(ROOT, "port_ledger.json")
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(gate.check_ledger(path), [])

    def test_bad_ledger_detected(self):
        tmp = tempfile.mkdtemp(prefix="mlc_ledger_bad_")
        try:
            p = os.path.join(tmp, "ledger.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "entries": [{
                    "id": "x", "matlab": "m", "c": "nope.c",
                    "status": "verified", "operators": ["OP-ADD"],
                    "golden": []}]}, fh)
            self.assertTrue(gate.check_ledger(p))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestGate(unittest.TestCase):
    def test_gate_clean(self):
        probs, stats = gate.run_checks()
        self.assertEqual(probs, [])
        self.assertGreaterEqual(stats["fidelity"]["total"], 5)

    def test_selftest_exit_zero(self):
        self.assertEqual(gate._selftest(), 0)

    def test_tp9_zero_pa1_is_not_pass(self):
        self.assertEqual(gate._parity_verified("PA1 已对拍 0\nPA2 未对拍 5"), 0)
        self.assertEqual(gate._parity_verified("PA1 已对拍 3\nPA2 未对拍 1"), 3)


if __name__ == "__main__":
    unittest.main()
