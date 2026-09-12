---
topic: deepseek-math-notation
cluster: 01-modellprofil
title: "Tokenizer-Sonde V1.1: Messung der Denk-Sprache-Lexeme"
language: de
status: Verifiziert
last_updated: 2026-09-12
created_at: 2026-09-12
sources_count: 4
citations_count: 4
images_count: 0
diagrams_count: 0
related:
  - 01-03-tokenizer-zahlen.md
  - ../05-entwurf-testplan/05-07-denksprache-v1.1.md
  - ../05-entwurf-testplan/05-04-test-harness.md
tags:
  - tokenizer
  - sonde
  - denksprache
  - v1.1
  - lexeme
persona_review:
  personas_tested: ["Engineer (Baustufe W1)"]
  gaps_found: 0
  gaps_fixed: 0
  note: "Erstellt im Bau-/Pilotzyklus V1.1 (W1, 2026-09-12). Kein separater Persona-Review-Durchgang."
---

# Tokenizer-Sonde V1.1: Messung der Denk-Sprache-Lexeme

Diese Datei ist der Messbericht der **Sonde**, die der Entwurf [05-07](../05-entwurf-testplan/05-07-denksprache-v1.1.md) als D3 zur Pflicht macht: Jedes potenzielle Lexem der Denk-Sprache wird gegen den gemessenen Tokenizer des Zielmodells geprüft, bevor es in die Lexik aufgenommen wird. Gemessen wurde die V1.1-Kandidatenliste aus [05-07](../05-entwurf-testplan/05-07-denksprache-v1.1.md) §§2–7 auf Basis der Methode und der Validierungsdaten aus [01-03](01-03-tokenizer-zahlen.md). Alle Zahlen sind lokale Messungen vom 2026-09-12.

## 1. Methode

- **Tokenizer:** `tokenizer.json` des Modells DeepSeek-V4.1-Flash (HF-Repo, Bezug wie in [01-03](01-03-tokenizer-zahlen.md)), SHA-256 `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b`, 6.367.257 Bytes.
- **Bibliothek:** `tokenizers` 0.23.2. Die Installation erfolgte ohne systemweites pip: Das cp310-abi3-manylinux-Wheel wurde als ZIP in ein projektlokales Verzeichnis entpackt und per `PYTHONPATH` geladen (kein `sudo`, kein Paketmanager — die Maschine hat kein pip; das ist eine Reproduktionsnotiz, keine Empfehlung).
- **Skript:** `assets/01-03-messskript.py` wurde um die V1.1-Lexemtabellen erweitert (Abschnitte `## V1.1: …`); die Originaltabellen und ihre Ausgaben bleiben unverändert.
- **Validierung:** Alle 42 bekannten Vektoren aus den Rohdaten zu [01-03](01-03-tokenizer-zahlen.md) (Zahlen, Operatoren, Symbole, Bausteine) wurden mit dieser Umgebung exakt reproduziert (0 Abweichungen). Die Sonde misst damit auf derselben Basis wie der veröffentlichte Tokenizer-Befund.
- **Rohdaten:** `assets/01-03b-rohdaten-v11.txt` (168 Zeilen, wörtliche Skript-Ausgabe der V1.1-Abschnitte).

Reproduktion:

```bash
PYTHONPATH=<pylibs> python3 assets/01-03-messskript.py <pfad/zu/tokenizer.json>
```

## 2. Befunde (Auszug; Vollständigkeit in den Rohdaten)

### 2.1 Potenz und Knuth-Pfeile

| Eingabe | Tokens | Zerlegung |
|---|---|---|
| `^` | 1 | `^` |
| `**` | 1 | `**` |
| `^^` | 1 | `^^` |
| `^^^` | 2 | `^^`+`^` |
| `2^^3` | 3 | `2`·`^^`·`3` |
| `2^^^3` | 4 | `2`·`^^`·`^`·`3` |
| `2^127-1` / `2**127-1` / `2^^127-1` | je 5 | wie [01-03](01-03-tokenizer-zahlen.md) |

**Befund:** `^^` ist ein Einzeltoken, `^^^` zerfällt in zwei. Die Knuth-Pfeil-Kandidaten aus [05-07](../05-entwurf-testplan/05-07-denksprache-v1.1.md) §5 sind damit token-ökonomisch tragfähig; `^^^` kostet einen Token mehr, bleibt aber deutlich billiger als jede ausgeschriebene Form.

