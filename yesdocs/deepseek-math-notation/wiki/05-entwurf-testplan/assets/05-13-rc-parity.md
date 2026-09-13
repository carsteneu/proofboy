# RC-Fidelity der Denkspur (Metrik h, deskriptiv)

- Wurzel: .yesmem/tmp/runs/20260913-125730 · Modell: deepseek-flash

| Arm-Tier | Runden | RC da | Tag-Zeilen ø | Notation-Zeilen ø | Notation-Zeichen ø (Proxy) | Reasoning-Tokens Σ | Ø/Runde | leere Tags | Loops (extra) | Prosa-Lauf max ø | Draft-Block ø |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1-A | 4 | 4 | 0.2473 | 0.3321 | 0.2141 | 2695 | 673.8 | 0 | 0 | 10.5 | 1.75 |
| C1-B | 5 | 5 | 0.0234 | 0.0313 | 0.0125 | 161138 | 32227.6 | 0 | 0 | 1012.6 | 0.0 |

Hinweise: `Tag-Zeilen` = (Tag- + v-Zeilen)/Zeilen (Metrik h); `Notation-Zeichen` ist der dokumentierte Zeichen-Proxy fuer den Token-Anteil (kein lokaler Tokenizer; unterschaetzt die Notation); `Draft-Block` = zusammenhaengender Notations-/Claim-Block am RC-Ende (Blatt-Entwurf inkl. CLAIM/WITNESS/[HALT]). Keine Signifikanzaussagen.