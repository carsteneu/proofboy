#!/usr/bin/env python3
"""Deep counter run for the Antihydra Cryptid (BB(6) holdout, BMO#2).

The halting question of ``1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA`` is
equivalent to the walk ``h_0 = 8``, ``h -> h + h//2`` with the counter
``+2`` for even ``h`` and ``-1`` for odd ``h``: the machine halts iff the
counter ever reaches ``-1`` (BusyBeaverWiki Antihydra, sligocki.com 2024).
The counter sequence is OEIS A385902.

Method
------
A block of ``2**dep`` steps is computed from two half blocks (the approach
mxdys described in the bbchallenge forum, July 2024): the parity sequence of
the first ``n`` steps depends only on the current value modulo ``2**n``, so a
sub-block only needs the low ``n`` bits, and the correction ``c`` with
``3**n * x - c = 2**n * phi**n(x)`` is propagated to the parent, which patches
the halves together. The counter and its minimum are accumulated at the
leaves, so all checkpoints are exact; the tracked value is only exact modulo
the block length, and since the counter does not depend on the high bits, no
value is reported.

Backend
-------
The parent patch-up multiplies numbers of up to ``n`` bits. ``--backend auto``
uses libgmp through ``ctypes`` when ``libgmp.so.10`` is present and falls back
to CPython integers otherwise; ``--backend gmp`` and ``--backend python``
force one side. The backend is verified against CPython integers on random
values at startup (deterministic seed), and the block method is verified
against the plain recurrence by ``--verify-brute``.

Usage::

    python3 -m bemyself.experiments.antihydra_deep --depth 22
    python3 -m bemyself.experiments.antihydra_deep --depth 26 --verify-brute 20
    python3 -m bemyself.experiments.antihydra_deep --check-prefix b385902.txt

Output (stdout): one line per checkpoint at ``2**k`` steps plus the minimum::

    steps=<n> counter=<c> deviation=<c - n//2>
    min_counter=<m>
"""

from __future__ import annotations

import argparse
import ctypes
import random
import sys
import time

BASE_DEP = 8  # steps per leaf block: 2**8 = 256


class PythonBackend:
    """Big-integer multiplication via CPython integers."""

    name = "python"

    def mul(self, a, b):
        return a * b

    def close(self):
        pass


class GmpBackend:
    """Big-integer multiplication via libgmp (ctypes, no headers needed).

    ``mpz_import``/``mpz_export`` are called with ``order=0`` and big-endian
    byte strings (``size=1``): the documented big-endian form, so the same
    code is correct on any GMP build.
    """

    name = "gmp"

    def __init__(self, library="libgmp.so.10"):
        lib = ctypes.CDLL(library)

        class Mpz(ctypes.Structure):
            _fields_ = [
                ("_mp_alloc", ctypes.c_int),
                ("_mp_size", ctypes.c_int),
                ("_mp_d", ctypes.POINTER(ctypes.c_ulong)),
            ]

        self._Mpz = Mpz
        # lib[name]: attribute access would mangle the double underscore names.
        init = lib["__gmpz_init"]
        clear = lib["__gmpz_clear"]
        import_ = lib["__gmpz_import"]
        export = lib["__gmpz_export"]
        mul = lib["__gmpz_mul"]
        init.argtypes = [ctypes.POINTER(Mpz)]
        clear.argtypes = [ctypes.POINTER(Mpz)]
        import_.argtypes = [
            ctypes.POINTER(Mpz), ctypes.c_size_t, ctypes.c_int, ctypes.c_size_t,
            ctypes.c_int, ctypes.c_size_t, ctypes.c_void_p,
        ]
        export.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_int,
            ctypes.c_size_t, ctypes.c_int, ctypes.c_size_t, ctypes.POINTER(Mpz),
        ]
        export.restype = ctypes.c_void_p
        mul.argtypes = [ctypes.POINTER(Mpz)] * 3
        self._lib = lib
        self._init = init
        self._clear = clear
        self._import_gmp = import_
        self._export_gmp = export
        self._mul = mul
        self._a = Mpz()
        self._b = Mpz()
        self._c = Mpz()
        for z in (self._a, self._b, self._c):
            init(ctypes.byref(z))

    def _set(self, z, value):
        self._clear(ctypes.byref(z))
        self._init(ctypes.byref(z))
        if value:
            size = (value.bit_length() + 7) // 8
            buf = ctypes.create_string_buffer(value.to_bytes(size, "big"))
            self._import_gmp(
                ctypes.byref(z), size, 0, 1, 0, 0, ctypes.cast(buf, ctypes.c_void_p)
            )

    def _get(self, z):
        if z._mp_size == 0:
            return 0
        size = ctypes.c_size_t(0)
        out = ctypes.create_string_buffer(abs(z._mp_size) * 8 + 16)
        self._export_gmp(out, ctypes.byref(size), 0, 1, 0, 0, ctypes.byref(z))
        return int.from_bytes(out.raw[: size.value], "big")

    def mul(self, a, b):
        self._set(self._a, a)
        self._set(self._b, b)
        self._mul(ctypes.byref(self._c), ctypes.byref(self._a), ctypes.byref(self._b))
        return self._get(self._c)

    def close(self):
        for z in (self._a, self._b, self._c):
            self._clear(ctypes.byref(z))


