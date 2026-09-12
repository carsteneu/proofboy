# Erdős–Straus bis N — Experiment-Artefakt

Modul: `bemyself/experiments/erdos_straus.py` (Python-3-stdlib,
deterministisch, kein Netz, kein stdin; Doku: README, Abschnitt "Experimente").

Kommando: `python3 -m bemyself.experiments.erdos_straus 1000000`
sha256(stdout): `e5b68dd1818d89f2c66d0e7b5a68bf906dbe7adc77c64dba015bf27058a4f89d`
Ausgabe: 46.906.788 Bytes. Laufzeit auf der Entwicklungsmaschine: Modul ~14 s,
Pruefer-Gegenlauf (frischer Checkout + bwrap + Lauf) ~15 s.

Aussage: Fuer jedes `n` von 2 bis 1.000.000 steht ein expliziter Zeuge
`(a, b, c)` -- das lexikografisch kleinste Tripel mit
`4/n = 1/a + 1/b + 1/c` -- in der deterministischen Ausgabe. Das ist endlich
verifiziert bis 1.000.000, kein Beweis der Vermutung: does not prove the
conjecture (ueber `n > 1.000.000` sagt der Lauf nichts).

Nachrechnung: das Paar `[COMMIT: <Branch-HEAD>]` +
`[COMPUTE: <Kommando> -> <sha256>]` steht im Artefakt-Report des Zweigs
(ungetrackt unter `.yesmem/tmp/`, wie bei den bisherigen Artefakten) und wird
geprueft mit
`python3 -m bemyself check --report <artefakt> --repo . --sandbox require --strict`
-> CONFIRMED (commit_exists, compute), Exit 0.
