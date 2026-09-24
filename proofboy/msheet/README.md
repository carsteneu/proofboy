# msheet — die Denk-Sprache V1.1, ausführbar

Dieses Paket ist die laufende Seite der Notation aus
`yesdocs/deepseek-math-notation/wiki/05-entwurf-testplan/05-02-notations-spezifikation.md`
(V1) und `05-07-denksprache-v1.1.md` (V1.1). Es liest ein **Blatt** (eine
Modell-Antwort) in drei Zonen, führt die Zeugen aus und schreibt die
Verdikte — die Verdikte schreibt **nur der Runner**, niemals das Modell.

```
python3 -m proofboy.msheet run tests/data/beispielblatt.msheet
python3 -m proofboy.msheet run blatt.msheet --json --sandbox require
```

Die drei Zonen eines Blatts:

- **Denkzone** — Zeilen mit striktem Kopf `<tag><n>:` (Tags `g d a c h q =`
  und die V1-Zeilen `S<n>:`); der Rumpf ist frei. `c:` allein eröffnet einen
  Zahlenkolonnen-Block (V1-`calc`-Regeln).
- **Status-Register** — append-only Mini-Zeilen `h1+`, `h2-`, `h3?`, `h4!`.
  Der **letzte** Marker zählt.
- **Behauptungszone** — `CLAIM c1: <formel>`, `WITNESS c1: <zeuge>`,
  `[HALT] c1 c2`; hier gilt die volle V1-Grammatik.

Der Runner gibt den Verdikt-Appendix aus: `#ok: v1 v2`, `#xx: v3`, `#?: v4`
(ok/xx/? = CONFIRMED/REFUTED/UNVERIFIABLE). `--json` liefert pro Zeile
zusätzlich den Grund.

## Zeugen

| Zeuge | Bedeutung |
|---|---|
| `auto` | Der Zielrumpf wird als V1-Formel kompiliert und ausgewertet. |
| `py: <ausdruck>` | Python-Ausdruck mit der V1-Bibliothek, in einem isolierten Subprozess (optional unter `bwrap`, siehe `--sandbox`). Nur `True` = ok. |
| `range n in a..b: <formel>` | Explizite endliche Allaussage. |
| `ref <id>` | Promotion: nur wenn `<id>` zuletzt `+` trägt **und** die letzte Prüfung ok war; sonst UNVERIFIABLE `ref_unconfirmed`. |
| `sim(a..b)` | Checkpoints des Ziels (`cp t: (Q,p,T)`) gegen die Referenz-Simulation (`proofboy.turing`). Der Checkpoint-Tape steht für das **beschriebene Fenster** (von der ersten links- bis zur letzten rechts-beschriebenen Zelle; Kopfposition absolut). |
| `cyc(t1,t2,d)` | Translationszyklus-Zertifikat, geprüft durch die bestehende `[CYCLE]`-Maschinerie. |

`sim`/`cyc` lösen ihre Maschine über die Bindungen des Blatts auf
(`a: M = <machine>`): per Namensnennung im Zielrumpf, sonst über die einzige
Bindung.

**Doktrin:** CONFIRMED nur bei exakter Prüfung. Guard-Verletzung, Timeout,
unparsbarer Rumpf, leerer Quantorbereich (`empty_range`) und nicht erreichte
Checkpoints sind UNVERIFIABLE — nie eine stille Näherung.

## Module

| Modul | Inhalt |
|---|---|
| `library.py` | Die V1-Bibliothek: exakte Ganzzahlfunktionen mit dokumentierten Guards; zehn 2-Zeichen-Aliase (`st`, `ip`, `gc`, …). |
| `formula.py` | Das V1-Formelfragment: Lexer, Parser, Auswerter. Voll geklammert, exakt (`/` → `Fraction`), endliche Quantoren. |
| `witnesses.py` | Die Zeugen-Registry (`WITNESS_KINDS`) und ihre Ausführung. |
| `_pyexec.py` | Sandbox-Executor für `py:`-Ausdrücke (JSON-Protokoll, CPU-/Speicher-Limits). |
| `sheet.py` | Der Blatt-Parser (Denkzone, Status, Behauptungszone); sammelt Formatfehler statt zu werfen. |
| `runner.py` | Ausführung eines Blatts zu Verdikten, Appendix und JSON. |

## Einen neuen Zeugen-Typ hinzufügen

Ein Zeuge ist ein Paar aus **Recognizer** (welcher Text ist dieser Zeuge?)
und **Executor** (was heißt es, ihn auszuführen?) plus **einer Zeile** in der
Registry. Beispiel: ein Zeuge `haltsteps(n)`, der nachrechnet, dass die
gebundene Maschine nach genau `n` Schritten hält.

