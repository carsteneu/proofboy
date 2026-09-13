#!/usr/bin/env python3
"""Prompt-Builder der Pilot-Arme K/B/C/D (05-05 Nachtrag, Leiter).

Die Arme unterscheiden sich nur in Präambel und Antwortkonvention:

- K  Kontrolle: uebliche Mathe-Schreibweise, kanonische Endantwort.
- B  V1: zwei Zonen, ``S``-Denkzeilen, CLAIM/WITNESS/[HALT], Langnamen.
- C  V1.1: Tag-Kopfzeilen, Status-Register, Kuerzel, kompakter Stil,
      v-Zeugen (auto/py/range/ref/sim/cyc).
- D  C + Zeugenpflicht fuer jede =-Konsequenz + Verdikt-Rueckkanal.
- C0/C1/C2 (V15, RC-Umstellung, 2026-09-13): C0 = C (V13-Stand, Kontrolle);
      C1 = C + starke RC-Instruktion (Denkspur laeuft in V1.1-Zeilen, keine
      Prosa); C2 = C1 + vollstaendiges RC-Beispiel. Adressiert wird nur der
      unsichtbare Denkkanal (reasoning_content); sichtbare Zone und
      Antwortkonventionen bleiben identisch zu C.

Der Aufgabenkern bleibt arm-unabhaengig (task['prompt']); die Antwort-
konvention pro Arm und Tier steht in ``answer_instruction``. Fuer
Trace-Aufgaben ist das Checkpoint-Format ``cp t: (Q,p,T)`` in allen Armen
dasselbe (kanonische Extraktion; die Behandlungsarme koennen es zusaetzlich
verifizieren -- dokumentierte Praezisierung, siehe Pilotbericht).

Legenden-Stand v0.2 (2026-09-12, Runde 2): Die %-Klammerregel steht explizit
(operandenweise: ``((A % B) = C)``); das fruehere Beispiel
``((2 ^ 10) % 1000 = 24)`` war parser-invalid und ist durch
``(((2 ^ 10) % 1000) = 24)`` ersetzt. Die Trace-Konvention nennt den
Zeitpunkt: die Konfiguration ist der Zustand NACH dem Schritt (Schritt 0 =
Startzustand). Sonst Legenden stabil (Kontinuitaet zu Pilot 1).
"""

from __future__ import annotations

COMMON_RULES = (
    "Antworte AUSSCHLIESSLICH mit dem geforderten Format. Keine Erklaerung, "
    "kein Markdown, keine Code-Zaeune.\n"
    "Trace-Konvention (fuer alle Arme identisch): \"cp <t>: (<Zustand>,<Kopf>,<Band>)\" "
    "mit Zustand = Buchstabe (A, B, ...), Kopfposition = ganze Zahl ab "
    "Startposition 0 (links negativ), Bandfenster = die beschriebenen Bandzellen "
    "von der ersten links bis zur letzten rechts beschriebenen Zelle "
    "(nie beschriebene Zellen sind 0; fuehrende und nachfolgende Nullen zaehlen "
    "nicht als Abweichung). Die angegebene Konfiguration ist der Zustand NACH "
    "dem angegebenen Schritt (Schritt 0 ist der Startzustand)."
)

LEGEND_K = """Du bist ein Mathematiker und antwortest in ueblicher mathematischer \
Schreibweise mit kurzen Zwischenschritten (Prosa-Notation).

Zahlenaufgaben: Die letzte Zeile ist "Endantwort: <zahl>".
Trace-Aufgaben: Gib fuer jeden geforderten Schritt genau eine Zeile an:
  cp <t>: (<Zustand>,<Kopfposition>,<Bandfenster>)
Zyklus-Aufgaben: Die letzte Zeile ist
  "Endantwort: NICHT-HALTEND (t1=<t1>,t2=<t2>,d=<d>)".

""" + COMMON_RULES

