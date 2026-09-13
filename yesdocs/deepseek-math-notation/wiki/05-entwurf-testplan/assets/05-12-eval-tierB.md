# Runden-Auswertung (deskriptiv)

- Lauf: 2026-09-13T09:40:57 · Modell: deepseek-flash · Arme: ['C0', 'C1', 'C2'] · reps: 1 · max_repairs: 2
- Tier-A-Set: v11-a-0.3 sha256 eb294ea93235e19c…
- Tier-B-Set: v11-b-0.3 sha256 a1fcac5e4c6ae568…

| Arm-Tier | n | R0 gelöst | R0-Rate | Formfehler-Läufe R0 | Final gelöst | Final-Rate (95%-CI) | repariert | Trigger-Läufe | Reparaturgewinn | Runden bis ok (0..max/offen) | #xx-Auflösung | Tokens gesamt | Tokens/Treffer | Zeit gesamt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C0-B | 8 | 7 | 0.875 | 0 | 8 | 1.0 (0.68–1.00) | 1 | 1 | +12.5 pp | 7/0/1/0 | 1/1 | 318876 | 39859.5 | 1129.8s |
| C1-B | 8 | 7 | 0.875 | 0 | 7 | 0.875 (0.53–0.98) | 0 | 1 | +0.0 pp | 7/0/0/1 | 0/0 | 234499 | 33499.9 | 1104.7s |
| C2-B | 8 | 6 | 0.75 | 0 | 8 | 1.0 (0.68–1.00) | 2 | 2 | +25.0 pp | 6/1/1/0 | 5/5 | 294317 | 36789.6 | 1045.0s |

Hinweise: `repariert` = R0 nicht gelöst, final gelöst; `Trigger-Läufe` = Läufe, in denen mindestens eine Runde den Trigger `end_state_not_confirmed` trug (Erfolg und Trigger sind getrennte Begriffe; Läufe ohne Trigger-Feld — V11 und V12 — zählen 0); `Reparaturgewinn` = Differenz in Prozentpunkten über n; `Runden bis ok` zählt die Buckets 0..max in Ordnung, dann die offenen Läufe; `#xx-Auflösung` = Anteil der in Runde r refutierten ids, die in Runde r+1 nicht mehr refutiert sind; `Tokens` = completion über alle Runden (enthaelt reasoning). Keine Signifikanzaussagen.