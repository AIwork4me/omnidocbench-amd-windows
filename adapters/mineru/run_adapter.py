"""omnidocbench-amd-windows adapter for MinerU-ROCm.

Delegates to MinerU-ROCm's dispatcher, which writes one Markdown file per page
plus ``_run_stats.json`` for the framework contract.
"""
from mineru_rocm.dispatcher import main


if __name__ == "__main__":
    raise SystemExit(main())
