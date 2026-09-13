# Latent-Lean-Smoke-Test (V18, deskriptiv)

- Sonden: 16 · valid 16 (1.0) · axiomfrei 13 · sorry 0 · invalid 0 · timeout 0 · ohne Code 0 · Transportfehler 0
- Tokens: reasoning 64620 · completion 65117 · Dauer 292.2 s

| Sonde | Aussage | Modell: Status | Axiome | Fehler (Auszug) |
|---|---|---|---|---|
| p01 | `2 + 2 = 4` | valid | none |  |
| p02 | `10 * 10 = 100` | valid | none |  |
| p03 | `29 * 31 = 899` | valid | none |  |
| p04 | `123456789 + 987654321 = 1111111110` | valid | ['main_thm._native.native_decide.ax_1_1'] |  |
| p05 | `837465291837 + 192837465564 = 1030302757401` | valid | none |  |
| p06 | `2 ^ 10 = 1024` | valid | none |  |
| p07 | `(2 ^ 10) % 7 = 2` | valid | ['main_thm._native.native_decide.ax_1_1'] |  |
| p08 | `7 * 11 * 13 = 1001` | valid | none |  |
| p09 | `Nat.gcd 12 18 = 6` | valid | ['main_thm._native.native_decide.ax_1_1'] |  |
| p10 | `[1,2,3].length = 3` | valid | none |  |
| p11 | `∀ n : Nat, n + 0 = n` | valid | none |  |
| p12 | `∀ n : Nat, 0 + n = n` | valid | none |  |
| p13 | `∀ n : Nat, n * 1 = n` | valid | none |  |
| p14 | `∀ a b : Nat, a + b = b + a` | valid | none |  |
| p15 | `∀ n : Nat, n < n + 1` | valid | none |  |
| p16 | `∀ n : Nat, 2 * n = n + n` | valid | none |  |

Hinweise: eine Sonde, eine Modellantwort, eine Elaboration (kein Reparaturpfad); `valid` = elaboriert fehlerfrei, `axiomfrei` = ohne Axiome (decide-Beweise), `propext/Quot.sound` gelten als Standard-Axiome (simp/omega). n klein, deskriptiv.