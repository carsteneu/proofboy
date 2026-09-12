"""Tests for the standalone Turing-machine simulator (bemyself.turing).

The small machines are hand-traced in the comments; the three real machines
are the published Busy Beaver halters from the bbchallenge wiki (BB(5) and the
historical records), with their documented step counts and scores.
"""

import os
import subprocess
import sys
import unittest

from bemyself.turing import MachineError, parse, run

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Hand trace (blank tape, head on 0, state A):
#   step 1: A reads 0, writes 1, moves right -> B
#   step 2: B reads 0, writes 0, moves left  -> A
#   step 3: A reads 1, writes 1, moves right -> halts (Z)
# Halts after exactly 3 steps; the tape holds one 1.
TRACE_MACHINE = "1RB1RZ_0LA0LA"

# Never halts: writes 1 and walks right forever.
WALKER = "1RA1RA"

# Never halts: writes 0 and walks left forever; score stays 0.
ZERO_WALKER = "0LA0LA"

# Halts on the very first transition; the write of that transition counts.
ONE_STEP = "1RZ1RZ"

# Hand trace: step 1 writes 1 at 0 and moves right, step 2 writes 1 at 1 and
# moves left, step 3 moves right again, step 4 reads the 1 at 1, writes 0 over
# it, moves right and halts. Four steps, score 1 (the 1 at cell 0).
OVERWRITE_MACHINE = "1RB1RB_1LA0RZ"

# Hand trace: step 1 writes 1 at 0 and moves left, step 2 writes 1 at -1 and
# moves right, step 3 reads the 0 at 0 and moves left, step 4 reads the 1 at
# -1 (the left tape half), moves left and halts. Four steps, score 1.
LEFT_HALF_MACHINE = "0LB0RB_1RA1LZ"

# Published machines (bbchallenge wiki, BB(5) page; Michel, Historical Survey).
BB5_CHAMPION = "1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA"  # 47176870 steps, 4098 ones
BB5_SECOND = "1RB0LD_1LC1RD_1LA1LC_1RZ1RE_1RA0RB"  # 23554764 steps, 4097 ones
UHING_1984 = "1RB1LC_0LA0LD_1LA1RZ_1LB1RE_0RD0RB"  # 2133492 steps, 1915 ones
# BB(6) record holder (mxdys, June 2025); S(6) exceeds 2 arrow-up 5, far
# beyond any executable limit.
BB6_RECORD = "1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE"

# The BB(6) Cryptid "Antihydra" in the canonical notation of the bbchallenge
# wiki, including the undefined F0 transition (`---`); believed to never halt.
ANTIHYDRA = "1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA"


class ParseTest(unittest.TestCase):
    def test_parses_state_count(self):
        self.assertEqual(parse(ONE_STEP).states, 1)
        self.assertEqual(parse(TRACE_MACHINE).states, 2)
        self.assertEqual(parse(BB5_CHAMPION).states, 5)
        self.assertEqual(parse(BB6_RECORD).states, 6)

    def test_source_is_kept(self):
        self.assertEqual(parse(BB5_CHAMPION).source, BB5_CHAMPION)

    def test_surrounding_whitespace_is_stripped(self):
        machine = parse(f"  {ONE_STEP}\t")
        self.assertEqual(machine.source, ONE_STEP)
        self.assertEqual(run(machine, 1), (True, 1, 1))

    def test_table_entries_are_write_move_next(self):
        # One state, halt on both symbols: (write 1, right, halt) twice.
        self.assertEqual(parse(ONE_STEP).table, ((1, 1, -1), (1, 1, -1)))

    def test_bad_machines_are_rejected(self):
        for text in (
            "",
            "   ",
            "1RB1LC",  # one block, but B is not a defined state
            "1RB1LC_1RC1RB",  # C is not a defined state
            "1rb1lc_1rc1rb",  # lowercase is not the notation
            "1RX1LC",  # X is not a move
            "1RB1L",  # short block
            "1RB1LCX",  # long block
            "2RB1LC",  # 2 is not a symbol of this class
            "1RB1LC_",  # trailing separator
            "_1RB1LC",  # leading separator
            "1RB1LC__1RC1RB",  # empty block
            "1RB1LC 1RC1RB",  # internal whitespace
            "1RZ0LB",  # halts on 0, but B is undefined in a one-state machine
            "1RB1LC_1RC1R-",  # a triple is three characters or ---
            "1RB1LC_1RC-1RB",  # mixed dash garbage
        ):
            with self.subTest(text=text):
                with self.assertRaises(MachineError):
                    parse(text)

    def test_machine_error_is_a_value_error(self):
        self.assertTrue(issubclass(MachineError, ValueError))

    def test_state_limit(self):
        # 25 states (A..Y) are fine; a 26th block would be state Z, which the
        # notation reserves for halting.
        self.assertEqual(parse("_".join(["1RA1RA"] * 25)).states, 25)
        with self.assertRaises(MachineError):
            parse("_".join(["1RA1RA"] * 26))


