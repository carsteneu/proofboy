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

# V1.1-Lexeme (05-07-denksprache-v1.1.md §§2–7): Kandidaten, deren Tokenpreis
# die Sonde entscheidet (D3: Sonden-pflichtige Lexik). Gruppenweise gemessen,
# damit der Messbericht 01-03b sie direkt übernehmen kann.
V11_LEXEME = {
    "Potenz und Knuth-Pfeile (§5)": [
        "^", "**", "^^", "^^^", "2^3", "2**3", "2^^3", "2^^^3",
        "2^127-1", "2**127-1", "2^^127-1", "2^^^5",
    ],
    "2-Zeichen-Aliase (§5), allein und im Aufruf": [
        "ip", "st", "mx", "pm", "gc", "dv", "di", "fc", "ch", "fb",
        "st(27)", "ip(97)", "mx(27)", "pm(2,10,1000)", "gc(12,18)",
        "dv(28)", "di(3,12)", "fc(5)", "ch(10,3)", "fb(100)",
        "st(27)=111", "(st(27)=111)", "st(n)", "d: st(n)=Schritte bis 1",
    ],
    "Langformen im Vergleich (V1-Bibliothek)": [
        "collatz_steps(27)", "isprime(97)", "collatz_max(27)", "powmod(2,10,1000)",
        "gcd(12,18)", "divisors(28)", "divides(3,12)", "factorial(5)",
        "choose(10,3)", "fib(100)",
    ],
    "Quantoren- und Zähl-Kandidaten (§5)": [
        "∀", "∃", "ex", "ex n", "ex(n)", "ex n in 1..100", "(ex n in 1..100: ...)",
        "forall n in 1..100", "(forall n in 1..100: ...)",
        "#(", "#(dv(28))", "#dv(28)", "|dv(28)|", "count(dv(28))",
    ],
    "Zeilen-Opcodes (§2, Kopfzeilen)": [
        "g:", "g: st(27)?", "d:", "a:", "a: n=27", "c:", "c: n+1 -> n", "h:", "q:",
        "=:", "=: st(27)=111 (h2+)", "h1:", "h2:", "h12:", "v h1:", "v h2: auto",
        "g: st(27)?; M haltet?", "d: st(n) = Schritte bis 1",
    ],
    "Status-Suffixe (§3)": [
        "h1+", "h2-", "h3?", "h4!", "+", "-", "?", "!",
    ],
    "Trace-Formen (§6)": [
        "x^k", "a^5", "a^5 b^12 c", "cp 0: (A,0,1101)", "cp 100: (C,3,1101)",
        "seg 0..100", "sim(0..100)", "sim(0..2**40)", "cyc(6,16,2)", "^5", "0^3 1^4",
    ],
    "Behauptungszone V1 (§2, wörtlich V1)": [
        "CLAIM c1: (st(27)=111)", "WITNESS c1: auto", "WITNESS c2: py: st(27)==111",
        "[HALT] c1 c2", "ref h1", "WITNESS c1: ref h1", "range n in 1..100:",
    ],
    "Verdikt-Appendix (§4)": [
        "#ok: v1 v2", "#xx: v3", "#?: v4", "#ok: v1 v3", "#xx: v2",
    ],
    "Kompaktstil (§5, Leerraum)": [
        "st(27)=111", "st(27) = 111", "(st(27)=111) ", "h1:st(27)=111", "h1: st(27)=111",
        "=: st(27)=111 (h2+)", "=:st(27)=111(h2+)",
    ],
    "Trace-Formen kompakt (Zusatz Sonde)": [
        "cp0:(A,0,1101)", "cp 0:(A,0,1101)", "cp0: (A,0,1101)", "cp0:(A,0,1101)",
        "cp100:(C,3,1101)", "seg0..100", "sim0..100", "cyc6,16,2",
        "->", "→", "=>",
        "#ok:v1 v2", "#ok: v1 v2", "#ok:v1", "#xx:v2", "#?:v4",
    ],
}


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
    for group, entries in V11_LEXEME.items():
        print(f"\n## V1.1: {group}")
        for s in entries:
            show(tok, s)
    print("\n## V1.1: Beispielzeilen (05-07 §9, wörtlich)")
    for s in (
        "g: M haltet?; st(27)?",
        "d: st(n) = Schritte bis 1 (V1-Bibliothek)",
        "a: M = 44394115",
        "h1: M zyklisch (Translation)",
        "v h1: cyc(6,16,2)",
        "h1+",
        "=: M kein Holdout (h1+)",
        "a: n=27",
        "h2: st(27)=111",
        "v h2: auto",
        "h2+",
        "=: st(27)=111 (h2+)",
        "#ok: v1 v2",
    ):
        show(tok, s)


if __name__ == "__main__":
    main()
