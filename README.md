# fine_tuning_experimentations

## Quick start

All commands below must be run from the **repo root** — every entrypoint uses paths (data,
config, output dirs) relative to that directory, and will fail with `FileNotFoundError` if run
from inside `src/`.

There are two environments:

- `.venv` — base env, used for data preprocessing (only needs `hydra-core`).
- `.venv-hf` — `hf` extras (`torch`, `transformers`, `peft`, `trl`, `gradio`), used for
  fine-tuning and the comparator. Create/update it with `uv sync --extra hf --active` after
  activating it once.
- NB! `.venv-mlx` is currently not used. It has been created for possible use of `mlx-lm` in the future.

Each step below shows both ways to run it: with the relevant venv activated (`source
.venv.../bin/activate` once per shell), or without activating anything by calling that venv's
`python` binary directly.

### 1. Data preprocessing

Builds canonical Spider JSONL (`data/processed/spider/canonical/{train,valid}.jsonl`) from raw
Spider data. Uses the base env.

With `.venv` activated:

```bash
source .venv/bin/activate
python -m fine_tuning_experimentations.data_processing.cli
```

Without activating:

```bash
.venv/bin/python -m fine_tuning_experimentations.data_processing.cli
```

Optional YAML overrides ([config/data_preprocessing.yaml](config/data_preprocessing.yaml)):

```bash
.venv/bin/python -m fine_tuning_experimentations.data_processing.cli \
  --config-dir=config --config-name=data_preprocessing
```

### 2. Fine-tuning

Trains a LoRA adapter on the canonical data. Uses `.venv-hf`. Each run gets its own timestamped
output directory under `outputs/hf_mps/spider-lora/<run_name>/`.

With `.venv-hf` activated:

```bash
source .venv-hf/bin/activate
python -m fine_tuning_experimentations.hf_mps.train
```

Without activating:

```bash
.venv-hf/bin/python -m fine_tuning_experimentations.hf_mps.train
```

Optional YAML overrides ([config/train_hf.yaml](config/train_hf.yaml)), or ad hoc CLI overrides,
e.g. a quick smoke test:

```bash
.venv-hf/bin/python -m fine_tuning_experimentations.hf_mps.train \
  --config-dir=config --config-name=train_hf \
  train.num_train_epochs=1 train.per_device_train_batch_size=1
```

### 3. Comparison bench

Launches a local Gradio app comparing the base model against a trained adapter side by side.
Also uses `.venv-hf`.

With `.venv-hf` activated:

```bash
source .venv-hf/bin/activate
python -m fine_tuning_experimentations.hf_mps.comparator
```

Without activating:

```bash
.venv-hf/bin/python -m fine_tuning_experimentations.hf_mps.comparator
```

This blocks and prints a local URL (default `http://127.0.0.1:7860`) — open it in a browser. Point
it at a specific trained run with an override, since adapter output directories are timestamped:

```bash
.venv-hf/bin/python -m fine_tuning_experimentations.hf_mps.comparator \
  model.adapter_dir=outputs/hf_mps/spider-lora/2026-09-23_14-30-05 \
  sample.size=10
```

## Using Docker on a Cloud Instance
NB! Currently untested. 




