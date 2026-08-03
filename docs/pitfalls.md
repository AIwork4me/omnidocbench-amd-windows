# Pitfalls — knowledge base

The curated record of every landmine we hit bringing OmniDocBench v1.6 up on AMD
Windows. Organized **by symptom** — when something fails, find your symptom
below, then read **Root Cause → Fix → Verify**.

This is the single most valuable file in the repo. Every entry below cost real
debugging hours; the fixes are distilled from 20+ throwaway scripts. If you
change a setup step anywhere in `eval-infra/` or `adapters/`, re-read the
relevant entry first.

> Cross-references like `#grayscale` are stable anchors — cite them from code
> comments and commit messages.

---

## Table of contents

- [Network](#network) — GitHub / HuggingFace / CTAN / Microsoft Store blocked
- [WSL install](#wsl) — `wsl --install` hangs or fails
- [WSL distro wrong name](#distro-name) — `wsl -d Ubuntu2204` fails, but a distro exists under a different name
- [Python version](#python-version) — OmniDocBench needs Python < 3.12
- [CDM F1 = 0 (the master decision tree)](#cdm-zero)
- [\mathcolor renders black](#mathcolor)
- [ImageMagick 6 renders color as grayscale](#grayscale)
- [gkaiu font not in pdftex.map](#gkaiu-map)
- [ImageMagick 6 policy blocks PDF](#im-policy)
- [IM7 AppImage missing shared libs](#im7-libs)
- [IM7 AppImage libgs shadows system Ghostscript](#im7-gs)
- [CDM code uses POSIX shell commands](#posix)
- [Ubuntu texlive lacks CJK.sty / gkaiu](#texlive-cjk)
- [Two TeX Live trees disagree](#two-texlive-trees)
- [WSL CDM fork-in-fork crash](#wsl-fork-fork)
- [PYTHONUTF8 / Windows codepage corruption](#pythonutf8)
- [Layout (ONNX) model not found](#layout)
- [VLM server 500 errors](#vlm)
- [Official PaddleOCRVL pretty Markdown hurts Text Edit-distance](#official-pretty-markdown)
- [MIOpen find-db corruption after unclean shutdown](#miopen-finddb)
- [Windows AMD GPU counters unavailable](#gpu-counters-windows)

---

<a id="network"></a>
## #network — GitHub / HuggingFace / CTAN / Store blocked

**Symptom.** Downloads hang, time out, or fail with `Connection refused` /
`Could not resolve host` for `github.com`, `huggingface.co`, `mirror.ctan.org`,
or the Microsoft Store. Common on restrictive or
corporate networks.

**Root cause.** Direct egress to those hosts is blocked or throttled. There is
no single global proxy; each source has its own working mirror.

**Fix.** Run `scripts/detect-mirrors.ps1` **once** before any other setup step.
It probes each source and writes `mirrors.env` with the working mirror per
source:

| Source | Reachable fallback |
|---|---|
| HuggingFace | ModelScope (`modelscope.cn`) — same datasets/models, China-hosted |
| GitHub | `ghproxy.net` / `ghfast.top` prefix proxies |
| CTAN (TeX Live) | USTC / Tsinghua CTAN mirrors |
| PyPI | Tsinghua PyPI mirror |
| Microsoft Store (WSL) | bypass entirely — see [#wsl](#wsl) |

Every downstream script (`setup.ps1`, `setup.sh`, `score-cdm.sh`) reads
`mirrors.env` and uses the recorded sources, so you only solve this once.

**Verify.** `Test-Path mirrors.env` returns true and the file contains a
non-empty `GITHUB_BASE=`, `HF_OR_MS=`, `CTAN_MIRROR=`, `PYPI_INDEX=`,
`UBUNTU_ROOTFS=`.

**If you skip it.** The very first `git clone` or `huggingface-cli download`
in setup hangs forever or fails opaquely. `detect-mirrors.ps1` exists
specifically to front-load this.

---

<a id="wsl"></a>
## #wsl — `wsl --install` hangs or fails

**Symptom.** `wsl --install -d Ubuntu-22.04` hangs for many minutes, then
fails. Or WSL itself installs but no distro appears. Console may mention the
Microsoft Store or `raw.githubusercontent.com` (the distro download URL).

**Root cause.** `wsl --install` pulls the distro image from the Microsoft
Store / `raw.githubusercontent.com`, both of which are commonly blocked (see
[#network](#network)). The command itself succeeds partially then dies on the
download.

**Fix.** `scripts/wsl-ensure.ps1` tries `wsl --install` first; if that fails it
downloads the Ubuntu 22.04 rootfs tarball directly from the USTC mirror
(`mirrors.ustc.edu.cn/ubuntu-cdimage/...`) and imports it with
`wsl --import Ubuntu2204 C:\WSL\Ubuntu2204 <tarball> --version 2`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\wsl-ensure.ps1
```

**Verify.** `wsl -d Ubuntu2204 -- echo OK` prints `OK`. If it errors about a
missing kernel component, **reboot Windows** once (a fresh WSL install needs a
reboot before the kernel is active).

**Gotcha — UTF-16LE output.** `wsl --list --quiet` emits UTF-16LE with embedded
NUL bytes; PowerShell 5.1 captures the NULs and `-match` silently fails to find
the distro name. `wsl-ensure.ps1` strips NULs (`-replace "`0"`) before matching.
If you write your own WSL detection, do the same.

**If you skip it.** The WSL-only scripts `setup.sh`, `verify.sh`, and
`score-cdm.sh` require a working WSL Ubuntu 22.04. The native Windows path
uses `verify-windows.ps1` as its verifier and does not require WSL.

---

<a id="distro-name"></a>
## #distro-name — `wsl -d Ubuntu2204` fails ("not found"), but a distro exists

**Symptom.** Every `wsl -d Ubuntu2204 ...` command in this repo fails with an
error like "The Windows Subsystem for Linux instance has not been started" or
"There is no distribution with the supplied name", yet `wsl --list` shows an
Ubuntu distro under a **different name** (commonly `Ubuntu`, `Ubuntu-22.04`,
or `Ubuntu-20.04`).

**Root cause.** Every script, README, and `\\wsl$\` UNC path in this repo
addresses the WSL distro by the canonical name **`Ubuntu2204`** (no dot, no
dash). `wsl --install -d Ubuntu-22.04` (the standard install command) creates a
distro named **`Ubuntu-22.04`** (with a dot and dash) instead — a name that
does not match. The same happens if you already had an `Ubuntu` distro from an
earlier `wsl --install` with no `-d` flag. The distro works fine; the name just
doesn't line up with what the scripts expect.

**Fix.** Pick one:

1. **Rename your existing distro to `Ubuntu2204`** (recommended — keeps your
   data). Export it to a tarball, unregister the old name, then import under the
   canonical name:

   ```powershell
   $old = "Ubuntu-22.04"   # or whatever `wsl --list` shows
   wsl --export $old "$env:TEMP\ubuntu-rename.tar.gz"
   wsl --unregister $old
   New-Item -ItemType Directory -Force -Path C:\WSL\Ubuntu2204 | Out-Null
   wsl --import Ubuntu2204 C:\WSL\Ubuntu2204 "$env:TEMP\ubuntu-rename.tar.gz" --version 2
   ```

   `scripts/wsl-ensure.ps1` already does this rename automatically when it
   detects an `Ubuntu-22.04` without a matching `Ubuntu2204`, so re-running it
   may be the quickest fix.

2. **Run `scripts/wsl-ensure.ps1` again** — it normalizes the distro name via
   the export/unregister/import dance above (see the `Rename-WslDistro` function
   in the script).

**Verify.** `wsl -d Ubuntu2204 -- echo OK` prints `OK`. `wsl --list` shows
`Ubuntu2204`.

**If you skip it.** Every WSL step (Step 2 CDM environment, Step 4b CDM scoring,
`full-verify.ps1`'s WSL checks) fails with "distro not found", and the error
doesn't point at the name mismatch — it looks like WSL itself is broken.

---

<a id="python-version"></a>
## #python-version — OmniDocBench needs Python < 3.12

**Symptom.** Importing OmniDocBench or running `pdf_validation.py` fails with
errors like `AttributeError: module 'inspect' has no attribute 'getargspec'` or
`ImportError: cannot import name '...' from 'distutils'`, on a Python 3.12
interpreter.

**Root cause.** OmniDocBench and several of its pinned deps (older `evaluate`,
`apted`) use APIs removed in Python 3.12 (`inspect.getargspec`, `distutils`,
`imp`). It works on 3.10 and 3.11.

**Fix.** Use the repository's locked uv environment. It installs a managed
Python 3.11 and synchronizes the same dependency set on every machine:

```powershell
winget install --id astral-sh.uv -e
uv python install 3.11
uv sync --locked --all-groups
```

`eval-infra/01-omnidocbench/setup.ps1` also uses uv when available and retains a
Python 3.10/3.11 compatibility fallback for existing installations. It now
stops before downloads or scoring rather than creating an unsupported venv.

**Verify.** `.\.venv\Scripts\python.exe --version` reports `3.11.x` (or a
deliberately selected `3.10.x`), then
`.\.venv\Scripts\python.exe -m pytest -q` passes.

**If you skip it.** Cryptic import errors mid-scoring, often deep inside
`evaluate`/`apted`. The version mismatch is not obvious from the traceback.

---

<a id="cdm-zero"></a>
## #cdm-zero — CDM F1 = 0 (the master decision tree)

**Symptom.** A CDM scoring run completes (exit 0), `metric_result.json` is
written, but `display_formula.CDM.all` is `0.0` (or near-0). Edit_dist on the
same formulas may be fine. No error is printed anywhere.

**Root cause.** CDM works by: compile each formula to a color-coded PDF →
rasterize to PNG → match colored bounding boxes between GT and prediction.
F1=0 means the color matching found nothing. There are **six** distinct ways
this happens, and they all look identical from the score. Walk this tree in
order:

```
CDM F1 = 0
│
├─ Are you running on Windows directly? ──────────────── YES → #posix
│   (CDM shells out to kpsewhich/magick/gs with POSIX semantics)
│
├─ `magick --version` shows ImageMagick 6, not 7? ────── YES → #grayscale
│   (IM6 renders color formulas as grayscale; no error)
│
├─ Count colors in a rendered formula PNG — only 2? ──── YES → #mathcolor
│   (\mathcolor defined but emitting black, or undefined)
│
├─ CJK glyphs are blank boxes / tofu in the PDF? ─────── YES → #gkaiu-map
│   (font files present but pdftex.map doesn't reference them)
│
├─ `kpsewhich CJK.sty` or `c70gkai.fd` empty? ────────── YES → #texlive-cjk
│   (system texlive missing CJK package; copy from TL2026)
│
└─ `magick` segfaults / "error loading shared library"? ─ YES → #im7-libs
    (IM7 AppImage deps missing: libfribidi etc.)
```

**Fix.** Follow the anchor for your branch. The canary that catches *all* of
these at once is `eval-infra/02-cdm-environment/verify.sh`: it compiles a CJK
color formula, counts colors in the PNG, and runs the real `CDM.evaluate` on
two identical formulas asserting F1 > 0.5. If `verify.sh` passes, CDM scoring
will produce real scores.

**Verify.** `verify.sh` prints `CDM F1 for identical formulas: 1.0` and
`VERIFY OK`. Then re-run `score-cdm.sh`.

**Why this entry is long.** This single failure mode consumed the majority of
the project's debugging hours. The deception is that *everything succeeds* —
LaTeX compiles, PDF rasterizes, Python imports — yet the score is zero. Only
inspecting the intermediate PNG (count its colors) reveals which branch you're
on. `verify.sh` automates exactly that inspection.

---

<a id="mathcolor"></a>
## #mathcolor — `\mathcolor` renders black (or undefined)

**Symptom.** A CDM formula PDF compiles without error, but the colored
bounding boxes are all black — so the color matcher finds nothing and CDM
F1=0. Variant: `! Undefined control sequence \mathcolor` aborts compilation
entirely.

**Root cause.** OmniDocBench's CDM template uses `\mathcolor{color}{expr}` to
color each formula fragment. TeX Live 2026's `xcolor` package either:
- doesn't define `\mathcolor` at all (`Undefined control sequence`), or
- defines it but the definition **ignores the color argument** and renders
  black (the insidious case — valid PDF, zero score).

**Fix.** `eval-infra/02-cdm-environment/setup.sh` step 8 patches
`src/metrics/cdm/modules/latex2bbox_color.py` to inject an explicit override
right after `\usepackage{xcolor}`:

```latex
\DeclareDocumentCommand{\mathcolor}{O{} m m}{\begingroup\color[#1]{#2}#3\endgroup}
```

`\DeclareDocumentCommand` (from `xparse`, autoloaded by TL2026) wins over any
package definition, so the override reliably takes effect. The same step
**reverts** earlier Windows experiments (`-strip`, `-colorspace sRGB` flags on
the `magick` call) that themselves caused grayscale output and masked this bug.

**Verify.** `verify.sh` prints `PDF→PNG color OK (4 colors)` — the `4` proves
red and blue were actually emitted. If you see `2 colors`, the patch regressed.

**If you skip it.** Either a hard LaTeX error on every formula, or — worse — a
clean compile that scores zero. See [#cdm-zero](#cdm-zero).

---

<a id="grayscale"></a>
## #grayscale — ImageMagick 6 renders color formulas as grayscale

**Symptom.** CDM F1=0 for every formula (see [#cdm-zero](#cdm-zero)). The
rendered formula PNG looks correct to the eye but is actually grayscale when
you count colors. `convert` (IM6) is what rasterized it.

**Root cause.** Ubuntu's packaged ImageMagick 6 (`convert`) silently flattens
the color-coded CDM formula PDFs to grayscale during PDF→PNG. No error, no
warning — the PNG comes out, `pdftoppm`/`gs` succeed, but every colored box is
now gray, so the CDM color matcher returns F1=0 for everything. **This is the
single most time-consuming bug in the whole project.**

**Fix.** Install ImageMagick 7 and make `magick` resolve to it.
`eval-infra/02-cdm-environment/setup.sh` step 5 downloads the official IM7
AppImage, extracts it, and installs `magick` + its libs system-wide
(`/usr/local/bin/magick`, `/usr/local/lib/im7`), registered with `ldconfig`.
IM7 does not have the grayscale bug.

**Critical detail — install system-wide, not from the AppImage.** Running IM7
straight from the extracted AppImage dir brings its *bundled* `libgs`, which
shadows the system Ghostscript and breaks PDF rasterization a different way
(see [#im7-gs](#im7-gs)). The system-wide copy + `ldconfig` avoids that.

**Verify.** `magick --version` reports `ImageMagick 7`. `verify.sh` color
count > 2. `which magick` points at `/usr/local/bin/magick`, not an AppImage.

**If you skip it.** CDM F1=0 for every formula, no error anywhere. You will
blame the LaTeX, the fonts, the Python, the venv — none of them. It is always
IM6. **Read this before touching step 5.**

---

<a id="gkaiu-map"></a>
## #gkaiu-map — `gkaiu` font not in `pdftex.map`

**Symptom.** CDM F1=0 on formulas containing CJK (Chinese) characters. The
PDF compiles, but CJK glyphs render as blank boxes/tofu, so the rasterized PNG
is mostly white and the color matcher sees nothing. Warning like
`pdflatex: Font gkai not found` may or may not appear.

**Root cause.** Even with the gkai (arphic) bitmap font *files* installed (see
[#texlive-cjk](#texlive-cjk)), `pdftex` won't embed them unless `pdftex.map`
has the map entries telling it how. `updmap-sys` is the "correct" tool but is
famously finicky — it silently no-ops if it thinks the map is enabled, or
refuses to write outside its own tree.

**Fix.** `eval-infra/02-cdm-environment/setup.sh` step 4 copies TL2026's
`fonts/map/dvips/arphic` map files into the system texlive tree, then
**directly appends** the `gkaiu` entries to the active `pdftex.map`
(`grep gkaiu <working-map> >> <active-map>`). Falls back to `updmap-sys` only
if direct injection can't locate a writable map.

**Verify.** `grep -q gkaiu "$(kpsewhich pdftex.map)"` succeeds. CJK formulas
in `verify.sh` produce visible glyphs.

**If you skip it.** Compiles fine, scores zero on any CJK formula. The most
deceptive failure mode — see [#cdm-zero](#cdm-zero).

---

<a id="im-policy"></a>
## #im-policy — ImageMagick 6 security policy blocks PDF

**Symptom.** A code path calling `convert` (IM6) on a PDF exits 1 with:
`attempt to perform an operation not allowed by your security policy 'PDF'
@ error/constitute.c/IsCoderAuthorized`. Or the same for `PS`.

**Root cause.** Debian/Ubuntu ship IM6 with `rights="none" pattern="PDF"` (and
`PS`) in `/etc/ImageMagick-6/policy.xml` — a 2018 Ghostscript-RCE hardening.
Any IM6 call that reads or writes PDF is denied.

**Fix.** `eval-infra/02-cdm-environment/setup.sh` step 6 rewrites those
`rights="none"` to `rights="read|write"` if the default rule is still present.
The primary CDM path uses IM7 (`magick`), so this is defensive — but step 5's
symlink means a stray `convert` somewhere can still trip it.

**Verify.** `grep 'pattern="PDF"' /etc/ImageMagick-6/policy.xml` shows
`rights="read|write"`.

**If you skip it.** Any fallback path that hits IM6 `convert` fails on PDF.
You may not hit it at all (if everything uses `magick`), hence defensive.

---

<a id="im7-libs"></a>
## #im7-libs — IM7 AppImage missing shared libraries

**Symptom.** Right after installing IM7 (step 5), `magick --version`
segfaults or exits 127 with `error while loading shared libraries:
libfribidi.so.0: cannot open shared object file` (or `libharfbuzz`,
`libfontconfig`, `libltdl`, etc.).

**Root cause.** The IM7 AppImage is built on a different distro and `dlopen`s
a minimal set of common libs that a fresh Ubuntu 22.04 may not have installed.

**Fix.** `eval-infra/02-cdm-environment/setup.sh` step 7 installs them:
`apt-get install libfribidi0 libharfbuzz0b libfontconfig1 libltdl7 libgomp1
libxml2`.

**Verify.** `magick --version` prints the IM7 banner with no errors.

**If you skip it.** Step 5 reports `IM7 installed` (the symlink was created)
but the very next `magick` invocation fails. `verify.sh` dies at
`IM7 not active`.

---

<a id="im7-gs"></a>
## #im7-gs — IM7 AppImage `libgs` shadows system Ghostscript

**Symptom.** After installing IM7 *from the AppImage dir* (not system-wide),
PDF→PNG rasterization breaks: `magick` exits non-zero on PDFs, or produces
corrupt output, even though `gs --version` works standalone.

**Root cause.** The AppImage bundles its own `libgs.so`. If IM7's lib dir is on
`LD_LIBRARY_PATH` (or the binary is run from the extracted squashfs), IM7's
`libgs` shadows the system Ghostscript, and the two are ABI-incompatible —
PDF rasterization inside `magick` breaks.

**Fix.** Don't run IM7 from the AppImage dir. `eval-infra/02-cdm-environment/
setup.sh` step 5 installs IM7 **system-wide**: copies only `magick` and its
`libMagick*.so` deps to `/usr/local/bin` + `/usr/local/lib/im7`, registers
the lib dir via `/etc/ld.so.conf.d/im7.conf` + `ldconfig`, and does **not**
put the AppImage's bundled `libgs` on the library path. The system Ghostscript
stays authoritative for `gs`.

**Verify.** `magick -density 100 any.pdf out.png` succeeds. `ldd $(which magick)
| grep gs` shows it linking the **system** `libgs` (under `/usr/lib`), not one
under a squashfs/AppImage path.

**If you skip it.** Step 5 "succeeds" (IM7 is active) but PDF rasterization
silently produces bad output or errors — which then looks like [#cdm-zero](#cdm-zero).

---

<a id="posix"></a>
## #posix — CDM code uses POSIX shell commands

**Symptom.** Running the CDM-enabled config on Windows directly produces
weird failures: `FileNotFoundError` on `kpsewhich`/`magick`/`gs`, malformed
paths with mixed `/` and `\`, or `shlex.quote` producing Windows-incompatible
output. Edit_dist + TEDS work fine; only CDM breaks.

**Root cause.** OmniDocBench's CDM metric shells out to `pdflatex`, `magick`,
`gs`, and `kpsewhich` via `subprocess` with POSIX assumptions: forward-slash
paths, `shlex` quoting, and coreutils-style command behavior. On Windows these
either aren't on `PATH`, behave differently, or get mis-quoted.

**Fix.** First run `powershell -ExecutionPolicy Bypass -File
eval-infra\02-cdm-environment\verify-windows.ps1`. If it fails, follow the
reported missing tool or use the WSL CDM path. The native verifier confirms the
tracked `windows-cdm.patch` is applied and that TeX Live, ImageMagick, and
Ghostscript can complete a real CDM smoke test. For the compatibility/reference
path, `eval-infra/03-scoring/score-cdm.sh` runs `pdf_validation.py` inside WSL
Ubuntu 22.04 with a clean Linux `PATH` (no `/mnt/c` Windows interop leakage).

**Verify.** `verify-windows.ps1` passes before drawing native-CDM conclusions,
or `score-cdm.sh` completes and `display_formula.CDM.all > 0` in
`metric_result.json` for the WSL path.

**If you skip it.** Native Windows CDM may fail because its toolchain or patch
is missing. WSL CDM remains the supported compatibility/reference path.

---

<a id="texlive-cjk"></a>
## #texlive-cjk — Ubuntu texlive lacks CJK.sty / gkaiu

**Symptom.** `pdflatex` aborts with `! LaTeX Error: File 'CJK.sty' not found.`
or `! LaTeX Error: File 'c70gkai.fd' not found.` when compiling a CDM formula
containing CJK.

**Root cause.** Ubuntu's packaged TeX Live is years old and ships an incomplete
CJK package (or none, depending on which `texlive-lang-*` you installed). The
official TeX Live 2026 (installed in step 2) has the complete CJK + arphic
(gkai) fonts, but OmniDocBench's CDM subprocess invokes `pdflatex` without
pinning to TL2026's binary — it uses whichever `pdflatex` is first on `PATH`,
which under several call sites is the *system* texlive.

**Fix.** `eval-infra/02-cdm-environment/setup.sh` step 3 copies TL2026's
`tex/latex/cjk` and `fonts/{afm,tfm,type1}/arphic` trees into the system
texlive's texmf-dist, then `mktexlsr`. Now both `pdflatex` binaries see the
same CJK + font files. (See also [#gkaiu-map](#gkaiu-map) for the map-file
half of this, and [#two-texlive-trees](#two-texlive-trees) for why both trees
must agree.)

**Verify.** `kpsewhich CJK.sty` and `kpsewhich c70gkai.fd` both return paths.

**If you skip it.** CDM crashes on the first CJK formula. Compiles of
English-only formulas may still work, masking the issue.

---

<a id="two-texlive-trees"></a>
## #two-texlive-trees — system texlive vs TL2026 disagree

**Symptom.** CDM works when you compile a test doc by hand with TL2026's
`pdflatex`, but fails when OmniDocBench's subprocess compiles the same doc.
Or vice versa. Inconsistent errors that depend on which `pdflatex` ran.

**Root cause.** There are **two** TeX Live installs after step 2: the system
one (`/usr/share/texlive`, from apt) and the official TL2026
(`/usr/local/texlive/2026`). They have different packages, different fonts,
different map files. Whichever `pdflatex` is first on `PATH` wins, and
different callers set PATH differently.

**Fix.** Two-pronged, both in `eval-infra/02-cdm-environment/setup.sh`:
1. Step 2 puts TL2026's bin dir **first** on PATH for the scoring run
   (`score-cdm.sh` sets the same PATH), so the official `pdflatex` is used.
2. Steps 3–4 copy TL2026's CJK.sty + arphic fonts + map entries into the system
   tree, so even if the system `pdflatex` is invoked, it has everything TL2026
   has. Defense in depth: both trees agree.

**Verify.** Both `pdflatex` binaries compile the `verify.sh` test doc
identically. `which pdflatex` shows TL2026's path during scoring.

**If you skip it.** Heisenbug: CDM passes or fails depending on which code path
invoked `pdflatex`. Step 8 of setup copies the OmniDocBench code into
`/root/OmniDocBench` so the working dir + PATH are controlled.

---

<a id="wsl-tlpdb-lock"></a>
## #wsl-tlpdb-lock — TeX Live package database differs from upstream-lock.json

**Symptom.** `setup.sh` step 2 prints
`✗ FAILED: TeX Live package database size differs from upstream-lock.json`
(and `verify.sh` prints `FAIL: TeX Live lock size/SHA mismatch`), even though
`pdflatex` exists and CDM pipelines compile fine by hand.

**Root cause.** `upstream-lock.json` pins the WSL TL2026
`/usr/local/texlive/2026/tlpkg/texlive.tlpdb` by size + SHA-256. The tlpdb is
snapshot-specific: it changes with every `tlmgr` install/remove/update and
with the install-tl profile. A re-install with a different profile (e.g. a
`scheme-infraonly` run on top of a full tree) replaces the tlpdb with a much
smaller database while leaving the installed package files intact — the tree
looks broken to the lock but still compiles. Live CTAN mirrors cannot
reproduce a historical tlpdb (no reachable snapshot archives).

**Fix.** Decide whether the tree is functionally correct first, then re-lock
with evidence (see `docs/upstream-lock.md` "2026-08-02 update"):
1. Restore the tlpdb to the installed-package state from tlmgr's backup
   (`texlive.tlpdb.main.<hash>` in the same directory) if one exists.
2. Re-sync `/root/odb-venv` to `requirements.lock.txt`
   (`pip install --require-hashes -r ... -i <working index>`).
3. Run the CDM end-to-end verify manually (CJK compile → PDF → color PNG →
   CDM F1 > 0.5) — the `verify.sh` standard without the tlpdb gate.
4. Update `wsl_cdm` in `upstream-lock.json` (tlpdb bytes/SHA, tlmgr revision)
   and record the evidence in `docs/upstream-lock.md`; never replace a hash
   just because a mirror served different bytes.

**Verify.** `eval-infra/02-cdm-environment/verify.sh` prints `VERIFY OK`;
`reproduce.ps1` passes `cdm.wsl_environment` and WSL CDM scoring yields a
positive CDM score.

**If you skip it.** The WSL CDM stage fails closed forever on that machine;
the failure is by design (fail-closed on mismatched content), not a bug.

---

<a id="pythonutf8"></a>
## #pythonutf8 — Windows codepage corrupts JSON / LaTeX I/O

**Symptom.** On Windows, `pdf_validation.py` crashes with
`UnicodeDecodeError` mid-run, or produces a `metric_result.json` that's valid
JSON but contains mojibake for any CJK content. CDM LaTeX compilation fails on
characters that look fine in the source.

**Root cause.** Python on Windows defaults to the system ANSI codepage
(cp1252 / cp936) for file I/O unless told otherwise. OmniDocBench reads and
writes UTF-8 JSON (with CJK strings) and the CDM template has CJK LaTeX — both
get corrupted under the default codepage.

**Fix.** Set `PYTHONUTF8=1` for every scoring run. Both `score.ps1` and
`score-cdm.sh` set it. `PYTHONUTF8=1` (PEP 540) forces Python into UTF-8 mode
for all text I/O regardless of the console codepage.

**Verify.** A scoring run completes without `UnicodeDecodeError` and the
`metric_result.json` CJK strings round-trip cleanly (`Get-Content | ConvertFrom-
Json` in `verify.ps1` works).

**If you skip it.** Random encoding errors, or worse — a "successful" run with
corrupted scores. Never run a scoring pass without `PYTHONUTF8=1`.

---

<a id="layout"></a>
## #layout — ONNX layout model not found

**Symptom.** An adapter's layout step fails with `onnxruntime.capi.
onnxruntime_pybind11_state.NoSuchFileException` or `RuntimeError: ... model
file not found`. Or the adapter produces no predictions.

**Root cause.** The layout model (e.g. PP-DocLayoutV3 ONNX) wasn't downloaded,
or its path in the adapter's `.env.local` is wrong/relative-and-broke.

**Fix.** Re-run the adapter's layout-model `setup.ps1`
(e.g. `adapters/paddleocr-vl-1.6/02-layout-model/setup.ps1`). It downloads the
model from the source recorded in `mirrors.env` (`VLM_MODEL_URL` /
`LAYOUT_MODEL_URL`) into a `models/` dir (gitignored) and writes the absolute
path to `.env.local`. The adapter reads `.env.local` for the path at runtime.

**Verify.** The adapter's `verify.ps1` passes. `Test-Path` the model file in
`.env.local`.

**If you skip it.** No predictions → every metric is zero → looks like a
scoring bug but is actually an adapter bug. Run the adapter's verify before
scoring.

---

<a id="wsl-fork-fork"></a>
## #wsl-fork-fork — WSL CDM scoring crashes: "can only join a started process"

**Symptom.** `score-cdm.sh` on the full 1651-page set crashes mid-run (often
around 82% of "Matching pages") with
`AssertionError: can only join a started process` from
`multiprocessing/process.py` in `_latex_to_text_with_timeout`, preceded by
`WARNING: os.fork is unsafe while filelock is changing descriptor ownership`.

**Root cause.** On WSL/Linux, `multiprocessing` uses the fork start method. The
formula matching phase runs `match_workers` workers; a worker that itself forks
a `latex_to_text_with_timeout` subprocess while another thread holds a
`filelock` descriptor produces a broken child, and the subsequent
`process.join()` asserts on a never-started process. It is a race: the same
run can pass or fail (observed ~50% failure at 1651 pages with
`match_workers: 24`). Windows-native scoring uses spawn and never hits this.

**Fix.** Use `match_workers: 1` (and `teds_workers: 1`) in the WSL CDM scoring
config — the value proven by the v16-cdm-cpu-200 WSL reference run. Worker
counts never change scores, only speed; single-worker matching is slower but
deterministic and crash-free. Keep high worker counts only in the
Windows-native scoring configs.

**Verify.** `score-cdm.sh` completes the full 1651-page run without the
AssertionError; the WSL result's shared metrics equal the Windows result's
(delta 0.0) apart from documented quick-match timeout fallbacks.

**If you skip it.** Flaky ~50% crashes 16+ minutes into every full WSL CDM
scoring run; retries eventually succeed but waste time and look like
environment corruption.

---

<a id="vlm"></a>
## #vlm — VLM server startup failures / 500 errors

**Symptom.** An adapter's `run_adapter.py` gets HTTP 500 (or connection
refused) from the VLM server. Or the server fails to start with a CUDA / ROCm
/ OOM error.

**Root cause.** Most commonly: the server wasn't started, started on a
different port than the adapter points at, or crashed mid-run (OOM). For
llama.cpp-served GGUF models, also: wrong quantization for available VRAM,
missing ROCm/CUDA runtime, or a stale `.env.local` pointing at a dead PID.

**Fix.** Re-run the adapter's `01-vlm-server/setup.ps1`; it starts the server
and writes the URL + PID to `.env.local`. Check `logs/` for the server's
stderr. For OOM, drop to a smaller quantization or reduce `--n-gpu-layers`.

**One GPU, one HIP server.** Running two HIP `llama-server` instances
concurrently on the same AMD GPU (e.g. an earlier profile's server left
running while the next profile starts its own on a different port) can make
the second one die silently during model load with no error line in the log
— `setup.ps1` then reports "llama-server not ready after 5 minutes". Stop
the leftover server first (`Stop-Process -Id <pid from logs/llama-server.pid>`)
before starting the next profile's server.

**Verify.** `curl <server-url>/health` (or the model's equivalent) returns 200
before running the adapter. The adapter's `verify.ps1` does this.

**If you skip it.** Empty or partial predictions; per-page failures are caught
by `run_adapter` (one bad page scores zero, the rest continue), but a totally
dead server means zero predictions for every page.

---

<a id="official-pretty-markdown"></a>
## #official-pretty-markdown - Official PaddleOCRVL pretty Markdown hurts Text Edit-distance

**Symptom.** Switching from the lightweight PaddleOCR-VL-ROCm adapter path to
the official `paddleocr.PaddleOCRVL` doc_parser path makes non-CDM metrics,
especially `text_block.Edit_dist`, worse on pages with figures/captions, even
when the recognized text itself looks similar.

**Root cause.** PaddleOCRVL's default Markdown export is
presentation-oriented: `_to_markdown(pretty=True)` wraps centered images and
captions in HTML such as:

```html
<div style="text-align: center;"><img src="imgs/..." alt="Image" width="45%" /></div>
```

OmniDocBench's `md_tex_filter()` removes Markdown image syntax
`![](imgs/...)`, but non-table HTML image wrappers are left as ordinary
`text_all` candidates. This changes the candidate sequence and can make
quick-match pair the wrong text spans.

**Fix.** For benchmark scoring, export official PaddleOCRVL results with
evaluation-oriented Markdown:

```python
markdown = result._to_markdown(pretty=False)["markdown_texts"]
```

The repo's `adapters/paddleocr-vl-1.6/run_adapter.py --engine official` does
this by default and keeps a small HTML-wrapper normalization fallback for older
or alternate result objects.

**Verify.** On the 2026-07-09 Text regression probe, raw official pretty
Markdown scored `0.430483` Text Edit-distance; `_to_markdown(pretty=False)`
scored `0.183316`, matching the HTML-normalized diagnostic path and nearly
matching lightweight `0.178384`.

On the published full-set official-prettyfalse run, Text Edit-distance is
`0.03446`, close to the public `0.033` baseline and the local
PaddleOCR-VL-ROCm engine's `0.03397`. Score it with
`v16-official-prettyfalse-full-2026-07-09.yaml` and the paired WSL CDM config
`v16-cdm-official-prettyfalse-full-2026-07-09.yaml`.

---

<a id="miopen-finddb"></a>
## #miopen-finddb — MIOpen find-db corruption after an unclean shutdown

**Symptom.** ROCm/HIP inference that was fast yesterday is suddenly 20–100×
slower per page (e.g. 200–450 s/page instead of 9–29 s/page), with no code or
model change. A direct torch probe may **crash inside MIOpen** with
`MIOpen(HIP): Warning [TryLockOperation] File <"...\.miopen\db\miopen-lockfiles\...ufdb.txt.lock"> timed lock timed out`
followed by an abort in `miopen::RamDb::StoreRecord` /
`miopenFindConvolutionForwardAlgorithm`.

**Root cause.** The machine suffered an unclean shutdown (Windows System log
Event 41, Kernel-Power) while MIOpen was writing its per-user convolution
find-db (`~/.miopen/db/<arch>...ufdb.txt`, tens of MB). The file is left
corrupted: every convolution algorithm lookup pays a lock timeout, and
`StoreRecord` aborts on write. Real incident: Phase B gate run, 2026-08-01
20:35 shutdown, discovered 2026-08-02 — see
[mineru-sample81-gate-2026-08-01.md](benchmarks/mineru-sample81-gate-2026-08-01.md).

**Fix.** Delete the user find-db **and** its stale lock files; the find-db is a
pure cache and MIOpen rebuilds it automatically on the next run (the first
convolution of each shape pays a one-time "find" cost, e.g. ~14 s, then steady
state returns). Discard any predictions produced by the degraded run — they are
valid content-wise but their timings poison any per-page statistics.

**Verify.** Re-run one inference page (or a small torch probe): first conv
rebuilds the cache, then steady-state speed is back to normal (e.g. conv
~16 ms/iter, matmul 4096³ ~60 ms/iter ≈ 2.3 TFLOPS on Strix Halo). Per-page
adapter timings return to their previous range.

---

<a id="gpu-counters-windows"></a>
## #gpu-counters-windows — Windows AMD GPU utilization/power counters unavailable

**Symptom.** On Windows with an AMD GPU, there is no `nvidia-smi` equivalent:
`rocm-smi` is not on PATH (not shipped for Windows), and GPU utilization /
power performance counters read ~0% (or stay flat) even during genuinely
GPU-bound ROCm/HIP work. Resource monitors degrade to `gpu-unavailable` and
can only log RAM/CPU.

**Root cause.** The Windows ROCm driver surface does not expose the Linux
sysfs/perf counters that `rocm-smi` and friends read. Utilization and power
telemetry simply isn't accessible from user space; this is a platform
limitation, not a misconfiguration.

**Fix.** Measure what *is* exposed. Use the torch API inside the workload:
`torch.cuda.get_device_name()`, `mem_get_info()` / `memory_allocated()` for
GPU-side memory, and a compute probe (e.g. matmul 4096³ → TFLOPS) as the
"is the GPU healthy and working" signal. On Strix Halo's unified memory, use
**system RAM as a proxy**: GPU allocations surface directly in RAM, so RAM
deltas track GPU memory pressure. See
[strix-halo-ai-max395.md](benchmarks/strix-halo-ai-max395.md) for the measured
probe numbers and monitor degradation behavior.

**Verify.** The probe script prints device name, device total/allocated MiB,
and a sane TFLOPS number (~2.1–2.3 on Strix Halo); a sustained GPU allocation
shows up as a matching system-RAM delta in the monitor log.

---

## How to add a new entry

1. Find the failing symptom (one sentence a user/agent would search for).
2. Add a section with anchor `#<short-id>`: **Symptom → Root Cause → Fix → Verify**.
3. Cross-link from the relevant setup step's README and code comments.
4. If the fix is encoded in a setup script, cite the step number
   (`setup.sh step N`) so the doc and code stay in sync.

The discipline is: every landmine that cost you time goes here, organized by
symptom, so the next person (or agent) finds it in one search.
