"""Resource sampler: background process polled at 1 Hz.

Writes one JSON line per second to a JSONL file until a sentinel stop file
appears. Degrades gracefully through GPU backends: rocm-smi -> typeperf -> none.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


class GPUQueryError(Exception):
    """Raised when all configured GPU backends fail for a sampling cycle."""


def _query_gpu_rocm_smi() -> tuple[float, float]:
    """Query GPU via rocm-smi. Returns (mem_mib, util_pct). Raises GPUQueryError on failure."""
    try:
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--json"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            raise GPUQueryError(f"rocm-smi exit {result.returncode}: {result.stderr[:200]}")
        data = json.loads(result.stdout)
        card = list(data.values())[0]
        vram = card.get("VRAM", {})
        mem_bytes = int(vram.get("Total Used Memory (B)", 0))
        gpu_mem_mib = mem_bytes / (1024 * 1024)
        gpu_util_pct = float(card.get("GPU use (%)", 0))
        return gpu_mem_mib, gpu_util_pct
    except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
        raise GPUQueryError(f"rocm-smi parse error: {e}")
    except FileNotFoundError:
        raise GPUQueryError("rocm-smi not found on PATH")
    except subprocess.TimeoutExpired:
        raise GPUQueryError("rocm-smi timed out")


def _fallback_ram_only() -> tuple[None, None]:
    """Return None for GPU data when all backends fail."""
    return None, None


def sample(interval: float, output_path: str, *, stop_file: str = "monitor_stop.txt") -> None:
    """Sample until sentinel file appears. Degrade gracefully on GPU query failure.

    Parameters
    ----------
    interval : float
        Seconds between samples.
    output_path : str
        Path to JSONL output file (appended).
    stop_file : str
        Path to sentinel file; loop exits when this file exists.
    """
    import psutil

    consecutive_failures = 0
    gpu_backend_level = "gpu-full"
    threshold = 3

    backends = [
        ("rocm-smi", _query_gpu_rocm_smi),
        ("none", _fallback_ram_only),
    ]

    with open(output_path, "a") as f:
        while True:
            ts = time.time()
            gpu_mem, gpu_util = None, None

            try:
                gpu_mem, gpu_util = _query_gpu_rocm_smi()
                consecutive_failures = 0
                gpu_backend_level = "gpu-full"
            except GPUQueryError:
                consecutive_failures += 1
                if consecutive_failures >= threshold:
                    gpu_backend_level = "gpu-degraded"
                if consecutive_failures >= 10 * threshold:
                    gpu_backend_level = "gpu-unavailable"
                gpu_mem, gpu_util = None, None

            ram = psutil.virtual_memory().used / (1024 ** 3)

            f.write(json.dumps({
                "ts": ts,
                "gpu_mem_mib": gpu_mem,
                "gpu_util_pct": gpu_util,
                "ram_gib": round(ram, 2),
                "gpu_level": gpu_backend_level,
            }) + "\n")
            f.flush()
            if Path(stop_file).exists():
                break
            time.sleep(interval)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Resource sampler for benchmark runs")
    p.add_argument("--output", required=True, help="JSONL output path")
    p.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds")
    p.add_argument("--stop-file", default="monitor_stop.txt", help="Sentinel file path")
    args = p.parse_args()
    sample(interval=args.interval, output_path=args.output, stop_file=args.stop_file)
