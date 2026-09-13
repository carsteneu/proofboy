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
Re-Evaluierung mit dem Repo-Evaluator und den eingefrorenen Sets (v11: 131
Laeufe, 112 geloest, 1 ohne Set-Zuordnung).

| Datei | Saetze | Inhalt |
|---|---|---|
| `sft.jsonl` | 160 | (System-Legende + Aufgabe) → verifiziertes Blatt verbatim; Arme B/C/D; je (Set-Version, Task, Arm) ein Satz |
| `dpo.jsonl` | 18 | (prompt, chosen=verifiziert, rejected=nicht bestaetigt), 15 mit Notiz (Cross-Arm/-Version) |
| `rlvr.jsonl` | 176 | Task + Verifier-Kommando (`python3 -m bemyself.msheet run … --json`) + Erwartung (`all_claims_confirmed`) + Gold (Checkpoints/Zertifikat/Zahl) |
| `think.jsonl` | 176 | Task + Denkzone des verifizierten Blatts (Material fuer Denk-Traces; Prosa-RC nur als Laengen-Metadatum) |

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
* **Splits auf Task-Familien** (Tier + Nummern-Suffix: `A-0007` und `A3-0007`
  sind eine Familie), Seed `20260912`, 20/4/4 Familien train/val/test;
  `splits.json` dokumentiert die Zuordnung.

Rebuild (deterministisch; sha256 der Datenfiles stabil):

```bash
python3 training/build_corpus.py \
  --runs /home/carsten/projects/bemyself/.yesmem/tmp/runs-v11-20260912 \
  --runs /home/carsten/projects/bemyself/.yesmem/tmp/runs-v12-20260912 \
  --runs /home/carsten/projects/bemyself/.yesmem/tmp/runs-v13-20260912 \
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
import functools, trl
from training.rlvr import reward           # oder: sys.path + Import wie im Kopf
records = {r["id"]: r for r in map(json.loads, open("training/corpus/rlvr.jsonl"))}
trainer = trl.GRPOTrainer(
    model=model,
    reward_funcs=[functools.partial(reward, records_by_id=records)],
    train_dataset=dataset,                 # Spalte: prompt + record_id
    args=trl.GRPOConfig(output_dir="training/out/rlvr", ...),
)
```

Reward-Vertrag: `REFUTED` → 0.0; sonst `confirmed / target` (target =
`max(min_claims, Referenz-Behauptungen)`). Die Gold-Felder der Saetze dienen
der Leiter-Auswertung, nicht der Belohnung.

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

Der Harness spricht den OpenAI-kompatiblen Endpunkt ueber `BEMYSELF_PROXY_URL`
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
export BEMYSELF_PROXY_URL=http://localhost:8000/v1/chat/completions
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
  Runner-Reward (echter Lauf), Leck-Guard, ENV-Endpunkt, Korpus-Rebuild
  (sha256-stabil) — 27 neue Tests insgesamt.
* Die Datei-/Tokenzahlen im Korpus sind gemessen; alle Kosten-/Dauerangaben
  sind Schaetzungen ohne Messung.
* Kein Push/Merge/Deploy; die Laufverzeichnisse wurden nur gelesen.
