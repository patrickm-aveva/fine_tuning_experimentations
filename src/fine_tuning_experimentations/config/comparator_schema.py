"""Structured configuration for the base-vs-fine-tuned comparison comparator."""

from __future__ import annotations

from dataclasses import dataclass, field

from hydra.core.config_store import ConfigStore


@dataclass
class ComparatorModelConfig:
    """Base model and adapter identity for the comparator.

    Attributes:
        base_model_id: Hugging Face model repo id, must match the id used for training.
        revision: Exact model revision/commit to pin for reproducibility.
        adapter_dir: Directory containing the trained LoRA adapter and tokenizer.
    """

    base_model_id: str = "Qwen/Qwen2.5-1.5B-Instruct"
    revision: str = "main"
    adapter_dir: str = "outputs/hf_mps/spider-lora"


@dataclass
class ComparatorDataConfig:
    """Canonical dataset and database paths consumed by the comparator.

    Attributes:
        valid_path: Canonical valid.jsonl path.
        database_root: Root directory of per-db_id SQLite databases.
    """

    valid_path: str = "data/processed/spider/canonical/valid.jsonl"
    database_root: str = "data/spider_data/database"


@dataclass
class SampleConfig:
    """Example-selection settings for one comparison run.

    Attributes:
        mode: "random" to draw a seeded sample, or "all" for the full split.
        size: Number of examples to sample when mode is "random".
        seed: Random seed for reproducible sampling.
    """

    mode: str = "random"
    size: int = 20
    seed: int = 42


@dataclass
class GenerationConfig:
    """Generation settings shared by base and fine-tuned inference.

    Attributes:
        max_new_tokens: Maximum tokens to generate per prediction.
        do_sample: Whether to sample; False for deterministic SQL output.
    """

    max_new_tokens: int = 256
    do_sample: bool = False


@dataclass
class ServerConfig:
    """Local Gradio server binding.

    Attributes:
        host: Interface to bind the server to.
        port: Port to serve the comparator on.
    """

    host: str = "127.0.0.1"
    port: int = 7860


@dataclass
class ComparatorConfig:
    """Top-level configuration for the base-vs-fine-tuned comparator.

    Attributes:
        model: Base model and adapter identity.
        data: Canonical dataset and database paths.
        sample: Example-selection settings.
        generation: Shared generation settings.
        server: Local server binding.
    """

    model: ComparatorModelConfig = field(default_factory=ComparatorModelConfig)
    data: ComparatorDataConfig = field(default_factory=ComparatorDataConfig)
    sample: SampleConfig = field(default_factory=SampleConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


def register_comparator_configs(store: ConfigStore) -> None:
    """Register the comparator schema for Hydra validation.

    Args:
        store: The ConfigStore instance to populate.
    """
    store.store(name="comparator_schema", node=ComparatorConfig)