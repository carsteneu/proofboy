---
topic: selbstmodell
language: de
min_sources_per_file: 2
default_max_runtime: 2h
max_concurrent_agents: 3
---

# Master-Plan: Selbstbericht und Kontinuitaet fuer LLM-Agenten

Zweck dieser Recherche: Sie traegt das Design von bemyself. Die Frage ist nicht allgemein "was ist Agenten-Memory", sondern praezise: Was muss ein Selbstbericht eines LLM-Agenten enthalten, damit er belegt, ehrlich und anschlussfaehig ist, und wie loesen vergleichbare Systeme den Selbstbezug.

Jede Aussage wird zitiert. Widerspruechliche Quellen werden beide dargestellt, nicht aufgeloest.

## 01-systeme

Wie vergleichbare Systeme Selbstbezug und Kontinuitaet behandeln.

- mem0.md — Architektur, Speichermodell, Umgang mit Nutzer- und Selbstprofilen, Stand 2026
- zep.md — zeitlicher Wissensgraph, Umgang mit Wandel und Gueltigkeit, Stand 2026
- letta-memgpt.md — Stateful Agents, Selbstmodell und Persona, Stand 2026
- claude-mem-und-yesmem.md — lokale Memory-Systeme, Proxy-Schicht, was sie ueber sich selbst wissen

## 02-selbstbericht

Was ein Agenten-Selbstbericht inhaltlich leisten muss.

- evidenzpflicht.md — warum jede Aussage eine Quelle braucht, Belegformen, Umgang mit Unbelegbarem
- identitaet-und-wandel.md — Kontinuitaet trotz Modellwechsel, Supersede-Ketten, wo sich ein Selbstbild aendert
- beziehung.md — was Berichte ueber die Beziehung zum Nutzer aussagen koennen, ohne Kitsch

## 03-evaluation

Wie man Kontinuitaet, Drift und Wiedererkennung messbar macht.

- drift-masse.md — Ansaetze zur Messung von Persoenlichkeitsdrift und Identitaetsverlust
- langzeit-benchmarks.md — bestehende Benchmarks fuer Langzeitgedaechtnis und Identitaet (LoCoMo, LongMemEval und Verwandte)

## 99-sources

- bibliography.md — gesammelte Quellen, nach Cluster gruppiert
