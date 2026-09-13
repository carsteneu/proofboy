# Sauberkeits-Runde V16: Direkt-Transport, Proxy-Kontamination und der Zwangsprompt-Arm H

> Lauf: 2026-09-13, 12:42–13:50 (63 Läufe) · Modell: `deepseek-flash` (direkt,
> api.deepseek.com) bzw. `privateTomMax` (Cluster, llm.ccm19.app) · Arme: C0,
> C1, H · Sets: v0.3 · Rohdaten: `.yesmem/tmp/runs-v16-20260913/` ·
> Begleit-Assets: `assets/05-13-*.md`.

## 1. Auftrag und Kernfrage

Drei Fragen der V16-Runde, alle drei empirisch, keine Modelländerung:

1. **Sauberkeit des Transports:** V11–V15 liefen über den lokalen YesMem-Proxy
   (Port 9099). Was davon ist *Kontamination* — also etwas, das nicht der
   Arm-Prompt bzw. der Modellaufruf selbst ist? Direkt gegen
   `api.deepseek.com` gemessen, mit drei Bedingungen: `proxy` (wie bisher),
   `direct` (gleiche Parameter) und `direct-parity` (Parameter ans tatsächliche
   Proxy-Verhalten angeglichen).
2. **Zwangsprompt (Arm H):** Bewegt ein *knallharter* Prompt — Marker im Stil
   der Session-Reminder, jede Prosa-Zeile als Formfehler mit Konsequenz — die
   Denkspur stärker als die höfliche Instruktion (C1) aus V15?
3. **Cross-Modell:** Erster Datenpunkt gegen `privateTomMax` auf dem Cluster
   (llm.ccm19.app) — eine ganz andere Modellfamilie als `deepseek-flash`.

## 2. Was gebaut wurde

- **Transport-Layer im Harness** (`tooling/harness.py`): ENV
  `BEMYSELF_TARGET=proxy|deepseek|cluster` wählt Endpoint und Modell;
  `BEMYSELF_MAX_TOKENS` (Default 8192) und `BEMYSELF_REASONING_EFFORT`
  (Default: Feld wird nicht gesendet) steuern den Request-Body. Keys kommen
  aus `~/.local/share/opencode/auth.json` (`deepseek` bzw. `gateway`);
  das Lauf-Manifest dokumentiert den Transport als Objekt
  `{target, url, model, max_tokens, reasoning_effort}` — ohne Key und ohne
  Zugangsdaten aus der URL. Hinweis: `manifest["transport"]` war bis V15 ein
  String (`"proxy-9099"`) und ist jetzt ein Objekt; der Wert `max_tokens` im
  Manifest ist der *gesendete* Wert (über den Proxy ohne Wirkung, s. §5.1).
- **Arm H** (`tooling/prompts.py`): `FORCE_BLOCK` auf `LEGEND_C`;
  Antwortkonventionen und der maschinelle Reparatur-Rückkanal bleiben
  identisch zu C. `H` ist in `MACHINE_FEEDBACK_ARMS` und im Trace-Eval-Pfad.
- **Tests** (`tests/test_v16_transport.py`, `tests/test_v16_force_arm.py`):
  TDD, Default-Target `proxy` bleibt rückwärts-kompatibel; Guard-Tests u. a.
  gegen Key-Leaks in Fehlermeldung und Manifest. Volle Suite: 917 Tests grün.

## 3. Design-Entscheidungen

### 3.1 Drei-Bedingungen-Design statt „Proxy aus, fertig"

Der Vergleich `proxy` vs. `direct` mischt zwei Dinge: den Transportweg *und*
das vom Proxy veränderte Parameterset. Die dritte Bedingung
`direct-parity` (mt=65536, effort=max — am Proxy-Verhalten orientiert)
isoliert den Transportweg; `direct` (mt=8192, kein effort) ist dagegen die
„nackte" Direktbedingung, wie sie ein Nutzer ohne Proxy fahren würde.

### 3.2 H erbt die C-Konventionen vollständig

H soll testen, was *Zwang* bewegt, nicht was ein anderer Antwortvertrag
bewegt. Deshalb: C-Legende als Präfix, identische Antwortinstruktionen,
identischer Rückkanal. Einziger Delta: `FORCE_BLOCK` (Marker MANDATORY /
ATTENTION / DU MUSST / SUPER WICHTIG, Formfehler-Konsequenz, kurzes Beispiel).

### 3.3 Kein Gold-Leak im H-Prompt

