"""Tests for the witness kinds of bemyself.msheet (05-02 §4, 05-07 §4/§6).

Witnesses decide claims and hypotheses: auto compiles the target formula,
py runs a model-written expression (sandboxed subprocess), range is an
explicit finite forall, ref promotes a confirmed line, sim compares
checkpoints against a reference simulation, cyc checks a translation-cycle
certificate through the existing [CYCLE] machinery. The doctrine: CONFIRMED
only on the exact check -- a guard violation, a timeout or an unparsable
target is UNVERIFIABLE, never a silent approximation.
"""

import shutil
import unittest

from bemyself import turing
from bemyself.model import Verdict
from bemyself.msheet import witnesses

WIKI_CYCLER = "1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC"  # certificate (6, 16, 2)
SMALL_HALTER = "1RB1RZ_0LA0LA"  # halts after exactly 3 steps, score 1
BB5_CHAMPION = "1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA"


def ctx(**over):
    base = dict(
        defs={},
        machines={},
        status_of=lambda _id: None,
        last_v=lambda _id: None,
        sandbox="off",
        timeout=10.0,
    )
    base.update(over)
    return witnesses.WitnessContext(**base)


def run(text, target_body, **over):
    spec = witnesses.parse_witness(text)
    return witnesses.execute(spec, target_body, ctx(**over))


class ParseTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(witnesses.parse_witness("auto").kind, "auto")
        py = witnesses.parse_witness("py: st(27)==111")
        self.assertEqual(py.kind, "py")
        self.assertEqual(py.parts["expr"], "st(27)==111")
        rng = witnesses.parse_witness("range n in 1..10: (n < 11)")
        self.assertEqual(rng.kind, "range")
        self.assertEqual(rng.parts["var"], "n")
        self.assertEqual(rng.parts["low"], "1")
        self.assertEqual(rng.parts["high"], "10")
        self.assertEqual(rng.parts["body"], "(n < 11)")
        ref = witnesses.parse_witness("ref h1")
        self.assertEqual(ref.kind, "ref")
        self.assertEqual(ref.parts["id"], "h1")
        sim = witnesses.parse_witness("sim(0..100)")
        self.assertEqual(sim.kind, "sim")
        self.assertEqual(sim.parts["low"], "0")
        self.assertEqual(sim.parts["high"], "100")
        cyc = witnesses.parse_witness("cyc(6,16,2)")
        self.assertEqual(cyc.kind, "cyc")
        self.assertEqual(cyc.parts["t1"], "6")
        self.assertEqual(cyc.parts["t2"], "16")
        self.assertEqual(cyc.parts["d"], "2")

    def test_invalid_texts(self):
        for text in ("", "automatic", "py", "ref", "sim(", "cyc(1,2)", "cyc(a,b,c)", "range n 1..10: (n < 11)"):
            with self.assertRaises(witnesses.WitnessError, msg=text):
                witnesses.parse_witness(text)


class AutoTest(unittest.TestCase):
    def test_confirmed_and_refuted(self):
        result = run("auto", "((2 + 2) = 4)")
        self.assertEqual(result.verdict, Verdict.CONFIRMED)
        result = run("auto", "((2 + 2) = 5)")
        self.assertEqual(result.verdict, Verdict.REFUTED)

    def test_unparsable_target(self):
        result = run("auto", "M zyklisch (Translation)")
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("formula", result.reason)

    def test_non_bool_target(self):
        result = run("auto", "(2 + 2)")
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)

    def test_empty_range(self):
        result = run("auto", "(forall n in 1..0: (n > 0))")
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("empty_range", result.reason)

    def test_guard(self):
        result = run("auto", "(ip(((10 ^ 12) + 1)) = 0)")
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("guard", result.reason)

    def test_library_claim(self):
        self.assertEqual(run("auto", "(st(27) = 111)").verdict, Verdict.CONFIRMED)
        self.assertEqual(run("auto", "(st(27) = 110)").verdict, Verdict.REFUTED)

    def test_defs_are_available(self):
        from bemyself.msheet.formula import parse_def

        defs = {"sum_1_to_n": parse_def("def sum_1_to_n(n) = sum(k=1..n, k)")}
        result = run("auto", "(sum_1_to_n(10) = 55)", defs=defs)
        self.assertEqual(result.verdict, Verdict.CONFIRMED)


