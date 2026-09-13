# Runden-Auswertung (deskriptiv)

- Lauf: 2026-09-13T09:35:41 · Modell: deepseek-flash · Arme: ['C0', 'C1', 'C2'] · reps: 2 · max_repairs: 2
- Tier-A-Set: v11-a-0.3 sha256 eb294ea93235e19c…
- Tier-B-Set: v11-b-0.3 sha256 a1fcac5e4c6ae568…

| Arm-Tier | n | R0 gelöst | R0-Rate | Formfehler-Läufe R0 | Final gelöst | Final-Rate (95%-CI) | repariert | Trigger-Läufe | Reparaturgewinn | Runden bis ok (0..max/offen) | #xx-Auflösung | Tokens gesamt | Tokens/Treffer | Zeit gesamt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C0-A | 8 | 8 | 1.0 | 0 | 8 | 1.0 (0.68–1.00) | 0 | 0 | +0.0 pp | 8/0/0/0 | 0/0 | 6796 | 849.5 | 33.5s |
| C1-A | 8 | 8 | 1.0 | 2 | 8 | 1.0 (0.68–1.00) | 0 | 0 | +0.0 pp | 8/0/0/0 | 0/0 | 9904 | 1238.0 | 44.9s |
| C2-A | 8 | 7 | 0.875 | 0 | 8 | 1.0 (0.68–1.00) | 1 | 1 | +12.5 pp | 7/1/0/0 | 0/0 | 14246 | 1780.8 | 61.1s |

Hinweise: `repariert` = R0 nicht gelöst, final gelöst; `Trigger-Läufe` = Läufe, in denen mindestens eine Runde den Trigger `end_state_not_confirmed` trug (Erfolg und Trigger sind getrennte Begriffe; Läufe ohne Trigger-Feld — V11 und V12 — zählen 0); `Reparaturgewinn` = Differenz in Prozentpunkten über n; `Runden bis ok` zählt die Buckets 0..max in Ordnung, dann die offenen Läufe; `#xx-Auflösung` = Anteil der in Runde r refutierten ids, die in Runde r+1 nicht mehr refutiert sind; `Tokens` = completion über alle Runden (enthaelt reasoning). Keine Signifikanzaussagen.