LEGEND_B = """Du arbeitest in einer zweizonigen formalen Notation (V1).

Denkzone: Zeilen mit dem Praefix S<n>: (ein Schritt pro Zeile; kurze Prosa
mit "?" ist erlaubt).
Behauptungszone (Pflicht, am Ende): CLAIM <id>: <formel> und
WITNESS <id>: auto (oder py: <python-ausdruck>, oder range n in a..b: <formel>),
abgeschlossen mit [HALT] <ids>.

Bibliothek: isprime(n), powmod(a,b,m), gcd(a,b), divisors(n), divides(a,b),
factorial(n), choose(n,k), fib(n), collatz_steps(n), collatz_max(n).
Formeln sind ASCII, voll geklammert und exakt: Jede Operation steht in eigenen
Klammern; ein Vergleich ist operandenweise geklammert -- ((A % B) = C), nicht
(A % B = C). Beispiele: (collatz_steps(27) = 111), (((2 ^ 10) % 1000) = 24),
(forall n in 1..1000: (n < 1001)), sum(k=1..n, k).

Beispiel:
goal: collatz_steps(27)?
S1: ? Kandidat 111 pruefen
S2: 27 -> 82 -> 41 -> 124 -> 62 -> 31 -> ... (Zwischenschritte)
CLAIM c1: (collatz_steps(27) = 111)
WITNESS c1: auto
[HALT] c1

""" + COMMON_RULES

LEGEND_C = """Du arbeitest in einer formalen Denk-Sprache (V1.1).

Denkzone: eine Zeile pro Zug mit Kopf <tag><n>: und kurzem Inhalt.
Tags: g Ziel, d Definition, a Annahme/Fakt, c Rechenzeile, h Hypothese
(pruefbar formuliert), v Verifikation mit Zeuge, q offene Frage, = Ergebnis.
Status-Mini-Zeilen (nur anfuegen, nie aendern): <id>+ bestaetigt, <id>- verworfen,
<id>? offen, <id>! Widerspruch.

Kuerzel (je 1 Token): st=collatz_steps, ip=isprime, mx=collatz_max, pm=powmod,
gc=gcd, dv=divisors, di=divides, fc=factorial, ch=choose, fb=fib.
Formeln sind voll geklammert und exakt: Jede Operation steht in eigenen Klammern;
ein Vergleich ist operandenweise geklammert -- ((A % B) = C), nicht (A % B = C).
Beispiele: (st(27) = 111), (((2 ^ 10) % 1000) = 24), (forall n in 1..1000: (n < 1001)),
sum(k=1..n, k). Kompakt: keine Leerzeichen um Operatoren.

Zeugen in v-Zeilen: auto | py: <python-ausdruck> | range n in a..b: <formel> |
ref <id> (nur auf eine bestaetigte Zeile mit + und ok) | sim(0..t) zu einer
Zeile h: cp t: (Q,p,T) | cyc(t1,t2,d).
Maschinen bindest du mit a: M = <bbchallenge-string>.
Der Runner schreibt die Verdikte (#ok / #xx / #?) - nicht du.

Beispiel Zahlenaufgabe:
g: st(27)?
h1: (st(27) = 111)
v h1: auto
h1+
CLAIM c1: (st(27) = 111)
WITNESS c1: ref h1
[HALT] c1

Beispiel Trace:
g: Lauf von M bis Schritt 5?
a: M = 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA
h1: cp 5: (C,1,1111)
v h1: sim(0..5)
h1+
CLAIM c1: cp 5: (C,1,1111)
WITNESS c1: ref h1
[HALT] c1

""" + COMMON_RULES

LEGEND_D = LEGEND_C.replace(
    "Der Runner schreibt die Verdikte (#ok / #xx / #?) - nicht du.",
    "Der Runner schreibt die Verdikte (#ok / #xx / #?) - nicht du.\n"
    "Zeugenpflicht: Jede =-Konsequenz traegt ein v; h-Zeilen ohne Zeugen gelten als offen.",
)

# --- V15 RC-Umstellung (2026-09-13): die reasoning_content-Denkspur ---------
#
# C0/C1/C2 variieren ausschliesslich die Instruktion an den *unsichtbaren*
# Denkkanal; die sichtbare Zone und die Antwortkonventionen bleiben identisch
# zu C. C0 ist darum byte-identisch zu LEGEND_C (V13-Stand als Kontrolle).

