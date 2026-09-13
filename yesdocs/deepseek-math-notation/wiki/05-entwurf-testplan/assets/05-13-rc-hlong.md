# RC-Fidelity der Denkspur (Metrik h, deskriptiv)

- Wurzel: .yesmem/tmp/runs/20260913-131245 · Modell: deepseek-flash

| Arm-Tier | Runden | RC da | Tag-Zeilen ø | Notation-Zeilen ø | Notation-Zeichen ø (Proxy) | Reasoning-Tokens Σ | Ø/Runde | leere Tags | Loops (extra) | Prosa-Lauf max ø | Draft-Block ø |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C0-B | 4 | 4 | 0.0106 | 0.0154 | 0.0057 | 152467 | 38116.8 | 0 | 0 | 956.5 | 0.0 |
| C1-B | 2 | 2 | 0.0369 | 0.0542 | 0.0139 | 60446 | 30223.0 | 0 | 0 | 709.5 | 0.0 |
| H-B | 2 | 2 | 0.0184 | 0.0258 | 0.0092 | 50313 | 25156.5 | 0 | 0 | 806.0 | 0.0 |

Hinweise: `Tag-Zeilen` = (Tag- + v-Zeilen)/Zeilen (Metrik h); `Notation-Zeichen` ist der dokumentierte Zeichen-Proxy fuer den Token-Anteil (kein lokaler Tokenizer; unterschaetzt die Notation); `Draft-Block` = zusammenhaengender Notations-/Claim-Block am RC-Ende (Blatt-Entwurf inkl. CLAIM/WITNESS/[HALT]). Keine Signifikanzaussagen.