class PyTest(unittest.TestCase):
    def test_confirmed_and_refuted(self):
        self.assertEqual(run("py: st(27)==111", "x").verdict, Verdict.CONFIRMED)
        self.assertEqual(run("py: st(27)==110", "x").verdict, Verdict.REFUTED)

    def test_non_bool_and_exception(self):
        result = run("py: 2 + 2", "x")
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("not a bool", result.reason)
        result = run("py: 1/0", "x")
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("ZeroDivisionError", result.reason)

    def test_timeout(self):
        result = run("py: sum(range(10**10))", "x", timeout=0.4)
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("timeout", result.reason)

    @unittest.skipUnless(shutil.which("bwrap"), "bwrap not available")
    def test_sandboxed_run(self):
        result = run('py: __import__("os").getcwd', "x", sandbox="require")
        # The import is available in the eval namespace only if it leaks in;
        # os is not part of the library, so this must fail as unverifiable.
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        ok = run("py: 2 + 2 == 4", "x", sandbox="require")
        self.assertEqual(ok.verdict, Verdict.CONFIRMED)
        self.assertTrue(ok.sandboxed)

    def test_require_without_bwrap(self):
        from unittest import mock

        with mock.patch.object(witnesses, "find_bwrap", return_value=None):
            result = witnesses.execute(
                witnesses.parse_witness("py: 2 + 2 == 4"),
                "x",
                ctx(sandbox="require"),
            )
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("bwrap", result.reason)


class RangeTest(unittest.TestCase):
    def test_confirmed_and_refuted(self):
        self.assertEqual(run("range n in 1..10: (n < 11)", "x").verdict, Verdict.CONFIRMED)
        self.assertEqual(run("range n in 1..10: (n < 10)", "x").verdict, Verdict.REFUTED)

    def test_empty_range(self):
        result = run("range n in 5..4: (n > 0)", "x")
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("empty_range", result.reason)


class RefTest(unittest.TestCase):
    def test_confirmed_only_with_plus_and_ok(self):
        result = run(
            "ref h1",
            "x",
            status_of=lambda _id: "+",
            last_v=lambda _id: Verdict.CONFIRMED,
        )
        self.assertEqual(result.verdict, Verdict.CONFIRMED)

    def test_without_plus_status(self):
        result = run("ref h1", "x", last_v=lambda _id: Verdict.CONFIRMED)
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("ref_unconfirmed", result.reason)

    def test_without_ok_verdict(self):
        result = run("ref h1", "x", status_of=lambda _id: "+", last_v=lambda _id: Verdict.REFUTED)
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("ref_unconfirmed", result.reason)

    def test_unknown_target(self):
        result = run(
            "ref h9",
            "x",
            status_of=lambda i: "+" if i == "h1" else None,
            last_v=lambda i: Verdict.CONFIRMED if i == "h1" else None,
        )
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)


class SimTest(unittest.TestCase):
    def machines(self):
        return {"M": turing.parse(SMALL_HALTER)}

    def test_confirmed_checkpoints(self):
        result = run("sim(0..2)", "cp 1: (B,1,1)", machines=self.machines())
        self.assertEqual(result.verdict, Verdict.CONFIRMED)
        result = run("sim(0..2)", "cp 1: (B,1,1)\ncp 2: (A,0,1)", machines=self.machines())
        self.assertEqual(result.verdict, Verdict.CONFIRMED)

    def test_refuted_on_wrong_state_head_or_tape(self):
        for body in ("cp 1: (A,1,1)", "cp 1: (B,2,1)", "cp 1: (B,1,11)"):
            result = run("sim(0..2)", body, machines=self.machines())
            self.assertEqual(result.verdict, Verdict.REFUTED, body)

    def test_trailing_zero_cell_is_value_equal(self):
        # The pilot smoke of 2026-09-12: models count a written zero cell at
        # the end of the window; the tape value is identical.
        result = run("sim(0..2)", "cp 1: (B,1,10)", machines=self.machines())
        self.assertEqual(result.verdict, Verdict.CONFIRMED)

    def test_checkpoint_outside_segment(self):
        result = run("sim(0..1)", "cp 2: (A,0,1)", machines=self.machines())
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("segment", result.reason)

    def test_target_without_checkpoint(self):
        result = run("sim(0..2)", "M haltet nach 3 Schritten", machines=self.machines())
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)

    def test_no_machine(self):
        result = run("sim(0..2)", "cp 1: (B,1,1)")
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("machine", result.reason)

    def test_bb5_champion_checkpoints(self):
        machines = {"M": turing.parse(BB5_CHAMPION)}
        result = run("sim(0..10)", "cp 5: (C,1,1111)", machines=machines)
        self.assertEqual(result.verdict, Verdict.CONFIRMED)
        result = run("sim(0..10)", "cp 10: (D,2,11111)", machines=machines)
        self.assertEqual(result.verdict, Verdict.CONFIRMED)


