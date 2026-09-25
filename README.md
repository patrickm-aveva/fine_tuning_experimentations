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

The [Dockerfile](Dockerfile) builds a CUDA image that runs `hf_mps.train` with the
[config/train_cuda.yaml](config/train_cuda.yaml) config (quantized Qwen2.5-1.5B-Instruct LoRA
fine-tune). It only bakes in `pyproject.toml`, `uv.lock`, `src`, `README.md`, and `config` — data
and outputs are not copied into the image and must be mounted as volumes at run time.

### 1. Build the image

From the repo root (needs `uv.lock` present):

```bash
docker build -t fine-tuning-experimentations:cuda .
```

### 2. Run it locally (requires an NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html))

Mount the canonical data and the outputs directory so training data is available and results
persist outside the container:

```bash
docker run --rm --gpus all \
  -v "$(pwd)/data/processed:/app/data/processed" \
  -v "$(pwd)/outputs:/app/outputs" \
  fine-tuning-experimentations:cuda
```

Override Hydra config the same way as the local `train_cuda` runs, e.g. a quick smoke test:

```bash
docker run --rm --gpus all \
  -v "$(pwd)/data/processed:/app/data/processed" \
  -v "$(pwd)/outputs:/app/outputs" \
  fine-tuning-experimentations:cuda \
  --config-dir=config --config-name=train_cuda \
  train.num_train_epochs=1 train.per_device_train_batch_size=1
```

### 3. Run it on a cloud GPU instance

Provision and prepare the instance (NVIDIA driver, verified `nvidia-smi`) first — see
[docs/ec2_gpu_python_setup.md](docs/ec2_gpu_python_setup.md) sections 1–4 for SSH access and driver
install; Docker replaces the `uv`/PyTorch steps in sections 5–9 of that doc.

On the instance:

1. Install Docker Engine and the NVIDIA Container Toolkit (see the
   [NVIDIA Container Toolkit install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)),
   then configure the Docker runtime:

   ```bash
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```

2. Get the repo and data onto the instance, e.g.:

   ```bash
   git clone <this-repo-url> ~/fine_tuning_experimentations
   rsync -avz -e "ssh -i ~/.ssh/<key>.pem" \
     data/processed/ ubuntu@<instance-dns>:~/fine_tuning_experimentations/data/processed/
   ```

3. Build and run exactly as in steps 1–2 above, from `~/fine_tuning_experimentations`:

   ```bash
   docker build -t fine-tuning-experimentations:cuda .
   docker run --rm --gpus all \
     -v "$(pwd)/data/processed:/app/data/processed" \
     -v "$(pwd)/outputs:/app/outputs" \
     fine-tuning-experimentations:cuda
   ```

4. Verify GPU visibility inside the container before a full run. The image's `ENTRYPOINT` is
   fixed to `hf_mps.train`, so override it explicitly to run a plain check:

   ```bash
   docker run --rm --gpus all --entrypoint nvidia-smi fine-tuning-experimentations:cuda
   ```

5. Copy results back after training:

   ```bash
   rsync -avz -e "ssh -i ~/.ssh/<key>.pem" \
     ubuntu@<instance-dns>:~/fine_tuning_experimentations/outputs/ outputs/
   ```

NB! Not yet run end-to-end against a real GPU instance — build and driver/toolkit steps are
untested in practice.

## Cloud GPU setup (EC2, no Docker)

For running fine-tuning directly with `uv` on an NVIDIA GPU EC2 instance instead of Docker, see
[docs/ec2_gpu_python_setup.md](docs/ec2_gpu_python_setup.md) for the full walkthrough (SSH access,
NVIDIA driver install, `uv`-managed Python env, GPU-enabled PyTorch, verification).