def backend_self_check(backend, seed=20260913):
    """Verify a backend against CPython integers on deterministic values."""
    rng = random.Random(seed)
    for bits in (1, 7, 8, 9, 63, 64, 65, 1023, 1024, 1025, 4096):
        a = rng.getrandbits(bits)
        b = rng.getrandbits(bits)
        if backend.mul(a, b) != a * b:
            return False, f"multiplication mismatch at {bits} bits"
    return True, "ok"


def make_backend(name):
    """(backend, note): resolve ``auto``/``gmp``/``python``."""
    if name == "python":
        return PythonBackend(), "python (forced)"
    try:
        backend = GmpBackend()
    except OSError as exc:
        if name == "gmp":
            raise SystemExit(f"libgmp unavailable: {exc}") from exc
        return PythonBackend(), f"python (libgmp unavailable: {exc})"
    ok, note = backend_self_check(backend)
    if not ok:
        backend.close()
        if name == "gmp":
            raise SystemExit(f"libgmp self-check failed: {note}")
        return PythonBackend(), f"python (libgmp self-check failed: {note})"
    return backend, "gmp (libgmp.so.10 via ctypes, order=0 big-endian)"


class DeepRun:
    """Block divide-and-conquer counter run up to ``2**depth`` steps.

    Checkpoints are powers of two (plus any ``extra_targets``), emitted in
    increasing step order; the counter minimum is tracked exactly.
    """

    def __init__(self, backend, depth, base_dep=BASE_DEP, extra_targets=(), progress=False):
        self.backend = backend
        self.depth = depth
        self.base_dep = base_dep
        self.extra = sorted(t for t in extra_targets if 0 < t <= (1 << depth))
        self.progress = progress
        self.pow3 = {}
        self.masks = {0: 0}
        self.steps = 0
        self.odds = 0
        self.evens = 0
        self.minimum = 0
        self.next_target = 1
        self.extra_index = 0
        self.lines = []
        self.emitted = set()
        self.started = time.monotonic()
        effective_base = min(base_dep, depth)
        exponents = set(range(effective_base, max(depth, effective_base + 1)))
        top = max(exponents)
        value = 3  # POW3[k] = 3 ** (2 ** k), built by repeated squaring
        for k in range(0, top + 1):
            if k in exponents:
                self.pow3[k] = value
            if k < top:
                value = backend.mul(value, value)

    def counter(self):
        return 2 * self.evens - self.odds

    def _emit(self, steps, counter):
        if steps in self.emitted:
            return
        self.emitted.add(steps)
        self.lines.append((steps, f"steps={steps} counter={counter} deviation={counter - steps // 2}"))
        if self.progress:
            elapsed = time.monotonic() - self.started
            print(
                f"# progress: {steps} steps, {elapsed:.1f}s, counter={counter}",
                file=sys.stderr,
                flush=True,
            )

    def _mask(self, bits):
        mask = self.masks.get(bits)
        if mask is None:
            mask = (1 << bits) - 1
            self.masks[bits] = mask
        return mask

    def _base_block(self, x, dep):
        """Plain recurrence for ``2**dep`` steps; returns (value, correction).

        The loop is split at checkpoint boundaries so that the hot part holds
        no per-step checkpoint tests.
        """
        n = 1 << dep  # number of steps
        start = x
        odds = evens = 0
        cur = self.counter()
        block_min = cur
        target = self.next_target
        extra = self.extra
        extra_index = self.extra_index
        steps = self.steps
        end = steps + n
        splits = []
        # Checkpoints that coincide with the block start belong to the state
        # the previous block ended in.
        while target <= steps:
            if target == steps:
                self._emit(target, cur)
            target *= 2
        while extra_index < len(extra) and extra[extra_index] <= steps:
            if extra[extra_index] == steps:
                self._emit(extra[extra_index], cur)
            extra_index += 1
        while target < end:
            if target > steps:
                splits.append(target)
            target *= 2
        while extra_index < len(extra) and extra[extra_index] < end:
            splits.append(extra[extra_index])
            extra_index += 1
        splits.sort()
        position = steps
        for split in splits:
            for _ in range(split - position):
                if x & 1:
                    odds += 1
                    cur -= 1
                else:
                    evens += 1
                    cur += 2
                x += x >> 1
                if cur < block_min:
                    block_min = cur
            position = split
            self.steps = position
            self.odds += odds
            self.evens += evens
            odds = evens = 0
            self._emit(position, cur)
        for _ in range(end - position):
            if x & 1:
                odds += 1
                cur -= 1
            else:
                evens += 1
                cur += 2
            x += x >> 1
            if cur < block_min:
                block_min = cur
        self.steps = end
        self.odds += odds
        self.evens += evens
        self.extra_index = extra_index
        self.next_target = target
        if block_min < self.minimum:
            self.minimum = block_min
        correction = self.backend.mul(self.pow3[dep], start) - (x << n)
        return x, correction

    def _block(self, x, dep, last):
        """(value, correction) for ``2**dep`` steps from the true value ``x``.

        Sub-blocks only need the low ``2**dep`` bits of their input (the
        parities of ``2**dep`` steps depend on nothing above them), so the
        recursive calls get a masked copy. The returned value is recomputed
        from the *unmasked* input with the composed correction, which makes it
        the true trajectory value -- feeding the masked-chain value onward
        would corrupt the parities of the next block. ``last`` blocks skip the
        recomputation (their value is never used).
        """
        n = 1 << dep  # number of steps of this block
        original = x
        if x.bit_length() > n:
            x &= self._mask(n)
        if dep <= self.base_dep:
            _, correction = self._base_block(x, dep)
        else:
            value1, correction1 = self._block(x, dep - 1, False)
            _, correction2 = self._block(value1, dep - 1, True)
            half = 1 << (dep - 1)  # steps of one half block
            correction = (
                self.backend.mul(correction1, self.pow3[dep - 1])
                + (correction2 << half)
            )
        if last:
            return None, correction
        value = (self.backend.mul(original, self.pow3[dep]) - correction) >> n
        return value, correction

    def run(self):
        self._block(8, self.depth, True)
        # The run's final step is a checkpoint as well (no block starts there).
        self._emit(1 << self.depth, self.counter())
        return [text for _, text in self.lines] + [
            f"min_counter={self.minimum}",
            f"total_steps={self.steps}",
        ]


