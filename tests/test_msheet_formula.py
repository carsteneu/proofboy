"""Tests for the V1 formula fragment of bemyself.msheet (05-02 §2/§3/§4).

The fragment is deliberately small and fully parenthesized: exact integers,
ranges, library calls, finite quantifiers. Terms evaluate to exact values
(int or Fraction), formulas to bool. Anything else is a FormulaError, a free
variable is never guessed, a guard violation raises, and a top-level
quantifier over an empty range is an error the runner turns into
UNVERIFIABLE/empty_range (no vacuous confirmations).
"""

import time
import unittest
from fractions import Fraction

from bemyself.msheet import formula
from bemyself.msheet.library import GuardError


def ev(text, env=None, defs=None, top_level=True):
    return formula.evaluate(formula.parse_formula(text, defs=defs), env=env, top_level=top_level)


class ArithmeticTest(unittest.TestCase):
    def test_integers(self):
        self.assertEqual(ev("7"), 7)
        self.assertEqual(ev("(2 + 3)"), 5)
        self.assertEqual(ev("((2 + 3) * 4)"), 20)
        self.assertEqual(ev("(10 // 3)"), 3)
        self.assertEqual(ev("(10 % 3)"), 1)
        self.assertEqual(ev("(2 ^ 10)"), 1024)
        self.assertEqual(ev("(2 ** 10)"), 1024)
        self.assertEqual(ev("((- 5) + 5)"), 0)
        self.assertEqual(ev("-17"), -17)

    def test_exact_division_and_decimals(self):
        self.assertEqual(ev("(1 / 2)"), Fraction(1, 2))
        self.assertEqual(ev("((1 / 2) + (1 / 2))"), Fraction(1))
        self.assertEqual(ev("(3.5 + 0.5)"), Fraction(4))
        self.assertEqual(ev("1e3"), 1000)

    def test_power_is_exact(self):
        self.assertEqual(ev("(2 ^ 127)"), 2**127)


class ComparisonAndLogicTest(unittest.TestCase):
    def test_comparisons(self):
        self.assertIs(ev("(2 < 3)"), True)
        self.assertIs(ev("(3 <= 2)"), False)
        self.assertIs(ev("(2 = 2)"), True)
        self.assertIs(ev("(2 != 3)"), True)
        self.assertIs(ev("(4 >= 4)"), True)
        self.assertIs(ev("(5 > 7)"), False)

    def test_logic(self):
        self.assertIs(ev("((2 < 3) & (4 < 5))"), True)
        self.assertIs(ev("((2 < 3) | (4 < 1))"), True)
        self.assertIs(ev("(!(2 < 3))"), False)
        self.assertIs(ev("((2 < 3) -> (4 < 5))"), True)
        self.assertIs(ev("((2 < 3) -> (4 > 5))"), False)
        self.assertIs(ev("((2 < 3) <-> (3 < 4))"), True)

    def test_exactness_across_types(self):
        self.assertIs(ev("((1 / 3) = (2 / 6))"), True)
        self.assertIs(ev("((1 / 2) < (2 / 3))"), True)


class LibraryCallTest(unittest.TestCase):
    def test_calls_and_aliases(self):
        self.assertIs(ev("(collatz_steps(27) = 111)"), True)
        self.assertIs(ev("(st(27) = 111)"), True)
        self.assertIs(ev("ip(97)"), True)
        self.assertEqual(ev("(dv(28))"), [1, 2, 4, 7, 14, 28])
        self.assertIs(ev("(ch(10, 3) = 120)"), True)
        self.assertIs(ev("(fb(100) = 354224848179261915075)"), True)

    def test_guard_violation_raises(self):
        with self.assertRaises(GuardError):
            ev("(ip(((10 ^ 12) + 1)) = 0)")
        with self.assertRaises(GuardError):
            ev("(fc(10001) = 0)")


class RangeAndQuantifierTest(unittest.TestCase):
    def test_sum_prod(self):
        self.assertEqual(ev("sum(k=1..5, k)"), 15)
        self.assertEqual(ev("prod(k=1..5, k)"), 120)
        self.assertEqual(ev("sum(k=1..0, k)"), 0)
        self.assertEqual(ev("prod(k=1..0, k)"), 1)

    def test_quantifiers(self):
        self.assertIs(ev("(forall n in 1..5: (n < 6))"), True)
        self.assertIs(ev("(forall n in 1..5: (n < 5))"), False)
        self.assertIs(ev("(exists n in 1..5: (n = 5))"), True)
        self.assertIs(ev("(exists n in 1..5: (n = 6))"), False)
        self.assertIs(ev("(forall x in {2, 3, 5}: ip(x))"), True)
        self.assertIs(ev("(exists x in {4, 9}: ip(x))"), False)

    def test_empty_range_top_level_is_an_error(self):
        with self.assertRaises(formula.EmptyRangeError):
            ev("(forall n in 1..0: (n > 0))")
        with self.assertRaises(formula.EmptyRangeError):
            ev("(exists n in 1..0: (n > 0))")

    def test_empty_range_nested_keeps_standard_semantics(self):
        self.assertIs(
            ev("(forall n in 1..3: (forall m in 1..0: (m > 0)))"),
            True,
        )
        self.assertIs(
            ev("(forall n in 1..3: (exists m in 1..0: (m > 0)))"),
            False,
        )