```python
import re
from proofboy import turing
from proofboy.model import Verdict
from proofboy.msheet.witnesses import WitnessKind, WitnessResult, WitnessSpec

def parse_haltsteps(text):
    match = re.match(r"\Ahaltsteps\(([0-9]+)\)\Z", text.strip())
    if match is None:
        return None
    return WitnessSpec("haltsteps", {"steps": match.group(1)})

def execute_haltsteps(spec, target_body, ctx, *, tolerant=False):
    machine, error = None, "no machine binding"
    if ctx.machines:
        machine = next(iter(ctx.machines.values()))  # oder Auswahl nach Name
    if machine is None:
        return WitnessResult(Verdict.UNVERIFIABLE, f"haltsteps: {error}")
    claimed = int(spec.parts["steps"])
    outcome = turing.run(machine, claimed + 1)
    if outcome.halts and outcome.steps == claimed:
        return WitnessResult(Verdict.CONFIRMED, f"halted after exactly {claimed} steps")
    return WitnessResult(Verdict.REFUTED, f"halts={outcome.halts} steps={outcome.steps}")

HALTSTEPS = WitnessKind("haltsteps", parse_haltsteps, execute_haltsteps)
```

Registrierung — eine Zeile, entweder in die Registry des Pakets oder (für
Experimente) als zusätzlicher Eintrag:

```python
from proofboy.msheet import witnesses
witnesses.WITNESS_KINDS = witnesses.WITNESS_KINDS + (HALTSTEPS,)
```

Test-Vorbild (läuft den ganzen Pfad ab):
`tests/test_msheet_witnesses.py::RegistryTest::test_a_new_kind_is_one_recognizer_plus_one_executor`.

Beim Bau echter neuer Zeugen gilt dieselbe Ehrlichkeitsregel: kein
CONFIRMED ohne exakte Prüfung; alles Unsichere wird UNVERIFIABLE mit Grund.

## Eine neue Bibliotheksfunktion hinzufügen

1. Funktion in `library.py` mit Guard (Grenze werfen, nie nähern).
2. Eintrag in `LIBRARY`; braucht sie einen Alias, eine Zeile in `ALIASES`.
3. Tests in `tests/test_msheet_library.py` (Wert + Guard-Fall).

## Grenzen (ehrlich)

- `py:`-Ausdrücke laufen als Subprozess mit Zeit-Limit; die Ausgabe ist als
  ein JSON-Objekt (`kind`: bool|nonbool|error) spezifiziert.
- **Sandbox-Ehrlichkeit:** Die eingeschränkten Builtins sind *kein*
  Containment — Attributzugriff auf Bibliotheks-Funktionen erreicht die echten
  Builtins (`isprime.__globals__["__builtins__"]...`). Containment leistet
  allein `bwrap`. Ohne `bwrap` läuft `--sandbox auto` unsandboxed **mit
  Warnung auf stderr**; für fremde Blätter `--sandbox require` verwenden
  (verweigert die Ausführung ohne bwrap).
- **Rechen-Grenzen:** `RANGE_GUARD` = 10^6 Elemente je Quantor (10^7 dauerte
  Sekunden bis Minuten — Review-Messung 2026-09-12); `POWER_GUARD` = 10^6,
  für beide Exponenten-Vorzeichen; `sim(a..b)` ist auf `halt_limit`
  begrenzt (Default `DEFAULT_HALT_LIMIT`); `sum`/`prod` und geschachtelte
  Quantoren multiplizieren die Arbeit — mehrere große Bereiche in einem
  Blatt können den Lauf dennoch lange beschäftigen (kein Wall-Clock-Timeout
  im In-Process-Pfad).
- Unbeschränkte Quantoren (`Z`/`N`/`Q`) sind `UNVERIFIABLE`
  (`unbounded_claim`) — auf dieser Maschine nicht ausführbar.
- Der `sim`-Checkpoint vergleicht das beschriebene Fenster **exakt** (bis auf
  führende/nachfolgende Nullen, wertgleich); eine abweichende
  Fensterkonvention des Modells ist ein REFUTED, kein Verziehen.
- Sprachdetails, die dokumentiert (nicht versteckt) sind: `|`/`&` werten
  kurzschließend aus; unäres Minus bindet stärker als der folgende Operator
  (`(- 2 ^ 2)` = 4); `True`/`False` sind reservierte Wörter, aber keine
  auswertbaren Literale der formalen Sprache.