def deep_lines(depth, backend, base_dep=BASE_DEP, extra_targets=(), progress=False):
    """The checkpoint lines of a D&C run to ``2**depth`` steps."""
    run = DeepRun(backend, depth, base_dep=base_dep, extra_targets=extra_targets,
                  progress=progress)
    return run.run()


def brute_lines(depth, extra_targets=()):
    """The same checkpoints from the plain recurrence (the reference)."""
    targets = {1 << k for k in range(0, depth + 1)} | set(extra_targets)
    h = 8
    odds = evens = 0
    minimum = 0
    lines = []
    for step in range(1, (1 << depth) + 1):
        if h & 1:
            odds += 1
        else:
            evens += 1
        h += h >> 1
        counter = 2 * evens - odds
        if counter < minimum:
            minimum = counter
        if step in targets:
            lines.append(
                f"steps={step} counter={counter} deviation={counter - step // 2}"
            )
    lines.append(f"min_counter={minimum}")
    lines.append(f"total_steps={1 << depth}")
    return lines


def brute_min_counter(steps):
    """The exact counter minimum of the plain walk for ``steps`` steps."""
    h = 8
    odds = evens = 0
    minimum = 0
    for _ in range(steps):
        if h & 1:
            odds += 1
        else:
            evens += 1
        h += h >> 1
        counter = 2 * evens - odds
        if counter < minimum:
            minimum = counter
    return minimum


