# 02-cdm-environment — the 9-step CDM setup

## What this is

The hardest part of running OmniDocBench on Windows is the **CDM** (Content
Distance Metric) — the formula-rendering evaluator that compiles LaTeX to PDF,
rasterizes it to a color-coded PNG, and matches colored bounding boxes between a
ground-truth formula and a predicted one. Every step of that pipeline has a
landmine on Windows/WSL, and we stepped on all of them. This module is the
single idempotent installer that encodes the full set of fixes.

It supports two CDM toolchain paths. The native Windows path applies
`windows-cdm.patch` during `01-omnidocbench/setup.ps1` and passes
`verify-windows.ps1`. The WSL compatibility/reference path provisions the
9-step environment and passes `verify.sh`. Each verifier checks that the CDM
F1 score for two identical formulas is > 0.5, the canary that catches every
known failure mode at once.

Three scripts:

- **`setup.sh`** — the 9-step installer. Run inside WSL:
  `wsl -d Ubuntu2204 bash setup.sh`. Each step self-checks and is idempotent, so
  re-running is safe and skips already-completed work.
- **`verify.sh`** — end-to-end check. Run inside WSL:
  `wsl -d Ubuntu2204 bash verify.sh`. Compiles a CJK color formula → PDF → PNG,
  confirms the PNG is genuinely multi-color (not grayscale), then runs the real
  `CDM.evaluate` on two identical formulas and asserts F1 > 0.5.
- **`verify-windows.ps1`** - native Windows CDM verifier. Run from PowerShell
  after `eval-infra/01-omnidocbench/setup.ps1`; it checks patch sentinels,
  TeX Live, ImageMagick, Ghostscript discovery, and a real CDM smoke test.

> These scripts were distilled from 20+ throwaway `cdm_*.sh` debug scripts. If
> you change the selected CDM path, re-run its applicable verifier first:
> `verify-windows.ps1` for native Windows or `verify.sh` for WSL. For the full
> narrative of each pitfall, see [`docs/pitfalls.md`](../../docs/pitfalls.md).

## Why it's a separate module

CDM is the only OmniDocBench metric with a non-Python system dependency (a
working LaTeX + ImageMagick + Ghostscript toolchain that renders color
correctly). Everything else — Edit distance, TEDS, reading order — runs on pure
Python and just works. Isolating CDM setup behind its own module means:

- The ~30-minute TeX Live 2026 + IM7 install happens **once**, ever.
- Adapters (Task 4) and scoring (Task 5) can assume CDM works without each
  re-provisioning it.
- The exact recipe is version-controlled, not memorized.

## Usage

```powershell
# Native Windows path: setup.ps1 applies windows-cdm.patch. Verify this path
# with native TeX Live, ImageMagick, and Ghostscript on PATH.
powershell -ExecutionPolicy Bypass -File ..\01-omnidocbench\setup.ps1
powershell -ExecutionPolicy Bypass -File verify-windows.ps1
```

Or use the WSL compatibility/reference path:

```powershell
# In WSL, this repo is at /mnt/c/<your-clone-path>/omnidocbench-amd-windows.
# Replace the path below with your actual clone location:
wsl -d Ubuntu2204 bash /mnt/c/<path-to-repo>/eval-infra/02-cdm-environment/setup.sh

# Verify it works (should print "VERIFY OK: CDM environment fully functional.").
wsl -d Ubuntu2204 bash /mnt/c/<path-to-repo>/eval-infra/02-cdm-environment/verify.sh
```

`setup.sh` reads `../../mirrors.env` (produced by `scripts/detect-mirrors.ps1`)
for `CTAN_MIRROR`, `GITHUB_PROXY`, and `PYPI_INDEX`. If `mirrors.env` is absent
it falls back to USTC's CTAN mirror and a public GitHub proxy with a warning.

## WSL path prerequisites

- **WSL Ubuntu 22.04 installed and bootstrapped** — from Task 1's
  `scripts/wsl-ensure.ps1`. `setup.sh` assumes `apt-get` works and that `/root`
  is writable.
- **OmniDocBench eval code present** — from Task 2's
  `eval-infra/01-omnidocbench/setup.ps1`, which clones the repo into
  `eval-infra/01-omnidocbench/OmniDocBench/`. Step 8 copies it into the WSL
  filesystem at `/root/OmniDocBench` (faster I/O than `/mnt/c`).

