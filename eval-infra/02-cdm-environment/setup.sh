#!/bin/bash
set -euo pipefail
# CDM Environment Setup — run inside WSL Ubuntu 22.04
# Consolidates 20+ debugging sessions into one idempotent script.
#
# Run from PowerShell:
#     wsl -d Ubuntu2204 bash /mnt/c/Users/rocm/Desktop/omnidocbench-amd-windows/eval-infra/02-cdm-environment/setup.sh
#
# Each of the 9 steps self-checks before proceeding, so re-running the script is
# safe and fast once the environment is provisioned. See README.md for what each
# step does, why it is needed, and what breaks if you skip it.

# Resolve the repo root from this script's own location (this file is at
# <root>/eval-infra/02-cdm-environment/setup.sh) instead of hardcoding a machine
# path, so a clone anywhere under /mnt/c works. $BASH_SOURCE reaches into WSL as
# a /mnt/c/... absolute path because the script is invoked via
#   wsl -d Ubuntu2204 bash /mnt/c/<clone>/eval-infra/02-cdm-environment/setup.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ODB_CODE="$REPO_ROOT/eval-infra/01-omnidocbench/OmniDocBench"

# Parse mirrors.env (CTAN_MIRROR, GITHUB_PROXY, PYPI_INDEX, ...).
CTAN_MIRROR="https://mirrors.ustc.edu.cn/CTAN/systems/texlive/tlnet"
if [ -f "$REPO_ROOT/mirrors.env" ]; then
    source <(grep -E "^[A-Z_]+=." "$REPO_ROOT/mirrors.env" | sed 's/^/export /')
fi

step() { echo ""; echo "=== Step $1: $2 ==="; }
ok()   { echo "  ✓ $1"; }
fail() { echo "  ✗ FAILED: $1"; exit 1; }

# ── Step 1: apt base deps ──
step 1 "apt base CDM deps (texlive-lang-cjk/chinese + imagemagick + ghostscript)"
dpkg -s texlive-lang-chinese >/dev/null 2>&1 && ok "already installed" || {
    apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        texlive-lang-cjk texlive-lang-chinese texlive-latex-extra texlive-fonts-recommended \
        texlive-science imagemagick ghostscript curl perl git >/dev/null 2>&1
    ok "apt deps installed"
}

# ── Step 2: Install TeX Live 2026 (official, for \mathcolor + complete CJK) ──
step 2 "TeX Live 2026 (official — has \\mathcolor + complete CJK package)"
TLBIN="/usr/local/texlive/2026/bin/x86_64-linux"
if [ -x "$TLBIN/pdflatex" ]; then ok "TL2026 already installed"; else
    cd /root
    curl -sL -m 180 -o install-tl.tar.gz "${CTAN_MIRROR}/install-tl-unx.tar.gz"
    tar xzf install-tl.tar.gz && cd install-tl-2*
    cat > tl.profile <<'PROF'
selected_scheme scheme-medium
instopt_adjustpath 0
instopt_adjustrepo 0
instopt_letter 0
instopt_portable 0
collection-langcjk 1
collection-langchinese 1
tlpdbopt_install_docfiles 0
tlpdbopt_install_srcfiles 0
PROF
    ./install-tl --no-interaction --profile tl.profile --repository "$CTAN_MIRROR" 2>&1 | tail -3
    [ -x "$TLBIN/pdflatex" ] && ok "TL2026 installed" || fail "TL2026 install"
fi
export PATH="$TLBIN:$PATH"

# ── Step 3: Copy CJK macros + gkai/arphic fonts from TL2026 to system texlive ──
# (Ubuntu's texlive lacks the classic CJK.sty + c70gkai.fd; TL2026 has them)
step 3 "Copy CJK.sty + gkai fonts from TL2026 → system texlive"
TLMF="/usr/local/texlive/2026/texmf-dist"
SYSMF="/usr/share/texlive/texmf-dist"
if kpsewhich CJK.sty >/dev/null 2>&1; then ok "CJK.sty already in system path"
else
    cp -rn "$TLMF/tex/latex/cjk" "$SYSMF/tex/latex/" 2>/dev/null || true
    for fd in afm tfm type1; do cp -rn "$TLMF/fonts/$fd/arphic" "$SYSMF/fonts/$fd/" 2>/dev/null || true; done
    mktexlsr "$SYSMF" >/dev/null 2>&1
    kpsewhich CJK.sty >/dev/null 2>&1 && ok "CJK.sty + gkai copied" || fail "CJK font copy"
fi

# ── Step 4: Inject gkaiu font map into pdftex.map ──
step 4 "Inject gkaiu font map → pdftex.map (pdflatex needs this to find gkaiu bitmaps)"
PDMAP=$(kpsewhich pdftex.map 2>/dev/null | head -1)
if [ -n "$PDMAP" ] && grep -q gkaiu "$PDMAP" 2>/dev/null; then ok "gkaiu already in pdftex.map"
else
    # Copy the map files from TL2026
    mkdir -p "$SYSMF/fonts/map/dvips/arphic"
    cp -rn "$TLMF/fonts/map/dvips/arphic/." "$SYSMF/fonts/map/dvips/arphic/" 2>/dev/null || true
    mktexlsr "$SYSMF" >/dev/null 2>&1
    # Direct injection (bypasses finicky updmap-sys)
    WPMAP=$(find /usr/local/texlive/2026 -name pdftex.map -path '*updmap*' 2>/dev/null | head -1)
    if [ -n "$WPMAP" ]; then
        grep gkaiu "$WPMAP" >> "$PDMAP"
        grep -q gkaiu "$PDMAP" && ok "gkaiu injected into pdftex.map" || fail "gkaiu map injection"
    else
        # Try updmap-sys as fallback
        updmap-sys --syncwithtrees >/dev/null 2>&1 || true
        updmap-sys --enable Map=gkaiu.map >/dev/null 2>&1 || true
        updmap-sys >/dev/null 2>&1 || true
        grep -q gkaiu "$PDMAP" 2>/dev/null && ok "gkaiu in pdftex.map (via updmap)" || fail "gkaiu map"
    fi
