# Runden-Auswertung (deskriptiv)

- Lauf: 2026-09-12T20:46:13 · Modell: deepseek-flash · Arme: ['K', 'B', 'C'] · reps: 2 · max_repairs: 2
- Tier-A-Set: v11-a-0.3 sha256 eb294ea93235e19c…
- Tier-B-Set: v11-b-0.3 sha256 a1fcac5e4c6ae568…

| Arm-Tier | n | R0 gelöst | R0-Rate | Formfehler-Läufe R0 | Final gelöst | Final-Rate (95%-CI) | repariert | Trigger-Läufe | Reparaturgewinn | Runden bis ok (0..max/offen) | #xx-Auflösung | Tokens gesamt | Tokens/Treffer | Zeit gesamt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B-A | 32 | 32 | 1.0 | 0 | 32 | 1.0 (0.89–1.00) | 0 | 0 | +0.0 pp | 32/0/0/0 | 0/0 | 148658 | 4645.6 | 516.6s |
| C-A | 32 | 32 | 1.0 | 0 | 32 | 1.0 (0.89–1.00) | 0 | 0 | +0.0 pp | 32/0/0/0 | 0/0 | 157088 | 4909.0 | 524.7s |
| K-A | 32 | 32 | 1.0 | 0 | 32 | 1.0 (0.89–1.00) | 0 | 0 | +0.0 pp | 32/0/0/0 | 0/0 | 116724 | 3647.6 | 384.3s |

Hinweise: `repariert` = R0 nicht gelöst, final gelöst; `Trigger-Läufe` = Läufe, in denen mindestens eine Runde den Trigger `end_state_not_confirmed` trug (Erfolg und Trigger sind getrennte Begriffe; Läufe ohne Trigger-Feld — V11 und V12 — zählen 0); `Reparaturgewinn` = Differenz in Prozentpunkten über n; `Runden bis ok` zählt die Buckets 0..max in Ordnung, dann die offenen Läufe; `#xx-Auflösung` = Anteil der in Runde r refutierten ids, die in Runde r+1 nicht mehr refutiert sind; `Tokens` = completion über alle Runden (enthaelt reasoning). Keine Signifikanzaussagen.