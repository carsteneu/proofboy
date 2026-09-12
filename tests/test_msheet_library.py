"""Tests for the V1 library of bemyself.msheet.

The library is the checkable fragment of mathematics of the notation
(05-02 §2): exact integers, deterministic functions, documented guard
limits. A guard violation must raise (never a silent approximation), and the
verdict of a witness stands or falls with this exactness.
"""

import unittest

from bemyself.msheet import library


class GuardTest(unittest.TestCase):
    def test_guard_error_is_a_value_error(self):
        self.assertTrue(issubclass(library.GuardError, ValueError))


class IsPrimeTest(unittest.TestCase):
    def test_small_cases(self):
        self.assertFalse(library.isprime(0))
        self.assertFalse(library.isprime(1))
        self.assertTrue(library.isprime(2))
        self.assertTrue(library.isprime(97))
        self.assertFalse(library.isprime(91))
        self.assertTrue(library.isprime(999999999989))  # prime, just below 10^12

    def test_guard_limit(self):
        self.assertFalse(library.isprime(10**12))  # 2^12 * 5^12, exactly at the limit
        with self.assertRaises(library.GuardError):
            library.isprime(10**12 + 1)


class PowmodTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(library.powmod(2, 10, 1000), 24)
        self.assertEqual(library.powmod(3, 0, 7), 1)
        self.assertEqual(library.powmod(123456, 789, 10**12), pow(123456, 789, 10**12))

    def test_guards(self):
        with self.assertRaises(library.GuardError):
            library.powmod(2, 10**12 + 1, 7)
        with self.assertRaises(library.GuardError):
            library.powmod(2, 3, 10**12 + 1)
        with self.assertRaises(library.GuardError):
            library.powmod(2, -1, 7)
        with self.assertRaises(library.GuardError):
            library.powmod(2, 3, 0)


class GcdDividesTest(unittest.TestCase):
    def test_gcd(self):
        self.assertEqual(library.gcd(12, 18), 6)
        self.assertEqual(library.gcd(-12, 18), 6)
        self.assertEqual(library.gcd(0, 5), 5)

    def test_divides(self):
        self.assertTrue(library.divides(3, 12))
        self.assertFalse(library.divides(5, 12))
        self.assertTrue(library.divides(-3, 12))
        with self.assertRaises(library.GuardError):
            library.divides(0, 12)

    def test_guards(self):
        with self.assertRaises(library.GuardError):
            library.gcd(10**12 + 1, 1)
        with self.assertRaises(library.GuardError):
            library.divides(1, 10**12 + 1)


class DivisorsTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(library.divisors(1), [1])
        self.assertEqual(library.divisors(28), [1, 2, 4, 7, 14, 28])
        self.assertEqual(library.divisors(97), [1, 97])

    def test_guards(self):
        with self.assertRaises(library.GuardError):
            library.divisors(0)
        with self.assertRaises(library.GuardError):
            library.divisors(10**12 + 1)


class FactorialChooseFibTest(unittest.TestCase):
    def test_factorial(self):
        self.assertEqual(library.factorial(0), 1)
        self.assertEqual(library.factorial(5), 120)
        with self.assertRaises(library.GuardError):
            library.factorial(10**4 + 1)
        with self.assertRaises(library.GuardError):
            library.factorial(-1)

    def test_choose(self):
        self.assertEqual(library.choose(10, 3), 120)
        self.assertEqual(library.choose(5, 0), 1)
        with self.assertRaises(library.GuardError):
            library.choose(10**4 + 1, 2)
        with self.assertRaises(library.GuardError):
            library.choose(3, 5)

    def test_fib(self):
        self.assertEqual(library.fib(0), 0)
        self.assertEqual(library.fib(1), 1)
        self.assertEqual(library.fib(10), 55)
        self.assertEqual(library.fib(100), 354224848179261915075)
        with self.assertRaises(library.GuardError):
            library.fib(10**6 + 1)
        with self.assertRaises(library.GuardError):
            library.fib(-1)


class CollatzTest(unittest.TestCase):
    def test_steps(self):
        self.assertEqual(library.collatz_steps(1), 0)
        self.assertEqual(library.collatz_steps(27), 111)
        self.assertEqual(library.collatz_steps(2), 1)

    def test_max(self):
        self.assertEqual(library.collatz_max(1), 1)
        self.assertEqual(library.collatz_max(27), 9232)

    def test_guards(self):
        with self.assertRaises(library.GuardError):
            library.collatz_steps(0)
        with self.assertRaises(library.GuardError):
            library.collatz_steps(10**7 + 1)
        with self.assertRaises(library.GuardError):
            library.collatz_max(10**7 + 1)


class AliasTest(unittest.TestCase):
    def test_all_ten_aliases_resolve_to_the_long_form(self):
        expected = {
            "ip": "isprime",
            "st": "collatz_steps",
            "mx": "collatz_max",
            "pm": "powmod",
            "gc": "gcd",
            "dv": "divisors",
            "di": "divides",
            "fc": "factorial",
            "ch": "choose",
            "fb": "fib",
        }
        for alias, canonical in expected.items():
            self.assertIn(alias, library.RESOLVED)
            self.assertIn(canonical, library.RESOLVED)
            self.assertIs(library.RESOLVED[alias], library.RESOLVED[canonical])

    def test_long_forms_are_resolved(self):
        for name in (
            "isprime",
            "collatz_steps",
            "collatz_max",
            "powmod",
            "gcd",
            "divisors",
            "divides",
            "factorial",
            "choose",
            "fib",
        ):
            self.assertIn(name, library.RESOLVED)


if __name__ == "__main__":
    unittest.main()
