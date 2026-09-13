# Runden-Auswertung (deskriptiv)

- Lauf: 2026-09-13T13:06:23 · Modell: deepseek-flash · Arme: ['C0', 'C1', 'H'] · reps: 2 · max_repairs: 2
- Tier-A-Set: v11-a-0.3 sha256 eb294ea93235e19c…
- Tier-B-Set: v11-b-0.3 sha256 a1fcac5e4c6ae568…

| Arm-Tier | n | R0 gelöst | R0-Rate | Formfehler-Läufe R0 | Final gelöst | Final-Rate (95%-CI) | repariert | Trigger-Läufe | Reparaturgewinn | Runden bis ok (0..max/offen) | #xx-Auflösung | Tokens gesamt | Tokens/Treffer | Zeit gesamt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C0-A | 4 | 4 | 1.0 | 0 | 4 | 1.0 (0.51–1.00) | 0 | 0 | +0.0 pp | 4/0/0/0 | 0/0 | 2143 | 535.8 | 10.4s |
| C0-B | 4 | 4 | 1.0 | 0 | 4 | 1.0 (0.51–1.00) | 0 | 0 | +0.0 pp | 4/0/0/0 | 0/0 | 12937 | 3234.2 | 59.1s |
| C1-A | 4 | 3 | 0.75 | 1 | 4 | 1.0 (0.51–1.00) | 1 | 1 | +25.0 pp | 3/1/0/0 | 0/0 | 6984 | 1746.0 | 30.8s |
| C1-B | 4 | 4 | 1.0 | 0 | 4 | 1.0 (0.51–1.00) | 0 | 0 | +0.0 pp | 4/0/0/0 | 0/0 | 12360 | 3090.0 | 59.1s |
| H-A | 4 | 4 | 1.0 | 0 | 4 | 1.0 (0.51–1.00) | 0 | 0 | +0.0 pp | 4/0/0/0 | 0/0 | 4601 | 1150.2 | 20.7s |
| H-B | 4 | 4 | 1.0 | 0 | 4 | 1.0 (0.51–1.00) | 0 | 0 | +0.0 pp | 4/0/0/0 | 0/0 | 40580 | 10145.0 | 197.6s |

Hinweise: `repariert` = R0 nicht gelöst, final gelöst; `Trigger-Läufe` = Läufe, in denen mindestens eine Runde den Trigger `end_state_not_confirmed` trug (Erfolg und Trigger sind getrennte Begriffe; Läufe ohne Trigger-Feld — V11 und V12 — zählen 0); `Reparaturgewinn` = Differenz in Prozentpunkten über n; `Runden bis ok` zählt die Buckets 0..max in Ordnung, dann die offenen Läufe; `#xx-Auflösung` = Anteil der in Runde r refutierten ids, die in Runde r+1 nicht mehr refutiert sind; `Tokens` = completion über alle Runden (enthaelt reasoning). Keine Signifikanzaussagen.