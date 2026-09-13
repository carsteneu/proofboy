# RC-Fidelity der Denkspur (Metrik h, deskriptiv)

- Wurzel: .yesmem/tmp/runs/20260913-130623 · Modell: deepseek-flash

| Arm-Tier | Runden | RC da | Tag-Zeilen ø | Notation-Zeilen ø | Notation-Zeichen ø (Proxy) | Reasoning-Tokens Σ | Ø/Runde | leere Tags | Loops (extra) | Prosa-Lauf max ø | Draft-Block ø |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C0-A | 4 | 4 | 0.1632 | 0.2268 | 0.0873 | 1767 | 441.8 | 0 | 0 | 9.25 | 0.0 |
| C0-B | 4 | 4 | 0.2355 | 0.2948 | 0.0617 | 12623 | 3155.8 | 0 | 0 | 13.0 | 0.0 |
| C1-A | 5 | 5 | 0.2503 | 0.3007 | 0.2059 | 6284 | 1256.8 | 0 | 0 | 19.8 | 1.6 |
| C1-B | 4 | 4 | 0.2146 | 0.2682 | 0.0415 | 12043 | 3010.8 | 0 | 0 | 13.5 | 0.0 |
| H-A | 4 | 4 | 0.1968 | 0.2524 | 0.0938 | 4197 | 1049.2 | 0 | 0 | 10.5 | 0.0 |
| H-B | 4 | 4 | 0.266 | 0.313 | 0.0587 | 40111 | 10027.8 | 0 | 0 | 23.75 | 0.0 |

Hinweise: `Tag-Zeilen` = (Tag- + v-Zeilen)/Zeilen (Metrik h); `Notation-Zeichen` ist der dokumentierte Zeichen-Proxy fuer den Token-Anteil (kein lokaler Tokenizer; unterschaetzt die Notation); `Draft-Block` = zusammenhaengender Notations-/Claim-Block am RC-Ende (Blatt-Entwurf inkl. CLAIM/WITNESS/[HALT]). Keine Signifikanzaussagen.