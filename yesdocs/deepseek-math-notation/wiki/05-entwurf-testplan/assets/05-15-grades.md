# Lean-Mandat-Matrix V19 (deskriptiv)

- Zellen: 105 · valid 94 (0.8952) · axiomfrei 88 · sorry 0 · invalid 6 · timeout 0 · infra 0 · ohne Code 5 (davon Transportfehler 0)
- Fences: 21 (0.2) · Prefill-Echo: 0 · Statement-Echo: 100
- Denkspur: Lean-Zeilen-Anteil ø 0.4664 · Taktik-Zeilen-Anteil ø 0.1408 · RC-Zeilen Σ 3638
- Tokens: reasoning 119052 · completion 122449 · Dauer 632.5 s

| Variante | Grad | n | valid | axiomfrei | sorry | Fence | Statement-Echo | RC-Lean ø | RC-Taktik ø | Reasoning-Tok | Completion-Tok |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V-A | trivial | 6 | 6 | 6 | 0 | 2 | 6 | 0.5154 | 0.1239 | 3347 | 3494 |
| V-A | mechanical | 6 | 4 | 3 | 0 | 0 | 4 | 0.3301 | 0.0552 | 12766 | 12880 |
| V-A | lemma | 9 | 8 | 5 | 0 | 1 | 8 | 0.4658 | 0.1886 | 12574 | 12863 |
| V-B | trivial | 6 | 6 | 6 | 0 | 3 | 6 | 0.486 | 0.0978 | 5360 | 5507 |
| V-B | mechanical | 6 | 6 | 6 | 0 | 1 | 6 | 0.5085 | 0.1599 | 6821 | 7006 |
| V-B | lemma | 9 | 9 | 9 | 0 | 5 | 9 | 0.4766 | 0.1991 | 9602 | 9921 |
| V-C | trivial | 6 | 6 | 6 | 0 | 1 | 6 | 0.4175 | 0.109 | 3107 | 3242 |
| V-C | mechanical | 6 | 4 | 4 | 0 | 0 | 5 | 0.4102 | 0.0905 | 10108 | 10254 |
| V-C | lemma | 9 | 7 | 7 | 0 | 5 | 8 | 0.4663 | 0.1944 | 15070 | 15432 |
| V-D | trivial | 6 | 6 | 6 | 0 | 0 | 6 | 0.5903 | 0.1748 | 4966 | 5106 |
| V-D | mechanical | 6 | 6 | 5 | 0 | 0 | 6 | 0.4486 | 0.0893 | 10404 | 10584 |
| V-D | lemma | 9 | 9 | 9 | 0 | 0 | 9 | 0.5138 | 0.1827 | 7746 | 8066 |
| V-E | trivial | 6 | 5 | 5 | 0 | 0 | 6 | 0.5693 | 0.0976 | 2508 | 2705 |
| V-E | mechanical | 6 | 5 | 4 | 0 | 1 | 6 | 0.3518 | 0.0816 | 7771 | 7955 |
| V-E | lemma | 9 | 7 | 7 | 0 | 2 | 9 | 0.4339 | 0.1587 | 6902 | 7434 |

| Variante | n | valid | axiomfrei | sorry | Fence | RC-Lean ø | RC-Taktik ø | Reasoning-Tok | Completion-Tok | Dauer s |
|---|---|---|---|---|---|---|---|---|---|---|
| V-A | 21 | 18 | 14 | 0 | 3 | 0.4412 | 0.132 | 28687 | 29237 | 147.4 |
| V-B | 21 | 21 | 21 | 0 | 9 | 0.4884 | 0.159 | 21783 | 22434 | 120.0 |
| V-C | 21 | 17 | 17 | 0 | 6 | 0.4363 | 0.1403 | 28285 | 28928 | 145.6 |
| V-D | 21 | 21 | 20 | 0 | 0 | 0.517 | 0.1537 | 23116 | 23756 | 118.4 |
| V-E | 21 | 17 | 16 | 0 | 3 | 0.4492 | 0.1192 | 17181 | 18094 | 101.0 |

Hinweise: `valid` = elaboriert fehlerfrei (`leancheck`, Std-Minimalprojekt, Lean 4.33.1); `axiomfrei` = ohne Axiome unter den validen Zellen (`propext`/`Quot.sound` zaehlen nicht als axiomfrei); `Fence` = Antwort enthielt einen Markdown-Code-Zaun; `RC-Lean`/`RC-Taktik` sind die heuristischen `leanfidelity`-Anteile der Denkspur (Untergrenze bzw. ueberschaetzend bei zitierten Code-Zeilen in Prosa — Augenschein-Stichprobe im Bericht); n klein, keine Signifikanz.