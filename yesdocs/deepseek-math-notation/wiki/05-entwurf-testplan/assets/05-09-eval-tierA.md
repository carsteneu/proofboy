# Runden-Auswertung V12 (deskriptiv)

- Lauf: 2026-09-12T19:02:57 · Modell: deepseek-flash · Arme: ['K', 'B', 'C', 'D'] · reps: 2 · max_repairs: 2
- Tier-A-Set: v11-a-0.2 sha256 007424292fd10129…
- Tier-B-Set: v11-b-0.2 sha256 68eb917ebd26ae2d…

| Arm-Tier | n | R0 gelöst | R0-Rate | Formfehler-Läufe R0 | Final gelöst | Final-Rate (95%-CI) | repariert | Reparaturgewinn | Runden bis ok (0..max/offen) | #xx-Auflösung | Tokens gesamt | Tokens/Treffer | Zeit gesamt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B-A | 32 | 31 | 0.9688 | 0 | 32 | 1.0 (0.89–1.00) | 1 | +3.1 pp | 31/1/0/0 | 0/0 | 72204 | 2256.4 | 272.9s |
| C-A | 32 | 32 | 1.0 | 0 | 32 | 1.0 (0.89–1.00) | 0 | +0.0 pp | 32/0/0/0 | 0/0 | 46774 | 1461.7 | 175.1s |
| D-A | 32 | 32 | 1.0 | 0 | 32 | 1.0 (0.89–1.00) | 0 | +0.0 pp | 32/0/0/0 | 0/0 | 46971 | 1467.8 | 171.7s |
| K-A | 32 | 32 | 1.0 | 0 | 32 | 1.0 (0.89–1.00) | 0 | +0.0 pp | 32/0/0/0 | 0/0 | 25667 | 802.1 | 97.5s |

Hinweise: `repariert` = R0 nicht gelöst, final gelöst; `Reparaturgewinn` = Differenz in Prozentpunkten über n; `Runden bis ok` zählt die Buckets 0..max in Ordnung, dann die offenen Läufe; `#xx-Auflösung` = Anteil der in Runde r refutierten ids, die in Runde r+1 nicht mehr refutiert sind; `Tokens` = completion über alle Runden (enthaelt reasoning). Keine Signifikanzaussagen.