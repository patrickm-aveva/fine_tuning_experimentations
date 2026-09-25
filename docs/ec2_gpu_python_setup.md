# EC2 GPU Python Environment Setup

This guide configures an Ubuntu 24.04 NVIDIA GPU EC2 instance with SSH access, NVIDIA Server Driver 580, `uv`, Python 3.12, GPU-enabled PyTorch, and authenticated access to a private GitHub repository.

## Environment used in this guide

- EC2 host: `ec2-16-171-11-214.eu-north-1.compute.amazonaws.com`
- EC2 user: `ubuntu`
- Local EC2 key: `~/.ssh/pm_g5xl_eu-north-1_1.pem`
- GitHub repository: `patrickm-aveva/fine_tuning_experimentations`

Commands identified as **local** run on the Mac. Other commands run on the EC2 instance.

---

## 1. Connect to the EC2 instance

On the Mac:

```bash
chmod 400 ~/.ssh/pm_g5xl_eu-north-1_1.pem

ssh -i ~/.ssh/pm_g5xl_eu-north-1_1.pem \
  ubuntu@ec2-16-171-11-214.eu-north-1.compute.amazonaws.com
```

Always specify the key path. A filename without a path is resolved relative to the current directory.

---

## 2. Confirm Ubuntu and the NVIDIA GPU

On the instance:

```bash
cat /etc/os-release
uname -m
lspci | grep -i nvidia
```

Expected results:

- Ubuntu 24.04
- Usually `x86_64`
- At least one NVIDIA device

If no NVIDIA device appears, verify that the EC2 instance type exposes an NVIDIA GPU before continuing.

---

## 3. Update Ubuntu and install prerequisites

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y \
  build-essential \
  curl \
  git \
  pkg-config \
  ca-certificates \
  ubuntu-drivers-common \
  linux-headers-$(uname -r)
```

If the upgrade installed a newer kernel, reboot:

```bash
sudo reboot
```

Reconnect from the Mac using the SSH command in section 1.

---

## 4. Install NVIDIA Server Driver 580

Check that the server package is available:

```bash
sudo ubuntu-drivers list --gpgpu
apt-cache policy nvidia-driver-580-server
```

Install the complete driver package:

```bash
sudo apt install -y nvidia-driver-580-server
sudo reboot
```

Do not install only `nvidia-utils-580-server`. The complete driver package installs the driver stack and matching utilities. Do not mix Ubuntu packages with NVIDIA `.run` installers.

Reconnect, then verify:

```bash
nvidia-smi
cat /proc/driver/nvidia/version
lsmod | grep nvidia
```

The reported driver version should begin with `580.`. Do not continue with GPU framework installation until `nvidia-smi` works.

---

## 5. Configure GitHub SSH access

The EC2 login key and a GitHub authentication key serve different purposes. The EC2 private key authenticates the Mac to AWS. The instance needs its own key that GitHub associates with the GitHub account or repository.

The first connection to GitHub may display this prompt:

```text
The authenticity of host 'github.com (...)' can't be established.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

Before accepting a host key, compare the displayed fingerprint with GitHub's published SSH host-key fingerprints. Once accepted, the host is stored in `~/.ssh/known_hosts`.

### 5.1 Create a dedicated GitHub key on the instance

Run as `ubuntu`, without `sudo`:

```bash
ssh-keygen -t ed25519 \
  -C "ec2-eu-north-1-fine-tuning" \
  -f ~/.ssh/github_ed25519
```

Choose whether to set a passphrase. A passphrase provides additional protection but requires an SSH agent or interactive entry.

Set restrictive permissions:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/github_ed25519
chmod 644 ~/.ssh/github_ed25519.pub
```

### 5.2 Configure SSH to use the dedicated key

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

If `~/.ssh/config` already contains a `Host github.com` block, edit that block rather than adding a duplicate.

### 5.3 Add the public key to GitHub

Display the public key:

```bash
cat ~/.ssh/github_ed25519.pub
```

Copy the entire single line beginning with `ssh-ed25519`.

In GitHub:

1. Open **Settings**.
2. Select **SSH and GPG keys**.
3. Select **New SSH key**.
4. Enter a descriptive title, such as `EC2 eu-north-1 fine-tuning`.
5. Select **Authentication Key**.
6. Paste the public key.
7. Save it.

Add only `~/.ssh/github_ed25519.pub`. Never copy, upload, or commit the private key `~/.ssh/github_ed25519`.

If the key should grant access only to this repository rather than the entire account, add the public key as a repository deploy key instead. Write access is unnecessary for cloning and pulling.

### 5.4 Test GitHub authentication

```bash
ssh -T git@github.com
```

A successful response identifies the GitHub account and states that authentication succeeded.

If it fails, use verbose diagnostics:

```bash
ssh -i ~/.ssh/github_ed25519 -vT git@github.com
```

Do not run Git commands with `sudo`; root uses a different home directory, SSH configuration, and key set.

### 5.5 Clone the repository

```bash
cd ~/projects
git clone git@github.com:patrickm-aveva/fine_tuning_experimentations.git
cd fine_tuning_experimentations
```

Verify the remote:

```bash
git remote -v
```

---

## 6. Install uv

Install `uv` as the normal `ubuntu` user:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

If the environment file is unavailable or `uv` is not found:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
uv --version
```

---

## 7. Set up the Python project

