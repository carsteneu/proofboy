# RC-Fidelity der Denkspur (Metrik h, deskriptiv)

- Wurzel: .yesmem/tmp/runs/20260913-093541 · Modell: deepseek-flash

| Arm-Tier | Runden | RC da | Tag-Zeilen ø | Notation-Zeilen ø | Notation-Zeichen ø (Proxy) | Reasoning-Tokens Σ | Ø/Runde | leere Tags | Loops (extra) | Prosa-Lauf max ø | Draft-Block ø |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C0-A | 8 | 8 | 0.1354 | 0.1761 | 0.0867 | 6046 | 755.8 | 0 | 0 | 15.25 | 0.0 |
| C1-A | 8 | 8 | 0.211 | 0.2721 | 0.1155 | 8958 | 1119.8 | 0 | 0 | 16.625 | 0.75 |
| C2-A | 9 | 9 | 0.2588 | 0.3198 | 0.1778 | 13357 | 1484.1 | 0 | 0 | 19.6667 | 1.1111 |

Hinweise: `Tag-Zeilen` = (Tag- + v-Zeilen)/Zeilen (Metrik h); `Notation-Zeichen` ist der dokumentierte Zeichen-Proxy fuer den Token-Anteil (kein lokaler Tokenizer; unterschaetzt die Notation); `Draft-Block` = zusammenhaengender Notations-/Claim-Block am RC-Ende (Blatt-Entwurf inkl. CLAIM/WITNESS/[HALT]). Keine Signifikanzaussagen.