## The 9 steps

Each step below has four parts: **what** it does, **why** it's needed, **what
problem it solves**, and **what breaks if you skip it**.

---

### Step 1 — apt base CDM deps

**What.** `apt-get install texlive-lang-cjk texlive-lang-chinese
texlive-latex-extra texlive-fonts-recommended texlive-science imagemagick
ghostscript curl perl git`.

**Why.** Ubuntu's packaged TeX Live gives us a working `pdflatex`, basic LaTeX
packages, the CJK language collection, and `gs` / `convert` (IM6) for free, in
one fast `apt` call. This is the floor everything else builds on.

**Problem solved.** Without `texlive-lang-chinese`, no `arphic` font package and
no CJK infrastructure at all — Step 3's font copy would have nothing to copy
into and no CJK.sty foundation. Without `ghostscript`, IM6 cannot rasterize PDF
back to PNG.

**If skipped.** Steps 2–4 still partly run (TL2026 is self-contained) but the
*system* texlive tree they copy fonts *into* wouldn't exist; `kpsewhich` lookups
fail in confusing ways. `gs` missing → `convert pdf png` exits 124.

---

### Step 2 — TeX Live 2026 (official)

**What.** Downloads the official `install-tl` installer from `$CTAN_MIRROR`,
runs it non-interactively with a profile that selects `scheme-medium` plus the
CJK and Chinese collections, into `/usr/local/texlive/2026`. Puts
`2026/bin/x86_64-linux` first on `PATH`.

