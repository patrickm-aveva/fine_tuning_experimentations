"""Hydra entrypoint for hf_mps LoRA fine-tuning on canonical Spider data."""

from __future__ import annotations

import logging

import hydra
import torch
from datasets import load_dataset
from hydra.core.config_store import ConfigStore
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, PreTrainedTokenizerBase
from trl import SFTConfig, SFTTrainer

from fine_tuning_experimentations.config.train_schema import (
    TrainConfig,
    register_train_configs,
)

from fine_tuning_experimentations.hf_mps.device import resolve_device, resolve_dtype

logger = logging.getLogger(__name__)

register_train_configs(ConfigStore.instance())

def load_canonical_datasets(train_path: str, valid_path: str) -> tuple:
    """Load canonical train/valid JSONL splits as Hugging Face datasets.

    Args:
        train_path: Path to canonical train.jsonl.
        valid_path: Path to canonical valid.jsonl.

    Returns:
        Tuple of (train_dataset, valid_dataset).
    """
    raw = load_dataset("json", data_files={"train": train_path, "validation": valid_path})
    result = (raw["train"], raw["validation"])
    return result


def format_example(example: dict, tokenizer: PreTrainedTokenizerBase) -> dict:
    """Render one canonical record's chat messages into trainer-ready text.

    Args:
        example: Canonical record with a "messages" field.
        tokenizer: Tokenizer providing the model's chat template.

    Returns:
        The example with an added "text" field.
    """
    example["text"] = tokenizer.apply_chat_template(example["messages"], tokenize=False)
    return example


def build_lora_config(cfg: TrainConfig) -> LoraConfig:
    """Build a PEFT LoRA configuration from the resolved training config.

    Args:
        cfg: Resolved TrainConfig.

    Returns:
        A LoraConfig for SFTTrainer.
    """
    lora_config = LoraConfig(
        r=cfg.lora.r,
        lora_alpha=cfg.lora.alpha,
        lora_dropout=cfg.lora.dropout,
        target_modules=list(cfg.lora.target_modules),
        bias="none",
        task_type="CAUSAL_LM",
    )
    return lora_config


@hydra.main(version_base=None, config_name="train_schema")
def main(cfg: TrainConfig) -> None:
    """Fine-tune a causal LM with LoRA on canonical Spider data via hf_mps.

    Args:
        cfg: Hydra-resolved TrainConfig.

    Returns:
        None.
    """
    device = resolve_device()
    dtype = resolve_dtype(device)
    logger.info("Using device: %s", device)

    tokenizer = AutoTokenizer.from_pretrained(cfg.model.base_model_id, revision=cfg.model.revision)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        cfg.model.base_model_id,
        revision=cfg.model.revision,
        torch_dtype=dtype,
    ).to(device)

    train_dataset, valid_dataset = load_canonical_datasets(cfg.data.train_path, cfg.data.valid_path)
    train_dataset = train_dataset.map(lambda example: format_example(example, tokenizer))
    valid_dataset = valid_dataset.map(lambda example: format_example(example, tokenizer))

    training_args = SFTConfig(
        output_dir=cfg.output.adapter_dir,
        per_device_train_batch_size=cfg.train.per_device_train_batch_size,
        gradient_accumulation_steps=cfg.train.gradient_accumulation_steps,
        learning_rate=cfg.train.learning_rate,
        num_train_epochs=cfg.train.num_train_epochs,
        warmup_steps=cfg.train.warmup_steps,
        logging_steps=cfg.train.logging_steps,
        save_strategy="epoch",
        eval_strategy="epoch",
        bf16=(dtype == torch.bfloat16),
        fp16=(dtype == torch.float16),
        max_length=cfg.train.max_seq_length,
        dataset_text_field="text",
        report_to=[],
        seed=cfg.train.seed,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=valid_dataset,
        peft_config=build_lora_config(cfg),
        processing_class=tokenizer,
    )

    trainer.train()
    trainer.save_model(cfg.output.adapter_dir)
    tokenizer.save_pretrained(cfg.output.adapter_dir)


if __name__ == "__main__":
    main()