If the cloned repository already contains `pyproject.toml` and `uv.lock`, use its existing configuration:

```bash
cd ~/projects/fine_tuning_experimentations
uv sync
uv run python --version
```

If it does not yet contain a uv project configuration:

```bash
cd ~/projects/fine_tuning_experimentations
uv init
uv python install 3.12
uv python pin 3.12
uv sync
```

For a separate new project:

```bash
mkdir -p ~/projects/gpu-python
cd ~/projects/gpu-python
uv init
uv python install 3.12
uv python pin 3.12
uv sync
```

`uv` uses `pyproject.toml` for project metadata and direct dependencies, `.python-version` for the selected interpreter, `.venv` for the isolated environment, and `uv.lock` for exact resolved dependencies.

---

## 8. Add baseline Python dependencies

Only add packages that are not already declared by the repository:

```bash
uv add \
  numpy \
  scipy \
  pandas \
  scikit-learn \
  matplotlib \
  jupyterlab \
  ipykernel \
  tqdm \
  psutil \
  rich

uv add --dev pytest ruff mypy
```

Avoid `sudo pip install`. Keep application dependencies inside the uv-managed project.

---

## 9. Install GPU-enabled PyTorch

Select the CUDA wheel channel supported by the intended PyTorch release. For the CUDA 12.6 wheel channel:

```bash
uv pip install \
  torch \
  torchvision \
  torchaudio \
  --index-url https://download.pytorch.org/whl/cu126
```

For a reproducible project, configure the chosen PyTorch index in `pyproject.toml` rather than relying only on an ad hoc `uv pip install` command.

---

## 10. Verify PyTorch GPU access

```bash
uv run python - <<'PY'
import sys
import torch

print("Python:", sys.version)
print("PyTorch:", torch.__version__)
print("PyTorch CUDA runtime:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())

if not torch.cuda.is_available():
    raise SystemExit("PyTorch cannot access CUDA")

print("GPU:", torch.cuda.get_device_name(0))
print("GPU count:", torch.cuda.device_count())

x = torch.rand(2048, 2048, device="cuda")
y = x @ x
print("GPU matrix test result:", y.mean().item())
PY
```

The essential results are:

```text
CUDA available: True
GPU: <GPU model>
```

---

## 11. Decide whether the CUDA Toolkit is required

The NVIDIA driver and a CUDA-enabled PyTorch wheel are sufficient for normal PyTorch execution.

```bash
nvcc --version
```

A missing `nvcc` is not a problem if the PyTorch GPU test succeeds. Install a system CUDA Toolkit only when the project must compile custom CUDA code or extensions, invoke `nvcc`, or build a package that explicitly requires a local Toolkit.

---

## 12. Final health check

From the project directory:

```bash
nvidia-smi
ssh -T git@github.com
uv --version
uv run python --version
uv run python -c 'import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))'
```

A working setup should show:

- NVIDIA driver version `580.x`
- Successful GitHub authentication
- A valid `uv` version
- Python 3.12, unless the repository pins another supported version
- `torch.cuda.is_available()` returning `True`
- The expected EC2 GPU model

---

## Troubleshooting

### SSH reports that the EC2 identity file is inaccessible

Use the complete local path:

```bash
ssh -i ~/.ssh/pm_g5xl_eu-north-1_1.pem \
  ubuntu@ec2-16-171-11-214.eu-north-1.compute.amazonaws.com
```

### GitHub reports `Permission denied (publickey)`

Check the key files and permissions:

```bash
ls -la ~/.ssh
ssh-add -l -E sha256
ssh -i ~/.ssh/github_ed25519 -vT git@github.com
```

Confirm that the public key shown by the following command is registered with the GitHub account or repository that can access `patrickm-aveva/fine_tuning_experimentations`:

```bash
cat ~/.ssh/github_ed25519.pub
```

### `nvidia-smi` is not found

```bash
dpkg -l | grep -E 'nvidia-driver-580-server|nvidia-utils-580-server'
sudo apt update
sudo apt install -y nvidia-driver-580-server
sudo reboot
```

### `nvidia-smi` cannot communicate with the driver

```bash
uname -r
dpkg -l "linux-headers-$(uname -r)"
lsmod | grep nvidia
modinfo nvidia | head
sudo dmesg | grep -iE 'nvidia|nouveau' | tail -100
```

### PyTorch reports `CUDA available: False`

First verify the host driver:

```bash
nvidia-smi
```

Then inspect PyTorch:

```bash
uv run python - <<'PY'
import torch
print("PyTorch:", torch.__version__)
print("Compiled CUDA runtime:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
PY
```

If `torch.version.cuda` is `None`, a CPU-only PyTorch build is installed.

---

## References

- [Ubuntu Server NVIDIA driver installation](https://ubuntu.com/server/docs/how-to/graphics/install-nvidia-drivers/)
- [NVIDIA Driver Installation Guide for Ubuntu](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/ubuntu.html)
- [GitHub SSH connection testing](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection)
- [GitHub SSH public-key troubleshooting](https://docs.github.com/en/authentication/troubleshooting-ssh/error-permission-denied-publickey)
- [GitHub SSH host-key fingerprints](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)
- [Astral uv installation](https://docs.astral.sh/uv/getting-started/installation/)
- [Astral uv project guide](https://docs.astral.sh/uv/guides/projects/)
- [PyTorch installation selector](https://pytorch.org/get-started/locally/)
