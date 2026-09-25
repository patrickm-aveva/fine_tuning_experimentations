# EC2 GPU Python Environment Setup

This guide records the setup of an Ubuntu 24.04 GPU-backed EC2 instance for private GitHub access, NVIDIA Server Driver 580, Docker GPU workloads, `uv`, and Python development.

## Confirmed environment

- EC2 user: `ubuntu`
- EC2 host: `ec2-16-171-11-214.eu-north-1.compute.amazonaws.com`
- Local EC2 key: `~/.ssh/pm_g5xl_eu-north-1_1.pem`
- Repository: `patrickm-aveva/fine_tuning_experimentations`
- GPU: NVIDIA A10G, 23,028 MiB
- NVIDIA driver: 580.178.04
- Docker: 29.1.3

Commands run on the EC2 instance unless marked **Mac**.

---

## 1. Connect from the Mac

```bash
chmod 400 ~/.ssh/pm_g5xl_eu-north-1_1.pem

ssh -i ~/.ssh/pm_g5xl_eu-north-1_1.pem \
  ubuntu@ec2-16-171-11-214.eu-north-1.compute.amazonaws.com
```

Always provide the key path. A bare filename is resolved relative to the current directory.

## 2. Confirm the operating system and GPU

```bash
cat /etc/os-release
uname -m
lspci | grep -i nvidia
```

Do not continue if the instance does not expose an NVIDIA GPU.

## 3. Install system prerequisites

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y \
  build-essential curl git pkg-config ca-certificates \
  ubuntu-drivers-common linux-headers-$(uname -r)
```

If a newer kernel was installed:

```bash
sudo reboot
```

Reconnect using the command in section 1.

## 4. Install NVIDIA Server Driver 580

```bash
sudo ubuntu-drivers list --gpgpu
apt-cache policy nvidia-driver-580-server
sudo apt install -y nvidia-driver-580-server
sudo reboot
```

Do not install only `nvidia-utils-580-server`, and do not mix Ubuntu packages with NVIDIA `.run` installers.

After reconnecting:

```bash
nvidia-smi
cat /proc/driver/nvidia/version
lsmod | grep nvidia
```

The driver version should begin with `580.`.

## 5. Configure private GitHub access

The EC2 login key authenticates the Mac to EC2. Create a separate key on the instance for GitHub.

```bash
ssh-keygen -t ed25519 \
  -C "ec2-eu-north-1-fine-tuning" \
  -f ~/.ssh/github_ed25519

chmod 700 ~/.ssh
chmod 600 ~/.ssh/github_ed25519
chmod 644 ~/.ssh/github_ed25519.pub
```

Configure SSH:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_ed25519
    IdentitiesOnly yes
EOF

chmod 600 ~/.ssh/config
```

If a `Host github.com` block already exists, edit it instead of adding another.

Display the public key:

```bash
cat ~/.ssh/github_ed25519.pub
```

Add that public key in GitHub under **Settings > SSH and GPG keys**. Never upload the private key.

Test and clone:

```bash
ssh -T git@github.com
mkdir -p ~/Projects
cd ~/Projects
git clone git@github.com:patrickm-aveva/fine_tuning_experimentations.git
cd fine_tuning_experimentations
git remote -v
```

Do not run Git commands with `sudo`.

## 6. Copy local data to the instance

Run `scp` on the **Mac**, not inside the EC2 SSH session.

Copy a directory recursively into the repository:

```bash
scp -i ~/.ssh/pm_g5xl_eu-north-1_1.pem -r \
  /path/to/local/data \
  ubuntu@ec2-16-171-11-214.eu-north-1.compute.amazonaws.com:~/Projects/fine_tuning_experimentations/
```

Example:

```bash
scp -i ~/.ssh/pm_g5xl_eu-north-1_1.pem -r \
  ~/Documents/training_data \
  ubuntu@ec2-16-171-11-214.eu-north-1.compute.amazonaws.com:~/Projects/fine_tuning_experimentations/data/
```

Verify on the instance:

```bash
ls -lah ~/Projects/fine_tuning_experimentations/data
```

For repeated transfers, `rsync` is preferable because it can transfer only changed files:

```bash
rsync -av --progress \
  -e "ssh -i ~/.ssh/pm_g5xl_eu-north-1_1.pem" \
  /path/to/local/data/ \
  ubuntu@ec2-16-171-11-214.eu-north-1.compute.amazonaws.com:~/Projects/fine_tuning_experimentations/data/
```

The trailing slash on the local source copies the directory contents rather than the containing directory itself.

## 7. Install Docker

```bash
sudo apt update
sudo apt install -y docker.io
sudo systemctl enable --now docker
```

Verify:

```bash
docker --version
sudo systemctl is-active docker
```

## 8. Install NVIDIA Container Toolkit

Install repository prerequisites:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg2
```

Add NVIDIA's production repository:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor \
      -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

Install and verify:

```bash
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
nvidia-ctk --version
```

Configure Docker:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo systemctl is-active docker
```

