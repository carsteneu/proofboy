# Runden-Auswertung V12 (deskriptiv)

- Lauf: 2026-09-12T18:25:06 · Modell: deepseek-flash · Arme: ['K', 'B', 'C', 'D'] · reps: 1 · max_repairs: 2
- Tier-A-Set: v11-a-0.2 sha256 007424292fd10129…
- Tier-B-Set: v11-b-0.2 sha256 68eb917ebd26ae2d…

| Arm-Tier | n | R0 gelöst | R0-Rate | Formfehler-Läufe R0 | Final gelöst | Final-Rate (95%-CI) | repariert | Reparaturgewinn | Runden bis ok (0..max/offen) | #xx-Auflösung | Tokens gesamt | Tokens/Treffer | Zeit gesamt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B-B | 12 | 12 | 1.0 | 10 | 12 | 1.0 (0.76–1.00) | 0 | +0.0 pp | 12/0/0/0 | 0/0 | 124690 | 10390.8 | 486.4s |
| C-B | 12 | 11 | 0.9167 | 0 | 12 | 1.0 (0.76–1.00) | 1 | +8.3 pp | 11/1/0/0 | 3/3 | 131924 | 10993.7 | 511.1s |
| D-B | 12 | 12 | 1.0 | 0 | 12 | 1.0 (0.76–1.00) | 0 | +0.0 pp | 12/0/0/0 | 0/0 | 94693 | 7891.1 | 380.6s |
| K-B | 12 | 11 | 0.9167 | 0 | 12 | 1.0 (0.76–1.00) | 1 | +8.3 pp | 11/1/0/0 | 0/0 | 107830 | 8985.8 | 439.5s |

Hinweise: `repariert` = R0 nicht gelöst, final gelöst; `Reparaturgewinn` = Differenz in Prozentpunkten über n; `Runden bis ok` zählt die Buckets 0..max in Ordnung, dann die offenen Läufe; `#xx-Auflösung` = Anteil der in Runde r refutierten ids, die in Runde r+1 nicht mehr refutiert sind; `Tokens` = completion über alle Runden (enthaelt reasoning). Keine Signifikanzaussagen.