fi

# ── Step 5: Install ImageMagick 7 (IM6 produces grayscale PNGs → CDM F1=0) ──
step 5 "ImageMagick 7 (IM6 renders color-coded formulas as grayscale → CDM fails)"
if magick --version 2>/dev/null | grep -q "ImageMagick 7"; then ok "IM7 already active"
else
    cd /root
    if [ ! -f magick7.AppImage ] || [ "$(stat -c%s magick7.AppImage 2>/dev/null || echo 0)" -lt 10000000 ]; then
        PROXY="${GITHUB_PROXY:-https://ghproxy.net}"
        curl -sL -m 300 -o magick7.AppImage "$PROXY/https://github.com/ImageMagick/ImageMagick/releases/download/7.1.2-26/ImageMagick-7.1.2-26-gcc-x86_64.AppImage"
    fi
    chmod +x magick7.AppImage
    rm -rf squashfs-root
    ./magick7.AppImage --appimage-extract >/dev/null 2>&1
    # Install system-wide (avoids LD_LIBRARY_PATH shadowing gs)
    cp squashfs-root/usr/bin/magick /usr/local/bin/magick7
    mkdir -p /usr/local/lib/im7
    cp -rn squashfs-root/usr/lib/*.so* /usr/local/lib/im7/ 2>/dev/null || true
    echo "/usr/local/lib/im7" > /etc/ld.so.conf.d/im7.conf
    ldconfig
    cp -rn squashfs-root/etc/ImageMagick-7 /usr/local/etc/ 2>/dev/null || true
    ln -sf /usr/local/bin/magick7 /usr/local/bin/magick
    magick --version 2>/dev/null | grep -q "ImageMagick 7" && ok "IM7 installed" || fail "IM7 install"
fi

# ── Step 6: Allow PDF in IM6 policy (fallback path uses IM6's convert) ──
step 6 "Allow PDF in ImageMagick 6 policy.xml"
POL="/etc/ImageMagick-6/policy.xml"
if [ -f "$POL" ] && grep -q 'pattern="PDF"' "$POL"; then
    sed -i 's#rights="none" pattern="PDF"#rights="read|write" pattern="PDF"#' "$POL"
    sed -i 's#rights="none" pattern="PS"#rights="read|write" pattern="PS"#' "$POL"
    ok "IM6 PDF policy updated"
else
    ok "IM6 policy not needed or already set"
fi

# ── Step 7: Install IM7 system deps (libfribidi etc.) ──
step 7 "IM7 system library deps"
if magick --version 2>/dev/null | grep -q "ImageMagick 7"; then ok "IM7 libs OK"
else
    apt-get install -y -qq libfribidi0 libharfbuzz0b libfontconfig1 libltdl7 libgomp1 libxml2 >/dev/null 2>&1
    magick --version 2>/dev/null | grep -q "ImageMagick 7" && ok "IM7 libs installed" || fail "IM7 libs"
fi

# ── Step 8: OmniDocBench code + \DeclareDocumentCommand fix ──
step 8 "OmniDocBench code + \\mathcolor override fix"
ODB_LOCAL="/root/OmniDocBench"
if [ ! -f "$ODB_LOCAL/pdf_validation.py" ]; then
    cp -r "$ODB_CODE" "$ODB_LOCAL"
    rm -rf "$ODB_LOCAL/.git"
fi
# Apply the \mathcolor fix (root cause: \mathcolor renders black in TL2026 → CDM F1=0)
FIXFILE="$ODB_LOCAL/src/metrics/cdm/modules/latex2bbox_color.py"
if ! grep -q "DeclareDocumentCommand" "$FIXFILE" 2>/dev/null; then
    sed -i 's/\\usepackage{xcolor}/\\usepackage{xcolor}\n\\DeclareDocumentCommand{\\mathcolor}{O{} m m}{\\begingroup\\color[#1]{#2}#3\\endgroup}/g' "$FIXFILE"
    grep -q "DeclareDocumentCommand" "$FIXFILE" && ok "\\mathcolor fix applied" || fail "\\mathcolor fix"
else
    ok "\\mathcolor fix already present"
fi
# Revert any stray Windows patches (shlex.quote, -strip, etc.)
sed -i 's/magick -density 200 -quality 100 -strip/magick -density 200 -quality 100/g' "$FIXFILE" 2>/dev/null || true
sed -i 's/magick -density 200 -quality 100 -colorspace sRGB/magick -density 200 -quality 100/g' "$FIXFILE" 2>/dev/null || true

# ── Step 9: Python venv + OmniDocBench deps ──
step 9 "Python venv + OmniDocBench dependencies"
if [ ! -d /root/odb-venv ]; then
    python3 -m venv /root/odb-venv
    /root/odb-venv/bin/pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple \
        apted beautifulsoup4 evaluate func-timeout Levenshtein loguru lxml numpy pandas \
        Pillow pylatexenc PyYAML scipy tabulate tqdm nltk matplotlib
    ok "venv + deps installed"
else
    ok "venv already exists"
fi

echo ""
echo "========================================"
echo "CDM Environment Setup COMPLETE."
echo "Run verify.sh to validate the full pipeline."
echo "========================================"
