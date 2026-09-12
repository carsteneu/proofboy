# Pilot-Auswertung V1.1 (deskriptiv)

- Lauf: 2026-09-12T16:47:55 · Modell: deepseek-flash · Arme: ['K', 'B', 'C'] · reps: 1
- Tier-A-Set: v11-a-0.1 sha256 50c985e169aa5007…
- Tier-B-Set: v11-b-0.1 sha256 074ab6bf5ebfc213…

| Arm-Tier | n | gelöst | Rate (95%-CI Wilson) | Dauer ø | completion ø | reasoning ø | Formfehler-Blätter | bestätigt/refutiert/unprüfbar | Marker-Treue | Trace-CPs |
|---|---|---|---|---|---|---|---|---|---|---|
| B-B | 8 | 5 | 0.625 (0.31–0.86) | 71.0s | 17791.1 | 17711.5 | 6 | 0/0/0 | 1.0 | 13/20 |
| C-B | 8 | 3 | 0.375 (0.14–0.69) | 78.4s | 18671.6 | 18491.6 | 0 | 7/12/3 | 1.0 | 8/20 |
| K-B | 8 | 8 | 1.0 (0.68–1.00) | 34.2s | 8580.6 | 8548.1 | 0 | 0/0/0 | None | 20/20 |

Hinweise: `Trace-CPs` zählt exakt getroffene Gold-Checkpoints über alle Trace-Läufe des Arms. „refutiert“ ist der Falschbestätigungs-Proxy (metrik e-Entsprechung). Keine Signifikanzaussagen.