### 2.2 2-Zeichen-Aliase (§5) und Langform-Vergleich

Alle zehn Kandidaten `ip st mx pm gc dv di fc ch fb` sind **je 1 Token** (allein gemessen). Im Aufruf dominiert die Klammer-/Argumentstruktur den Preis:

| Aufruf | Tokens | Langform | Tokens |
|---|---|---|---|
| `st(27)` | 4 | `collatz_steps(27)` | 7 |
| `ip(97)` | 4 | `isprime(97)` | 5 |
| `mx(27)` | 4 | `collatz_max(27)` | 6 |
| `pm(2,10,1000)` | 9 | `powmod(2,10,1000)` | 10 |
| `gc(12,18)` | 6 | `gcd(12,18)` | 6 |
| `dv(28)` | 4 | `divisors(28)` | 5 |
| `di(3,12)` | 6 | `divides(3,12)` | 7 |
| `fc(5)` | 4 | `factorial(5)` | 5 |
| `ch(10,3)` | 6 | `choose(10,3)` | 6 |
| `fb(100)` | 4 | `fib(100)` | 4 |

**Befund:** Der Alias-Vorteil ist real, aber moderat (1–3 Tokens je Aufruf; bei `gc`, `ch`, `fb` gleichauf, weil die Langformen bereits kurz mergen). Die Einzeltoken-Eigenschaft der Aliasse selbst ist bestätigt — die Sonde verbietet keinen der zehn.

### 2.3 Quantoren- und Zähl-Kandidaten

| Eingabe | Tokens | Anmerkung |
|---|---|---|
| `∀` | 1 | wie [01-03](01-03-tokenizer-zahlen.md) |
| `∃` | 2 | wie [01-03](01-03-tokenizer-zahlen.md) |
| `ex` | 1 | Kandidat statt `∃` |
| `ex n in 1..100` | 7 | wie `forall n in 1..100` (7) |
| `#(` | 2 | Zählform |
| `#(dv(28))` | 6 | |
| `#dv(28)` | 5 | kompakter, aber nicht in der Spezifikation |
| `\|dv(28)\|` | 5 | Betrags-Kollision mit absoluter Zahl |

**Befund:** `ex` ist als Einzeltoken bestätigt und halbiert den Symbolpreis gegenüber `∃`. `#(…)` ist messbar teurer als die Alternativen (`#dv(28)`, `|dv(28)|`), kostet aber nur einen Token mehr; die Sonde lässt alle drei zu. Die Wahl ist eine Designfrage (Lesbarkeit/Off-Distribution), keine Tokenfrage der ersten Ordnung.

### 2.4 Zeilen-Opcodes, Status-Suffixe, Appendix

| Eingabe | Tokens |
|---|---|
| `g:` / `d:` / `a:` / `c:` / `q:` / `=:` | je 2 |
| `h1:` / `h2:` | je 3 |
| `v h1:` | 4 |
| `h1+` / `h2-` / `h3?` / `h4!` | je 3 |
| `#ok: v1 v2` | 7 |
| `#ok:v1 v2` (kompakt) | 6 |
| `#?:v4` | 4 |

**Befund:** Die Kopfzeilen sind billig (2–4 Tokens). Die Status-Suffixe kosten 3 Tokens als Mini-Zeile — die explizite Epistemik ist damit auch im schlimmsten Fall ein Bruchteil einer Rechenzeile. Appendix kompakt gespart 1 Token pro Zeile.

### 2.5 Trace-Formen (§6), kompakt vs. mit Leerraum

| Eingabe | Tokens |
|---|---|
| `cp 0: (A,0,1101)` | 12 |
| `cp0:(A,0,1101)` | 10 |
| `seg 0..100` | 5 |
| `seg0..100` | 4 |
| `sim(0..100)` | 6 |
| `cyc(6,16,2)` | 9 |
| `a^5 b^12 c` | 7 |
| `->` / `→` / `=>` | je 1 |

**Befund:** Die Checkpoint-Form ist der teuerste Denk-Baustein (10–12 Tokens): Die Ziffern des Tapes (`1101` → `110`·`1`) und die Strukturzeichen addieren sich. Die kompakte Variante ohne Leerzeichen nach `cp`/`seg` spart je 1–2 Tokens und wird für Trace-Aufgaben empfohlen; die Repräsentation eines Tapes als Ziffernlauf bleibt der dominante Kostenpunkt.

