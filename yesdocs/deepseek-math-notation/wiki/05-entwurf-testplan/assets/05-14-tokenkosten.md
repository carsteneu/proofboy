# Token-Kosten-Sonde V18: Lean-Zeile vs. V1.1-Zeile vs. Prosa-Zeile

- tokenizer.json SHA-256 `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b` · 10 Zeilen-Tripel

| Zeile | lean | v1.1 | prosa | lean/prosa | v1.1/prosa |
|---|---|---|---|---|---|
| sum-klein | 15 | 8 | 6 | 2.5 | 1.333 |
| sum-gross | 25 | 18 | 22 | 1.136 | 0.818 |
| produkt | 15 | 8 | 8 | 1.875 | 1.0 |
| modulo | 20 | 11 | 15 | 1.333 | 0.733 |
| teilbarkeit | 16 | 8 | 5 | 3.2 | 1.6 |
| forall-null | 23 | 13 | 13 | 1.769 | 1.0 |
| forall-schranke | 22 | 13 | 9 | 2.444 | 1.444 |
| liste-summe | 23 | 9 | 11 | 2.091 | 0.818 |
| trace-checkpoint | 15 | 15 | 21 | 0.714 | 0.714 |
| zyklus | 17 | 13 | 24 | 0.708 | 0.542 |
| **Σ** | **191** | **116** | **134** | **1.425** | **0.866** |

Hinweise: je Zeile dieselbe Aussage in drei Stilen; Lean-Zeilen sind Std-Formen, Trace-/Zyklus-Zeilen eine Kommentar-Skizze (kein Std-Aequivalent); gemessen ohne BOS/Serving-Kontext. Deskriptiv, keine Signifikanzaussagen.