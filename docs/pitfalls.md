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
- [PYTHONUTF8 / Windows codepage corruption](#pythonutf8)
- [Layout (ONNX) model not found](#layout)
- [VLM server 500 errors](#vlm)
- [Official PaddleOCRVL pretty Markdown hurts Text Edit-distance](#official-pretty-markdown)

---

<a id="network"></a>
## #network — GitHub / HuggingFace / CTAN / Store blocked

**Symptom.** Downloads hang, time out, or fail with `Connection refused` /
`Could not resolve host` for `github.com`, `huggingface.co`, `mirror.ctan.org`,
or the Microsoft Store. Common behind the China firewall but also on
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

**If you skip it.** Nothing in `eval-infra/02-cdm-environment` (the CDM
environment) or `score-cdm.sh` can run — they all assume a working WSL
Ubuntu 22.04.

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

**Fix.** Use Python 3.10 or 3.11 for the OmniDocBench venv. The venv created by
`eval-infra/01-omnidocbench` pins 3.11. If you build your own venv, pin
explicitly:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r eval-infra\01-omnidocbench\OmniDocBench\requirements.txt
```

**Verify.** `python --version` reports `3.11.x` (or `3.10.x`) inside the venv.

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

**Fix.** Run CDM in WSL, never Windows-native. `eval-infra/03-scoring/score-cdm.sh`
runs `pdf_validation.py` inside WSL Ubuntu 22.04 with a clean Linux `PATH`
(no `/mnt/c` Windows interop leakage). Use `eval-infra/03-scoring/score.ps1`
for the Edit_dist + TEDS-only pass on Windows.

**Verify.** `score-cdm.sh` completes and `display_formula.CDM.all > 0` in
`metric_result.json`.

**If you skip it.** Hours lost trying to make CDM work on Windows. It can be
forced but every subprocess call is a new edge case. WSL is the supported path.

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

## How to add a new entry

1. Find the failing symptom (one sentence a user/agent would search for).
2. Add a section with anchor `#<short-id>`: **Symptom → Root Cause → Fix → Verify**.
3. Cross-link from the relevant setup step's README and code comments.
4. If the fix is encoded in a setup script, cite the step number
   (`setup.sh step N`) so the doc and code stay in sync.

The discipline is: every landmine that cost you time goes here, organized by
symptom, so the next person (or agent) finds it in one search.
