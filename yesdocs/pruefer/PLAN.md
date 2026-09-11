---
topic: pruefer
language: de
min_sources_per_file: 2
default_max_runtime: 2h
max_concurrent_agents: 3
---

# Master-Plan: unabhaengige Verifikation von Behauptungen

Zweck: Diese Recherche traegt das Design des Pruefers. Leitfrage: Wie prueft man eine Behauptung ueber den Zustand der Welt unabhaengig, ohne sie zu glauben, und was ist aus bestehenden Systemen uebertragbar.

Jede Aussage wird zitiert. Widerspruechliche Quellen werden beide dargestellt.

## 01-theorie

Was eine Behauptung pruefbar macht.

- falsifizierbarkeit.md — Falsifizierbarkeit, Beleg und Beweislast, was ein Zeuge ist und was ein Beweis
- provenance-und-herkunft.md — Herkunftsnachweise, Signatur, Vertrauenskette, warum Herkunft nicht Wahrheit ist

## 02-systeme

Wie bestehende Systeme Behauptungen verifizieren.

- ci-und-reproduzierbare-builds.md — CI-Gates, reproduzierbare Builds, Artefakt-Hashes als Zeugen
- supply-chain-provenienz.md — SLSA, in-toto, signaturebasierte Lieferketten, was sie garantieren und was nicht
- fact-checking-pipelines.md — Fact-Checking und Claim-Verifikation in Redaktionen, ClaimBuster und Verwandte

## 03-agenten

Verifikation fuer LLM-Agenten.

- selbstpruefung-und-grenzen.md — Selbstpruefung, LLM-as-Judge, warum ein Modell seine eigene Ausgabe nicht verlaesslich prueft
- halluzination-und-belegbindung.md — Halluzinationserkennung, Belegbindung, Zitationsverifikation
- falsche-bestaetigung.md — Fehlerkosten, warum eine falsche Bestaetigung schwerer wiegt als ein durchgelassener Betrug

## 99-sources

- bibliography.md — gesammelte Quellen, nach Cluster gruppiert