class CycTest(unittest.TestCase):
    def machines(self):
        return {"M": turing.parse(WIKI_CYCLER)}

    def test_confirmed_certificate(self):
        result = run("cyc(6,16,2)", "M zyklisch (Translation)", machines=self.machines())
        self.assertEqual(result.verdict, Verdict.CONFIRMED)

    def test_refuted_certificate(self):
        result = run("cyc(6,16,3)", "M zyklisch", machines=self.machines())
        self.assertEqual(result.verdict, Verdict.REFUTED)

    def test_invalid_certificate_values(self):
        result = run("cyc(0,1,0)", "M zyklisch", machines=self.machines())
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        result = run("cyc(6,16,2)", "M zyklisch")
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)


class RegistryTest(unittest.TestCase):
    def test_registry_order_and_names(self):
        self.assertEqual(
            [kind.name for kind in witnesses.WITNESS_KINDS],
            ["auto", "py", "range", "ref", "sim", "cyc"],
        )

    def test_a_new_kind_is_one_recognizer_plus_one_executor(self):
        # The README recipe, walked: 'haltsteps(n)' re-derives that the bound
        # machine halts after exactly n steps.
        import re as _re
        from unittest import mock

        def parse_haltsteps(text):
            match = _re.match(r"\Ahaltsteps\(([0-9]+)\)\Z", text.strip())
            if match is None:
                return None
            return witnesses.WitnessSpec("haltsteps", {"steps": match.group(1)})

        def execute_haltsteps(spec, target_body, ctx, *, tolerant=False):
            machine, error = witnesses._machine_for(target_body, ctx)
            if machine is None:
                return witnesses.WitnessResult(Verdict.UNVERIFIABLE, f"haltsteps: {error}")
            claimed = int(spec.parts["steps"])
            outcome = turing.run(machine, claimed + 1)
            if outcome.halts and outcome.steps == claimed:
                return witnesses.WitnessResult(
                    Verdict.CONFIRMED, f"haltsteps: halted after exactly {claimed} steps"
                )
            return witnesses.WitnessResult(
                Verdict.REFUTED,
                f"haltsteps: halts={outcome.halts} steps={outcome.steps}, not {claimed}",
            )

        kind = witnesses.WitnessKind("haltsteps", parse_haltsteps, execute_haltsteps)
        with mock.patch.object(witnesses, "WITNESS_KINDS", witnesses.WITNESS_KINDS + (kind,)):
            spec = witnesses.parse_witness("haltsteps(3)")
            self.assertEqual(spec.kind, "haltsteps")
            result = witnesses.execute(
                spec,
                "M haltet",
                ctx(machines={"M": turing.parse(SMALL_HALTER)}),
            )
            self.assertEqual(result.verdict, Verdict.CONFIRMED)
            wrong = witnesses.execute(
                witnesses.parse_witness("haltsteps(4)"),
                "M haltet",
                ctx(machines={"M": turing.parse(SMALL_HALTER)}),
            )
            self.assertEqual(wrong.verdict, Verdict.REFUTED)
        # outside the patch the kind is unknown again
        with self.assertRaises(witnesses.WitnessError):
            witnesses.parse_witness("haltsteps(3)")


if __name__ == "__main__":
    unittest.main()
