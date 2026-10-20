"""Live memory probe for the local model screen: system RAM and GPU memory, total and free.

nvidia-smi comes first because it needs no Python GPU stack; llama.cpp installs do not ship torch.
Unknown values are None so the UI can say so instead of showing a guess.
"""

from __future__ import annotations

import subprocess
from typing import Optional

GB = 1024**3


def _ram() -> tuple[Optional[float], Optional[float]]:
    try:
        import psutil

        vm = psutil.virtual_memory()
        return vm.total / GB, vm.available / GB
    except Exception:
        pass
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat.ullTotalPhys / GB, stat.ullAvailPhys / GB
    except Exception:
        pass
    return None, None


def _gpu_nvidia_smi() -> Optional[dict]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        # shortcut: first GPU only; llama.cpp splits across GPUs, sum them if multi-GPU rigs matter.
        name, total, free = (p.strip() for p in out.stdout.strip().splitlines()[0].split(","))
        return {"name": name, "total": float(total) / 1024, "free": float(free) / 1024}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _gpu_torch() -> Optional[dict]:
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        free, total = torch.cuda.mem_get_info(0)
        return {"name": torch.cuda.get_device_name(0), "total": total / GB, "free": free / GB}
    except Exception:
        return None


def probe_hardware() -> dict:
    ram_total, ram_free = _ram()
    gpu = _gpu_nvidia_smi() or _gpu_torch()
    r = lambda v: round(v, 1) if v is not None else None
    return {
        "ram_total_gb": r(ram_total),
        "ram_available_gb": r(ram_free),
        "gpu_name": gpu["name"] if gpu else None,
        "vram_total_gb": r(gpu["total"]) if gpu else None,
        "vram_free_gb": r(gpu["free"]) if gpu else None,
    }
