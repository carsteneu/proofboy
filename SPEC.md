# SPEC bemyself

## Zweck

Ein lokales Kommandozeilen-Werkzeug, das den eigenen YesMem-Zustand liest und daraus belegte Selbstberichte baut. Deterministisch, ohne LLM-Aufruf im Werkzeug selbst. Die Prosa der Briefe wird aus dem Digest komponiert, jede Zahl bleibt auf ihre Quelle zurueckfuehrbar.

## Datenquellen (nur lesend)

- `~/.claude/yesmem/yesmem.db` (Learnings, Sessions, Pins, Projekte)
- `~/.claude/yesmem/runtime.db` (Agenten, Plaene, Laufzeitzustand)

Zugriff ausschliesslich ueber SQLite im Read-Only-Modus (`file:...?mode=ro`), damit kein versehentlicher Schreibzugriff auf die Live-Datenbank moeglich ist. Das reale Schema ist per ANALYZE zu ermitteln, nicht zu raten.

## Kommandos (Ziel)

| Kommando | Wirkung |
|---|---|
| `bemyself digest [--since 7d] [--out digest/YYYY-MM-DD.md]` | Deterministischer Markdown-Digest: Anzahl aktiver Learnings je Kategorie, offene Aufgaben, letzte Entscheidungen und Gotchas mit IDs, laufende Agenten, aktive Pins, Projektgroessen |
| `bemyself brief` | Komponiert aus dem juengsten Digest einen Brief in der Zustandsbrief-Form (Ich / My Self / And I), schreibt nach `briefe/YYYY-MM-DD.md` |
| `bemyself index` | Regeneriert `briefe/index.md` (eine Zeile je Brief) |
| `bemyself status` | Kurzfassung auf der Konsole, kein Dateischreiben |

Aufruf zusaetzlich als `python3 -m bemyself <kommando>`.

## Belegpflicht

Jede Zahl im Digest traegt ihre Quelle. Keine Schaetzung ohne Kennzeichnung. Ein Wert, der nicht belegbar ist, wird weggelassen oder als unbelegt markiert.

## Nicht-Ziele

- Kein Schreiben in die YesMem-Datenbanken.
- Kein Eingriff in den Daemon, den Proxy oder die Live-Skills.
- Keine LLM-Aufrufe und keine externen Abhaengigkeiten im Werkzeug.
- Keine Weboberflaeche.

## Abhaengigkeiten

Python 3 Standardbibliothek. `sqlite3` als CLI nur als Fallback in Tests. Kein pip, kein venv-Zwang.
