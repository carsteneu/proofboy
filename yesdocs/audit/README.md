# Audit: Platzhalter-Rauschen in den Worker-Sections (P15)

Dieses Verzeichnis haelt den Vorher/Nachher-Vergleich des P15-Audits fest:
Seit P15 gilt der Rumpf eines Markers, der einen Platzhalter traegt
(`<hash>`, `<machine>`, `...`/`…`, `TODO`), nicht mehr als Behauptung — die
Zeile wird ignoriert statt als `unpruefbar` gemeldet (Regel:
[README](../../README.md), Abschnitt "Grenzen", und [SPEC](../../SPEC.md),
Abschnitt "Eingabe").

## Kommando (wiederholbar)

Das Skript [`audit_sections.py`](audit_sections.py) fuehrt `bemyself check`
ueber die 13 Worker-Sections der Yesloop-Kette (p1, p3–p14) und ueber eine
Exit-Code-Matrix mit echten Werten. Es laeuft fuer jeden Stand aus dem
jeweiligen Code-Checkout:

```
# Stand VORHER (Basis b85de12, in einem Wegwerf-Worktree):
git worktree add .yesmem/tmp/audit-base b85de12
python3 yesdocs/audit/audit_sections.py --checkout .yesmem/tmp/audit-base
git worktree remove .yesmem/tmp/audit-base --force

# Stand NACHHER (dieser HEAD):
python3 yesdocs/audit/audit_sections.py
```

Die Sektions-Baselines (je `--base`) sind die Regressions-Baselines, die die
Sections selbst in ihren Phase-4-Bloecken dokumentieren; `p3` nennt in seiner
Meldung die Basis `7c7392c`, `p1` dokumentiert keine und laeuft ohne `--base`.
Die Sections werden ausschliesslich lesend aus der YesMem-Scratchpad-DB
gelesen (`--project /home/carsten/projects/bemyself`). Laeuft eine Section in
einen Fehler (kein lesbares JSON), zaehlt sie nicht als null Claims: das
Skript listet die Fehllaeufe am Ende und endet mit Exit 1.

## Ergebnis der Sections (13 Worker)

| Section | vorher C/R/U | nachher C/R/U |
|---|---|---|
| yesloop-bemyself-p1-verifier | 0 / 0 / 0 | 0 / 0 / 0 |
| yesloop-bemyself-p3-eval | 0 / 0 / 1 | 0 / 0 / 1 |
| yesloop-bemyself-p4-cli | 4 / 0 / 9 | 4 / 0 / 9 |
| yesloop-bemyself-p5-strict | 1 / 1 / 3 | 1 / 1 / 3 |
| yesloop-bemyself-p6-sandbox | 0 / 0 / 5 | 0 / 0 / **4** |
| yesloop-bemyself-p7-halt | 0 / 0 / 5 | 0 / 0 / **3** |
| yesloop-bemyself-p8-repo-optional | 2 / 0 / 3 | 2 / 0 / 3 |
| yesloop-bemyself-p9-compute | 4 / 0 / 0 | 4 / 0 / 0 |
| yesloop-bemyself-p10-cycle | 3 / 0 / 0 | 3 / 0 / 0 |
| yesloop-bemyself-p11-erdos-straus | 4 / 0 / 12 | 4 / 0 / **10** |
| yesloop-bemyself-p12-ident | 1 / 0 / 6 | 1 / 0 / **4** |
| yesloop-bemyself-p13-schur | 0 / 0 / 8 | 0 / 0 / **4** |
| yesloop-bemyself-p14-merge-artifact | 0 / 0 / 25 | 0 / 0 / **13** |
| **Summe** | **19 / 1 / 77** | **19 / 1 / 54** |

`CONFIRMED` und `REFUTED` sind unveraendert; die Unpruefbar-Zahl sinkt um 23
(77 -> 54). Die zwei `REFUTED`-freien Abweichungen zum urspruenglichen
Superorchestrator-Befund (dort 20 / 0 / 77): mit der hier gepinnten
p5-Baseline vergleicht der Diff-Scope gegen die Prosa-Planliste "the 6 files
above" und endet korrekt `widerlegt`; die fuer dieses Audit entscheidende
Zahl — 77 `unpruefbar` vorher — ist reproduziert.

## Die 23 ignorierten Behauptungen (vorher -> nachher entfernt)

