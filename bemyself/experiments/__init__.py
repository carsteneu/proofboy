"""Bounded, deterministic experiments over the bemyself package.

Each experiment is a module with its own ``__main__`` entry: it recomputes a
finite window of a mathematical statement and prints the canonical result on
stdout. A ``[COMPUTE]`` claim pins command, commit and the SHA-256 of that
stdout, so a reported run becomes checkable without new verifier code.
"""
