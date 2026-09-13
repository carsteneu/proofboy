#!/usr/bin/env python3
"""QLoRA-SFT auf dem Trainingskorpus (GPU-Pfad; Runbook: training/README.md).

Dieses Skript laeuft auf der CPU-Maschine nur im ``--dry-run``-Modus: der
validiert Korpus und Config ohne Torch. Der Trainingspfad importiert
torch/transformers/peft/trl erst beim Aufruf, damit der Modulkopf ueberall
import-sicher bleibt.

    python3 training/train_sft.py --dry-run --corpus training/corpus/sft.jsonl
    # auf der gemieteten GPU:
    python3 training/train_sft.py --corpus training/corpus/sft.jsonl \
        --config training/configs/sft_qlora.json --out training/out/sft
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_io import corpus_stats, read_jsonl, validate_records  # noqa: E402

DEFAULT_CONFIG = Path(__file__).resolve().parent / "configs" / "sft_qlora.json"


def load_config(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def select_records(records, splits):
    return [record for record in records if record["split"] in splits]


def dry_run(args) -> int:
    records = read_jsonl(args.corpus)
    validate_records(records, path=str(args.corpus))
    config = load_config(args.config)
    splits = tuple(part.strip() for part in args.splits.split(",") if part.strip())
    selected = select_records(records, splits)
    stats = corpus_stats(selected)
    summary = {
        "mode": "dry-run",
        "corpus": str(args.corpus),
        "config": str(args.config),
        "base_model": args.base_model or config["base_model"],
        "splits": list(splits),
        "out": str(args.out),
        "lora": config["lora"],
        "max_seq_len": config["max_seq_len"],
        **stats,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def train(args) -> int:
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    config = load_config(args.config)
    base_model = args.base_model or config["base_model"]
    records = select_records(read_jsonl(args.corpus), ("train", "val"))
    validate_records(records, path=str(args.corpus))
    train_records = [record for record in records if record["split"] == "train"]
    eval_records = [record for record in records if record["split"] == "val"]
    if not train_records:
        raise SystemExit("kein train-Satz im Korpus")

    quantization = BitsAndBytesConfig(
        load_in_4bit=config["load_in_4bit"],
        bnb_4bit_quant_type=config["bnb_4bit_quant_type"],
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        base_model, quantization_config=quantization, device_map="auto"
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    lora = LoraConfig(
        r=config["lora"]["r"],
        lora_alpha=config["lora"]["alpha"],
        lora_dropout=config["lora"]["dropout"],
        target_modules=config["lora"]["target_modules"],
        task_type="CAUSAL_LM",
    )
    sft_config = SFTConfig(
        output_dir=str(args.out),
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
    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=Dataset.from_list([{"messages": record["messages"]} for record in train_records]),
        eval_dataset=Dataset.from_list([{"messages": record["messages"]} for record in eval_records]) if eval_records else None,
        peft_config=lora,
    )
    trainer.train()
    trainer.save_model(str(args.out))
    tokenizer.save_pretrained(str(args.out))
    print(json.dumps({"mode": "train", "out": str(args.out), "train": len(train_records),
                      "val": len(eval_records)}, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="QLoRA-SFT auf dem Trainingskorpus.")
    parser.add_argument("--corpus", default=str(Path(__file__).resolve().parent / "corpus" / "sft.jsonl"))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--base-model", default=None)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "out" / "sft"))
    parser.add_argument("--splits", default="train,val")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        return dry_run(args)
    return train(args)


if __name__ == "__main__":
    raise SystemExit(main())
