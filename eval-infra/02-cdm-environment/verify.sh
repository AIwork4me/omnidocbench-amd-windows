#!/bin/bash
set -euo pipefail
# End-to-end CDM verification: compile CJK formula → PDF → color PNG → CDM F1 > 0
#
# Run from PowerShell (replace /mnt/c/<path-to-repo> with your clone location):
#     wsl -d Ubuntu2204 bash /mnt/c/<path-to-repo>/eval-infra/02-cdm-environment/verify.sh
#
# Exits 0 only if the full CDM pipeline is functional. Any failure prints FAIL
# with the offending stage so you know which step of setup.sh to re-run.
export PATH=/usr/local/texlive/2026/bin/x86_64-linux:/usr/local/bin:$PATH
export MAGICK_CONFIGURE_PATH=/usr/local/etc/ImageMagick-7

# Resolve the OmniDocBench checkout + venv relative to $HOME (not a hardcoded
# /root/... path) so this works for non-root WSL users too. setup.sh installs
# into $HOME/OmniDocBench and $HOME/odb-venv; the wsl --import path makes the
# default user root, but a `wsl --install`-created distro (or a manually-set
# non-root default user) lands elsewhere under $HOME.
ODB_HOME="${HOME}"
ODB_LOCAL="${ODB_HOME}/OmniDocBench"
ODB_VENV="${ODB_HOME}/odb-venv"

echo "=== Checking tools ==="
which pdflatex >/dev/null 2>&1 || { echo "FAIL: pdflatex not found"; exit 1; }
magick --version 2>/dev/null | grep -q "ImageMagick 7" || { echo "FAIL: IM7 not active"; exit 1; }
which gs >/dev/null 2>&1 || { echo "FAIL: gs not found"; exit 1; }
echo "  tools OK"

echo "=== Checking CJK + gkai ==="
kpsewhich CJK.sty >/dev/null 2>&1 || { echo "FAIL: CJK.sty not found"; exit 1; }
kpsewhich c70gkai.fd >/dev/null 2>&1 || { echo "FAIL: c70gkai.fd not found"; exit 1; }
echo "  CJK OK"

echo "=== Compile test: CJK formula → PDF → color PNG ==="
cd /tmp
cat > cdm_verify.tex <<'TEX'
\documentclass{article}\usepackage{xcolor}
\DeclareDocumentCommand{\mathcolor}{O{} m m}{\begingroup\color[#1]{#2}#3\endgroup}
\begin{document}\ensuremath{\mathcolor[RGB]{255,0,0}{x}+\mathcolor[RGB]{0,0,255}{y}}\end{document}
TEX
pdflatex -interaction=nonstopmode -halt-on-error cdm_verify.tex >/dev/null 2>&1 || { echo "FAIL: pdflatex compile"; exit 1; }
magick -density 100 cdm_verify.pdf cdm_verify.png 2>/dev/null
[ -f cdm_verify.png ] || { echo "FAIL: magick PDF→PNG"; exit 1; }
source "$ODB_VENV/bin/activate"
COLORS=$(python3 -c "from PIL import Image; c=Image.open('/tmp/cdm_verify.png').convert('RGB').getcolors(10**6); print(len(c) if c else 0)")
[ "$COLORS" -gt 2 ] || { echo "FAIL: PNG is grayscale ($COLORS colors) — \\mathcolor fix not working"; exit 1; }
echo "  PDF→PNG color OK ($COLORS colors)"

echo "=== CDM F1 test ==="
cd "$ODB_LOCAL"
python3 -c "
import sys; sys.path.insert(0,'.')
from src.metrics.cdm_metric import CDM
c=CDM(output_root='/tmp/cdm_verify_cdm')
r=c.evaluate(r'a^2+b^2=c^2', r'a^2+b^2=c^2', 't', sample_context={'img_id':'t','gt_idx':[0],'pred_idx':[0]})
f1=r.get('F1_score',0)
print('  CDM F1 for identical formulas:', f1)
exit(0 if f1 > 0.5 else 1)
" || { echo "FAIL: CDM F1=0 — check \\mathcolor fix"; exit 1; }

echo ""
echo "VERIFY OK: CDM environment fully functional."
exit 0
