"""Structured configuration for hf_mps LoRA fine-tuning."""

from __future__ import annotations

from dataclasses import dataclass, field

from hydra.core.config_store import ConfigStore


@dataclass
class ModelConfig:
    """Base model identity for fine-tuning.

    Attributes:
        base_model_id: Hugging Face model repo id.
        revision: Exact model revision/commit to pin for reproducibility.
    """

    base_model_id: str = "Qwen/Qwen2.5-1.5B-Instruct"
    revision: str = "main"


@dataclass
class LoraHParams:
    """LoRA adapter hyperparameters.

    Attributes:
        r: LoRA rank.
        alpha: LoRA scaling factor.
        dropout: LoRA dropout probability.
        target_modules: Module name substrings LoRA is applied to.
    """

    r: int = 16
    alpha: int = 32
    dropout: float = 0.05
    target_modules: list[str] = field(
        default_factory=lambda: ["q_proj", "k_proj", "v_proj", "o_proj"]
    )


@dataclass
class DataConfig:
    """Canonical dataset paths consumed by training.

    Attributes:
        train_path: Canonical train.jsonl path.
        valid_path: Canonical valid.jsonl path.
    """

    train_path: str = "data/processed/spider/canonical/train.jsonl"
    valid_path: str = "data/processed/spider/canonical/valid.jsonl"


@dataclass
class TrainHParams:
    """Trainer hyperparameters.

    Attributes:
        per_device_train_batch_size: Micro-batch size per device.
        gradient_accumulation_steps: Steps to accumulate before an optimizer step.
        learning_rate: Peak learning rate.
        num_train_epochs: Number of training epochs.
        warmup_steps: Number of steps used for LR warmup.
        max_seq_length: Maximum tokenized sequence length.
        logging_steps: Steps between log emissions.
        seed: Random seed for reproducibility.
    """

    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 8
    learning_rate: float = 2e-4
    num_train_epochs: float = 3.0
    warmup_steps: int = 50
    max_seq_length: int = 2048
    logging_steps: int = 10
    seed: int = 42


@dataclass
class OutputConfig:
    """Output locations for adapter artifacts.

    Attributes:
        adapter_dir: Directory the trained LoRA adapter and tokenizer are saved to.
    """

    adapter_dir: str = "outputs/hf_mps/spider-lora"


@dataclass
class TrainConfig:
    """Top-level configuration for the hf_mps LoRA fine-tuning entrypoint.

    Attributes:
        model: Base model identity.
        lora: LoRA hyperparameters.
        data: Canonical dataset paths.
        train: Trainer hyperparameters.
        output: Output artifact locations.
    """

    model: ModelConfig = field(default_factory=ModelConfig)
    lora: LoraHParams = field(default_factory=LoraHParams)
    data: DataConfig = field(default_factory=DataConfig)
    train: TrainHParams = field(default_factory=TrainHParams)
    output: OutputConfig = field(default_factory=OutputConfig)


def register_train_configs(store: ConfigStore) -> None:
    """Register the hf_mps training schema for Hydra validation.

    Args:
        store: The ConfigStore instance to populate.
    """
    store.store(name="train_schema", node=TrainConfig)