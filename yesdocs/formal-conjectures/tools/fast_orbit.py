#!/usr/bin/env python3
"""Fast Antihydra orbit generator via exact W-step block transfer.

The Antihydra parity chain is the iteration x -> T(x) = 3*x // 2 starting
at x0 = 8 (x = b + 4, the blank-tape orbit).  The generator uses the exact
transfer identity

    T^w(2^w * q + r) = 3^w * q + T^w(r)      (all q >= 0, 0 <= r < 2^w)

so one block advances w steps at once, and the parity bits of those w steps
depend only on r = x mod 2^w.  Only the running exact x is kept (no per-step
x list), therefore memory stays O(n) bytes for the bit stream plus the 2^w
translation tables, instead of Theta(n^2) bits for stored per-step x values.

Output: a bits file (one byte per step, 1 = x even) plus statistics,
including H(n) = 5*E(n) - 2*n (the reserve, E = number of even steps),
A(n) = 3*E(n) - n (the counter) and the 8-step block drawdown

    max_j ( max_{i<=j} S_i - S_j ),   S_j = sum_{i<j} (5*even_i - 16),

over all full 8-step blocks of the stream, with the block indices of the
maximal peak-to-trough segment.  (This is the quantity D_Block = 73 of the
Astra lemma loop; w=8 block weights are 5*(#even) - 16 because 16 = 2*8.)

Usage:  python3 fast_orbit.py 8388608 -o antihydra-bits-2p23.bin
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time

DEFAULT_W = 16
X0 = 8
MIN_W = 4
MAX_W = 20
MAX_N = 1 << 27  # bounds the up-front bytearray(n) commitment (128 MiB)


def _tables(w):
    """Return (T^w(r), parity-word of the next w steps) for r in [0, 2^w)."""
    size = 1 << w
    tw = [0] * size
    pw = [0] * size
    for r in range(size):
        x = r
        word = 0
        for i in range(w):
            if not (x & 1):
                word |= 1 << i
            x = 3 * x // 2
        tw[r] = x
        pw[r] = word
    return tw, pw


def transfer_table(w):
    """T^w(r) for r in [0, 2^w): the remainder of the block transfer."""
    return _tables(w)[0]


def orbit_bits(n, w=DEFAULT_W, x0=X0):
    """Return (bits, x_end): parity bits of the first n steps, x after n steps."""
    if n < 0:
        raise ValueError("n must be >= 0")
    tw, pw = _tables(w)
    p3 = 3 ** w
    mask = (1 << w) - 1
    out = bytearray(n)
    x = x0
    pos = 0
    while pos + w <= n:
        r = x & mask
        word = pw[r]
        for i in range(w):
            out[pos + i] = (word >> i) & 1
        x = p3 * (x >> w) + tw[r]
        pos += w
    while pos < n:  # tail: exact x_end after exactly n steps
        out[pos] = 0 if (x & 1) else 1
        x = 3 * x // 2
        pos += 1
    return bytes(out), x


def stats(bits):
    """Statistics of a parity stream: E/H/A, dyadic H values, block drawdown."""
    n = len(bits)
    E = sum(bits)
    H = 5 * E - 2 * n
    A = 3 * E - n
    dyadic = {}
    c = 0
    nxt = 1
    for i, b in enumerate(bits, start=1):
        c += b
        if i == nxt:
            dyadic[i.bit_length() - 1] = 5 * c - 2 * i
            nxt <<= 1
    best = 0
    cum = 0
    peak = 0
    peak_at = 0
    bi = bj = 0
    for b0 in range(0, n - 7, 8):
        g = 5 * sum(bits[b0:b0 + 8]) - 16
        cum += g
        if cum > peak:
            peak = cum
            peak_at = b0 // 8
        dd = peak - cum
        if dd > best:
            best = dd
            bi = peak_at
            bj = b0 // 8
    return {
        "n": n, "E": E, "H": H, "A": A, "gsum": H,
        "H_dyadic": dyadic,
        "block_drawdown_8": best, "dd_peak_block": bi, "dd_trough_block": bj,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fast Antihydra orbit generator (x -> 3x//2, x0=8).")
    ap.add_argument("n", type=int,
                    help=f"number of steps (up to {MAX_N})")
    ap.add_argument("-w", "--w", type=int, default=DEFAULT_W,
                    help=f"block width in steps (default {DEFAULT_W})")
    ap.add_argument("-o", "--out", default="antihydra-bits.bin",
                    help="bits output file (default antihydra-bits.bin)")
    ap.add_argument("--no-bits", action="store_true",
                    help="do not write the bits file")
    ap.add_argument("--quiet", action="store_true",
                    help="deterministic output only (no timing, no path)")
    args = ap.parse_args(argv)
    if not (MIN_W <= args.w <= MAX_W):
        ap.error(f"w must be in [{MIN_W}, {MAX_W}]")
    if args.n < 0:
        ap.error("n must be >= 0")
    if args.n > MAX_N:
        ap.error(f"n exceeds the supported maximum ({MAX_N})")

    t0 = time.time()
    bits, xend = orbit_bits(args.n, w=args.w)
    t1 = time.time()
    if not args.no_bits:
        with open(args.out, "wb") as fh:
            fh.write(bits)
    st = stats(bits)
    if args.quiet:
        print(f"n={st['n']} w={args.w} "
              f"sha256={hashlib.sha256(bits).hexdigest()}")
        print(f"E={st['E']} H={st['H']} A={st['A']} gsum={st['gsum']}")
        print(f"x_end_bits={xend.bit_length()} "
              f"x_end_sha256={hashlib.sha256(format(xend, 'x').encode()).hexdigest()}")
        for k in sorted(st["H_dyadic"]):
            print(f"H(2^{k})={st['H_dyadic'][k]}")
        print(f"block_drawdown_8={st['block_drawdown_8']} "
              f"(peak block {st['dd_peak_block']}, trough block {st['dd_trough_block']})")
        return 0
    print(f"n={st['n']} w={args.w} bits={args.out} "
          f"x_end_bits={xend.bit_length()} walk_s={t1 - t0:.1f}")
    print(f"sha256={hashlib.sha256(bits).hexdigest()}")
    print(f"E={st['E']} H={st['H']} A={st['A']} gsum={st['gsum']}")
    for k in sorted(st["H_dyadic"]):
        print(f"H(2^{k})={st['H_dyadic'][k]}")
    print(f"block_drawdown_8={st['block_drawdown_8']} "
          f"(peak block {st['dd_peak_block']}, trough block {st['dd_trough_block']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
