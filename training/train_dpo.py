#!/usr/bin/env python3
"""DPO auf dem Praeferenz-Korpus (GPU-Pfad; Runbook: training/README.md).

Die Korpus-Saetze tragen ``prompt`` (System-Legende + Aufgabe), ``chosen``
(verifiziertes Blatt) und ``rejected`` (nicht bestaetigtes Blatt). Notizen in
``meta.notes`` weisen aus, wenn der verworfene Text aus einem anderen Arm oder
einer anderen Set-Version stammt (Prompt dann aus der gewaehlten Zelle).

    python3 training/train_dpo.py --dry-run --corpus training/corpus/dpo.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_io import read_jsonl, validate_records  # noqa: E402

DEFAULT_CONFIG = Path(__file__).resolve().parent / "configs" / "dpo_qlora.json"


def load_config(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_pairs(records, *, path: str = "<records>") -> None:
    validate_records(records, path=path, require_assistant=False)
    for index, record in enumerate(records):
        for key in ("chosen", "rejected"):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f"{path}[{index}]: {key} fehlt oder ist leer")
        if record["chosen"].strip() == record["rejected"].strip():
            raise ValueError(f"{path}[{index}]: chosen == rejected")


def select_train(records):
    return [record for record in records if record["split"] == "train"]


def build_dpo_rows(records) -> list[dict]:
    """Trainer-Zeilen im TRL-Gespraechsformat.

    ``prompt`` ist die Nachrichtenliste (System-Legende + Aufgabe),
    ``chosen``/``rejected`` sind ebenfalls Gespraechslisten -- ein gemischtes
    Format (Liste + String) entscheidet TRL versionsabhaengig und kann an
    ``example["prompt"] + example["chosen"]`` zerbrechen.
    """
    return [
        {
            "prompt": record["messages"],
            "chosen": [{"role": "assistant", "content": record["chosen"]}],
            "rejected": [{"role": "assistant", "content": record["rejected"]}],
        }
        for record in records
    ]


def is_adapter(path: Path | str) -> bool:
    return (Path(path) / "adapter_config.json").exists()


def dry_run(args) -> int:
    records = read_jsonl(args.corpus)
    validate_pairs(records, path=str(args.corpus))
    config = load_config(args.config)
    train_records = select_train(records)
    chosen_chars = sum(len(record["chosen"]) for record in train_records)
    rejected_chars = sum(len(record["rejected"]) for record in train_records)
    noted = sum(1 for record in train_records if record.get("meta", {}).get("notes"))
    base_model = args.base_model or config["base_model"]
    summary = {
        "mode": "dry-run",
        "corpus": str(args.corpus),
        "config": str(args.config),
        "base_model": base_model,
        "base_model_is_adapter": is_adapter(base_model),
        "out": str(args.out),
        "records": len(records),
        "train_pairs": len(train_records),
        "pairs_with_notes": noted,
        "chosen_chars": chosen_chars,
        "rejected_chars": rejected_chars,
        "beta": config["beta"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def load_model(base_model: str, quantization, config: dict):
    """Basismodell laden -- oder einen SFT-Adapter (dann weiter auf ihm)."""
    from peft import LoraConfig, PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if is_adapter(base_model):
        inner = json.loads(
            (Path(base_model) / "adapter_config.json").read_text(encoding="utf-8")
        )["base_model_name_or_path"]
        model = AutoModelForCausalLM.from_pretrained(
            inner, quantization_config=quantization, device_map="auto"
        )
        model = PeftModel.from_pretrained(model, base_model, is_trainable=True)
        return model, AutoTokenizer.from_pretrained(inner), None
    model = AutoModelForCausalLM.from_pretrained(
        base_model, quantization_config=quantization, device_map="auto"
    )
    lora = LoraConfig(
        r=config["lora"]["r"],
        lora_alpha=config["lora"]["alpha"],
        lora_dropout=config["lora"]["dropout"],
        target_modules=config["lora"]["target_modules"],
        task_type="CAUSAL_LM",
    )
    return model, AutoTokenizer.from_pretrained(base_model), lora


def train(args) -> int:
    import torch
    from datasets import Dataset
    from transformers import BitsAndBytesConfig
    from trl import DPOConfig, DPOTrainer

    config = load_config(args.config)
    base_model = args.base_model or config["base_model"]
    records = read_jsonl(args.corpus)
    validate_pairs(records, path=str(args.corpus))
    train_records = select_train(records)
    if not train_records:
        raise SystemExit("kein train-Satz im Korpus")

    quantization = BitsAndBytesConfig(
        load_in_4bit=config["load_in_4bit"],
        bnb_4bit_quant_type=config["bnb_4bit_quant_type"],
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model, tokenizer, lora = load_model(base_model, quantization, config)
    # ``max_prompt_length`` wird bewusst nicht gesetzt: aeltere TRL-Versionen
    # kennen es, ab 1.0 ist es entfernt -- ohne den Schluessel laeuft beides.
    dpo_config = DPOConfig(
        output_dir=str(args.out),
        beta=config["beta"],
        max_length=config["max_seq_len"],
        num_train_epochs=args.epochs or config["epochs"],
        per_device_train_batch_size=config["per_device_train_batch_size"],
        gradient_accumulation_steps=config["gradient_accumulation_steps"],
        learning_rate=config["learning_rate"],
        lr_scheduler_type=config["lr_scheduler"],
        warmup_ratio=config["warmup_ratio"],
        logging_steps=config["logging_steps"],
        save_strategy=config["save_strategy"],
        bf16=config["bf16"],
        gradient_checkpointing=config["gradient_checkpointing"],
        seed=args.seed or config["seed"],
        report_to="none",
    )
    dataset = Dataset.from_list(build_dpo_rows(train_records))
    trainer = DPOTrainer(
        model=model,
        args=dpo_config,
        train_dataset=dataset,
        peft_config=lora,
        # seit TRL 0.17 Pflicht (ohne Auto-Laden bis 0.18); unabhaengig davon
        # explizit gesetzt, damit die Version nicht ueber den Aufruf entscheidet
        processing_class=tokenizer,
    )
    trainer.train()
    trainer.save_model(str(args.out))
    tokenizer.save_pretrained(str(args.out))
    print(json.dumps({"mode": "train", "out": str(args.out), "pairs": len(train_records)},
                     ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DPO auf dem Praeferenz-Korpus.")
    parser.add_argument("--corpus", default=str(Path(__file__).resolve().parent / "corpus" / "dpo.jsonl"))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--base-model", default=None)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "out" / "dpo"))
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        return dry_run(args)
    return train(args)


if __name__ == "__main__":
    raise SystemExit(main())