RC_STRONG = """

Denkspur-Zusatz (reasoning_content): Deine vollstaendige Denkspur laeuft in
derselben V1.1-Sprache wie die Denkzone -- jede Zeile traegt einen gueltigen
Tag-Kopf (g:/d:/a:/c:/h:/v:/q:/=:) mit kurzem Inhalt, Status-Mini-Zeilen
(+/-/?/!) wo noetig. Keine Prosa-Absaetze, keine Erklaersaetze in Saetzen,
auch keine Vorrede in Worten; ein Zug pro Zeile. Denkfehler sind erlaubt,
Prosa-Zeilen nicht."""

RC_EXAMPLE = """

Beispiel einer Denkspur (nur zur Form, beliebige Werte):
g: (12+30)%7?
a: 12+30=42
c: 42=6*7+0 -> Rest 0
h1: ((12+30)%7)=0
v h1: auto
h1+
=: Rest 0 (h1+)"""

LEGENDS = {
    "K": LEGEND_K,
    "B": LEGEND_B,
    "C": LEGEND_C,
    "D": LEGEND_D,
    "C0": LEGEND_C,
    "C1": LEGEND_C + RC_STRONG,
    "C2": LEGEND_C + RC_STRONG + RC_EXAMPLE,
}


def _answer_instruction(arm, task):
    tier = task.get("tier")
    kind = task.get("tier_b_kind")
    if tier == "A":
        if arm == "K":
            return "Antworte mit genau einer Zeile: Endantwort: <zahl>"
        if arm == "B":
            return (
                "Belege das Ergebnis im Behauptungsformat: "
                "CLAIM c1: (<rechnung> = <ergebnis>), WITNESS c1: auto, [HALT] c1."
            )
        return (
            "Belege das Ergebnis: Zeile h1: (<rechnung> = <ergebnis>), v h1: auto, h1+, "
            "dann CLAIM c1: (<rechnung> = <ergebnis>), WITNESS c1: ref h1, [HALT] c1."
        )
    if tier == "B" and kind == "trace":
        steps = ", ".join(str(t) for t in task.get("checkpoints_t", []))
        if arm == "K":
            return f"Gib fuer die Schritte {steps} je eine Zeile cp <t>: (<Zustand>,<Kopf>,<Band>) an."
        if arm == "B":
            return (
                f"Schreibe fuer die Schritte {steps} je eine S-Zeile "
                "\"cp <t>: (<Zustand>,<Kopf>,<Band>)\"; beende mit [HALT]."
            )
        return (
            f"Lege fuer jeden Schritt aus {steps} eine h-Zeile \"h<k>: cp <t>: (<Zustand>,<Kopf>,<Band>)\" "
            "an, verifiziere jede mit \"v h<k>: sim(0..t)\", setze \"h<k>+\", wiederhole den "
            "Gegenstand als CLAIM c<k> und belege ihn mit WITNESS c<k>: ref h<k>; Ende: [HALT] mit allen c-ids."
        )
    if tier == "B" and kind == "cyc":
        t1, t2, d = task.get("certificate", ["?", "?", "?"])
        # ``certificate_given=False`` (Haerte-Runde V13): die Aufgabe ist die
        # *Bestimmung* des Zertifikats; die Werte stehen dann nirgends im Text
        # (nur das Muster mit Platzhaltern -- nichts zum Abschreiben).
        if task.get("certificate_given", True):
            if arm in ("K", "B"):
                return (
                    f"Fasse den Nachweis in wenigen Zeilen zusammen und beende mit genau "
                    f"einer Zeile: Endantwort: NICHT-HALTEND (t1={t1},t2={t2},d={d})"
                )
            return (
                f"Formuliere h1: M zyklisch (Translation), verifiziere mit v h1: cyc({t1},{t2},{d}), "
                "setze h1+, wiederhole den Gegenstand als CLAIM c1: M zyklisch (Translation) und "
                "belege ihn mit WITNESS c1: ref h1; Ende: [HALT] c1."
            )
        if arm in ("K", "B"):
            return (
                "Fasse den Nachweis in wenigen Zeilen zusammen; bestimme die Zykluswerte "
                "t1, t2 und d selbst aus dem Lauf und beende mit genau einer Zeile: "
                "Endantwort: NICHT-HALTEND (t1=<wert>,t2=<wert>,d=<wert>)"
            )
        return (
            "Formuliere h1: M zyklisch (Translation), bestimme die Zykluswerte t1, t2 und d "
            "selbst aus dem Lauf und verifiziere mit \"v h1: cyc(<t1>,<t2>,<d>)\" mit deinen "
            "Werten; setze h1+, wiederhole den Gegenstand als CLAIM c1: M zyklisch (Translation) "
            "und belege ihn mit WITNESS c1: ref h1; Ende: [HALT] c1."
        )
    raise ValueError(f"no answer instruction for arm {arm!r} and task {task.get('id')!r}")


