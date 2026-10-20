"""Live memory probe: nvidia-smi parsing, torch-free fallback, and unknowns reported as None."""

from types import SimpleNamespace
from unittest.mock import patch

from services.agent import hardware


def test_reads_gpu_memory_from_nvidia_smi():
    out = SimpleNamespace(returncode=0, stdout="NVIDIA GeForce RTX 4050 Laptop GPU, 6141, 5530\n")
    with patch("subprocess.run", return_value=out), patch.object(hardware, "_ram", return_value=(16.0, 4.0)):
        hw = hardware.probe_hardware()
    assert hw == {
        "ram_total_gb": 16.0,
        "ram_available_gb": 4.0,
        "gpu_name": "NVIDIA GeForce RTX 4050 Laptop GPU",
        "vram_total_gb": 6.0,
        "vram_free_gb": 5.4,
    }


def test_no_gpu_and_unreadable_ram_are_none_not_guesses():
    with patch("subprocess.run", side_effect=FileNotFoundError), patch.object(hardware, "_gpu_torch", return_value=None), patch.object(
        hardware, "_ram", return_value=(None, None)
    ):
        hw = hardware.probe_hardware()
    assert set(hw.values()) == {None}
