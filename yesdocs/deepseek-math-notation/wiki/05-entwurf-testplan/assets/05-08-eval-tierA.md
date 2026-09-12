# Pilot-Auswertung V1.1 (deskriptiv)

- Lauf: 2026-09-12T16:39:29 · Modell: deepseek-flash · Arme: ['K', 'B', 'C'] · reps: 2
- Tier-A-Set: v11-a-0.1 sha256 50c985e169aa5007…
- Tier-B-Set: v11-b-0.1 sha256 074ab6bf5ebfc213…

| Arm-Tier | n | gelöst | Rate (95%-CI Wilson) | Dauer ø | completion ø | reasoning ø | Formfehler-Blätter | bestätigt/refutiert/unprüfbar | Marker-Treue | Trace-CPs |
|---|---|---|---|---|---|---|---|---|---|---|
| B-A | 32 | 29 | 0.9062 (0.76–0.97) | 6.9s | 1834.9 | 1682.4 | 0 | 29/0/3 | 0.9954 | 0/0 |
| C-A | 32 | 27 | 0.8438 (0.68–0.93) | 4.9s | 1262.2 | 1197.9 | 0 | 54/0/10 | 1.0 | 0/0 |
| K-A | 32 | 32 | 1.0 (0.89–1.00) | 4.0s | 1061.8 | 1054.8 | 0 | 0/0/0 | None | 0/0 |

Hinweise: `Trace-CPs` zählt exakt getroffene Gold-Checkpoints über alle Trace-Läufe des Arms. „refutiert“ ist der Falschbestätigungs-Proxy (metrik e-Entsprechung). Keine Signifikanzaussagen.