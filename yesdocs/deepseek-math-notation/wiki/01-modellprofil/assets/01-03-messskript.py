#!/usr/bin/env python3
"""Tokenisierungs-Messskript zu 01-03-tokenizer-zahlen.md.

Reproduziert die im Artikel genannten Messwerte mit dem offiziellen
DeepSeek-V4.1-Flash-Tokenizer (tokenizer.json aus HF-Repo oder
deepseek_v4_tokenizer.zip von cdn.deepseek.com).

Aufruf:
    python3 01-03-messskript.py <pfad/zu/tokenizer.json>

Abhängigkeit: tokenizers >= 0.20, Python 3.12.
"""
import sys

from tokenizers import Tokenizer

TABLE = [
    # (Eingabe, Kontext) — Tabellenstichprobe Abbildung 1
    "7", "42", "123", "1234", "123456", "1234567890",
    "1234567890123456", "3.14159", "0.000001", "1e-6",
    "2**127-1", "x^2+2*x-1=0", "x^2 + 2x - 1 = 0",
    "\\frac{1}{2}", "∀ε>0∃δ>0", "√2", "≤", "∃", "⊂",
]

NUMSYMS = [
    "-17", "1/2", "1e308", "10^6", "1,000,000", "1 000 000",
    "+", "-", "=", "^", "**", "*x",
    "123456789012345678901234567890",
    "1" * 45,
]

BAUSTEINE = [
    "x_1", "x_{12}", "a_{i,j}", "\\vec{v}", "\\hat{x}",
    "\\sum_{i=1}^{n}", "\\int_0^1", "(a,b)", "[a,b]", "{a,b}",
    "\\mathbb{R}", "A^T", "A^{-1}", "\\frac{a}{b}",
]

SYMBOLE = list("∀∃¬∧∨→⇒↔≡⊢⊨∈∉⊂⊆∪∩∅ℝℕℤℚℂ≤≥≈∼±·×÷∂∇∫∮ℵℏαβγδελμσφωΩΔΘΣΠ")


def show(tok, s):
    e = tok.encode(s)
    toks = " · ".join(t.replace("Ġ", "␣") for t in e.tokens)
    print(f"{s!r:34} n={len(e.ids):2d}  {toks}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "tokenizer.json"
    tok = Tokenizer.from_file(path)
    print(f"# tokenizer: {path}")
    print(f"# vocab (get_vocab): {len(tok.get_vocab())}")
    print("\n## Tabellenstichprobe (Abbildung 1)")
    for s in TABLE:
        show(tok, s)
    print("\n## Zahlen und Operatoren")
    for s in NUMSYMS:
        show(tok, s)
    print("\n## Weitere Bausteine (Indizes, Klammern, LaTeX)")
    for s in BAUSTEINE:
        show(tok, s)
    print("\n## Unicode-Mathe-Symbole")
    for s in SYMBOLE:
        show(tok, s)


if __name__ == "__main__":
    main()