Für die Nicht-Vorgabe-Aufgaben (B3-0005/06/08) darf das Zertifikat nicht im
Prompt stehen; Guard-Test `test_no_certificate_gold_in_h_prompt` prüft die
verbotenen Zeichenketten.

## 4. Protokoll und Läufe

| Strang | Bedingung | Arme | Aufgaben | reps | Läufe | Ordner |
|---|---|---|---|---|---|---|
| Kontamination | `proxy` (mt=8192, kein effort) | C1 | A3-0016, A3-0001, B3-0001, B3-0004 | 2 | 8 | `20260913-124209` |
| Kontamination | `direct` (mt=8192, kein effort) | C1 | dieselben | 2 | 8 | `20260913-125200` |
| Kontamination | `direct-parity` (mt=65536, effort=max) | C1 | dieselben | 2 | 8 | `20260913-125730` |
| H-Matrix | `direct` (mt=65536, effort=max) | C0, C1, H | A3-0016, A3-0001, B3-0005, B3-0007 | 2 | 24 | `20260913-130623` |
| H-Matrix | `direct` (mt=65536, effort=max) | C0, C1, H | B3-0001, B3-0004 | 1 | 6 | `20260913-131245` |
| Cross-Modell | `cluster` (mt=65536, kein effort) | C1, H | A3-0016, A3-0001, B3-0007, B3-0001 | 1 | 8 (+1 Smoke) | `20260913-132653`, `20260913-132723` |

## 5. Ergebnisse

### 5.1 Der Hauptfund (Transport): Über den Proxy war das Output-Limit wirkungslos

Beim Angleich der Bedingungen (Phase 1) zeigte sich: Der YesMem-Proxy
übersetzt im OpenAI-Pfad `max_tokens` nach `max_completion_tokens`
(`internal/proxy/openai_reverse.go`, seit 2026-07-15) — und DeepSeek
**ignoriert `max_completion_tokens`** (live verifiziert: mt=16 erzeugt 26
Tokens, kein Effekt). Über den Proxy lief also jedes V11–V15-Generat
limitlos; `finish_reason=length` gab es nie. Direkt wirkt `max_tokens` hart:
`mt=16 → 16 Tokens, finish=length`.

Konsequenz für die Läufe (T1):

| Bedingung | Läufe | solved | Runden | comp Tokens Σ | RC Tokens Σ | finish=length |
|---|---|---|---|---|---|---|
| `proxy` (mt=8192, kein effort) | 8 | **8** | 9 | 179 147 | 176 606 | **0** |
| `direct` (mt=8192, kein effort) | 8 | **4** | 16 | 99 008 | 98 170 | **11** |
| `direct-parity` (mt=65536, effort=max) | 8 | **8** | 9 | 166 303 | 163 833 | **0** |

Mit dem real wirksamen 8192er-Limit scheitern alle vier langen Zellen
(B3-0001, B3-0004; je 3 Runden × 8192 Tokens = exakt abgeschnitten,
Rohbeleg: `round0/raw.json` → `completion_tokens=8192`, `finish_reason=length`).
Die kurzen A-Zellen laufen unverändert durch. **Das heißt rückwirkend: Die
V11–V15-Ergebnisse sind transport-seitig gültig** (die Prompts kamen
unverändert an, s. u.), aber die dort berichteten Token-/Kostenzahlen sind
*limitlose* Zahlen — „8192er-Limit" war nie eine wirksame Bedingung.

### 5.2 Kontamination Input: null bei diesen Requests

