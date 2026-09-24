# training — der Trainingspfad (Korpus v0 + GPU-ready Skripte)

Dieses Verzeichnis macht den Trainings-Pfad vollstaendig vorbereitet — **hier
wird nicht trainiert** (diese Maschine ist CPU-only, Torch ist nicht
installiert). Alles, was ohne GPU pruefbar ist, ist geprueft: der Korpus-Bauer
(TDD), die dry-run-Pfade der Skripte, der Reward gegen den echten Runner, der
Leck-Guard der Denk-Trace-Destillation und der per ENV umstellbare
Harness-Endpunkt.

## Inhalt

| Datei | Zweck |
|---|---|
| `build_corpus.py` | Baut den Korpus aus den Experiment-Laeufen (v11/v12/v13); Labels strikt maschinell |
| `corpus/` | Korpus v0 (committet: `sft.jsonl`, `dpo.jsonl`, `rlvr.jsonl`, `think.jsonl`, `splits.json`, `manifest.json`) |
| `corpus_io.py` | Gemeinsame JSONL-Validierung/Statistik |
| `train_sft.py` | QLoRA-SFT (TRL `SFTTrainer`) — `--dry-run` laeuft ohne Torch |
| `train_dpo.py` | DPO (TRL `DPOTrainer`) — `--dry-run` laeuft ohne Torch |
| `rlvr.py` | RLVR-Skizze: Reward = Maschinenverdikt des Runners (GRPOTrainer-Andockpunkt) |
| `distill_thinking.py` | Geruest: Task + verifiziertes Blatt → Notation-Denk-Trace (mit Leck-Guard) |
| `configs/*.json` | Trainings-Configs (JSON, damit die dry-runs sie stdlib-validieren koennen) |
| `requirements-gpu.txt` | Pakete fuer die gemietete CUDA-Maschine (hier NICHT installieren) |
| `EVALPLAN.md` | Leiter: Basis vs. LoRA vs. DPO/RLVR auf denselben Faellen |

## Korpus v0

Quellen (nur lesend): `.yesmem/tmp/runs-v11-20260912/`,
`runs-v12-20260912/`, `runs-v13-20260912/` (Set-Versionen v0.1/v0.2/v0.3).
436 Arm-Laeufe gescannt; Labels aus `summary.json` (v12/v13) bzw. per
Re-Evaluierung mit dem Repo-Evaluator und den eingefrorenen Sets (v11: 132
gescannt, 131 re-evaluiert, 112 geloest, 1 ohne Set-Zuordnung). Die
Re-Evaluierung nutzt den Evaluator des aktuellen Stands -- fuer die beiden
cyc-Zellen der v0.1-Sets (B-0011/B-0012) kann das Label dadurch vom
Originallauf abweichen (Fenster: `evaluate_answer` und das Zyklus-Scoring
entstanden erst mit den v12-Laeufen).

| Datei | Saetze | Inhalt |
|---|---|---|
| `sft.jsonl` | 160 | (System-Legende + Aufgabe) → verifiziertes Blatt verbatim; Arme B/C/D; je (Set-Version, Task, Arm) ein Satz |
| `dpo.jsonl` | 18 | (prompt, chosen=verifiziert, rejected=nicht bestaetigt), 15 mit Notiz (Cross-Arm/-Version) |
| `rlvr.jsonl` | 176 | Task + Verifier-Kommando (`python3 -m proofboy.msheet run … --json`) + Erwartung + Gold (Checkpoints/Zertifikat/Zahl) |
| `think.jsonl` | 176 | Task + Denkzone des verifizierten Blatts (Material fuer Denk-Traces; Prosa-RC nur als Laengen-Metadatum; ein Satz traegt eine leere Denkzone -- datentreu, das Blatt hat keine Denkzeilen) |

Zwei Verifier-Modi in `rlvr.jsonl` (maschinell aus dem Aufgabentyp abgeleitet):

* `all_claims_confirmed` mit `min_claims` -- Aufgaben mit Behauptungszone: alle
  Behauptungen des abgegebenen Blatts muessen CONFIRMED sein;
* `checkpoints_all_matched` mit `checkpoints_total` -- Trace-Aufgaben ohne
  Behauptungsblock (v0.1-Format ``S<n>: cp <t>: (…)``): die Konfigurationspunkte
  werden wie im Original-Harness abgeglichen.

Regeln, die der Bauer durchsetzt (und die Tests festhalten):

* **Nur maschinelle Labels.** Kein Label wird aus Prosa abgeleitet; v11 laeuft
  durch denselben Evaluator wie die Original-Laeufe.
