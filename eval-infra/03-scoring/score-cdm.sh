#!/bin/bash
set -euo pipefail
# Score adapter predictions with the FULL metric set INCLUDING CDM (WSL).
#
# This is the CDM-enabled counterpart to score.ps1. CDM (the formula-rendering
# metric) cannot run Windows-native: OmniDocBench's CDM code shells out to
# POSIX-only commands (kpsewhich, magick, gs, pdflatex) and needs a working
# LaTeX + ImageMagick 7 + Ghostscript toolchain that renders color correctly.
# That environment is provisioned by eval-infra/02-cdm-environment (Task 3) and
# lives in WSL. So we run the CDM config here.
#
# Run from PowerShell (replace /mnt/c/<path-to-repo> with your clone location):
#   wsl -d Ubuntu2204 bash /mnt/c/<path-to-repo>/eval-infra/03-scoring/score-cdm.sh
#
# Produces (in /root/OmniDocBench/result/):
#   <save_name>_metric_result.json     — now display_formula has a CDM score too
#   <save_name>_run_summary.json
# where <save_name> = paddleocrvl_rocm_cdm_quick_match (the cdm-named
# predictions dir in v16-cdm.yaml prevents clobbering the Edit_dist-only run).

# Config template (under eval-infra/01-omnidocbench/configs/). v16-cdm.yaml is
# the only CDM-enabled template; allow override for future CDM + hard-subset
# configs.
CONFIG="${1:-v16-cdm.yaml}"

# --- Resolve paths ----------------------------------------------------------
# This script lives at <root>/eval-infra/03-scoring/score-cdm.sh; repo root is
# two levels up. Resolve to an absolute /mnt/c path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CFG_TEMPLATE="$REPO_ROOT/eval-infra/01-omnidocbench/configs/$CONFIG"

if [ ! -f "$CFG_TEMPLATE" ]; then
    echo "FAIL: config template not found: $CFG_TEMPLATE" >&2
    echo "  Expected: v16-cdm.yaml under eval-infra/01-omnidocbench/configs/" >&2
    exit 1
fi

# OmniDocBench code lives natively in WSL at /root/OmniDocBench (faster I/O than
# /mnt/c; provisioned by 02-cdm-environment/setup.sh step 8). Verify the CDM
# environment is set up before scoring — running without it yields CDM F1=0.
ODB_LOCAL="/root/OmniDocBench"
if [ ! -f "$ODB_LOCAL/pdf_validation.py" ]; then
    echo "FAIL: $ODB_LOCAL/pdf_validation.py not found." >&2
    echo "  Run eval-infra/02-cdm-environment/setup.sh first to provision the CDM environment." >&2
    exit 1
fi

# --- Materialize the run config (resolve <REPO_ROOT>) ----------------------
# The template uses <REPO_ROOT> as a placeholder. On the WSL side the repo is
# reached at /mnt/c/... so the absolute /mnt/c path works for both the GT
# manifest and the predictions dir.
RUN_CFG="$ODB_LOCAL/run_${CONFIG%.yaml}.yaml"
sed "s|<REPO_ROOT>|$REPO_ROOT|g" "$CFG_TEMPLATE" > "$RUN_CFG"
echo "Rendered run config: $RUN_CFG"

# --- Clean Linux PATH (no Windows interop leakage) -------------------------
# This exact PATH combo is the one that produced our verified CDM scores
# (see the cdm_run_full.sh debug script in the project history). Order matters:
#   TeX Live 2026 bin first  — \mathcolor + complete CJK
#   /usr/local/bin           — magick (IM7, installed system-wide in step 5)
#   standard Linux paths     — gs, coreutils
# Anything from /mnt/c (Windows) on PATH breaks subprocess calls (shlex/POSIX).
export PATH=/usr/local/texlive/2026/bin/x86_64-linux:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
# IM7 reads its policy.xml from $MAGICK_CONFIGURE_PATH; without it the AppImage
# lib copy can fall back to the locked-down IM6 policy and refuse PDF.
export MAGICK_CONFIGURE_PATH=/usr/local/etc/ImageMagick-7
export HOME=/root
export PYTHONUTF8=1

# --- Run pdf_validation.py with the OmniDocBench venv ----------------------
cd "$ODB_LOCAL"
echo "Scoring (Edit_dist + TEDS + CDM) with $CONFIG ..."
/root/odb-venv/bin/python pdf_validation.py --config "$RUN_CFG" 2>&1

echo ""
echo "Scoring complete. Results in: $ODB_LOCAL/result/"
echo "Next: copy <save_name>_metric_result.json to the Windows side and run"
echo "      verify.ps1, or run verify.ps1 against the WSL result path directly."
