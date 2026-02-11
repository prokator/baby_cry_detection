from __future__ import annotations

import shutil
import subprocess


def run_gpu_check() -> tuple[bool, str]:
    if shutil.which("nvidia-smi") is None:
        return False, "nvidia-smi not found in container"

    try:
        output = subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True)
    except subprocess.CalledProcessError as exc:
        return False, f"nvidia-smi failed: {exc}"

    names = [line.strip() for line in output.splitlines() if line.strip()]
    if not names:
        return False, "no GPU devices reported"
    return True, ", ".join(names)