class DefTest(unittest.TestCase):
    def test_user_definition(self):
        defs = {"sum_1_to_n": formula.parse_def("def sum_1_to_n(n) = sum(k=1..n, k)")}
        self.assertEqual(ev("sum_1_to_n(5)", defs=defs), 15)
        self.assertIs(ev("(sum_1_to_n(5) = ((5 * (5 + 1)) // 2))", defs=defs), True)

    def test_def_may_use_earlier_def(self):
        defs = {
            "double": formula.parse_def("def double(n) = (n + n)"),
            "quad": formula.parse_def("def quad(n) = double(double(n))"),
        }
        self.assertEqual(ev("quad(3)", defs=defs), 12)

    def test_reserved_words_are_no_names(self):
        with self.assertRaises(formula.FormulaError):
            formula.parse_def("def sum(n) = n")
        with self.assertRaises(formula.FormulaError):
            formula.parse_def("def forall(n) = n")

    def test_unknown_name_is_an_error(self):
        with self.assertRaises(formula.FormulaError):
            ev("(foo(2) = 0)")
        with self.assertRaises(formula.FormulaError):
            ev("(n + 1)")  # free variable in a closed formula

    def test_def_shadowing_a_library_name_is_rejected(self):
        with self.assertRaises(formula.FormulaError):
            formula.parse_def("def isprime(n) = n")


    def test_exponent_guard_bounds_both_signs(self):
        with self.assertRaises(formula.EvaluationError):
            ev("(2 ^ 1000001)")
        with self.assertRaises(formula.EvaluationError):
            ev("(2 ^ -1000001)")
        self.assertEqual(ev("(2 ^ -3)"), Fraction(1, 8))

    def test_range_guard_bounds_the_element_count(self):
        # 10^6 elements run in well under a second per the security review
        # measurement (10^7 would take seconds to minutes).
        self.assertIs(ev("(forall k in 1..1000000: (k = k))"), True)
        with self.assertRaises(formula.EvaluationError):
            ev("(forall k in 1..1000001: (k = k))")

    def test_deep_nesting_is_a_formula_error_not_a_recursion_error(self):
        with self.assertRaises(formula.FormulaError):
            formula.parse_formula("(" * 3000 + "1" + ")" * 3000)


class SyntaxTest(unittest.TestCase):
    def test_full_parenthesization_is_required(self):
        with self.assertRaises(formula.FormulaError):
            formula.parse_formula("2 + 3")
        with self.assertRaises(formula.FormulaError):
            formula.parse_formula("(2 + 3 + 4)")

    def test_broken_texts(self):
        for text in ("(2 + )", "(2 + 3", "2 3", "(= 3)", "()", "sum(k=1..5)", ""):
            with self.assertRaises(formula.FormulaError, msg=text):
                formula.parse_formula(text)

    def test_whitespace_is_free(self):
        self.assertEqual(ev("( 2   +   3 )"), 5)
        self.assertIs(ev("( forall n in 1..3 : ( n < 4 ) )"), True)

    def test_not_a_bool(self):
        with self.assertRaises(formula.NotAFormula):
            formula.evaluate_bool(formula.parse_formula("(2 + 3)"))
        with self.assertRaises(formula.NotAFormula):
            formula.evaluate_bool(formula.parse_formula("(dv(28))"))

    def test_parse_performance_on_hostile_whitespace(self):
        text = "(2" + " " * 4000 + "+ 3)"
        start = time.monotonic()
        self.assertEqual(ev(text), 5)
        self.assertLess(time.monotonic() - start, 1.0)

    def test_parse_performance_on_unterminated_text(self):
        text = "(" + " " * 8000
        start = time.monotonic()
        with self.assertRaises(formula.FormulaError):
            formula.parse_formula(text)
        self.assertLess(time.monotonic() - start, 1.0)


if __name__ == "__main__":
    unittest.main()