* **Saubere Blaetter fuer SFT/DPO.** Ein Lauf kann auf Trace-Aufgaben
  „geloest" sein (Checkpoint-Gleichheit), waehrend das Blatt selbst z.B. eine
  `sim`-Zeugen ohne Maschinenbindung traegt → Runner-Verdikt UNVERIFIABLE.
  Solche Blaetter werden als SFT-Ziel und als DPO-`chosen` verworfen (16 bzw.
  3 Faelle, `manifest.json → counts.filtered`), bleiben aber in `rlvr.jsonl`
  (dort ist gerade die Uebung „UNVERIFIABLE → CONFIRMED" das Signal) und in
  `think.jsonl` erhalten.
* **Dedup je (Set-Version, Task, Arm).** Wiederholungen derselben Zelle fallen
  weg; v11- und v12-Saetze derselben Aufgabe bleiben, weil sie verschiedene
  Legenden tragen.
* **SFT-Ziel:** der Runden-0-Prompt (System-Legende + Aufgabe) mit der Antwort
  der **ersten geloesten Runde** als Assistant-Teil; `meta.round` weist aus,
  welche Runde das war (bei reparierten Zellen also die korrigierte Fassung).
* **Splits auf Task-Familien** (Tier + Nummern-Suffix: `A-0007` und `A3-0007`
  sind eine Familie), Seed `20260912`, 20/4/4 Familien train/val/test;
  `splits.json` dokumentiert die Zuordnung.

Rebuild (deterministisch; sha256 der Datenfiles stabil). Fragilitaet, die man
kennen muss: die Quell-Laeufe liegen unter `.yesmem/tmp/` und sind
**gitignoriert** -- nach einem Clone/`git clean -xdf` ist der Korpus nicht mehr
re-derivierbar (nur noch trainierbar). Auch der Ordnername zaehlt:
`runs-v<ziffern>…`, sonst faellt die Zuordnung zu den Set-Versionen still aus
(der Lauf bleibt dann `unresolved`).

```bash
python3 training/build_corpus.py \
  --runs /home/carsten/projects/proofboy/.yesmem/tmp/runs-v11-20260912 \
  --runs /home/carsten/projects/proofboy/.yesmem/tmp/runs-v12-20260912 \
  --runs /home/carsten/projects/proofboy/.yesmem/tmp/runs-v13-20260912 \
  --out training/corpus
```

## GPU-Runbook (gemietete CUDA-Maschine)

Alle Zahlen in §0 sind **Schaetzungen** (Stand 2026-09-13, Preise schwanken);
gemessen ist auf dieser Maschine nichts.

### 0. Kostenbild (Schaetzung)

| Posten | Groesse | Schaetzung |
|---|---|---|
| GPU RTX 4090 24 GB (Community-Clouds) | 8B-QLoRA geht bequem in 24 GB (seq 4096) | ~0,30–0,60 $/h |
| GPU A100 80 GB | mehr Luft fuer DPO/laengere Sequenzen | ~1,50–2,50 $/h |
| SFT-Lauf | 160 Saetze × 3 Epochen, seq ≤ 4096 | ~0,3–1,0 h → < 1 $ |
| DPO-Lauf | 18 Paare × 1 Epoche | Minuten |
| Leiter-Auswertung (176 Laeufe, Arme B/C/D) | je nach Modell 30–120 s pro Lauf | ~2–5 h → ~1–3 $ |
| **Erster Durchlauf komplett** | | **grob 5–15 $** |

### 1. Maschine + Umgebung

```bash
# auf der gemieteten Maschine (Repo klonen/kopieren), dann:
python3 -m venv .venv && source .venv/bin/activate
pip install -r training/requirements-gpu.txt
nvidia-smi   # CUDA sichtbar?
```

### 2. SFT

```bash
python3 training/train_sft.py --dry-run          # Korpus/Config pruefen (CPU ok)
python3 training/train_sft.py --corpus training/corpus/sft.jsonl \
    --config training/configs/sft_qlora.json --out training/out/sft
```

### 3. DPO (nach dem SFT)

```bash
python3 training/train_dpo.py --dry-run
python3 training/train_dpo.py --corpus training/corpus/dpo.jsonl \
    --config training/configs/dpo_qlora.json --out training/out/dpo \
    --base-model training/out/sft        # auf dem SFT-Adapter weiter
```

### 4. RLVR (Skizze)

`training/rlvr.py` liefert den Reward gegen den Runner; als GRPO-Reward:

```python
import functools, json, trl
from training.rlvr import reward
records = {r["id"]: r for r in map(json.loads, open("training/corpus/rlvr.jsonl"))}
dataset = [{"prompt": r["messages"], "record_id": r["id"]} for r in records.values()]
trainer = trl.GRPOTrainer(
    model=model,
    reward_funcs=[functools.partial(reward, records_by_id=records)],
    train_dataset=dataset,          # Spalten: prompt + record_id (Name zaehlt!)
    args=trl.GRPOConfig(output_dir="training/out/rlvr", ...),
)
```

Reward-Vertrag (`reward(completions, prompts, record_id, …)` -- TRLs Aufruf,
Dataset-Spalte `record_id`): `REFUTED` → 0.0 (fail closed); Behauptungszellen
`confirmed / max(min_claims, Referenz-Behauptungen)`; Checkpoint-Zellen
`matched / total` gegen die Aufgaben-Zielpunkte; kein Referenzmaterial → 0.0 mit
`reason = "no_reference"`. Blaetter laufen mit `sandbox="require"`; `sandboxed`
(True/False/None = keine py:-Zeugen) steht im Ergebnis. Die Gold-Felder dienen
sonst der Leiter-Auswertung.

### 5. Adapter servieren + Harness gegen die eigene Instanz

```bash
# Variante A: Adapter mergen und das gemergte Modell servieren
python3 - <<'PY'
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
base = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-8B", torch_dtype="auto")
model = PeftModel.from_pretrained(base, "training/out/sft").merge_and_unload()
model.save_pretrained("training/out/sft-merged")
AutoTokenizer.from_pretrained("Qwen/Qwen3-8B").save_pretrained("training/out/sft-merged")
PY
vllm serve training/out/sft-merged --served-model-name deepseek-flash --port 8000
```

Der Harness spricht den OpenAI-kompatiblen Endpunkt ueber `PROOFBOY_PROXY_URL`
an (Default `http://localhost:9099/v1/chat/completions`); der Modellname im
Request ist `deepseek-flash`, deshalb `--served-model-name deepseek-flash`.
Zwei Stolpersteine:

* Der Harness liest den API-Schluessel aus
  `~/.local/share/opencode/auth.json` (`{"deepseek": {"key": "…"}}`). Auf der
  gemieteten Maschine existiert die Datei nicht — fuer vLLM (ohne Auth) genuegt
  ein Dummy: `mkdir -p ~/.local/share/opencode && printf '{"deepseek":{"key":"dummy"}}' > ~/.local/share/opencode/auth.json`.
* Die Laeufe landen in `.yesmem/tmp/runs/` **des jeweiligen Checkouts** — am
  besten einen eigenen Checkout der Basis-Commit-Position dafuer benutzen.

```bash
export PROOFBOY_PROXY_URL=http://localhost:8000/v1/chat/completions
python3 yesdocs/deepseek-math-notation/tooling/harness.py dry --arm C --task B3-0001
python3 yesdocs/deepseek-math-notation/tooling/harness.py one --arm C --task B3-0001 --rep 1
python3 yesdocs/deepseek-math-notation/tooling/harness.py batch --arms B,C,D --reps 1 --tier-a 16 --tier-b 8
```

### 6. Leiter-Auswertung

Siehe `training/EVALPLAN.md`: Basis vs. LoRA auf denselben Leiter-Faellen
(Sets v0.3, Arme B/C/D), gleiche Metriken wie in der Haerte-Runde (05-10).

## Ehrlichkeit (Stand 2026-09-13)

* Der Trainingspfad ist **nicht ausgefuehrt** (keine GPU, kein Torch auf dieser
  Maschine). Geprueft sind: Kompilat aller Skripte, dry-run-Validierung,
  Runner-Reward in beiden Modi (echte Laeufe), Leck-Guard, ENV-Endpunkt,
  Korpus-Rebuild (sha256-stabil) — die Suite steht bei 856 Tests (818 Basis + 38 neue; Lauf: `python3 -m unittest discover -s tests`).
* Der TRL-Aufruf ist gegen die deklarierte Spanne (`trl>=0.17` bis 1.x)
  gebaut: `processing_class` ist immer gesetzt, `max_prompt_length` nur, wenn
  die installierte Version das Feld kennt (Altversionen kuerzen sonst still auf
  512 Tokens vom Prompt-Anfang), chosen/rejected sind Gespraechslisten. Auf einer
  konkreten Installation gehoert das trotzdem einmal mit `--dry-run` und einem
  Mini-Lauf geprueft -- auf einer CPU-Maschine ist keiner dieser Pfade
  ausfuehrbar.
* Die Datei-/Tokenzahlen im Korpus sind gemessen; alle Kosten-/Dauerangaben
  sind Schaetzungen ohne Messung.
* Kein Push/Merge/Deploy; die Laufverzeichnisse wurden nur gelesen.