**Why.** Ubuntu's TeX Live (Step 1) is years old and **lacks `\mathcolor`**
(the color-in-math command OmniDocBench's CDM relies on) and ships an
incomplete CJK package. Only the current official TeX Live has both. We need
the *official* distribution side-by-side with the *system* one — Step 3 bridges
them.

**Problem solved.** The `\mathcolor` not-defined error, and the "CJK.sty /
c70gkai.fd not found" errors. Both are symptoms of an outdated system TeX Live.

**If skipped.** `pdflatex` aborts at `\mathcolor` with `Undefined control
sequence` on the very first CDM formula. Or, if you patch `\mathcolor` away, it
aborts at `\usepackage{CJK}` with `File 'CJK.sty' not found`. Either way: every
CDM evaluation crashes — F1 = 0 for every formula.

> See `docs/pitfalls.md#mathcolor` and `docs/pitfalls.md#cjk-sty-missing`.

---

### Step 3 — Copy CJK.sty + gkai fonts from TL2026 → system texlive

**What.** `cp -rn` the `tex/latex/cjk` directory and the `fonts/{afm,tfm,type1}/arphic`
trees from `/usr/local/texlive/2026/texmf-dist` into
`/usr/share/texlive/texmf-dist`, then `mktexlsr` to rebuild the filename
database.

**Why.** OmniDocBench's CDM invokes `pdflatex` **without** pinning to TL2026's
binary — it relies on whatever `pdflatex` is first on `PATH`, which under
several call sites is the *system* texlive. The system texlive has no CJK.sty
and no gkai (arphic) bitmap fonts. Copying them in (rather than rebuilding PATH
everywhere) makes both toolchains behave identically.

**Problem solved.** `! LaTeX Error: File 'CJK.sty' not found.` and
`! LaTeX Error: File 'c70gkai.fd' not found.` — the two errors you get when the
*system* pdflatex is asked to compile a CJK document.

**If skipped.** Whichever code path ends up calling the system `pdflatex`
(notably the CDM metric's subprocess) fails to find CJK.sty and crashes. The
fix is invisible unless you know there are *two* texlive trees that must agree.

> See `docs/pitfalls.md#two-texlive-trees`.

---

### Step 4 — Inject gkaiu font map → pdftex.map

**What.** Finds the active `pdftex.map`, copies TL2026's
`fonts/map/dvips/arphic` map files into the system tree, then directly appends
the `gkaiu` map entries into `pdftex.map`. Falls back to `updmap-sys` if direct
injection can't locate a writable map.

**Why.** Even with the gkai font *files* present (Step 3), `pdftex` won't embed
them unless `pdftex.map` tells it how. `updmap-sys` is the "correct" tool, but
it is famously finicky — it silently no-ops if it thinks the map is already
enabled, or refuses to write outside its own tree. Direct `grep >> map` is the
reliable path we settled on after `cdm_map.sh` / `cdm_map2.sh` both failed.

**Problem solved.** `PDF warning: pdflatex: Font gkai not found` and the
resulting tofu/blank glyphs in CJK PDFs — which downstream look like "CDM F1=0
even though compilation succeeded."

**If skipped.** CJK characters render as blank boxes in the PDF, the rasterized
PNG is mostly white, and the CDM bounding-box matcher sees no colored content →
F1 = 0 for any formula containing CJK. Compiles fine; scores zero. The most
deceptive failure mode in the whole pipeline.

> See `docs/pitfalls.md#gkaiu-map`.

---

### Step 5 — ImageMagick 7

**What.** Downloads the official `ImageMagick-7.1.2-26-gcc-x86_64.AppImage`
(via `$GITHUB_PROXY` if set), extracts it, copies `magick` and its shared
libraries into `/usr/local/bin` + `/usr/local/lib/im7`, registers the lib dir
with `ldconfig`, copies the IM7 config tree to `/usr/local/etc/ImageMagick-7`,
and symlinks `/usr/local/bin/magick` → the IM7 binary.

**Why.** **This is the single most important step.** Ubuntu's ImageMagick 6
(`convert`) **silently renders color-coded formula PDFs as grayscale.** The PNG
comes out, `pdftoppm` / `gs` succeed, no error is printed — but every colored
bounding box is now gray, so the CDM color matcher finds zero matches and
returns F1 = 0 for *every* formula. IM7 does not have this bug. We install
IM7's libraries system-wide (rather than running from the AppImage) so that the
`libMagick*.so` IM7 ships don't shadow `libgs` — the AppImage bundled its own
`libgs` that conflicted with the system Ghostscript and broke PDF rasterization
in a different way.

**Problem solved.** The "everything compiles, F1 is always 0, no error
anywhere" ghost-bug that consumed the most debugging hours of the entire
project. Diagnosed by counting colors in the output PNG (the same check
`verify.sh` performs).

**If skipped.** CDM F1 = 0 for every formula, with no error message anywhere in
the pipeline. You will suspect the LaTeX, the fonts, the Python, the venv —
none of them. It is always IM6's grayscale rendering.

> See `docs/pitfalls.md#grayscale` — **read this before changing Step 5.**

---

### Step 6 — Allow PDF in ImageMagick 6 policy.xml

**What.** If `/etc/ImageMagick-6/policy.xml` still has the default Debian/Ubuntu
`rights="none" pattern="PDF"` (and `PS`) sandbox rule, rewrites it to
`rights="read|write"`.

**Why.** Debian disables PDF read/write in IM6 by default (a Ghostscript RCE
hardening from 2018). Some CDM code paths and older tooling fall back to IM6's
`convert`; if PDF is blocked they exit 1 with the misleading error
`attempt to perform an operation not allowed by your security policy`.

**Problem solved.** `convert-im6.q16: attempt to perform an operation not
allowed by your security policy 'PDF' @ error/constitute.c/IsCoderAuthorized/408`.

**If skipped.** Any code path that calls `convert` (IM6) instead of `magick`
(IM7) fails on PDF rasterization. The primary CDM path uses IM7 so this is
defensive — but Step 5's symlink means a stray `convert` somewhere can still
trip it.

---

### Step 7 — IM7 system library deps

**What.** `apt-get install libfribidi0 libharfbuzz0b libfontconfig1 libltdl7
libgomp1 libxml2` — the shared libraries IM7's extracted binaries dlopen but
that aren't pulled in by the AppImage.

**Why.** The AppImage is built on a different distro and assumes a minimal set
of common libs that a fresh Ubuntu 22.04 may not have. Without them, `magick
--version` segfaults or exits 127 with `error while loading shared libraries:
libfribidi.so.0`.

**Problem solved.** `magick: error while loading shared libraries: libXxx.so.N:
cannot open shared object file` right after Step 5.

**If skipped.** Step 5 reports `IM7 installed` (the symlink was made) but the
very next `magick --version` fails, and `verify.sh` dies at `IM7 not active`.

---

### Step 8 — OmniDocBench code + `\mathcolor` override fix

**What.** Copies `eval-infra/01-omnidocbench/OmniDocBench` into `/root/OmniDocBench`
(faster WSL-native I/O than `/mnt/c`), strips its `.git`, then patches
`src/metrics/cdm/modules/latex2bbox_color.py`: after `\usepackage{xcolor}` it
injects
`\DeclareDocumentCommand{\mathcolor}{O{} m m}{\begingroup\color[#1]{#2}#3\endgroup}`.
Also reverts any stray Windows-specific patches (`-strip`, `-colorspace sRGB`).

**Why.** TeX Live 2026's `xcolor` does **not** define `\mathcolor` as a
command, but OmniDocBench's CDM template uses it. Worse, some `xcolor`
versions *do* define it but render it **black** (ignoring the color argument) —
which produces a valid PDF that scores F1 = 0 because there's no color to
match. The `\DeclareDocumentCommand` override forces `\mathcolor` to actually
emit the color, and the override survives because `\DeclareDocumentCommand`
wins over any package definition.

**Problem solved.** Both `Undefined control sequence \mathcolor` *and* the more
insidious "`\mathcolor` defined but renders black" — the latter masquerades as
a working setup until you count colors in the PNG.

**If skipped.** Either a hard LaTeX error (formula won't compile), or — worse —
a clean compile whose output PDF is black-on-white, rasterized to a 2-color
grayscale PNG, F1 = 0. The `-strip` / `-colorspace sRGB` reverts undo earlier
Windows experiments that themselves caused grayscale output; leaving them in
re-introduces the Step 5 bug.

> See `docs/pitfalls.md#mathcolor-renders-black`.

---

### Step 9 — Python venv + OmniDocBench deps

**What.** Creates `/root/odb-venv` (Python 3 venv) and `pip install`s the CDM
runtime deps from Tsinghua's PyPI mirror: `apted beautifulsoup4 evaluate
func-timeout Levenshtein loguru lxml numpy pandas Pillow pylatexenc PyYAML scipy
tabulate tqdm nltk matplotlib`.

**Why.** OmniDocBench's Python (which `cdm_metric.py` imports from) needs
`pylatexenc`, `Pillow`, `numpy`, `scipy`, and a handful of utility libs.
Installing into an isolated venv avoids polluting the system Python and avoids
version conflicts with anything else in WSL. `verify.sh` activates this venv
before calling `CDM.evaluate`.

**Problem solved.** `ModuleNotFoundError: No module named 'pylatexenc'` (and
its many siblings) when the CDM metric tries to parse LaTeX.

**If skipped.** `verify.sh` dies at the `CDM F1 test` stage with an ImportError
— the LaTeX/ImageMagick pipeline is fine but the Python side can't import the
metric.

---

## Expected result

```
=== Checking tools ===
  tools OK
=== Checking CJK + gkai ===
  CJK OK
=== Compile test: CJK formula → PDF → color PNG ===
  PDF→PNG color OK (4 colors)
=== CDM F1 test ===
  CDM F1 for identical formulas: 1.0

VERIFY OK: CDM environment fully functional.
```

The `4 colors` line is the canary: it proves `\mathcolor` actually emitted red
and blue (plus the white background and any anti-aliasing). If you ever see
`2 colors` there, Step 5 (IM7) or Step 8 (the `\mathcolor` fix) has regressed.

## Idempotency & re-runs

Every step guards on a presence check (`dpkg -s`, `[ -x ... ]`, `kpsewhich`,
`magick --version | grep`, `[ -d /root/odb-venv ]`, etc.) before doing work, so
`setup.sh` is safe to re-run. After the first run it completes in seconds and
prints `already installed` / `already active` for each step.

`verify.sh` is non-mutating (it writes only to `/tmp`) and can be run any time.

## Related

- [`eval-infra/01-omnidocbench`](../01-omnidocbench/README.md) — provides the
  OmniDocBench source tree that Step 8 copies.
- [`scripts/wsl-ensure.ps1`](../../scripts/wsl-ensure.ps1) — provisions the WSL
  Ubuntu 22.04 instance this all runs inside.
- [`mirrors.env`](../../mirrors.env) — `CTAN_MIRROR`, `GITHUB_PROXY`,
  `PYPI_INDEX` consumed by setup.sh.
- [`docs/pitfalls.md`](../../docs/pitfalls.md) — full narrative of each CDM
  landmine (`#grayscale`, `#mathcolor`, `#cjk-sty-missing`, `#gkaiu-map`,
  `#two-texlive-trees`, `#mathcolor-renders-black`).
