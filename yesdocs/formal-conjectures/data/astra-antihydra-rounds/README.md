# Astra-Rohdaten — Antihydra-Lemma-Loop, Runden 1-18

Rohantworten des externen Modells `gpt-6-astra` (Reasoning-Effort `high`) aus
dem Lemma-Loop vom 2026-09-13/14, wie empfangen und unter `/tmp/opencode`
gespeichert (keine Nachbearbeitung; der Antworttext steht in
`choices[0].message.content`, `usage` und `model` im jeweiligen JSON).

Es existieren 17 der 18 Antwortdateien; `astra-antihydra-r2.json` wurde nie
gespeichert. Die Dateien sind das Beweismaterial des Loops: Jede im Bericht
zitierte Astra-Aussage stammt aus einer dieser Antworten (und jede davon
wurde ihrerseits endlich nachgerechnet — siehe `attack-02.md` §2/§3).

| Datei | Empfangen (2026-09-13/14) | Inhalt (Kurzform) |
|---|---|---|
| `astra-antihydra-r1.json` | 18:55 | R1: Regel-Hypothese H; Kandidat D (Vier-Block-Dichte); Kandidat V (2-adisch); Bijektions-Lemma + Halt-Familie |
| `astra-antihydra-r3.json` | 19:01 | R3: Lean-tauglicher Beweis der Halt-Familie; Skalenidentität; Negativsatz feste Modul-Tabellen |
| `astra-antihydra-r4.json` | 21:31 | R4: Antwort auf den (W)-Widerlegungsbefund; Reduktion der Erhaltungs-Ungleichung auf Residuen-Vermeidung |
| `astra-antihydra-r5.json` | 21:41 | R5: Rückzug (W); Schranke aus einseitigem D−; Rückkehrargument-Grenze |
| `astra-antihydra-r6.json` | 21:46 | R6: Korrektur normierte Verluste; D− allein ⇒ lineare Barriere; Seed 53348 |
| `astra-antihydra-r7.json` | 22:11 | R7: Zwei-Skalen-Bedingung (P) ⇒ Barriere (bewiesen); Route (R) Run-Balance |
| `astra-antihydra-r8.json` | 22:26 | R8: Route (R): H-Reserve-Lemma (dyadische Gewinne/Defizite + Seed) |
| `astra-antihydra-r9.json` | 22:44 | R9: Zertifikat (k0=12, a=2/5, b=1/256); Kompositionsregeln G/D |
| `astra-antihydra-r10.json` | 22:54 | R10: (G,D,m)-Tabelle k≤21; Vorhersage H(2^22)=2091252 |
| `astra-antihydra-r11.json` | 23:20 | R11: Carry-Plan w=8, Tabellen R(r,s)/C(r,s); Graph-/Potential-Plan |
| `astra-antihydra-r12.json` | 23:32 | R12: Negativbefund 2-Byte-Graph (unbeschränkt); Bitte um Tests am beobachteten Graphen |
| `astra-antihydra-r13.json` | 23:37 | R13: Bewertung des 2-Byte-Tods; Drei-Byte-Diagnose; Reserve-Dynamik D_{k+1}=max(0,D_k−w_k) |
| `astra-antihydra-r14.json` | 23:46 | R14: Korrektur minimale Potentialbreite = maximale Wegdefizite; 73-Exakttest-Rezept; 74-Zustands-Produktgraph |
| `astra-antihydra-r15.json` | 23:58 | R15: Gap 92 vs 73; konstruktive Verfeinerung (r,s,t,D) mit Breite exakt 73; präzise offene Aussage |
| `astra-antihydra-r16.json` | 00:13 (09-14) | R16: präzises Minimalziel (D−)/(P); (P) strikt schwächer; probabilistisches Haar-Theorem; Budgetbedingung (S) |
| `astra-antihydra-r17.json` | 00:17 (09-14) | R17: algebraischer Defektvektor (R^16); Kriterium für eine geschlossene Defektrekursion |
| `astra-antihydra-r18.json` | 00:23 (09-14) | R18: exakte Carry-Rekursion; Paritätswort-Bijektion; Vier-Skalen-Rekursion; Nicht-Abgeschlossenheit; Endbilanz |

Die korrespondierenden Verifikationsläufe (`R2` … `R18`, unser Teil) stehen als
Protokoll in der Conveyor-Seite `bemyself-conveyor` (2026-09-13/14, Einträge
18:58–00:23) und verdichtet in `attack-02.md`. Digests aller Dateien:
`data/attack-02-check.txt`.
