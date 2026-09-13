# Runden-Auswertung (deskriptiv)

- Lauf: 2026-09-13T13:12:45 · Modell: deepseek-flash · Arme: ['C0', 'C1', 'H'] · reps: 1 · max_repairs: 2
- Tier-A-Set: v11-a-0.3 sha256 eb294ea93235e19c…
- Tier-B-Set: v11-b-0.3 sha256 a1fcac5e4c6ae568…

| Arm-Tier | n | R0 gelöst | R0-Rate | Formfehler-Läufe R0 | Final gelöst | Final-Rate (95%-CI) | repariert | Trigger-Läufe | Reparaturgewinn | Runden bis ok (0..max/offen) | #xx-Auflösung | Tokens gesamt | Tokens/Treffer | Zeit gesamt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C0-B | 2 | 1 | 0.5 | 0 | 1 | 0.5 (0.09–0.91) | 0 | 1 | +0.0 pp | 1/0/0/1 | 7/7 | 153849 | 153849.0 | 491.4s |
| C1-B | 2 | 2 | 1.0 | 0 | 2 | 1.0 (0.34–1.00) | 0 | 0 | +0.0 pp | 2/0/0/0 | 0/0 | 61210 | 30605.0 | 185.4s |
| H-B | 2 | 2 | 1.0 | 0 | 2 | 1.0 (0.34–1.00) | 0 | 0 | +0.0 pp | 2/0/0/0 | 0/0 | 51131 | 25565.5 | 165.8s |

Hinweise: `repariert` = R0 nicht gelöst, final gelöst; `Trigger-Läufe` = Läufe, in denen mindestens eine Runde den Trigger `end_state_not_confirmed` trug (Erfolg und Trigger sind getrennte Begriffe; Läufe ohne Trigger-Feld — V11 und V12 — zählen 0); `Reparaturgewinn` = Differenz in Prozentpunkten über n; `Runden bis ok` zählt die Buckets 0..max in Ordnung, dann die offenen Läufe; `#xx-Auflösung` = Anteil der in Runde r refutierten ids, die in Runde r+1 nicht mehr refutiert sind; `Tokens` = completion über alle Runden (enthaelt reasoning). Keine Signifikanzaussagen.