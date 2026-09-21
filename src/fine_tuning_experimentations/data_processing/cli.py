"""Hydra entrypoint for building canonical Spider datasets."""

from __future__ import annotations

import hydra
from hydra.core.config_store import ConfigStore

from fine_tuning_experimentations.config.schema import (
    PrepareSpiderConfig,
    register_configs,
)
from fine_tuning_experimentations.data_processing.prepare_spider import prepare_spider

register_configs(ConfigStore.instance())


@hydra.main(version_base=None, config_name="prepare_spider_schema")
def main(cfg: PrepareSpiderConfig) -> None:
    """Build canonical Spider JSONL splits from the resolved configuration.

    Args:
        cfg: Hydra-resolved PrepareSpiderConfig.

    Returns:
        None.
    """
    split_records = prepare_spider(cfg)
    for name, records in split_records.items():
        print(f"{name}: wrote {len(records)} records")


if __name__ == "__main__":
    main()
