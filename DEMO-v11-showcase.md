# DEMO v1.1-Denk-Sprache — B3-0005, Arm D (Zeugenpflicht)

**Zweck.** Live-Demonstration der V1.1-Denk-Sprache gegen die lokale
Modell-Instanz (`deepseek-flash`, direkter Proxy `localhost:9099/v1/chat/completions`).
Ein echter Lauf auf Aufgabe **B3-0005** aus `tier_b_v11-b-0.3.json`
(sha256 `a1fcac5e4c6ae568dc17a4cd56928eaba7d7949ec94760d02281b1e5d3c1c51f`)
— eine **Zyklus-Aufgabe ohne vorgegebenes Zertifikat**: t1, t2 und d muss das
Modell selbst aus dem Lauf bestimmen.

- Lauf: `20260912-230013` → `.yesmem/tmp/runs/20260912-230013/B3-0005/D-rep1/` (gitignoriert; `round0/` mit `prompt.md`, `raw.json`, `parsed.json`, `sheet.msheet`)
- Arm **D** = V1.1 + Zeugenpflicht je =-Konsequenz + Verdikt-Rueckkanal; rep 1, max-repairs 2
- Ergebnis: **Runde 0 bestaetigt** — 0 Reparaturrunden, 0 Transport-Retries

## Aufgaben-Prompt (user, verbatim)

```text
### AUFGABE
Die 2-Symbol-Turingmaschine in bbchallenge-Notation lautet: 0LA0LA. Start: Zustand A, Kopf auf Position 0, leeres Band; R = Kopf nach rechts, L = Kopf nach links, Z = Halt. Untersuche den Lauf: Halte er an, oder laeuft die Maschine in einen Translationszyklus? Bestimme im Zyklusfall die Werte t1, t2 und d selbst.
Formuliere h1: M zyklisch (Translation), bestimme die Zykluswerte t1, t2 und d selbst aus dem Lauf und verifiziere mit "v h1: cyc(<t1>,<t2>,<d>)" mit deinen Werten; setze h1+, wiederhole den Gegenstand als CLAIM c1: M zyklisch (Translation) und belege ihn mit WITNESS c1: ref h1; Ende: [HALT] c1.
```

System-Legende: `LEGEND_D` aus `yesdocs/deepseek-math-notation/tooling/prompts.py`
(V1.1-Zeichensprache, Zeugen `auto/py/range/ref/sim/cyc`, Zeugenpflicht:
"Jede =-Konsequenz traegt ein v"). Das Zertifikat `[0,1,-1]` des Sets steht
nirgends im Prompt — `certificate_given=false` liefert nur das Muster mit
Platzhaltern.

## Das Blatt (verbatim, Runden-0-Artefakt des Modells)

```text
g: Lauf von M: halt oder Translation?
a: M = 0LA0LA
h1: M zyklisch (Translation)
v h1: cyc(0,1,-1)
h1+
CLAIM c1: M zyklisch (Translation)
WITNESS c1: ref h1
[HALT] c1
```

## Verdikte (ausschliesslich vom Runner)

```
#ok: v1 c1
```

| Zeile | Verdikt | Details |
|---|---|---|
| v1 (`cyc`-Zeuge) | **CONFIRMED** | `cyc(0,1,-1)` — Translation t1=0 → t2=1, Versatz d=-1, maschinenverifiziert gegen die Maschine (`claimtypes.cycle`) |
| c1 (`ref h1`) | **CONFIRMED** | "ref h1: carries + and its check was ok" |
| `machine_bound` | **true** | das Blatt rechnet ueber M = 0LA0LA |
| `format_errors` | **0** | — |

## Doppelbeleg: msheet-CLI

Dieselbe Blatt-Datei durch `python3 -m bemyself.msheet run <blatt>`:

```
#ok: v1 c1
exit=0
```

Beide Wege — Harness-Auswertung und eigenstaendige CLI — liefern dasselbe
Verdikt.

## Lauf-Kennzahlen

| Kennzahl | Wert |
|---|---|
| Dauer (ein Modell-Aufruf) | 43,28 s |
| prompt_tokens | 1068 (Cache-Hit 896) |
| completion_tokens | 9417, davon **reasoning 9340** (99,2 %) |
| Blatt-Umfang | 166 Zeichen (8 Zeilen, keine Prosa) |
| finish_reason | stop |
| Reparaturrunden / Retries | 0 / 0 |

## Zertifikat: gefunden vs. Bauzeit-Gold

| | t1 | t2 | d |
|---|---|---|---|
| Gefunden (Modell, im Runden-0-Blatt) | 0 | 1 | -1 |
| Bauzeit-Gold (Set, per `cycle.check` verifiziert) | 0 | 1 | -1 |

Identisch. Der Lauf ist bestaetigt, ohne dass ein Referenzwert im Prompt stand.

## Reasoning-Ausschnitt (`reasoning_content`, gekuerzt)

Kopf — das Modell erschliesst die Notation selbst:

```text
Machine: "0LA0LA". Need parse bbchallenge notation. ... For state A: 0LA for symbol 0, 0LA for symbol 1?
For symbol 0: "0LA": write 0, move L, next state A. ...
So machine just writes 0 (no change), moves left, stays A, for both symbols. ... It will move left forever,
tape all zeros, no halt. Is this a translation cycle?
```

Ende — die Vorzeichen-Frage bei d wird explizit ausdiskutiert, bevor das Blatt
geschrieben wird:

```text
If you check C(t2) = shift(C(t1), d), then d sign matters. ... So signed is necessary.
Thus d=-1.
```

## Einordnung

Das Blatt ist vollstaendig maschinenverifiziert: jede Zeile traegt ein Verdikt,
das Zertifikat wurde selbst gefunden statt abgeschrieben, und die Zeugenpflicht
ist nicht kosmetisch (v1 haengt am `cyc`-Zeugen, c1 per `ref` an der
bestaetigten Zeile — eine erfundene Zahl bekaeme `#xx`). Bemerkenswert ist die
Arbeitsteilung: 99 % der Tokens liegen im unsichtbaren Reasoning, das sichtbare
Blatt hat acht Zeilen ohne ein Wort Prosa. Und die Rueckkanal-Runde blieb
ungenutzt: Runde 0 war auf Anhieb bestaetigt.