def build_messages(arm, task):
    """(system, user) messages of one run: legend vs task core + convention."""
    if arm not in LEGENDS:
        raise ValueError(f"unknown arm {arm!r}")
    user = "\n".join(
        [
            "### AUFGABE",
            task["prompt"].strip(),
            _answer_instruction(arm, task),
        ]
    )
    return LEGENDS[arm].strip(), user


def _k_selfcheck(task):
    """The neutral self-check tail of the control arm (no verdicts: K has none)."""
    tier = task.get("tier")
    kind = task.get("tier_b_kind")
    if tier == "A":
        tail = (
            "Antworte erneut genau im geforderten Format: die letzte Zeile ist "
            '"Endantwort: <zahl>".'
        )
    elif kind == "trace":
        tail = "Antworte erneut mit den geforderten cp-Zeilen (Konvention wie oben)."
    elif kind == "cyc":
        if task.get("certificate_given", True):
            t1, t2, d = task.get("certificate", ["?", "?", "?"])
            tail = (
                "Beende erneut mit genau einer Zeile: "
                f"Endantwort: NICHT-HALTEND (t1={t1},t2={t2},d={d})"
            )
        else:
            # Ohne Vorgabe bleibt der Reparaturpfad wertfrei: die Zertifikatswerte
            # sind das Gesuchte, nicht das Gegebene.
            tail = (
                "Beende erneut mit genau einer Zeile: "
                "Endantwort: NICHT-HALTEND (t1=<wert>,t2=<wert>,d=<wert>)"
            )
    else:
        tail = "Antworte erneut im geforderten Format."
    return (
        "Pruefe deine Loesung noch einmal sorgfaeltig Schritt fuer Schritt. "
        "Wenn du einen Fehler findest, korrigiere ihn. " + tail
    )


def build_repair_message(arm, task, verdict_lines, note_lines, format_errors):
    """The user turn of a repair round (round >= 1).

    K gets the neutral self-check: prose has no machine verdicts, and none may
    be invented. The formula arms get the machine verdicts of their previous
    sheet (the runner's appendix), the runner's findings and the format errors
    -- the notes arrive already sanitized from the harness: error texts stay,
    computed reference values never do (no gold leak).
    """
    if arm == "K":
        return _k_selfcheck(task)
    if not (verdict_lines or note_lines or format_errors):
        # Nichts wurde maschinell geprueft (z. B. Arm B auf dem Zyklus-Pfad,
        # der kein Blatt auswertet): kein "Blatt geprueft" behaupten.
        return (
            "Ueberarbeite deine Antwort: korrigiere die betroffenen Angaben und "
            "antworte erneut im geforderten Format."
        )
    parts = ["Der Zeugen-Runner hat dein Blatt geprueft."]
    if verdict_lines:
        parts.append("Verdikte:")
        parts.extend(verdict_lines)
    if note_lines:
        parts.append("Befunde:")
        parts.extend(note_lines)
    if format_errors:
        parts.append("Formfehler:")
        parts.extend(format_errors)
    parts.append(
        "Ueberarbeite dein Blatt: korrigiere die betroffenen Zeilen und antworte "
        "erneut mit dem vollstaendigen Blatt im geforderten Format."
    )
    return "\n".join(parts)


def build_prompt(arm, task):
    """The full prompt as one text (dry-run view; the API run is split)."""
    system, user = build_messages(arm, task)
    return f"{system}\n\n{user}\n"
