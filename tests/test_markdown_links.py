"""Guard: relative links in tracked markdown files must resolve."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def strip_code(text: str) -> str:
    """Remove fenced code blocks and inline code spans before link scanning."""
    text = FENCE_RE.sub("", text)
    return INLINE_CODE_RE.sub("", text)


def tracked_markdown_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [ROOT / line.strip() for line in out.stdout.splitlines() if line.strip()]


def test_relative_markdown_links_resolve():
    broken = []
    for md in tracked_markdown_files():
        text = strip_code(md.read_text(encoding="utf-8"))
        for m in LINK_RE.finditer(text):
            target = m.group(1).split("#")[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            if not (md.parent / target).resolve().exists():
                broken.append(f"{md.relative_to(ROOT)}: {target}")
    assert not broken, "broken relative links:\n" + "\n".join(broken)
