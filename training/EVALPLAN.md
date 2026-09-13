# EVALPLAN — Basis vs. LoRA (und spaeter DPO/RLVR) auf denselben Leitern

Die Frage dieses Plans: **Traegt ein Training auf dem eigenen Korpus die
Notation?** Gemessen wird auf denselben Faellen, mit denselben Metriken und
demselben maschinellen Urteil wie in der Haerte-Runde (05-10) — nicht mit
Urteilen des Trainers.

## Leiter

| Stufe | Was laeuft | Zweck |
|---|---|---|
| 0 | **Referenz (Bestand):** v13-Laeufe (Sets v0.3, Arme K/B/C/D), Tier A-hard 96/96, Tier B-hard 29/32 final, 0 Falschbestaetigungen (05-10 §5) | Anker; API-Modell ist die Messlatte, die die 8B-Vertreter schlagen oder belegen sollen |
| 1 | **Basis** (Qwen3-8B unveraendert) auf Sets v0.3, Arme B/C/D, 1 Wiederholung | Vorher-Linie ohne Training |
| 2 | **LoRA-SFT** (`training/out/sft`) auf denselben Faellen | Notationstreue + Trefferquote |
| 3 | **DPO** (`training/out/dpo`), dann **RLVR** (Runner-Reward) | Verstaerkung der Praeferenz; RLVR nur, wenn Stufe 2 stabil |

Kommandos: `training/README.md` §5/§6 (Harness gegen `BEMYSELF_PROXY_URL`,
Sets v0.3, gleiche Arme). Jede Stufe ist reproduzierbar aus dem Basis-Commit
plus Korpus; Laeufe landen in `.yesmem/tmp/runs/` des Checkouts.

## Metriken (identisch zur Haerte-Runde)

* **Notationstreue / RC-Treue:** Anteil Blaetter ohne Formatfehler
  (`format_errors == 0`), Anteil Blaetter mit ≥ 1 CONFIRMED-Behauptung,
  Verdikt-Verteilung (CONFIRMED / UNVERIFIABLE / REFUTED).
* **Trefferquote:** tier-typisierter Endzustand je Zelle
  (`evaluate_answer`: Zahl exakt resp. alle Checkpoints exakt resp. Zertifikat
  maschinenverifiziert) — roh und final (nach Reparaturrunden).
* **Token-Oekonomie:** completion/reasoning-Tokens je Lauf, Tokens je geloestem
  Lauf (das Kosten-Regime aus 05-10 §5.5 bleibt der Vergleichsanker).
* **Falschbestaetigungen:** Runden mit lauter CONFIRMED-Behauptungen, aber
  nicht bestaetigtem Endzustand. Ziel 0; **jeder** Fall ist ein Vorfall.
* **Unpruefbar-Quote:** Referenz ~26,6 % (Tier-A/B gemischt, v13); nicht
  „wegoptimieren", sondern beobachten — UNVERIFIABLE ist die ehrliche Antwort.

## Erwartungen — und was davon ehrlich ist

* **Korpus ist klein:** 160 SFT-Saetze, 18 DPO-Paare, 28 Task-Familien.
  Erwartbar ist ein Sichtbarmachen der Notationstreue (Format-Rate), **keine**
  Signifikanzaussagen — n = 8 je Arm in Tier B, eine Wiederholung.
* **GO/NO-GO:** SFT behalten, wenn Falschbestaetigungen 0 bleiben **und** die
  Trefferquote nicht unter die Basis faellt; LoRA verwerfen, wenn die
  Format-Rate nicht steigt oder die Modellausgaben kollabieren.
  DPO nur nach stabilem SFT; RLVR nur, wenn die Reward-Kurve im Lauf steigt,
  ohne die Falschbestaetigungsrate zu heben.
* **Der 8B-Stand-in ist nicht das API-Zielmodell.** Uebertragbar ist die
  Methodik (Legende, Format, Zeugen); die absoluten Ziffern sind es nicht.
* **Sandbox auf der GPU-Kiste:** `py:`-Zeugen laufen in `training/build_corpus.py`
  und `training/rlvr.py` mit `sandbox="require"` (Default) -- fehlt `bwrap`,
  werden die Blaetter UNVERIFIABLE und fallen aus SFT/DPO bzw. liefern 0 Reward,
  statt still unsandboxed zu rechnen. Der Harness selbst hat weiterhin seinen
  `--sandbox auto`-Default; fuer fremde Blaetter dort ebenfalls `require` nutzen.
* **Splits:** train/val/test sind auf Task-Familien gezogen; die Leiter-Faelle
  selbst sind Saetze v0.3 — sie sind teilweise Trainingsmaterial (Tier A/B).
  Fuer saubere Verallgemeinerungsaussagen muessten neue Aufgaben (neue Familien)
  gehalten werden; das ist der naechste Schritt, nicht dieser Plan.

## Artefakte je Lauf

1. `training/corpus/manifest.json` (sha256 je Korpus-Datei, Quellen, Filter),
2. Harness-Ausgaben unter `.yesmem/tmp/runs-*` (summary.json je Zelle),
3. Vergleichstabelle Stufe 0–3 (05-10-Stil) im Wiki,
4. Verdikt: behalten/verwerfen je Stufe mit den drei GO/NO-GO-Kriterien.