class RunTest(unittest.TestCase):
    def test_hand_traced_machine_halts_at_exactly_three_steps(self):
        self.assertEqual(run(parse(TRACE_MACHINE), 10), (True, 3, 1))

    def test_halts_exactly_at_the_limit(self):
        self.assertEqual(run(parse(TRACE_MACHINE), 3), (True, 3, 1))

    def test_limit_stops_a_running_machine(self):
        self.assertEqual(run(parse(TRACE_MACHINE), 2), (False, 2, 1))
        self.assertEqual(run(parse(TRACE_MACHINE), 0), (False, 0, 0))

    def test_walker_never_halts_within_the_limit(self):
        self.assertEqual(run(parse(WALKER), 5), (False, 5, 5))

    def test_zero_walker_scores_zero(self):
        self.assertEqual(run(parse(ZERO_WALKER), 4), (False, 4, 0))

    def test_overwriting_a_one_decrements_the_score(self):
        self.assertEqual(run(parse(OVERWRITE_MACHINE), 10), (True, 4, 1))

    def test_writes_and_reads_on_the_left_tape_half(self):
        self.assertEqual(run(parse(LEFT_HALF_MACHINE), 10), (True, 4, 1))

    def test_result_fields(self):
        result = run(parse(ONE_STEP), 1)
        self.assertTrue(result.halts)
        self.assertEqual(result.steps, 1)
        self.assertEqual(result.score, 1)

    def test_negative_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            run(parse(ONE_STEP), -1)


class BusyBeaverTest(unittest.TestCase):
    """The published halters must come out with their exact numbers."""

    def test_bb5_champion(self):
        # Source: wiki.bbchallenge.org/wiki/BB(5); Coq-BB5 (arXiv:2509.12337).
        self.assertEqual(run(parse(BB5_CHAMPION), 47176870), (True, 47176870, 4098))

    def test_bb5_second_halter(self):
        # Source: wiki.bbchallenge.org/wiki/BB(5) (Marxen & Buntrock, 1989).
        self.assertEqual(run(parse(BB5_SECOND), 23554764), (True, 23554764, 4097))

    def test_uhing_1984_halter(self):
        # Source: P. Michel, Historical Survey (bbchallenge.org/~pascal.michel/
        # ha#tm52); Uhing, December 1984.
        self.assertEqual(run(parse(UHING_1984), 2133492), (True, 2133492, 1915))

    def test_bb6_record_halts_nowhere_near_a_short_limit(self):
        # Source: wiki.bbchallenge.org/wiki/BB(6) (mxdys, June 2025).
        result = run(parse(BB6_RECORD), 1000)
        self.assertFalse(result.halts)
        self.assertEqual(result.steps, 1000)


class UndefinedTransitionTest(unittest.TestCase):
    """The `---` triple of the notation: the machine halts when the head reads
    that pair, and the attempted transition is not counted as a step."""

    # Hand trace (blank tape, head on 0, state A):
    #   step 1: A reads 0, writes 1, moves right -> B
    #   B reads 0: undefined transition -> halt, before executing anything
    # One step, score 1.
    UNDEFINED_HALT = "1RB1RZ_---0LA"

    def test_undefined_transition_halts_before_executing(self):
        self.assertEqual(run(parse(self.UNDEFINED_HALT), 10), (True, 1, 1))

    def test_undefined_transition_at_the_start_halts_at_zero_steps(self):
        self.assertEqual(run(parse("---1RA"), 10), (True, 0, 0))

    def test_whole_block_may_be_undefined(self):
        machine = parse("------")
        self.assertEqual(machine.states, 1)
        self.assertEqual(run(machine, 10), (True, 0, 0))

    def test_undefined_transition_only_halts_when_reached(self):
        # Reads 0 forever and walks right: the undefined read-1 pair is never
        # taken, so the limit stops the run.
        self.assertEqual(run(parse("1RA---"), 4), (False, 4, 4))

    def test_explicit_halt_still_counts_its_transition(self):
        # The two halt flavours of the notation: Z counts its transition,
        # `---` halts without executing. Both machines read 0 first.
        self.assertEqual(run(parse("1RZ1RZ"), 10), (True, 1, 1))
        self.assertEqual(run(parse("---1RZ"), 10), (True, 0, 0))

    def test_antihydra_parses_and_survives_a_bounded_run(self):
        # Source: wiki.bbchallenge.org/wiki/Antihydra (rev 7477), the BB(6)
        # Cryptid; the undefined F0 transition is never reached in a bounded
        # run, so the simulation reports exactly the executed steps.
        machine = parse(ANTIHYDRA)
        self.assertEqual(machine.states, 6)
        result = run(machine, 1000)
        self.assertFalse(result.halts)
        self.assertEqual(result.steps, 1000)


class TuringCliTest(unittest.TestCase):
    """``python3 -m bemyself.turing <maschine> <schritte>`` prints one result
    line: the command form the COMPUTE claim type runs in the sandbox."""

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "bemyself.turing", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_prints_the_run_result(self):
        proc = self.invoke("1RB1RZ_0LA0LA", "3")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "halts=True steps=3 score=1\n")

    def test_prints_a_bounded_run_without_halt(self):
        proc = self.invoke(ANTIHYDRA, "100")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertRegex(proc.stdout, r"\Ahalts=False steps=100 score=\d+\n\Z")

    def test_usage_without_arguments(self):
        proc = self.invoke()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr)

    def test_bad_machine_is_an_error(self):
        proc = self.invoke("1RB", "3")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.strip())

    def test_bad_step_count_is_an_error(self):
        for steps in ("three", "-1", "3.0", ""):
            with self.subTest(steps=steps):
                proc = self.invoke("1RB1RZ_0LA0LA", steps)
                self.assertEqual(proc.returncode, 2)
                self.assertTrue(proc.stderr.strip())


if __name__ == "__main__":
    unittest.main()
