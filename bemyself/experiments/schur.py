"""Deterministic search for Schur colorings: find a k-coloring of 1..N
without a monochromatic solution of ``x + y = z``.

The search exists to produce *own-search* certificates for the small Schur
numbers S(k) (the largest N that admits a Schur coloring) where the values
are known -- S(1) = 1, S(2) = 4, S(3) = 13, S(4) = 44 -- so the evaluation
under ``yesdocs/schur/`` can be re-derived instead of quoted. A found
certificate is re-checked by the [COLORING] checker before it is used
anywhere; the search has no licence to fabricate one.

The algorithm is a backtracking tree search whose next decision is the
*most constrained* position: the smallest still uncolored number with the
fewest allowed colors (the number 1 is fixed to color 1 -- permuting colors
never changes whether a coloring is sum-free). A color is allowed for a
number p when no triple involving p is monochromatic: not with p as the
sum (``x + y = p``), not with p as a summand (``p + x = z``), and not
``p + p = 2p``. Each decision is one *node*; the budget counts nodes, so
two runs with the same arguments explore the exact same tree and return
the exact same certificate. There is no randomness and no seed: runs are
reproducible by construction.

Cost is empirical, not bounded: on the development machine (CPython,
stdlib only) the own-search certificates of S(1)..S(4) are found playing
15 nodes (N = 13) and 18,870 nodes (N = 44, about a second at the default
budget); the work per node grows with N and k, and N = 160 (the S(5)
certificate) was **not** found within 90 seconds, so the evaluation takes
that certificate from the literature ([Exoo], OEIS A030126/A045652)
instead. A budget-exhausted run prints ``none`` and exits non-zero: an
unfinished search claims nothing.

CLI: ``python3 -m bemyself.experiments.schur <k> <n> [--budget <nodes>]``
prints ``coloring k=<k> n=<n> nodes=<nodes> <digits>`` (exit 0) or
``none k=<k> n=<n> nodes=<nodes> budget=<budget>`` (exit 1); usage errors
exit 2.
"""

from __future__ import annotations

import sys

# The node budget without --budget: comfortably above what the documented
# own-search certificates need (18,870 nodes for S(4) = 44) and far below
# what would silently run for hours at larger N.
DEFAULT_MAX_NODES = 50_000

_USAGE = "usage: python3 -m bemyself.experiments.schur <k> <n> [--budget <nodes>]"


def _allowed(colors, p, color, n):
    """Whether ``color`` can go to ``p`` without forming a monochromatic
    triple: p as the sum, p as a summand, and p + p."""
    for x in range(1, p // 2 + 1):
        if colors[x] == color and colors[p - x] == color:
            return False
    for x in range(1, n - p + 1):
        if colors[x] == color and colors[p + x] == color:
            return False
    if 2 * p <= n and colors[2 * p] == color:
        return False
    return True


def _search(k, n, max_nodes):
    """MRV backtracking: the coloring digits, or None, plus the nodes played."""
    colors = [0] * (n + 1)
    colors[1] = 1
    nodes = 0

    def options(p):
        return [c for c in range(1, k + 1) if _allowed(colors, p, c, n)]

    def rec():
        nonlocal nodes
        best = None
        best_options = None
        for p in range(2, n + 1):
            if colors[p] == 0:
                opts = options(p)
                if best is None or len(opts) < len(best_options):
                    best, best_options = p, opts
                    if not opts:
                        # A number without any allowed color: dead end.
                        return False
        if best is None:
            return True
        nodes += 1
        if nodes >= max_nodes:
            # The budget is spent: stop, do not finish this branch.
            return False
        for color in best_options:
            colors[best] = color
            if rec():
                return True
            colors[best] = 0
        return False

    found = rec()
    digits = "".join(str(colors[i]) for i in range(1, n + 1)) if found else None
    return digits, nodes


def search(k, n, max_nodes=DEFAULT_MAX_NODES):
    """A Schur coloring of 1..n with k colors, or None within the budget.

    Deterministic: identical arguments give the identical result. Raises
    ValueError for a color count outside 1..9 or a length below 1.
    """
    if not 1 <= k <= 9:
        raise ValueError(f"k must be 1..9, got {k}")
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if max_nodes < 1:
        raise ValueError(f"max_nodes must be >= 1, got {max_nodes}")
    digits, _ = _search(k, n, max_nodes)
    return digits


def _parse_args(argv):
    """(k, n, budget) or None for a usage error."""
    positional = []
    budget = DEFAULT_MAX_NODES
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--budget":
            if index + 1 >= len(argv):
                return None
            text = argv[index + 1]
            if not (text.isascii() and text.isdigit()):
                return None
            budget = int(text)
            index += 2
            continue
        if arg.startswith("--"):
            return None
        positional.append(arg)
        index += 1
    if len(positional) != 2:
        return None
    k_text, n_text = positional
    if not (k_text.isascii() and k_text.isdigit()):
        return None
    if not (n_text.isascii() and n_text.isdigit()):
        return None
    return int(k_text), int(n_text), budget


def main(argv=None):
    """CLI: ``python3 -m bemyself.experiments.schur <k> <n> [--budget N]``."""
    args = list(sys.argv[1:] if argv is None else argv)
    parsed = _parse_args(args)
    if parsed is None:
        print(_USAGE, file=sys.stderr)
        return 2
    k, n, budget = parsed
    if not (1 <= k <= 9) or n < 1 or budget < 1:
        print(
            f"{_USAGE}: k must be 1..9, n >= 1, budget >= 1 "
            f"(got k={k}, n={n}, budget={budget})",
            file=sys.stderr,
        )
        return 2
    digits, nodes = _search(k, n, budget)
    if digits is None:
        print(f"none k={k} n={n} nodes={nodes} budget={budget}")
        return 1
    print(f"coloring k={k} n={n} nodes={nodes} {digits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
