"""Structured configuration schemas registered with Hydra's ConfigStore."""

from __future__ import annotations

from dataclasses import dataclass, field

from hydra.core.config_store import ConfigStore

from fine_tuning_experimentations.data_processing.prepare_spider import (
    SYSTEM_PROMPT,
)


@dataclass
class PathsConfig:
    """Filesystem roots used by every pipeline stage.

    Attributes:
        raw_dir: Directory holding raw Spider JSON and `tables.json`.
        processed_dir: Root of generated dataset views.
        canonical_dir: Canonical backend-neutral JSONL output directory.
    """

    raw_dir: str = "data/spider_data"
    processed_dir: str = "data/processed/spider"
    canonical_dir: str = "data/processed/spider/canonical"


@dataclass
class PromptConfig:
    """Versioned prompt contract shared by all backends.

    Attributes:
        system_prompt: System message defining the task.
        template_version: Identifier recorded in every emitted record.
    """

    system_prompt: str = SYSTEM_PROMPT
    template_version: str = "spider-prompt-v1"


@dataclass
class SplitConfig:
    """One canonical output split built from one or more raw Spider files.

    Attributes:
        name: Canonical split name, e.g. `train` or `valid`.
        sources: Raw Spider JSON file names relative to the raw directory.
    """

    name: str = "train"
    sources: list[str] = field(default_factory=lambda: ["train_spider.json"])


@dataclass
class PrepareSpiderConfig:
    """Top-level configuration for the canonical preprocessing entrypoint.

    Attributes:
        paths: Filesystem roots.
        prompt: Prompt contract.
        splits: Canonical splits to emit.
        tables_file: Schema metadata file name inside the raw directory.
        write_manifest: Whether to write `manifest.json` beside the splits.
    """

    paths: PathsConfig = field(default_factory=PathsConfig)
    prompt: PromptConfig = field(default_factory=PromptConfig)
    splits: list[SplitConfig] = field(
        default_factory=lambda: [
            SplitConfig(name="train", sources=["train_spider.json"]),
            SplitConfig(name="valid", sources=["dev.json"]),
        ]
    )
    tables_file: str = "tables.json"
    write_manifest: bool = True


def register_configs(store: ConfigStore) -> None:
    """Register structured config schemas for Hydra validation.

    Args:
        store: The ConfigStore instance to populate.
    """
    store.store(name="prepare_spider_schema", node=PrepareSpiderConfig)
    store.store(group="paths", name="default_schema", node=PathsConfig)
    store.store(group="prompt", name="spider_v1_schema", node=PromptConfig)