Test GPU access inside a container:

```bash
sudo docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```

The successful test on this instance reported NVIDIA A10G, driver 580.178.04, and 23,028 MiB GPU memory.

The CUDA version displayed by `nvidia-smi` is the maximum CUDA driver API level supported by the driver. It does not prove that the corresponding CUDA Toolkit is installed on the host or in every container.

## 9. Permit the current user to run Docker

By default, Docker's Unix socket may reject commands issued without `sudo`:

```text
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

Add the current user to the `docker` group:

```bash
sudo usermod -aG docker "$USER"
```

Activate the new group membership in the current shell:

```bash
newgrp docker
```

Alternatively, disconnect and reconnect over SSH.

Verify access without `sudo`:

```bash
docker run --rm hello-world
docker run --rm --gpus all ubuntu nvidia-smi
```

Membership in the `docker` group effectively grants root-level control of the host. Grant it only to trusted users.

## 10. Run the project container

From the repository root:

```bash
cd ~/Projects/fine_tuning_experimentations
mkdir -p data/processed outputs

docker run --rm --gpus all \
  -v "$(pwd)/data/processed:/app/data/processed" \
  -v "$(pwd)/outputs:/app/outputs" \
  fine-tuning-experimentations:cuda
```

The bind mounts preserve processed data and outputs on the EC2 host after the container exits.

If the image does not exist locally, inspect the repository for its intended build command before running it:

```bash
ls -la
find . -maxdepth 2 -iname 'Dockerfile*' -o -iname 'compose*.yml' -o -iname 'compose*.yaml'
```

## 11. Install uv

Install as the normal `ubuntu` user:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

If `uv` is not found:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## 12. Set up the Python project

If the repository already contains `pyproject.toml` and `uv.lock`:

```bash
cd ~/Projects/fine_tuning_experimentations
uv sync
uv run python --version
```

Do not run `uv init` in an already configured project.

If no uv configuration exists:

```bash
cd ~/Projects/fine_tuning_experimentations
uv init
uv python install 3.12
uv python pin 3.12
uv sync
```

Avoid `sudo pip install`.

## 13. Optional GPU-enabled PyTorch setup

Use the CUDA wheel channel required by the project. Example for CUDA 12.6 wheels:

```bash
uv pip install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu126
```

Verify GPU access:

```bash
uv run python - <<'PY'
import torch

print("PyTorch:", torch.__version__)
print("PyTorch CUDA runtime:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())

if not torch.cuda.is_available():
    raise SystemExit("PyTorch cannot access CUDA")

print("GPU:", torch.cuda.get_device_name(0))
x = torch.rand(2048, 2048, device="cuda")
print("GPU test:", (x @ x).mean().item())
PY
```

A system CUDA Toolkit is not required for ordinary use of CUDA-enabled PyTorch wheels. It is required when compiling custom CUDA code or extensions that need `nvcc`.

## 14. Final checks

```bash
nvidia-smi
docker run --rm --gpus all ubuntu nvidia-smi
ssh -T git@github.com
uv --version
uv run python --version
```

## Troubleshooting

### EC2 key cannot be found

Use the complete local key path:

```bash
ssh -i ~/.ssh/pm_g5xl_eu-north-1_1.pem \
  ubuntu@ec2-16-171-11-214.eu-north-1.compute.amazonaws.com
```

### GitHub rejects the key

```bash
ssh -i ~/.ssh/github_ed25519 -vT git@github.com
cat ~/.ssh/github_ed25519.pub
```

Confirm that the displayed public key is registered with a GitHub account or repository that can access the private repository.

### `nvidia-smi` is missing

```bash
sudo apt update
sudo apt install -y nvidia-driver-580-server
sudo reboot
```

### `nvidia-ctk` is missing

```bash
dpkg -l | grep nvidia-container-toolkit
```

Complete section 8 if the package is absent.

### Docker commands require `sudo`

```bash
id
getent group docker
ls -l /var/run/docker.sock
```

The user must belong to the `docker` group, and a new login or `newgrp docker` is required before the current shell sees the membership.

### PyTorch reports `CUDA available: False`

```bash
nvidia-smi
uv run python -c 'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())'
```

If `torch.version.cuda` is `None`, the environment contains a CPU-only PyTorch build.

## References

- [Ubuntu Server NVIDIA driver installation](https://ubuntu.com/server/docs/how-to/graphics/install-nvidia-drivers/)
- [NVIDIA Container Toolkit installation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- [NVIDIA Container Toolkit sample workload](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/sample-workload.html)
- [Docker Linux post-installation](https://docs.docker.com/engine/install/linux-postinstall/)
- [GitHub SSH troubleshooting](https://docs.github.com/en/authentication/troubleshooting-ssh/error-permission-denied-publickey)
- [Astral uv installation](https://docs.astral.sh/uv/getting-started/installation/)
- [PyTorch installation selector](https://pytorch.org/get-started/locally/)