### 2.6 Kompaktstil (§5)

| Eingabe | Tokens |
|---|---|
| `st(27)=111` | 5 |
| `st(27) = 111` | 7 |
| `h1:st(27)=111` | 8 |
| `h1: st(27)=111` | 8 |
| `=: st(27)=111 (h2+)` | 11 |
| `=:st(27)=111(h2+)` | 10 |

**Befund:** Leerraum um `=` kostet real (5 → 7). Ein Leerzeichen nach dem Tag-Doppelpunkt ist dagegen kostenfrei (`h1:` + `␣st` vs. `h1:` + `st` — beide 8), weil führende Leerzeichen an Folgetokens mergen. Interpretation für S9: Der Sparhebel ist der Rumpf (keine Leerzeichen um Operatoren), nicht der Kopf.

## 3. Konsequenzen für V1.1 (die Sonde entscheidet)

| Lexem-Frage | Messbefund | Entscheidung der Sonde |
|---|---|---|
| `^^` / `^^^` | 1 / 2 Tokens | **tragfähig** — beide aufgenommen |
| Zehn 2-Zeichen-Aliase | je 1 Token | **bestätigt** — alle tragfähig |
| `ex` vs. `∃` | 1 vs. 2 Tokens | `ex` **tragfähig** (Ersatz-Kandidat) |
| `#(…)` | `#(` = 2, Aufruf +1 Token | **messbar zulässig**; `#dv(…)`/`\|…\|` billiger |
| Tag-Präfixe | 2–4 Tokens | **tragfähig** |
| Status-Suffixe | 3 Tokens | **tragfähig** |
| Kompaktstil | −2 Tokens um `=`; −1..−2 in Trace-Zeilen | **wirksam** — im Legendentext als Stilregel führen |
| Verdikt-Appendix | 6–7 Tokens kompakt | **tragfähig** |

**Kosten-Nullprobe des Beispielblatts ([05-07](../05-entwurf-testplan/05-07-denksprache-v1.1.md) §9, wörtlich):** Die 13 Zeilen des illustrativen Blatts kosten zusammen gemessen knapp über 90 Tokens (Summe der Rohdaten-Zeilen `Beispielzeilen`). Zum Vergleich: eine einzige LaTeX-Formel `\sum_{i=1}^{n}` kostet 8 Tokens; die Denk-Sprache erreicht ihre Ökonomie über kurze Zeilen und Zeugen statt gerechneter Zwischenschritte.

## 4. Grenzen des Befunds

- Gemessen wurde der veröffentlichte Tokenizer; ob der Inferenz-Server dieser Instanz exakt denselben Stand verwendet, ist wie in [01-03](01-03-tokenizer-zahlen.md) nicht unabhängig verifiziert.
- Die Beispielzeilen-Summen sind einfache Additionen der Zeilenmessungen (gleiche Messmethode); als Ganzes wurde das Blatt nicht gemessen (Zeilenumbrüche/BOS-Kontext sind serving-abhängig).
- Die Messung entscheidet Tokenkosten, nicht Erlernbarkeit: Ob das Modell die Lexeme im Denken tatsächlich nutzt, messen erst die Arme des Pilotlaufs (Metriken h/k, [05-05](../05-entwurf-testplan/05-05-ablation-protokoll.md) Nachtrag).

## Quellen

1. Lokale Messung (2026-09-12): `assets/01-03-messskript.py` (erweitert), `assets/01-03b-rohdaten-v11.txt`; Tokenizer-Datei SHA-256 `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b`.
2. Lokale Quelle: [01-03-tokenizer-zahlen.md](01-03-tokenizer-zahlen.md) — Methode und Validierungsvektoren (42/42 reproduziert).
3. Lokale Quelle: [05-07-denksprache-v1.1.md](../05-entwurf-testplan/05-07-denksprache-v1.1.md) — Kandidatenliste (§§2–7) und D3-Sondenpflicht (§1).
4. DeepSeek-AI (2026): tokenizer.json des Modells DeepSeek-V4.1-Flash. Hugging Face. https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/main/tokenizer.json (accessed 2026-09-12)