Der Proxy hat einen Skip-Pfad für „non-interactive" Requests (seit
2026-05-08): keine Briefing-/Disziplin-Injektionen, `reasoning_effort=max`
ausgenommen. Nachgemessen mit dem echten A3-0001/C1-Prompt: `prompt_tokens`
identisch (1060 direkt == 1060 über den Proxy). Die message-basierten
Injektionen des OpenAI-Pfads sind zudem seit 2026-05-12 deaktiviert
(`openai_parity.go`, „DISABLED: cache-incompatible injections"). Damit ist
die Prompt-Kontamination der V11–V15-Läufe empirisch ausgeschlossen; die
einzige Injektion ist der Parameter `reasoning_effort=max` (seit
2026-09-12).

### 5.3 Proxy vs. Direct-parity: gleiche Lösungslage, kein systematischer RC-Richtungseffekt

Beide Bedingungen lösen alle 8 Läufe. Bei den RC-Tokens je Aufgabe (2 reps):
A3-0016 −1 154, A3-0001 −1 857, B3-0001 −19 397, B3-0004 **+9 635** — in
Summe −12 773 Tokens (176 606 → 163 833), also rund 7 % auf niedrigem n, mit
gemischten Vorzeichen. Die RC-Tag-Anteile (C1-B) liegen nahe beieinander
(0,0285 proxy vs. 0,0234 parity). Lesart: Der Transportweg allein verschiebt
die Denkspur nicht erkennbar; die Effekte sind zell- und zufallsgetrieben.

### 5.4 Arm H: Zwang bewegt kurze Zellen — lange Traces bleiben Prosa

H-Matrix (direct, mt=65536, effort=max; 30 Läufe):

| Arm | solved | RC Tokens Σ | Tag-Zeilen ø (Tier A) | Notation-Zeichen ø (A) | Prosa-Lauf max ø (Tier B) |
|---|---|---|---|---|---|
| C0 | 9/10 | 166 857 | 0,1632 | 0,0873 | 484,8 |
| C1 | 10/10 | 78 773 | 0,2503 | 0,2059 | 361,5 |
| H | 10/10 | 94 621 | 0,1968 | 0,0938 | 414,9 |

- **Kurze Zellen:** In der Zyklus-Zelle B3-0005 zog H enorm an
  (rep1: 28 552 RC-Tokens und Tag-Anteil 0,4113; rep2: 10 161/0,1637) —
  gegenüber C0 (6 679/4 954) und C1 (4 901/5 417). Über die A-Zellen hinweg
  liegt C1 bei Tag- und Notation-Anteil allerdings vorn (0,2503/0,2059 vs.
  0,1968/0,0938). **H schlägt C1 nicht systematisch; der Effekt ist Zelle
  für Zelle verschieden** — die stärkste Einzelzelle der Runde ist aber eine
  H-Zelle.
- **Lange Traces (B3-0001, B3-0004):** Tag-Anteile 0,0106/0,0369/0,0184
  (C0/C1/H), Prosa-Läufe von 709–957 Zeilen am Stück. **Kein Arm bewegt die
  Proton-Prosa der langen Denkspur messbar** — das verallgemeinert den
  V15-Befund („Instruction-only bewegt kurze Zellen") von der Instruktion
  auf den expliziten Zwang.
- **Kosten/Solve:** C0 scheiterte bei B3-0001 nach 3 Runden und 127 815
  Tokens (der einzige Fehlschlag der Matrix); C1 und H je 10/10.

Fußnoten: Die Spalte „Prosa-Lauf max ø" mittelt die Ordnermittel der beiden
B-Läufe (hshort/hlong), nicht laufgewichtet. Die im `FORCE_BLOCK` angedrohte
Sanktion („Prosa-Zeile → Aufgabe gilt als NICHT gelöst") ist eine rhetorische
Intervention: Der Harness wertet Formatfehler nur als Rückkanal-Material, nie
als Fehlschlag — geprüft wurden also die *Texteffekte*, nicht die angedrohte
Konsequenz.

### 5.5 Cross-Modell: `privateTomMax` (Cluster)

- Alle 8 Läufe solved (H brauchte 2× eine Reparatur-Runde, C1 nie).
- Die API liefert `reasoning_content`, aber **keine**
  `completion_tokens_details.reasoning_tokens` — die RC-Token-Metrik fehlt;
  auswertbar ist der Text (Tag-Anteile). Tag-Anteile: C1 0,1366/0,1026
  (A/B), H 0,3009/0,0380. H zeigt auch hier in der kurzen A-Zelle den
  höheren Tag-Anteil — bei drei A-Runden (inkl. Reparaturen).
- Latenz deutlich höher als direkt (B3-0001: 280 s C1, 334 s H; direkt:
  88–121 s). Erster Datenpunkt, keine Verallgemeinerung.

## 6. Was belegt ist — und was nicht

**Belegt:**

- Über den Proxy war `max_tokens` ab 2026-07-15 wirkungslos
  (Code-Pfad + Live-Test + Läufe: 11× `finish=length` bei `direct` mt=8192,
  0× über den Proxy).
- Input-Injektion in non-interactive Requests: gemessen 0 Prompt-Token-Delta.
- `reasoning_effort=max` wurde in alle Proxy-Läufe injiziert (ab 2026-09-12).
- H bewegt die Denkspur zellweise stark (B3-0005: 5–7× RC-Menge), aber
  nicht systematisch über alle Zellen; lange Traces bleiben in jedem Arm
  Prosa.
- Der Transport-Layer (Target, Modell, Limits, effort, Manifest) ist
  getestet (16+12 Tests) und lief in allen 63 Läufen.

**Nicht belegt / Grenzen:**

- n = 1–2 je Zelle; keine Signifikanzaussagen, alle Vergleiche deskriptiv.
- Der isolierte Effekt von `reasoning_effort=max` vs. kein effort wurde
  nicht getrennt vermessen (die Sonden mt=16 zeigten keinen Unterschied,
  aber das ist keine Zelle der Matrix).
- Der Cluster-Datenpunkt ist von ganz anderer Modellfamilie; Vergleiche
  deepseek-flash ↔ privateTomMax sind keine Arm-Ergebnisse im engen Sinn.
- Bekannte, seit V12 akzeptierte Grenze: `urllib` reicht den
  `Authorization`-Header bei Redirects auch cross-origin weiter; unter dem
  hiesigen Bedrohungsmodell (https-Ziele, lokaler Proxy) nicht ausnutzbar.

## 7. Offene Punkte (Kandidaten für die nächste Runde)

1. **Effort-Zelle:** 2×2-Zerlegung (mt hoch/niedrig × effort an/aus) auf
   denselben Zellen — Budget war knapp für die saubere Zerlegung.
2. **Reps erhöhen** für B3-0005 (der H-Ausreißer ist mit n=2 nicht zu
   bewerten) und für den Cluster-Datenpunkt.
3. **RC-Nachweis am Cluster:** Falls privateTomMax RC-Metriken liefern soll,
   braucht es eine Länge-Messung aus dem Text (RC-Zeichen) als Ersatz-Metrik
   — in dieser Runde bewusst nicht gebaut.
4. **Harness-Konsequenz:** Default `max_tokens` im Direktpfad auf hohen Wert
   (z. B. 65536) stellen oder das Limit aus den Sets ableiten — 8192 ist
   für lange Traces real zu knapp (4/8 Fehlschläge).

## Quellen

1. Lokale Messung (2026-09-13): 63 Läufe in `.yesmem/tmp/runs/` (Ordner
   `20260913-124209` [proxy], `-125200` [direct 8192], `-125730`
   [direct-parity], `-130623`/`-131245` [H-Matrix], `-132653`/`-132723`
   [Cluster]), gesichert unter `.yesmem/tmp/runs-v16-20260913/`; Auswertung
   `analyze16.py` + `report-data.json` in `.yesmem/tmp/v16-logs/`; Sonden zu
   Limit/Injektion: `probe_transport.py` + `probe_transport.log`; Assets
   [05-13-rc-proxy.md](assets/05-13-rc-proxy.md),
   [05-13-rc-parity.md](assets/05-13-rc-parity.md),
   [05-13-rc-hshort.md](assets/05-13-rc-hshort.md),
   [05-13-rc-hlong.md](assets/05-13-rc-hlong.md),
   [05-13-eval-hshort.md](assets/05-13-eval-hshort.md),
   [05-13-eval-hlong.md](assets/05-13-eval-hlong.md),
   [05-13-eval-cluster.md](assets/05-13-eval-cluster.md).
2. [05-12-rc-umstellung-v15.md](05-12-rc-umstellung-v15.md) — V15-Baseline
   (RC-Fidelity-Metrik, Arme C0/C1/C2, Prefill-Grenze).
3. YesMem-Proxy-Code: `internal/proxy/openai_reverse.go`
   (max_tokens→max_completion_tokens, Commit f41499f4, 2026-07-15),
   `internal/proxy/reasoning_effort.go` + `internal/config/config.go`
   (Effort-Injektion, Commit 637b1066, 2026-09-12),
   `internal/proxy/openai_handler.go` (non-interactive Skip, Commit
   7642f31d, 2026-05-08), `internal/proxy/openai_parity.go`
   (DISABLED-Block, Commit f337c0db, 2026-05-12).
4. Implementierung + Tests V16: `tooling/harness.py`, `tooling/prompts.py`,
   `tests/test_v16_transport.py`, `tests/test_v16_force_arm.py`
   (917 Tests grün, 28 neu).
5. [05-04-test-harness.md](05-04-test-harness.md) — Harness-Spezifikation
   (Transport, Sets, Artefakt-Regeln).
6. [05-07-denksprache-v1.1.md](05-07-denksprache-v1.1.md) — Denk-Sprache
   V1.1 (Tag-Formen, gemessen als Metrik h).