Alle trugen einen Platzhalter im eigenen Rumpf; keine davon war vorher
`bestaetigt` oder `widerlegt`:

| Typ | Anzahl | Beispiele |
|---|---|---|
| commit_exists | 7 | `[COMMIT: <hash>]`, `[COMMIT: <HEAD>]`, `[COMMIT: <Branch-HEAD>]` |
| artifact | 4 | `[ARTIFACT: <pfad> -> <sha256>]`, `[ARTIFACT: ... -> <sha256>]` |
| merge | 3 | `[MERGE: <branch>]`, `[MERGE: ...]` |
| coloring | 3 | `[COLORING: k=<k> ; <digits>]`, `[COLORING: k=4 ; 1112223...]` |
| halt | 2 | `[HALT: <machine> -> <steps>]` (die P7-Vorlage aus dem Befund) |
| deploy | 2 | `[DEPLOY: ...]` |
| compute | 1 | `... -> e5b68dd1…` (abgeschnittener Digest) |
| ident | 1 | `[IDENT: n=<affine> ; ...]` |
| **Summe** | **23** | |

## Exit-Code-Matrix (echte Werte unveraendert)

| Meldung | vorher exit / strict | nachher exit / strict |
|---|---|---|
| echter Commit | 0 / 0 | 0 / 0 |
| hash-foermiger, fehlender Commit | 1 / 1 | 1 / 1 |
| `[HALT]` bestaetigt | 0 / 0 | 0 / 0 |
| `[HALT]` widerlegt | 1 / 1 | 1 / 1 |
| `[HALT]` ueber dem Limit (unpruefbar) | 3 / 3 | 3 / 3 |
| Meldung ohne Behauptung | 3 / 3 | 3 / 3 |
| Commit + echtes unpruefbares `[HALT]` (strict) | 0 / 4 | 0 / 4 |
| Commit + Platzhalter-`[HALT]` (strict) | 0 / 4 | 0 / **0** |

Die letzte Zeile ist die gewollte Aenderung: eine Platzhalter-Zeile macht aus
einem `--strict`-Lauf keinen Exit 4 mehr, weil sie keine Behauptung ist.

P18-Nachtrag (2026-09-13): Die beiden HALT-Zeilen der Matrix laufen unter
`--strict` jetzt mit Exit 6 (`[HALT]` ueber dem Limit ist die Klasse `limit`,
eigener Code fuer "wegen Budget nicht ausgefuehrt"): `halt-over-limit`
3 / **6** statt 3 / 3 und `strict-mixed-real` 0 / **6** statt 0 / 4. Alle
uebrigen Zeilen bleiben unveraendert; die "vorher/nachher"-Spalten dieser
Tabelle dokumentieren den P15-Stand. Siehe README, Abschnitt "Exit-Codes".

## Was bewusst NICHT ignoriert wird (Grenzen)

- **Literale Marker auf Vorlagenzeilen.** Ein Briefing-Template wie
  `[DONE] [DEPLOY: no] [COMMIT: <hash>] [BRANCH: yesloop/...] [MERGE: no]`
  verliert nur die Platzhalter-Behauptungen; `[DEPLOY: no]`, `[BRANCH: ...]`
  und `[MERGE: no]` tragen eigene, literale Werte und bleiben Behauptungen
  (und damit `unpruefbar`, solange es keinen Deploy-Checker bzw. kein Remote
  gibt). Das ist die konservative Seite der Regel: niemals eine Behauptung
  stillschweigend fallen lassen, deren eigener Wert ausgeschrieben ist. So
  bleiben von den 77 `unpruefbar` genau 54 uebrig (12 `[DEPLOY]`, 18
  `[MERGE]`, 11 `[BRANCH]` mit literalen Werten aus Templates, dazu 7
  Diff-Scopes ohne Basis-Kontext und 6 fachliche Reste wie `[COMMIT: HEAD]`
  oder die Beispielmaschine `M`).
- **`go test ./...`** bleibt eine Testbehauptung: `./...` ist ein Pfadmuster,
  kein abgeschnittener Wert.
- **`<` ohne `>`** (etwa ein Dateiname `a<b.txt`) bleibt eine Behauptung.
- **`[COMMIT: e5b68dd1]`** (kurz, aber hash-foermig, ohne Ellipse) bleibt
  eine Behauptung und behaelt sein Urteil.