def check_prefix(path):
    """Compare the plain walk against an OEIS b-file ('n value' lines)."""
    mismatches = []
    with open(path, encoding="utf-8") as handle:
        rows = [
            line.split()
            for line in handle
            if line.strip() and not line.startswith("#")
        ]
    h = 8
    odds = evens = 0
    for index, row in enumerate(rows):
        n, value = int(row[0]), int(row[1])
        if n != index:
            mismatches.append(f"line {index + 1}: index {n} != {index}")
            break
        counter = 2 * evens - odds
        if counter != value:
            mismatches.append(f"n={n}: walk {counter} != file {value}")
            break
        if h & 1:
            odds += 1
        else:
            evens += 1
        h += h >> 1
    return mismatches


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--depth", type=int, default=22, help="run to 2**DEPTH steps")
    parser.add_argument("--backend", choices=("auto", "gmp", "python"), default="auto")
    parser.add_argument("--base", type=int, default=BASE_DEP,
                        help="steps per leaf block, 2**BASE (default %(default)s)")
    parser.add_argument("--also", type=int, action="append", default=[],
                        help="extra checkpoint step (repeatable)")
    parser.add_argument("--verify-brute", type=int, metavar="DEPTH", default=None,
                        help="compare the checkpoints with the plain recurrence to 2**DEPTH")
    parser.add_argument("--check-prefix", metavar="FILE", default=None,
                        help="compare the plain walk against an OEIS b-file")
    parser.add_argument("--progress", action="store_true", help="progress on stderr")
    args = parser.parse_args(argv)

    backend, note = make_backend(args.backend)
    header = [
        "# antihydra deep counter run",
        "# map: h_0=8, h -> h + h//2; counter +2 on even h, -1 on odd h (walk of the A-rule model)",
        f"# backend: {note}; leaf block 2**{args.base}={1 << args.base} steps",
        "# deviation = counter - floor(steps/2); checkpoints at powers of two",
    ]

    if args.check_prefix:
        mismatches = check_prefix(args.check_prefix)
        header.append(f"check.prefix.mismatches={mismatches or 'none'}")
        print("\n".join(header))
        return 0 if not mismatches else 1

    lines = deep_lines(args.depth, backend, base_dep=args.base,
                       extra_targets=args.also, progress=args.progress)
    if args.verify_brute is not None:
        reference = brute_lines(
            args.verify_brute,
            extra_targets=[t for t in args.also if t <= (1 << args.verify_brute)],
        )
        missing = [line for line in reference if line not in lines]
        lines.append(
            f"check.brute.depth={args.verify_brute} "
            f"reference_lines={len(reference)} "
            f"mismatches={missing or 'none'}"
        )
    print("\n".join(header + lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
